"""Offline path/permission screen after cap8, never an executable policy.

All remaining heads are deliberately revealed offline. This relaxation cannot
certify live information, native path selection, capacity, timing or protection.
"""
from collections import Counter, deque
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(gzip.decompress(p.read_bytes()) if p.suffix == '.gz' else p.read_bytes())


def main():
    began = time.perf_counter()
    target = OUT / 'original_recirculation_screen_001'
    assert not target.exists()
    case = OUT / 'original_low_wip_cap_relay_prepare_001/cap8'
    bound_path = OUT / 'original_carrier_bound_002/analysis.json.gz'
    actual_path = OUT / 'original_low_wip_cap_relay_actual_review_001.json'
    assert sha(actual_path) == '9b30bdc7abb24e65e4ad4816653f2835e4259d1b882145f517db357cc450e69e'
    assert sha(bound_path) == 'd8425de32b66fc129e5e5b133c0b3335228e0c102d8047b8726babaddad4e8e4'
    actual, bound = read(actual_path), read(bound_path)
    plan = read(case / 'preregistered_protocol.json')
    for name in ('input.json.gz', 'all_job_states.json.gz', 'preregistered_protocol.json', 'independent_verification.json'):
        assert sha(case / name) == actual['evidence_sha256']['cap8/' + name]
    data, outcomes = read(case / 'input.json.gz'), read(case / 'all_job_states.json.gz')
    raw = read(case / 'raw_final.json.gz')
    producer = read(case.parent / 'receipt.json')
    raw_key = str((case / 'raw_final.json.gz').relative_to(case.parent))
    assert sha(case / 'raw_final.json.gz') == producer['artifact_sha256'][raw_key]
    archived = case / 'compiled_source_archive/cpp/ics_core/runtime/circulation_runtime_impl.hpp'
    relative = str(archived.relative_to(case / 'compiled_source_archive'))
    assert sha(archived) == plan['compiled_source_sha256'][relative]
    code = archived.read_text(encoding='utf8')
    for text in ('same_zone_transfer_not_authorized', 'source_module_min_stock', 'receiving_full', 'empty_return'):
        assert text in code
    nodes = {n['node']: n for n in data['node_contracts']}
    roles = {n[0]: n[1] for n in data['node_records']}
    edges = {(e['from'], e['to']): e['capacity'] for e in data['edge_contracts']}
    graph = {n: [] for n in nodes}
    for u, v, length, speed in data['edge_records']:
        assert length > 0 and speed > 0
        if edges[u, v] > 0 and nodes[u]['capacity'] > 0 and nodes[v]['capacity'] > 0:
            graph[u].append(v)
    paths = {}
    for start in nodes:
        seen, queue = {start: [start]}, deque([start])
        while queue:
            u = queue.popleft()
            for v in sorted(graph[u]):
                if v not in seen:
                    seen[v] = seen[u] + [v]
                    queue.append(v)
        paths[start] = seen
    jobs = {j['business_bag_id']: j for j in data['jobs']}
    completed = {j['business_bag_id'] for j in outcomes['jobs'] if j['status'] == 'completed'}
    assert completed == set(actual['completed_ids']) and len(completed) == 8
    prefixes = {l['origin']: [r['business_bag_id'] for r in l['jobs_in_native_fifo_order']
                             if r['unreachable_through_prefix'] == 0] for l in bound['loaders']}
    assert sum(map(len, prefixes.values())) == 39 and completed <= set(sum(prefixes.values(), []))
    for ids in prefixes.values():
        count = sum(j in completed for j in ids)
        assert set(ids[:count]) == set(ids) & completed
    token = plan['parking_plan']['token_tray_id']
    parked = Counter(p['destination'] for p in plan['parking_plan']['parking'] if p['tray_id'] != token)
    final = next(t for t in raw['result']['trays'] if t['tray_id'] == token)
    assert final['mode'] == 'empty' and final['job'] == final['edge_to'] == final['reception_node'] == -1
    assert len(raw['result']['trays']) == len(data['trays']) == 22 and len(jobs) == 28506

    def transfer(source, destination):
        # Only a relaxed stationary occupancy/stock screen. Actual route and
        # receiver reservations must still pass native source/receiver checks.
        a, b = nodes[source], nodes[destination]
        return (source != destination and a['zone'] != b['zone'] and a['allow_export']
                and b['allow_receive'] and parked[source] + 1 > a['export_min_stock']
                and parked[destination] < b['capacity'] and destination in paths[source])

    runs = {}
    for mode in ('direct_only', 'direct_then_one_bridge'):
        remaining = {o: [j for j in ids if j not in completed] for o, ids in prefixes.items()}
        position, trace = final['node'], []
        for _ in range(39):
            candidates = []
            for origin, ids in remaining.items():
                if not ids:
                    continue
                job = jobs[ids[0]]
                stages = [job['origin'], job['storage_node'], job['destination']]
                assert all(b in paths[a] for a, b in zip(stages, stages[1:]))
                route = [position, origin] if transfer(position, origin) else None
                if route is None and mode == 'direct_then_one_bridge':
                    bridges = [n for n in nodes if roles[n] not in (1, 7)
                               and transfer(position, n) and transfer(n, origin)]
                    if bridges:
                        route = [position, min(bridges), origin]
                if route:
                    candidates.append((job['arrival'], job['business_bag_id'], origin, route))
            if not candidates:
                break
            _, identity, origin, route = min(candidates)
            job = jobs[identity]
            trace.append({'job': identity, 'from': position, 'origin': origin, 'destination': job['destination'],
                          'empty_transfer_endpoints': route,
                          'positive_empty_paths': [paths[a][b] for a, b in zip(route, route[1:])],
                          'positive_mandatory_paths': [paths[job['origin']][job['storage_node']],
                                                       paths[job['storage_node']][job['destination']]]})
            remaining[origin].pop(0)
            position = job['destination']
        runs[mode] = {'relaxed_additional_count': len(trace), 'actual8_plus_relaxed_count': 8 + len(trace),
                      'bridge_count': sum(len(r['empty_transfer_endpoints']) == 3 for r in trace),
                      'terminal_position': position, 'remaining_heads': {str(o): ids[0] for o, ids in remaining.items() if ids},
                      'trace': trace}
    evidence = {str(p.relative_to(OUT)): sha(p) for p in (actual_path, bound_path,
        case / 'input.json.gz', case / 'all_job_states.json.gz', case / 'raw_final.json.gz',
        case / 'preregistered_protocol.json', archived)}
    report = {'schema': 'g31.original_recirculation_relaxed_screen.v1',
              'status': 'offline_relaxed_path_witness_only', 'recorded_utc': datetime.now(timezone.utc).isoformat(),
              'source_sha256': sha(Path(__file__)), 'evidence_sha256': evidence,
              'offered': 28506, 'trays': 22, 'actual_completed': 8, 'zero_bad_prefix_bound': 39,
              'cases': runs, 'native_calls': 0, 'projection_calls': 0, 'online_policy_input': False,
              'whole_day_goal_met': False, 'strict_protection_certified': False,
              'precheck_correction': 'First read stopped before graph work or output: producer uses Windows relative path keys. Read the exact key and derive it with pathlib; no evidence changed.',
              'limits': ['All future heads are revealed offline; no live delivered snapshots or ACK authorization.',
                         'No timing, release schedule, native route selection or dynamic berth/FIFO reservation proof.',
                         'A direct-only greedy trace is not a maximum or impossibility certificate.',
                         'Two individually authorized cross-zone endpoints do not authorize the second operation before new owner-local validation.',
                         'Current frozen cap8 policy forbids new actions. This is a separate future design, not restoration or continuation of its terminal state.',
                         'No graph, original R1 permissions, inventory, job count or zero-capacity edge change.'],
              'wall_seconds': time.perf_counter() - began}
    target.mkdir()
    (target / 'analyzer.py').write_bytes(Path(__file__).read_bytes())
    (target / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'report_sha256': sha(target / 'report.json'),
                      'counts': {k: {n: v[n] for n in ('relaxed_additional_count', 'bridge_count', 'terminal_position')} for k, v in runs.items()},
                      'wall_seconds': report['wall_seconds']}))


if __name__ == '__main__':
    main()
