"""Read only final shard/input/offline export; no native or prior-shard scan."""
from collections import Counter, defaultdict, deque
import gzip
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / 'outputs/experiments/g31_ics_lt2_sustained_20261014'
SOURCE = OUT / 'full024_chained_2x_20261015_002'
OUTPUT = OUT / 'full2x_endpoint_diagnostic_002'
EXPECTED_RAW = '3e5e9214697ab3973a15837c124d341b5d82e5ad9877a6a51cf398cbd241b137'
EXPECTED_INPUT = 'f409d6ce906d6aa225f71b9f8a80dc30d458fe598716c41ebe399b95239c2e6d'
EXPECTED_SEAL = 'a3421e8622df91d31e014333ec016c33a0845827e541d2f3e3d034e9da1e2826'
pins = {}
def load(path, expected=None):
    path = Path(path); before = path.stat(); data = path.read_bytes(); after = path.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    digest = hashlib.sha256(data).hexdigest()
    if expected is not None: assert digest == expected, str(path)
    pins[str(path)] = {'sha256': digest, 'size': len(data), 'mtime_ns': after.st_mtime_ns}
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)

def bfs(source, goal, adjacency):
    parent = {source: None}; queue = deque([source])
    while queue:
        node = queue.popleft()
        for target in adjacency.get(node, []):
            if target not in parent: parent[target] = node; queue.append(target)
    path = None
    if goal in parent:
        path = [goal]
        while parent[path[-1]] is not None: path.append(parent[path[-1]])
        path.reverse()
    return path, sorted(parent)

began = time.perf_counter()
assert not OUTPUT.exists()
sidecar = load(SOURCE / 'segment_hashes/0525.json')
assert sidecar == {'path': 'segments\\0525.json.gz', 'sha256': EXPECTED_RAW}
manifest = load(SOURCE / 'run_shards.json')
assert manifest['final_state_shard'] == sidecar['path'] and manifest['shards'][-1]['sha256'] == EXPECTED_RAW
part = load(SOURCE / sidecar['path'], EXPECTED_RAW)
data = load(SOURCE / 'input.json.gz', EXPECTED_INPUT)
input_manifest = load(SOURCE / 'input_manifest.json')
canonical_input_digest = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
diagnostic = load(SOURCE / 'native_offline_diagnostics.json.gz', '5d6e24c9a5a793bec1119d83caf01ce5d60267d1190160c863c3e4ddd1ac2c4b')
receipt = load(SOURCE / 'receipt.json')
heartbeat = load(SOURCE / 'heartbeat.json')
prior_audit = load(OUT / 'full024_chained_2x_20261015_002_saved_audit_001.json')
assert prior_audit['status'] == 'passed_saved_physical_horizon'
assert canonical_input_digest == prior_audit['input_provenance']['reconstructed_offered_input_sha256']
for name in ('receipt.json', 'run_shards.json', 'input.json.gz', 'input_manifest.json'):
    assert pins[str(SOURCE/name)]['sha256'] == prior_audit['evidence_sha256'][name]
result = part['result']; horizon = result['physical_clock']
assert part['status'] == 'reached' and horizon == result['horizon'] == diagnostic['now'] == 86400
assert part['native_state_sha256'] == heartbeat['latest_native_seal']['native_state_sha256'] == prior_audit['native_state_sha256'] == EXPECTED_SEAL
assert len(data['jobs']) == len(result['jobs']) == 57012 and len(data['trays']) == len(result['trays']) == 22
assert [x['business_bag_id'] for x in data['jobs']] == [x['business_bag_id'] for x in result['jobs']]
assert [x['tray_id'] for x in data['trays']] == [x['tray_id'] for x in result['trays']]
assert result['native_events'] == result['transport_legs'] == []
node_contracts = {n['node']: n for n in data['node_contracts']}
edge_contracts = {(e['from'], e['to']): e for e in data['edge_contracts']}
adjacency = defaultdict(list); all_edges = defaultdict(list)
for u,v,*_ in data['edge_records']:
    capacity = edge_contracts[(u,v)]['capacity']
    assert type(capacity) is int and capacity >= 0
    all_edges[u].append(v)
    if capacity > 0: adjacency[u].append(v)
assert len(edge_contracts) == len(data['edge_records'])
legs = {x['runtime_id']: x for x in diagnostic['legs']}
assert [{**{k:v for k,v in row.items() if k not in ('tray','job')},
         'tray_index': row['tray'], 'job_index': row['job']} for row in result['leg_identities']] == diagnostic['legs']
by_tray = {x['tray_id']: x for x in diagnostic['trays']}
junctions = {x['node']: x for x in diagnostic['junctions']}
waits = {x['runtime_id']: x for x in diagnostic['resource_waits']}
occupants = defaultdict(list); reception = defaultdict(list)
starts = {}; latest_receipt = {}; last_wait_receipt = {}
for row in result['receipts']:
    if row['tray_id']: latest_receipt[row['tray_id']] = row
    if row['event'] == 'LEG_START': starts[row['transport_leg_id']] = row
    if row['event'] == 'RESOURCE_WAIT': last_wait_receipt[row['transport_leg_id']] = row
rows = []
for index, tray in enumerate(result['trays']):
    d = by_tray[tray['tray_id']]
    for key in ('node','mode','active_leg','edge_from','edge_to','reception_node'):
        assert tray[key] == d[key]
    assert tray['job'] == d['job_index'] and tray['edge_from'] == tray['edge_to'] == -1
    occupants[tray['node']].append(tray['tray_id'])
    if tray['reception_node'] >= 0: reception[tray['reception_node']].append(tray['tray_id'])
    leg = legs[tray['active_leg']]; assert leg['tray_index'] == index and leg['job_index'] == tray['job']
    start = starts[leg['transport_leg_id']]
    assert start['tray_id'] == tray['tray_id'] and start['reason'] == leg['kind']
    job = data['jobs'][tray['job']] if tray['job'] >= 0 else None
    goal = (job['storage_node'] if leg['kind'] == 'storage_in' else job['destination']) if job else tray['reception_node']
    assert start['to'] == goal
    path, reachable = bfs(tray['node'], goal, adjacency)
    rawpath, _ = bfs(tray['node'], goal, all_edges)
    frontier = [{'from': u, 'to': v, 'capacity': edge_contracts[(u,v)]['capacity']}
        for u in reachable for v in all_edges.get(u, []) if v not in reachable]
    if path is None: assert all(x['capacity'] == 0 for x in frontier)
    queue = junctions[tray['node']]['queue']; position = queue.index(tray['active_leg'])
    head = legs[queue[0]]
    rows.append({'tray_index': index, **tray, 'business_bag_id': None if job is None else job['business_bag_id'],
        'job_contract': job, 'job_result': None if job is None else result['jobs'][tray['job']],
        'leg': leg, 'current_leg_goal': goal, 'leg_start_receipt': start,
        'latest_tray_receipt': latest_receipt[tray['tray_id']],
        'last_resource_wait_receipt': last_wait_receipt.get(leg['transport_leg_id']),
        'queue_position': position, 'queue_head_leg': head,
        'head_wait': waits.get(queue[0]), 'capacity_positive_path': path,
        'unconstrained_topological_path': rawpath, 'positive_reachable_nodes': reachable if path is None else None,
        'closed_outgoing_cut': frontier if path is None else None,
        'selected_current_route': 'unknown: trace_limit0 omits transport-leg route bodies; goal and current wait subscriptions are retained'})
queued = [leg for q in junctions.values() for leg in q['queue']]
assert sorted(queued) == sorted(x['active_leg'] for x in result['trays']) and len(queued) == len(set(queued))
resources = []
for node in sorted(set(occupants) | set(reception)):
    contract = node_contracts[node]; incoming = junctions.get(node, {}).get('scheduled_incoming', 0)
    count = len(occupants[node]) + len(reception[node]) + incoming
    assert count <= contract['capacity']
    resources.append({'node': node, 'capacity': contract['capacity'], 'parked_trays': occupants[node],
        'incoming_count': incoming, 'reception_reservations': reception[node], 'total_occupancy': count,
        'queue': junctions.get(node, {}).get('queue', []),
        'next_dispatch_time': junctions.get(node, {}).get('next_dispatch_time'), 'resource_owner': contract['resource_owner']})
dependencies = []
for wait in diagnostic['resource_waits']:
    queue = junctions[wait['node']]['queue']; assert queue[0] == wait['runtime_id']
    for receiver in wait['receiving_nodes']:
        capacity = node_contracts[receiver]['capacity']
        occupied = len(occupants[receiver]) + len(reception[receiver]) + junctions.get(receiver, {}).get('scheduled_incoming', 0)
        dependencies.append({'from': wait['node'], 'to': receiver, 'head_leg': wait['runtime_id'],
            'receiver_occupancy': occupied, 'capacity': capacity, 'receiver_full': occupied >= capacity,
            'scope': 'actual current receiving subscription, not proof every alternative route is blocked'})
dependency_adj = defaultdict(list)
for d in dependencies: dependency_adj[d['from']].append(d['to'])
def cycle(node, active, done):
    if node in active: return True
    if node in done: return False
    active.add(node)
    result = any(cycle(x,active,done) for x in dependency_adj.get(node,[]))
    active.remove(node); done.add(node); return result
has_cycle = any(cycle(x,set(),set()) for x in list(dependency_adj))
assert not has_cycle
assert {x['business_bag_id'] for x in rows if x['capacity_positive_path'] is None} == {'projected:2x:0','projected:2x:28506','projected:2x:1'}
reachable_storage = next(x for x in rows if x['business_bag_id'] == 'projected:2x:2')
assert reachable_storage['current_leg_goal'] == 116 and reachable_storage['capacity_positive_path'] is not None and reachable_storage['queue_position'] == 1
assert junctions[53]['queue'] == [28,29,30,31] and waits[28]['static_blocked'] is True
assert all(x['job_result']['storage_released_at'] <= horizon for x in rows if x['node'] == 53)
assert result['advance']['horizon_complete'] is True
assert result['native_summary']['completed_count'] == sum(x['event'] == 'LEG_COMPLETE' for x in result['receipts']) == 10
summary = {
    'schema': 'g31.full2x.endpoint_saved_diagnostic.v1', 'status': 'completed_narrow_saved_endpoint_diagnostic',
    'producer_status_unchanged': receipt['status'], 'horizon': horizon, 'final_native_seal_field': EXPECTED_SEAL,
    'native_seal_replayed_here': False, 'all_shards_replayed_here': False, 'native_executions': 0,
    'read_scope': 'One final raw shard0525, original input, small saved offline diagnostics and manifest/audit metadata. No intermediate raw shard or NativeSession.',
    'offered': len(result['jobs']), 'completed_business_jobs': sum(x['completed_at'] >= 0 for x in result['jobs']),
    'input_binding': {'saved_input_canonical_sha256': canonical_input_digest,
        'raw_workload_manifest_input_sha256': input_manifest['input_sha256'],
        'distinction': 'Manifest digest precedes profile runtime options. Saved input is pinned as bytes and to the prior full audit reconstructed configured input digest, not falsely equated to the manifest raw-workload digest.'},
    'business_status_counts': dict(Counter(x['status'] for x in result['jobs'])),
    'tray_modes': dict(Counter(x['mode'] for x in result['trays'])), 'active_edges': 0,
    'native_completed_count_transport_legs': result['native_summary']['completed_count'],
    'leg_complete_receipts': sum(x['event'] == 'LEG_COMPLETE' for x in result['receipts']),
    'prior_full_saved_audit': {k: prior_audit[k] for k in ('status','physical_audit','producer_process_success','completed','unfinished')},
    'static_unreachable_current_legs': [x['leg']['runtime_id'] for x in rows if x['capacity_positive_path'] is None],
    'trays': rows, 'resources': resources, 'current_waits': diagnostic['resource_waits'],
    'receiving_dependencies': dependencies, 'current_receiving_dependency_cycle_found': has_cycle,
    'deadlock_certified': False,
    'findings': [
        'All22 trays have active legs but none is currently on an edge;17 loaded and5 empty_transit. Business completed count is0; native completed_count10 counts transport legs.',
        'Four storage_out trays at53 carry business IDs projected:2x:0, projected:2x:28506, projected:2x:1 and projected:2x:2 (job indices0,1,2,3). The first three listed business IDs target99 and lack a positive-capacity path, with closed cut97->98 capacity0. Business2 targets116, has a positive-capacity path, and is second in FIFO behind blocked business0. All four releases are already past.',
        'Current head subscription chain is28->29->112->53,136->137->112,139->112 and150->112. All named receiving resources are currently full. This receiving graph is acyclic; it is not a demonstrated capacity-ring deadlock.',
        'Offline53 FIFO queue is[28,29,30,31], headed by leg28 business0 with static_blocked=true. All22 legs belong to eight source queues;14 non-head legs are behind their respective head. Ranking subscriptions are alternative/reevaluation triggers, not an AND dependency certificate.',
        'No idle empty tray remains at any loader. Empty_transit trays have outstanding physical legs and reserved reception destinations; they are not newly available supply.',
        'A hypothetical authorized112->113 diversion has a positive-capacity static path toward53 but does not remove three statically undeliverable99 obligations at53. Acceptance/FIFO/shield and business gain require actual separate evidence; no route change is executed here.'
    ],
    'unknowns': [
        'No full future event heap is exported. Complete H timestamp plus past visible service/release times does not certify absence of every future wake or protocol action.',
        'Selected route suffixes, arbitration candidate scores and hypothetical alternative admission are not in trace_limit0 export; no reconstruction or inference of them is used.',
        'Offline global data are diagnostic only and must not enter owner online policy.',
        'Full saved-horizon audit is referenced and hash-bound, not rerun by this narrow report. Original worker remains hard_timeout.'
    ],
    'source_script': {'path': str(Path(__file__)), 'sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
    'evidence': pins, 'analysis_wall_seconds': time.perf_counter() - began,
}
for path, record in pins.items():
    stat = Path(path).stat(); assert (stat.st_size, stat.st_mtime_ns) == (record['size'],record['mtime_ns'])
OUTPUT.mkdir()
(OUTPUT/'report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'report': str(OUTPUT/'report.json'), 'sha256': hashlib.sha256((OUTPUT/'report.json').read_bytes()).hexdigest(),
    'tray_modes': summary['tray_modes'], 'static_unreachable_legs': summary['static_unreachable_current_legs'], 'receiving_dependencies': dependencies}))
