"""Current owner endpoint action facts; supplied data never proves provenance."""
from __future__ import annotations
import copy
import math
from .planning_capture_v2_contract import PHYSICAL_KINDS, TERMINAL_BY_KIND


def current_actions(view):
    """Retain every physical request from this owner's actual public endpoint.

    A terminal ACK is a delivered operation outcome, not job completion. The
    online adapter must supply the real current view; this helper cannot mint
    delivery authority from a dictionary.
    """
    owner, now = view['owner_id'], view['now']
    if owner not in ('A', 'B') or type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError('current_action_scope')
    rows, ids, pending = [], set(), []
    supplied = [(row, 'transfer') for row in view['client_requests']]
    supplied += [(row, row['kind']) for row in view['client_commands'] if row['kind'] in PHYSICAL_KINDS]
    for row, kind in supplied:
        key = row['request_id']
        if type(key) is not str or not key or key in ids or kind not in PHYSICAL_KINDS:
            raise ValueError('current_action_identity')
        ids.add(key)
        ack = row.get('last_delivered_ack')
        if ack is not None:
            if (type(ack.get('sequence')) is not int or ack['sequence'] < 1
                    or type(ack.get('delivered_at')) not in (int, float)
                    or not math.isfinite(ack['delivered_at']) or not 0 <= ack['delivered_at'] <= now):
                raise ValueError('current_action_ack_time_or_identity')
        if ack is None or ack.get('status') not in TERMINAL_BY_KIND[kind]:
            pending.append(key)
        rows.append({'request_id': key, 'kind': kind, 'last_delivered_ack': copy.deepcopy(ack)})
    return {'owner': owner, 'observed_at': now, 'actions': sorted(rows, key=lambda row: row['request_id']),
            'pending_request_ids': sorted(pending), 'native_delivery_verified': False}


def bind_supplied_bundle(bundle, view):
    """Add current own facts without claiming that this supplied view is real."""
    result = copy.deepcopy(bundle)
    facts = current_actions(view)
    result['owner_current_action_facts'] = facts
    result['owner_pending_tray_requests'] = copy.deepcopy(facts['pending_request_ids'])
    return result
