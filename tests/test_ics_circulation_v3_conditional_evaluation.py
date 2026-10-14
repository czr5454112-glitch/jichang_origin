from dataclasses import replace

from scripts.experiments.ics_circulation_v3.conditional_evaluation import ConditionalCandidatePolicy, ConditionalAnalyticEvaluator
from scripts.experiments.ics_circulation_v3.learning import RoutingDemandForecast
from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.prebalance import known_supply, conditional_supply
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, actual_action_key, invalidate_conditional_forecasts


def state_with_hint(slow):
    nodes = {n: Node(n, 'z', 'r', capacity=4) for n in ('S', 'M', 'X', 'G', 'P', 'Q', 'Z')}
    edges = [Edge('SM', 'S', 'M', 1), Edge('MG', 'M', 'G', 1), Edge('MX', 'M', 'X', 2),
             Edge('XG', 'X', 'G', 3), Edge('PG', 'P', 'G', 2), Edge('PQ', 'P', 'Q', 4),
             Edge('QG', 'Q', 'G', 2), Edge('GZ', 'G', 'Z', 1)]
    state = Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                     {'t1': Tray('t1', 'S', 'loaded', 'b1'), 't2': Tray('t2', 'P', 'loaded', 'b2')},
                     {'b1': Bag('b1', 'S', 'G', 0, 50), 'b2': Bag('b2', 'P', 'G', 0, 50)})
    legs = (Leg('SM', 0, 1), Leg('MX', 1, 3), Leg('XG', 3, 6)) if slow else (Leg('SM', 0, 1), Leg('MG', 1, 2))
    end = legs[-1].arrive + 1
    full = RouteCandidate('hint', 'b1', 't1', legs, end, end, 0, 'hint', True, 'G')
    assert ExecutionValidator().commit(state, full, route_mode='next_edge').accepted
    candidates = (RouteCandidate('slow', 'b2', 't2', (Leg('PQ', 0, 4), Leg('QG', 4, 6)), 7, 7, state.version, 'slow', True, 'G'),
                  RouteCandidate('fast', 'b2', 't2', (Leg('PG', 0, 2),), 3, 3, state.version, 'slow', False, 'G'))
    assert all(ExecutionValidator().validate(state, c, route_mode='next_edge').accepted for c in candidates)
    return state, candidates


def test_same_physical_prefix_different_hint_can_change_later_routing_decision():
    fast_hint, first = state_with_hint(False)
    slow_hint, second = state_with_hint(True)
    assert fast_hint.plans['t1'].legs == slow_hint.plans['t1'].legs
    forecasts = (RoutingDemandForecast('demand', 'G', 'Z', 4, 100),)
    a = ConditionalCandidatePolicy(20, forecasts)(fast_hint, first)
    b = ConditionalCandidatePolicy(20, forecasts)(slow_hint, second)
    assert a.candidate_id == 'slow'
    assert b.candidate_id == 'fast'
    assert known_supply(fast_hint) == known_supply(slow_hint) == ()


def test_forecast_scoring_cannot_authorize_empty_export_from_loaded_tray():
    state, candidates = state_with_hint(False)
    before = state.clone()
    ConditionalCandidatePolicy(20, ())(state, candidates)
    assert state == before
    assert len(conditional_supply(state)) == 1
    forged = RouteCandidate('export', None, 't1', (), 0, 0, state.version, 'export', destination_node='S')
    assert not ExecutionValidator().validate(state, forged).accepted


def test_invalid_hint_is_not_used_and_candidate_identity_aliases_deduplicate():
    state, candidates = state_with_hint(False)
    invalidate_conditional_forecasts(state, 'observed_delay')
    candidates = tuple(replace(c, dependency_version=state.version) for c in candidates)
    alias = replace(candidates[0], candidate_id='alias', baseline_id='alias')
    assert actual_action_key(state, alias) == actual_action_key(state, candidates[0])
    policy = ConditionalCandidatePolicy(20, (RoutingDemandForecast('demand', 'G', 'Z', 4, 100),))
    selected = policy(state, (candidates[0], alias, candidates[1]))
    assert selected.candidate_id == 'fast'
    assert policy.history[-1]['distinct_interventions'] == 2
    assert policy.history[-1]['conditional_supply'] == []


def test_candidate_replaces_own_conditional_supply_without_double_counting():
    state, candidates = state_with_hint(False)
    # Evaluate another candidate for t1 only after reaching a legitimate boundary
    # is the caller's responsibility; this accounting unit verifies dedup itself.
    hint = state.conditional_forecasts['t1']
    own = RouteCandidate('own', 'b1', 't1', hint.witness_legs, hint.unload_complete,
                         hint.usable_at, state.version, 'own', destination_node='G')
    supplies = ConditionalAnalyticEvaluator(20)._supply(state, own)
    assert supplies['G'] == [hint.usable_at]
