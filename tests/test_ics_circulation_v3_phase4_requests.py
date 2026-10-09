"""Explicit optimization requests exercise owner-authorized atomic suffixes."""
from dataclasses import asdict, replace
import json

from scripts.experiments.ics_circulation_v3.model import Bag, Edge, Leg, Network, Node, RouteCandidate, Snapshot, Tray
from scripts.experiments.ics_circulation_v3.request_service import AttemptFault, ResourceOwner, RouteRequest, RoutingRequestService, TransportScript
from scripts.experiments.ics_circulation_v3.routing import RegionalCandidateGenerator
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, Simulation, assert_invariants


def future_route(*, authorized=True, protected=False):
    nodes = {n: Node(n, 'z', 'r', capacity=4) for n in ('S', 'U', 'V', 'G')}
    edges = [Edge('SU', 'S', 'U', 1), Edge('UG', 'U', 'G', 1),
             Edge('SV', 'S', 'V', 3), Edge('VG', 'V', 'G', 3)]
    state = Snapshot(0, Network(nodes, {e.edge_id: e for e in edges}),
                     {'t': Tray('t', 'S', 'loaded', 'b')},
                     {'b': Bag('b', 'S', 'G', 0, 40, protected=protected)})
    if authorized:
        state.replaceable_trays = ('t',)
    candidate = RouteCandidate('old', 'b', 't', (Leg('SV', 5, 8), Leg('VG', 8, 11)),
                               12, 12, 0, 'old', True, 'G')
    assert ExecutionValidator().commit(state, candidate).accepted
    return state


def service(owner, **kwargs):
    return RoutingRequestService(owner, generator_factory=lambda: RegionalCandidateGenerator(
        horizon=30, deadline_ms=None, dynamic_local=True), **kwargs)


def update(request_id='update', **kwargs):
    return RouteRequest(request_id, 'b', 't', route_mode='whole_route',
                        intent='update_suffix', trigger_reason='explicit_congestion_optimization', **kwargs)


def test_explicit_update_searches_even_when_old_complete_route_is_valid():
    owner = ResourceOwner(future_route())
    result = service(owner).handle(update())
    assert result.status == 'updated_route_success', result.reason
    assert owner.snapshot().plans['t'].unload_complete == 3
    assert result.attempts_trace[0]['replacement']['frozen_legs'] == []
    assert result.attempts_trace[0]['distinct_actual_actions'] >= 1
    assert_invariants(owner.snapshot())


def test_update_requires_owner_permission_and_keeps_old_route_on_refusal():
    state = future_route(authorized=False)
    owner = ResourceOwner(state)
    result = service(owner).handle(update())
    assert result.status == 'suffix_update_failed_old_route_kept'
    assert not result.owner_committed
    assert owner.snapshot() == state


def test_protected_full_commitment_is_not_replaced_by_optimization_request():
    state = future_route(protected=True)
    owner = ResourceOwner(state)
    result = service(owner).handle(update())
    assert result.status == 'suffix_update_failed_old_route_kept'
    assert owner.snapshot() == state


def test_new_keep_and_update_are_distinct_request_intents():
    state = future_route()
    for intent, expected in [('ensure_route', 'still_valid_old_route'),
                             ('keep_valid', 'still_valid_old_route'), ('new_route', 'commit_failure')]:
        owner = ResourceOwner(state)
        result = service(owner).handle(RouteRequest(intent, 'b', 't', intent=intent))
        assert result.status == expected
        assert owner.snapshot() == state


def test_failed_scoring_cannot_release_owned_old_resources():
    owner = ResourceOwner(future_route())
    before = owner.snapshot()
    def invalid_choice(state, candidates, features):
        return replace(candidates[0], candidate_id='not-generated')
    result = service(owner, selector=invalid_choice).handle(update())
    assert result.status == 'suffix_update_failed_old_route_kept'
    assert owner.snapshot() == before


def test_lost_update_ack_replays_once_and_preserves_update_classification():
    owner = ResourceOwner(future_route())
    request = update(max_attempts=1)
    first = service(owner).handle(request, TransportScript((AttemptFault(lose_acknowledgement=True),)))
    assert first.status == 'communication_failure' and first.owner_committed
    accepted = owner.snapshot()
    second = service(owner).handle(request)
    assert second.status == 'updated_route_success' and second.receipt_replayed
    assert owner.snapshot() == accepted


def test_reused_request_id_cannot_change_intent():
    owner = ResourceOwner(future_route())
    keep = RouteRequest('same-id', 'b', 't', intent='keep_valid')
    assert service(owner).handle(keep).status == 'still_valid_old_route'
    result = service(owner).handle(update('same-id'))
    assert not result.owner_committed
    assert result.reason == 'request_id_collision'


def test_closed_future_edge_can_be_replaced_without_erasing_failure():
    state = future_route()
    state.network.edges['SV'] = replace(state.network.edges['SV'], capacity=0)
    state.version += 1
    owner = ResourceOwner(state)
    result = service(owner).handle(update())
    assert result.status == 'updated_route_success', result.reason
    assert all(leg.edge_id != 'SV' for leg in owner.snapshot().plans['t'].legs)
    assert_invariants(owner.snapshot())


def test_inflight_edge_is_preserved_and_only_after_arrival_suffix_changes():
    state = future_route()
    # Let the original long first segment really enter the physical engine.
    engine = Simulation(state, route_mode='whole_route', reactive_empty_dispatch=False)
    engine.advance(6)
    initial = engine.state.clone()
    assert initial.trays['t'].node is None
    # An alternate edge leaving the future safe anchor allows a real update.
    initial.network.edges['VU'] = Edge('VU', 'V', 'U', 1)
    initial.version += 1
    owner = ResourceOwner(initial)
    result = service(owner).handle(update())
    assert result.status == 'updated_route_success', result.reason
    changed = owner.snapshot()
    assert changed.trays['t'] == initial.trays['t']
    assert changed.plans['t'].legs[0] == initial.plans['t'].legs[0]
    assert result.attempts_trace[0]['replacement']['anchor_time'] == 8
    finished = Simulation(changed, route_mode='whole_route').advance(20)
    assert finished.completed['b'] == 11


def test_request_result_is_json_serializable_with_actual_action_keys():
    result = service(ResourceOwner(future_route())).handle(update())
    encoded = json.dumps(asdict(result), allow_nan=False)
    assert 'actual_action_keys' in encoded


def test_future_anchor_does_not_advance_scoring_observation_or_reveal_new_messages():
    engine = Simulation(future_route(), route_mode='whole_route', reactive_empty_dispatch=False)
    state = engine.advance(6).final_snapshot
    seen = []
    def feature(observation, candidate):
        seen.append(('feature', observation.now))
        assert observation.trays['t'].node is None
        assert candidate.legs[0].depart >= 8
        return {'published_at_7_is_visible': observation.now >= 7}
    def choose(observation, candidates, features):
        seen.append(('score', observation.now))
        assert not any(f['published_at_7_is_visible'] for f in features)
        return candidates[0]
    result = service(ResourceOwner(state), feature_builder=feature, selector=choose).handle(update())
    assert result.status == 'updated_route_success', result.reason
    assert seen and all(t == 6 for _, t in seen)
    assert result.attempts_trace[0]['replacement']['anchor_time'] == 8


def test_owner_rejects_unknown_intent_even_without_service_frontend():
    state = future_route()
    state.plans.clear()
    state.reservations = ()
    owner = ResourceOwner(state)
    observation, summary = owner.observe()
    candidate = RegionalCandidateGenerator(deadline_ms=None).generate(observation, 'b', 't', 1)[0]
    malformed = RouteRequest('bad-intent', 'b', 't', intent='implicit_replace')
    assert owner.revalidate(candidate, malformed, summary).reason == 'invalid_request_intent'
    result, receipt, _ = owner.commit(candidate, malformed)
    assert result.reason == 'invalid_request_intent' and receipt is None
    assert owner.snapshot() == state
