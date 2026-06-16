"""Deterministic headless reference replay loop."""

from __future__ import annotations

from dataclasses import dataclass

from .astar import AStarPlanner, TimedNode
from .graph import IcsGraph
from .metrics import EpisodeMetrics, compute_episode_metrics
from .reservation import ReservationTable
from .task_stream import TaskLeg, TaskStream


@dataclass(frozen=True)
class EpisodeResult:
    routes: dict[str, list[TimedNode]]
    unplanned: list[TaskLeg]
    events: list[dict[str, object]]
    metrics: EpisodeMetrics

    def to_log(self) -> dict[str, object]:
        return {
            "routes": {
                segment_id: [node.to_dict() for node in route]
                for segment_id, route in self.routes.items()
            },
            "unplanned": [task.to_dict() for task in self.unplanned],
            "events": self.events,
            "metrics": self.metrics.to_dict(),
        }


class ReferenceSimulator:
    """Sequential event replay using the Python A* reference planner.

    This is intentionally headless: no GUI, no file writes, and all externally
    visible information is returned as structured Python data.
    """

    def __init__(self, graph: IcsGraph, reservations: ReservationTable | None = None) -> None:
        self.graph = graph
        self.reservations = reservations or ReservationTable()
        self.planner = AStarPlanner(graph)

    def run_episode(
        self,
        tasks: TaskStream | list[TaskLeg] | tuple[TaskLeg, ...],
        max_tasks: int | None = None,
        end_time: float | None = None,
        fault_edges: set[tuple[int, int]] | None = None,
    ) -> EpisodeResult:
        routes: dict[str, list[TimedNode]] = {}
        unplanned: list[TaskLeg] = []
        events: list[dict[str, object]] = []
        task_by_segment: dict[str, TaskLeg] = {}

        planned_tasks = 0
        for task in tasks:
            if end_time is not None and task.pass_time > end_time:
                continue
            if max_tasks is not None and planned_tasks >= max_tasks:
                break
            task_by_segment[task.segment_id] = task
            route = self.planner.plan(
                start=task.start,
                goal=task.goal,
                start_time=task.pass_time,
                reservations=self.reservations,
                fault_edges=fault_edges,
                task_id=task.task_id,
            )
            if route:
                self.reservations.add_route(task.task_id, route)
                routes[task.segment_id] = route
                planned_tasks += 1
                events.append(
                    {
                        "event": "planned",
                        "segment_id": task.segment_id,
                        "task_id": task.task_id,
                        "start": task.start,
                        "goal": task.goal,
                        "entry_time": task.pass_time,
                        "finish_time": route[-1].t2,
                        "path": [node.location for node in route],
                    }
                )
            else:
                unplanned.append(task)
                planned_tasks += 1
                events.append(
                    {
                        "event": "unplanned",
                        "segment_id": task.segment_id,
                        "task_id": task.task_id,
                        "start": task.start,
                        "goal": task.goal,
                        "entry_time": task.pass_time,
                    }
                )

        metrics = compute_episode_metrics(routes, task_by_segment, unplanned, self.reservations)
        return EpisodeResult(routes=routes, unplanned=unplanned, events=events, metrics=metrics)

