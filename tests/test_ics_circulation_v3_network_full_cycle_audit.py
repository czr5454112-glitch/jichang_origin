"""Independent negative controls for the full-ledger drain certificate."""
from dataclasses import asdict, replace
from types import SimpleNamespace

import pytest

from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, Network, Node, Reservation, Snapshot, Tray)
from scripts.experiments.ics_circulation_v3.network_full_cycle import (
    branch_full_cycle, compare_old_result, cycle_state, forecast_expiry)
from scripts.experiments.ics_circulation_v3.network_role_labels import (
    SearchBudget, branch_network_decision, collect_network_decisions)
from scripts.experiments.ics_circulation_v3.phase4_control import ControlSpec, build_engine
from scripts.experiments.ics_circulation_v3.role_coverage import checkpoint_fingerprint
from scripts.experiments.ics_circulation_v3.runtime import INFINITY, Simulation


def network():
    return Network({n: Node(n, n, "p", 3) for n in ("L", "J", "U")},
        {"LJ": Edge("LJ", "L", "J", 2), "JU": Edge("JU", "J", "U", 2),
         "UL": Edge("UL", "U", "L", 2)})


def empty_state(now=0):
    return Snapshot(now, network(), {"tray": Tray("tray", "L")}, {})


def sample_with(forecasts=(), future=(), module=FixedLocalModule()):
    state = Snapshot(0, network(), {"tray": Tray("tray", "L", "loaded", "seen")},
        {"seen": Bag("seen", "L", "U", 0, 40)}, module=module)
    scene = SimpleNamespace(name="independent_drain_audit", initial=state,
                            forecasts=forecasts, future_bags=future, horizon=12)
    spec = ControlSpec(planning_horizon=20, slow_period=2, expansion_limit=1000)
    collection = collect_network_decisions(scene, spec=spec,
        budget=SearchBudget(100, 100000, 30), bands=(0,))
    assert collection["metadata"]["status"] == "reached_horizon"
    return collection["samples"][0]


def test_empty_observed_result_is_not_full_ledger_completion():
    future = Bag("unobserved", "L", "U", 90, 120)
    engine = Simulation(empty_state(), (future,))
    assert engine.result().uncompleted_bag_ids == ()
    assert engine.result().cost_components["terminal_backlog"] == 0
    diagnostic = cycle_state(engine, (future.bag_id,), 0)
    assert diagnostic["unobserved_task_ids"] == diagnostic["pending_arrival_ids"] == ["unobserved"]
    assert not diagnostic["task_complete"] and not diagnostic["transport_drained"]


@pytest.mark.parametrize("obligation", ["hold", "empty_target", "reservation"])
def test_zero_terminal_penalties_do_not_erase_residual_physical_obligations(obligation):
    state = empty_state(8)
    if obligation == "hold":
        state.trays["tray"] = replace(state.trays["tray"], mode="holding", available_at=11)
    elif obligation == "empty_target":
        state.empty_targets["tray"] = "U"
    else:
        state.reservations = (Reservation("node:L", 8, 12, "tray"),)
    engine = Simulation(state, reactive_empty_dispatch=False)
    result = engine.result()
    assert result.cost_components["terminal_backlog"] == result.cost_components["terminal_inflight"] == 0
    diagnostic = cycle_state(engine, (), 0)
    assert diagnostic["task_complete"] and not diagnostic["transport_drained"]


def test_future_ghost_publication_can_move_tray_after_h80_appears_drained():
    # This public forecast never materializes in the true event tape. Its later
    # publication still legitimately causes an irrevocable empty transfer.
    ghost = RoutingDemandForecast("ghost", "L", "U", 100, 130, published_at=85)
    sample = sample_with((ghost,))
    checkpoint, candidate = sample["checkpoint"], sample["pool"][0]
    before = checkpoint_fingerprint(checkpoint)
    old = branch_network_decision(checkpoint, candidate, (), horizon_ticks=80,
        budget=SearchBudget(1000, 1000000, 30))["result"]
    outcome = branch_full_cycle(checkpoint, candidate, (), old_result=old,
        budget=SearchBudget(1000, 1000000, 30), tail_cap=60)
    assert outcome["status"] == "controller_quiescent"
    assert outcome["old80_comparison"]["equal"]
    old_cycle = outcome["endpoints"]["80"]["cycle"]
    assert old_cycle["task_complete"] and old_cycle["transport_drained"]
    assert not old_cycle["forecast_expired"]
    assert outcome["last_cycle_state"]["forecast_expired_at"] == 146
    assert outcome["stopped_at"] >= 148
    assert outcome["milestones"]["controller_quiescent"]["actual_slow_triggers_since"] >= 1
    result = outcome["result"]
    assert result.final_trays["tray"].node == "L"
    assert result.cost_components["empty_distance"] > old.cost_components["empty_distance"]
    assert set(result.completed) == {"seen"} and "ghost:0" not in result.final_snapshot.bags
    assert any(e["event"] == "slow_commit" and e["time"] >= 85 for e in result.trace)
    assert checkpoint_fingerprint(checkpoint) == before


def test_late_unadmitted_protected_task_remains_in_completion_denominator():
    state = empty_state(8)
    state.bags["protected"] = Bag("protected", "L", "U", 0, 3, protected=True)
    state.trays["tray"] = replace(state.trays["tray"], mode="loaded", bag_id="protected")
    engine = Simulation(state, reactive_empty_dispatch=False)
    engine.policy_stats["protected_unadmitted_decisions"] = 4
    diagnostic = cycle_state(engine, ("protected",), 0)
    assert not diagnostic["task_complete"]
    assert diagnostic["protected_observed"] == diagnostic["protected_late"] == 1
    assert diagnostic["protected_completed"] == 0
    assert diagnostic["protected_unadmitted_decisions"] == 4


def test_saved_h80_comparison_ignores_timing_only_and_checks_search_counts():
    original = asdict(Simulation(empty_state()).result())
    measured = asdict(Simulation(empty_state()).result())
    measured["policy_stats"]["generation_ms"] += 12345
    assert compare_old_result(original, measured)["equal"]
    measured["policy_stats"]["generation_calls"] += 1
    comparison = compare_old_result(original, measured)
    assert not comparison["equal"] and comparison["different_fields"] == ["policy_stats"]


def test_forecast_expiry_includes_later_cancellation_publication_without_mutation():
    original = RoutingDemandForecast("revision", "L", "U", 4, 40, published_at=0)
    cancellation = replace(original, count=0, published_at=100)
    engine = build_engine(empty_state(), (original, cancellation), (), ControlSpec())
    before = engine.slow_controller.next_trigger_at
    assert forecast_expiry(engine) == 161
    assert engine.slow_controller.forecast_publications == (original, cancellation)
    assert engine.slow_controller.next_trigger_at == before


def test_idle_stock_materialized_by_another_trays_commit_is_not_pending_transport():
    # Validator.commit persists every OTHER tray's current-node parking slot.
    # With two trays this remains after the moving tray's own plan finishes.
    state = empty_state()
    state.trays["other"] = Tray("other", "U")
    engine = Simulation(state, reactive_empty_dispatch=False)
    options = engine._generator.generate_empty(engine.state, "tray", "J", 1)
    assert options
    assert engine.intervene(options[0]).accepted
    engine.advance(10)
    assert any(r.tray_id == "other" and r.end == INFINITY for r in engine.state.reservations)
    diagnostic = cycle_state(engine, (), 0)
    assert diagnostic["task_complete"] and diagnostic["transport_drained"]


@pytest.mark.parametrize("resource,start,end", [
    ("node:U", 0, INFINITY),  # Parking for the wrong physical node.
    ("node:L", 9, INFINITY),  # A future reservation, not current inventory.
    ("node:L", 0, 12),        # A finite accepted reservation.
    ("reception:L", 0, INFINITY),
    ("edge:LJ", 0, INFINITY),
])
def test_idle_inventory_exception_does_not_hide_other_reservation_types(resource, start, end):
    state = empty_state(8)
    state.reservations = (Reservation(resource, start, end, "tray"),)
    engine = Simulation(state, reactive_empty_dispatch=False)
    assert not cycle_state(engine, (), 0)["transport_drained"]
