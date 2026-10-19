#!/usr/bin/env python3
"""Fail-closed Stage-14E opportunity census on the protected original task.

This module deliberately produces a blocker artifact, not causal labels.  It
combines:

* one exact-binary three-way no-op checkpoint replay for the five production
  replay hashes;
* one passive opportunity-telemetry run for complete I1 source-ready support;
* one bounded trace run for conservative I3/I4 screening lower bounds; and
* raw destination-merge and P2 counters for strict I2/I5 support decisions.

No H_bag or H_system intervention is executed here.  Consequently the only
admissible publication status is ``PARTIAL_WITH_EXPLICIT_BLOCKER``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import struct
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap_path in (ROOT, ROOT / "src"):
    _bootstrap_text = str(_bootstrap_path)
    if _bootstrap_text not in sys.path:
        sys.path.insert(0, _bootstrap_text)

from scripts.eval import g4irsf12_reproducible_harness as g12
from scripts.eval.g4irsf11_fixed_map import (
    assert_canonical_map,
    canonical_graph_records,
)


OUTPUT_PATH = Path("outputs/tables/g4irsf14_opportunity_census.json")
REPORT_PATH = Path(
    "outputs/reports/g4irsf14_matched_state_clone_report.md"
)
CLONE_FIDELITY_PATH = Path(
    "outputs/tables/g4irsf14_clone_fidelity.csv"
)
CAUSAL_INTERVENTIONS_PATH = Path(
    "outputs/tables/g4irsf14_causal_interventions.csv"
)
COMPONENT_LEDGER_PATH = Path(
    "outputs/tables/g4irsf14_causal_component_ledger.csv"
)
CLONE_MANIFEST_PATH = Path(
    "artifacts/datasets/g4irsf14_clone_manifest.json"
)
MAP_PATH = Path("data/processed/maps/map2.json")
TASK_PATH = Path("data/processed/tasks/inputdata.jsonl")
MODEL_PATH = Path("artifacts/models/g4e_risk_calibrated_policy.json")

SCHEMA = "czr005.g4irsf14.opportunity_census.v1"
STATUS = "PARTIAL_WITH_EXPLICIT_BLOCKER"
EVIDENCE_SCOPE = (
    "ORIGINAL_1X_OPPORTUNITY_SUPPORT_AND_BLOCKER_ONLY_"
    "NOT_CAUSAL_LABEL_EVIDENCE"
)
FORMAL_BLOCKER_CODE = (
    "MISSING_EXACT_BINARY_I1_I5_ONE_SHOT_RERUN_AND_"
    "ORIGINAL_TASK_2000_H_SYSTEM_FORMAL_EVIDENCE"
)
BUNDLE_EVIDENCE_SCOPE = (
    "STAGE_14E_BLOCKER_AUDIT_BUNDLE_NOT_FORMAL_CAUSAL_LABEL_EVIDENCE"
)
MANIFEST_SCHEMA = "czr005.g4irsf14.blocker_bundle_manifest.v1"
REPORT_SCHEMA = "czr005.g4irsf14.matched_state_clone_blocker_report.v1"
CLONE_FIDELITY_SCHEMA = "czr005.g4irsf14.clone_fidelity_audit.v1"
CAUSAL_INTERVENTIONS_SCHEMA = (
    "czr005.g4irsf14.causal_interventions_blocker_header.v1"
)
COMPONENT_LEDGER_SCHEMA = (
    "czr005.g4irsf14.causal_component_support_ledger.v1"
)

FULL_SEGMENT_COUNT = 43_603
FULL_RAW_BAG_COUNT = 28_506
MAP_RAW_SHA256 = (
    "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
)
MAP_SEMANTIC_SHA256 = (
    "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
)
TASK_RAW_SHA256 = (
    "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"
)
TASK_SEMANTIC_SHA256 = TASK_RAW_SHA256
MODEL_SHA256 = (
    "4a058dee0bdd17e15f67d1943a551822847d0c066ac3cf03a5da71a07731bbca"
)

OPPORTUNITY_TRACE_LIMIT = 100_000
DECISION_TRACE_LIMIT = 100_000
CLONE_EVENT_ORDINAL = 1_000
MIN_FORMAL_INTERVENTIONS = 2_000

REPLAY_HASH_FIELDS = (
    "complete_bags_sha256",
    "segment_result_sha256",
    "junction_state_sha256",
    "algorithm_summary_sha256",
    "deterministic_result_sha256",
)

SOURCE_PATHS = (
    Path("CMakeLists.txt"),
    Path("scripts/eval/g4irsf14_opportunity_census.py"),
    Path("scripts/eval/g4irsf12_reproducible_harness.py"),
    Path("scripts/eval/g4irsf11_fixed_map.py"),
    Path("scripts/eval/g4irsf14_state_clone_validation.py"),
    Path("scripts/validate_g4irsf14_state_clone_artifacts.py"),
    Path("src/czr005/cpp_backend.py"),
    Path("cpp/ics_core/bindings/czr005_cpp.cpp"),
    Path("cpp/ics_core/runtime/event_driven_junction.hpp"),
    Path("cpp/ics_core/runtime/destination_merge_grant.hpp"),
    Path("cpp/ics_core/runtime/g4irsf14_causal_intervention.hpp"),
    Path("cpp/ics_core/runtime/g4irsf14_state_clone.hpp"),
    Path("cpp/ics_core/runtime/bounded_local_pibt.hpp"),
    MODEL_PATH,
)

# Every runtime control that could affect the live execution is explicit.
# The two census passes vary only trace/telemetry storage.
FROZEN_RUNTIME_CONTROLS: Mapping[str, Any] = {
    "queue_discipline": "aging",
    "retry_interval": 0.25,
    "minimum_service_seconds": 0.001,
    "dispatch_headway_seconds": 0.001,
    "history_limit": 8,
    "max_decisions_per_bag": 512,
    "max_events": 20_000_000,
    "max_simulation_time": -1.0,
    "trace_shard_count": 1,
    "trace_shard_index": 0,
    "local_queue_capacity": 32,
    "deadlock_retry_threshold": 8,
    "diagnostic_hops": 2,
    "enable_source_admission": False,
    "enable_backpressure": False,
    "enable_pibt_lite": False,
    "enable_deadlock_escape": True,
    "enable_fault_policy": True,
    "scale": 1.0,
    "resource_semantics": "R3_java_node_window_compatible",
    "entry_headway_seconds": 0.001,
    "pressure_mode": "off",
    "pressure_weight": 2.0,
    "pressure_age_weight": 0.05,
    "pressure_distance_bias": 0.25,
    "admission_mode": "off",
    "credit_validity_seconds": 1.0,
    "credit_snapshot_max_age_seconds": 1.0,
    "credit_capacity_per_edge": 1,
    "credit_lifecycle_limit": 512,
    "pibt_mode": "P2",
    "pibt_max_depth": 2,
    "pibt_max_ready_bags": 8,
    "pibt_max_local_resources": 32,
    "pibt_max_candidates_per_bag": 8,
    "scorer_mode": "S1_frozen_g4e_legal_local_adapter",
    "framework_mode": "event_loop_one_step",
    "event_trace_limit": 0,
    "priority_mode": "Q0",
    "pibt_preference_mode": "current",
    "pibt_regret_prior_records": [],
    "selective_credit_contention_threshold": 1,
    "event_semantics": "E4_batch_plus_destination_merge_request",
    "merge_grant_rule": "M0",
    "merge_grant_max_pending_requests": 256,
    "merge_grant_lifecycle_limit": 8192,
}

CLONE_FROZEN_CONTROLS: Mapping[str, Any] = {
    "resource_semantics": "R3_java_node_window_compatible",
    "scorer_mode": "S1_frozen_g4e_legal_local_adapter",
    "pibt_mode": "P2",
    "admission_mode": "off",
    "pressure_mode": "off",
    "priority_mode": "Q0",
    "event_semantics": "E4_batch_plus_destination_merge_request",
    "merge_grant_rule": "M0",
    "scale": 1.0,
    "reservation_depth": 1,
    "max_events": 20_000_000,
    "max_simulation_time": -1.0,
    "trace_limit": 0,
    "event_trace_limit": 0,
}

RAW_HARD_GATE_FIELDS = (
    "requested_count",
    "completed_count",
    "failed_count",
    "event_count",
    "physical_fault_edge_entry_violation_count",
    "reservation_conflicts",
    "runtime_full_astar_calls",
    "global_reservation_scan_count",
    "priority_global_scan_count",
    "scorer_runtime_global_scan_count",
    "microphase_runtime_global_scan_count",
    "first_edge_credit_global_scan_count",
    "priority_future_route_input_count",
    "scorer_future_route_input_count",
    "first_edge_credit_future_route_count",
    "scorer_future_schedule_input_count",
    "priority_teacher_input_count",
    "scorer_teacher_input_count",
    "full_future_routes_stored",
    "bag_future_path_field_present",
    "max_edges_selected_per_bag_per_decision",
    "two_step_reservation_count",
    "unresolved_deadlock_count",
    "event_limit_reached",
    "time_limit_reached",
    "merge_grant_stale_arbitration_count",
    "stale_arbitration_event_count",
    "artificial_batch_delay_seconds",
    "merge_grant_conservation_holds",
    "merge_grant_active_bijection_holds",
    "merge_grant_runtime_owned_capability",
    "merge_grant_exact_slot_no_future_shift",
    "merge_grant_final_active_unconsumed",
    "merge_grant_outstanding_request_count",
    "merge_grant_lifecycle_dropped_count",
    "merge_grant_lifecycle_complete",
    "merge_grant_protocol_integrity_pass",
)

I2_RAW_COUNTER_FIELDS = (
    "g4irsf14_i2_live_eligible_multi_request_boundary_count",
    "merge_grant_request_count",
    "destination_merge_arbitration_event_count",
    "merge_grant_peak_pending_requests",
    "merge_grant_contended_loser_retry_count",
    "merge_grant_request_expired_count",
    "merge_grant_grant_expired_count",
    "merge_grant_active_grant_rejection_count",
    "merge_grant_exact_slot_busy_count",
    "merge_grant_queue_capacity_block_count",
    "merge_grant_duplicate_wakeup_prevented_count",
    "merge_grant_stale_arbitration_count",
    "merge_grant_terminal_request_count",
    "merge_grant_outstanding_request_count",
)

P2_RAW_COUNTER_FIELDS = (
    "g4irsf14_i5_prefilter_candidate_count",
    "g4irsf14_i5_applicable_ready_slice_boundary_count",
    "merge_grant_queue_capacity_block_count",
    "bounded_local_pibt_activation_count",
    "bounded_local_pibt_not_applicable_count",
    "bounded_local_pibt_attempt_count",
    "bounded_local_pibt_prepare_count",
    "bounded_local_pibt_validate_count",
    "bounded_local_pibt_commit_count",
    "bounded_local_pibt_proposal_batch_count",
    "bounded_local_pibt_proposed_action_count",
    "bounded_local_pibt_committed_batch_count",
    "bounded_local_pibt_committed_action_count",
    "bounded_local_pibt_inherited_action_count",
    "bounded_local_pibt_blocker_move_attempt_count",
    "bounded_local_pibt_backtrack_count",
    "bounded_local_pibt_cycle_guard_count",
    "bounded_local_pibt_rollback_count",
    "bounded_local_pibt_max_inheritance_depth",
    "bounded_local_pibt_max_slice_bags",
    "bounded_local_pibt_max_slice_resources",
    "bounded_local_pibt_max_candidates_per_bag",
)

DETERMINISTIC_CORE_SUMMARY_FIELDS = (
    "requested_count",
    "completed_count",
    "failed_count",
    "event_count",
    "end_time",
    "decision_trace_seen_count",
    *RAW_HARD_GATE_FIELDS[4:],
    *I2_RAW_COUNTER_FIELDS,
    *P2_RAW_COUNTER_FIELDS,
)

CLONE_FIDELITY_FIELDS = (
    "audit_schema",
    "status",
    "evidence_scope",
    "formal_pass_claimed",
    "causal_label_count",
    "bundle_generation_id",
    "census_self_sha256",
    "binary_path",
    "binary_sha256",
    "clone_event_ordinal",
    "intervention_applied",
    "source_baseline_exact_match",
    "source_clone_exact_match",
    "baseline_clone_exact_match",
    *REPLAY_HASH_FIELDS,
    "all_five_replay_hashes_exact_match",
    "clone_replay_fidelity",
)

CAUSAL_INTERVENTION_FIELDS = (
    "audit_schema",
    "status",
    "formal_pass_claimed",
    "census_self_sha256",
    "intervention_id",
    "intervention_type",
    "checkpoint_runtime_state_sha256",
    "baseline_action",
    "selected_action",
    "horizon",
    "delta_affected_bag_completion",
    "delta_local_group_delay",
    "delta_system_mean",
    "delta_system_p95",
    "delta_system_p99",
    "delta_source_wait",
    "delta_network_wait",
    "delta_path_length",
    "delta_grant_wait",
    "delta_deadline_miss",
    "safety_equivalent",
    "causal_label",
)

COMPONENT_LEDGER_FIELDS = (
    "audit_schema",
    "status",
    "evidence_scope",
    "formal_pass_claimed",
    "causal_label_count",
    "bundle_generation_id",
    "census_self_sha256",
    "component",
    "intervention_type",
    "screening_support_count",
    "formal_matched_boundary_count",
    "formal_horizon_completion_count",
    "prefilter_without_applicable_slice_count",
    "lower_bound_only",
    "support_status",
    "causal_contribution_status",
)

BUNDLE_PATHS = {
    "opportunity_census": OUTPUT_PATH,
    "matched_state_clone_report": REPORT_PATH,
    "clone_fidelity": CLONE_FIDELITY_PATH,
    "causal_interventions": CAUSAL_INTERVENTIONS_PATH,
    "causal_component_ledger": COMPONENT_LEDGER_PATH,
}


class OpportunityCensusError(RuntimeError):
    """Raised before publication when census evidence is not admissible."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OpportunityCensusError(message)


def _is_portable_absolute_path(value: str) -> bool:
    """Recognize absolute provenance paths independent of the validator OS."""

    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
    )


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
    _require(path.is_file(), f"missing hash-bound file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_text_sha256(path: Path) -> str:
    _require(path.is_file(), f"missing semantic source file: {path}")
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OpportunityCensusError(
            f"source file is not strict UTF-8: {path}"
        ) from exc
    normalized = text.replace("\r\n", "\n")
    _require("\r" not in normalized, f"source contains unsupported lone CR: {path}")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _display_path(path: Path, root: Path) -> str:
    resolved = path.resolve(strict=True)
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def source_bundle_identity(
    root: Path = ROOT,
    source_paths: Sequence[Path] = SOURCE_PATHS,
) -> dict[str, Any]:
    _require(bool(source_paths), "source bundle cannot be empty")
    rows = []
    for raw_path in source_paths:
        path = raw_path if raw_path.is_absolute() else root / raw_path
        rows.append(
            {
                "path": _display_path(path, root),
                "semantic_sha256": semantic_text_sha256(path),
            }
        )
    rows.sort(key=lambda row: row["path"])
    _require(
        len({row["path"] for row in rows}) == len(rows),
        "source bundle paths must be unique",
    )
    return {
        "hash_mode": "sha256_utf8_after_crlf_to_lf_reject_lone_cr",
        "files": rows,
        "path_manifest_sha256": canonical_sha256(
            [row["path"] for row in rows]
        ),
        "bundle_sha256": canonical_sha256(rows),
    }


def _protected_input_identity(root: Path) -> dict[str, Any]:
    map_path = (root / MAP_PATH).resolve(strict=True)
    task_path = (root / TASK_PATH).resolve(strict=True)
    fixed = g12.assert_fixed_identity(root)
    _require(
        file_sha256(map_path) == MAP_RAW_SHA256,
        "protected map raw SHA-256 drift",
    )
    _require(
        semantic_text_sha256(map_path) == MAP_SEMANTIC_SHA256,
        "protected map semantic SHA-256 drift",
    )
    _require(
        file_sha256(task_path) == TASK_RAW_SHA256,
        "protected task raw SHA-256 drift",
    )
    _require(
        semantic_text_sha256(task_path) == TASK_SEMANTIC_SHA256,
        "protected task semantic SHA-256 drift",
    )
    _require(
        fixed.get("source_row_count") == FULL_SEGMENT_COUNT,
        "protected task segment count drift",
    )
    _require(
        fixed.get("source_bag_count") == FULL_RAW_BAG_COUNT,
        "protected task raw bag count drift",
    )
    return {
        "map": {
            "path": MAP_PATH.as_posix(),
            "raw_sha256": MAP_RAW_SHA256,
            "semantic_sha256": MAP_SEMANTIC_SHA256,
        },
        "task": {
            "path": TASK_PATH.as_posix(),
            "raw_sha256": TASK_RAW_SHA256,
            "semantic_sha256": TASK_SEMANTIC_SHA256,
            "segment_count": FULL_SEGMENT_COUNT,
            "raw_bag_count": FULL_RAW_BAG_COUNT,
        },
    }


def execution_identity(
    *,
    binary: Path,
    root: Path,
    source_paths: Sequence[Path] = SOURCE_PATHS,
) -> dict[str, Any]:
    resolved = binary.resolve(strict=True)
    return {
        "binary": {
            "path": str(resolved),
            "sha256": file_sha256(resolved),
        },
        "protected_inputs": _protected_input_identity(root),
        "source_bundle": source_bundle_identity(root, source_paths),
    }


def _assert_execution_identity(
    expected: Mapping[str, Any],
    *,
    binary: Path,
    root: Path,
    source_paths: Sequence[Path],
    phase: str,
) -> None:
    observed = execution_identity(
        binary=binary, root=root, source_paths=source_paths
    )
    if observed != dict(expected):
        raise OpportunityCensusError(
            f"EXECUTION_IDENTITY_DRIFT:{phase}"
        )


def _strict_int(value: Any, label: str) -> int:
    _require(
        isinstance(value, int) and not isinstance(value, bool),
        f"{label} must be an integer",
    )
    return int(value)


def _strict_nonnegative_int(value: Any, label: str) -> int:
    result = _strict_int(value, label)
    _require(result >= 0, f"{label} must be nonnegative")
    return result


def _strict_bool(value: Any, label: str) -> bool:
    _require(isinstance(value, bool), f"{label} must be boolean")
    return bool(value)


def _finite(value: Any, label: str) -> float:
    _require(
        isinstance(value, (int, float)) and not isinstance(value, bool),
        f"{label} must be numeric",
    )
    result = float(value)
    _require(math.isfinite(result), f"{label} must be finite")
    return result


def _mapping(value: Any, label: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object")
    return {str(key): child for key, child in value.items()}


def _array(value: Any, label: str) -> list[Any]:
    _require(isinstance(value, list), f"{label} must be an array")
    return value


def _require_sha256(value: Any, label: str) -> str:
    _require(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value),
        f"{label} must be a lowercase SHA-256",
    )
    return value


def _double_bits(value: Any, label: str) -> int:
    floating = _finite(value, label)
    return struct.unpack(">Q", struct.pack(">d", floating))[0]


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        allow_nan=False,
    ).encode("utf-8") + b"\n"
    _atomic_write_bytes(path, payload)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
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


def _json_file_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _csv_file_bytes(
    fields: Sequence[str],
    rows: Sequence[Mapping[str, Any]],
) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(fields),
        extrasaction="raise",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        _require(
            set(row) == set(fields),
            "CSV row key inventory mismatch",
        )
        writer.writerow(row)
    return stream.getvalue().encode("utf-8")


def _bytes_sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_write_bundle(
    payloads: Mapping[Path, bytes],
    *,
    commit_path: Path,
) -> None:
    """Publish a multi-file bundle with a manifest-last commit marker.

    Every payload is staged and flushed before the first target is replaced.
    The manifest is replaced last, so any concurrently observed intermediate
    state is fail-closed under the manifest SHA bindings.  A failed replace
    restores every already-replaced target to its prior bytes.
    """

    normalized = {path.resolve(): bytes(data) for path, data in payloads.items()}
    commit = commit_path.resolve()
    _require(commit in normalized, "bundle commit manifest payload is missing")
    _require(
        len(normalized) == len(payloads),
        "bundle target paths are not unique",
    )
    staged: dict[Path, Path] = {}
    prior: dict[Path, bytes | None] = {}
    replaced: list[Path] = []
    try:
        for target, payload in normalized.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            prior[target] = target.read_bytes() if target.is_file() else None
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{target.name}.",
                suffix=".bundle.tmp",
                dir=str(target.parent),
            )
            temporary = Path(temporary_name)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            staged[target] = temporary
        order = sorted(
            (target for target in normalized if target != commit),
            key=lambda target: str(target),
        )
        order.append(commit)
        for target in order:
            os.replace(staged[target], target)
            replaced.append(target)
    except BaseException as exc:
        rollback_failures: list[str] = []
        for target in reversed(replaced):
            try:
                previous = prior[target]
                if previous is None:
                    target.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(target, previous)
            except BaseException as rollback_exc:
                rollback_failures.append(
                    f"{target}:{type(rollback_exc).__name__}"
                )
        detail = (
            ""
            if not rollback_failures
            else ":ROLLBACK_FAILED:" + ",".join(rollback_failures)
        )
        raise OpportunityCensusError(
            f"BUNDLE_PUBLICATION_FAILED:{type(exc).__name__}{detail}"
        ) from exc
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)


def _resolve_binary(binary: Path, search_path: Path | None) -> tuple[Path, Path]:
    resolved = binary.resolve(strict=True)
    _require(
        resolved.suffix.lower() in {".pyd", ".so", ".dylib"},
        "native binary must be a Python extension",
    )
    directory = (
        search_path.resolve(strict=True)
        if search_path is not None
        else resolved.parent
    )
    _require(
        directory == resolved.parent,
        "search path must be exactly the native binary parent",
    )
    return resolved, directory


def _runtime_request(
    *,
    node_records: Sequence[Any],
    edge_records: Sequence[Any],
    heuristic_time: Sequence[Any],
    bag_records: Sequence[Any],
    binary: Path,
    search_path: Path,
    model_path: Path,
    mode: str,
    opportunity_trace_limit: int,
    decision_trace_limit: int,
) -> dict[str, Any]:
    _require(mode in {"opportunity", "decision"}, "unknown census run mode")
    request = {
        **dict(FROZEN_RUNTIME_CONTROLS),
        "node_records": node_records,
        "edge_records": edge_records,
        "heuristic_time": heuristic_time,
        "bag_records": bag_records,
        "fault_windows": [],
        "scenario": f"g4irsf14_opportunity_census_{mode}_original_1x",
        "summary_only": False,
        "expected_binary_path": binary,
        "search_path": search_path,
        "scorer_model_path": model_path,
        "trace_limit": 0 if mode == "opportunity" else decision_trace_limit,
        "enable_opportunity_telemetry": mode == "opportunity",
        "opportunity_trace_limit": (
            opportunity_trace_limit if mode == "opportunity" else 0
        ),
    }
    return request


def _clone_request(
    *,
    node_records: Sequence[Any],
    edge_records: Sequence[Any],
    heuristic_time: Sequence[Any],
    bag_records: Sequence[Any],
    binary: Path,
    search_path: Path,
    model_path: Path,
    clone_event_ordinal: int,
) -> dict[str, Any]:
    return {
        "node_records": node_records,
        "edge_records": edge_records,
        "heuristic_time": heuristic_time,
        "bag_records": bag_records,
        "preregistered_event_ordinal": clone_event_ordinal,
        "scorer_model_path": model_path,
        "expected_binary_path": binary,
        "search_path": search_path,
    }


def _call_checked(
    executor: Callable[..., Mapping[str, Any]],
    request: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    binary: Path,
    root: Path,
    source_paths: Sequence[Path],
    phase: str,
) -> dict[str, Any]:
    _assert_execution_identity(
        identity,
        binary=binary,
        root=root,
        source_paths=source_paths,
        phase=f"{phase}:before",
    )
    try:
        result = executor(**dict(request))
    except OpportunityCensusError:
        raise
    except Exception as exc:
        raise OpportunityCensusError(
            f"EXECUTOR_FAILED:{phase}:{type(exc).__name__}:{exc}"
        ) from exc
    _assert_execution_identity(
        identity,
        binary=binary,
        root=root,
        source_paths=source_paths,
        phase=f"{phase}:after",
    )
    return _mapping(result, f"{phase} executor result")


def _validate_binary_echo(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    binary: Mapping[str, Any],
    label: str,
) -> None:
    expected_path = str(binary["path"])
    expected_sha = str(binary["sha256"])
    for owner, value in (("payload", payload), ("summary", summary)):
        observed_path = value.get("loaded_cpp_binary_path")
        observed_sha = value.get("loaded_cpp_binary_sha256")
        _require(
            isinstance(observed_path, str)
            and os.path.normcase(str(Path(observed_path).resolve()))
            == os.path.normcase(str(Path(expected_path).resolve())),
            f"{label} {owner} binary path echo mismatch",
        )
        _require(
            observed_sha == expected_sha,
            f"{label} {owner} binary SHA echo mismatch",
        )


def _validate_frozen_echo(
    summary: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    opportunity_enabled: bool,
    opportunity_limit: int,
    label: str,
) -> None:
    expected_trace_limit = (
        0 if opportunity_enabled else DECISION_TRACE_LIMIT
    )
    summary_expected = {
        "resource_semantics_id": FROZEN_RUNTIME_CONTROLS[
            "resource_semantics"
        ],
        "resource_semantics_echo": FROZEN_RUNTIME_CONTROLS[
            "resource_semantics"
        ],
        "scorer_mode": FROZEN_RUNTIME_CONTROLS["scorer_mode"],
        "scorer_mode_echo": FROZEN_RUNTIME_CONTROLS["scorer_mode"],
        "scorer_model_sha256": MODEL_SHA256,
        "pibt_mode": "P2",
        "pibt_mode_echo": "P2",
        "pibt_max_depth": 2,
        "pibt_max_ready_bags": 8,
        "pibt_max_local_resources": 32,
        "pibt_max_candidates_per_bag": 8,
        "pibt_mode_diagnostic_only": False,
        "framework_mode": "event_loop_one_step",
        "framework_mode_echo": "event_loop_one_step",
        "framework_diagnostic_only": False,
        "pressure_mode": "C0_off",
        "pressure_mode_echo": "off",
        "pressure_weight": 2.0,
        "pressure_age_weight": 0.05,
        "pressure_distance_bias": 0.25,
        "admission_mode": "off",
        "admission_mode_echo": "off",
        "source_admission_enabled": False,
        "fault_policy_enabled": True,
        "legacy_pibt_lite_enabled": False,
        "credit_mode": "C0",
        "credit_validity_seconds": 1.0,
        "credit_snapshot_max_age_seconds": 1.0,
        "credit_capacity_per_edge": 1,
        "credit_lifecycle_limit": 512,
        "selective_credit_contention_threshold": 1,
        "priority_mode": "Q0",
        "priority_mode_echo": "Q0",
        "pibt_preference_mode": "current",
        "pibt_preference_mode_echo": "current",
        "pibt_regret_prior_record_count": 0,
        "event_semantics": "E4_batch_plus_destination_merge_request",
        "event_semantics_echo": "E4_batch_plus_destination_merge_request",
        "merge_grant_rule": "M0",
        "merge_grant_rule_echo": "M0",
        "merge_grant_max_pending_requests": 256,
        "merge_grant_lifecycle_limit": 8192,
        "local_queue_capacity": 32,
        "diagnostic_hops": 2,
        "trace_limit": expected_trace_limit,
        "event_trace_limit": 0,
        "event_trace_limit_inherited": False,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
        "entry_headway_seconds": 0.001,
        "declared_max_events": 20_000_000,
        "declared_max_simulation_time": -1.0,
        "opportunity_telemetry_enabled": opportunity_enabled,
    }
    for field, expected in summary_expected.items():
        _require(
            summary.get(field) == expected,
            f"{label} frozen summary echo drift: {field}",
        )
    context_expected = {
        "resource_semantics_id": FROZEN_RUNTIME_CONTROLS[
            "resource_semantics"
        ],
        "resource_semantics_echo": FROZEN_RUNTIME_CONTROLS[
            "resource_semantics"
        ],
        "scorer_mode_echo": FROZEN_RUNTIME_CONTROLS["scorer_mode"],
        "scorer_model_sha256": MODEL_SHA256,
        "pibt_mode": "P2",
        "pibt_mode_echo": "P2",
        "pibt_max_depth": 2,
        "pibt_max_ready_bags": 8,
        "pibt_max_local_resources": 32,
        "pibt_max_candidates_per_bag": 8,
        "pibt_mode_diagnostic_only": False,
        "framework_mode": "event_loop_one_step",
        "framework_mode_echo": "event_loop_one_step",
        "framework_diagnostic_only": False,
        "pressure_mode_echo": "off",
        "admission_mode": "off",
        "admission_mode_echo": "off",
        "enable_source_admission": False,
        "enable_fault_policy": True,
        "credit_mode": "C0",
        "credit_validity_seconds": 1.0,
        "credit_snapshot_max_age_seconds": 1.0,
        "credit_capacity_per_edge": 1,
        "credit_lifecycle_limit": 512,
        "selective_credit_contention_threshold": 1,
        "priority_mode": "Q0",
        "priority_mode_echo": "Q0",
        "pibt_preference_mode": "current",
        "pibt_preference_mode_echo": "current",
        "pibt_regret_prior_record_count": 0,
        "event_semantics": "E4_batch_plus_destination_merge_request",
        "event_semantics_echo": "E4_batch_plus_destination_merge_request",
        "merge_grant_rule": "M0",
        "merge_grant_rule_echo": "M0",
        "merge_grant_max_pending_requests": 256,
        "merge_grant_lifecycle_limit": 8192,
        "local_queue_capacity": 32,
        "opportunity_telemetry_enabled": opportunity_enabled,
        "opportunity_trace_limit": opportunity_limit,
        "diagnostic_hops": 2,
        "trace_limit": expected_trace_limit,
        "event_trace_limit": 0,
        "event_trace_limit_inherited": False,
        "trace_shard_count": 1,
        "trace_shard_index": 0,
        "entry_headway_seconds": 0.001,
        "declared_max_events": 20_000_000,
        "scale": 1.0,
        "reservation_depth": 1,
        "destination_merge_grant_enabled": True,
    }
    for field, expected in context_expected.items():
        _require(
            context.get(field) == expected,
            f"{label} frozen trace-context echo drift: {field}",
        )


def _raw_hard_gates(
    summary: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Any]:
    missing = [field for field in RAW_HARD_GATE_FIELDS if field not in summary]
    _require(not missing, f"{label} missing raw hard gates: {missing}")
    raw = {field: summary[field] for field in RAW_HARD_GATE_FIELDS}
    integer_fields = {
        field
        for field in RAW_HARD_GATE_FIELDS
        if field
        not in {
            "bag_future_path_field_present",
            "event_limit_reached",
            "time_limit_reached",
            "merge_grant_conservation_holds",
            "merge_grant_active_bijection_holds",
            "merge_grant_runtime_owned_capability",
            "merge_grant_exact_slot_no_future_shift",
            "merge_grant_lifecycle_complete",
            "merge_grant_protocol_integrity_pass",
            "artificial_batch_delay_seconds",
        }
    }
    for field in integer_fields:
        _strict_nonnegative_int(raw[field], f"{label}.{field}")
    for field in (
        "bag_future_path_field_present",
        "event_limit_reached",
        "time_limit_reached",
        "merge_grant_conservation_holds",
        "merge_grant_active_bijection_holds",
        "merge_grant_runtime_owned_capability",
        "merge_grant_exact_slot_no_future_shift",
        "merge_grant_lifecycle_complete",
        "merge_grant_protocol_integrity_pass",
    ):
        _strict_bool(raw[field], f"{label}.{field}")
    _finite(
        raw["artificial_batch_delay_seconds"],
        f"{label}.artificial_batch_delay_seconds",
    )
    runtime_global_scan_count = sum(
        _strict_int(summary[field], f"{label}.{field}")
        for field in (
            "global_reservation_scan_count",
            "priority_global_scan_count",
            "scorer_runtime_global_scan_count",
            "microphase_runtime_global_scan_count",
            "first_edge_credit_global_scan_count",
        )
    )
    runtime_future_route_read_count = sum(
        _strict_int(summary[field], f"{label}.{field}")
        for field in (
            "priority_future_route_input_count",
            "scorer_future_route_input_count",
            "first_edge_credit_future_route_count",
        )
    )
    runtime_future_schedule_read_count = _strict_int(
        summary["scorer_future_schedule_input_count"],
        f"{label}.scorer_future_schedule_input_count",
    )
    teacher_input_count = sum(
        _strict_int(summary[field], f"{label}.{field}")
        for field in (
            "priority_teacher_input_count",
            "scorer_teacher_input_count",
        )
    )
    live_merge_state_integrity = (
        raw["merge_grant_conservation_holds"]
        and raw["merge_grant_active_bijection_holds"]
        and raw["merge_grant_runtime_owned_capability"]
        and raw["merge_grant_exact_slot_no_future_shift"]
        and raw["merge_grant_final_active_unconsumed"] == 0
        and raw["merge_grant_outstanding_request_count"] == 0
    )
    lifecycle_complete = (
        raw["merge_grant_lifecycle_dropped_count"] == 0
    )
    protocol_integrity = (
        live_merge_state_integrity and lifecycle_complete
    )
    _require(
        raw["merge_grant_lifecycle_complete"] is lifecycle_complete,
        f"{label} merge lifecycle-complete flag drift",
    )
    _require(
        raw["merge_grant_protocol_integrity_pass"]
        is protocol_integrity,
        f"{label} merge protocol-integrity flag drift",
    )
    passed = (
        raw["requested_count"] == FULL_SEGMENT_COUNT
        and raw["completed_count"] == FULL_SEGMENT_COUNT
        and raw["failed_count"] == 0
        and raw["physical_fault_edge_entry_violation_count"] == 0
        and raw["reservation_conflicts"] == 0
        and raw["runtime_full_astar_calls"] == 0
        and runtime_global_scan_count == 0
        and runtime_future_route_read_count == 0
        and runtime_future_schedule_read_count == 0
        and teacher_input_count == 0
        and raw["full_future_routes_stored"] == 0
        and raw["bag_future_path_field_present"] is False
        and raw["max_edges_selected_per_bag_per_decision"] <= 1
        and raw["two_step_reservation_count"] == 0
        and raw["unresolved_deadlock_count"] == 0
        and raw["event_limit_reached"] is False
        and raw["time_limit_reached"] is False
        and raw["merge_grant_stale_arbitration_count"] == 0
        and raw["stale_arbitration_event_count"] == 0
        and raw["artificial_batch_delay_seconds"] == 0.0
        and live_merge_state_integrity
    )
    result = {
        **raw,
        "runtime_global_scan_count": runtime_global_scan_count,
        "runtime_future_route_read_count": runtime_future_route_read_count,
        "runtime_future_schedule_read_count": (
            runtime_future_schedule_read_count
        ),
        "teacher_input_count": teacher_input_count,
        "live_merge_state_integrity_pass": live_merge_state_integrity,
        "passive_lifecycle_truncated": (
            not lifecycle_complete
        ),
        "all_live_hard_gates_pass": passed,
    }
    _require(passed, f"{label} live hard gate failure")
    return result


def _validate_bag_coverage(
    payload: Mapping[str, Any],
    expected_segment_ids: Sequence[str],
    *,
    label: str,
) -> tuple[str, str]:
    bags = _array(payload.get("bags"), f"{label}.bags")
    _require(
        len(bags) == FULL_SEGMENT_COUNT,
        f"{label} bag result count is not full original 1x",
    )
    rows = [_mapping(row, f"{label}.bags[{index}]") for index, row in enumerate(bags)]
    observed_ids = [str(row.get("segment_id", "")) for row in rows]
    _require(
        len(set(observed_ids)) == FULL_SEGMENT_COUNT,
        f"{label} bag result segment IDs are not unique",
    )
    _require(
        set(observed_ids) == set(expected_segment_ids),
        f"{label} bag result segment coverage drift",
    )
    for index, row in enumerate(rows):
        _require(
            row.get("completed") is True
            and row.get("failure_reason") in {"", None},
            f"{label} incomplete bag result at row {index}",
        )
    ordered = sorted(rows, key=lambda row: str(row["segment_id"]))
    junction = _array(
        payload.get("junction_state"), f"{label}.junction_state"
    )
    _require(bool(junction), f"{label}.junction_state cannot be empty")
    return canonical_sha256(ordered), canonical_sha256(junction)


def _validate_runtime_payload(
    payload: Mapping[str, Any],
    *,
    binary: Mapping[str, Any],
    expected_segment_ids: Sequence[str],
    opportunity_enabled: bool,
    opportunity_limit: int,
    label: str,
) -> dict[str, Any]:
    summary = _mapping(payload.get("summary"), f"{label}.summary")
    context = _mapping(
        payload.get("trace_context"), f"{label}.trace_context"
    )
    _validate_binary_echo(
        payload, summary, binary=binary, label=label
    )
    _validate_frozen_echo(
        summary,
        context,
        opportunity_enabled=opportunity_enabled,
        opportunity_limit=opportunity_limit,
        label=label,
    )
    hard_gates = _raw_hard_gates(summary, label=label)
    bag_sha, junction_sha = _validate_bag_coverage(
        payload, expected_segment_ids, label=label
    )
    missing_core = [
        field
        for field in DETERMINISTIC_CORE_SUMMARY_FIELDS
        if field not in summary
    ]
    _require(
        not missing_core,
        f"{label} missing deterministic core summary fields: {missing_core}",
    )
    core = {
        field: summary[field]
        for field in dict.fromkeys(DETERMINISTIC_CORE_SUMMARY_FIELDS)
    }
    return {
        "summary": summary,
        "trace_context": context,
        "raw_hard_gates": hard_gates,
        "bag_projection_sha256": bag_sha,
        "junction_state_sha256": junction_sha,
        "deterministic_core_summary": core,
        "deterministic_core_summary_sha256": canonical_sha256(core),
    }


def _validate_clone_hard_gates(
    invariants: Mapping[str, Any],
) -> dict[str, Any]:
    required_zero = (
        "failed_segment_count",
        "unsafe_entry_count",
        "reservation_conflict_count",
        "runtime_full_astar_call_count",
        "runtime_global_scan_count",
        "runtime_future_route_read_count",
        "runtime_future_schedule_read_count",
        "teacher_input_count",
        "full_future_routes_stored",
        "two_step_reservation_count",
        "unresolved_deadlock_count",
        "merge_grant_final_active_unconsumed",
        "merge_grant_outstanding_request_count",
        "merge_grant_stale_arbitration_count",
        "stale_arbitration_event_count",
    )
    required_true = (
        "merge_grant_conservation_holds",
        "merge_grant_active_bijection_holds",
        "merge_grant_runtime_owned_capability",
        "merge_grant_exact_slot_no_future_shift",
        "merge_grant_active_state_integrity_pass",
    )
    for field in (
        "requested_count",
        "completed_count",
        "event_count",
        "max_selected_edges_per_bag",
        "reservation_depth",
        "merge_grant_lifecycle_dropped_count",
        "g4irsf14_i2_live_eligible_multi_request_boundary_count",
        "g4irsf14_i5_prefilter_candidate_count",
        "g4irsf14_i5_applicable_ready_slice_boundary_count",
        *required_zero,
    ):
        _strict_nonnegative_int(
            invariants.get(field), f"clone invariants.{field}"
        )
    _require(
        invariants["g4irsf14_i5_prefilter_candidate_count"]
        >= invariants[
            "g4irsf14_i5_applicable_ready_slice_boundary_count"
        ],
        "clone I5 exact counter relation failed",
    )
    for field in (
        *required_true,
        "bag_future_path_field_present",
        "event_limit_reached",
        "time_limit_reached",
        "merge_grant_lifecycle_complete",
        "merge_grant_protocol_integrity_pass",
    ):
        _strict_bool(invariants.get(field), f"clone invariants.{field}")
    _finite(
        invariants.get("artificial_batch_delay_seconds"),
        "clone invariants.artificial_batch_delay_seconds",
    )
    passed = (
        invariants["requested_count"] == FULL_SEGMENT_COUNT
        and invariants["completed_count"] == FULL_SEGMENT_COUNT
        and all(invariants[field] == 0 for field in required_zero)
        and invariants["bag_future_path_field_present"] is False
        and invariants["reservation_depth"] == 1
        and invariants["max_selected_edges_per_bag"] <= 1
        and invariants["event_limit_reached"] is False
        and invariants["time_limit_reached"] is False
        and invariants["artificial_batch_delay_seconds"] == 0.0
        and all(invariants[field] is True for field in required_true)
    )
    active_state_integrity = (
        invariants["merge_grant_conservation_holds"]
        and invariants["merge_grant_active_bijection_holds"]
        and invariants["merge_grant_runtime_owned_capability"]
        and invariants["merge_grant_exact_slot_no_future_shift"]
        and invariants["merge_grant_final_active_unconsumed"] == 0
        and invariants["merge_grant_outstanding_request_count"] == 0
    )
    lifecycle_complete = (
        invariants["merge_grant_lifecycle_dropped_count"] == 0
    )
    _require(
        invariants["merge_grant_active_state_integrity_pass"]
        is active_state_integrity,
        "clone merge active-state integrity flag drift",
    )
    _require(
        invariants["merge_grant_lifecycle_complete"]
        is lifecycle_complete,
        "clone merge lifecycle-complete flag drift",
    )
    _require(
        invariants["merge_grant_protocol_integrity_pass"]
        is (active_state_integrity and lifecycle_complete),
        "clone merge protocol-integrity flag drift",
    )
    _require(passed, "clone branch live hard gate failure")
    return {
        **dict(invariants),
        "passive_lifecycle_truncated": (
            not lifecycle_complete
        ),
        "all_live_hard_gates_pass": True,
    }


def _validate_clone_payload(
    payload: Mapping[str, Any],
    *,
    clone_event_ordinal: int,
    binary: Mapping[str, Any],
) -> dict[str, Any]:
    _require(
        payload.get("schema")
        == "czr005.g4irsf14.exact_binary_noop_rerun.v1",
        "clone payload schema mismatch",
    )
    _require(
        payload.get("evidence_scope")
        == "NOOP_FIDELITY_MECHANISM_ONLY_NOT_A_CAUSAL_LABEL",
        "clone payload evidence scope mismatch",
    )
    _require(payload.get("formal_pass_claimed") is False, "clone claimed formal pass")
    _require(payload.get("intervention_applied") is False, "clone applied intervention")
    _require(
        payload.get("input_request_count") == FULL_SEGMENT_COUNT,
        "clone input request count mismatch",
    )
    expected_binary = {
        "path": str(binary["path"]),
        "sha256": str(binary["sha256"]),
    }
    observed_path = payload.get("loaded_cpp_binary_path")
    _require(
        isinstance(observed_path, str)
        and os.path.normcase(str(Path(observed_path).resolve()))
        == os.path.normcase(
            str(Path(expected_binary["path"]).resolve())
        ),
        "clone loaded binary path echo mismatch",
    )
    _require(
        payload.get("loaded_cpp_binary_sha256")
        == expected_binary["sha256"],
        "clone loaded binary SHA echo mismatch",
    )
    observed_binary = _mapping(payload.get("binary"), "clone.binary")
    _require(
        observed_binary == expected_binary,
        "clone binary object differs from execution identity",
    )
    _require(
        _mapping(payload.get("frozen_controls"), "clone.frozen_controls")
        == dict(CLONE_FROZEN_CONTROLS),
        "clone frozen controls mismatch",
    )
    boundary = _mapping(payload.get("boundary"), "clone.boundary")
    _require(
        boundary.get("kind") == "queue_top_pre_pop"
        and boundary.get("queue_top_not_popped") is True
        and boundary.get("staged_event_sink_empty") is True
        and boundary.get("processed_event_count") == clone_event_ordinal,
        "clone boundary is not the preregistered safe pre-pop boundary",
    )
    _require_sha256(
        boundary.get("runtime_state_sha256"),
        "clone.boundary.runtime_state_sha256",
    )
    _require(
        payload.get("native_three_way_exact_match") is True,
        "clone native three-way replay mismatch",
    )
    hashes = _mapping(
        payload.get("source_replay_hashes"),
        "clone.source_replay_hashes",
    )
    _require(
        set(hashes) == set(REPLAY_HASH_FIELDS),
        "clone replay hash inventory mismatch",
    )
    for field in REPLAY_HASH_FIELDS:
        _require_sha256(hashes[field], f"clone replay hash {field}")
    _require(
        _mapping(
            payload.get("baseline_replay_hashes"),
            "clone.baseline_replay_hashes",
        )
        == hashes
        and _mapping(
            payload.get("clone_replay_hashes"),
            "clone.clone_replay_hashes",
        )
        == hashes,
        "clone replay hashes are not exactly equal",
    )
    source_invariants = _mapping(
        payload.get("source_invariants"), "clone.source_invariants"
    )
    _require(
        _mapping(
            payload.get("baseline_invariants"),
            "clone.baseline_invariants",
        )
        == source_invariants
        and _mapping(
            payload.get("clone_invariants"), "clone.clone_invariants"
        )
        == source_invariants,
        "clone branch invariants are not exactly equal",
    )
    hard_gates = _validate_clone_hard_gates(source_invariants)
    return {
        "binary": expected_binary,
        "boundary": boundary,
        "replay_hashes": hashes,
        "raw_hard_gates": hard_gates,
        "evidence_sha256": canonical_sha256(
            {
                "binary": expected_binary,
                "boundary": boundary,
                "replay_hashes": hashes,
                "raw_hard_gates": hard_gates,
            }
        ),
    }


def _screen_key(fields: Mapping[str, Any]) -> str:
    return canonical_sha256(fields)


def _source_support(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    rows = _array(
        payload.get("source_admission_opportunities"),
        "opportunity.source_admission_opportunities",
    )
    total = _strict_int(
        summary.get("source_opportunity_total_count"),
        "source_opportunity_total_count",
    )
    stored = _strict_int(
        summary.get("source_opportunity_stored_count"),
        "source_opportunity_stored_count",
    )
    dropped = _strict_int(
        summary.get("source_opportunity_dropped_count"),
        "source_opportunity_dropped_count",
    )
    _require(total == stored + dropped, "source telemetry conservation mismatch")
    _require(stored == len(rows), "source telemetry stored-row mismatch")
    _require(dropped == 0, "I1 source opportunity census was truncated")
    keys: list[str] = []
    max_ready = 0
    for index, raw in enumerate(rows):
        row = _mapping(raw, f"source opportunity row {index}")
        ready = _strict_int(
            row.get("ready_set_size"),
            f"source opportunity row {index}.ready_set_size",
        )
        max_ready = max(max_ready, ready)
        if ready < 2:
            continue
        fields = {
            "timestamp_bits": _strict_int(
                row.get("timestamp_bits"),
                f"source opportunity row {index}.timestamp_bits",
            ),
            "source_node": _strict_int(
                row.get("source_node"),
                f"source opportunity row {index}.source_node",
            ),
            "event_seq": _strict_int(
                row.get("event_seq"),
                f"source opportunity row {index}.event_seq",
            ),
            "arbitration_generation": _strict_int(
                row.get("arbitration_generation"),
                f"source opportunity row {index}.arbitration_generation",
            ),
            "ready_set_size": ready,
            "chosen_runtime_bag_id": _strict_int(
                row.get("chosen_runtime_bag_id"),
                f"source opportunity row {index}.chosen_runtime_bag_id",
            ),
        }
        keys.append(_screen_key(fields))
    _require(len(keys) == len(set(keys)), "I1 screening keys are not unique")
    return {
        "support_status": "SUPPORTED_SCREENING_ONLY",
        "total_boundary_count": total,
        "multi_ready_boundary_count": len(keys),
        "unique_screening_boundary_count": len(keys),
        "minimum_distinct_swap_action_count": len(keys),
        "max_ready_set_size": max_ready,
        "stored_count": stored,
        "dropped_count": dropped,
        "screening_manifest_sha256": canonical_sha256(sorted(keys)),
        "count_semantics": (
            "exact complete source-boundary census; each ready_set_size>=2 "
            "boundary admits at least one in-set order swap"
        ),
        "causal_label_count": 0,
        "formal_horizon_completion_count": 0,
        "content_address_contract": [
            "checkpoint.runtime_state_sha256",
            "queue_top.next_event_seq",
            "queue_top.next_event_time_bits",
            "source_node",
            "source_arbitration_generation",
            "complete_ordered_source_ready_runtime_bag_ids",
            "swap_runtime_bag_id",
            "swap_peer_runtime_bag_id",
            "horizon",
        ],
    }


def _i2_support(summary: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    raw = {
        field: _strict_nonnegative_int(
            summary.get(field), f"I2 raw.{field}"
        )
        for field in I2_RAW_COUNTER_FIELDS
    }
    exact_count = raw[
        "g4irsf14_i2_live_eligible_multi_request_boundary_count"
    ]
    exact_zero = exact_count == 0
    support = {
        "support_status": (
            "BLOCKED_ZERO_LIVE_ELIGIBLE_SUPPORT"
            if exact_zero
            else "SUPPORTED_EXACT_BOUNDARY_SCREENING_ONLY"
        ),
        "eligible_live_multi_request_boundary_count": exact_count,
        "exact_zero_proven": exact_zero,
        "proof_semantics": (
            "native uint64 increments exactly once at each arbitration "
            "boundary whose post-expiry live eligible request set has "
            "cardinality at least two; legacy pending/loser counters are "
            "informational only"
        ),
        "causal_label_count": 0,
        "formal_horizon_completion_count": 0,
        "content_address_contract": [
            "checkpoint.runtime_state_sha256",
            "queue_top.next_event_seq",
            "queue_top.next_event_time_bits",
            "destination_node",
            "destination_wakeup_generation",
            "complete_ordered_live_eligible_request_ids",
            "swap_request_id",
            "swap_peer_request_id",
            "horizon",
        ],
    }
    return support, raw


def _decision_support(
    payload: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    decision_trace_limit: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    decisions = _array(payload.get("decisions"), "decision.decisions")
    alias = _array(payload.get("decision_trace"), "decision.decision_trace")
    holds = _array(payload.get("hold_attempts"), "decision.hold_attempts")
    _require(alias == decisions, "decision_trace alias drift")
    stored_decisions = _strict_int(
        summary.get("decision_trace_stored_count"),
        "decision_trace_stored_count",
    )
    stored_holds = _strict_int(
        summary.get("hold_trace_stored_count"),
        "hold_trace_stored_count",
    )
    seen = _strict_int(
        summary.get("decision_trace_seen_count"),
        "decision_trace_seen_count",
    )
    _require(stored_decisions == len(decisions), "stored decision count mismatch")
    _require(stored_holds == len(holds), "stored hold count mismatch")
    _require(
        stored_decisions + stored_holds <= decision_trace_limit,
        "combined decision trace exceeds declared bound",
    )
    i3_keys: list[str] = []
    i3_action_count = 0
    i4_keys: list[str] = []
    max_candidate_count = 0
    max_safe_candidate_count = 0
    for index, raw in enumerate(decisions):
        row = _mapping(raw, f"decision row {index}")
        metadata = _mapping(
            row.get("metadata"), f"decision row {index}.metadata"
        )
        candidates = _array(
            row.get("candidate_records"),
            f"decision row {index}.candidate_records",
        )
        max_candidate_count = max(max_candidate_count, len(candidates))
        safe_nodes: list[int] = []
        for candidate_index, raw_candidate in enumerate(candidates):
            candidate = _mapping(
                raw_candidate,
                f"decision row {index}.candidate {candidate_index}",
            )
            if _strict_bool(
                candidate.get("shield_allowed"),
                f"decision row {index}.candidate {candidate_index}.shield_allowed",
            ):
                safe_nodes.append(
                    _strict_int(
                        candidate.get("next_node"),
                        f"decision row {index}.candidate {candidate_index}.next_node",
                    )
                )
        _require(
            len(safe_nodes) == len(set(safe_nodes)),
            f"decision row {index} safe candidate nodes are not unique",
        )
        max_safe_candidate_count = max(
            max_safe_candidate_count, len(safe_nodes)
        )
        selected = row.get("selected_next")
        if selected is None:
            continue
        selected_int = _strict_int(
            selected, f"decision row {index}.selected_next"
        )
        common = {
            "arrive_event_seq": _strict_int(
                metadata.get("arrive_event_seq"),
                f"decision row {index}.metadata.arrive_event_seq",
            ),
            "event_time_bits": _double_bits(
                row.get("event_time"),
                f"decision row {index}.event_time",
            ),
            "runtime_bag_id": _strict_int(
                metadata.get("runtime_bag_id"),
                f"decision row {index}.metadata.runtime_bag_id",
            ),
            "current_node": _strict_int(
                row.get("current_node"),
                f"decision row {index}.current_node",
            ),
            "baseline_next_node": selected_int,
        }
        i4_keys.append(_screen_key({**common, "selected_release": False}))
        alternatives = sorted(
            node for node in safe_nodes if node != selected_int
        )
        if alternatives:
            i3_keys.append(
                _screen_key(
                    {**common, "safe_alternative_next_nodes": alternatives}
                )
            )
            i3_action_count += len(alternatives)
    _require(len(i3_keys) == len(set(i3_keys)), "I3 screening keys are not unique")
    _require(len(i4_keys) == len(set(i4_keys)), "I4 screening keys are not unique")
    i3 = {
        "support_status": "SUPPORTED_CONSERVATIVE_SCREENING_LOWER_BOUND",
        "total_decision_trace_rows_seen": seen,
        "combined_trace_storage_limit": decision_trace_limit,
        "stored_committed_decision_count": stored_decisions,
        "stored_hold_attempt_count": stored_holds,
        "safe_alternative_boundary_lower_bound": len(i3_keys),
        "safe_alternative_action_lower_bound": i3_action_count,
        "max_candidate_count": max_candidate_count,
        "max_safe_candidate_count": max_safe_candidate_count,
        "screening_manifest_sha256": canonical_sha256(sorted(i3_keys)),
        "lower_bound_only": True,
        "causal_label_count": 0,
        "formal_horizon_completion_count": 0,
        "content_address_contract": [
            "checkpoint.runtime_state_sha256",
            "queue_top.next_event_seq",
            "decision.arrive_event_seq",
            "decision.event_time_bits",
            "runtime_bag_id",
            "current_node",
            "baseline_next_node",
            "complete_sorted_shield_allowed_next_nodes",
            "selected_alternative_next_node",
            "horizon",
        ],
    }
    i4 = {
        "support_status": "SUPPORTED_CONSERVATIVE_SCREENING_LOWER_BOUND",
        "release_to_hold_boundary_lower_bound": len(i4_keys),
        "screening_manifest_sha256": canonical_sha256(sorted(i4_keys)),
        "direction": "baseline_release_to_one_local_opportunity_hold_only",
        "forced_hold_to_release_allowed": False,
        "lower_bound_only": True,
        "completion_caveat": (
            "local hold is non-collision-creating, but exact H_bag/H_system "
            "completion remains unexecuted"
        ),
        "causal_label_count": 0,
        "formal_horizon_completion_count": 0,
        "content_address_contract": [
            "checkpoint.runtime_state_sha256",
            "queue_top.next_event_seq",
            "decision.arrive_event_seq",
            "decision.event_time_bits",
            "runtime_bag_id",
            "current_node",
            "baseline_release_true",
            "selected_release_false",
            "one_local_service_opportunity_generation",
            "horizon",
        ],
    }
    return i3, i4


def _i5_support(summary: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    raw = {
        field: _strict_nonnegative_int(
            summary.get(field), f"P2 raw.{field}"
        )
        for field in P2_RAW_COUNTER_FIELDS
    }
    prefilter = raw["g4irsf14_i5_prefilter_candidate_count"]
    applicable = raw[
        "g4irsf14_i5_applicable_ready_slice_boundary_count"
    ]
    _require(
        prefilter >= applicable,
        "I5 exact prefilter count is below applicable ready-slice count",
    )
    without_applicable = prefilter - applicable
    support = {
        "support_status": (
            "SUPPORTED_STRICT_READY_SLICE_SCREENING_ONLY"
            if applicable > 0
            else (
                "BLOCKED_ZERO_READY_SLICE_SUPPORT_WITH_PREFILTER_ONLY"
                if prefilter > 0
                else "BLOCKED_ZERO_READY_SLICE_AND_PREFILTER_SUPPORT"
            )
        ),
        "prefilter_candidate_count": prefilter,
        "applicable_ready_slice_boundary_count": applicable,
        "prefilter_without_applicable_slice_count": without_applicable,
        "ready_slice_intervention_opportunity_count": applicable,
        "strict_same_ready_slice_boundary_count": applicable,
        "exact_zero_proven": applicable == 0,
        "interpretation": (
            "native uint64 counters separately record prefilter candidates "
            "and boundaries where the recursively constructed PIBTLocalSlice "
            "is applicable; the arithmetic remainder is not a no-benefit "
            "causal label, and legacy P2 activation/not-applicable counters "
            "are informational only"
        ),
        "causal_label_count": 0,
        "formal_horizon_completion_count": 0,
        "content_address_contract": [
            "checkpoint.runtime_state_sha256",
            "queue_top.next_event_seq",
            "queue_top.next_event_time_bits",
            "trigger_node",
            "trigger_runtime_bag_id",
            "complete_ordered_ready_slice_bag_ids",
            "complete_local_resource_owner_map",
            "complete_safe_one_edge_candidate_sets",
            "baseline_pibt_enabled",
            "selected_pibt_enabled",
            "horizon",
        ],
    }
    return support, raw


def _blocker_reasons(
    support: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    reasons = [
        "NO_EXACT_BINARY_ONE_SHOT_I1_I5_INTERVENTION_RERUNS",
        "ZERO_COMPLETE_H_BAG_H_SYSTEM_CAUSAL_LABELS",
        "ORIGINAL_TASK_MINIMUM_2000_MATCHED_INTERVENTIONS_NOT_ESTABLISHED",
        "H_SYSTEM_INTERVENTION_COUNT_IS_ZERO",
    ]
    if support["I2_merge_request_order_swap"]["exact_zero_proven"]:
        reasons.append(
            "I2_ZERO_LIVE_ELIGIBLE_MULTI_REQUEST_GRANT_BOUNDARIES"
        )
    if support["I5_pibt_trigger"]["exact_zero_proven"]:
        reasons.append("I5_ZERO_P2_READY_SLICE_INTERVENTION_BOUNDARIES")
    return sorted(reasons)


def _self_hash(document: Mapping[str, Any]) -> str:
    payload = dict(document)
    payload.pop("self_sha256", None)
    return canonical_sha256(payload)


def _recompute_stored_hard_gates(
    gates: Mapping[str, Any],
    *,
    run_name: str,
) -> dict[str, Any]:
    value = _mapping(gates, f"raw_hard_gates.{run_name}")
    if run_name == "clone_noop":
        raw = {
            field: child
            for field, child in value.items()
            if field
            not in {
                "passive_lifecycle_truncated",
                "all_live_hard_gates_pass",
            }
        }
        recomputed = _validate_clone_hard_gates(raw)
    else:
        recomputed = _raw_hard_gates(value, label=run_name)
    _require(
        value == recomputed,
        f"{run_name} raw hard-gate derivation drift",
    )
    return value


def validate_census_document(
    document: Mapping[str, Any],
    *,
    expected_execution_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    value = _mapping(document, "census document")
    required_top = {
        "schema",
        "status",
        "evidence_scope",
        "formal_pass_claimed",
        "causal_label_count",
        "generated_by",
        "protected_inputs",
        "binary",
        "source_bundle",
        "frozen_controls",
        "replay_hashes",
        "raw_hard_gates",
        "execution",
        "support",
        "i2_raw_counters",
        "p2_raw_counters",
        "blocker",
        "self_sha256",
    }
    _require(set(value) == required_top, "census document key inventory mismatch")
    _require(value["schema"] == SCHEMA, "census schema mismatch")
    _require(value["status"] == STATUS, "census status must remain partial")
    _require(
        value["evidence_scope"] == EVIDENCE_SCOPE,
        "census evidence scope mismatch",
    )
    _require(value["formal_pass_claimed"] is False, "census claimed formal pass")
    _require(value["causal_label_count"] == 0, "census contains causal labels")
    _require(
        value["generated_by"]
        == "scripts/eval/g4irsf14_opportunity_census.py",
        "census generator identity mismatch",
    )
    _require_sha256(value["self_sha256"], "census self_sha256")
    _require(value["self_sha256"] == _self_hash(value), "census self hash drift")
    protected = _mapping(value["protected_inputs"], "protected_inputs")
    _require(
        protected
        == {
            "map": {
                "path": MAP_PATH.as_posix(),
                "raw_sha256": MAP_RAW_SHA256,
                "semantic_sha256": MAP_SEMANTIC_SHA256,
            },
            "task": {
                "path": TASK_PATH.as_posix(),
                "raw_sha256": TASK_RAW_SHA256,
                "semantic_sha256": TASK_SEMANTIC_SHA256,
                "segment_count": FULL_SEGMENT_COUNT,
                "raw_bag_count": FULL_RAW_BAG_COUNT,
            },
        },
        "census protected input identity mismatch",
    )
    binary = _mapping(value["binary"], "binary")
    _require(set(binary) == {"path", "sha256"}, "binary inventory mismatch")
    _require(
        _is_portable_absolute_path(str(binary["path"])),
        "binary path is not absolute",
    )
    _require_sha256(binary["sha256"], "binary.sha256")
    source_bundle = _mapping(value["source_bundle"], "source_bundle")
    _require(
        set(source_bundle)
        == {
            "hash_mode",
            "files",
            "path_manifest_sha256",
            "bundle_sha256",
        },
        "source bundle inventory mismatch",
    )
    _require(
        source_bundle["hash_mode"]
        == "sha256_utf8_after_crlf_to_lf_reject_lone_cr",
        "source bundle hash mode drift",
    )
    source_rows = [
        _mapping(row, f"source_bundle.files[{index}]")
        for index, row in enumerate(
            _array(source_bundle["files"], "source_bundle.files")
        )
    ]
    _require(bool(source_rows), "source bundle files cannot be empty")
    _require(
        all(set(row) == {"path", "semantic_sha256"} for row in source_rows),
        "source bundle row inventory mismatch",
    )
    for index, row in enumerate(source_rows):
        _require(
            isinstance(row["path"], str) and bool(row["path"]),
            f"source bundle row {index} path is invalid",
        )
        _require_sha256(
            row["semantic_sha256"],
            f"source bundle row {index} semantic SHA",
        )
    _require(
        source_rows == sorted(source_rows, key=lambda row: row["path"])
        and len({row["path"] for row in source_rows}) == len(source_rows),
        "source bundle paths are not sorted unique",
    )
    for field in ("path_manifest_sha256", "bundle_sha256"):
        _require_sha256(source_bundle.get(field), f"source_bundle.{field}")
    _require(
        source_bundle["path_manifest_sha256"]
        == canonical_sha256([row["path"] for row in source_rows])
        and source_bundle["bundle_sha256"] == canonical_sha256(source_rows),
        "source bundle internal hash drift",
    )
    _require(
        value["frozen_controls"]
        == {
            **dict(FROZEN_RUNTIME_CONTROLS),
            "opportunity_trace_limit": OPPORTUNITY_TRACE_LIMIT,
            "decision_trace_limit": DECISION_TRACE_LIMIT,
            "clone_event_ordinal": CLONE_EVENT_ORDINAL,
        },
        "census frozen controls drift",
    )
    replay = _mapping(value["replay_hashes"], "replay_hashes")
    _require(set(replay) == set(REPLAY_HASH_FIELDS), "replay hash inventory drift")
    for field in REPLAY_HASH_FIELDS:
        _require_sha256(replay[field], f"replay_hashes.{field}")
    raw_gates = _mapping(value["raw_hard_gates"], "raw_hard_gates")
    _require(
        set(raw_gates) == {"clone_noop", "opportunity_run", "decision_run"},
        "raw hard gate run inventory mismatch",
    )
    validated_gates = {
        run_name: _recompute_stored_hard_gates(
            gates_value, run_name=run_name
        )
        for run_name, gates_value in raw_gates.items()
    }
    support = _mapping(value["support"], "support")
    _require(
        set(support)
        == {
            "I1_source_order_swap",
            "I2_merge_request_order_swap",
            "I3_next_edge",
            "I4_hold_release",
            "I5_pibt_trigger",
        },
        "intervention support inventory mismatch",
    )
    for kind, raw_support in support.items():
        item = _mapping(raw_support, f"support.{kind}")
        _require(
            item.get("causal_label_count") == 0
            and item.get("formal_horizon_completion_count") == 0,
            f"{kind} improperly claims causal completion",
        )
    _require(
        support["I3_next_edge"].get("lower_bound_only") is True
        and support["I4_hold_release"].get("lower_bound_only") is True,
        "I3/I4 must remain conservative screening lower bounds",
    )
    _require(
        support["I1_source_order_swap"].get("support_status")
        == "SUPPORTED_SCREENING_ONLY",
        "I1 support status drift",
    )
    _require(
        support["I3_next_edge"].get("support_status")
        == "SUPPORTED_CONSERVATIVE_SCREENING_LOWER_BOUND"
        and support["I4_hold_release"].get("support_status")
        == "SUPPORTED_CONSERVATIVE_SCREENING_LOWER_BOUND",
        "I3/I4 support status drift",
    )
    i2_raw = _mapping(value["i2_raw_counters"], "i2_raw_counters")
    p2_raw = _mapping(value["p2_raw_counters"], "p2_raw_counters")
    _require(
        set(i2_raw) == set(I2_RAW_COUNTER_FIELDS),
        "I2 raw counter inventory mismatch",
    )
    _require(
        set(p2_raw) == set(P2_RAW_COUNTER_FIELDS),
        "P2 raw counter inventory mismatch",
    )
    for field, counter in i2_raw.items():
        _strict_nonnegative_int(counter, f"i2_raw_counters.{field}")
    for field, counter in p2_raw.items():
        _strict_nonnegative_int(counter, f"p2_raw_counters.{field}")
    expected_i2, _ = _i2_support(i2_raw)
    _require(
        _mapping(
            support["I2_merge_request_order_swap"],
            "support.I2_merge_request_order_swap",
        )
        == expected_i2,
        "I2 support does not recompute from raw counters",
    )
    expected_i5, _ = _i5_support(p2_raw)
    _require(
        _mapping(
            support["I5_pibt_trigger"],
            "support.I5_pibt_trigger",
        )
        == expected_i5,
        "I5 support does not recompute from raw counters",
    )
    _require(
        validated_gates["clone_noop"][
            "g4irsf14_i2_live_eligible_multi_request_boundary_count"
        ]
        == i2_raw[
            "g4irsf14_i2_live_eligible_multi_request_boundary_count"
        ]
        and validated_gates["clone_noop"][
            "g4irsf14_i5_prefilter_candidate_count"
        ]
        == p2_raw["g4irsf14_i5_prefilter_candidate_count"]
        and validated_gates["clone_noop"][
            "g4irsf14_i5_applicable_ready_slice_boundary_count"
        ]
        == p2_raw[
            "g4irsf14_i5_applicable_ready_slice_boundary_count"
        ],
        "clone/runtime exact opportunity counter drift",
    )
    blocker = _mapping(value["blocker"], "blocker")
    expected_reasons = _blocker_reasons(support)
    _require(
        blocker
        == {
            "code": FORMAL_BLOCKER_CODE,
            "reasons": expected_reasons,
            "minimum_required_complete_interventions": (
                MIN_FORMAL_INTERVENTIONS
            ),
            "unique_complete_h_bag_h_system_intervention_count": 0,
            "h_system_intervention_count": 0,
            "taxonomy_complete": False,
            "formal_pass_allowed": False,
        },
        "formal blocker does not recompute from support",
    )
    execution = _mapping(value["execution"], "execution")
    _require(
        set(execution)
        == {
            "clone_noop",
            "opportunity_run",
            "decision_run",
            "cross_run",
        },
        "execution evidence inventory mismatch",
    )
    clone_execution = _mapping(
        execution["clone_noop"], "execution.clone_noop"
    )
    _require(
        set(clone_execution)
        == {
            "binary",
            "boundary",
            "replay_hashes",
            "raw_hard_gates",
            "evidence_sha256",
        },
        "clone execution projection inventory mismatch",
    )
    clone_boundary = _mapping(
        clone_execution["boundary"], "execution.clone_noop.boundary"
    )
    _require_sha256(
        clone_boundary.get("runtime_state_sha256"),
        "execution.clone_noop.boundary.runtime_state_sha256",
    )
    _require(
        clone_execution["binary"] == binary,
        "clone execution binary binding drift",
    )
    _require(
        clone_execution["replay_hashes"] == replay,
        "clone execution replay-hash binding drift",
    )
    _require(
        clone_execution["raw_hard_gates"]
        == validated_gates["clone_noop"],
        "clone execution hard-gate binding drift",
    )
    expected_clone_evidence_sha = canonical_sha256(
        {
            "binary": binary,
            "boundary": clone_boundary,
            "replay_hashes": replay,
            "raw_hard_gates": validated_gates["clone_noop"],
        }
    )
    _require(
        clone_execution["evidence_sha256"]
        == expected_clone_evidence_sha,
        "clone execution evidence hash drift",
    )
    opportunity_execution = _mapping(
        execution["opportunity_run"], "execution.opportunity_run"
    )
    decision_execution = _mapping(
        execution["decision_run"], "execution.decision_run"
    )
    _require(
        set(opportunity_execution)
        == {
            "bag_projection_sha256",
            "junction_state_sha256",
            "deterministic_core_summary_sha256",
            "source_opportunity_total_count",
            "source_multi_ready_boundary_count",
            "source_unique_screening_boundary_count",
            "source_opportunity_manifest_sha256",
            "g4irsf14_i2_live_eligible_multi_request_boundary_count",
            "g4irsf14_i5_prefilter_candidate_count",
            "g4irsf14_i5_applicable_ready_slice_boundary_count",
        },
        "opportunity execution projection inventory mismatch",
    )
    _require(
        set(decision_execution)
        == {
            "bag_projection_sha256",
            "junction_state_sha256",
            "deterministic_core_summary_sha256",
            "i3_safe_alternative_boundary_lower_bound",
            "i3_screening_manifest_sha256",
            "i4_release_to_hold_boundary_lower_bound",
            "i4_screening_manifest_sha256",
            "g4irsf14_i2_live_eligible_multi_request_boundary_count",
            "g4irsf14_i5_prefilter_candidate_count",
            "g4irsf14_i5_applicable_ready_slice_boundary_count",
        },
        "decision execution projection inventory mismatch",
    )
    for run_name, projection in (
        ("opportunity_run", opportunity_execution),
        ("decision_run", decision_execution),
    ):
        for field in (
            "bag_projection_sha256",
            "junction_state_sha256",
            "deterministic_core_summary_sha256",
        ):
            _require_sha256(
                projection[field],
                f"execution.{run_name}.{field}",
            )
        _require(
            projection[
                "g4irsf14_i2_live_eligible_multi_request_boundary_count"
            ]
            == i2_raw[
                "g4irsf14_i2_live_eligible_multi_request_boundary_count"
            ]
            and projection["g4irsf14_i5_prefilter_candidate_count"]
            == p2_raw["g4irsf14_i5_prefilter_candidate_count"]
            and projection[
                "g4irsf14_i5_applicable_ready_slice_boundary_count"
            ]
            == p2_raw[
                "g4irsf14_i5_applicable_ready_slice_boundary_count"
            ],
            f"{run_name} exact counter projection drift",
        )
    i1 = _mapping(
        support["I1_source_order_swap"],
        "support.I1_source_order_swap",
    )
    i3 = _mapping(support["I3_next_edge"], "support.I3_next_edge")
    i4 = _mapping(support["I4_hold_release"], "support.I4_hold_release")
    _require_sha256(
        i1.get("screening_manifest_sha256"),
        "I1 screening manifest SHA",
    )
    _require_sha256(
        i3.get("screening_manifest_sha256"),
        "I3 screening manifest SHA",
    )
    _require_sha256(
        i4.get("screening_manifest_sha256"),
        "I4 screening manifest SHA",
    )
    i1_total = _strict_nonnegative_int(
        i1.get("total_boundary_count"), "I1 total boundary count"
    )
    i1_stored = _strict_nonnegative_int(
        i1.get("stored_count"), "I1 stored count"
    )
    i1_dropped = _strict_nonnegative_int(
        i1.get("dropped_count"), "I1 dropped count"
    )
    i1_multi = _strict_nonnegative_int(
        i1.get("multi_ready_boundary_count"),
        "I1 multi-ready boundary count",
    )
    _require(
        i1_total == i1_stored + i1_dropped
        and i1_dropped == 0
        and i1_multi <= i1_total
        and i1.get("unique_screening_boundary_count") == i1_multi
        and i1.get("minimum_distinct_swap_action_count") == i1_multi,
        "I1 support count semantics drift",
    )
    i3_count = _strict_nonnegative_int(
        i3.get("safe_alternative_boundary_lower_bound"),
        "I3 safe-alternative boundary lower bound",
    )
    i3_actions = _strict_nonnegative_int(
        i3.get("safe_alternative_action_lower_bound"),
        "I3 safe-alternative action lower bound",
    )
    i4_count = _strict_nonnegative_int(
        i4.get("release_to_hold_boundary_lower_bound"),
        "I4 release-to-hold boundary lower bound",
    )
    _require(
        i3_actions >= i3_count,
        "I3 action lower bound is below its boundary lower bound",
    )
    _require(
        opportunity_execution["source_opportunity_total_count"]
        == i1.get("total_boundary_count")
        and opportunity_execution["source_multi_ready_boundary_count"]
        == i1.get("multi_ready_boundary_count")
        and opportunity_execution["source_unique_screening_boundary_count"]
        == i1.get("unique_screening_boundary_count")
        and opportunity_execution["source_opportunity_manifest_sha256"]
        == i1.get("screening_manifest_sha256"),
        "I1 support-to-execution projection drift",
    )
    _require(
        decision_execution[
            "i3_safe_alternative_boundary_lower_bound"
        ]
        == i3_count
        and decision_execution["i3_screening_manifest_sha256"]
        == i3.get("screening_manifest_sha256"),
        "I3 support-to-execution projection drift",
    )
    _require(
        decision_execution[
            "i4_release_to_hold_boundary_lower_bound"
        ]
        == i4_count
        and decision_execution["i4_screening_manifest_sha256"]
        == i4.get("screening_manifest_sha256"),
        "I4 support-to-execution projection drift",
    )
    cross = _mapping(execution["cross_run"], "execution.cross_run")
    expected_cross = {
        "bag_projection_exact_match": (
            opportunity_execution["bag_projection_sha256"]
            == decision_execution["bag_projection_sha256"]
        ),
        "junction_state_exact_match": (
            opportunity_execution["junction_state_sha256"]
            == decision_execution["junction_state_sha256"]
        ),
        "deterministic_core_summary_exact_match": (
            opportunity_execution["deterministic_core_summary_sha256"]
            == decision_execution["deterministic_core_summary_sha256"]
        ),
    }
    _require(
        cross == expected_cross
        and all(expected_cross.values()),
        "census diagnostic runs are not deterministic-core equivalent",
    )
    if expected_execution_identity is not None:
        expected = _mapping(
            expected_execution_identity, "expected_execution_identity"
        )
        _require(
            binary == expected.get("binary"),
            "document binary differs from execution identity",
        )
        _require(
            protected == expected.get("protected_inputs"),
            "document inputs differ from execution identity",
        )
        _require(
            source_bundle == expected.get("source_bundle"),
            "document source bundle differs from execution identity",
        )
    return value


def _bundle_generation_id(document: Mapping[str, Any]) -> str:
    return canonical_sha256(
        {
            "manifest_schema": MANIFEST_SCHEMA,
            "census_self_sha256": document["self_sha256"],
            "binary_sha256": document["binary"]["sha256"],
            "source_bundle_sha256": document["source_bundle"][
                "bundle_sha256"
            ],
            "replay_hashes": document["replay_hashes"],
            "blocker": document["blocker"],
        }
    )


def _clone_fidelity_rows(
    document: Mapping[str, Any],
    *,
    bundle_generation_id: str,
) -> list[dict[str, Any]]:
    replay = _mapping(document["replay_hashes"], "bundle replay hashes")
    row: dict[str, Any] = {
        "audit_schema": CLONE_FIDELITY_SCHEMA,
        "status": STATUS,
        "evidence_scope": (
            "ONE_NOOP_THREE_WAY_REPLAY_FIDELITY_AUDIT_"
            "NOT_A_CAUSAL_INTERVENTION"
        ),
        "formal_pass_claimed": "false",
        "causal_label_count": 0,
        "bundle_generation_id": bundle_generation_id,
        "census_self_sha256": document["self_sha256"],
        "binary_path": document["binary"]["path"],
        "binary_sha256": document["binary"]["sha256"],
        "clone_event_ordinal": document["frozen_controls"][
            "clone_event_ordinal"
        ],
        "intervention_applied": "false",
        "source_baseline_exact_match": "true",
        "source_clone_exact_match": "true",
        "baseline_clone_exact_match": "true",
        "all_five_replay_hashes_exact_match": "true",
        "clone_replay_fidelity": "1.0",
    }
    for field in REPLAY_HASH_FIELDS:
        row[field] = replay[field]
    return [row]


def _component_ledger_rows(
    document: Mapping[str, Any],
    *,
    bundle_generation_id: str,
) -> list[dict[str, Any]]:
    support = _mapping(document["support"], "bundle support")
    descriptions = (
        (
            "source_order",
            "I1_source_order_swap",
            support["I1_source_order_swap"]["multi_ready_boundary_count"],
            0,
            False,
        ),
        (
            "merge_order",
            "I2_merge_request_order_swap",
            support["I2_merge_request_order_swap"][
                "eligible_live_multi_request_boundary_count"
            ],
            0,
            False,
        ),
        (
            "route_choice",
            "I3_next_edge",
            support["I3_next_edge"][
                "safe_alternative_boundary_lower_bound"
            ],
            0,
            True,
        ),
        (
            "hold_release",
            "I4_hold_release",
            support["I4_hold_release"][
                "release_to_hold_boundary_lower_bound"
            ],
            0,
            True,
        ),
        (
            "pibt",
            "I5_pibt_trigger",
            support["I5_pibt_trigger"][
                "strict_same_ready_slice_boundary_count"
            ],
            support["I5_pibt_trigger"][
                "prefilter_without_applicable_slice_count"
            ],
            False,
        ),
    )
    rows: list[dict[str, Any]] = []
    for (
        component,
        intervention_type,
        screening_count,
        prefilter_without_applicable_slice_count,
        lower_bound_only,
    ) in descriptions:
        item = _mapping(
            support[intervention_type],
            f"ledger support {intervention_type}",
        )
        rows.append(
            {
                "audit_schema": COMPONENT_LEDGER_SCHEMA,
                "status": STATUS,
                "evidence_scope": BUNDLE_EVIDENCE_SCOPE,
                "formal_pass_claimed": "false",
                "causal_label_count": 0,
                "bundle_generation_id": bundle_generation_id,
                "census_self_sha256": document["self_sha256"],
                "component": component,
                "intervention_type": intervention_type,
                "screening_support_count": screening_count,
                "formal_matched_boundary_count": 0,
                "formal_horizon_completion_count": 0,
                "prefilter_without_applicable_slice_count": (
                    prefilter_without_applicable_slice_count
                ),
                "lower_bound_only": str(lower_bound_only).lower(),
                "support_status": item["support_status"],
                "causal_contribution_status": (
                    "NOT_ESTIMATED_ZERO_CAUSAL_LABELS"
                ),
            }
        )
    return rows


def _matched_clone_report_bytes(
    document: Mapping[str, Any],
    *,
    bundle_generation_id: str,
    bound_hashes: Mapping[str, str],
) -> bytes:
    support = _mapping(document["support"], "report support")
    reasons = _array(document["blocker"]["reasons"], "report blocker reasons")
    lines = [
        "# G4IRSF14 matched-state clone blocker audit",
        "",
        f"- Audit schema: `{REPORT_SCHEMA}`",
        f"- Status: `{STATUS}`",
        "- Formal pass claimed: `false`",
        "- Formal v3 schema claimed: `false`",
        "- Causal label count: `0`",
        f"- Bundle generation ID: `{bundle_generation_id}`",
        f"- Census self SHA-256: `{document['self_sha256']}`",
        "",
        (
            "This report is a blocker/audit artifact. It does not contain "
            "matched causal labels and cannot satisfy the Stage 14E formal "
            "promotion gate."
        ),
        "",
        "## Executed evidence",
        "",
        (
            "One exact-binary, three-way no-op checkpoint replay established "
            "mechanism fidelity for all five replay hashes. Two passive "
            "original-1x diagnostic runs established opportunity screening "
            "support and live hard-gate evidence. No action-changing matched "
            "H_bag or H_system branch was run."
        ),
        "",
        "| Intervention | Strict screening support | Prefilter-only rows | "
        "Formal matched boundaries | Formal completions | Interpretation |",
        "|---|---:|---:|---:|---:|---|",
        (
            "| I1 source order | "
            f"{support['I1_source_order_swap']['multi_ready_boundary_count']} "
            "| 0 | 0 | 0 | complete source screening census |"
        ),
        (
            "| I2 merge order | "
            f"{support['I2_merge_request_order_swap']['eligible_live_multi_request_boundary_count']} "
            "| 0 | 0 | 0 | exact native live-eligible boundary count |"
        ),
        (
            "| I3 next edge | "
            f"{support['I3_next_edge']['safe_alternative_boundary_lower_bound']} "
            "| 0 | 0 | 0 | stored-trace lower bound |"
        ),
        (
            "| I4 hold/release | "
            f"{support['I4_hold_release']['release_to_hold_boundary_lower_bound']} "
            "| 0 | 0 | 0 | stored-trace lower bound |"
        ),
        (
            "| I5 PIBT trigger | "
            f"{support['I5_pibt_trigger']['strict_same_ready_slice_boundary_count']} "
            "| "
            f"{support['I5_pibt_trigger']['prefilter_without_applicable_slice_count']} "
            "| 0 | 0 | prefilter-only rows make no no-benefit claim; strict "
            "support starts only when `slice.applicable` constructs the "
            "identical ready slice |"
        ),
        "",
        "## Explicit blockers",
        "",
    ]
    lines.extend(f"- `{reason}`" for reason in reasons)
    lines.extend(
        [
            "",
            "## SHA-256 bindings",
            "",
            "| Artifact | SHA-256 |",
            "|---|---|",
        ]
    )
    for name in (
        "opportunity_census",
        "clone_fidelity",
        "causal_interventions",
        "causal_component_ledger",
    ):
        lines.append(
            f"| `{BUNDLE_PATHS[name].as_posix()}` | "
            f"`{bound_hashes[name]}` |"
        )
    lines.extend(
        [
            "",
            (
                "The clone manifest is published last as the transaction "
                "commit marker and binds this report plus every table above."
            ),
            "",
        ]
    )
    return "\n".join(lines).encode("utf-8")


def _bundle_manifest(
    document: Mapping[str, Any],
    *,
    bundle_generation_id: str,
    payloads: Mapping[str, bytes],
) -> dict[str, Any]:
    schemas = {
        "opportunity_census": SCHEMA,
        "matched_state_clone_report": REPORT_SCHEMA,
        "clone_fidelity": CLONE_FIDELITY_SCHEMA,
        "causal_interventions": CAUSAL_INTERVENTIONS_SCHEMA,
        "causal_component_ledger": COMPONENT_LEDGER_SCHEMA,
    }
    media_types = {
        "opportunity_census": "application/json",
        "matched_state_clone_report": "text/markdown",
        "clone_fidelity": "text/csv",
        "causal_interventions": "text/csv",
        "causal_component_ledger": "text/csv",
    }
    record_counts = {
        "opportunity_census": 1,
        "matched_state_clone_report": 1,
        "clone_fidelity": 1,
        "causal_interventions": 0,
        "causal_component_ledger": 5,
    }
    files: dict[str, Any] = {}
    for name, path in BUNDLE_PATHS.items():
        payload = payloads[name]
        files[name] = {
            "path": path.as_posix(),
            "schema": schemas[name],
            "media_type": media_types[name],
            "record_count": record_counts[name],
            "byte_count": len(payload),
            "sha256": _bytes_sha256(payload),
        }
    manifest: dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "status": STATUS,
        "evidence_scope": BUNDLE_EVIDENCE_SCOPE,
        "formal_pass_claimed": False,
        "formal_v3_schema_claimed": False,
        "causal_label_count": 0,
        "bundle_generation_id": bundle_generation_id,
        "manifest_path": CLONE_MANIFEST_PATH.as_posix(),
        "census_self_sha256": document["self_sha256"],
        "protected_inputs": document["protected_inputs"],
        "binary": document["binary"],
        "source_bundle": document["source_bundle"],
        "replay_hashes": document["replay_hashes"],
        "blocker": document["blocker"],
        "bundle_files": files,
    }
    manifest["self_sha256"] = _self_hash(manifest)
    return manifest


def build_blocker_bundle_payloads(
    document: Mapping[str, Any],
) -> dict[Path, bytes]:
    """Build the deterministic six-file Stage-14E blocker bundle."""

    validated = validate_census_document(document)
    generation_id = _bundle_generation_id(validated)
    named: dict[str, bytes] = {
        "opportunity_census": _json_file_bytes(validated),
        "clone_fidelity": _csv_file_bytes(
            CLONE_FIDELITY_FIELDS,
            _clone_fidelity_rows(
                validated, bundle_generation_id=generation_id
            ),
        ),
        "causal_interventions": _csv_file_bytes(
            CAUSAL_INTERVENTION_FIELDS,
            [],
        ),
        "causal_component_ledger": _csv_file_bytes(
            COMPONENT_LEDGER_FIELDS,
            _component_ledger_rows(
                validated, bundle_generation_id=generation_id
            ),
        ),
    }
    hashes = {name: _bytes_sha256(payload) for name, payload in named.items()}
    named["matched_state_clone_report"] = _matched_clone_report_bytes(
        validated,
        bundle_generation_id=generation_id,
        bound_hashes=hashes,
    )
    manifest = _bundle_manifest(
        validated,
        bundle_generation_id=generation_id,
        payloads=named,
    )
    result = {
        BUNDLE_PATHS[name]: payload for name, payload in named.items()
    }
    result[CLONE_MANIFEST_PATH] = _json_file_bytes(manifest)
    return result


def _parse_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OpportunityCensusError(f"{label} is not strict JSON UTF-8") from exc
    return _mapping(value, label)


def validate_blocker_bundle_payloads(
    payloads: Mapping[Path, bytes],
) -> dict[str, Any]:
    """Validate byte-exact bindings and blocker-only semantics in memory."""

    normalized = {Path(path): bytes(payload) for path, payload in payloads.items()}
    required = set(BUNDLE_PATHS.values()) | {CLONE_MANIFEST_PATH}
    _require(
        set(normalized) == required,
        "blocker bundle path inventory mismatch",
    )
    document = validate_census_document(
        _parse_json_bytes(
            normalized[OUTPUT_PATH],
            "bundle opportunity census",
        )
    )
    manifest = _parse_json_bytes(
        normalized[CLONE_MANIFEST_PATH],
        "bundle clone manifest",
    )
    required_manifest = {
        "schema",
        "status",
        "evidence_scope",
        "formal_pass_claimed",
        "formal_v3_schema_claimed",
        "causal_label_count",
        "bundle_generation_id",
        "manifest_path",
        "census_self_sha256",
        "protected_inputs",
        "binary",
        "source_bundle",
        "replay_hashes",
        "blocker",
        "bundle_files",
        "self_sha256",
    }
    _require(
        set(manifest) == required_manifest,
        "blocker manifest key inventory mismatch",
    )
    _require(manifest["schema"] == MANIFEST_SCHEMA, "manifest schema mismatch")
    _require(manifest["status"] == STATUS, "manifest status must remain partial")
    _require(
        manifest["evidence_scope"] == BUNDLE_EVIDENCE_SCOPE,
        "manifest evidence scope mismatch",
    )
    _require(
        manifest["formal_pass_claimed"] is False,
        "manifest claimed formal pass",
    )
    _require(
        manifest["formal_v3_schema_claimed"] is False,
        "manifest claimed formal v3 schema",
    )
    _require(
        manifest["causal_label_count"] == 0,
        "manifest claimed causal labels",
    )
    _require(
        manifest["manifest_path"] == CLONE_MANIFEST_PATH.as_posix(),
        "manifest path mismatch",
    )
    _require_sha256(manifest["self_sha256"], "manifest self_sha256")
    _require(
        manifest["self_sha256"] == _self_hash(manifest),
        "manifest self hash drift",
    )
    _require(
        manifest["bundle_generation_id"]
        == _bundle_generation_id(document),
        "bundle generation ID drift",
    )
    for field in (
        "census_self_sha256",
        "protected_inputs",
        "binary",
        "source_bundle",
        "replay_hashes",
        "blocker",
    ):
        expected_value = (
            document["self_sha256"]
            if field == "census_self_sha256"
            else document[field]
        )
        _require(
            manifest[field] == expected_value,
            f"manifest-to-census binding drift: {field}",
        )
    files = _mapping(manifest["bundle_files"], "manifest bundle_files")
    _require(
        set(files) == set(BUNDLE_PATHS),
        "manifest file inventory mismatch",
    )
    for name, path in BUNDLE_PATHS.items():
        entry = _mapping(files[name], f"manifest bundle_files.{name}")
        _require(entry.get("path") == path.as_posix(), f"{name} path drift")
        _require(
            entry.get("sha256") == _bytes_sha256(normalized[path]),
            f"{name} SHA binding drift",
        )
        _require(
            entry.get("byte_count") == len(normalized[path]),
            f"{name} byte count drift",
        )
        _require(
            ".v3" not in str(entry.get("schema", "")).lower(),
            f"{name} improperly claims a formal v3 schema",
        )
    expected = build_blocker_bundle_payloads(document)
    for path in required:
        _require(
            normalized[path] == expected[path],
            f"blocker bundle canonical payload drift: {path.as_posix()}",
        )
    return {"document": document, "manifest": manifest}


def validate_published_blocker_bundle(
    bundle_root: Path = ROOT,
) -> dict[str, Any]:
    root = bundle_root.resolve()
    payloads: dict[Path, bytes] = {}
    for relative in set(BUNDLE_PATHS.values()) | {CLONE_MANIFEST_PATH}:
        path = (root / relative).resolve(strict=True)
        _require(
            path.is_relative_to(root),
            f"bundle path escaped publication root: {relative}",
        )
        payloads[relative] = path.read_bytes()
    validated = validate_blocker_bundle_payloads(payloads)
    document = _mapping(
        validated["document"], "published census document"
    )
    binary = _mapping(document["binary"], "published binary identity")
    binary_path = Path(str(binary["path"]))
    _require(
        binary_path.is_absolute() and binary_path.is_file(),
        "published exact binary is missing from disk",
    )
    _require(
        file_sha256(binary_path) == binary["sha256"],
        "published exact binary current-disk SHA drift",
    )
    source = _mapping(
        document["source_bundle"], "published source bundle"
    )
    source_rows = _array(source["files"], "published source bundle files")
    recorded_paths = tuple(
        Path(str(_mapping(row, "published source row")["path"]))
        for row in source_rows
    )
    _require(
        source_bundle_identity(ROOT, recorded_paths) == source,
        "published source bundle current-disk identity drift",
    )
    _require(
        _protected_input_identity(ROOT) == document["protected_inputs"],
        "published protected input current-disk identity drift",
    )
    return validated


def generate_opportunity_census(
    *,
    binary: Path,
    search_path: Path | None = None,
    root: Path = ROOT,
    output_path: Path | None = None,
    bundle_root: Path | None = None,
    event_executor: Callable[..., Mapping[str, Any]] | None = None,
    clone_executor: Callable[..., Mapping[str, Any]] | None = None,
    source_paths: Sequence[Path] = SOURCE_PATHS,
    opportunity_trace_limit: int = OPPORTUNITY_TRACE_LIMIT,
    decision_trace_limit: int = DECISION_TRACE_LIMIT,
    clone_event_ordinal: int = CLONE_EVENT_ORDINAL,
    write: bool = True,
) -> dict[str, Any]:
    """Run and optionally publish the original-1x blocker-only census."""

    custom_executor_injected = (
        event_executor is not None or clone_executor is not None
    )
    _require(
        not (write and custom_executor_injected),
        "CUSTOM_EXECUTOR_PUBLICATION_FORBIDDEN",
    )
    _require(
        opportunity_trace_limit == OPPORTUNITY_TRACE_LIMIT,
        f"opportunity_trace_limit must be frozen at {OPPORTUNITY_TRACE_LIMIT}",
    )
    _require(
        decision_trace_limit == DECISION_TRACE_LIMIT,
        f"decision_trace_limit must be frozen at {DECISION_TRACE_LIMIT}",
    )
    _require(
        clone_event_ordinal == CLONE_EVENT_ORDINAL,
        f"clone_event_ordinal must be frozen at {CLONE_EVENT_ORDINAL}",
    )
    binary, search_path = _resolve_binary(binary, search_path)
    model_path = (root / MODEL_PATH).resolve(strict=True)
    _require(file_sha256(model_path) == MODEL_SHA256, "frozen scorer model drift")
    protected = _protected_input_identity(root)
    prefix = g12.load_input_prefix(FULL_SEGMENT_COUNT, root=root)
    _require(
        prefix.size_segments == FULL_SEGMENT_COUNT
        and prefix.raw_bag_count == FULL_RAW_BAG_COUNT
        and prefix.prefix_sha256 == TASK_RAW_SHA256,
        "full protected input prefix identity drift",
    )
    expected_segment_ids = [
        str(row["segment_id"]) for row in prefix.rows
    ]
    _require(
        len(set(expected_segment_ids)) == FULL_SEGMENT_COUNT,
        "protected segment IDs are not unique",
    )
    nodes, edges, heuristic = canonical_graph_records(
        assert_canonical_map(root / MAP_PATH)
    )
    bag_records = g12.binding_bag_records(prefix)
    identity = execution_identity(
        binary=binary, root=root, source_paths=source_paths
    )
    _require(
        identity["protected_inputs"] == protected,
        "pre-execution protected identity disagreement",
    )

    if event_executor is None or clone_executor is None:
        from czr005 import cpp_backend

        if event_executor is None:
            event_executor = cpp_backend.g4irsf11_event_runtime_from_records
        if clone_executor is None:
            clone_executor = (
                cpp_backend.g4irsf14_state_clone_noop_rerun_from_records
            )
    _require(callable(event_executor), "event executor is not callable")
    _require(callable(clone_executor), "clone executor is not callable")

    clone_payload = _call_checked(
        clone_executor,
        _clone_request(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=bag_records,
            binary=binary,
            search_path=search_path,
            model_path=model_path,
            clone_event_ordinal=clone_event_ordinal,
        ),
        identity=identity,
        binary=binary,
        root=root,
        source_paths=source_paths,
        phase="clone_noop",
    )
    clone_evidence = _validate_clone_payload(
        clone_payload,
        clone_event_ordinal=clone_event_ordinal,
        binary=identity["binary"],
    )

    opportunity_payload = _call_checked(
        event_executor,
        _runtime_request(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=bag_records,
            binary=binary,
            search_path=search_path,
            model_path=model_path,
            mode="opportunity",
            opportunity_trace_limit=opportunity_trace_limit,
            decision_trace_limit=decision_trace_limit,
        ),
        identity=identity,
        binary=binary,
        root=root,
        source_paths=source_paths,
        phase="opportunity_run",
    )
    opportunity_evidence = _validate_runtime_payload(
        opportunity_payload,
        binary=identity["binary"],
        expected_segment_ids=expected_segment_ids,
        opportunity_enabled=True,
        opportunity_limit=opportunity_trace_limit,
        label="opportunity_run",
    )

    decision_payload = _call_checked(
        event_executor,
        _runtime_request(
            node_records=nodes,
            edge_records=edges,
            heuristic_time=heuristic,
            bag_records=bag_records,
            binary=binary,
            search_path=search_path,
            model_path=model_path,
            mode="decision",
            opportunity_trace_limit=opportunity_trace_limit,
            decision_trace_limit=decision_trace_limit,
        ),
        identity=identity,
        binary=binary,
        root=root,
        source_paths=source_paths,
        phase="decision_run",
    )
    decision_evidence = _validate_runtime_payload(
        decision_payload,
        binary=identity["binary"],
        expected_segment_ids=expected_segment_ids,
        opportunity_enabled=False,
        opportunity_limit=0,
        label="decision_run",
    )

    bag_match = (
        opportunity_evidence["bag_projection_sha256"]
        == decision_evidence["bag_projection_sha256"]
    )
    junction_match = (
        opportunity_evidence["junction_state_sha256"]
        == decision_evidence["junction_state_sha256"]
    )
    core_match = (
        opportunity_evidence["deterministic_core_summary"]
        == decision_evidence["deterministic_core_summary"]
    )
    _require(
        bag_match and junction_match and core_match,
        "diagnostic instrumentation changed deterministic core outcomes",
    )

    i1 = _source_support(
        opportunity_payload, opportunity_evidence["summary"]
    )
    i2, i2_raw = _i2_support(opportunity_evidence["summary"])
    i3, i4 = _decision_support(
        decision_payload,
        decision_evidence["summary"],
        decision_trace_limit=decision_trace_limit,
    )
    i5, p2_raw = _i5_support(opportunity_evidence["summary"])
    # The passive telemetry and decision runs must agree on the raw I2/P2
    # counters; otherwise no support decision is publishable.
    _require(
        i2_raw
        == {
            field: _strict_int(
                decision_evidence["summary"].get(field),
                f"decision I2 raw.{field}",
            )
            for field in I2_RAW_COUNTER_FIELDS
        },
        "I2 raw counters changed across diagnostic modes",
    )
    _require(
        p2_raw
        == {
            field: _strict_int(
                decision_evidence["summary"].get(field),
                f"decision P2 raw.{field}",
            )
            for field in P2_RAW_COUNTER_FIELDS
        },
        "P2 raw counters changed across diagnostic modes",
    )
    support = {
        "I1_source_order_swap": i1,
        "I2_merge_request_order_swap": i2,
        "I3_next_edge": i3,
        "I4_hold_release": i4,
        "I5_pibt_trigger": i5,
    }
    reasons = _blocker_reasons(support)

    execution = {
        "clone_noop": clone_evidence,
        "opportunity_run": {
            "bag_projection_sha256": opportunity_evidence[
                "bag_projection_sha256"
            ],
            "junction_state_sha256": opportunity_evidence[
                "junction_state_sha256"
            ],
            "deterministic_core_summary_sha256": opportunity_evidence[
                "deterministic_core_summary_sha256"
            ],
            "source_opportunity_total_count": i1[
                "total_boundary_count"
            ],
            "source_multi_ready_boundary_count": i1[
                "multi_ready_boundary_count"
            ],
            "source_unique_screening_boundary_count": i1[
                "unique_screening_boundary_count"
            ],
            "source_opportunity_manifest_sha256": i1[
                "screening_manifest_sha256"
            ],
            "g4irsf14_i2_live_eligible_multi_request_boundary_count": (
                i2_raw[
                    "g4irsf14_i2_live_eligible_multi_request_boundary_count"
                ]
            ),
            "g4irsf14_i5_prefilter_candidate_count": p2_raw[
                "g4irsf14_i5_prefilter_candidate_count"
            ],
            "g4irsf14_i5_applicable_ready_slice_boundary_count": (
                p2_raw[
                    "g4irsf14_i5_applicable_ready_slice_boundary_count"
                ]
            ),
        },
        "decision_run": {
            "bag_projection_sha256": decision_evidence[
                "bag_projection_sha256"
            ],
            "junction_state_sha256": decision_evidence[
                "junction_state_sha256"
            ],
            "deterministic_core_summary_sha256": decision_evidence[
                "deterministic_core_summary_sha256"
            ],
            "i3_screening_manifest_sha256": i3[
                "screening_manifest_sha256"
            ],
            "i3_safe_alternative_boundary_lower_bound": i3[
                "safe_alternative_boundary_lower_bound"
            ],
            "i4_screening_manifest_sha256": i4[
                "screening_manifest_sha256"
            ],
            "i4_release_to_hold_boundary_lower_bound": i4[
                "release_to_hold_boundary_lower_bound"
            ],
            "g4irsf14_i2_live_eligible_multi_request_boundary_count": (
                i2_raw[
                    "g4irsf14_i2_live_eligible_multi_request_boundary_count"
                ]
            ),
            "g4irsf14_i5_prefilter_candidate_count": p2_raw[
                "g4irsf14_i5_prefilter_candidate_count"
            ],
            "g4irsf14_i5_applicable_ready_slice_boundary_count": (
                p2_raw[
                    "g4irsf14_i5_applicable_ready_slice_boundary_count"
                ]
            ),
        },
        "cross_run": {
            "bag_projection_exact_match": bag_match,
            "junction_state_exact_match": junction_match,
            "deterministic_core_summary_exact_match": core_match,
        },
    }
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "status": STATUS,
        "evidence_scope": EVIDENCE_SCOPE,
        "formal_pass_claimed": False,
        "causal_label_count": 0,
        "generated_by": "scripts/eval/g4irsf14_opportunity_census.py",
        "protected_inputs": protected,
        "binary": identity["binary"],
        "source_bundle": identity["source_bundle"],
        "frozen_controls": {
            **dict(FROZEN_RUNTIME_CONTROLS),
            "opportunity_trace_limit": opportunity_trace_limit,
            "decision_trace_limit": decision_trace_limit,
            "clone_event_ordinal": clone_event_ordinal,
        },
        "replay_hashes": clone_evidence["replay_hashes"],
        "raw_hard_gates": {
            "clone_noop": clone_evidence["raw_hard_gates"],
            "opportunity_run": opportunity_evidence["raw_hard_gates"],
            "decision_run": decision_evidence["raw_hard_gates"],
        },
        "execution": execution,
        "support": support,
        "i2_raw_counters": i2_raw,
        "p2_raw_counters": p2_raw,
        "blocker": {
            "code": FORMAL_BLOCKER_CODE,
            "reasons": reasons,
            "minimum_required_complete_interventions": (
                MIN_FORMAL_INTERVENTIONS
            ),
            "unique_complete_h_bag_h_system_intervention_count": 0,
            "h_system_intervention_count": 0,
            "taxonomy_complete": False,
            "formal_pass_allowed": False,
        },
    }
    document["self_sha256"] = _self_hash(document)
    validated = validate_census_document(
        document, expected_execution_identity=identity
    )
    _assert_execution_identity(
        identity,
        binary=binary,
        root=root,
        source_paths=source_paths,
        phase="before_publication",
    )
    if write:
        publication_root = (
            bundle_root if bundle_root is not None else root
        ).resolve()
        destination = output_path or publication_root / OUTPUT_PATH
        if not destination.is_absolute():
            destination = publication_root / destination
        destination = destination.resolve()
        _require(
            destination == (publication_root / OUTPUT_PATH).resolve(),
            "census output must use its canonical blocker-bundle path",
        )
        relative_payloads = build_blocker_bundle_payloads(validated)
        _assert_execution_identity(
            identity,
            binary=binary,
            root=root,
            source_paths=source_paths,
            phase="bundle_staged_before_commit",
        )
        disk_payloads = {
            publication_root / relative: payload
            for relative, payload in relative_payloads.items()
        }
        _atomic_write_bundle(
            disk_payloads,
            commit_path=publication_root / CLONE_MANIFEST_PATH,
        )
        published = validate_published_blocker_bundle(publication_root)
        _require(
            published["document"] == validated,
            "published census differs from validated in-memory census",
        )
    return validated


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the fail-closed original-1x G4IRSF14 opportunity census "
            "and publish blocker-only evidence"
        )
    )
    parser.add_argument(
        "--binary",
        type=Path,
        default=None,
        help="exact czr005_cpp native extension to load",
    )
    parser.add_argument(
        "--search-path",
        type=Path,
        default=None,
        help="must be exactly the directory containing --binary",
    )
    parser.add_argument(
        "--bundle-root",
        type=Path,
        default=ROOT,
        help=(
            "root containing canonical outputs/ and artifacts/ bundle paths "
            f"(default: {ROOT})"
        ),
    )
    parser.add_argument(
        "--validate-bundle",
        action="store_true",
        help="validate an existing blocker bundle without running native code",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help=f"output JSON (default: {OUTPUT_PATH.as_posix()})",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.validate_bundle:
        validated = validate_published_blocker_bundle(args.bundle_root)
        print(
            json.dumps(
                {
                    "status": validated["manifest"]["status"],
                    "bundle_root": str(args.bundle_root),
                    "manifest_self_sha256": validated["manifest"][
                        "self_sha256"
                    ],
                    "causal_label_count": 0,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if args.binary is None:
        parser.error("--binary is required unless --validate-bundle is used")
    document = generate_opportunity_census(
        binary=args.binary,
        search_path=args.search_path,
        output_path=args.output,
        bundle_root=args.bundle_root,
    )
    print(
        json.dumps(
            {
                "status": document["status"],
                "output": str(args.output),
                "self_sha256": document["self_sha256"],
                "blocker": document["blocker"]["code"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
