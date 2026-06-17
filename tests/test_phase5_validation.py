from __future__ import annotations

from czr005.datasets import collect_labeled_policy_slices, collect_teacher_slices
from czr005.envs import IcsJunctionEnv, astar_guided_policy_factory
from czr005.eval import edge_score_policy_factory
from czr005.models import fit_edge_score_model
from czr005.sim_py import IcsGraph, SimEdge, SimNode
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


def _task(task_id: int, pass_time: float) -> TaskLeg:
    return TaskLeg(
        segment_id=f"validation-{task_id}",
        task_id=task_id,
        pallet_id=task_id,
        pass_time=pass_time,
        std=20.0 + pass_time,
        start=0,
        goal=2,
        original_start=0,
        original_goal=2,
        original_entry_time=pass_time,
        leg="direct",
        early_bag_split=False,
        source_line=task_id,
    )


def test_dagger_bc_policy_matches_baseline_on_tiny_validation_window() -> None:
    graph = _line_graph()
    train_tasks = (_task(1, 0.0), _task(2, 0.5))
    validation_tasks = (_task(3, 1.0),)
    expert = astar_guided_policy_factory(graph)

    base = collect_teacher_slices(IcsJunctionEnv(graph, train_tasks), expert, seed=1)
    model, _ = fit_edge_score_model(list(base.slices), hidden_dim=8, epochs=80, learning_rate=0.08, seed=2)
    dagger = collect_labeled_policy_slices(
        IcsJunctionEnv(graph, train_tasks),
        behavior_policy=edge_score_policy_factory(model, safe_only=True),
        expert_policy=expert,
        seed=3,
    )
    model, _ = fit_edge_score_model(
        list(base.slices) + list(dagger.slices),
        hidden_dim=8,
        epochs=80,
        learning_rate=0.08,
        seed=4,
    )

    baseline_env = IcsJunctionEnv(graph, validation_tasks)
    baseline, _ = baseline_env.run_policy(expert, seed=5)
    bc_env = IcsJunctionEnv(graph, validation_tasks)
    bc, _ = bc_env.run_policy(edge_score_policy_factory(model, safe_only=True), seed=5)

    assert baseline.metrics.planned_count == 1
    assert bc.metrics.planned_count == baseline.metrics.planned_count
    assert bc_env.episode_summary()["post_shield_conflicts"] == 0
