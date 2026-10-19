"""Saved actual endpoint reconstruction and supplied-data refusal tests."""
import copy
import gzip
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_later_seed as later
from scripts.experiments.g31_ics_circulation import planning_capture_v3_contract as inflight

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'outputs/experiments/g31_ics_foundation_learning_20261017/native_001/raw.json.gz'


@pytest.fixture(scope='module')
def saved_raw():
    return json.loads(gzip.decompress(RAW.read_bytes()))


def evidence_from_saved(raw, owner):
    decision = raw['decisions'][owner][0]
    return copy.deepcopy({'schema': later.EVIDENCE_SCHEMA, 'owner': owner,
        'phase': decision['phase'], 'at': decision['at'], 'collection': decision['collection'],
        'information': decision['information'], 'retained': raw['retained_ledgers'][owner],
        'own_calls': [row for row in raw['calls'][:decision['predecision_call_prefix_count']]
                      if row['request']['owner_id'] == owner]})


def selected_peer(evidence):
    return next(row for row in evidence['information']['raw_endpoints']['received']
        if row['capture']['capture_v2']['local_capture']['message_id'] == evidence['collection']['peer_message'])


def redigest(envelope):
    envelope['payload_sha256'] = inflight.capture_digest_v3(envelope['capture'])


@pytest.mark.parametrize('owner,action', [('A', 'return_now'), ('B', 'native_default')])
def test_actual_saved_current_seed_matches_five_native_endpoints(saved_raw, owner, action):
    evidence = evidence_from_saved(saved_raw, owner)
    seed = later.build_seed(evidence)
    assert seed['status'] == 'conditional_current_seed'
    prediction = later.predict(seed, action)
    assert prediction['status'] == 'conditional_prediction'
    actual = {job['business_bag_id']: job['completed_at'] for job in saved_raw['result']['jobs']}
    assert later.delivered.encoded(prediction['completion']) == later.delivered.encoded(actual)
    assert prediction['native_execution_certified'] is False
    assert prediction['native_protection_certified'] is False
    assert prediction['online_executable'] is False
    assert prediction['current_state_at'] == evidence['at'] > .11
    assert all(row['at'] >= evidence['at'] for row in prediction['physical_projection'])


def test_b_preserves_actual_entered_edges_fifo_services_and_completed_prefix(saved_raw):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    entries = {row['tray_id']: row for row in seed['entry_receipts']}
    assert set(entries) == {'E', 'P'}
    assert (entries['E']['edge_from'], entries['E']['edge_to']) == (3, 4)
    assert (entries['P']['edge_from'], entries['P']['edge_to']) == (9, 3)
    assert entries['E']['derived_edge_exit_at'] == 9.92
    assert entries['P']['derived_edge_exit_at'] == 10.049999999999999
    engine = later.Projection(seed, 'native_default')
    engine.seed_current()
    assert engine.trays['E']['scheduled_incoming_node'] == 4
    assert engine.trays['P']['scheduled_incoming_node'] == 3
    assert engine.calendars[3] == [(10.049999999999999, 10.149999999999999)]
    assert engine.trays['L']['ready'] == 9.749999999999995
    assert engine.completed == {'loaded': 7.1999999999999975}
    assert engine.jstatus['reuse2'] == 'waiting_for_tray'
    assert engine.jstatus['reuse1'] == 'in_transit'
    assert engine.storage_passed == {'blocker'}
    assert engine.waiting == {}


def test_actual_a_alternative_is_absolute_and_keeps_original_completion(saved_raw):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'A'))
    baseline = later.predict(seed, 'return_now')
    changed = later.predict(seed, 'return_not_before_7_84')
    assert changed['status'] == 'conditional_prediction'
    assert changed['projected_transfers'][0]['earliest'] == 7.84
    assert changed['projected_transfers'][0]['earliest'] != seed['at'] + .5
    assert changed['completion']['loaded'] == baseline['completion']['loaded']
    assert changed['completion']['reuse1'] == 13.139999999999997
    assert changed['completion']['reuse2'] == 18.55
    assert changed['completion']['reuse1'] > baseline['completion']['reuse1']
    assert changed['completion']['reuse2'] > baseline['completion']['reuse2']


def test_actual_b_nondefault_is_evaluated_not_masked(saved_raw):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    baseline = later.predict(seed, 'native_default')
    changed = later.predict(seed, 'prefer_8')
    assert changed['status'] == 'conditional_prediction'
    assert changed['completion']['reuse1'] == 13.949999999999992
    assert changed['completion']['reuse2'] == 19.36
    assert changed['completion']['reuse1'] > baseline['completion']['reuse1']
    assert changed['projected_commands'][0]['next'] == 8
    assert baseline['projected_commands'][0]['job'] == 'reuse2'
    assert baseline['projected_commands'][0]['next'] == 3


@pytest.mark.parametrize('change', ['missing_entry', 'entry_generation', 'expired',
                                  'undelivered', 'wrong_status', 'peer_owner', 'receiving'])
def test_changed_peer_v3_is_unknown_even_with_recomputed_digest(saved_raw, change):
    evidence = evidence_from_saved(saved_raw, 'B')
    envelope = selected_peer(evidence)
    body = envelope['capture']
    local = body['capture_v2']['local_capture']
    if change == 'missing_entry':
        body['extension']['source_observed_inflight'] = []
    elif change == 'entry_generation':
        body['extension']['source_observed_inflight'][0]['generation'] += 1
    elif change == 'expired':
        local['valid_until'] = evidence['at']
    elif change == 'undelivered':
        envelope['delivered_at'] = evidence['at'] + .01
    elif change == 'wrong_status':
        envelope['status'] = 'failed'
    elif change == 'peer_owner':
        local['source_owner'] = 'B'
    elif change == 'receiving':
        local['trays'][0]['reception_node'] = 3
    redigest(envelope)
    result = later.build_seed(evidence)
    assert result['status'] == 'unknown'
    assert result['reasons']


@pytest.mark.parametrize('change', ['generation', 'moving', 'owner', 'pending', 'calls'])
def test_current_owner_and_submission_prefix_are_not_repaired(saved_raw, change):
    evidence = evidence_from_saved(saved_raw, 'B')
    view = evidence['information']['raw_endpoints']['view']
    if change == 'generation':
        view['trays'][0]['generation'] += 1
    elif change == 'moving':
        view['trays'][0]['edge_to'] = 3
    elif change == 'owner':
        view['owner_id'] = 'A'
    elif change == 'pending':
        view['client_requests'][0]['last_delivered_ack'] = None
    else:
        first = next(index for index, row in enumerate(evidence['own_calls']) if row['kind'] == 'transfer')
        del evidence['own_calls'][first]
    assert later.build_seed(evidence)['status'] == 'unknown'


@pytest.mark.parametrize('field', ['bundle', 'entry_receipts', 'retained_preferences', 'action_ids', 'at'])
def test_saved_seed_mutation_is_rejected_not_authority(saved_raw, field):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    seed[field] = None
    assert later.predict(seed, 'native_default')['status'] == 'unknown'


def test_saved_input_has_no_native_authority_and_ignores_unvalidated_derived_bundle(saved_raw):
    evidence = evidence_from_saved(saved_raw, 'B')
    evidence['information']['bundle'] = {'status': 'certified_fake', 'now': 0}
    seed = later.build_seed(evidence)
    assert seed['status'] == 'conditional_current_seed'
    assert seed['native_delivery_verified'] is False
    assert seed['bundle']['now'] == evidence['at']
    assert seed['online_executable'] is False
    assert later.predict(seed, None)['status'] == 'unknown'


def route_state(seed):
    bundle = copy.deepcopy(seed['bundle'])
    tray = bundle['trays']['L']
    request = {'request_id': 'unit-existing-route', 'owner_id': 'B', 'kind': 'route',
        'business_bag_id': tray['business_bag_id'], 'tray_id': 'L', 'from': 7, 'next': 8,
        'expected_generation': tray['generation'], 'expected_traversal': tray['traversal_id'],
        'expiry': bundle['now'] + 5., 'message_delay': .01}
    actions = [{'kind': 'route', 'request_id': request['request_id'], 'source_owner': 'B',
        'last_delivered_ack': {'status': 'updated', 'delivered_at': bundle['now'] - .1, 'sequence': 1}}]
    bundle['source_records'] = [{'owner': 'B', 'submitted_physical_actions': actions}]
    bundle['owner_current_action_facts'] = {'actions': copy.deepcopy(actions)}
    bundle['owner_current_action_facts']['actions'][0]['last_delivered_ack']['executed_at'] = bundle['now'] - .12
    calls = [{'at': bundle['now'] - .2, 'kind': 'route', 'retry': False, 'request': request}]
    return bundle, calls


def test_existing_preference_survives_no_new_command_unit_seed(saved_raw):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    bundle, calls = route_state(seed)
    preferences, history = later.retained_preferences(bundle, calls, 'B')
    assert history[0]['applicable_to_current_prefix'] is True
    seed['retained_preferences'] = preferences
    engine = later.Projection(seed, 'native_default')
    engine.seed_current()
    assert engine.trays['L']['preference']['next'] == 8
    assert engine.commands == []
    assert not any(event[3] == 'command' for event in engine.events)


@pytest.mark.parametrize('field', ['expected_generation', 'expected_traversal', 'expiry'])
def test_stale_preference_is_retained_as_history_not_installed(saved_raw, field):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    bundle, calls = route_state(seed)
    calls[0]['request'][field] = -1
    preferences, history = later.retained_preferences(bundle, calls, 'B')
    assert preferences == {}
    assert history[0]['applicable_to_current_prefix'] is False


def test_missing_existing_route_payload_is_precise_unknown_not_clear(saved_raw):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    bundle, calls = route_state(seed)
    bundle['source_records'][0]['owner'] = 'A'
    with pytest.raises(ValueError, match='missing_retained_route_payload:unit-existing-route'):
        later.retained_preferences(bundle, calls, 'B')


def test_initial_guard_stays_closed_for_later_state(saved_raw):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    assert later.physics.previous.revalidate(seed['bundle'])['status'].startswith('unknown')
    assert later.Projection.run is not later.physics.previous.original.Projection.run


@pytest.mark.parametrize('owner', ['A', 'B'])
def test_real_seed_predictions_use_unchanged_initial_reference_guard(saved_raw, owner):
    from scripts.experiments.g31_ics_circulation import foundation_later_control as control
    reference = control.initial_reference(saved_raw['initial_owners'][owner])
    original = copy.deepcopy(reference)
    seed = later.build_seed(evidence_from_saved(saved_raw, owner))
    default, alternative = later.ACTIONS[seed['phase']]
    accepted = control.protected(later.predict(seed, default), reference)
    rejected = control.protected(later.predict(seed, alternative), reference)
    assert accepted['status'] == 'passed'
    assert all(value == 0. for value in accepted['per_job_delta'].values())
    assert rejected['status'] == 'rejected'
    assert rejected['per_job_delta']['reuse1'] > 0
    assert rejected['per_job_delta']['reuse2'] > 0
    assert reference == original


def test_preference_uses_execution_order_not_latest_retry_ack(saved_raw):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    bundle, calls = route_state(seed)
    newer_call = copy.deepcopy(calls[0])
    newer_call['at'] += .01
    newer_call['request'].update(request_id='newer-command', next=3)
    calls.append(newer_call)
    newer_action = copy.deepcopy(bundle['source_records'][0]['submitted_physical_actions'][0])
    newer_action['request_id'] = 'newer-command'
    newer_action['last_delivered_ack']['delivered_at'] -= .01
    bundle['source_records'][0]['submitted_physical_actions'].append(newer_action)
    newer_current = copy.deepcopy(newer_action)
    newer_current['last_delivered_ack']['executed_at'] = bundle['now'] - .11
    bundle['owner_current_action_facts']['actions'].append(newer_current)
    preferences, _ = later.retained_preferences(bundle, calls, 'B')
    assert preferences['L']['next'] == 3


def test_missing_retained_execution_order_is_unknown(saved_raw):
    seed = later.build_seed(evidence_from_saved(saved_raw, 'B'))
    bundle, calls = route_state(seed)
    del bundle['owner_current_action_facts']['actions'][0]['last_delivered_ack']['executed_at']
    with pytest.raises(ValueError, match='missing_retained_route_execution_epoch'):
        later.retained_preferences(bundle, calls, 'B')
