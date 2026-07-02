"""Action candidate construction and hard safety masks for junction decisions."""

from __future__ import annotations

from dataclasses import dataclass

from czr005.sim_py.astar import AStarPlanner
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable
from czr005.sim_py.task_stream import TaskLeg

EdgeFaultWindow = tuple[int, int, float, float]


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


def active_fault_edges(
    fault_edges: set[tuple[int, int]] | None = None,
    fault_windows: tuple[EdgeFaultWindow, ...] | None = None,
    ready_time: float = 0.0,
) -> set[tuple[int, int]]:
    active = set(fault_edges or set())
    for start, end, fault_start, repair_time in fault_windows or ():
        if repair_time <= fault_start:
            raise ValueError("repair_time must be greater than fault_start")
        if fault_start <= ready_time < repair_time:
            active.add((start, end))
    return active


def build_action_candidates(
    graph: IcsGraph,
    task: TaskLeg,
    current: int,
    ready_time: float,
    reservations: ReservationTable,
    edge_reservations: EdgeReservationTable,
    edge_capacity: int = 1,
    edge_headway_seconds: float = 0.0,
    node_capacities: dict[int, int] | None = None,
    merge_groups: dict[tuple[int, int], int] | None = None,
    merge_capacity: int = 1,
    merge_headway_seconds: float = 0.0,
    fault_edges: set[tuple[int, int]] | None = None,
    fault_windows: tuple[EdgeFaultWindow, ...] | None = None,
    hold_seconds: float = 1.0,
    require_reachable_goal: bool = True,
) -> tuple[ActionCandidate, ...]:
    if edge_capacity <= 0:
        raise ValueError("edge_capacity must be positive")
    if merge_capacity <= 0:
        raise ValueError("merge_capacity must be positive")
    if hold_seconds <= 0.0:
        raise ValueError("hold_seconds must be positive")

    node_capacities = node_capacities or {}
    merge_groups = merge_groups or {}
    active_faults = active_fault_edges(fault_edges, fault_windows, ready_time)
    reachability_faults = _reachability_fault_edges(fault_edges, fault_windows, ready_time)
    planner = AStarPlanner(graph) if require_reachable_goal else None
    candidates: list[ActionCandidate] = []

    for index, next_node in enumerate(graph.outgoing(current)):
        edge = graph.edge(current, next_node)
        edge_start = ready_time
        edge_end = edge_start + edge.travel_time
        node_start = edge_end
        service_time = graph.service_time(next_node)
        node_end = node_start + service_time
        reasons: list[str] = []

        if (current, next_node) in active_faults:
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
        if _has_merge_group_conflict(
            edge_reservations=edge_reservations,
            start_node=current,
            end_node=next_node,
            start=edge_start,
            end=edge_end,
            merge_groups=merge_groups,
            merge_capacity=merge_capacity,
            merge_headway_seconds=merge_headway_seconds,
            task_id=task.task_id,
        ):
            reasons.append("merge_group")
        node_capacity = node_capacities.get(next_node, 1)
        if reservations.has_capacity_conflict(
            next_node,
            node_start,
            node_end,
            capacity=node_capacity,
            task_id=task.task_id,
        ):
            reasons.append("node_reservation")
        if (
            planner is not None
            and next_node != task.goal
            and not planner.plan(next_node, task.goal, fault_edges=reachability_faults)
        ):
            reasons.append("unreachable_goal")

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
    hold_capacity = node_capacities.get(current, 1)
    if reservations.has_capacity_conflict(
        current,
        hold_start,
        hold_end,
        capacity=hold_capacity,
        task_id=task.task_id,
    ):
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


def _has_merge_group_conflict(
    edge_reservations: EdgeReservationTable,
    start_node: int,
    end_node: int,
    start: float,
    end: float,
    merge_groups: dict[tuple[int, int], int],
    merge_capacity: int,
    merge_headway_seconds: float,
    task_id: int,
) -> bool:
    group = merge_groups.get((start_node, end_node))
    if group is None:
        return False
    overlapping = 0
    for interval in edge_reservations.all_intervals():
        if interval.task_id == task_id:
            continue
        if merge_groups.get((interval.start_node, interval.end_node)) != group:
            continue
        if interval.overlaps(start, end):
            overlapping += 1
        if merge_headway_seconds > 0.0 and abs(start - interval.start) < merge_headway_seconds:
            return True
    return overlapping >= merge_capacity


def _reachability_fault_edges(
    fault_edges: set[tuple[int, int]] | None,
    fault_windows: tuple[EdgeFaultWindow, ...] | None,
    _ready_time: float,
) -> set[tuple[int, int]]:
    """Faults used only for downstream reachability pruning.

    A currently failed repair-window edge should still block immediate travel
    through that edge, but it should not make an upstream node look permanently
    unreachable. Keeping permanent faults here while dropping future-repair
    windows lets event policies move toward safe waiting nodes instead of
    forcing premature no-path labels.
    """

    permanent = set(fault_edges or set())
    for _, _, fault_start, repair_time in fault_windows or ():
        if repair_time <= fault_start:
            raise ValueError("repair_time must be greater than fault_start")
    return permanent


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
