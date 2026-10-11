from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.joint_reference import JointDomain, JointMPC, solve_joint
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.run_joint_reference import fixture, rolling_episode
from scripts.experiments.ics_circulation_v3.runtime import Simulation


def test_finite_joint_search_proves_anticipatory_cycle_cost_and_returns_executable_first_action():
    case = fixture()
    result = solve_joint(case.initial, case.future, domain=JointDomain(3))
    assert result.complete and result.status == "finite_domain_optimal"
    assert result.total_cost == pytest.approx(.1) and result.gap == 0
    assert len(result.first_actions) == 1 and result.first_actions[0].bag_id is None
    engine = Simulation(case.initial, case.future, control_mode="external")
    assert engine.intervene(result.first_actions[0]).accepted
    assert case.initial.trays["tray"].node == "A"  # Branch isolation.


def test_same_tick_joint_two_trays_and_later_loaded_actions_are_not_greedy_first_supply_pool():
    nodes = {n: Node(n, n, n, capacity=4) for n in "ABC"}
    edges = {e.edge_id: e for e in (Edge("AB", "A", "B", 1), Edge("BA", "B", "A", 1),
                                     Edge("AC", "A", "C", 1), Edge("CA", "C", "A", 1))}
    state = Snapshot(0, Network(nodes, edges), {t: Tray(t, "A") for t in ("x", "y")}, {},
                     module=FixedLocalModule(unload_ticks=0))
    future = (Bag("b", "B", "A", 1, 4), Bag("c", "C", "A", 1, 4))
    result = solve_joint(state, future, domain=JointDomain(2, expansion_limit=200000))
    assert result.complete, result.diagnostics
    assert result.total_cost == pytest.approx(.2)
    assert len(result.first_actions) == 2
    assert {a.destination_node for a in result.first_actions} == {"B", "C"}
    assert len([a for a in result.schedule if a.bag_id is not None]) == 2


def test_actual_released_tray_can_be_exported_again_in_same_exact_episode():
    case = fixture(horizon=5)
    future = case.future + (Bag("second", "B", "A", 3, 6),)
    result = solve_joint(case.initial, future, domain=JointDomain(5, expansion_limit=200000))
    assert result.complete, result.diagnostics
    assert result.total_cost == pytest.approx(.2)
    exports = [a for a in result.schedule if a.bag_id is None and a.destination == "B"]
    assert len(exports) == 2 and exports[0].tray_id == exports[1].tray_id
    assert exports[1].tick >= 2


def test_budget_failure_is_not_infeasibility_or_optimality_certificate():
    case = fixture()
    result = solve_joint(case.initial, case.future, domain=JointDomain(3, expansion_limit=20))
    assert not result.complete and result.status == "work_budget_exhausted"
    assert result.total_cost is not None  # Valid no-action incumbent retained.
    assert result.lower_bound is None and result.gap is None


def test_route_tail_keeps_terminal_inflight_penalty_instead_of_requiring_window_completion():
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=2) for n in "AB"},
                               {"AB": Edge("AB", "A", "B", 3)}),
                     {"t": Tray("t", "A", "loaded", "b")}, {"b": Bag("b", "A", "B", 0, 20)},
                     module=FixedLocalModule(unload_ticks=0))
    # Construct a feasible warm route crossing H; search may prefer waiting for
    # this objective, but must evaluate the terminal in-flight branch legally.
    from scripts.experiments.ics_circulation_v3.joint_reference import TimedJointAction
    from scripts.experiments.ics_circulation_v3.model import Leg
    action = TimedJointAction(0, "t", "b", "B", (Leg("AB", 0, 3),), 3, 3)
    engine = Simulation(state, control_mode="external")
    assert engine.intervene(action.proposal(engine.observe())).accepted
    end = engine.advance(1)
    assert end.cost_components["terminal_inflight"] == 1 and end.cost_components["terminal_backlog"] == 1
    result = solve_joint(state, domain=JointDomain(1, route_tail_ticks=3), warm_start=(action,))
    assert result.complete and result.total_cost == 10  # Waiting beats crossing this terminal cut.


def test_source_export_floor_cannot_be_bypassed_by_joint_or_mpc():
    case = fixture()
    case.initial.module = FixedLocalModule(unload_ticks=0, export_min_stock=1)
    result = solve_joint(case.initial, case.future, domain=JointDomain(3))
    assert result.complete and not result.first_actions
    assert result.total_cost == 12


def test_mpc_uses_only_published_identified_proxy_and_latest_cancellation():
    case = fixture()
    controller = JointMPC(planning_horizon=3, expansion_limit=10000)
    with pytest.raises(ValueError, match="Unpublished"):
        controller.plan(case.initial, (replace(case.forecasts[0], published_at=1),))
    cancellation = replace(case.forecasts[0], count=0, published_at=1)
    state = case.initial.clone()
    state.now = 1
    result = controller.plan(state, (case.forecasts[0], cancellation))
    assert controller.history[-1]["proxy_bags"] == []
    assert not result.first_actions
    assert not controller.history[-1]["actual_world_optimality_claim"]


def test_two_truth_tapes_cannot_change_same_mpc_observation_decision():
    case = fixture()
    first = JointMPC(planning_horizon=3, expansion_limit=10000).plan(case.initial, case.forecasts)
    changed_truth = fixture("false_forecast")
    second = JointMPC(planning_horizon=3, expansion_limit=10000).plan(changed_truth.initial, changed_truth.forecasts)
    assert first.first_actions == second.first_actions
    assert first.total_cost == second.total_cost


def test_rolling_positive_zero_and_false_forecast_negative_are_all_retained():
    results = {name: rolling_episode(fixture(name), planning_horizon=3, work_budget=10000)
               for name in ("positive", "zero", "false_forecast")}
    assert results["positive"]["cost"] == pytest.approx(.1)
    assert results["zero"]["cost"] == 0
    assert results["false_forecast"]["cost"] > 0
    assert all(item["commit_rejections"] == 0 for item in results.values())


def test_no_wait_dead_end_is_only_proven_infeasible_after_complete_domain_search():
    state = Snapshot(0, Network({"S": Node("S", "z", "r", can_wait=False),
                                 "G": Node("G", "z", "r")}, {}),
                     {"t": Tray("t", "S", "loaded", "b")}, {"b": Bag("b", "S", "G", 0, 5)})
    result = solve_joint(state, domain=JointDomain(1))
    assert result.complete and result.status == "finite_domain_infeasible"
    assert result.total_cost is None and result.gap is None


def test_existing_empty_obligation_and_protected_route_deadline_are_kept():
    case = fixture()
    state = case.initial.clone()
    state.empty_targets["tray"] = "B"
    protected = replace(case.future[0], protected=True, deadline=2)
    result = solve_joint(state, (protected,), domain=JointDomain(3))
    assert result.complete and result.total_cost == pytest.approx(.1)
    assert all(a.destination == "B" for a in result.schedule if a.bag_id is None)
    assert next(a for a in result.schedule if a.bag_id is not None).unload_complete <= 2


def test_same_tick_commit_order_is_searched_when_first_tray_needs_second_trays_node():
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=1) for n in "ABC"},
                               {"AB": Edge("AB", "A", "B", 1), "BC": Edge("BC", "B", "C", 1)}),
                     {"a": Tray("a", "A", "loaded", "first"), "b": Tray("b", "B", "loaded", "second")},
                     {"first": Bag("first", "A", "B", 0, 3), "second": Bag("second", "B", "C", 0, 3)},
                     module=FixedLocalModule(unload_ticks=0))
    result = solve_joint(state, domain=JointDomain(1))
    assert result.complete and result.total_cost == 0
    # A fixed sorted-tray pass misses this joint transaction: b must vacate B
    # in its accepted calendar before a's full terminal reservation is legal.
    assert [candidate.tray_id for candidate in result.first_actions] == ["b", "a"]


def test_joint_domain_includes_required_cycles_at_nonwaitable_nodes():
    from scripts.experiments.ics_circulation_v3.run_phase4_routing import no_wait_cycle_case
    case = no_wait_cycle_case()
    result = solve_joint(case.state, domain=JointDomain(7))
    assert result.complete and result.total_cost == 0
    assert tuple(leg.edge_id for leg in result.first_actions[0].legs) == ("S-A", "A-S", "S-A", "A-S", "S-G")


def test_old_inflight_tray_is_usable_only_after_actual_arrival_and_fixed_hold():
    from scripts.experiments.ics_circulation_v3.model import InFlight
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=2) for n in "ABC"},
                               {"CB": Edge("CB", "C", "B", 2), "BA": Edge("BA", "B", "A", 1)}),
                     {"old": Tray("old", None, "in_transit")}, {},
                     old_in_transit=(InFlight("old", "CB", 0, 2),),
                     module=FixedLocalModule(unload_ticks=0, hold_by_node={"B": 2}))
    result = solve_joint(state, (Bag("later", "B", "A", 3, 8),), domain=JointDomain(5))
    assert result.complete and result.total_cost == 1
    assert not result.first_actions
    assert len(result.schedule) == 1 and result.schedule[0].tick == 4


def test_current_sequential_domain_misses_capacity_one_atomic_swap_counterexample():
    """A recorded domain gap, not a claim that the physical swap is impossible.

    The second half declares a complete legal physical plan as an initial
    fixture. It is not an available single-commit authorization path. An atomic
    bundle owner transaction is needed before this can join the control domain.
    """
    from scripts.experiments.ics_circulation_v3.model import Leg, RouteCandidate
    from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, candidate_reservations, assert_invariants
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=1) for n in "AB"},
                               {"AB": Edge("AB", "A", "B", 1), "BA": Edge("BA", "B", "A", 1)}),
                     {"x": Tray("x", "A", "loaded", "bx"), "y": Tray("y", "B", "loaded", "by")},
                     {"bx": Bag("bx", "A", "B", 0, 5), "by": Bag("by", "B", "A", 0, 5)},
                     module=FixedLocalModule(unload_ticks=0))
    sequence_only = solve_joint(state, domain=JointDomain(1))
    assert sequence_only.complete and sequence_only.total_cost == 20
    assert not sequence_only.first_actions
    plans = (RouteCandidate("swap-x", "bx", "x", (Leg("AB", 0, 1),), 1, 1, 0, "swap-x", True, "B"),
             RouteCandidate("swap-y", "by", "y", (Leg("BA", 0, 1),), 1, 1, 0, "swap-y", True, "A"))
    assert all(not ExecutionValidator().validate(state, plan).accepted for plan in plans)
    physical_fixture = state.clone()
    physical_fixture.reservations = tuple(slot for plan in plans for slot in candidate_reservations(state, plan))
    physical_fixture.plans = {plan.tray_id: plan for plan in plans}
    assert_invariants(physical_fixture)
    end = Simulation(physical_fixture, control_mode="external").advance(1)
    assert end.total_cost == 0 and len(end.completed) == 2


def test_atomic_domain_closes_swap_gap_and_requires_grouped_execution():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
    from scripts.experiments.ics_circulation_v3.joint_transactions import commit_joint_actions
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=1) for n in "AB"},
                               {"AB": Edge("AB", "A", "B", 1), "BA": Edge("BA", "B", "A", 1)}),
                     {"x": Tray("x", "A", "loaded", "bx"), "y": Tray("y", "B", "loaded", "by")},
                     {"bx": Bag("bx", "A", "B", 0, 5), "by": Bag("by", "B", "A", 0, 5)},
                     module=FixedLocalModule(unload_ticks=0))
    before = state.clone()
    sequential = solve_atomic_joint(state, domain=AtomicJointDomain(1, atomic_bundles=False))
    atomic = solve_atomic_joint(state, domain=AtomicJointDomain(1))
    assert sequential.complete and sequential.total_cost == 20
    assert atomic.complete and atomic.total_cost == 0
    assert len(atomic.first_bundles) == 1 and len(atomic.first_bundles[0]) == 2
    with pytest.raises(ValueError, match="must not be flattened"):
        _ = atomic.first_actions
    assert state == before
    engine = Simulation(state, control_mode="external")
    assert commit_joint_actions(engine, atomic.first_bundles[0]).accepted
    assert len(engine.advance(1).completed) == 2


def test_atomic_relaxation_keeps_nonparticipating_stock_and_joint_export_floor():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=4) for n in "AB"},
                               {"AB": Edge("AB", "A", "B", 1, capacity=2),
                                "BA": Edge("BA", "B", "A", 1, capacity=2)}),
                     {"x": Tray("x", "A"), "y": Tray("y", "A")}, {},
                     module=FixedLocalModule(unload_ticks=0, export_min_stock=1))
    future = (Bag("b1", "B", "A", 1, 4), Bag("b2", "B", "A", 1, 4))
    result = solve_atomic_joint(state, future, domain=AtomicJointDomain(2, expansion_limit=200000))
    assert result.complete and result.total_cost == pytest.approx(11.1)
    assert sum(candidate.destination_node == "B" and candidate.bag_id is None
               for bundle in result.first_bundles for candidate in bundle) == 1


def test_atomic_mpc_preserves_future_information_gate_and_budget_unknown_gap():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointMPC
    case = fixture()
    policy = AtomicJointMPC(planning_horizon=3, expansion_limit=20)
    with pytest.raises(ValueError, match="Unpublished"):
        policy.plan(case.initial, (replace(case.forecasts[0], published_at=1),))
    result = policy.plan(case.initial, case.forecasts)
    assert not result.complete and result.gap is None
    assert policy.history[-1]["input_kind"] == "published_forecast_proxy_only"


def test_source_contract_is_explicit_and_prefix_guard_blocks_uncommitted_reuse():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
    from scripts.experiments.ics_circulation_v3.run_joint_bundle_reference import source_reuse_fixture
    initial, forecasts, future = source_reuse_fixture()
    unrestricted = solve_atomic_joint(initial, future, domain=AtomicJointDomain(5), published_forecasts=forecasts)
    guarded = solve_atomic_joint(initial, future,
        domain=AtomicJointDomain(5, source_protection_contract="shared_forecast_prefix"),
        published_forecasts=forecasts, warm_start=unrestricted.schedule)
    assert unrestricted.complete and unrestricted.total_cost == pytest.approx(.1)
    assert guarded.complete and guarded.total_cost == pytest.approx(3.)
    assert not guarded.first_bundles  # Warm incumbent cannot bypass the guard.
    assert guarded.diagnostics["source_protection_contract"] == "shared_forecast_prefix"
    with pytest.raises(ValueError, match="source_protection_contract"):
        AtomicJointDomain(5, source_protection_contract="implicit")


def test_shared_prefix_guard_uses_same_single_donor_rule_and_aggregates_bundle_exports():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, source_protection_failure
    from scripts.experiments.ics_circulation_v3.joint_reference import TimedJointAction
    from scripts.experiments.ics_circulation_v3.model import Leg
    from scripts.experiments.ics_circulation_v3.prebalance import PredictivePrebalancer, known_supply
    from scripts.experiments.ics_circulation_v3.run_joint_bundle_reference import source_reuse_fixture
    state, forecasts, _ = source_reuse_fixture()
    state.trays["spare"] = Tray("spare", "A")
    domain = AtomicJointDomain(5, source_protection_contract="shared_forecast_prefix")
    proposals = tuple(TimedJointAction(0, tray, None, "B", (Leg("AB", 0, 1),), 1, 1).proposal(state)
                      for tray in ("tray", "spare"))
    greedy = PredictivePrebalancer(planning_horizon=5)
    demand = greedy._demand(state, forecasts, {"accepted_forecasts": [], "ignored_forecasts": []})
    assert source_protection_failure(state, proposals[:1], domain, forecasts) == greedy._donor_protection(
        state, "tray", known_supply(state), demand) is None
    assert source_protection_failure(state, proposals, domain, forecasts).startswith("source_zone_prefix_min_stock")


def test_atomic_warm_schedule_outside_declared_time_domain_cannot_supply_certificate():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, TimedJointBundle, solve_atomic_joint
    from scripts.experiments.ics_circulation_v3.joint_reference import TimedJointAction
    from scripts.experiments.ics_circulation_v3.model import Leg
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=2) for n in "AB"},
                               {"AB": Edge("AB", "A", "B", 2)}),
                     {"t": Tray("t", "A", "loaded", "b")}, {"b": Bag("b", "A", "B", 0, 8)},
                     module=FixedLocalModule(unload_ticks=0))
    warm = (TimedJointBundle(0, (TimedJointAction(0, "t", "b", "B", (Leg("AB", 0, 2),), 2, 2),)),)
    result = solve_atomic_joint(state, domain=AtomicJointDomain(1), warm_start=warm)
    assert result.complete and result.total_cost == 10
    assert not result.schedule


def test_shared_prefix_guard_does_not_recharge_an_accepted_empty_target_obligation():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint, source_protection_failure
    from scripts.experiments.ics_circulation_v3.joint_reference import TimedJointAction
    from scripts.experiments.ics_circulation_v3.model import Leg
    from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=2) for n in "MB"},
                               {"MB": Edge("MB", "M", "B", 1), "BM": Edge("BM", "B", "M", 1)}),
                     {"t": Tray("t", "M")}, {}, module=FixedLocalModule(unload_ticks=0, export_min_stock=1),
                     empty_targets={"t": "B"})
    domain = AtomicJointDomain(2, source_protection_contract="shared_forecast_prefix")
    candidate = TimedJointAction(0, "t", None, "B", (Leg("MB", 0, 1),), 1, 1).proposal(state)
    assert ExecutionValidator().validate(state, candidate).accepted
    assert source_protection_failure(state, (candidate,), domain) is None
    result = solve_atomic_joint(state, (Bag("need", "B", "M", 1, 5),), domain=domain)
    assert result.complete and result.total_cost == pytest.approx(.1)
    assert result.first_bundles[0][0].destination_node == "B"


def test_shared_prefix_extra_guard_does_not_reject_loaded_optional_destination_field():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, source_protection_failure
    from scripts.experiments.ics_circulation_v3.joint_reference import TimedJointAction
    from scripts.experiments.ics_circulation_v3.model import Leg
    from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator
    state = Snapshot(0, Network({n: Node(n, n, n, capacity=2) for n in "AB"},
                               {"AB": Edge("AB", "A", "B", 1)}),
                     {"t": Tray("t", "A", "loaded", "b")}, {"b": Bag("b", "A", "B", 0, 5)},
                     module=FixedLocalModule(unload_ticks=0))
    proposal = replace(TimedJointAction(0, "t", "b", "B", (Leg("AB", 0, 1),), 1, 1).proposal(state), destination_node=None)
    assert ExecutionValidator().validate(state, proposal).accepted
    assert source_protection_failure(state, (proposal,), AtomicJointDomain(1, source_protection_contract="shared_forecast_prefix")) is None


def test_dependency_seed_does_not_grant_atomic_permission_to_sequential_domain():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
    from scripts.experiments.ics_circulation_v3.run_joint_seed_stress import cycle_scene
    initial = cycle_scene(size=2, waves=1)["initial"]
    result = solve_atomic_joint(initial, domain=AtomicJointDomain(2, dependency_seed=True, atomic_bundles=False))
    assert result.complete and result.total_cost == 20
    assert not result.first_bundles
    assert result.diagnostics["work_counts"]["dependency_seed_permission_rejections"] > 0


def test_partial_dependency_seed_cannot_be_claimed_as_completed_feasible_incumbent():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
    from scripts.experiments.ics_circulation_v3.run_joint_seed_stress import cycle_scene
    initial = cycle_scene(size=2, waves=1)["initial"]
    without = solve_atomic_joint(initial, domain=AtomicJointDomain(2, expansion_limit=40))
    with_seed = solve_atomic_joint(initial, domain=AtomicJointDomain(2, expansion_limit=40, dependency_seed=True))
    assert without.complete and without.total_cost == 0
    # Extra seed effort can hurt a very small budget. Retain this negative.
    assert not with_seed.complete and with_seed.total_cost == 20
    assert with_seed.gap is None and not with_seed.schedule
    assert with_seed.diagnostics["work_counts"]["dependency_seed_local_budget_exhausted"] == 1
    assert with_seed.diagnostics["work_counts"]["joint_states"] > 0


def test_complete_dependency_incumbent_is_physically_replayable_and_zero_bound_is_valid():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointDomain, solve_atomic_joint
    from scripts.experiments.ics_circulation_v3.joint_transactions import commit_joint_actions
    from scripts.experiments.ics_circulation_v3.run_joint_seed_stress import cycle_scene
    state = cycle_scene(size=3, waves=1)["initial"]
    result = solve_atomic_joint(state, domain=AtomicJointDomain(2, expansion_limit=320, dependency_seed=True))
    assert result.complete and result.total_cost == result.lower_bound == result.gap == 0
    assert result.diagnostics["work_counts"]["dependency_seed_admitted_trays"] == 3
    engine = Simulation(state, control_mode="external")
    for bundle in result.first_bundles:
        assert commit_joint_actions(engine, bundle).accepted
    assert len(engine.advance(2).completed) == 3


def test_current_bundle_incumbent_survives_budget_failure_of_later_wave_continuation():
    from scripts.experiments.ics_circulation_v3.joint_bundle_reference import AtomicJointMPC
    from scripts.experiments.ics_circulation_v3.joint_transactions import commit_joint_actions
    from scripts.experiments.ics_circulation_v3.run_joint_seed_stress import cycle_scene
    scene = cycle_scene()
    engine = Simulation(scene["initial"], scene["future"], control_mode="external")
    policy = AtomicJointMPC(planning_horizon=12, route_tail_ticks=1, expansion_limit=500, dependency_seed=False)
    plan = policy.plan(engine.observe(), tuple(f for f in scene["forecasts"] if f.published_at <= 0))
    assert len(plan.first_bundles) == 1 and len(plan.first_bundles[0]) == 3
    assert plan.diagnostics["work_counts"]["root_completion_local_budget_exhausted"] > 0
    assert plan.diagnostics["work_counts"]["passive_completion_tick"] > 0
    assert commit_joint_actions(engine, plan.first_bundles[0]).accepted
    result = engine.advance(2)
    assert len(result.completed) == 3
    assert not plan.complete and plan.gap is None  # No global prediction certificate.
