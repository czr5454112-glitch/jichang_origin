#!/usr/bin/env python3
"""Confirm the frozen G31 S4 policy on the original map2 populations.

This runner is intentionally independent of the historical G26--G30 runners.
It rebuilds a ``RuntimeMapProfile`` from the canonical map2 data, loads the
original 1x population or the G29 schedule-preserving 2x population, and uses
the generic G31 map adapter.  Fault cells reuse the deterministic local
fixed-point construction; no runtime learning or full-route planning is
introduced.

The executable matrix is eight stable-speed cells plus thirty measurable
fault cells.  The archived ``pair_5_7`` label conflict is recorded as NM for
both scales and cannot be selected for execution.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import lru_cache
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import g4irsf31_map_adapter as map_adapter  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402
from scripts.eval import run_g4irsf27_fault_values as g27_fault  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_native as g31_native  # noqa: E402
from scripts.eval.g4irsf11_fixed_map import (  # noqa: E402
    CANONICAL_MAP_PATH,
    canonical_map_data,
)


SCHEMA = "czr005.g4irsf31.map2_final_policy_case.v1"
AGGREGATE_SCHEMA = "czr005.g4irsf31.map2_final_policy_aggregate.v1"
FINAL_POLICY_PROTOCOL = "G31_FINAL_POLICY_MAP2_V1"
MAP_ID = "protected_map2_54_nodes_69_edges"
STORAGE_NODE = 52
MAP_NODE_COUNT = 54
MAP_EDGE_COUNT = 69
SPEEDS_MPS = (1.5, 2.0, 2.5, 3.0)
SCALE_COUNTS = {1: (28_506, 43_603), 2: (57_012, 87_206)}
FIXED_START_EPOCH = 8_260.0
FIXED_END_EPOCH = 98_259.0
MAX_EVENTS = 60_000_000

LOCAL_POTENTIAL_DESCENT_GUARD = g31_native.LOCAL_POTENTIAL_DESCENT_GUARD
LOCAL_SOFTWARE_QUEUE_CAP = g31_native.LOCAL_SOFTWARE_QUEUE_CAP
DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY = (
    g31_native.DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
)
GOAL_ARRIVAL_COMPLETION = g31_native.GOAL_ARRIVAL_COMPLETION

COMPLETE = "COMPLETE_G31_MAP2_FIXED_HORIZON_CAPACITY_EVIDENCE"
DRY_RUN_READY = "READY_G31_MAP2_NATIVE_DRY_RUN"
FAILED = "FAILED_G31_MAP2_NATIVE_ADMISSION"

DEFAULT_WORKLOAD_1X = ROOT / "data/processed/tasks/inputdata.jsonl"
DEFAULT_WORKLOAD_2X = (
    ROOT / "artifacts/tasks/g4irsf29/inputdata_flight_densified_2x.jsonl"
)
DEFAULT_BINARY_DIR = ROOT / "build/g4irsf24_dlp_release/python"
DEFAULT_CASE_ROOT = ROOT / "outputs/runtime/g4irsf31_map2_native"
DEFAULT_AGGREGATE = ROOT / "outputs/tables/g4irsf31_map2_native.json"

Executor = Callable[..., Mapping[str, Any]]


class Map2NativeError(RuntimeError):
    """Raised when the map2 final-policy protocol cannot be prepared."""


@dataclass(frozen=True)
class CaseSpec:
    case_id: str
    group: str
    scale: int
    speed_mps: float
    fault_scenario: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "paper_table": "5.5" if self.fault_scenario else "5.2",
            "group": self.group,
            "scale": self.scale,
            "speed_mps": self.speed_mps,
            "fault_scenario": self.fault_scenario,
        }


@dataclass(frozen=True)
class Workload:
    scale: int
    source_path: Path
    protocol: str
    rows: tuple[dict[str, Any], ...]
    raw_bag_count: int
    segment_count: int


def _speed_label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


_PAPER_FAULT_ROWS = {
    suffix: tuple(int(value) for value in line_ids)
    for suffix, line_ids, _affected, _success in g26.PAPER_T5_5
}
FAULT_SCENARIOS = tuple(
    suffix for suffix in _PAPER_FAULT_ROWS if suffix != "pair_5_7"
)
FAULT_SEED_EDGES = dict(g26.PAPER_LINE_SEED_EDGES)
NM_SCENARIO = "pair_5_7"
NM_REASON = (
    "archived workbook label conflicts with the registered line-5/line-7 "
    "mapping; no fresh protocol-identifying measurement is available"
)


def _primary_cases() -> tuple[CaseSpec, ...]:
    stable = [
        CaseSpec(
            case_id=f"t5_2_map2_{scale}x_speed_{_speed_label(speed)}",
            group="stable_speed",
            scale=scale,
            speed_mps=speed,
        )
        for scale in (1, 2)
        for speed in SPEEDS_MPS
    ]
    faults = [
        CaseSpec(
            case_id=f"t5_5_map2_{scale}x_fault_{scenario}",
            group="all_day_line_interruption",
            scale=scale,
            speed_mps=2.5,
            fault_scenario=scenario,
        )
        for scale in (1, 2)
        for scenario in FAULT_SCENARIOS
    ]
    return tuple((*stable, *faults))


PRIMARY_CASES = _primary_cases()
CASE_IDS = tuple(case.case_id for case in PRIMARY_CASES)
_CASE_BY_ID = {case.case_id: case for case in PRIMARY_CASES}
NM_CASE_IDS = tuple(
    f"t5_5_map2_{scale}x_fault_{NM_SCENARIO}" for scale in (1, 2)
)


def case_by_id(case_id: str) -> CaseSpec:
    if case_id in NM_CASE_IDS:
        raise Map2NativeError(
            f"{case_id} is NM and intentionally not executable: {NM_REASON}"
        )
    try:
        return _CASE_BY_ID[case_id]
    except KeyError as exc:
        raise Map2NativeError(f"unsupported G31 map2 case: {case_id}") from exc


def campaign_manifest() -> dict[str, Any]:
    return {
        "protocol": FINAL_POLICY_PROTOCOL,
        "primary_cases": [case.as_dict() for case in PRIMARY_CASES],
        "primary_case_count": len(PRIMARY_CASES),
        "stable_speed_case_count": sum(
            case.group == "stable_speed" for case in PRIMARY_CASES
        ),
        "measurable_line_interruption_case_count": sum(
            case.group == "all_day_line_interruption" for case in PRIMARY_CASES
        ),
        "not_measurable_cases": [
            {
                "case_id": case_id,
                "scenario": NM_SCENARIO,
                "scale": scale,
                "status": "NM",
                "execution_allowed": False,
                "reason": NM_REASON,
            }
            for scale, case_id in zip((1, 2), NM_CASE_IDS)
        ],
        "not_measurable_case_count": len(NM_CASE_IDS),
    }


@lru_cache(maxsize=1)
def map2_profile() -> map_adapter.RuntimeMapProfile:
    """Build the generic G31 profile directly from canonical map2 data."""

    payload = canonical_map_data()
    nodes = tuple(
        (
            int(row["location"]),
            int(row["node_type"]),
            float(row.get("service_time", 0.0)),
            int(row.get("x", 0)),
            int(row.get("y", 0)),
            tuple(int(value) for value in row.get("outgoing", [])),
        )
        for row in payload["nodes"]
    )
    edges = tuple(
        sorted(
            (
                int(row["start"]),
                int(row["end"]),
                float(row["length"]),
                float(row["speed"]),
            )
            for row in payload["edges"]
        )
    )
    return map_adapter.RuntimeMapProfile(
        name="canonical_map2",
        source_path=CANONICAL_MAP_PATH,
        node_records=nodes,
        edge_records=edges,
        start_nodes=tuple(int(value) for value in payload["start_nodes"]),
        goal_nodes=tuple(int(value) for value in payload["end_nodes"]),
        storage_source_nodes=(STORAGE_NODE,),
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Map2NativeError(f"JSON object required: {path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


@lru_cache(maxsize=8)
def load_workload(
    scale: int,
    workload_1x: Path = DEFAULT_WORKLOAD_1X,
    workload_2x: Path = DEFAULT_WORKLOAD_2X,
) -> Workload:
    if scale not in SCALE_COUNTS:
        raise Map2NativeError("scale must be 1 or 2")
    source = (workload_1x if scale == 1 else workload_2x).resolve(strict=True)
    rows: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise Map2NativeError(f"workload row is not an object: {source}")
                rows.append(value)
    expected_raw, expected_segments = SCALE_COUNTS[scale]
    raw_count = len({int(row["task_id"]) for row in rows})
    segment_ids = [str(row["segment_id"]) for row in rows]
    if (
        len(rows) != expected_segments
        or raw_count != expected_raw
        or len(segment_ids) != len(set(segment_ids))
    ):
        raise Map2NativeError(
            "map2 workload population mismatch: "
            f"scale={scale} raw={raw_count}/{expected_raw} "
            f"segments={len(rows)}/{expected_segments}"
        )
    protocol = (
        "ORIGINAL_PAPER_CANONICAL_EXPANDED_1X"
        if scale == 1
        else "G29_SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_2X"
    )
    return Workload(
        scale=scale,
        source_path=source,
        protocol=protocol,
        rows=tuple(rows),
        raw_bag_count=raw_count,
        segment_count=len(rows),
    )


def _registered_fault_scenario(
    case: CaseSpec,
    workload: Workload,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    if case.fault_scenario is None:
        raise Map2NativeError("stable case has no fault scenario")
    line_ids = _PAPER_FAULT_ROWS[case.fault_scenario]
    fault_edges = [list(FAULT_SEED_EDGES[line_id]) for line_id in line_ids]
    topology = g26.topology_reachable_raw_bag_upper_bound(
        workload.rows, request["edge_records"], fault_edges
    )
    upper = int(topology["topology_reachable_raw_bag_upper_bound"])
    return {
        "scenario": case.fault_scenario,
        "line_ids": list(line_ids),
        "fault_edges": fault_edges,
        "measurement_status": "MEASURABLE_REGISTERED_MAP2_LINE_MAPPING",
        "topology_upper_raw_bags": upper,
        "topology_blocked_raw_bags": workload.raw_bag_count - upper,
        "topology_upper_rate": upper / workload.raw_bag_count,
    }


def prepare_native_request(
    case: CaseSpec,
    workload: Workload,
    *,
    binary: Path | None,
) -> tuple[
    dict[str, Any],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    dict[str, Any],
]:
    profile = map2_profile()
    request, potential_contract = map_adapter.build_s4_request(
        profile,
        workload.rows,
        binary=binary,
        scenario=f"g4irsf31_map2_{case.case_id}",
        max_events=MAX_EVENTS,
        max_simulation_time=FIXED_END_EPOCH,
        trace_limit=0,
        event_trace_limit=0,
        summary_only=False,
        edge_speed_mps=case.speed_mps,
        enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True,
        complete_on_goal_arrival=True,
    )
    runtime_rows = tuple(dict(row) for row in workload.rows)
    rejected: tuple[dict[str, Any], ...] = ()
    if case.fault_scenario is None:
        local: dict[str, Any] = {
            "activation": "FAULT_STRUCTURAL_VALUES_EXACT_OFF",
            "learned_from_runtime_data": False,
            "fault_edges": [],
            "source_rejected_unreachable_segment_count": 0,
            "runtime_reachable_segment_count": workload.segment_count,
            "artifact_contract": None,
            "artifact": None,
        }
    else:
        scenario = _registered_fault_scenario(case, workload, request)
        runtime_rows, rejected, local = g31_native._prepare_fault_values(
            request, workload.rows, scenario, potential_contract
        )
        local["protocol_scenario"] = scenario
    local["service_aware_potential"] = dict(potential_contract)
    local["local_potential_descent_guard"] = dict(
        LOCAL_POTENTIAL_DESCENT_GUARD
    )
    local["direct_neighbor_merge_calendar_visibility"] = dict(
        DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
    )
    local["goal_arrival_completion"] = dict(GOAL_ARRIVAL_COMPLETION)
    return request, runtime_rows, rejected, local


def _portable_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _map_contract(profile: map_adapter.RuntimeMapProfile) -> dict[str, Any]:
    return {
        "map_id": MAP_ID,
        "builder": "canonical_map_data_to_RuntimeMapProfile",
        "source_path": _portable_path(profile.source_path),
        "node_count": len(profile.node_records),
        "directed_edge_count": len(profile.edge_records),
        "start_nodes": list(profile.start_nodes),
        "goal_nodes": list(profile.goal_nodes),
        "storage_source_nodes": list(profile.storage_source_nodes),
    }


def _selection(case: CaseSpec, workload: Workload) -> dict[str, Any]:
    return {
        "mode": "full",
        "scale": case.scale,
        "workload_source": _portable_path(workload.source_path),
        "workload_protocol": workload.protocol,
        "selected_raw_bag_count": workload.raw_bag_count,
        "selected_segment_count": workload.segment_count,
        "scheduled_arrival_source": "canonical_pass_time",
        "hca_release_trace_applied": False,
        "whole_population_fixed_denominator": True,
    }


def _comparison_contract(case: CaseSpec, workload: Workload) -> dict[str, Any]:
    return {
        "capacity": {
            "protocol": "SAME_CANONICAL_SCHEDULE_EACH_FRAMEWORK_OWN_SOURCE",
            "raw_bag_denominator": workload.raw_bag_count,
            "fixed_start_epoch": FIXED_START_EPOCH,
            "fixed_end_epoch": FIXED_END_EPOCH,
            "max_events": MAX_EVENTS,
            "speed_mps": case.speed_mps,
            "fault_scenario": case.fault_scenario,
        },
        "timing": {
            "comparison_allowed_in_s4_artifact": False,
            "requires_both_frameworks_complete_full_population": True,
            "survivor_only_timing_allowed": False,
        },
    }


def execute_case(
    case_id: str,
    *,
    workload_1x: Path = DEFAULT_WORKLOAD_1X,
    workload_2x: Path = DEFAULT_WORKLOAD_2X,
    binary: Path | None,
    dry_run: bool = False,
    executor: Executor | None = None,
) -> dict[str, Any]:
    case = case_by_id(case_id)
    workload = load_workload(case.scale, workload_1x, workload_2x)
    request, runtime_rows, rejected, local = prepare_native_request(
        case, workload, binary=binary
    )
    profile = map2_profile()
    common = {
        "schema": SCHEMA,
        "protocol": FINAL_POLICY_PROTOCOL,
        "case_id": case.case_id,
        "case": case.as_dict(),
        "map_id": MAP_ID,
        "map_profile": _map_contract(profile),
        "selection": _selection(case, workload),
        "comparison_contract": _comparison_contract(case, workload),
        "request_contract": g31_native._request_contract(
            request, runtime_rows, rejected, local
        ),
    }
    if dry_run:
        return {
            **common,
            "status": DRY_RUN_READY,
            "native_execution_started": False,
        }
    if binary is None:
        raise Map2NativeError("binary is required unless --dry-run is used")

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise Map2NativeError("native executor did not return summary and bag rows")
    if any(not isinstance(row, Mapping) for row in bags):
        raise Map2NativeError("native bag result contains a non-object row")

    combined = [dict(row) for row in bags] + g27_fault._synthetic_source_rejections(
        rejected
    )
    outcome = g26.summarize_paper_outcome(
        workload.rows, combined, total_raw_bags=workload.raw_bag_count
    )
    safety = g31_native._runtime_admission(
        case,
        workload,
        request,
        runtime_rows,
        rejected,
        local,
        summary,
        bags,
        outcome,
    )
    return {
        **common,
        "status": COMPLETE if safety["pass"] else FAILED,
        "native_execution_started": True,
        "outcome": {
            "requested_segment_count": workload.segment_count,
            "runtime_requested_reachable_segment_count": len(runtime_rows),
            "source_rejected_unreachable_segment_count": len(rejected),
            **outcome,
        },
        "timing": g31_native._timing_evidence(workload, combined, outcome),
        "safety": safety,
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "event_count": int(summary.get("event_count", 0)),
            "decision_count": int(summary.get("decision_count", 0)),
            "declared_max_events": summary.get("declared_max_events"),
            "declared_max_simulation_time": summary.get(
                "declared_max_simulation_time"
            ),
            "event_limit_reached": summary.get("event_limit_reached"),
            "time_limit_reached": summary.get("time_limit_reached"),
        },
    }


def _contract_current(value: Mapping[str, Any]) -> bool:
    case_id = value.get("case_id")
    if case_id not in _CASE_BY_ID:
        return False
    case = _CASE_BY_ID[str(case_id)]
    expected_raw, expected_segments = SCALE_COUNTS[case.scale]
    selection = value.get("selection")
    profile = value.get("map_profile")
    request = value.get("request_contract")
    policy = request.get("policy") if isinstance(request, Mapping) else None
    return (
        value.get("schema") == SCHEMA
        and value.get("protocol") == FINAL_POLICY_PROTOCOL
        and value.get("map_id") == MAP_ID
        and value.get("case") == case.as_dict()
        and isinstance(profile, Mapping)
        and profile.get("builder") == "canonical_map_data_to_RuntimeMapProfile"
        and profile.get("node_count") == MAP_NODE_COUNT
        and profile.get("directed_edge_count") == MAP_EDGE_COUNT
        and profile.get("storage_source_nodes") == [STORAGE_NODE]
        and isinstance(selection, Mapping)
        and selection.get("mode") == "full"
        and selection.get("selected_raw_bag_count") == expected_raw
        and selection.get("selected_segment_count") == expected_segments
        and selection.get("hca_release_trace_applied") is False
        and isinstance(request, Mapping)
        and request.get("max_simulation_time") == FIXED_END_EPOCH
        and request.get("max_events") == MAX_EVENTS
        and request.get("local_queue_capacity")
        == map_adapter.G31_LOCAL_QUEUE_CAPACITY
        and isinstance(policy, Mapping)
        and policy.get("local_potential_descent_guard")
        == LOCAL_POTENTIAL_DESCENT_GUARD
        and policy.get("local_software_queue_cap") == LOCAL_SOFTWARE_QUEUE_CAP
        and policy.get("direct_neighbor_merge_calendar_visibility")
        == DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
        and policy.get("goal_arrival_completion") == GOAL_ARRIVAL_COMPLETION
    )


def _artifact_admitted(value: Mapping[str, Any]) -> bool:
    safety = value.get("safety")
    return (
        _contract_current(value)
        and value.get("status") == COMPLETE
        and isinstance(safety, Mapping)
        and safety.get("pass") is True
    )


def _dry_artifact_ready(value: Mapping[str, Any]) -> bool:
    return (
        _contract_current(value)
        and value.get("status") == DRY_RUN_READY
        and value.get("native_execution_started") is False
    )


def _portable_artifact_paths(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize descriptive source paths without changing case admission."""

    normalized = dict(value)
    profile = value.get("map_profile")
    if isinstance(profile, Mapping):
        normalized_profile = dict(profile)
        source_path = normalized_profile.get("source_path")
        if isinstance(source_path, str):
            normalized_profile["source_path"] = _portable_path(Path(source_path))
        normalized["map_profile"] = normalized_profile
    selection = value.get("selection")
    if isinstance(selection, Mapping):
        normalized_selection = dict(selection)
        workload_source = normalized_selection.get("workload_source")
        if isinstance(workload_source, str):
            normalized_selection["workload_source"] = _portable_path(
                Path(workload_source)
            )
        normalized["selection"] = normalized_selection
    return normalized


def aggregate_results(case_root: Path) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    stale: list[str] = []
    for case_id in CASE_IDS:
        path = case_root / f"{case_id}.json"
        if not path.is_file():
            continue
        value = _read_json(path)
        if not _contract_current(value):
            stale.append(case_id)
            continue
        by_id[case_id] = _portable_artifact_paths(value)
    complete = sorted(
        case_id for case_id, value in by_id.items() if _artifact_admitted(value)
    )
    ready = sorted(
        case_id for case_id, value in by_id.items() if _dry_artifact_ready(value)
    )
    failed = sorted(
        case_id for case_id, value in by_id.items() if value.get("status") == FAILED
    )
    missing = sorted(set(CASE_IDS) - by_id.keys() - set(stale))
    manifest = campaign_manifest()
    return {
        "schema": AGGREGATE_SCHEMA,
        "protocol": FINAL_POLICY_PROTOCOL,
        "status": "COMPLETE" if len(complete) == len(CASE_IDS) else "PARTIAL",
        "map_id": MAP_ID,
        "fixed_window": {
            "start_epoch": FIXED_START_EPOCH,
            "end_epoch": FIXED_END_EPOCH,
            "max_events": MAX_EVENTS,
        },
        "expected_executable_case_count": len(CASE_IDS),
        "expected_stable_speed_case_count": 8,
        "expected_measurable_fault_case_count": 30,
        "not_measurable_case_count": len(NM_CASE_IDS),
        "not_measurable_cases": manifest["not_measurable_cases"],
        "observed_current_case_count": len(by_id),
        "complete_case_ids": complete,
        "dry_run_ready_case_ids": ready,
        "failed_case_ids": failed,
        "stale_case_ids": sorted(stale),
        "missing_case_ids": missing,
        "campaign_manifest": manifest,
        "cases": [by_id[case_id] for case_id in sorted(by_id)],
    }


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _resolve_binary(path: Path | None) -> Path:
    if path is not None:
        return _rooted(path).resolve(strict=True)
    candidates = sorted(DEFAULT_BINARY_DIR.glob("czr005_cpp*.pyd"))
    if not candidates:
        raise Map2NativeError("no Release native binary found; pass --binary")
    return candidates[-1].resolve()


def _add_workload_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workload-1x", type=Path, default=DEFAULT_WORKLOAD_1X)
    parser.add_argument("--workload-2x", type=Path, default=DEFAULT_WORKLOAD_2X)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    case = commands.add_parser("case", help="run or dry-run one map2 case")
    case.add_argument("--case-id", required=True, choices=CASE_IDS)
    _add_workload_args(case)
    case.add_argument("--binary", type=Path)
    case.add_argument("--output", type=Path, required=True)
    case.add_argument("--dry-run", action="store_true")
    case.add_argument("--force", action="store_true")

    resume = commands.add_parser("resume", help="resume selected map2 cases")
    resume.add_argument("--case-id", action="append", choices=CASE_IDS)
    _add_workload_args(resume)
    resume.add_argument("--binary", type=Path)
    resume.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    resume.add_argument("--dry-run", action="store_true")
    resume.add_argument("--force", action="store_true")

    aggregate = commands.add_parser("aggregate", help="aggregate map2 case JSON")
    aggregate.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    aggregate.add_argument("--output", type=Path, default=DEFAULT_AGGREGATE)
    return parser


def _run_one(args: argparse.Namespace, case_id: str, output: Path) -> int:
    if output.is_file() and not args.force:
        existing = _read_json(output)
        if _artifact_admitted(existing) or (
            args.dry_run and _dry_artifact_ready(existing)
        ):
            print(json.dumps({"status": "SKIPPED_EXISTING", "case_id": case_id}))
            return 0
        raise Map2NativeError(
            f"existing artifact is stale or incompatible for {case_id}; "
            "use --force to replace it"
        )
    binary = None if args.dry_run else _resolve_binary(args.binary)
    payload = execute_case(
        case_id,
        workload_1x=_rooted(args.workload_1x),
        workload_2x=_rooted(args.workload_2x),
        binary=binary,
        dry_run=args.dry_run,
    )
    _write_json(output, payload)
    print(json.dumps({"status": payload["status"], "case_id": case_id}))
    return 0 if payload["status"] in {COMPLETE, DRY_RUN_READY} else 2


def _resume(args: argparse.Namespace) -> int:
    case_root = _rooted(args.case_root)
    selected = tuple(dict.fromkeys(args.case_id or CASE_IDS))
    exit_code = 0
    for case_id in selected:
        exit_code = _run_one(args, case_id, case_root / f"{case_id}.json")
        if exit_code:
            break
    aggregate = aggregate_results(case_root)
    _write_json(case_root / "aggregate.json", aggregate)
    print(
        json.dumps(
            {
                "status": "RESUME_COMPLETE" if exit_code == 0 else "RESUME_STOPPED",
                "aggregate_status": aggregate["status"],
                "dry_run_ready": len(aggregate["dry_run_ready_case_ids"]),
            }
        )
    )
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "aggregate":
        payload = aggregate_results(_rooted(args.case_root))
        output = _rooted(args.output)
        _write_json(output, payload)
        print(json.dumps({"status": payload["status"], "output": str(output)}))
        return 0 if payload["status"] == "COMPLETE" else 2
    if args.command == "resume":
        return _resume(args)
    return _run_one(args, args.case_id, _rooted(args.output))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Map2NativeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G31 map2 native failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
