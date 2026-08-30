#!/usr/bin/env python3
"""Freeze the outcome-blind V3R13 Stage-2 real-map cases.

This module only reads the frozen workloads, map profiles, and fault
registries.  It does not load a native binary or execute either Stage-2 arm.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005.io.legacy_tasks import expand_tasks, parse_legacy_tasks  # noqa: E402
from scripts.eval import g4irsf31_map_adapter as map_adapter  # noqa: E402
from scripts.eval import run_g4irsf28_service_potential as service_potential  # noqa: E402
from scripts.eval import run_g4irsf29_workload as map2_workload  # noqa: E402
from scripts.eval import run_g4irsf31_map2_native as map2_native  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_native as nanning_native  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_workload as nanning_workload  # noqa: E402


SCHEMA = "czr005.g4irsf32.v3r13.stage2_preregistered_cases.v1"
PROTOCOL_ID = "G4IRSF32_V3R13_CANDIDATE_A_CLOSED_LOOP_STAGE2_20260829"
STATUS = "READY_V3R13_STAGE2_PREREGISTERED_CONTROL_ONLY"
OUTPUT_PATH = ROOT / "outputs/tables/g4irsf32_v3r13_stage2_preregistered_cases.json"

ANCHOR_START = 19_200.0
ANCHOR_END = 19_800.0
SPEED_MPS = 2.5
EXPECTED_COUNTS = {
    1: {"raw_tasks": 540, "segments": 998, "external": 147, "local": 42},
    2: {"raw_tasks": 877, "segments": 1_599, "external": 147, "local": 71},
}
NANNING_ACTIVE_SCENARIO = "single_1"
NANNING_ACTIVE_EDGE = (50, 25)
NANNING_INACTIVE_SCENARIO = "single_8"
NANNING_INACTIVE_EDGE = (100, 102)
MAP2_FAULT_SCENARIO = "single_1"
MAP2_FAULT_EDGE = (6, 12)


class Stage2PreregistrationError(RuntimeError):
    """Raised when a frozen Stage-2 selection invariant does not hold."""


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    if is_dataclass(row):
        return asdict(row)
    raise Stage2PreregistrationError("canonical workload row is not an object")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage2PreregistrationError(f"JSON object required: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise Stage2PreregistrationError(
                        f"JSONL object required: {path}"
                    )
                rows.append(value)
    return rows


def _canonical_workloads() -> dict[str, dict[int, list[dict[str, Any]]]]:
    for scale, expected in ((1, 43_603), (2, 87_206)):
        manifest = _read_json(
            nanning_native.DEFAULT_TASK_DIR / f"nanning_{scale}x_manifest.json"
        )
        manifest_ok = (
            manifest.get("schema") == nanning_native.WORKLOAD_SCHEMA
            and manifest.get("status") == "COMPLETE"
            and manifest.get("scale") == scale
            and manifest.get("map_id") == nanning_native.MAP_ID
            and manifest.get("expanded_segment_count") == expected
        )
        if not manifest_ok:
            raise Stage2PreregistrationError(
                f"frozen Nanning {scale}x manifest changed"
            )

    profile = nanning_workload.load_map_profile(
        nanning_workload.DEFAULT_MAP_PROFILE
    )
    _header, source_raw = parse_legacy_tasks(nanning_workload.DEFAULT_SOURCE_RAW)
    projection = nanning_workload.build_original_projection(source_raw, profile)
    projected_original = nanning_workload._project_generated_tasks(
        source_raw,
        source_raw,
        projection,
        profile,
        inserted_id_offset=None,
    )
    storage = nanning_workload.select_storage_pair(projected_original, profile)
    if (
        int(storage["storage_in_goal"]),
        int(storage["storage_out_start"]),
    ) != (53, 53):
        raise Stage2PreregistrationError("frozen Nanning storage pair is not 53/53")

    generated_2x, _flight_rows, generation = (
        map2_workload.densify_flight_timetable(source_raw)
    )
    inserted_offset = int(generation["inserted_id_offset"])
    projected_2x = nanning_workload._project_generated_tasks(
        source_raw,
        generated_2x,
        projection,
        profile,
        inserted_id_offset=inserted_offset,
    )
    nanning = {
        1: [
            _row_dict(row)
            for row in expand_tasks(
                projected_original, storage_in_goal=53, storage_out_start=53
            )
        ],
        2: [
            _row_dict(row)
            for row in expand_tasks(
                projected_2x, storage_in_goal=53, storage_out_start=53
            )
        ],
    }

    map2_manifest = _read_json(map2_workload.DEFAULT_MANIFEST_OUTPUT)
    lifecycle = map2_manifest.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        raise Stage2PreregistrationError("map2 2x manifest lacks lifecycle")
    storage_in = int(lifecycle["storage_in_goal"])
    storage_out = int(lifecycle["storage_out_start"])
    if (storage_in, storage_out) != (47, 52):
        raise Stage2PreregistrationError("frozen map2 storage pair is not 47/52")
    map2 = {
        1: _read_jsonl(map2_native.DEFAULT_WORKLOAD_1X),
        2: [
            _row_dict(row)
            for row in expand_tasks(
                generated_2x,
                storage_in_goal=storage_in,
                storage_out_start=storage_out,
            )
        ],
    }

    full_expected = {1: 43_603, 2: 87_206}
    for map_name, scales in (("nanning", nanning), ("map2", map2)):
        for scale, rows in scales.items():
            if len(rows) != full_expected[scale]:
                raise Stage2PreregistrationError(
                    f"{map_name} {scale}x canonical count changed: {len(rows)}"
                )
    return {"nanning": nanning, "map2": map2}


def _slice_rows(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[int], list[dict[str, Any]], list[dict[str, Any]]]:
    anchor_ids = {
        int(row["task_id"])
        for row in rows
        if ANCHOR_START <= float(row["pass_time"]) < ANCHOR_END
    }
    selected = [dict(row) for row in rows if int(row["task_id"]) in anchor_ids]
    anchor_rows = [
        dict(row)
        for row in rows
        if int(row["task_id"]) in anchor_ids
        and ANCHOR_START <= float(row["pass_time"]) < ANCHOR_END
    ]
    return sorted(anchor_ids), selected, anchor_rows


def _static_route(
    row: Mapping[str, Any],
    *,
    outgoing: Mapping[int, Sequence[tuple[int, float]]],
    potential: Sequence[Sequence[float]],
    node_count: int,
) -> tuple[tuple[int, int], ...]:
    current = int(row["start"])
    goal = int(row["goal"])
    route: list[tuple[int, int]] = []
    visited: set[int] = set()
    while current != goal:
        if current in visited or len(route) >= node_count:
            raise Stage2PreregistrationError(
                f"static route did not terminate for {row['segment_id']}"
            )
        visited.add(current)
        candidates = [
            (travel + float(potential[next_node][goal]), next_node)
            for next_node, travel in outgoing.get(current, ())
        ]
        if not candidates:
            raise Stage2PreregistrationError(
                f"static route is unreachable for {row['segment_id']}"
            )
        _score, next_node = min(candidates)
        route.append((current, next_node))
        current = next_node
    return tuple(route)


def _nanning_route_evidence(
    target_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    profile = map_adapter.load_map_profile(
        nanning_native.DEFAULT_MAP_PROFILE, storage_source_nodes=[53]
    )
    active_edges = tuple(
        (start, end, length, SPEED_MPS)
        for start, end, length, _speed in profile.edge_records
    )
    potential, contract = service_potential.service_aware_potential(
        profile.node_records, active_edges
    )
    outgoing: dict[int, list[tuple[int, float]]] = {}
    for start, end, length, speed in active_edges:
        outgoing.setdefault(start, []).append((end, length / speed))
    for values in outgoing.values():
        values.sort()

    counts = {NANNING_ACTIVE_EDGE: 0, NANNING_INACTIVE_EDGE: 0}
    for row in target_rows:
        route = _static_route(
            row,
            outgoing=outgoing,
            potential=potential,
            node_count=len(profile.node_records),
        )
        for edge in counts:
            counts[edge] += edge in route
    active_count = counts[NANNING_ACTIVE_EDGE]
    inactive_count = counts[NANNING_INACTIVE_EDGE]
    return {
        "method": "G31_OFF_SERVICE_AWARE_STATIC_LOCAL_POTENTIAL",
        "speed_mps": SPEED_MPS,
        "candidate_outcomes_consulted": False,
        "potential_contract": {
            "mode": contract["mode"],
            "formula": contract["formula"],
            "minimum_service_seconds": contract["minimum_service_seconds"],
        },
        "target_segment_count": len(target_rows),
        "edge_traversal_counts": {
            "50->25": active_count,
            "100->102": inactive_count,
        },
        "checks": {
            "source_chain_active_single_1": active_count > 0,
            "source_chain_inactive_single_8": inactive_count == 0,
        },
        "pass": active_count > 0 and inactive_count == 0,
    }


def _fault_registry_evidence() -> dict[str, Any]:
    nanning_rows: dict[str, list[list[int]]] = {}
    for scenario in (NANNING_ACTIVE_SCENARIO, NANNING_INACTIVE_SCENARIO):
        per_scale = [
            nanning_native.load_fault_scenario(scale, scenario)["fault_edges"]
            for scale in (1, 2)
        ]
        if per_scale[0] != per_scale[1]:
            raise Stage2PreregistrationError(
                f"Nanning {scenario} differs between scales"
            )
        nanning_rows[scenario] = [list(edge) for edge in per_scale[0]]
    if nanning_rows[NANNING_ACTIVE_SCENARIO] != [list(NANNING_ACTIVE_EDGE)]:
        raise Stage2PreregistrationError("Nanning single_1 edge changed")
    if nanning_rows[NANNING_INACTIVE_SCENARIO] != [
        list(NANNING_INACTIVE_EDGE)
    ]:
        raise Stage2PreregistrationError("Nanning single_8 edge changed")

    map2_line_ids = map2_native._PAPER_FAULT_ROWS[MAP2_FAULT_SCENARIO]
    map2_edges = [list(map2_native.FAULT_SEED_EDGES[line]) for line in map2_line_ids]
    if map2_edges != [list(MAP2_FAULT_EDGE)]:
        raise Stage2PreregistrationError("map2 single_1 edge changed")
    return {
        "nanning": nanning_rows,
        "map2": {MAP2_FAULT_SCENARIO: map2_edges},
    }


def _map2_structural_negative_control() -> dict[str, Any]:
    profile = map2_native.map2_profile()
    indegree = {int(row[0]): 0 for row in profile.node_records}
    edge_pairs: set[tuple[int, int]] = set()
    for start, end, _length, _speed in profile.edge_records:
        indegree[end] += 1
        edge_pairs.add((start, end))
    source_indegrees = {str(node): indegree[node] for node in profile.start_nodes}
    mixed = [node for node in profile.start_nodes if indegree[node] > 0]
    checks = {
        "all_source_indegrees_zero": not mixed,
        "registered_fault_edge_present": MAP2_FAULT_EDGE in edge_pairs,
    }
    return {
        "map_id": map2_native.MAP_ID,
        "start_nodes": list(profile.start_nodes),
        "source_indegrees": source_indegrees,
        "mixed_origin_source_nodes": mixed,
        "checks": checks,
        "pass": all(checks.values()),
    }


def _case_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scale in (1, 2):
        population_id = f"stage2_{scale}x_anchor_task_closure"
        rows.extend(
            [
                {
                    "case_id": f"g4irsf32_s2_nanning_{scale}x_stable_2p5",
                    "map_id": nanning_native.MAP_ID,
                    "scale": scale,
                    "speed_mps": SPEED_MPS,
                    "role": "NANNING_STABLE_TARGET",
                    "fault_scenario": None,
                    "fault_edges": [],
                    "population_id": population_id,
                },
                {
                    "case_id": (
                        f"g4irsf32_s2_nanning_{scale}x_"
                        "fault_source_chain_active_single_1"
                    ),
                    "map_id": nanning_native.MAP_ID,
                    "scale": scale,
                    "speed_mps": SPEED_MPS,
                    "role": "NANNING_SOURCE_CHAIN_ACTIVE_FAULT",
                    "fault_scenario": NANNING_ACTIVE_SCENARIO,
                    "fault_edges": [list(NANNING_ACTIVE_EDGE)],
                    "population_id": population_id,
                },
                {
                    "case_id": (
                        f"g4irsf32_s2_nanning_{scale}x_"
                        "fault_source_chain_inactive_single_8"
                    ),
                    "map_id": nanning_native.MAP_ID,
                    "scale": scale,
                    "speed_mps": SPEED_MPS,
                    "role": "NANNING_SOURCE_CHAIN_INACTIVE_FAULT",
                    "fault_scenario": NANNING_INACTIVE_SCENARIO,
                    "fault_edges": [list(NANNING_INACTIVE_EDGE)],
                    "population_id": population_id,
                },
                {
                    "case_id": f"g4irsf32_s2_map2_{scale}x_stable_2p5",
                    "map_id": map2_native.MAP_ID,
                    "scale": scale,
                    "speed_mps": SPEED_MPS,
                    "role": "MAP2_STABLE_STRUCTURAL_SENTINEL",
                    "fault_scenario": None,
                    "fault_edges": [],
                    "population_id": population_id,
                },
                {
                    "case_id": (
                        f"g4irsf32_s2_map2_{scale}x_fault_sentinel_single_1"
                    ),
                    "map_id": map2_native.MAP_ID,
                    "scale": scale,
                    "speed_mps": SPEED_MPS,
                    "role": "MAP2_FAULT_STRUCTURAL_SENTINEL",
                    "fault_scenario": MAP2_FAULT_SCENARIO,
                    "fault_edges": [list(MAP2_FAULT_EDGE)],
                    "population_id": population_id,
                },
            ]
        )
    return rows


def build_preregistration() -> dict[str, Any]:
    workloads = _canonical_workloads()
    populations: dict[str, Any] = {}
    all_checks: dict[str, bool] = {}
    for scale in (1, 2):
        n_task_ids, n_rows, n_anchor = _slice_rows(workloads["nanning"][scale])
        m_task_ids, m_rows, m_anchor = _slice_rows(workloads["map2"][scale])
        n_segment_ids = [str(row["segment_id"]) for row in n_rows]
        m_segment_ids = [str(row["segment_id"]) for row in m_rows]
        target_rows = [
            row for row in n_anchor if int(row["start"]) in (49, 53)
        ]
        external_count = sum(int(row["start"]) == 53 for row in target_rows)
        local_count = sum(int(row["start"]) == 49 for row in target_rows)
        expected = EXPECTED_COUNTS[scale]
        checks = {
            "task_ids_match_between_maps": n_task_ids == m_task_ids,
            "anchor_segment_ids_match_between_maps": [
                str(row["segment_id"]) for row in n_anchor
            ]
            == [str(row["segment_id"]) for row in m_anchor],
            "ordered_segment_ids_match_between_maps": n_segment_ids
            == m_segment_ids,
            "raw_task_count": len(n_task_ids) == expected["raw_tasks"],
            "segment_count": len(n_rows) == expected["segments"],
            "external_window_count": external_count == expected["external"],
            "local_window_count": local_count == expected["local"],
            "task_id_closure": {int(row["task_id"]) for row in n_rows}
            == set(n_task_ids),
        }
        if not all(checks.values()):
            raise Stage2PreregistrationError(
                f"{scale}x outcome-blind slice gate failed: {checks}"
            )
        route = _nanning_route_evidence(target_rows)
        if not route["pass"]:
            raise Stage2PreregistrationError(
                f"{scale}x static control route classification failed"
            )
        all_checks[f"population_{scale}x"] = all(checks.values())
        all_checks[f"route_{scale}x"] = bool(route["pass"])
        populations[f"{scale}x"] = {
            "population_id": f"stage2_{scale}x_anchor_task_closure",
            "scale": scale,
            "anchor_task_ids": n_task_ids,
            "ordered_segment_ids": n_segment_ids,
            "raw_task_count": len(n_task_ids),
            "segment_count": len(n_segment_ids),
            "anchor_window_segment_count": len(n_anchor),
            "nanning_target_segment_ids": [
                str(row["segment_id"]) for row in target_rows
            ],
            "nanning_target_composition": {
                "external_start_53": external_count,
                "local_start_49": local_count,
            },
            "static_g31_off_route": route,
            "checks": checks,
        }

    fault_registry = _fault_registry_evidence()
    map2_negative = _map2_structural_negative_control()
    all_checks["fault_registries"] = True
    all_checks["map2_structural_negative_control"] = bool(map2_negative["pass"])
    cases = _case_rows()
    all_checks["ten_unique_semantic_cases"] = len(cases) == 10 and len(
        {row["case_id"] for row in cases}
    ) == 10
    passed = all(all_checks.values())
    if not passed:
        raise Stage2PreregistrationError(
            f"V3R13 Stage-2 preregistration failed: {all_checks}"
        )
    return {
        "schema": SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "status": STATUS,
        "pass": True,
        "selection": {
            "basis": "FROZEN_WORKLOAD_AND_STATIC_G31_OFF_ROUTE_ONLY",
            "candidate_outcomes_consulted": False,
            "candidate_execution_started": False,
            "native_runtime_executed": False,
            "anchor_window": {
                "start_inclusive": ANCHOR_START,
                "end_exclusive": ANCHOR_END,
            },
            "closure": "all canonical lifecycle segments sharing an anchor task_id",
            "order": "canonical workload order",
            "speed_mps": SPEED_MPS,
            "registered_paired_arms": ["off", "closed_loop"],
        },
        "inputs": {
            "source_timetable": nanning_workload.DEFAULT_SOURCE_RAW.relative_to(
                ROOT
            ).as_posix(),
            "nanning_profile": nanning_workload.DEFAULT_MAP_PROFILE.relative_to(
                ROOT
            ).as_posix(),
            "nanning_fault_registry": nanning_native.DEFAULT_FAULT_PROTOCOL.relative_to(
                ROOT
            ).as_posix(),
            "nanning_1x_manifest": (
                nanning_native.DEFAULT_TASK_DIR / "nanning_1x_manifest.json"
            ).relative_to(ROOT).as_posix(),
            "nanning_2x_manifest": (
                nanning_native.DEFAULT_TASK_DIR / "nanning_2x_manifest.json"
            ).relative_to(ROOT).as_posix(),
            "map2_profile": map2_native.CANONICAL_MAP_PATH.relative_to(ROOT).as_posix(),
            "map2_1x_workload": map2_native.DEFAULT_WORKLOAD_1X.relative_to(
                ROOT
            ).as_posix(),
            "map2_2x_manifest": map2_workload.DEFAULT_MANIFEST_OUTPUT.relative_to(
                ROOT
            ).as_posix(),
        },
        "populations": populations,
        "fault_registries": fault_registry,
        "map2_structural_negative_control": map2_negative,
        "cases": cases,
        "checks": all_checks,
    }


def write_preregistration(
    value: Mapping[str, Any], path: Path = OUTPUT_PATH
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    value = build_preregistration()
    write_preregistration(value)
    print(
        f"{value['status']} cases={len(value['cases'])} "
        f"output={OUTPUT_PATH.relative_to(ROOT).as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
