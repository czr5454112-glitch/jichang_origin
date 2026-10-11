"""Read-only field audit of every actual collection/checkpoint/query artifact.

Trusted local pickle bytes are SHA checked before loading. No engine restore,
controller evaluation, query generation, or physical simulation is performed.
"""
from collections import Counter
from dataclasses import asdict, is_dataclass
from hashlib import sha256
import gzip
import json
from pathlib import Path
import pickle
import sys
from time import process_time, perf_counter

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BASE = HERE.parent
sys.path.insert(0, str(ROOT))


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def canon(value):
    return json.loads(json.dumps(value, allow_nan=False))


def semantic(value):
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): semantic(v) for k, v in value.items() if not str(k).endswith('_ms')}
    if isinstance(value, (list, tuple)):
        return [semantic(v) for v in value]
    if isinstance(value, set):
        return sorted((semantic(v) for v in value), key=lambda x: json.dumps(x, sort_keys=True))
    if hasattr(value, 'tolist'):
        return value.tolist()
    cls = type(value).__module__ + '.' + type(value).__qualname__
    if is_dataclass(value):
        return {'class': cls, 'fields': semantic({k: getattr(value, k) for k in value.__dataclass_fields__})}
    if hasattr(value, '__dict__'):
        return {'class': cls, 'fields': semantic(vars(value))}
    raise TypeError(type(value))


def physical(result):
    result = canon(result)
    result['policy_stats'] = {k: v for k, v in result['policy_stats'].items() if not k.endswith('_ms')}
    return result


def unwrapped(value, attribute):
    seen = set()
    while hasattr(value, attribute):
        if id(value) in seen:
            raise ValueError('wrapper cycle')
        seen.add(id(value))
        value = getattr(value, attribute)
    return value


def main(run):
    wall0, cpu0 = perf_counter(), process_time()
    bound, errors, checks = {}, [], 0

    def check(condition, description):
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(description)

    def content(path, expected=None):
        path = path.resolve()
        data = path.read_bytes()
        actual = sha256(data).hexdigest()
        check(expected is None or actual == expected, 'sha:' + str(path))
        if expected is not None and actual != expected:
            raise ValueError('Refusing to parse mismatching artifact: ' + str(path))
        check(str(path) not in bound or bound[str(path)] == actual, 'unchanged_repeated_read:' + str(path))
        bound[str(path)] = actual
        return data

    def read(path, expected=None):
        data = content(path, expected)
        return json.loads(gzip.decompress(data) if path.name.endswith('.gz') else data)

    def manifest(path, relative):
        values = read(path)
        for name, expected in values.items():
            content(relative / name, expected)
        return values

    manifest(run / 'preparation_manifest.json', run)
    protocol = read(run / 'protocol.json')
    for key, folder in [('source_sha256', ROOT / 'scripts/experiments/ics_circulation_v3'),
                        ('test_sha256', ROOT / 'tests')]:
        for name, expected in protocol[key].items():
            content(folder / name, expected)
    for name, expected in protocol['input_sha256'].items():
        content(Path(name), expected)
    content(ROOT / 'cpp/ics_core/runtime/bounded_local_pibt.hpp',
            'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951')
    manifest(run / 'collection_run/manifest.json', run)
    summary = read(run / 'collection_run/summary.json')
    check({r['scene'] for r in summary['rows']} == set(protocol['scene_names']), 'complete scene denominator')
    reference = Path(protocol['reference'])
    prior_manifest = read(reference / 'full/manifest.json')
    scene_rows = []
    for scene_summary in summary['rows']:
        scene = scene_summary['scene']
        raw = read(run / scene_summary['file'], scene_summary['sha256'])
        reference_name = scene + '__nominal__same_zone32plus32.json.gz'
        old = read(reference / 'full' / reference_name, prior_manifest[reference_name])
        check(raw['status'] == scene_summary['status'] == 'controller_quiescent', scene + ':complete collection')
        check(physical(raw['result']) == physical(old['result']), scene + ':all physical result fields')
        for key in ('opportunities', 'searches', 'cache_before', 'cache_after', 'stopped_at',
                    'physical_tick_trace', 'event_trace_suffix', 'selector_history_suffix', 'actual_slow_trigger_times'):
            check(raw[key] == old[key], scene + ':original ' + key)
        check(raw['search_calls'] == len(raw['searches']) == len(raw['query_index']), scene + ':all query denominator')
        check(raw['search_work'] == sum(q['work'] for q in raw['searches']), scene + ':all actual logical work')
        queries = []
        for number, row in enumerate(raw['query_index']):
            query = pickle.loads(content(run / row['file'], row['sha256']))
            check(row['ordinal'] == query['query_ordinal'] == number, scene + ':query ordinal')
            check(query['phase'] == 'returned', scene + ':query returned')
            snapshot = query['snapshot']
            check(set(vars(snapshot)) == set(snapshot.__dataclass_fields__), scene + ':public Snapshot fields only')
            check(query['public_snapshot_sha256'] == digest(asdict(snapshot)), scene + ':public query digest')
            check(all(b.arrival <= snapshot.now for b in snapshot.bags.values()), scene + ':no unobserved bags in query')
            check(query['raw_candidate_count'] == len(query['options']), scene + ':raw query pool count')
            original_query = raw['searches'][number]
            check(all(query[k] == original_query[k] for k in ('time', 'bag_id', 'tray_id')), scene + ':query identity')
            check(query['last_expansions'] == original_query['work'] and
                  query['last_search_status'] == original_query['status'], scene + ':query work/status')
            queries.append(query)
        check(len(raw['attempts']) == len(raw['opportunities']), scene + ':all attempt records')
        chosen_history = iter(raw['selector_history_suffix'])
        candidate_histogram, role_histogram = Counter(), Counter()
        for index, (attempt, opportunity) in enumerate(zip(raw['attempts'], raw['opportunities'])):
            label = scene + ':d' + str(index)
            check(attempt['decision_index'] == index and attempt['capture_status'] == 'saved', label + ':saved exact sequence')
            check(all(attempt[k] == opportunity[k] for k in ('time', 'version', 'node', 'bag_id', 'tray_id', 'candidate_count')), label + ':actual attempt identity')
            metadata = read(run / attempt['metadata_file'], attempt['metadata_sha256'])
            payload = pickle.loads(content(run / attempt['checkpoint_file'], attempt['checkpoint_sha256']))
            checkpoint = payload['checkpoint']
            base, state, cursor = checkpoint.base, checkpoint.state, checkpoint.cursor
            check(metadata['checkpoint_sha256'] == attempt['checkpoint_sha256'], label + ':metadata pickle binding')
            check(digest(semantic(checkpoint)) == metadata['checkpoint_fingerprint'], label + ':full instance fingerprint')
            check(digest(asdict(state)) == metadata['state_sha256'], label + ':state digest')
            check(canon(asdict(cursor)) == metadata['cursor'] == opportunity['cursor'], label + ':full current cursor')
            check(base.phase == metadata['phase'], label + ':physical phase')
            check(base.slow_controller.next_trigger_at == metadata['next_slow_trigger_at'] == opportunity['next_slow_trigger_at'], label + ':actual slow clock')
            check(canon([asdict(p) for p in payload['pool']]) == metadata['candidates'] == opportunity['candidates'] ==
                  canon([asdict(p) for p in cursor.pending_options]), label + ':entire pending pool')
            future = sorted((b for tasks in base.pending_arrivals.values() for b in tasks), key=lambda b: (b.arrival, b.bag_id))
            check(future == list(payload['future']), label + ':remaining exact event tape')
            check(all(b.arrival > state.now and b.bag_id not in state.bags for b in future), label + ':remaining unobserved identities')
            check(digest([asdict(b) for b in future]) == metadata['future_sha256'] == attempt['future_sha256'], label + ':future digest')
            fast = unwrapped(base.generator, 'generator')
            cache = metadata['routing_cache']
            check(canon(fast._owned_topology_cache.export()) == cache['fast_cache'], label + ':private cache all entries and LRU')
            check(digest(cache['fast_cache']) == cache['fast_cache_sha256'], label + ':private cache digest')
            check(metadata['search_prefix_count'] == len(base.generator.owner.rows), label + ':search prefix')
            check(metadata['selector_prefix_count'] == len(base.route_selector.history), label + ':selector prefix')
            check(metadata['trace_prefix_count'] == len(base.trace), label + ':execution trace prefix')
            check(not hasattr(base.generator, 'sink') and not hasattr(base.generator_factory, 'sink') and
                  not hasattr(base.slow_controller.controller.generator_factory, 'sink'), label + ':no observer sink restored')
            active = dict(metadata['active_continuation'])
            claimed = active.pop('sha256')
            check(digest(active) == claimed == attempt['continuation_sha256'], label + ':active contract digest')
            inner = base.slow_controller.controller
            check(type(inner).__module__ + '.' + type(inner).__qualname__ == active['controller_class'], label + ':actual continuation class')
            check({k: v for k, v in vars(inner).items() if isinstance(v, (str, int, float, bool)) or v is None}
                  == active['controller_scalars'], label + ':actual continuation scalars')
            check(canon([asdict(f) for f in base.slow_controller.forecast_publications]) == active['forecast_publications'], label + ':original publication schedule')
            check(canon([asdict(f) for f in inner.forecasts]) == metadata['published_slow_forecasts'] and
                  all(f.published_at <= state.now for f in inner.forecasts), label + ':published controller inputs only')
            query = queries[metadata['loaded_query_ordinal']]
            check(metadata['query_prefix_count'] == metadata['loaded_query_ordinal'] + 1, label + ':query capture position')
            check(query['callsite'] == 'engine_loaded' and query['bag_id'] == attempt['bag_id'] and
                  query['tray_id'] == attempt['tray_id'], label + ':actual loaded query')
            check(asdict(query['snapshot']) == asdict(state), label + ':same public generator input and decision state')
            raw_pool = canon([asdict(p) for p in query['options']])
            check(all(p in raw_pool for p in metadata['candidates']), label + ':authorized pool subset of actual raw query')
            if attempt['candidate_count']:
                selected = next(chosen_history)
                check(selected['candidates'] == metadata['candidates'], label + ':actual selector pool')
                check(metadata['candidates'][attempt['actual_chosen_index']] == selected['chosen'], label + ':actual chosen identity')
            else:
                check(attempt['actual_chosen_index'] is None, label + ':zero had no selector')
            candidate_histogram[attempt['candidate_count']] += 1
            role_histogram[attempt['role']] += 1
        check(next(chosen_history, None) is None, scene + ':no uncaptured selector')
        scene_rows.append(dict(scene=scene, attempts=len(raw['attempts']), query_records=len(queries),
            candidates=sum(r['candidate_count'] for r in raw['attempts']), zero=candidate_histogram[0],
            candidate_histogram=dict(candidate_histogram), role_histogram=dict(role_histogram)))
    for path, expected in bound.items():
        check(sha256(Path(path).read_bytes()).hexdigest() == expected, 'unchanged at finish:' + path)
    result = dict(schema='ics_v3_round7_independent_collection_audit_v1', checks=checks, errors=errors,
        scenes=scene_rows, bound_files=bound, bound_file_count=len(bound), new_physical_simulations=0,
        cpu_seconds=process_time() - cpu0, wall_seconds=perf_counter() - wall0,
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        resource_scope='Pure file/pickle structural audit through final rehash; report serialization/bootstrap excluded.')
    with (HERE / 'collection_artifact_audit.json').open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'bound_files'}))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main(BASE / (sys.argv[1] if len(sys.argv) > 1 else 'phase4_w3_same_zone_labels_20261010')))
