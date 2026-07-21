"""Execute the frozen G4IRSF11 event-runtime protocol case by case.

Each case runs in a fresh process so peak working set is an OS measurement.
Raw full traces and generated workloads stay in ``.pytest_cache``; only compact
tables, reports, schemas and balanced samples are repository artifacts.
"""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence
import uuid


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
    EXTENSION_PROTOCOL_VERSION,
    CaseSpec,
    fault_windows,
    formal_cases,
    protocol_manifest,
    system_extension_manifest,
)
from scripts.eval.g4irsf11_workloads import (
    build_workload,
    load_jsonl,
    namespace_workload,
)
from scripts.eval.g4irsf11_result_validation import (
    EXECUTION_DESCRIPTOR_SCHEMA,
    ResultExpectation,
    WORKER_RUNTIME_DEFAULTS,
    artifact_binding,
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_json_bytes,
    canonical_manifest_sha256,
    count_jsonl_rows,
    fault_binding,
    read_json_array,
    read_json_object,
    validate_execution_descriptor,
    workload_binding,
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
PROTOCOL_LOCK = RUNTIME_ROOT / "shared_protocol.lock"
CONSOLIDATION_LOCK = RUNTIME_ROOT / "shared_consolidation.lock"

IMPLEMENTATION_FILES = (
    ROOT / "cpp" / "ics_core" / "runtime" / "event_driven_junction.hpp",
    ROOT / "cpp" / "ics_core" / "bindings" / "czr005_cpp.cpp",
    ROOT / "src" / "czr005" / "cpp_backend.py",
    ROOT / "scripts" / "eval" / "g4irsf11_workloads.py",
    ROOT / "scripts" / "eval" / "g4irsf11_capacity_metrics.py",
    ROOT / "scripts" / "eval" / "g4irsf11_fault_metrics.py",
    ROOT / "scripts" / "eval" / "g4irsf11_continuity_metrics.py",
    ROOT / "scripts" / "eval" / "g4irsf11_experiment_protocol.py",
    ROOT / "scripts" / "eval" / "g4irsf11_evaluation_reporting.py",
    ROOT / "scripts" / "eval" / "g4irsf11_result_validation.py",
    ROOT / "scripts" / "eval" / "run_g4irsf11_event_case.py",
    ROOT / "scripts" / "eval" / "run_g4irsf11_event_runtime_evaluation.py",
    ROOT / "scripts" / "eval" / "run_g4irsf11_system_extensions.py",
)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(path, dict(value))


def _read_json(path: Path) -> dict[str, Any]:
    return read_json_object(path)


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
        "archive": EXECUTION_DIR / "archive" / case.case_id,
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
    path = Path(token["path"])
    try:
        current = read_json_object(path)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        current = {}
    if (
        current.get("pid") == token.get("pid")
        and current.get("nonce") == token.get("nonce")
    ):
        path.unlink(missing_ok=True)
    token["released"] = True


def _acquire_case_lock(
    path: Path,
    case_id: str,
    *,
    wait_seconds: float = 0.0,
) -> dict[str, Any] | None:
    """Acquire an atomic per-case writer lease, or fail closed.

    A stale lock is intentionally not guessed away.  Operators must first
    prove that no worker owns it, retain the failed attempt, and then remove
    that exact file before retrying.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + max(0.0, wait_seconds)
    while True:
        try:
            descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.05)
    nonce = uuid.uuid4().hex
    payload = json.dumps(
        {
            "case_id": case_id,
            "pid": os.getpid(),
            "nonce": nonce,
            "acquired_unix_time": time.time(),
        },
        sort_keys=True,
    ).encode("utf-8")
    os.write(descriptor, payload)
    os.fsync(descriptor)
    token: dict[str, Any] = {
        "descriptor": descriptor,
        "path": path,
        "pid": os.getpid(),
        "nonce": nonce,
        "released": False,
    }
    atexit.register(_release_case_lock, token)
    return token


def _archive_existing_attempt(
    case: CaseSpec,
    paths: Mapping[str, Path],
    *,
    reason: str,
) -> None:
    """Archive stale/mismatched evidence while holding the exact case lock."""

    if not any(paths[name].is_file() for name in ("execution", "result", "trace", "outcomes", "tasks")):
        return
    try:
        execution = _read_json(paths["execution"]) if paths["execution"].is_file() else {}
    except (OSError, ValueError):
        execution = {"status": "CORRUPT_DESCRIPTOR"}
    try:
        result = _read_json(paths["result"]) if paths["result"].is_file() else {}
    except (OSError, ValueError):
        result = {}
    summary = result.get("summary") or {}
    capacity = result.get("raw_bag_capacity_metrics") or {}
    sample_reasons: dict[str, int] = {}
    for row in result.get("bag_sample") or []:
        failure_reason = str(row.get("failure_reason") or "")
        if failure_reason:
            sample_reasons[failure_reason] = sample_reasons.get(failure_reason, 0) + 1
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
        "archived_reason": reason,
        "archived_status": (
            "ARCHIVED_STALE_RUNNING_NOT_REUSABLE"
            if execution.get("status") == "RUNNING"
            else "ARCHIVED_NOT_REUSABLE"
        ),
        "archived_unix_time": time.time(),
    }
    artifact_evidence: dict[str, Any] = {}
    for name in ("execution", "result", "trace", "outcomes", "tasks", "workload", "fault"):
        path = paths[name]
        if path.is_file():
            artifact_evidence[name] = {
                "path": str(path.resolve()),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
    compact["artifact_evidence"] = artifact_evidence

    run_id = str(execution.get("run_id") or "legacy-no-run-id")
    run_token = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
    archive_token = f"{time.time_ns()}-{run_token}"
    archive_dir = paths["archive"] / archive_token
    archive_dir.mkdir(parents=True, exist_ok=False)
    atomic_write_json(archive_dir / "archive_manifest.json", compact)
    if paths["execution"].is_file():
        atomic_write_bytes(archive_dir / "execution.json", paths["execution"].read_bytes())
    if paths["result"].is_file():
        atomic_write_bytes(archive_dir / "result.json", paths["result"].read_bytes())

    previous: list[dict[str, Any]] = []
    if paths["history"].is_file():
        try:
            for row in load_jsonl(paths["history"]):
                previous.append(dict(row))
        except (OSError, ValueError, json.JSONDecodeError):
            previous.append(
                {
                    "archived_status": "CORRUPT_PRIOR_HISTORY_RETAINED_BY_HASH",
                    "sha256": sha256_file(paths["history"]),
                    "size_bytes": paths["history"].stat().st_size,
                }
            )
    previous.append(compact)
    atomic_write_jsonl(paths["history"], previous)


def _descriptor_matches(
    descriptor: Mapping[str, Any],
    case: CaseSpec,
    *,
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
    protocol_version: str = PROTOCOL_VERSION,
    protocol_manifest_value: Mapping[str, Any] | None = None,
    paths: Mapping[str, Path] | None = None,
) -> bool:
    manifest = dict(
        protocol_manifest_value
        or (
            system_extension_manifest()
            if protocol_version == EXTENSION_PROTOCOL_VERSION
            else protocol_manifest()
        )
    )
    identity_matches = (
        descriptor.get("schema") == EXECUTION_DESCRIPTOR_SCHEMA
        and descriptor.get("protocol_version") == protocol_version
        and descriptor.get("protocol_manifest_sha256")
        == canonical_manifest_sha256(manifest)
        and descriptor.get("case") == case.as_dict()
        and descriptor.get("source_sha256") == source_sha256
        and descriptor.get("map_sha256") == map_sha256
        and descriptor.get("implementation_sha256") == implementation_digest
        and descriptor.get("status") == "EXECUTED"
        and descriptor.get("return_code") == 0
        and descriptor.get("blocker") == ""
    )
    if not identity_matches:
        return False
    bundle_paths = paths or _case_paths(case)
    try:
        result = _read_json(bundle_paths["result"])
        workload_rows = load_jsonl(bundle_paths["workload"])
        fault_payload = read_json_array(bundle_paths["fault"])
        expectation = ResultExpectation(
            run_id=str(descriptor.get("run_id") or ""),
            case=case.as_dict(),
            protocol_version=protocol_version,
            protocol_manifest_sha256=canonical_manifest_sha256(manifest),
            input_artifact=dict(descriptor.get("input_artifact") or {}),
            fault_artifact=dict(descriptor.get("fault_artifact") or {}),
            fault_rows=[dict(row) for row in fault_payload],
            map_sha256=map_sha256,
            source_sha256=source_sha256,
            implementation_sha256=implementation_digest,
            config=dict(descriptor.get("config") or {}),
            measurement_cohort=dict(descriptor.get("measurement_cohort") or {}),
        )
        return not _bundle_validation_errors(
            descriptor,
            result,
            expectation,
            case=case,
            paths=bundle_paths,
            normalized_argv=list(descriptor.get("normalized_argv") or []),
            parent_timeout_seconds=float(descriptor.get("parent_timeout_seconds")),
            workload_rows=workload_rows,
        )
    except (FileNotFoundError, OSError, ValueError, TypeError, KeyError):
        return False


def _command_text(command: Sequence[str]) -> str:
    return subprocess.list2cmdline(list(command)) if sys.platform == "win32" else shlex.join(command)


def _fault_rows(case: CaseSpec, workload: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    releases = [float(row["release_time"]) for row in workload]
    return fault_windows(
        case.fault_profile,
        minimum_release=min(releases),
        maximum_release=max(releases),
    )


def _measurement_cohort(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "name": str(args.measurement_cohort),
        "declared_concurrent_worker_target": int(args.concurrent_worker_target),
    }


def _worker_config(case: CaseSpec, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "queue_discipline": case.queue_discipline,
        "retry_interval": WORKER_RUNTIME_DEFAULTS["retry_interval"],
        "minimum_service_seconds": WORKER_RUNTIME_DEFAULTS["minimum_service_seconds"],
        "dispatch_headway_seconds": WORKER_RUNTIME_DEFAULTS["dispatch_headway_seconds"],
        "history_limit": WORKER_RUNTIME_DEFAULTS["history_limit"],
        "max_decisions_per_bag": WORKER_RUNTIME_DEFAULTS["max_decisions_per_bag"],
        "max_events": int(args.max_events),
        "max_simulation_time": WORKER_RUNTIME_DEFAULTS["max_simulation_time"],
        "trace_limit": -1 if case.trace_complete else 0,
        "trace_shard_count": WORKER_RUNTIME_DEFAULTS["trace_shard_count"],
        "trace_shard_index": WORKER_RUNTIME_DEFAULTS["trace_shard_index"],
        "local_queue_capacity": WORKER_RUNTIME_DEFAULTS["local_queue_capacity"],
        "deadlock_retry_threshold": WORKER_RUNTIME_DEFAULTS["deadlock_retry_threshold"],
        "diagnostic_hops": case.diagnostic_hops,
        "enable_source_admission": case.enable_source_admission,
        "enable_backpressure": case.enable_backpressure,
        "enable_pibt_lite": case.enable_pibt_lite,
        "enable_deadlock_escape": case.enable_deadlock_escape,
        "enable_fault_policy": case.enable_fault_policy,
        "max_backlog_slope_fraction": CAPACITY_SLO["max_backlog_slope_fraction"],
        "max_drain_seconds": CAPACITY_SLO["max_drain_seconds"],
        "max_p95_service_seconds": CAPACITY_SLO["max_p95_service_seconds"],
        "max_p99_service_seconds": CAPACITY_SLO["max_p99_service_seconds"],
        "max_deadline_miss_rate": CAPACITY_SLO["max_deadline_miss_rate"],
        "starvation_seconds": CAPACITY_SLO["starvation_seconds"],
        "max_fault_recovery_seconds": FAULT_SLO["max_fault_recovery_seconds"],
    }


def _worker_command(
    case: CaseSpec,
    paths: Mapping[str, Path],
    args: argparse.Namespace,
    *,
    run_id: str,
    protocol_version: str,
    protocol_manifest_digest: str,
    input_artifact: Mapping[str, Any],
    fault_artifact: Mapping[str, Any],
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
) -> list[str]:
    config = _worker_config(case, args)
    command = [
        str(args.python.resolve()),
        str((ROOT / "scripts" / "eval" / "run_g4irsf11_event_case.py").resolve()),
        "--run-id", run_id,
        "--protocol-version", protocol_version,
        "--protocol-manifest-sha256", protocol_manifest_digest,
        "--case-spec-json", canonical_json_bytes(case.as_dict()).decode("utf-8"),
        "--input-artifact-json", canonical_json_bytes(dict(input_artifact)).decode("utf-8"),
        "--fault-artifact-json", canonical_json_bytes(dict(fault_artifact)).decode("utf-8"),
        "--map-sha256", map_sha256,
        "--source-sha256", source_sha256,
        "--implementation-sha256", implementation_digest,
        "--measurement-cohort", str(args.measurement_cohort),
        "--concurrent-worker-target", str(args.concurrent_worker_target),
        "--workload", str(paths["workload"].resolve()),
        "--map", str(MAP_PATH.resolve()),
        "--output", str(paths["result"].resolve()),
        "--search-path", str(args.search_path.resolve()),
        "--scenario", case.case_id,
        "--scale", str(case.scale),
        "--workload-mode", case.workload_mode,
        "--fault-mode", case.fault_profile,
        "--fault-windows", str(paths["fault"].resolve()),
        "--queue-discipline", case.queue_discipline,
        "--retry-interval", str(config["retry_interval"]),
        "--minimum-service-seconds", str(config["minimum_service_seconds"]),
        "--dispatch-headway-seconds", str(config["dispatch_headway_seconds"]),
        "--history-limit", str(config["history_limit"]),
        "--max-decisions-per-bag", str(config["max_decisions_per_bag"]),
        "--max-events", str(config["max_events"]),
        "--max-simulation-time", str(config["max_simulation_time"]),
        "--trace-limit", str(config["trace_limit"]),
        "--trace-shard-count", str(config["trace_shard_count"]),
        "--trace-shard-index", str(config["trace_shard_index"]),
        "--local-queue-capacity", str(config["local_queue_capacity"]),
        "--deadlock-retry-threshold", str(config["deadlock_retry_threshold"]),
        "--diagnostic-hops", str(config["diagnostic_hops"]),
        "--max-backlog-slope-fraction", str(config["max_backlog_slope_fraction"]),
        "--max-drain-seconds", str(config["max_drain_seconds"]),
        "--max-p95-service-seconds", str(config["max_p95_service_seconds"]),
        "--max-p99-service-seconds", str(config["max_p99_service_seconds"]),
        "--max-deadline-miss-rate", str(config["max_deadline_miss_rate"]),
        "--starvation-seconds", str(config["starvation_seconds"]),
        "--max-fault-recovery-seconds", str(config["max_fault_recovery_seconds"]),
    ]
    for enabled, name in (
        (case.enable_source_admission, "enable-source-admission"),
        (case.enable_backpressure, "enable-backpressure"),
        (case.enable_pibt_lite, "enable-pibt-lite"),
        (case.enable_deadlock_escape, "enable-deadlock-escape"),
        (case.enable_fault_policy, "enable-fault-policy"),
    ):
        command.append(f"--{name}" if enabled else f"--no-{name}")
    if case.trace_complete:
        command.extend(
            [
                "--trace-output", str(paths["trace"].resolve()),
                "--outcome-output", str(paths["outcomes"].resolve()),
                "--trace-task-output", str(paths["tasks"].resolve()),
            ]
        )
    return command


def _trace_artifact_bindings(
    case: CaseSpec,
    paths: Mapping[str, Path],
) -> dict[str, dict[str, Any]]:
    if not case.trace_complete:
        unexpected = [name for name in ("trace", "outcomes", "tasks") if paths[name].exists()]
        if unexpected:
            raise ValueError(
                "non-trace case has unexpected trace artifacts: " + ", ".join(unexpected)
            )
        return {
            name: artifact_binding(paths[name], state="not_requested")
            for name in ("trace", "outcomes", "tasks")
        }
    trace_payload = _read_json(paths["trace"])
    decisions = trace_payload.get("decision_trace")
    if not isinstance(decisions, list):
        raise ValueError("trace artifact decision_trace must be an array")
    return {
        "trace": artifact_binding(paths["trace"], row_count=len(decisions)),
        "outcomes": artifact_binding(
            paths["outcomes"], row_count=count_jsonl_rows(paths["outcomes"])
        ),
        "tasks": artifact_binding(
            paths["tasks"], row_count=count_jsonl_rows(paths["tasks"])
        ),
    }


def _expectation(
    case: CaseSpec,
    args: argparse.Namespace,
    *,
    run_id: str,
    protocol_version: str,
    protocol_manifest_digest: str,
    input_artifact: Mapping[str, Any],
    fault_artifact: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
) -> ResultExpectation:
    return ResultExpectation(
        run_id=run_id,
        case=case.as_dict(),
        protocol_version=protocol_version,
        protocol_manifest_sha256=protocol_manifest_digest,
        input_artifact=dict(input_artifact),
        fault_artifact=dict(fault_artifact),
        fault_rows=[dict(row) for row in windows],
        map_sha256=map_sha256,
        source_sha256=source_sha256,
        implementation_sha256=implementation_digest,
        config=_worker_config(case, args),
        measurement_cohort=_measurement_cohort(args),
    )


def _bundle_validation_errors(
    descriptor: Mapping[str, Any],
    result: Mapping[str, Any],
    expectation: ResultExpectation,
    *,
    case: CaseSpec,
    paths: Mapping[str, Path],
    normalized_argv: Sequence[str],
    parent_timeout_seconds: float,
    workload_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    errors: list[str] = []
    if not paths["workload"].is_file():
        errors.append("workload artifact is missing")
    elif sha256_file(paths["workload"]) != expectation.input_artifact.get("sha256"):
        errors.append("workload file hash differs from rebuilt canonical workload")
    if not paths["fault"].is_file():
        errors.append("fault artifact is missing, including required explicit-empty artifact")
    elif sha256_file(paths["fault"]) != expectation.fault_artifact.get("sha256"):
        errors.append("fault file hash differs from canonical fault input")
    try:
        result_artifact = artifact_binding(paths["result"])
        trace_artifacts = _trace_artifact_bindings(case, paths)
    except (FileNotFoundError, OSError, ValueError) as exc:
        errors.append(f"output artifact validation failed: {exc}")
        return sorted(set(errors))
    errors.extend(
        validate_execution_descriptor(
            descriptor,
            result,
            expectation,
            normalized_argv=normalized_argv,
            normalized_command_text=_command_text(normalized_argv),
            parent_timeout_seconds=parent_timeout_seconds,
            result_artifact=result_artifact,
            trace_artifacts=trace_artifacts,
            workload_rows=workload_rows,
        )
    )
    environment = result.get("environment")
    if not isinstance(environment, Mapping):
        errors.append("result environment is missing")
    elif not normalized_argv:
        errors.append("normalized worker argv is empty")
    elif Path(str(environment.get("python_executable") or "")).resolve() != Path(
        normalized_argv[0]
    ).resolve():
        errors.append("worker environment python executable differs from normalized argv")
    return sorted(set(errors))


def execute_case(
    case: CaseSpec,
    base_rows: Sequence[Mapping[str, Any]],
    args: argparse.Namespace,
    *,
    source_sha256: str,
    map_sha256: str,
    implementation_digest: str,
    protocol_version: str = PROTOCOL_VERSION,
    protocol_manifest_value: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    paths = _case_paths(case)
    lock_token = _acquire_case_lock(paths["lock"], case.case_id)
    if lock_token is None:
        try:
            existing = _read_json(paths["execution"]) if paths["execution"].is_file() else {}
        except (OSError, ValueError):
            existing = {}
        blocked = dict(existing)
        blocked["status"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
        blocked["blocker"] = (
            f"another writer owns exact case lock {paths['lock']}; do not delete it until the owning "
            "process is proven stopped, then rerun the exact case"
        )
        return None, blocked
    descriptor: dict[str, Any] = {}
    try:
        manifest = dict(protocol_manifest_value or protocol_manifest())
        protocol_manifest_digest = canonical_manifest_sha256(manifest)
        workload = build_workload(base_rows, scale=case.scale, mode=case.workload_mode)
        workload = namespace_workload(workload, scenario=case.case_id, task_id_offset=0)
        if case.segment_limit is not None:
            workload = timeline_spanning_sample(workload, case.segment_limit)
        input_artifact = workload_binding(paths["workload"], workload)
        windows = _fault_rows(case, workload)
        fault_artifact = fault_binding(paths["fault"], windows)

        if args.resume and paths["execution"].is_file() and paths["result"].is_file():
            try:
                candidate = _read_json(paths["execution"])
                candidate_result = _read_json(paths["result"])
                candidate_run_id = str(candidate.get("run_id") or "")
                candidate_command = _worker_command(
                    case,
                    paths,
                    args,
                    run_id=candidate_run_id,
                    protocol_version=protocol_version,
                    protocol_manifest_digest=protocol_manifest_digest,
                    input_artifact=input_artifact,
                    fault_artifact=fault_artifact,
                    source_sha256=source_sha256,
                    map_sha256=map_sha256,
                    implementation_digest=implementation_digest,
                )
                candidate_expectation = _expectation(
                    case,
                    args,
                    run_id=candidate_run_id,
                    protocol_version=protocol_version,
                    protocol_manifest_digest=protocol_manifest_digest,
                    input_artifact=input_artifact,
                    fault_artifact=fault_artifact,
                    windows=windows,
                    source_sha256=source_sha256,
                    map_sha256=map_sha256,
                    implementation_digest=implementation_digest,
                )
                resume_errors = _bundle_validation_errors(
                    candidate,
                    candidate_result,
                    candidate_expectation,
                    case=case,
                    paths=paths,
                    normalized_argv=candidate_command,
                    parent_timeout_seconds=args.timeout_seconds,
                    workload_rows=workload,
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                resume_errors = [f"resume bundle could not be decoded: {exc}"]
            if not resume_errors:
                return candidate_result, candidate
            _archive_existing_attempt(
                case,
                paths,
                reason="resume_validation_failed: " + "; ".join(resume_errors),
            )
        elif any(
            paths[name].is_file()
            for name in ("execution", "result", "trace", "outcomes", "tasks")
        ):
            _archive_existing_attempt(
                case,
                paths,
                reason="exact rerun requested without a reusable complete v3 bundle",
            )

        atomic_write_jsonl(paths["workload"], workload)
        _write_json_array(paths["fault"], windows)
        if sha256_file(paths["workload"]) != input_artifact["sha256"]:
            raise ValueError("published workload hash differs from canonical workload hash")
        if sha256_file(paths["fault"]) != fault_artifact["sha256"]:
            raise ValueError("published fault artifact hash differs from canonical fault hash")

        run_id = str(uuid.uuid4())
        command = _worker_command(
            case,
            paths,
            args,
            run_id=run_id,
            protocol_version=protocol_version,
            protocol_manifest_digest=protocol_manifest_digest,
            input_artifact=input_artifact,
            fault_artifact=fault_artifact,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
        )
        command_text = _command_text(command)
        expectation = _expectation(
            case,
            args,
            run_id=run_id,
            protocol_version=protocol_version,
            protocol_manifest_digest=protocol_manifest_digest,
            input_artifact=input_artifact,
            fault_artifact=fault_artifact,
            windows=windows,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
        )
        descriptor = {
            "schema": EXECUTION_DESCRIPTOR_SCHEMA,
            "run_id": run_id,
            "protocol_version": protocol_version,
            "protocol_manifest_sha256": protocol_manifest_digest,
            "case": case.as_dict(),
            "config": _worker_config(case, args),
            "source_sha256": source_sha256,
            "map_sha256": map_sha256,
            "implementation_sha256": implementation_digest,
            "input_sha256": input_artifact["sha256"],
            "input_artifact": input_artifact,
            "fault_artifact": fault_artifact,
            "normalized_argv": list(command),
            "command": command_text,
            "parent_timeout_seconds": float(args.timeout_seconds),
            "measurement_cohort": _measurement_cohort(args),
            "environment": {},
            "result_artifact": {},
            "trace_artifacts": {},
            "status": "RUNNING",
            "return_code": "",
            "blocker": "",
        }
        _write_json(paths["execution"], descriptor)
        started = time.perf_counter()
        result: dict[str, Any] | None = None
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
            descriptor["wall_seconds_parent"] = time.perf_counter() - started
            if completed.returncode == 0 and paths["result"].is_file():
                try:
                    result = _read_json(paths["result"])
                    descriptor["result_artifact"] = artifact_binding(paths["result"])
                    descriptor["trace_artifacts"] = _trace_artifact_bindings(case, paths)
                    descriptor["environment"] = dict(result.get("environment") or {})
                    descriptor["status"] = "EXECUTED"
                    validation_errors = _bundle_validation_errors(
                        descriptor,
                        result,
                        expectation,
                        case=case,
                        paths=paths,
                        normalized_argv=command,
                        parent_timeout_seconds=args.timeout_seconds,
                        workload_rows=workload,
                    )
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    validation_errors = [f"worker result bundle could not be decoded: {exc}"]
                if validation_errors:
                    descriptor["status"] = "FAILED"
                    descriptor["blocker"] = (
                        "strict v3 result/descriptor validation failed: "
                        + "; ".join(validation_errors)
                    )
                    result = None
            else:
                descriptor["status"] = "FAILED"
                descriptor["blocker"] = (
                    f"worker return code {completed.returncode}; reproduce: {command_text}"
                )
        except subprocess.TimeoutExpired as exc:
            descriptor["status"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
            descriptor["return_code"] = "TIMEOUT"
            descriptor["stdout_tail"] = (
                (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else ""
            )
            descriptor["stderr_tail"] = (
                (exc.stderr or "")[-8000:] if isinstance(exc.stderr, str) else ""
            )
            descriptor["blocker"] = (
                f"isolated worker exceeded {args.timeout_seconds}s; reproduce without timeout: {command_text}"
            )
            descriptor["wall_seconds_parent"] = time.perf_counter() - started
        _write_json(paths["execution"], descriptor)
        return result, descriptor
    except Exception as exc:
        failed = dict(descriptor)
        failed.setdefault("schema", EXECUTION_DESCRIPTOR_SCHEMA)
        failed.setdefault("run_id", str(uuid.uuid4()))
        failed.setdefault("protocol_version", protocol_version)
        failed.setdefault("case", case.as_dict())
        failed["status"] = "FAILED"
        failed["return_code"] = "PARENT_EXCEPTION"
        failed["blocker"] = (
            f"parent execution setup failed: {type(exc).__name__}: {exc}"
        )
        _write_json(paths["execution"], failed)
        return None, failed
    finally:
        _release_case_lock(lock_token)


def _write_json_array(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    atomic_write_json(path, [dict(row) for row in rows])


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
            elif candidate.get("status") == "RUNNING":
                execution = dict(candidate)
                execution["status"] = "PARTIAL_WITH_EXPLICIT_BLOCKER"
                execution["blocker"] = (
                    "stale/unverified RUNNING descriptor is not reusable; acquire the case lock, "
                    "archive it explicitly, and rerun"
                )
            elif candidate.get("status") == "EXECUTED":
                execution = dict(candidate)
                execution["claimed_execution_status"] = "EXECUTED"
                execution["status"] = "FAILED"
                execution["blocker"] = (
                    "descriptor claimed EXECUTED but strict v3 identity/artifact/semantic "
                    "bundle validation failed; result is not reusable or reportable as executed"
                )
            else:
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
    atomic_write_jsonl(task_path, task_rows)
    atomic_write_jsonl(outcome_path, outcomes)
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
    parser.add_argument(
        "--keep-workloads",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Strict v3 requires retained exact inputs for resume revalidation.",
    )
    parser.add_argument(
        "--execute-only",
        action="store_true",
        help="Run selected isolated cases without rewriting shared consolidated reports.",
    )
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument("--max-events", type=int, default=20_000_000)
    parser.add_argument("--measurement-cohort", required=True)
    parser.add_argument("--concurrent-worker-target", type=int, required=True)
    parser.add_argument("--shared-lock-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--search-path", type=Path, default=ROOT / "build_vs" / "python" / "Release")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.keep_workloads:
        raise SystemExit("strict v3 forbids --no-keep-workloads because resume must rehash exact inputs")
    if not str(args.measurement_cohort).strip():
        raise SystemExit("--measurement-cohort must be non-empty")
    if args.concurrent_worker_target <= 0:
        raise SystemExit("--concurrent-worker-target must be positive")
    if args.timeout_seconds <= 0.0 or args.shared_lock_timeout_seconds < 0.0:
        raise SystemExit("timeout values must be positive (shared lock timeout may be zero)")
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
    protocol_lock = _acquire_case_lock(
        PROTOCOL_LOCK,
        "shared_protocol_manifest",
        wait_seconds=args.shared_lock_timeout_seconds,
    )
    if protocol_lock is None:
        raise SystemExit(
            f"could not acquire shared protocol lock {PROTOCOL_LOCK}; prove its owner stopped before removal"
        )
    try:
        _write_json(PROTOCOL_PATH, manifest)
    finally:
        _release_case_lock(protocol_lock)
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
            protocol_manifest_value=manifest,
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

    consolidation_lock = _acquire_case_lock(
        CONSOLIDATION_LOCK,
        "shared_consolidation",
        wait_seconds=args.shared_lock_timeout_seconds,
    )
    if consolidation_lock is None:
        raise SystemExit(
            f"could not acquire shared consolidation lock {CONSOLIDATION_LOCK}; "
            "no shared report was rewritten"
        )
    try:
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
    finally:
        _release_case_lock(consolidation_lock)
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
    if not complete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
