"""Current binding, validation and reuse contracts; no native or model fit."""
import copy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_action_value as value
from scripts.experiments.g31_ics_circulation import foundation_airport_learning_public as public
from test_g31_foundation_action_value import observation, action, compact_observation, inbound_observation
from test_g31_foundation_airport_learning_public import record, forecast


def model_for(row):
    names = sorted(value.features(row, action()))
    return {'schema': value.MODEL_SCHEMA, 'feature_schema': value.FEATURE_SCHEMA,
        'information_variant': row['information_variant'], 'mapping_version': row['mapping_version'],
        'feature_names': names, 'parameters': {'center': [0.] * len(names), 'scale': [1.] * len(names),
            'layers': [{'weight': [[.001 * (i + 1) for i in range(len(names))]], 'bias': [.3]}],
            'target_center': 4., 'target_scale': 2.}}


@pytest.mark.parametrize('factory', [observation, compact_observation, inbound_observation])
def test_prepared_feature_rows_and_predictions_preserve_exact_values(factory):
    row = factory()
    actions = [action('left'), action('right')]
    expected = [value.features(row, candidate) for candidate in actions]
    context = value.prepare_observation(row)
    matrix = value.prepare_feature_matrix(context, actions)
    assert json.dumps(matrix.feature_rows(), sort_keys=True) == json.dumps(expected, sort_keys=True)
    model = model_for(row)
    assert value.predict_prepared(value.prepare_model(model), matrix, context=context) == value.predict(
        model, [row] * len(actions), actions)


def test_same_batch_validation_once_then_three_forwards_without_revalidation(monkeypatch):
    row = observation()
    frozen = value.prepare_model(model_for(row))
    original = value.validate_accounts
    calls = []
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(value, 'validate_accounts', counted)
    context = value.prepare_observation(row)
    matrix = value.prepare_feature_matrix(context, [action()] * 13)
    for _ in range(3):
        assert len(value.predict_prepared(frozen, matrix, context=context)) == 13
    assert len(calls) == 1


def test_current_and_arrays_cannot_be_mutated_or_relabelled():
    row = observation()
    context = value.prepare_observation(row)
    matrix = value.prepare_feature_matrix(context, [action()])
    frozen = value.prepare_model(model_for(row))
    original = value.predict_prepared(frozen, matrix, context=context)
    row['now'] += 1
    row['circulation_accounts']['current_free_trays'].clear()
    assert context.observation['now'] == 60000.
    assert value.predict_prepared(frozen, matrix, context=context) == original
    with pytest.raises(TypeError):
        context.observation['now'] = 70000.
    with pytest.raises(FrozenInstanceError):
        context.observation_sha256 = 'changed'
    for array in (matrix.matrix, frozen.center, frozen.scale, *frozen.layers[0]):
        with pytest.raises(ValueError):
            array.setflags(write=True)
    with pytest.raises(ValueError, match='current_binding'):
        value.predict_prepared(frozen, matrix, context=value.prepare_observation(observation()))
    with pytest.raises(ValueError, match='base_owner_time'):
        value.prepare_observation(row)


@pytest.mark.parametrize('factory', [value.PreparedObservation, value.PreparedFeatureMatrix, value.PreparedModel])
def test_prepared_objects_have_no_public_trusted_constructor(factory):
    with pytest.raises(TypeError):
        factory()
    with pytest.raises(TypeError):
        factory(trusted=True)


@pytest.mark.parametrize('mutate,reason', [
    (lambda row: row['demand_forecast'].update(forecast_origin=59999.), 'current_time_projection'),
    (lambda row: row['base_observation'].update(owner='other'), 'base_owner_time'),
    (lambda row: row['circulation_accounts']['current_free_trays'].append(
        copy.deepcopy(row['circulation_accounts']['current_free_trays'][0])), 'multiple_supply'),
    (lambda row: row['circulation_accounts']['coverage_by_account_region']['current_free_trays']['left'].update(
        observed_at=60001.), 'coverage_time'),
])
def test_preparation_rejects_malformed_external_observation(mutate, reason):
    row = observation()
    mutate(row)
    with pytest.raises(ValueError, match=reason):
        value.prepare_observation(row)


def test_partial_forecast_mask_stays_unknown_after_freezing_list_to_tuple():
    row = observation()
    row['demand_forecast']['missing_mask_by_region']['right'] = [True] + [False] * 29
    context = value.prepare_observation(row)
    features = value.prepare_feature_matrix(context, [action()]).feature_rows()[0]
    assert features['destination_demand_missing_60'] == 1.
    assert features['destination_new_demand_60'] == 0.


def test_public_adapter_prepares_current_and_preserves_batch_with_one_public_validation(monkeypatch):
    row, demand = record(), forecast()
    wrapped, audit = public.wrap_record(row, demand, episode_id='e', episode_end=59400.)
    candidates = public.proposal_actions(row)
    original = public.validate_public
    calls = []
    def counted(observation):
        calls.append(1)
        return original(observation)
    monkeypatch.setattr(public, 'validate_public', counted)
    context, actual_audit, actual_candidates = public.prepare_record(row, demand, episode_id='e', episode_end=59400.)
    assert len(calls) == 1
    assert context.to_observation() == wrapped
    assert actual_audit == audit and actual_candidates == candidates
    row['observation']['trays'][0]['generation'] += 1
    assert context.observation['base_observation']['trays'][0]['generation'] == 1


def test_model_validation_and_information_contracts_survive_preparation():
    row = observation()
    model = model_for(row)
    context = value.prepare_observation(row)
    matrix = value.prepare_feature_matrix(context, [action()])
    for field, changed, reason in [('information_variant', 'no_plan', 'information_variant'),
                                   ('mapping_version', 'other', 'mapping_version')]:
        malformed = copy.deepcopy(model)
        malformed[field] = changed
        with pytest.raises(ValueError, match=reason):
            value.predict_prepared(value.prepare_model(malformed), matrix, context=context)
    malformed = copy.deepcopy(model)
    malformed['parameters']['layers'][0]['weight'][0][0] = float('nan')
    with pytest.raises(ValueError, match='layer_shape'):
        value.prepare_model(malformed)


def test_frozen_behavior_checkpoint_keeps_provenance_and_rechecks_every_current(tmp_path):
    from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_consumer as consumer
    from test_g31_foundation_airport_behavior_consumer import fixture, save
    _, descriptor = fixture(tmp_path)
    row = observation()
    model = json.loads(Path(descriptor['path']).read_bytes())
    model.update(model_for(row))
    model_path = Path(descriptor['path'])
    reference = save(model_path, model)
    receipt_path = Path(descriptor['training_receipt']['path'])
    receipt = json.loads(receipt_path.read_bytes())
    receipt['models'][0].update(checkpoint=reference, content_sha256=consumer.digest(model))
    descriptor = {**reference, 'training_receipt': save(receipt_path, receipt)}
    checkpoint = consumer.prepare_behavior_checkpoint(row, descriptor)
    context = value.prepare_observation(row)
    matrix = value.prepare_feature_matrix(context, [action()])
    assert consumer.predict_prepared_behavior_checkpoint(context, matrix, checkpoint, descriptor=descriptor)
    with pytest.raises(ValueError, match='descriptor_binding'):
        consumer.predict_prepared_behavior_checkpoint(context, matrix, checkpoint, descriptor={**descriptor, 'sha256': 'other'})
    with pytest.raises(ValueError, match='current_binding'):
        consumer.predict_prepared_behavior_checkpoint(value.prepare_observation(row), matrix, checkpoint, descriptor=descriptor)
    early = observation()
    early['now'] = early['base_observation']['at'] = 57000.
    early['demand_forecast']['forecast_origin'] = 57000.
    for account in early['circulation_accounts']['coverage_by_account_region'].values():
        for coverage in account.values():
            coverage['observed_at'] = 57000.
    early['circulation_accounts']['current_free_trays'][0]['observed_at'] = 57000.
    early_context = value.prepare_observation(early)
    with pytest.raises(ValueError, match='unavailable_before_registered'):
        consumer.predict_prepared_behavior_checkpoint(early_context,
            value.prepare_feature_matrix(early_context, [action()]), checkpoint, descriptor=descriptor)
    # An unrelated or historical implementation pin cannot be relabelled as
    # this implementation just because the checkpoint's numeric shape fits.
    plan_path = Path(receipt['plan']['path'])
    plan = json.loads(plan_path.read_bytes())
    plan['source_sha256'][str(Path(value.__file__).resolve())] = 'old_source'
    changed_plan = save(plan_path, plan)
    model['behavior_evidence']['training_plan'] = changed_plan
    reference = save(model_path, model)
    receipt.update(plan=changed_plan)
    receipt['models'][0].update(checkpoint=reference, content_sha256=consumer.digest(model))
    descriptor = {**reference, 'training_receipt': save(receipt_path, receipt)}
    with pytest.raises(ValueError, match='fixed_trained_feature'):
        consumer.prepare_behavior_checkpoint(row, descriptor)
