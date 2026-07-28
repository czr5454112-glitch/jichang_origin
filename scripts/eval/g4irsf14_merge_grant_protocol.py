#!/usr/bin/env python3
"""Generate the Stage-14D production E4 merge-grant evidence bundle.

The formal experiment is intentionally narrow:

* the only topology is the protected ``map2.json``;
* the only demand is the first 144 non-empty rows of ``inputdata.jsonl``;
* every online rule M0--M6 receives that exact, unreordered workload;
* the runtime tuple is frozen at R3/S1/P2/C0/Q0/E4, scale 1, no fault;
* M7--M9 are exercised only as fail-closed production-entrypoint negatives;
* no performance promotion is authorized by this mechanism-stage artifact.

The generated CSV rows self-hash.  The JSON manifest binds the protected
inputs, workload prefix, runtime source bundle, loaded native binary, all
runtime projections, and every other committed output.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import g4irsf12_reproducible_harness as g12  # noqa: E402
from scripts.eval.g4irsf11_fixed_map import (  # noqa: E402
    assert_canonical_map,
    canonical_graph_records,
)
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
GENERATOR_PATH = Path("scripts/eval/g4irsf14_merge_grant_protocol.py")
VALIDATOR_PATH = Path("scripts/validate_g4irsf14_merge_grant_artifacts.py")
REPORT_PATH = Path("outputs/reports/g4irsf14_merge_grant_protocol.md")
LIFECYCLE_PATH = Path(
    "outputs/tables/g4irsf14_merge_grant_lifecycle.csv"
)
RULE_AB_PATH = Path("outputs/tables/g4irsf14_merge_rule_ab.csv")
CONFIG_PATH = Path("artifacts/configs/g4irsf14_merge_grant_protocol.json")

PREFIX_SEGMENTS = 144
ONLINE_RULES = tuple(f"M{index}" for index in range(7))
NEGATIVE_RULES = ("M7", "M8", "M9")
CONTROL_RULE = "M0"
RUNTIME_REPEAT_COUNT = 2
FROZEN_MODEL_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)

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

SUMMARY_PROJECTION_FIELDS = (
    "resource_semantics_id",
    "resource_semantics_echo",
    "pressure_mode",
    "pressure_mode_echo",
    "admission_mode",
    "admission_mode_echo",
    "source_admission_enabled",
    "framework_mode",
    "framework_mode_echo",
    "pibt_mode",
    "pibt_mode_echo",
    "pibt_max_depth",
    "pibt_preference_mode",
    "pibt_preference_mode_echo",
    "pibt_regret_prior_record_count",
    "priority_mode",
    "priority_mode_echo",
    "scorer_mode",
    "scorer_mode_echo",
    "scorer_model_sha256",
    "legacy_pibt_lite_enabled",
    "fault_policy_enabled",
    "fault_event_count",
    "repair_event_count",
    "declared_max_events",
    "declared_max_simulation_time",
    "local_queue_capacity",
    "pibt_max_ready_bags",
    "pibt_max_local_resources",
    "pibt_max_candidates_per_bag",
    "event_trace_limit",
    "opportunity_telemetry_enabled",
    "requested_count",
    "completed_count",
    "failed_count",
    "unresolved_deadlock_count",
    "reservation_conflicts",
    "physical_fault_edge_entry_violation_count",
    "runtime_full_astar_calls",
    "global_reservation_scan_count",
    "priority_global_scan_count",
    "priority_future_route_input_count",
    "priority_teacher_input_count",
    "microphase_runtime_global_scan_count",
    "reservation_depth",
    "two_step_reservation_count",
    "max_edges_selected_per_arrive",
    "release_selected_edge_count",
    "full_future_routes_stored",
    "bag_future_path_field_present",
    "event_limit_reached",
    "time_limit_reached",
    "stale_arbitration_event_count",
    "artificial_batch_delay_seconds",
    "end_time",
    "destination_merge_arbitration_event_count",
    "merge_grant_request_count",
    "merge_grant_issued_count",
    "merge_grant_issued_transition_count",
    "merge_grant_prepared_count",
    "merge_grant_prepared_transition_count",
    "merge_grant_committed_count",
    "merge_grant_committed_transition_count",
    "merge_grant_consumed_count",
    "merge_grant_expired_count",
    "merge_grant_request_expired_count",
    "merge_grant_grant_expired_count",
    "merge_grant_revoked_count",
    "merge_grant_post_commit_revoked_count",
    "merge_grant_post_commit_expired_count",
    "merge_grant_post_commit_rollback_count",
    "merge_grant_revoked_fault_count",
    "merge_grant_revoked_stale_state_count",
    "merge_grant_revoked_replan_current_edge_count",
    "merge_grant_rolled_back_count",
    "merge_grant_exact_slot_busy_count",
    "merge_grant_active_grant_rejection_count",
    "merge_grant_queue_capacity_block_count",
    "merge_grant_contended_loser_retry_count",
    "merge_grant_lifecycle_transition_count",
    "merge_grant_lifecycle_stored_count",
    "merge_grant_lifecycle_dropped_count",
    "merge_grant_terminal_request_count",
    "merge_grant_outstanding_request_count",
    "merge_grant_goal_exempt_bypass_count",
    "merge_grant_stale_arbitration_count",
    "merge_grant_duplicate_wakeup_prevented_count",
    "merge_grant_peak_pending_requests",
    "merge_grant_peak_active_unconsumed",
    "merge_grant_final_active_unconsumed",
    "merge_grant_conservation_holds",
    "merge_grant_active_bijection_holds",
    "merge_grant_runtime_owned_capability",
    "merge_grant_exact_slot_no_future_shift",
    "merge_grant_lifecycle_complete",
    "merge_grant_protocol_integrity_pass",
    "merge_grant_rule",
    "merge_grant_rule_echo",
    "merge_grant_max_pending_requests",
    "merge_grant_lifecycle_limit",
    "event_semantics",
    "event_semantics_echo",
)


class ProtocolError(RuntimeError):
    """Raised when formal Stage-14D evidence cannot be admitted."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProtocolError(message)


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
        raise ProtocolError(f"source file is not strict UTF-8: {path}") from exc
    normalized = text.replace("\r\n", "\n")
    require(
        "\r" not in normalized,
        f"source file contains unsupported lone CR: {path}",
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        require(math.isfinite(value), "CSV value must be finite")
        if value == 0.0:
            return "0"
        return format(value, ".17g")
    if isinstance(value, str):
        return value
    raise ProtocolError(f"unsupported CSV value type: {type(value).__name__}")


def _sealed_row(
    row: Mapping[str, Any],
    columns: Sequence[str],
) -> dict[str, str]:
    require(columns[-1] == "row_sha256", "sealed CSV must end in row_sha256")
    normalized = {
        column: _cell(row.get(column, ""))
        for column in columns
        if column != "row_sha256"
    }
    normalized["row_sha256"] = canonical_sha256(normalized)
    return normalized


def _csv_bytes(
    columns: Sequence[str],
    rows: Iterable[Mapping[str, str]],
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer,
        fieldnames=list(columns),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


def source_bundle(root: Path = ROOT) -> dict[str, Any]:
    files = [
        {
            "path": relative.as_posix(),
            "semantic_sha256": semantic_text_sha256(root / relative),
        }
        for relative in SOURCE_PATHS
    ]
    return {
        "hash_mode": "sha256_utf8_after_crlf_to_lf_reject_lone_cr",
        "files": files,
        "path_manifest_sha256": canonical_sha256(
            [row["path"] for row in files]
        ),
        "bundle_sha256": canonical_sha256(files),
    }


def _path_hint(path: Path, root: Path) -> str:
    resolved = path.resolve(strict=True)
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def resolve_binary(
    binary: Path,
    *,
    search_path: Path | None,
) -> tuple[Path, Path]:
    resolved = binary.resolve(strict=True)
    require(
        resolved.suffix.lower() in {".pyd", ".so", ".dylib"},
        "native binary must be a Python extension module",
    )
    directory = (
        search_path.resolve(strict=True)
        if search_path is not None
        else resolved.parent
    )
    require(
        resolved.parent == directory,
        "--search-path must be the directory containing --binary",
    )
    return resolved, directory


def _runtime_kwargs(
    *,
    rule: str,
    prefix: g12.InputPrefix,
    binary: Path,
    search_path: Path,
    root: Path,
    repeat_index: int | None = None,
) -> dict[str, Any]:
    nodes, edges, heuristic = canonical_graph_records(
        assert_canonical_map(root / CANONICAL_MAP_PATH)
    )
    controls = dict(FROZEN_CONTROLS)
    controls.pop("reservation_depth")
    return {
        "node_records": nodes,
        "edge_records": edges,
        "heuristic_time": heuristic,
        "bag_records": g12.binding_bag_records(prefix),
        "fault_windows": [],
        "scenario": (
            f"g4irsf14_stage_d_144_{rule}"
            if repeat_index is None
            else f"g4irsf14_stage_d_144_{rule}_repeat_{repeat_index}"
        ),
        "expected_binary_path": binary,
        "search_path": search_path,
        "summary_only": False,
        "merge_grant_rule": rule,
        **controls,
    }


def _strict_int(value: Any, label: str) -> int:
    require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{label} must be an integer",
    )
    return int(value)


def _finite(value: Any, label: str) -> float:
    require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{label} must be numeric",
    )
    result = float(value)
    require(math.isfinite(result), f"{label} must be finite")
    return result


def _bool(value: Any, label: str) -> bool:
    require(isinstance(value, bool), f"{label} must be boolean")
    return bool(value)


def _summary_projection(summary: Mapping[str, Any]) -> dict[str, Any]:
    missing = [name for name in SUMMARY_PROJECTION_FIELDS if name not in summary]
    require(not missing, "runtime summary missing: " + ",".join(missing))
    return {name: summary[name] for name in SUMMARY_PROJECTION_FIELDS}


def _validate_frozen_runtime_echo(
    summary: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    rule: str,
) -> dict[str, dict[str, Any]]:
    expected_summary: dict[str, Any] = {
        "resource_semantics_id": FROZEN_CONTROLS["resource_semantics"],
        "resource_semantics_echo": FROZEN_CONTROLS["resource_semantics"],
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
    }
    expected_trace: dict[str, Any] = {
        "scale": FROZEN_CONTROLS["scale"],
        "reservation_depth": FROZEN_CONTROLS["reservation_depth"],
        "resource_semantics_id": FROZEN_CONTROLS["resource_semantics"],
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
    }
    projections: dict[str, dict[str, Any]] = {}
    for scope, source, expected in (
        ("summary", summary, expected_summary),
        ("trace_context", context, expected_trace),
    ):
        missing = sorted(set(expected) - set(source))
        require(
            not missing,
            f"{scope} missing frozen runtime echoes: {','.join(missing)}",
        )
        actual = {name: source[name] for name in expected}
        for name, expected_value in expected.items():
            actual_value = actual[name]
            require(
                type(actual_value) is type(expected_value)
                and actual_value == expected_value,
                (
                    f"{scope}.{name} does not echo frozen runtime control: "
                    f"actual={actual_value!r}, expected={expected_value!r}"
                ),
            )
        projections[scope] = actual
    return projections


def _validate_loaded_binary_identity(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    expected_binary_path: Path,
    expected_binary_sha256: str,
) -> None:
    expected_path_text = str(expected_binary_path.resolve(strict=True))
    for owner, container in (("payload", payload), ("summary", summary)):
        loaded_path = container.get("loaded_cpp_binary_path")
        loaded_sha256 = container.get("loaded_cpp_binary_sha256")
        require(
            isinstance(loaded_path, str)
            and os.path.normcase(str(Path(loaded_path).resolve()))
            == os.path.normcase(expected_path_text),
            f"{owner} loaded native binary path does not match exact binary",
        )
        require(
            loaded_sha256 == expected_binary_sha256,
            f"{owner} loaded native binary SHA-256 does not match exact bytes",
        )


def _hard_gates(
    summary: Mapping[str, Any],
    *,
    expected_segments: int,
) -> dict[str, bool]:
    return {
        "complete": (
            _strict_int(summary.get("requested_count"), "requested_count")
            == expected_segments
            and _strict_int(summary.get("completed_count"), "completed_count")
            == expected_segments
            and _strict_int(summary.get("failed_count"), "failed_count") == 0
        ),
        "conflict_free": (
            _strict_int(
                summary.get("reservation_conflicts"),
                "reservation_conflicts",
            )
            == 0
        ),
        "unsafe_zero": (
            _strict_int(
                summary.get("physical_fault_edge_entry_violation_count"),
                "physical_fault_edge_entry_violation_count",
            )
            == 0
        ),
        "deadlock_resolved": (
            _strict_int(
                summary.get("unresolved_deadlock_count"),
                "unresolved_deadlock_count",
            )
            == 0
        ),
        "astar_zero": (
            _strict_int(
                summary.get("runtime_full_astar_calls"),
                "runtime_full_astar_calls",
            )
            == 0
        ),
        "global_scan_zero": all(
            _strict_int(summary.get(name), name) == 0
            for name in (
                "global_reservation_scan_count",
                "priority_global_scan_count",
                "microphase_runtime_global_scan_count",
            )
        ),
        "future_route_zero": (
            _strict_int(
                summary.get("priority_future_route_input_count"),
                "priority_future_route_input_count",
            )
            == 0
            and _strict_int(
                summary.get("full_future_routes_stored"),
                "full_future_routes_stored",
            )
            == 0
            and not _bool(
                summary.get("bag_future_path_field_present"),
                "bag_future_path_field_present",
            )
        ),
        "teacher_input_zero": (
            _strict_int(
                summary.get("priority_teacher_input_count"),
                "priority_teacher_input_count",
            )
            == 0
        ),
        "reservation_depth_one": (
            _strict_int(summary.get("reservation_depth"), "reservation_depth")
            == 1
            and _strict_int(
                summary.get("two_step_reservation_count"),
                "two_step_reservation_count",
            )
            == 0
            and _strict_int(
                summary.get("max_edges_selected_per_arrive"),
                "max_edges_selected_per_arrive",
            )
            <= 1
            and _strict_int(
                summary.get("release_selected_edge_count"),
                "release_selected_edge_count",
            )
            == 0
        ),
        "no_event_or_time_limit": (
            not _bool(
                summary.get("event_limit_reached"), "event_limit_reached"
            )
            and not _bool(
                summary.get("time_limit_reached"), "time_limit_reached"
            )
        ),
        "no_stale_arbitration": (
            _strict_int(
                summary.get("stale_arbitration_event_count"),
                "stale_arbitration_event_count",
            )
            == 0
        ),
        "zero_artificial_delay": (
            abs(
                _finite(
                    summary.get("artificial_batch_delay_seconds"),
                    "artificial_batch_delay_seconds",
                )
            )
            <= 1.0e-15
        ),
        "lifecycle_complete": (
            _strict_int(
                summary.get("merge_grant_lifecycle_dropped_count"),
                "merge_grant_lifecycle_dropped_count",
            )
            == 0
            and _bool(
                summary.get("merge_grant_lifecycle_complete"),
                "merge_grant_lifecycle_complete",
            )
        ),
        "protocol_integrity": all(
            _bool(summary.get(name), name)
            for name in (
                "merge_grant_conservation_holds",
                "merge_grant_active_bijection_holds",
                "merge_grant_runtime_owned_capability",
                "merge_grant_exact_slot_no_future_shift",
                "merge_grant_protocol_integrity_pass",
            )
        )
        and _strict_int(
            summary.get("merge_grant_final_active_unconsumed"),
            "merge_grant_final_active_unconsumed",
        )
        == 0
        and _strict_int(
            summary.get("merge_grant_outstanding_request_count"),
            "merge_grant_outstanding_request_count",
        )
        == 0,
    }


def _p95(values: Sequence[float]) -> float:
    require(bool(values), "p95 requires observations")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _grant_slot_metrics(
    lifecycle: Sequence[Mapping[str, Any]],
) -> tuple[float, float]:
    intervals_by_destination: dict[int, list[tuple[float, float]]] = {}
    seen: set[tuple[int, int]] = set()
    for row in lifecycle:
        if row["state"] != "COMMITTED":
            continue
        key = (
            _strict_int(row["destination_node"], "destination_node"),
            _strict_int(row["grant_id"], "grant_id"),
        )
        if key in seen:
            continue
        seen.add(key)
        start = _finite(row["slot_start"], "slot_start")
        end = _finite(row["slot_end"], "slot_end")
        require(end > start, "committed grant slot must be non-empty")
        intervals_by_destination.setdefault(key[0], []).append((start, end))
    busy = sum(
        end - start
        for intervals in intervals_by_destination.values()
        for start, end in intervals
    )
    idle = 0.0
    for intervals in intervals_by_destination.values():
        ordered = sorted(intervals)
        for previous, current in zip(ordered, ordered[1:]):
            require(
                previous[1] <= current[0] + 1.0e-9,
                "destination grant slots overlap",
            )
        span = max(end for _, end in ordered) - min(
            start for start, _ in ordered
        )
        idle += max(
            0.0,
            span - sum(end - start for start, end in ordered),
        )
    return busy, idle


def _incoming_edge_fairness(
    lifecycle: Sequence[Mapping[str, Any]],
) -> float:
    counts: dict[tuple[int, int], int] = {}
    for row in lifecycle:
        if row["state"] != "CONSUMED":
            continue
        key = (
            _strict_int(row["upstream_node"], "upstream_node"),
            _strict_int(row["destination_node"], "destination_node"),
        )
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return 1.0
    values = list(counts.values())
    return (sum(values) ** 2) / (len(values) * sum(v * v for v in values))


def _validate_exact_request_timing(
    row: Mapping[str, Any],
    *,
    expected_travel: float,
    expected_service: float,
) -> None:
    request_time = _finite(row["request_time"], "request_time")
    earliest_edge_entry = _finite(
        row["earliest_edge_entry"], "earliest_edge_entry"
    )
    exact_edge_travel = _finite(
        row["exact_edge_travel_seconds"],
        "exact_edge_travel_seconds",
    )
    projected_arrival = _finite(
        row["projected_arrival"], "projected_arrival"
    )
    require(
        abs(earliest_edge_entry - request_time) <= 1.0e-9,
        "earliest edge entry was future-shifted from request time",
    )
    require(
        abs(exact_edge_travel - expected_travel) <= 1.0e-9,
        "exact edge travel is not the map2 directed-edge travel time",
    )
    require(
        abs(projected_arrival - (request_time + expected_travel))
        <= 1.0e-9,
        "projected arrival is not request time plus exact edge travel",
    )
    if _strict_int(row["grant_id"], "grant_id") <= 0:
        return
    slot_start = _finite(row["slot_start"], "slot_start")
    slot_end = _finite(row["slot_end"], "slot_end")
    require(slot_end > slot_start, "grant slot is empty")
    require(
        abs((slot_end - slot_start) - expected_service) <= 1.0e-8,
        "grant slot length is not the exact R3 service duration",
    )
    require(
        abs(slot_start - projected_arrival) <= 1.0e-9,
        "grant slot start was future-shifted from projected arrival",
    )
    require(
        abs(_finite(row["grant_expiry"], "grant_expiry") - slot_end)
        <= 1.0e-9,
        "grant expiry does not equal exact slot end",
    )


def _validate_lifecycle(
    lifecycle: Sequence[Mapping[str, Any]],
    *,
    summary: Mapping[str, Any],
    prefix: g12.InputPrefix,
    real_edges: set[tuple[int, int]],
    travel_by_edge: Mapping[tuple[int, int], float],
    service_by_node: Mapping[int, float],
) -> None:
    require(bool(lifecycle), "production E4 lifecycle is empty")
    require(
        len(lifecycle)
        == _strict_int(
            summary.get("merge_grant_lifecycle_stored_count"),
            "merge_grant_lifecycle_stored_count",
        ),
        "lifecycle stored count mismatch",
    )
    require(
        _strict_int(
            summary.get("merge_grant_lifecycle_dropped_count"),
            "merge_grant_lifecycle_dropped_count",
        )
        == 0,
        "formal lifecycle evidence was truncated",
    )
    prefix_by_segment = {
        str(row["segment_id"]): row for row in prefix.rows
    }
    allowed_segments = set(prefix_by_segment)
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
    request_rows: dict[tuple[int, int], list[dict[str, Any]]] = {}
    grant_owner: dict[tuple[int, int], tuple[int, int]] = {}
    requested_rows = 0
    for index, raw in enumerate(lifecycle):
        require(
            set(raw) == set(LIFECYCLE_RUNTIME_FIELDS),
            f"lifecycle[{index}] field set drift",
        )
        segment = raw["segment_id"]
        require(
            isinstance(segment, str) and segment in allowed_segments,
            f"lifecycle[{index}] is not bound to the protected prefix",
        )
        source_row = prefix_by_segment[segment]
        require(
            _strict_int(raw["task_id"], "task_id")
            == int(source_row["task_id"])
            and _strict_int(raw["goal"], "goal") == int(source_row["goal"]),
            f"lifecycle[{index}] task/goal identity drift",
        )
        upstream = _strict_int(raw["upstream_node"], "upstream_node")
        destination = _strict_int(
            raw["destination_node"], "destination_node"
        )
        edge = (
            _strict_int(raw["edge_from_node"], "edge_from_node"),
            _strict_int(raw["edge_to_node"], "edge_to_node"),
        )
        require(edge == (upstream, destination), "grant edge identity drift")
        require(edge in real_edges, "lifecycle contains a non-map2 edge")
        require(
            destination in service_by_node,
            "lifecycle destination is not a map2 node",
        )
        expected_service = max(service_by_node[destination], 0.001)
        require(
            abs(
                _finite(
                    raw["destination_service_seconds"],
                    "destination_service_seconds",
                )
                - expected_service
            )
            <= 1.0e-9,
            "grant service duration is not the R3 map2 service expression",
        )
        _validate_exact_request_timing(
            raw,
            expected_travel=travel_by_edge[edge],
            expected_service=expected_service,
        )
        state = raw["state"]
        require(state in allowed_states, f"unknown lifecycle state: {state}")
        request_key = (
            destination,
            _strict_int(raw["request_id"], "request_id"),
        )
        request_rows.setdefault(request_key, []).append(dict(raw))
        if state == "REQUESTED":
            requested_rows += 1
        grant_id = _strict_int(raw["grant_id"], "grant_id")
        if grant_id > 0:
            grant_key = (destination, grant_id)
            prior_request = grant_owner.setdefault(grant_key, request_key)
            require(
                prior_request == request_key,
                f"grant {grant_key} was reused across requests",
            )
        require(
            _finite(raw["wait_age"], "wait_age") >= -1.0e-12,
            "wait age must be non-negative",
        )
    require(
        requested_rows
        == _strict_int(
            summary.get("merge_grant_request_count"),
            "merge_grant_request_count",
        ),
        "REQUESTED rows do not match merge request count",
    )
    terminal_states = {
        "CONSUMED",
        "EXPIRED",
        "REVOKED_FAULT",
        "REVOKED_STALE_STATE",
        "REVOKED_REPLAN_CURRENT_EDGE",
        "ROLLED_BACK",
    }
    for key, rows in request_rows.items():
        states = [str(row["state"]) for row in rows]
        require(states[0] == "REQUESTED", f"{key} does not begin REQUESTED")
        require(states[-1] in terminal_states, f"{key} lacks a terminal state")
        require(
            states.count("REQUESTED") == 1,
            f"{key} has duplicate REQUESTED transitions",
        )
        times = [_finite(row["time"], "time") for row in rows]
        ages = [_finite(row["wait_age"], "wait_age") for row in rows]
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
            field: rows[0][field] for field in REQUEST_IMMUTABLE_FIELDS
        }
        require(
            all(
                all(row[field] == value for field, value in immutable.items())
                for row in rows[1:]
            ),
            f"{key} immutable request identity changed across transitions",
        )
        for previous, current in zip(states, states[1:]):
            require(
                current in LEGAL_LIFECYCLE_SUCCESSORS.get(previous, set()),
                f"{key} illegal lifecycle transition {previous}->{current}",
            )
        granted = [
            row
            for row in rows
            if _strict_int(row["grant_id"], "grant_id") > 0
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
            require("ISSUED" in states, f"{key} grant lacks ISSUED transition")
            require(
                states.index("ISSUED")
                == next(
                    index
                    for index, row in enumerate(rows)
                    if _strict_int(row["grant_id"], "grant_id") > 0
                ),
                f"{key} grant identity appeared outside ISSUED",
            )
        if states[-1] == "CONSUMED":
            terminal = rows[-1]
            require(
                states == [
                    "REQUESTED",
                    "ISSUED",
                    "PREPARED",
                    "COMMITTED",
                    "CONSUMED",
                ],
                f"{key} consumed lifecycle is not exact",
            )
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


def validate_runtime_payload(
    payload: Mapping[str, Any],
    *,
    rule: str,
    prefix: g12.InputPrefix,
    real_edges: set[tuple[int, int]],
    travel_by_edge: Mapping[tuple[int, int], float],
    service_by_node: Mapping[int, float],
    expected_binary_path: Path,
    expected_binary_sha256: str,
) -> dict[str, Any]:
    summary = payload.get("summary")
    bags = payload.get("bags")
    lifecycle = payload.get("merge_grant_lifecycle")
    context = payload.get("trace_context")
    require(isinstance(summary, Mapping), "runtime payload.summary missing")
    require(
        isinstance(bags, list)
        and all(isinstance(row, Mapping) for row in bags),
        "runtime payload.bags missing",
    )
    require(
        isinstance(lifecycle, list)
        and all(isinstance(row, Mapping) for row in lifecycle),
        "runtime merge_grant_lifecycle missing",
    )
    require(isinstance(context, Mapping), "runtime trace_context missing")
    _validate_loaded_binary_identity(
        payload,
        summary,
        expected_binary_path=expected_binary_path,
        expected_binary_sha256=expected_binary_sha256,
    )
    runtime_echo_projection = _validate_frozen_runtime_echo(
        summary,
        context,
        rule=rule,
    )
    projection = _summary_projection(summary)
    require(summary["merge_grant_rule"] == rule, "merge rule echo drift")
    require(
        summary["merge_grant_rule_echo"] == rule,
        "merge rule request echo drift",
    )
    require(
        summary["event_semantics"]
        == "E4_batch_plus_destination_merge_request",
        "runtime did not execute production E4",
    )
    require(
        context.get("destination_merge_grant_enabled") is True,
        "trace context does not enable destination merge grants",
    )
    require(
        context.get("merge_grant_request_scope")
        == "current_one_hop_exact_directed_edge_only_no_future_route",
        "trace context one-hop boundary drift",
    )
    require(
        context.get("merge_grant_owner") == "destination_local_controller",
        "trace context destination ownership drift",
    )
    gates = _hard_gates(summary, expected_segments=PREFIX_SEGMENTS)
    failures = sorted(name for name, passed in gates.items() if not passed)
    require(not failures, f"{rule} hard gates failed: {','.join(failures)}")

    expected_segments = [str(row["segment_id"]) for row in prefix.rows]
    observed_segments = [str(row.get("segment_id", "")) for row in bags]
    require(
        len(bags) == PREFIX_SEGMENTS
        and len(set(observed_segments)) == PREFIX_SEGMENTS
        and set(observed_segments) == set(expected_segments),
        "runtime bag set does not equal protected 144 prefix",
    )
    require(
        all(row.get("completed") is True for row in bags),
        "runtime returned an incomplete bag",
    )
    require(
        all(
            _finite(
                row.get("merge_grant_wait_seconds"),
                "merge_grant_wait_seconds",
            )
            <= _finite(
                row.get("junction_queue_wait_seconds"),
                "junction_queue_wait_seconds",
            )
            + 1.0e-9
            for row in bags
        ),
        "merge grant wait is not a diagnostic subset of junction wait",
    )
    _validate_lifecycle(
        lifecycle,
        summary=summary,
        prefix=prefix,
        real_edges=real_edges,
        travel_by_edge=travel_by_edge,
        service_by_node=service_by_node,
    )

    completion = [
        _finite(row["finish_time"], "finish_time")
        - _finite(row["release_time"], "release_time")
        for row in bags
    ]
    require(all(value >= 0.0 for value in completion), "negative completion")
    grant_waits = [
        _finite(
            row["merge_grant_wait_seconds"], "merge_grant_wait_seconds"
        )
        for row in bags
    ]
    deadline_misses = sum(
        _finite(row["finish_time"], "finish_time")
        > _finite(row["deadline"], "deadline") + 1.0e-9
        for row in bags
    )
    busy, idle = _grant_slot_metrics(lifecycle)
    end_time = _finite(summary["end_time"], "end_time")
    consumed = _strict_int(
        summary["merge_grant_consumed_count"],
        "merge_grant_consumed_count",
    )
    committed_projection = [
        {
            "destination_node": row["destination_node"],
            "grant_id": row["grant_id"],
            "request_id": row["request_id"],
            "runtime_bag_id": row["runtime_bag_id"],
            "slot_start": row["slot_start"],
            "slot_end": row["slot_end"],
        }
        for row in lifecycle
        if row["state"] == "COMMITTED"
    ]
    bag_projection = [
        {
            key: row[key]
            for key in (
                "segment_id",
                "task_id",
                "runtime_bag_id",
                "release_time",
                "deadline",
                "finish_time",
                "junction_queue_wait_seconds",
                "merge_grant_wait_seconds",
                "completed",
                "failure_reason",
            )
        }
        for row in bags
    ]
    deterministic_projection = {
        "summary": projection,
        "runtime_echo": runtime_echo_projection,
        "bags": bag_projection,
        "lifecycle": [dict(row) for row in lifecycle],
    }
    return {
        "summary": dict(summary),
        "summary_projection": projection,
        "runtime_echo_projection": runtime_echo_projection,
        "bags": [dict(row) for row in bags],
        "lifecycle": [dict(row) for row in lifecycle],
        "hard_gates": gates,
        "metrics": {
            "end_time": end_time,
            "mean_completion_seconds": statistics.fmean(completion),
            "p95_completion_seconds": _p95(completion),
            "max_completion_seconds": max(completion),
            "mean_grant_wait_seconds": statistics.fmean(grant_waits),
            "max_grant_wait_seconds": max(grant_waits),
            "grant_slot_busy_seconds": busy,
            "grant_slot_idle_seconds": idle,
            "merge_throughput_per_second": (
                consumed / end_time if end_time > 0.0 else 0.0
            ),
            "incoming_edge_fairness_jain": _incoming_edge_fairness(
                lifecycle
            ),
            "deadline_miss_count": int(deadline_misses),
            "deadline_miss_rate": deadline_misses / len(bags),
        },
        "committed_order_sha256": canonical_sha256(committed_projection),
        "bag_projection_sha256": canonical_sha256(bag_projection),
        "lifecycle_projection_sha256": canonical_sha256(
            [dict(row) for row in lifecycle]
        ),
        "deterministic_result_sha256": canonical_sha256(
            deterministic_projection
        ),
    }


def execute_online_rules(
    *,
    executor: Callable[..., Mapping[str, Any]],
    prefix: g12.InputPrefix,
    binary: Path,
    search_path: Path,
    root: Path,
) -> dict[str, dict[str, Any]]:
    map_document = json.loads(
        (root / CANONICAL_MAP_PATH).read_text(encoding="utf-8")
    )
    real_edges = {
        (int(row["start"]), int(row["end"]))
        for row in map_document["edges"]
    }
    service_by_node = {
        int(row["location"]): float(row["service_time"])
        for row in map_document["nodes"]
    }
    travel_by_edge = {
        (int(row["start"]), int(row["end"])): float(row["travel_time"])
        for row in map_document["edges"]
    }
    binary = binary.resolve(strict=True)
    binary_sha256 = file_sha256(binary)
    results: dict[str, dict[str, Any]] = {}
    for rule in ONLINE_RULES:
        repeats: list[dict[str, Any]] = []
        for repeat_index in range(RUNTIME_REPEAT_COUNT):
            payload = executor(
                **_runtime_kwargs(
                    rule=rule,
                    prefix=prefix,
                    binary=binary,
                    search_path=search_path,
                    root=root,
                    repeat_index=repeat_index,
                )
            )
            require(
                isinstance(payload, Mapping),
                f"{rule} runtime returned a non-object payload",
            )
            repeats.append(
                validate_runtime_payload(
                    payload,
                    rule=rule,
                    prefix=prefix,
                    real_edges=real_edges,
                    travel_by_edge=travel_by_edge,
                    service_by_node=service_by_node,
                    expected_binary_path=binary,
                    expected_binary_sha256=binary_sha256,
                )
            )
        repeat_hashes = [
            str(result["deterministic_result_sha256"])
            for result in repeats
        ]
        require(
            len(set(repeat_hashes)) == 1,
            f"{rule} deterministic projection changed across independent repeats",
        )
        primary = repeats[0]
        primary["repeat_count"] = RUNTIME_REPEAT_COUNT
        primary["repeat_deterministic_sha256"] = repeat_hashes
        primary["repeat_determinism_pass"] = True
        results[rule] = primary
    return results


def execute_negative_rules(
    *,
    executor: Callable[..., Mapping[str, Any]],
    prefix: g12.InputPrefix,
    binary: Path,
    search_path: Path,
    root: Path,
) -> dict[str, dict[str, Any]]:
    evidence: dict[str, dict[str, Any]] = {}
    for rule in NEGATIVE_RULES:
        try:
            executor(
                **_runtime_kwargs(
                    rule=rule,
                    prefix=prefix,
                    binary=binary,
                    search_path=search_path,
                    root=root,
                )
            )
        except ValueError as exc:
            message = str(exc)
            require(rule in message or "M8/M9" in message, f"{rule} rejection")
            evidence[rule] = {
                "rule": rule,
                "online_allowed": False,
                "execution_status": "REJECTED_FAIL_CLOSED",
                "exception_type": type(exc).__name__,
                "message": message,
                "production_entrypoint": (
                    "czr005.cpp_backend."
                    "g4irsf11_event_runtime_from_records"
                ),
                "native_execution_started": False,
                "fail_closed": True,
            }
        else:
            raise ProtocolError(f"{rule} unexpectedly executed online")
    return evidence


def _run_id(
    rule: str,
    *,
    prefix: g12.InputPrefix,
    source_identity: Mapping[str, Any],
    binary_sha256: str,
) -> str:
    return canonical_sha256(
        {
            "schema": SCHEMA,
            "rule": rule,
            "controls": dict(FROZEN_CONTROLS),
            "prefix_sha256": prefix.prefix_sha256,
            "source_bundle_sha256": source_identity["bundle_sha256"],
            "binary_sha256": binary_sha256,
        }
    )[:24]


def _lifecycle_rows(
    results: Mapping[str, Mapping[str, Any]],
    *,
    prefix: g12.InputPrefix,
    source_identity: Mapping[str, Any],
    binary_sha256: str,
) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for rule in ONLINE_RULES:
        run_id = _run_id(
            rule,
            prefix=prefix,
            source_identity=source_identity,
            binary_sha256=binary_sha256,
        )
        lifecycle = results[rule]["lifecycle"]
        for index, event in enumerate(lifecycle):
            row = {
                "schema": SCHEMA,
                "rule": rule,
                "run_id": run_id,
                "transition_index": index,
                "input_selection_sha256": prefix.prefix_sha256,
                "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
                "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
                "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
                "source_bundle_sha256": source_identity["bundle_sha256"],
                "binary_sha256": binary_sha256,
                **{field: event[field] for field in LIFECYCLE_RUNTIME_FIELDS},
            }
            output.append(_sealed_row(row, LIFECYCLE_COLUMNS))
    return output


def _rule_ab_rows(
    results: Mapping[str, Mapping[str, Any]],
    negatives: Mapping[str, Mapping[str, Any]],
    *,
    prefix: g12.InputPrefix,
    source_identity: Mapping[str, Any],
    binary_sha256: str,
) -> list[dict[str, str]]:
    control = results[CONTROL_RULE]["metrics"]
    rows: list[dict[str, str]] = []
    for rule in ONLINE_RULES:
        result = results[rule]
        metrics = result["metrics"]
        summary = result["summary"]
        failures = sorted(
            name for name, passed in result["hard_gates"].items() if not passed
        )
        row = {
            "schema": SCHEMA,
            "rule": rule,
            "control_rule": CONTROL_RULE,
            "online_allowed": True,
            "execution_status": "EXECUTED_PRODUCTION_E4",
            "rejection_type": "",
            "rejection_message": "",
            "run_id": _run_id(
                rule,
                prefix=prefix,
                source_identity=source_identity,
                binary_sha256=binary_sha256,
            ),
            "segment_count": PREFIX_SEGMENTS,
            "raw_bag_count": prefix.raw_bag_count,
            "input_selection_sha256": prefix.prefix_sha256,
            "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
            "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "source_bundle_sha256": source_identity["bundle_sha256"],
            "binary_sha256": binary_sha256,
            "completed_count": summary["completed_count"],
            "failed_count": summary["failed_count"],
            "unresolved_deadlock_count": summary[
                "unresolved_deadlock_count"
            ],
            **metrics,
            "merge_request_count": summary["merge_grant_request_count"],
            "merge_committed_count": summary["merge_grant_committed_count"],
            "merge_consumed_count": summary["merge_grant_consumed_count"],
            "merge_request_expired_count": summary[
                "merge_grant_request_expired_count"
            ],
            "merge_grant_expired_count": summary[
                "merge_grant_grant_expired_count"
            ],
            "merge_revoked_count": summary["merge_grant_revoked_count"],
            "merge_peak_pending_requests": summary[
                "merge_grant_peak_pending_requests"
            ],
            "merge_peak_active_unconsumed": summary[
                "merge_grant_peak_active_unconsumed"
            ],
            "merge_contended_loser_retry_count": summary[
                "merge_grant_contended_loser_retry_count"
            ],
            "lifecycle_transition_count": summary[
                "merge_grant_lifecycle_transition_count"
            ],
            "lifecycle_stored_count": summary[
                "merge_grant_lifecycle_stored_count"
            ],
            "lifecycle_dropped_count": summary[
                "merge_grant_lifecycle_dropped_count"
            ],
            "repeat_count": result["repeat_count"],
            "repeat_deterministic_sha256": "|".join(
                result["repeat_deterministic_sha256"]
            ),
            "repeat_determinism_pass": result[
                "repeat_determinism_pass"
            ],
            "mean_completion_delta_vs_m0_seconds": (
                metrics["mean_completion_seconds"]
                - control["mean_completion_seconds"]
            ),
            "p95_completion_delta_vs_m0_seconds": (
                metrics["p95_completion_seconds"]
                - control["p95_completion_seconds"]
            ),
            "end_time_delta_vs_m0_seconds": (
                metrics["end_time"] - control["end_time"]
            ),
            "grant_wait_delta_vs_m0_seconds": (
                metrics["mean_grant_wait_seconds"]
                - control["mean_grant_wait_seconds"]
            ),
            "committed_order_sha256": result["committed_order_sha256"],
            "bag_projection_sha256": result["bag_projection_sha256"],
            "lifecycle_projection_sha256": result[
                "lifecycle_projection_sha256"
            ],
            "deterministic_result_sha256": result[
                "deterministic_result_sha256"
            ],
            "hard_gate_pass": not failures,
            "hard_gate_failures": "|".join(failures),
            "performance_gain_claimed": False,
            "promotion_status": PROMOTION_STATUS,
        }
        rows.append(_sealed_row(row, RULE_AB_COLUMNS))
    for rule in NEGATIVE_RULES:
        negative = negatives[rule]
        row = {
            "schema": SCHEMA,
            "rule": rule,
            "control_rule": CONTROL_RULE,
            "online_allowed": False,
            "execution_status": "REJECTED_FAIL_CLOSED",
            "rejection_type": negative["exception_type"],
            "rejection_message": negative["message"],
            "run_id": _run_id(
                rule,
                prefix=prefix,
                source_identity=source_identity,
                binary_sha256=binary_sha256,
            ),
            "segment_count": PREFIX_SEGMENTS,
            "raw_bag_count": prefix.raw_bag_count,
            "input_selection_sha256": prefix.prefix_sha256,
            "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
            "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "source_bundle_sha256": source_identity["bundle_sha256"],
            "binary_sha256": binary_sha256,
            "hard_gate_pass": False,
            "hard_gate_failures": "ONLINE_RULE_FORBIDDEN",
            "performance_gain_claimed": False,
            "promotion_status": "NOT_APPLICABLE_FAIL_CLOSED",
        }
        rows.append(_sealed_row(row, RULE_AB_COLUMNS))
    return rows


def _performance_conclusion(
    results: Mapping[str, Mapping[str, Any]],
) -> str:
    control = results[CONTROL_RULE]["metrics"]
    improved = [
        rule
        for rule in ONLINE_RULES
        if rule != CONTROL_RULE
        and results[rule]["metrics"]["mean_completion_seconds"]
        < control["mean_completion_seconds"] - 1.0e-12
        and results[rule]["metrics"]["p95_completion_seconds"]
        < control["p95_completion_seconds"] - 1.0e-12
    ]
    return (
        "DESCRIPTIVE_DIFFERENCE_ONLY_NOT_PROMOTION"
        if improved
        else "NO_RULE_IMPROVED_BOTH_MEAN_AND_P95_VS_M0_ON_144"
    )


def _report(
    results: Mapping[str, Mapping[str, Any]],
    negatives: Mapping[str, Mapping[str, Any]],
    *,
    prefix: g12.InputPrefix,
    source_identity: Mapping[str, Any],
    binary_sha256: str,
    binary_hint: str,
) -> str:
    conclusion = _performance_conclusion(results)
    peak_pending = max(
        int(results[rule]["summary"]["merge_grant_peak_pending_requests"])
        for rule in ONLINE_RULES
    )
    outcome_signatures = {
        canonical_sha256(
            {
                "metrics": results[rule]["metrics"],
                "committed_order_sha256": results[rule][
                    "committed_order_sha256"
                ],
                "bag_projection_sha256": results[rule][
                    "bag_projection_sha256"
                ],
                "lifecycle_projection_sha256": results[rule][
                    "lifecycle_projection_sha256"
                ],
            }
        )
        for rule in ONLINE_RULES
    }
    rule_outcomes_equal = len(outcome_signatures) == 1
    lines = [
        "# G4IRSF14 destination-owned merge-grant protocol",
        "",
        f"Status: `{STATUS}`",
        "",
        "This is production E4 mechanism evidence, not a standalone fixture. "
        "Every M0–M6 row was executed through the production Python/native "
        "entrypoint on the same protected map2 and the same unreordered first "
        "144 input rows. It is **not a performance promotion** and does not "
        "authorize a larger tier.",
        "",
        "## Frozen evidence identity",
        "",
        f"- map2 raw SHA-256: `{CANONICAL_MAP_RAW_SHA256}`",
        f"- map2 LF-semantic SHA-256: `{CANONICAL_MAP_SEMANTIC_SHA256}`",
        f"- inputdata raw/semantic SHA-256: `{CANONICAL_SOURCE_RAW_SHA256}`",
        f"- exact first-144 prefix SHA-256: `{prefix.prefix_sha256}`",
        f"- selected raw bag count: `{prefix.raw_bag_count}`",
        f"- runtime source bundle SHA-256: `{source_identity['bundle_sha256']}`",
        f"- loaded native binary: `{binary_hint}`",
        f"- loaded native binary SHA-256: `{binary_sha256}`",
        "",
        "Frozen runtime tuple: `R3/S1/P2/C0/Q0/E4`, scale `1`, no fault, "
        "reservation depth `1`, no future route, no global scan, and no "
        "runtime A*.",
        "The generator directly verifies the payload and summary loaded-binary "
        "path/SHA and the summary/trace echoes for this frozen tuple before "
        "admitting any run.",
        "",
        "## Same-input mechanism A/B",
        "",
        "M0 is the plan-defined current event-sequence / earliest-known "
        "control. Each M0–M6 rule was executed independently twice; the two "
        "deterministic runtime projections matched exactly before one complete "
        "lifecycle copy was published.",
        "",
        "| rule | complete | mean seconds | p95 seconds | mean grant wait | "
        "requests | consumed | hard gates |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for rule in ONLINE_RULES:
        result = results[rule]
        summary = result["summary"]
        metrics = result["metrics"]
        lines.append(
            "| {rule} | {complete}/{total} | {mean:.9g} | {p95:.9g} | "
            "{wait:.9g} | {requests} | {consumed} | PASS |".format(
                rule=rule,
                complete=summary["completed_count"],
                total=PREFIX_SEGMENTS,
                mean=metrics["mean_completion_seconds"],
                p95=metrics["p95_completion_seconds"],
                wait=metrics["mean_grant_wait_seconds"],
                requests=summary["merge_grant_request_count"],
                consumed=summary["merge_grant_consumed_count"],
            )
        )
    lines.extend(
        [
            "",
            f"Descriptive 144-prefix conclusion: `{conclusion}`. Exact "
            "deltas and per-run projection hashes are in "
            "`outputs/tables/g4irsf14_merge_rule_ab.csv`. Even a descriptive "
            "difference here is not independent replication, a promotion "
            "gate, or a full-scale result.",
            "",
            (
                "Observed mechanism-coverage limit: the maximum pending merge "
                f"request count was `{peak_pending}` and M0-M6 outcome "
                f"projections were exactly equal: "
                f"`{str(rule_outcomes_equal).lower()}`. With only one pending "
                "request at a time, this protected prefix did not elicit a "
                "rule-order divergence. These runs therefore prove the "
                "production grant path and complete lifecycle, not rule "
                "efficacy; native comparator and real-map tests cover the "
                "ordering semantics."
            ),
            "",
            "## Complete lifecycle and negative evidence",
            "",
            "The lifecycle CSV contains every stored production transition "
            "for all seven online runs. Every run reports "
            "`lifecycle_dropped_count=0`; request/grant identity is retained "
            "together with exact directed edge, exact destination service "
            "slot, queue/calendar/fault generations, observed consume-time "
            "state, reason, and terminal state.",
            "For every request, earliest edge entry equals request time, edge "
            "travel equals map2, projected arrival equals request plus travel, "
            "and each issued grant starts exactly at that arrival and expires "
            "exactly at its R3 slot end; future-shifted slots fail closed.",
            "",
        ]
    )
    for rule in NEGATIVE_RULES:
        lines.append(
            f"- `{rule}`: `{negatives[rule]['execution_status']}` — "
            f"`{negatives[rule]['message']}`"
        )
    lines.extend(
        [
            "",
            "M7 remains diagnostic-only. M8/M9 remain unavailable until a "
            "validated model artifact exists. No learned model is trained or "
            "promoted by Stage D.",
            "",
            "## Reproduction",
            "",
            "Run the generator with the exact native extension to be sealed:",
            "",
            "```text",
            "python scripts/eval/g4irsf14_merge_grant_protocol.py "
            "--binary <path-to-czr005_cpp-extension> "
            "--search-path <directory-containing-that-extension>",
            "python scripts/validate_g4irsf14_merge_grant_artifacts.py "
            "--binary <same-extension>",
            "```",
            "",
            "The validator rejects the obsolete standalone/withheld schema, "
            "any input/source/output hash drift, missing online or negative "
            "rules, truncated lifecycle rows, row self-hash drift, hard-gate "
            "failure, topology escape, or an unauthorized promotion claim.",
            "",
        ]
    )
    return "\n".join(lines)


def write_bundle(
    *,
    results: Mapping[str, Mapping[str, Any]],
    negatives: Mapping[str, Mapping[str, Any]],
    prefix: g12.InputPrefix,
    binary: Path,
    root: Path = ROOT,
    artifact_root: Path | None = None,
) -> dict[str, Any]:
    artifact_root = artifact_root or root
    source_identity = source_bundle(root)
    binary_sha256 = file_sha256(binary)
    binary_hint = _path_hint(binary, root)
    lifecycle_rows = _lifecycle_rows(
        results,
        prefix=prefix,
        source_identity=source_identity,
        binary_sha256=binary_sha256,
    )
    ab_rows = _rule_ab_rows(
        results,
        negatives,
        prefix=prefix,
        source_identity=source_identity,
        binary_sha256=binary_sha256,
    )
    lifecycle_bytes = _csv_bytes(LIFECYCLE_COLUMNS, lifecycle_rows)
    ab_bytes = _csv_bytes(RULE_AB_COLUMNS, ab_rows)
    report_bytes = _report(
        results,
        negatives,
        prefix=prefix,
        source_identity=source_identity,
        binary_sha256=binary_sha256,
        binary_hint=binary_hint,
    ).encode("utf-8")

    output_hashes = {
        REPORT_PATH.as_posix(): hashlib.sha256(report_bytes).hexdigest(),
        LIFECYCLE_PATH.as_posix(): hashlib.sha256(
            lifecycle_bytes
        ).hexdigest(),
        RULE_AB_PATH.as_posix(): hashlib.sha256(ab_bytes).hexdigest(),
    }
    manifest: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "generated_by": GENERATOR_PATH.as_posix(),
        "validated_by": VALIDATOR_PATH.as_posix(),
        "promotion_status": PROMOTION_STATUS,
        "performance_gain_claimed": False,
        "performance_conclusion": _performance_conclusion(results),
        "protected_inputs": {
            "map_path": CANONICAL_MAP_PATH,
            "map_raw_sha256": CANONICAL_MAP_RAW_SHA256,
            "map_semantic_sha256": CANONICAL_MAP_SEMANTIC_SHA256,
            "task_path": CANONICAL_SOURCE_PATH,
            "task_raw_sha256": CANONICAL_SOURCE_RAW_SHA256,
            "task_semantic_sha256": CANONICAL_SOURCE_SEMANTIC_SHA256,
            "map_topology_mutated": False,
            "task_rows_mutated": False,
        },
        "workload": {
            "selection": "first_144_nonempty_rows_without_reordering",
            "segment_count": PREFIX_SEGMENTS,
            "raw_bag_count": prefix.raw_bag_count,
            "prefix_sha256": prefix.prefix_sha256,
            "segment_ids_sha256": canonical_sha256(
                [str(row["segment_id"]) for row in prefix.rows]
            ),
            "first_segment_id": prefix.first_segment_id,
            "last_segment_id": prefix.last_segment_id,
        },
        "frozen_controls": dict(FROZEN_CONTROLS),
        "boundary": dict(BOUNDARY),
        "online_rules": list(ONLINE_RULES),
        "control_rule": CONTROL_RULE,
        "negative_rules": list(NEGATIVE_RULES),
        "negative_rule_evidence": {
            rule: dict(negatives[rule]) for rule in NEGATIVE_RULES
        },
        "source_bundle": source_identity,
        "binary": {
            "path_hint": binary_hint,
            "sha256": binary_sha256,
        },
        "runs": {
            rule: {
                "run_id": _run_id(
                    rule,
                    prefix=prefix,
                    source_identity=source_identity,
                    binary_sha256=binary_sha256,
                ),
                "repeat_count": results[rule]["repeat_count"],
                "repeat_deterministic_sha256": list(
                    results[rule]["repeat_deterministic_sha256"]
                ),
                "repeat_determinism_pass": results[rule][
                    "repeat_determinism_pass"
                ],
                "hard_gates": dict(results[rule]["hard_gates"]),
                "summary_projection": dict(
                    results[rule]["summary_projection"]
                ),
                "runtime_echo_projection": {
                    scope: dict(values)
                    for scope, values in results[rule][
                        "runtime_echo_projection"
                    ].items()
                },
                "metrics": dict(results[rule]["metrics"]),
                "committed_order_sha256": results[rule][
                    "committed_order_sha256"
                ],
                "bag_projection_sha256": results[rule][
                    "bag_projection_sha256"
                ],
                "lifecycle_projection_sha256": results[rule][
                    "lifecycle_projection_sha256"
                ],
                "deterministic_result_sha256": results[rule][
                    "deterministic_result_sha256"
                ],
            }
            for rule in ONLINE_RULES
        },
        "output_sha256": output_hashes,
        "reproduction": {
            "generate": (
                "python scripts/eval/g4irsf14_merge_grant_protocol.py "
                "--binary <path-to-czr005_cpp-extension> "
                "--search-path <extension-directory>"
            ),
            "validate": (
                "python scripts/validate_g4irsf14_merge_grant_artifacts.py "
                "--binary <same-extension>"
            ),
        },
    }
    manifest["self_sha256"] = canonical_sha256(manifest)
    config_bytes = canonical_json_bytes(manifest) + b"\n"

    _atomic_write(artifact_root / REPORT_PATH, report_bytes)
    _atomic_write(artifact_root / LIFECYCLE_PATH, lifecycle_bytes)
    _atomic_write(artifact_root / RULE_AB_PATH, ab_bytes)
    _atomic_write(artifact_root / CONFIG_PATH, config_bytes)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary",
        type=Path,
        required=True,
        help="exact czr005_cpp extension whose bytes will be sealed",
    )
    parser.add_argument(
        "--search-path",
        type=Path,
        default=None,
        help="directory containing --binary (defaults to its parent)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="execute and validate every rule without replacing artifacts",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT,
        help="artifact root (defaults to the repository root)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    binary, search_path = resolve_binary(
        args.binary, search_path=args.search_path
    )
    g12.assert_fixed_identity(ROOT)
    prefix = g12.load_input_prefix(PREFIX_SEGMENTS, root=ROOT)
    initial_source_identity = source_bundle(ROOT)
    initial_binary_sha256 = file_sha256(binary)
    results = execute_online_rules(
        executor=cpp_backend.g4irsf11_event_runtime_from_records,
        prefix=prefix,
        binary=binary,
        search_path=search_path,
        root=ROOT,
    )
    negatives = execute_negative_rules(
        executor=cpp_backend.g4irsf11_event_runtime_from_records,
        prefix=prefix,
        binary=binary,
        search_path=search_path,
        root=ROOT,
    )
    require(
        source_bundle(ROOT) == initial_source_identity,
        "SOURCE_BUNDLE_DRIFT_DURING_EXECUTION",
    )
    require(
        file_sha256(binary) == initial_binary_sha256,
        "NATIVE_BINARY_DRIFT_DURING_EXECUTION",
    )
    if args.dry_run:
        print(
            "G4IRSF14 Stage-D dry run valid:",
            f"rules={','.join(ONLINE_RULES)}",
            f"segments={PREFIX_SEGMENTS}",
            "artifacts=NOT_WRITTEN",
        )
        return 0
    manifest = write_bundle(
        results=results,
        negatives=negatives,
        prefix=prefix,
        binary=binary,
        root=ROOT,
        artifact_root=args.output_root,
    )
    print(
        "G4IRSF14 Stage-D evidence generated:",
        f"rules={','.join(ONLINE_RULES)}",
        f"segments={PREFIX_SEGMENTS}",
        f"status={manifest['status']}",
        f"self_sha256={manifest['self_sha256']}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
