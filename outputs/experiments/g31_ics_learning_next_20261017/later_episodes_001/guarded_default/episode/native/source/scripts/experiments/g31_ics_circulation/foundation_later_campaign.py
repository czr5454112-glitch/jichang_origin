"""Fixed small later-choice episodes with separate Windows Job time budgets.

Three interventions are one mechanism scenario, not independent training scenes.
Preparation never runs native. Launch is one-shot, sequential and fail-stop.
"""
from __future__ import annotations

import sys

if __name__ == '__main__' and '--worker' in sys.argv:
    if '--admission' not in sys.argv:
        raise SystemExit('later_campaign:missing_parent_job_admission')
    expected_admission = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != expected_admission:
        raise SystemExit('later_campaign:missing_parent_job_admission')

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import secrets
import time
import traceback

from . import bounded_windows_job

ROOT = Path(__file__).resolve().parents[3]
MODULE = 'scripts.experiments.g31_ics_circulation.foundation_later_campaign'
SCHEMA = 'g31.foundation.later_campaign.v1'
MANIFEST_SCHEMA = 'g31.foundation.later_episode_manifest.v1'
HARD_SECONDS = 150
BRANCHES = (
    {'id': 'guarded_default', 'mode': 'guarded',
     'actions': {'first_return': 'return_now', 'first_reuse_route': 'native_default'}},
    {'id': 'diagnostic_prefer8', 'mode': 'diagnostic_intervention',
     'actions': {'first_return': 'return_now', 'first_reuse_route': 'prefer_8'}},
    {'id': 'diagnostic_absolute_return', 'mode': 'diagnostic_intervention',
     'actions': {'first_return': 'return_not_before_7_84', 'first_reuse_route': 'native_default'}},
)


def require(condition, reason):
    if not condition:
        raise ValueError('later_campaign:' + reason)


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


def source_pins():
    paths = set((ROOT / 'scripts/experiments/g31_ics_circulation').glob('*.py'))
    paths.update((ROOT / 'src/czr005').rglob('*.py'))
    return {str(path.resolve()): sha(path) for path in sorted(paths)}


def check_pins(plan):
    require(plan['schema'] == SCHEMA and plan['hard_process_seconds'] == HARD_SECONDS,
            'frozen_protocol_and_budget')
    expected = list(BRANCHES) if plan['checkpoint'] is None else [
        {'id': 'guarded_learned_value', 'mode': 'guarded', 'actions': None}]
    require(json.dumps(plan['branches'], sort_keys=True) == json.dumps(expected, sort_keys=True)
            and plan['scenario'] == 'mechanism' and plan['horizon'] == 40.
            and plan['method'] == 'incumbent' and plan['automatic_retries'] == 0,
            'fixed_episode_plan_required')
    require(source_pins() == plan['source_sha256'], 'source_set_or_bytes_changed')
    for item in plan['runtime_references']:
        require(sha(item['path']) == item['sha256'], 'runtime_reference_changed:' + item['path'])
    if plan['checkpoint'] is not None:
        require(sha(plan['checkpoint']['path']) == plan['checkpoint']['sha256'], 'checkpoint_changed')


def prepare(output, *, evaluate_checkpoint=None):
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and output != ROOT, 'workspace_output_required')
    require(not output.exists(), 'fresh_output_required')
    contract_path = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014/native027_accepted_contract_001.json'
    contract = read(contract_path)
    checkpoint = None
    if evaluate_checkpoint is not None:
        checkpoint = reference(Path(evaluate_checkpoint).resolve(strict=True))
        require(read(checkpoint['path'])['schema'] == 'g31.foundation.later_value_model.v1',
                'later_value_checkpoint_schema')
    branches = copy.deepcopy(list(BRANCHES)) if checkpoint is None else [
        {'id': 'guarded_learned_value', 'mode': 'guarded', 'actions': None}]
    plan = {'schema': SCHEMA, 'status': 'prepared_not_executed', 'scenario': 'mechanism',
        'horizon': 40., 'method': 'incumbent', 'timing_mode': 'offline_sync',
        'branches': branches, 'hard_process_seconds': HARD_SECONDS, 'automatic_retries': 0,
        'checkpoint': checkpoint, 'source_sha256': source_pins(),
        'runtime_references': [reference(contract_path), reference(contract['binary']), reference(sys.executable)],
        'runtime_python': sys.version, 'independent_scene_count': 1,
        'original_reference_refresh_allowed': False, 'closed_loop_RL_trained': False,
        'native_protection_certified': False, 'complete_request_100ms_certified': False,
        'scope': 'One deterministic mechanism scene; diagnostic interventions are not protected deployment'}
    output.mkdir(parents=True, exist_ok=False)
    write_new(output / 'plan.json', plan)
    check_pins(plan)
    return plan


def choose_fixed(actions, records):
    def choose(observation, candidates):
        started = time.perf_counter_ns()
        expected = actions[observation['phase']]
        matches = [row for row in candidates if row['action_id'] == expected and row['enabled'] is True]
        require(len(matches) == 1, 'fixed_action_disabled_no_fallback:' + expected)
        selected = matches[0]
        records.append({'owner': observation['owner'], 'phase': observation['phase'], 'at': observation['at'],
            'action_id': expected, 'candidate_id': selected['candidate_id'], 'scores': None,
            'inference_wall_ms': (time.perf_counter_ns() - started) / 1e6})
        return selected['candidate_id']
    return choose


def choose_learned(checkpoint, records):
    from . import foundation_later_learning as learning
    model = read(checkpoint['path'])
    require(sha(checkpoint['path']) == checkpoint['sha256'], 'checkpoint_changed_before_inference')
    def choose(observation, candidates):
        started = time.perf_counter_ns()
        enabled = [row for row in candidates if row['enabled'] is True]
        require(bool(enabled), 'no_enabled_learned_candidate')
        scores = [{'candidate_id': row['candidate_id'], 'action_id': row['action_id'],
                   'value_s': learning.predict(model, observation, row['action_id'])} for row in enabled]
        require(all(type(row['value_s']) in (int, float) and math.isfinite(row['value_s']) for row in scores),
                'invalid_learned_score')
        selected = min(scores, key=lambda row: (row['value_s'], row['action_id'], row['candidate_id']))
        records.append({'owner': observation['owner'], 'phase': observation['phase'], 'at': observation['at'],
            'checkpoint_sha256': checkpoint['sha256'], 'scores': scores,
            'action_id': selected['action_id'], 'candidate_id': selected['candidate_id'],
            'inference_wall_ms': (time.perf_counter_ns() - started) / 1e6,
            'information_scope': 'detached_legal_actor_observation_and_enabled_mask_only'})
        return selected['candidate_id']
    return choose


def worker(output, branch_id, expected_plan_sha):
    output = Path(output).resolve()
    plan = read(output / 'plan.json')
    directory = output / branch_id
    report = {'schema': SCHEMA, 'status': 'unknown_failed', 'branch_id': branch_id,
              'selector_calls': [], 'native_execution_attempted': False}
    try:
        require(sha(output / 'plan.json') == expected_plan_sha, 'plan_changed_after_launch')
        check_pins(plan)
        matches = [branch for branch in plan['branches'] if branch['id'] == branch_id]
        require(len(matches) == 1, 'registered_branch_required')
        branch = matches[0]
        from . import foundation_later_episode as episode
        from . import foundation_later_seed as model
        choose = (choose_learned(plan['checkpoint'], report['selector_calls']) if plan['checkpoint']
                  else choose_fixed(branch['actions'], report['selector_calls']))
        report['native_execution_attempted'] = True
        receipt = episode.run_episode(directory / 'episode', choose=choose, model=model,
            mode=branch['mode'], case='mechanism', method='incumbent')
        path = directory / 'episode/native/receipt.json'
        report['native_receipt'] = reference(path)
        require(receipt['status'] == 'assessed'
                and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed', 'native_not_closed')
        summary = read(directory / 'episode/episode.json')
        require(summary['status'] == 'assessed' and summary['transition_count'] == 2
                and summary['actual_effective_count'] == 2, 'two_actual_later_effects_required')
        require([row['phase'] for row in report['selector_calls']] == ['first_return', 'first_reuse_route'],
                'two_chronological_actor_choices_required')
        report['status'] = 'completed_later_episode'
    except Exception:
        report['exception'] = traceback.format_exc()
    finally:
        try:
            require(sha(output / 'plan.json') == expected_plan_sha, 'plan_changed_during_worker')
            check_pins(plan)
            report['source_and_checkpoint_exit_pins_passed'] = True
        except Exception:
            report.update(status='unknown_source_or_checkpoint_changed', pin_exception=traceback.format_exc())
        write_new(directory / 'worker_report.json', report)
    return report


def launch_branch(output, branch, plan, plan_sha):
    directory = output / branch['id']
    directory.mkdir(exist_ok=False)
    write_new(directory / 'launch.json', {'schema': SCHEMA, 'branch': branch,
        'hard_process_seconds': HARD_SECONDS, 'automatic_retries': 0, 'plan': reference(output / 'plan.json')})
    admission = secrets.token_hex(24)
    process = None
    error = None
    try:
        check_pins(plan)
        require(sha(output / 'plan.json') == plan_sha, 'plan_bytes_changed_before_branch')
        require(json.dumps(read(output / 'plan.json'), sort_keys=True) == json.dumps(plan, sort_keys=True),
                'plan_changed_before_branch')
        with (directory / 'stdout.log').open('x') as stdout, (directory / 'stderr.log').open('x') as stderr:
            process = bounded_windows_job.run([sys.executable, '-m', MODULE, '--worker', '--output', str(output),
                '--branch', branch['id'], '--admission', admission, '--plan-sha256', plan_sha], timeout=HARD_SECONDS,
                stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    except Exception:
        error = traceback.format_exc()
    report_path = directory / 'worker_report.json'
    try:
        child = read(report_path) if report_path.exists() else None
    except Exception:
        child = None
        error = traceback.format_exc()
    complete = (error is None and process is not None and process['status'] == 'exited'
                and process['exitcode'] == 0 and child is not None
                and child['status'] == 'completed_later_episode')
    try:
        check_pins(plan)
        require(sha(output / 'plan.json') == plan_sha, 'plan_bytes_changed_during_branch')
        require(json.dumps(read(output / 'plan.json'), sort_keys=True) == json.dumps(plan, sort_keys=True),
                'plan_changed_during_branch')
        if complete:
            receipt_path = directory / 'episode/native/receipt.json'
            require(child['native_receipt'] == reference(receipt_path), 'native_receipt_binding')
            native = read(receipt_path)
            require(native['status'] == 'assessed'
                    and native['run_acceptance_status'] == 'closed_run_acceptance_passed', 'native_receipt_not_closed')
    except Exception:
        complete = False
        error = traceback.format_exc()
    result = {'schema': SCHEMA, 'status': 'completed_later_episode' if complete else 'unknown_incomplete_episode',
        'process': process, 'worker_report': reference(report_path) if child is not None else None,
        'native_receipt': child.get('native_receipt') if child else None,
        'exception': error, 'automatic_retries': 0}
    write_new(directory / 'receipt.json', result)
    return result


def launch(output):
    output = Path(output).resolve()
    plan = read(output / 'plan.json')
    plan_sha = sha(output / 'plan.json')
    check_pins(plan)
    write_new(output / 'launch.json', {'schema': SCHEMA, 'plan': reference(output / 'plan.json'),
        'status': 'launching_once', 'automatic_retries': 0, 'ordered_branches': [row['id'] for row in plan['branches']]})
    branches = []
    for branch in plan['branches']:
        try:
            result = launch_branch(output, branch, plan, plan_sha)
        except Exception:
            result = {'status': 'unknown_branch_setup_failure', 'exception': traceback.format_exc()}
        branches.append({'id': branch['id'], **result})
        if result['status'] != 'completed_later_episode':
            break
    unchanged = (output / 'plan.json').is_file() and sha(output / 'plan.json') == plan_sha
    complete = unchanged and len(branches) == len(plan['branches']) and all(row['status'] == 'completed_later_episode' for row in branches)
    result = {'schema': SCHEMA, 'status': 'completed_later_campaign' if complete else 'unknown_incomplete_campaign',
        'branches': branches, 'planned_count': len(plan['branches']), 'attempted_count': len(branches),
        'independent_scene_count': 1, 'automatic_retries': 0, 'checkpoint': plan['checkpoint'],
        'original_plan_sha256': plan_sha, 'plan_bytes_unchanged': unchanged,
        'closed_loop_RL_trained': False, 'learned_takeover_certified': False, 'quality_improvement_claimed': False,
        'complete_request_100ms_certified': False}
    if complete:
        entries = [{'receipt_path': row['native_receipt']['path'], 'receipt_sha256': row['native_receipt']['sha256']}
                   for row in branches]
        write_new(output / 'episode_manifest.json', {'schema': MANIFEST_SCHEMA, 'episodes': entries,
            'independent_scene_count': 1, 'evaluation_only': plan['checkpoint'] is not None,
            'closed_loop_RL_trained': False, 'diagnostic_interventions_are_not_protected_deployment': True})
        result['manifest'] = reference(output / 'episode_manifest.json')
    write_new(output / 'receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--worker', action='store_true')
    parser.add_argument('--evaluate-checkpoint', type=Path)
    parser.add_argument('--branch')
    parser.add_argument('--admission')
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    require(args.evaluate_checkpoint is None or args.prepare, 'checkpoint_only_at_preparation')
    result = (prepare(args.output, evaluate_checkpoint=args.evaluate_checkpoint) if args.prepare else
              launch(args.output) if args.launch else worker(args.output, args.branch, args.plan_sha256))
    print(json.dumps({'status': result['status'], 'output': str(args.output.resolve())}))
    if args.worker and result['status'] != 'completed_later_episode':
        raise SystemExit(1)
    if args.launch and result['status'] != 'completed_later_campaign':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
