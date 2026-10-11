"""Read-only artifact analysis for frozen matched-continuation label batches.

No model fitting, candidate selection, simulator calls, or physical memoization.
Run only once all required stages have written their complete summaries.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
from time import perf_counter, process_time
import traceback

EPS = 1e-8


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def read(path):
    data = gzip.decompress(path.read_bytes()) if path.name.endswith('.gz') else path.read_bytes()
    return json.loads(data)


def write(path, data):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)


def ledger_vector(raw):
    return sorted((r['bag_id'], r['completed_at']) for r in raw['evaluation_ledger'])


def main(run, output, old):
    started, cpu = perf_counter(), process_time()
    output.mkdir(parents=True, exist_ok=False)
    inputs, checks, manifest_hashes = {}, 0, {}

    def load(path, expected=None):
        nonlocal checks
        path = path.resolve()
        value = sha(path)
        if str(path) in manifest_hashes:
            assert value == manifest_hashes[str(path)], (str(path), 'stage manifest mismatch')
            checks += 1
        if expected is not None:
            assert value == expected, (str(path), 'sha256 mismatch')
            checks += 1
        inputs[str(path)] = value
        return read(path)

    for base, name in ((run, 'preparation_manifest.json'), (run, 'collection_run/manifest.json'),
                       (run, 'full/manifest.json'), (run, 'old12/manifest.json'), (old / 'full', 'manifest.json')):
        manifest = load(base / name)
        manifest_hashes.update({str((base / path).resolve()): value for path, value in manifest.items()})
    old_reuse = load(old / 'collection_reuse_manifest.json')
    manifest_hashes.update({str((old / path).resolve()): value for path, value in old_reuse['files'].items()})
    protocol = load(run / 'protocol.json')
    collection_summary = load(run / 'collection_run/summary.json')
    full = load(run / 'full/summary.json')
    history = load(run / 'old12/summary.json')
    oldfull = load(old / 'full/summary.json')
    baseline = {(r['scene'], r['decision_index'], r['candidate']): r for r in oldfull['rows']}
    collections, attempts = {}, {}
    for row in collection_summary['rows']:
        raw = load(run / row['file'], row['sha256'])
        assert row['status'] == 'controller_quiescent'
        assert raw['replication']['result']['equal']
        assert all(v for k, v in raw['replication'].items() if k != 'result')
        checks += 3
        collections[row['scene']] = raw
        for attempt in raw['attempts']:
            key = attempt['scene'], attempt['decision_index']
            assert key not in attempts
            attempts[key] = attempt

    grouped = defaultdict(dict)
    for row in full['rows']:
        key = row['scene'], row['decision_index']
        assert key in attempts and row['candidate'] not in grouped[key]
        grouped[key][row['candidate']] = row
        checks += 1
    requested = load(run / 'full/requested_rows.json')
    assert len(requested) == full['planned_requests'] == sum(a['candidate_count'] for a in attempts.values())
    assert len(full['rows']) == len(requested)
    assert {r['request_key'] for r in full['rows']} == {r['request_key'] for r in requested}
    checks += 3

    pools, service_changes = [], []
    status_counts = Counter()
    for key, attempt in sorted(attempts.items()):
        rows = grouped[key]
        assert set(rows) == set(range(attempt['candidate_count'])), (key, 'candidate denominator')
        checks += 1
        pool = {k: attempt[k] for k in ('scene', 'decision_index', 'time', 'role', 'candidate_count', 'actual_chosen_index')}
        pool['candidate_statuses'] = {i: row['status'] for i, row in rows.items()}
        status_counts.update(pool['candidate_statuses'].values())
        pool['complete'] = bool(rows) and all(row['status'] == 'controller_quiescent' for row in rows.values())
        pool['values'] = {i: row.get('total_cost') for i, row in rows.items()}
        if not pool['complete']:
            pools.append(pool)
            continue
        costs = pool['values']
        best = min(costs.values())
        selected = attempt['actual_chosen_index']
        pool.update(best_cost=best, worst_cost=max(costs.values()),
                    optimal_indices=[i for i, cost in costs.items() if abs(cost - best) <= EPS],
                    actual_chosen_cost=costs[selected], actual_choice_regret=costs[selected] - best,
                    spread=max(costs.values()) - best)
        raw_by_candidate = {i: load(run / row['file'], row['sha256']) for i, row in rows.items()}
        chosen_raw = raw_by_candidate[selected]
        assert abs(costs[selected] - collections[key[0]]['result']['total_cost']) <= EPS, (key, 'chosen cost reproduction')
        assert ledger_vector(chosen_raw) == ledger_vector(collections[key[0]]), (key, 'chosen service reproduction')
        checks += 2
        ledgers = {}
        for i, raw in raw_by_candidate.items():
            assert raw['status'] == rows[i]['status']
            assert abs(raw['result']['total_cost'] - costs[i]) <= EPS
            assert raw['request']['checkpoint_sha256'] == attempt['checkpoint_sha256']
            assert raw['request']['future_sha256'] == attempt['future_sha256']
            assert raw['active_continuation']['sha256'] == attempt['continuation_sha256']
            continuation = dict(raw['active_continuation'])
            assert continuation.pop('sha256') == digest(continuation)
            assert raw['request']['candidate'] == i and raw['request']['request_key'] == rows[i]['request_key']
            assert raw['request']['metadata_sha256'] == attempt['metadata_sha256']
            metadata = load(run / attempt['metadata_file'], attempt['metadata_sha256'])
            assert raw['checkpoint_metadata'] == metadata
            assert metadata['candidate_keys'] == attempt['candidate_keys']
            assert len(metadata['candidates']) == attempt['candidate_count']
            ledger = {r['bag_id']: r for r in raw['evaluation_ledger']}
            assert set(ledger) == set(raw['expected_task_ids'])
            assert all(r['observed'] and r['completed_at'] is not None for r in ledger.values())
            assert all(r['completed_at'] <= r['deadline'] for r in ledger.values() if r['protected'])
            checks += 14
            ledgers[i] = ledger
        chosen_ledger = ledgers[selected]
        changed = {}
        for i, ledger in ledgers.items():
            assert set(ledger) == set(chosen_ledger)
            checks += 1
            deltas = [{ 'bag_id': bag, 'delta_completion': item['completed_at'] - chosen_ledger[bag]['completed_at'],
                        'protected': item['protected'], 'completion': item['completed_at'], 'deadline': item['deadline']}
                      for bag, item in ledger.items() if item['completed_at'] != chosen_ledger[bag]['completed_at']]
            changed[i] = {'earlier': sum(r['delta_completion'] < 0 for r in deltas),
                          'later': sum(r['delta_completion'] > 0 for r in deltas), 'details': deltas}
        pool['different_completion_vectors'] = len({tuple(ledger_vector(raw)) for raw in raw_by_candidate.values()})
        pool['same_cost_different_service'] = pool['spread'] <= EPS and pool['different_completion_vectors'] > 1
        pool['optimal_actions_with_later_tasks'] = [i for i in pool['optimal_indices'] if changed[i]['later']]
        pool['no_later_completion_indices'] = [i for i in costs if not changed[i]['later']]
        service_best = min(costs[i] for i in pool['no_later_completion_indices'])
        pool['no_later_completion_oracle_gap'] = costs[selected] - service_best
        pool['service_oracle_scope'] = 'offline same-tape comparison with actual chosen branch, within original pool; not an implementable online protection guarantee'
        pool['h80_values'] = {i: raw['original_endpoint']['result']['total_cost'] if raw.get('original_endpoint') else None
                             for i, raw in raw_by_candidate.items()}
        service_changes.append({'scene': key[0], 'decision_index': key[1], 'chosen': selected,
                                'optimal_indices': pool['optimal_indices'], 'candidate_service_changes': changed})
        pools.append(pool)

    groups = {}
    for scene in ('all', *sorted(collections)):
        for role in ('all', *sorted({a['role'] for a in attempts.values()})):
            group = [r for r in pools if (scene == 'all' or r['scene'] == scene) and (role == 'all' or r['role'] == role)]
            complete = [r for r in group if r['complete']]
            groups[f'{scene}:{role}'] = {'attempts': len(group), 'zero': sum(r['candidate_count'] == 0 for r in group),
                'nonempty': sum(r['candidate_count'] > 0 for r in group), 'complete_pools': len(complete),
                'unknown_nonempty_pools': sum(r['candidate_count'] > 0 and not r['complete'] for r in group),
                'candidate_count_distribution': dict(Counter(r['candidate_count'] for r in group)),
                'nonflat_pools': sum(r['spread'] > EPS for r in complete),
                'actual_choice_suboptimal': sum(r['actual_choice_regret'] > EPS for r in complete),
                'max_actual_choice_regret': max((r['actual_choice_regret'] for r in complete), default=None),
                'correlated_local_regret_sum_not_deployment_gain': sum(r['actual_choice_regret'] for r in complete),
                'different_completion_vector_pools': sum(r['different_completion_vectors'] > 1 for r in complete),
                'flat_cost_but_different_service_pools': sum(r['same_cost_different_service'] for r in complete),
                'pools_with_optimal_action_delaying_some_task': sum(bool(r['optimal_actions_with_later_tasks']) for r in complete)}
            groups[f'{scene}:{role}'].update({
                    'no_later_completion_oracle_improvement_pools': sum(r['no_later_completion_oracle_gap'] > EPS for r in complete),
                    'max_no_later_completion_oracle_gap': max((r['no_later_completion_oracle_gap'] for r in complete), default=None)})

    historical_groups = defaultdict(list)
    for row in history['rows']:
        historical_groups[row['decision_index']].append(row)
    historical = []
    for index, rows in sorted(historical_groups.items()):
        assert {r['candidate'] for r in rows} == {0, 1, 2, 3}
        oldmeta = load(old / f'collections/counterflow/d{index:04d}.json')
        oldchosen = oldmeta['actual_chosen_index']
        oldvalues = {i: baseline[('counterflow', index, i)]['total_cost'] for i in range(4)}
        newvalues = {r['candidate']: r.get('total_cost') for r in rows}
        item = {'decision_index': index, 'old_values': oldvalues, 'new_values': newvalues, 'old_actual_chosen_index': oldchosen,
                'statuses': {r['candidate']: r['status'] for r in rows},
                'complete': all(r['status'] == 'controller_quiescent' for r in rows)}
        historical_ledgers = {}
        for row in rows:
            if row['status'] != 'controller_quiescent':
                continue
            raw = load(run / row['file'], row['sha256'])
            meta = raw['checkpoint_metadata']
            oldrow = baseline[('counterflow', index, row['candidate'])]
            assert meta['historical_source_sha256'] == oldrow['checkpoint_sha256']
            assert row['future_sha256'] == oldrow['future_sha256']
            historical_ledgers[row['candidate']] = {r['bag_id']: r['completed_at'] for r in raw['evaluation_ledger']}
            checks += 2
        if item['complete']:
            service_reference = historical_ledgers[oldchosen]
            assert all(set(v) == set(service_reference) for v in historical_ledgers.values())
            nondegrading = [i for i, v in historical_ledgers.items()
                           if all(v[bag] <= at for bag, at in service_reference.items())]
            item.update(old_c0_regret=oldvalues[0] - min(oldvalues.values()),
                        new_c0_regret=newvalues[0] - min(newvalues.values()),
                        old_actual_choice_regret=oldvalues[oldchosen] - min(oldvalues.values()),
                        new_cost_of_old_actual_choice_regret=newvalues[oldchosen] - min(newvalues.values()),
                        new_no_later_completion_indices=nondegrading,
                        new_no_later_completion_oracle_gap=newvalues[oldchosen] - min(newvalues[i] for i in nondegrading),
                        old_optimal_indices=[i for i, v in oldvalues.items() if abs(v - min(oldvalues.values())) <= EPS],
                        new_optimal_indices=[i for i, v in newvalues.items() if abs(v - min(newvalues.values())) <= EPS])
        historical.append(item)
    assert len(historical) == 12 and len(history['rows']) == history['planned_requests'] == 48
    assert set(historical_groups) == set(protocol['historical_selection']['decision_indices'])
    checks += 2
    for path, expected in inputs.items():
        assert sha(Path(path)) == expected, (path, 'input changed during analysis')
        checks += 1

    result = {'schema': 'ics_v3_round7_matched_continuation_analysis_v1', 'run': str(run.resolve()),
        'analysis_source_sha256': sha(Path(__file__)),
        'scope': 'three reused synthetic development streams; state-local conditional values, not deployment improvement or independent confirmation',
        'checks': checks, 'groups': groups, 'status_counts': dict(status_counts), 'pools': pools,
        'historical_old12': historical, 'resources': {'analysis_cpu_seconds': process_time() - cpu,
        'analysis_wall_seconds': perf_counter() - started, 'scope': 'pure artifact analysis; no simulation'},
        'label_source_count': len(protocol['source_sha256'])}
    write(output / 'analysis.json', result)
    write(output / 'service_changes.json', service_changes)
    write(output / 'input_sha256.json', inputs)
    lines = ['# 第七轮同一继续控制价值分析', '',
             '来自三个反复使用的合成开发流；逐状态 regret 不可相加为部署增益。所有零池和未知结果保留在分母。', '',
             '|scene/role|尝试|零池|完整池|非平坦|实际选择非最优|最大 regret|成本相同但逐件服务不同|',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key, g in groups.items():
        lines.append(f"|{key}|{g['attempts']}|{g['zero']}|{g['complete_pools']}|{g['nonflat_pools']}|{g['actual_choice_suboptimal']}|{g['max_actual_choice_regret']}|{g['flat_cost_but_different_service_pools']}|")
    lines += ['', '## 历史旧12状态，只替换继续控制器', '', '|decision|旧 c0 regret|新 c0 regret|新各候选 J|', '|---|---:|---:|---|']
    for row in historical:
        lines.append(f"|d{row['decision_index']}|{row.get('old_c0_regret')}|{row.get('new_c0_regret')}|{row['new_values']}|")
    lines += ['', '## 实际选择仍非最优的全部新状态', '', '|scene|decision|time|role|chosen|optimal|regret|', '|---|---:|---:|---|---:|---|---:|']
    for row in pools:
        if row.get('actual_choice_regret', 0) > EPS:
            lines.append(f"|{row['scene']}|{row['decision_index']}|{row['time']}|{row['role']}|{row['actual_chosen_index']}|{row['optimal_indices']}|{row['actual_choice_regret']}|")
    (output / 'ANALYSIS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    write(output / 'manifest.json', {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()})
    print(json.dumps({'output': str(output), 'checks': checks, 'all': groups['all:all'], 'cpu': result['resources']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--old', type=Path, default=Path('outputs/experiments/ics_circulation_v3/phase4_w3_network_nominal_opportunities_repaired_20261010'))
    args = parser.parse_args()
    cpu, wall = process_time(), perf_counter()
    try:
        main(args.run, args.output, args.old)
    except Exception as error:
        if args.output.is_dir() and not (args.output / 'failure.json').exists():
            write(args.output / 'failure.json', {'type': type(error).__name__, 'message': str(error),
                'traceback': traceback.format_exc(), 'analysis_source_sha256': sha(Path(__file__)),
                'cpu_seconds': process_time() - cpu, 'wall_seconds': perf_counter() - wall,
                'scope': 'failed pure artifact analysis; zero physical simulation calls'})
        raise
