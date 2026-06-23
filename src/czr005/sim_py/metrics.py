"""Shared metrics for the Python reference simulator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import mean

from .astar import TimedNode
from .reservation import ReservationTable
from .task_stream import TaskLeg


@dataclass(frozen=True)
class RouteMetric:
    segment_id: str
    task_id: int
    start: int
    goal: int
    entry_time: float
    finish_time: float
    travel_time: float
    late_by: float

    def to_dict(self) -> dict[str, float | int | str]:
        return asdict(self)


@dataclass(frozen=True)
class EpisodeMetrics:
    planned_count: int
    unplanned_count: int
    mean_travel_time: float
    p95_travel_time: float
    p99_travel_time: float
    late_count: int
    max_lateness: float
    makespan: float
    reservation_conflicts: int

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def route_metric(task: TaskLeg, route: list[TimedNode]) -> RouteMetric:
    finish_time = route[-1].t2
    travel_time = finish_time - task.pass_time
    return RouteMetric(
        segment_id=task.segment_id,
        task_id=task.task_id,
        start=task.start,
        goal=task.goal,
        entry_time=task.pass_time,
        finish_time=finish_time,
        travel_time=travel_time,
        late_by=max(0.0, finish_time - task.std),
    )


def compute_episode_metrics(
    planned: dict[str, list[TimedNode]],
    task_by_segment: dict[str, TaskLeg],
    unplanned: list[TaskLeg],
    reservations: ReservationTable,
    node_capacities: dict[int, int] | None = None,
) -> EpisodeMetrics:
    route_metrics = [
        route_metric(task_by_segment[segment_id], route)
        for segment_id, route in planned.items()
        if route
    ]
    travel_times = [metric.travel_time for metric in route_metrics]
    lateness = [metric.late_by for metric in route_metrics]
    return EpisodeMetrics(
        planned_count=len(route_metrics),
        unplanned_count=len(unplanned),
        mean_travel_time=mean(travel_times) if travel_times else 0.0,
        p95_travel_time=_percentile(travel_times, 95.0),
        p99_travel_time=_percentile(travel_times, 99.0),
        late_count=sum(1 for value in lateness if value > 0.0),
        max_lateness=max(lateness) if lateness else 0.0,
        makespan=max((route[-1].t2 for route in planned.values() if route), default=0.0),
        reservation_conflicts=reservations.conflict_count(node_capacities),
    )


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction
