"""PIBT/CS-PIBT-style one-step conflict resolver baseline."""

from __future__ import annotations

from dataclasses import dataclass

from czr005.sim_py.astar import AStarPlanner
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.reservation import ReservationTable


@dataclass(frozen=True)
class AgentState:
    task_id: int
    current: int
    goal: int
    ready_time: float
    deadline: float
    waiting_time: float = 0.0

    @property
    def slack(self) -> float:
        return self.deadline - self.ready_time


@dataclass(frozen=True)
class ResolvedAction:
    task_id: int
    action: str
    current: int
    next_node: int
    edge_start: float
    edge_end: float
    node_start: float
    node_end: float
    reason: str
    priority_rank: int

    @property
    def is_hold(self) -> bool:
        return self.action == "hold"


class PIBTStyleOneStepResolver:
    """Resolve a simultaneous junction-decision slice with deterministic priority.

    This is a compact Phase2D baseline, not a full recursive PIBT
    implementation. Agents are ordered by deadline pressure and waiting time;
    each agent takes the best safe outgoing edge by shortest heuristic-to-goal,
    otherwise it holds. The resolver screens against existing node
    reservations, same-slice target-node conflicts, same-slice edge conflicts,
    faulted edges, and next-hop reachability.
    """

    def __init__(self, graph: IcsGraph, hold_seconds: float = 1.0) -> None:
        if hold_seconds <= 0.0:
            raise ValueError("hold_seconds must be positive")
        self.graph = graph
        self.hold_seconds = hold_seconds
        self._astar = AStarPlanner(graph)

    def resolve(
        self,
        agents: list[AgentState] | tuple[AgentState, ...],
        reservations: ReservationTable | None = None,
        fault_edges: set[tuple[int, int]] | None = None,
    ) -> list[ResolvedAction]:
        reservations = reservations or ReservationTable()
        fault_edges = fault_edges or set()
        ordered = sorted(
            agents,
            key=lambda agent: (agent.slack, -agent.waiting_time, agent.ready_time, agent.task_id),
        )
        chosen: list[ResolvedAction] = []
        local_node_windows: list[tuple[int, float, float, int]] = []
        local_edges: set[tuple[int, int]] = set()

        for priority_rank, agent in enumerate(ordered):
            action = self._choose_action(
                agent=agent,
                priority_rank=priority_rank,
                reservations=reservations,
                fault_edges=fault_edges,
                local_node_windows=local_node_windows,
                local_edges=local_edges,
            )
            chosen.append(action)
            local_node_windows.append((action.next_node, action.node_start, action.node_end, action.task_id))
            if action.action == "move":
                local_edges.add((action.current, action.next_node))

        return chosen

    def _choose_action(
        self,
        agent: AgentState,
        priority_rank: int,
        reservations: ReservationTable,
        fault_edges: set[tuple[int, int]],
        local_node_windows: list[tuple[int, float, float, int]],
        local_edges: set[tuple[int, int]],
    ) -> ResolvedAction:
        for next_node in self._candidate_edges(agent):
            if (agent.current, next_node) in fault_edges:
                continue
            if (agent.current, next_node) in local_edges:
                continue
            if not self._reachable_after_step(next_node, agent.goal, fault_edges):
                continue

            edge = self.graph.edge(agent.current, next_node)
            edge_start = agent.ready_time
            edge_end = edge_start + edge.travel_time
            node_start = edge_end
            node_end = node_start + self.graph.service_time(next_node)

            if next_node != agent.goal and reservations.has_conflict(
                next_node, node_start, node_end, task_id=agent.task_id
            ):
                continue
            if self._local_node_conflict(next_node, node_start, node_end, agent.task_id, local_node_windows):
                continue

            return ResolvedAction(
                task_id=agent.task_id,
                action="move",
                current=agent.current,
                next_node=next_node,
                edge_start=edge_start,
                edge_end=edge_end,
                node_start=node_start,
                node_end=node_end,
                reason="best_safe_edge",
                priority_rank=priority_rank,
            )

        return ResolvedAction(
            task_id=agent.task_id,
            action="hold",
            current=agent.current,
            next_node=agent.current,
            edge_start=agent.ready_time,
            edge_end=agent.ready_time,
            node_start=agent.ready_time,
            node_end=agent.ready_time + self.hold_seconds,
            reason="no_safe_edge",
            priority_rank=priority_rank,
        )

    def _candidate_edges(self, agent: AgentState) -> list[int]:
        return sorted(
            self.graph.outgoing(agent.current),
            key=lambda next_node: (
                self.graph.heuristic(next_node, agent.goal),
                self.graph.edge(agent.current, next_node).travel_time,
                next_node,
            ),
        )

    def _reachable_after_step(
        self,
        next_node: int,
        goal: int,
        fault_edges: set[tuple[int, int]],
    ) -> bool:
        if next_node == goal:
            return True
        return bool(self._astar.plan(next_node, goal, fault_edges=fault_edges))

    @staticmethod
    def _local_node_conflict(
        node: int,
        start: float,
        end: float,
        task_id: int,
        local_windows: list[tuple[int, float, float, int]],
    ) -> bool:
        for other_node, other_start, other_end, other_task_id in local_windows:
            if other_node != node or other_task_id == task_id:
                continue
            if not (start > other_end or end < other_start):
                return True
        return False
