"""Declared continuation x tie ablation, with a common empty-action domain.

This is a development mechanism comparison prompted by the complete earlier
matrix, not an independent confirmation or a robust-control implementation.
The earliest proxy keeps planning20 and K4, unlike the older reference's
planning40/K1 proxy.  Actual outer routing remains timed for all four cells.
"""
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path

from .empty_improvement import (EmptyImprovementSettings, OneStepEmptyPrebalancer,
    build_empty_improvement_engine, slow_after_context)
from .phase4_control import digest
from .prebalance_reference import _action_key
from .role_coverage import CursorSimulation, VisibleDecisionContext
from .routing_cache_contract import CACHE_CONTRACT


@dataclass(frozen=True)
class EmptyFactorial:
    continuation: str = "timed_greedy"
    tie: str = "incumbent"

    def __post_init__(self):
        if self.continuation not in ("timed_greedy", "earliest_reactive"):
            raise ValueError("unknown empty proxy continuation")
        if self.tie not in ("incumbent", "fewest_physical"):
            raise ValueError("unknown empty proxy tie rule")

    @property
    def policy_id(self):
        return self.continuation + "__" + self.tie


FACTORS = tuple(EmptyFactorial(continuation, tie)
    for continuation in ("timed_greedy", "earliest_reactive")
    for tie in ("incumbent", "fewest_physical"))
SETTINGS = EmptyImprovementSettings(score_horizon=40, max_rollouts=12)


class FactorialEmptyPrebalancer(OneStepEmptyPrebalancer):
    def __init__(self, *args, factors=EmptyFactorial(), **kwargs):
        if not isinstance(factors, EmptyFactorial):
            raise TypeError("factors must be a validated EmptyFactorial")
        self.factors = factors
        super().__init__(*args, **kwargs)

    def _project(self, state, forecasts, proxy, next_slow):
        if self.factors.continuation == "timed_greedy":
            return super()._project(state, forecasts, proxy, next_slow)
        spec = replace(self.spec, routing="baseline", predictive=False)
        original = slow_after_context(self.spec, next_slow)
        context = VisibleDecisionContext(original.cursor, None, CACHE_CONTRACT)
        return CursorSimulation.from_visible(state, context, proxy, spec, forecasts)

    def _prefer_complete(self, cost, sequence, ordinal, best_cost, best_sequence, best_ordinal):
        if cost < best_cost - 1e-9:
            return True
        if self.factors.tie == "incumbent" or abs(cost - best_cost) > 1e-9:
            return False
        return (len(sequence), _action_key(sequence), ordinal) < (
            len(best_sequence), _action_key(best_sequence), best_ordinal)

    def plan(self, snapshot, forecasts):
        plan = super().plan(snapshot, forecasts)
        plan.diagnostics.update(method="empty_continuation_tie_factorial",
            factorial=asdict(self.factors), tie_tolerance=1e-9,
            continuation=("timed_routing_and_original_greedy_at_future_slow_triggers"
                if self.factors.continuation == "timed_greedy" else
                "first_of_normal_K4_routing_and_reactive_dispatch_without_future_slow_control"),
            proxy_route_search_horizon=self.spec.planning_horizon,
            proxy_fast_candidate_count=self.spec.candidate_count,
            interpretation="all_four_predeclared_cells_are_development_mechanism_ablation_not_confirmation")
        return plan


def build_empty_factorial_engine(scene, factors=EmptyFactorial(), *, spec=None, settings=SETTINGS):
    engine = build_empty_improvement_engine(scene, spec, settings=settings)
    prior = engine.slow_controller.controller
    engine.slow_controller.controller = FactorialEmptyPrebalancer(spec=prior.spec,
        settings=settings, generator_factory=prior.generator_factory, factors=factors)
    contract = engine.control_contract
    contract["continuation"].update(prebalancer="FactorialEmptyPrebalancer", empty_factorial=asdict(factors))
    contract["continuation"]["implementation_sha256"]["empty_factorial.py"] = sha256(Path(__file__).read_bytes()).hexdigest()
    contract["continuation_sha256"] = digest(contract["continuation"])
    contract.pop("contract_sha256", None)
    contract["contract_sha256"] = digest(contract)
    engine.slow_controller.contract = engine.route_selector.contract = contract
    return engine
