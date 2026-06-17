from __future__ import annotations

from czr005.eval import run_event_replay
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


def _task(segment_id: str, task_id: int, pass_time: float) -> TaskLeg:
    return TaskLeg(
        segment_id=segment_id,
        task_id=task_id,
        pallet_id=task_id,
        pass_time=pass_time,
        std=30.0,
        start=0,
        goal=2,
        original_start=0,
        original_goal=2,
        original_entry_time=pass_time,
        leg="direct",
        early_bag_split=False,
        source_line=task_id + 1,
    )


def test_event_replay_interleaves_active_tasks_without_conflicts() -> None:
    run = run_event_replay(
        _line_graph(),
        (_task("first", 1, 0.0), _task("second", 2, 0.1)),
        max_tasks=2,
        max_decisions_per_task=8,
    )

    assert run.summary["planned_count"] == 2
    assert run.summary["unplanned_count"] == 0
    assert run.summary["post_shield_conflicts"] == 0
    assert run.summary["decision_count"] == len(run.trace)
    assert [row["decision_ordinal"] for row in run.trace] == list(range(1, len(run.trace) + 1))
    assert all(row["executed_safe"] for row in run.trace if row["event"] == "step")
    assert [row["task_id"] for row in run.trace[:2]] == [1, 2]
    assert len({row["task_id"] for row in run.trace[:4]}) == 2
