from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from scripts.eval.g4irsf11_experiment_protocol import CaseSpec
from scripts.eval.g4irsf11_result_validation import atomic_write_json
from scripts.eval import run_g4irsf11_event_runtime_evaluation as runner


def _paths(root: Path, case: CaseSpec) -> dict[str, Path]:
    return {
        "workload": root / f"{case.case_id}.jsonl",
        "result": root / f"{case.case_id}.result.json",
        "execution": root / f"{case.case_id}.execution.json",
        "fault": root / f"{case.case_id}.fault.json",
        "trace": root / f"{case.case_id}.trace.json",
        "outcomes": root / f"{case.case_id}.outcomes.jsonl",
        "tasks": root / f"{case.case_id}.tasks.jsonl",
        "history": root / f"{case.case_id}.history.jsonl",
        "archive": root / "archive" / case.case_id,
        "lock": root / f"{case.case_id}.lock",
    }


def _args(root: Path, *, resume: bool = True) -> argparse.Namespace:
    return argparse.Namespace(
        resume=resume,
        python=Path(sys.executable),
        search_path=root,
        max_events=100,
        timeout_seconds=60.0,
        measurement_cohort="pytest_sequential1",
        concurrent_worker_target=1,
        keep_workloads=True,
    )


def test_resume_acquires_case_lock_before_reading_or_validating_cache(
    tmp_path: Path, monkeypatch: object
) -> None:
    case = CaseSpec("lock-first", "test", "time_compressed", 1.0)
    paths = _paths(tmp_path, case)
    monkeypatch.setattr(runner, "_case_paths", lambda ignored: paths)  # type: ignore[attr-defined]
    owner = runner._acquire_case_lock(paths["lock"], case.case_id)
    assert owner is not None
    try:
        monkeypatch.setattr(  # type: ignore[attr-defined]
            runner,
            "build_workload",
            lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not build")),
        )
        result, descriptor = runner.execute_case(
            case,
            [],
            _args(tmp_path),
            source_sha256="a" * 64,
            map_sha256="b" * 64,
            implementation_digest="c" * 64,
        )
        assert result is None
        assert descriptor["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER"
    finally:
        runner._release_case_lock(owner)


def test_stale_running_and_old_result_are_archived_and_never_reused(
    tmp_path: Path, monkeypatch: object
) -> None:
    case = CaseSpec("stale-running", "test", "time_compressed", 1.0)
    paths = _paths(tmp_path, case)
    monkeypatch.setattr(runner, "_case_paths", lambda ignored: paths)  # type: ignore[attr-defined]
    monkeypatch.setattr(  # type: ignore[attr-defined]
        runner,
        "build_workload",
        lambda *args, **kwargs: [
            {
                "segment_id": "segment-1",
                "task_id": 1,
                "release_time": 0.0,
                "generation_copy_index": 0,
            }
        ],
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        runner, "namespace_workload", lambda rows, **kwargs: list(rows)
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        runner,
        "subprocess",
        type(
            "FakeSubprocess",
            (),
            {
                "run": staticmethod(
                    lambda command, **kwargs: subprocess.CompletedProcess(command, 0, "", "")
                ),
                "list2cmdline": staticmethod(subprocess.list2cmdline),
                "TimeoutExpired": subprocess.TimeoutExpired,
            },
        ),
    )
    atomic_write_json(
        paths["execution"],
        {"status": "RUNNING", "run_id": "old-run", "protocol_version": "v2"},
    )
    atomic_write_json(
        paths["result"],
        {
            "schema": "legacy",
            "run_id": "old-run",
            "bag_sample": [{"failure_reason": "old_failure_reason_must_not_shadow_archive_reason"}],
        },
    )

    result, descriptor = runner.execute_case(
        case,
        [],
        _args(tmp_path),
        source_sha256="a" * 64,
        map_sha256="b" * 64,
        implementation_digest="c" * 64,
    )
    assert result is None
    assert descriptor["status"] == "FAILED"
    assert "strict v3" in descriptor["blocker"]
    assert not paths["lock"].exists()
    archive_manifests = list(paths["archive"].glob("*/archive_manifest.json"))
    assert len(archive_manifests) == 1
    archive = json.loads(archive_manifests[0].read_text(encoding="utf-8"))
    assert archive["archived_status"] == "ARCHIVED_STALE_RUNNING_NOT_REUSABLE"
    assert "resume_validation_failed" in archive["archived_reason"]
