"""One real source-local snapshot at the first finite supply-cap proof.

The frozen quiescent owner executes unchanged. Only after it establishes its
first cap proof does this subclass enqueue one ordinary typed publication.
This carries the sender's native-captured facts, never a copied peer body.
It adds no physical request, refreshes no old timestamp, and has no periodic
post-cap publisher. Failed delivery remains an unknown handshake.
"""
from __future__ import annotations

from copy import deepcopy
from . import repeat_quiescent_cap as reference


class RepeatOwner(reference.RepeatOwner):
    def __init__(self, session, owner, plan):
        super().__init__(session, owner, plan)
        self.cap_barrier_relay = None

    def activate(self):
        was_observed = self.cap_observed
        super().activate()
        if was_observed or not self.cap_observed:
            return
        # The unchanged superclass just obtained a current view, selected the
        # latest unexpired delivered peer body, and checked every received ACK.
        # last_barrier is a copy of that proof; it is diagnostic, not wire input.
        reference.require(self.cap_barrier_relay is None, 'cap_relay_duplicate')
        reference.require(self.last_barrier is not None and
            self.last_barrier['known_supply_count'] >= self.plan['supply_cap'],
            'cap_relay_missing_current_proof')
        now = self.session.physical_time
        request_id = reference.base.owner_request_id(self.owner, f'snapshot:{self.publications}')
        proof = deepcopy(self.last_barrier)
        published = self.publish(now, {'kind': 'terminal_cap_barrier_relay',
            'supply_cap': self.plan['supply_cap'], 'peer_message_id': proof['peer_message_id']})
        self.cap_barrier_relay = {'request_id': request_id, 'at': now,
            'source_owner': self.owner, 'target_owner': self.peer,
            'fresh_cap_proof': proof, 'publication_enqueued': bool(published)}

    def summary(self):
        return {**super().summary(), 'cap_barrier_relay': deepcopy(self.cap_barrier_relay)}


def relay_evidence(owner_summary):
    """Historical delivered-ACK evidence, never permission for a new action.

    A full saved-policy replay must establish that cap_observed arose from the
    real fresh superclass branch. This helper only checks the subsequent own
    typed-publication receipt. Final-horizon expiry does not erase a delivery
    that actually occurred while valid; it must not make a live peer fresh.
    """
    relay = owner_summary.get('cap_barrier_relay')
    result = {'status': 'unknown', 'reason': 'missing_cap_relay',
              'new_physical_actions_authorized': False}
    if not owner_summary.get('cap_observed') or not isinstance(relay, dict):
        return result
    if relay.get('publication_enqueued') is not True:
        return {**result, 'reason': 'publication_not_enqueued'}
    row = owner_summary.get('outbox', {}).get('outbox', {}).get(relay.get('request_id'))
    if not isinstance(row, dict):
        return {**result, 'reason': 'missing_own_outbox_publication'}
    request = row.get('payload', {})
    ack = (row.get('client_view') or {}).get('last_delivered_ack') or {}
    if row.get('kind') != 'planning_snapshot_v2' or request.get('kind') != 'planning_snapshot_v2' or \
       request.get('owner_id') != relay['source_owner'] or \
       request.get('target_owner') != relay['target_owner'] or request.get('request_id') != relay['request_id']:
        return {**result, 'reason': 'publication_identity_mismatch'}
    if ack.get('status') != 'delivered':
        return {**result, 'reason': 'missing_delivered_ack', 'ack_status': ack.get('status')}
    envelope = ack.get('planning_snapshot_v2') or {}
    local = (envelope.get('capture') or {}).get('local_capture') or {}
    clocks = [relay.get('at'), local.get('captured_at'), envelope.get('delivered_at'), ack.get('delivered_at'),
              local.get('valid_until')]
    if not all(reference.reuse.finite(t) for t in clocks):
        return {**result, 'reason': 'invalid_delivery_clock'}
    sent, captured, delivered, ack_at, valid_until = clocks
    if not (0 <= sent <= captured <= delivered <= ack_at and delivered < valid_until) or \
       valid_until != request.get('expiry'):
        return {**result, 'reason': 'invalid_delivery_chronology'}
    if envelope.get('schema') != 'g31.planning_snapshot.v2' or envelope.get('kind') != 'planning_snapshot_v2' or \
       local.get('source_owner') != relay['source_owner'] or local.get('target_owner') != relay['target_owner'] or \
       ack.get('result_id') != local.get('message_id') or not local.get('message_id'):
        return {**result, 'reason': 'capture_identity_mismatch'}
    return {'status': 'delivered_historical_cap_relay', 'request_id': relay['request_id'],
            'native_message_id': local['message_id'], 'captured_at': captured,
            'delivered_at': delivered, 'ack_delivered_at': ack_at,
            'new_physical_actions_authorized': False}


def scope():
    return {'schema': 'g31.repeat_cap_barrier_relay.v1', 'status': 'pure_candidate_native_unexecuted',
        'reference': 'repeat_quiescent_cap.RepeatOwner',
        'change': 'After the unchanged first fresh cap proof, publish exactly one new source-local native snapshot before future activations quiesce.',
        'physical_changes': 0,
        'physical_changes_meaning': 'No additional physical request and no physical rule edit; actual physical-trace equality is not yet tested.',
        'additional_publications_per_owner_maximum': 1,
        'unchanged': 'Full input, cap, owner-local selection, native physical rules, received barrier, periodic schedule, immutable retries and ACK refresh.',
        'failure': 'A missing/dropped/expired/rejected terminal relay is unknown. No retransmission with a new expiry and no periodic post-cap publisher.',
        'limits': 'Not consensus under arbitrary outages. Both saved owner cap proofs and delivered relay ACKs must be checked by the eventual saved-policy verifier. Original timeout remains unknown.'}
