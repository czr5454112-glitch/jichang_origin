from __future__ import annotations

from scripts.eval.g4irsf11_capacity_metrics import (
    BACKLOG_AREA_METHOD_OBSERVATION_END_V2,
    CapacityGateConfig,
    backlog_metrics,
    capacity_metrics,
    current_peak_working_set_bytes,
    process_working_set_bytes,
)


def _bag(task_id: int, release: float, admitted: float, finish: float) -> dict:
    return {
        "task_id": task_id,
        "release_time": release,
        "admitted_time": admitted,
        "finish_time": finish,
        "deadline": release + 20.0,
        "total_wait": admitted - release,
        "complete": True,
    }


def test_capacity_requires_safety_stability_and_service() -> None:
    bags = [_bag(index, index * 10.0, index * 10.0, index * 10.0 + 4.0) for index in range(30)]
    summary = {
        "conflict_count": 0,
        "runtime_full_astar_calls": 0,
        "event_count": 300,
        "decision_count": 120,
        "runtime_seconds": 2.0,
        "decision_latency_us_p99": 7.0,
    }
    gate = CapacityGateConfig(
        max_backlog_slope_fraction=0.0,
        max_drain_seconds=10.0,
        max_p95_total_seconds=10.0,
        max_p99_total_seconds=10.0,
        starvation_seconds=10.0,
    )

    row = capacity_metrics(bags, summary, gate)

    assert row["safe_execution_pass"] is True
    assert row["queue_stability_pass"] is True
    assert row["service_level_pass"] is True
    assert row["capacity_pass"] is True
    assert row["event_throughput_per_second"] == 150.0
    assert row["decision_throughput_per_second"] == 60.0


def test_completion_alone_does_not_pass_overloaded_queue() -> None:
    bags = [_bag(index, float(index), float(index), 100.0 + index * 5.0) for index in range(30)]
    gate = CapacityGateConfig(
        max_backlog_slope_fraction=0.0,
        max_drain_seconds=30.0,
        max_p95_total_seconds=20.0,
        max_p99_total_seconds=30.0,
        starvation_seconds=20.0,
    )

    row = capacity_metrics(
        bags,
        {"conflict_count": 0, "runtime_full_astar_calls": 0},
        gate,
    )

    assert row["complete_count"] == 30
    assert row["safe_execution_pass"] is True
    assert row["queue_stability_pass"] is False
    assert row["service_level_pass"] is False
    assert row["capacity_pass"] is False


def test_backlog_keeps_unfinished_work_at_end() -> None:
    metrics = backlog_metrics([0.0, 1.0, 2.0], [3.0])
    assert metrics.end_backlog == 2
    assert metrics.peak_backlog == 3
    assert metrics.drain_time_seconds == 1.0


def test_incomplete_backlog_tail_is_integrated_to_observation_end() -> None:
    metrics = backlog_metrics(
        [0.0, 1.0, 2.0], [3.0], observation_end=10.0
    )

    # Legacy area through the last event is 6 bag-seconds. Two bags remain
    # for the seven-second observation tail, so the fixed-horizon area is 20.
    assert metrics.backlog_area_seconds == 20.0
    assert metrics.observation_end_seconds == 10.0
    assert metrics.last_event_time_seconds == 3.0
    assert metrics.backlog_area_method == BACKLOG_AREA_METHOD_OBSERVATION_END_V2
    assert metrics.tail_extension_area_seconds == 14.0


def test_complete_backlog_area_is_unchanged_by_later_observation_end() -> None:
    legacy = backlog_metrics([0.0, 1.0], [2.0, 3.0])
    fixed = backlog_metrics(
        [0.0, 1.0], [2.0, 3.0], observation_end=10.0
    )

    assert fixed.end_backlog == 0
    assert fixed.backlog_area_seconds == legacy.backlog_area_seconds
    assert fixed.tail_extension_area_seconds == 0.0


def test_observation_end_before_last_event_is_rejected() -> None:
    try:
        backlog_metrics([0.0, 2.0], [3.0], observation_end=2.5)
    except ValueError as exc:
        assert "last event" in str(exc)
    else:
        raise AssertionError("observation_end before the last event was accepted")


def test_fixed_horizon_examples_cover_late_arrival_and_no_departure() -> None:
    assert (
        backlog_metrics([0.0, 10.0], [5.0], observation_end=20.0)
        .backlog_area_seconds
        == 15.0
    )
    no_departure = backlog_metrics([2.0, 4.0], [], observation_end=10.0)
    assert no_departure.backlog_area_seconds == 14.0
    assert no_departure.tail_extension_area_seconds == 12.0


def test_nonfinite_observation_end_is_rejected() -> None:
    for value in (float("nan"), float("inf"), True):
        try:
            backlog_metrics([0.0], [], observation_end=value)
        except ValueError as exc:
            assert "finite" in str(exc)
        else:
            raise AssertionError(f"invalid observation_end was accepted: {value!r}")


def test_peak_memory_is_os_measurement() -> None:
    current, peak = process_working_set_bytes()
    assert current > 0
    assert peak >= current
    assert current_peak_working_set_bytes() >= current


def test_slowly_positive_backlog_slope_never_passes_capacity() -> None:
    bags = [
        _bag(index, float(index), float(index), float(index) / 0.995)
        for index in range(1000)
    ]
    gate = CapacityGateConfig(
        max_backlog_slope_fraction=0.0,
        max_drain_seconds=10.0,
        max_p95_total_seconds=20.0,
        max_p99_total_seconds=20.0,
        starvation_seconds=20.0,
    )

    row = capacity_metrics(
        bags,
        {"conflict_count": 0, "runtime_full_astar_calls": 0},
        gate,
    )

    assert row["backlog_slope_per_second"] > 0.0
    assert row["backlog_slope_fraction_of_arrival_rate"] > 0.0
    assert row["queue_slope_pass"] is False
    assert row["queue_stability_pass"] is False
    assert row["capacity_pass"] is False


def test_missing_safety_summary_is_unverified_and_fails_closed() -> None:
    bags = [_bag(0, 0.0, 0.0, 1.0)]
    gate = CapacityGateConfig(
        max_backlog_slope_fraction=0.0,
        max_drain_seconds=10.0,
        max_p95_total_seconds=10.0,
        max_p99_total_seconds=10.0,
    )

    row = capacity_metrics(bags, {}, gate)

    assert row["safety_evidence_status"] == "UNVERIFIED_MISSING_REQUIRED_SUMMARY"
    assert row["missing_required_summary_fields"] == [
        "reservation_conflicts",
        "runtime_full_astar_calls",
    ]
    assert row["safe_execution_pass"] is False
    assert row["capacity_pass"] is False


def test_nonfinite_or_fractional_safety_counters_fail_closed() -> None:
    gate = CapacityGateConfig(
        max_backlog_slope_fraction=0.0,
        max_drain_seconds=10.0,
        max_p95_total_seconds=10.0,
        max_p99_total_seconds=10.0,
    )
    row = capacity_metrics(
        [_bag(0, 0.0, 0.0, 1.0)],
        {"reservation_conflicts": "NAN", "runtime_full_astar_calls": 0.5},
        gate,
    )
    assert row["safe_execution_pass"] is False
    assert row["missing_required_summary_fields"] == [
        "reservation_conflicts:invalid",
        "runtime_full_astar_calls:invalid",
    ]
