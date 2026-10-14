"""Independent adversarial controls for the central same-zone proxy baseline.

These tests exercise public contracts and physical counterexamples. They do not
grant supplier permissions or establish simultaneous capacity-feasible matching.
"""
from dataclasses import replace
from itertools import product

import pytest

from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.runtime import (
    CandidateGenerator, ExecutionValidator,
)
from scripts.experiments.ics_circulation_v3.same_zone_supply import (
    GuardWorkBudget, SameZoneDemand, SameZoneSupplyPrebalancer, same_zone_service_guard,
)


def _state(*, spare=None, spare_at=0, spare_mode="empty", hold=None):
    nodes = {n: Node(n, "same-zone", "owner:" + n, 5) for n in "ABCD"}
    edges = [Edge("AB", "A", "B", 3, 2), Edge("AC", "A", "C", 4, 2),
             Edge("DC", "D", "C", 100, 2), Edge("BA", "B", "A", 3, 2)]
    trays = {"donor": Tray("donor", "A")}
    if spare is not None:
        trays["spare"] = Tray("spare", spare, spare_mode, available_at=spare_at)
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}), trays, {},
                    module=FixedLocalModule(hold_by_node=hold or {}))


def _candidate(state):
    candidate, = CandidateGenerator(horizon=200).generate_empty(state, "donor", "B", k=1)
    assert ExecutionValidator().validate(state, candidate).accepted
    return candidate


def _need(key, node, at):
    return SameZoneDemand(key, node, at, "independent_test", key)


def test_same_logistics_zone_cross_owner_service_uses_real_hold_time():
    state = _state(hold={"B": 2})
    candidate = _candidate(state)
    assert candidate.usable_at == 5
    assert state.network.nodes["A"].control_partition != state.network.nodes["B"].control_partition
    before = state.clone()
    reason, _ = same_zone_service_guard(state, candidate, (_need("target", "B", 2),), "target")
    assert reason is None
    assert state == before  # The guard does not reserve stock or create demand.


@pytest.mark.parametrize("other_release", [0, 5])
def test_only_time_reachable_donor_is_protected_even_for_already_waiting_remote_demand(other_release):
    state = _state(spare="D")
    candidate = _candidate(state)
    needs = (_need("target", "B", 10), _need("other", "C", other_release))
    reason, _ = same_zone_service_guard(state, candidate, needs, "target")
    assert reason is not None
    # A bare node-inventory prefix misses this: no tray starts at C. Merely
    # finding a directed D->C path also misses the 4-versus-100 tick gap.
    assert all(tray.node != "C" for tray in state.trays.values())


def test_future_empty_release_is_not_usable_before_its_available_tick():
    state = _state(spare="D", spare_at=10, spare_mode="holding")
    state.network.edges["DC"] = replace(state.network.edges["DC"], travel_time=1)
    reason, _ = same_zone_service_guard(state, _candidate(state),
        (_need("target", "B", 10), _need("other", "C", 0)), "target")
    assert reason is not None


def test_target_credit_does_not_hide_same_tick_loss_of_another_named_demand():
    state = _state()
    reason, _ = same_zone_service_guard(state, _candidate(state),
        (_need("target", "B", 3), _need("other", "A", 3)), "target")
    assert reason is not None


def test_real_spare_at_other_need_preserves_service_without_inventing_a_second_donor_use():
    state = _state(spare="C")
    reason, _ = same_zone_service_guard(state, _candidate(state),
        (_need("target", "B", 3), _need("other", "C", 0)), "target")
    assert reason is None


def test_same_node_known_release_already_contains_hold_and_is_not_delayed_twice():
    state = _state(spare="C", spare_at=4, spare_mode="holding", hold={"C": 9})
    reason, _ = same_zone_service_guard(state, _candidate(state),
        (_need("target", "B", 5), _need("other", "C", 4)), "target")
    assert reason is None


def test_only_target_release_may_be_deferred_to_candidate_usable_time():
    state = _state(hold={"B": 7})
    candidate = _candidate(state)
    assert candidate.usable_at == 10
    reason, _ = same_zone_service_guard(state, candidate,
        (_need("target", "B", 0), _need("other", "A", 5)), "target")
    assert reason is not None


def test_directed_reachability_does_not_reverse_an_edge_to_fake_spare_supply():
    state = _state(spare="D")
    del state.network.edges["DC"]
    state.network.edges["CD"] = Edge("CD", "C", "D", 1, 2)
    reason, _ = same_zone_service_guard(state, _candidate(state),
        (_need("target", "B", 10), _need("other", "C", 4)), "target")
    assert reason is not None


def _forecast(unit="target", node="B", at=3, **kwargs):
    return RoutingDemandForecast("forecast:" + unit, node, "A", at, 80,
                                 unit_ids=(unit,), **kwargs)


def _controller(**kwargs):
    return SameZoneSupplyPrebalancer(planning_horizon=40, planning_budget_ms=None, **kwargs)


def test_target_traversal_cap_does_not_truncate_later_other_demand_protection():
    state = _state()
    plan = _controller(max_demand_units=1).plan(state,
        (_forecast(), _forecast("other", "C", 4)))
    assert plan.proposals == ()
    assert len(plan.diagnostics["demand_units"]) == 2
    assert plan.diagnostics["demand_units_truncated"]
    assert any(row["reason"] == "same_zone_would_degrade_other_prefix"
               for row in plan.diagnostics["candidate_rejections"])


def test_incomplete_guard_ledger_fails_closed_without_mutating_the_input():
    state = _state()
    before = state.clone()
    plan = _controller(max_guard_demand_units=1).plan(state,
        (_forecast(), _forecast("other", "C", 4)))
    assert not plan.proposals
    assert plan.diagnostics["same_zone_enhancement_blocked"] == "same_zone_demand_ledger_limit"
    assert plan.diagnostics["search_calls_by_domain"]["same_zone"] == 0
    assert state == before


def test_guard_budget_exhaustion_is_unknown_and_cannot_approve_a_partial_prefix():
    state = _state()
    budget = GuardWorkBudget(limit=1)
    reason, details = same_zone_service_guard(state, _candidate(state),
        (_need("target", "B", 3),), "target", work_budget=budget)
    assert reason == "same_zone_guard_work_budget"
    assert details["work"] == budget.used == 1
    plan = _controller(max_guard_work=1).plan(state, (_forecast(),))
    assert not plan.proposals and plan.diagnostics["guard_work"] == 1
    assert any(row["reason"] == reason for row in plan.diagnostics["candidate_rejections"])


def test_sequential_commits_do_not_reuse_one_release_for_two_named_targets():
    state = _state()
    state.trays["donor:second"] = Tray("donor:second", "A")
    before = state.clone()
    controller = _controller()
    forecasts = (_forecast("one"), _forecast("two"))
    plan = controller.plan(state, forecasts)
    assert state == before
    assert len(plan.proposals) == 2
    assert len({c.tray_id for c in plan.proposals}) == 2
    assert [c.dependency_version for c in plan.proposals] == [0, 1]
    for candidate in plan.proposals:
        assert ExecutionValidator().commit(state, candidate).accepted
    assert controller.plan(state, forecasts).proposals == ()


@pytest.mark.parametrize("variant", ["future_publication", "cancelled", "stale", "observed_loaded", "observed_completed"])
def test_publication_and_actual_identity_filters_cannot_create_phantom_same_zone_targets(variant):
    state = _state()
    forecast = _forecast(at=20)
    forecasts = (forecast,)
    if variant == "future_publication":
        forecasts = (replace(forecast, published_at=1),)
    elif variant == "cancelled":
        state.now = 1
        forecasts += (replace(forecast, count=0, unit_ids=(), published_at=1),)
    elif variant == "stale":
        state.now = 61
    else:
        state.bags["target"] = Bag("target", "B", "A", 0, 80)
        if variant == "observed_loaded":
            state.trays["actual"] = Tray("actual", "B", "loaded", "target")
        else:
            state.completed["target"] = 0
    plan = _controller().plan(state, forecasts)
    assert plan.proposals == ()
    assert plan.diagnostics["demand_units"] == []


def test_visible_unadmitted_protected_task_blocks_only_the_new_same_zone_arm():
    state = _state()
    state.bags["protected"] = Bag("protected", "C", "A", 0, 10, True)
    plan = _controller().plan(state, (_forecast(),))
    assert not plan.proposals
    assert plan.diagnostics["same_zone_enhancement_blocked"] == "unadmitted_protected_obligation"
    assert plan.diagnostics["unadmitted_protected_bag_ids"] == ["protected"]
    assert plan.diagnostics["search_calls_by_domain"]["same_zone"] == 0


def test_unknown_empty_obligation_neither_cancels_nor_invents_a_timed_release():
    state = _state()
    state.trays["promised"] = Tray("promised", "D")
    state.empty_targets["promised"] = "B"
    before = state.clone()
    plan = _controller().plan(state, (_forecast(),))
    assert not plan.proposals and state == before
    obligation, = plan.diagnostics["pending_empty_obligations"]
    assert obligation["tray_id"] == "promised" and obligation["final_available_at"] is None
    assert plan.diagnostics["demand_covered_by_pending_empty_obligation"]


def test_iterative_matching_agrees_with_exhaustive_assignment_on_every_three_by_three_graph():
    # The guard's matching rank is a substantive admission condition. Enumerate
    # all 512 tiny bipartite graphs against a structurally different brute-force
    # oracle, including alternating paths that greedy single-pass matching loses.
    from scripts.experiments.ics_circulation_v3.prebalance import SupplyEvent
    from scripts.experiments.ics_circulation_v3.same_zone_supply import _matching

    units = tuple(_need(str(i), str(i), 0) for i in range(3))
    supplies = tuple(SupplyEvent(str(i), str(i), 0, "test") for i in range(3))
    for bits in range(1 << 9):
        allowed = {(str(t), str(u)) for t in range(3) for u in range(3)
                   if bits & (1 << (3 * t + u))}
        expected = 0
        for assignment in product((None, "0", "1", "2"), repeat=3):
            used = [tray for tray in assignment if tray is not None]
            if len(set(used)) != len(used):
                continue
            if all(tray is None or (tray, str(unit)) in allowed
                   for unit, tray in enumerate(assignment)):
                expected = max(expected, len(used))
        earliest = {pair: 0 for pair in allowed}
        actual = _matching(units, supplies, earliest, 0, None, GuardWorkBudget(10000))
        assert actual == expected, (bits, actual, expected)


def test_a_shortest_path_may_cross_another_zone_without_deleting_the_other_need():
    state = _state()
    del state.network.edges["AC"]
    state.network.nodes["X"] = Node("X", "other-zone", "foreign-owner", 5)
    state.network.edges["AX"] = Edge("AX", "A", "X", 1, 2)
    state.network.edges["XC"] = Edge("XC", "X", "C", 1, 2)
    reason, details = same_zone_service_guard(state, _candidate(state),
        (_need("target", "B", 4), _need("other", "C", 0)), "target", horizon_end=10)
    assert reason == "same_zone_would_degrade_other_prefix"
    assert any(row == {"tray_id": "donor", "node": "C", "at": 2}
               for row in details["earliest_service"])


def test_closed_edge_is_not_an_optimistic_supply_path_and_zero_budget_is_unknown():
    state = _state()
    state.network.edges["AC"] = replace(state.network.edges["AC"], capacity=0)
    needs = (_need("target", "B", 4), _need("other", "C", 0))
    reason, _ = same_zone_service_guard(state, _candidate(state), needs, "target", horizon_end=10)
    assert reason is None  # The action cannot remove a capability that did not exist.
    reason, _ = same_zone_service_guard(state, _candidate(state), needs, "target",
        horizon_end=10, work_budget=GuardWorkBudget(0))
    assert reason == "same_zone_guard_work_budget"


@pytest.mark.parametrize("status", ["expansion_budget_exhausted", "deadline_exhausted", "bounded_no_candidate"])
def test_finite_candidate_search_failure_is_never_a_physical_infeasibility_certificate(status):
    class EmptyBoundedSearch:
        last_search_status = status
        last_expansions = 7

        def generate_empty(self, snapshot, tray_id, destination, k=1):
            return ()

    plan = _controller(generator_factory=EmptyBoundedSearch).plan(_state(), (_forecast(),))
    assert not plan.proposals
    rejection, = plan.diagnostics["candidate_rejections"]
    assert rejection["search_status"] == status
    assert rejection["reason"] in {"same_zone_search_budget_unknown", "same_zone_search_no_candidate"}
    assert "infeasible" not in rejection["reason"]
    assert plan.diagnostics["search_expansions"] == 7
