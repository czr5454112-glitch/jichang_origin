"""Reconstruct parked occupancy from actual initial trays and ordered edges.

This is offline diagnosis, not policy input or a receiver-reservation oracle.
In-flight occupancy/leases and hidden junction queues are not inferred.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path


def audit(data, result, critical=(28, 29, 53, 112)):
    nodes = {n['node']: n for n in data['node_contracts']}
    positions = {t['tray_id']: {'node': t['node'], 'edge': None, 'job': '', 'stage': ''} for t in data['trays']}
    if len(positions) != len(data['trays']): raise ValueError('duplicate_initial_tray')
    parked = defaultdict(set)
    for tray, position in positions.items(): parked[position['node']].add(tray)
    history = {str(node): [] for node in critical}
    def capture(node, time, event, moving):
        if node not in critical: return
        capacity = nodes[node]['capacity']
        if len(parked[node]) > capacity: raise ValueError('parked_capacity_exceeded')
        history[str(node)].append({'time': time, 'event': event, 'moving_tray': moving,
            'count': len(parked[node]), 'capacity': capacity,
            'occupants': [{'tray_id': t, 'business_bag_id': positions[t]['job'], 'stage': positions[t]['stage']}
                for t in sorted(parked[node])]})
    for node in critical: capture(node, 0., 'INITIAL', '')
    previous, enters, exits = 0., 0, 0
    for row in result['receipts']:
        now, event = row['time'], row['event']
        if now < previous: raise ValueError('nonmonotone_receipt_order')
        previous = now
        tray = row.get('tray_id')
        if event not in {'LOAD_START', 'LEG_START', 'EDGE_ENTER', 'EDGE_EXIT', 'UNLOAD_COMPLETE'}: continue
        if tray not in positions: raise ValueError('unknown_receipt_tray')
        position = positions[tray]
        if event == 'LOAD_START': position['job'] = row['business_bag_id']
        elif event == 'LEG_START':
            position['job'], position['stage'] = row['business_bag_id'], row['reason']
        elif event == 'UNLOAD_COMPLETE': position['job'], position['stage'] = '', ''
        elif event == 'EDGE_ENTER':
            source, target = row['from'], row['to']
            if position['edge'] is not None or position['node'] != source or tray not in parked[source]:
                raise ValueError('edge_enter_not_at_observed_source')
            parked[source].remove(tray); position['edge'] = (source, target)
            enters += 1; capture(source, now, event, tray)
        elif event == 'EDGE_EXIT':
            source, target = row['from'], row['to']
            if position['edge'] != (source, target): raise ValueError('edge_exit_without_matching_entry')
            position['edge'], position['node'] = None, target
            parked[target].add(tray); exits += 1; capture(target, now, event, tray)
    final = {t['tray_id']: t for t in result['trays']}
    if final.keys() != positions.keys(): raise ValueError('final_tray_denominator_changed')
    for tray, position in positions.items():
        edge = None if final[tray]['edge_to'] < 0 else (final[tray]['edge_from'], final[tray]['edge_to'])
        if edge != position['edge'] or final[tray]['node'] != position['node']:
            raise ValueError('final_native_positions_do_not_match_receipt_reconstruction')
    summaries = {}
    for node, rows in history.items():
        full = [r for r in rows if r['count'] == r['capacity']]
        last_nonfull = max((i for i, r in enumerate(rows) if r['count'] < r['capacity']), default=-1)
        summaries[node] = {'first_parked_full_at': full[0]['time'] if full else None,
            'final_parked_full_since': rows[last_nonfull + 1]['time'] if rows[-1]['count'] == rows[-1]['capacity'] else None,
            'final_count': rows[-1]['count'], 'capacity': rows[-1]['capacity'], 'transition_count': len(rows)}
    return {'status': 'exact_parked_receipt_reconstruction', 'tray_count': len(positions),
        'edge_enters': enters, 'edge_exits': exits, 'critical_summaries': summaries, 'critical_history': history,
        'scope': 'All recorded movement pairs replayed in exact original order; every final tray position matches native result.',
        'limitations': ['Parked occupancy only: in-flight reception reservations can exhaust capacity earlier.',
            'No hidden FIFO head/committed next-hop or owner knowledge inferred.',
            'Intermediate occupancy changes do not certify complete business protection.']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    paths = {name: args.campaign / (name + '.json.gz') for name in ('input', 'control', 'candidate')}
    data = json.load(gzip.open(paths['input'], 'rt', encoding='utf-8'))
    report = {'schema': 'g31.original_parked_occupancy_audit.v1', 'source_sha256': {str(p): sha(p) for p in paths.values()},
        'script_sha256': sha(Path(__file__)), 'new_native_executions': 0, 'arms': {}}
    for name in ('control', 'candidate'):
        result = json.load(gzip.open(paths[name], 'rt', encoding='utf-8'))['result']
        try: report['arms'][name] = audit(data, result)
        except Exception as error: report['arms'][name] = {'status': 'unknown_incomplete_or_inconsistent_receipts', 'error': str(error)}
    with args.output.open('x', encoding='utf-8') as out: json.dump(report, out, indent=2, allow_nan=False)
    print(json.dumps({name: {k: row[k] for k in row if k not in ('critical_history', 'scope', 'limitations')}
        for name, row in report['arms'].items()}, indent=2))


if __name__ == '__main__': main()
