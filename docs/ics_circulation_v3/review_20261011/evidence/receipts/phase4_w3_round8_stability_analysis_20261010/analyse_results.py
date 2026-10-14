"""Read-only, manifest-bound Round8 analysis. Never executes physical branches.

Extraction can run incrementally; final analysis requires the sealed full stage.
Every logical draw retains its weight even when its physical file is memoized.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter, process_time

import numpy as np
from paired_statistics import EPSILON, PREFIXES, analyse_state, choose, optimal, service_delta

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'phase4_w3_same_zone_stability_20261010'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    value = path.read_bytes()
    return json.loads(gzip.decompress(value) if path.suffix == '.gz' else value)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def extraction_bindings():
    result = {}
    for path in sorted(HERE.glob('extraction_*.json')):
        for name, expected in read(path).get('compact_files', {}).items():
            require(name not in result or result[name] == expected, 'conflicting extraction receipts')
            result[name] = expected
    return result


def immutable_inputs():
    """Close both saved preparation and live source/test identities."""
    paths = {SOURCE / name: expected for name, expected in read(SOURCE / 'preparation_manifest.json').items()}
    protocol = read(SOURCE / 'protocol.json')
    root = HERE.parents[3]
    for field, folder in (('source_sha256', root / 'scripts/experiments/ics_circulation_v3'), ('test_sha256', root / 'tests')):
        paths.update({folder / name: expected for name, expected in protocol[field].items()})
    paths.update({Path(name): expected for name, expected in protocol['input_sha256'].items()})
    for path, expected in paths.items():
        require(sha(path) == expected, 'frozen preparation/source/input changed: ' + str(path))
    return {str(path): expected for path, expected in paths.items()}


def project(raw, receipt, raw_path):
    """Keep enough original per-task evidence to recompute all paired service."""
    require(raw['request']['physical_key'] == receipt['physical_key'], 'physical key mismatch')
    require(raw['status'] == receipt['status'], 'outcome/receipt status mismatch')
    value = {'physical_key': receipt['physical_key'], 'request': raw['request'],
             'status': raw['status'], 'raw_file': str(raw_path.relative_to(SOURCE)),
             'raw_sha256': sha(raw_path), 'cost': None, 'components': None,
             'ledger': raw['evaluation_ledger'], 'stopped_at': raw['stopped_at']}
    if raw['status'] == 'controller_quiescent':
        require(raw['result'] is not None, 'quiescent without complete result')
        require(all(r['observed'] and r['completed_at'] is not None for r in value['ledger']), 'incomplete task ledger')
        require(set(raw['expected_task_ids']) == {r['bag_id'] for r in value['ledger']}, 'expected ledger mismatch')
        require(len(value['ledger']) == len({r['bag_id'] for r in value['ledger']}), 'duplicate task ledger')
        value.update(cost=raw['result']['total_cost'], components=raw['result']['cost_components'])
        require(np.isfinite(value['cost']), 'nonfinite complete cost')
        require(value['cost'] == receipt['total_cost'], 'receipt cost mismatch')
        require(raw['result']['completed'] == {r['bag_id']: r['completed_at'] for r in value['ledger']}, 'result ledger mismatch')
        require(all(raw['future_replacement_binding']['unchanged'].values()), 'changed causal continuation')
        require(all(raw['checkpoint_binding_checks'].values()), 'checkpoint mismatch')
        require('controller_quiescent' in raw['milestones'], 'no quiescence milestone')
    return value


def extract(output, receipt_name):
    cpu, wall = process_time(), perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    requested = {r['physical_key']: r for r in read(SOURCE / 'unique_rows.json')}
    claims = extraction_bindings()
    added, present, pending, unavailable, revalidated, compact_files = [], [], [], [], [], {}
    for key in requested:
        target = output / (key + '.json')
        receipt_path = SOURCE / 'full' / (key + '.json.receipt.json')
        if target.exists():
            if str(target) in claims:
                require(sha(target) == claims[str(target)], 'previously bound compact changed')
            else:
                # First extraction predates per-shard receipt binding: re-read
                # its original bytes, rather than retroactively trust a hash.
                receipt = read(receipt_path)
                raw_path = SOURCE / receipt['file']
                require(sha(raw_path) == receipt['sha256'], 'raw changed before revalidation')
                value = project(read(raw_path), receipt, raw_path)
                value.update(receipt_file=str(receipt_path.relative_to(SOURCE)), receipt_sha256=sha(receipt_path))
                require(value == read(target), 'unbound compact differs from original raw')
                compact_files[str(target)] = sha(target)
                revalidated.append(key)
            present.append(key)
            continue
        if not receipt_path.exists():
            pending.append(key)
            continue
        # Only a completed, parseable receipt authorizes reading a raw file.
        try:
            receipt = read(receipt_path)
        except json.JSONDecodeError:
            pending.append(key)
            continue
        if not receipt.get('file') or receipt['status'] != 'controller_quiescent':
            unavailable.append({'physical_key': key, 'status': receipt['status'],
                                'physical_result_status': receipt.get('physical_result_status')})
            continue
        path = SOURCE / receipt['file']
        require(sha(path) == receipt['sha256'], 'raw artifact changed')
        value = project(read(path), receipt, path)
        value.update(receipt_file=str(receipt_path.relative_to(SOURCE)), receipt_sha256=sha(receipt_path))
        write(target, value)
        compact_files[str(target)] = sha(target)
        added.append(key)
    result = {'source': str(SOURCE), 'added': len(added), 'previous': len(present), 'pending': len(pending),
              'unavailable': unavailable, 'planned_unique_physical': len(requested),
              'revalidated_unbound_existing': len(revalidated), 'compact_files': compact_files,
              'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
              'source_sha256': sha(Path(__file__)), 'physical_simulations': 0,
              'scope': 'Read-only incremental extraction; imports and final receipt write excluded. Pending files are not failed or zero-valued labels.'}
    write(receipt_name, result)
    print(json.dumps({k: v for k, v in result.items() if k != 'compact_files'}))


def service_summary(rows):
    deltas = [c['completion_delta'] for r in rows for c in r['changes']]
    return {'draws': len(rows), 'earlier_task_draws': sum(r['earlier'] for r in rows),
            'later_task_draws': sum(r['later'] for r in rows),
            'draws_with_any_later': sum(not r['no_completion_later'] for r in rows),
            'all_draws_no_completion_later': all(r['no_completion_later'] for r in rows),
            'protected_late_task_draws': sum(r['protected_late'] for r in rows),
            'max_completion_delay': max([0] + deltas), 'max_completion_gain': -min([0] + deltas)}


def state_analysis(detail, requests, compact):
    k, actual = detail['candidate_count'], detail['actual_chosen_index']
    result = {'state': detail, 'planned_logical': len(requests),
              'physical_status_counts_weighted_by_draw': dict(Counter(r['physical_status'] for r in requests))}
    if k == 0:
        return {**result, 'status': 'zero_candidate_pool_retained', 'statistics': None}
    require(len(requests) == 2 * k * 32, 'incomplete logical state grid')
    coordinates = {(r['block'], r['candidate'], r['future_index']) for r in requests}
    require(coordinates == {(b, c, f) for b in range(2) for c in range(k) for f in range(32)}, 'wrong logical coordinate grid')
    if any(r['physical_status'] != 'controller_quiescent' for r in requests):
        return {**result, 'status': 'unknown_state_ranking', 'statistics': None}
    grid = {(r['block'], r['candidate'], r['future_index']): compact[r['physical_key']] for r in requests}
    values = np.array([[[grid[b, c, f]['cost'] for f in range(32)] for c in range(k)] for b in range(2)])
    paired = {}
    draws = []
    for b in range(2):
        for f in range(32):
            base = grid[b, actual, f]
            for c in range(k):
                require(grid[b, c, f]['request']['sampled_future_sha256'] == base['request']['sampled_future_sha256'], 'different future paired')
                paired[b, c, f] = service_delta(grid[b, c, f]['ledger'], base['ledger'])
            best = optimal(values[b, :, f])
            draws.append({'block': b, 'future_index': f,
                'future_sha256': base['request']['sampled_future_sha256'],
                'costs': values[b, :, f].tolist(), 'optimal_indices': best,
                'actual_empirical_regret': float(values[b, actual, f] - min(values[b, :, f])),
                'service_to_actual': [paired[b, c, f] for c in range(k)]})
    stats = analyse_state(values, actual)
    for prefix in stats['prefixes']:
        other, chosen = prefix['evaluation_block'], prefix['selected_index']
        prefix['heldout_service_to_actual'] = service_summary([paired[other, chosen, f] for f in range(32)])
    candidates = []
    for c in range(k):
        service = service_summary([paired[b, c, f] for b in range(2) for f in range(32)])
        delta = values[:, c, :] - values[:, actual, :]
        candidates.append({'candidate': c, 'is_actual': c == actual, 'service_to_actual': service,
            'lower_cost_draws': int(np.count_nonzero(delta < -EPSILON)),
            'higher_cost_draws': int(np.count_nonzero(delta > EPSILON)),
            'all_draws_no_higher_cost': bool(np.all(delta <= EPSILON)),
            'samplewise_cost_and_completion_weak_dominance_with_service_gain': bool(np.all(delta <= EPSILON))
                and service['all_draws_no_completion_later'] and service['earlier_task_draws'] > 0})
    return {**result, 'status': 'complete', 'statistics': stats, 'candidate_service': candidates,
            'draws': draws, 'cost_matrix_block_candidate_draw': values.tolist()}


def analyse(compact_dir, output):
    cpu, wall = process_time(), perf_counter()
    require(not output.exists(), 'final analysis directory already exists')
    immutable = immutable_inputs()
    protocol, summary = read(SOURCE / 'protocol.json'), read(SOURCE / 'full/summary.json')
    require(summary['source_input_test_unchanged'], 'source changed during physical evaluation')
    manifest = read(SOURCE / 'full/manifest.json')
    paths = ('full/summary.json', 'full/resolved_requests.json', 'full/requested_rows.json', 'full/unique_rows.json')
    for name in paths:
        require(sha(SOURCE / name) == manifest[str(Path(name))], 'sealed stage metadata changed')
    resolved, planned = read(SOURCE / 'full/resolved_requests.json'), read(SOURCE / 'requested_rows.json')
    require([{k: r[k] for k in p} for r, p in zip(resolved, planned)] == planned and len(resolved) == len(planned), 'resolved denominator changed')
    unique = {r['physical_key']: r for r in summary['rows']}
    require(len(unique) == summary['planned_unique_physical'] == protocol['planned_unique_physical'], 'physical denominator mismatch')
    compact, hashes, claims = {}, {}, extraction_bindings()
    for key, row in unique.items():
        if row['status'] != 'controller_quiescent':
            continue
        path = compact_dir / (key + '.json')
        require(str(path) in claims and sha(path) == claims[str(path)], 'compact lacks unchanged extraction receipt')
        value = read(path)
        require(value['raw_sha256'] == row['sha256'] == manifest[row['file']], 'compact raw binding mismatch')
        require(value['physical_key'] == key and value['status'] == row['status'], 'compact identity/status mismatch')
        receipt_path = SOURCE / value['receipt_file']
        require(value['receipt_sha256'] == manifest[value['receipt_file']] == sha(receipt_path), 'receipt changed')
        compact[key], hashes[str(path)] = value, sha(path)
    for row in resolved:
        physical = unique[row['physical_key']]
        require(row['physical_status'] == physical['status'], 'alias status mismatch')
        for field in ('state_key', 'checkpoint_sha256', 'candidate', 'candidate_key', 'sampled_future_sha256', 'continuation_sha256', 'memo_key', 'minimum_observation_at'):
            require(row[field] == physical[field], 'memo alias changed ' + field)
        if physical['status'] == 'controller_quiescent':
            require(row['physical_sha256'] == compact[row['physical_key']]['raw_sha256'], 'alias raw changed')
    details = read(SOURCE / 'selected_details.json')
    support = read(HERE / 'future_support.json')
    for name, expected in support['input_binding'].items():
        require(sha(Path(name)) == expected, 'finite support input changed')
    support_rows = {r['state_key']: r for r in support['states']}
    states = [state_analysis(d, [r for r in resolved if r['state_key'] == d['state_key']], compact) for d in details]
    for state in states:
        detail = state['state']
        mass = support_rows[detail['state_key']]
        state['finite_support'] = {k: v for k, v in mass.items() if k != 'tape_probabilities'}
        state['exhaustive_law_cost'] = None
        if state['status'] != 'complete' or not mass['exhaustive_support']:
            continue
        by_tape = {r['future_sha256']: r['costs'] for r in state['draws']}
        require(set(by_tape) == set(mass['tape_probabilities']), 'exhaustive tape mismatch')
        means = [math.fsum(by_tape[tape][c] * p['numerator'] / p['denominator']
                         for tape, p in mass['tape_probabilities'].items()) for c in range(detail['candidate_count'])]
        state['exhaustive_law_cost'] = {'means': means, 'optimal_indices': optimal(means),
            'actual_regret': means[detail['actual_chosen_index']] - min(means),
            'scope': 'Finite-law expectation from every legal synthetic future, using recorded floating-point simulation costs. Auxiliary only; no real-world distribution claim and no substitution for primary nested draw-weighted estimates.'}
    complete = [r for r in states if r['status'] == 'complete']
    prefixes = [{**p, 'state_key': r['state']['state_key']} for r in complete for p in r['statistics']['prefixes']]
    aggregates = []
    for n in PREFIXES:
        rows = [p for p in prefixes if p['selection_draws'] == n]
        delta = [p['heldout_selected_minus_actual']['delta_mean_to_actual'] for p in rows]
        aggregates.append({'selection_draws': n, 'planned_state_block_selections': 34, 'complete_selections': len(rows),
            'selected_actual': sum(p['selected_is_actual'] for p in rows),
            'heldout_mean_better': sum(v < -EPSILON for v in delta), 'heldout_mean_tied': sum(abs(v) <= EPSILON for v in delta),
            'heldout_mean_worse': sum(v > EPSILON for v in delta),
            'max_heldout_mean_harm': max([0.] + delta), 'max_heldout_mean_benefit': -min([0.] + delta),
            'heldout_any_completion_later': sum(not p['heldout_service_to_actual']['all_draws_no_completion_later'] for p in rows),
            'selected_outside_same_block32_best_set': sum(not p['selected_in_same_block_32_optimal_set'] for p in rows)})
    overview = {'planned_logical': len(planned), 'planned_unique_physical': len(unique),
        'memo_aliases': len(planned) - len(unique), 'logical_status_counts': dict(Counter(r['physical_status'] for r in resolved)),
        'selected_records': len(states), 'complete_states': len(complete),
        'zero_states': sum(r['status'] == 'zero_candidate_pool_retained' for r in states),
        'unknown_states': sum(r['status'] == 'unknown_state_ranking' for r in states),
        'nonflat_pooled64_states': sum(r['statistics']['pooled64_value_range'] > EPSILON for r in complete),
        'actual_not_pooled64_best_states': sum(r['statistics']['actual_within_pooled64_regret'] > EPSILON for r in complete),
        'max_actual_pooled64_regret': max([0.] + [r['statistics']['actual_within_pooled64_regret'] for r in complete]),
        'block32_best_sets_differ_states': sum(r['statistics']['blocks32_optimal_sets'][0] != r['statistics']['blocks32_optimal_sets'][1] for r in complete),
        'draws_actual_not_best': sum(d['actual_empirical_regret'] > EPSILON for r in complete for d in r['draws']),
        'cost_flat_draws_with_completion_difference': sum(max(d['costs']) - min(d['costs']) <= EPSILON
            and any(s['changes'] for s in d['service_to_actual']) for r in complete for d in r['draws']),
        'all_draws_with_completion_difference': sum(any(s['changes'] for s in d['service_to_actual']) for r in complete for d in r['draws']),
        'optimal_nonactual_candidate_draws_with_later_completion': sum(not d['service_to_actual'][c]['no_completion_later']
            for r in complete for d in r['draws'] for c in d['optimal_indices'] if c != r['state']['actual_chosen_index']),
        'state_draw_denominator': sum(len(r['draws']) for r in complete),
        'samplewise_cost_completion_dominant_nonactual_candidates': sum(c['samplewise_cost_and_completion_weak_dominance_with_service_gain'] for r in complete for c in r['candidate_service'] if not c['is_actual']),
        'prefixes': aggregates,
        'scope': 'Descriptive conditional simulation on reused states. State/block/draw counts are not independent operating days. No cost means for incomplete states; no additive deployment gain or real-world posterior claim.'}
    output.mkdir(parents=True)
    for r in states:
        write(output / 'states' / (r['state']['state_key'] + '.json'), r)
    write(output / 'summary.json', overview)
    write(output / 'prefix_rows.json', prefixes)
    require(immutable_inputs() == immutable, 'input closure changed during analysis')
    for name, expected in hashes.items():
        require(sha(Path(name)) == expected, 'compact changed during analysis')
    for name in paths:
        require(sha(SOURCE / name) == manifest[str(Path(name))], 'stage metadata changed during analysis')
    write(output / 'input_binding.json', {'protocol': sha(SOURCE / 'protocol.json'), 'manifest': sha(SOURCE / 'full/manifest.json'),
        'compact_files': hashes, 'analysis_source': sha(Path(__file__)), 'statistics_source': sha(HERE / 'paired_statistics.py'),
        'finite_support': sha(HERE / 'future_support.json'), 'frozen_inputs': immutable,
        'extraction_receipts': {str(p): sha(p) for p in HERE.glob('extraction_*.json')}})
    write(output / 'resource.json', {'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
        'physical_simulations': 0, 'scope': 'Final read-only analysis, imports and receipt/manifest write excluded; incremental extraction separately billed.'})
    write(output / 'manifest.json', {str(p.relative_to(output)): sha(p) for p in sorted(output.rglob('*')) if p.is_file()})
    print(json.dumps(overview))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('extract', 'analyse'))
    parser.add_argument('--compact', type=Path, default=HERE / 'compact')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'extract':
        extract(args.compact, args.output)
    else:
        analyse(args.compact, args.output)
