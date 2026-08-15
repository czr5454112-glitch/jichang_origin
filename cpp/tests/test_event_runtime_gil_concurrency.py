from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from time import perf_counter

import czr005_cpp


NODE_RECORDS = [
    (0, 1, 0.01, 0, 0, [1, 2]),
    (1, 4, 0.01, 1, 0, [3]),
    (2, 4, 0.01, 1, 1, [3]),
    (3, 2, 0.0, 2, 0, []),
]
EDGE_RECORDS = [
    (0, 1, 1.0, 1.0),
    (0, 2, 1.0, 1.0),
    (1, 3, 1.0, 1.0),
    (2, 3, 1.0, 1.0),
]
HEURISTIC_TIME = [
    [0.0, 1.0, 1.0, 2.0],
    [1.0, 0.0, 1.0, 1.0],
    [1.0, 1.0, 0.0, 1.0],
    [2.0, 1.0, 1.0, 0.0],
]


def _arguments(
    *,
    bag_count: int = 32,
    **overrides: object,
) -> dict[str, object]:
    arguments: dict[str, object] = {
        "node_records": NODE_RECORDS,
        "edge_records": EDGE_RECORDS,
        "heuristic_time": HEURISTIC_TIME,
        "bag_records": [
            (
                f"gil-concurrency-{index}",
                index + 1,
                float(index) * 0.001,
                1_000.0,
                0,
                3,
                "gil-concurrency",
            )
            for index in range(bag_count)
        ],
        "fault_windows": [],
        "enable_source_admission": False,
        "enable_backpressure": False,
        "enable_pibt_lite": False,
        "enable_deadlock_escape": False,
        "pibt_mode": "P0",
        "scorer_mode": "S4",
        "retry_interval": 0.01,
        "max_events": 100_000,
        "max_simulation_time": 1_000.0,
        "trace_limit": 10_000,
        "event_trace_limit": 10_000,
        "scenario": "gil-concurrency-regression",
    }
    arguments.update(overrides)
    return arguments


def _run(**overrides: object) -> dict[str, object]:
    return czr005_cpp.g4irsf11_event_runtime_from_records(
        **_arguments(**overrides)
    )


def _logical_payload(payload: dict[str, object]) -> dict[str, object]:
    logical = deepcopy(payload)
    summary = logical["summary"]
    assert isinstance(summary, dict)
    for field in (
        "runtime_seconds",
        "decision_latency_us_p50",
        "decision_latency_us_p95",
        "decision_latency_us_p99",
        "event_throughput_per_second",
    ):
        summary.pop(field, None)
    return logical


def main() -> None:
    serial = _run()
    serial_summary = serial["summary"]
    assert isinstance(serial_summary, dict)
    assert serial_summary["completed_count"] == 32
    assert serial_summary["failed_count"] == 0
    assert serial_summary["reservation_conflicts"] == 0

    ready = Barrier(2)

    def concurrent_run() -> dict[str, object]:
        ready.wait()
        return _run()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(concurrent_run) for _ in range(2)]
        concurrent = [future.result(timeout=30.0) for future in futures]

    expected = _logical_payload(serial)
    assert _logical_payload(concurrent[0]) == expected
    assert _logical_payload(concurrent[1]) == expected

    # Prebuild Python inputs outside the measured intervals.  With the GIL
    # released around the pure-C++ runtime, the second thread enters Python
    # while the first native call is active and both bounded intervals overlap.
    # Removing gil_scoped_release makes these calls serialize and collapses
    # this overlap to (at most) a Python scheduling handoff.
    overlap_arguments = [
        _arguments(
            bag_count=1_000,
            bounded_wall_seconds=0.08,
            bounded_check_every_events=1,
            trace_limit=0,
            event_trace_limit=0,
            max_events=10_000_000,
            scenario=f"gil-overlap-{index}",
        )
        for index in range(2)
    ]
    overlap_ready = Barrier(2)

    def timed_bounded_run(
        arguments: dict[str, object],
    ) -> tuple[float, float, dict[str, object]]:
        overlap_ready.wait()
        started = perf_counter()
        payload = czr005_cpp.g4irsf11_event_runtime_from_records(
            **arguments
        )
        ended = perf_counter()
        return started, ended, payload

    with ThreadPoolExecutor(max_workers=2) as executor:
        overlap_futures = [
            executor.submit(timed_bounded_run, arguments)
            for arguments in overlap_arguments
        ]
        intervals = [
            future.result(timeout=10.0)
            for future in overlap_futures
        ]

    for started, ended, payload in intervals:
        assert ended > started
        assert payload["execution_status"] == "BOUNDED_PROGRESS"
        assert payload["summary"]["bounded_progress"] is True
    overlap_seconds = min(row[1] for row in intervals) - max(
        row[0] for row in intervals
    )
    assert overlap_seconds > 0.02, overlap_seconds

    bounded = _run(
        bounded_wall_seconds=1.0e-12,
        bounded_check_every_events=1,
    )
    assert bounded["execution_status"] == "BOUNDED_PROGRESS"
    assert bounded["stop_reason"] == "WALL_LIMIT"
    assert "bags" not in bounded
    assert bounded["summary"]["bounded_progress"] is True
    assert bounded["progress"]["phase"] == "READY"

    invalid = _arguments(bag_count=2)
    invalid["bag_records"][1] = invalid["bag_records"][0]
    try:
        czr005_cpp.g4irsf11_event_runtime_from_records(**invalid)
    except ValueError as exc:
        assert "segment_id values must be unique" in str(exc)
    else:
        raise AssertionError("duplicate segment IDs must fail during initialize")

    # The exception crosses the no-GIL scope.  Its RAII guard must reacquire
    # the GIL so ordinary Python work and a fresh native runtime remain valid.
    assert "".join(["python", "-continued"]) == "python-continued"
    recovered = _run(bag_count=1)
    assert recovered["summary"]["completed_count"] == 1
    assert recovered["summary"]["failed_count"] == 0


if __name__ == "__main__":
    main()
