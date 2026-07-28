#!/usr/bin/env python3
"""Fail-closed validator for Stage-14D production E4 evidence.

This validator deliberately does not import the generator.  It independently
reconstructs protected-input identity, source identity, CSV schemas and row
self-hashes, typed lifecycle projections, runtime hard gates, topology/slot
constraints, same-input M0--M6 coverage, and M7--M9 fail-closed evidence.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from scripts.eval import g4irsf12_reproducible_harness as g12  # noqa: E402
from scripts.eval.g4irsf12_size_ladder import (  # noqa: E402
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_RAW_SHA256,
    CANONICAL_MAP_SEMANTIC_SHA256,
    CANONICAL_SOURCE_PATH,
    CANONICAL_SOURCE_RAW_SHA256,
    CANONICAL_SOURCE_SEMANTIC_SHA256,
)


SCHEMA = "czr005.g4irsf14.merge_grant_protocol.v2"
STATUS = "PASS_STAGE_D_PRODUCTION_E4_MECHANISM_EVIDENCE"
PROMOTION_STATUS = "NOT_EVALUATED_STAGE_D_MECHANISM_ONLY"
PREFIX_SEGMENTS = 144
ONLINE_RULES = tuple(f"M{index}" for index in range(7))
NEGATIVE_RULES = ("M7", "M8", "M9")
CONTROL_RULE = "M0"
RUNTIME_REPEAT_COUNT = 2
FROZEN_MODEL_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)

GENERATOR_PATH = Path("scripts/eval/g4irsf14_merge_grant_protocol.py")
VALIDATOR_PATH = Path("scripts/validate_g4irsf14_merge_grant_artifacts.py")
REPORT_PATH = Path("outputs/reports/g4irsf14_merge_grant_protocol.md")
LIFECYCLE_PATH = Path(
    "outputs/tables/g4irsf14_merge_grant_lifecycle.csv"
)
RULE_AB_PATH = Path("outputs/tables/g4irsf14_merge_rule_ab.csv")
CONFIG_PATH = Path("artifacts/configs/g4irsf14_merge_grant_protocol.json")

SOURCE_PATHS = (
    GENERATOR_PATH,
    VALIDATOR_PATH,
    Path("CMakeLists.txt"),
    Path("src/czr005/cpp_backend.py"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
    Path("cpp/ics_core/runtime/destination_merge_grant.hpp"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("artifacts/models/g4e_risk_calibrated_policy.json"),
)

FROZEN_CONTROLS: Mapping[str, Any] = {
    "event_semantics": "E4_batch_plus_destination_merge_request",
    "resource_semantics": "R3_java_node_window_compatible",
    "scorer_mode": "S1_frozen_g4e_legal_local_adapter",
    "pibt_mode": "P2",
    "pibt_max_depth": 2,
    "priority_mode": "Q0",
    "framework_mode": "event_loop_one_step",
    "pibt_preference_mode": "current",
    "pibt_regret_prior_records": [],
    "admission_mode": "off",
    "pressure_mode": "off",
    "enable_source_admission": False,
    "enable_backpressure": False,
    "enable_pibt_lite": False,
    "enable_deadlock_escape": True,
    "enable_fault_policy": True,
    "enable_opportunity_telemetry": False,
    "opportunity_trace_limit": 0,
    "scale": 1.0,
    "reservation_depth": 1,
    "local_queue_capacity": 32,
    "pibt_max_ready_bags": 8,
    "pibt_max_local_resources": 32,
    "pibt_max_candidates_per_bag": 8,
    "selective_credit_contention_threshold": 1,
    "entry_headway_seconds": 0.001,
    "credit_validity_seconds": 1.0,
    "credit_snapshot_max_age_seconds": 1.0,
    "credit_capacity_per_edge": 1,
    "credit_lifecycle_limit": 512,
    "merge_grant_max_pending_requests": 256,
    "merge_grant_lifecycle_limit": 8192,
    "max_events": 20_000_000,
    "max_simulation_time": -1.0,
    "history_limit": 8,
    "trace_limit": 0,
    "event_trace_limit": 0,
}

BOUNDARY = {
    "reservation_depth": 1,
    "directed_edges_per_grant": 1,
    "destination_slots_per_grant": 1,
    "reads_future_route": False,
    "reads_global_task_list": False,
    "reads_global_reservation_table": False,
    "reads_all_airport_queues": False,
    "uses_teacher_path": False,
    "stores_post_hoc_outcome_in_request": False,
    "runtime_astar_allowed": False,
    "fault_windows": [],
    "scale": 1.0,
}

LIFECYCLE_RUNTIME_FIELDS = (
    "time",
    "request_id",
    "grant_id",
    "lineage",
    "request_generation",
    "junction_queue_generation",
    "runtime_bag_id",
    "task_id",
    "segment_id",
    "upstream_node",
    "destination_node",
    "edge_from_node",
    "edge_to_node",
    "request_time",
    "fifo_request_time",
    "earliest_edge_entry",
    "exact_edge_travel_seconds",
    "projected_arrival",
    "goal",
    "route_score",
    "static_remaining",
    "destination_service_seconds",
    "downstream_queue_pressure",
    "deadline_slack",
    "wait_age",
    "task_class_code",
    "task_class",
    "storage_leg",
    "source_release_age",
    "local_queue_age",
    "enqueue_sequence",
    "request_expiry",
    "slot_start",
    "slot_end",
    "issue_time",
    "grant_expiry",
    "calendar_generation",
    "fault_generation",
    "advertised_fault_generation",
    "observed_claimed_request_generation",
    "observed_claimed_junction_queue_generation",
    "observed_claimed_calendar_generation",
    "observed_claimed_owner_runtime_bag_id",
    "observed_claimed_edge_from_node",
    "observed_claimed_edge_to_node",
    "observed_claimed_destination_node",
    "observed_event_owner_runtime_bag_id",
    "observed_event_edge_from_node",
    "observed_event_edge_to_node",
    "observed_event_destination_node",
    "observed_junction_queue_generation",
    "observed_calendar_generation",
    "observed_physical_fault_generation",
    "observed_advertised_fault_generation",
    "observed_physical_fault_active",
    "observed_exact_calendar_reservation_present",
    "state",
    "reason",
)

REQUEST_IMMUTABLE_FIELDS = (
    "request_id",
    "lineage",
    "request_generation",
    "junction_queue_generation",
    "runtime_bag_id",
    "task_id",
    "segment_id",
    "upstream_node",
    "destination_node",
    "edge_from_node",
    "edge_to_node",
    "request_time",
    "fifo_request_time",
    "earliest_edge_entry",
    "exact_edge_travel_seconds",
    "projected_arrival",
    "goal",
    "route_score",
    "static_remaining",
    "destination_service_seconds",
    "downstream_queue_pressure",
    "deadline_slack",
    "task_class_code",
    "task_class",
    "storage_leg",
    "source_release_age",
    "local_queue_age",
    "enqueue_sequence",
    "request_expiry",
    "fault_generation",
    "advertised_fault_generation",
)
GRANT_IMMUTABLE_FIELDS = (
    "grant_id",
    "slot_start",
    "slot_end",
    "issue_time",
    "grant_expiry",
    "calendar_generation",
)
LEGAL_LIFECYCLE_SUCCESSORS = {
    "REQUESTED": {
        "ISSUED",
        "EXPIRED",
        "REVOKED_FAULT",
        "REVOKED_STALE_STATE",
        "REVOKED_REPLAN_CURRENT_EDGE",
        "ROLLED_BACK",
    },
    "ISSUED": {
        "PREPARED",
        "EXPIRED",
        "REVOKED_FAULT",
        "REVOKED_STALE_STATE",
        "REVOKED_REPLAN_CURRENT_EDGE",
        "ROLLED_BACK",
    },
    "PREPARED": {
        "COMMITTED",
        "EXPIRED",
        "REVOKED_FAULT",
        "REVOKED_STALE_STATE",
        "REVOKED_REPLAN_CURRENT_EDGE",
        "ROLLED_BACK",
    },
    "COMMITTED": {
        "CONSUMED",
        "EXPIRED",
        "REVOKED_FAULT",
        "REVOKED_STALE_STATE",
        "REVOKED_REPLAN_CURRENT_EDGE",
        "ROLLED_BACK",
    },
}

LIFECYCLE_CONTEXT_FIELDS = (
    "schema",
    "rule",
    "run_id",
    "transition_index",
    "input_selection_sha256",
    "map_raw_sha256",
    "map_semantic_sha256",
    "task_raw_sha256",
    "source_bundle_sha256",
    "binary_sha256",
)
LIFECYCLE_COLUMNS = (
    *LIFECYCLE_CONTEXT_FIELDS,
    *LIFECYCLE_RUNTIME_FIELDS,
    "row_sha256",
)

RULE_AB_COLUMNS = (
    "schema",
    "rule",
    "control_rule",
    "online_allowed",
    "execution_status",
    "rejection_type",
    "rejection_message",
    "run_id",
    "segment_count",
    "raw_bag_count",
    "input_selection_sha256",
    "map_raw_sha256",
    "map_semantic_sha256",
    "task_raw_sha256",
    "source_bundle_sha256",
    "binary_sha256",
    "completed_count",
    "failed_count",
    "unresolved_deadlock_count",
    "end_time",
    "mean_completion_seconds",
    "p95_completion_seconds",
    "max_completion_seconds",
    "mean_grant_wait_seconds",
    "max_grant_wait_seconds",
    "grant_slot_busy_seconds",
    "grant_slot_idle_seconds",
    "merge_throughput_per_second",
    "incoming_edge_fairness_jain",
    "deadline_miss_count",
    "deadline_miss_rate",
    "merge_request_count",
    "merge_committed_count",
    "merge_consumed_count",
    "merge_request_expired_count",
    "merge_grant_expired_count",
    "merge_revoked_count",
    "merge_peak_pending_requests",
    "merge_peak_active_unconsumed",
    "merge_contended_loser_retry_count",
    "lifecycle_transition_count",
    "lifecycle_stored_count",
    "lifecycle_dropped_count",
    "repeat_count",
    "repeat_deterministic_sha256",
    "repeat_determinism_pass",
    "mean_completion_delta_vs_m0_seconds",
    "p95_completion_delta_vs_m0_seconds",
    "end_time_delta_vs_m0_seconds",
    "grant_wait_delta_vs_m0_seconds",
    "committed_order_sha256",
    "bag_projection_sha256",
    "lifecycle_projection_sha256",
    "deterministic_result_sha256",
    "hard_gate_pass",
    "hard_gate_failures",
    "performance_gain_claimed",
    "promotion_status",
    "row_sha256",
)

LIFECYCLE_INTEGER_FIELDS = {
    "request_id",
    "grant_id",
    "lineage",
    "request_generation",
    "junction_queue_generation",
    "runtime_bag_id",
    "task_id",
    "upstream_node",
    "destination_node",
    "edge_from_node",
    "edge_to_node",
    "goal",
    "downstream_queue_pressure",
    "task_class_code",
    "task_class",
    "enqueue_sequence",
    "calendar_generation",
    "fault_generation",
    "advertised_fault_generation",
    "observed_claimed_request_generation",
    "observed_claimed_junction_queue_generation",
    "observed_claimed_calendar_generation",
    "observed_claimed_owner_runtime_bag_id",
    "observed_claimed_edge_from_node",
    "observed_claimed_edge_to_node",
    "observed_claimed_destination_node",
    "observed_event_owner_runtime_bag_id",
    "observed_event_edge_from_node",
    "observed_event_edge_to_node",
    "observed_event_destination_node",
    "observed_junction_queue_generation",
    "observed_calendar_generation",
    "observed_physical_fault_generation",
    "observed_advertised_fault_generation",
}
LIFECYCLE_BOOLEAN_FIELDS = {
    "storage_leg",
    "observed_physical_fault_active",
    "observed_exact_calendar_reservation_present",
}
LIFECYCLE_STRING_FIELDS = {"segment_id", "state", "reason"}
LIFECYCLE_FLOAT_FIELDS = (
    set(LIFECYCLE_RUNTIME_FIELDS)
    - LIFECYCLE_INTEGER_FIELDS
    - LIFECYCLE_BOOLEAN_FIELDS
    - LIFECYCLE_STRING_FIELDS
)

HARD_GATE_NAMES = {
    "complete",
    "conflict_free",
    "unsafe_zero",
    "deadlock_resolved",
    "astar_zero",
    "global_scan_zero",
    "future_route_zero",
    "teacher_input_zero",
    "reservation_depth_one",
    "no_event_or_time_limit",
    "no_stale_arbitration",
    "zero_artificial_delay",
    "lifecycle_complete",
    "protocol_integrity",
}


class ProtocolValidationError(RuntimeError):
    """Raised for any evidence identity or semantic mismatch."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolValidationError(message)


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


def file_sha256(path: Path) -> str:
    require(path.is_file(), f"missing hash-bound file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_text_sha256(path: Path) -> str:
    require(path.is_file(), f"missing semantic source file: {path}")
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ProtocolValidationError(
            f"source file is not strict UTF-8: {path}"
        ) from exc
    normalized = text.replace("\r\n", "\n")
    require(
        "\r" not in normalized,
        f"source file contains unsupported lone CR: {path}",
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _expected_runtime_echo(rule: str) -> dict[str, dict[str, Any]]:
    return {
        "summary": {
            "resource_semantics_id": FROZEN_CONTROLS[
                "resource_semantics"
            ],
            "resource_semantics_echo": FROZEN_CONTROLS[
                "resource_semantics"
            ],
            "pressure_mode": "C0_off",
            "pressure_mode_echo": FROZEN_CONTROLS["pressure_mode"],
            "admission_mode": FROZEN_CONTROLS["admission_mode"],
            "admission_mode_echo": FROZEN_CONTROLS["admission_mode"],
            "source_admission_enabled": False,
            "framework_mode": FROZEN_CONTROLS["framework_mode"],
            "framework_mode_echo": FROZEN_CONTROLS["framework_mode"],
            "pibt_mode": FROZEN_CONTROLS["pibt_mode"],
            "pibt_mode_echo": FROZEN_CONTROLS["pibt_mode"],
            "pibt_max_depth": FROZEN_CONTROLS["pibt_max_depth"],
            "pibt_preference_mode": FROZEN_CONTROLS[
                "pibt_preference_mode"
            ],
            "pibt_preference_mode_echo": FROZEN_CONTROLS[
                "pibt_preference_mode"
            ],
            "pibt_regret_prior_record_count": 0,
            "priority_mode": FROZEN_CONTROLS["priority_mode"],
            "priority_mode_echo": FROZEN_CONTROLS["priority_mode"],
            "scorer_mode": FROZEN_CONTROLS["scorer_mode"],
            "scorer_mode_echo": FROZEN_CONTROLS["scorer_mode"],
            "scorer_model_sha256": FROZEN_MODEL_SHA256,
            "legacy_pibt_lite_enabled": False,
            "fault_policy_enabled": True,
            "fault_event_count": 0,
            "repair_event_count": 0,
            "declared_max_events": FROZEN_CONTROLS["max_events"],
            "declared_max_simulation_time": FROZEN_CONTROLS[
                "max_simulation_time"
            ],
            "local_queue_capacity": FROZEN_CONTROLS[
                "local_queue_capacity"
            ],
            "pibt_max_ready_bags": FROZEN_CONTROLS[
                "pibt_max_ready_bags"
            ],
            "pibt_max_local_resources": FROZEN_CONTROLS[
                "pibt_max_local_resources"
            ],
            "pibt_max_candidates_per_bag": FROZEN_CONTROLS[
                "pibt_max_candidates_per_bag"
            ],
            "event_trace_limit": FROZEN_CONTROLS["event_trace_limit"],
            "opportunity_telemetry_enabled": False,
            "event_semantics": FROZEN_CONTROLS["event_semantics"],
            "event_semantics_echo": FROZEN_CONTROLS["event_semantics"],
            "merge_grant_rule": rule,
            "merge_grant_rule_echo": rule,
            "merge_grant_max_pending_requests": FROZEN_CONTROLS[
                "merge_grant_max_pending_requests"
            ],
            "merge_grant_lifecycle_limit": FROZEN_CONTROLS[
                "merge_grant_lifecycle_limit"
            ],
        },
        "trace_context": {
            "scale": FROZEN_CONTROLS["scale"],
            "reservation_depth": FROZEN_CONTROLS["reservation_depth"],
            "resource_semantics_id": FROZEN_CONTROLS[
                "resource_semantics"
            ],
            "resource_semantics_echo": FROZEN_CONTROLS[
                "resource_semantics"
            ],
            "pressure_mode": "C0_off",
            "pressure_mode_echo": FROZEN_CONTROLS["pressure_mode"],
            "admission_mode": FROZEN_CONTROLS["admission_mode"],
            "admission_mode_echo": FROZEN_CONTROLS["admission_mode"],
            "enable_source_admission": False,
            "framework_mode": FROZEN_CONTROLS["framework_mode"],
            "framework_mode_echo": FROZEN_CONTROLS["framework_mode"],
            "pibt_mode": FROZEN_CONTROLS["pibt_mode"],
            "pibt_mode_echo": FROZEN_CONTROLS["pibt_mode"],
            "pibt_max_depth": FROZEN_CONTROLS["pibt_max_depth"],
            "pibt_preference_mode": FROZEN_CONTROLS[
                "pibt_preference_mode"
            ],
            "pibt_preference_mode_echo": FROZEN_CONTROLS[
                "pibt_preference_mode"
            ],
            "pibt_regret_prior_record_count": 0,
            "priority_mode": FROZEN_CONTROLS["priority_mode"],
            "priority_mode_echo": FROZEN_CONTROLS["priority_mode"],
            "scorer_mode_echo": FROZEN_CONTROLS["scorer_mode"],
            "scorer_model_sha256": FROZEN_MODEL_SHA256,
            "enable_fault_policy": True,
            "event_trace_limit": FROZEN_CONTROLS["event_trace_limit"],
            "opportunity_telemetry_enabled": False,
            "event_semantics": FROZEN_CONTROLS["event_semantics"],
            "event_semantics_echo": FROZEN_CONTROLS["event_semantics"],
            "destination_merge_grant_enabled": True,
            "merge_grant_rule": rule,
            "merge_grant_rule_echo": rule,
            "merge_grant_max_pending_requests": FROZEN_CONTROLS[
                "merge_grant_max_pending_requests"
            ],
            "merge_grant_lifecycle_limit": FROZEN_CONTROLS[
                "merge_grant_lifecycle_limit"
            ],
            "local_queue_capacity": FROZEN_CONTROLS[
                "local_queue_capacity"
            ],
            "pibt_max_ready_bags": FROZEN_CONTROLS[
                "pibt_max_ready_bags"
            ],
            "pibt_max_local_resources": FROZEN_CONTROLS[
                "pibt_max_local_resources"
            ],
            "pibt_max_candidates_per_bag": FROZEN_CONTROLS[
                "pibt_max_candidates_per_bag"
            ],
        },
    }


def _read_json(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"missing JSON artifact: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProtocolValidationError(f"cannot decode {path}: {exc}") from exc
    require(isinstance(value, dict), f"{path} root must be an object")
    return value


def _read_csv(path: Path, columns: Sequence[str]) -> list[dict[str, str]]:
    require(path.is_file(), f"missing CSV artifact: {path}")
    try:
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            require(
                reader.fieldnames == list(columns),
                f"{path} columns drift",
            )
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ProtocolValidationError(f"cannot decode {path}: {exc}") from exc
    require(bool(rows), f"{path} is empty")
    require(
        all(set(row) == set(columns) for row in rows),
        f"{path} row field set drift",
    )
    return rows


def _int(value: str, label: str, *, minimum: int | None = None) -> int:
    require(value != "", f"{label} is empty")
    try:
        result = int(value)
    except ValueError as exc:
        raise ProtocolValidationError(f"{label} must be integer") from exc
    require(str(result) == value, f"{label} is not canonical integer text")
    if minimum is not None:
        require(result >= minimum, f"{label} is below {minimum}")
    return result


def _float(value: str, label: str) -> float:
    require(value != "", f"{label} is empty")
    try:
        result = float(value)
    except ValueError as exc:
        raise ProtocolValidationError(f"{label} must be numeric") from exc
    require(math.isfinite(result), f"{label} must be finite")
    return result


def _bool_text(value: str, label: str) -> bool:
    require(value in {"true", "false"}, f"{label} must be true/false")
    return value == "true"


def _verify_row_self_hash(row: Mapping[str, str], label: str) -> None:
    declared = row.get("row_sha256")
    require(_is_sha256(declared), f"{label} row_sha256 malformed")
    projection = dict(row)
    projection.pop("row_sha256", None)
    require(
        canonical_sha256(projection) == declared,
        f"{label} row self-hash mismatch",
    )


def _typed_lifecycle_row(row: Mapping[str, str]) -> dict[str, Any]:
    typed: dict[str, Any] = {}
    for field in LIFECYCLE_RUNTIME_FIELDS:
        value = row[field]
        if field in LIFECYCLE_INTEGER_FIELDS:
            typed[field] = _int(value, field)
        elif field in LIFECYCLE_BOOLEAN_FIELDS:
            typed[field] = _bool_text(value, field)
        elif field in LIFECYCLE_STRING_FIELDS:
            require(value != "", f"{field} is empty")
            typed[field] = value
        else:
            require(field in LIFECYCLE_FLOAT_FIELDS, f"untyped field: {field}")
            typed[field] = _float(value, field)
    return typed


def _validate_source_bundle(
    config: Mapping[str, Any],
    *,
    root: Path,
) -> str:
    bundle = config.get("source_bundle")
    require(isinstance(bundle, Mapping), "source_bundle missing")
    require(
        bundle.get("hash_mode")
        == "sha256_utf8_after_crlf_to_lf_reject_lone_cr",
        "source bundle hash_mode drift",
    )
    files = bundle.get("files")
    require(isinstance(files, list), "source_bundle.files missing")
    expected_paths = [path.as_posix() for path in SOURCE_PATHS]
    require(
        [row.get("path") for row in files if isinstance(row, Mapping)]
        == expected_paths,
        "source path manifest drift",
    )
    expected_files = [
        {
            "path": relative.as_posix(),
            "semantic_sha256": semantic_text_sha256(root / relative),
        }
        for relative in SOURCE_PATHS
    ]
    require(files == expected_files, "runtime source file hash drift")
    require(
        bundle.get("path_manifest_sha256")
        == canonical_sha256(expected_paths),
        "source path manifest self-hash mismatch",
    )
    expected_bundle = canonical_sha256(expected_files)
    require(
        bundle.get("bundle_sha256") == expected_bundle,
        "source bundle self-hash mismatch",
    )
    return expected_bundle


def _validate_manifest(
    config: Mapping[str, Any],
    *,
    root: Path,
) -> tuple[g12.InputPrefix, str, str]:
    require(config.get("schema") == SCHEMA, "obsolete/unexpected schema")
    declared_self = config.get("self_sha256")
    require(_is_sha256(declared_self), "config self_sha256 malformed")
    unsigned = dict(config)
    unsigned.pop("self_sha256", None)
    require(
        canonical_sha256(unsigned) == declared_self,
        "config self_sha256 mismatch",
    )
    require(config.get("status") == STATUS, "Stage-D status is not PASS")
    require(
        config.get("generated_by") == GENERATOR_PATH.as_posix(),
        "generated_by does not name the real Python generator",
    )
    require(
        config.get("validated_by") == VALIDATOR_PATH.as_posix(),
        "validated_by drift",
    )
    require(
        config.get("promotion_status") == PROMOTION_STATUS,
        "Stage-D promotion status drift",
    )
    require(
        config.get("performance_gain_claimed") is False,
        "Stage D must not claim performance gain",
    )
    require(
        config.get("performance_conclusion")
        in {
            "NO_RULE_IMPROVED_BOTH_MEAN_AND_P95_VS_M0_ON_144",
            "DESCRIPTIVE_DIFFERENCE_ONLY_NOT_PROMOTION",
        },
        "invalid descriptive performance conclusion",
    )
    identity = g12.assert_fixed_identity(root)
    protected = config.get("protected_inputs")
    expected_protected = {
        "map_path": CANONICAL_MAP_PATH,
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "task_path": CANONICAL_SOURCE_PATH,
        "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
        "task_semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
        "map_topology_mutated": False,
        "task_rows_mutated": False,
    }
    require(protected == expected_protected, "protected input manifest drift")
    require(
        identity["map_raw_sha256"] == CANONICAL_MAP_RAW_SHA256
        and identity["map_semantic_sha256"]
        == CANONICAL_MAP_SEMANTIC_SHA256
        and identity["source_raw_sha256"] == CANONICAL_SOURCE_RAW_SHA256,
        "protected input bytes drift",
    )

    prefix = g12.load_input_prefix(PREFIX_SEGMENTS, root=root)
    workload = config.get("workload")
    require(isinstance(workload, Mapping), "workload binding missing")
    expected_workload = {
        "selection": "first_144_nonempty_rows_without_reordering",
        "segment_count": PREFIX_SEGMENTS,
        "raw_bag_count": prefix.raw_bag_count,
        "prefix_sha256": prefix.prefix_sha256,
        "segment_ids_sha256": canonical_sha256(
            [str(row["segment_id"]) for row in prefix.rows]
        ),
        "first_segment_id": prefix.first_segment_id,
        "last_segment_id": prefix.last_segment_id,
    }
    require(workload == expected_workload, "protected 144 workload drift")
    require(
        config.get("frozen_controls") == dict(FROZEN_CONTROLS),
        "R3/S1/P2/C0/Q0/E4 controls drift",
    )
    require(config.get("boundary") == BOUNDARY, "one-hop boundary drift")
    require(
        config.get("online_rules") == list(ONLINE_RULES),
        "M0-M6 coverage drift",
    )
    require(config.get("control_rule") == CONTROL_RULE, "control rule drift")
    require(
        config.get("negative_rules") == list(NEGATIVE_RULES),
        "M7-M9 negative coverage drift",
    )

    source_digest = _validate_source_bundle(config, root=root)
    binary = config.get("binary")
    require(isinstance(binary, Mapping), "binary binding missing")
    binary_digest = binary.get("sha256")
    require(_is_sha256(binary_digest), "binary SHA-256 malformed")
    require(
        isinstance(binary.get("path_hint"), str)
        and bool(binary.get("path_hint")),
        "binary path_hint missing",
    )
    return prefix, source_digest, str(binary_digest)


def _validate_negative_evidence(config: Mapping[str, Any]) -> None:
    evidence = config.get("negative_rule_evidence")
    require(isinstance(evidence, Mapping), "negative rule evidence missing")
    require(set(evidence) == set(NEGATIVE_RULES), "negative rule set drift")
    for rule in NEGATIVE_RULES:
        row = evidence[rule]
        require(isinstance(row, Mapping), f"{rule} evidence malformed")
        require(row.get("rule") == rule, f"{rule} identity drift")
        require(row.get("online_allowed") is False, f"{rule} online allowed")
        require(
            row.get("execution_status") == "REJECTED_FAIL_CLOSED",
            f"{rule} did not fail closed",
        )
        require(
            row.get("exception_type") == "ValueError",
            f"{rule} rejection type drift",
        )
        message = row.get("message")
        require(
            isinstance(message, str)
            and (rule in message or "M8/M9" in message),
            f"{rule} rejection message missing rule identity",
        )
        require(
            row.get("production_entrypoint")
            == (
                "czr005.cpp_backend."
                "g4irsf11_event_runtime_from_records"
            ),
            f"{rule} was not tested at the production entrypoint",
        )
        require(
            row.get("native_execution_started") is False
            and row.get("fail_closed") is True,
            f"{rule} negative is not fail closed",
        )


def _validate_output_hashes(
    config: Mapping[str, Any],
    *,
    artifact_root: Path,
) -> None:
    hashes = config.get("output_sha256")
    require(isinstance(hashes, Mapping), "output hash manifest missing")
    expected_paths = (REPORT_PATH, LIFECYCLE_PATH, RULE_AB_PATH)
    require(
        set(hashes) == {path.as_posix() for path in expected_paths},
        "output hash path set drift",
    )
    for relative in expected_paths:
        declared = hashes.get(relative.as_posix())
        require(_is_sha256(declared), f"{relative} digest malformed")
        require(
            file_sha256(artifact_root / relative) == declared,
            f"{relative} output hash mismatch",
        )


def _validate_ab_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    config: Mapping[str, Any],
    prefix: g12.InputPrefix,
    source_digest: str,
    binary_digest: str,
) -> dict[str, Mapping[str, str]]:
    require(len(rows) == 10, "rule A/B must contain M0-M9 exactly once")
    by_rule: dict[str, Mapping[str, str]] = {}
    for index, row in enumerate(rows):
        _verify_row_self_hash(row, f"rule_ab[{index}]")
        rule = row["rule"]
        require(rule not in by_rule, f"duplicate A/B rule: {rule}")
        by_rule[rule] = row
        require(row["schema"] == SCHEMA, f"{rule} schema drift")
        require(row["control_rule"] == CONTROL_RULE, f"{rule} control drift")
        require(
            _int(row["segment_count"], f"{rule}.segment_count")
            == PREFIX_SEGMENTS,
            f"{rule} segment count drift",
        )
        require(
            _int(row["raw_bag_count"], f"{rule}.raw_bag_count")
            == prefix.raw_bag_count,
            f"{rule} raw bag count drift",
        )
        expected_identity = {
            "input_selection_sha256": prefix.prefix_sha256,
            "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
            "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "source_bundle_sha256": source_digest,
            "binary_sha256": binary_digest,
        }
        require(
            all(row[name] == value for name, value in expected_identity.items()),
            f"{rule} evidence identity drift",
        )
        require(_is_sha256(row["row_sha256"]), f"{rule} row hash malformed")
        require(
            row["performance_gain_claimed"] == "false",
            f"{rule} unauthorized performance claim",
        )
    require(
        set(by_rule) == set(ONLINE_RULES) | set(NEGATIVE_RULES),
        "rule A/B row set drift",
    )

    runs = config.get("runs")
    require(isinstance(runs, Mapping), "config runs missing")
    require(set(runs) == set(ONLINE_RULES), "config online run set drift")
    for rule in ONLINE_RULES:
        row = by_rule[rule]
        require(row["online_allowed"] == "true", f"{rule} not online")
        require(
            row["execution_status"] == "EXECUTED_PRODUCTION_E4",
            f"{rule} was not executed through production E4",
        )
        require(
            row["rejection_type"] == "" and row["rejection_message"] == "",
            f"{rule} contains spurious rejection evidence",
        )
        require(
            _int(row["completed_count"], f"{rule}.completed_count")
            == PREFIX_SEGMENTS
            and _int(row["failed_count"], f"{rule}.failed_count") == 0,
            f"{rule} is incomplete",
        )
        require(
            _int(
                row["unresolved_deadlock_count"],
                f"{rule}.unresolved_deadlock_count",
            )
            == 0,
            f"{rule} left an unresolved deadlock",
        )
        require(
            row["hard_gate_pass"] == "true"
            and row["hard_gate_failures"] == "",
            f"{rule} hard gates failed",
        )
        require(
            _int(row["lifecycle_dropped_count"], f"{rule}.dropped") == 0,
            f"{rule} lifecycle is truncated",
        )
        require(
            _int(row["lifecycle_transition_count"], f"{rule}.transitions")
            == _int(row["lifecycle_stored_count"], f"{rule}.stored"),
            f"{rule} lifecycle count identity failed",
        )
        require(
            _int(row["merge_peak_active_unconsumed"], f"{rule}.active")
            >= 0,
            f"{rule} invalid active count",
        )
        for name in (
            "end_time",
            "mean_completion_seconds",
            "p95_completion_seconds",
            "max_completion_seconds",
            "mean_grant_wait_seconds",
            "max_grant_wait_seconds",
            "grant_slot_busy_seconds",
            "grant_slot_idle_seconds",
            "merge_throughput_per_second",
            "incoming_edge_fairness_jain",
            "deadline_miss_rate",
            "mean_completion_delta_vs_m0_seconds",
            "p95_completion_delta_vs_m0_seconds",
            "end_time_delta_vs_m0_seconds",
            "grant_wait_delta_vs_m0_seconds",
        ):
            _float(row[name], f"{rule}.{name}")
        require(
            0.0
            <= _float(
                row["incoming_edge_fairness_jain"],
                f"{rule}.incoming_edge_fairness_jain",
            )
            <= 1.0 + 1.0e-12,
            f"{rule} fairness is outside [0,1]",
        )
        for name in (
            "committed_order_sha256",
            "bag_projection_sha256",
            "lifecycle_projection_sha256",
            "deterministic_result_sha256",
        ):
            require(_is_sha256(row[name]), f"{rule}.{name} malformed")
        require(
            row["promotion_status"] == PROMOTION_STATUS,
            f"{rule} promotion status drift",
        )
        repeat_hashes = row["repeat_deterministic_sha256"].split("|")
        require(
            _int(row["repeat_count"], f"{rule}.repeat_count")
            == RUNTIME_REPEAT_COUNT
            and len(repeat_hashes) == RUNTIME_REPEAT_COUNT
            and all(_is_sha256(value) for value in repeat_hashes)
            and len(set(repeat_hashes)) == 1
            and row["repeat_determinism_pass"] == "true",
            f"{rule} independent repeat identity failed",
        )
        run = runs[rule]
        require(isinstance(run, Mapping), f"{rule} run manifest malformed")
        require(run.get("run_id") == row["run_id"], f"{rule} run ID drift")
        require(
            run.get("repeat_count") == RUNTIME_REPEAT_COUNT
            and run.get("repeat_deterministic_sha256") == repeat_hashes
            and run.get("repeat_determinism_pass") is True,
            f"{rule} manifest repeat evidence drift",
        )
        gates = run.get("hard_gates")
        require(
            isinstance(gates, Mapping)
            and set(gates) == HARD_GATE_NAMES
            and all(value is True for value in gates.values()),
            f"{rule} manifest hard gates are not all true",
        )
        projection = run.get("summary_projection")
        require(isinstance(projection, Mapping), f"{rule} summary missing")
        require(
            projection.get("completed_count") == PREFIX_SEGMENTS
            and projection.get("failed_count") == 0
            and projection.get("unresolved_deadlock_count") == 0
            and projection.get("merge_grant_lifecycle_dropped_count") == 0
            and projection.get("merge_grant_protocol_integrity_pass") is True
            and projection.get("runtime_full_astar_calls") == 0
            and projection.get("global_reservation_scan_count") == 0
            and projection.get("priority_global_scan_count") == 0
            and projection.get("priority_future_route_input_count") == 0
            and projection.get("reservation_depth") == 1
            and projection.get("two_step_reservation_count") == 0
            and projection.get("event_limit_reached") is False
            and projection.get("time_limit_reached") is False
            and projection.get("merge_grant_rule") == rule
            and projection.get("event_semantics")
            == "E4_batch_plus_destination_merge_request",
            f"{rule} summary projection violates Stage-D gates",
        )
        runtime_echo = run.get("runtime_echo_projection")
        expected_echo = _expected_runtime_echo(rule)
        require(
            isinstance(runtime_echo, Mapping)
            and set(runtime_echo) == set(expected_echo),
            f"{rule} frozen runtime echo projection missing",
        )
        for scope, expected_values in expected_echo.items():
            actual_values = runtime_echo.get(scope)
            require(
                isinstance(actual_values, Mapping)
                and set(actual_values) == set(expected_values),
                f"{rule} {scope} frozen runtime echo field set drift",
            )
            for name, expected_value in expected_values.items():
                actual_value = actual_values[name]
                require(
                    type(actual_value) is type(expected_value)
                    and actual_value == expected_value,
                    (
                        f"{rule} {scope}.{name} does not equal the "
                        "frozen runtime control"
                    ),
                )
        require(
            all(
                projection.get(name) == value
                and type(projection.get(name)) is type(value)
                for name, value in expected_echo["summary"].items()
            ),
            f"{rule} summary/runtime echo projection mismatch",
        )
        for name in (
            "committed_order_sha256",
            "bag_projection_sha256",
            "lifecycle_projection_sha256",
            "deterministic_result_sha256",
        ):
            require(
                run.get(name) == row[name],
                f"{rule} {name} table/manifest mismatch",
            )

    control = by_rule[CONTROL_RULE]
    for name in (
        "mean_completion_delta_vs_m0_seconds",
        "p95_completion_delta_vs_m0_seconds",
        "end_time_delta_vs_m0_seconds",
        "grant_wait_delta_vs_m0_seconds",
    ):
        require(
            abs(_float(control[name], f"M0.{name}")) <= 1.0e-12,
            f"M0 control delta {name} is non-zero",
        )

    evidence = config["negative_rule_evidence"]
    for rule in NEGATIVE_RULES:
        row = by_rule[rule]
        require(row["online_allowed"] == "false", f"{rule} online allowed")
        require(
            row["execution_status"] == "REJECTED_FAIL_CLOSED",
            f"{rule} did not fail closed",
        )
        require(
            row["rejection_type"] == evidence[rule]["exception_type"]
            and row["rejection_message"] == evidence[rule]["message"],
            f"{rule} table/manifest rejection mismatch",
        )
        require(
            row["hard_gate_pass"] == "false"
            and row["hard_gate_failures"] == "ONLINE_RULE_FORBIDDEN"
            and row["promotion_status"] == "NOT_APPLICABLE_FAIL_CLOSED",
            f"{rule} negative status drift",
        )
        metric_columns = set(RULE_AB_COLUMNS) - {
            "schema",
            "rule",
            "control_rule",
            "online_allowed",
            "execution_status",
            "rejection_type",
            "rejection_message",
            "run_id",
            "segment_count",
            "raw_bag_count",
            "input_selection_sha256",
            "map_raw_sha256",
            "map_semantic_sha256",
            "task_raw_sha256",
            "source_bundle_sha256",
            "binary_sha256",
            "hard_gate_pass",
            "hard_gate_failures",
            "performance_gain_claimed",
            "promotion_status",
            "row_sha256",
        }
        require(
            all(row[name] == "" for name in metric_columns),
            f"{rule} negative row fabricates runtime metrics",
        )
    return by_rule


def _validate_lifecycle_rows(
    rows: Sequence[Mapping[str, str]],
    *,
    config: Mapping[str, Any],
    ab_by_rule: Mapping[str, Mapping[str, str]],
    prefix: g12.InputPrefix,
    source_digest: str,
    binary_digest: str,
    root: Path,
) -> None:
    prefix_by_segment = {
        str(row["segment_id"]): row for row in prefix.rows
    }
    allowed_segments = set(prefix_by_segment)
    map_document = json.loads(
        (root / CANONICAL_MAP_PATH).read_text(encoding="utf-8")
    )
    real_edges = {
        (int(row["start"]), int(row["end"]))
        for row in map_document["edges"]
    }
    travel_by_edge = {
        (int(row["start"]), int(row["end"])): float(row["travel_time"])
        for row in map_document["edges"]
    }
    service_by_node = {
        int(row["location"]): float(row["service_time"])
        for row in map_document["nodes"]
    }
    by_rule: dict[str, list[dict[str, Any]]] = {
        rule: [] for rule in ONLINE_RULES
    }
    request_rows: dict[
        tuple[str, int, int], list[dict[str, Any]]
    ] = {}
    grant_owner: dict[
        tuple[str, int, int], tuple[str, int, int]
    ] = {}
    allowed_states = {
        "REQUESTED",
        "ISSUED",
        "PREPARED",
        "COMMITTED",
        "CONSUMED",
        "EXPIRED",
        "REVOKED_FAULT",
        "REVOKED_STALE_STATE",
        "REVOKED_REPLAN_CURRENT_EDGE",
        "ROLLED_BACK",
    }
    expected_identity = {
        "input_selection_sha256": prefix.prefix_sha256,
        "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
        "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
        "source_bundle_sha256": source_digest,
        "binary_sha256": binary_digest,
    }
    for index, row in enumerate(rows):
        _verify_row_self_hash(row, f"lifecycle[{index}]")
        require(row["schema"] == SCHEMA, "lifecycle schema drift")
        rule = row["rule"]
        require(rule in ONLINE_RULES, "lifecycle contains non-online rule")
        require(
            row["run_id"] == ab_by_rule[rule]["run_id"],
            f"{rule} lifecycle run ID drift",
        )
        require(
            all(row[name] == value for name, value in expected_identity.items()),
            f"{rule} lifecycle evidence identity drift",
        )
        require(
            _int(row["transition_index"], "transition_index")
            == len(by_rule[rule]),
            f"{rule} transition index is not contiguous",
        )
        typed = _typed_lifecycle_row(row)
        require(
            typed["segment_id"] in allowed_segments,
            "lifecycle segment escaped protected 144 prefix",
        )
        source_row = prefix_by_segment[typed["segment_id"]]
        require(
            typed["task_id"] == int(source_row["task_id"])
            and typed["goal"] == int(source_row["goal"]),
            "lifecycle task/goal identity drift",
        )
        edge = (typed["edge_from_node"], typed["edge_to_node"])
        require(
            edge == (typed["upstream_node"], typed["destination_node"]),
            "lifecycle edge/request identity mismatch",
        )
        require(edge in real_edges, "lifecycle contains non-map2 edge")
        expected_travel = travel_by_edge[edge]
        require(
            abs(typed["earliest_edge_entry"] - typed["request_time"])
            <= 1.0e-9,
            "lifecycle earliest edge entry was future-shifted",
        )
        require(
            abs(
                typed["exact_edge_travel_seconds"] - expected_travel
            )
            <= 1.0e-9,
            "lifecycle exact edge travel is not map2 travel time",
        )
        require(
            abs(
                typed["projected_arrival"]
                - (typed["request_time"] + expected_travel)
            )
            <= 1.0e-9,
            "lifecycle projected arrival is not request plus edge travel",
        )
        require(
            typed["destination_node"] in service_by_node,
            "lifecycle destination is not in map2",
        )
        expected_service = max(
            service_by_node[typed["destination_node"]], 0.001
        )
        require(
            abs(
                typed["destination_service_seconds"] - expected_service
            )
            <= 1.0e-9,
            "lifecycle service duration is not R3/map2",
        )
        if typed["grant_id"] > 0:
            grant_key = (
                rule,
                typed["destination_node"],
                typed["grant_id"],
            )
            request_key = (
                rule,
                typed["destination_node"],
                typed["request_id"],
            )
            prior_request = grant_owner.setdefault(grant_key, request_key)
            require(
                prior_request == request_key,
                f"grant {grant_key} was reused across requests",
            )
            require(
                typed["slot_end"] > typed["slot_start"]
                and abs(
                    (
                        typed["slot_end"]
                        - typed["slot_start"]
                    )
                    - expected_service
                )
                <= 1.0e-8,
                "lifecycle exact slot drift",
            )
            require(
                abs(
                    typed["slot_start"] - typed["projected_arrival"]
                )
                <= 1.0e-9,
                "lifecycle grant slot was future-shifted",
            )
            require(
                abs(typed["grant_expiry"] - typed["slot_end"])
                <= 1.0e-9,
                "lifecycle grant expiry does not equal slot end",
            )
        require(typed["state"] in allowed_states, "unknown lifecycle state")
        require(typed["wait_age"] >= -1.0e-12, "negative wait age")
        key = (
            rule,
            typed["destination_node"],
            typed["request_id"],
        )
        request_rows.setdefault(key, []).append(typed)
        by_rule[rule].append(typed)

    terminal_states = {
        "CONSUMED",
        "EXPIRED",
        "REVOKED_FAULT",
        "REVOKED_STALE_STATE",
        "REVOKED_REPLAN_CURRENT_EDGE",
        "ROLLED_BACK",
    }
    for key, transitions in request_rows.items():
        states = [row["state"] for row in transitions]
        ages = [row["wait_age"] for row in transitions]
        times = [row["time"] for row in transitions]
        require(states[0] == "REQUESTED", f"{key} lacks REQUESTED start")
        require(states[-1] in terminal_states, f"{key} lacks terminal state")
        require(states.count("REQUESTED") == 1, f"{key} duplicate REQUESTED")
        require(
            all(
                left <= right + 1.0e-12
                for left, right in zip(times, times[1:])
            ),
            f"{key} transition time is not monotone",
        )
        require(
            all(left <= right + 1.0e-12 for left, right in zip(ages, ages[1:])),
            f"{key} wait age is not monotone",
        )
        immutable = {
            field: transitions[0][field]
            for field in REQUEST_IMMUTABLE_FIELDS
        }
        require(
            all(
                all(row[field] == value for field, value in immutable.items())
                for row in transitions[1:]
            ),
            f"{key} immutable request identity changed across transitions",
        )
        for previous, current in zip(states, states[1:]):
            require(
                current in LEGAL_LIFECYCLE_SUCCESSORS.get(previous, set()),
                f"{key} illegal lifecycle transition {previous}->{current}",
            )
        granted = [
            row for row in transitions if row["grant_id"] > 0
        ]
        if granted:
            grant_identity = {
                field: granted[0][field]
                for field in GRANT_IMMUTABLE_FIELDS
            }
            require(
                all(
                    all(
                        row[field] == value
                        for field, value in grant_identity.items()
                    )
                    for row in granted[1:]
                ),
                f"{key} immutable grant identity changed across transitions",
            )
            require("ISSUED" in states, f"{key} grant lacks ISSUED")
            require(
                states.index("ISSUED")
                == next(
                    index
                    for index, row in enumerate(transitions)
                    if row["grant_id"] > 0
                ),
                f"{key} grant identity appeared outside ISSUED",
            )
        if states[-1] == "CONSUMED":
            require(
                states
                == [
                    "REQUESTED",
                    "ISSUED",
                    "PREPARED",
                    "COMMITTED",
                    "CONSUMED",
                ],
                f"{key} consumed lifecycle is not exact",
            )
            terminal = transitions[-1]
            exact_observations = {
                "observed_claimed_request_generation": terminal[
                    "request_generation"
                ],
                "observed_claimed_junction_queue_generation": terminal[
                    "junction_queue_generation"
                ],
                "observed_claimed_calendar_generation": terminal[
                    "calendar_generation"
                ],
                "observed_claimed_owner_runtime_bag_id": terminal[
                    "runtime_bag_id"
                ],
                "observed_claimed_edge_from_node": terminal[
                    "edge_from_node"
                ],
                "observed_claimed_edge_to_node": terminal["edge_to_node"],
                "observed_claimed_destination_node": terminal[
                    "destination_node"
                ],
                "observed_event_owner_runtime_bag_id": terminal[
                    "runtime_bag_id"
                ],
                "observed_event_edge_from_node": terminal["edge_from_node"],
                "observed_event_edge_to_node": terminal["edge_to_node"],
                "observed_event_destination_node": terminal[
                    "destination_node"
                ],
                "observed_physical_fault_generation": terminal[
                    "fault_generation"
                ],
                "observed_advertised_fault_generation": terminal[
                    "advertised_fault_generation"
                ],
            }
            require(
                all(
                    terminal[field] == value
                    for field, value in exact_observations.items()
                ),
                f"{key} consume-time capability identity mismatch",
            )
            require(
                terminal["observed_physical_fault_active"] is False
                and terminal[
                    "observed_exact_calendar_reservation_present"
                ]
                is True,
                f"{key} consume-time physical/calendar observation invalid",
            )

    runs = config["runs"]
    for rule in ONLINE_RULES:
        typed_rows = by_rule[rule]
        require(typed_rows, f"{rule} lifecycle is empty")
        ab = ab_by_rule[rule]
        require(
            len(typed_rows)
            == _int(ab["lifecycle_stored_count"], f"{rule}.stored")
            == _int(
                ab["lifecycle_transition_count"], f"{rule}.transitions"
            ),
            f"{rule} lifecycle count mismatch",
        )
        requested = sum(row["state"] == "REQUESTED" for row in typed_rows)
        require(
            requested
            == _int(ab["merge_request_count"], f"{rule}.requests"),
            f"{rule} REQUESTED row count mismatch",
        )
        lifecycle_digest = canonical_sha256(typed_rows)
        require(
            lifecycle_digest == ab["lifecycle_projection_sha256"]
            == runs[rule]["lifecycle_projection_sha256"],
            f"{rule} typed lifecycle projection hash mismatch",
        )
        committed = [
            {
                "destination_node": row["destination_node"],
                "grant_id": row["grant_id"],
                "request_id": row["request_id"],
                "runtime_bag_id": row["runtime_bag_id"],
                "slot_start": row["slot_start"],
                "slot_end": row["slot_end"],
            }
            for row in typed_rows
            if row["state"] == "COMMITTED"
        ]
        require(
            canonical_sha256(committed) == ab["committed_order_sha256"],
            f"{rule} committed order projection mismatch",
        )
        intervals_by_destination: dict[
            int, list[tuple[float, float]]
        ] = {}
        for row in committed:
            intervals_by_destination.setdefault(
                row["destination_node"], []
            ).append((row["slot_start"], row["slot_end"]))
        for destination, intervals in intervals_by_destination.items():
            ordered = sorted(intervals)
            require(
                all(
                    previous[1] <= current[0] + 1.0e-9
                    for previous, current in zip(ordered, ordered[1:])
                ),
                f"{rule} destination {destination} grant slots overlap",
            )


def _validate_report(
    *,
    artifact_root: Path,
    prefix: g12.InputPrefix,
    source_digest: str,
    binary_digest: str,
) -> None:
    report = (artifact_root / REPORT_PATH).read_text(encoding="utf-8")
    for token in (
        STATUS,
        CANONICAL_MAP_RAW_SHA256,
        CANONICAL_MAP_SEMANTIC_SHA256,
        CANONICAL_SOURCE_RAW_SHA256,
        prefix.prefix_sha256,
        source_digest,
        binary_digest,
        "production E4 mechanism evidence",
        "not a performance promotion",
    ):
        require(token in report, f"report missing binding/status token: {token}")
    for rule in (*ONLINE_RULES, *NEGATIVE_RULES):
        require(f"`{rule}`" in report or f"| {rule} |" in report, f"report omits {rule}")
    require(
        "STANDALONE_PROTOCOL_TESTED_NOT_RUNTIME_INTEGRATED" not in report
        and "WITHHELD_UNTIL_RUNTIME_INTEGRATION" not in report
        and "--emit-artifacts" not in report,
        "report retains obsolete standalone claims",
    )


def validate_bundle(
    *,
    root: Path = ROOT,
    artifact_root: Path | None = None,
    binary: Path | None = None,
) -> dict[str, Any]:
    artifact_root = artifact_root or root
    config = _read_json(artifact_root / CONFIG_PATH)
    prefix, source_digest, binary_digest = _validate_manifest(
        config, root=root
    )
    _validate_negative_evidence(config)
    _validate_output_hashes(config, artifact_root=artifact_root)
    ab_rows = _read_csv(artifact_root / RULE_AB_PATH, RULE_AB_COLUMNS)
    lifecycle_rows = _read_csv(
        artifact_root / LIFECYCLE_PATH, LIFECYCLE_COLUMNS
    )
    ab_by_rule = _validate_ab_rows(
        ab_rows,
        config=config,
        prefix=prefix,
        source_digest=source_digest,
        binary_digest=binary_digest,
    )
    _validate_lifecycle_rows(
        lifecycle_rows,
        config=config,
        ab_by_rule=ab_by_rule,
        prefix=prefix,
        source_digest=source_digest,
        binary_digest=binary_digest,
        root=root,
    )
    _validate_report(
        artifact_root=artifact_root,
        prefix=prefix,
        source_digest=source_digest,
        binary_digest=binary_digest,
    )

    binary_recheck = "SEALED_DIGEST_ONLY"
    candidate = binary
    if candidate is None:
        hint = Path(str(config["binary"]["path_hint"]))
        candidate = hint if hint.is_absolute() else root / hint
        if not candidate.is_file():
            candidate = None
    if candidate is not None:
        require(candidate.is_file(), f"binary recheck file missing: {candidate}")
        require(
            file_sha256(candidate) == binary_digest,
            "provided/current native binary does not match sealed SHA-256",
        )
        binary_recheck = "VERIFIED_EXACT_BYTES"
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "online_rules": list(ONLINE_RULES),
        "negative_rules": list(NEGATIVE_RULES),
        "segment_count": PREFIX_SEGMENTS,
        "lifecycle_rows": len(lifecycle_rows),
        "source_bundle_sha256": source_digest,
        "binary_sha256": binary_digest,
        "binary_recheck": binary_recheck,
        "self_sha256": config["self_sha256"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary",
        type=Path,
        default=None,
        help="optional exact native extension for byte-for-byte recheck",
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=ROOT,
        help="root containing the four evidence paths",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = validate_bundle(
        root=ROOT,
        artifact_root=args.artifact_root,
        binary=args.binary,
    )
    print(
        "G4IRSF14 Stage-D artifacts valid:",
        f"rules={','.join(result['online_rules'])}",
        f"segments={result['segment_count']}",
        f"lifecycle_rows={result['lifecycle_rows']}",
        f"binary={result['binary_recheck']}",
        f"self_sha256={result['self_sha256']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
