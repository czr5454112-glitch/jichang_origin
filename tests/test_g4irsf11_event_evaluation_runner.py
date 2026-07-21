from __future__ import annotations

from pathlib import Path
import json

import pytest

from scripts.eval.g4irsf11_evaluation_reporting import case_row, gate_rows
from scripts.eval.g4irsf11_experiment_protocol import formal_cases
from scripts.eval.g4irsf11_experiment_protocol import PROTOCOL_VERSION
from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
    _descriptor_matches,
    _acquire_case_lock,
    _release_case_lock,
    _trace_artifact_bindings,
    _load_all_rows,
    build_parser,
    timeline_spanning_sample,
)
from scripts.eval.g4irsf11_result_validation import atomic_write_json, atomic_write_jsonl
from scripts.eval.run_g4irsf11_event_case import _outcomes


def _rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "release_time": float(index),
            "segment_id": f"segment-{index}",
            "generation_copy_index": 0,
        }
        for index in range(count)
    ]


def test_timeline_sample_is_exact_deterministic_and_spans_both_ends() -> None:
    rows = _rows(100)
    sampled = timeline_spanning_sample(rows, 9)
    assert len(sampled) == 9
    assert sampled[0]["release_time"] == 0.0
    assert sampled[-1]["release_time"] == 99.0
    assert sampled == timeline_spanning_sample(list(reversed(rows)), 9)


def test_case_row_never_equates_completion_with_capacity() -> None:
    case = formal_cases()[0]
    result = {
        "workload_segment_count": 10,
        "raw_bag_count": 10,
        "completion_pass": True,
        "event_runtime_invariant_pass": True,
        "summary": {"completed_count": 10, "failed_count": 0},
        "segment_capacity_metrics": {"safe_execution_pass": True},
        "raw_bag_capacity_metrics": {
            "queue_stability_pass": False,
            "service_level_pass": False,
            "capacity_pass": False,
        },
        "resource_metrics": {"peak_working_set_bytes": 1},
    }
    row = case_row(case, result, {"status": "EXECUTED", "return_code": 0})
    assert row["completion_pass"] is True
    assert row["capacity_pass"] is False


def test_missing_formal_cases_are_explicit_blockers() -> None:
    gates = gate_rows([])
    assert gates
    assert all(row["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER" for row in gates)


def test_parser_rejects_incomplete_protocol_success_bypass() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "--measurement-cohort",
                "developer_validation_sequential1",
                "--concurrent-worker-target",
                "1",
                "--allow-incomplete-protocol",
            ]
        )


def test_legacy_or_incomplete_descriptor_is_never_reusable_as_v3() -> None:
    case = formal_cases()[0]
    descriptor = {
        "protocol_version": PROTOCOL_VERSION,
        "case": case.as_dict(),
        "source_sha256": "source",
        "map_sha256": "map",
        "implementation_sha256": "implementation",
        "status": "EXECUTED",
    }
    assert not _descriptor_matches(
        descriptor,
        case,
        source_sha256="source",
        map_sha256="map",
        implementation_digest="implementation",
    )
    assert not _descriptor_matches(
        descriptor,
        case,
        source_sha256="source",
        map_sha256="map",
        implementation_digest="changed-implementation",
    )


def test_case_writer_lock_prevents_concurrent_descriptor_clobber(tmp_path: Path) -> None:
    path = tmp_path / "same-case.lock"
    first = _acquire_case_lock(path, "same-case")
    assert first is not None
    assert _acquire_case_lock(path, "same-case") is None
    _release_case_lock(first)
    second = _acquire_case_lock(path, "same-case")
    assert second is not None
    _release_case_lock(second)


def test_case_lock_release_never_deletes_a_different_owner_nonce(tmp_path: Path) -> None:
    path = tmp_path / "same-case.lock"
    token = _acquire_case_lock(path, "same-case")
    assert token is not None
    path.write_text(
        json.dumps({"case_id": "same-case", "pid": token["pid"], "nonce": "other"}),
        encoding="utf-8",
    )
    _release_case_lock(token)
    assert path.is_file()
    path.unlink()


def test_trace_bundle_binds_trace_outcome_and_task_files(tmp_path: Path) -> None:
    case = next(case for case in formal_cases() if case.trace_complete)
    paths = {
        "trace": tmp_path / "trace.json",
        "outcomes": tmp_path / "outcomes.jsonl",
        "tasks": tmp_path / "tasks.jsonl",
    }
    atomic_write_json(paths["trace"], {"decision_trace": [{"id": 1}, {"id": 2}]})
    atomic_write_jsonl(paths["outcomes"], [{"id": 1}, {"id": 2}])
    atomic_write_jsonl(paths["tasks"], [{"id": 1}])
    first = _trace_artifact_bindings(case, paths)
    assert first["trace"]["row_count"] == 2
    assert first["outcomes"]["row_count"] == 2
    assert first["tasks"]["row_count"] == 1
    atomic_write_jsonl(paths["outcomes"], [{"id": 1}, {"id": "tampered"}])
    second = _trace_artifact_bindings(case, paths)
    assert first["outcomes"]["sha256"] != second["outcomes"]["sha256"]


def test_non_trace_bundle_rejects_any_stale_trace_artifact(tmp_path: Path) -> None:
    case = next(case for case in formal_cases() if not case.trace_complete)
    paths = {
        "trace": tmp_path / "trace.json",
        "outcomes": tmp_path / "outcomes.jsonl",
        "tasks": tmp_path / "tasks.jsonl",
    }
    bindings = _trace_artifact_bindings(case, paths)
    assert all(binding["state"] == "not_requested" for binding in bindings.values())

    for name, path in paths.items():
        path.write_text("stale", encoding="utf-8")
        with pytest.raises(ValueError, match=rf"unexpected trace artifacts:.*{name}"):
            _trace_artifact_bindings(case, paths)
        path.unlink()


def test_invalid_executed_descriptor_is_never_reported_as_executed(
    tmp_path: Path, monkeypatch: object
) -> None:
    case = formal_cases()[0]
    execution_path = tmp_path / "execution.json"
    paths = {
        "execution": execution_path,
        "result": tmp_path / "result.json",
        "workload": tmp_path / "workload.jsonl",
        "fault": tmp_path / "fault.json",
        "trace": tmp_path / "trace.json",
        "outcomes": tmp_path / "outcomes.jsonl",
        "tasks": tmp_path / "tasks.jsonl",
    }
    atomic_write_json(
        execution_path,
        {
            "status": "EXECUTED",
            "return_code": 0,
            "blocker": "",
            "case": case.as_dict(),
        },
    )
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "scripts.eval.run_g4irsf11_event_runtime_evaluation._case_paths",
        lambda ignored: paths,
    )
    rows = _load_all_rows(
        [case],
        source_sha256="a" * 64,
        map_sha256="b" * 64,
        implementation_digest="c" * 64,
    )
    assert rows[0]["execution_status"] == "FAILED"
    assert "claimed EXECUTED" in rows[0]["blocker"]


def test_outcomes_join_duplicate_original_task_ids_by_runtime_segment_identity() -> None:
    segments = [
        {
            "runtime_bag_id": 0,
            "task_id": 77,
            "segment_id": "77:storage_in",
            "release_time": 0.0,
            "finish_time": 10.0,
            "completed": True,
            "total_local_wait": 1.0,
        },
        {
            "runtime_bag_id": 1,
            "task_id": 77,
            "segment_id": "77:storage_out",
            "release_time": 20.0,
            "finish_time": 50.0,
            "completed": True,
            "total_local_wait": 2.0,
        },
    ]
    decisions = [
        {
            "decision_id": "in",
            "task_id": 77,
            "segment_id": "77:storage_in",
            "metadata": {"runtime_bag_id": 0},
        },
        {
            "decision_id": "out",
            "task_id": 77,
            "segment_id": "77:storage_out",
            "metadata": {"runtime_bag_id": 1},
        },
    ]
    rows = _outcomes(decisions, segments, fault_mode="no_fault")
    assert [row["bag_tth_seconds"] for row in rows] == [10.0, 30.0]
    assert [row["local_wait_seconds"] for row in rows] == [1.0, 2.0]
