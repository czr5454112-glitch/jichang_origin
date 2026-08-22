#!/usr/bin/env python3
"""Build the map2 final-policy same-HCA-release timing view.

For each stable speed, run_01 and run_02 must expose the complete canonical
segment release map and those maps must be exactly equal.  HCA timing is
eligible only when both HCA repeats completed the whole raw-bag population.
The paired S4 arm reuses the frozen map2 G31 request and changes only each
segment's scheduled pass time to run_01's audited release epoch.

No survivor or common-cohort timing is produced.  The formal 2x HCA stable
runs release the whole schedule but do not complete the whole population, so
they are strict N/A inputs and never start S4.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, replace
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

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import run_g4irsf24_native_race as g24  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402
from scripts.eval import run_g4irsf31_map2_native as map2_native  # noqa: E402
from scripts.eval import run_g4irsf31_same_hca_release_timing as paired31  # noqa: E402


SCHEMA = "czr005.g4irsf31.map2_same_hca_release_timing.v1"
READY = "READY_G31_MAP2_SAME_HCA_RELEASE_TIMING"
COMPLETE = "COMPLETE_G31_MAP2_SAME_HCA_RELEASE_TIMING"
FAILED = "FAILED_G31_MAP2_SAME_HCA_RELEASE_TIMING_SAFETY"
N_A_RELEASE = "N_A_HCA_RELEASE_TRACE_INCOMPLETE"
N_A_REPEAT = "N_A_HCA_REPEAT_RELEASE_MISMATCH"
N_A_HCA_TIMING = "N_A_HCA_FULL_POPULATION_TIMING_UNAVAILABLE"
N_A_S4_TIMING = "N_A_PAIRED_S4_FULL_POPULATION_TIMING_UNAVAILABLE"
METRICS = ("min", "mean", "p95", "p99", "max")

FORMAL_HCA_CASE_ROOTS: Mapping[tuple[int, float], Path] = {
    (1, 1.5): ROOT / "build/g26_hca_speed_1p5",
    (1, 2.0): ROOT / "build/g26_hca_speed_2p0",
    (1, 2.5): ROOT / "build/g4irsf24_fresh_hca_full",
    (1, 3.0): ROOT / "build/g26_hca_speed_3p0",
    (2, 1.5): ROOT / "outputs/runtime/g4irsf29_hca/t5_2_speed_1p5",
    (2, 2.0): ROOT / "outputs/runtime/g4irsf29_hca/t5_2_speed_2",
    (2, 2.5): ROOT / "outputs/runtime/g4irsf29_hca/t5_2_speed_2p5",
    (2, 3.0): ROOT / "outputs/runtime/g4irsf29_hca/t5_2_speed_3",
}
DEFAULT_BINARY_DIR = ROOT / "build/g4irsf24_dlp_release/python"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs/runtime/g4irsf31_map2_paired"

Executor = Callable[..., Mapping[str, Any]]


class Map2PairedTimingError(RuntimeError):
    """Raised when a map2 paired timing input is structurally invalid."""


@dataclass(frozen=True)
class AlignmentResult:
    workload: map2_native.Workload | None
    trace_gate: Mapping[str, Any]
    hca_timing: Mapping[str, Any]


@dataclass(frozen=True)
class PreparedCase:
    artifact: Mapping[str, Any]
    workload: map2_native.Workload | None = None
    request: Mapping[str, Any] | None = None
    runtime_rows: tuple[dict[str, Any], ...] = ()
    rejected: tuple[dict[str, Any], ...] = ()
    local: Mapping[str, Any] | None = None
    hca_metrics_seconds: Mapping[str, float] | None = None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _same_number(value: Any, expected: float) -> bool:
    number = _number(value)
    return number is not None and math.isclose(
        number, expected, rel_tol=0.0, abs_tol=1.0e-12
    )


def _portable(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Map2PairedTimingError(f"JSON object required: {path}")
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


def formal_hca_case_root(scale: int, speed_mps: float) -> Path:
    try:
        return FORMAL_HCA_CASE_ROOTS[(scale, float(speed_mps))]
    except KeyError as exc:
        raise Map2PairedTimingError(
            f"no formal HCA stable run directory for {scale}x at {speed_mps:g} m/s"
        ) from exc


def _stable_speed_evidence(
    case: map2_native.CaseSpec,
    case_root: Path,
    benchmark: Mapping[str, Any],
) -> tuple[bool, str]:
    """Identify the explicit G26 speed or G24's canonical 2.5 m/s default."""

    if _number(benchmark.get("speed_mps")) is not None:
        return (
            _same_number(benchmark.get("speed_mps"), case.speed_mps),
            "benchmark_summary.speed_mps",
        )
    is_formal_g24_default = bool(
        case.scale == 1
        and math.isclose(case.speed_mps, 2.5, rel_tol=0.0, abs_tol=1.0e-12)
        and case_root.resolve()
        == formal_hca_case_root(1, 2.5).resolve()
    )
    return is_formal_g24_default, (
        "formal_g4irsf24_default_map_speed_2p5"
        if is_formal_g24_default
        else "missing"
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
                raise Map2PairedTimingError(
                    f"HCA lifecycle lacks segment_id/release_epoch: {path}"
                )
            if segment_id in releases:
                raise Map2PairedTimingError(
                    f"duplicate HCA lifecycle segment: {segment_id}"
                )
            releases[segment_id] = release
    return releases


def inspect_hca_case(
    case: map2_native.CaseSpec,
    workload: map2_native.Workload,
    case_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, float] | None]:
    """Gate two complete, repeat-identical HCA release and outcome traces."""

    canonical_ids = {str(row["segment_id"]) for row in workload.rows}
    releases_by_run: list[dict[str, float]] = []
    run_rows: list[dict[str, Any]] = []
    full_outcome_by_run: list[bool] = []
    run_01_metrics: Mapping[str, Any] = {}
    for repeat in (1, 2):
        run_id = f"run_{repeat:02d}"
        run_dir = case_root / run_id
        status = _read_json(run_dir / "run_status.json")
        metrics = _read_json(run_dir / "metrics.json")
        if repeat == 1:
            run_01_metrics = metrics
        lifecycle = run_dir / "segment_lifecycle.csv"
        releases = _release_map(lifecycle)
        releases_by_run.append(releases)
        benchmark = metrics.get("benchmark_summary")
        benchmark = benchmark if isinstance(benchmark, Mapping) else {}
        stable_speed, stable_speed_source = _stable_speed_evidence(
            case, case_root, benchmark
        )
        identity_gates = {
            "run_id": (
                status.get("run_id") == run_id and metrics.get("run_id") == run_id
            ),
            "complete_process": (
                status.get("schema") == "g4irsf24.fresh_hca.run.v1"
                and status.get("status") == "complete"
                and status.get("returncode") == 0
            ),
            "fixed_window": (
                status.get("start_epoch") == 8_260
                and status.get("max_epochs") == 90_000
            ),
            "stable_speed": stable_speed,
            "no_fault": (
                _same_number(benchmark.get("active_fault_count"), 0.0)
                and _same_number(benchmark.get("fault_event_count"), 0.0)
            ),
            "population": (
                metrics.get("canonical_segment_count") == workload.segment_count
                and metrics.get("canonical_raw_bag_count")
                == workload.raw_bag_count
            ),
        }
        release_gates = {
            "all_segments_reported_released": (
                metrics.get("released_segment_count") == workload.segment_count
            ),
            "lifecycle_exact_canonical_segments": (
                len(releases) == workload.segment_count
                and set(releases) == canonical_ids
            ),
        }
        full_outcome = bool(
            metrics.get("comparison_eligible") is True
            and metrics.get("survivor_only") is False
            and metrics.get("scope") == "canonical_full"
            and metrics.get("planned_segment_count") == workload.segment_count
            and metrics.get("completed_segment_count") == workload.segment_count
            and metrics.get("canonical_complete_raw_bag_count")
            == workload.raw_bag_count
        )
        full_outcome_by_run.append(full_outcome)
        run_rows.append(
            {
                "run_id": run_id,
                "root": _portable(run_dir),
                "identity_gates": identity_gates,
                "stable_speed_source": stable_speed_source,
                "release_gates": release_gates,
                "full_population_outcome": full_outcome,
                "released_segment_count": metrics.get("released_segment_count"),
                "completed_segment_count": metrics.get(
                    "completed_segment_count"
                ),
                "completed_raw_bag_count": metrics.get(
                    "canonical_complete_raw_bag_count"
                ),
            }
        )

    release_full = all(
        all(row["identity_gates"].values())
        and all(row["release_gates"].values())
        for row in run_rows
    )
    repeat_equal = bool(
        releases_by_run[0]
        and releases_by_run[0] == releases_by_run[1]
    )
    trace_gates = {
        "both_runs_identify_formal_stable_case": all(
            all(row["identity_gates"].values()) for row in run_rows
        ),
        "both_runs_release_all_canonical_segments": release_full,
        "run_01_run_02_segment_release_values_identical": repeat_equal,
    }
    trace_pass = all(trace_gates.values())
    if trace_pass:
        trace_status = "ELIGIBLE_EXACT_HCA_RELEASE_TRACE"
    elif not release_full:
        trace_status = N_A_RELEASE
    else:
        trace_status = N_A_REPEAT
    trace = {
        "status": trace_status,
        "pass": trace_pass,
        "formal_case_root": _portable(case_root),
        "canonical_segment_count": workload.segment_count,
        "gates": trace_gates,
        "runs": run_rows,
        "repeat_release_comparison": "direct_segment_id_to_release_epoch_equality",
    }

    denominators = run_01_metrics.get("denominators")
    denominators = denominators if isinstance(denominators, Mapping) else {}
    java_release = denominators.get("java_release")
    java_release = java_release if isinstance(java_release, Mapping) else {}
    seconds = java_release.get("seconds")
    seconds = seconds if isinstance(seconds, Mapping) else {}
    values = {metric: _number(seconds.get(metric)) for metric in METRICS}
    timing_gates = {
        "both_hca_repeats_complete_full_population": all(full_outcome_by_run),
        "run_01_java_release_denominator_full": (
            java_release.get("count") == workload.raw_bag_count
        ),
        "run_01_five_metrics_finite": all(
            value is not None for value in values.values()
        ),
    }
    timing_pass = trace_pass and all(timing_gates.values())
    timing = {
        "status": "FULL_POPULATION_TIMING" if timing_pass else N_A_HCA_TIMING,
        "pass": timing_pass,
        "raw_bag_count": workload.raw_bag_count,
        "denominator": "sum_over_segments(finish_time-segment_release_epoch)",
        "gates": timing_gates,
        "metrics_seconds": values if timing_pass else None,
        "survivor_or_common_cohort_comparison_allowed": False,
    }
    return trace, timing, releases_by_run[0] if trace_pass else None


def _align_workload(
    workload: map2_native.Workload,
    releases: Mapping[str, float],
) -> tuple[map2_native.Workload, dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    deltas: list[float] = []
    for source in workload.rows:
        row = dict(source)
        segment_id = str(row["segment_id"])
        release = releases[segment_id]
        deltas.append(release - float(row["pass_time"]))
        row["pass_time"] = release
        rows.append(row)
    return replace(workload, rows=tuple(rows)), {
        "aligned_segment_count": len(rows),
        "release_minus_canonical_pass_mean_seconds": statistics.fmean(deltas),
        "release_minus_canonical_pass_min_seconds": min(deltas),
        "release_minus_canonical_pass_max_seconds": max(deltas),
        "only_modified_input_field": "pass_time",
        "algorithm_or_policy_modified": False,
    }


def align_to_hca_release(
    case: map2_native.CaseSpec,
    workload: map2_native.Workload,
    case_root: Path,
) -> AlignmentResult:
    trace, timing, releases = inspect_hca_case(case, workload, case_root)
    if releases is None or timing.get("pass") is not True:
        return AlignmentResult(None, trace, timing)
    aligned, details = _align_workload(workload, releases)
    return AlignmentResult(
        aligned,
        {**trace, "alignment": details},
        timing,
    )


def _base_artifact(
    case: map2_native.CaseSpec,
    workload: map2_native.Workload,
    alignment: AlignmentResult,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "case_id": case.case_id,
        "case": case.as_dict(),
        "map_id": map2_native.MAP_ID,
        "view_role": "SECONDARY_STABLE_TIMING_ONLY",
        "primary_view": {
            "protocol": "OWN_SOURCE_FIXED_WINDOW_FIXED_DENOMINATOR_CAPACITY",
            "remains_primary": True,
            "modified_by_this_runner": False,
        },
        "comparison_contract": {
            "reference_arm": "HCA_formal_run_01",
            "candidate_arm": "S4_same_segment_release_trace",
            "same_segment_release_required": True,
            "both_hca_repeats_full_population_required": True,
            "both_frameworks_full_raw_bag_populations_required": True,
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
    workload_1x: Path = map2_native.DEFAULT_WORKLOAD_1X,
    workload_2x: Path = map2_native.DEFAULT_WORKLOAD_2X,
    hca_case_root: Path | None = None,
    binary: Path | None,
) -> PreparedCase:
    case = map2_native.case_by_id(case_id)
    if case.group != "stable_speed" or case.fault_scenario is not None:
        raise Map2PairedTimingError("paired timing accepts stable-speed cases only")
    workload = map2_native.load_workload(
        case.scale, workload_1x, workload_2x
    )
    root = (
        hca_case_root.resolve()
        if hca_case_root is not None
        else formal_hca_case_root(case.scale, case.speed_mps)
    )
    alignment = align_to_hca_release(case, workload, root)
    common = _base_artifact(case, workload, alignment)
    if alignment.trace_gate.get("pass") is not True:
        return PreparedCase(
            artifact={
                **common,
                "status": alignment.trace_gate["status"],
                "native_execution_started": False,
                "comparison": {
                    "status": "N_A",
                    "reason": "HCA release trace is not complete and repeat-identical",
                    "metric_rows": [],
                    "survivor_or_common_cohort_comparison_allowed": False,
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
                    "reason": "HCA repeats did not complete the full population",
                    "metric_rows": [],
                    "survivor_or_common_cohort_comparison_allowed": False,
                },
            }
        )
    if alignment.workload is None:
        raise Map2PairedTimingError("eligible HCA timing has no aligned workload")
    request, runtime_rows, rejected, local = map2_native.prepare_native_request(
        case, alignment.workload, binary=binary
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
                "strict_local_potential_descent": True,
                "local_software_queue_capacity": 0,
                "direct_neighbor_merge_calendar_visibility": True,
                "goal_arrival_completion": True,
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


def execute_case(
    case_id: str,
    *,
    workload_1x: Path = map2_native.DEFAULT_WORKLOAD_1X,
    workload_2x: Path = map2_native.DEFAULT_WORKLOAD_2X,
    hca_case_root: Path | None = None,
    binary: Path | None,
    dry_run: bool = False,
    executor: Executor | None = None,
) -> dict[str, Any]:
    prepared = prepare_case(
        case_id,
        workload_1x=workload_1x,
        workload_2x=workload_2x,
        hca_case_root=hca_case_root,
        binary=binary,
    )
    common = dict(prepared.artifact)
    if prepared.request is None or dry_run:
        return common
    if binary is None or prepared.workload is None or prepared.local is None:
        raise Map2PairedTimingError("eligible paired execution lacks runtime inputs")

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    payload = selected_executor(**prepared.request)
    wall_seconds = time.perf_counter() - wall_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise Map2PairedTimingError("native executor did not return summary and bags")
    if any(not isinstance(row, Mapping) for row in bags):
        raise Map2PairedTimingError("native executor returned a non-object bag row")

    outcome = g26.summarize_paper_outcome(
        prepared.workload.rows,
        bags,
        total_raw_bags=prepared.workload.raw_bag_count,
    )
    case = map2_native.case_by_id(case_id)
    safety = map2_native.g31_native._runtime_admission(
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
        "event_count": int(summary.get("event_count", 0)),
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
        raise Map2PairedTimingError("eligible case lacks HCA timing metrics")
    comparison = paired31.compare_five_metrics(
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
    for case in map2_native.PRIMARY_CASES
    if case.group == "stable_speed"
)


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _resolve_binary(path: Path | None) -> Path | None:
    if path is not None:
        return _rooted(path).resolve(strict=True)
    candidates = sorted(DEFAULT_BINARY_DIR.glob("czr005_cpp*.pyd"))
    return candidates[-1].resolve() if candidates else None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True, choices=STABLE_CASE_IDS)
    parser.add_argument(
        "--workload-1x", type=Path, default=map2_native.DEFAULT_WORKLOAD_1X
    )
    parser.add_argument(
        "--workload-2x", type=Path, default=map2_native.DEFAULT_WORKLOAD_2X
    )
    parser.add_argument("--hca-case-root", type=Path)
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
            raise Map2PairedTimingError("existing artifact belongs to another case")
        print(json.dumps({"status": "SKIPPED_EXISTING", "case_id": args.case_id}))
        return 0
    binary = None if args.dry_run else _resolve_binary(args.binary)
    payload = execute_case(
        args.case_id,
        workload_1x=_rooted(args.workload_1x),
        workload_2x=_rooted(args.workload_2x),
        hca_case_root=(
            _rooted(args.hca_case_root) if args.hca_case_root is not None else None
        ),
        binary=binary,
        dry_run=args.dry_run,
    )
    _write_json(output, payload)
    print(json.dumps({"status": payload["status"], "case_id": args.case_id}))
    return 2 if payload["status"] == FAILED else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Map2PairedTimingError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G31 map2 same-release timing failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
