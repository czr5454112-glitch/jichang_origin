from __future__ import annotations

from scripts.eval.run_g4irsf11_event_case import _outcomes


def test_outcomes_join_duplicate_task_id_by_runtime_and_segment_identity() -> None:
    segments = [
        {
            "runtime_bag_id": 10,
            "task_id": 77,
            "segment_id": "77:storage_in",
            "release_time": 1.0,
            "finish_time": 11.0,
            "completed": True,
            "total_local_wait": 2.0,
            "source_queue_delay": 0.5,
            "loop_count": 0,
            "failure_reason": "",
        },
        {
            "runtime_bag_id": 11,
            "task_id": 77,
            "segment_id": "77:storage_out",
            "release_time": 20.0,
            "finish_time": -1.0,
            "completed": False,
            "total_local_wait": 9.0,
            "source_queue_delay": 4.0,
            "loop_count": 1,
            "failure_reason": "time_limit_reached",
        },
    ]
    decisions = [
        {
            "decision_id": "storage-in-decision",
            "task_id": 77,
            "segment_id": "77:storage_in",
            "metadata": {"runtime_bag_id": 10},
        },
        {
            "decision_id": "storage-out-decision",
            "task_id": 77,
            "segment_id": "77:storage_out",
            "metadata": {"runtime_bag_id": 11},
        },
    ]

    rows = _outcomes(decisions, segments, fault_mode="no_fault")
    by_decision = {row["decision_id"]: row for row in rows}

    storage_in = by_decision["storage-in-decision"]
    assert storage_in["reached_goal"] is True
    assert storage_in["bag_tth_seconds"] == 10.0
    assert storage_in["local_wait_seconds"] == 2.0
    assert storage_in["loop_or_dead_end"] is False

    storage_out = by_decision["storage-out-decision"]
    assert storage_out["reached_goal"] is False
    assert storage_out["bag_tth_seconds"] == 0.0
    assert storage_out["local_wait_seconds"] == 9.0
    assert storage_out["loop_or_dead_end"] is True


def test_fault_outcome_exposure_can_come_from_non_training_hold_attempt() -> None:
    segment = {
        "runtime_bag_id": 10,
        "task_id": 77,
        "segment_id": "77:storage_in",
        "release_time": 1.0,
        "finish_time": 11.0,
        "completed": True,
        "total_local_wait": 2.0,
        "source_queue_delay": 0.5,
        "loop_count": 0,
        "failure_reason": "",
    }
    decision = {
        "decision_id": "committed",
        "task_id": 77,
        "segment_id": "77:storage_in",
        "metadata": {"runtime_bag_id": 10},
        "local_snapshot": {"faulted_outgoing_count": 0},
        "candidate_records": [],
    }
    hold = {
        "task_id": 77,
        "segment_id": "77:storage_in",
        "metadata": {"runtime_bag_id": 10},
        "local_snapshot": {"faulted_outgoing_count": 1},
        "candidate_records": [],
    }
    rows = _outcomes(
        [decision],
        [segment],
        fault_mode="single_delayed_30s",
        exposure_rows=[hold],
    )
    assert rows[0]["fault_recovery_outcome"] == "recovered"

    unexposed = _outcomes(
        [decision],
        [segment],
        fault_mode="single_delayed_30s",
        exposure_rows=[],
    )
    assert unexposed[0]["fault_recovery_outcome"] == "not_exposed"
