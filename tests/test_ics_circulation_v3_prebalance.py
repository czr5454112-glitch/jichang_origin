from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import permutations
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.experiments.ics_circulation_v3.evaluation import ForecastDemand
from scripts.experiments.ics_circulation_v3.model import Bag, FixedLocalModule, Tray
from scripts.experiments.ics_circulation_v3.prebalance import (
    PredictivePrebalancer, known_supply, synthetic_prebalance_fixtures,
)
from scripts.experiments.ics_circulation_v3.runtime import (
    CandidateGenerator, ExecutionValidator, Simulation, assert_invariants, simulate,
)


def _controller(forecasts=(), **kwargs) -> PredictivePrebalancer:
    return PredictivePrebalancer(forecasts, planning_budget_ms=None, **kwargs)


def test_long_connection_dispatches_before_visible_demand_and_reduces_wait() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    controller = _controller(fixture.forecasts)
    plan = controller.plan(state, fixture.forecasts)
    assert not state.plans and state.version == 0  # Planning has no physical side effects.
    assert len(plan.proposals) == 1
    route = plan.proposals[0]
    assert route.bag_id is None and route.tray_id == "donor"
    assert route.legs[0].depart == 0 and route.usable_at == 8
    accepted = controller(state)
    assert len(accepted) == 1 and state.version == 1
    assert_invariants(state)
    pre = simulate(state, None, fixture.future_bags, fixture.horizon)
    reactive = simulate(fixture.snapshot, None, fixture.future_bags, fixture.horizon)
    assert pre.cost_components["tray_wait"] < reactive.cost_components["tray_wait"]
    assert set(pre.final_trays) == set(state.trays)


def test_old_arrival_counts_hold_before_available_and_prevents_duplicate() -> None:
    fixture = synthetic_prebalance_fixtures()[1]
    supplies = {event.tray_id: event for event in known_supply(fixture.snapshot)}
    assert supplies["old"].at == 8  # Physical arrival at 6, fixed local hold for 2.
    plan = _controller().plan(fixture.snapshot, fixture.forecasts)
    assert plan.proposals == ()
    assert plan.diagnostics["search_calls"] == 0


def test_source_future_demand_and_minimum_stock_prevent_export() -> None:
    fixture = synthetic_prebalance_fixtures()[2]
    plan = _controller().plan(fixture.snapshot, fixture.forecasts)
    assert not plan.proposals
    assert any("prefix" in row["reason"] for row in plan.diagnostics["donor_rejections"])
    minimum = synthetic_prebalance_fixtures()[0]
    state = minimum.snapshot.clone()
    state.module = FixedLocalModule(export_min_stock=1)
    result = _controller().plan(state, minimum.forecasts)
    assert not result.proposals
    assert result.diagnostics["donor_rejections"][0]["reason"].startswith("source_zone_prefix_min_stock")


def test_committed_loaded_release_is_credited_only_after_unload_and_hold() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    bag = Bag("loaded:bag", "A", "B", 0, 30)
    state.bags[bag.bag_id] = bag
    state.trays["loaded"] = Tray("loaded", "A", "loaded", bag.bag_id)
    state.module = FixedLocalModule(unload_ticks=2, hold_by_node={"B": 3})
    route = CandidateGenerator().generate(state, bag.bag_id, "loaded", k=1)[0]
    assert ExecutionValidator().commit(state, route).accepted
    events = [event for event in known_supply(state) if event.tray_id == "loaded"]
    assert len(events) == 1 and events[0].at == 13
    plan = _controller().plan(state, (ForecastDemand("B", 13),))
    assert not plan.proposals


def test_receiver_capacity_and_candidate_identity_are_revalidated() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.network.nodes["B"] = replace(state.network.nodes["B"], capacity=1)
    state.trays["receiver:stock"] = Tray("receiver:stock", "B")
    plan = _controller().plan(state, (ForecastDemand("B", 8, count=2),))
    assert not plan.proposals
    assert any(row["reason"] == "no_feasible_candidate" for row in plan.diagnostics["candidate_rejections"])

    class WrongIdentity:
        def generate_empty(self, snapshot, tray_id, destination, k=1):
            valid = CandidateGenerator().generate_empty(snapshot, tray_id, destination, k)[0]
            return (replace(valid, tray_id="nonexistent"),)

    fresh = synthetic_prebalance_fixtures()[0]
    result = _controller(generator_factory=WrongIdentity).plan(fresh.snapshot, fresh.forecasts)
    assert not result.proposals
    assert result.diagnostics["candidate_rejections"][0]["reason"] == "candidate_identity_or_destination_mismatch"


def test_temporal_forecast_filter_has_explicit_reasons() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.now = 10
    forecasts = (ForecastDemand("B", 18, published_at=11),
                 ForecastDemand("B", 10, published_at=0),
                 ForecastDemand("B", 18, published_at=0),
                 ForecastDemand("B", 80, published_at=10))
    result = _controller(max_forecast_age=5).plan(state, forecasts)
    assert not result.proposals
    assert {row["reason"] for row in result.diagnostics["ignored_forecasts"]} == {
        "future_publication", "expired_arrival_use_visible_queue", "stale_publication", "beyond_planning_horizon",
    }


def test_visible_queue_works_without_forecast_or_reactive_controller() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.bags["visible"] = Bag("visible", "B", "A", 0, 25)
    result = _controller().plan(state, ())
    assert len(result.proposals) == 1
    assert result.proposals[0].usable_at == 8
    assert result.diagnostics["demand"][0]["source"] == "visible_queue:visible"


def test_logistics_zone_defines_cross_region_not_control_partition() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.network.nodes["B"] = replace(state.network.nodes["B"], logistics_zone="domestic")
    assert state.network.nodes["A"].control_partition != state.network.nodes["B"].control_partition
    result = _controller().plan(state, fixture.forecasts)
    assert not result.proposals and result.diagnostics["search_calls"] == 0


def test_sequential_commit_versions_and_no_duplicate_irrevocable_transfer() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.trays["donor:2"] = Tray("donor:2", "A")
    forecasts = (ForecastDemand("B", 16, count=2),)
    controller = _controller(forecasts)
    accepted = controller(state)
    assert len(accepted) == 2
    assert [candidate.dependency_version for candidate in accepted] == [0, 1]
    assert len({candidate.tray_id for candidate in accepted}) == 2
    assert controller(state) == ()
    assert len(state.plans) == 2
    assert_invariants(state)


def test_latest_valid_departure_and_explicit_search_bound() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    result = _controller(max_candidates=1).plan(fixture.snapshot, (ForecastDemand("B", 12),))
    assert result.proposals[0].legs[0].depart == 4
    assert result.proposals[0].usable_at == 12
    assert result.diagnostics["search_calls"] <= 1


def test_forecast_reversal_does_not_recall_committed_tray_and_can_hurt() -> None:
    fixture = synthetic_prebalance_fixtures()[3]
    state = fixture.snapshot.clone()
    controller = _controller(fixture.forecasts)
    committed = controller(state)
    assert committed and committed[0].legs[0].depart == 0
    controller.forecasts = ()  # Forecast correction has no cancellation permission.
    assert not controller(state)
    assert state.plans["donor"] == committed[0]
    pre = simulate(state, None, fixture.future_bags, fixture.horizon)
    reactive = simulate(fixture.snapshot, None, fixture.future_bags, fixture.horizon)
    assert pre.cost_components["tray_wait"] > reactive.cost_components["tray_wait"]


def test_invalid_forecast_and_unknown_future_input_not_accepted() -> None:
    fixture = synthetic_prebalance_fixtures()[0]
    with pytest.raises(ValueError, match="node/count"):
        _controller().plan(fixture.snapshot, (ForecastDemand("unknown", 8),))
    with pytest.raises(TypeError):
        _controller().plan(fixture.snapshot, fixture.forecasts, future_bags=fixture.future_bags)


def test_intermediate_committed_prefix_is_not_empty_release() -> None:
    from scripts.experiments.ics_circulation_v3.model import Edge

    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.network.edges.pop("A-B")
    state.network.edges["A-C"] = Edge("A-C", "A", "C", 2)
    state.network.edges["C-B"] = Edge("C-B", "C", "B", 6)
    bag = Bag("loaded:prefix", "A", "B", 0, 30)
    state.bags[bag.bag_id] = bag
    state.trays["donor"] = Tray("donor", "A", "loaded", bag.bag_id)
    route = CandidateGenerator().generate(state, bag.bag_id, "donor", k=1)[0]
    assert ExecutionValidator().commit(state, route, route_mode="next_edge").accepted
    assert state.plans["donor"].prefix_only
    assert known_supply(state) == ()


@pytest.mark.parametrize("fixture_index", range(4))
def test_complete_callback_loop_preserves_physical_invariants(fixture_index: int) -> None:
    fixture = synthetic_prebalance_fixtures()[fixture_index]
    engine = Simulation(fixture.snapshot, fixture.future_bags,
                        slow_controller=_controller(fixture.forecasts), route_mode="whole_route")
    result = engine.advance(fixture.horizon)
    assert result.invariant_checks > fixture.horizon
    assert set(result.final_trays) == set(fixture.snapshot.trays)
    assert_invariants(result.final_snapshot)
    assert result.policy_stats["slow_calls"] > 0
    if fixture_index == 0:
        assert result.policy_stats["slow_commits"] == 1
    elif fixture_index == 3:
        assert result.policy_stats["slow_commits"] == 2  # Outbound commitment, then corrective return.
    else:
        assert result.policy_stats["slow_commits"] == 0


@dataclass(frozen=True)
class _RevisionForecast:
    forecast_id: str = "revision"
    node: str = "B"
    at: int = 8
    count: int = 1
    published_at: int = 0
    unit_ids: tuple[str, ...] = ("observed",)
    destination: str = "A"
    deadline: int = 30


@pytest.mark.parametrize("changed_field", ("unit_ids", "node", "at", "count", "destination", "deadline", "identity_mode"))
def test_same_publication_semantic_conflicts_rejected_independent_of_order_and_newer_revision(changed_field):
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.now = 1
    state.bags["observed"] = Bag("observed", "B", "A", 0, 30)
    first = _RevisionForecast()
    changes = {
        "unit_ids": {"unit_ids": ("not_observed",)},
        "node": {"node": "A"}, "at": {"at": 9},
        "count": {"count": 2, "unit_ids": ("observed", "not_observed")},
        "destination": {"destination": "C"}, "deadline": {"deadline": 31},
    }
    second = (SimpleNamespace(**{key: value for key, value in vars(first).items() if key != "unit_ids"})
              if changed_field == "identity_mode" else replace(first, **changes[changed_field]))
    newer = replace(first, at=10, published_at=1)
    for records in (tuple(permutations((first, second))) + tuple(permutations((first, second, newer)))):
        with pytest.raises(ValueError, match="conflicting forecast values for one identity/publication"):
            _controller().plan(state, records)
    assert not state.plans  # Even a conflict hidden behind a newer row is atomic failure.


def test_identical_duplicate_forecast_is_allowed_and_counted_once():
    fixture = synthetic_prebalance_fixtures()[0]
    forecast = _RevisionForecast(unit_ids=("pending",))
    single = _controller().plan(fixture.snapshot, (forecast,))
    duplicate = _controller().plan(fixture.snapshot, (forecast, replace(forecast)))
    assert duplicate.proposals == single.proposals
    assert duplicate.diagnostics["demand"] == single.diagnostics["demand"]
    assert len(duplicate.diagnostics["accepted_forecasts"]) == 1


def test_explicit_implicit_and_reordered_same_identity_set_are_equivalent_duplicates():
    fixture = synthetic_prebalance_fixtures()[0]
    state = fixture.snapshot.clone()
    state.trays["donor:second"] = Tray("donor:second", "A")
    implicit = _RevisionForecast(forecast_id="same", count=2, at=16, unit_ids=())
    explicit = replace(implicit, unit_ids=("same:0", "same:1"))
    reordered = replace(implicit, unit_ids=("same:1", "same:0"))
    reference = _controller().plan(state, (implicit,))
    for records in permutations((implicit, explicit, reordered)):
        plan = _controller().plan(state, records)
        assert plan.proposals == reference.proposals
        assert plan.diagnostics["demand"] == reference.diagnostics["demand"]
        assert len(plan.diagnostics["accepted_forecasts"]) == 1
