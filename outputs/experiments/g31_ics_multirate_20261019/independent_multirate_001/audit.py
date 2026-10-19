"""Independent saved-artifact audit of multirate_002; Python standard library only.

No project modules are imported, no model is evaluated, and no native process is
started. The older 001 run is not an input to this audit.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import traceback


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
RUN = OUT.parent / 'multirate_002'
JOBS = {'loaded', 'receiver', 'reuse1', 'reuse2', 'blocker'}
TRAYS = {'L', 'E', 'P'}
COMMUNICATION = {'demand', 'planning_snapshot', 'planning_snapshot_v3'}
LIFECYCLE = {'LOAD_START', 'LOAD_COMPLETE', 'EDGE_ENTER', 'EDGE_EXIT',
    'STORAGE_ENTER', 'STORAGE_RELEASE', 'UNLOAD_START', 'UNLOAD_COMPLETE',
    'HOLD_START', 'HOLD_COMPLETE', 'EMPTY_RECEIVED'}
ALL_KNOWN_EVENTS = LIFECYCLE | {'BAG_ARRIVAL', 'LEG_START', 'LEG_COMPLETE',
    'EXPORT_GRANTED', 'MODULE_REQUEST_DELIVERED', 'RESOURCE_WAIT', 'RESOURCE_WAKE',
    'ROUTE_INTENT_updated', 'TRANSFER_REJECTED', 'PROTOCOL_ACK_DELIVERED',
    'PROTOCOL_COMMAND_ACK_DELIVERED'}
HASHES = {}
CHECKS = []


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def sha(path):
    path = Path(path).resolve(strict=True)
    if path not in HASHES:
        HASHES[path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return HASHES[path]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def check(condition, name):
    CHECKS.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise ValueError(name)


def reference(item, name):
    check(sha(item['path']) == item['sha256'], 'reference:' + name)
    return Path(item['path'])


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def nonpublication(raw):
    result = []
    for row in raw['result']['receipts']:
        check(row['event'] in ALL_KNOWN_EVENTS, 'known_event:' + row['event'])
        if row['event'] == 'PROTOCOL_COMMAND_ACK_DELIVERED':
            request_id = row['reason'].rsplit(':', 1)[0]
            kind = raw['outbox'][request_id]['kind']
            check(kind in COMMUNICATION | {'route', 'transfer'}, 'known_ack_kind:' + kind)
            if kind in COMMUNICATION:
                continue
        result.append(row)
    return result


def audit():
    final = read(RUN / 'receipt.json')
    plan = read(reference(final['plan'], 'probe_plan'))
    worker = read(reference(final['worker_report'], 'worker_report'))
    check(final['status'] == worker['status'] == 'completed_multirate_late_refusal_probe', 'final_success_status')
    check(final['process']['status'] == 'exited' and final['process']['exitcode'] == 0
        and final['process']['windows_job_kill_on_close'] is True, 'bounded_process_exited_normally')
    check(plan['native_branches'] == 1 and plan['automatic_retries'] == 0
        and plan['realtime_async'] is False and plan['wall_to_sim_time_mapping'] is None
        and plan['new_action_admission_enabled'] is False, 'declared_single_offline_probe')
    native_receipt = read(reference(worker['native_receipt'], 'native_receipt'))
    native_plan = read(reference(native_receipt['plan'], 'native_plan'))
    raw_path = reference(worker['native_raw'], 'native_raw')
    check(reference(native_receipt['raw_artifact'], 'native_receipt_raw') == raw_path, 'same_native_raw_binding')
    raw = json.loads(gzip.decompress(raw_path.read_bytes()))
    observed = read(reference(worker['probe_observations'], 'probe_observations'))
    prediction = read(reference(worker['prediction'], 'prediction'))
    baseline_path = reference(plan['baseline']['raw.json.gz'], 'baseline_raw')
    baseline_receipt = read(reference(plan['baseline']['receipt.json'], 'baseline_receipt'))
    check(reference(baseline_receipt['raw_artifact'], 'baseline_receipt_raw') == baseline_path,
        'baseline_raw_receipt_binding')
    baseline = json.loads(gzip.decompress(baseline_path.read_bytes()))

    acceptance = read(RUN / 'native/acceptance.json')
    check(native_receipt['status'] == baseline_receipt['status'] == 'assessed'
        and native_receipt['run_acceptance_status'] == baseline_receipt['run_acceptance_status']
        == acceptance['status'] == 'closed_run_acceptance_passed', 'closed_native_and_baseline')
    check(acceptance['active'] is False and acceptance['invalid'] == []
        and acceptance['branch_keys'] == ['mechanism/incumbent'], 'native_acceptance_closed_without_invalidations')
    check(raw['native027_acceptance']['runtime_accepted'] is True
        and raw['decision_boundaries'][-1]['status'] == 'finished'
        and raw['decision_boundaries'][-1]['due_owners'] == []
        and raw['result']['physical_clock'] == 40., 'actual_terminal_native_clock')
    check(acceptance['pid'] == final['process']['pid'], 'native_process_matches_bounded_worker')
    life = worker['worker_lifecycle_timing']
    check(type(life['process_id']) is int and life['process_id'] > 0
        and life['process_id'] != acceptance['pid'], 'predictor_is_distinct_process')

    for path, expected in plan['source_pins'].items():
        check(sha(path) == expected, 'current_source_pin:' + path)
    for item in plan['runtime_references']:
        reference(item, 'runtime:' + item['path'])
    for path, expected in acceptance['evidence_sha256'].items():
        check(sha(path) == expected, 'native_evidence_pin:' + path)
    source_map = native_plan['source_archive']
    check(set(source_map) == set(native_plan['source_sha256']), 'source_archive_full_declared_mapping')
    for source, relative in source_map.items():
        saved = (RUN / 'native' / relative).resolve(strict=True)
        check(saved.is_relative_to((RUN / 'native/source').resolve()), 'source_archive_inside_native_source')
        expected = native_plan['source_sha256'][source]
        check(sha(saved) == expected == sha(source), 'archived_source_bytes:' + source)
    for name in ('foundation_multirate.py', 'foundation_multirate_probe.py', 'foundation_later_seed.py',
                 'foundation_later_control.py', 'foundation_native_environment.py'):
        check(any(Path(path).name == name for path in source_map), 'critical_source_archived:' + name)
    check(worker['source_and_reference_exit_pins_passed'] is True, 'worker_exit_source_pins')

    b = observed['B']['multirate']
    advice, evidence = b['advice'], b['input_evidence']
    report = prediction['model_report']
    check(prediction['status'] == 'completed_detached_prediction'
        and report['status'] == 'conditional_current_seed', 'completed_actual_seed_prediction')
    check(report['seed']['evidence'] == evidence and digest(evidence) == advice['evidence_sha256'],
        'prediction_input_equals_captured_evidence')
    check(digest(advice['original_reference']) == advice['reference_sha256']
        == observed['B']['initial_reference_sha256'], 'unchanged_original_reference_digest')
    check(report['evaluation']['source_exit_pins_passed'] is True
        and report['evaluation']['native_execution_authority'] is False, 'prediction_source_exit_and_no_authority')
    for path, expected in report['evaluation']['source_sha256'].items():
        check(sha(path) == expected, 'prediction_source_pin:' + path)
    results = report['candidate_results']
    check(set(results) == {'native_default', 'prefer_8'}, 'exact_two_candidate_predictions')
    for action, result in results.items():
        check(result['status'] == 'conditional_prediction' and result['action_id'] == action
            and set(result['completion']) == JOBS and all(finite(value) and value >= 0
                for value in result['completion'].values()), 'known_five_job_candidate:' + action)
        check(all(result[field] is False for field in ('online_executable', 'native_protection_certified',
            'native_execution_certified', 'native_delivery_verified')), 'candidate_no_native_authority:' + action)
        check(result['seed_sha256'] == report['seed']['seed_sha256']
            and result['current_state_at'] == advice['capture_sim_time'], 'candidate_bound_to_seed_epoch:' + action)

    start, end = prediction['worker_started_ns'], prediction['worker_compute_end_ns']
    check(type(start) is int and type(end) is int and life['worker_ready_ns'] <= life['enqueued_ns'] <= start < end,
        'ordered_actual_process_wall_times')
    check(prediction['injected_delay_wall_ms'] == 0. and prediction['simulated_delay_s'] is None
        and prediction['worker_compute_cpu_ms'] > 0., 'actual_computation_without_injected_delay')
    check(prediction['worker_compute_wall_ms'] == (end - start) / 1e6, 'worker_elapsed_recomputed')
    samples = b['samples']
    check(samples and [row['wall_ns'] for row in samples] == sorted(row['wall_ns'] for row in samples)
        and [row['sim_time'] for row in samples] == sorted(row['sim_time'] for row in samples),
        'monotone_native_poll_trace')
    overlap = [sample for sample in samples if start <= sample['wall_ns'] <= end]
    check(len(overlap) >= 2 and overlap[-1]['sim_time'] > overlap[0]['sim_time'], 'multiple_sim_advances_inside_worker_wall_interval')
    check(all(sample['worker_done'] is False for sample in overlap), 'worker_not_done_during_overlap')
    physical = [row for row in raw['result']['receipts']
        if overlap[0]['sim_time'] < row['time'] <= overlap[-1]['sim_time']
        and row['event'] in LIFECYCLE and row.get('tray_id')]
    check(bool(physical), 'actual_tray_lifecycle_during_compute')
    measured = worker['native_progress_during_worker']
    check(measured['sample_count'] == len(overlap) and measured['actual_receipts'] == physical
        and measured['actual_receipt_count'] == len(physical), 'independently_recomputed_overlap_matches_report')

    endpoints = evidence['information']['raw_endpoints']
    own = endpoints['command']['last_delivered_ack']['planning_snapshot_v3']
    peers = [row for row in endpoints['received']
        if row['capture']['capture_v2']['local_capture']['message_id'] == evidence['collection']['peer_message']]
    check(len(peers) == 1, 'unique_actual_peer_capture')
    source_at = min(item['capture']['capture_v2']['local_capture']['captured_at'] for item in (own, peers[0]))
    service_at = evidence['information']['bundle']['trays']['L']['service_ready_at']
    check(advice['source_captured_at'] == source_at and advice['source_collection_valid_through'] == source_at + .05
        and advice['use_by'] == service_at - .01 and advice['capture_sim_time'] == evidence['at'],
        'source_age_and_deadline_derived_from_captured_evidence')
    expiry = b['expiry_event']
    first_expired = next(row for row in samples if row['sim_time'] - source_at > .05)
    check(expiry['due_at'] == source_at + .05 and expiry['observed_at'] == first_expired['sim_time']
        and expiry['detection_lag_sim_s'] == expiry['observed_at'] - expiry['due_at'], 'first_observed_expiry_without_time_reset')
    delivery = b['result_delivery']
    view, screen = delivery['current_local_view'], delivery['screen']
    now = view['now']
    check(now == delivery['ready_sim_time'] == screen['checked_at_sim_time']
        and delivery['ready_observed_ns'] >= end and now >= advice['use_by'], 'real_late_current_return_time')
    check(screen['status'] == 'rejected' and screen['missed_action_deadline'] is True
        and 'action_deadline_missed' in screen['reasons']
        and 'old_collection_expired_full_refresh_required' in screen['reasons']
        and screen['source_age_s'] == now - source_at and now - source_at > .05, 'recomputed_expiry_and_deadline_refusal')
    check(screen['execution_authority'] is False and screen['old_collection_capability_reusable'] is False
        and screen['current_capability_id'] is None and screen['new_physical_commands'] == 0
        and delivery['new_current_capability_acquired'] is False, 'refusal_does_not_grant_execution')
    check(b['additional_actions'] == 0 and raw['later_transitions'] == []
        and observed['A']['transitions'] == observed['B']['transitions'] == [], 'no_advice_actions_or_transitions')

    check(raw['input'] == baseline['input'], 'same_exogenous_input')
    check(len(raw['result']['jobs']) == 5 and {row['business_bag_id'] for row in raw['result']['jobs']} == JOBS
        and raw['result']['jobs'] == baseline['result']['jobs'], 'all_five_jobs_exact')
    check(len(raw['result']['trays']) == 3 and {row['tray_id'] for row in raw['result']['trays']} == TRAYS
        and raw['result']['trays'] == baseline['result']['trays'], 'all_three_trays_exact')
    nonpub, baseline_nonpub = nonpublication(raw), nonpublication(baseline)
    check(len(nonpub) == 140 and nonpub == baseline_nonpub, 'all_140_nonpublication_receipts_exact')
    calls = lambda data: [item for item in data['calls'] if item['kind'] in {'route', 'transfer'}]
    check(calls(raw) == calls(baseline), 'all_actual_physical_calls_exact_no_added_actions')
    outbox = lambda data: {key: value for key, value in data['outbox'].items() if value['kind'] in {'route', 'transfer'}}
    check(outbox(raw) == outbox(baseline), 'all_physical_request_identity_ACK_and_outbox_rows_exact')
    complete = {row['business_bag_id']: row['completed_at'] for row in raw['result']['jobs']}
    base_complete = {row['business_bag_id']: row['completed_at'] for row in baseline['result']['jobs']}
    check(set(complete) == JOBS and all(finite(value) and value >= 0 for value in complete.values())
        and complete == raw['summary']['completion'] == base_complete, 'all_actual_job_completion_values_equal')
    for flag in ('realtime_async', 'native_protection_certified', 'full_foreground_R1_100ms_certified',
                 'prescheduling_gain_measured', 'new_current_admission_tested', 'on_time_admission_tested',
                 'p99_or_hard_realtime_bound_claimed'):
        check(worker[flag] is False, 'honest_claim_boundary:' + flag)
    return {'audited_run': str(RUN), 'raw_sha256': sha(raw_path), 'prediction_sha256': sha(RUN / 'prediction.json'),
        'baseline_raw': str(baseline_path), 'baseline_raw_sha256': sha(baseline_path),
        'distinct_processes': {'native_pid': acceptance['pid'], 'predictor_pid': life['process_id']},
        'worker_compute_wall_ms': prediction['worker_compute_wall_ms'], 'worker_compute_cpu_ms': prediction['worker_compute_cpu_ms'],
        'overlap': {'sample_count': len(overlap), 'first': overlap[0], 'last': overlap[-1],
                    'physical_event_count': len(physical), 'actual_physical_events': physical},
        'candidate_completion': {action: result['completion'] for action, result in results.items()},
        'source_captured_at': source_at, 'capture_sim_time': advice['capture_sim_time'],
        'expiry': expiry, 'use_by': advice['use_by'], 'delivery_sim_time': now, 'current_screen': screen,
        'unchanged_actual_completion': complete, 'per_job_delta': {job: complete[job] - base_complete[job] for job in sorted(JOBS)},
        'jobs': 5, 'trays': 3, 'nonpublication_receipts': len(nonpub), 'physical_call_count': len(calls(raw)),
        'physical_request_count': len(outbox(raw)), 'source_pin_count': len(plan['source_pins']),
        'archived_source_count': len(source_map), 'native_evidence_pin_count': len(acceptance['evidence_sha256']),
        'scope': 'Independent recomputation from saved multirate_002 artifacts; no project import, model call or native run.',
        'limits': ['Offline event simulation with process overlap; no wall-to-simulation-time mapping or hard real-time certificate.',
            'Only late refusal is exercised; no fresh current admission, on-time action or prescheduling benefit is established.',
            'Transient client ACK state at the delivery instant is not fully reconstructed; final physical ACK/outbox rows match baseline exactly.',
            'Source pins and archived bytes are checked as declared, not a complete operating-system dependency image.']}


def main():
    result = {'schema': 'g31.independent.multirate002_audit.v1', 'status': 'failed',
        'script_sha256': sha(__file__), 'python': sys.executable, 'standard_library_only': True}
    try:
        result.update(audit())
        result['status'] = 'passed'
    except Exception:
        result['exception'] = traceback.format_exc()
    result.update(checks=CHECKS, check_count=len(CHECKS), unique_files_hashed=len(HASHES))
    with (OUT / 'audit_report.json').open('x', encoding='utf8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: result.get(key) for key in ('status', 'check_count', 'unique_files_hashed', 'exception')}, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
