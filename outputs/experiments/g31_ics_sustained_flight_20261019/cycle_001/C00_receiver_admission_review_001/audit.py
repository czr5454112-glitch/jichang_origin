"""Independent closed-evidence inspection; standard library only, no native execution."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE.parent / 'C00_receiver_admission_001'
PRIOR = HERE.parent / 'C00_cyclic_od_001'
BRANCH = RUN / 'C00'


def load(path):
    if str(path).endswith('.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')


def counted_at(trays, node):
    return [t['tray_id'] for t in trays
            if (t['edge_to'] < 0 and t['node'] == node)
            or t['edge_to'] == node or t['reception_node'] == node]


def main():
    plan, receipt = load(RUN / 'plan.json'), load(RUN / 'receipt.json')
    worker, acceptance = load(BRANCH / 'worker_report.json'), load(BRANCH / 'acceptance.json')
    assert receipt['status'] == worker['status'] == 'native_event_budget_censored'
    assert receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
    assert acceptance['status'] == 'closed_run_acceptance_passed' and not acceptance['invalid']
    assert sha(RUN / 'plan.json') == receipt['plan_sha256_at_launch']
    assert sha(BRANCH / 'raw.json.gz') == worker['raw']['sha256']
    assert sha(BRANCH / 'acceptance.json') == worker['acceptance']['sha256']
    assert sha(RUN / 'inputs/C00.json') == plan['input_file_sha256']['C00']
    archive_bad = [p for p, a in plan['source_archive'].items() if sha(RUN / a) != plan['source_sha256'][p]]
    evidence_bad = [p for p, h in acceptance['evidence_sha256'].items() if sha(p) != h]
    assert not archive_bad and not evidence_bad
    raw, inputs = load(BRANCH / 'raw.json.gz'), load(RUN / 'inputs/C00.json')
    prior_input = load(PRIOR / 'inputs/C00.json')
    final = raw['final_result']
    snapshot_time = final['physical_clock']
    # The wrapper intentionally retains the last complete result; a censored
    # advance has result=None. Never relabel this as the actual stop state.
    assert snapshot_time == 28800 and raw['final_physical_time'] == 31922.567000000006
    prior_final = load(PRIOR / 'C00/segment_08.json.gz')['result']
    assert prior_final['physical_clock'] == snapshot_time
    assert len(final['jobs']) == len(inputs['jobs']) == len(prior_input['jobs']) == 28506
    assert len(final['trays']) == len(inputs['trays']) == 22
    assert raw['session_instance_count'] == 1 and raw['physical_reset_count'] == 0
    assert raw['warmup_native_state_sha256'] is None
    assert inputs['jobs'] == prior_input['jobs'] and inputs['trays'] == prior_input['trays']
    changes = [(a['node'], a, b) for a, b in zip(prior_input['node_contracts'], inputs['node_contracts']) if a != b]
    assert len(changes) == 1 and changes[0][0] == 49
    assert changes[0][2] == {**changes[0][1], 'empty_receive_transit_reserve': 1}
    assert {**inputs, 'node_contracts': prior_input['node_contracts']} == prior_input
    events = final['receipts']
    by_event, by_tray = collections.defaultdict(list), collections.defaultdict(list)
    for e in events:
        by_event[e['event']].append(e)
        if e['tray_id']:
            by_tray[e['tray_id']].append(e)
    assert len(by_event['UNLOAD_COMPLETE']) == final['population']['completed']

    # Replay the physical occupancy ingredients from real event receipts and
    # verify them against the independently exported final native state.
    replay = {t['tray_id']: dict(t, edge_to=-1, reception_node=-1) for t in inputs['trays']}
    occupancy49_history, policy_rejections = [], []
    for e in events:
        t = replay.get(e['tray_id'])
        if t is None:
            continue
        if e['event'] == 'EDGE_ENTER':
            t['edge_to'] = e['to']
        elif e['event'] == 'EDGE_EXIT':
            t['node'], t['edge_to'] = e['to'], -1
        elif e['event'] == 'EXPORT_GRANTED':
            before = counted_at(replay.values(), e['to'])
            if e['to'] == 49:
                assert len([x for x in before if x != e['tray_id']]) < 3
            t['reception_node'] = e['to']
        elif e['event'] in ('EMPTY_RECEIVED', 'UNUSED_RECEIVING_RELEASED'):
            t['reception_node'] = -1
        if e['event'] == 'TRANSFER_REJECTED' and e['reason'] == 'receiver_transit_reserve':
            policy_rejections.append(e)
        if e['event'] in ('EDGE_ENTER', 'EDGE_EXIT', 'EXPORT_GRANTED', 'EMPTY_RECEIVED', 'UNUSED_RECEIVING_RELEASED'):
            occupancy49_history.append({'time': e['time'], 'event': e['event'], 'tray_id': e['tray_id'],
                'counted': counted_at(replay.values(), 49),
                'remote_leases': [x['tray_id'] for x in replay.values() if x['reception_node'] == 49],
                'physical': [x['tray_id'] for x in replay.values() if x['node'] == 49 and x['edge_to'] < 0]})
    assert all(all(replay[t['tray_id']][k] == t[k] for k in ('node', 'edge_to', 'reception_node')) for t in final['trays'])
    contracts = {r['node']: r for r in inputs['node_contracts']}
    occupied_nodes = {t['node'] for t in final['trays']} | {t['reception_node'] for t in final['trays']}
    nodes = {str(n): {'capacity': contracts[n]['capacity'], 'counted': counted_at(final['trays'], n),
        'physical': [t['tray_id'] for t in final['trays'] if t['node'] == n and t['edge_to'] < 0],
        'receiving_leases': [t['tray_id'] for t in final['trays'] if t['reception_node'] == n],
        'outgoing_edges': [r for r in inputs['edge_records'] if r[0] == n]}
        for n in sorted(occupied_nodes | {49, 53}) if n >= 0}
    details = []
    for t in final['trays']:
        history = by_tray[t['tray_id']]
        details.append({'tray': t, 'active_leg': next((l for l in final['leg_identities'] if l['runtime_id'] == t['active_leg']), None),
            'business_contract': inputs['jobs'][t['job']] if t['job'] >= 0 else None,
            'latest_queue_evidence': next((e for e in reversed(history) if e['event'] in ('EDGE_EXIT', 'LEG_START')), None),
            'latest_wait': next((e for e in reversed(history) if e['event'] == 'RESOURCE_WAIT'), None), 'last_events': history[-10:]})
    calls, views = load(BRANCH / 'client_calls.json.gz'), load(BRANCH / 'delivered_ack_views.json.gz')
    failures = []
    for transfer in final['transfers']:
        if transfer['status'] != 'failed':
            continue
        identity = transfer['request_id']
        actual_calls = [c for c in calls if c['request']['request_id'] == identity]
        payloads = {json.dumps(c['request'], sort_keys=True) for c in actual_calls}
        assert len(payloads) == 1
        failures.append({'native_transfer': transfer, 'immutable_calls': actual_calls,
            'received_ack_history': {owner: [a for a in v['delivered_transfer_acks'] if a['request_id'] == identity] for owner, v in views.items()}})

    observation_receipt = load(BRANCH / 'policy_observation_receipt.json')
    assert sha(BRANCH / 'policy_observations.jsonl.gz') == observation_receipt['artifact']['sha256']
    obs_counts, gate_counts, gate_rows = collections.Counter(), collections.Counter(), []
    obs_times, obs_owners = [], set()
    with gzip.open(BRANCH / 'policy_observations.jsonl.gz', 'rt', encoding='utf-8') as f:
        for sequence, line in enumerate(f):
            row = json.loads(line); obs, decision = row['observation'], row['decision']
            assert row['sequence'] == sequence and row['now'] == obs['now'] == decision['now']
            assert row['owner_id'] == obs['owner_id'] and row['readonly']
            assert row['candidate_conditional_labels'] is None and not row['native_execution_authority']
            assert all(contracts[t['node']]['resource_owner'] == row['owner_id'] for t in obs['trays'])
            assert obs['transfers'] == obs['client_transfer_ledger']
            assert all(x['issued_at'] <= row['now'] for x in obs['transfers'])
            assert all(x.get('delivered_at', row['now']) <= row['now'] for x in obs['delivered_messages'])
            obs_times.append(row['now']); obs_owners.add(row['owner_id'])
            available = sum(s['ledger'] == 'actual_available' for s in decision['supplies'])
            obs_counts[(row['owner_id'], available, len(decision['intents']))] += 1
            if row['now'] >= plan['planner_activate_at']:
                gate = 'baseline_intents_returned' if decision['intents'] else 'no_actual_available_supply' if not available else 'forecast_would_be_called'
                gate_counts[gate] += 1
                gate_rows.append({'sequence': sequence, 'now': row['now'], 'owner': row['owner_id'], 'actual_available': available,
                    'intent_count': len(decision['intents']), 'gate': gate})
    assert len(obs_times) == observation_receipt['record_count']
    assert obs_times == [] and observation_receipt['first_at'] is None and observation_receipt['last_at'] is None
    oldjobs = {j['business_bag_id']: j for j in prior_final['jobs']}
    deltas = []
    for j in final['jobs']:
        old = oldjobs[j['business_bag_id']]
        complete = old['status'] == j['status'] == 'completed'
        delta = j['completed_at'] - old['completed_at'] if complete else None
        deltas.append({'business_bag_id': j['business_bag_id'], 'prior_status': old['status'], 'new_status': j['status'],
            'prior_completed_at': old['completed_at'], 'new_completed_at': j['completed_at'], 'delta_seconds': delta,
            'comparison': 'unknown_incomplete' if not complete else 'harmed' if delta > 0 else 'improved' if delta < 0 else 'equal'})
    segments = []
    for record in raw['segments']:
        assert sha(record['raw']['path']) == record['raw']['sha256']
        segment = load(record['raw']['path']); result = segment['result']
        segments.append({'target':record['target'],'actual_clock':record['actual_clock'],'result_available':result is not None,
            'snapshot_time': result['physical_clock'] if result else None, 'population': result['population'] if result else None,
            'native_summary': result['native_summary'] if result else None,
            'wall_seconds': segment['wall_seconds'], 'raw': record['raw'],'last_native_batch':segment['native_batches'][-1]})
    stopped = load(raw['segments'][-1]['raw']['path'])
    assert stopped['result'] is None and stopped['status'] == 'budget_exhausted'
    assert inputs['options']['max_events'] == 100000
    terminal_public = [dict(t, public_owner=owner) for owner,v in views.items() for t in v['trays']]
    assert len(terminal_public) == len({t['tray_id'] for t in terminal_public}) == 22
    assert all(v['now'] == raw['final_physical_time'] for v in views.values())
    received_after_snapshot = [dict(a, public_owner=owner) for owner,v in views.items()
        for a in v['delivered_transfer_acks'] if a['status']=='received' and a['received_at']>snapshot_time]
    latest_received = max(received_after_snapshot,key=lambda a:a['received_at'])
    last_exit = by_event['EDGE_EXIT'][-1] if by_event['EDGE_EXIT'] else None
    report = {'schema': 'g31.independent.airport_receiver_admission_audit.v1', 'run': str(RUN),
        'method': 'Standard-library closed raw/ACK/event/public-observation inspection; no controller/model/native imports or execution.',
        'closure': {'plan_sha256': sha(RUN/'plan.json'), 'archive_count': len(plan['source_archive']), 'archive_mismatches': archive_bad,
            'evidence_count': len(acceptance['evidence_sha256']), 'evidence_mismatches': evidence_bad, 'acceptance': acceptance['status'],
            'physical_stop': raw['final_physical_time'], 'last_complete_snapshot_time':snapshot_time,
            'warmup_reached':False,'continuous_session_count': 1, 'reset_count': 0},
        'input_comparison': {'full_business_jobs': 28506, 'same_jobs_trays_graph_capacity_services': True, 'only_delta': changes,
            'different_receiver_admission_control_and_native_version': True, 'unchanged_business_version': plan['business_contract_version']},
        'last_closed_snapshot_business': {'snapshot_time':snapshot_time,'population': final['population'], 'status_counts': dict(collections.Counter(j['status'] for j in final['jobs'])),
            'unresolved_offered': 28506-len(by_event['UNLOAD_COMPLETE']), 'completed_ids': [j['business_bag_id'] for j in final['jobs'] if j['status']=='completed'],
            'native_leg_counts': {k: len(by_event[k]) for k in ('LEG_COMPLETE','STORAGE_ENTER','UNLOAD_COMPLETE','EMPTY_RECEIVED')}},
        'last_closed_snapshot_movement': {'snapshot_time':snapshot_time,'event_counts': {k: len(v) for k,v in by_event.items()}, 'last_edge_enter': by_event['EDGE_ENTER'][-1] if by_event['EDGE_ENTER'] else None,
            'last_edge_exit': last_exit, 'within_snapshot_tail_seconds': snapshot_time-last_exit['time'] if last_exit else None,
            'motion_after_snapshot_unknown_from_receipts':True,
            'last_business_completion': by_event['UNLOAD_COMPLETE'][-1] if by_event['UNLOAD_COMPLETE'] else None},
        'receiver49_through_closed_snapshot': {'snapshot_time':snapshot_time,'max_remote_leases': max(len(r['remote_leases']) for r in occupancy49_history),
            'max_counted': max(len(r['counted']) for r in occupancy49_history),
            'grants': [e for e in by_event['EXPORT_GRANTED'] if e['to']==49], 'policy_rejection_count':len(policy_rejections),
            'grant_time_occupancy_policy_verified_from_receipts': True},
        'nodes_at_closed_snapshot': nodes, 'snapshot_tray_mode_counts': dict(collections.Counter(t['mode'] for t in final['trays'])),
        'failed_requests': len(failures), 'transfer_status_counts': dict(collections.Counter(t['status'] for t in final['transfers'])),
        'transfer_rejection_reasons': dict(collections.Counter(e['reason'] for e in by_event['TRANSFER_REJECTED'])),
        'observations': {'count':len(obs_times), 'first':min(obs_times) if obs_times else None, 'last':max(obs_times) if obs_times else None, 'owners':sorted(obs_owners),
            'owner_scope_integrity_passed':True, 'conditional_labels_available':False,
            'counts':[{'owner':k[0],'actual_available':k[1],'intents':k[2],'count':v} for k,v in sorted(obs_counts.items())]},
        'C10_guard_branch_audit': {'activate_at':plan['planner_activate_at'], 'counts':dict(gate_counts),
            'forecast_branch_reachable_on_recorded_observations':None,
            'scope':'Unavailable: stop precedes 43200 observation start, 57600 warmup and 57660 activation. Zero records is not zero supply.'},
        'same_business_prior_policy_comparison_at_28800': {'counts':dict(collections.Counter(d['comparison'] for d in deltas)),
            'strict_all_job_nonharm_established':False, 'unfinished_jobs_excluded':0}, 'segments':segments,
        'budget_diagnosis':{'input_global_max_events':100000,'last_snapshot_event_count':final['native_summary']['event_count'],
            'remaining_events_after_snapshot':100000-final['native_summary']['event_count'],
            'last_native_batch':stopped['native_batches'][-1],
            'source_explanation':'process_one_event first stops at cumulative result.summary.event_count >= config.max_events. advance_circulation_to also has a per-call budget=100000; with 79289 already used, the global remaining20711 must stop first. No per-tick100000 exhaustion is possible here.',
            'same_timestamp_event_storm_established':False,'final_event_counter_exported':False,
            'last_5_control_ticks':[{'at':r['at'],'owners':[{'owner':x['owner_id'],'supply_count':len(x['decision']['supplies']),'intent_count':len(x['decision']['intents']),'submit_count':len(x['attempts'])} for x in r['owner_decisions']]} for r in stopped['control_records'][-5:]]},
        'post_censor_public_evidence':{'at':raw['final_physical_time'],'timestamp_complete':False,
            'scope':'Diagnostic owner-public endpoint reads after failed advance, not a complete native result or actor training snapshot.',
            'unique_tray_count':len(terminal_public),'tray_modes':dict(collections.Counter(t['mode'] for t in terminal_public)),
            'active_edges':sum(t['edge_to']>=0 for t in terminal_public),
            'node49_receiving_leases':[t['tray_id'] for t in terminal_public if t['reception_node']==49],
            'node49_stationary_trays':[t['tray_id'] for t in terminal_public if t['node']==49 and t['edge_to']<0],
            'node53_stationary_trays':[t['tray_id'] for t in terminal_public if t['node']==53 and t['edge_to']<0],
            'latest_received_ack':latest_received,'motion_after_28800_proven_by_delivered_ack':True,
            'full_business_completion_at_stop':None,'new_global_wait_for_cycle_established':False},
        'excluded_claims':['full-flow completion','global deadlock freedom','forecast improvement','strict all-job nonharm','multi-step RL']}
    save('report.json',report);save('tray_wait_for.json',details);save('failed_requests.json',failures)
    save('node49_occupancy_history.json',occupancy49_history);save('all_business_deltas.json',deltas)
    save('C10_guard_branch_rows.json',gate_rows)
    save('post_censor_public_trays.json',terminal_public)
    print(json.dumps({'report':str(HERE/'report.json'),'population':final['population'],'last_edge_exit':last_exit,
        'snapshot_time':snapshot_time,'stop_time':raw['final_physical_time'],
        'failed_requests':len(failures),'receiver49_max_leases':report['receiver49_through_closed_snapshot']['max_remote_leases'],
        'C10_guard_counts':dict(gate_counts)},ensure_ascii=False))


if __name__ == '__main__':
    main()
