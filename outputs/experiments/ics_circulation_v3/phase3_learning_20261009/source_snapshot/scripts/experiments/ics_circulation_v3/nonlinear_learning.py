"""Small, explicitly scoped NumPy value models for the frozen V3 protocol.

The only architecture is one 32-unit tanh hidden layer. Direct and residual
models have identical capacity for the same selected input features. Direct
training fits full cost; residual training fits *paired* f(x)-f(x0), not f(x)
alone. Both return action differences, giving the reference exactly zero.

There is no validation, test, early stopping, hyperparameter search, simulator,
or future access here. Callers choose a configuration using their separate
validation protocol. ``fit`` uses only the rows it receives and rejects rows
explicitly marked as any split other than "train". All optimizer steps are
deterministic full-batch Adam, using a local NumPy random generator.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from numbers import Real

import numpy as np


FULL_FEATURE_NAMES = tuple(sorted((
    "remaining_route_ticks", "usable_ticks", "edge_ticks", "edge_count",
    "destination_supply_before_10", "forecast_count", "old_in_transit_count",
    "module_hold_ticks", "analytic_absolute", "forecast_conflict_delay",
    "forecast_tardiness", "forecast_edge_overlaps", "forecast_unmatched",
    "timed_analytic_absolute", "source_empty_stock", "destination_empty_stock",
    "total_tray_count", "known_waiting_count", "old_remaining_ticks",
    "candidate_deadline_margin", "candidate_first_departure", "forecast_earliest_ticks",
    "forecast_destination_count",
)))
HIDDEN_WIDTH = 32
_PARAMETERS = ("w1", "b1", "w2", "b2")
_SCHEMA = "ics_v3_numpy_mlp_value_v1"


def _number(value, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def _array(value, name: str, shape: tuple[int, ...]) -> np.ndarray:
    try:
        raw = np.asarray(value)
        if raw.dtype.kind not in "fiu":
            raise ValueError(f"{name} must be numeric")
        result = np.array(raw, dtype=np.float64, copy=True)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"Invalid numeric array {name}") from exc
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f"{name} must have shape {shape} and finite values")
    return result


@dataclass(frozen=True)
class MLPConfig:
    """Fixed-budget optimizer settings; no data-dependent epoch selection."""

    epochs: int = 400
    learning_rate: float = .01
    l2: float = 1e-4
    seed: int = 0
    beta1: float = .9
    beta2: float = .999
    epsilon: float = 1e-8

    def __post_init__(self):
        if type(self.epochs) is not int or self.epochs <= 0:
            raise ValueError("epochs must be a positive integer")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        for name in ("learning_rate", "l2", "beta1", "beta2", "epsilon"):
            object.__setattr__(self, name, _number(getattr(self, name), name))
        if self.learning_rate <= 0 or self.epsilon <= 0 or self.l2 < 0:
            raise ValueError("learning_rate/epsilon must be positive and l2 nonnegative")
        if not (0 <= self.beta1 < 1 and 0 <= self.beta2 < 1):
            raise ValueError("Adam beta values must lie in [0, 1)")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping) -> "MLPConfig":
        if not isinstance(value, Mapping) or set(value) != set(cls.__dataclass_fields__):
            raise ValueError("Invalid optimizer configuration schema")
        try:
            return cls(**dict(value))
        except TypeError as exc:
            raise ValueError("Invalid optimizer configuration") from exc


def _feature_names(value: Sequence[str] | None, kind: str) -> tuple[str, ...]:
    if kind not in {"direct", "residual"}:
        raise ValueError("Model kind must be direct or residual")
    if value is None:
        names = FULL_FEATURE_NAMES
    else:
        if isinstance(value, (str, bytes)):
            raise ValueError("feature_names must be an explicit sequence")
        names = tuple(value)
        if not names or any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
            raise ValueError("Feature subset must be nonempty and unique")
        if not set(names) <= set(FULL_FEATURE_NAMES):
            raise ValueError("Feature subset contains unknown features")
        names = tuple(sorted(names))
    if kind == "residual" and "timed_analytic_absolute" not in names:
        raise ValueError("Residual models require timed_analytic_absolute in their feature subset")
    return names


def _feature_vector(features: Mapping, names: tuple[str, ...]) -> np.ndarray:
    # Explicit ablations accept either the selected schema or the full upstream
    # schema. Removed values are never read, validated, normalized, or scored.
    if not isinstance(features, Mapping) or set(features) not in (set(names), set(FULL_FEATURE_NAMES)):
        raise ValueError("Feature schema mismatch")
    return np.array([_number(features[name], f"feature {name}") for name in names], dtype=np.float64)


def _forward(parameters: Mapping[str, np.ndarray], x: np.ndarray):
    hidden = np.tanh(x @ parameters["w1"] + parameters["b1"])
    return hidden @ parameters["w2"] + parameters["b2"][0], hidden


def _objective_and_gradients(parameters: Mapping[str, np.ndarray], x: np.ndarray,
                             y: np.ndarray, reference_x: np.ndarray | None = None,
                             *, l2: float = 0.) -> tuple[float, dict[str, np.ndarray], float]:
    """Exact MSE + 0.5*l2*(||w1||^2+||w2||^2) used by ``fit``.

    ``reference_x=None`` means direct full-cost training. Otherwise the loss
    prediction is f(x)-f(reference_x) and both forward paths are differentiated.
    This intentionally exposed private helper supports finite-difference audits.
    """
    prediction, hidden = _forward(parameters, x)
    if reference_x is not None:
        reference_prediction, reference_hidden = _forward(parameters, reference_x)
        prediction = prediction - reference_prediction
    error = prediction - y
    data_mse = float(np.mean(error * error))
    upstream = 2. * error / len(y)
    hidden_upstream = upstream[:, None] * parameters["w2"] * (1. - hidden * hidden)
    gradients = {"w1": x.T @ hidden_upstream, "b1": hidden_upstream.sum(axis=0),
                 "w2": hidden.T @ upstream, "b2": np.array([upstream.sum()])}
    if reference_x is not None:
        reference_upstream = upstream[:, None] * parameters["w2"] * (1. - reference_hidden * reference_hidden)
        gradients["w1"] -= reference_x.T @ reference_upstream
        gradients["b1"] -= reference_upstream.sum(axis=0)
        gradients["w2"] -= reference_hidden.T @ upstream
        # The shared output bias cancels algebraically, including its gradient.
        gradients["b2"][:] = 0.
    penalty = .5 * l2 * (np.sum(parameters["w1"] ** 2) + np.sum(parameters["w2"] ** 2))
    gradients["w1"] += l2 * parameters["w1"]
    gradients["w2"] += l2 * parameters["w2"]
    objective = float(data_mse + penalty)
    if not np.isfinite(objective) or any(not np.isfinite(value).all() for value in gradients.values()):
        raise ValueError("Nonfinite training objective or gradient")
    return objective, gradients, data_mse


@dataclass(frozen=True)
class MLPValueModel:
    kind: str
    feature_names: tuple[str, ...]
    center: np.ndarray
    scale: np.ndarray
    parameters: dict[str, np.ndarray]
    config: MLPConfig
    training_metadata: dict

    def __post_init__(self):
        names = _feature_names(self.feature_names, self.kind)
        if tuple(self.feature_names) != names:
            raise ValueError("Serialized feature_names must be in canonical sorted order")
        object.__setattr__(self, "feature_names", names)
        size = len(names)
        center, scale = _array(self.center, "center", (size,)), _array(self.scale, "scale", (size,))
        if (scale <= 0).any():
            raise ValueError("Feature scales must be positive")
        if not isinstance(self.parameters, Mapping) or set(self.parameters) != set(_PARAMETERS):
            raise ValueError("Invalid parameter schema")
        shapes = {"w1": (size, HIDDEN_WIDTH), "b1": (HIDDEN_WIDTH,), "w2": (HIDDEN_WIDTH,), "b2": (1,)}
        parameters = {name: _array(self.parameters[name], name, shapes[name]) for name in _PARAMETERS}
        if not isinstance(self.config, MLPConfig):
            raise ValueError("config must be MLPConfig")
        if not isinstance(self.training_metadata, dict):
            raise ValueError("training_metadata must be a JSON object")
        try:
            metadata = json.loads(json.dumps(self.training_metadata, allow_nan=False))
        except (ValueError, TypeError) as exc:
            raise ValueError("training_metadata must contain finite JSON values") from exc
        for value in (center, scale, *parameters.values()):
            value.setflags(write=False)
        object.__setattr__(self, "center", center)
        object.__setattr__(self, "scale", scale)
        object.__setattr__(self, "parameters", parameters)
        object.__setattr__(self, "training_metadata", metadata)

    @property
    def hidden_width(self) -> int:
        return HIDDEN_WIDTH

    @property
    def parameter_count(self) -> int:
        return sum(value.size for value in self.parameters.values())

    @classmethod
    def fit(cls, rows: Sequence[dict], kind: str, config: MLPConfig | None = None, *,
            feature_names: Sequence[str] | None = None) -> "MLPValueModel":
        config = config if config is not None else MLPConfig()
        if not isinstance(config, MLPConfig):
            raise ValueError("config must be MLPConfig")
        names = _feature_names(feature_names, kind)
        if not rows:
            raise ValueError("Need nonempty training rows")
        baselines, groups, vectors = {}, [], []
        for row in rows:
            if not isinstance(row, Mapping) or row.get("split", "train") != "train":
                raise ValueError("Only training rows may be passed to fit")
            group = row.get("source_group")
            if not isinstance(group, str) or not group or type(row.get("is_baseline")) is not bool:
                raise ValueError("Rows need a source_group and boolean is_baseline")
            groups.append(group)
            vectors.append(_feature_vector(row.get("features"), names))
            if row["is_baseline"]:
                if group in baselines:
                    raise ValueError("Every training group needs exactly one baseline")
                baselines[group] = len(vectors) - 1
        if set(baselines) != set(groups):
            raise ValueError("Every training group needs exactly one baseline")
        x = np.stack(vectors)
        reference_x = x[[baselines[group] for group in groups]]
        if kind == "direct":
            y = np.array([_number(row.get("cost_mean"), "cost_mean") for row in rows])
        else:
            delta = np.array([_number(row.get("delta_mean"), "delta_mean") for row in rows])
            timed = np.array([_number(row.get("timed_delta"), "timed_delta") for row in rows])
            timed_index = names.index("timed_analytic_absolute")
            if not np.allclose(timed, x[:, timed_index] - reference_x[:, timed_index], rtol=1e-10, atol=1e-9):
                raise ValueError("timed_delta must match the paired timed_analytic_absolute features")
            if any(delta[index] != 0. or timed[index] != 0. for index in baselines.values()):
                raise ValueError("Baseline paired deltas must equal zero")
            y = delta - timed
        # No caller-owned arrays or rows are mutated. Statistics come only from
        # selected features of these training rows, never from reference/test IO.
        with np.errstate(over="ignore", invalid="ignore"):
            center, scale = x.mean(axis=0), x.std(axis=0)
        if not np.isfinite(center).all() or not np.isfinite(scale).all() or not np.isfinite(y).all():
            raise ValueError("Nonfinite training normalization or targets")
        scale[scale < 1e-9] = 1.
        normalized = (x - center) / scale
        normalized_reference = (reference_x - center) / scale if kind == "residual" else None
        rng = np.random.default_rng(config.seed)
        parameters = {
            "w1": rng.normal(0., np.sqrt(2. / (len(names) + HIDDEN_WIDTH)), (len(names), HIDDEN_WIDTH)),
            "b1": np.zeros(HIDDEN_WIDTH),
            "w2": rng.normal(0., np.sqrt(2. / (HIDDEN_WIDTH + 1)), HIDDEN_WIDTH),
            "b2": np.array([float(y.mean()) if kind == "direct" else 0.]),
        }
        first = {name: np.zeros_like(value) for name, value in parameters.items()}
        second = {name: np.zeros_like(value) for name, value in parameters.items()}
        history = []
        initial_objective, _, initial_mse = _objective_and_gradients(
            parameters, normalized, y, normalized_reference, l2=config.l2)
        history.append({"epoch": 0, "objective": initial_objective, "data_mse": initial_mse})
        for step in range(1, config.epochs + 1):
            _, gradients, _ = _objective_and_gradients(parameters, normalized, y, normalized_reference, l2=config.l2)
            for name in _PARAMETERS:
                first[name] = config.beta1 * first[name] + (1. - config.beta1) * gradients[name]
                second[name] = config.beta2 * second[name] + (1. - config.beta2) * gradients[name] ** 2
                m = first[name] / (1. - config.beta1 ** step)
                v = second[name] / (1. - config.beta2 ** step)
                parameters[name] -= config.learning_rate * m / (np.sqrt(v) + config.epsilon)
            if step == config.epochs or step % max(1, config.epochs // 10) == 0:
                objective, _, mse = _objective_and_gradients(parameters, normalized, y, normalized_reference, l2=config.l2)
                history.append({"epoch": step, "objective": objective, "data_mse": mse})
        fingerprint = json.dumps({"groups": groups, "baseline_indices": baselines,
                                  "feature_names": names, "x": x.tolist(), "y": y.tolist()},
                                 sort_keys=True, separators=(",", ":"), allow_nan=False)
        metadata = {
            "optimizer": "full_batch_adam", "activation": "tanh", "hidden_width": HIDDEN_WIDTH,
            "parameter_count": (len(names) + 2) * HIDDEN_WIDTH + 1,
            "target": "cost_mean" if kind == "direct" else "delta_mean_minus_timed_delta",
            "prediction_in_loss": "f(x)" if kind == "direct" else "f(x)-f(group_baseline)",
            "objective": "mean_squared_error + 0.5*l2*(sum(w1**2)+sum(w2**2)); biases unpenalized",
            "row_count": len(rows), "source_group_count": len(baselines), "source_groups": sorted(baselines),
            "normalization": "training_rows_selected_features_only", "feature_names": list(names),
            "removed_feature_names": sorted(set(FULL_FEATURE_NAMES) - set(names)),
            "seed": config.seed, "epochs_completed": config.epochs, "config": config.to_dict(),
            "training_data_sha256": sha256(fingerprint.encode()).hexdigest(),
            "initial_objective": initial_objective, "initial_data_mse": initial_mse,
            "final_objective": history[-1]["objective"], "final_data_mse": history[-1]["data_mse"],
            "history": history, "early_stopping": False, "validation_or_test_access": False,
        }
        return cls(kind, names, center, scale, parameters, config, metadata)

    def predict_value(self, features: Mapping[str, float]) -> float:
        x = _feature_vector(features, self.feature_names)
        with np.errstate(over="ignore", invalid="ignore"):
            normalized = (x - self.center) / self.scale
            value = _forward(self.parameters, normalized[None, :])[0][0]
        if not np.isfinite(normalized).all() or not np.isfinite(value):
            raise ValueError("Nonfinite runtime prediction")
        return float(value)

    def score_features(self, features: Mapping[str, float], reference: Mapping[str, float]) -> float:
        delta = self.predict_value(features) - self.predict_value(reference)
        if self.kind == "residual":
            delta += features["timed_analytic_absolute"] - reference["timed_analytic_absolute"]
        if not np.isfinite(delta):
            raise ValueError("Nonfinite runtime score")
        return float(delta)

    def to_dict(self) -> dict:
        return {"schema": _SCHEMA, "architecture": {"hidden_width": HIDDEN_WIDTH, "activation": "tanh"},
                "kind": self.kind, "feature_names": list(self.feature_names),
                "center": self.center.tolist(), "scale": self.scale.tolist(),
                "parameters": {name: value.tolist() for name, value in self.parameters.items()},
                "config": self.config.to_dict(), "training_metadata": deepcopy(self.training_metadata)}

    @classmethod
    def from_dict(cls, value: Mapping) -> "MLPValueModel":
        expected = {"schema", "architecture", "kind", "feature_names", "center", "scale",
                    "parameters", "config", "training_metadata"}
        if not isinstance(value, Mapping) or set(value) != expected or value["schema"] != _SCHEMA:
            raise ValueError("Invalid serialized model schema")
        if value["architecture"] != {"hidden_width": HIDDEN_WIDTH, "activation": "tanh"}:
            raise ValueError("Only a 32-unit tanh hidden layer is supported")
        return cls(value["kind"], tuple(value["feature_names"]), value["center"], value["scale"],
                   value["parameters"], MLPConfig.from_dict(value["config"]), value["training_metadata"])
