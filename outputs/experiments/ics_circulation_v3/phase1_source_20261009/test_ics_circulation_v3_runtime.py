"""Physical boundary tests for the standalone, synthetic circulation kernel."""
from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, InFlight, Leg, Network, Node, Reservation,
    RouteCandidate, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.runtime import (
    CandidateGenerator, ExecutionValidator, assert_invariants, simulate,
)


def network(*, wait_j=True, reception_hold=0):
    nodes = {name: Node(name, name, "control", capacity=4, can_wait=wait_j if name == "J" else True)
             for name in ("A", "J", "B")}
    edges = (Edge("A-J", "A", "J", 1), Edge("J-B", "J", "B", 2),
             Edge("A-B", "A", "B", 5), Edge("B-J", "B", "J", 2), Edge("J-A", "J", "A", 1))
    return Network(nodes, {edge.edge_id: edge for edge in edges})


def loaded_state(**kwargs):
    bag = Bag("bag0", "A", "B", 0, 20)
    return Snapshot(0, network(), {"tray0": Tray("tray0", "A", "loaded", "bag0")},
                    {bag.bag_id: bag}, **kwargs)


def first(state):
    return CandidateGenerator(horizon=20).generate(state, "bag0", "tray0", k=1)[0]


def test_identity_conservation_and_arrival_is_not_availability():
    state = loaded_state(module=FixedLocalModule(unload_ticks=2, hold_by_node={"B": 4}))
    candidate = first(state)
    assert candidate.legs[-1].arrive == 3
    assert candidate.unload_complete == 5
    assert candidate.usable_at == 9
    at_arrival = simulate(state, candidate, (), 3)
    assert at_arrival.final_trays["tray0"].mode == "unloading"
    assert at_arrival.uncompleted_bag_ids == ("bag0",)
    at_unload = simulate(state, candidate, (), 5)
    assert at_unload.completed == {"bag0": 5}
    assert at_unload.final_trays["tray0"].mode == "holding"
    assert at_unload.final_trays["tray0"].bag_id is None
    at_release = simulate(state, candidate, (), 9)
    assert at_release.final_trays["tray0"].mode == "empty"
    assert set(at_release.final_trays) == set(state.trays)
    assert set(at_release.final_snapshot.bags) == set(state.bags)


def test_no_tray_preserves_future_arrivals_and_accrued_wait():
    state = Snapshot(0, network(), {}, {})
    bag = Bag("unserved", "A", "B", 2, 4)
    result = simulate(state, None, (bag,), 8)
    assert result.waiting_bag_ids == result.uncompleted_bag_ids == ("unserved",)
    assert result.cost_components == {
        "tray_wait": 6, "nonprotected_tardiness": 4, "empty_distance": 0,
        "terminal_backlog": 1, "terminal_inflight": 0,
    }
    assert result.total_cost == 20
    assert state.bags == {}


def test_old_empty_transit_is_irrevocable_and_respects_receiving_hold():
    state = Snapshot(1, network(), {"old": Tray("old", None, "in_transit")}, {},
                     old_in_transit=(InFlight("old", "A-B", -2, 3),),
                     module=FixedLocalModule(hold_by_node={"B": 4}))
    request = RouteCandidate("illegal", None, "old", (), 1, 1, 0, "illegal", destination_node="B")
    assert ExecutionValidator().validate(state, request).reason == "old_in_transit_irrevocable"
    arrival = simulate(state, None, (), 3)
    assert arrival.final_trays["old"].mode == "holding"
    assert arrival.final_trays["old"].available_at == 7
    assert simulate(state, None, (), 7).final_trays["old"].mode == "empty"
    assert state.old_in_transit[0].arrive == 3


def test_old_loaded_transit_unloads_then_holds_at_destination():
    bag = Bag("oldbag", "A", "B", 0, 20)
    state = Snapshot(1, network(), {"old": Tray("old", None, "in_transit", "oldbag")}, {"oldbag": bag},
                     old_in_transit=(InFlight("old", "A-B", -2, 3),),
                     module=FixedLocalModule(unload_ticks=2, hold_by_node={"B": 4}))
    arrival = simulate(state, None, (), 3)
    assert arrival.final_trays["old"].mode == "unloading"
    unloaded = simulate(state, None, (), 5)
    assert unloaded.completed == {"oldbag": 5}
    assert unloaded.final_trays["old"].mode == "holding"
    assert simulate(state, None, (), 9).final_trays["old"].mode == "empty"


def test_reservation_conflict_and_half_open_boundary():
    state = loaded_state()
    candidate = first(state)
    state.trays["blocker"] = Tray("blocker", "B")
    state.reservations = (Reservation("edge:A-J", 0, 1, "blocker"),)
    assert ExecutionValidator().validate(state, candidate).reason.startswith("capacity:edge:A-J")
    state.reservations = (Reservation("edge:A-J", -1, 0, "blocker"),)
    assert ExecutionValidator().validate(state, candidate).accepted


def test_commit_revalidates_version_and_does_not_repeat_capacity():
    state = loaded_state()
    candidate = first(state)
    validator = ExecutionValidator()
    assert validator.commit(state, candidate).accepted
    accepted_slots = state.reservations
    assert validator.commit(state, candidate).reason == "stale_version"
    assert state.reservations == accepted_slots
    updated = replace(candidate, dependency_version=state.version)
    assert validator.commit(state, updated).reason == "accepted_itinerary_irrevocable"
    assert len(state.plans) == 1


def test_clone_isolates_all_mutable_nested_state():
    state = loaded_state(module=FixedLocalModule(hold_by_node={"B": 2}))
    clone = state.clone()
    clone.module.hold_by_node["B"] = 100
    clone.network.nodes["A"] = replace(clone.network.nodes["A"], capacity=99)
    clone.trays.clear()
    assert state.module.hold_by_node["B"] == 2
    assert state.network.nodes["A"].capacity == 4
    assert len(state.trays) == 1


def test_no_wait_node_keeps_arrival_label_and_waits_upstream():
    state = loaded_state()
    state.network = network(wait_j=False)
    state.trays["blocker"] = Tray("blocker", "B")
    state.reservations = (Reservation("edge:J-B", 0, 3, "blocker"),)
    bad = RouteCandidate("bad", "bag0", "tray0", (Leg("A-J", 0, 1), Leg("J-B", 3, 5)), 6, 6, 0, "bad")
    assert ExecutionValidator().validate(state, bad).reason == "waiting_forbidden"
    candidates = CandidateGenerator(horizon=10).generate(state, "bag0", "tray0", k=2)
    via_j = next(c for c in candidates if c.legs[0].edge_id == "A-J")
    assert via_j.legs[0].depart == 2
    assert via_j.legs[0].arrive == via_j.legs[1].depart == 3


def test_source_identity_and_protected_deadline_are_hard_checks():
    state = loaded_state()
    candidate = first(state)
    state.trays["tray0"] = replace(state.trays["tray0"], mode="empty", bag_id=None)
    assert ExecutionValidator().validate(state, candidate).reason == "source_not_carrying_bag"
    state.trays["tray0"] = Tray("tray0", "A", "loaded", "bag0")
    state.bags["bag0"] = replace(state.bags["bag0"], deadline=3, protected=True)
    assert ExecutionValidator().validate(state, candidate).reason == "protected_deadline"


def test_contiguous_empty_edges_are_each_charged_once():
    state = Snapshot(0, network(), {"t": Tray("t", "B")}, {})
    bag = Bag("need", "A", "B", 0, 30)
    result = simulate(state, None, (bag,), 4)
    assert result.cost_components["empty_distance"] == 3
    entered = [event["edge_id"] for event in result.trace if event["event"] == "depart"]
    assert entered.count("B-J") == entered.count("J-A") == 1


def test_bounded_search_exhaustion_is_explicit():
    state = loaded_state()
    generator = CandidateGenerator(expansion_limit=1, horizon=10)
    assert generator.generate(state, "bag0", "tray0") == ()
    assert generator.last_search_status == "exhausted"


def test_fifo_continuation_cannot_see_later_future_arrivals():
    state = Snapshot(0, network(), {"t": Tray("t", "B")}, {})
    left = simulate(state, None, (Bag("later", "A", "B", 6, 20),), 9)
    right = simulate(state, None, (Bag("later", "B", "A", 6, 20),), 9)
    assert [event for event in left.trace if event["time"] < 6] == [event for event in right.trace if event["time"] < 6]


def test_node_and_receiving_capacity_not_only_edges():
    state = loaded_state(module=FixedLocalModule(reception_capacity=1, hold_by_node={"B": 3}))
    candidate = first(state)
    state.trays["holding"] = Tray("holding", "B", "holding", available_at=8)
    assert ExecutionValidator().validate(state, candidate).reason.startswith("capacity:reception:B")
    state.trays["holding"] = Tray("holding", "B")
    state.network.nodes["B"] = replace(state.network.nodes["B"], capacity=1)
    assert ExecutionValidator().validate(state, candidate).reason.startswith("capacity:node:B")


def test_invalid_moving_identity_is_detected():
    state = Snapshot(0, network(), {"bad": Tray("bad", None, "in_transit")}, {})
    with pytest.raises(AssertionError, match="no physical edge witness"):
        assert_invariants(state)


def test_export_stock_accounts_for_already_accepted_empty_departures():
    state = Snapshot(0, network(), {name: Tray(name, "A") for name in ("one", "two")}, {},
                     module=FixedLocalModule(export_min_stock=1, reception_capacity=2))
    generator = CandidateGenerator(horizon=10)
    outgoing = generator.generate_empty(state, "one", "B")[0]
    assert ExecutionValidator().commit(state, outgoing).accepted
    assert generator.generate_empty(state, "two", "B") == ()


def test_concurrent_commits_have_one_version_winner():
    from concurrent.futures import ThreadPoolExecutor

    state = loaded_state()
    candidate = first(state)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: ExecutionValidator().commit(state, candidate), range(2)))
    assert sum(result.accepted for result in results) == 1
    assert state.version == 1
    assert len(state.plans) == 1


def test_rejected_commit_is_a_noop():
    state = loaded_state()
    candidate = replace(first(state), dependency_version=99)
    before = state.clone()
    assert not ExecutionValidator().commit(state, candidate).accepted
    assert state == before
