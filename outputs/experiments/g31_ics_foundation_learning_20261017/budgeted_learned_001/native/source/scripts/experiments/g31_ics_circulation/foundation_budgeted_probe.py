"""One bounded, advice-only live-context rule/learned top-K comparison.

Ranking and selective rollouts precede the B full32 teacher. The original
incumbent dispatcher alone acts. Saved comparisons never create authority.
"""
from __future__ import annotations

import sys

if __name__ == '__main__' and '--worker' in sys.argv:
    expected_admission = sys.argv[sys.argv.index('--admission') + 1]
    if sys.stdin.readline().strip() != expected_admission:
        raise SystemExit('foundation_probe:missing_parent_job_admission')

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import secrets
import time
import traceback

from . import bounded_windows_job
from . import foundation_budgeted_provider as provider
from . import foundation_native_environment as environment
from . import foundation_ranker as ranker

SCHEMA = 'g31.foundation.budgeted_live_probe.v1'
ROOT = environment.ROOT
ORDER = ('rule', 'learned')
BUDGET = 8
HARD_SECONDS = 90


def require(condition, reason):
    if not condition:
        raise ValueError('foundation_probe:' + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(provider.teacher.encoding(value).encode()).hexdigest()


def reference(path):
    return {'path': str(Path(path).resolve()), 'sha256': sha(path)}


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n', encoding='utf8')


def shared_rule(observation, candidates, model_version):
    require(model_version == 'shared_semantic_rule_v1', 'rule_version')
    return ranker.rule_scores(observation, candidates)


def validate_model(path):
    path = Path(path).resolve()
    payload = json.loads(path.read_bytes())
    require(payload['schema'] == ranker.MODEL_SCHEMA and payload['feature_schema'] == ranker.data.SCHEMA,
            'model_schema')
    require(payload['kind'] == 'linear' and payload['trained_source_groups'] == ['insufficient_advance', 'no_overlap']
        and payload['validation_or_test_used_for_fit'] is False
        and payload['uses_candidate_index_as_feature'] is False
        and payload['native_execution_authority'] is False, 'heldout_mechanism_linear_model')
    folds = json.loads((path.parent / 'folds.json').read_bytes())
    matches = [fold for fold in folds if fold['held_out_group'] == 'mechanism']
    require(len(matches) == 1 and Path(matches[0]['models']['linear']).resolve() == path
        and matches[0]['training_groups'] == payload['trained_source_groups'], 'frozen_holdout_fold')
    return payload


def make_callback(model_version, output):
    output = Path(output)

    def callback(decision):
        provider.origin.require_current(decision)
        audit = decision.audit_copy()
        if audit['owner'] != 'B':
            return {'status': 'not_scheduled_for_owner_A', 'model_calls': 0, 'native_authority': False}
        result = {'schema': SCHEMA, 'status': 'unknown_unexecuted', 'owner': 'B',
            'public_sha256': audit['public_sha256'], 'at': audit['at'],
            'order': list(ORDER), 'budget_including_incumbent': BUDGET, 'variants': {},
            'full32_teacher_not_available_to_callback': True, 'native_authority': False,
            'dispatch_authorized': False, 'strict_speed_causal_claim': False}
        write(output / 'callback_partial.json', result)
        for kind in ORDER:
            started, cpu_started = time.perf_counter_ns(), time.process_time_ns()
            model = 'shared_semantic_rule_v1' if kind == 'rule' else model_version
            measured = provider.evaluate_budgeted(decision, budget=BUDGET,
                scorer=shared_rule if kind == 'rule' else ranker.score_candidates, model_version=model)
            report = measured.pop('batch').audit_copy()
            provider.origin.require_current(decision)
            require(decision.audit_copy()['public_sha256'] == result['public_sha256'], 'same_live_observation')
            result['variants'][kind] = {**measured, 'report': report,
                'through_export_and_current_check_wall_ms': (time.perf_counter_ns() - started) / 1e6,
                'through_export_and_current_check_cpu_ms': (time.process_time_ns() - cpu_started) / 1e6}
            result['status'] = 'running' if report['status'] == 'conditional_forecasts_complete' else 'unknown_variant'
            write(output / 'callback_partial.json', result)
            require(report['status'] == 'conditional_forecasts_complete', kind + '_incomplete_advice')
        result['status'] = 'complete_advice_only'
        write(output / 'callback_complete.json', result)
        return result

    return callback


def _reference_optima(rows, owner):
    baseline = rows[4]
    protected = [index for index, row in enumerate(rows)
        if provider.compatibility.known(row) and provider.compatibility.known(baseline)
        and all(row['completion'][job] <= baseline['completion'][job] for job in provider.teacher.JOBS)]
    conditional = min(protected, key=lambda index: (
        sum(rows[index]['completion'][job] for job in provider.teacher.JOBS), index)) if protected else None
    selected = provider.compatibility.select_component({
        'selected_index': conditional, 'accounting': {'query_indices': list(range(32))},
        'allowed_candidate_indices': list(range(32)), 'provider_evidence': {'owner': owner, 'rows': rows}}, owner, 4)
    return conditional, selected['selected_index'], protected


def compare_variant(measured, teacher):
    """Pure after-the-fact parity/regret, never a source for pre-rollout ranking."""
    report = measured['report']
    rows = teacher['selection']['provider_evidence']['rows']
    evidence = teacher['selection']['provider_evidence']
    same_context = (report['owner'] == evidence['owner']
        and report['initial_public_sha256'] == evidence['initial_public_sha256']
        and report['actual_collection_at'] == evidence['actual_collection_at'])
    requested = report['requested_indices']
    comparisons = [{
        'candidate_index': index, 'action_exact': report['rows'][index]['action'] == rows[index]['action'],
        'completion_exact': report['rows'][index]['completion'] == rows[index]['completion'],
        'prediction_exact': report['rows'][index].get('prediction') == rows[index].get('prediction'),
        'both_known': provider.compatibility.known(report['rows'][index]) and provider.compatibility.known(rows[index]),
        'budgeted_prediction_sha256': digest(report['rows'][index].get('prediction')),
        'teacher_prediction_sha256': digest(rows[index].get('prediction'))} for index in requested]
    parity = same_context and bool(requested) and all(all(row[field] for field in (
        'action_exact', 'completion_exact', 'prediction_exact', 'both_known')) for row in comparisons)
    conditional, compatible, protected = _reference_optima(rows, report['owner'])
    full_known = all(provider.compatibility.known(row) for row in rows)
    selected = report.get('selection', {}).get('selected_index')

    def cost(index):
        return sum(rows[index]['completion'][job] for job in provider.teacher.JOBS)

    admissible = [index for index in requested if index in protected]
    best = min(admissible, key=lambda index: (cost(index), index)) if admissible else None
    reference_known = full_known and parity and conditional is not None and compatible is not None
    selected_known = (reference_known and selected is not None and selected in requested
        and selected in protected and provider.compatibility.known(report['rows'][selected]))
    selected_compatible = selected_known and all(rows[selected]['action'][field] == rows[4]['action'][field]
        for field in provider.compatibility.OWNER_FIELDS['A'])
    current = report.get('selection', {}).get('current_revalidation', {})
    closed = report['source_binding'].get('close_completed') is True
    proof_uses = report['source_binding'].get('before_close', {}).get('proof_binding', {}).get('proof_uses')
    return {'status': 'same_context_exact_requested_predictions' if parity and closed else 'unknown_or_mismatched_predictions',
        'same_context': same_context, 'all_requested_prediction_parity': parity, 'comparisons': comparisons,
        'requested_indices': requested, 'budget_including_incumbent': report['candidate_budget'],
        'counts': report['counts'], 'teacher_counts': evidence['counts'], 'closed_source_binding': closed,
        'source_proof_uses': proof_uses, 'expected_proof_uses': 1 + 2 * len(requested),
        'unrequested_rows_not_evaluated': all(row['status'] == 'not_requested' and row.get('prediction') is None
            and row['completion'] is None for index, row in enumerate(report['rows']) if index not in requested),
        'selected_compatible_index': selected,
        'selected_strictly_protected_and_component_compatible': selected_compatible,
        'selected_per_job_delta_s': {job: report['rows'][selected]['completion'][job] - rows[4]['completion'][job]
            for job in provider.teacher.JOBS} if selected_known else None,
        'fresh_local_revalidation': current.get('status') == 'fresh_local_component_proposal',
        'full32_reference_known': reference_known,
        'full32_conditional_optimum_index': conditional if reference_known else None,
        'full32_component_compatible_optimum_index': compatible if reference_known else None,
        'conditional_optimum_retained': any(cost(index) == cost(conditional) for index in admissible) if reference_known else None,
        'conditional_protected_regret_s': cost(best) - cost(conditional) if reference_known and best is not None else None,
        'component_compatible_regret_s': cost(selected) - cost(compatible) if selected_compatible else None,
        'costs': {'budgeted_through_seal_wall_ms': measured['compute_wall_ms'],
            'budgeted_seal_wall_ms': measured['seal_wall_ms'],
            'budgeted_export_wall_ms': measured.get('through_export_and_current_check_wall_ms',
                measured.get('diagnostic_through_export_wall_ms')),
            'budgeted_export_cpu_ms': measured.get('through_export_and_current_check_cpu_ms'),
            'teacher_through_seal_wall_ms': teacher['selection']['accounting']['provider_measured_through_seal_seconds'] * 1000,
            'budgeted_exclusive_outer_stage_ns': report['timing']['exclusive_outer_stage_ns']},
        'strict_speed_causal_claim': False, 'native_policy_gain_measured': False,
        'native_authority': False, 'complete_request_100ms_certified': False,
        'scope': 'Fixed order, one live context. Conditional joint regret and publicly compatible regret are distinct; neither is measured native policy gain.'}


def prepare(output, model):
    output, model = Path(output).resolve(), Path(model).resolve()
    require(not output.exists(), 'fresh_output_required')
    payload = validate_model(model)
    output.mkdir(parents=True)
    sources = set(environment.online.old.bound.imported_sources()) | {Path(__file__).resolve()}
    source_pins = {}
    for path in sorted(sources):
        target = output / 'source' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        source_pins[str(path)] = sha(path)
    model_copy = output / 'model.json'
    model_copy.write_bytes(model.read_bytes())
    plan = {'schema': SCHEMA, 'status': 'prepared_unexecuted', 'model': reference(model),
        'model_copy': reference(model_copy), 'model_version': payload['model_version'],
        'folds': reference(model.parent / 'folds.json'),
        'training_registration': reference(model.parent / 'registration.json'),
        'source_sha256': source_pins, 'order': list(ORDER), 'budget_including_incumbent': BUDGET,
        'incumbent_index': 4, 'case': 'mechanism', 'method': 'incumbent', 'owner': 'B',
        'native_sessions': 1, 'hard_process_seconds': HARD_SECONDS, 'automatic_retries': 0,
        'teacher_order': 'B rule K8 then learned K8 then unchanged B full32',
        'model_preload_before_source_binding': True, 'first_owner_A_full32_precedes_B_callback': True,
        'native_authority': False, 'strict_speed_causal_claim': False, 'dispatch_changed': False,
        'scope': 'One heldout-context smoke, no learned controller deployment or generalization claim.'}
    write(output / 'plan.json', plan)
    return plan


def check_pins(plan):
    for path, expected in plan['source_sha256'].items():
        require(sha(path) == expected, 'frozen_source:' + path)
    for key in ('model', 'model_copy', 'folds', 'training_registration'):
        require(sha(plan[key]['path']) == plan[key]['sha256'], 'frozen_' + key)


def worker(output):
    output = Path(output).resolve()
    plan = json.loads((output / 'plan.json').read_bytes())
    require(plan['schema'] == SCHEMA and plan['hard_process_seconds'] == HARD_SECONDS
        and plan['order'] == list(ORDER) and plan['budget_including_incumbent'] == BUDGET, 'frozen_protocol')
    report = {'schema': SCHEMA, 'status': 'unknown_failed', 'plan': reference(output / 'plan.json')}
    try:
        check_pins(plan)
        validate_model(plan['model']['path'])
        version = ranker.load_model(plan['model_copy']['path'])
        require(version == plan['model_version'], 'frozen_model_version')
        receipt = environment.run_baseline(output / 'native', initial_evaluator=make_callback(version, output))
        report['native_receipt'] = reference(output / 'native/receipt.json')
        require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed', 'native_closed')
        raw = json.loads(gzip.decompress(Path(receipt['raw_artifact']['path']).read_bytes()))
        callback = raw['initial_evaluator_advice']['B']
        report.update(variants={kind: compare_variant(callback['variants'][kind], raw['initial_owners']['B']) for kind in ORDER},
            native_trajectory_comparison=raw['saved_baseline_comparison'], order=callback['order'],
            native_raw_artifact=receipt['raw_artifact'], native_policy_gain_measured=False,
            native_authority=False, complete_request_100ms_certified=False)
        require(all(row['status'] == 'same_context_exact_requested_predictions'
            and row['unrequested_rows_not_evaluated'] and row['source_proof_uses'] == row['expected_proof_uses']
            and row['fresh_local_revalidation'] and row['selected_strictly_protected_and_component_compatible']
            and len(row['requested_indices']) == BUDGET and row['counts']['future_resumes'] == BUDGET
            for row in report['variants'].values()), 'requested_semantics_and_guards')
        check_pins(plan)
        report['status'] = 'complete_advice_only_same_context_probe'
    except Exception:
        report['exception'] = traceback.format_exc()
    finally:
        try:
            check_pins(plan)
            report['source_and_model_exit_pins_passed'] = True
        except Exception:
            report.update(status='unknown_source_or_model_changed', pin_exception=traceback.format_exc())
        write(output / 'worker_report.json', report)
    return report


def launch(output):
    output = Path(output).resolve()
    plan_path = output / 'plan.json'
    plan = json.loads(plan_path.read_bytes())
    require(not (output / 'launch.json').exists(), 'one_launch_only')
    check_pins(plan)
    admission = secrets.token_hex(24)
    write(output / 'launch.json', {'plan': reference(plan_path), 'status': 'launching_once',
        'hard_process_seconds': HARD_SECONDS, 'automatic_retries': 0})
    with (output / 'stdout.log').open('w') as stdout, (output / 'stderr.log').open('w') as stderr:
        process = bounded_windows_job.run([sys.executable, '-m', __name__ if __name__ != '__main__'
            else 'scripts.experiments.g31_ics_circulation.foundation_budgeted_probe',
            '--worker', '--output', str(output), '--admission', admission],
            timeout=HARD_SECONDS, stdout=stdout, stderr=stderr, admission=admission, cwd=ROOT)
    worker_path = output / 'worker_report.json'
    child = json.loads(worker_path.read_bytes()) if worker_path.exists() else None
    complete = process['status'] == 'exited' and process['exitcode'] == 0 and child is not None
    complete = complete and child['status'] == 'complete_advice_only_same_context_probe'
    result = {'schema': SCHEMA, 'status': 'complete_advice_only_same_context_probe' if complete else 'unknown_incomplete_probe',
        'process': process, 'worker_status': child['status'] if child is not None else 'missing',
        'worker_report': reference(worker_path) if worker_path.exists() else None,
        'automatic_retries': 0, 'native_authority': False, 'complete_request_100ms_certified': False}
    write(output / 'receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare', action='store_true')
    mode.add_argument('--launch', action='store_true')
    mode.add_argument('--worker', action='store_true')
    parser.add_argument('--admission')
    args = parser.parse_args()
    if args.prepare:
        require(args.model is not None, 'model_required')
        result = prepare(args.output, args.model)
    elif args.launch:
        result = launch(args.output)
    else:
        result = worker(args.output)
    print(json.dumps({'status': result['status'], 'output': str(args.output.resolve())}))


if __name__ == '__main__':
    main()
