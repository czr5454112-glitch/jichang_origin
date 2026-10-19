"""Bounded closed-artifact audit; no native/model/controller execution.

All gzip/ref graphs are checked; only two selected callback rows are fully
materialized. The baseline's independent3978-row full audit remains separate.
"""
from collections import defaultdict
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import time
import traceback

from scripts.experiments.g31_ics_circulation.foundation_airport_observations_v2 import members,encoded

HERE=Path(__file__).resolve().parent
CYCLE=HERE.parent
RUN=CYCLE/'B2_live_behavior_shadow_003';BRANCH=RUN/'C00'
BASE=CYCLE/'C00_receiver_recorded_budget_002'
START=time.monotonic();SOFT_SECONDS=100

def checkpoint():
    if time.monotonic()-START>=SOFT_SECONDS:raise TimeoutError('independent audit soft100s; retain partial, no retry')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):
    data=Path(path).read_bytes()
    return json.loads(gzip.decompress(data) if str(path).endswith('.gz') else data)
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def write(name,value):
    with (HERE/name).open('x',encoding='utf8') as stream:json.dump(value,stream,indent=2,ensure_ascii=False,allow_nan=False)
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def bind(reference):
    assert sha(reference['path'])==reference['sha256'];return load(reference['path'])


def main(report):
    plan=load(RUN/'plan.json');receipt=load(RUN/'receipt.json');worker=load(BRANCH/'worker_report.json')
    accepted=bind(worker['acceptance']);raw=bind(worker['raw'])
    assert receipt['plan_sha256_at_launch']==sha(RUN/'plan.json')
    assert receipt['process']['status']=='exited' and receipt['process']['exitcode']==0
    assert accepted['status']=='closed_run_acceptance_passed' and not accepted['invalid']
    assert accepted['run_reference']==ref(RUN/'plan.json') and accepted['branch_keys']==['C00']
    for source,expected in plan['source_sha256'].items():
        assert sha(source)==expected and sha(RUN/plan['source_archive'][source])==expected
    report['process_status']=receipt['status'];report['source_archive_pairs']=len(plan['source_sha256'])
    report['actual_clock']=raw['final_physical_time'];report['snapshot']=raw['last_complete_snapshot_time']
    assert raw['status']==worker['status']==receipt['status']=='requested_calibration_end_reached'
    assert raw['final_physical_time']==raw['last_complete_snapshot_time']==59400.
    assert raw['session_instance_count']==1 and raw['physical_reset_count']==0
    baseline=load(BASE/'C00/raw.json.gz')
    assert raw['warmup_native_state_sha256']==baseline['warmup_native_state_sha256']
    assert Path(plan['input']['path']).read_bytes()==Path(load(BASE/'plan.json')['input']['path']).read_bytes()
    assert len(raw['final_result']['jobs'])==28506
    # Exact complete physical/native result equality except explicitly measured
    # native wall clocks; do not omit failed transfers or incomplete jobs.
    left=json.loads(json.dumps(raw['final_result']));right=json.loads(json.dumps(baseline['final_result']))
    ignored=[]
    for value in (left,right):
        value.pop('native_event_ms');value['advance'].pop('wall_seconds')
    assert left==right
    report['full_native_result_parity']={'equal':True,'excluded':['native_event_ms','advance.wall_seconds'],
        'includes':'all jobs/trays/transfers/receipts/leg identities/native counts/population/advance and continuation semantics',
        'completed_business':raw['final_result']['population']['completed']}
    calls=load(BRANCH/'client_calls.json.gz');oldcalls=load(BASE/'C00/client_calls.json.gz')
    clean=lambda rows:[{k:v for k,v in row.items() if k!='submit_compute_ms'} for row in rows]
    assert clean(calls)==clean(oldcalls)
    acks=load(BRANCH/'delivered_ack_views.json.gz')
    assert acks==load(BASE/'C00/delivered_ack_views.json.gz')
    report['all_command_payload_reply_retry_and_ACK_parity']=True
    resources=plan['behavior_shadow'];targets=bind(resources['runtime_targets'])
    selected={r['callback']['sequence']:r for r in bind(resources['selection'])['selected']}
    diagnostic=load(BRANCH/'behavior_shadow_receipt.json')
    assert diagnostic==raw['behavior_shadow'] and diagnostic['all_targets_hit'] and diagnostic['all_shadow_scores_completed']
    assert diagnostic['actual_hits']==diagnostic['registered_targets']==2 and len(diagnostic['results'])==2
    assert not diagnostic['native_consumption_closed'] and diagnostic['request_ACK_edge_join_pending']
    eventfile=Path(diagnostic['event_artifact']['path']);assert sha(eventfile)==diagnostic['event_artifact']['sha256']
    events=[json.loads(line) for line in eventfile.read_text().splitlines()]
    assert len(events)==2
    for event,result in zip(events,diagnostic['results'],strict=True):
        assert all(result[key]==value for key,value in event.items())
    results={r['actual_sequence']:r for r in diagnostic['results']}
    assert set(results)==set(selected)
    recording=load(BRANCH/'policy_observation_receipt.json')
    for key in ('artifact','blobs'):assert sha(recording[key]['path'])==recording[key]['sha256']
    blobs_path=recording['blobs']['path'];index={}
    for payload,offset,length in members(blobs_path,with_offsets=True):
        checkpoint();item=json.loads(payload);digest=item['sha256'];value=item['value']
        assert digest not in index and hashlib.sha256(encoded(value)).hexdigest()==digest
        index[digest]=(offset,length,len(value) if type(value)is list else None)
    @lru_cache(maxsize=128)
    def blob(digest):
        offset,length,_=index[digest]
        with open(blobs_path,'rb') as stream:
            stream.seek(offset);value=json.loads(gzip.decompress(stream.read(length)))
        assert value['sha256']==digest and hashlib.sha256(encoded(value['value'])).hexdigest()==digest
        return value['value']
    def validate(node):
        kind=node['kind']
        if kind=='inline':assert set(node)=={'kind','value'} and (node['value']is None or type(node['value'])in(str,int,float,bool))
        elif kind=='value':assert set(node)=={'kind','sha256'} and node['sha256']in index
        elif kind=='list':
            assert set(node)=={'kind','length','chunks'} and type(node['length'])is int and node['length']>=0
            assert all(key in index and index[key][2]is not None for key in node['chunks'])
            assert sum(index[key][2]for key in node['chunks'])==node['length']
        elif kind=='object':
            assert set(node)=={'kind','fields'}
            for item in node['fields'].values():validate(item)
        else:raise AssertionError('reference_kind')
    def decode(node):
        kind=node['kind']
        if kind=='inline':return node['value']
        if kind=='value':return blob(node['sha256'])
        if kind=='list':return [item for key in node['chunks'] for item in blob(key)]
        if kind=='object':return {key:decode(value) for key,value in node['fields'].items()}
        raise AssertionError('reference_kind')
    decoded={};count=0
    for count,payload in enumerate(members(recording['artifact']['path']),1):
        checkpoint();row=json.loads(payload)
        assert row['sequence']==count-1 and row['readonly'] and not row['native_execution_authority']
        assert row['candidate_conditional_labels']is None
        for field in ('observation','decision','policy_options'):validate(row[field])
        if row['sequence']in selected:
            decoded[row['sequence']]={key:decode(value)if key in ('observation','decision','policy_options')else value for key,value in row.items()}
    assert count==recording['record_count']==3978 and set(decoded)==set(selected)
    report['recording']={'all_blob_CRC_SHA_verified':True,'blob_count':len(index),'all_ref_graphs_verified':count,
        'full_callback_materializations':len(decoded),'scope':'All new storage hashes/graphs plus exactly2 full public rows; baseline all3978 audit remains separately closed.'}
    # Rebuild actual control callback order and bind every selected row to its
    # actual first attempted request; do not substitute the reference's call.
    order=[];callback_requests={}
    for segment in raw['segments']:
        run=bind(segment['raw']);checkpoint()
        for tick in run['control_records']:
            if not 43200<=tick['at']<=59400:continue
            for owner in tick['owner_decisions']:
                current=len(order)
                identity={'owner_id':owner['owner_id'],'now':tick['at'],'sequence':current,'residual_index':0,'request_prefix':f"protocol:{tick['tick']}"}
                order.append(identity)
                for index_attempt,attempt in enumerate(owner['attempts']):
                    callback_requests[current]=attempt['request_id']
                    if attempt['reply']['status']=='pending':
                        current=len(order);order.append({**identity,'sequence':current,'residual_index':index_attempt+1,'request_prefix':f"protocol:{tick['tick']}:residual"})
    assert len(order)==3978
    model_manifest=bind(resources['model_manifest']);joins=[]
    for target in targets:
        identity=target['callback'];seq=identity['sequence'];record=decoded[seq];result=results[seq];scorer=result['scorer']
        assert order[seq]==identity and result['identity']==identity
        assert result['actual_owner']==record['owner_id']==identity['owner_id'] and result['actual_now']==record['now']==identity['now']
        assert result['status']=='completed_shadow_scoring_only' and scorer['status']=='completed_public_shadow_scoring'
        assert scorer['callback_record_sha256']==canonical(record)
        # Wrapper digest is insertion-order JSON, while scorer uses sorted
        # canonical JSON. Restore the wrapper's documented top-level order.
        fields=('schema','sequence','branch','business_contract_version','owner_id','now','readonly','scope','observation','policy_options','native_execution_authority','candidate_conditional_labels','decision')
        assert result['public_record_sha256']==hashlib.sha256(encoded({key:record[key]for key in fields})).hexdigest()
        assert [row['seed']for row in scorer['models']]==[17,29,43]
        assert not scorer['native_runtime_verified_by_this_scorer'] and not scorer['scores_used_for_selection']
        for saved,descriptor in zip(scorer['models'],model_manifest['model_descriptors'],strict=True):
            assert saved['checkpoint']==descriptor and saved['model_content_sha256']==canonical(bind(descriptor))
            assert len(saved['scores'])==len(record['decision']['intents'])
        assert result['entire_recorded_callback_elapsed_including_all_storage_seconds']>=result['callback_elapsed_before_return_seconds_including_storage']>=scorer['full_scorer_wall_seconds']>=0
        request_id=callback_requests[seq]
        matches=[c for c in calls if c['kind']=='transfer' and not c['retry'] and c['request']['request_id']==request_id]
        assert len(matches)==1;call=matches[0];request=call['request']
        proposed=dict(record['decision']['intents'][0]);proposed.pop('expected_version',None)
        proposed.update(request_id=request_id,owner_id=record['owner_id'])
        assert proposed==request==selected[seq]['actual_request'] and call['at']==record['now']
        legs=[leg for leg in raw['final_result']['leg_identities'] if leg['kind']=='empty_return' and leg['transport_leg_id'].split(':empty_return:')[0]==request_id]
        assert len(legs)==1
        entries=[r for r in raw['final_result']['receipts'] if r['event']=='EDGE_ENTER' and r['transport_leg_id']==legs[0]['transport_leg_id']]
        positive=[a for a in acks[record['owner_id']]['delivered_transfer_acks'] if a['request_id']==request_id and a['status']in('departed','received')]
        assert entries and positive
        edge=min(entries,key=lambda r:r['time']);ack=min(positive,key=lambda r:r['delivered_at'])
        assert 0<=edge['time']-record['now']<=300 and 0<=ack['delivered_at']-record['now']<=300
        joins.append({'identity':identity,'request':request,'first_edge':edge,'positive_source_delivered_ACK':ack,
            'scorer_wall_seconds':scorer['full_scorer_wall_seconds'],
            'entire_recorded_callback_wall_seconds':result['entire_recorded_callback_elapsed_including_all_storage_seconds'],
            'all3_actual_models_scored':True,'public_row_canonical_sha256':canonical(record)})
    report.update(status='passed_closed_two_callback_shadow_mechanism',joins=joins,
        physical_window_completed=True,model_consumptions=6,fit_calls=0,native_calls_in_this_audit=0,
        native_consumption_proven_by_this_separate_audit=True,scores_selected_or_modified_actions=False,
        policy_gain_established=False,unseen_validation_established=False,request_100ms_certified=False,
        full28506_business_completed=False)


if __name__=='__main__':
    report={'schema':'g31.airport_live_shadow_independent_audit.v1','status':'failed_or_incomplete',
        'scope':'posthoc-selected train-trajectory mechanism only; no native/model execution in this audit',
        'budget':{'soft_seconds':SOFT_SECONDS,'requested_outer_hard_seconds':120,'native_branches':0,'fit_calls':0,'automatic_retries':0}}
    try:main(report)
    except Exception:report['exception']=traceback.format_exc()
    report['wall_seconds']=time.monotonic()-START
    write('report.json',report)
    print(json.dumps({'status':report['status'],'wall_seconds':report['wall_seconds']}))
    if report['status']!='passed_closed_two_callback_shadow_mechanism':raise SystemExit(1)
