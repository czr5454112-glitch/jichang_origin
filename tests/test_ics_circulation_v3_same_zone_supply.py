"""Authoring tests for the opt-in central supply baseline; old source untouched."""
from dataclasses import replace
import pytest

from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import (
    Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray,
)
from scripts.experiments.ics_circulation_v3.prebalance import PredictivePrebalancer, synthetic_prebalance_fixtures
from scripts.experiments.ics_circulation_v3.runtime import CandidateGenerator, ExecutionValidator, assert_invariants
from scripts.experiments.ics_circulation_v3.same_zone_supply import (
    GuardWorkBudget, SameZoneDemand, SameZoneSupplyPrebalancer, same_zone_service_guard,
)


def state(*, cross=True, donors=1):
    nodes = {n: Node(n, 'foreign' if n == 'X' else 'local', 'owner:' + n, 5) for n in 'ABCDX'}
    edges = [Edge('AB', 'A', 'B', 3, 2), Edge('XB', 'X', 'B', 12, 2),
             Edge('AC', 'A', 'C', 4, 2), Edge('DC', 'D', 'C', 1, 2), Edge('BA', 'B', 'A', 3, 2)]
    trays = {f'local:{i}': Tray(f'local:{i}', 'A') for i in range(donors)}
    if cross:
        trays['a_cross'] = Tray('a_cross', 'X')
    return Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}), trays, {})


def forecast(identity='target', node='B', at=10, published_at=0, count=1):
    return RoutingDemandForecast(identity, node, 'A', at, at + 30, count=count, published_at=published_at)


def controller(**kw):
    kw.setdefault('planning_budget_ms', None)
    kw.setdefault('planning_horizon', 40)
    return SameZoneSupplyPrebalancer(**kw)


def test_domains_are_ranked_together_before_cross_zone_commit_and_plan_is_private():
    s = state()
    before = s.clone()
    old = PredictivePrebalancer(planning_budget_ms=None).plan(s, (forecast(),))
    new = controller().plan(s, (forecast(),))
    assert old.proposals[0].tray_id == 'a_cross'
    assert new.proposals[0].tray_id == 'local:0'
    assert s == before
    ranked = new.diagnostics['candidate_comparisons'][0]['candidates']
    assert {r['domain'] for r in ranked} == {'same_zone', 'cross_zone'}
    assert new.diagnostics['search_calls_by_domain'] == {'cross_zone': 1, 'same_zone': 1}
    assert new.proposals[0].usable_at == 10  # latest feasible departure, no premature credit
    assert new.proposals[0].legs[0].depart == 7


@pytest.mark.parametrize('fixture_index', range(4))
def test_disabled_arm_retains_original_strong_policy_exactly(fixture_index):
    f = synthetic_prebalance_fixtures()[fixture_index]
    old = PredictivePrebalancer(planning_budget_ms=None).plan(f.snapshot, f.forecasts)
    new = controller(max_same_zone_candidates=0).plan(f.snapshot, f.forecasts)
    assert new.proposals == old.proposals
    assert new.diagnostics['search_calls'] == old.diagnostics['search_calls']


def test_visible_backlog_and_hold_are_real_and_cross_owner_labels_unchanged():
    s = state(cross=False)
    s.module = FixedLocalModule(hold_by_node={'B': 2})
    s.bags['waiting'] = Bag('waiting', 'B', 'A', 0, 30)
    plan = controller().plan(s, ())
    assert plan.proposals[0].usable_at == 5
    guard = plan.diagnostics['same_zone_guards'][0]
    assert guard['service_at'] == 5
    assert all(r['target_credit'] == 0 for r in guard['prefixes'] if r['tick'] < 5)
    assert guard['source_owner'] != guard['target_owner']
    assert s.network.nodes['A'].logistics_zone == s.network.nodes['B'].logistics_zone == 'local'


def test_identity_filter_publication_revision_ttl_and_visible_actual_precedence():
    s = state(cross=False)
    c = controller(max_forecast_age=4)
    assert not c.plan(s, (forecast(published_at=1),)).proposals
    s.now = 6
    assert not c.plan(s, (forecast(published_at=0),)).proposals
    original = forecast(published_at=3)
    cancellation = replace(original, published_at=4, count=0)
    assert not c.plan(s, (original, cancellation)).proposals
    s.bags['target:0'] = Bag('target:0', 'B', 'A', 6, 30)
    actual = c.plan(s, (original, cancellation))
    assert len(actual.proposals) == 1
    assert actual.diagnostics['demand_units'][0]['unit_id'] == 'target:0'
    assert len(actual.diagnostics['demand_units']) == 1
    s.completed['target:0'] = 6
    assert not c.plan(s, (original,)).proposals


def test_duplicate_identity_exact_dedup_and_conflict_fail_closed():
    s = state(cross=False)
    first = replace(forecast('f1'), unit_ids=('shared',))
    same = replace(first, forecast_id='f2')
    c = controller()
    plan = c.plan(s, (first, same))
    assert len(plan.diagnostics['demand_units']) == 1
    assert plan.diagnostics['duplicate_published_unit_ids_removed'] == ['shared']
    with pytest.raises(ValueError, match='conflicting published unit identity'):
        c.plan(s, (first, replace(same, node='C')))
    assert not s.plans


def test_two_targets_do_not_spend_one_donor_twice_and_two_donors_do_not_reuse_credit():
    one = controller().plan(state(cross=False), (forecast(count=2),))
    # Other known unit would lose its sole potential donor: fail conservatively.
    assert not one.proposals
    s = state(cross=False, donors=2)
    c = controller(forecasts=(forecast(count=2),))
    accepted = c(s)
    assert len(accepted) == 2 and len({r.tray_id for r in accepted}) == 2
    assert [r.dependency_version for r in accepted] == [0, 1]
    assert c(s) == ()
    assert_invariants(s)


def test_sole_future_source_demand_blocks_service_even_if_target_is_late():
    s = state(cross=False)
    s.bags['waiting'] = Bag('waiting', 'B', 'A', 0, 30)
    result = controller().plan(s, (forecast('source', 'A', 1),))
    assert not result.proposals
    assert any(r['reason'] == 'same_zone_would_degrade_other_prefix'
               for r in result.diagnostics['candidate_rejections'])


def test_temporal_guard_uses_paths_through_other_zones_without_relabeling():
    s = state(cross=False)
    del s.network.edges['AC']
    s.network.edges['AX'] = Edge('AX', 'A', 'X', 2, 2)
    s.network.edges['XC'] = Edge('XC', 'X', 'C', 2, 2)
    candidate, = CandidateGenerator().generate_empty(s, 'local:0', 'B', k=1)
    needs = (SameZoneDemand('target', 'B', 10, 'test'), SameZoneDemand('other', 'C', 0, 'test'))
    reason, details = same_zone_service_guard(s, candidate, needs, 'target')
    assert reason == 'same_zone_would_degrade_other_prefix'
    assert {'tray_id': 'local:0', 'node': 'C', 'at': 4} in details['earliest_service']
    assert s.network.nodes['X'].logistics_zone == 'foreign'


def test_budget_exhaustion_does_not_accept_partial_guard_or_disable_old_cross_arm():
    s = state()
    result = controller(max_guard_work=1).plan(s, (forecast(),))
    assert result.proposals[0].tray_id == 'a_cross'
    assert result.diagnostics['guard_work'] == 1
    assert any(r['reason'] == 'same_zone_guard_work_budget' for r in result.diagnostics['candidate_rejections'])
    for total in [1, 2]:
        result = controller(max_candidates=1, max_same_zone_candidates=total).plan(state(donors=3), (forecast(),))
        assert result.diagnostics['search_calls_by_domain'] == {'cross_zone': 1, 'same_zone': total}
        assert result.diagnostics['candidate_budget_omissions']['same_zone'] == 3 - total


def test_incomplete_guard_ledger_blocks_enhancement_without_dropping_source_protection():
    s = state()
    result = controller(max_guard_demand_units=1).plan(s, (forecast(), forecast('source', 'A', 12)))
    assert result.diagnostics['same_zone_enhancement_blocked'] == 'same_zone_demand_ledger_limit'
    assert result.diagnostics['search_calls_by_domain']['same_zone'] == 0
    assert result.proposals[0].tray_id == 'a_cross'


def test_target_traversal_limit_does_not_truncate_other_demand_protection():
    result = controller(max_demand_units=1).plan(state(cross=False), (forecast(at=5), forecast('source', 'A', 6)))
    assert len(result.diagnostics['demand_units']) == 2
    assert not result.proposals


def test_unadmitted_protected_blocks_only_extra_domain():
    s = state()
    s.bags['p'] = Bag('p', 'B', 'A', 0, 30, True)
    result = controller().plan(s, ())
    assert result.diagnostics['same_zone_enhancement_blocked'] == 'unadmitted_protected_obligation'
    assert result.diagnostics['unadmitted_protected_bag_ids'] == ['p']
    assert result.diagnostics['search_calls_by_domain']['same_zone'] == 0
    assert result.proposals[0].tray_id == 'a_cross'


def test_existing_empty_obligation_does_not_get_replaced_after_forecast_change():
    s = state()
    c = controller(forecasts=(forecast(),))
    accepted = c(s)
    assert accepted
    original = dict(s.plans)
    c.forecasts = (replace(forecast(), count=0),)
    assert c(s) == () and s.plans == original


def test_receiver_capacity_and_wrong_identity_remain_physical_rejections():
    s = state(cross=False)
    s.network.nodes['B'] = replace(s.network.nodes['B'], capacity=1)
    s.trays['occupied'] = Tray('occupied', 'B')
    result = controller().plan(s, (forecast(count=2),))
    assert not result.proposals
    assert any(r['reason'] == 'same_zone_search_no_candidate' for r in result.diagnostics['candidate_rejections'])

    class Wrong:
        def generate_empty(self, snapshot, tray_id, destination, k):
            candidate = CandidateGenerator().generate_empty(snapshot, tray_id, destination, k)[0]
            return (replace(candidate, tray_id='wrong'),)
    result = controller(generator_factory=Wrong).plan(state(cross=False), (forecast(),))
    assert not result.proposals
    assert result.diagnostics['candidate_rejections'][0]['reason'] == 'candidate_identity_or_destination_mismatch'


@pytest.mark.parametrize('value', [-1, True, 1.5])
def test_extra_budget_types_are_validated(value):
    with pytest.raises(ValueError):
        controller(max_same_zone_candidates=value)


def test_private_future_tape_cannot_be_given_to_policy():
    with pytest.raises(TypeError):
        controller().plan(state(), (), future_bags=())


def test_generator_budget_rejection_is_unknown_not_physical_infeasibility():
    class Exhausted:
        last_search_status = 'expansion_budget_exhausted'
        last_expansions = 7
        def generate_empty(self, *args, **kwargs):
            return ()
    result = controller(generator_factory=Exhausted).plan(state(cross=False), (forecast(),))
    assert result.diagnostics['search_calls'] == 1
    assert result.diagnostics['search_expansions'] == 7
    assert result.diagnostics['candidate_rejections'][0]['reason'] == 'same_zone_search_budget_unknown'


def test_guard_reports_explicit_finite_horizon_and_never_credits_before_service():
    s = state(cross=False)
    result = controller(planning_horizon=4).plan(s, (forecast(at=2),))
    guard = result.diagnostics['same_zone_guards'][0]
    assert guard['horizon_end'] == 4
    assert max(p['tick'] for p in guard['prefixes']) == 4
    assert all(p['target_credit'] == 0 for p in guard['prefixes'] if p['tick'] < 3)
