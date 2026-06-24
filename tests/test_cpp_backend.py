from __future__ import annotations

from pathlib import Path

import pytest

from czr005 import cpp_backend
from czr005.sim_py import IcsGraph, ReferenceSimulator, SimEdge, SimNode, TaskLeg, TaskStream


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"

NODE_RECORDS = [
    (0, 1, 0.0, 0, 0, [1]),
    (1, 4, 1.0, 1, 0, [2]),
    (2, 2, 0.0, 2, 0, []),
]
EDGE_RECORDS = [
    (0, 1, 5.0, 2.5),
    (1, 2, 5.0, 2.5),
]
HEURISTIC_TIME = [
    [0.0, 2.0, 4.0],
    [4.0, 0.0, 2.0],
    [4.0, 2.0, 0.0],
]
TASK_RECORDS = [
    ("reference-first", 201, 201, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", False, 1),
    ("reference-second", 202, 202, 6.0, 30.0, 0, 2, 0, 2, 6.0, "direct", False, 2),
]


def _require_cpp_backend() -> None:
    try:
        cpp_backend.load_cpp_module()
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def test_default_search_paths_include_cmake_build_trees() -> None:
    custom = ROOT / "custom_python"

    paths = cpp_backend.default_search_paths(custom)

    assert paths[0] == custom
    assert paths.index(ROOT / "build_vs" / "python" / "Release") < paths.index(
        ROOT / "build_vs" / "python" / "Debug"
    )
    assert ROOT / "build_vs" / "python" / "Debug" in paths
    assert ROOT / "build_vs" / "python" / "Release" in paths
    assert ROOT / "build_nmake" / "python" in paths


def test_cpp_backend_legacy_map_astar_smoke() -> None:
    _require_cpp_backend()

    map2 = LEGACY / "map2.txt"
    summary = cpp_backend.read_legacy_map_summary(map2)

    assert summary["node_count"] == 54
    assert summary["edge_count"] == 69
    assert cpp_backend.plan_legacy_map_path(map2, 0, 47) == [
        0,
        6,
        12,
        13,
        23,
        24,
        27,
        28,
        47,
    ]
    assert cpp_backend.plan_legacy_map_paths(map2, [(0, 47), (52, 49)]) == [
        [0, 6, 12, 13, 23, 24, 27, 28, 47],
        [52, 29, 30, 31, 32, 37, 49],
    ]


def test_cpp_backend_legacy_no_fault_window_smoke() -> None:
    _require_cpp_backend()

    result = cpp_backend.legacy_no_fault_window_summary(
        LEGACY / "map2.txt",
        LEGACY / "inputdata.txt",
        start_epoch=8260,
        max_epochs=512,
        max_new_tasks=0,
        include_routes=True,
    )

    assert result["epochs_run"] == 512
    assert result["generated_count"] == 1
    assert result["planned_count"] == 1
    assert result["completed_count"] == 1
    assert result["active_route_count"] == 0
    assert result["unfinished_count"] == 0
    assert result["route_size_checksum"] == 9
    assert result["route_location_checksum"] == 1293
    assert result["planned_routes"][0]["path"] == [3, 16, 17, 18, 22, 24, 27, 28, 47]


def test_cpp_backend_legacy_scheduled_fault_window_smoke() -> None:
    _require_cpp_backend()

    result = cpp_backend.legacy_scheduled_fault_window_summary(
        LEGACY / "map2.txt",
        LEGACY / "inputdata.txt",
        start_epoch=8260,
        max_epochs=512,
        max_new_tasks=0,
        fault_schedule=[(8260, 16, 17, False)],
        include_routes=True,
    )

    assert result["epochs_run"] == 512
    assert result["generated_count"] == 1
    assert result["planned_count"] == 1
    assert result["completed_count"] == 1
    assert result["fault_event_count"] == 1
    assert result["repair_event_count"] == 0
    assert result["active_fault_count"] == 1
    assert result["route_size_checksum"] == 8
    assert result["route_location_checksum"] == 1080
    assert result["planned_routes"][0]["path"] == [3, 16, 21, 23, 24, 27, 28, 47]


def test_cpp_backend_legacy_active_route_fault_window_smoke() -> None:
    _require_cpp_backend()

    result = cpp_backend.legacy_scheduled_fault_window_summary(
        LEGACY / "map2.txt",
        LEGACY / "inputdata.txt",
        start_epoch=8260,
        max_epochs=96,
        max_new_tasks=0,
        fault_schedule=[(8268, 3, 16, False), (8300, 3, 16, True)],
        include_routes=True,
    )

    assert result["generated_count"] == 1
    assert result["planned_count"] == 1
    assert result["completed_count"] == 0
    assert result["fault_event_count"] == 1
    assert result["repair_event_count"] == 1
    assert result["active_fault_count"] == 0
    assert result["active_route_count"] == 0
    assert result["route_size_checksum"] == 9
    assert result["route_location_checksum"] == 1293
    assert result["planned_routes"][0]["path"] == [3, 16, 17, 18, 22, 24, 27, 28, 47]


def test_cpp_backend_example1_ragged_heuristic_mode() -> None:
    _require_cpp_backend()

    example_map = LEGACY / "example1" / "map.txt"
    with pytest.raises(RuntimeError, match="heuristic row"):
        cpp_backend.read_legacy_map_summary(example_map)

    summary = cpp_backend.read_legacy_map_summary(example_map, allow_ragged_heuristic=True)

    assert summary["node_count"] == 11
    assert summary["edge_count"] == 13
    assert cpp_backend.plan_legacy_map_path(
        example_map,
        10,
        9,
        allow_ragged_heuristic=True,
    ) == [10, 2, 4, 6, 7, 9]


def test_cpp_backend_reference_simulator_matches_python_reference() -> None:
    _require_cpp_backend()

    graph = IcsGraph(
        nodes={
            location: SimNode(location, node_type, service_time, x, y, tuple(outgoing))
            for location, node_type, service_time, x, y, outgoing in NODE_RECORDS
        },
        edges={(start, end): SimEdge(start, end, length, speed) for start, end, length, speed in EDGE_RECORDS},
        heuristic_time=tuple(tuple(row) for row in HEURISTIC_TIME),
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=4.0,
    )
    tasks = TaskStream(TaskLeg(*record) for record in TASK_RECORDS)
    python_result = ReferenceSimulator(graph).run_episode(tasks, max_tasks=2)

    cpp_result = cpp_backend.reference_simulator_from_records(
        NODE_RECORDS,
        EDGE_RECORDS,
        HEURISTIC_TIME,
        TASK_RECORDS,
        max_tasks=2,
    )

    assert cpp_result["metrics"]["planned_count"] == python_result.metrics.planned_count
    assert cpp_result["metrics"]["unplanned_count"] == python_result.metrics.unplanned_count
    assert cpp_result["metrics"]["reservation_conflicts"] == python_result.metrics.reservation_conflicts
    assert cpp_result["metrics"]["mean_travel_time"] == python_result.metrics.mean_travel_time
    assert cpp_result["metrics"]["makespan"] == python_result.metrics.makespan
    assert [event["event"] for event in cpp_result["events"]] == [
        event["event"] for event in python_result.events
    ]
    assert [event["path"] for event in cpp_result["events"]] == [
        event["path"] for event in python_result.events
    ]

    cpp_fault_result = cpp_backend.reference_simulator_from_records(
        NODE_RECORDS,
        EDGE_RECORDS,
        HEURISTIC_TIME,
        TASK_RECORDS,
        max_tasks=1,
        fault_edges=[(1, 2)],
    )

    assert cpp_fault_result["metrics"]["planned_count"] == 0
    assert cpp_fault_result["metrics"]["unplanned_count"] == 1
    assert cpp_fault_result["events"][0]["event"] == "unplanned"
