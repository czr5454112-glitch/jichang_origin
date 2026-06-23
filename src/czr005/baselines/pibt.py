"""PIBT/CS-PIBT-style one-step conflict resolver baseline."""

from __future__ import annotations

from dataclasses import dataclass

from czr005.sim_py.astar import AStarPlanner
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.reservation import EdgeReservationTable, ReservationTable


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

    Agents are ordered by deadline pressure and waiting time; each agent takes
    the best safe outgoing edge by shortest heuristic-to-goal, otherwise it
    holds. When a preferred next node is currently occupied by another active
    agent in the same decision slice, the resolver recursively tries to move
    the blocking lower-priority agent away before falling back to an
    alternative edge or hold.
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
        edge_reservations: EdgeReservationTable | None = None,
        edge_capacity: int = 1,
        edge_headway_seconds: float = 0.0,
        node_capacities: dict[int, int] | None = None,
        fault_edges: set[tuple[int, int]] | None = None,
    ) -> list[ResolvedAction]:
        if edge_capacity <= 0:
            raise ValueError("edge_capacity must be positive")
        reservations = reservations or ReservationTable()
        edge_reservations = edge_reservations or EdgeReservationTable()
        node_capacities = node_capacities or {}
        fault_edges = fault_edges or set()
        ordered = sorted(
            agents,
            key=lambda agent: (agent.slack, -agent.waiting_time, agent.ready_time, agent.task_id),
        )
        priority_ranks = {agent.task_id: priority_rank for priority_rank, agent in enumerate(ordered)}
        agents_by_task = {agent.task_id: agent for agent in ordered}
        current_owner: dict[int, int] = {}
        for agent in ordered:
            current_owner.setdefault(agent.current, agent.task_id)
        chosen_by_task: dict[int, ResolvedAction] = {}
        local_node_windows: list[tuple[int, float, float, int]] = []
        local_edges: set[tuple[int, int]] = set()

        for agent in ordered:
            if agent.task_id in chosen_by_task:
                continue
            self._assign_recursive(
                agent=agent,
                priority_rank=priority_ranks[agent.task_id],
                reservations=reservations,
                edge_reservations=edge_reservations,
                edge_capacity=edge_capacity,
                edge_headway_seconds=edge_headway_seconds,
                node_capacities=node_capacities,
                fault_edges=fault_edges,
                agents_by_task=agents_by_task,
                current_owner=current_owner,
                priority_ranks=priority_ranks,
                chosen_by_task=chosen_by_task,
                local_node_windows=local_node_windows,
                local_edges=local_edges,
                blocked_targets=set(),
                inherited=False,
                visiting=set(),
            )

        return [chosen_by_task[agent.task_id] for agent in ordered]

    def _assign_recursive(
        self,
        agent: AgentState,
        priority_rank: int,
        reservations: ReservationTable,
        edge_reservations: EdgeReservationTable,
        edge_capacity: int,
        edge_headway_seconds: float,
        node_capacities: dict[int, int],
        fault_edges: set[tuple[int, int]],
        agents_by_task: dict[int, AgentState],
        current_owner: dict[int, int],
        priority_ranks: dict[int, int],
        chosen_by_task: dict[int, ResolvedAction],
        local_node_windows: list[tuple[int, float, float, int]],
        local_edges: set[tuple[int, int]],
        blocked_targets: set[int],
        inherited: bool,
        visiting: set[int],
    ) -> bool:
        if agent.task_id in chosen_by_task:
            return chosen_by_task[agent.task_id].action == "move"
        if agent.task_id in visiting:
            return False

        visiting.add(agent.task_id)
        for next_node in self._candidate_edges(agent):
            if next_node in blocked_targets:
                continue
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

            if edge_reservations.has_capacity_conflict(
                agent.current,
                next_node,
                edge_start,
                edge_end,
                edge_capacity,
                task_id=agent.task_id,
            ):
                continue
            if edge_reservations.has_headway_conflict(
                agent.current,
                next_node,
                edge_start,
                edge_headway_seconds,
                task_id=agent.task_id,
            ):
                continue

            if next_node != agent.goal and reservations.has_capacity_conflict(
                next_node,
                node_start,
                node_end,
                capacity=node_capacities.get(next_node, 1),
                task_id=agent.task_id,
            ):
                continue
            if self._local_node_conflict(next_node, node_start, node_end, agent.task_id, local_node_windows):
                continue

            blocker_id = current_owner.get(next_node)
            inherited_move = False
            if blocker_id is not None and blocker_id != agent.task_id:
                blocker_action = chosen_by_task.get(blocker_id)
                if blocker_action is None:
                    blocker = agents_by_task[blocker_id]
                    if not self._assign_recursive(
                        agent=blocker,
                        priority_rank=priority_ranks[blocker.task_id],
                        reservations=reservations,
                        edge_reservations=edge_reservations,
                        edge_capacity=edge_capacity,
                        edge_headway_seconds=edge_headway_seconds,
                        node_capacities=node_capacities,
                        fault_edges=fault_edges,
                        agents_by_task=agents_by_task,
                        current_owner=current_owner,
                        priority_ranks=priority_ranks,
                        chosen_by_task=chosen_by_task,
                        local_node_windows=local_node_windows,
                        local_edges=local_edges,
                        blocked_targets={agent.current, next_node},
                        inherited=True,
                        visiting=visiting,
                    ):
                        continue
                    blocker_action = chosen_by_task.get(blocker_id)
                    inherited_move = True
                if (
                    blocker_action is None
                    or blocker_action.is_hold
                    or blocker_action.next_node == next_node
                    or blocker_action.edge_start > node_start
                ):
                    continue
                if (agent.current, next_node) in local_edges:
                    continue
                if self._local_node_conflict(next_node, node_start, node_end, agent.task_id, local_node_windows):
                    continue

            reason = (
                "priority_inheritance"
                if inherited_move
                else "inherited_move"
                if inherited
                else "best_safe_edge"
            )
            chosen_by_task[agent.task_id] = ResolvedAction(
                task_id=agent.task_id,
                action="move",
                current=agent.current,
                next_node=next_node,
                edge_start=edge_start,
                edge_end=edge_end,
                node_start=node_start,
                node_end=node_end,
                reason=reason,
                priority_rank=priority_rank,
            )
            local_node_windows.append((next_node, node_start, node_end, agent.task_id))
            local_edges.add((agent.current, next_node))
            visiting.remove(agent.task_id)
            return True

        visiting.remove(agent.task_id)
        if inherited:
            return False
        chosen_by_task[agent.task_id] = ResolvedAction(
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
        local_node_windows.append(
            (agent.current, agent.ready_time, agent.ready_time + self.hold_seconds, agent.task_id)
        )
        return True

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
