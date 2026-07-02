from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import heapq
import os
from pathlib import Path
import struct
import sys
from typing import Any, Iterable
import zlib


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
G2_FAILED_TABLE = ROOT / "outputs" / "tables" / "g2_failed_task_inventory.csv"
G2_FAMILY_SUMMARY = ROOT / "outputs" / "tables" / "g2_family_summary.csv"

TEACHER_MASK_TABLE = ROOT / "outputs" / "tables" / "g3_teacher_next_in_mask.csv"
ORACLE_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g3_local_oracle_replay_summary.csv"
RECOVERED_TABLE = ROOT / "outputs" / "tables" / "g3_oracle_recovered_failures.csv"
UNRECOVERABLE_TABLE = ROOT / "outputs" / "tables" / "g3_unrecoverable_failures.csv"
DECOMPOSITION_TABLE = ROOT / "outputs" / "tables" / "g3_oracle_failure_decomposition.csv"
FEATURE_NEED_TABLE = ROOT / "outputs" / "tables" / "g3_feature_need_summary.csv"
HEATMAP_PATH = ROOT / "outputs" / "figures" / "g3_oracle_recovery_heatmap.png"
REPORT_PATH = ROOT / "outputs" / "reports" / "g3_oracle_upper_bound_report.md"

MAX_DECISIONS_PER_TASK = 128
ORACLE_POLICIES = (
    "oracle1_teacher_next",
    "oracle2_sipp_rank",
    "oracle3_lookahead_k2",
    "oracle3_lookahead_k3",
    "oracle3_lookahead_k5",
)


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
class _EventTaskState:
    local_task_index: int
    task: Any
    route: list[Any]
    current: int
    ready_time: float
    waiting_time: float
    decision_count: int = 0
    closed: bool = False


@dataclass(frozen=True)
class DetailedReplayRun:
    result: Any
    summary: dict[str, float | int]
    trace: list[dict[str, Any]]


@dataclass(frozen=True)
class PolicyOutcome:
    planned: bool
    path: tuple[int, ...]
    finish_time: float | None
    decision_count: int
    terminal_reason: str
    trace_rows: tuple[dict[str, Any], ...]


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


def _load_g2_edge_failures() -> dict[tuple[str, str], dict[str, Any]]:
    with G2_FAILED_TABLE.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    failures = {
        (str(row["scenario"]), str(row["segment_id"])): row
        for row in rows
        if row.get("policy_family") == "edge_score_event"
    }
    if len(failures) != 47:
        raise AssertionError(f"expected 47 G2 EdgeScore failures, found {len(failures)}")
    return failures


def _load_g2_recap_rows() -> list[dict[str, str]]:
    if not G2_FAMILY_SUMMARY.exists():
        return []
    with G2_FAMILY_SUMMARY.open("r", encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _route_path(route: Iterable[Any] | None) -> tuple[int, ...]:
    if not route:
        return ()
    return tuple(int(node.location) for node in route)


def _route_finish(route: Iterable[Any] | None) -> float | None:
    values = list(route or ())
    if not values:
        return None
    return float(values[-1].t2)


def _format_path(path: tuple[int, ...], limit: int = 64) -> str:
    if len(path) <= limit:
        return " ".join(str(value) for value in path)
    return " ".join(str(value) for value in path[:limit]) + f" ...(+{len(path) - limit} more)"


def _teacher_next_for_current(teacher_path: tuple[int, ...], current: int) -> int | None:
    for index, node in enumerate(teacher_path[:-1]):
        if int(node) == int(current):
            return int(teacher_path[index + 1])
    return None


def _teacher_rank(teacher_path: tuple[int, ...], current: int, candidate_next: int) -> int | None:
    seen_current = False
    for index, node in enumerate(teacher_path):
        if not seen_current:
            seen_current = int(node) == int(current)
            continue
        if int(node) == int(candidate_next):
            return index
    return None


def _candidate_by_index(candidates: tuple[Any, ...], index: int | None) -> Any | None:
    if index is None:
        return None
    for candidate in candidates:
        if int(candidate.index) == int(index):
            return candidate
    return None


def _candidate_by_next(candidates: tuple[Any, ...], next_node: int | None, safe_only: bool = False) -> Any | None:
    if next_node is None:
        return None
    for candidate in candidates:
        if candidate.is_hold:
            continue
        if int(candidate.next_node) != int(next_node):
            continue
        if safe_only and not candidate.safe:
            continue
        return candidate
    return None


def _fallback_candidate_index(candidates: tuple[Any, ...], goal: int) -> int | None:
    best = None
    best_rank = None
    for candidate in candidates:
        if not candidate.safe or candidate.is_hold:
            continue
        rank = (0 if candidate.next_node == goal else 1, candidate.heuristic_to_goal, candidate.travel_time)
        if best_rank is None or rank < best_rank:
            best = candidate
            best_rank = rank
    if best is not None:
        return int(best.index)
    for candidate in candidates:
        if candidate.safe:
            return int(candidate.index)
    return None


def _edge_score_candidate_index(
    graph: Any,
    task: Any,
    state: _EventTaskState,
    candidates: tuple[Any, ...],
    runtime_model: Any,
    reservations: Any,
    edge_reservations: Any,
    edge_capacity: int,
    edge_headway_seconds: float,
    node_capacities: dict[int, int],
    merge_groups: dict[tuple[int, int], int],
    merge_capacity: int,
    merge_headway_seconds: float,
    fault_edges: set[tuple[int, int]],
    fault_windows: tuple[tuple[int, int, float, float], ...],
    hold_seconds: float,
    require_reachable_goal: bool,
) -> tuple[int | None, int, bool]:
    from czr005.envs.observation_builder import build_junction_observation  # pylint: disable=import-outside-toplevel
    from czr005.models.edge_score import featurize_slice  # pylint: disable=import-outside-toplevel

    obs = build_junction_observation(
        graph=graph,
        task=task,
        current=state.current,
        ready_time=state.ready_time,
        waiting_time=state.waiting_time,
        reservations=reservations,
        edge_reservations=edge_reservations,
        edge_capacity=edge_capacity,
        edge_headway_seconds=edge_headway_seconds,
        node_capacities=node_capacities,
        merge_groups=merge_groups,
        merge_capacity=merge_capacity,
        merge_headway_seconds=merge_headway_seconds,
        fault_edges=fault_edges,
        fault_windows=fault_windows,
        hold_seconds=hold_seconds,
        require_reachable_goal=require_reachable_goal,
    )
    features, _, mask = featurize_slice(
        {
            "obs": obs["task"],
            "candidate_edges": obs["candidates"],
            "action_mask": obs["action_mask"],
            "goal": obs["task"]["goal"],
            "expert_action": 0,
        }
    )
    try:
        selected = int(runtime_model.predict(features, mask))
    except (RuntimeError, ValueError):
        fallback = _fallback_candidate_index(candidates, task.goal)
        return fallback, -1, True
    return selected, selected, False


def _active_faults_for_time(
    fault_edges: set[tuple[int, int]],
    fault_windows: tuple[tuple[int, int, float, float], ...],
    ready_time: float,
) -> set[tuple[int, int]]:
    from czr005.envs.action_mask import active_fault_edges  # pylint: disable=import-outside-toplevel

    return active_fault_edges(fault_edges, fault_windows, ready_time)


def _reservation_pressure(candidate: Any, reservations: Any, edge_reservations: Any, windows: tuple[float, ...] = (15.0, 30.0, 60.0)) -> dict[str, int]:
    pressure: dict[str, int] = {}
    for window in windows:
        edge_end = float(candidate.edge_start) + window
        node_end = float(candidate.node_start) + window
        pressure[f"edge_pressure_{int(window)}s"] = sum(
            1
            for interval in edge_reservations.intervals(int(candidate.current), int(candidate.next_node))
            if interval.overlaps(float(candidate.edge_start), edge_end)
        )
        pressure[f"node_pressure_{int(window)}s"] = sum(
            1
            for interval in reservations.intervals(int(candidate.next_node))
            if interval.overlaps(float(candidate.node_start), node_end)
        )
    return pressure


def _pressure_score(candidate: Any, reservations: Any, edge_reservations: Any) -> tuple[int, int, int, float, float]:
    pressure = _reservation_pressure(candidate, reservations, edge_reservations)
    return (
        pressure["edge_pressure_15s"] + pressure["node_pressure_15s"],
        pressure["edge_pressure_30s"] + pressure["node_pressure_30s"],
        pressure["edge_pressure_60s"] + pressure["node_pressure_60s"],
        float(candidate.heuristic_to_goal),
        float(candidate.travel_time),
    )


def _sipp_rank_candidate_index(
    candidates: tuple[Any, ...],
    teacher_path: tuple[int, ...],
    current: int,
    reservations: Any,
    edge_reservations: Any,
) -> tuple[int | None, str]:
    ranked: list[tuple[tuple[int, int, int, int, float, float], Any]] = []
    for candidate in candidates:
        if not candidate.safe or candidate.is_hold:
            continue
        teacher_rank = _teacher_rank(teacher_path, current, int(candidate.next_node))
        if teacher_rank is None:
            continue
        pressure = _pressure_score(candidate, reservations, edge_reservations)
        ranked.append(((0, teacher_rank, *pressure), candidate))
    if ranked:
        return int(min(ranked, key=lambda item: item[0])[1].index), "teacher_suffix_rank"

    safe_moves = [candidate for candidate in candidates if candidate.safe and not candidate.is_hold]
    if safe_moves:
        chosen = min(safe_moves, key=lambda candidate: _pressure_score(candidate, reservations, edge_reservations))
        return int(chosen.index), "pressure_tiebreak"
    return _fallback_candidate_index(candidates, -1), "safe_hold_fallback"


def _lookahead_candidate_index(
    graph: Any,
    task: Any,
    candidates: tuple[Any, ...],
    reservations: Any,
    edge_reservations: Any,
    fault_edges: set[tuple[int, int]],
    fault_windows: tuple[tuple[int, int, float, float], ...],
    k_steps: int,
) -> tuple[int | None, str]:
    from czr005.sim_py.astar import AStarPlanner  # pylint: disable=import-outside-toplevel

    planner = AStarPlanner(graph)
    scored: list[tuple[tuple[float, int, int, int, float, float], Any]] = []
    for candidate in candidates:
        if not candidate.safe:
            continue
        if candidate.is_hold:
            score = (1000.0 + float(candidate.heuristic_to_goal), 999, 999, 999, float(candidate.heuristic_to_goal), 0.0)
            scored.append((score, candidate))
            continue
        if int(candidate.next_node) == int(task.goal):
            score = (0.0, *_pressure_score(candidate, reservations, edge_reservations))
            scored.append((score, candidate))
            continue
        active_faults = _active_faults_for_time(fault_edges, fault_windows, float(candidate.node_end))
        route = planner.plan(
            start=int(candidate.next_node),
            goal=int(task.goal),
            start_time=float(candidate.node_end),
            reservations=reservations,
            fault_edges=active_faults,
            task_id=int(task.task_id),
        )
        if not route:
            risk = 10_000.0
        else:
            remaining_edges = max(0, len(route) - 1)
            risk = max(0, remaining_edges - k_steps)
        score = (risk, *_pressure_score(candidate, reservations, edge_reservations))
        scored.append((score, candidate))
    if not scored:
        return None, "no_safe_candidate_for_lookahead"
    chosen = min(scored, key=lambda item: item[0])[1]
    return int(chosen.index), f"k_step_{k_steps}_risk_rank"


def _choose_candidate(
    policy: str,
    graph: Any,
    task: Any,
    state: _EventTaskState,
    candidates: tuple[Any, ...],
    runtime_model: Any,
    teacher_path: tuple[int, ...],
    reservations: Any,
    edge_reservations: Any,
    edge_capacity: int,
    edge_headway_seconds: float,
    node_capacities: dict[int, int],
    merge_groups: dict[tuple[int, int], int],
    merge_capacity: int,
    merge_headway_seconds: float,
    fault_edges: set[tuple[int, int]],
    fault_windows: tuple[tuple[int, int, float, float], ...],
    hold_seconds: float,
    require_reachable_goal: bool,
) -> dict[str, Any]:
    teacher_next = _teacher_next_for_current(teacher_path, state.current)
    base_index, proposed_index, base_fallback_used = _edge_score_candidate_index(
        graph,
        task,
        state,
        candidates,
        runtime_model,
        reservations,
        edge_reservations,
        edge_capacity,
        edge_headway_seconds,
        node_capacities,
        merge_groups,
        merge_capacity,
        merge_headway_seconds,
        fault_edges,
        fault_windows,
        hold_seconds,
        require_reachable_goal,
    )
    selected = base_index
    reason = "edge_score"
    oracle_used = False
    if policy == "fallback_event":
        selected = _fallback_candidate_index(candidates, task.goal)
        proposed_index = -1
        reason = "shortest_safe_fallback"
        base_fallback_used = True
    elif policy == "oracle1_teacher_next":
        teacher_candidate = _candidate_by_next(candidates, teacher_next, safe_only=True)
        if teacher_candidate is not None:
            selected = int(teacher_candidate.index)
            reason = "teacher_next_safe"
            oracle_used = True
        else:
            reason = "teacher_next_unavailable_use_edge_score"
    elif policy == "oracle2_sipp_rank":
        selected, reason = _sipp_rank_candidate_index(candidates, teacher_path, state.current, reservations, edge_reservations)
        oracle_used = True
    elif policy.startswith("oracle3_lookahead_k"):
        teacher_candidate = _candidate_by_next(candidates, teacher_next, safe_only=True)
        if teacher_candidate is not None:
            selected = int(teacher_candidate.index)
            reason = "teacher_next_safe"
        else:
            k_steps = int(policy.rsplit("k", 1)[1])
            selected, reason = _lookahead_candidate_index(
                graph,
                task,
                candidates,
                reservations,
                edge_reservations,
                fault_edges,
                fault_windows,
                k_steps,
            )
        oracle_used = True
    return {
        "selected": selected,
        "proposed": proposed_index,
        "base_selected": base_index,
        "fallback_used": base_fallback_used,
        "teacher_next": teacher_next,
        "oracle_used": oracle_used,
        "oracle_reason": reason,
    }


def _candidate_audit(candidates: tuple[Any, ...], teacher_next: int | None) -> dict[str, Any]:
    teacher_candidate = _candidate_by_next(candidates, teacher_next, safe_only=False)
    safe_teacher = teacher_candidate is not None and bool(teacher_candidate.safe)
    block_reasons = ""
    if teacher_candidate is not None and not teacher_candidate.safe:
        block_reasons = ";".join(str(reason) for reason in teacher_candidate.blocked_reasons) or "unsafe_unknown"
    elif teacher_next is None:
        block_reasons = "current_not_on_teacher_path"
    elif teacher_candidate is None:
        block_reasons = "teacher_next_not_candidate"
    safe_moves = [candidate for candidate in candidates if candidate.safe and not candidate.is_hold]
    return {
        "candidate_next_nodes": " ".join(str(candidate.next_node) for candidate in candidates),
        "safe_next_nodes": " ".join(str(candidate.next_node) for candidate in candidates if candidate.safe),
        "move_candidate_next_nodes": " ".join(str(candidate.next_node) for candidate in candidates if not candidate.is_hold),
        "safe_move_next_nodes": " ".join(str(candidate.next_node) for candidate in safe_moves),
        "teacher_next_in_candidate": teacher_candidate is not None,
        "teacher_next_in_safe_mask": safe_teacher,
        "teacher_next_block_reason": block_reasons,
        "blocked_reasons_summary": "|".join(
            f"{candidate.next_node}:{';'.join(candidate.blocked_reasons)}"
            for candidate in candidates
            if candidate.blocked_reasons
        ),
    }


def _detailed_trace_row(
    trace: list[dict[str, Any]],
    policy: str,
    scenario: MatchedScenario,
    state: _EventTaskState,
    event: str,
    terminal_reason: str,
    candidates: tuple[Any, ...],
    choice: dict[str, Any],
    executed: Any | None,
    unsafe_proposal: bool,
    reached_goal: bool = False,
) -> dict[str, Any]:
    teacher_next = choice.get("teacher_next")
    audit = _candidate_audit(candidates, teacher_next)
    if executed is None:
        executed_index = -1
        executed_next = state.current
        executed_kind = "none"
        executed_safe = False
        route_size_after = len(state.route)
        pressure = {"edge_pressure_15s": "", "node_pressure_15s": "", "edge_pressure_30s": "", "node_pressure_30s": "", "edge_pressure_60s": "", "node_pressure_60s": ""}
    else:
        executed_index = int(executed.index)
        executed_next = int(executed.next_node)
        executed_kind = str(executed.kind)
        executed_safe = bool(executed.safe)
        route_size_after = len(state.route) + (0 if executed.is_hold else 1)
        pressure = choice.get("pressure", {})
    return {
        "scenario": scenario.name,
        "policy": policy,
        "scenario_context": _scenario_context(scenario),
        "decision_ordinal": len(trace) + 1,
        "task_decision_ordinal": state.decision_count,
        "event": event,
        "terminal_reason": terminal_reason,
        "task_index": state.local_task_index,
        "task_global_index": scenario.task_offset + state.local_task_index,
        "segment_id": state.task.segment_id,
        "task_id": int(state.task.task_id),
        "source_line": int(state.task.source_line),
        "current": int(state.current),
        "goal": int(state.task.goal),
        "ready_time": float(state.ready_time),
        "waiting_time": float(state.waiting_time),
        "proposed_position": choice.get("proposed", ""),
        "base_selected_position": choice.get("base_selected", ""),
        "executed_index": executed_index,
        "executed_next": executed_next,
        "executed_kind": executed_kind,
        "executed_safe": executed_safe,
        "unsafe_proposal": unsafe_proposal,
        "fallback_used": bool(choice.get("fallback_used", False)),
        "oracle_used": bool(choice.get("oracle_used", False)),
        "oracle_reason": str(choice.get("oracle_reason", "")),
        "reached_goal": reached_goal,
        "candidate_count": len(candidates),
        "safe_candidate_count": sum(1 for candidate in candidates if candidate.safe),
        "route_size_after": route_size_after,
        "teacher_next": "" if teacher_next is None else int(teacher_next),
        **audit,
        **pressure,
    }


def _add_planned_event(routes: dict[str, list[Any]], events: list[dict[str, object]], task: Any, route: list[Any], decision_count: int, waiting_time: float, policy: str) -> None:
    routes[task.segment_id] = list(route)
    events.append(
        {
            "event": "planned",
            "baseline": policy,
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
    )


def _mark_unplanned(unplanned: list[Any], events: list[dict[str, object]], reservations: Any, edge_reservations: Any, task: Any, state: _EventTaskState, reason: str, shield_blocked: bool, policy: str) -> None:
    reservations.remove_task(task.task_id)
    edge_reservations.remove_task(task.task_id)
    unplanned.append(task)
    events.append(
        {
            "event": "unplanned",
            "baseline": policy,
            "segment_id": task.segment_id,
            "task_id": task.task_id,
            "start": task.start,
            "goal": task.goal,
            "entry_time": task.pass_time,
            "reason": reason,
            "decision_count": state.decision_count,
            "shield_blocked": shield_blocked,
        }
    )


def _earliest_safe_node_start(reservations: Any, node: int, earliest_start: float, duration: float, task_id: int, capacity: int = 1) -> float:
    candidate = earliest_start
    intervals = sorted(reservations.intervals(node), key=lambda item: (item.start, item.end, item.task_id))
    for _ in range(len(intervals) * 2 + 2):
        moved = False
        for interval in intervals:
            if interval.task_id == task_id:
                continue
            if interval.end <= interval.start or candidate > interval.end or candidate + duration < interval.start:
                continue
            if reservations.has_capacity_conflict(node, candidate, candidate + duration, capacity=capacity, task_id=task_id):
                candidate = interval.end + 1.0e-9
                moved = True
                break
        if not moved:
            return candidate
    return candidate


def _run_detailed_event_replay(
    graph: Any,
    tasks: tuple[Any, ...],
    scenario: MatchedScenario,
    policy: str,
    runtime_model: Any,
    teacher_paths: dict[str, tuple[int, ...]],
    hold_seconds: float = 1.0,
    edge_capacity: int = 1,
    edge_headway_seconds: float = 0.0,
    require_reachable_goal: bool = True,
) -> DetailedReplayRun:
    from czr005.baselines.sipp import SIPPNode  # pylint: disable=import-outside-toplevel
    from czr005.envs.action_mask import build_action_candidates  # pylint: disable=import-outside-toplevel
    from czr005.sim_py.event_sim import EpisodeResult  # pylint: disable=import-outside-toplevel
    from czr005.sim_py.metrics import compute_episode_metrics  # pylint: disable=import-outside-toplevel
    from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable  # pylint: disable=import-outside-toplevel

    node_capacities = dict(scenario.node_capacities)
    merge_groups = {(start, end): group for start, end, group in scenario.merge_groups}
    fault_edges = set(scenario.fault_edges)
    fault_windows = tuple(scenario.fault_windows)

    reservations = ReservationTable()
    edge_reservations = EdgeReservationTable()
    routes: dict[str, list[Any]] = {}
    unplanned: list[Any] = []
    events: list[dict[str, object]] = []
    task_by_segment: dict[str, Any] = {}
    trace: list[dict[str, Any]] = []
    shield_blocks = 0
    unsafe_proposals = 0

    event_queue: list[tuple[float, int, int, int, int]] = []
    sequence = 0
    limit = min(scenario.max_tasks, len(tasks))
    for local_task_index in range(limit):
        task = tasks[local_task_index]
        heapq.heappush(event_queue, (float(task.pass_time), sequence, 0, local_task_index, -1))
        sequence += 1

    states: list[_EventTaskState] = []
    while event_queue:
        _, _, event_kind, local_task_index, state_index = heapq.heappop(event_queue)
        if event_kind == 0:
            task = tasks[local_task_index]
            task_by_segment[task.segment_id] = task
            start_duration = graph.service_time(task.start)
            start_time = _earliest_safe_node_start(
                reservations,
                task.start,
                task.pass_time,
                start_duration,
                task.task_id,
                node_capacities.get(task.start, 1),
            )
            route = [
                SIPPNode(
                    location=task.start,
                    t1=start_time,
                    t2=start_time + start_duration,
                    gcost=start_time,
                    hcost=graph.heuristic(task.start, task.goal),
                    fcost=start_time + graph.heuristic(task.start, task.goal),
                    parent=None,
                )
            ]
            reservations.reserve(task.task_id, task.start, route[-1].t1, route[-1].t2)
            state = _EventTaskState(
                local_task_index=local_task_index,
                task=task,
                route=route,
                current=task.start,
                ready_time=route[-1].t2,
                waiting_time=max(0.0, start_time - task.pass_time),
            )
            states.append(state)
            created_state_index = len(states) - 1
            if task.start == task.goal:
                state.closed = True
                _add_planned_event(routes, events, task, state.route, state.decision_count, state.waiting_time, policy)
            else:
                heapq.heappush(event_queue, (state.ready_time, sequence, 1, local_task_index, created_state_index))
                sequence += 1
            continue

        state = states[state_index]
        if state.closed:
            continue
        task = state.task
        candidates = build_action_candidates(
            graph=graph,
            task=task,
            current=state.current,
            ready_time=state.ready_time,
            reservations=reservations,
            edge_reservations=edge_reservations,
            edge_capacity=edge_capacity,
            edge_headway_seconds=edge_headway_seconds,
            node_capacities=node_capacities,
            merge_groups=merge_groups,
            merge_capacity=scenario.merge_capacity,
            merge_headway_seconds=scenario.merge_headway_seconds,
            fault_edges=fault_edges,
            fault_windows=fault_windows,
            hold_seconds=hold_seconds,
            require_reachable_goal=require_reachable_goal,
        )
        choice = _choose_candidate(
            policy,
            graph,
            task,
            state,
            candidates,
            runtime_model,
            teacher_paths.get(str(task.segment_id), ()),
            reservations,
            edge_reservations,
            edge_capacity,
            edge_headway_seconds,
            node_capacities,
            merge_groups,
            scenario.merge_capacity,
            scenario.merge_headway_seconds,
            fault_edges,
            fault_windows,
            hold_seconds,
            require_reachable_goal,
        )

        state.decision_count += 1
        chosen_position = choice["selected"]
        if chosen_position is None or int(chosen_position) < 0 or int(chosen_position) >= len(candidates):
            terminal_reason = "no_safe_action" if chosen_position is None or int(chosen_position) < 0 else "invalid_action"
            trace.append(
                _detailed_trace_row(
                    trace,
                    policy,
                    scenario,
                    state,
                    "unplanned",
                    terminal_reason,
                    candidates,
                    choice,
                    None,
                    unsafe_proposal=False,
                )
            )
            _mark_unplanned(unplanned, events, reservations, edge_reservations, task, state, terminal_reason, bool(choice.get("fallback_used", False)), policy)
            state.closed = True
            continue

        chosen = candidates[int(chosen_position)]
        unsafe_proposal = False
        if not chosen.safe:
            unsafe_proposals += 1
            unsafe_proposal = True
            fallback_index = _fallback_candidate_index(candidates, task.goal)
            choice = {**choice, "selected": fallback_index, "fallback_used": True, "oracle_reason": str(choice.get("oracle_reason", "")) + "|shield_fallback"}
            if fallback_index is None:
                trace.append(
                    _detailed_trace_row(
                        trace,
                        policy,
                        scenario,
                        state,
                        "unplanned",
                        "unsafe_no_safe_fallback",
                        candidates,
                        choice,
                        None,
                        unsafe_proposal=True,
                    )
                )
                _mark_unplanned(unplanned, events, reservations, edge_reservations, task, state, "unsafe_no_safe_fallback", True, policy)
                state.closed = True
                continue
            chosen = candidates[int(fallback_index)]
            shield_blocks += 1

        executed = chosen
        reached_goal = not executed.is_hold and executed.next_node == task.goal
        choice = {**choice, "pressure": _reservation_pressure(executed, reservations, edge_reservations)}
        trace.append(
            _detailed_trace_row(
                trace,
                policy,
                scenario,
                state,
                "step",
                "",
                candidates,
                choice,
                executed,
                unsafe_proposal=unsafe_proposal,
                reached_goal=reached_goal,
            )
        )

        if executed.is_hold:
            state.waiting_time += executed.node_end - state.ready_time
            state.route[-1].t2 = executed.node_end
            state.route[-1].gcost = executed.node_end
            state.route[-1].fcost = state.route[-1].gcost + state.route[-1].hcost
            reservations.reserve(task.task_id, state.current, state.route[-1].t1, state.route[-1].t2)
            state.ready_time = executed.node_end
        else:
            edge_reservations.reserve(task.task_id, state.current, executed.next_node, executed.edge_start, executed.edge_end)
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

        if reached_goal:
            _add_planned_event(routes, events, task, state.route, state.decision_count, state.waiting_time, policy)
            state.closed = True
            continue
        if state.decision_count >= MAX_DECISIONS_PER_TASK:
            _mark_unplanned(unplanned, events, reservations, edge_reservations, task, state, "max_decisions", False, policy)
            state.closed = True
            continue
        heapq.heappush(event_queue, (state.ready_time, sequence, 1, state.local_task_index, state_index))
        sequence += 1

    result = EpisodeResult(
        routes=routes,
        unplanned=unplanned,
        events=events,
        metrics=compute_episode_metrics(routes, task_by_segment, unplanned, reservations, node_capacities=node_capacities),
    )
    edge_conflicts = edge_reservations.conflict_count(capacity=edge_capacity, headway_seconds=edge_headway_seconds)
    merge_conflicts = edge_reservations.merge_group_conflict_count(merge_groups, scenario.merge_capacity, scenario.merge_headway_seconds)
    summary = {
        **result.metrics.to_dict(),
        "max_tasks": limit,
        "decision_count": len(trace),
        "shield_blocks": shield_blocks,
        "unsafe_proposals": unsafe_proposals,
        "edge_reservation_conflicts": edge_conflicts,
        "merge_group_conflicts": merge_conflicts,
        "post_shield_conflicts": result.metrics.reservation_conflicts + edge_conflicts + merge_conflicts,
        "completed_events": len([event for event in events if event["event"] == "planned"]),
    }
    return DetailedReplayRun(result=result, summary=summary, trace=trace)


def _outcomes_from_run(tasks: tuple[Any, ...], run: DetailedReplayRun) -> dict[str, PolicyOutcome]:
    traces: dict[str, list[dict[str, Any]]] = defaultdict(list)
    events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in run.trace:
        traces[str(row["segment_id"])].append(dict(row))
    for event in run.result.events:
        events[str(event["segment_id"])].append(dict(event))
    outcomes: dict[str, PolicyOutcome] = {}
    for task in tasks:
        segment = str(task.segment_id)
        route = run.result.routes.get(segment)
        rows = traces.get(segment, [])
        task_events = events.get(segment, [])
        terminal_reason = ""
        if route is None:
            terminal_reason = next((str(row.get("terminal_reason")) for row in rows if row.get("event") == "unplanned"), "")
            if not terminal_reason:
                terminal_reason = next((str(event.get("reason")) for event in task_events if event.get("event") == "unplanned"), "")
        path = _route_path(route) if route is not None else _trace_path(task, rows)
        outcomes[segment] = PolicyOutcome(
            planned=route is not None,
            path=path,
            finish_time=_route_finish(route),
            decision_count=max((int(row.get("task_decision_ordinal", 0)) for row in rows), default=0),
            terminal_reason=terminal_reason,
            trace_rows=tuple(rows),
        )
    return outcomes


def _outcomes_from_episode(tasks: tuple[Any, ...], result: Any) -> dict[str, PolicyOutcome]:
    events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in result.events:
        events[str(event["segment_id"])].append(dict(event))
    outcomes: dict[str, PolicyOutcome] = {}
    for task in tasks:
        segment = str(task.segment_id)
        route = result.routes.get(segment)
        task_events = events.get(segment, [])
        terminal_reason = "" if route is not None else next((str(event.get("reason", "unplanned")) for event in task_events if event.get("event") == "unplanned"), "unplanned")
        outcomes[segment] = PolicyOutcome(
            planned=route is not None,
            path=_route_path(route),
            finish_time=_route_finish(route),
            decision_count=max((int(event.get("decision_count", event.get("replan_count", 0))) for event in task_events), default=0),
            terminal_reason=terminal_reason,
            trace_rows=tuple(task_events),
        )
    return outcomes


def _trace_path(task: Any, rows: list[dict[str, Any]]) -> tuple[int, ...]:
    path = [int(task.start)]
    for row in rows:
        if row.get("event") != "step" or row.get("executed_kind") != "move":
            continue
        next_node = int(row["executed_next"])
        if path[-1] != next_node:
            path.append(next_node)
    return tuple(path)


def _run_teacher(graph: Any, tasks: tuple[Any, ...], scenario: MatchedScenario) -> tuple[Any, dict[str, PolicyOutcome], dict[str, tuple[int, ...]], dict[str, Any]]:
    from czr005.baselines import RollingHorizonBaseline  # pylint: disable=import-outside-toplevel

    baseline = RollingHorizonBaseline(
        graph,
        horizon_seconds=300.0,
        node_capacities=dict(scenario.node_capacities),
        merge_groups={(start, end): group for start, end, group in scenario.merge_groups},
        merge_capacity=scenario.merge_capacity,
        merge_headway_seconds=scenario.merge_headway_seconds,
    )
    result = baseline.run_episode(
        tasks,
        max_tasks=scenario.max_tasks,
        fault_edges=set(scenario.fault_edges),
        fault_windows=scenario.fault_windows,
    )
    edge_conflicts = baseline.edge_reservations.conflict_count() + baseline.edge_reservations.merge_group_conflict_count(
        {(start, end): group for start, end, group in scenario.merge_groups},
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    summary = {
        **result.metrics.to_dict(),
        "max_tasks": scenario.max_tasks,
        "decision_count": len(result.events),
        "post_shield_conflicts": result.metrics.reservation_conflicts + edge_conflicts,
    }
    outcomes = _outcomes_from_episode(tasks, result)
    teacher_paths = {segment: outcome.path for segment, outcome in outcomes.items()}
    return result, outcomes, teacher_paths, summary


def _build_teacher_mask_rows(
    scenario: MatchedScenario,
    tasks: tuple[Any, ...],
    baseline_run: DetailedReplayRun,
    g2_failures: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    task_by_segment = {str(task.segment_id): task for task in tasks}
    rows: list[dict[str, Any]] = []
    first_divergence_seen: set[str] = set()
    for trace_row in baseline_run.trace:
        segment = str(trace_row["segment_id"])
        failure = g2_failures.get((scenario.name, segment))
        if failure is None:
            continue
        current = str(trace_row["current"])
        teacher_next = str(trace_row["teacher_next"])
        is_first = (
            segment not in first_divergence_seen
            and current == str(failure.get("first_divergence_current", ""))
            and teacher_next == str(failure.get("sipp_teacher_next", ""))
        )
        if is_first:
            first_divergence_seen.add(segment)
        task = task_by_segment[segment]
        rows.append(
            {
                "scenario": scenario.name,
                "scenario_context": _scenario_context(scenario),
                "segment_id": segment,
                "task_id": int(task.task_id),
                "task_global_index": int(trace_row["task_global_index"]),
                "source_line": int(task.source_line),
                "failure_motif": failure.get("failure_motif", ""),
                "is_g2_failed_task": True,
                "is_g2_first_divergence": is_first,
                "current": int(trace_row["current"]),
                "goal": int(trace_row["goal"]),
                "ready_time": float(trace_row["ready_time"]),
                "teacher_next": trace_row["teacher_next"],
                "teacher_next_in_candidate": bool(trace_row["teacher_next_in_candidate"]),
                "teacher_next_in_safe_mask": bool(trace_row["teacher_next_in_safe_mask"]),
                "teacher_next_block_reason": trace_row["teacher_next_block_reason"],
                "candidate_count": int(trace_row["candidate_count"]),
                "safe_candidate_count": int(trace_row["safe_candidate_count"]),
                "candidate_next_nodes": trace_row["candidate_next_nodes"],
                "safe_next_nodes": trace_row["safe_next_nodes"],
                "executed_next": int(trace_row["executed_next"]),
                "executed_kind": trace_row["executed_kind"],
                "oracle_reason": trace_row["oracle_reason"],
                "edge_pressure_15s": trace_row["edge_pressure_15s"],
                "node_pressure_15s": trace_row["node_pressure_15s"],
                "edge_pressure_30s": trace_row["edge_pressure_30s"],
                "node_pressure_30s": trace_row["node_pressure_30s"],
                "edge_pressure_60s": trace_row["edge_pressure_60s"],
                "node_pressure_60s": trace_row["node_pressure_60s"],
                "blocked_reasons_summary": trace_row["blocked_reasons_summary"],
            }
        )
    return rows


def _summarize_oracle_rows(
    scenario: MatchedScenario,
    policy: str,
    run: DetailedReplayRun,
    edge_outcomes: dict[str, PolicyOutcome],
    oracle_outcomes: dict[str, PolicyOutcome],
    g2_failures: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    failed_segments = [segment for scen, segment in g2_failures if scen == scenario.name]
    recovered = sum(1 for segment in failed_segments if not edge_outcomes[segment].planned and oracle_outcomes[segment].planned)
    remaining = sum(1 for segment in failed_segments if not edge_outcomes[segment].planned and not oracle_outcomes[segment].planned)
    new_regressions = sum(
        1
        for segment, edge_outcome in edge_outcomes.items()
        if (scenario.name, segment) not in g2_failures and edge_outcome.planned and not oracle_outcomes[segment].planned
    )
    return {
        "scenario": scenario.name,
        "scenario_context": _scenario_context(scenario),
        "policy": policy,
        "max_tasks": int(run.summary["max_tasks"]),
        "planned_count": int(run.summary["planned_count"]),
        "unplanned_count": int(run.summary["unplanned_count"]),
        "decision_count": int(run.summary["decision_count"]),
        "post_shield_conflicts": int(run.summary["post_shield_conflicts"]),
        "mean_travel_time": float(run.summary["mean_travel_time"]),
        "edge_score_failed_rows_in_scenario": len(failed_segments),
        "recovered_edge_score_failures": recovered,
        "remaining_edge_score_failures": remaining,
        "new_regressions_vs_edge_score": new_regressions,
        "recovery_rate_of_edge_score_failures": recovered / len(failed_segments) if failed_segments else 0.0,
    }


def _aggregate_summary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["policy"])].append(row)
    aggregate_rows: list[dict[str, Any]] = []
    for policy, values in grouped.items():
        total_failures = sum(int(row["edge_score_failed_rows_in_scenario"]) for row in values)
        recovered = sum(int(row["recovered_edge_score_failures"]) for row in values)
        aggregate_rows.append(
            {
                "scenario": "ALL",
                "scenario_context": "all",
                "policy": policy,
                "max_tasks": sum(int(row["max_tasks"]) for row in values),
                "planned_count": sum(int(row["planned_count"]) for row in values),
                "unplanned_count": sum(int(row["unplanned_count"]) for row in values),
                "decision_count": sum(int(row["decision_count"]) for row in values),
                "post_shield_conflicts": sum(int(row["post_shield_conflicts"]) for row in values),
                "mean_travel_time": _weighted_mean(values, "mean_travel_time", "planned_count"),
                "edge_score_failed_rows_in_scenario": total_failures,
                "recovered_edge_score_failures": recovered,
                "remaining_edge_score_failures": sum(int(row["remaining_edge_score_failures"]) for row in values),
                "new_regressions_vs_edge_score": sum(int(row["new_regressions_vs_edge_score"]) for row in values),
                "recovery_rate_of_edge_score_failures": recovered / total_failures if total_failures else 0.0,
            }
        )
    return rows + aggregate_rows


def _weighted_mean(rows: list[dict[str, Any]], value_key: str, weight_key: str) -> float:
    total_weight = sum(int(row[weight_key]) for row in rows)
    if total_weight <= 0:
        return 0.0
    return sum(float(row[value_key]) * int(row[weight_key]) for row in rows) / total_weight


def _build_recovery_tables(
    scenario: MatchedScenario,
    policy: str,
    edge_outcomes: dict[str, PolicyOutcome],
    oracle_outcomes: dict[str, PolicyOutcome],
    teacher_outcomes: dict[str, PolicyOutcome],
    g2_failures: dict[tuple[str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    recovered_rows: list[dict[str, Any]] = []
    unrecovered_rows: list[dict[str, Any]] = []
    for (failed_scenario, segment), failure in g2_failures.items():
        if failed_scenario != scenario.name:
            continue
        edge = edge_outcomes[segment]
        oracle = oracle_outcomes[segment]
        teacher = teacher_outcomes[segment]
        row = {
            "scenario": scenario.name,
            "scenario_context": _scenario_context(scenario),
            "oracle_policy": policy,
            "segment_id": segment,
            "task_id": failure.get("task_id", ""),
            "source_line": failure.get("source_line", ""),
            "failure_motif": failure.get("failure_motif", ""),
            "first_divergence_current": failure.get("first_divergence_current", ""),
            "sipp_teacher_next": failure.get("sipp_teacher_next", ""),
            "edge_score_terminal_reason": edge.terminal_reason,
            "oracle_terminal_reason": oracle.terminal_reason,
            "teacher_finish_time": "" if teacher.finish_time is None else teacher.finish_time,
            "oracle_finish_time": "" if oracle.finish_time is None else oracle.finish_time,
            "oracle_decision_count": oracle.decision_count,
            "teacher_path": _format_path(teacher.path),
            "oracle_path": _format_path(oracle.path),
        }
        if not edge.planned and oracle.planned:
            recovered_rows.append({**row, "recovery_status": "recovered"})
        elif not edge.planned and not oracle.planned:
            unrecovered_rows.append({**row, "recovery_status": "unrecoverable", "unrecoverable_reason": _unrecoverable_reason(failure, oracle)})
    return recovered_rows, unrecovered_rows


def _unrecoverable_reason(failure: dict[str, Any], oracle: PolicyOutcome) -> str:
    terminal = oracle.terminal_reason
    motif = str(failure.get("failure_motif", ""))
    if terminal in {"no_safe_action", "unsafe_no_safe_fallback"}:
        return "no_safe_action_or_mask_timing"
    if terminal == "max_decisions":
        return "event_horizon_max_decisions"
    if "repair" in motif or "fault" in motif:
        return "fault_repair_context_unresolved"
    if "merge" in motif or "buffer" in motif:
        return "nonlocal_capacity_context_unresolved"
    return terminal or "oracle_still_failed"


def _feature_need_for_failure(mask_row: dict[str, Any] | None, recovered_by: set[str], failure: dict[str, Any]) -> str:
    if mask_row is None:
        return "missing_decision_audit"
    if not bool(mask_row["teacher_next_in_candidate"]):
        return "candidate_set_or_teacher_path_alignment"
    if not bool(mask_row["teacher_next_in_safe_mask"]):
        return "mask_shield_timing"
    if "oracle1_teacher_next" in recovered_by or "oracle2_sipp_rank" in recovered_by:
        return "sipp_rank_supervision"
    if any(policy.startswith("oracle3_lookahead") for policy in recovered_by):
        return "k_step_horizon_features"
    motif = str(failure.get("failure_motif", ""))
    if "merge" in motif or "buffer" in motif:
        return "nonlocal_capacity_features"
    if "repair" in motif or "fault" in motif:
        return "fault_repair_features"
    return "event_horizon_or_global_guidance"


def _build_feature_need_summary(
    teacher_mask_rows: list[dict[str, Any]],
    recovered_rows: list[dict[str, Any]],
    unrecovered_rows: list[dict[str, Any]],
    g2_failures: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    first_mask: dict[tuple[str, str], dict[str, Any]] = {}
    for row in teacher_mask_rows:
        key = (str(row["scenario"]), str(row["segment_id"]))
        if bool(row["is_g2_first_divergence"]) and key not in first_mask:
            first_mask[key] = row
    recovered_by_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in recovered_rows:
        recovered_by_key[(str(row["scenario"]), str(row["segment_id"]))].add(str(row["oracle_policy"]))

    grouped: dict[str, dict[str, Any]] = {}
    unrecovered_by_key = {(str(row["scenario"]), str(row["segment_id"]), str(row["oracle_policy"])) for row in unrecovered_rows}
    for key, failure in g2_failures.items():
        need = _feature_need_for_failure(first_mask.get(key), recovered_by_key.get(key, set()), failure)
        item = grouped.setdefault(
            need,
            {
                "feature_need": need,
                "edge_score_failed_rows": 0,
                "teacher_next_candidate_rows": 0,
                "teacher_next_safe_rows": 0,
                "recovered_by_oracle1": 0,
                "recovered_by_oracle2": 0,
                "recovered_by_oracle3_k5": 0,
                "still_unrecovered_by_best_oracle": 0,
                "example_follow_up": _feature_follow_up(need),
            },
        )
        item["edge_score_failed_rows"] += 1
        mask = first_mask.get(key)
        if mask is not None and bool(mask["teacher_next_in_candidate"]):
            item["teacher_next_candidate_rows"] += 1
        if mask is not None and bool(mask["teacher_next_in_safe_mask"]):
            item["teacher_next_safe_rows"] += 1
        recovered_set = recovered_by_key.get(key, set())
        item["recovered_by_oracle1"] += int("oracle1_teacher_next" in recovered_set)
        item["recovered_by_oracle2"] += int("oracle2_sipp_rank" in recovered_set)
        item["recovered_by_oracle3_k5"] += int("oracle3_lookahead_k5" in recovered_set)
        item["still_unrecovered_by_best_oracle"] += int((key[0], key[1], "oracle3_lookahead_k5") in unrecovered_by_key)
    return sorted(grouped.values(), key=lambda row: (-int(row["edge_score_failed_rows"]), str(row["feature_need"])))


def _feature_follow_up(need: str) -> str:
    return {
        "candidate_set_or_teacher_path_alignment": "Audit action-mask timing and teacher/current-node alignment before model work.",
        "mask_shield_timing": "Inspect shield block reasons and reservation timing; do not train around unsafe teacher labels.",
        "sipp_rank_supervision": "Proceed to G4 SIPP-rank teacher slices and EdgeRanker-v2 ranking losses.",
        "k_step_horizon_features": "Add K-step no-safe-action risk and future occupancy features.",
        "nonlocal_capacity_features": "Add merge/buffer pressure features and grouped capacity labels.",
        "fault_repair_features": "Add active fault/repair-window remaining-time features.",
        "event_horizon_or_global_guidance": "Add global guide or longer-horizon oracle diagnostics.",
        "missing_decision_audit": "Regenerate detailed replay traces for missing failed decisions.",
    }.get(need, "Continue G3b structural audit.")


def _build_decomposition_rows(unrecoverable_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: Counter[tuple[str, str, str, str]] = Counter()
    for row in unrecoverable_rows:
        grouped[
            (
                str(row["oracle_policy"]),
                str(row["scenario_context"]),
                str(row["failure_motif"]),
                str(row["unrecoverable_reason"]),
            )
        ] += 1
    return [
        {
            "oracle_policy": policy,
            "scenario_context": context,
            "failure_motif": motif,
            "unrecoverable_reason": reason,
            "failed_rows": count,
        }
        for (policy, context, motif, reason), count in sorted(grouped.items(), key=lambda item: (-item[1], item[0]))
    ]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])
    payload = b"\x89PNG\r\n\x1a\n"
    payload += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    payload += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    payload += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _write_heatmap(recovered_rows: list[dict[str, Any]]) -> str:
    policies = list(ORACLE_POLICIES)
    contexts = ["no_fault", "buffer_capacity", "static_fault", "repair_window", "merge_group"]
    counts = {(policy, context): 0 for policy in policies for context in contexts}
    for row in recovered_rows:
        key = (str(row["oracle_policy"]), str(row["scenario_context"]))
        if key in counts:
            counts[key] += 1
    max_count = max(counts.values()) if counts else 1
    try:
        from PIL import Image, ImageDraw, ImageFont  # pylint: disable=import-outside-toplevel
    except ImportError:
        cell = 30
        margin = 8
        width = margin * 2 + len(contexts) * cell
        height = margin * 2 + len(policies) * cell
        pixels = [(255, 255, 255) for _ in range(width * height)]
        for y_index, policy in enumerate(policies):
            for x_index, context in enumerate(contexts):
                value = counts[(policy, context)]
                intensity = 0 if max_count == 0 else int(220 * value / max_count)
                color = (238 - intensity // 3, 250 - intensity // 4, 255)
                x0 = margin + x_index * cell
                y0 = margin + y_index * cell
                for y in range(y0, y0 + cell - 2):
                    for x in range(x0, x0 + cell - 2):
                        pixels[y * width + x] = color
        _write_png(HEATMAP_PATH, width, height, pixels)
        return "generated with stdlib fallback; labels are in g3_oracle_recovered_failures.csv"

    cell_w = 150
    cell_h = 42
    left = 210
    top = 110
    width = left + len(contexts) * cell_w + 40
    height = top + len(policies) * cell_h + 55
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("arial.ttf", 18)
        font = ImageFont.truetype("arial.ttf", 12)
        small = ImageFont.truetype("arial.ttf", 10)
    except OSError:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    draw.text((24, 24), "G3 oracle recovered EdgeScore failures", fill="#111111", font=title_font)
    draw.text((24, 50), "Recovered rows by oracle policy and scenario context.", fill="#333333", font=font)
    for x_index, context in enumerate(contexts):
        draw.text((left + x_index * cell_w + 4, top - 34), context, fill="#111111", font=small)
    for y_index, policy in enumerate(policies):
        y = top + y_index * cell_h
        draw.text((24, y + 12), policy, fill="#111111", font=small)
        for x_index, context in enumerate(contexts):
            value = counts[(policy, context)]
            intensity = 0 if max_count == 0 else int(210 * value / max_count)
            fill = (235 - intensity // 3, 247 - intensity // 5, 255)
            x = left + x_index * cell_w
            draw.rectangle((x, y, x + cell_w - 4, y + cell_h - 4), fill=fill, outline="#dddddd")
            if value:
                draw.text((x + 8, y + 12), str(value), fill="#111111", font=font)
    HEATMAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(HEATMAP_PATH)
    return "generated"


def _teacher_recall(mask_rows: list[dict[str, Any]]) -> tuple[float, float, int]:
    first_rows = [row for row in mask_rows if bool(row["is_g2_first_divergence"])]
    if not first_rows:
        return 0.0, 0.0, 0
    candidate = sum(1 for row in first_rows if bool(row["teacher_next_in_candidate"]))
    safe = sum(1 for row in first_rows if bool(row["teacher_next_in_safe_mask"]))
    return candidate / len(first_rows), safe / len(first_rows), len(first_rows)


def _all_row(summary_rows: list[dict[str, Any]], policy: str) -> dict[str, Any]:
    for row in summary_rows:
        if row["scenario"] == "ALL" and row["policy"] == policy:
            return row
    raise KeyError(policy)


def _gate_interpretation(summary_rows: list[dict[str, Any]], teacher_safe_recall: float) -> tuple[str, str]:
    best = max((_all_row(summary_rows, policy) for policy in ORACLE_POLICIES), key=lambda row: float(row["recovery_rate_of_edge_score_failures"]))
    best_rate = float(best["recovery_rate_of_edge_score_failures"])
    if best_rate >= 0.70 and int(best["new_regressions_vs_edge_score"]) == 0 and int(best["post_shield_conflicts"]) == 0:
        return (
            "Development pass A: local oracle recovers the gap.",
            "Proceed to G4 SIPP teacher dataset expansion and EdgeRanker-v2 ranking supervision before any RL.",
        )
    if teacher_safe_recall < 0.70:
        return (
            "Development pass B: teacher next-hop is often unsafe under the current event replay mask.",
            "Prioritize G3b mask/shield/event-horizon audit before scaling model or dataset.",
        )
    return (
        "Development pass C: mixed recovery.",
        "Run G4 teacher dataset expansion for recoverable rank failures while auditing remaining horizon/nonlocal failures in G3b.",
    )


def _write_report(
    g2_recap: list[dict[str, str]],
    summary_rows: list[dict[str, Any]],
    teacher_mask_rows: list[dict[str, Any]],
    recovered_rows: list[dict[str, Any]],
    unrecovered_rows: list[dict[str, Any]],
    decomposition_rows: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    heatmap_status: str,
) -> None:
    candidate_recall, safe_recall, first_count = _teacher_recall(teacher_mask_rows)
    gate_title, gate_next = _gate_interpretation(summary_rows, safe_recall)
    g2_totals: dict[str, tuple[int, int]] = {}
    for row in g2_recap:
        if row.get("scope") != "matched_active_bag":
            continue
        family = str(row["family"])
        planned, total = g2_totals.get(family, (0, 0))
        g2_totals[family] = (planned + int(row["planned_count"]), total + int(row["max_tasks"]))

    lines = [
        "# G3 Oracle Upper Bound and Teacher-in-Mask Diagnosis",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This diagnostic keeps the current event policy candidate set and hard shield intact, then swaps only candidate scoring for SIPP teacher-next, SIPP-rank, and K-step lookahead oracles. It is an upper-bound/route-selection diagnostic, not model training and not an RL result.",
        "",
        f"- map: `{MAP_PATH.relative_to(ROOT).as_posix()}`",
        f"- tasks: `{TASK_PATH.relative_to(ROOT).as_posix()}`",
        f"- G2 failure source: `{G2_FAILED_TABLE.relative_to(ROOT).as_posix()}`",
        f"- heatmap: `{HEATMAP_PATH.relative_to(ROOT).as_posix()}` ({heatmap_status})",
        "",
        "## G2 Baseline Recap",
        "",
        "| Family | Planned / tasks |",
        "|---|---:|",
    ]
    for family in ("rolling_horizon_sipp", "periodic_replanning_sipp", "edge_score_event", "fallback_event", "pibt_active_bag_replay"):
        planned, total = g2_totals.get(family, (0, 0))
        lines.append(f"| `{family}` | `{planned}/{total}` |")
    lines.extend(
        [
            "",
            "## Teacher-Next-In-Mask Audit",
            "",
            f"- audited first-divergence rows: `{first_count}`",
            f"- teacher_next_candidate_recall: `{candidate_recall:.3f}`",
            f"- teacher_next_safe_recall: `{safe_recall:.3f}`",
            "",
            "## Oracle Recovery Summary",
            "",
            "| Oracle | Planned / 144 | Recovered EdgeScore failures | Remaining failures | New regressions | Conflicts | Recovery rate |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for policy in ORACLE_POLICIES:
        row = _all_row(summary_rows, policy)
        lines.append(
            "| `{policy}` | `{planned_count}/{max_tasks}` | {recovered_edge_score_failures} | {remaining_edge_score_failures} | {new_regressions_vs_edge_score} | {post_shield_conflicts} | {recovery_rate_of_edge_score_failures:.3f} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Unrecoverable Decomposition",
            "",
            "| Oracle | Context | Motif | Reason | Rows |",
            "|---|---|---|---|---:|",
        ]
    )
    for row in decomposition_rows[:15]:
        lines.append(
            "| `{oracle_policy}` | `{scenario_context}` | `{failure_motif}` | `{unrecoverable_reason}` | {failed_rows} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Feature Need Summary",
            "",
            "| Need | Failed rows | Teacher next safe | Oracle-1 recovered | Oracle-2 recovered | Oracle-3 K5 recovered | Still unrecovered by K5 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in feature_rows:
        lines.append(
            "| `{feature_need}` | {edge_score_failed_rows} | {teacher_next_safe_rows} | {recovered_by_oracle1} | {recovered_by_oracle2} | {recovered_by_oracle3_k5} | {still_unrecovered_by_best_oracle} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            gate_title,
            "",
            gate_next,
            "",
            "The key distinction is whether failures remain after the oracle has access to the same SIPP next-hop/rank signal that a supervised EdgeRanker would learn. Recovered rows are suitable for G4 teacher-slice expansion. Unrecovered rows need mask, event-horizon, or nonlocal-context audit before larger models or RL.",
            "",
            "## Artifacts",
            "",
            f"- Teacher-next-in-mask audit: `{TEACHER_MASK_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Oracle replay summary: `{ORACLE_SUMMARY_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Recovered failures: `{RECOVERED_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Unrecoverable failures: `{UNRECOVERABLE_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Failure decomposition: `{DECOMPOSITION_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Feature need summary: `{FEATURE_NEED_TABLE.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- Oracle-0 teacher-next-in-mask audit: PASS",
            "- Oracle-1 same-step SIPP next-hop replay: PASS",
            "- Oracle-2 SIPP-rank replay: PASS",
            "- Oracle-3 K-step lookahead replay/diagnostic for K=2/3/5: PASS",
            "- post-shield conflict accounting: PASS" if all(int(row["post_shield_conflicts"]) == 0 for row in summary_rows if row["scenario"] == "ALL") else "- post-shield conflict accounting: FAIL",
            "- model training / PPO / MAPPO: not started",
            "",
            "## Next Blocking Question",
            "",
            "For the rows still unrecovered by `oracle3_lookahead_k5`, is the blocker an event-horizon artifact in the local replay, or does it require nonlocal reservation guidance beyond what candidate ranking can express?",
            "",
            "## Follow-up",
            "",
            "- Build G4 SIPP teacher slices for rows marked `sipp_rank_supervision` and `k_step_horizon_features`.",
            "- Run G3b mask/event-horizon audit on rows marked `mask_shield_timing`, `candidate_set_or_teacher_path_alignment`, or still unrecovered by K5.",
            "- Keep all EdgeScore/BC/DAgger language at smoke/prototype level until a closed-loop policy beats fallback and approaches SIPP on heldout diagnostics.",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-error,import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))
    g2_failures = _load_g2_edge_failures()
    g2_recap = _load_g2_recap_rows()

    teacher_mask_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    recovered_rows: list[dict[str, Any]] = []
    unrecovered_rows: list[dict[str, Any]] = []

    for scenario in _case_plan():
        tasks = _selected_tasks(all_tasks, scenario)
        _, teacher_outcomes, teacher_paths, _ = _run_teacher(graph, tasks, scenario)
        edge_run = _run_detailed_event_replay(graph, tasks, scenario, "edge_score_event", runtime_model, teacher_paths)
        edge_outcomes = _outcomes_from_run(tasks, edge_run)
        teacher_mask_rows.extend(_build_teacher_mask_rows(scenario, tasks, edge_run, g2_failures))

        for policy in ORACLE_POLICIES:
            run = _run_detailed_event_replay(graph, tasks, scenario, policy, runtime_model, teacher_paths)
            oracle_outcomes = _outcomes_from_run(tasks, run)
            summary_rows.append(_summarize_oracle_rows(scenario, policy, run, edge_outcomes, oracle_outcomes, g2_failures))
            recovered, unrecovered = _build_recovery_tables(
                scenario,
                policy,
                edge_outcomes,
                oracle_outcomes,
                teacher_outcomes,
                g2_failures,
            )
            recovered_rows.extend(recovered)
            unrecovered_rows.extend(unrecovered)

    summary_rows = _aggregate_summary_rows(summary_rows)
    decomposition_rows = _build_decomposition_rows(unrecovered_rows)
    feature_rows = _build_feature_need_summary(teacher_mask_rows, recovered_rows, unrecovered_rows, g2_failures)
    heatmap_status = _write_heatmap(recovered_rows)

    _write_csv(TEACHER_MASK_TABLE, teacher_mask_rows)
    _write_csv(ORACLE_SUMMARY_TABLE, summary_rows)
    _write_csv(RECOVERED_TABLE, recovered_rows)
    _write_csv(UNRECOVERABLE_TABLE, unrecovered_rows)
    _write_csv(DECOMPOSITION_TABLE, decomposition_rows)
    _write_csv(FEATURE_NEED_TABLE, feature_rows)
    _write_report(
        g2_recap,
        summary_rows,
        teacher_mask_rows,
        recovered_rows,
        unrecovered_rows,
        decomposition_rows,
        feature_rows,
        heatmap_status,
    )

    candidate_recall, safe_recall, first_count = _teacher_recall(teacher_mask_rows)
    oracle1 = _all_row(summary_rows, "oracle1_teacher_next")
    if first_count != 47:
        raise AssertionError(f"expected 47 first-divergence audit rows, found {first_count}")
    if int(oracle1["edge_score_failed_rows_in_scenario"]) != 47:
        raise AssertionError("oracle summary did not cover the 47 EdgeScore failures")
    print(
        "g3_oracle_upper_bound "
        f"teacher_candidate_recall={candidate_recall:.3f} "
        f"teacher_safe_recall={safe_recall:.3f} "
        f"oracle1_recovered={oracle1['recovered_edge_score_failures']}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
