from __future__ import annotations

from pathlib import Path

from czr005.io.legacy_map import parse_legacy_map
from czr005.sim_py import AStarPlanner, IcsGraph, ReferenceSimulator, ReservationTable, TaskStream

ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
PROCESSED = ROOT / "data" / "processed"


def _graph() -> IcsGraph:
    return IcsGraph.from_legacy_map(parse_legacy_map(LEGACY / "map2.txt"))


def test_astar_matches_legacy_smoke_paths() -> None:
    planner = AStarPlanner(_graph())
    cases = {
        (0, 47): [0, 6, 12, 13, 23, 24, 27, 28, 47],
        (52, 49): [52, 29, 30, 31, 32, 37, 49],
        (53, 50): [53, 20, 10, 15, 14, 46, 36, 44, 50],
    }

    for (start, goal), expected in cases.items():
        route = planner.plan(start=start, goal=goal)
        assert [node.location for node in route] == expected
        assert route[0].t1 == 0.0
        assert route[-1].location == goal
        assert all(left.t2 <= right.t1 for left, right in zip(route, route[1:]))

    route = planner.plan(start=3, goal=49)
    assert route[0].location == 3
    assert route[-1].location == 49
    assert all(left.t2 <= right.t1 for left, right in zip(route, route[1:]))


def test_reservation_blocks_overlapping_node_windows() -> None:
    graph = _graph()
    planner = AStarPlanner(graph)
    reservations = ReservationTable()

    first_route = planner.plan(start=0, goal=47, start_time=0.0, reservations=reservations, task_id=1)
    assert first_route
    reservations.add_route(1, first_route)

    blocked = planner.plan(start=0, goal=47, start_time=0.0, reservations=reservations, task_id=2)
    assert blocked == []

    later = planner.plan(
        start=0,
        goal=47,
        start_time=first_route[-1].t2 + 1.0,
        reservations=reservations,
        task_id=3,
    )
    assert [node.location for node in later] == [node.location for node in first_route]


def test_task_stream_and_reference_simulator_are_headless_and_structured() -> None:
    graph = IcsGraph.from_json(PROCESSED / "maps" / "map2.json")
    stream = TaskStream.from_jsonl(PROCESSED / "tasks" / "inputdata.jsonl")
    simulator = ReferenceSimulator(graph)

    result = simulator.run_episode(stream, max_tasks=8)
    log = result.to_log()

    assert result.metrics.planned_count == 8
    assert result.metrics.unplanned_count == 0
    assert result.metrics.reservation_conflicts == 0
    assert len(result.events) == 8
    assert set(log) == {"routes", "unplanned", "events", "metrics"}
    assert all(event["event"] == "planned" for event in result.events)
    assert all(route[0]["t1"] >= 0.0 for route in log["routes"].values())
