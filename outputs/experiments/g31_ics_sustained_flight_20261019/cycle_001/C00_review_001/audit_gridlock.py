"""Independent saved-C00 audit; stdlib only, no controller/model/native import."""
from collections import Counter, defaultdict, deque
import gzip
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[4]
RUN = OUT.parent / 'C00_calibration_001'


def read(path):
    return json.loads(Path(path).read_bytes())


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {'path': str(path), 'sha256': digest(path)}


def write(name, value):
    with (OUT / name).open('x', encoding='utf8') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write('\n')


def main():
    plan = read(RUN / 'plan.json')
    data = read(RUN / 'inputs/C00.json')
    envelope = json.loads(gzip.decompress((RUN / 'C00/raw.json.gz').read_bytes()))
    result = envelope['final_result']
    source_path = ROOT / 'legacy/jichang_origin_readonly/inputdata.txt'
    profile_path = ROOT / 'data/processed/maps/nanning_airport_profile.json'
    profile = read(profile_path)
    crosswalk = json.loads(gzip.decompress((RUN / 'business_crosswalk.json.gz').read_bytes()))
    assert len(data['jobs']) == len(result['jobs']) == len(crosswalk) == 28506
    assert len(data['trays']) == len(result['trays']) == 22
    assert len(profile['nodes']) == len(data['node_records']) == 151
    assert len(profile['edges']) == len(data['edge_records']) == 227
    assert digest(RUN / 'inputs/C00.json') == plan['input']['sha256']
    expected_edges = {(row['start'], row['end']): row for row in profile['edges']}
    capacities = {(row['from'], row['to']): row['capacity'] for row in data['edge_contracts']}
    assert set(expected_edges) == set(capacities)
    for source, destination, length, speed in data['edge_records']:
        original = expected_edges[source, destination]
        assert (length, speed, capacities[source, destination]) == (
            original['length'], original['speed'], original['pallet_capacity'])
    adjacent, geometric = defaultdict(list), defaultdict(list)
    for source, destination, *_ in data['edge_records']:
        geometric[source].append(destination)
        if capacities[source, destination] > 0:
            adjacent[source].append(destination)

    def parents(graph, source):
        previous, queue = {source: None}, deque([source])
        while queue:
            node = queue.popleft()
            for target in graph[node]:
                if target not in previous:
                    previous[target] = node
                    queue.append(target)
        return previous

    def path(previous, target):
        if target not in previous:
            return None
        nodes = []
        while target is not None:
            nodes.append(target)
            target = previous[target]
        return nodes[::-1]

    reach = {node: parents(adjacent, node) for node in range(151)}
    geometry_reach = {node: parents(geometric, node) for node in range(151)}
    raw_rows = {}
    for line in source_path.read_text(encoding='utf8').splitlines()[1:]:
        if not line.strip():
            continue
        identity, entry, std, source, goal, unloader, loader = line.split()
        group = 'hg_' + hashlib.sha256(json.dumps([float(std), int(goal), unloader],
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()[:24]
        raw_rows[int(identity)] = {'parent_group': group, 'STD': float(std), 'original_start': int(source),
            'original_goal': int(goal), 'original_unloader': unloader}
    assert len(raw_rows) == 28506
    lineage = {row['business_bag_id']: raw_rows[row['original_task_id']] for row in crosswalk}
    offered_groups, unreachable_groups = Counter(), Counter()
    static_rows = []
    for job in data['jobs']:
        stages = [(job['origin'], job['destination'])] if job['storage_node'] < 0 else [
            (job['origin'], job['storage_node']), (job['storage_node'], job['destination'])]
        failed = [{'from': source, 'to': target, 'positive_capacity_path': path(reach[source], target),
                   'ignoring_zero_capacity_path': path(geometry_reach[source], target)}
            for source, target in stages if target not in reach[source]]
        parent = lineage[job['business_bag_id']]
        offered_groups[parent['parent_group']] += 1
        if failed:
            unreachable_groups[parent['parent_group']] += 1
            static_rows.append({'business_bag_id': job['business_bag_id'], **parent,
                'projected_origin': job['origin'], 'storage_node': job['storage_node'],
                'destination': job['destination'], 'failed_stages': failed})
    write('unreachable_jobs.json', static_rows)
    group_rows = [{'parent_group': group, 'offered_jobs': offered_groups[group], 'unreachable_jobs': count}
        for group, count in sorted(unreachable_groups.items())]
    write('unreachable_parent_groups.json', group_rows)
    occupancy = Counter(tray['node'] for tray in result['trays'] if tray['edge_to'] < 0)
    leases = Counter(tray['reception_node'] for tray in result['trays'] if tray['reception_node'] >= 0)
    waits = defaultdict(list)
    for event in result['receipts']:
        if event['event'] == 'RESOURCE_WAIT':
            waits[event['tray_id']].append(event)
    calls = json.loads(gzip.decompress((RUN / 'C00/client_calls.json.gz').read_bytes()))
    requests = {row['request']['request_id']: row['request'] for row in calls if not row['retry'] and row['kind'] == 'transfer'}
    ledger = json.loads(gzip.decompress((RUN / 'C00/request_ledger.json.gz').read_bytes()))
    acknowledgements = {row['request_id']: row['last_delivered_ack'] for row in ledger['requests'] if row['kind'] == 'transfer'}
    transfer_by_tray = defaultdict(list)
    for transfer in result['transfers']:
        transfer_by_tray[transfer['tray']].append({
            'request': requests[transfer['request_id']], 'physical_transfer': transfer,
            'last_delivered_ack': acknowledgements.get(transfer['request_id'])})
    tray_rows = []
    for index, tray in enumerate(result['trays']):
        if tray['job'] >= 0:
            spec, business = data['jobs'][tray['job']], result['jobs'][tray['job']]
            goal = spec['storage_node'] if spec['storage_node'] >= 0 and business['storage_released_at'] < 0 else spec['destination']
        else:
            spec = business = None
            goal = tray['reception_node']
        outgoing = [{'from': tray['node'], 'to': target, 'capacity': capacities[tray['node'], target],
            'target_parked_trays': occupancy[target], 'target_receiving_leases': leases[target],
            'positive_capacity_suffix_exists': goal in reach[target]}
            for target in geometric[tray['node']]]
        tray_rows.append({'tray': tray, 'business': business, 'job_contract': spec,
            'current_stage_goal': goal, 'positive_capacity_path': path(reach[tray['node']], goal),
            'last_recorded_resource_wait': waits[tray['tray_id']][-1] if waits[tray['tray_id']] else None,
            'resource_wait_absence_is_not_no_blockage': True, 'outgoing_edge_audit': outgoing,
            'transfers': transfer_by_tray[index],
            'note': 'Detailed native wait dependency/queue order absent from trace_limit=0 output; no preferred-next-edge is invented.'})
    write('tray_blockage_and_ack.json', tray_rows)
    profile_zeros = [list(edge) for edge, capacity in capacities.items() if capacity == 0]
    no_suffix = [event for event in result['receipts'] if event['event'] == 'RESOURCE_WAIT'
        and event['reason'] == 'no_static_legal_suffix']
    evidence = [RUN / 'plan.json', RUN / 'inputs/C00.json', RUN / 'C00/raw.json.gz', RUN / 'C00/acceptance.json',
        RUN / 'C00/client_calls.json.gz', RUN / 'C00/request_ledger.json.gz', profile_path, source_path,
        ROOT / 'cpp/ics_core/runtime/circulation_recovery_impl.hpp',
        ROOT / 'cpp/ics_core/runtime/circulation_runtime_impl.hpp']
    report = {'schema': 'g31.foundation.independent_airport_blockage.v1',
        'status': 'saved_raw_and_full_population_static_audit_complete', 'evidence': [ref(item) for item in evidence],
        'native_execution_in_this_audit': False, 'controller_or_model_imported': False,
        'business_count': len(data['jobs']), 'final_clock': result['physical_clock'],
        'business_status_counts': dict(Counter(job['status'] for job in result['jobs'])),
        'actual_business_completed': sum(job['completed_at'] >= 0 for job in result['jobs']),
        'native_transport_leg_completed': result['native_summary']['completed_count'],
        'last_edge_exit_at': max(event['time'] for event in result['receipts'] if event['event'] == 'EDGE_EXIT'),
        'parked_trays_by_node': dict(occupancy), 'receiving_leases_by_node': dict(leases),
        'profile_and_input_directed_geometry_capacity_exact': True, 'zero_capacity_edges': profile_zeros,
        'static_unreachable_business_count': len(static_rows), 'affected_parent_group_count': len(group_rows),
        'entirely_unreachable_parent_group_count': sum(row['offered_jobs'] == row['unreachable_jobs'] for row in group_rows),
        'unreachable_by_destination': dict(Counter(row['destination'] for row in static_rows)),
        'unreachable_by_original_start': dict(Counter(row['original_start'] for row in static_rows)),
        'unreachable_stage_patterns': dict(Counter('via_storage' if row['storage_node'] >= 0 else 'direct' for row in static_rows)),
        'native_no_static_suffix_receipts': no_suffix,
        'transfer_status_counts': dict(Counter(row['status'] for row in result['transfers'])),
        'transfer_rejection_reasons': dict(Counter(row['reason'] for row in result['transfers'] if row['status'] == 'rejected')),
        'control_contract': {'all_suffix_reroute_permissions_false': all(not row.get('allow_suffix_reroute', False) for row in data['jobs']),
            'node_berths': 4, 'storage_berths': 4, 'trays_per_loader': 2, 'fixed_FIFO': True},
        'causal_findings': [
            'At 19500 Storage53 releases jobs0,2,1,3; job0 to99 receives no_static_legal_suffix. Capacity-positive BFS independently agrees.',
            'Two Storage occupants have unreachable destination99; jobs2 to116 and3 to47 have static paths. FIFO head blocking is supported by fixed FIFO plus head-only resource receipts, not a dumped queue.',
            'Storage53 and upstream112/29/137 each hold four trays. Four departed empty trays remain in transit at137/139; ACK departed is never a received result.',
            'The physical blockage is not repaired by repeated predictive empty reservations: rejected forecast departures expire while no loaded completion has occurred.',
            'Static topology disallows 4001 complete required business paths before queueing; stronger learning cannot create a legal path under unchanged graph/capacity/destinations.'
        ],
        'unchanged_contract_recovery_boundary': [
            'Existing route commands require allow_suffix_reroute and a legal suffix to the active goal; both fail for the unreachable Storage head.',
            'R2 transfers apply to empties; loaded recovery cannot relocate these jobs, and departed empties keep their receiving obligations.',
            'Reducing duplicate forecast proposals can improve compute/message costs but cannot establish physical recovery or all-job completion.'
        ],
        'input_contract_options_for_user_or_GPT_Pro_only': [
            'Check whether source edge97->98 zero capacity denotes a true closed conveyor. Any corrected capacity needs external source evidence and a separately named common physical contract.',
            'Review the retrospective flight-to-unloader projection: a new topology-feasible projection is a different scenario, retains all original business identities, and must never replace this negative run.',
            'If unreachable jobs are real offered demand, retain them and agree on infeasibility/censoring evaluation or explicit exception staging/service semantics; those semantics require a new physical/permission contract, not invented successful completions.'
        ],
        'strict_nonharm_or_benefit_certified': False, 'no_business_jobs_deleted': True,
        'no_capacity_graph_destination_changes': True}
    write('report.json', report)
    text = f'''# C00 independent airport blockage audit

The original 28,506 jobs, 151 nodes, 227 edges and 22 trays were preserved. C00 reached 59,400 with closed native acceptance, but completed **zero business jobs**. The native summary's six completions are transport legs (four Storage entries and two empty returns), not business completions.

Physical edge motion stopped at {report['last_edge_exit_at']:.12f}. At 19,500 the Storage53 head job `projected:1x:0` attempted goal99 and native reported `no_static_legal_suffix`. The original profile and actual input agree exactly on edge geometry/direction/capacity, including closed edge97->98. Independent positive-capacity directed reachability finds **{len(static_rows)} unreachable business paths across {len(group_rows)} parent groups**; no task was removed for this analysis.

The four Storage trays hold jobs0,2,1,3. Jobs0/1 cannot reach99. Jobs2/3 have paths to116/47 but fixed FIFO places the no-route head ahead of them. Four trays occupy112 waiting toward53; four occupy29; four occupy137, including two departed empties. Two more departed empties wait139. Actual receiving leases remain at0/24/26/49. Full per-tray contracts, outgoing alternatives, last resource receipts and immutable delivered ACKs are in `tray_blockage_and_ack.json`. Trace-limit zero means this audit does not claim an exact native dependency queue dump or invent a selected edge.

Changing empty reserve or learned priority cannot supply a missing legal path. Loaded reroute permission is false in this input, and the native route gate also rejects any suffix that cannot reach the active goal. No C01/C11 gain claim is supported. Suppressing pointless forecast retries could reduce overhead, but would not establish physical recovery.

Contract decisions requiring separate review: verify the meaning of the zero-capacity edge against source evidence; review whether the retrospective projection assigned unreachable unloaders; or explicitly define treatment/staging of infeasible offered jobs. Any repaired capacity, destination projection, FIFO/exception handling or service semantics is a new common physical contract and must retain this run as a negative result. It is not same-scenario algorithmic improvement.
'''
    with (OUT / 'report.md').open('x', encoding='utf8') as stream:
        stream.write(text)
    print(json.dumps({key: report[key] for key in ('status', 'business_count', 'actual_business_completed',
        'static_unreachable_business_count', 'affected_parent_group_count', 'entirely_unreachable_parent_group_count')}))


if __name__ == '__main__':
    main()
