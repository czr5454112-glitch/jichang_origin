"""Reachable decision boundaries, first-prefix intervention and exact replay."""
from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, InFlight, Network, Node, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator, ExecutionValidator, Simulation


def state_fixture(*, no_wait_j=False):
    nodes = {name: Node(name, name, name, 5, not (name == "J" and no_wait_j))
             for name in ("A", "J", "K", "B")}
    edges = (Edge("A-J", "A", "J", 2), Edge("J-B", "J", "B", 2),
             Edge("J-K", "J", "K", 2), Edge("K-B", "K", "B", 3),
             Edge("B-J", "B", "J", 2), Edge("J-A", "J", "A", 2))
    bag = Bag("initial", "A", "B", 0, 30)
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                    {"tray": Tray("tray", "A", "loaded", bag.bag_id)}, {bag.bag_id: bag},
                    module=FixedLocalModule(unload_ticks=2, hold_by_node={"B": 3, "J": 7}))


def make_sim(mode="whole_route"):
    simulation = Simulation(state_fixture(), (Bag("next", "B", "A", 2, 35),), route_mode=mode)
    visible = simulation.observe()
    candidate = CandidateGenerator(horizon=30).generate(visible, "initial", "tray", k=1)[0]
    assert simulation.intervene(candidate).accepted
    return simulation


@pytest.mark.parametrize("mode", ["whole_route", "next_edge"])
@pytest.mark.parametrize("pause", [0, 1, 2, 4, 6, 8, 9, 12])
def test_checkpoint_resume_matches_uninterrupted_trace_ledger_and_cost(mode, pause):
    full = make_sim(mode).advance(20)
    paused = make_sim(mode)
    interim = paused.advance(pause)
    checkpoint = paused.checkpoint()
    restored = Simulation.from_checkpoint(checkpoint)
    assert restored.result() == interim
    resumed = restored.advance(20)
    assert resumed == full
    assert resumed.trace == full.trace
    assert resumed.cost_components == full.cost_components
    assert resumed.final_snapshot == full.final_snapshot


def test_repeated_pause_at_same_tick_neither_consumes_future_nor_duplicates_events():
    simulation = make_sim("next_edge")
    first = simulation.advance(2)
    assert simulation.advance(2) == first
    assert simulation.advance(2) == first
    assert sum(event["event"] == "bag_arrival" for event in first.trace) == 1
    assert Simulation.from_checkpoint(simulation.checkpoint()).advance(20) == make_sim("next_edge").advance(20)


def test_reachable_intermediate_snapshot_retains_loaded_bag_without_local_hold():
    simulation = make_sim("next_edge")
    result = simulation.advance(2)
    tray = result.final_trays["tray"]
    assert tray.node == "J" and tray.mode == "loaded" and tray.bag_id == "initial"
    assert tray.available_at == 2
    assert "initial" not in result.completed
    assert "tray" not in result.final_snapshot.plans
    visible = simulation.observe()
    candidates = CandidateGenerator().generate(visible, "initial", "tray", k=2)
    assert candidates
    branch = simulation.branch(candidates[-1])
    assert "tray" not in simulation.state.plans
    assert "tray" in branch.state.plans


def test_next_edge_intervention_differs_from_whole_route_intervention():
    state = state_fixture()
    candidates = CandidateGenerator(horizon=30).generate(state, "initial", "tray", k=2)
    assert len(candidates) == 2 and candidates[0].legs[0] == candidates[1].legs[0]
    next_values, whole_values = [], []
    for candidate in candidates:
        for mode, values in (("next_edge", next_values), ("whole_route", whole_values)):
            simulation = Simulation(state, route_mode=mode)
            simulation.observe()
            assert simulation.intervene(candidate).accepted
            values.append(simulation.advance(7).total_cost)
    assert next_values[0] == next_values[1]
    assert whole_values[0] != whole_values[1]


def test_non_waitable_chain_is_an_indivisible_safe_prefix():
    state = state_fixture(no_wait_j=True)
    candidate = CandidateGenerator(horizon=30).generate(state, "initial", "tray", k=2)[1]
    simulation = Simulation(state, route_mode="next_edge")
    simulation.observe()
    assert simulation.intervene(candidate).accepted
    plan = simulation.state.plans["tray"]
    assert tuple(leg.edge_id for leg in plan.legs) == ("A-J", "J-K")
    assert plan.prefix_only and plan.destination_node == "K"
    mid = simulation.advance(2)
    assert mid.final_trays["tray"].node is None
    assert simulation.advance(4).final_trays["tray"].node == "K"


def test_in_flight_intervention_cannot_revoke_existing_or_old_movement():
    simulation = make_sim("next_edge")
    initial = state_fixture()
    candidate = CandidateGenerator().generate(initial, "initial", "tray", k=1)[0]
    simulation.advance(1)
    candidate = replace(candidate, dependency_version=simulation.state.version)
    assert simulation.intervene(candidate).reason == "entered_edge_irrevocable"
    old = initial.clone()
    old.now = 1
    old.trays["tray"] = Tray("tray", None, "in_transit", "initial")
    old.old_in_transit = (InFlight("tray", "A-J", 0, 2),)
    old_sim = Simulation(old, route_mode="next_edge")
    rejected = old_sim.intervene(replace(candidate, dependency_version=0))
    assert rejected.reason == "old_in_transit_irrevocable"


def test_callback_observations_hide_future_and_are_isolated():
    seen = []

    def selector(snapshot, candidates):
        assert all(bag.arrival <= snapshot.now for bag in snapshot.bags.values())
        assert not hasattr(snapshot, "pending_arrivals")
        assert not hasattr(snapshot, "future_bags")
        seen.append((snapshot.now, tuple(snapshot.bags)))
        snapshot.module.hold_by_node["B"] = 500
        snapshot.trays.clear()
        return candidates[0]

    simulation = Simulation(state_fixture(), (Bag("secret", "B", "A", 10, 30),),
                            route_selector=selector, route_mode="next_edge")
    simulation.advance(5)
    assert seen and all("secret" not in ids for _, ids in seen)
    assert simulation.state.module.hold_ticks("B") == 3
    assert simulation.state.trays
    assert simulation.policy_stats["selection_calls"] > 0
    assert simulation.policy_stats["selection_ms"] >= 0


def test_checkpoint_isolation_includes_future_tape_and_module_dictionaries():
    simulation = make_sim("next_edge")
    checkpoint = simulation.checkpoint()
    checkpoint.pending_arrivals.clear()
    checkpoint.state.module.hold_by_node["B"] = 100
    assert simulation.advance(3).final_snapshot.bags["next"].arrival == 2
    assert simulation.state.module.hold_ticks("B") == 3


def test_slow_controller_runs_after_loaded_routes_and_commits_through_owner():
    state = state_fixture()
    state.trays["spare"] = Tray("spare", "B")
    calls = []

    def slow(snapshot):
        calls.append(snapshot.now)
        assert "tray" in snapshot.plans
        if snapshot.now:
            return ()
        proposal = CandidateGenerator(horizon=20).generate_empty(snapshot, "spare", "A")[0]
        assert ExecutionValidator().commit(snapshot, proposal).accepted
        return (proposal,)

    simulation = Simulation(state, slow_controller=slow)
    result = simulation.advance(1)
    assert calls == [0]
    assert result.policy_stats["slow_commits"] == 1
    assert any(event["event"] == "slow_commit" for event in result.trace)


def test_slow_controller_cannot_change_fixed_module():
    def bad(snapshot):
        snapshot.module.hold_by_node["B"] = 1000
        return ()

    simulation = Simulation(state_fixture(), slow_controller=bad)
    with pytest.raises(ValueError, match="outside ExecutionValidator"):
        simulation.advance(1)
    assert simulation.state.module.hold_ticks("B") == 3


def test_factory_injection_and_observer_snapshot_boundary():
    made, observed = [], []

    def factory(*, horizon):
        made.append(horizon)
        return CandidateGenerator(horizon=horizon)

    def observer(snapshot):
        observed.append(snapshot)

    simulation = Simulation(state_fixture(), generator_factory=factory, observer=observer, search_horizon=25)
    simulation.advance(1)
    assert made == [25]
    assert observed[0].trays["tray"].mode == "loaded"
    assert "tray" not in observed[0].plans
    observed[0].trays.clear()
    assert simulation.state.trays


def test_prefix_internal_record_cannot_be_submitted_as_a_free_forged_witness():
    simulation = make_sim("next_edge")
    prefix = simulation.state.plans["tray"]
    assert prefix.prefix_only
    assert ExecutionValidator().validate(state_fixture(), prefix).reason == "prefix_requires_full_witness"


def test_reactive_empty_dispatch_switch_survives_checkpoint():
    state = state_fixture()
    state.trays = {"tray": Tray("tray", "B")}
    state.bags = {}
    future = (Bag("need", "A", "B", 1, 20),)
    simulation = Simulation(state, future, reactive_empty_dispatch=False)
    simulation.advance(2)
    result = Simulation.from_checkpoint(simulation.checkpoint()).advance(8)
    assert result.final_trays["tray"].node == "B"
    assert result.cost_components["empty_distance"] == 0
    assert result.waiting_bag_ids == ("need",)
