"""Build faithful 1x/2x simulated baggage streams for the Nanning map.

The temporal demand model remains the thesis model: one day of flight
departures and one complete baggage manifest per flight.  G31 changes only
the physical airport projection.  Logical check-in lanes are assigned to
Nanning loader nodes, every flight is assigned atomically to one Nanning
unloader, and early bags retain the original two-leg EBS lifecycle.

For 2x, this module reuses the validated G29 rule: insert one complete flight
manifest halfway to the next departure in the same original flight stream.
It deliberately does not duplicate already-expanded route segments.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import heapq
import json
import math
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005.io.legacy_tasks import (  # noqa: E402
    RawLegacyTask,
    expand_tasks,
    parse_legacy_tasks,
    write_task_jsonl,
)
from scripts.eval import run_g4irsf29_workload as g29  # noqa: E402


SCHEMA = "czr005.g4irsf31.nanning_workload_manifest.v1"
STATUS = "COMPLETE"
PROTOCOL_1X = "FLIGHT_TIMETABLE_PRESERVING_NANNING_OD_PROJECTION_1X"
PROTOCOL_2X = (
    "FLIGHT_TIMETABLE_PRESERVING_NANNING_OD_PROJECTION_"
    "AND_INTERMEDIATE_FLIGHT_DENSIFICATION_2X"
)
DEFAULT_SOURCE_RAW = ROOT / "legacy/jichang_origin_readonly/inputdata.txt"
DEFAULT_MAP_PROFILE = ROOT / "data/processed/maps/nanning_airport_profile.json"
DEFAULT_OUTPUT_DIR = ROOT / "artifacts/tasks/g4irsf31_nanning"
DEFAULT_SPEED_MPS = 2.5
DAY_AXIS_SECONDS = 86_400.0

FlightKey = tuple[float, int, str]
SourceLane = tuple[str, int]


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _flight_key(task: RawLegacyTask) -> FlightKey:
    if task.unloader is None:
        raise ValueError("flight projection requires the Unloader field")
    return float(task.std), int(task.end), str(task.unloader)


def _profile_nodes(profile: Mapping[str, Any]) -> dict[int, Mapping[str, Any]]:
    nodes = {int(row["location"]): row for row in profile.get("nodes", [])}
    if sorted(nodes) != list(range(len(nodes))):
        raise ValueError("map profile node locations must be dense 0..N-1")
    return nodes


def _role_nodes(profile: Mapping[str, Any], name: str) -> tuple[int, ...]:
    roles = profile.get("business_roles", {})
    values = tuple(int(value) for value in roles.get(name, []))
    if not values:
        raise ValueError(f"map profile business role {name!r} is empty")
    return values


def load_map_profile(path: Path) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    if not str(profile.get("status", "")).startswith("COMPLETE"):
        raise ValueError("Nanning map profile is not complete")
    nodes = _profile_nodes(profile)
    for role in (
        "standard_loader_nodes",
        "transfer_loader_nodes",
        "unloader_nodes",
    ):
        values = _role_nodes(profile, role)
        if any(value not in nodes for value in values):
            raise ValueError(f"map role {role!r} references an unknown node")
    if not profile.get("business_roles", {}).get("storage_pairs"):
        raise ValueError("map profile has no storage pair candidates")
    return profile


def _balanced_assignment(
    groups: Sequence[tuple[Any, Sequence[RawLegacyTask]]],
    candidates: Sequence[int],
) -> tuple[dict[Any, int], dict[int, int]]:
    """Assign atomic groups to candidates with deterministic load balancing."""

    loads = {int(candidate): 0 for candidate in candidates}
    result: dict[Any, int] = {}
    ordered_groups = sorted(
        groups,
        key=lambda item: (-len(item[1]), repr(item[0])),
    )
    for key, rows in ordered_groups:
        target = min(loads, key=lambda node: (loads[node], node))
        result[key] = target
        loads[target] += len(rows)
    return result, loads


def build_original_projection(
    raw_tasks: Sequence[RawLegacyTask],
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze task-ID to Nanning source/goal before any 2x densification."""

    standard_loaders = _role_nodes(profile, "standard_loader_nodes")
    transfer_loaders = _role_nodes(profile, "transfer_loader_nodes")
    unloaders = _role_nodes(profile, "unloader_nodes")

    by_lane: dict[SourceLane, list[RawLegacyTask]] = defaultdict(list)
    by_flight: dict[FlightKey, list[RawLegacyTask]] = defaultdict(list)
    for task in raw_tasks:
        if task.loader is None:
            raise ValueError("source projection requires the Loader field")
        by_flight[_flight_key(task)].append(task)
        if task.loader != "T":
            by_lane[(str(task.loader), int(task.start))].append(task)

    lane_assignment, standard_load = _balanced_assignment(
        list(by_lane.items()), standard_loaders
    )
    goal_assignment, goal_load = _balanced_assignment(
        list(by_flight.items()), unloaders
    )
    transfer_groups = [
        (flight, tuple(row for row in rows if row.loader == "T"))
        for flight, rows in by_flight.items()
    ]
    transfer_assignment, transfer_load = _balanced_assignment(
        [(key, rows) for key, rows in transfer_groups if rows], transfer_loaders
    )

    task_projection: dict[int, tuple[int, int]] = {}
    for task in raw_tasks:
        flight = _flight_key(task)
        if task.loader == "T":
            start = transfer_assignment[flight]
        else:
            start = lane_assignment[(str(task.loader), int(task.start))]
        task_projection[int(task.task_id)] = (start, goal_assignment[flight])

    return {
        "task_projection": task_projection,
        "source_lane_assignment": lane_assignment,
        "flight_goal_assignment": goal_assignment,
        "transfer_flight_assignment": transfer_assignment,
        "standard_loader_load": standard_load,
        "transfer_loader_load": transfer_load,
        "unloader_load": goal_load,
    }


def _project_generated_tasks(
    source_raw: Sequence[RawLegacyTask],
    generated: Sequence[RawLegacyTask],
    projection: Mapping[str, Any],
    profile: Mapping[str, Any],
    *,
    inserted_id_offset: int | None,
) -> tuple[RawLegacyTask, ...]:
    nodes = _profile_nodes(profile)
    by_original_id = {
        int(task.task_id): int(task.task_id) for task in source_raw
    }
    if inserted_id_offset is not None:
        for rank, task in enumerate(source_raw):
            by_original_id[inserted_id_offset + rank] = int(task.task_id)

    task_projection: Mapping[int, tuple[int, int]] = projection["task_projection"]
    projected: list[RawLegacyTask] = []
    for task in generated:
        original_id = by_original_id.get(int(task.task_id))
        if original_id is None:
            raise ValueError(f"generated task {task.task_id} has no original manifest row")
        start, goal = task_projection[original_id]
        projected.append(
            replace(
                task,
                start=start,
                end=goal,
                loader=str(nodes[start]["alias"]),
                unloader=str(nodes[goal]["alias"]),
            )
        )
    return tuple(projected)


def _service_aware_distances(
    profile: Mapping[str, Any], speed_mps: float
) -> list[list[float]]:
    nodes = _profile_nodes(profile)
    incoming: list[list[tuple[int, float]]] = [[] for _ in nodes]
    for edge in profile.get("edges", []):
        start, end = int(edge["start"]), int(edge["end"])
        incoming[end].append((start, float(edge["length"]) / speed_mps))

    distances = [[math.inf] * len(nodes) for _ in nodes]
    for goal in nodes:
        reverse = [math.inf] * len(nodes)
        reverse[goal] = 0.0
        heap: list[tuple[float, int]] = [(0.0, goal)]
        while heap:
            cost, node = heapq.heappop(heap)
            if cost != reverse[node]:
                continue
            service = max(float(nodes[node].get("service_time", 0.0)), 0.0)
            for predecessor, travel in incoming[node]:
                candidate = cost + travel + (0.0 if node == goal else service)
                if candidate < reverse[predecessor]:
                    reverse[predecessor] = candidate
                    heapq.heappush(heap, (candidate, predecessor))
        for source, value in enumerate(reverse):
            distances[source][goal] = value
    return distances


def select_storage_pair(
    projected_original: Sequence[RawLegacyTask],
    profile: Mapping[str, Any],
    *,
    speed_mps: float = DEFAULT_SPEED_MPS,
) -> dict[str, Any]:
    """Choose the single EBS pair used by both algorithms and both scales."""

    early = [
        task for task in projected_original if task.std - task.entry_time >= 4_800.0
    ]
    distances = _service_aware_distances(profile, speed_mps)
    candidates: list[dict[str, Any]] = []
    for row in profile["business_roles"]["storage_pairs"]:
        storage_in = int(row["storage_in_goal"])
        storage_out = int(row["storage_out_start"])
        total = sum(
            distances[task.start][storage_in] + distances[storage_out][task.end]
            for task in early
        )
        candidates.append(
            {
                **dict(row),
                "mean_free_flow_seconds": total / len(early),
            }
        )
    return min(
        candidates,
        key=lambda row: (
            float(row["mean_free_flow_seconds"]),
            int(row["storage_in_goal"]),
            int(row["storage_out_start"]),
        ),
    )


def _counts(values: Iterable[int]) -> dict[str, int]:
    return {
        str(key): value for key, value in sorted(Counter(values).items())
    }


def build_workload(
    *,
    scale: int,
    source_raw_path: Path = DEFAULT_SOURCE_RAW,
    map_profile_path: Path = DEFAULT_MAP_PROFILE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    if scale not in (1, 2):
        raise ValueError("G31 Nanning workload scale must be 1 or 2")
    profile = load_map_profile(map_profile_path)
    header, source_raw = parse_legacy_tasks(source_raw_path)
    projection = build_original_projection(source_raw, profile)

    inserted_id_offset: int | None = None
    if scale == 1:
        generated = source_raw
        generation = {
            "input_flight_count": len({_flight_key(task) for task in source_raw}),
            "inserted_flight_count": 0,
            "stream_count": len(
                {(task.end, task.unloader) for task in source_raw}
            ),
        }
    else:
        generated, _, generation = g29.densify_flight_timetable(source_raw)
        inserted_id_offset = int(generation["inserted_id_offset"])

    projected = _project_generated_tasks(
        source_raw,
        generated,
        projection,
        profile,
        inserted_id_offset=inserted_id_offset,
    )
    projected_original = _project_generated_tasks(
        source_raw,
        source_raw,
        projection,
        profile,
        inserted_id_offset=None,
    )
    storage = select_storage_pair(projected_original, profile)

    raw_output = output_dir / f"nanning_{scale}x_raw.txt"
    canonical_output = output_dir / f"nanning_{scale}x_canonical.jsonl"
    manifest_output = output_dir / f"nanning_{scale}x_manifest.json"
    g29.write_raw_tasks(header, projected, raw_output)
    _, reparsed = parse_legacy_tasks(raw_output)
    expanded = expand_tasks(
        reparsed,
        storage_in_goal=int(storage["storage_in_goal"]),
        storage_out_start=int(storage["storage_out_start"]),
    )
    write_task_jsonl(expanded, canonical_output)

    nodes = _profile_nodes(profile)
    direct = sum(task.std - task.entry_time < 4_800.0 for task in reparsed)
    raw_count = len(reparsed)
    expected_raw = scale * len(source_raw)
    source_flights = len({_flight_key(task) for task in source_raw})
    manifest = {
        "schema": SCHEMA,
        "status": STATUS,
        "protocol": PROTOCOL_1X if scale == 1 else PROTOCOL_2X,
        "scale": scale,
        "map_id": profile["map_id"],
        "map_profile": _display_path(map_profile_path),
        "source_timetable": _display_path(source_raw_path),
        "raw_output": _display_path(raw_output),
        "canonical_output": _display_path(canonical_output),
        "raw_task_count": raw_count,
        "expanded_segment_count": len(expanded),
        "direct_raw_task_count": direct,
        "early_split_raw_task_count": raw_count - direct,
        "source_flight_count": source_flights,
        "flight_count": source_flights * scale,
        "inserted_flight_count": int(generation["inserted_flight_count"]),
        "stream_count": int(generation["stream_count"]),
        "storage_pair": storage,
        "mapping_rule": {
            "non_transfer_sources": (
                "atomic original (Loader,start) lanes greedily balanced over "
                "Nanning standard loader nodes"
            ),
            "transfer_sources": (
                "atomic original flights greedily balanced over Nanning GTC loaders"
            ),
            "destinations": (
                "each original flight manifest is assigned atomically and greedily "
                "balanced over Nanning type-2 unloader nodes"
            ),
            "ebs": (
                "one graph-derived storage pair is frozen from the 1x projected "
                "workload and reused by both algorithms and both scales"
            ),
        },
        "source_lane_assignment": {
            f"{key[0]}|{key[1]}": int(value)
            for key, value in sorted(projection["source_lane_assignment"].items())
        },
        "source_loads": {
            **{
                str(key): value
                for key, value in projection["standard_loader_load"].items()
            },
            **{
                str(key): value
                for key, value in projection["transfer_loader_load"].items()
            },
        },
        "goal_loads": {
            str(key): value for key, value in projection["unloader_load"].items()
        },
        "raw_by_start": _counts(task.start for task in reparsed),
        "raw_by_goal": _counts(task.end for task in reparsed),
        "timing": {
            "day_axis_seconds": DAY_AXIS_SECONDS,
            "earliest_entry_time": min(task.entry_time for task in reparsed),
            "latest_entry_time": max(task.entry_time for task in reparsed),
            "earliest_std": min(task.std for task in reparsed),
            "latest_std": max(task.std for task in reparsed),
        },
        "lifecycle": {
            "early_bag_threshold_seconds": 4_800.0,
            "storage_out_lead_seconds": 2_700.0,
            "storage_in_goal": int(storage["storage_in_goal"]),
            "storage_out_start": int(storage["storage_out_start"]),
            "segment_id_rule": "<task_id>:direct|storage_in|storage_out",
        },
        "role_aliases": {
            "storage_in": nodes[int(storage["storage_in_goal"])]["alias"],
            "storage_out": nodes[int(storage["storage_out_start"])]["alias"],
        },
        "invariants": {
            "raw_count_matches_scale": raw_count == expected_raw,
            "expanded_count_matches_scale": len(expanded) == scale * 43_603,
            "flight_count_matches_scale": source_flights * scale == 360 * scale,
            "direct_count_matches_scale": direct == scale * 13_409,
            "early_count_matches_scale": raw_count - direct == scale * 15_097,
            "all_starts_are_registered_loaders": set(
                task.start for task in reparsed
            ).issubset(
                set(_role_nodes(profile, "standard_loader_nodes"))
                | set(_role_nodes(profile, "transfer_loader_nodes"))
            ),
            "all_goals_are_registered_unloaders": set(
                task.end for task in reparsed
            ).issubset(set(_role_nodes(profile, "unloader_nodes"))),
            "same_day_no_time_compression": (
                0.0 <= min(task.entry_time for task in reparsed)
                and max(task.entry_time for task in reparsed) < DAY_AXIS_SECONDS
                and max(task.std for task in reparsed) < DAY_AXIS_SECONDS
            ),
            "canonical_expanded_from_written_raw": True,
        },
    }
    if not all(manifest["invariants"].values()):
        raise ValueError("Nanning workload invariants did not hold")
    manifest_output.parent.mkdir(parents=True, exist_ok=True)
    manifest_output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scale", type=int, choices=(1, 2), required=True)
    parser.add_argument("--source-raw", type=Path, default=DEFAULT_SOURCE_RAW)
    parser.add_argument("--map-profile", type=Path, default=DEFAULT_MAP_PROFILE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = build_workload(
        scale=args.scale,
        source_raw_path=args.source_raw,
        map_profile_path=args.map_profile,
        output_dir=args.output_dir,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "map_id": result["map_id"],
                "scale": result["scale"],
                "raw_task_count": result["raw_task_count"],
                "expanded_segment_count": result["expanded_segment_count"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
