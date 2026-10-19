"""Build the leakage-safe G4IRSF16 model-ready causal datasets.

This module is intentionally a data projection, not another G4IRSF15
validator.  It consumes the already-formal release, performs the two joins
needed for learning, and writes a narrow schema whose deployment partition is
exactly :data:`czr005.g4irsf16.model.DEPLOYMENT_FEATURES`.

The target-address census contains several airport-wide counters.  They are
useful audit evidence, but they are *not* local queue features.  They are
therefore deny-listed here and never appear in an output table.  Runtime-local
F2/queue/calendar features remain Arrow null unless an optional, matched
runtime feature cache supplies them.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq
import zstandard as zstd

from .model import DEPLOYMENT_FEATURES


DATASET_SCHEMA = "czr005.g4irsf16.model_ready_causal_row.v1"
SPLIT_MANIFEST_SCHEMA = "czr005.g4irsf16.split_manifest.v1"
SPLIT_SEED = "czr005.g4irsf16.split.v1"

LABEL_DATASET = Path("artifacts/datasets/g4irsf15_causal_labels.jsonl.zst")
LABEL_MANIFEST = Path("artifacts/datasets/g4irsf15_causal_label_manifest.json")
TARGET_FRAME = Path(
    "artifacts/datasets/g4irsf15_causal_target_address_frame.jsonl.zst"
)
SOURCE_COMPONENTS = Path(
    "artifacts/datasets/g4irsf15_intervention_split_groups.json"
)
MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")

DATASET_OUTPUTS: Mapping[str, Path] = {
    "i3_route": Path("artifacts/datasets/g4irsf16_i3_route_dataset.parquet"),
    "i4_hold": Path("artifacts/datasets/g4irsf16_i4_hold_dataset.parquet"),
    "hsystem_externality": Path(
        "artifacts/datasets/g4irsf16_hsystem_externality_dataset.parquet"
    ),
}
SPLIT_MANIFEST_OUTPUT = Path(
    "artifacts/datasets/g4irsf16_split_manifest.json"
)
LABEL_INVENTORY_OUTPUT = Path(
    "outputs/tables/g4irsf16_i3_i4_label_inventory.csv"
)
SPLIT_SUPPORT_OUTPUT = Path("outputs/tables/g4irsf16_split_support.csv")
MODEL_READY_REPORT_OUTPUT = Path(
    "outputs/reports/g4irsf16_model_ready_data_report.md"
)

# Hash bucket boundaries implement 60/15/15/10 without data-dependent
# shuffling.  The final interval is deliberately named final_audit rather than
# test: it is sealed and unavailable to model/rule selection.
SPLIT_BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("train", 0, 6000),
    ("calibration", 6000, 7500),
    ("validation", 7500, 9000),
    ("final_audit", 9000, 10000),
)
SPLIT_NAMES = tuple(name for name, _, _ in SPLIT_BUCKETS)

# These features require an exact frozen-F2 decision trace.  Null is a real
# missing value; zero-imputation at data-build time would fabricate state.
DYNAMIC_DEPLOYMENT_FEATURES: tuple[str, ...] = (
    "current_queue_length",
    "target_queue_length",
    "target_scheduled_incoming",
    "current_next_available_wait_seconds",
    "target_next_available_wait_seconds",
    "f2_model_margin",
    "f2_raw_score",
    "recent_visit_count",
    "short_history_repeat_count",
    "advertised_fault",
)

TRACE_MAPPED_DYNAMIC_FEATURES: tuple[str, ...] = DYNAMIC_DEPLOYMENT_FEATURES

STATIC_DEPLOYMENT_FEATURES = tuple(
    name for name in DEPLOYMENT_FEATURES if name not in DYNAMIC_DEPLOYMENT_FEATURES
)

# The weights are fixed in the Stage-16A data contract.  They were not tuned
# against validation or final-audit outcomes.  Deadline misses are absent in
# the formal 256-pair panel, but the explicit penalty keeps the unit defined
# for future append-only H_system evidence.
RISK_BALANCED_WEIGHTS: Mapping[str, float] = {
    "positive_mean_harm": 1.0,
    "cvar95_harm": 0.5,
    "log_external_affected_count": 1.0,
    "extra_deadline_miss": 300.0,
}
RISK_PROFILE = "risk-balanced-stage16a-v1"

LABEL_COLUMNS: tuple[str, ...] = (
    "signed_class",
    "direct_benefit_seconds",
    "risk_adjusted_utility_seconds",
    "risk_profile",
    "direct_affected_count",
    "h_bag_effect_seconds",
    "h_system_available",
    "externality_observed",
    "externality_nonempty",
    "external_affected_count",
    "realized_affected_count",
    "other_bag_mean_harm_seconds",
    "other_bag_max_harm_seconds",
    "other_bag_p95_harm_seconds",
    "other_bag_cvar95_harm_seconds",
    "extra_deadline_miss_count",
    "system_original_entry_delta_seconds",
)

SPLIT_COLUMNS: tuple[str, ...] = (
    "split",
    "component_id",
    "final_audit_status",
)

# Identifiers remain available for scientific subgroup reporting, but are
# segregated from the exact deployment projection.  Raw task/segment/runtime
# IDs are not written at all.
AUDIT_COLUMNS: tuple[str, ...] = (
    "descriptor_id",
    "target_key",
    "clone_group_id",
    "intervention_id",
    "pair_evidence_sha256",
    "kind",
    "horizon",
    "source_frame_horizon",
    "event_ordinal",
    "event_time_seconds",
    "event_time_block",
    "current_node_id",
    "baseline_next_node_id",
    "intervention_next_node_id",
    "goal_node_id",
    "source_node_id",
    "task_class",
    "pre_action_retry_count",
    "pre_action_decision_count",
    "pre_action_status",
    "pre_action_pending_merge",
    "safety_hard_gate_pass",
    "runtime_feature_cache_matched",
    "runtime_dynamic_feature_complete",
)

# Nested source paths are recorded explicitly so later stages cannot quietly
# promote an audit/global/outcome field into the deployment matrix.
FORBIDDEN_SOURCE_FIELDS: tuple[str, ...] = (
    "target.queued_bag_count",
    "target.pending_merge_request_count",
    "target.active_merge_capability_count",
    "target.active_physical_fault_edge_count",
    "target.offline_sampling_metadata",
    "target.coverage_tags",
    "target.sampling",
    "label.offline_sampling_metadata",
    "label.coverage_tags",
    "label.sampling",
    "label.baseline_affected_bag_outcomes",
    "label.treatment_affected_bag_outcomes",
    "label.realized_affected_runtime_bag_ids",
    "label.h_system_signed_label",
    "task.task_id",
    "task.segment_id",
    "target.runtime_bag_id",
    "target.segment_id",
    "pair.resolved_execution_descriptor.queued_bag_count",
    "pair.resolved_execution_descriptor.pending_merge_request_count",
    "pair.resolved_execution_descriptor.active_merge_capability_count",
    "pair.resolved_execution_descriptor.active_physical_fault_edge_count",
)

FORBIDDEN_OUTPUT_COLUMNS: tuple[str, ...] = (
    "task_id",
    "segment_id",
    "runtime_bag_id",
    "queued_bag_count",
    "pending_merge_request_count",
    "active_merge_capability_count",
    "active_physical_fault_edge_count",
    "coverage_tags",
    "offline_sampling_metadata",
    "sampling",
    "realized_affected_runtime_bag_ids",
)

COLUMN_PARTITIONS: Mapping[str, tuple[str, ...]] = {
    "deployable_feature": DEPLOYMENT_FEATURES,
    "label_only": LABEL_COLUMNS,
    "split_only": SPLIT_COLUMNS,
    "audit_identity": AUDIT_COLUMNS,
    "forbidden_source": FORBIDDEN_SOURCE_FIELDS,
}


class ModelReadyDataError(ValueError):
    """A formal-release join or leakage boundary is inconsistent."""


@dataclass(frozen=True)
class ModelReadyBuild:
    """In-memory Stage-16A build result."""

    rows_by_dataset: Mapping[str, tuple[dict[str, Any], ...]]
    split_manifest: dict[str, Any]
    inventory_rows: tuple[dict[str, Any], ...]
    support_rows: tuple[dict[str, Any], ...]
    report_markdown: str


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ModelReadyDataError(
                    f"JSONL_ROW_NOT_OBJECT:{path}:{line_number}"
                )
            rows.append(value)
    return rows


def _read_zstd_json(path: Path) -> Any:
    with path.open("rb") as raw:
        with zstd.ZstdDecompressor().stream_reader(raw) as reader:
            with io.TextIOWrapper(reader, encoding="utf-8") as text:
                return json.load(text)


def _read_zstd_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("rb") as raw:
        with zstd.ZstdDecompressor().stream_reader(raw) as reader:
            with io.TextIOWrapper(reader, encoding="utf-8") as text:
                for line_number, line in enumerate(text, start=1):
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ModelReadyDataError(
                            f"ZSTD_JSONL_ROW_NOT_OBJECT:{path}:{line_number}"
                        )
                    rows.append(value)
    return rows


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelReadyDataError(f"NOT_NUMERIC:{name}")
    result = float(value)
    if not math.isfinite(result):
        raise ModelReadyDataError(f"NOT_FINITE:{name}")
    return result


def _plain_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelReadyDataError(f"NOT_INTEGER:{name}")
    return int(value)


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ModelReadyDataError(f"NOT_MAPPING:{name}")
    return value


def _require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ModelReadyDataError(f"NOT_LIST:{name}")
    return value


def _close(left: Any, right: Any, *, tolerance: float = 1e-8) -> bool:
    return math.isclose(
        _finite_number(left, "left"),
        _finite_number(right, "right"),
        rel_tol=0.0,
        abs_tol=tolerance,
    )


def split_for_component(
    component_id: str,
    *,
    seed: str = SPLIT_SEED,
) -> str:
    """Assign one hard-leakage component to the immutable four-way split."""

    if not isinstance(component_id, str) or not component_id:
        raise ModelReadyDataError("EMPTY_COMPONENT_ID")
    digest = hashlib.sha256(f"{seed}|{component_id}".encode("utf-8")).hexdigest()
    bucket = int(digest[:16], 16) % 10000
    for name, lower, upper in SPLIT_BUCKETS:
        if lower <= bucket < upper:
            return name
    raise AssertionError("split bucket outside [0, 10000)")


def linear_type7_quantile(values: Sequence[float], probability: float) -> float:
    """Hyndman-Fan type-7 quantile (the plan's H_system convention)."""

    if not values:
        raise ModelReadyDataError("TYPE7_EMPTY_INPUT")
    if not 0.0 <= probability <= 1.0:
        raise ModelReadyDataError("TYPE7_PROBABILITY_OUT_OF_RANGE")
    ordered = sorted(_finite_number(value, "quantile_value") for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def cvar_upper_tail(
    values: Sequence[float],
    *,
    confidence: float = 0.95,
) -> float:
    """Mean of the largest ceil((1-confidence) * n) observations."""

    if not values:
        raise ModelReadyDataError("CVAR_EMPTY_INPUT")
    if not 0.0 < confidence < 1.0:
        raise ModelReadyDataError("CVAR_CONFIDENCE_OUT_OF_RANGE")
    ordered = sorted(
        (_finite_number(value, "cvar_value") for value in values),
        reverse=True,
    )
    tail_count = max(1, math.ceil((1.0 - confidence) * len(ordered)))
    return statistics.fmean(ordered[:tail_count])


def _deadline_miss(outcome: Mapping[str, Any]) -> int:
    completed = outcome.get("completed") is True
    if not completed:
        return 1
    finish = _finite_number(outcome.get("finish_time"), "finish_time")
    deadline = _finite_number(outcome.get("deadline"), "deadline")
    return int(finish > deadline + 1e-9)


def hsystem_externality_metrics(pair: Mapping[str, Any]) -> dict[str, Any]:
    """Project sparse H_system deltas into positive-harm tail labels.

    Only ``externality_runtime_bag_ids`` define the other-bag population.
    Directly affected IDs are excluded even when both sets appear in the
    compact realized delta payload.
    """

    if pair.get("horizon") != "H_system":
        raise ModelReadyDataError("EXTERNALITY_METRICS_REQUIRE_H_SYSTEM")
    external_ids = [
        _plain_int(value, "externality_runtime_bag_id")
        for value in _require_list(
            pair.get("externality_runtime_bag_ids"),
            "externality_runtime_bag_ids",
        )
    ]
    if len(external_ids) != len(set(external_ids)):
        raise ModelReadyDataError("DUPLICATE_EXTERNALITY_RUNTIME_BAG_ID")
    direct_ids = {
        _plain_int(value, "direct_affected_runtime_bag_id")
        for value in _require_list(
            pair.get("direct_affected_runtime_bag_ids"),
            "direct_affected_runtime_bag_ids",
        )
    }
    if direct_ids.intersection(external_ids):
        raise ModelReadyDataError("DIRECT_EXTERNALITY_ID_OVERLAP")

    delta_rows = _require_list(
        pair.get("realized_outcome_deltas"),
        "realized_outcome_deltas",
    )
    by_runtime_id: dict[int, Mapping[str, Any]] = {}
    for raw_row in delta_rows:
        row = _require_mapping(raw_row, "realized_outcome_delta")
        runtime_id = _plain_int(row.get("runtime_bag_id"), "runtime_bag_id")
        if runtime_id in by_runtime_id:
            raise ModelReadyDataError("DUPLICATE_REALIZED_OUTCOME_DELTA")
        by_runtime_id[runtime_id] = row
    missing = sorted(set(external_ids).difference(by_runtime_id))
    if missing:
        raise ModelReadyDataError(
            "EXTERNALITY_RUNTIME_DELTA_MISSING:" + ",".join(map(str, missing))
        )

    realized_ids = [
        _plain_int(value, "realized_affected_runtime_bag_id")
        for value in _require_list(
            pair.get("realized_affected_runtime_bag_ids"),
            "realized_affected_runtime_bag_ids",
        )
    ]
    harms: list[float] = []
    extra_misses = 0
    for runtime_id in external_ids:
        row = by_runtime_id[runtime_id]
        signed_harm = _finite_number(
            row.get("completion_delta_seconds"),
            "completion_delta_seconds",
        )
        harms.append(max(0.0, signed_harm))
        baseline = _require_mapping(row.get("baseline"), "baseline_outcome")
        treatment = _require_mapping(row.get("treatment"), "treatment_outcome")
        extra_misses += _deadline_miss(treatment) - _deadline_miss(baseline)

    if not harms:
        mean_harm = max_harm = p95_harm = cvar95_harm = 0.0
    else:
        mean_harm = statistics.fmean(harms)
        max_harm = max(harms)
        p95_harm = linear_type7_quantile(harms, 0.95)
        cvar95_harm = cvar_upper_tail(harms, confidence=0.95)
    return {
        "externality_nonempty": bool(external_ids),
        "external_affected_count": len(external_ids),
        "realized_affected_count": len(realized_ids),
        "other_bag_mean_harm_seconds": mean_harm,
        "other_bag_max_harm_seconds": max_harm,
        "other_bag_p95_harm_seconds": p95_harm,
        "other_bag_cvar95_harm_seconds": cvar95_harm,
        "extra_deadline_miss_count": extra_misses,
    }


def balanced_risk_adjusted_utility(
    direct_benefit_seconds: float,
    externality: Mapping[str, Any],
) -> float:
    """Apply the fixed Stage-16A risk-balanced utility sign convention."""

    direct = _finite_number(direct_benefit_seconds, "direct_benefit_seconds")
    mean_harm = max(
        0.0,
        _finite_number(
            externality.get("other_bag_mean_harm_seconds"),
            "other_bag_mean_harm_seconds",
        ),
    )
    cvar = max(
        0.0,
        _finite_number(
            externality.get("other_bag_cvar95_harm_seconds"),
            "other_bag_cvar95_harm_seconds",
        ),
    )
    affected = _plain_int(
        externality.get("external_affected_count"),
        "external_affected_count",
    )
    extra_miss = max(
        0,
        _plain_int(
            externality.get("extra_deadline_miss_count"),
            "extra_deadline_miss_count",
        ),
    )
    return (
        direct
        - RISK_BALANCED_WEIGHTS["positive_mean_harm"] * mean_harm
        - RISK_BALANCED_WEIGHTS["cvar95_harm"] * cvar
        - RISK_BALANCED_WEIGHTS["log_external_affected_count"]
        * math.log1p(affected)
        - RISK_BALANCED_WEIGHTS["extra_deadline_miss"] * extra_miss
    )


def _normalise_signed_class(value: Any) -> str:
    mapping = {
        "BENEFICIAL": "BENEFICIAL",
        "NEUTRAL": "NEUTRAL",
        "NEUTRAL_WITHIN_TOLERANCE": "NEUTRAL",
        "HARMFUL": "HARMFUL",
    }
    result = mapping.get(str(value))
    if result is None:
        raise ModelReadyDataError(f"UNKNOWN_SIGNED_CLASS:{value}")
    return result


def _load_runtime_feature_cache(
    path: Path | None,
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    if path is None:
        return {}, {}
    if not path.exists():
        raise ModelReadyDataError(f"RUNTIME_FEATURE_CACHE_MISSING:{path}")
    if path.suffix == ".parquet":
        rows = pq.read_table(path).to_pylist()
    elif path.suffix == ".zst":
        rows = _read_zstd_jsonl(path)
    elif path.suffix == ".json":
        value = _read_json(path)
        if isinstance(value, Mapping):
            value = value.get("rows")
        if not isinstance(value, list):
            raise ModelReadyDataError("RUNTIME_FEATURE_CACHE_JSON_NOT_ROWS")
        rows = value
    else:
        rows = _read_jsonl(path)

    by_descriptor: dict[str, Mapping[str, Any]] = {}
    by_target: dict[str, Mapping[str, Any]] = {}
    for raw in rows:
        row = _require_mapping(raw, "runtime_feature_cache_row")
        features = row.get("features")
        nested_target = row.get("target")
        is_matched_trace = isinstance(nested_target, Mapping)
        if is_matched_trace:
            if row.get("schema") != "czr005.g4irsf16.matched_local_features.v1":
                raise ModelReadyDataError("RUNTIME_TRACE_CACHE_SCHEMA_MISMATCH")
            target_identity = _require_mapping(
                nested_target,
                "runtime_feature_cache.target",
            )
            descriptor_id = target_identity.get("descriptor_id")
            target_key = target_identity.get("target_key")
            features = _require_mapping(
                features,
                "runtime_feature_cache.features",
            )
            allowed_top = {
                "current_local_queue_length",
                "current_next_available_time",
                "current_calendar_wait_seconds",
                "short_history",
                "f2",
                "candidates",
            }
            unknown_top = sorted(set(features).difference(allowed_top))
            if unknown_top:
                raise ModelReadyDataError(
                    "RUNTIME_TRACE_FEATURE_NOT_ALLOWLISTED:"
                    + ",".join(unknown_top)
                )
            f2 = _require_mapping(features.get("f2"), "runtime_trace.features.f2")
            unknown_f2 = sorted(
                set(f2).difference(
                    {
                        "model_margin",
                        "scorer_raw_margin",
                        "risk_gate_triggered",
                        "scorer_risk_abstain",
                    }
                )
            )
            if unknown_f2:
                raise ModelReadyDataError(
                    "RUNTIME_TRACE_F2_FEATURE_NOT_ALLOWLISTED:"
                    + ",".join(unknown_f2)
                )
            allowed_candidate = {
                "target_queue_length",
                "target_scheduled_incoming",
                "corridor_next_available",
                "target_next_available",
                "corridor_wait_seconds",
                "target_calendar_delay_seconds",
                "travel_time",
                "static_potential",
                "model_score",
                "scorer_raw_score",
                "scorer_raw_bottleneck",
                "advertised_fault",
                "shield_allowed",
                "shield_reason",
            }
            for candidate in _require_list(
                features.get("candidates"),
                "runtime_trace.features.candidates",
            ):
                candidate_row = _require_mapping(candidate, "runtime_trace.candidate")
                candidate_features = _require_mapping(
                    candidate_row.get("features"),
                    "runtime_trace.candidate.features",
                )
                unknown_candidate = sorted(
                    set(candidate_features).difference(allowed_candidate)
                )
                if unknown_candidate:
                    raise ModelReadyDataError(
                        "RUNTIME_TRACE_CANDIDATE_FEATURE_NOT_ALLOWLISTED:"
                        + ",".join(unknown_candidate)
                    )
            clean_row = dict(row)
            clean_row["descriptor_id"] = descriptor_id
            clean_row["target_key"] = target_key
            clean_row["cache_format"] = "MATCHED_LOCAL_FEATURES_V1"
        elif features is None:
            features = {
                name: row[name]
                for name in DYNAMIC_DEPLOYMENT_FEATURES
                if name in row
            }
        if not is_matched_trace:
            features = _require_mapping(features, "runtime_feature_cache.features")
            unknown = sorted(set(features).difference(DYNAMIC_DEPLOYMENT_FEATURES))
            if unknown:
                raise ModelReadyDataError(
                    "RUNTIME_CACHE_NON_DYNAMIC_FEATURE:" + ",".join(unknown)
                )
            clean_features: dict[str, float | None] = {}
            for name in DYNAMIC_DEPLOYMENT_FEATURES:
                value = features.get(name)
                clean_features[name] = (
                    None if value is None else _finite_number(value, f"cache.{name}")
                )
            clean_row = dict(row)
            clean_row["features"] = clean_features
            clean_row["cache_format"] = "FLAT_DYNAMIC_FEATURES_V1"
            descriptor_id = row.get("descriptor_id")
            target_key = row.get("target_key")
        if not isinstance(descriptor_id, str) and not isinstance(target_key, str):
            raise ModelReadyDataError("RUNTIME_CACHE_JOIN_ID_MISSING")
        if isinstance(descriptor_id, str):
            if descriptor_id in by_descriptor:
                raise ModelReadyDataError("RUNTIME_CACHE_DUPLICATE_DESCRIPTOR")
            by_descriptor[descriptor_id] = clean_row
        if isinstance(target_key, str):
            if target_key in by_target:
                raise ModelReadyDataError("RUNTIME_CACHE_DUPLICATE_TARGET_KEY")
            by_target[target_key] = clean_row
    return by_descriptor, by_target


def _matched_trace_runtime_features(
    row: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, float | None]:
    """Map the outcome-free live trace allowlist to the frozen model schema."""

    identity = _require_mapping(row.get("target"), "runtime_trace.target")
    action = _require_mapping(row.get("action_context"), "runtime_trace.action_context")
    features = _require_mapping(row.get("features"), "runtime_trace.features")
    if identity.get("kind") != target.get("kind"):
        raise ModelReadyDataError("RUNTIME_TRACE_KIND_MISMATCH")
    if _plain_int(action.get("current_node"), "runtime_trace.current_node") != _plain_int(
        target.get("node"),
        "target.node",
    ):
        raise ModelReadyDataError("RUNTIME_TRACE_CURRENT_NODE_MISMATCH")
    if _plain_int(action.get("goal_node"), "runtime_trace.goal_node") != _plain_int(
        target.get("goal"),
        "target.goal",
    ):
        raise ModelReadyDataError("RUNTIME_TRACE_GOAL_NODE_MISMATCH")
    baseline_next = _plain_int(
        target.get("baseline_next_node"),
        "target.baseline_next_node",
    )
    observed_f2_next = action.get("f2_selected_next")
    if observed_f2_next is None:
        # Native hold-attempt rows do not commit an edge and therefore expose
        # selected_next=null.  Their outcome-free scorer prediction is the F2
        # release edge bound by the formal baseline action.
        observed_f2_next = action.get("f2_model_prediction")
    if _plain_int(observed_f2_next, "runtime_trace.f2_next") != baseline_next:
        raise ModelReadyDataError("RUNTIME_TRACE_F2_ACTION_MISMATCH")
    if target.get("kind") == "I3":
        target_next = _plain_int(
            target.get("selected_next_node"),
            "target.selected_next_node",
        )
    elif target.get("kind") == "I4":
        # I4 compares one natural hold with releasing along the frozen F2 edge.
        target_next = baseline_next
    else:
        raise ModelReadyDataError("RUNTIME_TRACE_UNSUPPORTED_KIND")

    candidates: dict[int, Mapping[str, Any]] = {}
    for raw_candidate in _require_list(
        features.get("candidates"),
        "runtime_trace.features.candidates",
    ):
        candidate = _require_mapping(raw_candidate, "runtime_trace.candidate")
        next_node = _plain_int(
            candidate.get("action_next_node"),
            "runtime_trace.action_next_node",
        )
        if next_node in candidates:
            raise ModelReadyDataError("RUNTIME_TRACE_CANDIDATE_DUPLICATE")
        candidates[next_node] = _require_mapping(
            candidate.get("features"),
            "runtime_trace.candidate.features",
        )
    try:
        target_candidate = candidates[target_next]
        baseline_candidate = candidates[baseline_next]
    except KeyError as error:
        raise ModelReadyDataError("RUNTIME_TRACE_REQUIRED_CANDIDATE_MISSING") from error
    short_history = [
        _plain_int(value, "runtime_trace.short_history")
        for value in _require_list(
            features.get("short_history"),
            "runtime_trace.short_history",
        )
    ]
    repeated = len(short_history) - len(set(short_history))
    f2 = _require_mapping(features.get("f2"), "runtime_trace.f2")

    result: dict[str, float | None] = {
        name: None for name in DYNAMIC_DEPLOYMENT_FEATURES
    }
    result.update(
        {
            "current_queue_length": _finite_number(
                features.get("current_local_queue_length"),
                "runtime_trace.current_local_queue_length",
            ),
            "target_queue_length": _finite_number(
                target_candidate.get("target_queue_length"),
                "runtime_trace.target_queue_length",
            ),
            "target_scheduled_incoming": _finite_number(
                target_candidate.get("target_scheduled_incoming"),
                "runtime_trace.target_scheduled_incoming",
            ),
            "current_next_available_wait_seconds": _finite_number(
                features.get("current_calendar_wait_seconds"),
                "runtime_trace.current_calendar_wait_seconds",
            ),
            "target_next_available_wait_seconds": _finite_number(
                target_candidate.get("target_calendar_delay_seconds"),
                "runtime_trace.target_calendar_delay_seconds",
            ),
            "f2_model_margin": _finite_number(
                f2.get("model_margin"),
                "runtime_trace.f2.model_margin",
            ),
            "f2_raw_score": _finite_number(
                baseline_candidate.get("scorer_raw_score"),
                "runtime_trace.f2_raw_score",
            ),
            "recent_visit_count": float(short_history.count(target_next)),
            "short_history_repeat_count": float(repeated),
            "advertised_fault": float(
                target_candidate.get("advertised_fault") is True
            ),
        }
    )
    # Physical-fault state remains owned by the supervisor shield.  It is not
    # projected into the learned model, and no shield/risk proxy is substituted.
    return result


def _runtime_features_for_row(
    descriptor_id: str,
    target_key: str,
    target: Mapping[str, Any],
    by_descriptor: Mapping[str, Mapping[str, Any]],
    by_target: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, float | None], bool]:
    descriptor_row = by_descriptor.get(descriptor_id)
    target_row = by_target.get(target_key)
    if descriptor_row is not None and target_row is not None:
        if descriptor_row is not target_row and descriptor_row != target_row:
            raise ModelReadyDataError("RUNTIME_CACHE_JOIN_DISAGREEMENT")
    row = descriptor_row if descriptor_row is not None else target_row
    if row is None:
        return {name: None for name in DYNAMIC_DEPLOYMENT_FEATURES}, False
    if row.get("descriptor_id") not in (None, descriptor_id):
        raise ModelReadyDataError("RUNTIME_CACHE_DESCRIPTOR_MISMATCH")
    if row.get("target_key") not in (None, target_key):
        raise ModelReadyDataError("RUNTIME_CACHE_TARGET_KEY_MISMATCH")
    if row.get("cache_format") == "MATCHED_LOCAL_FEATURES_V1":
        return _matched_trace_runtime_features(row, target), True
    features = _require_mapping(row.get("features"), "runtime_cache.features")
    return {name: features.get(name) for name in DYNAMIC_DEPLOYMENT_FEATURES}, True


def _load_pair_index(
    root: Path,
    label_manifest: Mapping[str, Any],
    wanted_target_keys: set[str],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    shards = _require_list(
        label_manifest.get("pair_evidence_shards"),
        "pair_evidence_shards",
    )
    for raw_shard in shards:
        shard = _require_mapping(raw_shard, "pair_evidence_shard")
        declared_keys = set(
            str(value)
            for value in _require_list(shard.get("target_keys"), "target_keys")
        )
        if not declared_keys.intersection(wanted_target_keys):
            continue
        relative_path = shard.get("path")
        if not isinstance(relative_path, str):
            raise ModelReadyDataError("PAIR_SHARD_PATH_MISSING")
        payload = _require_mapping(
            _read_zstd_json(root / relative_path),
            "pair_evidence_payload",
        )
        entries = _require_list(payload.get("pairs"), "pair_evidence_payload.pairs")
        for raw_entry in entries:
            entry = _require_mapping(raw_entry, "pair_evidence_entry")
            target_key = entry.get("target_key")
            if target_key not in wanted_target_keys:
                continue
            if not isinstance(target_key, str):
                raise ModelReadyDataError("PAIR_TARGET_KEY_NOT_STRING")
            if target_key in result:
                raise ModelReadyDataError(f"PAIR_TARGET_KEY_DUPLICATE:{target_key}")
            pair = _require_mapping(entry.get("pair"), "pair")
            if pair.get("target_key") != target_key:
                raise ModelReadyDataError(f"PAIR_TARGET_KEY_MISMATCH:{target_key}")
            result[target_key] = entry
    missing = sorted(wanted_target_keys.difference(result))
    if missing:
        raise ModelReadyDataError(f"PAIR_EVIDENCE_MISSING:{len(missing)}")
    return result


def _component_index(
    source: Mapping[str, Any],
    wanted_target_keys: set[str],
) -> tuple[dict[str, str], list[Mapping[str, Any]]]:
    groups = [
        _require_mapping(value, "source_component")
        for value in _require_list(source.get("groups"), "source_components.groups")
    ]
    result: dict[str, str] = {}
    for group in groups:
        component_id = group.get("component_id")
        if not isinstance(component_id, str) or not component_id:
            raise ModelReadyDataError("SOURCE_COMPONENT_ID_MISSING")
        for raw_key in _require_list(group.get("target_keys"), "component.target_keys"):
            key = str(raw_key)
            if key not in wanted_target_keys:
                continue
            if key in result:
                raise ModelReadyDataError(f"TARGET_COMPONENT_DUPLICATE:{key}")
            result[key] = component_id
    missing = sorted(wanted_target_keys.difference(result))
    if missing:
        raise ModelReadyDataError(f"TARGET_COMPONENT_MISSING:{len(missing)}")
    return result, groups


def _target_index(
    rows: Iterable[Mapping[str, Any]],
    wanted_descriptor_ids: set[str],
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        descriptor_id = row.get("descriptor_id")
        if descriptor_id not in wanted_descriptor_ids:
            continue
        if not isinstance(descriptor_id, str):
            raise ModelReadyDataError("TARGET_DESCRIPTOR_ID_NOT_STRING")
        if descriptor_id in result:
            raise ModelReadyDataError(
                f"TARGET_DESCRIPTOR_JOIN_AMBIGUOUS:{descriptor_id}"
            )
        result[descriptor_id] = row
    missing = sorted(wanted_descriptor_ids.difference(result))
    if missing:
        raise ModelReadyDataError(f"TARGET_DESCRIPTOR_JOIN_MISSING:{len(missing)}")
    return result


def _map_lookups(map_payload: Mapping[str, Any]) -> tuple[
    dict[int, Mapping[str, Any]],
    dict[tuple[int, int], float],
    list[list[float]],
]:
    nodes: dict[int, Mapping[str, Any]] = {}
    for raw in _require_list(map_payload.get("nodes"), "map.nodes"):
        node = _require_mapping(raw, "map.node")
        location = _plain_int(node.get("location"), "node.location")
        if location in nodes:
            raise ModelReadyDataError("MAP_NODE_DUPLICATE")
        nodes[location] = node
    edges: dict[tuple[int, int], float] = {}
    for raw in _require_list(map_payload.get("edges"), "map.edges"):
        edge = _require_mapping(raw, "map.edge")
        key = (
            _plain_int(edge.get("start"), "edge.start"),
            _plain_int(edge.get("end"), "edge.end"),
        )
        if key in edges:
            raise ModelReadyDataError("MAP_EDGE_DUPLICATE")
        edges[key] = _finite_number(edge.get("travel_time"), "edge.travel_time")
    raw_heuristic = _require_list(map_payload.get("heuristic_time"), "heuristic_time")
    heuristic = [
        [_finite_number(value, "heuristic_time") for value in _require_list(row, "heuristic_row")]
        for row in raw_heuristic
    ]
    return nodes, edges, heuristic


def _edge_time(edges: Mapping[tuple[int, int], float], start: int, end: int) -> float:
    try:
        return edges[(start, end)]
    except KeyError as error:
        raise ModelReadyDataError(f"MAP_EDGE_MISSING:{start}:{end}") from error


def _heuristic(heuristic: Sequence[Sequence[float]], start: int, goal: int) -> float:
    try:
        return _finite_number(heuristic[start][goal], "heuristic_lookup")
    except IndexError as error:
        raise ModelReadyDataError(f"HEURISTIC_LOOKUP_MISSING:{start}:{goal}") from error


def _pre_action_snapshot(
    pair: Mapping[str, Any],
    runtime_bag_id: int,
) -> Mapping[str, Any] | None:
    certificate = _require_mapping(
        pair.get("committed_action_certificate"),
        "committed_action_certificate",
    )
    snapshots = _require_list(
        certificate.get("baseline_pre_action_snapshots"),
        "baseline_pre_action_snapshots",
    )
    matches = [
        _require_mapping(value, "pre_action_snapshot")
        for value in snapshots
        if isinstance(value, Mapping) and value.get("runtime_bag_id") == runtime_bag_id
    ]
    if len(matches) > 1:
        raise ModelReadyDataError("PRE_ACTION_SNAPSHOT_AMBIGUOUS")
    return matches[0] if matches else None


def _pending_merge(snapshot: Mapping[str, Any] | None) -> bool | None:
    if snapshot is None:
        return None
    request = snapshot.get("pending_merge_request_id")
    destination = snapshot.get("pending_merge_destination")
    return bool(
        request not in (None, "", -1, 0, "0")
        or (isinstance(destination, int) and destination >= 0)
    )


def _static_feature_projection(
    target: Mapping[str, Any],
    task: Mapping[str, Any],
    nodes: Mapping[int, Mapping[str, Any]],
    edges: Mapping[tuple[int, int], float],
    heuristic: Sequence[Sequence[float]],
) -> tuple[dict[str, float], dict[str, int | None]]:
    kind = str(target.get("kind"))
    current = _plain_int(target.get("node"), "target.node")
    goal = _plain_int(target.get("goal"), "target.goal")
    baseline_next = _plain_int(
        target.get("baseline_next_node"),
        "target.baseline_next_node",
    )
    raw_intervention_next = target.get("selected_next_node")
    intervention_next: int | None
    if kind == "I3":
        intervention_next = _plain_int(
            raw_intervention_next,
            "target.selected_next_node",
        )
        if intervention_next < 0:
            raise ModelReadyDataError("I3_INTERVENTION_NEXT_MISSING")
    elif kind == "I4":
        intervention_next = None
    else:
        raise ModelReadyDataError(f"UNSUPPORTED_KIND:{kind}")

    try:
        current_node = nodes[current]
    except KeyError as error:
        raise ModelReadyDataError(f"CURRENT_NODE_MISSING:{current}") from error
    baseline_travel = _edge_time(edges, current, baseline_next)
    current_remaining = _heuristic(heuristic, current, goal)
    baseline_remaining = baseline_travel + _heuristic(
        heuristic,
        baseline_next,
        goal,
    )
    if intervention_next is None:
        intervention_travel = 0.0
        intervention_remaining = current_remaining
    else:
        intervention_travel = _edge_time(edges, current, intervention_next)
        intervention_remaining = intervention_travel + _heuristic(
            heuristic,
            intervention_next,
            goal,
        )

    event_time = _finite_number(target.get("event_time"), "event_time")
    deadline = _finite_number(task.get("std"), "task.std")
    release_time = _finite_number(task.get("pass_time"), "task.pass_time")
    wait_age = event_time - release_time
    if wait_age < -1e-8:
        raise ModelReadyDataError("NEGATIVE_WAIT_AGE")
    hour = (event_time / 3600.0) % 24.0
    radians = 2.0 * math.pi * hour / 24.0
    leg = str(task.get("leg"))
    projection = {
        "deadline_slack_seconds": deadline - event_time,
        "wait_age_seconds": max(0.0, wait_age),
        "alternative_action_count": float(
            _plain_int(
                target.get("alternative_action_count"),
                "alternative_action_count",
            )
        ),
        "total_legal_action_count": float(
            _plain_int(
                target.get("total_legal_action_count"),
                "total_legal_action_count",
            )
        ),
        "current_node_out_degree": float(
            len(_require_list(current_node.get("outgoing"), "node.outgoing"))
        ),
        "current_node_type": float(
            _plain_int(current_node.get("node_type"), "node.node_type")
        ),
        "current_node_service_seconds": _finite_number(
            current_node.get("service_time"),
            "node.service_time",
        ),
        "baseline_edge_travel_seconds": baseline_travel,
        "intervention_edge_travel_seconds": intervention_travel,
        "static_remaining_current_seconds": current_remaining,
        "static_remaining_baseline_seconds": baseline_remaining,
        "static_remaining_intervention_seconds": intervention_remaining,
        # Positive means the intervention has a lower static route cost.
        "static_potential_delta_seconds": (
            baseline_remaining - intervention_remaining
        ),
        "storage_in_leg": float(leg == "storage_in"),
        "storage_out_leg": float(leg == "storage_out"),
        "direct_leg": float(leg == "direct"),
        "event_hour_sin": math.sin(radians),
        "event_hour_cos": math.cos(radians),
        "baseline_release": float(target.get("baseline_release") is True),
    }
    if tuple(projection) != STATIC_DEPLOYMENT_FEATURES:
        raise AssertionError("static deployment feature ordering drifted")
    return projection, {
        "current_node": current,
        "goal": goal,
        "baseline_next": baseline_next,
        "intervention_next": intervention_next,
    }


def _build_row(
    *,
    label: Mapping[str, Any],
    target: Mapping[str, Any],
    pair_entry: Mapping[str, Any],
    component_id: str,
    task: Mapping[str, Any],
    nodes: Mapping[int, Mapping[str, Any]],
    edges: Mapping[tuple[int, int], float],
    heuristic: Sequence[Sequence[float]],
    runtime_by_descriptor: Mapping[str, Mapping[str, Any]],
    runtime_by_target: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    descriptor_id = str(label.get("descriptor_id"))
    target_key = str(label.get("target_key"))
    kind = str(label.get("kind"))
    horizon = str(label.get("horizon"))
    pair = _require_mapping(pair_entry.get("pair"), "pair")

    for name, left, right in (
        ("target.kind", target.get("kind"), kind),
        ("target.event_ordinal", target.get("event_ordinal"), label.get("event_ordinal")),
        ("target.clone_group_id", target.get("clone_group_id"), label.get("clone_group_id")),
        ("pair.kind", pair.get("kind"), kind),
        ("pair.horizon", pair.get("horizon"), horizon),
        ("pair.descriptor_id", pair.get("descriptor_id"), descriptor_id),
        ("pair.target_key", pair.get("target_key"), target_key),
        (
            "pair_evidence_sha256",
            pair_entry.get("pair_evidence_sha256"),
            label.get("pair_evidence_sha256"),
        ),
    ):
        if left != right:
            raise ModelReadyDataError(f"FORMAL_JOIN_MISMATCH:{name}:{target_key}")

    if str(task.get("segment_id")) != str(target.get("segment_id")):
        raise ModelReadyDataError("TASK_SEGMENT_JOIN_MISMATCH")
    if _plain_int(task.get("goal"), "task.goal") != _plain_int(
        target.get("goal"), "target.goal"
    ):
        raise ModelReadyDataError("TASK_GOAL_MISMATCH")
    if not _close(task.get("std"), target.get("deadline")):
        raise ModelReadyDataError("TASK_DEADLINE_MISMATCH")
    if not _close(task.get("pass_time"), target.get("release_time")):
        raise ModelReadyDataError("TASK_RELEASE_TIME_MISMATCH")

    static_features, identities = _static_feature_projection(
        target,
        task,
        nodes,
        edges,
        heuristic,
    )
    dynamic_features, cache_matched = _runtime_features_for_row(
        descriptor_id,
        target_key,
        target,
        runtime_by_descriptor,
        runtime_by_target,
    )
    deployment = {
        name: (
            static_features[name]
            if name in static_features
            else dynamic_features[name]
        )
        for name in DEPLOYMENT_FEATURES
    }

    h_bag_effect = _finite_number(
        label.get("h_bag_delta_completion_mean_seconds"),
        "h_bag_delta_completion_mean_seconds",
    )
    direct_benefit = -h_bag_effect
    externality: dict[str, Any] | None = None
    if horizon == "H_system":
        externality = hsystem_externality_metrics(pair)
        risk_utility = balanced_risk_adjusted_utility(
            direct_benefit,
            externality,
        )
    elif horizon == "H_bag":
        risk_utility = None
    else:
        raise ModelReadyDataError(f"UNSUPPORTED_HORIZON:{horizon}")

    direct_ids = _require_list(
        pair.get("direct_affected_runtime_bag_ids"),
        "direct_affected_runtime_bag_ids",
    )
    runtime_bag_id = _plain_int(
        target.get("runtime_bag_id"),
        "target.runtime_bag_id",
    )
    snapshot = _pre_action_snapshot(pair, runtime_bag_id)
    split = split_for_component(component_id)
    resolved = _require_mapping(
        pair.get("resolved_execution_descriptor"),
        "resolved_execution_descriptor",
    )

    row: dict[str, Any] = dict(deployment)
    row.update(
        {
            "signed_class": _normalise_signed_class(label.get("signed_label")),
            "direct_benefit_seconds": direct_benefit,
            "risk_adjusted_utility_seconds": risk_utility,
            "risk_profile": RISK_PROFILE if externality is not None else None,
            "direct_affected_count": len(direct_ids),
            "h_bag_effect_seconds": h_bag_effect,
            "h_system_available": externality is not None,
            "externality_observed": externality is not None,
            "externality_nonempty": (
                externality["externality_nonempty"]
                if externality is not None
                else None
            ),
            "external_affected_count": (
                externality["external_affected_count"]
                if externality is not None
                else None
            ),
            "realized_affected_count": (
                externality["realized_affected_count"]
                if externality is not None
                else None
            ),
            "other_bag_mean_harm_seconds": (
                externality["other_bag_mean_harm_seconds"]
                if externality is not None
                else None
            ),
            "other_bag_max_harm_seconds": (
                externality["other_bag_max_harm_seconds"]
                if externality is not None
                else None
            ),
            "other_bag_p95_harm_seconds": (
                externality["other_bag_p95_harm_seconds"]
                if externality is not None
                else None
            ),
            "other_bag_cvar95_harm_seconds": (
                externality["other_bag_cvar95_harm_seconds"]
                if externality is not None
                else None
            ),
            "extra_deadline_miss_count": (
                externality["extra_deadline_miss_count"]
                if externality is not None
                else None
            ),
            "system_original_entry_delta_seconds": (
                _finite_number(
                    label.get("h_system_delta_original_entry_mean_seconds"),
                    "h_system_delta_original_entry_mean_seconds",
                )
                if externality is not None
                else None
            ),
            "split": split,
            "component_id": component_id,
            "final_audit_status": (
                "SEALED_NOT_CONSUMED"
                if split == "final_audit"
                else "NOT_FINAL_AUDIT"
            ),
            "descriptor_id": descriptor_id,
            "target_key": target_key,
            "clone_group_id": str(label.get("clone_group_id")),
            "intervention_id": str(resolved.get("descriptor_id")),
            "pair_evidence_sha256": str(pair_entry.get("pair_evidence_sha256")),
            "kind": kind,
            "horizon": horizon,
            "source_frame_horizon": str(target.get("horizon")),
            "event_ordinal": _plain_int(
                label.get("event_ordinal"),
                "event_ordinal",
            ),
            "event_time_seconds": _finite_number(
                target.get("event_time"),
                "event_time",
            ),
            "event_time_block": int(
                (_finite_number(target.get("event_time"), "event_time") / 3600.0)
                % 24.0
            ),
            "current_node_id": identities["current_node"],
            "baseline_next_node_id": identities["baseline_next"],
            "intervention_next_node_id": identities["intervention_next"],
            "goal_node_id": identities["goal"],
            "source_node_id": _plain_int(task.get("start"), "task.start"),
            "task_class": str(task.get("leg")),
            "pre_action_retry_count": (
                _plain_int(snapshot.get("retry_count"), "snapshot.retry_count")
                if snapshot is not None
                else None
            ),
            "pre_action_decision_count": (
                _plain_int(
                    snapshot.get("decision_count"),
                    "snapshot.decision_count",
                )
                if snapshot is not None
                else None
            ),
            "pre_action_status": (
                str(snapshot.get("status")) if snapshot is not None else None
            ),
            "pre_action_pending_merge": _pending_merge(snapshot),
            "safety_hard_gate_pass": label.get("safety_hard_gate_pass") is True,
            "runtime_feature_cache_matched": cache_matched,
            "runtime_dynamic_feature_complete": all(
                dynamic_features[name] is not None
                for name in DYNAMIC_DEPLOYMENT_FEATURES
            ),
        }
    )
    expected = set(DEPLOYMENT_FEATURES + LABEL_COLUMNS + SPLIT_COLUMNS + AUDIT_COLUMNS)
    if set(row) != expected:
        missing = sorted(expected.difference(row))
        extra = sorted(set(row).difference(expected))
        raise AssertionError(f"row schema drifted: missing={missing} extra={extra}")
    return row


_LABEL_ARROW_TYPES: Mapping[str, pa.DataType] = {
    "signed_class": pa.string(),
    "direct_benefit_seconds": pa.float64(),
    "risk_adjusted_utility_seconds": pa.float64(),
    "risk_profile": pa.string(),
    "direct_affected_count": pa.int64(),
    "h_bag_effect_seconds": pa.float64(),
    "h_system_available": pa.bool_(),
    "externality_observed": pa.bool_(),
    "externality_nonempty": pa.bool_(),
    "external_affected_count": pa.int64(),
    "realized_affected_count": pa.int64(),
    "other_bag_mean_harm_seconds": pa.float64(),
    "other_bag_max_harm_seconds": pa.float64(),
    "other_bag_p95_harm_seconds": pa.float64(),
    "other_bag_cvar95_harm_seconds": pa.float64(),
    "extra_deadline_miss_count": pa.int64(),
    "system_original_entry_delta_seconds": pa.float64(),
}

_SPLIT_ARROW_TYPES: Mapping[str, pa.DataType] = {
    "split": pa.string(),
    "component_id": pa.string(),
    "final_audit_status": pa.string(),
}

_AUDIT_ARROW_TYPES: Mapping[str, pa.DataType] = {
    "descriptor_id": pa.string(),
    "target_key": pa.string(),
    "clone_group_id": pa.string(),
    "intervention_id": pa.string(),
    "pair_evidence_sha256": pa.string(),
    "kind": pa.string(),
    "horizon": pa.string(),
    "source_frame_horizon": pa.string(),
    "event_ordinal": pa.int64(),
    "event_time_seconds": pa.float64(),
    "event_time_block": pa.int16(),
    "current_node_id": pa.int64(),
    "baseline_next_node_id": pa.int64(),
    "intervention_next_node_id": pa.int64(),
    "goal_node_id": pa.int64(),
    "source_node_id": pa.int64(),
    "task_class": pa.string(),
    "pre_action_retry_count": pa.int64(),
    "pre_action_decision_count": pa.int64(),
    "pre_action_status": pa.string(),
    "pre_action_pending_merge": pa.bool_(),
    "safety_hard_gate_pass": pa.bool_(),
    "runtime_feature_cache_matched": pa.bool_(),
    "runtime_dynamic_feature_complete": pa.bool_(),
}


def model_ready_arrow_schema() -> pa.Schema:
    """Return the single explicit schema shared by all three Parquet files."""

    fields: list[pa.Field] = []
    for name in DEPLOYMENT_FEATURES:
        fields.append(
            pa.field(
                name,
                pa.float64(),
                nullable=name in DYNAMIC_DEPLOYMENT_FEATURES,
                metadata={b"g4irsf16.column_partition": b"deployable_feature"},
            )
        )
    for name in LABEL_COLUMNS:
        nullable = name in {
            "risk_adjusted_utility_seconds",
            "risk_profile",
            "externality_nonempty",
            "external_affected_count",
            "realized_affected_count",
            "other_bag_mean_harm_seconds",
            "other_bag_max_harm_seconds",
            "other_bag_p95_harm_seconds",
            "other_bag_cvar95_harm_seconds",
            "extra_deadline_miss_count",
            "system_original_entry_delta_seconds",
        }
        fields.append(
            pa.field(
                name,
                _LABEL_ARROW_TYPES[name],
                nullable=nullable,
                metadata={b"g4irsf16.column_partition": b"label_only"},
            )
        )
    for name in SPLIT_COLUMNS:
        fields.append(
            pa.field(
                name,
                _SPLIT_ARROW_TYPES[name],
                nullable=False,
                metadata={b"g4irsf16.column_partition": b"split_only"},
            )
        )
    for name in AUDIT_COLUMNS:
        nullable = name in {
            "intervention_next_node_id",
            "pre_action_retry_count",
            "pre_action_decision_count",
            "pre_action_status",
            "pre_action_pending_merge",
        }
        fields.append(
            pa.field(
                name,
                _AUDIT_ARROW_TYPES[name],
                nullable=nullable,
                metadata={b"g4irsf16.column_partition": b"audit_identity"},
            )
        )
    metadata = {
        b"czr005.schema": DATASET_SCHEMA.encode("utf-8"),
        b"g4irsf16.column_partitions": json.dumps(
            COLUMN_PARTITIONS,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        b"g4irsf16.dynamic_missing_policy": (
            b"ARROW_NULL_UNLESS_MATCHED_FROZEN_F2_RUNTIME_FEATURE_CACHE"
        ),
        b"g4irsf16.join_contract": (
            b"LABEL_DESCRIPTOR_ID_TO_TARGET_DESCRIPTOR_ID_AND_TARGET_KEY_PLUS_PAIR_HASH"
        ),
        b"g4irsf16.risk_profile": json.dumps(
            {"name": RISK_PROFILE, "weights": RISK_BALANCED_WEIGHTS},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
    }
    return pa.schema(fields, metadata=metadata)


def rows_to_arrow(rows: Sequence[Mapping[str, Any]]) -> pa.Table:
    table = pa.Table.from_pylist(list(rows), schema=model_ready_arrow_schema())
    table.validate(full=True)
    return table


def _inventory(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["kind"]), str(row["horizon"]), str(row["signed_class"]))].append(row)
    result: list[dict[str, Any]] = []
    for (kind, horizon, signed_class), members in sorted(grouped.items()):
        benefits = [float(row["direct_benefit_seconds"]) for row in members]
        result.append(
            {
                "schema": "czr005.g4irsf16.label_inventory.v1",
                "kind": kind,
                "horizon": horizon,
                "signed_class": signed_class,
                "row_count": len(members),
                "component_count": len({row["component_id"] for row in members}),
                "direct_benefit_mean_seconds": statistics.fmean(benefits),
                "direct_benefit_min_seconds": min(benefits),
                "direct_benefit_max_seconds": max(benefits),
                "h_system_available_count": sum(
                    bool(row["h_system_available"]) for row in members
                ),
                "externality_nonempty_count": sum(
                    row["externality_nonempty"] is True for row in members
                ),
            }
        )
    return tuple(result)


def _support(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["kind"]), str(row["split"]), str(row["signed_class"]))].append(row)
    result: list[dict[str, Any]] = []
    for (kind, split, signed_class), members in sorted(grouped.items()):
        result.append(
            {
                "schema": "czr005.g4irsf16.split_support.v1",
                "kind": kind,
                "split": split,
                "signed_class": signed_class,
                "row_count": len(members),
                "component_count": len({row["component_id"] for row in members}),
                "h_system_row_count": sum(
                    bool(row["h_system_available"]) for row in members
                ),
                "runtime_feature_cache_matched_count": sum(
                    bool(row["runtime_feature_cache_matched"]) for row in members
                ),
                "runtime_dynamic_feature_complete_count": sum(
                    bool(row["runtime_dynamic_feature_complete"]) for row in members
                ),
                "runtime_trace_mapped_feature_complete_count": sum(
                    all(row[name] is not None for name in TRACE_MAPPED_DYNAMIC_FEATURES)
                    for row in members
                ),
                "selection_allowed": split != "final_audit",
                "audit_status": (
                    "SEALED_NOT_CONSUMED"
                    if split == "final_audit"
                    else "NOT_FINAL_AUDIT"
                ),
            }
        )
    return tuple(result)


def _component_manifest(
    rows: Sequence[Mapping[str, Any]],
    groups: Sequence[Mapping[str, Any]],
    source_components: Mapping[str, Any],
    runtime_cache_path: str | None,
) -> dict[str, Any]:
    rows_by_component: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_component[str(row["component_id"])].append(row)
    assignments = []
    for component_id in sorted(rows_by_component):
        members = rows_by_component[component_id]
        assigned = split_for_component(component_id)
        if {row["split"] for row in members} != {assigned}:
            raise ModelReadyDataError("COMPONENT_SPLIT_INCONSISTENT")
        assignments.append(
            {
                "component_id": component_id,
                "split": assigned,
                "row_count": len(members),
                "kind_counts": dict(sorted(Counter(row["kind"] for row in members).items())),
            }
        )

    clone_splits: dict[str, set[str]] = defaultdict(set)
    raw_task_splits: dict[int, set[str]] = defaultdict(set)
    for group in groups:
        component_id = str(group.get("component_id"))
        assigned = split_for_component(component_id)
        for clone_id in _require_list(group.get("clone_group_ids"), "clone_group_ids"):
            clone_splits[str(clone_id)].add(assigned)
        for raw_task_id in _require_list(group.get("raw_task_ids"), "raw_task_ids"):
            raw_task_splits[_plain_int(raw_task_id, "raw_task_id")].add(assigned)
    clone_cross = sum(len(splits) > 1 for splits in clone_splits.values())
    raw_cross = sum(len(splits) > 1 for splits in raw_task_splits.values())
    if clone_cross or raw_cross:
        raise ModelReadyDataError(
            f"FOUR_WAY_SPLIT_CONTAMINATION:clone={clone_cross}:raw={raw_cross}"
        )

    split_rows = Counter(str(row["split"]) for row in rows)
    split_components = Counter(item["split"] for item in assignments)
    by_kind: dict[str, dict[str, int]] = {}
    by_signed: dict[str, dict[str, int]] = {}
    for split in SPLIT_NAMES:
        members = [row for row in rows if row["split"] == split]
        by_kind[split] = dict(sorted(Counter(row["kind"] for row in members).items()))
        by_signed[split] = dict(
            sorted(Counter(row["signed_class"] for row in members).items())
        )
    dynamic_null_counts = {
        name: sum(row[name] is None for row in rows)
        for name in DYNAMIC_DEPLOYMENT_FEATURES
    }
    fully_observed_dynamic = [
        name for name, null_count in dynamic_null_counts.items() if null_count == 0
    ]
    return {
        "schema": SPLIT_MANIFEST_SCHEMA,
        "seed": SPLIT_SEED,
        "method": "SHA256_SEED_COMPONENT_ID_FIRST64_MOD10000",
        "bucket_intervals": [
            {"split": name, "lower_inclusive": lower, "upper_exclusive": upper}
            for name, lower, upper in SPLIT_BUCKETS
        ],
        "source_component_artifact": SOURCE_COMPONENTS.as_posix(),
        "source_component_schema": source_components.get("schema"),
        "source_component_policy": source_components.get("split_policy"),
        "source_split_assignments_consumed": False,
        "hard_leakage_edges": ["clone_group_id", "raw_task_id"],
        "balance_only_diagnostics": [
            "source_node_id",
            "event_time_block",
            "current_node_id",
            "kind",
        ],
        "component_count": len(assignments),
        "row_count": len(rows),
        "split_row_counts": {name: split_rows[name] for name in SPLIT_NAMES},
        "split_component_counts": {
            name: split_components[name] for name in SPLIT_NAMES
        },
        "split_kind_counts": by_kind,
        "split_signed_class_counts": by_signed,
        "clone_group_cross_split_count": clone_cross,
        "raw_task_cross_split_count": raw_cross,
        "component_assignments": assignments,
        "column_partitions": COLUMN_PARTITIONS,
        "runtime_feature_cache": {
            "path": runtime_cache_path,
            "missing_policy": (
                "ARROW_NULL_UNLESS_MATCHED_FROZEN_F2_RUNTIME_FEATURE_CACHE"
            ),
            "matched_row_count": sum(
                bool(row["runtime_feature_cache_matched"]) for row in rows
            ),
            "fully_complete_dynamic_row_count": sum(
                bool(row["runtime_dynamic_feature_complete"]) for row in rows
            ),
            "dynamic_feature_null_counts": dynamic_null_counts,
            "fully_observed_dynamic_columns": fully_observed_dynamic,
            "fully_observed_dynamic_column_count": len(fully_observed_dynamic),
            "dynamic_column_coverage": (
                len(fully_observed_dynamic) / len(DYNAMIC_DEPLOYMENT_FEATURES)
            ),
            "trace_mapped_feature_complete_row_count": sum(
                all(row[name] is not None for name in TRACE_MAPPED_DYNAMIC_FEATURES)
                for row in rows
            ),
            "matched_live_trace_projection": {
                "i3_candidate": "FORMAL_INTERVENTION_NEXT_NODE",
                "i4_candidate": "FROZEN_F2_BASELINE_RELEASE_NEXT_NODE",
                "current_queue_length": "features.current_local_queue_length",
                "current_next_available_wait_seconds": (
                    "features.current_calendar_wait_seconds"
                ),
                "target_queue_and_incoming": (
                    "features.candidates[action].target_queue_length_and_"
                    "target_scheduled_incoming"
                ),
                "target_next_available_wait_seconds": (
                    "features.candidates[action].target_calendar_delay_seconds"
                ),
                "f2_model_margin": "features.f2.model_margin",
                "f2_raw_score": (
                    "features.candidates[f2_baseline].scorer_raw_score"
                ),
                "recent_visit_count": "COUNT_ACTION_NODE_IN_SHORT_HISTORY",
                "short_history_repeat_count": (
                    "LEN_SHORT_HISTORY_MINUS_UNIQUE_NODE_COUNT"
                ),
                "advertised_fault": (
                    "features.candidates[action].advertised_fault"
                ),
                "feature_realizability_pruning": {
                    "removed_from_deployment_schema": [
                        "downstream_pressure",
                        "has_physical_fault",
                    ],
                    "downstream_pressure_reason": (
                        "NOT_EXPOSED_AS_EXACT_LOCAL_RUNTIME_SCALAR"
                    ),
                    "has_physical_fault_owner": (
                        "SUPERVISOR_PHYSICAL_SHIELD_STATE"
                    ),
                    "proxy_substitution_allowed": False,
                },
            },
        },
        "final_audit": {
            "status": "SEALED",
            "row_count": split_rows["final_audit"],
            "row_level_results_consumed_for_selection": False,
            "model_training_allowed": False,
            "rule_or_threshold_selection_allowed": False,
            "support_census_only": True,
        },
        "risk_adjusted_utility": {
            "profile": RISK_PROFILE,
            "weights": dict(RISK_BALANCED_WEIGHTS),
            "h_bag_without_h_system_is_null": True,
        },
    }


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def _report(rows: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]) -> str:
    class_rows = []
    for kind in ("I3", "I4"):
        members = [row for row in rows if row["kind"] == kind]
        counts = Counter(row["signed_class"] for row in members)
        class_rows.append(
            [kind, len(members), counts["BENEFICIAL"], counts["NEUTRAL"], counts["HARMFUL"]]
        )
    split_rows = []
    for kind in ("I3", "I4"):
        for split in SPLIT_NAMES:
            members = [
                row for row in rows if row["kind"] == kind and row["split"] == split
            ]
            counts = Counter(row["signed_class"] for row in members)
            split_rows.append(
                [
                    kind,
                    split,
                    len(members),
                    counts["BENEFICIAL"],
                    counts["NEUTRAL"],
                    counts["HARMFUL"],
                ]
            )
    missing_rows = []
    for name in DEPLOYMENT_FEATURES:
        missing_rows.append(
            [name, sum(row[name] is None for row in rows), "dynamic" if name in DYNAMIC_DEPLOYMENT_FEATURES else "static"]
        )
    subgroup_rows = []
    for kind in ("I3", "I4"):
        members = [row for row in rows if row["kind"] == kind]
        subgroup_rows.append(
            [
                kind,
                len({row["current_node_id"] for row in members}),
                len({row["source_node_id"] for row in members}),
                len({row["goal_node_id"] for row in members}),
                len({row["event_time_block"] for row in members}),
                ", ".join(sorted({str(row["task_class"]) for row in members})),
            ]
        )
    hsystem = [
        row
        for row in rows
        if row["h_system_available"] and row["split"] != "final_audit"
    ]
    external_nonempty = sum(row["externality_nonempty"] is True for row in hsystem)
    max_external = max(int(row["external_affected_count"]) for row in hsystem)
    max_harm = max(float(row["other_bag_max_harm_seconds"]) for row in hsystem)
    max_cvar = max(float(row["other_bag_cvar95_harm_seconds"]) for row in hsystem)
    i4 = [row for row in rows if row["kind"] == "I4"]
    i4_counts = Counter(row["signed_class"] for row in i4)
    i4_non_audit_positive = {
        split: sum(
            row["signed_class"] == "BENEFICIAL" and row["split"] == split
            for row in i4
        )
        for split in ("train", "calibration", "validation")
    }
    i4_selectable_beneficial = sum(i4_non_audit_positive.values())
    runtime_cache_matched = sum(
        bool(row["runtime_feature_cache_matched"]) for row in rows
    )
    fully_complete_dynamic = sum(
        bool(row["runtime_dynamic_feature_complete"]) for row in rows
    )
    if runtime_cache_matched:
        runtime_cache_summary = (
            f"Matched live runtime feature rows: {runtime_cache_matched}/{len(rows)}. "
            f"Rows complete across all {len(DYNAMIC_DEPLOYMENT_FEATURES)} dynamic "
            f"deployment columns: {fully_complete_dynamic}/{len(rows)}. "
            "`downstream_pressure` was removed because no exact local runtime "
            "scalar is exposed; physical-fault state remains owned by the "
            "supervisor shield. No shield/risk proxy was substituted."
        )
    else:
        runtime_cache_summary = (
            "No matched live runtime feature cache was supplied. All exact dynamic "
            "F2/queue/calendar/history columns remain Arrow null."
        )
    return "\n".join(
        [
            "# G4IRSF16 Stage 16A model-ready data report",
            "",
            "## Outcome",
            "",
            (
                "The formal G4IRSF15 release was projected into separated I3, I4, "
                "and H_system Parquet datasets. No model was trained. The final-audit "
                "partition is sealed and its row-level outcomes were not used for rule, "
                "threshold, or model selection."
            ),
            "",
            "## Join and leakage contract",
            "",
            "- Labels join the target-address frame only by `descriptor_id` (one-to-one).",
            "- Compact causal evidence joins by `target_key`, with the entry pair hash required to equal the formal label pair hash.",
            "- H_system other-bag tails use only `externality_runtime_bag_ids`; harm is `max(0, treatment completion - baseline completion)`.",
            "- H_bag has no observed system externality. Its externality and risk-adjusted utility fields remain Arrow null, not zero.",
            "- Airport-wide target-address `queued/merge/fault` counters are forbidden and are not local feature proxies.",
            "- Missing exact F2 queue/calendar/history/score features remain Arrow null unless a matched runtime feature cache is supplied.",
            "",
            "## Label inventory",
            "",
            _markdown_table(
                ["Kind", "Rows", "Beneficial", "Neutral", "Harmful"],
                class_rows,
            ),
            "",
            "## Four-way support",
            "",
            _markdown_table(
                ["Kind", "Split", "Rows", "Beneficial", "Neutral", "Harmful"],
                split_rows,
            ),
            "",
            (
                f"The pure component hash produced {manifest['split_row_counts']}. "
                "Source/time/node/kind are balance diagnostics, not union edges, because "
                "coarse unioning collapses the formal panel into giant components."
            ),
            "",
            "## Feature availability",
            "",
            runtime_cache_summary,
            "",
            _markdown_table(["Deployment feature", "Null rows", "Origin"], missing_rows),
            "",
            "`pre_action_retry_count` and `pre_action_decision_count` are retained only in the audit partition because the frozen deployment schema does not include them.",
            "",
            "## Subgroup coverage (audit identities only)",
            "",
            _markdown_table(
                ["Kind", "Nodes", "Sources", "Goals", "Hours", "Task classes"],
                subgroup_rows,
            ),
            "",
            "## Sparse H_system externality (selectable partitions only)",
            "",
            (
                f"Selectable H_system rows: {len(hsystem)}; nonempty external sets: "
                f"{external_nonempty}; maximum external affected count: {max_external}; "
                f"maximum positive other-bag harm: {max_harm:.6f} s; maximum CVaR95: "
                f"{max_cvar:.6f} s. P95 uses linear type-7 interpolation and CVaR95 "
                "uses the largest `ceil(0.05*n)` clipped harms."
            ),
            "Final-audit H_system outcomes are excluded from every tail statistic above.",
            "",
            (
                "Risk-balanced utility is fixed before training as direct benefit minus "
                f"the penalties {dict(RISK_BALANCED_WEIGHTS)}. It is null for H_bag rows."
            ),
            "",
            "## Learnability boundary exposed by Stage 16A",
            "",
            (
                "- `I3_REROUTE_MODEL_NOT_AUTHORIZED`: train contains only 13 "
                "beneficial I3 rows and all selectable partitions contain 19, already "
                "below the preregistered train minimum of 24. This conclusion does not "
                "require opening final audit."
            ),
            (
                f"- I4 support screen: the published full-panel census is "
                f"beneficial={i4_counts['BENEFICIAL']}, harmful={i4_counts['HARMFUL']}; "
                f"selectable positives={i4_non_audit_positive} "
                f"(total={i4_selectable_beneficial}). Because final-audit labels cannot "
                "authorize training, the selectable total remains below 24: "
                "`NOT_AUTHORIZED`."
            ),
            "- H_system extra-deadline-miss labels are degenerate at zero in the formal panel; a deadline-miss classifier is not trainable from this release.",
            "",
            "## Final-audit seal",
            "",
            (
                f"`final_audit` contains {manifest['final_audit']['row_count']} rows. "
                "The builder records the predeclared descriptive support census, but "
                "authorization ignores final-audit labels and writes "
                "`SEALED_NOT_CONSUMED`; it performs no fitting, threshold search, ranking, "
                "or candidate selection."
            ),
            "",
        ]
    )


def build_model_ready_data(
    root: str | Path,
    *,
    runtime_feature_cache: str | Path | None = None,
) -> ModelReadyBuild:
    """Build all Stage-16A rows in memory from the formal G4IRSF15 release."""

    repository = Path(root).resolve()
    runtime_cache_path = (
        Path(runtime_feature_cache).resolve()
        if runtime_feature_cache is not None
        else None
    )
    runtime_cache_manifest_path: str | None = None
    if runtime_cache_path is not None:
        try:
            runtime_cache_manifest_path = runtime_cache_path.relative_to(
                repository
            ).as_posix()
        except ValueError:
            runtime_cache_manifest_path = str(runtime_cache_path)
    labels = _read_zstd_jsonl(repository / LABEL_DATASET)
    if len(labels) != 2172:
        raise ModelReadyDataError(f"FORMAL_LABEL_COUNT_MISMATCH:{len(labels)}")
    if any(row.get("schema") != "czr005.g4irsf15.causal_label.v1" for row in labels):
        raise ModelReadyDataError("FORMAL_LABEL_SCHEMA_MISMATCH")
    if any(row.get("eligible_causal_label") is not True for row in labels):
        raise ModelReadyDataError("INELIGIBLE_FORMAL_LABEL_PRESENT")
    descriptor_ids = [str(row.get("descriptor_id")) for row in labels]
    target_keys = [str(row.get("target_key")) for row in labels]
    if len(descriptor_ids) != len(set(descriptor_ids)):
        raise ModelReadyDataError("FORMAL_DESCRIPTOR_ID_DUPLICATE")
    if len(target_keys) != len(set(target_keys)):
        raise ModelReadyDataError("FORMAL_TARGET_KEY_DUPLICATE")
    for label, descriptor_id, target_key in zip(
        labels,
        descriptor_ids,
        target_keys,
        strict=True,
    ):
        if target_key != f"{descriptor_id}:{label.get('horizon')}":
            raise ModelReadyDataError("FORMAL_TARGET_KEY_NOT_DESCRIPTOR_HORIZON")

    target_rows = _read_zstd_jsonl(repository / TARGET_FRAME)
    targets = _target_index(target_rows, set(descriptor_ids))
    label_manifest = _require_mapping(
        _read_json(repository / LABEL_MANIFEST),
        "label_manifest",
    )
    pair_entries = _load_pair_index(
        repository,
        label_manifest,
        set(target_keys),
    )
    source_components = _require_mapping(
        _read_json(repository / SOURCE_COMPONENTS),
        "source_components",
    )
    if source_components.get("split_contamination_count") != 0:
        raise ModelReadyDataError("SOURCE_SPLIT_CONTAMINATED")
    target_components, groups = _component_index(
        source_components,
        set(target_keys),
    )

    task_rows = _read_jsonl(repository / TASK_PATH)
    tasks: dict[str, Mapping[str, Any]] = {}
    for task in task_rows:
        segment_id = str(task.get("segment_id"))
        if segment_id in tasks:
            raise ModelReadyDataError("TASK_SEGMENT_ID_DUPLICATE")
        tasks[segment_id] = task
    nodes, edges, heuristic = _map_lookups(
        _require_mapping(_read_json(repository / MAP_PATH), "map")
    )
    runtime_by_descriptor, runtime_by_target = _load_runtime_feature_cache(
        runtime_cache_path
    )

    rows: list[dict[str, Any]] = []
    for label in sorted(labels, key=lambda row: str(row["target_key"])):
        descriptor_id = str(label["descriptor_id"])
        target_key = str(label["target_key"])
        target = targets[descriptor_id]
        segment_id = str(target.get("segment_id"))
        try:
            task = tasks[segment_id]
        except KeyError as error:
            raise ModelReadyDataError(f"TASK_SEGMENT_JOIN_MISSING:{segment_id}") from error
        rows.append(
            _build_row(
                label=label,
                target=target,
                pair_entry=pair_entries[target_key],
                component_id=target_components[target_key],
                task=task,
                nodes=nodes,
                edges=edges,
                heuristic=heuristic,
                runtime_by_descriptor=runtime_by_descriptor,
                runtime_by_target=runtime_by_target,
            )
        )

    if Counter(row["kind"] for row in rows) != Counter({"I3": 1086, "I4": 1086}):
        raise ModelReadyDataError("FORMAL_KIND_COUNTS_MISMATCH")
    if sum(row["h_system_available"] for row in rows) != 256:
        raise ModelReadyDataError("FORMAL_H_SYSTEM_COUNT_MISMATCH")
    if any(
        row[name] is not None
        for row in rows
        if row["horizon"] == "H_bag"
        for name in (
            "risk_adjusted_utility_seconds",
            "externality_nonempty",
            "external_affected_count",
            "realized_affected_count",
            "other_bag_mean_harm_seconds",
            "other_bag_max_harm_seconds",
            "other_bag_p95_harm_seconds",
            "other_bag_cvar95_harm_seconds",
            "extra_deadline_miss_count",
            "system_original_entry_delta_seconds",
        )
    ):
        raise ModelReadyDataError("H_BAG_EXTERNALITY_WAS_IMPUTED")

    rows_by_dataset = {
        "i3_route": tuple(row for row in rows if row["kind"] == "I3"),
        "i4_hold": tuple(row for row in rows if row["kind"] == "I4"),
        "hsystem_externality": tuple(
            row for row in rows if row["h_system_available"]
        ),
    }
    manifest = _component_manifest(
        rows,
        groups,
        source_components,
        runtime_cache_manifest_path,
    )
    inventory = _inventory(rows)
    support = _support(rows)
    report = _report(rows, manifest)
    return ModelReadyBuild(
        rows_by_dataset=rows_by_dataset,
        split_manifest=manifest,
        inventory_rows=inventory,
        support_rows=support,
        report_markdown=report,
    )


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ModelReadyDataError(f"EMPTY_CSV:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_model_ready_data(
    root: str | Path,
    build: ModelReadyBuild,
) -> dict[str, Path]:
    """Write the three Parquets plus the Stage-16A scientific deliverables."""

    repository = Path(root).resolve()
    written: dict[str, Path] = {}
    output_inventory: dict[str, Any] = {}
    for name, relative_path in DATASET_OUTPUTS.items():
        path = repository / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        table = rows_to_arrow(build.rows_by_dataset[name])
        pq.write_table(
            table,
            path,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
            data_page_version="2.0",
        )
        read_back = pq.read_table(path)
        if read_back.num_rows != table.num_rows or read_back.schema != table.schema:
            raise ModelReadyDataError(f"PARQUET_ROUND_TRIP_MISMATCH:{name}")
        written[name] = path
        output_inventory[name] = {
            "path": relative_path.as_posix(),
            "row_count": table.num_rows,
            "column_count": table.num_columns,
            "byte_count": path.stat().st_size,
            "schema": DATASET_SCHEMA,
        }

    manifest = dict(build.split_manifest)
    manifest["outputs"] = output_inventory
    split_path = repository / SPLIT_MANIFEST_OUTPUT
    split_path.parent.mkdir(parents=True, exist_ok=True)
    split_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    _write_csv(repository / LABEL_INVENTORY_OUTPUT, build.inventory_rows)
    _write_csv(repository / SPLIT_SUPPORT_OUTPUT, build.support_rows)
    report_path = repository / MODEL_READY_REPORT_OUTPUT
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(build.report_markdown, encoding="utf-8")
    written.update(
        {
            "split_manifest": split_path,
            "label_inventory": repository / LABEL_INVENTORY_OUTPUT,
            "split_support": repository / SPLIT_SUPPORT_OUTPUT,
            "report": report_path,
        }
    )
    return written


def build_and_write_model_ready_data(
    root: str | Path,
    *,
    runtime_feature_cache: str | Path | None = None,
) -> tuple[ModelReadyBuild, dict[str, Path]]:
    build = build_model_ready_data(
        root,
        runtime_feature_cache=runtime_feature_cache,
    )
    return build, write_model_ready_data(root, build)
