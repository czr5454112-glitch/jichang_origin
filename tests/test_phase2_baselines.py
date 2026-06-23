from __future__ import annotations

from czr005.baselines import (
    AgentState,
    PeriodicReplanningBaseline,
    PIBTActiveBagReplayBaseline,
    PIBTStyleOneStepResolver,
    RollingHorizonBaseline,
    SIPPPlanner,
)
from czr005.sim_py import AStarPlanner, EdgeReservationTable, IcsGraph, ReservationTable, SimEdge, SimNode
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


def _handoff_graph() -> IcsGraph:
    return IcsGraph(
        nodes={
            0: SimNode(location=0, node_type=1, service_time=0.0, x=0, y=0, outgoing=(1, 2)),
            1: SimNode(location=1, node_type=4, service_time=0.0, x=1, y=0, outgoing=(0, 3)),
            2: SimNode(location=2, node_type=4, service_time=0.0, x=1, y=1, outgoing=(3,)),
            3: SimNode(location=3, node_type=2, service_time=0.0, x=2, y=0, outgoing=()),
        },
        edges={
            (0, 1): SimEdge(start=0, end=1, length=5.0, speed=2.5),
            (0, 2): SimEdge(start=0, end=2, length=7.5, speed=2.5),
            (1, 0): SimEdge(start=1, end=0, length=5.0, speed=2.5),
            (1, 3): SimEdge(start=1, end=3, length=5.0, speed=2.5),
            (2, 3): SimEdge(start=2, end=3, length=5.0, speed=2.5),
        },
        heuristic_time=(
            (0.0, 2.0, 3.0, 4.0),
            (2.0, 0.0, 5.0, 2.0),
            (999.0, 999.0, 0.0, 2.0),
            (999.0, 999.0, 999.0, 0.0),
        ),
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )


def _single_edge_goal_graph() -> IcsGraph:
    return IcsGraph(
        nodes={
            0: SimNode(location=0, node_type=1, service_time=0.0, x=0, y=0, outgoing=(1,)),
            1: SimNode(location=1, node_type=2, service_time=0.0, x=1, y=0, outgoing=()),
        },
        edges={(0, 1): SimEdge(start=0, end=1, length=5.0, speed=2.5)},
        heuristic_time=((0.0, 2.0), (2.0, 0.0)),
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


def test_sipp_waits_for_edge_capacity() -> None:
    edge_reservations = EdgeReservationTable()
    edge_reservations.reserve(task_id=99, start_node=0, end_node=1, start=0.0, end=2.0)

    route = SIPPPlanner(_line_graph()).plan(
        0,
        2,
        edge_reservations=edge_reservations,
        edge_capacity=1,
        task_id=1,
    )

    assert [node.location for node in route] == [0, 1, 2]
    assert route[1].t1 >= 4.0
    assert not edge_reservations.has_capacity_conflict(0, 1, route[1].t1 - 2.0, route[1].t1, 1, task_id=1)


def test_sipp_waits_for_edge_headway() -> None:
    edge_reservations = EdgeReservationTable()
    edge_reservations.reserve(task_id=99, start_node=0, end_node=1, start=0.0, end=0.5)

    route = SIPPPlanner(_line_graph()).plan(
        0,
        2,
        edge_reservations=edge_reservations,
        edge_capacity=2,
        edge_headway_seconds=2.0,
        task_id=1,
    )

    assert [node.location for node in route] == [0, 1, 2]
    assert route[1].t1 >= 4.0
    assert not edge_reservations.has_headway_conflict(0, 1, route[1].t1 - 2.0, 2.0, task_id=1)


def _task(segment_id: str, task_id: int, pass_time: float, std: float, goal: int = 2) -> TaskLeg:
    return TaskLeg(
        segment_id=segment_id,
        task_id=task_id,
        pallet_id=task_id,
        pass_time=pass_time,
        std=std,
        start=0,
        goal=goal,
        original_start=0,
        original_goal=goal,
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


def test_rolling_horizon_reserves_edge_capacity() -> None:
    tasks = (
        _task("urgent", 1, pass_time=0.0, std=10.0, goal=1),
        _task("loose", 2, pass_time=0.1, std=20.0, goal=1),
    )

    result = RollingHorizonBaseline(
        _single_edge_goal_graph(),
        horizon_seconds=60.0,
        edge_capacity=1,
    ).run_episode(tasks)

    assert result.metrics.planned_count == 2
    assert result.routes["urgent"][1].t1 == 2.0
    assert result.routes["loose"][1].t1 >= 4.0


def test_rolling_horizon_reserves_edge_headway() -> None:
    tasks = (
        _task("urgent", 1, pass_time=0.0, std=10.0, goal=1),
        _task("loose", 2, pass_time=0.1, std=20.0, goal=1),
    )

    result = RollingHorizonBaseline(
        _single_edge_goal_graph(),
        horizon_seconds=60.0,
        edge_capacity=2,
        edge_headway_seconds=2.0,
    ).run_episode(tasks)

    assert result.metrics.planned_count == 2
    assert result.routes["urgent"][1].t1 == 2.0
    assert result.routes["loose"][1].t1 >= 4.0


def test_periodic_replanning_commits_one_step_per_tick() -> None:
    result = PeriodicReplanningBaseline(
        _line_graph(),
        interval_seconds=2.0,
        max_ticks=16,
    ).run_episode((_task("active", 7, pass_time=0.0, std=20.0),))

    move_events = [event for event in result.events if event["event"] == "replan_move"]
    assert result.metrics.planned_count == 1
    assert result.metrics.unplanned_count == 0
    assert result.metrics.reservation_conflicts == 0
    assert [event["planned_path"] for event in move_events] == [[0, 1, 2], [1, 2]]
    assert result.events[-1]["event"] == "planned"
    assert result.events[-1]["path"] == [0, 1, 2]


def test_periodic_replanning_uses_fault_safe_alternative() -> None:
    result = PeriodicReplanningBaseline(
        _branch_graph(),
        interval_seconds=2.0,
        max_ticks=16,
    ).run_episode(
        (_task("fault-alt", 8, pass_time=0.0, std=20.0, goal=3),),
        fault_edges={(0, 1)},
    )

    move_events = [event for event in result.events if event["event"] == "replan_move"]
    assert result.metrics.planned_count == 1
    assert move_events[0]["current"] == 0
    assert move_events[0]["next_node"] == 2


def test_periodic_replanning_respects_repair_windows() -> None:
    active_window_result = PeriodicReplanningBaseline(
        _branch_graph(),
        interval_seconds=2.0,
        max_ticks=16,
    ).run_episode(
        (_task("during-window", 9, pass_time=0.0, std=20.0, goal=3),),
        fault_windows=((0, 1, 0.0, 5.0),),
    )
    repaired_result = PeriodicReplanningBaseline(
        _branch_graph(),
        interval_seconds=2.0,
        max_ticks=16,
    ).run_episode(
        (_task("after-window", 10, pass_time=6.0, std=26.0, goal=3),),
        fault_windows=((0, 1, 0.0, 5.0),),
    )

    active_move_events = [event for event in active_window_result.events if event["event"] == "replan_move"]
    repaired_move_events = [event for event in repaired_result.events if event["event"] == "replan_move"]
    assert active_window_result.metrics.planned_count == 1
    assert repaired_result.metrics.planned_count == 1
    assert active_move_events[0]["next_node"] == 2
    assert repaired_move_events[0]["next_node"] == 1


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


def test_pibt_style_resolver_respects_edge_capacity_reservation() -> None:
    edge_reservations = EdgeReservationTable()
    edge_reservations.reserve(task_id=99, start_node=0, end_node=1, start=0.0, end=2.0)

    actions = PIBTStyleOneStepResolver(_single_edge_goal_graph()).resolve(
        (AgentState(task_id=3, current=0, goal=1, ready_time=0.0, deadline=20.0),),
        edge_reservations=edge_reservations,
        edge_capacity=1,
    )

    assert len(actions) == 1
    assert actions[0].action == "hold"
    assert actions[0].reason == "no_safe_edge"


def test_pibt_style_resolver_uses_recursive_handoff() -> None:
    actions = PIBTStyleOneStepResolver(_handoff_graph()).resolve(
        (
            AgentState(task_id=1, current=0, goal=3, ready_time=0.0, deadline=10.0),
            AgentState(task_id=2, current=1, goal=3, ready_time=0.0, deadline=100.0),
        )
    )

    by_task = {action.task_id: action for action in actions}
    assert [action.task_id for action in actions] == [1, 2]
    assert by_task[1].action == "move"
    assert by_task[1].next_node == 1
    assert by_task[1].reason == "priority_inheritance"
    assert by_task[2].action == "move"
    assert by_task[2].next_node == 3
    assert by_task[2].reason == "inherited_move"


def test_pibt_style_resolver_uses_alternative_when_blocker_cannot_handoff() -> None:
    actions = PIBTStyleOneStepResolver(_handoff_graph()).resolve(
        (
            AgentState(task_id=1, current=0, goal=3, ready_time=0.0, deadline=10.0),
            AgentState(task_id=2, current=1, goal=0, ready_time=0.0, deadline=100.0),
        )
    )

    by_task = {action.task_id: action for action in actions}
    assert by_task[1].action == "move"
    assert by_task[1].next_node == 2
    assert by_task[1].reason == "best_safe_edge"
    assert by_task[2].action == "move"
    assert by_task[2].next_node == 0


def test_pibt_active_bag_replay_runs_recursive_handoff_slice() -> None:
    tasks = (
        TaskLeg("handoff-high", 1, 1, 0.0, 20.0, 0, 3, 0, 3, 0.0, "direct", False, 1),
        TaskLeg("handoff-blocker", 2, 2, 0.0, 100.0, 1, 3, 1, 3, 0.0, "direct", False, 2),
    )

    baseline = PIBTActiveBagReplayBaseline(
        _handoff_graph(),
        interval_seconds=2.0,
        hold_seconds=2.0,
        max_ticks=16,
    )
    result = baseline.run_episode(tasks)

    first_slice_moves = [
        event for event in result.events if event["event"] == "pibt_move" and event["tick_time"] == 0.0
    ]
    assert result.metrics.planned_count == 2
    assert baseline.summary.post_shield_conflicts == 0
    assert [(event["task_id"], event["next_node"], event["reason"]) for event in first_slice_moves] == [
        (1, 1, "priority_inheritance"),
        (2, 3, "inherited_move"),
    ]
