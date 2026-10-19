"""Registered native first-nine experiment with immutable evidence and hard limits."""
from __future__ import annotations

import argparse
import copy
import faulthandler
import gzip
import json
from pathlib import Path
import sys
import threading
import time
import traceback
import uuid

BOOT_MONOTONIC = time.monotonic()
BOOT_NS = time.perf_counter_ns()

if '--worker' in sys.argv:
    print('worker_before_online_import', file=sys.stderr, flush=True)

from . import bounded_windows_job
from . import research_live_obligation_initial_methods as online

MODULE = 'scripts.experiments.g31_ics_circulation.run_compatible_initial_native'
FIRST_ARMS = ('incumbent', 'coordinate_strict', 'finite_MPC')
CELL_SECONDS = 60.
GROUP_SECONDS = 600.
REMAINING_GROUP_SECONDS = 780.
ROOT = Path(__file__).resolve().parents[3]


def first9_order():
    first = [case + '/' + arm for case in online.CASES for arm in FIRST_ARMS]
    isolation = 'no_overlap/incumbent'
    return [isolation] + [key for key in first if key != isolation]


def remaining12_order():
    return [case + '/' + arm for case in online.CASES for arm in online.ARMS if arm not in FIRST_ARMS]


def prior_first9_evidence(previous, audit_path):
    previous = previous.resolve()
    audit_path = audit_path.resolve()
    audit = online.old.read(audit_path)
    required = ('all9_execution_closed', 'all9_observed_componentwise_protected',
        'all9_structural_witness_verified', 'all18_request_bindings_closed_complete65',
        'all18_effective_predictions_exact_native_endpoints', 'all_native_execution_lineages_verified')
    online.require(all(audit.get(field) is True for field in required), 'prior_first9_audit_incomplete')
    online.require(Path(audit['campaign']).resolve() == previous, 'prior_audit_campaign')
    plan_path = previous / 'preregistered_protocol.json'
    plan = online.old.read(plan_path)
    online.require(online.old.sha(plan_path) == online.old.read(previous / 'prepare_receipt.json')['plan_sha256'],
        'prior_plan_changed')
    online.require(set(plan['branch_order']) == set(first9_order()), 'prior_first9_domain')
    matrix = online.old.read(previous / 'execution_matrix.json')
    files = [audit_path, plan_path, previous / 'prepare_receipt.json', previous / 'receipt.json',
        previous / 'execution_matrix.json']
    endpoints = {}
    for key in first9_order():
        cell = matrix[key]
        online.require(cell['status'] == 'assessed' and cell['run_acceptance_status'] == 'closed_run_acceptance_passed',
            'prior_cell_not_closed:' + key)
        raw_path = previous / (key + '.raw.json.gz')
        digest = online.old.sha(raw_path)
        online.require(digest == cell['raw_artifact']['sha256'] == audit['source']['raw_sha256'][str(raw_path)],
            'prior_raw_changed:' + key)
        raw = json.loads(gzip.decompress(raw_path.read_bytes()))
        endpoints[key] = {job['business_bag_id']: job['completed_at'] for job in raw['result']['jobs']}
        online.require(endpoints[key] == cell['summary']['completion'] == audit['rows'][key]['actual_completion'],
            'prior_endpoint_audit_mismatch:' + key)
        files.extend([raw_path, previous / (key + '.cell.json'), previous / (key + '.acceptance.json'),
            previous / (key + '.process.json')])
    for key, completion in endpoints.items():
        baseline = endpoints[key.split('/')[0] + '/incumbent']
        online.require(set(completion) == set(baseline) and len(completion) == 5
            and all(type(value) in (float, int) and value <= baseline[job] for job, value in completion.items()),
            'prior_actual_componentwise_harm:' + key)
    current_sources = set(map(str, online.old.bound.imported_sources()))
    online.require(current_sources == set(plan['source_sha256']), 'prior_project_source_domain_changed')
    runner = Path(__file__).resolve()
    for source, digest in plan['source_sha256'].items():
        online.require(online.old.sha(previous / plan['source_archive'][source]) == digest, 'prior_archive_changed')
        if Path(source).resolve() != runner:
            online.require(online.old.sha(source) == digest, 'core_source_changed_after_first9:' + source)
    return {'campaign_reference': online.old.reference(plan_path), 'audit_reference': online.old.reference(audit_path),
        'source_change_allowlist': [str(runner)], 'core_source_bytes_unchanged': True,
        'evidence_sha256': {str(path): online.old.sha(path) for path in files}}


def check_prior_evidence(plan):
    for path, digest in plan.get('prior_first9', {}).get('evidence_sha256', {}).items():
        online.require(online.old.sha(path) == digest, 'prior_evidence_changed:' + path)


def dump_due_traceback(now, next_at, stream):
    if now < next_at:
        return next_at
    print('Python_observer_synchronous_traceback', file=stream, flush=True)
    faulthandler.dump_traceback(file=stream, all_threads=True)
    return now + 20.


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf8')


def prepare(output, remaining_after=None, prior_audit=None):
    online.require(not output.exists(), 'immutable_campaign_output')
    online.require((remaining_after is None) == (prior_audit is None), 'prior_campaign_and_audit_required_together')
    prior = prior_first9_evidence(remaining_after, prior_audit) if remaining_after is not None else None
    output.mkdir(parents=True)
    contract_path = online.old.OUT / 'native027_accepted_contract_001.json'
    semantic_path = online.old.OUT / 'native027_semantic_native_002/receipt.json'
    contract = online.old.read(contract_path)
    rows = online.rows()
    first = first9_order() if prior is None else remaining12_order()
    sources = online.old.bound.imported_sources()
    plan = {'schema': 'g31.compatible_initial_native_first9.v1', 'rows': rows,
        'phase': 'first9' if prior is None else 'remaining12',
        'branch_order': first, 'native_branch_budget': len(first), 'registered_domain_count': 21,
        'order_change': 'no_overlap/incumbent first as isolation for the previous access violation; remaining eight retain original relative order.',
        'diagnostic_change': 'Only replace asynchronous C traceback watchdog with synchronous Python-observer traceback calls; model, native authority, partial snapshots and hard limits unchanged.',
        'diagnostic_limit': 'Python observer needs the GIL; no diagnostic progress during a GIL-holding native stall. External Windows JobObject still enforces the hard deadline.',
        'hard_cell_seconds': CELL_SECONDS,
        'hard_group_seconds': GROUP_SECONDS if prior is None else REMAINING_GROUP_SECONDS,
        'horizon': 40., 'incumbent_index': 4, 'strict_protection_tolerance': 0.,
        'max_candidate_predictions_per_owner': 32, 'system_candidate_predictions_per_cell': 64,
        'complete_request_target_ms': 100, 'message_tape': 'normal',
        'component_contract': online.dispatch.compatibility.CONTRACT,
        'native_contract_reference': online.old.reference(contract_path),
        'semantic_gate_reference': online.old.reference(semantic_path),
        'binary': online.old.reference(contract['binary']),
        'source_sha256': {}, 'source_archive': {}, 'input_file_sha256': {},
        'T2_registered_bands': {'normal': {'variants': ['incumbent', 'finite_MPC'], 'status': 'covered_by_T4_normal_cells'},
            'one_ACK_delayed': {'variants': ['incumbent', 'finite_MPC'], 'status': 'unexecuted_native_has_only_global_ACK_delay'},
            'partial_commit_then_refusal': {'variants': ['incumbent', 'finite_MPC'], 'status': 'unexecuted_no_injected_refusal_authority'}},
        'T2_budget': {'horizon': 40., 'cell_seconds': 60., 'maximum_cells': 12, 'maximum_total_seconds': 720.},
        'limitation': 'A stays incumbent; R1 joint changes and vector25 remain outside this conservative contract. No hard reservation is added.'}
    if prior is not None:
        plan['prior_first9'] = prior
        plan['order_change'] = 'Remaining four registered arms in original case/method order; prior nine are referenced, never re-executed or copied into this campaign.'
        plan['diagnostic_change'] = 'No controller/model/native diagnostic changes after the first-nine campaign; only explicit remaining-subset registration and evidence checks.'
    for source in sources:
        archive = output / 'source' / source.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(source.read_bytes())
        plan['source_sha256'][str(source)] = online.old.sha(source)
        plan['source_archive'][str(source)] = str(archive.relative_to(output))
    for key, row in rows.items():
        path = output / 'inputs' / (key + '.json')
        write(path, online.old.native_scene(row['case']))
        plan['input_file_sha256'][key] = online.old.sha(path)
    write(output / 'preregistered_protocol.json', plan)
    write(output / 'prepare_receipt.json', {'status': 'prepared_unexecuted',
        'plan_sha256': online.old.sha(output / 'preregistered_protocol.json'), 'native_executions': 0})
    write(output / 'execution_matrix.json', rows)
    return {'status': 'prepared_unexecuted', 'output': str(output), 'phase': plan['phase'], 'branch_order': first}


def worker(output, key):
    started = time.perf_counter_ns()
    plan = online.old.read(output / 'preregistered_protocol.json')
    check_prior_evidence(plan)
    online.require(online.old.sha(output / 'preregistered_protocol.json') ==
        online.old.read(output / 'prepare_receipt.json')['plan_sha256'], 'immutable_plan')
    online.require(key in plan['branch_order'], 'registered_first9_cell')
    campaign = online.old.reference(output / 'preregistered_protocol.json')
    accepted = None
    record = {'status': 'unknown_admission_not_completed', 'native_session_attempted': False,
        'root_started_ns': started, 'key': key}
    raw_path = output / (key + '.raw.json.gz')
    journal_path = output / (key + '.journal.jsonl')
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    progress = {}
    stopped = threading.Event()

    def phase(name):
        with journal_path.open('a', encoding='utf8') as stream:
            stream.write(json.dumps({'phase': name, 'at_ns': time.perf_counter_ns()}) + '\n')
            stream.flush()

    def save_progress():
        next_traceback = time.monotonic() + 20.
        while not stopped.wait(1.):
            try:
                client = progress.get('client')
                partial = {'observed_ns': time.perf_counter_ns(), 'stage': progress.get('stage'),
                    'initial_owners': progress.get('initial_owners', {}),
                    'outbox': client.rows if client is not None else {},
                    'request_creations': client.creations if client is not None else {},
                    'physical_execution_certified': False,
                    'scope': 'Passive Python evidence snapshot; absence is not proof that a command was not issued.'}
                encoded = json.dumps(partial, allow_nan=False).encode()
                temporary = output / (key + '.partial.tmp')
                temporary.write_bytes(encoded)
                temporary.replace(output / (key + '.partial.json'))
                next_traceback = dump_due_traceback(time.monotonic(), next_traceback, sys.stderr)
            except Exception as error:
                phase('partial_snapshot_error:' + type(error).__name__)

    phase('worker_admission_token_consumed')
    observer = threading.Thread(target=save_progress, daemon=True)
    observer.start()
    try:
        phase('closed_runtime_admission_started')
        accepted = online.old.run_admission.open_run(plan['native_contract_reference'],
            plan['semantic_gate_reference'], campaign)
        phase('closed_runtime_admission_completed')
        native = online.old.bound.load_native(Path(plan['binary']['path']))
        phase('native_binary_loaded')
        accepted.enter_branch(key, campaign)
        phase('native_branch_entered')
        record['native_session_attempted'] = True
        try:
            raw = online._run_branch(native, plan['rows'][key], plan['native_contract_reference'],
                plan['semantic_gate_reference'], accepted_run=accepted, branch_key=key, progress=progress)
        except Exception:
            raw = online.old.capture_partial(progress, traceback.format_exc())
        phase('native_branch_returned')
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_bytes(gzip.compress(json.dumps(raw, allow_nan=False).encode(), compresslevel=1, mtime=0))
        record.update(status=raw['summary']['status'], summary=raw['summary'],
            raw_artifact=online.old.reference(raw_path))
        accepted.finish_branch(key)
    except Exception:
        record.update(status='unknown_failed', exception=traceback.format_exc())
    finally:
        stopped.set()
        observer.join(timeout=2.)
        phase('runtime_closure_started')
        if accepted is not None:
            closed = accepted.close()
            write(output / (key + '.acceptance.json'), closed)
            record['run_acceptance_status'] = closed['status']
            if closed['status'] != 'closed_run_acceptance_passed':
                record['status'] = 'unknown_invalidated_runtime_evidence'
        try:
            check_prior_evidence(plan)
        except Exception:
            record.update(status='unknown_invalidated_prior_evidence', prior_evidence_error=traceback.format_exc())
        record['finished_ns'] = time.perf_counter_ns()
        record['worker_observation_ms'] = (record['finished_ns'] - started) / 1e6
        record['complete_request_100ms_certified'] = False
        write(output / (key + '.cell.json'), record)
        phase('cell_record_written')


def launch(output):
    online.require(not (output / 'launch_started.json').exists(), 'campaign_already_attempted')
    plan = online.old.read(output / 'preregistered_protocol.json')
    phase = plan.get('phase', 'first9')
    group_seconds = plan.get('hard_group_seconds', GROUP_SECONDS)
    online.require(phase in ('first9', 'remaining12') and group_seconds ==
        (GROUP_SECONDS if phase == 'first9' else REMAINING_GROUP_SECONDS), 'registered_group_budget')
    started = BOOT_MONOTONIC
    write(output / 'launch_started.json', {'started_ns': time.perf_counter_ns(),
        'before_project_imports_ns': BOOT_NS,
        'hard_group_seconds': group_seconds, 'hard_cell_seconds': CELL_SECONDS})
    matrix = copy.deepcopy(plan['rows'])
    stopped_early = False
    for key in plan['branch_order']:
        remaining = group_seconds - (time.monotonic() - started)
        if remaining <= 0:
            matrix[key]['status'] = 'unknown_unexecuted_group_budget_exhausted'
            continue
        token = uuid.uuid4().hex
        command = [sys.executable, '-m', MODULE, '--worker', '--output', str(output),
            '--key', key, '--admission', token]
        directory = (output / key).parent
        directory.mkdir(parents=True, exist_ok=True)
        write(output / (key + '.started.json'), {'started_ns': time.perf_counter_ns(),
            'status': 'worker_launch_started', 'native_session_attempted': None})
        with (output / (key + '.stdout.log')).open('w') as stdout, (output / (key + '.stderr.log')).open('w') as stderr:
            process = bounded_windows_job.run(command, timeout=min(CELL_SECONDS, remaining),
                stdout=stdout, stderr=stderr, admission=token, cwd=str(ROOT))
        write(output / (key + '.process.json'), process)
        result_path = output / (key + '.cell.json')
        matrix[key].update(online.old.read(result_path) if result_path.exists() else
            {'status': 'unknown_process_' + process['status'], 'native_session_attempted': None})
        matrix[key]['process'] = process
        process_ok = process['status'] == 'exited' and process['exitcode'] == 0
        if not process_ok and matrix[key]['status'] == 'assessed':
            matrix[key]['child_assessment_status'] = matrix[key]['status']
            matrix[key]['status'] = 'unknown_process_' + process['status']
        write(output / 'execution_matrix.json', matrix)
        print(json.dumps({'key': key, 'status': matrix[key]['status']}), flush=True)
        if not process_ok or matrix[key]['status'] != 'assessed':
            stopped_early = True
            write(output / 'early_stop.json', {'status': 'stopped_on_first_unclosed_cell',
                'trigger_cell': key, 'process': process, 'remaining_cells': 'unexecuted',
                'budget_extended': False})
            break
    write(output / 'execution_matrix.json', matrix)
    attempts = sum('process' in row for row in matrix.values())
    complete = not stopped_early and all(matrix[key]['status'] == 'assessed'
        and matrix[key].get('process', {}).get('status') == 'exited'
        and matrix[key]['process']['exitcode'] == 0 for key in plan['branch_order'])
    status = ('first9_attempted_remaining12_unexecuted' if complete else 'first9_stopped_with_unknowns') if phase == 'first9' else (
        'remaining12_assessed_prior9_referenced' if complete else 'remaining12_stopped_with_unknowns')
    write(output / 'receipt.json', {'status': status, 'phase': phase,
        'actual_cell_attempts': attempts,
        'scheduled_cell_count': len(plan['branch_order']), 'all_scheduled_cells_assessed': complete,
        'registered_domain_count': 21, 'wall_seconds': time.monotonic() - started,
        'component_contract': plan['component_contract'], 'full_online21_completed': False,
        'complete_request_100ms_certified': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--key')
    parser.add_argument('--admission')
    parser.add_argument('--remaining-after', type=Path)
    parser.add_argument('--prior-audit', type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--launch', action='store_true')
    modes.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    online.require(args.prepare or args.remaining_after is None and args.prior_audit is None,
        'remaining_options_only_during_prepare')
    if args.prepare:
        print(json.dumps(prepare(output, args.remaining_after, args.prior_audit)))
    elif args.launch:
        launch(output)
    else:
        online.require(bool(args.admission) and sys.stdin.readline().strip() == args.admission,
            'bounded_worker_admission')
        worker(output, args.key)
