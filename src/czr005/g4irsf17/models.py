"""Small deterministic NumPy rankers for G4IRSF17 Phase D."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .features import assert_strictly_local_feature_names


def _finite_matrix(values: Any, name: str) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError(f"{name}_MUST_BE_NONEMPTY_2D")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name}_NOT_FINITE")
    return matrix


def _sigmoid(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, -40.0, 40.0)
    return 1.0 / (1.0 + np.exp(-clipped))


@dataclass(frozen=True)
class PairwiseLinearRanker:
    """Linear/logistic preference model over candidate deltas and context."""

    feature_names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray
    bias: float
    objective: str = "logistic"

    @classmethod
    def fit(
        cls,
        pairwise_features: Any,
        preferences: Any,
        *,
        feature_names: Sequence[str],
        objective: str = "logistic",
        l2: float = 1e-3,
        epochs: int = 500,
        learning_rate: float = 0.05,
    ) -> "PairwiseLinearRanker":
        matrix = _finite_matrix(pairwise_features, "PAIRWISE_FEATURES")
        names = tuple(feature_names)
        if len(names) != matrix.shape[1]:
            raise ValueError("FEATURE_NAME_DIMENSION_MISMATCH")
        assert_strictly_local_feature_names(names)
        labels = np.asarray(preferences, dtype=np.float64)
        if labels.shape != (matrix.shape[0],) or not np.all(np.isfinite(labels)):
            raise ValueError("PREFERENCES_MUST_BE_FINITE_VECTOR")
        if objective not in {"logistic", "linear"}:
            raise ValueError("UNKNOWN_PAIRWISE_OBJECTIVE")
        if l2 < 0.0:
            raise ValueError("L2_MUST_BE_NONNEGATIVE")
        mean = np.mean(matrix, axis=0)
        scale = np.std(matrix, axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
        normalized = (matrix - mean) / scale

        if objective == "linear":
            targets = np.where(labels > 0.5, 1.0, -1.0)
            design = np.column_stack([np.ones(matrix.shape[0]), normalized])
            regularizer = np.eye(design.shape[1]) * l2
            regularizer[0, 0] = 0.0
            solved = np.linalg.solve(design.T @ design + regularizer, design.T @ targets)
            bias = float(solved[0])
            weights = solved[1:]
        else:
            if not np.all((labels == 0.0) | (labels == 1.0)):
                raise ValueError("LOGISTIC_PREFERENCES_MUST_BE_BINARY")
            if epochs <= 0 or learning_rate <= 0.0:
                raise ValueError("OPTIMIZER_PARAMETERS_MUST_BE_POSITIVE")
            weights = np.zeros(matrix.shape[1], dtype=np.float64)
            bias = 0.0
            for _ in range(epochs):
                probabilities = _sigmoid(normalized @ weights + bias)
                residual = probabilities - labels
                gradient = normalized.T @ residual / matrix.shape[0] + l2 * weights
                bias_gradient = float(np.mean(residual))
                weights -= learning_rate * gradient
                bias -= learning_rate * bias_gradient
        return cls(names, mean, scale, np.asarray(weights), float(bias), objective)

    def decision_function(self, pairwise_features: Any) -> np.ndarray:
        matrix = np.asarray(pairwise_features, dtype=np.float64)
        one_row = matrix.ndim == 1
        if one_row:
            matrix = matrix[None, :]
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError("PAIRWISE_FEATURE_DIMENSION_MISMATCH")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("PAIRWISE_FEATURES_NOT_FINITE")
        result = ((matrix - self.mean) / self.scale) @ self.weights + self.bias
        return result[0] if one_row else result

    def predict_proba(self, pairwise_features: Any) -> np.ndarray:
        margins = np.asarray(self.decision_function(pairwise_features))
        return _sigmoid(margins)

    def choose_against_baseline(
        self,
        pairwise_against_baseline: Any,
        baseline_index: int,
        *,
        legal_mask: Sequence[bool] | None = None,
    ) -> int:
        """Choose the largest predicted advantage over the current baseline."""

        matrix = np.asarray(pairwise_against_baseline, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError("PAIRWISE_FEATURE_DIMENSION_MISMATCH")
        count = matrix.shape[0]
        if baseline_index < 0 or baseline_index >= count:
            raise ValueError("BASELINE_INDEX_OUT_OF_RANGE")
        legal = np.ones(count, dtype=bool) if legal_mask is None else np.asarray(legal_mask, dtype=bool)
        if legal.shape != (count,) or not np.any(legal):
            raise ValueError("LEGAL_MASK_INVALID")
        margins = np.asarray(self.decision_function(matrix), dtype=np.float64)
        margins[~legal] = -np.inf
        margins[baseline_index] = 0.0 if legal[baseline_index] else -np.inf
        return int(np.argmax(margins))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "pairwise_linear_logistic",
            "objective": self.objective,
            "feature_names": list(self.feature_names),
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "weights": self.weights.tolist(),
            "bias": self.bias,
            "identity_features_used": False,
        }


@dataclass(frozen=True)
class TinyMLPListwiseRanker:
    """One-hidden-layer listwise ranker with a fixed K=2 or K=4 mask."""

    feature_names: tuple[str, ...]
    top_k: int
    mean: np.ndarray
    scale: np.ndarray
    input_weights: np.ndarray
    hidden_bias: np.ndarray
    output_weights: np.ndarray
    output_bias: float

    @classmethod
    def fit(
        cls,
        candidate_features: Any,
        target_indices: Any,
        *,
        feature_names: Sequence[str],
        legal_masks: Any | None = None,
        hidden_dim: int = 8,
        epochs: int = 600,
        learning_rate: float = 0.03,
        l2: float = 1e-4,
        seed: int = 17,
    ) -> "TinyMLPListwiseRanker":
        features = np.asarray(candidate_features, dtype=np.float64)
        if features.ndim != 3 or features.shape[0] == 0:
            raise ValueError("LISTWISE_FEATURES_MUST_BE_NONEMPTY_3D")
        example_count, top_k, feature_count = features.shape
        if top_k not in {2, 4}:
            raise ValueError("TOP_K_MUST_BE_2_OR_4")
        names = tuple(feature_names)
        if len(names) != feature_count:
            raise ValueError("FEATURE_NAME_DIMENSION_MISMATCH")
        assert_strictly_local_feature_names(names)
        masks = (
            np.ones((example_count, top_k), dtype=bool)
            if legal_masks is None
            else np.asarray(legal_masks, dtype=bool)
        )
        if masks.shape != (example_count, top_k) or np.any(np.sum(masks, axis=1) == 0):
            raise ValueError("LEGAL_MASK_INVALID")
        if not np.all(np.isfinite(features[masks])):
            raise ValueError("LISTWISE_FEATURES_NOT_FINITE")
        targets = np.asarray(target_indices, dtype=np.int64)
        if targets.shape != (example_count,):
            raise ValueError("TARGET_INDEX_DIMENSION_MISMATCH")
        if any(target < 0 or target >= top_k or not masks[index, target] for index, target in enumerate(targets)):
            raise ValueError("TARGET_INDEX_NOT_LEGAL")
        if hidden_dim <= 0 or hidden_dim > 32:
            raise ValueError("HIDDEN_DIM_MUST_BE_IN_1_TO_32")
        if epochs <= 0 or learning_rate <= 0.0 or l2 < 0.0:
            raise ValueError("OPTIMIZER_PARAMETERS_INVALID")

        observed = features[masks]
        mean = np.mean(observed, axis=0)
        scale = np.std(observed, axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
        normalized = (features - mean) / scale
        # Padded illegal slots may be NaN in an offline tensor.  They are
        # never scored or differentiated, so give them a finite neutral input.
        normalized = np.where(masks[:, :, None], normalized, 0.0)
        rng = np.random.default_rng(int(seed))
        input_weights = rng.normal(0.0, 0.08, size=(feature_count, hidden_dim))
        hidden_bias = np.zeros(hidden_dim, dtype=np.float64)
        output_weights = rng.normal(0.0, 0.08, size=hidden_dim)
        output_bias = 0.0

        for _ in range(epochs):
            grad_input = np.zeros_like(input_weights)
            grad_hidden_bias = np.zeros_like(hidden_bias)
            grad_output = np.zeros_like(output_weights)
            grad_output_bias = 0.0
            for index in range(example_count):
                # These tensors are deliberately tiny (K is 2 or 4).  Using
                # explicit reductions avoids paying a BLAS dispatch cost and
                # also keeps training reliable on Windows installations where
                # a delay-loaded BLAS DLL is unavailable to worker processes.
                hidden = np.tanh(
                    np.sum(
                        normalized[index, :, :, None]
                        * input_weights[None, :, :],
                        axis=1,
                    )
                    + hidden_bias
                )
                scores = (
                    np.sum(hidden * output_weights[None, :], axis=1)
                    + output_bias
                )
                scores = np.where(masks[index], scores, -np.inf)
                maximum = float(np.max(scores[masks[index]]))
                exponent = np.where(masks[index], np.exp(scores - maximum), 0.0)
                probabilities = exponent / np.sum(exponent)
                score_gradient = probabilities
                score_gradient[targets[index]] -= 1.0
                grad_output += np.sum(
                    hidden * score_gradient[:, None], axis=0
                )
                grad_output_bias += float(np.sum(score_gradient))
                hidden_gradient = score_gradient[:, None] * output_weights[None, :]
                preactivation_gradient = hidden_gradient * (1.0 - hidden * hidden)
                grad_input += np.sum(
                    normalized[index, :, :, None]
                    * preactivation_gradient[:, None, :],
                    axis=0,
                )
                grad_hidden_bias += np.sum(preactivation_gradient, axis=0)
            inverse = 1.0 / example_count
            grad_input = grad_input * inverse + l2 * input_weights
            grad_hidden_bias *= inverse
            grad_output = grad_output * inverse + l2 * output_weights
            grad_output_bias *= inverse
            input_weights -= learning_rate * grad_input
            hidden_bias -= learning_rate * grad_hidden_bias
            output_weights -= learning_rate * grad_output
            output_bias -= learning_rate * grad_output_bias

        return cls(
            names,
            top_k,
            mean,
            scale,
            input_weights,
            hidden_bias,
            output_weights,
            float(output_bias),
        )

    def scores(self, candidate_features: Any, legal_mask: Sequence[bool] | None = None) -> np.ndarray:
        features = np.asarray(candidate_features, dtype=np.float64)
        if features.shape != (self.top_k, len(self.feature_names)):
            raise ValueError("LISTWISE_INFERENCE_DIMENSION_MISMATCH")
        mask = np.ones(self.top_k, dtype=bool) if legal_mask is None else np.asarray(legal_mask, dtype=bool)
        if mask.shape != (self.top_k,) or not np.any(mask):
            raise ValueError("LEGAL_MASK_INVALID")
        if not np.all(np.isfinite(features[mask])):
            raise ValueError("LISTWISE_FEATURES_NOT_FINITE")
        normalized = (features - self.mean) / self.scale
        normalized = np.where(mask[:, None], normalized, 0.0)
        hidden = np.tanh(
            np.sum(
                normalized[:, :, None] * self.input_weights[None, :, :],
                axis=1,
            )
            + self.hidden_bias
        )
        scores = (
            np.sum(hidden * self.output_weights[None, :], axis=1)
            + self.output_bias
        )
        return np.where(mask, scores, -np.inf)

    def choose(self, candidate_features: Any, legal_mask: Sequence[bool] | None = None) -> int:
        return int(np.argmax(self.scores(candidate_features, legal_mask)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "tiny_mlp_listwise",
            "top_k": self.top_k,
            "hidden_dim": int(self.output_weights.shape[0]),
            "feature_names": list(self.feature_names),
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "input_weights": self.input_weights.tolist(),
            "hidden_bias": self.hidden_bias.tolist(),
            "output_weights": self.output_weights.tolist(),
            "output_bias": self.output_bias,
            "identity_features_used": False,
        }
