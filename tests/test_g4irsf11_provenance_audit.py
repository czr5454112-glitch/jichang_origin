from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.g4irsf11_provenance_audit import assemble_provenance_audit


HEAD = "a" * 40


def _local(path: Path, *, status: str = "PASS", remote: str = HEAD) -> None:
    path.write_text(
        json.dumps(
            {
                "schema": "czr005.g4irsf11.gate_integrity.v1",
                "overall_status": status,
                "checks": [
                    {
                        "name": "git_provenance_and_state_clean",
                        "status": status,
                        "metrics": {"head": HEAD, "remote_head": remote},
                    }
                ],
                "commands": [
                    {
                        "argv": [
                            "git", "status", "--porcelain=v1", "--untracked-files=all", "--",
                            "legacy", "data/processed/maps/map2.json", "data/processed/tasks/inputdata.jsonl",
                        ],
                        "return_code": 0,
                        "stdout": "",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_audit_passes_only_for_exact_clean_head_and_successful_push_run(tmp_path: Path) -> None:
    local = tmp_path / "local.json"
    _local(local)
    audit = assemble_provenance_audit(
        local,
        remote_head_sha=HEAD,
        remote_run_url="https://github.com/czr5454112-glitch/jichang_origin/actions/runs/123",
        remote_conclusion="success",
        observed_at="2026-07-21T00:00:00Z",
    )
    assert audit["overall_status"] == "PASS"
    assert audit["protected_inputs_clean"] is True


def test_unrelated_nonempty_remote_head_cannot_pass(tmp_path: Path) -> None:
    local = tmp_path / "local.json"
    _local(local, remote="b" * 40)
    audit = assemble_provenance_audit(
        local,
        remote_head_sha="b" * 40,
        remote_run_url="https://github.com/czr5454112-glitch/jichang_origin/actions/runs/123",
        remote_conclusion="success",
    )
    assert audit["overall_status"] != "PASS"
    assert any("upstream" in blocker for blocker in audit["blockers"])


def test_remote_failure_or_head_mismatch_cannot_pass(tmp_path: Path) -> None:
    local = tmp_path / "local.json"
    _local(local)
    audit = assemble_provenance_audit(
        local,
        remote_head_sha="c" * 40,
        remote_run_url="https://github.com/czr5454112-glitch/jichang_origin/actions/runs/123",
        remote_conclusion="failure",
    )
    assert audit["remote_ci_status"] != "PASS"
    assert any("conclusion" in blocker for blocker in audit["blockers"])
