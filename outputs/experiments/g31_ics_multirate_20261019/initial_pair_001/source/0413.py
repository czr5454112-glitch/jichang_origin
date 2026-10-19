"""Source-only candidate: stop new admission reads once a lawful cap proof exists.

The original class AST differs only by moving its existing cap check before
invitation/current-empty. No producer file is changed. Not native-accepted.
"""
from __future__ import annotations
import ast
from copy import deepcopy
from pathlib import Path
from . import research_original_low_wip_repeat as reference
from .research_original_low_wip_repeat import (BaseOwner, base, reuse, require,
    MAX_PUBLICATIONS, HORIZON, is_supply, physical_barrier, invitation, local_permit)

class RepeatOwner(BaseOwner):
    def __init__(self, session, owner, plan):
        super().__init__(session, owner, plan)
        self.repeated = []; self.consumed = []; self.relayed = []; self.replied = []
        self.repeat_publications = []; self.last_barrier = None; self.cap_observed = False
        self.halt_new_actions = False

    def publish(self, now, reason):
        if len(self.repeat_publications) >= MAX_PUBLICATIONS:
            self.failure = {'reason': 'unknown_publication_budget', 'at': now}; return False
        rid = base.owner_request_id(self.owner, f'snapshot:{self.publications}')
        self.client.submit(self.owner, 'planning_snapshot_v2', {'target_owner': self.peer,
            'message_delay': base.WIRE, 'publication_delay': base.WIRE, 'expiry': now+base.VALIDITY}, request_id=rid)
        self.publications += 1; self.next_publication = now+base.PERIOD
        self.repeat_publications.append({'request_id': rid, 'at': now, 'reason': deepcopy(reason)})
        return True

    def activate(self):
        if self.halt_new_actions:
            self.client.refresh(owner_id=self.owner)  # preserve immutable retries/ACKs after experiment failure
            return
        was_quiet = self.quiet
        super().activate()  # frozen startup, plus actual own refresh/retry even when quiet
        if not was_quiet or self.failure or self.index != len(self.rows): return
        now = self.session.physical_time
        # A real terminal ACK is relayed even while the token is elsewhere.
        for rid, row in list(self.client.state['outbox'].items()):
            if row['kind'] != 'transfer' or not is_supply(rid, self.owner): continue
            ack = row.get('client_view', {}).get('last_delivered_ack') or {}
            if row.get('submission_reply', {}).get('status') == 'rejected':
                self.failure = {'reason': 'unknown_supply_submission_rejected', 'request_id': rid}; return
            if row['terminal'] and ack.get('status') != 'received':
                if ack and [rid, ack.get('status')] not in self.relayed:
                    if self.publish(now, {'kind': 'terminal_ack_relay', 'request_id': rid, 'ack': ack}):
                        self.relayed.append([rid, ack.get('status')])
                self.failure = {'reason': 'unknown_supply_terminal_failure', 'request_id': rid, 'ack': deepcopy(ack)}; return
            if ack.get('status') == 'received' and [rid, 'received'] not in self.relayed:
                require(reuse.finite(ack.get('delivered_at')) and 0 <= ack['delivered_at'] <= now, 'own_ack_clock')
                if not self.publish(now, {'kind': 'received_ack_relay', 'request_id': rid, 'ack': ack}): return
                self.relayed.append([rid, 'received'])
        # Cap acknowledgement is terminal for this finite admission policy.
        # Do not restart invitations merely when its old peer snapshot expires.
        # Own immutable refresh/retries above remain active.
        if self.cap_observed: return
        view = self.session.observe_protocol_control_policy_recent(self.owner, base.VALIDITY)
        require(view['owner_id'] == self.owner and view['now'] == now, 'fresh_view')
        nodes = {r['node']: r for r in view['node_contracts']}; token = self.plan['token_tray_id']
        peer = base.delivered_peer(self.session.protocol_planning_snapshots_v2(self.owner), self.owner, self.peer, now, nodes)
        barrier = physical_barrier(self.client.state['outbox'], self.owner, peer, self.plan['parking'])
        if barrier is not None: self.last_barrier = deepcopy(barrier)
        if barrier is not None and barrier['known_supply_count'] >= self.plan['supply_cap']:
            self.cap_observed = True; return
        if invitation(peer, token, nodes) is not None:
            message = peer['capture']['local_capture']['message_id']
            if message not in self.replied and now >= self.next_publication:
                if not self.publish(now, {'kind': 'reply_to_actual_return', 'message_id': message}): return
                self.replied.append(message)
        if not reuse.current_empty(view, token): return
        require(nodes[next(t for t in view['trays'] if t['tray_id'] == token)['node']]['resource_owner'] == self.owner, 'fresh_token_nonlocal')
        # A missing/expired peer body must not prevent requesting a fresh one.
        # Own unresolved transfers still prevent an invitation at a source
        # that has not actually completed its preceding immutable transfer.
        if any((r.get('client_view', {}).get('last_delivered_ack') or {}).get('status') != 'received'
                for r in self.client.state['outbox'].values() if r['kind'] == 'transfer'): return
        if now >= self.next_publication:
            if not self.publish(now, {'kind': 'current_empty_invitation'}): return
        permit = local_permit(view, self.client.state['outbox'], self.owner, self.peer, token, self.consumed)
        if permit is None or peer is None or barrier is None: return
        capture_at = permit['self_copy']['envelope']['capture']['local_capture']['captured_at']
        if peer['capture']['local_capture']['captured_at'] < capture_at: return
        choice = base.eligible_head(peer, view, token)
        if choice is None: return
        receipt = permit['receipt']; rid = base.owner_request_id(self.owner, 'repeat:'+receipt['receipt_id'])
        require(rid not in self.client.state['outbox'], 'permit_reused')
        self.consumed.append(receipt['receipt_id'])  # consume before native submission, including rejection
        request = {'tray_id': token, 'source': choice['tray']['node'], 'destination': choice['job']['origin'],
            'message_delay': base.WIRE, 'earliest_departure': now, 'expiry': min(HORIZON, now+2000.)}
        selected = {'request_id': rid, 'request': deepcopy(request), 'at': now, 'choice': choice,
            'return_permit': permit, 'physical_barrier': deepcopy(barrier)}
        self.repeated.append(selected); self.decisions.append(deepcopy(selected))
        self.client.submit(self.owner, 'transfer', request, request_id=rid)

    def summary(self):
        return {**super().summary(), 'repeated': self.repeated, 'consumed': self.consumed,
            'relayed': self.relayed, 'replied': self.replied, 'repeat_publications': self.repeat_publications,
            'last_barrier': self.last_barrier, 'cap_observed': self.cap_observed, 'halt_new_actions': self.halt_new_actions}


def prove_only_cap_check_moved(old_source=None, new_source=None):
    old_source = old_source if old_source is not None else Path(reference.__file__).read_text(encoding='utf8')
    new_source = new_source if new_source is not None else Path(__file__).read_text(encoding='utf8')
    def owner(source):
        rows = [n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'RepeatOwner']
        require(len(rows) == 1, 'cap_variant_owner_ast'); return rows[0]
    old, new = owner(old_source), owner(new_source)
    condition = ast.parse("barrier is not None and barrier['known_supply_count'] >= self.plan['supply_cap']", mode='eval').body
    dump = lambda node: ast.dump(node, include_attributes=False)
    cap = lambda node: isinstance(node, ast.If) and dump(node.test) == dump(condition)
    methods = [next(n for n in c.body if isinstance(n, ast.FunctionDef) and n.name == 'activate') for c in (old, new)]
    positions = [[i for i,n in enumerate(m.body) if cap(n)] for m in methods]
    require(all(len(rows) == 1 for rows in positions), 'cap_variant_unique_check')
    old_at, new_at = positions[0][0], positions[1][0]
    require(new_at < old_at and dump(methods[0].body[old_at]) == dump(methods[1].body[new_at]), 'cap_variant_moved_unchanged')
    anchor = ast.parse('if barrier is not None: self.last_barrier = deepcopy(barrier)').body[0]
    require(dump(methods[1].body[new_at-1]) == dump(anchor), 'cap_variant_after_current_barrier')
    del methods[0].body[old_at]; del methods[1].body[new_at]
    require(dump(old) == dump(new), 'cap_variant_other_ast_changed')
    return {'status':'passed_only_existing_cap_check_moved', 'reference_source_sha256':base.sha(reference.__file__),
        'candidate_source_sha256':base.sha(__file__), 'old_statement_index':old_at, 'new_statement_index':new_at,
        'all_other_class_ast_identical':True, 'native_executions':0}


def comparison_contract():
    return {'schema':'g31.repeat_quiescent_cap.comparison.v1', 'status':'source_only_native_unexecuted',
        'cumulative_supply_caps':[3,8], 'circulating_tokens_each':1, 'total_trays_each':22,
        'startup_parking_requests_each':22, 'other_parked_trays':21, 'offered_each':28506, 'horizon_each':86400.,
        'preserved':'All original input, permissions, graph, capacity, FIFO, Storage, refresh/retry/ACK relay and actual native horizon.',
        'change':'After actual own refresh/ACK relay and fresh local view/latest valid peer physical barrier, an exhausted cumulative supply cap halts new publication/admission regardless of current token location. Current empty is still required for every new physical supply below the cap.',
        'completion':'The cap proof establishes no remaining admission budget, never current job completion. Actual LOAD/UNLOAD/HOLD/final state are audited independently.',
        'prefix':'For each owner, reconstruct its first actual valid cap proof. Compare exact global ordered API prefix through the earliest divergent proof read, excluding only finite nonnegative advance_to.result.wall_seconds. Later owner proof inputs are individually compared at their actual logical time, never by assuming unchanged global API ordinal.',
        'outcome':'Against every completed old arm, require exact same full jobs/trays/physical lifecycle and traversal receipts, offered identities and final horizon. Report protocol-message/API/native-seal differences explicitly. An old arm absent or unfinished gives no completed-arm parity certificate.',
        'cost':'Charge whole setup, source checking, both workers, all retained diagnostics and verification. No GC disabling/subtraction, no per-request averaging or100ms claim. Current2400s attempt is preserved without extension.',
        'execution':'No native launch command exists in this source-only plan. Root must approve a separately pinned runner/whole-tree budget after current attempt ends.',
        'unknown':'Both registered caps retained on timeout/rejection/failure; no strict protection for unfinished offered jobs, no39achievability.'}
