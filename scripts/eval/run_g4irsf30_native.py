#!/usr/bin/env python3
"""Run the unchanged local S4 stack on the faithful G30 3x workload.

This is a thin G30 contract adapter over the tested G27--G29 implementation.
It changes the workload population and HCA release root, while retaining
S4/J2/E2, one-junction FIFO arbitration, the service-aware static potential,
the fixed observation-bias stream, and fault-only structural local values.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend
from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf24_native_race as g24
from scripts.eval import run_g4irsf26_paper_experiments as g26
from scripts.eval import run_g4irsf27_fault_values as g27_fault
from scripts.eval import run_g4irsf29_native as g29


SCHEMA = "czr005.g4irsf30.s4_case.v1"
AGGREGATE_SCHEMA = "czr005.g4irsf30.s4_aggregate.v1"
WORKLOAD_SCHEMA = "czr005.g4irsf30.workload_manifest.v1"
HCA_CASE_PROTOCOL_SCHEMA = "czr005.g4irsf30.hca_case_protocol.v1"
WORKLOAD_ID = "g4irsf30_flight_densified_3x"
WORKLOAD_PROTOCOL = "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_3X"
FULL_RAW_BAGS = 85_518
FULL_SEGMENTS = 130_809
FIXED_HORIZON = g29.FIXED_HORIZON
G30_MAX_EVENTS = 60_000_000
HCA_START_EPOCH = 8_260
HCA_MAX_EPOCHS = 90_000
HCA_END_EPOCH = 98_259

COMPLETE = "COMPLETE_G30_3X_ADMISSION"
COMPLETE_OWN_SOURCE = "COMPLETE_G30_3X_OWN_SOURCE_CAPACITY_ADMISSION"
COMPLETE_FIXED_HORIZON_CAPACITY = (
    "COMPLETE_G30_3X_FIXED_HORIZON_CAPACITY"
)
COMPLETE_STATUSES = frozenset(
    (COMPLETE, COMPLETE_OWN_SOURCE, COMPLETE_FIXED_HORIZON_CAPACITY)
)
OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE = (
    "OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE"
)
DRY_RUN_READY = "READY_G30_DRY_RUN"
BLOCKED_RELEASE = "BLOCKED_G30_EXACT_RELEASE_INCOMPLETE"
FAILED = "FAILED_G30_3X_ADMISSION"

CASE_IDS = g29.CASE_IDS
DEFAULT_CANONICAL = (
    ROOT / "artifacts/tasks/g4irsf30/inputdata_flight_densified_3x.jsonl"
)
DEFAULT_MANIFEST = ROOT / "artifacts/tasks/g4irsf30/g4irsf30_workload_manifest.json"
DEFAULT_HCA_ROOT = ROOT / "outputs/runtime/g4irsf30_hca"
DEFAULT_CASE_ROOT = ROOT / "outputs/runtime/g4irsf30_native"
DEFAULT_AGGREGATE = ROOT / "outputs/tables/g4irsf30_native.json"
RESUME_AGGREGATE_NAME = "aggregate.json"

Executor = Callable[..., Mapping[str, Any]]


class Native30Error(RuntimeError):
    """Raised when a G30 case cannot support the requested claim."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Native30Error(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise Native30Error(f"canonical row {line_number} is not an object")
            rows.append(value)
    if not rows:
        raise Native30Error("G30 canonical workload is empty")
    return rows


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def load_workload(
    canonical_path: Path,
    manifest_path: Path,
    *,
    earliest_raw_bags: int | None = None,
) -> tuple[harness.InputPrefix, dict[str, Any], dict[str, Any]]:
    """Load the registered 3x population and retain whole bags for a canary."""

    manifest = _read_json(manifest_path)
    if manifest.get("schema") != WORKLOAD_SCHEMA or manifest.get("status") != "COMPLETE":
        raise Native30Error("G30 workload manifest is not complete")
    if manifest.get("protocol") != WORKLOAD_PROTOCOL:
        raise Native30Error("G30 workload is not the schedule-preserving 3x stream")
    rows = _read_jsonl(canonical_path)
    required = {
        "segment_id",
        "task_id",
        "original_entry_time",
        "pass_time",
        "std",
        "start",
        "goal",
    }
    if any(not required.issubset(row) for row in rows):
        raise Native30Error("G30 canonical row lacks a runtime field")
    segment_ids = [str(row["segment_id"]) for row in rows]
    if len(segment_ids) != len(set(segment_ids)):
        raise Native30Error("G30 canonical segment IDs are not unique")
    raw_count = len({int(row["task_id"]) for row in rows})
    manifest_raw = g29._manifest_count(
        manifest, "raw_task_count", "raw_bag_count", "raw_order_count", "raw_bags"
    )
    manifest_segments = g29._manifest_count(
        manifest, "expanded_segment_count", "segment_count", "expanded_segments"
    )
    if raw_count != FULL_RAW_BAGS or len(rows) != FULL_SEGMENTS:
        raise Native30Error("G30 canonical workload is not the registered 3x population")
    if manifest_raw not in (None, raw_count) or manifest_segments not in (
        None,
        len(rows),
    ):
        raise Native30Error("G30 manifest counts disagree with its canonical workload")

    selected = g29._select_whole_raw_bags(rows, earliest_raw_bags)
    selected_tasks = {int(row["task_id"]) for row in selected}
    if earliest_raw_bags is not None and len(selected_tasks) != min(
        earliest_raw_bags, raw_count
    ):
        raise Native30Error("earliest-raw selection did not retain the requested bags")
    prefix = harness.InputPrefix(
        len(selected),
        selected,
        "",
        len(selected_tasks),
        str(selected[0]["segment_id"]),
        str(selected[-1]["segment_id"]),
    )
    selection = {
        "mode": "full" if earliest_raw_bags is None else "earliest_raw_bags",
        "requested_earliest_raw_bags": earliest_raw_bags,
        "selected_raw_bag_count": prefix.raw_bag_count,
        "selected_segment_count": prefix.size_segments,
        "whole_raw_bags_retained": True,
        "ordering": "min(original_entry_time),task_id",
        "fixed_denominator_raw_bags": FULL_RAW_BAGS,
        "fixed_population_segments": FULL_SEGMENTS,
    }
    return prefix, manifest, selection


def release_source_contract(resolved: Mapping[str, Any]) -> dict[str, Any]:
    return g29.release_source_contract(resolved)


def default_hca_run_dir(case_id: str) -> Path:
    contract = release_source_contract(g29.resolve_case(case_id))
    return DEFAULT_HCA_ROOT / str(contract["source_case_id"]) / str(
        contract["source_run_id"]
    )


def _lifecycle_releases(path: Path) -> dict[str, float]:
    releases: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            segment_id = str(row.get("segment_id", ""))
            if not segment_id:
                raise Native30Error("HCA lifecycle lacks segment_id")
            if segment_id in releases:
                raise Native30Error(f"duplicate HCA lifecycle segment: {segment_id}")
            releases[segment_id] = float(row["release_epoch"])
    return releases


def apply_hca_release_lifecycle(
    prefix: harness.InputPrefix,
    *,
    lifecycle_path: Path,
    metrics_path: Path,
    full_required: bool,
    release_contract: Mapping[str, Any],
) -> tuple[harness.InputPrefix | None, dict[str, Any], dict[str, Any]]:
    """Use exact HCA releases when complete, otherwise admit a trusted capacity run."""

    releases = _lifecycle_releases(lifecycle_path)
    metrics = _read_json(metrics_path) if metrics_path.is_file() else {}
    run_status_path = lifecycle_path.with_name("run_status.json")
    case_protocol_path = lifecycle_path.parent.parent / "case_protocol.json"
    run_status = _read_json(run_status_path) if run_status_path.is_file() else {}
    case_protocol = _read_json(case_protocol_path) if case_protocol_path.is_file() else {}
    protocol_case = case_protocol.get("case")
    if not isinstance(protocol_case, Mapping):
        protocol_case = {}
    fixed_window = case_protocol.get("fixed_window")
    if not isinstance(fixed_window, Mapping):
        fixed_window = {}
    protocol_workload = case_protocol.get("workload")
    if not isinstance(protocol_workload, Mapping):
        protocol_workload = {}
    expected_speed = float(release_contract["expected_speed_mps"])
    source_gates = {
        "case_protocol_schema": case_protocol.get("schema")
        == HCA_CASE_PROTOCOL_SCHEMA,
        "source_case_id": protocol_case.get("case_id")
        == release_contract["source_case_id"],
        "source_case_speed": isinstance(protocol_case.get("speed_mps"), (int, float))
        and math.isclose(
            float(protocol_case["speed_mps"]), expected_speed, abs_tol=1.0e-12
        ),
        "source_case_no_fault": protocol_case.get("fault_schedule")
        == release_contract["expected_fault_schedule"],
        "source_run_complete": run_status.get("status") == "complete",
        "source_run_id": run_status.get("run_id")
        == release_contract["source_run_id"],
        "source_run_speed": isinstance(run_status.get("speed_mps"), (int, float))
        and math.isclose(
            float(run_status["speed_mps"]), expected_speed, abs_tol=1.0e-12
        ),
        "source_run_no_fault": run_status.get("fault_schedule")
        == release_contract["expected_fault_schedule"],
    }
    selected_ids = {str(row["segment_id"]) for row in prefix.rows}
    missing = selected_ids - releases.keys()
    reported_released = metrics.get("released_segment_count")
    full_gates = {
        "selected_lifecycle_coverage_complete": not missing,
        "full_selected_population": (
            prefix.size_segments == FULL_SEGMENTS
            and prefix.raw_bag_count == FULL_RAW_BAGS
        ),
        "hca_reported_all_segments_released": reported_released == FULL_SEGMENTS,
        "hca_canonical_segment_count_matches": metrics.get(
            "canonical_segment_count"
        )
        in (None, FULL_SEGMENTS),
        "hca_canonical_raw_bag_count_matches": metrics.get(
            "canonical_raw_bag_count"
        )
        in (None, FULL_RAW_BAGS),
    }
    exact_passed = all(source_gates.values()) and not missing and (
        not full_required
        or all(
            full_gates[name]
            for name in (
                "full_selected_population",
                "hca_reported_all_segments_released",
                "hca_canonical_segment_count_matches",
                "hca_canonical_raw_bag_count_matches",
            )
        )
    )
    complete_raw = metrics.get("canonical_complete_raw_bag_count")
    incomplete_raw = metrics.get("canonical_incomplete_raw_bag_count")
    fixed_population_source_gates = {
        "protocol_start_epoch": fixed_window.get("start_epoch")
        == HCA_START_EPOCH,
        "protocol_max_epochs": fixed_window.get("max_epochs") == HCA_MAX_EPOCHS,
        "protocol_end_epoch": fixed_window.get("end_epoch") == HCA_END_EPOCH,
        "run_start_epoch": run_status.get("start_epoch") == HCA_START_EPOCH,
        "run_max_epochs": run_status.get("max_epochs") == HCA_MAX_EPOCHS,
        "run_returncode_zero": run_status.get("returncode") == 0,
        "protocol_workload": protocol_workload.get("protocol")
        == WORKLOAD_PROTOCOL,
        "protocol_raw_population": protocol_workload.get("raw_task_count")
        == FULL_RAW_BAGS,
        "protocol_segment_population": protocol_workload.get(
            "expanded_segment_count"
        )
        == FULL_SEGMENTS,
        "metrics_raw_population": metrics.get("canonical_raw_bag_count")
        == FULL_RAW_BAGS,
        "metrics_segment_population": metrics.get("canonical_segment_count")
        == FULL_SEGMENTS,
        "metrics_raw_population_partition": (
            isinstance(complete_raw, int)
            and isinstance(incomplete_raw, int)
            and complete_raw + incomplete_raw == FULL_RAW_BAGS
        ),
        "reported_release_matches_lifecycle": (
            isinstance(reported_released, int)
            and reported_released == len(releases)
        ),
    }
    own_source_capacity = (
        full_required
        and full_gates["full_selected_population"]
        and all(source_gates.values())
        and all(fixed_population_source_gates.values())
        and isinstance(reported_released, int)
        and 0 <= reported_released < FULL_SEGMENTS
    )
    passed = exact_passed or own_source_capacity
    fault_scope = (
        release_contract["comparison_scope"]
        == "fixed_population_fault_capacity_not_segment_paired"
    )
    gate = {
        "pass": passed,
        "mode": (
            "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY"
            if own_source_capacity
            else "REFERENCE_RELEASE_FULL_NON_PAIRED_FAULT"
            if full_required and fault_scope
            else "EXACT_PAIRED_FULL"
            if full_required
            else "EXACT_PAIRED_CANARY"
        ),
        "release_source_contract": dict(release_contract),
        "release_source_gates": source_gates,
        "lifecycle_path": str(lifecycle_path),
        "metrics_path": str(metrics_path),
        "run_status_path": str(run_status_path),
        "case_protocol_path": str(case_protocol_path),
        "selected_segment_count": prefix.size_segments,
        "lifecycle_segment_count": len(releases),
        "missing_selected_segment_count": len(missing),
        "full_gates": full_gates,
        "fixed_population_source_gates": fixed_population_source_gates,
        "exact_release_applied": exact_passed,
        "release_pairing": "NOT_PAIRED" if own_source_capacity else "EXACT",
        "arrival_source": (
            "canonical_scheduled_pass_time"
            if own_source_capacity
            else "hca_segment_lifecycle_release_epoch"
        ),
        "full_population_capacity_comparison_allowed": passed,
        "full_outcome_timing_comparison_allowed": (
            exact_passed
            and full_required
            and not fault_scope
            and metrics.get("comparison_eligible") is True
        ),
        "survivor_only_full_claim_allowed": False,
        "claim_boundary": (
            "same_canonical_scheduled_arrivals_each_framework_uses_its_own_"
            "source_admission_fixed_horizon_completion_only_not_release_or_"
            "timing_paired"
            if own_source_capacity
            else "hca_release_lifecycle_applied_to_selected_s4_segments"
        ),
    }
    capacity = g29.capacity_view(
        metrics,
        expected_segments=(FULL_SEGMENTS if full_required else prefix.size_segments),
        expected_raw_bags=(FULL_RAW_BAGS if full_required else prefix.raw_bag_count),
    )
    if not passed:
        return None, gate, capacity

    if own_source_capacity:
        gate["scheduled_arrival"] = {
            "segment_count": prefix.size_segments,
            "source_field": "canonical.pass_time",
            "hca_released_segment_count": reported_released,
        }
        return prefix, gate, capacity

    adjusted: list[dict[str, Any]] = []
    deltas: list[float] = []
    for source in prefix.rows:
        row = dict(source)
        release = releases[str(row["segment_id"])]
        deltas.append(release - float(row["pass_time"]))
        row["pass_time"] = release
        adjusted.append(row)
    aligned = harness.InputPrefix(
        len(adjusted),
        tuple(adjusted),
        "",
        prefix.raw_bag_count,
        prefix.first_segment_id,
        prefix.last_segment_id,
    )
    gate["alignment"] = {
        "aligned_segment_count": len(adjusted),
        "release_minus_scheduled_mean_seconds": statistics.fmean(deltas),
        "release_minus_scheduled_min_seconds": min(deltas),
        "release_minus_scheduled_max_seconds": max(deltas),
    }
    return aligned, gate, capacity


def prepare_native_request(
    resolved: Mapping[str, Any],
    prefix: harness.InputPrefix,
    *,
    binary: Path,
    canary: bool,
) -> tuple[
    dict[str, Any],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    dict[str, Any],
]:
    request, runtime_rows, rejected, local = g29.prepare_native_request(
        resolved, prefix, binary=binary, canary=canary
    )
    request["scenario"] = (
        f"g4irsf30_{resolved['case_id']}_{'canary' if canary else 'full'}"
    )
    if not canary:
        request["max_simulation_time"] = FIXED_HORIZON
        request["max_events"] = G30_MAX_EVENTS
    return request, runtime_rows, rejected, local


def event_budget_evidence(
    request: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    full_required: bool,
) -> dict[str, Any]:
    """Register the existing G26 all-day event ceiling for G30 full runs."""

    requested = request.get("max_events")
    declared = summary.get("declared_max_events")
    event_count = summary.get("event_count")
    request_matches = requested == G30_MAX_EVENTS
    summary_matches = declared == G30_MAX_EVENTS
    event_count_within_budget = (
        isinstance(event_count, int) and event_count <= G30_MAX_EVENTS
    )
    event_limit_not_reached = summary.get("event_limit_reached") is False
    return {
        "required": full_required,
        "expected_max_events": G30_MAX_EVENTS,
        "request_max_events": requested,
        "summary_declared_max_events": declared,
        "summary_event_count": event_count,
        "summary_event_limit_reached": summary.get("event_limit_reached"),
        "request_matches": request_matches,
        "summary_matches": summary_matches,
        "event_count_within_budget": event_count_within_budget,
        "event_limit_not_reached": event_limit_not_reached,
        "pass": (
            request_matches
            and summary_matches
            and event_count_within_budget
            and event_limit_not_reached
        )
        if full_required
        else True,
    }


def _blocked_result(
    *,
    case_id: str,
    selection: Mapping[str, Any],
    release_gate: Mapping[str, Any],
    hca_capacity: Mapping[str, Any],
    release_contract: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": BLOCKED_RELEASE,
        "case_id": case_id,
        "workload_id": WORKLOAD_ID,
        "workload_protocol": WORKLOAD_PROTOCOL,
        "selection": dict(selection),
        "exact_release_gate": dict(release_gate),
        "hca_capacity_view": dict(hca_capacity),
        "release_source_contract": dict(release_contract),
        "native_execution_started": False,
        "claim_boundary": (
            "incomplete_HCA_release_is_capacity_evidence_not_an_exact_paired_"
            "survivor_cohort"
        ),
    }


def _capacity_only_timing(
    outcome: Mapping[str, Any], release_gate: Mapping[str, Any]
) -> dict[str, Any]:
    """Prevent own-Source capacity evidence from becoming a timing claim."""

    return {
        "status": "NOT_MEASURED",
        "reason": "own_source_fixed_horizon_capacity_only_not_timing_paired",
        "selected_raw_bag_count": outcome["selected_raw_bag_count"],
        "completed_raw_bag_count": outcome["completed_raw_bag_count"],
        "fixed_population_success": outcome["success"][
            "primary_completed_raw_bags"
        ],
        "comparison_protocol": release_gate["mode"],
        "full_outcome_timing_comparison_allowed": False,
    }


def _own_source_timing(
    resolved: Mapping[str, Any],
    outcome: Mapping[str, Any],
    release_gate: Mapping[str, Any],
    timing: Mapping[str, Any],
) -> dict[str, Any]:
    """Keep intrinsic full-population timing without creating a fresh verdict."""

    selected = int(outcome["selected_raw_bag_count"])
    completed = int(outcome["completed_raw_bag_count"])
    if (
        resolved["group"] != "fault"
        and selected == FULL_RAW_BAGS
        and completed == FULL_RAW_BAGS
        and timing.get("status") == "MEASURED"
        and isinstance(timing.get("distributions"), Mapping)
    ):
        value = dict(timing)
        aliases = dict(value.get("display_aliases") or {})
        aliases["java_release"] = "scheduled_segment_arrival"
        value.update(
            {
                "status": OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE,
                "display_aliases": aliases,
                "comparison_protocol": release_gate["mode"],
                "full_outcome_timing_comparison_allowed": False,
                "fresh_hca_timing_verdict_allowed": False,
                "claim_boundary": (
                    "S4_own_source_full_population_descriptive_only_not_"
                    "fresh_HCA_release_or_timing_paired"
                ),
            }
        )
        return value
    return _capacity_only_timing(outcome, release_gate)


_STRUCTURAL_SOURCE_GATES = (
    "all_required_fields_present",
    "runtime_requested_plus_source_rejected_equals_selected",
    "runtime_returned_exactly_reachable_segment_ids",
    "fault_event_count_equals_seed_count",
    "repair_event_not_processed",
    # G27's combined horizon gate is intentionally not structural here.  A
    # stable/bias case may reach G30's fixed horizon with unfinished work; that
    # is the capacity outcome being measured, not a local-safety violation.
    "reservation_conflicts_zero",
    "physical_fault_edge_entry_violation_count_zero",
    "runtime_full_astar_calls_zero",
    "runtime_full_cie_astar_calls_zero",
    "global_reservation_scan_count_zero",
    "priority_global_scan_count_zero",
    "scorer_runtime_global_scan_count_zero",
    "microphase_runtime_global_scan_count_zero",
    "first_edge_credit_global_scan_count_zero",
    "priority_future_route_input_count_zero",
    "scorer_future_route_input_count_zero",
    "first_edge_credit_future_route_count_zero",
    "scorer_future_schedule_input_count_zero",
    "full_future_routes_stored_zero",
    "event_limit_reached_false",
    "bag_future_path_field_present_false",
    "full_cie_astar_runtime_fallback_false",
)


def fixed_horizon_capacity_admission(
    *,
    selection: Mapping[str, Any],
    fixed_horizon: Mapping[str, Any],
    event_budget: Mapping[str, Any],
    source_admission: Mapping[str, Any],
    runtime_echo: Mapping[str, Any],
    fault_value_echo: Mapping[str, Any],
    observation_bias_echo: Mapping[str, Any],
    topology_gate_pass: bool,
) -> dict[str, Any]:
    """Separate structural safety from unfinished work at the fixed horizon."""

    source_gates = source_admission.get("gates")
    if not isinstance(source_gates, Mapping):
        source_gates = {}
    terminal = source_admission.get("terminal_accounting")
    if not isinstance(terminal, Mapping):
        terminal = {}
    selected = terminal.get("selected_segments")
    requested = terminal.get("runtime_requested_reachable_segments")
    rejected = terminal.get("source_rejected_unreachable_segments")
    completed = terminal.get("runtime_completed_segments")
    failed = terminal.get("runtime_failed_segments")
    gates = {
        "full_fixed_population": (
            selection.get("mode") == "full"
            and selection.get("selected_raw_bag_count") == FULL_RAW_BAGS
            and selection.get("selected_segment_count") == FULL_SEGMENTS
        ),
        "fixed_horizon": fixed_horizon.get("pass") is True,
        "event_budget": event_budget.get("pass") is True,
        "event_limit_not_reached": event_budget.get("event_limit_not_reached")
        is True,
        "selected_partition": (
            isinstance(selected, int)
            and isinstance(requested, int)
            and isinstance(rejected, int)
            and selected == requested + rejected
        ),
        "runtime_terminal_partition": (
            isinstance(completed, int)
            and isinstance(failed, int)
            and isinstance(requested, int)
            and completed + failed == requested
        ),
        "structural_source_gates": all(
            source_gates.get(name) is True for name in _STRUCTURAL_SOURCE_GATES
        ),
        "runtime_policy_echo": bool(runtime_echo) and all(runtime_echo.values()),
        "fault_value_echo": fault_value_echo.get("pass") is True,
        "observation_bias_echo": observation_bias_echo.get("pass") is True,
        "topology_bound": topology_gate_pass,
    }
    return {
        "mode": "FIXED_HORIZON_CAPACITY",
        "pass": all(gates.values()),
        "gates": gates,
        "required_structural_source_gates": list(_STRUCTURAL_SOURCE_GATES),
        "terminal_accounting": dict(terminal),
        "operational_outcome": {
            "runtime_failed_segments": failed,
            "failed_count_zero": source_gates.get("failed_count_zero"),
            "unresolved_deadlock_count_zero": source_gates.get(
                "unresolved_deadlock_count_zero"
            ),
            "time_limit_reached_false": source_gates.get(
                "time_limit_reached_false"
            ),
            "does_not_veto_capacity_admission": True,
        },
    }


def execute_case(
    case_id: str,
    *,
    canonical_path: Path,
    manifest_path: Path,
    lifecycle_path: Path,
    metrics_path: Path,
    binary: Path | None,
    earliest_raw_bags: int | None = None,
    dry_run: bool = False,
    executor: Executor | None = None,
) -> dict[str, Any]:
    resolved = g29.resolve_case(case_id)
    release_contract = release_source_contract(resolved)
    prefix, manifest, selection = load_workload(
        canonical_path, manifest_path, earliest_raw_bags=earliest_raw_bags
    )
    aligned, release_gate, hca_capacity = apply_hca_release_lifecycle(
        prefix,
        lifecycle_path=lifecycle_path,
        metrics_path=metrics_path,
        full_required=earliest_raw_bags is None,
        release_contract=release_contract,
    )
    if aligned is None:
        return _blocked_result(
            case_id=case_id,
            selection=selection,
            release_gate=release_gate,
            hca_capacity=hca_capacity,
            release_contract=release_contract,
        )
    if dry_run:
        return {
            "schema": SCHEMA,
            "status": DRY_RUN_READY,
            "case_id": case_id,
            "workload_id": WORKLOAD_ID,
            "workload_protocol": WORKLOAD_PROTOCOL,
            "selection": selection,
            "exact_release_gate": release_gate,
            "hca_capacity_view": hca_capacity,
            "release_source_contract": release_contract,
            "policy_contract": g29.intended_policy_contract(resolved),
            "native_execution_started": False,
            "claim_boundary": release_gate["claim_boundary"],
        }
    if binary is None:
        raise Native30Error("binary is required unless --dry-run is used")

    request, runtime_rows, rejected, local = prepare_native_request(
        resolved,
        aligned,
        binary=binary,
        canary=earliest_raw_bags is not None,
    )
    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise Native30Error("native executor did not return summary and bag rows")
    fixed_horizon = g29.fixed_horizon_evidence(
        request, summary, full_required=earliest_raw_bags is None
    )
    event_budget = event_budget_evidence(
        request, summary, full_required=earliest_raw_bags is None
    )
    combined = [dict(row) for row in bags] + g27_fault._synthetic_source_rejections(
        rejected
    )
    outcome = g26.summarize_paper_outcome(
        aligned.rows, combined, total_raw_bags=aligned.raw_bag_count
    )
    timing = g29.timing_evidence(
        resolved, aligned, combined, outcome, release_gate
    )
    if release_gate["mode"] == (
        "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY"
    ):
        timing = _own_source_timing(
            resolved, outcome, release_gate, timing
        )
    source_safety = g27_fault.g27_source_admission_safety(
        summary,
        selected_segment_count=aligned.size_segments,
        runtime_requested_segment_count=len(runtime_rows),
        source_rejected_segment_count=len(rejected),
        seed_fault_count=len(resolved["runtime_case"]["seed_edges"]),
        expected_runtime_segment_ids=[str(row["segment_id"]) for row in runtime_rows],
        runtime_bags=bags,
    )
    runtime_echo = g26._runtime_echo_gates(summary)
    dlp = g27_fault._dlp_evidence(summary, local.get("artifact"))
    bias_echo = g29._bias_echo(summary, resolved.get("bias"))
    topology: dict[str, Any] | None = None
    topology_pass = True
    if resolved["group"] == "fault":
        topology = g26.topology_reachable_raw_bag_upper_bound(
            aligned.rows,
            request["edge_records"],
            resolved["runtime_case"]["seed_edges"],
        )
        topology_pass = int(outcome["completed_raw_bag_count"]) <= int(
            topology["topology_reachable_raw_bag_upper_bound"]
        )
    capacity_admission = fixed_horizon_capacity_admission(
        selection=selection,
        fixed_horizon=fixed_horizon,
        event_budget=event_budget,
        source_admission=source_safety,
        runtime_echo=runtime_echo,
        fault_value_echo=dlp,
        observation_bias_echo=bias_echo,
        topology_gate_pass=topology_pass,
    )
    admitted = bool(capacity_admission["pass"])
    full_population_complete = (
        int(outcome["completed_raw_bag_count"])
        == int(outcome["selected_raw_bag_count"])
    )
    return {
        "schema": SCHEMA,
        "status": (
            COMPLETE_FIXED_HORIZON_CAPACITY
            if admitted and not full_population_complete
            else
            COMPLETE_OWN_SOURCE
            if admitted
            and release_gate["mode"]
            == "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY"
            else COMPLETE
            if admitted
            else FAILED
        ),
        "case_id": case_id,
        "case_group": resolved["group"],
        "case": resolved["public_case"],
        "workload_id": WORKLOAD_ID,
        "workload_protocol": WORKLOAD_PROTOCOL,
        "workload_manifest": {
            "schema": manifest.get("schema"),
            "status": manifest.get("status"),
            "protocol": manifest.get("protocol"),
        },
        "selection": selection,
        "exact_release_gate": release_gate,
        "hca_capacity_view": hca_capacity,
        "release_source_contract": release_contract,
        "comparison_protocol": release_gate["mode"],
        "claim_boundary": release_gate["claim_boundary"],
        "fixed_horizon": fixed_horizon,
        "event_budget": event_budget,
        "policy_contract": g29.intended_policy_contract(resolved),
        "local_policy": local,
        "outcome": {
            "requested_segment_count": aligned.size_segments,
            "runtime_requested_reachable_segment_count": len(runtime_rows),
            "source_rejected_unreachable_segment_count": len(rejected),
            "topology_reachability": topology,
            **outcome,
        },
        "timing": timing,
        "safety": {
            "pass": admitted,
            "fixed_horizon_capacity_admission": capacity_admission,
            "source_admission": source_safety,
            "runtime_echo_gates": runtime_echo,
            "fault_value_echo": dlp,
            "observation_bias_echo": bias_echo,
            "topology_gate_pass": topology_pass,
        },
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "event_count": int(summary.get("event_count", 0)),
            "decision_count": int(summary.get("decision_count", 0)),
            "declared_max_events": summary.get("declared_max_events"),
            "event_limit_reached": summary.get("event_limit_reached"),
        },
        "native_execution_started": True,
    }


def _artifact_admitted(value: Mapping[str, Any]) -> bool:
    selection = value.get("selection")
    release_gate = value.get("exact_release_gate")
    safety = value.get("safety")
    event_budget = value.get("event_budget")
    status = value.get("status")
    mode = release_gate.get("mode") if isinstance(release_gate, Mapping) else None
    capacity_admission = (
        safety.get("fixed_horizon_capacity_admission")
        if isinstance(safety, Mapping)
        else None
    )
    status_matches_mode = (
        status == COMPLETE_OWN_SOURCE
        and mode == "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY"
        and release_gate.get("exact_release_applied") is False
    ) or (
        status == COMPLETE
        and mode in {
            "EXACT_PAIRED_FULL",
            "REFERENCE_RELEASE_FULL_NON_PAIRED_FAULT",
        }
        and release_gate.get("exact_release_applied") is True
    ) or (
        status == COMPLETE_FIXED_HORIZON_CAPACITY
        and mode
        in {
            "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY",
            "EXACT_PAIRED_FULL",
            "REFERENCE_RELEASE_FULL_NON_PAIRED_FAULT",
        }
        and isinstance(capacity_admission, Mapping)
        and capacity_admission.get("pass") is True
    )
    return (
        isinstance(selection, Mapping)
        and selection.get("mode") == "full"
        and selection.get("selected_raw_bag_count") == FULL_RAW_BAGS
        and selection.get("selected_segment_count") == FULL_SEGMENTS
        and value.get("workload_protocol") == WORKLOAD_PROTOCOL
        and isinstance(release_gate, Mapping)
        and release_gate.get("pass") is True
        and release_gate.get("full_population_capacity_comparison_allowed")
        is True
        and isinstance(safety, Mapping)
        and safety.get("pass") is True
        and isinstance(event_budget, Mapping)
        and event_budget.get("required") is True
        and event_budget.get("expected_max_events") == G30_MAX_EVENTS
        and event_budget.get("request_max_events") == G30_MAX_EVENTS
        and event_budget.get("summary_declared_max_events") == G30_MAX_EVENTS
        and event_budget.get("summary_event_limit_reached") is False
        and event_budget.get("pass") is True
        and status_matches_mode
        and g29._artifact_fixed_horizon_admitted(value)
    )


def aggregate_results(case_root: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for path in sorted(case_root.rglob("*.json")) if case_root.exists() else []:
        value = _read_json(path)
        if value.get("schema") == SCHEMA and value.get("case_id") in CASE_IDS:
            cases.append(value)
    by_id = {str(row["case_id"]): row for row in cases}
    missing = sorted(set(CASE_IDS) - by_id.keys())
    blocked = sorted(
        case_id
        for case_id, row in by_id.items()
        if row.get("status") == BLOCKED_RELEASE
    )
    failed = sorted(
        case_id for case_id, row in by_id.items() if row.get("status") == FAILED
    )
    stale = sorted(
        case_id
        for case_id, row in by_id.items()
        if row.get("status") in COMPLETE_STATUSES and not _artifact_admitted(row)
    )
    complete = sorted(
        case_id
        for case_id, row in by_id.items()
        if row.get("status") in COMPLETE_STATUSES and _artifact_admitted(row)
    )
    event_budget_evidence_by_case = {
        case_id: {
            key: budget.get(key)
            for key in (
                "expected_max_events",
                "request_max_events",
                "summary_declared_max_events",
                "summary_event_count",
                "summary_event_limit_reached",
                "pass",
            )
        }
        for case_id, row in sorted(by_id.items())
        if isinstance((budget := row.get("event_budget")), Mapping)
    }
    exact_release = sorted(
        case_id
        for case_id, row in by_id.items()
        if isinstance(row.get("exact_release_gate"), Mapping)
        and row["exact_release_gate"].get("exact_release_applied") is True
    )
    own_source_capacity = sorted(
        case_id
        for case_id, row in by_id.items()
        if isinstance(row.get("exact_release_gate"), Mapping)
        and row["exact_release_gate"].get("mode")
        == "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY"
    )
    timing_comparison_allowed = sorted(
        case_id
        for case_id, row in by_id.items()
        if isinstance(row.get("exact_release_gate"), Mapping)
        and row["exact_release_gate"].get(
            "full_outcome_timing_comparison_allowed"
        )
        is True
    )
    timing_measured = sorted(
        case_id
        for case_id, row in by_id.items()
        if isinstance(row.get("timing"), Mapping)
        and row["timing"].get("status")
        in {"MEASURED", OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE}
    )
    own_source_descriptive_timing = sorted(
        case_id
        for case_id, row in by_id.items()
        if isinstance(row.get("timing"), Mapping)
        and row["timing"].get("status")
        == OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE
    )
    timing_not_measured = sorted(
        case_id
        for case_id, row in by_id.items()
        if isinstance(row.get("timing"), Mapping)
        and row["timing"].get("status") == "NOT_MEASURED"
    )
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": "COMPLETE" if len(complete) == len(CASE_IDS) else "PARTIAL",
        "workload_id": WORKLOAD_ID,
        "workload_protocol": WORKLOAD_PROTOCOL,
        "fixed_population": {
            "raw_bag_count": FULL_RAW_BAGS,
            "segment_count": FULL_SEGMENTS,
        },
        "expected_case_count": len(CASE_IDS),
        "observed_case_count": len(by_id),
        "complete_case_ids": complete,
        "blocked_release_case_ids": blocked,
        "failed_case_ids": failed,
        "stale_admission_case_ids": stale,
        "missing_case_ids": missing,
        "fixed_horizon_admission": {
            "expected_max_simulation_time": FIXED_HORIZON,
            "admitted_case_ids": complete,
            "stale_case_ids": stale,
            "pass": len(complete) == len(CASE_IDS),
        },
        "event_budget_admission": {
            "expected_max_events": G30_MAX_EVENTS,
            "admitted_case_ids": complete,
            "stale_case_ids": stale,
            "case_evidence": event_budget_evidence_by_case,
            "pass": len(complete) == len(CASE_IDS),
        },
        "measurement_scope": {
            "timing_measured_case_ids": timing_measured,
            "own_source_full_population_descriptive_timing_case_ids": (
                own_source_descriptive_timing
            ),
            "timing_not_measured_case_ids": timing_not_measured,
            "survivor_only_full_claim_allowed": False,
            "exact_release_case_ids": exact_release,
            "own_source_fixed_horizon_capacity_case_ids": own_source_capacity,
            "full_outcome_timing_comparison_allowed_case_ids": (
                timing_comparison_allowed
            ),
        },
        "release_source_mapping": {
            case_id: release_source_contract(g29.resolve_case(case_id))
            for case_id in CASE_IDS
        },
        "claim_boundary": (
            "exact_release_is_used_only_when_the_full_HCA_lifecycle_exists;_"
            "otherwise_same_scheduled_arrivals_with_each_framework_own_Source_"
            "admission_support_fixed_denominator_completion_only_not_release_"
            "or_timing_pairing"
        ),
        "cases": [
            g29._portable_repo_paths(by_id[case_id]) for case_id in sorted(by_id)
        ],
    }


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def reclassify_failed_capacity(case_id: str, case_root: Path) -> dict[str, Any]:
    """Upgrade a stored FAILED artifact only when capacity safety is provable."""

    path = case_root / f"{case_id}.json"
    value = _read_json(path)
    if (
        value.get("schema") != SCHEMA
        or value.get("case_id") != case_id
        or value.get("status") != FAILED
    ):
        raise Native30Error("reclassify requires one current-schema FAILED artifact")
    selection = value.get("selection")
    fixed_horizon = value.get("fixed_horizon")
    event_budget = value.get("event_budget")
    safety = value.get("safety")
    if not all(
        isinstance(item, Mapping)
        for item in (selection, fixed_horizon, event_budget, safety)
    ):
        raise Native30Error("FAILED artifact lacks capacity admission evidence")
    capacity = fixed_horizon_capacity_admission(
        selection=selection,
        fixed_horizon=fixed_horizon,
        event_budget=event_budget,
        source_admission=safety.get("source_admission", {}),
        runtime_echo=safety.get("runtime_echo_gates", {}),
        fault_value_echo=safety.get("fault_value_echo", {}),
        observation_bias_echo=safety.get("observation_bias_echo", {}),
        topology_gate_pass=safety.get("topology_gate_pass") is True,
    )
    if not capacity["pass"]:
        raise Native30Error("FAILED artifact does not prove fixed-horizon capacity safety")
    updated = dict(value)
    updated_safety = dict(safety)
    updated_safety["pass"] = True
    updated_safety["fixed_horizon_capacity_admission"] = capacity
    updated["safety"] = updated_safety
    updated["status"] = COMPLETE_FIXED_HORIZON_CAPACITY
    updated["reclassification"] = {
        "from_status": FAILED,
        "to_status": COMPLETE_FIXED_HORIZON_CAPACITY,
        "mode": "FIXED_HORIZON_CAPACITY_ADMISSION_ONLY",
        "business_metrics_changed": False,
    }
    if not _artifact_admitted(updated):
        raise Native30Error(
            "reclassified artifact does not satisfy full G30 admission"
        )
    _write_json(path, updated)
    return updated


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    case = commands.add_parser("case", help="run or resume one G30 native case")
    case.add_argument("--case-id", required=True, choices=CASE_IDS)
    case.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    case.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    case.add_argument("--hca-run-dir", type=Path)
    case.add_argument("--binary", type=Path)
    case.add_argument("--earliest-raw-bags", type=int)
    case.add_argument("--output", type=Path, required=True)
    case.add_argument("--dry-run", action="store_true")
    case.add_argument("--force", action="store_true")

    resume = commands.add_parser("resume", help="resume one lane of G30 cases")
    resume.add_argument("--case-id", action="append", choices=CASE_IDS)
    resume.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    resume.add_argument("--binary", type=Path, required=True)
    resume.add_argument("--force", action="store_true")

    aggregate = commands.add_parser("aggregate", help="aggregate G30 case JSON")
    aggregate.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    aggregate.add_argument("--output", type=Path, default=DEFAULT_AGGREGATE)

    reclassify = commands.add_parser(
        "reclassify", help="upgrade one proven fixed-horizon FAILED artifact"
    )
    reclassify.add_argument("--case-id", required=True, choices=CASE_IDS)
    reclassify.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    return parser


def _resume(args: argparse.Namespace) -> int:
    case_root = _rooted(args.case_root)
    binary = _rooted(args.binary)
    case_ids = tuple(dict.fromkeys(args.case_id or CASE_IDS))
    exit_code = 0
    for case_id in case_ids:
        output = case_root / f"{case_id}.json"
        if output.is_file() and not args.force:
            existing = _read_json(output)
            if existing.get("schema") != SCHEMA or existing.get("case_id") != case_id:
                raise Native30Error(f"existing resume artifact does not match {case_id}")
            if (
                existing.get("status") in COMPLETE_STATUSES
                and _artifact_admitted(existing)
            ):
                print(json.dumps({"status": "SKIPPED_COMPLETE", "case_id": case_id}))
                continue
            if existing.get("status") in COMPLETE_STATUSES:
                print(json.dumps({"status": "STALE_G30_ADMISSION", "case_id": case_id}))

        hca_run_dir = default_hca_run_dir(case_id)
        payload = execute_case(
            case_id,
            canonical_path=DEFAULT_CANONICAL,
            manifest_path=DEFAULT_MANIFEST,
            lifecycle_path=hca_run_dir / "segment_lifecycle.csv",
            metrics_path=hca_run_dir / "metrics.json",
            binary=binary,
        )
        _write_json(output, payload)
        print(json.dumps({"status": payload["status"], "case_id": case_id}))
        if payload["status"] not in COMPLETE_STATUSES:
            exit_code = 2
            break
    aggregate = aggregate_results(case_root)
    aggregate_output = case_root / RESUME_AGGREGATE_NAME
    _write_json(aggregate_output, aggregate)
    print(
        json.dumps(
            {
                "status": "RESUME_COMPLETE" if exit_code == 0 else "RESUME_STOPPED",
                "aggregate_status": aggregate["status"],
                "aggregate": str(aggregate_output),
            }
        )
    )
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "reclassify":
        payload = reclassify_failed_capacity(
            args.case_id, _rooted(args.case_root)
        )
        print(json.dumps({"status": payload["status"], "case_id": args.case_id}))
        return 0
    if args.command == "aggregate":
        payload = aggregate_results(_rooted(args.case_root))
        output = _rooted(args.output)
        _write_json(output, payload)
        print(json.dumps({"status": payload["status"], "output": str(output)}))
        return 0 if payload["status"] == "COMPLETE" else 2
    if args.command == "resume":
        return _resume(args)

    output = _rooted(args.output)
    if output.is_file() and not args.force:
        existing = _read_json(output)
        if existing.get("schema") != SCHEMA or existing.get("case_id") != args.case_id:
            raise Native30Error("existing resume artifact does not match the requested case")
        admitted = (
            existing.get("status") in COMPLETE_STATUSES
            and _artifact_admitted(existing)
        )
        if admitted or existing.get("status") == DRY_RUN_READY:
            print(
                json.dumps(
                    {
                        "status": "SKIPPED_EXISTING",
                        "case_id": args.case_id,
                        "case_status": existing.get("status"),
                        "output": str(output),
                    }
                )
            )
            return 0

    hca_run_dir = (
        _rooted(args.hca_run_dir)
        if args.hca_run_dir is not None
        else default_hca_run_dir(args.case_id)
    )
    payload = execute_case(
        args.case_id,
        canonical_path=_rooted(args.canonical),
        manifest_path=_rooted(args.manifest),
        lifecycle_path=hca_run_dir / "segment_lifecycle.csv",
        metrics_path=hca_run_dir / "metrics.json",
        binary=(_rooted(args.binary) if args.binary is not None else None),
        earliest_raw_bags=args.earliest_raw_bags,
        dry_run=args.dry_run,
    )
    _write_json(output, payload)
    print(
        json.dumps(
            {"status": payload["status"], "case_id": args.case_id, "output": str(output)}
        )
    )
    return 0 if payload["status"] in {*COMPLETE_STATUSES, DRY_RUN_READY} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Native30Error, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G30 native failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
