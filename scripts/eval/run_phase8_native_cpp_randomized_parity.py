from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_randomized_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_randomized_parity_report.md"
MAX_DECISIONS_PER_TASK = 128
TOLERANCE = 1.0e-9
SPEED = 2.5

FaultWindow = tuple[int, int, float, float]


@dataclass(frozen=True)
class SyntheticCase:
    name: str
    seed: int
    task_count: int
    spacing: float
    fault_edges: set[tuple[int, int]]
    fault_windows: tuple[FaultWindow, ...]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def _format_faults(fault_edges: set[tuple[int, int]]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def _format_fault_windows(fault_windows: tuple[FaultWindow, ...]) -> str:
    if not fault_windows:
        return "none"
    return ";".join(
        f"{start}->{end}@[{fault_start:.3f},{repair_time:.3f})"
        for start, end, fault_start, repair_time in fault_windows
    )


def _case_plan() -> tuple[SyntheticCase, ...]:
    return (
        SyntheticCase("synthetic_seed7_medium_repair", 7, 18, 3.0, set(), ((4, 8, 4.0, 18.0),)),
        SyntheticCase(
            "synthetic_seed11_dense_multi_repair",
            11,
            24,
            1.4,
            set(),
            ((7, 9, 5.0, 16.0), (8, 9, 10.0, 22.0)),
        ),
        SyntheticCase(
            "synthetic_seed17_static_plus_repair",
            17,
            20,
            2.2,
            {(4, 7)},
            ((5, 8, 0.0, 14.0),),
        ),
        SyntheticCase(
            "synthetic_seed23_repeated_repair",
            23,
            22,
            1.8,
            set(),
            ((4, 8, 3.0, 8.0), (4, 8, 14.0, 21.0), (8, 9, 9.0, 15.0)),
        ),
    )


def _all_pairs_shortest_time(
    node_count: int,
    edges: dict[tuple[int, int], object],
) -> tuple[tuple[float, ...], ...]:
    inf = 1.0e6
    distances = [[inf for _ in range(node_count)] for _ in range(node_count)]
    for node in range(node_count):
        distances[node][node] = 0.0
    for (start, end), edge in edges.items():
        distances[start][end] = min(distances[start][end], float(edge.travel_time))
    for pivot in range(node_count):
        for start in range(node_count):
            via_pivot = distances[start][pivot]
            if via_pivot >= inf:
                continue
            for end in range(node_count):
                candidate = via_pivot + distances[pivot][end]
                if candidate < distances[start][end]:
                    distances[start][end] = candidate
    return tuple(tuple(row) for row in distances)


def _make_synthetic_graph(seed: int):
    from czr005.sim_py import IcsGraph, SimEdge, SimNode  # pylint: disable=import-outside-toplevel

    rng = random.Random(seed)
    node_count = 12
    base_edges = [
        (0, 3),
        (0, 4),
        (1, 4),
        (1, 5),
        (2, 5),
        (2, 6),
        (3, 7),
        (4, 7),
        (4, 8),
        (5, 8),
        (6, 8),
        (7, 9),
        (8, 9),
        (9, 10),
        (9, 11),
    ]
    optional_edges = [
        (3, 8),
        (4, 9),
        (5, 7),
        (6, 9),
        (7, 10),
        (8, 11),
    ]
    edge_pairs = list(base_edges)
    for edge in optional_edges:
        if rng.random() < 0.55:
            edge_pairs.append(edge)

    edges: dict[tuple[int, int], SimEdge] = {}
    for start, end in edge_pairs:
        travel_time = rng.uniform(1.6, 5.5)
        edges[(start, end)] = SimEdge(start=start, end=end, length=travel_time * SPEED, speed=SPEED)

    outgoing_by_node: dict[int, list[int]] = {node: [] for node in range(node_count)}
    for start, end in edge_pairs:
        outgoing_by_node[start].append(end)
    nodes = {}
    for node in range(node_count):
        if node in (0, 1, 2):
            node_type = 1
            service_time = 0.0
        elif node in (10, 11):
            node_type = 2
            service_time = 0.0
        else:
            node_type = 4
            service_time = rng.choice((0.0, 0.5, 1.0))
        nodes[node] = SimNode(
            location=node,
            node_type=node_type,
            service_time=service_time,
            x=node % 4,
            y=node // 4,
            outgoing=tuple(outgoing_by_node[node]),
        )

    return IcsGraph(
        nodes=nodes,
        edges=edges,
        heuristic_time=_all_pairs_shortest_time(node_count, edges),
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )


def _make_tasks(case: SyntheticCase):
    from czr005.sim_py.task_stream import TaskLeg  # pylint: disable=import-outside-toplevel

    rng = random.Random(case.seed * 101 + case.task_count)
    tasks: list[TaskLeg] = []
    starts = (0, 1, 2)
    goals = (10, 11)
    for task_id in range(case.task_count):
        start = rng.choice(starts)
        goal = rng.choice(goals)
        pass_time = task_id * case.spacing + rng.uniform(0.0, case.spacing * 0.25)
        tasks.append(
            TaskLeg(
                segment_id=f"{case.name}:{task_id}",
                task_id=task_id,
                pallet_id=task_id,
                pass_time=pass_time,
                std=pass_time + 180.0,
                start=start,
                goal=goal,
                original_start=start,
                original_goal=goal,
                original_entry_time=pass_time,
                leg="direct",
                early_bag_split=False,
                source_line=task_id + 1,
            )
        )
    return tuple(sorted(tasks, key=lambda task: (task.pass_time, task.task_id, task.leg)))


def _node_records(graph) -> list[tuple[int, int, float, int, int, list[int]]]:
    return [
        (
            node.location,
            node.node_type,
            node.service_time,
            node.x,
            node.y,
            list(node.outgoing),
        )
        for _, node in sorted(graph.nodes.items())
    ]


def _edge_records(graph) -> list[tuple[int, int, float, float]]:
    return [
        (edge.start, edge.end, edge.length, edge.speed)
        for _, edge in sorted(graph.edges.items())
    ]


def _task_records(tasks) -> list[tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]]:
    return [
        (
            task.segment_id,
            task.task_id,
            task.pallet_id,
            task.pass_time,
            task.std,
            task.start,
            task.goal,
            task.original_start,
            task.original_goal,
            task.original_entry_time,
            task.leg,
            task.early_bag_split,
            task.source_line,
        )
        for task in tasks
    ]


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    strict_pass = all(bool(row["strict_parity_pass"]) for row in rows)
    safety_pass = all(
        int(row["python_conflicts"]) == 0
        and int(row["cpp_conflicts"]) == 0
        and not bool(row["python_truncated"])
        for row in rows
    )
    lines = [
        "# Phase8 Native C++ Randomized Synthetic Parity Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This diagnostic checks compact native C++ replay parity against the Python junction environment on fixed-seed synthetic directed ICS-like maps. The rows vary map edge lengths, optional branch edges, task density, static fault edges, and repair-window schedules.",
        "",
        "The graph and task stream are passed through the pybind in-memory record API, so this is no longer limited to legacy `map2.txt` files. This is randomized synthetic-map coverage, not a real heldout airport map or the final high-throughput C++ event scheduler.",
        "",
        "## Metrics",
        "",
        "| Case | Seed | Tasks | Edges | Spacing | Static faults | Repair windows | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Strict parity |",
        "|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {seed} | {task_count} | {edge_count} | {spacing:.3f} | {fault_edges} | "
            "{fault_windows} | {python_planned} | {cpp_planned} | {python_steps} | "
            "{cpp_decision_count} | {mean_travel_abs_diff:.12f} | {strict_parity_pass} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- randomized synthetic compact replay parity: PASS" if strict_pass else "- randomized synthetic compact replay parity: FAIL",
            "- randomized synthetic safety: PASS" if safety_pass else "- randomized synthetic safety: FAIL",
            "- real heldout-map parity: not covered",
            "- full high-throughput event-scheduler parity: not covered",
            "",
            "## Remaining Work",
            "",
            "- add real heldout-map fixtures or map generators with persisted manifests",
            "- carry the same randomized schedules into the final C++ event scheduler",
            "- expand randomized density/fault seeds before paper-grade claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.envs import IcsJunctionEnv  # pylint: disable=import-outside-toplevel
    from czr005.eval import runtime_edge_score_policy_factory  # pylint: disable=import-outside-toplevel

    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))
    rows: list[dict[str, float | int | str | bool]] = []

    for case in _case_plan():
        graph = _make_synthetic_graph(case.seed)
        tasks = _make_tasks(case)
        env = IcsJunctionEnv(
            graph,
            tasks,
            fault_edges=case.fault_edges,
            fault_windows=case.fault_windows,
            max_decisions_per_task=MAX_DECISIONS_PER_TASK,
        )
        python_result, python_run = env.run_policy(
            runtime_edge_score_policy_factory(runtime_model),
            seed=case.seed,
            max_steps=case.task_count * MAX_DECISIONS_PER_TASK,
        )
        python_summary = env.episode_summary()
        cpp_summary = czr005_cpp.edge_score_native_replay_summary_from_records(
            _node_records(graph),
            _edge_records(graph),
            [list(row) for row in graph.heuristic_time],
            _task_records(tasks),
            str(MODEL_PATH),
            max_tasks=case.task_count,
            fault_edges=list(case.fault_edges),
            max_decisions_per_task=MAX_DECISIONS_PER_TASK,
            fault_windows=list(case.fault_windows),
        )
        mean_diff = abs(python_result.metrics.mean_travel_time - float(cpp_summary["mean_travel_time"]))
        planned_match = python_result.metrics.planned_count == int(cpp_summary["planned_count"])
        unplanned_match = python_result.metrics.unplanned_count == int(cpp_summary["unplanned_count"])
        decision_match = python_run.steps == int(cpp_summary["decision_count"])
        conflict_match = int(python_summary["post_shield_conflicts"]) == int(cpp_summary["post_shield_conflicts"])
        mean_match = mean_diff <= TOLERANCE
        strict_parity_pass = all((planned_match, unplanned_match, decision_match, conflict_match, mean_match))
        rows.append(
            {
                "case": case.name,
                "seed": case.seed,
                "task_count": case.task_count,
                "node_count": graph.node_count,
                "edge_count": len(graph.edges),
                "spacing": case.spacing,
                "fault_edges": _format_faults(case.fault_edges),
                "fault_windows": _format_fault_windows(case.fault_windows),
                "python_planned": python_result.metrics.planned_count,
                "cpp_planned": int(cpp_summary["planned_count"]),
                "planned_match": planned_match,
                "python_unplanned": python_result.metrics.unplanned_count,
                "cpp_unplanned": int(cpp_summary["unplanned_count"]),
                "unplanned_match": unplanned_match,
                "python_steps": python_run.steps,
                "cpp_decision_count": int(cpp_summary["decision_count"]),
                "decision_match": decision_match,
                "python_mean_travel_time": python_result.metrics.mean_travel_time,
                "cpp_mean_travel_time": float(cpp_summary["mean_travel_time"]),
                "mean_travel_abs_diff": mean_diff,
                "mean_travel_match": mean_match,
                "python_conflicts": int(python_summary["post_shield_conflicts"]),
                "cpp_conflicts": int(cpp_summary["post_shield_conflicts"]),
                "conflict_match": conflict_match,
                "python_truncated": python_run.truncated,
                "strict_parity_pass": strict_parity_pass,
            }
        )

    write_table(rows)
    write_report(rows)
    if not all(bool(row["strict_parity_pass"]) for row in rows):
        raise AssertionError("randomized synthetic compact replay parity failed")
    if any(bool(row["python_truncated"]) for row in rows):
        raise AssertionError("randomized synthetic Python replay truncated")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("randomized synthetic replay produced post-shield conflicts")

    print(f"phase8_native_cpp_randomized_parity rows={len(rows)} strict_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
