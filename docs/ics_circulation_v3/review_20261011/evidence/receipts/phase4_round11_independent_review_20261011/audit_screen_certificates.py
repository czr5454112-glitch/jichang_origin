"""Rebuild every screened calendar from accepted complete itineraries and stock.

No production imports, route calls, validator calls, or physical replays. The
existing independent raw auditor separately checks actual motion/cost/capacity.
This audit binds each certificate to its saved public state and to candidate
options plus actual commitment trace, rather than trusting witness_slots.
"""
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import zip_longest
import argparse
import gzip
import json
from pathlib import Path
from time import process_time, perf_counter
import traceback

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
RUNS = BASE.parent / 'phase4_round11_validation_20261011'
parser = argparse.ArgumentParser()
parser.add_argument('--run', default='projected_h21600_screen_001')
parser.add_argument('--output', required=True)
args = parser.parse_args()
cpu, wall = process_time(), perf_counter()
OUT = BASE / args.output
OUT.mkdir(exist_ok=False)
RUN = RUNS / args.run
FOREVER = 10**12
bindings = {}
checks = 0


def check(condition, reason):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(reason)


def read(path):
    data = path.read_bytes()
    bindings[path.relative_to(ROOT).as_posix()] = sha256(data).hexdigest()
    return data


def document(name):
    return json.loads(read(RUN / name))


def lines(name):
    path = RUN / name
    read(path)  # compressed bytes are bound; streaming avoids uncompressed copies.
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            yield json.loads(line)


def merged(slots, now):
    groups = defaultdict(list)
    for resource, start, end, owner in slots:
        if end > max(start, now):
            groups[resource, owner].append((max(now, start), end))
    answer = {}
    for key, values in groups.items():
        union = []
        for start, end in sorted(values):
            if union and union[-1][1] >= start:
                union[-1][1] = max(union[-1][1], end)
            else:
                union.append([start, end])
        answer[key] = union
    return answer


def itinerary_slots(candidate, created, edges, bags, module):
    """Hand derive node waits, full-edge travel and permanent terminal stock."""
    owner = candidate['tray_id']
    node = edges[candidate['legs'][0]['edge_id']]['source'] if candidate['legs'] else candidate['destination_node']
    at, slots = created, []
    for leg in candidate['legs']:
        edge = edges[leg['edge_id']]
        check(edge['source'] == node and leg['depart'] >= at, 'discontinuous accepted plan')
        check(leg['arrive'] == leg['depart'] + edge['travel_time'], 'accepted plan physical edge clock')
        if leg['depart'] > at:
            slots.append(('node:' + node, at, leg['depart'], owner))
        slots.append(('edge:' + leg['edge_id'], leg['depart'], leg['arrive'], owner))
        node, at = edge['target'], leg['arrive']
    goal = bags[candidate['bag_id']]['destination'] if candidate['bag_id'] else candidate['destination_node']
    check(node == goal and not candidate['prefix_only'], 'certificate calendar requires complete real commitment')
    unload = at + (module['unload_ticks'] if candidate['bag_id'] else 0)
    usable = unload + module['hold_by_node'].get(node, 0)
    check((unload, usable) == (candidate['unload_complete'], candidate['usable_at']), 'accepted final service clock')
    slots.append(('node:' + node, at, FOREVER, owner))
    if usable > at:
        slots.append(('reception:' + node, at, usable, owner))
    return slots


report = {'status': 'running', 'physical_runs': 0, 'production_queries': 0, 'run': args.run,
          'exception': None, 'scope': 'Every certified state reconstructed from prior query options, actual commit events, idle stock and irrevocable old flights; no production calendar/certificate import.'}
try:
    result, protocol = document('results.json'), document('protocol.json')
    initial, tape = document('initial_snapshot.json'), document('environment_tape.json')
    physical = json.loads(gzip.decompress(read(RUN / 'final_result.json.gz')))
    check(result['success'] and not result['source_changed'], 'unsealed/changed source run')
    check(protocol['route_mode'] == 'whole_route' and protocol['screen_enabled'], 'certificate audited domain')
    before, after = document('before.json'), document('after.json')
    check(before == after, 'source binding drift')
    for relative, digest in before.items():
        check(sha256(read(RUN / 'source_snapshot' / relative)).hexdigest() == digest, 'frozen source ' + relative)
    bags = {bag['bag_id']: bag for bag in tape}
    commits = {(event['candidate_id'], event['time']): event for event in physical['trace']
               if event['event'] in ('route_commit', 'empty_dispatch', 'empty_continue')}
    departures = defaultdict(list)
    for event in physical['trace']:
        if event['event'] == 'depart':
            departures[event['tray_id']].append(event)
    actual_ingress = {event['bag_id']: event for event in physical['trace'] if event['event'] == 'storage_arrival'}
    actual_release = {event['bag_id']: event for event in physical['trace'] if event['event'] == 'storage_departure'}
    completions = physical['completed']
    candidates, bookings = defaultdict(list), {}
    states = iter(lines('screen_cert_states.jsonl.gz'))
    rows, certified, total_work, total_screen_cpu, total_observation_cpu = 0, 0, 0, 0., 0.
    counts, conflict_domains = Counter(), Counter()
    first_certificates = []
    for query, row in zip_longest(lines('queries.jsonl.gz'), lines('screen_rows.jsonl.gz')):
        check(query is not None and row is not None, 'query/screen census differs')
        rows += 1
        check(query['query_id'] == row['query_id'] == rows, 'monotone complete query IDs')
        check((query['now'], query['tray_id'], query['bag_id']) == (row['time'], row['tray_id'], row['bag_id']), 'row query identity')
        check(row['requested_k'] == 1 and row['search_work'] == query['expansions'] <= 10000, 'caller K or inner budget drift')
        check(row['search_status'] == query['status'] and row['phase'] == 'returned' and row['error'] is None, 'status/error loss')
        check(row['certificate'] == query['diagnostics']['terminal_screen'], 'certificate differs between raw ledgers')
        check(len(row['options']) == query['candidate_count'], 'filtered candidate census differs')
        counts[row['search_status']] += 1
        cert = row['certificate']
        check(cert['screen_work'] == sum(cert.get('work_by_stage', {}).values()), 'unaccounted screen work')
        total_work += cert['screen_work']
        total_screen_cpu += cert['screen_cpu_seconds']
        total_observation_cpu += row['observation_cpu_seconds']
        for candidate in row['options']:
            key = candidate['candidate_id']
            # Candidate IDs include snapshot version, not an absolute query ID;
            # different uncommitted empty destinations may share that label.
            candidates[key].append((candidate, row['time']))
        if not cert['certified']:
            continue
        certified += 1
        check(row['options'] == [] and row['search_work'] == 0, 'certified query searched/returned options')
        check(row['search_status'] == 'terminal_capacity_certificate', 'certified status')
        saved = next(states)
        check(saved['query_id'] == rows, 'certificate missing or attached to wrong query')
        state = saved['snapshot']
        digest = sha256(json.dumps(state, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        check(digest == saved['public_snapshot_sha256'] == row['public_snapshot_sha256'], 'public state hash mismatch')
        now = state['now']
        check(now == row['time'] and state['version'] == row['version'], 'public state clock/version')
        check(state['network'] == initial['network'] and state['module'] == initial['module'], 'physical graph/module changed')
        check(set(state['trays']) == set(initial['trays']), 'carrier identity changed')
        visible = {key: bag for key, bag in bags.items() if bag['arrival'] <= now}
        check(state['bags'] == visible, 'public bag census/field mutation/future leak')
        check(state['completed'] == {key: at for key, at in completions.items() if at <= now}, 'completion state not backed by actual event')
        check(set(state['storage_progress']) == {key for key, event in actual_ingress.items() if event['time'] <= now}, 'missing actual storage milestone')
        for key, progress in state['storage_progress'].items():
            event = actual_ingress.get(key)
            check(event is not None and event['time'] == progress['arrived_at'] <= now
                  and event['tray_id'] == progress['tray_id'], 'storage ingress is not actual')
            check(progress['contract'] == visible[key]['storage'], 'storage contract changed')
            if progress['departed_at'] is not None:
                event = actual_release.get(key)
                check(event is not None and event['time'] == progress['departed_at'] <= now
                      and event['tray_id'] == progress['tray_id'], 'storage release is not actual')
        expected, extra = [], []
        for owner, plan in state['plans'].items():
            key = plan['candidate_id']
            matching = [at for candidate, at in candidates[key] if candidate == plan and (key, at) in commits and at <= now]
            check(bool(matching), 'plan not among preceding complete options with actual commitment')
            created = max(matching)
            cache_key = key, created, sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
            if cache_key not in bookings:
                bookings[cache_key] = itinerary_slots(plan, created, state['network']['edges'], bags, state['module'])
            expected.extend(bookings[cache_key])
        old_ids = set()
        for flight in state['old_in_transit']:
            owner = flight['tray_id']
            old_ids.add(owner)
            edge = state['network']['edges'][flight['edge_id']]
            extra.extend((('edge:' + edge['edge_id'], flight['depart'], flight['arrive'], owner),
                          ('node:' + edge['target'], flight['arrive'], FOREVER, owner)))
            tray = state['trays'][owner]
            if not tray['bag_id'] or bags[tray['bag_id']]['destination'] == edge['target']:
                end = flight['arrive'] + (state['module']['unload_ticks'] if tray['bag_id'] else 0) + state['module']['hold_by_node'].get(edge['target'], 0)
                extra.append(('reception:' + edge['target'], flight['arrive'], end, owner))
        for owner, tray in state['trays'].items():
            if owner in state['plans'] or owner in old_ids or tray['node'] is None:
                continue
            past = [event for event in departures[owner] if event['time'] < now]
            if past:
                event = past[-1]
                edge = state['network']['edges'][event['edge_id']]
                check(event['time'] + edge['travel_time'] <= now and tray['node'] == edge['target'], 'idle stock lacks actual arrival')
            else:
                check(tray['node'] == initial['trays'][owner]['node'], 'idle stock moved without actual departure')
            extra.append(('node:' + tray['node'], now, FOREVER, owner))
            if tray['mode'] in ('unloading', 'holding') and tray['available_at'] > now:
                extra.append(('reception:' + tray['node'], now, tray['available_at'], owner))
        declared = [(s['resource'], s['start'], s['end'], s['tray_id']) for s in state['reservations']]
        rebuilt = merged(expected + extra, now)
        check(rebuilt == merged(declared + extra, now), 'published calendars differ from actual complete commitments/stock')
        check(cert['cutoff'] == now + protocol['search_horizon'], 'certificate horizon was changed')
        destination, owner = row['destination'], row['tray_id']
        check(destination == (visible[row['bag_id']]['destination'] if row['bag_id'] else query['destination']), 'wrong target certificate')
        capacity = state['network']['nodes'][destination]['capacity']
        target = [('node:' + destination, start, end, peer) for (resource, peer), intervals in rebuilt.items()
                  if resource == 'node:' + destination and peer != owner for start, end in intervals]
        ticks = {cert['cutoff']}
        ticks.update(max(cert['cutoff'], start) for _, start, end, peer in target if end > cert['cutoff'])
        ticks.update(end for _, start, end, peer in target if cert['cutoff'] <= end < FOREVER)
        first = next((tick for tick in sorted(ticks) if tick < FOREVER and
                      len({peer for _, start, end, peer in target if start <= tick < end}) >= capacity), None)
        check(first is not None and first == cert['conflict_at'], 'no independently reconstructed terminal conflict')
        owners = {peer for _, start, end, peer in target if start <= first < end}
        check(len(owners) == cert['other_occupancy'] >= capacity == cert['capacity'], 'wrong distinct-carrier conflict count')
        witness = sorted((peer, start, end) for _, start, end, peer in target if start <= first < end)
        check(witness == sorted((s['tray_id'], s['start'], s['end']) for s in cert['witness_slots']), 'witness_slots not actual merged peer calendar')
        check(owner not in owners, 'query carrier incorrectly counted as an obstacle')
        check(cert['work_by_stage']['effective_slots'] == sum(len(v) for v in rebuilt.values()), 'effective-slot work count')
        conflict_domains[destination] += 1
        if len(first_certificates) < 12:
            first_certificates.append({'query_id': rows, 'now': now, 'bag_id': row['bag_id'], 'destination': destination,
                                       'cutoff': cert['cutoff'], 'conflict_at': first, 'owners': sorted(owners)})
    check(next(states, None) is None, 'unmatched extra certificate states')
    check(rows == physical['policy_stats']['generation_calls'], 'runtime query denominator')
    check(dict(counts) == result['search_status_counts'], 'runtime query status counts')
    accounting = result['screen_accounting']
    check(total_work == accounting['screen_work'], 'screen work total')
    check(abs(total_screen_cpu - accounting['screen_cpu_seconds_nested']) < 1e-8, 'screen CPU total')
    check(abs(total_observation_cpu - accounting['observation_cpu_seconds_nested']) < 1e-8, 'observation CPU total')
    comparison = []
    for tick in (10080, 11640):
        off = RUNS / 'projected_h21600_001' / ('final_result.json.gz' if tick == 11640 else f'matched_{tick}.json.gz')
        on = RUN / f'matched_{tick}.json.gz'
        check(json.loads(gzip.decompress(read(off))) == json.loads(gzip.decompress(read(on))), 'screen changed exact common-tick physical result')
        comparison.append({'tick': tick, 'exact_physical_result': True})
    for relative, digest in bindings.items():
        check(sha256((ROOT / relative).read_bytes()).hexdigest() == digest, 'input changed while auditing: ' + relative)
    report.update(status='passed', query_rows=rows, certified_queries=certified, conflict_destinations=dict(conflict_domains),
                  screen_work=total_work, screen_cpu_nested=total_screen_cpu, observation_cpu_nested=total_observation_cpu,
                  first_certificates=first_certificates, matched_screen_off=comparison,
                  qualification='Current-calendar finite-horizon full-witness rejection only. The same query may become feasible after real carrier movement; this is not permanent task infeasibility or general search completeness.')
except Exception:
    report.update(status='failed', exception=traceback.format_exc())
finally:
    report.update(checks=checks, cpu_seconds=process_time()-cpu, wall_seconds=perf_counter()-wall,
                  resource_scope='Read/hash/stream/reconstruct all certificate evidence; no simulation, generator or production imports; initial imports/final receipts excluded.')
    (OUT / 'results.json').write_text(json.dumps(report, indent=2))
    (OUT / 'manifest.json').write_text(json.dumps({'inputs_sha256': bindings,
        'script_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
        'results_sha256': sha256((OUT / 'results.json').read_bytes()).hexdigest()}, indent=2))
    (OUT / Path(__file__).name).write_bytes(Path(__file__).read_bytes())
    print(json.dumps(report, indent=2))
raise SystemExit(report['status'] != 'passed')
