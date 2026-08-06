"""Leakage-safe Phase-D training and transparent artifact export for G4IRSF17.

The training unit is one matched two-candidate source-front decision.  Candidate
zero is the unmodified/current policy decision and candidate one is the causal
alternative.  Realized ``system_utility`` is an offline label only; task,
source, and time keys are used only to build diagnostic partitions.  None of
those values can enter a fitted model.

The final-audit partition is assigned and counted, but deliberately never
scored here.  Opening that partition belongs to a later, explicit decision
step.
"""

from __future__ import annotations

import csv
import io
import json
import math
import uuid
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from .features import (
    CANONICAL_OBSERVATION_FEATURES,
    CANDIDATE_FEATURES,
    CONTEXT_FEATURES,
    PAIRWISE_FEATURES,
    LocalFeatureError,
    canonical_feature_vector,
    pairwise_feature_vector,
)
from .metrics import (
    bucket_generalization_metrics,
    calibration_metrics,
    evaluate_policy_families,
    selective_override_metrics,
    system_utility,
)
from .models import PairwiseLinearRanker, TinyMLPListwiseRanker
from .policies import LocalPriorityCandidate, LocalizedThesisPriority, fifo_baseline
from .selection import (
    ConservativeSelectiveOverride,
    FeatureEnvelope,
    OverrideEvidence,
    PlattCalibrator,
)
from .splits import DEFAULT_FRACTIONS, DiagnosticSplits, group_overlap_count, make_diagnostic_splits


SCHEMA = "czr005.g4irsf17.phase_d_training.v1"
PAIRWISE_MODEL_SCHEMA = "czr005.g4irsf17.i1_pairwise_ensemble.v1"
MLP_MODEL_SCHEMA = "czr005.g4irsf17.i1_tiny_mlp.v1"
POLICY_SCHEMA = "czr005.g4irsf17.i1_policy_comparison.v1"
GATE_SCHEMA = "czr005.g4irsf17.i1_selective_gate.v1"
DEADLINE_MISS_PENALTY_SECONDS = 3_600.0
H_BAG_TRAINING_SCOPE = "BOUNDED_DIRECT_SWAP_COHORT"
H_SYSTEM_EVIDENCE_SCOPE = "H_SYSTEM_EXTERNALITY_AUDIT"


def _new_artifact_set_id(config: "PhaseDTrainingConfig", row_count: int) -> str:
    """Mint one readable, non-hash identity for a coordinated export set."""

    return (
        f"g4irsf17-i1-seed{config.seed}-rows{row_count}-"
        f"{uuid.uuid4()}"
    )


@dataclass(frozen=True)
class PhaseDTrainingConfig:
    """Frozen training, support, and promotion settings.

    Defaults mirror the planned beneficial-effect floor (32/8/8) and use a
    smaller but explicit harmful-effect floor.  Small unit tests or diagnostic
    probes may lower these settings, but every exported gate records the exact
    values used.
    """

    seed: int = 17
    split_fractions: tuple[float, float, float, float] = DEFAULT_FRACTIONS
    time_block_seconds: float = 3_600.0
    utility_tolerance_seconds: float = 1e-9
    ensemble_size: int = 5
    pairwise_epochs: int = 350
    pairwise_learning_rate: float = 0.05
    pairwise_l2: float = 1e-3
    mlp_hidden_dim: int = 8
    mlp_epochs: int = 350
    mlp_learning_rate: float = 0.03
    mlp_l2: float = 1e-4
    calibrator_epochs: int = 600
    utility_l2: float = 1e-3
    minimum_beneficial_train: int = 32
    minimum_beneficial_calibration: int = 8
    minimum_beneficial_validation: int = 8
    minimum_harmful_train: int = 16
    minimum_harmful_calibration: int = 4
    minimum_harmful_validation: int = 4
    minimum_beneficial_sources: int = 3
    minimum_beneficial_time_buckets: int = 3
    minimum_beneficial_legs: int = 2
    minimum_h_system_rows: int = 1
    minimum_validation_activations: int = 1
    minimum_beneficial_precision: float = 0.90
    minimum_harmful_recall: float = 0.95
    maximum_harmful_activation_rate: float = 0.05
    maximum_calibration_ece: float = 0.08
    minimum_activated_utility_seconds: float = 0.0
    benefit_probability_lcb_min: float = 0.60
    harm_probability_ucb_max: float = 0.05

    def __post_init__(self) -> None:
        if self.ensemble_size < 3:
            raise ValueError("ENSEMBLE_SIZE_MUST_BE_AT_LEAST_THREE")
        if self.pairwise_epochs <= 0 or self.mlp_epochs <= 0 or self.calibrator_epochs <= 0:
            raise ValueError("TRAINING_EPOCHS_MUST_BE_POSITIVE")
        if self.time_block_seconds <= 0.0:
            raise ValueError("TIME_BLOCK_MUST_BE_POSITIVE")
        if self.utility_tolerance_seconds < 0.0:
            raise ValueError("UTILITY_TOLERANCE_MUST_BE_NONNEGATIVE")
        integer_floors = (
            self.minimum_beneficial_train,
            self.minimum_beneficial_calibration,
            self.minimum_beneficial_validation,
            self.minimum_harmful_train,
            self.minimum_harmful_calibration,
            self.minimum_harmful_validation,
            self.minimum_beneficial_sources,
            self.minimum_beneficial_time_buckets,
            self.minimum_beneficial_legs,
            self.minimum_h_system_rows,
            self.minimum_validation_activations,
        )
        if any(value < 0 for value in integer_floors):
            raise ValueError("SUPPORT_FLOORS_MUST_BE_NONNEGATIVE")
        probabilities = (
            self.minimum_beneficial_precision,
            self.minimum_harmful_recall,
            self.maximum_harmful_activation_rate,
            self.maximum_calibration_ece,
            self.benefit_probability_lcb_min,
            self.harm_probability_ucb_max,
        )
        if any(value < 0.0 or value > 1.0 for value in probabilities):
            raise ValueError("PROBABILITY_CRITERIA_OUT_OF_RANGE")

    def to_dict(self) -> dict[str, Any]:
        return {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in self.__dict__.items()
        }


@dataclass(frozen=True)
class LinearUtilityRegressor:
    """Small standardized ridge model used only for an override utility LCB."""

    feature_names: tuple[str, ...]
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray
    bias: float

    @classmethod
    def fit(
        cls,
        features: Any,
        utilities_seconds: Any,
        *,
        feature_names: Sequence[str],
        l2: float = 1e-3,
        epochs: int = 300,
        learning_rate: float = 0.03,
    ) -> "LinearUtilityRegressor":
        matrix = np.asarray(features, dtype=np.float64)
        targets = np.asarray(utilities_seconds, dtype=np.float64)
        names = tuple(str(name) for name in feature_names)
        if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] != len(names):
            raise ValueError("UTILITY_FEATURE_DIMENSION_MISMATCH")
        if targets.shape != (matrix.shape[0],):
            raise ValueError("UTILITY_TARGET_DIMENSION_MISMATCH")
        if not np.all(np.isfinite(matrix)) or not np.all(np.isfinite(targets)):
            raise ValueError("UTILITY_TRAINING_VALUE_NOT_FINITE")
        if l2 < 0.0:
            raise ValueError("UTILITY_L2_MUST_BE_NONNEGATIVE")
        if epochs <= 0 or learning_rate <= 0.0:
            raise ValueError("UTILITY_OPTIMIZER_PARAMETERS_INVALID")
        mean = np.mean(matrix, axis=0)
        scale = np.std(matrix, axis=0)
        scale = np.where(scale > 1e-12, scale, 1.0)
        normalized = (matrix - mean) / scale
        # Gradient descent keeps this tiny model portable on Windows workers
        # where delay-loaded LAPACK DLLs may be unavailable.  Explicit
        # reductions also avoid paying a large solver startup cost for a
        # 39-feature diagnostic model.
        weights = np.zeros(matrix.shape[1], dtype=np.float64)
        bias = float(np.mean(targets))
        for _ in range(epochs):
            prediction = np.sum(normalized * weights[None, :], axis=1) + bias
            residual = prediction - targets
            gradient = np.mean(normalized * residual[:, None], axis=0) + l2 * weights
            bias_gradient = float(np.mean(residual))
            weights -= learning_rate * gradient
            bias -= learning_rate * bias_gradient
        return cls(names, mean, scale, weights, bias)

    def predict(self, features: Any) -> np.ndarray | float:
        matrix = np.asarray(features, dtype=np.float64)
        one_row = matrix.ndim == 1
        if one_row:
            matrix = matrix[None, :]
        if matrix.ndim != 2 or matrix.shape[1] != len(self.feature_names):
            raise ValueError("UTILITY_FEATURE_DIMENSION_MISMATCH")
        if not np.all(np.isfinite(matrix)):
            raise ValueError("UTILITY_FEATURE_NOT_FINITE")
        result = np.sum(
            ((matrix - self.mean) / self.scale) * self.weights[None, :], axis=1
        ) + self.bias
        return float(result[0]) if one_row else result

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": "linear_ridge_utility",
            "feature_names": list(self.feature_names),
            "mean": self.mean.tolist(),
            "scale": self.scale.tolist(),
            "weights": self.weights.tolist(),
            "bias": self.bias,
            "identity_features_used": False,
        }


@dataclass(frozen=True)
class _PreparedRow:
    task_group: str
    source_group: str
    timestamp: float
    leg: str
    time_bucket: str
    queue_bucket: str
    slack_bucket: str
    # ``None`` is reserved for the sealed final-audit partition.  Its outcome
    # is not parsed, counted by sign, or passed to any evaluator in Phase D.
    utility_seconds: float | None
    utility_scope: str
    h_system_externality_evidence: bool
    candidate_observations: tuple[dict[str, float], dict[str, float]]
    candidate_matrix: np.ndarray
    pairwise_vector: np.ndarray
    legal_mask: tuple[bool, bool]
    supervisor_authorized: bool

    @property
    def benefit_label(self) -> int:
        if self.utility_seconds is None:
            raise ValueError("FINAL_AUDIT_LABEL_IS_SEALED")
        return int(self.utility_seconds > 0.0)

    @property
    def harm_label(self) -> int:
        if self.utility_seconds is None:
            raise ValueError("FINAL_AUDIT_LABEL_IS_SEALED")
        return int(self.utility_seconds < 0.0)


@dataclass(frozen=True)
class _SplitMetadata:
    task_group: str
    source_group: str
    timestamp: float


@dataclass(frozen=True)
class PhaseDTrainingResult:
    """In-memory decision bundle; all payloads are directly JSON serializable."""

    status: str
    authorized: bool
    reasons: tuple[str, ...]
    config: PhaseDTrainingConfig
    input_summary: dict[str, Any]
    split_summary: dict[str, Any]
    support: dict[str, Any]
    calibration: dict[str, Any]
    validation_evaluation: dict[str, Any]
    diagnostics: dict[str, Any]
    buckets: dict[str, Any]
    model_artifacts: dict[str, dict[str, Any]]
    policy_artifact: dict[str, Any]
    gate_artifact: dict[str, Any]
    report_markdown: str
    diagnostic_splits: DiagnosticSplits | None = field(default=None, repr=False)

    def summary_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "status": self.status,
            "authorized": self.authorized,
            "reasons": list(self.reasons),
            "input_summary": self.input_summary,
            "split_summary": self.split_summary,
            "calibration": self.calibration,
            "final_audit_consumed": False,
        }


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label}_MUST_BE_NUMERIC")
    if isinstance(value, str):
        value = value.strip()
        if not value:
            raise ValueError(f"{label}_MUST_BE_NUMERIC")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}_MUST_BE_NUMERIC") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label}_NOT_FINITE")
    return result


def _mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str) and value.strip().startswith("{"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, Mapping) else None
    return None


def _sequence(value: Any) -> Sequence[Any] | None:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, list) else None
    return None


def _first(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _bool_value(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "pass", "authorized"}:
            return True
        if normalized in {"0", "false", "no", "fail", "unauthorized"}:
            return False
    raise ValueError("BOOLEAN_VALUE_INVALID")


def _feature_containers(row: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    containers: list[Mapping[str, Any]] = [row]
    for key in ("features", "feature_row", "observation_pair"):
        nested = _mapping(row.get(key))
        if nested is not None:
            containers.append(nested)
    return tuple(containers)


def _project_observation(raw: Mapping[str, Any], label: str) -> dict[str, float]:
    missing = [name for name in CANONICAL_OBSERVATION_FEATURES if name not in raw]
    if missing:
        raise ValueError(f"{label}_FEATURES_MISSING:" + ",".join(missing))
    projected = {
        name: _finite_number(raw[name], f"{label}_{name}")
        for name in CANONICAL_OBSERVATION_FEATURES
    }
    # This call enforces the physical bounds and exact local schema.  Extra
    # metadata in an input mapping is intentionally ignored, never modeled.
    canonical_feature_vector(projected)
    return projected


def _ordered_feature_mapping(
    raw: Any,
    names: Sequence[str],
    label: str,
) -> dict[str, float]:
    mapping = _mapping(raw)
    if mapping is not None:
        nested = mapping.get("features")
        mapping = _mapping(nested) or mapping
        if _sequence(nested) is not None:
            raw = nested
        else:
            missing = [name for name in names if name not in mapping]
            if missing:
                raise ValueError(f"{label}_FEATURES_MISSING:" + ",".join(missing))
            return {
                name: _finite_number(mapping[name], f"{label}_{name}")
                for name in names
            }
    values = _sequence(raw)
    if values is None or len(values) != len(names):
        raise ValueError(f"{label}_FEATURE_DIMENSION_MISMATCH")
    return {
        name: _finite_number(value, f"{label}_{name}")
        for name, value in zip(names, values, strict=True)
    }


def _candidate_index(
    container: Mapping[str, Any],
    row: Mapping[str, Any],
    names: Sequence[str],
    *,
    default: int | None,
) -> int | None:
    raw = _first(container, names)
    if raw is None and container is not row:
        raw = _first(row, names)
    if raw is None:
        return default
    numeric = _finite_number(raw, names[0].upper())
    integer = int(numeric)
    if float(integer) != numeric:
        raise ValueError(f"{names[0].upper()}_MUST_BE_INTEGER")
    return integer


def _extract_candidate_pair(row: Mapping[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    raw_pair: Sequence[Any] | None = None
    baseline: Mapping[str, Any] | None = None
    treatment: Mapping[str, Any] | None = None
    pair_container: Mapping[str, Any] = row
    for container in _feature_containers(row):
        for key in ("candidate_features", "candidate_observations", "candidates"):
            raw_pair = _sequence(container.get(key))
            if raw_pair is not None:
                pair_container = container
                break
        if raw_pair is not None:
            break
        for baseline_key, treatment_key in (
            ("baseline_features", "treatment_features"),
            ("baseline_observation", "treatment_observation"),
            ("current_features", "alternative_features"),
        ):
            baseline = _mapping(container.get(baseline_key))
            treatment = _mapping(container.get(treatment_key))
            if baseline is not None and treatment is not None:
                pair_container = container
                break
        if baseline is not None and treatment is not None:
            break

    if raw_pair is not None:
        if len(raw_pair) < 2 or len(raw_pair) > 4:
            raise ValueError("CANDIDATE_SET_SIZE_MUST_BE_2_TO_4")
        baseline_index = _candidate_index(
            pair_container,
            row,
            ("baseline_candidate_index", "baseline_index"),
            default=0,
        )
        treatment_index = _candidate_index(
            pair_container,
            row,
            (
                "treatment_candidate_index",
                "alternative_candidate_index",
                "proposed_candidate_index",
                "proposed_index",
            ),
            default=1 if len(raw_pair) == 2 else None,
        )
        if baseline_index is None or treatment_index is None:
            raise ValueError("TREATMENT_CANDIDATE_INDEX_MISSING")
        if not 0 <= baseline_index < len(raw_pair) or not 0 <= treatment_index < len(raw_pair):
            raise ValueError("CANDIDATE_INDEX_OUT_OF_RANGE")
        if baseline_index == treatment_index:
            raise ValueError("TREATMENT_INDEX_EQUALS_BASELINE")
        baseline_raw = raw_pair[baseline_index]
        treatment_raw = raw_pair[treatment_index]
        baseline_mapping = _mapping(baseline_raw)
        treatment_mapping = _mapping(treatment_raw)
        if baseline_mapping is not None:
            baseline_mapping = _mapping(baseline_mapping.get("features")) or baseline_mapping
        if treatment_mapping is not None:
            treatment_mapping = _mapping(treatment_mapping.get("features")) or treatment_mapping
        baseline_is_full = baseline_mapping is not None and all(
            name in baseline_mapping for name in CANONICAL_OBSERVATION_FEATURES
        )
        treatment_is_full = treatment_mapping is not None and all(
            name in treatment_mapping for name in CANONICAL_OBSERVATION_FEATURES
        )
        if baseline_is_full and treatment_is_full:
            baseline, treatment = baseline_mapping, treatment_mapping
        else:
            context_raw: Any = None
            for key in (
                "context_features",
                "shared_context_features",
                "shared_context",
                "context",
            ):
                if key in pair_container:
                    context_raw = pair_container[key]
                    break
                if key in row:
                    context_raw = row[key]
                    break
            if context_raw is None:
                raise ValueError("SHARED_CONTEXT_FEATURES_MISSING")
            context = _ordered_feature_mapping(context_raw, CONTEXT_FEATURES, "CONTEXT")
            baseline = {
                **_ordered_feature_mapping(
                    baseline_raw, CANDIDATE_FEATURES, "BASELINE_CANDIDATE"
                ),
                **context,
            }
            treatment = {
                **_ordered_feature_mapping(
                    treatment_raw, CANDIDATE_FEATURES, "TREATMENT_CANDIDATE"
                ),
                **context,
            }

    if baseline is None or treatment is None:
        # CSV-friendly representation: baseline_<name>, treatment_<name>.
        flattened_baseline = {
            name: row[f"baseline_{name}"]
            for name in CANONICAL_OBSERVATION_FEATURES
            if f"baseline_{name}" in row
        }
        flattened_treatment = {
            name: row[f"treatment_{name}"]
            for name in CANONICAL_OBSERVATION_FEATURES
            if f"treatment_{name}" in row
        }
        if flattened_baseline and flattened_treatment:
            baseline, treatment = flattened_baseline, flattened_treatment

    if baseline is not None and treatment is not None:
        baseline_has_context = all(name in baseline for name in CONTEXT_FEATURES)
        treatment_has_context = all(name in treatment for name in CONTEXT_FEATURES)
        if not baseline_has_context or not treatment_has_context:
            context_raw = _first(
                pair_container,
                (
                    "context_features",
                    "shared_context_features",
                    "shared_context",
                    "context",
                ),
            )
            if context_raw is None and pair_container is not row:
                context_raw = _first(
                    row,
                    (
                        "context_features",
                        "shared_context_features",
                        "shared_context",
                        "context",
                    ),
                )
            if context_raw is not None:
                context = _ordered_feature_mapping(context_raw, CONTEXT_FEATURES, "CONTEXT")
                baseline = {**baseline, **context}
                treatment = {**treatment, **context}

    if baseline is None or treatment is None:
        raise ValueError("FEATURE_ROWS_MISSING_MATCHED_CANDIDATE_PAIR")
    projected_baseline = _project_observation(baseline, "BASELINE")
    projected_treatment = _project_observation(treatment, "TREATMENT")
    for name in CONTEXT_FEATURES:
        if not math.isclose(
            projected_baseline[name], projected_treatment[name], rel_tol=0.0, abs_tol=1e-9
        ):
            raise ValueError(f"CANDIDATE_CONTEXT_NOT_SHARED:{name}")
    return projected_baseline, projected_treatment


def _utility_scope_metadata(row: Mapping[str, Any]) -> tuple[str, bool]:
    raw_scope = str(row.get("utility_scope", "")).strip().upper()
    horizon = str(row.get("horizon", "")).strip().upper()
    if raw_scope.startswith("DIRECT_ONLY") or raw_scope == H_BAG_TRAINING_SCOPE:
        return H_BAG_TRAINING_SCOPE, False
    h_system = horizon == "H_SYSTEM" and raw_scope in {
        "SYSTEM_REALIZED_AFFECTED",
        H_SYSTEM_EVIDENCE_SCOPE,
        "FULL_SYSTEM_EXTERNALITY",
    }
    if h_system:
        return H_SYSTEM_EVIDENCE_SCOPE, True
    return raw_scope or "UNSCOPED_SYSTEM_UTILITY", False


def _extract_utility(row: Mapping[str, Any], utility_scope: str) -> float:
    if utility_scope == H_BAG_TRAINING_SCOPE:
        if not _bool_value(row.get("hard_gate_pass"), default=False):
            raise ValueError("H_BAG_HARD_GATE_REQUIRED")
        if not _bool_value(row.get("eligible_causal_effect"), default=False):
            raise ValueError("H_BAG_ELIGIBLE_CAUSAL_EFFECT_REQUIRED")
        if not _bool_value(row.get("action_changed"), default=False):
            raise ValueError("H_BAG_ACTION_CHANGE_REQUIRED")
        direct_count = _finite_number(row.get("direct_bag_count"), "DIRECT_BAG_COUNT")
        if direct_count != 2.0:
            raise ValueError("H_BAG_REQUIRES_TWO_DIRECT_AFFECTED_BAGS")
        direct_delta = _finite_number(
            row.get("direct_bag_tth_sum_delta_seconds"),
            "DIRECT_BAG_TTH_SUM_DELTA_SECONDS",
        )
        deadline_delta = _finite_number(row.get("deadline_miss_delta"), "DEADLINE_MISS_DELTA")
        bounded_utility = -(
            direct_delta
            + DEADLINE_MISS_PENALTY_SECONDS * max(0.0, deadline_delta)
        )
        reported = _first(
            row, ("system_utility", "system_utility_seconds", "effect_system_utility")
        )
        if reported is not None and not math.isclose(
            _finite_number(reported, "SYSTEM_UTILITY"),
            bounded_utility,
            rel_tol=0.0,
            abs_tol=1e-6,
        ):
            raise ValueError("H_BAG_BOUNDED_DIRECT_UTILITY_MISMATCH")
        return bounded_utility

    if utility_scope == H_SYSTEM_EVIDENCE_SCOPE:
        if not _bool_value(row.get("hard_gate_pass"), default=False):
            raise ValueError("H_SYSTEM_HARD_GATE_REQUIRED")
        if not _bool_value(row.get("eligible_causal_effect"), default=False):
            raise ValueError("H_SYSTEM_ELIGIBLE_CAUSAL_EFFECT_REQUIRED")
        if not _bool_value(row.get("action_changed"), default=False):
            raise ValueError("H_SYSTEM_ACTION_CHANGE_REQUIRED")
        other_count = _finite_number(row.get("other_bag_count"), "OTHER_BAG_COUNT")
        if other_count < 0.0 or other_count != float(int(other_count)):
            raise ValueError("H_SYSTEM_OTHER_BAG_COUNT_INVALID")
        _finite_number(row.get("other_bag_sum_delta_seconds"), "OTHER_BAG_SUM_DELTA_SECONDS")
        tail_harm = _finite_number(
            row.get("other_bag_cvar95_harm_seconds"),
            "OTHER_BAG_CVAR95_HARM_SECONDS",
        )
        if tail_harm < 0.0:
            raise ValueError("H_SYSTEM_TAIL_HARM_NEGATIVE")

    direct = _first(row, ("system_utility", "system_utility_seconds", "effect_system_utility"))
    if direct is not None:
        return _finite_number(direct, "SYSTEM_UTILITY")
    effects = _mapping(row.get("effects"))
    if effects is not None:
        direct = _first(effects, ("system_utility", "system_utility_seconds"))
        if direct is not None:
            return _finite_number(direct, "SYSTEM_UTILITY")
        source = effects
    else:
        source = row
    own = _first(source, ("own_bag_effect_seconds", "own_effect_seconds"))
    external = _sequence(
        _first(source, ("bounded_external_bag_effects_seconds", "external_effects_seconds"))
    )
    if own is None or external is None:
        raise ValueError("SYSTEM_UTILITY_LABEL_MISSING")
    return system_utility(
        _finite_number(own, "OWN_BAG_EFFECT"),
        [_finite_number(value, "EXTERNAL_BAG_EFFECT") for value in external],
        tail_harm_penalty_seconds=_finite_number(
            source.get("tail_harm_penalty_seconds", 0.0), "TAIL_HARM_PENALTY"
        ),
        deadline_risk_seconds=_finite_number(
            source.get("deadline_risk_seconds", 0.0), "DEADLINE_RISK"
        ),
        starvation_penalty_seconds=_finite_number(
            source.get("starvation_penalty_seconds", 0.0), "STARVATION_PENALTY"
        ),
    )


def _bucket_queue(utilization: float) -> str:
    if utilization < 0.50:
        return "queue_lt_0.50"
    if utilization < 0.75:
        return "queue_0.50_0.75"
    if utilization < 0.90:
        return "queue_0.75_0.90"
    return "queue_ge_0.90"


def _bucket_slack(slack: float) -> str:
    if slack < 0.0:
        return "slack_negative"
    if slack < 30.0:
        return "slack_0_30s"
    if slack < 120.0:
        return "slack_30_120s"
    return "slack_ge_120s"


def _split_metadata(row: Mapping[str, Any]) -> _SplitMetadata:
    task_group_value = _first(
        row,
        (
            "task_group",
            "task_group_id",
            "task_id",
            "bag_id",
            "descriptor_id",
            "target_key",
        ),
    )
    source_group_value = _first(
        row, ("source_group", "source_node", "source_id", "source", "wait_source_node")
    )
    timestamp_value = _first(
        row,
        (
            "event_time",
            "timestamp",
            "decision_time",
            "t0",
            "decision_time_seconds",
            "event_ordinal",
        ),
    )
    if task_group_value is None:
        raise ValueError("TASK_GROUP_SPLIT_KEY_MISSING")
    if source_group_value is None:
        raise ValueError("SOURCE_GROUP_DIAGNOSTIC_KEY_MISSING")
    if timestamp_value is None:
        raise ValueError("TIMESTAMP_DIAGNOSTIC_KEY_MISSING")
    return _SplitMetadata(
        task_group=str(task_group_value),
        source_group=str(source_group_value),
        timestamp=_finite_number(timestamp_value, "TIMESTAMP"),
    )


def _utility_label_is_present(row: Mapping[str, Any]) -> bool:
    if any(key in row for key in ("system_utility", "system_utility_seconds", "effect_system_utility")):
        return True
    effects = _mapping(row.get("effects"))
    source = effects if effects is not None else row
    if any(key in source for key in ("system_utility", "system_utility_seconds")):
        return True
    if (
        "direct_bag_tth_sum_delta_seconds" in source
        and "deadline_miss_delta" in source
        and "direct_bag_count" in source
    ):
        return True
    return (
        any(key in source for key in ("own_bag_effect_seconds", "own_effect_seconds"))
        and any(
            key in source
            for key in ("bounded_external_bag_effects_seconds", "external_effects_seconds")
        )
    )


def _prepare_row(
    row: Mapping[str, Any],
    ordinal: int,
    *,
    metadata: _SplitMetadata,
    consume_utility: bool,
) -> _PreparedRow:
    if "eligible_causal_effect" in row and not _bool_value(row.get("eligible_causal_effect")):
        raise ValueError("CAUSAL_EFFECT_NOT_ELIGIBLE")
    if "hard_gate_pass" in row and not _bool_value(row.get("hard_gate_pass")):
        raise ValueError("CAUSAL_EFFECT_HARD_GATE_FAILED")
    if "action_changed" in row and not _bool_value(row.get("action_changed")):
        raise ValueError("ALTERNATIVE_ACTION_NOT_CHANGED")
    utility_scope, h_system_evidence = _utility_scope_metadata(row)
    if consume_utility and str(row.get("effect_label", "")).upper() == "EXCLUDED":
        raise ValueError("CAUSAL_EFFECT_EXCLUDED")
    baseline, treatment = _extract_candidate_pair(row)
    if not _utility_label_is_present(row):
        raise ValueError("SYSTEM_UTILITY_LABEL_MISSING")
    utility = _extract_utility(row, utility_scope) if consume_utility else None
    legal_raw = _sequence(row.get("legal_mask"))
    legal = (True, True) if legal_raw is None else tuple(_bool_value(value) for value in legal_raw)
    if len(legal) != 2 or legal != (True, True):
        raise ValueError("MATCHED_TRAINING_PAIR_REQUIRES_TWO_LEGAL_CANDIDATES")
    supervisor = _bool_value(
        _first(row, ("supervisor_authorized", "hard_gate_pass", "pair_hard_gate_pass")),
        default=False,
    )
    context = {name: treatment[name] for name in CONTEXT_FEATURES}
    left = {name: treatment[name] for name in CANDIDATE_FEATURES}
    right = {name: baseline[name] for name in CANDIDATE_FEATURES}
    pairwise = pairwise_feature_vector(left, right, context)
    candidate_matrix = np.stack(
        [canonical_feature_vector(baseline), canonical_feature_vector(treatment)], axis=0
    )
    leg_value = _first(row, ("leg", "bag_leg", "leg_bucket", "leg_type"))
    leg = str(leg_value if leg_value is not None else int(treatment["candidate_leg_priority"]))
    explicit_time_bucket = _first(row, ("time_bucket", "release_time_bucket"))
    time_bucket = str(
        explicit_time_bucket
        if explicit_time_bucket is not None
        else math.floor(metadata.timestamp / 3_600.0)
    )
    queue_bucket_value = _first(row, ("queue_bucket", "source_queue_bucket"))
    slack_bucket_value = _first(row, ("slack_bucket", "deadline_slack_bucket"))
    return _PreparedRow(
        task_group=metadata.task_group,
        source_group=metadata.source_group,
        timestamp=metadata.timestamp,
        leg=leg,
        time_bucket=time_bucket,
        queue_bucket=str(
            queue_bucket_value
            if queue_bucket_value is not None
            else _bucket_queue(treatment["source_queue_utilization"])
        ),
        slack_bucket=str(
            slack_bucket_value
            if slack_bucket_value is not None
            else _bucket_slack(treatment["candidate_deadline_slack_seconds"])
        ),
        utility_seconds=utility,
        utility_scope=utility_scope,
        h_system_externality_evidence=h_system_evidence,
        candidate_observations=(baseline, treatment),
        candidate_matrix=candidate_matrix,
        pairwise_vector=pairwise,
        legal_mask=(True, True),
        supervisor_authorized=supervisor,
    )


def _prepare_rows(
    rows: Iterable[Mapping[str, Any]],
    config: PhaseDTrainingConfig,
) -> tuple[list[_PreparedRow], dict[str, Any], DiagnosticSplits | None]:
    prepared: list[_PreparedRow] = []
    rejected: Counter[str] = Counter()
    input_count = 0
    metadata_rows: list[tuple[int, Mapping[str, Any], _SplitMetadata]] = []
    for ordinal, row in enumerate(rows):
        input_count += 1
        if not isinstance(row, Mapping):
            rejected["ROW_NOT_OBJECT"] += 1
            continue
        try:
            metadata = _split_metadata(row)
        except ValueError as exc:
            reason = str(exc).split(":", 1)[0] or exc.__class__.__name__
            rejected[reason] += 1
            continue
        metadata_rows.append((ordinal, row, metadata))

    if metadata_rows:
        preliminary = make_diagnostic_splits(
            [item[2].source_group for item in metadata_rows],
            [item[2].timestamp for item in metadata_rows],
            [item[2].task_group for item in metadata_rows],
            seed=config.seed,
            time_block_seconds=config.time_block_seconds,
            fractions=config.split_fractions,
            model_feature_names=PAIRWISE_FEATURES,
        )
    else:
        preliminary = None
    kept_task: list[str] = []
    kept_source: list[str] = []
    kept_time: list[str] = []
    if preliminary is not None:
        for position, (ordinal, row, metadata) in enumerate(metadata_rows):
            task_assignment = preliminary.task_group[position]
            try:
                candidate = _prepare_row(
                    row,
                    ordinal,
                    metadata=metadata,
                    consume_utility=task_assignment != "final_audit",
                )
            except (ValueError, LocalFeatureError) as exc:
                reason = str(exc).split(":", 1)[0] or exc.__class__.__name__
                rejected[reason] += 1
                continue
            # Keep the configured neutral band out of support labels without
            # changing the real-valued utility used by ranking metrics.
            if (
                candidate.utility_seconds is not None
                and abs(candidate.utility_seconds) <= config.utility_tolerance_seconds
            ):
                candidate = _PreparedRow(
                    **{**candidate.__dict__, "utility_seconds": 0.0}
                )
            prepared.append(candidate)
            kept_task.append(task_assignment)
            kept_source.append(preliminary.source_held_out[position])
            kept_time.append(preliminary.time_held_out[position])
    splits = (
        DiagnosticSplits(
            task_group=tuple(kept_task),
            source_held_out=tuple(kept_source),
            time_held_out=tuple(kept_time),
        )
        if kept_task
        else None
    )
    return prepared, {
        "input_row_count": input_count,
        "valid_feature_effect_row_count": len(prepared),
        "rejected_row_count": input_count - len(prepared),
        "rejection_reasons": dict(sorted(rejected.items())),
        "candidate_count_per_row": 2,
        "baseline_candidate_index": 0,
        "alternative_candidate_index": 1,
        "ids_used_as_model_features": False,
        "final_audit_outcomes_parsed": False,
    }, splits


def _split_counts(rows: Sequence[_PreparedRow], assignments: Sequence[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for split in ("train", "calibration", "validation", "final_audit"):
        members = [row for row, assigned in zip(rows, assignments, strict=True) if assigned == split]
        sealed = split == "final_audit"
        result[split] = {
            "row_count": len(members),
            "beneficial_count": (
                None if sealed else sum(row.utility_seconds is not None and row.utility_seconds > 0.0 for row in members)
            ),
            "harmful_count": (
                None if sealed else sum(row.utility_seconds is not None and row.utility_seconds < 0.0 for row in members)
            ),
            "neutral_count": (
                None if sealed else sum(row.utility_seconds == 0.0 for row in members)
            ),
            "task_group_count": len({row.task_group for row in members}),
            "source_group_count": len({row.source_group for row in members}),
            "utility_scope_counts": dict(
                sorted(Counter(row.utility_scope for row in members).items())
            ),
            "h_system_externality_evidence_count": sum(
                row.h_system_externality_evidence for row in members
            ),
        }
    return result


def _support_summary(
    rows: Sequence[_PreparedRow],
    assignments: Sequence[str],
    config: PhaseDTrainingConfig,
) -> dict[str, Any]:
    counts = _split_counts(rows, assignments)
    development_beneficial = [
        row
        for row, split in zip(rows, assignments, strict=True)
        if split != "final_audit" and row.utility_seconds > 0.0
    ]
    development_harmful = [
        row
        for row, split in zip(rows, assignments, strict=True)
        if split != "final_audit" and row.utility_seconds < 0.0
    ]
    observed = {
        "beneficial_train": counts["train"]["beneficial_count"],
        "beneficial_calibration": counts["calibration"]["beneficial_count"],
        "beneficial_validation": counts["validation"]["beneficial_count"],
        "harmful_train": counts["train"]["harmful_count"],
        "harmful_calibration": counts["calibration"]["harmful_count"],
        "harmful_validation": counts["validation"]["harmful_count"],
        "beneficial_sources": len({row.source_group for row in development_beneficial}),
        "beneficial_time_buckets": len({row.time_bucket for row in development_beneficial}),
        "beneficial_legs": len({row.leg for row in development_beneficial}),
        "harmful_sources": len({row.source_group for row in development_harmful}),
        "harmful_time_buckets": len({row.time_bucket for row in development_harmful}),
        "harmful_legs": len({row.leg for row in development_harmful}),
        "h_bag_training_rows": sum(
            row.utility_scope == H_BAG_TRAINING_SCOPE
            for row, split in zip(rows, assignments, strict=True)
            if split != "final_audit"
        ),
        "h_system_externality_rows": sum(
            row.h_system_externality_evidence
            for row, split in zip(rows, assignments, strict=True)
            if split != "final_audit"
        ),
    }
    required = {
        "beneficial_train": config.minimum_beneficial_train,
        "beneficial_calibration": config.minimum_beneficial_calibration,
        "beneficial_validation": config.minimum_beneficial_validation,
        "harmful_train": config.minimum_harmful_train,
        "harmful_calibration": config.minimum_harmful_calibration,
        "harmful_validation": config.minimum_harmful_validation,
        "beneficial_sources": config.minimum_beneficial_sources,
        "beneficial_time_buckets": config.minimum_beneficial_time_buckets,
        "beneficial_legs": config.minimum_beneficial_legs,
    }
    checks = {name: observed[name] >= minimum for name, minimum in required.items()}
    return {
        "by_selection_split": counts,
        "observed": observed,
        "required": required,
        "checks": checks,
        "pass": all(checks.values()),
    }


def _indices(assignments: Sequence[str], split: str) -> list[int]:
    return [index for index, assigned in enumerate(assignments) if assigned == split]


def _bootstrap_indices(
    rows: Sequence[_PreparedRow], train_indices: Sequence[int], rng: np.random.Generator
) -> list[int]:
    grouped: dict[str, list[int]] = {}
    for index in train_indices:
        grouped.setdefault(rows[index].task_group, []).append(index)
    groups = sorted(grouped)
    sampled = rng.choice(groups, size=len(groups), replace=True)
    return [index for group in sampled for index in grouped[str(group)]]


def _platt_dict(calibrator: PlattCalibrator) -> dict[str, Any]:
    return {
        "family": "platt_logistic",
        "slope": calibrator.slope,
        "intercept": calibrator.intercept,
        "fit_partition": "task_group.calibration",
    }


def _envelope_dict(envelope: FeatureEnvelope) -> dict[str, Any]:
    return {
        "family": "quantile_feature_envelope",
        "feature_names": list(envelope.feature_names),
        "lower": envelope.lower.tolist(),
        "upper": envelope.upper.tolist(),
        "fit_partition": "task_group.train",
        "identity_features_used": False,
    }


def _localized_choice(row: _PreparedRow, rule: LocalizedThesisPriority) -> int:
    candidates = []
    for observation in row.candidate_observations:
        candidates.append(
            LocalPriorityCandidate(
                local_rank=int(round(observation["candidate_local_rank"])),
                deadline_slack_seconds=observation["candidate_deadline_slack_seconds"],
                wait_age_seconds=observation["candidate_wait_age_seconds"],
                leg_priority=int(round(observation["candidate_leg_priority"])),
                repair_priority=bool(observation["candidate_repair_priority"] >= 0.5),
                legal=True,
            )
        )
    return rule.choose(candidates).chosen_index


def _ensemble_probabilities(
    row: _PreparedRow,
    benefit_models: Sequence[PairwiseLinearRanker],
    harm_models: Sequence[PairwiseLinearRanker],
    benefit_calibrators: Sequence[PlattCalibrator],
    harm_calibrators: Sequence[PlattCalibrator],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    benefit = tuple(
        float(calibrator.predict(model.decision_function(row.pairwise_vector)))
        for model, calibrator in zip(benefit_models, benefit_calibrators, strict=True)
    )
    harm = tuple(
        float(calibrator.predict(model.decision_function(row.pairwise_vector)))
        for model, calibrator in zip(harm_models, harm_calibrators, strict=True)
    )
    return benefit, harm


def _policy_panel(
    rows: Sequence[_PreparedRow],
    indices: Sequence[int],
    *,
    benefit_models: Sequence[PairwiseLinearRanker],
    harm_models: Sequence[PairwiseLinearRanker],
    utility_models: Sequence[LinearUtilityRegressor],
    benefit_calibrators: Sequence[PlattCalibrator],
    harm_calibrators: Sequence[PlattCalibrator],
    utility_residual_q05_seconds: float,
    mlp: TinyMLPListwiseRanker,
    envelope: FeatureEnvelope,
    selector: ConservativeSelectiveOverride,
    calibration_ece: float,
) -> tuple[dict[str, Any], dict[str, Any], list[bool], list[int], list[str], list[bool]]:
    subset = [rows[index] for index in indices]
    family_choices: dict[str, list[int]] = {
        "FIFO": [],
        "CURRENT_AGING_Q0": [],
        "LOCALIZED_THESIS_RULE": [],
        "PAIRWISE_LINEAR": [],
        "TINY_MLP": [],
        "SELECTIVE_GATE": [],
    }
    activations: list[bool] = []
    gate_reasons: list[str] = []
    ood_flags: list[bool] = []
    rule = LocalizedThesisPriority()
    for row in subset:
        ranks = [
            observation["candidate_local_rank"] for observation in row.candidate_observations
        ]
        family_choices["FIFO"].append(fifo_baseline(ranks, row.legal_mask).chosen_index)
        family_choices["CURRENT_AGING_Q0"].append(0)
        family_choices["LOCALIZED_THESIS_RULE"].append(_localized_choice(row, rule))
        benefit_probabilities, harm_probabilities = _ensemble_probabilities(
            row,
            benefit_models,
            harm_models,
            benefit_calibrators,
            harm_calibrators,
        )
        pairwise_choice = int(float(np.mean(benefit_probabilities)) >= 0.5)
        family_choices["PAIRWISE_LINEAR"].append(pairwise_choice)
        family_choices["TINY_MLP"].append(mlp.choose(row.candidate_matrix, row.legal_mask))
        ood = envelope.is_ood(row.pairwise_vector)
        ood_flags.append(ood)
        utility_samples = tuple(
            float(model.predict(row.pairwise_vector)) + utility_residual_q05_seconds
            for model in utility_models
        )
        decision = selector.decide(
            0,
            OverrideEvidence(
                proposed_index=pairwise_choice,
                calibrated_benefit_probabilities=benefit_probabilities,
                calibrated_harm_probabilities=harm_probabilities,
                utility_samples_seconds=utility_samples,
                calibration_ece=calibration_ece,
                ood=ood,
                supervisor_authorized=row.supervisor_authorized,
            ),
        )
        family_choices["SELECTIVE_GATE"].append(decision.chosen_index)
        activations.append(decision.activated)
        gate_reasons.append(decision.reason)

    candidate_utilities = [[0.0, row.utility_seconds] for row in subset]
    evaluation = evaluate_policy_families(
        candidate_utilities,
        family_choices,
        baseline_indices=[0] * len(subset),
        legal_masks=[row.legal_mask for row in subset],
    )
    selective = selective_override_metrics(
        [row.utility_seconds for row in subset], activations
    )
    selective["reason_counts"] = dict(sorted(Counter(gate_reasons).items()))
    selective["ood_row_count"] = sum(ood_flags)
    selective["ood_activation_count"] = sum(
        ood and active for ood, active in zip(ood_flags, activations, strict=True)
    )
    return evaluation, selective, activations, family_choices["SELECTIVE_GATE"], gate_reasons, ood_flags


def _label_contract() -> dict[str, Any]:
    return {
        H_BAG_TRAINING_SCOPE: {
            "eligible_for_training_and_calibration": True,
            "definition": (
                "-(two direct affected bags' TTH delta sum + "
                "3600s * max(0, deadline miss delta))"
            ),
            "required_direct_bag_count": 2,
            "deadline_miss_penalty_seconds": DEADLINE_MISS_PENALTY_SECONDS,
            "provides_full_system_externality_evidence": False,
            "can_authorize_runtime_closed_loop": False,
        },
        H_SYSTEM_EVIDENCE_SCOPE: {
            "eligible_for_training_and_calibration": True,
            "provides_full_system_externality_evidence": True,
            "required_for_offline_shadow_authorization": True,
            "can_authorize_runtime_closed_loop": False,
        },
    }


def _empty_result(
    *,
    status: str,
    reasons: Sequence[str],
    config: PhaseDTrainingConfig,
    input_summary: dict[str, Any],
    split_summary: dict[str, Any] | None = None,
    support: dict[str, Any] | None = None,
    diagnostic_splits: DiagnosticSplits | None = None,
) -> PhaseDTrainingResult:
    split_payload = split_summary or {
        "selection_view": "task_group",
        "task_group_overlap_count": 0,
        "final_audit": {"row_count": 0, "consumed": False},
    }
    support_payload = support or {
        "by_selection_split": {},
        "observed": {},
        "required": {},
        "checks": {},
        "pass": False,
    }
    policy = {
        "schema": POLICY_SCHEMA,
        "status": status,
        "authorized": False,
        "reason_codes": list(reasons),
        "families_compared": [
            "FIFO",
            "CURRENT_AGING_Q0",
            "LOCALIZED_THESIS_RULE",
            "PAIRWISE_LINEAR",
            "TINY_MLP",
            "SELECTIVE_GATE",
        ],
        "validation_evaluation": {},
        "diagnostics": {},
        "final_audit": {"consumed": False},
    }
    gate = {
        "schema": GATE_SCHEMA,
        "status": status,
        "authorized": False,
        "authorization_scope": "offline_candidate_for_supervised_shadow",
        "runtime_closed_loop_authorized": False,
        "reason_codes": list(reasons),
        "training_config": config.to_dict(),
        "training_label_contract": _label_contract(),
        "input_summary": input_summary,
        "support": support_payload,
        "calibration": {"available": False},
        "promotion_checks": {},
        "final_audit": {"consumed": False},
        "identity_features_used": False,
    }
    report = _render_report(
        status=status,
        authorized=False,
        reasons=reasons,
        input_summary=input_summary,
        split_summary=split_payload,
        support=support_payload,
        calibration={"available": False},
        validation={},
        diagnostics={},
        buckets={},
        checks={},
    )
    return PhaseDTrainingResult(
        status=status,
        authorized=False,
        reasons=tuple(reasons),
        config=config,
        input_summary=input_summary,
        split_summary=split_payload,
        support=support_payload,
        calibration={"available": False},
        validation_evaluation={},
        diagnostics={},
        buckets={},
        model_artifacts={},
        policy_artifact=policy,
        gate_artifact=gate,
        report_markdown=report,
        diagnostic_splits=diagnostic_splits,
    )


def train_phase_d(
    rows: Iterable[Mapping[str, Any]],
    *,
    config: PhaseDTrainingConfig | None = None,
) -> PhaseDTrainingResult:
    """Train/evaluate G17 I1 without ever consuming the final-audit outcomes."""

    settings = config or PhaseDTrainingConfig()
    prepared, input_summary, splits = _prepare_rows(rows, settings)
    if not prepared:
        return _empty_result(
            status="NO_GO_FEATURE_EFFECT_ROWS_ABSENT",
            reasons=("NO_VALID_MATCHED_FEATURE_EFFECT_ROWS",),
            config=settings,
            input_summary=input_summary,
        )

    if splits is None:  # Kept as a defensive invariant, not an evidence gate.
        raise RuntimeError("PREPARED_ROWS_WITHOUT_SPLIT_ASSIGNMENTS")
    split_counts = _split_counts(prepared, splits.task_group)
    split_summary = {
        "selection_view": splits.selection_view,
        "diagnostic_views": ["source_held_out", "time_held_out"],
        "task_group_overlap_count": group_overlap_count(
            [row.task_group for row in prepared], splits.task_group
        ),
        "by_selection_split": split_counts,
        "final_audit": {
            "row_count": split_counts["final_audit"]["row_count"],
            "consumed": False,
        },
        "split_keys_are_model_inputs": False,
    }
    support = _support_summary(prepared, splits.task_group, settings)
    train_indices = _indices(splits.task_group, "train")
    calibration_indices = _indices(splits.task_group, "calibration")
    validation_indices = _indices(splits.task_group, "validation")
    basic_reasons: list[str] = []
    if not train_indices:
        basic_reasons.append("TRAIN_PARTITION_EMPTY")
    if not calibration_indices:
        basic_reasons.append("CALIBRATION_PARTITION_EMPTY")
    if not validation_indices:
        basic_reasons.append("VALIDATION_PARTITION_EMPTY")
    if basic_reasons:
        return _empty_result(
            status="NO_GO_INSUFFICIENT_SPLIT_SUPPORT",
            reasons=basic_reasons,
            config=settings,
            input_summary=input_summary,
            split_summary=split_summary,
            support=support,
            diagnostic_splits=splits,
        )

    train_matrix = np.stack([prepared[index].pairwise_vector for index in train_indices])
    train_candidates = np.stack([prepared[index].candidate_matrix for index in train_indices])
    train_benefit = np.asarray(
        [prepared[index].utility_seconds > settings.utility_tolerance_seconds for index in train_indices],
        dtype=np.float64,
    )
    train_targets = np.asarray(train_benefit, dtype=np.int64)
    benefit_models: list[PairwiseLinearRanker] = []
    harm_models: list[PairwiseLinearRanker] = []
    utility_models: list[LinearUtilityRegressor] = []
    rng = np.random.default_rng(settings.seed)
    for _ in range(settings.ensemble_size):
        sampled_indices = _bootstrap_indices(prepared, train_indices, rng)
        sampled_matrix = np.stack([prepared[index].pairwise_vector for index in sampled_indices])
        sampled_benefit = [
            int(prepared[index].utility_seconds > settings.utility_tolerance_seconds)
            for index in sampled_indices
        ]
        sampled_harm = [
            int(prepared[index].utility_seconds < -settings.utility_tolerance_seconds)
            for index in sampled_indices
        ]
        sampled_utility = [prepared[index].utility_seconds for index in sampled_indices]
        benefit_models.append(
            PairwiseLinearRanker.fit(
                sampled_matrix,
                sampled_benefit,
                feature_names=PAIRWISE_FEATURES,
                l2=settings.pairwise_l2,
                epochs=settings.pairwise_epochs,
                learning_rate=settings.pairwise_learning_rate,
            )
        )
        harm_models.append(
            PairwiseLinearRanker.fit(
                sampled_matrix,
                sampled_harm,
                feature_names=PAIRWISE_FEATURES,
                l2=settings.pairwise_l2,
                epochs=settings.pairwise_epochs,
                learning_rate=settings.pairwise_learning_rate,
            )
        )
        utility_models.append(
            LinearUtilityRegressor.fit(
                sampled_matrix,
                sampled_utility,
                feature_names=PAIRWISE_FEATURES,
                l2=settings.utility_l2,
            )
        )

    mlp = TinyMLPListwiseRanker.fit(
        train_candidates,
        train_targets,
        feature_names=CANONICAL_OBSERVATION_FEATURES,
        legal_masks=np.ones((len(train_indices), 2), dtype=bool),
        hidden_dim=settings.mlp_hidden_dim,
        epochs=settings.mlp_epochs,
        learning_rate=settings.mlp_learning_rate,
        l2=settings.mlp_l2,
        seed=settings.seed,
    )
    envelope = FeatureEnvelope.fit(train_matrix, feature_names=PAIRWISE_FEATURES)

    calibration_rows = [prepared[index] for index in calibration_indices]
    calibration_benefit_labels = [
        int(row.utility_seconds > settings.utility_tolerance_seconds) for row in calibration_rows
    ]
    calibration_harm_labels = [
        int(row.utility_seconds < -settings.utility_tolerance_seconds) for row in calibration_rows
    ]
    if len(set(calibration_benefit_labels)) < 2 or len(set(calibration_harm_labels)) < 2:
        artifact_set_id = _new_artifact_set_id(settings, len(prepared))
        model_artifacts = {
            "pairwise_linear": {
                "schema": PAIRWISE_MODEL_SCHEMA,
                "artifact_set_id": artifact_set_id,
                "status": "TRAINED_UNCALIBRATED",
                "benefit_members": [model.to_dict() for model in benefit_models],
                "harm_members": [model.to_dict() for model in harm_models],
                "utility_members": [model.to_dict() for model in utility_models],
                "fit_partition": "task_group.train",
                "calibration_partition": "task_group.calibration",
                "calibration_available": False,
                "training_config": settings.to_dict(),
                "training_label_contract": _label_contract(),
                "final_audit_consumed": False,
                "identity_features_used": False,
            },
            "tiny_mlp": {
                "schema": MLP_MODEL_SCHEMA,
                "artifact_set_id": artifact_set_id,
                "status": "TRAINED_DIAGNOSTIC_ONLY",
                "model": mlp.to_dict(),
                "fit_partition": "task_group.train",
                "training_config": settings.to_dict(),
                "training_label_contract": _label_contract(),
                "final_audit_consumed": False,
                "identity_features_used": False,
            },
        }
        result = _empty_result(
            status="NO_GO_CALIBRATION_CLASS_SUPPORT",
            reasons=("CALIBRATION_REQUIRES_BENEFICIAL_AND_HARMFUL_ROWS",),
            config=settings,
            input_summary=input_summary,
            split_summary=split_summary,
            support=support,
            diagnostic_splits=splits,
        )
        gate_artifact = {
            **result.gate_artifact,
            "artifact_set_id": artifact_set_id,
        }
        policy_artifact = {
            **result.policy_artifact,
            "artifact_set_id": artifact_set_id,
        }
        return PhaseDTrainingResult(
            **{
                **result.__dict__,
                "model_artifacts": model_artifacts,
                "policy_artifact": policy_artifact,
                "gate_artifact": gate_artifact,
            }
        )

    benefit_calibrators: list[PlattCalibrator] = []
    harm_calibrators: list[PlattCalibrator] = []
    for benefit_model, harm_model in zip(benefit_models, harm_models, strict=True):
        benefit_calibrators.append(
            PlattCalibrator.fit(
                [benefit_model.decision_function(row.pairwise_vector) for row in calibration_rows],
                calibration_benefit_labels,
                epochs=settings.calibrator_epochs,
            )
        )
        harm_calibrators.append(
            PlattCalibrator.fit(
                [harm_model.decision_function(row.pairwise_vector) for row in calibration_rows],
                calibration_harm_labels,
                epochs=settings.calibrator_epochs,
            )
        )
    calibration_benefit_probabilities: list[float] = []
    calibration_harm_probabilities: list[float] = []
    for row in calibration_rows:
        benefits, harms = _ensemble_probabilities(
            row,
            benefit_models,
            harm_models,
            benefit_calibrators,
            harm_calibrators,
        )
        calibration_benefit_probabilities.append(float(np.mean(benefits)))
        calibration_harm_probabilities.append(float(np.mean(harms)))
    calibration = {
        "available": True,
        **calibration_metrics(
            calibration_benefit_probabilities,
            calibration_benefit_labels,
            calibration_harm_probabilities,
            calibration_harm_labels,
        ),
        "row_count": len(calibration_rows),
        "beneficial_count": sum(calibration_benefit_labels),
        "harmful_count": sum(calibration_harm_labels),
        "fit_partition": "task_group.calibration",
    }
    calibration_fit_ece = max(calibration["benefit_ece"], calibration["harm_ece"])
    utility_residuals = []
    for row in calibration_rows:
        prediction = float(
            np.mean([model.predict(row.pairwise_vector) for model in utility_models])
        )
        utility_residuals.append(row.utility_seconds - prediction)
    utility_residual_q05 = float(np.quantile(utility_residuals, 0.05))
    calibration["utility_residual_q05_seconds"] = utility_residual_q05

    selector = ConservativeSelectiveOverride(
        benefit_probability_lcb_min=settings.benefit_probability_lcb_min,
        harm_probability_ucb_max=settings.harm_probability_ucb_max,
        utility_lcb_min_seconds=settings.minimum_activated_utility_seconds,
        calibration_ece_max=settings.maximum_calibration_ece,
        min_ensemble_size=settings.ensemble_size,
    )
    validation_evaluation, validation_selective, activations, _, _, validation_ood = _policy_panel(
        prepared,
        validation_indices,
        benefit_models=benefit_models,
        harm_models=harm_models,
        utility_models=utility_models,
        benefit_calibrators=benefit_calibrators,
        harm_calibrators=harm_calibrators,
        utility_residual_q05_seconds=utility_residual_q05,
        mlp=mlp,
        envelope=envelope,
        selector=selector,
        calibration_ece=calibration_fit_ece,
    )
    validation_rows = [prepared[index] for index in validation_indices]
    validation_benefit_probabilities: list[float] = []
    validation_harm_probabilities: list[float] = []
    for row in validation_rows:
        benefit_probabilities, harm_probabilities = _ensemble_probabilities(
            row,
            benefit_models,
            harm_models,
            benefit_calibrators,
            harm_calibrators,
        )
        validation_benefit_probabilities.append(float(np.mean(benefit_probabilities)))
        validation_harm_probabilities.append(float(np.mean(harm_probabilities)))
    validation_calibration = calibration_metrics(
        validation_benefit_probabilities,
        [
            int(row.utility_seconds is not None and row.utility_seconds > settings.utility_tolerance_seconds)
            for row in validation_rows
        ],
        validation_harm_probabilities,
        [
            int(row.utility_seconds is not None and row.utility_seconds < -settings.utility_tolerance_seconds)
            for row in validation_rows
        ],
    )
    validation_calibration_ece = max(
        validation_calibration["benefit_ece"], validation_calibration["harm_ece"]
    )
    calibration["validation_evaluation"] = {
        **validation_calibration,
        "row_count": len(validation_rows),
        "partition": "task_group.validation",
    }
    calibration["promotion_ece"] = max(calibration_fit_ece, validation_calibration_ece)
    validation_evaluation["selective_metrics"] = validation_selective
    validation_evaluation["ood"] = {
        "row_count": sum(validation_ood),
        "rate": float(np.mean(validation_ood)),
        "activation_count": validation_selective["ood_activation_count"],
        "envelope_fit_partition": "task_group.train",
    }
    validation_evaluation["partition"] = "task_group.validation"

    diagnostics: dict[str, Any] = {}
    for view_name, assignments in (
        ("source_held_out", splits.source_held_out),
        ("time_held_out", splits.time_held_out),
    ):
        # Intersect with the untouched task-group validation set so a second
        # view never exposes train/calibration or final-audit outcomes.  The
        # fitted model still uses the task-group selection view; therefore we
        # report entity overlap with task-train rather than mislabeling this
        # descriptive slice as a separately refitted source/time model.
        diagnostic_indices = [
            index
            for index in validation_indices
            if assignments[index] == "validation"
        ]
        if view_name == "source_held_out":
            diagnostic_entities = {prepared[index].source_group for index in diagnostic_indices}
            train_entities = {prepared[index].source_group for index in train_indices}
        else:
            diagnostic_entities = {
                math.floor(prepared[index].timestamp / settings.time_block_seconds)
                for index in diagnostic_indices
            }
            train_entities = {
                math.floor(prepared[index].timestamp / settings.time_block_seconds)
                for index in train_indices
            }
        entity_overlap = len(diagnostic_entities & train_entities)
        if diagnostic_indices:
            evaluation, selective, _, _, _, diagnostic_ood = _policy_panel(
                prepared,
                diagnostic_indices,
                benefit_models=benefit_models,
                harm_models=harm_models,
                utility_models=utility_models,
                benefit_calibrators=benefit_calibrators,
                harm_calibrators=harm_calibrators,
                utility_residual_q05_seconds=utility_residual_q05,
                mlp=mlp,
                envelope=envelope,
                selector=selector,
                calibration_ece=calibration_fit_ece,
            )
            diagnostics[view_name] = {
                "row_count": len(diagnostic_indices),
                "evaluation": evaluation,
                "selective_metrics": selective,
                "ood_rate": float(np.mean(diagnostic_ood)),
                "selection_validation_intersection": True,
                "model_fit_view": "task_group.train",
                "entity_overlap_with_model_train_count": entity_overlap,
                "strict_entity_holdout": entity_overlap == 0,
            }
        else:
            diagnostics[view_name] = {
                "row_count": 0,
                "status": "INSUFFICIENT_INTERSECTION_SUPPORT",
                "selection_validation_intersection": True,
                "model_fit_view": "task_group.train",
                "entity_overlap_with_model_train_count": 0,
                "strict_entity_holdout": False,
            }

    buckets = {
        "source": bucket_generalization_metrics(
            [row.utility_seconds for row in validation_rows],
            activations,
            [row.source_group for row in validation_rows],
        ),
        "time": bucket_generalization_metrics(
            [row.utility_seconds for row in validation_rows],
            activations,
            [row.time_bucket for row in validation_rows],
        ),
        "queue": bucket_generalization_metrics(
            [row.utility_seconds for row in validation_rows],
            activations,
            [row.queue_bucket for row in validation_rows],
        ),
        "slack": bucket_generalization_metrics(
            [row.utility_seconds for row in validation_rows],
            activations,
            [row.slack_bucket for row in validation_rows],
        ),
        "leg": bucket_generalization_metrics(
            [row.utility_seconds for row in validation_rows],
            activations,
            [row.leg for row in validation_rows],
        ),
        "utility_scope": bucket_generalization_metrics(
            [row.utility_seconds for row in validation_rows],
            activations,
            [row.utility_scope for row in validation_rows],
        ),
    }

    validation_families = validation_evaluation["families"]
    selective_mean_utility = float(
        validation_families["SELECTIVE_GATE"]["mean_system_utility"] or 0.0
    )
    localized_mean_utility = float(
        validation_families["LOCALIZED_THESIS_RULE"]["mean_system_utility"] or 0.0
    )
    observed = {
        "validation_activation_count": validation_selective["activation_count"],
        "beneficial_precision": validation_selective["beneficial_precision"],
        "harmful_recall": validation_selective["harmful_recall"],
        "harmful_activation_rate": validation_selective["harmful_activation_rate"],
        "activated_utility_mean": validation_selective["activated_utility_mean"],
        "calibration_ece": calibration["promotion_ece"],
        "ood_activation_count": validation_selective["ood_activation_count"],
        "ood_row_count": sum(validation_ood),
        "ood_rate": float(np.mean(validation_ood)),
        "selective_minus_localized_rule_mean_utility_seconds": (
            selective_mean_utility - localized_mean_utility
        ),
        "h_system_externality_row_count": support["observed"][
            "h_system_externality_rows"
        ],
    }
    required = {
        "validation_activation_count": settings.minimum_validation_activations,
        "beneficial_precision": settings.minimum_beneficial_precision,
        "harmful_recall": settings.minimum_harmful_recall,
        "harmful_activation_rate": settings.maximum_harmful_activation_rate,
        "activated_utility_mean": settings.minimum_activated_utility_seconds,
        "calibration_ece": settings.maximum_calibration_ece,
        "ood_activation_count": 0,
        "selective_minus_localized_rule_mean_utility_seconds": 0.0,
        "h_system_externality_row_count": settings.minimum_h_system_rows,
    }
    promotion_checks = {
        "support": bool(support["pass"]),
        "task_group_hard_split": split_summary["task_group_overlap_count"] == 0,
        "calibration": calibration["promotion_ece"] <= settings.maximum_calibration_ece,
        "validation_activation_support": (
            observed["validation_activation_count"] >= required["validation_activation_count"]
        ),
        "beneficial_precision": observed["beneficial_precision"] >= required["beneficial_precision"],
        "harmful_recall": observed["harmful_recall"] >= required["harmful_recall"],
        "harmful_activation_rate": (
            observed["harmful_activation_rate"] <= required["harmful_activation_rate"]
        ),
        "activated_utility": observed["activated_utility_mean"] > required["activated_utility_mean"],
        "ood_abstention": observed["ood_activation_count"] == 0,
        "learned_not_worse_than_localized_rule": (
            observed["selective_minus_localized_rule_mean_utility_seconds"]
            >= required["selective_minus_localized_rule_mean_utility_seconds"]
            - settings.utility_tolerance_seconds
        ),
        "h_system_externality_evidence": (
            observed["h_system_externality_row_count"]
            >= required["h_system_externality_row_count"]
        ),
        "final_audit_sealed": True,
    }
    authorized = all(promotion_checks.values())
    failed = [name.upper() for name, passed in promotion_checks.items() if not passed]
    status = "OFFLINE_CANDIDATE_AUTHORIZED" if authorized else "TRAINED_NOT_AUTHORIZED"
    reasons = tuple() if authorized else tuple(f"PROMOTION_{name}_FAILED" for name in failed)

    artifact_set_id = _new_artifact_set_id(settings, len(prepared))
    pairwise_artifact = {
        "schema": PAIRWISE_MODEL_SCHEMA,
        "artifact_set_id": artifact_set_id,
        "status": status,
        "training_config": settings.to_dict(),
        "training_label_contract": _label_contract(),
        "benefit_members": [model.to_dict() for model in benefit_models],
        "harm_members": [model.to_dict() for model in harm_models],
        "utility_members": [model.to_dict() for model in utility_models],
        "benefit_calibrators": [_platt_dict(item) for item in benefit_calibrators],
        "harm_calibrators": [_platt_dict(item) for item in harm_calibrators],
        "utility_residual_q05_seconds": utility_residual_q05,
        "ood_envelope": _envelope_dict(envelope),
        "fit_partition": "task_group.train",
        "calibration_partition": "task_group.calibration",
        "selection_partition": "task_group.validation",
        "training_row_count": len(train_indices),
        "calibration_row_count": len(calibration_indices),
        "validation_row_count": len(validation_indices),
        "final_audit_consumed": False,
        "identity_features_used": False,
        "outcome_features_used": False,
    }
    mlp_artifact = {
        "schema": MLP_MODEL_SCHEMA,
        "artifact_set_id": artifact_set_id,
        "status": "DIAGNOSTIC_FAMILY",
        "training_config": settings.to_dict(),
        "training_label_contract": _label_contract(),
        "model": mlp.to_dict(),
        "fit_partition": "task_group.train",
        "training_row_count": len(train_indices),
        "final_audit_consumed": False,
        "identity_features_used": False,
        "outcome_features_used": False,
    }
    policy_artifact = {
        "schema": POLICY_SCHEMA,
        "artifact_set_id": artifact_set_id,
        "status": status,
        "authorized": authorized,
        "selected_family": "SELECTIVE_GATE" if authorized else None,
        "families_compared": list(validation_evaluation["families"]),
        "current_baseline_definition": (
            "candidate_index_0 is the matched unmodified/current-policy decision"
        ),
        "localized_rule": LocalizedThesisPriority().ablation_definition(),
        "validation_evaluation": validation_evaluation,
        "diagnostics": diagnostics,
        "buckets": buckets,
        "support": support,
        "final_audit": {
            "row_count": split_counts["final_audit"]["row_count"],
            "consumed": False,
        },
        "identity_features_used": False,
    }
    gate_artifact = {
        "schema": GATE_SCHEMA,
        "artifact_set_id": artifact_set_id,
        "status": status,
        "authorized": authorized,
        "authorization_scope": "offline_candidate_for_supervised_shadow",
        # Closed-loop authorization still requires the later native shadow and
        # system campaign, even when this offline promotion gate passes.
        "runtime_closed_loop_authorized": False,
        "reason_codes": list(reasons),
        "training_config": settings.to_dict(),
        "training_label_contract": _label_contract(),
        "input_summary": input_summary,
        "split_summary": split_summary,
        "support": support,
        "calibration": calibration,
        "selector": {
            "benefit_probability_lcb_min": selector.benefit_probability_lcb_min,
            "harm_probability_ucb_max": selector.harm_probability_ucb_max,
            "utility_lcb_min_seconds": selector.utility_lcb_min_seconds,
            "calibration_ece_max": selector.calibration_ece_max,
            "lower_quantile": selector.lower_quantile,
            "upper_quantile": selector.upper_quantile,
            "ensemble_size": settings.ensemble_size,
            "supervisor_authorization_required": True,
            "ood_abstention_required": True,
        },
        "promotion_observed": observed,
        "promotion_required": required,
        "promotion_checks": promotion_checks,
        "final_audit": {
            "row_count": split_counts["final_audit"]["row_count"],
            "consumed": False,
        },
        "identity_features_used": False,
    }
    report = _render_report(
        status=status,
        authorized=authorized,
        reasons=reasons,
        input_summary=input_summary,
        split_summary=split_summary,
        support=support,
        calibration=calibration,
        validation=validation_evaluation,
        diagnostics=diagnostics,
        buckets=buckets,
        checks=promotion_checks,
    )
    return PhaseDTrainingResult(
        status=status,
        authorized=authorized,
        reasons=reasons,
        config=settings,
        input_summary=input_summary,
        split_summary=split_summary,
        support=support,
        calibration=calibration,
        validation_evaluation=validation_evaluation,
        diagnostics=diagnostics,
        buckets=buckets,
        model_artifacts={
            "pairwise_linear": pairwise_artifact,
            "tiny_mlp": mlp_artifact,
        },
        policy_artifact=policy_artifact,
        gate_artifact=gate_artifact,
        report_markdown=report,
        diagnostic_splits=splits,
    )


# A descriptive alias for scripts and notebooks.
train_g4irsf17_i1 = train_phase_d


def _render_report(
    *,
    status: str,
    authorized: bool,
    reasons: Sequence[str],
    input_summary: Mapping[str, Any],
    split_summary: Mapping[str, Any],
    support: Mapping[str, Any],
    calibration: Mapping[str, Any],
    validation: Mapping[str, Any],
    diagnostics: Mapping[str, Any],
    buckets: Mapping[str, Any],
    checks: Mapping[str, Any],
) -> str:
    split_counts = split_summary.get("by_selection_split", {})
    lines = [
        "# G4IRSF17 I1 Phase-D model decision",
        "",
        f"- Status: `{status}`",
        f"- Offline candidate authorized: `{str(authorized).lower()}`",
        "- Runtime closed-loop authorized: `false` (requires later native shadow/system evidence)",
        "- Final audit consumed: `false`",
        "- Model features contain task/source IDs: `false`",
        "",
        "## Input and split support",
        "",
        f"Valid matched feature/effect rows: {input_summary.get('valid_feature_effect_row_count', 0)} "
        f"of {input_summary.get('input_row_count', 0)}.",
        "",
    ]
    if input_summary.get("rejection_reasons"):
        lines.append("Rejected-row reasons: " + json.dumps(input_summary["rejection_reasons"], sort_keys=True))
        lines.append("")
    if split_counts:
        lines.extend(
            [
                "| split | rows | beneficial | harmful | neutral |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for split in ("train", "calibration", "validation", "final_audit"):
            values = split_counts.get(split, {})
            beneficial = values.get("beneficial_count", 0)
            harmful = values.get("harmful_count", 0)
            neutral = values.get("neutral_count", 0)
            lines.append(
                f"| {split} | {values.get('row_count', 0)} | "
                f"{'sealed' if beneficial is None else beneficial} | "
                f"{'sealed' if harmful is None else harmful} | "
                f"{'sealed' if neutral is None else neutral} |"
            )
        lines.append("")
    lines.extend(
        [
            "Support pass: `" + str(bool(support.get("pass", False))).lower() + "`.",
            f"H_bag `{H_BAG_TRAINING_SCOPE}` development rows: "
            f"{support.get('observed', {}).get('h_bag_training_rows', 0)}.",
            f"H_system externality evidence rows: "
            f"{support.get('observed', {}).get('h_system_externality_rows', 0)}.",
            "H_bag labels are limited to the two direct affected bags plus the fixed "
            "deadline penalty; they can train the local ranker but cannot provide "
            "full-system or runtime closed-loop authorization.",
            "",
            "## Calibration, OOD, and validation",
            "",
        ]
    )
    if calibration.get("available"):
        lines.append(
            f"Calibration-fit ECE: benefit={calibration.get('benefit_ece', 0.0):.6f}, "
            f"harm={calibration.get('harm_ece', 0.0):.6f}."
        )
        validation_calibration = calibration.get("validation_evaluation", {})
        if validation_calibration:
            lines.append(
                f"Validation ECE: benefit={validation_calibration.get('benefit_ece', 0.0):.6f}, "
                f"harm={validation_calibration.get('harm_ece', 0.0):.6f}."
            )
    else:
        lines.append("Calibration unavailable; the selector remains no-go.")
    lines.append("")
    families = validation.get("families", {}) if isinstance(validation, Mapping) else {}
    if families:
        lines.extend(
            [
                "| family | rows | top-1 | mean advantage vs current | harmful override rate |",
                "| --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for family, metrics in families.items():
            lines.append(
                f"| {family} | {metrics.get('row_count', 0)} | "
                f"{float(metrics.get('top1_accuracy') or 0.0):.6f} | "
                f"{float(metrics.get('mean_advantage_vs_baseline') or 0.0):.6f} | "
                f"{float(metrics.get('harmful_override_rate') or 0.0):.6f} |"
            )
        lines.append("")
    selective = validation.get("selective_metrics", {}) if isinstance(validation, Mapping) else {}
    if selective:
        lines.append(
            "Selective validation: "
            f"coverage={selective.get('activation_coverage', 0.0):.6f}, "
            f"beneficial precision={selective.get('beneficial_precision', 0.0):.6f}, "
            f"beneficial recall={selective.get('beneficial_recall', 0.0):.6f}, "
            f"harm veto recall={selective.get('harmful_recall', 0.0):.6f}, "
            f"activated utility={selective.get('activated_utility_mean', 0.0):.6f}s, "
            f"OOD rows={selective.get('ood_row_count', 0)}, "
            f"OOD activations={selective.get('ood_activation_count', 0)}."
        )
        lines.append("")
    lines.extend(
        [
            "Source/time diagnostics are task-validation slices; no final-audit row is included. "
            "They report any source/time entity overlap with task-train instead of claiming a "
            "separately refitted strict holdout.",
            "Bucket diagnostics: "
            + (", ".join(sorted(buckets)) if buckets else "unavailable"),
            "",
        ]
    )
    if checks:
        lines.extend(["## Promotion checks", ""])
        for name, passed in checks.items():
            lines.append(f"- `{name}`: `{'pass' if passed else 'fail'}`")
        lines.append("")
    if reasons:
        lines.extend(["## No-go reasons", ""])
        lines.extend(f"- `{reason}`" for reason in reasons)
        lines.append("")
    lines.extend(
        [
            "## Evidence boundaries",
            "",
            "Training uses only the task-group train partition. Platt calibration and the utility "
            "residual bound use only calibration. Promotion metrics use only task-group validation. "
            "Source/time and bucket results are diagnostics, not extra promotion samples. The final "
            "audit stays sealed.",
            "",
        ]
    )
    return "\n".join(lines)


def write_phase_d_artifacts(
    result: PhaseDTrainingResult,
    output_root: str | Path,
) -> dict[str, Path]:
    """Write transparent JSON/CSV/Markdown artifacts and return their paths."""

    root = Path(output_root)
    paths: dict[str, Path] = {
        "policy": root / "artifacts/policies/g4irsf17_i1_policy_comparison.json",
        "gate": root / "artifacts/gates/g4irsf17_i1_selective_gate.json",
        "report": root / "outputs/reports/g4irsf17_i1_model_decision.md",
        "policy_table": root / "outputs/tables/g4irsf17_i1_policy_evaluation.csv",
        "bucket_table": root / "outputs/tables/g4irsf17_i1_bucket_diagnostics.csv",
    }
    if "pairwise_linear" in result.model_artifacts:
        paths["pairwise_model"] = root / "artifacts/models/g4irsf17_i1_pairwise_linear.json"
    if "tiny_mlp" in result.model_artifacts:
        paths["mlp_model"] = root / "artifacts/models/g4irsf17_i1_tiny_mlp.json"
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
    json_payloads = {
        "policy": result.policy_artifact,
        "gate": result.gate_artifact,
    }
    if "pairwise_model" in paths:
        json_payloads["pairwise_model"] = result.model_artifacts["pairwise_linear"]
    if "mlp_model" in paths:
        json_payloads["mlp_model"] = result.model_artifacts["tiny_mlp"]
    for name, payload in json_payloads.items():
        paths[name].write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    paths["report"].write_text(result.report_markdown, encoding="utf-8")

    with paths["policy_table"].open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "family",
                "row_count",
                "top1_accuracy",
                "mean_system_utility",
                "mean_regret",
                "p95_regret",
                "mean_advantage_vs_baseline",
                "beneficial_override_rate",
                "harmful_override_rate",
            ),
        )
        writer.writeheader()
        for family, metrics in result.validation_evaluation.get("families", {}).items():
            writer.writerow({"family": family, **metrics})
    with paths["bucket_table"].open("w", encoding="utf-8", newline="") as handle:
        fieldnames = (
            "dimension",
            "bucket",
            "row_count",
            "activation_count",
            "activation_coverage",
            "beneficial_precision",
            "beneficial_recall",
            "harmful_recall",
            "harmful_activation_rate",
            "activated_utility_mean",
        )
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for dimension, bucket_rows in result.buckets.items():
            for bucket_row in bucket_rows:
                writer.writerow({"dimension": dimension, **bucket_row})
    return paths


def load_effect_feature_rows(path: str | Path) -> list[dict[str, Any]]:
    """Load JSON, JSONL/NDJSON, CSV, or their ``.zst`` compressed form."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    suffixes = [suffix.lower() for suffix in source.suffixes]
    if suffixes and suffixes[-1] == ".zst":
        try:
            import zstandard as zstd
        except ImportError as exc:  # pragma: no cover - project dependency
            raise RuntimeError("ZSTANDARD_REQUIRED_FOR_ZST_INPUT") from exc
        text = zstd.ZstdDecompressor().decompress(source.read_bytes()).decode("utf-8")
        data_suffix = suffixes[-2] if len(suffixes) > 1 else ".jsonl"
    else:
        text = source.read_text(encoding="utf-8")
        data_suffix = suffixes[-1] if suffixes else ".jsonl"
    if data_suffix == ".csv":
        return [dict(row) for row in csv.DictReader(io.StringIO(text))]
    if data_suffix == ".json":
        parsed = json.loads(text)
        if isinstance(parsed, list):
            values = parsed
        elif isinstance(parsed, Mapping):
            values = None
            for key in ("rows", "effects", "feature_rows", "records"):
                candidate = parsed.get(key)
                if isinstance(candidate, list):
                    values = candidate
                    break
            if values is None:
                values = [parsed]
        else:
            raise ValueError("JSON_INPUT_MUST_BE_OBJECT_OR_ARRAY")
    else:
        values = [json.loads(line) for line in text.splitlines() if line.strip()]
    if any(not isinstance(row, Mapping) for row in values):
        raise ValueError("INPUT_ROWS_MUST_BE_OBJECTS")
    return [dict(row) for row in values]


__all__ = [
    "LinearUtilityRegressor",
    "PhaseDTrainingConfig",
    "PhaseDTrainingResult",
    "load_effect_feature_rows",
    "train_g4irsf17_i1",
    "train_phase_d",
    "write_phase_d_artifacts",
]
