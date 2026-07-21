from __future__ import annotations

from scripts.eval.g4irsf11_capacity_metrics import (
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
