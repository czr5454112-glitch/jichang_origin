"""Registered supervision from complete conditional forecasts on real captures.

Labels are frozen conditional-model predictions, never actual native returns or
Bellman targets. This module imports no native controller or conditional engine:
it reads closed, archived native runs and never generates replacement labels.
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

from . import foundation_repeated_value as value

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL_SCHEMA = 'g31.foundation.repeated_supervised_protocol.v1'
PLAN_SCHEMA = 'g31.foundation.repeated_supervised_plan.v1'
ROW_SCHEMA = 'g31.foundation.repeated_conditional_supervision.v1'
TRAIN_CASE = 'three_reuse_blocker_11_1'
DEVELOPMENT_CASE = 'four_reuse_blocker_12_5'
FORMAL_TEST_CASE = 'three_reuse_blocker_12_1'
require, number, digest = value.require, value.number, value.digest


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def write_new(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8') as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def protocol():
    return {'schema': PROTOCOL_SCHEMA, 'train_cases': [TRAIN_CASE], 'development_cases': [DEVELOPMENT_CASE],
        'formal_test_cases_reserved_not_read': [FORMAL_TEST_CASE], 'seeds': [1701, 1702, 1703],
        'epochs': 200, 'per_seed_wall_seconds': 45., 'total_wall_seconds': 180., 'cpu_threads': 1,
        'architecture': [64, 64], 'optimizer': {'kind': 'Adam', 'learning_rate': .01, 'weight_decay': 1e-4},
        'target': 'negative_sum_max_zero_conditional_completion_minus_current_observation_time',
        'label_kind': 'frozen_full_job_conditional_model_prediction_on_actual_native_delivered_evidence',
        'model_selection': 'report_all_three_seeds_no_development_selection_no_formal_test_access',
        'deployment_seed_if_needed': 1701, 'native_branches': 0,
        'parent_group_unit': 'registered_input_case_not_action_or_decision',
        'scope': 'supervised_conditional_model_distillation_not_actual_return_training_not_RL'}


def source_pins():
    return {str(path.resolve()): sha(path) for path in (Path(__file__), Path(value.__file__))}


def reference(path):
    path = Path(path).resolve()
    return {'path': str(path), 'sha256': sha(path)}


def closed_native_source(directory, *, case):
    """Read only predeclared train/development cases, with archived source pins."""
    require(case in (TRAIN_CASE, DEVELOPMENT_CASE), 'formal_test_or_unregistered_source_forbidden')
    directory = Path(directory).resolve()
    require(directory.is_relative_to(ROOT), 'workspace_native_source')
    paths = {name: directory / name for name in ('receipt.json', 'worker_report.json', 'acceptance.json', 'plan.json', 'raw.json.gz')}
    receipt, report, accepted, plan = (read(paths[name]) for name in ('receipt.json', 'worker_report.json', 'acceptance.json', 'plan.json'))
    key = case + '/guarded'
    require(plan['schema'] == 'g31.foundation.repeated_campaign.v1' and plan['branch_order'] == [key]
        and plan['rows'][key]['case'] == case and plan['rows'][key]['mode'] == 'guarded', 'registered_guarded_case_before_raw_read')
    require(receipt['status'] == report['status'] == 'completed_native_branch'
        and receipt['worker_report'] == reference(paths['worker_report.json'])
        and receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
        and receipt['process']['windows_job_kill_on_close'] is True
        and receipt['process']['child_released_only_after_job_assignment'] is True, 'closed_bounded_native_process')
    require(report['raw'] == reference(paths['raw.json.gz']) and report['source_exit_pins_passed'] is True
        and report['run_acceptance_status'] == accepted['status'] == 'closed_run_acceptance_passed'
        and accepted['active'] is False and accepted['invalid'] == []
        and accepted['run_reference'] == reference(paths['plan.json']) and accepted['branch_keys'] == [key],
        'closed_native_acceptance_binding')
    raw = json.loads(gzip.decompress(paths['raw.json.gz'].read_bytes()))
    require(raw['schema'] == 'g31.foundation.repeated_native.v1' and raw['specification'] == plan['rows'][key]
        and raw['summary'] == report['summary'] and raw['summary']['status'] == 'assessed'
        and raw['summary']['business_complete'] is True and raw['summary']['audit']['status'] == 'passed',
        'complete_actual_guarded_source')
    require(digest(raw['input']) == raw['specification']['domain']['input_sha256'], 'native_input_identity')
    input_path = directory / 'inputs' / (key + '.json')
    require(sha(input_path) == plan['input_file_sha256'][key] and read(input_path) == raw['input'], 'registered_native_input_file')
    require(set(plan['source_archive']) == set(plan['source_sha256']), 'complete_native_source_archives')
    for original, relative in plan['source_archive'].items():
        archived = (directory / relative).resolve()
        require(archived.is_relative_to(directory) and sha(archived) == plan['source_sha256'][original]
            and accepted['evidence_sha256'].get(original) == plan['source_sha256'][original], 'native_historical_source_archive')
    provenance = plan['original_reference_provenance']
    require(type(provenance) is dict and set(provenance) == {'raw', 'worker_report', 'receipt', 'acceptance', 'plan'},
        'frozen_original_baseline_provenance')
    for bound in provenance.values():
        require(reference(bound['path']) == bound, 'frozen_original_baseline_file')
    baseline_plan = read(provenance['plan']['path'])
    require(baseline_plan['branch_order'] == [case + '/baseline'], 'same_case_baseline_before_result_read')
    require(plan['original_reference'] == provenance['raw'], 'baseline_raw_reference')
    baseline = json.loads(gzip.decompress(Path(provenance['raw']['path']).read_bytes()))
    require(baseline['input'] == raw['input'] and baseline['specification'] == baseline_plan['rows'][case + '/baseline']
        and baseline['summary']['status'] == 'assessed' and baseline['summary']['business_complete'] is True
        and raw['specification']['reference'] == {'completion': baseline['summary']['completion'],
            'input_sha256': digest(raw['input']), 'reference_refresh_allowed': False,
            'kind': 'frozen_paired_actual_baseline', 'actor_access': False}, 'original_baseline_not_silently_reset')
    return raw, {name: reference(path) for name, path in paths.items()}


def make_plan(train_directory, development_directory, protocol_path):
    protocol_path = Path(protocol_path).resolve()
    require(read(protocol_path) == protocol(), 'predeclared_supervised_protocol')
    sources = []
    for split, case, directory in (('train', TRAIN_CASE, train_directory),
        ('development', DEVELOPMENT_CASE, development_directory)):
        raw, binding = closed_native_source(directory, case=case)
        sources.append({'split': split, 'case': case, 'directory': str(Path(directory).resolve()), 'bindings': binding,
            'input_sha256': digest(raw['input'])})
    return {'schema': PLAN_SCHEMA, 'protocol': protocol(), 'protocol_reference': reference(protocol_path),
        'source_sha256_pins': source_pins(), 'sources': sources, 'native_branches': 0}


def complete_prediction(prediction, *, identities, prefix, jobs, now, horizon, model_version):
    require(prediction['status'] == 'conditional_prediction' and prediction['online_executable'] is False
        and prediction['native_protection_certified'] is False and prediction['model_version'] == model_version,
        'complete_conditional_prediction_without_authority')
    completion = prediction['completion']
    require(type(completion) is dict and set(completion) == set(identities), 'full_job_completion_vector_required')
    for identity, completed_at in completion.items():
        require(number(jobs[identity]['arrival']) <= number(completed_at) <= horizon, 'finite_uncensored_predicted_completion')
        if identity in prefix:
            require(completed_at == prefix[identity] and completed_at <= now, 'preserved_observed_completed_prefix')
        else:
            require(completed_at >= now, 'future_prediction_after_current_seed')
    return -math.fsum(max(0., completed_at - now) for completed_at in completion.values())


def _public_messages(envelopes, owner, now):
    result = []
    for envelope in envelopes:
        local = envelope['capture']['capture_v2']['local_capture']
        require(local['target_owner'] == owner and local['source_owner'] != owner
            and envelope['delivered_at'] <= now, 'received_public_capture_scope')
        result.append({'envelope': envelope, **{name: local[name] for name in (
            'message_id', 'source_owner', 'target_owner', 'captured_at', 'valid_until')},
            'status': envelope['status'], 'delivered_at': envelope['delivered_at'],
            'fresh': envelope['status'] == 'conditional' and local['captured_at'] <= now < local['valid_until']})
    return result


def extract_rows(raw, *, split, case, origin):
    """Consume archived reports only; unknown/partial reports never become labels."""
    require((split, case) in (('train', TRAIN_CASE), ('development', DEVELOPMENT_CASE)), 'registered_parent_split')
    require(raw['specification']['case'] == case and raw['specification']['mode'] == 'guarded', 'guarded_source_case')
    require(raw['specification']['domain']['input_sha256'] == digest(raw['input']), 'source_input_binding')
    identities = set(raw['specification']['domain']['business_ids'])
    expected_count = 6 if split == 'train' else 7
    require(len(identities) == expected_count and identities == {job['business_bag_id'] for job in raw['input']['jobs']},
        'complete_registered_source_population')
    attempts = [attempt for group in raw['repeated_attempts'].values() for attempt in group]
    rows, exclusions = [], []
    for decision in raw['repeated_decisions']:
        admission = decision['current_admission']
        if not admission.get('fresh_collection'):
            exclusions.append({'decision_id': decision['decision_id'], 'reason': 'no_current_conditional_collection'})
            continue
        try:
            observed, now = decision['observation'], number(decision['selected_at'])
            require(observed['owner'] == decision['owner'] and observed['at'] == now
                and admission['at'] == now, 'decision_observation_epoch')
            matching = [attempt for attempt in attempts if digest(attempt['evidence']) == admission['evidence_sha256']]
            require(len(matching) == 1, 'one_exact_current_evidence_binding')
            evidence, report = matching[0]['evidence'], matching[0]['model_report']
            require(evidence['owner'] == observed['owner'] and evidence['at'] == now
                and evidence['phase'] == 'cycle_route', 'evidence_owner_phase_epoch')
            require(report['status'] == 'conditional_current_seed' and report['execution_authority'] is False,
                'known_full_candidate_report_required')
            seed = report['seed']
            require(seed['evidence_sha256'] == digest(evidence) and seed['seed_sha256'] == digest({key: val
                for key, val in seed.items() if key != 'seed_sha256'}), 'frozen_seed_evidence_binding')
            require(seed['status'] == 'conditional_current_seed' and seed['owner'] == observed['owner']
                and seed['at'] == now and seed['phase'] == evidence['phase'] and seed['online_executable'] is False
                and seed['native_protection_certified'] is False
                and report['model_version'] == seed['schema'] == 'g31.foundation.repeated_domain.v1', 'current_advice_only_seed')
            require(seed['bundle']['case'] == case and set(seed['bundle']['jobs']) == identities
                and set(observed['known_contracts']['contracts']) == identities
                and all(job['arrival'] <= now for job in observed['known_contracts']['contracts'].values()),
                'all_labelled_jobs_actually_known_before_prediction')
            require(0 <= now - number(seed['source_captured_at']) <= raw['specification']['domain']['source_age_limit_s'] + 1e-12,
                'current_source_age')
            endpoints = evidence['information']['raw_endpoints']
            local = copy.deepcopy(endpoints['view'])
            local['jobs'] = [job for job in local['jobs'] if job['arrival'] <= now and job['status'] != 'unreleased']
            require(local == observed['local_view'] and evidence['retained'] == observed['known_contracts']
                and evidence['own_outbox'] == observed['own_outbox']
                and _public_messages(endpoints['received'], observed['owner'], now) == observed['delivered_v3'],
                'actor_detached_from_exact_actual_delivered_endpoints')
            candidates = decision['candidate_mask']
            action_ids = {candidate['action_id'] for candidate in candidates}
            require(len(action_ids) == len(candidates) == 3 and action_ids == set(seed['action_ids'])
                == set(report['candidate_results']) == {'native_default', 'prefer_3', 'prefer_8'}, 'all_three_candidates_required')
            targets = {}
            for candidate in candidates:
                action_id = candidate['action_id']
                prediction = report['candidate_results'][action_id]
                require(prediction['action_id'] == action_id, 'conditional_action_identity')
                targets[action_id] = complete_prediction(prediction, identities=identities,
                    prefix=seed['bundle']['completed_prefix'], jobs=seed['bundle']['jobs'], now=now,
                    horizon=raw['specification']['domain']['horizon'], model_version=report['model_version'])
                value.features(observed, candidate['semantic'])
                require(type(candidate['enabled']) is bool and candidate['guard_status'] in ('passed', 'rejected', 'unknown'),
                    'declared_conditional_protection_status')
                if candidate['guard_status'] in ('passed', 'rejected'):
                    reference_completion = raw['specification']['reference']['completion']
                    require(set(reference_completion) == identities and candidate['per_job_delta'] ==
                        {identity: prediction['completion'][identity] - reference_completion[identity] for identity in identities},
                        'full_job_guard_delta_binding')
                    protected = all(number(delta) <= 0 for delta in candidate['per_job_delta'].values())
                    require((candidate['guard_status'] == 'passed') == protected, 'guard_status_matches_full_delta')
                require(not candidate['enabled'] or candidate['guard_status'] == 'passed'
                    and candidate['mask_reason'] is None, 'enabled_candidate_requires_current_full_guard')
            staged_rows = []
            for candidate in candidates:
                if candidate['mask_reason'] is not None:
                    exclusions.append({'decision_id': decision['decision_id'], 'action_id': candidate['action_id'],
                        'reason': 'current_physical_candidate_unavailable:' + candidate['mask_reason']})
                    continue
                action_id = candidate['action_id']
                staged_rows.append({'schema': ROW_SCHEMA, 'observation': copy.deepcopy(observed),
                    'action': copy.deepcopy(candidate['semantic']), 'target_value': targets[action_id],
                    'split': split, 'parent_group': case, 'source_decision_id': decision['decision_id'],
                    'source': copy.deepcopy(origin), 'evidence_sha256': digest(evidence), 'seed_sha256': seed['seed_sha256'],
                    'conditional_report_sha256': digest(report), 'conditional_completion': copy.deepcopy(report['candidate_results'][action_id]['completion']),
                    'action_id': action_id, 'conditional_protection_status': candidate['guard_status'],
                    'admissible_under_current_guard': candidate['enabled'], 'target_kind': protocol()['label_kind'],
                    'actual_native_return_label': False, 'eligible_for_TD': False, 'native_execution_authority': False})
            rows.extend(staged_rows)
        except (KeyError, TypeError, ValueError) as error:
            exclusions.append({'decision_id': decision['decision_id'], 'reason': str(error)})
    return rows, exclusions


def score(model, rows):
    predicted = value.predict(model, [row['observation'] for row in rows], [row['action'] for row in rows])
    errors = [prediction - row['target_value'] for prediction, row in zip(predicted, rows, strict=True)]
    groups = {}
    for row, prediction in zip(rows, predicted, strict=True):
        groups.setdefault((row['parent_group'], row['source_decision_id']), []).append((row, prediction))
    decisions, matches, regrets, differentiated_regrets = 0, 0, [], []
    for group in groups.values():
        allowed = [(row, prediction) for row, prediction in group if row['admissible_under_current_guard']]
        if len(allowed) < 2:
            continue
        selected = max(allowed, key=lambda item: (item[1], item[0]['action_id']))[0]
        optimum = max(row['target_value'] for row, _ in allowed)
        regret = optimum - selected['target_value']
        decisions += 1
        matches += regret <= 1e-9
        regrets.append(regret)
        if optimum - min(row['target_value'] for row, _ in allowed) > 1e-9:
            differentiated_regrets.append(regret)
    return {'rows': len(rows), 'independent_parent_groups': len({row['parent_group'] for row in rows}),
        'MAE_to_conditional_teacher': math.fsum(abs(error) for error in errors) / len(errors),
        'RMSE_to_conditional_teacher': math.sqrt(math.fsum(error ** 2 for error in errors) / len(errors)),
        'guard_admissible_multiple_action_decisions': decisions,
        'guard_admissible_teacher_differentiated_decisions': len(differentiated_regrets),
        'guard_admissible_teacher_all_tied_decisions': decisions - len(differentiated_regrets),
        'teacher_best_match_fraction': None if not decisions else matches / decisions,
        'mean_teacher_regret': None if not decisions else math.fsum(regrets) / decisions,
        'differentiated_teacher_best_match_fraction': None if not differentiated_regrets else
            sum(regret <= 1e-9 for regret in differentiated_regrets) / len(differentiated_regrets),
        'differentiated_mean_teacher_regret': None if not differentiated_regrets else
            math.fsum(differentiated_regrets) / len(differentiated_regrets),
        'native_policy_improvement_measured': False, 'predictions': predicted}


def run(plan, output):
    started = time.monotonic()
    require(plan['schema'] == PLAN_SCHEMA and plan['protocol'] == protocol() and plan['native_branches'] == 0,
        'frozen_supervision_protocol')
    require(plan['source_sha256_pins'] == source_pins() and reference(plan['protocol_reference']['path']) == plan['protocol_reference']
        and read(plan['protocol_reference']['path']) == protocol(), 'supervision_source_protocol_pins')
    require([(source['split'], source['case']) for source in plan['sources']] == [('train', TRAIN_CASE),
        ('development', DEVELOPMENT_CASE)], 'only_registered_train_development_sources')
    output = Path(output).resolve()
    require(output.is_relative_to(ROOT) and not output.exists(), 'fresh_supervised_output')
    output.mkdir(parents=True)
    write_new(output / 'registered_plan.json', plan)
    receipt = {'schema': 'g31.foundation.repeated_supervised_receipt.v1', 'status': 'running',
        'native_executed': False, 'reinforcement_learning_performed': False, 'formal_test_read': False,
        'plan_sha256': digest(plan), 'source_sha256_pins': source_pins()}
    try:
        rows, exclusions = [], []
        for source in plan['sources']:
            raw, binding = closed_native_source(source['directory'], case=source['case'])
            require(binding == source['bindings'] and digest(raw['input']) == source['input_sha256'], 'frozen_native_source_files')
            extracted, omitted = extract_rows(raw, split=source['split'], case=source['case'], origin=binding)
            rows.extend(extracted)
            exclusions.extend({'case': source['case'], **item} for item in omitted)
        write_new(output / 'conditional_supervision_rows.json', rows)
        write_new(output / 'excluded_candidates.json', exclusions)
        training = [row for row in rows if row['split'] == 'train']
        development = [row for row in rows if row['split'] == 'development']
        require(training and development, 'both_registered_splits_need_real_complete_conditional_rows')
        reports = []
        for seed in protocol()['seeds']:
            deadline = min(started + protocol()['total_wall_seconds'], time.monotonic() + protocol()['per_seed_wall_seconds'])
            model = value.fit(training, seed=seed, epochs=protocol()['epochs'], deadline=deadline,
                objective='supervised_full_job_conditional_model_distillation_not_native_return_or_RL')
            write_new(output / ('model_seed_' + str(seed) + '.json'), model)
            reports.append({'seed': seed, 'training': score(model, training), 'development': score(model, development),
                'model_sha256': model['model_sha256'], 'final_training_mse': model['training_curve'][-1]['mse']})
        write_new(output / 'evaluation.json', {'schema': 'g31.foundation.repeated_supervised_evaluation.v1',
            'seeds': reports, 'formal_test_read': False, 'model_selection_performed': False,
            'limitations': ['conditional teacher labels are not actual native returns',
                'one train parent and one development parent, decisions/candidates are correlated',
                'training success is not RL readiness or native policy improvement']})
        require(all(reference(bound['path']) == bound for source in plan['sources']
            for bound in source['bindings'].values()), 'native_label_source_exit_bindings')
        require(source_pins() == plan['source_sha256_pins'] and time.monotonic() - started < protocol()['total_wall_seconds'],
            'source_exit_and_total_wall_budget')
        receipt.update(status='completed_supervised_conditional_pretraining', training_rows=len(training),
            development_rows=len(development), completed_seeds=protocol()['seeds'], source_exit_pins_passed=True)
    except Exception:
        receipt.update(status='failed_or_unsupported_supervision', exception=traceback.format_exc())
    receipt['wall_seconds'] = time.monotonic() - started
    receipt['artifacts'] = {str(path.relative_to(output)): sha(path) for path in sorted(output.rglob('*')) if path.is_file()}
    write_new(output / 'receipt.json', receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--admission', required=True)
    args = parser.parse_args()
    require(sys.stdin.readline().strip() == args.admission, 'parent_training_admission_required')
    receipt = run(read(args.plan), args.output)
    print(json.dumps({'status': receipt['status'], 'wall_seconds': receipt['wall_seconds']}))
    return 0 if receipt['status'] == 'completed_supervised_conditional_pretraining' else 1


if __name__ == '__main__':
    raise SystemExit(main())
