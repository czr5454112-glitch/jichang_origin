from __future__ import annotations

from pathlib import Path

from czr005.datasets import collect_teacher_slices, write_teacher_manifest
from czr005.envs import IcsJunctionEnv, astar_guided_policy_factory
from czr005.models import (
    EdgeScoreModel,
    evaluate_top1,
    fit_edge_score_model,
    load_edge_score_model,
    load_teacher_manifest,
    save_edge_score_model,
    save_edge_score_runtime_text,
)
from czr005.sim_py import IcsGraph, SimEdge, SimNode
from czr005.sim_py.task_stream import TaskLeg


ROOT = Path(__file__).resolve().parents[1]


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
        segment_id=f"teacher-{task_id}",
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


def test_edge_score_bc_fits_tiny_teacher_manifest() -> None:
    graph = _line_graph()
    env = IcsJunctionEnv(graph, (_task(1, 0.0), _task(2, 0.5)))
    run = collect_teacher_slices(env, astar_guided_policy_factory(graph), seed=3)
    manifest = ROOT / ".pytest_cache" / "edge_score_teacher.jsonl"
    model_path = ROOT / ".pytest_cache" / "edge_score_model.json"
    try:
        write_teacher_manifest(manifest, run.slices)
        rows = load_teacher_manifest(manifest)
        model, history = fit_edge_score_model(rows, hidden_dim=8, epochs=80, learning_rate=0.08, seed=5)
        top1 = evaluate_top1(model, rows)
        save_edge_score_model(model_path, model)
        loaded = load_edge_score_model(model_path)

        assert history[-1]["loss"] < history[0]["loss"]
        assert top1 >= 0.75
        assert evaluate_top1(loaded, rows) == top1
    finally:
        manifest.unlink(missing_ok=True)
        model_path.unlink(missing_ok=True)


def test_edge_score_runtime_text_export() -> None:
    model = EdgeScoreModel(
        w1=[[0.1, -0.2], [0.3, 0.4], [-0.5, 0.25]],
        b1=[0.01, -0.02],
        w2=[0.7, -0.6],
        b2=0.05,
    )
    model_path = ROOT / ".pytest_cache" / "edge_score_runtime.txt"
    try:
        save_edge_score_runtime_text(model_path, model)
        lines = model_path.read_text(encoding="utf-8").splitlines()

        assert lines[:5] == [
            "czr005_edge_score_v1",
            "feature_dim 3",
            "hidden_dim 2",
            "b2 0.050000000000000003",
            "w1",
        ]
        assert lines[5:8] == [
            "0.10000000000000001 -0.20000000000000001",
            "0.29999999999999999 0.40000000000000002",
            "-0.5 0.25",
        ]
        assert lines[8:] == [
            "b1",
            "0.01 -0.02",
            "w2",
            "0.69999999999999996 -0.59999999999999998",
        ]
    finally:
        model_path.unlink(missing_ok=True)
