"""Small adversarial integrations, not production capacity/fault evidence."""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.experiments.ics_circulation_v3.evaluation import ForecastDemand
from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.prebalance import (
    PredictivePrebalancer, known_supply, synthetic_prebalance_fixtures,
)
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.runtime import (
    CandidateGenerator, ExecutionValidator, Simulation, assert_invariants,
)


def _regional():
    return RegionalCandidateGenerator(horizon=40, deadline_ms=None)


def _predictive(forecasts=(), **kwargs):
    return PredictivePrebalancer(forecasts, planning_budget_ms=None,
                                generator_factory=_regional, **kwargs)


def _junction_state(*, junction_wait=False, protected=True) -> Snapshot:
    nodes = {
        name: Node(name, "destination" if name == "B" else "source", name,
                   capacity=4 if name in {"B", "J"} else 2,
                   can_wait=name != "J" or junction_wait)
        for name in ("A", "C", "J", "B")
    }
    edges = (Edge("A-J", "A", "J", 1), Edge("C-J", "C", "J", 1),
             Edge("J-B", "J", "B", 3, capacity=1), Edge("B-A", "B", "A", 3),
             Edge("B-C", "B", "C", 3))
    bag = Bag("protected:loaded", "A", "B", 0, 5, protected=protected)
    return Snapshot(0, Network(nodes, {edge.edge_id: edge for edge in edges}),
                    {"loaded": Tray("loaded", "A", "loaded", bag.bag_id),
                     "empty": Tray("empty", "C")}, {bag.bag_id: bag})


@pytest.mark.parametrize("route_mode", ("whole_route", "next_edge"))
@pytest.mark.parametrize("regional", (False, True))
def test_simultaneous_demands_empty_loaded_bottleneck_and_no_wait_junction(route_mode, regional):
    state = _junction_state()
    future = (Bag("future:1", "B", "A", 4, 20), Bag("future:2", "B", "C", 4, 20))
    factory = _regional if regional else lambda: CandidateGenerator(horizon=40)
    controller = PredictivePrebalancer((ForecastDemand("B", 4, 2),),
                                      generator_factory=factory, planning_budget_ms=None)
    engine = Simulation(state, future, route_mode=route_mode,
                        generator_factory=factory, slow_controller=controller,
                        reactive_empty_dispatch=False)
    result = engine.advance(22)
    assert result.completed["protected:loaded"] <= 5
    assert set(result.completed) == {"protected:loaded", "future:1", "future:2"}
    bottleneck_departures = [event["time"] for event in result.trace
                             if event["event"] == "depart" and event["edge_id"] == "J-B"]
    assert bottleneck_departures[:2] == [1, 4]
    assert all(right - left >= 3 for left, right in zip(bottleneck_departures, bottleneck_departures[1:]))
    for detail in (row for call in engine.slow_controller.history for row in call["proposal_details"]):
        assert detail["first_depart"] >= 3  # Upstream waiting; never wait inside J.
    assert result.policy_stats["slow_commits"] == 1
    assert_invariants(result.final_snapshot)


def test_next_edge_protected_deadline_survives_competing_slow_whole_route():
    state = _junction_state(junction_wait=True)
    engine = Simulation(state, (), route_mode="next_edge", generator_factory=_regional,
                        slow_controller=_predictive((ForecastDemand("B", 4),)),
                        reactive_empty_dispatch=False)
    result = engine.advance(10)
    assert result.completed.get("protected:loaded", 99) <= 5
    assert not any(event["event"] == "prefix_arrive" and event["tray_id"] == "loaded"
                   for event in result.trace)


def _pending_empty_state() -> Snapshot:
    nodes = {name: Node(name, "destination" if name == "B" else "source", name, capacity=4)
             for name in ("A", "J", "C", "B")}
    edges = (Edge("A-J", "A", "J", 2), Edge("J-B", "J", "B", 2),
             Edge("C-B", "C", "B", 6), Edge("J-A", "J", "A", 2), Edge("B-A", "B", "A", 4))
    state = Snapshot(0, Network(nodes, {edge.edge_id: edge for edge in edges}),
                     {"traveling": Tray("traveling", "A"), "spare": Tray("spare", "C")}, {})
    candidate = _regional().generate_empty(state, "traveling", "B", k=1)[0]
    assert ExecutionValidator().commit(state, candidate, route_mode="next_edge").accepted
    assert state.empty_targets["traveling"] == "B" and state.plans["traveling"].prefix_only
    return state


def test_multistep_accepted_empty_transfer_is_not_duplicated_by_prebalance():
    state = _pending_empty_state()
    # A prefix is not a timed terminal release, but it is an existing transfer
    # obligation. Do not send 'spare' to cover the same one-tray forecast.
    assert all(event.tray_id != "traveling" for event in known_supply(state))
    plan = _predictive().plan(state, (ForecastDemand("B", 6),))
    assert not plan.proposals
    engine = Simulation(state, (Bag("future", "B", "A", 6, 20),),
                        route_mode="next_edge", generator_factory=_regional,
                        slow_controller=_predictive((ForecastDemand("B", 6),)),
                        reactive_empty_dispatch=False)
    result = engine.advance(18)
    assert result.completed["future"] <= 20
    assert result.policy_stats["slow_commits"] == 0
    assert result.final_trays["spare"].node == "C"
    assert len([event for event in result.trace if event["event"] == "empty_continue"]) == 1


def test_owner_rejects_redirect_of_accepted_empty_target_at_safe_boundary():
    engine = Simulation(_pending_empty_state(), (), route_mode="next_edge",
                        generator_factory=_regional, reactive_empty_dispatch=False)
    engine.advance(2)
    state = engine.observe()
    assert state.trays["traveling"].node == "J"
    assert state.empty_targets["traveling"] == "B"
    options = CandidateGenerator().generate_empty(state, "traveling", "A", k=1)
    # A generator may prefilter the request; if it proposes a redirect, the
    # owner must still reject it independently.
    if options:
        assert not ExecutionValidator().commit(state, options[0]).accepted
    assert state.empty_targets["traveling"] == "B"
    assert "traveling" not in state.plans


@dataclass(frozen=True)
class IdentifiedForecast:
    forecast_id: str
    node: str
    at: int
    count: int = 1
    published_at: int = 0
    unit_ids: tuple[str, ...] = ()


def test_early_observed_units_remove_future_forecast_double_count():
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.now = 4
    state.trays["donor:2"] = Tray("donor:2", "A")
    state.bags["B:0"] = Bag("B:0", "B", "A", 4, 25)
    forecast = IdentifiedForecast("B", "B", 6)
    plan = _predictive().plan(state, (forecast,))
    assert sum(event["count"] for event in plan.diagnostics["demand"]) == 1
    assert plan.diagnostics["accepted_forecasts"][0]["observed_units_removed"] == ("B:0",)
    assert len(plan.proposals) == 1
    aggregate = _predictive().plan(state, (ForecastDemand("B", 6),))
    assert sum(event["count"] for event in aggregate.diagnostics["demand"]) == 2
    assert "observed_units_removed" not in aggregate.diagnostics["accepted_forecasts"][0]


def test_source_identity_aware_forecast_not_double_reserved_after_early_queue():
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.now = 2
    state.trays["source:second"] = Tray("source:second", "A")
    state.bags["local:0"] = Bag("local:0", "A", "B", 2, 30)
    forecasts = (IdentifiedForecast("local", "A", 4), IdentifiedForecast("remote", "B", 10))
    plan = _predictive().plan(state, forecasts)
    assert len(plan.proposals) == 1  # One source tray retained for the real queue.
    assert plan.proposals[0].tray_id in {"donor", "source:second"}


class RevisingController(PredictivePrebalancer):
    def __init__(self):
        super().__init__((IdentifiedForecast("remote", "B", 8),),
                         generator_factory=_regional, planning_budget_ms=None)
        self.applied_revision = False

    def __call__(self, snapshot):
        if snapshot.now >= 2 and not self.applied_revision:
            self.forecasts = (IdentifiedForecast("remote", "B", 8, count=0, published_at=2),
                              IdentifiedForecast("A:unexpected", "A", 4, published_at=2,
                                                 unit_ids=("A:unexpected",)))
            self.applied_revision = True
        return super().__call__(snapshot)


def test_midcourse_forecast_revision_and_checkpoint_preserve_policy_state():
    fixture = synthetic_prebalance_fixtures()[3]
    engine = Simulation(fixture.snapshot, fixture.future_bags,
                        slow_controller=RevisingController(), generator_factory=_regional,
                        reactive_empty_dispatch=False)
    engine.advance(3)
    checkpoint = engine.checkpoint()
    resumed = Simulation.from_checkpoint(checkpoint)
    assert resumed.slow_controller.applied_revision
    assert resumed.slow_controller is not engine.slow_controller
    assert resumed.slow_controller.history is not engine.slow_controller.history
    assert len(resumed.slow_controller.history) == len(engine.slow_controller.history) == 3
    assert resumed.state.plans["donor"] == engine.state.plans["donor"]
    uninterrupted = engine.advance(32)
    replay = resumed.advance(32)
    assert replay == uninterrupted
    assert replay.cost_components["tray_wait"] > 0
    assert resumed.slow_controller.forecasts == engine.slow_controller.forecasts
    assert resumed.slow_controller.last_diagnostics["snapshot_time"] == 31


def test_zero_capacity_is_rejected_not_silently_upgraded_by_regional_routing():
    state = _junction_state()
    state.network.edges["J-B"] = replace(state.network.edges["J-B"], capacity=0)
    with pytest.raises(ValueError, match="capacity"):
        _regional().generate(state, "protected:loaded", "loaded", k=1)
    assert state.network.edges["J-B"].capacity == 0
    assert not CandidateGenerator(horizon=10).generate(state, "protected:loaded", "loaded", k=1)
