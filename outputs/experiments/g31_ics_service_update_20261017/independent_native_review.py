"""Read-only comparison of two closed actual native episodes, no model imports."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import traceback

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'outputs/experiments/g31_ics_service_update_20261017'
REFERENCE = ROOT / 'outputs/experiments/g31_ics_learning_next_20261017/later_episodes_001/guarded_default/episode/native'
CURRENT = BASE / 'native_001/guarded_default/episode/native'
TIMING_FIELDS = ('actor_choose_wall_ms', 'actor_inference_wall_ms', 'collection_through_offer_wall_ms',
    'model_and_guard_wall_ms', 'submission_and_local_guard_wall_ms',
    'collection_to_decision_record_wall_ms', 'request_timing_scope')
JOBS = {'loaded', 'receiver', 'reuse1', 'reuse2', 'blocker'}


def encoding(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoding(value).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reject_constant(value):
    raise ValueError('nonfinite_json:' + value)


class Review:
    def __init__(self):
        self.pins = {}
        self.checks = []

    def read(self, path):
        path = Path(path).resolve(strict=True)
        data = path.read_bytes()
        current = hashlib.sha256(data).hexdigest()
        if str(path) in self.pins and self.pins[str(path)] != current:
            raise ValueError('input_changed_between_reads:' + str(path))
        self.pins[str(path)] = current
        return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data,
            parse_constant=reject_constant)

    def check(self, name, condition, **detail):
        self.checks.append({'name': name, 'passed': bool(condition), **detail})

    def equal(self, name, reference, actual):
        self.check(name, encoding(reference) == encoding(actual),
            reference_json_sha256=digest(reference), actual_json_sha256=digest(actual))

    def bound(self, reference, expected_path=None):
        path = Path(reference['path']).resolve(strict=True)
        self.check('reference_sha256:' + str(path), sha(path) == reference['sha256'])
        if expected_path is not None:
            self.check('reference_path:' + str(path), path == Path(expected_path).resolve())
        return path

    def episode(self, directory, label):
        directory = Path(directory).resolve(strict=True)
        receipt_path = directory / 'receipt.json'
        receipt = self.read(receipt_path)
        self.check(label + ':closed_native_receipt', receipt['status'] == 'assessed'
            and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed'
            and receipt['native_session_attempted'] is True)
        plan = self.read(self.bound(receipt['plan'], directory / 'preregistered_protocol.json'))
        raw = self.read(self.bound(receipt['raw_artifact'], directory / 'raw.json.gz'))
        acceptance = self.read(directory / 'acceptance.json')
        self.equal(label + ':acceptance_plan_binding', receipt['plan'], acceptance['run_reference'])
        self.check(label + ':acceptance_closed', acceptance['status'] == 'closed_run_acceptance_passed'
            and acceptance['active'] is False and acceptance['invalid'] == []
            and acceptance['branch_keys'] == ['mechanism/incumbent'])
        self.equal(label + ':receipt_raw_summary', receipt['summary'], raw['summary'])
        input_path = directory / 'inputs/mechanism/incumbent.json'
        input_value = self.read(input_path)
        self.check(label + ':registered_input_hash', sha(input_path) == plan['input_file_sha256']['mechanism/incumbent'])
        self.equal(label + ':registered_raw_input', input_value, raw['input'])
        archived = []
        self.check(label + ':source_archive_key_coverage', set(plan['source_sha256']) == set(plan['source_archive']))
        for source, expected in plan['source_sha256'].items():
            archive = (directory / plan['source_archive'][source]).resolve(strict=True)
            self.check(label + ':archive_path_scope:' + source, archive.is_relative_to(directory / 'source'))
            actual = sha(archive)
            self.pins[str(archive)] = actual
            archived.append(actual == expected)
        self.check(label + ':all_archived_source_bytes', bool(archived) and all(archived), count=len(archived))
        branch = directory.parent.parent
        branch_receipt = self.read(branch / 'receipt.json')
        self.bound(branch_receipt['native_receipt'], receipt_path)
        worker = self.read(self.bound(branch_receipt['worker_report'], branch / 'worker_report.json'))
        self.bound(worker['native_receipt'], receipt_path)
        process = branch_receipt['process']
        self.check(label + ':bounded_completed_branch', branch_receipt['status'] == 'completed_later_episode'
            and worker['status'] == 'completed_later_episode'
            and worker['source_and_checkpoint_exit_pins_passed'] is True
            and process['status'] == 'exited' and process['exitcode'] == 0
            and process['hard_timeout_seconds'] == 150
            and process['windows_job_kill_on_close'] is True
            and process['child_released_only_after_job_assignment'] is True)
        launch = self.read(branch / 'launch.json')
        campaign = self.read(self.bound(launch['plan'], branch.parent / 'plan.json'))
        shared = set(campaign['source_sha256']) & set(plan['source_sha256'])
        self.check(label + ':campaign_shared_source_binding', bool(shared) and all(
            campaign['source_sha256'][source] == plan['source_sha256'][source] for source in shared),
            shared_count=len(shared), native_archive_only_sources=sorted(set(plan['source_sha256']) - shared))
        self.check(label + ':no_100ms_certificate', receipt['complete_request_100ms_certified'] is False
            and raw['summary']['complete_request_100ms_certified'] is False)
        return raw, plan, {'native_receipt': {'path': str(receipt_path), 'sha256': sha(receipt_path)},
            'raw': receipt['raw_artifact'], 'plan': receipt['plan'], 'process': process,
            'source_archive_count': len(archived), 'live_source_files_not_used_to_rejudge_historical_runs': True}


def comparable_transition(row):
    result = {name: value for name, value in row.items() if name not in TIMING_FIELDS and name != 'model_report'}
    result['model_report'] = {name: row['model_report'][name] for name in ('status', 'seed', 'candidate_results')}
    return result


def review(current, reference):
    audit = Review()
    result = {'schema': 'g31.foundation.service_update.independent_native_review.v1', 'status': 'unknown',
        'independent_scene_count': 1, 'native_executions': 0, 'model_evaluations': 0,
        'complete_request_100ms_certified': False, 'quality_improvement_claimed': False,
        'excluded_transition_fields': list(TIMING_FIELDS),
        'comparison_scope': 'Strict sorted JSON identity; no float tolerance, ID rewriting, trace filtering or outcome-based rebasing.',
        'timing_limit': 'Instrumented offline_sync collection entry through decision record is not a complete deployment request or ACK latency.'}
    try:
        old, old_plan, old_meta = audit.episode(reference, 'reference')
        new, new_plan, new_meta = audit.episode(current, 'current')
        result['episodes'] = {'reference': old_meta, 'current': new_meta}
        audit.equal('input_exact', old['input'], new['input'])
        for field in ('receipts', 'jobs', 'trays'):
            audit.equal('full_native_' + field + '_exact', old['result'][field], new['result'][field])
        for field in ('calls', 'outbox', 'request_creations', 'continuation', 'decision_boundaries'):
            audit.equal('full_' + field + '_exact', old[field], new[field])
        old_rows = {(row['owner'], row['phase']): row for row in old['later_transitions']}
        new_rows = {(row['owner'], row['phase']): row for row in new['later_transitions']}
        expected = {('A', 'first_return'), ('B', 'first_reuse_route')}
        audit.check('exact_two_unique_cutpoints', len(old['later_transitions']) == len(new['later_transitions']) == 2
            and set(old_rows) == set(new_rows) == expected)
        rows = []
        for identity in sorted(expected):
            earlier, actual = old_rows[identity], new_rows[identity]
            name = '_'.join(identity)
            audit.equal(name + ':complete_nontiming_transition', comparable_transition(earlier), comparable_transition(actual))
            for field in ('seed', 'candidate_results'):
                audit.equal(name + ':full_model_' + field, earlier['model_report'][field], actual['model_report'][field])
            evidence = actual['model_report']['seed']['evidence']
            audit.equal(name + ':raw_evidence', earlier['model_report']['seed']['evidence'], evidence)
            audit.equal(name + ':original_reference', earlier['initial_reference'], actual['initial_reference'])
            audit.check(name + ':original_reference_digest', digest(actual['initial_reference']) == actual['initial_reference_sha256'])
            initial = new['initial_owners'][identity[0]]
            choices = [row for row in initial['selection']['provider_evidence']['rows'] if row['candidate_index'] == 4]
            audit.check(name + ':one_initial04_reference', len(choices) == 1)
            audit.equal(name + ':reference_still_initial04', choices[0]['completion'], actual['initial_reference']['completion'])
            evaluation = actual['model_report']['evaluation']
            audit.equal(name + ':request_local_counts', {'static_catalog_builds': 1, 'static_catalog_reads': 31,
                'dynamic_later_context_calls': 2}, evaluation['counts'])
            audit.check(name + ':request_local_guards_and_scope', evaluation['source_exit_pins_passed'] is True
                and evaluation['cross_request_cache'] is False and evaluation['dynamic_guards_skipped'] is False
                and evaluation['native_execution_authority'] is False
                and evaluation['source_pins_are_full_dependency_proof'] is False
                and evaluation['campaign_full_source_pins_required'] is True)
            audit.check(name + ':request_pins_bound_to_native_archive', all(
                new_plan['source_sha256'].get(path) == expected_hash
                for path, expected_hash in evaluation['source_sha256'].items()))
            isolation = actual['actor_state_check']
            audit.check(name + ':actor_native_state_and_clock_unchanged', actual['actor_state_unchanged'] is True
                and isolation['native_state_before'] == isolation['native_state_after']
                and isolation['physical_time_before'] == isolation['physical_time_after'])
            wall = actual['collection_to_decision_record_wall_ms']
            audit.check(name + ':decision_window_finite', type(wall) in (int, float) and math.isfinite(wall)
                and wall >= actual['collection_through_offer_wall_ms'] >= 0
                and 'later ACK' in actual['request_timing_scope'])
            rows.append({'owner': identity[0], 'phase': identity[1], 'at': evidence['at'],
                'action_id': actual['action_id'], 'candidate_id': actual['candidate_id'],
                'full_model_report_json_sha256': digest({name: actual['model_report'][name]
                    for name in ('status', 'seed', 'candidate_results')}),
                'evaluation': evaluation, 'timings': {field: actual.get(field) for field in TIMING_FIELDS}})
        result['cutpoints'] = rows
        completion = {job['business_bag_id']: job['completed_at'] for job in new['result']['jobs']}
        audit.check('complete_five_business_jobs', set(completion) == JOBS
            and all(type(value) in (int, float) and math.isfinite(value) and value >= 0 for value in completion.values()))
        audit.check('same_finite_three_trays', len(new['result']['trays']) == len(new['input']['trays']) == 3)
        audit.check('all_shadow_native_states_unchanged', bool(new['shadow_records']) and all(
            row['native_state_before'] == row['native_state_after'] for row in new['shadow_records']))
        result['physical_summary'] = {'completion': completion, 'receipt_count': len(new['result']['receipts']),
            'event_counts': dict(Counter(row['event'] for row in new['result']['receipts'])),
            'job_count': len(new['result']['jobs']), 'tray_count': len(new['result']['trays'])}
    except Exception:
        result['exception'] = traceback.format_exc()
    changed = [path for path, expected_hash in audit.pins.items() if sha(path) != expected_hash]
    audit.check('all_read_artifacts_unchanged_at_exit', not changed, changed=changed)
    result['read_artifact_sha256'] = audit.pins
    result['checks'] = audit.checks
    result['failed_checks'] = [row for row in audit.checks if not row['passed']]
    if not result.get('exception') and not result['failed_checks']:
        result['status'] = 'passed_exact_native_and_current_model_parity'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--current', type=Path, default=CURRENT)
    parser.add_argument('--reference', type=Path, default=REFERENCE)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(BASE) or output.exists():
        raise SystemExit('fresh_review_report_under_service_update_required')
    result = review(args.current, args.reference)
    result['reviewer_source'] = {'path': str(Path(__file__).resolve()), 'sha256': sha(__file__)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    print(json.dumps({'status': result['status'], 'failed_check_count': len(result['failed_checks']),
        'exception': result.get('exception'), 'output': str(output)}, ensure_ascii=False))
    return 0 if result['status'] == 'passed_exact_native_and_current_model_parity' else 1


if __name__ == '__main__':
    raise SystemExit(main())
