"""Saved three-branch readback only: no native loading or model predictions."""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, time
from pathlib import Path
from types import SimpleNamespace
from . import research_live_obligation_native_probe as producer

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_bytes())
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def require(v, why):
    if not v:raise ValueError('saved_live_probe:'+why)
def one(rows,why):
    require(len(rows)==1,why);return rows[0]
def events(raw,event,job=None,tray=None):
    return [r for r in raw['result']['receipts'] if r['event']==event and
            (job is None or r['business_bag_id']==job) and (tray is None or r['tray_id']==tray)]
def captures(decision):
    endpoint=decision['information']['raw_endpoints']
    ack=endpoint['command']['last_delivered_ack']
    return [ack['planning_snapshot_v3'],*endpoint['received']]

def audit(folder):
    started=time.perf_counter();plan=read(folder/'preregistered_protocol.json');receipt=read(folder/'receipt.json')
    ledger=read(folder/'branch_ledger.json');admission=read(folder/'run_acceptance.json')
    pins={**plan['source_sha256'],**admission['evidence_sha256']}
    for path,digest in pins.items():require(sha(path)==digest,'entry_pin:'+path)
    for path,digest in plan['source_sha256'].items():require(sha(folder/plan['source_archive'][path])==digest,'archived_source')
    require(sha(folder/'preregistered_protocol.json')==receipt['plan_sha256'],'plan')
    require(sha(folder/'branch_ledger.json')==receipt['ledger_sha256'],'ledger')
    require(sha(folder/'run_acceptance.json')==receipt['run_acceptance']['sha256'],'acceptance')
    require(plan['branch_order']==list(ledger)==receipt['branch_order']==producer.ORDER,'three_order')
    require(receipt['branch_count']==3 and receipt['source_changed']==[],'denominator_or_drift')
    require(admission['status']=='closed_run_acceptance_passed' and admission['active'] is False and admission['invalid']==[],'run_acceptance_status')
    phases=[r['phase'] for r in admission['costs']]
    require('run_entry_closed_verifiers' in phases and 'run_exit_closed_verifiers' in phases,'entry_exit44_21')
    for key in producer.ORDER:
        require('branch_entry:'+key in phases and 'branch_exit:'+key in phases,'branch_pins')
    pure_dir=OUT/'live_obligation_projection_prepare_003';pure_ledger=read(pure_dir/'branch_ledger.json')
    pure_receipt=read(pure_dir/'receipt.json')
    rows={};raws={}
    for key in producer.ORDER:
        row=ledger[key];artifact=row['raw_artifact'];require(sha(artifact['path'])==artifact['sha256'],'raw_sha')
        raw=json.loads(gzip.decompress(Path(artifact['path']).read_bytes()));raws[key]=raw
        require(raw.get('partial') is not True and raw['specification']['vector']==plan['rows'][key]['vector'],'whole_raw_action')
        input_path=folder/'inputs'/(key+'.json');require(sha(input_path)==plan['input_file_sha256'][key],'input_sha')
        require(raw['input']==read(input_path),'raw_input')
        producer.validate_runtime_input(raw['input'])
        producer.verify_saved_inputs(raw)
        rebuilt=producer.completed_summary(raw['input'],raw['result'],SimpleNamespace(rows=raw['outbox'],calls=raw['calls']),
            raw['continuation'],row['vector'],raw['initial_owners'],raw['decisions'])
        require(rebuilt==raw['summary']==row['summary'],'full_saved_assessor_replay')
        require(rebuilt['audit']['status']=='passed' and rebuilt['common_horizon_complete'],'physical_replay')
        require(raw['result']['advance']['physical_time']==40. and raw['result']['advance']['horizon_complete'],'native_horizon')
        jobs={j['business_bag_id']:j for j in raw['result']['jobs']}
        require(set(jobs)==producer.model.JOBS and len(raw['result']['jobs'])==5,'whole_five')
        actual={}
        for name,job in jobs.items():
            final=one(events(raw,'UNLOAD_COMPLETE',name),'one_final:'+name)
            require(job['status']=='completed' and type(job['completed_at']) in (int,float) and
                math.isfinite(job['completed_at']) and job['completed_at']==final['time']<=40.,'terminal:'+name)
            actual[name]=job['completed_at']
        p_enter=one(events(raw,'STORAGE_ENTER','blocker','P'),'P_storage_enter')
        p_release=one(events(raw,'STORAGE_RELEASE','blocker','P'),'P_storage_release')
        require(p_enter['node']==p_release['node']==9 and p_enter['time']<=p_release['time']==8.95,'mandatory_storage')
        p_path=[(r['from'],r['to']) for r in events(raw,'EDGE_ENTER','blocker','P')]
        require(p_path==[(1,9),(9,3),(3,10)],'P_full_path')
        require(len(events(raw,'LOAD_START','reuse1','L'))==len(events(raw,'LOAD_START','reuse2','L'))==1,'same_tray_reuse')
        requests={}
        for call in raw['calls']:
            payload=call['request'];identity=payload['request_id']
            require(identity not in requests or payload==requests[identity],'immutable_retry')
            requests[identity]=payload
        for returning in raw['continuation']['returns']:
            identity=returning['request_id'];ack=raw['outbox'][identity]['ack']
            received=one([r for r in events(raw,'EMPTY_RECEIVED',tray='L') if r['reason']==identity],'return_received')
            require(ack['status']=='received' and ack['received_at']==received['time']<=ack['delivered_at']<=40.,'return_delivered_ack')
        pure_row=pure_ledger['rows'][key];require(sha(pure_row['raw'])==pure_row['raw_sha256'],'pure_raw')
        pure=json.loads(gzip.decompress(Path(pure_row['raw']).read_bytes()))
        require(pure['action']==row['vector'],'pure_vector')
        expected=pure['assessment']['completion'];require(actual==expected,'exact_per_job_model_conformance')
        # Aggregation order may differ by one ULP; no tolerance is used for jobs.
        diagnostic={'actual_completion':actual,'pure_completion':expected,'per_job_actual_minus_pure':{j:actual[j]-expected[j] for j in jobs},
            'actual_completion_sum':rebuilt['completion_sum'],'pure_completion_sum':pure['prediction']['completion_sum'],
            'sum_difference_only':rebuilt['completion_sum']-pure['prediction']['completion_sum']}
        initial_known=all(r['information']['native_delivery_verified'] is True for r in raw['initial_owners'].values())
        require(initial_known,'initial_actual_inputs')
        stage_rows=[]
        for owner in ('A','B'):
            decision=one(raw['decisions'][owner],'one_decision_per_owner')
            info=decision['information'];envelopes=captures(decision)
            require(len(envelopes)==2,'two_source_captures')
            locals_=[e['capture']['capture_v2']['local_capture'] for e in envelopes]
            require({r['source_owner'] for r in locals_}=={'A','B'},'capture_sources')
            floor=min(r['captured_at'] for r in locals_)
            actions=[]
            for envelope,local in zip(envelopes,locals_,strict=True):
                require(decision['collection']['at']<=local['captured_at']<=envelope['delivered_at']<=decision['at']<local['valid_until'],'capture_chronology')
                require(decision['at']-local['captured_at']<=.05,'capture_age')
                for a in envelope['capture']['capture_v2']['extension']['submitted_physical_actions']:
                    ack=a['last_delivered_ack'];require(0<=ack['delivered_at']<floor,'physical_ACK_before_union')
                    require(a['source_owner']==local['source_owner'],'action_authority')
                    actions.append({'owner':a['source_owner'],'request_id':a['request_id'],'status':ack['status'],'delivered_at':ack['delivered_at']})
            view=decision['actual_local_view'];require(view['owner_id']==owner and view['now']==decision['at'],'current_owner_clock')
            current=one([t for t in view['trays'] if t['tray_id']=='L'],'current_local_L')
            expected_phase=(6,'empty','') if owner=='A' else (7,'loaded','reuse1')
            require((current['node'],current['mode'],current['business_bag_id'])==expected_phase and current['edge_to']<0,'uncommitted_current_L')
            action_id=decision['native_request_id'];route_ack=None
            if owner=='B' and action_id:
                payload=requests[action_id];route_ack=raw['outbox'][action_id]['ack']
                require(payload['owner_id']=='B' and payload['from']==7 and payload['next']==8 and
                    payload['expected_generation']==current['generation'] and payload['expected_traversal']==current['traversal_id'],'current_route_binding')
                require(route_ack['status']=='updated' and route_ack['executed_at']==decision['at']+.01 and route_ack['delivered_at']==route_ack['executed_at']+.02,'route_wire_ack')
            future_available=[{'source':local['source_owner'],'tray_id':t['tray_id'],'mode':t['mode'],'available_at':t['available_at'],
                'service_ready_at':t['service_ready_at'],'load_complete_at':t['load_complete_at'],'ready_kind':t['ready_kind']} for local in locals_ for t in local['trays'] if t['available_at']>floor]
            stage_rows.append({'owner':owner,'phase':decision['phase'],'collection_start':decision['collection']['at'],
                'capture_times':{r['source_owner']:r['captured_at'] for r in locals_},'capture_union_floor':floor,'decision_at':decision['at'],
                'verified':info['native_delivery_verified'],'reasons':info.get('reasons'),'model_reasons':info.get('bundle',{}).get('reasons'),
                'fallback_used':decision['fallback_used'],'selected_action_admitted':decision['selected_action_admitted'],
                'actual_request_id':action_id,'route_ack':route_ack,'physical_ACKs_before_floor':actions,'future_available_captures':future_available})
        preflight=one([r for r in raw['exchanges']['B'] if r['kind']=='preflight_from_local_loading'],'preflight')
        refresh=one([r for r in raw['exchanges']['A'] if r['kind']=='immutable_ack_refresh_before_reply'],'preflight_refresh')
        reply=one([r for r in raw['exchanges']['A'] if r['kind']=='reply_after_delivered_received_ack'],'received_reply')
        require(preflight['at']==events(raw,'LOAD_START','reuse1','L')[0]['time'],'preflight_actual_loading')
        refresh_id=one(refresh['request_ids'],'one_refresh_request')
        retry=one([c for c in raw['calls'] if c['request']['request_id']==refresh_id and c['at']==refresh['at']],'actual_preflight_retry')
        require(retry['retry'] is True,'immutable_retry_flag')
        reply_ack=reply['causal']['delivered_terminal_acknowledgements'][refresh_id]
        require(reply_ack['status']=='received' and reply_ack['delivered_at']==reply['at']<stage_rows[1]['capture_union_floor'],'preflight_ack_before_fresh_pair')
        reuse_edges=[{k:r[k] for k in ('time','from','to')} for r in events(raw,'EDGE_ENTER','reuse1','L')]
        initial_edge=one([r for r in events(raw,'EDGE_ENTER','loaded','L') if r['from']==0],'initial_edge')
        require(reuse_edges[0]['to']==(8 if row['vector']['later_action']=='prefer_8' else 3),'actual_chosen_later')
        rows[key]={'raw_artifact':artifact,'producer_status':row['status'],'assessment_preserved':rebuilt['status'],
            'endpoint_replay':'passed','physical_replay':rebuilt['audit'],'whole_five_complete':True,'initial_inputs_verified':initial_known,
            'stages':stage_rows,'preflight':{'local_loading':preflight['at'],'captured_at':refresh['message']['capture']['capture_v2']['local_capture']['captured_at'],
                'delivered_and_retry_at':refresh['at'],'received_ack':reply_ack,'reply_at':reply['at']},
            'initial_actual_edge':{k:initial_edge[k] for k in ('time','from','to')},'first_reuse_actual_edges':reuse_edges,
            'P_storage':{'enter':p_enter['time'],'release':p_release['time'],'path':p_path,'edges':[{k:r[k] for k in ('time','from','to')} for r in events(raw,'EDGE_ENTER','blocker','P')]},
            **diagnostic,'reported_strict_protection':None}
    baseline=rows[producer.ORDER[0]]['actual_completion']
    for row in rows.values():
        row['observed_only_delta_vs_executed_baseline']={j:row['actual_completion'][j]-baseline[j] for j in baseline}
        row['observed_only_all_jobs_nondegraded']=all(row['actual_completion'][j]<=baseline[j] for j in baseline)
    for path,digest in pins.items():require(sha(path)==digest,'exit_pin:'+path)
    return {'schema':'g31.live_obligation_native_saved_review.v1','status':'verified_three_physical_completions_but_three_input_unknowns',
        'producer_receipt':ref(folder/'receipt.json'),'plan':ref(folder/'preregistered_protocol.json'),
        'ledger':ref(folder/'branch_ledger.json'),'runtime_acceptance':ref(folder/'run_acceptance.json'),
        'external_wall':ref(folder/'external_application_wall.json'),'pure96_receipt':ref(pure_dir/'receipt.json'),
        'source_pins':len(plan['source_sha256']),'closure_pins':len(admission['evidence_sha256']),'all_pins_entry_exit_match':True,
        'denominator':3,'assessed':0,'unknown':3,'all_per_job_times_exactly_match_corresponding_saved_pure003':True,'rows':rows,
        'diagnosis':'Generic tray available_at<=union-floor guard rejects E loading; native v1 capture intentionally substitutes observed load completion into available_at (planning_snapshot_impl.hpp:88). At every first return E has future available_at==service_ready_at==load_complete_at. Source guard line94 applies a past epoch check before its otherwise supported E loading case. No later-stage guard failed.',
        'next_causal_question':'Versioned typed loading capture correction, retaining equality to observed completion, future ready bound and start-before-union proof; rerun same three only after review. Existing three statuses remain unknown, despite actual later route and exact whole-job outcomes.',
        'limits':['Only three fixed actions; no complete16/32/96 native reference families','First R2 was lawful current-local fallback, not the selected information-qualified counterfactual','Observed nondegradation is descriptive; full declared-policy/protection gate remains unknown','No native or predictor execution in this audit; saved endpoint/physical replay only','No novelty, online optimization, current-state synchronization, or100ms claim'],
        'audit_source':ref(__file__),'native_executions':0,'model_evaluations':0,'elapsed_wall_seconds':time.perf_counter()-started}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--folder',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();require(not args.output.exists(),'immutable_output');report=audit(args.folder.resolve())
    args.output.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'status':report['status'],'output':ref(args.output),'elapsed':report['elapsed_wall_seconds']}))
