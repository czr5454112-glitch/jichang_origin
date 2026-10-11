"""Hand-computed on-carrier routing cases; no business-data thinning."""
from copy import deepcopy
from dataclasses import asdict, replace

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, Leg, Network, Node, Reservation, RouteCandidate, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.runtime import (
    CandidateGenerator, ExecutionValidator, INFINITY, candidate_reservations,
)
from scripts.experiments.ics_circulation_v3.storage_contracts import (
    StorageBag, StoragePlanningSnapshot, StorageProgress, StorageSnapshot, StorageWaypointContract,
)
from scripts.experiments.ics_circulation_v3.storage_routing import StorageCandidateGenerator


def case(*, release=5, now=0, protected=False, deadline=30, capacity=1):
    nodes = {key: Node(key, "zone", "owner", capacity=capacity if key == "E" else 3)
             for key in ("S", "E", "G")}
    edges = {key: Edge(key, source, target, 1)
             for key, source, target in (("direct", "S", "G"), ("ingress", "S", "E"), ("egress", "E", "G"))}
    contract = StorageWaypointContract(node_id="E", release_at=release, published_at=0)
    bag = StorageBag("bag", "S", "G", 0, deadline, protected, storage=contract)
    return StorageSnapshot(now, Network(nodes, edges),
                           {"tray": Tray("tray", "S", "loaded", "bag")}, {"bag": bag})


def generator(*, horizon=20, budget=5000, deadline=None):
    return StorageCandidateGenerator(RegionalCandidateGenerator(
        horizon=horizon, expansion_limit=budget, deadline_ms=deadline, dynamic_local=True))


def signature(candidate):
    return tuple((leg.edge_id, leg.depart, leg.arrive) for leg in candidate.legs)


def occupy_storage(state, owner, until):
    """A real tray with a committed departure, or an idle stored tray."""
    state.trays[owner] = Tray(owner, "E")
    if until == INFINITY:
        return
    destination, edge_id = f"away-{owner}", f"leave-{owner}"
    state.network.nodes[destination] = Node(destination, "zone", "owner")
    state.network.edges[edge_id] = Edge(edge_id, "E", destination, 1)
    candidate = RouteCandidate(owner, None, owner, (Leg(edge_id, until, until + 1),),
                               until + 1, until + 1, state.version, owner, True, destination)
    state.reservations += candidate_reservations(state, candidate)
    state.plans[owner] = candidate


@pytest.mark.parametrize("factory", [CandidateGenerator, lambda: RegionalCandidateGenerator(
    deadline_ms=None, cache_contract="isolated_replay_v1")])
def test_ordinary_bag_and_empty_delegate_exactly(factory):
    state = case()
    state.bags["bag"] = Bag("bag", "S", "G", 0, 30)
    wrapped = StorageCandidateGenerator(factory())
    plain = deepcopy(wrapped.generator)
    assert wrapped.generate(state, "bag", "tray", 2) == plain.generate(state, "bag", "tray", 2)
    assert wrapped.last_search_status == plain.last_search_status
    assert wrapped.last_expansions == plain.last_expansions
    state.bags.clear()
    state.trays["tray"] = Tray("tray", "S")
    wrapped = StorageCandidateGenerator(factory())
    plain = deepcopy(wrapped.generator)
    assert wrapped.generate_empty(state, "tray", "G", 2) == plain.generate_empty(state, "tray", "G", 2)
    assert wrapped.last_search_status == plain.last_search_status


def test_complete_witness_must_visit_storage_and_hold_same_tray_until_release():
    state = case()
    state.module = FixedLocalModule(unload_ticks=2, hold_by_node={"G": 3})
    before = deepcopy(state)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("ingress", 0, 1), ("egress", 5, 6))
    assert (candidate.unload_complete, candidate.usable_at, candidate.destination_node) == (8, 11, "G")
    assert Reservation("node:E", 1, 5, "tray") in candidate_reservations(state, candidate)
    assert ExecutionValidator().validate(state, candidate).accepted
    assert state == before and state.bags["bag"].destination == "G"
    assert state.completed == {} and state.trays["tray"].mode == "loaded"


def test_full_storage_requires_delayed_ingress_and_real_node_reservation():
    state = case()
    occupy_storage(state, "occupant", 4)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("ingress", 3, 4), ("egress", 5, 6))
    assert Reservation("node:S", 0, 3, "tray") in candidate_reservations(state, candidate)
    assert Reservation("node:E", 4, 5, "tray") in candidate_reservations(state, candidate)


def test_full_storage_and_blocked_upstream_wait_cannot_be_bypassed():
    state = case()
    state.network.nodes["S"] = replace(state.network.nodes["S"], can_wait=False)
    occupy_storage(state, "occupant", 4)
    planner = generator()
    assert planner.generate(state, "bag", "tray", 1) == ()
    assert planner.last_search_status == "bounded_no_candidate"


def test_one_free_storage_slot_is_sufficient_without_unbounded_capacity():
    state = case(capacity=2)
    occupy_storage(state, "occupant", INFINITY)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("ingress", 0, 1), ("egress", 5, 6))
    occupy_storage(state, "second", INFINITY)
    # All slots are full, so positive dwell is invalid; the existing runtime
    # still allows exact release arrival followed by instantaneous departure.
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("ingress", 4, 5), ("egress", 5, 6))
    assert not any(slot.resource == "node:E" for slot in candidate_reservations(state, candidate))
    assert ExecutionValidator().validate(state, candidate).accepted


def test_reception_calendar_projects_delay_through_downstream_no_wait_node():
    state = case()
    state.network.nodes["N"] = Node("N", "zone", "other_owner", can_wait=False)
    state.network.edges.pop("egress")
    state.network.edges.update({"E-N": Edge("E-N", "E", "N", 1), "N-G": Edge("N-G", "N", "G", 1)})
    state.trays["receiver"] = Tray("receiver", "G", "holding", available_at=9)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("ingress", 0, 1), ("E-N", 7, 8), ("N-G", 8, 9))
    assert candidate.unload_complete == 10


def test_long_release_uses_original_horizon_and_reports_unknown_bound():
    planner = generator(horizon=4)
    assert planner.generate(case(release=5), "bag", "tray", 1) == ()
    assert planner.last_search_status == "storage_horizon_or_deadline_bound"
    assert planner.last_diagnostics["missing_candidate_is_not_infeasibility"]


def test_final_protected_deadline_includes_storage_and_unload():
    assert generator().generate(case(protected=True, deadline=6), "bag", "tray", 1) == ()
    candidate, = generator().generate(case(protected=True, deadline=7), "bag", "tray", 1)
    assert candidate.unload_complete == 7


def test_late_ingress_does_not_travel_backwards_to_scheduled_release():
    state = case(release=1, now=4)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("ingress", 4, 5), ("egress", 5, 6))


def test_real_stored_progress_allows_release_wait_without_second_ingress():
    state = case(now=2)
    state.trays["tray"] = Tray("tray", "E", "loaded", "bag")
    state.storage_progress["bag"] = StorageProgress("tray", state.bags["bag"].storage, arrived_at=1)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("egress", 5, 6),)
    assert Reservation("node:E", 2, 5, "tray") in candidate_reservations(state, candidate)


def test_private_frozen_prefix_progress_is_used_without_mutating_actual_ledger():
    actual = case(now=2)
    actual.trays["tray"] = Tray("tray", "E", "loaded", "bag")
    progress = StorageProgress("tray", actual.bags["bag"].storage, arrived_at=2)
    planning = StoragePlanningSnapshot(**deepcopy(actual.__dict__),
                                       projected_storage_progress={"bag": progress})
    candidate, = generator().generate(planning, "bag", "tray", 1)
    assert signature(candidate) == (("egress", 5, 6),)
    assert actual.storage_progress == {} and planning.storage_progress == {}
    assert planning.projected_storage_progress == {"bag": progress}


def test_exact_release_tick_has_no_spurious_extra_wait_tick():
    state = case(now=5)
    state.trays["tray"] = Tray("tray", "E", "loaded", "bag")
    state.storage_progress["bag"] = StorageProgress("tray", state.bags["bag"].storage, arrived_at=1)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("egress", 5, 6),)
    assert not any(slot.resource == "node:E" for slot in candidate_reservations(state, candidate))


def test_departed_progress_does_not_reimpose_another_storage_visit():
    state = case(now=7)
    state.storage_progress["bag"] = StorageProgress("tray", state.bags["bag"].storage, arrived_at=1, departed_at=5)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("direct", 7, 8),)


def test_presence_at_storage_cannot_invent_missing_ingress_history():
    state = case(now=2)
    state.trays["tray"] = Tray("tray", "E", "loaded", "bag")
    planner = generator()
    assert planner.generate(state, "bag", "tray", 1) == ()
    assert planner.last_search_status in {"missing_storage_ingress", "invalid_storage_contract"}


@pytest.mark.parametrize("update", [{"tray_id": "other"}, {"arrived_at": 10}, {"departed_at": 10}])
def test_wrong_tray_or_future_progress_cannot_authorize_departure(update):
    state = case(now=2)
    state.trays["tray"] = Tray("tray", "E", "loaded", "bag")
    progress = StorageProgress("tray", state.bags["bag"].storage, arrived_at=1)
    state.storage_progress["bag"] = replace(progress, **update)
    planner = generator()
    assert planner.generate(state, "bag", "tray", 1) == ()
    assert planner.last_search_status in {"invalid_storage_progress", "invalid_storage_contract"}


def test_shared_budget_counts_cold_graph_before_any_product_search():
    planner = generator(budget=1)
    assert planner.generate(case(), "bag", "tray", 1) == ()
    assert planner.last_search_status == "expansion_budget_exhausted"
    assert planner.last_expansions == 1
    assert planner.last_diagnostics["work_units_by_stage"] == {"topology_edges": 1}


def test_wall_deadline_is_enforced_before_cold_preprocessing():
    planner = generator(deadline=1e-12)
    assert planner.generate(case(), "bag", "tray", 1) == ()
    assert planner.last_search_status == "deadline_exhausted"
    assert planner.last_expansions == 0


def test_repeat_and_deepcopy_retain_full_cold_work_and_recompute_changed_release():
    state = case()
    planner = generator()
    first = planner.generate(state, "bag", "tray", 2)
    work = planner.last_expansions
    clone = deepcopy(planner)
    assert clone.generate(state, "bag", "tray", 2) == first
    assert clone.last_expansions == work
    state.bags["bag"] = replace(state.bags["bag"], storage=replace(state.bags["bag"].storage, release_at=9))
    later, = clone.generate(state, "bag", "tray", 1)
    assert later.legs[-1].depart == 9
    assert planner.last_expansions == work
    assert planner.last_diagnostics["cache_accounting"]["reused_preprocessing_work"] == {}


def test_k_is_global_for_complete_candidates_and_ids_have_owned_baseline():
    state = case()
    state.network.nodes["A"] = Node("A", "zone", "owner")
    state.network.edges.update({"E-A": Edge("E-A", "E", "A", 1), "A-G": Edge("A-G", "A", "G", 1)})
    candidates = generator().generate(state, "bag", "tray", 2)
    assert len(candidates) == 2
    assert all(candidate.baseline_id == candidates[0].candidate_id for candidate in candidates)
    assert [candidate.is_baseline for candidate in candidates] == [True, False]
    assert len({candidate.legs for candidate in candidates}) == 2
    assert all(ExecutionValidator().validate(state, candidate).accepted for candidate in candidates)


def test_static_direct_connection_does_not_mask_unreachable_required_storage():
    state = case()
    state.network.edges.pop("ingress")
    planner = generator()
    assert planner.generate(state, "bag", "tray", 1) == ()
    assert planner.last_search_status == "static_unreachable"


def test_closed_required_edge_stays_closed_even_when_direct_route_exists():
    state = case()
    state.network.edges["ingress"] = replace(state.network.edges["ingress"], capacity=0)
    planner = generator()
    assert planner.generate(state, "bag", "tray", 1) == ()
    assert planner.last_search_status == "static_unreachable"


def test_generator_does_not_hide_storage_contract_on_plain_snapshot():
    state = case()
    plain = Snapshot(**{name: deepcopy(getattr(state, name)) for name in Snapshot.__dataclass_fields__})
    planner = generator()
    assert planner.generate(plain, "bag", "tray", 1) == ()
    assert planner.last_search_status == "invalid_storage_contract"


def test_opt_in_wrapper_does_not_change_base_bag_serialization():
    assert set(asdict(Bag("bag", "S", "G", 0, 30))) == {
        "bag_id", "origin", "destination", "arrival", "deadline", "protected"}


def test_long_release_plateau_does_not_breadth_first_expand_all_cycles_before_egress():
    state = case(release=10000, deadline=12000)
    state.network.edges.clear()
    # The legitimate waypoint path is last in sorted edge order. One hundred
    # positive-cost cycles create equal final-arrival lower bounds before the
    # release, without zero-length edges or artificial task suppression.
    for index in range(100):
        node = f"B{index:03d}"
        state.network.nodes[node] = Node(node, "zone", "owner")
        state.network.edges[f"a-out-{index:03d}"] = Edge(f"a-out-{index:03d}", "S", node, 1)
        state.network.edges[f"b-back-{index:03d}"] = Edge(f"b-back-{index:03d}", node, "S", 1)
    state.network.edges["z-ingress"] = Edge("z-ingress", "S", "E", 1)
    state.network.edges["z-egress"] = Edge("z-egress", "E", "G", 1)
    before = deepcopy(state)
    planner = generator(horizon=10005, budget=500)
    candidate, = planner.generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("z-ingress", 0, 1), ("z-egress", 10000, 10001))
    assert planner.last_expansions <= 500
    assert planner.last_diagnostics["work_units_by_stage"]["topology_edges"] == 202
    assert planner.last_diagnostics["cache_accounting"]["reused_preprocessing_work"] == {}
    assert state == before


def test_busy_storage_release_arrival_keeps_zero_dwell_legal_with_same_500_budget():
    state = case(release=10000, deadline=12000, protected=True)
    state.network.edges.clear()
    for index in range(100):
        node = f"B{index:03d}"
        state.network.nodes[node] = Node(node, "zone", "owner")
        state.network.edges[f"a{index:03d}"] = Edge(f"a{index:03d}", "S", node, 1)
        state.network.edges[f"b{index:03d}"] = Edge(f"b{index:03d}", node, "S", 1)
    state.network.edges["z-in"] = Edge("z-in", "S", "E", 1)
    state.network.edges["z-out"] = Edge("z-out", "E", "G", 1)
    occupy_storage(state, "blocker", 10002)
    before = deepcopy(state)
    planner = generator(horizon=10005, budget=500)
    candidate, = planner.generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("z-in", 9999, 10000), ("z-out", 10000, 10001))
    assert ExecutionValidator().validate(state, candidate).accepted
    assert planner.last_expansions <= 500
    assert planner.last_diagnostics["work_units_by_stage"]["storage_calendar_reservations"] > 0
    assert state == before


def test_release_arrival_projects_back_through_no_wait_chain():
    state = case(release=5)
    state.network.edges.pop("ingress")
    state.network.nodes["N"] = Node("N", "zone", "owner", can_wait=False)
    state.network.edges["S-N"] = Edge("S-N", "S", "N", 1)
    state.network.edges["N-E"] = Edge("N-E", "N", "E", 1)
    occupy_storage(state, "blocker", 9)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("S-N", 3, 4), ("N-E", 4, 5), ("egress", 5, 6))
    assert ExecutionValidator().validate(state, candidate).accepted


def test_storage_departure_event_from_blocked_no_wait_suffix_projects_to_late_ingress():
    state = case(release=3, protected=True, deadline=10)
    state.network.edges.pop("egress")
    state.network.nodes.update({"B": Node("B", "zone", "owner", can_wait=False),
                                "C": Node("C", "zone", "owner", can_wait=False),
                                "X": Node("X", "zone", "owner"),
                                "Q": Node("Q", "zone", "owner")})
    state.network.edges.update({"E-B": Edge("E-B", "E", "B", 1),
                                "B-C": Edge("B-C", "B", "C", 2),
                                "C-G": Edge("C-G", "C", "G", 1),
                                "X-B": Edge("X-B", "X", "B", 4),
                                "C-Q": Edge("C-Q", "C", "Q", 1)})
    state.trays["moving"] = Tray("moving", "X")
    plan = RouteCandidate("moving", None, "moving", (Leg("X-B", 0, 4), Leg("B-C", 4, 6), Leg("C-Q", 6, 7)),
                           7, 7, state.version, "moving", True, "Q")
    state.reservations += candidate_reservations(state, plan)
    state.plans["moving"] = plan
    occupy_storage(state, "stored", 6)
    candidate, = generator().generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("ingress", 4, 5), ("E-B", 5, 6), ("B-C", 6, 8), ("C-G", 8, 9))
    assert candidate.unload_complete == 10
    assert ExecutionValidator().validate(state, candidate).accepted


def test_suffix_floor_considers_all_exits_and_rejects_only_necessary_bound():
    state = case(release=5, protected=True, deadline=9)
    state.network.nodes["A"] = Node("A", "zone", "owner")
    state.network.edges["E-A"] = Edge("E-A", "E", "A", 1)
    state.network.edges["A-G"] = Edge("A-G", "A", "G", 2)
    state.network.nodes["Q"] = Node("Q", "zone", "owner")
    state.trays["committed"] = Tray("committed", "Q")
    # The witness uses the other physical exit; a single-shortest-exit bound
    # would falsely reject it. The existing owner-bound reservation remains.
    state.reservations += (Reservation("edge:egress", 5, 20, "committed"),)
    planner = generator()
    candidate, = planner.generate(state, "bag", "tray", 1)
    assert signature(candidate) == (("ingress", 0, 1), ("E-A", 5, 6), ("A-G", 6, 8))
    assert candidate.unload_complete == 9
    assert planner.last_diagnostics["storage_relaxed_completion_floor"] == 8
    state.bags["bag"] = replace(state.bags["bag"], deadline=8)
    planner = generator()
    assert planner.generate(state, "bag", "tray", 1) == ()
    assert planner.last_search_status == "storage_calendar_horizon_or_deadline_bound"


def test_capacity_calendar_uses_overlap_threshold_and_half_open_full_traversal():
    from scripts.experiments.ics_circulation_v3.storage_calendar import CapacityCalendarView
    state = case()
    state.network.edges["egress"] = replace(state.network.edges["egress"], capacity=2)
    state.reservations += (Reservation("edge:egress", 2, 7, "one"),
                           Reservation("edge:egress", 4, 9, "two"),
                           Reservation("edge:egress", 7, 8, "three"))
    class Counter:
        def __init__(self):
            self.stages = {}
        def _consume(self, stage):
            self.stages[stage] = self.stages.get(stage, 0) + 1
    owner = Counter()
    view = CapacityCalendarView(owner, state, "tray")
    assert view.blocked("edge:egress") == ((4, 8),)
    assert view.available("edge:egress", 2, 4)
    assert not view.available("edge:egress", 3, 5)
    assert view.available("edge:egress", 8, 10)
    assert view.available("edge:egress", 5, 5)
    assert view.earliest_available("edge:egress", 3, 2) == 8
    assert view.earliest_available("edge:egress", 2, 2) == 2
    assert owner.stages["storage_calendar_interval_scans"] > 0


def test_isolated_static_unreachable_reuses_complete_bound_with_same_logical_budget():
    state = case()
    state.network.edges.pop("ingress")
    planner = StorageCandidateGenerator(RegionalCandidateGenerator(
        horizon=20, expansion_limit=5000, deadline_ms=None, cache_contract="isolated_replay_v1"))
    assert planner.generate(state, "bag", "tray", 1) == ()
    work = planner.last_expansions
    first = deepcopy(planner.last_diagnostics)
    assert planner.generate(state, "bag", "tray", 1) == ()
    assert planner.last_search_status == "static_unreachable"
    assert planner.last_expansions == work
    assert first["cache_accounting"]["actual_preprocessing_work"] == planner.last_diagnostics["cache_accounting"]["reused_preprocessing_work"]
    exported = planner.generator._owned_topology_cache.export()
    goals = {row["goal"] for row in exported["entries_lru_oldest_first"][0]["lower"]}
    assert goals == {"E", "G"}
