"""Pure, fail-closed prototype for an unchanged initial-A scheduler.

This is not installed in the accepted v3 campaign.  A future adapter must bind
each input to the actual all-owner advance call and retain the original .05
tick, owner activations, root admission, immutable retry and final drain.  This
module grants no native authority and does not freshen a saved observation.

The gate omits the *root's* two observations/drain only when no A notification,
no intervening protocol submission, and no due A retry can change its closure
predicate.  It does not suppress either background owner's ordinary activation.
"""
from __future__ import annotations

import copy
import math

SCHEMA = 'g31.initial_owner.root_observation_gate.v1'
OWNERS = ('A', 'B')
KNOWN_MASK = 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128
KINDS = frozenset(('transfer', 'route', 'demand', 'planning_snapshot',
                   'planning_snapshot_v2', 'planning_snapshot_v3'))


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def cursors(value):
    return (type(value) is dict and set(value) == set(OWNERS)
            and all(type(n) is int and n >= 0 for n in value.values()))


class RootObservationGate:
    """Bounded state; all proof records are returned to the caller for logging.

`after_step` is a required integration hook after the original full observation
and same-time drain, or after the exact skipped admission.  Without it the next
decision falls back.  A standalone caller's supplied booleans are NOT proof of
actual execution; that proof requires the future source-bound adapter/replay.
    """
    def __init__(self):
        self._prior = None
        self._pending = None
        self._ordinal = 0

    def decide(self, *, before, horizon, response, cursor_before, now,
               protocol_call_count, outbox, root_state,
               all_native_advances_observed):
        self._ordinal += 1
        proof = {'schema': SCHEMA, 'ordinal': self._ordinal, 'skip': False,
                 'reason': 'unknown', 'before': before, 'at': now,
                 'horizon': horizon, 'cursor_before': copy.deepcopy(cursor_before),
                 'response': copy.deepcopy(response),
                 'protocol_call_count': protocol_call_count,
                 'actual_native_authority': False,
                 'retained_observation_time_unchanged': True}
        previous = self._prior
        unfinished = self._pending is not None
        self._pending = None
        self._prior = None  # malformed or interrupted chains cannot stay valid

        def fallback(reason):
            proof['reason'] = reason
            return proof

        if unfinished:
            return fallback('previous_step_completion_missing')
        if all_native_advances_observed is not True:
            return fallback('unobserved_native_advance_or_mutation')
        if (not all(finite(t) for t in (before, horizon, now))
                or not before <= now <= horizon or not cursors(cursor_before)
                or type(protocol_call_count) is not int or protocol_call_count < 0):
            return fallback('malformed_boundary_arguments')
        if (type(response) is not dict or response.get('physical_time') != now
                or response.get('timestamp_complete') is not True
                or type(response.get('horizon_complete')) is not bool
                or response.get('status') not in ('notified', 'horizon_reached')
                or type(response.get('notifications')) is not dict):
            return fallback('incomplete_or_unsupported_boundary')
        if response['horizon_complete'] is not (now == horizon):
            return fallback('horizon_receipt_mismatch')
        if response['status'] == 'horizon_reached' and (
                now != horizon or response['horizon_complete'] is not True):
            return fallback('horizon_receipt_mismatch')
        notices = response['notifications']
        if not set(notices) <= set(OWNERS):
            return fallback('foreign_notice')
        if response['status'] == 'notified' and not notices:
            return fallback('missing_notified_notice')
        after = dict(cursor_before)
        for owner, notice in notices.items():
            if (type(notice) is not dict or type(notice.get('sequence')) is not int
                    or notice['sequence'] <= cursor_before[owner]
                    or not finite(notice.get('observed_at'))
                    or notice['observed_at'] != now
                    or type(notice.get('change_mask')) is not int
                    or not 0 < notice['change_mask'] <= KNOWN_MASK):
                return fallback('stale_malformed_or_unknown_notice')
            after[owner] = notice['sequence']
        # Several events may increment a sequence within one complete timestamp.
        # Continuity means exact call-cursor linkage, NOT sequence == old + 1.
        proof['cursor_after'] = after
        self._pending = {'at': now, 'cursors': dict(after),
                         'call_count': protocol_call_count, 'skip': False}
        if root_state != 'pending_first_hop_and_ack':
            return fallback('root_not_pending')
        if type(outbox) is not dict:
            return fallback('missing_complete_outbox')
        retries = []
        for identity, row in outbox.items():
            if (type(identity) is not str or not identity or type(row) is not dict
                    or row.get('kind') not in KINDS or type(row.get('request')) is not dict
                    or row['request'].get('request_id') != identity
                    or row['request'].get('owner_id') not in OWNERS
                    or type(row.get('terminal')) is not bool):
                return fallback('malformed_outbox_row')
            if row['request']['owner_id'] != 'A' or row['terminal']:
                continue
            if not finite(row.get('next_retry')):
                return fallback('unknown_retry_deadline')
            retries.append({'request_id': identity, 'next_retry': row['next_retry']})
        proof['pending_A_retries'] = retries
        if previous is None:
            return fallback('initial_or_unproven_chain')
        if previous['at'] != before or previous['cursors'] != cursor_before:
            return fallback('native_clock_or_cursor_gap')
        if previous['call_count'] != protocol_call_count:
            return fallback('protocol_submission_since_previous_step')
        if 'A' in notices:  # deliberately broader than just physical/ACK masks
            return fallback('actual_A_notification')
        if any(row['next_retry'] <= now for row in retries):
            return fallback('A_retry_due')
        self._pending['skip'] = True
        proof.update(skip=True, reason='no_A_change_no_submission_no_due_A_retry')
        return proof

    def after_step(self, *, now, protocol_call_count, original_admission_retained,
                   full_root_observation_and_drain_completed):
        """Commit only a complete actual step; return a small audit record.

Even a skipped step must execute the original client.activate('A', trigger),
at its original position.  Later demand IDs depend on len(client.roots).
        """
        pending, self._pending = self._pending, None
        self._prior = None
        valid = (pending is not None and finite(now) and now == pending['at']
                 and type(protocol_call_count) is int
                 and protocol_call_count >= pending['call_count']
                 and original_admission_retained is True)
        if valid and pending['skip']:
            valid = (protocol_call_count == pending['call_count']
                     and full_root_observation_and_drain_completed is False)
        elif valid:
            valid = full_root_observation_and_drain_completed is True
        if valid:
            self._prior = {'at': now, 'cursors': dict(pending['cursors']),
                           'call_count': protocol_call_count}
        return {'schema': SCHEMA, 'chain_continues': valid,
                'ordinal': self._ordinal, 'at': now,
                'full_observation_completed': full_root_observation_and_drain_completed,
                'admission_retained': original_admission_retained}
