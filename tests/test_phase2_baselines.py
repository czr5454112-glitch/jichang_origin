from __future__ import annotations

from czr005.baselines import AgentState, PIBTStyleOneStepResolver, RollingHorizonBaseline, SIPPPlanner
from czr005.sim_py import AStarPlanner, IcsGraph, ReservationTable, SimEdge, SimNode
from czr005.sim_py.task_stream import TaskLeg


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


def _merge_graph() -> IcsGraph:
    return IcsGraph(
        nodes={
            0: SimNode(location=0, node_type=1, service_time=0.0, x=0, y=0, outgoing=(2,)),
            1: SimNode(location=1, node_type=1, service_time=0.0, x=0, y=1, outgoing=(2,)),
            2: SimNode(location=2, node_type=4, service_time=1.0, x=1, y=0, outgoing=(3,)),
            3: SimNode(location=3, node_type=2, service_time=0.0, x=2, y=0, outgoing=()),
        },
        edges={
            (0, 2): SimEdge(start=0, end=2, length=5.0, speed=2.5),
            (1, 2): SimEdge(start=1, end=2, length=5.0, speed=2.5),
            (2, 3): SimEdge(start=2, end=3, length=5.0, speed=2.5),
        },
        heuristic_time=(
            (0.0, 4.0, 2.0, 4.0),
            (4.0, 0.0, 2.0, 4.0),
            (4.0, 4.0, 0.0, 2.0),
            (4.0, 4.0, 2.0, 0.0),
        ),
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )


def _branch_graph() -> IcsGraph:
    return IcsGraph(
        nodes={
            0: SimNode(location=0, node_type=1, service_time=0.0, x=0, y=0, outgoing=(1, 2)),
            1: SimNode(location=1, node_type=4, service_time=0.0, x=1, y=0, outgoing=(3,)),
            2: SimNode(location=2, node_type=4, service_time=0.0, x=1, y=1, outgoing=(3,)),
            3: SimNode(location=3, node_type=2, service_time=0.0, x=2, y=0, outgoing=()),
        },
        edges={
            (0, 1): SimEdge(start=0, end=1, length=5.0, speed=2.5),
            (0, 2): SimEdge(start=0, end=2, length=5.0, speed=2.5),
            (1, 3): SimEdge(start=1, end=3, length=5.0, speed=2.5),
            (2, 3): SimEdge(start=2, end=3, length=7.5, speed=2.5),
        },
        heuristic_time=(
            (0.0, 2.0, 3.0, 4.0),
            (4.0, 0.0, 4.0, 2.0),
            (4.0, 4.0, 0.0, 3.0),
            (4.0, 2.0, 3.0, 0.0),
        ),
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


def _task(segment_id: str, task_id: int, pass_time: float, std: float) -> TaskLeg:
    return TaskLeg(
        segment_id=segment_id,
        task_id=task_id,
        pallet_id=task_id,
        pass_time=pass_time,
        std=std,
        start=0,
        goal=2,
        original_start=0,
        original_goal=2,
        original_entry_time=pass_time,
        leg="direct",
        early_bag_split=False,
        source_line=task_id + 1,
    )


def test_rolling_horizon_prioritizes_deadline_slack_and_reserves_routes() -> None:
    tasks = (
        _task("loose", 1, pass_time=0.1, std=100.0),
        _task("urgent", 2, pass_time=0.0, std=20.0),
    )

    result = RollingHorizonBaseline(_line_graph(), horizon_seconds=60.0).run_episode(tasks)

    assert result.metrics.planned_count == 2
    assert result.metrics.unplanned_count == 0
    assert result.metrics.reservation_conflicts == 0
    assert [event["segment_id"] for event in result.events] == ["urgent", "loose"]
    assert result.routes["urgent"][1].t1 == 2.0
    assert result.routes["loose"][1].t1 > result.routes["urgent"][1].t2


def test_rolling_horizon_reports_fault_unplanned() -> None:
    result = RollingHorizonBaseline(_line_graph()).run_episode(
        (_task("faulted", 3, pass_time=0.0, std=20.0),),
        fault_edges={(1, 2)},
    )

    assert result.metrics.planned_count == 0
    assert result.metrics.unplanned_count == 1
    assert result.events[0]["event"] == "unplanned"
    assert result.events[0]["baseline"] == "rolling_horizon_sipp"


def test_pibt_style_resolver_prioritizes_merge_conflict() -> None:
    actions = PIBTStyleOneStepResolver(_merge_graph()).resolve(
        (
            AgentState(task_id=1, current=0, goal=3, ready_time=0.0, deadline=100.0),
            AgentState(task_id=2, current=1, goal=3, ready_time=0.0, deadline=20.0),
        )
    )

    by_task = {action.task_id: action for action in actions}
    assert [action.task_id for action in actions] == [2, 1]
    assert by_task[2].action == "move"
    assert by_task[2].next_node == 2
    assert by_task[1].action == "hold"
    assert by_task[1].reason == "no_safe_edge"


def test_pibt_style_resolver_uses_fault_safe_alternative() -> None:
    actions = PIBTStyleOneStepResolver(_branch_graph()).resolve(
        (AgentState(task_id=3, current=0, goal=3, ready_time=0.0, deadline=20.0),),
        fault_edges={(0, 1)},
    )

    assert len(actions) == 1
    assert actions[0].action == "move"
    assert actions[0].next_node == 2
