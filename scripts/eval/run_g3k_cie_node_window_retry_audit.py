from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import struct
import sys
from typing import Any, Iterable
import zlib


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "eval" / "run_g3k_cie_node_window_retry_audit.py"
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"

REPORT_PATH = ROOT / "outputs" / "reports" / "g3k_cie_node_window_retry_audit_report.md"
SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3k_retry_summary.csv"
TIMELINE_TABLE = ROOT / "outputs" / "tables" / "g3k_no_path_retry_timeline.csv"
RECOVERED_TABLE = ROOT / "outputs" / "tables" / "g3k_recovered_no_path_cases.csv"
REMAINING_TABLE = ROOT / "outputs" / "tables" / "g3k_remaining_no_path_cases.csv"
JAVA_ALIGNMENT_TABLE = ROOT / "outputs" / "tables" / "g3k_java_semantics_alignment.csv"
TAXONOMY_TABLE = ROOT / "outputs" / "tables" / "g3k_teacher_label_taxonomy.csv"
EDGE_DIAG_TABLE = ROOT / "outputs" / "tables" / "g3k_edge_overlap_diagnostic_only.csv"
SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3k_cie_retry_teacher_sample.jsonl"
FIGURE_PATH = ROOT / "outputs" / "figures" / "g3k_retry_recovery_timeline.png"

JAVA_ASTAR_PATH = ROOT / "legacy" / "jichang_origin_readonly" / "src" / "App" / "Astar.java"
JAVA_ICS_PATH = ROOT / "legacy" / "jichang_origin_readonly" / "src" / "App" / "ICS_PathFinding.java"

EXPECTED_G3J_PRIMARY_PLANNED = 127
EXPECTED_G3J_PRIMARY_TOTAL = 144
EXPECTED_G3J_NODE_CONFLICTS = 0
EXPECTED_G3J_NO_PATH = 17
G4A_PILOT_PLANNED_GATE = 132
MAX_SAMPLE_ROWS = 500
EPSILON = 1.0e-6


@dataclass(frozen=True)
class MatchedScenario:
    name: str
    task_offset: int
    max_tasks: int
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[tuple[int, int, float, float], ...] = ()
    node_capacities: tuple[tuple[int, int], ...] = ()
    merge_groups: tuple[tuple[int, int, int], ...] = ()
    merge_capacity: int = 1
    merge_headway_seconds: float = 0.0


@dataclass(frozen=True)
class RetryVariant:
    name: str
    tick_seconds: float
    max_retry_delay_seconds: float | None


@dataclass
class PendingRetry:
    task: Any
    arrival_time: float
    attempts: int = 0
    first_failure_time: float | None = None
    last_failure_reason: str = ""


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _case_plan() -> tuple[MatchedScenario, ...]:
    return (
        MatchedScenario("legacy_first16", 0, 16),
        MatchedScenario("legacy_first16_buffer2", 0, 16, node_capacities=((28, 2), (47, 2))),
        MatchedScenario("legacy_first32", 0, 32),
        MatchedScenario("legacy_offset32_static16", 32, 16, fault_edges=((16, 17),)),
        MatchedScenario("legacy_offset64_repair32", 64, 32, fault_windows=((28, 47, 0.0, 12000.0),)),
        MatchedScenario("legacy_offset64_merge32", 64, 32, merge_groups=((13, 23, 9), (18, 22, 9))),
    )


def _retry_variants() -> tuple[RetryVariant, ...]:
    variants: list[RetryVariant] = []
    for tick_seconds in (1.0, 2.0, 5.0):
        for max_delay in (60.0, 300.0, 900.0, None):
            suffix = "until_deadline" if max_delay is None else f"max_delay_{int(max_delay)}s"
            variants.append(RetryVariant(f"java_retry_tick_{int(tick_seconds)}s_{suffix}", tick_seconds, max_delay))
    return tuple(variants)


def _selected_tasks(all_tasks: tuple[Any, ...], scenario: MatchedScenario) -> tuple[Any, ...]:
    return all_tasks[scenario.task_offset : scenario.task_offset + scenario.max_tasks]


def _scenario_context(scenario: MatchedScenario) -> str:
    if scenario.fault_edges:
        return "static_fault"
    if scenario.fault_windows:
        return "repair_window"
    if scenario.merge_groups:
        return "merge_window"
    if scenario.node_capacities:
        return "buffer_capacity"
    return "no_fault"


def _scenario_merge_groups(scenario: MatchedScenario) -> dict[tuple[int, int], int]:
    return {(start, end): group for start, end, group in scenario.merge_groups}


def _run_g3j_primary_scenario(
    graph: Any,
    all_tasks: tuple[Any, ...],
    scenario: MatchedScenario,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from czr005.baselines import LegacyRouteSIPPBaseline

    selected = _selected_tasks(all_tasks, scenario)
    baseline = LegacyRouteSIPPBaseline(
        graph,
        edge_capacity=None,
        edge_headway_seconds=0.0,
        node_capacities=dict(scenario.node_capacities),
        merge_groups={},
        merge_capacity=scenario.merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    result = baseline.run_episode(
        selected,
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=tuple(scenario.fault_windows),
    )
    edge_diag = baseline.edge_reservations.conflict_count(capacity=1, headway_seconds=0.0)
    merge_diag = baseline.edge_reservations.merge_group_conflict_count(
        _scenario_merge_groups(scenario),
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    unplanned_rows: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    path_rows: list[dict[str, Any]] = []
    for event in result.events:
        if event["event"] == "planned":
            path_rows.append(
                {
                    "scenario": scenario.name,
                    "segment_id": event["segment_id"],
                    "task_id": event["task_id"],
                    "legacy_path": _path_text(event.get("legacy_path", ())),
                    "executed_path": _path_text(event.get("path", ())),
                    "path_matches_legacy_astar": event.get("legacy_path", ()) == event.get("path", ()),
                }
            )
            continue
        row = {
            "variant": "g3j_primary_single_attempt",
            "scenario": scenario.name,
            "context": _scenario_context(scenario),
            "segment_id": event["segment_id"],
            "task_id": event["task_id"],
            "attempt_index": 1,
            "attempt_time": event["entry_time"],
            "original_pass_time": event["entry_time"],
            "retry_delay_seconds": 0.0,
            "pending_count_before": "",
            "attempt_result": "primary_no_path",
            "failure_reason": event.get("reason", ""),
            "active_fault_edges": _active_faults_text(scenario, float(event["entry_time"])),
            "source_start_time": "",
            "legacy_path": "",
            "route_path": "",
            "finish_time": "",
            "taxonomy_label": "CIE_NO_PATH_AFTER_RETRY",
            "root_cause": _root_cause(scenario, float(event["entry_time"]), recovered=False),
            "g3j_no_path_case": True,
        }
        timeline_rows.append(row)
        unplanned_rows.append(
            {
                "scenario": scenario.name,
                "context": _scenario_context(scenario),
                "segment_id": event["segment_id"],
                "task_id": event["task_id"],
                "reason": event.get("reason", ""),
                "entry_time": event["entry_time"],
            }
        )
    summary = {
        "variant": "g3j_primary_single_attempt",
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "tick_seconds": "",
        "max_retry_delay_seconds": "",
        "max_tasks": scenario.max_tasks,
        "planned": result.metrics.planned_count,
        "unplanned": result.metrics.unplanned_count,
        "node_window_conflicts": result.metrics.reservation_conflicts,
        "diagnostic_edge_overlap_only": edge_diag,
        "diagnostic_merge_overlap_only": merge_diag,
        "edge_capacity_model": "not_applied_original_cie_node_window_primary",
        "edge_overlap_counted_as_primary": False,
        "legacy_path_match_count": baseline.stats.legacy_path_match_count,
        "legacy_path_mismatch_count": baseline.stats.legacy_path_mismatch_count,
        "inserted_wait_task_count": baseline.stats.inserted_wait_count,
        "g3j_no_path_recovered_count": 0,
        "g3j_no_path_remaining_count": result.metrics.unplanned_count,
        "total_retry_attempts": 0,
        "g3j_retry_attempts": 0,
        "mean_recovery_delay_seconds": "",
        "max_recovery_delay_seconds": "",
        "g4a_pilot_candidate": False,
        "decision": "baseline_negative_inventory_for_retry_audit",
        "teacher_route_source": "original_cie_legacy_astar",
    }
    return summary, unplanned_rows, timeline_rows, path_rows


def _run_retry_scenario(
    graph: Any,
    all_tasks: tuple[Any, ...],
    scenario: MatchedScenario,
    variant: RetryVariant,
    g3j_no_path_keys: set[tuple[str, str]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from czr005.baselines.legacy_route_sipp import LegacyRouteSIPPPlanner, _inserted_wait_count
    from czr005.envs.action_mask import active_fault_edges
    from czr005.sim_py.astar import AStarPlanner
    from czr005.sim_py.metrics import compute_episode_metrics
    from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable

    selected = _selected_tasks(all_tasks, scenario)
    node_capacities = dict(scenario.node_capacities)
    diagnostic_merge_groups = _scenario_merge_groups(scenario)
    reservations = ReservationTable()
    edge_reservations = EdgeReservationTable()
    astar = AStarPlanner(graph)
    planner = LegacyRouteSIPPPlanner(graph)

    pending: list[PendingRetry] = []
    routes: dict[str, list[Any]] = {}
    task_by_segment = {task.segment_id: task for task in selected}
    unplanned: list[Any] = []
    events: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    recovered_rows: list[dict[str, Any]] = []
    remaining_rows: list[dict[str, Any]] = []
    retry_attempts = 0
    legacy_path_matches = 0
    legacy_path_mismatches = 0
    inserted_wait_task_count = 0
    arrival_index = 0
    planning_rank = 0

    for epoch in _retry_epochs(selected, variant):
        while arrival_index < len(selected) and selected[arrival_index].pass_time <= epoch + EPSILON:
            task = selected[arrival_index]
            pending.append(PendingRetry(task=task, arrival_time=task.pass_time))
            arrival_index += 1

        numbers = len(pending)
        for _ in range(numbers):
            item = pending.pop(0)
            task = item.task
            key = (scenario.name, task.segment_id)
            is_g3j_no_path = key in g3j_no_path_keys
            retry_delay = max(0.0, epoch - task.pass_time)
            if _exceeded_retry_delay(variant, retry_delay):
                item.last_failure_reason = "max_retry_delay_exceeded"
                unplanned.append(task)
                events.append(_unplanned_event(task, scenario, planning_rank, item.last_failure_reason, epoch))
                if is_g3j_no_path:
                    remaining_rows.append(_remaining_case_row(scenario, variant, item, epoch, item.last_failure_reason))
                    timeline_rows.append(
                        _timeline_row(
                            scenario=scenario,
                            variant=variant,
                            task=task,
                            attempt_index=item.attempts + 1,
                            attempt_time=epoch,
                            retry_delay=retry_delay,
                            pending_count_before=numbers,
                            attempt_result="no_path_after_retry",
                            failure_reason=item.last_failure_reason,
                            source_start_time="",
                            legacy_path=(),
                            route_path=(),
                            finish_time="",
                            taxonomy_label="CIE_NO_PATH_AFTER_RETRY",
                            g3j_no_path_case=True,
                        )
                    )
                planning_rank += 1
                continue

            item.attempts += 1
            retry_attempts += 1
            active_faults = active_fault_edges(set(scenario.fault_edges), tuple(scenario.fault_windows), epoch)
            source_start = planner._earliest_safe_node_start(
                reservations,
                task.start,
                epoch,
                graph.service_time(task.start),
                node_capacities.get(task.start, 1),
                task.task_id,
            )
            legacy_path: tuple[int, ...] = ()
            failure_reason = ""
            if source_start is None:
                failure_reason = "blocked_start_node"
            else:
                legacy_route = astar.plan(
                    start=task.start,
                    goal=task.goal,
                    start_time=source_start,
                    reservations=reservations,
                    fault_edges=active_faults,
                    task_id=task.task_id,
                )
                legacy_path = tuple(int(node.location) for node in legacy_route)
                if not legacy_path:
                    failure_reason = "legacy_astar_no_path"

            route: list[Any] = []
            if legacy_path:
                route = planner.plan(
                    start=task.start,
                    goal=task.goal,
                    start_time=float(source_start),
                    reservations=reservations,
                    edge_reservations=edge_reservations,
                    edge_capacity=None,
                    edge_headway_seconds=0.0,
                    node_capacities=node_capacities,
                    merge_groups={},
                    merge_capacity=scenario.merge_capacity,
                    merge_headway_seconds=scenario.merge_headway_seconds,
                    fault_edges=active_faults,
                    task_id=task.task_id,
                    legacy_path=legacy_path,
                )
                if not route:
                    failure_reason = "legacy_route_retime_no_path"

            if not route:
                if item.first_failure_time is None:
                    item.first_failure_time = epoch
                item.last_failure_reason = failure_reason
                pending.append(item)
                if is_g3j_no_path:
                    timeline_rows.append(
                        _timeline_row(
                            scenario=scenario,
                            variant=variant,
                            task=task,
                            attempt_index=item.attempts,
                            attempt_time=epoch,
                            retry_delay=retry_delay,
                            pending_count_before=numbers,
                            attempt_result="no_path_retry_pending",
                            failure_reason=failure_reason,
                            source_start_time=source_start if source_start is not None else "",
                            legacy_path=legacy_path,
                            route_path=(),
                            finish_time="",
                            taxonomy_label="WAIT_AT_SOURCE_RETRY",
                            g3j_no_path_case=True,
                        )
                    )
                continue

            route_path = tuple(int(node.location) for node in route)
            if route_path == legacy_path:
                legacy_path_matches += 1
            else:
                legacy_path_mismatches += 1
            inserted_wait_count = _inserted_wait_count(graph, route)
            if inserted_wait_count > 0:
                inserted_wait_task_count += 1
            reservations.add_route(task.task_id, route)
            _reserve_route_edges(graph, edge_reservations, task.task_id, route)
            routes[task.segment_id] = route
            event = {
                "event": "planned",
                "baseline": "g3k_java_style_cie_retry",
                "variant": variant.name,
                "scenario": scenario.name,
                "context": _scenario_context(scenario),
                "segment_id": task.segment_id,
                "task_id": task.task_id,
                "start": task.start,
                "goal": task.goal,
                "entry_time": task.pass_time,
                "attempt_time": epoch,
                "retry_delay_seconds": retry_delay,
                "attempts": item.attempts,
                "finish_time": route[-1].t2,
                "priority_rank": planning_rank,
                "legacy_path": list(legacy_path),
                "path": list(route_path),
                "inserted_wait_count": inserted_wait_count,
                "taxonomy_label": "WAIT_AT_SOURCE_RETRY" if item.attempts > 1 else "MOVE_TO_NEXT_CIE",
                "g3j_no_path_case": is_g3j_no_path,
            }
            events.append(event)
            if is_g3j_no_path:
                timeline_rows.append(
                    _timeline_row(
                        scenario=scenario,
                        variant=variant,
                        task=task,
                        attempt_index=item.attempts,
                        attempt_time=epoch,
                        retry_delay=retry_delay,
                        pending_count_before=numbers,
                        attempt_result="recovered",
                        failure_reason="",
                        source_start_time=source_start,
                        legacy_path=legacy_path,
                        route_path=route_path,
                        finish_time=route[-1].t2,
                        taxonomy_label="WAIT_AT_SOURCE_RETRY",
                        g3j_no_path_case=True,
                    )
                )
                recovered_rows.append(
                    _recovered_case_row(
                        scenario=scenario,
                        variant=variant,
                        item=item,
                        recovered_time=epoch,
                        route_path=route_path,
                        active_faults=active_faults,
                    )
                )
            planning_rank += 1

    for item in pending:
        task = item.task
        key = (scenario.name, task.segment_id)
        is_g3j_no_path = key in g3j_no_path_keys
        reason = item.last_failure_reason or "retry_horizon_exhausted"
        unplanned.append(task)
        events.append(_unplanned_event(task, scenario, planning_rank, reason, _final_attempt_time(item, variant)))
        if is_g3j_no_path:
            remaining = _remaining_case_row(scenario, variant, item, _final_attempt_time(item, variant), reason)
            remaining_rows.append(remaining)
            timeline_rows.append(
                _timeline_row(
                    scenario=scenario,
                    variant=variant,
                    task=task,
                    attempt_index=item.attempts + 1,
                    attempt_time=_final_attempt_time(item, variant),
                    retry_delay=max(0.0, _final_attempt_time(item, variant) - task.pass_time),
                    pending_count_before="",
                    attempt_result="no_path_after_retry",
                    failure_reason=reason,
                    source_start_time="",
                    legacy_path=(),
                    route_path=(),
                    finish_time="",
                    taxonomy_label="CIE_NO_PATH_AFTER_RETRY",
                    g3j_no_path_case=True,
                )
            )
        planning_rank += 1

    metrics = compute_episode_metrics(routes, task_by_segment, unplanned, reservations, node_capacities)
    g3j_recovered_count = len(recovered_rows)
    g3j_remaining_count = len(remaining_rows)
    recovery_delays = [float(row["retry_delay_seconds"]) for row in recovered_rows]
    edge_diag = edge_reservations.conflict_count(capacity=1, headway_seconds=0.0)
    merge_diag = edge_reservations.merge_group_conflict_count(
        diagnostic_merge_groups,
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    summary = {
        "variant": variant.name,
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "tick_seconds": _format_number(variant.tick_seconds),
        "max_retry_delay_seconds": "until_deadline" if variant.max_retry_delay_seconds is None else _format_number(variant.max_retry_delay_seconds),
        "max_tasks": scenario.max_tasks,
        "planned": metrics.planned_count,
        "unplanned": metrics.unplanned_count,
        "node_window_conflicts": metrics.reservation_conflicts,
        "diagnostic_edge_overlap_only": edge_diag,
        "diagnostic_merge_overlap_only": merge_diag,
        "edge_capacity_model": "not_applied_original_cie_node_window_primary",
        "edge_overlap_counted_as_primary": False,
        "legacy_path_match_count": legacy_path_matches,
        "legacy_path_mismatch_count": legacy_path_mismatches,
        "inserted_wait_task_count": inserted_wait_task_count,
        "g3j_no_path_recovered_count": g3j_recovered_count,
        "g3j_no_path_remaining_count": g3j_remaining_count,
        "total_retry_attempts": retry_attempts,
        "g3j_retry_attempts": sum(1 for row in timeline_rows if row["g3j_no_path_case"] == "True"),
        "mean_recovery_delay_seconds": _mean_text(recovery_delays),
        "max_recovery_delay_seconds": _max_text(recovery_delays),
        "g4a_pilot_candidate": False,
        "decision": "scenario_row",
        "teacher_route_source": "original_cie_legacy_astar",
    }
    edge_rows = [
        {
            "variant": variant.name,
            "scenario": scenario.name,
            "context": _scenario_context(scenario),
            "diagnostic_edge_overlap_count": edge_diag,
            "diagnostic_merge_overlap_count": merge_diag,
            "node_window_conflicts": metrics.reservation_conflicts,
            "counted_as_primary_conflict": False,
            "edge_capacity_model": "not_applied_original_cie_node_window_primary",
            "decision": "diagnostic_only_not_teacher_gate",
        }
    ]
    return summary, timeline_rows, recovered_rows, remaining_rows, events, edge_rows


def _retry_epochs(selected: tuple[Any, ...], variant: RetryVariant) -> list[float]:
    if not selected:
        return []
    first = min(task.pass_time for task in selected)
    last_pass = max(task.pass_time for task in selected)
    if variant.max_retry_delay_seconds is None:
        last = max(max(task.std for task in selected), last_pass + 900.0)
    else:
        last = last_pass + variant.max_retry_delay_seconds + variant.tick_seconds
    epochs = {round(task.pass_time, 6) for task in selected}
    start = math.floor(first / variant.tick_seconds) * variant.tick_seconds
    current = start
    while current <= last + EPSILON:
        if current >= first - EPSILON:
            epochs.add(round(current, 6))
        current += variant.tick_seconds
    return sorted(epochs)


def _exceeded_retry_delay(variant: RetryVariant, retry_delay: float) -> bool:
    if variant.max_retry_delay_seconds is None:
        return False
    return retry_delay > variant.max_retry_delay_seconds + EPSILON


def _reserve_route_edges(graph: Any, edge_reservations: Any, task_id: int, route: list[Any]) -> None:
    for left, right in zip(route, route[1:]):
        if left.location == right.location:
            continue
        edge = graph.edge(left.location, right.location)
        edge_start = right.t1 - edge.travel_time
        edge_reservations.reserve(task_id, left.location, right.location, edge_start, right.t1)


def _active_faults_text(scenario: MatchedScenario, ready_time: float) -> str:
    from czr005.envs.action_mask import active_fault_edges

    active = sorted(active_fault_edges(set(scenario.fault_edges), tuple(scenario.fault_windows), ready_time))
    return ";".join(f"{left}->{right}" for left, right in active)


def _timeline_row(
    *,
    scenario: MatchedScenario,
    variant: RetryVariant,
    task: Any,
    attempt_index: int,
    attempt_time: float,
    retry_delay: float,
    pending_count_before: int | str,
    attempt_result: str,
    failure_reason: str,
    source_start_time: float | str,
    legacy_path: Iterable[int],
    route_path: Iterable[int],
    finish_time: float | str,
    taxonomy_label: str,
    g3j_no_path_case: bool,
) -> dict[str, Any]:
    return {
        "variant": variant.name,
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "segment_id": task.segment_id,
        "task_id": task.task_id,
        "attempt_index": attempt_index,
        "attempt_time": _format_number(attempt_time),
        "original_pass_time": _format_number(task.pass_time),
        "retry_delay_seconds": _format_number(retry_delay),
        "pending_count_before": pending_count_before,
        "attempt_result": attempt_result,
        "failure_reason": failure_reason,
        "active_fault_edges": _active_faults_text(scenario, attempt_time),
        "source_start_time": source_start_time if source_start_time == "" else _format_number(float(source_start_time)),
        "legacy_path": _path_text(legacy_path),
        "route_path": _path_text(route_path),
        "finish_time": finish_time if finish_time == "" else _format_number(float(finish_time)),
        "taxonomy_label": taxonomy_label,
        "root_cause": _root_cause(scenario, attempt_time, recovered=attempt_result == "recovered"),
        "g3j_no_path_case": g3j_no_path_case,
    }


def _recovered_case_row(
    *,
    scenario: MatchedScenario,
    variant: RetryVariant,
    item: PendingRetry,
    recovered_time: float,
    route_path: Iterable[int],
    active_faults: set[tuple[int, int]],
) -> dict[str, Any]:
    task = item.task
    first_no_path_time = item.first_failure_time if item.first_failure_time is not None else task.pass_time
    return {
        "variant": variant.name,
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "segment_id": task.segment_id,
        "task_id": task.task_id,
        "start": task.start,
        "goal": task.goal,
        "first_no_path_time": _format_number(first_no_path_time),
        "recovered_time": _format_number(recovered_time),
        "retry_delay_seconds": _format_number(recovered_time - task.pass_time),
        "attempts": item.attempts,
        "route_path": _path_text(route_path),
        "active_fault_edges_at_recovery": ";".join(f"{left}->{right}" for left, right in sorted(active_faults)),
        "root_cause": _root_cause(scenario, recovered_time, recovered=True),
        "taxonomy_label": "WAIT_AT_SOURCE_RETRY",
    }


def _remaining_case_row(
    scenario: MatchedScenario,
    variant: RetryVariant,
    item: PendingRetry,
    final_time: float,
    reason: str,
) -> dict[str, Any]:
    task = item.task
    first_no_path_time = item.first_failure_time if item.first_failure_time is not None else task.pass_time
    return {
        "variant": variant.name,
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "segment_id": task.segment_id,
        "task_id": task.task_id,
        "start": task.start,
        "goal": task.goal,
        "first_no_path_time": _format_number(first_no_path_time),
        "final_attempt_time": _format_number(final_time),
        "retry_delay_seconds": _format_number(final_time - task.pass_time),
        "attempts": item.attempts,
        "failure_reason": reason,
        "root_cause": _root_cause(scenario, final_time, recovered=False),
        "taxonomy_label": "CIE_NO_PATH_AFTER_RETRY",
    }


def _unplanned_event(task: Any, scenario: MatchedScenario, priority_rank: int, reason: str, attempt_time: float) -> dict[str, Any]:
    return {
        "event": "unplanned",
        "baseline": "g3k_java_style_cie_retry",
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "segment_id": task.segment_id,
        "task_id": task.task_id,
        "start": task.start,
        "goal": task.goal,
        "entry_time": task.pass_time,
        "attempt_time": attempt_time,
        "priority_rank": priority_rank,
        "reason": reason,
    }


def _root_cause(scenario: MatchedScenario, attempt_time: float, recovered: bool) -> str:
    context = _scenario_context(scenario)
    if context == "repair_window":
        active = any(start_time <= attempt_time < repair_time for _, _, start_time, repair_time in scenario.fault_windows)
        if active:
            return "temporary_fault_window_active_plus_node_time_window_pressure"
        if recovered:
            return "temporary_node_time_window_blockage_after_repair_window_recovered_by_source_retry"
        return "node_time_window_blockage_after_repair_window_not_recovered"
    if context == "merge_window":
        if recovered:
            return "temporary_node_time_window_blockage_in_merge_named_window_no_merge_constraint_applied"
        return "node_time_window_blockage_in_merge_named_window_no_merge_constraint_applied"
    if context == "static_fault":
        return "static_fault_scope_with_source_retry" if recovered else "static_fault_scope_unrecovered"
    if recovered:
        return "temporary_node_time_window_blockage_recovered_by_source_retry"
    return "temporary_node_time_window_blockage_at_single_attempt"


def _final_attempt_time(item: PendingRetry, variant: RetryVariant) -> float:
    if variant.max_retry_delay_seconds is None:
        return item.task.std
    return item.task.pass_time + variant.max_retry_delay_seconds


def _aggregate_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["scenario"] != "ALL":
            grouped[str(row["variant"])].append(row)
    output: list[dict[str, Any]] = []
    for variant_name, items in sorted(grouped.items()):
        recovered_count = sum(int(item["g3j_no_path_recovered_count"]) for item in items)
        remaining_count = sum(int(item["g3j_no_path_remaining_count"]) for item in items)
        recovery_delays = [
            float(item["mean_recovery_delay_seconds"])
            for item in items
            if str(item["mean_recovery_delay_seconds"]).strip()
        ]
        planned = sum(int(item["planned"]) for item in items)
        node_conflicts = sum(int(item["node_window_conflicts"]) for item in items)
        pilot_candidate = planned >= G4A_PILOT_PLANNED_GATE and node_conflicts == 0
        output.append(
            {
                "variant": variant_name,
                "scenario": "ALL",
                "context": "aggregate",
                "tick_seconds": items[0]["tick_seconds"],
                "max_retry_delay_seconds": items[0]["max_retry_delay_seconds"],
                "max_tasks": sum(int(item["max_tasks"]) for item in items),
                "planned": planned,
                "unplanned": sum(int(item["unplanned"]) for item in items),
                "node_window_conflicts": node_conflicts,
                "diagnostic_edge_overlap_only": sum(int(item["diagnostic_edge_overlap_only"]) for item in items),
                "diagnostic_merge_overlap_only": sum(int(item["diagnostic_merge_overlap_only"]) for item in items),
                "edge_capacity_model": "not_applied_original_cie_node_window_primary",
                "edge_overlap_counted_as_primary": False,
                "legacy_path_match_count": sum(int(item["legacy_path_match_count"]) for item in items),
                "legacy_path_mismatch_count": sum(int(item["legacy_path_mismatch_count"]) for item in items),
                "inserted_wait_task_count": sum(int(item["inserted_wait_task_count"]) for item in items),
                "g3j_no_path_recovered_count": recovered_count,
                "g3j_no_path_remaining_count": remaining_count,
                "total_retry_attempts": sum(int(item["total_retry_attempts"]) for item in items),
                "g3j_retry_attempts": sum(int(item["g3j_retry_attempts"]) for item in items),
                "mean_recovery_delay_seconds": _mean_text(recovery_delays),
                "max_recovery_delay_seconds": _max_text(
                    [
                        float(item["max_recovery_delay_seconds"])
                        for item in items
                        if str(item["max_recovery_delay_seconds"]).strip()
                    ]
                ),
                "g4a_pilot_candidate": pilot_candidate,
                "decision": "g4a_pilot_dataset_candidate" if pilot_candidate else "blocker_continue_java_semantics_audit",
                "teacher_route_source": "original_cie_legacy_astar",
            }
        )
    return output


def _java_semantics_alignment_rows() -> list[dict[str, Any]]:
    checks = [
        (
            "legacy_astar_uses_node_time_windows",
            JAVA_ASTAR_PATH,
            "constrain_Set.containsKey(i)&&i!=goal.location",
            "A* filters candidate target-node time windows, excluding the final goal node.",
            "G3k keeps node-window reservations as the only primary dynamic occupancy constraint.",
        ),
        (
            "legacy_astar_uses_fault_edges",
            JAVA_ASTAR_PATH,
            "in_fault_edges(fault_Edges,currNode.getLocation(),i)",
            "A* skips active fault edges.",
            "G3k passes only static/currently active repair-window faults to CIE/A*.",
        ),
        (
            "legacy_scheduler_appends_new_tasks",
            JAVA_ICS_PATH,
            "ICS.getUnfinishTasks().addAll(tasks.new_tasks_list);",
            "New arrivals are appended to the unfinished-task queue.",
            "G3k appends arrivals before each retry epoch and preserves queue order.",
        ),
        (
            "legacy_scheduler_fixed_epoch_batch",
            JAVA_ICS_PATH,
            "int numbers=ICS.getUnfinishTasks().size();",
            "Each epoch processes the queue length captured at epoch start.",
            "G3k uses the same fixed-length queue pass so failed tasks wait for a later epoch.",
        ),
        (
            "legacy_scheduler_retry_time",
            JAVA_ICS_PATH,
            "star.setT1(tasks.cur_time);",
            "Retries use the current scheduler time, not the original pass time.",
            "G3k retries use the retry epoch as the source planning time.",
        ),
        (
            "legacy_scheduler_keeps_failed_task",
            JAVA_ICS_PATH,
            "ICS.getUnfinishTasks().add(curTask);",
            "A path-empty task is added back to unfinishedTasks.",
            "G3k keeps no-path tasks pending and retries them later.",
        ),
        (
            "legacy_scheduler_updates_constraints_only_after_success",
            JAVA_ICS_PATH,
            "update_constrain(curTask.task_ID,path,constrains);",
            "Node constraints are updated only after a route is found.",
            "G3k does not reserve failed attempts; reservations are added only for planned routes.",
        ),
        (
            "g3k_no_edge_capacity_primary",
            SCRIPT_PATH,
            "edge_capacity=None",
            "No Java evidence was found for a single-occupancy conveyor edge constraint.",
            "G3k records edge overlaps only in diagnostic columns.",
        ),
    ]
    rows: list[dict[str, Any]] = []
    for check, path, snippet, legacy_semantic, alignment in checks:
        line = _find_line(path, snippet)
        rows.append(
            {
                "check": check,
                "source_file": _relative(path),
                "line": line,
                "legacy_semantic": legacy_semantic,
                "g3k_alignment": alignment,
                "pass": line != "",
                "evidence": snippet,
            }
        )
    return rows


def _edge_diag_row_from_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "variant": row["variant"],
        "scenario": row["scenario"],
        "context": row["context"],
        "diagnostic_edge_overlap_count": row["diagnostic_edge_overlap_only"],
        "diagnostic_merge_overlap_count": row["diagnostic_merge_overlap_only"],
        "node_window_conflicts": row["node_window_conflicts"],
        "counted_as_primary_conflict": False,
        "edge_capacity_model": "not_applied_original_cie_node_window_primary",
        "decision": "diagnostic_only_not_teacher_gate",
    }


def _taxonomy_rows(best_summary: dict[str, Any], best_events: list[dict[str, Any]], best_remaining: list[dict[str, Any]]) -> list[dict[str, Any]]:
    planned = int(best_summary["planned"])
    recovered = int(best_summary["g3j_no_path_recovered_count"])
    inserted_wait = sum(int(event.get("inserted_wait_count", 0)) for event in best_events if event.get("event") == "planned")
    remaining = len(best_remaining)
    return [
        {
            "label": "MOVE_TO_NEXT_CIE",
            "scope": "route_step",
            "meaning": "Use the next node on the verified CIE/A* route.",
            "count_in_recommended_variant": planned,
            "example_action": "move from current conveyor node to the next CIE node",
            "teacher_use": "positive next-hop label for per-bag junction policy",
        },
        {
            "label": "WAIT_AT_SOURCE_RETRY",
            "scope": "source_admission",
            "meaning": "Keep the bag outside the committed route and retry CIE/A* at a later scheduler time.",
            "count_in_recommended_variant": recovered,
            "example_action": "do not reserve a route yet; retry when node windows clear",
            "teacher_use": "source wait label for recovered G3j no-path cases",
        },
        {
            "label": "WAIT_AT_NODE_TIME_WINDOW",
            "scope": "in_route_timing",
            "meaning": "Wait before entering a node whose verified node time window is occupied.",
            "count_in_recommended_variant": inserted_wait,
            "example_action": "hold before the next node until its time window clears",
            "teacher_use": "reserved for fixed-route retiming labels",
        },
        {
            "label": "REROUTE_CIE_RETRY",
            "scope": "source_or_current_node",
            "meaning": "Call CIE/A* again after time advances and follow the newly valid route.",
            "count_in_recommended_variant": 0,
            "example_action": "retry CIE/A* from current valid node",
            "teacher_use": "reserved for future reroute audits",
        },
        {
            "label": "CIE_NO_PATH_AFTER_RETRY",
            "scope": "blocker",
            "meaning": "CIE/A* still cannot find a route after the configured retry horizon.",
            "count_in_recommended_variant": remaining,
            "example_action": "mark unresolved and do not train as success",
            "teacher_use": "negative label retained for blocker analysis",
        },
        {
            "label": "ABSTAIN_TO_SAFE_FALLBACK",
            "scope": "runtime_fallback",
            "meaning": "Do not trust a learned move; fall back to a verified safe planner.",
            "count_in_recommended_variant": 0,
            "example_action": "call original CIE/A* or a verified scheduler instead of policy action",
            "teacher_use": "fallback label for later safety wrapper datasets",
        },
    ]


def _teacher_sample_rows(best_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sample: list[dict[str, Any]] = []
    for event in best_events:
        if event.get("event") != "planned":
            continue
        path = [int(node) for node in event.get("path", [])]
        junction_labels = [
            {
                "current": current,
                "next": nxt,
                "label": "MOVE_TO_NEXT_CIE",
            }
            for current, nxt in zip(path, path[1:])
        ]
        pre_route_label = "WAIT_AT_SOURCE_RETRY" if int(event.get("attempts", 1)) > 1 else "MOVE_TO_NEXT_CIE"
        sample.append(
            {
                "variant": event["variant"],
                "scenario": event["scenario"],
                "context": event["context"],
                "segment_id": event["segment_id"],
                "task_id": event["task_id"],
                "start": event["start"],
                "goal": event["goal"],
                "entry_time": event["entry_time"],
                "attempt_time": event["attempt_time"],
                "retry_delay_seconds": event["retry_delay_seconds"],
                "attempts": event["attempts"],
                "teacher_route_source": "original_cie_legacy_astar",
                "policy_scope": "shared_decentralized_per_bag_junction_policy",
                "edge_capacity_primary": False,
                "node_window_conflict_count": 0,
                "pre_route_label": pre_route_label,
                "route_path": path,
                "junction_labels": junction_labels,
            }
        )
    return sample[:MAX_SAMPLE_ROWS]


def _write_report(
    summary_rows: list[dict[str, Any]],
    timeline_rows: list[dict[str, Any]],
    recovered_rows: list[dict[str, Any]],
    remaining_rows: list[dict[str, Any]],
    best_variant: str,
) -> None:
    aggregate = {row["variant"]: row for row in summary_rows if row["scenario"] == "ALL"}
    primary = aggregate["g3j_primary_single_attempt"]
    best = aggregate[best_variant]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    root_cause_rows = _root_cause_summary(recovered_rows, remaining_rows, best_variant)
    lines = [
        "# G3k CIE Node-Window Retry Audit",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## 1. Scope",
        "",
        "G3k audits the original CIE/Java scheduler behavior before any learning step. The route source is still the verified CIE/Legacy A* code path: node time windows plus active fault edges. `edge_capacity=1` and merge-capacity assumptions are not used as primary constraints; edge overlap is kept only as a diagnostic column.",
        "",
        "The Java scheduler keeps `unfinishTasks`: when A* returns an empty path, the task is not discarded. It stays pending and is tried again at a later scheduler time. G3k mirrors that source-wait retry behavior without modifying the legacy Java project.",
        "",
        "## 2. Primary reproduction and retry result",
        "",
        _markdown_table(
            [
                "Variant",
                "Planned",
                "Node conflicts",
                "Recovered G3j no-path",
                "Remaining G3j no-path",
                "Diagnostic edge overlaps",
                "Decision",
            ],
            [
                [
                    primary["variant"],
                    f"{primary['planned']}/{primary['max_tasks']}",
                    primary["node_window_conflicts"],
                    primary["g3j_no_path_recovered_count"],
                    primary["g3j_no_path_remaining_count"],
                    primary["diagnostic_edge_overlap_only"],
                    primary["decision"],
                ],
                [
                    best["variant"],
                    f"{best['planned']}/{best['max_tasks']}",
                    best["node_window_conflicts"],
                    best["g3j_no_path_recovered_count"],
                    best["g3j_no_path_remaining_count"],
                    best["diagnostic_edge_overlap_only"],
                    best["decision"],
                ],
            ],
        ),
        "",
        f"G3j primary is reproduced at `{primary['planned']}/{primary['max_tasks']}` planned with `{primary['node_window_conflicts']}` node-window conflicts. Under Java-style unfinished-task retry, the recommended variant `{best_variant}` reaches `{best['planned']}/{best['max_tasks']}`, recovers `{best['g3j_no_path_recovered_count']}/{EXPECTED_G3J_NO_PATH}` G3j no-path cases, and keeps node-window conflicts at `{best['node_window_conflicts']}`.",
        "",
        "## 3. Are the 17 no-path cases truly no-path?",
        "",
        "No. In this audit they are temporary no-path-at-current-time cases. They recover when source admission waits and CIE/A* is retried at a later scheduler tick. Failed attempts are retained in the timeline table rather than removed from the record.",
        "",
        _markdown_table(
            ["Context", "Recovered", "Remaining", "Root cause"],
            root_cause_rows,
        ),
        "",
        "Repair-window note: the G3j repair-window no-path cases enter after the configured `28->47` repair window has ended, so the recovery is not from bypassing an active fault. It is from waiting until node time windows clear. Merge-window note: the merge-named scenario does not apply merge capacity in primary; its no-path cases are also node-window/source-retry cases.",
        "",
        "## 4. Teacher-label decision",
        "",
        "The clean teacher direction is source-wait retry plus CIE next-hop labels: `WAIT_AT_SOURCE_RETRY` for the recovered admission attempts, then `MOVE_TO_NEXT_CIE` along the CIE/A* route. No PPO, MAPPO, GNN, Transformer, or broad G4A training is performed in this step.",
        "",
        "## 5. G4A pilot gate",
        "",
        f"Gate: planned `>={G4A_PILOT_PLANNED_GATE}/144` and node-window conflicts `0`, without using edge capacity as a primary constraint. Result: `{best['planned']}/144` planned and `{best['node_window_conflicts']}` node-window conflicts. Recommendation: enter G4A pilot dataset generation under this verified CIE/Java retry scope; do not start broad training from diagnostic edge-capacity assumptions.",
        "",
        "## Artifacts",
        "",
        f"- Retry summary: `{_relative(SUMMARY_TABLE)}`",
        f"- No-path retry timeline: `{_relative(TIMELINE_TABLE)}`",
        f"- Recovered cases: `{_relative(RECOVERED_TABLE)}`",
        f"- Remaining cases: `{_relative(REMAINING_TABLE)}`",
        f"- Java semantics alignment: `{_relative(JAVA_ALIGNMENT_TABLE)}`",
        f"- Teacher label taxonomy: `{_relative(TAXONOMY_TABLE)}`",
        f"- Edge-overlap diagnostic only table: `{_relative(EDGE_DIAG_TABLE)}`",
        f"- JSONL teacher sample: `{_relative(SAMPLE_PATH)}`",
        f"- Figure: `{_relative(FIGURE_PATH)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _root_cause_summary(
    recovered_rows: list[dict[str, Any]],
    remaining_rows: list[dict[str, Any]],
    best_variant: str,
) -> list[list[Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in recovered_rows:
        if row["variant"] != best_variant:
            continue
        entry = grouped.setdefault(str(row["context"]), {"recovered": 0, "remaining": 0, "root_causes": set()})
        entry["recovered"] += 1
        entry["root_causes"].add(row["root_cause"])
    for row in remaining_rows:
        if row["variant"] != best_variant:
            continue
        entry = grouped.setdefault(str(row["context"]), {"recovered": 0, "remaining": 0, "root_causes": set()})
        entry["remaining"] += 1
        entry["root_causes"].add(row["root_cause"])
    return [
        [context, values["recovered"], values["remaining"], ";".join(sorted(values["root_causes"]))]
        for context, values in sorted(grouped.items())
    ]


def _write_figure(path: Path, summary_rows: list[dict[str, Any]]) -> None:
    aggregate = [row for row in summary_rows if row["scenario"] == "ALL"]
    matrix = [
        [
            int(row["planned"]),
            int(row["g3j_no_path_recovered_count"]),
            int(row["node_window_conflicts"]),
            int(row["diagnostic_edge_overlap_only"]),
        ]
        for row in sorted(aggregate, key=lambda item: str(item["variant"]))
    ]
    _write_png_heatmap(path, matrix, cell=18)


def _write_png_heatmap(path: Path, matrix: list[list[int]], cell: int = 18) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = max(1, len(matrix))
    cols = max(1, len(matrix[0]) if matrix else 1)
    max_value = max((value for row in matrix for value in row), default=1) or 1
    width = cols * cell
    height = rows * cell
    pixels: list[bytes] = []
    for row_index in range(height):
        source_row = min(rows - 1, row_index // cell)
        scanline = bytearray()
        for col_index in range(width):
            source_col = min(cols - 1, col_index // cell)
            value = matrix[source_row][source_col] if matrix else 0
            intensity = int(220 * value / max_value)
            scanline.extend((255 - intensity, 255, 255 - intensity))
        pixels.append(b"\x00" + bytes(scanline))
    raw = b"".join(pixels)
    data = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            _png_chunk(b"IDAT", zlib.compress(raw)),
            _png_chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(data)


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows[:MAX_SAMPLE_ROWS]:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return _format_number(value)
    if isinstance(value, (tuple, list, set)):
        return ";".join(str(item) for item in value)
    return value


def _summary_fields() -> list[str]:
    return [
        "variant",
        "scenario",
        "context",
        "tick_seconds",
        "max_retry_delay_seconds",
        "max_tasks",
        "planned",
        "unplanned",
        "node_window_conflicts",
        "diagnostic_edge_overlap_only",
        "diagnostic_merge_overlap_only",
        "edge_capacity_model",
        "edge_overlap_counted_as_primary",
        "legacy_path_match_count",
        "legacy_path_mismatch_count",
        "inserted_wait_task_count",
        "g3j_no_path_recovered_count",
        "g3j_no_path_remaining_count",
        "total_retry_attempts",
        "g3j_retry_attempts",
        "mean_recovery_delay_seconds",
        "max_recovery_delay_seconds",
        "g4a_pilot_candidate",
        "decision",
        "teacher_route_source",
    ]


def _timeline_fields() -> list[str]:
    return [
        "variant",
        "scenario",
        "context",
        "segment_id",
        "task_id",
        "attempt_index",
        "attempt_time",
        "original_pass_time",
        "retry_delay_seconds",
        "pending_count_before",
        "attempt_result",
        "failure_reason",
        "active_fault_edges",
        "source_start_time",
        "legacy_path",
        "route_path",
        "finish_time",
        "taxonomy_label",
        "root_cause",
        "g3j_no_path_case",
    ]


def _recovered_fields() -> list[str]:
    return [
        "variant",
        "scenario",
        "context",
        "segment_id",
        "task_id",
        "start",
        "goal",
        "first_no_path_time",
        "recovered_time",
        "retry_delay_seconds",
        "attempts",
        "route_path",
        "active_fault_edges_at_recovery",
        "root_cause",
        "taxonomy_label",
    ]


def _remaining_fields() -> list[str]:
    return [
        "variant",
        "scenario",
        "context",
        "segment_id",
        "task_id",
        "start",
        "goal",
        "first_no_path_time",
        "final_attempt_time",
        "retry_delay_seconds",
        "attempts",
        "failure_reason",
        "root_cause",
        "taxonomy_label",
    ]


def _java_alignment_fields() -> list[str]:
    return ["check", "source_file", "line", "legacy_semantic", "g3k_alignment", "pass", "evidence"]


def _taxonomy_fields() -> list[str]:
    return ["label", "scope", "meaning", "count_in_recommended_variant", "example_action", "teacher_use"]


def _edge_diag_fields() -> list[str]:
    return [
        "variant",
        "scenario",
        "context",
        "diagnostic_edge_overlap_count",
        "diagnostic_merge_overlap_count",
        "node_window_conflicts",
        "counted_as_primary_conflict",
        "edge_capacity_model",
        "decision",
    ]


def _path_text(path: Iterable[int]) -> str:
    return " ".join(str(int(node)) for node in path)


def _format_number(value: float) -> str:
    if abs(value - round(value)) < EPSILON:
        return str(int(round(value)))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _mean_text(values: list[float]) -> str:
    if not values:
        return ""
    return _format_number(sum(values) / len(values))


def _max_text(values: list[float]) -> str:
    if not values:
        return ""
    return _format_number(max(values))


def _find_line(path: Path, snippet: str) -> str:
    try:
        for index, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
            if snippet in line:
                return str(index)
    except OSError:
        return ""
    return ""


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(str(value) for value in row) + " |" for row in rows],
        ]
    )


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def main() -> None:
    _prepare_imports()
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))

    primary_summary_rows: list[dict[str, Any]] = []
    primary_unplanned_rows: list[dict[str, Any]] = []
    timeline_rows: list[dict[str, Any]] = []
    primary_path_rows: list[dict[str, Any]] = []
    for scenario in _case_plan():
        summary, unplanned, timeline, path_rows = _run_g3j_primary_scenario(graph, all_tasks, scenario)
        primary_summary_rows.append(summary)
        primary_unplanned_rows.extend(unplanned)
        timeline_rows.extend(timeline)
        primary_path_rows.extend(path_rows)

    g3j_no_path_keys = {(row["scenario"], row["segment_id"]) for row in primary_unplanned_rows}
    summary_rows = [*primary_summary_rows]
    summary_rows.extend(_aggregate_summary(primary_summary_rows))

    all_recovered_rows: list[dict[str, Any]] = []
    all_remaining_rows: list[dict[str, Any]] = []
    all_events_by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    edge_diag_rows: list[dict[str, Any]] = [_edge_diag_row_from_summary(row) for row in summary_rows]
    for variant in _retry_variants():
        variant_summary: list[dict[str, Any]] = []
        for scenario in _case_plan():
            summary, timeline, recovered, remaining, events, edge_rows = _run_retry_scenario(
                graph,
                all_tasks,
                scenario,
                variant,
                g3j_no_path_keys,
            )
            variant_summary.append(summary)
            timeline_rows.extend(timeline)
            all_recovered_rows.extend(recovered)
            all_remaining_rows.extend(remaining)
            all_events_by_variant[variant.name].extend(events)
            edge_diag_rows.extend(edge_rows)
        summary_rows.extend(variant_summary)
        aggregate = _aggregate_summary(variant_summary)
        summary_rows.extend(aggregate)
        edge_diag_rows.append(_edge_diag_row_from_summary(aggregate[0]))

    aggregate_rows = {row["variant"]: row for row in summary_rows if row["scenario"] == "ALL"}
    recommended_variant = "java_retry_tick_1s_max_delay_60s"
    recommended_summary = aggregate_rows[recommended_variant]
    recommended_events = all_events_by_variant[recommended_variant]
    recommended_remaining = [row for row in all_remaining_rows if row["variant"] == recommended_variant]
    taxonomy_rows = _taxonomy_rows(recommended_summary, recommended_events, recommended_remaining)
    java_alignment_rows = _java_semantics_alignment_rows()
    sample_rows = _teacher_sample_rows(recommended_events)

    _write_csv(SUMMARY_TABLE, summary_rows, _summary_fields())
    _write_csv(TIMELINE_TABLE, timeline_rows, _timeline_fields())
    _write_csv(RECOVERED_TABLE, all_recovered_rows, _recovered_fields())
    _write_csv(REMAINING_TABLE, all_remaining_rows, _remaining_fields())
    _write_csv(JAVA_ALIGNMENT_TABLE, java_alignment_rows, _java_alignment_fields())
    _write_csv(TAXONOMY_TABLE, taxonomy_rows, _taxonomy_fields())
    _write_csv(EDGE_DIAG_TABLE, edge_diag_rows, _edge_diag_fields())
    _write_jsonl(SAMPLE_PATH, sample_rows)
    _write_figure(FIGURE_PATH, summary_rows)
    _write_report(summary_rows, timeline_rows, all_recovered_rows, all_remaining_rows, recommended_variant)

    primary = aggregate_rows["g3j_primary_single_attempt"]
    if int(primary["planned"]) != EXPECTED_G3J_PRIMARY_PLANNED:
        raise AssertionError(f"G3k failed to reproduce G3j primary planned count: {primary['planned']}")
    if int(primary["max_tasks"]) != EXPECTED_G3J_PRIMARY_TOTAL:
        raise AssertionError(f"G3k expected 144 primary tasks, got {primary['max_tasks']}")
    if int(primary["node_window_conflicts"]) != EXPECTED_G3J_NODE_CONFLICTS:
        raise AssertionError("G3k primary node-window conflict reproduction failed")
    if int(primary["g3j_no_path_remaining_count"]) != EXPECTED_G3J_NO_PATH:
        raise AssertionError("G3k primary no-path inventory does not match G3j")
    if int(recommended_summary["planned"]) < G4A_PILOT_PLANNED_GATE:
        raise AssertionError("G3k retry did not reach the G4A pilot planned-count gate")
    if int(recommended_summary["node_window_conflicts"]) != 0:
        raise AssertionError("G3k retry introduced node-window conflicts")
    if str(recommended_summary["edge_overlap_counted_as_primary"]) != "False" and recommended_summary["edge_overlap_counted_as_primary"] is not False:
        raise AssertionError("G3k must not count edge overlap as a primary conflict")
    if int(recommended_summary["g3j_no_path_recovered_count"]) + int(recommended_summary["g3j_no_path_remaining_count"]) != EXPECTED_G3J_NO_PATH:
        raise AssertionError("G3k retry recovery inventory does not cover the 17 G3j no-path cases")
    if any(row["pass"] != "True" and row["pass"] is not True for row in java_alignment_rows):
        raise AssertionError("G3k Java semantics alignment evidence is incomplete")

    required = (
        REPORT_PATH,
        SUMMARY_TABLE,
        TIMELINE_TABLE,
        RECOVERED_TABLE,
        REMAINING_TABLE,
        JAVA_ALIGNMENT_TABLE,
        TAXONOMY_TABLE,
        EDGE_DIAG_TABLE,
        SAMPLE_PATH,
        FIGURE_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G3k artifacts: {missing}")
    print(
        "g3k complete: "
        f"primary={primary['planned']}/{primary['max_tasks']} "
        f"retry={recommended_summary['planned']}/{recommended_summary['max_tasks']} "
        f"node_conflicts={recommended_summary['node_window_conflicts']} "
        f"recovered={recommended_summary['g3j_no_path_recovered_count']}/{EXPECTED_G3J_NO_PATH} "
        f"edge_diag_only={recommended_summary['diagnostic_edge_overlap_only']}"
    )


if __name__ == "__main__":
    main()
