"""Prepared finite initial-A campaign; execution requires an owned launcher.

The accepted native session is never replaced by an observation proxy. Saved
evidence covers every immutable submission/retry, scheduler boundary and root
endpoint, plus the original continuation's own decision/exchange evidence.
It does not claim a replay of every internal native query.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import traceback
from types import FunctionType, SimpleNamespace

from . import initial_owner_route_request as request
from . import initial_owner_route_contract as contract
from . import initial_owner_route_image as image
from .initial_owner_route_client import InitialOwnerClient

public = request.public
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
SCHEMA = 'g31.initial_owner_route_campaign.v1'
LIMIT = 600.
ARMS = ('fixed_default', 'budget_two')
FAULTS = ('normal', 'initial_ack_drop3', 'postsubmit_source_outage', 'postsubmit_B_execution_outage')


def require(value, reason):
    if not value:
        raise ValueError('initial_campaign:' + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def ordered(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf8')


def declarations():
    cases = public.domain.cases()
    rows = {}
    for case in cases:
        for arm in ARMS:
            key = 'normal/' + case['case_id'] + '/' + arm
            rows[key] = {'case': copy.deepcopy(case), 'method': arm, 'fault': 'normal'}
    for fault in FAULTS[1:]:
        for arm in ARMS:
            key = fault + '/' + cases[0]['case_id'] + '/' + arm
            rows[key] = {'case': copy.deepcopy(cases[0]), 'method': arm, 'fault': fault}
    require(len(cases) == 6 and len(rows) == 18, 'fixed_denominator')
    return rows


def scene(row):
    require(row in declarations().values(), 'undeclared_scene')
    data = public.native_scene(row['case'])
    protocol = data['owner_protocol']
    if row['fault'] == 'initial_ack_drop3':
        protocol['drop_ack_packets'] = 3
    elif row['fault'] in ('postsubmit_source_outage', 'postsubmit_B_execution_outage'):
        # Actual accepted027 owner availability gates wire execution/publication,
        # NOT already-created ACK delivery. No route-only ACK selector exists.
        owner = 'A' if row['fault'] == 'postsubmit_source_outage' else 'B'
        protocol['owner_outages'] = [{'owner': owner, 'start': .115, 'end': 2.}]
    return data


def captured_collection(records, *args, **kwargs):
    native, session, owner, identity = args
    information, ledger = request.adapter.collect_initial_ledger(*args, **kwargs)
    endpoints = {'owner': owner, 'request_id': identity, 'at': session.physical_time,
        'view': session.observe_protocol(owner), 'command': session.protocol_command(owner, identity),
        'received': session.protocol_planning_snapshots(owner)}
    # Only the initial collector's ordinary dict is copied, never a later
    # NativeCollectedV3 carrying a live accepted/session capability.
    records.append({'information': copy.deepcopy(information), 'endpoints': endpoints,
                    'ledger': ledger.audit_copy() if ledger is not None else None})
    return information, ledger


def call_with_recorded_collection(function, records, *args, **kwargs):
    facade = SimpleNamespace(**vars(request.adapter))
    facade.collect_initial_ledger = lambda *a, **k: captured_collection(records, *a, **k)
    private = FunctionType(function.__code__, {**function.__globals__, 'adapter': facade},
                           function.__name__, function.__defaults__, function.__closure__)
    private.__kwdefaults__ = function.__kwdefaults__
    return private(*args, **kwargs)


class CapturedRequest(request.InitialOwnerRequest):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial_endpoint_records = []
        self.B_endpoint_records = []

    def collect(self):
        return call_with_recorded_collection(request.InitialOwnerRequest.collect,
                                            self.initial_endpoint_records, self)

    def final_revalidate_and_submit(self):
        return call_with_recorded_collection(request.InitialOwnerRequest.final_revalidate_and_submit,
                                            self.initial_endpoint_records, self)

    def evidence(self):
        result = super().evidence()
        result['evidence']['initial_endpoint_records'] = copy.deepcopy({
            'A': self.initial_endpoint_records, 'B': self.B_endpoint_records})
        result['evidence']['scope'] = ('Actual finite initial-A first-hop evidence; future fixed continuation '
            'and full-H outcome are separate. No full32, protection or universal100ms certificate.')
        result['encoded'] = image.artifact_encode(result['evidence'])
        result['body_finished_ns'] = time.perf_counter_ns()
        result['body_elapsed_ns'] = result['body_finished_ns'] - self.started_ns
        return result


class FixedDefaultRequest(CapturedRequest):
    """An explicit physical control, not a truncated or evaluated solver."""
    def choose(self):
        require(self.state == 'collected', 'fixed_choice_without_collection')
        self.choice = 'native_default'
        self._record('predeclared_default_control', {
            'baseline_simulated': False, 'candidate_evaluations': 0,
            'participation_contract_sha256': contract.contract_sha256()})
        self.state = 'selected'


def finish_root(root):
    """Return encoding and ledger work are charged, then caller stamps outside."""
    start = time.perf_counter_ns()
    value = root.evidence()
    encoded = value.pop('encoded')
    decoded = image.artifact_decode(encoded)
    require(decoded == value['evidence'], 'root_codec_roundtrip')
    ledger = {'root_id': root.request_id, 'evidence_sha256': hashlib.sha256(encoded).hexdigest(),
              'bytes': len(encoded), 'state': root.state, 'choice': root.choice}
    # A returned independent copy and its full JSON representation are part of
    # this caller path. No old timing is subtracted for diagnosis.
    result = {'value': copy.deepcopy(value), 'ledger': copy.deepcopy(ledger),
              'return_codec': image.artifact_encode(ledger).decode('utf8'),
              'finalization_started_ns': start}
    return result


def publish_root(root, holder):
    returned = finish_root(root)
    holder.append(returned)
    # This timestamp is after the synchronous function return and ledger append.
    outside = time.perf_counter_ns()
    returned['outside_return_ns'] = outside
    returned['warm_caller_elapsed_ns'] = outside - root.started_ns
    returned['closed'] = root.state in ('closed_native_default_first_hop',
        'closed_delivered_terminal_failure', 'closed_updated_and_requested_first_hop',
        'closed_updated_but_other_first_hop')
    returned['within_100ms_observed'] = returned['closed'] and outside <= root.deadline_ns
    returned['complete_100ms_certificate'] = False
    return returned


def continuation_result(policies, status):
    return {'status': status, 'route_choices': policies['B'].choices if policies else [],
            'returns': policies['A'].returns if policies else [],
            'supply_lineage': policies['B'].supplies if policies else [],
            'recovery_decisions': policies['B'].recovery if policies else []}


def full_outcome(data, result, client, continuation, choice):
    spec = {'initial_action': choice or 'native_default', 'empty_departure': .11,
            'return_delay': 0., 'later_action': 'native_default'}
    # This reuses the complete five-job, 3-tray, two-reuse, ACK, route, FIFO/
    # finite-capacity assessor. A source/readiness failure is retained unknown.
    return public.matrix_runner.assess_cell(data, result, client, continuation, spec)


def run_continuation(session, client, policies, root, root_records, batches):
    """Same notification/tick/collection scheduler; add explicit root drains."""
    cursors = {o: 0 for o in ('A', 'B')}
    tick = 0
    activations, status = 0, 'finished'
    while session.physical_time < contract.HORIZON and activations < public.MAX_ACTIVATIONS:
        deadline = min(contract.HORIZON, public.v1.START + tick * public.v1.PERIOD,
                       *(max(p.pending['deadline'], p.peer_quiet_until)
                         for p in policies.values() if p.pending))
        require(deadline >= session.physical_time, 'missed_public_deadline')
        response = session.advance_until_owner_notification(['A', 'B'], cursors, deadline, max_events=100000)
        batches.append({'deadline': deadline, 'response': copy.deepcopy(response)})
        if not request.native_boundary_complete(response, session.physical_time):
            status = 'unknown_native_boundary'
            break
        now = session.physical_time
        due_tick = now == public.v1.START + tick * public.v1.PERIOD
        if due_tick:
            tick += 1
        notices = response.get('notifications', {})
        due = {o for o in policies if due_tick or o in notices or
               policies[o].pending and now >= policies[o].pending['deadline']}
        for owner, notice in notices.items():
            cursors[owner] = notice['sequence']
        for owner in sorted(due):
            policies[owner].activate({'native_notification': copy.deepcopy(notices.get(owner)),
                'periodic_tick': due_tick, 'collection_deadline': bool(
                    policies[owner].pending and now >= policies[owner].pending['deadline'])})
            activations += 1
        if not policies:
            # Missing accepted initial ledgers cannot be silently repaired from
            # future private truth. Still retain real retries and all input.
            for owner in ('A', 'B'):
                client.activate(owner, {'kind': 'missing_initial_input_refresh', 'at': now})
                client.refresh_owner(owner)
                activations += 1
        if root.state == 'pending_first_hop_and_ack':
            root.observe_after_boundary(response)
            verdict = root.drain_and_finish_if_closed()
            if verdict['closed']:
                publish_root(root, root_records)
    if activations >= public.MAX_ACTIVATIONS:
        status = 'unknown_activation_budget'
    if status == 'finished':
        final = session.advance_to(contract.HORIZON, max_events=100000)
        batches.append({'deadline': contract.HORIZON, 'response': copy.deepcopy(final), 'kind': 'final_drain'})
        if not request.native_boundary_complete(final, session.physical_time):
            status = 'unknown_final_drain'
    if status == 'finished':
        for owner in ('A', 'B'):
            client.activate(owner, {'kind': 'final_outbox_collection', 'at': session.physical_time})
            client.refresh_owner(owner, retry=False)
    if not root_records:
        # Unknown initial/prediction roots persist until the explicit censor;
        # no successful closure is manufactured from the physical result.
        if status == 'finished' and root.state == 'pending_first_hop_and_ack':
            root.drain_and_finish_if_closed()
        publish_root(root, root_records)
    return batches, activations, status


def run_branch(native, accepted_run, key, row, plan, predictor):
    require(accepted_run.active_for(key) and accepted_run.branch_specification(key) == row,
            'inactive_or_changed_branch')
    started = time.perf_counter_ns()
    data = scene(row)
    session = native.NativeSession(data)
    admission, accepted = request.adapter.bind_native027(native, session, plan['native_contract_reference'],
        accepted_run=accepted_run, branch_key=key)
    require(accepted is not None, 'native_acceptance_rejected:' + str(admission))
    setup_boundary = session.advance_to(.05, max_events=100000)
    require(request.native_boundary_complete(setup_boundary, .05), 'native_setup_boundary')
    client = public.LocalTransport(session)
    root = None
    roots, policies, stages, batches = [], {}, [], []
    failure = None
    b_info = None
    b_records = []
    try:
        root_type = FixedDefaultRequest if row['method'] == 'fixed_default' else CapturedRequest
        root = root_type(native, session, accepted, predictor, client, request_id=key.replace('/', ':'))
        root.B_endpoint_records = b_records
        root.collect()
        stages.append({'stage': 'A_collection', 'at': session.physical_time})
        if root.state == 'collected':
            root.choose()
            if root.state == 'selected':
                root.final_revalidate_and_submit()
        # This is unconditionally before the next native advance. It is a B
        # owner-local fixed policy, never a projection selected by A for B.
        if session.physical_time == .11:
            b_info, b_ledger = call_with_recorded_collection(request.fixed_B_first_action, b_records,
                session, client, root.planning['B'], native=native, accepted=accepted)
            stages.append({'stage': 'fixed_B_first_action', 'at': session.physical_time,
                           'request_id': b_info['request_id']})
            if root.ledger is not None and b_ledger is not None:
                ledgers = {'A': root.ledger, 'B': b_ledger}
                policies = {o: request.FixedContinuationOwner(native, session, client, o,
                    ledgers[o], root.channels[o], 'predeclared_fixed', accepted,
                    b_info['request_id'] if o == 'B' else None) for o in ('A', 'B')}
                stages.append({'stage': 'both_fixed_continuation_owners', 'owners': list(policies), 'at': .11})
        batches, activations, status = run_continuation(session, client, policies, root, roots, batches)
    except Exception:
        failure = traceback.format_exc()
        activations, status = None, 'unknown_exception'
        if root is not None and not roots:
            try:
                root._record('exception', {'traceback': failure})
                publish_root(root, roots)
            except Exception:
                failure += '\nroot_evidence_failure:\n' + traceback.format_exc()
    capture_started = time.perf_counter_ns()
    result, seal, offline = None, None, None
    capture_physical_before = session.physical_time
    try:
        # result_at is an advancing API. Never use it to diagnose an exception,
        # partial timestamp or budget failure. Preserve that exact cut instead.
        if failure is None and status == 'finished' and session.physical_time == contract.HORIZON:
            result = session.result_at(contract.HORIZON)
        else:
            offline = session.offline_diagnostics()
        seal = session.offline_state_sha256()
    except Exception:
        failure = (failure or '') + '\nresult_or_seal_failure:\n' + traceback.format_exc()
    continuation = continuation_result(policies, status)
    try:
        outcome = full_outcome(data, result, client, continuation, root.choice if root else None)
    except Exception:
        outcome = {'status': 'unknown_assessor_failure', 'exception': traceback.format_exc()}
    return {'schema': SCHEMA, 'key': key, 'specification': copy.deepcopy(row), 'input': data,
        'native027_acceptance': accepted.audit_copy(), 'setup_boundary': setup_boundary,
        'root_records': roots, 'root_constructed': root is not None, 'failure': failure,
        'initial_B': b_info, 'initial_endpoint_records': {
            'A': root.initial_endpoint_records if root is not None else [], 'B': b_records},
        'participation_stages': stages, 'native_batches': batches,
        'owner_activation_count': activations, 'calls': client.calls, 'outbox': client.rows,
        'request_creations': client.creations, 'owner_activation_admissions': client.roots,
        'ack_handling': client.ack_handling, 'continuation': continuation,
        'decisions': {o: p.decisions for o, p in policies.items()},
        'exchanges': {o: p.exchanges for o, p in policies.items()},
        'quiet_intervals': {o: p.quiet_periods for o, p in policies.items()},
        'result': result, 'offline_partial_diagnostics': offline,
        'diagnostic_physical_time_before': capture_physical_before,
        'diagnostic_physical_time_after': session.physical_time,
        'native_state_sha256': seal, 'outcome': outcome,
        'clocks': {'branch_setup_started_ns': started, 'root_started_ns': root.started_ns if root else None,
                   'result_capture_started_ns': capture_started, 'result_capture_finished_ns': time.perf_counter_ns()},
        'scope': {'root': 'actual initial owner A first hop, not complete future route maintenance',
                  'trace': 'All LocalTransport submissions/retries and explicit boundaries/root endpoints; not every internal native query',
                  'default_control': row['method'] == 'fixed_default', 'native_result_used_for_policy': False,
                  'full32_search': False, 'native_protection_certificate': False}}


def verify_plan(output, expected):
    output = Path(output).resolve()
    require(sha(output / 'campaign.json') == expected, 'campaign_hash')
    plan = read(output / 'campaign.json')
    require(plan['schema'] == SCHEMA and plan['rows'] == declarations() and
            plan['row_order'] == list(declarations()) and plan['hard_timeout_seconds'] == LIMIT,
            'campaign_domain')
    for path, digest in plan['source_sha256'].items():
        require(sha(path) == digest and sha(output / plan['source_archive'][path]) == digest, 'source_changed:' + path)
    for key, digest in plan['input_file_sha256'].items():
        path = output / 'inputs' / (key + '.json')
        require(sha(path) == digest and ordered(read(path)) == ordered(scene(plan['rows'][key])), 'input_changed:' + key)
    for name in ('native_contract_reference', 'semantic_gate_reference', 'source_preparation', 'pure_reference','startup_reference'):
        ref = plan[name]
        require(sha(ref['path']) == ref['sha256'], 'reference_changed:' + name)
    image.verify_image(plan['image']['path'], plan['image']['version'])
    native_contract = read(plan['native_contract_reference']['path'])
    require(sha(native_contract['binary']) == native_contract['binary_sha256'], 'native_binary')
    require(all(sha(path) == digest for path,digest in plan['compiled_source_archive_sha256'].items()),
            'compiled_archive_changed')
    return plan


def check_loaded_sources(plan):
    # Static closure can include modules not yet loaded; every actually loaded
    # project module must be a pinned member. A new dynamic helper invalidates.
    actual = [str(p) for p in public.imported_sources()]
    require(all(p in plan['source_sha256'] and sha(p) == plan['source_sha256'][p] for p in actual),
            'unlisted_or_changed_runtime_import')
    return actual


def worker(output, expected):
    """One native process; predictor child remains pure and owns no session."""
    started = time.perf_counter_ns()
    output = Path(output).resolve()
    with (output / 'worker_claim.json').open('x', encoding='utf8') as stream:
        json.dump({'campaign_sha256': expected, 'started_ns': started}, stream)
    plan = verify_plan(output, expected)
    loaded_entry = check_loaded_sources(plan)
    campaign_ref = reference(output / 'campaign.json')
    rows = {key: {**row, 'status': 'unknown_unexecuted'} for key, row in plan['rows'].items()}
    write(output / 'branch_ledger.json', rows)
    accepted_run = public.run_admission.open_run(plan['native_contract_reference'],
        plan['semantic_gate_reference'], campaign_ref)
    predictor = None
    predictor_evidence = {}
    try:
        native = public.load_native(read(plan['native_contract_reference']['path'])['binary'])
        with (output / 'predictor.stderr.log').open('x', encoding='utf8') as stderr:
            predictor = InitialOwnerClient(plan['image']['path'], plan['image']['version'], 'initial_A_two',
                timeout=LIMIT, stderr=stderr)
            require({k:predictor.ready[k] for k in plan['expected_READY']} == plan['expected_READY'],
                    'actual_READY_proof_or_loaded_closure_changed')
            predictor_evidence.update(command=predictor.command, started_ns=predictor.started_ns,
                ready_ns=predictor.ready_ns, ready=copy.deepcopy(predictor.ready))
            for key in plan['row_order']:
                rows[key]['status'] = 'unknown_in_progress'
                write(output / 'branch_ledger.json', rows)
                try:
                    accepted_run.enter_branch(key, campaign_ref)
                    raw = run_branch(native, accepted_run, key, plan['rows'][key], plan, predictor)
                    accepted_run.finish_branch(key)
                    path = output / 'raw' / (key + '.json.gz')
                    path.parent.mkdir(parents=True, exist_ok=True)
                    export_start = time.perf_counter_ns()
                    with gzip.open(path, 'wt', encoding='utf8', compresslevel=1) as stream:
                        json.dump(raw, stream, ensure_ascii=False, allow_nan=False)
                    rows[key].update(status='raw_saved', raw=reference(path),
                        export_started_ns=export_start, export_finished_ns=time.perf_counter_ns())
                except Exception:
                    rows[key].update(status='unknown_failed', exception=traceback.format_exc())
                    if accepted_run.active_for(key):
                        try:
                            accepted_run.finish_branch(key)
                        except Exception:
                            rows[key]['acceptance_exit_error'] = traceback.format_exc()
                write(output / 'branch_ledger.json', rows)
            predictor_evidence['close'] = predictor.close()
            predictor_evidence['cleanup_finished_ns'] = time.perf_counter_ns()
            predictor_evidence['ledger'] = copy.deepcopy(predictor.ledger)
    finally:
        if predictor is not None and not predictor.closed:
            try:
                predictor.abort()
            finally:
                predictor_evidence['abort_cleanup_finished_ns'] = time.perf_counter_ns()
        write(output / 'predictor_lifetime.json', predictor_evidence)
        acceptance = accepted_run.close() if not accepted_run._closed else accepted_run.audit_copy()
        write(output / 'run_acceptance.json', acceptance)
    # This import is included in the predeclared AST closure, not an unpinned
    # dynamically supplied extension. Verification remains inside the same Job.
    from . import verify_initial_owner_route_campaign as verifier
    report = verifier.verify_saved(output, expected)
    write(output / 'verification.json', report)
    verify_plan(output, expected)
    loaded_exit = check_loaded_sources(plan)
    write(output / 'receipt.json', {'schema': SCHEMA, 'status': 'completed_finite_request_cohort',
        'campaign_sha256': expected, 'source_changed': [], 'branches': len(rows),
        'verification': reference(output / 'verification.json'),
        'loaded_project_sources_entry': loaded_entry, 'loaded_project_sources_exit': loaded_exit,
        'worker_started_after_import_ns': started, 'before_final_receipt_export_ns': time.perf_counter_ns(),
        'timing': 'External launch-to-exit includes imports, startup, all roots/background, shutdown, acceptance and saved verification. No cold amortization or full32/100ms certificate.'})


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--campaign-sha256', required=True)
    p.add_argument('--admission', required=True)
    a = p.parse_args()
    require(a.admission == a.campaign_sha256 and sys.stdin.readline() == a.admission + '\n', 'owned_job_admission')
    worker(a.output, a.campaign_sha256)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
