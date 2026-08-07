"""Small deterministic candidate scorers for the G18 rich-local controller.

The models consume only an already-validated local feature matrix.  Complete
rollout outcomes are training targets, never inference inputs.  Pairwise J3
reuses the G17 ranker; the remaining models are tiny NumPy regressors intended
for transparent experiments and later native parity work.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from ..g4irsf17.models import PairwiseLinearRanker
from .features import assert_deployable_g18_feature_names


def _finite_feature_matrix(
    values: Any,
    feature_names: Sequence[str],
    *,
    name: str = "CANDIDATE_FEATURES",
) -> np.ndarray:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0:
        raise ValueError(f"{name}_MUST_BE_NONEMPTY_2D")
    if matrix.shape[1] != len(feature_names):
        raise ValueError(f"{name}_DIMENSION_MISMATCH")
    if not np.all(np.isfinite(matrix)):
        raise ValueError(f"{name}_NOT_FINITE")
    return matrix


def _finite_targets(values: Any, row_count: int, *, name: str) -> np.ndarray:
    targets = np.asarray(values, dtype=np.float64)
    if targets.shape != (row_count,):
        raise ValueError(f"{name}_DIMENSION_MISMATCH")
    if not np.all(np.isfinite(targets)):
        raise ValueError(f"{name}_NOT_FINITE")
    return targets


def _legal_mask(mask: Sequence[bool] | None, count: int) -> np.ndarray:
    result = np.ones(count, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    if result.shape != (count,) or not np.any(result):
        raise ValueError("LEGAL_MASK_INVALID")
    return result


def _masked_scores(
    values: Any,
    legal_mask: Sequence[bool] | None,
    count: int,
) -> np.ndarray:
    scores = np.asarray(values, dtype=np.float64)
    mask = _legal_mask(legal_mask, count)
    if scores.shape != (count,) or not np.all(np.isfinite(scores[mask])):
        raise ValueError("BASELINE_SCORE_INVALID")
    return np.where(mask, scores, -np.inf)


def _candidate_matrix_with_mask(
    values: Any,
    feature_names: Sequence[str],
    legal_mask: Sequence[bool] | None,
) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.asarray(values, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] != len(feature_names):
        raise ValueError("CANDIDATE_FEATURES_DIMENSION_MISMATCH")
    mask = _legal_mask(legal_mask, matrix.shape[0])
    if not np.all(np.isfinite(matrix[mask])):
        raise ValueError("CANDIDATE_FEATURES_NOT_FINITE")
    # Padded illegal candidates never reach a model head.
    return np.where(mask[:, None], matrix, 0.0), mask


@dataclass(frozen=True)
class TinyMLPRegressor:
    """One-hidden-layer standardized utility regressor with deterministic fit."""

    feature_names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    input_weights: np.ndarray
    hidden_bias: np.ndarray
    output_weights: np.ndarray
    output_bias: float
    target_mean: float
    target_scale: float

    @classmethod
    def fit(
        cls,
        features: Any,
        targets: Any,
        *,
        feature_names: Sequence[str],
        hidden_dim: int = 12,
        epochs: int = 700,
        learning_rate: float = 0.025,
        l2: float = 1e-4,
        seed: int = 18,
    ) -> "TinyMLPRegressor":
        names = tuple(str(name) for name in feature_names)
        assert_deployable_g18_feature_names(names)
        matrix = _finite_feature_matrix(features, names)
        target = _finite_targets(targets, matrix.shape[0], name="UTILITY_TARGET")
        if hidden_dim <= 0 or hidden_dim > 32:
            raise ValueError("HIDDEN_DIM_MUST_BE_IN_1_TO_32")
        if epochs <= 0 or learning_rate <= 0.0 or l2 < 0.0:
            raise ValueError("OPTIMIZER_PARAMETERS_INVALID")

        mean = np.mean(matrix, axis=0)
        scale = np.std(matrix, axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
        normalized = (matrix - mean) / scale
        target_mean = float(np.mean(target))
        target_scale = float(np.std(target))
        if target_scale <= 1e-12:
            target_scale = 1.0
        normalized_target = (target - target_mean) / target_scale

        rng = np.random.default_rng(int(seed))
        input_weights = rng.normal(0.0, 0.08, size=(matrix.shape[1], hidden_dim))
        hidden_bias = np.zeros(hidden_dim, dtype=np.float64)
        output_weights = rng.normal(0.0, 0.08, size=hidden_dim)
        output_bias = 0.0

        inverse_count = 1.0 / matrix.shape[0]
        for _ in range(epochs):
            hidden = np.tanh(normalized @ input_weights + hidden_bias)
            prediction = hidden @ output_weights + output_bias
            residual = prediction - normalized_target
            grad_output = hidden.T @ residual * inverse_count + l2 * output_weights
            grad_output_bias = float(np.mean(residual))
            hidden_gradient = residual[:, None] * output_weights[None, :]
            preactivation_gradient = hidden_gradient * (1.0 - hidden * hidden)
            grad_input = normalized.T @ preactivation_gradient * inverse_count + l2 * input_weights
            grad_hidden_bias = np.mean(preactivation_gradient, axis=0)
            input_weights -= learning_rate * grad_input
            hidden_bias -= learning_rate * grad_hidden_bias
            output_weights -= learning_rate * grad_output
            output_bias -= learning_rate * grad_output_bias

        return cls(
            names,
            mean,
            scale,
            input_weights,
            hidden_bias,
            output_weights,
            float(output_bias),
            target_mean,
            target_scale,
        )

    def predict(self, features: Any) -> np.ndarray | float:
        matrix = np.asarray(features, dtype=np.float64)
        one_row = matrix.ndim == 1
        if one_row:
            matrix = matrix[None, :]
        matrix = _finite_feature_matrix(matrix, self.feature_names)
        hidden = np.tanh((matrix - self.mean) / self.scale @ self.input_weights + self.hidden_bias)
        normalized = hidden @ self.output_weights + self.output_bias
        result = self.target_mean + self.target_scale * normalized
        return float(result[0]) if one_row else result

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "tiny_mlp_regressor",
            "feature_names": list(self.feature_names),
            "hidden_dim": int(self.output_weights.shape[0]),
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "input_weights": self.input_weights.tolist(),
            "hidden_bias": self.hidden_bias.tolist(),
            "output_weights": self.output_weights.tolist(),
            "output_bias": self.output_bias,
            "target_mean": self.target_mean,
            "target_scale": self.target_scale,
            "identity_features_used": False,
            "outcome_features_used": False,
        }


@dataclass(frozen=True)
class PairwiseResidualScorer:
    """J3: G17 pairwise ranker used as a residual over F2/J2 scores."""

    feature_names: tuple[str, ...]
    ranker: PairwiseLinearRanker
    residual_scale: float = 1.0

    @classmethod
    def fit(
        cls,
        candidate_sets: Sequence[Any],
        utility_sets: Sequence[Any],
        baseline_indices: Sequence[int],
        *,
        feature_names: Sequence[str],
        legal_masks: Sequence[Sequence[bool]] | None = None,
        residual_scale: float = 1.0,
        epochs: int = 600,
        learning_rate: float = 0.05,
        l2: float = 1e-3,
    ) -> "PairwiseResidualScorer":
        names = tuple(str(name) for name in feature_names)
        assert_deployable_g18_feature_names(names)
        if not math.isfinite(float(residual_scale)) or residual_scale <= 0.0:
            raise ValueError("RESIDUAL_SCALE_MUST_BE_POSITIVE")
        if not (
            len(candidate_sets) == len(utility_sets) == len(baseline_indices)
        ):
            raise ValueError("GROUPED_TRAINING_DIMENSION_MISMATCH")
        if legal_masks is not None and len(legal_masks) != len(candidate_sets):
            raise ValueError("GROUPED_LEGAL_MASK_DIMENSION_MISMATCH")

        pairwise: list[np.ndarray] = []
        labels: list[float] = []
        for group_index, (raw_features, raw_utility, raw_baseline) in enumerate(
            zip(candidate_sets, utility_sets, baseline_indices, strict=True)
        ):
            matrix = np.asarray(raw_features, dtype=np.float64)
            if matrix.ndim != 2 or matrix.shape[1] != len(names) or matrix.shape[0] < 2:
                raise ValueError("CANDIDATE_SET_DIMENSION_MISMATCH")
            mask = _legal_mask(
                None if legal_masks is None else legal_masks[group_index],
                matrix.shape[0],
            )
            if not np.all(np.isfinite(matrix[mask])):
                raise ValueError("CANDIDATE_SET_NOT_FINITE")
            utility = np.asarray(raw_utility, dtype=np.float64)
            if utility.shape != (matrix.shape[0],) or not np.all(np.isfinite(utility[mask])):
                raise ValueError("UTILITY_SET_INVALID")
            baseline = int(raw_baseline)
            if baseline < 0 or baseline >= matrix.shape[0] or not mask[baseline]:
                raise ValueError("BASELINE_INDEX_NOT_LEGAL")
            for candidate in np.flatnonzero(mask):
                if candidate == baseline:
                    continue
                advantage = float(utility[candidate] - utility[baseline])
                if abs(advantage) <= 1e-12:
                    continue
                delta = matrix[candidate] - matrix[baseline]
                preferred = 1.0 if advantage > 0.0 else 0.0
                pairwise.extend((delta, -delta))
                labels.extend((preferred, 1.0 - preferred))
        if not pairwise:
            raise ValueError("PAIRWISE_TRAINING_REQUIRES_NONTIED_ACTIONS")
        delta_names = tuple(f"delta_{name}" for name in names)
        ranker = PairwiseLinearRanker.fit(
            np.asarray(pairwise),
            np.asarray(labels),
            feature_names=delta_names,
            epochs=epochs,
            learning_rate=learning_rate,
            l2=l2,
        )
        return cls(names, ranker, float(residual_scale))

    def scores(
        self,
        candidate_features: Any,
        baseline_scores: Any,
        baseline_index: int,
        legal_mask: Sequence[bool] | None = None,
    ) -> np.ndarray:
        matrix = np.asarray(candidate_features, dtype=np.float64)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError("CANDIDATE_FEATURES_DIMENSION_MISMATCH")
        mask = _legal_mask(legal_mask, matrix.shape[0])
        if not np.all(np.isfinite(matrix[mask])):
            raise ValueError("CANDIDATE_FEATURES_NOT_FINITE")
        if baseline_index < 0 or baseline_index >= matrix.shape[0] or not mask[baseline_index]:
            raise ValueError("BASELINE_INDEX_NOT_LEGAL")
        base = _masked_scores(baseline_scores, mask, matrix.shape[0])
        finite_matrix = np.where(mask[:, None], matrix, matrix[baseline_index])
        deltas = finite_matrix - matrix[baseline_index]
        residual = np.asarray(self.ranker.decision_function(deltas), dtype=np.float64)
        residual[baseline_index] = 0.0
        return np.where(mask, base + self.residual_scale * residual, -np.inf)

    def choose(self, *args: Any, **kwargs: Any) -> int:
        return int(np.argmax(self.scores(*args, **kwargs)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "J3_pairwise_linear_residual",
            "feature_names": list(self.feature_names),
            "residual_scale": self.residual_scale,
            "ranker": self.ranker.to_dict(),
            "consumes_baseline_scores": True,
            "identity_features_used": False,
            "outcome_features_used": False,
        }


@dataclass(frozen=True)
class TinyResidualScorer:
    """J4: tiny nonlinear advantage model added to the local baseline score."""

    regressor: TinyMLPRegressor
    residual_scale: float = 1.0

    @classmethod
    def fit(
        cls,
        features: Any,
        advantages: Any,
        *,
        feature_names: Sequence[str],
        residual_scale: float = 1.0,
        **fit_kwargs: Any,
    ) -> "TinyResidualScorer":
        if not math.isfinite(float(residual_scale)) or residual_scale <= 0.0:
            raise ValueError("RESIDUAL_SCALE_MUST_BE_POSITIVE")
        model = TinyMLPRegressor.fit(
            features,
            advantages,
            feature_names=feature_names,
            **fit_kwargs,
        )
        return cls(model, float(residual_scale))

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.regressor.feature_names

    def scores(
        self,
        candidate_features: Any,
        baseline_scores: Any,
        legal_mask: Sequence[bool] | None = None,
    ) -> np.ndarray:
        matrix, mask = _candidate_matrix_with_mask(
            candidate_features,
            self.feature_names,
            legal_mask,
        )
        base = _masked_scores(baseline_scores, mask, matrix.shape[0])
        residual = np.asarray(self.regressor.predict(matrix), dtype=np.float64)
        return np.where(mask, base + self.residual_scale * residual, -np.inf)

    def choose(self, *args: Any, **kwargs: Any) -> int:
        return int(np.argmax(self.scores(*args, **kwargs)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "J4_tiny_mlp_residual",
            "residual_scale": self.residual_scale,
            "regressor": self.regressor.to_dict(),
            "consumes_baseline_scores": True,
            "identity_features_used": False,
            "outcome_features_used": False,
        }


@dataclass(frozen=True)
class StandaloneMLPScorer:
    """J5: rich-local utility scorer that does not read an F2 score."""

    regressor: TinyMLPRegressor

    @classmethod
    def fit(
        cls,
        features: Any,
        utilities: Any,
        *,
        feature_names: Sequence[str],
        **fit_kwargs: Any,
    ) -> "StandaloneMLPScorer":
        return cls(
            TinyMLPRegressor.fit(
                features,
                utilities,
                feature_names=feature_names,
                **fit_kwargs,
            )
        )

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.regressor.feature_names

    def scores(
        self,
        candidate_features: Any,
        legal_mask: Sequence[bool] | None = None,
    ) -> np.ndarray:
        matrix, mask = _candidate_matrix_with_mask(
            candidate_features,
            self.feature_names,
            legal_mask,
        )
        prediction = np.asarray(self.regressor.predict(matrix), dtype=np.float64)
        return np.where(mask, prediction, -np.inf)

    def choose(self, *args: Any, **kwargs: Any) -> int:
        return int(np.argmax(self.scores(*args, **kwargs)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "J5_standalone_rich_local_mlp",
            "regressor": self.regressor.to_dict(),
            "consumes_baseline_scores": False,
            "identity_features_used": False,
            "outcome_features_used": False,
        }


def _set_feature_names(feature_names: Sequence[str]) -> tuple[str, ...]:
    prefixes = ("self", "set_mean", "set_max", "delta_mean", "delta_max")
    return tuple(
        f"{prefix}__{name}"
        for prefix in prefixes
        for name in feature_names
    )


def _augment_candidate_set(
    candidate_features: Any,
    feature_names: Sequence[str],
    legal_mask: Sequence[bool] | None,
) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.asarray(candidate_features, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] != len(feature_names):
        raise ValueError("CANDIDATE_SET_DIMENSION_MISMATCH")
    mask = _legal_mask(legal_mask, matrix.shape[0])
    if not np.all(np.isfinite(matrix[mask])):
        raise ValueError("CANDIDATE_SET_NOT_FINITE")
    observed = matrix[mask]
    mean = np.mean(observed, axis=0)
    maximum = np.max(observed, axis=0)
    augmented = np.zeros((matrix.shape[0], matrix.shape[1] * 5), dtype=np.float64)
    augmented[mask] = np.concatenate(
        (
            observed,
            np.broadcast_to(mean, observed.shape),
            np.broadcast_to(maximum, observed.shape),
            observed - mean,
            observed - maximum,
        ),
        axis=1,
    )
    return augmented, mask


@dataclass(frozen=True)
class SetCandidateScorer:
    """J6: small variable-cardinality scorer with mean/max set context."""

    feature_names: tuple[str, ...]
    regressor: TinyMLPRegressor

    @classmethod
    def fit(
        cls,
        candidate_sets: Sequence[Any],
        utility_sets: Sequence[Any],
        *,
        feature_names: Sequence[str],
        legal_masks: Sequence[Sequence[bool]] | None = None,
        **fit_kwargs: Any,
    ) -> "SetCandidateScorer":
        names = tuple(str(name) for name in feature_names)
        assert_deployable_g18_feature_names(names)
        if len(candidate_sets) == 0 or len(candidate_sets) != len(utility_sets):
            raise ValueError("GROUPED_TRAINING_DIMENSION_MISMATCH")
        if legal_masks is not None and len(legal_masks) != len(candidate_sets):
            raise ValueError("GROUPED_LEGAL_MASK_DIMENSION_MISMATCH")
        rows: list[np.ndarray] = []
        targets: list[np.ndarray] = []
        for index, (candidate_set, utility_set) in enumerate(
            zip(candidate_sets, utility_sets, strict=True)
        ):
            augmented, mask = _augment_candidate_set(
                candidate_set,
                names,
                None if legal_masks is None else legal_masks[index],
            )
            utility = np.asarray(utility_set, dtype=np.float64)
            if utility.shape != (augmented.shape[0],) or not np.all(np.isfinite(utility[mask])):
                raise ValueError("UTILITY_SET_INVALID")
            rows.append(augmented[mask])
            targets.append(utility[mask])
        regressor = TinyMLPRegressor.fit(
            np.concatenate(rows, axis=0),
            np.concatenate(targets, axis=0),
            feature_names=_set_feature_names(names),
            **fit_kwargs,
        )
        return cls(names, regressor)

    def scores(
        self,
        candidate_features: Any,
        legal_mask: Sequence[bool] | None = None,
    ) -> np.ndarray:
        augmented, mask = _augment_candidate_set(
            candidate_features,
            self.feature_names,
            legal_mask,
        )
        prediction = np.asarray(self.regressor.predict(augmented), dtype=np.float64)
        return np.where(mask, prediction, -np.inf)

    def choose(self, *args: Any, **kwargs: Any) -> int:
        return int(np.argmax(self.scores(*args, **kwargs)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "J6_small_set_candidate_scorer",
            "feature_names": list(self.feature_names),
            "set_pooling": ["mean", "max"],
            "regressor": self.regressor.to_dict(),
            "variable_candidate_count": True,
            "consumes_baseline_scores": False,
            "identity_features_used": False,
            "outcome_features_used": False,
        }


@dataclass(frozen=True)
class TeacherCounterfactualAffineScorer:
    """Native-exportable J2 warm start plus learned local-utility correction.

    The fixed teacher component is the observed, non-starving M3 priority
    ``(wait_age - deadline_slack) / teacher_time_scale``.  A ridge-regressed
    counterfactual-advantage component is added with a validation-selected
    blend.  The two components are folded into one standardized affine model
    for native inference; neither winner labels nor outcomes are inputs.
    """

    feature_names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    advantage_weights: np.ndarray
    advantage_bias: float
    blend: float
    teacher_time_scale_seconds: float = 120.0

    @classmethod
    def fit_counterfactual_advantage(
        cls,
        features: Any,
        advantages: Any,
        *,
        feature_names: Sequence[str],
        blend: float = 0.0,
        teacher_time_scale_seconds: float = 120.0,
        l2: float = 1e-3,
    ) -> "TeacherCounterfactualAffineScorer":
        names = tuple(str(name) for name in feature_names)
        assert_deployable_g18_feature_names(names)
        matrix = _finite_feature_matrix(features, names)
        targets = _finite_targets(
            advantages, matrix.shape[0], name="COUNTERFACTUAL_ADVANTAGE"
        )
        if (
            not math.isfinite(float(blend))
            or blend < 0.0
            or not math.isfinite(float(teacher_time_scale_seconds))
            or teacher_time_scale_seconds <= 0.0
            or not math.isfinite(float(l2))
            or l2 < 0.0
        ):
            raise ValueError("TEACHER_COUNTERFACTUAL_PARAMETERS_INVALID")
        try:
            deadline_index = names.index("deadline_slack_seconds")
            wait_index = names.index("wait_age_seconds")
        except ValueError as exc:
            raise ValueError("TEACHER_PRIORITY_FEATURES_REQUIRED") from exc
        if deadline_index == wait_index:  # pragma: no cover - names are unique
            raise ValueError("TEACHER_PRIORITY_FEATURES_INVALID")
        mean = np.mean(matrix, axis=0)
        scale = np.std(matrix, axis=0)
        scale = np.where(scale > 1.0e-12, scale, 1.0)
        normalized = (matrix - mean) / scale
        design = np.column_stack((np.ones(matrix.shape[0]), normalized))
        regularizer = np.eye(design.shape[1], dtype=np.float64) * float(l2)
        regularizer[0, 0] = 0.0
        solved = np.linalg.solve(
            design.T @ design + regularizer,
            design.T @ targets,
        )
        return cls(
            names,
            np.asarray(mean, dtype=np.float64),
            np.asarray(scale, dtype=np.float64),
            np.asarray(solved[1:], dtype=np.float64),
            float(solved[0]),
            float(blend),
            float(teacher_time_scale_seconds),
        )

    def with_blend(self, blend: float) -> "TeacherCounterfactualAffineScorer":
        if not math.isfinite(float(blend)) or blend < 0.0:
            raise ValueError("BLEND_MUST_BE_FINITE_NONNEGATIVE")
        return TeacherCounterfactualAffineScorer(
            self.feature_names,
            self.mean,
            self.scale,
            self.advantage_weights,
            self.advantage_bias,
            float(blend),
            self.teacher_time_scale_seconds,
        )

    def component_scores(self, candidate_features: Any) -> tuple[np.ndarray, np.ndarray]:
        matrix = _finite_feature_matrix(
            candidate_features, self.feature_names, name="CANDIDATE_FEATURES"
        )
        deadline_index = self.feature_names.index("deadline_slack_seconds")
        wait_index = self.feature_names.index("wait_age_seconds")
        teacher = (
            matrix[:, wait_index] - matrix[:, deadline_index]
        ) / self.teacher_time_scale_seconds
        advantage = (
            (matrix - self.mean) / self.scale @ self.advantage_weights
            + self.advantage_bias
        )
        return teacher, np.asarray(advantage, dtype=np.float64)

    def scores(self, candidate_features: Any) -> np.ndarray:
        teacher, advantage = self.component_scores(candidate_features)
        return teacher + self.blend * advantage

    def choose(self, candidate_features: Any) -> int:
        return int(np.argmax(self.scores(candidate_features)))

    def affine_parameters(self) -> tuple[np.ndarray, float]:
        """Fold both components into ``bias + weights @ standardized_x``."""

        weights = self.blend * self.advantage_weights.copy()
        bias = self.blend * self.advantage_bias
        deadline_index = self.feature_names.index("deadline_slack_seconds")
        wait_index = self.feature_names.index("wait_age_seconds")
        weights[wait_index] += (
            self.scale[wait_index] / self.teacher_time_scale_seconds
        )
        weights[deadline_index] -= (
            self.scale[deadline_index] / self.teacher_time_scale_seconds
        )
        bias += (
            self.mean[wait_index] - self.mean[deadline_index]
        ) / self.teacher_time_scale_seconds
        return weights, float(bias)

    def to_dict(self) -> dict[str, Any]:
        weights, bias = self.affine_parameters()
        return {
            "family": "teacher_warm_start_counterfactual_advantage_affine",
            "feature_names": list(self.feature_names),
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "weights": weights.tolist(),
            "bias": bias,
            "score_direction": "higher_is_better",
            "tie_break": "fifo",
            "tie_break_scope": "finite_in_contract_equal_score_only",
            "ood_fallback": "J2",
            "teacher_component": {
                "formula": "(wait_age_seconds - deadline_slack_seconds) / teacher_time_scale_seconds",
                "teacher_time_scale_seconds": self.teacher_time_scale_seconds,
                "validated_support": "non_starving_wait_age_below_120_seconds",
            },
            "counterfactual_advantage_component": {
                "blend": self.blend,
                "weights": self.advantage_weights.tolist(),
                "bias": self.advantage_bias,
            },
            "identity_features_used": False,
            "outcome_features_used": False,
        }


__all__ = [
    "PairwiseResidualScorer",
    "SetCandidateScorer",
    "StandaloneMLPScorer",
    "TinyMLPRegressor",
    "TinyResidualScorer",
    "TeacherCounterfactualAffineScorer",
]
