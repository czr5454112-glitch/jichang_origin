"""Saved-only equivalence audit with generated/authorized counts separated.

The original runner compared its raw generated candidate count with the cursor
hook's post-validation count in one auxiliary table. Keep that failed comparison
as evidence; reconstruct the common authorized denominator from both saved
actual selector histories. This audit does not run the physical simulation.
"""
from collections import Counter, defaultdict, deque
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def read(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def semantic(value):
    if isinstance(value, dict):
        return {k: semantic(v) for k, v in value.items() if not k.endswith('_ms')
                and k not in {'wall_seconds', 'cpu_seconds', 'process_cpu_seconds'}}
    if isinstance(value, list):
        return [semantic(v) for v in value]
    return value


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def normalized_attempts(case):
    calls = defaultdict(deque)
    for call in case['route_history']:
        calls[(call['time'], call['bag_id'], call['tray_id'])].append(call)
    rows, corrections = [], []
    loaded = [r for r in case['searches'] if r['bag_id'] is not None]
    assert len(loaded) == len(case['opportunities'])
    for search, opportunity in zip(loaded, case['opportunities']):
        key = search['time'], search['bag_id'], search['tray_id']
        assert key == (opportunity['time'], opportunity['bag_id'], opportunity['tray_id'])
        call = calls[key].popleft() if calls[key] else None
        authorized = 0 if call is None else call['candidate_count']
        assert 0 <= authorized <= search['candidate_count']
        if call is not None:
            assert call['node'] == opportunity['node'] == search['origin']
        if case['metrics']['engine'] == 'cursor':
            assert authorized == opportunity['candidate_count']
        row = {k: opportunity[k] for k in ('time', 'node', 'role', 'bag_id', 'tray_id', 'protected')}
        row.update(generated_candidate_count=search['candidate_count'], authorized_candidate_count=authorized)
        rows.append(row)
        if search['candidate_count'] != authorized:
            corrections.append(row)
    assert not any(calls.values()), 'selector calls missing from generation denominator'
    return rows, corrections


def main():
    checks, pairs = [], []
    def check(name, condition):
        checks.append({'check': name, 'passed': bool(condition)})
    summary, protocol, manifest = read('summary.json'), read('protocol.json'), read('manifest.json')
    check('all_manifest_hashes', all(sha256((HERE / p).read_bytes()).hexdigest() == h for p, h in manifest.items()))
    check('source_snapshot_hashes', all(sha256((HERE / 'source_snapshot' / p).read_bytes()).hexdigest() == h
                                       for p, h in summary['source_sha256'].items()))
    check('current_source_hashes', all(sha256((ROOT / 'scripts/experiments/ics_circulation_v3' / p).read_bytes()).hexdigest() == h
                                      for p, h in summary['source_sha256'].items()))
    check('complete_six_planned_runs', summary['planned_runs'] == summary['executed_runs'] == 6
          and summary['not_executed'] == [] and summary['unselected_planned_scenes'] == [])
    check('frozen_during_run', summary['source_changed_during_run'] is False)
    budget = protocol['budget']
    check('declared_work_budget', budget['max_search_calls'] == 300 and budget['max_search_work'] == 300000
          and budget['per_search_work'] == 3000 and budget['max_wall_seconds'] == 300.)
    node_counts, role_counts, valid_counts = Counter(), Counter(), Counter()
    total_bags = total_searches = total_work = total_attempts = total_selectors = total_slow = 0
    for name in ('cross_cycle', 'counterflow', 'near_full'):
        left, right = read(name + '_original.json'), read(name + '_cursor.json')
        input_data = read(name + '_input.json')
        declared = input_data.pop('input_sha256')
        check(name + ':identical_input_hash', digest(input_data) == declared == left['input_sha256'] == right['input_sha256'])
        for engine, case in (('original', left), ('cursor', right)):
            m = case['metrics']
            check(name + ':' + engine + ':reached_full_horizon', m['status'] == 'reached_horizon' and m['stopped_at'] == input_data['horizon'])
            check(name + ':' + engine + ':all_tasks_completed', m['completed_bags'] == m['observed_bags'] == m['scheduled_bags'])
            check(name + ':' + engine + ':no_fail_or_exhaust', case['failure'] is None and m['budget_stop'] is None)
            check(name + ':' + engine + ':budget_accounting', m['search_calls'] == len(case['searches']) <= 300
                  and m['search_work'] == sum(r['work'] for r in case['searches']) <= 300000
                  and all(r['work'] <= 3000 for r in case['searches']))
        comparisons = {}
        for key in ('result', 'route_history', 'slow_history', 'slow_trigger_times', 'slow_next_trigger_at', 'searches', 'observer_boundaries'):
            comparisons[key] = semantic(left[key]) == semantic(right[key])
            check(name + ':same_' + key, comparisons[key])
        left_rows, left_corrections = normalized_attempts(left)
        right_rows, right_corrections = normalized_attempts(right)
        check(name + ':authorized_opportunity_denominator', left_rows == right_rows)
        check(name + ':same_generated_to_authorized_reductions', left_corrections == right_corrections)
        original_pair = read(name + '_comparison.json')
        pairs.append({'scene': name, 'horizon': right['metrics']['horizon'], 'scheduled_each': right['metrics']['scheduled_bags'],
                      'complete_result_and_controls_equal': all(comparisons.values()),
                      'authorized_opportunities_equal': left_rows == right_rows,
                      'original_auxiliary_comparison': original_pair['comparisons']['attempt_role_node_denominator'],
                      'generated_to_authorized_reductions': right_corrections,
                      'authorized_candidate_count_histogram': dict(Counter(r['authorized_candidate_count'] for r in right_rows)),
                      'loaded_attempts_each': len(right_rows), 'actual_selector_calls_each': len(right['route_history']),
                      'zero_candidate_attempts_each': sum(r['authorized_candidate_count'] == 0 for r in right_rows),
                      'actual_nodes_each': dict(Counter(r['node'] for r in right_rows)),
                      'roles_each': dict(Counter(r['role'] for r in right_rows)),
                      'semantic_result_sha256': digest(semantic(right['result']))})
        node_counts.update(r['node'] for r in right_rows)
        role_counts.update(r['role'] for r in right_rows)
        valid_counts.update(r['authorized_candidate_count'] for r in right_rows)
        m = right['metrics']
        total_bags += m['scheduled_bags']
        total_searches += m['search_calls']
        total_work += m['search_work']
        total_attempts += len(right_rows)
        total_selectors += len(right['route_history'])
        total_slow += len(right['slow_trigger_times'])
    result = {'audit': 'Independent saved-artifact comparison; no simulation or runtime imports',
              'check_count': len(checks), 'all_passed': all(c['passed'] for c in checks), 'checks': checks,
              'pairs': pairs, 'per_engine_totals': {'bags_completed': total_bags, 'searches': total_searches,
                  'search_work': total_work, 'loaded_attempts': total_attempts, 'actual_selector_calls': total_selectors,
                  'slow_triggers': total_slow, 'node_counts': dict(node_counts), 'role_counts': dict(role_counts),
                  'authorized_candidate_histogram': dict(valid_counts)},
              'interpretation': 'Original and cursor physical/control semantics agree on all three full original-topology workloads. The original runner auxiliary false flags compared different generated/authorized stages, not divergent executions.',
              'preservation': 'Original summary, raw files, sources and failed auxiliary flags are unchanged; this additional audit separates those stages explicitly.',
              'limits': ['Three reused synthetic workload proxies on the original topology; no independent field traffic or controller quality claim.',
                         'Zero candidates remain in the denominator; bounded search exhaustion is never proof of physical infeasibility.',
                         'Wall/CPU timing fields excluded from equality, not physical ticks, plans, costs, decision counts or search work.',
                         'No new labels were generated.']}
    (HERE / 'audit_saved.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in {'checks', 'pairs'}}, indent=2))
    if not result['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
