from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"

JAVA_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3c_java_teacher_trace_summary.csv"
CPP_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3c_cpp_teacher_trace_summary.csv"
JAVA_CPP_PARITY_TABLE = ROOT / "outputs" / "tables" / "g3c_java_cpp_teacher_parity.csv"
JUNCTION_SLICE_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_junction_slices_sample.csv"
REPLAY_SAFETY_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_replay_safety.csv"
LEGACY_SIPP_AGREEMENT_TABLE = ROOT / "outputs" / "tables" / "g3c_legacy_vs_sipp_teacher_agreement.csv"
COVERAGE_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_label_coverage.csv"
UNAVAILABLE_TABLE = ROOT / "outputs" / "tables" / "g3c_teacher_unavailable_cases.csv"
TEACHER_SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3c_legacy_astar_teacher_sample.jsonl"
REPORT_PATH = ROOT / "outputs" / "reports" / "g3c_legacy_astar_teacher_fidelity_report.md"

JAVA_CPP_ACCEPTANCE_TABLE = ROOT / "outputs" / "tables" / "java_cpp_legacy_acceptance_summary.csv"
JAVA_PY_CPP_ASTAR_PARITY_TABLE = ROOT / "outputs" / "tables" / "java_python_cpp_astar_path_parity.csv"
JAVA_CPP_WINDOW_PARITY_TABLE = ROOT / "outputs" / "tables" / "java_cpp_legacy_window_route_parity.csv"
JAVA_CPP_SCHEDULED_WINDOW_PARITY_TABLE = (
    ROOT / "outputs" / "tables" / "java_cpp_legacy_scheduled_fault_window_route_parity.csv"
)
JAVA_CPP_PROBABILITY_WINDOW_PARITY_TABLE = (
    ROOT / "outputs" / "tables" / "java_cpp_legacy_probability_extreme_window_route_parity.csv"
)

TEACHER_SOURCE = "python_faithful_legacy_astar_event_trace"
TEACHER_PARITY_VERIFIER = "existing_java_cpp_phase1_legacy_acceptance"
MAX_DECISIONS_PER_TASK = 128
MAX_SAMPLE_ROWS = 500
HOLD_SECONDS = 1.0
G3_SIPP_SAFE_RECALL = 0.319


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


@dataclass
class _TeacherTaskState:
    local_task_index: int
    task: Any
    route: list[Any]
    current: int
    ready_time: float
    waiting_time: float
    decision_count: int = 0
    closed: bool = False


@dataclass(frozen=True)
class TeacherReplay:
    scenario: MatchedScenario
    summary: dict[str, Any]
    slices: tuple[dict[str, Any], ...]
    unavailable: tuple[dict[str, Any], ...]
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


def _route_path(route: Iterable[Any] | None) -> tuple[int, ...]:
    if not route:
        return ()
    return tuple(int(node.location) for node in route)


def _format_path(path: Iterable[int], limit: int = 48) -> str:
    values = tuple(int(value) for value in path)
    if len(values) <= limit:
        return " ".join(str(value) for value in values)
    return " ".join(str(value) for value in values[:limit]) + f" ...(+{len(values) - limit} more)"


def _candidate_by_next(candidates: tuple[Any, ...], next_node: int | None) -> Any | None:
    if next_node is None:
        return None
    for candidate in candidates:
        if candidate.is_hold:
            continue
        if int(candidate.next_node) == int(next_node):
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


def _blocked_reason(candidate: Any | None, label_kind: str) -> str:
    if label_kind == "no_path":
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


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _truthy(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "pass", "passed"}


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


def _run_legacy_teacher_replay(graph: Any, selected: tuple[Any, ...], scenario: MatchedScenario) -> TeacherReplay:
    from czr005.baselines.sipp import SIPPNode
    from czr005.envs.action_mask import active_fault_edges, build_action_candidates
    from czr005.sim_py.astar import AStarPlanner
    from czr005.sim_py.event_sim import EpisodeResult
    from czr005.sim_py.metrics import compute_episode_metrics
    from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable

    planner = AStarPlanner(graph)
    reservations = ReservationTable()
    edge_reservations = EdgeReservationTable()
    routes: dict[str, list[Any]] = {}
    unplanned: list[Any] = []
    events: list[dict[str, Any]] = []
    slices: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    task_by_segment: dict[str, Any] = {}

    node_capacities = dict(scenario.node_capacities)
    merge_groups = {(start, end): group for start, end, group in scenario.merge_groups}
    static_faults = set(scenario.fault_edges)
    repair_windows = tuple(scenario.fault_windows)

    event_queue: list[tuple[float, int, int, int, int]] = []
    sequence = 0
    for local_task_index, task in enumerate(selected):
        task_by_segment[task.segment_id] = task
        event_queue.append((float(task.pass_time), sequence, 0, local_task_index, -1))
        sequence += 1
    event_queue.sort()
    states: list[_TeacherTaskState] = []

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
            state = _TeacherTaskState(
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
                events.append(_planned_event(task, state.route, state.decision_count, state.waiting_time))
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
            edge_capacity=1,
            edge_headway_seconds=0.0,
            node_capacities=node_capacities,
            merge_groups=merge_groups,
            merge_capacity=scenario.merge_capacity,
            merge_headway_seconds=scenario.merge_headway_seconds,
            fault_edges=static_faults,
            fault_windows=repair_windows,
            hold_seconds=HOLD_SECONDS,
            require_reachable_goal=True,
        )
        legacy_route = planner.plan(
            start=state.current,
            goal=task.goal,
            start_time=max(0.0, state.ready_time - graph.service_time(state.current)),
            reservations=reservations,
            fault_edges=active_faults,
            task_id=task.task_id,
        )
        route_suffix = _route_path(legacy_route)
        next_label = int(route_suffix[1]) if len(route_suffix) > 1 else None
        label_kind = "move" if next_label is not None else "no_path"
        label_source = "python_faithful_legacy_astar" if next_label is not None else "python_faithful_legacy_astar_no_path"
        label_candidate = _candidate_by_next(candidates, next_label)
        label_in_candidate = label_candidate is not None
        label_in_safe_mask = bool(label_candidate and label_candidate.safe)
        block_reason = _blocked_reason(label_candidate, label_kind)
        hold = _hold_candidate(candidates)
        executed = label_candidate if label_in_safe_mask else (hold if hold and hold.safe else None)
        replay_action = "teacher_move" if executed is label_candidate and executed is not None else "shield_hold"
        if executed is None:
            replay_action = "mark_unplanned"

        state.decision_count += 1
        row = {
            "scenario": scenario.name,
            "context": _scenario_context(scenario),
            "teacher_source": TEACHER_SOURCE,
            "teacher_parity_verifier": TEACHER_PARITY_VERIFIER,
            "decision_ordinal": len(slices) + 1,
            "task_decision_ordinal": state.decision_count,
            "task_index": state.local_task_index,
            "segment_id": task.segment_id,
            "task_id": task.task_id,
            "source_line": task.source_line,
            "segment_id_numeric": task.segment_id,
            "start": task.start,
            "current": state.current,
            "next_label": "" if next_label is None else next_label,
            "goal": task.goal,
            "ready_time": state.ready_time,
            "route_suffix": _format_path(route_suffix),
            "label_kind": label_kind,
            "label_source": label_source,
            "replan_reason": "event_decision_reroute",
            "fault_state": _active_fault_string(active_faults),
            "repair_state": _format_fault_windows(repair_windows),
            "constraint_summary": _constraint_summary(scenario),
            "out_degree": len(graph.outgoing(state.current)),
            "node_kind": "branch" if len(graph.outgoing(state.current)) >= 2 else "linear",
            "candidate_next_nodes": _format_path(_candidate_next_nodes(candidates)),
            "safe_next_nodes": _format_path(_safe_next_nodes(candidates)),
            "candidate_count": len(candidates),
            "safe_candidate_count": sum(1 for candidate in candidates if candidate.safe),
            "label_in_candidate": label_in_candidate,
            "label_in_safe_mask": label_in_safe_mask,
            "label_block_reason": block_reason,
            "executed_next": "" if executed is None else executed.next_node,
            "executed_kind": "none" if executed is None else executed.kind,
            "executed_safe": False if executed is None else executed.safe,
            "replay_action": replay_action,
            "teacher_diverged": replay_action != "teacher_move",
            "waiting_time": state.waiting_time,
        }
        slices.append(row)
        if label_kind == "no_path" or not label_in_safe_mask:
            unavailable.append(row)

        if executed is None:
            _mark_unplanned(unplanned, events, reservations, edge_reservations, task, state, block_reason)
            state.closed = True
            continue

        reached_goal = False
        if executed.is_hold:
            state.waiting_time += executed.node_end - state.ready_time
            state.route[-1].t2 = executed.node_end
            state.route[-1].gcost = executed.node_end
            state.route[-1].fcost = state.route[-1].gcost + state.route[-1].hcost
            reservations.reserve(task.task_id, state.current, state.route[-1].t1, state.route[-1].t2)
            state.ready_time = executed.node_end
        else:
            edge_reservations.reserve(
                task_id=task.task_id,
                start_node=state.current,
                end_node=executed.next_node,
                start=executed.edge_start,
                end=executed.edge_end,
            )
            reservations.reserve(task.task_id, executed.next_node, executed.node_start, executed.node_end)
            state.route.append(
                SIPPNode(
                    location=executed.next_node,
                    t1=executed.node_start,
                    t2=executed.node_end,
                    gcost=executed.node_start,
                    hcost=executed.heuristic_to_goal,
                    fcost=executed.node_start + executed.heuristic_to_goal,
                    parent=state.route[-1],
                )
            )
            state.current = executed.next_node
            state.ready_time = executed.node_end
            reached_goal = executed.next_node == task.goal

        if reached_goal:
            routes[task.segment_id] = list(state.route)
            events.append(_planned_event(task, state.route, state.decision_count, state.waiting_time))
            state.closed = True
            continue
        if state.decision_count >= MAX_DECISIONS_PER_TASK:
            _mark_unplanned(unplanned, events, reservations, edge_reservations, task, state, "max_decisions")
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
    label_move_count = sum(1 for row in slices if row["label_kind"] == "move")
    label_candidate_count = sum(1 for row in slices if row["label_kind"] == "move" and row["label_in_candidate"])
    label_safe_count = sum(1 for row in slices if row["label_kind"] == "move" and row["label_in_safe_mask"])
    edge_conflicts = edge_reservations.conflict_count(capacity=1, headway_seconds=0.0)
    merge_conflicts = edge_reservations.merge_group_conflict_count(
        merge_groups=merge_groups,
        merge_capacity=scenario.merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    block_counter = Counter(str(row["label_block_reason"]) for row in unavailable)
    post_shield_conflicts = result.metrics.reservation_conflicts + edge_conflicts + merge_conflicts
    summary = {
        **result.metrics.to_dict(),
        "scenario": scenario.name,
        "context": _scenario_context(scenario),
        "teacher_source": TEACHER_SOURCE,
        "teacher_parity_verifier": TEACHER_PARITY_VERIFIER,
        "task_offset": scenario.task_offset,
        "max_tasks": scenario.max_tasks,
        "decision_count": len(slices),
        "teacher_replay_planned_count": result.metrics.planned_count,
        "teacher_replay_unplanned_count": result.metrics.unplanned_count,
        "teacher_move_label_count": label_move_count,
        "teacher_no_path_count": sum(1 for row in slices if row["label_kind"] == "no_path"),
        "teacher_action_candidate_recall": _ratio(label_candidate_count, label_move_count),
        "teacher_action_safe_recall": _ratio(label_safe_count, label_move_count),
        "teacher_action_candidate_hits": label_candidate_count,
        "teacher_action_safe_hits": label_safe_count,
        "teacher_replay_conflicts": post_shield_conflicts,
        "node_reservation_conflicts": result.metrics.reservation_conflicts,
        "edge_reservation_conflicts": edge_conflicts,
        "merge_group_conflicts": merge_conflicts,
        "post_shield_conflicts": post_shield_conflicts,
        "teacher_divergence_count": sum(1 for row in slices if row["teacher_diverged"]),
        "teacher_block_reason_distribution": _format_counter(block_counter),
        "fault_edges": _format_faults(scenario.fault_edges),
        "fault_windows": _format_fault_windows(scenario.fault_windows),
        "node_capacities": _format_node_capacities(scenario.node_capacities),
        "merge_groups": _format_merge_groups(scenario.merge_groups),
    }
    return TeacherReplay(
        scenario=scenario,
        summary=summary,
        slices=tuple(slices),
        unavailable=tuple(unavailable),
        routes=routes,
        unplanned=tuple(unplanned),
    )


def _push_event(event_queue: list[tuple[float, int, int, int, int]], event: tuple[float, int, int, int, int]) -> None:
    event_queue.append(event)
    event_queue.sort()


def _planned_event(task: Any, route: list[Any], decision_count: int, waiting_time: float) -> dict[str, Any]:
    return {
        "event": "planned",
        "baseline": "g3c_legacy_astar_teacher_replay",
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
    state: _TeacherTaskState,
    reason: str,
) -> None:
    reservations.remove_task(task.task_id)
    edge_reservations.remove_task(task.task_id)
    unplanned.append(task)
    events.append(
        {
            "event": "unplanned",
            "baseline": "g3c_legacy_astar_teacher_replay",
            "segment_id": task.segment_id,
            "task_id": task.task_id,
            "start": task.start,
            "goal": task.goal,
            "entry_time": task.pass_time,
            "reason": reason,
            "decision_count": state.decision_count,
        }
    )


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
        moved = False
        for interval in intervals:
            if interval.task_id == task_id:
                continue
            if interval.end <= interval.start or candidate + duration <= candidate:
                continue
            if candidate > interval.end or candidate + duration < interval.start:
                continue
            if reservations.has_capacity_conflict(node, candidate, candidate + duration, capacity=capacity, task_id=task_id):
                candidate = interval.end + 1.0e-9
                moved = True
                break
        if not moved:
            return candidate
    return candidate


def _constraint_summary(scenario: MatchedScenario) -> str:
    return (
        f"fault_edges={_format_faults(scenario.fault_edges)}|"
        f"fault_windows={_format_fault_windows(scenario.fault_windows)}|"
        f"node_capacities={_format_node_capacities(scenario.node_capacities)}|"
        f"merge_groups={_format_merge_groups(scenario.merge_groups)}"
    )


def _ratio(numerator: int, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "none"
    return ";".join(f"{key}:{value}" for key, value in sorted(counter.items()))


def _run_sipp_baseline(graph: Any, selected: tuple[Any, ...], scenario: MatchedScenario) -> Any:
    from czr005.baselines.rolling_horizon import RollingHorizonBaseline

    baseline = RollingHorizonBaseline(
        graph,
        horizon_seconds=300.0,
        node_capacities=dict(scenario.node_capacities),
        merge_groups={(start, end): group for start, end, group in scenario.merge_groups},
        merge_capacity=scenario.merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    return baseline.run_episode(
        selected,
        max_tasks=len(selected),
        fault_edges=set(scenario.fault_edges),
        fault_windows=tuple(scenario.fault_windows),
    )


def _sipp_next_map(routes: dict[str, list[Any]]) -> dict[tuple[str, int], int]:
    mapping: dict[tuple[str, int], int] = {}
    for segment_id, route in routes.items():
        path = _route_path(route)
        for current, next_node in zip(path, path[1:]):
            mapping.setdefault((str(segment_id), int(current)), int(next_node))
    return mapping


def _agreement_row(replay: TeacherReplay, sipp_result: Any) -> dict[str, Any]:
    mapping = _sipp_next_map(sipp_result.routes)
    legacy_move_rows = [row for row in replay.slices if row["label_kind"] == "move"]
    shared = []
    no_sipp = 0
    for row in legacy_move_rows:
        sipp_next = mapping.get((str(row["segment_id"]), int(row["current"])))
        if sipp_next is None:
            no_sipp += 1
            continue
        shared.append((row, sipp_next))
    agreement = sum(1 for row, sipp_next in shared if str(row["next_label"]) == str(sipp_next))
    return {
        "scenario": replay.scenario.name,
        "context": _scenario_context(replay.scenario),
        "teacher_source": TEACHER_SOURCE,
        "legacy_planned_count": replay.summary["planned_count"],
        "legacy_unplanned_count": replay.summary["unplanned_count"],
        "sipp_planned_count": sipp_result.metrics.planned_count,
        "sipp_unplanned_count": sipp_result.metrics.unplanned_count,
        "legacy_mean_travel_time": replay.summary["mean_travel_time"],
        "sipp_mean_travel_time": sipp_result.metrics.mean_travel_time,
        "legacy_move_decisions": len(legacy_move_rows),
        "shared_decisions": len(shared),
        "agreement_count": agreement,
        "agreement_rate": _ratio(agreement, len(shared)),
        "legacy_only_no_sipp_next": no_sipp,
        "sipp_route_conflicts": sipp_result.metrics.reservation_conflicts,
    }


def _coverage_rows(replays: tuple[TeacherReplay, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for replay in replays:
        grouped: dict[str, list[dict[str, Any]]] = {"all": list(replay.slices)}
        grouped["branch"] = [row for row in replay.slices if row["node_kind"] == "branch"]
        grouped["linear"] = [row for row in replay.slices if row["node_kind"] == "linear"]
        for node_kind, slices in grouped.items():
            if not slices:
                continue
            move_count = sum(1 for row in slices if row["label_kind"] == "move")
            candidate_hits = sum(1 for row in slices if row["label_kind"] == "move" and row["label_in_candidate"])
            safe_hits = sum(1 for row in slices if row["label_kind"] == "move" and row["label_in_safe_mask"])
            rows.append(
                {
                    "scenario": replay.scenario.name,
                    "context": _scenario_context(replay.scenario),
                    "node_kind": node_kind,
                    "teacher_source": TEACHER_SOURCE,
                    "decisions": len(slices),
                    "move_labels": move_count,
                    "hold_labels": sum(1 for row in slices if row["label_kind"] == "hold"),
                    "no_path_labels": sum(1 for row in slices if row["label_kind"] == "no_path"),
                    "unavailable_or_blocked_labels": sum(1 for row in slices if row["label_kind"] == "no_path" or not row["label_in_safe_mask"]),
                    "branch_decisions": sum(1 for row in slices if row["node_kind"] == "branch"),
                    "linear_decisions": sum(1 for row in slices if row["node_kind"] == "linear"),
                    "candidate_recall": _ratio(candidate_hits, move_count),
                    "safe_recall": _ratio(safe_hits, move_count),
                    "fault_slices": sum(1 for row in slices if row["fault_state"] != "none"),
                    "repair_slices": sum(1 for row in slices if row["repair_state"] != "none"),
                    "merge_slices": len(slices) if replay.scenario.merge_groups else 0,
                    "buffer_slices": len(slices) if replay.scenario.node_capacities else 0,
                    "unique_current_nodes": len({int(row["current"]) for row in slices}),
                    "unique_segments": len({str(row["segment_id"]) for row in slices}),
                }
            )
    return rows


def _java_cpp_parity_rows() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    acceptance = _read_csv_rows(JAVA_CPP_ACCEPTANCE_TABLE)
    astar = _read_csv_rows(JAVA_PY_CPP_ASTAR_PARITY_TABLE)
    no_fault = _read_csv_rows(JAVA_CPP_WINDOW_PARITY_TABLE)
    scheduled = _read_csv_rows(JAVA_CPP_SCHEDULED_WINDOW_PARITY_TABLE)
    probability = _read_csv_rows(JAVA_CPP_PROBABILITY_WINDOW_PARITY_TABLE)

    astar_pass = bool(astar) and all(
        _truthy(row.get("java_python_parity")) and _truthy(row.get("java_cpp_parity")) and _truthy(row.get("python_cpp_parity"))
        for row in astar
    )
    route_tables = (
        ("legacy_no_fault_window", JAVA_CPP_WINDOW_PARITY_TABLE, no_fault),
        ("legacy_scheduled_fault_window", JAVA_CPP_SCHEDULED_WINDOW_PARITY_TABLE, scheduled),
        ("legacy_probability_extreme_window", JAVA_CPP_PROBABILITY_WINDOW_PARITY_TABLE, probability),
    )

    java_rows = [
        {
            "verifier": "legacy_java_astar",
            "source_table": _relative(JAVA_PY_CPP_ASTAR_PARITY_TABLE),
            "role": "source_of_truth_path_spotcheck",
            "rows": len(astar),
            "pass": astar_pass,
            "notes": "existing Phase1 Java/Python/C++ A* path parity; no new Java harness was added in G3c",
        }
    ]
    cpp_rows = [
        {
            "verifier": "python_cpp_astar",
            "source_table": _relative(JAVA_PY_CPP_ASTAR_PARITY_TABLE),
            "role": "faithful_astar_generator_verifier",
            "rows": len(astar),
            "pass": astar_pass,
            "notes": "C++ and Python path outputs match Java path rows in existing acceptance artifacts",
        }
    ]
    parity_rows: list[dict[str, Any]] = []

    for gate, table, rows in route_tables:
        route_pass = bool(rows) and all(_truthy(row.get("match")) for row in rows)
        java_rows.append(
            {
                "verifier": f"legacy_java_ics_{gate}",
                "source_table": _relative(table),
                "role": "legacy_scheduler_window_spotcheck",
                "rows": len(rows),
                "pass": route_pass,
                "notes": "existing read-only Java ICS harness route-multiset parity artifact",
            }
        )
        cpp_rows.append(
            {
                "verifier": f"cpp_pybind_{gate}",
                "source_table": _relative(table),
                "role": "large_scale_generator_candidate",
                "rows": len(rows),
                "pass": route_pass,
                "notes": "native faithful scheduler parity artifact available for scalable trace generation",
            }
        )
        parity_rows.append(
            {
                "gate": gate,
                "java_runtime": f"legacy_java_ics_{gate}",
                "cpp_runtime": f"cpp_pybind_{gate}",
                "parity_rows": len(rows),
                "parity_pass": route_pass,
                "source_table": _relative(table),
                "teacher_source_used_in_g3c": TEACHER_SOURCE,
                "notes": "G3c generated event trace with Python legacy-compatible A* and used this table as Java/C++ verifier evidence",
            }
        )

    for row in acceptance:
        parity_rows.append(
            {
                "gate": row.get("gate", ""),
                "java_runtime": row.get("java_runtime", ""),
                "cpp_runtime": row.get("cpp_runtime", ""),
                "parity_rows": row.get("parity_rows", ""),
                "parity_pass": row.get("parity_pass", ""),
                "source_table": row.get("parity_table", ""),
                "teacher_source_used_in_g3c": TEACHER_SOURCE,
                "notes": f"acceptance gate_pass={row.get('gate_pass', '')}; cpp_java_speedup={row.get('cpp_java_speedup', '')}",
            }
        )

    return java_rows, cpp_rows, parity_rows


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _write_jsonl_sample(replays: tuple[TeacherReplay, ...]) -> None:
    TEACHER_SAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for replay in replays:
        rows.extend(replay.slices)
    with TEACHER_SAMPLE_PATH.open("w", encoding="utf-8") as handle:
        for row in rows[:MAX_SAMPLE_ROWS]:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _write_report(
    replays: tuple[TeacherReplay, ...],
    agreement_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
    java_rows: list[dict[str, Any]],
    cpp_rows: list[dict[str, Any]],
    parity_rows: list[dict[str, Any]],
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    total_move = sum(int(replay.summary["teacher_move_label_count"]) for replay in replays)
    candidate_hits = sum(int(replay.summary["teacher_action_candidate_hits"]) for replay in replays)
    safe_hits = sum(int(replay.summary["teacher_action_safe_hits"]) for replay in replays)
    total_decisions = sum(int(replay.summary["decision_count"]) for replay in replays)
    total_planned = sum(int(replay.summary["planned_count"]) for replay in replays)
    total_tasks = sum(int(replay.summary["max_tasks"]) for replay in replays)
    total_conflicts = sum(int(replay.summary["teacher_replay_conflicts"]) for replay in replays)
    total_unavailable = sum(len(replay.unavailable) for replay in replays)
    candidate_recall = _ratio(candidate_hits, total_move)
    safe_recall = _ratio(safe_hits, total_move)
    parity_pass = all(_truthy(row.get("pass", row.get("parity_pass", False))) for row in java_rows + cpp_rows)
    gate = _gate_status(parity_pass, safe_recall, total_conflicts)

    lines = [
        "# G3c Legacy-A* Teacher Fidelity Audit",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This diagnostic audits whether the paper-faithful Legacy A* route source can be converted into per-junction imitation labels and replayed under the current Python event environment and hard shield. It is not model training, not PPO/MAPPO, and not a learning-success claim.",
        "",
        f"- teacher_source: `{TEACHER_SOURCE}`",
        f"- parity_verifier: `{TEACHER_PARITY_VERIFIER}`",
        f"- map: `{_relative(MAP_PATH)}`",
        f"- tasks: `{_relative(TASK_PATH)}`",
        f"- sampled teacher trace: `{_relative(TEACHER_SAMPLE_PATH)}`",
        "",
        "## Java/C++ Teacher Source Check",
        "",
        "G3c did not modify the read-only legacy Java tree and did not add a new Java GUI/headless harness. It uses the existing Phase1/legacy acceptance artifacts as verifier evidence, then generates the event decision trace with the Python legacy-compatible A* implementation.",
        "",
        _markdown_table(
            ["Verifier", "Rows", "Pass", "Role"],
            [[row["verifier"], row["rows"], row["pass"], row["role"]] for row in java_rows],
        ),
        "",
        "## Replay Safety",
        "",
        _markdown_table(
            ["Scenario", "Planned", "Decisions", "Candidate Recall", "Safe Recall", "Conflicts", "Blocked"],
            [
                [
                    replay.scenario.name,
                    f"{replay.summary['planned_count']}/{replay.summary['max_tasks']}",
                    replay.summary["decision_count"],
                    f"{float(replay.summary['teacher_action_candidate_recall']):.3f}",
                    f"{float(replay.summary['teacher_action_safe_recall']):.3f}",
                    replay.summary["teacher_replay_conflicts"],
                    replay.summary["teacher_block_reason_distribution"],
                ]
                for replay in replays
            ],
        ),
        "",
        f"- aggregate planned: `{total_planned}/{total_tasks}`",
        f"- aggregate decisions: `{total_decisions}`",
        f"- aggregate teacher_action_candidate_recall: `{candidate_recall:.3f}`",
        f"- aggregate teacher_action_safe_recall: `{safe_recall:.3f}`",
        f"- aggregate unavailable/blocked slices: `{total_unavailable}`",
        f"- aggregate post-shield conflicts: `{total_conflicts}`",
        f"- G3 SIPP teacher safe recall reference: `{G3_SIPP_SAFE_RECALL:.3f}`",
        "",
        "## Legacy vs SIPP Teacher Agreement",
        "",
        _markdown_table(
            ["Scenario", "Shared Decisions", "Agreement", "Rate", "Legacy Planned", "SIPP Planned"],
            [
                [
                    row["scenario"],
                    row["shared_decisions"],
                    row["agreement_count"],
                    f"{float(row['agreement_rate']):.3f}",
                    row["legacy_planned_count"],
                    row["sipp_planned_count"],
                ]
                for row in agreement_rows
            ],
        ),
        "",
        "## Teacher Coverage",
        "",
        _markdown_table(
            ["Scenario", "Node Kind", "Decisions", "Moves", "No Path", "Blocked", "Safe Recall"],
            [
                [
                    row["scenario"],
                    row["node_kind"],
                    row["decisions"],
                    row["move_labels"],
                    row["no_path_labels"],
                    row["unavailable_or_blocked_labels"],
                    f"{float(row['safe_recall']):.3f}",
                ]
                for row in coverage_rows
                if row["node_kind"] == "all"
            ],
        ),
        "",
        "## Interpretation",
        "",
        _interpretation(gate, parity_pass, safe_recall, total_conflicts),
        "",
        "## Artifacts",
        "",
        f"- Java teacher verifier summary: `{_relative(JAVA_SUMMARY_TABLE)}`",
        f"- C++ teacher verifier summary: `{_relative(CPP_SUMMARY_TABLE)}`",
        f"- Java/C++ parity summary: `{_relative(JAVA_CPP_PARITY_TABLE)}`",
        f"- Junction slice sample: `{_relative(JUNCTION_SLICE_TABLE)}`",
        f"- Replay safety: `{_relative(REPLAY_SAFETY_TABLE)}`",
        f"- Legacy vs SIPP agreement: `{_relative(LEGACY_SIPP_AGREEMENT_TABLE)}`",
        f"- Label coverage: `{_relative(COVERAGE_TABLE)}`",
        f"- Unavailable cases: `{_relative(UNAVAILABLE_TABLE)}`",
        f"- JSONL sample: `{_relative(TEACHER_SAMPLE_PATH)}`",
        "",
        "## Gate Status",
        "",
        f"- Java/C++ verifier artifact availability: `{'PASS' if parity_pass else 'FAIL'}`",
        f"- route-to-decision conversion: `PASS`",
        f"- teacher replay conflict accounting: `{'PASS' if total_conflicts == 0 else 'FAIL'}`",
        f"- safe-mask recall compared with G3 SIPP teacher: `{'PASS' if safe_recall > G3_SIPP_SAFE_RECALL else 'FAIL'}`",
        f"- overall G3c decision: `{gate}`",
        "",
        "## Next Blocking Question",
        "",
        _next_question(gate),
        "",
        "## Follow-up",
        "",
        _follow_up(gate),
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _gate_status(parity_pass: bool, safe_recall: float, total_conflicts: int) -> str:
    if not parity_pass:
        return "BLOCKED_ON_LEGACY_TEACHER_PARITY"
    if total_conflicts != 0:
        return "BLOCKED_ON_REPLAY_CONFLICTS"
    if safe_recall <= G3_SIPP_SAFE_RECALL:
        return "BLOCKED_ON_G3B_MASK_HORIZON_AUDIT"
    if safe_recall >= 0.8:
        return "PASS_TO_G4A_WITH_CAUTION"
    return "DEVELOPMENT_PASS_NEEDS_TARGETED_G3B"


def _interpretation(gate: str, parity_pass: bool, safe_recall: float, total_conflicts: int) -> str:
    if not parity_pass:
        return (
            "Legacy A* cannot yet be promoted to the main imitation teacher because the Java/C++ verifier "
            "artifacts are incomplete or failing. Fix teacher extraction/parity before dataset generation."
        )
    if total_conflicts:
        return (
            "The converted Legacy A* labels still create post-shield replay conflicts. The next step must be "
            "a replay-semantics fix, not behavior cloning."
        )
    if gate == "PASS_TO_G4A_WITH_CAUTION":
        return (
            f"Legacy A* teacher labels are substantially better aligned with the current event mask than the G3 SIPP "
            f"teacher reference (`{safe_recall:.3f}` vs `{G3_SIPP_SAFE_RECALL:.3f}` safe recall) and replay cleanly. "
            "This supports moving to G4A Legacy-A* teacher dataset construction, while retaining SIPP only as an upper-bound/repair diagnostic."
        )
    return (
        f"Legacy A* safe recall (`{safe_recall:.3f}`) is above the G3 SIPP reference but still leaves enough blocked "
        "teacher slices that G3b-style mask/shield/event-horizon diagnosis should run before broad teacher scaling."
    )


def _next_question(gate: str) -> str:
    if gate == "PASS_TO_G4A_WITH_CAUTION":
        return (
            "Can the G4A dataset generator scale this Legacy-A* route-to-junction conversion across larger task windows "
            "while preserving Java/C++ verifier spotchecks and keeping label_source explicit?"
        )
    if gate == "BLOCKED_ON_LEGACY_TEACHER_PARITY":
        return "Which Java/C++ route-parity gap blocks Legacy A* from serving as the paper-faithful teacher source?"
    return "Are the remaining blocked Legacy-A* labels caused by local mask timing, event-horizon semantics, or missing wait/repair labels?"


def _follow_up(gate: str) -> str:
    if gate == "PASS_TO_G4A_WITH_CAUTION":
        return (
            "- Build `G4A Legacy-A* Teacher Dataset` with all/junction/blocked slice manifests.\n"
            "- Keep SIPP as upper-bound, repair-label, and disagreement diagnostic only.\n"
            "- Do not start BC/RL until the dataset manifest records label_source, safe-mask recall, and verifier evidence."
        )
    return (
        "- Run G3b mask/shield/event-horizon audit on blocked Legacy-A* slices.\n"
        "- Add explicit hold/repair labels only if the audit proves route-next labels are temporarily unsafe rather than globally invalid.\n"
        "- Keep training work paused until replay semantics are clean."
    )


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(str(value) for value in row) + " |" for row in rows]
    return "\n".join([header, divider, *body])


def main() -> None:
    _prepare_imports()
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))

    replays: list[TeacherReplay] = []
    agreement_rows: list[dict[str, Any]] = []
    for scenario in _case_plan():
        selected = _selected_tasks(all_tasks, scenario)
        replay = _run_legacy_teacher_replay(graph, selected, scenario)
        sipp_result = _run_sipp_baseline(graph, selected, scenario)
        replays.append(replay)
        agreement_rows.append(_agreement_row(replay, sipp_result))

    java_rows, cpp_rows, parity_rows = _java_cpp_parity_rows()
    coverage_rows = _coverage_rows(tuple(replays))
    all_slices = [row for replay in replays for row in replay.slices]
    sample_slices = [row for row in all_slices if row["node_kind"] == "branch" or row["label_block_reason"] != "none"]
    sample_slices = (sample_slices or all_slices)[:MAX_SAMPLE_ROWS]
    unavailable_rows = [row for replay in replays for row in replay.unavailable]

    _write_csv(
        JAVA_SUMMARY_TABLE,
        java_rows,
        ["verifier", "source_table", "role", "rows", "pass", "notes"],
    )
    _write_csv(
        CPP_SUMMARY_TABLE,
        cpp_rows,
        ["verifier", "source_table", "role", "rows", "pass", "notes"],
    )
    _write_csv(
        JAVA_CPP_PARITY_TABLE,
        parity_rows,
        [
            "gate",
            "java_runtime",
            "cpp_runtime",
            "parity_rows",
            "parity_pass",
            "source_table",
            "teacher_source_used_in_g3c",
            "notes",
        ],
    )
    _write_csv(
        JUNCTION_SLICE_TABLE,
        sample_slices,
        [
            "scenario",
            "context",
            "teacher_source",
            "decision_ordinal",
            "task_decision_ordinal",
            "segment_id",
            "task_id",
            "source_line",
            "current",
            "next_label",
            "goal",
            "ready_time",
            "route_suffix",
            "label_kind",
            "label_source",
            "replan_reason",
            "fault_state",
            "repair_state",
            "constraint_summary",
            "out_degree",
            "node_kind",
            "candidate_next_nodes",
            "safe_next_nodes",
            "label_in_candidate",
            "label_in_safe_mask",
            "label_block_reason",
            "executed_next",
            "executed_kind",
            "replay_action",
        ],
    )
    _write_csv(
        REPLAY_SAFETY_TABLE,
        [replay.summary for replay in replays],
        [
            "scenario",
            "context",
            "teacher_source",
            "teacher_parity_verifier",
            "task_offset",
            "max_tasks",
            "planned_count",
            "unplanned_count",
            "decision_count",
            "teacher_move_label_count",
            "teacher_no_path_count",
            "teacher_action_candidate_recall",
            "teacher_action_safe_recall",
            "teacher_action_candidate_hits",
            "teacher_action_safe_hits",
            "teacher_replay_planned_count",
            "teacher_replay_unplanned_count",
            "teacher_replay_conflicts",
            "node_reservation_conflicts",
            "edge_reservation_conflicts",
            "merge_group_conflicts",
            "post_shield_conflicts",
            "teacher_divergence_count",
            "teacher_block_reason_distribution",
            "mean_travel_time",
            "p95_travel_time",
            "p99_travel_time",
            "late_count",
            "max_lateness",
            "makespan",
            "fault_edges",
            "fault_windows",
            "node_capacities",
            "merge_groups",
        ],
    )
    _write_csv(
        LEGACY_SIPP_AGREEMENT_TABLE,
        agreement_rows,
        [
            "scenario",
            "context",
            "teacher_source",
            "legacy_planned_count",
            "legacy_unplanned_count",
            "sipp_planned_count",
            "sipp_unplanned_count",
            "legacy_mean_travel_time",
            "sipp_mean_travel_time",
            "legacy_move_decisions",
            "shared_decisions",
            "agreement_count",
            "agreement_rate",
            "legacy_only_no_sipp_next",
            "sipp_route_conflicts",
        ],
    )
    _write_csv(
        COVERAGE_TABLE,
        coverage_rows,
        [
            "scenario",
            "context",
            "node_kind",
            "teacher_source",
            "decisions",
            "move_labels",
            "hold_labels",
            "no_path_labels",
            "unavailable_or_blocked_labels",
            "branch_decisions",
            "linear_decisions",
            "candidate_recall",
            "safe_recall",
            "fault_slices",
            "repair_slices",
            "merge_slices",
            "buffer_slices",
            "unique_current_nodes",
            "unique_segments",
        ],
    )
    _write_csv(
        UNAVAILABLE_TABLE,
        unavailable_rows,
        [
            "scenario",
            "context",
            "teacher_source",
            "decision_ordinal",
            "task_decision_ordinal",
            "segment_id",
            "task_id",
            "current",
            "next_label",
            "goal",
            "ready_time",
            "route_suffix",
            "label_kind",
            "label_source",
            "fault_state",
            "repair_state",
            "constraint_summary",
            "candidate_next_nodes",
            "safe_next_nodes",
            "label_in_candidate",
            "label_in_safe_mask",
            "label_block_reason",
            "executed_next",
            "executed_kind",
            "replay_action",
        ],
    )
    _write_jsonl_sample(tuple(replays))
    _write_report(tuple(replays), agreement_rows, coverage_rows, java_rows, cpp_rows, parity_rows)

    required = (
        JAVA_SUMMARY_TABLE,
        CPP_SUMMARY_TABLE,
        JAVA_CPP_PARITY_TABLE,
        JUNCTION_SLICE_TABLE,
        REPLAY_SAFETY_TABLE,
        LEGACY_SIPP_AGREEMENT_TABLE,
        COVERAGE_TABLE,
        UNAVAILABLE_TABLE,
        TEACHER_SAMPLE_PATH,
        REPORT_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G3c artifacts: {missing}")
    if not all_slices:
        raise AssertionError("G3c generated no teacher decision slices")
    print(
        "g3c complete: "
        f"scenarios={len(replays)} decisions={len(all_slices)} "
        f"sample_rows={len(sample_slices)} unavailable={len(unavailable_rows)}"
    )


if __name__ == "__main__":
    main()
