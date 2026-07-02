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

REPORT_PATH = ROOT / "outputs" / "reports" / "g3d_legacy_teacher_wait_horizon_audit_report.md"
BLOCKED_LEDGER_TABLE = ROOT / "outputs" / "tables" / "g3d_blocked_slice_ledger.csv"
EARLIEST_SAFE_TABLE = ROOT / "outputs" / "tables" / "g3d_earliest_safe_time_labels.csv"
VARIANT_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3d_teacher_replay_variant_summary.csv"
RECOVERED_TASKS_TABLE = ROOT / "outputs" / "tables" / "g3d_wait_until_safe_recovered_tasks.csv"
STILL_BLOCKED_TABLE = ROOT / "outputs" / "tables" / "g3d_still_blocked_after_wait.csv"
REROUTE_TABLE = ROOT / "outputs" / "tables" / "g3d_legacy_reroute_from_current.csv"
BRANCH_RECALL_TABLE = ROOT / "outputs" / "tables" / "g3d_branch_vs_linear_recall.csv"
EDGE_HOTSPOT_TABLE = ROOT / "outputs" / "tables" / "g3d_edge_capacity_hotspots.csv"
TAXONOMY_TABLE = ROOT / "outputs" / "tables" / "g3d_teacher_label_taxonomy.csv"
G4A_MANIFEST_TABLE = ROOT / "outputs" / "tables" / "g3d_g4a_eligible_slice_manifest.csv"
WAIT_LABEL_SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3d_legacy_astar_wait_labels_sample.jsonl"
HEATMAP_PATH = ROOT / "outputs" / "figures" / "g3d_block_reason_heatmap.png"

G3C_REPLAY_SAFETY_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_replay_safety.csv"
G3C_UNAVAILABLE_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_unavailable_cases.csv"
G3C_COVERAGE_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_label_coverage.csv"

TEACHER_SOURCE = "python_faithful_legacy_astar_wait_horizon_audit"
MAX_DECISIONS_PER_TASK = 128
MAX_WAIT_SECONDS = 3600.0
MAX_SAMPLE_ROWS = 500
EPSILON = 1.0e-9

PRIMARY_G4A_TAXA = {
    "MOVE_NOW_LEGACY",
    "HOLD_UNTIL_SAFE_LEGACY_NEXT",
    "REROUTE_NOW_LEGACY",
}


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
    diagnostic: bool = False
    hybrid: bool = False
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
        ReplayVariant("g3c_baseline_reproduction", "baseline", hold_seconds=1.0),
        ReplayVariant("wait_fixed_hold_1s", "fixed_hold", hold_seconds=1.0),
        ReplayVariant("wait_fixed_hold_2s", "fixed_hold", hold_seconds=2.0),
        ReplayVariant("wait_fixed_hold_5s", "fixed_hold", hold_seconds=5.0),
        ReplayVariant("jump_to_earliest_safe_time", "jump"),
        ReplayVariant("reroute_from_current_legacy", "reroute"),
        ReplayVariant("ablation_edge_capacity_2", "baseline", diagnostic=True, edge_capacity=2),
        ReplayVariant("ablation_disable_edge_capacity", "baseline", diagnostic=True, edge_capacity=999),
        ReplayVariant("ablation_disable_merge_group", "baseline", diagnostic=True, disable_merge_group=True),
        ReplayVariant("hybrid_legacy_wait_sipp_fallback", "hybrid", hybrid=True),
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

    if variant.mode == "jump" or variant.hybrid:
        jump_decision = _jump_wait_decision(state, legacy_next, legacy_candidate, earliest)
        if jump_decision is not None:
            return jump_decision

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

    if variant.mode == "fixed_hold" and legacy_candidate is not None and not legacy_candidate.safe:
        hold = _hold_candidate(candidates)
        if hold is not None and hold.safe:
            return {
                "taxonomy": "HOLD_UNTIL_SAFE_LEGACY_NEXT",
                "label_kind": "hold_until_safe",
                "label_source": "legacy_wait_until_safe_fixed_step",
                "label_next": legacy_next,
                "executed_kind": "hold",
                "executed_next": state.current,
                "edge_start": "",
                "edge_end": "",
                "node_start": state.ready_time,
                "node_end": hold.node_end,
                "hold_until_time": hold.node_end,
                "hold_duration": hold.node_end - state.ready_time,
                "post_label_safe": True,
                "terminal_reason": "",
                "reroute_attempted": False,
                "sipp_repair_attempted": False,
            }

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


def _jump_wait_decision(
    state: TaskState,
    legacy_next: int | None,
    legacy_candidate: Any | None,
    earliest: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if legacy_next is None or legacy_candidate is None:
        return None
    if not earliest or not earliest.get("reachable"):
        return None
    edge_start = float(earliest["edge_start"])
    hold_duration = max(0.0, edge_start - state.ready_time)
    if hold_duration > MAX_WAIT_SECONDS:
        return None
    return {
        "taxonomy": "HOLD_UNTIL_SAFE_LEGACY_NEXT",
        "label_kind": "hold_until_safe",
        "label_source": "legacy_wait_until_safe_jump",
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
    }


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
        "label_taxonomy": taxonomy,
        "label_kind": decision["label_kind"],
        "label_next": decision["label_next"],
        "hold_until_time": decision["hold_until_time"],
        "hold_duration": decision["hold_duration"],
        "earliest_safe_time": earliest["edge_start"] if earliest_reachable else "",
        "earliest_hold_duration": earliest["hold_duration"] if earliest_reachable else "",
        "earliest_safe_status": earliest["reason"] if earliest else "",
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
        "g4a_primary_eligible": taxonomy in PRIMARY_G4A_TAXA and bool(decision["post_label_safe"]) and not variant.diagnostic and not variant.hybrid,
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
    hold = taxonomy["HOLD_UNTIL_SAFE_LEGACY_NEXT"]
    reroute = taxonomy["REROUTE_NOW_LEGACY"]
    primary = move_now + hold + reroute
    branch_rows = [row for row in slices if row["branch_or_linear"] == "branch"]
    branch_primary = sum(1 for row in branch_rows if row["label_taxonomy"] in PRIMARY_G4A_TAXA)
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
        "move_now_legacy_labels": move_now,
        "hold_until_safe_labels": hold,
        "reroute_now_legacy_labels": reroute,
        "legacy_no_path_labels": taxonomy["LEGACY_NO_PATH"],
        "temporarily_blocked_labels": taxonomy["LEGACY_NEXT_TEMPORARILY_BLOCKED"],
        "globally_unsafe_labels": taxonomy["LEGACY_NEXT_GLOBALLY_UNSAFE"],
        "fallback_safe_labels": taxonomy["FALLBACK_SAFE_MOVE"],
        "sipp_repair_labels": taxonomy["SIPP_REPAIR_MOVE"],
        "abstain_labels": taxonomy["ABSTAIN_NO_TEACHER"],
        "primary_g4a_label_count": primary,
        "primary_g4a_label_coverage": _ratio(primary, decisions),
        "branch_decision_count": len(branch_rows),
        "branch_effective_label_coverage": _ratio(branch_primary, len(branch_rows)),
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
            return {"reachable": False, "reason": "current_node_hold_conflict"}
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
        }
    return {"reachable": False, "reason": "earliest_safe_search_exhausted"}


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
        "baseline": f"g3d_{variant}",
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
            "baseline": f"g3d_{variant}",
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
                "move_now_legacy_labels": sum(int(row["move_now_legacy_labels"]) for row in variant_rows),
                "hold_until_safe_labels": sum(int(row["hold_until_safe_labels"]) for row in variant_rows),
                "reroute_now_legacy_labels": sum(int(row["reroute_now_legacy_labels"]) for row in variant_rows),
                "legacy_no_path_labels": sum(int(row["legacy_no_path_labels"]) for row in variant_rows),
                "temporarily_blocked_labels": sum(int(row["temporarily_blocked_labels"]) for row in variant_rows),
                "globally_unsafe_labels": sum(int(row["globally_unsafe_labels"]) for row in variant_rows),
                "fallback_safe_labels": sum(int(row["fallback_safe_labels"]) for row in variant_rows),
                "sipp_repair_labels": sum(int(row["sipp_repair_labels"]) for row in variant_rows),
                "abstain_labels": sum(int(row["abstain_labels"]) for row in variant_rows),
                "primary_g4a_label_count": primary,
                "primary_g4a_label_coverage": _ratio(primary, decision_count),
                "branch_decision_count": branch_count,
                "branch_effective_label_coverage": _ratio(branch_primary, branch_count),
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
                    "label_role": "primary_g4a" if taxonomy in PRIMARY_G4A_TAXA else "auxiliary_or_exclusion",
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
        if not result.variant.diagnostic and not result.variant.hybrid and result.variant.name != "g3c_baseline_reproduction"
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
            if row["label_taxonomy"] in PRIMARY_G4A_TAXA:
                continue
            rows.append(dict(row))
    return rows


def _reroute_rows(results: tuple[ReplayResult, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if result.variant.name != "reroute_from_current_legacy":
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


def _g4a_manifest_rows(results: tuple[ReplayResult, ...], best_variant: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if result.variant.diagnostic or result.variant.hybrid or result.variant.name == "g3c_baseline_reproduction":
            continue
        for row in result.slices:
            if row["label_taxonomy"] in PRIMARY_G4A_TAXA and row["post_label_safe"]:
                rows.append(dict(row))
    return rows


def _write_jsonl_sample(rows: list[dict[str, Any]]) -> None:
    WAIT_LABEL_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    prioritized = [row for row in rows if row["label_taxonomy"] == "HOLD_UNTIL_SAFE_LEGACY_NEXT"]
    sample = (prioritized + rows)[:MAX_SAMPLE_ROWS]
    with WAIT_LABEL_SAMPLE_PATH.open("w", encoding="utf-8") as handle:
        for row in sample:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_heatmap(blocked_rows: list[dict[str, Any]]) -> None:
    scenarios = [scenario.name for scenario in _case_plan()]
    reasons = sorted({str(row["block_reason"]) for row in blocked_rows if str(row["block_reason"]) != "none"})
    if not reasons:
        reasons = ["none"]
    counts = Counter((str(row["scenario"]), str(row["block_reason"])) for row in blocked_rows)
    matrix = [[counts[(scenario, reason)] for reason in reasons] for scenario in scenarios]
    _write_png_heatmap(HEATMAP_PATH, matrix)


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
    blocked_rows: list[dict[str, Any]],
    earliest_rows: list[dict[str, Any]],
    recovered_rows: list[dict[str, Any]],
    still_blocked_rows: list[dict[str, Any]],
    reroute_rows: list[dict[str, Any]],
    branch_rows: list[dict[str, Any]],
    taxonomy_rows: list[dict[str, Any]],
    g4a_rows: list[dict[str, Any]],
    best_primary_variant: str,
) -> None:
    aggregate = {row["replay_variant"]: row for row in summary_rows if row["scenario"] == "ALL"}
    baseline = aggregate["g3c_baseline_reproduction"]
    best = aggregate[best_primary_variant]
    hybrid = aggregate["hybrid_legacy_wait_sipp_fallback"]
    diagnostic_edge2 = aggregate["ablation_edge_capacity_2"]
    diagnostic_disable_edge = aggregate["ablation_disable_edge_capacity"]
    decision = _decision(best)
    best_taxonomy: Counter[str] = Counter()
    for row in taxonomy_rows:
        if row["replay_variant"] == best_primary_variant:
            best_taxonomy[str(row["label_taxonomy"])] += int(row["count"])
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G3d Legacy-A* Teacher Wait/Horizon Audit",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## 1. Scope and non-claim boundary",
        "",
        "This audit explains blocked Legacy-A* route-next labels from G3c by replaying wait, jump-to-safe-time, reroute, diagnostic ablation, and hybrid repair variants. It does not train a model, does not start RL/PPO/MAPPO, does not create a large G4A dataset, and does not modify legacy Java.",
        "",
        f"- map: `{_relative(MAP_PATH)}`",
        f"- tasks: `{_relative(TASK_PATH)}`",
        f"- teacher source: `{TEACHER_SOURCE}`",
        "",
        "## 2. G3c recap",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ["G3c planned", "78/144"],
                ["G3c blocked/unavailable slices", "614"],
                ["G3c candidate recall", "1.000"],
                ["G3c safe recall", "0.610"],
                ["G3 SIPP safe recall", "0.319"],
                ["G3c post-shield conflicts", "0"],
            ],
        ),
        "",
        "## 3. Blocked slice root-cause ledger",
        "",
        f"G3d baseline reproduction records `{len(blocked_rows)}` non-MOVE_NOW slices. The dominant reasons remain edge-capacity timing and Legacy no-path cases; merge scenarios add merge-group coupling.",
        "",
        _markdown_table(
            ["Reason", "Rows"],
            [[reason, count] for reason, count in Counter(str(row["block_reason"]) for row in blocked_rows).most_common(8)],
        ),
        "",
        "## 4. Earliest-safe-time / wait-until-safe audit",
        "",
        f"Earliest-safe rows written: `{len(earliest_rows)}`. Fixed-hold sweeps test 1s/2s/5s event-horizon effects; jump-to-earliest-safe-time separates transient waits from true no-path or unsafe labels.",
        "",
        "## 5. Replay variants and planned-count comparison",
        "",
        _markdown_table(
            ["Variant", "Planned", "Primary coverage", "Branch coverage", "Conflicts", "Real conflicts"],
            [
                [
                    name,
                    f"{row['planned_count']}/{row['max_tasks']}",
                    f"{float(row['primary_g4a_label_coverage']):.3f}",
                    f"{float(row['branch_effective_label_coverage']):.3f}",
                    row["post_shield_conflicts"],
                    row["real_constraint_conflicts"],
                ]
                for name, row in aggregate.items()
            ],
        ),
        "",
        f"Best primary wait/reroute variant: `{best_primary_variant}` with `{best['planned_count']}/144` planned, `{float(best['branch_effective_label_coverage']):.3f}` branch coverage, and `{best['post_shield_conflicts']}` post-shield conflicts.",
        f"Hybrid repair reaches `{hybrid['planned_count']}/144`, but its SIPP/fallback labels are auxiliary repair data, not primary Legacy labels.",
        f"Capacity diagnostic rows show edge-capacity sensitivity: edge_capacity=2 plans `{diagnostic_edge2['planned_count']}/144`; disabling edge capacity plans `{diagnostic_disable_edge['planned_count']}/144` but has `{diagnostic_disable_edge['real_constraint_conflicts']}` real-constraint conflicts, so it is diagnosis only.",
        "",
        "## 6. Reroute-from-current audit",
        "",
        f"Reroute audit rows written: `{len(reroute_rows)}`. Reroute labels are only primary G4A candidates when the alternate Legacy-compatible next-hop is safe under the current hard mask.",
        "",
        "## 7. Branch vs linear decision breakdown",
        "",
        _markdown_table(
            ["Variant", "Scenario", "Node kind", "Coverage", "Primary labels"],
            [
                [
                    row["replay_variant"],
                    row["scenario"],
                    row["node_kind"],
                    f"{float(row['effective_label_coverage']):.3f}",
                    row["primary_g4a_labels"],
                ]
                for row in branch_rows
                if row["scenario"] == "legacy_offset64_merge32" and row["node_kind"] in {"branch", "linear"}
            ],
        ),
        "",
        "## 8. Label taxonomy for G4A",
        "",
        f"G4A primary-eligible manifest rows: `{len(g4a_rows)}` across non-diagnostic primary variants. Primary labels are restricted to `MOVE_NOW_LEGACY`, `HOLD_UNTIL_SAFE_LEGACY_NEXT`, and `REROUTE_NOW_LEGACY`; `LEGACY_NO_PATH`, `FALLBACK_SAFE_MOVE`, `SIPP_REPAIR_MOVE`, and `ABSTAIN_NO_TEACHER` remain auxiliary/exclusion labels.",
        "",
        _markdown_table(
            ["Taxonomy", "Rows"],
            [[taxonomy, count] for taxonomy, count in best_taxonomy.most_common()],
        ),
        "",
        "## 9. Decision: enter G4A, run more G3d, or fix event semantics first",
        "",
        decision,
        "",
        "## Artifacts",
        "",
        f"- Blocked ledger: `{_relative(BLOCKED_LEDGER_TABLE)}`",
        f"- Earliest safe labels: `{_relative(EARLIEST_SAFE_TABLE)}`",
        f"- Replay variant summary: `{_relative(VARIANT_SUMMARY_TABLE)}`",
        f"- Recovered tasks: `{_relative(RECOVERED_TASKS_TABLE)}`",
        f"- Still blocked after wait: `{_relative(STILL_BLOCKED_TABLE)}`",
        f"- Reroute audit: `{_relative(REROUTE_TABLE)}`",
        f"- Branch vs linear recall: `{_relative(BRANCH_RECALL_TABLE)}`",
        f"- Edge-capacity hotspots: `{_relative(EDGE_HOTSPOT_TABLE)}`",
        f"- Label taxonomy: `{_relative(TAXONOMY_TABLE)}`",
        f"- G4A eligible manifest: `{_relative(G4A_MANIFEST_TABLE)}`",
        f"- Wait-label JSONL sample: `{_relative(WAIT_LABEL_SAMPLE_PATH)}`",
        f"- Block reason heatmap: `{_relative(HEATMAP_PATH)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _decision(best: dict[str, Any]) -> str:
    planned = int(best["planned_count"])
    conflicts = int(best["post_shield_conflicts"])
    branch_coverage = float(best["branch_effective_label_coverage"])
    if conflicts > 0:
        return "Hard stop: post-shield conflicts appeared in the best primary wait/reroute replay. Do not enter G4A or training."
    if planned >= 115 and branch_coverage >= 0.75:
        return "Development pass: Legacy wait/reroute semantics are stable enough for a small G4A pilot dataset, still with explicit label_source and exclusion labels."
    return (
        "Diagnostic pass: do not enter broad G4A or training yet. Wait/reroute semantics improve label taxonomy, "
        "but planned count or branch effective coverage remains below the G3d gate. Continue with event-horizon, "
        "edge-capacity timing, and no-path semantics repair."
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
    baseline_results = tuple(result for result in results if result.variant.name == "g3c_baseline_reproduction")
    blocked_rows = _blocked_ledger_rows(baseline_results)
    earliest_rows = _earliest_safe_rows(baseline_results)
    summary_rows = _aggregate_summary(results)
    recovered_rows = _recovered_task_rows(results)
    best_primary = _best_primary_variant(results)
    still_blocked = _still_blocked_rows(results, best_primary)
    reroute_rows = _reroute_rows(results)
    branch_rows = _branch_rows(results)
    hotspot_rows = _edge_hotspot_rows(blocked_rows)
    taxonomy_rows = _taxonomy_rows(results)
    g4a_rows = _g4a_manifest_rows(results, best_primary)

    _write_csv(BLOCKED_LEDGER_TABLE, blocked_rows, _slice_fields())
    _write_csv(EARLIEST_SAFE_TABLE, earliest_rows, _earliest_fields())
    _write_csv(VARIANT_SUMMARY_TABLE, summary_rows, _summary_fields())
    _write_csv(RECOVERED_TASKS_TABLE, recovered_rows, _recovered_fields())
    _write_csv(STILL_BLOCKED_TABLE, still_blocked, _slice_fields())
    _write_csv(REROUTE_TABLE, reroute_rows, _slice_fields())
    _write_csv(BRANCH_RECALL_TABLE, branch_rows, _branch_fields())
    _write_csv(EDGE_HOTSPOT_TABLE, hotspot_rows, ["scenario", "current", "legacy_next", "branch_or_linear", "block_reason", "blocked_count"])
    _write_csv(TAXONOMY_TABLE, taxonomy_rows, ["scenario", "context", "replay_variant", "label_taxonomy", "label_role", "count", "share"])
    _write_csv(G4A_MANIFEST_TABLE, g4a_rows, _slice_fields())
    _write_jsonl_sample(g4a_rows + still_blocked)
    _write_heatmap(blocked_rows)
    _write_report(
        results=results,
        summary_rows=summary_rows,
        blocked_rows=blocked_rows,
        earliest_rows=earliest_rows,
        recovered_rows=recovered_rows,
        still_blocked_rows=still_blocked,
        reroute_rows=reroute_rows,
        branch_rows=branch_rows,
        taxonomy_rows=taxonomy_rows,
        g4a_rows=g4a_rows,
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
        "label_taxonomy",
        "label_kind",
        "label_next",
        "hold_until_time",
        "hold_duration",
        "earliest_safe_time",
        "earliest_hold_duration",
        "earliest_safe_status",
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
        "move_now_legacy_labels",
        "hold_until_safe_labels",
        "reroute_now_legacy_labels",
        "legacy_no_path_labels",
        "temporarily_blocked_labels",
        "globally_unsafe_labels",
        "fallback_safe_labels",
        "sipp_repair_labels",
        "abstain_labels",
        "primary_g4a_label_count",
        "primary_g4a_label_coverage",
        "branch_decision_count",
        "branch_effective_label_coverage",
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
        raise AssertionError("G3d requires non-empty G3c replay, unavailable, and coverage tables")

    results: list[ReplayResult] = []
    for scenario in _case_plan():
        selected = _selected_tasks(all_tasks, scenario)
        for variant in _variants():
            results.append(_run_replay(graph, selected, scenario, variant))
    _write_all_outputs(tuple(results))

    required = (
        REPORT_PATH,
        BLOCKED_LEDGER_TABLE,
        EARLIEST_SAFE_TABLE,
        VARIANT_SUMMARY_TABLE,
        RECOVERED_TASKS_TABLE,
        STILL_BLOCKED_TABLE,
        REROUTE_TABLE,
        BRANCH_RECALL_TABLE,
        EDGE_HOTSPOT_TABLE,
        TAXONOMY_TABLE,
        G4A_MANIFEST_TABLE,
        WAIT_LABEL_SAMPLE_PATH,
        HEATMAP_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G3d artifacts: {missing}")
    print(
        "g3d complete: "
        f"scenarios={len(_case_plan())} variants={len(_variants())} "
        f"result_rows={len(results)}"
    )


if __name__ == "__main__":
    main()
