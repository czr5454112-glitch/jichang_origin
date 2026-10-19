"""Bounded cooperative owner-local single-token policy; never infer peer payloads."""
from __future__ import annotations
import argparse
import ast
from contextlib import contextmanager
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from . import research_original_low_wip as base
from . import research_original_low_wip_reuse as reuse

ROOT, OUT = base.ROOT, base.OUT
SCHEMA = 'g31.original_low_wip_repeating.v1'
HORIZON, MAX_TICKS, MAX_PUBLICATIONS = 86400., 8642, 512
CAPS, PARENT_SECONDS = {'cap3': 3, 'cap8': 8}, 2400.
MODULE = 'scripts.experiments.g31_ics_circulation.research_original_low_wip_repeat'
BASE_SHA = reuse.BASE_SHA
REUSE_SHA = 'e91ada16a9f6089ffb49ac79e06fff492be467e54ee8074bd46c3c47e1742a02'
BaseOwner = base.Owner
_old_verify, _installed = base.verify_pins, False


def require(ok, why): base.require(ok, 'repeat:' + why)


def is_supply(request_id, owner):
    if request_id == base.owner_request_id(owner, 'single-supply'): return True
    prefix = base.owner_request_id(owner, f'repeat:completion:{len(owner.encode("utf8"))}:{owner}:')
    if not request_id.startswith(prefix): return False
    sequence = request_id[len(prefix):]
    return sequence.isascii() and sequence.isdecimal() and str(int(sequence)) == sequence and int(sequence) > 0


def receipt_for_token(local, extension, token, owner, nodes):
    """Newest local completion only; never resurrect an older consumed receipt."""
    rows = [r for r in extension['terminal_receipts'] if r['tray_id'] == token]
    if not rows: return None
    require(len({r['receipt_id'] for r in rows}) == len(rows), 'duplicate_receipt')
    require(all(type(r['source_local_sequence']) is int and r['source_local_sequence'] > 0
        and reuse.finite(r['completed_at']) and 0 <= r['completed_at'] <= local['captured_at']
        and r['source_owner'] == owner and r['event'] == 'UNLOAD_COMPLETE' and r['status'] == 'completed'
        and nodes[r['destination']]['resource_owner'] == owner for r in rows), 'receipt_authority')
    require(len({r['source_local_sequence'] for r in rows}) == len(rows), 'duplicate_receipt_sequence')
    return max(rows, key=lambda r: r['source_local_sequence'])


def invitation(envelope, token, nodes):
    if envelope is None: return None
    body = envelope['capture']; local = body['local_capture']; owner = local['source_owner']
    if not reuse.current_empty({'now': local['captured_at'], 'trays': local['trays']}, token): return None
    receipt = receipt_for_token(local, body['extension'], token, owner, nodes)
    if receipt is None: return None
    tray = next(t for t in local['trays'] if t['tray_id'] == token)
    if tray['node'] != receipt['destination'] or receipt['completed_at'] > tray['available_at']: return None
    return receipt


def local_permit(view, outbox, owner, peer, token, consumed):
    require(view['owner_id'] == owner, 'permit_owner')
    if not reuse.current_empty(view, token): return None
    nodes = {r['node']: r for r in view['node_contracts']}
    tray = next(t for t in view['trays'] if t['tray_id'] == token)
    require(nodes[tray['node']]['resource_owner'] == owner, 'permit_nonlocal_token')
    own = reuse.latest_own_capture(outbox, owner, peer, view['now'], nodes)
    if own is None: return None
    body = own['envelope']['capture']; local = body['local_capture']
    receipt = receipt_for_token(local, body['extension'], token, owner, nodes)
    if receipt is None or receipt['receipt_id'] in consumed: return None
    if tray['node'] != receipt['destination'] or receipt['completed_at'] > tray['available_at']: return None
    return {'receipt': deepcopy(receipt), 'self_copy': deepcopy(own), 'current_token': deepcopy(tray), 'observed_at': view['now']}


def physical_barrier(outbox, owner, peer_envelope, parking):
    """All source actions must have delivered received ACKs; IDs do NOT map jobs."""
    if peer_envelope is None: return None
    peer = peer_envelope['capture']['local_capture']['source_owner']
    captured = peer_envelope['capture']['local_capture']['captured_at']
    rows = []
    for rid, row in outbox.items():
        if row['kind'] == 'planning_snapshot_v2': continue
        require(row['kind'] == 'transfer', 'unexpected_own_physical_kind')
        rows.append((owner, rid, row.get('client_view', {}).get('last_delivered_ack') or {}))
    actions = peer_envelope['capture']['extension']['submitted_physical_actions']
    for action in actions:
        require(action['source_owner'] == peer and action['kind'] == 'transfer', 'unexpected_peer_physical_kind')
        ack = action.get('last_delivered_ack') or {}
        if ack and (not reuse.finite(ack.get('delivered_at')) or not 0 <= ack['delivered_at'] <= captured):
            raise ValueError('repeat:peer_ack_clock')
        rows.append((peer, action['request_id'], ack))
    ids = [r[1] for r in rows]
    require(len(ids) == len(set(ids)), 'duplicate_action')
    parks = {r['request_id'] for r in parking}
    for source, rid, ack in rows:
        require(rid in parks or is_supply(rid, source), 'undeclared_physical_action')
    if not parks <= set(ids): return None
    for source, rid, ack in rows:
        if ack.get('status') != 'received': return None
    return {'known_supply_count': len(ids)-len(parks), 'received_request_ids': ids,
        'peer_message_id': peer_envelope['capture']['local_capture']['message_id']}


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
        if invitation(peer, token, nodes) is not None:
            message = peer['capture']['local_capture']['message_id']
            if message not in self.replied and now >= self.next_publication:
                if not self.publish(now, {'kind': 'reply_to_actual_return', 'message_id': message}): return
                self.replied.append(message)
        if not reuse.current_empty(view, token): return
        require(nodes[next(t for t in view['trays'] if t['tray_id'] == token)['node']]['resource_owner'] == self.owner, 'fresh_token_nonlocal')
        if barrier is not None and barrier['known_supply_count'] >= self.plan['supply_cap']:
            self.cap_observed = True; return
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


def run_policy(session, plan, progress=None):
    local = {**plan['parking_plan'], 'supply_cap': plan['supply_cap']}
    owners = [RepeatOwner(session, owner, local) for owner in local['owners']]
    status = 'unknown_incomplete'; tick = 0; halted = False
    for tick in range(MAX_TICKS):
        for owner in owners:
            # Experiment-wide failure shutdown only. This flag cannot choose a
            # job, authorize a handoff or improve any assessed policy outcome.
            halted = halted or any(o.failure for o in owners)
            owner.halt_new_actions = bool(halted)
            owner.activate()
        halted = halted or any(o.failure for o in owners)
        calls = [r for o in owners for r in o.client.calls]
        require(sum(r['kind'] == 'transfer' and not r['retry'] for r in calls) <= 22+plan['supply_cap'], 'physical_budget')
        if progress: progress(tick, owners)
        if session.physical_time >= HORIZON:
            status = 'horizon_complete_with_policy_failure' if halted else 'horizon_complete'; break
        target = min(HORIZON, session.physical_time+base.PERIOD)
        response = session.advance_to(target, max_events=100000)
        if response.get('status') != 'reached' or response.get('horizon_complete') is not True or session.physical_time != target:
            status = 'unknown_native_budget'; break
    return owners, status, tick


def supplies(raw):
    rows = [r for o in raw['owners'] for r in ([o['supply']] if o['supply'] else []) + o['repeated']]
    require(len({r['request_id'] for r in rows}) == len(rows), 'duplicate_supplies')
    return sorted(rows, key=lambda r: (r['at'], r['request_id']))


def assess(raw, plan):
    token = plan['parking_plan']['token_tray_id']; selected = supplies(raw); receipts = raw['result'].get('receipts', [])
    witnesses = []
    for row in selected:
        job = row['choice']['job']; matches = [[r for r in receipts if r.get('tray_id') == token
            and r.get('business_bag_id') == job['business_bag_id'] and r.get('event') == event]
            for event in ('LOAD_START', 'LOAD_COMPLETE', 'UNLOAD_COMPLETE', 'HOLD_COMPLETE')]
        if not all(len(r) == 1 for r in matches): continue
        load, loaded, unload, hold = [r[0] for r in matches]
        if (all(reuse.finite(r['time']) for r in (load, loaded, unload, hold))
                and row['at'] <= load['time'] <= loaded['time'] <= unload['time'] <= hold['time'] <= HORIZON
                and load['node'] == loaded['node'] == job['origin'] and unload['node'] == hold['node'] == job['destination']):
            witnesses.append({'job': job['business_bag_id'], 'request_id': row['request_id'], 'tray_id': token,
                'load': load, 'load_complete': loaded, 'unload': unload, 'hold_complete': hold})
    actual_loads = [(r['business_bag_id'], r['tray_id']) for r in receipts if r.get('event') == 'LOAD_START']
    only_selected = actual_loads == [(w['job'], token) for w in witnesses]
    sequential = len(witnesses) == len(selected) and len({w['job'] for w in witnesses}) == len(selected)
    sequential = sequential and all(witnesses[i]['hold_complete']['time'] <= selected[i+1]['at'] for i in range(len(selected)-1))
    physical = [r for o in raw['owners'] for r in o['outbox']['outbox'].values() if r['kind'] == 'transfer']
    received = len(physical) == 22+len(selected) and all((r.get('client_view', {}).get('last_delivered_ack') or {}).get('status') == 'received' for r in physical)
    empty = [t for t in raw['result']['trays'] if t['tray_id'] == token and t['mode'] == 'empty' and t['job'] == -1
        and t['edge_to'] < 0 and t.get('reception_node', -1) < 0 and reuse.finite(t['available_at']) and t['available_at'] <= raw['physical_time']]
    complete = (raw['status'] == 'horizon_complete' and raw['physical_time'] == HORIZON
        and raw['result']['advance']['horizon_complete'] is True and sequential and only_selected and received
        and len(empty) == 1 and sum(o['index'] for o in raw['owners']) == 22 and raw['physical_audit']['status'] == 'passed')
    return {'schema': SCHEMA, 'status': 'complete_finite_policy_evidence' if complete else 'unknown_or_incomplete_policy_evidence',
        'offered': 28506, 'arrived': sum(j['status'] != 'unreleased' for j in raw['result']['jobs']),
        'horizon': raw['physical_time'], 'supply_cap': plan['supply_cap'], 'actual_supplies': len(selected),
        'completion_witnesses': witnesses, 'all_physical_received': received, 'only_selected_jobs_loaded': only_selected,
        'same_token_sequential': sequential, 'final_token_empty': len(empty) == 1,
        'full_horizon_complete': raw['physical_time'] == HORIZON and raw['result']['advance']['horizon_complete'] is True,
        'new_actions_halted': any(o.get('halt_new_actions') or o['failure'] for o in raw['owners']),
        'strict_protection': 'not_assessed', 'complete_100ms_certified': False}


def source_paths():
    pending = [Path(__file__), Path(__file__).with_name('verify_original_low_wip_repeat.py'),
        Path(__file__).with_name('launch_original_low_wip_repeat.py'), ROOT/'tests/test_g31_circulation_low_wip_repeat.py']
    found = set()
    def enqueue(target):
        for p in (target.with_suffix('.py'), target/'__init__.py'):
            if p.is_file() and p.resolve().is_relative_to(ROOT):
                pending.append(p)
                for parent in p.parents:
                    if parent == ROOT: break
                    if (parent/'__init__.py').is_file(): pending.append(parent/'__init__.py')
    while pending:
        path = pending.pop().resolve()
        if path in found: continue
        require(path.is_file(), 'source_missing'); found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.ImportFrom):
                for target in ([path.parent] if node.level else [ROOT, ROOT/'src']):
                    for _ in range(max(node.level-1, 0)): target = target.parent
                    if node.module: target = target.joinpath(*node.module.split('.')); enqueue(target)
                    for alias in node.names:
                        if alias.name != '*': enqueue(target/alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for target in (ROOT, ROOT/'src'): enqueue(target.joinpath(*alias.name.split('.')))
    return sorted(found)


def verify_pins(output, plan, runtime=False):
    require(base.sha(base.__file__) == BASE_SHA and base.sha(reuse.__file__) == REUSE_SHA, 'frozen_predecessor')
    require(plan['schema'] == SCHEMA and plan['horizon'] == HORIZON and plan['supply_cap'] in CAPS.values()
        and plan['max_physical_requests'] == 22+plan['supply_cap'] and plan['max_ticks'] == MAX_TICKS
        and plan['max_repeat_publications_per_owner'] == MAX_PUBLICATIONS and plan['parent_timeout_seconds'] == PARENT_SECONDS
        and plan['repeat_contract'] == contract(), 'scope_changed')
    require(set(plan['source_before']) == {str(p) for p in source_paths()}, 'source_closure')
    require(plan['bootstrap_reference'] == str(OUT/'original_low_wip_prepare_005')
        and set(plan['bootstrap_pins']) == {'receipt.json','raw_final.json.gz','api/manifest.jsonl','input.json.gz'}, 'bootstrap_reference')
    for name, digest in plan['bootstrap_pins'].items(): require(base.sha(Path(plan['bootstrap_reference'])/name) == digest, 'bootstrap_evidence_changed')
    _old_verify(output, plan, runtime)


@contextmanager
def installed():
    global _installed
    require(not _installed, 'overlapping_context')
    values = {'Owner': RepeatOwner, 'run_policy': run_policy, 'assess': assess, 'source_paths': source_paths,
        'verify_pins': verify_pins, 'SCHEMA': SCHEMA, 'HORIZON': HORIZON, 'MAX_TICKS': MAX_TICKS, 'MAX_PHYSICAL': 30}
    prior = {k: getattr(base, k) for k in values}; _installed = True
    try:
        for k, v in values.items(): setattr(base, k, v)
        yield
    finally:
        for k, v in prior.items(): setattr(base, k, v)
        _installed = False


def contract():
    return {'caps': CAPS, 'horizon': HORIZON, 'offered': 28506, 'trays': 22, 'original_r1': False,
        'parking': 'Frozen005 startup and first supply,21 parked trays never used again.',
        'authority': 'Cooperative two-owner single-token contract. Current native owner alone may consume a new source-owned terminal receipt plus fresh empty/HOLD and own delivered v2 selfcopy. Native snapshots do not certify future Python plans.',
        'barrier': 'Own and latest delivered peer complete physical action coverage must all have receivedACK. No remote payload/job inference. Actual receivedACK change publishes nativev2 even after token departure.',
        'choice': 'Current latest delivered peer per-origin FIFO heads only; cross-zone permissions and all mandatory positive-capacity paths. No fixedjob, alternatehead or samezone fallback.',
        'limits': 'Cumulative SUPPLY caps3/8, both WIP1. Ten-second activation,512new repeat publications perowner. Any policy failure halts all NEW experiment actions but preserves own immutable refresh/retry/native progress toH; failure status never becomes successful merely atH. Shutdown is an external censoring mechanism, not an online scheduling fact. One shared2400s WindowsJob including both native workers and all verifiers.',
        'claims': 'Finite policy completion and alloffered denominator. No39achievability, strictprotection, deadline or100ms certificate.'}


def prepare(output):
    require(not output.exists(), 'output_exists'); output.mkdir(parents=True)
    source = OUT/'full_stream_native024_001/full1x/input.json.gz'
    binary = ROOT/'build_lt_session_026/python/czr005_circulation.cp311-win_amd64.pyd'
    plans = {}
    with installed():
        for name, cap in CAPS.items():
            directory = output/name; plan = base.prepare(directory, source, binary)
            plan.update(supply_cap=cap, max_physical_requests=22+cap, max_repeat_publications_per_owner=MAX_PUBLICATIONS,
                parent_timeout_seconds=PARENT_SECONDS, repeat_contract=contract())
            plan['policy_contract'] = contract()['parking']+' '+contract()['authority']+' '+contract()['barrier']+' '+contract()['choice']
            plan['conditional_quiescence'] = 'Only this cooperative twoowner controller submits physical actions;21 parked trays never move;single designatedtoken, no thirdpartyomniscience. Supply cap is cumulative, not WIP3/8.'
            plan['bootstrap_reference'] = str(OUT/'original_low_wip_prepare_005')
            plan['bootstrap_pins'] = {name: base.sha(Path(plan['bootstrap_reference'])/name)
                for name in ('receipt.json','raw_final.json.gz','api/manifest.jsonl','input.json.gz')}
            plan['assessment'] = contract()['claims']; base.write(directory/'preregistered_protocol.json', plan)
            verify_pins(directory, plan); plans[name] = base.sha(directory/'preregistered_protocol.json')
    campaign = {'schema': SCHEMA, 'status': 'prepared_native_unexecuted', 'contract': contract(), 'case_plans': plans,
        'source_before': {str(p): base.sha(p) for p in source_paths()}, 'interpreter': {'path': sys.executable, 'sha256': base.sha(sys.executable)},
        'parent_seconds': PARENT_SECONDS, 'native_workers_at_once': 1}
    base.write(output/'campaign.json', campaign)
    base.write(output/'branch_ledger.json', {name: {'status': 'unknown_unexecuted'} for name in CAPS})
    return campaign


def verify_campaign(output):
    plan = base.read(output/'campaign.json')
    require(plan['schema'] == SCHEMA and plan['contract'] == contract() and plan['parent_seconds'] == PARENT_SECONDS
        and set(plan['case_plans']) == set(CAPS) and plan['native_workers_at_once'] == 1, 'campaign_scope')
    require(plan['source_before'] == {str(p): base.sha(p) for p in source_paths()}, 'campaign_source')
    require(base.sha(plan['interpreter']['path']) == plan['interpreter']['sha256'], 'interpreter')
    for name in CAPS:
        case = output/name
        require(base.sha(case/'preregistered_protocol.json') == plan['case_plans'][name], 'case_plan')
        verify_pins(case, base.read(case/'preregistered_protocol.json'))
    return plan


def campaign_worker(output, admission):
    require(sys.stdin.readline().rstrip('\n') == admission, 'outer_job_admission')
    require(base.sha(output/'campaign.json') == admission
        and base.read(output/'external_launch_claim.json')['campaign_sha256'] == admission, 'outer_campaign_identity')
    began = time.monotonic(); plan = verify_campaign(output)
    ledger = {name: {'status': 'unknown_unexecuted'} for name in CAPS}
    def child(args, log):
        remaining = PARENT_SECONDS-(time.monotonic()-began)
        if remaining <= 0: return {'status': 'unknown_shared_budget', 'exit_code': None}
        command = [sys.executable, '-m', MODULE, '--output', str(output), *args]
        start = time.monotonic()
        with log.open('xb') as stream:
            try:
                code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=remaining).returncode
                status = 'child_finished' if code == 0 else 'unknown_child_nonzero'
            except subprocess.TimeoutExpired: code, status = None, 'unknown_shared_timeout'
        return {'status': status, 'exit_code': code, 'command': command, 'wall_seconds': time.monotonic()-start, 'allowed_seconds': remaining}
    for name in CAPS:
        case = output/name; case_plan = base.read(case/'preregistered_protocol.json')
        base.claim_execution(case, case_plan)
        ledger[name] = {'status': 'unknown_in_progress'}; base.write(output/'branch_ledger.json', ledger)
        execution = child(['--worker', name], case/'worker.log')
        verification = child(['--verify', name], case/'verification.log') if execution['exit_code'] == 0 else {'status': 'unknown_worker_incomplete', 'exit_code': None}
        ledger[name] = {'status': 'completed_saved_case' if verification['exit_code'] == 0 else 'unknown_incomplete_case',
            'execution': execution, 'verification': verification}
        base.write(output/'branch_ledger.json', ledger)
    comparison = child(['--compare'], output/'comparison.log') if all(v['status'] == 'completed_saved_case' for v in ledger.values()) else {'status': 'unknown_incomplete_denominator', 'exit_code': None}
    verify_campaign(output)
    receipt = {'schema': SCHEMA, 'status': 'completed_finite_campaign' if comparison['exit_code'] == 0 else 'unknown_incomplete_campaign',
        'campaign_sha256': base.sha(output/'campaign.json'), 'cases': ledger, 'comparison': comparison,
        'wall_seconds': time.monotonic()-began, 'source_changed': [], 'strict_protection': 'not_assessed', 'complete_100ms_certified': False}
    receipt['finite_pair_assessment'] = base.read(output/'comparison.json') if (output/'comparison.json').is_file() else {'status':'unknown_unassessed_pair'}
    receipt['artifact_sha256'] = {str(path.relative_to(output)):base.sha(path) for path in
        [output/'branch_ledger.json', output/'comparison.json', *[output/name/file for name in CAPS
            for file in ('raw_final.json.gz','assessment.json','api/manifest.jsonl','independent_verification.json','worker.log','verification.log','error_prefix.json.gz')]] if path.is_file()}
    base.write(output/'receipt.json', receipt)
    return 0 if receipt['status'] == 'completed_finite_campaign' else 1


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--output', required=True, type=Path)
    p.add_argument('--prepare', action='store_true'); p.add_argument('--worker', choices=tuple(CAPS)); p.add_argument('--verify', choices=tuple(CAPS))
    p.add_argument('--compare', action='store_true'); p.add_argument('--campaign', action='store_true'); p.add_argument('--admission')
    a = p.parse_args(); output = a.output.resolve()
    require(sum((a.prepare, bool(a.worker), bool(a.verify), a.compare, a.campaign)) == 1, 'mode')
    if a.prepare: prepare(output); print('prepared_native_unexecuted'); return
    if a.campaign: raise SystemExit(campaign_worker(output, a.admission))
    if a.worker:
        with installed(): base.worker(output/a.worker)
    else:
        from . import verify_original_low_wip_repeat as verifier
        result = verifier.verify_case(output/a.verify) if a.verify else verifier.compare(output)
        path = output/a.verify/'independent_verification.json' if a.verify else output/'comparison.json'
        require(not path.exists(), 'verification_already_exists'); base.write(path, result); print(json.dumps(result))


if __name__ == '__main__': main()
