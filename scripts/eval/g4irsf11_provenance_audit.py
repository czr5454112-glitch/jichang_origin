"""Bind local fail-closed provenance to an independently observed CI run."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Mapping


SCHEMA = "czr005.g4irsf11.provenance_ci_audit.v1"
WORKFLOW = "g4irsf11-gate-integrity"
BRANCH = "codex/czr005-rewrite"
RUN_URL = re.compile(
    r"^https://github\.com/czr5454112-glitch/jichang_origin/actions/runs/[0-9]+$"
)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def assemble_provenance_audit(
    local_audit_path: Path,
    *,
    remote_head_sha: str,
    remote_run_url: str,
    remote_conclusion: str,
    remote_workflow: str = WORKFLOW,
    remote_branch: str = BRANCH,
    remote_event: str = "push",
    observed_at: str | None = None,
) -> dict[str, Any]:
    local = _read(local_audit_path)
    checks = local.get("checks") if isinstance(local.get("checks"), list) else []
    provenance = next(
        (row for row in checks if isinstance(row, Mapping) and row.get("name") == "git_provenance_and_state_clean"),
        {},
    )
    metrics = provenance.get("metrics") if isinstance(provenance.get("metrics"), Mapping) else {}
    audited_head = str(metrics.get("head") or "")
    upstream_head = str(metrics.get("remote_head") or "")
    commands = local.get("commands") if isinstance(local.get("commands"), list) else []
    protected_command = next(
        (
            row for row in commands
            if isinstance(row, Mapping)
            and row.get("argv") == [
                "git", "status", "--porcelain=v1", "--untracked-files=all", "--",
                "legacy", "data/processed/maps/map2.json", "data/processed/tasks/inputdata.jsonl",
            ]
        ),
        {},
    )
    blockers: list[str] = []
    if local.get("schema") != "czr005.g4irsf11.gate_integrity.v1":
        blockers.append("local gate-integrity schema is missing or unexpected")
    if local.get("overall_status") != "PASS" or provenance.get("status") != "PASS":
        blockers.append("local Git ancestry/state-clean gate is not PASS")
    if not audited_head or audited_head != upstream_head:
        blockers.append("audited local HEAD does not exactly equal audited upstream HEAD")
    if protected_command.get("return_code") != 0 or str(protected_command.get("stdout") or "").strip():
        blockers.append("legacy/map/inputdata protected-path status is not clean")
    if remote_head_sha != audited_head:
        blockers.append("remote workflow head SHA does not bind the audited local HEAD")
    if remote_workflow != WORKFLOW:
        blockers.append(f"remote workflow must be exactly {WORKFLOW}")
    if remote_branch != BRANCH:
        blockers.append(f"remote branch must be exactly {BRANCH}")
    if remote_event != "push":
        blockers.append("remote CI evidence must be a push run for the audited branch")
    if remote_conclusion.lower() != "success":
        blockers.append("remote CI conclusion is not success")
    if not RUN_URL.fullmatch(remote_run_url):
        blockers.append("remote workflow run URL is missing or not the repository Actions URL")
    status = "PASS" if not blockers else "PARTIAL_WITH_EXPLICIT_BLOCKER"
    return {
        "schema": SCHEMA,
        "overall_status": status,
        "remote_ci_status": "PASS" if not blockers else "PARTIAL_WITH_EXPLICIT_BLOCKER",
        "audited_head_sha": audited_head,
        "audited_upstream_head_sha": upstream_head,
        "local_state_clean": local.get("overall_status") == "PASS",
        "protected_inputs_clean": (
            protected_command.get("return_code") == 0
            and not str(protected_command.get("stdout") or "").strip()
        ),
        "local_audit": {
            "path": local_audit_path.as_posix(),
            "schema": local.get("schema", ""),
            "status": local.get("overall_status", ""),
            "recorded_command_count": len(commands),
        },
        "remote_ci": {
            "workflow": remote_workflow,
            "branch": remote_branch,
            "event": remote_event,
            "head_sha": remote_head_sha,
            "conclusion": remote_conclusion,
            "run_url": remote_run_url,
            "observed_at": observed_at or datetime.now(timezone.utc).isoformat(),
            "observation_method": "read-only GitHub Actions page inspection",
        },
        "blockers": blockers,
        "claim_boundary": (
            "This audit binds a clean local/upstream commit to one successful remote push run. "
            "It does not promote experiment, capacity, or v3 gates."
        ),
    }


def write_provenance_audit(path: Path, audit: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(audit), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
