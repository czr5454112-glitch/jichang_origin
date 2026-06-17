"""Action candidate construction and hard safety masks for junction decisions."""

from __future__ import annotations

from dataclasses import dataclass

from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable
from czr005.sim_py.task_stream import TaskLeg


@dataclass(frozen=True)
class ActionCandidate:
    index: int
    kind: str
    current: int
    next_node: int
    edge_start: float
    edge_end: float
    node_start: float
    node_end: float
    travel_time: float
    service_time: float
    heuristic_to_goal: float
    safe: bool
    blocked_reasons: tuple[str, ...] = ()

    @property
    def is_hold(self) -> bool:
        return self.kind == "hold"

    def to_dict(self) -> dict[str, float | int | str | bool | list[str]]:
        return {
            "index": self.index,
            "kind": self.kind,
            "current": self.current,
            "next_node": self.next_node,
            "edge_start": self.edge_start,
            "edge_end": self.edge_end,
            "node_start": self.node_start,
            "node_end": self.node_end,
            "travel_time": self.travel_time,
            "service_time": self.service_time,
            "heuristic_to_goal": self.heuristic_to_goal,
            "safe": self.safe,
            "blocked_reasons": list(self.blocked_reasons),
        }


def build_action_candidates(
    graph: IcsGraph,
    task: TaskLeg,
    current: int,
    ready_time: float,
    reservations: ReservationTable,
    edge_reservations: EdgeReservationTable,
    edge_capacity: int = 1,
    edge_headway_seconds: float = 0.0,
    fault_edges: set[tuple[int, int]] | None = None,
    hold_seconds: float = 1.0,
) -> tuple[ActionCandidate, ...]:
    if edge_capacity <= 0:
        raise ValueError("edge_capacity must be positive")
    if hold_seconds <= 0.0:
        raise ValueError("hold_seconds must be positive")

    fault_edges = fault_edges or set()
    candidates: list[ActionCandidate] = []

    for index, next_node in enumerate(graph.outgoing(current)):
        edge = graph.edge(current, next_node)
        edge_start = ready_time
        edge_end = edge_start + edge.travel_time
        node_start = edge_end
        service_time = graph.service_time(next_node)
        node_end = node_start + service_time
        reasons: list[str] = []

        if (current, next_node) in fault_edges:
            reasons.append("fault_edge")
        if edge_reservations.has_capacity_conflict(
            current,
            next_node,
            edge_start,
            edge_end,
            edge_capacity,
            task_id=task.task_id,
        ):
            reasons.append("edge_capacity")
        if edge_reservations.has_headway_conflict(
            current,
            next_node,
            edge_start,
            edge_headway_seconds,
            task_id=task.task_id,
        ):
            reasons.append("edge_headway")
        if reservations.has_conflict(next_node, node_start, node_end, task_id=task.task_id):
            reasons.append("node_reservation")

        candidates.append(
            ActionCandidate(
                index=index,
                kind="move",
                current=current,
                next_node=next_node,
                edge_start=edge_start,
                edge_end=edge_end,
                node_start=node_start,
                node_end=node_end,
                travel_time=edge.travel_time,
                service_time=service_time,
                heuristic_to_goal=graph.heuristic(next_node, task.goal),
                safe=not reasons,
                blocked_reasons=tuple(reasons),
            )
        )

    hold_index = len(candidates)
    hold_start = ready_time
    hold_end = hold_start + hold_seconds
    hold_reasons: list[str] = []
    if reservations.has_conflict(current, hold_start, hold_end, task_id=task.task_id):
        hold_reasons.append("node_reservation")
    candidates.append(
        ActionCandidate(
            index=hold_index,
            kind="hold",
            current=current,
            next_node=current,
            edge_start=hold_start,
            edge_end=hold_start,
            node_start=hold_start,
            node_end=hold_end,
            travel_time=0.0,
            service_time=hold_seconds,
            heuristic_to_goal=graph.heuristic(current, task.goal),
            safe=not hold_reasons,
            blocked_reasons=tuple(hold_reasons),
        )
    )

    return tuple(candidates)


def action_mask(candidates: tuple[ActionCandidate, ...]) -> tuple[bool, ...]:
    return tuple(candidate.safe for candidate in candidates)


def shortest_safe_action(candidates: tuple[ActionCandidate, ...], goal: int | None = None) -> int | None:
    safe_moves = [candidate for candidate in candidates if candidate.safe and not candidate.is_hold]
    if goal is not None:
        goal_moves = [candidate for candidate in safe_moves if candidate.next_node == goal]
        if goal_moves:
            return min(goal_moves, key=lambda candidate: (candidate.travel_time, candidate.index)).index
    if safe_moves:
        chosen = min(
            safe_moves,
            key=lambda candidate: (
                candidate.heuristic_to_goal,
                candidate.travel_time,
                candidate.next_node,
            ),
        )
        return chosen.index
    for candidate in candidates:
        if candidate.safe:
            return candidate.index
    return None
