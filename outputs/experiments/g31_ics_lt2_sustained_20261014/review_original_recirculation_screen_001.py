"""Independent saved-data screen check; no native or predictive simulation."""
from collections import Counter
from pathlib import Path
import gzip, hashlib, json, time

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
EXPECTED = '8a67822c5db2d749258e9109ce48e75971f49c065f51713679169355fabc7a1c'
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
    p = Path(p); value = p.read_bytes()
    return json.loads(gzip.decompress(value) if p.suffix == '.gz' else value)
def require(ok, why):
    if not ok: raise ValueError(why)

def main():
    began = time.perf_counter(); pins = {}
    def pin(path, expected=None):
        got = sha(path); require(expected is None or got == expected, 'hash:' + str(path))
        pins[str(path)] = got
    path = OUT / 'original_recirculation_screen_001/report.json'; pin(path, EXPECTED); report = read(path)
    source = ROOT / 'scripts/experiments/g31_ics_circulation/audit_original_recirculation_screen.py'
    pin(source, report['source_sha256']); pin(path.parent / 'analyzer.py', report['source_sha256'])
    for name, digest in report['evidence_sha256'].items(): pin(OUT / name, digest)
    case = OUT / 'original_low_wip_cap_relay_prepare_001/cap8'
    data, raw, plan = (read(case / p) for p in ('input.json.gz', 'raw_final.json.gz', 'preregistered_protocol.json'))
    outcomes = read(case / 'all_job_states.json.gz'); bound = read(OUT / 'original_carrier_bound_002/analysis.json.gz')
    nodes = {n['node']: n for n in data['node_contracts']}; roles = {n[0]: n[1] for n in data['node_records']}
    edge_caps = {(e['from'], e['to']): e['capacity'] for e in data['edge_contracts']}
    positive = {(a, b) for a, b, length, speed in data['edge_records']
                if length > 0 and speed > 0 and edge_caps[a, b] > 0 and nodes[a]['capacity'] > 0 and nodes[b]['capacity'] > 0}
    reach = {a: {a} | {b for x, b in positive if x == a} for a in nodes}
    for k in nodes:
        for a in nodes:
            if k in reach[a]: reach[a] |= reach[k]
    jobs = {j['business_bag_id']: j for j in data['jobs']}
    completed = {j['business_bag_id'] for j in outcomes['jobs'] if j['status'] == 'completed'}
    prefixes = {r['origin']: [j['business_bag_id'] for j in r['jobs_in_native_fifo_order']
                              if j['unreachable_through_prefix'] == 0] for r in bound['loaders']}
    require(len(jobs) == 28506 and len(completed) == 8 and sum(map(len, prefixes.values())) == 39, 'denominators')
    token = plan['parking_plan']['token_tray_id']; final = {t['tray_id']: t for t in raw['result']['trays']}
    require(len(final) == len(data['trays']) == 22, 'tray identities')
    parked = Counter()
    for p in plan['parking_plan']['parking']:
        if p['tray_id'] == token: continue
        t = final[p['tray_id']]
        require(t['node'] == p['destination'] and t['mode'] == 'empty'
                and t['job'] == t['edge_to'] == t['reception_node'] == -1
                and t['available_at'] <= raw['physical_time'], 'actual parked stock differs')
        parked[t['node']] += 1
    require(sum(parked.values()) == 21, '21 parked after token released')
    require(final[token]['mode'] == 'empty' and final[token]['job'] == final[token]['edge_to'] == final[token]['reception_node'] == -1, 'actual token empty')
    def eligible(a, b):
        x, y = nodes[a], nodes[b]
        return a != b and x['zone'] != y['zone'] and x['allow_export'] and y['allow_receive'] and parked[a] + 1 > x['export_min_stock'] and parked[b] < y['capacity'] and b in reach[a]
    def path_ok(path, a, b):
        require(path[0] == a and path[-1] == b and all((x, y) in positive for x, y in zip(path, path[1:])), 'positive path')
    counts = {}
    for mode, value in report['cases'].items():
        remaining = {o: [j for j in ids if j not in completed] for o, ids in prefixes.items()}
        position = final[token]['node']; bridges = 0
        for row in value['trace']:
            choices = []
            for o, ids in remaining.items():
                if not ids: continue
                route = [position, o] if eligible(position, o) else None
                if route is None and mode == 'direct_then_one_bridge':
                    options = [n for n in nodes if roles[n] not in (1, 7) and eligible(position, n) and eligible(n, o)]
                    if options: route = [position, min(options), o]
                if route: choices.append((jobs[ids[0]]['arrival'], ids[0], o, route))
            require(bool(choices), 'reported step without eligible head')
            _, job_id, origin, route = min(choices); job = jobs[job_id]
            require((row['job'], row['from'], row['origin'], row['destination'], row['empty_transfer_endpoints'])
                    == (job_id, position, origin, job['destination'], route), 'greedy head/route identity')
            require(len(row['positive_empty_paths']) == len(route)-1, 'empty path denominator')
            for p, (a, b) in zip(row['positive_empty_paths'], zip(route, route[1:])): path_ok(p, a, b)
            require(len(row['positive_mandatory_paths']) == 2, 'mandatory denominator')
            path_ok(row['positive_mandatory_paths'][0], origin, job['storage_node'])
            path_ok(row['positive_mandatory_paths'][1], job['storage_node'], job['destination'])
            remaining[origin].pop(0); position = job['destination']; bridges += len(route) == 3
        require(value['relaxed_additional_count'] == len(value['trace']) and value['bridge_count'] == bridges
                and value['actual8_plus_relaxed_count'] == 8+len(value['trace']) and value['terminal_position'] == position
                and value['remaining_heads'] == {str(o): ids[0] for o, ids in remaining.items() if ids}, 'reported totals')
        counts[mode] = {'additional': len(value['trace']), 'bridges': bridges, 'final_node': position}
    require(counts == {'direct_only': {'additional': 6, 'bridges': 0, 'final_node': 85},
                       'direct_then_one_bridge': {'additional': 31, 'bridges': 12, 'final_node': 17}}, 'fixed result')
    pin(__file__)
    result = {'status': 'independent_offline_relaxation_checked', 'evidence_sha256': pins, 'counts': counts,
        'actual_parked_empty_trays_checked': 21, 'actual_token_tray_id': token, 'offered': 28506, 'total_tray_identities': 22,
        'native_calls': 0, 'projection_calls': 0, 'online_achievability_certified': False,
        'authority_review': {
            'existing_v2_limit': 'Submitted action rows authenticate source, opaque request ID and delivered ACK status; they do not bind a remote request payload to tray or destination. Terminal receipts contain UNLOAD_COMPLETE, not EMPTY_RECEIVED.',
            'conditional_bridge_permit': 'A separately declared cooperative two-owner, one-circulating-token policy may use fresh current owner-local exact-token empty possession plus own delivered capture and fresh all-received action-set barrier. This is a current-possession permit, not an authenticated EMPTY_RECEIVED causal receipt.',
            'required_guards': [
                'All non-token trays remain parked; every post-parking physical submission is restricted by both cooperating source policies to the designated token; no third-party action or unsubmitted future plan is certified by the snapshot.',
                'At most one outstanding immutable transfer globally under the cooperative policy; actual local token ownership, no job, no active edge/reception, and availability at current time are revalidated before each source submission.',
                'Latest own native selfcopy must contain that local token state; latest peer capture is no older than the current invitation and has complete source action coverage with actually delivered received ACKs.',
                'Consume an exact monotone action-ID-set watermark before submission, including rejected attempts; require set inclusion plus a genuinely new action identity after the previous permit. Counts or duplicate ACK revisions alone cannot advance it.',
                'Restore preserves consumed watermarks and immutable outboxes; absent, rejected, expired, nonmonotone, stale or unknown action facts stop new supply and retain unknown evidence.',
                'Every bridge arrival starts a new owner-local decision using delivered current FIFO facts; no opaque-ID payload parsing, offline future-head input, or preauthorized second leg.'
            ],
            'when_native_extension_needed': 'A claim that a particular remote ACK caused the exact token arrival at the exact bridge requires genuine native payload-bound EMPTY_RECEIVED/arrival evidence. Existing v2 rows alone cannot establish that claim.'},
        'limits': ['Positive static paths and endpoint stock/permissions do not prove native chosen paths, dynamic reservations, timing, completion, protection, optimality or realization of 39.',
                   'All future zero-bad-prefix heads were revealed offline. This is not lawful online selection data.',
                   'Current cap8 run is terminal. Any bridge trial must be fresh and separately declared; this check does not resume it.'],
        'wall_seconds': time.perf_counter()-began}
    target = OUT / 'original_recirculation_screen_001_independent_review.json'
    with target.open('x', encoding='utf8') as f: json.dump(result, f, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps({'status': result['status'], 'sha256': sha(target), 'counts': counts, 'wall_seconds': result['wall_seconds']}))
if __name__ == '__main__': main()
