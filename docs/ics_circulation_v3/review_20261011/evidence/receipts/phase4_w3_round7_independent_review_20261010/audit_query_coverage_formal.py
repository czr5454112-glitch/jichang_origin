"""Independent file/authorization audit; no routing search or physical replay."""
from collections import Counter, defaultdict
from dataclasses import asdict
from hashlib import sha256
import gzip
import json
from pathlib import Path
import pickle
import sys
from time import perf_counter, process_time

from audit_collection import ROOT, HERE, BASE, canon, digest, physical
from scripts.experiments.ics_circulation_v3.model import RouteCandidate, Leg
from scripts.experiments.ics_circulation_v3.runtime import ExecutionValidator, actual_action_key


def without_ms(value):
    if isinstance(value, dict):
        return {k: without_ms(v) for k, v in value.items() if not k.endswith('_ms')}
    if isinstance(value, (list, tuple)):
        return [without_ms(v) for v in value]
    return value


def main(run, stage):
    wall, cpu = perf_counter(), process_time()
    bound, errors, checks = {}, [], 0

    def check(ok, label):
        nonlocal checks
        checks += 1
        if not ok:
            errors.append(label)

    def data(path, expected=None):
        path = Path(path).resolve()
        value = path.read_bytes()
        actual = sha256(value).hexdigest()
        check(expected is None or actual == expected, 'SHA:' + str(path))
        if expected is not None and actual != expected:
            raise ValueError('refuse mismatching artifact ' + str(path))
        check(str(path) not in bound or bound[str(path)] == actual, 'stable read:' + str(path))
        bound[str(path)] = actual
        return value

    def read(path, expected=None):
        path = Path(path)
        value = data(path, expected)
        return json.loads(gzip.decompress(value) if path.name.endswith('.gz') else value)

    def absolute_manifest(path):
        entries = read(path)
        for p, expected in entries.items():
            data(p, expected)
        return entries

    protocol = read(run / 'protocol.json')
    absolute_manifest(run / 'preparation_manifest.json')
    for kind, current in [('source', ROOT / 'scripts/experiments/ics_circulation_v3'), ('test', ROOT / 'tests')]:
        for name, expected in protocol[kind + '_sha256'].items():
            data(current / name, expected)
            data(run / (kind + '_snapshot') / name, expected)
    for p, expected in protocol['input_sha256'].items():
        data(p, expected)
    data(ROOT / 'cpp/ics_core/runtime/bounded_local_pibt.hpp', 'b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951')
    reuse = read(run / 'collection_reuse.json')
    origin = Path(protocol['reused_collection_root'])
    check(str(origin) == reuse['origin'] and reuse['new_physical_calls'] == 0 and reuse['original_physical_calls'] == 27,
          'certified zero additional physical collection')
    for p, expected in reuse['files_sha256'].items():
        data(p, expected)
    old_protocol = read(origin / 'protocol.json')
    for kind in ('source', 'test'):
        for name, expected in old_protocol[kind + '_sha256'].items():
            data(origin / (kind + '_snapshot') / name, expected)
    old = BASE / 'phase4_w3_same_zone_supply_repaired_20261010'
    prior_manifest = read(old / 'full/manifest.json')
    for name, expected in prior_manifest.items():
        data(old / 'full' / name, expected)
    requests = {r['case_id']: r for r in read(old / 'full/summary.json')['rows'] if r['policy'] == 'same_zone32plus32'}
    check(len(requests) == 27 and set(requests) == {r['case_id'] for r in protocol['requests']}, 'all27 exact round6 policy episodes')
    collected = read(origin / 'collections/summary.json')
    check(len(collected['rows']) == 27 and {r['case_id'] for r in collected['rows']} == set(requests), 'all27 actual collector outcomes')
    previous = read(HERE / 'query_coverage_pilot_audit.json')
    check(not previous['errors'] and previous['collection_cases'] == 27 and previous['query_count'] == 2467,
          'previous complete independent collection audit succeeded')
    data(HERE / 'audit_query_coverage.py', previous['source_sha256'])
    for path, expected in previous['bound_files'].items():
        data(path, expected)
    query_rows, query_counts, truncated = [], Counter(), Counter()
    collection_checks = 27
    for row in collected['rows']:
        index = read(origin / row['query_index_file'], row['query_index_sha256'])
        query_rows.extend(index)
        for query in index:
            query_counts[query['scene']] += 1
            truncated[query['last_search_status']] += 1
    check(len(query_rows) == 2467 and truncated['expansion_budget_exhausted'] == 93,
          'fully rehashed certified collection and all query identities')
    absolute_manifest(run / 'selection_manifest.json')
    selected = read(run / 'selection.json')
    cell = lambda r: tuple(r[k] for k in ('scene', 'callsite', 'source', 'destination', 'requested_k', 'protected'))
    order = lambda r: (r['case_id'], r['time'], r['query_ordinal'])
    exhausted = [r for r in query_rows if r['last_search_status'] == 'expansion_budget_exhausted']
    successes = defaultdict(list)
    for r in query_rows:
        if r['last_search_status'] == 'candidate_limit_reached' and r['raw_candidate_count'] > 0:
            successes[cell(r)].append(r)
    expected = {r['query_id']: {**r, 'selection': 'all_truncated'} for r in exhausted}
    controls = []
    for c in sorted({cell(r) for r in exhausted}):
        control = min(successes[c], key=order) if successes[c] else None
        controls.append({'cell': list(c), 'control_query_id': None if control is None else control['query_id'], 'available_successful_queries': len(successes[c])})
        if control is not None:
            expected[control['query_id']] = {**control, 'selection': 'earliest_successful_control'}
    expected = sorted(expected.values(), key=order)
    check(selected['formal'] == expected and selected['controls'] == controls, 'independently recomputed complete feature-only selection')
    pilot = set()
    for scene in sorted({r['scene'] for r in exhausted}):
        first = min((r for r in exhausted if r['scene'] == scene), key=order)
        pilot.add(first['query_id'])
        c = next(c for c in controls if tuple(c['cell']) == cell(first))
        if c['control_query_id'] is not None:
            pilot.add(c['control_query_id'])
    check(selected['pilot'] == [r for r in expected if r['query_id'] in pilot] and selected['selection_before_shadow_outcomes'], 'predeclared pilot and no value selection')
    variant_counts, request_count = Counter(), 0
    if stage != 'collection':
        absolute_manifest(run / (stage + '_manifest.json'))
        summary = read(run / stage / 'summary.json')
        planned = {r['query_id']: r for r in selected[stage]}
        check(len(summary['rows']) == summary['planned_requests'] == len(planned) and
              {r['query_id'] for r in summary['rows']} == set(planned), 'all planned probe outcome identities')
        for row in summary['rows']:
            identity = row['query_id']
            if not row.get('file'):
                check(row['status'] != 'completed_shadow_probe', identity + ':explicit missing artifact failure')
                continue
            raw = read(run / row['file'], row['sha256'])
            request = planned[identity]
            check(raw['request'] == request, identity + ':entire selected request')
            query = pickle.loads(gzip.decompress(data(origin / request['file'], request['sha256'])))
            state = query['snapshot']
            if row['status'] != 'completed_shadow_probe':
                continue
            result = raw['result']
            check(result['input_sha256'] == digest(asdict(state)) and result['no_physical_branch_executed'], identity + ':public-only no execution')
            variants = result['variants']
            check([r['variant'] for r in variants] == ['regional3000', 'regional12000', 'regional48000', 'fullgraph_event48000'], identity + ':all four fixed queries')
            original_keys = None
            original_usable = None
            for v, limit in zip(variants, (3000, 12000, 48000, 48000)):
                label = identity + ':' + v['variant']
                variant_counts[v['variant']] += 1
                check(v['settings'] == {'horizon': query['generator_settings']['horizon'], 'expansion_limit': limit,
                      'requested_k': query['requested_k'], 'deadline_ms': None}, label + ':same K/H and declared work cap')
                mode = 'whole_route' if query['callsite'] == 'slow_empty' else 'next_edge'
                check(v['execution_mode_for_authorization'] == mode and not v['failure'] and v['query_input_unchanged'], label + ':original authorization scope')
                accepted, rejected, keys = [], [], []
                for option in v['raw_options']:
                    restored = RouteCandidate(**{**option, 'legs': tuple(Leg(**leg) for leg in option['legs'])})
                    verdict = ExecutionValidator().validate(state, restored, route_mode=mode)
                    if verdict.accepted:
                        accepted.append(option)
                        keys.append(actual_action_key(state, restored, route_mode=mode))
                    else:
                        rejected.append({'candidate': option, 'reason': verdict.reason})
                check(accepted == v['authorized_options'] and rejected == v['rejections'] and keys == v['actual_action_keys'], label + ':independently revalidated complete raw candidate pool')
                check(len(v['raw_options']) == v['raw_candidate_count'] and len(accepted) == v['authorized_candidate_count'] <= query['requested_k'], label + ':complete unchanged K denominator')
                minimum = min((o['usable_at'] for o in accepted), default=None)
                check(minimum == v['minimum_usable_at'], label + ':actual returned pool minimum')
                if v['variant'] == 'regional3000':
                    check(v['raw_options'] == canon([asdict(o) for o in query['options']]) and
                          v['status'] == query['last_search_status'] and v['work'] == query['last_expansions'] and v['original_query_reproduced'], label + ':strict original logical query reproduction')
                    original_keys, original_usable = set(keys), minimum
                check(v['new_authorized_action_keys'] == sorted(set(keys) - original_keys) and
                      v['earlier_usable_than_original'] == (original_usable is not None and minimum is not None and minimum < original_usable) and
                      v['resolves_original_zero'] == (not original_keys and bool(keys)), label + ':bounded coverage classification')
            check(digest(asdict(state)) == query['public_snapshot_sha256'], identity + ':validator did not mutate input')
            request_count += 1
    for path, expected in bound.items():
        check(sha256(Path(path).read_bytes()).hexdigest() == expected, 'final unchanged:' + path)
    report = dict(schema='round7_independent_query_coverage_audit_v1', stage=stage, checks=checks, errors=errors,
        collection_cases=collection_checks, query_count=len(query_rows), query_scene_counts=dict(query_counts),
        query_status_counts=dict(truncated), selected_query_count=len(selected['formal']),
        successfully_audited_probe_requests=request_count, audited_variant_counts=dict(variant_counts),
        bound_files=bound, new_physical_simulations=0, new_routing_searches=0,
        scope='Bind and rehash prior complete independent27/2467 query audit; independently inspect all99 formal shadow options and rerun pure ExecutionValidator only. No prior collection re-parsing or new search.',
        cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    path = HERE / ('query_coverage_' + stage + '_audit.json')
    with path.open('x', encoding='utf8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k:v for k,v in report.items() if k != 'bound_files'}))
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main(Path(sys.argv[1]), sys.argv[2]))
