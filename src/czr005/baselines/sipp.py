"""Safe-interval path planning baseline for the Python reference graph."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from itertools import count

from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable


EPSILON = 1e-9


@dataclass
class SIPPNode:
    location: int
    t1: float
    t2: float
    gcost: float
    hcost: float
    fcost: float
    parent: "SIPPNode | None" = None

    def to_dict(self) -> dict[str, float | int]:
        return {
            "location": self.location,
            "t1": self.t1,
            "t2": self.t2,
            "gcost": self.gcost,
            "hcost": self.hcost,
            "fcost": self.fcost,
        }


class SIPPPlanner:
    """Minimal SIPP-style planner that waits for safe target-node intervals.

    This first Phase2 baseline keeps the same directed graph and node service
    semantics as the Python A* reference. It can wait before traversing an edge
    so that arrival at the target node lands in the next reservation-free
    interval. Edge reservations and buffer/merge rules are intentionally left
    for later Phase2 work.
    """

    def __init__(self, graph: IcsGraph, max_time: float = 86_400.0) -> None:
        self.graph = graph
        self.max_time = max_time

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
        if merge_capacity <= 0:
            raise ValueError("merge_capacity must be positive")
        reservations = reservations or ReservationTable()
        edge_reservations = edge_reservations or EdgeReservationTable()
        node_capacities = node_capacities or {}
        merge_groups = merge_groups or {}
        fault_edges = fault_edges or set()
        sequence = count()
        open_heap: list[tuple[float, int, SIPPNode]] = []
        start_node = SIPPNode(
            location=start,
            t1=start_time,
            t2=start_time + self.graph.service_time(start),
            gcost=start_time,
            hcost=self.graph.heuristic(start, goal),
            fcost=start_time + self.graph.heuristic(start, goal),
        )
        heapq.heappush(open_heap, (start_node.fcost, next(sequence), start_node))
        best_t2: dict[int, float] = {start: start_node.t2}

        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            if current.t2 > best_t2.get(current.location, float("inf")) + EPSILON:
                continue
            if current.location == goal:
                return self._reconstruct(current)

            for next_location in self.graph.outgoing(current.location):
                if (current.location, next_location) in fault_edges:
                    continue
                edge = self.graph.edge(current.location, next_location)
                service_time = self.graph.service_time(next_location)
                transition = self._earliest_safe_transition(
                    current=current,
                    next_location=next_location,
                    goal=goal,
                    travel_time=edge.travel_time,
                    service_time=service_time,
                    reservations=reservations,
                    edge_reservations=edge_reservations,
                    edge_capacity=edge_capacity,
                    edge_headway_seconds=edge_headway_seconds,
                    node_capacities=node_capacities,
                    merge_groups=merge_groups,
                    merge_capacity=merge_capacity,
                    merge_headway_seconds=merge_headway_seconds,
                    task_id=task_id,
                )
                if transition is None:
                    continue
                edge_start, node_start = transition

                node_end = node_start + service_time
                if node_end >= best_t2.get(next_location, float("inf")) - EPSILON:
                    continue
                hcost = self.graph.heuristic(next_location, goal)
                child = SIPPNode(
                    location=next_location,
                    t1=node_start,
                    t2=node_end,
                    gcost=node_start,
                    hcost=hcost,
                    fcost=node_start + hcost,
                    parent=current,
                )
                best_t2[next_location] = node_end
                heapq.heappush(open_heap, (child.fcost, next(sequence), child))

        return []

    def _earliest_safe_transition(
        self,
        current: SIPPNode,
        next_location: int,
        goal: int,
        travel_time: float,
        service_time: float,
        reservations: ReservationTable,
        edge_reservations: EdgeReservationTable,
        edge_capacity: int,
        edge_headway_seconds: float,
        node_capacities: dict[int, int],
        merge_groups: dict[tuple[int, int], int],
        merge_capacity: int,
        merge_headway_seconds: float,
        task_id: int | None,
    ) -> tuple[float, float] | None:
        edge_start = current.t2
        attempts = (
            len(edge_reservations.intervals(current.location, next_location))
            + len(edge_reservations.all_intervals())
        ) * 3 + 8
        for _ in range(attempts):
            edge_start = edge_reservations.earliest_start(
                current.location,
                next_location,
                edge_start,
                travel_time,
                edge_capacity,
                edge_headway_seconds,
                task_id,
            )
            edge_start = edge_reservations.earliest_merge_group_start(
                current.location,
                next_location,
                edge_start,
                travel_time,
                merge_groups,
                merge_capacity,
                merge_headway_seconds,
                task_id,
            )
            node_start = edge_start + travel_time
            if next_location != goal:
                safe_node_start = self._earliest_safe_node_start(
                    reservations,
                    next_location,
                    node_start,
                    service_time,
                    node_capacities.get(next_location, 1),
                    task_id,
                )
                if safe_node_start is None:
                    return None
                if safe_node_start > node_start + EPSILON:
                    edge_start = safe_node_start - travel_time
                    continue
                node_start = safe_node_start
            if node_start <= self.max_time:
                return edge_start, node_start
            return None
        return None

    def _earliest_safe_node_start(
        self,
        reservations: ReservationTable,
        node: int,
        earliest_start: float,
        duration: float,
        capacity: int,
        task_id: int | None,
    ) -> float | None:
        if capacity <= 0:
            return None
        candidate = earliest_start
        intervals = tuple(sorted(reservations.intervals(node), key=lambda item: (item.start, item.end, item.task_id)))
        for _ in range(len(intervals) * 2 + 2):
            candidate_end = candidate + duration
            if not reservations.has_capacity_conflict(node, candidate, candidate_end, capacity, task_id):
                return candidate if candidate <= self.max_time else None

            overlapping = [
                interval
                for interval in intervals
                if (task_id is None or interval.task_id != task_id) and interval.overlaps(candidate, candidate_end)
            ]
            if not overlapping:
                return None
            candidate = min(interval.end for interval in overlapping) + EPSILON
            if candidate > self.max_time:
                return None

        return None

    @staticmethod
    def _reconstruct(goal_node: SIPPNode) -> list[SIPPNode]:
        route: list[SIPPNode] = []
        current: SIPPNode | None = goal_node
        while current is not None:
            route.append(current)
            current = current.parent
        route.reverse()
        return route
