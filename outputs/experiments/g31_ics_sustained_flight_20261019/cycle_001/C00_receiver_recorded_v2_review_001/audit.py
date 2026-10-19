"""Independent completed-artifact audit; no native/model/controller execution."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / 'scripts').is_dir())
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation.foundation_airport_observations_v2 import read_records

RUN = HERE.parent / 'C00_receiver_recorded_v2_001'
BRANCH = RUN / 'C00'
PREVIOUS = HERE.parent / 'C00_receiver_admission_500k_001'
ORIGINAL_POLICY = HERE.parent / 'C00_cyclic_od_001'


def load(path):
    if str(path).endswith('.gz'):
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            return json.load(f)
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for part in iter(lambda: f.read(1048576), b''):
            digest.update(part)
    return digest.hexdigest()


def save(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as f:
        json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')


def counted(trays, node):
    return [t['tray_id'] for t in trays if (t['node'] == node and t['edge_to'] < 0)
        or t['edge_to'] == node or t['reception_node'] == node]


def main():
    plan, receipt = load(RUN/'plan.json'), load(RUN/'receipt.json')
    worker, acceptance = load(BRANCH/'worker_report.json'), load(BRANCH/'acceptance.json')
    assert receipt['process']['status'] == 'exited' and receipt['process']['exitcode'] == 0
    assert receipt['status'] == worker['status']
    assert receipt['status'] in ('requested_calibration_end_reached', 'censored_before_requested_window_end', 'native_event_budget_censored')
    assert acceptance['status'] == 'closed_run_acceptance_passed' and not acceptance['invalid']
    assert sha(RUN/'plan.json') == receipt['plan_sha256_at_launch']
    assert sha(BRANCH/'raw.json.gz') == worker['raw']['sha256']
    assert sha(BRANCH/'acceptance.json') == worker['acceptance']['sha256']
    for source, digest in plan['source_sha256'].items():
        assert sha(RUN/plan['source_archive'][source]) == digest
        assert sha(source) == digest
    for path, digest in acceptance['evidence_sha256'].items():
        assert sha(path) == digest, path
    for key in ['input','mapping','business_contract','business_audit','crosswalk','native_contract_reference','semantic_gate_reference','binary']:
        assert sha(plan[key]['path']) == plan[key]['sha256']
    old_plan = load(PREVIOUS/'plan.json')
    assert Path(plan['input']['path']).read_bytes() == Path(old_plan['input']['path']).read_bytes()
    for key in ['controller','physical_start','warmup_end','window_boundaries','resource_contract','receiver_admission_policy','binary']:
        assert plan[key] == old_plan[key]
    inputs, raw = load(plan['input']['path']), load(BRANCH/'raw.json.gz')
    final = raw['final_result']
    assert final is not None, 'No completed snapshot; separate censored audit required'
    snapshot_time, actual = final['physical_clock'], raw['final_physical_time']
    assert snapshot_time == raw['last_complete_snapshot_time'] <= actual <= 59400
    assert raw['last_snapshot_is_actual_stop'] == (snapshot_time == actual)
    completed = receipt['status'] == 'requested_calibration_end_reached'
    if completed:
        assert snapshot_time == actual == 59400
    assert raw['session_instance_count'] == 1 and raw['physical_reset_count'] == 0
    assert len(final['jobs']) == len(inputs['jobs']) == 28506
    assert len(final['trays']) == len(inputs['trays']) == 22
    assert {j['business_bag_id'] for j in final['jobs']} == {j['business_bag_id'] for j in inputs['jobs']}
    boundary = None
    if raw['warmup_native_state_sha256'] is not None:
        boundary = load(BRANCH/'warmup_boundary.json')
        assert boundary['physical_time'] == 57600
        assert boundary['native_state_sha256'] == raw['warmup_native_state_sha256']
        assert sha(boundary['raw']['path']) == boundary['raw']['sha256']
        assert load(boundary['raw']['path'])['result']['physical_clock'] == 57600
    if completed:
        assert boundary is not None

    segments, common_prefix = [], []
    last_clock, last_events = 0, 0
    for item in raw['segments']:
        assert sha(item['raw']['path']) == item['raw']['sha256']
        segment = load(item['raw']['path'])
        assert item['start_at'] == last_clock
        last_clock = item['actual_clock']
        result = segment['result']
        entry = {'index':item['index'], 'target':item['target'], 'actual_clock':last_clock,
            'status':segment['status'], 'result_available':result is not None,
            'elapsed_wall_seconds':item['elapsed_wall_seconds'], 'raw':item['raw']}
        if result:
            count = result['native_summary']['event_count']
            assert count >= last_events and result['physical_clock'] == last_clock
            entry.update(event_count=count, event_increment=count-last_events, population=result['population'])
            last_events = count
            old_path = PREVIOUS/'C00'/Path(item['raw']['path']).name
            if old_path.exists():
                previous = load(old_path)
                assert previous['result']['physical_clock'] == result['physical_clock']
                fields = ['receipts','jobs','trays','transfers','leg_identities']
                for field in fields:
                    assert previous['result'][field] == result[field], (item['index'],field)
                old_calls = [{k:v for k,v in c.items() if k != 'submit_compute_ms'} for c in previous['client_calls']]
                new_calls = [{k:v for k,v in c.items() if k != 'submit_compute_ms'} for c in segment['client_calls']]
                assert old_calls == new_calls
                common_prefix.append({'time':last_clock,'fields':fields+['client_calls'],
                    'only_ignored_client_call_field':'submit_compute_ms','exact_equal':True})
        segments.append(entry)
    assert last_clock == actual
    assert any(row['time'] == 43200 for row in common_prefix), 'Common43200 prefix missing'

    events = collections.defaultdict(list)
    for row in final['receipts']:
        events[row['event']].append(row)
    completions = events['UNLOAD_COMPLETE']
    assert len(completions) == final['population']['completed']
    assert len(completions) == sum(j['status'] == 'completed' for j in final['jobs'])
    replay = {t['tray_id']:dict(t,edge_to=-1,reception_node=-1) for t in inputs['trays']}
    occupancy, grants = [], []
    for event in final['receipts']:
        tray = replay.get(event['tray_id'])
        if tray is None:
            continue
        kind = event['event']
        if kind == 'EDGE_ENTER':
            tray['edge_to'] = event['to']
        elif kind == 'EDGE_EXIT':
            tray['node'], tray['edge_to'] = event['to'], -1
        elif kind == 'EXPORT_GRANTED':
            before = counted(replay.values(),event['to'])
            if event['to'] == 49:
                excluding_self = [x for x in before if x != event['tray_id']]
                assert len(excluding_self) < 3
                grants.append({'event':event,'counted_before_excluding_self':excluding_self})
            tray['reception_node'] = event['to']
        elif kind in ('EMPTY_RECEIVED','UNUSED_RECEIVING_RELEASED'):
            tray['reception_node'] = -1
        if kind in ('EDGE_ENTER','EDGE_EXIT','EXPORT_GRANTED','EMPTY_RECEIVED','UNUSED_RECEIVING_RELEASED'):
            occupancy.append({'time':event['time'], 'event':kind,
                'counted':len(counted(replay.values(),49)),
                'receiving_leases':sum(t['reception_node']==49 for t in replay.values())})
    for t in final['trays']:
        assert all(replay[t['tray_id']][key] == t[key] for key in ['node','edge_to','reception_node'])
    assert max(x['receiving_leases'] for x in occupancy) <= 3
    assert max(x['counted'] for x in occupancy) <= 4

    observation_receipt = load(BRANCH/'policy_observation_receipt.json')
    for key in ['artifact','blobs']:
        assert sha(observation_receipt[key]['path']) == observation_receipt[key]['sha256']
    times, owners, guard_rows = [], collections.Counter(), []
    counts = collections.Counter()
    max_group_count, group_count_none = 0, 0
    for sequence, row in enumerate(read_records(observation_receipt['artifact']['path'])):
        obs, decision = row['observation'], row['decision']
        assert row['schema'] == 'g31.foundation.airport_policy_observation.v2'
        assert row['sequence'] == sequence and row['now'] == obs['now'] == decision['now']
        assert row['owner_id'] == obs['owner_id'] and row['readonly']
        assert row['candidate_conditional_labels'] is None and not row['native_execution_authority']
        assert 43200 <= row['now'] <= min(actual,59400)
        assert obs['transfers'] == obs['client_transfer_ledger']
        assert all(x['issued_at'] <= row['now'] for x in obs['transfers'])
        assert all(x.get('delivered_at',row['now']) <= row['now'] for x in obs['delivered_messages'])
        for group in obs.get('control_projection',{}).get('waiting_groups',[]):
            n = group.get('count')
            if n is None:
                group_count_none += 1
            else:
                assert type(n) is int and n >= 0
                max_group_count = max(max_group_count,n)
        times.append(row['now']); owners[row['owner_id']] += 1
        available = sum(s['ledger'] == 'actual_available' for s in decision['supplies'])
        if row['now'] >= plan['planner_activate_at']:
            gate = ('baseline_intents_returned' if decision['intents'] else
                'no_actual_available_supply' if not available else 'forecast_would_be_called')
            counts[gate] += 1
            guard_rows.append({'sequence':sequence,'now':row['now'],'owner':row['owner_id'],
                'actual_available':available,'intent_count':len(decision['intents']),'gate':gate})
    assert len(times) == observation_receipt['record_count']
    assert observation_receipt['first_at'] == (min(times) if times else None)
    assert observation_receipt['last_at'] == (max(times) if times else None)
    if completed:
        assert min(times) == 43200

    old = load(ORIGINAL_POLICY/'C00/raw.json.gz')['final_result']
    old_jobs = {j['business_bag_id']:j for j in old['jobs']}
    deltas = []
    for job in final['jobs']:
        previous = old_jobs[job['business_bag_id']]
        both = job['status'] == previous['status'] == 'completed' and previous['completed_at'] <= snapshot_time
        delta = job['completed_at'] - previous['completed_at'] if both else None
        deltas.append({'business_bag_id':job['business_bag_id'],'old_status':previous['status'],
            'new_status':job['status'],'old_completed_at':previous['completed_at'],
            'new_completed_at':job['completed_at'],'delta_seconds':delta,
            'comparison':'unknown_incomplete' if delta is None else 'harmed' if delta>0 else 'improved' if delta<0 else 'equal'})
    eligible = completed and bool(counts['forecast_would_be_called'])
    report = {'schema':'g31.independent.airport_recorded_v2_audit.v1',
        'method':'Closed raw/receipts/ACK/source inspection plus read-only lossless decoder; no native/model/controller execution.',
        'closure':{'status':receipt['status'],'process':receipt['process'],'native_acceptance':acceptance['status'],
            'plan_sha256':sha(RUN/'plan.json'),'source_and_archive_count':len(plan['source_sha256']),
            'acceptance_evidence_hashes_verified':len(acceptance['evidence_sha256']),
            'actual_clock':actual,'last_complete_snapshot_time':snapshot_time,
            'warmup_hash':raw['warmup_native_state_sha256'],'warmup_boundary':boundary,
            'requested_window_reached':completed,'session_count':1,'reset_count':0},
        'same500k_input':{'bytes_equal':True,'sha256':plan['input']['sha256'],
            'full_population':28506,'trays':22,'same_business_physics_policy_controller':True},
        'prior500k_common_prefix':common_prefix,
        'last_closed_snapshot':{'physical_time':snapshot_time,'population':final['population'],
            'unfinished_total_population':28506-len(completions),
            'business_status_counts':dict(collections.Counter(j['status'] for j in final['jobs'])),
            'tray_modes':dict(collections.Counter(t['mode'] for t in final['trays'])),
            'native_summary':final['native_summary'],
            'last_edge_enter':events['EDGE_ENTER'][-1] if events['EDGE_ENTER'] else None,
            'last_edge_exit':events['EDGE_EXIT'][-1] if events['EDGE_EXIT'] else None,
            'last_business_completion':completions[-1] if completions else None,
            'transfer_statuses':dict(collections.Counter(t['status'] for t in final['transfers']))},
        'receiver49':{'snapshot_time':snapshot_time,'grants_checked':len(grants),
            'max_leases':max(x['receiving_leases'] for x in occupancy),'max_counted':max(x['counted'] for x in occupancy),
            'self_reservation_deducted_and_grant_occupancy_below3':True,'replay_matches_final_trays':True,
            'policy_rejections':sum(e['reason']=='receiver_transit_reserve' for e in events['TRANSFER_REJECTED'])},
        'public_observations':{'reconstructable_records':len(times),'owners':dict(owners),
            'first':min(times) if times else None,'last':max(times) if times else None,
            'schema':'g31.foundation.airport_policy_observation.v2',
            'recording_and_blob_hashes_verified':True,'max_public_waiting_group_count':max_group_count,
            'unknown_group_count_occurrences':group_count_none,
            'receiver_completeness_inferred_from_ledger':False,'conditional_outcome_labels_established':False},
        'C10_guard':{'activate_at':plan['planner_activate_at'],'counts':dict(counts),
            'eligible_for_same_contract_C10_preparation':eligible,
            'scope':'Initial baseline guard only: real actual_available supply and zero baseline intent. No candidate, destination receiver completeness, command or benefit certified.'},
        'old7_completion_reference':{'comparison_counts':dict(collections.Counter(d['comparison'] for d in deltas)),
            'full_denominator':28506,'unfinished_excluded':0,'strict_all_job_nonharm_established':False},
        'segments':segments,'excluded_claims':['all28506completed','globaldeadlockfreedom','forecasteffect','fullnonharm','multistepRL']}
    save('report.json',report); save('node49_occupancy.json',occupancy);save('node49_grants.json',grants)
    save('all_business_deltas.json',deltas);save('C10_guard_rows.json',guard_rows)
    print(json.dumps({'status':receipt['status'],'actual_clock':actual,'snapshot':snapshot_time,
        'completed_business':len(completions),'population':28506,'observations':len(times),
        'C10_gate_counts':dict(counts),'C10_prepare_eligible':eligible}))


if __name__ == '__main__':
    main()
