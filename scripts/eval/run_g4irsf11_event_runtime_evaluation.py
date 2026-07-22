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
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence
import uuid


ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from czr005.datasets.decision_trace import SamplingConfig
from scripts.eval.g4irsf11_fixed_map import (
    CANONICAL_MAP_PATH,
    CANONICAL_MAP_SHA256,
    assert_canonical_map,
    canonical_map_identity,
    canonical_map_protocol_identity,
)
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
    atomic_write_json,
    atomic_write_jsonl,
    canonical_json_bytes,
    canonical_manifest_sha256,
    count_jsonl_rows,
    fault_binding,
    parse_json_object,
    read_json_array,
    read_json_object,
    validate_execution_descriptor,
    workload_binding,
)
from scripts.eval.g4irsf11_publication import (
    artifact_bindings as publication_artifact_bindings,
    begin_completion,
    complete_publication,
    completion_validation_errors,
    create_staging_root,
    promote_staged_artifacts,
    semantic_file_sha256,
    source_bundle_sha256,
)
from scripts.eval.run_g4irsf11_decision_trace_sampling import write_artifacts


MAP_PATH = CANONICAL_MAP_PATH
SOURCE_TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
RUNTIME_ROOT = ROOT / ".pytest_cache" / "g4irsf11" / "event_evaluation"
WORKLOAD_DIR = RUNTIME_ROOT / "workloads"
RESULT_DIR = RUNTIME_ROOT / "results"
TRACE_DIR = RUNTIME_ROOT / "traces"
EXECUTION_DIR = RUNTIME_ROOT / "executions"
FAULT_DIR = RUNTIME_ROOT / "faults"
PROTOCOL_PATH = ROOT / "artifacts" / "gates" / "g4irsf11_event_runtime_protocol.json"
FORMAL_COMPLETION_PATH = (
    ROOT / "artifacts" / "gates" / "g4irsf11_event_runtime_completion.json"
)
CASE_TABLE = ROOT / "outputs" / "tables" / "g4irsf11_event_runtime_case_ledger.csv"
PROTOCOL_LOCK = RUNTIME_ROOT / "shared_protocol.lock"
CONSOLIDATION_LOCK = RUNTIME_ROOT / "shared_consolidation.lock"

CPP_IMPLEMENTATION_FILES = tuple(
    sorted(
        path
        for path in (ROOT / "cpp" / "ics_core").rglob("*")
        if path.is_file() and path.suffix.lower() in {".c", ".cc", ".cpp", ".h", ".hpp"}
    )
)
PYTHON_IMPLEMENTATION_FILES = tuple(
    sorted(
        {
            *(ROOT / "src" / "czr005").rglob("*.py"),
            *(ROOT / "scripts" / "eval").glob("g4irsf11*.py"),
            *(ROOT / "scripts" / "eval").glob("run_g4irsf11*.py"),
            ROOT / "scripts" / "eval" / "validate_g4irsf11_committed_artifacts.py",
            ROOT / "scripts" / "eval" / "g4i_runtime.py",
        }
    )
)
IMPLEMENTATION_FILES = (
    ROOT / "CMakeLists.txt",
    *CPP_IMPLEMENTATION_FILES,
    *PYTHON_IMPLEMENTATION_FILES,
)

FORMAL_PUBLICATION_ARTIFACTS = (
    "artifacts/gates/g4irsf11_event_runtime_protocol.json",
    "artifacts/datasets/g4irsf11_decision_trace_schema.json",
    "artifacts/datasets/g4irsf11_decision_trace_manifest.json",
    "artifacts/datasets/g4irsf11_decision_trace_sample.jsonl",
    "artifacts/datasets/g4irsf11_decision_outcome_sample.jsonl",
    "outputs/tables/g4irsf11_event_runtime_case_ledger.csv",
    "outputs/tables/g4irsf11_event_runtime_size_ladder.csv",
    "outputs/tables/g4irsf11_capacity_frontier.csv",
    "outputs/tables/g4irsf11_system_ablation.csv",
    "outputs/tables/g4irsf11_temporal_fault_repair.csv",
    "outputs/tables/g4irsf11_resource_runtime.csv",
    "outputs/tables/g4irsf11_event_runtime_gate.csv",
    "outputs/tables/g4irsf11_event_runtime_negative_attempts.csv",
    "outputs/tables/g4irsf11_stratified_hard_case_index.csv",
    "outputs/tables/g4irsf11_sampling_balance.csv",
    "outputs/tables/g4irsf11_feature_lineage_audit.csv",
    "outputs/tables/g4irsf11_source_release_decision_mapping.csv",
    "outputs/tables/g4irsf11_source_identity_audit.csv",
    "outputs/reports/g4irsf11_event_runtime_correctness_report.md",
    "outputs/reports/g4irsf11_capacity_frontier_report.md",
    "outputs/reports/g4irsf11_system_ablation_report.md",
    "outputs/reports/g4irsf11_temporal_fault_report.md",
    "outputs/reports/g4irsf11_runtime_resource_report.md",
    "outputs/reports/g4irsf11_claim_boundary_report.md",
    "outputs/reports/g4irsf11_sampling_balance_report.md",
    "outputs/reports/g4irsf11_feature_lineage_audit.md",
    "outputs/reports/g4irsf11_source_identity_audit.md",
)


def _fixed_map_protocol_manifest(
    base: Mapping[str, Any] | None = None,
    *,
    extension: bool = False,
) -> dict[str, Any]:
    manifest = dict(
        base
        or (system_extension_manifest() if extension else protocol_manifest())
    )
    manifest["fixed_real_map_only"] = True
    manifest["canonical_map"] = canonical_map_protocol_identity()
    return manifest


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(path, dict(value))


def _read_json(path: Path) -> dict[str, Any]:
    return read_json_object(path)


def _atomic_copy_file(source: Path, destination: Path) -> None:
    """Stream an exact copy into place without exposing partial archive bytes."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        with source.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            shutil.copyfileobj(input_handle, output_handle, length=1024 * 1024)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            rows.append(
                parse_json_object(line, label=f"{path}:{line_number}")
            )
    return rows


def _source_identity_from_payload(payload: bytes) -> dict[str, Any]:
    normalized = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return {
        "path": SOURCE_TASK_PATH.relative_to(ROOT).as_posix(),
        "raw_bytes_sha256": hashlib.sha256(payload).hexdigest(),
        "semantic_sha256": hashlib.sha256(normalized).hexdigest(),
        "semantic_hash_semantics": (
            "sha256 of text bytes after CRLF/CR newline normalization to LF"
        ),
        "row_count": sum(bool(line.strip()) for line in normalized.splitlines()),
    }


def load_source_task_snapshot() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = SOURCE_TASK_PATH.read_bytes()
    identity = _source_identity_from_payload(payload)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        rows.append(
            parse_json_object(line, label=f"{SOURCE_TASK_PATH}:{line_number}")
        )
    if len(rows) != identity["row_count"]:
        raise ValueError("source task snapshot row count changed during parsing")
    return rows, identity


def source_task_identity() -> dict[str, Any]:
    return _source_identity_from_payload(SOURCE_TASK_PATH.read_bytes())


def assert_frozen_inputs_unchanged(
    expected_source: Mapping[str, Any], expected_map: Mapping[str, Any]
) -> None:
    actual_source = source_task_identity()
    if actual_source != dict(expected_source):
        raise RuntimeError(
            "G4IRSF11 source task changed during the measurement cohort; "
            "all affected cases must be rerun"
        )
    actual_map = canonical_map_identity()
    if actual_map != dict(expected_map):
        raise RuntimeError(
            "G4IRSF11 canonical map changed during the measurement cohort; "
            "all affected cases must be rerun"
        )


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


def implementation_source_sha256() -> str:
    return source_bundle_sha256(IMPLEMENTATION_FILES, ROOT)


def _formal_case_set_sha256() -> str:
    return canonical_manifest_sha256(
        {"case_ids": [case.case_id for case in formal_cases()]}
    )


def _formal_producer(
    args: argparse.Namespace,
    *,
    implementation_digest: str,
    frozen_source_identity: Mapping[str, Any] | None = None,
    frozen_map_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_identity_value = dict(frozen_source_identity or source_task_identity())
    map_identity_value = dict(frozen_map_identity or canonical_map_identity())
    return {
        "schema": "czr005.g4irsf11.evidence_producer.v1",
        "scope": "formal",
        "protocol_version": PROTOCOL_VERSION,
        "protocol_manifest_sha256": canonical_manifest_sha256(
            _fixed_map_protocol_manifest()
        ),
        "fixed_real_map_only": True,
        "canonical_map_path": map_identity_value["repo_relative_path"],
        "canonical_map_sha256": map_identity_value["sha256"],
        "canonical_map_raw_bytes_sha256": map_identity_value["raw_bytes_sha256"],
        "topology_mutation_allowed": map_identity_value["topology_mutation_allowed"],
        "source_task_path": source_identity_value["path"],
        "source_task_raw_bytes_sha256": source_identity_value["raw_bytes_sha256"],
        "source_task_semantic_sha256": source_identity_value["semantic_sha256"],
        "source_task_row_count": source_identity_value["row_count"],
        "implementation_sha256": implementation_digest,
        "implementation_source_bundle_sha256": implementation_source_sha256(),
        "measurement_cohort": _measurement_cohort(args),
        "formal_case_set_sha256": _formal_case_set_sha256(),
        "expected_case_count": len(formal_cases()),
    }


def _formal_completion_metadata(
    args: argparse.Namespace,
    *,
    implementation_digest: str,
    executed_case_count: int,
    decision_artifacts_ready: bool,
    no_smoke_substitution_pass: bool,
    frozen_source_identity: Mapping[str, Any] | None = None,
    frozen_map_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_identity_value = dict(frozen_source_identity or source_task_identity())
    map_identity_value = dict(frozen_map_identity or canonical_map_identity())
    producer = _formal_producer(
        args,
        implementation_digest=implementation_digest,
        frozen_source_identity=source_identity_value,
        frozen_map_identity=map_identity_value,
    )
    return {
        "scope": "formal",
        "protocol_version": PROTOCOL_VERSION,
        "protocol_manifest_sha256": canonical_manifest_sha256(
            _fixed_map_protocol_manifest()
        ),
        "fixed_real_map_only": True,
        "canonical_map_sha256": map_identity_value["sha256"],
        "canonical_map_path": map_identity_value["repo_relative_path"],
        "canonical_map_raw_bytes_sha256": map_identity_value["raw_bytes_sha256"],
        "topology_mutation_allowed": map_identity_value["topology_mutation_allowed"],
        "source_task_path": source_identity_value["path"],
        "source_task_raw_bytes_sha256": source_identity_value["raw_bytes_sha256"],
        "source_task_semantic_sha256": source_identity_value["semantic_sha256"],
        "source_task_row_count": source_identity_value["row_count"],
        "implementation_sha256": implementation_digest,
        "implementation_source_bundle_sha256": implementation_source_sha256(),
        "measurement_cohort": _measurement_cohort(args),
        "concurrent_worker_target": int(args.concurrent_worker_target),
        "expected_case_count": len(formal_cases()),
        "executed_case_count": int(executed_case_count),
        "formal_case_set_sha256": _formal_case_set_sha256(),
        "decision_artifacts_ready": bool(decision_artifacts_ready),
        "no_smoke_substitution_pass": bool(no_smoke_substitution_pass),
        "producer": producer,
        "producer_sha256": canonical_manifest_sha256(producer),
    }


def formal_completion_validation_errors(root: Path = ROOT) -> list[str]:
    current_source_identity = source_task_identity()
    current_map_identity = canonical_map_identity()
    expected_metadata = {
        "protocol_version": PROTOCOL_VERSION,
        "fixed_real_map_only": True,
        "canonical_map_sha256": current_map_identity["sha256"],
        "canonical_map_path": current_map_identity["repo_relative_path"],
        "topology_mutation_allowed": current_map_identity["topology_mutation_allowed"],
        "source_task_path": current_source_identity["path"],
        "source_task_semantic_sha256": current_source_identity["semantic_sha256"],
        "source_task_row_count": current_source_identity["row_count"],
        "expected_case_count": len(formal_cases()),
        "executed_case_count": len(formal_cases()),
        "formal_case_set_sha256": _formal_case_set_sha256(),
        "decision_artifacts_ready": True,
        "no_smoke_substitution_pass": True,
    }
    completion_path = root / FORMAL_COMPLETION_PATH.relative_to(ROOT)
    errors = completion_validation_errors(
        root,
        completion_path,
        expected_scope="formal",
        expected_source_bundle_sha256=implementation_source_sha256(),
        expected_protocol_manifest_sha256=canonical_manifest_sha256(
            _fixed_map_protocol_manifest()
        ),
        expected_artifact_paths=FORMAL_PUBLICATION_ARTIFACTS,
        expected_metadata=expected_metadata,
    )
    protocol_path = root / PROTOCOL_PATH.relative_to(ROOT)
    try:
        published_protocol = read_json_object(protocol_path)
    except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
        errors.append(
            f"published formal protocol cannot be decoded: {type(exc).__name__}: {exc}"
        )
    else:
        if published_protocol != _fixed_map_protocol_manifest():
            errors.append("published formal protocol differs from the exact protocol")
    if completion_path.is_file():
        try:
            completion = read_json_object(completion_path)
        except (OSError, TypeError, ValueError):
            completion = {}
        runtime_digest = str(completion.get("implementation_sha256") or "")
        if len(runtime_digest) != 64 or any(
            character not in "0123456789abcdef" for character in runtime_digest
        ):
            errors.append("completion runtime implementation SHA-256 is invalid")
        for raw_key in (
            "canonical_map_raw_bytes_sha256",
            "source_task_raw_bytes_sha256",
        ):
            raw_digest = str(completion.get(raw_key) or "")
            if len(raw_digest) != 64 or any(
                character not in "0123456789abcdef" for character in raw_digest
            ):
                errors.append(f"completion {raw_key} is invalid")
        producer = (
            completion.get("producer")
            if isinstance(completion.get("producer"), Mapping)
            else {}
        )
        if producer.get("scope") != "formal":
            errors.append("completion producer scope is not formal")
        if completion.get("producer_sha256") != canonical_manifest_sha256(producer):
            errors.append("completion producer SHA-256 binding differs")
        for key in (
            "protocol_version",
            "protocol_manifest_sha256",
            "fixed_real_map_only",
            "canonical_map_path",
            "canonical_map_sha256",
            "canonical_map_raw_bytes_sha256",
            "topology_mutation_allowed",
            "source_task_path",
            "source_task_raw_bytes_sha256",
            "source_task_semantic_sha256",
            "source_task_row_count",
            "implementation_sha256",
            "implementation_source_bundle_sha256",
            "measurement_cohort",
            "formal_case_set_sha256",
            "expected_case_count",
        ):
            if producer.get(key) != completion.get(key):
                errors.append(f"completion producer field differs: {key}")
        cohort = completion.get("measurement_cohort")
        if not isinstance(cohort, Mapping) or not str(cohort.get("name") or "").strip():
            errors.append("completion measurement cohort is empty")
        try:
            worker_target = int(
                cohort.get("declared_concurrent_worker_target")
                if isinstance(cohort, Mapping)
                else 0
            )
        except (TypeError, ValueError):
            worker_target = 0
        if worker_target <= 0:
            errors.append("completion concurrent worker target is invalid")
        if completion.get("concurrent_worker_target") != worker_target:
            errors.append("completion top-level worker target differs from cohort")
    return errors


def assert_implementation_unchanged(expected: str, search_path: Path) -> None:
    actual = implementation_sha256(search_path)
    if actual != expected:
        raise RuntimeError(
            "G4IRSF11 implementation changed during the measurement cohort; "
            f"expected={expected}, actual={actual}. All affected cases must be rerun."
        )


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
    except FileNotFoundError:
        token["released"] = True
        return
    except (OSError, ValueError, json.JSONDecodeError):
        # Keep the token live so atexit (or an explicit retry) can try again.
        return
    if (
        current.get("pid") == token.get("pid")
        and current.get("nonce") == token.get("nonce")
    ):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            # Do not let one cleanup failure prevent later case/consolidation
            # locks from being released; retain this token for a retry.
            return
        token["released"] = True
        return
    # The path no longer names our lease.  Never unlink another owner.
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
    token: dict[str, Any] = {
        "descriptor": descriptor,
        "path": path,
        "pid": os.getpid(),
        "nonce": nonce,
        "released": False,
    }
    try:
        remaining = memoryview(payload)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError("short write while creating case lock")
            remaining = remaining[written:]
        os.fsync(descriptor)
        atexit.register(_release_case_lock, token)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        token["released"] = True
        raise
    return token


def _acquire_all_case_locks(
    cases: Sequence[CaseSpec], *, scope: str, wait_seconds: float
) -> list[dict[str, Any]] | None:
    """Hold a stable snapshot boundary against every execute-only writer."""

    deadline = time.monotonic() + max(0.0, wait_seconds)
    tokens: list[dict[str, Any]] = []
    try:
        for case in sorted(cases, key=lambda value: value.case_id):
            remaining = max(0.0, deadline - time.monotonic())
            token = _acquire_case_lock(
                _case_paths(case)["lock"],
                f"{scope}:{case.case_id}",
                wait_seconds=remaining,
            )
            if token is None:
                for acquired in reversed(tokens):
                    _release_case_lock(acquired)
                return None
            tokens.append(token)
    except BaseException:
        for acquired in reversed(tokens):
            _release_case_lock(acquired)
        raise
    return tokens


def _archive_existing_attempt(
    case: CaseSpec,
    paths: Mapping[str, Path],
    *,
    reason: str,
) -> None:
    """Archive stale/mismatched evidence while holding the exact case lock."""

    artifact_names = (
        "execution",
        "result",
        "trace",
        "outcomes",
        "tasks",
        "workload",
        "fault",
    )
    if not any(paths[name].is_file() for name in artifact_names):
        return
    try:
        execution = _read_json(paths["execution"]) if paths["execution"].is_file() else {}
    except (OSError, ValueError):
        execution = {"status": "CORRUPT_DESCRIPTOR"}
    try:
        result = _read_json(paths["result"]) if paths["result"].is_file() else {}
    except (OSError, ValueError):
        result = {}
    summary_value = result.get("summary")
    summary = summary_value if isinstance(summary_value, Mapping) else {}
    capacity_value = result.get("raw_bag_capacity_metrics")
    capacity = capacity_value if isinstance(capacity_value, Mapping) else {}
    sample_reasons: dict[str, int] = {}
    bag_sample_value = result.get("bag_sample")
    bag_sample = bag_sample_value if isinstance(bag_sample_value, list) else []
    for row in bag_sample:
        if not isinstance(row, Mapping):
            continue
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
    run_id = str(execution.get("run_id") or "legacy-no-run-id")
    run_token = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16]
    archive_token = f"{time.time_ns()}-{run_token}"
    archive_dir = paths["archive"] / archive_token
    archive_dir.mkdir(parents=True, exist_ok=False)
    archive_filenames = {
        "execution": "execution.json",
        "result": "result.json",
        "trace": "trace.json",
        "outcomes": "outcomes.jsonl",
        "tasks": "tasks.jsonl",
        "workload": "workload.jsonl",
        "fault": "fault.json",
    }
    artifact_evidence: dict[str, Any] = {}
    for name in artifact_names:
        path = paths[name]
        if path.is_file():
            artifact_evidence[name] = {
                "source_path": str(path.resolve()),
                "archived_path": str((archive_dir / archive_filenames[name]).resolve()),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
    compact["artifact_evidence"] = artifact_evidence
    compact["archive_transaction_status"] = "ARCHIVE_IN_PROGRESS"
    in_progress_path = archive_dir / "archive_in_progress.json"
    atomic_write_json(in_progress_path, compact)
    # Copy first and retain every active source until all archived bytes have
    # been rehashed.  A crash before the final manifest therefore leaves an
    # explicit IN_PROGRESS record and the original attempt remains recoverable.
    for name, evidence in artifact_evidence.items():
        source = paths[name]
        destination = archive_dir / archive_filenames[name]
        _atomic_copy_file(source, destination)
        if (
            sha256_file(destination) != evidence["sha256"]
            or destination.stat().st_size != evidence["size_bytes"]
        ):
            raise ValueError(f"archive copy verification failed for {name}")
    previous: list[dict[str, Any]] = []
    if paths["history"].is_file():
        try:
            for row in _read_jsonl_objects(paths["history"]):
                previous.append(dict(row))
        except (OSError, ValueError, json.JSONDecodeError):
            corrupt_history_sha256 = sha256_file(paths["history"])
            corrupt_history_size = paths["history"].stat().st_size
            corrupt_history_archive = archive_dir / "corrupt_prior_attempt_history.jsonl"
            _atomic_copy_file(paths["history"], corrupt_history_archive)
            if (
                sha256_file(corrupt_history_archive) != corrupt_history_sha256
                or corrupt_history_archive.stat().st_size != corrupt_history_size
            ):
                raise ValueError("corrupt prior history archive copy verification failed")
            previous.append(
                {
                    "archived_status": "CORRUPT_PRIOR_HISTORY_RETAINED_EXACTLY",
                    "archived_path": str(corrupt_history_archive.resolve()),
                    "sha256": corrupt_history_sha256,
                    "size_bytes": corrupt_history_size,
                }
            )
            compact["corrupt_prior_history_evidence"] = {
                "archived_path": str(corrupt_history_archive.resolve()),
                "sha256": corrupt_history_sha256,
                "size_bytes": corrupt_history_size,
            }
    complete = dict(compact)
    complete["archive_transaction_status"] = "COMPLETE"
    complete["archive_completed_unix_time"] = time.time()
    # Publish the commit point with one same-filesystem rename: first replace
    # the marker contents atomically with COMPLETE, then rename that single
    # file to its final name.  No instant can expose both marker names.
    atomic_write_json(in_progress_path, complete)
    os.replace(in_progress_path, archive_dir / "archive_manifest.json")
    previous.append(complete)
    atomic_write_jsonl(paths["history"], previous)
    # Only a fully published, rehashed and history-recorded archive may clear
    # active paths.  A history-write failure therefore retains every source.
    for name in artifact_evidence:
        paths[name].unlink(missing_ok=True)


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
    expected_args: argparse.Namespace | None = None,
    expected_workload_rows: Sequence[Mapping[str, Any]] | None = None,
    expected_fault_rows: Sequence[Mapping[str, Any]] | None = None,
) -> bool:
    manifest = _fixed_map_protocol_manifest(
        protocol_manifest_value,
        extension=protocol_version == EXTENSION_PROTOCOL_VERSION,
    )
    identity_matches = (
        descriptor.get("schema") == EXECUTION_DESCRIPTOR_SCHEMA
        and descriptor.get("protocol_version") == protocol_version
        and descriptor.get("protocol_manifest_sha256")
        == canonical_manifest_sha256(manifest)
        and descriptor.get("case") == case.as_dict()
        and descriptor.get("source_sha256") == source_sha256
        and descriptor.get("map_sha256") == map_sha256
        and descriptor.get("fixed_real_map_only") is True
        and (descriptor.get("map_identity") or {}).get("sha256")
        == CANONICAL_MAP_SHA256
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
        run_id = str(descriptor.get("run_id") or "")
        if expected_args is None:
            input_artifact = dict(descriptor.get("input_artifact") or {})
            fault_artifact = dict(descriptor.get("fault_artifact") or {})
            validation_workload_rows = workload_rows
            validation_fault_rows = [dict(row) for row in fault_payload]
            expected_config = dict(descriptor.get("config") or {})
            expected_cohort = dict(descriptor.get("measurement_cohort") or {})
            expected_argv = list(descriptor.get("normalized_argv") or [])
            expected_timeout = float(descriptor.get("parent_timeout_seconds"))
        else:
            if expected_workload_rows is None or expected_fault_rows is None:
                raise ValueError(
                    "current-cohort descriptor validation requires canonical workload/fault rows"
                )
            validation_workload_rows = [dict(row) for row in expected_workload_rows]
            validation_fault_rows = [dict(row) for row in expected_fault_rows]
            if workload_rows != validation_workload_rows:
                raise ValueError("retained workload differs from current canonical derivation")
            if fault_payload != validation_fault_rows:
                raise ValueError("retained fault rows differ from current canonical derivation")
            input_artifact = workload_binding(
                bundle_paths["workload"], validation_workload_rows
            )
            fault_artifact = fault_binding(bundle_paths["fault"], validation_fault_rows)
            expected_config = _worker_config(case, expected_args)
            expected_cohort = _measurement_cohort(expected_args)
            expected_argv = _worker_command(
                case,
                bundle_paths,
                expected_args,
                run_id=run_id,
                protocol_version=protocol_version,
                protocol_manifest_digest=canonical_manifest_sha256(manifest),
                input_artifact=input_artifact,
                fault_artifact=fault_artifact,
                source_sha256=source_sha256,
                map_sha256=map_sha256,
                implementation_digest=implementation_digest,
            )
            expected_timeout = float(expected_args.timeout_seconds)
        expectation = ResultExpectation(
            run_id=run_id,
            case=case.as_dict(),
            protocol_version=protocol_version,
            protocol_manifest_sha256=canonical_manifest_sha256(manifest),
            input_artifact=input_artifact,
            fault_artifact=fault_artifact,
            fault_rows=validation_fault_rows,
            map_sha256=map_sha256,
            source_sha256=source_sha256,
            implementation_sha256=implementation_digest,
            config=expected_config,
            measurement_cohort=expected_cohort,
        )
        return not _bundle_validation_errors(
            descriptor,
            result,
            expectation,
            case=case,
            paths=bundle_paths,
            normalized_argv=expected_argv,
            parent_timeout_seconds=expected_timeout,
            workload_rows=validation_workload_rows,
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


def _canonical_case_inputs(
    case: CaseSpec,
    base_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Rebuild the only workload/fault inputs valid for a protocol case."""

    workload = build_workload(base_rows, scale=case.scale, mode=case.workload_mode)
    workload = namespace_workload(workload, scenario=case.case_id, task_id_offset=0)
    if case.segment_limit is not None:
        workload = timeline_spanning_sample(workload, case.segment_limit)
    return workload, _fault_rows(case, workload)


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


def _trace_semantic_errors(
    case: CaseSpec,
    paths: Mapping[str, Path],
    result: Mapping[str, Any],
    workload_rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[str]:
    """Cross-bind external trace files to the validated worker result."""

    if not case.trace_complete:
        return []
    errors: list[str] = []
    try:
        trace_payload = _read_json(paths["trace"])
        outcomes = _read_jsonl_objects(paths["outcomes"])
        tasks = _read_jsonl_objects(paths["tasks"])
    except (OSError, ValueError, TypeError) as exc:
        return [f"trace semantic bundle could not be decoded: {exc}"]
    decisions_value = trace_payload.get("decision_trace")
    if not isinstance(decisions_value, list) or not all(
        isinstance(row, Mapping) for row in decisions_value
    ):
        return ["external trace decision_trace must be an array of objects"]
    decisions = [dict(row) for row in decisions_value]
    result_trace = result.get("trace")
    if not isinstance(result_trace, Mapping):
        return ["result trace metadata is missing for external trace binding"]
    for key, path_name in (
        ("trace_output", "trace"),
        ("outcome_output", "outcomes"),
        ("trace_task_output", "tasks"),
    ):
        try:
            declared = Path(str(result_trace.get(key) or "")).resolve()
        except (OSError, ValueError):
            errors.append(f"result {key} path is invalid")
            continue
        if declared != paths[path_name].resolve():
            errors.append(f"result {key} path differs from bound {path_name} artifact")
    if trace_payload.get("trace_context") != result_trace.get("trace_context"):
        errors.append("external trace context differs from result trace context")
    if trace_payload.get("summary") != result.get("summary"):
        errors.append("external trace summary differs from result summary")
    if result_trace.get("decision_rows_stored") != len(decisions):
        errors.append("external trace decision count differs from result")

    def identity(
        row: Mapping[str, Any], label: str, *, decision_row: bool
    ) -> tuple[str, int, str, int]:
        decision_id = row.get("decision_id")
        segment_id = row.get("segment_id")
        if (
            not isinstance(decision_id, str)
            or not decision_id.strip()
            or not isinstance(segment_id, str)
            or not segment_id.strip()
        ):
            raise ValueError(f"{label} has an empty decision/segment identity")
        task_id_value = row.get("task_id")
        if isinstance(task_id_value, bool) or not isinstance(task_id_value, int):
            raise ValueError(f"{label}.task_id must be an integer")
        task_id = task_id_value
        metadata = row.get("metadata") if decision_row else None
        if decision_row:
            if not isinstance(metadata, Mapping):
                raise ValueError(f"{label}.metadata must be an object")
            runtime_bag_value = metadata.get("runtime_bag_id")
        else:
            runtime_bag_value = row.get("runtime_bag_id")
        if isinstance(runtime_bag_value, bool) or not isinstance(
            runtime_bag_value, int
        ):
            raise ValueError(f"{label}.runtime_bag_id must be an integer")
        runtime_bag_id = runtime_bag_value
        if task_id < 0 or runtime_bag_id < 0:
            raise ValueError(f"{label} has a negative task/runtime bag identity")
        return decision_id, task_id, segment_id, runtime_bag_id

    def task_identity(row: Mapping[str, Any], label: str) -> tuple[int, str]:
        task_id = row.get("task_id")
        segment_id = row.get("segment_id")
        if isinstance(task_id, bool) or not isinstance(task_id, int):
            raise ValueError(f"{label}.task_id must be an integer")
        if task_id < 0 or not isinstance(segment_id, str) or not segment_id.strip():
            raise ValueError(f"{label} has an invalid task/segment identity")
        return task_id, segment_id

    try:
        decision_identities = [
            identity(row, f"decision[{index}]", decision_row=True)
            for index, row in enumerate(decisions)
        ]
        outcome_identities = [
            identity(row, f"outcome[{index}]", decision_row=False)
            for index, row in enumerate(outcomes)
        ]
        task_identities = [
            task_identity(row, f"task[{index}]")
            for index, row in enumerate(tasks)
        ]
    except (TypeError, ValueError) as exc:
        errors.append(f"trace identity decoding failed: {exc}")
        return sorted(set(errors))
    decision_ids = [identity_row[0] for identity_row in decision_identities]
    if len(set(decision_ids)) != len(decision_ids):
        errors.append("external trace decision_ids are not unique")
    if len(set(decision_identities)) != len(decision_identities):
        errors.append("external trace decision identities are not unique")
    if outcome_identities != decision_identities:
        errors.append("outcome decision identities/order differ from external trace")
    expected_task_identities = {
        (task_id, segment_id)
        for _, task_id, segment_id, _ in decision_identities
    }
    if len(set(task_identities)) != len(task_identities):
        errors.append("trace task identities are not unique")
    if set(task_identities) != expected_task_identities:
        errors.append("trace task identities differ from decision task identities")
    runtime_to_original: dict[int, tuple[int, str]] = {}
    original_to_runtime: dict[tuple[int, str], int] = {}
    for _, task_id, segment_id, runtime_bag_id in decision_identities:
        original = (task_id, segment_id)
        if runtime_bag_id in runtime_to_original and runtime_to_original[runtime_bag_id] != original:
            errors.append("runtime_bag_id aliases multiple original segments")
        if original in original_to_runtime and original_to_runtime[original] != runtime_bag_id:
            errors.append("original segment changes runtime_bag_id")
        runtime_to_original[runtime_bag_id] = original
        original_to_runtime[original] = runtime_bag_id
    if workload_rows is not None:
        expected_task_rows = [
            dict(row)
            for row in workload_rows
            if (int(row.get("task_id")), str(row.get("segment_id") or ""))
            in expected_task_identities
        ]
        try:
            task_bytes_equal = canonical_json_bytes(tasks) == canonical_json_bytes(
                expected_task_rows
            )
        except (TypeError, ValueError):
            task_bytes_equal = False
        if not task_bytes_equal:
            errors.append("trace task rows differ from canonical workload rows")
    return sorted(set(errors))


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
    errors.extend(_trace_semantic_errors(case, paths, result, workload_rows))
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
        manifest = _fixed_map_protocol_manifest(protocol_manifest_value)
        protocol_manifest_digest = canonical_manifest_sha256(manifest)
        workload, windows = _canonical_case_inputs(case, base_rows)
        input_artifact = workload_binding(paths["workload"], workload)
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
            for name in (
                "execution",
                "result",
                "trace",
                "outcomes",
                "tasks",
                "workload",
                "fault",
            )
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
            "map_identity": canonical_map_identity(),
            "fixed_real_map_only": True,
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
    expected_args: argparse.Namespace | None = None,
    base_rows: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if expected_args is not None and base_rows is None:
        raise ValueError(
            "formal consolidation requires current source rows for canonical input rebuild"
        )
    rows: list[dict[str, Any]] = []
    for case in cases:
        paths = _case_paths(case)
        execution: dict[str, Any] = {"status": "NOT_RUN", "blocker": "formal case not executed"}
        result: dict[str, Any] | None = None
        expected_workload_rows: list[dict[str, Any]] | None = None
        expected_fault_rows: list[dict[str, Any]] | None = None
        if expected_args is not None:
            try:
                expected_workload_rows, expected_fault_rows = _canonical_case_inputs(
                    case, base_rows or []
                )
            except (KeyError, TypeError, ValueError) as exc:
                execution = {
                    "status": "FAILED",
                    "return_code": "CANONICAL_INPUT_REBUILD_ERROR",
                    "blocker": (
                        "current source rows could not rebuild the protocol-defined workload/fault "
                        f"for consolidation ({type(exc).__name__}: {exc})"
                    ),
                }
                rows.append(case_row(case, None, execution))
                continue
        if paths["execution"].is_file():
            try:
                candidate = _read_json(paths["execution"])
            except (OSError, TypeError, ValueError) as exc:
                execution = {
                    "status": "FAILED",
                    "return_code": "DESCRIPTOR_DECODE_ERROR",
                    "blocker": (
                        "execution descriptor could not be decoded; the case evidence "
                        f"is not consolidatable ({type(exc).__name__})"
                    ),
                }
            else:
                if _descriptor_matches(
                    candidate,
                    case,
                    source_sha256=source_sha256,
                    map_sha256=map_sha256,
                    implementation_digest=implementation_digest,
                    expected_args=expected_args,
                    expected_workload_rows=expected_workload_rows,
                    expected_fault_rows=expected_fault_rows,
                ):
                    execution = candidate
                    try:
                        result = _read_json(paths["result"])
                    except (OSError, TypeError, ValueError) as exc:
                        execution = dict(candidate)
                        execution["claimed_execution_status"] = "EXECUTED"
                        execution["status"] = "FAILED"
                        execution["return_code"] = "RESULT_DECODE_ERROR"
                        execution["blocker"] = (
                            "validated result could not be decoded during consolidation; "
                            f"the case evidence is not reportable ({type(exc).__name__})"
                        )
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


def _write_tables_and_reports(
    rows: Sequence[Mapping[str, Any]], *, output_root: Path = ROOT
) -> list[dict[str, Any]]:
    write_csv(output_root / CASE_TABLE.relative_to(ROOT), rows)
    table_dir = output_root / "outputs" / "tables"
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
        "protocol_manifest_sha256", "map_sha256",
        "workload_segment_count", "raw_bag_count", "junction_count",
        "peak_active_bag_count", "runtime_thread_count", "peak_working_set_bytes",
        "cpp_internal_accounted_bytes", "peak_junction_local_state_accounted_bytes",
        "sum_final_junction_local_state_accounted_bytes",
        "max_junction_service_utilization", "bottleneck_node", "bottleneck_score",
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
    negative_fields = None if history_rows else [*rows[0], "attempt_ordinal"]
    write_csv(
        table_dir / "g4irsf11_event_runtime_negative_attempts.csv",
        history_rows,
        fieldnames=negative_fields,
    )
    write_reports(output_root, rows)
    write_claim_boundary(output_root, rows, gates)
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
    expected_args: argparse.Namespace | None = None,
    base_rows: Sequence[Mapping[str, Any]] | None = None,
    output_root: Path = ROOT,
    producer: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    trace_cases = [case for case in cases if case.category == "decision_trace"]
    if not trace_cases:
        return None
    if not all(_case_paths(case)["execution"].is_file() for case in trace_cases):
        return None
    try:
        executions = [_read_json(_case_paths(case)["execution"]) for case in trace_cases]
    except (OSError, TypeError, ValueError):
        # The case ledger already records the explicit descriptor blocker.  A
        # corrupt decision descriptor must suppress derived artifacts, not abort
        # consolidation after the ledger/report have been built.
        return None
    canonical_inputs: list[
        tuple[list[dict[str, Any]] | None, list[dict[str, Any]] | None]
    ] = []
    if expected_args is not None:
        if base_rows is None:
            return None
        try:
            canonical_inputs = [
                _canonical_case_inputs(case, base_rows) for case in trace_cases
            ]
        except (KeyError, TypeError, ValueError):
            return None
    else:
        canonical_inputs = [(None, None) for _ in trace_cases]
    if not all(
        _descriptor_matches(
            row,
            case,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
            expected_args=expected_args,
            expected_workload_rows=canonical[0],
            expected_fault_rows=canonical[1],
        )
        for row, case, canonical in zip(executions, trace_cases, canonical_inputs)
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
        output_root=output_root,
        publication_root=ROOT,
        producer=producer,
    )


def _formal_stage_validation_errors(
    rows: Sequence[Mapping[str, Any]],
    *,
    args: argparse.Namespace,
    implementation_digest: str,
    decision_manifest: Mapping[str, Any] | None,
    producer: Mapping[str, Any],
    stage_root: Path,
) -> list[str]:
    errors: list[str] = []
    cases = formal_cases()
    expected_ids = [case.case_id for case in cases]
    actual_ids = [str(row.get("case_id") or "") for row in rows]
    if actual_ids != expected_ids or len(set(actual_ids)) != len(actual_ids):
        errors.append("formal staged ledger case set/order is not exact")
    protocol_digest = canonical_manifest_sha256(_fixed_map_protocol_manifest())
    expected_cohort = _measurement_cohort(args)
    for row in rows:
        case_id = str(row.get("case_id") or "<missing>")
        if row.get("execution_status") != "EXECUTED":
            errors.append(f"formal staged case is not EXECUTED: {case_id}")
        if row.get("protocol_manifest_sha256") != protocol_digest:
            errors.append(f"formal staged case protocol differs: {case_id}")
        if row.get("map_sha256") != CANONICAL_MAP_SHA256:
            errors.append(f"formal staged case map differs: {case_id}")
        if row.get("implementation_sha256") != implementation_digest:
            errors.append(f"formal staged case implementation differs: {case_id}")
        if row.get("measurement_cohort") != expected_cohort["name"]:
            errors.append(f"formal staged case cohort differs: {case_id}")
        if row.get("declared_concurrent_worker_target") != expected_cohort[
            "declared_concurrent_worker_target"
        ]:
            errors.append(f"formal staged case worker target differs: {case_id}")
    if decision_manifest is None:
        errors.append("formal staged decision artifacts are not ready")
    elif decision_manifest.get("producer") != dict(producer):
        errors.append("formal staged decision manifest producer differs")
    try:
        from scripts.eval.validate_g4irsf11_committed_artifacts import (
            validate_committed_artifacts,
        )

        committed = validate_committed_artifacts(
            stage_root,
            canonical_map_path=MAP_PATH,
            require_completion=False,
        )
    except (OSError, TypeError, ValueError) as exc:
        errors.append(
            "formal staged committed-artifact validation raised: "
            f"{type(exc).__name__}: {exc}"
        )
    else:
        if committed.get("status") != "PASS":
            errors.extend(
                f"formal staged committed artifact: {failure}"
                for failure in committed.get("failures", [])
            )
    return errors


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

    assert_canonical_map(MAP_PATH)
    frozen_map_identity = canonical_map_identity()
    manifest = _fixed_map_protocol_manifest()
    base_rows, frozen_source_identity = load_source_task_snapshot()
    if len(base_rows) != 43_603:
        raise SystemExit(f"formal source task count must be 43603, got {len(base_rows)}")
    source_sha256 = str(frozen_source_identity["raw_bytes_sha256"])
    map_sha256 = CANONICAL_MAP_SHA256
    implementation_digest = implementation_sha256(args.search_path)

    def assert_measurement_identity_unchanged() -> None:
        assert_implementation_unchanged(implementation_digest, args.search_path)
        assert_frozen_inputs_unchanged(
            frozen_source_identity, frozen_map_identity
        )

    assert_measurement_identity_unchanged()

    failures = 0
    for index, case in enumerate(selected, start=1):
        assert_measurement_identity_unchanged()
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
        assert_measurement_identity_unchanged()
        if execution.get("status") != "EXECUTED":
            failures += 1
        print(
            f"[g4irsf11-event] {index}/{len(selected)} {execution.get('status')} {case.case_id}",
            flush=True,
        )

    if args.execute_only:
        assert_measurement_identity_unchanged()
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
    case_snapshot_locks: list[dict[str, Any]] = []
    stage_errors: list[str] = []
    try:
        acquired_case_locks = _acquire_all_case_locks(
            cases,
            scope="formal_consolidation_snapshot",
            wait_seconds=args.shared_lock_timeout_seconds,
        )
        if acquired_case_locks is None:
            raise SystemExit(
                "could not acquire every formal case lock within the shared timeout; "
                "no staged or published report was rewritten"
            )
        case_snapshot_locks = acquired_case_locks
        stage_root = create_staging_root(ROOT, "formal")
        assert_measurement_identity_unchanged()
        _write_json(stage_root / PROTOCOL_PATH.relative_to(ROOT), manifest)
        rows = _load_all_rows(
            cases,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
            expected_args=args,
            base_rows=base_rows,
        )
        gates = _write_tables_and_reports(rows, output_root=stage_root)
        producer = _formal_producer(
            args,
            implementation_digest=implementation_digest,
            frozen_source_identity=frozen_source_identity,
            frozen_map_identity=frozen_map_identity,
        )
        decision_manifest = _build_decision_artifacts(
            cases,
            source_sha256=source_sha256,
            map_sha256=map_sha256,
            implementation_digest=implementation_digest,
            expected_args=args,
            base_rows=base_rows,
            output_root=stage_root,
            producer=producer,
        )
        assert_measurement_identity_unchanged()
        executed_case_count = sum(
            row["execution_status"] == "EXECUTED" for row in rows
        )
        stage_errors.extend(
            _formal_stage_validation_errors(
                rows,
                args=args,
                implementation_digest=implementation_digest,
                decision_manifest=decision_manifest,
                producer=producer,
                stage_root=stage_root,
            )
        )
        try:
            staged_bindings = publication_artifact_bindings(
                stage_root, FORMAL_PUBLICATION_ARTIFACTS
            )
        except (FileNotFoundError, OSError, TypeError, ValueError) as exc:
            stage_errors.append(
                "formal staged publication binding failed: "
                f"{type(exc).__name__}: {exc}"
            )
            staged_bindings = {}
        complete = (
            not failures
            and not stage_errors
            and executed_case_count == len(rows) == len(cases)
            and decision_manifest is not None
        )
        final_metadata = _formal_completion_metadata(
            args,
            implementation_digest=implementation_digest,
            executed_case_count=executed_case_count,
            decision_artifacts_ready=decision_manifest is not None,
            no_smoke_substitution_pass=complete,
            frozen_source_identity=frozen_source_identity,
            frozen_map_identity=frozen_map_identity,
        )
        if complete:
            assert_measurement_identity_unchanged()
            transaction = begin_completion(
                FORMAL_COMPLETION_PATH,
                final_metadata,
                expected_bindings=staged_bindings,
            )
            promote_staged_artifacts(
                stage_root,
                ROOT,
                FORMAL_PUBLICATION_ARTIFACTS,
                staged_bindings,
            )
            assert_measurement_identity_unchanged()
            complete_publication(
                FORMAL_COMPLETION_PATH,
                final_metadata,
                root=ROOT,
                artifact_paths=FORMAL_PUBLICATION_ARTIFACTS,
                expected_bindings=staged_bindings,
                publication_id=str(transaction["publication_id"]),
            )
            try:
                assert_measurement_identity_unchanged()
            except Exception:
                begin_completion(
                    FORMAL_COMPLETION_PATH,
                    final_metadata,
                    expected_bindings=staged_bindings,
                )
                raise
    finally:
        for case_lock in reversed(case_snapshot_locks):
            _release_case_lock(case_lock)
        _release_case_lock(consolidation_lock)
    print(
        "[g4irsf11-event] summary",
        f"selected={len(selected)}",
        f"selected_failures={failures}",
        f"formal_executed={sum(row['execution_status'] == 'EXECUTED' for row in rows)}/{len(rows)}",
        f"runtime_gates_pass={sum(row['status'] == 'PASS' for row in gates)}/{len(gates)}",
        f"decision_manifest={'written' if decision_manifest else 'not_ready'}",
        flush=True,
    )
    for blocker in stage_errors:
        print(f"[g4irsf11-event] publication blocker: {blocker}", flush=True)
    if failures:
        return 2
    if not complete:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
