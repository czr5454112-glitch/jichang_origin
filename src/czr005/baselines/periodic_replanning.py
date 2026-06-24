"""Periodic active-bag SIPP replanning baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from czr005.baselines.sipp import SIPPNode, SIPPPlanner
from czr005.envs.action_mask import EdgeFaultWindow, active_fault_edges
from czr005.sim_py.event_sim import EpisodeResult
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.metrics import compute_episode_metrics
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable
from czr005.sim_py.task_stream import TaskLeg, TaskStream


EPSILON = 1.0e-9


@dataclass
class _ActiveBag:
    task: TaskLeg
    route: list[SIPPNode]
    current: int
    ready_time: float
    waiting_time: float = 0.0
    replan_count: int = 0
    closed: bool = False


@dataclass(frozen=True)
class PeriodicReplanningSummary:
    planned_count: int
    unplanned_count: int
    replan_count: int
    tick_count: int
    peak_active_bags: int
    edge_reservation_conflicts: int
    post_shield_conflicts: int


class PeriodicReplanningBaseline:
    """Route-discarding active-bag replanner using one SIPP step per tick.

    Each periodic tick admits newly arrived bags, prioritizes ready active bags,
    replans a full SIPP path from each current node, commits only the next hop,
    and discards the rest of the path. The next tick replans from the updated
    current node against reservations committed by previous steps.
    """

    def __init__(
        self,
        graph: IcsGraph,
        interval_seconds: float = 5.0,
        max_ticks: int = 2048,
        reservations: ReservationTable | None = None,
        edge_reservations: EdgeReservationTable | None = None,
        edge_capacity: int = 1,
        edge_headway_seconds: float = 0.0,
        node_capacities: dict[int, int] | None = None,
        merge_groups: dict[tuple[int, int], int] | None = None,
        merge_capacity: int = 1,
        merge_headway_seconds: float = 0.0,
    ) -> None:
        if interval_seconds <= 0.0:
            raise ValueError("interval_seconds must be positive")
        if max_ticks <= 0:
            raise ValueError("max_ticks must be positive")
        if edge_capacity <= 0:
            raise ValueError("edge_capacity must be positive")
        if merge_capacity <= 0:
            raise ValueError("merge_capacity must be positive")
        self.graph = graph
        self.interval_seconds = interval_seconds
        self.max_ticks = max_ticks
        self.reservations = reservations or ReservationTable()
        self.edge_reservations = edge_reservations or EdgeReservationTable()
        self.edge_capacity = edge_capacity
        self.edge_headway_seconds = edge_headway_seconds
        self.node_capacities = dict(node_capacities or {})
        self.merge_groups = dict(merge_groups or {})
        self.merge_capacity = merge_capacity
        self.merge_headway_seconds = merge_headway_seconds
        self.planner = SIPPPlanner(graph)
        self.summary = PeriodicReplanningSummary(0, 0, 0, 0, 0, 0, 0)

    def run_episode(
        self,
        tasks: TaskStream | Iterable[TaskLeg],
        max_tasks: int | None = None,
        fault_edges: set[tuple[int, int]] | None = None,
        fault_windows: tuple[EdgeFaultWindow, ...] | None = None,
    ) -> EpisodeResult:
        selected = self._select_tasks(tuple(tasks), max_tasks=max_tasks)
        routes: dict[str, list[SIPPNode]] = {}
        unplanned: list[TaskLeg] = []
        events: list[dict[str, object]] = []
        task_by_segment: dict[str, TaskLeg] = {task.segment_id: task for task in selected}
        active: list[_ActiveBag] = []
        next_task_index = 0
        tick_count = 0
        replan_count = 0
        peak_active_bags = 0
        static_faults = fault_edges or set()
        repair_windows = tuple(fault_windows or ())

        tick_time = selected[0].pass_time if selected else 0.0
        while (next_task_index < len(selected) or any(not bag.closed for bag in active)) and tick_count < self.max_ticks:
            if not any(not bag.closed for bag in active) and next_task_index < len(selected):
                tick_time = max(tick_time, selected[next_task_index].pass_time)

            while next_task_index < len(selected) and selected[next_task_index].pass_time <= tick_time + EPSILON:
                bag = self._admit(selected[next_task_index], tick_time, events)
                active.append(bag)
                next_task_index += 1

            open_active = [bag for bag in active if not bag.closed]
            peak_active_bags = max(peak_active_bags, len(open_active))
            ready = [bag for bag in open_active if bag.ready_time <= tick_time + EPSILON]
            ready.sort(
                key=lambda bag: (
                    bag.task.std - tick_time,
                    -bag.waiting_time,
                    bag.ready_time,
                    bag.task.task_id,
                    bag.task.leg,
                )
            )
            for priority_rank, bag in enumerate(ready):
                if bag.closed:
                    continue
                if bag.current == bag.task.goal:
                    self._close_planned(bag, routes, events, tick_time, priority_rank)
                    continue
                replan_count += 1
                bag.replan_count += 1
                self._replan_one_step(
                    bag,
                    tick_time,
                    priority_rank,
                    static_faults,
                    repair_windows,
                    routes,
                    unplanned,
                    events,
                )

            tick_count += 1
            tick_time += self.interval_seconds

        for bag in active:
            if not bag.closed:
                self.reservations.remove_task(bag.task.task_id)
                self.edge_reservations.remove_task(bag.task.task_id)
                unplanned.append(bag.task)
                bag.closed = True
                events.append(
                    {
                        "event": "unplanned",
                        "baseline": "periodic_replanning_sipp",
                        "segment_id": bag.task.segment_id,
                        "task_id": bag.task.task_id,
                        "current": bag.current,
                        "goal": bag.task.goal,
                        "tick_time": tick_time,
                        "reason": "max_ticks",
                        "replan_count": bag.replan_count,
                    }
                )

        metrics = compute_episode_metrics(
            routes,
            task_by_segment,
            unplanned,
            self.reservations,
            self.node_capacities,
        )
        edge_conflicts = self.edge_reservations.conflict_count(
            capacity=self.edge_capacity,
            headway_seconds=self.edge_headway_seconds,
        ) + self.edge_reservations.merge_group_conflict_count(
            self.merge_groups,
            self.merge_capacity,
            self.merge_headway_seconds,
        )
        self.summary = PeriodicReplanningSummary(
            planned_count=metrics.planned_count,
            unplanned_count=metrics.unplanned_count,
            replan_count=replan_count,
            tick_count=tick_count,
            peak_active_bags=peak_active_bags,
            edge_reservation_conflicts=edge_conflicts,
            post_shield_conflicts=metrics.reservation_conflicts + edge_conflicts,
        )
        return EpisodeResult(routes=routes, unplanned=unplanned, events=events, metrics=metrics)

    @staticmethod
    def _select_tasks(tasks: tuple[TaskLeg, ...], max_tasks: int | None) -> tuple[TaskLeg, ...]:
        selected = sorted(tasks, key=lambda task: (task.pass_time, task.task_id, task.leg))
        if max_tasks is None:
            return tuple(selected)
        return tuple(selected[:max_tasks])

    def _admit(self, task: TaskLeg, tick_time: float, events: list[dict[str, object]]) -> _ActiveBag:
        start_time = self._earliest_safe_node_start(
            task_id=task.task_id,
            node=task.start,
            earliest_start=max(task.pass_time, tick_time),
            duration=self.graph.service_time(task.start),
            capacity=self.node_capacities.get(task.start, 1),
        )
        start_node = SIPPNode(
            location=task.start,
            t1=start_time,
            t2=start_time + self.graph.service_time(task.start),
            gcost=start_time,
            hcost=self.graph.heuristic(task.start, task.goal),
            fcost=start_time + self.graph.heuristic(task.start, task.goal),
        )
        self.reservations.reserve(task.task_id, task.start, start_node.t1, start_node.t2)
        events.append(
            {
                "event": "arrival",
                "baseline": "periodic_replanning_sipp",
                "segment_id": task.segment_id,
                "task_id": task.task_id,
                "current": task.start,
                "goal": task.goal,
                "entry_time": task.pass_time,
                "tick_time": tick_time,
                "ready_time": start_node.t2,
            }
        )
        return _ActiveBag(
            task=task,
            route=[start_node],
            current=task.start,
            ready_time=start_node.t2,
            waiting_time=max(0.0, start_time - task.pass_time),
        )

    def _replan_one_step(
        self,
        bag: _ActiveBag,
        tick_time: float,
        priority_rank: int,
        fault_edges: set[tuple[int, int]],
        fault_windows: tuple[EdgeFaultWindow, ...],
        routes: dict[str, list[SIPPNode]],
        unplanned: list[TaskLeg],
        events: list[dict[str, object]],
    ) -> None:
        start_time = max(tick_time, bag.ready_time)
        active_faults = active_fault_edges(fault_edges, fault_windows, start_time)
        planned = self.planner.plan(
            start=bag.current,
            goal=bag.task.goal,
            start_time=start_time,
            reservations=self.reservations,
            edge_reservations=self.edge_reservations,
            edge_capacity=self.edge_capacity,
            edge_headway_seconds=self.edge_headway_seconds,
            node_capacities=self.node_capacities,
            merge_groups=self.merge_groups,
            merge_capacity=self.merge_capacity,
            merge_headway_seconds=self.merge_headway_seconds,
            fault_edges=active_faults,
            task_id=bag.task.task_id,
        )
        if len(planned) >= 2:
            next_node = planned[1]
            edge = self.graph.edge(bag.current, next_node.location)
            edge_start = next_node.t1 - edge.travel_time
            self.edge_reservations.reserve(
                task_id=bag.task.task_id,
                start_node=bag.current,
                end_node=next_node.location,
                start=edge_start,
                end=next_node.t1,
            )
            self.reservations.reserve(bag.task.task_id, next_node.location, next_node.t1, next_node.t2)
            previous = bag.current
            bag.route.append(
                SIPPNode(
                    location=next_node.location,
                    t1=next_node.t1,
                    t2=next_node.t2,
                    gcost=next_node.gcost,
                    hcost=next_node.hcost,
                    fcost=next_node.fcost,
                )
            )
            bag.current = next_node.location
            bag.ready_time = next_node.t2
            reached_goal = bag.current == bag.task.goal
            events.append(
                {
                    "event": "replan_move",
                    "baseline": "periodic_replanning_sipp",
                    "segment_id": bag.task.segment_id,
                    "task_id": bag.task.task_id,
                    "current": previous,
                    "next_node": bag.current,
                    "goal": bag.task.goal,
                    "entry_time": bag.task.pass_time,
                    "tick_time": tick_time,
                    "ready_time": bag.ready_time,
                    "priority_rank": priority_rank,
                    "replan_count": bag.replan_count,
                    "planned_path": [node.location for node in planned],
                    "reached_goal": reached_goal,
                }
            )
            if reached_goal:
                self._close_planned(bag, routes, events, tick_time, priority_rank)
            return

        if len(planned) == 1 and bag.current == bag.task.goal:
            self._close_planned(bag, routes, events, tick_time, priority_rank)
            return

        self._hold(bag, tick_time, priority_rank, events)
        if bag.replan_count >= self.max_ticks:
            self.reservations.remove_task(bag.task.task_id)
            self.edge_reservations.remove_task(bag.task.task_id)
            unplanned.append(bag.task)
            bag.closed = True

    def _hold(
        self,
        bag: _ActiveBag,
        tick_time: float,
        priority_rank: int,
        events: list[dict[str, object]],
    ) -> None:
        hold_start = self._earliest_safe_node_start(
            task_id=bag.task.task_id,
            node=bag.current,
            earliest_start=max(tick_time, bag.ready_time),
            duration=self.interval_seconds,
            capacity=self.node_capacities.get(bag.current, 1),
        )
        hold_end = hold_start + self.interval_seconds
        bag.route[-1].t2 = hold_end
        bag.route[-1].gcost = hold_end
        bag.route[-1].fcost = hold_end + bag.route[-1].hcost
        bag.waiting_time += hold_end - hold_start
        bag.ready_time = hold_end
        self.reservations.reserve(bag.task.task_id, bag.current, hold_start, hold_end)
        events.append(
            {
                "event": "replan_hold",
                "baseline": "periodic_replanning_sipp",
                "segment_id": bag.task.segment_id,
                "task_id": bag.task.task_id,
                "current": bag.current,
                "next_node": bag.current,
                "goal": bag.task.goal,
                "entry_time": bag.task.pass_time,
                "tick_time": tick_time,
                "ready_time": bag.ready_time,
                "priority_rank": priority_rank,
                "replan_count": bag.replan_count,
                "reason": "no_route",
            }
        )

    def _close_planned(
        self,
        bag: _ActiveBag,
        routes: dict[str, list[SIPPNode]],
        events: list[dict[str, object]],
        tick_time: float,
        priority_rank: int,
    ) -> None:
        if bag.closed:
            return
        bag.closed = True
        routes[bag.task.segment_id] = bag.route
        events.append(
            {
                "event": "planned",
                "baseline": "periodic_replanning_sipp",
                "segment_id": bag.task.segment_id,
                "task_id": bag.task.task_id,
                "current": bag.current,
                "next_node": -1,
                "start": bag.task.start,
                "goal": bag.task.goal,
                "entry_time": bag.task.pass_time,
                "finish_time": bag.route[-1].t2,
                "tick_time": tick_time,
                "ready_time": bag.ready_time,
                "priority_rank": priority_rank,
                "replan_count": bag.replan_count,
                "reached_goal": True,
                "path": [node.location for node in bag.route],
                "planned_path": [],
            }
        )

    def _earliest_safe_node_start(
        self,
        task_id: int,
        node: int,
        earliest_start: float,
        duration: float,
        capacity: int,
    ) -> float:
        if capacity <= 0:
            raise ValueError("node capacity must be positive")
        candidate = earliest_start
        intervals = self.reservations.intervals(node)
        for _ in range(len(intervals) * 2 + 2):
            candidate_end = candidate + duration
            if not self.reservations.has_capacity_conflict(node, candidate, candidate_end, capacity, task_id):
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
