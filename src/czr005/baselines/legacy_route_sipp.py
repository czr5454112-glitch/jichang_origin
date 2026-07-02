"""Legacy-A* route intent with SIPP-style execution timing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from czr005.baselines.sipp import EPSILON, SIPPNode
from czr005.envs.action_mask import EdgeFaultWindow, active_fault_edges
from czr005.sim_py.astar import AStarPlanner
from czr005.sim_py.event_sim import EpisodeResult
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.metrics import compute_episode_metrics
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable
from czr005.sim_py.task_stream import TaskLeg, TaskStream


@dataclass(frozen=True)
class LegacyRouteSIPPStats:
    planned_count: int
    unplanned_count: int
    legacy_path_match_count: int
    legacy_path_mismatch_count: int
    inserted_wait_count: int
    edge_conflicts: int
    merge_conflicts: int


class LegacyRouteSIPPPlanner:
    """Retimes the existing Legacy/CIE A* path with SIPP-style reservations.

    The planner deliberately separates route intent from execution timing:

    - Legacy/CIE A* chooses the path.
    - This wrapper keeps that path fixed and only moves timestamps later when
      node, edge, or merge reservations require waiting.
    """

    def __init__(self, graph: IcsGraph, max_time: float = 86_400.0) -> None:
        self.graph = graph
        self.max_time = max_time
        self.astar = AStarPlanner(graph)

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
        legacy_path: Iterable[int] | None = None,
    ) -> list[SIPPNode]:
        if edge_capacity <= 0:
            raise ValueError("edge_capacity must be positive")
        if merge_capacity <= 0:
            raise ValueError("merge_capacity must be positive")
        reservations = reservations or ReservationTable()
        edge_reservations = edge_reservations or EdgeReservationTable()
        node_capacities = node_capacities or {}
        merge_groups = merge_groups or {}
        fault_edges = fault_edges or set()

        path = tuple(int(node) for node in legacy_path) if legacy_path is not None else self._legacy_path(
            start=start,
            goal=goal,
            start_time=start_time,
            reservations=reservations,
            fault_edges=fault_edges,
            task_id=task_id,
        )
        if not self._valid_path(path, start, goal, fault_edges):
            return []

        start_duration = self.graph.service_time(start)
        safe_start = self._earliest_safe_node_start(
            reservations,
            start,
            start_time,
            start_duration,
            node_capacities.get(start, 1),
            task_id,
        )
        if safe_start is None:
            return []
        route = [
            SIPPNode(
                location=start,
                t1=safe_start,
                t2=safe_start + start_duration,
                gcost=safe_start,
                hcost=self.graph.heuristic(start, goal),
                fcost=safe_start + self.graph.heuristic(start, goal),
                parent=None,
            )
        ]
        for next_location in path[1:]:
            transition = self._earliest_transition_on_path(
                current=route[-1],
                next_location=next_location,
                goal=goal,
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
                return []
            edge_start, node_start = transition
            if edge_start > self.max_time or node_start > self.max_time:
                return []
            service_time = self.graph.service_time(next_location)
            hcost = self.graph.heuristic(next_location, goal)
            route.append(
                SIPPNode(
                    location=next_location,
                    t1=node_start,
                    t2=node_start + service_time,
                    gcost=node_start,
                    hcost=hcost,
                    fcost=node_start + hcost,
                    parent=route[-1],
                )
            )
        return route

    def _legacy_path(
        self,
        start: int,
        goal: int,
        start_time: float,
        reservations: ReservationTable,
        fault_edges: set[tuple[int, int]],
        task_id: int | None,
    ) -> tuple[int, ...]:
        route = self.astar.plan(
            start=start,
            goal=goal,
            start_time=start_time,
            reservations=reservations,
            fault_edges=fault_edges,
            task_id=task_id,
        )
        return tuple(int(node.location) for node in route)

    def _valid_path(
        self,
        path: tuple[int, ...],
        start: int,
        goal: int,
        fault_edges: set[tuple[int, int]],
    ) -> bool:
        if not path or path[0] != start or path[-1] != goal:
            return False
        for left, right in zip(path, path[1:]):
            if (left, right) in fault_edges or not self.graph.has_edge(left, right):
                return False
        return True

    def _earliest_transition_on_path(
        self,
        current: SIPPNode,
        next_location: int,
        goal: int,
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
        edge = self.graph.edge(current.location, next_location)
        travel_time = edge.travel_time
        service_time = self.graph.service_time(next_location)
        edge_start = current.t2
        attempts = (
            len(edge_reservations.intervals(current.location, next_location))
            + len(edge_reservations.all_intervals())
            + len(reservations.intervals(next_location))
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
            return edge_start, node_start
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
                if interval.task_id != task_id and interval.overlaps(candidate, candidate_end)
            ]
            if not overlapping:
                return candidate if candidate <= self.max_time else None
            candidate = min(interval.end for interval in overlapping) + EPSILON
        return None


class LegacyRouteSIPPBaseline:
    """Airport-ICS episode baseline that keeps Legacy/CIE A* paths fixed."""

    def __init__(
        self,
        graph: IcsGraph,
        reservations: ReservationTable | None = None,
        edge_reservations: EdgeReservationTable | None = None,
        edge_capacity: int = 1,
        edge_headway_seconds: float = 0.0,
        node_capacities: dict[int, int] | None = None,
        merge_groups: dict[tuple[int, int], int] | None = None,
        merge_capacity: int = 1,
        merge_headway_seconds: float = 0.0,
    ) -> None:
        if edge_capacity <= 0:
            raise ValueError("edge_capacity must be positive")
        if merge_capacity <= 0:
            raise ValueError("merge_capacity must be positive")
        self.graph = graph
        self.reservations = reservations or ReservationTable()
        self.edge_reservations = edge_reservations or EdgeReservationTable()
        self.edge_capacity = edge_capacity
        self.edge_headway_seconds = edge_headway_seconds
        self.node_capacities = dict(node_capacities or {})
        self.merge_groups = dict(merge_groups or {})
        self.merge_capacity = merge_capacity
        self.merge_headway_seconds = merge_headway_seconds
        self.astar = AStarPlanner(graph)
        self.planner = LegacyRouteSIPPPlanner(graph)
        self.stats = LegacyRouteSIPPStats(0, 0, 0, 0, 0, 0, 0)

    def run_episode(
        self,
        tasks: TaskStream | Iterable[TaskLeg],
        max_tasks: int | None = None,
        end_time: float | None = None,
        fault_edges: set[tuple[int, int]] | None = None,
        fault_windows: tuple[EdgeFaultWindow, ...] | None = None,
    ) -> EpisodeResult:
        selected = self._select_tasks(tuple(tasks), max_tasks=max_tasks, end_time=end_time)
        routes: dict[str, list[SIPPNode]] = {}
        unplanned: list[TaskLeg] = []
        events: list[dict[str, object]] = []
        task_by_segment = {task.segment_id: task for task in selected}
        static_faults = set(fault_edges or set())
        repair_windows = tuple(fault_windows or ())
        legacy_path_match = 0
        legacy_path_mismatch = 0
        inserted_wait = 0

        for priority_rank, task in enumerate(selected):
            planning_faults = active_fault_edges(static_faults, repair_windows, task.pass_time)
            start_time = self.planner._earliest_safe_node_start(
                self.reservations,
                task.start,
                task.pass_time,
                self.graph.service_time(task.start),
                self.node_capacities.get(task.start, 1),
                task.task_id,
            )
            if start_time is None:
                self._append_unplanned(events, unplanned, task, priority_rank, "blocked_start_node")
                continue
            legacy_route = self.astar.plan(
                start=task.start,
                goal=task.goal,
                start_time=start_time,
                reservations=self.reservations,
                fault_edges=planning_faults,
                task_id=task.task_id,
            )
            legacy_path = tuple(int(node.location) for node in legacy_route)
            route = self.planner.plan(
                start=task.start,
                goal=task.goal,
                start_time=start_time,
                reservations=self.reservations,
                edge_reservations=self.edge_reservations,
                edge_capacity=self.edge_capacity,
                edge_headway_seconds=self.edge_headway_seconds,
                node_capacities=self.node_capacities,
                merge_groups=self.merge_groups,
                merge_capacity=self.merge_capacity,
                merge_headway_seconds=self.merge_headway_seconds,
                fault_edges=planning_faults,
                task_id=task.task_id,
                legacy_path=legacy_path,
            )
            if not route:
                self._append_unplanned(events, unplanned, task, priority_rank, "legacy_astar_no_path")
                continue
            route_path = tuple(int(node.location) for node in route)
            if route_path == legacy_path:
                legacy_path_match += 1
            else:
                legacy_path_mismatch += 1
            if _inserted_wait_count(self.graph, route) > 0:
                inserted_wait += 1
            self.reservations.add_route(task.task_id, route)
            self._reserve_route_edges(task.task_id, route)
            routes[task.segment_id] = route
            events.append(
                {
                    "event": "planned",
                    "baseline": "legacy_route_sipp",
                    "segment_id": task.segment_id,
                    "task_id": task.task_id,
                    "start": task.start,
                    "goal": task.goal,
                    "entry_time": task.pass_time,
                    "finish_time": route[-1].t2,
                    "priority_rank": priority_rank,
                    "legacy_path": list(legacy_path),
                    "path": list(route_path),
                    "inserted_wait_count": _inserted_wait_count(self.graph, route),
                }
            )

        metrics = compute_episode_metrics(routes, task_by_segment, unplanned, self.reservations, self.node_capacities)
        edge_conflicts = self.edge_reservations.conflict_count(self.edge_capacity, self.edge_headway_seconds)
        merge_conflicts = self.edge_reservations.merge_group_conflict_count(
            self.merge_groups,
            self.merge_capacity,
            self.merge_headway_seconds,
        )
        self.stats = LegacyRouteSIPPStats(
            planned_count=metrics.planned_count,
            unplanned_count=metrics.unplanned_count,
            legacy_path_match_count=legacy_path_match,
            legacy_path_mismatch_count=legacy_path_mismatch,
            inserted_wait_count=inserted_wait,
            edge_conflicts=edge_conflicts,
            merge_conflicts=merge_conflicts,
        )
        return EpisodeResult(routes=routes, unplanned=unplanned, events=events, metrics=metrics)

    @staticmethod
    def _select_tasks(
        tasks: tuple[TaskLeg, ...],
        max_tasks: int | None,
        end_time: float | None,
    ) -> tuple[TaskLeg, ...]:
        selected: list[TaskLeg] = []
        for task in sorted(tasks, key=lambda item: (item.pass_time, item.task_id, item.leg)):
            if end_time is not None and task.pass_time > end_time:
                continue
            if max_tasks is not None and len(selected) >= max_tasks:
                break
            selected.append(task)
        return tuple(selected)

    def _reserve_route_edges(self, task_id: int, route: list[SIPPNode]) -> None:
        for left, right in zip(route, route[1:]):
            if left.location == right.location:
                continue
            edge = self.graph.edge(left.location, right.location)
            edge_start = right.t1 - edge.travel_time
            self.edge_reservations.reserve(task_id, left.location, right.location, edge_start, right.t1)

    @staticmethod
    def _append_unplanned(
        events: list[dict[str, object]],
        unplanned: list[TaskLeg],
        task: TaskLeg,
        priority_rank: int,
        reason: str,
    ) -> None:
        unplanned.append(task)
        events.append(
            {
                "event": "unplanned",
                "baseline": "legacy_route_sipp",
                "segment_id": task.segment_id,
                "task_id": task.task_id,
                "start": task.start,
                "goal": task.goal,
                "entry_time": task.pass_time,
                "priority_rank": priority_rank,
                "reason": reason,
            }
        )


def _inserted_wait_count(graph: IcsGraph, route: list[SIPPNode]) -> int:
    waits = 0
    for left, right in zip(route, route[1:]):
        edge = graph.edge(left.location, right.location)
        edge_start = right.t1 - edge.travel_time
        if edge_start > left.t2 + EPSILON:
            waits += 1
    return waits
