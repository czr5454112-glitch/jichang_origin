#!/usr/bin/env python3
"""Run the secondary G31 stable timing view on one exact HCA release trace.

The normal G31 native artifacts remain the primary own-Source, fixed-window
capacity evidence.  This runner changes no S4/J2/E2 policy input: it replaces
only each canonical segment ``pass_time`` with the matching corrected HCA
``run_01`` release, using the G24 alignment helper.  Timing is reported only
when the HCA reference and the paired S4 run both complete the entire raw-bag
population.  An incomplete HCA release trace is N/A, never a survivor/common-
cohort comparison.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import g4irsf12_reproducible_harness as harness  # noqa: E402
from scripts.eval import run_g4irsf24_native_race as g24  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_hca as hca31  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_native as native31  # noqa: E402


SCHEMA = "czr005.g4irsf31.same_hca_release_timing.v1"
READY = "READY_G31_SAME_HCA_RELEASE_TIMING"
COMPLETE = "COMPLETE_G31_SAME_HCA_RELEASE_TIMING"
FAILED = "FAILED_G31_SAME_HCA_RELEASE_TIMING_SAFETY"
N_A_RELEASE = "N_A_HCA_RELEASE_TRACE_INCOMPLETE"
N_A_REPEAT = "N_A_HCA_REPEAT_RELEASE_MISMATCH"
N_A_SOURCE = "N_A_HCA_REFERENCE_NOT_MATCHING_CORRECTED_RUN_01"
N_A_HCA_TIMING = "N_A_HCA_FULL_POPULATION_TIMING_UNAVAILABLE"
N_A_S4_TIMING = "N_A_PAIRED_S4_FULL_POPULATION_TIMING_UNAVAILABLE"

DEFAULT_HCA_ROOT = hca31.DEFAULT_OUTPUT_ROOT
DEFAULT_OUTPUT_ROOT = ROOT / "outputs/runtime/g4irsf31_nanning_paired_timing"
DEFAULT_BINARY_DIR = ROOT / "build/g4irsf24_dlp_release/python"
METRICS = ("min", "mean", "p95", "p99", "max")

Executor = Callable[..., Mapping[str, Any]]
AdmissionChecker = Callable[..., Mapping[str, Any]]


class PairedTimingError(RuntimeError):
    """Raised when a paired timing input is structurally invalid."""


@dataclass(frozen=True)
class AlignmentResult:
    workload: native31.Workload | None
    trace_gate: Mapping[str, Any]
    hca_timing: Mapping[str, Any]


@dataclass(frozen=True)
class PreparedCase:
    artifact: Mapping[str, Any]
    workload: native31.Workload | None = None
    request: Mapping[str, Any] | None = None
    runtime_rows: tuple[dict[str, Any], ...] = ()
    rejected: tuple[dict[str, Any], ...] = ()
    local: Mapping[str, Any] | None = None
    hca_metrics_seconds: Mapping[str, float] | None = None


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PairedTimingError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_binary(path: Path | None) -> Path | None:
    if path is not None:
        return _rooted(path).resolve(strict=True)
    candidates = sorted(DEFAULT_BINARY_DIR.glob("czr005_cpp*.pyd"))
    return candidates[-1].resolve() if candidates else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _same_number(left: Any, right: float) -> bool:
    value = _number(left)
    return value is not None and math.isclose(
        value, right, rel_tol=0.0, abs_tol=1.0e-12
    )


def _hca_case_id(case: native31.CaseSpec) -> str:
    return (
        f"nanning_{case.scale}x_t5_2_speed_"
        f"{native31._speed_label(case.speed_mps)}"
    )


def _release_map(path: Path) -> dict[str, float]:
    if not path.is_file():
        return {}
    releases: dict[str, float] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            segment_id = str(row.get("segment_id", ""))
            release = _number(row.get("release_epoch"))
            if not segment_id or release is None:
                raise PairedTimingError(
                    f"corrected HCA lifecycle lacks segment_id/release_epoch: {path}"
                )
            if segment_id in releases:
                raise PairedTimingError(
                    f"duplicate corrected HCA lifecycle segment: {segment_id}"
                )
            releases[segment_id] = release
    return releases


def inspect_hca_release_trace(
    case: native31.CaseSpec,
    workload: native31.Workload,
    hca_root: Path,
) -> tuple[dict[str, Any], Path | None]:
    """Admit only a matching full run_01 trace repeated exactly in run_02."""

    if case.group != "stable_speed" or case.fault_scenario is not None:
        raise PairedTimingError("same-release timing is defined only for stable cases")
    expected_case_id = _hca_case_id(case)
    case_root = hca_root / expected_case_id
    protocol_path = case_root / "case_protocol.json"
    protocol = _read_json(protocol_path)
    protocol_case = protocol.get("case")
    protocol_case = protocol_case if isinstance(protocol_case, Mapping) else {}
    protocol_workload = protocol.get("workload")
    protocol_workload = (
        protocol_workload if isinstance(protocol_workload, Mapping) else {}
    )
    fixed_window = protocol.get("fixed_window")
    fixed_window = fixed_window if isinstance(fixed_window, Mapping) else {}

    protocol_gates = {
        "schema": protocol.get("schema") == hca31.CASE_PROTOCOL_SCHEMA,
        "case_id": protocol_case.get("case_id") == expected_case_id,
        "stable_no_fault": (
            protocol_case.get("case_group") == "stable_speed"
            and protocol_case.get("fault_schedule") == "none"
            and protocol_case.get("fault_edges") == []
        ),
        "scale": protocol_case.get("scale") == case.scale,
        "speed": _same_number(protocol_case.get("speed_mps"), case.speed_mps),
        "repeat_count": protocol_case.get("repeats") == hca31.STABLE_REPEATS,
        "map": protocol_workload.get("map_id") == native31.MAP_ID,
        "raw_population": (
            protocol_workload.get("raw_task_count") == workload.raw_bag_count
        ),
        "segment_population": (
            protocol_workload.get("expanded_segment_count")
            == workload.segment_count
        ),
        "fixed_window": (
            fixed_window.get("start_epoch") == hca31.START_EPOCH
            and fixed_window.get("max_epochs") == hca31.MAX_EPOCHS
            and fixed_window.get("end_epoch") == hca31.END_EPOCH
        ),
    }

    canonical_ids = {str(row["segment_id"]) for row in workload.rows}
    run_rows: list[dict[str, Any]] = []
    release_maps: list[dict[str, float]] = []
    for repeat in range(1, hca31.STABLE_REPEATS + 1):
        run_id = f"run_{repeat:02d}"
        run_dir = case_root / run_id
        status = _read_json(run_dir / "run_status.json")
        metrics = _read_json(run_dir / "metrics.json")
        lifecycle_path = run_dir / "segment_lifecycle.csv"
        releases = _release_map(lifecycle_path)
        release_maps.append(releases)
        identity = {
            "run_id": status.get("run_id") == run_id,
            "speed": _same_number(status.get("speed_mps"), case.speed_mps),
            "fixed_window": (
                status.get("start_epoch") == hca31.START_EPOCH
                and status.get("max_epochs") == hca31.MAX_EPOCHS
            ),
            "no_fault": status.get("fault_schedule") == "none",
            "storage_role": (
                status.get("storage_in_goal") == native31.STORAGE_NODE
                and status.get("storage_out_start") == native31.STORAGE_NODE
            ),
        }
        release_full = {
            "metrics_schema": (
                metrics.get("schema") == "g4irsf24.fresh_hca.metrics.v1"
            ),
            "metrics_run_id": metrics.get("run_id") == run_id,
            "canonical_segment_count": (
                metrics.get("canonical_segment_count") == workload.segment_count
            ),
            "canonical_raw_bag_count": (
                metrics.get("canonical_raw_bag_count") == workload.raw_bag_count
            ),
            "reported_all_segments_released": (
                metrics.get("released_segment_count") == workload.segment_count
            ),
            "lifecycle_exact_canonical_segments": (
                len(releases) == workload.segment_count
                and set(releases) == canonical_ids
            ),
        }
        run_rows.append(
            {
                "run_id": run_id,
                "identity_gates": identity,
                "release_gates": release_full,
                "reported_released_segment_count": metrics.get(
                    "released_segment_count"
                ),
                "lifecycle_segment_count": len(releases),
                "lifecycle": _portable_path(lifecycle_path),
            }
        )

    run_01_status = _read_json(case_root / "run_01/run_status.json")
    run_01_metrics = _read_json(case_root / "run_01/metrics.json")
    run_01_corrected = bool(
        run_01_status.get("status") == "complete"
        and run_01_status.get("returncode") == 0
        and run_01_metrics.get("status") == "complete"
        and all(run_rows[0]["identity_gates"].values())
    )
    all_repeat_traces_full = all(
        all(row["identity_gates"].values())
        and all(row["release_gates"].values())
        for row in run_rows
    )
    repeat_release_equal = bool(
        release_maps
        and release_maps[0]
        and all(value == release_maps[0] for value in release_maps[1:])
    )
    gates = {
        "matching_case_protocol": all(protocol_gates.values()),
        "corrected_run_01_complete": run_01_corrected,
        "all_repeat_release_traces_cover_canonical_segments": (
            all_repeat_traces_full
        ),
        "repeat_segment_release_values_identical": repeat_release_equal,
    }
    passed = all(gates.values())
    if passed:
        status_value = "ELIGIBLE_EXACT_HCA_RELEASE_TRACE"
    elif not gates["matching_case_protocol"] or not gates[
        "corrected_run_01_complete"
    ]:
        status_value = N_A_SOURCE
    elif not gates["all_repeat_release_traces_cover_canonical_segments"]:
        status_value = N_A_RELEASE
    else:
        status_value = N_A_REPEAT
    reference = case_root / "run_01/segment_lifecycle.csv"
    return (
        {
            "status": status_value,
            "pass": passed,
            "hca_case_id": expected_case_id,
            "reference_run_id": "run_01",
            "canonical_segment_count": workload.segment_count,
            "protocol": _portable_path(protocol_path),
            "protocol_gates": protocol_gates,
            "gates": gates,
            "runs": run_rows,
            "repeat_release_comparison": (
                "direct_segment_id_to_release_epoch_equality"
            ),
        },
        reference if passed else None,
    )


def inspect_hca_full_population_timing(
    metrics_path: Path,
    workload: native31.Workload,
) -> dict[str, Any]:
    """Return run_01 Java-release timing only for its full population."""

    metrics = _read_json(metrics_path)
    denominators = metrics.get("denominators")
    denominators = denominators if isinstance(denominators, Mapping) else {}
    java_release = denominators.get("java_release")
    java_release = java_release if isinstance(java_release, Mapping) else {}
    seconds = java_release.get("seconds")
    seconds = seconds if isinstance(seconds, Mapping) else {}
    values = {name: _number(seconds.get(name)) for name in METRICS}
    gates = {
        "comparison_eligible": metrics.get("comparison_eligible") is True,
        "not_survivor_only": metrics.get("survivor_only") is False,
        "scope_full": metrics.get("scope") == "canonical_full",
        "all_segments_released": (
            metrics.get("released_segment_count") == workload.segment_count
        ),
        "all_segments_planned": (
            metrics.get("planned_segment_count") == workload.segment_count
        ),
        "all_segments_completed": (
            metrics.get("completed_segment_count") == workload.segment_count
        ),
        "all_raw_bags_completed": (
            metrics.get("canonical_complete_raw_bag_count")
            == workload.raw_bag_count
        ),
        "java_release_denominator_full": (
            java_release.get("count") == workload.raw_bag_count
        ),
        "five_metrics_finite": all(value is not None for value in values.values()),
    }
    passed = all(gates.values())
    return {
        "status": "FULL_POPULATION_TIMING" if passed else N_A_HCA_TIMING,
        "pass": passed,
        "source": _portable_path(metrics_path),
        "denominator": "sum_over_segments(finish_time-segment_release_epoch)",
        "raw_bag_count": workload.raw_bag_count,
        "gates": gates,
        "metrics_seconds": values if passed else None,
        "survivor_or_common_cohort_comparison_allowed": False,
    }


def align_to_audited_hca_release(
    case: native31.CaseSpec,
    workload: native31.Workload,
    hca_root: Path,
) -> AlignmentResult:
    """Apply G24's exact release replacement after the trace passes its gate."""

    trace_gate, lifecycle_path = inspect_hca_release_trace(
        case, workload, hca_root
    )
    metrics_path = hca_root / _hca_case_id(case) / "run_01/metrics.json"
    hca_timing = inspect_hca_full_population_timing(metrics_path, workload)
    if lifecycle_path is None or hca_timing.get("pass") is not True:
        return AlignmentResult(None, trace_gate, hca_timing)
    prefix = harness.InputPrefix(
        size_segments=workload.segment_count,
        rows=workload.rows,
        prefix_sha256="",
        raw_bag_count=workload.raw_bag_count,
        first_segment_id=str(workload.rows[0]["segment_id"]),
        last_segment_id=str(workload.rows[-1]["segment_id"]),
    )
    adjusted, alignment = g24.apply_exact_hca_releases(prefix, lifecycle_path)
    trace_gate = {
        **trace_gate,
        "alignment": {
            **alignment,
            "only_modified_input_field": "pass_time",
            "algorithm_or_policy_modified": False,
        },
    }
    return AlignmentResult(
        replace(workload, rows=tuple(dict(row) for row in adjusted.rows)),
        trace_gate,
        hca_timing,
    )


def _base_artifact(
    case: native31.CaseSpec,
    workload: native31.Workload,
    alignment: AlignmentResult,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "case_id": case.case_id,
        "case": case.as_dict(),
        "map_id": native31.MAP_ID,
        "view_role": "SECONDARY_STABLE_TIMING_ONLY",
        "primary_view": {
            "protocol": "OWN_SOURCE_FIXED_WINDOW_FIXED_DENOMINATOR_CAPACITY",
            "remains_primary": True,
            "modified_by_this_runner": False,
        },
        "comparison_contract": {
            "reference_arm": "HCA_corrected_run_01",
            "candidate_arm": "S4_same_segment_release_trace",
            "same_segment_release_required": True,
            "both_full_raw_bag_populations_required": True,
            "metrics_seconds": list(METRICS),
            "lower_is_better": True,
            "survivor_only_comparison_allowed": False,
            "common_cohort_comparison_allowed": False,
            "capacity_verdict_allowed": False,
        },
        "selection": {
            "scale": case.scale,
            "speed_mps": case.speed_mps,
            "raw_bag_count": workload.raw_bag_count,
            "segment_count": workload.segment_count,
            "whole_population": True,
        },
        "hca_release_trace": dict(alignment.trace_gate),
        "hca_timing": dict(alignment.hca_timing),
    }


def prepare_case(
    case_id: str,
    *,
    task_dir: Path = native31.DEFAULT_TASK_DIR,
    hca_root: Path = DEFAULT_HCA_ROOT,
    map_profile_path: Path = native31.DEFAULT_MAP_PROFILE,
    binary: Path | None,
) -> PreparedCase:
    case = native31.case_by_id(case_id)
    if case.group != "stable_speed" or case.fault_scenario is not None:
        raise PairedTimingError("paired timing runner accepts stable-speed cases only")
    workload = native31.load_workload(case.scale, task_dir)
    alignment = align_to_audited_hca_release(case, workload, hca_root)
    common = _base_artifact(case, workload, alignment)
    if alignment.trace_gate.get("pass") is not True:
        return PreparedCase(
            artifact={
                **common,
                "status": alignment.trace_gate["status"],
                "native_execution_started": False,
                "comparison": {
                    "status": "N_A",
                    "reason": "HCA release trace is not full and repeat-identical",
                    "metric_rows": [],
                },
            }
        )
    if alignment.hca_timing.get("pass") is not True:
        return PreparedCase(
            artifact={
                **common,
                "status": N_A_HCA_TIMING,
                "native_execution_started": False,
                "comparison": {
                    "status": "N_A",
                    "reason": "HCA run_01 did not complete the full population",
                    "metric_rows": [],
                },
            }
        )
    if alignment.workload is None:
        raise PairedTimingError("eligible HCA timing has no aligned S4 workload")
    request, runtime_rows, rejected, local = native31.prepare_native_request(
        case,
        alignment.workload,
        map_profile_path=map_profile_path,
        fault_protocol_path=native31.DEFAULT_FAULT_PROTOCOL,
        binary=binary,
    )
    if request.get("complete_on_goal_arrival") is not True:
        raise PairedTimingError(
            "paired G31 timing requires legacy-HCA goal-arrival completion"
        )
    return PreparedCase(
        artifact={
            **common,
            "status": READY,
            "native_execution_started": False,
            "algorithm_contract": {
                "policy": "S4/J2/E2 + node-local FIFO",
                "decision_scope": "one_next_edge_at_current_junction",
                "learning_active": False,
                "completion_semantics": dict(
                    native31.GOAL_ARRIVAL_COMPLETION
                ),
                "release_pairing_is_input_only": True,
                "algorithm_or_weight_change": False,
            },
        },
        workload=alignment.workload,
        request=request,
        runtime_rows=runtime_rows,
        rejected=rejected,
        local=local,
        hca_metrics_seconds=alignment.hca_timing["metrics_seconds"],
    )


def compare_five_metrics(
    hca_seconds: Mapping[str, Any],
    s4_java_release_distribution: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare the five registered metrics for two full populations."""

    s4_fields = {
        "min": "min_seconds",
        "mean": "mean_seconds",
        "p95": "p95_seconds",
        "p99": "p99_seconds",
        "max": "max_seconds",
    }
    rows: list[dict[str, Any]] = []
    for metric in METRICS:
        hca_value = _number(hca_seconds.get(metric))
        s4_value = _number(s4_java_release_distribution.get(s4_fields[metric]))
        if hca_value is None or s4_value is None:
            raise PairedTimingError(f"non-finite paired metric: {metric}")
        delta = s4_value - hca_value
        result = "S4_LOWER" if delta < 0.0 else "HCA_LOWER" if delta > 0.0 else "TIE"
        rows.append(
            {
                "metric": metric,
                "hca_seconds": hca_value,
                "s4_seconds": s4_value,
                "s4_minus_hca_seconds": delta,
                "s4_improvement_percent": (
                    (hca_value - s4_value) / hca_value * 100.0
                    if hca_value != 0.0
                    else None
                ),
                "result": result,
            }
        )
    return {
        "status": "FULL_POPULATION_SAME_RELEASE_COMPARISON",
        "metric_rows": rows,
        "s4_lower_metric_count": sum(row["result"] == "S4_LOWER" for row in rows),
        "hca_lower_metric_count": sum(row["result"] == "HCA_LOWER" for row in rows),
        "tie_metric_count": sum(row["result"] == "TIE" for row in rows),
        "all_five_s4_strictly_lower": all(
            row["result"] == "S4_LOWER" for row in rows
        ),
        "common_cohort_verdict_used": False,
    }


def execute_case(
    case_id: str,
    *,
    task_dir: Path = native31.DEFAULT_TASK_DIR,
    hca_root: Path = DEFAULT_HCA_ROOT,
    map_profile_path: Path = native31.DEFAULT_MAP_PROFILE,
    binary: Path | None,
    dry_run: bool = False,
    executor: Executor | None = None,
    admission_checker: AdmissionChecker | None = None,
) -> dict[str, Any]:
    prepared = prepare_case(
        case_id,
        task_dir=task_dir,
        hca_root=hca_root,
        map_profile_path=map_profile_path,
        binary=binary,
    )
    common = dict(prepared.artifact)
    if prepared.request is None or dry_run:
        return common
    if binary is None:
        raise PairedTimingError("binary is required for paired S4 execution")
    if prepared.workload is None or prepared.local is None:
        raise PairedTimingError("paired S4 request lacks its aligned workload")

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    payload = selected_executor(**prepared.request)
    wall_seconds = time.perf_counter() - wall_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise PairedTimingError("native executor did not return summary and bag rows")
    if any(not isinstance(row, Mapping) for row in bags):
        raise PairedTimingError("native executor returned a non-object bag row")

    outcome = g26.summarize_paper_outcome(
        prepared.workload.rows,
        bags,
        total_raw_bags=prepared.workload.raw_bag_count,
    )
    case = native31.case_by_id(case_id)
    checker = admission_checker or native31._runtime_admission
    safety = checker(
        case,
        prepared.workload,
        prepared.request,
        prepared.runtime_rows,
        prepared.rejected,
        prepared.local,
        summary,
        bags,
        outcome,
    )
    runtime = {
        "wall_seconds": wall_seconds,
        "event_count": int(native31._number(summary, "event_count") or 0),
        "time_limit_reached": summary.get("time_limit_reached"),
        "event_limit_reached": summary.get("event_limit_reached"),
    }
    if safety.get("pass") is not True:
        return {
            **common,
            "status": FAILED,
            "native_execution_started": True,
            "outcome": outcome,
            "safety": safety,
            "runtime": runtime,
            "comparison": {
                "status": "N_A",
                "reason": "paired S4 safety admission failed",
                "metric_rows": [],
            },
        }

    full_population = bool(
        outcome.get("completed_raw_bag_count") == prepared.workload.raw_bag_count
        and summary.get("completed_count") == prepared.workload.segment_count
        and len(bags) == prepared.workload.segment_count
    )
    if not full_population:
        return {
            **common,
            "status": N_A_S4_TIMING,
            "native_execution_started": True,
            "outcome": outcome,
            "safety": safety,
            "runtime": runtime,
            "comparison": {
                "status": "N_A",
                "reason": "paired S4 did not complete the full population",
                "metric_rows": [],
                "survivor_or_common_cohort_comparison_allowed": False,
            },
        }

    distributions, raw = g24.timing_distributions(prepared.workload.rows, bags)
    java_release = distributions["java_release"]
    if prepared.hca_metrics_seconds is None:
        raise PairedTimingError("eligible paired case lacks HCA timing metrics")
    comparison = compare_five_metrics(
        prepared.hca_metrics_seconds, java_release
    )
    return {
        **common,
        "status": COMPLETE,
        "native_execution_started": True,
        "outcome": outcome,
        "safety": safety,
        "runtime": runtime,
        "paired_s4_timing": {
            "status": "FULL_POPULATION_TIMING",
            "raw_bag_count": len(raw),
            "denominator": (
                "sum_over_segments(finish_time-HCA_run_01_segment_release_epoch)"
            ),
            "metrics_seconds": {
                metric: java_release[
                    {
                        "min": "min_seconds",
                        "mean": "mean_seconds",
                        "p95": "p95_seconds",
                        "p99": "p99_seconds",
                        "max": "max_seconds",
                    }[metric]
                ]
                for metric in METRICS
            },
        },
        "comparison": comparison,
    }


STABLE_CASE_IDS = tuple(
    case.case_id
    for case in native31.PRIMARY_CASES
    if case.group == "stable_speed" and case.fault_scenario is None
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True, choices=STABLE_CASE_IDS)
    parser.add_argument("--task-dir", type=Path, default=native31.DEFAULT_TASK_DIR)
    parser.add_argument("--hca-root", type=Path, default=DEFAULT_HCA_ROOT)
    parser.add_argument("--map-profile", type=Path, default=native31.DEFAULT_MAP_PROFILE)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    output = _rooted(args.output)
    if output.is_file() and not args.force:
        existing = _read_json(output)
        if existing.get("schema") != SCHEMA or existing.get("case_id") != args.case_id:
            raise PairedTimingError("existing paired artifact belongs to another case")
        print(json.dumps({"status": "SKIPPED_EXISTING", "case_id": args.case_id}))
        return 0
    binary = _resolve_binary(args.binary)
    if not args.dry_run and binary is None:
        # N/A cases can still be inspected without a binary.  prepare first.
        prepared = prepare_case(
            args.case_id,
            task_dir=_rooted(args.task_dir),
            hca_root=_rooted(args.hca_root),
            map_profile_path=_rooted(args.map_profile),
            binary=None,
        )
        if prepared.request is not None:
            raise PairedTimingError("no native binary found; pass --binary")
        payload = dict(prepared.artifact)
    else:
        payload = execute_case(
            args.case_id,
            task_dir=_rooted(args.task_dir),
            hca_root=_rooted(args.hca_root),
            map_profile_path=_rooted(args.map_profile),
            binary=binary,
            dry_run=args.dry_run,
        )
    _write_json(output, payload)
    print(json.dumps({"status": payload["status"], "case_id": args.case_id}))
    return 2 if payload["status"] == FAILED else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PairedTimingError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G31 same-HCA-release timing failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
