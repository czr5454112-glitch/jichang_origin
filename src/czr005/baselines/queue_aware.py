"""Queue-aware shortest-path baseline for Phase2."""

from __future__ import annotations

from dataclasses import dataclass

from czr005.baselines.sipp import SIPPPlanner, SIPPNode
from czr005.envs.action_mask import (
    ActionCandidate,
    EdgeFaultWindow,
    build_action_candidates,
)
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable
from czr005.sim_py.task_stream import TaskLeg


EPSILON = 1.0e-9


@dataclass(frozen=True)
class QueueAwareRoute:
    route: tuple[SIPPNode, ...]
    score: float
    finish_time: float
    queue_penalty: float

    @property
    def path(self) -> tuple[int, ...]:
        return tuple(node.location for node in self.route)


@dataclass(frozen=True)
class QueueAwareDecision:
    candidate: ActionCandidate
    score: float
    queue_penalty: float


class QueueAwareShortestPath:
    """Non-learning shortest-path baseline with local queue pressure.

    The baseline keeps the Phase2 hard-safety surface unchanged: feasible routes
    are produced by SIPP and one-step decisions are built from shielded action
    candidates. Queue pressure is only a tie-break/penalty over already-safe
    candidates, so it cannot authorize a conflict.
    """

    def __init__(
        self,
        graph: IcsGraph,
        queue_weight: float = 1.0,
        edge_queue_weight: float = 1.0,
        lookahead_seconds: float = 300.0,
        hold_seconds: float = 1.0,
    ) -> None:
        if queue_weight < 0.0:
            raise ValueError("queue_weight must be non-negative")
        if edge_queue_weight < 0.0:
            raise ValueError("edge_queue_weight must be non-negative")
        if lookahead_seconds <= 0.0:
            raise ValueError("lookahead_seconds must be positive")
        if hold_seconds <= 0.0:
            raise ValueError("hold_seconds must be positive")
        self.graph = graph
        self.queue_weight = queue_weight
        self.edge_queue_weight = edge_queue_weight
        self.lookahead_seconds = lookahead_seconds
        self.hold_seconds = hold_seconds
        self.planner = SIPPPlanner(graph)

    def plan(
        self,
        start: int,
        goal: int,
        start_time: float = 0.0,
        reservations: ReservationTable | None = None,
        edge_reservations: EdgeReservationTable | None = None,
        edge_capacity: int = 1,
        edge_headway_seconds: float = 0.0,
        node_capacities: dict[int, int] | None = None,
        merge_groups: dict[tuple[int, int], int] | None = None,
        merge_capacity: int = 1,
        merge_headway_seconds: float = 0.0,
        fault_edges: set[tuple[int, int]] | None = None,
        task_id: int | None = None,
    ) -> list[SIPPNode]:
        routes = self.ranked_routes(
            start=start,
            goal=goal,
            start_time=start_time,
            reservations=reservations,
            edge_reservations=edge_reservations,
            edge_capacity=edge_capacity,
            edge_headway_seconds=edge_headway_seconds,
            node_capacities=node_capacities,
            merge_groups=merge_groups,
            merge_capacity=merge_capacity,
            merge_headway_seconds=merge_headway_seconds,
            fault_edges=fault_edges,
            task_id=task_id,
        )
        return list(routes[0].route) if routes else []

    def ranked_routes(
        self,
        start: int,
        goal: int,
        start_time: float = 0.0,
        reservations: ReservationTable | None = None,
        edge_reservations: EdgeReservationTable | None = None,
        edge_capacity: int = 1,
        edge_headway_seconds: float = 0.0,
        node_capacities: dict[int, int] | None = None,
        merge_groups: dict[tuple[int, int], int] | None = None,
        merge_capacity: int = 1,
        merge_headway_seconds: float = 0.0,
        fault_edges: set[tuple[int, int]] | None = None,
        task_id: int | None = None,
    ) -> tuple[QueueAwareRoute, ...]:
        reservations = reservations or ReservationTable()
        edge_reservations = edge_reservations or EdgeReservationTable()
        node_capacities = node_capacities or {}
        merge_groups = merge_groups or {}
        base_faults = set(fault_edges or set())

        if start == goal:
            route = self.planner.plan(
                start=start,
                goal=goal,
                start_time=start_time,
                reservations=reservations,
                edge_reservations=edge_reservations,
                edge_capacity=edge_capacity,
                edge_headway_seconds=edge_headway_seconds,
                node_capacities=node_capacities,
                merge_groups=merge_groups,
                merge_capacity=merge_capacity,
                merge_headway_seconds=merge_headway_seconds,
                fault_edges=base_faults,
                task_id=task_id,
            )
            return (
                QueueAwareRoute(
                    route=tuple(route),
                    score=route[-1].t2 if route else float("inf"),
                    finish_time=route[-1].t2 if route else float("inf"),
                    queue_penalty=0.0,
                ),
            ) if route else ()

        ranked: list[QueueAwareRoute] = []
        outgoing = tuple(self.graph.outgoing(start))
        for first_hop in outgoing:
            if (start, first_hop) in base_faults:
                continue
            forced_faults = base_faults | {
                (start, other) for other in outgoing if other != first_hop
            }
            route = self.planner.plan(
                start=start,
                goal=goal,
                start_time=start_time,
                reservations=reservations,
                edge_reservations=edge_reservations,
                edge_capacity=edge_capacity,
                edge_headway_seconds=edge_headway_seconds,
                node_capacities=node_capacities,
                merge_groups=merge_groups,
                merge_capacity=merge_capacity,
                merge_headway_seconds=merge_headway_seconds,
                fault_edges=forced_faults,
                task_id=task_id,
            )
            if len(route) < 2 or route[1].location != first_hop:
                continue
            queue_penalty = self._route_queue_penalty(
                route=route,
                reservations=reservations,
                edge_reservations=edge_reservations,
                node_capacities=node_capacities,
                merge_groups=merge_groups,
                task_id=task_id,
            )
            finish_time = route[-1].t2
            ranked.append(
                QueueAwareRoute(
                    route=tuple(route),
                    score=finish_time + queue_penalty,
                    finish_time=finish_time,
                    queue_penalty=queue_penalty,
                )
            )

        ranked.sort(key=lambda item: (item.score, item.finish_time, item.path))
        return tuple(ranked)

    def choose_action(
        self,
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
        require_reachable_goal: bool = True,
    ) -> ActionCandidate | None:
        decision = self.rank_actions(
            task=task,
            current=current,
            ready_time=ready_time,
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
            require_reachable_goal=require_reachable_goal,
        )
        return decision[0].candidate if decision else None

    def rank_actions(
        self,
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
        require_reachable_goal: bool = True,
    ) -> tuple[QueueAwareDecision, ...]:
        node_capacities = node_capacities or {}
        merge_groups = merge_groups or {}
        candidates = build_action_candidates(
            graph=self.graph,
            task=task,
            current=current,
            ready_time=ready_time,
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
            hold_seconds=self.hold_seconds,
            require_reachable_goal=require_reachable_goal,
        )
        ranked: list[QueueAwareDecision] = []
        for candidate in candidates:
            if not candidate.safe:
                continue
            queue_penalty = self._candidate_queue_penalty(
                candidate=candidate,
                reservations=reservations,
                edge_reservations=edge_reservations,
                node_capacities=node_capacities,
                merge_groups=merge_groups,
                task_id=task.task_id,
            )
            if candidate.is_hold:
                base_score = candidate.node_end + self.graph.heuristic(current, task.goal)
            else:
                base_score = candidate.node_end + candidate.heuristic_to_goal
            ranked.append(
                QueueAwareDecision(
                    candidate=candidate,
                    score=base_score + queue_penalty,
                    queue_penalty=queue_penalty,
                )
            )
        ranked.sort(
            key=lambda item: (
                item.score,
                item.candidate.is_hold,
                item.candidate.heuristic_to_goal,
                item.candidate.travel_time,
                item.candidate.index,
            )
        )
        return tuple(ranked)

    def _route_queue_penalty(
        self,
        route: list[SIPPNode],
        reservations: ReservationTable,
        edge_reservations: EdgeReservationTable,
        node_capacities: dict[int, int],
        merge_groups: dict[tuple[int, int], int],
        task_id: int | None,
    ) -> float:
        node_penalty = sum(
            self._node_queue_pressure(
                node=node.location,
                start=node.t1,
                reservations=reservations,
                capacity=node_capacities.get(node.location, 1),
                task_id=task_id,
            )
            for node in route[1:]
        )
        edge_penalty = 0.0
        for left, right in zip(route, route[1:]):
            if left.location == right.location:
                continue
            edge = self.graph.edge(left.location, right.location)
            edge_start = right.t1 - edge.travel_time
            edge_penalty += self._edge_queue_pressure(
                start_node=left.location,
                end_node=right.location,
                start=edge_start,
                edge_reservations=edge_reservations,
                merge_groups=merge_groups,
                task_id=task_id,
            )
        return self.queue_weight * node_penalty + self.edge_queue_weight * edge_penalty

    def _candidate_queue_penalty(
        self,
        candidate: ActionCandidate,
        reservations: ReservationTable,
        edge_reservations: EdgeReservationTable,
        node_capacities: dict[int, int],
        merge_groups: dict[tuple[int, int], int],
        task_id: int,
    ) -> float:
        node_penalty = self._node_queue_pressure(
            node=candidate.next_node,
            start=candidate.node_start,
            reservations=reservations,
            capacity=node_capacities.get(candidate.next_node, 1),
            task_id=task_id,
        )
        edge_penalty = 0.0
        if not candidate.is_hold:
            edge_penalty = self._edge_queue_pressure(
                start_node=candidate.current,
                end_node=candidate.next_node,
                start=candidate.edge_start,
                edge_reservations=edge_reservations,
                merge_groups=merge_groups,
                task_id=task_id,
            )
        return self.queue_weight * node_penalty + self.edge_queue_weight * edge_penalty

    def _node_queue_pressure(
        self,
        node: int,
        start: float,
        reservations: ReservationTable,
        capacity: int,
        task_id: int | None,
    ) -> float:
        if capacity <= 0:
            return float("inf")
        window_end = start + self.lookahead_seconds
        pressure = 0.0
        for interval in reservations.intervals(node):
            if task_id is not None and interval.task_id == task_id:
                continue
            if interval.end <= start + EPSILON or interval.start >= window_end - EPSILON:
                continue
            pressure += self._time_decay(max(interval.start, start), start) / capacity
        return pressure

    def _edge_queue_pressure(
        self,
        start_node: int,
        end_node: int,
        start: float,
        edge_reservations: EdgeReservationTable,
        merge_groups: dict[tuple[int, int], int],
        task_id: int | None,
    ) -> float:
        window_end = start + self.lookahead_seconds
        pressure = 0.0
        for interval in edge_reservations.intervals(start_node, end_node):
            if task_id is not None and interval.task_id == task_id:
                continue
            if interval.end <= start + EPSILON or interval.start >= window_end - EPSILON:
                continue
            pressure += self._time_decay(max(interval.start, start), start)

        group = merge_groups.get((start_node, end_node))
        if group is None:
            return pressure
        for interval in edge_reservations.all_intervals():
            if interval.start_node == start_node and interval.end_node == end_node:
                continue
            if task_id is not None and interval.task_id == task_id:
                continue
            if merge_groups.get((interval.start_node, interval.end_node)) != group:
                continue
            if interval.end <= start + EPSILON or interval.start >= window_end - EPSILON:
                continue
            pressure += self._time_decay(max(interval.start, start), start)
        return pressure

    def _time_decay(self, interval_start: float, reference: float) -> float:
        distance = max(0.0, interval_start - reference)
        return max(0.0, 1.0 - distance / self.lookahead_seconds)
