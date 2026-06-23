"""Node time-window reservations for the Python reference simulator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class NodeReservation:
    task_id: int
    node: int
    start: float
    end: float

    def overlaps(self, start: float, end: float) -> bool:
        if self.end <= self.start or end <= start:
            return False
        return not (start > self.end or end < self.start)

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True)
class EdgeReservation:
    task_id: int
    start_node: int
    end_node: int
    start: float
    end: float

    def overlaps(self, start: float, end: float) -> bool:
        epsilon = 1.0e-9
        return not (start >= self.end - epsilon or end <= self.start + epsilon)

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


class ReservationTable:
    """Java-compatible node interval table.

    The legacy A* checks node constraints with strict separation:
    an interval is safe only when `candidate_start > reserved_end` or
    `candidate_end < reserved_start`.
    """

    def __init__(self) -> None:
        self._by_node: dict[int, list[NodeReservation]] = {}

    def clone(self) -> "ReservationTable":
        copied = ReservationTable()
        for node, intervals in self._by_node.items():
            copied._by_node[node] = list(intervals)
        return copied

    def intervals(self, node: int) -> tuple[NodeReservation, ...]:
        return tuple(self._by_node.get(node, ()))

    def all_intervals(self) -> tuple[NodeReservation, ...]:
        values: list[NodeReservation] = []
        for intervals in self._by_node.values():
            values.extend(intervals)
        return tuple(values)

    def has_conflict(self, node: int, start: float, end: float, task_id: int | None = None) -> bool:
        for interval in self._by_node.get(node, ()):
            if task_id is not None and interval.task_id == task_id:
                continue
            if interval.overlaps(start, end):
                return True
        return False

    def has_capacity_conflict(
        self,
        node: int,
        start: float,
        end: float,
        capacity: int = 1,
        task_id: int | None = None,
    ) -> bool:
        if capacity <= 0:
            return True
        overlapping = 0
        for interval in self._by_node.get(node, ()):
            if task_id is not None and interval.task_id == task_id:
                continue
            if interval.overlaps(start, end):
                overlapping += 1
        return overlapping >= capacity

    def reserve(self, task_id: int, node: int, start: float, end: float) -> NodeReservation:
        existing = self._by_node.setdefault(node, [])
        existing[:] = [interval for interval in existing if interval.task_id != task_id]
        reservation = NodeReservation(task_id=task_id, node=node, start=start, end=end)
        existing.append(reservation)
        existing.sort(key=lambda interval: (interval.start, interval.end, interval.task_id))
        return reservation

    def add_route(self, task_id: int, route: Iterable[object]) -> None:
        for node in route:
            self.reserve(
                task_id=task_id,
                node=int(getattr(node, "location")),
                start=float(getattr(node, "t1")),
                end=float(getattr(node, "t2")),
            )

    def remove_task(self, task_id: int) -> None:
        for node in list(self._by_node):
            self._by_node[node] = [
                interval for interval in self._by_node[node] if interval.task_id != task_id
            ]
            if not self._by_node[node]:
                del self._by_node[node]

    def conflict_count(self, node_capacities: dict[int, int] | None = None) -> int:
        node_capacities = node_capacities or {}
        conflicts = 0
        for node, intervals in self._by_node.items():
            capacity = node_capacities.get(node, 1)
            ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
            if capacity > 1:
                active_intervals = [interval for interval in ordered if interval.end > interval.start]
                points = sorted({point for interval in active_intervals for point in (interval.start, interval.end)})
                for point in points:
                    active = sum(
                        1 for interval in active_intervals if interval.start <= point <= interval.end
                    )
                    if active > capacity:
                        conflicts += active - capacity
                continue
            for index, left in enumerate(ordered):
                for right in ordered[index + 1 :]:
                    if right.start > left.end:
                        break
                    if left.overlaps(right.start, right.end):
                        conflicts += 1
        return conflicts

    def to_constraints(self) -> dict[int, list[list[float]]]:
        return {
            node: [[float(item.task_id), item.start, item.end] for item in intervals]
            for node, intervals in self._by_node.items()
        }


class EdgeReservationTable:
    """Edge interval reservations with capacity and entry-headway checks."""

    def __init__(self) -> None:
        self._by_edge: dict[tuple[int, int], list[EdgeReservation]] = {}

    def intervals(self, start_node: int, end_node: int) -> tuple[EdgeReservation, ...]:
        return tuple(self._by_edge.get((start_node, end_node), ()))

    def all_intervals(self) -> tuple[EdgeReservation, ...]:
        values: list[EdgeReservation] = []
        for intervals in self._by_edge.values():
            values.extend(intervals)
        return tuple(values)

    def reserve(
        self,
        task_id: int,
        start_node: int,
        end_node: int,
        start: float,
        end: float,
    ) -> EdgeReservation:
        existing = self._by_edge.setdefault((start_node, end_node), [])
        existing[:] = [interval for interval in existing if interval.task_id != task_id]
        reservation = EdgeReservation(
            task_id=task_id,
            start_node=start_node,
            end_node=end_node,
            start=start,
            end=end,
        )
        existing.append(reservation)
        existing.sort(key=lambda interval: (interval.start, interval.end, interval.task_id))
        return reservation

    def remove_task(self, task_id: int) -> None:
        for edge in list(self._by_edge):
            self._by_edge[edge] = [
                interval for interval in self._by_edge[edge] if interval.task_id != task_id
            ]
            if not self._by_edge[edge]:
                del self._by_edge[edge]

    def has_capacity_conflict(
        self,
        start_node: int,
        end_node: int,
        start: float,
        end: float,
        capacity: int,
        task_id: int | None = None,
    ) -> bool:
        if capacity <= 0:
            return True
        overlapping = 0
        for interval in self._by_edge.get((start_node, end_node), ()):
            if task_id is not None and interval.task_id == task_id:
                continue
            if interval.overlaps(start, end):
                overlapping += 1
        return overlapping >= capacity

    def has_headway_conflict(
        self,
        start_node: int,
        end_node: int,
        start: float,
        headway_seconds: float,
        task_id: int | None = None,
    ) -> bool:
        if headway_seconds <= 0.0:
            return False
        for interval in self._by_edge.get((start_node, end_node), ()):
            if task_id is not None and interval.task_id == task_id:
                continue
            if abs(start - interval.start) < headway_seconds:
                return True
        return False

    def earliest_start(
        self,
        start_node: int,
        end_node: int,
        earliest: float,
        duration: float,
        capacity: int,
        headway_seconds: float = 0.0,
        task_id: int | None = None,
    ) -> float:
        candidate = earliest
        intervals = self._by_edge.get((start_node, end_node), ())
        for _ in range(len(intervals) * 2 + 2):
            moved = False
            for interval in intervals:
                if task_id is not None and interval.task_id == task_id:
                    continue
                candidate_end = candidate + duration
                if capacity <= 0 or interval.overlaps(candidate, candidate_end):
                    if self.has_capacity_conflict(
                        start_node, end_node, candidate, candidate_end, capacity, task_id
                    ):
                        candidate = max(candidate, interval.end)
                        moved = True
                        break
                if headway_seconds > 0.0 and abs(candidate - interval.start) < headway_seconds:
                    candidate = interval.start + headway_seconds
                    moved = True
                    break
            if not moved:
                return candidate
        return candidate

    def conflict_count(self, capacity: int = 1, headway_seconds: float = 0.0) -> int:
        conflicts = 0
        for intervals in self._by_edge.values():
            ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
            for index, left in enumerate(ordered):
                for right in ordered[index + 1 :]:
                    if right.start >= left.end and right.start - left.start >= headway_seconds:
                        break
                    if left.overlaps(right.start, right.end) and capacity <= 1:
                        conflicts += 1
                    elif headway_seconds > 0.0 and abs(left.start - right.start) < headway_seconds:
                        conflicts += 1
        return conflicts
