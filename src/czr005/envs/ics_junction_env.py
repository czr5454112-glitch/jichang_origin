"""Gym-style junction-decision environment with hard shield fallback."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
import random
from typing import Any

from czr005.baselines.sipp import SIPPNode
from czr005.envs.action_mask import (
    ActionCandidate,
    EdgeFaultWindow,
    active_fault_edges,
    build_action_candidates,
    shortest_safe_action,
)
from czr005.envs.observation_builder import build_junction_observation
from czr005.envs.reward import DecisionRewardConfig, decision_reward
from czr005.sim_py.astar import AStarPlanner
from czr005.sim_py.event_sim import EpisodeResult
from czr005.sim_py.graph import IcsGraph
from czr005.sim_py.metrics import compute_episode_metrics
from czr005.sim_py.reservation import EdgeReservationTable, NodeReservation, ReservationTable
from czr005.sim_py.task_stream import TaskLeg, TaskStream


PolicyFn = Callable[[dict[str, Any], dict[str, Any]], int]


@dataclass(frozen=True)
class EnvRunInfo:
    total_reward: float
    steps: int
    truncated: bool


class IcsJunctionEnv:
    """Sequential junction-decision shell for safe policy experiments.

    The environment keeps learning semantics simple in Phase3: one task leg is
    routed through a sequence of local junction decisions, then the next task
    leg starts. A policy proposes an action index from the current observation;
    the hard shield executes that action only if the current reservation,
    headway, capacity, and fault checks allow it. Otherwise it falls back to the
    shortest safe candidate or a safe hold action.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        graph: IcsGraph,
        tasks: TaskStream | Iterable[TaskLeg],
        max_tasks: int | None = None,
        hold_seconds: float = 1.0,
        edge_capacity: int = 1,
        edge_headway_seconds: float = 0.0,
        fault_edges: set[tuple[int, int]] | None = None,
        fault_windows: tuple[EdgeFaultWindow, ...] | None = None,
        require_reachable_goal: bool = True,
        max_decisions_per_task: int = 256,
        reward_config: DecisionRewardConfig | None = None,
    ) -> None:
        if hold_seconds <= 0.0:
            raise ValueError("hold_seconds must be positive")
        if edge_capacity <= 0:
            raise ValueError("edge_capacity must be positive")
        if max_decisions_per_task <= 0:
            raise ValueError("max_decisions_per_task must be positive")

        selected = sorted(tuple(tasks), key=lambda task: (task.pass_time, task.task_id, task.leg))
        self.graph = graph
        self.tasks = tuple(selected[:max_tasks] if max_tasks is not None else selected)
        self.hold_seconds = hold_seconds
        self.edge_capacity = edge_capacity
        self.edge_headway_seconds = edge_headway_seconds
        self.fault_edges = fault_edges or set()
        self.fault_windows = tuple(fault_windows or ())
        self.require_reachable_goal = require_reachable_goal
        self.max_decisions_per_task = max_decisions_per_task
        self.reward_config = reward_config or DecisionRewardConfig()
        self._rng = random.Random()
        self._reset_state()

    def reset(self, seed: int | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        if seed is not None:
            self._rng.seed(seed)
        self._reset_state()
        self._start_next_task()
        return self._observation(), self._info(event="reset")

    def step(self, action: int) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]:
        if self.terminated:
            return {}, 0.0, True, False, self._info(event="terminated")
        if self.current_task is None or not self.current_route:
            raise RuntimeError("environment must be reset before step")

        candidates = self._candidates()
        proposed = self._candidate_by_index(candidates, action)
        unsafe_proposal = proposed is None or not proposed.safe
        executed = proposed if proposed is not None and proposed.safe else self._fallback_candidate(candidates)
        shield_blocked = unsafe_proposal

        if executed is None:
            reward = self._mark_unplanned(reason="no_safe_action", shield_blocked=shield_blocked)
            return self._observation(), reward, self.terminated, False, self._info(
                event="unplanned",
                reason="no_safe_action",
                proposed_action=action,
                executed_action=None,
                shield_blocked=shield_blocked,
                unsafe_proposal=unsafe_proposal,
            )

        task_deadline = self.current_task.std
        if shield_blocked:
            self.shield_blocks += 1
        if unsafe_proposal:
            self.unsafe_proposals += 1

        previous_ready = self.current_route[-1].t2
        if executed.is_hold:
            reached_goal = False
            self._apply_hold(executed)
            waited_seconds = executed.node_end - previous_ready
            elapsed_seconds = waited_seconds
        else:
            reached_goal = self._apply_move(executed)
            waited_seconds = 0.0
            elapsed_seconds = executed.node_end - previous_ready

        unplanned = False
        if not reached_goal and self.task_decisions >= self.max_decisions_per_task:
            unplanned = True
            self._mark_unplanned(reason="max_decisions", shield_blocked=False)
        elif reached_goal:
            self._complete_current_task()

        reward = decision_reward(
            elapsed_seconds=elapsed_seconds,
            waited_seconds=waited_seconds,
            reached_goal=reached_goal,
            finish_time=executed.node_end if reached_goal else None,
            deadline=task_deadline,
            shield_blocked=shield_blocked,
            unsafe_proposal=unsafe_proposal,
            unplanned=unplanned,
            config=self.reward_config,
        )
        return self._observation(), reward, self.terminated, False, self._info(
            event="step",
            proposed_action=action,
            executed_action=executed.index,
            executed_kind=executed.kind,
            shield_blocked=shield_blocked,
            unsafe_proposal=unsafe_proposal,
            reached_goal=reached_goal,
            unplanned=unplanned,
        )

    def run_policy(
        self,
        policy: PolicyFn,
        seed: int | None = None,
        max_steps: int = 100_000,
    ) -> tuple[EpisodeResult, EnvRunInfo]:
        obs, info = self.reset(seed=seed)
        total_reward = 0.0
        steps = 0
        terminated = False
        truncated = False
        while not terminated:
            if steps >= max_steps:
                truncated = True
                break
            action = policy(obs, info)
            obs, reward, terminated, truncated_step, info = self.step(action)
            total_reward += reward
            steps += 1
            if truncated_step:
                truncated = True
                break
        return self.episode_result(), EnvRunInfo(total_reward=total_reward, steps=steps, truncated=truncated)

    def episode_result(self) -> EpisodeResult:
        metrics = compute_episode_metrics(
            self.routes,
            self.task_by_segment,
            self.unplanned,
            self.reservations,
        )
        return EpisodeResult(
            routes=self.routes,
            unplanned=self.unplanned,
            events=self.events,
            metrics=metrics,
        )

    def episode_summary(self) -> dict[str, float | int]:
        result = self.episode_result()
        edge_conflicts = self.edge_reservations.conflict_count(
            capacity=self.edge_capacity,
            headway_seconds=self.edge_headway_seconds,
        )
        return {
            **result.metrics.to_dict(),
            "edge_reservation_conflicts": edge_conflicts,
            "post_shield_conflicts": result.metrics.reservation_conflicts + edge_conflicts,
            "shield_blocks": self.shield_blocks,
            "unsafe_proposals": self.unsafe_proposals,
            "completed_events": len([event for event in self.events if event["event"] == "planned"]),
        }

    def _reset_state(self) -> None:
        self.reservations = ReservationTable()
        self.edge_reservations = EdgeReservationTable()
        self.routes: dict[str, list[SIPPNode]] = {}
        self.unplanned: list[TaskLeg] = []
        self.events: list[dict[str, object]] = []
        self.task_by_segment: dict[str, TaskLeg] = {}
        self.task_index = 0
        self.current_task: TaskLeg | None = None
        self.current_route: list[SIPPNode] = []
        self.waiting_time = 0.0
        self.task_decisions = 0
        self.total_steps = 0
        self.shield_blocks = 0
        self.unsafe_proposals = 0
        self.terminated = False

    def _start_next_task(self) -> None:
        if self.task_index >= len(self.tasks):
            self.current_task = None
            self.current_route = []
            self.terminated = True
            return

        task = self.tasks[self.task_index]
        start_time = self._earliest_safe_node_start(
            task.start,
            task.pass_time,
            self.graph.service_time(task.start),
            task.task_id,
        )
        start_node = SIPPNode(
            location=task.start,
            t1=start_time,
            t2=start_time + self.graph.service_time(task.start),
            gcost=start_time,
            hcost=self.graph.heuristic(task.start, task.goal),
            fcost=start_time + self.graph.heuristic(task.start, task.goal),
            parent=None,
        )
        self.current_task = task
        self.current_route = [start_node]
        self.waiting_time = max(0.0, start_time - task.pass_time)
        self.task_decisions = 0
        self.task_by_segment[task.segment_id] = task
        self.reservations.reserve(task.task_id, task.start, start_node.t1, start_node.t2)
        self.terminated = False

    def _complete_current_task(self) -> None:
        if self.current_task is None:
            return
        task = self.current_task
        route = list(self.current_route)
        self.routes[task.segment_id] = route
        self.events.append(
            {
                "event": "planned",
                "baseline": "junction_env",
                "segment_id": task.segment_id,
                "task_id": task.task_id,
                "start": task.start,
                "goal": task.goal,
                "entry_time": task.pass_time,
                "finish_time": route[-1].t2,
                "decision_count": self.task_decisions,
                "waiting_time": self.waiting_time,
                "path": [node.location for node in route],
            }
        )
        self.task_index += 1
        self._start_next_task()

    def _mark_unplanned(self, reason: str, shield_blocked: bool) -> float:
        if self.current_task is None:
            return 0.0
        task = self.current_task
        self.reservations.remove_task(task.task_id)
        self.edge_reservations.remove_task(task.task_id)
        self.unplanned.append(task)
        self.events.append(
            {
                "event": "unplanned",
                "baseline": "junction_env",
                "segment_id": task.segment_id,
                "task_id": task.task_id,
                "start": task.start,
                "goal": task.goal,
                "entry_time": task.pass_time,
                "reason": reason,
                "decision_count": self.task_decisions,
                "shield_blocked": shield_blocked,
            }
        )
        self.task_index += 1
        self._start_next_task()
        return decision_reward(
            elapsed_seconds=0.0,
            shield_blocked=shield_blocked,
            unsafe_proposal=shield_blocked,
            unplanned=True,
            config=self.reward_config,
        )

    def _apply_hold(self, candidate: ActionCandidate) -> None:
        current = self.current_route[-1]
        current.t2 = candidate.node_end
        current.gcost = candidate.node_end
        current.fcost = current.gcost + current.hcost
        self.waiting_time += candidate.node_end - candidate.node_start
        self.task_decisions += 1
        self.total_steps += 1
        if self.current_task is not None:
            self.reservations.reserve(
                self.current_task.task_id,
                current.location,
                current.t1,
                current.t2,
            )

    def _apply_move(self, candidate: ActionCandidate) -> bool:
        if self.current_task is None:
            return False
        previous = self.current_route[-1]
        node = SIPPNode(
            location=candidate.next_node,
            t1=candidate.node_start,
            t2=candidate.node_end,
            gcost=candidate.node_start,
            hcost=candidate.heuristic_to_goal,
            fcost=candidate.node_start + candidate.heuristic_to_goal,
            parent=previous,
        )
        self.edge_reservations.reserve(
            task_id=self.current_task.task_id,
            start_node=candidate.current,
            end_node=candidate.next_node,
            start=candidate.edge_start,
            end=candidate.edge_end,
        )
        self.reservations.reserve(
            self.current_task.task_id,
            candidate.next_node,
            candidate.node_start,
            candidate.node_end,
        )
        self.current_route.append(node)
        self.task_decisions += 1
        self.total_steps += 1
        return candidate.next_node == self.current_task.goal

    def _observation(self) -> dict[str, Any]:
        if self.current_task is None or not self.current_route:
            return {}
        current = self.current_route[-1]
        return build_junction_observation(
            graph=self.graph,
            task=self.current_task,
            current=current.location,
            ready_time=current.t2,
            waiting_time=self.waiting_time,
            reservations=self.reservations,
            edge_reservations=self.edge_reservations,
            edge_capacity=self.edge_capacity,
            edge_headway_seconds=self.edge_headway_seconds,
            fault_edges=self.fault_edges,
            fault_windows=self.fault_windows,
            hold_seconds=self.hold_seconds,
            require_reachable_goal=self.require_reachable_goal,
        )

    def _candidates(self) -> tuple[ActionCandidate, ...]:
        if self.current_task is None or not self.current_route:
            return ()
        current = self.current_route[-1]
        return build_action_candidates(
            graph=self.graph,
            task=self.current_task,
            current=current.location,
            ready_time=current.t2,
            reservations=self.reservations,
            edge_reservations=self.edge_reservations,
            edge_capacity=self.edge_capacity,
            edge_headway_seconds=self.edge_headway_seconds,
            fault_edges=self.fault_edges,
            fault_windows=self.fault_windows,
            hold_seconds=self.hold_seconds,
            require_reachable_goal=self.require_reachable_goal,
        )

    @staticmethod
    def _candidate_by_index(
        candidates: tuple[ActionCandidate, ...],
        index: int,
    ) -> ActionCandidate | None:
        for candidate in candidates:
            if candidate.index == index:
                return candidate
        return None

    def _fallback_candidate(self, candidates: tuple[ActionCandidate, ...]) -> ActionCandidate | None:
        goal = self.current_task.goal if self.current_task is not None else None
        fallback_index = shortest_safe_action(candidates, goal=goal)
        if fallback_index is None:
            return None
        return IcsJunctionEnv._candidate_by_index(candidates, fallback_index)

    def _info(self, event: str, **extra: Any) -> dict[str, Any]:
        info: dict[str, Any] = {
            "event": event,
            "task_index": self.task_index,
            "terminated": self.terminated,
            "shield_blocks": self.shield_blocks,
            "unsafe_proposals": self.unsafe_proposals,
        }
        if self.current_task is not None:
            info["task_id"] = self.current_task.task_id
            info["segment_id"] = self.current_task.segment_id
        info.update(extra)
        if self.terminated:
            info["episode_summary"] = self.episode_summary()
        return info

    def _earliest_safe_node_start(
        self,
        node: int,
        earliest_start: float,
        duration: float,
        task_id: int,
    ) -> float:
        candidate = earliest_start
        for interval in sorted(
            self.reservations.intervals(node),
            key=lambda item: (item.start, item.end, item.task_id),
        ):
            if interval.task_id == task_id:
                continue
            if _node_interval_safe(interval, candidate, candidate + duration):
                continue
            candidate = interval.end + 1e-9
        return candidate


def _node_interval_safe(interval: NodeReservation, start: float, end: float) -> bool:
    return start > interval.end or end < interval.start


def shortest_safe_policy(obs: dict[str, Any], info: dict[str, Any] | None = None) -> int:
    candidates = obs.get("candidates", ())
    safe_moves = [
        candidate
        for candidate in candidates
        if candidate.get("safe") and candidate.get("kind") == "move"
    ]
    goal = int(obs.get("task", {}).get("goal", -1))
    goal_moves = [candidate for candidate in safe_moves if int(candidate["next_node"]) == goal]
    if goal_moves:
        chosen = min(
            goal_moves,
            key=lambda candidate: (float(candidate["travel_time"]), int(candidate["index"])),
        )
        return int(chosen["index"])
    if safe_moves:
        return int(
            min(
                safe_moves,
                key=lambda candidate: (
                    float(candidate["heuristic_to_goal"]),
                    float(candidate["travel_time"]),
                    int(candidate["next_node"]),
                ),
            )["index"]
        )
    for candidate in candidates:
        if candidate.get("safe"):
            return int(candidate["index"])
    return 0


def astar_guided_policy_factory(graph: IcsGraph) -> PolicyFn:
    planner = AStarPlanner(graph)

    def policy(obs: dict[str, Any], info: dict[str, Any]) -> int:
        if not obs:
            return 0
        task = obs["task"]
        route = planner.plan(
            start=int(task["current"]),
            goal=int(task["goal"]),
            start_time=float(task["ready_time"]),
        )
        if len(route) > 1:
            next_node = route[1].location
            candidates = obs["candidates"]
            planned = [
                candidate
                for candidate in candidates
                if candidate["kind"] == "move" and int(candidate["next_node"]) == next_node
            ]
            if planned and planned[0]["safe"]:
                return int(planned[0]["index"])
            if planned and _only_transient_blocks(planned[0]["blocked_reasons"]):
                hold = _safe_hold_action(candidates)
                if hold is not None:
                    return hold
        return shortest_safe_policy(obs, info)

    return policy


def fault_aware_astar_policy_factory(
    graph: IcsGraph,
    fault_edges: set[tuple[int, int]] | None = None,
    fault_windows: tuple[EdgeFaultWindow, ...] | None = None,
) -> PolicyFn:
    planner = AStarPlanner(graph)
    blocked = fault_edges or set()
    windows = tuple(fault_windows or ())

    def policy(obs: dict[str, Any], info: dict[str, Any]) -> int:
        if not obs:
            return 0
        task = obs["task"]
        ready_time = float(task["ready_time"])
        route = planner.plan(
            start=int(task["current"]),
            goal=int(task["goal"]),
            start_time=ready_time,
            fault_edges=active_fault_edges(blocked, windows, ready_time),
        )
        if len(route) > 1:
            action = _action_for_next_node(obs["candidates"], route[1].location)
            if action is not None:
                return action
        return shortest_safe_policy(obs, info)

    return policy


def _action_for_next_node(candidates: object, next_node: int) -> int | None:
    planned = [
        candidate
        for candidate in candidates
        if candidate["kind"] == "move" and int(candidate["next_node"]) == next_node
    ]
    if planned and planned[0]["safe"]:
        return int(planned[0]["index"])
    if planned and _only_transient_blocks(planned[0]["blocked_reasons"]):
        return _safe_hold_action(candidates)
    return None


def _only_transient_blocks(reasons: object) -> bool:
    transient = {"edge_capacity", "edge_headway", "node_reservation"}
    return bool(reasons) and all(str(reason) in transient for reason in reasons)


def _safe_hold_action(candidates: object) -> int | None:
    for candidate in candidates:
        if candidate.get("kind") == "hold" and candidate.get("safe"):
            return int(candidate["index"])
    return None
