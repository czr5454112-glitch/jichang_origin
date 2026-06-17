from __future__ import annotations

import json
from pathlib import Path

from czr005.datasets import collect_teacher_slices, write_teacher_manifest
from czr005.envs import IcsJunctionEnv, astar_guided_policy_factory
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


def _task() -> TaskLeg:
    return TaskLeg(
        segment_id="teacher",
        task_id=1,
        pallet_id=1,
        pass_time=0.0,
        std=20.0,
        start=0,
        goal=2,
        original_start=0,
        original_goal=2,
        original_entry_time=0.0,
        leg="direct",
        early_bag_split=False,
        source_line=1,
    )


ROOT = Path(__file__).resolve().parents[1]


def test_collect_teacher_slices_records_expert_actions() -> None:
    graph = _line_graph()
    env = IcsJunctionEnv(graph, (_task(),))
    run = collect_teacher_slices(env, astar_guided_policy_factory(graph), seed=1)

    assert run.result.metrics.planned_count == 1
    assert run.summary()["slice_count"] == 2
    assert run.summary()["reservation_conflicts"] == 0
    first = run.slices[0]
    assert first["obs"]["current"] == 0
    assert first["expert_action"] == 0
    assert first["action_mask"][0] is True
    assert first["shield_result"] == "accepted"

    manifest = ROOT / ".pytest_cache" / "teacher_slices_test.jsonl"
    try:
        write_teacher_manifest(manifest, run.slices)
        rows = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
        assert len(rows) == 2
        assert rows[1]["reached_goal"] is True
    finally:
        manifest.unlink(missing_ok=True)
