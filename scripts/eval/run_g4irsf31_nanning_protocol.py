#!/usr/bin/env python3
"""Freeze the Nanning Chapter-5 comparison and interruption protocol.

The eight interruption edges are selected from topology and projected 1x
business demand only.  This module does not call HCA, S4, or inspect either
algorithm's outcomes.  It emits the same 8-single/5-pair/3-triple shape as
thesis Table 5.5 and computes a raw-bag reachability ceiling for both G31
workload scales.
"""

from __future__ import annotations

import argparse
from collections import Counter
import heapq
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005.io.legacy_tasks import RawLegacyTask, parse_legacy_tasks  # noqa: E402


SCHEMA = "czr005.g4irsf31.nanning_experiment_protocol.v1"
DEFAULT_PROFILE = ROOT / "data/processed/maps/nanning_airport_profile.json"
DEFAULT_TASK_DIR = ROOT / "artifacts/tasks/g4irsf31_nanning"
DEFAULT_OUTPUT = ROOT / "configs/eval/g4irsf31_nanning_fault_scenarios.json"
NOMINAL_SPEED_MPS = 2.5
FIXED_START_EPOCH = 8_260.0
FIXED_END_EPOCH = 98_259.0

# Frozen before any S4 result is inspected.  Dense IDs are accompanied by
# source aliases/external IDs in the emitted file, so the map-specific mapping
# remains readable if a future converter changes its dense-ID convention.
LINE_EDGES: Mapping[int, tuple[int, int]] = {
    1: (50, 25),  # IU25 -> ID26: international redundant high-flow trunk
    2: (28, 29),  # IU3 -> IU4: international high-flow structural cut
    3: (94, 76),  # DU38 -> DU20: domestic redundant high-flow trunk
    4: (78, 80),  # DU22 -> DU24: DU-ring high-flow branch
    5: (112, 113),  # DD18 -> DD19: DD-ring largest business cut
    6: (29, 112),  # IU4 -> DD18: highest-flow cross-system link
    7: (34, 55),  # IU9 -> IUMES: highest-flow recode branch
    8: (100, 102),  # DD6 -> DD8: remaining high-flow DD branch
}

LINE_SELECTION_BASIS: Mapping[int, str] = {
    1: "international internal edge with the largest nominal 1x shortest-path exposure among single-edge-removal-reachable trunks",
    2: "international internal positive-capacity edge with the largest nominal 1x shortest-path exposure among edges whose removal blocks projected bags",
    3: "domestic internal edge with the largest nominal 1x shortest-path exposure among single-edge-removal-reachable trunks",
    4: "highest-exposure positive-capacity internal DU-to-DU branch whose removal blocks projected bags",
    5: "positive-capacity internal DD-to-DD branch with the largest single-edge raw-bag reachability loss",
    6: "highest-exposure positive-capacity internal edge whose endpoints belong to different workbook systems",
    7: "highest-exposure positive-capacity internal edge entering a documented recode station",
    8: "highest-exposure remaining positive-capacity internal DD-to-DD branch whose removal blocks projected bags",
}

# The combinations are copied as a shape, not as a claim that the new physical
# lines equal the paper's old-map lines or affected-conveyor counts.
TABLE_5_5_SHAPE: tuple[tuple[str, tuple[int, ...]], ...] = (
    ("single_1", (1,)),
    ("single_2", (2,)),
    ("single_3", (3,)),
    ("single_4", (4,)),
    ("single_5", (5,)),
    ("single_6", (6,)),
    ("single_7", (7,)),
    ("single_8", (8,)),
    ("pair_1_7", (1, 7)),
    ("pair_2_4", (2, 4)),
    ("pair_3_5", (3, 5)),
    ("pair_4_5", (4, 5)),
    ("pair_5_7", (5, 7)),
    ("triple_2_4_6", (2, 4, 6)),
    ("triple_3_5_8", (3, 5, 8)),
    ("triple_4_6_7", (4, 6, 7)),
)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return payload


def _adjacency(
    profile: Mapping[str, Any],
    removed: Iterable[tuple[int, int]] = (),
) -> dict[int, tuple[int, ...]]:
    removed_set = set(removed)
    adjacency = {int(node["location"]): [] for node in profile["nodes"]}
    for edge in profile["edges"]:
        pair = (int(edge["start"]), int(edge["end"]))
        if pair not in removed_set:
            adjacency[pair[0]].append(pair[1])
    return {node: tuple(sorted(targets)) for node, targets in adjacency.items()}


def _reachable(adjacency: Mapping[int, Sequence[int]], start: int) -> set[int]:
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for target in adjacency[node]:
            if target not in seen:
                seen.add(target)
                stack.append(target)
    return seen


def topology_upper_raw_bags(
    profile: Mapping[str, Any],
    raw_tasks: Sequence[RawLegacyTask],
    *,
    removed_edges: Iterable[tuple[int, int]],
    early_threshold_seconds: float,
    storage_in_goal: int,
    storage_out_start: int,
) -> int:
    """Return the lifecycle-aware raw-bag reachability ceiling."""

    adjacency = _adjacency(profile, removed_edges)
    sources = {task.start for task in raw_tasks}
    sources.add(storage_out_start)
    reach = {source: _reachable(adjacency, source) for source in sources}
    feasible = 0
    for task in raw_tasks:
        if task.slack_at_entry >= early_threshold_seconds:
            admitted = (
                storage_in_goal in reach[task.start]
                and task.end in reach[storage_out_start]
            )
        else:
            admitted = task.end in reach[task.start]
        feasible += int(admitted)
    return feasible


def _weighted_adjacency(
    profile: Mapping[str, Any],
) -> dict[int, tuple[tuple[int, float], ...]]:
    values: dict[int, list[tuple[int, float]]] = {
        int(node["location"]): [] for node in profile["nodes"]
    }
    for edge in profile["edges"]:
        values[int(edge["start"])].append(
            (int(edge["end"]), float(edge["length"]) / NOMINAL_SPEED_MPS)
        )
    return {
        node: tuple(sorted(targets, key=lambda row: row[0]))
        for node, targets in values.items()
    }


def _shortest_path(
    adjacency: Mapping[int, Sequence[tuple[int, float]]],
    start: int,
    goal: int,
) -> tuple[int, ...]:
    """Return one deterministic free-flow shortest path."""

    heap: list[tuple[float, tuple[int, ...], int]] = [(0.0, (start,), start)]
    best: dict[int, tuple[float, tuple[int, ...]]] = {start: (0.0, (start,))}
    while heap:
        distance, path, node = heapq.heappop(heap)
        if best.get(node) != (distance, path):
            continue
        if node == goal:
            return path
        for target, weight in adjacency[node]:
            candidate = (distance + weight, path + (target,))
            previous = best.get(target)
            if previous is None or candidate < previous:
                best[target] = candidate
                heapq.heappush(heap, (candidate[0], candidate[1], target))
    raise ValueError(f"no baseline route from {start} to {goal}")


def nominal_edge_exposure(
    profile: Mapping[str, Any],
    raw_tasks: Sequence[RawLegacyTask],
    *,
    early_threshold_seconds: float,
    storage_in_goal: int,
    storage_out_start: int,
) -> Counter[tuple[int, int]]:
    """Count raw-bag legs using each deterministic nominal shortest path."""

    legs: Counter[tuple[int, int]] = Counter()
    for task in raw_tasks:
        if task.slack_at_entry >= early_threshold_seconds:
            legs[(task.start, storage_in_goal)] += 1
            legs[(storage_out_start, task.end)] += 1
        else:
            legs[(task.start, task.end)] += 1

    adjacency = _weighted_adjacency(profile)
    exposure: Counter[tuple[int, int]] = Counter()
    for (start, goal), count in legs.items():
        path = _shortest_path(adjacency, start, goal)
        for pair in zip(path, path[1:]):
            exposure[pair] += count
    return exposure


def build_protocol(
    profile: Mapping[str, Any],
    workloads: Mapping[int, tuple[Mapping[str, Any], Sequence[RawLegacyTask]]],
) -> dict[str, Any]:
    nodes = {int(row["location"]): row for row in profile["nodes"]}
    edges = {
        (int(row["start"]), int(row["end"])): row
        for row in profile["edges"]
    }
    one_manifest, one_tasks = workloads[1]
    lifecycle = one_manifest["lifecycle"]
    storage_in = int(lifecycle["storage_in_goal"])
    storage_out = int(lifecycle["storage_out_start"])
    threshold = float(lifecycle["early_bag_threshold_seconds"])
    exposure = nominal_edge_exposure(
        profile,
        one_tasks,
        early_threshold_seconds=threshold,
        storage_in_goal=storage_in,
        storage_out_start=storage_out,
    )

    line_rows: list[dict[str, Any]] = []
    for line_id, pair in LINE_EDGES.items():
        edge = edges[pair]
        start = nodes[pair[0]]
        end = nodes[pair[1]]
        line_rows.append(
            {
                "line_id": line_id,
                "edge": list(pair),
                "from_alias": start["alias"],
                "from_external_id": start["external_id"],
                "to_alias": end["alias"],
                "to_external_id": end["external_id"],
                "from_system": start["system_key"],
                "to_system": end["system_key"],
                "length_m": float(edge["length"]),
                "pallet_capacity": int(edge["pallet_capacity"]),
                "nominal_1x_shortest_path_leg_exposure_count": exposure[pair],
                "selection_basis": LINE_SELECTION_BASIS[line_id],
            }
        )

    scales: dict[str, Any] = {}
    for scale, (manifest, tasks) in sorted(workloads.items()):
        scale_lifecycle = manifest["lifecycle"]
        if (
            int(scale_lifecycle["storage_in_goal"]) != storage_in
            or int(scale_lifecycle["storage_out_start"]) != storage_out
        ):
            raise ValueError("both scales must use the same frozen storage proxy")
        total = len(tasks)
        scenario_rows = []
        for name, line_ids in TABLE_5_5_SHAPE:
            removed = tuple(LINE_EDGES[value] for value in line_ids)
            upper = topology_upper_raw_bags(
                profile,
                tasks,
                removed_edges=removed,
                early_threshold_seconds=float(
                    scale_lifecycle["early_bag_threshold_seconds"]
                ),
                storage_in_goal=storage_in,
                storage_out_start=storage_out,
            )
            scenario_rows.append(
                {
                    "scenario": name,
                    "line_ids": list(line_ids),
                    "fault_edges": [list(pair) for pair in removed],
                    "topology_upper_raw_bags": upper,
                    "topology_blocked_raw_bags": total - upper,
                    "topology_upper_rate": upper / total,
                }
            )
        scales[f"{scale}x"] = {
            "raw_bag_count": total,
            "expanded_segment_count": int(manifest["expanded_segment_count"]),
            "scenario_count": len(scenario_rows),
            "scenarios": scenario_rows,
        }

    return {
        "schema": SCHEMA,
        "status": "COMPLETE_PROTOCOL_ONLY_NO_ALGORITHM_RUN",
        "map_id": profile["map_id"],
        "selection_inputs": {
            "topology": f"{len(nodes)} nodes / {len(edges)} directed edges",
            "business_population": "projected Nanning 1x raw workload",
            "algorithm_outcomes_consulted": False,
            "nominal_shortest_path_speed_mps": NOMINAL_SPEED_MPS,
            "eligible_edge_rule": (
                "internal business edges only; no loader, unloader, or type-7 "
                "storage endpoint; positive pallet capacity; positive nominal "
                "1x shortest-path exposure"
            ),
        },
        "fixed_window": {
            "start_epoch": FIXED_START_EPOCH,
            "end_epoch": FIXED_END_EPOCH,
            "fault_start_epoch": FIXED_START_EPOCH,
            "repair_within_window": False,
        },
        "storage_proxy": {
            "storage_in_goal": storage_in,
            "storage_out_start": storage_out,
            "alias": nodes[storage_in]["alias"],
            "source_role": "EMPTY_PALLET_STORAGE_EBS_PROXY_CANDIDATE",
            "real_ebs_claimed": False,
        },
        "line_count": len(line_rows),
        "lines": line_rows,
        "table_5_5_shape": "8 singles + 5 pairs + 3 triples",
        "scales": scales,
        "claim_boundary": {
            "new_map_line_identity": "NANNING_PRE_REGISTERED_RECONSTRUCTION",
            "paper_affected_conveyor_counts_reused": False,
            "pair_5_7_old_map_override_reused": False,
            "topology_upper_is_not_an_algorithm_result": True,
        },
    }


def _workload(
    scale: int,
    task_dir: Path,
) -> tuple[dict[str, Any], tuple[RawLegacyTask, ...]]:
    manifest = _load_json(task_dir / f"nanning_{scale}x_manifest.json")
    _header, tasks = parse_legacy_tasks(task_dir / f"nanning_{scale}x_raw.txt")
    return manifest, tasks


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--task-dir", type=Path, default=DEFAULT_TASK_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    protocol = build_protocol(
        _load_json(args.profile),
        {scale: _workload(scale, args.task_dir) for scale in (1, 2)},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(protocol, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output}: {protocol['line_count']} lines, "
        f"{len(TABLE_5_5_SHAPE)} scenarios per scale"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
