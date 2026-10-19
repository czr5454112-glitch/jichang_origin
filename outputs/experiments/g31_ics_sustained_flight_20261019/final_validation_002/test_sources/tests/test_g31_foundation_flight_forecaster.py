"""Small synthetic causal forecast checks; no source-day fitting or native run."""
import ast
import copy
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_flight_data as data
from scripts.experiments.g31_ics_circulation import foundation_flight_forecaster as forecast
from scripts.experiments.g31_ics_circulation import foundation_flight_training as training


def row(ref, std, entry, region='legacy_start_0', ident=None):
    return {'bag_id': ident or ref, 'parent_flight_ref': ref, 'flight_ref': ref,
        'copy_lineage': 'original_1x', 'arrived_at': entry, 'scheduled_std': std,
        'region': region, 'loader': 'private-loader', 'original_start': 0}


def inputs():
    rows = [row('train-a', 36000., 35820.), row('train-b', 43200., 43020., 'legacy_start_1'),
        row('development', 50000., 49820.), row('test', 60000., 59820.)]
    context, split = data.build_artifacts(rows)
    return rows, context, split


def model_and_plan():
    _, context, _ = inputs()
    context['owner_scope'] = 'A'
    context['entries'] = [dict(context['entries'][-1], scheduled_event_at=600.)]
    params = {'shape': 2., 'rate': 1., 'cdf_edges': [-600., 0.], 'cdf_values': [0., 1.]}
    model = {'schema': forecast.MODEL_SCHEMA, 'regions': ['legacy_start_0'],
        'parameters': {'legacy_start_0': params}, 'mapping_version': data.MAPPING_VERSION,
        'time_basis': data.TIME_BASIS, 'frozen_at': 0., 'training_labels_closed_at': 0.,
        'calibration_status': 'synthetic_uncalibrated', 'native_execution_authority': False,
        'historical_arrival_rate_by_region': {'legacy_start_0': 1. / 300.}}
    model['model_sha256'] = forecast.digest(model)
    return model, context


def counts(context, *, n=0, observed=300.):
    return {'schema': forecast.COUNTS_SCHEMA, 'owner_scope': 'A', 'observed_at': observed,
        'complete_history_from': 0., 'mapping_version': data.MAPPING_VERSION,
        'source_kind': 'explicit_synthetic_asof_arrival_feed',
        'counts_by_flight': {context['entries'][0]['flight_ref']: {'legacy_start_0': n}}}


def predict(model, context, **kwargs):
    return forecast.predict(context, model, now=300., owner='A', **kwargs)


def summary(result, horizon='300'):
    return result['window_summaries_by_region']['legacy_start_0'][horizon]


def test_forecast_integrates_future_mass_and_cumulative_gamma_covariance():
    model, context = model_and_plan()
    result = predict(model, context)
    assert result['bin_edges_seconds'] == list(range(0, 1801, 60))
    assert result['absolute_bin_edges'][0] == 300.
    assert summary(result)['mean'] == pytest.approx(1.)
    assert summary(result)['variance'] == pytest.approx(1.5)
    assert sum(result['uncertainty_by_region']['legacy_start_0']['variance'][:5]) == pytest.approx(1.1)
    assert result['native_execution_authority'] is False
    assert result['predicted_inventory_is_actual'] is False


def test_missing_counts_are_prior_and_differ_from_observed_zero():
    model, context = model_and_plan()
    no_counts = predict(model, context)
    unknown = counts(context)
    unknown['counts_by_flight'] = {}
    result_unknown = predict(model, context, observed_counts=unknown)
    zero = predict(model, context, observed_counts=counts(context))
    assert summary(no_counts) == summary(result_unknown)
    assert not result_unknown['observed_count_update']
    assert summary(zero)['mean'] == pytest.approx(2. / 3.)
    assert zero['observed_count_update']


def test_positive_observed_count_changes_posterior_but_only_predicts_future():
    model, context = model_and_plan()
    result = predict(model, context, observed_counts=counts(context, n=4))
    assert summary(result)['mean'] == pytest.approx(2.)
    assert result['information_cutoffs']['observed_arrivals_through'] == 300.
    assert result['counts_missing_is_observed_zero'] is False


@pytest.mark.parametrize('change', [
    {'observed_at': 301.}, {'complete_history_from': 10.}, {'owner_scope': 'B'},
    {'mapping_version': 'invented'}, {'source_kind': 'private_future_truth'},
    {'counts_by_flight': {'unknown': {'legacy_start_0': 0}}},
])
def test_illegal_count_provenance_is_rejected(change):
    model, context = model_and_plan()
    observation = counts(context)
    observation.update(change)
    with pytest.raises(ValueError):
        predict(model, context, observed_counts=observation)


@pytest.mark.parametrize('value', [-1, True, .5, float('nan')])
def test_counts_are_nonnegative_integers(value):
    model, context = model_and_plan()
    with pytest.raises(ValueError):
        predict(model, context, observed_counts=counts(context, n=value))


def test_later_origin_reintegrates_cdf_without_renewing_source_timestamp():
    model, context = model_and_plan()
    initial = predict(model, context)
    later = forecast.predict(context, model, now=540., owner='A')
    assert summary(later)['mean'] == pytest.approx(.2)
    assert summary(later)['mean'] < summary(initial)['mean']
    assert later['information_cutoffs']['plan_received_at'] == initial['information_cutoffs']['plan_received_at'] == 0.
    assert later['context_sha256'] == initial['context_sha256']


def test_new_legal_plan_changes_prediction_cancelled_plan_does_not_create_inventory():
    model, context = model_and_plan()
    initial = predict(model, context)
    changed = copy.deepcopy(context)
    changed['version'] = 2
    changed['entries'][0]['scheduled_event_at'] = 2400.
    shifted = predict(model, changed)
    assert summary(shifted)['mean'] == 0.
    assert shifted['context_sha256'] != initial['context_sha256']
    changed['entries'][0]['plan_status'] = 'cancelled'
    assert sum(predict(model, changed)['new_demand_mean_by_region']['legacy_start_0']) == 0.


def test_missing_context_has_missing_values_not_zero_demand():
    model, _ = model_and_plan()
    result = predict(model, None)
    assert result['missing_mask_by_region']['legacy_start_0']
    assert result['new_demand_mean_by_region']['legacy_start_0'] == [None] * 30
    assert summary(result) is None


def test_model_cannot_be_consumed_before_label_freeze_or_after_content_tampering():
    model, context = model_and_plan()
    model['frozen_at'] = 301.
    model['model_sha256'] = forecast.digest({key: value for key, value in model.items() if key != 'model_sha256'})
    with pytest.raises(ValueError, match='not_yet_frozen'):
        predict(model, context)
    model['frozen_at'] = 0.
    with pytest.raises(ValueError, match='content_binding'):
        predict(model, context)


def event(at=300.):
    return {'schema': forecast.EVENT_SCHEMA, 'bag_id': 'arrived-bag', 'region': 'legacy_start_0',
        'arrived_at': at, 'received_at': at, 'owner_scope': 'A'}


def test_no_plan_baseline_reacts_to_arrived_events_and_rejects_future_or_duplicate_events():
    model, _ = model_and_plan()
    empty = forecast.recent_rate_forecast(model, now=300., owner='A', arrival_events=[])
    seen = forecast.recent_rate_forecast(model, now=300., owner='A', arrival_events=[event()])
    assert summary(seen)['mean'] > summary(empty)['mean']
    assert seen['context_sha256'] is None
    for events in ([event(301.)], [event(), event()], [dict(event(), future_truth=9)]):
        with pytest.raises(ValueError):
            forecast.recent_rate_forecast(model, now=300., owner='A', arrival_events=events)


def test_split_uses_parent_STD_and_purges_cross_boundary_statistical_windows():
    rows, context, split = inputs()
    assert [entry['split'] for entry in split['group_roster']] == ['train', 'train', 'development', 'test']
    assert len(context['entries']) == 4
    assert all(entry['planned_injection_region'] is None for entry in context['entries'])
    assert all('arrived_at' not in entry and 'loader' not in entry for entry in context['entries'])
    assert split['all_physical_source_rows_retained']
    assert all(window['label_window_end'] <= (57600 if window['split'] == 'development' else 86400)
        for window in split['evaluation_windows'])
    assert split['purged_statistical_windows']
    assert len(rows) == 4


@pytest.mark.parametrize('change', [{'arrived_at': 36001.}, {'copy_lineage': 'copied'}, {'parent_flight_ref': 'other'}])
def test_invalid_closure_or_unregistered_lineage_fails_closed(change):
    rows, _, _ = inputs()
    rows[0].update(change)
    with pytest.raises(ValueError):
        data.build_artifacts(rows)


def test_small_closed_form_fit_includes_zero_groups_and_ignores_development_test_labels():
    rows, context, split = inputs()
    original, history = training.fit(rows, context, split)
    poisoned = copy.deepcopy(rows)
    poisoned.extend(row('test', 60000., 59999., ident='test-extra-' + str(i)) for i in range(20))
    poisoned[2]['arrived_at'] = 0.
    changed, _ = training.fit(poisoned, context, split)
    assert original['parameters'] == changed['parameters']
    assert original['training_bag_count'] == 2
    assert original['training_parent_count'] == 2
    assert original['parameters']['legacy_start_0']['zero_count_groups_included'] == 1
    assert original['parameters']['legacy_start_0']['shape'] / original['parameters']['legacy_start_0']['rate'] == pytest.approx(.5)
    assert original['parameters']['legacy_start_53']['pooled_zero_region_fallback']
    assert len(history['steps']) == 7
    assert all(item['negative_log_likelihood_per_group'] >= 0 for item in history['steps'])


def test_training_rejects_parent_labels_after_cutoff_even_if_arrivals_are_early():
    rows, context, split = inputs()
    split['group_roster'][-1]['split'] = 'train'
    with pytest.raises(ValueError, match='closed_training_parent_labels'):
        training.fit(rows, context, split)


def test_asof_auxiliary_feed_excludes_future_labels_and_is_explicitly_synthetic():
    rows, context, _ = inputs()
    observation, events = training.public_observations(rows, context, now=43200., owner=context['owner_scope'])
    assert len(events) == 2
    assert observation['source_kind'] == 'explicit_synthetic_asof_arrival_feed'
    assert sum(sum(values.values()) for values in observation['counts_by_flight'].values()) == 2
    assert all(set(item) == {'schema', 'bag_id', 'region', 'arrived_at', 'received_at', 'owner_scope'} for item in events)


def test_runtime_module_has_no_filesystem_label_loader_or_native_import():
    tree = ast.parse(Path(forecast.__file__).read_text(encoding='utf8'))
    imports = [node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not any(any(banned in name for banned in ('pathlib', 'foundation_flight_data', 'training', 'native', 'controller')) for name in imports)
    assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'open' for node in ast.walk(tree))


def test_registered_plan_binds_budget_source_bytes_and_bootstrap_seed_meaning():
    plan = training.make_plan()
    training.check_plan(plan)
    assert plan['native_branches'] == 0
    assert plan['settings']['task_wall_seconds'] == 600.
    assert 'not_three_neural_fits' in plan['training_kind']
    changed = copy.deepcopy(plan)
    changed['settings']['bootstrap_seeds'] += [999]
    with pytest.raises(ValueError, match='frozen_B1_protocol'):
        training.check_plan(changed)


def test_small_evaluation_separates_public_predictions_and_private_targets(tmp_path):
    rows, context, split = inputs()
    checkpoint, _ = training.fit(rows, context, split)
    split['evaluation_windows'] = [{'split': 'development', 'forecast_origin': 48000., 'label_window_end': 49800.},
        {'split': 'test', 'forecast_origin': 58200., 'label_window_end': 60000.}]
    result = training.evaluate(rows, context, split, checkpoint, tmp_path, deadline=float('inf'))
    predictions = [json.loads(line) for line in (tmp_path / 'forecast_predictions.jsonl').read_text().splitlines()]
    assert len(predictions) == 6
    assert not any('actual' in prediction['forecast'] for prediction in predictions)
    assert (tmp_path / 'private/forecast_evaluation_labels.json').exists()
    assert result['main_result'] == 'flight_prior_only'
    assert result['main_forecast_uses_native_group_counts'] is False
    assert len(result['bootstrap']) == 3
    assert all(not report['independent_generalization_claim'] for report in result['bootstrap'])
