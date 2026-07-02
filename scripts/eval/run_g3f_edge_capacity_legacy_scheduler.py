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

REPORT_PATH = ROOT / "outputs" / "reports" / "g3f_edge_capacity_legacy_scheduler_report.md"
EDGE_BLOCK_LEDGER_TABLE = ROOT / "outputs" / "tables" / "g3f_edge_block_ledger.csv"
EDGE_RELEASE_AUDIT_TABLE = ROOT / "outputs" / "tables" / "g3f_edge_release_time_audit.csv"
EDGE_QUEUE_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3f_edge_queue_replay_summary.csv"
ROUTE_EXECUTABLE_TABLE = ROOT / "outputs" / "tables" / "g3f_route_intent_vs_executable_labels.csv"
WAIT_TAXONOMY_TABLE = ROOT / "outputs" / "tables" / "g3f_wait_label_taxonomy.csv"
SCHEDULER_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3f_scheduler_variant_comparison.csv"
HOTSPOT_TIMELINE_TABLE = ROOT / "outputs" / "tables" / "g3f_hotspot_edge_capacity_timeline.csv"
UNRESOLVED_TABLE = ROOT / "outputs" / "tables" / "g3f_unresolved_capacity_cases.csv"
G4A_ELIGIBILITY_TABLE = ROOT / "outputs" / "tables" / "g3f_g4a_pilot_eligibility.csv"
ROUTE_INTENT_SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3f_route_intent_teacher_sample.jsonl"
EXECUTABLE_SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3f_executable_wait_teacher_sample.jsonl"
HOTSPOT_FIGURE_PATH = ROOT / "outputs" / "figures" / "g3f_edge_hotspot_timeline.png"

G3C_REPLAY_SAFETY_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_replay_safety.csv"
G3C_UNAVAILABLE_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_unavailable_cases.csv"
G3C_COVERAGE_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_label_coverage.csv"

TEACHER_SOURCE = "python_faithful_legacy_astar_edge_capacity_scheduler_g3f"
MAX_DECISIONS_PER_TASK = 128
MAX_WAIT_SECONDS = 3600.0
MAX_SAMPLE_ROWS = 500
EPSILON = 1.0e-9

PRIMARY_EXECUTABLE_TAXA = {
    "MOVE_NOW_LEGACY",
    "WAIT_EDGE_CAPACITY",
    "WAIT_EDGE_QUEUE",
    "WAIT_NODE_CAPACITY",
    "WAIT_MERGE_GROUP",
    "WAIT_FAULT_REPAIR",
    "WAIT_UNTIL_SAFE_LEGACY_NEXT",
    "REROUTE_NOW_LEGACY",
}

WAIT_TAXA = {
    "WAIT_EDGE_CAPACITY",
    "WAIT_EDGE_QUEUE",
    "WAIT_NODE_CAPACITY",
    "WAIT_MERGE_GROUP",
    "WAIT_FAULT_REPAIR",
    "WAIT_UNTIL_SAFE_LEGACY_NEXT",
}

G3F_GATE_PLANNED = 115
G3F_GATE_BRANCH_COVERAGE = 0.85
G3F_GATE_ROUTE_INTENT = 130
G3D_EDGE_CAPACITY_CASES = 541


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
class ReplayVariant:
    name: str
    mode: str
    hold_seconds: float = 1.0
    wait_budget_seconds: float | None = None
    diagnostic: bool = False
    hybrid: bool = False
    route_intent_only: bool = False
    edge_capacity: int = 1
    disable_merge_group: bool = False


@dataclass
class TaskState:
    local_task_index: int
    task: Any
    route: list[Any]
    current: int
    ready_time: float
    waiting_time: float
    decision_count: int = 0
    closed: bool = False


@dataclass(frozen=True)
class ReplayResult:
    scenario: MatchedScenario
    variant: ReplayVariant
    summary: dict[str, Any]
    slices: tuple[dict[str, Any], ...]
    routes: dict[str, list[Any]]
    unplanned: tuple[Any, ...]


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


def _variants() -> tuple[ReplayVariant, ...]:
    return (
        ReplayVariant("g3d_reroute_anchor", "reroute"),
        ReplayVariant("edge_release_wait_scheduler", "edge_release_wait"),
        ReplayVariant("fifo_edge_queue_scheduler", "fifo_queue"),
        ReplayVariant("capacity_wait_budget_5s", "wait_budget", wait_budget_seconds=5.0),
        ReplayVariant("capacity_wait_budget_10s", "wait_budget", wait_budget_seconds=10.0),
        ReplayVariant("capacity_wait_budget_30s", "wait_budget", wait_budget_seconds=30.0),
        ReplayVariant("capacity_wait_budget_60s", "wait_budget", wait_budget_seconds=60.0),
        ReplayVariant("route_intent_only_teacher", "route_intent", route_intent_only=True),
        ReplayVariant("hybrid_executable_teacher", "hybrid", hybrid=True),
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


def _format_path(path: Iterable[int], limit: int = 48) -> str:
    values = tuple(int(value) for value in path)
    if len(values) <= limit:
        return " ".join(str(value) for value in values)
    return " ".join(str(value) for value in values[:limit]) + f" ...(+{len(values) - limit} more)"


def _format_faults(fault_edges: tuple[tuple[int, int], ...]) -> str:
    return "none" if not fault_edges else ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def _format_fault_windows(windows: tuple[tuple[int, int, float, float], ...]) -> str:
    if not windows:
        return "none"
    return ";".join(f"{start}->{end}@[{fault_start:.3f},{repair_time:.3f})" for start, end, fault_start, repair_time in windows)


def _format_node_capacities(capacities: tuple[tuple[int, int], ...]) -> str:
    return "none" if not capacities else ";".join(f"{node}:{capacity}" for node, capacity in sorted(capacities))


def _format_merge_groups(groups: tuple[tuple[int, int, int], ...]) -> str:
    return "none" if not groups else ";".join(f"{start}->{end}:{group}" for start, end, group in sorted(groups))


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ";".join(f"{key}:{value}" for key, value in sorted(counter.items()))


def _candidate_by_next(candidates: tuple[Any, ...], next_node: int | None) -> Any | None:
    if next_node is None:
        return None
    for candidate in candidates:
        if not candidate.is_hold and int(candidate.next_node) == int(next_node):
            return candidate
    return None


def _hold_candidate(candidates: tuple[Any, ...]) -> Any | None:
    for candidate in candidates:
        if candidate.is_hold:
            return candidate
    return None


def _safe_next_nodes(candidates: tuple[Any, ...]) -> tuple[int, ...]:
    return tuple(int(candidate.next_node) for candidate in candidates if candidate.safe and not candidate.is_hold)


def _candidate_next_nodes(candidates: tuple[Any, ...]) -> tuple[int, ...]:
    return tuple(int(candidate.next_node) for candidate in candidates if not candidate.is_hold)


def _blocked_reason(candidate: Any | None, legacy_next: int | None) -> str:
    if legacy_next is None:
        return "legacy_astar_no_path"
    if candidate is None:
        return "not_in_candidate_set"
    if candidate.safe:
        return "none"
    return "+".join(str(reason) for reason in candidate.blocked_reasons) or "unsafe_unknown"


def _active_fault_string(active_faults: set[tuple[int, int]]) -> str:
    if not active_faults:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(active_faults))


def _merge_state(scenario: MatchedScenario) -> str:
    return _format_merge_groups(scenario.merge_groups)


def _buffer_state(scenario: MatchedScenario) -> str:
    return _format_node_capacities(scenario.node_capacities)


def _variant_edge_capacity(variant: ReplayVariant) -> int:
    return variant.edge_capacity


def _variant_merge_capacity(scenario: MatchedScenario, variant: ReplayVariant) -> int:
    return 999 if variant.disable_merge_group else scenario.merge_capacity


def _variant_merge_groups(scenario: MatchedScenario) -> dict[tuple[int, int], int]:
    return {(start, end): group for start, end, group in scenario.merge_groups}


def _run_replay(graph: Any, selected: tuple[Any, ...], scenario: MatchedScenario, variant: ReplayVariant) -> ReplayResult:
    from czr005.baselines.sipp import SIPPNode, SIPPPlanner
    from czr005.envs.action_mask import active_fault_edges, build_action_candidates
    from czr005.sim_py.astar import AStarPlanner
    from czr005.sim_py.event_sim import EpisodeResult
    from czr005.sim_py.metrics import compute_episode_metrics
    from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable

    astar = AStarPlanner(graph)
    sipp = SIPPPlanner(graph)
    reservations = ReservationTable()
    edge_reservations = EdgeReservationTable()
    routes: dict[str, list[Any]] = {}
    events: list[dict[str, Any]] = []
    unplanned: list[Any] = []
    task_by_segment = {task.segment_id: task for task in selected}
    slices: list[dict[str, Any]] = []
    node_capacities = dict(scenario.node_capacities)
    merge_groups = _variant_merge_groups(scenario)
    edge_capacity = _variant_edge_capacity(variant)
    merge_capacity = _variant_merge_capacity(scenario, variant)
    static_faults = set(scenario.fault_edges)
    repair_windows = tuple(scenario.fault_windows)

    event_queue: list[tuple[float, int, int, int, int]] = []
    sequence = 0
    for local_task_index, task in enumerate(selected):
        event_queue.append((float(task.pass_time), sequence, 0, local_task_index, -1))
        sequence += 1
    event_queue.sort()
    states: list[TaskState] = []

    while event_queue:
        _, _, event_kind, local_task_index, state_index = event_queue.pop(0)

        if event_kind == 0:
            task = selected[local_task_index]
            start_duration = graph.service_time(task.start)
            start_time = _earliest_safe_node_start(
                reservations,
                task.start,
                task.pass_time,
                start_duration,
                task.task_id,
                node_capacities.get(task.start, 1),
            )
            start_node = SIPPNode(
                location=task.start,
                t1=start_time,
                t2=start_time + start_duration,
                gcost=start_time,
                hcost=graph.heuristic(task.start, task.goal),
                fcost=start_time + graph.heuristic(task.start, task.goal),
                parent=None,
            )
            reservations.reserve(task.task_id, task.start, start_node.t1, start_node.t2)
            state = TaskState(
                local_task_index=local_task_index,
                task=task,
                route=[start_node],
                current=task.start,
                ready_time=start_node.t2,
                waiting_time=max(0.0, start_time - task.pass_time),
            )
            states.append(state)
            created_state_index = len(states) - 1
            if task.start == task.goal:
                state.closed = True
                routes[task.segment_id] = list(state.route)
                events.append(_planned_event(task, state.route, state.decision_count, state.waiting_time, variant.name))
            else:
                _push_event(event_queue, (state.ready_time, sequence, 1, local_task_index, created_state_index))
                sequence += 1
            continue

        state = states[state_index]
        if state.closed:
            continue

        task = state.task
        active_faults = active_fault_edges(static_faults, repair_windows, state.ready_time)
        candidates = build_action_candidates(
            graph=graph,
            task=task,
            current=state.current,
            ready_time=state.ready_time,
            reservations=reservations,
            edge_reservations=edge_reservations,
            edge_capacity=edge_capacity,
            edge_headway_seconds=0.0,
            node_capacities=node_capacities,
            merge_groups=merge_groups,
            merge_capacity=merge_capacity,
            merge_headway_seconds=scenario.merge_headway_seconds,
            fault_edges=static_faults,
            fault_windows=repair_windows,
            hold_seconds=variant.hold_seconds,
            require_reachable_goal=True,
        )
        legacy_route = astar.plan(
            start=state.current,
            goal=task.goal,
            start_time=max(0.0, state.ready_time - graph.service_time(state.current)),
            reservations=reservations,
            fault_edges=active_faults,
            task_id=task.task_id,
        )
        route_suffix = _route_path(legacy_route)
        legacy_next = int(route_suffix[1]) if len(route_suffix) > 1 else None
        legacy_candidate = _candidate_by_next(candidates, legacy_next)
        earliest = (
            _earliest_safe_transition(
                graph=graph,
                task=task,
                current=state.current,
                next_node=legacy_next,
                ready_time=state.ready_time,
                reservations=reservations,
                edge_reservations=edge_reservations,
                edge_capacity=edge_capacity,
                node_capacities=node_capacities,
                merge_groups=merge_groups,
                merge_capacity=merge_capacity,
                merge_headway_seconds=scenario.merge_headway_seconds,
                static_faults=static_faults,
                fault_windows=repair_windows,
            )
            if legacy_next is not None
            else None
        )

        state.decision_count += 1
        decision = _choose_decision(
            graph=graph,
            astar=astar,
            sipp=sipp,
            scenario=scenario,
            variant=variant,
            task=task,
            state=state,
            candidates=candidates,
            reservations=reservations,
            edge_reservations=edge_reservations,
            active_faults=active_faults,
            static_faults=static_faults,
            repair_windows=repair_windows,
            node_capacities=node_capacities,
            merge_groups=merge_groups,
            edge_capacity=edge_capacity,
            merge_capacity=merge_capacity,
            legacy_route=legacy_route,
            route_suffix=route_suffix,
            legacy_next=legacy_next,
            legacy_candidate=legacy_candidate,
            earliest=earliest,
        )
        row = _decision_row(
            scenario=scenario,
            variant=variant,
            state=state,
            candidates=candidates,
            legacy_route=legacy_route,
            route_suffix=route_suffix,
            legacy_next=legacy_next,
            legacy_candidate=legacy_candidate,
            earliest=earliest,
            active_faults=active_faults,
            decision=decision,
            ordinal=len(slices) + 1,
        )
        slices.append(row)

        executed_kind = decision["executed_kind"]
        if executed_kind == "unplanned":
            _mark_unplanned(unplanned, events, reservations, edge_reservations, task, state, str(decision["terminal_reason"]), variant.name)
            state.closed = True
            continue

        if executed_kind == "hold":
            hold_until = float(decision["hold_until_time"])
            if hold_until <= state.ready_time + EPSILON:
                hold_until = state.ready_time + variant.hold_seconds
            state.waiting_time += hold_until - state.ready_time
            state.route[-1].t2 = hold_until
            state.route[-1].gcost = hold_until
            state.route[-1].fcost = state.route[-1].gcost + state.route[-1].hcost
            reservations.reserve(task.task_id, state.current, state.route[-1].t1, state.route[-1].t2)
            state.ready_time = hold_until
        elif executed_kind == "move":
            next_node = int(decision["executed_next"])
            edge_start = float(decision["edge_start"])
            edge_end = float(decision["edge_end"])
            node_start = float(decision["node_start"])
            node_end = float(decision["node_end"])
            if edge_start > state.ready_time + EPSILON:
                state.waiting_time += edge_start - state.ready_time
                state.route[-1].t2 = edge_start
                state.route[-1].gcost = edge_start
                state.route[-1].fcost = state.route[-1].gcost + state.route[-1].hcost
                reservations.reserve(task.task_id, state.current, state.route[-1].t1, state.route[-1].t2)
            edge_reservations.reserve(task.task_id, state.current, next_node, edge_start, edge_end)
            reservations.reserve(task.task_id, next_node, node_start, node_end)
            state.route.append(
                SIPPNode(
                    location=next_node,
                    t1=node_start,
                    t2=node_end,
                    gcost=node_start,
                    hcost=graph.heuristic(next_node, task.goal),
                    fcost=node_start + graph.heuristic(next_node, task.goal),
                    parent=state.route[-1],
                )
            )
            state.current = next_node
            state.ready_time = node_end
        else:
            raise AssertionError(f"unknown executed kind: {executed_kind}")

        if state.current == task.goal:
            routes[task.segment_id] = list(state.route)
            events.append(_planned_event(task, state.route, state.decision_count, state.waiting_time, variant.name))
            state.closed = True
            continue
        if state.decision_count >= MAX_DECISIONS_PER_TASK:
            _mark_unplanned(unplanned, events, reservations, edge_reservations, task, state, "max_decisions", variant.name)
            state.closed = True
            continue
        _push_event(event_queue, (state.ready_time, sequence, 1, state.local_task_index, state_index))
        sequence += 1

    result = EpisodeResult(
        routes=routes,
        unplanned=unplanned,
        events=events,
        metrics=compute_episode_metrics(routes, task_by_segment, unplanned, reservations, node_capacities),
    )
    edge_conflicts = edge_reservations.conflict_count(capacity=edge_capacity, headway_seconds=0.0)
    merge_conflicts = edge_reservations.merge_group_conflict_count(
        merge_groups=merge_groups,
        merge_capacity=merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    real_edge_conflicts = edge_reservations.conflict_count(capacity=1, headway_seconds=0.0)
    real_merge_conflicts = edge_reservations.merge_group_conflict_count(
        merge_groups=merge_groups,
        merge_capacity=scenario.merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    summary = _summary_row(
        scenario=scenario,
        variant=variant,
        metrics=result.metrics.to_dict(),
        slices=slices,
        planned_count=result.metrics.planned_count,
        unplanned_count=result.metrics.unplanned_count,
        edge_conflicts=edge_conflicts,
        merge_conflicts=merge_conflicts,
        real_edge_conflicts=real_edge_conflicts,
        real_merge_conflicts=real_merge_conflicts,
    )
    return ReplayResult(
        scenario=scenario,
        variant=variant,
        summary=summary,
        slices=tuple(slices),
        routes=routes,
        unplanned=tuple(unplanned),
    )


def _choose_decision(
    graph: Any,
    astar: Any,
    sipp: Any,
    scenario: MatchedScenario,
    variant: ReplayVariant,
    task: Any,
    state: TaskState,
    candidates: tuple[Any, ...],
    reservations: Any,
    edge_reservations: Any,
    active_faults: set[tuple[int, int]],
    static_faults: set[tuple[int, int]],
    repair_windows: tuple[tuple[int, int, float, float], ...],
    node_capacities: dict[int, int],
    merge_groups: dict[tuple[int, int], int],
    edge_capacity: int,
    merge_capacity: int,
    legacy_route: list[Any],
    route_suffix: tuple[int, ...],
    legacy_next: int | None,
    legacy_candidate: Any | None,
    earliest: dict[str, Any] | None,
) -> dict[str, Any]:
    if variant.route_intent_only:
        return {
            "taxonomy": "ROUTE_INTENT_LEGACY",
            "label_kind": "route_intent",
            "label_source": "legacy_astar_route_intent_only",
            "label_next": "" if legacy_next is None else legacy_next,
            "executed_kind": "unplanned",
            "executed_next": "",
            "edge_start": "",
            "edge_end": "",
            "node_start": "",
            "node_end": "",
            "hold_until_time": "",
            "hold_duration": 0.0,
            "post_label_safe": legacy_next is not None,
            "terminal_reason": "route_intent_only_no_execution",
            "reroute_attempted": False,
            "sipp_repair_attempted": False,
        }

    if legacy_candidate is not None and legacy_candidate.safe:
        return _move_decision(
            taxonomy="MOVE_NOW_LEGACY",
            label_source="legacy_route_next",
            candidate=legacy_candidate,
            hold_until_time="",
            hold_duration=0.0,
            terminal_reason="",
            reroute_attempted=False,
            sipp_repair_attempted=False,
        )

    if variant.mode in {"edge_release_wait", "fifo_queue"}:
        wait_decision = _wait_until_release_decision(
            state=state,
            legacy_next=legacy_next,
            legacy_candidate=legacy_candidate,
            earliest=earliest,
            block_reason=_blocked_reason(legacy_candidate, legacy_next),
            label_source=(
                "fifo_edge_queue_earliest_release"
                if variant.mode == "fifo_queue"
                else "edge_capacity_earliest_release"
            ),
            queue_label=variant.mode == "fifo_queue",
        )
        if wait_decision is not None:
            return wait_decision

    if variant.mode == "wait_budget":
        wait_budget_decision = _wait_budget_or_reroute_decision(
            graph=graph,
            astar=astar,
            task=task,
            state=state,
            candidates=candidates,
            reservations=reservations,
            active_faults=active_faults,
            legacy_next=legacy_next,
            legacy_candidate=legacy_candidate,
            earliest=earliest,
            wait_budget_seconds=float(variant.wait_budget_seconds or 0.0),
        )
        if wait_budget_decision is not None:
            return wait_budget_decision

    if variant.hybrid:
        wait_decision = _wait_until_release_decision(
            state=state,
            legacy_next=legacy_next,
            legacy_candidate=legacy_candidate,
            earliest=earliest,
            block_reason=_blocked_reason(legacy_candidate, legacy_next),
            label_source="hybrid_legacy_wait_until_release",
            queue_label=False,
        )
        if wait_decision is not None:
            return wait_decision

    if variant.mode == "reroute":
        reroute = _reroute_decision(
            graph=graph,
            astar=astar,
            task=task,
            state=state,
            candidates=candidates,
            reservations=reservations,
            active_faults=active_faults,
        )
        if reroute is not None:
            return reroute

    if variant.hybrid:
        repair = _sipp_or_fallback_repair(
            sipp=sipp,
            task=task,
            state=state,
            candidates=candidates,
            reservations=reservations,
            edge_reservations=edge_reservations,
            edge_capacity=edge_capacity,
            node_capacities=node_capacities,
            merge_groups=merge_groups,
            merge_capacity=merge_capacity,
            merge_headway_seconds=scenario.merge_headway_seconds,
            active_faults=active_faults,
        )
        if repair is not None:
            return repair

    hold = _hold_candidate(candidates)
    if hold is not None and hold.safe:
        taxonomy = (
            "LEGACY_NO_PATH"
            if legacy_next is None
            else "LEGACY_NEXT_TEMPORARILY_BLOCKED"
            if earliest and earliest.get("reachable")
            else "LEGACY_NEXT_GLOBALLY_UNSAFE"
        )
        return {
            "taxonomy": taxonomy,
            "label_kind": "hold_no_path_probe" if legacy_next is None else "hold",
            "label_source": "shield_hold_after_legacy_no_path" if legacy_next is None else "shield_hold_after_blocked_legacy_next",
            "label_next": "" if legacy_next is None else legacy_next,
            "executed_kind": "hold",
            "executed_next": state.current,
            "edge_start": "",
            "edge_end": "",
            "node_start": state.ready_time,
            "node_end": hold.node_end,
            "hold_until_time": hold.node_end,
            "hold_duration": hold.node_end - state.ready_time,
            "post_label_safe": hold.safe,
            "terminal_reason": "",
            "reroute_attempted": False,
            "sipp_repair_attempted": False,
        }

    return {
        "taxonomy": "LEGACY_NO_PATH" if legacy_next is None else "ABSTAIN_NO_TEACHER",
        "label_kind": "no_teacher",
        "label_source": "legacy_no_path" if legacy_next is None else "abstain_no_safe_hold",
        "label_next": "" if legacy_next is None else legacy_next,
        "executed_kind": "unplanned",
        "executed_next": "",
        "edge_start": "",
        "edge_end": "",
        "node_start": "",
        "node_end": "",
        "hold_until_time": "",
        "hold_duration": 0.0,
        "post_label_safe": False,
        "terminal_reason": "legacy_astar_no_path" if legacy_next is None else _blocked_reason(legacy_candidate, legacy_next),
        "reroute_attempted": variant.mode == "reroute",
        "sipp_repair_attempted": variant.hybrid,
    }


def _move_decision(
    taxonomy: str,
    label_source: str,
    candidate: Any,
    hold_until_time: Any,
    hold_duration: float,
    terminal_reason: str,
    reroute_attempted: bool,
    sipp_repair_attempted: bool,
) -> dict[str, Any]:
    return {
        "taxonomy": taxonomy,
        "label_kind": "move",
        "label_source": label_source,
        "label_next": candidate.next_node,
        "executed_kind": "move",
        "executed_next": candidate.next_node,
        "edge_start": candidate.edge_start,
        "edge_end": candidate.edge_end,
        "node_start": candidate.node_start,
        "node_end": candidate.node_end,
        "hold_until_time": hold_until_time,
        "hold_duration": hold_duration,
        "post_label_safe": candidate.safe,
        "terminal_reason": terminal_reason,
        "reroute_attempted": reroute_attempted,
        "sipp_repair_attempted": sipp_repair_attempted,
    }


def _wait_until_release_decision(
    state: TaskState,
    legacy_next: int | None,
    legacy_candidate: Any | None,
    earliest: dict[str, Any] | None,
    block_reason: str,
    label_source: str,
    queue_label: bool,
) -> dict[str, Any] | None:
    if legacy_next is None or legacy_candidate is None:
        return None
    if not earliest or not earliest.get("reachable"):
        return None
    edge_start = float(earliest["edge_start"])
    hold_duration = max(0.0, edge_start - state.ready_time)
    if hold_duration > MAX_WAIT_SECONDS:
        return None
    taxonomy = "WAIT_EDGE_QUEUE" if queue_label and "edge_capacity" in block_reason else _wait_taxonomy(block_reason)
    return {
        "taxonomy": taxonomy,
        "label_kind": "wait_then_move",
        "label_source": label_source,
        "label_next": legacy_next,
        "executed_kind": "move",
        "executed_next": legacy_next,
        "edge_start": edge_start,
        "edge_end": earliest["edge_end"],
        "node_start": earliest["node_start"],
        "node_end": earliest["node_end"],
        "hold_until_time": edge_start,
        "hold_duration": hold_duration,
        "post_label_safe": True,
        "terminal_reason": "",
        "reroute_attempted": False,
        "sipp_repair_attempted": False,
        "queue_rank": earliest.get("queue_rank", ""),
        "queue_length": earliest.get("queue_length", ""),
        "earliest_release_time": earliest.get("earliest_release_time", edge_start),
        "wait_blocker_task_ids": earliest.get("wait_blocker_task_ids", ""),
    }


def _wait_budget_or_reroute_decision(
    graph: Any,
    astar: Any,
    task: Any,
    state: TaskState,
    candidates: tuple[Any, ...],
    reservations: Any,
    active_faults: set[tuple[int, int]],
    legacy_next: int | None,
    legacy_candidate: Any | None,
    earliest: dict[str, Any] | None,
    wait_budget_seconds: float,
) -> dict[str, Any] | None:
    block_reason = _blocked_reason(legacy_candidate, legacy_next)
    wait_needed = float(earliest.get("hold_duration", 0.0)) if earliest and earliest.get("reachable") else MAX_WAIT_SECONDS + 1.0
    if wait_needed > wait_budget_seconds:
        reroute = _reroute_decision(
            graph=graph,
            astar=astar,
            task=task,
            state=state,
            candidates=candidates,
            reservations=reservations,
            active_faults=active_faults,
        )
        if reroute is not None:
            reroute["label_source"] = f"legacy_reroute_after_wait_budget_{wait_budget_seconds:g}s"
            return reroute
    return _wait_until_release_decision(
        state=state,
        legacy_next=legacy_next,
        legacy_candidate=legacy_candidate,
        earliest=earliest,
        block_reason=block_reason,
        label_source=f"capacity_wait_budget_{wait_budget_seconds:g}s",
        queue_label=False,
    )


def _wait_taxonomy(block_reason: str) -> str:
    reasons = set(part for part in block_reason.split("+") if part)
    if "edge_capacity" in reasons:
        return "WAIT_EDGE_CAPACITY"
    if "merge_group" in reasons:
        return "WAIT_MERGE_GROUP"
    if "node_reservation" in reasons:
        return "WAIT_NODE_CAPACITY"
    if "fault_edge" in reasons:
        return "WAIT_FAULT_REPAIR"
    return "WAIT_UNTIL_SAFE_LEGACY_NEXT"


def _reroute_decision(
    graph: Any,
    astar: Any,
    task: Any,
    state: TaskState,
    candidates: tuple[Any, ...],
    reservations: Any,
    active_faults: set[tuple[int, int]],
) -> dict[str, Any] | None:
    safe_moves = [candidate for candidate in candidates if candidate.safe and not candidate.is_hold]
    scored: list[tuple[tuple[float, float, int], Any]] = []
    for candidate in safe_moves:
        if candidate.next_node == task.goal:
            scored.append(((0.0, candidate.travel_time, candidate.next_node), candidate))
            continue
        suffix = astar.plan(
            start=candidate.next_node,
            goal=task.goal,
            start_time=max(0.0, candidate.node_end - graph.service_time(candidate.next_node)),
            reservations=reservations,
            fault_edges=active_faults,
            task_id=task.task_id,
        )
        if suffix:
            scored.append(((graph.heuristic(candidate.next_node, task.goal), candidate.travel_time, candidate.next_node), candidate))
    if not scored:
        return None
    _, chosen = min(scored, key=lambda item: item[0])
    return _move_decision(
        taxonomy="REROUTE_NOW_LEGACY",
        label_source="legacy_reroute_from_current",
        candidate=chosen,
        hold_until_time="",
        hold_duration=0.0,
        terminal_reason="",
        reroute_attempted=True,
        sipp_repair_attempted=False,
    )


def _sipp_or_fallback_repair(
    sipp: Any,
    task: Any,
    state: TaskState,
    candidates: tuple[Any, ...],
    reservations: Any,
    edge_reservations: Any,
    edge_capacity: int,
    node_capacities: dict[int, int],
    merge_groups: dict[tuple[int, int], int],
    merge_capacity: int,
    merge_headway_seconds: float,
    active_faults: set[tuple[int, int]],
) -> dict[str, Any] | None:
    route = sipp.plan(
        start=state.current,
        goal=task.goal,
        start_time=max(0.0, state.ready_time),
        reservations=reservations,
        edge_reservations=edge_reservations,
        edge_capacity=edge_capacity,
        edge_headway_seconds=0.0,
        node_capacities=node_capacities,
        merge_groups=merge_groups,
        merge_capacity=merge_capacity,
        merge_headway_seconds=merge_headway_seconds,
        fault_edges=active_faults,
        task_id=task.task_id,
    )
    if len(route) > 1:
        candidate = _candidate_by_next(candidates, int(route[1].location))
        if candidate is not None and candidate.safe:
            return _move_decision(
                taxonomy="SIPP_REPAIR_MOVE",
                label_source="sipp_repair",
                candidate=candidate,
                hold_until_time="",
                hold_duration=0.0,
                terminal_reason="",
                reroute_attempted=False,
                sipp_repair_attempted=True,
            )
    safe_moves = [candidate for candidate in candidates if candidate.safe and not candidate.is_hold]
    if safe_moves:
        chosen = min(safe_moves, key=lambda candidate: (candidate.heuristic_to_goal, candidate.travel_time, candidate.next_node))
        return _move_decision(
            taxonomy="FALLBACK_SAFE_MOVE",
            label_source="fallback_safe_shortest",
            candidate=chosen,
            hold_until_time="",
            hold_duration=0.0,
            terminal_reason="",
            reroute_attempted=False,
            sipp_repair_attempted=True,
        )
    return None


def _decision_row(
    scenario: MatchedScenario,
    variant: ReplayVariant,
    state: TaskState,
    candidates: tuple[Any, ...],
    legacy_route: list[Any],
    route_suffix: tuple[int, ...],
    legacy_next: int | None,
    legacy_candidate: Any | None,
    earliest: dict[str, Any] | None,
    active_faults: set[tuple[int, int]],
    decision: dict[str, Any],
    ordinal: int,
) -> dict[str, Any]:
    block_reason = _blocked_reason(legacy_candidate, legacy_next)
    teacher_finish = float(legacy_route[-1].t2) if legacy_route else ""
    taxonomy = str(decision["taxonomy"])
    earliest_reachable = bool(earliest and earliest.get("reachable"))
    return {
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "replay_variant": variant.name,
        "variant_mode": variant.mode,
        "diagnostic_ablation": variant.diagnostic,
        "teacher_source": TEACHER_SOURCE,
        "decision_ordinal": ordinal,
        "task_decision_ordinal": state.decision_count,
        "task_index": state.local_task_index,
        "segment_id": state.task.segment_id,
        "task_id": state.task.task_id,
        "source_line": state.task.source_line,
        "current": state.current,
        "goal": state.task.goal,
        "ready_time": state.ready_time,
        "candidate_next_nodes": _format_path(_candidate_next_nodes(candidates)),
        "safe_next_nodes": _format_path(_safe_next_nodes(candidates)),
        "legacy_route_suffix": _format_path(route_suffix),
        "legacy_next": "" if legacy_next is None else legacy_next,
        "route_intent_label": "ROUTE_INTENT_LEGACY" if legacy_next is not None else "ROUTE_INTENT_NO_PATH",
        "label_taxonomy": taxonomy,
        "executable_label": taxonomy,
        "label_kind": decision["label_kind"],
        "label_next": decision["label_next"],
        "hold_until_time": decision["hold_until_time"],
        "hold_duration": decision["hold_duration"],
        "earliest_safe_time": earliest["edge_start"] if earliest_reachable else "",
        "earliest_release_time": decision.get("earliest_release_time", earliest["edge_start"] if earliest_reachable else ""),
        "earliest_hold_duration": earliest["hold_duration"] if earliest_reachable else "",
        "earliest_safe_status": earliest["reason"] if earliest else "",
        "queue_rank": decision.get("queue_rank", earliest.get("queue_rank", "") if earliest else ""),
        "queue_length": decision.get("queue_length", earliest.get("queue_length", "") if earliest else ""),
        "wait_blocker_task_ids": decision.get("wait_blocker_task_ids", earliest.get("wait_blocker_task_ids", "") if earliest else ""),
        "occupying_task_ids": earliest.get("occupying_task_ids", "") if earliest else "",
        "occupancy_start": earliest.get("occupancy_start", "") if earliest else "",
        "occupancy_end": earliest.get("occupancy_end", "") if earliest else "",
        "can_current_node_hold": earliest.get("can_current_node_hold", "") if earliest else "",
        "block_reason": block_reason,
        "block_reason_detail": block_reason,
        "label_source": decision["label_source"],
        "post_label_safe": decision["post_label_safe"],
        "teacher_finish_time": teacher_finish,
        "branch_or_linear": "branch" if len(_candidate_next_nodes(candidates)) >= 2 else "linear",
        "fault_state": _active_fault_string(active_faults),
        "repair_state": _format_fault_windows(scenario.fault_windows),
        "merge_state": _merge_state(scenario),
        "buffer_state": _buffer_state(scenario),
        "executed_kind": decision["executed_kind"],
        "executed_next": decision["executed_next"],
        "edge_start": decision["edge_start"],
        "edge_end": decision["edge_end"],
        "node_start": decision["node_start"],
        "node_end": decision["node_end"],
        "terminal_reason": decision["terminal_reason"],
        "reroute_attempted": decision["reroute_attempted"],
        "sipp_repair_attempted": decision["sipp_repair_attempted"],
        "g4a_primary_eligible": taxonomy in PRIMARY_EXECUTABLE_TAXA
        and bool(decision["post_label_safe"])
        and not variant.diagnostic
        and not variant.hybrid
        and not variant.route_intent_only,
    }


def _summary_row(
    scenario: MatchedScenario,
    variant: ReplayVariant,
    metrics: dict[str, Any],
    slices: list[dict[str, Any]],
    planned_count: int,
    unplanned_count: int,
    edge_conflicts: int,
    merge_conflicts: int,
    real_edge_conflicts: int,
    real_merge_conflicts: int,
) -> dict[str, Any]:
    taxonomy = Counter(str(row["label_taxonomy"]) for row in slices)
    decisions = len(slices)
    legacy_move = sum(1 for row in slices if row["legacy_next"] != "")
    move_now = taxonomy["MOVE_NOW_LEGACY"]
    wait_edge = taxonomy["WAIT_EDGE_CAPACITY"]
    wait_queue = taxonomy["WAIT_EDGE_QUEUE"]
    wait_node = taxonomy["WAIT_NODE_CAPACITY"]
    wait_merge = taxonomy["WAIT_MERGE_GROUP"]
    wait_fault = taxonomy["WAIT_FAULT_REPAIR"]
    wait_generic = taxonomy["WAIT_UNTIL_SAFE_LEGACY_NEXT"]
    wait_total = wait_edge + wait_queue + wait_node + wait_merge + wait_fault + wait_generic
    reroute = taxonomy["REROUTE_NOW_LEGACY"]
    primary = move_now + wait_total + reroute
    branch_rows = [row for row in slices if row["branch_or_linear"] == "branch"]
    branch_primary = sum(1 for row in branch_rows if row["label_taxonomy"] in PRIMARY_EXECUTABLE_TAXA)
    route_intent_task_count = len({row["segment_id"] for row in slices if row["legacy_next"] != ""})
    unresolved_edge_capacity = sum(
        1
        for row in slices
        if "edge_capacity" in str(row["block_reason"]) and str(row["label_taxonomy"]) not in PRIMARY_EXECUTABLE_TAXA
    )
    post_conflicts = int(metrics["reservation_conflicts"]) + edge_conflicts + merge_conflicts
    real_conflicts = int(metrics["reservation_conflicts"]) + real_edge_conflicts + real_merge_conflicts
    wait_durations = [float(row["hold_duration"]) for row in slices if str(row["hold_duration"]) not in {"", "0", "0.0"}]
    return {
        **metrics,
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "replay_variant": variant.name,
        "variant_mode": variant.mode,
        "diagnostic_ablation": variant.diagnostic,
        "hybrid_repair": variant.hybrid,
        "max_tasks": scenario.max_tasks,
        "planned_count": planned_count,
        "unplanned_count": unplanned_count,
        "decision_count": decisions,
        "legacy_route_next_labels": legacy_move,
        "route_intent_task_coverage": route_intent_task_count,
        "move_now_legacy_labels": move_now,
        "wait_edge_capacity_labels": wait_edge,
        "wait_edge_queue_labels": wait_queue,
        "wait_node_capacity_labels": wait_node,
        "wait_merge_group_labels": wait_merge,
        "wait_fault_repair_labels": wait_fault,
        "wait_until_safe_labels": wait_generic,
        "wait_executable_labels": wait_total,
        "reroute_now_legacy_labels": reroute,
        "legacy_no_path_labels": taxonomy["LEGACY_NO_PATH"],
        "temporarily_blocked_labels": taxonomy["LEGACY_NEXT_TEMPORARILY_BLOCKED"],
        "globally_unsafe_labels": taxonomy["LEGACY_NEXT_GLOBALLY_UNSAFE"],
        "fallback_safe_labels": taxonomy["FALLBACK_SAFE_MOVE"],
        "sipp_repair_labels": taxonomy["SIPP_REPAIR_MOVE"],
        "abstain_labels": taxonomy["ABSTAIN_NO_TEACHER"],
        "route_intent_only_labels": taxonomy["ROUTE_INTENT_LEGACY"],
        "primary_g4a_label_count": primary,
        "primary_g4a_label_coverage": _ratio(primary, decisions),
        "branch_decision_count": len(branch_rows),
        "branch_effective_label_coverage": _ratio(branch_primary, len(branch_rows)),
        "unresolved_edge_capacity_cases": unresolved_edge_capacity,
        "unresolved_edge_capacity_share_of_g3d": _ratio(unresolved_edge_capacity, G3D_EDGE_CAPACITY_CASES),
        "mean_wait_inserted": sum(wait_durations) / len(wait_durations) if wait_durations else 0.0,
        "max_wait_inserted": max(wait_durations) if wait_durations else 0.0,
        "node_reservation_conflicts": metrics["reservation_conflicts"],
        "edge_reservation_conflicts": edge_conflicts,
        "merge_group_conflicts": merge_conflicts,
        "post_shield_conflicts": post_conflicts,
        "real_constraint_conflicts": real_conflicts,
        "label_taxonomy_distribution": _format_counter(taxonomy),
        "block_reason_distribution": _format_counter(Counter(str(row["block_reason"]) for row in slices if row["block_reason"] != "none")),
    }


def _earliest_safe_transition(
    graph: Any,
    task: Any,
    current: int,
    next_node: int | None,
    ready_time: float,
    reservations: Any,
    edge_reservations: Any,
    edge_capacity: int,
    node_capacities: dict[int, int],
    merge_groups: dict[tuple[int, int], int],
    merge_capacity: int,
    merge_headway_seconds: float,
    static_faults: set[tuple[int, int]],
    fault_windows: tuple[tuple[int, int, float, float], ...],
) -> dict[str, Any] | None:
    if next_node is None or not graph.has_edge(current, next_node):
        return None
    if (current, next_node) in static_faults:
        return {"reachable": False, "reason": "static_fault_edge"}
    edge = graph.edge(current, next_node)
    travel_time = edge.travel_time
    service_time = graph.service_time(next_node)
    immediate_edge_end = ready_time + travel_time
    immediate_node_start = immediate_edge_end
    immediate_node_end = immediate_node_start + service_time
    edge_blockers = _edge_blockers(
        edge_reservations=edge_reservations,
        start_node=current,
        end_node=next_node,
        start=ready_time,
        end=immediate_edge_end,
        task_id=task.task_id,
    )
    merge_blockers = _merge_blockers(
        edge_reservations=edge_reservations,
        start_node=current,
        end_node=next_node,
        start=ready_time,
        end=immediate_edge_end,
        merge_groups=merge_groups,
        task_id=task.task_id,
    )
    node_blockers = _node_blockers(
        reservations=reservations,
        node=next_node,
        start=immediate_node_start,
        end=immediate_node_end,
        task_id=task.task_id,
    )
    blocker_ids = _format_blocker_ids(edge_blockers + merge_blockers + node_blockers)
    edge_start = ready_time
    for _ in range(len(edge_reservations.all_intervals()) * 4 + len(reservations.all_intervals()) * 2 + 16):
        release = _fault_release_time(current, next_node, edge_start, fault_windows)
        if release is None:
            return {"reachable": False, "reason": "fault_window_no_release"}
        edge_start = max(edge_start, release)
        edge_start = edge_reservations.earliest_start(current, next_node, edge_start, travel_time, edge_capacity, 0.0, task.task_id)
        edge_start = edge_reservations.earliest_merge_group_start(
            current,
            next_node,
            edge_start,
            travel_time,
            merge_groups,
            merge_capacity,
            merge_headway_seconds,
            task.task_id,
        )
        node_start = edge_start + travel_time
        node_end = node_start + service_time
        if next_node != task.goal and reservations.has_capacity_conflict(
            next_node,
            node_start,
            node_end,
            capacity=node_capacities.get(next_node, 1),
            task_id=task.task_id,
        ):
            node_start = _earliest_safe_node_start(
                reservations,
                next_node,
                node_start,
                service_time,
                task.task_id,
                node_capacities.get(next_node, 1),
            )
            edge_start = node_start - travel_time
            continue
        if reservations.has_capacity_conflict(
            current,
            ready_time,
            edge_start,
            capacity=node_capacities.get(current, 1),
            task_id=task.task_id,
        ):
            return {
                "reachable": False,
                "reason": "current_node_hold_conflict",
                "earliest_release_time": edge_start,
                "queue_rank": len(edge_blockers) + len(merge_blockers) + 1 if edge_blockers or merge_blockers else "",
                "queue_length": len(edge_blockers) + len(merge_blockers) + 1 if edge_blockers or merge_blockers else "",
                "wait_blocker_task_ids": blocker_ids,
                "occupying_task_ids": blocker_ids,
                "occupancy_start": _format_blocker_times(edge_blockers + merge_blockers + node_blockers, "start"),
                "occupancy_end": _format_blocker_times(edge_blockers + merge_blockers + node_blockers, "end"),
                "can_current_node_hold": False,
            }
        if edge_start - ready_time > MAX_WAIT_SECONDS:
            return {"reachable": False, "reason": "wait_exceeds_max", "edge_start": edge_start}
        return {
            "reachable": True,
            "reason": "ok",
            "edge_start": edge_start,
            "edge_end": edge_start + travel_time,
            "node_start": node_start,
            "node_end": node_start + service_time,
            "hold_duration": max(0.0, edge_start - ready_time),
            "earliest_release_time": edge_start,
            "queue_rank": len(edge_blockers) + len(merge_blockers) + 1 if edge_blockers or merge_blockers else "",
            "queue_length": len(edge_blockers) + len(merge_blockers) + 1 if edge_blockers or merge_blockers else "",
            "wait_blocker_task_ids": blocker_ids,
            "occupying_task_ids": blocker_ids,
            "occupancy_start": _format_blocker_times(edge_blockers + merge_blockers + node_blockers, "start"),
            "occupancy_end": _format_blocker_times(edge_blockers + merge_blockers + node_blockers, "end"),
            "can_current_node_hold": True,
        }
    return {"reachable": False, "reason": "earliest_safe_search_exhausted"}


def _edge_blockers(
    edge_reservations: Any,
    start_node: int,
    end_node: int,
    start: float,
    end: float,
    task_id: int,
) -> list[Any]:
    return [
        interval
        for interval in edge_reservations.intervals(start_node, end_node)
        if interval.task_id != task_id and interval.overlaps(start, end)
    ]


def _merge_blockers(
    edge_reservations: Any,
    start_node: int,
    end_node: int,
    start: float,
    end: float,
    merge_groups: dict[tuple[int, int], int],
    task_id: int,
) -> list[Any]:
    group = merge_groups.get((start_node, end_node))
    if group is None:
        return []
    return [
        interval
        for interval in edge_reservations.all_intervals()
        if interval.task_id != task_id
        and merge_groups.get((interval.start_node, interval.end_node)) == group
        and interval.overlaps(start, end)
    ]


def _node_blockers(reservations: Any, node: int, start: float, end: float, task_id: int) -> list[Any]:
    return [
        interval
        for interval in reservations.intervals(node)
        if interval.task_id != task_id and interval.overlaps(start, end)
    ]


def _format_blocker_ids(blockers: list[Any]) -> str:
    ids = sorted({int(interval.task_id) for interval in blockers})
    return ";".join(str(task_id) for task_id in ids)


def _format_blocker_times(blockers: list[Any], attr: str) -> str:
    values = [float(getattr(interval, attr)) for interval in blockers]
    return ";".join(f"{value:.6g}" for value in sorted(values))


def _fault_release_time(
    start: int,
    end: int,
    edge_start: float,
    fault_windows: tuple[tuple[int, int, float, float], ...],
) -> float | None:
    release = edge_start
    for fault_start, fault_end, window_start, repair_time in fault_windows:
        if fault_start == start and fault_end == end and window_start <= release < repair_time:
            release = repair_time
    return release


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


def _push_event(event_queue: list[tuple[float, int, int, int, int]], event: tuple[float, int, int, int, int]) -> None:
    event_queue.append(event)
    event_queue.sort()


def _planned_event(task: Any, route: list[Any], decision_count: int, waiting_time: float, variant: str) -> dict[str, Any]:
    return {
        "event": "planned",
        "baseline": f"g3f_{variant}",
        "segment_id": task.segment_id,
        "task_id": task.task_id,
        "start": task.start,
        "goal": task.goal,
        "entry_time": task.pass_time,
        "finish_time": route[-1].t2,
        "decision_count": decision_count,
        "waiting_time": waiting_time,
        "path": [node.location for node in route],
    }


def _mark_unplanned(
    unplanned: list[Any],
    events: list[dict[str, Any]],
    reservations: Any,
    edge_reservations: Any,
    task: Any,
    state: TaskState,
    reason: str,
    variant: str,
) -> None:
    reservations.remove_task(task.task_id)
    edge_reservations.remove_task(task.task_id)
    unplanned.append(task)
    events.append(
        {
            "event": "unplanned",
            "baseline": f"g3f_{variant}",
            "segment_id": task.segment_id,
            "task_id": task.task_id,
            "start": task.start,
            "goal": task.goal,
            "entry_time": task.pass_time,
            "reason": reason,
            "decision_count": state.decision_count,
        }
    )


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


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


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _aggregate_summary(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows = [result.summary for result in results]
    by_variant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_variant[str(row["replay_variant"])].append(row)
    aggregate: list[dict[str, Any]] = []
    for variant_name, variant_rows in sorted(by_variant.items()):
        decision_count = sum(int(row["decision_count"]) for row in variant_rows)
        primary = sum(int(row["primary_g4a_label_count"]) for row in variant_rows)
        branch_count = sum(int(row["branch_decision_count"]) for row in variant_rows)
        branch_primary = 0.0
        for row in variant_rows:
            branch_primary += float(row["branch_effective_label_coverage"]) * int(row["branch_decision_count"])
        aggregate.append(
            {
                "scenario": "ALL",
                "context": "aggregate",
                "replay_variant": variant_name,
                "variant_mode": variant_rows[0]["variant_mode"],
                "diagnostic_ablation": variant_rows[0]["diagnostic_ablation"],
                "hybrid_repair": variant_rows[0]["hybrid_repair"],
                "max_tasks": sum(int(row["max_tasks"]) for row in variant_rows),
                "planned_count": sum(int(row["planned_count"]) for row in variant_rows),
                "unplanned_count": sum(int(row["unplanned_count"]) for row in variant_rows),
                "decision_count": decision_count,
                "legacy_route_next_labels": sum(int(row["legacy_route_next_labels"]) for row in variant_rows),
                "route_intent_task_coverage": sum(int(row["route_intent_task_coverage"]) for row in variant_rows),
                "move_now_legacy_labels": sum(int(row["move_now_legacy_labels"]) for row in variant_rows),
                "wait_edge_capacity_labels": sum(int(row["wait_edge_capacity_labels"]) for row in variant_rows),
                "wait_edge_queue_labels": sum(int(row["wait_edge_queue_labels"]) for row in variant_rows),
                "wait_node_capacity_labels": sum(int(row["wait_node_capacity_labels"]) for row in variant_rows),
                "wait_merge_group_labels": sum(int(row["wait_merge_group_labels"]) for row in variant_rows),
                "wait_fault_repair_labels": sum(int(row["wait_fault_repair_labels"]) for row in variant_rows),
                "wait_until_safe_labels": sum(int(row["wait_until_safe_labels"]) for row in variant_rows),
                "wait_executable_labels": sum(int(row["wait_executable_labels"]) for row in variant_rows),
                "reroute_now_legacy_labels": sum(int(row["reroute_now_legacy_labels"]) for row in variant_rows),
                "legacy_no_path_labels": sum(int(row["legacy_no_path_labels"]) for row in variant_rows),
                "temporarily_blocked_labels": sum(int(row["temporarily_blocked_labels"]) for row in variant_rows),
                "globally_unsafe_labels": sum(int(row["globally_unsafe_labels"]) for row in variant_rows),
                "fallback_safe_labels": sum(int(row["fallback_safe_labels"]) for row in variant_rows),
                "sipp_repair_labels": sum(int(row["sipp_repair_labels"]) for row in variant_rows),
                "abstain_labels": sum(int(row["abstain_labels"]) for row in variant_rows),
                "route_intent_only_labels": sum(int(row["route_intent_only_labels"]) for row in variant_rows),
                "primary_g4a_label_count": primary,
                "primary_g4a_label_coverage": _ratio(primary, decision_count),
                "branch_decision_count": branch_count,
                "branch_effective_label_coverage": _ratio(branch_primary, branch_count),
                "unresolved_edge_capacity_cases": sum(int(row["unresolved_edge_capacity_cases"]) for row in variant_rows),
                "unresolved_edge_capacity_share_of_g3d": _ratio(
                    sum(int(row["unresolved_edge_capacity_cases"]) for row in variant_rows),
                    G3D_EDGE_CAPACITY_CASES,
                ),
                "mean_wait_inserted": sum(float(row["mean_wait_inserted"]) for row in variant_rows) / len(variant_rows),
                "max_wait_inserted": max(float(row["max_wait_inserted"]) for row in variant_rows),
                "node_reservation_conflicts": sum(int(row["node_reservation_conflicts"]) for row in variant_rows),
                "edge_reservation_conflicts": sum(int(row["edge_reservation_conflicts"]) for row in variant_rows),
                "merge_group_conflicts": sum(int(row["merge_group_conflicts"]) for row in variant_rows),
                "post_shield_conflicts": sum(int(row["post_shield_conflicts"]) for row in variant_rows),
                "real_constraint_conflicts": sum(int(row["real_constraint_conflicts"]) for row in variant_rows),
                "mean_travel_time": "",
                "p95_travel_time": "",
                "p99_travel_time": "",
                "late_count": sum(int(row["late_count"]) for row in variant_rows),
                "max_lateness": max(float(row["max_lateness"]) for row in variant_rows),
                "makespan": max(float(row["makespan"]) for row in variant_rows),
                "label_taxonomy_distribution": "aggregate",
                "block_reason_distribution": "aggregate",
            }
        )
    return rows + aggregate


def _branch_rows(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for kind in ("all", "branch", "linear"):
            selected = [
                row
                for row in result.slices
                if kind == "all" or row["branch_or_linear"] == kind
            ]
            if not selected:
                continue
            primary = sum(1 for row in selected if row["label_taxonomy"] in PRIMARY_G4A_TAXA)
            move = sum(1 for row in selected if row["label_taxonomy"] == "MOVE_NOW_LEGACY")
            hold = sum(1 for row in selected if row["label_taxonomy"] == "HOLD_UNTIL_SAFE_LEGACY_NEXT")
            reroute = sum(1 for row in selected if row["label_taxonomy"] == "REROUTE_NOW_LEGACY")
            rows.append(
                {
                    "scenario": result.scenario.name,
                    "context": _scenario_context(result.scenario),
                    "replay_variant": result.variant.name,
                    "node_kind": kind,
                    "decision_count": len(selected),
                    "move_now_legacy": move,
                    "hold_until_safe": hold,
                    "reroute_now_legacy": reroute,
                    "primary_g4a_labels": primary,
                    "effective_label_coverage": _ratio(primary, len(selected)),
                    "no_path": sum(1 for row in selected if row["label_taxonomy"] == "LEGACY_NO_PATH"),
                    "repair_or_fallback": sum(1 for row in selected if row["label_taxonomy"] in {"SIPP_REPAIR_MOVE", "FALLBACK_SAFE_MOVE"}),
                    "blocked_or_abstain": sum(1 for row in selected if row["label_taxonomy"] in {"LEGACY_NEXT_TEMPORARILY_BLOCKED", "LEGACY_NEXT_GLOBALLY_UNSAFE", "ABSTAIN_NO_TEACHER"}),
                }
            )
    return rows


def _taxonomy_rows(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        counter = Counter(str(row["label_taxonomy"]) for row in result.slices)
        for taxonomy, count in sorted(counter.items()):
            rows.append(
                {
                    "scenario": result.scenario.name,
                    "context": _scenario_context(result.scenario),
                    "replay_variant": result.variant.name,
                    "label_taxonomy": taxonomy,
                    "label_role": "primary_executable" if taxonomy in PRIMARY_EXECUTABLE_TAXA else "auxiliary_or_exclusion",
                    "count": count,
                    "share": _ratio(count, len(result.slices)),
                }
            )
    return rows


def _blocked_ledger_rows(baseline_results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in baseline_results:
        for row in result.slices:
            if row["label_taxonomy"] == "MOVE_NOW_LEGACY":
                continue
            rows.append(dict(row))
    return rows


def _earliest_safe_rows(baseline_results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows = []
    for result in baseline_results:
        for row in result.slices:
            if row["legacy_next"] == "" or row["block_reason"] == "none":
                continue
            rows.append(
                {
                    "scenario": row["scenario"],
                    "context": row["context"],
                    "segment_id": row["segment_id"],
                    "task_id": row["task_id"],
                    "current": row["current"],
                    "legacy_next": row["legacy_next"],
                    "goal": row["goal"],
                    "ready_time": row["ready_time"],
                    "block_reason": row["block_reason"],
                    "label_taxonomy": row["label_taxonomy"],
                    "hold_until_time": row["hold_until_time"],
                    "hold_duration": row["hold_duration"],
                    "earliest_safe_time": row["earliest_safe_time"],
                    "earliest_hold_duration": row["earliest_hold_duration"],
                    "earliest_safe_status": row["earliest_safe_status"],
                    "wait_label_candidate": row["label_taxonomy"] == "LEGACY_NEXT_TEMPORARILY_BLOCKED",
                    "branch_or_linear": row["branch_or_linear"],
                    "fault_state": row["fault_state"],
                    "repair_state": row["repair_state"],
                    "merge_state": row["merge_state"],
                    "buffer_state": row["buffer_state"],
                }
            )
    return rows


def _recovered_task_rows(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    baseline_by_scenario = {
        result.scenario.name: set(result.routes)
        for result in results
        if result.variant.name == "g3c_baseline_reproduction"
    }
    rows: list[dict[str, Any]] = []
    for result in results:
        if result.variant.name == "g3c_baseline_reproduction":
            continue
        baseline_planned = baseline_by_scenario.get(result.scenario.name, set())
        for segment_id in sorted(set(result.routes) - baseline_planned):
            route = result.routes[segment_id]
            rows.append(
                {
                    "scenario": result.scenario.name,
                    "context": _scenario_context(result.scenario),
                    "replay_variant": result.variant.name,
                    "segment_id": segment_id,
                    "task_id": route[-1].location if not route else _task_id_for_segment(result, segment_id),
                    "recovered_by_wait_or_repair": True,
                    "finish_time": route[-1].t2 if route else "",
                    "path": _format_path(_route_path(route)),
                    "diagnostic_ablation": result.variant.diagnostic,
                    "hybrid_repair": result.variant.hybrid,
                }
            )
    return rows


def _task_id_for_segment(result: ReplayResult, segment_id: str) -> str:
    for row in result.slices:
        if row["segment_id"] == segment_id:
            return str(row["task_id"])
    return ""


def _best_primary_variant(results: tuple[ReplayResult, ...]) -> str:
    candidates = [
        result
        for result in results
        if not result.variant.diagnostic and not result.variant.route_intent_only and not result.variant.hybrid
    ]
    by_variant: dict[str, list[ReplayResult]] = defaultdict(list)
    for result in candidates:
        by_variant[result.variant.name].append(result)
    best_name = ""
    best_rank = (-1, -1.0, 0)
    for name, grouped in by_variant.items():
        planned = sum(int(result.summary["planned_count"]) for result in grouped)
        branch_count = sum(int(result.summary["branch_decision_count"]) for result in grouped)
        branch_cov = _ratio(
            sum(float(result.summary["branch_effective_label_coverage"]) * int(result.summary["branch_decision_count"]) for result in grouped),
            branch_count,
        )
        conflicts = sum(int(result.summary["post_shield_conflicts"]) for result in grouped)
        rank = (planned, branch_cov, -conflicts)
        if rank > best_rank:
            best_rank = rank
            best_name = name
    return best_name


def _still_blocked_rows(results: tuple[ReplayResult, ...], best_variant: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if result.variant.name != best_variant:
            continue
        for row in result.slices:
            if row["label_taxonomy"] in PRIMARY_EXECUTABLE_TAXA:
                continue
            rows.append(dict(row))
    return rows


def _reroute_rows(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if result.variant.name != "g3d_reroute_anchor":
            continue
        for row in result.slices:
            if row["reroute_attempted"] or row["label_taxonomy"] in {"REROUTE_NOW_LEGACY", "LEGACY_NO_PATH"}:
                rows.append(dict(row))
    return rows


def _edge_hotspot_rows(blocked_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counter: Counter[tuple[str, str, str, str, str]] = Counter()
    for row in blocked_rows:
        if "edge_capacity" not in str(row["block_reason"]):
            continue
        key = (
            str(row["scenario"]),
            str(row["current"]),
            str(row["legacy_next"]),
            str(row["branch_or_linear"]),
            str(row["block_reason"]),
        )
        counter[key] += 1
    return [
        {
            "scenario": scenario,
            "current": current,
            "legacy_next": next_node,
            "branch_or_linear": kind,
            "block_reason": reason,
            "blocked_count": count,
        }
        for (scenario, current, next_node, kind, reason), count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _all_slices(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    return [dict(row) for result in results for row in result.slices]


def _edge_block_ledger_rows(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    task_to_segment = {
        str(row["task_id"]): str(row["segment_id"])
        for result in results
        for row in result.slices
    }
    for result in results:
        for row in result.slices:
            if row["legacy_next"] == "" or row["block_reason"] == "none":
                continue
            if not any(reason in str(row["block_reason"]) for reason in ("edge_capacity", "merge_group", "node_reservation")):
                continue
            rows.append(
                {
                    "scenario": row["scenario"],
                    "segment_id": row["segment_id"],
                    "task_id": row["task_id"],
                    "current": row["current"],
                    "legacy_next": row["legacy_next"],
                    "goal": row["goal"],
                    "ready_time": row["ready_time"],
                    "blocked_reason": row["block_reason"],
                    "edge_start": row["current"],
                    "edge_end": row["legacy_next"],
                    "occupying_segment_id": _segment_ids_for_task_ids(row.get("occupying_task_ids", ""), task_to_segment),
                    "occupying_task_id": row.get("occupying_task_ids", ""),
                    "occupancy_start": row.get("occupancy_start", ""),
                    "occupancy_end": row.get("occupancy_end", ""),
                    "earliest_release_time": row.get("earliest_release_time", ""),
                    "wait_needed": row.get("earliest_hold_duration", ""),
                    "can_current_node_hold": row.get("can_current_node_hold", ""),
                    "node_hold_capacity_reason": "ok" if row.get("can_current_node_hold") in {True, "True"} else "current_node_hold_conflict",
                    "merge_group_reason": "merge_group" if "merge_group" in str(row["block_reason"]) else "",
                    "event_variant": row["replay_variant"],
                    "queue_rank": row.get("queue_rank", ""),
                    "queue_length": row.get("queue_length", ""),
                    "label_source": row["label_source"],
                }
            )
    return rows


def _segment_ids_for_task_ids(task_ids: Any, task_to_segment: dict[str, str]) -> str:
    values = [part for part in str(task_ids).split(";") if part]
    return ";".join(task_to_segment.get(value, "") for value in values)


def _edge_release_rows(edge_block_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "scenario": row["scenario"],
            "event_variant": row["event_variant"],
            "segment_id": row["segment_id"],
            "task_id": row["task_id"],
            "edge": f"{row['edge_start']}->{row['edge_end']}",
            "ready_time": row["ready_time"],
            "blocked_reason": row["blocked_reason"],
            "occupying_task_id": row["occupying_task_id"],
            "occupancy_start": row["occupancy_start"],
            "occupancy_end": row["occupancy_end"],
            "earliest_release_time": row["earliest_release_time"],
            "wait_needed": row["wait_needed"],
            "can_current_node_hold": row["can_current_node_hold"],
            "queue_rank": row["queue_rank"],
            "queue_length": row["queue_length"],
        }
        for row in edge_block_rows
    ]


def _route_executable_rows(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        for row in result.slices:
            rows.append(
                {
                    "scenario": row["scenario"],
                    "event_variant": row["replay_variant"],
                    "segment_id": row["segment_id"],
                    "task_id": row["task_id"],
                    "current": row["current"],
                    "goal": row["goal"],
                    "ready_time": row["ready_time"],
                    "route_intent_label": row["route_intent_label"],
                    "legacy_next": row["legacy_next"],
                    "legacy_route_suffix": row["legacy_route_suffix"],
                    "executable_label": row["executable_label"],
                    "executed_kind": row["executed_kind"],
                    "executed_next": row["executed_next"],
                    "label_source": row["label_source"],
                    "post_label_safe": row["post_label_safe"],
                    "block_reason": row["block_reason"],
                    "g4a_primary_eligible": row["g4a_primary_eligible"],
                }
            )
    return rows


def _queue_summary_rows(edge_block_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in edge_block_rows:
        grouped[(str(row["scenario"]), str(row["event_variant"]), f"{row['edge_start']}->{row['edge_end']}")].append(row)
    rows: list[dict[str, Any]] = []
    for (scenario, variant, edge), items in sorted(grouped.items()):
        waits = [
            float(item["wait_needed"])
            for item in items
            if str(item.get("wait_needed", "")) not in {"", "None"}
        ]
        queue_lengths = [
            int(float(item["queue_length"]))
            for item in items
            if str(item.get("queue_length", "")) not in {"", "None"}
        ]
        rows.append(
            {
                "scenario": scenario,
                "event_variant": variant,
                "edge": edge,
                "blocked_count": len(items),
                "mean_wait_needed": sum(waits) / len(waits) if waits else 0.0,
                "max_wait_needed": max(waits) if waits else 0.0,
                "max_queue_length": max(queue_lengths) if queue_lengths else 0,
                "release_audit_rows": len(items),
            }
        )
    return rows


def _hotspot_timeline_rows(edge_block_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hotspot_counts = Counter(str(row["edge_start"]) + "->" + str(row["edge_end"]) for row in edge_block_rows)
    hotspots = {edge for edge, _ in hotspot_counts.most_common(10)}
    rows: list[dict[str, Any]] = []
    for row in edge_block_rows:
        edge = f"{row['edge_start']}->{row['edge_end']}"
        if edge not in hotspots:
            continue
        rows.append(
            {
                "scenario": row["scenario"],
                "event_variant": row["event_variant"],
                "edge": edge,
                "event_type": "wait_for_release",
                "segment_id": row["segment_id"],
                "task_id": row["task_id"],
                "time_start": row["ready_time"],
                "time_end": row["earliest_release_time"],
                "occupying_task_id": row["occupying_task_id"],
                "occupancy_start": row["occupancy_start"],
                "occupancy_end": row["occupancy_end"],
                "queue_length": row["queue_length"],
                "queue_rank": row["queue_rank"],
                "deadline_slack": "",
                "blocked_reason": row["blocked_reason"],
            }
        )
    return rows


def _unresolved_capacity_rows(results: tuple[ReplayResult, ...], best_variant: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if result.variant.name != best_variant:
            continue
        for row in result.slices:
            if "edge_capacity" not in str(row["block_reason"]):
                continue
            if row["label_taxonomy"] in PRIMARY_EXECUTABLE_TAXA:
                continue
            rows.append(dict(row))
    return rows


def _g4a_eligibility_rows(summary_rows: list[dict[str, Any]], best_variant: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in summary_rows:
        if row["scenario"] != "ALL":
            continue
        planned = int(row["planned_count"])
        conflicts = int(row["real_constraint_conflicts"])
        post_conflicts = int(row["post_shield_conflicts"])
        branch = float(row["branch_effective_label_coverage"])
        route_intent = int(row["route_intent_task_coverage"])
        unresolved_share = float(row["unresolved_edge_capacity_share_of_g3d"])
        pass_gate = (
            planned >= G3F_GATE_PLANNED
            and conflicts == 0
            and post_conflicts == 0
            and branch >= G3F_GATE_BRANCH_COVERAGE
            and route_intent >= G3F_GATE_ROUTE_INTENT
            and unresolved_share <= 0.20
            and row["variant_mode"] != "route_intent"
            and row["variant_mode"] != "hybrid"
        )
        rows.append(
            {
                "replay_variant": row["replay_variant"],
                "variant_mode": row["variant_mode"],
                "best_executable_variant": row["replay_variant"] == best_variant,
                "planned_count": planned,
                "planned_gate": planned >= G3F_GATE_PLANNED,
                "real_constraint_conflicts": conflicts,
                "real_conflict_gate": conflicts == 0,
                "post_shield_conflicts": post_conflicts,
                "post_shield_gate": post_conflicts == 0,
                "branch_executable_coverage": branch,
                "branch_gate": branch >= G3F_GATE_BRANCH_COVERAGE,
                "route_intent_coverage": route_intent,
                "route_intent_gate": route_intent >= G3F_GATE_ROUTE_INTENT,
                "unresolved_edge_capacity_cases": row["unresolved_edge_capacity_cases"],
                "unresolved_edge_capacity_share_of_g3d": unresolved_share,
                "unresolved_gate": unresolved_share <= 0.20,
                "g4a_pilot_eligible": pass_gate,
            }
        )
    return rows


def _g4a_manifest_rows(results: tuple[ReplayResult, ...], best_variant: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if result.variant.diagnostic or result.variant.route_intent_only:
            continue
        for row in result.slices:
            if row["label_taxonomy"] in PRIMARY_EXECUTABLE_TAXA and row["post_label_safe"]:
                rows.append(dict(row))
    return rows


def _write_jsonl_samples(route_rows: list[dict[str, Any]], executable_rows: list[dict[str, Any]]) -> None:
    ROUTE_INTENT_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    route_sample = [row for row in route_rows if row["route_intent_label"] == "ROUTE_INTENT_LEGACY"][:MAX_SAMPLE_ROWS]
    with ROUTE_INTENT_SAMPLE_PATH.open("w", encoding="utf-8") as handle:
        for row in route_sample:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    prioritized = [row for row in executable_rows if str(row["executable_label"]).startswith("WAIT_")]
    sample = (prioritized + executable_rows)[:MAX_SAMPLE_ROWS]
    with EXECUTABLE_SAMPLE_PATH.open("w", encoding="utf-8") as handle:
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_hotspot_figure(blocked_rows: list[dict[str, Any]]) -> None:
    scenarios = [scenario.name for scenario in _case_plan()]
    edges = [edge for edge, _ in Counter(f"{row['edge_start']}->{row['edge_end']}" for row in blocked_rows).most_common(10)]
    if not edges:
        edges = ["none"]
    counts = Counter((str(row["scenario"]), f"{row['edge_start']}->{row['edge_end']}") for row in blocked_rows)
    matrix = [[counts[(scenario, edge)] for edge in edges] for scenario in scenarios]
    _write_png_heatmap(HOTSPOT_FIGURE_PATH, matrix)


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
    results: tuple[ReplayResult, ...],
    summary_rows: list[dict[str, Any]],
    edge_block_rows: list[dict[str, Any]],
    release_rows: list[dict[str, Any]],
    queue_rows: list[dict[str, Any]],
    route_exec_rows: list[dict[str, Any]],
    taxonomy_rows: list[dict[str, Any]],
    unresolved_rows: list[dict[str, Any]],
    eligibility_rows: list[dict[str, Any]],
    best_primary_variant: str,
) -> None:
    aggregate = {row["replay_variant"]: row for row in summary_rows if row["scenario"] == "ALL"}
    anchor = aggregate["g3d_reroute_anchor"]
    best = aggregate[best_primary_variant]
    hybrid = aggregate["hybrid_executable_teacher"]
    route_intent = aggregate["route_intent_only_teacher"]
    decision = _decision(best, eligibility_rows)
    best_taxonomy: Counter[str] = Counter()
    for row in taxonomy_rows:
        if row["replay_variant"] == best_primary_variant:
            best_taxonomy[str(row["label_taxonomy"])] += int(row["count"])
    route_label_counts = Counter(str(row["route_intent_label"]) for row in route_exec_rows)
    executable_counts = Counter(str(row["executable_label"]) for row in route_exec_rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G3f Edge-Capacity-Aware Legacy-A* Teacher Scheduler",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## 1. Scope and non-claim boundary",
        "",
        "This audit builds an execution-layer scheduler around the Legacy-A* route-intent teacher. It does not train a model, does not start PPO/MAPPO/RL, does not create a broad G4A dataset, does not disable edge capacity, and does not modify legacy Java.",
        "",
        f"- map: `{_relative(MAP_PATH)}`",
        f"- tasks: `{_relative(TASK_PATH)}`",
        f"- teacher source: `{TEACHER_SOURCE}`",
        "",
        "## 2. Prior result anchor",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ["G3c planned", "78/144"],
                ["G3c blocked/unavailable slices", "614"],
                ["G3c candidate recall", "1.000"],
                ["G3c safe recall", "0.610"],
                ["G3d best primary replay", "94/144"],
                ["G3d disable-edge-capacity diagnostic", "125/144 with 491 real conflicts"],
                ["G3e semantic fix", "repair-window reachability fixed; best primary remained 94/144"],
            ],
        ),
        "",
        "## 3. Legacy route intent vs runtime execution",
        "",
        "The original Legacy Java A* route source is paper-faithful route intent: it plans over graph cost, fault edges, and node time-window style constraints. The current Python/C++ event shield adds runtime safety checks for edge capacity, edge headway, merge groups, and buffer/node capacity. Therefore a Legacy next-hop can be a valid route preference while not being executable at the current event time.",
        "",
        _markdown_table(
            ["Label family", "Rows"],
            [[label, count] for label, count in (route_label_counts + executable_counts).most_common(12)],
        ),
        "",
        "## 4. Edge release and queue audit",
        "",
        f"G3f records `{len(edge_block_rows)}` edge/node/merge block ledger rows and `{len(release_rows)}` release-time rows. These rows keep the hard shield active and explain which occupied intervals force WAIT labels.",
        "",
        "Top blocked edges:",
        "",
        _markdown_table(
            ["Edge", "Rows"],
            [[edge, count] for edge, count in Counter(f"{row['edge_start']}->{row['edge_end']}" for row in edge_block_rows).most_common(10)],
        ),
        "",
        "## 5. Scheduler variants",
        "",
        _markdown_table(
            ["Variant", "Planned", "Branch exec cov", "Route intent", "Unresolved edge share", "Real conflicts"],
            [
                [
                    name,
                    f"{row['planned_count']}/{row['max_tasks']}",
                    f"{float(row['branch_effective_label_coverage']):.3f}",
                    row["route_intent_task_coverage"],
                    f"{float(row['unresolved_edge_capacity_share_of_g3d']):.3f}",
                    row["real_constraint_conflicts"],
                ]
                for name, row in aggregate.items()
            ],
        ),
        "",
        f"G3d reroute anchor reproduces `{anchor['planned_count']}/144` planned with `{anchor['real_constraint_conflicts']}` real conflicts.",
        f"Best executable G3f variant is `{best_primary_variant}` with `{best['planned_count']}/144` planned, `{float(best['branch_effective_label_coverage']):.3f}` branch executable coverage, and `{best['real_constraint_conflicts']}` real conflicts.",
        f"Hybrid executable teacher reaches `{hybrid['planned_count']}/144`; SIPP/fallback labels remain auxiliary and are not counted as primary Legacy labels.",
        f"Route-intent-only teacher coverage is `{route_intent['route_intent_task_coverage']}/144`; it is suitable for route-ranking/global-guide supervision, not closed-loop action imitation.",
        "",
        "## 6. Executable label taxonomy",
        "",
        _markdown_table(
            ["Taxonomy", "Rows"],
            [[taxonomy, count] for taxonomy, count in best_taxonomy.most_common()],
        ),
        "",
        "## 7. G4A pilot gate",
        "",
        _markdown_table(
            ["Variant", "Planned", "Branch", "Route intent", "Unresolved", "Eligible"],
            [
                [
                    row["replay_variant"],
                    row["planned_count"],
                    f"{float(row['branch_executable_coverage']):.3f}",
                    row["route_intent_coverage"],
                    f"{float(row['unresolved_edge_capacity_share_of_g3d']):.3f}",
                    row["g4a_pilot_eligible"],
                ]
                for row in eligibility_rows
            ],
        ),
        "",
        decision,
        "",
        "## 8. Unresolved capacity blocker",
        "",
        f"Unresolved edge-capacity rows for the best variant: `{len(unresolved_rows)}`. If the gate fails, the next step remains scheduler-semantics alignment rather than training.",
        "",
        "## Artifacts",
        "",
        f"- Edge block ledger: `{_relative(EDGE_BLOCK_LEDGER_TABLE)}`",
        f"- Edge release audit: `{_relative(EDGE_RELEASE_AUDIT_TABLE)}`",
        f"- Edge queue replay summary: `{_relative(EDGE_QUEUE_SUMMARY_TABLE)}`",
        f"- Route intent vs executable labels: `{_relative(ROUTE_EXECUTABLE_TABLE)}`",
        f"- Wait label taxonomy: `{_relative(WAIT_TAXONOMY_TABLE)}`",
        f"- Scheduler variant comparison: `{_relative(SCHEDULER_SUMMARY_TABLE)}`",
        f"- Hotspot timeline: `{_relative(HOTSPOT_TIMELINE_TABLE)}`",
        f"- Unresolved cases: `{_relative(UNRESOLVED_TABLE)}`",
        f"- G4A pilot eligibility: `{_relative(G4A_ELIGIBILITY_TABLE)}`",
        f"- Route-intent JSONL sample: `{_relative(ROUTE_INTENT_SAMPLE_PATH)}`",
        f"- Executable wait JSONL sample: `{_relative(EXECUTABLE_SAMPLE_PATH)}`",
        f"- Hotspot figure: `{_relative(HOTSPOT_FIGURE_PATH)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _decision(best: dict[str, Any], eligibility_rows: list[dict[str, Any]]) -> str:
    eligible = any(row["g4a_pilot_eligible"] == True for row in eligibility_rows)
    if int(best["post_shield_conflicts"]) > 0 or int(best["real_constraint_conflicts"]) > 0:
        return "Hard stop: the best executable scheduler produced shield or real-constraint conflicts. Do not enter G4A or training."
    if eligible:
        return "Development pass: G3f reaches the pilot gate. A small G4A dataset build is allowed, still before any model training."
    return (
        "Diagnostic pass: G3f generated the required route-intent/executable-label split and capacity ledger, "
        "but the gate is not met. Do not start G4A or training; continue with G3g scheduler semantics alignment."
    )


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


def _write_all_outputs(results: tuple[ReplayResult, ...]) -> None:
    summary_rows = _aggregate_summary(results)
    best_primary = _best_primary_variant(results)
    edge_block_rows = _edge_block_ledger_rows(results)
    release_rows = _edge_release_rows(edge_block_rows)
    queue_rows = _queue_summary_rows(edge_block_rows)
    route_exec_rows = _route_executable_rows(results)
    hotspot_timeline_rows = _hotspot_timeline_rows(edge_block_rows)
    taxonomy_rows = _taxonomy_rows(results)
    unresolved_rows = _unresolved_capacity_rows(results, best_primary)
    eligibility_rows = _g4a_eligibility_rows(summary_rows, best_primary)

    _write_csv(EDGE_BLOCK_LEDGER_TABLE, edge_block_rows, _edge_block_fields())
    _write_csv(EDGE_RELEASE_AUDIT_TABLE, release_rows, _edge_release_fields())
    _write_csv(EDGE_QUEUE_SUMMARY_TABLE, queue_rows, _edge_queue_fields())
    _write_csv(ROUTE_EXECUTABLE_TABLE, route_exec_rows, _route_exec_fields())
    _write_csv(WAIT_TAXONOMY_TABLE, taxonomy_rows, ["scenario", "context", "replay_variant", "label_taxonomy", "label_role", "count", "share"])
    _write_csv(SCHEDULER_SUMMARY_TABLE, summary_rows, _summary_fields())
    _write_csv(HOTSPOT_TIMELINE_TABLE, hotspot_timeline_rows, _hotspot_timeline_fields())
    _write_csv(UNRESOLVED_TABLE, unresolved_rows, _slice_fields())
    _write_csv(G4A_ELIGIBILITY_TABLE, eligibility_rows, _eligibility_fields())
    _write_jsonl_samples(route_exec_rows, route_exec_rows)
    _write_hotspot_figure(edge_block_rows)
    _write_report(
        results=results,
        summary_rows=summary_rows,
        edge_block_rows=edge_block_rows,
        release_rows=release_rows,
        queue_rows=queue_rows,
        route_exec_rows=route_exec_rows,
        taxonomy_rows=taxonomy_rows,
        unresolved_rows=unresolved_rows,
        eligibility_rows=eligibility_rows,
        best_primary_variant=best_primary,
    )


def _slice_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "replay_variant",
        "variant_mode",
        "diagnostic_ablation",
        "teacher_source",
        "decision_ordinal",
        "task_decision_ordinal",
        "task_index",
        "segment_id",
        "task_id",
        "source_line",
        "current",
        "goal",
        "ready_time",
        "candidate_next_nodes",
        "safe_next_nodes",
        "legacy_route_suffix",
        "legacy_next",
        "route_intent_label",
        "label_taxonomy",
        "executable_label",
        "label_kind",
        "label_next",
        "hold_until_time",
        "hold_duration",
        "earliest_safe_time",
        "earliest_release_time",
        "earliest_hold_duration",
        "earliest_safe_status",
        "queue_rank",
        "queue_length",
        "wait_blocker_task_ids",
        "occupying_task_ids",
        "occupancy_start",
        "occupancy_end",
        "can_current_node_hold",
        "block_reason",
        "block_reason_detail",
        "label_source",
        "post_label_safe",
        "teacher_finish_time",
        "branch_or_linear",
        "fault_state",
        "repair_state",
        "merge_state",
        "buffer_state",
        "executed_kind",
        "executed_next",
        "edge_start",
        "edge_end",
        "node_start",
        "node_end",
        "terminal_reason",
        "reroute_attempted",
        "sipp_repair_attempted",
        "g4a_primary_eligible",
    ]


def _earliest_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "segment_id",
        "task_id",
        "current",
        "legacy_next",
        "goal",
        "ready_time",
        "block_reason",
        "label_taxonomy",
        "hold_until_time",
        "hold_duration",
        "earliest_safe_time",
        "earliest_hold_duration",
        "earliest_safe_status",
        "wait_label_candidate",
        "branch_or_linear",
        "fault_state",
        "repair_state",
        "merge_state",
        "buffer_state",
    ]


def _summary_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "replay_variant",
        "variant_mode",
        "diagnostic_ablation",
        "hybrid_repair",
        "max_tasks",
        "planned_count",
        "unplanned_count",
        "decision_count",
        "legacy_route_next_labels",
        "route_intent_task_coverage",
        "move_now_legacy_labels",
        "wait_edge_capacity_labels",
        "wait_edge_queue_labels",
        "wait_node_capacity_labels",
        "wait_merge_group_labels",
        "wait_fault_repair_labels",
        "wait_until_safe_labels",
        "wait_executable_labels",
        "reroute_now_legacy_labels",
        "legacy_no_path_labels",
        "temporarily_blocked_labels",
        "globally_unsafe_labels",
        "fallback_safe_labels",
        "sipp_repair_labels",
        "abstain_labels",
        "route_intent_only_labels",
        "primary_g4a_label_count",
        "primary_g4a_label_coverage",
        "branch_decision_count",
        "branch_effective_label_coverage",
        "unresolved_edge_capacity_cases",
        "unresolved_edge_capacity_share_of_g3d",
        "mean_wait_inserted",
        "max_wait_inserted",
        "mean_travel_time",
        "p95_travel_time",
        "p99_travel_time",
        "late_count",
        "max_lateness",
        "makespan",
        "node_reservation_conflicts",
        "edge_reservation_conflicts",
        "merge_group_conflicts",
        "post_shield_conflicts",
        "real_constraint_conflicts",
        "label_taxonomy_distribution",
        "block_reason_distribution",
    ]


def _edge_block_fields() -> list[str]:
    return [
        "scenario",
        "segment_id",
        "task_id",
        "current",
        "legacy_next",
        "goal",
        "ready_time",
        "blocked_reason",
        "edge_start",
        "edge_end",
        "occupying_segment_id",
        "occupying_task_id",
        "occupancy_start",
        "occupancy_end",
        "earliest_release_time",
        "wait_needed",
        "can_current_node_hold",
        "node_hold_capacity_reason",
        "merge_group_reason",
        "event_variant",
        "queue_rank",
        "queue_length",
        "label_source",
    ]


def _edge_release_fields() -> list[str]:
    return [
        "scenario",
        "event_variant",
        "segment_id",
        "task_id",
        "edge",
        "ready_time",
        "blocked_reason",
        "occupying_task_id",
        "occupancy_start",
        "occupancy_end",
        "earliest_release_time",
        "wait_needed",
        "can_current_node_hold",
        "queue_rank",
        "queue_length",
    ]


def _edge_queue_fields() -> list[str]:
    return [
        "scenario",
        "event_variant",
        "edge",
        "blocked_count",
        "mean_wait_needed",
        "max_wait_needed",
        "max_queue_length",
        "release_audit_rows",
    ]


def _route_exec_fields() -> list[str]:
    return [
        "scenario",
        "event_variant",
        "segment_id",
        "task_id",
        "current",
        "goal",
        "ready_time",
        "route_intent_label",
        "legacy_next",
        "legacy_route_suffix",
        "executable_label",
        "executed_kind",
        "executed_next",
        "label_source",
        "post_label_safe",
        "block_reason",
        "g4a_primary_eligible",
    ]


def _hotspot_timeline_fields() -> list[str]:
    return [
        "scenario",
        "event_variant",
        "edge",
        "event_type",
        "segment_id",
        "task_id",
        "time_start",
        "time_end",
        "occupying_task_id",
        "occupancy_start",
        "occupancy_end",
        "queue_length",
        "queue_rank",
        "deadline_slack",
        "blocked_reason",
    ]


def _eligibility_fields() -> list[str]:
    return [
        "replay_variant",
        "variant_mode",
        "best_executable_variant",
        "planned_count",
        "planned_gate",
        "real_constraint_conflicts",
        "real_conflict_gate",
        "post_shield_conflicts",
        "post_shield_gate",
        "branch_executable_coverage",
        "branch_gate",
        "route_intent_coverage",
        "route_intent_gate",
        "unresolved_edge_capacity_cases",
        "unresolved_edge_capacity_share_of_g3d",
        "unresolved_gate",
        "g4a_pilot_eligible",
    ]


def _recovered_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "replay_variant",
        "segment_id",
        "task_id",
        "recovered_by_wait_or_repair",
        "finish_time",
        "path",
        "diagnostic_ablation",
        "hybrid_repair",
    ]


def _branch_fields() -> list[str]:
    return [
        "scenario",
        "context",
        "replay_variant",
        "node_kind",
        "decision_count",
        "move_now_legacy",
        "hold_until_safe",
        "reroute_now_legacy",
        "primary_g4a_labels",
        "effective_label_coverage",
        "no_path",
        "repair_or_fallback",
        "blocked_or_abstain",
    ]


def main() -> None:
    _prepare_imports()
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    # Read G3c artifacts explicitly so a missing prerequisite fails loudly.
    g3c_replay_rows = _read_csv_rows(G3C_REPLAY_SAFETY_TABLE)
    g3c_unavailable_rows = _read_csv_rows(G3C_UNAVAILABLE_TABLE)
    g3c_coverage_rows = _read_csv_rows(G3C_COVERAGE_TABLE)
    if not g3c_replay_rows or not g3c_unavailable_rows or not g3c_coverage_rows:
        raise AssertionError("G3f requires non-empty G3c replay, unavailable, and coverage tables")

    results: list[ReplayResult] = []
    for scenario in _case_plan():
        selected = _selected_tasks(all_tasks, scenario)
        for variant in _variants():
            results.append(_run_replay(graph, selected, scenario, variant))
    _write_all_outputs(tuple(results))

    required = (
        REPORT_PATH,
        EDGE_BLOCK_LEDGER_TABLE,
        EDGE_RELEASE_AUDIT_TABLE,
        EDGE_QUEUE_SUMMARY_TABLE,
        ROUTE_EXECUTABLE_TABLE,
        WAIT_TAXONOMY_TABLE,
        SCHEDULER_SUMMARY_TABLE,
        HOTSPOT_TIMELINE_TABLE,
        UNRESOLVED_TABLE,
        G4A_ELIGIBILITY_TABLE,
        ROUTE_INTENT_SAMPLE_PATH,
        EXECUTABLE_SAMPLE_PATH,
        HOTSPOT_FIGURE_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G3f artifacts: {missing}")
    print(
        "g3f complete: "
        f"scenarios={len(_case_plan())} variants={len(_variants())} "
        f"result_rows={len(results)}"
    )


if __name__ == "__main__":
    main()
