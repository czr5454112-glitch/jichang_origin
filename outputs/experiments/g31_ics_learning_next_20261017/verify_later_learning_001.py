"""Independent tiny saved-data ridge arithmetic; no project imports/native runs."""
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
specification = importlib.util.spec_from_file_location('saved_later_review', HERE / 'verify_later_evidence_001.py')
evidence = importlib.util.module_from_spec(specification)
specification.loader.exec_module(evidence)


def features(observation, action):
    now = observation['at']
    message = next(row for row in observation['delivered_v3'] if row['message_id'] == observation['collection']['peer_message_id'])
    peer = message['envelope']['capture']['capture_v2']['local_capture']
    local = observation['local_view']
    values = {'event_time_s': now, 'phase_return': float(observation['phase'] == 'first_return'),
        'peer_message_age_s': now - message['captured_at'], 'peer_remaining_valid_s': message['valid_until'] - now,
        'collection_elapsed_s': now - observation['collection']['started_at'],
        'return_not_before_delay_s': max(0., 7.84 - now) if action == 'return_not_before_7_84' else 0.}
    for candidate in ('return_now', 'return_not_before_7_84', 'native_default', 'prefer_8'):
        values['action_' + candidate] = float(action == candidate)
    for prefix, view, nodes in (('own_', local, [row for row in local['node_contracts'] if row['resource_owner'] == observation['owner']]),
                               ('peer_', peer, peer['nodes'])):
        jobs, trays = view['jobs'], view['trays']
        current = {'job_count': float(len(jobs)), 'tray_count': float(len(trays)),
            'available_empty': sum(float(node['actual_available']) for node in nodes),
            'occupancy': sum(float(node['occupancy']) for node in nodes),
            'inflight': float(sum(tray['edge_to'] >= 0 for tray in trays)),
            'load_seconds': sum(float(job['load_seconds']) for job in jobs),
            'unload_seconds': sum(float(job['unload_seconds']) for job in jobs),
            'deadline_slack': sum(max(0., float(job['deadline']) - now) for job in jobs),
            'storage_release_delay': sum(max(0., float(job['storage_release_at']) - now) for job in jobs if job['status'] == 'storage'),
            'available_delay': sum(max(0., float(tray['available_at']) - now) for tray in trays if tray['edge_to'] < 0),
            'committed_prefix_length': float(sum(len(tray['committed_prefix']) for tray in trays))}
        for status in ('waiting_for_tray', 'loading', 'in_transit', 'storage', 'completed'):
            current['jobs_' + status] = float(sum(job['status'] == status for job in jobs))
        for mode in ('empty', 'loading', 'loaded', 'storage', 'unloading'):
            current['trays_' + mode] = float(sum(tray['mode'] == mode for tray in trays))
        values.update({prefix + key: value for key, value in current.items()})
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=HERE.parents[2])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    evidence.require(not args.output.exists(), 'output_must_be_new')
    directory = root / 'outputs/experiments/g31_ics_learning_next_20261017'
    branches = {'guarded_default': directory / 'later_episodes_001/guarded_default',
        'diagnostic_prefer8': directory / 'later_episodes_001/diagnostic_prefer8',
        'diagnostic_absolute_return': directory / 'later_repair_001/diagnostic_absolute_return',
        'guarded_learned_value': directory / 'later_frozen_evaluation_001/guarded_learned_value'}
    raw, reports = {}, {}
    for name, path in branches.items():
        raw[name], reports[name] = evidence.inspect_branch(path, root)
    baseline = raw['guarded_default']
    comparisons = {}
    for name, candidate in raw.items():
        evidence.require(candidate['input'] == baseline['input'], 'same_physical_input')
        changed = [index for index, (left, right) in enumerate(zip(baseline['later_transitions'], candidate['later_transitions']))
            if left['action_id'] != right['action_id']]
        cutoff = baseline['later_transitions'][changed[0]]['selected_at'] if changed else 40.
        prefix = lambda value: [row for row in value['result']['receipts'] if row['time'] <= cutoff]
        delta = {job: candidate['summary']['completion'][job] - baseline['summary']['completion'][job] for job in evidence.JOBS}
        comparisons[name] = {'baseline': 'guarded_default', 'same_input': True, 'prefix_cutoff': cutoff,
            'all_receipts_prefix_exact': prefix(candidate) == prefix(baseline), 'baseline_prefix_count': len(prefix(baseline)),
            'per_job_actual_delta': delta, 'strict_protected_zero_tolerance': all(value <= 0 for value in delta.values()),
            'full_result_parity': {field: candidate['result'][field] == baseline['result'][field] for field in ('receipts', 'jobs', 'trays')}}
    model_directory = directory / 'later_value_001/train-later-value/models'
    rows = evidence.read(model_directory / 'rows.json')
    model = evidence.read(model_directory / 'checkpoint.json')
    training = evidence.read(model_directory / 'report.json')
    registration = evidence.read(model_directory / 'preregistered.json')
    evidence.require(len(rows) == 6 and len({row['scene_id'] for row in rows}) == 1
        and sum(row['behavior_mode'] == 'diagnostic_intervention' for row in rows) == 4, 'actual_six_row_one_scene_scope')
    sources = {reports[name]['references']['raw']['sha256']: raw[name] for name in branches if name != 'guarded_learned_value'}
    evidence.require(len({(row['source_sha256'], row['decision_index']) for row in rows}) == 6, 'unique_actual_decisions')
    for row in rows:
        source = sources[row['source_sha256']]
        transition = source['later_transitions'][row['decision_index']]
        evidence.require(row['observation'] == transition['observation']
            and row['action_id'] == transition['executed_action_id']
            and row['behavior_mode'] == transition['behavior_mode'], 'actual_transition_row_binding')
        extracted = features(row['observation'], row['action_id'])
        evidence.require(extracted == row['features'] and len(extracted) == 52, 'independent_legal_feature_reextraction')
        observation = row['observation']
        message = next(message for message in observation['delivered_v3'] if message['message_id'] == observation['collection']['peer_message_id'])
        peer = message['envelope']['capture']['capture_v2']['local_capture']
        jobs = sorted({job['business_bag_id'] for view in (observation['local_view'], peer)
            for job in view['jobs'] if job['status'] != 'completed'})
        remaining = {job: max(0., source['summary']['completion'][job] - observation['at']) for job in jobs}
        evidence.require(row['labels']['per_job_remaining_s'] == remaining
            and row['labels']['value_s'] == sum(remaining.values()) / len(remaining), 'actual_executed_terminal_labels')
    dataset_sha = evidence.hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    checkpoint_sha = evidence.sha(model_directory / 'checkpoint.json')
    evidence.require(dataset_sha == training['dataset_sha256'] == registration['dataset_sha256']
        and checkpoint_sha == training['checkpoint_sha256'], 'training_artifact_hashes')
    names = sorted(rows[0]['features'])
    matrix = np.asarray([[row['features'][name] for name in names] for row in rows], dtype=np.float64)
    targets = np.asarray([row['labels']['value_s'] for row in rows], dtype=np.float64)
    center, scale = matrix.mean(axis=0), matrix.std(axis=0)
    scale[scale < 1e-9] = 1.
    standardized = (matrix - center) / scale
    intercept = float(targets.mean())
    coefficient = np.linalg.solve(standardized.T @ standardized + np.eye(len(names)), standardized.T @ (targets - intercept))
    errors = {'center': float(np.max(np.abs(center - model['center']))), 'scale': float(np.max(np.abs(scale - model['scale']))),
        'intercept': abs(intercept - model['intercept']), 'coefficients': float(np.max(np.abs(coefficient - model['coefficients'])))}
    evidence.require(model['feature_names'] == names and model['alpha'] == 1.
        and max(errors.values()) <= 1e-12, 'independent_ridge_parameter_reconstruction')
    fitted = standardized @ coefficient + intercept
    evidence.require(np.max(np.abs(fitted - training['fit_predictions_s'])) <= 1e-12, 'saved_fit_predictions')
    evaluation = raw['guarded_learned_value']
    worker = evidence.read(branches['guarded_learned_value'] / 'worker_report.json')
    scores = []
    for transition, call in zip(evaluation['later_transitions'], worker['selector_calls'], strict=True):
        enabled = [candidate for candidate in transition['candidate_mask'] if candidate['enabled']]
        evidence.require(len(enabled) == 1 and enabled[0]['action_id'] in ('return_now', 'native_default'), 'only_default_enabled')
        vector = features(transition['observation'], enabled[0]['action_id'])
        value = float(((np.asarray([vector[name] for name in names]) - center) / scale) @ coefficient + intercept)
        evidence.require(call['checkpoint_sha256'] == checkpoint_sha and len(call['scores']) == 1
            and call['scores'][0]['candidate_id'] == transition['candidate_id']
            and abs(call['scores'][0]['value_s'] - value) <= 1e-12, 'new_legal_actor_score_replay')
        scores.append({'owner': transition['owner'], 'action_id': transition['action_id'], 'only_one_enabled': True,
            'recomputed_value_s': value, 'saved_value_s': call['scores'][0]['value_s']})
    evidence.require(all(comparisons['guarded_learned_value']['full_result_parity'].values()), 'new_learned_episode_exact_default_trajectory')
    report = {'schema': 'g31.independent_later_evidence_review.v2',
        'status': 'passed_with_negative_learning_and_protection_results', 'branches': reports, 'comparisons': comparisons,
        'learning': {'references': {name: evidence.reference(model_directory / name, root) for name in
            ('rows.json', 'checkpoint.json', 'report.json', 'preregistered.json')}, 'training_rows': 6,
            'independent_scene_count': 1, 'diagnostic_intervention_rows': 4, 'features_independently_reextracted': 52,
            'dataset_canonical_sha256': dataset_sha, 'checkpoint_sha256': checkpoint_sha,
            'independent_ridge_max_parameter_errors': errors, 'numeric_replay_tolerance': 1e-12,
            'numeric_tolerance_is_not_business_protection_tolerance': True,
            'recomputed_fit_mse_s2': float(np.mean((fitted - targets) ** 2)), 'fresh_callback_scores': scores,
            'independent_generalization': 'unknown_single_scene', 'fit_is_resubstitution': True,
            'improvement_from_learned_actor': False, 'protected_multistep_RL': False},
        'scope': 'Independent saved receipt/feature/label/ridge/score arithmetic, no original learner import or new native execution.',
        'limitations': ['Numerical ridge replay only uses 1e-12 arithmetic comparison; business protection uses exact zero tolerance.',
            'Diagnostic actions retain business rejection and may invalidate earlier conditional default-future forecasts.',
            'All episodes share one scene; no independent-scene generalization.',
            'Learned execution has only one enabled default per point and no business improvement or protected RL.',
            'No native full-physics proof, 100ms certification, or full R1/R2 authority claim.']}
    with args.output.open('x', encoding='utf8') as target:
        json.dump(report, target, indent=2, ensure_ascii=False, allow_nan=False)
        target.write('\n')
    print(json.dumps({'status': report['status'], 'branches': len(reports), 'ridge_errors': errors,
        'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
