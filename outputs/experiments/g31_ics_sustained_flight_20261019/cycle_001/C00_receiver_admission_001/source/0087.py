"""Small, deterministic models used by the G4IRSF16 supervisor.

Training may use scikit-learn, but deployment deliberately does not.  The
exported artifact is an auditable ensemble of linear heads evaluated here with
only the Python standard library.  Every unknown, malformed, or out-of-range
feature fails closed to abstention.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


MODEL_SCHEMA = "czr005.g4irsf16.selective_linear_ensemble.v1"

# Ordered and intentionally ID-free.  No task, current-node, source, or goal
# identifier is available to the deployable model.  Topology is represented by
# local classes and static potentials, not memorized identities.
DEPLOYMENT_FEATURES: tuple[str, ...] = (
    "deadline_slack_seconds",
    "wait_age_seconds",
    "current_queue_length",
    "target_queue_length",
    "target_scheduled_incoming",
    "current_next_available_wait_seconds",
    "target_next_available_wait_seconds",
    "alternative_action_count",
    "total_legal_action_count",
    "current_node_out_degree",
    "current_node_type",
    "current_node_service_seconds",
    "baseline_edge_travel_seconds",
    "intervention_edge_travel_seconds",
    "static_remaining_current_seconds",
    "static_remaining_baseline_seconds",
    "static_remaining_intervention_seconds",
    "static_potential_delta_seconds",
    "f2_model_margin",
    "f2_raw_score",
    "recent_visit_count",
    "short_history_repeat_count",
    "storage_in_leg",
    "storage_out_leg",
    "direct_leg",
    "event_hour_sin",
    "event_hour_cos",
    "baseline_release",
    "advertised_fault",
)

FORBIDDEN_RUNTIME_FEATURE_TOKENS: tuple[str, ...] = (
    "task_id",
    "runtime_bag_id",
    "segment_id",
    "teacher",
    "future_route",
    "future_schedule",
    "final_tth",
    "completion_outcome",
    "realized_affected",
    "h_system_outcome",
    "global_queue",
    "global_reservation",
)


class FeatureSchemaError(ValueError):
    """Raised when deployment input does not exactly match the frozen schema."""


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def with_self_sha256(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    result.pop("self_sha256", None)
    result["self_sha256"] = canonical_sha256(result)
    return result


def validate_self_sha256(value: Mapping[str, Any]) -> None:
    declared = value.get("self_sha256")
    unsigned = dict(value)
    unsigned.pop("self_sha256", None)
    if not isinstance(declared, str) or declared != canonical_sha256(unsigned):
        raise ValueError("MODEL_SELF_SHA256_MISMATCH")


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FeatureSchemaError(f"FEATURE_NOT_NUMERIC:{name}")
    number = float(value)
    if not math.isfinite(number):
        raise FeatureSchemaError(f"FEATURE_NOT_FINITE:{name}")
    return number


def ordered_feature_vector(features: Mapping[str, Any]) -> tuple[float, ...]:
    """Validate an exact ordered feature mapping and return its numeric vector."""

    keys = tuple(features.keys())
    if keys != DEPLOYMENT_FEATURES:
        missing = [name for name in DEPLOYMENT_FEATURES if name not in features]
        extra = [name for name in keys if name not in DEPLOYMENT_FEATURES]
        if missing:
            raise FeatureSchemaError("FEATURES_MISSING:" + ",".join(missing))
        if extra:
            raise FeatureSchemaError("FEATURES_EXTRA:" + ",".join(extra))
        raise FeatureSchemaError("FEATURE_ORDER_MISMATCH")
    return tuple(_finite_float(features[name], name) for name in keys)


def deployment_feature_mapping(row: Mapping[str, Any]) -> dict[str, float]:
    """Project a larger scientific row into the exact deployment schema."""

    return {
        name: _finite_float(row[name], name)
        for name in DEPLOYMENT_FEATURES
    }


def _sigmoid(value: float) -> float:
    if value >= 0.0:
        exp_value = math.exp(-min(value, 700.0))
        return 1.0 / (1.0 + exp_value)
    exp_value = math.exp(max(value, -700.0))
    return exp_value / (1.0 + exp_value)


def _linear(weights: Sequence[float], vector: Sequence[float]) -> float:
    if len(weights) != len(vector) + 1:
        raise ValueError("MODEL_WEIGHT_DIMENSION_MISMATCH")
    return float(weights[0]) + math.fsum(
        float(weight) * float(value)
        for weight, value in zip(weights[1:], vector, strict=True)
    )


def _quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        raise ValueError("EMPTY_ENSEMBLE")
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


@dataclass(frozen=True)
class SelectiveScore:
    action: str
    activation: bool
    abstention_reason: str
    benefit_probability_mean: float
    benefit_probability_lcb: float
    harmful_probability_mean: float
    harmful_probability_ucb: float
    utility_mean_seconds: float
    utility_lcb_seconds: float
    ood: bool


@dataclass(frozen=True)
class SelectiveEnsembleModel:
    kind: str
    action: str
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    feature_min: tuple[float, ...]
    feature_max: tuple[float, ...]
    benefit_weights: tuple[tuple[float, ...], ...]
    harmful_weights: tuple[tuple[float, ...], ...]
    utility_weights: tuple[tuple[float, ...], ...]
    benefit_probability_lcb_threshold: float
    harmful_probability_ucb_budget: float
    utility_lcb_margin_seconds: float
    artifact_sha256: str

    @classmethod
    def from_artifact(cls, artifact: Mapping[str, Any]) -> "SelectiveEnsembleModel":
        validate_self_sha256(artifact)
        if artifact.get("schema") != MODEL_SCHEMA:
            raise ValueError("MODEL_SCHEMA_MISMATCH")
        names = tuple(str(name) for name in artifact.get("feature_names", ()))
        if names != DEPLOYMENT_FEATURES:
            raise ValueError("MODEL_FEATURE_SCHEMA_MISMATCH")
        normalization = artifact.get("normalization")
        bounds = artifact.get("training_bounds")
        heads = artifact.get("heads")
        thresholds = artifact.get("thresholds")
        if not all(isinstance(item, Mapping) for item in (normalization, bounds, heads, thresholds)):
            raise ValueError("MODEL_SECTION_MISSING")

        def numeric_tuple(section: Mapping[str, Any], key: str) -> tuple[float, ...]:
            values = section.get(key)
            if not isinstance(values, list) or len(values) != len(names):
                raise ValueError(f"MODEL_VECTOR_MISMATCH:{key}")
            result = tuple(_finite_float(value, key) for value in values)
            return result

        means = numeric_tuple(normalization, "mean")
        scales = numeric_tuple(normalization, "scale")
        if any(value <= 0.0 for value in scales):
            raise ValueError("MODEL_SCALE_NONPOSITIVE")
        feature_min = numeric_tuple(bounds, "min")
        feature_max = numeric_tuple(bounds, "max")
        if any(lo > hi for lo, hi in zip(feature_min, feature_max, strict=True)):
            raise ValueError("MODEL_BOUNDS_INVALID")

        def ensemble(name: str) -> tuple[tuple[float, ...], ...]:
            rows = heads.get(name)
            if not isinstance(rows, list) or not rows:
                raise ValueError(f"MODEL_HEAD_MISSING:{name}")
            result: list[tuple[float, ...]] = []
            for row in rows:
                if not isinstance(row, list) or len(row) != len(names) + 1:
                    raise ValueError(f"MODEL_HEAD_DIMENSION:{name}")
                result.append(tuple(_finite_float(value, name) for value in row))
            return tuple(result)

        return cls(
            kind=str(artifact.get("kind")),
            action=str(artifact.get("action")),
            feature_names=names,
            means=means,
            scales=scales,
            feature_min=feature_min,
            feature_max=feature_max,
            benefit_weights=ensemble("benefit_logit"),
            harmful_weights=ensemble("harmful_logit"),
            utility_weights=ensemble("risk_adjusted_utility_seconds"),
            benefit_probability_lcb_threshold=_finite_float(
                thresholds.get("benefit_probability_lcb"),
                "benefit_probability_lcb",
            ),
            harmful_probability_ucb_budget=_finite_float(
                thresholds.get("harmful_probability_ucb"),
                "harmful_probability_ucb",
            ),
            utility_lcb_margin_seconds=_finite_float(
                thresholds.get("utility_lcb_margin_seconds"),
                "utility_lcb_margin_seconds",
            ),
            artifact_sha256=str(artifact["self_sha256"]),
        )

    @classmethod
    def load(cls, path: str | Path) -> "SelectiveEnsembleModel":
        with Path(path).open("r", encoding="utf-8") as handle:
            artifact = json.load(handle)
        if not isinstance(artifact, dict):
            raise ValueError("MODEL_ARTIFACT_NOT_OBJECT")
        return cls.from_artifact(artifact)

    def score(self, features: Mapping[str, Any]) -> SelectiveScore:
        try:
            raw = ordered_feature_vector(features)
        except (FeatureSchemaError, KeyError):
            return SelectiveScore(
                action=self.action,
                activation=False,
                abstention_reason="FEATURE_SCHEMA_FAIL_CLOSED",
                benefit_probability_mean=0.0,
                benefit_probability_lcb=0.0,
                harmful_probability_mean=1.0,
                harmful_probability_ucb=1.0,
                utility_mean_seconds=float("-inf"),
                utility_lcb_seconds=float("-inf"),
                ood=True,
            )
        ood = any(
            value < lower or value > upper
            for value, lower, upper in zip(
                raw,
                self.feature_min,
                self.feature_max,
                strict=True,
            )
        )
        vector = tuple(
            (value - mean) / scale
            for value, mean, scale in zip(
                raw,
                self.means,
                self.scales,
                strict=True,
            )
        )
        benefit = [_sigmoid(_linear(weights, vector)) for weights in self.benefit_weights]
        harmful = [_sigmoid(_linear(weights, vector)) for weights in self.harmful_weights]
        utility = [_linear(weights, vector) for weights in self.utility_weights]
        benefit_mean = statistics.fmean(benefit)
        benefit_lcb = _quantile(benefit, 0.05)
        harmful_mean = statistics.fmean(harmful)
        harmful_ucb = _quantile(harmful, 0.95)
        utility_mean = statistics.fmean(utility)
        utility_lcb = _quantile(utility, 0.05)
        reason = "ACTIVATE"
        activation = True
        if ood:
            reason = "OOD_ABSTAIN"
            activation = False
        elif benefit_lcb < self.benefit_probability_lcb_threshold:
            reason = "BENEFIT_CONFIDENCE_ABSTAIN"
            activation = False
        elif harmful_ucb > self.harmful_probability_ucb_budget:
            reason = "HARMFUL_RISK_ABSTAIN"
            activation = False
        elif utility_lcb <= self.utility_lcb_margin_seconds:
            reason = "UTILITY_LCB_ABSTAIN"
            activation = False
        return SelectiveScore(
            action=self.action,
            activation=activation,
            abstention_reason=reason,
            benefit_probability_mean=benefit_mean,
            benefit_probability_lcb=benefit_lcb,
            harmful_probability_mean=harmful_mean,
            harmful_probability_ucb=harmful_ucb,
            utility_mean_seconds=utility_mean,
            utility_lcb_seconds=utility_lcb,
            ood=ood,
        )


def expected_calibration_error(
    probabilities: Sequence[float],
    labels: Sequence[int],
    *,
    bin_count: int = 10,
) -> float:
    if len(probabilities) != len(labels) or not probabilities:
        raise ValueError("CALIBRATION_INPUT_MISMATCH")
    total = len(probabilities)
    error = 0.0
    for index in range(bin_count):
        lower = index / bin_count
        upper = (index + 1) / bin_count
        members = [
            position
            for position, probability in enumerate(probabilities)
            if lower <= probability < upper
            or (index == bin_count - 1 and probability == 1.0)
        ]
        if not members:
            continue
        confidence = statistics.fmean(probabilities[position] for position in members)
        accuracy = statistics.fmean(float(labels[position]) for position in members)
        error += len(members) / total * abs(confidence - accuracy)
    return error


def one_sided_mean_lcb(values: Sequence[float], *, z_value: float = 1.6448536269514722) -> float:
    """Conservative normal-approximation lower bound used for offline gates."""

    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return float("-inf")
    if len(finite) == 1:
        return float("-inf")
    mean = statistics.fmean(finite)
    standard_error = statistics.stdev(finite) / math.sqrt(len(finite))
    return mean - z_value * standard_error


def activation_metrics(
    signed_classes: Sequence[str],
    activations: Sequence[bool],
    utilities: Sequence[float],
) -> dict[str, float | int]:
    if not (len(signed_classes) == len(activations) == len(utilities)):
        raise ValueError("ACTIVATION_METRIC_INPUT_MISMATCH")
    activated = [index for index, flag in enumerate(activations) if flag]
    beneficial = [index for index, label in enumerate(signed_classes) if label == "BENEFICIAL"]
    activated_beneficial = sum(signed_classes[index] == "BENEFICIAL" for index in activated)
    activated_harmful = sum(signed_classes[index] == "HARMFUL" for index in activated)
    activated_utilities = [utilities[index] for index in activated]
    eligible_count = len(signed_classes)
    return {
        "row_count": eligible_count,
        "activation_count": len(activated),
        "activation_coverage": len(activated) / eligible_count if eligible_count else 0.0,
        "beneficial_precision": activated_beneficial / len(activated) if activated else 0.0,
        "beneficial_recall": activated_beneficial / len(beneficial) if beneficial else 0.0,
        # This is a policy risk budget over all eligible states, not harmful-class recall.
        "harmful_activation_rate": activated_harmful / eligible_count if eligible_count else 0.0,
        "high_confidence_harmful_precision": (
            activated_harmful / len(activated) if activated else 0.0
        ),
        # Abstention preserves F2 on this causal target panel. Outside-target F2
        # preservation is measured separately by the full native shadow.
        "target_panel_abstention_rate": (
            1.0 - len(activated) / eligible_count if eligible_count else 1.0
        ),
        "risk_adjusted_utility_mean_seconds": (
            statistics.fmean(activated_utilities) if activated_utilities else float("nan")
        ),
        "risk_adjusted_utility_lcb_seconds": one_sided_mean_lcb(activated_utilities),
    }
