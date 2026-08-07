#!/usr/bin/env python3
"""Process-isolated paired rollout throughput benchmark for G4IRSF19.

Each immutable job runs the same G18 ladder prefix twice in one worker process:
J2/S1 is the baseline and J2/S2 is the treatment.  Worker count changes only
concurrency; it never changes the plan or the paired workload.

This is a replica-throughput and determinism benchmark.  Repeating one fixed
workload does not create independent learning support or justify promotion of
either scorer.
"""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ProcessPoolExecutor, as_completed
import csv
import io
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


SCHEMA_PLAN = "czr005.g4irsf19.rollout_farm_plan.v1"
SCHEMA_JOB_RESULT = "czr005.g4irsf19.rollout_pair_job_result.v1"
SCHEMA_RUN = "czr005.g4irsf19.rollout_farm_run.v1"
SCHEMA_BENCHMARK = "czr005.g4irsf19.rollout_parallelism.v1"

DEFAULT_PLAN = ROOT / "artifacts/manifests/g4irsf19_rollout_farm_plan.json"
DEFAULT_RUNSTATE = ROOT / "outputs/runstate/g4irsf19_rollout_farm"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf19_rollout_parallelism.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf19_rollout_parallelism.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf19_rollout_parallelism.md"

DEFAULT_WORKERS = (1, 2, 4, 8)
DEFAULT_PREFIX_SEGMENTS = 2_048
DEFAULT_REPLICA_COUNT = 8
ALLOWED_PREFIXES = (144, 512, 2_048, 8_192, 43_603)

J2_TIMING_MODE = "jit_fair_aging_deadline"
J2_MERGE_RULE = "M3"
S1_MODE = "S1_frozen_g4e_legal_local_adapter"
S2_MODE = "S2_frozen_g4e_without_absolute_node_ids"

TERMINAL_NATIVE_STATUSES = {
    "COMPLETE",
    "CAPACITY_CENSORED_EVENT_LIMIT",
    "CAPACITY_CENSORED_SIMULATION_TIME",
}

Worker = Callable[[Mapping[str, Any], str, str, str, int], Mapping[str, Any]]


class RolloutFarmError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RolloutFarmError(message)


def _resolve(root: Path, path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else root / value


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_json(path: Path, value: Any) -> None:
    _atomic_bytes(path, _json_bytes(value))


def _atomic_text(path: Path, value: str) -> None:
    _atomic_bytes(path, value.encode("utf-8"))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RolloutFarmError(f"cannot read JSON {path}: {exc}") from exc
    _require(isinstance(value, dict), f"JSON root is not an object: {path}")
    return value


def _arm(arm_id: str, scorer_mode: str) -> dict[str, Any]:
    return {
        "arm_id": arm_id,
        "timing_mode": J2_TIMING_MODE,
        "merge_rule": J2_MERGE_RULE,
        "learned": False,
        "native_controls": {"scorer_mode": scorer_mode},
        "research_closed_loop_authorized": False,
        "production_closed_loop_authorized": False,
    }


def _system_job(
    *, replica_index: int, prefix_segments: int, side: str, arm_id: str
) -> dict[str, Any]:
    return {
        "job_id": (
            f"g19_replica_{replica_index:03d}__{side.lower()}__"
            f"s{prefix_segments}"
        ),
        "stage": "ladder",
        "arm_id": arm_id,
        "prefix_segments": prefix_segments,
        "scale": 1,
        "max_segments": -1,
        "fault_scenario": None,
        # Reuse the frozen G18 ladder contract exactly. Candidate rows are
        # discarded before per-job persistence; only their summary counters
        # survive in the rollout-farm output.
        "telemetry_mode": (
            "evidence_trace" if prefix_segments <= 8_192 else "capacity"
        ),
    }


def build_plan(
    *,
    replica_count: int = DEFAULT_REPLICA_COUNT,
    prefix_segments: int = DEFAULT_PREFIX_SEGMENTS,
) -> dict[str, Any]:
    _require(
        isinstance(replica_count, int)
        and not isinstance(replica_count, bool)
        and replica_count > 0,
        "replica_count must be a positive integer",
    )
    _require(prefix_segments in ALLOWED_PREFIXES, "unsupported G18 ladder prefix")
    baseline_arm = _arm("G19_J2_S1_BASELINE", S1_MODE)
    treatment_arm = _arm("G19_J2_S2_TREATMENT", S2_MODE)
    jobs: list[dict[str, Any]] = []
    for index in range(replica_count):
        jobs.append(
            {
                "plan_index": index,
                "job_id": f"g19_pair_replica_{index:03d}__s{prefix_segments}",
                "replica_id": f"replica_{index:03d}",
                "prefix_segments": prefix_segments,
                "baseline": {
                    "label": "J2/S1",
                    "job": _system_job(
                        replica_index=index,
                        prefix_segments=prefix_segments,
                        side="baseline",
                        arm_id=str(baseline_arm["arm_id"]),
                    ),
                    "arm": dict(baseline_arm),
                },
                "treatment": {
                    "label": "J2/S2",
                    "job": _system_job(
                        replica_index=index,
                        prefix_segments=prefix_segments,
                        side="treatment",
                        arm_id=str(treatment_arm["arm_id"]),
                    ),
                    "arm": dict(treatment_arm),
                },
            }
        )
    return {
        "schema": SCHEMA_PLAN,
        "status": "FIXED_REPLICA_BENCHMARK_PLAN",
        "design": {
            "pair_order": ["J2/S1", "J2/S2"],
            "same_g18_ladder_prefix_within_pair": True,
            "worker_count_does_not_change_jobs": True,
            "one_fresh_process_per_pair_job": True,
            "replicas_are_identical_workload_repeats": True,
            "independent_learning_support_claimed": False,
        },
        "claim_boundary": (
            "Replica throughput and deterministic execution benchmark only; "
            "identical replicas are not independent learning support."
        ),
        "prefix_segments": prefix_segments,
        "replica_count": replica_count,
        "jobs": jobs,
    }


def _parse_arm(value: Mapping[str, Any]) -> Any:
    from scripts.eval import run_g4irsf18_system_campaign as g18

    controls = value.get("native_controls")
    _require(isinstance(controls, Mapping), "arm.native_controls is missing")
    return g18.Arm(
        arm_id=str(value["arm_id"]),
        timing_mode=str(value["timing_mode"]),
        merge_rule=str(value["merge_rule"]),
        learned=bool(value.get("learned", False)),
        native_controls=dict(controls),
        research_closed_loop_authorized=bool(
            value.get("research_closed_loop_authorized", False)
        ),
        production_closed_loop_authorized=bool(
            value.get("production_closed_loop_authorized", False)
        ),
    )


def validate_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    from scripts.eval import run_g4irsf18_system_campaign as g18

    _require(value.get("schema") == SCHEMA_PLAN, "rollout farm plan schema mismatch")
    prefix = value.get("prefix_segments")
    _require(type(prefix) is int and prefix in ALLOWED_PREFIXES, "bad plan prefix")
    jobs = value.get("jobs")
    _require(isinstance(jobs, list) and jobs, "plan has no pair jobs")
    _require(
        value.get("replica_count") == len(jobs),
        "replica_count does not match pair jobs",
    )
    ids: list[str] = []
    for expected_index, raw in enumerate(jobs):
        _require(isinstance(raw, Mapping), "pair job is not an object")
        _require(raw.get("plan_index") == expected_index, "plan_index is not contiguous")
        job_id = raw.get("job_id")
        _require(isinstance(job_id, str) and job_id, "pair job_id is missing")
        ids.append(job_id)
        _require(raw.get("prefix_segments") == prefix, "pair prefix drift")
        for side, expected_label, expected_scorer in (
            ("baseline", "J2/S1", S1_MODE),
            ("treatment", "J2/S2", S2_MODE),
        ):
            branch = raw.get(side)
            _require(isinstance(branch, Mapping), f"{side} branch is missing")
            _require(branch.get("label") == expected_label, f"{side} label drift")
            job_value = branch.get("job")
            arm_value = branch.get("arm")
            _require(isinstance(job_value, Mapping), f"{side} job is missing")
            _require(isinstance(arm_value, Mapping), f"{side} arm is missing")
            native_job = g18.SystemJob.from_mapping(job_value)
            arm = _parse_arm(arm_value)
            _require(native_job.prefix_segments == prefix, f"{side} prefix drift")
            _require(native_job.arm_id == arm.arm_id, f"{side} arm identity drift")
            _require(
                arm.timing_mode == J2_TIMING_MODE and arm.merge_rule == J2_MERGE_RULE,
                f"{side} is not J2",
            )
            _require(
                dict(arm.native_controls or {}).get("scorer_mode")
                == expected_scorer,
                f"{side} scorer drift",
            )
    _require(len(ids) == len(set(ids)), "duplicate pair job_id")
    return dict(value)


def _omit_candidate_rows(result: Mapping[str, Any]) -> dict[str, Any]:
    compact = dict(result)
    rows = compact.pop("_opportunity_rows", None)
    if isinstance(rows, list):
        compact["opportunity_rows_omitted_count"] = len(rows)
    return compact


def _current_rss_mb() -> float | None:
    try:
        import psutil  # type: ignore[import-not-found]

        return psutil.Process(os.getpid()).memory_info().rss / (1024.0 * 1024.0)
    except (ImportError, OSError):
        pass
    try:
        import resource

        value = float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        if sys.platform == "darwin":
            return value / (1024.0 * 1024.0)
        return value / 1024.0
    except (ImportError, OSError, ValueError):
        return None


def _pair_record(
    raw_job: Mapping[str, Any],
    baseline: Mapping[str, Any],
    treatment: Mapping[str, Any],
    *,
    attempt: int,
    wall_seconds: float,
    cpu_seconds: float,
) -> dict[str, Any]:
    baseline_status = str(baseline.get("status", ""))
    treatment_status = str(treatment.get("status", ""))
    return {
        "schema": SCHEMA_JOB_RESULT,
        "status": "COMPLETE",
        "pair_job": dict(raw_job),
        "native_pair_complete": (
            baseline_status == "COMPLETE" and treatment_status == "COMPLETE"
        ),
        "native_pair_terminal": (
            baseline_status in TERMINAL_NATIVE_STATUSES
            and treatment_status in TERMINAL_NATIVE_STATUSES
        ),
        "baseline": _omit_candidate_rows(baseline),
        "treatment": _omit_candidate_rows(treatment),
        "resources": {
            "attempt": attempt,
            "worker_pid": os.getpid(),
            "worker_wall_seconds": wall_seconds,
            "worker_cpu_seconds": cpu_seconds,
            "worker_rss_mb": _current_rss_mb(),
        },
    }


def _execute_pair_job(
    raw_job: Mapping[str, Any],
    binary_text: str,
    root_text: str,
    output_text: str,
    attempt: int,
) -> Mapping[str, Any]:
    """Production worker entrypoint.  It is top-level so spawn can pickle it."""

    from scripts.eval import run_g4irsf18_system_campaign as g18

    root = Path(root_text)
    binary = Path(binary_text)
    output = Path(output_text)
    baseline_spec = raw_job["baseline"]
    treatment_spec = raw_job["treatment"]
    _require(isinstance(baseline_spec, Mapping), "baseline spec is invalid")
    _require(isinstance(treatment_spec, Mapping), "treatment spec is invalid")
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    baseline = g18.execute_job(
        g18.SystemJob.from_mapping(baseline_spec["job"]),
        _parse_arm(baseline_spec["arm"]),
        binary=binary,
        root=root,
    )
    treatment = g18.execute_job(
        g18.SystemJob.from_mapping(treatment_spec["job"]),
        _parse_arm(treatment_spec["arm"]),
        binary=binary,
        root=root,
    )
    record = _pair_record(
        raw_job,
        baseline,
        treatment,
        attempt=attempt,
        wall_seconds=time.perf_counter() - wall_start,
        cpu_seconds=time.process_time() - cpu_start,
    )
    _atomic_json(output, record)
    return {
        "job_id": raw_job["job_id"],
        "plan_index": raw_job["plan_index"],
        "status": "COMPLETE",
        "attempt": attempt,
    }


def _fixture_execute_pair_job(
    raw_job: Mapping[str, Any],
    binary_text: str,
    root_text: str,
    output_text: str,
    attempt: int,
) -> Mapping[str, Any]:
    """Small deterministic process worker used by unit tests; no native pyd."""

    del binary_text, root_text
    if raw_job.get("_fixture_fail_always") is True:
        raise RuntimeError("fixture persistent failure")
    if raw_job.get("_fixture_fail_first") is True and attempt == 1:
        raise RuntimeError("fixture first-attempt failure")
    delay = float(raw_job.get("_fixture_delay_seconds", 0.0))
    if delay > 0.0:
        time.sleep(delay)

    def branch(side: str) -> dict[str, Any]:
        spec = raw_job[side]
        return {
            "schema": "fixture.g18.result.v1",
            "job": dict(spec["job"]),
            "arm": dict(spec["arm"]),
            "status": "COMPLETE",
            "input": {
                "segments": raw_job["prefix_segments"],
                "topology_changed": False,
            },
            "metrics": {
                "requested_segments": raw_job["prefix_segments"],
                "complete_raw_bag_count": raw_job["prefix_segments"],
                "mean_tth_seconds": 100.0 if side == "baseline" else 99.0,
            },
            "counters": {"unsafe_entry_count": 0, "event_count": 1_000},
            "resources": {
                "wall_seconds": delay,
                "cpu_seconds": 0.0,
                "fixture_pid": os.getpid(),
            },
        }

    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    baseline = branch("baseline")
    treatment = branch("treatment")
    record = _pair_record(
        raw_job,
        baseline,
        treatment,
        attempt=attempt,
        wall_seconds=time.perf_counter() - wall_start + delay,
        cpu_seconds=time.process_time() - cpu_start,
    )
    _atomic_json(Path(output_text), record)
    return {
        "job_id": raw_job["job_id"],
        "plan_index": raw_job["plan_index"],
        "status": "COMPLETE",
        "attempt": attempt,
    }


def _result_path(run_directory: Path, raw_job: Mapping[str, Any]) -> Path:
    return run_directory / "jobs" / f"{raw_job['job_id']}.json"


def _result_is_resumable(path: Path, raw_job: Mapping[str, Any]) -> bool:
    if not path.is_file():
        return False
    try:
        value = _read_json(path)
    except RolloutFarmError:
        return False
    return (
        value.get("schema") == SCHEMA_JOB_RESULT
        and value.get("status") == "COMPLETE"
        and value.get("pair_job") == dict(raw_job)
        and isinstance(value.get("baseline"), Mapping)
        and isinstance(value.get("treatment"), Mapping)
    )


def _semantic_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _semantic_value(item)
            for key, item in sorted(value.items(), key=lambda row: str(row[0]))
            if key != "resources"
        }
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    return value


def semantic_job_result(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "pair_job": _semantic_value(value["pair_job"]),
        "native_pair_complete": value.get("native_pair_complete"),
        "native_pair_terminal": value.get("native_pair_terminal"),
        "baseline": _semantic_value(value["baseline"]),
        "treatment": _semantic_value(value["treatment"]),
    }


def _finite_sum(values: Sequence[Any]) -> float:
    total = 0.0
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            if math.isfinite(number):
                total += number
    return total


def _finite_max(values: Sequence[Any]) -> float | None:
    numbers = [
        float(value)
        for value in values
        if isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ]
    return max(numbers) if numbers else None


def run_configuration(
    plan: Mapping[str, Any],
    *,
    workers: int,
    repeat: int,
    binary: Path,
    root: Path,
    runstate_root: Path,
    force: bool = False,
    worker: Worker = _execute_pair_job,
) -> dict[str, Any]:
    validated = validate_plan(plan)
    _require(type(workers) is int and workers > 0, "workers must be positive")
    _require(type(repeat) is int and repeat > 0, "repeat must be positive")
    jobs = [dict(row) for row in validated["jobs"]]
    run_directory = runstate_root / f"p{workers}" / f"r{repeat}"
    run_directory.mkdir(parents=True, exist_ok=True)
    attempts = {str(job["job_id"]): 0 for job in jobs}
    resumed: list[str] = []
    pending: list[dict[str, Any]] = []
    for job in jobs:
        path = _result_path(run_directory, job)
        if not force and _result_is_resumable(path, job):
            resumed.append(str(job["job_id"]))
        else:
            pending.append(job)

    failures: dict[str, str] = {}
    wall_start = time.perf_counter()
    if pending:
        effective_workers = min(workers, len(pending))
        with ProcessPoolExecutor(
            max_workers=effective_workers,
            max_tasks_per_child=1,
        ) as pool:
            active: dict[Future[Mapping[str, Any]], dict[str, Any]] = {}

            def submit(job: dict[str, Any]) -> None:
                job_id = str(job["job_id"])
                attempts[job_id] += 1
                active[
                    pool.submit(
                        worker,
                        job,
                        str(binary),
                        str(root),
                        str(_result_path(run_directory, job)),
                        attempts[job_id],
                    )
                ] = job

            for job in pending:
                submit(job)
            while active:
                future = next(as_completed(tuple(active)))
                job = active.pop(future)
                job_id = str(job["job_id"])
                try:
                    future.result()
                    if not _result_is_resumable(
                        _result_path(run_directory, job), job
                    ):
                        raise RolloutFarmError(
                            "worker returned without a complete atomic result"
                        )
                except Exception as exc:
                    if attempts[job_id] < 2:
                        submit(job)
                    else:
                        failures[job_id] = f"{type(exc).__name__}: {exc}"
                        _atomic_json(
                            _result_path(run_directory, job),
                            {
                                "schema": SCHEMA_JOB_RESULT,
                                "status": "FAILED",
                                "pair_job": job,
                                "attempts": attempts[job_id],
                                "error": failures[job_id],
                            },
                        )
    wall_seconds = time.perf_counter() - wall_start

    merge_start = time.perf_counter()
    ordered_results: list[dict[str, Any]] = []
    missing: list[str] = []
    output_bytes = 0
    for job in jobs:
        path = _result_path(run_directory, job)
        if not _result_is_resumable(path, job):
            missing.append(str(job["job_id"]))
            continue
        output_bytes += path.stat().st_size
        ordered_results.append(_read_json(path))
    merge_seconds = time.perf_counter() - merge_start

    resources = [
        row.get("resources", {})
        for row in ordered_results
        if isinstance(row.get("resources"), Mapping)
    ]
    cpu_seconds = _finite_sum(
        [row.get("worker_cpu_seconds") for row in resources]
    )
    max_rss = _finite_max([row.get("worker_rss_mb") for row in resources])
    prefix = int(validated["prefix_segments"])
    pair_segment_replicas = 2 * prefix * len(ordered_results)
    effective_worker_count = min(workers, max(1, len(jobs)))
    retry_count = sum(max(0, value - 1) for value in attempts.values())
    failed_job_ids = sorted(set(failures) | set(missing))
    fresh_full_plan = (
        not resumed
        and not failed_job_ids
        and retry_count == 0
        and len(ordered_results) == len(jobs)
    )
    summary = {
        "schema": SCHEMA_RUN,
        "status": "COMPLETE" if not missing and not failures else "INCOMPLETE",
        "workers": workers,
        "effective_workers": effective_worker_count,
        "repeat": repeat,
        "planned_job_count": len(jobs),
        "completed_job_count": len(ordered_results),
        "native_pair_complete_count": sum(
            row.get("native_pair_complete") is True for row in ordered_results
        ),
        "scheduled_job_count": len(pending),
        "resumed_job_count": len(resumed),
        "resumed_job_ids": resumed,
        "retry_count": retry_count,
        "failure_count": len(failed_job_ids),
        "failed_job_ids": failed_job_ids,
        "ordered_job_ids": [str(row["job_id"]) for row in jobs],
        "fresh_full_plan_timing": fresh_full_plan,
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "cpu_utilization": (
            cpu_seconds / (wall_seconds * effective_worker_count)
            if wall_seconds > 0.0
            else None
        ),
        "max_worker_rss_mb": max_rss,
        "io_write_bytes": output_bytes,
        "merge_seconds": merge_seconds,
        "pair_segment_replicas": pair_segment_replicas,
        "groups_per_hour": (
            len(ordered_results) * 3_600.0 / wall_seconds
            if fresh_full_plan and wall_seconds > 0.0
            else None
        ),
        "segments_per_hour": (
            pair_segment_replicas * 3_600.0 / wall_seconds
            if fresh_full_plan and wall_seconds > 0.0
            else None
        ),
    }
    _atomic_json(run_directory / "configuration.json", summary)
    return {
        "summary": summary,
        "semantic_by_job": {
            str(row["pair_job"]["job_id"]): semantic_job_result(row)
            for row in ordered_results
        },
        "job_results": ordered_results,
    }


CSV_FIELDS = (
    "workers",
    "effective_workers",
    "repeat",
    "planned_job_count",
    "completed_job_count",
    "native_pair_complete_count",
    "scheduled_job_count",
    "resumed_job_count",
    "retry_count",
    "failure_count",
    "fresh_full_plan_timing",
    "wall_seconds",
    "cpu_seconds",
    "cpu_utilization",
    "groups_per_hour",
    "segments_per_hour",
    "pair_segment_replicas",
    "speedup_vs_p1",
    "efficiency",
    "max_worker_rss_mb",
    "io_write_bytes",
    "merge_seconds",
    "semantic_equal_to_p1",
)


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({name: row.get(name) for name in CSV_FIELDS})
    return output.getvalue()


def _number(value: Any, digits: int = 3) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "-"
    number = float(value)
    return f"{number:.{digits}f}" if math.isfinite(number) else "-"


def render_report(benchmark: Mapping[str, Any]) -> str:
    lines = [
        "# G4IRSF19 process-isolated paired rollout farm",
        "",
        f"Status: **`{benchmark['status']}`**.",
        "",
        "This benchmark runs each fixed pair in one fresh process: J2/S1 first,",
        "then J2/S2 on the same G18 ladder prefix. P changes concurrency only.",
        "",
        "| P | Repeat | Jobs | Wall s | Speedup | Efficiency | Groups/hour | "
        "Semantic = P1 | Retries | Failures |",
        "|---:|---:|---:|---:|---:|---:|---:|:---:|---:|---:|",
    ]
    for row in benchmark["runs"]:
        lines.append(
            f"| {row['workers']} | {row['repeat']} | "
            f"{row['completed_job_count']} | {_number(row.get('wall_seconds'))} | "
            f"{_number(row.get('speedup_vs_p1'))} | "
            f"{_number(row.get('efficiency'))} | "
            f"{_number(row.get('groups_per_hour'), 1)} | "
            f"{'yes' if row.get('semantic_equal_to_p1') else 'no'} | "
            f"{row['retry_count']} | {row['failure_count']} |"
        )
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            "- This proves only process-isolated replica throughput and output determinism.",
            "- The replicas repeat one fixed workload; they are not independent learning support.",
            "- S1/S2 resources are excluded before semantic equality is evaluated.",
            "- No production policy promotion is implied.",
            "",
        ]
    )
    return "\n".join(lines)


def benchmark_plan(
    plan: Mapping[str, Any],
    *,
    binary: Path,
    root: Path,
    workers: Sequence[int] = DEFAULT_WORKERS,
    repeats: int = 1,
    runstate_root: Path = DEFAULT_RUNSTATE,
    json_output: Path | None = DEFAULT_JSON,
    csv_output: Path | None = DEFAULT_CSV,
    report_output: Path | None = DEFAULT_REPORT,
    force: bool = False,
    worker: Worker = _execute_pair_job,
) -> dict[str, Any]:
    validated = validate_plan(plan)
    normalized_workers = tuple(sorted(set(int(value) for value in workers)))
    _require(normalized_workers and all(value > 0 for value in normalized_workers), "bad workers")
    _require(1 in normalized_workers, "P=1 is required as the semantic and speed baseline")
    _require(type(repeats) is int and repeats > 0, "repeats must be positive")
    configurations: list[dict[str, Any]] = []
    for repeat in range(1, repeats + 1):
        for count in normalized_workers:
            configurations.append(
                run_configuration(
                    validated,
                    workers=count,
                    repeat=repeat,
                    binary=binary,
                    root=root,
                    runstate_root=runstate_root,
                    force=force,
                    worker=worker,
                )
            )

    reference = next(
        row["semantic_by_job"]
        for row in configurations
        if row["summary"]["workers"] == 1 and row["summary"]["repeat"] == 1
    )
    p1_wall = {
        row["summary"]["repeat"]: row["summary"]["wall_seconds"]
        for row in configurations
        if row["summary"]["workers"] == 1
        and row["summary"]["fresh_full_plan_timing"] is True
    }
    rows: list[dict[str, Any]] = []
    for configuration in configurations:
        summary = dict(configuration["summary"])
        semantics = configuration["semantic_by_job"]
        mismatch = sorted(
            set(reference) ^ set(semantics)
            | {
                job_id
                for job_id in set(reference) & set(semantics)
                if reference[job_id] != semantics[job_id]
            }
        )
        baseline_wall = p1_wall.get(int(summary["repeat"]))
        speedup = (
            baseline_wall / float(summary["wall_seconds"])
            if baseline_wall is not None
            and summary["fresh_full_plan_timing"] is True
            and float(summary["wall_seconds"]) > 0.0
            else None
        )
        summary.update(
            semantic_equal_to_p1=not mismatch,
            semantic_mismatch_job_ids=mismatch,
            speedup_vs_p1=speedup,
            efficiency=(
                speedup / int(summary["workers"])
                if speedup is not None
                else None
            ),
        )
        rows.append(summary)
    benchmark = {
        "schema": SCHEMA_BENCHMARK,
        "status": (
            "COMPLETE_DETERMINISTIC"
            if all(
                row["failure_count"] == 0
                and row["native_pair_complete_count"] == row["planned_job_count"]
                and row["semantic_equal_to_p1"]
                for row in rows
            )
            else "INCOMPLETE_OR_NONDETERMINISTIC"
        ),
        "plan_status": validated["status"],
        "prefix_segments": validated["prefix_segments"],
        "replica_count": validated["replica_count"],
        "worker_counts": list(normalized_workers),
        "repeat_count": repeats,
        "independent_learning_support_claimed": False,
        "claim_boundary": validated["claim_boundary"],
        "runs": rows,
    }
    if json_output is not None:
        _atomic_json(json_output, benchmark)
    if csv_output is not None:
        _atomic_text(csv_output, _csv_text(rows))
    if report_output is not None:
        _atomic_text(report_output, render_report(benchmark))
    return benchmark


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="write the fixed paired replica plan")
    plan.add_argument("--root", type=Path, default=ROOT)
    plan.add_argument("--output", type=Path, default=DEFAULT_PLAN)
    plan.add_argument("--replicas", type=_positive_int, default=DEFAULT_REPLICA_COUNT)
    plan.add_argument(
        "--prefix-segments",
        type=int,
        choices=ALLOWED_PREFIXES,
        default=DEFAULT_PREFIX_SEGMENTS,
    )
    plan.add_argument("--force", action="store_true")

    benchmark = subparsers.add_parser(
        "benchmark", help="run P=1/2/4/8 on the unchanged pair jobs"
    )
    benchmark.add_argument("--root", type=Path, default=ROOT)
    benchmark.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    benchmark.add_argument("--binary", type=Path, required=True)
    benchmark.add_argument(
        "--workers",
        type=_positive_int,
        nargs="+",
        default=list(DEFAULT_WORKERS),
    )
    benchmark.add_argument("--repeats", type=_positive_int, default=1)
    benchmark.add_argument("--runstate-root", type=Path, default=DEFAULT_RUNSTATE)
    benchmark.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    benchmark.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    benchmark.add_argument("--report-output", type=Path, default=DEFAULT_REPORT)
    benchmark.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    root = arguments.root.resolve()
    if arguments.command == "plan":
        output = _resolve(root, arguments.output)
        if output.exists() and not arguments.force:
            existing = validate_plan(_read_json(output))
            print(
                json.dumps(
                    {
                        "status": "REUSED",
                        "path": str(output),
                        "jobs": len(existing["jobs"]),
                    },
                    indent=2,
                )
            )
            return 0
        value = build_plan(
            replica_count=arguments.replicas,
            prefix_segments=arguments.prefix_segments,
        )
        _atomic_json(output, value)
        print(
            json.dumps(
                {
                    "status": value["status"],
                    "path": str(output),
                    "jobs": len(value["jobs"]),
                    "independent_learning_support_claimed": False,
                },
                indent=2,
            )
        )
        return 0

    plan_path = _resolve(root, arguments.plan)
    binary = _resolve(root, arguments.binary).resolve(strict=True)
    result = benchmark_plan(
        _read_json(plan_path),
        binary=binary,
        root=root,
        workers=arguments.workers,
        repeats=arguments.repeats,
        runstate_root=_resolve(root, arguments.runstate_root),
        json_output=_resolve(root, arguments.json_output),
        csv_output=_resolve(root, arguments.csv_output),
        report_output=_resolve(root, arguments.report_output),
        force=arguments.force,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "worker_counts": result["worker_counts"],
                "repeat_count": result["repeat_count"],
                "independent_learning_support_claimed": False,
            },
            indent=2,
        )
    )
    return 0 if result["status"] == "COMPLETE_DETERMINISTIC" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutFarmError as exc:
        print(f"G4IRSF19_ROLLOUT_FARM_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
