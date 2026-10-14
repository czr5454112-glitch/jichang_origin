"""Independent read-only comparison of three detached-tick supplements."""
from collections import Counter
from hashlib import sha256
import gzip
import json
from pathlib import Path
from time import process_time, perf_counter
from audit_collection import ROOT, HERE, BASE, physical


def main():
    cpu, wall = process_time(), perf_counter()
    bound, errors, checks = {}, [], 0
    run = BASE / 'phase4_w3_round7_physical_observation_20261010/supplement'

    def check(ok, label):
        nonlocal checks
        checks += 1
        if not ok: errors.append(label)

    def data(path, expected=None):
        path = Path(path).resolve()
        value = path.read_bytes()
        actual = sha256(value).hexdigest()
        check(expected is None or expected == actual, 'SHA:' + str(path))
        if expected is not None and expected != actual: raise ValueError('mismatching artifact')
        check(str(path) not in bound or bound[str(path)] == actual, 'repeated read:' + str(path))
        bound[str(path)] = actual
        return value

    def read(path, expected=None):
        value = data(path, expected)
        return json.loads(gzip.decompress(value) if Path(path).name.endswith('.gz') else value)

    for name, expected in read(run / 'manifest.json').items(): data(run / name, expected)
    protocol = read(run / 'protocol.json')
    for name, expected in protocol['source_sha256'].items(): data(ROOT / 'scripts/experiments/ics_circulation_v3' / name, expected)
    for name, expected in protocol['input_sha256'].items(): data(name, expected)
    summary = read(run / 'summary.json')
    reference = BASE / 'phase4_w3_same_zone_supply_repaired_20261010'
    old_manifest = read(reference / 'full/manifest.json')
    counts, total = Counter(), 0
    check(len(summary['rows']) == 3 and {r['scene'] for r in summary['rows']} == set(protocol['scenes']), 'exact3 supplemental deployments')
    rows = []
    for row in summary['rows']:
        scene = row['scene']
        raw = read(run / row['file'], row['sha256'])
        old_name = scene + '__nominal__same_zone32plus32.json.gz'
        old = read(reference / 'full' / old_name, old_manifest[old_name])
        current = raw['legacy_result']
        check(physical(current['result']) == physical(old['result']), scene + ':all physical result fields unchanged')
        for key in ('opportunities', 'searches', 'cache_before', 'cache_after', 'stopped_at', 'physical_tick_trace',
                    'event_trace_suffix', 'selector_history_suffix', 'actual_slow_trigger_times'):
            check(current[key] == old[key], scene + ':strict original ' + key)
        ticks = raw['instant_physical_ticks']
        check(len(ticks) == row['ticks'] == len(current['physical_tick_trace']), scene + ':all observed ticks')
        check([r['time'] for r in ticks] == list(range(current['initial_state']['now'] + 1, current['stopped_at'] + 1)), scene + ':every consecutive prepared tick')
        final = current['result']['final_snapshot']
        initial_loads = current['initial_state']['load_times']
        mismatch = Counter({key: 0 for key in ('completed', 'load_times', 'empty_targets')})
        for instant, legacy in zip(ticks, current['physical_tick_trace']):
            time = instant['time']
            for key in ('time', 'trays', 'visible_bags', 'reservations', 'plans', 'old_in_transit'):
                check(instant[key] == legacy[key], scene + ':' + str(time) + ':other physical field ' + key)
            check(instant['completed'] == {key: at for key, at in final['completed'].items() if at <= time}, scene + ':' + str(time) + ':completion at event preparation')
            check(instant['load_times'] == {key: at for key, at in final['load_times'].items() if at < time or key in initial_loads}, scene + ':' + str(time) + ':loading at prior control ticks')
            check(set(instant['visible_bags']) == {key for key, bag in final['bags'].items() if bag['arrival'] <= time}, scene + ':' + str(time) + ':only arrived tasks visible')
            for key in mismatch:
                mismatch[key] += instant[key] != legacy[key]
        check(dict(mismatch) == raw['legacy_alias_mismatch_ticks'] == row['legacy_alias_mismatch_ticks'], scene + ':independently recomputed alias discrepancy')
        check(row['physical_calls'] == 1 and row['status'] == 'passed', scene + ':separate physical invocation')
        counts.update(mismatch)
        total += len(ticks)
        rows.append({'scene': scene, 'ticks': len(ticks), 'alias_mismatch_ticks': dict(mismatch)})
    for path, expected in bound.items(): check(sha256(Path(path).read_bytes()).hexdigest() == expected, 'final unchanged:' + path)
    report = dict(schema='round7_independent_instant_observation_audit_v1', checks=checks, errors=errors,
        rows=rows, total_ticks=total, alias_mismatch_ticks=dict(counts), bound_files=bound,
        new_physical_simulations=0, cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        qualification='Pure file evidence checks actual prepared-tick ledgers, not only final-map compatibility; no old raw or labels rewritten.')
    with (HERE / 'instant_observation_artifact_audit.json').open('x', encoding='utf8') as stream: json.dump(report, stream, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k != 'bound_files'}))
    return bool(errors)


if __name__ == '__main__': raise SystemExit(main())
