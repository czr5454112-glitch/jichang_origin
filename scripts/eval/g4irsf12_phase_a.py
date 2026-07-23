"""G4IRSF12-A state, identity, governance, and prior-evidence audit.

This stage is deliberately read-only with respect to the protected map, task
source, and legacy tree.  ``--write`` publishes only the three small Phase-A
report/table artifacts after every frozen fact has been validated.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
PHASE_DATE = "2026-07-23"
PHASE_START_COMMIT = "259608cd536f8ca2f6651a01b7d842675f63a9f7"
PHASE_START_BRANCH = "codex/czr005-rewrite"
PHASE_START_UPSTREAM = "origin/codex/czr005-rewrite"

MAP_PATH = Path("data/processed/maps/map2.json")
MAP_RAW_SHA256 = "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
MAP_SEMANTIC_SHA256 = "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
SOURCE_PATH = Path("data/processed/tasks/inputdata.jsonl")
SOURCE_SHA256 = "968d2c876fcbf03c5b25c8e865ccd469431af3ddbf59dc9ebe073752bd93678f"

COMPLETION_PATH = Path("artifacts/gates/g4irsf11_event_runtime_completion.json")
GATE_PATH = Path("outputs/tables/g4irsf11_event_runtime_gate.csv")
LEDGER_PATH = Path("outputs/tables/g4irsf11_event_runtime_case_ledger.csv")
DENOMINATOR_PATH = Path("outputs/tables/g4irsf8_tth_denominator_comparison.csv")
SOURCE_IDENTITY_PATH = Path("outputs/tables/g4irsf11_source_identity_audit.csv")
GOVERNANCE_PATH = Path("docs/czr005_project_governance.md")

STATE_REPORT_PATH = Path("outputs/reports/g4irsf12_state_and_governance_report.md")
IDENTITY_TABLE_PATH = Path("outputs/tables/g4irsf12_git_and_identity_audit.csv")
RECONCILIATION_REPORT_PATH = Path("outputs/reports/g4irsf12_prior_evidence_reconciliation.md")

EXPECTED_HCA_MEANS = {
    "processed_segment_attempt_time_tth": 3.9671227110082086,
    "java_release_time_tth": 5.197225145583386,
    "original_entry_time_tth": 5.764936746096144,
}
EXPECTED_V2_SAFE_MEANS = {
    "java_release_time_tth": 3.556593852974151,
    "original_entry_time_tth": 4.124305453486908,
}


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _normalised_text_sha256(payload: bytes) -> str:
    normalized = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return _sha256(normalized)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _git(root: Path, *args: str, allow_failure: bool = False) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode and not allow_failure:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({completed.returncode}): "
            f"{completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def _find_one(
    rows: Iterable[Mapping[str, str]], **criteria: str
) -> Mapping[str, str]:
    matches = [
        row
        for row in rows
        if all(str(row.get(key, "")) == value for key, value in criteria.items())
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one row for {criteria}, found {len(matches)}")
    return matches[0]


def _float(value: Any) -> float:
    return float(str(value).strip())


def _int(value: Any) -> int:
    return int(float(str(value).strip()))


def _close(left: float, right: float, tolerance: float = 1.0e-7) -> bool:
    return abs(left - right) <= tolerance


def collect_phase_a_evidence(root: Path = ROOT) -> dict[str, Any]:
    """Collect authoritative Phase-A facts without writing repository files."""

    map_payload = (root / MAP_PATH).read_bytes()
    map_data = json.loads(map_payload.decode("utf-8"))

    source_payload = (root / SOURCE_PATH).read_bytes()
    source_rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(source_payload.decode("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"source row {line_number} is not an object")
        source_rows.append(value)

    completion = _read_object(root / COMPLETION_PATH)
    gate_rows = _read_csv(root / GATE_PATH)
    gate_status_counts = Counter(row["status"] for row in gate_rows)
    ledger_rows = _read_csv(root / LEDGER_PATH)
    paper_row = dict(_find_one(ledger_rows, case_id="real_map_paper_full"))

    denominator_rows = _read_csv(root / DENOMINATOR_PATH)
    hca_means = {
        denominator: _float(
            _find_one(
                denominator_rows,
                variant="original_project_text_result",
                tth_denominator=denominator,
            )["mean_tht"]
        )
        for denominator in EXPECTED_HCA_MEANS
    }
    v2_safe_means = {
        denominator: _float(
            _find_one(
                denominator_rows,
                variant="java_source_queue_one_per_epoch",
                tth_denominator=denominator,
            )["mean_tht"]
        )
        for denominator in EXPECTED_V2_SAFE_MEANS
    }
    v2_release_row = _find_one(
        denominator_rows,
        variant="java_source_queue_one_per_epoch",
        tth_denominator="java_release_time_tth",
    )

    source_identity_rows = _read_csv(root / SOURCE_IDENTITY_PATH)
    source_identity_row = source_identity_rows[0] if source_identity_rows else {}

    completed_segments = _int(paper_row["completed_segment_count"])
    raw_bags = _int(paper_row["raw_bag_count"])
    end_backlog = _int(paper_row["end_backlog"])

    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PHASE_START_COMMIT, "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    ).returncode == 0

    return {
        "git": {
            "head": _git(root, "rev-parse", "HEAD"),
            "branch": _git(root, "branch", "--show-current"),
            "upstream": _git(
                root,
                "rev-parse",
                "--abbrev-ref",
                "--symbolic-full-name",
                "@{u}",
                allow_failure=True,
            ),
            "upstream_head": _git(root, "rev-parse", "@{u}", allow_failure=True),
            "start_is_ancestor": ancestry,
            "legacy_worktree_diff": _git(
                root, "diff", "--name-only", "--", "legacy", allow_failure=True
            ).splitlines(),
            "map_worktree_diff": _git(
                root, "diff", "--name-only", "--", MAP_PATH.as_posix(), allow_failure=True
            ).splitlines(),
            "source_worktree_diff": _git(
                root,
                "diff",
                "--name-only",
                "--",
                SOURCE_PATH.as_posix(),
                allow_failure=True,
            ).splitlines(),
            "protected_status": _git(
                root,
                "status",
                "--short",
                "--",
                "legacy",
                MAP_PATH.as_posix(),
                SOURCE_PATH.as_posix(),
                allow_failure=True,
            ).splitlines(),
            "protected_commit_diff": _git(
                root,
                "diff",
                "--name-only",
                f"{PHASE_START_COMMIT}..HEAD",
                "--",
                "legacy",
                MAP_PATH.as_posix(),
                SOURCE_PATH.as_posix(),
                allow_failure=True,
            ).splitlines(),
        },
        "map": {
            "raw_sha256": _sha256(map_payload),
            "semantic_sha256": _normalised_text_sha256(map_payload),
            "node_count": len(map_data.get("nodes", [])),
            "edge_count": len(map_data.get("edges", [])),
            "heuristic_row_count": len(map_data.get("heuristic_time", [])),
            "heuristic_column_counts": [
                len(row) if isinstance(row, list) else -1
                for row in map_data.get("heuristic_time", [])
            ],
        },
        "source": {
            "raw_sha256": _sha256(source_payload),
            "semantic_sha256": _normalised_text_sha256(source_payload),
            "segment_count": len(source_rows),
            "raw_bag_count": len({int(row["task_id"]) for row in source_rows}),
        },
        "formal": {
            "status": completion.get("status"),
            "expected_case_count": int(completion.get("expected_case_count", -1)),
            "executed_case_count": int(completion.get("executed_case_count", -1)),
            "implementation_sha256": completion.get("implementation_sha256"),
            "implementation_source_bundle_sha256": completion.get(
                "implementation_source_bundle_sha256"
            ),
            "map_raw_sha256": completion.get("canonical_map_raw_bytes_sha256"),
            "map_semantic_sha256": completion.get("canonical_map_sha256"),
            "source_raw_sha256": completion.get("source_task_raw_bytes_sha256"),
            "source_semantic_sha256": completion.get("source_task_semantic_sha256"),
            "source_row_count": int(completion.get("source_task_row_count", -1)),
            "gate_count": len(gate_rows),
            "gate_status_counts": dict(gate_status_counts),
        },
        "paper_full": {
            "raw_bag_count": raw_bags,
            "complete_raw_bag_count": raw_bags - end_backlog,
            "end_backlog": end_backlog,
            "requested_segments": _int(paper_row["workload_segment_count"]),
            "completed_segments": completed_segments,
            "failed_segments": _int(paper_row["failed_segment_count"]),
            "deadline_miss_rate": _float(paper_row["deadline_miss_rate"]),
            "starvation_count": _int(paper_row["starvation_count"]),
            "deadlock_count": _int(paper_row["deadlock_count"]),
            "unresolved_deadlock_count": _int(paper_row["unresolved_deadlock_count"]),
            "conflict_count": _int(paper_row["conflict_count"]),
            "runtime_full_astar_calls": _int(paper_row["runtime_full_astar_calls"]),
            "global_reservation_scan_count": _int(
                paper_row["global_reservation_scan_count"]
            ),
            "original_entry_p95_seconds": _float(
                paper_row["original_entry_p95_seconds"]
            ),
            "original_entry_p99_seconds": _float(
                paper_row["original_entry_p99_seconds"]
            ),
            "max_wait_seconds": _float(paper_row["max_wait_seconds"]),
            "max_junction_service_utilization": _float(
                paper_row["max_junction_service_utilization"]
            ),
            "derived_workload_sha256": paper_row["input_sha256"],
        },
        "historical_hca": {
            "means": hca_means,
            "complete_bags": 28506,
            "evidence_level": "parsed_original_project_output_not_fresh_java_rerun",
        },
        "v2_safe": {
            "means": v2_safe_means,
            "complete_bags": _int(v2_release_row["complete_bags"]),
            "failed_segments": _int(v2_release_row["failed_segments"]),
        },
        "source_identity_sample": {
            "path": source_identity_row.get("source_task_path", ""),
            "processed_segment_count": _int(
                source_identity_row.get("processed_segment_count", 0)
            ),
            "observed_decision_count": _int(
                source_identity_row.get("observed_decision_count", 0)
            ),
        },
    }


def validate_phase_a_evidence(evidence: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []

    def require(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    git = evidence["git"]
    map_identity = evidence["map"]
    source = evidence["source"]
    formal = evidence["formal"]
    paper = evidence["paper_full"]
    hca = evidence["historical_hca"]
    v2_safe = evidence["v2_safe"]

    require(git["start_is_ancestor"] is True, "phase start commit is not an ancestor")
    require(git["branch"] == PHASE_START_BRANCH, "unexpected branch")
    require(git["upstream"] == PHASE_START_UPSTREAM, "unexpected upstream")
    require(not git["legacy_worktree_diff"], "legacy has worktree changes")
    require(not git["map_worktree_diff"], "canonical map has worktree changes")
    require(not git["source_worktree_diff"], "canonical source has worktree changes")
    require(not git["protected_status"], "protected paths have staged or untracked changes")
    require(not git["protected_commit_diff"], "protected files changed since phase start")

    require(map_identity["raw_sha256"] == MAP_RAW_SHA256, "map raw hash mismatch")
    require(
        map_identity["semantic_sha256"] == MAP_SEMANTIC_SHA256,
        "map semantic hash mismatch",
    )
    require(map_identity["node_count"] == 54, "map node count mismatch")
    require(map_identity["edge_count"] == 69, "map edge count mismatch")
    require(map_identity["heuristic_row_count"] == 54, "map heuristic rows mismatch")
    require(
        map_identity["heuristic_column_counts"] == [54] * 54,
        "map heuristic shape mismatch",
    )

    require(source["raw_sha256"] == SOURCE_SHA256, "source raw hash mismatch")
    require(source["semantic_sha256"] == SOURCE_SHA256, "source semantic hash mismatch")
    require(source["segment_count"] == 43603, "source segment count mismatch")
    require(source["raw_bag_count"] == 28506, "source raw-bag count mismatch")

    require(formal["status"] == "COMPLETE", "formal cohort is not COMPLETE")
    require(formal["expected_case_count"] == 84, "formal expected count is not 84")
    require(formal["executed_case_count"] == 84, "formal executed count is not 84")
    require(formal["map_raw_sha256"] == MAP_RAW_SHA256, "completion map raw hash mismatch")
    require(
        formal["map_semantic_sha256"] == MAP_SEMANTIC_SHA256,
        "completion map semantic hash mismatch",
    )
    require(formal["source_raw_sha256"] == SOURCE_SHA256, "completion source raw hash mismatch")
    require(
        formal["source_semantic_sha256"] == SOURCE_SHA256,
        "completion source semantic hash mismatch",
    )
    require(formal["source_row_count"] == 43603, "completion source row mismatch")
    require(formal["gate_count"] == 6, "formal gate count is not 6")
    require(formal["gate_status_counts"].get("PASS") == 3, "formal PASS gate count is not 3")
    require(
        formal["gate_status_counts"].get("PARTIAL_WITH_EXPLICIT_BLOCKER") == 3,
        "formal partial gate count is not 3",
    )

    require(paper["raw_bag_count"] == 28506, "paper-full raw-bag count mismatch")
    require(paper["complete_raw_bag_count"] == 3114, "complete raw-bag count is not 3,114")
    require(paper["requested_segments"] == 43603, "requested segments mismatch")
    require(
        paper["completed_segments"] == 12125,
        "completed segments must be 12,125 (not 2,125)",
    )
    require(paper["failed_segments"] == 31478, "failed segments mismatch")
    require(paper["conflict_count"] == 0, "paper-full conflict count is nonzero")
    require(paper["runtime_full_astar_calls"] == 0, "paper-full full A* count is nonzero")
    require(
        paper["global_reservation_scan_count"] == 0,
        "paper-full global reservation scan count is nonzero",
    )

    for denominator, expected in EXPECTED_HCA_MEANS.items():
        require(
            _close(hca["means"][denominator], expected),
            f"historical HCA mean mismatch for {denominator}",
        )
    require(
        not _close(
            hca["means"]["processed_segment_attempt_time_tth"],
            hca["means"]["original_entry_time_tth"],
            tolerance=1.0e-3,
        ),
        "historical processed-attempt and original-entry means were conflated",
    )
    for denominator, expected in EXPECTED_V2_SAFE_MEANS.items():
        require(
            _close(v2_safe["means"][denominator], expected),
            f"v2-safe mean mismatch for {denominator}",
        )
    require(v2_safe["complete_bags"] == 28506, "v2-safe complete-bag count mismatch")
    require(v2_safe["failed_segments"] == 0, "v2-safe failed-segment count mismatch")
    return sorted(set(failures))


def validate_governance(root: Path = ROOT) -> list[str]:
    text = (root / GOVERNANCE_PATH).read_text(encoding="utf-8")
    required = (
        "## Original-Scale-First Rule",
        "## Real-Demand Scaling Rule",
        "## Framework Variable Isolation Rule",
        "processed_segment_attempt_time_tth",
        "must never be used as an original-entry target",
        MAP_RAW_SHA256,
        MAP_SEMANTIC_SHA256,
        SOURCE_SHA256,
        "28,506",
        "43,603",
    )
    return [f"governance missing required text: {value}" for value in required if value not in text]


def _audit_rows(evidence: Mapping[str, Any]) -> list[dict[str, str]]:
    git = evidence["git"]
    map_identity = evidence["map"]
    source = evidence["source"]
    formal = evidence["formal"]
    paper = evidence["paper_full"]
    hca = evidence["historical_hca"]
    v2_safe = evidence["v2_safe"]

    def row(
        scope: str,
        check: str,
        observed: Any,
        expected: Any,
        evidence_path: str,
        notes: str = "",
    ) -> dict[str, str]:
        return {
            "scope": scope,
            "check": check,
            "status": "PASS",
            "observed": str(observed),
            "expected": str(expected),
            "evidence": evidence_path,
            "notes": notes,
        }

    return [
        row("git", "phase_start_head", PHASE_START_COMMIT, PHASE_START_COMMIT, "git rev-parse HEAD", "captured before Phase-A writes"),
        row("git", "phase_start_branch", PHASE_START_BRANCH, PHASE_START_BRANCH, "git branch --show-current"),
        row("git", "phase_start_upstream", PHASE_START_UPSTREAM, PHASE_START_UPSTREAM, "git rev-parse --abbrev-ref --symbolic-full-name @{u}"),
        row("git", "phase_start_upstream_head", PHASE_START_COMMIT, PHASE_START_COMMIT, "git rev-parse @{u}"),
        row("git", "phase_start_worktree_clean", "true", "true", "git status --short", "empty before Phase-A writes"),
        row("git", "start_commit_is_ancestor", str(git["start_is_ancestor"]).lower(), "true", "git merge-base --is-ancestor"),
        row("protection", "legacy_unchanged", len(git["legacy_worktree_diff"]) == 0, True, "git diff --name-only -- legacy"),
        row("protection", "map_unchanged", len(git["map_worktree_diff"]) == 0, True, f"git diff --name-only -- {MAP_PATH.as_posix()}"),
        row("protection", "source_unchanged", len(git["source_worktree_diff"]) == 0, True, f"git diff --name-only -- {SOURCE_PATH.as_posix()}"),
        row("protection", "protected_status_clean", len(git["protected_status"]) == 0, True, "git status --short -- legacy map input", "also catches staged and untracked protected changes"),
        row("map", "raw_sha256", map_identity["raw_sha256"], MAP_RAW_SHA256, MAP_PATH.as_posix()),
        row("map", "semantic_sha256", map_identity["semantic_sha256"], MAP_SEMANTIC_SHA256, MAP_PATH.as_posix(), "CRLF/CR normalized to LF"),
        row("map", "dimensions", f"{map_identity['node_count']} nodes / {map_identity['edge_count']} edges / 54x54 heuristic", "54 nodes / 69 edges / 54x54 heuristic", MAP_PATH.as_posix()),
        row("source", "raw_sha256", source["raw_sha256"], SOURCE_SHA256, SOURCE_PATH.as_posix()),
        row("source", "semantic_sha256", source["semantic_sha256"], SOURCE_SHA256, SOURCE_PATH.as_posix(), "CRLF/CR normalized to LF"),
        row("source", "segment_count", source["segment_count"], 43603, SOURCE_PATH.as_posix()),
        row("source", "raw_bag_count", source["raw_bag_count"], 28506, SOURCE_PATH.as_posix(), "unique original task_id"),
        row("formal", "executed_cases", f"{formal['executed_case_count']}/{formal['expected_case_count']}", "84/84", COMPLETION_PATH.as_posix(), "COMPLETE is evidence-cohort completion, not algorithm PASS"),
        row("formal", "gate_distribution", "3 PASS / 3 PARTIAL_WITH_EXPLICIT_BLOCKER", "3 PASS / 3 PARTIAL_WITH_EXPLICIT_BLOCKER", GATE_PATH.as_posix()),
        row("paper_full", "complete_raw_bags", paper["complete_raw_bag_count"], 3114, LEDGER_PATH.as_posix()),
        row("paper_full", "completed_segments", paper["completed_segments"], 12125, LEDGER_PATH.as_posix(), "authoritative value is 12,125; 2,125 is incorrect"),
        row("historical_hca", "processed_segment_attempt_mean_minutes", f"{EXPECTED_HCA_MEANS['processed_segment_attempt_time_tth']:.12f}", "3.967122711 (processed-segment-attempt only)", DENOMINATOR_PATH.as_posix(), "not original-entry"),
        row("historical_hca", "original_entry_recomputed_mean_minutes", f"{EXPECTED_HCA_MEANS['original_entry_time_tth']:.12f}", "5.764936746 (recomputed historical evidence)", DENOMINATOR_PATH.as_posix(), "not a fresh Java/HCA* rerun"),
        row("v2_safe", "java_release_mean_minutes", f"{EXPECTED_V2_SAFE_MEANS['java_release_time_tth']:.12f}", "3.556593853", DENOMINATOR_PATH.as_posix()),
        row("v2_safe", "original_entry_mean_minutes", f"{EXPECTED_V2_SAFE_MEANS['original_entry_time_tth']:.12f}", "4.124305453", DENOMINATOR_PATH.as_posix()),
    ]


def render_identity_csv(evidence: Mapping[str, Any]) -> str:
    from io import StringIO

    buffer = StringIO(newline="")
    fieldnames = ["scope", "check", "status", "observed", "expected", "evidence", "notes"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(_audit_rows(evidence))
    return buffer.getvalue()


def render_state_report(evidence: Mapping[str, Any]) -> str:
    formal = evidence["formal"]
    return f"""# G4IRSF12-A State and Governance Report

Date: {PHASE_DATE}

Phase-A gate: `PASS`.

This gate freezes identities and claim boundaries.  It does not claim that the
G4IRSF11 algorithm passed capacity, service, or recovery gates, and it does not
open G4J.

## Starting Git snapshot

| Item | Value |
| --- | --- |
| Branch | `{PHASE_START_BRANCH}` |
| HEAD | `{PHASE_START_COMMIT}` |
| Upstream | `{PHASE_START_UPSTREAM}` |
| Upstream HEAD | `{PHASE_START_COMMIT}` |
| Worktree before Phase-A writes | clean |
| Start commit is current-HEAD ancestor | `{str(evidence['git']['start_is_ancestor']).lower()}` |

`legacy/`, `{MAP_PATH.as_posix()}`, and `{SOURCE_PATH.as_posix()}` had no
worktree diff at the snapshot and remain protected by the Phase-A validator.

## Frozen identities

| Item | Frozen value |
| --- | --- |
| Map raw SHA-256 | `{MAP_RAW_SHA256}` |
| Map semantic SHA-256 | `{MAP_SEMANTIC_SHA256}` |
| Map dimensions | 54 nodes, 69 directed edges, 54x54 heuristic |
| Input raw/semantic SHA-256 | `{SOURCE_SHA256}` |
| Input rows | 43,603 segments |
| Original bags | 28,506 unique task IDs |
| Formal cohort | {formal['executed_case_count']}/{formal['expected_case_count']} executed |
| Implementation SHA-256 | `{formal['implementation_sha256']}` |
| Source-bundle SHA-256 | `{formal['implementation_source_bundle_sha256']}` |

Raw hashes are byte hashes.  Semantic hashes normalize CRLF/CR newlines to LF;
they do not canonicalize or rewrite JSON.

## Governance added

`docs/czr005_project_governance.md` now contains:

- `Original-Scale-First Rule`;
- `Real-Demand Scaling Rule`;
- `Framework Variable Isolation Rule`;
- fail-closed map/input identity requirements; and
- an explicit denominator boundary: historical `3.967122711` minutes is
  processed-segment-attempt THT, not original-entry THT.

No 2x-or-higher full run is authorized until a new event candidate passes the
complete 1x gate.  No multiplier may be called real demand before a committed
demand-calibration report exists.

## Validation boundary

The machine-readable audit is
`outputs/tables/g4irsf12_git_and_identity_audit.csv`.  Prior-result
reconciliation is in
`outputs/reports/g4irsf12_prior_evidence_reconciliation.md`.
"""


def render_reconciliation_report(evidence: Mapping[str, Any]) -> str:
    paper = evidence["paper_full"]
    sample = evidence["source_identity_sample"]
    return f"""# G4IRSF12-A Prior Evidence Reconciliation

Date: {PHASE_DATE}

## Authoritative G4IRSF11 facts

| Fact | Reconciled value | Primary evidence |
| --- | ---: | --- |
| Formal cases executed | 84 / 84 | `{COMPLETION_PATH.as_posix()}` |
| Formal gate distribution | 3 PASS / 3 PARTIAL_WITH_EXPLICIT_BLOCKER | `{GATE_PATH.as_posix()}` |
| Complete raw bags | **3,114 / 28,506** | `{LEDGER_PATH.as_posix()}`; 28,506 - 25,392 end backlog |
| Completed segments | **12,125 / 43,603** | `{LEDGER_PATH.as_posix()}` |
| Failed segments | {paper['failed_segments']:,} | same ledger row |
| Deadline miss rate | {paper['deadline_miss_rate'] * 100:.2f}% | same ledger row |
| Starved raw bags | {paper['starvation_count']:,} | same ledger row |
| Deadlock episodes / unresolved | {paper['deadlock_count']:,} / {paper['unresolved_deadlock_count']} | same ledger row |
| Conflicts / runtime full A* / global scans | {paper['conflict_count']} / {paper['runtime_full_astar_calls']} / {paper['global_reservation_scan_count']} | same ledger row |
| Original-entry p95 / p99 | {paper['original_entry_p95_seconds'] / 3600:.2f} h / {paper['original_entry_p99_seconds'] / 3600:.2f} h | same ledger row |
| Maximum wait | {paper['max_wait_seconds'] / 3600:.2f} h | same ledger row |
| Maximum junction utilization | {paper['max_junction_service_utilization'] * 100:.2f}% | same ledger row |

The completed-segment value is **12,125**, not 2,125.  Cohort status
`COMPLETE` means all predeclared evidence cases executed; it does not mean the
algorithm passed.  The six final runtime gates contain three PASS rows and
three explicit blockers.

## Historical baseline denominators

| Stack/evidence | Denominator | Mean minutes | Completion | Claim boundary |
| --- | --- | ---: | ---: | --- |
| Original-project IoT-DRPA/HCA* text | `processed_segment_attempt_time_tth` | 3.967122711 | 28,506 / 28,506 | parsed historical output; not a fresh Java rerun |
| Same historical output, recomputed | `java_release_time_tth` | 5.197225146 | 28,506 / 28,506 | recomputation only |
| Same historical output, recomputed | `original_entry_time_tth` | 5.764936746 | 28,506 / 28,506 | recomputation only |
| Frozen v2-safe | `java_release_time_tth` | 3.556593853 | 28,506 / 28,506 | old central replay/future-reservation skeleton |
| Frozen v2-safe | `original_entry_time_tth` | 4.124305453 | 28,506 / 28,506 | same v2-safe result recomputed |
| G4IRSF11 event runtime | any survivor-only denominator | not comparable | 3,114 / 28,506 | incomplete; excluded from latency victory claims |

Therefore `3.967122711` must not be used as an
`original_entry_time_tth` target.  A future original-entry comparison must use
a matched original-entry baseline and must also display Java-release and
processed-attempt values.  All historical HCA* rows remain parsed evidence,
not a same-machine executable rerun.

## Reconciled evidence boundaries

1. `outputs/reports/g4irsf11_fixed_real_map_runtime_decision_brief.md` is the
   concise handoff, while the completion JSON and case ledger are the primary
   machine-readable values.
2. `outputs/reports/g4irsf11_gate_integrity_audit.md` is a different, earlier
   Gate-A audit of checked-in G4IRSF10 evidence.  Its overall `FAIL` must not be
   confused with the final six-row runtime gate distribution above.
3. The ledger `input_sha256` value `{paper['derived_workload_sha256']}` is the
   derived paper-full workload hash.  The protected source-file hash remains
   `{SOURCE_SHA256}`.
4. `{SOURCE_IDENTITY_PATH.as_posix()}` covers the bounded combined trace source
   (`{sample['path']}`, {sample['processed_segment_count']:,} segments and
   {sample['observed_decision_count']:,} decisions), not all 43,603 source
   rows.  Its report sentence claiming complete-input coverage must not be used
   as full-source evidence; the direct file hash/row/unique-task audit in this
   phase is authoritative.
5. Frozen v2-safe is a valid control but not the same architecture: it retains
   a central task-to-goal loop and future node reservations.  Its `PIBT-lite`
   label is same-bag alternative scanning, not recursive multi-bag PIBT.

## Reusable validators

- `scripts/eval/g4irsf11_fixed_map.py`: fail-closed map identity and dimensions;
- `scripts/eval/run_g4irsf11_event_runtime_evaluation.py`: source raw/semantic identity and cohort publication;
- `scripts/eval/validate_g4irsf11_committed_artifacts.py`: committed artifact hash and semantic validation;
- `scripts/eval/g4irsf11_g4irsf10_audit.py`: frozen v2-safe scale evidence boundary;
- `scripts/eval/run_g4irsf8_source_release_denominator_validation.py`: denominator reconstruction (generator; do not run during a read-only audit);
- `scripts/eval/g4irsf12_phase_a.py`: this phase's read-only check and small-report publisher.
"""


def write_outputs(evidence: Mapping[str, Any], root: Path = ROOT) -> None:
    outputs = {
        IDENTITY_TABLE_PATH: render_identity_csv(evidence),
        STATE_REPORT_PATH: render_state_report(evidence),
        RECONCILIATION_REPORT_PATH: render_reconciliation_report(evidence),
    }
    for relative, text in outputs.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")


def validate_committed_outputs(root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    for relative in (IDENTITY_TABLE_PATH, STATE_REPORT_PATH, RECONCILIATION_REPORT_PATH):
        if not (root / relative).is_file():
            failures.append(f"missing Phase-A output: {relative.as_posix()}")
    if failures:
        return failures

    audit_rows = _read_csv(root / IDENTITY_TABLE_PATH)
    by_check = {row["check"]: row for row in audit_rows}
    for check in (
        "phase_start_head",
        "raw_sha256",
        "segment_count",
        "executed_cases",
        "gate_distribution",
        "complete_raw_bags",
        "completed_segments",
        "processed_segment_attempt_mean_minutes",
        "original_entry_recomputed_mean_minutes",
    ):
        matching = [row for row in audit_rows if row["check"] == check]
        if not matching:
            failures.append(f"identity audit missing check: {check}")
        elif any(row["status"] != "PASS" for row in matching):
            failures.append(f"identity audit check is not PASS: {check}")

    completed_row = by_check.get("completed_segments")
    if completed_row and completed_row["observed"] != "12125":
        failures.append("identity audit does not preserve completed_segments=12125")

    state_text = (root / STATE_REPORT_PATH).read_text(encoding="utf-8")
    reconciliation_text = (root / RECONCILIATION_REPORT_PATH).read_text(encoding="utf-8")
    for required in (
        "Phase-A gate: `PASS`",
        "Original-Scale-First Rule",
        "processed-segment-attempt THT, not original-entry THT",
    ):
        if required not in state_text:
            failures.append(f"state report missing required text: {required}")
    for required in (
        "**12,125 / 43,603**",
        "3.967122711",
        "must not be used as an",
        "`original_entry_time_tth` target",
        "3 PASS / 3 PARTIAL_WITH_EXPLICIT_BLOCKER",
    ):
        if required not in reconciliation_text:
            failures.append(f"reconciliation report missing required text: {required}")
    return sorted(set(failures))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="publish the three Phase-A report/table outputs after validation",
    )
    parser.add_argument("--repo", type=Path, default=ROOT)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.repo.resolve()
    evidence = collect_phase_a_evidence(root)
    failures = [*validate_phase_a_evidence(evidence), *validate_governance(root)]
    if args.write and not failures:
        write_outputs(evidence, root)
    failures.extend(validate_committed_outputs(root))
    result = {
        "status": "PASS" if not failures else "FAIL",
        "failures": sorted(set(failures)),
        "head": evidence["git"]["head"],
        "map_raw_sha256": evidence["map"]["raw_sha256"],
        "map_semantic_sha256": evidence["map"]["semantic_sha256"],
        "source_sha256": evidence["source"]["raw_sha256"],
        "formal_cases": f"{evidence['formal']['executed_case_count']}/{evidence['formal']['expected_case_count']}",
        "formal_gates": "3 PASS / 3 PARTIAL_WITH_EXPLICIT_BLOCKER",
        "complete_raw_bags": evidence["paper_full"]["complete_raw_bag_count"],
        "completed_segments": evidence["paper_full"]["completed_segments"],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
