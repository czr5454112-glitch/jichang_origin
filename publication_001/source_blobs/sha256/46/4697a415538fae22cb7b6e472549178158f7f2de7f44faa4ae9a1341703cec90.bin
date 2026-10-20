"""Unexecuted owner-local single-token bridge policy for the original contract.

The frozen005 startup/first supply executes unchanged. Later decisions use
current local possession and actually delivered typed facts. No remote action
ID is interpreted as a payload. This module has no native loader or launcher.
"""
from __future__ import annotations
from copy import deepcopy
from . import research_original_low_wip as base
from . import research_original_low_wip_reuse as reuse
from .current_empty_possession_permit import PossessionGate

HORIZON = 86400.
MAX_TICKS = 8642
MAX_TOKEN_COMPLETIONS = 39
MAX_EMPTY_OPERATIONS = 2 * MAX_TOKEN_COMPLETIONS
MAX_PHYSICAL = 22 + MAX_EMPTY_OPERATIONS
MAX_PUBLICATIONS = MAX_TICKS + MAX_EMPTY_OPERATIONS + 2
SCHEMA = 'g31.cooperative_current_possession_bridge.v1'


def require(ok, reason):
    if not ok: raise ValueError('cooperative_bridge:' + reason)


def fifo_heads(jobs, owner, nodes, observed_at):
    """Current released source heads; a blocked head never exposes its successor."""
    require(type(jobs) is list and len({j['business_bag_id'] for j in jobs}) == len(jobs), 'job_scope')
    heads = {}
    for job in sorted(jobs, key=lambda j: (j['arrival'], j['business_bag_id'])):
        if job['status'] != 'waiting_for_tray' or nodes[job['origin']]['resource_owner'] != owner: continue
        require(reuse.finite(job['arrival']) and 0 <= job['arrival'] <= observed_at, 'future_head')
        heads.setdefault(job['origin'], job)
    return sorted(heads.values(), key=lambda j: (j['arrival'], j['business_bag_id']))


def completion_permit(local, extension, token, current, consumed):
    """Only a new actual local job completion can authorize another bridge.

    Empty arrival alone can authorize a direct supply, never bridge-to-bridge.
    This prevents an unsupported promise of at most two empty legs per supply.
    """
    rows = [r for r in extension['terminal_receipts'] if r['tray_id'] == token]
    if not rows: return None
    require(len({r['receipt_id'] for r in rows}) == len(rows), 'duplicate_completion')
    require(all(r['source_owner'] == local['source_owner'] and r['event'] == 'UNLOAD_COMPLETE'
        and r['status'] == 'completed' and type(r['source_local_sequence']) is int
        and r['source_local_sequence'] > 0 and reuse.finite(r['completed_at'])
        and 0 <= r['completed_at'] <= local['captured_at'] for r in rows), 'completion_authority')
    row = max(rows, key=lambda r: r['source_local_sequence'])
    if row['receipt_id'] in consumed or row['destination'] != current['node'] or row['completed_at'] > current['available_at']: return None
    return deepcopy(row)


def _count(value, why):
    require(type(value) is int and value >= 0, why)
    return value


def current_own_fifo_heads(view, own, nodes):
    """Join current compact head identities to delivered complete contracts.

    ``own`` must be the exact result of latest_own_capture in this activation;
    that caller validates the typed digest/coverage/ACK. Compact view.jobs only
    contains carried contracts and must never be read as a waiting queue.
    """
    body = own['envelope']['capture']; local = body['local_capture']; owner = view['owner_id']
    require(own['envelope']['schema'] == 'g31.planning_snapshot.v2'
        and own['envelope']['kind'] == 'planning_snapshot_v2' and body['schema'] == 'g31.planning_capture.v2'
        and local['schema'] == 'g31.planning_capture.v1' and local['source_owner'] == owner
        and reuse.finite(local['captured_at']) and 0 <= local['captured_at'] <= view['now']
        and local['coverage']['complete_for_declared_local_scope'] is True
        and local['coverage']['future_arrivals_included'] is False, 'own_head_capture_scope')
    captured = {j['origin']:j for j in fifo_heads(local['jobs'], owner, nodes, local['captured_at'])}
    projection = view['control_projection']
    require(projection['schema'] == 'g31.analytic_control_projection.v1'
        and projection['waiting_selection'] == 'fifo_prefix_cover_upper_plus_finite_tray_bound'
        and type(projection['waiting_groups']) is list, 'current_head_projection_schema')
    groups = projection['waiting_groups']; origins = set(); total = 0; result = []
    for group in groups:
        origin = group['origin']; require(type(origin) is int and origin in nodes and origin not in origins, 'current_head_origin')
        origins.add(origin); count = _count(group['count'], 'current_head_count'); total += count
        limit = _count(group['head_limit'], 'current_head_limit'); rows = group['jobs']
        require(count > 0 and type(rows) is list and len(rows) == min(count, limit)
            and [r['fifo_index'] for r in rows] == list(range(len(rows))), 'current_head_prefix')
        if nodes[origin]['resource_owner'] != owner: continue
        require(group['demand_observed_at'] == view['now'] and rows, 'current_head_missing_or_not_current')
        head = rows[0]; require(head['status'] == 'waiting_for_tray' and head['origin'] == origin
            and head['demand_observed_at'] == view['now'] and reuse.finite(head['arrival'])
            and 0 <= head['arrival'] <= view['now'] and type(head['business_bag_id']) is str
            and bool(head['business_bag_id']), 'current_head_identity')
        require(origin in captured and all(head[key] == captured[origin][key]
            for key in ('business_bag_id','origin','arrival','deadline')), 'current_head_contract_missing_or_changed')
        result.append(deepcopy(captured[origin]))
    require(total == _count(projection['exact_waiting_count'], 'current_exact_waiting_count')
        and {j['origin'] for j in result} == set(captured), 'current_head_scope_changed')
    return sorted(result, key=lambda j:(j['arrival'],j['business_bag_id']))


def choose_action(view, peer, own, token, consumed_completions):
    """Direct peer FIFO first; otherwise one bridge for a current own head.

    Static paths are necessary screens, not a claim about native route choice.
    A bridge recipient is not sent the selecting owner's proposed next job.
    """
    if peer is None or own is None or not reuse.current_empty(view, token): return None
    nodes = {n['node']: n for n in view['node_contracts']}
    roles = {n[0]: n[1] for n in view['node_records']}
    current = next(t for t in view['trays'] if t['tray_id'] == token)
    source = current['node']; owner = view['owner_id']; local = peer['capture']['local_capture']
    require(nodes[source]['resource_owner'] == owner, 'nonlocal_source')
    source_stock = _count(nodes[source]['actual_available'], 'source_stock_missing')
    if source_stock <= nodes[source]['export_min_stock'] or not nodes[source]['allow_export']: return None
    peer_nodes = {n['node']: n for n in local['nodes']}
    graph = base.public_graph(view); paths = {}
    def path(a, b):
        if a not in paths: paths[a] = base.paths_from(graph, a)
        return paths[a].get(b)
    def mandatory(job):
        stages = [job['origin']] + ([job['storage_node']] if job['storage_node'] >= 0 else []) + [job['destination']]
        result = [path(a, b) for a, b in zip(stages, stages[1:])]
        return [r[1] for r in result] if all(result) else None
    def receiving(node, facts):
        return (nodes[node]['allow_receive'] and nodes[node]['capacity'] > 0
                and _count(facts['occupancy'], 'receiver_occupancy_missing') < nodes[node]['capacity'])
    for job in fifo_heads(local['jobs'], local['source_owner'], nodes, local['captured_at']):
        destination = job['origin']; route = path(source, destination); work = mandatory(job)
        if (nodes[source]['zone'] != nodes[destination]['zone'] and route and work
                and destination in peer_nodes and receiving(destination, peer_nodes[destination])):
            return {'kind': 'direct_supply', 'destination': destination, 'selected_current_job': deepcopy(job),
                'positive_empty_path': route[1], 'positive_mandatory_paths': work,
                'peer_message_id': local['message_id'], 'bridge_followup_pre_authorized': False}
    own_local = own['envelope']['capture']['local_capture']
    proof = completion_permit(own_local, own['envelope']['capture']['extension'], token, current, consumed_completions)
    if proof is None: return None
    for job in current_own_fifo_heads(view, own, nodes):
        destination = job['origin']; work = mandatory(job)
        if not work or not receiving(destination, nodes[destination]): continue
        options = []
        for bridge in sorted(peer_nodes):
            info = nodes[bridge]; facts = peer_nodes[bridge]
            if (roles[bridge] in (1, 7) or info['resource_owner'] != local['source_owner']
                    or info['zone'] == nodes[source]['zone'] or info['zone'] == nodes[destination]['zone']
                    or not info['allow_export'] or not receiving(bridge, facts)
                    or _count(facts['actual_available'], 'bridge_stock_missing') + 1 <= info['export_min_stock']): continue
            first, second = path(source, bridge), path(bridge, destination)
            if first and second: options.append((bridge, first[1], second[1]))
        if options:
            bridge, first, second = options[0]
            return {'kind': 'bridge_empty', 'destination': bridge, 'selected_current_job': deepcopy(job),
                'positive_empty_path': first, 'possible_second_empty_path': second,
                'positive_mandatory_paths': work, 'completion_permit': proof,
                'peer_message_id': local['message_id'], 'bridge_followup_pre_authorized': False}
    return None


def received_barrier(outbox, owner, own, peer, parking, token, now):
    """Actual current own rows plus complete native self/peer action coverage."""
    if own is None or peer is None: return None
    own_local = own['envelope']['capture']['local_capture']; other = peer['capture']['local_capture']
    if other['captured_at'] < own_local['captured_at']: return None
    parks = {p['request_id']: p for p in parking}; own_rows = {}
    for rid, row in outbox.items():
        if row['kind'] == 'planning_snapshot_v2': continue
        require(row['kind'] == 'transfer', 'undeclared_own_action')
        p = row['payload']; require(p['owner_id'] == owner and p['request_id'] == rid, 'own_payload_identity')
        if rid in parks:
            require(parks[rid]['owner'] == owner and all(p[k] == parks[rid][k] for k in ('tray_id','source','destination')), 'parking_payload')
        else: require(p['tray_id'] == token, 'other_tray_moved')
        ack = (row.get('client_view') or {}).get('last_delivered_ack')
        if row.get('submission_reply', {}).get('status') == 'rejected' or not row['terminal'] or not PossessionGate._received(ack, now): return None
        own_rows[rid] = row
    self_actions = own['envelope']['capture']['extension']['submitted_physical_actions']
    other_actions = peer['capture']['extension']['submitted_physical_actions']
    if {r['request_id'] for r in self_actions} != set(own_rows): return None
    for rows, source, through in ((self_actions, owner, own_local['captured_at']), (other_actions, other['source_owner'], other['captured_at'])):
        require(all(r['kind'] == 'transfer' and r['source_owner'] == source for r in rows), 'physical_action_scope')
        if not all(PossessionGate._received(r.get('last_delivered_ack'), through) for r in rows): return None
    peer_ids = {r['request_id'] for r in other_actions}; require(not peer_ids & set(own_rows), 'duplicate_cross_owner_id')
    ids = frozenset(own_rows) | peer_ids
    if not set(parks) <= ids or any((rid in own_rows) != (p['owner'] == owner) for rid,p in parks.items()): return None
    completions = []
    for body in (own['envelope']['capture'], peer['capture']):
        local = body['local_capture']
        for row in body['extension']['terminal_receipts']:
            if row['tray_id'] != token: continue
            require(row['source_owner'] == local['source_owner'] and row['event'] == 'UNLOAD_COMPLETE'
                and row['status'] == 'completed' and reuse.finite(row['completed_at'])
                and 0 <= row['completed_at'] <= local['captured_at'], 'terminal_fact')
            completions.append(row['business_bag_id'])
    require(len(completions) == len(set(completions)), 'duplicate_terminal_fact')
    return {'received_action_ids': sorted(ids), 'postparking_empty_operations': len(ids)-len(parks),
        'token_completed_job_ids': sorted(completions), 'own_message_id': own_local['message_id'],
        'peer_message_id': other['message_id'], 'own_captured_at': own_local['captured_at'],
        'peer_captured_at': other['captured_at'], 'observed_at': now, 'remote_payload_inferred': False}


def cap_relay_evidence(summary, plan, public_contract):
    """Historical stop-message evidence only, never permission to act.

    A future independent full API replay must establish the actual first cap
    branch and its fresh barrier. This helper cannot authenticate supplied JSON
    or prove that both live owners saw one simultaneous state.
    """
    unknown = {'status': 'unknown_cap_relay', 'new_actions_authorized': False,
               'full_policy_replay_verified': False}
    try:
        relay = summary['cap_relay']; owner = summary['owner']
        peer = next(o for o in plan['owners'] if o != owner)
        require(owner in plan['owners'] and summary['cap_observed'] is True and not summary['failure'], 'cap_state')
        require(relay['publication_enqueued'] is True and relay['source_owner'] == owner and relay['target_owner'] == peer, 'cap_publication')
        proof = relay['proof']; ids = proof['received_action_ids']
        jobs = proof['token_completed_job_ids']
        require(type(ids) is list and all(type(k) is str and k for k in ids)
            and type(jobs) is list and all(type(k) is str and k for k in jobs) and len(jobs) == len(set(jobs))
            and len(ids) == len(set(ids)) and {p['request_id'] for p in plan['parking']} <= set(ids)
            and proof['postparking_empty_operations'] == len(ids)-len(plan['parking'])
            and 0 <= proof['postparking_empty_operations'] <= MAX_EMPTY_OPERATIONS and len(jobs) <= MAX_TOKEN_COMPLETIONS
            and (proof['postparking_empty_operations'] >= MAX_EMPTY_OPERATIONS
                 or len(proof['token_completed_job_ids']) >= MAX_TOKEN_COMPLETIONS), 'cap_threshold')
        require(all(reuse.finite(proof[k]) for k in ('own_captured_at','peer_captured_at','observed_at'))
            and 0 <= proof['own_captured_at'] <= proof['peer_captured_at'] <= proof['observed_at'] == relay['at'], 'cap_proof_clock')
        row = summary['outbox']['outbox'][relay['request_id']]; request = row['payload']
        ack = row.get('client_view', {}).get('last_delivered_ack') or {}
        require(row['kind'] == request['kind'] == 'planning_snapshot_v2' and row['terminal']
            and request['owner_id'] == owner and request['target_owner'] == peer
            and request['request_id'] == relay['request_id'] and ack.get('status') == 'delivered', 'cap_own_delivered_ack')
        envelope = ack['planning_snapshot_v2']; local = envelope['capture']['local_capture']
        require(all(reuse.finite(v) for v in (relay['at'],local['captured_at'],envelope['delivered_at'],ack['delivered_at'],local['valid_until']))
            and relay['at'] <= local['captured_at'] == ack['executed_at'] <= envelope['delivered_at'] == ack['completed_at']
            <= ack['delivered_at'] and envelope['delivered_at'] < local['valid_until'] == request['expiry']
            and ack['result_id'] == local['message_id'], 'cap_relay_clock_identity')
        nodes = {n['node']: n for n in public_contract['node_contracts']}
        require(base.delivered_peer([envelope], peer, owner, envelope['delivered_at'], nodes) is not None, 'cap_typed_digest')
        actions = envelope['capture']['extension']['submitted_physical_actions']
        own_ids = {rid for rid,r in summary['outbox']['outbox'].items() if r['kind'] == 'transfer'}
        require(own_ids <= set(ids) and {r['request_id'] for r in actions} == own_ids
            and all(r['kind'] == 'transfer' and PossessionGate._received(r.get('last_delivered_ack'), local['captured_at']) for r in actions), 'cap_relay_physical_scope')
        return {'status': 'historical_delivered_cap_relay', 'request_id': relay['request_id'],
            'message_id': local['message_id'], 'ack_delivered_at': ack['delivered_at'],
            'new_actions_authorized': False, 'full_policy_replay_verified': False}
    except (ValueError, KeyError, TypeError, StopIteration):
        return unknown


class BridgeOwner(base.Owner):
    """Fresh-trial controller. No native-JSON restore or implicit state reset."""
    def __init__(self, session, owner, plan):
        require(session.physical_time == 0., 'fresh_trial_only_no_JSON_restore')
        super().__init__(session, owner, plan)
        self.possession = PossessionGate(owner, plan, [p['request_id'] for p in plan['parking']])
        self.operations = []; self.consumed_completions = []; self.relayed = []; self.replied = []
        self.bridge_publications = []; self.last_barrier = None; self.cap_observed = False
        self.cap_relay = None; self.halt_new_actions = False

    def publish(self, now, reason):
        if self.publications >= MAX_PUBLICATIONS:
            self.failure = {'reason': 'unknown_publication_budget', 'at': now}; return None
        rid = base.owner_request_id(self.owner, f'bridge-snapshot:{self.publications}')
        self.client.submit(self.owner, 'planning_snapshot_v2', {'target_owner': self.peer,
            'message_delay': base.WIRE, 'publication_delay': base.WIRE, 'expiry': now+base.VALIDITY}, request_id=rid)
        self.publications += 1; self.next_publication = now+base.PERIOD
        self.bridge_publications.append({'request_id': rid, 'at': now, 'reason': deepcopy(reason)})
        return rid

    def activate(self):
        if self.halt_new_actions:
            self.client.refresh(owner_id=self.owner); return
        was_quiet = self.quiet
        super().activate()  # exact frozen005 startup, first supply and immutable refresh
        if not was_quiet or self.failure or self.index != len(self.rows): return
        now = self.session.physical_time; box = self.client.state['outbox']; parks = self.possession.parking
        for rid, row in list(box.items()):
            if row['kind'] != 'transfer' or rid in parks: continue
            ack = (row.get('client_view') or {}).get('last_delivered_ack') or {}
            if row.get('submission_reply', {}).get('status') == 'rejected' or (row['terminal'] and ack.get('status') != 'received'):
                self.failure = {'reason': 'unknown_physical_failure', 'request_id': rid, 'at': now}; return
            if ack.get('status') == 'received' and rid not in self.relayed:
                require(PossessionGate._received(ack, now), 'received_clock')
                if self.publish(now, {'kind': 'actual_received_ack_relay', 'request_id': rid}) is None: return
                self.relayed.append(rid)
        for publication in self.bridge_publications:
            row = box[publication['request_id']]; ack = (row.get('client_view') or {}).get('last_delivered_ack') or {}
            if row.get('submission_reply', {}).get('status') == 'rejected' or (row['terminal'] and ack.get('status') != 'delivered'):
                self.failure = {'reason': 'unknown_publication_failure', 'request_id': publication['request_id'], 'at': now}; return
        if self.cap_observed: return
        view = self.session.observe_protocol_control_policy_recent(self.owner, base.VALIDITY)
        require(view['owner_id'] == self.owner and view['now'] == now, 'current_view')
        nodes = {n['node']: n for n in view['node_contracts']}
        envelopes = self.session.protocol_planning_snapshots_v2(self.owner)
        peer = base.delivered_peer(envelopes, self.owner, self.peer, now, nodes)
        own = reuse.latest_own_capture(box, self.owner, self.peer, now, nodes)
        barrier = received_barrier(box, self.owner, own, peer, self.plan['parking'], self.plan['token_tray_id'], now)
        if barrier is not None:
            self.last_barrier = deepcopy(barrier)
            if (barrier['postparking_empty_operations'] >= MAX_EMPTY_OPERATIONS
                    or len(barrier['token_completed_job_ids']) >= MAX_TOKEN_COMPLETIONS):
                self.cap_observed = True
                rid = self.publish(now, {'kind': 'terminal_cap_barrier_relay'})
                self.cap_relay = {'request_id': rid, 'at': now, 'proof': deepcopy(barrier),
                    'source_owner': self.owner, 'target_owner': self.peer, 'publication_enqueued': rid is not None}
                return
        if peer is not None:
            local = peer['capture']['local_capture']
            if reuse.current_empty({'now': local['captured_at'], 'trays': local['trays']}, self.plan['token_tray_id']):
                if local['message_id'] not in self.replied and now >= self.next_publication:
                    if self.publish(now, {'kind': 'reply_to_current_empty', 'message_id': local['message_id']}) is None: return
                    self.replied.append(local['message_id'])
        if not reuse.current_empty(view, self.plan['token_tray_id']): return
        if any(not PossessionGate._received((r.get('client_view') or {}).get('last_delivered_ack'), now)
               for r in box.values() if r['kind'] == 'transfer'): return
        if now >= self.next_publication:
            if self.publish(now, {'kind': 'current_empty_invitation'}) is None: return
        if barrier is None: return
        choice = choose_action(view, peer, own, self.plan['token_tray_id'], self.consumed_completions)
        if choice is None: return
        permit = self.possession.consume(view, box, envelopes)
        if permit is None: return
        current = permit['current_token']; body = permit['own_delivered_selfcopy']['envelope']['capture']
        completion = completion_permit(body['local_capture'], body['extension'], self.plan['token_tray_id'], current, self.consumed_completions)
        if completion is not None: self.consumed_completions.append(completion['receipt_id'])
        rid = base.owner_request_id(self.owner, f'bridge-operation:{len(self.operations)+1}')
        require(rid not in box, 'operation_identity_reused')
        request = {'tray_id': self.plan['token_tray_id'], 'source': current['node'], 'destination': choice['destination'],
            'message_delay': base.WIRE, 'earliest_departure': now, 'expiry': min(HORIZON, now+2000.)}
        decision = {'request_id': rid, 'request': deepcopy(request), 'at': now, 'choice': choice,
            'possession_permit': permit, 'physical_barrier': deepcopy(barrier)}
        self.operations.append(decision); self.decisions.append(deepcopy(decision))
        self.client.submit(self.owner, 'transfer', request, request_id=rid)

    def controller_checkpoint(self):
        return {'owner': self.owner, 'client_state': deepcopy(self.client.state),
            'possession': self.possession.checkpoint(), 'consumed_completions': list(self.consumed_completions),
            'operations': deepcopy(self.operations), 'relayed': list(self.relayed), 'replied': list(self.replied),
            'cap_observed': self.cap_observed, 'cap_relay': deepcopy(self.cap_relay),
            'restore_supported': False, 'scope': 'Diagnostic controller state only; no native-JSON restore or crash recovery certification.'}

    def summary(self):
        return {**super().summary(), 'operations': deepcopy(self.operations), 'consumed_completions': list(self.consumed_completions),
            'possession': self.possession.checkpoint(), 'relayed': list(self.relayed), 'replied': list(self.replied),
            'bridge_publications': deepcopy(self.bridge_publications), 'last_barrier': deepcopy(self.last_barrier),
            'cap_observed': self.cap_observed, 'cap_relay': deepcopy(self.cap_relay), 'halt_new_actions': self.halt_new_actions}


def run_policy(session, plan, progress=None):
    # Global halt is experiment management after a failed premise. It is not
    # owner-visible coordination and cannot support a successful online-policy
    # claim. Failed campaigns stay unknown even if physical H is later reached.
    owners = [BridgeOwner(session, owner, plan['parking_plan']) for owner in plan['parking_plan']['owners']]
    status = 'unknown_incomplete'; tick = 0; halted = False
    for tick in range(MAX_TICKS):
        for owner in owners:
            halted = halted or any(o.failure for o in owners); owner.halt_new_actions = halted
            try:
                owner.activate()
            except (ValueError, KeyError, TypeError) as error:
                # A malformed/missing public premise cannot create an action
                # or terminate physical observation early. Subsequent ticks
                # retain the same immutable outbox and only refresh/retry it.
                owner.failure = {'reason': 'unknown_public_guard_failure',
                    'error': type(error).__name__ + ':' + str(error), 'at': session.physical_time}
                owner.halt_new_actions = True; halted = True
        halted = halted or any(o.failure for o in owners)
        calls = [c for o in owners for c in o.client.calls]
        require(sum(c['kind'] == 'transfer' and not c['retry'] for c in calls) <= MAX_PHYSICAL, 'physical_budget')
        if progress: progress(tick, owners)
        if session.physical_time >= HORIZON:
            status = 'horizon_complete_with_policy_failure' if halted else 'horizon_complete'; break
        target = min(HORIZON, session.physical_time+base.PERIOD)
        result = session.advance_to(target, max_events=100000)
        if result.get('status') != 'reached' or result.get('horizon_complete') is not True or session.physical_time != target:
            status = 'unknown_native_budget'; break
    return owners, status, tick


def scope():
    return {'schema': SCHEMA, 'status': 'source_only_unexecuted_policy_prototype', 'offered': 28506, 'total_tray_identities': 22,
        'noncirculating_parked_trays': 21, 'startup': 'Frozen005 Owner executes unchanged through22 parking transfers and first supply.',
        'horizon': HORIZON, 'max_physical_requests': MAX_PHYSICAL, 'max_postparking_empty_operations': MAX_EMPTY_OPERATIONS,
        'max_actual_token_completions': MAX_TOKEN_COMPLETIONS, 'max_publications_per_owner': MAX_PUBLICATIONS,
        'budget_basis': '39 is a conditional necessary zero-bad-loader-prefix bound for this fixed original input, not an achievable schedule. At most one bridge may follow each consumed local completion, and bridge arrival can only make a direct supply.78 bounds two empty operations per putative39 supplies.',
        'selection': 'Current delivered peer FIFO heads first; only otherwise a current own FIFO head via the least feasible public opposite-zone nonloader/nonStorage bridge. Positive paths and public berth/stock are necessary screens only.',
        'cooperation': 'Only these two source policies submit physical operations; all post-parking operations use one token, at most one outstanding token transfer, with21others left parked. Peer opaque IDs do not authenticate remote payloads or future plans.',
        'checkpoint': 'Consumed exact action sets and completion receipts are exported with client state, but this prototype only constructs at physicaltime0. No native JSON restoration or resume is supported.',
        'failure': 'Any terminal failure or bound exhaustion globally halts new actions while immutable refresh/retries and native progress continue toH; unknown is retained. This cross-owner failure inspection is experiment management only, not a lawful distributed recovery or successful-policy decision. Stopcap requires both actual fresh owner proofs and delivered one-shot relay ACK evidence.',
        'assessment_pending': 'Future independent saved audit must bind all offered jobs, every parking/transfer ACK, token LOAD/UNLOAD/HOLD, bridge EMPTY_RECEIVED receipts offline, no other tray movement, fullH and stopcap handshakes. No oldcap8 timing/protection comparison is declared.',
        'native_calls': 0, 'native_authority_certified': False, 'whole_day_business_success': False, 'complete_100ms_certified': False}
