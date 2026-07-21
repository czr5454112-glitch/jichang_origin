from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

import pytest

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
    assert "worker return code 0" in descriptor["blocker"]
    assert not paths["result"].exists()
    assert not paths["lock"].exists()
    archive_manifests = list(paths["archive"].glob("*/archive_manifest.json"))
    assert len(archive_manifests) == 1
    archive = json.loads(archive_manifests[0].read_text(encoding="utf-8"))
    assert archive["archived_status"] == "ARCHIVED_STALE_RUNNING_NOT_REUSABLE"
    assert "resume_validation_failed" in archive["archived_reason"]


def test_archive_moves_every_active_attempt_artifact_out_of_clean_rerun_paths(
    tmp_path: Path,
) -> None:
    case = CaseSpec("archive-complete-bundle", "test", "time_compressed", 1.0)
    paths = _paths(tmp_path, case)
    payloads = {
        "execution": b'{"run_id":"old-run","status":"FAILED"}\n',
        "result": b'{"schema":"legacy"}\n',
        "trace": b'{"decision_trace":[]}\n',
        "outcomes": b'{"decision_id":"old"}\n',
        "tasks": b'{"task_id":1}\n',
        "workload": b'{"segment_id":"old"}\n',
        "fault": b'[]\n',
    }
    for name, payload in payloads.items():
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].write_bytes(payload)
    corrupt_history = b'{"truncated_history":\n'
    paths["history"].write_bytes(corrupt_history)

    runner._archive_existing_attempt(
        case,
        paths,
        reason="test clean-rerun recovery",
    )

    assert all(not paths[name].exists() for name in payloads)
    manifests = list(paths["archive"].glob("*/archive_manifest.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["archived_reason"] == "test clean-rerun recovery"
    assert manifest["archive_transaction_status"] == "COMPLETE"
    assert set(manifest["artifact_evidence"]) == set(payloads)
    assert not list(paths["archive"].glob("*/archive_in_progress.json"))
    for name, payload in payloads.items():
        archived = Path(manifest["artifact_evidence"][name]["archived_path"])
        assert archived.read_bytes() == payload
    history_rows = [
        json.loads(line)
        for line in paths["history"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert history_rows[0]["archived_status"] == "CORRUPT_PRIOR_HISTORY_RETAINED_EXACTLY"
    archived_history = Path(history_rows[0]["archived_path"])
    assert archived_history.read_bytes() == corrupt_history


def test_archive_copy_failure_retains_every_active_source_and_marks_in_progress(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    case = CaseSpec("archive-interrupted-bundle", "test", "time_compressed", 1.0)
    paths = _paths(tmp_path, case)
    payloads = {
        "execution": b'{"run_id":"old-run","status":"FAILED"}\n',
        "result": b'{"schema":"legacy"}\n',
    }
    for name, payload in payloads.items():
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].write_bytes(payload)

    copied = 0
    original_copy = runner._atomic_copy_file

    def interrupted_copy(source: Path, destination: Path) -> None:
        nonlocal copied
        copied += 1
        if copied == 2:
            raise OSError("simulated archive interruption")
        original_copy(source, destination)

    monkeypatch.setattr(runner, "_atomic_copy_file", interrupted_copy)  # type: ignore[attr-defined]
    try:
        runner._archive_existing_attempt(case, paths, reason="simulated interruption")
    except OSError as exc:
        assert "simulated archive interruption" in str(exc)
    else:
        raise AssertionError("interrupted archive must fail closed")

    assert all(paths[name].read_bytes() == payload for name, payload in payloads.items())
    assert not list(paths["archive"].glob("*/archive_manifest.json"))
    in_progress = list(paths["archive"].glob("*/archive_in_progress.json"))
    assert len(in_progress) == 1
    marker = json.loads(in_progress[0].read_text(encoding="utf-8"))
    assert marker["archive_transaction_status"] == "ARCHIVE_IN_PROGRESS"


def test_archive_tolerates_structurally_corrupt_but_parseable_result(
    tmp_path: Path,
) -> None:
    case = CaseSpec("archive-malformed-shape", "test", "time_compressed", 1.0)
    paths = _paths(tmp_path, case)
    result_bytes = (
        b'{"summary":[],"raw_bag_capacity_metrics":[],"bag_sample":[1]}\n'
    )
    paths["execution"].write_bytes(b'{"run_id":"old","status":"FAILED"}\n')
    paths["result"].write_bytes(result_bytes)

    runner._archive_existing_attempt(case, paths, reason="malformed shape")

    manifest_path = next(paths["archive"].glob("*/archive_manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    archived_result = Path(manifest["artifact_evidence"]["result"]["archived_path"])
    assert archived_result.read_bytes() == result_bytes
    assert not paths["result"].exists()


@pytest.mark.parametrize(
    "history_bytes",
    [
        b'{"value":NaN}\n',
        b'{"value":1,"value":2}\n',
    ],
)
def test_archive_retains_noncanonical_history_bytes_exactly(
    tmp_path: Path,
    history_bytes: bytes,
) -> None:
    token = str(abs(hash(history_bytes)))
    case = CaseSpec(f"archive-strict-history-{token}", "test", "time_compressed", 1.0)
    paths = _paths(tmp_path / token, case)
    paths["execution"].parent.mkdir(parents=True, exist_ok=True)
    paths["execution"].write_bytes(b'{"run_id":"old","status":"FAILED"}\n')
    paths["result"].write_bytes(b'{"schema":"legacy"}\n')
    paths["history"].write_bytes(history_bytes)

    runner._archive_existing_attempt(case, paths, reason="strict history")

    history_rows = [
        json.loads(line)
        for line in paths["history"].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    retained = history_rows[0]
    assert retained["archived_status"] == "CORRUPT_PRIOR_HISTORY_RETAINED_EXACTLY"
    assert Path(retained["archived_path"]).read_bytes() == history_bytes


def test_history_write_failure_retains_active_sources_without_dual_markers(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    case = CaseSpec("archive-history-write-failure", "test", "time_compressed", 1.0)
    paths = _paths(tmp_path, case)
    payloads = {
        "execution": b'{"run_id":"old","status":"FAILED"}\n',
        "result": b'{"schema":"legacy"}\n',
    }
    for name, payload in payloads.items():
        paths[name].parent.mkdir(parents=True, exist_ok=True)
        paths[name].write_bytes(payload)

    original_write = runner.atomic_write_jsonl

    def fail_history_write(path: Path, rows: object) -> None:
        if path == paths["history"]:
            raise OSError("simulated history write failure")
        original_write(path, rows)  # type: ignore[arg-type]

    monkeypatch.setattr(runner, "atomic_write_jsonl", fail_history_write)  # type: ignore[attr-defined]
    with pytest.raises(OSError, match="simulated history write failure"):
        runner._archive_existing_attempt(case, paths, reason="history write failure")

    assert all(paths[name].read_bytes() == payload for name, payload in payloads.items())
    assert len(list(paths["archive"].glob("*/archive_manifest.json"))) == 1
    assert not list(paths["archive"].glob("*/archive_in_progress.json"))
