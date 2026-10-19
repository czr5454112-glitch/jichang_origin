"""Runtime flight-conditioned new-arrival prediction, with no label/file access.

Gamma parameters use shape/rate. Regional priors already contain regional
shares. Observations are optional: unknown counts are never observed zeros.
Aggregate intervals moment-match the independent Gamma-Poisson mixture; they
are model-based uncertainty, not calibrated guarantees or execution authority.
"""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np
from scipy.stats import nbinom, poisson

from . import foundation_flight_context as contexts

MODEL_SCHEMA = 'g31.foundation.flight_forecaster.v1'
SCHEMA = 'g31.foundation.new_demand_forecast.v1'
COUNTS_SCHEMA = 'g31.foundation.flight_arrival_counts.v1'
EVENT_SCHEMA = 'g31.foundation.observed_flight_arrival.v1'
WINDOWS = (60, 300, 900, 1800)


def require(ok, reason):
    if not ok:
        raise ValueError('flight_forecaster:' + reason)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        allow_nan=False).encode()).hexdigest()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_checkpoint(checkpoint):
    require(type(checkpoint) is dict and checkpoint.get('schema') == MODEL_SCHEMA, 'model_schema')
    require(checkpoint.get('model_sha256') == digest({key: value for key, value in checkpoint.items()
        if key != 'model_sha256'}), 'model_content_binding')
    require(checkpoint['native_execution_authority'] is False, 'no_model_authority')
    require(finite(checkpoint['training_labels_closed_at']) and finite(checkpoint['frozen_at'])
        and 0 <= checkpoint['training_labels_closed_at'] <= checkpoint['frozen_at'], 'causal_model_freeze')
    require(checkpoint['regions'] and len(set(checkpoint['regions'])) == len(checkpoint['regions']), 'model_regions')
    require(set(checkpoint['parameters']) == set(checkpoint['regions']), 'parameter_regions')
    require(set(checkpoint['historical_arrival_rate_by_region']) == set(checkpoint['regions'])
        and all(finite(value) and value >= 0 for value in checkpoint['historical_arrival_rate_by_region'].values()),
        'historical_nonnegative_rate_regions')
    for region, params in checkpoint['parameters'].items():
        require(all(finite(params[key]) and params[key] > 0 for key in ('shape', 'rate')), 'positive_gamma_shape_rate')
        x, y = params['cdf_edges'], params['cdf_values']
        require(len(x) == len(y) and len(x) >= 2 and all(finite(v) for v in x + y)
            and all(a < b for a, b in zip(x, x[1:])) and x[-1] == 0.
            and y[0] == 0. and y[-1] == 1. and all(0 <= a <= b <= 1 for a, b in zip(y, y[1:])),
            'monotone_normalized_training_cdf:' + region)
    return checkpoint


def _interval(mean, latent_variance):
    mean, latent_variance = np.asarray(mean, float), np.asarray(latent_variance, float)
    lower, upper = np.zeros_like(mean), np.zeros_like(mean)
    positive = mean > 0
    mixed = positive & (latent_variance > 1e-12)
    if mixed.any():
        shape = mean[mixed] ** 2 / latent_variance[mixed]
        probability = shape / (shape + mean[mixed])
        lower[mixed] = nbinom.ppf(.05, shape, probability)
        upper[mixed] = nbinom.ppf(.95, shape, probability)
    regular = positive & ~mixed
    lower[regular] = poisson.ppf(.05, mean[regular])
    upper[regular] = poisson.ppf(.95, mean[regular])
    require(np.isfinite(lower).all() and np.isfinite(upper).all(), 'finite_predictive_interval')
    return {'level': .90, 'lower': lower.tolist(), 'upper': upper.tolist(),
        'variance': (mean + latent_variance).tolist(),
        'method': 'moment_matched_independent_gamma_poisson_aggregate'}


def _base(checkpoint, *, now, owner, regions, bin_seconds, horizon_seconds, context):
    validate_checkpoint(checkpoint)
    require(finite(now) and now >= checkpoint['frozen_at'], 'model_not_yet_frozen')
    require(type(owner) is str and owner, 'owner')
    regions = list(checkpoint['regions']) if regions is None else list(regions)
    require(regions and len(set(regions)) == len(regions) and set(regions) <= set(checkpoint['regions']), 'requested_regions')
    require(type(bin_seconds) is int and type(horizon_seconds) is int and bin_seconds > 0
        and horizon_seconds > 0 and horizon_seconds % bin_seconds == 0, 'forecast_grid')
    edges = np.arange(0, horizon_seconds + bin_seconds, bin_seconds, dtype=float)
    return regions, edges, {'schema': SCHEMA, 'forecast_origin': float(now), 'owner_scope': owner,
        'model_sha256': checkpoint['model_sha256'], 'context_sha256': None if context is None else digest(context.to_dict()),
        'context_version': None if context is None else context.version,
        'mapping_version': checkpoint['mapping_version'], 'time_basis': checkpoint['time_basis'],
        'information_cutoffs': {'training_labels_closed_at': checkpoint['training_labels_closed_at'],
            'model_frozen_at': checkpoint['frozen_at'], 'plan_received_at': None if context is None else context.received_at,
            'observed_arrivals_through': None},
        'bin_edges_seconds': edges.tolist(), 'absolute_bin_edges': (now + edges).tolist(),
        'remaining_support_until': now + horizon_seconds, 'new_demand_mean_by_region': {},
        'uncertainty_by_region': {}, 'window_summaries_by_region': {}, 'missing_mask_by_region': {},
        'calibration_status': checkpoint['calibration_status'], 'native_execution_authority': False,
        'predicted_inventory_is_actual': False, 'observed_count_update': False,
        'counts_missing_is_observed_zero': False, 'target': 'not_yet_arrived_new_demand_left_open_right_closed',
        'region_mapping_scope': 'legacy_source_injection_regions_not_airport_owner_assignment'}


def validate_counts(counts, *, context, checkpoint, now, owner, regions):
    if counts is None:
        return None
    require(type(counts) is dict and set(counts) == {'schema', 'owner_scope', 'observed_at',
        'complete_history_from', 'mapping_version', 'source_kind', 'counts_by_flight'}, 'counts_schema')
    require(counts['schema'] == COUNTS_SCHEMA and counts['owner_scope'] == owner
        and counts['mapping_version'] == checkpoint['mapping_version'], 'counts_owner_mapping')
    require(finite(counts['observed_at']) and 0 <= counts['observed_at'] <= now
        and counts['complete_history_from'] == 0., 'causal_complete_count_observation')
    require(counts['source_kind'] in ('actual_delivered_public_arrivals', 'explicit_synthetic_asof_arrival_feed'),
        'declared_count_source')
    known_refs = {entry.flight_ref for entry in context.entries}
    require(type(counts['counts_by_flight']) is dict and set(counts['counts_by_flight']) <= known_refs,
        'counts_known_plan_identity')
    for values in counts['counts_by_flight'].values():
        require(type(values) is dict and set(values) <= set(regions)
            and all(type(count) is int and count >= 0 for count in values.values()), 'counts_visible_region_values')
    return counts


def predict(context, checkpoint, *, now, owner, regions=None, observed_counts=None,
            bin_seconds=60, horizon_seconds=1800):
    """Consume only a legal plan and optional public count snapshot, never labels.

Calling this at a later now re-integrates the fixed CDF over absolute future
intervals. It does not relabel cached old bins or refresh source timestamps.
Missing per-flight/per-region counts keep the original prior, not n=0 updates.
    """
    payload = context.to_dict() if isinstance(context, contexts.FlightContext) else context
    context = contexts.adapt_context(payload, owner=owner, now=now, expected_time_basis=checkpoint['time_basis'])
    regions, edges, result = _base(checkpoint, now=now, owner=owner, regions=regions,
        bin_seconds=bin_seconds, horizon_seconds=horizon_seconds, context=context)
    if context is None:
        result.update(status='missing_flight_context', missing_reason='missing_expired_or_unavailable_plan')
        for region in regions:
            result['new_demand_mean_by_region'][region] = [None] * (len(edges) - 1)
            result['missing_mask_by_region'][region] = True
            result['uncertainty_by_region'][region] = None
            result['window_summaries_by_region'][region] = {str(w): None for w in WINDOWS}
        return result
    require(all(entry.scheduled_event_type == 'STD' for entry in context.entries), 'STD_model_only')
    counts = validate_counts(observed_counts, context=context, checkpoint=checkpoint,
        now=now, owner=owner, regions=regions)
    result.update(status='forecast', method='flight_gamma_poisson',
        context_availability_basis=context.availability_basis, plan_group_count=len(context.entries))
    if counts is not None:
        result['information_cutoffs']['observed_arrivals_through'] = counts['observed_at']
        result['count_source_kind'] = counts['source_kind']
    updated = 0
    for region in regions:
        params = checkpoint['parameters'][region]
        mean, variance = np.zeros(len(edges) - 1), np.zeros(len(edges) - 1)
        window_mean, window_variance = np.zeros(len(WINDOWS)), np.zeros(len(WINDOWS))
        for entry in context.entries:
            if entry.plan_status == 'cancelled':
                continue  # Only future belief changes; this module owns no arrived jobs.
            std = entry.scheduled_event_at
            shape, rate = params['shape'], params['rate']
            values = {} if counts is None else counts['counts_by_flight'].get(entry.flight_ref, {})
            if region in values:
                shape += values[region]
                rate += float(np.interp(counts['observed_at'] - std, params['cdf_edges'], params['cdf_values']))
                updated += 1
            cdf = np.interp(now + edges - std, params['cdf_edges'], params['cdf_values'])
            mass = np.diff(cdf)
            mean += shape / rate * mass
            variance += shape / rate ** 2 * mass ** 2
            start = float(np.interp(now - std, params['cdf_edges'], params['cdf_values']))
            mass_w = np.interp(now + np.asarray(WINDOWS) - std, params['cdf_edges'], params['cdf_values']) - start
            window_mean += shape / rate * mass_w
            window_variance += shape / rate ** 2 * mass_w ** 2
        intervals = _interval(window_mean, window_variance)
        result['new_demand_mean_by_region'][region] = mean.tolist()
        result['uncertainty_by_region'][region] = _interval(mean, variance)
        result['missing_mask_by_region'][region] = False
        result['window_summaries_by_region'][region] = {str(window):
            ({'mean': float(window_mean[i]), 'lower': intervals['lower'][i], 'upper': intervals['upper'][i],
              'variance': intervals['variance'][i], 'level': .90} if window <= horizon_seconds else None)
            for i, window in enumerate(WINDOWS)}
    result.update(observed_count_update=updated > 0, updated_flight_region_count=updated)
    return result


def recent_rate_forecast(checkpoint, *, now, owner, arrival_events, regions=None,
                         bin_seconds=60, horizon_seconds=1800, lookback_seconds=900):
    """No-plan comparator: delivered regional arrivals plus frozen historical rate.

The caller supplies only actual past events; STD/flight identity is not a model
feature. This pure runtime function never opens the evaluator's label index.
    """
    regions, edges, result = _base(checkpoint, now=now, owner=owner, regions=regions,
        bin_seconds=bin_seconds, horizon_seconds=horizon_seconds, context=None)
    require(type(arrival_events) is list and finite(lookback_seconds) and lookback_seconds > 0, 'past_event_list')
    seen, counts = set(), dict.fromkeys(regions, 0)
    for event in arrival_events:
        require(type(event) is dict and set(event) == {'schema', 'bag_id', 'region', 'arrived_at',
            'received_at', 'owner_scope'}, 'observed_event_schema')
        require(event['schema'] == EVENT_SCHEMA and event['owner_scope'] == owner and event['region'] in regions,
            'observed_event_owner_region')
        require(finite(event['arrived_at']) and finite(event['received_at'])
            and 0 <= event['arrived_at'] <= event['received_at'] <= now, 'event_not_received_or_future')
        require(event['bag_id'] not in seen, 'duplicate_bag_event')
        seen.add(event['bag_id'])
        if now - lookback_seconds < event['arrived_at'] <= now:
            counts[event['region']] += 1
    result.update(status='forecast', method='no_plan_recent_arrival_rate', count_source_kind='delivered_regional_arrivals')
    result['information_cutoffs']['observed_arrivals_through'] = now
    for region in regions:
        # One lookback of frozen-rate pseudo exposure; fixed before development.
        shape = counts[region] + checkpoint['historical_arrival_rate_by_region'][region] * lookback_seconds + 1e-6
        rate = 2. * lookback_seconds
        mass = np.diff(edges)
        means, variances = shape / rate * mass, shape / rate ** 2 * mass ** 2
        windows = np.asarray(WINDOWS, float)
        wm, wv = shape / rate * windows, shape / rate ** 2 * windows ** 2
        interval = _interval(wm, wv)
        result['new_demand_mean_by_region'][region] = means.tolist()
        result['uncertainty_by_region'][region] = _interval(means, variances)
        result['missing_mask_by_region'][region] = False
        result['window_summaries_by_region'][region] = {str(w):
            ({'mean': float(wm[i]), 'lower': interval['lower'][i], 'upper': interval['upper'][i],
              'variance': interval['variance'][i], 'level': .90} if w <= horizon_seconds else None)
            for i, w in enumerate(WINDOWS)}
    return result
