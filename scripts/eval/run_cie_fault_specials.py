#!/usr/bin/env python3
"""Run the frozen 1x CIE fault-special comparisons.

This is a deliberately thin Python orchestration layer over the existing G31
request and native executor.  It adds no scorer or C++ mode.  The registered
matrix contains only four fixed, all-day faults on the complete original 1x
population:

* strict: the surviving-graph service-aware fault treatment with strict local
  descent ON versus OFF; the boolean guard is the sole request delta;
* potential: both arms use the same surviving-graph source-unreachable
  recognition and native admission cohort; the only request delta is the
  existing surviving-graph service-aware DLP artifact.

Potential cells with source-unreachable bags retain the same original raw-bag
denominator, canonical release schedule, and native admission cohort; rejected
segments are added back as synthetic terminal failures for fixed-denominator
business subjects. Timing is
reported only when the entire 1x raw-bag population completes; survivor or
common-cohort timing is never emitted.
"""

from __future__ import annotations

import argparse
import csv
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Callable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend  # noqa: E402
from scripts.eval import cie_fixed_denominator_business as cie_business  # noqa: E402
from scripts.eval import g4irsf31_map_adapter as map_adapter  # noqa: E402
from scripts.eval import run_g4irsf24_native_race as g24  # noqa: E402
from scripts.eval import run_g4irsf26_paper_experiments as g26  # noqa: E402
from scripts.eval import run_g4irsf27_fault_values as g27_fault  # noqa: E402
from scripts.eval import run_g4irsf31_map2_native as map2_native  # noqa: E402
from scripts.eval import run_g4irsf31_nanning_native as nanning_native  # noqa: E402


SCHEMA = "czr005.cie_fault_special.run.v1"
AGGREGATE_SCHEMA = "czr005.cie_fault_special.aggregate.v1"
REGISTERED_SCALE = 1
REGISTERED_RAW_BAG_COUNT = 28_506
REGISTERED_SEGMENT_COUNT = 43_603
SPEED_MPS = 2.5
FIXED_END_EPOCH = nanning_native.FIXED_END_EPOCH
MAX_EVENTS = nanning_native.MAX_EVENTS

REGISTERED_SCENARIOS: dict[str, tuple[str, ...]] = {
    "map2": ("single_4", "pair_2_4"),
    "nanning": ("single_3", "pair_3_5"),
}
STUDY_ARMS: dict[str, tuple[str, str]] = {
    "strict": (
        "FULL_WITHOUT_STRICT_DESCENT",
        "FULL_WITH_STRICT_DESCENT",
    ),
    "potential": (
        "EDGE_FILTER_ONLY",
        "SURVIVING_GRAPH_SERVICE_AWARE_POTENTIAL",
    ),
}
REFERENCE_ARM = {study: arms[0] for study, arms in STUDY_ARMS.items()}
TREATMENT_ARM = {study: arms[1] for study, arms in STUDY_ARMS.items()}

DEFAULT_CASE_ROOT = ROOT / "outputs/runtime/cie_fault_specials"
DEFAULT_AGGREGATE = ROOT / "outputs/tables/cie_fault_specials.json"
DEFAULT_TABLE = ROOT / "outputs/tables/cie_fault_specials.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/cie_fault_specials.md"
DEFAULT_NANNING_TASK_DIR = (
    ROOT / "build_cie_revision/workloads/g4irsf31_nanning"
)

Executor = Callable[..., Mapping[str, Any]]


class FaultSpecialError(RuntimeError):
    """Raised when the frozen fault-special protocol is violated."""


@dataclass(frozen=True)
class FaultContext:
    rows: tuple[dict[str, Any], ...]
    raw_bag_count: int
    segment_count: int
    workload_source: Path
    scenario_record: Mapping[str, Any]
    base_request: Mapping[str, Any]
    graph_request: Mapping[str, Any]
    graph_runtime_rows: tuple[dict[str, Any], ...]
    graph_rejected_rows: tuple[dict[str, Any], ...]
    graph_local: Mapping[str, Any]


@dataclass(frozen=True)
class PreparedRun:
    rows: tuple[dict[str, Any], ...]
    request: dict[str, Any]
    runtime_rows: tuple[dict[str, Any], ...]
    rejected_rows: tuple[dict[str, Any], ...]
    local: Mapping[str, Any]
    contract: Mapping[str, Any]
    workload_source: Path


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    ).encode("utf-8")


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_value(*args: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNAVAILABLE"


def _changed_top_level_fields(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> list[str]:
    return sorted(
        key
        for key in set(before) | set(after)
        if _canonical_json(before.get(key)) != _canonical_json(after.get(key))
    )


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _json_safe(value: Any) -> Any:
    """Keep JSON standards-compliant while preserving infinite-drain meaning."""

    if isinstance(value, float) and not math.isfinite(value):
        if math.isinf(value):
            return "INFINITE" if value > 0 else "NEGATIVE_INFINITE"
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(
            _json_safe(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(TABLE_FIELDS)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field) for field in fields})
    os.replace(temporary, path)


def _validate_cell(map_name: str, scenario: str, study: str, arm: str) -> None:
    if map_name not in REGISTERED_SCENARIOS:
        raise FaultSpecialError(f"unsupported map: {map_name}")
    if scenario not in REGISTERED_SCENARIOS[map_name]:
        raise FaultSpecialError(
            f"unregistered 1x fault for {map_name}: {scenario}"
        )
    if study not in STUDY_ARMS:
        raise FaultSpecialError(f"unsupported study: {study}")
    if arm not in STUDY_ARMS[study]:
        raise FaultSpecialError(f"arm {arm} does not belong to study {study}")


def _validate_population(*, raw_bag_count: int, segment_count: int) -> None:
    actual = (int(raw_bag_count), int(segment_count))
    expected = (REGISTERED_RAW_BAG_COUNT, REGISTERED_SEGMENT_COUNT)
    if actual != expected:
        raise FaultSpecialError(
            "fault specials require the complete original 1x population: "
            f"expected raw/segments={expected}, got {actual}"
        )


def _case_id(map_name: str, scenario: str) -> str:
    return f"t5_5_{map_name}_1x_fault_{scenario}"


def _load_fault_context(
    *,
    map_name: str,
    scenario: str,
    binary: Path | None,
    map2_workload_path: Path = map2_native.DEFAULT_WORKLOAD_1X,
    nanning_task_dir: Path = DEFAULT_NANNING_TASK_DIR,
    nanning_profile_path: Path = nanning_native.DEFAULT_MAP_PROFILE,
    nanning_fault_protocol_path: Path = nanning_native.DEFAULT_FAULT_PROTOCOL,
) -> FaultContext:
    """Build the common G31 request and the existing full fault treatment."""

    if map_name == "map2":
        case = map2_native.case_by_id(_case_id(map_name, scenario))
        workload = map2_native.load_workload(
            REGISTERED_SCALE,
            map2_workload_path,
            map2_native.DEFAULT_WORKLOAD_2X,
        )
        profile = map2_native.map2_profile()
        workload_source = workload.source_path
    else:
        case = nanning_native.case_by_id(_case_id(map_name, scenario))
        workload = nanning_native.load_workload(
            REGISTERED_SCALE, nanning_task_dir
        )
        profile = map_adapter.load_map_profile(
            nanning_profile_path.resolve(strict=True),
            storage_source_nodes=[nanning_native.STORAGE_NODE],
        )
        workload_source = workload.canonical_path

    _validate_population(
        raw_bag_count=workload.raw_bag_count,
        segment_count=workload.segment_count,
    )
    base_request, potential_contract = map_adapter.build_s4_request(
        profile,
        workload.rows,
        binary=binary,
        # Deliberately arm/study independent so it cannot become a second
        # factor inside either registered pair.
        scenario=f"cie_fault_special_{map_name}_{scenario}_1x",
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
    base_request["enable_cie_component_activation"] = True

    if map_name == "map2":
        scenario_record = map2_native._registered_fault_scenario(
            case, workload, base_request
        )
    else:
        scenario_record = nanning_native.load_fault_scenario(
            REGISTERED_SCALE,
            scenario,
            nanning_fault_protocol_path,
        )

    graph_request = deepcopy(base_request)
    graph_runtime, graph_rejected, graph_local = (
        nanning_native._prepare_fault_values(
            graph_request,
            workload.rows,
            scenario_record,
            potential_contract,
        )
    )
    graph_local["protocol_scenario"] = dict(scenario_record)
    graph_local["service_aware_potential"] = dict(potential_contract)

    # Edge-filter-only uses the same H_SA base and exactly the same physical
    # fault windows, but has neither DLP nor oracle source rejection.
    base_request["fault_windows"] = deepcopy(graph_request["fault_windows"])
    return FaultContext(
        rows=tuple(dict(row) for row in workload.rows),
        raw_bag_count=int(workload.raw_bag_count),
        segment_count=int(workload.segment_count),
        workload_source=workload_source,
        scenario_record=dict(scenario_record),
        base_request=base_request,
        graph_request=graph_request,
        graph_runtime_rows=graph_runtime,
        graph_rejected_rows=graph_rejected,
        graph_local=graph_local,
    )


def _request_identity_gates(request: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "g31_s4_scorer": request.get("scorer_mode")
        == "S4_queue_aware_rule_only",
        "full_s4_component_mask": int(
            request.get("s4_score_component_mask", 15)
        )
        == 15,
        "j2_m3": request.get("merge_grant_rule") == "M3",
        "j2_jit_fair_aging_deadline": request.get("merge_grant_timing_mode")
        == "jit_fair_aging_deadline",
        "e2": request.get("g4irsf20_event_hotpath_policy") == "E2",
        "direct_neighbor_calendar": request.get(
            "enable_s4_direct_neighbor_merge_calendar_visibility"
        )
        is True,
        "goal_arrival_completion": request.get("complete_on_goal_arrival")
        is True,
        "activation_telemetry": request.get("enable_cie_component_activation")
        is True,
        "fixed_horizon": request.get("max_simulation_time")
        == FIXED_END_EPOCH,
        "fixed_event_budget": request.get("max_events") == MAX_EVENTS,
        "no_full_route_mode_added": request.get("g4irsf16_supervisor_mode")
        == "off",
    }


def prepare_special_request(
    *,
    map_name: str,
    scenario: str,
    study: str,
    arm: str,
    binary: Path | None,
    map2_workload_path: Path = map2_native.DEFAULT_WORKLOAD_1X,
    nanning_task_dir: Path = DEFAULT_NANNING_TASK_DIR,
    nanning_profile_path: Path = nanning_native.DEFAULT_MAP_PROFILE,
    nanning_fault_protocol_path: Path = nanning_native.DEFAULT_FAULT_PROTOCOL,
) -> PreparedRun:
    """Prepare one frozen arm and prove its within-study request delta."""

    _validate_cell(map_name, scenario, study, arm)
    context = _load_fault_context(
        map_name=map_name,
        scenario=scenario,
        binary=binary,
        map2_workload_path=map2_workload_path,
        nanning_task_dir=nanning_task_dir,
        nanning_profile_path=nanning_profile_path,
        nanning_fault_protocol_path=nanning_fault_protocol_path,
    )

    if study == "strict":
        reference = deepcopy(context.graph_request)
        reference["enable_s4_local_potential_descent_guard"] = False
        request = deepcopy(context.graph_request)
        request["enable_s4_local_potential_descent_guard"] = (
            arm == "FULL_WITH_STRICT_DESCENT"
        )
        runtime_rows = context.graph_runtime_rows
        rejected_rows = context.graph_rejected_rows
        local = context.graph_local
        expected_delta = (
            []
            if arm == "FULL_WITHOUT_STRICT_DESCENT"
            else ["enable_s4_local_potential_descent_guard"]
        )
        cohort_identical = True
        boundary = "IDENTICAL_NATIVE_ADMISSION_COHORT_WITHIN_STRICT_PAIR"
        pure_potential_effect = None
        bundled_recognition = False
    else:
        reference = deepcopy(context.graph_request)
        reference.pop("g4irsf24_dlp_artifact", None)
        request = deepcopy(reference)
        if arm == "SURVIVING_GRAPH_SERVICE_AWARE_POTENTIAL":
            request["g4irsf24_dlp_artifact"] = deepcopy(
                context.graph_request["g4irsf24_dlp_artifact"]
            )
        runtime_rows = context.graph_runtime_rows
        rejected_rows = context.graph_rejected_rows
        if arm == "EDGE_FILTER_ONLY":
            local = {
                "activation": (
                    "EDGE_FILTER_ONLY_STATIC_H_SA_WITH_SHARED_"
                    "SOURCE_UNREACHABLE_RECOGNITION"
                ),
                "artifact": None,
                "fault_edges": [
                    list(edge) for edge in context.scenario_record["fault_edges"]
                ],
                "source_rejected_unreachable_segment_count": len(
                    context.graph_rejected_rows
                ),
                "runtime_reachable_segment_count": len(
                    context.graph_runtime_rows
                ),
                "protocol_scenario": dict(context.scenario_record),
            }
            expected_delta = []
        else:
            local = context.graph_local
            expected_delta = ["g4irsf24_dlp_artifact"]
        cohort_identical = True
        boundary = "IDENTICAL_NATIVE_ADMISSION_COHORT_PURE_POTENTIAL_COMPARISON"
        pure_potential_effect = True
        bundled_recognition = False

    changed_fields = _changed_top_level_fields(reference, request)
    identity_gates = _request_identity_gates(request)
    identity_gates["registered_factor_delta_exact"] = (
        changed_fields == expected_delta
    )
    identity_gates["fixed_complete_1x_population"] = (
        context.raw_bag_count == REGISTERED_RAW_BAG_COUNT
        and context.segment_count == REGISTERED_SEGMENT_COUNT
    )
    if not all(identity_gates.values()):
        raise FaultSpecialError(
            f"fault-special request identity failed: {identity_gates}; "
            f"changed={changed_fields}, expected={expected_delta}"
        )

    rejected_segment_count = len(context.graph_rejected_rows)
    rejected_raw_bag_count = len(
        {int(row["task_id"]) for row in context.graph_rejected_rows}
    )
    contract = {
        "map": map_name,
        "scenario": scenario,
        "study": study,
        "arm": arm,
        "scale": REGISTERED_SCALE,
        "raw_bag_denominator": context.raw_bag_count,
        "complete_segment_count": context.segment_count,
        "canonical_release_schedule_sha256": _json_sha256(
            [
                (
                    str(row["segment_id"]),
                    int(row["task_id"]),
                    float(row["pass_time"]),
                    float(row["std"]),
                )
                for row in context.rows
            ]
        ),
        "reference_arm": REFERENCE_ARM[study],
        "changed_request_fields_from_reference": changed_fields,
        "expected_changed_request_fields": expected_delta,
        "sole_registered_factor": (
            "enable_s4_local_potential_descent_guard"
            if study == "strict"
            else (
                "g4irsf24_dlp_artifact_only_with_shared_source_unreachable_"
                "recognition"
            )
        ),
        "reference_request_sha256": _json_sha256(reference),
        "selected_request_sha256": _json_sha256(request),
        "identity_gates": identity_gates,
        "identity_pass": all(identity_gates.values()),
        "fault_edges": [
            list(edge) for edge in context.scenario_record["fault_edges"]
        ],
        "fault_windows_identical_within_pair": True,
        "complete_raw_bag_denominator_identical_within_pair": True,
        "canonical_release_schedule_identical_within_pair": True,
        "native_admission_cohort_identical_within_pair": cohort_identical,
        "admission_cohort_boundary": boundary,
        "graph_treatment_runtime_segment_count": len(
            context.graph_runtime_rows
        ),
        "graph_treatment_source_rejected_segment_count": rejected_segment_count,
        "graph_treatment_raw_bags_with_source_rejected_segment_count": (
            rejected_raw_bag_count
        ),
        "registered_topology_blocked_raw_bag_count": int(
            context.scenario_record.get("topology_blocked_raw_bags", 0)
        ),
        "registered_topology_upper_raw_bag_count": int(
            context.scenario_record.get("topology_upper_raw_bags", 0)
        ),
        "pure_potential_effect_identified": pure_potential_effect,
        "source_unreachable_recognition_bundled_with_graph_treatment": (
            bundled_recognition
        ),
        "route_effect_reporting_scope": (
            "NATIVE_COHORT_DIAGNOSTIC_ONLY_NOT_A_PAIRED_ROUTE_EFFECT"
            if bundled_recognition
            else "SAME_NATIVE_COHORT"
        ),
        "fixed_denominator_outcome_scope": "ALL_ORIGINAL_RAW_BAGS",
        "survivor_or_common_cohort_timing_allowed": False,
        "two_x_timing_policy_if_extended": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
    }
    return PreparedRun(
        rows=context.rows,
        request=request,
        runtime_rows=runtime_rows,
        rejected_rows=rejected_rows,
        local=local,
        contract=contract,
        workload_source=context.workload_source,
    )


def _synthetic_source_rejections(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Represent pre-admission rejections on the protected segment identity."""

    return [
        {
            "segment_id": str(row["segment_id"]),
            "task_id": int(row["task_id"]),
            "completed": False,
            "complete": False,
            "release_time": float(row["pass_time"]),
            "arrival_time": float(row["pass_time"]),
            "admitted_time": -1.0,
            "finish_time": -1.0,
            "decision_count": 0,
            "loop_count": 0,
            "failure_reason": (
                "source_local_goal_unreachable_after_fixed_edge_fault"
            ),
        }
        for row in rows
    ]


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _execution_integrity(
    *,
    prepared: PreparedRun,
    summary: Mapping[str, Any],
    bags: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    expected_ids = sorted(str(row["segment_id"]) for row in prepared.runtime_rows)
    returned_ids = sorted(str(row.get("segment_id", "")) for row in bags)
    completed = _number(summary.get("completed_count"))
    failed = _number(summary.get("failed_count"))
    returned_completed = sum(
        bool(row.get("completed", row.get("complete", False))) for row in bags
    )
    returned_failed = len(bags) - returned_completed
    event_count = _number(summary.get("event_count"))
    goals = {
        str(row["segment_id"]): int(row["goal"])
        for row in prepared.runtime_rows
    }
    completed_at_correct_goal = all(
        not bool(row.get("completed", row.get("complete", False)))
        or (
            str(row.get("segment_id", "")) in goals
            and int(row.get("final_node", -1))
            == goals[str(row.get("segment_id", ""))]
        )
        for row in bags
    )
    fault_count = len(prepared.contract["fault_edges"])
    strict_enabled = bool(
        prepared.request["enable_s4_local_potential_descent_guard"]
    )
    dlp = g27_fault._dlp_evidence(
        summary,
        prepared.local.get("artifact")
        if isinstance(prepared.local, Mapping)
        else None,
    )
    topology = g26.topology_reachable_raw_bag_upper_bound(
        prepared.rows,
        prepared.request["edge_records"],
        prepared.contract["fault_edges"],
    )
    registered_upper = int(
        prepared.contract["registered_topology_upper_raw_bag_count"]
    )
    combined = [dict(row) for row in bags] + _synthetic_source_rejections(
        prepared.rejected_rows
    )
    fixed_outcome = g26.summarize_paper_outcome(
        prepared.rows,
        combined,
        total_raw_bags=int(prepared.contract["raw_bag_denominator"]),
    )
    completed_raw_bags = int(fixed_outcome["completed_raw_bag_count"])
    all_reachable_complete = completed == float(len(prepared.runtime_rows))
    binary_echo = True
    binary_sha_echo = True
    if "expected_binary_path" in prepared.request:
        expected_binary = Path(
            str(prepared.request["expected_binary_path"])
        ).resolve(strict=True)
        binary_echo = (
            Path(str(summary.get("loaded_cpp_binary_path", ""))).resolve()
            == expected_binary
        )
        binary_sha_echo = (
            summary.get("loaded_cpp_binary_sha256")
            == _file_sha256(expected_binary)
        )
    gates = {
        "registered_request_identity": prepared.contract["identity_pass"] is True,
        "runtime_terminal_partition": (
            completed is not None
            and failed is not None
            and completed + failed == float(len(prepared.runtime_rows))
        ),
        "runtime_summary_counts_match_returned_bag_states": (
            completed == float(returned_completed)
            and failed == float(returned_failed)
        ),
        "runtime_requested_count_echo": _number(summary.get("requested_count"))
        == float(len(prepared.runtime_rows)),
        "runtime_returned_exact_admission_cohort": returned_ids == expected_ids,
        "completed_at_correct_goal": completed_at_correct_goal,
        "full_denominator_partition": (
            len(prepared.runtime_rows) + len(prepared.rejected_rows)
            == len(prepared.rows)
        ),
        "reachable_segments_match_local_fixed_point": int(
            topology["reachable_segment_count"]
        )
        == len(prepared.runtime_rows),
        "registered_raw_bag_upper_matches_graph": int(
            topology["topology_reachable_raw_bag_upper_bound"]
        )
        == registered_upper,
        "completed_raw_bags_do_not_exceed_registered_upper": (
            completed_raw_bags <= registered_upper
        ),
        "all_reachable_complete_saturates_registered_upper": (
            completed_raw_bags == registered_upper
            if all_reachable_complete
            else True
        ),
        "fixed_horizon_echo": _number(
            summary.get("declared_max_simulation_time")
        )
        == FIXED_END_EPOCH,
        "event_budget_echo": _number(summary.get("declared_max_events"))
        == float(MAX_EVENTS),
        "event_count_within_budget": event_count is not None
        and event_count <= MAX_EVENTS,
        "event_limit_not_reached": summary.get("event_limit_reached") is False,
        "time_limit_reported": isinstance(summary.get("time_limit_reached"), bool),
        "fault_event_count": _number(summary.get("fault_event_count"))
        == float(fault_count),
        "repair_event_count_zero": _number(summary.get("repair_event_count"))
        == 0.0,
        "physical_fault_edge_entry_violation_zero": _number(
            summary.get("physical_fault_edge_entry_violation_count")
        )
        == 0.0,
        "reservation_conflicts_zero": _number(
            summary.get("reservation_conflicts")
        )
        == 0.0,
        "runtime_full_astar_zero": _number(
            summary.get("runtime_full_astar_calls")
        )
        == 0.0,
        "runtime_full_cie_astar_zero": _number(
            summary.get("runtime_full_cie_astar_calls")
        )
        == 0.0,
        "global_reservation_scan_zero": _number(
            summary.get("global_reservation_scan_count")
        )
        == 0.0,
        "merge_grant_conservation": summary.get(
            "merge_grant_conservation_holds"
        )
        is True,
        "merge_grant_active_bijection": summary.get(
            "merge_grant_active_bijection_holds"
        )
        is True,
        "loaded_expected_binary": binary_echo,
        "loaded_expected_binary_sha256": binary_sha_echo,
        "scorer_echo": summary.get("scorer_mode_echo")
        == prepared.request.get("scorer_mode"),
        "s4_component_mask_echo": int(summary.get("s4_score_component_mask", -1))
        == int(prepared.request.get("s4_score_component_mask", 15)),
        "j2_m3_echo": summary.get("merge_grant_rule") == "M3",
        "j2_jit_fair_aging_deadline_echo": summary.get(
            "merge_grant_timing_mode"
        )
        == "jit_fair_aging_deadline",
        "e2_echo": summary.get("g4irsf20_event_hotpath_policy") == "E2",
        "direct_neighbor_calendar_echo": summary.get(
            "s4_direct_neighbor_merge_calendar_visibility_enabled"
        )
        is True,
        "goal_arrival_completion_echo": summary.get(
            "complete_on_goal_arrival_enabled"
        )
        is True,
        "strict_guard_echo": (
            summary.get("s4_local_potential_descent_guard_enabled") is True
            if strict_enabled
            else summary.get("s4_local_potential_descent_guard_enabled")
            is not True
        ),
        "activation_telemetry_present": isinstance(
            summary.get("cie_component_activation"), Mapping
        ),
        "fault_value_echo": dlp["pass"] is True,
    }
    return {
        "pass": all(gates.values()),
        "gates": gates,
        "fault_value_echo": dlp,
        "topology_reachable_cohort": {
            "computed": topology,
            "registered_upper_raw_bags": registered_upper,
            "completed_raw_bags": completed_raw_bags,
        },
        "time_limit_is_fixed_horizon_outcome_not_automatic_failure": True,
    }


def _fixed_denominator_business(
    rows: Sequence[Mapping[str, Any]],
    combined: Sequence[Mapping[str, Any]],
    raw_bag_count: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    outcome = g26.summarize_paper_outcome(
        rows, combined, total_raw_bags=raw_bag_count
    )
    on_time = outcome["success"]["finish_le_std"]
    detailed = cie_business.summarize(
        rows, combined, fixed_horizon=FIXED_END_EPOCH
    )
    # The historical helper also computes a completed-bag-only TTH.  Do not
    # expose that survivor distribution here: this campaign's only THT field
    # is ``full_population_timing`` below.
    outcome = {
        key: value for key, value in outcome.items() if key != "paper_raw_bag_tth"
    }
    outcome["paper_raw_bag_tth"] = {
        "status": "NOT_REPORTED_USE_FULL_POPULATION_TIMING_FIELD",
        "survivor_or_common_cohort_used": False,
        "distribution": None,
    }
    return outcome, {
        "capacity": outcome["success"]["primary_completed_raw_bags"],
        "on_time": on_time,
        "missed_bag_count": raw_bag_count - int(on_time["count"]),
        "missed_bag_rate": 1.0 - float(on_time["rate"]),
        "literal_early_margin": outcome["success"][
            "finish_le_std_minus_2700_literal"
        ],
        "detailed": detailed,
    }


def _full_population_timing(
    rows: Sequence[Mapping[str, Any]],
    combined: Sequence[Mapping[str, Any]],
    *,
    completed_raw_bags: int,
    raw_bag_count: int,
) -> dict[str, Any]:
    if completed_raw_bags != raw_bag_count:
        return {
            "status": "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
            "raw_bag_count": None,
            "survivor_or_common_cohort_used": False,
            "distributions": None,
        }
    distributions, raw = g24.timing_distributions(rows, combined)
    return {
        "status": "FULL_POPULATION_RAW_BAG_TIMING_1X",
        "raw_bag_count": len(raw),
        "survivor_or_common_cohort_used": False,
        "distributions": distributions,
    }


def _diagnostics(
    summary: Mapping[str, Any], bags: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    activation = summary.get("cie_component_activation")
    activation = activation if isinstance(activation, Mapping) else {}
    strict = activation.get("strict_descent")
    strict = strict if isinstance(strict, Mapping) else {}
    decisions = [int(row.get("decision_count", 0) or 0) for row in bags]
    loops = [int(row.get("loop_count", 0) or 0) for row in bags]
    dlp_counters = {
        name: int(summary.get(name, 0) or 0)
        for name in g27_fault._DLP_COUNTER_FIELDS
    }
    return {
        "strict_descent": {
            "evaluation_count": int(strict.get("evaluation_count", 0) or 0),
            "filtered_candidate_count": int(
                strict.get("filtered_candidate_count", 0) or 0
            ),
            "filtered_decision_count": int(
                strict.get("filtered_decision_count", 0) or 0
            ),
            "empty_ranking_count": int(
                strict.get("empty_ranking_count", 0) or 0
            ),
            "scope": (
                "PRE_FEASIBILITY_FILTERING_DIAGNOSTIC_NOT_PAIRED_FINAL_ACTION"
            ),
            "equal_or_uphill_final_action_trace_available": False,
        },
        "fault_potential": {
            "dlp_counters": dlp_counters,
            "committed_mutation_count": dlp_counters[
                "g4irsf24_dlp_committed_mutation_count"
            ],
            "committed_mutation_scope": (
                "RUNTIME_RANKING_MUTATION_NOT_PAIRED_FINAL_ACTION_TRACE"
            ),
            "fault_target_edge_candidate_exposure_count": int(
                summary.get("fault_target_edge_candidate_exposure_count", 0)
                or 0
            ),
            "fault_target_edge_attempt_count": int(
                summary.get("fault_target_edge_attempt_count", 0) or 0
            ),
            "wrong_guidance_direct_measure_available": False,
            "wrong_guidance_proxies_only": (
                "fault-edge exposure/attempt, interlock rejection/hold/reroute, "
                "loops, completion and backlog"
            ),
        },
        "progress": {
            "summary_loop_count": int(summary.get("loop_count", 0) or 0),
            "bag_loop_count_sum": sum(loops),
            "bags_with_loop_count": sum(value > 0 for value in loops),
            "max_bag_loop_count": max(loops, default=0),
            "max_bag_decision_count": max(decisions, default=0),
            "unresolved_deadlock_count": int(
                summary.get("unresolved_deadlock_count", 0) or 0
            ),
            "starvation_count": int(summary.get("starvation_count", 0) or 0),
            "full_revisit_sequence_available": False,
            "short_history_limit": 8,
        },
        "holds_and_reroutes": {
            name: int(summary.get(name, 0) or 0)
            for name in (
                "physical_fault_interlock_rejection_count",
                "physical_fault_interlock_hold_count",
                "physical_fault_interlock_reroute_count",
                "local_fault_policy_action_count",
                "local_fault_policy_hold_count",
                "local_fault_policy_reroute_count",
                "source_admission_local_resource_hold_count",
                "source_admission_downstream_pressure_hold_count",
            )
        },
    }


def execute_case(
    *,
    map_name: str,
    scenario: str,
    study: str,
    arm: str,
    binary: Path | None,
    map2_workload_path: Path = map2_native.DEFAULT_WORKLOAD_1X,
    nanning_task_dir: Path = DEFAULT_NANNING_TASK_DIR,
    nanning_profile_path: Path = nanning_native.DEFAULT_MAP_PROFILE,
    nanning_fault_protocol_path: Path = nanning_native.DEFAULT_FAULT_PROTOCOL,
    dry_run: bool = False,
    executor: Executor | None = None,
) -> dict[str, Any]:
    if not dry_run and binary is None:
        raise FaultSpecialError("binary is required unless --dry-run is used")
    resolved_binary = binary.resolve(strict=True) if binary is not None else None
    prepared = prepare_special_request(
        map_name=map_name,
        scenario=scenario,
        study=study,
        arm=arm,
        binary=resolved_binary,
        map2_workload_path=map2_workload_path,
        nanning_task_dir=nanning_task_dir,
        nanning_profile_path=nanning_profile_path,
        nanning_fault_protocol_path=nanning_fault_protocol_path,
    )
    case_key = f"{study}:{map_name}:1x:{scenario}:{arm}"
    common = {
        "schema": SCHEMA,
        "case_key": case_key,
        "map": map_name,
        "scale": REGISTERED_SCALE,
        "scenario": scenario,
        "study": study,
        "arm": arm,
        "status": "READY_CIE_FAULT_SPECIAL_DRY_RUN" if dry_run else None,
        "native_execution_started": not dry_run,
        "population": {
            "raw_bag_denominator": REGISTERED_RAW_BAG_COUNT,
            "segment_count": REGISTERED_SEGMENT_COUNT,
            "whole_original_population": True,
            "fixed_denominator": True,
        },
        "algorithm": {
            "base": "G31_S4_NATIVE_H_SA_J2_M3_E2",
            "strict_descent": bool(
                prepared.request["enable_s4_local_potential_descent_guard"]
            ),
            "fault_treatment": (
                "SURVIVING_GRAPH_SERVICE_AWARE_POTENTIAL"
                if "g4irsf24_dlp_artifact" in prepared.request
                else "EDGE_FILTER_ONLY"
            ),
            "new_scorer_added": False,
            "new_cpp_mode_added": False,
            "posthoc_tuning": False,
        },
        "experiment_contract": dict(prepared.contract),
        "request_contract": {
            "runtime_requested_segment_count": len(prepared.runtime_rows),
            "source_rejected_unreachable_segment_count": len(
                prepared.rejected_rows
            ),
            "fault_windows": [
                list(row) for row in prepared.request["fault_windows"]
            ],
            "max_simulation_time": prepared.request["max_simulation_time"],
            "max_events": prepared.request["max_events"],
            "scorer_mode": prepared.request["scorer_mode"],
            "s4_score_component_mask": int(
                prepared.request.get("s4_score_component_mask", 15)
            ),
            "merge_grant_rule": prepared.request["merge_grant_rule"],
            "merge_grant_timing_mode": prepared.request[
                "merge_grant_timing_mode"
            ],
            "event_hotpath_policy": prepared.request[
                "g4irsf20_event_hotpath_policy"
            ],
            "strict_descent": prepared.request[
                "enable_s4_local_potential_descent_guard"
            ],
            "dlp_active": "g4irsf24_dlp_artifact" in prepared.request,
            "component_activation_telemetry": True,
        },
        "provenance": {
            "git_commit": _git_value("rev-parse", "HEAD"),
            "git_branch": _git_value("branch", "--show-current"),
            "runner_sha256": _file_sha256(Path(__file__).resolve()),
            "binary_path": str(resolved_binary) if resolved_binary else None,
            "binary_sha256": (
                _file_sha256(resolved_binary) if resolved_binary else None
            ),
            "canonical_workload_path": str(prepared.workload_source.resolve()),
            "canonical_workload_sha256": _file_sha256(
                prepared.workload_source.resolve(strict=True)
            ),
            "executor_identity": "COMMON_CPP_EVENT_EXECUTOR_G31_NATIVE",
            "release_protocol": "CANONICAL_PASS_TIME_COMPLETE_1X_POPULATION",
            "random_seed": None,
        },
    }
    if dry_run:
        return common

    selected_executor = executor or cpp_backend.g4irsf11_event_runtime_from_records
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = selected_executor(**prepared.request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    summary = payload.get("summary") if isinstance(payload, Mapping) else None
    bags = payload.get("bags") if isinstance(payload, Mapping) else None
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise FaultSpecialError("native executor did not return summary and bags")
    if any(not isinstance(row, Mapping) for row in bags):
        raise FaultSpecialError("native executor returned a non-object bag row")

    combined = [dict(row) for row in bags] + _synthetic_source_rejections(
        prepared.rejected_rows
    )
    integrity = _execution_integrity(
        prepared=prepared, summary=summary, bags=bags
    )
    outcome, business = _fixed_denominator_business(
        prepared.rows,
        combined,
        REGISTERED_RAW_BAG_COUNT,
    )
    completed_raw = int(outcome["completed_raw_bag_count"])
    timing = _full_population_timing(
        prepared.rows,
        combined,
        completed_raw_bags=completed_raw,
        raw_bag_count=REGISTERED_RAW_BAG_COUNT,
    )
    return _json_safe(
        {
            **common,
            "status": "COMPLETE" if integrity["pass"] else "FAILED_INTEGRITY",
            "outcome": {
                "runtime_requested_segment_count": len(prepared.runtime_rows),
                "source_rejected_unreachable_segment_count": len(
                    prepared.rejected_rows
                ),
                "combined_terminal_segment_count": len(combined),
                **outcome,
            },
            "fixed_denominator_business": business,
            "full_population_timing": timing,
            "execution_integrity": integrity,
            "mechanism_diagnostics": _diagnostics(summary, bags),
            "runtime": {
                "wall_seconds": wall_seconds,
                "cpu_seconds": cpu_seconds,
                "event_count": int(summary.get("event_count", 0) or 0),
                "decision_count": int(summary.get("decision_count", 0) or 0),
                "time_limit_reached": summary.get("time_limit_reached"),
                "event_limit_reached": summary.get("event_limit_reached"),
                "native_summary": dict(summary),
            },
        }
    )


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


TABLE_FIELDS = (
    "case_key",
    "study",
    "map",
    "scenario",
    "arm",
    "status",
    "integrity_pass",
    "git_commit",
    "runner_sha256",
    "binary_sha256",
    "loaded_cpp_binary_sha256",
    "workload_sha256",
    "canonical_release_schedule_sha256",
    "reference_request_sha256",
    "raw_bag_denominator",
    "runtime_requested_segment_count",
    "source_rejected_unreachable_segment_count",
    "graph_treatment_raw_bags_with_source_rejected_segment_count",
    "native_admission_cohort_identical_within_pair",
    "admission_cohort_boundary",
    "pure_potential_effect_identified",
    "completed_raw_bag_count",
    "completion_rate",
    "on_time_raw_bag_count",
    "on_time_rate",
    "missed_bag_count",
    "missed_bag_rate",
    "fixed_horizon_tardiness_sum_seconds",
    "raw_bag_peak_backlog",
    "raw_bag_end_backlog",
    "raw_bag_backlog_area_seconds",
    "timing_status",
    "population_latency_mean_seconds",
    "population_latency_p95_seconds",
    "population_latency_p99_seconds",
    "population_latency_max_seconds",
    "strict_filtered_candidate_count_pre_feasibility",
    "strict_filtered_decision_count_pre_feasibility",
    "strict_empty_ranking_count_pre_feasibility",
    "dlp_committed_ranking_mutation_count",
    "fault_target_edge_candidate_exposure_count",
    "fault_target_edge_attempt_count",
    "physical_fault_interlock_rejection_count",
    "physical_fault_interlock_hold_count",
    "physical_fault_interlock_reroute_count",
    "loop_count",
    "bags_with_loop_count",
    "max_bag_decision_count",
    "unresolved_deadlock_count",
    "wall_seconds",
    "cpu_seconds",
    "event_count",
    "decision_count",
)


def result_table_row(value: Mapping[str, Any]) -> dict[str, Any]:
    strict = _nested(value, "mechanism_diagnostics", "strict_descent") or {}
    potential = _nested(value, "mechanism_diagnostics", "fault_potential") or {}
    progress = _nested(value, "mechanism_diagnostics", "progress") or {}
    holds = _nested(value, "mechanism_diagnostics", "holds_and_reroutes") or {}
    paper_network = _nested(
        value,
        "full_population_timing",
        "distributions",
        "processed_attempt",
    ) or {}
    return {
        "case_key": value.get("case_key"),
        "study": value.get("study"),
        "map": value.get("map"),
        "scenario": value.get("scenario"),
        "arm": value.get("arm"),
        "status": value.get("status"),
        "integrity_pass": _nested(value, "execution_integrity", "pass"),
        "git_commit": _nested(value, "provenance", "git_commit"),
        "runner_sha256": _nested(value, "provenance", "runner_sha256"),
        "binary_sha256": _nested(value, "provenance", "binary_sha256"),
        "loaded_cpp_binary_sha256": _nested(
            value, "runtime", "native_summary", "loaded_cpp_binary_sha256"
        ),
        "workload_sha256": _nested(
            value, "provenance", "canonical_workload_sha256"
        ),
        "canonical_release_schedule_sha256": _nested(
            value, "experiment_contract", "canonical_release_schedule_sha256"
        ),
        "reference_request_sha256": _nested(
            value, "experiment_contract", "reference_request_sha256"
        ),
        "raw_bag_denominator": _nested(
            value, "population", "raw_bag_denominator"
        ),
        "runtime_requested_segment_count": _nested(
            value, "request_contract", "runtime_requested_segment_count"
        ),
        "source_rejected_unreachable_segment_count": _nested(
            value,
            "request_contract",
            "source_rejected_unreachable_segment_count",
        ),
        "graph_treatment_raw_bags_with_source_rejected_segment_count": _nested(
            value,
            "experiment_contract",
            "graph_treatment_raw_bags_with_source_rejected_segment_count",
        ),
        "native_admission_cohort_identical_within_pair": _nested(
            value,
            "experiment_contract",
            "native_admission_cohort_identical_within_pair",
        ),
        "admission_cohort_boundary": _nested(
            value, "experiment_contract", "admission_cohort_boundary"
        ),
        "pure_potential_effect_identified": _nested(
            value, "experiment_contract", "pure_potential_effect_identified"
        ),
        "completed_raw_bag_count": _nested(
            value, "fixed_denominator_business", "capacity", "count"
        ),
        "completion_rate": _nested(
            value, "fixed_denominator_business", "capacity", "rate"
        ),
        "on_time_raw_bag_count": _nested(
            value, "fixed_denominator_business", "on_time", "count"
        ),
        "on_time_rate": _nested(
            value, "fixed_denominator_business", "on_time", "rate"
        ),
        "missed_bag_count": _nested(
            value, "fixed_denominator_business", "missed_bag_count"
        ),
        "missed_bag_rate": _nested(
            value, "fixed_denominator_business", "missed_bag_rate"
        ),
        "fixed_horizon_tardiness_sum_seconds": _nested(
            value,
            "fixed_denominator_business",
            "detailed",
            "tardiness_seconds",
            "fixed_horizon_all_population_lower_bound",
            "sum",
        ),
        "raw_bag_peak_backlog": _nested(
            value,
            "fixed_denominator_business",
            "detailed",
            "backlog",
            "raw_bag_total",
            "peak_backlog",
        ),
        "raw_bag_end_backlog": _nested(
            value,
            "fixed_denominator_business",
            "detailed",
            "backlog",
            "raw_bag_total",
            "end_backlog",
        ),
        "raw_bag_backlog_area_seconds": _nested(
            value,
            "fixed_denominator_business",
            "detailed",
            "backlog",
            "raw_bag_total",
            "backlog_area_seconds",
        ),
        "timing_status": _nested(value, "full_population_timing", "status"),
        "population_latency_mean_seconds": paper_network.get("mean_seconds"),
        "population_latency_p95_seconds": paper_network.get("p95_seconds"),
        "population_latency_p99_seconds": paper_network.get("p99_seconds"),
        "population_latency_max_seconds": paper_network.get("max_seconds"),
        "strict_filtered_candidate_count_pre_feasibility": strict.get(
            "filtered_candidate_count"
        ),
        "strict_filtered_decision_count_pre_feasibility": strict.get(
            "filtered_decision_count"
        ),
        "strict_empty_ranking_count_pre_feasibility": strict.get(
            "empty_ranking_count"
        ),
        "dlp_committed_ranking_mutation_count": potential.get(
            "committed_mutation_count"
        ),
        "fault_target_edge_candidate_exposure_count": potential.get(
            "fault_target_edge_candidate_exposure_count"
        ),
        "fault_target_edge_attempt_count": potential.get(
            "fault_target_edge_attempt_count"
        ),
        "physical_fault_interlock_rejection_count": holds.get(
            "physical_fault_interlock_rejection_count"
        ),
        "physical_fault_interlock_hold_count": holds.get(
            "physical_fault_interlock_hold_count"
        ),
        "physical_fault_interlock_reroute_count": holds.get(
            "physical_fault_interlock_reroute_count"
        ),
        "loop_count": progress.get("summary_loop_count"),
        "bags_with_loop_count": progress.get("bags_with_loop_count"),
        "max_bag_decision_count": progress.get("max_bag_decision_count"),
        "unresolved_deadlock_count": progress.get(
            "unresolved_deadlock_count"
        ),
        "wall_seconds": _nested(value, "runtime", "wall_seconds"),
        "cpu_seconds": _nested(value, "runtime", "cpu_seconds"),
        "event_count": _nested(value, "runtime", "event_count"),
        "decision_count": _nested(value, "runtime", "decision_count"),
    }


EFFECT_METRICS = (
    "completed_raw_bag_count",
    "completion_rate",
    "on_time_raw_bag_count",
    "on_time_rate",
    "missed_bag_count",
    "missed_bag_rate",
    "fixed_horizon_tardiness_sum_seconds",
    "raw_bag_peak_backlog",
    "raw_bag_end_backlog",
    "raw_bag_backlog_area_seconds",
    "population_latency_mean_seconds",
    "population_latency_p95_seconds",
    "population_latency_p99_seconds",
    "population_latency_max_seconds",
    "loop_count",
    "max_bag_decision_count",
    "wall_seconds",
    "event_count",
)

PAIR_IDENTITY_FIELDS = (
    "git_commit",
    "runner_sha256",
    "binary_sha256",
    "loaded_cpp_binary_sha256",
    "workload_sha256",
    "canonical_release_schedule_sha256",
    "reference_request_sha256",
)


def _effect(reference: Any, treatment: Any) -> dict[str, Any]:
    ref = _number(reference)
    treated = _number(treatment)
    if ref is None or treated is None:
        return {"reference": ref, "treatment": treated, "absolute": None, "percent": None}
    absolute = treated - ref
    return {
        "reference": ref,
        "treatment": treated,
        "absolute": absolute,
        "percent": absolute / abs(ref) * 100.0 if ref != 0.0 else None,
    }


def _expected_case_keys() -> list[str]:
    return sorted(
        f"{study}:{map_name}:1x:{scenario}:{arm}"
        for study, arms in STUDY_ARMS.items()
        for map_name, scenarios in REGISTERED_SCENARIOS.items()
        for scenario in scenarios
        for arm in arms
    )


def aggregate_results(result_paths: Sequence[Path]) -> dict[str, Any]:
    by_key: dict[str, dict[str, Any]] = {}
    artifact_paths: dict[str, str] = {}
    for path in sorted(set(path.resolve() for path in result_paths)):
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or value.get("schema") != SCHEMA:
            continue
        key = str(value.get("case_key", ""))
        if not key:
            raise FaultSpecialError(f"fault-special artifact lacks case_key: {path}")
        map_name = str(value.get("map", ""))
        scenario = str(value.get("scenario", ""))
        study = str(value.get("study", ""))
        arm = str(value.get("arm", ""))
        _validate_cell(map_name, scenario, study, arm)
        expected_key = f"{study}:{map_name}:1x:{scenario}:{arm}"
        if value.get("scale") != REGISTERED_SCALE or key != expected_key:
            raise FaultSpecialError(
                f"artifact cell identity does not match its case_key: {path}"
            )
        if key in by_key:
            raise FaultSpecialError(f"duplicate fault-special cell: {key}")
        by_key[key] = value
        artifact_paths[key] = str(path)

    rows = [result_table_row(by_key[key]) for key in sorted(by_key)]
    keyed_rows = {
        (str(row["study"]), str(row["map"]), str(row["scenario"]), str(row["arm"])): row
        for row in rows
    }
    effects: list[dict[str, Any]] = []
    for study in STUDY_ARMS:
        for map_name, scenarios in REGISTERED_SCENARIOS.items():
            for scenario in scenarios:
                reference = keyed_rows.get(
                    (study, map_name, scenario, REFERENCE_ARM[study])
                )
                treatment = keyed_rows.get(
                    (study, map_name, scenario, TREATMENT_ARM[study])
                )
                if reference is None or treatment is None:
                    continue
                pair_identity_gates = {
                    field: bool(reference.get(field))
                    and reference.get(field) == treatment.get(field)
                    for field in PAIR_IDENTITY_FIELDS
                }
                pair_identity_pass = all(pair_identity_gates.values())
                valid = (
                    reference.get("status") == "COMPLETE"
                    and treatment.get("status") == "COMPLETE"
                    and reference.get("integrity_pass") is True
                    and treatment.get("integrity_pass") is True
                    and pair_identity_pass
                )
                effects.append(
                    {
                        "study": study,
                        "map": map_name,
                        "scenario": scenario,
                        "reference_arm": REFERENCE_ARM[study],
                        "treatment_arm": TREATMENT_ARM[study],
                        "valid_for_outcome_comparison": valid,
                        "pair_identity_pass": pair_identity_pass,
                        "pair_identity_gates": pair_identity_gates,
                        "native_admission_cohort_identical": treatment.get(
                            "native_admission_cohort_identical_within_pair"
                        ),
                        "causal_interpretation": (
                            "INVALID_IDENTITY_NOT_COMPARABLE"
                            if not pair_identity_pass
                            else (
                                "PURE_REGISTERED_SINGLE_FACTOR"
                                if study == "strict"
                                or treatment.get(
                                    "pure_potential_effect_identified"
                                )
                                is True
                                else (
                                    "BUNDLED_GRAPH_TREATMENT_EFFECT_NOT_PURE_"
                                    "POTENTIAL_EFFECT"
                                )
                            )
                        ),
                        "metrics": {
                            metric: (
                                _effect(reference.get(metric), treatment.get(metric))
                                if valid
                                else {
                                    "reference": reference.get(metric),
                                    "treatment": treatment.get(metric),
                                    "absolute": None,
                                    "percent": None,
                                }
                            )
                            for metric in EFFECT_METRICS
                        },
                    }
                )

    expected = set(_expected_case_keys())
    complete = sorted(
        key
        for key, value in by_key.items()
        if value.get("status") == "COMPLETE"
        and _nested(value, "execution_integrity", "pass") is True
    )
    dry = sorted(
        key
        for key, value in by_key.items()
        if value.get("status") == "READY_CIE_FAULT_SPECIAL_DRY_RUN"
    )
    invalid = sorted(set(by_key) - set(complete) - set(dry))
    complete_rows = [
        result_table_row(by_key[key]) for key in complete if key in by_key
    ]
    campaign_identity_gates = {
        "single_git_commit": len(
            {row.get("git_commit") for row in complete_rows}
        )
        == 1
        and all(
            row.get("git_commit") not in (None, "", "UNAVAILABLE")
            for row in complete_rows
        ),
        "single_runner_sha256": len(
            {row.get("runner_sha256") for row in complete_rows}
        )
        == 1
        and all(bool(row.get("runner_sha256")) for row in complete_rows),
        "single_binary_sha256": len(
            {row.get("binary_sha256") for row in complete_rows}
        )
        == 1
        and all(bool(row.get("binary_sha256")) for row in complete_rows),
        "single_loaded_binary_sha256": len(
            {row.get("loaded_cpp_binary_sha256") for row in complete_rows}
        )
        == 1
        and all(
            row.get("loaded_cpp_binary_sha256") == row.get("binary_sha256")
            for row in complete_rows
        ),
        "single_workload_per_map": all(
            len(
                {
                    row.get("workload_sha256")
                    for row in complete_rows
                    if row.get("map") == map_name
                }
            )
            <= 1
            and all(
                bool(row.get("workload_sha256"))
                for row in complete_rows
                if row.get("map") == map_name
            )
            for map_name in REGISTERED_SCENARIOS
        ),
        "single_release_schedule_per_map": all(
            len(
                {
                    row.get("canonical_release_schedule_sha256")
                    for row in complete_rows
                    if row.get("map") == map_name
                }
            )
            <= 1
            and all(
                bool(row.get("canonical_release_schedule_sha256"))
                for row in complete_rows
                if row.get("map") == map_name
            )
            for map_name in REGISTERED_SCENARIOS
        ),
        "every_available_pair_identity_matches": all(
            effect["pair_identity_pass"] for effect in effects
        ),
    }
    campaign_identity_pass = bool(complete_rows) and all(
        campaign_identity_gates.values()
    )
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": (
            "COMPLETE"
            if set(complete) == expected and campaign_identity_pass
            else "PARTIAL"
        ),
        "registered_scope": {
            "scale": REGISTERED_SCALE,
            "raw_bag_denominator_per_cell": REGISTERED_RAW_BAG_COUNT,
            "segment_count_per_cell": REGISTERED_SEGMENT_COUNT,
            "maps_and_faults": REGISTERED_SCENARIOS,
            "studies_and_arms": STUDY_ARMS,
            "expected_case_count": len(expected),
        },
        "complete_case_keys": complete,
        "dry_run_case_keys": dry,
        "invalid_case_keys": invalid,
        "missing_case_keys": sorted(expected - set(by_key)),
        "campaign_identity_pass": campaign_identity_pass,
        "campaign_identity_gates": campaign_identity_gates,
        "artifact_paths": artifact_paths,
        "claim_boundaries": {
            "fixed_denominator": "ALL_ORIGINAL_RAW_BAGS",
            "timing": (
                "1x only if the entire raw-bag population completes; no "
                "survivor/common-cohort timing; 2x remains formal N/A"
            ),
            "strict_telemetry": (
                "pre-feasibility filtering diagnostic, not a paired final action"
            ),
            "potential": (
                "both arms share source-unreachable recognition and the native "
                "admission cohort; only the DLP artifact changes"
            ),
        },
        "rows": rows,
        "pair_effects": effects,
    }


def _display(value: Any, digits: int = 4) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_report(aggregate: Mapping[str, Any]) -> str:
    rows = aggregate.get("rows", [])
    effects = aggregate.get("pair_effects", [])
    lines = [
        "# CIE fixed-fault specialty results",
        "",
        f"Campaign status: **{aggregate.get('status', 'UNKNOWN')}**.",
        "",
        (
            "Campaign identity gate: **"
            f"{aggregate.get('campaign_identity_pass', False)}**. Pair effects "
            "require the same commit, runner, binary (requested and actually "
            "loaded), workload, release schedule, and reference request."
        ),
        "",
        (
            "Every executed cell uses the original 1× population (28,506 raw "
            "bags / 43,603 segments), canonical `pass_time` releases, the same "
            "fixed horizon, and fixed-denominator completion, deadline, "
            "tardiness and backlog metrics."
        ),
        "",
        (
            "Strict counters describe pre-feasibility filtering and are not a "
            "paired final-action trace. DLP committed mutations are runtime "
            "ranking mutations, likewise not a paired final-action trace."
        ),
        "",
        (
            "For potential cells with source-unreachable bags, both arms use "
            "the same unreachable recognition, native admission cohort, "
            "complete raw-bag denominator, and releases. The only request "
            "delta is the existing DLP artifact."
        ),
        "",
        (
            "Timing is shown only after all 28,506 raw bags complete at 1×. No "
            "survivor/common-cohort timing is used; a future 2× extension remains "
            "formal THT N/A by protocol."
        ),
        "",
        "## Arm results",
        "",
        "| Study | Map/fault | Arm | Status | Integrity | Complete | On time | Missed | Tardiness sum (s) | End backlog | Timing | Mean/P95/P99/max (s) | Cohort |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {study} | {map}/{scenario} | {arm} | {status} | {integrity} | "
            "{complete} | {on_time} | {missed} | {tardy} | {backlog} | "
            "{timing} | {latency} | {cohort} |".format(
                study=row.get("study"),
                map=row.get("map"),
                scenario=row.get("scenario"),
                arm=row.get("arm"),
                status=row.get("status"),
                integrity=row.get("integrity_pass"),
                complete=_display(row.get("completed_raw_bag_count")),
                on_time=_display(row.get("on_time_raw_bag_count")),
                missed=_display(row.get("missed_bag_count")),
                tardy=_display(
                    row.get("fixed_horizon_tardiness_sum_seconds"), 1
                ),
                backlog=_display(row.get("raw_bag_end_backlog")),
                timing=row.get("timing_status") or "N/A",
                latency="/".join(
                    _display(row.get(field), 3)
                    for field in (
                        "population_latency_mean_seconds",
                        "population_latency_p95_seconds",
                        "population_latency_p99_seconds",
                        "population_latency_max_seconds",
                    )
                ),
                cohort=(
                    "same"
                    if row.get("native_admission_cohort_identical_within_pair")
                    else "different (declared)"
                ),
            )
        )

    lines.extend(["", "## Registered pair effects", ""])
    if not effects:
        lines.append("No complete arm pair is available yet.")
    else:
        lines.extend(
            [
                "| Study | Map/fault | Valid | Interpretation | Δ complete | Δ on time | Δ missed | Δ tardiness (s) | Δ end backlog | Δ mean/P95/P99/max (s) |",
                "|---|---|---|---|---:|---:|---:|---:|---:|---|",
            ]
        )
        for effect in effects:
            metrics = effect["metrics"]
            lines.append(
                "| {study} | {map}/{scenario} | {valid} | {interpretation} | "
                "{complete} | {on_time} | {missed} | {tardy} | {backlog} | "
                "{latency} |".format(
                    study=effect["study"],
                    map=effect["map"],
                    scenario=effect["scenario"],
                    valid="yes" if effect["valid_for_outcome_comparison"] else "no",
                    interpretation=effect["causal_interpretation"],
                    complete=_display(
                        metrics["completed_raw_bag_count"]["absolute"]
                    ),
                    on_time=_display(
                        metrics["on_time_raw_bag_count"]["absolute"]
                    ),
                    missed=_display(metrics["missed_bag_count"]["absolute"]),
                    tardy=_display(
                        metrics["fixed_horizon_tardiness_sum_seconds"][
                            "absolute"
                        ],
                        1,
                    ),
                    backlog=_display(
                        metrics["raw_bag_end_backlog"]["absolute"]
                    ),
                    latency="/".join(
                        _display(metrics[field]["absolute"], 3)
                        for field in (
                            "population_latency_mean_seconds",
                            "population_latency_p95_seconds",
                            "population_latency_p99_seconds",
                            "population_latency_max_seconds",
                        )
                    ),
                )
            )
    lines.extend(
        [
            "",
            "## Missing / invalid cells",
            "",
            f"Missing: {', '.join(aggregate.get('missing_case_keys', [])) or 'none'}",
            "",
            f"Invalid: {', '.join(aggregate.get('invalid_case_keys', [])) or 'none'}",
            "",
        ]
    )
    return "\n".join(lines)


def _result_paths(case_root: Path, explicit: Sequence[Path]) -> list[Path]:
    paths = [_rooted(path).resolve(strict=True) for path in explicit]
    if case_root.exists():
        paths.extend(path.resolve() for path in case_root.rglob("*.json"))
    return sorted(set(paths))


def _add_input_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--map2-workload", type=Path, default=map2_native.DEFAULT_WORKLOAD_1X
    )
    parser.add_argument(
        "--nanning-task-dir", type=Path, default=DEFAULT_NANNING_TASK_DIR
    )
    parser.add_argument(
        "--nanning-map-profile",
        type=Path,
        default=nanning_native.DEFAULT_MAP_PROFILE,
    )
    parser.add_argument(
        "--nanning-fault-protocol",
        type=Path,
        default=nanning_native.DEFAULT_FAULT_PROTOCOL,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    case = commands.add_parser("case", help="run or dry-run one registered arm")
    case.add_argument("--study", choices=tuple(STUDY_ARMS), required=True)
    case.add_argument("--map", choices=tuple(REGISTERED_SCENARIOS), required=True)
    case.add_argument(
        "--scenario",
        choices=sorted(
            {item for values in REGISTERED_SCENARIOS.values() for item in values}
        ),
        required=True,
    )
    case.add_argument(
        "--arm",
        choices=sorted({item for values in STUDY_ARMS.values() for item in values}),
        required=True,
    )
    case.add_argument("--binary", type=Path)
    case.add_argument("--output", type=Path, required=True)
    case.add_argument("--dry-run", action="store_true")
    case.add_argument("--force", action="store_true")
    _add_input_args(case)

    aggregate = commands.add_parser(
        "aggregate", help="aggregate artifacts and write JSON, CSV and Markdown"
    )
    aggregate.add_argument("--case-root", type=Path, default=DEFAULT_CASE_ROOT)
    aggregate.add_argument("--result", type=Path, action="append", default=[])
    aggregate.add_argument("--output", type=Path, default=DEFAULT_AGGREGATE)
    aggregate.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    aggregate.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "aggregate":
        payload = aggregate_results(
            _result_paths(_rooted(args.case_root), args.result)
        )
        output = _rooted(args.output)
        table = _rooted(args.table)
        report = _rooted(args.report)
        _write_json(output, payload)
        _write_csv(table, payload["rows"])
        _write_text(report, render_report(payload))
        print(
            json.dumps(
                {
                    "status": payload["status"],
                    "output": str(output),
                    "table": str(table),
                    "report": str(report),
                }
            )
        )
        return 0 if payload["status"] == "COMPLETE" else 2

    output = _rooted(args.output)
    if output.exists() and not args.force:
        raise FaultSpecialError(f"output exists; pass --force to replace: {output}")
    payload = execute_case(
        map_name=args.map,
        scenario=args.scenario,
        study=args.study,
        arm=args.arm,
        binary=_rooted(args.binary) if args.binary else None,
        map2_workload_path=_rooted(args.map2_workload),
        nanning_task_dir=_rooted(args.nanning_task_dir),
        nanning_profile_path=_rooted(args.nanning_map_profile),
        nanning_fault_protocol_path=_rooted(args.nanning_fault_protocol),
        dry_run=args.dry_run,
    )
    _write_json(output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "case_key": payload["case_key"],
                "output": str(output),
            }
        )
    )
    return 0 if payload["status"] in {
        "COMPLETE",
        "READY_CIE_FAULT_SPECIAL_DRY_RUN",
    } else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        FaultSpecialError,
        map_adapter.MapProfileError,
        map2_native.Map2NativeError,
        nanning_native.Native31Error,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"CIE fault specials failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
