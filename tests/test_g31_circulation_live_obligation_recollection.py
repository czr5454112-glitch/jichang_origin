"""Pure bounded-policy checks using immutable actual96 endpoint fixtures.

These tests do not load native, run a physical projection, or certify a new
capture. Test doubles exercise authority gating without claiming real delivery.
"""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_g31_circulation_live_obligation_lifecycle_v2 import fixture, raw, validate, review
from scripts.experiments.g31_ics_circulation import live_obligation_recollection_policy as p
from scripts.experiments.g31_ics_circulation import live_obligation_recollection_adapter as a


def case(key='mechanism/vector_06', owner='B'):
    information = validate(key, owner)
    original = raw(key)
    decision = original['decisions'][owner][0]
    pending = deepcopy(decision['collection'])
    pending.update(recollection_index=0, policy_quiet_since=pending['at'])
    view = information['raw_endpoints']['view']
    before = original['calls'][:decision['predecision_call_prefix_count']]
    requests = {c['request']['request_id']: c for c in before if c['request']['owner_id'] == owner}
    endpoints = {r['request_id']: r for r in view['client_requests'] + view['client_commands']}
    owned = {}
    for identity, call in requests.items():
        ack = deepcopy(endpoints[identity].get('last_delivered_ack', {}))
        owned[identity] = {'request': deepcopy(call['request']), 'kind': call['kind'],
            'ack': ack, 'terminal': ack.get('status') in p.TERMINAL_BY_KIND.get(call['kind'], ())}
    return information, pending, view, owned


def own_l(information):
    own = information['raw_endpoints']['command']['last_delivered_ack']['planning_snapshot_v3']
    return next(t for t in own['capture']['capture_v2']['local_capture']['trays'] if t['tray_id'] == 'L')


def test_private_collector_retains_bytecode_and_old_globals():
    assert a._collect.__code__ is a.old.collect_native.__code__
    assert a._collect.__globals__ is not vars(a.old)
    assert a._collect.__globals__['validate_collected_endpoints'] is a.guard.validate_collected_endpoints
    assert a.old.collect_native.__globals__['validate_collected_endpoints'] is a.old.validate_collected_endpoints
    assert p.OwnerPolicy.return_tray is p.prior.OwnerPolicy.return_tray
    assert p.OwnerPolicy.route_tray is p.prior.OwnerPolicy.route_tray
    assert p.OwnerPolicy.activate is p.bound.OwnerPolicy.activate


def test_saved44_candidates_have_original_L_identity_and_finite_window_only():
    counts = {'A': 0, 'B': 0}; reasons = {}
    for key, row in review()['rows'].items():
        for stage in row['stages']:
            if stage['verified']: continue
            information, pending, view, owned = case(key, stage['owner'])
            if information['status'] != 'unknown': continue
            screen = p.retry_admission(information, pending, view, owned)
            assert screen['status'] == 'conditional_retry_admissible', (key, stage['owner'], screen)
            assert screen['native_success_certified'] is False
            counts[stage['owner']] += 1
            reasons[screen['reason']] = reasons.get(screen['reason'], 0) + 1
            if stage['owner'] == 'B':
                assert screen['nominal_epochs']['physical_wire'] < screen['retained_own_service_bound']
    assert counts == {'A': 4, 'B': 40}
    assert reasons == {'actual_owned_tray_changed_after_capture': 30,
                      'known_stationary_service_crossed_collection': 14}


@pytest.mark.parametrize('change', ['used', 'wrong_reason', 'wrong_owner', 'changed_view',
    'missing_peer', 'own_ack_id', 'source_owner', 'pending', 'missing_action', 'extra_action',
    'wrong_ack_time', 'coverage', 'unresolved', 'bad_ack_sequence'])
def test_recollection_fails_closed_on_missing_or_changed_action_and_endpoint_data(change):
    i, pending, view, owned = case()
    ext = i['raw_endpoints']['command']['last_delivered_ack']['planning_snapshot_v3']['capture']['capture_v2']['extension']
    physical = next(k for k, r in owned.items() if r['kind'] in p.PHYSICAL_KINDS)
    if change == 'used': pending['recollection_index'] = 1
    elif change == 'wrong_reason': i['reasons'] = ['invalid_v3_schema_or_digest']
    elif change == 'wrong_owner': view['owner_id'] = 'A'
    elif change == 'changed_view': view = deepcopy(view); view['now'] += .001
    elif change == 'missing_peer': pending['peer_message'] = 'missing'
    elif change == 'own_ack_id': i['raw_endpoints']['command']['last_delivered_ack']['result_id'] = 'other'
    elif change == 'source_owner': ext['source_owner'] = 'A'
    elif change == 'pending': owned[physical]['terminal'] = False
    elif change == 'missing_action': del owned[physical]
    elif change == 'extra_action': owned['new'] = deepcopy(owned[physical])
    elif change == 'wrong_ack_time': owned[physical]['ack']['delivered_at'] = view['now'] + .001
    elif change == 'coverage': ext['action_coverage']['complete_for_declared_scope'] = False
    elif change == 'unresolved': ext['action_coverage']['unresolved_request_ids'] = [physical]
    else: ext['submitted_physical_actions'][0]['last_delivered_ack']['sequence'] = True
    assert p.retry_admission(i, pending, view, owned)['status'] == 'not_admitted'


@pytest.mark.parametrize('field,value', [('generation', 99), ('traversal_id', 99),
    ('business_bag_id', 'reuse2'), ('node', 8), ('mode', 'loading'), ('edge_from', 7),
    ('edge_to', 8), ('reception_node', 8), ('committed_prefix', [7, 8]), ('available_at', 99.)])
def test_original_uncommitted_target_is_immutable(field, value):
    i, pending, view, owned = case()
    next(t for t in view['trays'] if t['tray_id'] == 'L')[field] = value
    assert p.retry_admission(i, pending, view, owned)['status'] == 'not_admitted'


@pytest.mark.parametrize('change', ['equal_wire', 'past_wire', 'bool_bound', 'unknown_bound', 'wrong_kind'])
def test_known_own_service_window_is_strict_and_never_created_from_available(change):
    i, pending, view, owned = case(); t = own_l(i)
    wire = p.sequential_epochs(view['now'])['physical_wire']
    if change == 'equal_wire': t['service_ready_at'] = wire
    elif change == 'past_wire': t['service_ready_at'] = wire - .001
    elif change == 'bool_bound': t['service_ready_at'] = True
    elif change == 'unknown_bound': t['service_ready_known'] = False
    else: t['ready_kind'] = 'empty_available_at'
    assert p.retry_admission(i, pending, view, owned)['status'] == 'not_admitted'


@pytest.mark.parametrize('change', ['future_bound', 'past_floor', 'unknown', 'wrong_prefix', 'wrong_kind'])
def test_deadline_reason_is_not_generic_permission_to_retry(change):
    i, pending, view, owned = case('mechanism/vector_02')
    envelopes = [i['raw_endpoints']['command']['last_delivered_ack']['planning_snapshot_v3'],
                 *i['raw_endpoints']['received']]
    t = next(t for e in envelopes for t in e['capture']['capture_v2']['local_capture']['trays'] if t['tray_id'] == 'E')
    if change == 'future_bound': t['service_ready_at'] = view['now'] + 1.
    elif change == 'past_floor': t['service_ready_at'] = pending['at'] - 1.
    elif change == 'unknown': t['service_ready_known'] = False
    elif change == 'wrong_prefix': t['committed_prefix'] = [4]
    else: t['ready_kind'] = 'observed_unload_completion'
    assert p.retry_admission(i, pending, view, owned)['status'] == 'not_admitted'


def test_A_empty_has_no_fabricated_future_service_deadline_and_keeps_absolute_return():
    i, pending, view, owned = case('insufficient_advance/vector_16', 'A')
    screen = p.retry_admission(i, pending, view, owned)
    assert screen['status'] == 'conditional_retry_admissible'
    assert screen['retained_own_service_bound'] is None
    now = screen['nominal_epochs']['pair_delivery']
    assert p.prior.return_earliest(now, .5, 0) == 7.84
    assert p.prior.return_earliest(now, 0., 1) == now
    view['now'] = 38.99
    assert p.retry_admission(i, pending, view, owned)['status'] == 'not_admitted'


def test_reply_limit_and_monotone_actual_identity():
    budget = p.PhaseReplyBudget()
    first = {'message_id': 'one', 'captured_at': 5., 'publication_sequence': 2}
    assert budget.admit('first_return', first)
    assert not budget.admit('first_return', first)
    assert not budget.admit('first_return', {**first, 'message_id': 'two'})
    assert not budget.admit('first_return', {**first, 'message_id': 'two', 'captured_at': 6.})
    assert budget.admit('first_return', {'message_id': 'two', 'captured_at': 6., 'publication_sequence': 3})
    assert not budget.admit('first_return', {'message_id': 'three', 'captured_at': 7., 'publication_sequence': 4})
    assert budget.admit('reuse1_loading_ack_refresh', first)
    assert not budget.admit('reuse1_loading_ack_refresh', {'message_id': 'two', 'captured_at': 6., 'publication_sequence': 3})
    assert not budget.admit(None, first)


@pytest.mark.parametrize('field,value', [('message_id', ''), ('captured_at', True),
    ('captured_at', float('nan')), ('publication_sequence', True), ('publication_sequence', 0)])
def test_malformed_invitation_never_consumes_or_grants_budget(field, value):
    budget = p.PhaseReplyBudget()
    data = {'message_id': 'one', 'captured_at': 5., 'publication_sequence': 1}; data[field] = value
    assert not budget.admit('first_return', data)
    assert budget.rows == {}


def test_saved_dict_and_caller_boolean_cannot_authorize_a_physical_choice():
    i, pending, view, owned = case()
    assert not a.is_native_attempt(i)
    assert not a.is_native_collected({**i, 'native_delivery_verified': True})
    assert p.fixed_choice({**i, 'status': 'conditional_native_delivered_later_v3_model_input',
                           'native_delivery_verified': True}, {})['selected_action'] is None
    with pytest.raises(ValueError): a.NativeCollectionAttempt(object(), i, object())


def test_seal_checks_time_content_and_handle_even_for_unknown(monkeypatch):
    # Explicit test-only handle verifier; no native object is created.
    monkeypatch.setattr(a.old, '_valid_handle', lambda native, session, accepted: accepted.enabled)
    session = SimpleNamespace(physical_time=1.)
    accepted = SimpleNamespace(_native=object(), _session=session, enabled=True)
    value = a.NativeCollectionAttempt(a._ATTEMPT_TOKEN, {'status': 'unknown',
        'reasons': ['owned_tray_changed_after_v3_capture'], 'native_read': {'at': 1.}}, accepted)
    assert a.is_native_attempt(value) and not a.is_native_collected(value)
    session.physical_time = 2.; assert not a.is_native_attempt(value)
    session.physical_time = 1.; accepted.enabled = False; assert not a.is_native_attempt(value)
    accepted.enabled = True; value['reasons'] = []; assert not a.is_native_attempt(value)


def test_json_attempt_copy_ignores_uncloneable_authority_attributes():
    class Data(dict):
        def __deepcopy__(self, memo): raise RuntimeError('capability must not be cloned')
    data = Data(status='unknown', rows=[{'x': 1}]); data.session = object()
    copied = a.json_data(data)
    assert type(copied) is dict and copied == data and not hasattr(copied, 'session')


def test_one_recollection_has_new_id_original_target_and_explicit_parent():
    i, pending, view, owned = case(); screen = p.retry_admission(i, pending, view, owned)
    policy = object.__new__(p.OwnerPolicy); policy.quiet_periods = []
    sent = []
    policy.publication = lambda label, causal: sent.append((label, deepcopy(causal))) or 'new-request'
    policy._begin_recollection(pending, screen, i, view)
    assert policy.pending['request_id'] == 'new-request'
    assert policy.pending['original_request_id'] == pending['request_id']
    assert policy.pending['trigger_tray'] == pending['trigger_tray']
    assert policy.pending['peer_message'] is None and policy.pending['recollection_index'] == 1
    assert sent[0][1]['predecessor_protocol_id'] == pending['request_id']
    assert sent[0][1]['continuation_parent_roots'] == [pending['root']]
    assert policy.pending['deadline'] <= screen['retained_own_service_bound']
    with pytest.raises(ValueError): policy._begin_recollection(policy.pending, screen, i, view)


def test_actual_failed_attempt_is_retained_and_second_failure_never_creates_third_pair(monkeypatch):
    information, pending, view, owned = case()
    policy = object.__new__(p.OwnerPolicy)
    policy.pending = pending; policy.peer_quiet_until = -1.
    policy.native = object(); policy.session = SimpleNamespace(physical_time=view['now'])
    policy.owner = 'B'; policy.accepted = object(); policy.ledger = object()
    policy.method = deepcopy(raw('mechanism/vector_06')['specification']['vector'])
    policy.collection_attempts = []; policy.decisions = []; policy.quiet_periods = []
    policy.client = SimpleNamespace(rows={pending['request_id']: {'ack': {'status': 'delivered'}}},
        owned=lambda owner: owned, calls=[1, 2, 3])
    publications = []; physical = []
    policy.publication = lambda label, causal: publications.append((label, deepcopy(causal))) or 'fresh'
    policy.route_tray = lambda view, tray, next_node, causal: physical.append(next_node)
    monkeypatch.setattr(a, 'collect_native', lambda *args, **kwargs: information)
    monkeypatch.setattr(a, 'is_native_attempt', lambda value: value is information)
    monkeypatch.setattr(a, 'is_native_collected', lambda value: False)
    policy.decide_pending(view)
    assert len(publications) == 1 and physical == [] and policy.decisions == []
    assert len(policy.collection_attempts) == 1
    assert policy.collection_attempts[0]['disposition'] == 'one_fresh_pair_requested'
    assert policy.collection_attempts[0]['information']['reasons'] == information['reasons']
    policy.pending['peer_message'] = 'fresh-peer'
    policy.client.rows['fresh'] = {'ack': {'status': 'delivered'}}
    policy.decide_pending(view)
    assert len(publications) == 1 and policy.pending is None
    assert len(policy.collection_attempts) == 2 and len(policy.decisions) == 1
    assert policy.decisions[0]['selected_action_admitted'] is False
    assert policy.decisions[0]['fallback_used'] is True and physical == [None]
    assert p.attempt_evidence({'B': policy})['B'] == policy.collection_attempts


@pytest.mark.parametrize('owner', ['A', 'B'])
def test_actual_reply_capture_does_not_qualify_as_a_new_invitation(owner):
    i, pending, view, owned = case('mechanism/vector_06', owner)
    envelope = i['raw_endpoints']['received'][0]
    assert p.bound.invitation_phase(envelope, owner, view['now']) is None


def test_unsealed_failure_never_requests_recollection(monkeypatch):
    information, pending, view, owned = case()
    policy = object.__new__(p.OwnerPolicy)
    policy.pending = pending; policy.peer_quiet_until = -1.
    policy.native = object(); policy.session = object(); policy.owner = 'B'
    policy.accepted = object(); policy.ledger = object(); policy.method = {}
    policy.collection_attempts = []; policy.decisions = []
    policy.client = SimpleNamespace(rows={pending['request_id']: {'ack': {'status': 'delivered'}}},
        owned=lambda owner: owned, calls=[])
    policy.publication = lambda *args: pytest.fail('unsealed dictionary cannot request a fresh pair')
    policy.route_tray = lambda *args: None
    monkeypatch.setattr(a, 'collect_native', lambda *args, **kwargs: information)
    policy.decide_pending(view)
    assert policy.pending is None and policy.decisions[0]['fallback_used'] is True
    assert policy.collection_attempts[0]['retry_admission']['status'] == 'not_admitted'
