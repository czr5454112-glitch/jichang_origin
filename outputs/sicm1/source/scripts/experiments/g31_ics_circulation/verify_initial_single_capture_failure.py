"""Saved failed endpoint prefixes only; never a branch/native certificate.

The successful endpoint replay stays at its original caller. A future versioned
branch verifier must retain every failed record and mark that root unknown even
when this structural check succeeds. Missing exported payload stays unverified.
"""
from __future__ import annotations

from . import initial_owner_route_json_v3 as representation

FIELDS = ('view', 'command', 'received')
SCHEMA = 'g31.initial_single_capture.failed_prefix_review.v1'


def require(value, reason):
    if not value:
        raise ValueError('single_capture_failure:' + reason)


def typed_decode(value):
    """Invert the existing bounded builtin failure format without user hooks."""
    count = 0
    active = set()

    def visit(node, depth):
        nonlocal count
        count += 1
        require(depth <= representation.wire.MAX_DEPTH and
                count <= representation.wire.MAX_ARTIFACT_NODES, 'typed_limit')
        require(type(node) is dict and id(node) not in active, 'typed_node_or_cycle')
        active.add(id(node))
        try:
            kind = node.get('type')
            require(type(kind) is str, 'typed_tag')
            scalars = {'str': str, 'int': int, 'bool': bool, 'NoneType': type(None)}
            if kind in scalars:
                require(set(node) == {'type', 'value'} and
                        type(node['value']) is scalars[kind], 'typed_scalar')
                return node['value']
            if kind == 'float':
                require(set(node) == {'type', 'hex'} and type(node['hex']) is str,
                        'typed_float')
                try:
                    result = float.fromhex(node['hex'])
                except (ValueError, OverflowError):
                    raise ValueError('single_capture_failure:typed_float') from None
                require(result.hex() == node['hex'], 'typed_float_canonical')
                return result
            require(kind in ('dict', 'list', 'tuple') and
                    set(node) == {'type', 'items'} and type(node['items']) is list,
                    'typed_container')
            if kind != 'dict':
                result = [visit(member, depth + 1) for member in node['items']]
                return tuple(result) if kind == 'tuple' else result
            result = {}
            for pair in node['items']:
                require(type(pair) is list and len(pair) == 2, 'typed_entry')
                key, member = visit(pair[0], depth + 1), visit(pair[1], depth + 1)
                try:
                    require(key not in result, 'typed_duplicate_key')
                    result[key] = member
                except TypeError:
                    raise ValueError('single_capture_failure:typed_unhashable_key') from None
            return result
        finally:
            active.remove(id(node))

    result = visit(value, 0)
    # Insertion order, tuple/list and scalar type distinctions remain exact.
    require(representation.typed_failure_snapshot(result) == value, 'typed_roundtrip')
    return result


def exact_builtin(left, right):
    return representation.typed_failure_snapshot(left) == representation.typed_failure_snapshot(right)


def verify(record, *, owner, request_id, branch_envelope=None):
    """Validate retained data and return unknown, including for valid failures.

branch_envelope, when available, is the actual branch attempt's start and end
in perf_counter_ns. Start clocks cannot establish endpoint return durations.
An absent envelope is stated explicitly, never replaced by a root clock.
"""
    require(type(owner) is str and owner in ('A', 'B') and
            type(request_id) is str and bool(request_id), 'expected_identity')
    require(type(record) is dict and set(record) ==
            {'information', 'endpoints', 'ledger', 'capture_failure'}, 'record_fields')
    endpoints, failure = record['endpoints'], record['capture_failure']
    require(type(endpoints) is dict and endpoints.get('owner') == owner and
            endpoints.get('request_id') == request_id, 'record_identity')
    require(type(failure) is dict, 'failure_shape')
    status = failure.get('status')
    require(status in ('unknown_incomplete_endpoint_collection', 'unknown_failed_collection'),
            'failure_status')
    completed, started, active = failure.get('completed'), failure.get('started'), failure.get('active')
    require(type(completed) is list and len(completed) <= 3 and
            all(type(name) is str for name in completed) and
            completed == list(FIELDS[:len(completed)]), 'completed_prefix')
    require(active is None or (type(active) is str and len(completed) < 3 and
                              active == FIELDS[len(completed)]), 'active_endpoint')
    expected = completed + ([active] if active is not None else [])
    require(type(started) is list and len(started) == len(expected), 'started_count')
    previous = -1
    for row, name in zip(started, expected):
        require(type(row) is dict and set(row) == {'endpoint', 'started_ns'} and
                row['endpoint'] == name and type(row['started_ns']) is int and
                row['started_ns'] >= 0 and row['started_ns'] >= previous, 'start_clock_order')
        previous = row['started_ns']
    if branch_envelope is not None:
        require(type(branch_envelope) is dict and set(branch_envelope) ==
                {'attempt_started_ns', 'attempt_finished_ns'}, 'branch_envelope_fields')
        lower, upper = (branch_envelope[k] for k in ('attempt_started_ns', 'attempt_finished_ns'))
        require(type(lower) is int and type(upper) is int and 0 <= lower <= upper,
                'branch_envelope_clock')
        require(all(lower <= row['started_ns'] <= upper for row in started), 'outside_branch')

    if status == 'unknown_incomplete_endpoint_collection':
        require(set(failure) == {'status', 'completed', 'active', 'started'} and
                len(completed) < 3 and active is None, 'incomplete_shape')
        info = record['information']
        require(type(info) is dict and info.get('native_delivery_verified') is not True and
                record['ledger'] is None, 'incomplete_promoted')
        require(set(endpoints) == {'owner', 'request_id', *completed} |
                ({'at'} if completed else set()), 'incomplete_returned_fields')
        prefix = endpoints
        exported = True
        cause = 'collector_returned_without_complete_triplet'
    else:
        require(set(failure) in (
            {'status', 'completed', 'active', 'started', 'error_type', 'error', 'typed_returned_prefix'},
            {'status', 'completed', 'active', 'started', 'error_type', 'error', 'prefix_export_error'}),
            'exception_fields')
        require(type(failure['error_type']) is str and bool(failure['error_type']) and
                type(failure['error']) is str, 'exception_cause')
        cause = failure['error_type']
        require(record['ledger'] is None, 'failed_ledger_promoted')
        if 'prefix_export_error' in failure:
            require(type(failure['prefix_export_error']) is str and bool(failure['prefix_export_error']),
                    'prefix_export_error')
            # The existing placeholder or partial assignments are retained, but
            # their returned payload has no independent typed export to compare.
            prefix, exported = None, False
        else:
            decoded = typed_decode(failure['typed_returned_prefix'])
            require(type(decoded) is dict and list(decoded) == ['information', 'endpoints'],
                    'typed_root_fields')
            prefix = decoded['endpoints']
            require(type(prefix) is dict and list(prefix) == ['owner', 'request_id', *completed] and
                    prefix['owner'] == owner and prefix['request_id'] == request_id,
                    'typed_prefix_identity_or_fields')
            require(set(endpoints) in ({'owner', 'request_id'},
                    {'owner', 'request_id', 'at', *completed}), 'record_returned_fields')
            if 'at' in endpoints:
                require(exact_builtin({k: v for k, v in endpoints.items() if k != 'at'},
                                      representation.normalize(prefix)), 'record_typed_mismatch')
            if record['information'] is not None:
                require(exact_builtin(record['information'], representation.normalize(decoded['information'])),
                        'record_information_mismatch')
            exported = True
    if prefix is not None:
        if 'at' in endpoints:
            require(type(endpoints['at']) in (int, float) and endpoints['at'] == .11,
                    'initial_epoch')
        if 'view' in prefix:
            require(type(prefix['view']) is dict and prefix['view'].get('owner_id') == owner and
                    type(prefix['view'].get('now')) in (int, float) and prefix['view']['now'] == .11,
                    'returned_view_identity')
        if 'command' in prefix:
            require(type(prefix['command']) is dict and
                    prefix['command'].get('request_id') == request_id and
                    prefix['command'].get('kind') == 'planning_snapshot', 'returned_command_identity')
        # received can itself be malformed: it is failed evidence, not accepted
        # planning data. No partial prefix is fed into validate_pair.
    return {'schema': SCHEMA, 'status': 'unknown_failed_or_incomplete_collection',
            'closed': False, 'failure_status': status, 'failure_cause': cause,
            'completed': list(completed), 'active': active, 'started_count': len(started),
            'returned_payload_verified': exported, 'branch_envelope_verified': branch_envelope is not None,
            'endpoint_durations_available': False, 'native_authority': False,
            'complete_branch_audit': False, 'root_must_remain_unknown': True}
