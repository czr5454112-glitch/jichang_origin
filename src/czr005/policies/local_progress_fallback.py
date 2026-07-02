"""No-full-A* local fallback rules for decentralized routing.

These rules deliberately use only runtime-visible local state plus the static
heuristic table already bundled with the map. They do not invoke the verified
CIE/A* teacher or re-plan a full route.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import math
from typing import Any


EPSILON = 1.0e-6
UNREACHABLE = 1.0e9


@dataclass(frozen=True)
class FallbackDecision:
    strategy: str
    next_node: int | None
    reason: str
    score: float
    candidate_scores: dict[str, dict[str, float | bool]]


@dataclass(frozen=True)
class LocalProgressFallbackConfig:
    strategy: str
    lookahead_depth: int = 1
    static_weight: float = 1.0
    wait_weight: float = 0.0
    pressure_weight: float = 0.0
    loop_weight: float = 12.0
    backtrack_weight: float = 6.0
    traffic_weight: float = 0.0
    progress_weight: float = 0.0
    slack_wait_multiplier: float = 0.0
    fault_penalty: float = UNREACHABLE
    lookahead_beam_width: int = 3


@dataclass
class TrafficMemory:
    node_visits: Counter[int] = field(default_factory=Counter)
    edge_visits: Counter[tuple[int, int]] = field(default_factory=Counter)
    node_wait_seconds: defaultdict[int, float] = field(default_factory=lambda: defaultdict(float))

    def update(self, current: int, selected: int, wait_seconds: float) -> None:
        self.node_visits[selected] += 1
        self.edge_visits[(current, selected)] += 1
        self.node_wait_seconds[selected] += max(0.0, wait_seconds)

    def penalty(self, current: int, selected: int) -> float:
        node_load = math.log1p(self.node_visits[selected])
        edge_load = math.log1p(self.edge_visits[(current, selected)])
        wait_load = math.log1p(self.node_wait_seconds[selected])
        return node_load + edge_load + 0.1 * wait_load


class LocalProgressFallback:
    def __init__(self, config: LocalProgressFallbackConfig) -> None:
        self.config = config

    @classmethod
    def static_distance(cls) -> "LocalProgressFallback":
        return cls(LocalProgressFallbackConfig(strategy="static_distance", progress_weight=0.1))

    @classmethod
    def node_window_aware(cls) -> "LocalProgressFallback":
        return cls(
            LocalProgressFallbackConfig(
                strategy="node_window_aware",
                wait_weight=1.4,
                pressure_weight=4.0,
                progress_weight=0.2,
            )
        )

    @classmethod
    def pibt_lite(cls) -> "LocalProgressFallback":
        return cls(
            LocalProgressFallbackConfig(
                strategy="node_window_pibt_lite",
                wait_weight=1.8,
                pressure_weight=6.0,
                loop_weight=18.0,
                backtrack_weight=10.0,
                progress_weight=0.35,
                slack_wait_multiplier=0.4,
            )
        )

    @classmethod
    def local_window(cls, depth: int = 3) -> "LocalProgressFallback":
        return cls(
            LocalProgressFallbackConfig(
                strategy=f"local_window_k{depth}",
                lookahead_depth=depth,
                wait_weight=1.2,
                pressure_weight=5.0,
                loop_weight=16.0,
                backtrack_weight=8.0,
                progress_weight=0.25,
            )
        )

    @classmethod
    def static_traffic_map(cls, depth: int = 3) -> "LocalProgressFallback":
        return cls(
            LocalProgressFallbackConfig(
                strategy="static_traffic_map",
                lookahead_depth=depth,
                wait_weight=1.2,
                pressure_weight=4.5,
                loop_weight=16.0,
                backtrack_weight=8.0,
                traffic_weight=7.0,
                progress_weight=0.25,
            )
        )

    @classmethod
    def bounded_local_search(cls, depth: int = 5) -> "LocalProgressFallback":
        return cls(
            LocalProgressFallbackConfig(
                strategy=f"bounded_local_search_k{depth}",
                lookahead_depth=depth,
                wait_weight=1.6,
                pressure_weight=6.0,
                loop_weight=22.0,
                backtrack_weight=12.0,
                traffic_weight=4.0,
                progress_weight=0.35,
            )
        )

    def select(
        self,
        *,
        graph: Any,
        row: dict[str, Any],
        current: int,
        goal: int,
        ready_time: float,
        reservations: dict[int, list[tuple[float, float]]],
        active_faults: set[tuple[int, int]],
        path: list[int],
        traffic: TrafficMemory | None = None,
    ) -> FallbackDecision:
        candidates = [int(value) for value in row.get("candidate_next_nodes", [])]
        if not candidates:
            return FallbackDecision(self.config.strategy, None, "no_candidate", UNREACHABLE, {})

        scored: list[tuple[float, int, dict[str, float | bool]]] = []
        candidate_scores: dict[str, dict[str, float | bool]] = {}
        for candidate in candidates:
            components = self._candidate_components(
                graph=graph,
                row=row,
                current=current,
                candidate=candidate,
                goal=goal,
                ready_time=ready_time,
                reservations=reservations,
                active_faults=active_faults,
                path=path,
                traffic=traffic,
                depth=self.config.lookahead_depth,
            )
            candidate_scores[str(candidate)] = components
            if components["faulted"]:
                score = self.config.fault_penalty
            else:
                score = float(components["score"])
            scored.append((score, candidate, components))

        scored.sort(key=lambda item: (item[0], item[1]))
        best_score, best_candidate, _components = scored[0]
        if best_score >= self.config.fault_penalty:
            return FallbackDecision(self.config.strategy, None, "all_candidates_faulted", best_score, candidate_scores)
        return FallbackDecision(self.config.strategy, best_candidate, "selected_lowest_local_score", best_score, candidate_scores)

    def _candidate_components(
        self,
        *,
        graph: Any,
        row: dict[str, Any],
        current: int,
        candidate: int,
        goal: int,
        ready_time: float,
        reservations: dict[int, list[tuple[float, float]]],
        active_faults: set[tuple[int, int]],
        path: list[int],
        traffic: TrafficMemory | None,
        depth: int,
    ) -> dict[str, float | bool]:
        faulted = (current, candidate) in active_faults
        edge = graph.edge(current, candidate)
        arrival = ready_time + edge.travel_time
        service = graph.service_time(candidate)
        service_start = _earliest_safe(reservations, candidate, arrival, service)
        wait = max(0.0, service_start - arrival)
        pressure = float(_overlap_count(reservations[candidate], arrival, arrival + service))
        static_cost = float(edge.travel_time) + float(graph.heuristic(candidate, goal))
        current_heuristic = float(graph.heuristic(current, goal))
        progress = current_heuristic - float(graph.heuristic(candidate, goal))
        loop_penalty = float(path.count(candidate))
        backtrack = 1.0 if len(path) >= 2 and candidate == path[-2] else 0.0
        traffic_penalty = traffic.penalty(current, candidate) if traffic is not None else 0.0
        slack = max(0.0, float(row.get("deadline_or_std", ready_time)) - ready_time)
        slack_pressure = wait / max(1.0, slack) if slack > 0.0 else wait
        lookahead = 0.0
        if depth > 1:
            lookahead = self._lookahead_cost(
                graph=graph,
                current=candidate,
                goal=goal,
                ready_time=service_start + service,
                reservations=reservations,
                active_faults=active_faults,
                path=[*path, candidate],
                depth=depth - 1,
            )
        score = (
            self.config.static_weight * static_cost
            + self.config.wait_weight * wait
            + self.config.pressure_weight * pressure
            + self.config.loop_weight * loop_penalty
            + self.config.backtrack_weight * backtrack
            + self.config.traffic_weight * traffic_penalty
            - self.config.progress_weight * progress
            + self.config.slack_wait_multiplier * slack_pressure
            + lookahead
        )
        return {
            "faulted": faulted,
            "static_cost": static_cost,
            "wait_seconds": wait,
            "pressure": pressure,
            "progress": progress,
            "loop_penalty": loop_penalty,
            "backtrack": backtrack,
            "traffic_penalty": traffic_penalty,
            "lookahead_cost": lookahead,
            "score": score,
        }

    def _lookahead_cost(
        self,
        *,
        graph: Any,
        current: int,
        goal: int,
        ready_time: float,
        reservations: dict[int, list[tuple[float, float]]],
        active_faults: set[tuple[int, int]],
        path: list[int],
        depth: int,
    ) -> float:
        if current == goal:
            return 0.0
        if depth <= 0:
            return 0.15 * float(graph.heuristic(current, goal))
        best = UNREACHABLE
        outgoing = [
            nxt
            for nxt in graph.outgoing(current)
            if (current, nxt) not in active_faults
        ]
        outgoing.sort(key=lambda nxt: (float(graph.edge(current, nxt).travel_time) + float(graph.heuristic(nxt, goal)), nxt))
        for nxt in outgoing[: self.config.lookahead_beam_width]:
            if (current, nxt) in active_faults:
                continue
            edge = graph.edge(current, nxt)
            arrival = ready_time + edge.travel_time
            service = graph.service_time(nxt)
            pressure = _overlap_count(reservations[nxt], arrival, arrival + service)
            wait = float(pressure) * min(service, 1.0)
            loop = float(path.count(nxt))
            cost = (
                0.35 * edge.travel_time
                + 0.2 * float(graph.heuristic(nxt, goal))
                + self.config.wait_weight * wait
                + 0.5 * self.config.loop_weight * loop
            )
            cost += self._lookahead_cost(
                graph=graph,
                current=nxt,
                goal=goal,
                ready_time=arrival + wait + service,
                reservations=reservations,
                active_faults=active_faults,
                path=[*path, nxt],
                depth=depth - 1,
            )
            best = min(best, cost)
        if best >= UNREACHABLE:
            return 0.5 * UNREACHABLE
        return best


def _overlap_count(intervals: list[tuple[float, float]], start: float, end: float) -> int:
    return sum(1 for left, right in intervals if not (end < left or start > right))


def _earliest_safe(reservations: dict[int, list[tuple[float, float]]], node: int, start: float, service: float) -> float:
    current = start
    for left, right in sorted(reservations[node]):
        end = current + service
        if end < left:
            return current
        if not (end < left or current > right):
            current = right + EPSILON
    return current
