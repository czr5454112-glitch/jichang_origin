"""Saved supplied-data checks, never native freshness or cache authorization."""
import copy
import gzip
import json
import math
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_service_refresh as refresh
from scripts.experiments.g31_ics_circulation import planning_capture_v3_contract as inflight


RAW = Path(__file__).resolve().parents[1] / 'outputs/experiments/g31_ics_foundation_learning_20261017/native_001/raw.json.gz'
REFERENCE = '1' * 64


@pytest.fixture(scope='module')
def saved():
    return json.loads(gzip.decompress(RAW.read_bytes()))


def record(raw, owner='B'):
    decision = raw['decisions'][owner][0]
    evidence = {'schema': refresh.later.EVIDENCE_SCHEMA, 'owner': owner,
        'phase': decision['phase'], 'at': decision['at'], 'collection': decision['collection'],
        'information': decision['information'], 'retained': raw['retained_ledgers'][owner],
        'own_calls': [call for call in raw['calls'][:decision['predecision_call_prefix_count']]
                      if call['request']['owner_id'] == owner]}
    return refresh.make_record(evidence, episode_id='saved_native_001', original_reference_sha256=REFERENCE)


@pytest.mark.parametrize('owner', ['A', 'B'])
def test_repeated_real_evidence_revalidates_without_prediction_or_cache_authority(saved, monkeypatch, owner):
    supplied = record(saved, owner)
    frozen = copy.deepcopy(supplied)

    def no_prediction(*args, **kwargs):
        raise AssertionError('read-only audit cannot run a suffix')

    monkeypatch.setattr(refresh.later, 'predict', no_prediction)
    result = refresh.refresh_audit(supplied, supplied, audit_at=supplied['evidence']['at'])
    assert result['status'] == 'unchanged_revalidated'
    assert result['seed_build_attempts'] == 2
    assert result['prediction_calls'] == 0
    assert result['refresh_required'] is False
    assert result['changed_dependencies'] == []
    assert result['reference_identity_preserved'] is True
    assert result['original_reference_sha256'] == REFERENCE
    assert result['dependency_closure']['scope'] == 'full_model_domain'
    assert len(result['dependency_closure']['entities']['jobs']) == 5
    assert len(result['dependency_closure']['entities']['trays']) == 3
    assert result['dependency_closure']['reused_suffix_entities'] == []
    for field in ('new_native_observation_verified', 'cache_execution_authorized',
                  'local_suffix_certified', 'native_computation_reduced', 'online_executable',
                  'native_execution_certified', 'native_protection_certified'):
        assert result[field] is False
    assert supplied == frozen
    refresh.later.delivered.encoded(result)


def test_record_is_detached_and_declares_no_validation(saved):
    original = record(saved)
    other = refresh.make_record(original['evidence'], episode_id='another', original_reference_sha256=REFERENCE)
    other['evidence']['phase'] = 'initial'
    assert original['evidence']['phase'] == 'first_reuse_route'
    assert 'status' not in other


@pytest.mark.parametrize('change,reason', [('episode', 'different_episode'), ('owner', 'different_owner'),
    ('reference', 'original_reference_changed'), ('missing_episode', 'episode_identity'),
    ('wrong_owner', 'record_evidence_owner_mismatch'), ('schema', 'record_schema')])
def test_pairing_and_original_reference_fail_closed(saved, change, reason):
    previous, current = record(saved), record(saved)
    if change == 'episode':
        current['episode_id'] = 'different_counterfactual'
    elif change == 'owner':
        current = record(saved, 'A')
    elif change == 'reference':
        current['original_reference_sha256'] = '2' * 64
    elif change == 'missing_episode':
        del current['episode_id']
    elif change == 'wrong_owner':
        current['owner'] = 'A'
    else:
        current['schema'] = 'initial_schema'
    result = refresh.refresh_audit(previous, current)
    assert result['status'] == 'unknown'
    assert reason in result['reasons']
    assert result['original_reference_sha256'] == REFERENCE
    assert result['refresh_required'] is True
    assert result['cache_execution_authorized'] is False


@pytest.mark.parametrize('offset', [-.01, .01, 10.])
def test_old_snapshot_cannot_be_current_by_advancing_or_rewinding_a_clock(saved, offset):
    supplied = record(saved)
    result = refresh.refresh_audit(supplied, supplied, audit_at=supplied['evidence']['at'] + offset)
    assert result['status'] == 'unknown'
    assert result['reasons'] == ['current_evidence_epoch_not_audit_epoch']
    assert result['refresh_required'] is True


@pytest.mark.parametrize('audit_at', [True, 'now', math.nan, math.inf])
def test_invalid_audit_epoch_is_not_coerced(saved, audit_at):
    supplied = record(saved)
    result = refresh.refresh_audit(supplied, supplied, audit_at=audit_at)
    assert result['status'] == 'unknown'
    assert result['reasons'] == ['invalid_audit_epoch']


@pytest.mark.parametrize('change', ['expired', 'generation', 'resource', 'command', 'initial_schema'])
def test_actual_raw_changes_cannot_be_hidden_behind_self_reported_seed(saved, change):
    previous, current = record(saved), record(saved)
    evidence = current['evidence']
    current['seed'] = {'status': 'conditional_current_seed', 'native_protection_certified': True}
    current['status'] = 'unchanged_revalidated'
    if change == 'expired':
        envelope = next(item for item in evidence['information']['raw_endpoints']['received']
            if item['capture']['capture_v2']['local_capture']['message_id'] == evidence['collection']['peer_message'])
        envelope['capture']['capture_v2']['local_capture']['valid_until'] = evidence['at']
        envelope['payload_sha256'] = inflight.capture_digest_v3(envelope['capture'])
    elif change == 'generation':
        evidence['information']['raw_endpoints']['view']['trays'][0]['generation'] += 1
    elif change == 'resource':
        resource = next(row for row in evidence['information']['raw_endpoints']['view']['node_contracts']
                        if row['resource_owner'] == evidence['owner'])
        resource['occupancy'] += 1
    elif change == 'command':
        command = next(call for call in evidence['own_calls'] if call['kind'] == 'transfer')
        command['request']['request_id'] = 'rewritten-immutable-command'
    else:
        evidence['schema'] = 'g31.foundation.initial_evidence.v1'
    result = refresh.refresh_audit(previous, current)
    assert result['status'] == 'unknown'
    assert result['refresh_required'] is True
    assert result['current_validation']['status'] == 'unknown'
    assert result['reference_identity_preserved'] is True


def test_unvalidated_derived_bundle_does_not_supply_dependencies_but_change_invalidates(saved):
    previous, current = record(saved), record(saved)
    current['evidence']['information']['bundle'] = {'status': 'trusted', 'jobs': {}}
    result = refresh.refresh_audit(previous, current)
    assert result['status'] == 'full_refresh_required'
    assert result['changed_dependencies'] == ['supplied_evidence']
    assert len(result['dependency_closure']['entities']['jobs']) == 5
    assert result['previous_evidence_sha256'] != result['current_evidence_sha256']


@pytest.mark.parametrize('field', ['own_outbox', 'unclassified_future_dependency'])
def test_unclassified_evidence_and_outbox_changes_cannot_look_unchanged(saved, field):
    previous, current = record(saved), record(saved)
    current['evidence'][field] = {'new_unclassified_fact': 1}
    result = refresh.refresh_audit(previous, current)
    assert result['status'] == 'full_refresh_required'
    assert 'supplied_evidence' in result['changed_dependencies']
    if field == 'own_outbox':
        assert field in result['changed_dependencies']
    assert result['cache_execution_authorized'] is False


@pytest.mark.parametrize('field', ['jobs', 'trays', 'resources', 'stability', 'contract', 'protocol'])
def test_dependency_diff_unit_fixture_always_closes_full_domain(saved, monkeypatch, field):
    supplied = record(saved)
    previous = refresh.later.build_seed(supplied['evidence'])
    current = copy.deepcopy(previous)
    if type(current['bundle'][field]) is dict:
        current['bundle'][field]['unit_change'] = 1
    else:
        current['bundle'][field][0]['unit_change'] = 1
    seeds = iter((previous, current))
    monkeypatch.setattr(refresh.later, 'build_seed', lambda evidence: next(seeds))
    result = refresh.refresh_audit(supplied, supplied)
    assert result['status'] == 'full_refresh_required'
    assert result['changed_dependencies']
    assert result['dependency_closure']['scope'] == 'full_model_domain'
    assert result['dependency_closure']['reused_suffix_entities'] == []


@pytest.mark.parametrize('change,reason', [('time', 'observation_time_regressed'),
    ('prefix', 'immutable_own_submission_prefix_changed'), ('completed', 'completed_prefix_changed:loaded'),
    ('source', 'source_epoch_regressed:A')])
def test_transition_unit_fixture_rejects_rewritten_or_out_of_order_history(saved, monkeypatch, change, reason):
    supplied = record(saved)
    previous = refresh.later.build_seed(supplied['evidence'])
    current = copy.deepcopy(previous)
    if change == 'time':
        current['at'] -= .01
    elif change == 'prefix':
        current['evidence']['own_calls'].pop(0)
    elif change == 'completed':
        current['bundle']['completed_prefix']['loaded'] += .01
    else:
        next(source for source in current['bundle']['source_records'] if source['owner'] == 'A')['captured_at'] -= .01
    seeds = iter((previous, current))
    monkeypatch.setattr(refresh.later, 'build_seed', lambda evidence: next(seeds))
    result = refresh.refresh_audit(supplied, supplied)
    assert result['status'] == 'unknown'
    assert result['reasons'] == [reason]
    assert result['refresh_required'] is True
