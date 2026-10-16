"""Saved endpoint dispatch only; no native/session authority or branch audit.

Successful records retain the exact original checker and its complete globals.
Failed captures are checked as failed evidence, never as a closed request. The
three slots required for a complete initial request are A initial, A final and
B initial. Missing/unattempted slots stay visible; this does not require an
already failed request to perform further collection.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

from . import verify_initial_owner_route_campaign as original
from . import verify_initial_single_capture_failure as failure

SCHEMA = 'g31.initial_single_capture.endpoint_dispatch.v1'
SLOTS = (('A', 0), ('A', 1), ('B', 0))
SUCCESS = original.endpoint_replay
_SUCCESS_CODE = SUCCESS.__code__
_SUCCESS_GLOBALS = SUCCESS.__globals__
_FAILURE_VERIFY = failure.verify
_MALFORMED = (ValueError, TypeError, KeyError, IndexError)


def require(value, reason):
    if not value:
        raise ValueError('single_capture_endpoints:' + reason)


def source_proof():
    require(SUCCESS is original.endpoint_replay and SUCCESS.__code__ is _SUCCESS_CODE
            and SUCCESS.__globals__ is _SUCCESS_GLOBALS
            and _FAILURE_VERIFY is failure.verify, 'checker_identity_changed')
    return {'success_code_unchanged': True, 'success_full_globals_unchanged': True,
            'failure_checker_unchanged': True, 'native_authority': False}


def typed_bytes(value):
    """Bounded lossless builtin representation, including failed float values.

ASCII serialization of the typed format preserves surrogate failures without
trying to accept them as ordinary successful wire JSON. Types, order, tuple vs
list and float.hex (including signed zero) are retained.
"""
    typed = failure.representation.typed_failure_snapshot(value)
    return json.dumps(typed, ensure_ascii=True, allow_nan=False,
                      separators=(',', ':')).encode('ascii')


def record_hash(value):
    data = typed_bytes(value)
    return {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
            'format': 'existing_typed_failure_snapshot_ascii_json_v1'}


def _error(exc):
    return {'type': type(exc).__name__, 'message': str(exc)}


def _envelope(value):
    require(type(value) is dict and set(value) ==
            {'attempt_started_ns', 'attempt_finished_ns'}, 'branch_envelope_fields')
    lower, upper = value['attempt_started_ns'], value['attempt_finished_ns']
    require(type(lower) is int and type(upper) is int and 0 <= lower <= upper,
            'branch_envelope_clock')
    return dict(value)


def planning_identities(calls, outbox):
    """Derive IDs from immutable real submission records, never ID spelling.

This validates the whole supplied call/outbox denominator and immutable retry
payloads. Only a unique first planning_snapshot submission per owner at or
before .11 identifies that owner's capture. Later publications do not change
that selection; a second eligible creation is ambiguous and rejected.
"""
    require(type(calls) is list and type(outbox) is dict, 'transport_shape')
    require(all(type(k) is str and k for k in outbox), 'outbox_key')
    seen, selected, previous = {}, {'A': [], 'B': []}, -math.inf
    for ordinal, call in enumerate(calls):
        require(type(call) is dict and type(call.get('request')) is dict, 'call_shape')
        at, payload = call.get('at'), call['request']
        require(type(at) in (int, float) and math.isfinite(at) and 0 <= at <= 40.
                and previous <= at, 'call_time')
        previous = at
        identity, owner, kind = payload.get('request_id'), payload.get('owner_id'), call.get('kind')
        require(type(identity) is str and bool(identity) and type(owner) is str
                and owner in ('A', 'B') and type(kind) is str and bool(kind), 'call_identity')
        require(type(call.get('retry')) is bool, 'retry_boolean')
        require(kind == 'transfer' or payload.get('kind') == kind, 'payload_kind')
        require(identity in outbox and type(outbox[identity]) is dict, 'missing_outbox')
        row = outbox[identity]
        require(row.get('kind') == kind and type(row.get('request')) is dict
                and typed_bytes(row['request']) == typed_bytes(payload), 'outbox_payload')
        if identity not in seen:
            require(call['retry'] is False, 'retry_without_creation')
            seen[identity] = typed_bytes(payload)
            if kind == 'planning_snapshot' and at <= .11:
                require(payload.get('target_owner') == ('B' if owner == 'A' else 'A'),
                        'planning_target')
                selected[owner].append({'request_id': identity, 'created_at': at,
                                        'creation_call_ordinal': ordinal,
                                        'payload_hash': record_hash(payload)})
        else:
            require(call['retry'] is True and typed_bytes(payload) == seen[identity],
                    'immutable_retry_payload')
    require(set(seen) == set(outbox), 'outbox_denominator')
    result = {}
    for owner in ('A', 'B'):
        rows = selected[owner]
        result[owner] = ({'status': 'bound_unique_creation', **rows[0]} if len(rows) == 1 else
                         {'status': 'missing_creation' if not rows else 'ambiguous_creation',
                          'candidates': rows})
    return {'owners': result, 'calls': len(calls), 'outbox': len(outbox)}


def _dispatch(record, *, owner, identity, envelope):
    require(type(record) is dict, 'record_shape')
    if 'capture_failure' in record:
        detail = _FAILURE_VERIFY(record, owner=owner, request_id=identity,
                                 branch_envelope=envelope)
        return 'verified_unknown_capture', detail
    require(set(record) == {'information', 'endpoints', 'ledger'}, 'success_record_fields')
    e = record['endpoints']
    require(type(e) is dict and set(e) ==
            {'owner', 'request_id', 'at', 'view', 'command', 'received'}
            and e['owner'] == owner and e['request_id'] == identity, 'success_expected_identity')
    status = SUCCESS(record)  # Exact old function, not a reconstructed namespace.
    return ('verified_conditional_endpoints' if status == 'conditional_validated_data'
            else 'verified_unknown_complete_endpoints'), {'original_status': status}


def verify_records(records_by_owner, *, calls, outbox, branch_envelope):
    """Check all supplied records and retain invalid/error/missing denominators.

Malformed evidence is invalid. Memory/resource and unexpected checker errors
are audit_error. Neither is relabeled a structurally verified failed capture.
No partial payload is sent to the successful checker. This function does not
read raw.failure, so a nonthrowing B incomplete capture cannot be hidden by it.
"""
    proof = source_proof()
    problems, rows, present = [], [], set()
    envelope = identities = None
    for stage, operation in (
            ('branch_envelope', lambda: _envelope(branch_envelope)),
            ('planning_identity', lambda: planning_identities(calls, outbox))):
        try:
            value = operation()
            if stage == 'branch_envelope': envelope = value
            else: identities = value
        except _MALFORMED as exc:
            problems.append({'stage': stage, 'status': 'invalid', 'error': _error(exc)})
        except Exception as exc:
            problems.append({'stage': stage, 'status': 'audit_error', 'error': _error(exc)})
    if type(records_by_owner) is not dict:
        problems.append({'stage': 'records_container', 'status': 'invalid',
                         'error': {'type': 'ValueError', 'message': 'expected exact dict'}})
        items = []
    else:
        items = list(records_by_owner.items())
    for owner, records in items:
        valid_owner = type(owner) is str and owner in ('A', 'B')
        if not valid_owner:
            problems.append({'stage': 'owner_domain', 'status': 'invalid',
                             'error': {'type': 'ValueError', 'message': 'unexpected owner key'}})
        if type(records) is not list:
            problems.append({'stage': 'owner_records', 'owner': owner if valid_owner else None,
                             'status': 'invalid', 'error': {'type': 'ValueError',
                             'message': 'expected exact list'}})
            # Preserve the rejected container itself as an independently hashed
            # row rather than silently treating it as zero successful records.
            records = [records]
            valid_container = False
        else:
            valid_container = True
        for ordinal, record in enumerate(records):
            failed = type(record) is dict and 'capture_failure' in record
            row = {'ordinal': len(rows), 'owner': owner if valid_owner else None,
                   'owner_ordinal': ordinal, 'capture_failure_present': failed,
                   'record_hash': None, 'status': 'unchecked'}
            rows.append(row)
            if valid_owner and valid_container: present.add((owner, ordinal))
            try:
                row['record_hash'] = record_hash(record)
                require(valid_owner and valid_container and (owner, ordinal) in SLOTS,
                        'unexpected_owner_or_record_ordinal')
                require(envelope is not None and identities is not None, 'missing_verified_context')
                selected = identities['owners'][owner]
                require(selected['status'] == 'bound_unique_creation', 'unbound_planning_identity')
                row['expected_request_id'] = selected['request_id']
                row['status'], row['check'] = _dispatch(record, owner=owner,
                    identity=selected['request_id'], envelope=envelope)
            except _MALFORMED as exc:
                row['status'], row['error'] = 'invalid', _error(exc)
            except Exception as exc:
                row['status'], row['error'] = 'audit_error', _error(exc)
    missing = [{'owner': owner, 'owner_ordinal': ordinal} for owner, ordinal in SLOTS
               if (owner, ordinal) not in present]
    valid = not problems and not missing and len(rows) == 3 and all(
        row['status'] == 'verified_conditional_endpoints' for row in rows)
    return {'schema': SCHEMA, 'status': 'complete_conditional_endpoints' if valid else
            'unknown_or_invalid_endpoint_certificate', 'source_proof': proof,
            'branch_envelope': envelope, 'planning_identity': identities,
            'records': rows, 'record_count': len(rows), 'expected_slots': [list(x) for x in SLOTS],
            'missing_slots': missing, 'problems': problems,
            'capture_failure_count': sum(row['capture_failure_present'] for row in rows),
            'all_required_endpoints_conditionally_verified': valid,
            'native_authority': False, 'complete_branch_audit': False}


def certify_reported_root(reported_root, endpoint_report, *, root_replay_verified, business_facts=None):
    """Conjoin endpoint evidence with caller's existing root replay conclusion.

This helper cannot verify that caller conclusion itself. A campaign must run
all original root/RPC/physical checks, bind the supplied report and retain this
conditional scope. It never upgrades an open or over-budget reported root.
"""
    require(type(root_replay_verified) is bool, 'root_replay_verdict_type')
    require(reported_root is None or type(reported_root) is dict, 'reported_root_shape')
    require(type(endpoint_report) is dict and endpoint_report.get('schema') == SCHEMA,
            'endpoint_report_schema')
    rows = endpoint_report.get('records')
    require(type(rows) is list and all(type(row) is dict for row in rows), 'endpoint_report_records')
    reasons = []
    if not root_replay_verified: reasons.append('original_root_replay_not_verified')
    if any(row.get('capture_failure_present') is not False for row in rows):
        reasons.append('capture_failure_retained')
    if (endpoint_report.get('problems') or endpoint_report.get('missing_slots') or
            endpoint_report.get('record_count') != 3 or len(rows) != 3 or
            {(r.get('owner'), r.get('owner_ordinal')) for r in rows} != set(SLOTS) or
            any(r.get('status') != 'verified_conditional_endpoints' for r in rows) or
            endpoint_report.get('all_required_endpoints_conditionally_verified') is not True):
        reasons.append('endpoint_certificate_incomplete_or_invalid')
    reported = copy.deepcopy(reported_root)
    closed = (not reasons and reported is not None and reported.get('closed') is True)
    # Preserve the caller's actual measured warm value and historical claim;
    # only an exact finite nonnegative number can yield a <=100ms observation.
    warm = None if reported is None else reported.get('warm_ms')
    within = (closed and type(warm) in (int, float) and math.isfinite(warm)
              and 0 <= warm <= 100. and reported.get('observed_within_100ms') is True)
    return {'schema': 'g31.initial_single_capture.root_certification.v1',
            'reported_root': reported, 'business_facts': copy.deepcopy(business_facts),
            'endpoint_report': copy.deepcopy(endpoint_report),
            'certified_root': {'status': 'conditionally_closed' if closed else 'unknown_or_open',
                'closed': closed, 'observed_within_100ms': within,
                'complete_100ms_certified': False, 'warm_ms': warm, 'reasons': reasons},
            'scope': 'Endpoint conjunction only; caller must separately verify full root/RPC/physical evidence.',
            'native_authority': False}
