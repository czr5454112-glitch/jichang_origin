import copy
from itertools import product
import json
from pathlib import Path

import numpy as np
import pytest

from scripts.experiments.g31_ics_circulation import foundation_learning_data as data
from scripts.experiments.g31_ics_circulation import foundation_ranker as ranker


def observation(owner='A', now=1.):
    peer = 'B' if owner == 'A' else 'A'
    job = {'arrival': .1, 'status': 'waiting_for_tray', 'load_seconds': 2.,
        'unload_seconds': .2, 'storage_release_at': 4., 'deadline': 50., 'business_bag_id': 'arbitrary'}
    capture = {'source_owner': peer, 'target_owner': owner, 'captured_at': .5,
        'coverage': {'future_arrivals_included': False}, 'jobs': [job],
        'nodes': [{'actual_available': 1., 'occupancy': 1.}],
        'trays': [{'service_ready_known': False, 'service_ready_at': 999.}]}
    return {'command': {}, 'own_request': {}, 'received': [
        {'kind': 'planning_snapshot', 'delivered_at': .75, 'capture': capture}],
        'view': {'owner_id': owner, 'now': now, 'jobs': [job],
            'trays': [{'tray_id': 'opaque', 'mode': 'empty', 'available_at': 0., 'edge_from': 0}],
            'node_contracts': [{'resource_owner': owner, 'occupancy': 2., 'capacity': 3., 'actual_available': 0.},
                {'resource_owner': peer, 'capacity': 3.}],
            'node_records': [[0], [1]], 'edge_records': [[0, 1, 10., 2.]]}}


def raw_source():
    actions = [{'initial_action': first, 'empty_departure': depart, 'return_delay': returned, 'later_action': later}
        for first, depart, returned, later in product(('native_default', 'prefer_2'), (4., 5., 6., 7.),
            (0., 1.), ('native_default', 'prefer_8'))]
    initial = {}
    for owner in ('A', 'B'):
        public = observation(owner)
        candidates = []
        for index, action in enumerate(actions):
            delta = .1 * (index - 4)
            candidates.append({'candidate_index': index, 'action': action, 'status': 'conditional_forecast',
                'completion': {job: 10. + delta for job in data.JOBS}})
        initial[owner] = {'collection': {'public': public, 'public_sha256': data.digest(public)},
            'selection': {'provider_evidence': {'owner': owner, 'initial_public_sha256': data.digest(public), 'rows': candidates}}}
    return {'summary': {'status': 'assessed', 'completion': {job: 10. for job in data.JOBS}}, 'initial_owners': initial}


def rows_for_groups():
    rows = []
    for index, group in enumerate(('group_one', 'group_two', 'group_three')):
        raw = raw_source()
        for owner in ('A', 'B'):
            raw['initial_owners'][owner]['collection']['public']['view']['now'] = index + 1.
            digest = data.digest(raw['initial_owners'][owner]['collection']['public'])
            raw['initial_owners'][owner]['collection']['public_sha256'] = digest
            raw['initial_owners'][owner]['selection']['provider_evidence']['initial_public_sha256'] = digest
        rows.extend(data.extract_raw(raw, {'path': 'synthetic', 'sha256': 'fixture'}, group))
    return rows


def test_features_preserve_units_and_actual_available_not_empty_inflight():
    features = data.observation_features(observation())
    assert features['static_edge_length_sum'] == 10.
    assert 'static_edge_travel_sum' not in features
    assert features['own_available_empty_count'] == 0.
    assert features['own_inflight_count'] == 1.
    assert features['peer_ready_missing_count'] == 1.
    assert features['peer_known_ready_delay'] == 0.
    assert len(data.feature_vector(observation(), raw_source()['initial_owners']['A']['selection']['provider_evidence']['rows'][0]['action'])) == 43


@pytest.mark.parametrize('mutation,reason', [
    (lambda value: value['view']['node_contracts'][1].update(occupancy=5), 'private_peer_node_fields'),
    (lambda value: value['view']['jobs'][0].update(arrival=9.), 'future_local_job'),
    (lambda value: value['received'][0].update(delivered_at=9.), 'message_not_yet_delivered'),
    (lambda value: value['received'][0]['capture']['coverage'].update(future_arrivals_included=True), 'future_arrival_coverage'),
    (lambda value: value['received'][0]['capture'].update(source_owner='A'), 'delivered_peer_scope'),
    (lambda value: value.update(labels={'future': 100}), 'public_observation_schema'),
])
def test_actor_rejects_illegal_information(mutation, reason):
    public = observation()
    mutation(public)
    with pytest.raises(ValueError, match=reason):
        data.observation_features(public)


def test_identifiers_and_unknown_ready_timestamp_do_not_enter_features():
    public = observation()
    before = data.observation_features(public)
    public['view']['trays'][0]['tray_id'] = '999999999999'
    public['view']['jobs'][0]['business_bag_id'] = 'future_label_99999'
    public['received'][0]['capture']['trays'][0]['service_ready_at'] = -99999.
    assert data.observation_features(public) == before


def test_extractor_retains_conditioning_and_does_not_promote_unknown_endpoints():
    raw = raw_source()
    raw['initial_owners']['A']['selection']['provider_evidence']['rows'][0]['status'] = 'unknown_projection'
    rows = data.extract_raw(raw, {}, 'scenario')
    first = rows[0]
    assert first['labels']['evaluation_status'] == 'unknown'
    assert first['labels']['cost_components']['delta_completion_sum_s'] is None
    assert first['labels']['per_job_outcomes'] is None
    assert all(row['labels']['protection_status'] == 'unknown' for row in rows)
    assert first['conditioned_peer_behavior']['assumed_components'] == {
        field: first['candidate_semantics'][field] for field in data.OWNER_FIELDS['B']}
    assert first['teacher_mode'] == 'causal_rollout'
    assert not first['proposal_mask']['full_joint_execution_authorized']
    assert len(ranker._training_rows(rows)) == 63


def test_unknown_reference_keeps_whole_decision_out_of_target_loss():
    raw = raw_source()
    raw['initial_owners']['A']['selection']['provider_evidence']['rows'][4]['status'] = 'unknown_projection'
    rows = data.extract_raw(raw, {}, 'scenario')
    assert all(row['labels']['conditional_protection_status'] == 'unknown' for row in rows[:32])
    assert len(ranker._training_rows(rows)) == 32


def test_actor_features_do_not_use_label_metadata_or_cached_feature_columns():
    rows = rows_for_groups()
    before = ranker._training_rows(rows)
    for row in rows:
        row['candidate_id'] = 'poison_999'
        row['scenario_set_id'] = 'future_scene'
        row['observation_features'] = {'future_label': 999.}
        row['candidate_features'] = {'future_label': 999.}
        row['labels']['per_job_outcomes'] = {'future_private_peer': 999.}
    assert ranker._training_rows(rows) == before


def test_candidate_index_not_semantic_input():
    candidate = raw_source()['initial_owners']['A']['selection']['provider_evidence']['rows'][0]['action']
    candidate['candidate_index'] = 4
    with pytest.raises(ValueError, match='semantic_candidate_schema'):
        data.candidate_features(observation(), candidate)


def test_evaluation_budget_includes_incumbent_and_unknown_is_not_protected():
    rows = data.extract_raw(raw_source(), {}, 'scenario')[:32]
    for row in rows:
        row['labels']['conditional_protection_status'] = 'unknown'
    result = ranker.evaluate_group(rows, list(range(32)), 4)
    assert len(result['retained_candidate_indices']) == 4
    assert 4 in result['retained_candidate_indices']
    assert result['conditional_optimal_retained'] is None
    assert result['conditional_protected_regret_s'] is None
    assert result['native_protection_status'] == 'unknown'


def test_real_training_group_holdout_portable_inference_and_replay(tmp_path):
    rows = rows_for_groups()
    dataset = tmp_path / 'dataset.jsonl'
    dataset.write_text(''.join(data.canonical(row) + '\n' for row in rows), encoding='utf8')
    output = tmp_path / 'models'
    report = ranker.train_rankers(dataset, output, epochs=2)
    assert report['candidate_rows'] == 192
    assert report['independent_source_groups'] == 3
    assert not report['gpu_used']
    assert not report['generalization_established']
    assert ranker.evaluate_models(dataset, output)['summary'] == report['summary']
    for fold in report['fold_models']:
        assert fold['held_out_group'] not in fold['training_groups']
        for kind, path in fold['models'].items():
            payload = json.loads(Path(path).read_bytes())
            assert payload['training_row_count'] == 128
            assert payload['trained_source_groups'] == fold['training_groups']
            mean_time = np.mean([row['owner_observation']['view']['now'] for row in rows if row['source_group'] in fold['training_groups']])
            feature_index = payload['feature_names'].index('event_time_s')
            assert payload['parameters']['center'][feature_index] == mean_time
            held_out_rows = [row for row in rows if row['source_group'] == fold['held_out_group'] and row['owner_id'] == 'A']
            candidates = [row['candidate_semantics'] for row in held_out_rows]
            public = held_out_rows[0]['owner_observation']
            version = ranker.load_model(path)
            scores = ranker.score_candidates(public, candidates, version)
            assert np.isfinite(scores).all()
            assert ranker.score_candidates(public, list(reversed(candidates)), version) == list(reversed(scores))
            ranker._MODELS.pop(version)
            assert ranker.score_candidates(public, candidates, path) == scores
            if kind == 'mlp':
                assert len(payload['parameters']['layers']) == 3
                assert payload['torch_threads'] == 1
                assert payload['device'] == 'cpu'
    with pytest.raises(ValueError, match='immutable_model_output'):
        ranker.train_rankers(dataset, output, epochs=2)
    dataset.write_text(dataset.read_text(encoding='utf8') + '\n', encoding='utf8')
    with pytest.raises(ValueError, match='frozen_evaluation_dataset'):
        ranker.evaluate_models(dataset, output)
