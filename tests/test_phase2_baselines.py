from __future__ import annotations

from czr005.baselines import SIPPPlanner
from czr005.sim_py import AStarPlanner, IcsGraph, ReservationTable, SimEdge, SimNode


def _line_graph() -> IcsGraph:
    return IcsGraph(
        nodes={
            0: SimNode(location=0, node_type=1, service_time=0.0, x=0, y=0, outgoing=(1,)),
            1: SimNode(location=1, node_type=4, service_time=1.0, x=1, y=0, outgoing=(2,)),
            2: SimNode(location=2, node_type=2, service_time=0.0, x=2, y=0, outgoing=()),
        },
        edges={
            (0, 1): SimEdge(start=0, end=1, length=5.0, speed=2.5),
            (1, 2): SimEdge(start=1, end=2, length=5.0, speed=2.5),
        },
        heuristic_time=((0.0, 2.0, 4.0), (4.0, 0.0, 2.0), (4.0, 2.0, 0.0)),
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )


def test_sipp_waits_for_next_safe_node_interval() -> None:
    graph = _line_graph()
    reservations = ReservationTable()
    reservations.reserve(task_id=99, node=1, start=2.0, end=3.0)

    naive_route = AStarPlanner(graph).plan(0, 2, reservations=reservations, task_id=1)
    assert naive_route == []

    route = SIPPPlanner(graph).plan(0, 2, reservations=reservations, task_id=1)
    assert [node.location for node in route] == [0, 1, 2]
    assert route[1].t1 > 3.0
    assert route[1].t2 > route[1].t1
    assert all(left.t2 <= right.t1 for left, right in zip(route, route[1:]))
    assert not reservations.has_conflict(1, route[1].t1, route[1].t2, task_id=1)


def test_sipp_respects_fault_edges() -> None:
    route = SIPPPlanner(_line_graph()).plan(0, 2, fault_edges={(1, 2)})
    assert route == []
