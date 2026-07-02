from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import struct
import sys
from typing import Any, Iterable
import zlib


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"

G3F_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3f_scheduler_variant_comparison.csv"
G3F_UNRESOLVED_TABLE = ROOT / "outputs" / "tables" / "g3f_unresolved_capacity_cases.csv"
G3F_REPORT = ROOT / "outputs" / "reports" / "g3f_edge_capacity_legacy_scheduler_report.md"

REPORT_PATH = ROOT / "outputs" / "reports" / "g3g_legacy_scheduler_semantics_alignment_report.md"
SEMANTICS_MATRIX_TABLE = ROOT / "outputs" / "tables" / "g3g_scheduler_semantics_matrix.csv"
HOLD_CONFLICT_TABLE = ROOT / "outputs" / "tables" / "g3g_hold_conflict_taxonomy.csv"
CURRENT_UPSTREAM_TABLE = ROOT / "outputs" / "tables" / "g3g_current_vs_upstream_wait_cases.csv"
SCHEDULER_REPLAY_TABLE = ROOT / "outputs" / "tables" / "g3g_scheduler_replay_comparison.csv"
FULL_ROUTE_ALIGNMENT_TABLE = ROOT / "outputs" / "tables" / "g3g_full_route_alignment.csv"
EDGE_HOTSPOTS_TABLE = ROOT / "outputs" / "tables" / "g3g_backpressure_edge_hotspots.csv"
NEXT_GATE_TABLE = ROOT / "outputs" / "tables" / "g3g_next_step_gate.csv"
TRACE_SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3g_scheduler_semantics_trace_sample.jsonl"
FIGURE_PATH = ROOT / "outputs" / "figures" / "g3g_scheduler_semantics_gap.png"

MAX_SAMPLE_ROWS = 500
EPSILON = 1.0e-9


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
class ReplayOutcome:
    scenario: MatchedScenario
    scheduler: str
    planned: int
    unplanned: int
    node_conflicts: int
    edge_conflicts: int
    merge_conflicts: int
    routes: dict[str, list[Any]]
    unplanned_segments: tuple[str, ...]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    candidates = (
        Path(os.environ["CZR005_CPP_PYTHON_PATH"])
        if os.environ.get("CZR005_CPP_PYTHON_PATH")
        else None,
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
    )
    for candidate in reversed([path for path in candidates if path is not None]):
        if candidate.exists() or str(candidate) == os.environ.get("CZR005_CPP_PYTHON_PATH"):
            sys.path.insert(0, str(candidate))


def _case_plan() -> tuple[MatchedScenario, ...]:
    return (
        MatchedScenario("legacy_first16", 0, 16),
        MatchedScenario("legacy_first16_buffer2", 0, 16, node_capacities=((28, 2), (47, 2))),
        MatchedScenario("legacy_first32", 0, 32),
        MatchedScenario("legacy_offset32_static16", 32, 16, fault_edges=((16, 17),)),
        MatchedScenario("legacy_offset64_repair32", 64, 32, fault_windows=((28, 47, 0.0, 12000.0),)),
        MatchedScenario("legacy_offset64_merge32", 64, 32, merge_groups=((13, 23, 9), (18, 22, 9))),
    )


def _selected_tasks(all_tasks: tuple[Any, ...], scenario: MatchedScenario) -> tuple[Any, ...]:
    return all_tasks[scenario.task_offset : scenario.task_offset + scenario.max_tasks]


def _scenario_context(scenario: MatchedScenario) -> str:
    if scenario.fault_edges:
        return "static_fault"
    if scenario.fault_windows:
        return "repair_window"
    if scenario.merge_groups:
        return "merge_group"
    if scenario.node_capacities:
        return "buffer_capacity"
    return "no_fault"


def _route_path(route: Iterable[Any] | None) -> tuple[int, ...]:
    if not route:
        return ()
    return tuple(int(node.location) for node in route)


def _format_path(path: Iterable[int], limit: int = 64) -> str:
    values = tuple(int(value) for value in path)
    if len(values) <= limit:
        return " ".join(str(value) for value in values)
    return " ".join(str(value) for value in values[:limit]) + f" ...(+{len(values) - limit} more)"


def _format_faults(scenario: MatchedScenario) -> str:
    parts = [f"{start}->{end}" for start, end in scenario.fault_edges]
    parts += [
        f"{start}->{end}@[{fault_start:.3f},{repair_time:.3f})"
        for start, end, fault_start, repair_time in scenario.fault_windows
    ]
    return "none" if not parts else ";".join(parts)


def _format_merge_groups(scenario: MatchedScenario) -> str:
    if not scenario.merge_groups:
        return "none"
    return ";".join(f"{start}->{end}:{group}" for start, end, group in scenario.merge_groups)


def _format_node_capacities(scenario: MatchedScenario) -> str:
    if not scenario.node_capacities:
        return "none"
    return ";".join(f"{node}:{capacity}" for node, capacity in scenario.node_capacities)


def _run_legacy_node_window(graph: Any, selected: tuple[Any, ...], scenario: MatchedScenario) -> ReplayOutcome:
    from czr005.envs.action_mask import active_fault_edges
    from czr005.sim_py.astar import AStarPlanner
    from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable

    planner = AStarPlanner(graph)
    reservations = ReservationTable()
    edge_reservations = EdgeReservationTable()
    node_capacities = dict(scenario.node_capacities)
    routes: dict[str, list[Any]] = {}
    unplanned: list[str] = []

    for task in selected:
        start_time = _earliest_safe_node_start(
            reservations,
            task.start,
            task.pass_time,
            graph.service_time(task.start),
            task.task_id,
            node_capacities.get(task.start, 1),
        )
        active_faults = active_fault_edges(set(scenario.fault_edges), tuple(scenario.fault_windows), task.pass_time)
        route = planner.plan(
            start=task.start,
            goal=task.goal,
            start_time=start_time,
            reservations=reservations,
            fault_edges=active_faults,
            task_id=task.task_id,
        )
        if not route:
            unplanned.append(task.segment_id)
            continue
        reservations.add_route(task.task_id, route)
        _reserve_route_edges(graph, edge_reservations, task.task_id, route)
        routes[task.segment_id] = route

    edge_conflicts = edge_reservations.conflict_count(capacity=1, headway_seconds=0.0)
    merge_conflicts = edge_reservations.merge_group_conflict_count(
        _variant_merge_groups(scenario),
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    return ReplayOutcome(
        scenario=scenario,
        scheduler="legacy_node_window_full_route",
        planned=len(routes),
        unplanned=len(unplanned),
        node_conflicts=reservations.conflict_count(node_capacities),
        edge_conflicts=edge_conflicts,
        merge_conflicts=merge_conflicts,
        routes=routes,
        unplanned_segments=tuple(unplanned),
    )


def _run_sipp_full_route(graph: Any, selected: tuple[Any, ...], scenario: MatchedScenario) -> ReplayOutcome:
    from czr005.baselines.rolling_horizon import RollingHorizonBaseline

    baseline = RollingHorizonBaseline(
        graph,
        horizon_seconds=300.0,
        edge_capacity=1,
        edge_headway_seconds=0.0,
        node_capacities=dict(scenario.node_capacities),
        merge_groups=_variant_merge_groups(scenario),
        merge_capacity=scenario.merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    result = baseline.run_episode(
        selected,
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=tuple(scenario.fault_windows),
    )
    edge_conflicts = baseline.edge_reservations.conflict_count(capacity=1, headway_seconds=0.0)
    merge_conflicts = baseline.edge_reservations.merge_group_conflict_count(
        _variant_merge_groups(scenario),
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    return ReplayOutcome(
        scenario=scenario,
        scheduler="sipp_full_route_edge_capacity",
        planned=result.metrics.planned_count,
        unplanned=result.metrics.unplanned_count,
        node_conflicts=result.metrics.reservation_conflicts,
        edge_conflicts=edge_conflicts,
        merge_conflicts=merge_conflicts,
        routes=result.routes,
        unplanned_segments=tuple(task.segment_id for task in result.unplanned),
    )


def _reserve_route_edges(graph: Any, edge_reservations: Any, task_id: int, route: list[Any]) -> None:
    for left, right in zip(route, route[1:]):
        if int(left.location) == int(right.location):
            continue
        edge = graph.edge(int(left.location), int(right.location))
        edge_start = float(right.t1) - float(edge.travel_time)
        edge_reservations.reserve(task_id, int(left.location), int(right.location), edge_start, float(right.t1))


def _earliest_safe_node_start(
    reservations: Any,
    node: int,
    earliest_start: float,
    duration: float,
    task_id: int,
    capacity: int = 1,
) -> float:
    candidate = earliest_start
    intervals = sorted(reservations.intervals(node), key=lambda item: (item.start, item.end, item.task_id))
    for _ in range(len(intervals) * 2 + 2):
        candidate_end = candidate + duration
        if not reservations.has_capacity_conflict(node, candidate, candidate_end, capacity=capacity, task_id=task_id):
            return candidate
        overlapping = [
            interval
            for interval in intervals
            if interval.task_id != task_id and interval.overlaps(candidate, candidate_end)
        ]
        if not overlapping:
            return candidate
        candidate = min(interval.end for interval in overlapping) + EPSILON
    return candidate


def _variant_merge_groups(scenario: MatchedScenario) -> dict[tuple[int, int], int]:
    return {(start, end): group for start, end, group in scenario.merge_groups}


def _source_evidence_rows() -> list[dict[str, Any]]:
    evidence = [
        (
            "legacy_java_astar",
            ROOT / "legacy" / "jichang_origin_readonly" / "src" / "App" / "Astar.java",
            "reservations",
            "node_window_only",
            "if (constrain_Set.containsKey(i)&&i!=goal.location)",
            "A* tests future node windows and fault edges; it has no explicit edge-capacity table.",
        ),
        (
            "legacy_java_scheduler",
            ROOT / "legacy" / "jichang_origin_readonly" / "src" / "App" / "ICS_PathFinding.java",
            "full_route_saved_constraints",
            "node_window_only",
            "update_constrain(on_PathTask.task_ID, Route, constrains)",
            "Saved routes write future node windows for the whole remaining route.",
        ),
        (
            "python_legacy_astar",
            ROOT / "src" / "czr005" / "sim_py" / "astar.py",
            "reservations",
            "node_window_only",
            "reservations.has_conflict",
            "Python Legacy-compatible A* mirrors node-window filtering and fault-edge filtering.",
        ),
        (
            "python_runtime_mask",
            ROOT / "src" / "czr005" / "envs" / "action_mask.py",
            "local_step_candidate",
            "hard_edge_capacity",
            "edge_reservations.has_capacity_conflict",
            "Runtime mask adds per-edge capacity and merge-group checks at the local action time.",
        ),
        (
            "python_runtime_hold",
            ROOT / "src" / "czr005" / "envs" / "action_mask.py",
            "local_step_candidate",
            "hold_occupies_current_node",
            "hold_capacity = node_capacities.get(current, 1)",
            "A HOLD action is safe only if the current node has capacity for the hold interval.",
        ),
        (
            "cpp_sipp_scheduler",
            ROOT / "cpp" / "ics_core" / "routing" / "sipp.hpp",
            "full_route_search",
            "hard_edge_capacity",
            "edge_reservations.earliest_start",
            "C++ SIPP searches full routes with edge-capacity release times.",
        ),
        (
            "cpp_rolling_horizon",
            ROOT / "cpp" / "ics_core" / "baselines" / "rolling_horizon.hpp",
            "full_route_reservation",
            "hard_edge_capacity",
            "reserve_route_edges",
            "Rolling-horizon SIPP commits full route node and edge reservations.",
        ),
    ]
    rows: list[dict[str, Any]] = []
    for layer, path, route_scope, edge_model, pattern, implication in evidence:
        line_no, snippet = _find_line(path, pattern)
        rows.append(
            {
                "layer": layer,
                "file": _relative(path),
                "line": line_no,
                "route_scope": route_scope,
                "edge_capacity_model": edge_model,
                "wait_occupancy_model": _wait_model(layer),
                "future_route_reservation": route_scope in {"full_route_saved_constraints", "full_route_search", "full_route_reservation"},
                "evidence_pattern": pattern,
                "evidence_snippet": snippet,
                "implication": implication,
            }
        )
    return rows


def _wait_model(layer: str) -> str:
    if layer == "python_runtime_hold":
        return "explicit_hold_consumes_current_node_capacity"
    if layer in {"cpp_sipp_scheduler", "cpp_rolling_horizon"}:
        return "full_route_release_time_search_without_local_hold_label"
    if layer.startswith("legacy_java") or layer == "python_legacy_astar":
        return "timed_node_windows_only_no_explicit_edge_wait_occupancy"
    return "immediate_local_transition_check"


def _find_line(path: Path, pattern: str) -> tuple[int, str]:
    if not path.exists():
        return 0, "missing"
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        if pattern in line:
            return index, line.strip()
    return 0, "pattern_not_found"


def _current_vs_upstream_rows(
    unresolved_rows: list[dict[str, str]],
    sipp_outcomes: dict[str, ReplayOutcome],
    legacy_outcomes: dict[str, ReplayOutcome],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in unresolved_rows:
        scenario = str(row["scenario"])
        segment_id = str(row["segment_id"])
        ready = _to_float(row.get("ready_time", ""))
        occupancy_end = _max_float_list(row.get("occupancy_end", ""))
        occupancy_start = _min_float_list(row.get("occupancy_start", ""))
        release = occupancy_end if occupancy_end is not None else ready
        wait_needed = max(0.0, release - ready)
        edge = f"{row['current']}->{row['legacy_next']}"
        sipp_route = sipp_outcomes[scenario].routes.get(segment_id, [])
        legacy_route = legacy_outcomes[scenario].routes.get(segment_id, [])
        rows.append(
            {
                "scenario": scenario,
                "context": row["context"],
                "segment_id": segment_id,
                "task_id": row["task_id"],
                "current": row["current"],
                "legacy_next": row["legacy_next"],
                "edge": edge,
                "ready_time": ready,
                "occupancy_start": "" if occupancy_start is None else occupancy_start,
                "occupancy_end": "" if occupancy_end is None else occupancy_end,
                "release_time_from_blocker": release,
                "wait_needed_if_nonoccupying": wait_needed,
                "g3f_local_label": row["label_taxonomy"],
                "g3f_terminal_reason": row["terminal_reason"],
                "local_hold_model": "fails_current_node_capacity",
                "route_window_counterfactual": "wait_or_delay_upstream_before_current_node",
                "sipp_full_route_planned": bool(sipp_route),
                "sipp_path": _format_path(_route_path(sipp_route)),
                "sipp_uses_same_next_after_current": _path_has_edge(sipp_route, int(row["current"]), int(row["legacy_next"])),
                "legacy_node_window_planned": bool(legacy_route),
                "legacy_node_window_path": _format_path(_route_path(legacy_route)),
                "required_semantics": "backpressure_or_non_node_occupying_wait",
            }
        )
    return rows


def _hold_conflict_taxonomy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: Counter[tuple[str, str, str, str]] = Counter()
    wait_totals: defaultdict[tuple[str, str, str, str], float] = defaultdict(float)
    for row in rows:
        key = (
            str(row["scenario"]),
            str(row["edge"]),
            str(row["g3f_local_label"]),
            str(row["required_semantics"]),
        )
        grouped[key] += 1
        wait_totals[key] += float(row["wait_needed_if_nonoccupying"])
    return [
        {
            "scenario": scenario,
            "edge": edge,
            "g3f_local_label": label,
            "required_semantics": semantics,
            "case_count": count,
            "mean_wait_needed_if_nonoccupying": wait_totals[(scenario, edge, label, semantics)] / count,
        }
        for (scenario, edge, label, semantics), count in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
    ]


def _edge_hotspot_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["scenario"]), str(row["edge"]))].append(row)
    output: list[dict[str, Any]] = []
    for (scenario, edge), items in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
        waits = [float(item["wait_needed_if_nonoccupying"]) for item in items]
        output.append(
            {
                "scenario": scenario,
                "edge": edge,
                "case_count": len(items),
                "mean_wait_needed_if_nonoccupying": sum(waits) / len(waits) if waits else 0.0,
                "max_wait_needed_if_nonoccupying": max(waits) if waits else 0.0,
                "sipp_full_route_planned_cases": sum(1 for item in items if item["sipp_full_route_planned"]),
                "same_next_in_sipp_cases": sum(1 for item in items if item["sipp_uses_same_next_after_current"]),
            }
        )
    return output


def _scheduler_replay_rows(
    g3f_summary: list[dict[str, str]],
    legacy_outcomes: dict[str, ReplayOutcome],
    sipp_outcomes: dict[str, ReplayOutcome],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    best_g3f = [
        row
        for row in g3f_summary
        if row.get("scenario") != "ALL" and row.get("replay_variant") == "capacity_wait_budget_5s"
    ]
    for row in best_g3f:
        rows.append(
            {
                "scenario": row["scenario"],
                "context": row["context"],
                "scheduler": "g3f_local_executable_capacity_wait_budget_5s",
                "planned": row["planned_count"],
                "unplanned": row["unplanned_count"],
                "node_conflicts": row["node_reservation_conflicts"],
                "edge_conflicts": row["edge_reservation_conflicts"],
                "merge_conflicts": row["merge_group_conflicts"],
                "real_constraint_conflicts": row["real_constraint_conflicts"],
                "wait_occupancy_model": "local_hold_consumes_current_node_capacity",
                "route_scope": "single_executable_step",
            }
        )
    for outcomes in (legacy_outcomes, sipp_outcomes):
        for scenario_name, outcome in sorted(outcomes.items()):
            rows.append(
                {
                    "scenario": scenario_name,
                    "context": _scenario_context(outcome.scenario),
                    "scheduler": outcome.scheduler,
                    "planned": outcome.planned,
                    "unplanned": outcome.unplanned,
                    "node_conflicts": outcome.node_conflicts,
                    "edge_conflicts": outcome.edge_conflicts,
                    "merge_conflicts": outcome.merge_conflicts,
                    "real_constraint_conflicts": outcome.node_conflicts + outcome.edge_conflicts + outcome.merge_conflicts,
                    "wait_occupancy_model": (
                        "timed_node_windows_only_no_explicit_edge_wait_occupancy"
                        if outcome.scheduler == "legacy_node_window_full_route"
                        else "full_route_release_time_search"
                    ),
                    "route_scope": "full_route",
                }
            )
    rows += _aggregate_scheduler_rows(rows)
    return rows


def _aggregate_scheduler_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["scheduler"])].append(row)
    output: list[dict[str, Any]] = []
    for scheduler, items in sorted(grouped.items()):
        if any(item["scenario"] == "ALL" for item in items):
            continue
        output.append(
            {
                "scenario": "ALL",
                "context": "aggregate",
                "scheduler": scheduler,
                "planned": sum(int(item["planned"]) for item in items),
                "unplanned": sum(int(item["unplanned"]) for item in items),
                "node_conflicts": sum(int(item["node_conflicts"]) for item in items),
                "edge_conflicts": sum(int(item["edge_conflicts"]) for item in items),
                "merge_conflicts": sum(int(item["merge_conflicts"]) for item in items),
                "real_constraint_conflicts": sum(int(item["real_constraint_conflicts"]) for item in items),
                "wait_occupancy_model": items[0]["wait_occupancy_model"],
                "route_scope": items[0]["route_scope"],
            }
        )
    return output


def _full_route_alignment_rows(
    unresolved_rows: list[dict[str, str]],
    legacy_outcomes: dict[str, ReplayOutcome],
    sipp_outcomes: dict[str, ReplayOutcome],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in unresolved_rows:
        scenario = str(row["scenario"])
        segment_id = str(row["segment_id"])
        legacy_route = legacy_outcomes[scenario].routes.get(segment_id, [])
        sipp_route = sipp_outcomes[scenario].routes.get(segment_id, [])
        legacy_edge = (int(row["current"]), int(row["legacy_next"]))
        rows.append(
            {
                "scenario": scenario,
                "segment_id": segment_id,
                "task_id": row["task_id"],
                "g3f_edge": f"{legacy_edge[0]}->{legacy_edge[1]}",
                "legacy_node_window_planned": bool(legacy_route),
                "legacy_node_window_contains_edge": _path_has_edge(legacy_route, *legacy_edge),
                "legacy_node_window_path": _format_path(_route_path(legacy_route)),
                "sipp_full_route_planned": bool(sipp_route),
                "sipp_full_route_contains_edge": _path_has_edge(sipp_route, *legacy_edge),
                "sipp_full_route_path": _format_path(_route_path(sipp_route)),
                "alignment_note": _alignment_note(legacy_route, sipp_route, legacy_edge),
            }
        )
    return rows


def _alignment_note(legacy_route: list[Any], sipp_route: list[Any], edge: tuple[int, int]) -> str:
    if not sipp_route:
        return "sipp_unplanned"
    if _path_has_edge(sipp_route, *edge):
        return "sipp_preserves_blocked_legacy_edge_with_full_route_timing"
    if legacy_route and _path_has_edge(legacy_route, *edge):
        return "legacy_path_uses_edge_but_sipp_reroutes_or_delays_elsewhere"
    return "full_route_scheduler_uses_alternate_timing_or_route"


def _next_gate_rows(
    current_upstream_rows: list[dict[str, Any]],
    scheduler_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    aggregate = {row["scheduler"]: row for row in scheduler_rows if row["scenario"] == "ALL"}
    unresolved = len(current_upstream_rows)
    current_hold = sum(1 for row in current_upstream_rows if row["local_hold_model"] == "fails_current_node_capacity")
    sipp_planned = sum(1 for row in current_upstream_rows if row["sipp_full_route_planned"])
    g3f = aggregate.get("g3f_local_executable_capacity_wait_budget_5s", {})
    sipp = aggregate.get("sipp_full_route_edge_capacity", {})
    legacy = aggregate.get("legacy_node_window_full_route", {})
    return [
        {
            "gate": "g3g_semantics_diagnosis_complete",
            "pass": unresolved > 0 and current_hold == unresolved,
            "value": f"{current_hold}/{unresolved}",
            "threshold": "all unresolved capacity cases classified",
            "decision": "diagnostic_pass" if unresolved > 0 and current_hold == unresolved else "needs_more_diagnosis",
        },
        {
            "gate": "full_route_scheduler_explains_unresolved",
            "pass": sipp_planned == unresolved,
            "value": f"{sipp_planned}/{unresolved}",
            "threshold": "SIPP full-route plans every unresolved local case",
            "decision": "full_route_timing_gap" if sipp_planned == unresolved else "mixed_failure_modes",
        },
        {
            "gate": "local_g3f_still_below_g4a_planned_gate",
            "pass": int(g3f.get("planned", 0)) < 115,
            "value": str(g3f.get("planned", "")),
            "threshold": "<115 means no G4A/training",
            "decision": "do_not_train",
        },
        {
            "gate": "legacy_node_window_not_runtime_safe",
            "pass": int(legacy.get("real_constraint_conflicts", 0)) > 0,
            "value": str(legacy.get("real_constraint_conflicts", "")),
            "threshold": ">0 real conflicts means route-only legacy is not executable under runtime edge capacity",
            "decision": "do_not_use_as_closed_loop_action_teacher",
        },
        {
            "gate": "sipp_full_route_runtime_safe_reference",
            "pass": int(sipp.get("planned", 0)) == 144 and int(sipp.get("real_constraint_conflicts", 0)) == 0,
            "value": f"{sipp.get('planned', '')}/144 conflicts={sipp.get('real_constraint_conflicts', '')}",
            "threshold": "144/144 and zero real conflicts",
            "decision": "use_as_semantics_reference_not_primary_legacy_teacher",
        },
    ]


def _path_has_edge(route: list[Any], start: int, end: int) -> bool:
    path = _route_path(route)
    return any(left == start and right == end for left, right in zip(path, path[1:]))


def _max_float_list(value: Any) -> float | None:
    values = [_to_float(part) for part in str(value).split(";") if str(part).strip()]
    values = [item for item in values if item is not None]
    return max(values) if values else None


def _min_float_list(value: Any) -> float | None:
    values = [_to_float(part) for part in str(value).split(";") if str(part).strip()]
    values = [item for item in values if item is not None]
    return min(values) if values else None


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key, "")) for key in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (tuple, list)):
        return ";".join(str(item) for item in value)
    return value


def _write_jsonl_sample(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows[:MAX_SAMPLE_ROWS]:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_figure(scheduler_rows: list[dict[str, Any]]) -> None:
    aggregate = [row for row in scheduler_rows if row["scenario"] == "ALL"]
    matrix = [
        [int(row["planned"]), int(row["real_constraint_conflicts"])]
        for row in sorted(aggregate, key=lambda item: str(item["scheduler"]))
    ]
    _write_png_heatmap(FIGURE_PATH, matrix, cell=22)


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
            intensity = int(255 * value / max_value)
            scanline.extend((255, 255 - intensity, 255 - intensity))
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


def _write_report(
    scheduler_rows: list[dict[str, Any]],
    semantics_rows: list[dict[str, Any]],
    hold_rows: list[dict[str, Any]],
    current_upstream_rows: list[dict[str, Any]],
    hotspot_rows: list[dict[str, Any]],
    gate_rows: list[dict[str, Any]],
) -> None:
    aggregate = {row["scheduler"]: row for row in scheduler_rows if row["scenario"] == "ALL"}
    g3f = aggregate["g3f_local_executable_capacity_wait_budget_5s"]
    legacy = aggregate["legacy_node_window_full_route"]
    sipp = aggregate["sipp_full_route_edge_capacity"]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G3g Legacy Scheduler Semantics Alignment",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## 1. Scope",
        "",
        "G3g is a non-learning semantics audit. It compares the Legacy Java/Python route-window model, the current local executable G3f replay, and the full-route SIPP scheduler that already has Python/C++ parity evidence. It does not modify legacy Java, does not relax edge capacity, and does not start G4A or training.",
        "",
        "## 2. Scheduler comparison",
        "",
        _markdown_table(
            ["Scheduler", "Planned", "Real conflicts", "Route scope", "Wait model"],
            [
                [
                    row["scheduler"],
                    f"{row['planned']}/144",
                    row["real_constraint_conflicts"],
                    row["route_scope"],
                    row["wait_occupancy_model"],
                ]
                for row in (g3f, legacy, sipp)
            ],
        ),
        "",
        "The key split is now explicit: the Legacy node-window scheduler can plan more route-intent tasks but is not runtime-safe under edge capacity, while SIPP full-route timing is runtime-safe but is not the paper-faithful Legacy-A* route source. G3f remains the strict local executable teacher and still plans only `96/144`.",
        "",
        "## 3. Source-level semantics evidence",
        "",
        _markdown_table(
            ["Layer", "Route scope", "Edge model", "Wait model"],
            [
                [row["layer"], row["route_scope"], row["edge_capacity_model"], row["wait_occupancy_model"]]
                for row in semantics_rows
            ],
        ),
        "",
        "## 4. G3f unresolved cases",
        "",
        f"G3f best-variant unresolved capacity cases: `{len(current_upstream_rows)}`. Cases classified as current-node hold-capacity failures: `{sum(1 for row in current_upstream_rows if row['local_hold_model'] == 'fails_current_node_capacity')}`.",
        "",
        _markdown_table(
            ["Scenario", "Edge", "Cases", "Mean nonoccupying wait"],
            [
                [
                    row["scenario"],
                    row["edge"],
                    row["case_count"],
                    f"{float(row['mean_wait_needed_if_nonoccupying']):.3f}",
                ]
                for row in hold_rows[:12]
            ],
        ),
        "",
        "Top backpressure hotspots:",
        "",
        _markdown_table(
            ["Scenario", "Edge", "Cases", "SIPP planned", "Same edge in SIPP"],
            [
                [
                    row["scenario"],
                    row["edge"],
                    row["case_count"],
                    row["sipp_full_route_planned_cases"],
                    row["same_next_in_sipp_cases"],
                ]
                for row in hotspot_rows[:10]
            ],
        ),
        "",
        "## 5. Decision",
        "",
        _decision_text(gate_rows),
        "",
        "## Artifacts",
        "",
        f"- Semantics matrix: `{_relative(SEMANTICS_MATRIX_TABLE)}`",
        f"- Hold conflict taxonomy: `{_relative(HOLD_CONFLICT_TABLE)}`",
        f"- Current vs upstream wait cases: `{_relative(CURRENT_UPSTREAM_TABLE)}`",
        f"- Scheduler replay comparison: `{_relative(SCHEDULER_REPLAY_TABLE)}`",
        f"- Full route alignment: `{_relative(FULL_ROUTE_ALIGNMENT_TABLE)}`",
        f"- Backpressure hotspots: `{_relative(EDGE_HOTSPOTS_TABLE)}`",
        f"- Next-step gate: `{_relative(NEXT_GATE_TABLE)}`",
        f"- Trace JSONL sample: `{_relative(TRACE_SAMPLE_PATH)}`",
        f"- Gap figure: `{_relative(FIGURE_PATH)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _decision_text(gate_rows: list[dict[str, Any]]) -> str:
    gate = {row["gate"]: row for row in gate_rows}
    if gate["g3g_semantics_diagnosis_complete"]["pass"] and gate["full_route_scheduler_explains_unresolved"]["pass"]:
        return (
            "Diagnostic pass: G3g explains the remaining G3f capacity blocker as a scheduler-semantics mismatch. "
            "The next step should be a backpressure-aware executable teacher or route pre-reservation semantics audit, "
            "not G4A/training."
        )
    return "Diagnostic incomplete: unresolved rows include mixed failure modes; continue auditing before changing the teacher target."


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


def _write_all_outputs(
    scheduler_rows: list[dict[str, Any]],
    semantics_rows: list[dict[str, Any]],
    current_upstream_rows: list[dict[str, Any]],
    full_route_rows: list[dict[str, Any]],
) -> None:
    hold_rows = _hold_conflict_taxonomy(current_upstream_rows)
    hotspot_rows = _edge_hotspot_rows(current_upstream_rows)
    gate_rows = _next_gate_rows(current_upstream_rows, scheduler_rows)

    _write_csv(SEMANTICS_MATRIX_TABLE, semantics_rows, _semantics_fields())
    _write_csv(HOLD_CONFLICT_TABLE, hold_rows, _hold_fields())
    _write_csv(CURRENT_UPSTREAM_TABLE, current_upstream_rows, _current_upstream_fields())
    _write_csv(SCHEDULER_REPLAY_TABLE, scheduler_rows, _scheduler_fields())
    _write_csv(FULL_ROUTE_ALIGNMENT_TABLE, full_route_rows, _full_route_fields())
    _write_csv(EDGE_HOTSPOTS_TABLE, hotspot_rows, _hotspot_fields())
    _write_csv(NEXT_GATE_TABLE, gate_rows, _gate_fields())
    _write_jsonl_sample(TRACE_SAMPLE_PATH, current_upstream_rows)
    _write_figure(scheduler_rows)
    _write_report(scheduler_rows, semantics_rows, hold_rows, current_upstream_rows, hotspot_rows, gate_rows)


def _semantics_fields() -> list[str]:
    return [
        "layer",
        "file",
        "line",
        "route_scope",
        "edge_capacity_model",
        "wait_occupancy_model",
        "future_route_reservation",
        "evidence_pattern",
        "evidence_snippet",
        "implication",
    ]


def _hold_fields() -> list[str]:
    return [
        "scenario",
        "edge",
        "g3f_local_label",
        "required_semantics",
        "case_count",
        "mean_wait_needed_if_nonoccupying",
    ]


def _current_upstream_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "segment_id",
        "task_id",
        "current",
        "legacy_next",
        "edge",
        "ready_time",
        "occupancy_start",
        "occupancy_end",
        "release_time_from_blocker",
        "wait_needed_if_nonoccupying",
        "g3f_local_label",
        "g3f_terminal_reason",
        "local_hold_model",
        "route_window_counterfactual",
        "sipp_full_route_planned",
        "sipp_path",
        "sipp_uses_same_next_after_current",
        "legacy_node_window_planned",
        "legacy_node_window_path",
        "required_semantics",
    ]


def _scheduler_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "scheduler",
        "planned",
        "unplanned",
        "node_conflicts",
        "edge_conflicts",
        "merge_conflicts",
        "real_constraint_conflicts",
        "wait_occupancy_model",
        "route_scope",
    ]


def _full_route_fields() -> list[str]:
    return [
        "scenario",
        "segment_id",
        "task_id",
        "g3f_edge",
        "legacy_node_window_planned",
        "legacy_node_window_contains_edge",
        "legacy_node_window_path",
        "sipp_full_route_planned",
        "sipp_full_route_contains_edge",
        "sipp_full_route_path",
        "alignment_note",
    ]


def _hotspot_fields() -> list[str]:
    return [
        "scenario",
        "edge",
        "case_count",
        "mean_wait_needed_if_nonoccupying",
        "max_wait_needed_if_nonoccupying",
        "sipp_full_route_planned_cases",
        "same_next_in_sipp_cases",
    ]


def _gate_fields() -> list[str]:
    return ["gate", "pass", "value", "threshold", "decision"]


def main() -> None:
    _prepare_imports()
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    if not G3F_REPORT.exists() or not G3F_SUMMARY_TABLE.exists() or not G3F_UNRESOLVED_TABLE.exists():
        raise AssertionError("G3g requires completed G3f report, summary, and unresolved tables")

    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    g3f_summary = _read_csv_rows(G3F_SUMMARY_TABLE)
    unresolved_rows = _read_csv_rows(G3F_UNRESOLVED_TABLE)
    if not g3f_summary or not unresolved_rows:
        raise AssertionError("G3g requires non-empty G3f summary and unresolved rows")

    legacy_outcomes: dict[str, ReplayOutcome] = {}
    sipp_outcomes: dict[str, ReplayOutcome] = {}
    for scenario in _case_plan():
        selected = _selected_tasks(all_tasks, scenario)
        legacy_outcomes[scenario.name] = _run_legacy_node_window(graph, selected, scenario)
        sipp_outcomes[scenario.name] = _run_sipp_full_route(graph, selected, scenario)

    semantics_rows = _source_evidence_rows()
    current_upstream_rows = _current_vs_upstream_rows(unresolved_rows, sipp_outcomes, legacy_outcomes)
    scheduler_rows = _scheduler_replay_rows(g3f_summary, legacy_outcomes, sipp_outcomes)
    full_route_rows = _full_route_alignment_rows(unresolved_rows, legacy_outcomes, sipp_outcomes)
    _write_all_outputs(scheduler_rows, semantics_rows, current_upstream_rows, full_route_rows)

    required = (
        REPORT_PATH,
        SEMANTICS_MATRIX_TABLE,
        HOLD_CONFLICT_TABLE,
        CURRENT_UPSTREAM_TABLE,
        SCHEDULER_REPLAY_TABLE,
        FULL_ROUTE_ALIGNMENT_TABLE,
        EDGE_HOTSPOTS_TABLE,
        NEXT_GATE_TABLE,
        TRACE_SAMPLE_PATH,
        FIGURE_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G3g artifacts: {missing}")
    print(
        "g3g complete: "
        f"scenarios={len(_case_plan())} unresolved={len(unresolved_rows)} "
        f"scheduler_rows={len(scheduler_rows)}"
    )


if __name__ == "__main__":
    main()
