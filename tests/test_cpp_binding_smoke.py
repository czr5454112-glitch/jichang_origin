from __future__ import annotations

from pathlib import Path

import pytest

from czr005 import cpp_backend


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"


def _require_cpp_backend() -> None:
    try:
        cpp_backend.load_cpp_module()
    except cpp_backend.CppBackendUnavailable as exc:
        pytest.skip(str(exc))


def test_cpp_binding_smoke_matches_master_plan_gate() -> None:
    _require_cpp_backend()

    map2 = LEGACY / "map2.txt"
    inputdata = LEGACY / "inputdata.txt"

    map_summary = cpp_backend.read_legacy_map_summary(map2)
    task_summary = cpp_backend.read_legacy_task_summary(inputdata)

    assert map_summary["node_count"] == 54
    assert map_summary["edge_count"] == 69
    assert task_summary["expanded_task_count"] == 43603
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


def test_cpp_binding_reference_simulator_records_smoke() -> None:
    _require_cpp_backend()

    node_records = [
        (0, 1, 0.0, 0, 0, [1]),
        (1, 4, 1.0, 1, 0, [2]),
        (2, 2, 0.0, 2, 0, []),
    ]
    edge_records = [
        (0, 1, 5.0, 2.5),
        (1, 2, 5.0, 2.5),
    ]
    heuristic_time = [
        [0.0, 2.0, 4.0],
        [4.0, 0.0, 2.0],
        [4.0, 2.0, 0.0],
    ]
    task_records = [
        ("first", 301, 301, 0.0, 20.0, 0, 2, 0, 2, 0.0, "direct", False, 1),
        ("second", 302, 302, 6.0, 30.0, 0, 2, 0, 2, 6.0, "direct", False, 2),
    ]

    result = cpp_backend.reference_simulator_from_records(
        node_records,
        edge_records,
        heuristic_time,
        task_records,
        max_tasks=2,
    )

    assert result["metrics"]["planned_count"] == 2
    assert result["metrics"]["unplanned_count"] == 0
    assert result["metrics"]["reservation_conflicts"] == 0
    assert [event["event"] for event in result["events"]] == ["planned", "planned"]
    assert [event["path"] for event in result["events"]] == [[0, 1, 2], [0, 1, 2]]
