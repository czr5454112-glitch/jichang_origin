"""Calibration, OOD checks, and conservative selective override gates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

import numpy as np

from .features import assert_strictly_local_feature_names


def expected_calibration_error(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    bin_count: int = 10,
) -> float:
    probability = np.asarray(probabilities, dtype=np.float64)
    target = np.asarray(labels, dtype=np.float64)
    if probability.ndim != 1 or probability.shape != target.shape or probability.size == 0:
        raise ValueError("CALIBRATION_INPUT_MISMATCH")
    if bin_count <= 0 or not np.all(np.isfinite(probability)):
        raise ValueError("CALIBRATION_INPUT_INVALID")
    if not np.all((probability >= 0.0) & (probability <= 1.0)):
        raise ValueError("PROBABILITY_OUT_OF_RANGE")
    if not np.all((target == 0.0) | (target == 1.0)):
        raise ValueError("CALIBRATION_LABEL_NOT_BINARY")
    bins = np.minimum((probability * bin_count).astype(int), bin_count - 1)
    error = 0.0
    for index in range(bin_count):
        members = bins == index
        if not np.any(members):
            continue
        error += float(np.mean(members)) * abs(
            float(np.mean(probability[members])) - float(np.mean(target[members]))
        )
    return error


@dataclass(frozen=True)
class PlattCalibrator:
    """Two-parameter calibration fitted only on the calibration partition."""

    slope: float
    intercept: float

    @classmethod
    def fit(
        cls,
        scores: Sequence[float],
        labels: Sequence[int],
        *,
        epochs: int = 1_000,
        learning_rate: float = 0.05,
        l2: float = 1e-4,
    ) -> "PlattCalibrator":
        values = np.asarray(scores, dtype=np.float64)
        target = np.asarray(labels, dtype=np.float64)
        if values.ndim != 1 or values.shape != target.shape or values.size == 0:
            raise ValueError("CALIBRATION_INPUT_MISMATCH")
        if not np.all(np.isfinite(values)) or not np.all((target == 0.0) | (target == 1.0)):
            raise ValueError("CALIBRATION_INPUT_INVALID")
        if len(np.unique(target)) != 2:
            raise ValueError("CALIBRATION_REQUIRES_BOTH_CLASSES")
        mean = float(np.mean(values))
        scale = float(np.std(values))
        if scale <= 1e-12:
            scale = 1.0
        normalized = (values - mean) / scale
        slope = 1.0
        intercept = math.log((float(np.sum(target)) + 0.5) / (float(np.sum(1.0 - target)) + 0.5))
        for _ in range(epochs):
            logits = np.clip(slope * normalized + intercept, -40.0, 40.0)
            probability = 1.0 / (1.0 + np.exp(-logits))
            residual = probability - target
            slope -= learning_rate * (float(np.mean(residual * normalized)) + l2 * slope)
            intercept -= learning_rate * float(np.mean(residual))
        # Fold normalization into exported coefficients.
        return cls(slope / scale, intercept - slope * mean / scale)

    def predict(self, scores: Sequence[float] | float) -> np.ndarray | float:
        values = np.asarray(scores, dtype=np.float64)
        if not np.all(np.isfinite(values)):
            raise ValueError("CALIBRATION_SCORE_NOT_FINITE")
        logits = np.clip(self.slope * values + self.intercept, -40.0, 40.0)
        result = 1.0 / (1.0 + np.exp(-logits))
        return float(result) if result.ndim == 0 else result


@dataclass(frozen=True)
class FeatureEnvelope:
    """A transparent local-feature support envelope for OOD abstention."""

    feature_names: tuple[str, ...]
    lower: np.ndarray
    upper: np.ndarray

    @classmethod
    def fit(
        cls,
        features: Any,
        *,
        feature_names: Sequence[str],
        lower_quantile: float = 0.005,
        upper_quantile: float = 0.995,
        margin_fraction: float = 0.05,
    ) -> "FeatureEnvelope":
        matrix = np.asarray(features, dtype=np.float64)
        names = tuple(feature_names)
        if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] != len(names):
            raise ValueError("OOD_FEATURE_DIMENSION_MISMATCH")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("OOD_FEATURES_NOT_FINITE")
        assert_strictly_local_feature_names(names)
        if not 0.0 <= lower_quantile < upper_quantile <= 1.0 or margin_fraction < 0.0:
            raise ValueError("OOD_QUANTILES_INVALID")
        lower = np.quantile(matrix, lower_quantile, axis=0)
        upper = np.quantile(matrix, upper_quantile, axis=0)
        width = np.maximum(upper - lower, 1e-9)
        return cls(names, lower - margin_fraction * width, upper + margin_fraction * width)

    def is_ood(self, features: Sequence[float]) -> bool:
        vector = np.asarray(features, dtype=np.float64)
        if vector.shape != self.lower.shape or not np.all(np.isfinite(vector)):
            return True
        return bool(np.any(vector < self.lower) or np.any(vector > self.upper))


@dataclass(frozen=True)
class OverrideEvidence:
    proposed_index: int
    calibrated_benefit_probabilities: tuple[float, ...]
    calibrated_harm_probabilities: tuple[float, ...]
    utility_samples_seconds: tuple[float, ...]
    calibration_ece: float
    ood: bool
    supervisor_authorized: bool


@dataclass(frozen=True)
class OverrideDecision:
    chosen_index: int
    baseline_index: int
    proposed_index: int
    activated: bool
    reason: str
    benefit_probability_lcb: float
    harm_probability_ucb: float
    utility_lcb_seconds: float


def _quantile(values: Sequence[float], probability: float, name: str) -> float:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name}_SAMPLES_INVALID")
    return float(np.quantile(array, probability))


@dataclass(frozen=True)
class ConservativeSelectiveOverride:
    """Keep the baseline unless every calibrated risk gate passes."""

    benefit_probability_lcb_min: float = 0.60
    harm_probability_ucb_max: float = 0.05
    utility_lcb_min_seconds: float = 0.0
    calibration_ece_max: float = 0.08
    lower_quantile: float = 0.05
    upper_quantile: float = 0.95
    min_ensemble_size: int = 3

    def decide(self, baseline_index: int, evidence: OverrideEvidence) -> OverrideDecision:
        for name, values in (
            ("BENEFIT", evidence.calibrated_benefit_probabilities),
            ("HARM", evidence.calibrated_harm_probabilities),
        ):
            if any(float(value) < 0.0 or float(value) > 1.0 for value in values):
                raise ValueError(f"{name}_PROBABILITY_OUT_OF_RANGE")
        if not 0.0 <= float(evidence.calibration_ece) <= 1.0:
            raise ValueError("CALIBRATION_ECE_OUT_OF_RANGE")
        benefit = _quantile(
            evidence.calibrated_benefit_probabilities,
            self.lower_quantile,
            "BENEFIT",
        )
        harm = _quantile(
            evidence.calibrated_harm_probabilities,
            self.upper_quantile,
            "HARM",
        )
        utility = _quantile(
            evidence.utility_samples_seconds,
            self.lower_quantile,
            "UTILITY",
        )
        sample_count = min(
            len(evidence.calibrated_benefit_probabilities),
            len(evidence.calibrated_harm_probabilities),
            len(evidence.utility_samples_seconds),
        )
        reason = "ACTIVATE"
        activated = True
        if evidence.proposed_index == baseline_index:
            reason, activated = "BASELINE_ALREADY_SELECTED", False
        elif sample_count < self.min_ensemble_size:
            reason, activated = "INSUFFICIENT_ENSEMBLE_SUPPORT", False
        elif not math.isfinite(float(evidence.calibration_ece)) or evidence.calibration_ece > self.calibration_ece_max:
            reason, activated = "CALIBRATION_GATE", False
        elif evidence.ood:
            reason, activated = "OOD_GATE", False
        elif not evidence.supervisor_authorized:
            reason, activated = "SUPERVISOR_GATE", False
        elif benefit < self.benefit_probability_lcb_min:
            reason, activated = "BENEFIT_CONFIDENCE_GATE", False
        elif harm >= self.harm_probability_ucb_max:
            reason, activated = "HARM_BUDGET_GATE", False
        elif utility <= self.utility_lcb_min_seconds:
            reason, activated = "UTILITY_LCB_GATE", False
        chosen = evidence.proposed_index if activated else baseline_index
        return OverrideDecision(
            chosen_index=int(chosen),
            baseline_index=int(baseline_index),
            proposed_index=int(evidence.proposed_index),
            activated=activated,
            reason=reason,
            benefit_probability_lcb=benefit,
            harm_probability_ucb=harm,
            utility_lcb_seconds=utility,
        )
