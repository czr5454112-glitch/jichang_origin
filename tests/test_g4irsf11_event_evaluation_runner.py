from __future__ import annotations

from pathlib import Path
import json

import pytest

from scripts.eval import run_g4irsf11_event_runtime_evaluation as runner_module
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
    assert_implementation_unchanged,
    build_parser,
    timeline_spanning_sample,
)
from scripts.eval.g4irsf11_result_validation import (
    EXECUTION_DESCRIPTOR_SCHEMA,
    atomic_write_json,
    atomic_write_jsonl,
    canonical_manifest_sha256,
)
from scripts.eval.g4irsf11_publication import (
    artifact_bindings as publication_artifact_bindings,
    begin_completion,
    complete_publication,
    completion_validation_errors,
    create_staging_root,
    promote_staged_artifacts,
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


def test_implementation_mutation_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "scripts.eval.run_g4irsf11_event_runtime_evaluation.implementation_sha256",
        lambda _search_path: "b" * 64,
    )

    with pytest.raises(RuntimeError, match="changed during the measurement cohort"):
        assert_implementation_unchanged("a" * 64, tmp_path)


def test_source_task_snapshot_detects_even_newline_only_runtime_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_bytes(b'{"task_id":1}\n{"task_id":2}\n')
    monkeypatch.setattr(runner_module, "SOURCE_TASK_PATH", source)
    rows, frozen_source = runner_module.load_source_task_snapshot()
    frozen_map = runner_module.canonical_map_identity()
    assert len(rows) == 2

    source.write_bytes(b'{"task_id":1}\r\n{"task_id":2}\r\n')
    with pytest.raises(RuntimeError, match="source task changed"):
        runner_module.assert_frozen_inputs_unchanged(frozen_source, frozen_map)


def test_all_case_lock_acquisition_rolls_back_partial_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cases = formal_cases()[:2]
    lock_paths = {case.case_id: tmp_path / f"{case.case_id}.lock" for case in cases}
    monkeypatch.setattr(
        runner_module,
        "_case_paths",
        lambda case: {"lock": lock_paths[case.case_id]},
    )
    held = runner_module._acquire_case_lock(
        lock_paths[cases[1].case_id], "held", wait_seconds=0.0
    )
    assert held is not None
    try:
        acquired = runner_module._acquire_all_case_locks(
            cases, scope="fixture", wait_seconds=0.0
        )
        assert acquired is None
        assert not lock_paths[cases[0].case_id].exists()
        assert lock_paths[cases[1].case_id].exists()
    finally:
        runner_module._release_case_lock(held)


def test_all_case_lock_acquisition_rolls_back_on_lock_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cases = formal_cases()[:2]
    lock_paths = {case.case_id: tmp_path / f"{case.case_id}.lock" for case in cases}
    monkeypatch.setattr(
        runner_module,
        "_case_paths",
        lambda case: {"lock": lock_paths[case.case_id]},
    )
    real_acquire = runner_module._acquire_case_lock
    calls = 0

    def acquire_then_fail(path: Path, scope: str, *, wait_seconds: float):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected lock failure")
        return real_acquire(path, scope, wait_seconds=wait_seconds)

    monkeypatch.setattr(runner_module, "_acquire_case_lock", acquire_then_fail)
    with pytest.raises(OSError, match="injected lock failure"):
        runner_module._acquire_all_case_locks(
            cases, scope="fixture", wait_seconds=0.0
        )
    assert not lock_paths[cases[0].case_id].exists()


def test_case_lock_file_write_failure_closes_and_removes_lock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    lock_path = tmp_path / "fault-injected.lock"
    descriptors: list[int] = []

    def fail_write(descriptor: int, _payload: object) -> int:
        descriptors.append(descriptor)
        raise OSError("injected lock write failure")

    monkeypatch.setattr(runner_module.os, "write", fail_write)
    with pytest.raises(OSError, match="injected lock write failure"):
        runner_module._acquire_case_lock(
            lock_path, "fault-injected", wait_seconds=0.0
        )
    assert descriptors
    with pytest.raises(OSError):
        runner_module.os.fstat(descriptors[0])
    assert not lock_path.exists()


def test_case_lock_unlink_failure_does_not_block_other_releases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first_path = tmp_path / "first.lock"
    second_path = tmp_path / "second.lock"
    first = runner_module._acquire_case_lock(
        first_path, "first", wait_seconds=0.0
    )
    second = runner_module._acquire_case_lock(
        second_path, "second", wait_seconds=0.0
    )
    assert first is not None and second is not None
    real_unlink = Path.unlink
    injected = False

    def fail_first_once(path: Path, *args: object, **kwargs: object) -> None:
        nonlocal injected
        if path == first_path and not injected:
            injected = True
            raise OSError("injected unlink failure")
        real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_first_once)
    runner_module._release_case_lock(first)
    runner_module._release_case_lock(second)
    assert first_path.exists()
    assert not first["released"]
    assert not second_path.exists()
    assert second["released"]

    runner_module._release_case_lock(first)
    assert not first_path.exists()
    assert first["released"]


def test_publication_commit_point_is_fail_closed_and_hash_bound(
    tmp_path: Path,
) -> None:
    artifacts = ("outputs/a.txt", "outputs/b.txt")
    final_a = tmp_path / artifacts[0]
    final_b = tmp_path / artifacts[1]
    final_a.parent.mkdir(parents=True, exist_ok=True)
    final_a.write_text("old-a\n", encoding="utf-8")
    final_b.write_text("old-b\n", encoding="utf-8")
    completion = tmp_path / "artifacts/gates/completion.json"
    metadata = {
        "scope": "formal",
        "implementation_source_bundle_sha256": "a" * 64,
        "protocol_manifest_sha256": "b" * 64,
    }

    stage = create_staging_root(tmp_path, "formal")
    for relative, value in zip(artifacts, ("new-a\n", "new-b\n")):
        path = stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    bindings = publication_artifact_bindings(stage, artifacts)
    transaction = begin_completion(
        completion, metadata, expected_bindings=bindings
    )

    def fail_after_first(index: int, _relative: str) -> None:
        if index == 1:
            raise RuntimeError("injected promotion failure")

    with pytest.raises(RuntimeError, match="injected promotion failure"):
        promote_staged_artifacts(
            stage,
            tmp_path,
            artifacts,
            bindings,
            after_replace=fail_after_first,
        )
    assert json.loads(completion.read_text(encoding="utf-8"))["status"] == "IN_PROGRESS"

    retry_stage = create_staging_root(tmp_path, "formal")
    for relative, value in zip(artifacts, ("new-a\n", "new-b\n")):
        path = retry_stage / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    retry_bindings = publication_artifact_bindings(retry_stage, artifacts)
    promote_staged_artifacts(retry_stage, tmp_path, artifacts, retry_bindings)
    final_b.write_text("raced-tamper\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="differ from the validated staging"):
        complete_publication(
            completion,
            metadata,
            root=tmp_path,
            artifact_paths=artifacts,
            expected_bindings=retry_bindings,
            publication_id=str(transaction["publication_id"]),
        )
    assert json.loads(completion.read_text(encoding="utf-8"))["status"] == "IN_PROGRESS"
    final_b.write_text("new-b\n", encoding="utf-8")
    complete_publication(
        completion,
        metadata,
        root=tmp_path,
        artifact_paths=artifacts,
        expected_bindings=retry_bindings,
        publication_id=str(transaction["publication_id"]),
    )
    assert completion_validation_errors(
        tmp_path,
        completion,
        expected_scope="formal",
        expected_source_bundle_sha256="a" * 64,
        expected_protocol_manifest_sha256="b" * 64,
        expected_artifact_paths=artifacts,
    ) == []

    final_b.write_text("tampered\n", encoding="utf-8")
    assert any(
        "SHA-256 mismatch" in error
        for error in completion_validation_errors(
            tmp_path,
            completion,
            expected_scope="formal",
            expected_source_bundle_sha256="a" * 64,
            expected_protocol_manifest_sha256="b" * 64,
            expected_artifact_paths=artifacts,
        )
    )


def test_execute_only_does_not_overwrite_published_protocol(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    protocol_path = tmp_path / "published-protocol.json"
    protocol_path.write_text('{"old":true}\n', encoding="utf-8")
    monkeypatch.setattr(runner_module, "PROTOCOL_PATH", protocol_path)
    monkeypatch.setattr(runner_module, "assert_canonical_map", lambda _path: None)
    monkeypatch.setattr(
        runner_module,
        "canonical_map_identity",
        lambda: {"fixture": "map"},
    )
    monkeypatch.setattr(
        runner_module,
        "load_source_task_snapshot",
        lambda: (
            [{}] * 43_603,
            {"raw_bytes_sha256": "c" * 64},
        ),
    )
    monkeypatch.setattr(
        runner_module,
        "assert_frozen_inputs_unchanged",
        lambda _source, _map: None,
    )
    monkeypatch.setattr(
        runner_module, "implementation_sha256", lambda _search_path: "d" * 64
    )
    monkeypatch.setattr(
        runner_module,
        "assert_implementation_unchanged",
        lambda _expected, _search_path: None,
    )
    monkeypatch.setattr(
        runner_module,
        "execute_case",
        lambda *_args, **_kwargs: ({}, {"status": "EXECUTED"}),
    )

    case_id = formal_cases()[0].case_id
    result = runner_module.main(
        [
            "--case",
            case_id,
            "--execute-only",
            "--measurement-cohort",
            "fixture",
            "--concurrent-worker-target",
            "1",
        ]
    )

    assert result == 0
    assert protocol_path.read_text(encoding="utf-8") == '{"old":true}\n'


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


def test_temporal_gate_counts_unrecovered_windows_as_explicit_negative_evidence() -> None:
    temporal = [case for case in formal_cases() if case.category == "temporal_fault"]
    rows = [
        {
            "case_id": case.case_id,
            "execution_status": "EXECUTED",
            "fault_recovery_pass": case.case_id != "fault_fault_policy_off",
            "fault_recovery_unobserved_count": (
                1 if case.case_id == "fault_fault_policy_off" else 0
            ),
        }
        for case in temporal
    ]

    gate = next(row for row in gate_rows(rows) if row["gate"] == "temporal_fault_recovery")
    assert gate["status"] == "PARTIAL_WITH_EXPLICIT_BLOCKER"
    assert f"executed={len(temporal)}/{len(temporal)}" in gate["evidence"]
    assert "unrecovered_windows=1" in gate["evidence"]


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
