#!/usr/bin/env python3
"""Evaluate a minimal fault-local scalar extension of the active S4 runtime.

G27 does not construct per-bag routes.  At case start, each node repeatedly
reads only its outgoing edge costs and its neighbours' scalar values until a
per-goal Bellman fixed point is reached.  The resulting structural values are
passed through the existing G24 TD-residual seam.  A source whose local scalar
is unreachable rejects only that segment before native admission; all other
segments run through S4/J2/E2 with FIFO arbitration at each local junction.

This runner is deliberately small.  It reuses the registered G26 paper case,
release, fault-window, outcome, and topology protocols, while declaring a new
G27 admission gate because the native request contains only reachable
segments.  It makes no physical-distribution or learned-policy claim.
"""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from czr005 import cpp_backend
from scripts.eval import g4irsf12_reproducible_harness as harness
from scripts.eval import run_g4irsf24_native_race as g24
from scripts.eval import run_g4irsf26_paper_experiments as g26


SCHEMA = "czr005.g4irsf27.fault_local_values_case.v1"
ADMITTED_STATUS = "COMPLETE_G27_LOCAL_FAULT_VALUES"
ALLOWED_SEGMENT_COUNTS = (512, g26.PAPER_DAY_SEGMENTS)
G27_QUEUE_DISCIPLINE = "fifo"


class FaultValueError(RuntimeError):
    """Raised when a G27 case cannot produce honest local-scalar evidence."""


def _edge_cost(edge: Sequence[Any]) -> float:
    if len(edge) < 4:
        raise FaultValueError("edge record must contain from, to, length, and speed")
    length = float(edge[2])
    speed = float(edge[3])
    if not math.isfinite(length) or not math.isfinite(speed):
        raise FaultValueError("edge length and speed must be finite")
    if length <= 0.0 or speed <= 0.0:
        raise FaultValueError("Bellman propagation requires positive edge weights")
    return length / speed


def local_bellman_fixed_point(
    node_records: Sequence[Sequence[Any]],
    edge_records: Sequence[Sequence[Any]],
    *,
    removed_edges: Sequence[Sequence[int]],
    goals: Sequence[int],
) -> tuple[dict[int, dict[int, float]], dict[str, Any]]:
    """Compute deterministic per-goal values using neighbour-only rounds.

    Updates are synchronous: a node reads the previous round's scalar from
    each surviving outgoing neighbour.  Strictly positive weights imply that
    every shortest walk can be made simple, so at most ``|V|-1`` updating
    rounds plus one quiet convergence round are required even when cycles are
    present.
    """

    nodes = sorted({int(row[0]) for row in node_records})
    if not nodes:
        raise FaultValueError("the graph has no nodes")
    node_set = set(nodes)
    removed = {(int(row[0]), int(row[1])) for row in removed_edges}
    adjacency: dict[int, list[tuple[int, float]]] = {node: [] for node in nodes}
    positive_weights: list[float] = []
    observed_edges: set[tuple[int, int]] = set()
    for edge in edge_records:
        source, target = int(edge[0]), int(edge[1])
        if source not in node_set or target not in node_set:
            raise FaultValueError("edge endpoint is outside the node records")
        key = (source, target)
        if key in observed_edges:
            raise FaultValueError(f"duplicate directed edge: {key}")
        observed_edges.add(key)
        cost = _edge_cost(edge)
        positive_weights.append(cost)
        if key not in removed:
            adjacency[source].append((target, cost))
    missing_removed = removed - observed_edges
    if missing_removed:
        raise FaultValueError(
            f"fault seed edge is absent from the graph: {sorted(missing_removed)}"
        )
    for values in adjacency.values():
        values.sort(key=lambda row: (row[0], row[1]))

    unique_goals = sorted({int(goal) for goal in goals})
    if not unique_goals:
        raise FaultValueError("at least one actual goal is required")
    if any(goal not in node_set for goal in unique_goals):
        raise FaultValueError("an actual goal is outside the node records")

    distances: dict[int, dict[int, float]] = {}
    per_goal: dict[str, Any] = {}
    total_updates = 0
    for goal in unique_goals:
        current = {node: (0.0 if node == goal else math.inf) for node in nodes}
        updates = 0
        converged = False
        rounds = 0
        for round_index in range(1, len(nodes) + 1):
            rounds = round_index
            following = dict(current)
            round_updates = 0
            for node in nodes:
                if node == goal:
                    continue
                candidate = min(
                    (
                        cost + current[neighbour]
                        for neighbour, cost in adjacency[node]
                        if math.isfinite(current[neighbour])
                    ),
                    default=math.inf,
                )
                if candidate < current[node]:
                    following[node] = candidate
                    round_updates += 1
            if round_updates == 0:
                converged = True
                break
            current = following
            updates += round_updates
        if not converged:
            raise FaultValueError(
                f"local Bellman propagation did not converge for goal {goal}"
            )
        distances[goal] = current
        total_updates += updates
        per_goal[str(goal)] = {
            "rounds_including_quiet_fixed_point_round": rounds,
            "updates": updates,
            "reachable_node_count": sum(math.isfinite(value) for value in current.values()),
            "unreachable_node_count": sum(
                not math.isfinite(value) for value in current.values()
            ),
        }

    weight_sum = math.fsum(positive_weights)
    maximum_weight = max(positive_weights)
    return distances, {
        "algorithm": "synchronous_local_out_neighbour_bellman_fixed_point",
        "update_semantics": "node_reads_only_surviving_outgoing_edge_cost_and_neighbour_scalar",
        "node_count": len(nodes),
        "directed_edge_count": len(edge_records),
        "surviving_directed_edge_count": len(edge_records) - len(removed),
        "removed_seed_edges": [list(edge) for edge in sorted(removed)],
        "positive_edge_weight_sum_seconds": weight_sum,
        "maximum_positive_edge_weight_seconds": maximum_weight,
        "per_goal": per_goal,
        "goal_count": len(unique_goals),
        "total_updates": total_updates,
        "maximum_rounds": max(
            row["rounds_including_quiet_fixed_point_round"]
            for row in per_goal.values()
        ),
        "cycle_termination_bound": "at_most_node_count_rounds_with_positive_weights",
    }


def structural_td_artifact(
    node_records: Sequence[Sequence[Any]],
    edge_records: Sequence[Sequence[Any]],
    heuristic_time: Sequence[Sequence[float]],
    distances: Mapping[int, Mapping[int, float]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Encode fault values through the existing compact G24 TD ABI."""

    nodes = sorted({int(row[0]) for row in node_records})
    goals = sorted(int(goal) for goal in distances)
    costs = [_edge_cost(edge) for edge in edge_records]
    positive_weight_sum = math.fsum(costs)
    maximum_weight = max(costs)
    # This is larger than every positive simple-path cost and is entirely
    # derived from the supplied graph, unlike a magic 1e6/1e9 sentinel.
    unreachable_penalty = positive_weight_sum + maximum_weight

    values: list[dict[str, Any]] = []
    unreachable_rows = 0
    for node in nodes:
        if node < 0 or node >= len(heuristic_time):
            raise FaultValueError("node ID cannot index the static heuristic")
        for goal in goals:
            if goal < 0 or goal >= len(heuristic_time[node]):
                raise FaultValueError("goal ID cannot index the static heuristic")
            if node == goal:
                continue
            dynamic = float(distances[goal][node])
            if not math.isfinite(dynamic):
                dynamic = unreachable_penalty
                unreachable_rows += 1
            static = float(heuristic_time[node][goal])
            if not math.isfinite(static):
                raise FaultValueError("static heuristic must be finite")
            values.append(
                {
                    "node": node,
                    "goal": goal,
                    "residual_seconds": dynamic - static,
                    "support": 1,
                }
            )

    artifact = {
        "schema": "czr005.g4irsf24.dlp.v1",
        "mode": "td",
        "beta": 1.0,
        "min_support": 1,
        "margin_seconds": 0.0,
        "detour_allowance_seconds": positive_weight_sum,
        "edge_residuals": [
            {
                "from": int(edge[0]),
                "to": int(edge[1]),
                "residual_seconds": 0.0,
                "support": 1,
            }
            for edge in sorted(edge_records, key=lambda row: (int(row[0]), int(row[1])))
        ],
        "value_residuals": values,
    }
    return artifact, {
        "construction": "structural_fault_distance_minus_static_heuristic",
        "learned_from_runtime_data": False,
        "edge_residual_semantics": "zero_physical_edge_residual",
        "value_residual_semantics": "fault_fixed_point_distance_minus_static_heuristic",
        "unreachable_penalty_seconds": unreachable_penalty,
        "unreachable_penalty_derivation": (
            "sum_all_positive_edge_weights_plus_max_positive_edge_weight"
        ),
        "detour_allowance_derivation": "sum_all_positive_edge_weights",
        "unreachable_value_row_count": unreachable_rows,
        "edge_residual_count": len(artifact["edge_residuals"]),
        "value_residual_count": len(values),
    }


def _runtime_prefix(
    prefix: harness.InputPrefix,
    rows: Sequence[Mapping[str, Any]],
) -> harness.InputPrefix:
    selected = tuple(dict(row) for row in rows)
    tasks = {int(row["task_id"]) for row in selected}
    return replace(
        prefix,
        size_segments=len(selected),
        rows=selected,
        raw_bag_count=len(tasks),
        first_segment_id=str(selected[0]["segment_id"]) if selected else "",
        last_segment_id=str(selected[-1]["segment_id"]) if selected else "",
    )


def prepare_request(
    case: Mapping[str, Any],
    prefix: harness.InputPrefix,
    *,
    binary: Path,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...], dict[str, Any]]:
    """Build G26 S4, enable local FIFO, then add fault-local values if needed."""

    request, reconstruction = g26.build_s4_request(case, prefix, binary=binary)
    request["queue_discipline"] = G27_QUEUE_DISCIPLINE
    active_policy = {
        "choice": "local_junction_fifo_arbitration",
        "queue_discipline": G27_QUEUE_DISCIPLINE,
        "scope": "one_junction_local_queue",
    }
    rejected: tuple[dict[str, Any], ...] = ()
    runtime_rows: tuple[dict[str, Any], ...] = tuple(dict(row) for row in prefix.rows)
    seed_edges = tuple(tuple(int(part) for part in edge) for edge in case["seed_edges"])
    if not seed_edges:
        if "g4irsf24_dlp_artifact" in request:
            raise FaultValueError(
                "no-fault G27 request must leave the fault-value/DLP seam exactly off"
            )
        return request, runtime_rows, rejected, {
            "activation": "FAULT_VALUES_DLP_EXACT_OFF_NO_FAULT_CASE",
            "active_policy": active_policy,
            "source_rejected_unreachable_segment_count": 0,
            "relaxation": {
                "algorithm": "not_run_without_fault",
                "goal_count": 0,
                "total_updates": 0,
                "maximum_rounds": 0,
            },
            "artifact": None,
            "artifact_contract": None,
            "g26_reconstruction": reconstruction,
        }

    goals = sorted({int(row["goal"]) for row in prefix.rows})
    distances, relaxation = local_bellman_fixed_point(
        request["node_records"],
        request["edge_records"],
        removed_edges=seed_edges,
        goals=goals,
    )
    reachable_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for source in prefix.rows:
        row = dict(source)
        distance = distances[int(row["goal"])][int(row["start"])]
        (reachable_rows if math.isfinite(distance) else rejected_rows).append(row)
    runtime_rows = tuple(reachable_rows)
    rejected = tuple(rejected_rows)
    request["bag_records"] = harness.binding_bag_records(
        _runtime_prefix(prefix, runtime_rows)
    )
    artifact, artifact_contract = structural_td_artifact(
        request["node_records"],
        request["edge_records"],
        request["heuristic_time"],
        distances,
    )
    request["g4irsf24_dlp_artifact"] = artifact
    return request, runtime_rows, rejected, {
        "activation": "FAULT_ONLY_STRUCTURAL_TD_ACTIVE",
        "active_policy": active_policy,
        "source_rejected_unreachable_segment_count": len(rejected),
        "runtime_reachable_segment_count": len(runtime_rows),
        "source_admission_semantics": (
            "source_reads_its_goal_scalar_and_rejects_only_that_segment_"
            "when_unreachable"
        ),
        "same_task_other_legs_are_not_filtered": True,
        "relaxation": relaxation,
        "artifact": artifact,
        "artifact_contract": artifact_contract,
        "g26_reconstruction": reconstruction,
    }


def _finite_number(summary: Mapping[str, Any], name: str) -> float | None:
    value = summary.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def g27_source_admission_safety(
    summary: Mapping[str, Any],
    *,
    selected_segment_count: int,
    runtime_requested_segment_count: int,
    source_rejected_segment_count: int,
    seed_fault_count: int,
    expected_runtime_segment_ids: Sequence[str],
    runtime_bags: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Gate the reachable native cohort without claiming the G26 strict gate."""

    required_false = tuple(
        name
        for name in g24.HARD_SAFETY_FALSE_FIELDS
        if not (seed_fault_count and name == "time_limit_reached")
    )
    required = (
        "completed_count",
        "fault_event_count",
        "repair_event_count",
        *g24.HARD_SAFETY_ZERO_FIELDS,
        *required_false,
        "time_limit_reached",
    )
    missing = sorted({name for name in required if name not in summary})
    expected_ids = sorted(str(value) for value in expected_runtime_segment_ids)
    returned_ids = sorted(str(row.get("segment_id", "")) for row in runtime_bags)
    completed_bags = sum(
        bool(row.get("completed", row.get("complete", False))) for row in runtime_bags
    )
    gates = {
        "all_required_fields_present": not missing,
        "runtime_requested_plus_source_rejected_equals_selected": (
            runtime_requested_segment_count + source_rejected_segment_count
            == selected_segment_count
        ),
        "runtime_summary_completed_equals_reachable_requested": (
            _finite_number(summary, "completed_count")
            == float(runtime_requested_segment_count)
        ),
        "runtime_returned_exactly_reachable_segment_ids": returned_ids == expected_ids,
        "runtime_all_returned_segments_completed": (
            completed_bags == runtime_requested_segment_count
        ),
        "fault_event_count_equals_seed_count": (
            _finite_number(summary, "fault_event_count") == float(seed_fault_count)
        ),
        "repair_event_not_processed": _finite_number(summary, "repair_event_count") == 0.0,
        "g26_fault_horizon_termination_preserved": (
            summary.get("time_limit_reached") is True
            if seed_fault_count
            else summary.get("time_limit_reached") is False
        ),
        **{
            f"{name}_zero": _finite_number(summary, name) == 0.0
            for name in g24.HARD_SAFETY_ZERO_FIELDS
        },
        **{
            f"{name}_false": summary.get(name) is False
            for name in required_false
        },
    }
    return {
        "mode": "G27_LOCAL_SOURCE_UNREACHABLE_ADMISSION_SAFETY",
        "pass": all(gates.values()),
        "gates": gates,
        "missing_fields": missing,
        "claim_boundary": {
            "is_original_g26_strict_gate": False,
            "reason": "native_requested_cohort_excludes_source_local_unreachable_segments",
            "hard_structural_safety_abi_remains_strict": True,
            "fault_time_limit_is_g26_business_horizon_not_structural_failure": True,
        },
        "terminal_accounting": {
            "selected_segments": selected_segment_count,
            "runtime_requested_reachable_segments": runtime_requested_segment_count,
            "source_rejected_unreachable_segments": source_rejected_segment_count,
            "runtime_completed_segments": int(summary.get("completed_count", 0)),
            "runtime_failed_segments": int(summary.get("failed_count", 0)),
        },
    }


_DLP_COUNTER_FIELDS = (
    "g4irsf24_dlp_route_evaluation_count",
    "g4irsf24_dlp_eligible_candidate_count",
    "g4irsf24_dlp_supported_candidate_count",
    "g4irsf24_dlp_proposal_count",
    "g4irsf24_dlp_committed_mutation_count",
    "g4irsf24_dlp_fallback_s4_count",
    "g4irsf24_dlp_same_action_count",
    "g4irsf24_dlp_unsupported_fallback_count",
    "g4irsf24_dlp_low_support_fallback_count",
    "g4irsf24_dlp_margin_fallback_count",
    "g4irsf24_dlp_detour_fallback_count",
    "g4irsf24_dlp_shield_fault_fallback_count",
)


def _dlp_evidence(
    summary: Mapping[str, Any],
    artifact: Mapping[str, Any] | None,
) -> dict[str, Any]:
    active = artifact is not None
    gates = {
        "fault_artifact_mode_echoed": (
            summary.get("g4irsf24_dlp_mode") == "td" if active
            else "g4irsf24_dlp_mode" not in summary
        ),
        "edge_residual_count_echoed": (
            int(summary.get("g4irsf24_dlp_edge_residual_count", -1))
            == len(artifact["edge_residuals"])
            if active
            else "g4irsf24_dlp_edge_residual_count" not in summary
        ),
        "value_residual_count_echoed": (
            int(summary.get("g4irsf24_dlp_value_residual_count", -1))
            == len(artifact["value_residuals"])
            if active
            else "g4irsf24_dlp_value_residual_count" not in summary
        ),
    }
    return {
        "active": active,
        "pass": all(gates.values()),
        "gates": gates,
        "mode": summary.get("g4irsf24_dlp_mode"),
        "claim_boundary": summary.get("g4irsf24_dlp_claim_boundary"),
        "counters": {
            name: int(summary.get(name, 0)) for name in _DLP_COUNTER_FIELDS
        },
    }


def _synthetic_source_rejections(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "segment_id": str(row["segment_id"]),
            "task_id": int(row["task_id"]),
            "completed": False,
            "complete": False,
            "failure_reason": "source_local_goal_unreachable_after_seed_edge_fault",
        }
        for row in rows
    ]


def execute_case(
    case_id: str,
    *,
    segments: int,
    binary: Path,
) -> dict[str, Any]:
    """Run one registered G26 case under the minimal G27 local-value policy."""

    if segments not in ALLOWED_SEGMENT_COUNTS:
        raise FaultValueError(f"segments must be one of {ALLOWED_SEGMENT_COUNTS}")
    case = g26.case_by_id(case_id)
    registered_release = g26.default_release_csv_for_case(case_id).resolve(strict=True)
    canonical = harness.load_input_prefix(segments, root=ROOT)
    full_workload_gates = (
        g26._full_workload_gate(canonical)
        if segments == g26.PAPER_DAY_SEGMENTS
        else None
    )
    prefix, alignment = g24.apply_exact_hca_releases(canonical, registered_release)
    if int(alignment["aligned_segment_count"]) != segments:
        raise FaultValueError("registered HCA release alignment did not cover the prefix")

    request, runtime_rows, rejected_rows, local = prepare_request(
        case,
        prefix,
        binary=binary.resolve(strict=True),
    )
    topology = g26.topology_reachable_raw_bag_upper_bound(
        prefix.rows,
        request["edge_records"],
        case["seed_edges"],
    )
    wall_started = time.perf_counter()
    cpu_started = time.process_time()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    wall_seconds = time.perf_counter() - wall_started
    cpu_seconds = time.process_time() - cpu_started
    if not isinstance(payload, Mapping):
        raise FaultValueError("native S4 result is not an object")
    summary = payload.get("summary")
    bags = payload.get("bags")
    if not isinstance(summary, Mapping) or not isinstance(bags, list):
        raise FaultValueError("native S4 result lacks summary or bag rows")
    if any(not isinstance(row, Mapping) for row in bags):
        raise FaultValueError("native S4 bag payload contains a non-object")

    rejected_results = _synthetic_source_rejections(rejected_rows)
    combined_results = [dict(row) for row in bags] + rejected_results
    outcome = g26.summarize_paper_outcome(
        prefix.rows,
        combined_results,
        total_raw_bags=prefix.raw_bag_count,
    )
    runtime_ids = [str(row["segment_id"]) for row in runtime_rows]
    custom_safety = g27_source_admission_safety(
        summary,
        selected_segment_count=segments,
        runtime_requested_segment_count=len(runtime_rows),
        source_rejected_segment_count=len(rejected_rows),
        seed_fault_count=len(case["seed_edges"]),
        expected_runtime_segment_ids=runtime_ids,
        runtime_bags=bags,
    )
    echo_gates = g26._runtime_echo_gates(summary)
    dlp = _dlp_evidence(summary, local["artifact"])
    runtime_all_reachable_complete = (
        custom_safety["gates"]["runtime_summary_completed_equals_reachable_requested"]
        and custom_safety["gates"]["runtime_all_returned_segments_completed"]
    )
    completed_raw_bags = int(outcome["completed_raw_bag_count"])
    topology_upper = int(topology["topology_reachable_raw_bag_upper_bound"])
    topology_gates = {
        "bellman_reachable_segments_equal_g26_directed_topology_count": (
            len(runtime_rows) == int(topology["reachable_segment_count"])
        ),
        "completed_raw_bags_do_not_exceed_g26_topology_upper_bound": (
            completed_raw_bags <= topology_upper
        ),
        "all_reachable_runtime_complete_saturates_topology_upper_bound": (
            completed_raw_bags == topology_upper
            if runtime_all_reachable_complete
            else True
        ),
    }
    admitted = (
        bool(custom_safety["pass"])
        and all(echo_gates.values())
        and bool(dlp["pass"])
        and all(topology_gates.values())
    )
    status = ADMITTED_STATUS if admitted else "FAILED_G27_ADMISSION_GATE"

    g26_fixed_horizon_diagnostic = (
        g26._fixed_horizon_fault_safety(
            summary,
            requested=len(runtime_rows),
            seed_fault_count=len(case["seed_edges"]),
        )
        if case["seed_edges"]
        else None
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "case": dict(case),
        "protocol": {
            "framework": (
                "active_decentralized_A0_S4_J2_E2_plus_G27_local_FIFO_"
                "and_fault_local_values"
            ),
            "active_policy": local["active_policy"],
            "selected_segment_count": segments,
            "selected_raw_bag_count": prefix.raw_bag_count,
            "full_43603_input_audit": full_workload_gates,
            "registered_release_csv": alignment["source"],
            "exact_hca_release_alignment": alignment,
            "retained_g26_fault_horizon": {
                "max_simulation_time": request.get("max_simulation_time"),
                "max_events": request.get("max_events"),
                "fault_protocol": local["g26_reconstruction"]["fault"],
            },
            "local_scalar_semantics": {
                "unit": "one_scalar_per_node_per_actual_goal",
                "read_scope": "own_outgoing_edges_and_direct_neighbour_scalars_only",
                "decision_scope": "one_next_hop_at_current_junction",
                "per_bag_route_materialized": False,
                "global_route_reservation_table": False,
                "runtime_full_astar_used": False,
                "physical_distribution_claimed": False,
                "implementation_boundary": (
                    "case_start_scalar_rounds_are_orchestrated_in_one_python_process"
                ),
            },
            "claim_boundary": (
                "structural_fault_local_scalar_policy_not_learning_not_per_bag_route_"
                "not_global_reservation_not_physical_distributed_deployment"
            ),
        },
        "local_values": local,
        "outcome": {
            "requested_segment_count": segments,
            "runtime_requested_reachable_segment_count": len(runtime_rows),
            "source_rejected_unreachable_segment_count": len(rejected_rows),
            "combined_terminal_segment_count": len(combined_results),
            "runtime_completed_segment_count": int(summary.get("completed_count", 0)),
            "runtime_failed_segment_count": int(summary.get("failed_count", 0)),
            "combined_failed_segment_count": (
                len(rejected_rows) + int(summary.get("failed_count", 0))
            ),
            "topology_reachability": topology,
            "topology_reachable_raw_bag_upper_bound": topology_upper,
            **outcome,
        },
        "safety": {
            "admission": {
                "mode": custom_safety["mode"],
                "pass": admitted,
                "custom_safety_pass": bool(custom_safety["pass"]),
                "runtime_echo_pass": all(echo_gates.values()),
                "dlp_echo_pass": bool(dlp["pass"]),
                "topology_gate_pass": all(topology_gates.values()),
            },
            "g27_source_admission": custom_safety,
            "g26_fixed_horizon_diagnostic_only_not_admission": g26_fixed_horizon_diagnostic,
            "runtime_echo_gates": echo_gates,
            "topology_gates": topology_gates,
        },
        "dlp": dlp,
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    case = commands.add_parser("case", help="run one registered G26 case with G27 values")
    case.add_argument(
        "--case-id",
        required=True,
        choices=[value["case_id"] for value in g26.paper_cases()],
    )
    case.add_argument("--segments", type=int, required=True, choices=ALLOWED_SEGMENT_COUNTS)
    case.add_argument("--binary", type=Path, required=True)
    case.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "case":
        raise AssertionError(f"unhandled command: {args.command}")
    value = execute_case(
        args.case_id,
        segments=args.segments,
        binary=args.binary,
    )
    output = _rooted(args.output)
    g26._atomic_json(output, value)
    print(
        json.dumps(
            {
                "case_id": args.case_id,
                "segments": args.segments,
                "status": value["status"],
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0 if value["status"] == ADMITTED_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
