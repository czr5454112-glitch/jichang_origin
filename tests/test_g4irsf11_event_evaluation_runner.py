from __future__ import annotations

from pathlib import Path

from scripts.eval.g4irsf11_evaluation_reporting import case_row, gate_rows
from scripts.eval.g4irsf11_experiment_protocol import formal_cases
from scripts.eval.g4irsf11_experiment_protocol import PROTOCOL_VERSION
from scripts.eval.run_g4irsf11_event_runtime_evaluation import (
    _descriptor_matches,
    _acquire_case_lock,
    _release_case_lock,
    timeline_spanning_sample,
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


def test_execution_descriptor_is_bound_to_exact_inputs_and_implementation() -> None:
    case = formal_cases()[0]
    descriptor = {
        "protocol_version": PROTOCOL_VERSION,
        "case": case.as_dict(),
        "source_sha256": "source",
        "map_sha256": "map",
        "implementation_sha256": "implementation",
        "status": "EXECUTED",
    }
    assert _descriptor_matches(
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
