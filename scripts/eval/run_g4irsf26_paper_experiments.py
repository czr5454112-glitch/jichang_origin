#!/usr/bin/env python3
"""Run the thesis Chapter-5 experiment matrix with the active S4 runtime.

This is intentionally a thin orchestration layer.  It reuses the protected
G24 Java-release alignment, the active G20 S4/J2/E2 request, and the G6 speed
graph reconstruction.  Each case runs in a fresh Python process and writes one
compact JSON artifact, so an interrupted campaign resumes case by case.

The runner does not claim that a reconstruction is the thesis simulator:
Table 5.4 keeps standard-speed heuristic estimates while physical edge travel
uses the slower actual speed, and Table 5.5 maps each paper line ID to one
documented seed edge before applying an all-day temporal fault window.
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend
from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf20_event_hotpath as g20
from scripts.eval import run_g4irsf24_native_race as g24
from scripts.eval import run_g4irsf6_paper_protocol_gap_closure as g6
from scripts.eval.g4irsf11_fixed_map import canonical_map_data


CASE_SCHEMA = "czr005.g4irsf26.paper_s4_case.v1"
AGGREGATE_SCHEMA = "czr005.g4irsf26.paper_s4_aggregate.v1"
MANIFEST_SCHEMA = "czr005.g4irsf26.paper_s4_manifest.v1"
PAPER_DAY_SEGMENTS = 43_603
PAPER_DAY_RAW_BAGS = 28_506
LITERAL_EARLY_MARGIN_SECONDS = 45.0 * 60.0
ALL_DAY_REPAIR_MARGIN_SECONDS = 7.0 * 24.0 * 60.0 * 60.0
FRESH_JAVA_START_EPOCH = 8_260.0
FRESH_JAVA_FULL_MAX_EPOCHS = 90_000
TABLE_5_5_FIXED_HORIZON = (
    FRESH_JAVA_START_EPOCH + FRESH_JAVA_FULL_MAX_EPOCHS - 1.0
)
TABLE_5_5_MAX_EVENTS = 60_000_000
DEFAULT_RELEASE_CSV = ROOT / "artifacts/datasets/g4irsf24_release_compact.csv"
SPEED_RELEASE_CSV: Mapping[float, Path] = {
    1.5: ROOT / "artifacts/datasets/g4irsf26_release_speed_1p5.csv",
    2.0: ROOT / "artifacts/datasets/g4irsf26_release_speed_2p0.csv",
    2.5: DEFAULT_RELEASE_CSV,
    3.0: ROOT / "artifacts/datasets/g4irsf26_release_speed_3p0.csv",
}
DEFAULT_CASE_DIR = ROOT / "outputs/runtime/g4irsf26_paper_experiments"
DEFAULT_AGGREGATE_JSON = ROOT / "outputs/tables/g4irsf26_paper_experiments.json"
DEFAULT_AGGREGATE_CSV = ROOT / "outputs/tables/g4irsf26_paper_experiments.csv"
ADMITTED_CASE_STATUSES = {
    "COMPLETE",
    "COMPLETE_FIXED_HORIZON",
    "COMPLETE_TOPOLOGY_SATURATED",
}
SUCCESSFUL_AGGREGATE_STATUSES = {
    "COMPLETE",
    "COMPLETE_WITH_ARCHIVED_ONLY_GAP",
}

PAPER_T5_2: Mapping[float, Mapping[str, float]] = {
    1.5: {"min": 5.10, "mean": 6.44, "max": 9.68},
    2.0: {"min": 3.87, "mean": 4.93, "max": 7.37},
    2.5: {"min": 3.13, "mean": 3.96, "max": 5.98},
    3.0: {"min": 2.63, "mean": 3.37, "max": 5.05},
}

PAPER_T5_4: Mapping[tuple[float, int], Mapping[str, float]] = {
    (1.5, 10): {"dynamic": 6.45, "static": 6.59, "improvement": 2.12},
    (1.5, 20): {"dynamic": 6.67, "static": 6.86, "improvement": 2.77},
    (1.5, 30): {"dynamic": 6.91, "static": 7.11, "improvement": 2.81},
    (2.0, 10): {"dynamic": 4.92, "static": 5.07, "improvement": 2.96},
    (2.0, 20): {"dynamic": 5.16, "static": 5.36, "improvement": 3.73},
    (2.0, 30): {"dynamic": 5.42, "static": 5.62, "improvement": 3.56},
    (2.5, 10): {"dynamic": 3.99, "static": 4.19, "improvement": 4.77},
    (2.5, 20): {"dynamic": 4.25, "static": 4.46, "improvement": 4.71},
    (2.5, 30): {"dynamic": 4.49, "static": 4.72, "improvement": 4.87},
    (3.0, 10): {"dynamic": 3.39, "static": 3.56, "improvement": 4.78},
    (3.0, 20): {"dynamic": 3.51, "static": 3.72, "improvement": 5.65},
    (3.0, 30): {"dynamic": 3.64, "static": 3.87, "improvement": 5.94},
}

# These are protocol seed edges, not a claim that one edge equals every
# downstream conveyor reported as affected in the thesis.
PAPER_LINE_SEED_EDGES: Mapping[int, tuple[int, int]] = {
    1: (6, 12),
    2: (8, 11),
    3: (13, 23),
    4: (24, 27),
    5: (14, 46),
    6: (43, 15),
    7: (33, 44),
    8: (31, 32),
}
PAPER_LINE_MAPPING_EVIDENCE: Mapping[int, str] = {
    1: "RECONSTRUCTION",
    2: "STRONG",
    3: "STRONG",
    4: "STRONG",
    5: "STRONG",
    6: "RECONSTRUCTION",
    7: "RECONSTRUCTION",
    8: "STRONG",
}

# The archived workbook is internally inconsistent for this one row.  Its
# pair_5_7 sheet is named ``33-44,46-36`` even though the other rows bind line
# 5 to 14->46 and line 7 to 33->44. A fresh exact-label HCA probe produced
# 8,013/28,506 rather than the cached 13,939/28,506, so this remains an
# exploratory archival-label probe and cannot identify the paper protocol.
# It never changes either global line mapping.
PAPER_T5_5_CASE_SEED_EDGE_OVERRIDES: Mapping[
    str, tuple[tuple[int, int], ...]
] = {
    "pair_5_7": ((33, 44), (46, 36)),
}

# scenario suffix, line IDs, paper affected-line count, paper success rate
PAPER_T5_5 = (
    ("single_1", (1,), 1, 1.00),
    ("single_2", (2,), 7, 0.88),
    ("single_3", (3,), 5, 1.00),
    ("single_4", (4,), 15, 0.95),
    ("single_5", (5,), 24, 0.97),
    ("single_6", (6,), 7, 0.96),
    ("single_7", (7,), 1, 1.00),
    ("single_8", (8,), 7, 0.99),
    ("pair_1_7", (1, 7), 2, 1.00),
    ("pair_2_4", (2, 4), 22, 0.76),
    ("pair_3_5", (3, 5), 36, 0.66),
    ("pair_4_5", (4, 5), 54, 0.00),
    ("pair_5_7", (5, 7), 12, 0.48),
    ("triple_2_4_6", (2, 4, 6), 36, 0.26),
    ("triple_3_5_8", (3, 5, 8), 51, 0.05),
    ("triple_4_6_7", (4, 6, 7), 30, 0.26),
)


class PaperExperimentError(RuntimeError):
    """Raised when a case cannot be admitted as G26 evidence."""


def _speed_label(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def paper_cases() -> list[dict[str, Any]]:
    """Return the frozen 4 + 12 + 16 S4 Chapter-5 case matrix."""

    cases: list[dict[str, Any]] = []
    for speed, paper in PAPER_T5_2.items():
        tables = ["5.2"] + (["5.3"] if speed == 2.5 else [])
        cases.append(
            {
                "case_id": f"t5_2_speed_{_speed_label(speed)}",
                "case_group": "stable_speed",
                "case_role": "nominal_reference",
                "comparison_reference_case_id": None,
                "paper_tables": tables,
                "standard_speed_mps": speed,
                "actual_speed_mps": speed,
                "deviation_percent": 0,
                "fault_line_ids": [],
                "seed_edges": [],
                "mapping_evidence": "NOT_APPLICABLE",
                "paper_reported": dict(paper),
                "protocol_fidelity": "MATCHED_SPEED_RECONSTRUCTION_ON_ACTIVE_S4",
            }
        )
    for (standard_speed, deviation), paper in PAPER_T5_4.items():
        actual_speed = standard_speed * (1.0 - deviation / 100.0)
        cases.append(
            {
                "case_id": (
                    f"t5_4_std_{_speed_label(standard_speed)}_dev_{deviation}"
                ),
                "case_group": "speed_deviation",
                "case_role": "degraded_actual_dual_speed_reconstruction",
                "comparison_reference_case_id": (
                    f"t5_2_speed_{_speed_label(standard_speed)}"
                ),
                "paper_tables": ["5.4"],
                "standard_speed_mps": standard_speed,
                "actual_speed_mps": actual_speed,
                "deviation_percent": deviation,
                "fault_line_ids": [],
                "seed_edges": [],
                "mapping_evidence": "NOT_APPLICABLE",
                "paper_reported": dict(paper),
                "protocol_fidelity": (
                    "RECONSTRUCTION_STANDARD_HEURISTIC_ACTUAL_EDGE_TIME_"
                    "NOT_THE_ORIGINAL_DEVIATION_SIMULATOR"
                ),
            }
        )
    for suffix, line_ids, affected, success in PAPER_T5_5:
        evidence = [PAPER_LINE_MAPPING_EVIDENCE[line_id] for line_id in line_ids]
        global_seed_edges = [
            list(PAPER_LINE_SEED_EDGES[value]) for value in line_ids
        ]
        override = PAPER_T5_5_CASE_SEED_EDGE_OVERRIDES.get(suffix)
        case = {
                "case_id": f"t5_5_fault_{suffix}",
                "case_group": "all_day_line_interruption",
                "case_role": "all_day_seed_edge_fault_reconstruction",
                "comparison_reference_case_id": "t5_2_speed_2p5",
                "paper_tables": ["5.5"],
                "standard_speed_mps": 2.5,
                "actual_speed_mps": 2.5,
                "deviation_percent": 0,
                "fault_line_ids": list(line_ids),
                "seed_edges": (
                    [list(edge) for edge in override]
                    if override is not None
                    else global_seed_edges
                ),
                "mapping_evidence": (
                    "ARCHIVED_CASE_SPECIFIC_LABEL_PROBE_SOURCE_PROTOCOL_"
                    "UNRESOLVED"
                    if override is not None
                    else "STRONG" if all(value == "STRONG" for value in evidence)
                    else "CONTAINS_RECONSTRUCTION"
                ),
                "line_mapping_evidence": {
                    str(line_id): PAPER_LINE_MAPPING_EVIDENCE[line_id]
                    for line_id in line_ids
                },
                "paper_reported": {
                    "affected_conveyor_count": affected,
                    "success_rate": success,
                },
                "protocol_fidelity": (
                    "PROTOCOL_MISMATCH_ARCHIVED_WORKBOOK_LABEL_PROBE_"
                    "FRESH_VERDICT_NOT_ADMISSIBLE"
                    if override is not None
                    else "SEED_EDGE_ALL_DAY_RECONSTRUCTION_NOT_A_CLAIM_OF_"
                    "EXACT_AFFECTED_CONVEYOR_CASCADE"
                ),
            }
        if override is not None:
            case["case_specific_seed_edge_override"] = {
                "source": "archived_workbook_sheet_33-44,46-36",
                "global_line_seed_edges": global_seed_edges,
                "applies_only_to_scenario": suffix,
                "changes_global_line_mapping": False,
                "fresh_reporting_status": (
                    "ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED"
                ),
                "fresh_hca_probe_canonical_complete_raw_bags": 8_013,
                "archived_workbook_cached_raw_bags": 13_939,
            }
        cases.append(case)
    return cases


def case_by_id(case_id: str) -> dict[str, Any]:
    for value in paper_cases():
        if value["case_id"] == case_id:
            return value
    raise PaperExperimentError(f"unknown paper case: {case_id}")


def default_release_csv_for_case(case_id: str) -> Path:
    standard_speed = float(case_by_id(case_id)["standard_speed_mps"])
    try:
        return SPEED_RELEASE_CSV[standard_speed]
    except KeyError as exc:
        raise PaperExperimentError(
            f"no matched HCA release trace for standard speed {standard_speed:g}"
        ) from exc


def build_speed_graph(
    standard_speed_mps: float,
    actual_speed_mps: float,
) -> tuple[list[Any], list[Any], list[list[float]], dict[str, Any]]:
    """Use actual speed for physical edges and standard speed for S4 potential."""

    if standard_speed_mps <= 0.0 or actual_speed_mps <= 0.0:
        raise PaperExperimentError("standard and actual speeds must be positive")
    graph = copy.deepcopy(canonical_map_data())
    for edge in graph["edges"]:
        edge["speed"] = float(actual_speed_mps)
    graph["heuristic_time"] = g6.recompute_heuristic_time(
        graph, float(standard_speed_mps)
    )
    nodes, edges, heuristic = g6.graph_records_from_map(graph)
    return nodes, edges, heuristic, {
        "topology": "protected_map2_54_nodes_69_edges",
        "physical_edge_speed_mps": float(actual_speed_mps),
        "heuristic_speed_mps": float(standard_speed_mps),
        "edge_travel_time": "length/actual_speed_mps",
        "heuristic_reconstruction": (
            "directed_shortest_travel_time_using_standard_speed_mps"
        ),
    }


def all_day_fault_windows(
    case: Mapping[str, Any],
    input_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[tuple[int, int, float, float, float, bool]], dict[str, Any]]:
    """Activate seed-edge faults before the first release and repair after the day."""

    edges = [tuple(int(part) for part in value) for value in case["seed_edges"]]
    if not edges:
        return [], {"mode": "no_fault", "windows": []}
    first_release = min(float(row["pass_time"]) for row in input_rows)
    horizon = max(
        max(float(row["pass_time"]) for row in input_rows),
        max(float(row["std"]) for row in input_rows),
    )
    fault_time = first_release - 1.0
    repair_time = horizon + ALL_DAY_REPAIR_MARGIN_SECONDS
    windows = [
        (start, end, fault_time, repair_time, 0.0, False)
        for start, end in edges
    ]
    return windows, {
        "mode": "all_day_seed_edge_fault_windows",
        "fault_before_first_release_seconds": 1.0,
        "fault_time": fault_time,
        "repair_time": repair_time,
        "runtime_limit_semantics": (
            "explicit_max_simulation_time_aligned_to_fresh_Java_full_window"
        ),
        "fixed_runtime_limit": TABLE_5_5_FIXED_HORIZON,
        "max_events": TABLE_5_5_MAX_EVENTS,
        "max_events_semantics": (
            "operational_ceiling_only; a censored run is not a completion result"
        ),
        "fixed_runtime_limit_source": (
            "LegacyIcsNoFaultWindowBenchmark_full_start_epoch_8260_plus_"
            "max_epochs_90000_minus_1"
        ),
        "repair_is_after_fixed_runtime_limit": (
            repair_time > TABLE_5_5_FIXED_HORIZON
        ),
        "repair_event_expected_before_fixed_horizon": False,
        "repair_margin_after_release_or_std_horizon_seconds": (
            ALL_DAY_REPAIR_MARGIN_SECONDS
        ),
        "immediate_local_notification": True,
        "windows": [list(value) for value in windows],
    }


def topology_reachable_raw_bag_upper_bound(
    input_rows: Sequence[Mapping[str, Any]],
    edge_records: Sequence[Sequence[Any]],
    fault_edges: Sequence[Sequence[int]],
) -> dict[str, Any]:
    """Count raw bags whose every selected leg remains directed-reachable.

    Reachability is necessary but not sufficient for runtime completion, so
    this count is a strict upper bound.  Removing the seed edges is the only
    graph mutation; congestion, timing, and controller behavior are excluded.
    """

    removed = {(int(edge[0]), int(edge[1])) for edge in fault_edges}
    adjacency: dict[int, set[int]] = {}
    for edge in edge_records:
        start, end = int(edge[0]), int(edge[1])
        if (start, end) not in removed:
            adjacency.setdefault(start, set()).add(end)
    starts = {int(row["start"]) for row in input_rows}
    reachable_by_start: dict[int, set[int]] = {}
    for start in starts:
        reachable = {start}
        frontier = [start]
        while frontier:
            node = frontier.pop()
            for nxt in adjacency.get(node, ()):
                if nxt not in reachable:
                    reachable.add(nxt)
                    frontier.append(nxt)
        reachable_by_start[start] = reachable

    groups: dict[int, list[Mapping[str, Any]]] = {}
    for row in input_rows:
        groups.setdefault(int(row["task_id"]), []).append(row)
    reachable_segments = 0
    reachable_raw_bags = 0
    for rows in groups.values():
        legs = [
            int(row["goal"]) in reachable_by_start[int(row["start"])]
            for row in rows
        ]
        reachable_segments += sum(legs)
        reachable_raw_bags += all(legs)
    return {
        "method": "directed_BFS_after_removing_seed_edges_all_selected_legs_required",
        "removed_seed_edges": [list(edge) for edge in sorted(removed)],
        "selected_segment_count": len(input_rows),
        "selected_raw_bag_count": len(groups),
        "reachable_segment_count": reachable_segments,
        "topology_reachable_raw_bag_upper_bound": reachable_raw_bags,
        "topology_unreachable_raw_bag_count": len(groups) - reachable_raw_bags,
        "bound_semantics": (
            "necessary_reachability_upper_bound_not_a_runtime_completion_prediction"
        ),
    }


def _describe(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "seconds": {
                name: None for name in ("min", "p50", "mean", "p95", "p99", "max")
            },
            "minutes": {
                name: None for name in ("min", "p50", "mean", "p95", "p99", "max")
            },
        }
    seconds = {
        "min": min(values),
        "p50": g24._quantile(values, 0.50),
        "mean": statistics.fmean(values),
        "p95": g24._quantile(values, 0.95),
        "p99": g24._quantile(values, 0.99),
        "max": max(values),
    }
    return {
        "count": len(values),
        "seconds": seconds,
        "minutes": {name: value / 60.0 for name, value in seconds.items()},
    }


def summarize_paper_outcome(
    input_rows: Sequence[Mapping[str, Any]],
    segment_results: Sequence[Mapping[str, Any]],
    *,
    total_raw_bags: int = PAPER_DAY_RAW_BAGS,
) -> dict[str, Any]:
    """Compute paper-style raw-bag THT and three explicit success definitions."""

    if total_raw_bags <= 0:
        raise PaperExperimentError("raw-bag denominator must be positive")
    raw = harness.aggregate_raw_bag_timings(
        input_rows,
        segment_results,
        allow_release_before_original_entry=True,
    )
    inputs_by_task: dict[int, list[Mapping[str, Any]]] = {}
    for row in input_rows:
        inputs_by_task.setdefault(int(row["task_id"]), []).append(row)
    results_by_segment = {
        str(row.get("segment_id", "")): row for row in segment_results
    }

    complete_rows = [row for row in raw if bool(row["complete"])]
    network_tth = [float(row["network_time_seconds"]) for row in complete_rows]
    finish_by_task: dict[int, float] = {}
    std_by_task: dict[int, float] = {}
    for row in complete_rows:
        task_id = int(row["task_id"])
        source_rows = inputs_by_task[task_id]
        std_by_task[task_id] = min(float(value["std"]) for value in source_rows)
        finish_by_task[task_id] = max(
            float(results_by_segment[str(value["segment_id"])]["finish_time"])
            for value in source_rows
        )

    std_success = sum(
        finish_by_task[task_id] <= std_by_task[task_id]
        for task_id in finish_by_task
    )
    literal_success = sum(
        finish_by_task[task_id]
        <= std_by_task[task_id] - LITERAL_EARLY_MARGIN_SECONDS
        for task_id in finish_by_task
    )
    completed = len(complete_rows)
    return {
        "selected_raw_bag_count": len(raw),
        "completed_raw_bag_count": completed,
        "paper_raw_bag_tth": {
            "denominator": "sum_over_segments(finish_time-admitted_time)",
            "scope": "complete_raw_bags_only",
            "distribution": _describe(network_tth),
        },
        "success": {
            "denominator_raw_bags": total_raw_bags,
            "primary_completed_raw_bags": {
                "count": completed,
                "rate": completed / total_raw_bags,
                "definition": "all_selected_segments_completed",
            },
            "finish_le_std": {
                "count": std_success,
                "rate": std_success / total_raw_bags,
                "definition": "complete_raw_bag_and_max_segment_finish_time<=STD",
            },
            "finish_le_std_minus_2700_literal": {
                "count": literal_success,
                "rate": literal_success / total_raw_bags,
                "definition": (
                    "complete_raw_bag_and_max_segment_finish_time<=STD-2700_seconds"
                ),
            },
        },
    }


def _full_workload_gate(prefix: harness.InputPrefix) -> dict[str, bool]:
    gates = {
        "segment_count_is_43603": len(prefix.rows) == PAPER_DAY_SEGMENTS,
        "raw_bag_count_is_28506": prefix.raw_bag_count == PAPER_DAY_RAW_BAGS,
    }
    if not all(gates.values()):
        raise PaperExperimentError(f"full paper workload gate failed: {gates}")
    return gates


def build_s4_request(
    case: Mapping[str, Any],
    prefix: harness.InputPrefix,
    *,
    binary: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build the active S4/J2/E2 request with only paper-case inputs changed."""

    nodes, edges, heuristic, speed_protocol = build_speed_graph(
        float(case["standard_speed_mps"]),
        float(case["actual_speed_mps"]),
    )
    faults, fault_protocol = all_day_fault_windows(case, prefix.rows)
    request = g20.build_native_request(
        prefix.rows,
        scale=1,
        policy="E2",
        binary=binary,
        root=ROOT,
        bounded_wall_seconds=60.0,
        check_events=65_536,
    )
    request.update(
        node_records=nodes,
        edge_records=edges,
        heuristic_time=heuristic,
        bag_records=harness.binding_bag_records(prefix),
        fault_windows=faults,
        scenario=f"g4irsf26_{case['case_id']}",
        summary_only=False,
        trace_limit=0,
        event_trace_limit=0,
    )
    if faults:
        request["max_simulation_time"] = TABLE_5_5_FIXED_HORIZON
        request["max_events"] = TABLE_5_5_MAX_EVENTS
    return request, {"speed": speed_protocol, "fault": fault_protocol}


def _runtime_echo_gates(summary: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "active_s4_scorer": summary.get("scorer_mode") == "S4_queue_aware_rule_only",
        "active_j2_timing": (
            summary.get("merge_grant_timing_mode") == "jit_fair_aging_deadline"
        ),
        "active_e2_hotpath": summary.get("g4irsf20_event_hotpath_policy") == "E2",
    }


def _fixed_horizon_fault_safety(
    summary: Mapping[str, Any],
    *,
    requested: int,
    seed_fault_count: int,
) -> dict[str, Any]:
    """Admit a fault run whose remaining work is failed at the fixed horizon.

    A temporal repair event is deliberately scheduled beyond the explicit
    fresh-Java-aligned endpoint (98,259 s).  Therefore
    ``time_limit_reached`` and terminal failures are experiment outcomes for
    Table 5.5, not by themselves safety violations.  Every other G24
    hard-safety field remains strict.
    """

    allowed_nonzero = {"failed_count", "unresolved_deadlock_count"}
    required_zero = tuple(
        name for name in g24.HARD_SAFETY_ZERO_FIELDS if name not in allowed_nonzero
    )
    required_false = tuple(
        name for name in g24.HARD_SAFETY_FALSE_FIELDS if name != "time_limit_reached"
    )
    required = (
        "completed_count",
        "failed_count",
        "unresolved_deadlock_count",
        "time_limit_reached",
        "fault_event_count",
        "repair_event_count",
        *required_zero,
        *required_false,
    )
    missing = sorted({name for name in required if name not in summary})

    def number(name: str) -> float | None:
        value = summary.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        value = float(value)
        return value if math.isfinite(value) else None

    completed = number("completed_count")
    failed = number("failed_count")
    unresolved = number("unresolved_deadlock_count")
    fault_events = number("fault_event_count")
    repair_events = number("repair_event_count")
    gates = {
        "all_required_fields_present": not missing,
        "completed_plus_failed_equals_requested": (
            completed is not None
            and failed is not None
            and completed + failed == float(requested)
        ),
        "unresolved_deadlock_count_finite_nonnegative": (
            unresolved is not None and unresolved >= 0.0
        ),
        "fixed_time_horizon_reached": summary.get("time_limit_reached") is True,
        "fault_event_count_equals_seed_count": (
            fault_events == float(seed_fault_count)
        ),
        "repair_event_not_processed": repair_events == 0.0,
        **{f"{name}_zero": number(name) == 0.0 for name in required_zero},
        **{f"{name}_false": summary.get(name) is False for name in required_false},
    }
    return {
        "mode": "TABLE_5_5_FIXED_HORIZON_SAFETY",
        "pass": all(gates.values()),
        "gates": gates,
        "missing_fields": missing,
        "allowed_business_outcome_fields": [
            "failed_count",
            "time_limit_reached",
        ],
        "operational_diagnostic_fields": ["unresolved_deadlock_count"],
        "unresolved_deadlock_semantics": (
            "finite_nonnegative_event_or_structure_diagnostic_not_failed_bag_count"
        ),
        "business_failures_counted_as_safety_failures": False,
        "terminal_accounting": {
            "requested": requested,
            "completed": int(completed) if completed is not None else None,
            "failed": int(failed) if failed is not None else None,
            "unresolved_deadlock": int(unresolved) if unresolved is not None else None,
        },
    }


def _topology_saturated_fault_safety(
    summary: Mapping[str, Any],
    *,
    requested: int,
    seed_fault_count: int,
    completed_raw_bags: int,
    topology_upper_bound: int,
) -> dict[str, Any]:
    """Admit only a Table-5.5 primary rate saturated at a proven graph bound."""

    allowed_nonzero = {"failed_count", "unresolved_deadlock_count"}
    required_zero = tuple(
        name for name in g24.HARD_SAFETY_ZERO_FIELDS if name not in allowed_nonzero
    )
    required_false = tuple(
        name
        for name in g24.HARD_SAFETY_FALSE_FIELDS
        if name not in {"event_limit_reached", "time_limit_reached"}
    )
    required = (
        "completed_count",
        "failed_count",
        "unresolved_deadlock_count",
        "event_limit_reached",
        "time_limit_reached",
        "fault_event_count",
        "repair_event_count",
        *required_zero,
        *required_false,
    )
    missing = sorted({name for name in required if name not in summary})

    def number(name: str) -> float | None:
        value = summary.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        value = float(value)
        return value if math.isfinite(value) else None

    completed = number("completed_count")
    failed = number("failed_count")
    unresolved = number("unresolved_deadlock_count")
    gates = {
        "all_required_fields_present": not missing,
        "completed_plus_failed_equals_requested": (
            completed is not None
            and failed is not None
            and completed + failed == float(requested)
        ),
        "unresolved_deadlock_count_finite_nonnegative": (
            unresolved is not None and unresolved >= 0.0
        ),
        "event_limit_reached_as_censor": summary.get("event_limit_reached") is True,
        "time_limit_reached_is_boolean": isinstance(
            summary.get("time_limit_reached"), bool
        ),
        "topology_upper_bound_in_population": (
            0 <= topology_upper_bound <= PAPER_DAY_RAW_BAGS
        ),
        "completed_raw_bags_equals_topology_upper_bound": (
            completed_raw_bags == topology_upper_bound
        ),
        "fault_event_count_equals_seed_count": (
            number("fault_event_count") == float(seed_fault_count)
        ),
        "repair_event_not_processed": number("repair_event_count") == 0.0,
        **{f"{name}_zero": number(name) == 0.0 for name in required_zero},
        **{f"{name}_false": summary.get(name) is False for name in required_false},
    }
    return {
        "mode": "TABLE_5_5_TOPOLOGY_SATURATION_EVIDENCE",
        "pass": all(gates.values()),
        "gates": gates,
        "missing_fields": missing,
        "operational_diagnostic_fields": ["unresolved_deadlock_count"],
        "allowed_censor_fields": [
            "event_limit_reached",
            "time_limit_reached",
            "failed_count",
        ],
        "terminal_accounting": {
            "requested": requested,
            "completed": int(completed) if completed is not None else None,
            "failed": int(failed) if failed is not None else None,
            "unresolved_deadlock": int(unresolved) if unresolved is not None else None,
        },
        "topology_accounting": {
            "completed_raw_bags": completed_raw_bags,
            "topology_reachable_raw_bag_upper_bound": topology_upper_bound,
            "saturated": completed_raw_bags == topology_upper_bound,
        },
        "claim_scope": {
            "table_5_5_primary_completed_raw_bag_rate": True,
            "fixed_horizon_completion": False,
            "full_horizon_timing": False,
            "paper_raw_bag_tth_distribution": False,
            "deadline_success_rates": False,
        },
        "classification": "RECONSTRUCTED_TOPOLOGY_PROVEN_NOT_EXACT_FIXED_HORIZON",
    }


def execute_case_worker(
    case_id: str,
    *,
    binary: Path,
    release_csv: Path,
) -> dict[str, Any]:
    """Execute one full case in the current (already isolated) process."""

    case = case_by_id(case_id)
    supplied_release_csv = release_csv.resolve(strict=True)
    registered_release_csv = default_release_csv_for_case(case_id).resolve(strict=True)
    if supplied_release_csv != registered_release_csv:
        raise PaperExperimentError(
            f"case {case_id} requires registered release trace "
            f"{registered_release_csv.relative_to(ROOT).as_posix()}, got "
            f"{supplied_release_csv}"
        )
    canonical = harness.load_input_prefix(harness.FULL_SIZE_SEGMENTS, root=ROOT)
    workload_gates = _full_workload_gate(canonical)
    prefix, alignment = g24.apply_exact_hca_releases(
        canonical, registered_release_csv
    )
    if int(alignment["aligned_segment_count"]) != PAPER_DAY_SEGMENTS:
        raise PaperExperimentError("exact HCA lifecycle did not align all 43,603 segments")
    registered_source = registered_release_csv.relative_to(ROOT).as_posix()
    if alignment.get("source") != registered_source:
        raise PaperExperimentError(
            "exact release alignment did not preserve the registered source: "
            f"{alignment.get('source')!r} != {registered_source!r}"
        )
    request, reconstruction = build_s4_request(
        case, prefix, binary=binary.resolve(strict=True)
    )
    topology_reachability = (
        topology_reachable_raw_bag_upper_bound(
            prefix.rows,
            request["edge_records"],
            case["seed_edges"],
        )
        if case["seed_edges"]
        else None
    )
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    if not isinstance(payload, Mapping):
        raise PaperExperimentError("native S4 result is not an object")
    summary = payload.get("summary")
    bags = payload.get("bags")
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise PaperExperimentError("native S4 result lacks summary or bag rows")
    if any(not isinstance(row, Mapping) for row in bags):
        raise PaperExperimentError("native S4 bag payload contains a non-object")

    outcome = summarize_paper_outcome(prefix.rows, bags)
    strict_safety = g24._strict_s4_safety(summary, PAPER_DAY_SEGMENTS)
    echo_gates = _runtime_echo_gates(summary)
    is_fault_case = bool(case["seed_edges"])
    fixed_horizon_safety = (
        _fixed_horizon_fault_safety(
            summary,
            requested=PAPER_DAY_SEGMENTS,
            seed_fault_count=len(case["seed_edges"]),
        )
        if is_fault_case
        else None
    )
    topology_saturation_safety = (
        _topology_saturated_fault_safety(
            summary,
            requested=PAPER_DAY_SEGMENTS,
            seed_fault_count=len(case["seed_edges"]),
            completed_raw_bags=int(outcome["completed_raw_bag_count"]),
            topology_upper_bound=int(
                topology_reachability["topology_reachable_raw_bag_upper_bound"]
            ),
        )
        if is_fault_case and topology_reachability is not None
        else None
    )
    if not is_fault_case:
        selected_safety = strict_safety
    elif fixed_horizon_safety["pass"]:
        selected_safety = fixed_horizon_safety
    else:
        selected_safety = topology_saturation_safety
    admitted = bool(selected_safety["pass"]) and all(echo_gates.values())
    status = (
        "COMPLETE_TOPOLOGY_SATURATED"
        if admitted and selected_safety is topology_saturation_safety
        else "COMPLETE_FIXED_HORIZON"
        if admitted and is_fault_case
        else ("COMPLETE" if admitted else "FAILED_STRICT_S4_GATE")
    )
    failed_raw_bags = PAPER_DAY_RAW_BAGS - int(outcome["completed_raw_bag_count"])
    return {
        "schema": CASE_SCHEMA,
        "status": status,
        "case": dict(case),
        "protocol": {
            "framework": "active_decentralized_A0_S4_J2_E2",
            "input": "protected_original_day_exact_file_order",
            "segment_count": PAPER_DAY_SEGMENTS,
            "raw_bag_count": PAPER_DAY_RAW_BAGS,
            "full_workload_gates": workload_gates,
            "release_semantics": "exact_G24_HCA_segment_lifecycle_release_epoch",
            "exact_fresh_status": "EXACT_G24_LIFECYCLE_ALIGNED",
            "exact_hca_release_alignment": alignment,
            "reconstruction": reconstruction,
            "paper_raw_bag_tth_denominator": (
                "sum_over_segments(finish_time-admitted_time)"
            ),
            "table_5_4_claim_boundary": (
                "RECONSTRUCTION_NOT_THE_ORIGINAL_DEVIATION_SIMULATOR"
            ),
            "table_5_5_claim_boundary": (
                "SEED_EDGE_MAPPING_WITH_EXPLICIT_EVIDENCE_NOT_EXACT_CASCADE"
            ),
        },
        "outcome": {
            "requested_segment_count": PAPER_DAY_SEGMENTS,
            "runtime_completed_segment_count": int(summary.get("completed_count", 0)),
            "runtime_failed_segment_count": int(summary.get("failed_count", 0)),
            "business_failed_raw_bag_count": failed_raw_bags,
            "business_failure_is_safety_failure": False,
            "business_and_safety_axes_are_separate": True,
            "topology_reachability": topology_reachability,
            "topology_reachable_raw_bag_upper_bound": (
                topology_reachability["topology_reachable_raw_bag_upper_bound"]
                if topology_reachability is not None
                else None
            ),
            "primary_success_topology_saturated": (
                status == "COMPLETE_TOPOLOGY_SATURATED"
            ),
            "secondary_metrics_censored_by_event_limit": (
                status == "COMPLETE_TOPOLOGY_SATURATED"
            ),
            "admitted_claim_scope": (
                "TABLE_5_5_PRIMARY_SUCCESS_RATE_ONLY"
                if status == "COMPLETE_TOPOLOGY_SATURATED"
                else "FULL_CASE_OUTCOME"
                if admitted
                else "NO_ADMITTED_CLAIM"
            ),
            **outcome,
        },
        "safety": {
            "admission": {
                "mode": selected_safety["mode"] if is_fault_case else "G24_STRICT_S4",
                "pass": admitted,
                "selected_safety_pass": bool(selected_safety["pass"]),
                "runtime_echo_pass": all(echo_gates.values()),
            },
            "strict_s4": strict_safety,
            "fixed_horizon_fault": fixed_horizon_safety,
            "topology_saturation_fault": topology_saturation_safety,
            "runtime_echo_gates": echo_gates,
        },
        "runtime": {
            "wall_seconds": wall_seconds,
            "cpu_seconds": cpu_seconds,
            "event_count": int(summary.get("event_count", 0)),
            "decision_count": int(summary.get("decision_count", 0)),
            "fault_event_count": int(summary.get("fault_event_count", 0)),
            "repair_event_count": int(summary.get("repair_event_count", 0)),
        },
    }


def _rooted(path: Path) -> Path:
    return path if path.is_absolute() else ROOT / path


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _load_resumable_case(path: Path, case_id: str) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        isinstance(value, dict)
        and value.get("schema") == CASE_SCHEMA
        and value.get("status") in ADMITTED_CASE_STATUSES
        and isinstance(value.get("case"), Mapping)
        and dict(value["case"]) == case_by_id(case_id)
    ):
        return value
    return None


def _worker_command(
    case_id: str,
    *,
    binary: Path,
    release_csv: Path,
    output: Path,
) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "_worker",
        "--case-id",
        case_id,
        "--binary",
        str(binary.resolve()),
        "--release-csv",
        str(release_csv.resolve()),
        "--output",
        str(output.resolve()),
    ]


def run_case_subprocess(
    case_id: str,
    *,
    binary: Path,
    release_csv: Path,
    output_dir: Path = DEFAULT_CASE_DIR,
    force: bool = False,
    timeout_seconds: float = 0.0,
) -> tuple[dict[str, Any], bool]:
    """Run one case in a fresh process, or resume its completed artifact."""

    case_by_id(case_id)
    destination = _rooted(output_dir) / f"{case_id}.json"
    if not force:
        resumed = _load_resumable_case(destination, case_id)
        if resumed is not None:
            return resumed, True
    command = _worker_command(
        case_id,
        binary=binary,
        release_csv=release_csv,
        output=destination,
    )
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=(timeout_seconds if timeout_seconds > 0.0 else None),
        )
    except subprocess.TimeoutExpired as exc:
        raise PaperExperimentError(
            f"case {case_id} exceeded {timeout_seconds:g} seconds"
        ) from exc
    # Exit 2 is a fully persisted scientific outcome that failed a strict S4
    # gate; it is not an orchestration crash and must remain aggregatable.
    if completed.returncode not in (0, 2):
        raise PaperExperimentError(
            f"case {case_id} worker failed: {completed.stderr or completed.stdout}"
        )
    if not destination.is_file():
        raise PaperExperimentError(f"case {case_id} worker wrote no artifact")
    value = json.loads(destination.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema") != CASE_SCHEMA:
        raise PaperExperimentError(f"case {case_id} worker artifact is invalid")
    return value, False


def _case_row(value: Mapping[str, Any]) -> dict[str, Any]:
    case = value.get("case", {})
    outcome = value.get("outcome", {})
    tth = outcome.get("paper_raw_bag_tth", {}).get("distribution", {})
    minutes = tth.get("minutes", {})
    success = outcome.get("success", {})
    return {
        "case_id": case.get("case_id"),
        "case_group": case.get("case_group"),
        "case_role": case.get("case_role"),
        "comparison_reference_case_id": case.get("comparison_reference_case_id"),
        "status": value.get("status"),
        "standard_speed_mps": case.get("standard_speed_mps"),
        "actual_speed_mps": case.get("actual_speed_mps"),
        "deviation_percent": case.get("deviation_percent"),
        "fault_line_ids": case.get("fault_line_ids"),
        "seed_edges": case.get("seed_edges"),
        "mapping_evidence": case.get("mapping_evidence"),
        "protocol_fidelity": case.get("protocol_fidelity"),
        "paper_reported": case.get("paper_reported"),
        "exact_fresh_status": value.get("protocol", {}).get("exact_fresh_status"),
        "completed_segments": outcome.get("runtime_completed_segment_count"),
        "completed_raw_bags": outcome.get("completed_raw_bag_count"),
        "tth_min_minutes": minutes.get("min"),
        "tth_mean_minutes": minutes.get("mean"),
        "tth_p95_minutes": minutes.get("p95"),
        "tth_p99_minutes": minutes.get("p99"),
        "tth_max_minutes": minutes.get("max"),
        "completed_raw_bag_rate": success.get("primary_completed_raw_bags", {}).get("rate"),
        "finish_le_std_rate": success.get("finish_le_std", {}).get("rate"),
        "finish_le_std_minus_2700_rate": success.get(
            "finish_le_std_minus_2700_literal", {}
        ).get("rate"),
        "strict_s4_safety_pass": value.get("safety", {}).get("strict_s4", {}).get("pass"),
        "admission_safety_pass": value.get("safety", {}).get("admission", {}).get("pass"),
        "safety_admission_mode": value.get("safety", {}).get("admission", {}).get("mode"),
        "business_failed_raw_bags": outcome.get("business_failed_raw_bag_count"),
        "business_failure_is_safety_failure": outcome.get(
            "business_failure_is_safety_failure"
        ),
        "topology_reachable_raw_bag_upper_bound": outcome.get(
            "topology_reachable_raw_bag_upper_bound"
        ),
        "primary_success_topology_saturated": outcome.get(
            "primary_success_topology_saturated"
        ),
        "secondary_metrics_censored_by_event_limit": outcome.get(
            "secondary_metrics_censored_by_event_limit"
        ),
        "admitted_claim_scope": outcome.get("admitted_claim_scope"),
        "topology_saturation_safety_pass": (
            value.get("safety", {}).get("topology_saturation_fault") or {}
        ).get("pass"),
        "wall_seconds": value.get("runtime", {}).get("wall_seconds"),
    }


def aggregate_case_artifacts(output_dir: Path = DEFAULT_CASE_DIR) -> dict[str, Any]:
    """Read the frozen matrix without executing missing cases."""

    root = _rooted(output_dir)
    expected = paper_cases()
    archived_only = [
        case
        for case in expected
        if (
            case.get("case_specific_seed_edge_override") or {}
        ).get("fresh_reporting_status")
        == "ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED"
    ]
    archived_only_ids = [str(case["case_id"]) for case in archived_only]
    executable_expected = [
        case for case in expected if str(case["case_id"]) not in archived_only_ids
    ]
    results: list[dict[str, Any]] = []
    missing: list[str] = []
    invalid: list[str] = []
    for case in executable_expected:
        case_id = str(case["case_id"])
        path = root / f"{case_id}.json"
        if not path.is_file():
            missing.append(case_id)
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            invalid.append(case_id)
            continue
        if (
            not isinstance(value, dict)
            or value.get("schema") != CASE_SCHEMA
            or not isinstance(value.get("case"), Mapping)
            or dict(value["case"]) != case
        ):
            invalid.append(case_id)
            continue
        results.append(value)
        if value.get("status") not in ADMITTED_CASE_STATUSES:
            invalid.append(case_id)
    rows = [_case_row(value) for value in results]
    rows_by_id = {str(row["case_id"]): row for row in rows}
    for row in rows:
        reference_id = row.get("comparison_reference_case_id")
        reference = rows_by_id.get(str(reference_id)) if reference_id else None
        reference_mean = reference.get("tth_mean_minutes") if reference else None
        current_mean = row.get("tth_mean_minutes")
        row["reference_tth_mean_minutes"] = reference_mean
        row["tth_mean_delta_vs_reference_minutes"] = (
            float(current_mean) - float(reference_mean)
            if isinstance(current_mean, (int, float))
            and isinstance(reference_mean, (int, float))
            else None
        )
    aggregate_status = (
        "PARTIAL_OR_FAILED"
        if missing or invalid
        else "COMPLETE_WITH_ARCHIVED_ONLY_GAP"
        if archived_only_ids
        else "COMPLETE"
    )
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": aggregate_status,
        "archived_only_not_executed_case_ids": archived_only_ids,
        "executable_expected_case_count": len(executable_expected),
        "protocol": {
            "expected_case_count": len(expected),
            "stable_speed_case_count": 4,
            "speed_deviation_case_count": 12,
            "all_day_fault_case_count": 16,
            "segment_count_per_case": PAPER_DAY_SEGMENTS,
            "raw_bag_count_per_case": PAPER_DAY_RAW_BAGS,
            "active_policy": "A0_S4_J2_E2",
            "paper_raw_bag_tth_denominator": (
                "sum_over_segments(finish_time-admitted_time)"
            ),
            "success_denominators": [
                "completed_raw_bags/28506",
                "max_segment_finish<=STD",
                "max_segment_finish<=STD-2700_seconds_literal",
            ],
            "topology_saturation_status": {
                "status": "COMPLETE_TOPOLOGY_SATURATED",
                "classification": "RECONSTRUCTED_TOPOLOGY_PROVEN",
                "claim_scope": "TABLE_5_5_PRIMARY_SUCCESS_RATE_ONLY",
                "secondary_timing_metrics_censored": True,
            },
            "table_5_3_reported_baseline": {
                "dispersed_heuristic_minutes": {"min": 3.56, "mean": 4.43, "max": 8.62},
                "iot_drpa_minutes": {"min": 3.13, "mean": 3.96, "max": 5.98},
                "executable_dispersed_baseline": False,
            },
        },
        "missing_case_ids": missing,
        "invalid_or_failed_case_ids": sorted(set(invalid)),
        "loaded_artifact_count": len(results),
        "completed_artifact_count": sum(
            value.get("status") in ADMITTED_CASE_STATUSES
            for value in results
        ),
        "rows": rows,
        "cases": results,
    }


def _csv_text(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return ""
    stream = io.StringIO(newline="")
    # Keep one logical newline here.  ``_atomic_text`` applies the host text
    # translation once; the csv module's Windows default would otherwise
    # produce ``\r\r\n`` when the aggregate is generated on Windows.
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (
                    json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list, tuple))
                    else value
                )
                for key, value in row.items()
            }
        )
    return stream.getvalue()


def _manifest() -> dict[str, Any]:
    return {
        "schema": MANIFEST_SCHEMA,
        "execution": "dry_run_only_no_case_started",
        "case_count": len(paper_cases()),
        "default_case_dir": DEFAULT_CASE_DIR.relative_to(ROOT).as_posix(),
        "release_csv_by_standard_speed": {
            f"{speed:g}": path.relative_to(ROOT).as_posix()
            for speed, path in SPEED_RELEASE_CSV.items()
        },
        "cases": paper_cases(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    dry = commands.add_parser("dry-run", help="print the frozen case manifest")
    dry.add_argument("--output-json", type=Path)

    case = commands.add_parser("case", help="run or resume one isolated full case")
    case.add_argument("--case-id", required=True, choices=[value["case_id"] for value in paper_cases()])
    case.add_argument("--binary", type=Path, required=True)
    case.add_argument("--release-csv", type=Path)
    case.add_argument("--output-dir", type=Path, default=DEFAULT_CASE_DIR)
    case.add_argument("--force", action="store_true")
    case.add_argument("--timeout-seconds", type=float, default=0.0)

    aggregate = commands.add_parser("aggregate", help="aggregate existing case artifacts")
    aggregate.add_argument("--output-dir", type=Path, default=DEFAULT_CASE_DIR)
    aggregate.add_argument("--output-json", type=Path, default=DEFAULT_AGGREGATE_JSON)
    aggregate.add_argument("--output-csv", type=Path, default=DEFAULT_AGGREGATE_CSV)

    worker = commands.add_parser("_worker", help=argparse.SUPPRESS)
    worker.add_argument("--case-id", required=True)
    worker.add_argument("--binary", type=Path, required=True)
    worker.add_argument("--release-csv", type=Path, required=True)
    worker.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "dry-run":
        value = _manifest()
        if args.output_json is not None:
            _atomic_json(_rooted(args.output_json), value)
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return 0
    if args.command == "case":
        release_csv = args.release_csv or default_release_csv_for_case(args.case_id)
        value, resumed = run_case_subprocess(
            args.case_id,
            binary=args.binary,
            release_csv=release_csv,
            output_dir=args.output_dir,
            force=args.force,
            timeout_seconds=args.timeout_seconds,
        )
        print(
            json.dumps(
                {
                    "case_id": args.case_id,
                    "status": value.get("status"),
                    "resumed": resumed,
                    "output": str(_rooted(args.output_dir) / f"{args.case_id}.json"),
                },
                ensure_ascii=False,
            )
        )
        return 0 if value.get("status") in ADMITTED_CASE_STATUSES else 2
    if args.command == "aggregate":
        value = aggregate_case_artifacts(args.output_dir)
        _atomic_json(_rooted(args.output_json), value)
        _atomic_text(_rooted(args.output_csv), _csv_text(value["rows"]))
        print(
            json.dumps(
                {
                    "status": value["status"],
                    "completed_artifact_count": value["completed_artifact_count"],
                    "missing_case_count": len(value["missing_case_ids"]),
                    "output_json": str(_rooted(args.output_json)),
                    "output_csv": str(_rooted(args.output_csv)),
                },
                ensure_ascii=False,
            )
        )
        return 0 if value["status"] in SUCCESSFUL_AGGREGATE_STATUSES else 2
    if args.command == "_worker":
        value = execute_case_worker(
            args.case_id,
            binary=args.binary,
            release_csv=args.release_csv,
        )
        _atomic_json(_rooted(args.output), value)
        print(json.dumps({"case_id": args.case_id, "status": value["status"]}))
        return 0 if value["status"] in ADMITTED_CASE_STATUSES else 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
