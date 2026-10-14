"""Source-bound static necessary domains; no assignment or physical simulation."""
from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction
import gzip
from hashlib import sha256
from heapq import heappop, heappush
import json
from pathlib import Path
from time import process_time, perf_counter

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'pyproject.toml').exists())
EXPERIMENTS = HERE.parent


def main():
    output = HERE / 'static_domains_001'
    output.mkdir()
    cpu, wall = process_time(), perf_counter()
    bindings = {}
    def read(path):
        value = path.read_bytes()
        bindings[str(path.relative_to(ROOT)).replace('\\', '/')] = sha256(value).hexdigest()
        return value
    old = EXPERIMENTS / 'phase4_w3_round8_business_input_research_repaired_20261010'
    business = EXPERIMENTS / 'phase4_round9_business_inputs_20261011'
    lifecycle = EXPERIMENTS / 'phase4_round9_storage_lifecycle_20261011'
    profile_path = ROOT / 'scripts/experiments/ics_circulation_v3/fixtures/nanning_airport_profile.json'
    profile = json.loads(read(profile_path), parse_float=Decimal)
    norm_path = old / 'business_tasks_1x.jsonl.gz'
    compressed = read(norm_path)
    norm_manifest = json.loads(read(old / 'manifest.json'))
    assert sha256(compressed).hexdigest() == norm_manifest['outputs'][norm_path.name]
    records = [json.loads(line, parse_float=Decimal) for line in gzip.decompress(compressed).splitlines()]
    audit = json.loads(read(business / 'audit_004.json'))
    assert audit['status'] == 'passed' and audit['scales'][0]['raw_business_count'] == len(records) == 28506
    root_scope = json.loads(read(lifecycle / 'business_window_h80_002/full_window_source_tasks.json'), parse_float=Decimal)
    scope2 = json.loads(read(lifecycle / 'business_window_h21600_002/full_window_source_tasks.json'), parse_float=Decimal)
    assert root_scope == scope2
    input_contract = json.loads(read(business / 'runtime_input_contract_002.json'), parse_float=Decimal)
    runtime_contract = json.loads(read(business / 'runtime_proxy_contract_002.json'), parse_float=Decimal)
    tick = Fraction(str(input_contract['tick_seconds']))
    assert tick == 1 and input_contract['protection']['policy'] == 'all'
    assert input_contract['deadline'] == {'policy': 'std_minus_lead', 'lead_seconds': '0'}
    unload_seconds = Fraction(str(runtime_contract['module']['unload_seconds']))
    def ceil_ratio(value):
        return -(-value.numerator // value.denominator)
    def ticks(value):
        return ceil_ratio(value / tick)
    unload_ticks = ticks(unload_seconds)
    assert unload_seconds == 1
    storage = input_contract['storage']['node_id']
    roles = profile['business_roles']
    loaders = tuple(sorted(map(str, roles['source_candidate_ids'])))
    goals = tuple(sorted(map(str, roles['sink_candidate_ids'])))
    adjacency = defaultdict(list)
    for edge in profile['edges']:
        if edge['capacity'] > 0:
            duration = Fraction(str(edge['length'])) / Fraction(str(edge['speed']))
            a, b = str(edge['start']), str(edge['end'])
            adjacency[a].append((b, f'{a}->{b}', duration, ticks(duration)))
    for values in adjacency.values():
        values.sort()
    def shortest(origin, unit):
        dist, paths, queue = {origin: Fraction(0)}, {origin: ()}, [(Fraction(0), origin)]
        while queue:
            cost, node = heappop(queue)
            if cost != dist[node]:
                continue
            for target, edge_id, seconds, tick_cost in adjacency[node]:
                new = cost + (seconds if unit == 'seconds' else tick_cost)
                candidate_path = paths[node] + (edge_id,)
                if target not in dist or new < dist[target] or (new == dist[target] and candidate_path < paths[target]):
                    dist[target], paths[target] = new, candidate_path
                    heappush(queue, (new, target))
        return dist, paths
    origins = set(loaders) | set(goals) | {storage}
    source_seconds = {o: shortest(o, 'seconds') for o in origins}
    source_ticks = {o: shortest(o, 'ticks') for o in origins}
    def segment(origin, destination):
        sec, paths = source_seconds[origin]
        ti, tick_paths = source_ticks[origin]
        reachable = destination in sec
        return dict(origin=origin, destination=destination, reachable=reachable,
                    seconds_fraction=str(sec[destination]) if reachable else None,
                    seconds_float=float(sec[destination]) if reachable else None,
                    ticks=int(ti[destination]) if reachable else None,
                    seconds_shortest_path=paths.get(destination), tick_shortest_path=tick_paths.get(destination))
    return_domain = {}
    for goal in goals:
        legal = [n for n in loaders if n in source_seconds[goal][0]]
        best_second = min(legal, key=lambda n: (source_seconds[goal][0][n], n)) if legal else None
        best_tick = min(legal, key=lambda n: (source_ticks[goal][0][n], n)) if legal else None
        return_domain[goal] = dict(legal_loaders=legal, reachable=bool(legal),
            min_seconds_loader=best_second, min_tick_loader=best_tick,
            min_seconds_fraction=str(source_seconds[goal][0][best_second]) if legal else None,
            min_ticks=int(source_ticks[goal][0][best_tick]) if legal else None,
            seconds_shortest_path=source_seconds[goal][1][best_second] if legal else None,
            tick_shortest_path=source_ticks[goal][1][best_tick] if legal else None)
    by_id = {r['business_bag_id']: r for r in records}
    first = min(Fraction(str(r['arrival_seconds'])) for r in records)
    expected_window = {r['business_bag_id'] for r in records if first <= Fraction(str(r['arrival_seconds'])) < first + 3600}
    assert {t['business_bag_id'] for t in root_scope} == expected_window and len(root_scope) == 44
    window_rows = []
    for task in root_scope:
        record = by_id[task['business_bag_id']]
        for key in ('origin', 'final_destination', 'lifecycle'):
            assert task[key] == record[key]
        assert task['source']['raw_task_id'] == record['source']['raw_task_id']
        assert task['source']['parent_task_id'] == record['source']['parent_task_id']
        assert task['source']['raw_sha256'] == record['source']['raw_sha256']
        assert Fraction(str(task['arrival_seconds'])) == Fraction(str(record['arrival_seconds']))
        incoming, outgoing = segment(task['origin'], storage), segment(storage, task['final_destination'])
        window_rows.append(dict(business_bag_id=task['business_bag_id'], raw_task_id=task['source']['raw_task_id'],
            parent_task_id=task['source']['parent_task_id'], raw_sha256=task['source']['raw_sha256'],
            parent_timetable_sha256=task['source']['parent_timetable_sha256'], source_line=task['source']['source_line'],
            arrival_seconds=task['arrival_seconds'], std_seconds=task['std_seconds'],
            lifecycle=task['lifecycle'], origin_to_storage=incoming, storage_to_final=outgoing,
            final_to_any_loader=return_domain[task['final_destination']],
            origin_to_original_final=segment(task['origin'], task['final_destination'])))
    groups = defaultdict(list)
    for record in records:
        flight = record['source']['flight_surrogate']
        key = (str(flight[0]), int(flight[1]), str(flight[2]))
        groups[key].append(record)
    flight_rows = []
    for key, tasks in sorted(groups.items()):
        original = {t['final_destination'] for t in tasks}
        assert len(original) == 1
        original = next(iter(original))
        reachable_domain, timed_domain = [], []
        rejected = Counter()
        blocked_origins = sorted({t['origin'] for t in tasks if t['lifecycle'] == 'early_storage' and storage not in source_seconds[t['origin']][0]})
        for goal in goals:
            if not return_domain[goal]['reachable']:
                rejected['no_return_to_any_loader'] += 1
                continue
            reach_ok, time_ok = True, True
            for task in tasks:
                origin = task['origin']
                arrival, std = Fraction(str(task['arrival_seconds'])), Fraction(str(task['std_seconds']))
                if task['lifecycle'] == 'early_storage':
                    if storage not in source_seconds[origin][0] or goal not in source_seconds[storage][0]:
                        reach_ok = False
                        break
                    release = Fraction(str(task['scheduled_release_seconds']))
                    earliest_tick = max(ticks(arrival) + source_ticks[origin][0][storage], ticks(release)) + source_ticks[storage][0][goal] + unload_ticks
                else:
                    if goal not in source_seconds[origin][0]:
                        reach_ok = False
                        break
                    earliest_tick = ticks(arrival) + source_ticks[origin][0][goal] + unload_ticks
                time_ok &= earliest_tick <= std // tick
            if reach_ok:
                reachable_domain.append(goal)
                if time_ok:
                    timed_domain.append(goal)
                else:
                    rejected['hard_deadline_travel_lower_bound'] += 1
            else:
                rejected['fixed_origin_lifecycle_unreachable'] += 1
        flight_rows.append(dict(flight_surrogate=key, business_count=len(tasks), raw_task_ids=sorted(t['source']['raw_task_id'] for t in tasks),
            fixed_origins=sorted({t['origin'] for t in tasks}), lifecycle_counts=dict(Counter(t['lifecycle'] for t in tasks)),
            original_destination=original, static_reachability_and_return_domain=reachable_domain,
            static_deadline_necessary_domain=timed_domain, unreachable_early_storage_origins=blocked_origins,
            original_destination_in_reachability_domain=original in reachable_domain,
            original_destination_in_deadline_necessary_domain=original in timed_domain,
            rejected_destination_counts=dict(rejected)))
    assert sum(f['business_count'] for f in flight_rows) == 28506 and len(flight_rows) == 360
    summary = dict(window_bags=len(window_rows), whole_source_business_bags=28506, flight_groups=360,
        window_origin_to_storage_unreachable=sum(not r['origin_to_storage']['reachable'] for r in window_rows),
        window_storage_to_final_unreachable=sum(not r['storage_to_final']['reachable'] for r in window_rows),
        window_final_to_any_loader_unreachable=sum(not r['final_to_any_loader']['reachable'] for r in window_rows),
        whole_flight_reachability_domain_size_counts=dict(Counter(len(f['static_reachability_and_return_domain']) for f in flight_rows)),
        whole_flight_deadline_necessary_domain_size_counts=dict(Counter(len(f['static_deadline_necessary_domain']) for f in flight_rows)),
        whole_flight_empty_reachability_domains=sum(not f['static_reachability_and_return_domain'] for f in flight_rows),
        whole_flight_empty_deadline_necessary_domains=sum(not f['static_deadline_necessary_domain'] for f in flight_rows),
        bags_in_whole_flight_empty_domains=sum(f['business_count'] for f in flight_rows if not f['static_reachability_and_return_domain']),
        original_destinations_outside_whole_flight_reachability_domain=sum(not f['original_destination_in_reachability_domain'] for f in flight_rows),
        no_destination_assignment_performed=True, no_physics=True)
    report = dict(status='passed', summary=summary, window_rows=window_rows, flight_rows=flight_rows,
        domain_definition='Fixed original origin; every bag in each complete original source flight; early must traverse storage53; final must return to at least one legal loader. Static positive-capacity directed topology only.',
        time_domain_definition='Additional necessary per-bag earliest completion using exact source arrival ceil, fixed release ceil, summed ceil edge ticks, explicit unload1s and protected STD floor. No queues or shared occupancy.',
        qualification='Domains are necessary conditions only, not joint calendar/capacity/owner/mode feasibility. No bag deletion, new/reversed edge, reallocation, or outcome reading.',
        input_sha256=bindings)
    for path_key, expected in bindings.items():
        assert sha256((ROOT / path_key).read_bytes()).hexdigest() == expected
    def default(value):
        if isinstance(value, Decimal): return str(value)
        raise TypeError(type(value).__name__)
    (output/'analysis.json').write_text(json.dumps(report, indent=2, default=default), encoding='utf-8')
    resource = dict(status='passed', cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
        physical_calls=0, scope='all static source reads, Dijkstra/domain enumeration and analysis write; imports/final resource/manifest write excluded',
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), input_sha256=bindings)
    (output/'resource.json').write_text(json.dumps(resource, indent=2), encoding='utf-8')
    (output/'manifest.json').write_text(json.dumps({'outputs':{p.name:sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.name!='manifest.json'}, 'script_sha256':resource['source_sha256']}, indent=2), encoding='utf-8')
    print(json.dumps({'summary':summary,'cpu_seconds':resource['cpu_seconds']},indent=2))


if __name__ == '__main__':
    main()
