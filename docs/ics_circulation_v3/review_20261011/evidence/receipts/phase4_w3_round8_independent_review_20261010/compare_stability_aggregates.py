"""Independent stdlib aggregation from this review's fully audited raw extracts.

No simulation and no use of the author's statistics implementation.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import statistics as stat
import time

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
SOURCE = BASE / 'phase4_w3_same_zone_stability_20261010'
AUTHOR = BASE / 'phase4_w3_round8_stability_analysis_20261010'
EPS = 1e-8
bindings, failures = {}, []
checks = 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    bindings[str(path)] = sha(path)
    return json.loads(path.read_text(encoding='utf8'))


def check(okay, description):
    global checks
    checks += 1
    if not okay:
        failures.append(description)


def compare(expected, actual, label):
    if isinstance(expected, dict):
        for key, value in expected.items():
            check(key in actual, label + '.' + key + ' exists')
            if key in actual:
                compare(value, actual[key], label + '.' + key)
    elif isinstance(expected, list):
        check(isinstance(actual, list) and len(expected) == len(actual), label + ' length')
        if isinstance(actual, list):
            for i, (left, right) in enumerate(zip(expected, actual)):
                compare(left, right, label + ':' + str(i))
    elif isinstance(expected, float):
        check(isinstance(actual, (float, int)) and math.isfinite(actual)
              and math.isclose(expected, actual, rel_tol=1e-8, abs_tol=1e-8), label)
    else:
        check(expected == actual, label)


def best(values):
    value = min(values)
    return [i for i, v in enumerate(values) if abs(v - value) <= EPS]


def paired(values, baseline):
    deltas = [a - b for a, b in zip(values, baseline)]
    variance = stat.variance(deltas)
    covariance = stat.covariance(values, baseline)
    independent = stat.variance(values) + stat.variance(baseline)
    return {'draws': len(values), 'delta_mean_to_actual': stat.fmean(deltas),
            'paired_delta_variance': variance,
            'paired_standard_error': math.sqrt(variance / len(values)),
            'candidate_baseline_sample_covariance': covariance,
            'independent_draw_variance_proxy': independent,
            'paired_to_independent_variance_proxy_ratio': variance / independent if independent > EPS else None,
            'negative_sample_covariance': covariance < -EPS,
            'lower_cost_draws': sum(d < -EPS for d in deltas),
            'tied_cost_draws': sum(abs(d) <= EPS for d in deltas),
            'higher_cost_draws': sum(d > EPS for d in deltas)}


def service(candidate, baseline):
    check(set(candidate['completed_at']) == set(baseline['completed_at']), 'same-future task set')
    changes = [{'bag_id': key, 'completion_delta': candidate['completed_at'][key] - value,
                'protected': key in candidate['protected']}
               for key, value in sorted(baseline['completed_at'].items())
               if candidate['completed_at'][key] != value]
    return {'task_count': len(baseline['completed_at']),
            'earlier': sum(r['completion_delta'] < 0 for r in changes),
            'later': sum(r['completion_delta'] > 0 for r in changes), 'changes': changes,
            'no_completion_later': all(r['completion_delta'] < 0 for r in changes),
            'protected_late': 0}  # Every protected deadline already checked against raw.


def service_summary(rows):
    delta = [c['completion_delta'] for row in rows for c in row['changes']]
    return {'draws': len(rows), 'earlier_task_draws': sum(r['earlier'] for r in rows),
            'later_task_draws': sum(r['later'] for r in rows),
            'draws_with_any_later': sum(not r['no_completion_later'] for r in rows),
            'all_draws_no_completion_later': all(r['no_completion_later'] for r in rows),
            'protected_late_task_draws': 0, 'max_completion_delay': max([0] + delta),
            'max_completion_gain': -min([0] + delta)}


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    audit = read(HERE / 'stability_full_artifact_audit.json')
    check(not audit['failures'] and not audit['drift'], 'raw audit complete and stable')
    rows = {r['physical_key']: r for r in audit['rows']}
    resolved = read(SOURCE / 'full/resolved_requests.json')
    details = read(SOURCE / 'selected_details.json')
    summary = read(AUTHOR / 'results/summary.json')
    manifest = read(AUTHOR / 'results/manifest.json')
    for name, expected in manifest.items():
        check(sha(AUTHOR / 'results' / name) == expected, 'author result manifest:' + name)
    expected_states, prefixes, tie_service_rows = [], [], []
    for detail in details:
        key, k, actual = detail['state_key'], detail['candidate_count'], detail['actual_chosen_index']
        author = read(AUTHOR / 'results/states' / (key + '.json'))
        compare(detail, author['state'], key + ':state')
        requests = [r for r in resolved if r['state_key'] == key]
        if k == 0:
            check(not requests and author['status'] == 'zero_candidate_pool_retained'
                  and author['statistics'] is None, key + ':zero remains explicit')
            expected_states.append({'zero': True})
            continue
        if any(r['physical_status'] != 'controller_quiescent' for r in requests):
            check(author['status'] == 'unknown_state_ranking' and author['statistics'] is None,
                  key + ':incomplete unranked')
            expected_states.append({'unknown': True})
            continue
        grid = {(r['block'], r['candidate'], r['future_index']): rows[r['physical_key']] for r in requests}
        check(set(grid) == {(b, c, f) for b in range(2) for c in range(k) for f in range(32)}, key + ':grid')
        values = [[[grid[b, c, f]['cost'] for f in range(32)] for c in range(k)] for b in range(2)]
        means = [stat.fmean(values[0][c] + values[1][c]) for c in range(k)]
        block_means = [[stat.fmean(values[b][c]) for c in range(k)] for b in range(2)]
        services = {(b, c, f): service(grid[b, c, f], grid[b, actual, f])
                    for b in range(2) for c in range(k) for f in range(32)}
        local_prefixes = []
        for b in range(2):
            other = 1 - b
            for n in (2, 8, 32):
                estimate = [stat.fmean(values[b][c][:n]) for c in range(k)]
                opt = best(estimate)
                chosen = actual if actual in opt else min(opt)
                p = {'selection_block': b, 'selection_draws': n, 'evaluation_block': other,
                     'evaluation_draws': 32, 'selection_means': estimate,
                     'selection_optimal_indices': opt, 'selected_index': chosen,
                     'actual_index': actual, 'selected_is_actual': chosen == actual,
                     'actual_within_prefix_regret': estimate[actual] - min(estimate),
                     'paired_candidates': [paired(values[b][c][:n], values[b][actual][:n]) for c in range(k)],
                     'same_block_32_optimal_indices': best(block_means[b]),
                     'selected_in_same_block_32_optimal_set': chosen in best(block_means[b]),
                     'heldout_cost_means': block_means[other],
                     'heldout_optimal_indices': best(block_means[other]),
                     'heldout_selected_minus_actual': paired(values[other][chosen], values[other][actual]),
                     'heldout_selected_minus_empirical_best': block_means[other][chosen] - min(block_means[other]),
                     'heldout_service_to_actual': service_summary([services[other, chosen, f] for f in range(32)])}
                local_prefixes.append(p)
                prefixes.append({**p, 'state_key': key})
        stats = {'candidate_count': k, 'future_draw_count_per_candidate': 64, 'actual_index': actual,
                 'pooled64_means': means, 'pooled64_optimal_indices': best(means),
                 'actual_within_pooled64_regret': means[actual] - min(means),
                 'pooled64_value_range': max(means) - min(means),
                 'blocks32_optimal_sets': [best(m) for m in block_means], 'prefixes': local_prefixes}
        candidate_rows = []
        for c in range(k):
            srv = service_summary([services[b, c, f] for b in range(2) for f in range(32)])
            ds = [values[b][c][f] - values[b][actual][f] for b in range(2) for f in range(32)]
            candidate_rows.append({'candidate': c, 'is_actual': c == actual, 'service_to_actual': srv,
                'lower_cost_draws': sum(d < -EPS for d in ds), 'higher_cost_draws': sum(d > EPS for d in ds),
                'all_draws_no_higher_cost': all(d <= EPS for d in ds),
                'samplewise_cost_and_completion_weak_dominance_with_service_gain': all(d <= EPS for d in ds)
                    and srv['all_draws_no_completion_later'] and srv['earlier_task_draws'] > 0})
        draws = [{'block': b, 'future_index': f, 'costs': [values[b][c][f] for c in range(k)],
                  'optimal_indices': best([values[b][c][f] for c in range(k)]),
                  'actual_empirical_regret': values[b][actual][f] - min(values[b][c][f] for c in range(k)),
                  'service_to_actual': [services[b, c, f] for c in range(k)]}
                 for b in range(2) for f in range(32)]
        tie_counts = dict(same=0, earlier_only=0, later_only=0, mixed=0)
        tie_task_pairs = tie_earlier = tie_later = protected_later = 0
        largest_delay = largest_gain = 0
        tie_examples = []
        for draw in draws:
            for c in range(k):
                if c == actual or abs(draw['costs'][c] - draw['costs'][actual]) > EPS:
                    continue
                srv = draw['service_to_actual'][c]
                signs = {(-1 if r['completion_delta'] < 0 else 1) for r in srv['changes']}
                category = 'mixed' if len(signs) == 2 else 'earlier_only' if -1 in signs else 'later_only' if 1 in signs else 'same'
                tie_counts[category] += 1
                tie_task_pairs += srv['task_count']
                tie_earlier += srv['earlier']
                tie_later += srv['later']
                for change in srv['changes']:
                    delta = change['completion_delta']
                    largest_delay = max(largest_delay, delta)
                    largest_gain = max(largest_gain, -delta)
                    protected_later += int(change['protected'] and delta > 0)
                tie_examples.append({'block': draw['block'], 'future_index': draw['future_index'],
                    'candidate': c, 'actual': actual, 'category': category, 'cost': draw['costs'][c],
                    'baseline_cost': draw['costs'][actual], 'changes': srv['changes']})
        tie_service_rows.append({'state_key': key, 'tie_action_draw_count': sum(tie_counts.values()),
            'counts': tie_counts, 'max_completion_delay_ticks': largest_delay,
            'max_completion_gain_ticks': largest_gain, 'task_pair_denominator': tie_task_pairs,
            'earlier_task_pairs': tie_earlier, 'later_task_pairs': tie_later,
            'unchanged_task_pairs': tie_task_pairs-tie_earlier-tie_later,
            'protected_later_task_pairs': protected_later, 'examples': tie_examples})
        expected = {'status': 'complete', 'statistics': stats, 'candidate_service': candidate_rows,
                    'draws': draws, 'cost_matrix_block_candidate_draw': values}
        compare(expected, author, key)
        expected_states.append(expected)
    complete = [r for r in expected_states if r.get('status') == 'complete']
    aggregate = []
    for n in (2, 8, 32):
        ps = [r for r in prefixes if r['selection_draws'] == n]
        ds = [r['heldout_selected_minus_actual']['delta_mean_to_actual'] for r in ps]
        aggregate.append({'selection_draws': n, 'planned_state_block_selections': 34,
            'complete_selections': len(ps), 'selected_actual': sum(r['selected_is_actual'] for r in ps),
            'heldout_mean_better': sum(d < -EPS for d in ds), 'heldout_mean_tied': sum(abs(d) <= EPS for d in ds),
            'heldout_mean_worse': sum(d > EPS for d in ds), 'max_heldout_mean_harm': max([0.] + ds),
            'max_heldout_mean_benefit': -min([0.] + ds),
            'heldout_any_completion_later': sum(not r['heldout_service_to_actual']['all_draws_no_completion_later'] for r in ps),
            'selected_outside_same_block32_best_set': sum(not r['selected_in_same_block_32_optimal_set'] for r in ps)})
    expected_summary = {'planned_logical': len(resolved), 'planned_unique_physical': len(rows),
        'memo_aliases': len(resolved) - len(rows),
        'logical_status_counts': dict(Counter(r['physical_status'] for r in resolved)),
        'selected_records': len(details), 'complete_states': len(complete),
        'zero_states': sum(r.get('zero', False) for r in expected_states),
        'unknown_states': sum(r.get('unknown', False) for r in expected_states),
        'nonflat_pooled64_states': sum(r['statistics']['pooled64_value_range'] > EPS for r in complete),
        'actual_not_pooled64_best_states': sum(r['statistics']['actual_within_pooled64_regret'] > EPS for r in complete),
        'max_actual_pooled64_regret': max([0.] + [r['statistics']['actual_within_pooled64_regret'] for r in complete]),
        'block32_best_sets_differ_states': sum(r['statistics']['blocks32_optimal_sets'][0] != r['statistics']['blocks32_optimal_sets'][1] for r in complete),
        'draws_actual_not_best': sum(d['actual_empirical_regret'] > EPS for r in complete for d in r['draws']),
        'cost_flat_draws_with_completion_difference': sum(max(d['costs']) - min(d['costs']) <= EPS
            and any(s['changes'] for s in d['service_to_actual']) for r in complete for d in r['draws']),
        'all_draws_with_completion_difference': sum(any(s['changes'] for s in d['service_to_actual']) for r in complete for d in r['draws']),
        'optimal_nonactual_candidate_draws_with_later_completion': sum(not d['service_to_actual'][c]['no_completion_later']
            for r in complete for d in r['draws'] for c in d['optimal_indices'] if c != r['statistics']['actual_index']),
        'state_draw_denominator': sum(len(r['draws']) for r in complete),
        'samplewise_cost_completion_dominant_nonactual_candidates': sum(c['samplewise_cost_and_completion_weak_dominance_with_service_gain'] for r in complete for c in r['candidate_service'] if not c['is_actual']),
        'prefixes': aggregate}
    compare(expected_summary, summary, 'aggregate')
    compare(prefixes, read(AUTHOR / 'results/prefix_rows.json'), 'saved-prefix-rows')
    tradeoff = read(AUTHOR / 'service_tradeoffs/analysis.json')
    service_manifest = read(AUTHOR / 'service_tradeoffs/manifest.json')
    for name, expected in service_manifest.items():
        check(sha(AUTHOR / 'service_tradeoffs' / name) == expected, 'service manifest:' + name)
    author_service_rows = {r['state_key']: r for r in tradeoff['states']}
    check(set(author_service_rows) == {r['state_key'] for r in tie_service_rows}, 'all cost-tie service state identities')
    for row in tie_service_rows:
        compare(row, author_service_rows[row['state_key']], 'tie-service:' + row['state_key'])
    tie_totals = {field: sum(r[field] for r in tie_service_rows) for field in
        ('tie_action_draw_count', 'task_pair_denominator', 'earlier_task_pairs', 'later_task_pairs',
         'unchanged_task_pairs', 'protected_later_task_pairs')}
    tie_totals['counts'] = {field: sum(r['counts'][field] for r in tie_service_rows)
                           for field in ('same', 'earlier_only', 'later_only', 'mixed')}
    compare(tie_totals, tradeoff['totals'], 'tie-service-totals')
    drift = [name for name, expected in bindings.items() if sha(name) != expected]
    check(not drift, 'all read files stable')
    result = {'schema': 'round8_independent_stability_aggregate_comparison_v1', 'checks': checks,
              'failures': failures, 'drift': drift, 'independent_summary': expected_summary,
              'independent_cost_tie_service_totals': tie_totals,
              'cpu_seconds': time.process_time() - cpu, 'wall_seconds': time.perf_counter() - wall,
              'files_sha256': bindings, 'source_sha256': sha(__file__), 'physical_simulations': 0,
              'scope': 'Independent stdlib arithmetic from own audited physical raw extracts; logical aliases retain original draw weights. Per-draw cost/completion, all prefix choices and held-out pairing, sample covariance/SE, candidate service, cost-tie service categories/each example/protected completion changes and final aggregates recomputed. No reuse of author statistics code.'}
    target = HERE / 'stability_aggregate_comparison.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('files_sha256',)}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
