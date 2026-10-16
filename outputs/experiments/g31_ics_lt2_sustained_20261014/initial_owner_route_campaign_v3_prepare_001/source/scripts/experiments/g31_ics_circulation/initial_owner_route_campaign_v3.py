"""Versioned repair of the live-builtin/strict-JSON boundary and failures.

Old 124 sources, failed campaign002 and frozen v2 preparation remain unchanged. Original scheduling,
native authority, fixed participant policy, request and worker image are reused
in private namespaces. No JSON value is promoted to a native capability.
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
from . import initial_owner_route_campaign as base
from . import initial_owner_route_json_v3 as normalization
from . import initial_owner_route_request as request
from . import initial_owner_route_contract as contract
from . import initial_owner_route_image as image
from .initial_owner_route_client import InitialOwnerClient

public, ROOT, OUT = base.public, base.ROOT, base.OUT
SCHEMA = 'g31.initial_owner_route_campaign.v3'
LIMIT, ARMS, FAULTS = base.LIMIT, base.ARMS, base.FAULTS


def private(function, replacements=None):
    result = FunctionType(function.__code__, {**function.__globals__, **(replacements or {})},
        function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


# Same function bytecode, new mutually bound module namespace. No mutation of
# imported module dictionaries/classes or any existing live controller source.
for _name in ('require','sha','read','ordered','reference','write','declarations','scene',
              'continuation_result','full_outcome','run_continuation','verify_plan','check_loaded_sources',
              'finish_root','publish_root'):
    _old = getattr(base, _name)
    globals()[_name] = FunctionType(_old.__code__, globals(), _old.__name__, _old.__defaults__, _old.__closure__)


def captured_collection(records, *args, **kwargs):
    native, session, owner, identity = args
    information, ledger = request.adapter.collect_initial_ledger(*args, **kwargs)
    endpoints = {'owner': owner, 'request_id': identity, 'at': session.physical_time,
        'view': session.observe_protocol(owner), 'command': session.protocol_command(owner, identity),
        'received': session.protocol_planning_snapshots(owner)}
    # Normalization follows the real collector. Never touch ledger or accepted
    # handle: those remain actual session-bound objects, not JSON reconstructions.
    record = {'information': copy.deepcopy(information), 'endpoints': endpoints,
              'ledger': ledger.audit_copy() if ledger is not None else None}
    records.append(record)  # Retain the captured data even if normalization rejects.
    normalized = normalization.normalize(information)
    record.update(information=copy.deepcopy(normalized), endpoints=normalization.normalize(endpoints))
    return normalized, ledger


def call_with_recorded_collection(function, records, *args, **kwargs):
    facade = SimpleNamespace(**vars(request.adapter))
    facade.collect_initial_ledger = lambda *a, **k: captured_collection(records, *a, **k)
    return private(function, {'adapter': facade})(*args, **kwargs)


class CapturedRequest(base.CapturedRequest):
    def collect(self):
        return call_with_recorded_collection(request.InitialOwnerRequest.collect,
            self.initial_endpoint_records, self)

    def final_revalidate_and_submit(self):
        return call_with_recorded_collection(request.InitialOwnerRequest.final_revalidate_and_submit,
            self.initial_endpoint_records, self)

    def choose(self):
        attempt = {'sequence_before': self.predictor.sequence, 'started_ns': time.perf_counter_ns(),
                   'closed_before': self.predictor.closed}
        try:
            return request.InitialOwnerRequest.choose(self)
        except Exception:
            attempt['error'] = traceback.format_exc()
            raise
        finally:
            attempt.update(finished_ns=time.perf_counter_ns(), closed_after=self.predictor.closed,
                           sequence_after=self.predictor.sequence)
            self._record('RPC_attempt', attempt)

    def evidence(self):
        # _record contains real native view tuples; preserve exact JSON values
        # at this evidence boundary without relaxing the old strict wire parser.
        codec = SimpleNamespace(**vars(request.codec))
        codec.artifact_encode = normalization.artifact_encode
        result = private(request.InitialOwnerRequest.evidence, {'codec': codec})(self)
        result['evidence'] = normalization.normalize(result['evidence'])
        result['evidence']['initial_endpoint_records'] = normalization.normalize({
            'A': self.initial_endpoint_records, 'B': self.B_endpoint_records})
        result['evidence']['scope'] = ('Actual finite initial-A first-hop evidence; future fixed continuation '
            'and full-H outcome are separate. No full32, protection or universal100ms certificate.')
        result['encoded'] = image.artifact_encode(result['evidence'])
        result['body_finished_ns'] = time.perf_counter_ns()
        result['body_elapsed_ns'] = result['body_finished_ns'] - self.started_ns
        return result


class FixedDefaultRequest(CapturedRequest):
    choose = base.FixedDefaultRequest.choose


def failed_root_evidence(root, *, key, attempt_started, error, endpoint_records):
    """Always retain an admitted failure clock; never manufacture a closed root."""
    started = getattr(root, 'started_ns', attempt_started)
    value = {'status': 'unknown_root_failure', 'root_id': key.replace('/', ':'),
        'attempt_started_ns': attempt_started, 'root_started_ns': started,
        'error': error, 'closed': False, 'complete_100ms_certified': False}
    snapshot = {'events': getattr(root, 'events', []), 'information': getattr(root, 'information', None),
        'reply': getattr(root, 'reply', None), 'initial_endpoint_records': endpoint_records}
    try:
        value['typed_builtin_snapshot'] = normalization.typed_failure_snapshot(snapshot)
    except Exception:
        value['snapshot_failure'] = traceback.format_exc()
    encoded = image.artifact_encode(value)
    value['encoded_sha256'] = hashlib.sha256(encoded).hexdigest()
    value['encoded_bytes'] = len(encoded)
    value['outside_return_ns'] = time.perf_counter_ns()
    value['elapsed_ns'] = value['outside_return_ns'] - started
    return value


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
    b_info, b_records = None, []
    failed_admission = None
    constructed = False
    attempt_started = time.perf_counter_ns()
    try:
        root_type = FixedDefaultRequest if row['method'] == 'fixed_default' else CapturedRequest
        # Keep the partially initialized object solely for failure evidence.
        # Only a successfully returned constructor grants live request authority.
        root = root_type.__new__(root_type)
        root_type.__init__(root, native, session, accepted, predictor, client, request_id=key.replace('/', ':'))
        constructed = True
        root.B_endpoint_records = b_records
        root.collect()
        stages.append({'stage': 'A_collection', 'at': session.physical_time})
        if root.state == 'collected':
            root.choose()
            if root.state == 'selected':
                root.final_revalidate_and_submit()
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
        if constructed and not roots:
            try:
                root._record('exception', {'traceback': failure})
                publish_root(root, roots)
            except Exception:
                failure += '\nroot_evidence_failure:\n' + traceback.format_exc()
        if not roots:
            failed_admission = failed_root_evidence(root, key=key, attempt_started=attempt_started,
                error=failure, endpoint_records={'A':getattr(root,'initial_endpoint_records',[]),'B':b_records})
    capture_started = time.perf_counter_ns()
    result, seal, offline = None, None, None
    capture_physical_before = session.physical_time
    try:
        if failure is None and status == 'finished' and session.physical_time == contract.HORIZON:
            result = session.result_at(contract.HORIZON)
        else:
            offline = session.offline_diagnostics()
        seal = session.offline_state_sha256()
    except Exception:
        failure = (failure or '') + '\nresult_or_seal_failure:\n' + traceback.format_exc()
    continuation = continuation_result(policies, status)
    try:
        outcome = full_outcome(data, result, client, continuation, getattr(root,'choice',None))
    except Exception:
        outcome = {'status': 'unknown_assessor_failure', 'exception': traceback.format_exc()}
    return {'schema': SCHEMA, 'key': key, 'specification': copy.deepcopy(row), 'input': data,
        'native027_acceptance': accepted.audit_copy(), 'setup_boundary': setup_boundary,
        'root_records': roots, 'root_constructed': constructed, 'failure': failure,
        'failed_root_admission': failed_admission,
        'initial_B': b_info, 'initial_endpoint_records': {
            'A': getattr(root,'initial_endpoint_records',[]), 'B': b_records},
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
        'clocks': {'branch_setup_started_ns': started, 'root_attempt_started_ns':attempt_started,
                   'root_started_ns': getattr(root,'started_ns',None),
                   'result_capture_started_ns': capture_started, 'result_capture_finished_ns': time.perf_counter_ns()},
        'scope': {'root': 'actual initial owner A first hop, not complete future route maintenance',
                  'trace': 'All LocalTransport submissions/retries and explicit boundaries/root endpoints; not every internal native query',
                  'default_control': row['method'] == 'fixed_default', 'native_result_used_for_policy': False,
                  'full32_search': False, 'native_protection_certificate': False}}


def close_predictor(predictor):
    evidence = {'close_attempt_started_ns': time.perf_counter_ns(), 'closed_before_close': predictor.closed}
    try:
        if predictor.closed:
            evidence['status'] = 'unknown_already_aborted'
        else:
            evidence['close'] = predictor.close()
            evidence['status'] = 'closed_protocol'
    except Exception:
        evidence.update(status='unknown_close_failure', error=traceback.format_exc())
    finally:
        try:
            if not predictor.closed:
                predictor.abort()
        except Exception:
            evidence['abort_error'] = traceback.format_exc()
            evidence['status'] = 'unknown_cleanup_failure'
        evidence['ledger'] = copy.deepcopy(predictor.ledger)
        evidence['process_exit_code'] = predictor.process.poll() if predictor.process is not None else None
        evidence['cleanup_finished_ns'] = time.perf_counter_ns()
    return evidence


def worker(output, expected):
    started = time.perf_counter_ns()
    output = Path(output).resolve()
    with (output/'worker_claim.json').open('x',encoding='utf8') as stream:
        json.dump({'campaign_sha256':expected,'started_ns':started},stream)
    plan = verify_plan(output,expected)
    loaded_entry = check_loaded_sources(plan)
    campaign_ref = reference(output/'campaign.json')
    rows = {key:{**row,'status':'unknown_unexecuted'} for key,row in plan['rows'].items()}
    write(output/'branch_ledger.json',rows)
    accepted_run = public.run_admission.open_run(plan['native_contract_reference'],plan['semantic_gate_reference'],campaign_ref)
    predictor, life = None, {'worker_setup_started_ns': started}
    try:
        native = public.load_native(read(plan['native_contract_reference']['path'])['binary'])
        with (output/'predictor.stderr.log').open('x',encoding='utf8') as stderr:
            life['construction_attempt_started_ns'] = time.perf_counter_ns()
            predictor = InitialOwnerClient(plan['image']['path'],plan['image']['version'],'initial_A_two',timeout=LIMIT,stderr=stderr)
            require({k:predictor.ready[k] for k in plan['expected_READY']}==plan['expected_READY'],'actual_READY_changed')
            life.update(command=predictor.command,started_ns=predictor.started_ns,ready_ns=predictor.ready_ns,
                        ready=copy.deepcopy(predictor.ready))
            for key in plan['row_order']:
                rows[key].update(status='unknown_in_progress',attempt_started_ns=time.perf_counter_ns())
                write(output/'branch_ledger.json',rows)
                try:
                    accepted_run.enter_branch(key,campaign_ref)
                    raw = run_branch(native,accepted_run,key,plan['rows'][key],plan,predictor)
                    accepted_run.finish_branch(key)
                    path = output/'raw'/(key+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True)
                    export_start = time.perf_counter_ns()
                    with gzip.open(path,'wt',encoding='utf8',compresslevel=1) as stream:
                        json.dump(raw,stream,ensure_ascii=False,allow_nan=False)
                    rows[key].update(status='raw_saved',raw=reference(path),export_started_ns=export_start,
                                     export_finished_ns=time.perf_counter_ns())
                except Exception:
                    rows[key].update(status='unknown_failed',exception=traceback.format_exc())
                    if accepted_run.active_for(key):
                        try: accepted_run.finish_branch(key)
                        except Exception: rows[key]['acceptance_exit_error']=traceback.format_exc()
                rows[key]['attempt_finished_ns']=time.perf_counter_ns()
                write(output/'branch_ledger.json',rows)
    except Exception:
        life['worker_setup_or_loop_failure']=traceback.format_exc()
    finally:
        if predictor is not None:
            life.update(close_predictor(predictor))
        else:
            life.update(status='unknown_predictor_construction',ledger=[],cleanup_finished_ns=time.perf_counter_ns())
        write(output/'predictor_lifetime.json',life)
        acceptance = accepted_run.close() if not accepted_run._closed else accepted_run.audit_copy()
        write(output/'run_acceptance.json',acceptance)
    from . import verify_initial_owner_route_campaign_v3 as verifier
    report = verifier.verify_saved(output,expected)
    write(output/'verification.json',report)
    verify_plan(output,expected)
    loaded_exit=check_loaded_sources(plan)
    write(output/'receipt.json',{'schema':SCHEMA,'status':'completed_finite_request_cohort',
        'campaign_sha256':expected,'source_changed':[],'branches':len(rows),
        'verification':reference(output/'verification.json'),'loaded_project_sources_entry':loaded_entry,
        'loaded_project_sources_exit':loaded_exit,'worker_started_after_import_ns':started,
        'before_final_receipt_export_ns':time.perf_counter_ns(),
        'timing':'All retained failures and cleanup charged; completed means saved audit, never all roots succeeded.'})


main = FunctionType(base.main.__code__,globals(),base.main.__name__)
if __name__=='__main__': raise SystemExit(main())
