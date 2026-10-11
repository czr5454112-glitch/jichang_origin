"""Fixed paired ridge comparator; no absolute-cost fit or learned intercept.

Training uses the same fold-only selected-feature normalization and paired
targets as the role MLP. The declared ridge objective is mean paired squared
error + alpha * ||w||^2, with alpha=1 in the experiment. This differs from the
MLP regularizer/parameter count and is not a capacity-matched comparison.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json

import numpy as np

from .nonlinear_learning import _array, _feature_names, _feature_vector, _number


@dataclass(frozen=True)
class LinearConfig:
    alpha: float = 1.
    # Compatibility with the existing selector manifest; no random operation.
    seed: None = None

    def __post_init__(self):
        value = _number(self.alpha, "alpha")
        if value <= 0 or self.seed is not None:
            raise ValueError("positive ridge alpha required; linear model has no seed")
        object.__setattr__(self, "alpha", value)


@dataclass(frozen=True)
class PairedLinearModel:
    kind: str
    feature_names: tuple
    center: np.ndarray
    scale: np.ndarray
    weights: np.ndarray
    config: LinearConfig
    training_metadata: dict

    def __post_init__(self):
        if self.kind not in {"paired_direct", "residual"}:
            raise ValueError("linear comparison requires a paired target")
        names = _feature_names(self.feature_names, self.kind)
        if names != tuple(self.feature_names):
            raise ValueError("feature names must use canonical sorted order")
        if not isinstance(self.config, LinearConfig):
            raise ValueError("LinearConfig required")
        object.__setattr__(self, "feature_names", names)
        for key in ("center", "scale", "weights"):
            value = _array(getattr(self, key), key, (len(names),))
            if key == "scale" and (value <= 0).any():
                raise ValueError("feature scales must be positive")
            value.setflags(write=False)
            object.__setattr__(self, key, value)
        if not isinstance(self.training_metadata, dict):
            raise ValueError("training metadata must be a JSON object")
        object.__setattr__(self, "training_metadata",
                           json.loads(json.dumps(self.training_metadata, allow_nan=False)))

    @classmethod
    def fit(cls, rows, kind, *, feature_names=None, alpha=1.):
        if kind not in {"paired_direct", "residual"}:
            raise ValueError("linear comparison requires a paired target")
        names, config = _feature_names(feature_names, kind), LinearConfig(alpha)
        if not rows:
            raise ValueError("nonempty training rows required")
        groups, baselines, vectors = [], {}, []
        for index, row in enumerate(rows):
            if row.get("split", "train") != "train":
                raise ValueError("only training rows may enter fit")
            group = row.get("source_group")
            if not isinstance(group, str) or not group or type(row.get("is_baseline")) is not bool:
                raise ValueError("source group and boolean baseline flag required")
            if row["is_baseline"]:
                if group in baselines:
                    raise ValueError("exactly one baseline per group required")
                baselines[group] = index
            groups.append(group)
            vectors.append(_feature_vector(row.get("features"), names))
        if set(groups) != set(baselines):
            raise ValueError("exactly one baseline per group required")
        x = np.stack(vectors)
        reference = x[[baselines[group] for group in groups]]
        delta = np.asarray([_number(row.get("delta_mean"), "delta_mean") for row in rows])
        if any(delta[index] != 0. for index in baselines.values()):
            raise ValueError("baseline paired target must be zero")
        target = delta.copy()
        if kind == "residual":
            timed = np.asarray([_number(row.get("timed_delta"), "timed_delta") for row in rows])
            column = names.index("timed_analytic_absolute")
            if not np.allclose(timed, x[:, column] - reference[:, column], rtol=1e-10, atol=1e-9):
                raise ValueError("timed delta must match paired observable features")
            if any(timed[index] != 0. for index in baselines.values()):
                raise ValueError("baseline analytic delta must be zero")
            target -= timed
        center, scale = x.mean(axis=0), x.std(axis=0)
        scale[scale < 1e-9] = 1.
        differences = (x - reference) / scale
        if not all(np.isfinite(v).all() for v in (center, scale, differences, target)):
            raise ValueError("nonfinite training normalization or target")
        gram = differences.T @ differences / len(rows)
        rhs = differences.T @ target / len(rows)
        weights = np.linalg.solve(gram + config.alpha * np.eye(len(names)), rhs)
        mse = float(np.mean((differences @ weights - target) ** 2))
        fingerprint = {"groups": groups, "baselines": baselines, "names": names,
                       "features": x.tolist(), "target": target.tolist()}
        metadata = {"optimizer": "closed_form_positive_ridge", "parameter_count": len(names),
            "normalization": "same training-row mean/std and constant-column threshold as role MLP",
            "prediction_in_loss": "w dot (normalized_candidate - normalized_group_reference)",
            "target": "delta_mean" if kind == "paired_direct" else "delta_mean_minus_timed_delta",
            "objective": "mean_squared_paired_error + alpha * sum(weights**2)",
            "alpha": config.alpha, "intercept": "cancels in paired difference; fixed zero",
            "row_count": len(rows), "source_groups": sorted(baselines),
            "source_group_count": len(baselines), "training_data_sha256":
                sha256(json.dumps(fingerprint, sort_keys=True, allow_nan=False).encode()).hexdigest(),
            "data_mse": mse, "objective_value": mse + config.alpha * float(weights @ weights),
            "validation_or_test_access": False, "hyperparameter_selection": False, "seed": None}
        return cls(kind, names, center, scale, weights, config, metadata)

    def score_features(self, features, reference):
        value = _feature_vector(features, self.feature_names)
        base = _feature_vector(reference, self.feature_names)
        score = float(((value - base) / self.scale) @ self.weights)
        if self.kind == "residual":
            column = self.feature_names.index("timed_analytic_absolute")
            score += value[column] - base[column]
        if not np.isfinite(score):
            raise ValueError("nonfinite linear score")
        return float(score)

    def to_dict(self):
        return {"schema": "ics_v3_paired_linear_v1", "architecture": "paired_linear_no_intercept",
            "kind": self.kind, "feature_names": list(self.feature_names), "center": self.center.tolist(),
            "scale": self.scale.tolist(), "weights": self.weights.tolist(), "config": asdict(self.config),
            "training_metadata": deepcopy(self.training_metadata)}

    @classmethod
    def from_dict(cls, value):
        expected = {"schema", "architecture", "kind", "feature_names", "center", "scale", "weights",
                    "config", "training_metadata"}
        if (not isinstance(value, dict) or set(value) != expected or value["schema"] != "ics_v3_paired_linear_v1"
                or value["architecture"] != "paired_linear_no_intercept"
                or set(value["config"]) != {"alpha", "seed"}):
            raise ValueError("invalid paired linear serialization")
        return cls(value["kind"], tuple(value["feature_names"]), value["center"], value["scale"], value["weights"],
                   LinearConfig(**value["config"]), value["training_metadata"])
