from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "data" / "processed" / "phase8" / "phase8_synthetic_replay_cases.json"
SPEED = 2.5

FaultEdge = tuple[int, int]
FaultWindow = tuple[int, int, float, float]
MergeGroup = tuple[int, int, int]
NodeCapacity = tuple[int, int]
NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
TaskRecord = tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]


@dataclass(frozen=True)
class SyntheticCaseSpec:
    name: str
    seed: int
    task_count: int
    spacing: float
    fault_edges: tuple[FaultEdge, ...]
    fault_windows: tuple[FaultWindow, ...]
    node_capacities: tuple[NodeCapacity, ...] = ()
    merge_groups: tuple[MergeGroup, ...] = ()
    merge_capacity: int = 1
    merge_headway_seconds: float = 0.0


@dataclass(frozen=True)
class SyntheticReplayCase:
    spec: SyntheticCaseSpec
    node_records: tuple[NodeRecord, ...]
    edge_records: tuple[EdgeRecord, ...]
    heuristic_time: tuple[tuple[float, ...], ...]
    task_records: tuple[TaskRecord, ...]


def case_plan() -> tuple[SyntheticCaseSpec, ...]:
    return (
        SyntheticCaseSpec("synthetic_seed7_medium_repair", 7, 18, 3.0, (), ((4, 8, 4.0, 18.0),)),
        SyntheticCaseSpec(
            "synthetic_seed11_dense_multi_repair",
            11,
            24,
            1.4,
            (),
            ((7, 9, 5.0, 16.0), (8, 9, 10.0, 22.0)),
        ),
        SyntheticCaseSpec(
            "synthetic_seed17_static_plus_repair",
            17,
            20,
            2.2,
            ((4, 7),),
            ((5, 8, 0.0, 14.0),),
        ),
        SyntheticCaseSpec(
            "synthetic_seed23_repeated_repair",
            23,
            22,
            1.8,
            (),
            ((4, 8, 3.0, 8.0), (4, 8, 14.0, 21.0), (8, 9, 9.0, 15.0)),
        ),
        SyntheticCaseSpec(
            "synthetic_seed31_merge_buffer",
            31,
            26,
            0.9,
            (),
            ((4, 8, 2.0, 13.0),),
            ((8, 2), (9, 2)),
            ((4, 7, 7), (4, 8, 7), (5, 8, 8), (6, 8, 8)),
        ),
    )


def format_faults(fault_edges: tuple[FaultEdge, ...]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def format_fault_windows(fault_windows: tuple[FaultWindow, ...]) -> str:
    if not fault_windows:
        return "none"
    return ";".join(
        f"{start}->{end}@[{fault_start:.3f},{repair_time:.3f})"
        for start, end, fault_start, repair_time in fault_windows
    )


def python_replay_kwargs(
    spec: SyntheticCaseSpec,
    max_decisions_per_task: int,
) -> dict[str, object]:
    return {
        "max_tasks": spec.task_count,
        "fault_edges": set(spec.fault_edges),
        "max_decisions_per_task": max_decisions_per_task,
        "fault_windows": tuple(spec.fault_windows),
        "node_capacities": dict(spec.node_capacities),
        "merge_groups": {
            (start_node, end_node): group for start_node, end_node, group in spec.merge_groups
        },
        "merge_capacity": spec.merge_capacity,
        "merge_headway_seconds": spec.merge_headway_seconds,
    }


def cpp_replay_kwargs(
    spec: SyntheticCaseSpec,
    max_decisions_per_task: int,
) -> dict[str, object]:
    return {
        "max_tasks": spec.task_count,
        "fault_edges": list(spec.fault_edges),
        "max_decisions_per_task": max_decisions_per_task,
        "fault_windows": list(spec.fault_windows),
        "node_capacities": list(spec.node_capacities),
        "merge_groups": list(spec.merge_groups),
        "merge_capacity": spec.merge_capacity,
        "merge_headway_seconds": spec.merge_headway_seconds,
    }


def make_replay_case(spec: SyntheticCaseSpec) -> SyntheticReplayCase:
    rng = random.Random(spec.seed)
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

    edge_records: list[EdgeRecord] = []
    outgoing_by_node: dict[int, list[int]] = {node: [] for node in range(node_count)}
    travel_times: dict[tuple[int, int], float] = {}
    for start, end in edge_pairs:
        travel_time = rng.uniform(1.6, 5.5)
        travel_times[(start, end)] = travel_time
        edge_records.append((start, end, travel_time * SPEED, SPEED))
        outgoing_by_node[start].append(end)

    node_records: list[NodeRecord] = []
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
        node_records.append(
            (node, node_type, service_time, node % 4, node // 4, list(outgoing_by_node[node]))
        )

    heuristic_time = _all_pairs_shortest_time(node_count, travel_times)
    task_records = _make_task_records(spec)
    return SyntheticReplayCase(
        spec=spec,
        node_records=tuple(node_records),
        edge_records=tuple(edge_records),
        heuristic_time=heuristic_time,
        task_records=task_records,
    )


def write_manifest(path: Path = MANIFEST_PATH) -> Path:
    cases = [make_replay_case(spec) for spec in case_plan()]
    payload = {
        "schema": "czr005.phase8.synthetic_replay_cases.v1",
        "description": (
            "Fixed-seed synthetic ICS-like replay cases for Python/C++ compact replay parity."
        ),
        "speed": SPEED,
        "cases": [_case_to_dict(case) for case in cases],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def load_manifest_cases(path: Path = MANIFEST_PATH) -> tuple[SyntheticReplayCase, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "czr005.phase8.synthetic_replay_cases.v1":
        raise ValueError("unsupported synthetic replay manifest schema")
    return tuple(_case_from_dict(item) for item in payload["cases"])


def graph_from_case(case: SyntheticReplayCase):
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


def tasks_from_case(case: SyntheticReplayCase):
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


def _all_pairs_shortest_time(
    node_count: int,
    edge_travel_times: dict[tuple[int, int], float],
) -> tuple[tuple[float, ...], ...]:
    inf = 1.0e6
    distances = [[inf for _ in range(node_count)] for _ in range(node_count)]
    for node in range(node_count):
        distances[node][node] = 0.0
    for (start, end), travel_time in edge_travel_times.items():
        distances[start][end] = min(distances[start][end], travel_time)
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


def _make_task_records(spec: SyntheticCaseSpec) -> tuple[TaskRecord, ...]:
    rng = random.Random(spec.seed * 101 + spec.task_count)
    task_records: list[TaskRecord] = []
    starts = (0, 1, 2)
    goals = (10, 11)
    for task_id in range(spec.task_count):
        start = rng.choice(starts)
        goal = rng.choice(goals)
        pass_time = task_id * spec.spacing + rng.uniform(0.0, spec.spacing * 0.25)
        task_records.append(
            (
                f"{spec.name}:{task_id}",
                task_id,
                task_id,
                pass_time,
                pass_time + 180.0,
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
    return tuple(sorted(task_records, key=lambda task: (task[3], task[1], task[10])))


def _case_to_dict(case: SyntheticReplayCase) -> dict[str, Any]:
    return {
        "name": case.spec.name,
        "seed": case.spec.seed,
        "task_count": case.spec.task_count,
        "spacing": case.spec.spacing,
        "fault_edges": [list(item) for item in case.spec.fault_edges],
        "fault_windows": [list(item) for item in case.spec.fault_windows],
        "node_capacities": [list(item) for item in case.spec.node_capacities],
        "merge_groups": [list(item) for item in case.spec.merge_groups],
        "merge_capacity": case.spec.merge_capacity,
        "merge_headway_seconds": case.spec.merge_headway_seconds,
        "node_records": [
            [location, node_type, service_time, x, y, outgoing]
            for location, node_type, service_time, x, y, outgoing in case.node_records
        ],
        "edge_records": [list(item) for item in case.edge_records],
        "heuristic_time": [list(row) for row in case.heuristic_time],
        "task_records": [list(item) for item in case.task_records],
    }


def _case_from_dict(data: dict[str, Any]) -> SyntheticReplayCase:
    spec = SyntheticCaseSpec(
        name=str(data["name"]),
        seed=int(data["seed"]),
        task_count=int(data["task_count"]),
        spacing=float(data["spacing"]),
        fault_edges=tuple((int(start), int(end)) for start, end in data["fault_edges"]),
        fault_windows=tuple(
            (int(start), int(end), float(fault_start), float(repair_time))
            for start, end, fault_start, repair_time in data["fault_windows"]
        ),
        node_capacities=tuple(
            (int(node), int(capacity)) for node, capacity in data.get("node_capacities", [])
        ),
        merge_groups=tuple(
            (int(start), int(end), int(group))
            for start, end, group in data.get("merge_groups", [])
        ),
        merge_capacity=int(data.get("merge_capacity", 1)),
        merge_headway_seconds=float(data.get("merge_headway_seconds", 0.0)),
    )
    return SyntheticReplayCase(
        spec=spec,
        node_records=tuple(
            (
                int(location),
                int(node_type),
                float(service_time),
                int(x),
                int(y),
                [int(value) for value in outgoing],
            )
            for location, node_type, service_time, x, y, outgoing in data["node_records"]
        ),
        edge_records=tuple(
            (int(start), int(end), float(length), float(speed))
            for start, end, length, speed in data["edge_records"]
        ),
        heuristic_time=tuple(tuple(float(value) for value in row) for row in data["heuristic_time"]),
        task_records=tuple(
            (
                str(segment_id),
                int(task_id),
                int(pallet_id),
                float(pass_time),
                float(std),
                int(start),
                int(goal),
                int(original_start),
                int(original_goal),
                float(original_entry_time),
                str(leg),
                bool(early_bag_split),
                int(source_line),
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
            ) in data["task_records"]
        ),
    )
