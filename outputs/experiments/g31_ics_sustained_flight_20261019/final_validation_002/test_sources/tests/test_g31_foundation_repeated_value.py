"""Small synthetic neural/visibility tests, never a native or FQI acceptance run."""
import ast
import copy
from pathlib import Path
import time

import numpy as np
import pytest

from scripts.experiments.g31_ics_circulation import foundation_repeated_value as value


def contract(identity='job', origin=7, destination=6):
    return {'business_bag_id': identity, 'origin': origin, 'destination': destination, 'arrival': 1.,
        'deadline': 40., 'storage_node': -1, 'storage_release_at': 0., 'storage_min_dwell': 0.,
        'load_seconds': .1, 'unload_seconds': .1, 'hold_seconds': .1,
        'protected_service': True, 'allow_suffix_reroute': True}


def tray(identity='target', node=7, mode='loaded', job='job', available=9.):
    return {'tray_id': identity, 'node': node, 'mode': mode, 'business_bag_id': job,
        'available_at': available, 'edge_from': -1, 'edge_to': -1, 'committed_prefix': [node],
        'generation': 3, 'traversal_id': 5, 'reception_node': -1}


def observation(*, blocked=3):
    local_job = {**contract(), 'status': 'in_transit', 'loaded_at': 8.,
        'storage_entered_at': -1., 'storage_released_at': -1.}
    peer_job = {**contract('peer-job', 6, 3), 'status': 'waiting_for_tray', 'loaded_at': -1.,
        'storage_entered_at': -1., 'storage_released_at': -1.}
    target = tray()
    nodes = [{'node': node, 'resource_owner': 'B', 'capacity': 2, 'occupancy': int(node in (7, blocked)),
        'actual_available': 0} for node in (3, 7, 8)] + [{'node': 6, 'resource_owner': 'A', 'capacity': 2}]
    capture = {'source_owner': 'A', 'target_owner': 'B', 'message_id': 'message', 'captured_at': 9.9,
        'valid_until': 10.1, 'coverage': {'future_arrivals_included': False}, 'jobs': [peer_job],
        'trays': [tray('peer-tray', 6, 'empty', '', 0.)],
        'nodes': [{'node': 6, 'occupancy': 1, 'actual_available': 1}]}
    message = {'message_id': 'message', 'source_owner': 'A', 'target_owner': 'B', 'captured_at': 9.9,
        'delivered_at': 9.95, 'valid_until': 10.1, 'status': 'conditional', 'fresh': True,
        'envelope': {'delivered_at': 9.95, 'status': 'conditional', 'capture': {'capture_v2': {'local_capture': capture}}}}
    return {'schema': value.OBSERVATION_SCHEMA, 'owner': 'B', 'at': 10., 'remaining_horizon_s': 30.,
        'opportunity': {'owner': 'B', 'observed_at': 10., 'phase': 'cycle_route',
            'opportunity_id': 'opaque-opportunity', 'episode_id': 'opaque-episode', 'causal_operation_id': 'opaque-cause',
            'target': copy.deepcopy(target), 'service_ready_at': 11., 'unexecuted_suffix_only': True,
            'execution_authority': False},
        'local_view': {'owner_id': 'B', 'now': 10., 'jobs': [local_job],
            'trays': [target, tray('busy-tray', blocked, 'empty', '', 11.)], 'node_contracts': nodes,
            'edge_contracts': [{'from': 7, 'to': target, 'capacity': 1, 'entry_headway': .1} for target in (3, 8)]},
        'delivered_v3': [message],
        'known_contracts': {'owner': 'B', 'retained_at': 10., 'static_contract_sha256': 'opaque-static-sha',
            'contracts': {'job': contract(), 'peer-job': contract('peer-job', 6, 3)},
            'sources': [{'job': 'job', 'at': 1., 'source': 'own_observation'}, {'job': 'peer-job', 'at': 10., 'source': 'message'}]},
        'own_outbox': {'request': {'kind': 'transfer', 'request': {'request_id': 'request', 'owner_id': 'B'},
            'terminal': True, 'ack': {'observed_at': 9., 'delivered_at': 9.5, 'status': 'received'}}},
        'account_summary': {'actual_locally_available': 0, 'arrived_unfinished_locally_known': 1},
        'privileged_evaluator_state_included': False, 'reference_included': False, 'timing_mode': 'offline_sync'}


def action(destination=3, *, arrival=12.):
    return {'operation_kind': 'route', 'source': 7, 'destination': destination,
        'tray_id': 'target', 'earliest_legal_arrival': arrival, 'native_default_does_not_clear_preference': True}


def test_semantic_features_use_small_domain_time_and_action_state_interactions():
    obs = observation(blocked=3)
    three, eight = value.features(obs, action(3)), value.features(obs, action(8))
    assert three['remaining_horizon_s'] == 30.
    assert three['arrival_delay_s'] == 2.
    assert three['destination_occupancy'] == three['route_x_destination_occupancy'] == 1.
    assert eight['destination_occupancy'] == eight['route_x_destination_occupancy'] == 0.
    assert three['captured_peer_available_empty'] == 1.
    assert not any('1800' in key or '300' in key or 'forecast' in key for key in three)
    assert all(type(x) in (int, float) for x in three.values())


def test_opaque_names_and_node_renumbering_cannot_change_feature_vector():
    obs, proposal = observation(), action()
    expected = value.features(obs, proposal)
    replacements = {key: 'renamed-' + key for key in ('A', 'B', 'job', 'peer-job', 'target', 'busy-tray',
        'peer-tray', 'message', 'request', 'opaque-opportunity', 'opaque-episode', 'opaque-cause', 'opaque-static-sha')}
    node_keys = {'node', 'origin', 'destination', 'storage_node', 'source', 'from', 'to', 'edge_to', 'edge_from', 'reception_node'}
    def renamed(item, key=None):
        if isinstance(item, dict):
            return {(replacements.get(k, k) if key in ('contracts', 'own_outbox') else k): renamed(v, k)
                for k, v in item.items()}
        if isinstance(item, list):
            return [v + 100 if key == 'committed_prefix' else renamed(v) for v in item]
        if isinstance(item, str):
            return replacements.get(item, item)
        if key in node_keys and type(item) is int and item >= 0:
            return item + 100
        return item
    assert value.features(renamed(obs), renamed(proposal)) == expected


@pytest.mark.parametrize('mutate,reason', [
    (lambda o: o.update(labels={'future_return': 1.}), 'observation_schema'),
    (lambda o: o.update(privileged_evaluator_state_included=True), 'privileged_actor_information'),
    (lambda o: o.update(reference_included=True), 'privileged_actor_information'),
    (lambda o: o.update(remaining_horizon_s=-1), 'owner_and_remaining_horizon'),
    (lambda o: o['local_view']['jobs'][0].update(arrival=11.), 'unreleased_or_future_actor_job'),
    (lambda o: o['local_view']['jobs'][0].update(status='unreleased'), 'unreleased_or_future_actor_job'),
    (lambda o: o['local_view']['jobs'][0].update(loaded_at=11.), 'future_observed_job_event'),
    (lambda o: o['local_view']['node_contracts'][-1].update(occupancy=1), 'private_peer_inventory'),
    (lambda o: o['known_contracts']['contracts']['job'].update(arrival=11.), 'known_contract_not_future_truth'),
    (lambda o: o['known_contracts']['sources'][0].update(at=11.), 'unique_causal_contract_discovery'),
    (lambda o: o['known_contracts']['sources'].pop(), 'all_known_contracts_have_observed_sources'),
    (lambda o: o['own_outbox']['request']['ack'].update(delivered_at=11.), 'future_or_undelivered_ack'),
    (lambda o: o['own_outbox']['request']['request'].update(owner_id='A'), 'own_immutable_request_identity'),
    (lambda o: o['delivered_v3'][0].update(delivered_at=11.), 'causal_message_time'),
    (lambda o: o['delivered_v3'][0].update(fresh=False), 'message_freshness_binding'),
    (lambda o: o['delivered_v3'][0].update(target_owner='A'), 'delivered_owner_scope'),
    (lambda o: o['opportunity']['target'].update(node=3), 'target_actual_local_observation'),
    (lambda o: o['account_summary'].update(actual_locally_available=2), 'actual_account_summary_binding'),
])
def test_illegal_or_future_input_fails_closed(mutate, reason):
    obs = observation()
    mutate(obs)
    with pytest.raises(ValueError, match=reason):
        value.features(obs, action())


def test_future_job_in_delivered_capture_rejected_at_capture_time_not_current_time():
    obs = observation()
    capture = obs['delivered_v3'][0]['envelope']['capture']['capture_v2']['local_capture']
    capture['jobs'][0]['arrival'] = 9.99  # Before now, but after the actual capture.
    with pytest.raises(ValueError, match='unreleased_or_future_actor_job'):
        value.features(obs, action())


def test_expired_latest_capture_is_missing_and_does_not_resurrect_older_inventory():
    obs = observation()
    newer = copy.deepcopy(obs['delivered_v3'][0])
    newer.update(message_id='newer', captured_at=9.98, delivered_at=9.99, valid_until=9.995, fresh=False)
    newer['envelope']['delivered_at'] = 9.99
    newer['envelope']['capture']['capture_v2']['local_capture'].update(message_id='newer', captured_at=9.98, valid_until=9.995)
    obs['delivered_v3'].append(newer)
    result = value.features(obs, action())
    assert result['peer_state_missing'] == 1.
    assert result['captured_peer_available_empty'] == result['captured_peer_occupancy'] == 0.
    assert result['known_contract_count'] == 2.  # Observed immutable contracts remain known.


def test_unknown_route_arrival_has_explicit_mask_not_a_zero_time_claim():
    result = value.features(observation(), action(arrival=None))
    assert result['arrival_bound_missing'] == 1.
    assert result['arrival_delay_s'] == 0.
    no_command = action(destination=None)
    no_command['operation_kind'] = 'no_command'
    assert value.features(observation(), no_command)['candidate_destination_missing'] == 1.


def test_actual_handed_off_and_empty_transit_states_are_observed_semantics():
    obs = observation()
    obs['local_view']['jobs'][0]['status'] = 'handed_off'
    capture = obs['delivered_v3'][0]['envelope']['capture']['capture_v2']['local_capture']
    capture['trays'][0].update(mode='empty_transit', reception_node=7)
    capture['nodes'][0]['actual_available'] = 0
    result = value.features(obs, action())
    assert result['own_jobs_handed_off'] == 1.
    assert result['captured_peer_trays_empty_transit'] == result['captured_peer_inflight'] == 1.
    assert result['captured_peer_available_empty'] == 0.


def test_transfer_requires_actual_endpoint_and_causal_time_bounds():
    obs = observation()
    obs['opportunity']['phase'] = 'cycle_return'
    proposal = {'operation_kind': 'transfer', 'source': 7, 'destination': 6, 'tray_id': 'target',
        'earliest_departure': 10.5, 'earliest_legal_arrival': 12.5}
    result = value.features(obs, proposal)
    assert result['departure_delay_s'] == .5
    assert result['arrival_delay_s'] == 2.5
    for changes in ({'earliest_legal_arrival': None}, {'earliest_departure': 13.}, {'destination': 7}, {'source': 3}):
        with pytest.raises(ValueError):
            value.features(obs, dict(proposal, **changes))


def test_runtime_does_not_import_native_flight_training_or_controller_modules():
    tree = ast.parse(Path(value.__file__).read_text(encoding='utf8'))
    imports = [node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
    assert not any(any(token in name for token in ('native', 'controller', 'foundation_flight', 'foundation_repeated_domain')) for name in imports)


def rows():
    return [{'observation': observation(blocked=blocked), 'action': action(destination),
        'target_value': -10. if destination == blocked else 10., 'split': 'train', 'parent_group': 'synthetic-parent-' + str(blocked)}
        for blocked in (3, 8) for destination in (3, 8)]


def test_small_neural_fit_learns_state_action_ranking_and_train_only_normalization():
    training_rows = rows()
    model = value.fit(training_rows, seed=71, epochs=100, deadline=time.monotonic() + 60.,
        objective='synthetic_unit_test_not_native_RL')
    assert model['training_curve'][-1]['mse'] < model['training_curve'][0]['mse'] * .01
    for blocked in (3, 8):
        scores = value.predict(model, [observation(blocked=blocked)] * 2, [action(3), action(8)])
        assert (scores[0] > scores[1]) == (blocked == 8)
    expected = np.asarray([[value.features(row['observation'], row['action'])[key]
        for key in model['feature_names']] for row in training_rows])
    assert np.allclose(model['parameters']['center'], expected.mean(axis=0))
    before = copy.deepcopy(model)
    unseen = observation()
    unseen['remaining_horizon_s'] = 1000.
    assert len(value.predict(model, [unseen], [action()])) == 1
    assert model == before
    assert model['native_execution_authority'] is False
    assert model['td_readiness_certified_by_this_module'] is False
    assert model['opaque_identifiers_are_features'] is False
    assert model['flight_minute_windows_used'] is False
    model['parameters']['target_center'] += 1
    with pytest.raises(ValueError, match='value_model_content_binding'):
        value.predict(model, [observation()], [action()])


def test_fit_rejects_nontraining_rows_and_expired_budget_before_training():
    training_rows = rows()
    training_rows[-1]['split'] = 'test'
    with pytest.raises(ValueError, match='train_only_parent_rows'):
        value.fit(training_rows, seed=71, epochs=5, deadline=time.monotonic() + 60, objective='not_run')
    with pytest.raises(ValueError, match='training_deadline_objective'):
        value.fit(rows(), seed=71, epochs=5, deadline=time.monotonic() - 1, objective='not_run')
