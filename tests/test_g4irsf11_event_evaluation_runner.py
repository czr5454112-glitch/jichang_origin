from __future__ import annotations

from pathlib import Path
import json

import pytest

from scripts.eval.g4irsf11_evaluation_reporting import case_row, gate_rows
from scripts.eval.g4irsf11_experiment_protocol import formal_cases
from scripts.eval.g4irsf11_experiment_protocol import PROTOCOL_VERSION, protocol_manifest
from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
    _descriptor_matches,
    _acquire_case_lock,
    _release_case_lock,
    _trace_artifact_bindings,
    _trace_semantic_errors,
    _load_all_rows,
    build_parser,
    timeline_spanning_sample,
)
from scripts.eval.g4irsf11_result_validation import (
    EXECUTION_DESCRIPTOR_SCHEMA,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_manifest_sha256,
)
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


def test_external_trace_semantics_are_cross_bound_to_result(tmp_path: Path) -> None:
    case = next(case for case in formal_cases() if case.trace_complete)
    paths = {
        "trace": tmp_path / "trace.json",
        "outcomes": tmp_path / "outcomes.jsonl",
        "tasks": tmp_path / "tasks.jsonl",
    }
    context = {
        "run_id": "run-1",
        "scenario": case.case_id,
        "scale": case.scale,
        "fault_mode": case.fault_profile,
    }
    summary = {"decision_count": 2}
    decisions = [
        {
            "decision_id": "d1",
            "task_id": 1,
            "segment_id": "s1",
            "metadata": {"runtime_bag_id": 7},
        },
        {
            "decision_id": "d2",
            "task_id": 1,
            "segment_id": "s1",
            "metadata": {"runtime_bag_id": 7},
        },
    ]
    outcomes = [
        {
            "decision_id": row["decision_id"],
            "task_id": row["task_id"],
            "segment_id": row["segment_id"],
            "runtime_bag_id": row["metadata"]["runtime_bag_id"],
        }
        for row in decisions
    ]
    tasks = [{"task_id": 1, "segment_id": "s1", "release_time": 1}]
    atomic_write_json(
        paths["trace"],
        {"decision_trace": decisions, "trace_context": context, "summary": summary},
    )
    atomic_write_jsonl(paths["outcomes"], outcomes)
    atomic_write_jsonl(paths["tasks"], tasks)
    result = {
        "summary": summary,
        "trace": {
            "trace_output": str(paths["trace"].resolve()),
            "outcome_output": str(paths["outcomes"].resolve()),
            "trace_task_output": str(paths["tasks"].resolve()),
            "decision_rows_stored": 2,
            "trace_context": context,
        },
    }
    assert _trace_semantic_errors(case, paths, result, tasks) == []
    atomic_write_jsonl(
        paths["outcomes"],
        [dict(outcomes[0]), dict(outcomes[1], decision_id="wrong")],
    )
    assert any(
        "outcome decision identities" in error
        for error in _trace_semantic_errors(case, paths, result, tasks)
    )
    atomic_write_jsonl(
        paths["outcomes"],
        [dict(outcomes[0]), dict(outcomes[1], runtime_bag_id=8)],
    )
    assert any(
        "outcome decision identities" in error
        for error in _trace_semantic_errors(case, paths, result, tasks)
    )
    atomic_write_jsonl(paths["outcomes"], outcomes)
    atomic_write_jsonl(
        paths["tasks"],
        [dict(tasks[0], release_time=1.0)],
    )
    assert any(
        "canonical workload rows" in error
        for error in _trace_semantic_errors(case, paths, result, tasks)
    )
    atomic_write_jsonl(paths["tasks"], tasks)
    duplicate_decisions = [dict(decisions[0]), dict(decisions[1], decision_id="d1")]
    atomic_write_json(
        paths["trace"],
        {
            "decision_trace": duplicate_decisions,
            "trace_context": context,
            "summary": summary,
        },
    )
    assert any(
        "decision_ids are not unique" in error
        for error in _trace_semantic_errors(case, paths, result, tasks)
    )
    atomic_write_json(
        paths["trace"],
        {"decision_trace": decisions, "trace_context": context, "summary": summary},
    )
    atomic_write_jsonl(paths["tasks"], [dict(tasks[0], release_time=999.0)])
    assert any(
        "canonical workload rows" in error
        for error in _trace_semantic_errors(case, paths, result, tasks)
    )


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


def test_corrupt_execution_descriptor_becomes_explicit_failed_row(
    tmp_path: Path, monkeypatch: object
) -> None:
    case = formal_cases()[0]
    paths = {
        "execution": tmp_path / "execution.json",
        "result": tmp_path / "result.json",
    }
    paths["execution"].write_text('{"status":', encoding="utf-8")
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
    assert rows[0]["return_code"] == "DESCRIPTOR_DECODE_ERROR"
    assert "descriptor could not be decoded" in rows[0]["blocker"]


def test_corrupt_formal_workload_fails_bundle_validation_without_crashing(
    tmp_path: Path, monkeypatch: object
) -> None:
    case = formal_cases()[0]
    source_sha256 = "a" * 64
    map_sha256 = "b" * 64
    implementation_digest = "c" * 64
    paths = {
        "execution": tmp_path / "execution.json",
        "result": tmp_path / "result.json",
        "workload": tmp_path / "workload.jsonl",
        "fault": tmp_path / "fault.json",
        "trace": tmp_path / "trace.json",
        "outcomes": tmp_path / "outcomes.jsonl",
        "tasks": tmp_path / "tasks.jsonl",
    }
    atomic_write_json(
        paths["execution"],
        {
            "schema": EXECUTION_DESCRIPTOR_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "protocol_manifest_sha256": canonical_manifest_sha256(protocol_manifest()),
            "case": case.as_dict(),
            "source_sha256": source_sha256,
            "map_sha256": map_sha256,
            "implementation_sha256": implementation_digest,
            "status": "EXECUTED",
            "return_code": 0,
            "blocker": "",
        },
    )
    atomic_write_json(paths["result"], {})
    paths["workload"].write_text('{"release_time":', encoding="utf-8")
    paths["fault"].write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "scripts.eval.run_g4irsf11_event_runtime_evaluation._case_paths",
        lambda ignored: paths,
    )
    rows = _load_all_rows(
        [case],
        source_sha256=source_sha256,
        map_sha256=map_sha256,
        implementation_digest=implementation_digest,
    )
    assert rows[0]["execution_status"] == "FAILED"
    assert "bundle validation failed" in rows[0]["blocker"]


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
