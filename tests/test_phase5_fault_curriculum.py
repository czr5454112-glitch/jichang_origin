from __future__ import annotations

from czr005.datasets import collect_teacher_slices
from czr005.envs import IcsJunctionEnv, fault_aware_astar_policy_factory
from czr005.sim_py import IcsGraph, SimEdge, SimNode
from czr005.sim_py.task_stream import TaskLeg


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


def _task() -> TaskLeg:
    return TaskLeg(
        segment_id="fault-aware",
        task_id=1,
        pallet_id=1,
        pass_time=0.0,
        std=20.0,
        start=0,
        goal=3,
        original_start=0,
        original_goal=3,
        original_entry_time=0.0,
        leg="direct",
        early_bag_split=False,
        source_line=1,
    )


def test_fault_aware_astar_teacher_uses_safe_alternative() -> None:
    graph = _branch_graph()
    faults = {(0, 1)}
    env = IcsJunctionEnv(graph, (_task(),), fault_edges=faults)

    result, run_info = env.run_policy(fault_aware_astar_policy_factory(graph, faults), seed=1)

    assert run_info.truncated is False
    assert result.metrics.planned_count == 1
    assert [node.location for node in result.routes["fault-aware"]] == [0, 2, 3]
    assert env.episode_summary()["post_shield_conflicts"] == 0


def test_fault_aware_teacher_slices_record_alternative_action() -> None:
    graph = _branch_graph()
    faults = {(0, 1)}
    run = collect_teacher_slices(
        IcsJunctionEnv(graph, (_task(),), fault_edges=faults),
        fault_aware_astar_policy_factory(graph, faults),
        seed=2,
        expert_source="fault_aware_astar",
    )

    assert run.summary()["slice_count"] == 2
    assert run.slices[0]["expert_source"] == "fault_aware_astar"
    assert run.slices[0]["expert_action"] == 1
    assert run.slices[0]["candidate_edges"][0]["safe"] is False
    assert "fault_edge" in run.slices[0]["candidate_edges"][0]["blocked_reasons"]
