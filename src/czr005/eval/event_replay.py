"""Python reference event-queue replay for native scheduler parity checks."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Any, Iterable

from czr005.baselines.sipp import SIPPNode
from czr005.envs.action_mask import (
    ActionCandidate,
    EdgeFaultWindow,
    build_action_candidates,
)
from czr005.envs.observation_builder import build_junction_observation
from czr005.models.edge_score import featurize_slice
from czr005.sim_py.event_sim import EpisodeResult
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.metrics import compute_episode_metrics
from czr005.sim_py.reservation import EdgeReservationTable, NodeReservation, ReservationTable
from czr005.sim_py.task_stream import TaskLeg, TaskStream


@dataclass(frozen=True)
class EventReplayRun:
    result: EpisodeResult
    summary: dict[str, float | int]
    trace: list[dict[str, float | int | str | bool]]


@dataclass
class _EventTaskState:
    local_task_index: int
    task: TaskLeg
    route: list[SIPPNode]
    current: int
    ready_time: float
    waiting_time: float
    decision_count: int = 0
    closed: bool = False


def run_event_replay(
    graph: IcsGraph,
    tasks: TaskStream | Iterable[TaskLeg],
    runtime_model: Any | None = None,
    max_tasks: int | None = None,
    task_offset: int = 0,
    hold_seconds: float = 1.0,
    edge_capacity: int = 1,
    edge_headway_seconds: float = 0.0,
    fault_edges: set[tuple[int, int]] | None = None,
    fault_windows: tuple[EdgeFaultWindow, ...] | None = None,
    require_reachable_goal: bool = True,
    max_decisions_per_task: int = 128,
) -> EventReplayRun:
    """Replay active bags through a chronological event queue.

    When ``runtime_model`` is provided, it is called through the same
    ``predict(features, action_mask)`` surface used by the C++ pybind runtime.
    Passing ``None`` runs the C++-compatible shortest-safe fallback policy.
    """

    if hold_seconds <= 0.0:
        raise ValueError("hold_seconds must be positive")
    if edge_capacity <= 0:
        raise ValueError("edge_capacity must be positive")
    if task_offset < 0:
        raise ValueError("task_offset must be non-negative")
    if max_decisions_per_task <= 0:
        raise ValueError("max_decisions_per_task must be positive")

    selected = tuple(tasks) if isinstance(tasks, TaskStream) else tuple(TaskStream(tasks))
    start_index = min(task_offset, len(selected))
    limit = min(max_tasks if max_tasks is not None else len(selected), len(selected) - start_index)
    static_fault_edges = set(fault_edges or set())
    repair_windows = tuple(fault_windows or ())

    reservations = ReservationTable()
    edge_reservations = EdgeReservationTable()
    routes: dict[str, list[SIPPNode]] = {}
    unplanned: list[TaskLeg] = []
    events: list[dict[str, object]] = []
    task_by_segment: dict[str, TaskLeg] = {}
    trace: list[dict[str, float | int | str | bool]] = []
    shield_blocks = 0
    unsafe_proposals = 0

    event_queue: list[tuple[float, int, int, int, int]] = []
    sequence = 0
    for local_task_index in range(limit):
        task = selected[start_index + local_task_index]
        heapq.heappush(event_queue, (task.pass_time, sequence, 0, local_task_index, -1))
        sequence += 1

    states: list[_EventTaskState] = []

    while event_queue:
        _, _, event_kind, local_task_index, state_index = heapq.heappop(event_queue)

        if event_kind == 0:
            task = selected[start_index + local_task_index]
            task_by_segment[task.segment_id] = task
            start_duration = graph.service_time(task.start)
            start_time = _earliest_safe_node_start(
                reservations,
                task.start,
                task.pass_time,
                start_duration,
                task.task_id,
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
                _add_planned_event(
                    routes,
                    events,
                    task,
                    state.route,
                    state.decision_count,
                    state.waiting_time,
                )
            else:
                heapq.heappush(
                    event_queue,
                    (state.ready_time, sequence, 1, local_task_index, created_state_index),
                )
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
            fault_edges=static_fault_edges,
            fault_windows=repair_windows,
            hold_seconds=hold_seconds,
            require_reachable_goal=require_reachable_goal,
        )
        chosen_position, proposed_position, fallback_used = _choose_candidate(
            graph=graph,
            task=task,
            state=state,
            candidates=candidates,
            runtime_model=runtime_model,
            reservations=reservations,
            edge_reservations=edge_reservations,
            edge_capacity=edge_capacity,
            edge_headway_seconds=edge_headway_seconds,
            fault_edges=static_fault_edges,
            fault_windows=repair_windows,
            hold_seconds=hold_seconds,
            require_reachable_goal=require_reachable_goal,
        )

        state.decision_count += 1
        safe_candidate_count = sum(1 for candidate in candidates if candidate.safe)
        if chosen_position is None or chosen_position < 0 or chosen_position >= len(candidates):
            terminal_reason = (
                "no_safe_action"
                if chosen_position is None or chosen_position < 0
                else "invalid_action"
            )
            trace.append(
                _trace_row(
                    trace=trace,
                    state=state,
                    event="unplanned",
                    terminal_reason=terminal_reason,
                    proposed_position=proposed_position,
                    executed=None,
                    unsafe_proposal=False,
                    fallback_used=fallback_used,
                    candidates=candidates,
                    safe_candidate_count=safe_candidate_count,
                )
            )
            _mark_unplanned(
                unplanned,
                events,
                reservations,
                edge_reservations,
                task,
                state,
                terminal_reason,
                fallback_used,
            )
            state.closed = True
            continue

        chosen = candidates[chosen_position]
        unsafe_proposal = False
        if not chosen.safe:
            unsafe_proposals += 1
            unsafe_proposal = True
            chosen_position = _fallback_candidate_index(candidates, task.goal)
            fallback_used = True
            if chosen_position is None:
                trace.append(
                    _trace_row(
                        trace=trace,
                        state=state,
                        event="unplanned",
                        terminal_reason="unsafe_no_safe_fallback",
                        proposed_position=proposed_position,
                        executed=None,
                        unsafe_proposal=unsafe_proposal,
                        fallback_used=fallback_used,
                        candidates=candidates,
                        safe_candidate_count=safe_candidate_count,
                    )
                )
                _mark_unplanned(
                    unplanned,
                    events,
                    reservations,
                    edge_reservations,
                    task,
                    state,
                    "unsafe_no_safe_fallback",
                    True,
                )
                state.closed = True
                continue

        executed = candidates[chosen_position]
        if chosen_position != executed.index:
            shield_blocks += 1
        reached_goal = not executed.is_hold and executed.next_node == task.goal
        trace.append(
            _trace_row(
                trace=trace,
                state=state,
                event="step",
                terminal_reason="",
                proposed_position=proposed_position,
                executed=executed,
                unsafe_proposal=unsafe_proposal,
                fallback_used=fallback_used,
                candidates=candidates,
                safe_candidate_count=safe_candidate_count,
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
            edge_reservations.reserve(
                task.task_id,
                state.current,
                executed.next_node,
                executed.edge_start,
                executed.edge_end,
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

        if reached_goal:
            _add_planned_event(routes, events, task, state.route, state.decision_count, state.waiting_time)
            state.closed = True
            continue
        if state.decision_count >= max_decisions_per_task:
            _mark_unplanned(
                unplanned,
                events,
                reservations,
                edge_reservations,
                task,
                state,
                "max_decisions",
                False,
            )
            state.closed = True
            continue
        heapq.heappush(event_queue, (state.ready_time, sequence, 1, state.local_task_index, state_index))
        sequence += 1

    result = EpisodeResult(
        routes=routes,
        unplanned=unplanned,
        events=events,
        metrics=compute_episode_metrics(routes, task_by_segment, unplanned, reservations),
    )
    edge_conflicts = edge_reservations.conflict_count(
        capacity=edge_capacity,
        headway_seconds=edge_headway_seconds,
    )
    summary = {
        **result.metrics.to_dict(),
        "max_tasks": limit,
        "decision_count": len(trace),
        "shield_blocks": shield_blocks,
        "unsafe_proposals": unsafe_proposals,
        "edge_reservation_conflicts": edge_conflicts,
        "post_shield_conflicts": result.metrics.reservation_conflicts + edge_conflicts,
        "completed_events": len([event for event in events if event["event"] == "planned"]),
    }
    return EventReplayRun(result=result, summary=summary, trace=trace)


def _choose_candidate(
    graph: IcsGraph,
    task: TaskLeg,
    state: _EventTaskState,
    candidates: tuple[ActionCandidate, ...],
    runtime_model: Any | None,
    reservations: ReservationTable,
    edge_reservations: EdgeReservationTable,
    edge_capacity: int,
    edge_headway_seconds: float,
    fault_edges: set[tuple[int, int]],
    fault_windows: tuple[EdgeFaultWindow, ...],
    hold_seconds: float,
    require_reachable_goal: bool,
) -> tuple[int | None, int, bool]:
    if runtime_model is None:
        return _fallback_candidate_index(candidates, task.goal), -1, True
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
        selected_position = int(runtime_model.predict(features, mask))
    except (RuntimeError, ValueError):
        return _fallback_candidate_index(candidates, task.goal), -1, True
    return selected_position, selected_position, False


def _fallback_candidate_index(candidates: tuple[ActionCandidate, ...], goal: int) -> int | None:
    best: ActionCandidate | None = None
    best_rank: tuple[int, float, float] | None = None
    for candidate in candidates:
        if not candidate.safe or candidate.is_hold:
            continue
        rank = (
            0 if candidate.next_node == goal else 1,
            candidate.heuristic_to_goal,
            candidate.travel_time,
        )
        if best_rank is None or rank < best_rank:
            best = candidate
            best_rank = rank
    if best is not None:
        return best.index
    for candidate in candidates:
        if candidate.safe:
            return candidate.index
    return None


def _trace_row(
    trace: list[dict[str, float | int | str | bool]],
    state: _EventTaskState,
    event: str,
    terminal_reason: str,
    proposed_position: int,
    executed: ActionCandidate | None,
    unsafe_proposal: bool,
    fallback_used: bool,
    candidates: tuple[ActionCandidate, ...],
    safe_candidate_count: int,
    reached_goal: bool = False,
) -> dict[str, float | int | str | bool]:
    if executed is None:
        executed_index = -1
        executed_next = state.current
        executed_kind = "none"
        executed_safe = False
        route_size_after = len(state.route)
    else:
        executed_index = executed.index
        executed_next = executed.next_node
        executed_kind = executed.kind
        executed_safe = executed.safe
        route_size_after = len(state.route) + (0 if executed.is_hold else 1)
    return {
        "decision_ordinal": len(trace) + 1,
        "task_decision_ordinal": state.decision_count,
        "event": event,
        "terminal_reason": terminal_reason,
        "task_index": state.local_task_index,
        "segment_id": state.task.segment_id,
        "task_id": state.task.task_id,
        "current": state.current,
        "goal": state.task.goal,
        "ready_time": state.ready_time,
        "waiting_time": state.waiting_time,
        "proposed_position": proposed_position,
        "executed_index": executed_index,
        "executed_next": executed_next,
        "executed_kind": executed_kind,
        "executed_safe": executed_safe,
        "unsafe_proposal": unsafe_proposal,
        "fallback_used": fallback_used,
        "reached_goal": reached_goal,
        "candidate_count": len(candidates),
        "safe_candidate_count": safe_candidate_count,
        "route_size_after": route_size_after,
    }


def _add_planned_event(
    routes: dict[str, list[SIPPNode]],
    events: list[dict[str, object]],
    task: TaskLeg,
    route: list[SIPPNode],
    decision_count: int,
    waiting_time: float,
) -> None:
    routes[task.segment_id] = list(route)
    events.append(
        {
            "event": "planned",
            "baseline": "event_replay",
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


def _mark_unplanned(
    unplanned: list[TaskLeg],
    events: list[dict[str, object]],
    reservations: ReservationTable,
    edge_reservations: EdgeReservationTable,
    task: TaskLeg,
    state: _EventTaskState,
    reason: str,
    shield_blocked: bool,
) -> None:
    reservations.remove_task(task.task_id)
    edge_reservations.remove_task(task.task_id)
    unplanned.append(task)
    events.append(
        {
            "event": "unplanned",
            "baseline": "event_replay",
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


def _earliest_safe_node_start(
    reservations: ReservationTable,
    node: int,
    earliest_start: float,
    duration: float,
    task_id: int,
) -> float:
    candidate = earliest_start
    for interval in sorted(
        reservations.intervals(node),
        key=lambda item: (item.start, item.end, item.task_id),
    ):
        if interval.task_id == task_id:
            continue
        if _node_interval_safe(interval, candidate, candidate + duration):
            continue
        candidate = interval.end + 1e-9
    return candidate


def _node_interval_safe(interval: NodeReservation, start: float, end: float) -> bool:
    return start > interval.end or end < interval.start
