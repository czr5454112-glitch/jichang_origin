"""Inspect retained partial evidence after hard timeout; never load native or policy."""
import collections
import gzip
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
RUN=HERE.parent/'C00_receiver_admission_500k_001'
BRANCH=RUN/'C00'


def load(path):
    if str(path).endswith('.gz'):
        with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name,value):
    with (HERE/name).open('x',encoding='utf-8',newline='\n') as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')


def main():
    plan,receipt=load(RUN/'plan.json'),load(RUN/'receipt.json')
    assert receipt['status']=='unknown_hard_timeout_or_incomplete'
    assert receipt['process']['status']=='hard_timeout' and receipt['worker_report'] is None
    assert not (BRANCH/'acceptance.json').exists() and not (BRANCH/'worker_report.json').exists()
    assert sha(RUN/'plan.json')==receipt['plan_sha256_at_launch']
    assert all(sha(RUN/a)==plan['source_sha256'][s] for s,a in plan['source_archive'].items())
    assert sha(plan['input']['path'])==plan['input']['sha256']
    data=load(plan['input']['path']);assert len(data['jobs'])==28506 and len(data['trays'])==22
    progress=[json.loads(line) for line in (BRANCH/'progress.jsonl').read_text(encoding='utf-8').splitlines()]
    assert [r['target'] for r in progress]==list(range(0,43201,3600))
    for row in progress:
        assert row['status']=='reached' and row['actual_clock']==row['target']
        assert sha(row['raw']['path'])==row['raw']['sha256']
    last=load(progress[-1]['raw']['path']);result=last['result']
    assert result['physical_clock']==43200 and len(result['jobs'])==28506
    assert result['population']['completed']==241
    earlier=load(BRANCH/'segment_08.json.gz')['result']
    old_earlier=load(HERE.parent/'C00_receiver_admission_001/C00/segment_08.json.gz')['result']
    assert all(earlier[k]==old_earlier[k] for k in ('receipts','jobs','trays','transfers','leg_identities'))
    old=load(HERE.parent/'C00_cyclic_od_001/C00/segment_12.json.gz')['result']
    previous={j['business_bag_id']:j for j in old['jobs']}
    deltas=[]
    for j in result['jobs']:
        a=previous[j['business_bag_id']];complete=a['status']==j['status']=='completed'
        delta=j['completed_at']-a['completed_at'] if complete else None
        deltas.append({'business_bag_id':j['business_bag_id'],'old_status':a['status'],'new_status':j['status'],
            'old_completed_at':a['completed_at'],'new_completed_at':j['completed_at'],'delta_seconds':delta,
            'comparison':'unknown_incomplete' if not complete else 'equal' if delta==0 else 'harmed' if delta>0 else 'improved'})
    replay={t['tray_id']:dict(t,edge_to=-1,reception_node=-1) for t in data['trays']}
    def occupancy(node,exclude=None):
        return [t['tray_id'] for t in replay.values() if t['tray_id']!=exclude and
            ((t['edge_to']<0 and t['node']==node) or t['edge_to']==node or t['reception_node']==node)]
    max_leases=max_counted=grants49=0;events=collections.Counter();lastmotion={}
    for e in result['receipts']:
        events[e['event']]+=1;t=replay.get(e['tray_id'])
        if t is None:continue
        if e['event']=='EDGE_ENTER':t['edge_to']=e['to'];lastmotion['entry']=e
        elif e['event']=='EDGE_EXIT':t['node'],t['edge_to']=e['to'],-1;lastmotion['exit']=e
        elif e['event']=='EXPORT_GRANTED':
            if e['to']==49:assert len(occupancy(49,e['tray_id']))<3;grants49+=1
            t['reception_node']=e['to']
        elif e['event'] in ('EMPTY_RECEIVED','UNUSED_RECEIVING_RELEASED'):t['reception_node']=-1
        max_leases=max(max_leases,sum(t['reception_node']==49 for t in replay.values()))
        max_counted=max(max_counted,len(occupancy(49)))
    assert all(all(replay[t['tray_id']][k]==t[k] for k in ('node','edge_to','reception_node')) for t in result['trays'])
    observation_path=BRANCH/'policy_observations.jsonl.gz'
    n=total_bytes=max_row_bytes=0;first_at=last_at=None;byowner=collections.Counter();last_row=None;truncated=None
    try:
        with gzip.open(observation_path,'rt',encoding='utf-8') as f:
            for line in f:
                row=json.loads(line);assert row['sequence']==n and row['readonly'] and row['candidate_conditional_labels'] is None
                assert row['now']==row['observation']['now']==row['decision']['now']
                assert row['observation']['transfers']==row['observation']['client_transfer_ledger']
                n+=1;total_bytes+=len(line.encode());max_row_bytes=max(max_row_bytes,len(line.encode()))
                first_at=row['now'] if first_at is None else first_at;last_at=row['now'];byowner[row['owner_id']]+=1;last_row=row
    except (EOFError,OSError,UnicodeDecodeError,json.JSONDecodeError) as error:truncated=type(error).__name__+':'+str(error)
    assert n==786 and first_at==43200 and last_at==46500 and truncated is None
    report={'schema':'g31.independent.airport_resource_hard_timeout.v1','status':'hard_timeout_retained_partial_evidence',
        'method':'Standard library only; no native/result_at/model/controller execution.',
        'closure':{'plan_sha256':sha(RUN/'plan.json'),'process':receipt['process'],'native_acceptance_closed':False,
            'worker_report_present':False,'source_archive_count':len(plan['source_archive']),'archive_hashes_match':True,
            'last_saved_complete_snapshot':43200,'actual_stop_physical_time':None,'actual_stop_lower_bound_from_callback':46500,
            'warmup_reached_proven':False,'requested59400_window_completed':False},
        'last_complete_snapshot':{'time':43200,'full_business_count':28506,'population':result['population'],
            'uncompleted_offered':28506-result['population']['completed'],'native_summary':result['native_summary'],
            'tray_modes':dict(collections.Counter(t['mode'] for t in result['trays'])),'last_motion':lastmotion},
        'receiver49_through_snapshot':{'max_remote_leases':max_leases,'max_counted_occupancy':max_counted,'grants_checked':grants49,
            'all_grants_deduct_own_and_require_occupancy_below3':True,'replayed_physical_and_lease_state_matches':True},
        'resource_only_behavior_parity':{'through_time':28800,'actual_receipts_jobs_trays_transfers_legs_equal_prior100000_attempt':True},
        'old7_sameclock_reference':{'snapshot':43200,'comparisons':dict(collections.Counter(x['comparison'] for x in deltas)),
            'strict_all_job_nonharm':False,'unfinished_jobs_excluded':0},
        'observation_cost':{'file_sha256':sha(observation_path),'gzip_bytes':observation_path.stat().st_size,
            'complete_rows':n,'first_at':first_at,'last_at':last_at,'uncompressed_bytes':total_bytes,
            'max_row_bytes':max_row_bytes,'owner_counts':dict(byowner),'last_row_ledger_length':len(last_row['observation']['client_transfer_ledger']),
            'same_ledger_serialized_twice_per_row':True,'truncated_final_member':truncated,
            'last_decision':{'now':last_row['now'],'supplies':len(last_row['decision']['supplies']),'intents':len(last_row['decision']['intents'])}},
        'timeout_diagnosis':{'last_segment12_saved_elapsed_seconds':progress[-1]['elapsed_wall_seconds'],
            'segment13_result_not_saved':True,'callback_progress_after_snapshot_to46500_proven':True,
            'soft_check_location':'foundation_airport_campaign.execute_continuous only before each3600s controller call',
            'reason_soft240_did_not_close':'segment13 entered around162.64s and checks no soft deadline inside its many ticks; hard300 interrupted it',
            'evidence_for_same_time_native_spin':False,'last_snapshot_event_count':181864,'global_event_limit':500000,
            'diagnosis_scope':'Recorder repeats two full4796-row ledger arrays plus static/context history each callback;2.344GB serialized in3300simulated seconds. Callback timestamp progresses; this supports recording/controller overhead, not a same-time native deadlock claim.'},
        'C10_eligibility':{'after57660_observation_count':0,'supply_or_forecaster_eligibility':None,'prepare_C10':False,
            'reason':'No successful common warmup or complete window. No late observations; do not mistake this for zero supply.'},
        'progress':progress,'excluded_claims':['native_acceptance_closed','59400completion','global circulation success','C10 forecast effect','all-job nonharm']}
    save('report.json',report);save('all_business_deltas_at43200.json',deltas)
    save('last_complete_snapshot_trays.json',result['trays'])
    print(json.dumps({'report':str(HERE/'report.json'),'last_complete':43200,'completed_at_snapshot':241,
        'callback_progress_to':last_at,'observations':n,'serialized_bytes':total_bytes,'max_node49_leases':max_leases},ensure_ascii=False))


if __name__=='__main__':main()
