"""Finite-episode continuation values from executed native later actions.

Labels are evaluator-only terminal outcomes, never actor features or authority.
Deterministic interventions of one scenario remain one independent group.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np


SCHEMA = 'g31.foundation.later_value_rows.v1'
ACTOR_SCHEMA = 'g31.foundation.later_actor.v1'
MODEL_SCHEMA = 'g31.foundation.later_value_model.v1'
MANIFEST_SCHEMA = 'g31.foundation.later_episode_manifest.v1'
PHASE_ACTIONS = {'first_return': ('return_now', 'return_not_before_7_84'),
    'first_reuse_route': ('native_default', 'prefer_8')}
ACTOR_FIELDS = {'schema', 'owner', 'phase', 'at', 'timing_mode', 'collection', 'local_view',
    'delivered_v3', 'own_outbox', 'collection_status', 'actor_information_scope',
    'model_predictions_included', 'privileged_evaluator_state_included'}


def require(condition, reason):
    if not condition:
        raise ValueError('later_learning:' + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), 'finite_number_required')
    return float(value)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def actor_parts(observation):
    require(set(observation) == ACTOR_FIELDS and observation['schema'] == ACTOR_SCHEMA, 'actor_schema')
    require(observation['model_predictions_included'] is False
        and observation['privileged_evaluator_state_included'] is False, 'actor_future_information')
    require(observation['timing_mode'] == 'offline_sync', 'declared_clock')
    owner, phase, now = observation['owner'], observation['phase'], number(observation['at'])
    require(phase in PHASE_ACTIONS and owner == ('A' if phase == 'first_return' else 'B'), 'owner_phase')
    local = observation['local_view']
    require(local['owner_id'] == owner and number(local['now']) == now, 'local_owner_epoch')
    for node in local['node_contracts']:
        require(node['resource_owner'] == owner or not {'occupancy', 'actual_available'}.intersection(node),
            'private_peer_inventory')
    selected = []
    for message in observation['delivered_v3']:
        require(number(message['delivered_at']) <= now, 'undelivered_message')
        if message['message_id'] != observation['collection']['peer_message_id']:
            continue
        require(message['status'] == 'conditional' and message['fresh'] is True
            and number(message['captured_at']) <= now < number(message['valid_until']), 'expired_selected_v3')
        capture = message['envelope']['capture']['capture_v2']['local_capture']
        require(capture['source_owner'] != owner and capture['target_owner'] == owner
            and message['source_owner'] == capture['source_owner']
            and message['target_owner'] == capture['target_owner'], 'message_owner_binding')
        for field in ('message_id', 'captured_at', 'valid_until'):
            require(message[field] == capture[field], 'message_identity_binding')
        require(capture['coverage']['future_arrivals_included'] is False, 'future_arrival_coverage')
        selected.append((capture, message))
    require(len(selected) == 1, 'one_fresh_selected_peer_capture')
    peer, message = selected[0]
    for view in (local, peer):
        require(all(number(job['arrival']) <= now for job in view['jobs']), 'unreleased_actor_job')
    return local, peer, message


def _view_features(view, now, prefix, nodes):
    jobs, trays = view['jobs'], view['trays']
    result = {prefix + 'job_count': float(len(jobs)), prefix + 'tray_count': float(len(trays)),
        prefix + 'available_empty': sum(number(node['actual_available']) for node in nodes),
        prefix + 'occupancy': sum(number(node['occupancy']) for node in nodes),
        prefix + 'inflight': float(sum(tray['edge_to'] >= 0 for tray in trays)),
        prefix + 'load_seconds': sum(number(job['load_seconds']) for job in jobs),
        prefix + 'unload_seconds': sum(number(job['unload_seconds']) for job in jobs),
        prefix + 'deadline_slack': sum(max(0., number(job['deadline']) - now) for job in jobs),
        prefix + 'storage_release_delay': sum(max(0., number(job['storage_release_at']) - now)
            for job in jobs if job['status'] == 'storage'),
        prefix + 'available_delay': sum(max(0., number(tray['available_at']) - now)
            for tray in trays if tray['edge_to'] < 0),
        prefix + 'committed_prefix_length': float(sum(len(tray['committed_prefix']) for tray in trays))}
    for status in ('waiting_for_tray', 'loading', 'in_transit', 'storage', 'completed'):
        result[prefix + 'jobs_' + status] = float(sum(job['status'] == status for job in jobs))
    for mode in ('empty', 'loading', 'loaded', 'storage', 'unloading'):
        result[prefix + 'trays_' + mode] = float(sum(tray['mode'] == mode for tray in trays))
    return result


def features(observation, action_id):
    local, peer, message = actor_parts(observation)
    phase, now = observation['phase'], number(observation['at'])
    require(action_id in PHASE_ACTIONS[phase], 'semantic_action_not_in_phase')
    result = {'event_time_s': now, 'phase_return': float(phase == 'first_return'),
        'peer_message_age_s': now - number(message['captured_at']),
        'peer_remaining_valid_s': number(message['valid_until']) - now,
        'collection_elapsed_s': now - number(observation['collection']['started_at']),
        'return_not_before_delay_s': max(0., 7.84 - now) if action_id == 'return_not_before_7_84' else 0.}
    for actions in PHASE_ACTIONS.values():
        for action in actions:
            result['action_' + action] = float(action_id == action)
    own_nodes = [node for node in local['node_contracts'] if node['resource_owner'] == observation['owner']]
    result.update(_view_features(local, now, 'own_', own_nodes))
    result.update(_view_features(peer, now, 'peer_', peer['nodes']))
    require(all(math.isfinite(value) for value in result.values()), 'nonfinite_feature')
    return result


def make_row(observation, action_id, completion, *, scene_id, episode_id, source_sha256,
             executed_action_id, behavior_mode, decision_index):
    require(action_id == executed_action_id, 'rejected_or_different_action_has_no_label')
    require(behavior_mode in ('guarded', 'diagnostic_intervention'), 'behavior_mode')
    require(bool(scene_id) and bool(episode_id) and len(source_sha256) == 64, 'source_provenance')
    local, peer, _ = actor_parts(observation)
    jobs = sorted({job['business_bag_id'] for view in (local, peer) for job in view['jobs']
        if job['status'] != 'completed'})
    require(bool(jobs) and all(job in completion for job in jobs), 'missing_actual_completion')
    require(all(number(completion[job]) >= 0. for job in jobs), 'unfinished_actual_completion')
    remaining = {job: max(0., number(completion[job]) - number(observation['at'])) for job in jobs}
    return {'schema': SCHEMA, 'scene_id': scene_id, 'episode_id': episode_id,
        'decision_index': decision_index, 'source_sha256': source_sha256,
        'behavior_mode': behavior_mode, 'observation': copy.deepcopy(observation), 'action_id': action_id,
        'features': features(observation, action_id), 'labels': {
            'scope': 'offline_actual_native_terminal_outcome_not_actor_input',
            'objective': 'undiscounted_mean_remaining_completion_seconds_of_observed_active_jobs',
            'per_job_remaining_s': remaining, 'value_s': sum(remaining.values()) / len(remaining)},
        'native_execution_authority': False, 'protected_policy_training_example': behavior_mode == 'guarded'}


def extract_episode(raw, source_sha256):
    require(raw.get('kind') == 'EvaluatorRecord' and raw.get('native027_acceptance', {}).get('runtime_accepted') is True,
        'accepted_native_episode_required')
    require(raw['summary']['status'] == 'assessed' and raw['summary'].get('later_current_choices_enabled') is True,
        'completed_current_later_episode_required')
    require(raw['specification']['case'] in ('mechanism', 'no_overlap', 'insufficient_advance')
        and raw['specification']['fault'] is None, 'registered_scene')
    transitions = raw.get('later_transitions', [])
    require(bool(transitions), 'new_later_transitions_required')
    rows = []
    for index, transition in enumerate(sorted(transitions, key=lambda item: item['selected_at'])):
        require(transition['schema'] == 'g31.foundation.later_transition.v1'
            and transition['timing_mode'] == 'offline_sync', 'transition_schema')
        require(transition['truncated'] is False, 'truncated_transition')
        require(transition['terminal_completion'] == raw['summary']['completion'], 'terminal_label_binding')
        require(transition['actual_physical_effect']['next_edge_enter'] is not None, 'actual_effect_required')
        require(transition['ACK_status'] in ('received', 'updated', 'not_applicable_no_command'), 'actual_action_ack_required')
        require((transition['command_id'] is None) == (transition['action_id'] == 'native_default'), 'command_semantics')
        if transition['behavior_mode'] == 'guarded':
            require(transition['conditional_protection_status'] == 'passed', 'guarded_behavior_rejected')
        selected = [candidate for candidate in transition['candidate_mask']
            if candidate['candidate_id'] == transition['candidate_id']]
        require(len(selected) == 1 and selected[0]['enabled'] is True
            and selected[0]['action_id'] == transition['action_id'], 'executed_mask_binding')
        following = transition['next_observation']
        if following is not None:
            require(number(transition['delta_sim_time_s']) == number(following['at']) - number(transition['selected_at']),
                'event_interval_binding')
            require(transition['terminated'] is False, 'next_observation_not_terminal')
        else:
            require(transition['terminated'] is True and number(transition['delta_sim_time_s']) >= 0., 'terminal_interval')
        record = make_row(transition['observation'], transition['action_id'], transition['terminal_completion'],
            scene_id=raw['specification']['case'], episode_id=source_sha256,
            source_sha256=source_sha256, executed_action_id=transition['executed_action_id'],
            behavior_mode=transition['behavior_mode'], decision_index=index)
        record.update(delta_sim_time_s=transition['delta_sim_time_s'], terminated=transition['terminated'],
            truncated=False, next_observation_sha256=digest(following) if following else None,
            candidate_mask=copy.deepcopy(transition['candidate_mask']))
        rows.append(record)
    return rows


def load_manifest(path, row_limit=20000):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    require(manifest.get('schema') == MANIFEST_SCHEMA and bool(manifest.get('episodes')), 'episode_manifest_schema')
    rows, sources = [], []
    for entry in manifest['episodes']:
        receipt_path = Path(entry['receipt_path']).resolve(strict=True)
        require(hashlib.sha256(receipt_path.read_bytes()).hexdigest() == entry['receipt_sha256'], 'receipt_identity')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        require(receipt['status'] == 'assessed' and receipt['run_acceptance_status'] == 'closed_run_acceptance_passed',
            'closed_native_acceptance_required')
        artifact = receipt['raw_artifact']
        raw_path = Path(artifact['path']).resolve(strict=True)
        require(raw_path.parent == receipt_path.parent, 'raw_receipt_directory_binding')
        payload = raw_path.read_bytes()
        require(hashlib.sha256(payload).hexdigest() == artifact['sha256'], 'raw_identity')
        raw = json.loads(gzip.decompress(payload))
        rows.extend(extract_episode(raw, artifact['sha256']))
        require(len(rows) <= row_limit, 'training_row_budget')
        sources.append({'receipt_path': str(receipt_path), 'receipt_sha256': entry['receipt_sha256'],
            'raw_path': str(raw_path), 'raw_sha256': artifact['sha256']})
    return rows, sources


def rl_support(rows):
    require(bool(rows), 'new_native_rows_for_readiness')
    episodes = sorted({row['episode_id'] for row in rows})
    actual_points = {episode: sum(row['episode_id'] == episode for row in rows) for episode in episodes}
    protected_choice_points = {episode: sum(row['episode_id'] == episode and sum(
        candidate['guard_status'] == 'passed' for candidate in row['candidate_mask']) >= 2 for row in rows)
        for episode in episodes}
    protected_nondefault = [row for row in rows if row['behavior_mode'] == 'guarded'
        and row['action_id'] in ('return_not_before_7_84', 'prefer_8')]
    return {'status': 'blocked_L1_not_certified', 'training_started': False,
        'actual_native_rows': len(rows), 'independent_scene_count': len({row['scene_id'] for row in rows}),
        'actual_temporal_points_by_episode': actual_points,
        'multiple_protected_actions_at_point_by_episode': protected_choice_points,
        'protected_executed_nondefault_rows': len(protected_nondefault),
        'missing_capabilities': ['Protected nondefault action with attributable actual effects and at least two meaningful temporal choice points.',
            'Independent native evaluation of a trained multi-step policy; continuation-value fitting is not RL.'],
        'allowed_next_training': 'supervised_value_only_on_explicit_actual_behavior_data',
        'L1_certified': False, 'complete_request_100ms_certified': False}


def _fit(rows, alpha=1.):
    require(bool(rows) and number(alpha) > 0, 'training_rows_and_positive_alpha')
    names = sorted(rows[0]['features'])
    for row in rows:
        require(row['schema'] == SCHEMA and features(row['observation'], row['action_id']) == row['features'],
            'reextract_features')
        require(sorted(row['features']) == names, 'feature_schema')
    matrix = np.array([[number(row['features'][name]) for name in names] for row in rows], dtype=np.float64)
    targets = np.array([number(row['labels']['value_s']) for row in rows], dtype=np.float64)
    center, scale = matrix.mean(axis=0), matrix.std(axis=0)
    scale[scale < 1e-9] = 1.
    standardized = (matrix - center) / scale
    intercept = float(targets.mean())
    coefficients = np.linalg.solve(standardized.T @ standardized + alpha * np.eye(len(names)),
        standardized.T @ (targets - intercept))
    predicted = standardized @ coefficients + intercept
    return {'schema': MODEL_SCHEMA, 'feature_schema': SCHEMA, 'feature_names': names,
        'center': center.tolist(), 'scale': scale.tolist(), 'coefficients': coefficients.tolist(),
        'intercept': intercept, 'alpha': alpha, 'kind': 'ridge_continuation_value', 'device': 'cpu',
        'objective': rows[0]['labels']['objective'], 'discount': 'none_finite_episode',
        'trained_scenes': sorted({row['scene_id'] for row in rows}), 'training_rows': len(rows),
        'training_curve': [{'step': 0, 'mse_s2': float(np.mean(targets ** 2))},
            {'step': 1, 'mse_s2': float(np.mean((predicted - targets) ** 2))}],
        'native_execution_authority': False, 'closed_loop_RL_trained': False}


def predict(model, observation, action_id):
    require(model['schema'] == MODEL_SCHEMA and model['feature_schema'] == SCHEMA, 'model_schema')
    vector = features(observation, action_id)
    require(sorted(vector) == model['feature_names'], 'model_feature_schema')
    standardized = (np.array([vector[name] for name in model['feature_names']])
        - np.array(model['center'])) / np.array(model['scale'])
    value = float(standardized @ np.array(model['coefficients']) + model['intercept'])
    require(math.isfinite(value), 'nonfinite_prediction')
    return value


def train(rows, output, *, max_wall_seconds=30.):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    require(number(max_wall_seconds) > 0., 'positive_training_wall_budget')
    deadline = started + max_wall_seconds
    require(bool(rows) and len(rows) <= 20000, 'training_row_budget')
    identities = [(row['episode_id'], row['decision_index']) for row in rows]
    require(len(set(identities)) == len(identities), 'duplicate_native_decision')
    scenes = sorted({row['scene_id'] for row in rows})
    dataset_hash = digest(rows)
    registration = {'dataset_sha256': dataset_hash, 'scene_groups': scenes,
        'split_rule': 'leave_one_entire_scenario_out_if_at_least_two_scenarios',
        'same_scene_interventions_never_independent_groups': True, 'ridge_alpha': 1.,
        'training_wall_budget_seconds': max_wall_seconds,
        'target': rows[0]['labels']['objective'], 'algorithm': 'supervised_ridge_value_not_RL'}
    write_json(output / 'preregistered.json', registration)
    write_json(output / 'rows.json', rows)
    require(time.perf_counter() <= deadline, 'training_wall_budget_exceeded')
    model = _fit(rows)
    require(time.perf_counter() <= deadline, 'training_wall_budget_exceeded')
    write_json(output / 'checkpoint.json', model)
    fitted = [predict(model, row['observation'], row['action_id']) for row in rows]
    folds = []
    if len(scenes) >= 2:
        for scene in scenes:
            training = [row for row in rows if row['scene_id'] != scene]
            testing = [row for row in rows if row['scene_id'] == scene]
            fold = _fit(training)
            require(time.perf_counter() <= deadline, 'training_wall_budget_exceeded')
            errors = [predict(fold, row['observation'], row['action_id']) - row['labels']['value_s'] for row in testing]
            fold_path = output / ('heldout_' + hashlib.sha256(scene.encode()).hexdigest()[:12] + '.json')
            write_json(fold_path, fold)
            folds.append({'heldout_scene': scene, 'trained_scenes': fold['trained_scenes'],
                'row_count': len(testing), 'mae_s': sum(abs(error) for error in errors) / len(errors),
                'checkpoint': str(fold_path.resolve())})
    require(time.perf_counter() <= deadline, 'training_wall_budget_exceeded')
    report = {'status': 'completed_supervised_value_update', 'training_started': True,
        'training_rows': len(rows), 'independent_scene_count': len(scenes),
        'diagnostic_intervention_rows': sum(row['behavior_mode'] == 'diagnostic_intervention' for row in rows),
        'dataset_sha256': dataset_hash, 'checkpoint_sha256': hashlib.sha256((output / 'checkpoint.json').read_bytes()).hexdigest(),
        'training_curve': model['training_curve'], 'fit_predictions_s': fitted, 'fit_is_resubstitution': True,
        'heldout_evaluation': folds, 'independent_generalization_status': 'evaluated_tiny_scene_holdout' if folds else 'unknown_single_scene',
        'training_wall_seconds': time.perf_counter() - started, 'device': 'cpu',
        'training_wall_budget_seconds': max_wall_seconds,
        'closed_loop_RL_trained': False, 'L1_certified': False, 'learned_takeover_certified': False,
        'complete_request_100ms_certified': False,
        'scope': 'Actual native continuation value fitting; no unsupported off-policy improvement or deployment guarantee.'}
    write_json(output / 'report.json', report)
    return report


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
