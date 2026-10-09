"""W2-start common causal controller construction for labels and deployment.

This connects existing controllers under an explicit contract. It is not a new
prebalancing optimizer, distributed controller or complete joint-MPC method.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from .learning import CandidatePolicy
from .conditional_evaluation import ConditionalCandidatePolicy
from .prebalance import PredictivePrebalancer
from .routing import RegionalCandidateGenerator
from .runtime import Simulation, actual_action_key


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ControlSpec:
    routing: str = "timed"
    predictive: bool = True
    reactive: bool = True
    slow_period: int = 2
    planning_horizon: int = 24
    route_mode: str = "next_edge"
    coordination_order: str = "route_then_prebalance"
    candidate_count: int = 4
    expansion_limit: int = 2000
    static_path_limit: int = 12
    local_label_limit: int = 3
    dynamic_local: bool = True

    def __post_init__(self):
        if self.routing not in {"baseline", "timed", "conditional_timed", "external"}:
            raise ValueError("routing must be baseline, timed, conditional_timed or explicit external selector")
        if any(type(value) is not int or value < 1 for value in (
                self.slow_period, self.planning_horizon, self.candidate_count, self.expansion_limit,
                self.static_path_limit, self.local_label_limit)):
            raise ValueError("control periods and search budgets must be positive integers")
        if self.route_mode not in {"whole_route", "next_edge"} or self.coordination_order not in {"route_then_prebalance", "prebalance_then_route"}:
            raise ValueError("invalid execution mode or coordination order")
        if type(self.predictive) is not bool or type(self.reactive) is not bool:
            raise ValueError("predictive and reactive toggles must be booleans")
        if self.dynamic_local is not True:
            raise ValueError("this phase4 builder requires the declared dynamic local generator")


@dataclass(frozen=True)
class GeneratorFactory:
    spec: ControlSpec

    def __call__(self, horizon=None):
        return RegionalCandidateGenerator(horizon=self.spec.planning_horizon if horizon is None else horizon,
            expansion_limit=self.spec.expansion_limit, static_path_limit=self.spec.static_path_limit,
            dynamic_local=self.spec.dynamic_local, local_label_limit=self.spec.local_label_limit, deadline_ms=None)


class LoggedSelector:
    def __init__(self, selector, contract):
        self.selector, self.contract, self.history = selector, contract, []

    def __call__(self, snapshot, candidates):
        chosen = self.selector(snapshot, candidates)
        self.history.append({"time": snapshot.now, "version": snapshot.version,
                             "bag_id": chosen.bag_id, "tray_id": chosen.tray_id,
                             "visible_bag_ids": sorted(snapshot.bags),
                             "candidate_count": len(candidates),
                             "distinct_interventions": len({actual_action_key(snapshot, item, route_mode=self.contract["spec"]["route_mode"]) for item in candidates}),
                             "candidates": [asdict(item) for item in candidates], "chosen": asdict(chosen)})
        return chosen


class PublishedRoutingSelector:
    """Synthetic publication gate; never pass later revisions into scoring."""
    def __init__(self, spec, forecasts):
        self.spec, self.forecast_publications = spec, tuple(forecasts)
        self.publication_history = []

    def __call__(self, snapshot, candidates):
        published = tuple(item for item in self.forecast_publications if item.published_at <= snapshot.now)
        self.publication_history.append({"time": snapshot.now,
                                         "published": [asdict(item) for item in published]})
        horizon = snapshot.now + self.spec.planning_horizon
        policy = (ConditionalCandidatePolicy(horizon, published) if self.spec.routing == "conditional_timed"
                  else CandidatePolicy(horizon, published, kind=self.spec.routing))
        return policy(snapshot, candidates)


class PeriodicSlowController:
    """Calls from the engine are not triggers; only scheduled ticks invoke plan."""
    def __init__(self, controller, *, period, first_trigger_at, contract, forecast_publications=()):
        if type(period) is not int or period < 1 or type(first_trigger_at) is not int:
            raise ValueError("period must be a positive integer and first trigger an integer tick")
        self.controller, self.period = controller, period
        self.next_trigger_at = first_trigger_at
        self.trigger_times, self.callback_times, self.history = [], [], []
        self.contract = contract
        self.forecast_publications = tuple(forecast_publications)

    def __call__(self, snapshot):
        self.callback_times.append(snapshot.now)
        if snapshot.now < self.next_trigger_at:
            return ()
        self.trigger_times.append(snapshot.now)
        # Preserve the phase of the independent slow clock if a restored or
        # externally advanced state skipped ticks; never run catch-up actions.
        self.next_trigger_at += ((snapshot.now - self.next_trigger_at) // self.period + 1) * self.period
        self.controller.forecasts = tuple(item for item in self.forecast_publications if item.published_at <= snapshot.now)
        proposals = self.controller(snapshot)
        self.history.append({"trigger_time": snapshot.now, "proposals": [asdict(item) for item in proposals],
                             "diagnostics": self.controller.last_diagnostics})
        return proposals


def control_contract(spec, forecasts, *, start_tick, selector_manifest=None):
    selector = ({"implementation": "PublishedRoutingSelector", "kind": spec.routing} if spec.routing != "external"
                else selector_manifest)
    if not isinstance(selector, dict) or not selector:
        raise ValueError("external selectors require a nonempty immutable selector_manifest")
    info = {"observable": "Snapshot only, including visible bags and published forecast revisions",
            "forecast_sha256": digest([asdict(forecast) for forecast in forecasts]),
            "future_tape_access": "event_engine_only_not_selector_or_slow_controller",
            "conditional_release_use": "optional_conditional_timed_route_scoring_only_existing_greedy_uses_firm_first_release",
            "forecast_publication_gate": "filter_on_actual_observed_snapshot_now_before_passing_to_scorers"}
    continuation = {"spec": asdict(spec), "selector": selector,
                    "prebalancer": "PredictivePrebalancer" if spec.predictive else None,
                    "slow_clock_phase": start_tick, "wall_clock_cutoffs": None,
                    "slow_candidate_budget": 32, "slow_proposal_budget": 8, "forecast_ttl": 60,
                    "permission_owner": "unchanged_ExecutionValidator", "local_module": "input_snapshot_fixed_module"}
    continuation["implementation_sha256"] = {
        name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
        for name in ("phase4_control.py", "conditional_evaluation.py", "learning.py", "prebalance.py",
                     "evaluation.py", "routing.py", "runtime.py", "model.py")}
    payload = {"schema": "ics_v3_phase4_control_contract_v1", "spec": asdict(spec),
               "information": info, "continuation": continuation,
               "information_sha256": digest(info), "continuation_sha256": digest(continuation)}
    payload["contract_sha256"] = digest(payload)
    return payload


def build_engine(initial, forecasts, future_bags, spec=ControlSpec(), *, route_selector=None,
                 selector_manifest=None, observer=None):
    """Both label branches and deployment must call this exact builder/spec.

    The tape is supplied solely to Simulation. No labels or tape-derived fields
    are accepted by either controller. External selector manifests are caller
    attestations; this helper cannot prove arbitrary callback code is causal.
    """
    forecasts = tuple(forecasts)
    if (spec.routing == "external") != (route_selector is not None):
        raise ValueError("external routing requires a selector; built-in modes forbid selector overrides")
    contract = control_contract(spec, forecasts, start_tick=initial.now, selector_manifest=selector_manifest)
    factory = GeneratorFactory(spec)
    selector = route_selector or PublishedRoutingSelector(spec, forecasts)
    slow = None
    if spec.predictive:
        controller = PredictivePrebalancer((), planning_horizon=spec.planning_horizon,
                                          planning_budget_ms=None, generator_factory=factory)
        slow = PeriodicSlowController(controller, period=spec.slow_period, first_trigger_at=initial.now,
                                      contract=contract, forecast_publications=forecasts)
    engine = Simulation(initial, future_bags, route_mode=spec.route_mode, generator_factory=factory,
                        route_selector=LoggedSelector(selector, contract), slow_controller=slow,
                        observer=observer, search_horizon=spec.planning_horizon,
                        candidate_count=spec.candidate_count, reactive_empty_dispatch=spec.reactive,
                        coordination_order=spec.coordination_order)
    engine.control_contract = contract  # Authoritative copy also lives in checkpointed selector/controller.
    return engine
