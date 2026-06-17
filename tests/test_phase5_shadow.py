from __future__ import annotations

from czr005.datasets import collect_labeled_policy_slices, collect_teacher_slices
from czr005.envs import IcsJunctionEnv, astar_guided_policy_factory
from czr005.eval import edge_score_policy_factory, run_shadow_replay
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
        segment_id=f"shadow-{task_id}",
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


def test_shadow_replay_and_closed_loop_policy_are_safe() -> None:
    graph = _line_graph()
    tasks = (_task(1, 0.0), _task(2, 0.5))
    teacher_env = IcsJunctionEnv(graph, tasks)
    teacher = collect_teacher_slices(teacher_env, astar_guided_policy_factory(graph), seed=5)
    model, _ = fit_edge_score_model(list(teacher.slices), hidden_dim=8, epochs=80, learning_rate=0.08, seed=9)

    shadow_env = IcsJunctionEnv(graph, tasks)
    shadow = run_shadow_replay(shadow_env, astar_guided_policy_factory(graph), model, seed=7)
    assert shadow.decisions >= 4
    assert shadow.baseline_conflicts == 0
    assert 0.0 <= shadow.unsafe_proposal_rate <= 0.5

    closed_env = IcsJunctionEnv(graph, tasks)
    result, run_info = closed_env.run_policy(edge_score_policy_factory(model), seed=7)
    assert run_info.truncated is False
    assert result.metrics.planned_count == 2
    assert closed_env.episode_summary()["post_shield_conflicts"] == 0


def test_labeled_policy_slices_keep_behavior_and_expert_actions() -> None:
    graph = _line_graph()
    tasks = (_task(1, 0.0),)

    def hold_first_policy(obs, info) -> int:
        for candidate in obs["candidates"]:
            if candidate["kind"] == "hold":
                return int(candidate["index"])
        return 0

    env = IcsJunctionEnv(graph, tasks, max_decisions_per_task=4)
    run = collect_labeled_policy_slices(
        env,
        behavior_policy=hold_first_policy,
        expert_policy=astar_guided_policy_factory(graph),
        seed=13,
        max_steps=4,
        behavior_source="hold_first",
    )

    assert run.slices[0]["behavior_source"] == "hold_first"
    assert run.slices[0]["proposed_action"] != run.slices[0]["expert_action"]
    assert run.slices[0]["shield_result"] == "accepted"
