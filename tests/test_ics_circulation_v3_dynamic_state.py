"""W1 conditional-release lifecycle and explicitly authorized suffix updates."""
from dataclasses import asdict, replace
import json

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, InFlight, Leg, Network, Node, RouteCandidate, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.prebalance import conditional_supply, known_supply
from scripts.experiments.ics_circulation_v3.runtime import (
    CandidateGenerator, ExecutionValidator, Simulation, actual_action_key,
    assert_invariants, effective_reservations, invalidate_conditional_forecasts,
    refresh_conditional_forecasts,
)


def fixture(*, long=1, no_wait=False, protected=False):
    nodes = {n: Node(n, n, n, capacity=3, can_wait=n != "M" or not no_wait)
             for n in ("S", "M", "V", "G", "U")}
    edges = (Edge("S-M", "S", "M", long), Edge("M-G", "M", "G", 1),
             Edge("M-V", "M", "V", 2), Edge("V-G", "V", "G", 1),
             Edge("S-U", "S", "U", 2), Edge("U-G", "U", "G", 2),
             Edge("G-S", "G", "S", 2))
    bag = Bag("bag", "S", "G", 0, 40, protected)
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                    {"tray": Tray("tray", "S", "loaded", "bag")}, {"bag": bag},
                    module=FixedLocalModule(unload_ticks=1), replaceable_trays=("tray",))


def proposal(state, path=("S-M", "M-G"), *, departure=None, name="candidate", tray_id="tray", bag_id="bag"):
    tick = state.now if departure is None else departure
    legs = []
    for edge_id in path:
        arrival = tick + state.network.edges[edge_id].travel_time
        legs.append(Leg(edge_id, tick, arrival))
        tick = arrival
    destination = state.bags[bag_id].destination if bag_id else state.network.edges[path[-1]].target
    unload = tick + (state.module.unload_ticks if bag_id else 0)
    return RouteCandidate(name, bag_id, tray_id, tuple(legs), unload,
                          unload + state.module.hold_ticks(destination), state.version, name,
                          destination_node=destination)


def committed(*, mode="whole_route", **kwargs):
    state = fixture(**kwargs)
    assert ExecutionValidator().commit(state, proposal(state), route_mode=mode).accepted
    return state


def test_prefix_has_separate_identified_conditional_release_and_no_firm_supply():
    state = committed(mode="next_edge")
    assert state.plans["tray"].prefix_only
    assert known_supply(state) == ()
    prediction, = conditional_supply(state)
    assert (prediction.tray_id, prediction.bag_id, prediction.node, prediction.at) == ("tray", "bag", "G", 3)
    f = state.conditional_forecasts["tray"]
    assert f.revision == 1 and f.parent_forecast_id is None
    assert tuple(x.edge_id for x in f.remaining_legs) == ("S-M", "M-G")
    assert {d.resource for d in f.dependencies} >= {"edge:M-G", "module:G"}
    # Existing artifact writers can still serialize the default permission and
    # forecast fields without a custom set/datetime JSON encoder.
    assert json.loads(json.dumps(asdict(state)))["replaceable_trays"] == ["tray"]


def test_progress_resume_and_realization_never_double_count_the_tray():
    engine = Simulation(committed(mode="next_edge"), route_mode="next_edge")
    branch = engine.fork()
    engine.advance(1)
    visible = engine.observe()
    f = visible.conditional_forecasts["tray"]
    assert [leg.edge_id for leg in f.remaining_legs] == ["M-G"]
    assert f.parent_forecast_id == "tray:forecast:1" and f.reason == "physical_progress"
    assert len(conditional_supply(visible)) == 1 and not known_supply(visible)
    checkpoint = engine.checkpoint()
    resumed = Simulation.from_checkpoint(checkpoint).advance(5)
    full = branch.advance(5)
    assert resumed == full
    assert resumed.final_snapshot.conditional_forecasts["tray"].status == "realized"
    assert conditional_supply(resumed.final_snapshot) == ()
    assert len(known_supply(resumed.final_snapshot)) == 1
    checkpoint.state.conditional_forecasts.clear()
    assert engine.state.conditional_forecasts


def test_model_dependency_change_invalidates_without_automatic_resurrection():
    state = committed(mode="next_edge")
    state.module.hold_by_node["G"] = 3
    assert conditional_supply(state) == ()  # Read-only consumers reject stale evidence too.
    refresh_conditional_forecasts(state)
    current = state.conditional_forecasts["tray"]
    assert current.status == "invalid" and current.reason == "dependency_changed:module:G"
    state.module.hold_by_node.clear()
    refresh_conditional_forecasts(state)
    assert state.conditional_forecasts["tray"] == current
    assert not conditional_supply(state)


def test_explicit_fault_only_invalidates_matching_predictions_and_preserves_commitment():
    state = committed(mode="next_edge")
    plan, slots = state.plans["tray"], state.reservations
    invalidate_conditional_forecasts(state, "observed_future_edge_fault", resources=("edge:M-G",))
    invalid = state.conditional_forecasts["tray"]
    assert invalid.status == "invalid" and invalid.parent_forecast_id == "tray:forecast:1"
    assert state.plans["tray"] == plan and state.reservations == slots
    refresh_conditional_forecasts(state)
    assert state.conditional_forecasts["tray"] == invalid and not conditional_supply(state)


def test_new_downstream_commit_invalidates_conditional_calendar_not_firm_prefix():
    state = committed(mode="next_edge")
    state.trays["other"] = Tray("other", "M")
    other = proposal(state, ("M-G",), departure=1, tray_id="other", bag_id=None)
    assert ExecutionValidator().commit(state, other).accepted
    assert state.conditional_forecasts["tray"].status == "invalid"
    assert "capacity:edge:M-G@1" in state.conditional_forecasts["tray"].reason
    assert state.plans["tray"].prefix_only
    assert not conditional_supply(state)
    assert [s.tray_id for s in known_supply(state)] == ["other"]


def test_action_key_ignores_candidate_names_but_includes_conditional_suffix():
    state = fixture()
    direct = proposal(state)
    renamed = replace(direct, candidate_id="other-name", baseline_id="other-baseline", is_baseline=True)
    detour = proposal(state, ("S-M", "M-V", "V-G"))
    assert direct.legs[0] == detour.legs[0]
    assert actual_action_key(state, direct) == actual_action_key(state, renamed)
    assert actual_action_key(state, direct) != actual_action_key(state, detour)
    a, b = Simulation(state, route_mode="next_edge"), Simulation(state, route_mode="next_edge")
    a.intervene(direct)
    b.intervene(detour)
    assert a.state.plans["tray"].legs == b.state.plans["tray"].legs
    assert a.state.conditional_forecasts["tray"].usable_at != b.state.conditional_forecasts["tray"].usable_at
    assert a.checkpoint().state.conditional_forecasts != b.checkpoint().state.conditional_forecasts
    assert a.fork().state.conditional_forecasts == a.state.conditional_forecasts


def test_replace_valid_old_route_on_explicit_authorization_only():
    owner = ExecutionValidator()
    state = committed()
    before = state.clone()
    context = owner.prepare_replacement(state, "tray")
    assert context.anchor_node == "S" and context.anchor_time == 0 and not context.frozen_legs
    assert context.planning_snapshot.plans == {} and state == before
    candidate = proposal(context.planning_snapshot, ("S-U", "U-G"))
    assert owner.validate_replacement(state, context, candidate).accepted and state == before
    assert owner.replace_suffix(state, context, candidate).accepted
    assert tuple(leg.edge_id for leg in state.plans["tray"].legs) == ("S-U", "U-G")
    assert not any(r.resource in {"edge:S-M", "edge:M-G"} for r in state.reservations)
    assert_invariants(state)


@pytest.mark.parametrize("change", ["not_authorized", "protected", "no_plan", "old_flight", "empty"])
def test_replacement_permission_denials_preserve_old_state(change):
    state = committed()
    if change == "not_authorized":
        state.replaceable_trays = ()
    elif change == "protected":
        state.bags["bag"] = replace(state.bags["bag"], protected=True)
    elif change == "no_plan":
        state.plans.clear()
    elif change == "old_flight":
        state.plans.clear()
        state.old_in_transit = (InFlight("tray", "S-M", 0, 1),)
    else:
        state.plans["tray"] = replace(state.plans["tray"], bag_id=None)
        state.empty_targets["tray"] = "G"
    before = state.clone()
    with pytest.raises(ValueError):
        ExecutionValidator().prepare_replacement(state, "tray")
    assert state == before


@pytest.mark.parametrize("fault", ["closed", "missing"])
def test_future_old_suffix_fault_allows_legal_bypass_without_touching_entered_edge(fault):
    engine = Simulation(committed(long=5))
    engine.advance(1)
    state = engine.state
    if fault == "closed":
        state.network.edges["M-G"] = replace(state.network.edges["M-G"], capacity=0)
    else:
        del state.network.edges["M-G"]
    state.version += 1
    before = state.clone()
    owner = ExecutionValidator()
    context = owner.prepare_replacement(state, "tray")
    assert (context.anchor_node, context.anchor_time) == ("M", 5)
    assert context.frozen_legs == before.plans["tray"].legs[:1]
    candidate = proposal(context.planning_snapshot, ("M-V", "V-G"))
    assert owner.replace_suffix(state, context, candidate).accepted
    assert state.trays["tray"] == before.trays["tray"]  # still inside S-M
    assert state.plans["tray"].legs[0] == before.plans["tray"].legs[0]
    assert any(r.resource == "edge:S-M" and r.start <= 1 and r.end == 5 for r in effective_reservations(state))
    result = engine.advance(12)
    assert result.completed == {"bag": 9} and not result.uncompleted_bag_ids


def test_nonwaitable_chain_is_frozen_until_next_safe_point_during_replacement():
    state = fixture(long=4, no_wait=True)
    owner = ExecutionValidator()
    assert owner.commit(state, proposal(state, ("S-M", "M-V", "V-G"))).accepted
    engine = Simulation(state)
    engine.advance(1)
    context = owner.prepare_replacement(engine.state, "tray")
    assert (context.anchor_node, context.anchor_time) == ("V", 6)
    assert tuple(l.edge_id for l in context.frozen_legs) == ("S-M", "M-V")
    candidate = proposal(context.planning_snapshot, ("V-G",), departure=8)
    assert owner.replace_suffix(engine.state, context, candidate).accepted
    assert engine.advance(4).final_trays["tray"].mode == "in_transit"
    assert engine.advance(6).final_trays["tray"].node == "V"
    assert engine.advance(12).completed == {"bag": 10}


@pytest.mark.parametrize("failure", ["stale", "identity", "edited_context", "capacity"])
def test_failed_replacement_never_releases_old_reservations_or_revises_forecast(failure):
    state = committed(mode="next_edge")
    owner = ExecutionValidator()
    if failure == "capacity":
        state.trays["blocker"] = Tray("blocker", "U")
        state.network.nodes["U"] = replace(state.network.nodes["U"], capacity=1)
    context = owner.prepare_replacement(state, "tray")
    candidate = proposal(context.planning_snapshot, ("S-U", "U-G"))
    if failure == "stale":
        state.version += 1
    elif failure == "identity":
        candidate = replace(candidate, bag_id="wrong")
    elif failure == "edited_context":
        context.planning_snapshot.module.hold_by_node["G"] = 5
    before = json.dumps(asdict(state), sort_keys=True)
    rejection = owner.replace_suffix(state, context, candidate, route_mode="next_edge")
    assert not rejection.accepted
    if failure == "capacity":
        assert "capacity:node:U" in rejection.reason
    assert json.dumps(asdict(state), sort_keys=True) == before


def test_replacement_next_edge_revises_forecast_chain_without_overlapping_supply():
    state = committed(mode="next_edge")
    old = state.conditional_forecasts["tray"]
    owner = ExecutionValidator()
    context = owner.prepare_replacement(state, "tray")
    candidate = proposal(context.planning_snapshot, ("S-U", "U-G"))
    assert owner.replace_suffix(state, context, candidate, route_mode="next_edge").accepted
    current = state.conditional_forecasts["tray"]
    assert current.parent_forecast_id == old.forecast_id and current.usable_at == 5
    assert state.forecast_history[-1] == old
    assert len(conditional_supply(state)) == 1 and known_supply(state) == ()
    before = state.clone()
    assert owner.replace_suffix(state, context, candidate).reason == "stale_replacement_context"
    assert state == before


def test_full_replacement_updates_firm_revision_to_new_eta_and_route():
    state = committed(mode="next_edge")
    owner = ExecutionValidator()
    old = state.conditional_forecasts["tray"]
    context = owner.prepare_replacement(state, "tray")
    candidate = proposal(context.planning_snapshot, ("S-U", "U-G"))
    assert owner.replace_suffix(state, context, candidate).accepted
    current = state.conditional_forecasts["tray"]
    assert current.status == "firm" and current.parent_forecast_id == old.forecast_id
    assert current.usable_at == 5 != old.usable_at
    assert current.witness_legs == candidate.legs and current.remaining_legs == candidate.legs
    assert known_supply(state)[0].at == current.usable_at
    assert not conditional_supply(state)


def test_future_anchor_generator_uses_isolated_view_and_rechecks_actual_resources():
    engine = Simulation(committed(long=5))
    engine.advance(2)
    owner = ExecutionValidator()
    state = engine.state
    context = owner.prepare_replacement(state, "tray")
    generated = CandidateGenerator(horizon=15).generate(context.planning_snapshot, "bag", "tray", k=2)
    assert len(generated) == 2 and all(c.legs[0].depart >= 5 for c in generated)
    assert owner.replace_suffix(state, context, generated[-1]).accepted
    assert engine.advance(15).completed == {"bag": 9}


def test_entered_edge_fault_is_explicitly_unsupported_not_silently_replanned():
    engine = Simulation(committed(long=5))
    engine.advance(1)
    engine.state.network.edges["S-M"] = replace(engine.state.network.edges["S-M"], capacity=0)
    before = engine.state.clone()
    with pytest.raises(ValueError, match="entered_or_uninterruptible_segment_changed"):
        ExecutionValidator().prepare_replacement(engine.state, "tray")
    assert engine.state == before
