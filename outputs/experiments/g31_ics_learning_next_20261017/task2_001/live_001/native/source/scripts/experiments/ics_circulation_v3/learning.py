"""Small observable value models and a stronger timed analytic comparator.

Neither forecast paths nor fitted costs authorize physical actions. The only
training dependency is the repository's existing NumPy installation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from heapq import heappop, heappush
from typing import Sequence

import numpy as np

from .evaluation import AnalyticDeltaEvaluator, ForecastDemand
from .model import Bag, RouteCandidate, Snapshot
from .runtime import COST_WEIGHTS


@dataclass(frozen=True)
class RoutingDemandForecast:
    forecast_id: str
    node: str
    destination: str
    at: int
    deadline: int
    count: int = 1
    published_at: int = 0
    # Synthetic identified requests. Empty means forecast_id:index identities;
    # aggregate field forecasts without such a mapping need another interface.
    unit_ids: tuple[str, ...] = ()


def active_forecasts(state: Snapshot, forecasts: Sequence[RoutingDemandForecast], *,
                     max_forecast_age: int = 60) -> tuple[RoutingDemandForecast, ...]:
    if any(f.published_at > state.now for f in forecasts):
        raise ValueError("Unpublished forecasts are not observable")
    if any(f.count < 0 or not isinstance(f.count, int) or f.node not in state.network.nodes
           or f.destination not in state.network.nodes for f in forecasts):
        raise ValueError("Invalid routing forecast")
    # Identified demand persists when late. A nominal time is not a cancellation.
    # Latest published revisions are selected BEFORE age/count filtering, so an
    # expired or cancelled new revision cannot resurrect an older request.
    latest = {}
    for forecast in forecasts:
        previous = latest.get(forecast.forecast_id)
        if previous is None or forecast.published_at > previous.published_at:
            latest[forecast.forecast_id] = forecast
        elif forecast.published_at == previous.published_at and forecast != previous:
            raise ValueError("Conflicting forecast revision")
    result = []
    for forecast in latest.values():
        if state.now - forecast.published_at > max_forecast_age:
            continue
        identities = forecast.unit_ids or tuple(f"{forecast.forecast_id}:{i}" for i in range(forecast.count))
        if len(identities) != forecast.count or len(set(identities)) != len(identities):
            raise ValueError("Forecast identity/count mismatch")
        pending = tuple(identity for identity in identities if identity not in state.bags)
        if pending:
            result.append(replace(forecast, at=max(state.now + 1, forecast.at), count=len(pending), unit_ids=pending))
    return tuple(result)


def shortest_edges(state: Snapshot, origin: str, destination: str) -> tuple[str, ...] | None:
    queue = [(0, origin, ())]
    best = {origin: 0}
    adjacency = {}
    for edge in state.network.edges.values():
        if edge.capacity > 0:
            adjacency.setdefault(edge.source, []).append(edge)
    while queue:
        length, node, path = heappop(queue)
        if length != best[node]:
            continue
        if node == destination:
            return path
        for edge in sorted(adjacency.get(node, ()), key=lambda e: e.edge_id):
            value = length + edge.travel_time
            if value < best.get(edge.target, float("inf")):
                best[edge.target] = value
                heappush(queue, (value, edge.target, path + (edge.edge_id,)))
    return None


class TimedAnalyticEvaluator(AnalyticDeltaEvaluator):
    """One-use inventory plus forecast OD paths interacting with the candidate.

    This deliberately omits interactions *between* forecast bags, replanning,
    and later tray cycles. It is a stronger cheap approximation, not an exact
    MPC, full simulation or certificate. All demands were issued by now.
    """

    def __init__(self, horizon: int, forecasts: Sequence[RoutingDemandForecast]):
        self.routing_forecasts = tuple(forecasts)
        super().__init__(horizon, ())

    def _base(self, state: Snapshot) -> AnalyticDeltaEvaluator:
        forecasts = active_forecasts(state, self.routing_forecasts)
        return AnalyticDeltaEvaluator(self.horizon, tuple(ForecastDemand(f.node, f.at, f.count, f.published_at)
                                                         for f in forecasts))

    def forecast_impacts(self, state: Snapshot, candidate: RouteCandidate) -> dict[str, float]:
        forecasts = active_forecasts(state, self.routing_forecasts)
        supplies = self._base(state)._supply(state, candidate)
        by_origin = {}
        for forecast in sorted(forecasts, key=lambda f: (f.at, f.forecast_id)):
            by_origin.setdefault(forecast.node, []).extend([forecast] * forecast.count)
        delay = tardiness = overlapping = unmatched = 0.
        for node, demands in by_origin.items():
            usable = sorted(supplies.get(node, ()))
            for index, forecast in enumerate(demands):
                path = shortest_edges(state, node, forecast.destination)
                if path is None or index >= len(usable):
                    unmatched += 1
                    continue
                tick = max(forecast.at, usable[index])
                route_delay = 0
                for edge_id in path:
                    edge = state.network.edges[edge_id]
                    # Candidate is already accepted; the later forecast vehicle
                    # waits behind its occupied half-open interval.
                    for leg in candidate.legs:
                        if leg.edge_id == edge_id and tick < leg.arrive and tick + edge.travel_time > leg.depart:
                            wait = max(0, leg.arrive - tick)
                            route_delay += wait
                            tick += wait
                            overlapping += 1
                    tick += edge.travel_time
                tick += state.module.unload_ticks
                delay += route_delay
                tardiness += max(0, min(tick, self.horizon) - forecast.deadline)
        return {"forecast_conflict_delay": delay, "forecast_tardiness": tardiness,
                "forecast_edge_overlaps": overlapping, "forecast_unmatched": unmatched}

    def absolute(self, state: Snapshot, candidate: RouteCandidate) -> float:
        return self._base(state).absolute(state, candidate) + COST_WEIGHTS["nonprotected_tardiness"] * self.forecast_impacts(state, candidate)["forecast_tardiness"]

    def features(self, state: Snapshot, candidate: RouteCandidate) -> dict[str, float]:
        base = self._base(state)
        values = base.features(state, candidate)
        impacts = self.forecast_impacts(state, candidate)
        values.update(impacts)
        values["timed_analytic_absolute"] = self.absolute(state, candidate)
        bag = state.bags[candidate.bag_id]
        current = state.trays[candidate.tray_id].node
        active = active_forecasts(state, self.routing_forecasts)
        values.update({
            "source_empty_stock": float(sum(t.node == current and t.mode == "empty" and t.available_at <= state.now
                                            and t.tray_id not in state.plans for t in state.trays.values())),
            "destination_empty_stock": float(sum(t.node == bag.destination and t.mode == "empty" and t.available_at <= state.now
                                                 and t.tray_id not in state.plans for t in state.trays.values())),
            "total_tray_count": float(len(state.trays)),
            "known_waiting_count": float(sum(b not in state.completed and b not in state.load_times for b in state.bags)),
            "old_remaining_ticks": float(sum(max(0, f.arrive - state.now) for f in state.old_in_transit)),
            "candidate_deadline_margin": float(bag.deadline - candidate.unload_complete),
            "candidate_first_departure": float(candidate.legs[0].depart - state.now if candidate.legs else 0),
            "forecast_earliest_ticks": float(min((f.at - state.now for f in active), default=0)),
            "forecast_destination_count": float(sum(f.count for f in active if f.node == bag.destination)),
        })
        if not all(np.isfinite(value) for value in values.values()):
            raise ValueError("Nonfinite feature")
        return values


@dataclass
class RidgeValueModel:
    """Small linear baseline, with identical features for direct and residual.

    Direct learns full rollout costs. Residual learns paired incremental cost
    minus the stronger analytic delta. Both subtract the reference prediction
    at inference, so baseline-zero consistency is structural.
    """

    kind: str
    feature_names: tuple[str, ...]
    center: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    intercept: float
    alpha: float

    @classmethod
    def fit(cls, rows: Sequence[dict], kind: str, alpha: float = 1.) -> "RidgeValueModel":
        if kind not in {"direct", "residual"} or alpha <= 0 or not rows:
            raise ValueError("Need nonempty training rows, valid model kind and positive penalty")
        names = tuple(sorted(rows[0]["features"]))
        if any(tuple(sorted(row["features"])) != names for row in rows):
            raise ValueError("Feature schema mismatch")
        x = np.array([[row["features"][key] for key in names] for row in rows], dtype=float)
        references = {row["source_group"]: row for row in rows if row["is_baseline"]}
        if len(references) != len({row["source_group"] for row in rows}):
            raise ValueError("Every training group needs its own baseline")
        center = x.mean(axis=0)
        scale = x.std(axis=0)
        scale[scale < 1e-9] = 1.
        if kind == "direct":
            matrix = (x - center) / scale
            y = np.array([row["cost_mean"] for row in rows])
            intercept = float(y.mean())
        else:
            x0 = np.array([[references[row["source_group"]]["features"][key] for key in names] for row in rows])
            matrix = (x - x0) / scale
            y = np.array([row["delta_mean"] - row["timed_delta"] for row in rows])
            intercept = 0.
        if not np.isfinite(matrix).all() or not np.isfinite(y).all():
            raise ValueError("Nonfinite training data")
        coefficients = np.linalg.solve(matrix.T @ matrix + alpha * np.eye(len(names)), matrix.T @ (y - intercept))
        return cls(kind, names, center, scale, coefficients, intercept, alpha)

    def predict_value(self, features: dict[str, float]) -> float:
        if set(features) != set(self.feature_names):
            raise ValueError("Feature schema mismatch")
        x = np.array([features[key] for key in self.feature_names])
        if not np.isfinite(x).all():
            raise ValueError("Nonfinite runtime feature")
        return float(((x - self.center) / self.scale) @ self.coefficients + self.intercept)

    def score_features(self, features: dict[str, float], reference: dict[str, float]) -> float:
        delta = self.predict_value(features) - self.predict_value(reference)
        if self.kind == "residual":
            delta += features["timed_analytic_absolute"] - reference["timed_analytic_absolute"]
        return delta

    def to_dict(self) -> dict:
        result = asdict(self)
        for key in ("center", "scale", "coefficients"):
            result[key] = result[key].tolist()
        return result

    @classmethod
    def from_dict(cls, value: dict) -> "RidgeValueModel":
        value = dict(value)
        value["feature_names"] = tuple(value["feature_names"])
        for key in ("center", "scale", "coefficients"):
            value[key] = np.array(value[key], dtype=float)
        return cls(**value)


class CandidatePolicy:
    def __init__(self, horizon: int, forecasts: Sequence[RoutingDemandForecast], kind: str,
                 model: RidgeValueModel | None = None):
        if kind not in {"baseline", "analytic", "timed", "direct", "residual"}:
            raise ValueError("Unknown policy")
        if kind in {"direct", "residual"} and (model is None or model.kind != kind):
            raise ValueError("A matching frozen model is required")
        self.horizon, self.forecasts, self.kind, self.model = horizon, tuple(forecasts), kind, model

    def __call__(self, state: Snapshot, candidates: tuple[RouteCandidate, ...]) -> RouteCandidate:
        if not candidates:
            raise ValueError("No authorized candidates")
        if self.kind == "baseline" or len(candidates) == 1:
            return candidates[0]
        timed = TimedAnalyticEvaluator(self.horizon, self.forecasts)
        if self.kind == "analytic":
            scores = [timed._base(state).absolute(state, c) for c in candidates]
        elif self.kind == "timed":
            scores = [timed.absolute(state, c) for c in candidates]
        else:
            features = [timed.features(state, c) for c in candidates]
            scores = [self.model.score_features(f, features[0]) for f in features]
        return candidates[min(range(len(candidates)), key=lambda i: (scores[i], i))]


class ForecastRolloutPolicy:
    """Extra-compute reference using a published forecast, never the true tape."""

    def __init__(self, horizon: int, forecasts: Sequence[RoutingDemandForecast], generator_factory):
        self.horizon, self.forecasts, self.generator_factory = horizon, tuple(forecasts), generator_factory
        self.rollout_count = 0

    def values(self, state: Snapshot, candidates: tuple[RouteCandidate, ...]) -> list[float]:
        from .runtime import Simulation
        future = tuple(Bag(f"projected:{unit_id}", f.node, f.destination, f.at, f.deadline)
                       for f in active_forecasts(state, self.forecasts) for unit_id in f.unit_ids)
        engine = Simulation(state, future, route_mode="next_edge", generator_factory=self.generator_factory,
                            search_horizon=max(1, self.horizon - state.now), candidate_count=4)
        engine.observe()
        values = [engine.branch(c).advance(self.horizon).total_cost for c in candidates]
        self.rollout_count += len(values)
        return values

    def __call__(self, state: Snapshot, candidates: tuple[RouteCandidate, ...]) -> RouteCandidate:
        if len(candidates) == 1:
            return candidates[0]
        values = self.values(state, candidates)
        return candidates[min(range(len(candidates)), key=lambda i: (values[i], i))]
