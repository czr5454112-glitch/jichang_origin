"""Decision-level trace validation and deterministic hard-case sampling.

This module is deliberately independent from a particular runtime binding.  It
accepts plain mappings emitted by the C++ event runtime, canonicalises candidate
records, validates graph/action semantics, links Java source-release metadata,
and builds an order-independent stratified reservoir sample.

Runtime observations and post-hoc outcomes stay separate throughout this
module.  A caller must pass outcomes through the dedicated ``outcomes``
mapping; outcome fields are never copied into the decision trace.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_ID = "czr005.g4irsf11.decision_trace.v1"
SCHEMA_VERSION = 1
CANDIDATE_ORDERING = "next_node_ascending"
MODEL_SCORE_SEMANTICS = "lower_is_better_cost"
DEFAULT_SAMPLING_SEED = "czr005-g4irsf11-stratified-reservoir-v1"

# The G4IRSF11 event runtime exposes only these bounded local/static candidate
# observations to the scorer.  Keeping an allow-list here turns lineage from a
# prose claim into a fail-closed executable contract.
EVENT_RUNTIME_FEATURE_SOURCES: dict[str, tuple[str, ...]] = {
    "static_potential": ("graph.static_potential", "goal_node", "candidate_records[].next_node"),
    "travel_time": ("graph.edge_travel_time", "current_node", "candidate_records[].next_node"),
    "target_queue_length": ("local_neighbor.queue_length",),
    "target_scheduled_incoming": ("local_neighbor.scheduled_incoming",),
    "corridor_next_available": ("local_edge.next_available_time", "event_time"),
    "target_next_available": ("local_neighbor.next_available_time", "event_time"),
    "advertised_fault": ("congestion_beacon.advertised_fault",),
    "fault_message_age_seconds": (
        "event_time",
        "congestion_beacon.fault_message_timestamp",
    ),
    "recent_visit_count": ("short_history", "candidate_records[].next_node"),
    "two_hop_queue_pressure": ("bounded_two_hop.queue_summary",),
}

# These fields must never appear in a runtime decision row, even if nested.
# ``short_history`` is intentionally allowed; it is bounded past state rather
# than a completed/future route.
FORBIDDEN_TRACE_KEYS = frozenset(
    {
        "teacher_next",
        "teacher_next_node",
        "teacher_path",
        "teacher_route",
        "full_cie_route_suffix",
        "future_path",
        "future_path_suffix",
        "future_route",
        "future_route_suffix",
        "future_schedule",
        "future_sipp_schedule",
        "route_path",
        "route_suffix",
        "full_path",
        "complete_path",
        "path_history",
        "reached_goal",
        "goal_reached",
        "finish_time",
        "route_finish_time",
        "bag_tth",
        "total_tth",
        "post_hoc_success",
        "post_hoc_success_flag",
        "outcome",
        "outcomes",
        "label",
        "labels",
        "label_source",
    }
)

_FORBIDDEN_DERIVED_KEY_TOKENS = (
    "teacher",
    "future_",
    "post_hoc",
    "posthoc",
    "route_suffix",
    "path_suffix",
    "full_route",
    "full_path",
    "complete_path",
    "reached_goal",
    "goal_reached",
    "finish_time",
    "bag_tth",
    "total_tth",
    "outcome",
    "label_source",
)

_TRACE_ALIASES = {
    "selected_next_node": "selected_next",
    "full_cie_astar_used": "full_astar_used",
    "fallback_action": "fallback_selected_next",
    "fallback_selected_next_node": "fallback_selected_next",
}

_ALLOWED_TOP_LEVEL = frozenset(
    {
        "schema_id",
        "schema_version",
        "decision_id",
        "task_id",
        "segment_id",
        "event_time",
        "current_node",
        "goal_node",
        "candidate_next_nodes",
        "candidate_records",
        "model_prediction",
        "model_score_semantics",
        "model_margin",
        "risk_gate_triggered",
        "fallback_selected_next",
        "selected_next",
        "decision_source",
        "rule_reason",
        "local_snapshot",
        "short_history",
        "full_astar_used",
        "model_fallback_disagreement",
        "candidate_ordering",
        "candidate_order_digest",
        "metadata",
    }
)

_ALLOWED_LOCAL_SNAPSHOT_KEYS = frozenset(
    {
        "junction_queue_length",
        "next_available_time",
        "faulted_outgoing_count",
        "message_age_seconds",
        "downstream_pressure",
        "recent_throughput",
        "local_wait_seconds",
        "active_reservation_count",
    }
)

_REPEAT_PATTERNS = (
    re.compile(r"(?i)(?:[_-]?repeat[_-]?\d+)$"),
    re.compile(r"(?i)(?:[_-]?rep[_-]?\d+)$"),
    re.compile(r"(?i)(?:[_-]?run[_-]?\d+)$"),
)


class DecisionTraceValidationError(ValueError):
    """Raised when a decision row violates runtime/data semantics."""


@dataclass(frozen=True)
class SamplingConfig:
    """Configuration for the deterministic stratified reservoir."""

    limit: int = 50_000
    minimum_per_stratum: int = 1
    maximum_per_stratum: int = 64
    seed: str = DEFAULT_SAMPLING_SEED

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError("sampling limit must be positive")
        if self.minimum_per_stratum < 0:
            raise ValueError("minimum_per_stratum must be non-negative")
        if self.maximum_per_stratum <= 0:
            raise ValueError("maximum_per_stratum must be positive")
        if self.minimum_per_stratum > self.maximum_per_stratum:
            raise ValueError("minimum_per_stratum cannot exceed maximum_per_stratum")
        if not self.seed:
            raise ValueError("sampling seed must be non-empty")


@dataclass(frozen=True)
class SamplingResult:
    """Sample rows, balance rows, and exact population statistics."""

    rows: tuple[dict[str, Any], ...]
    balance_rows: tuple[dict[str, Any], ...]
    statistics: dict[str, Any]


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DecisionTraceValidationError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise DecisionTraceValidationError(f"{field} must be a finite number")
    return result


def _required_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise DecisionTraceValidationError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise DecisionTraceValidationError(f"{field} must be an integer") from exc
    if isinstance(value, float) and value != result:
        raise DecisionTraceValidationError(f"{field} must be an integer")
    return result


def _required_text(value: Any, field: str) -> str:
    if value is None:
        raise DecisionTraceValidationError(f"{field} must be non-empty text")
    result = str(value).strip()
    if not result:
        raise DecisionTraceValidationError(f"{field} must be non-empty text")
    return result


def _required_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise DecisionTraceValidationError(f"{field} must be a boolean")
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _normalised_key(value: Any) -> str:
    return str(value).strip().lower().replace("-", "_")


def _walk_keys(value: Any, path: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            yield child_path, _normalised_key(key)
            yield from _walk_keys(child, child_path)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            yield from _walk_keys(child, f"{path}[{index}]")


def assert_no_future_or_label_leakage(row: Mapping[str, Any]) -> None:
    """Reject explicit and derived future-route/post-hoc fields recursively."""

    violations = [
        path
        for path, key in _walk_keys(row)
        if key in FORBIDDEN_TRACE_KEYS or any(token in key for token in _FORBIDDEN_DERIVED_KEY_TOKENS)
    ]
    if violations:
        raise DecisionTraceValidationError(
            "forbidden future-route or post-hoc field(s): " + ", ".join(sorted(violations))
        )


def _canonical_features(value: Any, candidate_index: int) -> dict[str, float | int | bool]:
    if not isinstance(value, Mapping):
        raise DecisionTraceValidationError(f"candidate_records[{candidate_index}].features must be an object")
    result: dict[str, float | int | bool] = {}
    for raw_name in sorted(value, key=str):
        name = _required_text(raw_name, f"candidate_records[{candidate_index}].features key")
        feature_value = value[raw_name]
        if isinstance(feature_value, bool):
            result[name] = feature_value
        elif isinstance(feature_value, int):
            result[name] = feature_value
        else:
            result[name] = _finite_number(
                feature_value, f"candidate_records[{candidate_index}].features.{name}"
            )
    return result


def _candidate_records_from_row(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_records = row.get("candidate_records")
    if raw_records is not None:
        if not isinstance(raw_records, Sequence) or isinstance(raw_records, (str, bytes, bytearray)):
            raise DecisionTraceValidationError("candidate_records must be a non-empty array")
        records: list[dict[str, Any]] = []
        for index, raw_record in enumerate(raw_records):
            if not isinstance(raw_record, Mapping):
                raise DecisionTraceValidationError(f"candidate_records[{index}] must be an object")
            unknown = set(raw_record) - {
                "next_node",
                "features",
                "model_score",
                "shield_allowed",
                "shield_reason",
            }
            if unknown:
                raise DecisionTraceValidationError(
                    f"candidate_records[{index}] has unknown field(s): {sorted(unknown)}"
                )
            record = {
                "next_node": _required_int(raw_record.get("next_node"), f"candidate_records[{index}].next_node"),
                "features": _canonical_features(raw_record.get("features"), index),
                "model_score": _finite_number(
                    raw_record.get("model_score"), f"candidate_records[{index}].model_score"
                ),
            }
            if "shield_allowed" in raw_record:
                record["shield_allowed"] = _required_bool(
                    raw_record["shield_allowed"], f"candidate_records[{index}].shield_allowed"
                )
            if "shield_reason" in raw_record:
                record["shield_reason"] = str(raw_record["shield_reason"] or "")
            records.append(record)
        return records

    raw_nodes = row.get("candidate_next_nodes")
    raw_features = row.get("candidate_features")
    raw_scores = row.get("model_scores")
    if raw_nodes is None or raw_features is None or raw_scores is None:
        raise DecisionTraceValidationError(
            "candidate_records is required (or candidate_next_nodes/candidate_features/model_scores adapter fields)"
        )
    if not all(isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) for value in (raw_nodes, raw_features, raw_scores)):
        raise DecisionTraceValidationError("candidate adapter fields must be arrays")
    if not (len(raw_nodes) == len(raw_features) == len(raw_scores)):
        raise DecisionTraceValidationError("candidate adapter fields must have equal lengths")
    return [
        {
            "next_node": _required_int(node, f"candidate_next_nodes[{index}]"),
            "features": _canonical_features(raw_features[index], index),
            "model_score": _finite_number(raw_scores[index], f"model_scores[{index}]"),
        }
        for index, node in enumerate(raw_nodes)
    ]


def _canonical_local_snapshot(value: Any) -> dict[str, float | int]:
    if not isinstance(value, Mapping):
        raise DecisionTraceValidationError("local_snapshot must be an object")
    unknown = set(value) - _ALLOWED_LOCAL_SNAPSHOT_KEYS
    if unknown:
        raise DecisionTraceValidationError(f"local_snapshot has unknown field(s): {sorted(unknown)}")
    required = {
        "junction_queue_length",
        "next_available_time",
        "faulted_outgoing_count",
        "message_age_seconds",
    }
    missing = required - set(value)
    if missing:
        raise DecisionTraceValidationError(f"local_snapshot missing field(s): {sorted(missing)}")
    result: dict[str, float | int] = {}
    for name in sorted(value):
        if name in {"junction_queue_length", "faulted_outgoing_count", "active_reservation_count"}:
            number = _required_int(value[name], f"local_snapshot.{name}")
            if number < 0:
                raise DecisionTraceValidationError(f"local_snapshot.{name} cannot be negative")
            result[name] = number
        else:
            number = _finite_number(value[name], f"local_snapshot.{name}")
            if name in {"message_age_seconds", "downstream_pressure", "recent_throughput", "local_wait_seconds"} and number < 0:
                raise DecisionTraceValidationError(f"local_snapshot.{name} cannot be negative")
            result[name] = number
    return result


def _canonical_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise DecisionTraceValidationError("metadata must be an object")
    # Metadata can vary by experiment, but must remain JSON scalar data.  Nested
    # structures would make field lineage ambiguous and are therefore rejected.
    result: dict[str, Any] = {}
    for raw_name in sorted(value, key=str):
        name = _required_text(raw_name, "metadata key")
        item = value[raw_name]
        if item is None or isinstance(item, (str, bool, int)):
            result[name] = item
        elif isinstance(item, float):
            result[name] = _finite_number(item, f"metadata.{name}")
        else:
            raise DecisionTraceValidationError(f"metadata.{name} must be a JSON scalar")
    return result


def canonicalise_decision_row(
    raw_row: Mapping[str, Any],
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a strict, canonical decision row without outcome information.

    Candidate records are sorted by ``next_node``.  The model score and feature
    object move with their candidate, so this operation cannot misalign values.
    """

    if not isinstance(raw_row, Mapping):
        raise DecisionTraceValidationError("decision row must be an object")
    assert_no_future_or_label_leakage(raw_row)

    adapted = dict(raw_row)
    for old_name, new_name in _TRACE_ALIASES.items():
        if old_name in adapted:
            if new_name in adapted and adapted[new_name] != adapted[old_name]:
                raise DecisionTraceValidationError(f"conflicting {old_name}/{new_name} values")
            adapted[new_name] = adapted.pop(old_name)

    # Adapter-only arrays are consumed into candidate_records.
    adapter_fields = {"candidate_features", "model_scores"}
    candidate_records = _candidate_records_from_row(adapted)
    for name in adapter_fields:
        adapted.pop(name, None)

    unknown = set(adapted) - _ALLOWED_TOP_LEVEL
    if unknown:
        raise DecisionTraceValidationError(f"decision row has unknown field(s): {sorted(unknown)}")
    if not candidate_records:
        raise DecisionTraceValidationError("candidate_records must not be empty")
    candidate_records.sort(key=lambda item: item["next_node"])
    unknown_features = sorted(
        {
            name
            for item in candidate_records
            for name in item["features"]
            if name not in EVENT_RUNTIME_FEATURE_SOURCES
        }
    )
    if unknown_features:
        raise DecisionTraceValidationError(
            "candidate runtime feature(s) have no approved lineage: " + ", ".join(unknown_features)
        )
    candidate_nodes = [int(item["next_node"]) for item in candidate_records]
    if len(candidate_nodes) != len(set(candidate_nodes)):
        raise DecisionTraceValidationError("candidate next nodes must be unique")
    provided_candidate_nodes = adapted.get("candidate_next_nodes")
    if provided_candidate_nodes is not None:
        if not isinstance(provided_candidate_nodes, Sequence) or isinstance(
            provided_candidate_nodes, (str, bytes, bytearray)
        ):
            raise DecisionTraceValidationError("candidate_next_nodes must be an array")
        canonical_provided_nodes = sorted(
            _required_int(value, f"candidate_next_nodes[{index}]")
            for index, value in enumerate(provided_candidate_nodes)
        )
        if canonical_provided_nodes != candidate_nodes:
            raise DecisionTraceValidationError(
                "candidate_next_nodes does not match candidate_records"
            )

    model_prediction = _required_int(adapted.get("model_prediction"), "model_prediction")
    selected_next = _required_int(adapted.get("selected_next"), "selected_next")
    current_node = _required_int(adapted.get("current_node"), "current_node")
    goal_node = _required_int(adapted.get("goal_node"), "goal_node")
    fallback_raw = adapted.get("fallback_selected_next")
    fallback_selected_next = None if fallback_raw is None else _required_int(
        fallback_raw, "fallback_selected_next"
    )
    model_margin = _finite_number(adapted.get("model_margin"), "model_margin")
    if model_margin < 0:
        raise DecisionTraceValidationError("model_margin cannot be negative")

    if model_prediction not in candidate_nodes:
        raise DecisionTraceValidationError("model_prediction must belong to candidate_next_nodes")
    if selected_next not in candidate_nodes:
        raise DecisionTraceValidationError("selected_next must belong to candidate_next_nodes")
    if fallback_selected_next is not None and fallback_selected_next not in candidate_nodes:
        raise DecisionTraceValidationError("fallback_selected_next must belong to candidate_next_nodes")

    merged_metadata = dict(adapted.get("metadata") or {})
    if metadata:
        for key, value in metadata.items():
            if key in merged_metadata and merged_metadata[key] != value:
                raise DecisionTraceValidationError(f"conflicting metadata value for {key}")
            merged_metadata[key] = value
    score_semantics = adapted.get(
        "model_score_semantics", merged_metadata.get("model_score_semantics")
    )
    if score_semantics != MODEL_SCORE_SEMANTICS:
        raise DecisionTraceValidationError(
            f"model_score_semantics must be {MODEL_SCORE_SEMANTICS}; got {score_semantics!r}"
        )
    runtime_bag_id = _required_int(
        merged_metadata.get("runtime_bag_id"), "metadata.runtime_bag_id"
    )
    if runtime_bag_id < 0:
        raise DecisionTraceValidationError("metadata.runtime_bag_id cannot be negative")
    merged_metadata["runtime_bag_id"] = runtime_bag_id
    score_ranking = sorted(
        candidate_records,
        key=lambda record: (float(record["model_score"]), int(record["next_node"])),
    )
    if model_prediction != int(score_ranking[0]["next_node"]):
        raise DecisionTraceValidationError(
            "model_prediction must be the minimum-cost candidate under lower_is_better_cost semantics"
        )
    expected_margin = (
        float(score_ranking[1]["model_score"]) - float(score_ranking[0]["model_score"])
        if len(score_ranking) > 1
        else 999.0
    )
    if not math.isclose(model_margin, expected_margin, rel_tol=1e-10, abs_tol=1e-10):
        raise DecisionTraceValidationError(
            f"model_margin must equal second_min_cost-min_cost ({expected_margin}); got {model_margin}"
        )

    provided_disagreement = adapted.get("model_fallback_disagreement")
    disagreement = fallback_selected_next is not None and fallback_selected_next != model_prediction
    if provided_disagreement is not None and _required_bool(
        provided_disagreement, "model_fallback_disagreement"
    ) != disagreement:
        raise DecisionTraceValidationError(
            "model_fallback_disagreement must be true exactly when model and fallback actions differ"
        )

    history_raw = adapted.get("short_history", [])
    if not isinstance(history_raw, Sequence) or isinstance(history_raw, (str, bytes, bytearray)):
        raise DecisionTraceValidationError("short_history must be an array")
    if len(history_raw) > 8:
        raise DecisionTraceValidationError("short_history exceeds the bounded length of 8")
    short_history = [_required_int(node, f"short_history[{index}]") for index, node in enumerate(history_raw)]
    if not short_history or short_history[-1] != current_node:
        raise DecisionTraceValidationError(
            "short_history must be non-empty, past-only, and end at current_node"
        )

    full_astar_used = adapted.get("full_astar_used")
    if full_astar_used is not False:
        raise DecisionTraceValidationError("full_astar_used must be false")

    digest_payload = candidate_records
    candidate_digest = _sha256_text(_canonical_json(digest_payload))
    provided_digest = adapted.get("candidate_order_digest")
    if provided_digest not in (None, "", candidate_digest):
        raise DecisionTraceValidationError("candidate_order_digest does not match canonical candidate records")
    provided_ordering = adapted.get("candidate_ordering")
    if provided_ordering not in (None, "", CANDIDATE_ORDERING):
        raise DecisionTraceValidationError(f"candidate_ordering must be {CANDIDATE_ORDERING}")

    result = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "decision_id": _required_text(adapted.get("decision_id"), "decision_id"),
        "task_id": _required_int(adapted.get("task_id"), "task_id"),
        "segment_id": _required_text(adapted.get("segment_id"), "segment_id"),
        "event_time": _finite_number(adapted.get("event_time"), "event_time"),
        "current_node": current_node,
        "goal_node": goal_node,
        "candidate_next_nodes": candidate_nodes,
        "candidate_records": candidate_records,
        "model_prediction": model_prediction,
        "model_score_semantics": MODEL_SCORE_SEMANTICS,
        "model_margin": model_margin,
        "risk_gate_triggered": _required_bool(adapted.get("risk_gate_triggered"), "risk_gate_triggered"),
        "fallback_selected_next": fallback_selected_next,
        "selected_next": selected_next,
        "decision_source": _required_text(adapted.get("decision_source"), "decision_source"),
        "rule_reason": str(adapted.get("rule_reason") or ""),
        "local_snapshot": _canonical_local_snapshot(adapted.get("local_snapshot")),
        "short_history": short_history,
        "full_astar_used": False,
        "model_fallback_disagreement": disagreement,
        "candidate_ordering": CANDIDATE_ORDERING,
        "candidate_order_digest": candidate_digest,
        "metadata": _canonical_metadata(merged_metadata),
    }
    assert_no_future_or_label_leakage(result)
    return result


def load_adjacency(map_path: Path) -> dict[int, tuple[int, ...]]:
    """Load canonical outgoing-neighbor sets from a processed map JSON."""

    payload = json.loads(map_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        raise ValueError(f"map has no nodes array: {map_path}")
    adjacency: dict[int, tuple[int, ...]] = {}
    for row in nodes:
        location = int(row["location"])
        outgoing = tuple(sorted(int(value) for value in row.get("outgoing", [])))
        if len(outgoing) != len(set(outgoing)):
            raise ValueError(f"map node {location} has duplicate outgoing neighbors")
        adjacency[location] = outgoing
    return adjacency


def validate_decision_rows(
    raw_rows: Iterable[Mapping[str, Any]],
    adjacency: Mapping[int, Sequence[int]],
    *,
    metadata: Mapping[str, Any] | None = None,
    require_all_outgoing: bool = True,
) -> list[dict[str, Any]]:
    """Canonicalise rows and validate graph/action semantics.

    With ``require_all_outgoing=True`` (the default), candidates must equal the
    complete outgoing-neighbor set, not merely be a valid subset.  Fault state
    remains a per-candidate/runtime feature and must not disguise candidate
    provenance.
    """

    result: list[dict[str, Any]] = []
    decision_ids: set[str] = set()
    for index, raw_row in enumerate(raw_rows):
        try:
            row = canonicalise_decision_row(raw_row, metadata=metadata)
        except DecisionTraceValidationError as exc:
            raise DecisionTraceValidationError(f"row {index}: {exc}") from exc
        current = int(row["current_node"])
        if current not in adjacency:
            raise DecisionTraceValidationError(f"row {index}: current_node {current} is absent from graph")
        expected = tuple(sorted(int(value) for value in adjacency[current]))
        candidates = tuple(int(value) for value in row["candidate_next_nodes"])
        invalid = sorted(set(candidates) - set(expected))
        if invalid:
            raise DecisionTraceValidationError(
                f"row {index}: candidate(s) are not outgoing neighbors of {current}: {invalid}"
            )
        if require_all_outgoing and candidates != expected:
            raise DecisionTraceValidationError(
                f"row {index}: candidates {candidates} do not equal true outgoing neighbors {expected}"
            )
        decision_id = str(row["decision_id"])
        if decision_id in decision_ids:
            raise DecisionTraceValidationError(f"row {index}: duplicate decision_id {decision_id}")
        decision_ids.add(decision_id)
        result.append(row)
    return result


def decision_trace_schema() -> dict[str, Any]:
    """Return the machine-readable JSON Schema for canonical trace rows."""

    finite_number = {"type": "number"}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "CZR005 G4IRSF11 decision-level runtime trace",
        "description": (
            "One online ARRIVE_JUNCTION decision. Outcomes/labels and full future routes are excluded."
        ),
        "type": "object",
        "additionalProperties": False,
        "required": sorted(_ALLOWED_TOP_LEVEL),
        "properties": {
            "schema_id": {"const": SCHEMA_ID},
            "schema_version": {"const": SCHEMA_VERSION},
            "decision_id": {"type": "string", "minLength": 1},
            "task_id": {"type": "integer"},
            "segment_id": {"type": "string", "minLength": 1},
            "event_time": finite_number,
            "current_node": {"type": "integer"},
            "goal_node": {"type": "integer"},
            "candidate_next_nodes": {
                "type": "array",
                "minItems": 1,
                "uniqueItems": True,
                "items": {"type": "integer"},
            },
            "candidate_records": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["next_node", "features", "model_score"],
                    "properties": {
                        "next_node": {"type": "integer"},
                        "features": {
                            "type": "object",
                            "additionalProperties": {"type": ["number", "integer", "boolean"]},
                        },
                        "model_score": finite_number,
                        "shield_allowed": {"type": "boolean"},
                        "shield_reason": {"type": "string"},
                    },
                },
            },
            "model_prediction": {"type": "integer"},
            "model_score_semantics": {"const": MODEL_SCORE_SEMANTICS},
            "model_margin": {"type": "number", "minimum": 0},
            "risk_gate_triggered": {"type": "boolean"},
            "fallback_selected_next": {"type": ["integer", "null"]},
            "selected_next": {"type": "integer"},
            "decision_source": {"type": "string", "minLength": 1},
            "rule_reason": {"type": "string"},
            "local_snapshot": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "junction_queue_length",
                    "next_available_time",
                    "faulted_outgoing_count",
                    "message_age_seconds",
                ],
                "properties": {
                    "junction_queue_length": {"type": "integer", "minimum": 0},
                    "next_available_time": finite_number,
                    "faulted_outgoing_count": {"type": "integer", "minimum": 0},
                    "message_age_seconds": {"type": "number", "minimum": 0},
                    "downstream_pressure": {"type": "number", "minimum": 0},
                    "recent_throughput": {"type": "number", "minimum": 0},
                    "local_wait_seconds": {"type": "number", "minimum": 0},
                    "active_reservation_count": {"type": "integer", "minimum": 0},
                },
            },
            "short_history": {"type": "array", "maxItems": 8, "items": {"type": "integer"}},
            "full_astar_used": {"const": False},
            "model_fallback_disagreement": {"type": "boolean"},
            "candidate_ordering": {"const": CANDIDATE_ORDERING},
            "candidate_order_digest": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "metadata": {
                "type": "object",
                "required": ["model_score_semantics", "runtime_bag_id"],
                "properties": {
                    "model_score_semantics": {"const": MODEL_SCORE_SEMANTICS},
                    "runtime_bag_id": {"type": "integer", "minimum": 0},
                },
                "additionalProperties": {"type": ["string", "number", "integer", "boolean", "null"]},
            },
        },
        "x-semantic-invariants": [
            "candidate_next_nodes equals the graph outgoing-neighbor set for current_node",
            "candidate_records is sorted by next_node and aligns features/scores with that node",
            "model_prediction, fallback_selected_next when present, and selected_next belong to candidates",
            "model_prediction is the minimum-cost candidate; ties break by ascending next_node",
            "model_margin equals second_min_cost minus min_cost (999 for one candidate)",
            "short_history is non-empty, contains only bounded past state, and ends at current_node",
            "model_fallback_disagreement iff fallback_selected_next is present and differs from model_prediction",
            "model_margin is finite and non-null",
            "metadata.runtime_bag_id is a non-negative internal identity; original task_id is unchanged",
            "full_astar_used is false",
            "no future path/route suffix, teacher field, or post-hoc label is present",
        ],
    }


def feature_lineage_rows() -> list[dict[str, Any]]:
    """Return a machine-traversable runtime/metadata/label lineage graph."""

    result: list[dict[str, Any]] = []

    def add(
        field_path: str,
        lineage: str,
        role: str,
        origin: str,
        availability: str,
        sources: Sequence[str] = (),
        *,
        model_input: bool = False,
        derivation: str = "",
        storage_boundary: str | None = None,
    ) -> None:
        result.append(
            {
                "field_path": field_path,
                "lineage": lineage,
                "role": role,
                "origin": origin,
                "availability": availability,
                "sources": list(sources),
                "available_at_decision": availability in {"decision_time", "static", "pre_run"},
                "model_input_allowed": model_input,
                "derivation": derivation,
                "prohibited_as_runtime_feature": lineage == "label",
                "lineage_status": "PASS",
                "storage_boundary": storage_boundary or (
                    "decision_trace"
                    if lineage == "runtime"
                    else "trace_or_sample_metadata"
                    if lineage == "metadata"
                    else "separate_outcome_table"
                ),
            }
        )

    # Runtime/static dependency leaves.  Every derived model feature below
    # references only these leaves or other declared decision-time nodes.
    runtime_leaves = {
        "event_scheduler.current_time": ("event_scheduler", "decision_time"),
        "bag.current_node": ("bag_agent_local_state", "decision_time"),
        "bag.goal_node": ("immutable_task_request", "static"),
        "bag.bounded_history": ("bag_agent_local_state", "decision_time"),
        "graph.outgoing_adjacency": ("official_map_local_adjacency", "static"),
        "graph.static_potential": ("official_map_static_goal_potential", "static"),
        "graph.edge_travel_time": ("official_map_directed_edge", "static"),
        "local_neighbor.queue_length": ("bounded_neighbor_beacon", "decision_time"),
        "local_neighbor.scheduled_incoming": ("bounded_neighbor_beacon", "decision_time"),
        "local_neighbor.next_available_time": ("bounded_neighbor_beacon", "decision_time"),
        "local_edge.next_available_time": ("junction_owned_one_step_calendar", "decision_time"),
        "congestion_beacon.advertised_fault": ("bounded_neighbor_beacon", "decision_time"),
        "congestion_beacon.fault_message_timestamp": ("bounded_neighbor_beacon", "decision_time"),
        "bounded_two_hop.queue_summary": ("bounded_two_hop_beacon", "decision_time"),
        "local_junction.queue_length": ("junction_controller_local_state", "decision_time"),
        "local_junction.next_available_time": ("junction_controller_local_state", "decision_time"),
        "local_junction.faulted_outgoing_count": ("junction_controller_local_state", "decision_time"),
        "local_junction.message_age_seconds": ("junction_controller_local_state", "decision_time"),
        "local_junction.downstream_pressure": ("bounded_neighbor_beacon", "decision_time"),
        "local_junction.recent_throughput": ("junction_controller_local_state", "decision_time"),
        "local_junction.local_wait_seconds": ("junction_controller_local_state", "decision_time"),
        "local_junction.active_reservation_count": ("junction_owned_one_step_calendar", "decision_time"),
        "local_safety_shield.state": ("bounded_local_safety_state", "decision_time"),
        "runtime.model_parameters": ("frozen_policy_bundle", "static"),
        "runtime.full_astar_counter": ("event_runtime_invariant_counter", "decision_time"),
    }
    for field, (origin, availability) in runtime_leaves.items():
        add(
            field,
            "runtime",
            "dependency_leaf",
            origin,
            availability,
            storage_boundary="lineage_dependency",
        )

    add("decision_id", "metadata", "identity", "event_runtime", "decision_time", derivation="stable runtime decision identifier")
    add("task_id", "metadata", "identity", "source_task_jsonl", "pre_run")
    add("segment_id", "metadata", "identity", "source_task_jsonl", "pre_run")
    add("event_time", "runtime", "observation", "event_scheduler", "decision_time", ["event_scheduler.current_time"], model_input=True)
    add("current_node", "runtime", "observation", "bag_agent", "decision_time", ["bag.current_node"], model_input=True)
    add("goal_node", "runtime", "observation", "task_request", "static", ["bag.goal_node"], model_input=True)
    add("candidate_next_nodes", "runtime", "candidate_structure", "official_map", "static", ["graph.outgoing_adjacency", "current_node"])
    add("candidate_records[].next_node", "runtime", "candidate_structure", "official_map", "static", ["candidate_next_nodes"])

    feature_paths = []
    for feature_name, sources in EVENT_RUNTIME_FEATURE_SOURCES.items():
        field = f"candidate_records[].features.{feature_name}"
        feature_paths.append(field)
        add(
            field,
            "runtime",
            "model_feature",
            "bounded_local_feature_builder",
            "decision_time",
            sources,
            model_input=True,
            derivation="deterministic candidate-local feature",
        )
    add(
        "candidate_records[].features.*",
        "runtime",
        "feature_group",
        "approved_feature_allowlist",
        "decision_time",
        feature_paths,
        derivation="closed allow-list; unknown feature names fail validation",
    )
    add(
        "candidate_records[].model_score",
        "runtime",
        "model_output",
        "frozen_local_scorer",
        "decision_time",
        [*feature_paths, "runtime.model_parameters"],
        derivation="cost/score under trace metadata score semantics",
    )
    add("candidate_records[].shield_allowed", "runtime", "shield_output", "local_safety_shield", "decision_time", ["local_safety_shield.state", "candidate_records[].next_node"])
    add("candidate_records[].shield_reason", "runtime", "shield_diagnostic", "local_safety_shield", "decision_time", ["candidate_records[].shield_allowed"])
    add("model_score_semantics", "runtime", "model_contract", "event_runtime", "static", derivation="lower_is_better_cost")
    add("model_prediction", "runtime", "model_output", "local_scorer", "decision_time", ["candidate_records[].model_score", "candidate_records[].next_node", "model_score_semantics"], derivation="minimum cost; ties by ascending next_node")
    add("model_margin", "runtime", "model_output", "local_scorer", "decision_time", ["candidate_records[].model_score", "model_score_semantics"], derivation="second minimum cost minus minimum cost; 999 for one candidate")
    add("risk_gate_triggered", "runtime", "shield_output", "local_safety_shield", "decision_time", ["model_prediction", "candidate_records[].shield_allowed"])
    add("fallback_selected_next", "runtime", "action_diagnostic", "local_pibt_lite_shield", "decision_time", ["candidate_records[].shield_allowed", "candidate_records[].model_score"])
    add("selected_next", "runtime", "committed_action", "junction_controller", "decision_time", ["model_prediction", "fallback_selected_next", "candidate_records[].shield_allowed"])
    add("decision_source", "runtime", "action_diagnostic", "junction_controller", "decision_time", ["selected_next", "model_prediction", "fallback_selected_next"])
    add("rule_reason", "runtime", "action_diagnostic", "local_safety_shield", "decision_time", ["candidate_records[].shield_reason"])

    snapshot_sources = {
        "junction_queue_length": "local_junction.queue_length",
        "next_available_time": "local_junction.next_available_time",
        "faulted_outgoing_count": "local_junction.faulted_outgoing_count",
        "message_age_seconds": "local_junction.message_age_seconds",
        "downstream_pressure": "local_junction.downstream_pressure",
        "recent_throughput": "local_junction.recent_throughput",
        "local_wait_seconds": "local_junction.local_wait_seconds",
        "active_reservation_count": "local_junction.active_reservation_count",
    }
    snapshot_paths = []
    for name, source in snapshot_sources.items():
        field = f"local_snapshot.{name}"
        snapshot_paths.append(field)
        add(field, "runtime", "model_feature", "junction_controller_local_state", "decision_time", [source], model_input=True)
    add("local_snapshot.*", "runtime", "feature_group", "bounded_local_snapshot", "decision_time", snapshot_paths)
    add("short_history", "runtime", "model_feature", "bag_agent", "decision_time", ["bag.bounded_history"], model_input=True, derivation="past-only, maximum eight nodes")
    add("full_astar_used", "runtime", "invariant", "event_runtime", "decision_time", ["runtime.full_astar_counter"])

    add("metadata.scenario", "metadata", "experiment_context", "experiment_manifest", "pre_run")
    add("metadata.scale", "metadata", "experiment_context", "experiment_manifest", "pre_run")
    add("metadata.run_id", "metadata", "experiment_context", "experiment_manifest", "pre_run", derivation="excluded from semantic repeat fingerprint")
    add("metadata.trace_shard", "metadata", "shard_context", "trace_input_manifest", "pre_run")
    add("metadata.trace_shard_count", "metadata", "shard_context", "event_runtime_trace_context", "pre_run")
    add("metadata.trace_shard_index", "metadata", "shard_context", "event_runtime_trace_context", "pre_run")
    add("metadata.runtime_bag_id", "metadata", "runtime_identity", "event_runtime_internal_identity", "decision_time", derivation="internal unique key; original task_id is never rewritten")
    add("source_node", "metadata", "source_release_mapping", "source_task_jsonl", "pre_run")
    add("original_arrival_time", "metadata", "source_release_mapping", "source_task_jsonl.g4irsf7_original_pass_time", "pre_run")
    add("java_arrival_epoch", "metadata", "source_release_mapping", "source_task_jsonl", "pre_run", ["original_arrival_time"], derivation="floor(original_arrival_time)")
    add("release_time", "metadata", "source_release_mapping", "source_task_jsonl.pass_time", "pre_run")
    add("source_queue_delay_seconds", "metadata", "source_release_mapping", "source_task_jsonl", "pre_run", ["java_arrival_epoch", "release_time"], derivation="release_time-java_arrival_epoch")
    add("sample_weight", "metadata", "sampling_metadata", "stratified_reservoir", "post_hoc", derivation="unique stratum population/effective quota")

    labels = {
        "reached_goal": "event outcome join",
        "realized_local_wait_seconds": "post-hoc event interval",
        "realized_downstream_wait_seconds": "post-hoc event interval",
        "loop_or_dead_end": "post-hoc event outcome",
        "bag_tth_seconds": "post-hoc bag aggregation",
        "tail_bucket": "post-hoc p95/p99 membership",
        "fault_recovery_outcome": "post-hoc fault outcome",
    }
    for field, derivation in labels.items():
        add(field, "label", "training_label", "separate_outcome_join", "post_hoc", derivation=derivation)
    return result


def validate_feature_lineage(rows: Iterable[Mapping[str, Any]]) -> None:
    """Validate lineage completeness and recursively audit model dependencies."""

    by_field: dict[str, Mapping[str, Any]] = {}
    for index, row in enumerate(rows):
        field = _required_text(row.get("field_path"), f"lineage[{index}].field_path")
        if field in by_field:
            raise DecisionTraceValidationError(f"duplicate lineage field: {field}")
        lineage = row.get("lineage")
        if lineage not in {"runtime", "metadata", "label"}:
            raise DecisionTraceValidationError(f"invalid lineage class for {field}: {lineage}")
        if not _required_text(row.get("role"), f"lineage[{index}].role"):
            raise DecisionTraceValidationError(f"lineage role missing for {field}")
        if not _required_text(row.get("origin"), f"lineage[{index}].origin"):
            raise DecisionTraceValidationError(f"lineage origin missing for {field}")
        availability = row.get("availability")
        if availability not in {"decision_time", "static", "pre_run", "post_hoc"}:
            raise DecisionTraceValidationError(f"invalid availability for {field}: {availability}")
        sources = row.get("sources")
        if not isinstance(sources, list) or not all(isinstance(source, str) and source for source in sources):
            raise DecisionTraceValidationError(f"lineage sources must be a string array for {field}")
        if lineage == "label" and bool(row.get("model_input_allowed")):
            raise DecisionTraceValidationError(f"label field cannot be a model input: {field}")
        if lineage == "label" and row.get("storage_boundary") != "separate_outcome_table":
            raise DecisionTraceValidationError(f"label field is not separated from runtime trace: {field}")
        by_field[field] = row

    required = {
        "candidate_records[].features.*",
        *(f"candidate_records[].features.{name}" for name in EVENT_RUNTIME_FEATURE_SOURCES),
        "model_margin",
        "fallback_selected_next",
        "selected_next",
        "short_history",
        "original_arrival_time",
        "release_time",
        "tail_bucket",
    }
    missing = required - set(by_field)
    if missing:
        raise DecisionTraceValidationError(f"lineage missing required field(s): {sorted(missing)}")

    visiting: set[str] = set()
    verified: set[str] = set()

    def verify_runtime_dependency(field: str, root: str) -> None:
        if field in verified:
            return
        if field in visiting:
            raise DecisionTraceValidationError(f"lineage dependency cycle at {field} for {root}")
        row = by_field.get(field)
        if row is None:
            raise DecisionTraceValidationError(f"undeclared lineage source {field} for {root}")
        if row["lineage"] == "label" or row["availability"] == "post_hoc":
            raise DecisionTraceValidationError(f"runtime model input {root} depends on post-hoc/label field {field}")
        normalised = _normalised_key(field)
        if normalised in FORBIDDEN_TRACE_KEYS or any(
            token in normalised for token in _FORBIDDEN_DERIVED_KEY_TOKENS
        ):
            raise DecisionTraceValidationError(f"runtime model input {root} depends on forbidden field {field}")
        visiting.add(field)
        for source in row["sources"]:
            verify_runtime_dependency(source, root)
        visiting.remove(field)
        verified.add(field)

    for field, row in by_field.items():
        if bool(row.get("model_input_allowed")):
            if row["lineage"] != "runtime":
                raise DecisionTraceValidationError(f"non-runtime model input declared: {field}")
            verify_runtime_dependency(field, field)


def source_release_mapping(task_rows: Iterable[Mapping[str, Any]]) -> dict[tuple[int, str], dict[str, Any]]:
    """Build exact original-arrival -> Java release mappings by task segment."""

    result: dict[tuple[int, str], dict[str, Any]] = {}
    for index, row in enumerate(task_rows):
        task_id = _required_int(row.get("task_id"), f"task_rows[{index}].task_id")
        segment_id = _required_text(row.get("segment_id"), f"task_rows[{index}].segment_id")
        source_node = _required_int(row.get("start"), f"task_rows[{index}].start")
        goal_node = _required_int(row.get("goal"), f"task_rows[{index}].goal")
        original_raw = row.get(
            "g4irsf7_original_pass_time",
            row.get("original_pass_time", row.get("original_entry_time", row.get("pass_time"))),
        )
        original = _finite_number(original_raw, f"task_rows[{index}].original_arrival_time")
        release = _finite_number(row.get("pass_time"), f"task_rows[{index}].pass_time")
        java_epoch = math.floor(original)
        queue_delay = release - java_epoch
        if queue_delay < -1e-9:
            raise DecisionTraceValidationError(
                f"task_rows[{index}] releases before Java arrival epoch: {release} < {java_epoch}"
            )
        key = (task_id, segment_id)
        mapping_row = {
            "task_id": task_id,
            "segment_id": segment_id,
            "source_node": source_node,
            "goal_node": goal_node,
            "original_arrival_time": original,
            "java_arrival_epoch": java_epoch,
            "release_time": release,
            "source_queue_delay_seconds": max(0.0, queue_delay),
            "raw_arrival_to_release_delta_seconds": release - original,
            "source_queue_rank": int(row.get("g4irsf7_source_queue_rank", 0) or 0),
            "mapping_source": (
                "g4irsf7_original_pass_time->pass_time"
                if "g4irsf7_original_pass_time" in row
                else "original_entry_time->pass_time"
            ),
        }
        previous = result.get(key)
        if previous is not None and previous != mapping_row:
            raise DecisionTraceValidationError(f"conflicting source-release mapping for task segment {key}")
        result[key] = mapping_row
    return result


def source_identity_audit(task_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Quantify repeated original task IDs without rewriting them."""

    segment_counts: Counter[int] = Counter()
    identities: set[tuple[int, str]] = set()
    total = 0
    for index, row in enumerate(task_rows):
        task_id = _required_int(row.get("task_id"), f"task_rows[{index}].task_id")
        segment_id = _required_text(row.get("segment_id"), f"task_rows[{index}].segment_id")
        identity = (task_id, segment_id)
        if identity in identities:
            raise DecisionTraceValidationError(f"duplicate original task/segment identity: {identity}")
        identities.add(identity)
        segment_counts[task_id] += 1
        total += 1
    repeated = {task_id: count for task_id, count in segment_counts.items() if count > 1}
    return {
        "processed_segment_count": total,
        "unique_original_task_id_count": len(segment_counts),
        "repeated_original_task_id_count": len(repeated),
        "extra_segments_sharing_original_task_id": sum(count - 1 for count in repeated.values()),
        "max_segments_per_original_task_id": max(segment_counts.values(), default=0),
        "original_task_ids_rewritten": False,
        "runtime_internal_identity_required": bool(repeated),
    }


def validate_runtime_bag_identity(decisions: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate internal runtime IDs while preserving original task/segment IDs.

    Runtime IDs are scoped by run/scenario because separate deterministic runs
    may legitimately reuse the same small internal integers.
    """

    runtime_to_original: dict[tuple[str, int], tuple[int, str]] = {}
    original_to_runtime: dict[tuple[str, int, str], int] = {}
    decision_count = 0
    for index, decision in enumerate(decisions):
        decision_count += 1
        metadata = decision.get("metadata") or {}
        if "runtime_bag_id" not in metadata:
            raise DecisionTraceValidationError(
                f"decision row {index} is missing metadata.runtime_bag_id"
            )
        runtime_bag_id = _required_int(
            metadata["runtime_bag_id"], f"decision[{index}].metadata.runtime_bag_id"
        )
        if runtime_bag_id < 0:
            raise DecisionTraceValidationError("metadata.runtime_bag_id cannot be negative")
        scope = str(metadata.get("run_id") or metadata.get("scenario") or "unspecified")
        original = (int(decision["task_id"]), str(decision["segment_id"]))
        runtime_key = (scope, runtime_bag_id)
        previous_original = runtime_to_original.get(runtime_key)
        if previous_original is not None and previous_original != original:
            raise DecisionTraceValidationError(
                f"runtime identity {runtime_key} aliases original segments {previous_original} and {original}"
            )
        original_key = (scope, *original)
        previous_runtime = original_to_runtime.get(original_key)
        if previous_runtime is not None and previous_runtime != runtime_bag_id:
            raise DecisionTraceValidationError(
                f"original segment {original_key} changes runtime_bag_id from {previous_runtime} to {runtime_bag_id}"
            )
        runtime_to_original[runtime_key] = original
        original_to_runtime[original_key] = runtime_bag_id
    return {
        "status": "PASS",
        "decision_count": decision_count,
        "runtime_identity_count": len(runtime_to_original),
        "original_segment_identity_count": len(original_to_runtime),
        "original_task_ids_rewritten": False,
        "runtime_identity_alias_count": 0,
    }


def decision_source_links(
    decisions: Iterable[Mapping[str, Any]],
    mappings: Mapping[tuple[int, str], Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Link every decision to its task-level original arrival and release."""

    result: list[dict[str, Any]] = []
    for index, decision in enumerate(decisions):
        key = (int(decision["task_id"]), str(decision["segment_id"]))
        mapped = mappings.get(key)
        if mapped is None:
            raise DecisionTraceValidationError(
                f"decision row {index} has no original-arrival/release mapping for task segment {key}"
            )
        if int(mapped["goal_node"]) != int(decision["goal_node"]):
            raise DecisionTraceValidationError(
                f"decision row {index} goal does not match source-release mapping for {key}"
            )
        if float(decision["event_time"]) + 1e-9 < float(mapped["release_time"]):
            raise DecisionTraceValidationError(
                f"decision row {index} occurs before source release for task segment {key}"
            )
        metadata = decision.get("metadata") or {}
        runtime_bag_id = _required_int(
            metadata.get("runtime_bag_id"),
            f"decision[{index}].metadata.runtime_bag_id",
        )
        if runtime_bag_id < 0:
            raise DecisionTraceValidationError("metadata.runtime_bag_id cannot be negative")
        result.append(
            {
                "decision_id": decision["decision_id"],
                "runtime_bag_id": runtime_bag_id,
                **dict(mapped),
            }
        )
    return result


def scenario_family(scenario: str) -> str:
    """Collapse deterministic repeat suffixes while retaining scenario meaning."""

    result = _required_text(scenario, "scenario")
    previous = None
    while previous != result:
        previous = result
        for pattern in _REPEAT_PATTERNS:
            result = pattern.sub("", result)
    return result.rstrip("_-") or _required_text(scenario, "scenario")


def _tail_bucket(outcome: Mapping[str, Any] | None) -> str:
    if not outcome:
        return "body_or_unlabeled"
    explicit = str(outcome.get("tail_bucket") or "").strip().lower()
    if explicit:
        aliases = {
            "p99": "p99_tail",
            "p95": "p95_tail",
            "tail_p99": "p99_tail",
            "tail_p95": "p95_tail",
            "failed": "failed",
            "body": "body",
        }
        return aliases.get(explicit, explicit)
    if outcome.get("reached_goal") is False:
        return "failed"
    if bool(outcome.get("is_p99")):
        return "p99_tail"
    if bool(outcome.get("is_p95")):
        return "p95_tail"
    return "body"


def hard_case_reasons(decision: Mapping[str, Any], outcome: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    """Derive deterministic decision-level hard-case reasons."""

    reasons: set[str] = set()
    fallback = decision.get("fallback_selected_next")
    prediction = decision.get("model_prediction")
    if fallback is not None and int(fallback) != int(prediction):
        reasons.add("model_fallback_disagreement")
    risk_triggered = bool(decision.get("risk_gate_triggered"))
    if risk_triggered:
        reasons.add("risk_gate_triggered")
    decision_source = str(decision.get("decision_source"))
    nominal_sources = {
        "model",
        "local_static_potential",
        "event_static_potential_heuristic",
        "event_v3_model_only",
    }
    fallback_or_shield = decision_source not in nominal_sources
    if fallback_or_shield:
        reasons.add("fallback_or_shield_selected")
    rule_reason = str(decision.get("rule_reason") or "").strip()
    if rule_reason and (risk_triggered or fallback_or_shield):
        reasons.add("rule:" + re.sub(r"[^a-z0-9]+", "_", rule_reason.lower()).strip("_"))
    if float(decision.get("model_margin", math.inf)) < 1.0:
        reasons.add("low_model_margin")
    snapshot = decision.get("local_snapshot") or {}
    # The controller queue includes the bag currently being dispatched, so a
    # value of one is not contention.  Hard pressure starts with another bag
    # waiting behind/in front of it.
    if int(snapshot.get("junction_queue_length", 0)) > 1:
        reasons.add("local_queue_pressure")
    if float(snapshot.get("downstream_pressure", 0.0)) > 0:
        reasons.add("downstream_pressure")
    if int(snapshot.get("faulted_outgoing_count", 0)) > 0:
        reasons.add("local_fault_state")
    tail = _tail_bucket(outcome)
    if tail in {"p95_tail", "p99_tail", "failed"}:
        reasons.add(tail)
    if outcome:
        if bool(outcome.get("loop_or_dead_end")):
            reasons.add("loop_or_dead_end")
        if str(outcome.get("fault_recovery_outcome") or "").lower() in {"failed", "timeout", "unrecovered"}:
            reasons.add("fault_recovery_failure")
    return tuple(sorted(reasons))


def _fault_bucket(decision: Mapping[str, Any]) -> str:
    snapshot = decision.get("local_snapshot") or {}
    metadata = decision.get("metadata") or {}
    fault_mode = str(metadata.get("fault_mode") or metadata.get("scenario_fault") or "no_fault").lower()
    if int(snapshot.get("faulted_outgoing_count", 0)) > 0:
        return "fault_local_active"
    if fault_mode not in {"", "none", "no_fault", "false", "0"}:
        return "fault_scenario_inactive_here"
    return "no_fault"


def _reason_bucket(reasons: Sequence[str]) -> str:
    return "+".join(sorted(set(reasons))) if reasons else "routine"


def _stratum_payload(
    decision: Mapping[str, Any],
    source_link: Mapping[str, Any],
    reasons: Sequence[str],
    tail_bucket: str,
) -> dict[str, Any]:
    metadata = decision.get("metadata") or {}
    scenario = _required_text(metadata.get("scenario", "unspecified"), "metadata.scenario")
    scale = _required_text(metadata.get("scale", "unspecified"), "metadata.scale")
    return {
        "scenario": scenario_family(scenario),
        "scale": scale,
        "source": int(source_link["source_node"]),
        "goal": int(decision["goal_node"]),
        "junction": int(decision["current_node"]),
        "fault": _fault_bucket(decision),
        "reason": _reason_bucket(reasons),
        "tail": tail_bucket,
    }


def _semantic_fingerprint(
    decision: Mapping[str, Any],
    source_link: Mapping[str, Any],
    stratum: Mapping[str, Any],
) -> str:
    """Fingerprint a semantic decision while ignoring run/repeat identifiers."""

    payload = {
        "scenario_family": stratum["scenario"],
        "scale": stratum["scale"],
        "task_id": decision["task_id"],
        "segment_id": decision["segment_id"],
        "event_time": decision["event_time"],
        "current_node": decision["current_node"],
        "goal_node": decision["goal_node"],
        "candidate_records": decision["candidate_records"],
        "model_prediction": decision["model_prediction"],
        "model_score_semantics": decision["model_score_semantics"],
        "model_margin": decision["model_margin"],
        "risk_gate_triggered": decision["risk_gate_triggered"],
        "fallback_selected_next": decision["fallback_selected_next"],
        "selected_next": decision["selected_next"],
        "decision_source": decision["decision_source"],
        "rule_reason": decision["rule_reason"],
        "local_snapshot": decision["local_snapshot"],
        "short_history": decision["short_history"],
        "source_node": source_link["source_node"],
        "original_arrival_time": source_link["original_arrival_time"],
        "release_time": source_link["release_time"],
        "fault_bucket": stratum["fault"],
        "reason_bucket": stratum["reason"],
        "tail_bucket": stratum["tail"],
    }
    return _sha256_text(_canonical_json(payload))


def _stratum_id(stratum: Mapping[str, Any]) -> str:
    return _sha256_text(_canonical_json(stratum))[:20]


def _allocate_quotas(
    capacities: Mapping[str, int], config: SamplingConfig
) -> tuple[dict[str, int], dict[str, int]]:
    """Allocate balanced min/max quotas deterministically within a global cap."""

    strata = sorted(capacities)
    target_min = {
        key: min(int(capacities[key]), config.minimum_per_stratum, config.maximum_per_stratum)
        for key in strata
    }
    quotas = {key: 0 for key in strata}
    remaining = config.limit

    # Round-robin the requested minimum.  This is explicit and fair even when
    # the number of strata makes the requested minima impossible under limit.
    for level in range(1, config.minimum_per_stratum + 1):
        for key in strata:
            if remaining <= 0:
                break
            if target_min[key] >= level:
                quotas[key] += 1
                remaining -= 1
        if remaining <= 0:
            break

    # Fill remaining balanced capacity one sample per stratum per pass.  A
    # stable hash rotation prevents lexical source/node IDs from always winning
    # the last partial pass while preserving determinism.
    order = sorted(strata, key=lambda key: (_sha256_text(config.seed + "|quota|" + key), key))
    while remaining > 0:
        progressed = False
        for key in order:
            cap = min(int(capacities[key]), config.maximum_per_stratum)
            if quotas[key] >= cap:
                continue
            quotas[key] += 1
            remaining -= 1
            progressed = True
            if remaining <= 0:
                break
        if not progressed:
            break
    return quotas, target_min


def stratified_reservoir_sample(
    decisions: Iterable[Mapping[str, Any]],
    source_links: Sequence[Mapping[str, Any]],
    *,
    outcomes: Mapping[str, Mapping[str, Any]] | None = None,
    config: SamplingConfig | None = None,
    include_routine: bool = False,
) -> SamplingResult:
    """Build an order-independent, deduplicated stratified hard-case sample.

    Strata use the exact cross-product requested by G4IRSF11:
    scenario/scale/source/goal/junction/fault/reason/tail.  Deterministic
    repeats are removed by semantic fingerprint before quotas are allocated.
    Hash-priority reservoirs select the lowest stable keys per stratum, making
    the result independent of input and candidate enumeration order.
    """

    config = config or SamplingConfig()
    outcomes = outcomes or {}
    links_by_decision: dict[str, Mapping[str, Any]] = {}
    for link in source_links:
        decision_id = str(link["decision_id"])
        if decision_id in links_by_decision:
            raise DecisionTraceValidationError(f"duplicate source link for decision_id {decision_id}")
        links_by_decision[decision_id] = link

    raw_eligible = 0
    input_decision_count = 0
    routine_excluded = 0
    # Binary digests substantially reduce the dedupe set footprint for
    # multi-million-decision shard collections.
    seen_fingerprints: set[bytes] = set()
    reservoirs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    retained_by_fingerprint: dict[str, dict[str, Any]] = {}
    raw_stratum_counts: Counter[str] = Counter()
    unique_stratum_counts: Counter[str] = Counter()
    stratum_payloads: dict[str, dict[str, Any]] = {}
    individual_reason_counts: Counter[str] = Counter()
    for decision in decisions:
        input_decision_count += 1
        decision_id = str(decision["decision_id"])
        link = links_by_decision.get(decision_id)
        if link is None:
            raise DecisionTraceValidationError(f"missing source-release link for decision_id {decision_id}")
        outcome = outcomes.get(decision_id)
        reason_set = set(hard_case_reasons(decision, outcome))
        source_delay = float(link.get("source_queue_delay_seconds", 0.0))
        if source_delay >= 1.0:
            reason_set.add("source_queue_delay")
        if source_delay >= 5.0:
            reason_set.add("source_queue_long_backlog")
        reasons = tuple(sorted(reason_set))
        if not reasons and not include_routine:
            routine_excluded += 1
            continue
        raw_eligible += 1
        for reason in reasons:
            individual_reason_counts[reason] += 1
        tail = _tail_bucket(outcome)
        stratum = _stratum_payload(decision, link, reasons, tail)
        sid = _stratum_id(stratum)
        fingerprint = _semantic_fingerprint(decision, link, stratum)
        fingerprint_key = bytes.fromhex(fingerprint)
        raw_stratum_counts[sid] += 1
        retained = retained_by_fingerprint.get(fingerprint)
        if fingerprint_key in seen_fingerprints:
            if retained is not None:
                retained["repeat_count"] = int(retained["repeat_count"]) + 1
                if str(decision_id) < str(retained["decision"]["decision_id"]):
                    retained["decision"] = dict(decision)
                    retained["source_link"] = dict(link)
                    retained["outcome"] = dict(outcome or {})
            continue
        seen_fingerprints.add(fingerprint_key)
        unique_stratum_counts[sid] += 1
        stratum_payloads[sid] = stratum
        candidate = {
            "decision": dict(decision),
            "source_link": dict(link),
            "outcome": dict(outcome or {}),
            "reasons": list(reasons),
            "tail_bucket": tail,
            "stratum": stratum,
            "stratum_id": sid,
            "fingerprint": fingerprint,
            "repeat_count": 1,
            "reservoir_priority": _sha256_text(
                config.seed + "|reservoir|" + sid + "|" + fingerprint
            ),
        }
        reservoir = reservoirs[sid]
        reservoir.append(candidate)
        retained_by_fingerprint[fingerprint] = candidate
        reservoir.sort(
            key=lambda item: (str(item["reservoir_priority"]), str(item["fingerprint"]))
        )
        if len(reservoir) > config.maximum_per_stratum:
            evicted = reservoir.pop()
            retained_by_fingerprint.pop(str(evicted["fingerprint"]), None)

    capacities = {sid: int(count) for sid, count in unique_stratum_counts.items()}
    quotas, target_min = _allocate_quotas(capacities, config)

    sample_rows: list[dict[str, Any]] = []
    balance_rows: list[dict[str, Any]] = []
    for sid in sorted(reservoirs):
        quota = quotas[sid]
        unique_total = int(unique_stratum_counts[sid])
        ordered = reservoirs[sid]
        selected = ordered[:quota]
        sample_weight = unique_total / quota if quota else 0.0
        raw_total = int(raw_stratum_counts[sid])
        balance_rows.append(
            {
                "stratum_id": sid,
                **stratum_payloads[sid],
                "total_count_before_dedupe": raw_total,
                "unique_total_count": unique_total,
                "deterministic_repeats_removed": raw_total - unique_total,
                "requested_minimum_quota": target_min[sid],
                "effective_quota": quota,
                "maximum_quota": config.maximum_per_stratum,
                "minimum_quota_satisfied": quota >= target_min[sid],
                "sample_weight": sample_weight,
            }
        )
        for candidate in selected:
            decision = candidate["decision"]
            link = candidate["source_link"]
            outcome = candidate["outcome"]
            fingerprint = candidate["fingerprint"]
            sample_rows.append(
                {
                    "case_id": "g4irsf11-" + fingerprint[:20],
                    "decision_id": decision["decision_id"],
                    "runtime_bag_id": link["runtime_bag_id"],
                    "task_id": decision["task_id"],
                    "segment_id": decision["segment_id"],
                    "event_time": decision["event_time"],
                    "scenario": candidate["stratum"]["scenario"],
                    "scenario_observed": (decision.get("metadata") or {}).get("scenario", "unspecified"),
                    "scale": candidate["stratum"]["scale"],
                    "source_node": link["source_node"],
                    "goal_node": decision["goal_node"],
                    "junction_node": decision["current_node"],
                    "fault_bucket": candidate["stratum"]["fault"],
                    "reason_bucket": candidate["stratum"]["reason"],
                    "tail_bucket": candidate["tail_bucket"],
                    "why_hard": list(candidate["reasons"]),
                    "candidate_next_nodes": list(decision["candidate_next_nodes"]),
                    "candidate_records": list(decision["candidate_records"]),
                    "candidate_order_digest": decision["candidate_order_digest"],
                    "model_prediction": decision["model_prediction"],
                    "model_score_semantics": decision["model_score_semantics"],
                    "model_margin": decision["model_margin"],
                    "risk_gate_triggered": decision["risk_gate_triggered"],
                    "fallback_selected_next": decision["fallback_selected_next"],
                    "selected_next": decision["selected_next"],
                    "model_fallback_disagreement": decision["model_fallback_disagreement"],
                    "decision_source": decision["decision_source"],
                    "rule_reason": decision["rule_reason"],
                    "local_snapshot": dict(decision["local_snapshot"]),
                    "short_history": list(decision["short_history"]),
                    "full_astar_used": decision["full_astar_used"],
                    "original_arrival_time": link["original_arrival_time"],
                    "java_arrival_epoch": link["java_arrival_epoch"],
                    "release_time": link["release_time"],
                    "source_queue_delay_seconds": link["source_queue_delay_seconds"],
                    "outcome_ref": decision["decision_id"] if outcome else "",
                    "stratum_id": sid,
                    "stratum_total_count_before_dedupe": raw_total,
                    "stratum_unique_total_count": unique_total,
                    "stratum_quota": quota,
                    "total_count": raw_total,
                    "unique_total_count": unique_total,
                    "quota": quota,
                    "sample_weight": sample_weight,
                    "deterministic_repeat_count": int(candidate["repeat_count"]),
                    "semantic_fingerprint": fingerprint,
                }
            )

    sample_rows.sort(key=lambda row: (str(row["stratum_id"]), str(row["semantic_fingerprint"])))
    missing_minimum = sum(1 for row in balance_rows if not row["minimum_quota_satisfied"])
    statistics = {
        "input_decision_count": input_decision_count,
        "eligible_hard_case_count_before_dedupe": raw_eligible,
        "routine_decision_count_excluded": routine_excluded,
        "unique_hard_case_count_after_dedupe": len(seen_fingerprints),
        "deterministic_repeat_count_removed": raw_eligible - len(seen_fingerprints),
        "stratum_count": len(reservoirs),
        "sample_count": len(sample_rows),
        "sampling_limit": config.limit,
        "minimum_per_stratum": config.minimum_per_stratum,
        "maximum_per_stratum": config.maximum_per_stratum,
        "strata_below_requested_minimum": missing_minimum,
        "sampling_seed": config.seed,
        "reservoir_method": "order_independent_bounded_sha256_priority_reservoir",
        "maximum_retained_candidate_rows": sum(len(items) for items in reservoirs.values()),
        "individual_reason_counts_before_dedupe": dict(sorted(individual_reason_counts.items())),
    }
    return SamplingResult(tuple(sample_rows), tuple(balance_rows), statistics)


def outcome_rows_by_decision(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index outcome labels while allowing only explicit join identities."""

    allowed = {
        "decision_id",
        "task_id",
        "segment_id",
        "runtime_bag_id",
        "reached_goal",
        "local_wait_seconds",
        "downstream_wait_seconds",
        "loop_or_dead_end",
        "bag_tth_seconds",
        "tail_bucket",
        "is_p95",
        "is_p99",
        "fault_recovery_outcome",
    }
    result: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        unknown = set(row) - allowed
        if unknown:
            raise DecisionTraceValidationError(f"outcome row {index} has unknown field(s): {sorted(unknown)}")
        decision_id = _required_text(row.get("decision_id"), f"outcome[{index}].decision_id")
        if decision_id in result:
            raise DecisionTraceValidationError(f"duplicate outcome decision_id: {decision_id}")
        identity_fields = {"task_id", "segment_id", "runtime_bag_id"}
        present_identity_fields = identity_fields.intersection(row)
        if present_identity_fields and present_identity_fields != identity_fields:
            raise DecisionTraceValidationError(
                f"outcome row {index} must provide all identity fields together"
            )
        normalized = dict(row)
        if present_identity_fields:
            task_id = _required_int(row.get("task_id"), f"outcome[{index}].task_id")
            runtime_bag_id = _required_int(
                row.get("runtime_bag_id"), f"outcome[{index}].runtime_bag_id"
            )
            if task_id < 0 or runtime_bag_id < 0:
                raise DecisionTraceValidationError(
                    f"outcome row {index} identity integers must be non-negative"
                )
            normalized["task_id"] = task_id
            normalized["segment_id"] = _required_text(
                row.get("segment_id"), f"outcome[{index}].segment_id"
            )
            normalized["runtime_bag_id"] = runtime_bag_id
        result[decision_id] = normalized
    return result


def validate_outcome_decision_identities(
    outcomes: Mapping[str, Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
) -> None:
    """Cross-bind optional outcome identities to their exact decision rows."""

    decisions_by_id = {str(row.get("decision_id")): row for row in decisions}
    for decision_id, outcome in outcomes.items():
        identity_fields = {"task_id", "segment_id", "runtime_bag_id"}
        if not identity_fields.intersection(outcome):
            continue
        decision = decisions_by_id.get(decision_id)
        if decision is None:
            continue
        metadata = decision.get("metadata")
        if not isinstance(metadata, Mapping):
            raise DecisionTraceValidationError(
                f"decision {decision_id} metadata is missing for outcome identity binding"
            )
        expected = (
            _required_int(decision.get("task_id"), f"decision[{decision_id}].task_id"),
            _required_text(
                decision.get("segment_id"), f"decision[{decision_id}].segment_id"
            ),
            _required_int(
                metadata.get("runtime_bag_id"),
                f"decision[{decision_id}].metadata.runtime_bag_id",
            ),
        )
        observed = (
            int(outcome["task_id"]),
            str(outcome["segment_id"]),
            int(outcome["runtime_bag_id"]),
        )
        if observed != expected:
            raise DecisionTraceValidationError(
                f"outcome identity differs from decision {decision_id}: "
                f"observed={observed}, expected={expected}"
            )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
            rows.append(value)
    return rows
