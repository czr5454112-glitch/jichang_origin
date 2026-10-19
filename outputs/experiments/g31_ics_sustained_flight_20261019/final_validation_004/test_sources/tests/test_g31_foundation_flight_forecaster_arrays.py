"""Small synthetic equivalence and refusal checks; no fitting or native run."""
import copy
import json
import pytest
from scripts.experiments.g31_ics_circulation import foundation_flight_context as contexts
from scripts.experiments.g31_ics_circulation import foundation_flight_data as data
from scripts.experiments.g31_ics_circulation import foundation_flight_forecaster as old
from scripts.experiments.g31_ics_circulation import foundation_flight_forecaster_arrays as new


def inputs():
    rows = [{'bag_id': str(i), 'parent_flight_ref': str(i), 'flight_ref': str(i), 'copy_lineage': 'original_1x',
        'arrived_at': std-180., 'scheduled_std': std, 'region': 'legacy_start_0', 'loader': 'fixture', 'original_start': 0}
        for i, std in enumerate((36000., 43200., 50000., 60000.))]
    context, _ = data.build_artifacts(rows)
    context['owner_scope'] = 'A'
    for entry, at in zip(context['entries'], (520., 600., 600., 1397.125), strict=True):
        entry['scheduled_event_at'] = at
    regions = ['legacy_start_0', 'legacy_start_1']
    model = {'schema': old.MODEL_SCHEMA, 'regions': regions,
        'parameters': {r: {'shape': 2. + i/3., 'rate': 1. + i/7.,
            'cdf_edges': [-600., -233.125, -0.5, 0.], 'cdf_values': [0., .2375, .999, 1.]} for i, r in enumerate(regions)},
        'mapping_version': data.MAPPING_VERSION, 'time_basis': data.TIME_BASIS,
        'frozen_at': 0., 'training_labels_closed_at': 0., 'calibration_status': 'synthetic_uncalibrated',
        'native_execution_authority': False, 'historical_arrival_rate_by_region': dict.fromkeys(regions, 1/300.)}
    model['model_sha256'] = old.digest(model)
    return context, model


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


@pytest.mark.parametrize('variant', ['prior', 'none', 'empty_counts', 'zero', 'positive', 'cancelled', 'later', 'grid', 'typed_context'])
def test_complete_forecast_bytes_and_inputs_are_exact(variant):
    context, model = inputs(); kwargs = {'now': 300., 'owner': 'A'}
    if variant == 'none': context = None
    elif variant == 'cancelled': context['entries'][1]['plan_status'] = 'cancelled'
    elif variant == 'later': kwargs['now'] = 540.125
    elif variant == 'grid': kwargs.update(regions=['legacy_start_1'], bin_seconds=30, horizon_seconds=900)
    elif variant == 'typed_context':
        context = contexts.adapt_context(context, owner='A', now=300., expected_time_basis=model['time_basis'])
    elif variant in ('empty_counts', 'zero', 'positive'):
        kwargs['observed_counts'] = {'schema': old.COUNTS_SCHEMA, 'owner_scope': 'A', 'observed_at': 300.,
            'complete_history_from': 0., 'mapping_version': data.MAPPING_VERSION,
            'source_kind': 'explicit_synthetic_asof_arrival_feed', 'counts_by_flight': {} if variant == 'empty_counts' else
                {context['entries'][0]['flight_ref']: {'legacy_start_0': 0 if variant == 'zero' else 4}}}
    before = copy.deepcopy((context, model, kwargs))
    assert encode(new.predict(context, model, **kwargs)) == encode(old.predict(context, model, **kwargs))
    assert (context, model, kwargs) == before


@pytest.mark.parametrize('failure', ['model_digest', 'cdf_order', 'future_model', 'wrong_owner', 'future_plan',
    'future_counts', 'private_counts', 'unknown_flight', 'negative_counts'])
def test_all_original_invalid_inputs_still_refuse_with_same_reason(failure):
    context, model = inputs(); kwargs = {'now': 300., 'owner': 'A'}
    if failure == 'model_digest': model['parameters']['legacy_start_0']['shape'] += 1
    elif failure in ('cdf_order', 'future_model'):
        if failure == 'cdf_order': model['parameters']['legacy_start_0']['cdf_edges'][1] = 10.
        else: model['frozen_at'] = 301.
        model['model_sha256'] = old.digest({k: v for k, v in model.items() if k != 'model_sha256'})
    elif failure == 'wrong_owner': kwargs['owner'] = 'B'
    elif failure == 'future_plan': context['received_at'] = 301.
    else:
        counts = {'schema': old.COUNTS_SCHEMA, 'owner_scope': 'A', 'observed_at': 300., 'complete_history_from': 0.,
            'mapping_version': data.MAPPING_VERSION, 'source_kind': 'explicit_synthetic_asof_arrival_feed',
            'counts_by_flight': {context['entries'][0]['flight_ref']: {'legacy_start_0': 0}}}
        if failure == 'future_counts': counts['observed_at'] = 301.
        elif failure == 'private_counts': counts['source_kind'] = 'private_future_truth'
        elif failure == 'unknown_flight': counts['counts_by_flight'] = {'unknown': {'legacy_start_0': 0}}
        else: counts['counts_by_flight'][context['entries'][0]['flight_ref']]['legacy_start_0'] = -1
        kwargs['observed_counts'] = counts
    errors = []
    for function in (old.predict, new.predict):
        with pytest.raises(ValueError) as caught: function(context, model, **kwargs)
        errors.append(str(caught.value))
    assert errors[0] == errors[1]


def test_no_cross_call_reuse_after_valid_model_or_plan_changes():
    context, model = inputs(); first = new.predict(context, model, now=300., owner='A')
    model['parameters']['legacy_start_0']['shape'] += 1
    model['model_sha256'] = old.digest({k: v for k, v in model.items() if k != 'model_sha256'})
    changed = new.predict(context, model, now=300., owner='A')
    assert encode(changed) == encode(old.predict(context, model, now=300., owner='A')) != encode(first)
    context['entries'][0]['scheduled_event_at'] += 100.; context['version'] += 1
    again = new.predict(context, model, now=300., owner='A')
    assert encode(again) == encode(old.predict(context, model, now=300., owner='A')) != encode(changed)
