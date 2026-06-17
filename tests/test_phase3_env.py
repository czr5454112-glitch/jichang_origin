from __future__ import annotations

from czr005.envs import (
    IcsJunctionEnv,
    VectorizedIcsEnv,
    astar_guided_policy_factory,
    build_action_candidates,
    shortest_safe_policy,
)
from czr005.sim_py import EdgeReservationTable, IcsGraph, ReservationTable, SimEdge, SimNode
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
            (0, 2): SimEdge(start=0, end=2, length=7.5, speed=2.5),
            (1, 3): SimEdge(start=1, end=3, length=5.0, speed=2.5),
            (2, 3): SimEdge(start=2, end=3, length=5.0, speed=2.5),
        },
        heuristic_time=(
            (0.0, 2.0, 3.0, 4.0),
            (4.0, 0.0, 4.0, 2.0),
            (4.0, 4.0, 0.0, 2.0),
            (4.0, 2.0, 2.0, 0.0),
        ),
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )


def _dead_end_branch_graph() -> IcsGraph:
    return IcsGraph(
        nodes={
            0: SimNode(location=0, node_type=1, service_time=0.0, x=0, y=0, outgoing=(1, 2)),
            1: SimNode(location=1, node_type=4, service_time=0.0, x=1, y=1, outgoing=()),
            2: SimNode(location=2, node_type=4, service_time=0.0, x=1, y=0, outgoing=(3,)),
            3: SimNode(location=3, node_type=2, service_time=0.0, x=2, y=0, outgoing=()),
        },
        edges={
            (0, 1): SimEdge(start=0, end=1, length=5.0, speed=2.5),
            (0, 2): SimEdge(start=0, end=2, length=5.0, speed=2.5),
            (2, 3): SimEdge(start=2, end=3, length=5.0, speed=2.5),
        },
        heuristic_time=(
            (0.0, 2.0, 2.0, 4.0),
            (4.0, 0.0, 4.0, 4.0),
            (4.0, 4.0, 0.0, 2.0),
            (4.0, 4.0, 2.0, 0.0),
        ),
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )


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


def test_action_mask_blocks_fault_and_edge_capacity() -> None:
    graph = _line_graph()
    task = _task("blocked", 1, pass_time=0.0, std=20.0)
    edge_reservations = EdgeReservationTable()
    edge_reservations.reserve(task_id=99, start_node=0, end_node=1, start=0.0, end=2.0)

    capacity_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=0.0,
        reservations=ReservationTable(),
        edge_reservations=edge_reservations,
        edge_capacity=1,
    )
    assert capacity_candidates[0].safe is False
    assert "edge_capacity" in capacity_candidates[0].blocked_reasons
    assert capacity_candidates[1].is_hold
    assert capacity_candidates[1].safe is True

    fault_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=3.0,
        reservations=ReservationTable(),
        edge_reservations=EdgeReservationTable(),
        fault_edges={(0, 1)},
    )
    assert fault_candidates[0].safe is False
    assert "fault_edge" in fault_candidates[0].blocked_reasons


def test_action_mask_respects_buffer_node_capacity() -> None:
    graph = _line_graph()
    task = _task("buffer-capacity", 1, pass_time=0.0, std=20.0)
    reservations = ReservationTable()
    reservations.reserve(task_id=99, node=1, start=2.0, end=3.0)

    blocked_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=0.0,
        reservations=reservations,
        edge_reservations=EdgeReservationTable(),
    )
    assert blocked_candidates[0].safe is False
    assert "node_reservation" in blocked_candidates[0].blocked_reasons

    buffer_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=0.0,
        reservations=reservations,
        edge_reservations=EdgeReservationTable(),
        node_capacities={1: 2},
    )
    assert buffer_candidates[0].safe is True

    reservations.reserve(task_id=98, node=1, start=2.0, end=3.0)
    full_buffer_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=0.0,
        reservations=reservations,
        edge_reservations=EdgeReservationTable(),
        node_capacities={1: 2},
    )
    assert full_buffer_candidates[0].safe is False
    assert "node_reservation" in full_buffer_candidates[0].blocked_reasons


def test_action_mask_blocks_merge_group_conflicts() -> None:
    graph = _branch_graph()
    task = _task("merge-group", 1, pass_time=0.0, std=20.0, goal=3)
    edge_reservations = EdgeReservationTable()
    edge_reservations.reserve(task_id=99, start_node=0, end_node=2, start=0.0, end=3.0)

    candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=0.0,
        reservations=ReservationTable(),
        edge_reservations=edge_reservations,
        merge_groups={(0, 1): 7, (0, 2): 7},
    )
    assert candidates[0].next_node == 1
    assert candidates[0].safe is False
    assert "merge_group" in candidates[0].blocked_reasons

    independent_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=0.0,
        reservations=ReservationTable(),
        edge_reservations=edge_reservations,
        merge_groups={(0, 1): 7},
    )
    assert independent_candidates[0].safe is True


def test_action_mask_applies_repair_windows_by_ready_time() -> None:
    graph = _branch_graph()
    task = _task("repair-window", 1, pass_time=0.0, std=20.0, goal=3)
    fault_windows = ((0, 1, 0.0, 5.0),)

    active_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=4.0,
        reservations=ReservationTable(),
        edge_reservations=EdgeReservationTable(),
        fault_windows=fault_windows,
    )
    assert active_candidates[0].next_node == 1
    assert active_candidates[0].safe is False
    assert "fault_edge" in active_candidates[0].blocked_reasons
    assert active_candidates[1].next_node == 2
    assert active_candidates[1].safe is True

    repaired_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=5.0,
        reservations=ReservationTable(),
        edge_reservations=EdgeReservationTable(),
        fault_windows=fault_windows,
    )
    assert repaired_candidates[0].next_node == 1
    assert repaired_candidates[0].safe is True


def test_action_mask_blocks_unreachable_goal_candidates() -> None:
    graph = _dead_end_branch_graph()
    task = _task("dead-end", 1, pass_time=0.0, std=20.0, goal=3)

    candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=0.0,
        reservations=ReservationTable(),
        edge_reservations=EdgeReservationTable(),
    )

    assert candidates[0].next_node == 1
    assert candidates[0].safe is False
    assert "unreachable_goal" in candidates[0].blocked_reasons
    assert candidates[1].next_node == 2
    assert candidates[1].safe is True

    compatibility_candidates = build_action_candidates(
        graph=graph,
        task=task,
        current=0,
        ready_time=0.0,
        reservations=ReservationTable(),
        edge_reservations=EdgeReservationTable(),
        require_reachable_goal=False,
    )
    assert compatibility_candidates[0].safe is True


def test_junction_env_shortest_policy_runs_without_post_shield_conflicts() -> None:
    tasks = (
        _task("first", 1, pass_time=0.0, std=20.0),
        _task("second", 2, pass_time=0.1, std=30.0),
    )
    env = IcsJunctionEnv(_line_graph(), tasks, edge_capacity=1, hold_seconds=1.0)

    result, run_info = env.run_policy(shortest_safe_policy, seed=7)
    summary = env.episode_summary()

    assert run_info.truncated is False
    assert result.metrics.planned_count == 2
    assert result.metrics.unplanned_count == 0
    assert summary["post_shield_conflicts"] == 0
    assert result.routes["second"][1].t1 >= 4.0


def test_junction_env_astar_guided_policy_runs() -> None:
    graph = _branch_graph()
    env = IcsJunctionEnv(
        graph,
        (_task("branch", 1, pass_time=0.0, std=20.0, goal=3),),
    )

    result, run_info = env.run_policy(astar_guided_policy_factory(graph), seed=5)

    assert run_info.truncated is False
    assert result.metrics.planned_count == 1
    assert result.routes["branch"][-1].location == 3
    assert env.episode_summary()["post_shield_conflicts"] == 0


def test_junction_env_shield_falls_back_from_unsafe_proposal() -> None:
    env = IcsJunctionEnv(
        _branch_graph(),
        (_task("branch", 1, pass_time=0.0, std=20.0, goal=3),),
        fault_edges={(0, 1)},
    )
    obs, info = env.reset(seed=11)

    obs, reward, terminated, truncated, info = env.step(0)

    assert reward < 0.0
    assert terminated is False
    assert truncated is False
    assert info["shield_blocked"] is True
    assert info["unsafe_proposal"] is True
    assert info["executed_action"] == 1
    assert env.shield_blocks == 1
    assert env.unsafe_proposals == 1
    assert obs["task"]["current"] == 2


def test_vectorized_ics_env_steps_multiple_envs() -> None:
    vector_env = VectorizedIcsEnv(
        (
            lambda: IcsJunctionEnv(_line_graph(), (_task("a", 1, 0.0, 20.0),)),
            lambda: IcsJunctionEnv(_line_graph(), (_task("b", 2, 0.0, 20.0),)),
        )
    )

    observations, infos = vector_env.reset(seed=3)
    actions = [shortest_safe_policy(obs, info) for obs, info in zip(observations, infos)]
    next_observations, rewards, terminated, truncated, infos = vector_env.step(actions)

    assert len(next_observations) == 2
    assert len(rewards) == 2
    assert terminated == [False, False]
    assert truncated == [False, False]
