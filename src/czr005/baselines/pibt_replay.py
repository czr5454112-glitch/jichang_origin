"""Active-bag replay baseline driven by the PIBT-style resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from czr005.baselines.pibt import AgentState, PIBTStyleOneStepResolver
from czr005.baselines.sipp import SIPPNode
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
    decision_count: int = 0
    closed: bool = False


@dataclass(frozen=True)
class PIBTActiveBagReplaySummary:
    planned_count: int
    unplanned_count: int
    decision_count: int
    tick_count: int
    peak_active_bags: int
    move_count: int
    hold_count: int
    edge_reservation_conflicts: int
    post_shield_conflicts: int


class PIBTActiveBagReplayBaseline:
    """Replay active bags by resolving each ready tick with PIBT-style priorities."""

    def __init__(
        self,
        graph: IcsGraph,
        interval_seconds: float = 5.0,
        max_ticks: int = 2048,
        hold_seconds: float | None = None,
        reservations: ReservationTable | None = None,
        edge_reservations: EdgeReservationTable | None = None,
        edge_capacity: int = 1,
        edge_headway_seconds: float = 0.0,
        node_capacities: dict[int, int] | None = None,
    ) -> None:
        if interval_seconds <= 0.0:
            raise ValueError("interval_seconds must be positive")
        if max_ticks <= 0:
            raise ValueError("max_ticks must be positive")
        if edge_capacity <= 0:
            raise ValueError("edge_capacity must be positive")
        self.graph = graph
        self.interval_seconds = interval_seconds
        self.max_ticks = max_ticks
        self.hold_seconds = hold_seconds if hold_seconds is not None else interval_seconds
        if self.hold_seconds <= 0.0:
            raise ValueError("hold_seconds must be positive")
        self.reservations = reservations or ReservationTable()
        self.edge_reservations = edge_reservations or EdgeReservationTable()
        self.edge_capacity = edge_capacity
        self.edge_headway_seconds = edge_headway_seconds
        self.node_capacities = dict(node_capacities or {})
        self.resolver = PIBTStyleOneStepResolver(graph, hold_seconds=self.hold_seconds)
        self.summary = PIBTActiveBagReplaySummary(0, 0, 0, 0, 0, 0, 0, 0, 0)

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
        decision_count = 0
        move_count = 0
        hold_count = 0
        peak_active_bags = 0
        static_faults = fault_edges or set()
        repair_windows = tuple(fault_windows or ())

        tick_time = selected[0].pass_time if selected else 0.0
        while (next_task_index < len(selected) or any(not bag.closed for bag in active)) and tick_count < self.max_ticks:
            if not any(not bag.closed for bag in active) and next_task_index < len(selected):
                tick_time = max(tick_time, selected[next_task_index].pass_time)

            while next_task_index < len(selected) and selected[next_task_index].pass_time <= tick_time + EPSILON:
                active.append(self._admit(selected[next_task_index], tick_time, events))
                next_task_index += 1

            open_active = [bag for bag in active if not bag.closed]
            peak_active_bags = max(peak_active_bags, len(open_active))
            for bag in open_active:
                if bag.current == bag.task.goal:
                    self._close_planned(bag, routes, events, tick_time, -1)

            ready = [
                bag
                for bag in active
                if not bag.closed and bag.current != bag.task.goal and bag.ready_time <= tick_time + EPSILON
            ]
            if ready:
                slice_faults = active_fault_edges(static_faults, repair_windows, tick_time)
                agents = [
                    AgentState(
                        task_id=bag.task.task_id,
                        current=bag.current,
                        goal=bag.task.goal,
                        ready_time=max(tick_time, bag.ready_time),
                        deadline=bag.task.std,
                        waiting_time=bag.waiting_time,
                    )
                    for bag in ready
                ]
                by_task = {bag.task.task_id: bag for bag in ready}
                actions = self.resolver.resolve(
                    agents,
                    reservations=self.reservations,
                    edge_reservations=self.edge_reservations,
                    edge_capacity=self.edge_capacity,
                    edge_headway_seconds=self.edge_headway_seconds,
                    node_capacities=self.node_capacities,
                    fault_edges=slice_faults,
                )
                for action in actions:
                    bag = by_task[action.task_id]
                    bag.decision_count += 1
                    decision_count += 1
                    if action.is_hold:
                        hold_count += 1
                        self._apply_hold(bag, action.node_end, tick_time, action.priority_rank, events, action.reason)
                    else:
                        move_count += 1
                        self._apply_move(bag, action, tick_time, events)
                        if bag.current == bag.task.goal:
                            self._close_planned(bag, routes, events, tick_time, action.priority_rank)
                    if bag.decision_count >= self.max_ticks and not bag.closed:
                        self.reservations.remove_task(bag.task.task_id)
                        self.edge_reservations.remove_task(bag.task.task_id)
                        unplanned.append(bag.task)
                        bag.closed = True

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
                        "baseline": "pibt_active_bag_replay",
                        "segment_id": bag.task.segment_id,
                        "task_id": bag.task.task_id,
                        "current": bag.current,
                        "goal": bag.task.goal,
                        "tick_time": tick_time,
                        "ready_time": bag.ready_time,
                        "reason": "max_ticks",
                        "decision_count": bag.decision_count,
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
        )
        self.summary = PIBTActiveBagReplaySummary(
            planned_count=metrics.planned_count,
            unplanned_count=metrics.unplanned_count,
            decision_count=decision_count,
            tick_count=tick_count,
            peak_active_bags=peak_active_bags,
            move_count=move_count,
            hold_count=hold_count,
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
                "baseline": "pibt_active_bag_replay",
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

    def _apply_move(
        self,
        bag: _ActiveBag,
        action: object,
        tick_time: float,
        events: list[dict[str, object]],
    ) -> None:
        previous = bag.current
        bag.waiting_time += max(0.0, float(getattr(action, "edge_start")) - bag.ready_time)
        self.edge_reservations.reserve(
            task_id=bag.task.task_id,
            start_node=previous,
            end_node=int(getattr(action, "next_node")),
            start=float(getattr(action, "edge_start")),
            end=float(getattr(action, "edge_end")),
        )
        self.reservations.reserve(
            bag.task.task_id,
            int(getattr(action, "next_node")),
            float(getattr(action, "node_start")),
            float(getattr(action, "node_end")),
        )
        next_node = int(getattr(action, "next_node"))
        bag.route.append(
            SIPPNode(
                location=next_node,
                t1=float(getattr(action, "node_start")),
                t2=float(getattr(action, "node_end")),
                gcost=float(getattr(action, "node_start")),
                hcost=self.graph.heuristic(next_node, bag.task.goal),
                fcost=float(getattr(action, "node_start")) + self.graph.heuristic(next_node, bag.task.goal),
            )
        )
        bag.current = next_node
        bag.ready_time = float(getattr(action, "node_end"))
        reached_goal = bag.current == bag.task.goal
        events.append(
            {
                "event": "pibt_move",
                "baseline": "pibt_active_bag_replay",
                "segment_id": bag.task.segment_id,
                "task_id": bag.task.task_id,
                "current": previous,
                "next_node": bag.current,
                "goal": bag.task.goal,
                "entry_time": bag.task.pass_time,
                "tick_time": tick_time,
                "ready_time": bag.ready_time,
                "priority_rank": int(getattr(action, "priority_rank")),
                "decision_count": bag.decision_count,
                "reason": str(getattr(action, "reason")),
                "reached_goal": reached_goal,
            }
        )

    def _apply_hold(
        self,
        bag: _ActiveBag,
        hold_end: float,
        tick_time: float,
        priority_rank: int,
        events: list[dict[str, object]],
        reason: str,
    ) -> None:
        bag.waiting_time += max(0.0, hold_end - bag.ready_time)
        bag.ready_time = hold_end
        current_node = bag.route[-1]
        current_node.t2 = hold_end
        current_node.gcost = hold_end
        current_node.fcost = current_node.gcost + current_node.hcost
        self.reservations.reserve(bag.task.task_id, bag.current, current_node.t1, current_node.t2)
        events.append(
            {
                "event": "pibt_hold",
                "baseline": "pibt_active_bag_replay",
                "segment_id": bag.task.segment_id,
                "task_id": bag.task.task_id,
                "current": bag.current,
                "next_node": bag.current,
                "goal": bag.task.goal,
                "entry_time": bag.task.pass_time,
                "tick_time": tick_time,
                "ready_time": bag.ready_time,
                "priority_rank": priority_rank,
                "decision_count": bag.decision_count,
                "reason": reason,
                "reached_goal": False,
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
                "baseline": "pibt_active_bag_replay",
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
                "decision_count": bag.decision_count,
                "reached_goal": True,
                "path": [node.location for node in bag.route],
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
        candidate = earliest_start
        for interval in self.reservations.intervals(node):
            if interval.task_id == task_id:
                continue
            if not interval.overlaps(candidate, candidate + duration):
                continue
            if self.reservations.has_capacity_conflict(node, candidate, candidate + duration, capacity, task_id):
                candidate = interval.end + EPSILON
        return candidate
