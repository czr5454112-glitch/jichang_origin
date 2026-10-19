import copy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_later_learning as learning


def actor():
    job = {'business_bag_id': 'job', 'arrival': 0., 'status': 'waiting_for_tray', 'load_seconds': .1,
        'unload_seconds': .1, 'deadline': 40., 'storage_release_at': 0.}
    tray = {'edge_to': -1, 'mode': 'empty', 'available_at': 1., 'committed_prefix': [7]}
    capture = {'source_owner': 'A', 'target_owner': 'B', 'captured_at': 9., 'valid_until': 10.,
        'message_id': 'peer', 'coverage': {'future_arrivals_included': False}, 'jobs': [copy.deepcopy(job)],
        'trays': [copy.deepcopy(tray)], 'nodes': [{'occupancy': 1, 'actual_available': 1}]}
    envelope = {'capture': {'capture_v2': {'local_capture': capture}}}
    message = {'envelope': envelope, 'source_owner': 'A', 'target_owner': 'B', 'captured_at': 9.,
        'valid_until': 10., 'message_id': 'peer', 'delivered_at': 9.1, 'status': 'conditional', 'fresh': True}
    return {'schema': learning.ACTOR_SCHEMA, 'owner': 'B', 'phase': 'first_reuse_route', 'at': 9.2,
        'timing_mode': 'offline_sync', 'collection': {'request_id': 'own', 'peer_message_id': 'peer',
            'started_at': 9., 'collected_at': 9.2}, 'local_view': {'owner_id': 'B', 'now': 9.2,
            'jobs': [job], 'trays': [tray], 'node_contracts': [
                {'resource_owner': 'B', 'occupancy': 1, 'actual_available': 1}, {'resource_owner': 'A'}]},
        'delivered_v3': [message], 'own_outbox': [], 'collection_status': 'accepted',
        'actor_information_scope': 'owner and delivered', 'model_predictions_included': False,
        'privileged_evaluator_state_included': False}


def row(action='native_default', episode='first', scene='mechanism', completion=13.):
    return learning.make_row(actor(), action, {'job': completion}, scene_id=scene,
        episode_id=episode, source_sha256='a' * 64, executed_action_id=action,
        behavior_mode='diagnostic_intervention', decision_index=0)


def episode():
    candidate = {'candidate_id': 'event-bound', 'action_id': 'native_default', 'enabled': True, 'guard_status': 'passed'}
    transition = {'schema': 'g31.foundation.later_transition.v1', 'timing_mode': 'offline_sync',
        'truncated': False, 'terminated': True, 'terminal_completion': {'job': 13.},
        'actual_physical_effect': {'next_edge_enter': {'time': 10.}},
        'ACK_status': 'not_applicable_no_command', 'command_id': None, 'action_id': 'native_default',
        'executed_action_id': 'native_default', 'behavior_mode': 'guarded', 'conditional_protection_status': 'passed',
        'candidate_mask': [candidate], 'candidate_id': 'event-bound', 'next_observation': None,
        'delta_sim_time_s': 30.8, 'selected_at': 9.2, 'observation': actor()}
    return {'kind': 'EvaluatorRecord', 'native027_acceptance': {'runtime_accepted': True},
        'summary': {'status': 'assessed', 'later_current_choices_enabled': True, 'completion': {'job': 13.}},
        'specification': {'case': 'mechanism', 'fault': None}, 'later_transitions': [transition]}


def test_new_semantic_features_no_ids_or_future_labels():
    observation = actor()
    original = learning.features(observation, 'native_default')
    observation['collection']['request_id'] = 'unseen-request'
    observation['local_view']['jobs'][0]['business_bag_id'] = 'unseen-business'
    assert learning.features(observation, 'native_default') == original
    assert original['own_available_empty'] == 1.
    assert original['action_prefer_8'] == 0.
    assert len(original) == 52


@pytest.mark.parametrize('mutation,reason', [
    (lambda item: item.update(labels={'cost': 5}), 'actor_schema'),
    (lambda item: item.update(model_predictions_included=True), 'actor_future_information'),
    (lambda item: item['delivered_v3'][0].update(delivered_at=12.), 'undelivered_message'),
    (lambda item: item['delivered_v3'][0].update(fresh=False), 'expired_selected_v3'),
    (lambda item: item['delivered_v3'][0].update(source_owner='B'), 'message_owner_binding'),
    (lambda item: item['local_view']['node_contracts'][1].update(occupancy=4), 'private_peer_inventory'),
    (lambda item: item['local_view']['jobs'][0].update(arrival=20.), 'unreleased_actor_job'),
    (lambda item: item.update(at=True), 'finite_number_required'),
])
def test_actor_rejects_illegal_data(mutation, reason):
    observation = actor()
    mutation(observation)
    with pytest.raises(ValueError, match=reason):
        learning.features(observation, 'native_default')


def test_rejected_action_never_gets_executed_cost_label():
    with pytest.raises(ValueError, match='rejected_or_different_action'):
        learning.make_row(actor(), 'prefer_8', {'job': 13.}, scene_id='same', episode_id='same',
            source_sha256='a' * 64, executed_action_id='native_default', behavior_mode='guarded', decision_index=0)


def test_labels_are_actual_remaining_undiscounted_not_guard_scores():
    record = row()
    assert record['labels']['value_s'] == pytest.approx(3.8)
    assert record['protected_policy_training_example'] is False
    assert record['native_execution_authority'] is False
    assert 'labels' not in record['observation']
    with pytest.raises(ValueError, match='unfinished_actual_completion'):
        row(completion=-1.)


def test_train_real_weights_not_fake_rl_or_independent_interventions(tmp_path):
    rows = [row(), row('prefer_8', 'second', completion=14.)]
    report = learning.train(rows, tmp_path / 'train')
    assert report['training_started'] is True
    assert report['training_curve'][-1]['mse_s2'] < report['training_curve'][0]['mse_s2']
    assert report['independent_scene_count'] == 1
    assert report['independent_generalization_status'] == 'unknown_single_scene'
    assert report['closed_loop_RL_trained'] is False
    assert report['diagnostic_intervention_rows'] == 2
    with pytest.raises(FileExistsError):
        learning.train(rows, tmp_path / 'train')


def test_holdout_uses_whole_scene_not_action_or_episode(tmp_path):
    report = learning.train([row(), row('prefer_8', 'second'), row(episode='third', scene='other')], tmp_path / 'train')
    assert len(report['heldout_evaluation']) == 2
    assert all(fold['heldout_scene'] not in fold['trained_scenes'] for fold in report['heldout_evaluation'])


def test_mutated_saved_features_and_duplicate_rows_fail(tmp_path):
    original = row()
    with pytest.raises(ValueError, match='duplicate_native_decision'):
        learning.train([original, original], tmp_path / 'duplicates')
    original['features']['event_time_s'] = 100.
    with pytest.raises(ValueError, match='reextract_features'):
        learning.train([original], tmp_path / 'mutated')


def test_episode_extracts_only_new_native_transition():
    rows = learning.extract_episode(episode(), 'a' * 64)
    assert len(rows) == 1
    assert rows[0]['protected_policy_training_example'] is True
    assert rows[0]['terminated'] is True
    assert rows[0]['labels']['value_s'] == pytest.approx(3.8)


def test_legacy_rows_remain_regression_only_and_v2_binds_local_owner():
    raw = episode()
    raw['result'] = {'physical_clock': 40.}
    assert learning.extract_episode(raw, 'a' * 64)[0]['eligible_for_local_td'] is False
    transition = raw['later_transitions'][0]
    transition.update(schema='g31.foundation.later_transition.v2', owner='B',
        next_state_scope='same_owner_next_decision_or_terminal')
    assert learning.extract_episode(raw, 'a' * 64)[0]['eligible_for_local_td'] is True
    transition.update(next_observation={'owner': 'A'}, terminated=False)
    with pytest.raises(ValueError, match='actual_next_same_owner_decision_binding'):
        learning.extract_episode(raw, 'a' * 64)


def test_v2_rejects_fabricated_self_loop():
    raw = episode()
    transition = raw['later_transitions'][0]
    transition.update(schema='g31.foundation.later_transition.v2', owner='B',
        next_state_scope='same_owner_next_decision_or_terminal', terminated=False,
        next_observation=copy.deepcopy(transition['observation']), delta_sim_time_s=0.)
    with pytest.raises(ValueError, match='actual_next_same_owner_decision_binding'):
        learning.extract_episode(raw, 'a' * 64)


def test_v2_terminal_interval_uses_actual_clock_and_cannot_skip_successor():
    raw = episode()
    raw['result'] = {'physical_clock': 40.}
    transition = raw['later_transitions'][0]
    transition.update(schema='g31.foundation.later_transition.v2', owner='B',
        next_state_scope='same_owner_next_decision_or_terminal', delta_sim_time_s=0.)
    with pytest.raises(ValueError, match='actual_terminal_time_binding'):
        learning.extract_episode(raw, 'a' * 64)
    transition.update(next_observation=None, terminated=True, delta_sim_time_s=30.8)
    raw['later_transitions'].append(copy.deepcopy(transition))
    with pytest.raises(ValueError, match='actual_next_same_owner_decision_binding'):
        learning.extract_episode(raw, 'a' * 64)


@pytest.mark.parametrize('mutation,reason', [
    (lambda raw: raw.update(later_transitions=[]), 'new_later_transitions_required'),
    (lambda raw: raw['native027_acceptance'].update(runtime_accepted=False), 'accepted_native_episode_required'),
    (lambda raw: raw['later_transitions'][0].update(truncated=True), 'truncated_transition'),
    (lambda raw: raw['later_transitions'][0].update(ACK_status='rejected'), 'actual_action_ack_required'),
    (lambda raw: raw['later_transitions'][0].update(terminal_completion={'job': 14.}), 'terminal_label_binding'),
    (lambda raw: raw['later_transitions'][0].update(conditional_protection_status='rejected'), 'guarded_behavior_rejected'),
    (lambda raw: raw['later_transitions'][0]['candidate_mask'][0].update(enabled=False), 'executed_mask_binding'),
    (lambda raw: raw['later_transitions'][0]['actual_physical_effect'].update(next_edge_enter=None), 'actual_effect_required'),
])
def test_unknown_rejected_or_unexecuted_episode_not_training_data(mutation, reason):
    raw = episode()
    mutation(raw)
    with pytest.raises(ValueError, match=reason):
        learning.extract_episode(raw, 'a' * 64)


def test_pipeline_later_value_requires_new_manifest(tmp_path):
    from scripts.experiments.g31_ics_circulation import run_learning_pipeline as pipeline

    config = pipeline.load_config(pipeline.ROOT / 'configs/g31_ics_circulation/learning_pilot_v1.json')
    with pytest.raises(ValueError, match='later_native_episode_manifest_required'):
        pipeline.execute('train-later-value', config, tmp_path)
    later_config = pipeline.load_config(pipeline.ROOT / 'configs/g31_ics_circulation/learning_next_value_v1.json')
    with pytest.raises(ValueError, match='later_value_config_command_scope'):
        pipeline.execute('smoke', later_config, tmp_path)


def test_training_wall_budget_is_enforced(tmp_path, monkeypatch):
    times = iter((0., 31.))
    monkeypatch.setattr(learning.time, 'perf_counter', lambda: next(times))
    with pytest.raises(ValueError, match='training_wall_budget_exceeded'):
        learning.train([row()], tmp_path / 'expired', max_wall_seconds=30.)


def test_actual_default_transitions_do_not_count_as_protected_choices():
    rows = learning.extract_episode(episode(), 'a' * 64)
    report = learning.rl_support(rows)
    assert report['actual_temporal_points_by_episode']['a' * 64] == 1
    assert report['multiple_protected_actions_at_point_by_episode']['a' * 64] == 0
    assert report['protected_executed_nondefault_rows'] == 0
    assert report['training_started'] is False
