from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import random
import sys
from time import perf_counter
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
TABLE_PATH = ROOT / "outputs" / "tables" / "phase9_random_topology_pibt_stress_sweep.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase9_random_topology_pibt_stress_sweep_report.md"

SPEED = 2.5
INF = 1.0e6
FLOAT_TOLERANCE = 1.0e-8

NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
TaskRecord = tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]
FaultEdge = tuple[int, int]
FaultWindow = tuple[int, int, float, float]
NodeCapacity = tuple[int, int]
MergeGroup = tuple[int, int, int]

ROW_FIELDS = [
    "scenario",
    "seed",
    "layers",
    "source_mode",
    "goal_mode",
    "branch_probability",
    "shortcut_probability",
    "task_count",
    "spacing",
    "node_count",
    "edge_count",
    "source_histogram",
    "goal_histogram",
    "fault_edges",
    "fault_windows",
    "node_capacities",
    "merge_groups",
    "merge_capacity",
    "merge_headway_seconds",
    "python_planned",
    "cpp_planned",
    "python_unplanned",
    "cpp_unplanned",
    "python_decisions",
    "cpp_decisions",
    "python_ticks",
    "cpp_ticks",
    "python_peak_active_bags",
    "cpp_peak_active_bags",
    "python_holds",
    "cpp_holds",
    "python_conflicts",
    "cpp_conflicts",
    "python_mean_travel_time",
    "cpp_mean_travel_time",
    "mean_travel_abs_diff",
    "python_makespan",
    "cpp_makespan",
    "makespan_abs_diff",
    "python_elapsed_seconds",
    "cpp_elapsed_seconds",
    "cpp_speedup",
    "parity_pass",
    "first_mismatch_field",
    "python_value",
    "cpp_value",
]

SUMMARY_FIELDS = (
    "planned_count",
    "unplanned_count",
    "decision_count",
    "tick_count",
    "peak_active_bags",
    "hold_count",
    "post_shield_conflicts",
    "mean_travel_time",
    "makespan",
)


@dataclass(frozen=True)
class RandomTopologySpec:
    name: str
    seed: int
    layers: tuple[int, ...]
    task_count: int
    spacing: float
    branch_probability: float
    shortcut_probability: float
    source_mode: str
    goal_mode: str
    fault_mode: str
    capacity_mode: str
    merge_mode: str
    merge_headway_seconds: float = 0.0


@dataclass(frozen=True)
class RandomTopologyCase:
    spec: RandomTopologySpec
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    task_records: tuple[TaskRecord, ...]
    fault_edges: tuple[FaultEdge, ...]
    fault_windows: tuple[FaultWindow, ...]
    node_capacities: tuple[NodeCapacity, ...]
    merge_groups: tuple[MergeGroup, ...]
    merge_capacity: int
    merge_headway_seconds: float


@dataclass(frozen=True)
class RuntimeInputs:
    graph: Any
    tasks: tuple[Any, ...]
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    task_records: tuple[TaskRecord, ...]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    build_candidates = (
        Path(os.environ["CZR005_CPP_PYTHON_PATH"])
        if os.environ.get("CZR005_CPP_PYTHON_PATH")
        else None,
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
        BUILD_PYTHON_PATH,
    )
    for candidate in reversed([path for path in build_candidates if path is not None]):
        if candidate.exists() or str(candidate) == os.environ.get("CZR005_CPP_PYTHON_PATH"):
            sys.path.insert(0, str(candidate))


def _case_specs() -> tuple[RandomTopologySpec, ...]:
    return (
        RandomTopologySpec(
            "random_topo_seed211_wide_uniform",
            211,
            (3, 4, 4, 3, 2),
            36,
            0.70,
            0.45,
            0.12,
            "uniform",
            "uniform",
            "none",
            "none",
            "none",
        ),
        RandomTopologySpec(
            "random_topo_seed223_skewed_bottleneck",
            223,
            (4, 3, 5, 3, 2),
            40,
            0.55,
            0.50,
            0.18,
            "skewed",
            "skewed",
            "none",
            "middle_buffers",
            "bottleneck_incoming",
            0.25,
        ),
        RandomTopologySpec(
            "random_topo_seed227_burst_repair",
            227,
            (3, 5, 3, 5, 2),
            42,
            0.50,
            0.42,
            0.10,
            "burst",
            "alternating",
            "repair",
            "middle_buffers",
            "bottleneck_incoming",
        ),
        RandomTopologySpec(
            "random_topo_seed229_static_alt",
            229,
            (4, 4, 4, 4, 3),
            44,
            0.48,
            0.38,
            0.16,
            "alternating",
            "uniform",
            "static",
            "none",
            "two_bottlenecks",
        ),
        RandomTopologySpec(
            "random_topo_seed233_shortcut_dense",
            233,
            (5, 5, 4, 5, 3),
            48,
            0.42,
            0.60,
            0.30,
            "skewed",
            "alternating",
            "multi_repair",
            "middle_buffers",
            "two_bottlenecks",
            0.25,
        ),
        RandomTopologySpec(
            "random_topo_seed239_sparse_repair",
            239,
            (3, 3, 3, 3, 2),
            34,
            0.75,
            0.22,
            0.05,
            "burst",
            "skewed",
            "repair",
            "none",
            "none",
        ),
    )


def _timed(call: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], float]:
    started = perf_counter()
    payload = call()
    return payload, perf_counter() - started


def _build_case(spec: RandomTopologySpec) -> RandomTopologyCase:
    rng = random.Random(spec.seed)
    nodes_by_layer = _nodes_by_layer(spec.layers)
    layer_index = {
        node: layer for layer, nodes in enumerate(nodes_by_layer) for node in nodes
    }
    edge_pairs = _edge_pairs(nodes_by_layer, spec, rng)
    travel_times = _edge_travel_times(edge_pairs, layer_index, rng)
    outgoing_by_node = {node: [] for layer in nodes_by_layer for node in layer}
    incoming_by_node = {node: [] for layer in nodes_by_layer for node in layer}
    for start, end in edge_pairs:
        outgoing_by_node[start].append(end)
        incoming_by_node[end].append(start)

    node_records = _node_records(nodes_by_layer, outgoing_by_node, rng)
    edge_records = tuple(
        (start, end, travel_times[(start, end)] * SPEED, SPEED) for start, end in edge_pairs
    )
    heuristic_time = _all_pairs_shortest_time(sum(spec.layers), travel_times)
    node_capacities = _select_node_capacities(spec, nodes_by_layer, incoming_by_node, rng)
    merge_groups = _select_merge_groups(spec, edge_pairs, incoming_by_node, rng)
    fault_edges, fault_windows = _select_faults(spec, edge_pairs, layer_index, outgoing_by_node, rng)
    task_records = _task_records(spec, nodes_by_layer[0], nodes_by_layer[-1], heuristic_time)
    return RandomTopologyCase(
        spec=spec,
        node_records=node_records,
        edge_records=edge_records,
        heuristic_time=heuristic_time,
        task_records=task_records,
        fault_edges=fault_edges,
        fault_windows=fault_windows,
        node_capacities=node_capacities,
        merge_groups=merge_groups,
        merge_capacity=1,
        merge_headway_seconds=spec.merge_headway_seconds,
    )


def _nodes_by_layer(layers: tuple[int, ...]) -> tuple[tuple[int, ...], ...]:
    nodes: list[tuple[int, ...]] = []
    next_node = 0
    for width in layers:
        layer_nodes = tuple(range(next_node, next_node + width))
        nodes.append(layer_nodes)
        next_node += width
    return tuple(nodes)


def _edge_pairs(
    nodes_by_layer: tuple[tuple[int, ...], ...],
    spec: RandomTopologySpec,
    rng: random.Random,
) -> tuple[tuple[int, int], ...]:
    edges: set[tuple[int, int]] = set()

    def add_edge(start: int, end: int) -> None:
        if start != end:
            edges.add((start, end))

    for layer_index in range(len(nodes_by_layer) - 1):
        left = nodes_by_layer[layer_index]
        right = nodes_by_layer[layer_index + 1]
        for start in left:
            add_edge(start, rng.choice(right))
        for end in right:
            add_edge(rng.choice(left), end)
        for start in left:
            for end in right:
                if rng.random() < spec.branch_probability:
                    add_edge(start, end)

    for layer_index in range(len(nodes_by_layer) - 2):
        left = nodes_by_layer[layer_index]
        right = nodes_by_layer[layer_index + 2]
        for start in left:
            for end in right:
                if rng.random() < spec.shortcut_probability:
                    add_edge(start, end)

    return tuple(sorted(edges))


def _edge_travel_times(
    edge_pairs: tuple[tuple[int, int], ...],
    layer_index: dict[int, int],
    rng: random.Random,
) -> dict[tuple[int, int], float]:
    travel_times: dict[tuple[int, int], float] = {}
    for start, end in edge_pairs:
        layer_span = max(1, layer_index[end] - layer_index[start])
        travel_times[(start, end)] = rng.uniform(1.4, 5.6) * layer_span
    return travel_times


def _node_records(
    nodes_by_layer: tuple[tuple[int, ...], ...],
    outgoing_by_node: dict[int, list[int]],
    rng: random.Random,
) -> tuple[NodeRecord, ...]:
    records: list[NodeRecord] = []
    final_layer = len(nodes_by_layer) - 1
    for layer, nodes in enumerate(nodes_by_layer):
        for offset, node in enumerate(nodes):
            if layer == 0:
                node_type = 1
                service_time = 0.0
            elif layer == final_layer:
                node_type = 2
                service_time = 0.0
            else:
                node_type = 4
                service_time = rng.choice((0.0, 0.0, 0.5, 1.0))
            records.append(
                (node, node_type, service_time, layer, offset, sorted(outgoing_by_node[node]))
            )
    return tuple(records)


def _select_node_capacities(
    spec: RandomTopologySpec,
    nodes_by_layer: tuple[tuple[int, ...], ...],
    incoming_by_node: dict[int, list[int]],
    rng: random.Random,
) -> tuple[NodeCapacity, ...]:
    if spec.capacity_mode == "none":
        return ()
    middle_nodes = [
        node
        for layer in nodes_by_layer[1:-1]
        for node in layer
        if len(incoming_by_node[node]) >= 2
    ]
    rng.shuffle(middle_nodes)
    return tuple(sorted((node, 2) for node in middle_nodes[: min(3, len(middle_nodes))]))


def _select_merge_groups(
    spec: RandomTopologySpec,
    edge_pairs: tuple[tuple[int, int], ...],
    incoming_by_node: dict[int, list[int]],
    rng: random.Random,
) -> tuple[MergeGroup, ...]:
    if spec.merge_mode == "none":
        return ()
    incoming_targets = sorted(
        node for node, incoming in incoming_by_node.items() if len(incoming) >= 2
    )
    rng.shuffle(incoming_targets)
    limit = 1 if spec.merge_mode == "bottleneck_incoming" else 2
    selected_targets = incoming_targets[: min(limit, len(incoming_targets))]
    edge_set = set(edge_pairs)
    groups: list[MergeGroup] = []
    for target in selected_targets:
        group_id = 100 + target
        for start in sorted(incoming_by_node[target]):
            if (start, target) in edge_set:
                groups.append((start, target, group_id))
    return tuple(sorted(groups))


def _select_faults(
    spec: RandomTopologySpec,
    edge_pairs: tuple[tuple[int, int], ...],
    layer_index: dict[int, int],
    outgoing_by_node: dict[int, list[int]],
    rng: random.Random,
) -> tuple[tuple[FaultEdge, ...], tuple[FaultWindow, ...]]:
    if spec.fault_mode == "none":
        return (), ()
    final_layer = max(layer_index.values())
    candidates = [
        edge
        for edge in edge_pairs
        if 0 < layer_index[edge[0]] < final_layer
        and layer_index[edge[1]] < final_layer
        and len(outgoing_by_node[edge[0]]) >= 2
    ]
    if not candidates:
        candidates = [edge for edge in edge_pairs if layer_index[edge[0]] > 0]
    rng.shuffle(candidates)
    if not candidates:
        return (), ()
    if spec.fault_mode == "static":
        return (candidates[0],), ()
    if spec.fault_mode == "repair":
        start, end = candidates[0]
        return (), ((start, end, 4.0, 18.0),)
    if spec.fault_mode == "multi_repair":
        windows: list[FaultWindow] = []
        for offset, (start, end) in enumerate(candidates[:2]):
            windows.append((start, end, 3.0 + offset * 5.0, 12.0 + offset * 8.0))
        return (), tuple(windows)
    raise ValueError(f"unknown fault mode: {spec.fault_mode}")


def _all_pairs_shortest_time(
    node_count: int,
    edge_travel_times: dict[tuple[int, int], float],
) -> tuple[tuple[float, ...], ...]:
    distances = [[INF for _ in range(node_count)] for _ in range(node_count)]
    for node in range(node_count):
        distances[node][node] = 0.0
    for (start, end), travel_time in edge_travel_times.items():
        distances[start][end] = min(distances[start][end], travel_time)
    for pivot in range(node_count):
        for start in range(node_count):
            via_pivot = distances[start][pivot]
            if via_pivot >= INF:
                continue
            for end in range(node_count):
                candidate = via_pivot + distances[pivot][end]
                if candidate < distances[start][end]:
                    distances[start][end] = candidate
    return tuple(tuple(row) for row in distances)


def _task_records(
    spec: RandomTopologySpec,
    starts: tuple[int, ...],
    goals: tuple[int, ...],
    heuristic_time: tuple[tuple[float, ...], ...],
) -> tuple[TaskRecord, ...]:
    rng = random.Random(spec.seed * 101 + spec.task_count)
    records: list[TaskRecord] = []
    for task_id in range(spec.task_count):
        start = _choose_start(spec, starts, task_id, rng)
        reachable_goals = tuple(goal for goal in goals if heuristic_time[start][goal] < INF * 0.5)
        if not reachable_goals:
            reachable_starts = [source for source in starts if any(heuristic_time[source][goal] < INF * 0.5 for goal in goals)]
            start = rng.choice(reachable_starts)
            reachable_goals = tuple(goal for goal in goals if heuristic_time[start][goal] < INF * 0.5)
        goal = _choose_goal(spec, reachable_goals, task_id, rng)
        pass_time = _pass_time(spec, task_id, rng)
        records.append(
            (
                f"{spec.name}:{task_id}",
                task_id,
                task_id,
                pass_time,
                pass_time + 240.0,
                start,
                goal,
                start,
                goal,
                pass_time,
                "direct",
                False,
                task_id + 1,
            )
        )
    return tuple(sorted(records, key=lambda task: (task[3], task[1], task[10])))


def _choose_start(
    spec: RandomTopologySpec,
    starts: tuple[int, ...],
    task_id: int,
    rng: random.Random,
) -> int:
    if spec.source_mode == "uniform":
        return rng.choice(starts)
    if spec.source_mode == "skewed":
        if rng.random() < 0.68:
            return starts[0]
        return rng.choice(starts[1:] or starts)
    if spec.source_mode == "burst":
        return starts[(task_id // 6) % len(starts)]
    if spec.source_mode == "alternating":
        return starts[(task_id * 2 + spec.seed) % len(starts)]
    raise ValueError(f"unknown source mode: {spec.source_mode}")


def _choose_goal(
    spec: RandomTopologySpec,
    goals: tuple[int, ...],
    task_id: int,
    rng: random.Random,
) -> int:
    if spec.goal_mode == "uniform":
        return rng.choice(goals)
    if spec.goal_mode == "skewed":
        if rng.random() < 0.72:
            return goals[0]
        return rng.choice(goals[1:] or goals)
    if spec.goal_mode == "alternating":
        return goals[(task_id + spec.seed) % len(goals)]
    raise ValueError(f"unknown goal mode: {spec.goal_mode}")


def _pass_time(spec: RandomTopologySpec, task_id: int, rng: random.Random) -> float:
    if spec.source_mode == "burst":
        burst_index = task_id // 4
        offset = (task_id % 4) * min(0.08, spec.spacing * 0.2)
        return burst_index * spec.spacing + offset + rng.uniform(0.0, 0.02)
    return task_id * spec.spacing + rng.uniform(0.0, spec.spacing * 0.2)


def _graph_from_case(case: RandomTopologyCase):
    from czr005.sim_py import IcsGraph, SimEdge, SimNode  # pylint: disable=import-outside-toplevel

    nodes = {
        location: SimNode(
            location=location,
            node_type=node_type,
            service_time=service_time,
            x=x,
            y=y,
            outgoing=tuple(outgoing),
        )
        for location, node_type, service_time, x, y, outgoing in case.node_records
    }
    edges = {
        (start, end): SimEdge(start=start, end=end, length=length, speed=speed)
        for start, end, length, speed in case.edge_records
    }
    return IcsGraph(
        nodes=nodes,
        edges=edges,
        heuristic_time=case.heuristic_time,
        agv_length=1.0,
        safe_length=1.0,
        fault_threshold=1.0,
    )


def _tasks_from_case(case: RandomTopologyCase) -> tuple[Any, ...]:
    from czr005.sim_py.task_stream import TaskLeg  # pylint: disable=import-outside-toplevel

    return tuple(
        TaskLeg(
            segment_id=segment_id,
            task_id=task_id,
            pallet_id=pallet_id,
            pass_time=pass_time,
            std=std,
            start=start,
            goal=goal,
            original_start=original_start,
            original_goal=original_goal,
            original_entry_time=original_entry_time,
            leg=leg,
            early_bag_split=early_bag_split,
            source_line=source_line,
        )
        for (
            segment_id,
            task_id,
            pallet_id,
            pass_time,
            std,
            start,
            goal,
            original_start,
            original_goal,
            original_entry_time,
            leg,
            early_bag_split,
            source_line,
        ) in case.task_records
    )


def _python_pibt(inputs: RuntimeInputs, case: RandomTopologyCase) -> dict[str, Any]:
    from czr005.baselines import PIBTActiveBagReplayBaseline  # pylint: disable=import-outside-toplevel

    baseline = PIBTActiveBagReplayBaseline(
        inputs.graph,
        interval_seconds=2.0,
        max_ticks=4096,
        hold_seconds=2.0,
        node_capacities=dict(case.node_capacities),
        merge_groups={(start, end): group for start, end, group in case.merge_groups},
        merge_capacity=case.merge_capacity,
        merge_headway_seconds=case.merge_headway_seconds,
    )
    result = baseline.run_episode(
        inputs.tasks,
        max_tasks=case.spec.task_count,
        fault_edges=set(case.fault_edges),
        fault_windows=case.fault_windows,
    )
    return {
        **result.metrics.to_dict(),
        "decision_count": baseline.summary.decision_count,
        "tick_count": baseline.summary.tick_count,
        "peak_active_bags": baseline.summary.peak_active_bags,
        "move_count": baseline.summary.move_count,
        "hold_count": baseline.summary.hold_count,
        "edge_reservation_conflicts": baseline.summary.edge_reservation_conflicts,
        "post_shield_conflicts": baseline.summary.post_shield_conflicts,
    }


def _cpp_pibt(inputs: RuntimeInputs, case: RandomTopologyCase) -> dict[str, Any]:
    import czr005_cpp  # pylint: disable=import-outside-toplevel

    payload = czr005_cpp.pibt_active_bag_replay_from_records(
        list(inputs.node_records),
        list(inputs.edge_records),
        [list(row) for row in inputs.heuristic_time],
        list(inputs.task_records),
        max_tasks=case.spec.task_count,
        interval_seconds=2.0,
        max_ticks=4096,
        hold_seconds=2.0,
        edge_capacity=1,
        edge_headway_seconds=0.0,
        fault_edges=list(case.fault_edges),
        fault_windows=list(case.fault_windows),
        node_capacities=list(case.node_capacities),
        merge_groups=list(case.merge_groups),
        merge_capacity=case.merge_capacity,
        merge_headway_seconds=case.merge_headway_seconds,
    )
    return dict(payload["summary"])


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field in {"mean_travel_time", "makespan"}:
        return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE
    return python_value == cpp_value


def _first_mismatch(python_summary: dict[str, Any], cpp_summary: dict[str, Any]) -> dict[str, Any]:
    for field in SUMMARY_FIELDS:
        if not _values_match(field, python_summary.get(field, ""), cpp_summary.get(field, "")):
            return {
                "field": field,
                "python_value": python_summary.get(field, ""),
                "cpp_value": cpp_summary.get(field, ""),
            }
    return {"field": "none", "python_value": "", "cpp_value": ""}


def _summary_int(summary: dict[str, Any], field: str) -> int:
    value = summary.get(field, "")
    if value == "":
        return 0
    return int(value)


def _summary_float(summary: dict[str, Any], field: str) -> float:
    value = summary.get(field, "")
    if value == "":
        return 0.0
    return float(value)


def _format_faults(fault_edges: tuple[FaultEdge, ...]) -> str:
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


def _format_node_capacities(node_capacities: tuple[NodeCapacity, ...]) -> str:
    if not node_capacities:
        return "none"
    return ";".join(f"{node}:{capacity}" for node, capacity in sorted(node_capacities))


def _format_merge_groups(merge_groups: tuple[MergeGroup, ...]) -> str:
    if not merge_groups:
        return "none"
    return ";".join(f"{start}->{end}:{group}" for start, end, group in sorted(merge_groups))


def _format_histogram(task_records: tuple[TaskRecord, ...], index: int) -> str:
    counts: dict[int, int] = {}
    for record in task_records:
        key = int(record[index])
        counts[key] = counts.get(key, 0) + 1
    return ";".join(f"{key}:{counts[key]}" for key in sorted(counts))


def _layers_label(layers: tuple[int, ...]) -> str:
    return "-".join(str(width) for width in layers)


def _row(
    case: RandomTopologyCase,
    python_summary: dict[str, Any],
    python_elapsed: float,
    cpp_summary: dict[str, Any],
    cpp_elapsed: float,
) -> dict[str, float | int | str | bool]:
    mismatch = _first_mismatch(python_summary, cpp_summary)
    return {
        "scenario": case.spec.name,
        "seed": case.spec.seed,
        "layers": _layers_label(case.spec.layers),
        "source_mode": case.spec.source_mode,
        "goal_mode": case.spec.goal_mode,
        "branch_probability": case.spec.branch_probability,
        "shortcut_probability": case.spec.shortcut_probability,
        "task_count": case.spec.task_count,
        "spacing": case.spec.spacing,
        "node_count": len(case.node_records),
        "edge_count": len(case.edge_records),
        "source_histogram": _format_histogram(case.task_records, 5),
        "goal_histogram": _format_histogram(case.task_records, 6),
        "fault_edges": _format_faults(case.fault_edges),
        "fault_windows": _format_fault_windows(case.fault_windows),
        "node_capacities": _format_node_capacities(case.node_capacities),
        "merge_groups": _format_merge_groups(case.merge_groups),
        "merge_capacity": case.merge_capacity,
        "merge_headway_seconds": case.merge_headway_seconds,
        "python_planned": _summary_int(python_summary, "planned_count"),
        "cpp_planned": _summary_int(cpp_summary, "planned_count"),
        "python_unplanned": _summary_int(python_summary, "unplanned_count"),
        "cpp_unplanned": _summary_int(cpp_summary, "unplanned_count"),
        "python_decisions": _summary_int(python_summary, "decision_count"),
        "cpp_decisions": _summary_int(cpp_summary, "decision_count"),
        "python_ticks": _summary_int(python_summary, "tick_count"),
        "cpp_ticks": _summary_int(cpp_summary, "tick_count"),
        "python_peak_active_bags": _summary_int(python_summary, "peak_active_bags"),
        "cpp_peak_active_bags": _summary_int(cpp_summary, "peak_active_bags"),
        "python_holds": _summary_int(python_summary, "hold_count"),
        "cpp_holds": _summary_int(cpp_summary, "hold_count"),
        "python_conflicts": _summary_int(python_summary, "post_shield_conflicts"),
        "cpp_conflicts": _summary_int(cpp_summary, "post_shield_conflicts"),
        "python_mean_travel_time": _summary_float(python_summary, "mean_travel_time"),
        "cpp_mean_travel_time": _summary_float(cpp_summary, "mean_travel_time"),
        "mean_travel_abs_diff": abs(
            _summary_float(python_summary, "mean_travel_time") - _summary_float(cpp_summary, "mean_travel_time")
        ),
        "python_makespan": _summary_float(python_summary, "makespan"),
        "cpp_makespan": _summary_float(cpp_summary, "makespan"),
        "makespan_abs_diff": abs(_summary_float(python_summary, "makespan") - _summary_float(cpp_summary, "makespan")),
        "python_elapsed_seconds": python_elapsed,
        "cpp_elapsed_seconds": cpp_elapsed,
        "cpp_speedup": python_elapsed / cpp_elapsed if cpp_elapsed > 0.0 else 0.0,
        "parity_pass": mismatch["field"] == "none",
        "first_mismatch_field": mismatch["field"],
        "python_value": mismatch["python_value"],
        "cpp_value": mismatch["cpp_value"],
    }


def build_rows(cases: tuple[RandomTopologyCase, ...]) -> list[dict[str, float | int | str | bool]]:
    rows: list[dict[str, float | int | str | bool]] = []
    for case in cases:
        inputs = RuntimeInputs(
            graph=_graph_from_case(case),
            tasks=_tasks_from_case(case),
            node_records=case.node_records,
            edge_records=case.edge_records,
            heuristic_time=case.heuristic_time,
            task_records=case.task_records,
        )
        python_summary, python_elapsed = _timed(lambda: _python_pibt(inputs, case))
        cpp_summary, cpp_elapsed = _timed(lambda: _cpp_pibt(inputs, case))
        rows.append(_row(case, python_summary, python_elapsed, cpp_summary, cpp_elapsed))
    return rows


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ROW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def _fault_label(row: dict[str, float | int | str | bool]) -> str:
    if row["fault_edges"] != "none":
        return str(row["fault_edges"])
    return str(row["fault_windows"])


def _config_label(row: dict[str, float | int | str | bool]) -> str:
    parts = []
    if row["node_capacities"] != "none":
        parts.append(f"nodes={row['node_capacities']}")
    if row["merge_groups"] != "none":
        parts.append(f"merge={row['merge_groups']},headway={row['merge_headway_seconds']}")
    return "; ".join(parts) if parts else "none"


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parity_pass = all(bool(row["parity_pass"]) for row in rows)
    safety_pass = all(int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows)
    planned_rates = [float(row["cpp_planned"]) / float(row["task_count"]) for row in rows]
    speedups = [float(row["cpp_speedup"]) for row in rows if float(row["cpp_speedup"]) > 0.0]
    lines = [
        "# Phase9 Random Topology PIBT Stress Sweep",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic generates additional random DAG-like ICS topologies with different layer widths, "
            "branch/shortcut probabilities, and task source/goal distributions. It runs Python and C++ "
            "active-bag PIBT replay from the same node, edge, heuristic, and task records."
        ),
        "",
        f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "These are synthetic randomized topology stress rows, not separate real airport maps.",
        "",
        "## Stress Rows",
        "",
        (
            "| Scenario | Layers | Source/Goal | Tasks | Edges | Faults | Config | Py/C++ planned | "
            "Py/C++ decisions | Py/C++ conflicts | Mean diff | C++ speedup | Parity |"
        ),
        "|---|---|---|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {scenario} | {layers} | {source_mode}/{goal_mode} | {task_count} | {edge_count} | {faults} | "
            "{config} | {python_planned}/{cpp_planned} | {python_decisions}/{cpp_decisions} | "
            "{python_conflicts}/{cpp_conflicts} | {mean_travel_abs_diff:.12f} | {cpp_speedup:.3f} | "
            "{parity_pass} |".format(
                **{**row, "faults": _fault_label(row), "config": _config_label(row)}
            )
        )
    lines.extend(
        [
            "",
            "## Gate Status",
            "",
            f"- random topology rows: `{len(rows)}`",
            f"- total tasks: `{sum(int(row['task_count']) for row in rows)}`",
            f"- distinct layer layouts: `{len({row['layers'] for row in rows})}`",
            f"- median planned rate: `{_median(planned_rates):.3f}`",
            f"- median C++ local-call speedup: `{_median(speedups):.3f}x`",
            "- random-topology PIBT Python/C++ summary parity: PASS"
            if parity_pass
            else "- random-topology PIBT Python/C++ summary parity: FAIL",
            "- random-topology PIBT post-shield safety: PASS"
            if safety_pass
            else "- random-topology PIBT post-shield safety: FAIL",
            "- real heldout airport map: not covered",
            "",
            "## Remaining Work",
            "",
            "- broaden beyond DAG-like synthetic topologies to real heldout airport maps when fixtures are available",
            "- repeat stress timing on multiple machines before paper-grade throughput claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()
    cases = tuple(_build_case(spec) for spec in _case_specs())
    rows = build_rows(cases)
    write_table(rows)
    write_report(rows)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("Phase9 random topology PIBT stress parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("Phase9 random topology PIBT stress produced post-shield conflicts")
    print(
        "phase9_random_topology_pibt_stress_sweep "
        f"rows={len(rows)} tasks={sum(int(row['task_count']) for row in rows)}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
