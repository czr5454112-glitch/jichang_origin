"""Fail-closed integrity gates for G4IRSF11.

This module deliberately does not generate research results.  It validates the
provenance and shape of results produced elsewhere.  The functions are kept
free of project-runtime imports so that the gate can run in a minimal CI job.
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
G4IRSF10_START_HEAD = "3ae9092ed0cfa0d5d75cfde1c35ae53c61a25d64"
G4IRSF10_PAPER_TASK_SHA256 = "abb03e6d6d46031bfb653fece7ade8a94d58a54e8142c53448704f800ec5d386"

PASS = "PASS"
FAIL = "FAIL"
EXECUTED = "EXECUTED"
BLOCKED = "BLOCKED"
PARTIAL_WITH_EXPLICIT_BLOCKER = "PARTIAL_WITH_EXPLICIT_BLOCKER"

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


DEFAULT_PAPER_SCENARIOS = frozenset(
    [f"paper_main_2_5_repeat_{index}" for index in range(1, 6)]
    + [f"speed_sweep_{speed}" for speed in ("1.5", "2.0", "2.5", "3.0")]
    + [
        f"dynamic_static_{speed}_{deviation}"
        for speed in ("1.5", "2.0", "2.5", "3.0")
        for deviation in (10, 20, 30)
    ]
    + [
        f"fault_16_{name}"
        for name in (
            "paper_fault_arc_1",
            "paper_fault_arc_2",
            "paper_fault_arc_3",
            "paper_fault_arc_4",
            "paper_fault_arc_5",
            "paper_fault_arc_6",
            "paper_fault_arc_7",
            "paper_fault_arc_8",
            "paper_fault_arcs_1_7",
            "paper_fault_arcs_2_4",
            "paper_fault_arcs_3_5",
            "paper_fault_arcs_4_5",
            "paper_fault_arcs_5_7",
            "paper_fault_arcs_2_4_6",
            "paper_fault_arcs_3_5_8",
            "paper_fault_arcs_4_6_7",
        )
    ]
)

DEFAULT_OPTIONAL_SCENARIOS = frozenset(
    {
        "high_flow_no_fault_16x",
        "high_flow_no_fault_32x_smoke",
        "rolling_2_day_1x",
        "rolling_7_day_1x_smoke",
    }
)


FORBIDDEN_RUNTIME_FIELD_PATTERNS = (
    "teacher_next",
    "teacher_path",
    "future_route",
    "future_schedule",
    "future_sipp",
    "full_cie_route",
    "full_route",
    "remaining_route",
    "route_suffix",
    "route_path",
    "planned_path",
    "path_history",
    "post_hoc",
    "goal_reached",
    "route_finish_time",
    "label_source",
)

FORBIDDEN_LINEAGE_ROLES = frozenset(
    {
        "future",
        "future_route",
        "teacher",
        "teacher_label",
        "label",
        "metadata_only",
        "offline_outcome",
        "post_hoc",
        "target",
    }
)

FORBIDDEN_AVAILABILITY = frozenset(
    {"after_decision", "after_route", "future", "offline_only", "post_hoc"}
)


@dataclass(frozen=True)
class GateCheck:
    """One binary gate result.  WARN is intentionally not representable."""

    name: str
    status: str
    details: tuple[str, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "details": list(self.details),
            "metrics": dict(self.metrics),
        }


def _check(
    name: str,
    violations: Iterable[str],
    *,
    metrics: Mapping[str, Any] | None = None,
) -> GateCheck:
    details = tuple(str(item) for item in violations if str(item))
    return GateCheck(
        name=name,
        status=PASS if not details else FAIL,
        details=details,
        metrics={} if metrics is None else metrics,
    )


@dataclass(frozen=True)
class CommandRecord:
    argv: tuple[str, ...]
    cwd: str
    return_code: int
    stdout: str
    stderr: str

    @property
    def executable_command(self) -> str:
        return subprocess.list2cmdline(list(self.argv))

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["argv"] = list(self.argv)
        payload["executable_command"] = self.executable_command
        return payload


def run_recorded_command(
    argv: Sequence[str],
    *,
    cwd: Path | str,
    timeout_seconds: float = 60.0,
) -> CommandRecord:
    """Run a command without a shell and retain its exact return code."""

    command = tuple(str(item) for item in argv)
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        return CommandRecord(
            argv=command,
            cwd=str(Path(cwd).resolve()),
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandRecord(
            argv=command,
            cwd=str(Path(cwd).resolve()),
            return_code=127 if isinstance(exc, OSError) else 124,
            stdout="",
            stderr=str(exc),
        )


@dataclass(frozen=True)
class GitProvenance:
    head: str
    base_head: str
    branch: str
    upstream: str
    remote_head: str
    base_is_ancestor_of_head: bool
    head_is_ancestor_of_remote: bool
    worktree_status: str
    protected_worktree_status: str
    protected_committed_diff: str
    commands: tuple[CommandRecord, ...] = ()


def _git_record(
    records: list[CommandRecord], repo: Path, args: Sequence[str]
) -> CommandRecord:
    record = run_recorded_command(("git", *args), cwd=repo)
    records.append(record)
    return record


def collect_git_provenance(
    repo: Path | str,
    *,
    base_head: str = G4IRSF10_START_HEAD,
    protected_paths: Sequence[str] = (
        "legacy",
        "data/processed/maps/map2.json",
        "data/processed/tasks/inputdata.jsonl",
    ),
) -> GitProvenance:
    """Collect local/remote/protected-file state and every command return code."""

    repo_path = Path(repo).resolve()
    records: list[CommandRecord] = []

    head_record = _git_record(records, repo_path, ("rev-parse", "HEAD"))
    branch_record = _git_record(records, repo_path, ("branch", "--show-current"))
    upstream_record = _git_record(
        records,
        repo_path,
        ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
    )
    upstream = upstream_record.stdout.strip() if upstream_record.return_code == 0 else ""
    remote_record = _git_record(records, repo_path, ("rev-parse", "@{u}"))
    base_relation = _git_record(
        records,
        repo_path,
        ("merge-base", "--is-ancestor", base_head, "HEAD"),
    )
    remote_relation = _git_record(
        records,
        repo_path,
        ("merge-base", "--is-ancestor", "HEAD", "@{u}"),
    )
    status_record = _git_record(
        records, repo_path, ("status", "--porcelain=v1", "--untracked-files=all")
    )
    protected_status = _git_record(
        records,
        repo_path,
        (
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *protected_paths,
        ),
    )
    protected_diff = _git_record(
        records,
        repo_path,
        ("diff", "--name-only", f"{base_head}..HEAD", "--", *protected_paths),
    )

    return GitProvenance(
        head=head_record.stdout.strip() if head_record.return_code == 0 else "",
        base_head=base_head,
        branch=branch_record.stdout.strip() if branch_record.return_code == 0 else "",
        upstream=upstream,
        remote_head=remote_record.stdout.strip() if remote_record.return_code == 0 else "",
        base_is_ancestor_of_head=base_relation.return_code == 0,
        head_is_ancestor_of_remote=remote_relation.return_code == 0,
        worktree_status=status_record.stdout.strip(),
        protected_worktree_status=protected_status.stdout.strip(),
        protected_committed_diff=protected_diff.stdout.strip(),
        commands=tuple(records),
    )


def audit_git_provenance(snapshot: GitProvenance) -> GateCheck:
    violations: list[str] = []
    if not _SHA1_RE.fullmatch(snapshot.head):
        violations.append("local HEAD is missing or is not a full SHA-1")
    if not _SHA1_RE.fullmatch(snapshot.base_head):
        violations.append("baseline HEAD is missing or is not a full SHA-1")
    if not snapshot.base_is_ancestor_of_head:
        violations.append("G4IRSF10 baseline is not an ancestor of local HEAD")
    if not snapshot.upstream:
        violations.append("upstream ref is missing")
    if not snapshot.branch:
        violations.append("current branch is missing")
    if not _SHA1_RE.fullmatch(snapshot.remote_head):
        violations.append("remote HEAD is missing or is not a full SHA-1")
    if not snapshot.head_is_ancestor_of_remote:
        violations.append(
            "local HEAD is not an ancestor of upstream; a non-empty unrelated or behind remote cannot pass"
        )
    if snapshot.worktree_status:
        violations.append("worktree is not clean")
    if snapshot.protected_worktree_status:
        violations.append("protected files have uncommitted changes")
    if snapshot.protected_committed_diff:
        violations.append("protected files differ from the G4IRSF10 baseline")

    command_argv = [command.argv for command in snapshot.commands]
    required_exact_commands = (
        ("git", "rev-parse", "HEAD"),
        ("git", "branch", "--show-current"),
        ("git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"),
        ("git", "rev-parse", "@{u}"),
        ("git", "merge-base", "--is-ancestor", snapshot.base_head, "HEAD"),
        ("git", "merge-base", "--is-ancestor", "HEAD", "@{u}"),
        ("git", "status", "--porcelain=v1", "--untracked-files=all"),
    )
    for required in required_exact_commands:
        if required not in command_argv:
            violations.append(f"required provenance command was not recorded: {subprocess.list2cmdline(required)}")
    if not any(
        argv[:4] == ("git", "status", "--porcelain=v1", "--untracked-files=all")
        and "--" in argv
        for argv in command_argv
    ):
        violations.append("protected-path git status command was not recorded")
    if not any(
        argv[:3] == ("git", "diff", "--name-only") and "--" in argv
        for argv in command_argv
    ):
        violations.append("protected-path baseline diff command was not recorded")
    for command in snapshot.commands:
        if command.return_code != 0:
            violations.append(
                f"provenance command returned {command.return_code}: {command.executable_command}"
            )

    return _check(
        "git_provenance_and_state_clean",
        violations,
        metrics={
            "head": snapshot.head,
            "remote_head": snapshot.remote_head,
            "base_is_ancestor_of_head": snapshot.base_is_ancestor_of_head,
            "head_is_ancestor_of_remote": snapshot.head_is_ancestor_of_remote,
            "recorded_command_count": len(snapshot.commands),
        },
    )


def audit_state_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    required_items: Iterable[str] = (),
) -> GateCheck:
    """Aggregate state rows strictly: every required row must be exactly PASS."""

    violations: list[str] = []
    if not rows:
        violations.append("state audit has no rows")
    names = [str(row.get("audit_item") or row.get("gate") or "") for row in rows]
    duplicates = sorted(name for name, count in Counter(names).items() if name and count > 1)
    if duplicates:
        violations.append(f"duplicate state rows: {duplicates}")
    missing = sorted(set(required_items) - set(names))
    if missing:
        violations.append(f"missing required state rows: {missing}")
    for index, row in enumerate(rows):
        status = str(row.get("status", "")).upper()
        if status != PASS:
            name = names[index] or f"row[{index}]"
            violations.append(f"{name} has status {status or '<missing>'}; only PASS is clean")
    return _check("state_clean", violations, metrics={"row_count": len(rows)})


@dataclass(frozen=True)
class PaperScenarioSpec:
    expected_hash_by_scenario: Mapping[str, str]
    expected_status_by_scenario: Mapping[str, str]

    @classmethod
    def single_hash(
        cls,
        expected_sha256: str,
        *,
        scenarios: Iterable[str] = DEFAULT_PAPER_SCENARIOS,
        expected_status: str = EXECUTED,
    ) -> "PaperScenarioSpec":
        names = tuple(str(name) for name in scenarios)
        return cls(
            expected_hash_by_scenario={name: expected_sha256 for name in names},
            expected_status_by_scenario={name: expected_status for name in names},
        )

    @property
    def scenarios(self) -> frozenset[str]:
        return frozenset(self.expected_hash_by_scenario)


def _execution_status(row: Mapping[str, Any]) -> str:
    return str(
        row.get("execution_status")
        or row.get("artifact_status")
        or row.get("status")
        or ""
    ).upper()


def audit_paper_scenarios(
    rows: Sequence[Mapping[str, Any]], spec: PaperScenarioSpec
) -> GateCheck:
    """Require the exact scenario set and exact per-row input hash/status."""

    violations: list[str] = []
    command_evidence: dict[str, dict[str, Any]] = {}
    scenario_counts = Counter(str(row.get("scenario", "")) for row in rows)
    duplicates = sorted(name for name, count in scenario_counts.items() if name and count > 1)
    if duplicates:
        violations.append(f"duplicate paper scenarios: {duplicates}")
    actual = frozenset(name for name in scenario_counts if name)
    missing = sorted(spec.scenarios - actual)
    unexpected = sorted(actual - spec.scenarios)
    if missing:
        violations.append(f"missing paper scenarios: {missing}")
    if unexpected:
        violations.append(f"unexpected paper scenarios: {unexpected}")
    if "" in scenario_counts:
        violations.append("paper row has no scenario")

    expected_status_names = frozenset(spec.expected_status_by_scenario)
    if expected_status_names != spec.scenarios:
        violations.append("paper status specification does not match hash specification")

    for row in rows:
        scenario = str(row.get("scenario", ""))
        if scenario not in spec.scenarios:
            continue
        expected_hash = str(spec.expected_hash_by_scenario[scenario]).lower()
        actual_hash = str(row.get("task_path_sha256") or row.get("input_sha256") or "").lower()
        if not _SHA256_RE.fullmatch(expected_hash):
            violations.append(f"{scenario}: expected hash specification is not SHA-256")
        if actual_hash != expected_hash:
            violations.append(f"{scenario}: input hash mismatch")
        status = _execution_status(row)
        expected_status = str(spec.expected_status_by_scenario.get(scenario, "")).upper()
        if status != expected_status:
            violations.append(
                f"{scenario}: status {status or '<missing>'} != {expected_status or '<missing>'}"
            )
        command = str(row.get("executable_command") or row.get("command") or "").strip()
        return_code = _int_or_none(row.get("return_code"))
        command_evidence[scenario] = {
            "executable_command": command,
            "return_code": return_code,
        }
        if not command:
            violations.append(f"{scenario}: executable command is missing")
        if return_code is None:
            violations.append(f"{scenario}: command return code is missing")
        elif expected_status == EXECUTED and return_code != 0:
            violations.append(f"{scenario}: executed command returned {return_code}, not 0")

    return _check(
        "paper_scenario_exact_set_hash_status",
        violations,
        metrics={
            "expected_count": len(spec.scenarios),
            "actual_count": len(rows),
            "command_evidence": command_evidence,
        },
    )


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def audit_optional_scenarios(
    rows: Sequence[Mapping[str, Any]], expected_scenarios: Iterable[str]
) -> GateCheck:
    """An optional scenario must be executed, or carry a reproducible blocker."""

    expected = frozenset(str(name) for name in expected_scenarios)
    scenario_counts = Counter(str(row.get("scenario", "")) for row in rows)
    violations: list[str] = []
    command_evidence: dict[str, dict[str, Any]] = {}
    if not expected:
        violations.append("no optional scenarios were declared")
    duplicates = sorted(name for name, count in scenario_counts.items() if name and count > 1)
    if duplicates:
        violations.append(f"duplicate optional scenarios: {duplicates}")
    missing = sorted(expected - set(scenario_counts))
    if missing:
        violations.append(f"missing optional scenarios: {missing}")

    for row in rows:
        scenario = str(row.get("scenario", ""))
        if scenario not in expected:
            continue
        status = _execution_status(row)
        command = str(row.get("executable_command") or row.get("command") or "").strip()
        return_code = _int_or_none(row.get("return_code"))
        command_evidence[scenario] = {
            "executable_command": command,
            "return_code": return_code,
        }
        if status == EXECUTED:
            artifact_hash = str(
                row.get("artifact_sha256") or row.get("task_path_sha256") or ""
            ).lower()
            if not _SHA256_RE.fullmatch(artifact_hash):
                violations.append(f"{scenario}: executed row lacks an artifact SHA-256")
            if not command:
                violations.append(f"{scenario}: executed row lacks its executable command")
            if return_code != 0:
                violations.append(f"{scenario}: executed command did not return 0")
        elif status in {BLOCKED, PARTIAL_WITH_EXPLICIT_BLOCKER}:
            reason = str(row.get("blocker_reason") or "").strip()
            if not reason:
                violations.append(f"{scenario}: blocker reason is missing")
            if not command:
                violations.append(f"{scenario}: blocker reproduction command is missing")
            if return_code is None or return_code == 0:
                violations.append(f"{scenario}: blocker must record a non-zero return code")
        else:
            violations.append(
                f"{scenario}: optional status {status or '<missing>'} is neither EXECUTED nor an explicit blocker"
            )

    return _check(
        "optional_executed_or_explicit_blocker",
        violations,
        metrics={
            "expected_count": len(expected),
            "row_count": len(rows),
            "command_evidence": command_evidence,
        },
    )


def _parsed(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(stripped)
        except (SyntaxError, ValueError):
            return stripped


def _truthy(value: Any) -> bool:
    parsed = _parsed(value)
    if isinstance(parsed, str):
        return parsed.strip().lower() not in {"", "0", "false", "none", "null", "[]", "{}"}
    return bool(parsed)


def _candidate_nodes(
    row: Mapping[str, Any], *, allow_graph_validated_alias: bool = False
) -> tuple[str, ...]:
    # G4IRSF10's candidate_next_nodes was a future path suffix.  The alias is
    # accepted only when the caller supplies graph adjacency and the gate can
    # prove that it is the exact outgoing set.
    raw = _parsed(row.get("true_outgoing_candidates"))
    if raw is None and allow_graph_validated_alias:
        raw = _parsed(row.get("candidate_next_nodes"))
    if isinstance(raw, Mapping):
        raw = raw.get("candidates") or raw.get("nodes")
    if not isinstance(raw, (list, tuple)):
        return ()
    nodes: list[str] = []
    for candidate in raw:
        if isinstance(candidate, Mapping):
            node = candidate.get("next_node", candidate.get("node"))
        else:
            node = candidate
        if node is not None and str(node) != "":
            nodes.append(str(node))
    return tuple(nodes)


def _selected_node(row: Mapping[str, Any]) -> str:
    if row.get("selected_next_node") is not None:
        selected = row.get("selected_next_node")
    elif row.get("selected_next") is not None:
        selected = row.get("selected_next")
    else:
        selected = row.get("selected_action")
    raw = _parsed(selected)
    if isinstance(raw, Mapping):
        raw = raw.get("next_node", raw.get("node"))
    return "" if raw is None else str(raw)


def _hard_reasons(row: Mapping[str, Any]) -> tuple[str, ...]:
    raw = _parsed(
        row.get("hard_reasons")
        or row.get("why_hard")
        or row.get("reason_bucket")
        or row.get("reason")
    )
    if isinstance(raw, str):
        return (raw.lower(),)
    if isinstance(raw, Mapping):
        return tuple(str(key).lower() for key, value in raw.items() if _truthy(value))
    if isinstance(raw, (list, tuple, set)):
        return tuple(str(item).lower() for item in raw)
    return ()


def _is_high_flow(row: Mapping[str, Any]) -> bool:
    scenario = str(row.get("scenario", "")).lower()
    scale = str(row.get("scale") or row.get("load_multiplier") or "").lower().rstrip("x")
    try:
        multiplier = float(scale)
    except ValueError:
        multiplier = 0.0
    return "high_flow" in scenario or multiplier > 1.0


def _is_fault(row: Mapping[str, Any], reasons: Sequence[str]) -> bool:
    bucket = str(row.get("fault_bucket") or "").strip().lower()
    bucket_is_active = bucket in {
        "fault_local_active",
        "local_fault_active",
        "active_fault",
        "fault_active",
    }
    normalized_reasons = {
        re.sub(r"[^a-z0-9]+", "_", str(reason).strip().lower()).strip("_")
        for reason in reasons
    }
    reason_is_active = bool(
        normalized_reasons
        & {"local_fault_state", "fault_local_active", "advertised_fault_active"}
    )
    snapshot = _parsed(row.get("local_snapshot", row.get("fault_snapshot")))
    snapshot_is_active = False
    if isinstance(snapshot, Mapping):
        try:
            snapshot_is_active = int(snapshot.get("faulted_outgoing_count", 0)) > 0
        except (TypeError, ValueError):
            snapshot_is_active = False
    return bucket_is_active or reason_is_active or _truthy(row.get("fault_active")) or snapshot_is_active


def _is_tail(row: Mapping[str, Any], reasons: Sequence[str]) -> bool:
    bucket = str(row.get("tail_bucket") or "").strip().lower()
    bucket_is_tail = any(token in bucket for token in ("p95", "p99", "tail")) and bucket not in {
        "no_tail",
        "not_tail",
        "body_or_unlabeled",
    }
    return bucket_is_tail or any(
        token in reason for reason in reasons for token in ("tail", "p95", "p99")
    )


def _normalized_repeat_scenario(scenario: str) -> str:
    # Collapse deterministic repeat IDs only.  A generic numeric suffix can be
    # semantically meaningful (for example paper_fault_arc_1 vs arc_2).
    return re.sub(r"_repeat_\d+$", "_repeat", scenario.lower())


def _decision_signature(
    row: Mapping[str, Any], *, candidate_nodes: Sequence[str] | None = None
) -> str:
    payload = {
        "scenario_family": _normalized_repeat_scenario(str(row.get("scenario", ""))),
        "task_id": str(row.get("task_id", "")),
        "segment_id": str(row.get("segment_id", "")),
        "decision_time": str(row.get("decision_time", row.get("event_time", ""))),
        "current_node": str(row.get("current_node", row.get("junction_node", ""))),
        "goal_node": str(row.get("goal_node", "")),
        "candidates": tuple(candidate_nodes) if candidate_nodes is not None else _candidate_nodes(row),
        "selected": _selected_node(row),
        "reasons": sorted(_hard_reasons(row)),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HardCasePolicy:
    minimum_rows: int = 3
    minimum_per_required_category: int = 1
    max_duplicate_fraction: float = 0.20
    max_single_scenario_family_fraction: float = 0.60
    require_graph_adjacency: bool = True

    def __post_init__(self) -> None:
        if self.minimum_rows < 3:
            raise ValueError("hard-case minimum_rows cannot weaken below 3")
        if self.minimum_per_required_category < 1:
            raise ValueError("hard-case category minimum cannot weaken below 1")
        if not 0.0 <= self.max_duplicate_fraction <= 0.20:
            raise ValueError("hard-case duplicate threshold must be within [0, 0.20]")
        if not 0.0 < self.max_single_scenario_family_fraction <= 0.60:
            raise ValueError("hard-case scenario-family threshold must be within (0, 0.60]")
        if not self.require_graph_adjacency:
            raise ValueError("graph adjacency validation cannot be disabled")


def audit_hard_case_coverage(
    rows: Sequence[Mapping[str, Any]],
    policy: HardCasePolicy = HardCasePolicy(),
    *,
    adjacency: Mapping[int, Sequence[int]] | None = None,
) -> GateCheck:
    """Audit stratified coverage, true candidate validity, and repeat bias."""

    violations: list[str] = []
    if len(rows) < policy.minimum_rows:
        violations.append(f"hard-case rows {len(rows)} < required {policy.minimum_rows}")
    if policy.require_graph_adjacency and adjacency is None:
        violations.append("graph adjacency is required to prove true outgoing candidate validity")

    category_counts = Counter({"high_flow": 0, "fault": 0, "tail": 0})
    signatures: list[str] = []
    scenario_families: Counter[str] = Counter()
    invalid_candidates = 0
    invalid_decision_semantics = 0

    for index, row in enumerate(rows):
        reasons = _hard_reasons(row)
        if _is_high_flow(row):
            category_counts["high_flow"] += 1
        if _is_fault(row, reasons):
            category_counts["fault"] += 1
        if _is_tail(row, reasons):
            category_counts["tail"] += 1

        candidates = _candidate_nodes(row, allow_graph_validated_alias=adjacency is not None)
        selected = _selected_node(row)
        explicit_validity = row.get("candidate_validity")
        candidate_valid = (
            bool(candidates)
            and len(candidates) == len(set(candidates))
            and bool(selected)
            and selected in candidates
            and (explicit_validity is None or _truthy(explicit_validity))
        )
        if adjacency is not None:
            current_value = row.get("current_node", row.get("junction_node"))
            try:
                current = int(current_value)
            except (TypeError, ValueError):
                current = None
            expected = () if current is None else tuple(str(node) for node in adjacency.get(current, ()))
            if current is None or current not in adjacency or set(candidates) != set(expected):
                candidate_valid = False
        records = _parsed(row.get("candidate_records"))
        record_nodes: tuple[str, ...] = ()
        record_scores: dict[str, float] = {}
        records_valid = isinstance(records, (list, tuple)) and bool(records)
        if records_valid:
            extracted: list[str] = []
            for record in records:
                if not isinstance(record, Mapping) or record.get("next_node") is None:
                    records_valid = False
                    break
                try:
                    score = float(record.get("model_score"))
                except (TypeError, ValueError):
                    records_valid = False
                    break
                if not math.isfinite(score) or not isinstance(record.get("features"), Mapping):
                    records_valid = False
                    break
                node = str(record["next_node"])
                extracted.append(node)
                record_scores[node] = score
            record_nodes = tuple(extracted)
        if not records_valid or record_nodes != candidates:
            candidate_valid = False
        if not candidate_valid:
            invalid_candidates += 1
            violations.append(
                f"hard-case row {index} has invalid/missing true outgoing candidates or selection"
            )

        model_prediction = str(row.get("model_prediction", ""))
        fallback_raw = row.get("fallback_selected_next")
        fallback = "" if fallback_raw is None or str(fallback_raw) == "" else str(fallback_raw)
        expected_disagreement = bool(fallback) and fallback != model_prediction
        reported_disagreement = row.get("model_fallback_disagreement")
        try:
            margin = float(row.get("model_margin"))
        except (TypeError, ValueError):
            margin = math.nan
        metadata = _parsed(row.get("metadata"))
        if not isinstance(metadata, Mapping):
            metadata = {}
        score_semantics = str(
            row.get("model_score_semantics") or metadata.get("model_score_semantics") or ""
        ).lower()
        score_semantics_valid = score_semantics == "lower_is_better_cost"
        score_consistent = False
        margin_consistent = False
        if records_valid and record_scores and model_prediction in record_scores:
            ordered_scores = sorted(record_scores.values())
            score_consistent = math.isclose(
                record_scores[model_prediction], ordered_scores[0], rel_tol=1e-12, abs_tol=1e-12
            )
            expected_margin = (
                ordered_scores[1] - ordered_scores[0] if len(ordered_scores) > 1 else 999.0
            )
            margin_consistent = math.isfinite(margin) and math.isclose(
                margin, expected_margin, rel_tol=1e-9, abs_tol=1e-9
            )
        decision_semantics_valid = (
            bool(model_prediction)
            and model_prediction in candidates
            and (not fallback or fallback in candidates)
            and reported_disagreement is not None
            and _truthy(reported_disagreement) == expected_disagreement
            and math.isfinite(margin)
            and margin >= 0.0
            and score_semantics_valid
            and score_consistent
            and margin_consistent
            and (row.get("full_astar_used") is None or not _truthy(row.get("full_astar_used")))
        )
        if not decision_semantics_valid:
            invalid_decision_semantics += 1
            violations.append(
                f"hard-case row {index} has invalid score direction/margin, disagreement, or full-A* evidence"
            )
        signatures.append(_decision_signature(row, candidate_nodes=candidates))
        scenario_families[_normalized_repeat_scenario(str(row.get("scenario", "")))] += 1

    for category in ("high_flow", "fault", "tail"):
        if category_counts[category] < policy.minimum_per_required_category:
            violations.append(
                f"hard-case category {category} has {category_counts[category]} rows; "
                f"requires {policy.minimum_per_required_category}"
            )

    duplicate_count = len(signatures) - len(set(signatures))
    duplicate_fraction = duplicate_count / len(signatures) if signatures else 1.0
    if duplicate_fraction > policy.max_duplicate_fraction:
        violations.append(
            f"decision duplicate fraction {duplicate_fraction:.6f} exceeds "
            f"{policy.max_duplicate_fraction:.6f}"
        )

    max_family_fraction = (
        max(scenario_families.values()) / len(rows) if rows and scenario_families else 1.0
    )
    if max_family_fraction > policy.max_single_scenario_family_fraction:
        violations.append(
            f"single scenario-family fraction {max_family_fraction:.6f} exceeds "
            f"{policy.max_single_scenario_family_fraction:.6f}"
        )

    return _check(
        "hard_case_stratified_coverage_and_validity",
        violations,
        metrics={
            "row_count": len(rows),
            "high_flow_count": category_counts["high_flow"],
            "fault_count": category_counts["fault"],
            "tail_count": category_counts["tail"],
            "invalid_candidate_count": invalid_candidates,
            "invalid_decision_semantics_count": invalid_decision_semantics,
            "duplicate_fraction": duplicate_fraction,
            "max_scenario_family_fraction": max_family_fraction,
            "graph_adjacency_supplied": adjacency is not None,
        },
    )


def _normalized_field_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _forbidden_field_reason(name: str) -> str | None:
    normalized = _normalized_field_name(name)
    for pattern in FORBIDDEN_RUNTIME_FIELD_PATTERNS:
        if pattern in normalized:
            return pattern
    return None


def audit_runtime_feature_lineage(
    runtime_features: Sequence[str],
    lineage: Mapping[str, Mapping[str, Any]],
    *,
    runtime_state_fields: Sequence[str] = (),
) -> GateCheck:
    """Trace every runtime field to decision-time/static leaves.

    A harmless-looking derived feature fails if any transitive source is a
    teacher, label, path history, post-hoc outcome, or future route/schedule.
    Unknown sources and cycles also fail closed.
    """

    violations: list[str] = []
    features = tuple(str(name) for name in runtime_features)
    state_fields = tuple(str(name) for name in runtime_state_fields)
    if not features:
        violations.append("runtime feature list is empty")
    if len(features) != len(set(features)):
        violations.append("runtime feature list contains duplicates")

    normalized_lineage: dict[str, Mapping[str, Any]] = {}
    original_names: dict[str, str] = {}
    for name, entry in lineage.items():
        normalized = _normalized_field_name(str(name))
        if normalized in normalized_lineage:
            violations.append(f"lineage has colliding field names for {normalized}")
        normalized_lineage[normalized] = entry
        original_names[normalized] = str(name)

    reported_paths: set[str] = set()

    def report(message: str) -> None:
        if message not in reported_paths:
            reported_paths.add(message)
            violations.append(message)

    def visit(root: str, current: str, path: tuple[str, ...]) -> None:
        normalized = _normalized_field_name(current)
        display_path = " -> ".join((*path, current))
        forbidden = _forbidden_field_reason(current)
        if forbidden:
            report(f"{root}: forbidden lineage dependency {display_path} ({forbidden})")
        if normalized in (_normalized_field_name(item) for item in path):
            report(f"{root}: cyclic lineage {display_path}")
            return
        entry = normalized_lineage.get(normalized)
        if entry is None:
            report(f"{root}: missing lineage entry for {current} via {display_path}")
            return
        role = _normalized_field_name(str(entry.get("role") or entry.get("kind") or ""))
        lineage_class = _normalized_field_name(str(entry.get("lineage") or ""))
        availability = _normalized_field_name(str(entry.get("availability") or ""))
        if role in FORBIDDEN_LINEAGE_ROLES:
            report(f"{root}: forbidden lineage role {role} via {display_path}")
        if lineage_class in {"label", "metadata"}:
            report(f"{root}: forbidden lineage class {lineage_class} via {display_path}")
        if availability in FORBIDDEN_AVAILABILITY:
            report(f"{root}: unavailable-at-decision field via {display_path} ({availability})")
        sources = _parsed(entry.get("sources", []))
        if sources is None:
            sources = []
        if isinstance(sources, str):
            sources = [sources]
        if not isinstance(sources, (list, tuple)):
            report(f"{root}: sources for {current} are not a list")
            return
        if not sources and not (role or entry.get("origin")):
            report(f"{root}: leaf {current} lacks role/origin provenance")
        for source in sources:
            visit(root, str(source), (*path, current))

    for name in (*features, *state_fields):
        forbidden = _forbidden_field_reason(name)
        if forbidden:
            report(f"{name}: forbidden runtime field ({forbidden})")
        visit(name, name, ())

    return _check(
        "runtime_feature_field_lineage_no_leakage",
        violations,
        metrics={
            "runtime_feature_count": len(features),
            "runtime_state_field_count": len(state_fields),
            "lineage_field_count": len(lineage),
        },
    )


def aggregate_gate(checks: Sequence[GateCheck]) -> GateCheck:
    """Overall PASS requires every component to be binary PASS."""

    violations = [f"{check.name}: {check.status}" for check in checks if not check.passed]
    if not checks:
        violations.append("no component gates were evaluated")
    return _check("g4irsf11_gate_integrity", violations, metrics={"check_count": len(checks)})


def read_csv_rows(path: Path | str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_graph_adjacency(path: Path | str) -> dict[int, tuple[int, ...]]:
    """Read either map2.json or a direct ``node -> outgoing`` JSON mapping."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    adjacency: dict[int, tuple[int, ...]] = {}
    if isinstance(payload, Mapping) and isinstance(payload.get("nodes"), list):
        for row in payload["nodes"]:
            if not isinstance(row, Mapping) or row.get("location") is None:
                raise ValueError("map node lacks location/outgoing fields")
            node = int(row["location"])
            outgoing = tuple(sorted(int(value) for value in row.get("outgoing", [])))
            if node in adjacency or len(outgoing) != len(set(outgoing)):
                raise ValueError(f"invalid or duplicate adjacency entry for node {node}")
            adjacency[node] = outgoing
    elif isinstance(payload, Mapping):
        for raw_node, raw_outgoing in payload.items():
            if not isinstance(raw_outgoing, (list, tuple)):
                raise ValueError(f"adjacency for node {raw_node} is not an array")
            node = int(raw_node)
            outgoing = tuple(sorted(int(value) for value in raw_outgoing))
            if node in adjacency or len(outgoing) != len(set(outgoing)):
                raise ValueError(f"invalid or duplicate adjacency entry for node {node}")
            adjacency[node] = outgoing
    else:
        raise ValueError("adjacency JSON must be a map object")
    if not adjacency:
        raise ValueError("adjacency is empty")
    return adjacency


def _evidence_path(repo: Path, value: Any, label: str) -> Path:
    if value is None or not str(value).strip():
        raise ValueError(f"{label} path is missing")
    candidate = Path(str(value))
    resolved = (repo / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    if not resolved.is_relative_to(repo):
        raise ValueError(f"{label} path escapes repository: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"{label} file does not exist: {resolved}")
    return resolved


def _mapping_section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = config.get(name)
    if not isinstance(section, Mapping):
        raise ValueError(f"full integrity config requires a {name} object")
    return section


def evaluate_integrity_config(
    repo: Path | str, config: Mapping[str, Any]
) -> list[GateCheck]:
    """Evaluate all non-Git gates declared by a full integrity config.

    All four sections are mandatory.  Missing evidence raises ``ValueError`` so
    a caller cannot accidentally turn a partial evaluation into an overall PASS.
    """

    repo_path = Path(repo).resolve()

    paper_config = _mapping_section(config, "paper")
    paper_rows = read_csv_rows(_evidence_path(repo_path, paper_config.get("csv"), "paper CSV"))
    raw_scenarios = paper_config.get("expected_scenarios", sorted(DEFAULT_PAPER_SCENARIOS))
    if not isinstance(raw_scenarios, (list, tuple)) or not raw_scenarios:
        raise ValueError("paper.expected_scenarios must be a non-empty array")
    scenarios = tuple(str(item) for item in raw_scenarios)
    if frozenset(scenarios) != DEFAULT_PAPER_SCENARIOS or len(scenarios) != len(
        DEFAULT_PAPER_SCENARIOS
    ):
        raise ValueError("full gate paper scenario specification must equal the frozen 37-row set")
    raw_hashes = paper_config.get("expected_hash_by_scenario")
    if raw_hashes is None:
        expected_hash = str(paper_config.get("expected_sha256") or "")
        hashes: Mapping[str, str] = {name: expected_hash for name in scenarios}
    elif isinstance(raw_hashes, Mapping):
        hashes = {str(key): str(value) for key, value in raw_hashes.items()}
    else:
        raise ValueError("paper.expected_hash_by_scenario must be an object")
    raw_statuses = paper_config.get("expected_status_by_scenario")
    if raw_statuses is None:
        expected_status = str(paper_config.get("expected_status") or EXECUTED)
        statuses: Mapping[str, str] = {name: expected_status for name in scenarios}
    elif isinstance(raw_statuses, Mapping):
        statuses = {str(key): str(value) for key, value in raw_statuses.items()}
    else:
        raise ValueError("paper.expected_status_by_scenario must be an object")
    if any(str(value).upper() != EXECUTED for value in statuses.values()):
        raise ValueError("all frozen paper scenarios must have expected status EXECUTED")
    if any(str(value).lower() != G4IRSF10_PAPER_TASK_SHA256 for value in hashes.values()):
        raise ValueError("paper input hash does not match the frozen G4IRSF10 source-queue artifact")
    paper_check = audit_paper_scenarios(
        paper_rows,
        PaperScenarioSpec(
            expected_hash_by_scenario=hashes,
            expected_status_by_scenario=statuses,
        ),
    )

    optional_config = _mapping_section(config, "optional")
    optional_rows = read_csv_rows(
        _evidence_path(repo_path, optional_config.get("csv"), "optional CSV")
    )
    optional_names = optional_config.get("expected_scenarios")
    if not isinstance(optional_names, (list, tuple)) or not optional_names:
        raise ValueError("optional.expected_scenarios must be a non-empty array")
    if not DEFAULT_OPTIONAL_SCENARIOS.issubset(map(str, optional_names)):
        raise ValueError("optional scenario specification omits a frozen G4IRSF11 boundary")
    optional_check = audit_optional_scenarios(optional_rows, map(str, optional_names))

    hard_config = _mapping_section(config, "hard_cases")
    hard_rows = read_csv_rows(
        _evidence_path(repo_path, hard_config.get("csv"), "hard-case CSV")
    )
    adjacency = read_graph_adjacency(
        _evidence_path(repo_path, hard_config.get("adjacency_json"), "adjacency JSON")
    )
    raw_policy = hard_config.get("policy", {})
    if not isinstance(raw_policy, Mapping):
        raise ValueError("hard_cases.policy must be an object")
    allowed_policy_fields = {
        "minimum_rows",
        "minimum_per_required_category",
        "max_duplicate_fraction",
        "max_single_scenario_family_fraction",
        "require_graph_adjacency",
    }
    unknown_policy = set(raw_policy) - allowed_policy_fields
    if unknown_policy:
        raise ValueError(f"unknown hard-case policy fields: {sorted(unknown_policy)}")
    hard_check = audit_hard_case_coverage(
        hard_rows,
        HardCasePolicy(**dict(raw_policy)),
        adjacency=adjacency,
    )

    lineage_config = _mapping_section(config, "lineage")
    if lineage_config.get("csv"):
        lineage_rows = read_csv_rows(
            _evidence_path(repo_path, lineage_config.get("csv"), "lineage CSV")
        )
        if not lineage_rows:
            raise ValueError("lineage CSV is empty")
        lineage_graph = {}
        runtime_features = []
        runtime_state_fields = []
        for row in lineage_rows:
            field_path = str(row.get("field_path") or "").strip()
            if not field_path:
                raise ValueError("lineage CSV row lacks field_path")
            if field_path in lineage_graph:
                raise ValueError(f"duplicate lineage field_path: {field_path}")
            entry = dict(row)
            entry["sources"] = _parsed(row.get("sources")) or []
            lineage_graph[field_path] = entry
            if _truthy(row.get("model_input_allowed")):
                runtime_features.append(field_path)
            if (
                str(row.get("lineage") or "").lower() == "runtime"
                and str(row.get("storage_boundary") or "").lower() == "decision_trace"
            ):
                runtime_state_fields.append(field_path)
    else:
        raise ValueError("full gate lineage section requires the complete machine-readable CSV")
    if not isinstance(runtime_features, list) or not isinstance(runtime_state_fields, list):
        raise ValueError("lineage runtime feature/state fields must be arrays")
    if not isinstance(lineage_graph, Mapping):
        raise ValueError("lineage evidence requires a lineage dependency object")
    lineage_check = audit_runtime_feature_lineage(
        [str(item) for item in runtime_features],
        lineage_graph,  # type: ignore[arg-type]
        runtime_state_fields=[str(item) for item in runtime_state_fields],
    )

    return [paper_check, optional_check, hard_check, lineage_check]


def write_integrity_report(
    path: Path | str,
    checks: Sequence[GateCheck],
    commands: Sequence[CommandRecord] = (),
) -> None:
    overall = aggregate_gate(checks)
    payload = {
        "schema": "czr005.g4irsf11.gate_integrity.v1",
        "overall_status": overall.status,
        "checks": [check.to_dict() for check in checks],
        "commands": [record.to_dict() for record in commands],
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect and audit fail-closed G4IRSF11 Git provenance."
    )
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--base-head", default=G4IRSF10_START_HEAD)
    parser.add_argument(
        "--config",
        type=Path,
        help="Full gate config with paper, optional, hard_cases, and lineage sections.",
    )
    parser.add_argument(
        "--provenance-only",
        action="store_true",
        help="Explicitly run only the Git/protected-file provenance sub-gate.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        # Keep the default in an ignored runtime directory.  Writing a new
        # tracked report after a clean-state snapshot would immediately make
        # that snapshot stale and recreate the G4IRSF10 provenance bug.
        default=ROOT / ".pytest_cache" / "g4irsf11" / "gate_integrity.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = collect_git_provenance(args.repo, base_head=args.base_head)
    checks = [audit_git_provenance(snapshot)]
    if args.config is not None and args.provenance_only:
        checks.append(
            _check("gate_cli_mode", ["--config and --provenance-only are mutually exclusive"])
        )
    elif args.config is not None:
        try:
            config = json.loads(args.config.read_text(encoding="utf-8"))
            if not isinstance(config, Mapping):
                raise ValueError("full integrity config must be a JSON object")
            checks.extend(evaluate_integrity_config(args.repo, config))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            checks.append(_check("full_integrity_evidence_config", [str(exc)]))
    elif not args.provenance_only:
        checks.append(
            _check(
                "full_integrity_evidence_config",
                ["full gate requires --config; use --provenance-only only for the named sub-gate"],
            )
        )
    overall = aggregate_gate(checks)
    write_integrity_report(args.output, checks, snapshot.commands)
    print(
        f"[g4irsf11-gate-integrity] status={overall.status} "
        f"commands={len(snapshot.commands)} output={args.output}",
        flush=True,
    )
    return 0 if overall.passed else 2


if __name__ == "__main__":
    sys.exit(main())
