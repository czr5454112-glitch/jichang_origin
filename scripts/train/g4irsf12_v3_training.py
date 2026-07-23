"""Fail-closed G4IRSF12 v3 preparation, validation, and candidate export.

This module deliberately separates four authorities:

* a pre-training gate manifest authorises *whether training may start*;
* a source-data manifest binds immutable decision-time traces, outcomes, and
  feature lineage;
* offline validation may export an immutable candidate model;
* only a later, separately bound closed-loop result may authorise runtime use.

The default invocation is preparation-only.  Missing evidence produces
``BLOCKED_NOT_RUN`` artifacts and never initialises model weights.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
from datetime import date
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sys
from typing import Any, Iterable, Mapping, Sequence
import uuid

import numpy as np


ROOT = Path(__file__).resolve().parents[2]

PROTOCOL_SCHEMA = "czr005.g4irsf12.v3_training_protocol.v1"
DATASET_SCHEMA = "czr005.g4irsf12.v3_decision_dataset.v1"
SOURCE_MANIFEST_SCHEMA = "czr005.g4irsf12.v3_source_manifest.v1"
GATE_MANIFEST_SCHEMA = "czr005.g4irsf12.v3_pretraining_gate.v1"
STATUS_SCHEMA = "czr005.g4irsf12.v3_training_status.v1"
MODEL_SCHEMA = "czr005.g4irsf12.v3_offline_candidate.v1"
CLOSED_LOOP_SCHEMA = "czr005.g4irsf12.v3_closed_loop_validation.v1"

PASS = "PASS"
BLOCKED = "BLOCKED_NOT_RUN"
READY = "READY_NOT_TRAINED"
OFFLINE_PASS = "OFFLINE_VALIDATED_CLOSED_LOOP_REQUIRED"

SEMANTIC_TEXT_HASH = "sha256_utf8_lf_normalized"
EXACT_BYTES_HASH = "sha256_exact_bytes"
TEXT_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".md", ".py", ".txt"})

MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
MAP_RAW_SHA256 = "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
MAP_SEMANTIC_SHA256 = "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
TASK_RAW_SHA256 = "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
TASK_SEMANTIC_SHA256 = TASK_RAW_SHA256
TASK_SEGMENT_COUNT = 43_603
RAW_BAG_COUNT = 28_506

DEFAULT_PROTOCOL = Path("artifacts/configs/g4irsf12_v3_training_protocol.json")
DEFAULT_SCHEMA = Path("artifacts/datasets/g4irsf12_v3_schema.json")
DEFAULT_GATE_MANIFEST = Path("artifacts/gates/g4irsf12_v3_pretraining_gate_manifest.json")
DEFAULT_SOURCE_MANIFEST = Path("artifacts/datasets/g4irsf12_v3_source_manifest.json")
DEFAULT_DATASET_MANIFEST = Path("artifacts/datasets/g4irsf12_v3_manifest.json")
DEFAULT_STATUS = Path("outputs/reports/g4irsf12_v3_training_status.json")
DEFAULT_TRAINING_REPORT = Path("outputs/reports/g4irsf12_v3_training_report.md")
DEFAULT_CLOSED_LOOP_REPORT = Path("outputs/reports/g4irsf12_v3_closed_loop_report.md")
DEFAULT_MODEL_AB = Path("outputs/tables/g4irsf12_v3_model_ab.csv")
DEFAULT_FEATURE_ABLATION = Path("outputs/tables/g4irsf12_v3_feature_ablation.csv")
DEFAULT_MODEL_DIR = Path("artifacts/models")

REQUIRED_GATES = (
    "resource_semantics_frozen",
    "size_ladder_8192_stable",
    "bounded_local_pibt_invariants",
    "pressure_credit_frozen",
    "decision_trace_actual_candidates_actions",
    "no_leakage",
    "hard_negative_easy_stratification",
    "frozen_scorer_diagnostic_complete",
)

ALLOWED_MODELS = (
    "v3_linear_ranker",
    "v3_pairwise_ranker",
    "v3_listwise_ranker",
    "v3_tiny_mlp",
    "v3_feature_pruned_mlp",
    "v3_ranker_plus_calibrated_risk_head",
)
IMPLEMENTED_MODELS = ("v3_linear_ranker",)
FORBIDDEN_MODELS = ("PPO", "MAPPO", "full_RL", "Transformer", "large_GNN")

# This allow-list is intentionally explicit.  Adding a runtime field does not
# silently make it a legal model input; this protocol must be revised and
# re-hashed first.
ALLOWED_FEATURES = (
    "static_potential",
    "travel_time",
    "target_queue_length",
    "target_scheduled_incoming",
    "corridor_next_available",
    "target_next_available",
    "advertised_fault",
    "fault_message_age_seconds",
    "recent_visit_count",
    "two_hop_queue_pressure",
    "current_goal_queue_length",
    "target_goal_queue_length",
    "target_goal_scheduled_incoming",
    "current_goal_max_wait",
    "goal_conditioned_differential",
    "estimated_service_rate",
    "service_weighted_pressure",
    "first_edge_credit_required",
    "first_edge_credit_matches",
    "first_edge_credit_valid",
    "first_edge_credit_slack_seconds",
    "candidate_node_type_code",
    "local_calendar_wait_seconds",
    "deadline_slack_seconds",
    "waiting_age_seconds",
    "recent_edge_service_rate",
    "local_cycle_motif_code",
    "pibt_is_local_owner",
    "pibt_local_blocker_depth",
    "pibt_inherited_priority",
    "merge_incoming_ready_count",
    "merge_service_slack_seconds",
)

FEATURE_LINEAGE_SOURCES: dict[str, tuple[str, ...]] = {
    "static_potential": (
        "graph.static_potential",
        "goal_node",
        "candidate_records[].next_node",
    ),
    "travel_time": (
        "graph.edge_travel_time",
        "current_node",
        "candidate_records[].next_node",
    ),
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
    "current_goal_queue_length": ("local_current.goal_conditioned_queue_length",),
    "target_goal_queue_length": ("local_neighbor.goal_conditioned_queue_length",),
    "target_goal_scheduled_incoming": (
        "local_neighbor.goal_conditioned_scheduled_incoming",
    ),
    "current_goal_max_wait": ("local_current.goal_conditioned_max_wait", "event_time"),
    "goal_conditioned_differential": (
        "local_current.goal_conditioned_queue_length",
        "local_neighbor.goal_conditioned_queue_length",
        "local_neighbor.goal_conditioned_scheduled_incoming",
    ),
    "estimated_service_rate": (
        "local_edge.service_duration",
        "local_neighbor.service_duration",
    ),
    "service_weighted_pressure": (
        "candidate_records[].features.goal_conditioned_differential",
        "candidate_records[].features.estimated_service_rate",
    ),
    "first_edge_credit_required": (
        "runtime.admission_mode",
        "bag.first_edge_credit_consumed",
    ),
    "first_edge_credit_matches": (
        "active_first_edge_credit.to_node",
        "candidate_records[].next_node",
    ),
    "first_edge_credit_valid": (
        "active_first_edge_credit.validation_state",
        "event_time",
    ),
    "first_edge_credit_slack_seconds": (
        "active_first_edge_credit.latest",
        "active_first_edge_credit.expiry",
        "event_time",
    ),
    "candidate_node_type_code": ("graph.node_type", "candidate_records[].next_node"),
    "local_calendar_wait_seconds": (
        "event_time",
        "local_edge.next_available_time",
        "local_neighbor.next_available_time",
    ),
    "deadline_slack_seconds": ("bag.deadline", "event_time"),
    "waiting_age_seconds": ("bag.ready_time", "event_time"),
    "recent_edge_service_rate": ("local_edge.bounded_recent_departures",),
    "local_cycle_motif_code": (
        "short_history",
        "graph.bounded_local_adjacency",
        "candidate_records[].next_node",
    ),
    "pibt_is_local_owner": (
        "local_pibt_slice.resource_owner",
        "bag.runtime_identity",
    ),
    "pibt_local_blocker_depth": ("local_pibt_slice.bounded_blocker_chain",),
    "pibt_inherited_priority": ("local_pibt_slice.inherited_priority",),
    "merge_incoming_ready_count": ("local_merge.ready_owner_count",),
    "merge_service_slack_seconds": (
        "event_time",
        "local_merge.next_available_time",
    ),
}

FORBIDDEN_KEY_TOKENS = (
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

SPLIT_SEEDS = (11, 29, 47)
SPLIT_NAMES = (
    "grouped_random",
    "time_block_heldout",
    "source_heldout",
    "goal_heldout",
    "junction_heldout",
    "congestion_heldout",
    "fault_heldout",
    "decision_motif_heldout",
)
HARD_NEGATIVE_CATEGORIES = (
    "frozen_scorer_disagreement",
    "shield_rejection",
    "pibt_takeover",
    "active_fault",
    "tail_wait",
    "loop_or_dead_end",
    "credit_invalid_or_mismatch",
)


class PhaseIError(ValueError):
    """Raised when a Phase-I evidence or training invariant is violated."""


@dataclass(frozen=True)
class Example:
    decision_id: str
    task_id: str
    bag_family: str
    semantic_fingerprint: str
    event_time: float
    time_block: str
    source: str
    goal: str
    junction: str
    congestion: str
    fault: str
    motif: str
    candidate_nodes: tuple[int, ...]
    candidate_features: tuple[tuple[float, ...], ...]
    candidate_allowed: tuple[bool, ...]
    selected_index: int
    rank_eligible: bool
    risk_label: int
    hard_categories: tuple[str, ...]
    sample_weight: float


@dataclass(frozen=True)
class PreparedDataset:
    feature_names: tuple[str, ...]
    examples: tuple[Example, ...]
    dataset_sha256: str
    trace_sha256: str
    outcome_sha256: str
    lineage_sha256: str


@dataclass(frozen=True)
class Split:
    name: str
    seed: int
    train_indices: tuple[int, ...]
    validation_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    heldout_values: tuple[str, ...]


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, _json_bytes(value))


def _normalise_text_bytes(value: bytes) -> bytes:
    return value.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_sha256(path: Path) -> str:
    return hashlib.sha256(_normalise_text_bytes(path.read_bytes())).hexdigest()


def artifact_sha256(path: Path, semantics: str | None = None) -> str:
    selected = semantics or (
        SEMANTIC_TEXT_HASH if path.suffix.lower() in TEXT_SUFFIXES else EXACT_BYTES_HASH
    )
    if selected == SEMANTIC_TEXT_HASH:
        return semantic_sha256(path)
    if selected == EXACT_BYTES_HASH:
        return raw_sha256(path)
    raise PhaseIError(f"unsupported hash semantics: {selected}")


def _relative(root: Path, path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def descriptor(root: Path, path: Path, *, row_count: int | None = None) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise PhaseIError(f"artifact escapes repository root: {resolved}")
    semantics = (
        SEMANTIC_TEXT_HASH if resolved.suffix.lower() in TEXT_SUFFIXES else EXACT_BYTES_HASH
    )
    result: dict[str, Any] = {
        "path": _relative(root, resolved),
        "sha256": artifact_sha256(resolved, semantics),
        "hash_semantics": semantics,
    }
    if row_count is not None:
        result["row_count"] = int(row_count)
    return result


def _resolve_bound_path(root: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise PhaseIError("artifact path is missing")
    raw = Path(value)
    resolved = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise PhaseIError(f"artifact path escapes repository: {resolved}")
    return resolved


def verify_descriptor(
    root: Path,
    value: Any,
    *,
    require_rows: bool = False,
) -> tuple[Path | None, list[str]]:
    blockers: list[str] = []
    if not isinstance(value, Mapping):
        return None, ["artifact descriptor is not an object"]
    try:
        path = _resolve_bound_path(root, value.get("path"))
    except PhaseIError as exc:
        return None, [str(exc)]
    if not path.is_file():
        return path, [f"artifact does not exist: {_relative(root, path)}"]
    semantics = str(value.get("hash_semantics") or "")
    if semantics not in {SEMANTIC_TEXT_HASH, EXACT_BYTES_HASH}:
        blockers.append(f"{_relative(root, path)}: unsupported or missing hash semantics")
        return path, blockers
    expected = str(value.get("sha256") or "").lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        blockers.append(f"{_relative(root, path)}: invalid SHA-256 descriptor")
    else:
        actual = artifact_sha256(path, semantics)
        if actual != expected:
            blockers.append(f"{_relative(root, path)}: SHA-256 mismatch")
    if require_rows:
        expected_rows = value.get("row_count")
        if isinstance(expected_rows, bool) or not isinstance(expected_rows, int) or expected_rows <= 0:
            blockers.append(f"{_relative(root, path)}: positive row_count is required")
        else:
            with path.open("r", encoding="utf-8", newline="") as handle:
                actual_rows = sum(1 for line in handle if line.strip())
            if path.suffix.lower() == ".csv":
                actual_rows = max(0, actual_rows - 1)
            if actual_rows != expected_rows:
                blockers.append(
                    f"{_relative(root, path)}: row_count {actual_rows} != {expected_rows}"
                )
    return path, blockers


def protocol_manifest() -> dict[str, Any]:
    """Return the immutable executable contract for G4IRSF12 Phase I."""

    return {
        "schema": PROTOCOL_SCHEMA,
        "stage": "G4IRSF12-I",
        "generated_date": date.today().isoformat(),
        "status_semantics": {
            BLOCKED: "No model weights are initialised and no model artifact is written.",
            READY: "Inputs pass preparation but training was not explicitly authorised.",
            OFFLINE_PASS: (
                "An immutable offline candidate exists, but runtime activation remains forbidden "
                "until a separately bound closed-loop PASS."
            ),
        },
        "protected_inputs": {
            "map": {
                "path": MAP_PATH.as_posix(),
                "raw_sha256": MAP_RAW_SHA256,
                "semantic_sha256": MAP_SEMANTIC_SHA256,
                "topology_mutation_allowed": False,
            },
            "tasks": {
                "path": TASK_PATH.as_posix(),
                "raw_sha256": TASK_RAW_SHA256,
                "semantic_sha256": TASK_SEMANTIC_SHA256,
                "segment_count": TASK_SEGMENT_COUNT,
                "raw_bag_count": RAW_BAG_COUNT,
                "mutation_allowed": False,
            },
        },
        "required_pretraining_gates": list(REQUIRED_GATES),
        "allowed_models": list(ALLOWED_MODELS),
        "implemented_models": list(IMPLEMENTED_MODELS),
        "forbidden_models": list(FORBIDDEN_MODELS),
        "model_responsibility": "rank_current_true_outgoing_neighbors_only",
        "pibt_responsibility": "bounded_local_multi_bag_coordination_and_atomic_action_set",
        "shield_responsibility": "physical_fault_resource_dead_end_queue_and_credit_legality",
        "feature_contract": {
            "allowed": list(ALLOWED_FEATURES),
            "lineage_sources": {
                name: list(FEATURE_LINEAGE_SOURCES[name]) for name in ALLOWED_FEATURES
            },
            "absolute_node_id_model_inputs_allowed": False,
            "future_route_inputs_allowed": False,
            "post_hoc_inputs_allowed": False,
            "reservation_depth": 1,
            "bounded_local_state_only": True,
        },
        "label_contract": {
            "rank_positive": (
                "actual committed selected_next only when the separate outcome is successful, "
                "non-looping, and the action was shield-allowed"
            ),
            "failed_or_looping_action": (
                "retained for risk/weight audit; never inverted into an unobserved correct action"
            ),
            "candidate_negative": (
                "other true outgoing candidates; shield-disallowed actions are explicit hard "
                "negatives, not positive counterfactual labels"
            ),
            "teacher_route_suffix_allowed": False,
            "outcomes_storage": "separate_hash_bound_jsonl",
        },
        "hard_negative_contract": {
            "categories": list(HARD_NEGATIVE_CATEGORIES),
            "easy_examples_required": True,
            "hard_examples_required": True,
            "maximum_rank_weight": 4.0,
            "failures_retained_even_when_rank_ineligible": True,
        },
        "split_contract": {
            "seeds": list(SPLIT_SEEDS),
            "splits": list(SPLIT_NAMES),
            "train_validation_test_fraction": [0.70, 0.15, 0.15],
            "component_links": ["bag_family", "semantic_fingerprint"],
            "audit_dimensions": [
                "task_or_bag",
                "time_block",
                "source",
                "goal",
                "junction",
                "congestion",
                "fault",
                "decision_motif",
            ],
            "bag_or_semantic_duplicate_overlap_allowed": False,
        },
        "offline_gates": {
            "candidate_recall": 1.0,
            "minimum_top1": 0.50,
            "minimum_pairwise_accuracy": 0.55,
            "maximum_ece": 0.15,
            "maximum_high_confidence_wrong_rate": 0.02,
            "all_seed_and_heldout_splits_must_pass": True,
            "feature_ablation_required": True,
        },
        "closed_loop_gates": {
            "repeat_count_minimum": 5,
            "completed_bags": RAW_BAG_COUNT,
            "completed_segments": TASK_SEGMENT_COUNT,
            "failed_bags": 0,
            "node_or_resource_conflicts": 0,
            "runtime_full_astar_calls": 0,
            "global_reservation_scans": 0,
            "future_routes_read": 0,
            "unresolved_deadlocks": 0,
            "time_or_event_limit_hit": False,
            "physical_fault_interlock_always_enabled": True,
            "matched_original_entry_denominator_required": True,
        },
        "publication_contract": {
            "candidate_export_is_immutable": True,
            "candidate_runtime_eligible": False,
            "active_pointer_written_by_this_tool": False,
            "closed_loop_manifest_must_bind_candidate_sha256": True,
            "G4J_status": "CLOSED",
        },
    }


def dataset_schema() -> dict[str, Any]:
    """Describe the source-manifest and row contract without claiming data exists."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": DATASET_SCHEMA,
        "title": "G4IRSF12 v3 decision-time training source",
        "description": (
            "The source manifest binds three separate artifacts: legal decision rows, "
            "post-hoc outcomes, and executable feature lineage."
        ),
        "source_manifest_schema": SOURCE_MANIFEST_SCHEMA,
        "required_manifest_fields": [
            "schema",
            "status",
            "fixed_real_map_only",
            "map",
            "tasks",
            "generation",
            "model_feature_names",
            "validation",
            "artifacts",
        ],
        "required_artifacts": ["decision_trace", "outcomes", "feature_lineage"],
        "decision_required_fields": [
            "decision_id",
            "task_id",
            "segment_id",
            "event_time",
            "current_node",
            "goal_node",
            "candidate_next_nodes",
            "candidate_records",
            "selected_next",
            "model_prediction",
            "decision_source",
            "full_astar_used",
            "metadata",
        ],
        "outcome_required_fields": ["decision_id", "reached_goal", "loop_or_dead_end"],
        "candidate_ordering": "next_node_ascending",
        "candidate_set_semantics": "exact_true_outgoing_neighbors",
        "allowed_model_features": list(ALLOWED_FEATURES),
        "feature_lineage_sources": {
            name: list(FEATURE_LINEAGE_SOURCES[name]) for name in ALLOWED_FEATURES
        },
        "feature_lineage_required_columns": [
            "field_path",
            "lineage",
            "role",
            "origin",
            "availability",
            "sources",
            "available_at_decision",
            "model_input_allowed",
            "prohibited_as_runtime_feature",
            "lineage_status",
        ],
        "forbidden_key_tokens": list(FORBIDDEN_KEY_TOKENS),
        "absolute_node_id_model_inputs_allowed": False,
        "full_astar_used": False,
        "global_reservation_scan_used": False,
        "future_route_input_allowed": False,
        "labels_in_decision_trace_allowed": False,
        "outcomes_must_be_separate": True,
    }


def verify_protected_inputs(root: Path) -> list[str]:
    blockers: list[str] = []
    for relative, expected_raw, expected_semantic, label in (
        (MAP_PATH, MAP_RAW_SHA256, MAP_SEMANTIC_SHA256, "map"),
        (TASK_PATH, TASK_RAW_SHA256, TASK_SEMANTIC_SHA256, "task input"),
    ):
        path = root / relative
        if not path.is_file():
            blockers.append(f"{label} is missing: {relative.as_posix()}")
            continue
        if raw_sha256(path) != expected_raw:
            blockers.append(f"{label} raw SHA-256 mismatch")
        if semantic_sha256(path) != expected_semantic:
            blockers.append(f"{label} semantic SHA-256 mismatch")
    return blockers


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PhaseIError(f"{path}: expected a JSON object")
    return value


def validate_gate_manifest(root: Path, path: Path) -> tuple[dict[str, str], list[str]]:
    blockers: list[str] = []
    statuses = {name: "MISSING" for name in REQUIRED_GATES}
    if not path.is_file():
        return statuses, [f"pre-training gate manifest is missing: {_relative(root, path)}"]
    try:
        payload = _read_json_object(path)
    except (OSError, UnicodeError, json.JSONDecodeError, PhaseIError) as exc:
        return statuses, [f"pre-training gate manifest is unreadable: {exc}"]
    if payload.get("schema") != GATE_MANIFEST_SCHEMA:
        blockers.append("pre-training gate manifest schema is missing or unexpected")
    gates = payload.get("gates")
    if not isinstance(gates, Mapping):
        return statuses, blockers + ["pre-training gate manifest gates must be an object"]
    if set(gates) != set(REQUIRED_GATES):
        blockers.append("pre-training gate manifest must contain exactly all required gates")
    for name in REQUIRED_GATES:
        entry = gates.get(name)
        if not isinstance(entry, Mapping):
            blockers.append(f"{name}: gate entry is missing")
            continue
        status = str(entry.get("status") or "MISSING")
        statuses[name] = status
        if status != PASS:
            reasons = entry.get("blockers")
            detail = "; ".join(map(str, reasons)) if isinstance(reasons, list) else ""
            blockers.append(f"{name}: status is {status}" + (f" ({detail})" if detail else ""))
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            blockers.append(f"{name}: at least one hash-bound evidence artifact is required")
            continue
        for index, evidence_descriptor in enumerate(evidence):
            _, errors = verify_descriptor(root, evidence_descriptor)
            blockers.extend(f"{name}.evidence[{index}]: {error}" for error in errors)
    if payload.get("overall_status") != PASS:
        blockers.append("pre-training gate overall_status is not PASS")
    return statuses, sorted(set(blockers))


def _forbidden_paths(value: Any, prefix: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            lowered = key.lower()
            path = f"{prefix}.{key}" if prefix else key
            if any(token in lowered for token in FORBIDDEN_KEY_TOKENS):
                violations.append(path)
            violations.extend(_forbidden_paths(child, path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, child in enumerate(value):
            violations.extend(_forbidden_paths(child, f"{prefix}[{index}]"))
    return violations


def _finite_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        return float(value)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise PhaseIError(f"{label} is not numeric") from exc
    if not math.isfinite(number):
        raise PhaseIError(f"{label} is not finite")
    return number


def _truth(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"1", "true", "yes", "pass"}


def _load_graph_outgoing(path: Path) -> tuple[dict[int, tuple[int, ...]], dict[int, int]]:
    payload = _read_json_object(path)
    raw_edges = payload.get("edges")
    if not isinstance(raw_edges, list):
        raise PhaseIError("map edges must be an array")
    outgoing: dict[int, set[int]] = {}
    incoming: dict[int, int] = {}
    for index, edge in enumerate(raw_edges):
        if not isinstance(edge, Mapping):
            raise PhaseIError(f"map edge[{index}] is not an object")
        try:
            start = int(edge["start"])
            end = int(edge["end"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise PhaseIError(f"map edge[{index}] start/end is invalid") from exc
        outgoing.setdefault(start, set()).add(end)
        outgoing.setdefault(end, set())
        incoming[end] = incoming.get(end, 0) + 1
        incoming.setdefault(start, incoming.get(start, 0))
    return (
        {node: tuple(sorted(neighbors)) for node, neighbors in outgoing.items()},
        incoming,
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise PhaseIError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise PhaseIError(f"{path}:{line_number}: row must be an object")
            rows.append(value)
    return rows


def _lineage_model_features(path: Path) -> tuple[set[str], list[str]]:
    blockers: list[str] = []
    approved: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "field_path",
            "lineage",
            "role",
            "origin",
            "availability",
            "sources",
            "available_at_decision",
            "model_input_allowed",
            "prohibited_as_runtime_feature",
            "lineage_status",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            return set(), ["feature lineage table is missing required columns"]
        for row_number, row in enumerate(reader, start=2):
            field = str(row.get("field_path") or "")
            if not field.startswith("candidate_records[].features."):
                continue
            feature = field.rsplit(".", 1)[-1]
            if feature == "*":
                continue
            try:
                raw_sources = json.loads(str(row.get("sources") or "[]"))
            except json.JSONDecodeError:
                raw_sources = None
            expected_sources = FEATURE_LINEAGE_SOURCES.get(feature)
            sources_match = (
                isinstance(raw_sources, list)
                and all(isinstance(value, str) for value in raw_sources)
                and expected_sources is not None
                and tuple(raw_sources) == expected_sources
            )
            if (
                row.get("lineage") == "runtime"
                and bool(str(row.get("role") or "").strip())
                and bool(str(row.get("origin") or "").strip())
                and row.get("availability") in {"decision_time", "static"}
                and sources_match
                and _truth(row.get("available_at_decision"))
                and _truth(row.get("model_input_allowed"))
                and not _truth(row.get("prohibited_as_runtime_feature"))
                and row.get("lineage_status") == PASS
            ):
                approved.add(feature)
            else:
                blockers.append(
                    f"feature lineage row {row_number} does not approve {feature} as a "
                    "decision-time runtime input with the protocol-bound dependencies"
                )
    return approved, blockers


def _bag_family(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    explicit = metadata.get("bag_group_id") or metadata.get("original_bag_id")
    if explicit not in (None, ""):
        return str(explicit)
    segment = str(row.get("segment_id") or "")
    # Runtime/scenario suffixes change across repeats.  The original task and
    # segment kind before a g4irsf suffix remain stable.
    stable_segment = segment.split(":g4irsf", 1)[0]
    if not stable_segment:
        stable_segment = segment
    return f"{row.get('task_id')}|{stable_segment}"


def _semantic_fingerprint(row: Mapping[str, Any], feature_names: Sequence[str]) -> str:
    candidates = []
    for candidate in row["candidate_records"]:
        features = candidate["features"]
        candidates.append(
            {
                "next_node": int(candidate["next_node"]),
                "features": {name: features[name] for name in feature_names},
                "shield_allowed": bool(candidate.get("shield_allowed", True)),
            }
        )
    value = {
        "current_node": int(row["current_node"]),
        "goal_node": int(row["goal_node"]),
        "candidates": candidates,
        "short_history": list(row.get("short_history") or [])[-8:],
        "local_snapshot": row.get("local_snapshot") or {},
    }
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _hard_categories(row: Mapping[str, Any], outcome: Mapping[str, Any]) -> tuple[str, ...]:
    categories: set[str] = set()
    if int(row["model_prediction"]) != int(row["selected_next"]):
        categories.add("frozen_scorer_disagreement")
    records = row["candidate_records"]
    if any(candidate.get("shield_allowed") is False for candidate in records):
        categories.add("shield_rejection")
    source = str(row.get("decision_source") or "").lower()
    if "pibt" in source or _truth((row.get("metadata") or {}).get("pibt_takeover")):
        categories.add("pibt_takeover")
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    fault_text = " ".join(
        str(metadata.get(name) or "").lower()
        for name in ("fault_mode", "fault_scenario", "fault_regime")
    )
    if (
        any(
            _truth(candidate["features"].get("advertised_fault"))
            for candidate in records
        )
        or ("fault" in fault_text and "no_fault" not in fault_text)
    ):
        categories.add("active_fault")
    if str(outcome.get("tail_bucket") or "").lower() in {"p95_tail", "p99_tail"} or _truth(
        outcome.get("is_p95")
    ):
        categories.add("tail_wait")
    if _truth(outcome.get("loop_or_dead_end")) or _truth(outcome.get("deadlock")):
        categories.add("loop_or_dead_end")
    for candidate in records:
        features = candidate["features"]
        if _truth(features.get("first_edge_credit_required")) and (
            not _truth(features.get("first_edge_credit_valid"))
            or not _truth(features.get("first_edge_credit_matches"))
        ):
            categories.add("credit_invalid_or_mismatch")
    return tuple(sorted(categories))


def _congestion_regime(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    explicit = metadata.get("congestion_regime") or metadata.get("load_level")
    if explicit not in (None, ""):
        return str(explicit)
    snapshot = row.get("local_snapshot") if isinstance(row.get("local_snapshot"), Mapping) else {}
    queue = int(float(snapshot.get("junction_queue_length") or 0))
    return "empty" if queue == 0 else "light" if queue <= 2 else "congested"


def _fault_regime(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    explicit = (
        metadata.get("fault_regime")
        or metadata.get("fault_scenario")
        or metadata.get("fault_mode")
    )
    if explicit not in (None, ""):
        return str(explicit)
    return "active_fault" if any(
        _truth(candidate["features"].get("advertised_fault"))
        for candidate in row["candidate_records"]
    ) else "no_fault"


def _motif(row: Mapping[str, Any], incoming_degree: Mapping[int, int]) -> str:
    metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
    explicit = metadata.get("decision_motif")
    if explicit not in (None, ""):
        return str(explicit)
    node = int(row["current_node"])
    out_degree = len(row["candidate_next_nodes"])
    in_degree = int(incoming_degree.get(node, 0))
    if in_degree > 1 and out_degree > 1:
        return "merge_split"
    if in_degree > 1:
        return "merge"
    if out_degree > 1:
        return "split"
    return "linear"


def prepare_dataset(
    root: Path,
    source_manifest_path: Path,
) -> tuple[PreparedDataset | None, dict[str, Any], list[str]]:
    """Validate and join source artifacts without initialising any weights."""

    blockers: list[str] = []
    audit: dict[str, Any] = {
        "source_manifest": _relative(root, source_manifest_path),
        "trace_rows": 0,
        "outcome_rows": 0,
        "rank_eligible_rows": 0,
        "risk_positive_rows": 0,
        "easy_rows": 0,
        "hard_rows": 0,
        "hard_category_counts": {name: 0 for name in HARD_NEGATIVE_CATEGORIES},
    }
    if not source_manifest_path.is_file():
        return None, audit, [
            f"G4IRSF12 v3 source manifest is missing: {_relative(root, source_manifest_path)}"
        ]
    try:
        manifest = _read_json_object(source_manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError, PhaseIError) as exc:
        return None, audit, [f"G4IRSF12 v3 source manifest is unreadable: {exc}"]
    if manifest.get("schema") != SOURCE_MANIFEST_SCHEMA:
        blockers.append("source manifest schema is missing or unexpected")
    if manifest.get("status") != PASS:
        blockers.append("source manifest status is not PASS")
    if manifest.get("fixed_real_map_only") is not True:
        blockers.append("source manifest is not fixed-real-map-only")
    map_binding = manifest.get("map") if isinstance(manifest.get("map"), Mapping) else {}
    task_binding = manifest.get("tasks") if isinstance(manifest.get("tasks"), Mapping) else {}
    if (
        map_binding.get("path") != MAP_PATH.as_posix()
        or map_binding.get("raw_sha256") != MAP_RAW_SHA256
        or map_binding.get("semantic_sha256") != MAP_SEMANTIC_SHA256
    ):
        blockers.append("source manifest canonical map binding is absent or stale")
    if (
        task_binding.get("path") != TASK_PATH.as_posix()
        or task_binding.get("raw_sha256") != TASK_RAW_SHA256
        or task_binding.get("semantic_sha256") != TASK_SEMANTIC_SHA256
        or task_binding.get("segment_count") != TASK_SEGMENT_COUNT
        or task_binding.get("raw_bag_count") != RAW_BAG_COUNT
    ):
        blockers.append("source manifest canonical task binding is absent or stale")
    generation = (
        manifest.get("generation") if isinstance(manifest.get("generation"), Mapping) else {}
    )
    for field in (
        "resource_semantics_id",
        "pibt_mode",
        "pressure_mode",
        "admission_mode",
        "implementation_sha256",
        "source_bundle_sha256",
    ):
        if not generation.get(field):
            blockers.append(f"source manifest generation.{field} is missing")
    if generation.get("reservation_depth") != 1:
        blockers.append("source manifest reservation_depth must be exactly one")
    if generation.get("runtime_full_astar_calls") != 0:
        blockers.append("source trace producer used runtime full A*/CIE")
    if generation.get("global_reservation_scan_count") != 0:
        blockers.append("source trace producer used a global reservation scan")
    if generation.get("future_route_read_count") != 0:
        blockers.append("source trace producer read a future route")
    if generation.get("physical_fault_interlock_always_enabled") is not True:
        blockers.append("physical fault interlock was not declared always enabled")
    validations = (
        manifest.get("validation") if isinstance(manifest.get("validation"), Mapping) else {}
    )
    for name in (
        "candidate_completeness",
        "actual_selected_action",
        "feature_lineage",
        "no_leakage",
        "trace_outcome_separation",
        "hard_negative_easy_stratification",
    ):
        if validations.get(name) != PASS:
            blockers.append(f"source validation.{name} is not PASS")
    raw_feature_names = manifest.get("model_feature_names")
    if not isinstance(raw_feature_names, list) or not raw_feature_names:
        blockers.append("source manifest model_feature_names must be a non-empty array")
        feature_names: tuple[str, ...] = ()
    else:
        feature_names = tuple(map(str, raw_feature_names))
        if len(feature_names) != len(set(feature_names)):
            blockers.append("source manifest model_feature_names contains duplicates")
        unknown = sorted(set(feature_names) - set(ALLOWED_FEATURES))
        if unknown:
            blockers.append(f"source manifest contains unapproved model features: {unknown}")
        if any("node_id" in name.lower() or name.lower() == "next_node" for name in feature_names):
            blockers.append("absolute node ID features are forbidden in the main v3 model")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return None, audit, sorted(set(blockers + ["source manifest artifacts is missing"]))
    paths: dict[str, Path] = {}
    for name in ("decision_trace", "outcomes", "feature_lineage"):
        path, errors = verify_descriptor(root, artifacts.get(name), require_rows=True)
        blockers.extend(f"{name}: {error}" for error in errors)
        if path is not None and not errors:
            paths[name] = path
    if blockers or set(paths) != {"decision_trace", "outcomes", "feature_lineage"}:
        return None, audit, sorted(set(blockers))
    approved_features, lineage_blockers = _lineage_model_features(paths["feature_lineage"])
    blockers.extend(lineage_blockers)
    missing_lineage = sorted(set(feature_names) - approved_features)
    if missing_lineage:
        blockers.append(f"feature lineage does not approve model features: {missing_lineage}")
    try:
        trace_rows = _read_jsonl(paths["decision_trace"])
        outcome_rows = _read_jsonl(paths["outcomes"])
        outgoing, incoming_degree = _load_graph_outgoing(root / MAP_PATH)
    except (OSError, UnicodeError, json.JSONDecodeError, PhaseIError) as exc:
        return None, audit, sorted(set(blockers + [f"source artifacts cannot be loaded: {exc}"]))
    audit["trace_rows"] = len(trace_rows)
    audit["outcome_rows"] = len(outcome_rows)
    outcomes: dict[str, dict[str, Any]] = {}
    for index, outcome in enumerate(outcome_rows):
        decision_id = str(outcome.get("decision_id") or "")
        if not decision_id:
            blockers.append(f"outcome[{index}] has no decision_id")
            continue
        if decision_id in outcomes:
            blockers.append(f"duplicate outcome decision_id: {decision_id}")
        if "reached_goal" not in outcome or "loop_or_dead_end" not in outcome:
            blockers.append(f"outcome[{index}] is missing required outcome fields")
        outcomes[decision_id] = outcome
    examples: list[Example] = []
    seen_decisions: set[str] = set()
    for index, row in enumerate(trace_rows):
        prefix = f"decision[{index}]"
        violations = _forbidden_paths(row)
        if violations:
            blockers.append(f"{prefix} contains forbidden future/post-hoc fields: {violations}")
            continue
        decision_id = str(row.get("decision_id") or "")
        if not decision_id:
            blockers.append(f"{prefix} has no decision_id")
            continue
        if decision_id in seen_decisions:
            blockers.append(f"duplicate trace decision_id: {decision_id}")
            continue
        seen_decisions.add(decision_id)
        outcome = outcomes.get(decision_id)
        if outcome is None:
            blockers.append(f"{prefix} has no separately joined outcome")
            continue
        try:
            current = int(row["current_node"])
            goal = int(row["goal_node"])
            selected = int(row["selected_next"])
            model_prediction = int(row["model_prediction"])
            event_time = _finite_number(row["event_time"], f"{prefix}.event_time")
            candidate_nodes = tuple(int(value) for value in row["candidate_next_nodes"])
            records = row["candidate_records"]
        except (KeyError, TypeError, ValueError, OverflowError, PhaseIError) as exc:
            blockers.append(f"{prefix} has invalid required fields: {exc}")
            continue
        if row.get("full_astar_used") is not False:
            blockers.append(f"{prefix}.full_astar_used must be false")
        if not isinstance(records, list) or not records:
            blockers.append(f"{prefix}.candidate_records must be a non-empty array")
            continue
        if tuple(sorted(candidate_nodes)) != candidate_nodes or len(set(candidate_nodes)) != len(
            candidate_nodes
        ):
            blockers.append(f"{prefix}.candidate_next_nodes must be sorted and unique")
            continue
        if candidate_nodes != outgoing.get(current, ()):
            blockers.append(f"{prefix} candidates do not equal true map outgoing neighbors")
            continue
        if len(records) != len(candidate_nodes):
            blockers.append(f"{prefix} candidate record/node lengths differ")
            continue
        candidate_features: list[tuple[float, ...]] = []
        allowed: list[bool] = []
        malformed = False
        for candidate_index, (candidate, node) in enumerate(zip(records, candidate_nodes)):
            if not isinstance(candidate, Mapping) or int(candidate.get("next_node", -1)) != node:
                blockers.append(f"{prefix}.candidate_records[{candidate_index}] node mismatch")
                malformed = True
                break
            features = candidate.get("features")
            if not isinstance(features, Mapping):
                blockers.append(f"{prefix}.candidate_records[{candidate_index}] features missing")
                malformed = True
                break
            unknown = sorted(set(map(str, features)) - set(ALLOWED_FEATURES))
            if unknown:
                blockers.append(
                    f"{prefix}.candidate_records[{candidate_index}] has unapproved features: "
                    f"{unknown}"
                )
                malformed = True
                break
            missing = sorted(set(feature_names) - set(map(str, features)))
            if missing:
                blockers.append(
                    f"{prefix}.candidate_records[{candidate_index}] misses model features: "
                    f"{missing}"
                )
                malformed = True
                break
            try:
                candidate_features.append(
                    tuple(
                        _finite_number(features[name], f"{prefix}.{node}.{name}")
                        for name in feature_names
                    )
                )
            except PhaseIError as exc:
                blockers.append(str(exc))
                malformed = True
                break
            allowed.append(candidate.get("shield_allowed") is not False)
        if malformed:
            continue
        if selected not in candidate_nodes or model_prediction not in candidate_nodes:
            blockers.append(f"{prefix} selected/model action is outside candidates")
            continue
        selected_index = candidate_nodes.index(selected)
        categories = _hard_categories(row, outcome)
        reached_goal = _truth(outcome.get("reached_goal"))
        loop = _truth(outcome.get("loop_or_dead_end")) or _truth(outcome.get("deadlock"))
        rank_eligible = (
            len(candidate_nodes) >= 2
            and reached_goal
            and not loop
            and allowed[selected_index]
        )
        risk_label = int(not reached_goal or loop or not allowed[selected_index])
        weight = min(4.0, 1.0 + 0.5 * len(categories))
        metadata = row.get("metadata") if isinstance(row.get("metadata"), Mapping) else {}
        source = metadata.get("source_node")
        if source in (None, ""):
            history = row.get("short_history")
            source = history[0] if isinstance(history, list) and history else current
        fingerprint = str(metadata.get("semantic_fingerprint") or "")
        if not fingerprint:
            fingerprint = _semantic_fingerprint(row, feature_names)
        example = Example(
            decision_id=decision_id,
            task_id=str(row.get("task_id")),
            bag_family=_bag_family(row),
            semantic_fingerprint=fingerprint,
            event_time=event_time,
            time_block=str(int(event_time // 900.0)),
            source=str(source),
            goal=str(goal),
            junction=str(current),
            congestion=_congestion_regime(row),
            fault=_fault_regime(row),
            motif=_motif(row, incoming_degree),
            candidate_nodes=candidate_nodes,
            candidate_features=tuple(candidate_features),
            candidate_allowed=tuple(allowed),
            selected_index=selected_index,
            rank_eligible=rank_eligible,
            risk_label=risk_label,
            hard_categories=categories,
            sample_weight=weight,
        )
        examples.append(example)
        if rank_eligible:
            audit["rank_eligible_rows"] += 1
        if risk_label:
            audit["risk_positive_rows"] += 1
        if categories:
            audit["hard_rows"] += 1
            for category in categories:
                audit["hard_category_counts"][category] += 1
        else:
            audit["easy_rows"] += 1
    extra_outcomes = sorted(set(outcomes) - seen_decisions)
    if extra_outcomes:
        blockers.append(f"{len(extra_outcomes)} outcomes have no matching decision trace row")
    if not examples:
        blockers.append("no valid decision examples remain")
    if audit["rank_eligible_rows"] <= 0:
        blockers.append("no successful multi-candidate rank examples remain")
    if audit["hard_rows"] <= 0:
        blockers.append("no hard-negative examples are present")
    if audit["easy_rows"] <= 0:
        blockers.append("no easy examples are present for stratified comparison")
    if blockers:
        return None, audit, sorted(set(blockers))
    dataset_value = {
        "feature_names": feature_names,
        "examples": [
            {
                "decision_id": example.decision_id,
                "bag_family": example.bag_family,
                "semantic_fingerprint": example.semantic_fingerprint,
                "candidate_nodes": example.candidate_nodes,
                "candidate_features": example.candidate_features,
                "candidate_allowed": example.candidate_allowed,
                "selected_index": example.selected_index,
                "rank_eligible": example.rank_eligible,
                "risk_label": example.risk_label,
                "hard_categories": example.hard_categories,
                "sample_weight": example.sample_weight,
            }
            for example in examples
        ],
    }
    dataset = PreparedDataset(
        feature_names=feature_names,
        examples=tuple(examples),
        dataset_sha256=hashlib.sha256(_canonical_bytes(dataset_value)).hexdigest(),
        trace_sha256=semantic_sha256(paths["decision_trace"]),
        outcome_sha256=semantic_sha256(paths["outcomes"]),
        lineage_sha256=semantic_sha256(paths["feature_lineage"]),
    )
    audit["dataset_sha256"] = dataset.dataset_sha256
    return dataset, audit, []


class _UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left != root_right:
            self.parent[max(root_left, root_right)] = min(root_left, root_right)


def _components(examples: Sequence[Example]) -> list[tuple[int, ...]]:
    union = _UnionFind(len(examples))
    bag_owner: dict[str, int] = {}
    fingerprint_owner: dict[str, int] = {}
    for index, example in enumerate(examples):
        for key, owners in (
            (example.bag_family, bag_owner),
            (example.semantic_fingerprint, fingerprint_owner),
        ):
            prior = owners.setdefault(key, index)
            union.union(index, prior)
    grouped: dict[int, list[int]] = {}
    for index in range(len(examples)):
        grouped.setdefault(union.find(index), []).append(index)
    return [tuple(indices) for _, indices in sorted(grouped.items())]


def _stable_fraction(seed: int, *parts: Any) -> float:
    payload = "|".join([str(seed), *(str(part) for part in parts)]).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big") / float(2**64)


def build_splits(dataset: PreparedDataset) -> tuple[dict[str, Split], list[dict[str, Any]]]:
    """Create deterministic, leakage-safe multi-seed grouped/held-out splits."""

    examples = dataset.examples
    components = _components(examples)
    component_for_index = {
        index: component_index
        for component_index, component in enumerate(components)
        for index in component
    }
    result: dict[str, Split] = {}
    audits: list[dict[str, Any]] = []
    dimension_attributes = {
        "time_block_heldout": "time_block",
        "source_heldout": "source",
        "goal_heldout": "goal",
        "junction_heldout": "junction",
        "congestion_heldout": "congestion",
        "fault_heldout": "fault",
        "decision_motif_heldout": "motif",
    }
    for seed in SPLIT_SEEDS:
        for split_name in SPLIT_NAMES:
            heldout_values: set[str] = set()
            forced_test_components: set[int] = set()
            if split_name != "grouped_random":
                attribute = dimension_attributes[split_name]
                values = sorted({str(getattr(example, attribute)) for example in examples})
                if len(values) < 2:
                    raise PhaseIError(
                        f"{split_name}/seed={seed}: at least two observed values are required"
                    )
                selected = [
                    value
                    for value in values
                    if _stable_fraction(seed, split_name, "value", value) >= 0.8
                ]
                if not selected:
                    selected = [
                        max(values, key=lambda value: _stable_fraction(seed, split_name, value))
                    ]
                if len(selected) == len(values):
                    selected = selected[:-1]
                heldout_values.update(selected)
                for index, example in enumerate(examples):
                    if str(getattr(example, attribute)) in heldout_values:
                        forced_test_components.add(component_for_index[index])
            train: list[int] = []
            validation: list[int] = []
            test: list[int] = []
            for component_index, component in enumerate(components):
                if component_index in forced_test_components:
                    test.extend(component)
                    continue
                fraction = _stable_fraction(
                    seed,
                    split_name,
                    *(examples[index].semantic_fingerprint for index in component),
                )
                if fraction < 0.70:
                    train.extend(component)
                elif fraction < 0.85:
                    validation.extend(component)
                else:
                    test.extend(component)
            if split_name != "grouped_random":
                # The held-out dimension is the test authority; do not add
                # random test components that dilute the interpretation.
                movable = [
                    index
                    for index in test
                    if component_for_index[index] not in forced_test_components
                ]
                test = [
                    index
                    for index in test
                    if component_for_index[index] in forced_test_components
                ]
                validation.extend(movable)
            if not train or not validation or not test:
                raise PhaseIError(
                    f"{split_name}/seed={seed}: train/validation/test must all be non-empty"
                )
            split = Split(
                name=split_name,
                seed=seed,
                train_indices=tuple(sorted(train)),
                validation_indices=tuple(sorted(validation)),
                test_indices=tuple(sorted(test)),
                heldout_values=tuple(sorted(heldout_values)),
            )
            key = f"{split_name}:seed={seed}"
            result[key] = split
            audits.append(split_audit(dataset, split))
    return result, audits


def split_audit(dataset: PreparedDataset, split: Split) -> dict[str, Any]:
    examples = dataset.examples

    def values(indices: Sequence[int], attribute: str) -> set[str]:
        return {str(getattr(examples[index], attribute)) for index in indices}

    train_bags = values(split.train_indices, "bag_family")
    validation_bags = values(split.validation_indices, "bag_family")
    test_bags = values(split.test_indices, "bag_family")
    train_fingerprints = values(split.train_indices, "semantic_fingerprint")
    validation_fingerprints = values(split.validation_indices, "semantic_fingerprint")
    test_fingerprints = values(split.test_indices, "semantic_fingerprint")
    bag_overlap = len(
        (train_bags & validation_bags)
        | (train_bags & test_bags)
        | (validation_bags & test_bags)
    )
    fingerprint_overlap = len(
        (train_fingerprints & validation_fingerprints)
        | (train_fingerprints & test_fingerprints)
        | (validation_fingerprints & test_fingerprints)
    )
    return {
        "split": split.name,
        "seed": split.seed,
        "train_count": len(split.train_indices),
        "validation_count": len(split.validation_indices),
        "test_count": len(split.test_indices),
        "heldout_values": list(split.heldout_values),
        "bag_family_overlap": bag_overlap,
        "semantic_fingerprint_overlap": fingerprint_overlap,
        "train_hard_count": sum(
            bool(examples[index].hard_categories) for index in split.train_indices
        ),
        "validation_hard_count": sum(
            bool(examples[index].hard_categories) for index in split.validation_indices
        ),
        "test_hard_count": sum(
            bool(examples[index].hard_categories) for index in split.test_indices
        ),
        "status": PASS if bag_overlap == 0 and fingerprint_overlap == 0 else BLOCKED,
    }


def _rank_pairs(
    dataset: PreparedDataset,
    indices: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    rows: list[np.ndarray] = []
    weights: list[float] = []
    for index in indices:
        example = dataset.examples[index]
        if not example.rank_eligible:
            continue
        features = np.asarray(example.candidate_features, dtype=np.float64)
        positive = features[example.selected_index]
        for candidate_index, candidate in enumerate(features):
            if candidate_index == example.selected_index:
                continue
            rows.append(positive - candidate)
            weight = example.sample_weight
            if not example.candidate_allowed[candidate_index]:
                weight = min(4.0, weight + 0.5)
            weights.append(weight)
    if not rows:
        raise PhaseIError("rank split has no eligible pairwise examples")
    return np.stack(rows), np.asarray(weights, dtype=np.float64)


def fit_linear_ranker(
    dataset: PreparedDataset,
    train_indices: Sequence[int],
    *,
    seed: int,
    epochs: int = 120,
    learning_rate: float = 0.04,
) -> dict[str, Any]:
    """Fit a deterministic weighted pairwise logistic linear ranker."""

    if epochs <= 0 or learning_rate <= 0:
        raise PhaseIError("epochs and learning_rate must be positive")
    pairs, pair_weights = _rank_pairs(dataset, train_indices)
    # Ranking is translation-invariant: only candidate differences matter.
    # A zero centre and no learned intercept preserve that invariant exactly.
    mean = np.zeros(pairs.shape[1], dtype=np.float64)
    std = pairs.std(axis=0)
    std[std < 1e-9] = 1.0
    normalised = pairs / std
    weights = np.zeros(normalised.shape[1], dtype=np.float64)
    order = list(range(len(normalised)))
    rng = random.Random(seed)
    for epoch in range(epochs):
        rng.shuffle(order)
        step = learning_rate / math.sqrt(1.0 + epoch)
        for index in order:
            vector = normalised[index]
            margin = float(np.dot(weights, vector))
            margin = max(-30.0, min(30.0, margin))
            gradient_scale = -pair_weights[index] / (1.0 + math.exp(margin))
            weights -= step * (gradient_scale * vector + 1e-4 * weights)
    # Candidate vectors are normalised with the same affine transform used for
    # pair differences.  Higher scores are preferred.
    return {
        "feature_names": list(dataset.feature_names),
        "normalisation": {"mean": mean.tolist(), "std": std.tolist()},
        "weights": weights.tolist(),
        "bias": 0.0,
        "score_semantics": "higher_is_preferred",
        "training_seed": seed,
        "epochs": epochs,
        "learning_rate": learning_rate,
    }


def _scores(model: Mapping[str, Any], example: Example) -> np.ndarray:
    features = np.asarray(example.candidate_features, dtype=np.float64)
    mean = np.asarray(model["normalisation"]["mean"], dtype=np.float64)
    std = np.asarray(model["normalisation"]["std"], dtype=np.float64)
    weights = np.asarray(model["weights"], dtype=np.float64)
    return ((features - mean) / std) @ weights + float(model["bias"])


def evaluate_ranker(
    dataset: PreparedDataset,
    model: Mapping[str, Any],
    indices: Sequence[int],
) -> dict[str, Any]:
    eligible = [index for index in indices if dataset.examples[index].rank_eligible]
    if not eligible:
        raise PhaseIError("evaluation split has no rank-eligible examples")
    top1 = 0
    top2 = 0
    pair_correct = 0
    pair_total = 0
    confidence_rows: list[tuple[float, int]] = []
    hard_top1 = 0
    hard_total = 0
    for index in eligible:
        example = dataset.examples[index]
        scores = _scores(model, example)
        order = sorted(
            range(len(scores)),
            key=lambda candidate: (-float(scores[candidate]), example.candidate_nodes[candidate]),
        )
        correct = int(order[0] == example.selected_index)
        top1 += correct
        top2 += int(example.selected_index in order[:2])
        if example.hard_categories:
            hard_total += 1
            hard_top1 += correct
        for candidate in range(len(scores)):
            if candidate == example.selected_index:
                continue
            pair_total += 1
            pair_correct += int(scores[example.selected_index] > scores[candidate])
        shifted = scores - float(np.max(scores))
        probabilities = np.exp(np.clip(shifted, -30.0, 0.0))
        probabilities /= probabilities.sum()
        confidence_rows.append((float(probabilities[order[0]]), correct))
    ece = 0.0
    for lower in np.linspace(0.0, 0.9, 10):
        upper = lower + 0.1
        bucket = [
            (confidence, correct)
            for confidence, correct in confidence_rows
            if lower <= confidence < upper or (upper >= 1.0 and confidence == 1.0)
        ]
        if bucket:
            mean_confidence = sum(value[0] for value in bucket) / len(bucket)
            mean_correct = sum(value[1] for value in bucket) / len(bucket)
            ece += len(bucket) / len(confidence_rows) * abs(mean_confidence - mean_correct)
    high_confidence = [correct for confidence, correct in confidence_rows if confidence >= 0.90]
    high_wrong = (
        sum(not bool(correct) for correct in high_confidence) / len(high_confidence)
        if high_confidence
        else 0.0
    )
    return {
        "eligible_decisions": len(eligible),
        "candidate_recall": 1.0,
        "top1": top1 / len(eligible),
        "top2": top2 / len(eligible),
        "pairwise_accuracy": pair_correct / pair_total if pair_total else 1.0,
        "ece": ece,
        "high_confidence_decision_count": len(high_confidence),
        "high_confidence_wrong_rate": high_wrong,
        "hard_top1": hard_top1 / hard_total if hard_total else None,
        "hard_decision_count": hard_total,
    }


def offline_metrics_pass(metrics: Mapping[str, Any]) -> bool:
    return (
        float(metrics["candidate_recall"]) == 1.0
        and float(metrics["top1"]) >= 0.50
        and float(metrics["pairwise_accuracy"]) >= 0.55
        and float(metrics["ece"]) <= 0.15
        and float(metrics["high_confidence_wrong_rate"]) <= 0.02
    )


def _project_dataset(
    dataset: PreparedDataset,
    keep_names: Sequence[str],
) -> PreparedDataset:
    keep = tuple(keep_names)
    if not keep:
        raise PhaseIError("feature ablation cannot remove every feature")
    positions = tuple(dataset.feature_names.index(name) for name in keep)
    projected_examples = tuple(
        replace(
            example,
            candidate_features=tuple(
                tuple(candidate[position] for position in positions)
                for candidate in example.candidate_features
            ),
        )
        for example in dataset.examples
    )
    digest_value = {
        "parent_dataset_sha256": dataset.dataset_sha256,
        "feature_names": keep,
    }
    return PreparedDataset(
        feature_names=keep,
        examples=projected_examples,
        dataset_sha256=hashlib.sha256(_canonical_bytes(digest_value)).hexdigest(),
        trace_sha256=dataset.trace_sha256,
        outcome_sha256=dataset.outcome_sha256,
        lineage_sha256=dataset.lineage_sha256,
    )


def feature_ablation_audit(
    dataset: PreparedDataset,
    split: Split,
    *,
    epochs: int,
    learning_rate: float,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Execute bounded diagnostics; ablations never become runtime candidates."""

    blockers: list[str] = []
    rows: list[dict[str, Any]] = []
    groups: dict[str, set[str]] = {
        "without_credit_features": {
            name for name in dataset.feature_names if name.startswith("first_edge_credit_")
        },
        "without_goal_conditioned_pressure": {
            name
            for name in dataset.feature_names
            if name
            in {
                "current_goal_queue_length",
                "target_goal_queue_length",
                "target_goal_scheduled_incoming",
                "current_goal_max_wait",
                "goal_conditioned_differential",
                "estimated_service_rate",
                "service_weighted_pressure",
            }
        },
        "without_fault_features": {
            name
            for name in dataset.feature_names
            if name in {"advertised_fault", "fault_message_age_seconds"}
        },
        "without_pibt_ownership_features": {
            name for name in dataset.feature_names if name.startswith("pibt_")
        },
    }
    rows.append(
        {
            "ablation": "all_legal_local_features",
            "status": PASS,
            "removed_features": [],
            "blocker": "",
        }
    )
    absolute_ids = [
        name
        for name in dataset.feature_names
        if "node_id" in name.lower() or name.lower() == "next_node"
    ]
    rows.append(
        {
            "ablation": "without_absolute_node_ids",
            "status": PASS if not absolute_ids else BLOCKED,
            "removed_features": absolute_ids,
            "blocker": (
                "" if not absolute_ids else "absolute node ID reached the main feature vector"
            ),
        }
    )
    if absolute_ids:
        blockers.append("absolute node ID reached the main feature vector")
    for name, removed in groups.items():
        if not removed:
            rows.append(
                {
                    "ablation": name,
                    "status": "NOT_APPLICABLE_FEATURE_GROUP_ABSENT",
                    "removed_features": [],
                    "blocker": "",
                }
            )
            continue
        kept = [feature for feature in dataset.feature_names if feature not in removed]
        try:
            projected = _project_dataset(dataset, kept)
            model = fit_linear_ranker(
                projected,
                split.train_indices,
                seed=split.seed,
                epochs=epochs,
                learning_rate=learning_rate,
            )
            validation = evaluate_ranker(projected, model, split.validation_indices)
            test = evaluate_ranker(projected, model, split.test_indices)
        except PhaseIError as exc:
            blockers.append(f"{name}: {exc}")
            rows.append(
                {
                    "ablation": name,
                    "status": BLOCKED,
                    "removed_features": sorted(removed),
                    "blocker": str(exc),
                }
            )
            continue
        rows.append(
            {
                "ablation": name,
                "status": PASS,
                "removed_features": sorted(removed),
                "validation_top1": validation["top1"],
                "test_top1": test["top1"],
                "validation_pairwise_accuracy": validation["pairwise_accuracy"],
                "test_pairwise_accuracy": test["pairwise_accuracy"],
                "blocker": "",
            }
        )
    return rows, blockers


def train_and_validate(
    dataset: PreparedDataset,
    *,
    epochs: int,
    learning_rate: float,
) -> tuple[dict[str, Any] | None, dict[str, Any], list[str]]:
    """Run all multi-seed held-out gates, then refit one offline candidate."""

    blockers: list[str] = []
    try:
        splits, split_audits = build_splits(dataset)
    except PhaseIError as exc:
        return None, {"split_audit": [], "evaluations": []}, [str(exc)]
    if any(row["status"] != PASS for row in split_audits):
        blockers.append("one or more split leakage audits did not PASS")
    evaluations: list[dict[str, Any]] = []
    for key, split in sorted(splits.items()):
        try:
            model = fit_linear_ranker(
                dataset,
                split.train_indices,
                seed=split.seed,
                epochs=epochs,
                learning_rate=learning_rate,
            )
            validation = evaluate_ranker(dataset, model, split.validation_indices)
            test = evaluate_ranker(dataset, model, split.test_indices)
        except PhaseIError as exc:
            blockers.append(f"{key}: {exc}")
            continue
        passed = offline_metrics_pass(validation) and offline_metrics_pass(test)
        if not passed:
            blockers.append(f"{key}: offline validation/test thresholds did not PASS")
        evaluations.append(
            {
                "split": split.name,
                "seed": split.seed,
                "validation": validation,
                "test": test,
                "status": PASS if passed else BLOCKED,
            }
        )
    primary_split = splits[f"grouped_random:seed={SPLIT_SEEDS[0]}"]
    feature_ablation, ablation_blockers = feature_ablation_audit(
        dataset,
        primary_split,
        epochs=epochs,
        learning_rate=learning_rate,
    )
    blockers.extend(ablation_blockers)
    audit = {
        "split_audit": split_audits,
        "evaluations": evaluations,
        "feature_ablation": feature_ablation,
    }
    if blockers:
        return None, audit, sorted(set(blockers))
    all_indices = tuple(range(len(dataset.examples)))
    try:
        candidate = fit_linear_ranker(
            dataset,
            all_indices,
            seed=SPLIT_SEEDS[0],
            epochs=epochs,
            learning_rate=learning_rate,
        )
    except PhaseIError as exc:
        return None, audit, [f"final refit: {exc}"]
    return candidate, audit, []


def _csv_bytes(rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> bytes:
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name, "") for name in fieldnames})
    return output.getvalue().encode("utf-8")


def _write_plan_tables(
    root: Path,
    *,
    status: str,
    blockers: Sequence[str],
    training_audit: Mapping[str, Any],
) -> None:
    reason = "; ".join(blockers) if blockers else (
        "training not explicitly authorised"
        if status == READY
        else "closed-loop validation has not run"
    )
    model_rows = [
        {
            "model": model,
            "implementation_status": (
                "IMPLEMENTED_NOT_RUN" if model in IMPLEMENTED_MODELS else "PROTOCOL_ONLY"
            ),
            "training_status": (
                PASS
                if status == OFFLINE_PASS and model == "v3_linear_ranker"
                else status
                if model == "v3_linear_ranker"
                else BLOCKED
            ),
            "offline_status": (
                PASS
                if status == OFFLINE_PASS and model == "v3_linear_ranker"
                else BLOCKED
            ),
            "closed_loop_status": BLOCKED,
            "runtime_eligible": False,
            "blocker": reason,
        }
        for model in ALLOWED_MODELS
    ]
    _atomic_write(
        root / DEFAULT_MODEL_AB,
        _csv_bytes(
            model_rows,
            (
                "model",
                "implementation_status",
                "training_status",
                "offline_status",
                "closed_loop_status",
                "runtime_eligible",
                "blocker",
            ),
        ),
    )
    raw_ablation = training_audit.get("feature_ablation")
    if isinstance(raw_ablation, list) and raw_ablation:
        ablation_rows = [
            {
                "ablation": str(row.get("ablation") or ""),
                "status": str(row.get("status") or BLOCKED),
                "runtime_eligible": False,
                "removed_features": json.dumps(
                    row.get("removed_features") or [], sort_keys=True
                ),
                "validation_top1": row.get("validation_top1", ""),
                "test_top1": row.get("test_top1", ""),
                "validation_pairwise_accuracy": row.get(
                    "validation_pairwise_accuracy", ""
                ),
                "test_pairwise_accuracy": row.get("test_pairwise_accuracy", ""),
                "blocker": str(row.get("blocker") or reason),
            }
            for row in raw_ablation
            if isinstance(row, Mapping)
        ]
    else:
        ablation_rows = [
            {
                "ablation": name,
                "status": BLOCKED,
                "runtime_eligible": False,
                "removed_features": "[]",
                "validation_top1": "",
                "test_top1": "",
                "validation_pairwise_accuracy": "",
                "test_pairwise_accuracy": "",
                "blocker": reason,
            }
            for name in (
                "all_legal_local_features",
                "without_absolute_node_ids",
                "without_credit_features",
                "without_goal_conditioned_pressure",
                "without_fault_features",
                "without_pibt_ownership_features",
            )
        ]
    _atomic_write(
        root / DEFAULT_FEATURE_ABLATION,
        _csv_bytes(
            ablation_rows,
            (
                "ablation",
                "status",
                "runtime_eligible",
                "removed_features",
                "validation_top1",
                "test_top1",
                "validation_pairwise_accuracy",
                "test_pairwise_accuracy",
                "blocker",
            ),
        ),
    )


def _report(status: str, blockers: Sequence[str], audit: Mapping[str, Any]) -> str:
    blocker_lines = [f"- {value}" for value in blockers] or ["- None."]
    return "\n".join(
        [
            "# G4IRSF12-I v3 Training Report",
            "",
            f"Status: `{status}`.",
            "",
            "No model is considered a runtime result in this report. Training is allowed only "
            "after every hash-bound Phase-I prerequisite passes.",
            "",
            "## Current blockers",
            "",
            *blocker_lines,
            "",
            "## Data preparation audit",
            "",
            f"- Decision rows: `{audit.get('trace_rows', 0)}`",
            f"- Outcome rows: `{audit.get('outcome_rows', 0)}`",
            f"- Rank-eligible rows: `{audit.get('rank_eligible_rows', 0)}`",
            f"- Hard rows: `{audit.get('hard_rows', 0)}`",
            f"- Easy rows: `{audit.get('easy_rows', 0)}`",
            "",
            "Failure, loop, and dead-end actions remain risk evidence. They are never inverted "
            "into an unobserved correct next edge. Teacher suffixes, future schedules, post-hoc "
            "success, and absolute node IDs are not legal model inputs.",
            "",
            "A future offline candidate must pass every seed and held-out split. Even then it "
            "remains `CLOSED_LOOP_REQUIRED` and cannot be activated by this tool.",
            "",
        ]
    )


def _closed_loop_report(status: str, candidate: Mapping[str, Any] | None) -> str:
    candidate_sha = str(candidate.get("candidate_sha256") or "") if candidate else ""
    return "\n".join(
        [
            "# G4IRSF12-I v3 Closed-Loop Report",
            "",
            f"Status: `{status}`.",
            "",
            f"Candidate SHA-256: `{candidate_sha or 'NONE'}`.",
            "",
            "No closed-loop evaluation has been substituted by offline accuracy. Runtime "
            "eligibility requires a separate manifest bound to this exact candidate, at least "
            "five deterministic repeats, complete 28,506 bags / 43,603 segments, zero conflicts, "
            "zero unresolved deadlocks, zero runtime A*/CIE, zero global reservation scans, no "
            "future-route reads, no time/event limit, and the matched original-entry denominator.",
            "",
            "G4J remains closed.",
            "",
        ]
    )


def _status_payload(
    *,
    root: Path,
    status: str,
    blockers: Sequence[str],
    gate_statuses: Mapping[str, str],
    audit: Mapping[str, Any],
    protocol_descriptor: Mapping[str, Any],
    source_manifest: Path,
    candidate: Mapping[str, Any] | None,
    command: str,
) -> dict[str, Any]:
    return {
        "schema": STATUS_SCHEMA,
        "status": status,
        "trained": candidate is not None,
        "runtime_eligible": False,
        "G4J_status": "CLOSED",
        "required_gates": list(REQUIRED_GATES),
        "gate_statuses": dict(gate_statuses),
        "blockers": sorted(set(map(str, blockers))),
        "protocol": dict(protocol_descriptor),
        "source_manifest": {
            "path": _relative(root, source_manifest)
            if source_manifest.resolve().is_relative_to(root.resolve())
            else str(source_manifest.resolve()),
            "sha256": semantic_sha256(source_manifest) if source_manifest.is_file() else "",
            "hash_semantics": SEMANTIC_TEXT_HASH,
        },
        "data_audit": dict(audit),
        "candidate_model": dict(candidate or {}),
        "reproduce_command": command,
        "claim_boundary": (
            "No runtime policy is published. A missing/partial gate, data mismatch, split "
            "leakage, offline failure, or absent closed-loop result fails closed."
        ),
    }


def _command(args: argparse.Namespace) -> str:
    parts = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--root",
        str(args.root),
        "--gate-manifest",
        str(args.gate_manifest),
        "--source-manifest",
        str(args.source_manifest),
        "--epochs",
        str(args.epochs),
        "--learning-rate",
        str(args.learning_rate),
    ]
    if args.authorize_training:
        parts.append("--authorize-training")
    return " ".join(json.dumps(part) for part in parts)


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    root = args.root.resolve()
    protocol_path = (root / DEFAULT_PROTOCOL).resolve()
    schema_path = (root / DEFAULT_SCHEMA).resolve()
    gate_path = (
        args.gate_manifest.resolve()
        if args.gate_manifest.is_absolute()
        else (root / args.gate_manifest).resolve()
    )
    source_path = (
        args.source_manifest.resolve()
        if args.source_manifest.is_absolute()
        else (root / args.source_manifest).resolve()
    )
    for path, label in (
        (protocol_path, "protocol"),
        (schema_path, "schema"),
        (gate_path, "gate manifest"),
        (source_path, "source manifest"),
    ):
        if not path.is_relative_to(root):
            raise PhaseIError(f"{label} escapes repository root: {path}")

    _write_json(protocol_path, protocol_manifest())
    _write_json(schema_path, dataset_schema())
    protocol_binding = descriptor(root, protocol_path)

    blockers = verify_protected_inputs(root)
    gate_statuses, gate_blockers = validate_gate_manifest(root, gate_path)
    blockers.extend(gate_blockers)
    dataset, data_audit, data_blockers = prepare_dataset(root, source_path)
    blockers.extend(data_blockers)

    candidate_descriptor: dict[str, Any] | None = None
    training_audit: dict[str, Any] = {}
    if blockers:
        status = BLOCKED
        exit_code = 2
    elif not args.authorize_training:
        status = READY
        exit_code = 0
    else:
        assert dataset is not None
        candidate_model, training_audit, training_blockers = train_and_validate(
            dataset,
            epochs=args.epochs,
            learning_rate=args.learning_rate,
        )
        blockers.extend(training_blockers)
        if candidate_model is None or blockers:
            status = BLOCKED
            exit_code = 2
        else:
            candidate_payload = {
                "schema": MODEL_SCHEMA,
                "status": OFFLINE_PASS,
                "model_name": "v3_linear_ranker",
                "runtime_eligible": False,
                "G4J_status": "CLOSED",
                "protected_inputs": protocol_manifest()["protected_inputs"],
                "protocol_sha256": protocol_binding["sha256"],
                "gate_manifest_sha256": semantic_sha256(gate_path),
                "source_manifest_sha256": semantic_sha256(source_path),
                "dataset_sha256": dataset.dataset_sha256,
                "trace_sha256": dataset.trace_sha256,
                "outcome_sha256": dataset.outcome_sha256,
                "lineage_sha256": dataset.lineage_sha256,
                "model": candidate_model,
                "validation": training_audit,
                "publication": {
                    "candidate_only": True,
                    "active_pointer_written": False,
                    "closed_loop_required": True,
                },
            }
            candidate_bytes = _json_bytes(candidate_payload)
            candidate_sha = hashlib.sha256(
                _normalise_text_bytes(candidate_bytes)
            ).hexdigest()
            candidate_path = root / DEFAULT_MODEL_DIR / f"g4irsf12_v3_{candidate_sha[:16]}.json"
            if candidate_path.exists() and candidate_path.read_bytes() != candidate_bytes:
                raise PhaseIError(f"immutable candidate collision: {candidate_path}")
            if not candidate_path.exists():
                _atomic_write(candidate_path, candidate_bytes)
            candidate_descriptor = descriptor(root, candidate_path)
            candidate_descriptor["candidate_sha256"] = candidate_sha
            candidate_descriptor["runtime_eligible"] = False
            status = OFFLINE_PASS
            exit_code = 0

    combined_audit = dict(data_audit)
    if training_audit:
        combined_audit["training_validation"] = training_audit
    status_payload = _status_payload(
        root=root,
        status=status,
        blockers=blockers,
        gate_statuses=gate_statuses,
        audit=combined_audit,
        protocol_descriptor=protocol_binding,
        source_manifest=source_path,
        candidate=candidate_descriptor,
        command=_command(args),
    )
    _write_json(root / DEFAULT_STATUS, status_payload)
    dataset_manifest = {
        "schema": DATASET_SCHEMA,
        "status": status,
        "weights_initialised": candidate_descriptor is not None,
        "runtime_eligible": False,
        "protocol": protocol_binding,
        "source_manifest": status_payload["source_manifest"],
        "protected_inputs": protocol_manifest()["protected_inputs"],
        "data_audit": combined_audit,
        "blockers": status_payload["blockers"],
        "claim_boundary": status_payload["claim_boundary"],
    }
    _write_json(root / DEFAULT_DATASET_MANIFEST, dataset_manifest)
    _atomic_write(
        root / DEFAULT_TRAINING_REPORT,
        _report(status, status_payload["blockers"], combined_audit).encode("utf-8"),
    )
    _atomic_write(
        root / DEFAULT_CLOSED_LOOP_REPORT,
        _closed_loop_report(BLOCKED, candidate_descriptor).encode("utf-8"),
    )
    _write_plan_tables(
        root,
        status=status,
        blockers=status_payload["blockers"],
        training_audit=training_audit,
    )
    return exit_code, status_payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--gate-manifest", type=Path, default=DEFAULT_GATE_MANIFEST)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--authorize-training", action="store_true")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--learning-rate", type=float, default=0.04)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    code, payload = run(args)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
