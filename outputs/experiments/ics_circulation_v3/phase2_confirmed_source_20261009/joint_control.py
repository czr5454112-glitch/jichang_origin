"""Six matched policies for routing and forecast prebalancing coordination."""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .learning import CandidatePolicy
from .prebalance import PredictivePrebalancer
from .routing import RegionalCandidateGenerator
from .runtime import Simulation


@dataclass(frozen=True)
class JointPolicy:
    routing: str
    balancing: str
    predictive: bool
    coordination_order: str

    @property
    def policy_id(self) -> str:
        return f"{self.routing}__{self.balancing}"


def policies() -> tuple[JointPolicy, ...]:
    return tuple(JointPolicy(routing, balancing, predictive, order)
                 for routing in ("baseline", "timed")
                 for balancing, predictive, order in (
                     ("reactive_only", False, "route_then_prebalance"),
                     ("predictive_route_first", True, "route_then_prebalance"),
                     ("predictive_prebalance_first", True, "prebalance_then_route")))


def regional_factory(horizon=80):
    # Deterministic search/count budgets remain active. Wall-clock cutoffs are
    # disabled in this matched experiment to avoid machine-load confounding.
    return RegionalCandidateGenerator(horizon=horizon, deadline_ms=None)


class LoggedCandidatePolicy(CandidatePolicy):
    """Runtime-only action audit; no future tape or training-side information."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.history = []

    def __call__(self, snapshot, candidates):
        chosen = super().__call__(snapshot, candidates)
        self.history.append({"time": snapshot.now, "dependency_version": snapshot.version,
                             "visible_bag_ids": sorted(snapshot.bags),
                             "chosen_candidate_id": chosen.candidate_id,
                             "candidates": [asdict(candidate) for candidate in candidates]})
        return chosen


def build_engine(scene, future_bags, policy: JointPolicy) -> Simulation:
    selector = LoggedCandidatePolicy(scene.horizon, scene.forecasts, kind=policy.routing)
    controller = PredictivePrebalancer(
        scene.forecasts, planning_horizon=scene.horizon, planning_budget_ms=None,
        generator_factory=lambda: regional_factory(scene.horizon),
    ) if policy.predictive else None
    return Simulation(
        scene.initial, future_bags, route_mode="next_edge", generator_factory=regional_factory,
        route_selector=selector, slow_controller=controller, search_horizon=scene.horizon,
        candidate_count=4, reactive_empty_dispatch=True, coordination_order=policy.coordination_order,
    )
