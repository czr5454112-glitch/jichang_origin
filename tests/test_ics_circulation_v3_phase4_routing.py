from dataclasses import replace

import pytest

from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator, clear_static_cache
from scripts.experiments.ics_circulation_v3.routing_reference import FullGraphReferenceGenerator
from scripts.experiments.ics_circulation_v3.run_phase4_routing import internal_bypass_case, no_wait_case, no_wait_cycle_case, routing_cases
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, assert_invariants


def test_authorized_internal_bypass_counterexample_and_opt_in_fix():
    case = internal_bypass_case()
    assert len(case.state.plans) == 5
    assert_invariants(case.state)
    initial = case.state.clone()
    old = RegionalCandidateGenerator(horizon=4, deadline_ms=None, dynamic_local=False)
    assert old.generate(case.state, "bag", "target", 3) == ()
    assert old.last_search_status == "bounded_no_candidate"
    dynamic = RegionalCandidateGenerator(horizon=4, deadline_ms=None, dynamic_local=True)
    candidates = dynamic.generate(case.state, "bag", "target", 3)
    assert candidates and candidates[0].legs[-1].arrive == 4
    assert tuple(leg.edge_id for leg in candidates[0].legs) == ("S-V", "V-G")
    assert dynamic.last_diagnostics["local_search_calls"] > 0
    assert all(ExecutionValidator().validate(case.state, c).accepted for c in candidates)
    assert case.state == initial
    assert ExecutionValidator().commit(case.state, candidates[0]).accepted


def test_strong_reference_and_finite_integer_oracle_recover_same_earliest_bypass():
    case = internal_bypass_case()
    for integer in (False, True):
        reference = FullGraphReferenceGenerator(horizon=4, deadline_ms=None, integer_ticks=integer)
        candidates = reference.generate(case.state, "bag", "target", 1)
        assert candidates[0].legs[-1].arrive == 4
        assert reference.last_diagnostics["earliest_arrival_certified"] is integer
        assert reference.last_diagnostics["static_lower_bound"] == 2


def test_dynamic_and_strong_search_preserve_upstream_wait_for_cross_region_no_wait_chain():
    case = no_wait_case()
    for generator in (RegionalCandidateGenerator(horizon=7, deadline_ms=None, dynamic_local=True),
                      FullGraphReferenceGenerator(horizon=7, deadline_ms=None),
                      FullGraphReferenceGenerator(horizon=7, deadline_ms=None, integer_ticks=True)):
        candidates = generator.generate(case.state, "bag", "target", 3)
        assert candidates and candidates[0].legs[-1].arrive == 6
        assert candidates[0].legs[0].depart == 2
        assert candidates[0].legs[0].arrive == candidates[0].legs[1].depart
        assert all(ExecutionValidator().validate(case.state, c).accepted for c in candidates)


def test_zero_capacity_future_edge_is_closed_without_disabling_legal_bypass():
    case = next(c for c in routing_cases() if c.name == "zero_capacity_short_edge_bypass")
    for generator in (RegionalCandidateGenerator(horizon=5, deadline_ms=None),
                      RegionalCandidateGenerator(horizon=5, deadline_ms=None, dynamic_local=True),
                      FullGraphReferenceGenerator(horizon=5, deadline_ms=None)):
        candidates = generator.generate(case.state, "bag", "target", 1)
        assert candidates and candidates[0].legs[-1].arrive == 4
        assert all(leg.edge_id != "S-U" for c in candidates for leg in c.legs)
    case.state.network.edges["S-U"] = replace(case.state.network.edges["S-U"], capacity=-1)
    with pytest.raises(ValueError, match="nonnegative"):
        RegionalCandidateGenerator(dynamic_local=True).generate(case.state, "bag", "target")


def test_cold_preprocessing_consumes_shared_budget_and_cannot_leave_partial_cache():
    case = internal_bypass_case()
    clear_static_cache()
    limited = RegionalCandidateGenerator(horizon=4, expansion_limit=1, deadline_ms=None, dynamic_local=True)
    assert limited.generate(case.state, "bag", "target") == ()
    assert limited.last_search_status == "expansion_budget_exhausted"
    assert limited.last_diagnostics["work_units_by_stage"] == {"topology_edges": 1}
    assert limited.last_expansions == 1
    enough = RegionalCandidateGenerator(horizon=4, deadline_ms=None, dynamic_local=True)
    assert enough.generate(case.state, "bag", "target")
    assert enough.last_diagnostics["cold_topology"]
    hot = RegionalCandidateGenerator(horizon=4, deadline_ms=None, dynamic_local=True)
    assert hot.generate(case.state, "bag", "target")
    assert not hot.last_diagnostics["cold_topology"]
    assert hot.last_expansions < enough.last_expansions


@pytest.mark.parametrize("dynamic", [False, True])
def test_deadline_and_exhaustion_are_not_infeasibility(dynamic):
    case = internal_bypass_case()
    clear_static_cache()
    generator = RegionalCandidateGenerator(horizon=4, deadline_ms=1e-12, dynamic_local=dynamic)
    assert generator.generate(case.state, "bag", "target") == ()
    assert generator.last_search_status == "deadline_exhausted"
    assert generator.last_diagnostics["missing_candidate_is_not_infeasibility"]
    oracle = FullGraphReferenceGenerator(horizon=4, expansion_limit=1, deadline_ms=None, integer_ticks=True)
    assert oracle.generate(case.state, "bag", "target") == ()
    assert oracle.last_search_status == "expansion_budget_exhausted"
    assert not oracle.last_diagnostics["earliest_arrival_certified"]
    assert not oracle.last_diagnostics["finite_horizon_exhausted"]


def test_integer_oracle_enumerates_all_small_dag_departure_windows():
    case = internal_bypass_case(0, horizon=4)
    oracle = FullGraphReferenceGenerator(horizon=4, expansion_limit=20000, deadline_ms=None, integer_ticks=True)
    candidates = oracle.generate(case.state, "bag", "target", 256)
    assert oracle.last_diagnostics["finite_horizon_exhausted"]
    assert not oracle.last_diagnostics.get("state_label_truncations", 0)
    short = [c for c in candidates if tuple(leg.edge_id for leg in c.legs) == ("S-U", "U-G")]
    # depart(S)=0/1/2, depart(U)>=depart(S)+1, final arrival<=4.
    assert len(short) == 6
    assert len(candidates) == 7  # plus the length-four bypass with no waiting
    assert min(c.legs[-1].arrive for c in candidates) == 2


def test_dynamic_cache_uses_current_reservations_and_candidates_have_unique_owned_ids():
    free = internal_bypass_case(0, horizon=4)
    busy = internal_bypass_case(5, horizon=4)
    generator = RegionalCandidateGenerator(horizon=4, deadline_ms=None, dynamic_local=True)
    assert generator.generate(free.state, "bag", "target", 3)[0].legs[-1].arrive == 2
    candidates = generator.generate(busy.state, "bag", "target", 3)
    assert candidates[0].legs[-1].arrive == 4
    assert len({candidate.legs for candidate in candidates}) == len(candidates)
    assert candidates[0].is_baseline and candidates[0].baseline_id == candidates[0].candidate_id
    assert all(candidate.baseline_id == candidates[0].candidate_id for candidate in candidates)


def test_finite_integer_oracle_keeps_cycle_time_states_and_certifies_horizon_boundary():
    case = no_wait_cycle_case()
    oracle = FullGraphReferenceGenerator(horizon=7, deadline_ms=None, integer_ticks=True)
    candidates = oracle.generate(case.state, "bag", "target", 256)
    assert len(candidates) == 1 and candidates[0].legs[-1].arrive == 7
    assert tuple(leg.edge_id for leg in candidates[0].legs) == ("S-A", "A-S", "S-A", "A-S", "S-G")
    assert oracle.last_diagnostics["earliest_arrival_certified"]
    assert oracle.last_diagnostics["finite_horizon_exhausted"]
    short = FullGraphReferenceGenerator(horizon=6, deadline_ms=None, integer_ticks=True)
    assert short.generate(case.state, "bag", "target", 256) == ()
    assert short.last_diagnostics["finite_horizon_exhausted"]
    assert not short.last_diagnostics["earliest_arrival_certified"]


def test_dynamic_empty_api_and_protected_deadline_keep_execution_contract():
    from scripts.experiments.ics_circulation_v3.model import Tray
    case = internal_bypass_case()
    case.state.trays["target"] = Tray("target", "S")
    case.state.bags.clear()
    dynamic = RegionalCandidateGenerator(horizon=4, deadline_ms=None, dynamic_local=True)
    empty = dynamic.generate_empty(case.state, "target", "G", 2)
    assert empty and empty[0].bag_id is None
    assert ExecutionValidator().commit(case.state, empty[0]).accepted
    case = internal_bypass_case()
    case.state.bags["bag"] = replace(case.state.bags["bag"], protected=True, deadline=3)
    assert dynamic.generate(case.state, "bag", "target", 2) == ()


def test_diagnostic_runner_refuses_to_overwrite_prior_evidence(tmp_path):
    from scripts.experiments.ics_circulation_v3.run_phase4_routing import run
    marker = tmp_path / "summary.json"
    marker.write_text("preserve this record", encoding="utf-8")
    with pytest.raises(ValueError, match="historical evidence"):
        run(tmp_path)
    assert marker.read_text(encoding="utf-8") == "preserve this record"


def test_terminal_invalid_labels_do_not_evict_legal_reception_bypass_at_same_local_cap():
    case = next(c for c in routing_cases() if c.name == "destination_reception_window")
    dynamic = RegionalCandidateGenerator(horizon=case.horizon, deadline_ms=None,
                                          dynamic_local=True, local_label_limit=3)
    candidates = dynamic.generate(case.state, "bag", "target", 3)
    assert {tuple(leg.edge_id for leg in c.legs) for c in candidates} == {("S-U", "U-G"), ("S-V", "V-G")}
    # Both arrive at 5; longer movement consumes less weighted waiting here.
    costs = [sum(leg.arrive - leg.depart for leg in c.legs) +
             2 * (c.legs[-1].arrive - sum(leg.arrive - leg.depart for leg in c.legs)) for c in candidates]
    assert min(costs) == 6


def test_fixed_local_cap_retains_path_diversity_when_short_path_has_extra_time_windows():
    from scripts.experiments.ics_circulation_v3.model import Edge, Leg, Node, RouteCandidate, Tray
    case = internal_bypass_case(0, horizon=6)
    case.state.network.nodes["X"] = Node("X", "zone", "local", capacity=10)
    case.state.network.edges["S-X"] = Edge("S-X", "S", "X", 1)
    for i in range(2):
        tray = f"clock:{i}"
        case.state.trays[tray] = Tray(tray, "S")
        plan = RouteCandidate(tray, None, tray, (Leg("S-X", i, i + 1),), i + 1, i + 1,
                              case.state.version, tray, True, "X")
        assert ExecutionValidator().commit(case.state, plan).accepted
    dynamic = RegionalCandidateGenerator(horizon=6, deadline_ms=None, dynamic_local=True, local_label_limit=2)
    candidates = dynamic.generate(case.state, "bag", "target", 2)
    assert len(candidates) == 2
    assert {tuple(leg.edge_id for leg in c.legs) for c in candidates} == {("S-U", "U-G"), ("S-V", "V-G")}
