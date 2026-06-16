"""Legacy-compatible A* route planner for the Python reference simulator."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key

from .graph import IcsGraph
from .reservation import ReservationTable


@dataclass
class TimedNode:
    location: int
    t1: float
    t2: float
    gcost: float = 0.0
    hcost: float = 0.0
    fcost: float = 0.0
    parent: "TimedNode | None" = None

    def to_dict(self) -> dict[str, float | int]:
        return {
            "location": self.location,
            "t1": self.t1,
            "t2": self.t2,
            "gcost": self.gcost,
            "hcost": self.hcost,
            "fcost": self.fcost,
        }


class AStarPlanner:
    def __init__(self, graph: IcsGraph) -> None:
        self.graph = graph

    def plan(
        self,
        start: int,
        goal: int,
        start_time: float = 0.0,
        reservations: ReservationTable | None = None,
        fault_edges: set[tuple[int, int]] | None = None,
        task_id: int | None = None,
    ) -> list[TimedNode]:
        reservations = reservations or ReservationTable()
        fault_edges = fault_edges or set()
        open_list: list[TimedNode] = [
            TimedNode(
                location=start,
                t1=start_time,
                t2=start_time + self.graph.service_time(start),
            )
        ]
        closed: set[int] = set()

        while open_list:
            current = self._pop_min_f(open_list)
            closed.add(current.location)
            if current.location == goal:
                return self._reconstruct(current)

            for next_location in self.graph.outgoing(current.location):
                if next_location in closed or (current.location, next_location) in fault_edges:
                    continue
                edge = self.graph.edge(current.location, next_location)
                t1 = current.t2 + edge.travel_time
                t2 = t1 + self.graph.service_time(next_location)
                if next_location != goal and reservations.has_conflict(
                    next_location, t1, t2, task_id=task_id
                ):
                    continue

                gcost = t1
                hcost = self.graph.heuristic(next_location, goal)
                child = TimedNode(
                    location=next_location,
                    t1=t1,
                    t2=t2,
                    gcost=gcost,
                    hcost=hcost,
                    fcost=gcost + hcost,
                    parent=current,
                )
                existing = self._in_open(open_list, next_location)
                if existing is None:
                    open_list.append(child)
                elif gcost < existing.gcost:
                    existing.t1 = child.t1
                    existing.t2 = child.t2
                    existing.gcost = child.gcost
                    existing.hcost = child.hcost
                    existing.fcost = child.fcost
                    existing.parent = current
        return []

    @staticmethod
    def _in_open(open_list: list[TimedNode], location: int) -> TimedNode | None:
        for node in open_list:
            if node.location == location:
                return node
        return None

    @staticmethod
    def _pop_min_f(open_list: list[TimedNode]) -> TimedNode:
        # Java uses `(int) (o1.getfCost() - o2.getfCost())`, so sub-unit
        # differences are treated as ties. Python keeps the same stable order.
        open_list.sort(key=cmp_to_key(lambda left, right: int(left.fcost - right.fcost)))
        return open_list.pop(0)

    @staticmethod
    def _reconstruct(goal_node: TimedNode) -> list[TimedNode]:
        route: list[TimedNode] = []
        current: TimedNode | None = goal_node
        while current is not None:
            route.append(current)
            current = current.parent
        route.reverse()
        return route
