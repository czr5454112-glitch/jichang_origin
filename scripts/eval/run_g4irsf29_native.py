#!/usr/bin/env python3
"""Run the active local S4 stack on the G29 faithful 2x workload.

This module is an orchestration layer only.  It loads the G29 canonical
workload, selects whole raw bags for a canary when requested, applies the
matching Java/HCA release lifecycle, and then reuses the existing G26/G27/G28
request builders:

* S4/J2/E2 with one-junction FIFO arbitration;
* the G28 service-aware static local potential;
* the fixed G27 ``U(0, k)`` observation-bias stream for Table 5.4; and
* the G27 deterministic structural local TD value for a pre-start fault.

No runtime planner, model, reservation table, or C++ policy is added here.
An exact-paired full run is refused when the HCA lifecycle does not cover the
entire 2x population.  The HCA capacity counters are still returned so an
incomplete release is visible instead of becoming a survivor-only comparison.
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
from scripts.eval import run_g4irsf27_bias_experiments as g27_bias
from scripts.eval import run_g4irsf27_fault_values as g27_fault


SCHEMA = "czr005.g4irsf29.s4_case.v1"
AGGREGATE_SCHEMA = "czr005.g4irsf29.s4_aggregate.v1"
WORKLOAD_SCHEMA = "czr005.g4irsf29.workload_manifest.v1"
HCA_CASE_PROTOCOL_SCHEMA = "czr005.g4irsf29.hca_case_protocol.v1"
WORKLOAD_ID = "g4irsf29_flight_densified_2x"
WORKLOAD_PROTOCOL = "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_2X"
FULL_RAW_BAGS = 57_012
FULL_SEGMENTS = 87_206
FIXED_HORIZON = 98_259.0

COMPLETE = "COMPLETE_G29_2X_ADMISSION"
DRY_RUN_READY = "READY_G29_DRY_RUN"
BLOCKED_RELEASE = "BLOCKED_G29_EXACT_RELEASE_INCOMPLETE"
FAILED = "FAILED_G29_2X_ADMISSION"

DEFAULT_CANONICAL = (
    ROOT / "artifacts/tasks/g4irsf29/inputdata_flight_densified_2x.jsonl"
)
DEFAULT_MANIFEST = (
    ROOT / "artifacts/tasks/g4irsf29/g4irsf29_workload_manifest.json"
)
DEFAULT_HCA_ROOT = ROOT / "outputs/runtime/g4irsf29_hca"
DEFAULT_CASE_ROOT = ROOT / "outputs/runtime/g4irsf29_native"
DEFAULT_AGGREGATE = ROOT / "outputs/tables/g4irsf29_native.json"
RESUME_AGGREGATE_NAME = "aggregate.json"

Executor = Callable[..., Mapping[str, Any]]


class Native29Error(RuntimeError):
    """Raised when a G29 native case cannot be compared honestly."""


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Native29Error(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise Native29Error(f"canonical row {line_number} is not an object")
            rows.append(value)
    if not rows:
        raise Native29Error("G29 canonical workload is empty")
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


def _portable_repo_paths(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _portable_repo_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_portable_repo_paths(item) for item in value]
    if isinstance(value, tuple):
        return [_portable_repo_paths(item) for item in value]
    if isinstance(value, str):
        path = Path(value)
        if path.is_absolute():
            try:
                return path.resolve().relative_to(ROOT.resolve()).as_posix()
            except ValueError:
                pass
    return value


def _manifest_count(manifest: Mapping[str, Any], *names: str) -> int | None:
    counts = manifest.get("counts")
    for name in names:
        value = manifest.get(name)
        if value is None and isinstance(counts, Mapping):
            value = counts.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def _select_whole_raw_bags(
    rows: Sequence[Mapping[str, Any]], earliest_raw_bags: int | None
) -> tuple[dict[str, Any], ...]:
    if earliest_raw_bags is None:
        return tuple(dict(row) for row in rows)
    if earliest_raw_bags <= 0:
        raise Native29Error("earliest raw-bag count must be positive")
    entry_by_task: dict[int, float] = {}
    for row in rows:
        task_id = int(row["task_id"])
        entry = float(row["original_entry_time"])
        entry_by_task[task_id] = min(entry, entry_by_task.get(task_id, entry))
    selected_tasks = {
        task_id
        for task_id, _entry in sorted(
            entry_by_task.items(), key=lambda item: (item[1], item[0])
        )[:earliest_raw_bags]
    }
    return tuple(dict(row) for row in rows if int(row["task_id"]) in selected_tasks)


def load_workload(
    canonical_path: Path,
    manifest_path: Path,
    *,
    earliest_raw_bags: int | None = None,
) -> tuple[harness.InputPrefix, dict[str, Any], dict[str, Any]]:
    """Load the 2x canonical stream and select complete raw bags for canaries."""

    manifest = _read_json(manifest_path)
    if manifest.get("schema") != WORKLOAD_SCHEMA or manifest.get("status") != "COMPLETE":
        raise Native29Error("G29 workload manifest is not complete")
    if manifest.get("protocol") != WORKLOAD_PROTOCOL:
        raise Native29Error("G29 workload is not the registered schedule-preserving 2x stream")
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
    for row in rows:
        if not required.issubset(row):
            raise Native29Error("G29 canonical row lacks a runtime field")
    segment_ids = [str(row["segment_id"]) for row in rows]
    if len(segment_ids) != len(set(segment_ids)):
        raise Native29Error("G29 canonical segment IDs are not unique")
    raw_count = len({int(row["task_id"]) for row in rows})
    manifest_raw = _manifest_count(
        manifest, "raw_task_count", "raw_bag_count", "raw_order_count", "raw_bags"
    )
    manifest_segments = _manifest_count(
        manifest, "expanded_segment_count", "segment_count", "expanded_segments"
    )
    if raw_count != FULL_RAW_BAGS or len(rows) != FULL_SEGMENTS:
        raise Native29Error("G29 canonical workload is not the registered 2x population")
    if manifest_raw not in (None, raw_count) or manifest_segments not in (None, len(rows)):
        raise Native29Error("G29 manifest counts disagree with its canonical workload")

    selected = _select_whole_raw_bags(rows, earliest_raw_bags)
    selected_tasks = {int(row["task_id"]) for row in selected}
    if earliest_raw_bags is not None and len(selected_tasks) != min(
        earliest_raw_bags, raw_count
    ):
        raise Native29Error("earliest-raw selection did not retain the requested bags")
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
    }
    return prefix, manifest, selection


def _lifecycle_releases(path: Path) -> dict[str, float]:
    releases: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            segment_id = str(row.get("segment_id", ""))
            if not segment_id:
                raise Native29Error("HCA lifecycle lacks segment_id")
            if segment_id in releases:
                raise Native29Error(f"duplicate HCA lifecycle segment: {segment_id}")
            releases[segment_id] = float(row["release_epoch"])
    return releases


def capacity_view(
    metrics: Mapping[str, Any], *, expected_segments: int, expected_raw_bags: int
) -> dict[str, Any]:
    """Expose HCA horizon counts without relabelling them as paired timing."""

    return {
        "claim_scope": "fixed_population_capacity_not_survivor_timing",
        "expected_segment_count": expected_segments,
        "expected_raw_bag_count": expected_raw_bags,
        "released_segment_count": metrics.get("released_segment_count"),
        "planned_segment_count": metrics.get("planned_segment_count"),
        "completed_segment_count": metrics.get("completed_segment_count"),
        "canonical_complete_raw_bag_count": metrics.get(
            "canonical_complete_raw_bag_count"
        ),
        "canonical_incomplete_raw_bag_count": metrics.get(
            "canonical_incomplete_raw_bag_count"
        ),
        "canonical_success_rate": metrics.get("canonical_success_rate"),
        "comparison_eligible": metrics.get("comparison_eligible"),
        "denominators": metrics.get("denominators", {}),
    }


def apply_hca_release_lifecycle(
    prefix: harness.InputPrefix,
    *,
    lifecycle_path: Path,
    metrics_path: Path,
    full_required: bool,
    release_contract: Mapping[str, Any],
) -> tuple[harness.InputPrefix | None, dict[str, Any], dict[str, Any]]:
    """Apply exact releases, refusing an incomplete full lifecycle."""

    releases = _lifecycle_releases(lifecycle_path)
    metrics = _read_json(metrics_path) if metrics_path.is_file() else {}
    run_status_path = lifecycle_path.with_name("run_status.json")
    case_protocol_path = lifecycle_path.parent.parent / "case_protocol.json"
    run_status = _read_json(run_status_path) if run_status_path.is_file() else {}
    case_protocol = _read_json(case_protocol_path) if case_protocol_path.is_file() else {}
    protocol_case = case_protocol.get("case")
    if not isinstance(protocol_case, Mapping):
        protocol_case = {}
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
    pass_gate = all(source_gates.values()) and not missing and (
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
    gate = {
        "pass": pass_gate,
        "mode": (
            "REFERENCE_RELEASE_FULL_NON_PAIRED_FAULT"
            if full_required
            and release_contract["comparison_scope"]
            == "fixed_population_fault_capacity_not_segment_paired"
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
        "full_population_capacity_comparison_allowed": pass_gate,
        "full_outcome_timing_comparison_allowed": (
            pass_gate
            and release_contract["comparison_scope"] == "exact_release_timing"
            and metrics.get("comparison_eligible") is True
        ),
        "survivor_only_full_claim_allowed": False,
    }
    view = capacity_view(
        metrics,
        expected_segments=(FULL_SEGMENTS if full_required else prefix.size_segments),
        expected_raw_bags=(FULL_RAW_BAGS if full_required else prefix.raw_bag_count),
    )
    if not pass_gate:
        return None, gate, view

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
    return aligned, gate, view


_G26_CASES = {str(case["case_id"]): case for case in g26.paper_cases()}
_BIAS_CASES = {str(case["case_id"]): case for case in g27_bias.bias_cases()}
_STABLE_IDS = tuple(
    case_id
    for case_id, case in _G26_CASES.items()
    if case.get("case_group") == "stable_speed"
)
_FAULT_IDS = tuple(
    case_id
    for case_id, case in _G26_CASES.items()
    if case.get("case_group") == "all_day_line_interruption"
    and case_id != "t5_5_fault_pair_5_7"
)
CASE_IDS = tuple(sorted((*_STABLE_IDS, *_BIAS_CASES, *_FAULT_IDS)))


def _speed_label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def resolve_case(case_id: str) -> dict[str, Any]:
    """Resolve one public G29 ID onto an unchanged G26 runtime case."""

    if case_id in _BIAS_CASES:
        public = dict(_BIAS_CASES[case_id])
        runtime_id = f"t5_2_speed_{_speed_label(float(public['standard_speed_mps']))}"
        return {
            "case_id": case_id,
            "group": "observation_bias",
            "public_case": public,
            "runtime_case": dict(g26.case_by_id(runtime_id)),
            "bias": {
                "seed": int(public["observation_bias"]["seed"]),
                "maximum_seconds": float(
                    public["observation_bias"]["maximum_seconds"]
                ),
                "distribution": "uniform_0_to_k_seconds",
            },
        }
    if case_id not in CASE_IDS:
        raise Native29Error(f"unsupported G29 native case: {case_id}")
    runtime_case = dict(g26.case_by_id(case_id))
    return {
        "case_id": case_id,
        "group": (
            "fault" if runtime_case.get("seed_edges") else "stable_speed"
        ),
        "public_case": runtime_case,
        "runtime_case": runtime_case,
        "bias": None,
    }


def release_source_contract(resolved: Mapping[str, Any]) -> dict[str, Any]:
    """Pin each S4 cell to a complete no-fault HCA release stream.

    Stable and observation-bias cells use the no-fault stream at their own
    standard speed.  Fault cells deliberately use the 2.5 m/s no-fault
    reference stream: their fixed-population business outcome is compared
    with the separate fault HCA cell, not paired segment by segment with it.
    """

    speed = float(resolved["runtime_case"]["standard_speed_mps"])
    source_case_id = f"t5_2_speed_{_speed_label(speed)}"
    comparison_scope = "exact_release_timing"
    if resolved["group"] == "fault":
        source_case_id = "t5_2_speed_2p5"
        speed = 2.5
        comparison_scope = "fixed_population_fault_capacity_not_segment_paired"
    return {
        "source_case_id": source_case_id,
        "source_run_id": "run_01",
        "expected_speed_mps": speed,
        "expected_fault_schedule": "none",
        "comparison_scope": comparison_scope,
    }


def default_hca_run_dir(case_id: str) -> Path:
    contract = release_source_contract(resolve_case(case_id))
    return DEFAULT_HCA_ROOT / str(contract["source_case_id"]) / str(
        contract["source_run_id"]
    )


def intended_policy_contract(resolved: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "framework": "S4_J2_E2_plus_local_FIFO",
        "decision_scope": "one_next_hop_at_current_junction",
        "runtime_decision_complexity": "O(outdegree)",
        "service_aware_static_local_potential": True,
        "observation_bias": resolved.get("bias"),
        "fault_structural_local_td": resolved.get("group") == "fault",
        "learning_active": False,
        "runtime_full_astar": False,
        "future_route_materialized": False,
        "hca_global_reservation_table": False,
        "full_fixed_horizon": FIXED_HORIZON,
    }


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
    request, runtime_rows, rejected, local = g27_fault.prepare_request(
        resolved["runtime_case"],
        prefix,
        binary=binary.resolve(strict=True),
        service_aware_potential=True,
    )
    bias = resolved.get("bias")
    if isinstance(bias, Mapping):
        request.update(
            legacy_observation_bias_max_seconds=float(bias["maximum_seconds"]),
            legacy_observation_bias_seed=int(bias["seed"]),
        )
    request["scenario"] = (
        f"g4irsf29_{resolved['case_id']}_{'canary' if canary else 'full'}"
    )
    request["summary_only"] = False
    request["trace_limit"] = 0
    request["event_trace_limit"] = 0
    if not canary:
        request["max_simulation_time"] = FIXED_HORIZON
    return request, runtime_rows, rejected, local


def _bias_echo(summary: Mapping[str, Any], bias: Mapping[str, Any] | None) -> dict[str, Any]:
    if bias is None:
        gates = {
            "maximum_absent": "legacy_observation_bias_max_seconds" not in summary,
            "seed_absent": "legacy_observation_bias_seed" not in summary,
        }
        return {"pass": all(gates.values()), "gates": gates, "active": False}
    maximum = summary.get("legacy_observation_bias_max_seconds")
    gates = {
        "maximum_seconds_echo": (
            isinstance(maximum, (int, float))
            and not isinstance(maximum, bool)
            and math.isclose(
                float(maximum), float(bias["maximum_seconds"]), abs_tol=1.0e-12
            )
        ),
        "seed_echo": summary.get("legacy_observation_bias_seed") == int(bias["seed"]),
        "claim_boundary_echo": summary.get(
            "legacy_observation_bias_claim_boundary"
        )
        == "deterministic_local_observation_delay_only",
    }
    return {"pass": all(gates.values()), "gates": gates, "active": True}


def timing_evidence(
    resolved: Mapping[str, Any],
    prefix: harness.InputPrefix,
    segment_results: Sequence[Mapping[str, Any]],
    outcome: Mapping[str, Any],
    release_gate: Mapping[str, Any],
) -> dict[str, Any]:
    """Publish the three protected denominators only for a complete cohort."""

    selected = int(outcome["selected_raw_bag_count"])
    completed = int(outcome["completed_raw_bag_count"])
    if resolved["group"] == "fault":
        return {
            "status": "NOT_MEASURED",
            "reason": "table_5_5_compares_fixed_population_success_rate_not_timing",
            "selected_raw_bag_count": selected,
            "completed_raw_bag_count": completed,
            "fixed_population_success": outcome["success"][
                "primary_completed_raw_bags"
            ],
            "full_outcome_timing_comparison_allowed": False,
        }
    if completed != selected:
        return {
            "status": "NOT_MEASURED",
            "reason": "incomplete_raw_bag_population",
            "selected_raw_bag_count": selected,
            "completed_raw_bag_count": completed,
            "full_outcome_timing_comparison_allowed": False,
        }

    distributions, raw_bags = g24.timing_distributions(
        prefix.rows, segment_results
    )
    normalized = {
        denominator: {
            "count": values["count"],
            "min_seconds": values["min_seconds"],
            "p50_seconds": values["median_seconds"],
            "mean_seconds": values["mean_seconds"],
            "p95_seconds": values["p95_seconds"],
            "p99_seconds": values["p99_seconds"],
            "max_seconds": values["max_seconds"],
        }
        for denominator, values in distributions.items()
    }
    return {
        "status": "MEASURED",
        "source": "run_g4irsf24_native_race.timing_distributions",
        "population": "all_selected_raw_bags_complete",
        "raw_bag_count": len(raw_bags),
        "units": "seconds",
        "display_aliases": {"original_entry": "raw_entry"},
        "distributions": normalized,
        "full_outcome_timing_comparison_allowed": bool(
            release_gate.get("full_outcome_timing_comparison_allowed")
        ),
    }


def fixed_horizon_evidence(
    request: Mapping[str, Any],
    summary: Mapping[str, Any],
    *,
    full_required: bool,
) -> dict[str, Any]:
    request_value = request.get("max_simulation_time")
    summary_value = summary.get("declared_max_simulation_time")
    request_matches = isinstance(request_value, (int, float)) and math.isclose(
        float(request_value), FIXED_HORIZON, abs_tol=1.0e-12
    )
    summary_matches = isinstance(summary_value, (int, float)) and math.isclose(
        float(summary_value), FIXED_HORIZON, abs_tol=1.0e-12
    )
    return {
        "required": full_required,
        "expected_max_simulation_time": FIXED_HORIZON,
        "request_max_simulation_time": request_value,
        "summary_declared_max_simulation_time": summary_value,
        "request_matches": request_matches,
        "summary_matches": summary_matches,
        "pass": (request_matches and summary_matches) if full_required else True,
    }


def _artifact_fixed_horizon_admitted(value: Mapping[str, Any]) -> bool:
    selection = value.get("selection")
    horizon = value.get("fixed_horizon")
    return (
        isinstance(selection, Mapping)
        and selection.get("mode") == "full"
        and isinstance(horizon, Mapping)
        and horizon.get("pass") is True
        and horizon.get("required") is True
        and horizon.get("expected_max_simulation_time") == FIXED_HORIZON
        and horizon.get("request_max_simulation_time") == FIXED_HORIZON
        and horizon.get("summary_declared_max_simulation_time") == FIXED_HORIZON
    )


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
    resolved = resolve_case(case_id)
    release_contract = release_source_contract(resolved)
    prefix, manifest, selection = load_workload(
        canonical_path,
        manifest_path,
        earliest_raw_bags=earliest_raw_bags,
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
            "policy_contract": intended_policy_contract(resolved),
            "native_execution_started": False,
        }
    if binary is None:
        raise Native29Error("binary is required unless --dry-run is used")

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
        raise Native29Error("native executor did not return summary and bag rows")
    fixed_horizon = fixed_horizon_evidence(
        request,
        summary,
        full_required=earliest_raw_bags is None,
    )

    combined = [dict(row) for row in bags] + g27_fault._synthetic_source_rejections(
        rejected
    )
    outcome = g26.summarize_paper_outcome(
        aligned.rows,
        combined,
        total_raw_bags=aligned.raw_bag_count,
    )
    timing = timing_evidence(
        resolved,
        aligned,
        combined,
        outcome,
        release_gate,
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
    bias_echo = _bias_echo(summary, resolved.get("bias"))
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
    admitted = (
        bool(source_safety["pass"])
        and all(runtime_echo.values())
        and bool(dlp["pass"])
        and bool(bias_echo["pass"])
        and topology_pass
        and bool(fixed_horizon["pass"])
    )
    return {
        "schema": SCHEMA,
        "status": COMPLETE if admitted else FAILED,
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
        "fixed_horizon": fixed_horizon,
        "policy_contract": intended_policy_contract(resolved),
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
        },
        "native_execution_started": True,
    }


def aggregate_results(case_root: Path) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for path in sorted(case_root.rglob("*.json")) if case_root.exists() else []:
        value = _read_json(path)
        if value.get("schema") != SCHEMA or value.get("case_id") not in CASE_IDS:
            continue
        cases.append(value)
    by_id = {str(row["case_id"]): row for row in cases}
    missing = sorted(set(CASE_IDS) - by_id.keys())
    blocked = sorted(
        case_id
        for case_id, row in by_id.items()
        if row.get("status") == BLOCKED_RELEASE
    )
    failed = sorted(
        case_id
        for case_id, row in by_id.items()
        if row.get("status") == FAILED
    )
    stale_fixed_horizon = sorted(
        case_id
        for case_id, row in by_id.items()
        if row.get("status") == COMPLETE
        and not _artifact_fixed_horizon_admitted(row)
    )
    complete = sorted(
        case_id
        for case_id, row in by_id.items()
        if row.get("status") == COMPLETE
        and _artifact_fixed_horizon_admitted(row)
    )
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": "COMPLETE" if len(complete) == len(CASE_IDS) else "PARTIAL",
        "workload_id": WORKLOAD_ID,
        "workload_protocol": WORKLOAD_PROTOCOL,
        "expected_case_count": len(CASE_IDS),
        "observed_case_count": len(by_id),
        "complete_case_ids": complete,
        "blocked_release_case_ids": blocked,
        "failed_case_ids": failed,
        "stale_fixed_horizon_case_ids": stale_fixed_horizon,
        "missing_case_ids": missing,
        "fixed_horizon_admission": {
            "expected_max_simulation_time": FIXED_HORIZON,
            "admitted_case_ids": complete,
            "stale_case_ids": stale_fixed_horizon,
            "pass": len(complete) == len(CASE_IDS),
        },
        "release_source_mapping": {
            case_id: release_source_contract(resolve_case(case_id))
            for case_id in CASE_IDS
        },
        "claim_boundary": (
            "stable_and_bias_cells_use_their_matching_no_fault_release;_fault_"
            "cells_use_the_2p5_no_fault_release_and_compare_fixed_population_"
            "business_outcomes_not_segment_paired_fault_timings"
        ),
        "cases": [
            _portable_repo_paths(by_id[case_id]) for case_id in sorted(by_id)
        ],
    }


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    case = commands.add_parser("case", help="run or resume one G29 native case")
    case.add_argument("--case-id", required=True, choices=CASE_IDS)
    case.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    case.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    case.add_argument(
        "--hca-run-dir",
        type=Path,
        help=(
            "override the registered no-fault release source; defaults to the "
            "matching speed, or 2.5 m/s no-fault for every fault case"
        ),
    )
    case.add_argument("--binary", type=Path)
    case.add_argument("--earliest-raw-bags", type=int)
    case.add_argument("--output", type=Path, required=True)
    case.add_argument("--dry-run", action="store_true")
    case.add_argument("--force", action="store_true")

    aggregate = commands.add_parser("aggregate", help="aggregate resumable case JSON")
    aggregate.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    aggregate.add_argument("--output", type=Path, default=DEFAULT_AGGREGATE)

    resume = commands.add_parser("resume", help="resume one lane of G29 native cases")
    resume.add_argument(
        "--case-id",
        action="append",
        choices=CASE_IDS,
        help="repeat for a subset; omitted runs the complete registered matrix",
    )
    resume.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    resume.add_argument("--binary", type=Path, required=True)
    resume.add_argument("--force", action="store_true")
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
                raise Native29Error(
                    f"existing resume artifact does not match {case_id}"
                )
            if existing.get("status") == COMPLETE and _artifact_fixed_horizon_admitted(
                existing
            ):
                print(json.dumps({"status": "SKIPPED_COMPLETE", "case_id": case_id}))
                continue
            if existing.get("status") == COMPLETE:
                print(
                    json.dumps(
                        {"status": "STALE_FIXED_HORIZON", "case_id": case_id}
                    )
                )

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
        if payload["status"] != COMPLETE:
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
            raise Native29Error("existing resume artifact does not match the requested case")
        admitted_complete = existing.get(
            "status"
        ) == COMPLETE and _artifact_fixed_horizon_admitted(existing)
        if admitted_complete or existing.get("status") == DRY_RUN_READY:
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
        if existing.get("status") == COMPLETE:
            print(
                json.dumps(
                    {"status": "STALE_FIXED_HORIZON", "case_id": args.case_id}
                )
            )

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
            {
                "status": payload["status"],
                "case_id": args.case_id,
                "output": str(output),
            }
        )
    )
    return 0 if payload["status"] in {COMPLETE, DRY_RUN_READY} else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Native29Error, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G29 native failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
