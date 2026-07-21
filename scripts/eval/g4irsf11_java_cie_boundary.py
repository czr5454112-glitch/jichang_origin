"""Fail-closed G4IRSF11 Java/CIE baseline boundary audit.

This module does not execute Java and never substitutes a Python/C++ replay for
the original scheduler.  It inventories the historical G4IRSF5--G4IRSF10
attempts, verifies the read-only legacy lifecycle and external Java harness,
and decides whether an accepted *full* headless Java/CIE baseline exists.

The bounded 64-task Java ``ICS_PathFinding`` harness is retained as strong
first-N evidence.  It is not promoted to a 28,506-bag full baseline.  G4J is
always emitted as ``CLOSED``; opening it requires a separate explicit
paper-protocol decision outside this audit.
"""

from __future__ import annotations

from dataclasses import dataclass
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any, Iterable, Mapping, Sequence


PASS = "PASS"
FAIL = "FAIL"
PARTIAL = "PARTIAL_WITH_EXPLICIT_BLOCKER"
CLOSED = "CLOSED"
SCHEMA = "czr005.g4irsf11.java_cie_boundary.v1"
EXPECTED_RAW_BAGS = 28_506
EXPECTED_JAVA_SEGMENTS = 43_603
FULL_DRAIN_MAX_EPOCHS = 90_000
LEGACY_BASE_HEAD = "3ae9092ed0cfa0d5d75cfde1c35ae53c61a25d64"

ATTEMPT_FIELDS = (
    "source",
    "attempt",
    "reported_status",
    "classification",
    "runtime_identity",
    "is_real_java",
    "is_full_scope",
    "accepted_as_full_baseline",
    "command",
    "returncode",
    "evidence_sha256",
    "exclusion_reason",
)
GATE_FIELDS = ("criterion", "status", "observed", "required", "evidence")
INVENTORY_FIELDS = ("evidence_id", "path", "exists", "sha256", "row_count", "role")

_JAVA_COMMAND_RE = re.compile(r"(?:^|[\\/\s\"])(?:java|java\.exe)(?:\s|\")", re.IGNORECASE)
_JAVAC_COMMAND_RE = re.compile(r"(?:^|[\\/\s\"])(?:javac|javac\.exe)(?:\s|\")", re.IGNORECASE)
_CPP_PROXY_RE = re.compile(r"cpp|pybind|noastar|no_astar|static_astar", re.IGNORECASE)


@dataclass(frozen=True)
class BoundaryCheck:
    criterion: str
    status: str
    observed: str
    required: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "criterion": self.criterion,
            "status": self.status,
            "observed": self.observed,
            "required": self.required,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class LegacyStructureAudit:
    main_gui_coupled: bool
    main_calls_generate_tasks: bool
    main_calls_ics_path_finding: bool
    tasks_one_head_per_source_epoch: bool
    scheduler_has_saved_routes: bool
    scheduler_rebuilds_constrains: bool
    scheduler_has_unfinished_retry: bool
    harness_imports_legacy_scheduler: bool
    harness_is_non_gui: bool
    harness_runs_epoch_loop: bool
    harness_records_route_state: bool

    @property
    def external_harness_valid(self) -> bool:
        return all(
            (
                self.harness_imports_legacy_scheduler,
                self.harness_is_non_gui,
                self.harness_runs_epoch_loop,
                self.harness_records_route_state,
            )
        )

    def to_dict(self) -> dict[str, bool]:
        return dict(self.__dict__)


@dataclass(frozen=True)
class BoundaryAudit:
    status: str
    g4j_status: str
    attempts: tuple[dict[str, Any], ...]
    checks: tuple[BoundaryCheck, ...]
    inventory: tuple[dict[str, Any], ...]
    blockers: tuple[str, ...]
    structure: LegacyStructureAudit
    commands: Mapping[str, str]
    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class EvidencePaths:
    g4irsf10_attempts: Path
    g4irsf5_baselines: Path
    java_window_performance: Path
    java_scheduled_performance: Path
    java_probability_performance: Path
    java_acceptance_summary: Path
    source_queue: Path
    source_queue_evidence: Path
    legacy_main: Path
    legacy_tasks: Path
    legacy_scheduler: Path
    external_harness: Path
    external_runner: Path
    full_run_manifest: Path
    full_lifecycle_trace: Path


def default_paths(root: Path | str) -> EvidencePaths:
    repo = Path(root).resolve()
    return EvidencePaths(
        g4irsf10_attempts=repo / "outputs" / "tables" / "g4irsf10_java_baseline_attempts.csv",
        g4irsf5_baselines=repo / "outputs" / "tables" / "g4irsf5_baseline_protocol_results.csv",
        java_window_performance=repo / "outputs" / "tables" / "java_cpp_legacy_window_performance.csv",
        java_scheduled_performance=repo / "outputs" / "tables" / "java_cpp_legacy_scheduled_fault_window_performance.csv",
        java_probability_performance=repo / "outputs" / "tables" / "java_cpp_legacy_probability_extreme_window_performance.csv",
        java_acceptance_summary=repo / "outputs" / "tables" / "java_cpp_legacy_acceptance_summary.csv",
        source_queue=repo / "artifacts" / "tasks" / "g4irsf7" / "java_source_queue_one_per_epoch.jsonl",
        source_queue_evidence=repo / "outputs" / "tables" / "g4irsf7_java_source_queue_evidence.csv",
        legacy_main=repo / "legacy" / "jichang_origin_readonly" / "src" / "RUN" / "Main.java",
        legacy_tasks=repo / "legacy" / "jichang_origin_readonly" / "src" / "App" / "Tasks.java",
        legacy_scheduler=repo / "legacy" / "jichang_origin_readonly" / "src" / "App" / "ICS_PathFinding.java",
        external_harness=repo / "benchmarks" / "java" / "LegacyIcsNoFaultWindowBenchmark.java",
        external_runner=repo / "scripts" / "eval" / "run_java_cpp_legacy_window_performance.py",
        full_run_manifest=repo / "outputs" / "reports" / "g4irsf11_java_cie_full_run_manifest.json",
        full_lifecycle_trace=repo / "outputs" / "tables" / "g4irsf11_java_cie_full_lifecycle_trace.csv",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _row_count(path: Path) -> int:
    if path.suffix.lower() == ".csv":
        return len(read_csv(path))
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def evidence_inventory(root: Path, paths: EvidencePaths) -> tuple[dict[str, Any], ...]:
    roles = {
        "g4irsf10_attempts": "historical_java_attempts",
        "g4irsf5_baselines": "paper_and_proxy_boundary",
        "java_window_performance": "real_java_first_n_window",
        "java_scheduled_performance": "real_java_fault_window",
        "java_probability_performance": "real_java_probability_extreme_window",
        "java_acceptance_summary": "bounded_java_cpp_acceptance",
        "source_queue": "java_release_semantics_trace",
        "source_queue_evidence": "legacy_source_semantics_audit",
        "legacy_main": "read_only_gui_lifecycle",
        "legacy_tasks": "read_only_release_lifecycle",
        "legacy_scheduler": "read_only_cie_scheduler",
        "external_harness": "non_gui_java_wrapper",
        "external_runner": "orchestration_source",
        "full_run_manifest": "optional_future_full_java_acceptance",
        "full_lifecycle_trace": "optional_future_epoch_state_trace",
    }
    rows: list[dict[str, Any]] = []
    for evidence_id, path in paths.__dict__.items():
        exists = path.is_file()
        try:
            display = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            display = str(path.resolve())
        rows.append(
            {
                "evidence_id": evidence_id,
                "path": display,
                "exists": exists,
                "sha256": sha256_file(path) if exists else "",
                "row_count": _row_count(path) if exists and path.suffix.lower() in {".csv", ".jsonl"} else "",
                "role": roles[evidence_id],
            }
        )
    return tuple(rows)


def classify_historical_attempt(row: Mapping[str, Any]) -> tuple[str, str, bool, str]:
    """Return classification, runtime identity, is-real-Java, exclusion reason."""

    attempt = str(row.get("attempt") or row.get("baseline_id") or "").strip()
    command = str(row.get("command") or "").strip()
    status = str(row.get("status") or "").upper()
    lowered = attempt.lower()
    if (
        "run_original_project_run_main_headless" in lowered
        or "original_java_run_main_headless" in lowered
    ):
        return (
            "JAVA_GUI_FULL_ATTEMPT",
            "legacy_java_RUN.Main",
            True,
            "headless execution failed with the recorded GUI boundary" if status != PASS else "",
        )
    if "run_external_stub_gui_run_main" in lowered:
        return (
            "JAVA_STUB_GUI_ATTEMPT",
            "legacy_java_RUN.Main_with_external_gui_stub",
            True,
            "external GUI stub timed out and has no accepted full result" if status != PASS else "",
        )
    if "headless_astar_probe" in lowered or "temp_headless_java_astar" in lowered:
        return (
            "JAVA_STATIC_ASTAR_PROBE",
            "legacy_java_Astar.research",
            True,
            "static A* is not the Java/CIE event scheduler",
        )
    if lowered.startswith("compile_") or "dependency_inventory" in lowered:
        return (
            "JAVA_BUILD_OR_DEPENDENCY_EVIDENCE",
            "legacy_java_build",
            True,
            "compilation/dependency inventory is not a runtime baseline",
        )
    if "source_queue" in lowered or "semantic" in lowered:
        return (
            "JAVA_SOURCE_SEMANTICS_EVIDENCE",
            "legacy_java_source_audit",
            True,
            "source/semantic evidence is not a completed Java/CIE run",
        )
    if "g4j" in lowered:
        return ("G4J_BOUNDARY_RECORD", "claim_boundary", False, "G4J is recorded closed")
    if lowered.startswith("original_project_iot_drpa_text"):
        return (
            "ORIGINAL_PROJECT_RESULT_ARTIFACT",
            "original_project_flat_text",
            False,
            "parsed historical result text is not a fresh Java execution",
        )
    if "paper_" in lowered:
        return (
            "PAPER_REPORTED_RESULT",
            "paper_table",
            False,
            "paper-reported value has no executable Java runtime evidence",
        )
    if _CPP_PROXY_RE.search(lowered) or _CPP_PROXY_RE.search(command):
        return (
            "NON_JAVA_PROXY",
            "python_or_cpp_proxy",
            False,
            "Python/C++/static proxy cannot satisfy the Java baseline",
        )
    return (
        "UNCLASSIFIED_EVIDENCE",
        "unknown",
        bool(_JAVA_COMMAND_RE.search(command)),
        "unclassified evidence cannot pass a fail-closed Java baseline gate",
    )


def _attempt_row(
    source: str,
    row: Mapping[str, Any],
    evidence_sha256: str,
) -> dict[str, Any]:
    classification, identity, is_java, exclusion = classify_historical_attempt(row)
    return {
        "source": source,
        "attempt": str(row.get("attempt") or row.get("baseline_id") or ""),
        "reported_status": str(row.get("status") or ""),
        "classification": classification,
        "runtime_identity": identity,
        "is_real_java": is_java,
        "is_full_scope": False,
        "accepted_as_full_baseline": False,
        "command": str(row.get("command") or ""),
        "returncode": str(row.get("returncode") or ""),
        "evidence_sha256": evidence_sha256,
        "exclusion_reason": exclusion,
    }


def classify_window_row(
    row: Mapping[str, Any],
    *,
    source: str,
    evidence_sha256: str,
) -> dict[str, Any]:
    runtime = str(row.get("runtime") or "")
    is_java = runtime.startswith("legacy_java_ics_")
    try:
        generated = int(row.get("generated_count") or 0)
        completed = int(row.get("completed_count") or 0)
        active = int(row.get("active_route_count") or 0)
        unfinished = int(row.get("unfinished_count") or 0)
        max_new = int(row.get("max_new_tasks") or 0)
    except (TypeError, ValueError):
        generated = completed = active = unfinished = max_new = -1
    full_scope = (
        is_java
        and generated >= EXPECTED_JAVA_SEGMENTS
        and completed >= EXPECTED_RAW_BAGS
        and active == 0
        and unfinished == 0
        and (max_new == 0 or max_new >= EXPECTED_JAVA_SEGMENTS)
    )
    if not is_java:
        classification = "NON_JAVA_PROXY"
        exclusion = "C++/pybind row is parity evidence only, never Java runtime evidence"
        identity = "cpp_pybind_proxy"
    elif full_scope:
        classification = "JAVA_CIE_FULL_SCOPE_CANDIDATE"
        exclusion = "candidate still requires exact command/return code and lifecycle trace acceptance"
        identity = "legacy_java_ICS_PathFinding_external_headless"
    else:
        classification = "JAVA_CIE_BOUNDED_WINDOW"
        exclusion = (
            f"bounded window generated {generated}/{EXPECTED_JAVA_SEGMENTS} Java segments; "
            "accepted as first-N evidence, not full baseline"
        )
        identity = "legacy_java_ICS_PathFinding_external_headless"
    return {
        "source": source,
        "attempt": runtime,
        "reported_status": PASS,
        "classification": classification,
        "runtime_identity": identity,
        "is_real_java": is_java,
        "is_full_scope": full_scope,
        "accepted_as_full_baseline": False,
        "command": "",
        "returncode": "",
        "evidence_sha256": evidence_sha256,
        "exclusion_reason": exclusion,
    }


def audit_legacy_structure(paths: EvidencePaths) -> LegacyStructureAudit:
    main = paths.legacy_main.read_text(encoding="utf-8", errors="replace")
    tasks = paths.legacy_tasks.read_text(encoding="utf-8", errors="replace")
    scheduler = paths.legacy_scheduler.read_text(encoding="utf-8", errors="replace")
    harness = paths.external_harness.read_text(encoding="utf-8", errors="replace")
    return LegacyStructureAudit(
        main_gui_coupled="gui.showmap()" in main and "while (true)" in main,
        main_calls_generate_tasks="generate_tasks(" in main,
        main_calls_ics_path_finding="ICS_path_finding(" in main,
        tasks_one_head_per_source_epoch=(
            "task_List.get(ics_pf.getMap().star.get(i).getLocation()).get(0)" in tasks
            and "remove(0)" in tasks
            and "temptask.getPass_time() - epoch >= 1" in tasks
        ),
        scheduler_has_saved_routes="saved_routes" in scheduler,
        scheduler_rebuilds_constrains="constrains=newHashMap" in scheduler.replace(" ", ""),
        scheduler_has_unfinished_retry=(
            "unfinishTasks" in scheduler and "ICS.getUnfinishTasks().add(curTask)" in scheduler
        ),
        harness_imports_legacy_scheduler=(
            "import App.ICS_PathFinding;" in harness
            and "new ICS_PathFinding()" in harness
            and ".ICS_path_finding(" in harness
            and ".generate_tasks(" in harness
        ),
        harness_is_non_gui=(
            "System.setProperty(\"java.awt.headless\", \"true\")" in harness
            and ".showmap(" not in harness
            and "new JFrame" not in harness
        ),
        harness_runs_epoch_loop=(
            "for (int epochIndex = 0; epochIndex < maxEpochs; epochIndex++)" in harness
        ),
        harness_records_route_state=(
            "ics.getSaved_routes()" in harness
            and "writeRoutes(" in harness
            and "writeSummary(" in harness
        ),
    )


def protected_legacy_state(root: Path) -> tuple[bool, tuple[str, ...], tuple[dict[str, Any], ...]]:
    commands = (
        (
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            "legacy",
            "data/processed/maps/map2.json",
            "data/processed/tasks/inputdata.jsonl",
        ),
        (
            "git",
            "diff",
            "--name-only",
            f"{LEGACY_BASE_HEAD}..HEAD",
            "--",
            "legacy",
            "data/processed/maps/map2.json",
            "data/processed/tasks/inputdata.jsonl",
        ),
    )
    records: list[dict[str, Any]] = []
    changes: list[str] = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        output = completed.stdout.strip()
        records.append(
            {
                "command": subprocess.list2cmdline(list(command)),
                "returncode": completed.returncode,
                "stdout": output,
                "stderr": completed.stderr.strip(),
            }
        )
        if completed.returncode != 0:
            changes.append(f"command failed ({completed.returncode}): {records[-1]['command']}")
        if output:
            changes.extend(line for line in output.splitlines() if line.strip())
    return not changes, tuple(changes), tuple(records)


def _python_command(root: Path, *, full: bool) -> str:
    script = root / "scripts" / "eval" / "run_java_cpp_legacy_window_performance.py"
    python = Path(r"C:\Users\38908\.conda\envs\czr005\python.exe")
    max_epochs = FULL_DRAIN_MAX_EPOCHS if full else 5_000
    max_new = 0 if full else 64
    repeats = 1 if full else 3
    warmup = 0 if full else 1
    parts = [
        str(python),
        str(script),
        "--start-epoch",
        "8260",
        "--max-epochs",
        str(max_epochs),
        "--max-new-tasks",
        str(max_new),
        "--repeats",
        str(repeats),
        "--java-warmup-repeats",
        str(warmup),
        "--cpp-warmup-repeats",
        str(warmup),
        "--cpp-python-path",
        str(root / "build_vs" / "python" / "Release"),
    ]
    return subprocess.list2cmdline(parts)


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


FULL_RUN_SCHEMA = "czr005.g4irsf11.java_cie_full_run.v1"
FULL_TRACE_FIELDS = (
    "epoch",
    "source_queue_count",
    "released_count",
    "saved_routes_before",
    "saved_routes_after",
    "constrains_before",
    "constrains_after",
    "unfinished_before",
    "unfinished_after",
)
FULL_HASH_FIELDS = (
    "legacy_main",
    "legacy_tasks",
    "legacy_scheduler",
    "external_harness",
    "external_runner",
    "legacy_map",
    "legacy_inputdata",
    "source_queue",
)


def validate_full_run_manifest(
    manifest: Mapping[str, Any],
    trace_rows: Sequence[Mapping[str, Any]],
    *,
    actual_hashes: Mapping[str, str],
) -> tuple[str, ...]:
    """Validate a future full Java/CIE result without trusting its PASS label."""

    violations: list[str] = []
    if manifest.get("schema") != FULL_RUN_SCHEMA:
        violations.append(f"manifest schema must be {FULL_RUN_SCHEMA}")
    if manifest.get("status") != PASS:
        violations.append("manifest status is not PASS")
    if manifest.get("runtime_identity") != "legacy_java_ICS_PathFinding_external_headless":
        violations.append("runtime identity is not the external headless legacy Java scheduler")
    java_command = str(manifest.get("java_subprocess_command") or "").strip()
    javac_command = str(manifest.get("javac_subprocess_command") or "").strip()
    orchestration = str(manifest.get("orchestration_command") or "").strip()
    if not _JAVA_COMMAND_RE.search(java_command) or _CPP_PROXY_RE.search(java_command):
        violations.append("java_subprocess_command is missing or is not an exact Java command")
    if not _JAVAC_COMMAND_RE.search(javac_command):
        violations.append("javac_subprocess_command is missing or not javac")
    if not orchestration:
        violations.append("orchestration_command is missing")
    returncode = manifest.get("returncode")
    if isinstance(returncode, bool) or returncode != 0:
        violations.append("full Java subprocess returncode is not integer 0")

    scope = manifest.get("scope")
    if not isinstance(scope, Mapping):
        violations.append("scope object is missing")
        scope = {}
    required_exact = {
        "raw_bag_count": EXPECTED_RAW_BAGS,
        "java_segment_count": EXPECTED_JAVA_SEGMENTS,
        "generated_count": EXPECTED_JAVA_SEGMENTS,
        "planned_count": EXPECTED_JAVA_SEGMENTS,
        "completed_count": EXPECTED_JAVA_SEGMENTS,
        "active_route_count": 0,
        "unfinished_count": 0,
        "max_new_tasks": 0,
    }
    for name, expected in required_exact.items():
        value = scope.get(name)
        if isinstance(value, bool) or value != expected:
            violations.append(f"scope.{name} must equal {expected}, got {value!r}")
    epochs_run = scope.get("epochs_run")
    if isinstance(epochs_run, bool) or not isinstance(epochs_run, int) or epochs_run <= 0:
        violations.append("scope.epochs_run must be a positive integer")
        epochs_run = -1

    recorded_hashes = manifest.get("evidence_hashes")
    if not isinstance(recorded_hashes, Mapping):
        violations.append("evidence_hashes object is missing")
        recorded_hashes = {}
    for name in FULL_HASH_FIELDS:
        expected_hash = actual_hashes.get(name, "")
        recorded_hash = str(recorded_hashes.get(name) or "").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            violations.append(f"actual evidence hash unavailable for {name}")
        elif recorded_hash != expected_hash:
            violations.append(f"evidence hash mismatch for {name}")

    if not trace_rows:
        violations.append("full lifecycle trace is empty")
    if epochs_run > 0 and len(trace_rows) != epochs_run:
        violations.append(
            f"lifecycle trace rows {len(trace_rows)} != scope.epochs_run {epochs_run}"
        )
    epochs: list[float] = []
    numeric_rows: list[dict[str, int]] = []
    for index, row in enumerate(trace_rows):
        missing = [field for field in FULL_TRACE_FIELDS if row.get(field) in {None, ""}]
        if missing:
            violations.append(f"trace row {index} missing fields {missing}")
            continue
        try:
            epoch = float(row["epoch"])
            values = {field: int(row[field]) for field in FULL_TRACE_FIELDS[1:]}
        except (TypeError, ValueError):
            violations.append(f"trace row {index} contains non-numeric lifecycle values")
            continue
        if any(value < 0 for value in values.values()):
            violations.append(f"trace row {index} contains negative lifecycle values")
        epochs.append(epoch)
        numeric_rows.append(values)
    if epochs and (epochs != sorted(epochs) or len(epochs) != len(set(epochs))):
        violations.append("trace epochs are not strictly increasing and unique")
    if numeric_rows:
        first, last = numeric_rows[0], numeric_rows[-1]
        if first["source_queue_count"] != EXPECTED_JAVA_SEGMENTS:
            violations.append("trace does not begin with all Java source segments queued")
        if last["source_queue_count"] != 0:
            violations.append("trace does not drain the Java source queue")
        if last["saved_routes_after"] != 0:
            violations.append("trace ends with active saved_routes")
        if last["constrains_after"] != 0:
            violations.append("trace ends with active constrains")
        if last["unfinished_after"] != 0:
            violations.append("trace ends with unfinished tasks")
        if not any(row["saved_routes_before"] != row["saved_routes_after"] for row in numeric_rows):
            violations.append("trace has no saved_routes state change")
        if not any(row["constrains_before"] != row["constrains_after"] for row in numeric_rows):
            violations.append("trace has no constrains state change")
        released_total = sum(row["released_count"] for row in numeric_rows)
        if released_total != EXPECTED_JAVA_SEGMENTS:
            violations.append(
                f"trace released_count sum {released_total} != {EXPECTED_JAVA_SEGMENTS}"
            )
    return tuple(sorted(set(violations)))


def _optional_full_evidence(
    repo: Path,
    paths: EvidencePaths,
    inventory_by_id: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, bool, bool, dict[str, Any] | None, tuple[str, ...]]:
    """Return accepted, exact-manifest, lifecycle-trace, attempt row, violations."""

    if not paths.full_run_manifest.is_file():
        return False, False, False, None, ("full-run manifest is absent",)
    try:
        manifest = json.loads(paths.full_run_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, False, False, None, (f"full-run manifest cannot be read: {exc}",)
    if not isinstance(manifest, Mapping):
        return False, False, False, None, ("full-run manifest is not an object",)
    trace_descriptor = manifest.get("lifecycle_trace")
    trace_rows: list[dict[str, str]] = []
    trace_descriptor_valid = False
    trace_path = paths.full_lifecycle_trace
    if isinstance(trace_descriptor, Mapping):
        raw_path = Path(str(trace_descriptor.get("path") or ""))
        candidate = raw_path.resolve() if raw_path.is_absolute() else (repo / raw_path).resolve()
        expected_hash = str(trace_descriptor.get("sha256") or "").lower()
        expected_rows = trace_descriptor.get("row_count")
        if (
            candidate == trace_path.resolve()
            and candidate.is_relative_to(repo)
            and candidate.is_file()
            and re.fullmatch(r"[0-9a-f]{64}", expected_hash)
            and sha256_file(candidate) == expected_hash
        ):
            trace_rows = read_csv(candidate)
            trace_descriptor_valid = expected_rows == len(trace_rows)

    legacy_root = repo / "legacy" / "jichang_origin_readonly"
    hash_paths = {
        "legacy_main": paths.legacy_main,
        "legacy_tasks": paths.legacy_tasks,
        "legacy_scheduler": paths.legacy_scheduler,
        "external_harness": paths.external_harness,
        "external_runner": paths.external_runner,
        "legacy_map": legacy_root / "map2.txt",
        "legacy_inputdata": legacy_root / "inputdata.txt",
        "source_queue": paths.source_queue,
    }
    actual_hashes = {
        name: sha256_file(path) if path.is_file() else "" for name, path in hash_paths.items()
    }
    violations = list(
        validate_full_run_manifest(manifest, trace_rows, actual_hashes=actual_hashes)
    )
    if not trace_descriptor_valid:
        violations.append("lifecycle_trace descriptor path/hash/row_count mismatch")
    lifecycle_violations = [
        violation
        for violation in violations
        if "trace" in violation or "lifecycle" in violation
    ]
    manifest_violations = [
        violation for violation in violations if violation not in lifecycle_violations
    ]
    exact_manifest = not manifest_violations
    lifecycle_valid = not lifecycle_violations
    accepted = not violations
    scope = manifest.get("scope") if isinstance(manifest.get("scope"), Mapping) else {}
    attempt = {
        "source": "g4irsf11_java_cie_full_run_manifest",
        "attempt": "legacy_java_ics_full_headless",
        "reported_status": str(manifest.get("status") or ""),
        "classification": "JAVA_CIE_FULL_ACCEPTED" if accepted else "JAVA_CIE_FULL_REJECTED",
        "runtime_identity": str(manifest.get("runtime_identity") or ""),
        "is_real_java": str(manifest.get("runtime_identity") or "").startswith("legacy_java_"),
        "is_full_scope": (
            scope.get("generated_count") == EXPECTED_JAVA_SEGMENTS
            and scope.get("completed_count") == EXPECTED_JAVA_SEGMENTS
        ),
        "accepted_as_full_baseline": accepted,
        "command": str(manifest.get("java_subprocess_command") or ""),
        "returncode": str(manifest.get("returncode") if manifest.get("returncode") is not None else ""),
        "evidence_sha256": str(inventory_by_id["full_run_manifest"].get("sha256") or ""),
        "exclusion_reason": "" if accepted else "; ".join(sorted(set(violations))),
    }
    return accepted, exact_manifest, lifecycle_valid, attempt, tuple(sorted(set(violations)))


def audit_repository(root: Path | str) -> BoundaryAudit:
    repo = Path(root).resolve()
    paths = default_paths(repo)
    inventory = evidence_inventory(repo, paths)
    optional_evidence = {"full_run_manifest", "full_lifecycle_trace"}
    missing = [
        row["evidence_id"]
        for row in inventory
        if not row["exists"] and row["evidence_id"] not in optional_evidence
    ]
    blockers: list[str] = []
    attempts: list[dict[str, Any]] = []
    if missing:
        blockers.append(f"required Java boundary evidence missing: {missing}")

    inventory_by_id = {row["evidence_id"]: row for row in inventory}
    if paths.g4irsf10_attempts.is_file():
        for row in read_csv(paths.g4irsf10_attempts):
            attempts.append(
                _attempt_row(
                    "g4irsf10_java_baseline_attempts",
                    row,
                    str(inventory_by_id["g4irsf10_attempts"]["sha256"]),
                )
            )
    if paths.g4irsf5_baselines.is_file():
        for row in read_csv(paths.g4irsf5_baselines):
            attempts.append(
                _attempt_row(
                    "g4irsf5_baseline_protocol_results",
                    row,
                    str(inventory_by_id["g4irsf5_baselines"]["sha256"]),
                )
            )
    for evidence_id, path in (
        ("java_window_performance", paths.java_window_performance),
        ("java_scheduled_performance", paths.java_scheduled_performance),
        ("java_probability_performance", paths.java_probability_performance),
    ):
        if path.is_file():
            for row in read_csv(path):
                attempts.append(
                    classify_window_row(
                        row,
                        source=evidence_id,
                        evidence_sha256=str(inventory_by_id[evidence_id]["sha256"]),
                    )
                )

    required_structure_paths = (
        paths.legacy_main,
        paths.legacy_tasks,
        paths.legacy_scheduler,
        paths.external_harness,
    )
    if all(path.is_file() for path in required_structure_paths):
        structure = audit_legacy_structure(paths)
    else:
        structure = LegacyStructureAudit(*(False for _ in range(11)))
    protected_clean, protected_changes, git_records = protected_legacy_state(repo)

    (
        accepted_full_manifest,
        exact_full_manifest,
        lifecycle_trace,
        full_attempt,
        full_manifest_violations,
    ) = _optional_full_evidence(repo, paths, inventory_by_id)
    if full_attempt is not None:
        attempts.append(full_attempt)

    source_queue_rows = _row_count(paths.source_queue) if paths.source_queue.is_file() else 0
    java_windows = [row for row in attempts if row["classification"] == "JAVA_CIE_BOUNDED_WINDOW"]
    full_candidates = [row for row in attempts if bool(row["is_full_scope"])]
    gui_attempts = [row for row in attempts if row["classification"] == "JAVA_GUI_FULL_ATTEMPT"]
    stub_attempts = [row for row in attempts if row["classification"] == "JAVA_STUB_GUI_ATTEMPT"]
    accepted_full = bool(
        accepted_full_manifest and full_candidates and exact_full_manifest and lifecycle_trace
    )

    checks = [
        BoundaryCheck(
            "protected_legacy_map_input_clean",
            PASS if protected_clean else FAIL,
            "clean" if protected_clean else "; ".join(protected_changes),
            "no worktree or baseline diff under legacy/map/inputdata",
            " | ".join(str(row["command"]) for row in git_records),
        ),
        BoundaryCheck(
            "legacy_java_lifecycle_identified",
            PASS
            if all(
                (
                    structure.main_gui_coupled,
                    structure.main_calls_generate_tasks,
                    structure.main_calls_ics_path_finding,
                    structure.tasks_one_head_per_source_epoch,
                    structure.scheduler_has_saved_routes,
                    structure.scheduler_rebuilds_constrains,
                    structure.scheduler_has_unfinished_retry,
                )
            )
            else FAIL,
            json.dumps(structure.to_dict(), sort_keys=True),
            "GUI boundary plus Tasks.generate_tasks and ICS_PathFinding lifecycle present",
            "legacy RUN/Main.java, App/Tasks.java, App/ICS_PathFinding.java",
        ),
        BoundaryCheck(
            "external_non_gui_java_cie_wrapper",
            PASS if structure.external_harness_valid else FAIL,
            _bool_text(structure.external_harness_valid),
            "external Java class directly invokes read-only Tasks and ICS_PathFinding without showmap",
            "benchmarks/java/LegacyIcsNoFaultWindowBenchmark.java",
        ),
        BoundaryCheck(
            "java_source_queue_trace_complete",
            PASS if source_queue_rows == EXPECTED_JAVA_SEGMENTS else FAIL,
            str(source_queue_rows),
            str(EXPECTED_JAVA_SEGMENTS),
            "artifacts/tasks/g4irsf7/java_source_queue_one_per_epoch.jsonl",
        ),
        BoundaryCheck(
            "first_n_epoch_real_java_cie_evidence",
            PASS if java_windows else FAIL,
            f"{len(java_windows)} real Java windows; max generated="
            + str(
                max(
                    (
                        int(row["exclusion_reason"].split("generated ", 1)[1].split("/", 1)[0])
                        for row in java_windows
                    ),
                    default=0,
                )
            ),
            "at least one non-GUI external Java ICS_PathFinding first-N run",
            "outputs/tables/java_cpp_legacy_*_window_performance.csv",
        ),
        BoundaryCheck(
            "first_n_java_source_saved_routes_constrains_trace",
            PASS if lifecycle_trace else FAIL,
            (
                "accepted full lifecycle trace includes its first-N prefix"
                if lifecycle_trace
                else "source release trace exists; Java windows persist route/summary snapshots but not per-epoch constrains deltas"
            ),
            "first-N per-epoch source queue, saved_routes before/after, constrains before/after",
            "g4irsf7 source queue artifact + LegacyIcsNoFaultWindowBenchmark outputs",
        ),
        BoundaryCheck(
            "full_java_cie_scope",
            PASS if full_candidates else FAIL,
            f"full candidates={len(full_candidates)}; bounded Java windows={len(java_windows)}",
            f">={EXPECTED_JAVA_SEGMENTS} generated, >={EXPECTED_RAW_BAGS} completed, active=0, unfinished=0",
            "historical attempts and Java performance tables",
        ),
        BoundaryCheck(
            "full_java_source_saved_routes_constrains_trace",
            PASS if lifecycle_trace else FAIL,
            "no accepted per-epoch full-run saved_routes/constrains delta artifact",
            "source queue plus saved_routes/constrains before/after for first N and full run",
            "existing Java window outputs record routes/summary, not constraint deltas",
        ),
        BoundaryCheck(
            "full_java_exact_command_returncode_manifest",
            PASS if exact_full_manifest else FAIL,
            "missing",
            "exact javac/java or Java-orchestrating command, return code 0, hashes, full-scope counts",
            _python_command(repo, full=True),
        ),
        BoundaryCheck(
            "python_cpp_proxy_excluded_from_java_identity",
            PASS,
            "all cpp_pybind/static_astar/noastar rows are classified non-Java or lower-bound",
            "no Python/C++ proxy accepted as Java",
            "attempt classification audit",
        ),
        BoundaryCheck(
            "accepted_headless_java_cie_full_baseline",
            PASS if accepted_full else FAIL,
            _bool_text(accepted_full),
            "all full-scope, identity, command, trace, and protected-file checks PASS",
            "aggregate fail-closed gate",
        ),
        BoundaryCheck(
            "g4j_closed",
            PASS,
            CLOSED,
            CLOSED,
            "governance: G4J requires a separate accepted Java/CIE or paper-protocol boundary",
        ),
    ]

    if gui_attempts and not any(row["reported_status"] == PASS for row in gui_attempts):
        blockers.append("original RUN.Main headless full attempt remains blocked by Swing/HeadlessException")
    if stub_attempts and not any(row["reported_status"] == PASS for row in stub_attempts):
        blockers.append("external GUI-stub RUN.Main attempt timed out without an accepted result")
    if java_windows:
        blockers.append(
            "real external Java/CIE evidence is bounded to 64 generated tasks (first-N), not the full 28,506-bag stream"
        )
    if not full_candidates:
        blockers.append(
            f"no headless Java/CIE run covers {EXPECTED_RAW_BAGS} raw bags / {EXPECTED_JAVA_SEGMENTS} Java segments and drains active/unfinished state"
        )
    if not lifecycle_trace:
        blockers.append("no accepted first-N/full-run source queue + saved_routes + constrains delta trace")
    if not exact_full_manifest:
        blockers.append("no full-run manifest records exact command, return code 0, input/output hashes, and full-scope counts")
    if full_attempt is not None and full_manifest_violations:
        blockers.append(
            "full-run manifest rejected: " + "; ".join(full_manifest_violations)
        )
    if not protected_clean:
        blockers.append("legacy/map/inputdata protected state is not clean")

    status = PASS if accepted_full and protected_clean else PARTIAL
    metadata = {
        "schema": SCHEMA,
        "expected_raw_bags": EXPECTED_RAW_BAGS,
        "expected_java_segments": EXPECTED_JAVA_SEGMENTS,
        "accepted_full_baseline": accepted_full,
        "g4j_opened": False,
        "g4j_status": CLOSED,
        "legacy_protected_clean": protected_clean,
        "historical_attempt_count": len(attempts),
        "real_java_bounded_window_count": len(java_windows),
        "full_candidate_count": len(full_candidates),
        "git_commands": list(git_records),
    }
    return BoundaryAudit(
        status=status,
        g4j_status=CLOSED,
        attempts=tuple(attempts),
        checks=tuple(checks),
        inventory=inventory,
        blockers=tuple(sorted(set(blockers))),
        structure=structure,
        commands={
            "reproduce_first_n_java_cie": _python_command(repo, full=False),
            "required_full_java_cie_attempt": _python_command(repo, full=True),
        },
        metadata=metadata,
    )


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: (
                        json.dumps(row.get(field), sort_keys=True, separators=(",", ":"))
                        if isinstance(row.get(field), (dict, list, tuple))
                        else row.get(field)
                    )
                    for field in fields
                }
            )


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in row)
            + " |"
        )
    return "\n".join(lines)


def write_outputs(
    root: Path | str,
    audit: BoundaryAudit,
    *,
    attempt_table: Path,
    gate_table: Path,
    inventory_table: Path,
    report_path: Path,
    status_path: Path,
) -> None:
    repo = Path(root).resolve()
    _write_csv(attempt_table, audit.attempts, ATTEMPT_FIELDS)
    _write_csv(gate_table, (check.to_dict() for check in audit.checks), GATE_FIELDS)
    _write_csv(inventory_table, audit.inventory, INVENTORY_FIELDS)

    def relative(path: Path) -> str:
        try:
            return path.resolve().relative_to(repo).as_posix()
        except ValueError:
            return str(path.resolve())

    report_lines = [
        "# G4IRSF11 Java/CIE Boundary Audit",
        "",
        f"Boundary status: `{audit.status}`.",
        f"G4J: `{audit.g4j_status}` (opened=false).",
        "",
        "## Result",
        "",
        (
            "The repository contains a genuine non-GUI external Java wrapper that directly runs the "
            "read-only `Tasks.generate_tasks` and `ICS_PathFinding` lifecycle. Its accepted evidence is "
            "a bounded 64-task first-N window. It is not a full Java/CIE paper baseline, and Python/C++ "
            "parity/proxy rows are not counted as Java."
        ),
        "",
        "## Gates",
        "",
        _markdown_table(
            ("Criterion", "Status", "Observed", "Required"),
            tuple(
                (check.criterion, check.status, check.observed, check.required)
                for check in audit.checks
            ),
        ),
        "",
        "## Explicit blockers",
        "",
        *(f"- {blocker}" for blocker in audit.blockers),
        "",
        "## Exact reproduction commands",
        "",
        "First-N Java/CIE evidence (Python only orchestrates javac/java plus the separate C++ parity row):",
        "",
        f"```text\n{audit.commands['reproduce_first_n_java_cie']}\n```",
        "",
        "Required full attempt; this command is recorded but was not executed or accepted by this audit:",
        "",
        f"```text\n{audit.commands['required_full_java_cie_attempt']}\n```",
        "",
        "A future full result must additionally persist the Java subprocess command and return code, "
        "input/output hashes, all 43,603 Java release segments, drained active/unfinished state, and "
        "per-epoch source queue / saved_routes / constrains deltas. Merely running the command does not pass.",
        "",
        "## Evidence identity",
        "",
        _markdown_table(
            ("Classification", "Rows", "Accepted full"),
            tuple(
                (
                    classification,
                    sum(1 for row in audit.attempts if row["classification"] == classification),
                    sum(
                        1
                        for row in audit.attempts
                        if row["classification"] == classification
                        and row["accepted_as_full_baseline"]
                    ),
                )
                for classification in sorted(
                    {str(row["classification"]) for row in audit.attempts}
                )
            ),
        ),
        "",
        "## Artifacts",
        "",
        f"- attempts: `{relative(attempt_table)}`",
        f"- gates: `{relative(gate_table)}`",
        f"- evidence inventory with SHA-256: `{relative(inventory_table)}`",
        f"- machine status: `{relative(status_path)}`",
        "",
        "No legacy Java, real map, or real inputdata file is modified by this audit.",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    payload = {
        **dict(audit.metadata),
        "status": audit.status,
        "g4j_status": audit.g4j_status,
        "blockers": list(audit.blockers),
        "commands": dict(audit.commands),
        "structure": audit.structure.to_dict(),
        "checks": [check.to_dict() for check in audit.checks],
        "artifacts": {
            "attempt_table": {"path": relative(attempt_table), "sha256": sha256_file(attempt_table)},
            "gate_table": {"path": relative(gate_table), "sha256": sha256_file(gate_table)},
            "inventory_table": {"path": relative(inventory_table), "sha256": sha256_file(inventory_table)},
            "report": {"path": relative(report_path), "sha256": sha256_file(report_path)},
        },
        "claim_boundary": (
            "G4J remains closed. First-N real Java/CIE evidence is retained, but no Python/C++ proxy, "
            "static A* probe, parsed historical text, or timed-out GUI stub is a full Java baseline."
        ),
    }
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
