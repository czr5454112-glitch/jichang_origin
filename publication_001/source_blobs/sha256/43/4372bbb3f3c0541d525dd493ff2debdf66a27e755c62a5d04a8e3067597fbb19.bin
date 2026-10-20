"""One native baseline continuation with an isolated, non-authoritative predictor.

This measures process overlap in an offline event-driven native simulation. It
does not pace that simulation to wall time and must not be called realtime_async.
"""
from __future__ import annotations

import sys

if __name__ == '__main__' and '--worker' in sys.argv:
    if '--admission' not in sys.argv or sys.stdin.readline().strip() != sys.argv[sys.argv.index('--admission') + 1]:
        raise SystemExit('multirate_probe:missing_parent_job_admission')

import argparse
import gzip
import json
import math
from pathlib import Path
import secrets
import time
import traceback

from . import bounded_windows_job
from . import foundation_later_campaign as campaign
from . import foundation_later_control as control
from . import foundation_later_episode as episode
from . import foundation_multirate as multirate
from . import foundation_native_environment as environment
from . import foundation_successful_refresh_probe as comparison

ROOT = campaign.ROOT
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_multirate_probe'
SCHEMA = 'g31.foundation.multirate_probe.v1'
HARD_SECONDS = 150
LIFECYCLE_EVENTS = frozenset(('LOAD_START', 'LOAD_COMPLETE', 'EDGE_ENTER', 'EDGE_EXIT',
    'STORAGE_ENTER', 'STORAGE_RELEASE', 'UNLOAD_START', 'UNLOAD_COMPLETE',
    'HOLD_START', 'HOLD_COMPLETE', 'EMPTY_RECEIVED'))


def require(condition, reason):
    if not condition:
        raise ValueError('multirate_probe:' + reason)


class MultirateLaterControl(control.LaterControl):
    """Observe the original policy; the advice never enters its submission path."""
    def __init__(self, *args, predictor, **kwargs):
        super().__init__(*args, **kwargs)
        require(self.model is None and self.mode == 'guarded', 'original_continuation_without_sync_predictor')
        self.predictor = predictor
        self.advice = self.result_delivery = self.expiry_event = None
        self.samples, self.poll_wall_ms = [], []
        self.collect_wall_ms = []
        self.evidence = None
        original_activate = self.policy.activate

        def activate(trigger):
            result = original_activate(trigger)
            if self.policy.owner == 'B' and self.advice is not None:
                self.poll()
            return result

        self.policy.activate = activate

    def collect(self, view):
        started = time.perf_counter_ns()
        policy = self.policy
        capture = (policy.owner == 'B' and self.advice is None and policy.pending is not None
                   and policy.pending['phase'] == 'first_reuse_route')
        before = len(policy.decisions)
        if capture:
            # Preserve inputs from before the original policy handles its default.
            owned = control.plain(policy.client.owned(policy.owner))
            retained = policy.ledger.audit_copy()
            calls = [control.plain(row) for row in policy.client.calls if row['request']['owner_id'] == policy.owner]
        result = self.original(view)
        if capture and len(policy.decisions) > before:
            decision = policy.decisions[-1]
            require(decision['selected_action_admitted'] is True and not decision['fallback_used']
                    and decision['native_request_id'] is None
                    and decision['executed_first_action']['reuse_next'] is None, 'unchanged_admitted_native_default')
            require(self.adapter.is_native_collected(decision['information']), 'real_successful_collection')
            self.evidence = {'schema': control.EVIDENCE_SCHEMA, 'owner': policy.owner,
                'phase': decision['phase'], 'at': view['now'], 'collection': control.plain(decision['collection']),
                'information': self.adapter.json_data(decision['information']), 'retained': retained,
                'own_outbox': owned, 'own_calls': calls}
            self.advice = multirate.advice_from_evidence(self.evidence, self.reference)
            self.predictor.submit(self.evidence, control.PHASE_ACTIONS['first_reuse_route'])
        self.collect_wall_ms.append({'at': view['now'], 'wall_ms': (time.perf_counter_ns() - started) / 1e6,
                                     'capture_candidate': capture})
        return result

    def poll(self):
        start = time.perf_counter_ns()
        try:
            policy = self.policy
            now = policy.session.physical_time
            sample = {'wall_ns': start, 'sim_time': now,
                      'worker_started': self.predictor.started.is_set(), 'worker_done': self.predictor.done.is_set()}
            self.samples.append(sample)
            expired = now - self.advice['source_captured_at'] > multirate.SOURCE_TTL
            if self.expiry_event is None and expired:
                self.expiry_event = {'kind': 'registered_source_expiry_checked_on_native_owner_activation',
                    'due_at': self.advice['source_collection_valid_through'], 'observed_at': now,
                    'detection_lag_sim_s': now - self.advice['source_collection_valid_through'],
                    'requires_new_message': False, 'old_capability_revoked': True,
                    'default_continuation_changed': False}
            if self.result_delivery is None and sample['worker_done']:
                view = policy.session.observe_protocol(policy.owner)
                current = multirate.screen_current(self.advice, view, policy.client.owned(policy.owner))
                self.result_delivery = {'ready_observed_ns': time.perf_counter_ns(), 'ready_sim_time': now,
                    'current_local_view': control.plain(view), 'screen': current,
                    'new_current_capability_acquired': False,
                    'scope': 'Current local refusal only; no fresh full-domain collection or submission attempted.'}
        finally:
            self.poll_wall_ms.append((time.perf_counter_ns() - start) / 1e6)

    def audit_copy(self):
        result = super().audit_copy()
        result['multirate'] = control.plain({'advice': self.advice, 'input_evidence': self.evidence,
            'samples': self.samples, 'poll_wall_ms': self.poll_wall_ms, 'result_delivery': self.result_delivery,
            'original_collect_plus_capture_wall_ms': self.collect_wall_ms,
            'expiry_event': self.expiry_event, 'additional_actions': 0,
            'timing_mode': 'offline_event_clock_with_process_async_advice', 'realtime_async': False,
            'old_collection_TTL_seconds': multirate.SOURCE_TTL})
        return result


def factory_for(predictor, controls):
    def factory(policy, reference, **kwargs):
        result = MultirateLaterControl(policy, reference, predictor=predictor, **kwargs)
        controls[policy.owner] = result
        return result
    return factory


def prepare(output):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and output != ROOT and not output.exists(), 'fresh_workspace_output')
    contract = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    semantic = contract.parent / 'native027_semantic_native_002/receipt.json'
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'hard_seconds': HARD_SECONDS,
        'native_branches': 1, 'automatic_retries': 0, 'case': 'mechanism', 'method': 'incumbent', 'horizon': 40.,
        'source_pins': campaign.source_pins(), 'baseline': comparison.baseline_references(),
        'runtime_references': [campaign.reference(path) for path in (contract, semantic,
            campaign.read(contract)['binary'], sys.executable)],
        'timing_mode': 'offline_event_clock_with_process_async_advice', 'realtime_async': False,
        'wall_to_sim_time_mapping': None, 'old_collection_TTL_seconds': multirate.SOURCE_TTL,
        'new_action_admission_enabled': False, 'default_continuation_keeps_running': True,
        'source_expiry_timer': 'Checked at each existing B owner activation; no new native wakeup is fabricated.',
        'cold_worker_start_before_native': True, 'injected_delay_wall_ms': 0.,
        'scope': 'One real detached prediction; default physical trajectory and current-time late refusal.'}
    output.mkdir(parents=True)
    campaign.write_new(output / 'plan.json', plan)
    check_plan(plan)
    return plan


def check_plan(plan):
    require(plan['schema'] == SCHEMA and plan['hard_seconds'] == HARD_SECONDS and plan['native_branches'] == 1
            and plan['automatic_retries'] == 0 and plan['case'] == 'mechanism' and plan['method'] == 'incumbent'
            and plan['horizon'] == 40. and plan['realtime_async'] is False
            and plan['new_action_admission_enabled'] is False and plan['old_collection_TTL_seconds'] == .05,
            'fixed_probe_protocol')
    require(plan['source_pins'] == campaign.source_pins(), 'source_set_or_bytes_changed')
    for item in list(plan['baseline'].values()) + plan['runtime_references']:
        require(campaign.sha(item['path']) == item['sha256'], 'reference_bytes_changed')


def known_prediction(report):
    """A valid seed alone says nothing about individual rollout completion."""
    if type(report) is not dict or report.get('status') != 'conditional_current_seed':
        return False
    results = report.get('candidate_results')
    evaluation = report.get('evaluation', {})
    return (type(results) is dict and set(results) == set(control.PHASE_ACTIONS['first_reuse_route'])
        and evaluation.get('source_exit_pins_passed') is True
        and evaluation.get('native_execution_authority') is False
        and all(type(result) is dict and result.get('status') == 'conditional_prediction'
            and result.get('online_executable') is False and result.get('native_protection_certified') is False
            and type(result.get('completion')) is dict and set(result['completion']) == set(control.JOBS)
            and all(type(value) in (int, float) and math.isfinite(value) and value >= 0.
                for value in result['completion'].values()) for result in results.values()))


def physical_progress(receipts, start, end):
    return [row for row in receipts if start < row['time'] <= end
        and row['event'] in LIFECYCLE_EVENTS and row.get('tray_id')]


def assess(raw, baseline, current, prediction):
    audit = current.audit_copy()['multirate']
    require(prediction['status'] == 'completed_detached_prediction'
            and known_prediction(prediction['model_report']), 'actual_supported_prediction_required')
    overlap = [sample for sample in audit['samples']
               if prediction['worker_started_ns'] <= sample['wall_ns'] <= prediction['worker_compute_end_ns']]
    progressed = (physical_progress(raw['result']['receipts'], overlap[0]['sim_time'], overlap[-1]['sim_time'])
        if overlap else [])
    require(len(overlap) >= 2 and overlap[-1]['sim_time'] > overlap[0]['sim_time'] and progressed,
            'native_physical_events_during_actual_worker_compute_required')
    physical = [comparison.physical_receipts(value) for value in (raw, baseline)]
    parity = {'input_exact': raw['input'] == baseline['input'],
              'physical_receipts_all_fields': physical[0] == physical[1],
              'physical_receipt_count': len(physical[0]),
              **{field + '_exact': raw['result'][field] == baseline['result'][field] for field in ('jobs', 'trays')}}
    actual = episode.compare_terminal(baseline, raw)
    require(all(parity[key] for key in ('input_exact', 'physical_receipts_all_fields', 'jobs_exact', 'trays_exact'))
            and all(delta == 0 for delta in actual['per_job_delta'].values()), 'baseline_physical_trajectory_changed')
    delivery = audit['result_delivery']
    require(delivery is not None and delivery['screen']['status'] == 'rejected'
            and 'action_deadline_missed' in delivery['screen']['reasons'], 'actual_current_late_refusal_required')
    require(audit['expiry_event'] is not None and raw['later_transitions'] == [], 'no_advice_action_or_transition')
    return {'physical_parity': parity, 'actual_terminal_comparison': actual,
        'native_progress_during_worker': {'sample_count': len(overlap),
            'from_sim_time': overlap[0]['sim_time'], 'through_sim_time': overlap[-1]['sim_time'],
            'actual_receipts': progressed, 'actual_receipt_count': len(progressed)},
        'delivery': delivery, 'expiry_event': audit['expiry_event'],
        'poll_cost': {'count': len(audit['poll_wall_ms']), 'total_wall_ms': sum(audit['poll_wall_ms']),
                      'max_wall_ms': max(audit['poll_wall_ms'])},
        'B_original_collect_plus_capture': audit['original_collect_plus_capture_wall_ms'],
        'foreground_activation_cost': {'count': len(raw['activation_records']),
            'total_wall_ms': sum(row.get('compute_wall_ms', 0.) for row in raw['activation_records']),
            'max_wall_ms': max(row.get('compute_wall_ms', 0.) for row in raw['activation_records']),
            'scope': 'All initial and retained activation costs, including original collection and polling; '
                     'overlaps other reported intervals and is not a separate additive cost.'},
        'enqueue_to_ready_observation_wall_ms':
            (delivery['ready_observed_ns'] - current.predictor.timing['enqueued_ns']) / 1e6,
        'response_timing_scope': 'Enqueue to readiness observation; original capture and collection costs '
                                 'are separate, no submission or ACK is performed for advice.',
        'full_foreground_R1_100ms_certified': False, 'native_protection_certified': False,
        'realtime_async': False, 'prescheduling_gain_measured': False,
        'new_current_admission_tested': False, 'on_time_admission_tested': False,
        'forecast_samples': 1, 'p99_or_hard_realtime_bound_claimed': False}


def worker(output, expected_plan_sha):
    output = Path(output).resolve()
    plan = campaign.read(output / 'plan.json')
    controls = {}
    predictor = multirate.PredictionWorker(output / 'prediction.json')
    report = {'schema': SCHEMA, 'status': 'unknown_failed', 'native_execution_attempted': False}
    try:
        require(campaign.sha(output / 'plan.json') == expected_plan_sha, 'plan_changed_before_worker')
        check_plan(plan)
        predictor.start()
        report['native_execution_attempted'] = True
        receipt = environment.run_baseline(output / 'native', later_mode='guarded', later_model=None,
            later_control_factory=factory_for(predictor, controls))
        report['native_receipt'] = campaign.reference(output / 'native/receipt.json')
        require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed',
                'closed_native_run_required')
        prediction = predictor.finish()  # Only after the native episode has finished.
        require(prediction is not None, 'native_prediction_was_not_launched')
        current = controls['B']
        if current.result_delivery is None:
            current.poll()  # Honest terminal arrival, not an invented earlier simulation time.
        raw_path = output / 'native/raw.json.gz'
        require(receipt['raw_artifact']['sha256'] == campaign.sha(raw_path), 'native_raw_binding')
        raw = json.loads(gzip.decompress(raw_path.read_bytes()))
        baseline = json.loads(gzip.decompress(Path(plan['baseline']['raw.json.gz']['path']).read_bytes()))
        report['native_raw'] = campaign.reference(raw_path)
        report['prediction'] = campaign.reference(output / 'prediction.json')
        report.update(assess(raw, baseline, current, prediction))
        report['status'] = 'completed_multirate_late_refusal_probe'
    except Exception:
        report['exception'] = traceback.format_exc()
    finally:
        predictor.terminate()
        report['worker_lifecycle_timing'] = predictor.timing
        campaign.write_new(output / 'probe_observations.json', {owner: current.audit_copy() for owner, current in controls.items()})
        report['probe_observations'] = campaign.reference(output / 'probe_observations.json')
        try:
            require(campaign.sha(output / 'plan.json') == expected_plan_sha, 'plan_changed_during_worker')
            check_plan(plan)
            report['source_and_reference_exit_pins_passed'] = True
        except Exception:
            report['status'] = 'unknown_failed'
            report['exit_pin_exception'] = traceback.format_exc()
    campaign.write_new(output / 'worker_report.json', report)
    return report


def launch(output):
    output = Path(output).resolve()
    plan = campaign.read(output / 'plan.json')
    check_plan(plan)
    plan_sha = campaign.sha(output / 'plan.json')
    campaign.write_new(output / 'launch_started.json', {'plan_sha256': plan_sha, 'hard_seconds': HARD_SECONDS})
    admission = secrets.token_hex(24)
    receipt = {'schema': SCHEMA, 'status': 'unknown_failed', 'plan': campaign.reference(output / 'plan.json')}
    try:
        with (output / 'stdout.log').open('x') as stdout, (output / 'stderr.log').open('x') as stderr:
            process = bounded_windows_job.run([sys.executable, '-m', MODULE, '--worker', '--output', str(output),
                '--plan-sha256', plan_sha, '--admission', admission], timeout=HARD_SECONDS,
                stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
        receipt['process'] = process
        report_path = output / 'worker_report.json'
        report = campaign.read(report_path) if report_path.exists() else {}
        receipt['worker_report'] = campaign.reference(report_path) if report_path.exists() else None
        check_plan(plan)
        require(campaign.sha(output / 'plan.json') == plan_sha, 'plan_changed_after_worker')
        require(process['status'] == 'exited' and process['exitcode'] == 0
                and report.get('status') == 'completed_multirate_late_refusal_probe'
                and report.get('source_and_reference_exit_pins_passed') is True, 'process_and_worker_success_required')
        for name in ('native_receipt', 'native_raw', 'probe_observations', 'prediction'):
            require(campaign.sha(report[name]['path']) == report[name]['sha256'], 'worker_artifact_binding:' + name)
        receipt['status'] = 'completed_multirate_late_refusal_probe'
    except Exception:
        receipt['exception'] = traceback.format_exc()
    campaign.write_new(output / 'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare', action='store_true')
    action.add_argument('--launch', action='store_true')
    action.add_argument('--worker', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--admission')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    result = prepare(args.output) if args.prepare else worker(args.output, args.plan_sha256) if args.worker else launch(args.output)
    print(json.dumps({'status': result['status']}))
    return 0 if result['status'] in ('prepared_unexecuted', 'completed_multirate_late_refusal_probe') else 1


if __name__ == '__main__':
    raise SystemExit(main())
