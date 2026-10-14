"""Raw-file audit of sampled complete-cycle branches; does not simulate."""
from pathlib import Path
from dataclasses import asdict
from collections import Counter
from copy import deepcopy
import gzip
import hashlib
import json
import pickle
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent
BASE = ROOT / 'outputs/experiments/ics_circulation_v3/phase4_w3_same_zone_stability_20261010'
INFINITY = 1000000000000
bound, failures = {}, []
checks = 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    bound[str(path)] = sha(path)
    with (gzip.open if path.suffix == '.gz' else open)(path, 'rt', encoding='utf8') as stream:
        return json.load(stream)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def check(value, message):
    global checks
    checks += 1
    if not value:
        failures.append(message)


def equal(a, b, message):
    check(canonical(a) == canonical(b), message)


def no_elapsed(value):
    if isinstance(value, dict):
        return {k: no_elapsed(v) for k, v in value.items() if k != 'elapsed_ms'}
    if isinstance(value, list):
        return [no_elapsed(v) for v in value]
    return value


def result_without_measurement(value):
    value = deepcopy(value)
    value['policy_stats'] = {k: v for k, v in value['policy_stats'].items() if not k.endswith('_ms')}
    return value


def main(stage):
    start, cpu = time.perf_counter(), time.process_time()
    protocol = read(BASE / 'protocol.json')
    prior = Path(protocol['source'])
    for name, expected in read(BASE / 'preparation_manifest.json').items():
        check(sha(BASE / name) == expected, 'preparation:' + name)
        bound[str(BASE / name)] = expected
    for key, directory in [('source_sha256', ROOT / 'scripts/experiments/ics_circulation_v3'),
                           ('test_sha256', ROOT / 'tests'), ('input_sha256', None)]:
        for name, expected in protocol[key].items():
            path = Path(name) if directory is None else directory / name
            check(sha(path) == expected, 'binding:' + str(path))
            bound[str(path)] = expected
    summary = read(BASE / stage / 'summary.json')
    for name, expected in read(BASE / stage / 'manifest.json').items():
        check(sha(BASE / name) == expected, 'stage manifest:' + name)
        bound[str(BASE / name)] = expected
    logical = read(BASE / stage / 'requested_rows.json')
    unique = read(BASE / stage / 'unique_rows.json')
    resolved = read(BASE / stage / 'resolved_requests.json')
    check(len(logical) == summary['planned_logical_requests'], 'logical count')
    check(len(unique) == len(summary['rows']) == summary['planned_unique_physical'], 'unique count')
    check(len(resolved) == len(logical), 'resolved denominator')
    expected_by_key = {r['physical_key']: r for r in unique}
    actual_by_key = {r['physical_key']: r for r in summary['rows']}
    check(len(expected_by_key) == len(unique) and set(actual_by_key) == set(expected_by_key), 'all physical identities')
    check(summary['source_input_test_unchanged'], 'recorded source stable')
    equal(dict(Counter(r['status'] for r in summary['rows'])), summary['status_counts'], 'physical status counts')
    equal(dict(Counter(r['physical_status'] for r in resolved)), summary['logical_status_counts'], 'logical status counts')
    for request, resolved_row in zip(logical, resolved):
        equal({k: resolved_row[k] for k in request}, request, 'logical resolution identity:' + request['request_key'])
        actual = actual_by_key[request['physical_key']]
        check(resolved_row['physical_status'] == actual['status'], 'alias propagates outcome:' + request['request_key'])
        check(resolved_row['memo_alias'] == (request['request_key'] != actual['request_key']), 'alias flag:' + request['request_key'])
        check(resolved_row['physical_file'] == actual.get('file') and resolved_row['physical_sha256'] == actual.get('sha256'), 'alias exact raw:' + request['request_key'])
    check(summary['memo_aliases'] == len(logical) - len(unique), 'memo resource count')
    check(abs(summary['case_invocation_cpu_seconds_recorded'] - sum(r['invocation_cpu_seconds'] or 0 for r in summary['rows'])) < 1e-9, 'unique CPU no aliases')
    cache = {}
    rows_out, tick_count, bag_count = [], 0, 0
    for ordinal, row in enumerate(summary['rows']):
        key = row['physical_key']
        if row['status'] != 'controller_quiescent':
            rows_out.append({'physical_key': key, 'status': row['status'], 'cost_known': False})
            continue
        raw_path = BASE / row['file']
        check(sha(raw_path) == row['sha256'], 'raw SHA:' + key)
        raw = read(raw_path)
        equal(raw['request'], expected_by_key[key], 'raw request:' + key)
        if row['state_key'] not in cache:
            metadata = read(prior / row['metadata_file'])
            checkpoint = prior / row['checkpoint_file']
            check(sha(checkpoint) == row['checkpoint_sha256'], 'checkpoint SHA:' + key)
            bound[str(checkpoint)] = row['checkpoint_sha256']
            with checkpoint.open('rb') as stream:
                payload = pickle.load(stream)
            future = read(BASE / row['future_file'])
            cache[row['state_key']] = (metadata, payload, future)
        metadata, payload, future = cache[row['state_key']]
        cp = payload['checkpoint']
        equal(raw['checkpoint_metadata'], metadata, 'full checkpoint metadata:' + key)
        equal(raw['initial_state'], asdict(cp.state), 'initial actual state:' + key)
        equal(raw['initial_cursor'], asdict(cp.cursor), 'initial private cursor:' + key)
        equal(raw['cache_before'], metadata['routing_cache'], 'initial private cache:' + key)
        equal(raw['active_continuation'], metadata['active_continuation'], 'actual continuation:' + key)
        check(all(raw['checkpoint_binding_checks'].values()) and all(raw['future_replacement_binding']['unchanged'].values()), 'runtime binding evidence:' + key)
        sampled = future['original_future'] if stage == 'bridge' else future['blocks'][row['block']]['tapes'][row['future_index']]['bags']
        equal(raw['sampled_future'], sampled, 'sampled tape:' + key)
        expected = {**raw['initial_state']['bags'], **{b['bag_id']: b for b in sampled}}
        check(set(raw['expected_task_ids']) == set(expected), 'full expected ledger:' + key)
        ledger = {b['bag_id']: b for b in raw['evaluation_ledger']}
        check(len(ledger) == len(raw['evaluation_ledger']) and set(ledger) == set(expected), 'unique complete ledger:' + key)
        final = raw['result']['final_snapshot']
        for task_id, definition in expected.items():
            item = ledger[task_id]
            equal({k: item[k] for k in definition}, definition, 'task definition:' + key + ':' + task_id)
            check(item['observed'] and item['completed_at'] is not None and item['load_time'] is not None, 'observed/load/complete:' + key + ':' + task_id)
            check(item['completed_at'] == final['completed'].get(task_id) and item['load_time'] == final['load_times'].get(task_id), 'final task timing:' + key + ':' + task_id)
            check(item['arrival'] <= item['load_time'] <= item['completed_at'] <= raw['stopped_at'], 'causal task timing:' + key + ':' + task_id)
            if item['protected']:
                check(item['completed_at'] <= item['deadline'], 'protected deadline:' + key + ':' + task_id)
        bag_count += len(ledger)
        check(not final['plans'] and not final['empty_targets'], 'no future plans/empty targets:' + key)
        check(all(t['mode'] == 'empty' and t['bag_id'] is None and t['available_at'] <= raw['stopped_at'] for t in final['trays'].values()), 'all trays physically empty/available:' + key)
        check(not any(f['arrive'] > raw['stopped_at'] for f in final['old_in_transit']), 'old transit drained:' + key)
        for slot in final['reservations']:
            if slot['end'] <= raw['stopped_at']:
                continue
            tray = final['trays'][slot['tray_id']]
            check(slot['resource'] == 'node:' + tray['node'] and slot['start'] <= raw['stopped_at'] and slot['end'] == INFINITY,
                  'only strict parked stock reservation remains:' + key)
        quiescent = raw['milestones']['controller_quiescent']
        check(raw['stopped_at'] >= raw['minimum_observation_at'] and raw['stopped_at'] >= raw['forecast_expired_at'], 'minimum and forecast TTL:' + key)
        check(quiescent['time'] - quiescent['quiet_since'] >= metadata['active_continuation']['periodic']['period'] if 'periodic' in metadata['active_continuation'] else quiescent['time'] > quiescent['quiet_since'], 'quiet duration:' + key)
        check(quiescent['actual_slow_triggers_since'] > 0 and any(quiescent['quiet_since'] <= t < quiescent['time'] for t in raw['actual_slow_trigger_times']), 'real slow trigger crossed:' + key)
        check(raw['forced_intervention']['candidate_index'] == row['candidate'], 'forced candidate index:' + key)
        equal(raw['forced_intervention']['candidate'], asdict(payload['pool'][row['candidate']]), 'forced physical candidate:' + key)
        check(raw['forced_intervention']['actual_action_key'] == metadata['candidate_keys'][row['candidate']], 'forced action key:' + key)
        check(raw['search_calls'] == len(raw['searches']) and raw['search_work'] == sum(r['work'] for r in raw['searches']), 'complete search work:' + key)
        check(abs(row['total_cost'] - raw['result']['total_cost']) < 1e-9, 'receipt cost:' + key)
        ticks = raw['instant_physical_tick_trace']
        check([t['time'] for t in ticks] == list(range(row['time'] + 1, raw['stopped_at'] + 1)), 'every detached tick:' + key)
        for tick in ticks:
            now = tick['time']
            check(tick['completed'] == {b: r['completed_at'] for b, r in ledger.items() if r['completed_at'] <= now}, 'instant completion map:' + key + ':' + str(now))
            check(tick['load_times'] == {b: r['load_time'] for b, r in ledger.items() if r['load_time'] < now}, 'instant load map:' + key + ':' + str(now))
            check(set(tick['visible_bags']) == {b for b, r in ledger.items() if r['arrival'] <= now}, 'instant visible IDs:' + key + ':' + str(now))
        tick_count += len(ticks)
        if stage == 'bridge':
            check(sha(row['reference_file']) == row['reference_sha256'], 'bridge old reference SHA:' + key)
            old = read(row['reference_file'])
            equal(result_without_measurement(raw['result']), result_without_measurement(old['result']), 'bridge complete result:' + key)
            for field in ('evaluation_ledger', 'cache_before', 'cache_after', 'searches', 'search_calls', 'search_work',
                          'stopped_at', 'event_trace_suffix', 'selector_history_suffix', 'actual_slow_trigger_times',
                          'physical_tick_trace', 'forced_intervention'):
                equal(raw[field], old[field], 'bridge ' + field + ':' + key)
            equal(no_elapsed(raw['slow_history_suffix']), no_elapsed(old['slow_history_suffix']), 'bridge slow history:' + key)
        rows_out.append({'physical_key': key, 'request_key': row['request_key'], 'state_key': row['state_key'],
            'status': raw['status'], 'cost_known': True, 'candidate': row['candidate'], 'cost': raw['result']['total_cost'],
            'cost_components': raw['result']['cost_components'], 'completed_at': {b: r['completed_at'] for b, r in ledger.items()},
            'protected': [b for b, r in ledger.items() if r['protected']]})
        if (ordinal + 1) % 100 == 0:
            print(json.dumps({'stage': stage, 'raw_audited': ordinal + 1, 'checks': checks, 'failures': len(failures)}), flush=True)
    drift = [name for name, expected in bound.items() if sha(name) != expected]
    check(not drift, 'all artifacts unchanged')
    result = {'schema': 'ics_round8_stability_raw_independent_audit_v1', 'stage': stage,
        'checks': checks, 'failures': failures, 'physical_rows': len(unique), 'logical_rows': len(logical),
        'status_counts': summary['status_counts'], 'instant_ticks_checked': tick_count, 'unique_physical_weighted_tasks': bag_count,
        'rows': rows_out, 'bound_files': len(bound), 'drift': drift,
        'cpu_seconds': time.process_time() - cpu, 'wall_seconds': time.perf_counter() - start,
        'scope': 'Every saved physical branch and resolved logical alias. File-only, no replay. Full expected task ledger, protected service, drain, detached timing maps, exact private checkpoint/action/tape binding. Bridge additionally compares all original result/search/cache/event fields with only declared measurements excluded.',
        'files_sha256': bound}
    (OUT / ('stability_' + stage + '_artifact_audit.json')).write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'files_sha256')}))


if __name__ == '__main__':
    main(sys.argv[1])
