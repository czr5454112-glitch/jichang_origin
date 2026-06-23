"""Rolling-horizon prioritized non-learning baseline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from czr005.baselines.sipp import SIPPPlanner, SIPPNode
from czr005.envs.action_mask import EdgeFaultWindow, active_fault_edges
from czr005.sim_py.event_sim import EpisodeResult
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.metrics import compute_episode_metrics
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable
from czr005.sim_py.task_stream import TaskLeg, TaskStream


@dataclass(frozen=True)
class HorizonBatch:
    start_time: float
    end_time: float
    tasks: tuple[TaskLeg, ...]


class RollingHorizonBaseline:
    """Periodic prioritized planner using SIPP and a shared reservation table.

    This is the first Phase2C baseline skeleton. It batches task legs by
    pass-time horizon, prioritizes deadline-critical tasks inside each batch,
    and plans each leg with SIPP against reservations created by previous legs.
    """

    def __init__(
        self,
        graph: IcsGraph,
        horizon_seconds: float = 300.0,
        reservations: ReservationTable | None = None,
        edge_reservations: EdgeReservationTable | None = None,
        edge_capacity: int = 1,
        edge_headway_seconds: float = 0.0,
    ) -> None:
        if horizon_seconds <= 0.0:
            raise ValueError("horizon_seconds must be positive")
        if edge_capacity <= 0:
            raise ValueError("edge_capacity must be positive")
        self.graph = graph
        self.horizon_seconds = horizon_seconds
        self.reservations = reservations or ReservationTable()
        self.edge_reservations = edge_reservations or EdgeReservationTable()
        self.edge_capacity = edge_capacity
        self.edge_headway_seconds = edge_headway_seconds
        self.planner = SIPPPlanner(graph)

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
        task_by_segment: dict[str, TaskLeg] = {task.segment_id: task for task in selected}
        static_faults = set(fault_edges or set())
        repair_windows = tuple(fault_windows or ())

        for batch in self._batches(selected):
            prioritized = sorted(
                batch.tasks,
                key=lambda task: (task.std - task.pass_time, task.pass_time, task.task_id, task.leg),
            )
            for priority_rank, task in enumerate(prioritized):
                planning_faults = active_fault_edges(static_faults, repair_windows, task.pass_time)
                route = self.planner.plan(
                    start=task.start,
                    goal=task.goal,
                    start_time=task.pass_time,
                    reservations=self.reservations,
                    edge_reservations=self.edge_reservations,
                    edge_capacity=self.edge_capacity,
                    edge_headway_seconds=self.edge_headway_seconds,
                    fault_edges=planning_faults,
                    task_id=task.task_id,
                )
                if route:
                    self.reservations.add_route(task.task_id, route)
                    self._reserve_route_edges(task.task_id, route)
                    routes[task.segment_id] = route
                    events.append(
                        {
                            "event": "planned",
                            "baseline": "rolling_horizon_sipp",
                            "segment_id": task.segment_id,
                            "task_id": task.task_id,
                            "start": task.start,
                            "goal": task.goal,
                            "entry_time": task.pass_time,
                            "finish_time": route[-1].t2,
                            "horizon_start": batch.start_time,
                            "horizon_end": batch.end_time,
                            "priority_rank": priority_rank,
                            "path": [node.location for node in route],
                        }
                    )
                else:
                    unplanned.append(task)
                    events.append(
                        {
                            "event": "unplanned",
                            "baseline": "rolling_horizon_sipp",
                            "segment_id": task.segment_id,
                            "task_id": task.task_id,
                            "start": task.start,
                            "goal": task.goal,
                            "entry_time": task.pass_time,
                            "horizon_start": batch.start_time,
                            "horizon_end": batch.end_time,
                            "priority_rank": priority_rank,
                        }
                    )

        metrics = compute_episode_metrics(routes, task_by_segment, unplanned, self.reservations)
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

    def _batches(self, tasks: tuple[TaskLeg, ...]) -> tuple[HorizonBatch, ...]:
        if not tasks:
            return ()
        batches: list[HorizonBatch] = []
        current_start = tasks[0].pass_time
        current_end = current_start + self.horizon_seconds
        current: list[TaskLeg] = []
        for task in tasks:
            while task.pass_time > current_end:
                if current:
                    batches.append(HorizonBatch(current_start, current_end, tuple(current)))
                    current = []
                current_start = current_end
                current_end = current_start + self.horizon_seconds
            current.append(task)
        if current:
            batches.append(HorizonBatch(current_start, current_end, tuple(current)))
        return tuple(batches)

    def _reserve_route_edges(self, task_id: int, route: list[SIPPNode]) -> None:
        for left, right in zip(route, route[1:]):
            if left.location == right.location:
                continue
            edge = self.graph.edge(left.location, right.location)
            edge_start = right.t1 - edge.travel_time
            self.edge_reservations.reserve(
                task_id=task_id,
                start_node=left.location,
                end_node=right.location,
                start=edge_start,
                end=right.t1,
            )
