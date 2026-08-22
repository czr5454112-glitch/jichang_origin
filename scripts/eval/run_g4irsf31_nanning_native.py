#!/usr/bin/env python3
"""Run the unchanged S4/J2/E2 policy on the Nanning G31 populations.

The primary matrix contains the eight Table-5.2-style stable-speed cells
(1x/2x by four speeds) and the thirty-two Table-5.5-style interruption cells
(1x/2x by sixteen pre-registered Nanning scenarios).  Every cell uses its own
canonical scheduled arrivals; it never waits for or substitutes an HCA release
trace.  This makes fixed-denominator capacity comparable once the matching HCA
cell exists, while timing remains descriptive until both arms complete the
entire population.

Fault cells retain the same S4/J2/E2/FIFO runtime.  Their deterministic local
structural values are rebuilt from the selected Nanning graph, the active edge
speed, and the service-aware static potential.  They are not learned values.
The twelve Table-5.4 observation-bias cells are registered separately as
non-exact reconstruction context and are not primary G31 executions.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
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
from scripts.eval import run_g4irsf24_native_race as g24  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402
from scripts.eval import run_g4irsf27_bias_experiments as g27_bias  # noqa: E402
from scripts.eval import run_g4irsf27_fault_values as g27_fault  # noqa: E402


SCHEMA = "czr005.g4irsf31.nanning_s4_case.v1"
AGGREGATE_SCHEMA = "czr005.g4irsf31.nanning_s4_aggregate.v1"
WORKLOAD_SCHEMA = "czr005.g4irsf31.nanning_workload_manifest.v1"
FAULT_PROTOCOL_SCHEMA = "czr005.g4irsf31.nanning_experiment_protocol.v1"

MAP_ID = "nanning_topology_examples_1_2_namespaced_ics156"
STORAGE_NODE = 53
SPEEDS_MPS = (1.5, 2.0, 2.5, 3.0)
SCALE_COUNTS = {1: (28_506, 43_603), 2: (57_012, 87_206)}
FIXED_START_EPOCH = 8_260.0
HCA_MAX_EPOCHS = 90_000
FIXED_END_EPOCH = 98_259.0
MAX_EVENTS = 60_000_000
FAULT_REPAIR_EPOCH = FIXED_END_EPOCH + 7.0 * 24.0 * 60.0 * 60.0

LOCAL_POTENTIAL_DESCENT_GUARD = {
    "enabled": True,
    "rule": "H_eff(next,goal)+epsilon<H_eff(current,goal)",
    "read_scope": "current_and_direct_outgoing_neighbors",
    "decision_scope": "one_next_edge_at_current_junction",
    "no_descending_action": "hold_retry",
    "learning_active": False,
    "learned_values_allowed": False,
}

LOCAL_SOFTWARE_QUEUE_CAP = {
    "local_queue_capacity": map_adapter.G31_LOCAL_QUEUE_CAPACITY,
    "semantics": (
        "no configured software queue cap; service calendar/R3 and E4/J2 "
        "retained; capacity-triggered PIBT relief inactive"
    ),
}

DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY = {
    "enabled": True,
    "read_scope": "direct_outgoing_merge_neighbor_service_calendar_scalar",
    "score_input": "existing_target_next_available_calendar_wait",
    "score_weight": "existing_calendar_wait_weight",
    "merge_authority": "E4/J2_unchanged",
    "decision_scope": "one_next_edge_at_current_junction",
    "learning_active": False,
}

GOAL_ARRIVAL_COMPLETION = {
    "enabled": True,
    "terminal_event": "physical_goal_edge_exit",
    "goal_service": "not_reserved_or_executed",
    "legacy_reference": "HCA_Tasks_ICS_goal_arrival_completion",
}
GOAL_ARRIVAL_COMPLETION_CLAIM = (
    "physical_goal_edge_exit_terminal;goal_service_not_reserved;"
    "legacy_HCA_Tasks_ICS_completion_semantics"
)

COMPLETE = "COMPLETE_G31_FIXED_HORIZON_CAPACITY_EVIDENCE"
DRY_RUN_READY = "READY_G31_NATIVE_DRY_RUN"
FAILED = "FAILED_G31_NATIVE_ADMISSION"

DEFAULT_TASK_DIR = ROOT / "artifacts/tasks/g4irsf31_nanning"
DEFAULT_MAP_PROFILE = ROOT / "data/processed/maps/nanning_airport_profile.json"
DEFAULT_FAULT_PROTOCOL = (
    ROOT / "configs/eval/g4irsf31_nanning_fault_scenarios.json"
)
DEFAULT_BINARY_DIR = ROOT / "build/g4irsf24_dlp_release/python"
DEFAULT_CASE_ROOT = ROOT / "outputs/runtime/g4irsf31_nanning_native"
DEFAULT_AGGREGATE = ROOT / "outputs/tables/g4irsf31_nanning_native.json"

Executor = Callable[..., Mapping[str, Any]]


class Native31Error(RuntimeError):
    """Raised when a G31 case cannot satisfy the registered protocol."""


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
    manifest_path: Path
    canonical_path: Path
    manifest: Mapping[str, Any]
    rows: tuple[dict[str, Any], ...]
    raw_bag_count: int
    segment_count: int


def _speed_label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def _primary_cases() -> tuple[CaseSpec, ...]:
    stable = [
        CaseSpec(
            case_id=f"t5_2_nanning_{scale}x_speed_{_speed_label(speed)}",
            group="stable_speed",
            scale=scale,
            speed_mps=speed,
        )
        for scale in (1, 2)
        for speed in SPEEDS_MPS
    ]
    faults = [
        CaseSpec(
            case_id=f"t5_5_nanning_{scale}x_fault_{scenario}",
            group="all_day_line_interruption",
            scale=scale,
            speed_mps=2.5,
            fault_scenario=scenario,
        )
        for scale in (1, 2)
        for scenario in (
            "single_1",
            "single_2",
            "single_3",
            "single_4",
            "single_5",
            "single_6",
            "single_7",
            "single_8",
            "pair_1_7",
            "pair_2_4",
            "pair_3_5",
            "pair_4_5",
            "pair_5_7",
            "triple_2_4_6",
            "triple_3_5_8",
            "triple_4_6_7",
        )
    ]
    return tuple((*stable, *faults))


PRIMARY_CASES = _primary_cases()
CASE_IDS = tuple(case.case_id for case in PRIMARY_CASES)
_CASE_BY_ID = {case.case_id: case for case in PRIMARY_CASES}


def case_by_id(case_id: str) -> CaseSpec:
    try:
        return _CASE_BY_ID[case_id]
    except KeyError as exc:
        raise Native31Error(f"unsupported G31 Nanning case: {case_id}") from exc


def observation_bias_contexts() -> list[dict[str, Any]]:
    """Return the twelve frozen, explicitly non-exact Table 5.4 contexts."""

    values: list[dict[str, Any]] = []
    for source in g27_bias.bias_cases():
        bias = source["observation_bias"]
        values.append(
            {
                "case_id": source["case_id"],
                "paper_table": "5.4",
                "group": "observation_bias_reconstruction_context",
                "execution_role": "CONTEXT_ONLY_NOT_PRIMARY_G31_CASE",
                "protocol_fidelity": "LEGACY_VARIANT_RECONSTRUCTION_NON_EXACT",
                "standard_speed_mps": float(source["standard_speed_mps"]),
                "physical_edge_speed_mps": float(source["physical_edge_speed_mps"]),
                "deviation_percent": int(source["deviation_percent"]),
                "observation_bias": {
                    "distribution": "uniform_0_to_k_seconds",
                    "maximum_seconds": float(bias["maximum_seconds"]),
                    "seed": int(bias["seed"]),
                    "level_mapping": "k_seconds=deviation_percent/10",
                },
                "exact_paper_reproduction_claimed": False,
                "adds_policy_or_learning": False,
            }
        )
    return values


def apply_observation_bias_context(
    request: Mapping[str, Any], context: Mapping[str, Any]
) -> dict[str, Any]:
    """Apply only the existing deterministic observation-delay ABI fields."""

    bias = context.get("observation_bias")
    if not isinstance(bias, Mapping):
        raise Native31Error("observation-bias context lacks its frozen rule")
    value = dict(request)
    value["legacy_observation_bias_max_seconds"] = float(
        bias["maximum_seconds"]
    )
    value["legacy_observation_bias_seed"] = int(bias["seed"])
    return value


def campaign_manifest() -> dict[str, Any]:
    return {
        "primary_cases": [case.as_dict() for case in PRIMARY_CASES],
        "primary_case_count": len(PRIMARY_CASES),
        "stable_speed_case_count": sum(
            case.group == "stable_speed" for case in PRIMARY_CASES
        ),
        "line_interruption_case_count": sum(
            case.group == "all_day_line_interruption" for case in PRIMARY_CASES
        ),
        "observation_bias_reconstruction_contexts": observation_bias_contexts(),
        "observation_bias_context_count": 12,
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Native31Error(f"JSON object required: {path}")
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


def _manifest_reference(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    rooted = ROOT / path
    return rooted if rooted.exists() else manifest_path.parent / path


def load_workload(scale: int, task_dir: Path = DEFAULT_TASK_DIR) -> Workload:
    if scale not in SCALE_COUNTS:
        raise Native31Error("scale must be 1 or 2")
    manifest_path = task_dir / f"nanning_{scale}x_manifest.json"
    manifest = _read_json(manifest_path)
    expected_raw, expected_segments = SCALE_COUNTS[scale]
    lifecycle = manifest.get("lifecycle")
    gates = {
        "schema": manifest.get("schema") == WORKLOAD_SCHEMA,
        "status": manifest.get("status") == "COMPLETE",
        "scale": manifest.get("scale") == scale,
        "map": manifest.get("map_id") == MAP_ID,
        "raw_count": manifest.get("raw_task_count") == expected_raw,
        "segment_count": manifest.get("expanded_segment_count")
        == expected_segments,
        "lifecycle": isinstance(lifecycle, Mapping)
        and lifecycle.get("storage_in_goal") == STORAGE_NODE
        and lifecycle.get("storage_out_start") == STORAGE_NODE,
    }
    if not all(gates.values()):
        raise Native31Error(f"Nanning {scale}x manifest gate failed: {gates}")
    canonical_path = _manifest_reference(
        str(manifest["canonical_output"]), manifest_path
    )
    rows: list[dict[str, Any]] = []
    required = {
        "segment_id",
        "task_id",
        "original_entry_time",
        "pass_time",
        "std",
        "start",
        "goal",
    }
    with canonical_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or not required.issubset(row):
                raise Native31Error(
                    f"canonical row {line_number} lacks a runtime field"
                )
            rows.append(row)
    segment_ids = [str(row["segment_id"]) for row in rows]
    raw_ids = {int(row["task_id"]) for row in rows}
    if len(rows) != expected_segments or len(raw_ids) != expected_raw:
        raise Native31Error("canonical workload counts do not match its manifest")
    if len(segment_ids) != len(set(segment_ids)):
        raise Native31Error("canonical segment IDs are not unique")
    return Workload(
        scale=scale,
        manifest_path=manifest_path,
        canonical_path=canonical_path,
        manifest=manifest,
        rows=tuple(rows),
        raw_bag_count=expected_raw,
        segment_count=expected_segments,
    )


def load_fault_scenario(
    scale: int,
    scenario: str,
    protocol_path: Path = DEFAULT_FAULT_PROTOCOL,
) -> dict[str, Any]:
    protocol = _read_json(protocol_path)
    if (
        protocol.get("schema") != FAULT_PROTOCOL_SCHEMA
        or protocol.get("map_id") != MAP_ID
    ):
        raise Native31Error("fault protocol does not describe the selected Nanning map")
    scales = protocol.get("scales")
    scale_row = scales.get(f"{scale}x") if isinstance(scales, Mapping) else None
    rows = scale_row.get("scenarios") if isinstance(scale_row, Mapping) else None
    if not isinstance(rows, list):
        raise Native31Error(f"fault protocol lacks the {scale}x scenario table")
    matches = [row for row in rows if row.get("scenario") == scenario]
    if len(matches) != 1:
        raise Native31Error(f"fault scenario is not registered once: {scenario}")
    return dict(matches[0])


def _service_aware_edge_cost_records(
    node_records: Sequence[Sequence[Any]],
    edge_records: Sequence[Sequence[Any]],
    *,
    minimum_service_seconds: float,
) -> tuple[tuple[int, int, float, float], ...]:
    """Encode service(source)+travel as unit-speed Bellman edge weights."""

    service = {
        int(row[0]): max(float(row[2]), minimum_service_seconds)
        for row in node_records
    }
    return tuple(
        (
            int(edge[0]),
            int(edge[1]),
            service[int(edge[0])] + float(edge[2]) / float(edge[3]),
            1.0,
        )
        for edge in edge_records
    )


def _prepare_fault_values(
    request: dict[str, Any],
    rows: Sequence[Mapping[str, Any]],
    scenario: Mapping[str, Any],
    potential_contract: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], dict[str, Any]]:
    fault_edges = tuple(
        (int(edge[0]), int(edge[1])) for edge in scenario["fault_edges"]
    )
    minimum_service = float(potential_contract["minimum_service_seconds"])
    weighted_edges = _service_aware_edge_cost_records(
        request["node_records"],
        request["edge_records"],
        minimum_service_seconds=minimum_service,
    )
    goals = sorted({int(row["goal"]) for row in rows})
    distances, relaxation = g27_fault.local_bellman_fixed_point(
        request["node_records"],
        weighted_edges,
        removed_edges=fault_edges,
        goals=goals,
    )
    reachable: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for source in rows:
        target = reachable if math.isfinite(
            distances[int(source["goal"])][int(source["start"])]
        ) else rejected
        target.append(dict(source))

    records = {str(record[0]): record for record in request["bag_records"]}
    request["bag_records"] = [records[str(row["segment_id"])] for row in reachable]
    artifact, artifact_contract = g27_fault.structural_td_artifact(
        request["node_records"],
        weighted_edges,
        request["heuristic_time"],
        distances,
    )
    request["g4irsf24_dlp_artifact"] = artifact
    request["fault_windows"] = [
        (
            start,
            end,
            FIXED_START_EPOCH,
            FAULT_REPAIR_EPOCH,
            0.0,
            False,
        )
        for start, end in fault_edges
    ]
    return tuple(reachable), tuple(rejected), {
        "activation": "FAULT_ONLY_SERVICE_AWARE_STRUCTURAL_VALUES",
        "learned_from_runtime_data": False,
        "fault_edges": [list(edge) for edge in fault_edges],
        "source_rejected_unreachable_segment_count": len(rejected),
        "runtime_reachable_segment_count": len(reachable),
        "relaxation": {
            **relaxation,
            "edge_cost": "max(node_service,minimum_service)+edge_travel_time",
            "potential_reference": potential_contract["mode"],
        },
        "artifact_contract": {
            **artifact_contract,
            "dynamic_distance_semantics": "service_aware_surviving_graph_cost",
            "residual_reference": potential_contract["mode"],
            "learned_from_runtime_data": False,
            "local_potential_descent_guard": dict(
                LOCAL_POTENTIAL_DESCENT_GUARD
            ),
        },
        "artifact": artifact,
    }


def prepare_native_request(
    case: CaseSpec,
    workload: Workload,
    *,
    map_profile_path: Path,
    fault_protocol_path: Path,
    binary: Path | None,
) -> tuple[
    dict[str, Any],
    tuple[dict[str, Any], ...],
    tuple[dict[str, Any], ...],
    dict[str, Any],
]:
    profile = map_adapter.load_map_profile(
        map_profile_path, storage_source_nodes=[STORAGE_NODE]
    )
    request, potential_contract = map_adapter.build_s4_request(
        profile,
        workload.rows,
        binary=binary,
        scenario=f"g4irsf31_{case.case_id}",
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
        local = {
            "activation": "FAULT_STRUCTURAL_VALUES_EXACT_OFF",
            "learned_from_runtime_data": False,
            "fault_edges": [],
            "source_rejected_unreachable_segment_count": 0,
            "runtime_reachable_segment_count": workload.segment_count,
            "artifact_contract": None,
            "artifact": None,
        }
    else:
        scenario = load_fault_scenario(
            case.scale, case.fault_scenario, fault_protocol_path
        )
        runtime_rows, rejected, local = _prepare_fault_values(
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


def _selection(case: CaseSpec, workload: Workload) -> dict[str, Any]:
    return {
        "mode": "full",
        "scale": case.scale,
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
            "hca_max_epochs": HCA_MAX_EPOCHS,
            "fixed_end_epoch": FIXED_END_EPOCH,
            "speed_mps": case.speed_mps,
            "fault_scenario": case.fault_scenario,
            "hca_release_dependency": False,
            "comparison_allowed_after_matching_hca_cell_exists": True,
        },
        "timing": {
            "comparison_allowed_in_s4_artifact": False,
            "requires_both_frameworks_complete_full_population": True,
            "pairing": "own_source_raw_entry_to_completion_not_release_trace_paired",
            "survivor_only_timing_allowed": False,
        },
    }


def _request_contract(
    request: Mapping[str, Any],
    runtime_rows: Sequence[Mapping[str, Any]],
    rejected: Sequence[Mapping[str, Any]],
    local: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "node_count": len(request["node_records"]),
        "directed_edge_count": len(request["edge_records"]),
        "runtime_requested_segment_count": len(runtime_rows),
        "source_rejected_unreachable_segment_count": len(rejected),
        "edge_speeds_mps": sorted({float(row[3]) for row in request["edge_records"]}),
        "storage_source_nodes": list(request["storage_source_nodes"]),
        "max_simulation_time": request["max_simulation_time"],
        "max_events": request["max_events"],
        "local_queue_capacity": request["local_queue_capacity"],
        "fault_windows": [list(row) for row in request["fault_windows"]],
        "policy": {
            "scorer_mode": request["scorer_mode"],
            "queue_discipline": request["queue_discipline"],
            "merge_grant_rule": request["merge_grant_rule"],
            "merge_grant_timing_mode": request["merge_grant_timing_mode"],
            "event_hotpath_policy": request["g4irsf20_event_hotpath_policy"],
            "decision_scope": "one_next_edge_at_current_junction",
            "learning_active": False,
            "local_potential_descent_guard": dict(
                LOCAL_POTENTIAL_DESCENT_GUARD
            ),
            "local_software_queue_cap": dict(LOCAL_SOFTWARE_QUEUE_CAP),
            "direct_neighbor_merge_calendar_visibility": dict(
                DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
            ),
            "goal_arrival_completion": dict(GOAL_ARRIVAL_COMPLETION),
        },
        "local_values": {
            key: value
            for key, value in local.items()
            if key != "artifact"
        },
    }


def _number(summary: Mapping[str, Any], name: str) -> float | None:
    value = summary.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _runtime_admission(
    case: CaseSpec,
    workload: Workload,
    request: Mapping[str, Any],
    runtime_rows: Sequence[Mapping[str, Any]],
    rejected: Sequence[Mapping[str, Any]],
    local: Mapping[str, Any],
    summary: Mapping[str, Any],
    bags: Sequence[Mapping[str, Any]],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    expected_ids = sorted(str(row["segment_id"]) for row in runtime_rows)
    returned_ids = sorted(str(row.get("segment_id", "")) for row in bags)
    completed = _number(summary, "completed_count")
    failed = _number(summary, "failed_count")
    event_count = _number(summary, "event_count")
    declared_time = _number(summary, "declared_max_simulation_time")
    declared_events = _number(summary, "declared_max_events")
    fault_count = len(local["fault_edges"])
    echo = g26._runtime_echo_gates(summary)
    dlp = g27_fault._dlp_evidence(summary, local.get("artifact"))
    guard_echo = {
        "request_enabled": request.get(
            "enable_s4_local_potential_descent_guard"
        )
        is True,
        "summary_enabled": summary.get(
            "s4_local_potential_descent_guard_enabled"
        )
        is True,
        "summary_nonlearning": summary.get(
            "s4_local_potential_descent_guard_learning_active"
        )
        is False,
        "summary_one_hop_strict_descent": summary.get(
            "s4_local_potential_descent_guard_claim_boundary"
        )
        == (
            "one_next_edge_at_current_junction;strict_H_eff_descent;"
            "O_outdegree;no_full_route;no_learning"
        ),
        "protocol_nonlearning": local.get(
            "local_potential_descent_guard"
        )
        == LOCAL_POTENTIAL_DESCENT_GUARD,
        "fault_values_deterministic": (
            local.get("artifact") is None
            or local["artifact"].get(
                "deterministic_surviving_graph_values"
            )
            is True
        ),
    }
    queue_cap_echo = {
        "request_zero": request.get("local_queue_capacity")
        == map_adapter.G31_LOCAL_QUEUE_CAPACITY,
        "summary_zero": _number(summary, "local_queue_capacity")
        == float(map_adapter.G31_LOCAL_QUEUE_CAPACITY),
    }
    merge_calendar_echo = {
        "request_enabled": request.get(
            "enable_s4_direct_neighbor_merge_calendar_visibility"
        )
        is True,
        "summary_enabled": summary.get(
            "s4_direct_neighbor_merge_calendar_visibility_enabled"
        )
        is True,
        "summary_nonlearning": summary.get(
            "s4_direct_neighbor_merge_calendar_visibility_learning_active"
        )
        is False,
        "summary_direct_neighbor_existing_weight_j2": summary.get(
            "s4_direct_neighbor_merge_calendar_visibility_claim_boundary"
        )
        == (
            "direct_outgoing_neighbor_calendar_scalar;"
            "existing_calendar_wait_weight;J2_authority_unchanged;"
            "O_outdegree;no_full_route;no_learning"
        ),
        "protocol_exact": local.get(
            "direct_neighbor_merge_calendar_visibility"
        )
        == DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY,
    }
    goal_arrival_echo = {
        "request_enabled": request.get("complete_on_goal_arrival") is True,
        "summary_enabled": summary.get(
            "complete_on_goal_arrival_enabled"
        )
        is True,
        "summary_legacy_completion_seam": summary.get(
            "complete_on_goal_arrival_claim_boundary"
        )
        == GOAL_ARRIVAL_COMPLETION_CLAIM,
        "protocol_exact": local.get("goal_arrival_completion")
        == GOAL_ARRIVAL_COMPLETION,
    }

    topology = None
    topology_gates: dict[str, bool] = {}
    if fault_count:
        topology = g26.topology_reachable_raw_bag_upper_bound(
            workload.rows, request["edge_records"], local["fault_edges"]
        )
        registered_upper = int(
            local["protocol_scenario"]["topology_upper_raw_bags"]
        )
        all_reachable_complete = completed == float(len(runtime_rows))
        topology_gates = {
            "reachable_segments_match_local_fixed_point": (
                int(topology["reachable_segment_count"]) == len(runtime_rows)
            ),
            "registered_raw_bag_upper_matches_graph": (
                int(topology["topology_reachable_raw_bag_upper_bound"])
                == registered_upper
            ),
            "completed_raw_bags_do_not_exceed_upper": (
                int(outcome["completed_raw_bag_count"]) <= registered_upper
            ),
            "all_reachable_complete_saturates_upper": (
                int(outcome["completed_raw_bag_count"]) == registered_upper
                if all_reachable_complete
                else True
            ),
        }

    gates = {
        "full_registered_population": (
            workload.raw_bag_count == SCALE_COUNTS[case.scale][0]
            and workload.segment_count == SCALE_COUNTS[case.scale][1]
        ),
        "selected_partition": len(runtime_rows) + len(rejected)
        == workload.segment_count,
        "runtime_terminal_partition": completed is not None
        and failed is not None
        and completed + failed == float(len(runtime_rows)),
        "runtime_returned_exact_segment_ids": returned_ids == expected_ids,
        "fixed_horizon_request": request["max_simulation_time"]
        == FIXED_END_EPOCH,
        "fixed_horizon_echo": declared_time == FIXED_END_EPOCH,
        "event_budget_request": request["max_events"] == MAX_EVENTS,
        "event_budget_echo": declared_events == float(MAX_EVENTS),
        "event_count_within_budget": event_count is not None
        and event_count <= MAX_EVENTS,
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "time_limit_is_reported": isinstance(summary.get("time_limit_reached"), bool),
        "fault_event_count": _number(summary, "fault_event_count")
        == float(fault_count),
        "repair_event_count": _number(summary, "repair_event_count") == 0.0,
        "reservation_conflicts_zero": _number(summary, "reservation_conflicts")
        == 0.0,
        "fault_edge_entry_violations_zero": _number(
            summary, "physical_fault_edge_entry_violation_count"
        )
        == 0.0,
        "runtime_full_astar_zero": _number(summary, "runtime_full_astar_calls")
        == 0.0,
        "runtime_full_cie_astar_zero": _number(
            summary, "runtime_full_cie_astar_calls"
        )
        == 0.0,
        "global_reservation_scan_zero": _number(
            summary, "global_reservation_scan_count"
        )
        == 0.0,
        "s4_j2_e2_echo": all(echo.values()),
        "fault_value_echo": dlp["pass"],
        "local_potential_descent_guard": all(guard_echo.values()),
        "local_software_queue_cap": all(queue_cap_echo.values()),
        "direct_neighbor_merge_calendar_visibility": all(
            merge_calendar_echo.values()
        ),
        "goal_arrival_completion": all(goal_arrival_echo.values()),
        "topology_bound": all(topology_gates.values()),
    }
    return {
        "pass": all(gates.values()),
        "mode": "FULL_POPULATION_FIXED_HORIZON_CAPACITY",
        "gates": gates,
        "runtime_echo_gates": echo,
        "fault_value_echo": dlp,
        "local_potential_descent_guard": {
            "pass": all(guard_echo.values()),
            "enabled": True,
            "learning_active": False,
            "decision_scope": "one_next_edge_at_current_junction",
            "rule": LOCAL_POTENTIAL_DESCENT_GUARD["rule"],
            "gates": guard_echo,
        },
        "local_software_queue_cap": {
            "pass": all(queue_cap_echo.values()),
            **LOCAL_SOFTWARE_QUEUE_CAP,
            "summary_local_queue_capacity": _number(
                summary, "local_queue_capacity"
            ),
            "gates": queue_cap_echo,
        },
        "direct_neighbor_merge_calendar_visibility": {
            "pass": all(merge_calendar_echo.values()),
            **DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY,
            "gates": merge_calendar_echo,
        },
        "goal_arrival_completion": {
            "pass": all(goal_arrival_echo.values()),
            **GOAL_ARRIVAL_COMPLETION,
            "claim_boundary": GOAL_ARRIVAL_COMPLETION_CLAIM,
            "gates": goal_arrival_echo,
        },
        "topology": topology,
        "topology_gates": topology_gates,
        "operational_outcome_not_structural_veto": {
            "completed_segment_count": int(completed or 0),
            "failed_segment_count": int(failed or 0),
            "unresolved_deadlock_count": int(
                _number(summary, "unresolved_deadlock_count") or 0
            ),
            "time_limit_reached": summary.get("time_limit_reached"),
        },
    }


def _timing_evidence(
    workload: Workload,
    bags: Sequence[Mapping[str, Any]],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    if int(outcome["completed_raw_bag_count"]) != workload.raw_bag_count:
        return {
            "status": "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
            "full_outcome_timing_comparison_allowed": False,
            "survivor_only_timing_allowed": False,
        }
    distributions, raw = g24.timing_distributions(workload.rows, bags)
    return {
        "status": "S4_FULL_POPULATION_DESCRIPTIVE",
        "population": "all_selected_raw_bags_complete",
        "raw_bag_count": len(raw),
        "display_aliases": {"java_release": "scheduled_segment_arrival"},
        "distributions": distributions,
        "full_outcome_timing_comparison_allowed": False,
        "comparison_requires_matching_full_population_hca_timing": True,
    }


def execute_case(
    case_id: str,
    *,
    task_dir: Path = DEFAULT_TASK_DIR,
    map_profile_path: Path = DEFAULT_MAP_PROFILE,
    fault_protocol_path: Path = DEFAULT_FAULT_PROTOCOL,
    binary: Path | None,
    dry_run: bool = False,
    executor: Executor | None = None,
) -> dict[str, Any]:
    case = case_by_id(case_id)
    workload = load_workload(case.scale, task_dir)
    request, runtime_rows, rejected, local = prepare_native_request(
        case,
        workload,
        map_profile_path=map_profile_path,
        fault_protocol_path=fault_protocol_path,
        binary=binary,
    )
    common = {
        "schema": SCHEMA,
        "case_id": case.case_id,
        "case": case.as_dict(),
        "map_id": MAP_ID,
        "workload_protocol": workload.manifest["protocol"],
        "selection": _selection(case, workload),
        "comparison_contract": _comparison_contract(case, workload),
        "request_contract": _request_contract(
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
        raise Native31Error("binary is required unless --dry-run is used")

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise Native31Error("native executor did not return summary and bag rows")
    if any(not isinstance(row, Mapping) for row in bags):
        raise Native31Error("native bag result contains a non-object row")

    combined = [dict(row) for row in bags] + g27_fault._synthetic_source_rejections(
        rejected
    )
    outcome = g26.summarize_paper_outcome(
        workload.rows, combined, total_raw_bags=workload.raw_bag_count
    )
    admission = _runtime_admission(
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
        "status": COMPLETE if admission["pass"] else FAILED,
        "native_execution_started": True,
        "outcome": {
            "requested_segment_count": workload.segment_count,
            "runtime_requested_reachable_segment_count": len(runtime_rows),
            "source_rejected_unreachable_segment_count": len(rejected),
            **outcome,
        },
        "timing": _timing_evidence(workload, combined, outcome),
        "safety": admission,
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "event_count": int(_number(summary, "event_count") or 0),
            "decision_count": int(_number(summary, "decision_count") or 0),
            "declared_max_events": summary.get("declared_max_events"),
            "declared_max_simulation_time": summary.get(
                "declared_max_simulation_time"
            ),
            "event_limit_reached": summary.get("event_limit_reached"),
            "time_limit_reached": summary.get("time_limit_reached"),
        },
    }


def _artifact_admitted(value: Mapping[str, Any]) -> bool:
    case_id = value.get("case_id")
    if case_id not in _CASE_BY_ID:
        return False
    case = _CASE_BY_ID[str(case_id)]
    expected_raw, expected_segments = SCALE_COUNTS[case.scale]
    selection = value.get("selection")
    safety = value.get("safety")
    request = value.get("request_contract")
    return (
        value.get("schema") == SCHEMA
        and value.get("status") == COMPLETE
        and isinstance(selection, Mapping)
        and selection.get("mode") == "full"
        and selection.get("selected_raw_bag_count") == expected_raw
        and selection.get("selected_segment_count") == expected_segments
        and isinstance(safety, Mapping)
        and safety.get("pass") is True
        and isinstance(request, Mapping)
        and request.get("max_simulation_time") == FIXED_END_EPOCH
        and request.get("max_events") == MAX_EVENTS
        and request.get("local_queue_capacity")
        == map_adapter.G31_LOCAL_QUEUE_CAPACITY
        and isinstance(request.get("policy"), Mapping)
        and request["policy"].get("local_potential_descent_guard")
        == LOCAL_POTENTIAL_DESCENT_GUARD
        and request["policy"].get("local_software_queue_cap")
        == LOCAL_SOFTWARE_QUEUE_CAP
        and request["policy"].get(
            "direct_neighbor_merge_calendar_visibility"
        )
        == DIRECT_NEIGHBOR_MERGE_CALENDAR_VISIBILITY
        and request["policy"].get("goal_arrival_completion")
        == GOAL_ARRIVAL_COMPLETION
    )


def aggregate_results(case_root: Path) -> dict[str, Any]:
    by_id: dict[str, dict[str, Any]] = {}
    if case_root.exists():
        for path in sorted(case_root.glob("*.json")):
            value = _read_json(path)
            if value.get("schema") == SCHEMA and value.get("case_id") in _CASE_BY_ID:
                by_id[str(value["case_id"])] = value
    complete = sorted(
        case_id for case_id, value in by_id.items() if _artifact_admitted(value)
    )
    ready = sorted(
        case_id
        for case_id, value in by_id.items()
        if value.get("status") == DRY_RUN_READY
    )
    failed = sorted(
        case_id for case_id, value in by_id.items() if value.get("status") == FAILED
    )
    stale = sorted(
        case_id
        for case_id, value in by_id.items()
        if value.get("status") == COMPLETE and not _artifact_admitted(value)
    )
    missing = sorted(set(CASE_IDS) - by_id.keys())
    manifest = campaign_manifest()
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": "COMPLETE" if len(complete) == len(CASE_IDS) else "PARTIAL",
        "map_id": MAP_ID,
        "fixed_window": {
            "start_epoch": FIXED_START_EPOCH,
            "hca_max_epochs": HCA_MAX_EPOCHS,
            "end_epoch": FIXED_END_EPOCH,
            "max_events": MAX_EVENTS,
        },
        "expected_primary_case_count": len(CASE_IDS),
        "observed_case_count": len(by_id),
        "complete_case_ids": complete,
        "dry_run_ready_case_ids": ready,
        "failed_case_ids": failed,
        "stale_case_ids": stale,
        "missing_case_ids": missing,
        "campaign_manifest": manifest,
        "comparison_scope": {
            "capacity": "same canonical schedule, own source, fixed denominator/window",
            "timing": "no verdict until both S4 and HCA complete the full population",
            "survivor_only_comparison_allowed": False,
        },
        "cases": [by_id[case_id] for case_id in sorted(by_id)],
    }


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _resolve_binary(path: Path | None) -> Path | None:
    if path is not None:
        return _rooted(path).resolve(strict=True)
    candidates = sorted(DEFAULT_BINARY_DIR.glob("czr005_cpp*.pyd"))
    return candidates[-1].resolve() if candidates else None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    case = commands.add_parser("case", help="run or dry-run one G31 case")
    case.add_argument("--case-id", required=True, choices=CASE_IDS)
    case.add_argument("--task-dir", type=Path, default=DEFAULT_TASK_DIR)
    case.add_argument("--map-profile", type=Path, default=DEFAULT_MAP_PROFILE)
    case.add_argument("--fault-protocol", type=Path, default=DEFAULT_FAULT_PROTOCOL)
    case.add_argument("--binary", type=Path)
    case.add_argument("--output", type=Path, required=True)
    case.add_argument("--dry-run", action="store_true")
    case.add_argument("--force", action="store_true")

    resume = commands.add_parser("resume", help="resume selected G31 primary cases")
    resume.add_argument("--case-id", action="append", choices=CASE_IDS)
    resume.add_argument("--task-dir", type=Path, default=DEFAULT_TASK_DIR)
    resume.add_argument("--map-profile", type=Path, default=DEFAULT_MAP_PROFILE)
    resume.add_argument("--fault-protocol", type=Path, default=DEFAULT_FAULT_PROTOCOL)
    resume.add_argument("--binary", type=Path)
    resume.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    resume.add_argument("--dry-run", action="store_true")
    resume.add_argument("--force", action="store_true")

    aggregate = commands.add_parser("aggregate", help="aggregate G31 case JSON")
    aggregate.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    aggregate.add_argument("--output", type=Path, default=DEFAULT_AGGREGATE)
    return parser


def _run_one(args: argparse.Namespace, case_id: str, output: Path) -> int:
    if output.is_file() and not args.force:
        existing = _read_json(output)
        if existing.get("schema") != SCHEMA or existing.get("case_id") != case_id:
            raise Native31Error(f"existing artifact does not match {case_id}")
        if _artifact_admitted(existing) or (
            args.dry_run and existing.get("status") == DRY_RUN_READY
        ):
            print(json.dumps({"status": "SKIPPED_EXISTING", "case_id": case_id}))
            return 0
    binary = _resolve_binary(args.binary)
    if not args.dry_run and binary is None:
        raise Native31Error("no native binary found; pass --binary")
    payload = execute_case(
        case_id,
        task_dir=_rooted(args.task_dir),
        map_profile_path=_rooted(args.map_profile),
        fault_protocol_path=_rooted(args.fault_protocol),
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
    except (Native31Error, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"G31 Nanning native failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
