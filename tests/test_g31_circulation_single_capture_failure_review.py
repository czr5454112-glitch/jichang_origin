"""Failed evidence structure only; no native authority or model execution."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import verify_initial_single_capture_failure as v
from test_g31_circulation_initial_owner_route_single_capture import fixture, pure_candidate, c


def failed(tmp_path, index):
    native, Session = fixture(tmp_path)
    session = Session()
    session.values['command'].update(request_id='pure', kind='planning_snapshot')
    session.failure = (c._FIELDS[index], RuntimeError('query rejected'))
    records = []
    with pytest.raises(RuntimeError, match='query rejected'):
        pure_candidate()(records, native, session, 'A', 'pure', accepted=object())
    return records[0]


def review(record, **kwargs):
    return v.verify(record, owner='A', request_id='pure', **kwargs)


@pytest.mark.parametrize('index', range(3))
def test_actual_prototype_query_exceptions_are_retained_unknown(tmp_path, index):
    record = failed(tmp_path, index)
    clocks = record['capture_failure']['started']
    envelope = {'attempt_started_ns': clocks[0]['started_ns'],
                'attempt_finished_ns': clocks[-1]['started_ns']}
    result = review(record, branch_envelope=envelope)
    assert result['completed'] == list(c._FIELDS[:index])
    assert result['active'] == c._FIELDS[index]
    assert result['returned_payload_verified'] and result['branch_envelope_verified']
    assert not result['closed'] and result['root_must_remain_unknown']
    assert not result['endpoint_durations_available'] and not result['complete_branch_audit']


def test_public_authority_rejection_zero_endpoints(tmp_path):
    native, Session = fixture(tmp_path)
    records = []
    c.captured_collection(records, native, Session(), 'A', 'pure', accepted=object())
    result = review(records[0])
    assert result['started_count'] == 0 and result['completed'] == []
    assert result['failure_status'] == 'unknown_incomplete_endpoint_collection'
    assert not result['branch_envelope_verified'] and result['root_must_remain_unknown']


def test_after_all_returns_normalizer_exception_keeps_full_typed_payload(tmp_path):
    native, Session = fixture(tmp_path)
    session = Session()
    session.values['command'].update(request_id='pure', kind='planning_snapshot')
    def reject(_):
        raise ValueError('normalization injected')
    fn = c.clone(c.captured_collection, {**pure_candidate().__globals__, '_NORMALIZE': reject})
    records = []
    with pytest.raises(ValueError, match='normalization injected'):
        fn(records, native, session, 'A', 'pure', accepted=object())
    result = review(records[0])
    assert result['completed'] == list(c._FIELDS) and result['active'] is None
    assert result['returned_payload_verified'] and not result['closed']


def test_failed_export_is_explicitly_unverified(tmp_path):
    record = failed(tmp_path, 2)
    failure = record['capture_failure']
    del failure['typed_returned_prefix']
    failure['prefix_export_error'] = 'ValueError: failed_evidence_limit'
    result = review(record)
    assert result['completed'] == ['view', 'command']
    assert not result['returned_payload_verified'] and result['root_must_remain_unknown']


@pytest.mark.parametrize('defect', [
    'reordered', 'duplicate', 'extra', 'wrong_active', 'missing_start',
    'bool_clock', 'negative_clock', 'reversed_clock', 'extra_duration',
    'missing_error', 'false_status', 'promoted_ledger', 'wrong_record_owner',
    'wrong_typed_owner', 'wrong_typed_id', 'wrong_view_owner', 'wrong_command_id',
    'unexpected_prefix', 'changed_information',
])
def test_structural_or_binding_corruption_is_rejected(tmp_path, defect):
    record = failed(tmp_path, 2)
    failure = record['capture_failure']
    if defect == 'reordered': failure['completed'].reverse()
    elif defect == 'duplicate': failure['completed'] = ['view', 'view']
    elif defect == 'extra': failure['completed'].extend(['received', 'extra'])
    elif defect == 'wrong_active': failure['active'] = 'command'
    elif defect == 'missing_start': failure['started'].pop()
    elif defect == 'bool_clock': failure['started'][0]['started_ns'] = True
    elif defect == 'negative_clock': failure['started'][0]['started_ns'] = -1
    elif defect == 'reversed_clock': failure['started'][0]['started_ns'] = failure['started'][-1]['started_ns'] + 1
    elif defect == 'extra_duration': failure['started'][0]['finished_ns'] = failure['started'][0]['started_ns']
    elif defect == 'missing_error': del failure['error']
    elif defect == 'false_status': failure['status'] = 'closed_success'
    elif defect == 'promoted_ledger': record['ledger'] = {'owner': 'A'}
    elif defect == 'wrong_record_owner': record['endpoints']['owner'] = 'B'
    elif defect == 'changed_information': record['information'] = {'status': 'invented'}
    else:
        decoded = v.typed_decode(failure['typed_returned_prefix'])
        endpoint = decoded['endpoints']
        if defect == 'wrong_typed_owner': endpoint['owner'] = 'B'
        elif defect == 'wrong_typed_id': endpoint['request_id'] = 'other'
        elif defect == 'wrong_view_owner': endpoint['view']['owner_id'] = 'B'
        elif defect == 'wrong_command_id': endpoint['command']['request_id'] = 'other'
        elif defect == 'unexpected_prefix': endpoint['received'] = []
        failure['typed_returned_prefix'] = v.representation.typed_failure_snapshot(decoded)
    with pytest.raises(ValueError, match='single_capture_failure:'):
        review(record)


def test_branch_envelope_uses_actual_attempt_clock(tmp_path):
    record = failed(tmp_path, 0)
    at = record['capture_failure']['started'][0]['started_ns']
    with pytest.raises(ValueError, match='outside_branch'):
        review(record, branch_envelope={'attempt_started_ns': at+1, 'attempt_finished_ns': at+2})
    with pytest.raises(ValueError, match='branch_envelope_clock'):
        review(record, branch_envelope={'attempt_started_ns': False, 'attempt_finished_ns': at})


def test_typed_payload_retains_order_tuple_integer_keys_and_nonfinite_failure_values():
    value = {'z': (1, -0.0, float('inf'), float('-inf'), float('nan')),
             'resources': {3: {'node': 3}}, 'a': [True, None, '\ud800']}
    typed = v.representation.typed_failure_snapshot(value)
    decoded = v.typed_decode(typed)
    assert list(decoded) == ['z', 'resources', 'a']
    assert type(decoded['z']) is tuple and decoded['z'][1].hex() == '-0x0.0p+0'
    assert v.representation.typed_failure_snapshot(decoded) == typed


@pytest.mark.parametrize('node', [
    {'type': 'int', 'value': True}, {'type': 'str', 'value': 1},
    {'type': 'float', 'hex': '0x1p0'}, {'type': 'float', 'hex': 'garbage'},
    {'type': 'dict', 'items': [[{'type': 'str', 'value': 'x'}]]},
    {'type': 'list', 'items': ()}, {'type': 'object', 'value': 0},
])
def test_malformed_typed_encoding_rejected(node):
    with pytest.raises(ValueError, match='single_capture_failure:'):
        v.typed_decode(node)


def test_typed_duplicates_unhashable_cycles_and_depth_rejected():
    string = {'type': 'str', 'value': 'x'}
    duplicate = {'type': 'dict', 'items': [[string, string], [string, string]]}
    unhashable = {'type': 'dict', 'items': [[{'type': 'list', 'items': []}, string]]}
    cycle = {'type': 'list', 'items': []}; cycle['items'].append(cycle)
    deep = string
    for _ in range(65): deep = {'type': 'list', 'items': [deep]}
    for value in (duplicate, unhashable, cycle, deep):
        with pytest.raises(ValueError, match='single_capture_failure:'):
            v.typed_decode(value)


def test_success_record_is_not_silently_reclassified_by_failure_checker(tmp_path):
    native, Session = fixture(tmp_path)
    records = []
    pure_candidate()(records, native, Session(), 'A', 'pure', accepted=object())
    with pytest.raises(ValueError, match='record_fields'):
        review(records[0])
