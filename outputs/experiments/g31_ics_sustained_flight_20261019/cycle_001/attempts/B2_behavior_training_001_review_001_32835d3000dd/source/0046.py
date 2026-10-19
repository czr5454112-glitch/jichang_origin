"""Equivalent per-call CDF arrays; the frozen B1 implementation is untouched.

All original validation and sequential flight accumulation remain. Only each
validated region's CDF lists and the fixed window grid are converted once per
call. No checkpoint, context, counts, prediction or authority survives a call.
"""
from __future__ import annotations
from . import foundation_flight_forecaster as original

VERSION = 'g31.foundation.flight_forecaster_per_call_arrays.v1'
np, contexts = original.np, original.contexts
require, WINDOWS = original.require, original.WINDOWS


def predict(context, checkpoint, *, now, owner, regions=None, observed_counts=None,
            bin_seconds=60, horizon_seconds=1800):
    payload = context.to_dict() if isinstance(context, contexts.FlightContext) else context
    context = contexts.adapt_context(payload, owner=owner, now=now, expected_time_basis=checkpoint['time_basis'])
    regions, edges, result = original._base(checkpoint, now=now, owner=owner, regions=regions,
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
    counts = original.validate_counts(observed_counts, context=context, checkpoint=checkpoint,
        now=now, owner=owner, regions=regions)
    result.update(status='forecast', method='flight_gamma_poisson',
        context_availability_basis=context.availability_basis, plan_group_count=len(context.entries))
    if counts is not None:
        result['information_cutoffs']['observed_arrivals_through'] = counts['observed_at']
        result['count_source_kind'] = counts['source_kind']
    updated = 0
    windows = np.asarray(WINDOWS)
    for region in regions:
        params = checkpoint['parameters'][region]
        cdf_edges = np.asarray(params['cdf_edges'], dtype=float)
        cdf_values = np.asarray(params['cdf_values'], dtype=float)
        mean, variance = np.zeros(len(edges) - 1), np.zeros(len(edges) - 1)
        window_mean, window_variance = np.zeros(len(WINDOWS)), np.zeros(len(WINDOWS))
        for entry in context.entries:
            if entry.plan_status == 'cancelled':
                continue
            std = entry.scheduled_event_at
            shape, rate = params['shape'], params['rate']
            values = {} if counts is None else counts['counts_by_flight'].get(entry.flight_ref, {})
            if region in values:
                shape += values[region]
                rate += float(np.interp(counts['observed_at'] - std, cdf_edges, cdf_values))
                updated += 1
            cdf = np.interp(now + edges - std, cdf_edges, cdf_values)
            mass = np.diff(cdf)
            mean += shape / rate * mass
            variance += shape / rate ** 2 * mass ** 2
            start = float(np.interp(now - std, cdf_edges, cdf_values))
            mass_w = np.interp(now + windows - std, cdf_edges, cdf_values) - start
            window_mean += shape / rate * mass_w
            window_variance += shape / rate ** 2 * mass_w ** 2
        intervals = original._interval(window_mean, window_variance)
        result['new_demand_mean_by_region'][region] = mean.tolist()
        result['uncertainty_by_region'][region] = original._interval(mean, variance)
        result['missing_mask_by_region'][region] = False
        result['window_summaries_by_region'][region] = {str(window):
            ({'mean': float(window_mean[i]), 'lower': intervals['lower'][i], 'upper': intervals['upper'][i],
              'variance': intervals['variance'][i], 'level': .90} if window <= horizon_seconds else None)
            for i, window in enumerate(WINDOWS)}
    result.update(observed_count_update=updated > 0, updated_flight_region_count=updated)
    return result
