"""Saved-only synthetic checker inputs; no native, model or performance run."""
import copy
from types import FunctionType

import pytest

from scripts.experiments.g31_ics_circulation import verify_initial_single_capture_endpoints as v
from test_g31_circulation_preexisting_online_model import initial_pair


ENVELOPE = {'attempt_started_ns': 1, 'attempt_finished_ns': 100}
IDS = {'A': 'opaque without owner syntax', 'B': 'another opaque request'}


def transport():
    calls, outbox = [], {}
    for owner in ('A', 'B'):
        payload = {'request_id': IDS[owner], 'owner_id': owner, 'kind': 'planning_snapshot',
                   'target_owner': 'B' if owner == 'A' else 'A', 'message_delay': .01,
                   'publication_delay': .01, 'expiry': .21}
        calls.append({'at': .05, 'kind': 'planning_snapshot', 'retry': False,
                      'request': copy.deepcopy(payload), 'reply': {'status': 'submitted'}})
        outbox[IDS[owner]] = {'kind': 'planning_snapshot', 'request': payload, 'terminal': True}
    return calls, outbox


def success(owner):
    view, ack, received = initial_pair(owner, 0)
    value = v.original.initial.validate_pair(view, ack, received)
    assert value['status'] == 'conditional_validated_data'
    info = copy.deepcopy(value)
    info['status'] = 'conditional_native_delivered_model_input'
    info['native_delivery_verified'] = True
    info['native_read'] = {'owner': owner, 'at': .11, 'own_request_id': IDS[owner]}
    return {'information': info, 'endpoints': {'owner': owner, 'request_id': IDS[owner],
            'at': .11, 'view': view, 'command': {'request_id': IDS[owner],
            'kind': 'planning_snapshot', 'last_delivered_ack': ack}, 'received': received},
            'ledger': {'owner': owner}}


def incomplete(owner='B'):
    return {'information': {'status': 'unknown_handle', 'native_delivery_verified': False},
            'endpoints': {'owner': owner, 'request_id': IDS[owner]}, 'ledger': None,
            'capture_failure': {'status': 'unknown_incomplete_endpoint_collection',
                                'completed': [], 'active': None, 'started': []}}


def failed(index, owner='A'):
    names = ['view', 'command', 'received']
    values = {'view': {'owner_id': owner, 'now': .11},
              'command': {'request_id': IDS[owner], 'kind': 'planning_snapshot'},
              'received': {'malformed_but_retained': [1, -0.]}}
    prefix = {'owner': owner, 'request_id': IDS[owner]}
    prefix.update({name: values[name] for name in names[:index]})
    active = names[index] if index < 3 else None
    started = [{'endpoint': name, 'started_ns': 10+i} for i, name in
               enumerate(names[:index] + ([active] if active else []))]
    return {'information': None, 'endpoints': {'owner': owner, 'request_id': IDS[owner]},
            'ledger': None, 'capture_failure': {'status': 'unknown_failed_collection',
            'completed': names[:index], 'active': active, 'started': started,
            'error_type': 'RuntimeError', 'error': 'saved injected endpoint failure',
            'typed_returned_prefix': v.failure.representation.typed_failure_snapshot(
                {'information': None, 'endpoints': prefix})}}


def records():
    return {'A': [success('A'), success('A')], 'B': [success('B')]}


def review(rows=None, *, calls=None, outbox=None, envelope=None):
    default_calls, default_outbox = transport()
    return v.verify_records(records() if rows is None else rows,
        calls=default_calls if calls is None else calls,
        outbox=default_outbox if outbox is None else outbox,
        branch_envelope=ENVELOPE if envelope is None else envelope)


def reported():
    return {'status': 'closed', 'closed': True, 'warm_ms': 20., 'observed_within_100ms': True,
            'physical_fact': {'edge': [0, 2]}, 'outside_return_ns': 100,
            'full32_or_universal_100ms_certificate': False}


def test_original_success_function_full_namespace_and_all_three_slots():
    assert v.SUCCESS is v.original.endpoint_replay
    assert v.SUCCESS.__globals__ is vars(v.original)
    result = review()
    assert result['all_required_endpoints_conditionally_verified']
    assert len(result['records']) == 3 and result['missing_slots'] == []
    assert [r['ordinal'] for r in result['records']] == [0, 1, 2]
    assert result['planning_identity']['owners']['A']['request_id'] == IDS['A']
    assert not result['native_authority'] and not result['complete_branch_audit']


@pytest.mark.parametrize('index', range(4))
def test_each_exception_stage_retained_verified_unknown(index):
    rows = records(); rows['A'][0] = failed(index)
    result = review(rows)
    first = result['records'][0]
    assert first['status'] == 'verified_unknown_capture' and first['record_hash']['sha256']
    assert first['check']['completed'] == ['view', 'command', 'received'][:index]
    assert first['check']['branch_envelope_verified'] and not first['check']['closed']
    assert result['records'][1]['status'] == 'verified_conditional_endpoints'
    assert result['records'][2]['status'] == 'verified_conditional_endpoints'
    assert not result['all_required_endpoints_conditionally_verified']


def test_B_nonthrowing_incomplete_with_raw_failure_none_does_not_rewrite_history():
    raw = {'failure': None, 'root': reported(), 'business': {'completed': ['loaded']}}
    rows = records(); rows['B'][0] = incomplete()
    before = copy.deepcopy(raw)
    result = v.certify_reported_root(raw['root'], review(rows), root_replay_verified=True,
                                    business_facts=raw['business'])
    assert result['reported_root'] == before['root'] and raw == before
    assert result['reported_root']['closed'] is True
    assert not result['certified_root']['closed']
    assert not result['certified_root']['observed_within_100ms']
    assert not result['certified_root']['complete_100ms_certified']
    assert result['business_facts'] == raw['business']
    result['business_facts']['completed'].append('changed')
    result['reported_root']['physical_fact']['edge'].append(9)
    result['endpoint_report']['records'].clear()
    assert raw == before


@pytest.mark.parametrize('defect', ['prefix_order', 'clock_bool', 'clock_outside', 'wrong_view',
                                  'wrong_command', 'promoted_ledger', 'extra_record_field'])
def test_malformed_failure_is_invalid_not_verified_unknown_and_other_rows_continue(defect):
    row = failed(2)
    if defect == 'prefix_order': row['capture_failure']['completed'].reverse()
    elif defect == 'clock_bool': row['capture_failure']['started'][0]['started_ns'] = True
    elif defect == 'clock_outside': row['capture_failure']['started'][0]['started_ns'] = 0
    elif defect == 'promoted_ledger': row['ledger'] = {'owner': 'A'}
    elif defect == 'extra_record_field': row['invented'] = 'ignored?'
    else:
        decoded = v.failure.typed_decode(row['capture_failure']['typed_returned_prefix'])
        if defect == 'wrong_view': decoded['endpoints']['view']['owner_id'] = 'B'
        else: decoded['endpoints']['command']['request_id'] = 'record self-declared impostor'
        row['capture_failure']['typed_returned_prefix'] = v.failure.representation.typed_failure_snapshot(decoded)
    rows = records(); rows['A'][0] = row
    result = review(rows)
    assert result['records'][0]['status'] == 'invalid'
    assert result['records'][0]['error'] and result['records'][0]['record_hash']
    assert result['records'][1]['status'] == result['records'][2]['status'] == 'verified_conditional_endpoints'


def test_prefix_export_error_kept_unverified_and_unknown():
    row = failed(1); failure = row['capture_failure']
    del failure['typed_returned_prefix']; failure['prefix_export_error'] = 'MemoryError: partial export'
    result = review({'A': [row], 'B': []})
    assert result['records'][0]['status'] == 'verified_unknown_capture'
    assert result['records'][0]['check']['returned_payload_verified'] is False
    assert result['missing_slots'] == [{'owner': 'A', 'owner_ordinal': 1}, {'owner': 'B', 'owner_ordinal': 0}]


@pytest.mark.parametrize('defect', ['no_call', 'outbox_only', 'late', 'ambiguous', 'wrong_owner',
                                  'wrong_kind', 'wrong_target', 'retry_first', 'mutated_retry',
                                  'bool_time', 'reversed_time', 'outbox_changed'])
def test_identity_is_only_from_unique_actual_immutable_transport(defect):
    calls, outbox = transport()
    if defect == 'no_call': calls.clear(); outbox.clear()
    elif defect == 'outbox_only': calls.pop(0)
    elif defect == 'late': calls[0]['at'] = calls[1]['at'] = .12
    elif defect == 'ambiguous':
        extra = copy.deepcopy(calls[0]); extra['request']['request_id'] = 'second eligible A'
        calls.append(extra); outbox['second eligible A'] = {'kind': extra['kind'], 'request': extra['request']}
    elif defect == 'wrong_owner': calls[0]['request']['owner_id'] = 'B'
    elif defect == 'wrong_kind': calls[0]['kind'] = 'demand'
    elif defect == 'wrong_target': calls[0]['request']['target_owner'] = 'A'
    elif defect == 'retry_first': calls[0]['retry'] = True
    elif defect == 'mutated_retry':
        retry = copy.deepcopy(calls[0]); retry['retry'] = True; retry['at'] = .5
        retry['request']['expiry'] = 1.; calls.append(retry)
    elif defect == 'bool_time': calls[0]['at'] = True
    elif defect == 'reversed_time': calls[0]['at'] = .06
    elif defect == 'outbox_changed': outbox[IDS['A']]['request']['expiry'] = .22
    result = review(calls=calls, outbox=outbox)
    assert not result['all_required_endpoints_conditionally_verified']
    assert any(r['status'] == 'invalid' for r in result['records'])


def test_valid_retry_and_later_new_planning_do_not_replace_initial_identity():
    calls, outbox = transport()
    retry = copy.deepcopy(calls[0]); retry.update(retry=True, at=.5); calls.append(retry)
    later = copy.deepcopy(calls[0]); later['at'] = 1.; later['request']['request_id'] = 'later'
    calls.append(later); outbox['later'] = {'kind': later['kind'], 'request': later['request']}
    assert review(calls=calls, outbox=outbox)['all_required_endpoints_conditionally_verified']


@pytest.mark.parametrize('defect', ['record_self_id', 'record_owner', 'missing_success_field',
                                  'extra_success_field', 'unexpected_owner_empty', 'extra_record',
                                  'owner_container_not_list', 'missing_A', 'missing_B', 'container_not_dict'])
def test_shape_missing_denominators_and_success_binding(defect):
    rows = records()
    if defect == 'record_self_id': rows['A'][0]['endpoints']['request_id'] = 'impostor'
    elif defect == 'record_owner': rows['A'][0]['endpoints']['owner'] = 'B'
    elif defect == 'missing_success_field': del rows['A'][0]['endpoints']['at']
    elif defect == 'extra_success_field': rows['A'][0]['extra'] = 1
    elif defect == 'unexpected_owner_empty': rows['C'] = []
    elif defect == 'extra_record': rows['B'].append(success('B'))
    elif defect == 'owner_container_not_list': rows['A'] = rows['A'][0]
    elif defect == 'missing_A': del rows['A']
    elif defect == 'missing_B': del rows['B']
    elif defect == 'container_not_dict': rows = []
    result = review(rows)
    assert not result['all_required_endpoints_conditionally_verified']
    if defect == 'extra_record': assert result['record_count'] == 4 and result['records'][-1]['status'] == 'invalid'


@pytest.mark.parametrize('envelope', [{}, {'attempt_started_ns': True, 'attempt_finished_ns': 100},
                                    {'attempt_started_ns': 101, 'attempt_finished_ns': 100}])
def test_actual_branch_envelope_required(envelope):
    result = review(envelope=envelope)
    assert result['problems'][0]['stage'] == 'branch_envelope'
    assert all(row['status'] == 'invalid' for row in result['records'])


@pytest.mark.parametrize('error', [MemoryError('resource'), RuntimeError('unexpected'), RecursionError('depth')])
def test_unexpected_checker_error_is_audit_error_not_passed_unknown(monkeypatch, error):
    original = v._dispatch
    def injected(record, **kwargs):
        if record.get('capture_failure'): raise error
        return original(record, **kwargs)
    monkeypatch.setattr(v, '_dispatch', injected)
    rows = records(); rows['A'][0] = failed(0)
    result = review(rows)
    assert result['records'][0]['status'] == 'audit_error'
    assert result['records'][0]['error']['type'] == type(error).__name__
    assert result['records'][1]['status'] == 'verified_conditional_endpoints'


def test_hash_preserves_types_order_float_bits_and_failed_unicode():
    values = [1, 1., True, 0., -0., (1,), [1], {'a': 1, 'b': 2}, {'b': 2, 'a': 1}, '\ud800']
    assert len({v.record_hash(value)['sha256'] for value in values}) == len(values)
    assert v.record_hash(float('nan'))['sha256']
    cycle = []; cycle.append(cycle)
    with pytest.raises(ValueError): v.record_hash(cycle)


@pytest.mark.parametrize('warm,claimed,closed,verified', [(20., True, True, True), (101., False, True, True),
    (20., True, False, True), (20., True, True, False), (True, True, True, True), (float('nan'), True, True, True)])
def test_root_conjunction_never_upgrades_history_or_clock(warm, claimed, closed, verified):
    original = reported(); original.update(warm_ms=warm, observed_within_100ms=claimed, closed=closed)
    result = v.certify_reported_root(original, review(), root_replay_verified=verified)
    expected = type(warm) is float and warm == 20. and claimed and closed and verified
    assert result['certified_root']['observed_within_100ms'] is expected
    assert result['reported_root']['closed'] is closed
    assert result['certified_root']['complete_100ms_certified'] is False


def test_missing_reported_root_and_nonboolean_caller_verdict():
    assert not v.certify_reported_root(None, review(), root_replay_verified=False)['certified_root']['closed']
    with pytest.raises(ValueError): v.certify_reported_root(reported(), review(), root_replay_verified=1)


def test_no_input_mutation_alias_or_checker_namespace_reconstruction():
    rows, (calls, outbox) = records(), transport()
    before = v.typed_bytes((rows, calls, outbox))
    result = review(rows, calls=calls, outbox=outbox)
    assert v.typed_bytes((rows, calls, outbox)) == before
    result['planning_identity']['owners']['A']['request_id'] = 'mutated result'
    assert calls[0]['request']['request_id'] == IDS['A']
    assert v.SUCCESS.__closure__ is v.original.endpoint_replay.__closure__


def test_source_drift_rejected(monkeypatch):
    fn = v.original.endpoint_replay
    clone = FunctionType(fn.__code__, dict(fn.__globals__), fn.__name__, fn.__defaults__, fn.__closure__)
    monkeypatch.setattr(v.original, 'endpoint_replay', clone)
    with pytest.raises(ValueError, match='checker_identity_changed'): review()
