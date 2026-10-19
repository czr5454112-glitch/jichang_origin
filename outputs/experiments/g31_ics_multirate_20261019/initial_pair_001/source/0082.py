"""Pure candidate for a separately declared cooperative single-token policy.

This certifies current local possession and a received-action barrier, not a
remote transfer payload or EMPTY_RECEIVED causality. It submits no operation.
The caller must retain consumed watermarks and perform native revalidation.
"""
from __future__ import annotations
from copy import deepcopy
from . import research_original_low_wip as base
from . import research_original_low_wip_reuse as reuse


def require(value, reason):
    if not value:
        raise ValueError('possession_permit:' + reason)


class PossessionGate:
    """One owner, immutable declared parking, consumption before submission.

    Both source policies must restrict every post-parking physical operation
    to the token. That cooperative assumption is not certified by a snapshot.
    No restore-from-native-JSON support or crash durability is asserted here.
    """
    def __init__(self, owner, plan, consumed_action_ids):
        self.owner = owner
        self.plan = deepcopy(plan)
        require(type(plan['owners']) is list and len(plan['owners']) == 2
                and len(set(plan['owners'])) == 2 and owner in plan['owners'], 'two_owners')
        self.peer = next(o for o in plan['owners'] if o != owner)
        self.token = plan['token_tray_id']
        parking = plan['parking']
        require(type(parking) is list and parking and all(p['owner'] in plan['owners'] for p in parking), 'parking_scope')
        self.parking = {p['request_id']: p for p in parking}
        require(len(self.parking) == len(parking)
                and len({p['tray_id'] for p in parking}) == len(parking)
                and self.token in {p['tray_id'] for p in parking}, 'parking_identity')
        require(type(consumed_action_ids) in (list, tuple, set, frozenset)
                and all(type(k) is str and k for k in consumed_action_ids), 'watermark_type')
        require(len(set(consumed_action_ids)) == len(consumed_action_ids), 'watermark_duplicates')
        self.consumed = frozenset(consumed_action_ids)
        require(set(self.parking) <= self.consumed, 'missing_parking_watermark')

    @staticmethod
    def _received(ack, through):
        if not ack or ack.get('status') != 'received':
            return False
        require(reuse.finite(ack.get('delivered_at')) and 0 <= ack['delivered_at'] <= through, 'ack_clock')
        return True

    def consume(self, view, outbox, peer_envelopes):
        require(view['owner_id'] == self.owner and reuse.finite(view['now']) and view['now'] >= 0, 'fresh_local_owner_clock')
        now = view['now']
        nodes = {n['node']: n for n in view['node_contracts']}
        require(len(nodes) == len(view['node_contracts']), 'duplicate_nodes')
        if not reuse.current_empty(view, self.token):
            return None
        current = next(t for t in view['trays'] if t['tray_id'] == self.token)
        require(nodes[current['node']]['resource_owner'] == self.owner, 'nonlocal_token')
        own = reuse.latest_own_capture(outbox, self.owner, self.peer, now, nodes)
        peer = base.delivered_peer(peer_envelopes, self.owner, self.peer, now, nodes)
        if own is None or peer is None:
            return None
        local = own['envelope']['capture']['local_capture']
        other = peer['capture']['local_capture']
        if other['captured_at'] < local['captured_at']:
            return None
        if not reuse.current_empty({'now': local['captured_at'], 'trays': local['trays']}, self.token):
            return None
        captured = next(t for t in local['trays'] if t['tray_id'] == self.token)
        keys = ('tray_id', 'node', 'mode', 'business_bag_id', 'edge_to', 'reception_node', 'available_at', 'generation', 'traversal_id')
        require(all(k in current and k in captured for k in keys), 'token_state_coverage')
        if any(current[k] != captured[k] for k in keys):
            return None
        own_actions = {}
        for rid, row in outbox.items():
            if row['kind'] == 'planning_snapshot_v2':
                continue
            require(row['kind'] == 'transfer', 'undeclared_own_operation')
            payload = row['payload']
            require(payload['request_id'] == rid and payload['owner_id'] == self.owner, 'own_action_identity')
            if rid in self.parking:
                parked = self.parking[rid]
                require(parked['owner'] == self.owner and all(payload[k] == parked[k]
                        for k in ('tray_id', 'source', 'destination')), 'own_parking_payload')
            else:
                require(payload['tray_id'] == self.token, 'own_nontoken_operation')
            if row.get('submission_reply', {}).get('status') == 'rejected' or not row['terminal']:
                return None
            ack = (row.get('client_view') or {}).get('last_delivered_ack')
            if not self._received(ack, now):
                return None
            own_actions[rid] = ack
        self_rows = own['envelope']['capture']['extension']['submitted_physical_actions']
        require(all(r['kind'] == 'transfer' and r['source_owner'] == self.owner for r in self_rows), 'self_operation_scope')
        if set(own_actions) != {r['request_id'] for r in self_rows}:
            return None
        if not all(self._received(r.get('last_delivered_ack'), local['captured_at']) for r in self_rows):
            return None
        peer_rows = peer['capture']['extension']['submitted_physical_actions']
        require(all(r['kind'] == 'transfer' and r['source_owner'] == self.peer for r in peer_rows), 'peer_operation_scope')
        if not all(self._received(r.get('last_delivered_ack'), other['captured_at']) for r in peer_rows):
            return None
        peer_ids = {r['request_id'] for r in peer_rows}
        require(not (peer_ids & set(own_actions)), 'cross_owner_duplicate_identity')
        current_ids = frozenset(own_actions) | peer_ids
        if not set(self.parking) <= current_ids:
            return None
        for rid, parked in self.parking.items():
            if (rid in own_actions) != (parked['owner'] == self.owner):
                return None
        if not self.consumed < current_ids:
            return None
        previous = self.consumed
        self.consumed = current_ids  # irreversible for this gate, before caller can submit
        return {'status': 'conditional_cooperative_current_possession_permit',
                'owner': self.owner, 'token': self.token, 'observed_at': now,
                'current_token': deepcopy(current), 'own_delivered_selfcopy': own,
                'delivered_peer': deepcopy(peer), 'previous_action_ids': sorted(previous),
                'consumed_action_ids': sorted(current_ids),
                'new_action_ids': sorted(current_ids - previous),
                'remote_payload_or_arrival_causality_certified': False,
                'native_revalidation_required': True, 'operation_submitted': False}

    def checkpoint(self):
        return {'owner': self.owner, 'consumed_action_ids': sorted(self.consumed),
                'native_state_persistence_certified': False}
