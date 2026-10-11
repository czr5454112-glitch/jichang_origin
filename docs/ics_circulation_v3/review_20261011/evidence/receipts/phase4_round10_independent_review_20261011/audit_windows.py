"""Independent business-window denominator/event/capacity/cost and chunk bridge.

Does not call the author's lifecycle_report or candidate validator. The two
optional continuation replays use the common engine only after raw audits.
"""
from collections import Counter, defaultdict
import argparse
from dataclasses import asdict
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import gzip
import json
from pathlib import Path
import pickle
import sys
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
RUNS = BASE.parent / 'phase4_round10_validation_20261011'
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, required=True,
                    help='Frozen source snapshot used by these window processes')
parser.add_argument('--attempts', nargs='+', default=['001'])
parser.add_argument('--runs', nargs='+', help='Explicit sealed run names, including separately budgeted continuation')
parser.add_argument('--output', default='window_review')
parser.add_argument('--bridge', action='store_true', help='Replay the original 001/002 chunk bridge with the supplied frozen source')
args = parser.parse_args()
SOURCE = args.source.resolve()
OUT = BASE / args.output
OUT.mkdir(exist_ok=False)
cpu, wall = process_time(), perf_counter()
sys.path.insert(0, str(SOURCE))
read_bindings = {}


def read(path):
    value = path.read_bytes()
    read_bindings[str(path.relative_to(ROOT))] = sha256(value).hexdigest()
    return value


def document(path):
    return json.loads(read(path))


checks = 0
def check(value, reason):
    global checks
    checks += 1
    if not value:
        raise AssertionError(reason)


def ceil_ratio(a, b):
    ratio = Fraction(Decimal(str(a))) / Fraction(Decimal(str(b)))
    return -(-ratio.numerator // ratio.denominator)


def sweep(slots, capacities, label):
    # Same carrier's overlapping descriptions consume a single physical unit.
    grouped = defaultdict(list)
    for resource, start, end, owner in slots:
        if end > start:
            grouped[resource, owner].append((start, end))
    events = defaultdict(lambda: defaultdict(int))
    for (resource, owner), intervals in grouped.items():
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        for start, end in merged:
            events[resource][start] += 1
            events[resource][end] -= 1
    maxima = {}
    for resource, changes in events.items():
        check(resource in capacities, label + ': unknown resource ' + resource)
        occupied = maximum = 0
        for at, change in sorted(changes.items()):
            occupied += change
            check(0 <= occupied <= capacities[resource], f'{label}: {resource}@{at} occupancy {occupied}')
            maximum = max(maximum, occupied)
        maxima[resource] = maximum
    return maxima


def audit_run(name):
    path = RUNS / name
    report = document(path / 'results.json')
    protocol = document(path / 'protocol.json')
    scope = document(path / 'scope.json')
    initial = document(path / 'initial_snapshot.json')
    tape = document(path / 'environment_tape.json')
    tasks = document(path / 'full_window_source_tasks.json')
    runtime_contract = document(path / 'runtime_contract.json')
    before, after = document(path / 'before.json'), document(path / 'after.json')
    check(report['success'] and not report.get('exception') and not report.get('final_result_failure'), name + ': execution failed')
    changed = sorted(p for p in before if before[p] != after[p])
    check(changed == sorted(report['source_changed']), name + ': undeclared source drift')
    for relative, digest in before.items():
        archived = SOURCE / relative
        expected_path = archived if archived.exists() else ROOT / relative
        check(sha256(expected_path.read_bytes()).hexdigest() == digest, name + ': frozen source differs ' + relative)
    for source, digest in scope['input_binding'].items():
        check(sha256(Path(source).read_bytes()).hexdigest() == digest, name + ': input binding')
    raw_path = next(Path(p) for p in scope['input_binding'] if p.endswith('nanning_1x_raw.txt'))
    raw_rows = [line.split() for line in read(raw_path).decode('utf-8-sig').splitlines()[1:] if line.strip()]
    first = min(Decimal(row[1]) for row in raw_rows)
    selected = {f'projected:1x:{row[0]}': row for row in raw_rows if first <= Decimal(row[1]) < first + Decimal(3600)}
    check(len(raw_rows) == scope['full_source_count'] == 28506, name + ': full raw denominator')
    check(set(selected) == set(scope['all_window_ids']), name + ': complete first-hour selection')
    check(len(selected) == len(tape) == len(tasks) == scope['included_count'], name + ': missing window tasks')
    bags = {bag['bag_id']: bag for bag in tape}
    check(set(bags) == set(selected), name + ': tape identities')
    node_by_id, edges = initial['network']['nodes'], initial['network']['edges']
    capacities = {'node:' + n: record['capacity'] for n, record in node_by_id.items()}
    capacities.update({'edge:' + e: record['capacity'] for e, record in edges.items()})
    capacities.update({'reception:' + n: initial['module']['reception_capacity'] for n in node_by_id})
    check(initial['now'] == 0 and not initial['bags'] and not initial['storage_progress'], name + ': future disclosure')
    initial_protocol = (document(RUNS / protocol['original_run'] / 'protocol.json')
                        if 'original_run' in protocol else protocol)
    check(len(initial['trays']) == initial_protocol['initial_carriers'] == 11, name + ': finite initial inventory')
    check(not initial['plans'] and not initial['old_in_transit'], name + ': unexpected warm-start plan')
    # Raw exact timestamps, not author-converted values, define the window.
    for task in tasks:
        ident = task['business_bag_id']
        row = selected[ident]
        check(Decimal(task['arrival_seconds']) == Decimal(row[1]) and Decimal(task['std_seconds']) == Decimal(row[2]), name + ': exact source seconds')
        check((task['origin'], task['final_destination']) == (row[3], row[4]), name + ': OD retained')
        check(bags[ident]['origin'] == row[3] and bags[ident]['destination'] == row[4], name + ': runtime OD retained')
        check(bags[ident]['arrival'] == task['arrival'] and bags[ident]['deadline'] == task['deadline'], name + ': task clock')
        check(bags[ident]['protected'] == task['protected'], name + ': protection retained')
        early = Decimal(row[2]) - Decimal(row[1]) >= Decimal(4800)
        check(('storage' in bags[ident]) == early, name + ': early business lifecycle')
        if early:
            check(bags[ident]['storage']['published_at'] <= bags[ident]['arrival'], name + ': unannounced release')
            check(bags[ident]['storage']['release_at'] == task['release_at'], name + ': release clock')
    physical = json.loads(gzip.decompress(read(path / 'final_result.json.gz')))
    final, trace = physical['final_snapshot'], physical['trace']
    now = final['now']
    check(set(final['trays']) == set(initial['trays']), name + ': invented/lost tray')
    visible_ids = {key for key, bag in bags.items() if bag['arrival'] <= now}
    check(set(final['bags']) == visible_ids, name + ': visible full denominator')
    check(set(final['completed']) <= visible_ids, name + ': impossible completion identity')
    check(set(report['lifecycle']['task_rows']) == set(bags), name + ': missing censored identity')
    check(report['lifecycle']['expected_business_tasks'] == len(bags), name + ': report denominator')
    check(set(physical['uncompleted_bag_ids']) == visible_ids - set(final['completed']), name + ': observed unfinished denominator')
    check([e['time'] for e in trace if e['event'] == 'tick'] == list(range(now + 1)), name + ': full clock without jumps')
    check([e['time'] for e in trace] == sorted(e['time'] for e in trace), name + ': trace order')
    state = {key: {'node': tray['node'], 'at': 0, 'bag': tray['bag_id'], 'flight': None,
                   'available': tray['available_at']} for key, tray in initial['trays'].items()}
    slots, loads, completions, ingress, releases = [], {}, {}, {}, {}
    edge_departures = {}
    empty_ticks = 0
    arrivals = {}
    for event in trace:
        at, kind = event['time'], event['event']
        check(0 <= at <= now, name + ': trace time range')
        if kind == 'bag_arrival':
            ident = event['bag_id']
            check(ident in bags and ident not in arrivals and at == bags[ident]['arrival'], name + ': actual arrival')
            arrivals[ident] = at
        elif kind == 'load':
            ident, owner = event['bag_id'], event['tray_id']
            check(ident not in loads and ident in arrivals and state[owner]['bag'] is None, name + ': physical loading identity')
            check(at >= state[owner]['available'], name + ': load before final service/hold')
            position = state[owner]['flight'][1] if state[owner]['flight'] and state[owner]['flight'][0] <= at else state[owner]['node']
            check(position == bags[ident]['origin'], name + ': loading at wrong place')
            state[owner]['bag'] = ident
            loads[ident] = {'time': at, 'tray_id': owner}
        elif kind == 'storage_arrival':
            ident, owner = event['bag_id'], event['tray_id']
            check(ident in bags and 'storage' in bags[ident] and ident not in ingress, name + ': storage ingress identity')
            flight = state[owner]['flight']
            check(flight and flight[0] == at and flight[1] == bags[ident]['storage']['node_id'], name + ': ingress lacks actual flight')
            check(state[owner]['bag'] == ident, name + ': ingress wrong carrier')
            ingress[ident] = {'time': at, 'tray_id': owner}
        elif kind == 'storage_departure':
            ident, owner = event['bag_id'], event['tray_id']
            check(ident in ingress and ident not in releases, name + ': release without ingress')
            check(ingress[ident]['tray_id'] == owner and state[owner]['bag'] == ident, name + ': storage carrier changed')
            check(at >= max(ingress[ident]['time'], bags[ident]['storage']['release_at']), name + ': early release')
            releases[ident] = {'time': at, 'tray_id': owner}
        elif kind == 'depart':
            owner, edge_id = event['tray_id'], event['edge_id']
            edge = edges[edge_id]
            carrier = state[owner]
            check(at >= carrier['available'], name + ': departure before final service/hold')
            if carrier['flight']:
                arrive, node = carrier['flight']
                check(arrive <= at, name + ': overlapping carrier motion')
                carrier['node'], carrier['at'] = node, arrive
            check(carrier['node'] == edge['source'], name + ': discontinuous actual motion')
            check(at == carrier['at'] or node_by_id[carrier['node']]['can_wait'], name + ': actual illegal waiting')
            slots.append(('node:' + carrier['node'], carrier['at'], at, owner))
            slots.append(('edge:' + edge_id, at, at + edge['travel_time'], owner))
            edge_departures[owner, at] = edge_id
            if carrier['bag'] is None:
                empty_ticks += edge['travel_time']
            else:
                ident = carrier['bag']
                if 'storage' in bags[ident] and edge['source'] == bags[ident]['storage']['node_id']:
                    check(ident in releases and releases[ident]['time'] <= at, name + ': storage exit lacks event')
            carrier['flight'] = (at + edge['travel_time'], edge['target'])
            carrier['node'] = None
        elif kind == 'unload_complete':
            ident, owner = event['bag_id'], event['tray_id']
            check(ident in loads and ident not in completions and state[owner]['bag'] == ident, name + ': business completion identity')
            flight = state[owner]['flight']
            check(flight and flight[1] == bags[ident]['destination'], name + ': final completion destination')
            check(at == flight[0] + initial['module']['unload_ticks'], name + ': final unload timing')
            if 'storage' in bags[ident]:
                check(ident in releases and at >= releases[ident]['time'], name + ': completion before storage release')
            if bags[ident]['protected']:
                check(at <= bags[ident]['deadline'], name + ': protected admitted late completion')
            completions[ident] = at
            state[owner]['bag'] = None
            state[owner]['available'] = at + initial['module']['hold_by_node'].get(bags[ident]['destination'], 0)
            slots.append(('reception:' + bags[ident]['destination'], flight[0], state[owner]['available'], owner))
        elif kind == 'tray_state' and event.get('mode') == 'unloading':
            owner = event['tray_id']
            ident = state[owner]['bag']
            check(ident is not None and event['node'] == bags[ident]['destination'], name + ': intermediate unload')
            flight = state[owner]['flight']
            check(flight and flight == (at, bags[ident]['destination']), name + ': unloading actual final arrival')
            state[owner]['available'] = at + initial['module']['unload_ticks'] + initial['module']['hold_by_node'].get(event['node'], 0)
            slots.append(('reception:' + event['node'], at, state[owner]['available'], owner))
        elif kind in ('tray_state', 'module_release') and event.get('mode') == 'empty':
            check(state[event['tray_id']]['bag'] is None, name + ': false empty during storage')
            check(at >= state[event['tray_id']]['available'], name + ': empty before service/hold release')
        elif kind == 'empty_dispatch':
            check(event['visible_bag_id'] in arrivals and arrivals[event['visible_bag_id']] <= at, name + ': future empty dispatch')
    check(set(arrivals) == visible_ids, name + ': trace lacks observed identities')
    check(completions == final['completed'], name + ': final ledger differs from actual events')
    check(set(final['storage_progress']) == set(ingress), name + ': storage milestone set')
    for ident, progress in final['storage_progress'].items():
        check(progress['tray_id'] == ingress[ident]['tray_id'] and progress['arrived_at'] == ingress[ident]['time'], name + ': milestone ingress binding')
        check(progress['departed_at'] == releases.get(ident, {}).get('time'), name + ': milestone release binding')
    for owner, carrier in state.items():
        flight = carrier['flight']
        if flight and flight[0] <= now:
            carrier['node'], carrier['at'] = flight[1], flight[0]
        if carrier['node'] is not None:
            slots.append(('node:' + carrier['node'], carrier['at'], now + 1, owner))
        check(carrier['node'] == final['trays'][owner]['node'], name + ': final physical position')
        check(carrier['bag'] == final['trays'][owner]['bag_id'], name + ': final physical load')
    maximum_occupancy = sweep(slots, capacities, name + ': actual occupancy')
    for ident, row in report['lifecycle']['task_rows'].items():
        check(row['observed'] == (ident in visible_ids) and row['uncompleted'] == (ident not in completions), name + ': report status')
        check(row['completed_at'] == completions.get(ident), name + ': report completion')
        check(row['loaded_at'] == loads.get(ident, {}).get('time') and row['tray_id'] == loads.get(ident, {}).get('tray_id'), name + ': report load')
        check(row['storage'] == final['storage_progress'].get(ident), name + ': report storage')
    expected_cost = {
        'tray_wait': sum(max(0, min(now, loads.get(ident, {}).get('time', now)) - bag['arrival']) for ident, bag in bags.items() if ident in visible_ids),
        'empty_distance': empty_ticks,
        'nonprotected_tardiness': sum(max(0, completions.get(ident, now) - bag['deadline']) for ident, bag in bags.items() if ident in visible_ids and not bag['protected']),
        'terminal_backlog': len(visible_ids) - len(completions),
        'terminal_inflight': sum(t['mode'] == 'in_transit' for t in final['trays'].values()),
    }
    check(expected_cost == physical['cost_components'] == report['lifecycle']['cost_components'], name + ': cost from actual events')
    expected_total = sum(expected_cost[k] * w for k, w in {'tray_wait': 1, 'empty_distance': .1, 'nonprotected_tardiness': 1, 'terminal_backlog': 10, 'terminal_inflight': 2}.items())
    check(abs(expected_total - physical['total_cost']) < 1e-8, name + ': total objective')
    statuses, query_count, maximum_expansions = Counter(), 0, 0
    query_bytes = read(path / 'queries.jsonl.gz')
    for line in gzip.decompress(query_bytes).splitlines():
        query = json.loads(line)
        statuses[query['status']] += 1
        query_count += 1
        maximum_expansions = max(maximum_expansions, query['expansions'])
        check(query['now'] <= now and query['tray_id'] in initial['trays'], name + ': query time/carrier')
        if query['bag_id'] is not None:
            check(query['bag_id'] in bags and bags[query['bag_id']]['arrival'] <= query['now'], name + ': future bag query leak')
        if query['diagnostics'].get('storage_mode'):
            check(sum(query['diagnostics']['work_units_by_stage'].values()) == query['expansions'], name + ': unaccounted storage work')
    check(dict(statuses) == report['search_status_counts'], name + ': query denominator')
    check(query_count + report.get('initial_generation_calls', 0) == physical['policy_stats']['generation_calls'], name + ': query generation count')
    check(maximum_expansions <= runtime_contract['routing']['expansion_limit'], name + ': search work budget')
    check(report['status'] in ('transport_drained', 'fixed_tick_cap_censored', 'cpu_cap_censored', 'wall_cap_censored',
                              'fixed_tail_cap_censored', 'additional_cpu_cap_censored', 'additional_wall_cap_censored'), name + ': stop classification')
    if report['status'] == 'transport_drained':
        check(len(completions) == len(bags) and not final['plans'] and all(t['mode'] == 'empty' for t in final['trays'].values()), name + ': false drained claim')
    matched_rows = []
    for point in sorted(path.glob('matched_*.json.gz')):
        saved = json.loads(gzip.decompress(read(point)))
        tick = saved['final_snapshot']['now']
        check(saved['trace'] == [e for e in trace if e['time'] <= tick], name + ': matched trace exact final prefix')
        visible = {key for key, bag in bags.items() if bag['arrival'] <= tick}
        done = {key: at for key, at in completions.items() if at <= tick}
        check(saved['completed'] == done and set(saved['final_snapshot']['bags']) == visible, name + ': matched public/completion census')
        check(set(saved['uncompleted_bag_ids']) == visible - set(done), name + ': matched observed denominator')
        matched_loads = {key: value for key, value in loads.items() if value['time'] <= tick}
        saved_cost = {
            'tray_wait': sum(max(0, matched_loads.get(key, {}).get('time', tick) - bag['arrival']) for key, bag in bags.items() if key in visible),
            'empty_distance': 0,
            'nonprotected_tardiness': sum(max(0, done.get(key, tick) - bag['deadline']) for key, bag in bags.items() if key in visible and not bag['protected']),
            'terminal_backlog': len(visible) - len(done),
            'terminal_inflight': 0,
        }
        load_by_owner, flights = {}, {}
        for event in saved['trace']:
            if event['event'] == 'load':
                load_by_owner[event['tray_id']] = event['bag_id']
            elif event['event'] == 'unload_complete':
                load_by_owner[event['tray_id']] = None
            elif event['event'] == 'depart':
                edge = edges[event['edge_id']]
                flights[event['tray_id']] = event['time'] + edge['travel_time']
                if load_by_owner.get(event['tray_id']) is None:
                    saved_cost['empty_distance'] += edge['travel_time']
        saved_cost['terminal_inflight'] = sum(arrive > tick for arrive in flights.values())
        check(saved_cost == saved['cost_components'], name + ': matched costs from actual prefix')
        matched_rows.append({'tick': tick, 'observed': len(visible), 'unobserved': len(bags)-len(visible),
                             'completed': len(done), 'cost_components': saved_cost, 'exact_final_trace_prefix': True})
    continuation = None
    if 'original_run' in protocol:
        prior_path = RUNS / protocol['original_run']
        prior_bytes = read(prior_path / 'final_result.json.gz')
        prior = json.loads(gzip.decompress(prior_bytes))
        checkpoint_bytes = read(path / 'input_checkpoint.pickle')
        checkpoint = pickle.loads(checkpoint_bytes)
        bridge = json.loads(gzip.decompress(read(path / 'bridge_at_original_stop.json.gz')))
        check(sha256(prior_bytes).hexdigest() == protocol['original_result_sha256'], name + ': original result binding')
        check(sha256(checkpoint_bytes).hexdigest() == protocol['checkpoint_sha256'], name + ': original checkpoint binding')
        check(bridge == prior and report['bridge_exact'], name + ': exact continuation bridge')
        check(prior['trace'] == [e for e in trace if e['time'] <= protocol['original_stop']], name + ': continuation retains original prefix')
        check(checkpoint.state.now == protocol['checkpoint_tick'] <= protocol['original_stop'] < now <= protocol['target_tick'], name + ': continuation clock domain')
        check(checkpoint.policy_stats['generation_calls'] == report['initial_generation_calls'], name + ': checkpoint counter offset')
        for filename in ('scope.json', 'environment_tape.json', 'full_window_source_tasks.json', 'runtime_contract.json', 'initial_snapshot.json'):
            check(read(path / filename) == read(prior_path / filename), name + ': continuation original input ' + filename)
        if report['status'] == 'fixed_tail_cap_censored':
            check(now == protocol['target_tick'] == 28500, name + ': complete declared tail')
        continuation = {'original_run': protocol['original_run'], 'original_stop': protocol['original_stop'],
                        'checkpoint_tick': checkpoint.state.now, 'bridge_exact': True,
                        'additional_cpu_cap_seconds': protocol['additional_cpu_cap_seconds'],
                        'qualification': 'Separate development budget and one restored physical branch; no new audit physics.'}
    return {'name': name, 'at': now, 'expected': len(bags), 'observed': len(visible_ids),
            'completed': len(completions), 'early_bags': sum('storage' in bag for bag in bags.values()),
            'unobserved': len(bags) - len(visible_ids), 'full_scope_uncompleted': len(bags) - len(completions),
            'ingress': len(ingress), 'released': len(releases), 'query_count': query_count,
            'status': report['status'], 'cost_components': expected_cost,
            'matched': matched_rows, 'continuation': continuation,
            'maximum_actual_occupancy': maximum_occupancy,
            'source_unchanged': not changed, 'source_changed_while_old_process_ran': changed,
            'runtime_identity': ('bound source drift retained; not a clean frozen experiment' if changed else
                                 'independently matched clean frozen source before/after')}, physical


report = {'status': 'running', 'source_snapshot': str(SOURCE), 'physical_replays': 0,
          'runs': [], 'chunk_bridges': [], 'exception': None,
          'scope': 'Raw evidence audit using the supplied frozen source; every run retains its observed source_changed status. Optional old chunk bridges compare physical results at identical ticks.'}
try:
    raw_results = {}
    run_names = args.runs or [f'business_window_h{horizon}_{attempt}' for horizon in (80, 21600) for attempt in args.attempts]
    for name in run_names:
        summary, raw_results[name] = audit_run(name)
        report['runs'].append(summary)
    # Restore the final preceding saved chunk boundary. This changes neither
    # the policy's physical one-second clock nor the source workload.
    from scripts.experiments.ics_circulation_v3.runtime import Simulation
    for horizon in ((80, 21600) if args.bridge else ()):
        target_name, chunk_name = f'business_window_h{horizon}_001', f'business_window_h{horizon}_002'
        target = raw_results[target_name]
        target_tick = target['final_snapshot']['now']
        checkpoints = list((RUNS / chunk_name).glob('checkpoint_*.pickle'))
        compatible = [p for p in checkpoints if int(p.stem.split('_')[-1]) <= target_tick]
        check(bool(compatible), 'missing checkpoint before single-tick stopping point')
        checkpoint_path = max(compatible, key=lambda p: int(p.stem.split('_')[-1]))
        checkpoint = pickle.loads(read(checkpoint_path))
        replay_cpu, replay_wall = process_time(), perf_counter()
        engine = Simulation.from_checkpoint(checkpoint)
        replay = asdict(engine.advance(target_tick))
        report['physical_replays'] += 1
        replay['policy_stats'] = {k: v for k, v in replay['policy_stats'].items() if not k.endswith('_ms')}
        replay = json.loads(json.dumps(replay))
        differences = sorted(k for k in set(replay) | set(target) if replay.get(k) != target.get(k))
        row = {'horizon': horizon, 'checkpoint_tick': checkpoint.state.now, 'target_tick': target_tick,
               'different_fields': differences, 'equal': not differences,
               'cpu_seconds_nested': process_time() - replay_cpu, 'wall_seconds_nested': perf_counter() - replay_wall,
               'scope': 'One continuation replay per horizon; all physical result fields compared, excluding only policy _ms clocks.'}
        report['chunk_bridges'].append(row)
        check(not differences, 'outer chunk continuation changed exact physics: ' + str(differences))
    for relative, digest in read_bindings.items():
        check(sha256((ROOT / relative).read_bytes()).hexdigest() == digest, 'audit input changed: ' + relative)
    report['status'] = 'passed'
except Exception:
    report['status'] = 'failed'
    report['exception'] = traceback.format_exc()
finally:
    report.update(checks=checks, cpu_seconds=process_time() - cpu, wall_seconds=perf_counter() - wall,
                  resource_scope='Entire process interval including imports/read/hash/raw audit and continuation physics; nested replay CPU not additive; initial imports and final receipt writes excluded.')
    (OUT / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (OUT / 'manifest.json').write_text(json.dumps({'inputs_sha256': read_bindings,
        'results_sha256': sha256((OUT / 'results.json').read_bytes()).hexdigest(),
        'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}, indent=2), encoding='utf-8')
    (OUT / 'audit_windows.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(report, indent=2))
sys.exit(0 if report['status'] == 'passed' else 1)
