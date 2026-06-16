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
        return not (start > self.end or end < self.start)

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

    def conflict_count(self) -> int:
        conflicts = 0
        for intervals in self._by_node.values():
            ordered = sorted(intervals, key=lambda interval: (interval.start, interval.end))
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

