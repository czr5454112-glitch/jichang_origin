"""Observable analytic approximation and paired finite-horizon rollout labels.

This is a deliberately small research proxy. Scores are never authorizations.
No function here trains a policy or consumes future outcomes as runtime inputs.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from time import perf_counter
from typing import Callable, Mapping, Sequence

from .model import Bag, RouteCandidate, Snapshot
from .runtime import COST_WEIGHTS, candidate_reservations, simulate


@dataclass(frozen=True)
class ForecastDemand:
    """A time-stamped forecast available at the current decision, not a label."""

    node: str
    at: int
    count: int = 1
    published_at: int = 0


@dataclass(frozen=True)
class ReleaseChange:
    node: str
    baseline_at: int
    candidate_at: int

    def cumulative_delta(self, at: int) -> int:
        return int(at >= self.candidate_at) - int(at >= self.baseline_at)


@dataclass(frozen=True)
class OccupancyChange:
    resource: str
    start: int
    end: int
    delta: int


@dataclass(frozen=True)
class CirculationFootprint:
    release: ReleaseChange
    occupancy: tuple[OccupancyChange, ...]
    dependency_version: int

    @classmethod
    def between(cls, state: Snapshot, candidate: RouteCandidate,
                baseline: RouteCandidate) -> "CirculationFootprint":
        bag = state.bags[candidate.bag_id]
        if candidate.bag_id != baseline.bag_id or candidate.tray_id != baseline.tray_id:
            raise ValueError("Candidate and baseline must refer to the same bag and tray")
        intervals: dict[tuple[str, int, int], int] = defaultdict(int)
        for route, sign in ((candidate, 1), (baseline, -1)):
            for slot in candidate_reservations(state, route):
                intervals[(slot.resource, slot.start, slot.end)] += sign
        return cls(
            ReleaseChange(bag.destination, baseline.usable_at, candidate.usable_at),
            tuple(OccupancyChange(*key, delta) for key, delta in sorted(intervals.items()) if delta),
            candidate.dependency_version,
        )


class AnalyticDeltaEvaluator:
    """One-use inventory approximation with known in-transit supply.

    The model counts the first usable empty event per tray. It omits later tray
    reuse, future route competition and FIFO dispatch effects. Those omissions
    are explicit candidates for residual learning, not new physical rules.
    """

    def __init__(self, horizon: int, forecasts: Sequence[ForecastDemand] = ()):
        self.horizon = horizon
        self.forecasts = tuple(forecasts)

    def _supply(self, state: Snapshot, candidate: RouteCandidate) -> dict[str, list[int]]:
        supplies: dict[str, list[int]] = defaultdict(list)
        flight_by_tray = {flight.tray_id: flight for flight in state.old_in_transit}
        for tray in state.trays.values():
            if tray.tray_id == candidate.tray_id:
                continue
            if tray.tray_id in state.plans:
                plan = state.plans[tray.tray_id]
                if plan.prefix_only:
                    continue  # A safe stop is not an empty release promise.
                node = (state.bags[plan.bag_id].destination if plan.bag_id is not None else plan.destination_node)
                supplies[node].append(max(state.now, plan.usable_at))
            elif tray.mode == "empty" and tray.node is not None:
                supplies[tray.node].append(max(state.now, tray.available_at))
            elif tray.mode in {"holding", "unloading"} and tray.node is not None:
                supplies[tray.node].append(max(state.now, tray.available_at))
            elif tray.tray_id in flight_by_tray:
                flight = flight_by_tray[tray.tray_id]
                node = state.network.edges[flight.edge_id].target
                available = flight.arrive + state.module.hold_by_node.get(node, 0)
                if tray.bag_id is not None:
                    if state.bags[tray.bag_id].destination != node:
                        continue  # Arrival at an intermediate node is not a release.
                    available += state.module.unload_ticks
                supplies[node].append(available)
        supplies[state.bags[candidate.bag_id].destination].append(candidate.usable_at)
        return supplies

    def absolute(self, state: Snapshot, candidate: RouteCandidate) -> float:
        if any(f.published_at > state.now for f in self.forecasts):
            raise ValueError("Forecast published after decision time")
        if any(f.count < 0 or f.node not in state.network.nodes for f in self.forecasts):
            raise ValueError("Invalid forecast count or node")
        supplies = self._supply(state, candidate)
        demand: dict[str, list[int]] = defaultdict(list)
        carried = {t.bag_id for t in state.trays.values() if t.bag_id is not None}
        for bag in state.bags.values():
            if bag.bag_id not in carried and bag.bag_id not in state.completed:
                demand[bag.origin].append(max(state.now, bag.arrival))
        for forecast in self.forecasts:
            demand[forecast.node].extend([max(state.now, forecast.at)] * forecast.count)
        wait = 0.0
        backlog = 0
        for node, arrivals in demand.items():
            available = sorted(supplies.get(node, ()))
            for index, arrival in enumerate(sorted(arrivals)):
                if arrival > self.horizon:
                    continue
                release = available[index] if index < len(available) else self.horizon + 1
                wait += max(0, min(release, self.horizon) - arrival)
                backlog += int(release > self.horizon)
        bag = state.bags[candidate.bag_id]
        tardiness = 0 if bag.protected else max(0, min(candidate.unload_complete, self.horizon) - bag.deadline)
        incomplete = int(candidate.unload_complete > self.horizon)
        inflight = int(any(leg.depart <= self.horizon < leg.arrive for leg in candidate.legs))
        # Same J_H weights as replay. This approximation predicts zero empty
        # travel and omits downstream tardiness; that is model error, not a
        # different objective or access to future outcomes.
        components = {"tray_wait": wait, "nonprotected_tardiness": tardiness,
                      "empty_distance": 0., "terminal_backlog": backlog + incomplete,
                      "terminal_inflight": inflight}
        return sum(COST_WEIGHTS[key] * value for key, value in components.items())

    def delta(self, state: Snapshot, candidate: RouteCandidate, baseline: RouteCandidate) -> float:
        return self.absolute(state, candidate) - self.absolute(state, baseline)

    def features(self, state: Snapshot, candidate: RouteCandidate) -> dict[str, float]:
        supplies = self._supply(state, candidate)
        destination = state.bags[candidate.bag_id].destination
        return {
            "remaining_route_ticks": float(candidate.unload_complete - state.now),
            "usable_ticks": float(candidate.usable_at - state.now),
            "edge_ticks": float(sum(leg.arrive - leg.depart for leg in candidate.legs)),
            "edge_count": float(len(candidate.legs)),
            "destination_supply_before_10": float(sum(t <= state.now + 10 for t in supplies[destination])),
            "forecast_count": float(sum(f.count for f in self.forecasts)),
            "old_in_transit_count": float(len(state.old_in_transit)),
            "module_hold_ticks": float(state.module.hold_by_node.get(destination, 0)),
            "analytic_absolute": self.absolute(state, candidate),
        }


class ResidualCandidateScorer:
    """Switchable linear residual interface; no fitted weights in this pilot.

    The exact same callable is subtracted at the baseline. Disabling the model
    leaves the analytic controller working and baseline delta exactly zero.
    """

    def __init__(self, evaluator: AnalyticDeltaEvaluator,
                 weights: Mapping[str, float] | None = None):
        self.evaluator = evaluator
        self.weights = None if weights is None else dict(weights)

    def score(self, state: Snapshot, candidate: RouteCandidate, baseline: RouteCandidate) -> float:
        value = self.evaluator.delta(state, candidate, baseline)
        if self.weights is None:
            return value
        features = self.evaluator.features(state, candidate)
        reference = self.evaluator.features(state, baseline)
        unknown = self.weights.keys() - features.keys()
        if unknown:
            raise ValueError(f"Unknown or forbidden feature keys: {sorted(unknown)}")
        return value + sum(w * (features[key] - reference[key]) for key, w in self.weights.items())


def indexed_int(seed: int, scene: str, object_id: str, field: str, lower: int, upper: int) -> int:
    """Counter-style noise: actions cannot change random-number consumption."""
    if upper < lower:
        raise ValueError("Invalid noise bounds")
    key = json.dumps([seed, scene, object_id, field], separators=(",", ":")).encode()
    return lower + int.from_bytes(hashlib.sha256(key).digest()[:8], "big") % (upper - lower + 1)


class PairedRolloutLabeler:
    """Whole-route commitment value under a fixed continuation, not optimal Q.

    A committed itinerary remains frozen in this first proxy. This is narrower
    than an intervention on only the next edge followed by rerouting.
    """

    def __init__(self, horizon: int, simulator: Callable = simulate):
        self.horizon = horizon
        self.simulator = simulator

    def label(self, state: Snapshot, candidates: Sequence[RouteCandidate],
              futures: Sequence[Sequence[Bag]]) -> tuple[list[dict], list[dict]]:
        if not candidates or not futures:
            raise ValueError("Need a valid baseline candidate and at least one future")
        if len({c.candidate_id for c in candidates}) != len(candidates):
            raise ValueError("Candidate IDs must be unique")
        baseline = candidates[0]
        if not baseline.is_baseline or baseline.baseline_id != baseline.candidate_id:
            raise ValueError("First candidate must be the explicit valid baseline")
        if any(c.bag_id != baseline.bag_id or c.tray_id != baseline.tray_id
               or c.baseline_id != baseline.candidate_id
               or c.dependency_version != state.version for c in candidates):
            raise ValueError("Candidates must share the current reference, bag, tray and version")
        branch_rows: list[dict] = []
        deltas: dict[str, list[float]] = defaultdict(list)
        for future_index, future in enumerate(futures):
            trajectory = tuple(future)
            outcomes = []
            for candidate in candidates:
                started = perf_counter()
                outcome = self.simulator(state.clone(), candidate, trajectory, self.horizon)
                elapsed_ms = (perf_counter() - started) * 1000
                outcomes.append((candidate, outcome, elapsed_ms))
            reference_cost = outcomes[0][1].total_cost
            for candidate, outcome, elapsed_ms in outcomes:
                delta = outcome.total_cost - reference_cost
                deltas[candidate.candidate_id].append(delta)
                branch_rows.append({
                    "candidate_id": candidate.candidate_id,
                    "baseline_id": baseline.candidate_id,
                    "future_index": future_index,
                    "total_cost": outcome.total_cost,
                    "paired_delta": delta,
                    "cost_components": outcome.cost_components,
                    "completed_count": len(outcome.completed),
                    "uncompleted_bag_ids": list(outcome.uncompleted_bag_ids),
                    "waiting_bag_ids": list(outcome.waiting_bag_ids),
                    "invariant_checks": outcome.invariant_checks,
                    "rollout_ms": elapsed_ms,
                })
        labels = [{"candidate_id": c.candidate_id,
                   "baseline_id": baseline.candidate_id,
                   "paired_delta_mean": sum(deltas[c.candidate_id]) / len(futures),
                   "paired_deltas": deltas[c.candidate_id],
                   "future_count": len(futures)} for c in candidates]
        return labels, branch_rows
