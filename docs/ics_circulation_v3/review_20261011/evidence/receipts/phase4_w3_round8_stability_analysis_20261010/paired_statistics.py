"""Descriptive paired-future statistics, not independent operating-day inference.

Input per state: two independent pseudorandom blocks x candidates x 32 futures.
Repeated identical tapes retain their original probability/occurrence weight.
Do not call on censored or missing complete-cycle outcomes.
"""
import math
import numpy as np

EPSILON = 1e-8
PREFIXES = (2, 8, 32)


def optimal(values):
    best = float(min(values))
    return [int(i) for i, value in enumerate(values) if abs(float(value) - best) <= EPSILON]


def choose(indices, actual):
    """Preserve the actual analytic decision when it is empirically tied best."""
    return actual if actual in indices else min(indices)


def paired_statistics(candidate, baseline):
    candidate, baseline = np.asarray(candidate, dtype=float), np.asarray(baseline, dtype=float)
    if candidate.ndim != 1 or candidate.shape != baseline.shape or len(candidate) < 2:
        raise ValueError('paired finite vectors with at least two draws required')
    if not np.isfinite(candidate).all() or not np.isfinite(baseline).all():
        raise ValueError('unknown or nonfinite outcome cannot be assigned a numerical label')
    delta = candidate - baseline
    variance = float(delta.var(ddof=1))
    covariance = float(np.cov(candidate, baseline, ddof=1)[0, 1])
    independent_variance_proxy = float(candidate.var(ddof=1) + baseline.var(ddof=1))
    if not math.isclose(variance, independent_variance_proxy - 2 * covariance, rel_tol=1e-8, abs_tol=1e-8):
        raise AssertionError('paired variance identity failed')
    return {
        'draws': len(candidate),
        'delta_mean_to_actual': float(delta.mean()),
        'paired_delta_variance': variance,
        'paired_standard_error': float(math.sqrt(max(0., variance) / len(candidate))),
        'candidate_baseline_sample_covariance': covariance,
        'independent_draw_variance_proxy': independent_variance_proxy,
        'paired_to_independent_variance_proxy_ratio': (
            variance / independent_variance_proxy if independent_variance_proxy > EPSILON else None),
        'negative_sample_covariance': covariance < -EPSILON,
        'lower_cost_draws': int(np.count_nonzero(delta < -EPSILON)),
        'tied_cost_draws': int(np.count_nonzero(np.abs(delta) <= EPSILON)),
        'higher_cost_draws': int(np.count_nonzero(delta > EPSILON)),
        'scope': 'Descriptive Monte Carlo pairing within the declared synthetic law. The independent variance is an estimated comparator, not an executed independent-CRN experiment or guarantee.'}


def analyse_state(costs, actual_index):
    values = np.asarray(costs, dtype=float)
    if (values.ndim != 3 or values.shape[0] != 2 or values.shape[2] != 32
            or values.shape[1] < 1 or type(actual_index) is not int
            or not 0 <= actual_index < values.shape[1] or not np.isfinite(values).all()):
        raise ValueError('complete finite 2 x K x 32 costs and an actual choice are required')
    all_means = values.mean(axis=(0, 2))
    pooled_optimal = optimal(all_means)
    prefix_rows = []
    for block in range(2):
        other = 1 - block
        block_means = values[block].mean(axis=1)
        heldout_means = values[other].mean(axis=1)
        full_block_optimal = optimal(block_means)
        for count in PREFIXES:
            means = values[block, :, :count].mean(axis=1)
            best = optimal(means)
            selected = choose(best, actual_index)
            heldout = paired_statistics(values[other, selected], values[other, actual_index])
            prefix_rows.append({
                'selection_block': block, 'selection_draws': count,
                'evaluation_block': other, 'evaluation_draws': 32,
                'selection_means': means.tolist(), 'selection_optimal_indices': best,
                'selected_index': selected, 'actual_index': actual_index,
                'selected_is_actual': selected == actual_index,
                'actual_within_prefix_regret': float(means[actual_index] - min(means)),
                'paired_candidates': [paired_statistics(values[block, i, :count], values[block, actual_index, :count])
                                      for i in range(values.shape[1])],
                'same_block_32_optimal_indices': full_block_optimal,
                'selected_in_same_block_32_optimal_set': selected in full_block_optimal,
                'heldout_cost_means': heldout_means.tolist(),
                'heldout_optimal_indices': optimal(heldout_means),
                'heldout_selected_minus_actual': heldout,
                'heldout_selected_minus_empirical_best': float(heldout_means[selected] - min(heldout_means)),
                'empirical_best_scope': 'The other block mean minimum is noisy and optimistically selected, not the true expected optimum.'})
    return {
        'candidate_count': values.shape[1], 'future_draw_count_per_candidate': 64,
        'actual_index': actual_index, 'pooled64_means': all_means.tolist(),
        'pooled64_optimal_indices': pooled_optimal,
        'actual_within_pooled64_regret': float(all_means[actual_index] - min(all_means)),
        'pooled64_value_range': float(max(all_means) - min(all_means)),
        'blocks32_optimal_sets': [optimal(values[b].mean(axis=1)) for b in range(2)],
        'prefixes': prefix_rows,
        'in_sample_scope': 'Pooled64 regret and best set describe these frozen draws; winner selection on these same draws does not establish true expected improvement.'}


def service_delta(candidate_ledger, actual_ledger):
    """Each future shares the same complete task IDs across all candidate arms."""
    by_candidate = {row['bag_id']: row for row in candidate_ledger}
    by_actual = {row['bag_id']: row for row in actual_ledger}
    if len(by_candidate) != len(candidate_ledger) or len(by_actual) != len(actual_ledger) or set(by_candidate) != set(by_actual):
        raise ValueError('paired branch task identities differ or repeat')
    changes = []
    for key, row in sorted(by_candidate.items()):
        other = by_actual[key]
        if row['completed_at'] is None or other['completed_at'] is None:
            raise ValueError('incomplete service is unknown, not zero delay')
        for field in ('arrival', 'deadline', 'origin', 'destination', 'protected'):
            if row[field] != other[field]:
                raise ValueError('same-future task definition changed across candidate arms')
        delta = row['completed_at'] - other['completed_at']
        if delta:
            changes.append({'bag_id': key, 'completion_delta': delta,
                            'protected': row['protected']})
    return {
        'task_count': len(by_actual), 'earlier': sum(row['completion_delta'] < 0 for row in changes),
        'later': sum(row['completion_delta'] > 0 for row in changes), 'changes': changes,
        'no_completion_later': not any(row['completion_delta'] > 0 for row in changes),
        'protected_late': sum(row['protected'] and row['completed_at'] > row['deadline'] for row in by_candidate.values())}
