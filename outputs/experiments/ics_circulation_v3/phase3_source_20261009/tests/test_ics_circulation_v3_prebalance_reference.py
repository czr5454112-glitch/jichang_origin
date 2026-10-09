from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.experiments.ics_circulation_v3.evaluation import ForecastDemand
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, InFlight, Network, Node, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.prebalance import PredictivePrebalancer
from scripts.experiments.ics_circulation_v3.prebalance_reference import BoundedForecastPrebalancer
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, Simulation, assert_invariants


def _generator():
    return RegionalCandidateGenerator(horizon=40, deadline_ms=None)


def _network(travel=2, capacity=2):
    nodes = {name: Node(name, "source" if name in {"A", "C"} else "target", name, capacity=5)
             for name in ("A", "B", "C")}
    edges = (Edge("A-B", "A", "B", travel, capacity), Edge("B-A", "B", "A", 1, capacity),
             Edge("old-C-B", "C", "B", 40, capacity))
    return Network(nodes, {edge.edge_id: edge for edge in edges})


def _reference(forecasts=(), **kwargs):
    return BoundedForecastPrebalancer(forecasts, generator_factory=_generator,
                                     proxy_destinations={"B": "A", "A": "B"},
                                     paths_per_request=1, **kwargs)


def test_no_transfer_is_scored_and_can_beat_greedy_under_same_forecast():
    nodes = {name: Node(name, "source" if name != "B" else "target", name, capacity=5)
             for name in ("A", "C", "J", "B")}
    edges = (Edge("A-J", "A", "J", 1), Edge("C-J", "C", "J", 1),
             Edge("J-B", "J", "B", 10), Edge("B-A", "B", "A", 1))
    bag = Bag("soft_loaded", "A", "B", 0, 12)
    state = Snapshot(0, Network(nodes, {edge.edge_id: edge for edge in edges}),
                     {"donor": Tray("donor", "C"), "loaded": Tray("loaded", "A", "loaded", bag.bag_id)},
                     {bag.bag_id: bag})
    forecast = (ForecastDemand("B", 2),)
    greedy = PredictivePrebalancer(forecast, generator_factory=_generator, planning_budget_ms=None)
    assert greedy.plan(state, forecast).proposals
    plan = _reference(forecast, score_horizon=30).plan(state, forecast)
    assert not plan.proposals
    actions = plan.diagnostics["scored_actions"]
    assert actions[0]["transfers"] == []
    assert plan.diagnostics["selected_proxy_cost"] == min(row["proxy_cost"] for row in actions)
    assert actions[0]["proxy_cost"] == pytest.approx(11.1)
    assert any(row["transfers"] and row["proxy_cost"] > actions[0]["proxy_cost"] for row in actions)
    assert not state.plans and state.version == 0


def test_joint_two_transfer_sequence_is_validated_and_committed_in_versions():
    state = Snapshot(0, _network(), {name: Tray(name, "A") for name in ("one", "two")}, {})
    forecasts = (ForecastDemand("B", 2, count=2),)
    controller = _reference(forecasts, score_horizon=12)
    plan = controller.plan(state, forecasts)
    assert len(plan.proposals) == 2
    assert [candidate.dependency_version for candidate in plan.proposals] == [0, 1]
    assert plan.diagnostics["selected_proxy_cost"] == pytest.approx(0.4)
    assert plan.diagnostics["rollout_calls"] <= controller.max_rollouts
    committed = controller(state)
    assert len(committed) == 2 and len(state.plans) == 2
    assert_invariants(state)


def test_tight_budget_keeps_no_transfer_and_discloses_unscored_actions():
    state = Snapshot(0, _network(), {"donor": Tray("donor", "A")}, {})
    forecasts = (ForecastDemand("B", 2),)
    plan = _reference(forecasts, max_rollouts=1, score_horizon=12).plan(state, forecasts)
    assert not plan.proposals
    assert plan.diagnostics["rollout_calls"] == 1
    assert plan.diagnostics["rollout_budget_exhausted"]
    assert plan.diagnostics["status"] == "partial_bounded_search"
    assert plan.diagnostics["unscored_enumerated_actions"] > 0


@pytest.mark.parametrize("protection", ("source_demand", "minimum_stock"))
def test_reference_uses_same_source_prefix_and_module_protection(protection):
    state = Snapshot(0, _network(), {"donor": Tray("donor", "A")}, {})
    forecasts = (ForecastDemand("B", 2),)
    if protection == "source_demand":
        forecasts += (ForecastDemand("A", 1),)
    else:
        state.module = FixedLocalModule(export_min_stock=1)
    greedy = PredictivePrebalancer(forecasts, generator_factory=_generator, planning_budget_ms=None)
    reference = _reference(forecasts)
    assert not greedy.plan(state, forecasts).proposals
    plan = reference.plan(state, forecasts)
    assert not plan.proposals and plan.diagnostics["rollout_calls"] == 0
    assert plan.diagnostics["donor_rejections"]


def test_proxy_uses_published_identity_destination_deadline_and_not_actual_future():
    state = Snapshot(4, _network(), {"donor": Tray("donor", "A")}, {})
    forecast = RoutingDemandForecast("known", "B", "A", 3, 15, published_at=0)
    controller = _reference((forecast,))
    diagnostics = {"accepted_forecasts": [], "ignored_forecasts": []}
    controller._demand(state, (forecast,), diagnostics)
    assert controller._proxy_future(state, (forecast,)) == (Bag("known:0", "B", "A", 5, 15),)
    unpublished = replace(forecast, forecast_id="unpublished", published_at=5)
    assert controller._proxy_future(state, (unpublished,)) == ()
    state.bags["known:0"] = Bag("known:0", "B", "A", 4, 15)
    assert controller._proxy_future(state, (forecast,)) == ()
    with pytest.raises(TypeError):
        controller.plan(state, (forecast,), future_bags=(Bag("truth", "A", "B", 9, 40),))


def test_missing_proxy_destination_fails_explicitly_instead_of_using_truth():
    state = Snapshot(0, _network(), {"donor": Tray("donor", "A")}, {})
    controller = BoundedForecastPrebalancer(generator_factory=_generator)
    with pytest.raises(ValueError, match="configured proxy destination"):
        controller.plan(state, (ForecastDemand("B", 2),))


def test_unadmitted_protected_load_blocks_reference_empty_actions():
    bag = Bag("hard", "A", "B", 0, 4, protected=True)
    state = Snapshot(0, _network(), {"loaded": Tray("loaded", "A", "loaded", "hard"),
                                    "donor": Tray("donor", "A")}, {"hard": bag})
    plan = _reference().plan(state, (ForecastDemand("B", 2, 2),))
    assert not plan.proposals
    assert plan.diagnostics["status"] == "no_transfer_protected_obligation_not_admitted"


def test_existing_transfer_is_irrevocable_and_not_duplicated():
    state = Snapshot(0, _network(), {"one": Tray("one", "A"), "two": Tray("two", "A")}, {})
    candidate = _generator().generate_empty(state, "one", "B", k=1)[0]
    assert ExecutionValidator().commit(state, candidate).accepted
    original = state.clone()
    plan = _reference().plan(state, (ForecastDemand("B", 2),))
    assert not plan.proposals
    assert state == original


def test_old_empty_arrival_covers_forecast_without_dispatching_spare():
    state = Snapshot(0, _network(), {"old": Tray("old", None, "in_transit"),
                                    "donor": Tray("donor", "A")}, {},
                     old_in_transit=(InFlight("old", "old-C-B", -38, 2),))
    original = state.clone()
    plan = _reference().plan(state, (ForecastDemand("B", 3),))
    assert not plan.proposals
    assert plan.diagnostics["rollout_calls"] == 0
    assert state == original


def test_zero_reception_permission_is_not_relaxed_by_reference():
    state = Snapshot(0, _network(), {"donor": Tray("donor", "A")}, {},
                     module=FixedLocalModule(reception_capacity=0))
    plan = _reference().plan(state, (ForecastDemand("B", 3),))
    assert not plan.proposals
    assert state.version == 0 and not state.plans


def test_accepted_protected_load_keeps_bottleneck_before_selected_empty():
    nodes = {name: Node(name, "target" if name == "B" else "source", name, capacity=5)
             for name in ("A", "C", "J", "B")}
    edges = (Edge("A-J", "A", "J", 1), Edge("C-J", "C", "J", 1),
             Edge("J-B", "J", "B", 3), Edge("B-A", "B", "A", 1))
    bag = Bag("hard", "A", "B", 0, 5, protected=True)
    state = Snapshot(0, Network(nodes, {edge.edge_id: edge for edge in edges}),
                     {"load": Tray("load", "A", "loaded", bag.bag_id),
                      "donor": Tray("donor", "C")}, {bag.bag_id: bag})
    load = _generator().generate(state, "hard", "load", k=1)[0]
    assert ExecutionValidator().commit(state, load).accepted
    original_load = state.plans["load"]
    controller = _reference((ForecastDemand("B", 5, count=2),), score_horizon=18)
    accepted = controller(state)
    assert state.plans["load"] == original_load
    occupied_until = next(leg.arrive for leg in load.legs if leg.edge_id == "J-B")
    for transfer in accepted:
        assert next(leg.depart for leg in transfer.legs if leg.edge_id == "J-B") >= occupied_until
    result = Simulation(state, generator_factory=_generator).advance(18)
    assert result.completed["hard"] <= bag.deadline
    assert_invariants(result.final_snapshot)


def test_reference_callback_runs_causally_and_checkpoint_restores_policy_state():
    state = Snapshot(0, _network(), {"donor": Tray("donor", "A")}, {})
    forecast = RoutingDemandForecast("future", "B", "A", 4, 15)
    actual = (Bag("future:0", "B", "A", 6, 15),)
    engine = Simulation(state, actual, generator_factory=_generator,
                        slow_controller=_reference((forecast,), score_horizon=16),
                        reactive_empty_dispatch=True)
    engine.advance(3)
    resumed = Simulation.from_checkpoint(engine.checkpoint())
    assert resumed.slow_controller is not engine.slow_controller
    result = engine.advance(18)
    replay = resumed.advance(18)
    assert result == replay
    assert result.completed["future:0"] <= 15
    assert set(result.final_trays) == {"donor"}


def test_runner_refuses_to_overwrite_any_existing_record(tmp_path):
    from scripts.experiments.ics_circulation_v3.run_prebalance_reference import run

    marker = tmp_path / "summary.json"
    marker.write_text("preserved", encoding="utf-8")
    with pytest.raises(ValueError, match="existing experiment records are immutable"):
        run(tmp_path, groups=0, diagnostic=True)
    assert marker.read_text(encoding="utf-8") == "preserved"
    assert list(tmp_path.iterdir()) == [marker]
