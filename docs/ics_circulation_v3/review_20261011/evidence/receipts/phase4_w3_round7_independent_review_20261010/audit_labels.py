"""Independent complete-cycle artifact checks, including all actual choices.

This audit performs no replay. A chosen branch is compared at its actual stop
with the common prefix of the already-recorded complete nominal collection.
"""
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
import pickle
import sys
from time import perf_counter, process_time

from audit_collection import ROOT, HERE, BASE, canon, digest, physical


def main(stage_name):
    cpu0, wall0 = process_time(), perf_counter()
    run = BASE / 'phase4_w3_same_zone_labels_20261010'
    stage = run / stage_name
    bound, errors, checks = {}, [], 0

    def check(condition, label):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(label)

    def data(path, expected=None):
        path = path.resolve()
        value = path.read_bytes()
        actual = sha256(value).hexdigest()
        check(expected is None or expected == actual, 'SHA:' + str(path))
        if expected is not None and expected != actual:
            raise ValueError('Refusing mismatching bytes: ' + str(path))
        check(str(path) not in bound or bound[str(path)] == actual, 'stable repeated input:' + str(path))
        bound[str(path)] = actual
        return value

    def read(path, expected=None):
        value = data(path, expected)
        return json.loads(gzip.decompress(value) if path.name.endswith('.gz') else value)

    protocol = read(run / 'protocol.json')
    for name, expected in read(run / 'preparation_manifest.json').items():
        data(run / name, expected)
    for key, folder in [('source_sha256', ROOT / 'scripts/experiments/ics_circulation_v3'),
                        ('test_sha256', ROOT / 'tests')]:
        for name, expected in protocol[key].items():
            data(folder / name, expected)
    for path, expected in protocol['input_sha256'].items():
        data(Path(path), expected)
    for name, expected in read(stage / 'manifest.json').items():
        data(run / name, expected)
    summary, requested = read(stage / 'summary.json'), read(stage / 'requested_rows.json')
    keys = [r['request_key'] for r in requested]
    check(len(keys) == len(set(keys)) == summary['planned_requests'] == len(summary['rows']), 'complete unique request denominator')
    check(sorted(keys) == sorted(r['request_key'] for r in summary['rows']), 'all requested identities returned')
    definitions = {r['request_key']: r for r in requested}
    collection_audit = read(HERE / 'collection_artifact_audit.json')
    check(not collection_audit['errors'], 'complete actual checkpoint/query independent audit passed')
    collection_summary = read(run / 'collection_run/summary.json')
    collections, fast_cache_by_scene, original_by_scene = {}, {}, {}
    for row in collection_summary['rows']:
        scene = row['scene']
        collection = read(run / row['file'], row['sha256'])
        collections[scene] = collection
        caches = []
        for item in collection['query_index']:
            query = pickle.loads(data(run / item['file'], item['sha256']))
            if query['generator_role'] == 'fast_generator':
                caches.append({'time': query['time'], 'cache': canon(query['cache_after'])})
        fast_cache_by_scene[scene] = caches
        matches = [Path(p) for p in protocol['input_sha256'] if Path(p).name == scene + '_input.json']
        check(len(matches) == 1, scene + ':one original input')
        original_by_scene[scene] = read(matches[0], protocol['input_sha256'][str(matches[0])])
    inspected, chosen_count, normal_count, requested_status = [], 0, 0, Counter()
    metadata_cache = {}
    for row in summary['rows']:
        identity, scene = row['request_key'], row['scene']
        requested_status[row['status']] += 1
        check(all(row[k] == value for k, value in definitions[identity].items()), identity + ':entire request preserved')
        if not row.get('file'):
            inspected.append({'request_key': identity, 'status': row['status'], 'physical_raw_available': False})
            continue
        raw = read(run / row['file'], row['sha256'])
        check(raw['request'] == definitions[identity], identity + ':raw request binding')
        if row['metadata_file'] not in metadata_cache:
            metadata_cache[row['metadata_file']] = read(run / row['metadata_file'], row['metadata_sha256'])
        metadata = metadata_cache[row['metadata_file']]
        check(raw['checkpoint_metadata'] == metadata, identity + ':complete checkpoint metadata')
        data(run / row['checkpoint_file'], row['checkpoint_sha256'])
        active = dict(raw['active_continuation'])
        claimed = active.pop('sha256')
        check(digest(active) == claimed == row['continuation_sha256'] == metadata['active_continuation']['sha256'], identity + ':actual continuation digest')
        check(raw['cache_before'] == metadata['routing_cache'], identity + ':exact initial private cache')
        check(digest(raw['initial_state']) == metadata['state_sha256'] and raw['initial_cursor'] == metadata['cursor'], identity + ':exact starting state and cursor')
        check(raw['search_calls'] == len(raw['searches']) and raw['search_work'] == sum(q['work'] for q in raw['searches']), identity + ':all search accounting')
        if row['candidate'] is None:
            check(raw['forced_intervention'] is None, identity + ':normal continuation had no forced action')
        else:
            check(raw['forced_intervention']['candidate_index'] == row['candidate'] and
                  raw['forced_intervention']['candidate'] == metadata['candidates'][row['candidate']] and
                  raw['forced_intervention']['actual_action_key'] == metadata['candidate_keys'][row['candidate']], identity + ':one exact pending intervention')
        original = original_by_scene[scene]
        expected = dict(original['initial']['bags'])
        expected.update({b['bag_id']: b for b in original['future_engine_only']})
        ledger = {r['bag_id']: r for r in raw['evaluation_ledger']}
        check(len(ledger) == len(raw['evaluation_ledger']) and set(ledger) == set(expected) == set(raw['expected_task_ids']), identity + ':full nominal task identity ledger')
        for bag_id, task in expected.items():
            check(all(ledger[bag_id][k] == value for k, value in task.items()), identity + ':unchanged actual task ' + bag_id)
        result = raw['result']
        if result is None:
            inspected.append({'request_key': identity, 'status': raw['status'], 'cost_auditable': False})
            continue
        state, stop = result['final_snapshot'], raw['stopped_at']
        # runtime._update_motion appends unload_complete without another
        # invariant call; every _check plus the terminal result check counts.
        trace_checks = sum(event['event'] != 'unload_complete' for event in result['trace'])
        check(result['invariant_checks'] == trace_checks, identity + ':invariant count including unchecked unload record distinction')
        for bag_id, record in ledger.items():
            check(record['observed'] == (bag_id in state['bags']) and record['load_time'] == state['load_times'].get(bag_id)
                  and record['completed_at'] == state['completed'].get(bag_id), identity + ':actual ledger ' + bag_id)
        if raw['status'] == 'controller_quiescent':
            check(set(expected) <= state['completed'].keys() and set(expected) <= state['bags'].keys(), identity + ':all tasks physically complete')
            check(not state['plans'] and not state['empty_targets'], identity + ':no pending transport promises')
            check(all(t['mode'] == 'empty' and t['bag_id'] is None and t['available_at'] <= stop for t in state['trays'].values()), identity + ':all physical trays released')
            check(set(state['trays']) == set(original['initial']['trays']), identity + ':finite tray conservation')
            check(not any(t['arrive'] > stop for t in state['old_in_transit']), identity + ':no active old transit')
            for reservation in state['reservations']:
                if reservation['end'] <= stop:
                    continue
                tray = state['trays'][reservation['tray_id']]
                check(reservation['resource'] == 'node:' + tray['node'] and reservation['start'] <= stop and
                      reservation['end'] == 10**12, identity + ':strict stationary INFINITY occupancy')
            milestone = raw['milestones']['controller_quiescent']
            check(stop >= raw['minimum_observation_at'] and stop >= raw['forecast_expired_at'] and
                  milestone['time'] - milestone['quiet_since'] >= active['slow_period'] and
                  milestone['actual_slow_triggers_since'] > 0, identity + ':complete observation and real slow quiet period')
            check(all(state['completed'][key] <= task['deadline'] for key, task in expected.items() if task['protected']), identity + ':protected physical service on time')
            wait = sum(state['load_times'][key] - task['arrival'] for key, task in expected.items() if key in state['load_times'])
            tardy = sum(max(0, state['completed'][key] - task['deadline']) for key, task in expected.items() if not task['protected'])
            cargo = {key: tray['bag_id'] for key, tray in original['initial']['trays'].items()}
            distance = 0
            for event in result['trace']:
                if event['event'] == 'load':
                    cargo[event['tray_id']] = event['bag_id']
                elif event['event'] == 'unload_complete':
                    cargo[event['tray_id']] = None
                elif event['event'] == 'depart' and cargo[event['tray_id']] is None:
                    distance += original['initial']['network']['edges'][event['edge_id']]['travel_time']
            components = result['cost_components']
            check(components['tray_wait'] == wait and components['empty_distance'] == distance and
                  components['nonprotected_tardiness'] == tardy and components['terminal_backlog'] == 0 and
                  components['terminal_inflight'] == 0, identity + ':all independently recomputed physical cost components')
            check(abs(result['total_cost'] - wait - tardy - .1 * distance) < 1e-8 and
                  abs(row['total_cost'] - result['total_cost']) < 1e-8, identity + ':complete objective')
        onpolicy = row['cohort'] == 'new_policy_onpolicy'
        normal = row['candidate'] is None
        chosen = onpolicy and row['candidate'] is not None and row['candidate'] == row['actual_chosen_index']
        if normal or chosen:
            collection = collections[scene]
            reference_result = collection['result']
            check(stop <= collection['stopped_at'], identity + ':reference covers actual stop')
            executed = result['trace'][:-1]
            check(result['trace'][-1] == {'time': stop, 'event': 'tick'} and
                  executed == reference_result['trace'][:len(executed)], identity + ':all actual execution trace prefix')
            check(raw['event_trace_suffix'] == executed[metadata['trace_prefix_count']:], identity + ':complete event suffix')
            expected_searches = [q for q in collection['searches'][metadata['search_prefix_count']:] if q['time'] < stop]
            check(raw['searches'] == expected_searches, identity + ':exact original query/work/cache suffix')
            expected_ticks = [{'time': tick['time'], 'physical_sha256': digest(tick)} for tick in collection['physical_tick_trace']
                              if metadata['cursor'] is not None and raw['initial_state']['now'] < tick['time'] <= stop]
            check(raw['physical_tick_trace'] == expected_ticks, identity + ':compatible saved projection at matching absolute time')
            selected_prefix = metadata['selector_prefix_count'] + int(chosen)
            check(raw['selector_history_suffix'] == [s for s in collection['selector_history_suffix'][selected_prefix:] if s['time'] < stop], identity + ':selector suffix except exactly one forced call')
            check(raw['actual_slow_trigger_times'] == [t for t in collection['actual_slow_trigger_times'] if t < stop], identity + ':all actual slow trigger times')
            eligible_cache = [q for q in fast_cache_by_scene[scene] if q['time'] < stop]
            expected_cache = eligible_cache[-1]['cache'] if eligible_cache else collection['cache_before']['fast_cache']
            check(raw['cache_after']['fast_cache'] == expected_cache and
                  digest(expected_cache) == raw['cache_after']['fast_cache_sha256'], identity + ':actual private cache at branch stop')
            check(not any(q['time'] >= stop for q in collection['searches']), identity + ':remaining reference tail had no queries')
            # Both runs are quiet here; the reference tail contains empty ticks
            # and periodic no-action slow calls only, never new decisions.
            tail_ticks = collection['stopped_at'] - stop
            expected_result = physical(reference_result)
            expected_result['trace'] = reference_result['trace'][:len(executed)] + [{'time': stop, 'event': 'tick'}]
            expected_result['invariant_checks'] = sum(event['event'] != 'unload_complete' for event in expected_result['trace'])
            expected_result['final_snapshot']['now'] = stop
            expected_result['final_snapshot']['version'] -= tail_ticks
            expected_result['policy_stats']['slow_calls'] -= tail_ticks
            expected_result['policy_stats']['selection_calls'] -= int(chosen)
            check(physical(result) == expected_result, identity + ':all result fields with only explicit tick-tail and one-selector adjustment')
            chosen_count += int(chosen)
            normal_count += int(normal)
        if row['cohort'] == 'historical_old12' and row['decision_index'] == 40 and row['candidate'] in (0, 1):
            reference = Path(protocol['reference']) / 'mechanism' / f"counterflow_d0040_c{row['candidate']}__same_zone32plus32.json.gz"
            prior = read(reference, protocol['input_sha256'][str(reference)])
            check(physical(result) == physical(prior['result']), identity + ':exact round6 d40 physical result')
            for key in ('searches', 'cache_before', 'cache_after', 'stopped_at'):
                check(raw[key] == prior[key], identity + ':exact round6 d40 ' + key)
            check(physical(raw['original_endpoint']['result']) == physical(prior['original_endpoint']['result']), identity + ':exact round6 h80 result')
        inspected.append(dict(request_key=identity, status=raw['status'], independently_recomputed_cost=result['total_cost'],
            physical_task_count=len(expected), actual_chosen_checked=chosen, normal_resume_checked=normal))
    if stage_name == 'full':
        check(chosen_count == sum(r['candidate_count'] > 0 for c in collections.values() for r in c['attempts']), 'all actual chosen nonempty states audited')
    if stage_name == 'old12':
        check({r['decision_index'] for r in requested} == set(protocol['historical_selection']['decision_indices']) and
              len(requested) == 48, 'all predeclared historical states and 48 candidates')
    for path, expected in bound.items():
        check(sha256(Path(path).read_bytes()).hexdigest() == expected, 'unchanged final bytes:' + path)
    report = dict(schema='ics_v3_round7_independent_label_artifact_audit_v1', stage=stage_name,
        checks=checks, errors=errors, status_counts=dict(requested_status), rows=inspected,
        chosen_branch_prefix_checks=chosen_count, normal_resume_checks=normal_count,
        bound_files=bound, bound_file_count=len(bound), new_physical_simulations=0,
        projection_qualification='The frozen legacy physical_projection retains aliases for completed/load_times/empty_targets maps. Their tick digests prove compatible stored representation, not instantaneous ledger values. Actual service timing is checked from complete event prefixes, checkpoint and final physical ledger.',
        cpu_seconds=process_time() - cpu0, wall_seconds=perf_counter() - wall0,
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        resource_scope='Pure file audit through final rehash; final serialization/bootstrap excluded. No physical replay.')
    with (HERE / (stage_name + '_artifact_audit_v2.json')).open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'bound_files')}))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1]))
