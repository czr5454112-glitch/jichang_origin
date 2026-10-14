"""Single read of all 2+24 boundary-supplement physical artifacts."""
from pathlib import Path
from dataclasses import asdict
from fractions import Fraction
from copy import deepcopy
import gzip
import hashlib
import json
import pickle
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
HERE = Path(__file__).parent
BASE = HERE.parent
EXPERIMENT = BASE / 'phase4_w3_round8_conditional_boundary_mechanism_20261010/experiment'
PRIOR = BASE / 'phase4_w3_same_zone_labels_20261010'
bindings, failures, checks = {}, [], 0


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(okay, label):
    global checks
    checks += 1
    if not okay:
        failures.append(label)


def read(path, expected=None):
    path = Path(path)
    actual = sha(path)
    if expected is not None:
        check(actual == expected, 'SHA:' + str(path))
    bindings[str(path)] = actual
    with (gzip.open if path.suffix == '.gz' else open)(path, 'rt', encoding='utf8') as stream:
        return json.load(stream)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def equal(a, b, label):
    check(canonical(a) == canonical(b), label)


def without_elapsed(value):
    if isinstance(value, dict):
        return {k: without_elapsed(v) for k, v in value.items() if k != 'elapsed_ms'}
    if isinstance(value, list):
        return [without_elapsed(v) for v in value]
    return value


def result_without_measurement(value):
    value = deepcopy(value)
    value['policy_stats'] = {k: v for k, v in value['policy_stats'].items() if not k.endswith('_ms')}
    return value


def main():
    cpu, wall = time.process_time(), time.perf_counter()
    protocol = read(EXPERIMENT / 'protocol.json')
    for name, expected in read(EXPERIMENT / 'preparation_manifest.json').items():
        path = EXPERIMENT / name
        check(sha(path) == expected, 'prepared artifact:' + name)
        bindings[str(path)] = expected
    for key, folder in [('source_sha256', ROOT / 'scripts/experiments/ics_circulation_v3'),
                        ('test_sha256', ROOT / 'tests'), ('input_sha256', None), ('auxiliary_sha256', None)]:
        for name, expected in protocol[key].items():
            path = Path(name) if folder is None else folder / name
            check(sha(path) == expected, 'immutable binding:' + str(path))
            bindings[str(path)] = expected
    check(len(protocol['missing_cells']) == 4 and protocol['memo_aliases'] == 0, 'gaps preserved, no memo')
    inventory = read(Path(protocol['selection_inventory']))
    equal([r['state_key'] for r in protocol['selected_details']], [r['state_key'] for r in inventory['selected']], 'fixed two-state selection')
    metadata_cache, rows_out, resource = {}, [], {}
    for stage, count in [('bridge', 2), ('full', 24)]:
        manifest = read(EXPERIMENT / stage / 'manifest.json')
        for name, expected in manifest.items():
            path = EXPERIMENT / name
            check(sha(path) == expected, 'sealed stage:' + name)
            bindings[str(path)] = expected
        summary = read(EXPERIMENT / stage / 'summary.json')
        requested = read(EXPERIMENT / (stage + '_rows.json'))
        equal(requested, read(EXPERIMENT / stage / 'requested_rows.json'), stage + ':requested unchanged')
        expected = {r['physical_key']: r for r in requested}
        check(len(expected) == len(requested) == len(summary['rows']) == count, stage + ':denominator')
        check({r['physical_key'] for r in summary['rows']} == set(expected), stage + ':exact complete identities')
        check(summary['source_input_test_unchanged'] and summary['complete_resource_accounting'], stage + ':recorded binding/resource complete')
        check(summary['actual_physical_calls_recorded'] == count and summary['unknown_physical_call_statuses'] == 0, stage + ':all calls known')
        check(summary['memo_aliases'] == 0, stage + ':independent physical calls')
        check(abs(summary['case_invocation_cpu_seconds_recorded'] - sum(r['invocation_cpu_seconds'] for r in summary['rows'])) < 1e-8, stage + ':paid CPU once')
        resource[stage] = {'worker_cpu_seconds': summary['case_invocation_cpu_seconds_recorded'],
                           'parent_cpu_seconds': summary['parent_cpu_seconds'], 'physical_calls': count}
        for receipt in summary['rows']:
            key = receipt['physical_key']
            check(receipt['status'] == 'controller_quiescent' and receipt['actual_physical_call'] is True, key + ':complete execution')
            if receipt['status'] != 'controller_quiescent':
                rows_out.append({'stage': stage, 'physical_key': key, 'state_key': receipt['state_key'],
                                 'status': receipt['status'], 'cost_known': False})
                continue
            raw = read(EXPERIMENT / receipt['file'], receipt['sha256'])
            equal(raw['request'], expected[key], key + ':raw identity')
            if receipt['state_key'] not in metadata_cache:
                metadata = read(PRIOR / receipt['metadata_file'], receipt['metadata_sha256'])
                path = PRIOR / receipt['checkpoint_file']
                check(sha(path) == receipt['checkpoint_sha256'], key + ':private checkpoint bytes')
                bindings[str(path)] = receipt['checkpoint_sha256']
                with path.open('rb') as stream:
                    payload = pickle.load(stream)
                future = read(EXPERIMENT / receipt['future_file'], receipt['future_file_sha256'])
                metadata_cache[receipt['state_key']] = (metadata, payload, future)
            metadata, payload, future = metadata_cache[receipt['state_key']]
            cp = payload['checkpoint']
            equal(raw['checkpoint_metadata'], metadata, key + ':full metadata')
            equal(raw['initial_state'], asdict(cp.state), key + ':actual original state')
            equal(raw['initial_cursor'], asdict(cp.cursor), key + ':actual private cursor')
            equal(raw['cache_before'], metadata['routing_cache'], key + ':private cache')
            equal(raw['active_continuation'], metadata['active_continuation'], key + ':same continuation')
            check(all(raw['checkpoint_binding_checks'].values()) and all(raw['future_replacement_binding']['unchanged'].values()), key + ':runtime replacement invariant')
            tape = future['original_future'] if stage == 'bridge' else future['blocks'][0]['tapes'][receipt['future_index']]['bags']
            equal(raw['sampled_future'], tape, key + ':exact finite tape')
            tasks = {**raw['initial_state']['bags'], **{b['bag_id']: b for b in tape}}
            ledger = {r['bag_id']: r for r in raw['evaluation_ledger']}
            check(set(tasks) == set(ledger) == set(raw['expected_task_ids']) and len(ledger) == len(raw['evaluation_ledger']), key + ':full unique expected task ledger')
            final = raw['result']['final_snapshot']
            for task_id, definition in tasks.items():
                task = ledger[task_id]
                equal({k: task[k] for k in definition}, definition, key + ':' + task_id + ':task unchanged')
                check(task['observed'] and task['load_time'] is not None and task['completed_at'] is not None, key + ':' + task_id + ':complete')
                check(task['arrival'] <= task['load_time'] <= task['completed_at'] <= raw['stopped_at'], key + ':' + task_id + ':causal service')
                check(task['load_time'] == final['load_times'][task_id] and task['completed_at'] == final['completed'][task_id], key + ':' + task_id + ':final times')
                if task['protected']:
                    check(task['completed_at'] <= task['deadline'], key + ':' + task_id + ':protected on time')
            check(not final['plans'] and not final['empty_targets'], key + ':plans and promises drained')
            check(all(t['mode'] == 'empty' and t['bag_id'] is None and t['available_at'] <= raw['stopped_at'] for t in final['trays'].values()), key + ':empty available stock')
            check(not any(r['arrive'] > raw['stopped_at'] for r in final['old_in_transit']), key + ':old transit drained')
            for slot in final['reservations']:
                if slot['end'] > raw['stopped_at']:
                    tray = final['trays'][slot['tray_id']]
                    check(slot['resource'] == 'node:' + tray['node'] and slot['start'] <= raw['stopped_at'] and slot['end'] == 10**12,
                          key + ':only exact parked-stock slot remains')
            quiet = raw['milestones']['controller_quiescent']
            check(quiet['time'] - quiet['quiet_since'] >= metadata['active_continuation']['slow_period'], key + ':true slow period quiet')
            check(raw['stopped_at'] >= max(raw['minimum_observation_at'], raw['forecast_expired_at']), key + ':minimum and forecast expiry')
            check(quiet['actual_slow_triggers_since'] > 0 and any(quiet['quiet_since'] <= t < quiet['time'] for t in raw['actual_slow_trigger_times']), key + ':real slow trigger')
            equal(raw['forced_intervention']['candidate'], asdict(payload['pool'][receipt['candidate']]), key + ':saved candidate action')
            check(raw['forced_intervention']['actual_action_key'] == metadata['candidate_keys'][receipt['candidate']], key + ':exact action identity')
            check(raw['search_calls'] == len(raw['searches']) and raw['search_work'] == sum(r['work'] for r in raw['searches']), key + ':search account')
            check(receipt['total_cost'] == raw['result']['total_cost'], key + ':receipt cost')
            ticks = raw['instant_physical_tick_trace']
            check([t['time'] for t in ticks] == list(range(receipt['time']+1, raw['stopped_at']+1)), key + ':every immediate tick')
            for tick in ticks:
                now = tick['time']
                equal(tick['completed'], {b: r['completed_at'] for b, r in ledger.items() if r['completed_at'] <= now}, key + ':instant completions:' + str(now))
                equal(tick['load_times'], {b: r['load_time'] for b, r in ledger.items() if r['load_time'] < now}, key + ':instant loads:' + str(now))
                check(set(tick['visible_bags']) == {b for b, r in ledger.items() if r['arrival'] <= now}, key + ':instant observed ids:' + str(now))
            if stage == 'bridge':
                old = read(receipt['reference_file'], receipt['reference_sha256'])
                equal(result_without_measurement(raw['result']), result_without_measurement(old['result']), key + ':bridge full result')
                for field in ('evaluation_ledger', 'cache_before', 'cache_after', 'searches', 'search_calls', 'search_work',
                              'stopped_at', 'event_trace_suffix', 'selector_history_suffix', 'actual_slow_trigger_times', 'physical_tick_trace', 'forced_intervention'):
                    equal(raw[field], old[field], key + ':bridge:' + field)
                equal(without_elapsed(raw['slow_history_suffix']), without_elapsed(old['slow_history_suffix']), key + ':bridge slow history')
            rows_out.append({'stage': stage, 'physical_key': key, 'state_key': receipt['state_key'],
                'candidate': receipt['candidate'], 'future_index': receipt.get('future_index'),
                'cost': raw['result']['total_cost'], 'components': raw['result']['cost_components'],
                'completed_at': {b: r['completed_at'] for b, r in ledger.items()},
                'probability_fraction': receipt.get('probability_fraction')})
    exact_means = []
    for detail in protocol['selected_details']:
        key, k, actual = detail['state_key'], detail['candidate_count'], detail['actual_chosen_index']
        grid = {(r['future_index'], r['candidate']): r for r in rows_out if r['stage'] == 'full' and r['state_key'] == key and 'cost' in r}
        check(set(grid) == {(f, c) for f in range(3) for c in range(k)}, key + ':finite full candidate grid')
        if len(grid) != 3*k:
            exact_means.append({'state_key': key, 'status': 'unknown_incomplete_grid'})
            continue
        weights = [Fraction(grid[f, 0]['probability_fraction']) for f in range(3)]
        check(weights == [Fraction(3, 17), Fraction(7, 17), Fraction(7, 17)] and sum(weights) == 1, key + ':exact slice weights')
        means = [sum(float(weights[f]) * grid[f, c]['cost'] for f in range(3)) for c in range(k)]
        service = []
        for c in range(k):
            changes = []
            for f in range(3):
                a, b = grid[f, c]['completed_at'], grid[f, actual]['completed_at']
                check(set(a) == set(b), key + ':same-future service identity')
                changes.append({bag: a[bag] - b[bag] for bag in a if a[bag] != b[bag]})
            service.append({'candidate': c, 'completion_changes_by_outcome': changes,
                            'no_task_later_all_three': all(d <= 0 for row in changes for d in row.values())})
        exact_means.append({'state_key': key, 'actual_index': actual,
            'costs_by_outcome': [[grid[f, c]['cost'] for c in range(k)] for f in range(3)],
            'exact_single_target_slice_means': means,
            'optimal_indices': [c for c, v in enumerate(means) if abs(v-min(means)) <= 1e-8],
            'actual_regret': means[actual] - min(means), 'service': service})
    drift = [p for p, expected in bindings.items() if sha(p) != expected]
    check(not drift, 'all audited artifacts unchanged')
    result = {'schema': 'round8_conditional_boundary_complete_artifact_audit_v1', 'checks': checks,
        'failures': failures, 'drift': drift, 'rows': rows_out, 'single_target_slice': exact_means,
        'source_experiment_resources_nested_not_added': resource, 'physical_simulations': 0,
        'cpu_seconds': time.process_time()-cpu, 'wall_seconds': time.perf_counter()-wall,
        'files_sha256': bindings, 'audit_source_sha256': sha(__file__),
        'scope': 'All two original-future exact bridges and all 24 separate finite-slice physical outcomes; no new routing or physics. Only the specified target varies, other pending tasks remain original. Exact 3/17,7/17,7/17 slice mean is not the main joint law or a deployed multi-action gain.'}
    target = HERE / 'boundary_mechanism_artifact_audit.json'
    if target.exists():
        raise FileExistsError(target)
    target.write_text(json.dumps(result, indent=2), encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows', 'files_sha256')}))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
