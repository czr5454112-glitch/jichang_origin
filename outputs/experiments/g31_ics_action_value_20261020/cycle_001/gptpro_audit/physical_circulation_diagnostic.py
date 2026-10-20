"""Read-only fixed-commit airport state and positive-capacity path diagnostic.

No project imports, training, native execution, or dynamic feasibility claim.
The static path cost is independently implemented from the documented public
formula: source-node service + edge length/speed, then destination service.
"""
import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import heapq
import json
import math
from pathlib import Path


def read_json(path):
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('physical_circulation_diagnostic.json'))
    args = parser.parse_args()
    base = args.root / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/C00_receiver_recorded_budget_002'
    ip, rp = base / 'inputs/C00.json', base / 'C00/raw.json.gz'
    data, raw = read_json(ip), read_json(rp)
    state = raw['final_result']
    now = state['physical_clock']
    assert now == 59400 and not data['faults']
    jobs = {row['business_bag_id']: row for row in data['jobs']}
    statuses = Counter(row['status'] for row in state['jobs'])
    waiting = Counter(jobs[row['business_bag_id']]['origin'] for row in state['jobs']
                      if row['status'] == 'waiting_for_tray')
    nodes = {row['node']: row for row in data['node_contracts']}
    edges = {(row['from'], row['to']): row for row in data['edge_contracts']}
    service = {int(row[0]): max(float(row[2]), .001) for row in data['node_records']}
    adjacency = defaultdict(list)
    for u, v, length, speed in data['edge_records']:
        if edges[(u, v)]['capacity'] > 0:
            adjacency[u].append((v, max(float(length) / float(speed), .001)))

    def path(source, destination):
        queue = [(0., (source,), source)]
        best = {source: 0.}
        while queue:
            cost, route, node = heapq.heappop(queue)
            if cost > best[node]:
                continue
            if node == destination:
                return cost + service[node], route
            for nxt, duration in adjacency[node]:
                candidate = cost + service[node] + duration
                if candidate < best.get(nxt, math.inf):
                    best[nxt] = candidate
                    heapq.heappush(queue, (candidate, route + (nxt,), nxt))
        raise ValueError('no positive-capacity path')

    trays = {row['tray_id']: row for row in state['trays']}
    empty = [row for row in state['trays'] if row['mode'] == 'empty']
    examples = []
    for identity, destination in [('initial:95:0', 57), ('initial:149:0', 95)]:
        tray = trays[identity]
        assert tray['mode'] == 'empty' and tray['active_leg'] == -1 and tray['edge_to'] == -1
        cost, route = path(tray['node'], destination)
        examples.append({
            'tray': tray, 'destination': destination,
            'actual_waiting_at_destination': waiting[destination],
            'positive_capacity_path': list(route),
            'static_service_and_travel_seconds': cost,
            'node_zones': sorted({nodes[n]['zone'] for n in route}),
            'node_owners': sorted({nodes[n]['resource_owner'] for n in route}),
            'node_capacities': [nodes[n]['capacity'] for n in route],
            'edge_capacities': [edges[(u, v)]['capacity'] for u, v in zip(route, route[1:])],
            'edge_headways': [edges[(u, v)]['entry_headway'] for u, v in zip(route, route[1:])],
            'dynamic_receiver_or_fifo_feasibility_certified': False,
        })
    arrived = sum(row['arrival'] <= now for row in data['jobs'])
    restricted_cost = math.fsum(
        max(0., min(row['completed_at'] if row['status'] == 'completed' else now, now)
            - jobs[row['business_bag_id']]['arrival'])
        for row in state['jobs'] if jobs[row['business_bag_id']]['arrival'] <= now)
    result = {
        'fixed_commit': '13cf8eeb9e9692eaf9eaf8b2ebbaeee8e1001626',
        'native_runs': 0, 'training_runs': 0, 'project_imports': 0,
        'scope': 'saved-state counts and static topology only; not a native control experiment',
        'input_sha256': hashlib.sha256(ip.read_bytes()).hexdigest(),
        'raw_sha256': hashlib.sha256(rp.read_bytes()).hexdigest(),
        'physical_clock': now, 'population': len(jobs), 'arrived': arrived,
        'future_arrivals': len(jobs) - arrived, 'job_statuses': dict(statuses),
        'completed_over_arrived': statuses['completed'] / arrived,
        'restricted_population_sojourn_bag_seconds': restricted_cost,
        'tray_modes': dict(Counter(row['mode'] for row in state['trays'])),
        'empty_nodes': sorted({row['node'] for row in empty}),
        'empty_owners': sorted({nodes[row['node']]['resource_owner'] for row in empty}),
        'empty_trays': empty, 'waiting_by_origin': dict(sorted(waiting.items())),
        'initial_trays': data['trays'],
        'strict_nonharm_certified': raw['strict_nonharm_certified'],
        'examples': examples,
    }
    assert len(empty) == 13 and statuses['waiting_for_tray'] == 20491
    assert arrived == 20924 and statuses['completed'] == 430
    assert math.isclose(examples[0]['static_service_and_travel_seconds'], 169.652, abs_tol=1e-9)
    assert math.isclose(examples[1]['static_service_and_travel_seconds'], 147.202, abs_tol=1e-9)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in (
        'native_runs', 'training_runs', 'physical_clock', 'population', 'arrived',
        'job_statuses', 'tray_modes', 'empty_nodes', 'completed_over_arrived')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
