"""Offline fitting helpers for G4IRSF16's small JSON model artifacts."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

from .model import (
    DEPLOYMENT_FEATURES,
    MODEL_SCHEMA,
    activation_metrics,
    with_self_sha256,
)


DEFAULT_UNOBSERVED_BOUNDS: Mapping[str, tuple[float, float]] = {
    "deadline_slack_seconds": (-86_400.0, 172_800.0),
    "wait_age_seconds": (0.0, 172_800.0),
    "current_queue_length": (0.0, 10_000.0),
    "target_queue_length": (0.0, 10_000.0),
    "target_scheduled_incoming": (0.0, 10_000.0),
    "current_next_available_wait_seconds": (0.0, 86_400.0),
    "target_next_available_wait_seconds": (0.0, 86_400.0),
    "alternative_action_count": (0.0, 128.0),
    "total_legal_action_count": (0.0, 128.0),
    "current_node_out_degree": (0.0, 128.0),
    "current_node_type": (0.0, 16.0),
    "current_node_service_seconds": (0.0, 86_400.0),
    "baseline_edge_travel_seconds": (0.0, 86_400.0),
    "intervention_edge_travel_seconds": (0.0, 86_400.0),
    "static_remaining_current_seconds": (0.0, 1_000_000.0),
    "static_remaining_baseline_seconds": (0.0, 1_000_000.0),
    "static_remaining_intervention_seconds": (0.0, 1_000_000.0),
    "static_potential_delta_seconds": (-1_000_000.0, 1_000_000.0),
    "f2_model_margin": (-1_000_000.0, 1_000_000.0),
    "f2_raw_score": (-1_000_000.0, 1_000_000.0),
    "recent_visit_count": (0.0, 1_000_000.0),
    "short_history_repeat_count": (0.0, 1_000_000.0),
    "storage_in_leg": (0.0, 1.0),
    "storage_out_leg": (0.0, 1.0),
    "direct_leg": (0.0, 1.0),
    "event_hour_sin": (-1.0, 1.0),
    "event_hour_cos": (-1.0, 1.0),
    "baseline_release": (0.0, 1.0),
    "advertised_fault": (0.0, 1.0),
}


@dataclass(frozen=True)
class PreparedFeatures:
    values: np.ndarray
    mean: np.ndarray
    scale: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    imputation: np.ndarray
    entirely_missing: tuple[str, ...]

    def transform(self, values: np.ndarray) -> np.ndarray:
        matrix = np.asarray(values, dtype=float).copy()
        for column in range(matrix.shape[1]):
            missing = ~np.isfinite(matrix[:, column])
            matrix[missing, column] = self.imputation[column]
        return (matrix - self.mean) / self.scale


def prepare_features(values: np.ndarray) -> PreparedFeatures:
    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2 or matrix.shape[1] != len(DEPLOYMENT_FEATURES):
        raise ValueError("TRAINING_FEATURE_DIMENSION_MISMATCH")
    filled = matrix.copy()
    imputation = np.zeros(matrix.shape[1], dtype=float)
    lower = np.zeros(matrix.shape[1], dtype=float)
    upper = np.zeros(matrix.shape[1], dtype=float)
    entirely_missing: list[str] = []
    for column, name in enumerate(DEPLOYMENT_FEATURES):
        finite = filled[np.isfinite(filled[:, column]), column]
        if finite.size == 0:
            entirely_missing.append(name)
            imputation[column] = 0.0
            lower[column], upper[column] = DEFAULT_UNOBSERVED_BOUNDS[name]
        else:
            imputation[column] = float(np.median(finite))
            lower[column] = float(np.min(finite))
            upper[column] = float(np.max(finite))
            if lower[column] == upper[column]:
                # A constant observed feature is still in-distribution only at
                # that value; the tiny tolerance is numerical, not semantic.
                tolerance = max(1e-12, abs(lower[column]) * 1e-12)
                lower[column] -= tolerance
                upper[column] += tolerance
        missing = ~np.isfinite(filled[:, column])
        filled[missing, column] = imputation[column]
    mean = np.mean(filled, axis=0)
    scale = np.std(filled, axis=0)
    scale[~np.isfinite(scale) | (scale < 1e-12)] = 1.0
    return PreparedFeatures(
        values=(filled - mean) / scale,
        mean=mean,
        scale=scale,
        lower=lower,
        upper=upper,
        imputation=imputation,
        entirely_missing=tuple(entirely_missing),
    )


def _constant_logit(label_mean: float, width: int) -> np.ndarray:
    probability = min(max(float(label_mean), 1e-6), 1.0 - 1e-6)
    return np.asarray([math.log(probability / (1.0 - probability)), *([0.0] * width)])


def _fit_logit(
    x: np.ndarray,
    y: np.ndarray,
    *,
    seed: int,
    balanced: bool = True,
    l2: float = 1.0,
) -> np.ndarray:
    if np.unique(y).size < 2:
        return _constant_logit(float(np.mean(y)), x.shape[1])
    # Keep evidence generation independent of platform BLAS/OpenMP loaders.
    # The Windows research environment has raised an uncatchable c06d007f
    # native exception in compiled sklearn/scipy solver paths.  This tiny,
    # deterministic full-batch optimizer uses only elementwise NumPy
    # reductions and is sufficient for the preregistered linear diagnostic.
    matrix = np.asarray(x, dtype=float)
    target = np.asarray(y, dtype=float)
    weights = np.zeros(matrix.shape[1] + 1, dtype=float)
    prevalence = min(max(float(np.mean(target)), 1e-6), 1.0 - 1e-6)
    weights[0] = math.log(prevalence / (1.0 - prevalence))
    sample_weight = np.ones(len(target), dtype=float)
    if balanced:
        positive_count = max(1, int(np.sum(target == 1.0)))
        negative_count = max(1, int(np.sum(target == 0.0)))
        sample_weight[target == 1.0] = len(target) / (2.0 * positive_count)
        sample_weight[target == 0.0] = len(target) / (2.0 * negative_count)
    mean_squared_norm = float(np.mean(np.sum(matrix * matrix, axis=1)))
    base_step = 0.5 / max(1.0, 0.25 * mean_squared_norm)
    for iteration in range(320):
        logits = weights[0] + np.sum(matrix * weights[1:], axis=1)
        probability = 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))
        error = (probability - target) * sample_weight
        gradient0 = float(np.mean(error))
        gradient = np.mean(error[:, None] * matrix, axis=0)
        gradient += (float(l2) / max(1, len(target))) * weights[1:]
        step = base_step / math.sqrt(1.0 + iteration / 40.0)
        update0 = step * gradient0
        update = step * gradient
        weights[0] -= update0
        weights[1:] -= update
        if max(abs(update0), float(np.max(np.abs(update)))) < 1e-9:
            break
    return weights


def _platt_transform(
    weights: np.ndarray,
    x_calibration: np.ndarray,
    y_calibration: np.ndarray,
    *,
    seed: int,
) -> np.ndarray:
    if x_calibration.size == 0 or np.unique(y_calibration).size < 2:
        return weights
    logits = weights[0] + np.sum(x_calibration * weights[1:], axis=1)
    calibrated = _fit_logit(
        logits.reshape(-1, 1),
        y_calibration,
        seed=seed,
        balanced=False,
        l2=1e-3,
    )
    intercept = float(calibrated[0])
    slope = float(calibrated[1])
    transformed = weights.copy()
    transformed[1:] *= slope
    transformed[0] = intercept + slope * weights[0]
    return transformed


def _fit_ridge(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    # Deterministic cyclic coordinate descent avoids scipy's native LSQR/BLAS
    # path for the same fail-closed portability reason as the logit optimizer.
    matrix = np.asarray(x, dtype=float)
    target = np.asarray(y, dtype=float)
    alpha = 10.0
    intercept = float(np.mean(target))
    coefficients = np.zeros(matrix.shape[1], dtype=float)
    residual = target - intercept
    denominators = np.sum(matrix * matrix, axis=0) + alpha
    for _ in range(80):
        maximum_change = 0.0
        intercept_change = float(np.mean(residual))
        intercept += intercept_change
        residual -= intercept_change
        maximum_change = abs(intercept_change)
        for column in range(matrix.shape[1]):
            values = matrix[:, column]
            old = coefficients[column]
            residual += values * old
            new = float(np.sum(values * residual) / denominators[column])
            coefficients[column] = new
            residual -= values * new
            maximum_change = max(maximum_change, abs(new - old))
        if maximum_change < 1e-9:
            break
    return np.concatenate(([intercept], coefficients))


def _cluster_bootstrap_indices(
    groups: np.ndarray,
    *,
    rng: np.random.Generator,
) -> np.ndarray:
    unique = np.unique(groups)
    sampled = rng.choice(unique, size=len(unique), replace=True)
    chunks = [np.flatnonzero(groups == group) for group in sampled]
    return np.concatenate(chunks) if chunks else np.arange(len(groups))


def fit_linear_ensemble(
    x_train_raw: np.ndarray,
    beneficial_train: np.ndarray,
    harmful_train: np.ndarray,
    utility_train: np.ndarray,
    train_groups: Sequence[str],
    *,
    x_calibration_raw: np.ndarray,
    beneficial_calibration: np.ndarray,
    harmful_calibration: np.ndarray,
    ensemble_size: int = 32,
    seed: int = 16,
) -> tuple[PreparedFeatures, dict[str, list[list[float]]]]:
    prepared = prepare_features(x_train_raw)
    x_train = prepared.values
    x_calibration = prepared.transform(np.asarray(x_calibration_raw, dtype=float))
    beneficial_train = np.asarray(beneficial_train, dtype=int)
    harmful_train = np.asarray(harmful_train, dtype=int)
    utility_train = np.asarray(utility_train, dtype=float)
    groups = np.asarray(tuple(str(group) for group in train_groups), dtype=object)
    if not (
        len(x_train)
        == len(beneficial_train)
        == len(harmful_train)
        == len(utility_train)
        == len(groups)
    ):
        raise ValueError("TRAINING_ROW_COUNT_MISMATCH")
    if not np.all(np.isfinite(utility_train)):
        raise ValueError("TRAINING_UTILITY_NOT_FINITE")
    rng = np.random.default_rng(seed)
    benefit_heads: list[list[float]] = []
    harmful_heads: list[list[float]] = []
    utility_heads: list[list[float]] = []
    for index in range(ensemble_size):
        selected = _cluster_bootstrap_indices(groups, rng=rng)
        benefit = _fit_logit(x_train[selected], beneficial_train[selected], seed=seed + index)
        harmful = _fit_logit(x_train[selected], harmful_train[selected], seed=seed + 10_000 + index)
        benefit = _platt_transform(
            benefit,
            x_calibration,
            np.asarray(beneficial_calibration, dtype=int),
            seed=seed + 20_000 + index,
        )
        harmful = _platt_transform(
            harmful,
            x_calibration,
            np.asarray(harmful_calibration, dtype=int),
            seed=seed + 30_000 + index,
        )
        utility = _fit_ridge(x_train[selected], utility_train[selected])
        benefit_heads.append(benefit.tolist())
        harmful_heads.append(harmful.tolist())
        utility_heads.append(utility.tolist())
    return prepared, {
        "benefit_logit": benefit_heads,
        "harmful_logit": harmful_heads,
        "risk_adjusted_utility_seconds": utility_heads,
    }


def score_linear_heads(
    prepared: PreparedFeatures,
    heads: Mapping[str, Sequence[Sequence[float]]],
    x_raw: np.ndarray,
) -> dict[str, np.ndarray]:
    x = prepared.transform(np.asarray(x_raw, dtype=float))

    def matrix(name: str) -> np.ndarray:
        values = np.asarray(heads[name], dtype=float)
        if values.ndim != 2 or values.shape[1] != x.shape[1] + 1:
            raise ValueError(f"MODEL_HEAD_DIMENSION:{name}")
        return values

    benefit_weights = matrix("benefit_logit")
    harmful_weights = matrix("harmful_logit")
    utility_weights = matrix("risk_adjusted_utility_seconds")
    # Broadcasting avoids platform BLAS loading in the evidence-generation
    # path; the matrices are intentionally tiny and this is fully deterministic.
    benefit_logits = benefit_weights[:, :1] + np.sum(
        benefit_weights[:, None, 1:] * x[None, :, :], axis=2
    )
    harmful_logits = harmful_weights[:, :1] + np.sum(
        harmful_weights[:, None, 1:] * x[None, :, :], axis=2
    )
    benefit = 1.0 / (1.0 + np.exp(-np.clip(benefit_logits, -700.0, 700.0)))
    harmful = 1.0 / (1.0 + np.exp(-np.clip(harmful_logits, -700.0, 700.0)))
    utility = utility_weights[:, :1] + np.sum(
        utility_weights[:, None, 1:] * x[None, :, :], axis=2
    )
    return {
        "benefit_probability_mean": np.mean(benefit, axis=0),
        "benefit_probability_lcb": np.quantile(benefit, 0.05, axis=0),
        "harmful_probability_mean": np.mean(harmful, axis=0),
        "harmful_probability_ucb": np.quantile(harmful, 0.95, axis=0),
        "utility_mean_seconds": np.mean(utility, axis=0),
        "utility_lcb_seconds": np.quantile(utility, 0.05, axis=0),
    }


def choose_selective_thresholds(
    diagnostics: Mapping[str, np.ndarray],
    signed_classes: Sequence[str],
    observed_utilities: Sequence[float],
    *,
    minimum_coverage: float,
    maximum_coverage: float,
    maximum_harmful_activation_rate: float,
) -> tuple[dict[str, float], dict[str, Any]]:
    benefit = np.asarray(diagnostics["benefit_probability_lcb"], dtype=float)
    harmful = np.asarray(diagnostics["harmful_probability_ucb"], dtype=float)
    utility_lcb = np.asarray(diagnostics["utility_lcb_seconds"], dtype=float)
    labels = tuple(str(value) for value in signed_classes)
    utilities = tuple(float(value) for value in observed_utilities)
    if not (len(benefit) == len(harmful) == len(utility_lcb) == len(labels) == len(utilities)):
        raise ValueError("THRESHOLD_SELECTION_ROW_COUNT_MISMATCH")

    # Calibration labels choose only the two probability cutoffs.  The utility
    # condition remains preregistered at a strict lower bound above zero.
    benefit_candidates = sorted({float(value) for value in benefit}, reverse=True)
    harmful_candidates = sorted({float(value) for value in harmful})
    best: tuple[tuple[Any, ...], dict[str, float], dict[str, Any]] | None = None
    for benefit_threshold in benefit_candidates:
        benefit_mask = benefit >= benefit_threshold
        if not np.any(benefit_mask & (utility_lcb > 0.0)):
            continue
        for harmful_budget in harmful_candidates:
            activation = benefit_mask & (harmful <= harmful_budget) & (utility_lcb > 0.0)
            metrics = activation_metrics(labels, activation.tolist(), utilities)
            coverage = float(metrics["activation_coverage"])
            in_range = minimum_coverage <= coverage <= maximum_coverage
            risk_pass = (
                float(metrics["harmful_activation_rate"])
                <= maximum_harmful_activation_rate
            )
            precision = float(metrics["beneficial_precision"])
            utility_bound = float(metrics["risk_adjusted_utility_lcb_seconds"])
            objective = (
                int(in_range and risk_pass and precision >= 0.90 and utility_bound > 0.0),
                int(risk_pass),
                precision,
                utility_bound if math.isfinite(utility_bound) else -math.inf,
                -abs(coverage - min(maximum_coverage, 0.01)),
                -harmful_budget,
                benefit_threshold,
            )
            thresholds = {
                "benefit_probability_lcb": benefit_threshold,
                "harmful_probability_ucb": harmful_budget,
                "utility_lcb_margin_seconds": 0.0,
            }
            if best is None or objective > best[0]:
                best = (objective, thresholds, metrics)
    if best is None:
        thresholds = {
            "benefit_probability_lcb": 1.0,
            "harmful_probability_ucb": 0.0,
            "utility_lcb_margin_seconds": 0.0,
        }
        metrics = activation_metrics(labels, [False] * len(labels), utilities)
        return thresholds, metrics
    return best[1], best[2]


def build_model_artifact(
    *,
    kind: str,
    action: str,
    prepared: PreparedFeatures,
    heads: Mapping[str, list[list[float]]],
    thresholds: Mapping[str, float],
    training_metadata: Mapping[str, Any],
) -> dict[str, Any]:
    return with_self_sha256(
        {
            "schema": MODEL_SCHEMA,
            "kind": kind,
            "action": action,
            "feature_names": list(DEPLOYMENT_FEATURES),
            "feature_policy": {
                "allowlist_only": True,
                "raw_node_source_goal_ids": False,
                "task_or_runtime_identity": False,
                "future_or_posthoc_features": False,
                "entirely_missing_during_training": list(prepared.entirely_missing),
            },
            "normalization": {
                "mean": prepared.mean.tolist(),
                "scale": prepared.scale.tolist(),
                "imputation": prepared.imputation.tolist(),
            },
            "training_bounds": {
                "min": prepared.lower.tolist(),
                "max": prepared.upper.tolist(),
            },
            "heads": dict(heads),
            "thresholds": {
                "benefit_probability_lcb": float(thresholds["benefit_probability_lcb"]),
                "harmful_probability_ucb": float(thresholds["harmful_probability_ucb"]),
                "utility_lcb_margin_seconds": float(thresholds["utility_lcb_margin_seconds"]),
            },
            "training_metadata": dict(training_metadata),
        }
    )
