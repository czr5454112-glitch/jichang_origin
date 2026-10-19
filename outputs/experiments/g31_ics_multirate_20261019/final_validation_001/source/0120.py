"""One frozen-model initial dispatch pair, with one bounded process per episode.

Preparation is read-only with respect to native execution. Both branches use
the explicit selector bridge; the first selects incumbent04 and the second
uses the already frozen mechanism-held-out linear model. No model is fitted.
"""
from __future__ import annotations

import sys

if __name__ == '__main__' and '--worker' in sys.argv:
    if '--admission' not in sys.argv:
        raise SystemExit('initial_campaign:missing_parent_job_admission')
    expected_admission = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != expected_admission:
        raise SystemExit('initial_campaign:missing_parent_job_admission')

import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import secrets
import traceback

from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_initial_campaign'
SCHEMA = 'g31.foundation.initial_selector_campaign.v1'
HARD_SECONDS = 150
JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')
BRANCHES = ({'id': 'bridge04', 'mode': 'incumbent'}, {'id': 'learned', 'mode': 'learned'})
DEFAULT_MODEL = ROOT / 'outputs/experiments/g31_ics_foundation_learning_20261017/l0_002/models/linear_holdout_mechanism.json'
MODEL_SHA256 = 'caa345a054c8c05c5db528f9b11dfd5343b334c1d6dd977e93f60ad7e2669f78'


def require(condition, reason):
    if not condition:
        raise ValueError('initial_campaign:' + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + '\n')


def strict_equal(left, right):
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def source_pins():
    paths = set((ROOT / 'scripts/experiments/g31_ics_circulation').glob('*.py'))
    paths.update((ROOT / 'src/czr005').rglob('*.py'))
    return {str(path.resolve()): sha(path) for path in sorted(paths)}


def validate_model(path):
    from . import foundation_budgeted_probe as probe
    path = Path(path).resolve(strict=True)
    require(sha(path) == MODEL_SHA256, 'preexisting_task2_linear_model_bytes')
    payload = probe.validate_model(path)
    require(len(payload['feature_names']) == len(set(payload['feature_names'])) == 43
            and payload['score_direction'] == 'higher_is_better_negative_predicted_delta',
            'frozen_43_feature_score_contract')
    return payload


def check_pins(plan):
    require(plan['schema'] == SCHEMA and plan['hard_process_seconds'] == HARD_SECONDS
            and plan['automatic_retries'] == 0 and plan['scenario'] == 'mechanism'
            and plan['method'] == 'incumbent' and plan['horizon'] == 40.
            and plan['timing_mode'] == 'offline_sync' and strict_equal(plan['branches'], list(BRANCHES)),
            'fixed_pair_protocol_required')
    require(plan['model']['sha256'] == plan['model_copy']['sha256'] == MODEL_SHA256
            and plan['feature_count'] == 43, 'fixed_model_identity')
    require(source_pins() == plan['source_sha256'], 'source_set_or_bytes_changed')
    require(set(plan['source_archive']) == set(plan['source_sha256']), 'complete_source_archive')
    for source, archived in plan['source_archive'].items():
        require(sha(archived) == plan['source_sha256'][source], 'archived_source_changed:' + source)
    for item in [plan['model'], plan['model_copy'], *plan['runtime_references']]:
        require(sha(item['path']) == item['sha256'], 'pinned_artifact_changed:' + item['path'])


def prepare(output, *, model=DEFAULT_MODEL):
    output, model = Path(output).resolve(), Path(model).resolve(strict=True)
    require(output.is_relative_to(ROOT) and output != ROOT, 'workspace_output_required')
    require(not output.exists(), 'fresh_output_required')
    payload = validate_model(model)
    contract_path = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    semantic_path = contract_path.parent / 'native027_semantic_native_002/receipt.json'
    contract = read(contract_path)
    pins = source_pins()
    output.mkdir(parents=True, exist_ok=False)
    archives = {}
    for index, source in enumerate(pins):
        target = output / 'source' / f'{index:04d}.py'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(Path(source).read_bytes())
        archives[source] = str(target)
    model_copy = output / 'frozen_linear_model.json'
    model_copy.write_bytes(model.read_bytes())
    plan = {'schema': SCHEMA, 'status': 'prepared_not_executed', 'scenario': 'mechanism',
        'method': 'incumbent', 'horizon': 40., 'timing_mode': 'offline_sync',
        'branches': copy.deepcopy(list(BRANCHES)), 'hard_process_seconds': HARD_SECONDS,
        'automatic_retries': 0, 'native_episode_budget': 2, 'source_sha256': pins, 'source_archive': archives,
        'model': reference(model), 'model_copy': reference(model_copy), 'model_version': payload['model_version'],
        'feature_schema': payload['feature_schema'], 'feature_count': 43,
        'runtime_references': [reference(path) for path in (contract_path, semantic_path, contract['binary'],
            sys.executable, model.parent / 'folds.json', model.parent / 'registration.json')],
        'runtime_python': sys.version, 'owner_A_budget': {'K': 1, 'P': 1, 'indices': [4]},
        'owner_B_incumbent_budget': {'K': 1, 'P': 1, 'indices': [4]},
        'owner_B_learned_budget': {'K': 4, 'P': 2, 'public_compatible_indices': [0, 1, 4, 5, 8, 9, 12, 13]},
        'selection': 'Frozen scores allocate queried candidates, then choose among currently protected compatible queried candidates.',
        'independent_scene_count': 1, 'training_performed': False, 'full32_teacher_in_controller': False,
        'original_reference_refresh_allowed': False, 'native_protection_certified': False,
        'complete_request_100ms_certified': False, 'multistep_RL_established': False,
        'scope': 'New matched native pair for one mechanism scene; conditional guards and actual outcomes are separate evidence.'}
    write_new(output / 'plan.json', plan)
    check_pins(plan)
    return plan


def assess_branch(raw, mode, model_version):
    """Check the actual call chain; rejected ACKs remain visible outcomes."""
    require(mode in ('incumbent', 'learned') and raw['kind'] == 'EvaluatorRecord'
            and raw['summary']['status'] == 'assessed'
            and raw['native027_acceptance']['runtime_accepted'] is True, 'accepted_completed_native_episode')
    require(raw['specification']['case'] == 'mechanism' and raw['specification']['method'] == 'incumbent'
            and raw['specification'].get('fault') is None, 'same_registered_scene')
    require(not raw.get('initial_evaluator_advice') and not raw.get('later_transitions'),
            'explicit_selector_and_original_retained_continuation')
    owners = {}
    for owner in ('A', 'B'):
        initial = raw['initial_owners'][owner]
        selection = initial['selection']
        report = selection['provider_evidence']
        chosen = selection['selected_index']
        queried = selection['accounting']['query_indices']
        expected_k, expected_p = ((4, 2) if owner == 'B' and mode == 'learned' else (1, 1))
        require(selection['selector_mode'] == mode and report['owner'] == owner
                and selection['model_version'] == (model_version if mode == 'learned' else None),
                'actual_selector_mode_and_model')
        require(report['initial_public_sha256'] == initial['collection']['public_sha256']
                and report['actual_collection_at'] == initial['collection']['at']
                and initial['collection']['owner'] == owner, 'same_actual_collection')
        require(report['status'] == 'conditional_forecasts_complete'
                and report['source_binding']['close_completed'] is True
                and report['source_binding']['before_close']['proof_binding']['proof_uses'] == 1 + 2 * expected_k,
                'closed_conditional_provider')
        require(queried == report['requested_indices'] and len(queried) == expected_k and 4 in queried
                and len(set(queried)) == expected_k and chosen in queried
                and report['allocation']['candidate_budget'] == expected_k
                and report['allocation']['prefix_budget'] == expected_p
                and report['evaluated_candidate_count'] == expected_k
                and report['evaluated_prefix_count'] == expected_p
                and report['counts']['future_forks'] == report['counts']['future_resumes'] == expected_k
                and report['counts']['context_constructions'] == expected_p,
                'actual_queried_K_P_budget')
        require(report['public_compatibility_filter']['enabled'] is True
                and set(queried) <= ({4} if owner == 'A' else {0, 1, 4, 5, 8, 9, 12, 13})
                and all(row['status'] == 'not_requested' and row['completion'] is None
                    and row.get('prediction') is None for index, row in enumerate(report['rows']) if index not in queried),
                'public_mask_and_unqueried_rows')
        rows = report['rows']
        require(initial['compatibility']['selected_index'] == chosen
                and selection['allowed_candidate_indices'] == [chosen]
                and strict_equal(initial['selected_action'], selection['selected_action'])
                and strict_equal(initial['selected_action'], rows[chosen]['action'])
                and all(rows[chosen]['completion'][job] <= rows[4]['completion'][job] for job in JOBS),
                'selected_queried_protected_action_reaches_dispatch')
        if owner == 'A' or mode == 'incumbent':
            require(chosen == 4, 'explicit_incumbent04')
        require(initial['immediate_component']['status'] == 'fresh_local_component_proposal'
                and initial['immediate_component']['owner'] == owner
                and initial['immediate_component']['public_sha256'] == initial['collection']['public_sha256']
                and initial['continuation_policy_created'] is True,
                'final_current_guard_and_retained_policy')
        identity = initial['native_request_id']
        calls = [call for call in raw['calls'] if call['request']['request_id'] == identity]
        ack = None
        if owner == 'A':
            require(identity is None and initial['native_default_no_command'] is True and not calls,
                    'A04_no_fabricated_command_or_ACK')
        else:
            require(type(identity) is str and identity and len([call for call in calls if not call['retry']]) == 1,
                    'one_actual_initial_submission')
            request = initial['submission']['request']
            require(all(strict_equal(call['request'], request) for call in calls)
                    and strict_equal(raw['outbox'][identity]['request'], request)
                    and request['earliest_departure'] == initial['selected_action']['empty_departure']
                    and request['owner_id'] == owner and request['tray_id'] == 'E'
                    and request['source'] == 5 and request['destination'] == 1,
                    'actual_transfer_identity_and_selected_departure')
            ack = raw['outbox'][identity].get('ack')
            require(type(ack) is dict and ack.get('status') in ('received', 'rejected')
                    and 0. <= ack['delivered_at'] <= 40., 'actual_delivered_terminal_ACK')
        owners[owner] = {'selected_index': chosen, 'selected_action': copy.deepcopy(initial['selected_action']),
            'queried_indices': list(queried), 'actual_K': expected_k, 'actual_P': expected_p,
            'native_request_id': identity, 'actual_call_count_including_protocol_retries': len(calls),
            'ACK': copy.deepcopy(ack), 'no_command': owner == 'A',
            'current_guard': initial['immediate_component']['status'],
            'conditional_per_job_delta_s': {job: rows[chosen]['completion'][job] - rows[4]['completion'][job] for job in JOBS}}
    completion = raw['summary']['completion']
    require(set(completion) == set(JOBS) and all(type(value) is float and math.isfinite(value) and value >= 0.
            for value in completion.values()), 'five_actual_job_completions')
    return {'status': 'actual_initial_selector_chain_verified', 'mode': mode, 'owners': owners,
        'completion': copy.deepcopy(completion), 'native_business_summary': copy.deepcopy(raw['summary']),
        'native_protection_certified': False, 'multistep_RL_established': False}


def compare_pair(baseline, learned):
    require(strict_equal(baseline['input'], learned['input']), 'paired_native_input_mismatch')
    require(all(raw['summary']['status'] == 'assessed' for raw in (baseline, learned)), 'completed_pair_required')
    before, after = (raw['summary']['completion'] for raw in (baseline, learned))
    require(set(before) == set(after) == set(JOBS) and all(type(value) is float and math.isfinite(value) and value >= 0.
            for vector in (before, after) for value in vector.values()), 'paired_five_completed_jobs')
    delta = {job: after[job] - before[job] for job in JOBS}
    protected = all(value <= 0. for value in delta.values())
    return {'status': 'completed_matched_native_pair', 'same_input_exact': True,
        'baseline_completion': before, 'learned_completion': after, 'per_job_delta_s': delta,
        'completion_sum_delta_s': sum(after.values()) - sum(before.values()),
        'observed_five_job_non_degradation': protected,
        'observed_strict_improvement': protected and any(value < 0. for value in delta.values()),
        'comparison_tolerance_s': 0., 'independent_scene_count': 1,
        'policy_generalization_established': False, 'native_protection_certified': False,
        'complete_request_100ms_certified': False, 'multistep_RL_established': False,
        'scope': 'Actual matched terminal outcomes in one scene, not a universal protection or learning gain certificate.'}


def load_raw(receipt):
    item = receipt['raw_artifact']
    require(sha(item['path']) == item['sha256'], 'native_raw_artifact_binding')
    return json.loads(gzip.decompress(Path(item['path']).read_bytes()))


def worker(output, branch_id, expected_plan_sha):
    output = Path(output).resolve()
    plan = read(output / 'plan.json')
    directory = output / branch_id
    report = {'schema': SCHEMA, 'status': 'unknown_failed', 'branch_id': branch_id,
        'native_execution_attempted': False}
    try:
        require(sha(output / 'plan.json') == expected_plan_sha, 'plan_changed_after_launch')
        check_pins(plan)
        matches = [branch for branch in plan['branches'] if branch['id'] == branch_id]
        require(len(matches) == 1, 'registered_branch_required')
        from . import foundation_initial_selector as selector
        from . import foundation_native_environment as environment
        from . import foundation_ranker as ranker
        validate_model(plan['model']['path'])
        version = ranker.load_model(plan['model_copy']['path'])
        require(version == plan['model_version'], 'frozen_model_version')
        mode = matches[0]['mode']
        choose = selector.make_selector(mode=mode, model_version=version if mode == 'learned' else None)
        report['native_execution_attempted'] = True
        receipt = environment.run_baseline(directory / 'native', case='mechanism', method='incumbent', initial_selector=choose)
        report['native_receipt'] = reference(directory / 'native/receipt.json')
        require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed',
                'native_not_closed')
        report['assessment'] = assess_branch(load_raw(receipt), mode, version)
        report['status'] = 'completed_initial_episode'
    except Exception:
        report['exception'] = traceback.format_exc()
    finally:
        try:
            require(sha(output / 'plan.json') == expected_plan_sha, 'plan_changed_during_worker')
            check_pins(plan)
            report['source_and_model_exit_pins_passed'] = True
        except Exception:
            report.update(status='unknown_source_or_model_changed', pin_exception=traceback.format_exc())
        write_new(directory / 'worker_report.json', report)
    return report


def launch_branch(output, branch, plan, plan_sha):
    directory = output / branch['id']
    directory.mkdir(exist_ok=False)
    write_new(directory / 'launch.json', {'schema': SCHEMA, 'branch': branch,
        'hard_process_seconds': HARD_SECONDS, 'automatic_retries': 0, 'plan': reference(output / 'plan.json')})
    admission = secrets.token_hex(24)
    process, error, child = None, None, None
    try:
        check_pins(plan)
        require(sha(output / 'plan.json') == plan_sha, 'plan_bytes_changed_before_branch')
        with (directory / 'stdout.log').open('x') as stdout, (directory / 'stderr.log').open('x') as stderr:
            process = bounded_windows_job.run([sys.executable, '-m', MODULE, '--worker', '--output', str(output),
                '--branch', branch['id'], '--admission', admission, '--plan-sha256', plan_sha],
                timeout=HARD_SECONDS, stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
        report_path = directory / 'worker_report.json'
        child = read(report_path) if report_path.exists() else None
        require(process['status'] == 'exited' and process['exitcode'] == 0 and child is not None
                and child['status'] == 'completed_initial_episode', 'bounded_process_and_child_completion')
        check_pins(plan)
        require(sha(output / 'plan.json') == plan_sha, 'plan_bytes_changed_during_branch')
        receipt_path = directory / 'native/receipt.json'
        require(child['native_receipt'] == reference(receipt_path), 'native_receipt_binding')
        native = read(receipt_path)
        require(native['status'] == 'assessed' and native['run_acceptance_status'] == 'closed_run_acceptance_passed',
                'native_receipt_not_closed')
        require(strict_equal(child['assessment'], assess_branch(load_raw(native), branch['mode'], plan['model_version'])),
                'recomputed_chain_assessment')
    except Exception:
        error = traceback.format_exc()
    result = {'schema': SCHEMA, 'status': 'completed_initial_episode' if error is None else 'unknown_incomplete_episode',
        'process': process, 'worker_report': reference(directory / 'worker_report.json') if child is not None else None,
        'native_receipt': child.get('native_receipt') if child else None,
        'assessment': child.get('assessment') if child else None, 'exception': error, 'automatic_retries': 0}
    write_new(directory / 'receipt.json', result)
    return result


def launch(output):
    output = Path(output).resolve()
    plan = read(output / 'plan.json')
    plan_sha = sha(output / 'plan.json')
    check_pins(plan)
    write_new(output / 'launch.json', {'schema': SCHEMA, 'plan': reference(output / 'plan.json'),
        'status': 'launching_once', 'automatic_retries': 0, 'ordered_branches': [row['id'] for row in BRANCHES]})
    branches = []
    for branch in plan['branches']:
        try:
            result = launch_branch(output, branch, plan, plan_sha)
        except Exception:
            result = {'status': 'unknown_branch_setup_failure', 'exception': traceback.format_exc()}
        branches.append({'id': branch['id'], **result})
        if result['status'] != 'completed_initial_episode':
            break
    unchanged = (output / 'plan.json').is_file() and sha(output / 'plan.json') == plan_sha
    complete = unchanged and len(branches) == 2 and all(row['status'] == 'completed_initial_episode' for row in branches)
    result = {'schema': SCHEMA, 'status': 'unknown_incomplete_campaign', 'branches': branches,
        'planned_count': 2, 'attempted_count': len(branches), 'independent_scene_count': 1, 'automatic_retries': 0,
        'model': plan['model'], 'original_plan_sha256': plan_sha, 'plan_bytes_unchanged': unchanged,
        'training_performed': False, 'multistep_RL_established': False,
        'native_protection_certified': False, 'complete_request_100ms_certified': False}
    if complete:
        try:
            check_pins(plan)
            raw = [load_raw(read(row['native_receipt']['path'])) for row in branches]
            result['pair'] = compare_pair(*raw)
            result['status'] = 'completed_initial_selector_campaign'
        except Exception:
            result['exception'] = traceback.format_exc()
    write_new(output / 'receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--worker', action='store_true')
    parser.add_argument('--model', type=Path, default=DEFAULT_MODEL)
    parser.add_argument('--branch', choices=[row['id'] for row in BRANCHES])
    parser.add_argument('--admission')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    result = (prepare(args.output, model=args.model) if args.prepare else launch(args.output) if args.launch else
              worker(args.output, args.branch, args.plan_sha256))
    print(json.dumps({'status': result['status'], 'output': str(args.output.resolve())}))
    if args.worker and result['status'] != 'completed_initial_episode':
        raise SystemExit(1)
    if args.launch and result['status'] != 'completed_initial_selector_campaign':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
