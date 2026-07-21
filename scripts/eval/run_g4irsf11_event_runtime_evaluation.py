"""Execute the frozen G4IRSF11 event-runtime protocol case by case.

Each case runs in a fresh process so peak working set is an OS measurement.
Raw full traces and generated workloads stay in ``.pytest_cache``; only compact
tables, reports, schemas and balanced samples are repository artifacts.
"""

from __future__ import annotations

import argparse
import atexit
import gc
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from czr005.datasets.decision_trace import SamplingConfig
from scripts.eval.g4irsf11_evaluation_reporting import (
    case_row,
    gate_rows,
    sha256_file,
    write_claim_boundary,
    write_csv,
    write_reports,
)
from scripts.eval.g4irsf11_experiment_protocol import (
    CAPACITY_SLO,
    FAULT_SLO,
    PROTOCOL_VERSION,
    CaseSpec,
    fault_windows,
    formal_cases,
    protocol_manifest,
)
from scripts.eval.g4irsf11_workloads import (
    build_workload,
    load_jsonl,
    namespace_workload,
    write_jsonl,
)
from scripts.eval.run_g4irsf11_decision_trace_sampling import write_artifacts


MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
SOURCE_TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
RUNTIME_ROOT = ROOT / ".pytest_cache" / "g4irsf11" / "event_evaluation"
WORKLOAD_DIR = RUNTIME_ROOT / "workloads"
RESULT_DIR = RUNTIME_ROOT / "results"
TRACE_DIR = RUNTIME_ROOT / "traces"
EXECUTION_DIR = RUNTIME_ROOT / "executions"
FAULT_DIR = RUNTIME_ROOT / "faults"
PROTOCOL_PATH = ROOT / "artifacts" / "gates" / "g4irsf11_event_runtime_protocol.json"
CASE_TABLE = ROOT / "outputs" / "tables" / "g4irsf11_event_runtime_case_ledger.csv"

IMPLEMENTATION_FILES = (
    ROOT / "cpp" / "ics_core" / "runtime" / "event_driven_junction.hpp",
    ROOT / "cpp" / "ics_core" / "bindings" / "czr005_cpp.cpp",
    ROOT / "src" / "czr005" / "cpp_backend.py",
    ROOT / "scripts" / "eval" / "g4irsf11_workloads.py",
    ROOT / "scripts" / "eval" / "g4irsf11_capacity_metrics.py",
    ROOT / "scripts" / "eval" / "g4irsf11_fault_metrics.py",
    ROOT / "scripts" / "eval" / "run_g4irsf11_event_case.py",
)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256_rows(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(
            json.dumps(dict(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        digest.update(b"\n")
    return digest.hexdigest()


def implementation_sha256(search_path: Path) -> str:
    candidates = list(IMPLEMENTATION_FILES)
    binaries = sorted(search_path.glob("czr005_cpp*.pyd")) + sorted(
        search_path.glob("czr005_cpp*.so")
    )
    if len(binaries) != 1:
        raise ValueError(
            f"expected exactly one built czr005_cpp module in {search_path}, got {binaries}"
        )
    candidates.extend(binaries)
    missing = [path for path in candidates if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"implementation evidence missing: {missing}")
    digest = hashlib.sha256()
    for path in candidates:
        digest.update(str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def timeline_spanning_sample(
    rows: Sequence[Mapping[str, Any]], count: int
) -> list[dict[str, Any]]:
    """Return an exact deterministic sample spanning the entire release order."""

    if count <= 0:
        raise ValueError("sample count must be positive")
    if count > len(rows):
        raise ValueError(f"cannot sample {count} rows from {len(rows)}")
    ordered = sorted(
        rows,
        key=lambda row: (
            float(row["release_time"]),
            str(row["segment_id"]),
            int(row.get("generation_copy_index", 0)),
        ),
    )
    if count == len(ordered):
        return [dict(row) for row in ordered]
    if count == 1:
        return [dict(ordered[len(ordered) // 2])]
    indices = [round(index * (len(ordered) - 1) / (count - 1)) for index in range(count)]
    if len(set(indices)) != count:
        raise AssertionError("systematic sample indices unexpectedly collided")
    return [dict(ordered[index]) for index in indices]


def _case_paths(case: CaseSpec) -> dict[str, Path]:
    return {
        "workload": WORKLOAD_DIR / f"{case.case_id}.jsonl",
        "result": RESULT_DIR / f"{case.case_id}.json",
        "execution": EXECUTION_DIR / f"{case.case_id}.json",
        "fault": FAULT_DIR / f"{case.case_id}.json",
        "trace": TRACE_DIR / f"{case.case_id}.json",
        "outcomes": TRACE_DIR / f"{case.case_id}.outcomes.jsonl",
        "tasks": TRACE_DIR / f"{case.case_id}.tasks.jsonl",
        "history": EXECUTION_DIR / f"{case.case_id}.attempt_history.jsonl",
        "lock": EXECUTION_DIR / f"{case.case_id}.lock",
    }


def _release_case_lock(token: dict[str, Any]) -> None:
    if token.get("released"):
        return
    descriptor = int(token["descriptor"])
    try:
        os.close(descriptor)
    except OSError:
        pass
    Path(token["path"]).unlink(missing_ok=True)
    token["released"] = True


def _acquire_case_lock(path: Path, case_id: str) -> dict[str, Any] | None:
    """Acquire an atomic per-case writer lease, or fail closed.

    A stale lock is intentionally not guessed away.  Operators must first
    prove that no worker owns it, retain the failed attempt, and then remove
    that exact file before retrying.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    payload = json.dumps(
        {"case_id": case_id, "pid": os.getpid(), "acquired_unix_time": time.time()},
        sort_keys=True,
    ).encode("utf-8")
    os.write(descriptor, payload)
    token: dict[str, Any] = {"descriptor": descriptor, "path": path, "released": False}
    atexit.register(_release_case_lock, token)
    return token


def _archive_existing_attempt(case: CaseSpec, paths: Mapping[str, Path]) -> None:
    """Retain compact negative evidence before a requested exact rerun."""

    if not paths["execution"].is_file() or not paths["result"].is_file():
        return
    execution = _read_json(paths["execution"])
    result = _read_json(paths["result"])
    summary = result.get("summary") or {}
    capacity = result.get("raw_bag_capacity_metrics") or {}
    sample_reasons: dict[str, int] = {}
    for row in result.get("bag_sample") or []:
        reason = str(row.get("failure_reason") or "")
        if reason:
            sample_reasons[reason] = sample_reasons.get(reason, 0) + 1
    compact = {
        "case_id": case.case_id,
        "protocol_version": execution.get("protocol_version", ""),
        "execution_status": execution.get("status", ""),
        "return_code": execution.get("return_code", ""),
        "command": execution.get("command", ""),
        "input_sha256": execution.get("input_sha256", ""),
        "requested_count": summary.get("requested_count", ""),
        "completed_count": summary.get("completed_count", ""),
        "failed_count": summary.get("failed_count", ""),
        "completion_pass": result.get("completion_pass", False),
        "safe_execution_pass": capacity.get("safe_execution_pass", False),
        "queue_stability_pass": capacity.get("queue_stability_pass", False),
        "service_level_pass": capacity.get("service_level_pass", False),
        "capacity_pass": capacity.get("capacity_pass", False),
        "runtime_full_astar_calls": summary.get("runtime_full_astar_calls", ""),
        "reservation_conflicts": summary.get("reservation_conflicts", ""),
        "global_reservation_scan_count": summary.get("global_reservation_scan_count", ""),
        "deadlock_count": summary.get("deadlock_count", ""),
        "unresolved_deadlock_count": summary.get("unresolved_deadlock_count", ""),
        "event_limit_reached": summary.get("event_limit_reached", ""),
        "time_limit_reached": summary.get("time_limit_reached", ""),
        "sample_failure_reasons": json.dumps(sample_reasons, sort_keys=True),
        "blocker": execution.get("blocker", ""),
    }
    paths["history"].parent.mkdir(parents=True, exist_ok=True)
    with paths["history"].open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(compact, ensure_ascii=False, sort_keys=True) + "\n")


def _descriptor_matches(
    descriptor: Mapping[str, Any],
    case: CaseSpec,
    *,
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
    protocol_version: str = PROTOCOL_VERSION,
) -> bool:
    return (
        descriptor.get("protocol_version") == protocol_version
        and descriptor.get("case") == case.as_dict()
        and descriptor.get("source_sha256") == source_sha256
        and descriptor.get("map_sha256") == map_sha256
        and descriptor.get("implementation_sha256") == implementation_digest
        and descriptor.get("status") == "EXECUTED"
    )


def _command_text(command: Sequence[str]) -> str:
    return subprocess.list2cmdline(list(command)) if sys.platform == "win32" else shlex.join(command)


def _fault_rows(case: CaseSpec, workload: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    releases = [float(row["release_time"]) for row in workload]
    return fault_windows(
        case.fault_profile,
        minimum_release=min(releases),
        maximum_release=max(releases),
    )


def _worker_command(
    case: CaseSpec,
    paths: Mapping[str, Path],
    args: argparse.Namespace,
    has_faults: bool,
) -> list[str]:
    command = [
        str(args.python),
        str(ROOT / "scripts" / "eval" / "run_g4irsf11_event_case.py"),
        "--workload", str(paths["workload"]),
        "--map", str(MAP_PATH),
        "--output", str(paths["result"]),
        "--search-path", str(args.search_path),
        "--scenario", case.case_id,
        "--scale", str(case.scale),
        "--workload-mode", case.workload_mode,
        "--fault-mode", case.fault_profile,
        "--queue-discipline", case.queue_discipline,
        "--diagnostic-hops", str(case.diagnostic_hops),
        "--trace-limit", "-1" if case.trace_complete else "0",
        "--max-events", str(args.max_events),
        "--max-backlog-slope-fraction", str(CAPACITY_SLO["max_backlog_slope_fraction"]),
        "--max-drain-seconds", str(CAPACITY_SLO["max_drain_seconds"]),
        "--max-p95-service-seconds", str(CAPACITY_SLO["max_p95_service_seconds"]),
        "--max-p99-service-seconds", str(CAPACITY_SLO["max_p99_service_seconds"]),
        "--max-deadline-miss-rate", str(CAPACITY_SLO["max_deadline_miss_rate"]),
        "--starvation-seconds", str(CAPACITY_SLO["starvation_seconds"]),
        "--max-fault-recovery-seconds", str(FAULT_SLO["max_fault_recovery_seconds"]),
    ]
    for enabled, name in (
        (case.enable_source_admission, "enable-source-admission"),
        (case.enable_backpressure, "enable-backpressure"),
        (case.enable_pibt_lite, "enable-pibt-lite"),
        (case.enable_deadlock_escape, "enable-deadlock-escape"),
    ):
        if not enabled:
            command.append(f"--no-{name}")
    if has_faults:
        command.extend(["--fault-windows", str(paths["fault"])])
    if case.trace_complete:
        command.extend(
            [
                "--trace-output", str(paths["trace"]),
                "--outcome-output", str(paths["outcomes"]),
                "--trace-task-output", str(paths["tasks"]),
            ]
        )
    return command


def execute_case(
    case: CaseSpec,
    base_rows: Sequence[Mapping[str, Any]],
    args: argparse.Namespace,
    *,
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
    protocol_version: str = PROTOCOL_VERSION,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    paths = _case_paths(case)
    if args.resume and paths["execution"].is_file() and paths["result"].is_file():
        descriptor = _read_json(paths["execution"])
        if _descriptor_matches(
            descriptor,
            case,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
            protocol_version=protocol_version,
        ):
            return _read_json(paths["result"]), descriptor

    lock_token = _acquire_case_lock(paths["lock"], case.case_id)
    if lock_token is None:
        existing = _read_json(paths["execution"]) if paths["execution"].is_file() else {}
        blocked = dict(existing)
        blocked["status"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
        blocked["blocker"] = (
            f"another writer owns exact case lock {paths['lock']}; do not delete it until the owning "
            "process is proven stopped, then rerun the exact case"
        )
        return None, blocked

    if not args.resume:
        _archive_existing_attempt(case, paths)

    started = time.perf_counter()
    workload = build_workload(base_rows, scale=case.scale, mode=case.workload_mode)
    workload = namespace_workload(workload, scenario=case.case_id, task_id_offset=0)
    if case.segment_limit is not None:
        workload = timeline_spanning_sample(workload, case.segment_limit)
    input_sha256 = _sha256_rows(workload)
    write_jsonl(paths["workload"], workload)
    windows = _fault_rows(case, workload)
    if windows:
        _write_json_array(paths["fault"], windows)
    command = _worker_command(case, paths, args, bool(windows))
    command_text = _command_text(command)
    del workload
    gc.collect()

    descriptor: dict[str, Any] = {
        "protocol_version": protocol_version,
        "case": case.as_dict(),
        "source_sha256": source_sha256,
        "map_sha256": map_sha256,
        "implementation_sha256": implementation_digest,
        "input_sha256": input_sha256,
        "command": command_text,
        "status": "RUNNING",
        "return_code": "",
        "blocker": "",
    }
    _write_json(paths["execution"], descriptor)
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=args.timeout_seconds,
            check=False,
        )
        descriptor["return_code"] = completed.returncode
        descriptor["stdout_tail"] = completed.stdout[-4000:]
        descriptor["stderr_tail"] = completed.stderr[-8000:]
        if completed.returncode == 0 and paths["result"].is_file():
            result = _read_json(paths["result"])
            descriptor["status"] = "EXECUTED"
        else:
            result = None
            descriptor["status"] = "FAILED"
            descriptor["blocker"] = (
                f"worker return code {completed.returncode}; reproduce: {command_text}"
            )
    except subprocess.TimeoutExpired as exc:
        result = None
        descriptor["status"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
        descriptor["return_code"] = "TIMEOUT"
        descriptor["stdout_tail"] = (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else ""
        descriptor["stderr_tail"] = (exc.stderr or "")[-8000:] if isinstance(exc.stderr, str) else ""
        descriptor["blocker"] = (
            f"isolated worker exceeded {args.timeout_seconds}s; reproduce without timeout: {command_text}"
        )
    descriptor["wall_seconds_parent"] = time.perf_counter() - started
    _write_json(paths["execution"], descriptor)
    if not args.keep_workloads and not case.trace_complete:
        paths["workload"].unlink(missing_ok=True)
    _release_case_lock(lock_token)
    return result, descriptor


def _write_json_array(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([dict(row) for row in rows], ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _load_all_rows(
    cases: Sequence[CaseSpec],
    *,
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        paths = _case_paths(case)
        execution: dict[str, Any] = {"status": "NOT_RUN", "blocker": "formal case not executed"}
        result: dict[str, Any] | None = None
        if paths["execution"].is_file():
            candidate = _read_json(paths["execution"])
            if _descriptor_matches(
                candidate,
                case,
                source_sha256=source_sha256,
                map_sha256=map_sha256,
                implementation_digest=implementation_digest,
            ):
                execution = candidate
                if paths["result"].is_file():
                    result = _read_json(paths["result"])
                else:
                    execution = dict(candidate)
                    execution["status"] = "FAILED"
                    execution["blocker"] = "execution descriptor exists but result JSON is missing"
            elif candidate.get("status") != "RUNNING":
                execution = candidate
        rows.append(case_row(case, result, execution))
    return rows


def _write_tables_and_reports(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    write_csv(CASE_TABLE, rows)
    table_dir = ROOT / "outputs" / "tables"
    categories = {
        "size_ladder": "g4irsf11_event_runtime_size_ladder.csv",
        "capacity_frontier": "g4irsf11_capacity_frontier.csv",
        "system_ablation": "g4irsf11_system_ablation.csv",
        "temporal_fault": "g4irsf11_temporal_fault_repair.csv",
    }
    for category, filename in categories.items():
        category_rows = [row for row in rows if row["category"] == category]
        write_csv(table_dir / filename, category_rows)
    resource_fields = (
        "case_id", "category", "workload_mode", "scale", "execution_status",
        "workload_segment_count", "peak_working_set_bytes", "cpp_internal_accounted_bytes",
        "decision_latency_us_p50", "decision_latency_us_p95", "decision_latency_us_p99",
        "event_throughput_per_second", "wall_seconds", "blocker",
    )
    write_csv(
        table_dir / "g4irsf11_resource_runtime.csv",
        [{name: row.get(name, "") for name in resource_fields} for row in rows],
    )
    gates = gate_rows(rows)
    write_csv(table_dir / "g4irsf11_event_runtime_gate.csv", gates)
    history_rows: list[dict[str, Any]] = []
    for case in formal_cases():
        history_path = _case_paths(case)["history"]
        if not history_path.is_file():
            continue
        for ordinal, row in enumerate(load_jsonl(history_path), start=1):
            item = dict(row)
            item["attempt_ordinal"] = ordinal
            if item.get("execution_status") != "EXECUTED" or not item.get("completion_pass"):
                history_rows.append(item)
    if history_rows:
        write_csv(table_dir / "g4irsf11_event_runtime_negative_attempts.csv", history_rows)
    write_reports(ROOT, rows)
    write_claim_boundary(ROOT, rows, gates)
    return gates


def _merge_trace_inputs(trace_cases: Sequence[CaseSpec]) -> tuple[list[Path], Path, Path]:
    trace_paths: list[Path] = []
    task_rows: list[dict[str, Any]] = []
    outcomes: list[dict[str, Any]] = []
    for case in trace_cases:
        paths = _case_paths(case)
        trace_paths.append(paths["trace"])
        task_rows.extend(load_jsonl(paths["tasks"]))
        outcomes.extend(load_jsonl(paths["outcomes"]))
    task_path = TRACE_DIR / "g4irsf11_trace_tasks_combined.jsonl"
    outcome_path = TRACE_DIR / "g4irsf11_trace_outcomes_combined.jsonl"
    write_jsonl(task_path, task_rows)
    write_jsonl(outcome_path, outcomes)
    return trace_paths, task_path, outcome_path


def _build_decision_artifacts(
    cases: Sequence[CaseSpec],
    *,
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
) -> dict[str, Any] | None:
    trace_cases = [case for case in cases if case.category == "decision_trace"]
    if not trace_cases:
        return None
    if not all(_case_paths(case)["execution"].is_file() for case in trace_cases):
        return None
    executions = [_read_json(_case_paths(case)["execution"]) for case in trace_cases]
    if not all(
        _descriptor_matches(
            row,
            case,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
        )
        for row, case in zip(executions, trace_cases)
    ):
        return None
    required = [
        path
        for case in trace_cases
        for path in (
            _case_paths(case)["trace"],
            _case_paths(case)["tasks"],
            _case_paths(case)["outcomes"],
        )
    ]
    if not all(path.is_file() for path in required):
        return None
    trace_paths, tasks, outcomes = _merge_trace_inputs(trace_cases)
    return write_artifacts(
        trace_paths=trace_paths,
        task_path=tasks,
        map_path=MAP_PATH,
        outcome_path=outcomes,
        scenario="g4irsf11_multi_trace",
        scale="mixed",
        fault_mode="mixed",
        config=SamplingConfig(
            limit=50_000,
            minimum_per_stratum=1,
            maximum_per_stratum=64,
            seed="czr005-g4irsf11-stratified-reservoir-v1",
        ),
        include_routine=False,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the frozen G4IRSF11 event-runtime matrix.")
    parser.add_argument("--case", action="append", help="Run only an exact case ID; repeatable")
    parser.add_argument("--category", action="append", help="Run only a category; repeatable")
    parser.add_argument(
        "--workload-mode",
        action="append",
        help="Filter selected formal cases by exact workload mode; repeatable.",
    )
    parser.add_argument("--resume", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--keep-workloads", action="store_true")
    parser.add_argument(
        "--execute-only",
        action="store_true",
        help="Run selected isolated cases without rewriting shared consolidated reports.",
    )
    parser.add_argument("--allow-incomplete-protocol", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument("--max-events", type=int, default=20_000_000)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--search-path", type=Path, default=ROOT / "build_vs" / "python" / "Release")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = formal_cases()
    by_id = {case.case_id: case for case in cases}
    if args.case:
        unknown = sorted(set(args.case) - set(by_id))
        if unknown:
            raise SystemExit(f"unknown --case values: {unknown}")
        selected = [by_id[name] for name in args.case]
    else:
        selected = list(cases)
        if args.category:
            selected = [case for case in selected if case.category in set(args.category)]
        if args.workload_mode:
            selected = [
                case for case in selected if case.workload_mode in set(args.workload_mode)
            ]
        if not selected:
            raise SystemExit(
                f"no cases matched categories={args.category} workload_modes={args.workload_mode}"
            )

    manifest = protocol_manifest()
    _write_json(PROTOCOL_PATH, manifest)
    base_rows = load_jsonl(SOURCE_TASK_PATH)
    if len(base_rows) != 43_603:
        raise SystemExit(f"formal source task count must be 43603, got {len(base_rows)}")
    source_sha256 = sha256_file(SOURCE_TASK_PATH)
    map_sha256 = sha256_file(MAP_PATH)
    implementation_digest = implementation_sha256(args.search_path)

    failures = 0
    for index, case in enumerate(selected, start=1):
        print(f"[g4irsf11-event] {index}/{len(selected)} START {case.case_id}", flush=True)
        _, execution = execute_case(
            case,
            base_rows,
            args,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
        )
        if execution.get("status") != "EXECUTED":
            failures += 1
        print(
            f"[g4irsf11-event] {index}/{len(selected)} {execution.get('status')} {case.case_id}",
            flush=True,
        )

    if args.execute_only:
        print(
            "[g4irsf11-event] execute-only summary",
            f"selected={len(selected)}",
            f"selected_failures={failures}",
            flush=True,
        )
        return 2 if failures else 0

    rows = _load_all_rows(
        cases,
        source_sha256=source_sha256,
        map_sha256=map_sha256,
        implementation_digest=implementation_digest,
    )
    gates = _write_tables_and_reports(rows)
    decision_manifest = _build_decision_artifacts(
        cases,
        source_sha256=source_sha256,
        map_sha256=map_sha256,
        implementation_digest=implementation_digest,
    )
    complete = all(row["execution_status"] == "EXECUTED" for row in rows)
    print(
        "[g4irsf11-event] summary",
        f"selected={len(selected)}",
        f"selected_failures={failures}",
        f"formal_executed={sum(row['execution_status'] == 'EXECUTED' for row in rows)}/{len(rows)}",
        f"runtime_gates_pass={sum(row['status'] == 'PASS' for row in gates)}/{len(gates)}",
        f"decision_manifest={'written' if decision_manifest else 'not_ready'}",
        flush=True,
    )
    if failures:
        return 2
    if not complete and not args.allow_incomplete_protocol:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
