"""Independent paired raw/timing/resource audit; no physical replay."""
from pathlib import Path
from copy import deepcopy
from collections import Counter
import gzip
import hashlib
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_terminal_screen_performance_20261010'
OUT = Path(__file__).resolve().parent
OLD = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_terminal_capacity_screen_20261010'
bound, failures, checks = {}, [], 0
QUERY = ('time', 'version', 'bag_id', 'tray_id', 'destination', 'requested_k', 'public_snapshot_sha256', 'options')
PHYSICAL = ('status', 'stopped_at', 'initial_state', 'initial_cursor', 'opportunities', 'actual_slow_trigger_times',
            'physical_tick_trace', 'event_trace_suffix', 'milestones', 'last_cycle_state', 'evaluation_ledger', 'selector_history_suffix')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    bound[str(path)] = sha(path)
    with (gzip.open if path.suffix == '.gz' else open)(path, 'rt', encoding='utf8') as stream:
        return json.load(stream)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def check(value, reason):
    global checks
    checks += 1
    if not value:
        failures.append(reason)


def equal(a, b, reason):
    check(digest(a) == digest(b), reason)


def without_ms(value):
    if isinstance(value, dict):
        return {k: without_ms(v) for k, v in value.items() if not k.endswith('_ms')}
    if isinstance(value, list):
        return [without_ms(v) for v in value]
    return value


def physical_hashes(outcome):
    result = {k: digest(without_ms(outcome[k])) for k in PHYSICAL}
    for key, value in [('result', outcome['result']), ('endpoint_result', outcome['original_endpoint']['result'])]:
        value = deepcopy(value)
        value['policy_stats'] = {k: v for k, v in value['policy_stats'].items() if not k.endswith('_ms')}
        result[key] = digest(value)
    result['slow_proposals'] = digest([{k: v for k, v in row.items() if k != 'diagnostics'} for row in outcome['slow_history_suffix']])
    return result


def main(stage):
    start, cpu = time.perf_counter(), time.process_time()
    protocol = read(BASE / 'protocol.json')
    for name, expected in read(BASE / 'preparation_manifest.json').items():
        # Performance manifests may be object-wrapped; original writer uses paths.
        check(sha(BASE / name) == expected, 'preparation:' + name)
        bound[str(BASE / name)] = expected
    for key, directory in [('source_sha256', ROOT / 'scripts/experiments/ics_circulation_v3'),
                           ('test_sha256', ROOT / 'tests'), ('input_sha256', None)]:
        for name, expected in protocol[key].items():
            path = Path(name) if directory is None else directory / name
            check(sha(path) == expected, 'binding:' + str(path))
            bound[str(path)] = expected
    for name, expected in read(BASE / (stage + '_manifest.json')).items():
        check(sha(BASE / name) == expected, 'stage:' + name)
        bound[str(BASE / name)] = expected
    summary = read(BASE / stage / 'summary.json')
    planned = protocol[stage + '_pairs']
    pairs = summary['pairs']
    check(len(pairs) == len(planned) == summary['planned_pairs'], 'full pair denominator')
    expected = {(p['block'], p['case']['case_id']): p for p in planned}
    check(set(expected) == {(p['block'], p['case_id']) for p in pairs}, 'all planned pair identities')
    requests = sorted([r for r in protocol['requests'] if stage == 'formal' or r['tape_id'] == 'nominal'], key=lambda r: r['case_id'])
    check(len(requests) * 4 == summary['planned_physical_calls'], 'two blocks both arms')
    check(summary['source_inputs_tests_unchanged'], 'recorded freeze stable')
    reference_cache = {}
    measures, totals = [], Counter()
    last_exit_by_block, first_entry_by_block = {}, {}
    for pair in pairs:
        ident = (pair['block'], pair['case_id'])
        spec = expected[ident]
        index = next(i for i, row in enumerate(requests) if row['case_id'] == pair['case_id'])
        order = ['off', 'on'] if (index + pair['block']) % 2 == 0 else ['on', 'off']
        equal(pair['arm_order'], order, 'fixed counterbalanced order:' + str(ident))
        check(set(pair['arms']) == {'off', 'on'}, 'both arms retained:' + str(ident))
        raw = {}
        if pair['case_id'] not in reference_cache:
            ref = protocol['screen_references'][pair['case_id']]
            check(sha(OLD / ref['file']) == ref['sha256'], 'old reference SHA:' + str(ident))
            old = read(OLD / ref['file'])
            reference_cache[pair['case_id']] = (physical_hashes(old['outcome']),
                [{k: row[k] for k in QUERY} for row in old['screen_accounting']['rows']])
        old_physical, old_queries = reference_cache[pair['case_id']]
        for arm in order:
            launch = pair['arms'][arm]
            receipt = launch['receipt']
            check(launch['exit_code'] == 0 and launch['launch_failure'] is None and receipt is not None, 'successful retained process:' + str(ident) + arm)
            check(launch['process_cpu_seconds'] is not None, 'whole-process CPU known:' + str(ident) + arm)
            totals['process_cpu_seconds'] += launch['process_cpu_seconds'] or 0
            check(sha(BASE / launch['receipt_file']) == launch['receipt_sha256'], 'receipt bytes:' + str(ident) + arm)
            equal(read(BASE / launch['receipt_file']), receipt, 'receipt exact:' + str(ident) + arm)
            check(receipt['physical_call_entered'] and receipt['raw_complete'] and receipt['status'] == 'controller_quiescent', 'complete physical call:' + str(ident) + arm)
            check(sha(BASE / receipt['file']) == receipt['sha256'], 'raw bytes:' + str(ident) + arm)
            value = read(BASE / receipt['file'])
            raw[arm] = value
            equal(value['case'], spec['case'], 'business input:' + str(ident) + arm)
            check(value['arm'] == arm and value['block'] == pair['block'], 'arm/block identity:' + str(ident) + arm)
            check(not value['cache_before']['fast_cache']['entries_lru_oldest_first'], 'actual initial cold cache:' + str(ident) + arm)
            outcome, query_rows = value['outcome'], value['measurement']['rows']
            equal(physical_hashes(outcome), old_physical, 'all old physical fields:' + str(ident) + arm)
            equal([{k: r[k] for k in QUERY} for r in query_rows], old_queries, 'all old exact Snapshot/K/pools:' + str(ident) + arm)
            check(len(query_rows) == receipt['search_calls'] == outcome['search_calls'], 'all query count:' + str(ident) + arm)
            check(sum(r['search_work'] for r in query_rows) == receipt['search_work'] == outcome['search_work'], 'logical search work:' + str(ident) + arm)
            check(sum(r['screen_work'] for r in query_rows) == receipt['screen_work'], 'screen work:' + str(ident) + arm)
            totals[arm + '_search_work'] += receipt['search_work']
            totals[arm + '_screen_work'] += receipt['screen_work']
            totals[arm + '_queries'] += len(query_rows)
            totals[arm + '_certified'] += sum(r['certified'] for r in query_rows)
            for query in query_rows:
                check(query['phase'] == 'returned' and query['error'] is None and query.get('observer_error') is None, 'no hidden failed query:' + str(ident) + arm)
                check(query['enabled'] == (arm == 'on'), 'probe arm flag:' + str(ident) + arm)
                for kind in ('cpu', 'wall'):
                    check(0 <= query['screen_' + kind + '_ns'] + query['search_' + kind + '_ns'] <= query['algorithm_' + kind + '_ns'], 'algorithm component interval:' + str(ident) + arm)
                    check(query['observer_' + kind + '_ns'] >= 0, 'observer interval:' + str(ident) + arm)
                if arm == 'off':
                    check(query['screen_work'] == query['screen_cpu_ns'] == query['screen_wall_ns'] == 0 and not query['certified'], 'off never screens:' + str(ident))
                if query['certified']:
                    check(not query['options'] and query['search_work'] == query['search_cpu_ns'] == query['search_wall_ns'] == 0, 'certificate skips actual search only:' + str(ident))
                for kind in ('algorithm', 'screen', 'search', 'observer'):
                    if query[kind + '_cpu_ns'] == 0:
                        totals[arm + '_' + kind + '_zero_cpu'] += 1
            for kind in ('algorithm', 'screen', 'search', 'observer'):
                for clock in ('cpu', 'wall'):
                    key = kind + '_' + clock + '_seconds'
                    check(abs(receipt['timings'][key] - sum(r[kind + '_' + clock + '_ns'] for r in query_rows) / 1e9) < 1e-8, 'timing sum:' + str(ident) + arm + key)
            check(receipt['timings']['algorithm_cpu_seconds'] + receipt['timings']['observer_cpu_seconds'] <= receipt['whole_simulation_cpu_seconds'] + 1e-7, 'nested CPU containment:' + str(ident) + arm)
            check(receipt['whole_simulation_cpu_seconds'] <= receipt['child_invocation_cpu_seconds'] + 1e-7, 'simulation inside invocation:' + str(ident) + arm)
            check(receipt['child_cumulative_cpu_at_receipt_seconds'] <= launch['process_cpu_seconds'] + 1e-7, 'receipt inside complete OS lifetime:' + str(ident) + arm)
            entry = receipt['module_entry_monotonic_ns'] / 1e9
            launch_at = entry - launch['launch_to_module_entry_wall_seconds']
            exit_at = launch_at + launch['launch_to_exit_wall_seconds']
            first_entry_by_block[pair['block']] = min(first_entry_by_block.get(pair['block'], entry), launch_at)
            last_exit_by_block[pair['block']] = max(last_exit_by_block.get(pair['block'], exit_at), exit_at)
            measures.append({'case_id': pair['case_id'], 'block': pair['block'], 'arm': arm,
                'algorithm_cpu_seconds': receipt['timings']['algorithm_cpu_seconds'], 'whole_process_cpu_seconds': launch['process_cpu_seconds'],
                'algorithm_wall_seconds': receipt['timings']['algorithm_wall_seconds'],
                'launch_wall_seconds': launch['launch_to_exit_wall_seconds'], 'query_count': len(query_rows),
                'launch_at': launch_at, 'exit_at': exit_at})
        equal(physical_hashes(raw['on']['outcome']), physical_hashes(raw['off']['outcome']), 'paired physical:' + str(ident))
        equal(raw['on']['cache_before'], raw['off']['cache_before'], 'paired initial cache configuration/state:' + str(ident))
        equal(raw['on']['instant_physical_ticks'], raw['off']['instant_physical_ticks'], 'all paired detached ticks:' + str(ident))
        equal([{k: r[k] for k in QUERY} for r in raw['on']['measurement']['rows']],
              [{k: r[k] for k in QUERY} for r in raw['off']['measurement']['rows']], 'all paired observed requests:' + str(ident))
        off = raw['off']['outcome']
        ledger = {r['bag_id']: r for r in off['evaluation_ledger']}
        for tick in raw['off']['instant_physical_ticks']:
            now = tick['time']
            check(tick['completed'] == {b: r['completed_at'] for b, r in ledger.items() if r['completed_at'] is not None and r['completed_at'] <= now}, 'detached completion time:' + str(ident))
            check(tick['load_times'] == {b: r['load_time'] for b, r in ledger.items() if r['load_time'] is not None and r['load_time'] < now}, 'detached loading time:' + str(ident))
        first, second = measures[-2:]
        check(first['exit_at'] <= second['launch_at'] + 1e-6, 'sequential pair fresh processes:' + str(ident))
    check(last_exit_by_block[0] <= first_entry_by_block[1] + 1e-6, 'block barrier')
    check(abs(totals['process_cpu_seconds'] - summary['worker_final_process_cpu_seconds_sum']) < 1e-8, 'all OS CPU once')
    check(summary['unknown_final_process_cpu_arms'] == 0 and summary['physical_calls_recorded'] == len(measures), 'known complete process denominator')
    drift = [path for path, expected in bound.items() if sha(path) != expected]
    check(not drift, 'all read evidence unchanged')
    result = {'schema': 'ics_round8_symmetric_performance_independent_audit_v1', 'stage': stage,
        'checks': checks, 'failures': failures, 'pairs': len(pairs), 'physical_arms': len(measures),
        'totals': dict(totals), 'measures': measures, 'bound_files': len(bound), 'drift': drift,
        'cpu_seconds': time.process_time() - cpu, 'wall_seconds': time.perf_counter() - start,
        'scope': 'All saved arms and pair identities, old and paired physical results/events/actual actions, every query public Snapshot/K/ordered pool, instant maps, actual cache startup, timing interval containment and non-overlap OS accounting. No simulation. Concurrent wall is not isolated latency; zero CPU intervals reflect clock quantization.',
        'files_sha256': bound}
    (OUT / ('performance_' + stage + '_artifact_audit.json')).write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('measures', 'files_sha256')}))


if __name__ == '__main__':
    main(sys.argv[1])
