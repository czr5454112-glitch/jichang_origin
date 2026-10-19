"""Predeclared compatible-domain quality probe, never a native action policy."""
from __future__ import annotations

import sys

if __name__ == '__main__' and '--worker' in sys.argv:
    expected_admission = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != expected_admission:
        raise SystemExit('compatible_probe:missing_parent_job_admission')

import argparse
import gzip
import json
from pathlib import Path
import secrets
import time
import traceback

from . import foundation_budgeted_probe as previous

provider = previous.provider
ranker = previous.ranker
environment = previous.environment
ROOT = environment.ROOT
SCHEMA = 'g31.foundation.compatible_prefix_budget_probe.v1'
ORDER = ('compatible8', 'rule4', 'prefix_cost4', 'linear4', 'mlp4')
HARD_SECONDS = 150
COMPATIBLE_B = (0, 1, 4, 5, 8, 9, 12, 13)


def require(value, reason):
    if not value:
        raise ValueError('compatible_probe:' + reason)


def variant_specifications():
    return {kind: {'candidate_budget': 8 if kind == 'compatible8' else 4,
        'prefix_budget': 4 if kind == 'compatible8' else 2,
        'ranking_policy': 'marginal_prefix_cost' if kind == 'prefix_cost4' else 'score',
        'model_kind': kind[:-1] if kind in ('linear4', 'mlp4') else None,
        'explicit_compatible_exhaustive': kind == 'compatible8'} for kind in ORDER}


def validate_models(model_dir):
    model_dir = Path(model_dir).resolve()
    folds = json.loads((model_dir / 'folds.json').read_bytes())
    heldout = [fold for fold in folds if fold['held_out_group'] == 'mechanism']
    require(len(heldout) == 1 and heldout[0]['training_groups'] == ['insufficient_advance', 'no_overlap'],
        'mechanism_heldout_fold')
    result = {}
    for kind in ('linear', 'mlp'):
        path = model_dir / (kind + '_holdout_mechanism.json')
        payload = json.loads(path.read_bytes())
        require(payload['schema'] == ranker.MODEL_SCHEMA and payload['feature_schema'] == ranker.data.SCHEMA
            and payload['kind'] == kind and payload['trained_source_groups'] == heldout[0]['training_groups']
            and payload['validation_or_test_used_for_fit'] is False
            and payload['uses_candidate_index_as_feature'] is False
            and payload['native_execution_authority'] is False
            and payload['score_direction'] == 'higher_is_better_negative_predicted_delta'
            and Path(heldout[0]['models'][kind]).resolve() == path, 'frozen_heldout_' + kind)
        result[kind] = {'reference': previous.reference(path), 'version': payload['model_version']}
    return result


def make_callback(versions, output):
    output = Path(output)
    specifications = variant_specifications()

    def callback(decision):
        provider.origin.require_current(decision)
        audit = decision.audit_copy()
        if audit['owner'] != 'B':
            return {'status': 'not_scheduled_for_owner_A', 'native_authority': False, 'model_calls': 0}
        result = {'schema': SCHEMA, 'status': 'unknown_unexecuted', 'owner': 'B',
            'public_sha256': audit['public_sha256'], 'at': audit['at'], 'order': list(ORDER), 'variants': {},
            'specifications': specifications, 'teacher_available_to_actor': False,
            'native_authority': False, 'dispatch_authorized': False, 'speed_superiority_claim': False}
        previous.write(output / 'callback_partial.json', result)
        for kind in ORDER:
            specification = specifications[kind]
            started, cpu_started = time.perf_counter_ns(), time.process_time_ns()
            kwargs = {'budget': specification['candidate_budget'], 'prefix_budget': specification['prefix_budget'],
                'ranking_policy': specification['ranking_policy'], 'compatible_only': True}
            if specification['explicit_compatible_exhaustive']:
                kwargs['candidate_indices'] = list(COMPATIBLE_B)
            elif specification['model_kind'] is not None:
                kwargs.update(scorer=ranker.score_candidates, model_version=versions[specification['model_kind']])
            else:
                kwargs.update(scorer=previous.shared_rule, model_version='shared_semantic_rule_v1')
            measured = provider.evaluate_budgeted(decision, **kwargs)
            report = measured.pop('batch').audit_copy()
            provider.origin.require_current(decision)
            require(previous.strict_equal(decision.audit_copy()['public_sha256'], result['public_sha256']),
                'unchanged_live_context')
            measured.update(report=report,
                through_export_and_current_check_wall_ms=(time.perf_counter_ns() - started) / 1e6,
                through_export_and_current_check_cpu_ms=(time.process_time_ns() - cpu_started) / 1e6)
            result['variants'][kind] = measured
            result['status'] = 'running' if report['status'] == 'conditional_forecasts_complete' else 'unknown_variant'
            previous.write(output / 'callback_partial.json', result)
            require(report['status'] == 'conditional_forecasts_complete', 'incomplete_' + kind)
        result['status'] = 'complete_advice_only'
        previous.write(output / 'callback_complete.json', result)
        return result

    return callback


def assess_variants(callback, teacher):
    specifications = variant_specifications()
    require(callback['order'] == list(ORDER) and set(callback['variants']) == set(ORDER), 'fixed_five_variants')
    assessed = {}
    for kind in ORDER:
        measured = callback['variants'][kind]
        report = measured['report']
        specification = specifications[kind]
        comparison = previous.compare_variant(measured, teacher)
        allocation = report['allocation']
        requested = comparison['requested_indices']
        comparison.update(allocation=allocation, public_compatibility_filter=report['public_compatibility_filter'],
            actual_prefix_count=report['evaluated_prefix_count'], total_domain_not_requested=32 - len(requested),
            legal_domain_not_requested=len(COMPATIBLE_B) - len(requested))
        comparison['declared_budgets_and_structure_passed'] = (
            allocation['legal_domain_size'] == len(COMPATIBLE_B)
            and allocation['eligible_candidate_indices'] == list(COMPATIBLE_B)
            and report['public_compatibility_filter']['enabled'] is True
            and allocation['candidate_budget'] == specification['candidate_budget']
            and allocation['prefix_budget'] == specification['prefix_budget']
            and allocation['ranking_policy'] == specification['ranking_policy']
            and allocation['scoring_row_count'] == (0 if kind == 'compatible8' else len(COMPATIBLE_B))
            and len(requested) == specification['candidate_budget'] and 4 in requested
            and set(requested) <= set(COMPATIBLE_B)
            and allocation['requested_prefix_count'] == specification['prefix_budget']
            and report['evaluated_prefix_count'] == specification['prefix_budget']
            and report['counts']['context_constructions'] == specification['prefix_budget']
            and report['counts']['future_forks'] == report['counts']['future_resumes'] == len(requested)
            and comparison['source_proof_uses'] == 1 + 2 * len(requested))
        comparison['variant_passed'] = (comparison['declared_budgets_and_structure_passed']
            and comparison['status'] == 'same_context_exact_requested_predictions'
            and comparison['unrequested_rows_not_evaluated'] and comparison['fresh_local_revalidation']
            and comparison['selected_strictly_protected_and_component_compatible'])
        assessed[kind] = comparison
    return {'variants': assessed, 'all_variants_passed': all(row['variant_passed'] for row in assessed.values()),
        'compatible8_selected_index': assessed['compatible8']['selected_compatible_index'],
        'compatible8_regret_s': assessed['compatible8']['component_compatible_regret_s'],
        'speed_superiority_claim': False, 'native_learning_gain_measured': False,
        'quality_scope': 'One current B context, fixed predeclared methods and models. No retuning or model selection after results.'}


def check_pins(plan):
    for path, expected in plan['source_sha256'].items():
        require(previous.sha(path) == expected, 'source_changed:' + path)
    for artifact in plan['artifact_pins']:
        require(previous.sha(artifact['path']) == artifact['sha256'], 'artifact_changed:' + artifact['path'])


def prepare(output, model_dir):
    output, model_dir = Path(output).resolve(), Path(model_dir).resolve()
    require(not output.exists(), 'fresh_output_required')
    models = validate_models(model_dir)
    output.mkdir(parents=True)
    source_pins = {}
    sources = set(environment.online.old.bound.imported_sources()) | {Path(__file__).resolve()}
    for path in sorted(sources):
        archive = output / 'source' / path.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(path.read_bytes())
        source_pins[str(path)] = previous.sha(path)
    artifacts = []
    for kind, model in models.items():
        original = Path(model['reference']['path'])
        target = output / (kind + '_model.json')
        target.write_bytes(original.read_bytes())
        model['copy'] = previous.reference(target)
        artifacts.extend((model['reference'], model['copy']))
    artifacts.extend(previous.reference(model_dir / filename) for filename in ('folds.json', 'registration.json'))
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'models': models,
        'artifact_pins': artifacts, 'source_sha256': source_pins, 'model_dir': str(model_dir),
        'order': list(ORDER), 'specifications': variant_specifications(), 'hard_process_seconds': HARD_SECONDS,
        'native_sessions': 1, 'automatic_retries': 0, 'case': 'mechanism', 'method': 'incumbent', 'owner': 'B',
        'compatible_domain': list(COMPATIBLE_B), 'teacher_order': 'A original full32; five B advice variants; B original full32',
        'candidate_and_prefix_budgets_are_separate': True,
        'candidate_budget_is_upper_bound_not_forced_when_domain_is_smaller': True,
        'marginal_cost_rule': 'new prefix = 1 unit, suffix = 1 unit; minimize incremental units, then shared rule score, then index',
        'cost_units_are_not_ms': True, 'speed_superiority_claim': False, 'native_authority': False,
        'budget_rationale': 'Prior native plus two K8 advice took 65.891s. Five independently bound advice calls reserve 150s once, without retry escalation.'}
    previous.write(output / 'plan.json', plan)
    return plan


def worker(output, plan_sha256):
    output = Path(output).resolve()
    plan_path = output / 'plan.json'
    require(previous.sha(plan_path) == plan_sha256, 'parent_frozen_plan')
    plan = json.loads(plan_path.read_bytes())
    require(plan['schema'] == SCHEMA and plan['order'] == list(ORDER)
        and plan['specifications'] == variant_specifications() and plan['hard_process_seconds'] == HARD_SECONDS
        and plan['native_sessions'] == 1 and plan['case'] == 'mechanism' and plan['method'] == 'incumbent',
        'fixed_protocol')
    require(not (output / 'worker_entry.json').exists(), 'one_worker_only')
    previous.write(output / 'worker_entry.json', {'plan_sha256': plan_sha256, 'status': 'entered_once'})
    result = {'schema': SCHEMA, 'status': 'unknown_failed', 'plan': previous.reference(plan_path)}
    try:
        check_pins(plan)
        validate_models(plan['model_dir'])
        versions = {kind: ranker.load_model(model['copy']['path']) for kind, model in plan['models'].items()}
        require(all(versions[kind] == model['version'] for kind, model in plan['models'].items()), 'frozen_model_versions')
        receipt = environment.run_baseline(output / 'native', initial_evaluator=make_callback(versions, output))
        result['native_receipt'] = previous.reference(output / 'native/receipt.json')
        require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed',
            'closed_native_baseline')
        require(previous.sha(receipt['raw_artifact']['path']) == receipt['raw_artifact']['sha256'], 'native_raw_pin')
        raw = json.loads(gzip.decompress(Path(receipt['raw_artifact']['path']).read_bytes()))
        result.update(assess_variants(raw['initial_evaluator_advice']['B'], raw['initial_owners']['B']))
        result.update(native_raw_artifact=receipt['raw_artifact'], native_trajectory_comparison=raw['saved_baseline_comparison'],
            native_authority=False, complete_request_100ms_certified=False)
        require(result['all_variants_passed'], 'strict_requested_parity_and_budget_guards')
        result['status'] = 'complete_compatible_domain_advice_probe'
    except Exception:
        result['exception'] = traceback.format_exc()
    finally:
        try:
            check_pins(plan)
            require(previous.sha(plan_path) == plan_sha256, 'unchanged_plan_at_exit')
            result['source_model_plan_exit_pins_passed'] = True
        except Exception:
            result.update(status='unknown_changed_evidence', pin_exception=traceback.format_exc())
        previous.write(output / 'worker_report.json', result)
    return result


def launch(output):
    output = Path(output).resolve()
    plan_path = output / 'plan.json'
    plan = json.loads(plan_path.read_bytes())
    require(not (output / 'launch.json').exists(), 'one_launch_only')
    check_pins(plan)
    plan_sha = previous.sha(plan_path)
    admission = secrets.token_hex(24)
    previous.write(output / 'launch.json', {'status': 'launching_once', 'plan': previous.reference(plan_path),
        'hard_process_seconds': HARD_SECONDS, 'automatic_retries': 0})
    with (output / 'stdout.log').open('w') as stdout, (output / 'stderr.log').open('w') as stderr:
        process = previous.bounded_windows_job.run([sys.executable, '-m',
            'scripts.experiments.g31_ics_circulation.foundation_compatible_probe', '--worker', '--output', str(output),
            '--plan-sha256', plan_sha, '--admission', admission], timeout=HARD_SECONDS,
            stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    child_path = output / 'worker_report.json'
    child = json.loads(child_path.read_bytes()) if child_path.exists() else None
    complete = (process['status'] == 'exited' and process['exitcode'] == 0 and child is not None
        and child['status'] == 'complete_compatible_domain_advice_probe')
    result = {'schema': SCHEMA, 'status': 'complete_compatible_domain_advice_probe' if complete else 'unknown_incomplete_probe',
        'process': process, 'worker_status': child['status'] if child is not None else 'missing',
        'worker_report': previous.reference(child_path) if child_path.exists() else None,
        'automatic_retries': 0, 'native_authority': False, 'complete_request_100ms_certified': False}
    try:
        check_pins(plan)
        require(previous.sha(plan_path) == plan_sha, 'parent_exit_plan')
        result['parent_exit_pins_passed'] = True
    except Exception:
        result.update(status='unknown_changed_evidence', pin_exception=traceback.format_exc())
    previous.write(output / 'receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model-dir', type=Path)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--admission')
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--launch', action='store_true')
    modes.add_argument('--worker', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        require(args.model_dir is not None, 'model_directory_required')
        result = prepare(args.output, args.model_dir)
    elif args.launch:
        result = launch(args.output)
    else:
        result = worker(args.output, args.plan_sha256)
    print(json.dumps({'status': result['status'], 'output': str(args.output.resolve())}))


if __name__ == '__main__':
    main()
