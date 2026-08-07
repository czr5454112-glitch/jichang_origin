#!/usr/bin/env python3
"""Run the G18 eager/JIT mechanism campaign on real native workloads.

The runner deliberately keeps the first G18 question narrow: does delaying a
destination-merge grant until the natural service opportunity create a real
bounded local choice, and what does that do to business time and event
amplification?  It never treats a score-only or singleton boundary as an
arbitration opportunity.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _path in (ROOT, ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


SCHEMA_PLAN = "czr005.g4irsf18.jit_campaign_plan.v1"
SCHEMA_RESULT = "czr005.g4irsf18.jit_campaign_result.v1"
SCHEMA_ANALYSIS = "czr005.g4irsf18.jit_campaign_analysis.v1"

DEFAULT_PLAN = ROOT / "artifacts/manifests/g4irsf18_jit_campaign_plan.json"
DEFAULT_RESULTS = ROOT / "outputs/runtime/g4irsf18_jit_campaign"
DEFAULT_ANALYSIS = ROOT / "outputs/tables/g4irsf18_jit_comparisons.json"
DEFAULT_TABLE = ROOT / "outputs/tables/g4irsf18_jit_results.csv"
DEFAULT_MECHANISM_REPORT = ROOT / "outputs/reports/g4irsf18_jit_mechanism.md"
DEFAULT_EVENT_REPORT = ROOT / "outputs/reports/g4irsf18_event_amplification.md"

ALLOWED_PREFIXES = (144, 512, 2_048, 8_192, 43_603)
ALLOWED_SCALES = (1, 2, 4, 8, 16, 32)

COUNTERS = (
    "merge_grant_service_opportunity_count",
    "merge_grant_multi_candidate_opportunity_count",
    "merge_grant_true_competition_count",
    "merge_grant_order_mutation_count",
    "merge_grant_candidate_total_count",
    "merge_grant_peak_pending_requests",
    "merge_grant_wakeup_scheduled_count",
    "merge_grant_wakeup_coalesced_count",
    "merge_grant_stale_wakeup_count",
    "merge_grant_opportunity_trace_total_count",
    "merge_grant_opportunity_trace_stored_count",
    "merge_grant_opportunity_trace_dropped_count",
    "merge_grant_request_count",
    "destination_merge_arbitration_event_count",
    "event_count",
    "decision_count",
    "requested_count",
    "completed_count",
    "failed_count",
    "reservation_conflicts",
    "physical_fault_edge_entry_violation_count",
    "unresolved_deadlock_count",
    "runtime_full_astar_calls",
    "runtime_full_cie_astar_calls",
    "global_reservation_scan_count",
    "priority_future_route_input_count",
    "scorer_future_route_input_count",
    "scorer_future_schedule_input_count",
    "first_edge_credit_future_route_count",
    "full_future_routes_stored",
    "event_limit_reached",
    "time_limit_reached",
    "cpp_internal_accounted_bytes",
)


class G18JitCampaignError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise G18JitCampaignError(message)


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    payload = (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"JSON artifact is not an object: {path}")
    return value


def _integer(value: Any) -> int | None:
    return int(value) if type(value) is int else None


def _finite(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


@dataclass(frozen=True)
class Variant:
    variant_id: str
    timing_mode: str
    merge_rule: str


VARIANTS: tuple[Variant, ...] = (
    Variant("J0_F2_EAGER", "eager", "M1"),
    Variant("J1_F2_JIT_FIFO", "jit_fifo", "M1"),
    Variant("J2_F2_JIT_FAIR_AGING_DEADLINE", "jit_fair_aging_deadline", "M3"),
)
VARIANT_BY_ID = {variant.variant_id: variant for variant in VARIANTS}


@dataclass(frozen=True)
class Job:
    job_id: str
    variant_id: str
    prefix_segments: int | None
    scale: int

    @classmethod
    def create(
        cls, variant_id: str, *, prefix_segments: int | None, scale: int
    ) -> "Job":
        scope = f"s{prefix_segments}" if prefix_segments is not None else f"{scale}x_full"
        return cls(
            job_id=f"{variant_id.lower()}__{scope}",
            variant_id=variant_id,
            prefix_segments=prefix_segments,
            scale=scale,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "variant_id": self.variant_id,
            "prefix_segments": self.prefix_segments,
            "scale": self.scale,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "Job":
        variant_id = value.get("variant_id")
        prefix = value.get("prefix_segments")
        scale = value.get("scale")
        _require(variant_id in VARIANT_BY_ID, "unknown JIT variant")
        _require(prefix is None or type(prefix) is int, "invalid prefix_segments")
        _require(type(scale) is int and scale in ALLOWED_SCALES, "invalid scale")
        _require(
            (prefix in ALLOWED_PREFIXES and scale == 1) or (prefix is None),
            "prefix jobs must use a supported 1x prefix",
        )
        expected = cls.create(str(variant_id), prefix_segments=prefix, scale=scale)
        _require(value.get("job_id") == expected.job_id, "job identity drifted")
        return expected


def build_plan(
    *,
    prefixes: Sequence[int] = (144, 512, 2_048, 8_192),
    full_scales: Sequence[int] = (),
) -> dict[str, Any]:
    normalized_prefixes = tuple(int(value) for value in prefixes)
    normalized_scales = tuple(int(value) for value in full_scales)
    _require(len(set(normalized_prefixes)) == len(normalized_prefixes), "duplicate prefix")
    _require(all(value in ALLOWED_PREFIXES for value in normalized_prefixes), "bad prefix")
    _require(len(set(normalized_scales)) == len(normalized_scales), "duplicate scale")
    _require(all(value in ALLOWED_SCALES for value in normalized_scales), "bad scale")
    jobs = [
        Job.create(variant.variant_id, prefix_segments=prefix, scale=1).as_dict()
        for prefix in normalized_prefixes
        for variant in VARIANTS
    ]
    for scale in normalized_scales:
        if scale == 1 and 43_603 in normalized_prefixes:
            continue
        jobs.extend(
            Job.create(variant.variant_id, prefix_segments=None, scale=scale).as_dict()
            for variant in VARIANTS
        )
    return {
        "schema": SCHEMA_PLAN,
        "design": {
            "topology": "fixed canonical real airport map",
            "locality": "one destination merge and adjacent incoming requests only",
            "matched_controls": "same input/release stream; only timing mode/rule differ",
            "variants": [variant.__dict__ for variant in VARIANTS],
            "score_only_is_not_control": True,
        },
        "prefixes": list(normalized_prefixes),
        "full_scales": list(normalized_scales),
        "jobs": jobs,
    }


def validate_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    _require(value.get("schema") == SCHEMA_PLAN, "unsupported plan schema")
    raw = value.get("jobs")
    _require(isinstance(raw, list) and raw, "plan has no jobs")
    jobs = [Job.from_mapping(row) for row in raw if isinstance(row, Mapping)]
    _require(len(jobs) == len(raw), "plan contains a non-object job")
    _require(len({job.job_id for job in jobs}) == len(jobs), "duplicate job ID")
    return dict(value)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        result = [json.loads(line) for line in handle if line.strip()]
    _require(result and all(isinstance(row, dict) for row in result), f"bad JSONL: {path}")
    return result


def _load_input(job: Job, root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if job.prefix_segments is not None:
        from scripts.eval import g4irsf12_reproducible_harness as g12

        prefix = g12.load_input_prefix(job.prefix_segments, root=root)
        return [dict(row) for row in prefix.rows], {
            "protocol": "protected_first_n_file_order",
            "segments": job.prefix_segments,
            "scale": 1,
            "topology_changed": False,
            "tth_denominator": "original_entry_time_tth",
        }

    from scripts.eval import run_g4irsf10_v2_safe_scale_hardcase_training as g10

    path, metadata = g10.ensure_source_queue_for_case(
        scale=job.scale,
        rolling_days=1,
        time_compression=1.0,
        label=f"g4irsf18_jit_{job.scale}x",
    )
    return _load_jsonl(path), {
        "protocol": "g4irsf10_distribution_preserving_fixed_map_resample",
        "segments": int(metadata.get("segment_count", 0)) or None,
        "scale": job.scale,
        "topology_changed": bool(metadata.get("topology_changed", False)),
        "tth_denominator": "java_release_time_tth",
    }


def _binding_rows(rows: Sequence[Mapping[str, Any]]) -> list[tuple[Any, ...]]:
    return [
        (
            str(row["segment_id"]),
            int(row["task_id"]),
            float(row["pass_time"]),
            float(row["std"]),
            int(row["start"]),
            int(row["goal"]),
            str(row.get("source", f"node_{int(row['start'])}")),
        )
        for row in rows
    ]


def _raw_bags(
    input_rows: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Any],
    denominator: str,
) -> list[dict[str, Any]]:
    from scripts.eval import g4irsf12_reproducible_harness as g12

    bags = payload.get("bags")
    _require(isinstance(bags, list), "native payload lacks bags")
    merge_wait_by_task: dict[int, float] = {}
    for segment in bags:
        _require(isinstance(segment, Mapping), "native bag row is not an object")
        task_id = _integer(segment.get("task_id"))
        merge_wait = _finite(segment.get("merge_grant_wait_seconds"))
        if task_id is not None and merge_wait is not None:
            merge_wait_by_task[task_id] = (
                merge_wait_by_task.get(task_id, 0.0) + merge_wait
            )
    aggregated = g12.aggregate_raw_bag_timings(
        input_rows,
        bags,
        allow_release_before_original_entry=(denominator == "java_release_time_tth"),
    )
    result: list[dict[str, Any]] = []
    for row in aggregated:
        complete = bool(row["complete"])
        result.append(
            {
                "task_id": int(row["task_id"]),
                "complete": complete,
                "tth_seconds": (
                    row[f"{denominator}_seconds"] if complete else None
                ),
                "source_wait_seconds": row["source_wait_seconds"] if complete else None,
                "network_time_seconds": row["network_time_seconds"] if complete else None,
                "merge_grant_wait_seconds": (
                    merge_wait_by_task.get(int(row["task_id"]), 0.0)
                    if complete
                    else None
                ),
            }
        )
    return result


def _write_jsonl_zst(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    try:
        import zstandard
    except ImportError as exc:  # project dependency
        raise G18JitCampaignError("zstandard is required for opportunity traces") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as raw:
        with zstandard.ZstdCompressor(level=3).stream_writer(raw, closefd=False) as stream:
            for row in rows:
                stream.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
                    + b"\n"
                )
    os.replace(temporary, path)


def _hard_safety(summary: Mapping[str, Any], requested: int) -> dict[str, Any]:
    global_reads = (
        "global_reservation_scan_count",
        "priority_global_scan_count",
        "scorer_runtime_global_scan_count",
        "microphase_runtime_global_scan_count",
        "first_edge_credit_global_scan_count",
    )
    future_route_reads = (
        "priority_future_route_input_count",
        "scorer_future_route_input_count",
        "first_edge_credit_future_route_count",
    )
    gates = {
        "all_segments_completed": _integer(summary.get("completed_count")) == requested,
        "failed_zero": _integer(summary.get("failed_count")) == 0,
        "conflict_zero": _integer(summary.get("reservation_conflicts")) == 0,
        "unsafe_zero": _integer(summary.get("physical_fault_edge_entry_violation_count")) == 0,
        "deadlock_zero": _integer(summary.get("unresolved_deadlock_count")) == 0,
        "full_astar_zero": _integer(summary.get("runtime_full_astar_calls")) == 0,
        "full_cie_zero": _integer(summary.get("runtime_full_cie_astar_calls", 0)) == 0,
        "global_scan_zero": all(_integer(summary.get(name)) == 0 for name in global_reads),
        "future_route_zero": all(
            _integer(summary.get(name)) == 0 for name in future_route_reads
        ),
        "future_schedule_zero": _integer(
            summary.get("scorer_future_schedule_input_count")
        ) == 0,
        "future_routes_not_stored": (
            _integer(summary.get("full_future_routes_stored")) == 0
            and summary.get("bag_future_path_field_present") is False
        ),
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "time_limit_not_reached": summary.get("time_limit_reached") is False,
    }
    return {"pass": all(gates.values()), "gates": gates}


def execute_job(job: Job, *, binary: Path, root: Path = ROOT) -> dict[str, Any]:
    from scripts.eval.g4irsf11_fixed_map import assert_canonical_map, canonical_graph_records
    from scripts.eval.g4irsf14_opportunity_census import FROZEN_RUNTIME_CONTROLS, MODEL_PATH
    from czr005.cpp_backend import g4irsf11_event_runtime_from_records

    rows, descriptor = _load_input(job, root)
    _require(descriptor["topology_changed"] is False, "scale input changed topology")
    variant = VARIANT_BY_ID[job.variant_id]
    nodes, edges, heuristic = canonical_graph_records(assert_canonical_map())
    resolved_binary = binary.resolve(strict=True)
    request = dict(FROZEN_RUNTIME_CONTROLS)
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=_binding_rows(rows),
        fault_windows=(),
        scenario=f"g4irsf18_{job.job_id}",
        summary_only=False,
        trace_limit=0,
        event_trace_limit=0,
        enable_opportunity_telemetry=True,
        opportunity_trace_limit=500_000,
        scorer_model_path=(root / MODEL_PATH).resolve(strict=True),
        expected_binary_path=resolved_binary,
        search_path=resolved_binary.parent,
        g4irsf16_supervisor_mode="off",
        merge_grant_rule=variant.merge_rule,
        merge_grant_timing_mode=variant.timing_mode,
    )
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    payload = g4irsf11_event_runtime_from_records(**request)
    cpu_seconds = time.process_time() - cpu_start
    wall_seconds = time.perf_counter() - wall_start
    _require(isinstance(payload, Mapping), "native result is not an object")
    summary = payload.get("summary")
    _require(isinstance(summary, Mapping), "native result lacks summary")
    _require(
        summary.get("merge_grant_timing_mode") == variant.timing_mode,
        "native timing-mode echo mismatch",
    )
    raw = _raw_bags(rows, payload, str(descriptor["tth_denominator"]))
    completed = [row for row in raw if row["complete"]]
    tth = [float(row["tth_seconds"]) for row in completed]
    source = [float(row["source_wait_seconds"]) for row in completed]
    network = [float(row["network_time_seconds"]) for row in completed]
    merge_wait = [float(row["merge_grant_wait_seconds"]) for row in completed]
    counters = {name: summary.get(name) for name in COUNTERS}
    safety = _hard_safety(summary, len(rows))
    event_count = _integer(summary.get("event_count"))
    service = _integer(summary.get("merge_grant_service_opportunity_count"))
    opportunity_rows = payload.get("merge_service_opportunities", [])
    _require(isinstance(opportunity_rows, list), "native opportunity trace is not a list")
    opportunity_stored = _integer(
        summary.get("merge_grant_opportunity_trace_stored_count")
    )
    _require(
        opportunity_stored is None or opportunity_stored == len(opportunity_rows),
        "native opportunity stored-count identity failed",
    )
    return {
        "schema": SCHEMA_RESULT,
        "job": job.as_dict(),
        "variant": variant.__dict__,
        "status": "COMPLETE" if safety["pass"] and len(completed) == len(raw) else "HARD_GATE_FAILED",
        "input": descriptor,
        "resources": {"wall_seconds": wall_seconds, "cpu_seconds": cpu_seconds},
        "hard_safety": safety,
        "metrics": {
            "requested_segments": len(rows),
            "complete_raw_bags": len(completed),
            "raw_bag_count": len(raw),
            "mean_tth_seconds": statistics.fmean(tth) if len(tth) == len(raw) else None,
            "p50_tth_seconds": _quantile(tth, 0.50) if len(tth) == len(raw) else None,
            "p95_tth_seconds": _quantile(tth, 0.95) if len(tth) == len(raw) else None,
            "p99_tth_seconds": _quantile(tth, 0.99) if len(tth) == len(raw) else None,
            "max_tth_seconds": max(tth) if len(tth) == len(raw) and tth else None,
            "source_wait_mean_seconds": statistics.fmean(source) if len(source) == len(raw) else None,
            "network_time_mean_seconds": statistics.fmean(network) if len(network) == len(raw) else None,
            "merge_grant_wait_mean_seconds": (
                statistics.fmean(merge_wait) if len(merge_wait) == len(raw) else None
            ),
            "events_per_completed_segment": event_count / len(rows) if event_count is not None else None,
            "wakeups_per_service_opportunity": (
                _integer(summary.get("merge_grant_wakeup_scheduled_count")) / service
                if service not in (None, 0)
                and _integer(summary.get("merge_grant_wakeup_scheduled_count")) is not None
                else None
            ),
        },
        "counters": counters,
        "opportunity_trace": {
            "total_count": summary.get("merge_grant_opportunity_trace_total_count"),
            "stored_count": opportunity_stored,
            "dropped_count": summary.get("merge_grant_opportunity_trace_dropped_count"),
            "row_semantics": "one row per candidate; opportunity_id groups one natural service opportunity",
        },
        "_opportunity_rows": opportunity_rows,
        "raw_bags": raw,
    }


def _result_path(directory: Path, job: Job) -> Path:
    return directory / f"{job.job_id}.json"


def run_plan(
    plan: Mapping[str, Any],
    *,
    binary: Path,
    results_dir: Path,
    root: Path = ROOT,
    force: bool = False,
) -> dict[str, Any]:
    validated = validate_plan(plan)
    results_dir.mkdir(parents=True, exist_ok=True)
    executed: list[str] = []
    resumed: list[str] = []
    failed: list[str] = []
    for raw_job in validated["jobs"]:
        job = Job.from_mapping(raw_job)
        path = _result_path(results_dir, job)
        if not force and path.is_file():
            existing = _read_json(path)
            if existing.get("schema") == SCHEMA_RESULT and existing.get("job") == job.as_dict():
                resumed.append(job.job_id)
                if existing.get("status") != "COMPLETE":
                    failed.append(job.job_id)
                continue
        try:
            result = execute_job(job, binary=binary, root=root)
        except Exception as exc:
            result = {
                "schema": SCHEMA_RESULT,
                "job": job.as_dict(),
                "status": "ERROR",
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        opportunity_rows = result.pop("_opportunity_rows", None)
        if isinstance(opportunity_rows, list):
            opportunity_path = path.with_suffix(".opportunities.jsonl.zst")
            _write_jsonl_zst(opportunity_path, opportunity_rows)
            result["opportunity_trace_artifact"] = _relative(opportunity_path, root)
        _atomic_json(path, result)
        executed.append(job.job_id)
        if result.get("status") != "COMPLETE":
            failed.append(job.job_id)
    return {
        "plan_schema": validated["schema"],
        "executed": executed,
        "resumed": resumed,
        "failed": failed,
        "complete": not failed,
    }


def _paired_performance(
    baseline: Sequence[Mapping[str, Any]], candidate: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    left = {int(row["task_id"]): row for row in baseline}
    right = {int(row["task_id"]): row for row in candidate}
    common = sorted(set(left) & set(right))
    eligible = [
        task_id
        for task_id in common
        if left[task_id].get("complete") is True and right[task_id].get("complete") is True
    ]
    tth = [float(right[i]["tth_seconds"]) - float(left[i]["tth_seconds"]) for i in eligible]
    source = [
        float(right[i]["source_wait_seconds"]) - float(left[i]["source_wait_seconds"])
        for i in eligible
    ]
    network = [
        float(right[i]["network_time_seconds"]) - float(left[i]["network_time_seconds"])
        for i in eligible
    ]
    merge_wait: list[float] = []
    for task_id in eligible:
        left_wait = _finite(left[task_id].get("merge_grant_wait_seconds"))
        right_wait = _finite(right[task_id].get("merge_grant_wait_seconds"))
        if left_wait is not None and right_wait is not None:
            merge_wait.append(right_wait - left_wait)
    return {
        "paired_raw_bag_count": len(eligible),
        "mean_tth_delta_seconds": statistics.fmean(tth) if tth else None,
        "p95_tth_delta_seconds": _quantile(tth, 0.95),
        "p99_tth_delta_seconds": _quantile(tth, 0.99),
        "source_wait_delta_mean_seconds": statistics.fmean(source) if source else None,
        "network_time_delta_mean_seconds": statistics.fmean(network) if network else None,
        "merge_grant_wait_delta_mean_seconds": (
            statistics.fmean(merge_wait) if merge_wait else None
        ),
        "improved_count": sum(value < -1.0e-9 for value in tth),
        "degraded_count": sum(value > 1.0e-9 for value in tth),
        "unchanged_count": sum(abs(value) <= 1.0e-9 for value in tth),
    }


def analyse_plan(
    plan: Mapping[str, Any], *, results_dir: Path, root: Path = ROOT
) -> dict[str, Any]:
    validated = validate_plan(plan)
    results: dict[tuple[int | None, int, str], dict[str, Any]] = {}
    missing: list[str] = []
    for raw_job in validated["jobs"]:
        job = Job.from_mapping(raw_job)
        path = _result_path(results_dir, job)
        if not path.is_file():
            missing.append(job.job_id)
            continue
        result = _read_json(path)
        if result.get("schema") == SCHEMA_RESULT:
            results[(job.prefix_segments, job.scale, job.variant_id)] = result

    comparisons: list[dict[str, Any]] = []
    scopes = sorted({(prefix, scale) for prefix, scale, _ in results}, key=str)
    for prefix, scale in scopes:
        baseline = results.get((prefix, scale, "J0_F2_EAGER"))
        if baseline is None or baseline.get("status") != "COMPLETE":
            continue
        for variant in VARIANTS[1:]:
            candidate = results.get((prefix, scale, variant.variant_id))
            if candidate is None or candidate.get("status") != "COMPLETE":
                continue
            counters = candidate.get("counters", {})
            multi = _integer(counters.get("merge_grant_multi_candidate_opportunity_count"))
            true = _integer(counters.get("merge_grant_true_competition_count"))
            mutations = _integer(counters.get("merge_grant_order_mutation_count"))
            performance = _paired_performance(baseline["raw_bags"], candidate["raw_bags"])
            comparisons.append(
                {
                    "prefix_segments": prefix,
                    "scale": scale,
                    "baseline": "J0_F2_EAGER",
                    "candidate": variant.variant_id,
                    "hard_safety_pass": candidate["hard_safety"]["pass"],
                    "multi_candidate_opportunity_count": multi,
                    "true_competition_count": true,
                    "order_mutation_count": mutations,
                    "real_choice_seam_pass": (
                        multi is not None and multi > 0 and true is not None and true > 0
                    ),
                    "action_mutation_pass": mutations is not None and mutations > 0,
                    "performance": performance,
                    "events_per_segment_delta": (
                        candidate["metrics"]["events_per_completed_segment"]
                        - baseline["metrics"]["events_per_completed_segment"]
                        if candidate["metrics"]["events_per_completed_segment"] is not None
                        and baseline["metrics"]["events_per_completed_segment"] is not None
                        else None
                    ),
                }
            )

    mechanism_pass = any(
        row["real_choice_seam_pass"] and row["action_mutation_pass"]
        for row in comparisons
    )
    analysis = {
        "schema": SCHEMA_ANALYSIS,
        "status": "COMPLETE" if not missing else "INCOMPLETE",
        "missing_job_ids": missing,
        "mechanism_decision": (
            "JIT_REAL_NATIVE_CHOICE_CONFIRMED"
            if mechanism_pass
            else "JIT_CHOICE_NOT_YET_CONFIRMED"
        ),
        "comparisons": comparisons,
    }
    _write_outputs(analysis, results, root=root)
    return analysis


def _write_outputs(
    analysis: Mapping[str, Any],
    results: Mapping[tuple[int | None, int, str], Mapping[str, Any]],
    *,
    root: Path,
) -> None:
    table_path = root / DEFAULT_TABLE.relative_to(ROOT)
    table_path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "prefix_segments", "scale", "variant_id", "status",
        "mean_tth_seconds", "p50_tth_seconds", "p95_tth_seconds", "p99_tth_seconds",
        "max_tth_seconds",
        "source_wait_mean_seconds", "network_time_mean_seconds",
        "merge_grant_wait_mean_seconds",
        "event_count", "events_per_completed_segment",
        "merge_grant_service_opportunity_count",
        "merge_grant_multi_candidate_opportunity_count",
        "merge_grant_true_competition_count", "merge_grant_order_mutation_count",
        "merge_grant_peak_pending_requests", "merge_grant_wakeup_scheduled_count",
        "merge_grant_wakeup_coalesced_count", "merge_grant_stale_wakeup_count",
        "hard_safety_pass", "wall_seconds", "cpu_seconds",
    ]
    temporary = table_path.with_name(f".{table_path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for (prefix, scale, variant_id), result in sorted(results.items(), key=str):
            metrics = result.get("metrics", {})
            counters = result.get("counters", {})
            resources = result.get("resources", {})
            writer.writerow(
                {
                    "prefix_segments": prefix,
                    "scale": scale,
                    "variant_id": variant_id,
                    "status": result.get("status"),
                    **{name: metrics.get(name) for name in fields if name in metrics},
                    **{name: counters.get(name) for name in fields if name in counters},
                    "hard_safety_pass": result.get("hard_safety", {}).get("pass"),
                    "wall_seconds": resources.get("wall_seconds"),
                    "cpu_seconds": resources.get("cpu_seconds"),
                }
            )
    os.replace(temporary, table_path)

    comparisons = list(analysis.get("comparisons", []))
    mechanism_rows = [
        "# G4IRSF18 bounded-pending JIT mechanism",
        "",
        f"Decision: **`{analysis.get('mechanism_decision')}`**.",
        "",
        "A true opportunity requires at least two still-valid local requests at the natural service boundary. A proposal or a request-time score does not count.",
        "",
        "| Scope | Candidate | Multi-candidate | True competition | Order mutations | Choice seam |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in comparisons:
        scope = f"{row['prefix_segments']} segments" if row["prefix_segments"] else f"{row['scale']}x full"
        mechanism_rows.append(
            f"| {scope} | {row['candidate']} | {row['multi_candidate_opportunity_count']} | {row['true_competition_count']} | {row['order_mutation_count']} | {row['real_choice_seam_pass'] and row['action_mutation_pass']} |"
        )
    _atomic_text(root / DEFAULT_MECHANISM_REPORT.relative_to(ROOT), "\n".join(mechanism_rows) + "\n")

    event_rows = [
        "# G4IRSF18 event amplification",
        "",
        "This table keeps event work separate from simulated business time. Negative event delta means fewer native events per completed segment than the matched eager arm.",
        "",
        "| Scope | Candidate | Events/segment delta | TTH mean delta (s) | Source wait delta (s) | Merge wait delta (s) | Network delta (s) |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in comparisons:
        scope = f"{row['prefix_segments']} segments" if row["prefix_segments"] else f"{row['scale']}x full"
        perf = row["performance"]
        event_rows.append(
            f"| {scope} | {row['candidate']} | {row['events_per_segment_delta']} | {perf['mean_tth_delta_seconds']} | {perf['source_wait_delta_mean_seconds']} | {perf['merge_grant_wait_delta_mean_seconds']} | {perf['network_time_delta_mean_seconds']} |"
        )
    _atomic_text(root / DEFAULT_EVENT_REPORT.relative_to(ROOT), "\n".join(event_rows) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--root", type=Path, default=ROOT)
    plan.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    plan.add_argument("--prefixes", nargs="+", type=int, default=[144, 512, 2_048, 8_192])
    plan.add_argument("--full-scales", nargs="*", type=int, default=[])
    run = sub.add_parser("run")
    run.add_argument("--root", type=Path, default=ROOT)
    run.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    run.add_argument("--force", action="store_true")
    analyse = sub.add_parser("analyse")
    analyse.add_argument("--root", type=Path, default=ROOT)
    analyse.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    analyse.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    analyse.add_argument("--output", type=Path, default=DEFAULT_ANALYSIS)
    all_parser = sub.add_parser("all")
    all_parser.add_argument("--root", type=Path, default=ROOT)
    all_parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    all_parser.add_argument("--binary", type=Path, required=True)
    all_parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    all_parser.add_argument("--output", type=Path, default=DEFAULT_ANALYSIS)
    all_parser.add_argument("--prefixes", nargs="+", type=int, default=[144, 512, 2_048, 8_192])
    all_parser.add_argument("--full-scales", nargs="*", type=int, default=[])
    all_parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = args.root.resolve()
    try:
        if args.command in {"plan", "all"}:
            plan_value = build_plan(prefixes=args.prefixes, full_scales=args.full_scales)
            plan_path = _resolve(root, args.output if args.command == "plan" else args.plan)
            _atomic_json(plan_path, plan_value)
        else:
            plan_path = _resolve(root, args.plan)
            plan_value = validate_plan(_read_json(plan_path))

        run_value = None
        if args.command in {"run", "all"}:
            run_value = run_plan(
                plan_value,
                binary=_resolve(root, args.binary),
                results_dir=_resolve(root, args.results_dir),
                root=root,
                force=args.force,
            )

        analysis = None
        if args.command in {"analyse", "all"}:
            analysis = analyse_plan(
                plan_value,
                results_dir=_resolve(root, args.results_dir),
                root=root,
            )
            _atomic_json(_resolve(root, args.output), analysis)

        print(json.dumps({
            "plan": _relative(plan_path, root),
            "run_complete": run_value.get("complete") if run_value else None,
            "analysis_status": analysis.get("status") if analysis else None,
            "mechanism_decision": analysis.get("mechanism_decision") if analysis else None,
        }, sort_keys=True))
        if run_value is not None and not run_value["complete"]:
            return 2
        if analysis is not None and analysis["status"] != "COMPLETE":
            return 2
        return 0
    except (G18JitCampaignError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G18 JIT campaign failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
