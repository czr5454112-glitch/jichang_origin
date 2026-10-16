"""Saved fixed96 readback only; no NativeSession and no model prediction.

Replays supplied endpoint guards and independent physical assessor, while
retaining every producer unknown and exact point differences from saved pure96.
"""
from __future__ import annotations
import gzip,hashlib,json,math,time
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from . import research_live_obligation_native_domain as p

ROOT,OUT=p.ROOT,p.OUT
FOLDER=OUT/'live_obligation_native_domain_prepare_001'
PURE=OUT/'live_obligation_projection_prepare_003'
TARGET=OUT/'live_obligation_native_domain_saved_review_001.json'
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def require(value,why):
    if not value:raise ValueError('saved96:'+why)
def one(rows,why):require(len(rows)==1,why);return rows[0]
def events(raw,event,job=None,tray=None):
    return [r for r in raw['result']['receipts'] if r['event']==event and
        (job is None or r['business_bag_id']==job) and (tray is None or r['tray_id']==tray)]
def compact_tray(t):
    fields=('tray_id','node','mode','business_bag_id','edge_from','edge_to','reception_node',
        'generation','traversal_id','available_at','service_ready_known','service_ready_at',
        'ready_kind','load_complete_at','committed_prefix')
    return {k:t.get(k) for k in fields}

def stage(raw,owner,d):
    info=d['information'];endpoint=info['raw_endpoints']
    own_ack=endpoint['command']['last_delivered_ack']
    selected=info['selected_peer_message_id']
    peers=[e for e in endpoint['received'] if e['capture']['capture_v2']['local_capture']['message_id']==selected]
    require(len(peers)==1,'selected_peer_'+owner)
    envelopes=[own_ack['planning_snapshot_v3'],*peers]
    local=[e['capture']['capture_v2']['local_capture'] for e in envelopes]
    require({x['source_owner'] for x in local}=={'A','B'},'stage_sources')
    floor=min(x['captured_at'] for x in local)
    captures=[];action_rows=[];terminal=[]
    for envelope,body in zip(envelopes,local,strict=True):
        require(d['collection']['at']<=body['captured_at']<=envelope['delivered_at']<=d['at']<body['valid_until'],'stage_chronology')
        require(d['at']-body['captured_at']<=.05,'stage_capture_age')
        extension=envelope['capture']['capture_v2']['extension']
        actions=extension['submitted_physical_actions']
        for a in actions:
            ack=a['last_delivered_ack']
            action_rows.append({'source_owner':a['source_owner'],'request_id':a['request_id'],'kind':a['kind'],
                'status':ack.get('status'),'delivered_at':ack.get('delivered_at'),
                'strictly_before_union':type(ack.get('delivered_at')) in (int,float) and 0<=ack['delivered_at']<floor})
        terminal.extend(extension['terminal_receipts'])
        captures.append({'source_owner':body['source_owner'],'message_id':body['message_id'],
            'captured_at':body['captured_at'],'delivered_at':envelope['delivered_at'],
            'trays':[compact_tray(t) for t in body['trays']],
            'jobs':[{k:j[k] for k in ('business_bag_id','status','loaded_at','storage_entered_at','storage_released_at')} for j in body['jobs']],
            'inflight':envelope['capture']['extension']['source_observed_inflight']})
    view=d['actual_local_view'];require(view==endpoint['view'] and view['owner_id']==owner and view['now']==d['at'],'actual_local_current')
    current=one([t for t in view['trays'] if t['tray_id']=='L'],'local_L')
    expected=(6,'empty','') if owner=='A' else (7,'loaded','reuse1')
    require((current['node'],current['mode'],current['business_bag_id'])==expected and current['edge_to']<0,'current_L_uncommitted')
    rid=d['native_request_id'];ack=raw['outbox'][rid]['ack'] if rid else None
    if owner=='B' and rid:
        request=raw['outbox'][rid]['request']
        require(all(request[k]==v for k,v in {'owner_id':'B','tray_id':'L','business_bag_id':'reuse1','from':7,'next':8,
            'expected_generation':current['generation'],'expected_traversal':current['traversal_id']}.items()),'actual_route_identity')
    return {'owner':owner,'phase':d['phase'],'at':d['at'],'collection_start':d['collection']['at'],
        'capture_union_floor':floor,'information_status':info['status'],'verified':info['native_delivery_verified'],
        'reasons':info.get('reasons',[]),'bundle_reasons':info.get('bundle',{}).get('reasons',[]),
        'fallback_used':d['fallback_used'],'selected_action_admitted':d['selected_action_admitted'],
        'actual_request_id':rid,'actual_ack':ack,'current_L':compact_tray(current),
        'source_captures':captures,'physical_action_acks':action_rows,'delivered_terminal_receipts':terminal}

def audit():
    started=time.perf_counter();plan=read(FOLDER/'preregistered_protocol.json');receipt=read(FOLDER/'receipt.json')
    ledger=read(FOLDER/'branch_ledger.json');admission=read(FOLDER/'run_acceptance.json')
    pins={**plan['source_sha256'],**admission['evidence_sha256']}
    for path,h in pins.items():require(sha(path)==h,'entry_pin:'+path)
    for path,h in plan['source_sha256'].items():require(sha(FOLDER/plan['source_archive'][path])==h,'archive:'+path)
    for name in ('preregistered_protocol.json','branch_ledger.json','run_acceptance.json'):
        expected={'preregistered_protocol.json':receipt['plan_sha256'],'branch_ledger.json':receipt['ledger_sha256'],
            'run_acceptance.json':receipt['run_acceptance']['sha256']}[name]
        require(sha(FOLDER/name)==expected,'producer_hash:'+name)
    require(receipt['status']=='completed_with_unknowns' and receipt['source_changed']==[],'producer_status')
    require(plan['branch_order']==list(ledger)==receipt['branch_order']==p.ORDER and len(ledger)==96,'all96_order')
    require(receipt['branch_count']==receipt['native_branch_attempts']==96,'all96_attempts')
    p.domain_contract.validate_rows(ledger)
    require(admission['status']=='closed_run_acceptance_passed' and admission['active'] is False and admission['invalid']==[],'closed_acceptance')
    phases=[x['phase'] for x in admission['costs']]
    require(phases.count('run_entry_closed_verifiers')==phases.count('run_exit_closed_verifiers')==1,'entry_exit44_21')
    pure_ledger=read(PURE/'branch_ledger.json');rows={};reason_counts=Counter();bundle_counts=Counter();stage_failures=Counter()
    equal=Counter();status=Counter();edge_counts=Counter();source_before=sha(__file__)
    for index,key in enumerate(p.ORDER):
        row=ledger[key];require(row['execution_index']==index,'execution_index')
        require(phases.count('branch_entry:'+key)==phases.count('branch_exit:'+key)==1,'branch_pin_pair')
        artifact=row['raw_artifact'];require(sha(artifact['path'])==artifact['sha256'],'raw_hash:'+key)
        raw=json.loads(gzip.decompress(Path(artifact['path']).read_bytes()))
        require(raw.get('partial') is not True and raw['specification']['vector']==plan['rows'][key]['vector']==row['vector'],'raw_binding')
        inp=FOLDER/'inputs'/(key+'.json');require(sha(inp)==plan['input_file_sha256'][key] and read(inp)==raw['input'],'input_binding')
        p.validate_runtime_input(raw['input']);p.verify_saved_inputs(raw)
        rebuilt=p.completed_summary(raw['input'],raw['result'],SimpleNamespace(rows=raw['outbox'],calls=raw['calls']),
            raw['continuation'],row['vector'],raw['initial_owners'],raw['decisions'])
        require(rebuilt==row['summary']==raw['summary'] and row['status']==rebuilt['status'],'full_assessor:'+key)
        require(rebuilt['common_horizon_complete'] and rebuilt['audit']['status']=='passed','physical_fullH')
        jobs={j['business_bag_id']:j for j in raw['result']['jobs']};require(set(jobs)==p.model.JOBS and len(raw['result']['jobs'])==5,'five_jobs')
        actual={}
        for jid,j in jobs.items():
            final=one(events(raw,'UNLOAD_COMPLETE',jid),'one_terminal:'+jid)
            require(j['status']=='completed' and type(j['completed_at']) in (int,float) and math.isfinite(j['completed_at']) and 0<=j['completed_at']==final['time']<=40.,'actual_terminal')
            actual[jid]=j['completed_at']
        pe=one(events(raw,'STORAGE_ENTER','blocker','P'),'P_enter');pr=one(events(raw,'STORAGE_RELEASE','blocker','P'),'P_release')
        pj=one([j for j in raw['input']['jobs'] if j['business_bag_id']=='blocker'],'P_contract')
        require(pe['node']==pr['node']==9 and pr['time']==max(pj['storage_release_at'],pe['time']+pj['storage_min_dwell']),'P_mandatory')
        require([(r['from'],r['to']) for r in events(raw,'EDGE_ENTER','blocker','P')]==[(1,9),(9,3),(3,10)],'P_path')
        require(len(events(raw,'LOAD_START','reuse1','L'))==len(events(raw,'LOAD_START','reuse2','L'))==1,'same_L_reuse')
        requests={}
        for c in raw['calls']:
            rid=c['request']['request_id'];require(rid not in requests or requests[rid]==c['request'],'retry_identity');requests[rid]=c['request']
        actual_returns=[]
        for i,r in enumerate(raw['continuation']['returns']):
            rid=r['request_id'];request=requests[rid];ack=raw['outbox'][rid]['ack']
            arrival=one([x for x in events(raw,'EMPTY_RECEIVED',tray='L') if x['reason']==rid],'return_empty')
            require(ack['status']=='received' and ack['received_at']==arrival['time']<=ack['delivered_at']<=40.,'return_receipt')
            actual_returns.append({'index':i,'at':r['at'],'selected_delay':r['selected_delay'],'earliest_departure':request['earliest_departure'],
                'declared_earliest':p.return_earliest(r['at'],row['vector']['return_delay'] if i==0 else 0.,i),
                'actually_matches_declared':request['earliest_departure']==p.return_earliest(r['at'],row['vector']['return_delay'] if i==0 else 0.,i),
                'received_at':arrival['time'],'ack':ack})
        pure_row=pure_ledger['rows'][key];require(sha(pure_row['raw'])==pure_row['raw_sha256'],'pure_raw')
        pure=json.loads(gzip.decompress(Path(pure_row['raw']).read_bytes()));require(pure['action']==row['vector'],'pure_action')
        expected=pure['assessment']['completion'];diff={j:actual[j]-expected[j] for j in actual};matched=actual==expected
        equal['all_exact' if matched else 'has_difference']+=1;equal['assessed_exact' if row['status']=='assessed' and matched else 'other']+=1
        ds=[stage(raw,o,one(raw['decisions'][o],'one_later_per_owner')) for o in ('A','B')]
        for d in ds:
            if not d['verified']:
                stage_failures[d['owner']]+=1
                reason_counts.update(d['reasons']);bundle_counts.update(d['bundle_reasons'])
        initial=all(x['information']['native_delivery_verified'] is True for x in raw['initial_owners'].values())
        require(initial,'all_initial_verified')
        status[row['status']]+=1;edge_counts[(rebuilt['initial_actual_next'],rebuilt['first_reuse_actual_next'])]+=1
        rows[key]={'raw_artifact':artifact,'producer_status_preserved':row['status'],'endpoint_replay':'passed',
            'physical_replay':rebuilt['audit'],'all_five_physically_complete':True,'initial_inputs_verified':initial,
            'all_required_inputs_verified':rebuilt['all_required_inputs_verified'],'selected_actions_executed':rebuilt['selected_actions_executed'],
            'assessor_predicates':{k:v for k,v in rebuilt.items() if type(v) is bool},'stages':ds,'actual_returns':actual_returns,
            'actual_completion':actual,'saved_pure_completion':expected,'per_job_actual_minus_pure':diff,'all_five_times_exact':matched,
            'initial_actual_next':rebuilt['initial_actual_next'],'first_reuse_actual_next':rebuilt['first_reuse_actual_next'],
            'actual_route_acks':rebuilt['route_acks'],'P_storage_enter':pe,'P_storage_release':pr,
            'actual_edge_entries':[{k:r[k] for k in ('time','tray_id','business_bag_id','from','to')} for r in events(raw,'EDGE_ENTER')],
            'actual_terminal_receipts':events(raw,'UNLOAD_COMPLETE'),'business_metrics_promoted_from_unknown':False}
    comparison=p.comparisons(ledger,plan);require(comparison==receipt['comparisons'],'all_references_and_methods')
    for c in comparison['cases'].values():
        for family in c['references'].values():
            require(family['member_count']==len(family['members'])==16,'reference16')
            require(family['status']=='unknown_incomplete_reference' and family['best_key'] is None,'incomplete_family_kept_unknown')
    for path,h in pins.items():require(sha(path)==h,'exit_pin:'+path)
    require(sha(__file__)==source_before,'auditor_drift')
    return {'schema':'g31.live_obligation_native_domain_saved_review.v1','status':'verified_all96_saved_rows_preserving34_assessed62_unknown',
        'producer_receipt':ref(FOLDER/'receipt.json'),'plan':ref(FOLDER/'preregistered_protocol.json'),'ledger':ref(FOLDER/'branch_ledger.json'),
        'run_acceptance':ref(FOLDER/'run_acceptance.json'),'external_wall':ref(FOLDER/'external_application_wall.json'),
        'pure96_receipt':ref(PURE/'receipt.json'),'source_pins':len(plan['source_sha256']),'closure_pins':len(admission['evidence_sha256']),
        'all_pins_entry_exit_match':True,'denominator':96,'status_counts':dict(status),'unknown_stage_owners':dict(stage_failures),
        'unknown_first_layer_reasons':dict(reason_counts),'unknown_bundle_reasons':dict(bundle_counts),
        'all96_full40_physical_audit':True,'all480_job_terminal_times_validated':True,'pure_time_conformance':dict(equal),
        'edge_pair_counts':{str(k):v for k,v in edge_counts.items()},'comparisons_recomputed':comparison,'rows':rows,
        'limits':['Saved native receipts and endpoint data only; no new native run or model prediction.',
            'All62 unknowns remain unknown even when all five jobs physically completed.',
            'All six16-member native reference families remain incomplete; no full-native optimum or online optimizer result.',
            'Source-state stability remains conditional, not an atomic global current-state proof.',
            'Retrospective pure comparisons were used for semantic debugging, not held-out statistical validation.',
            'No novelty, original-airport improvement, global protection or complete-request100ms claim.'],
        'audit_source':ref(__file__),'native_executions':0,'model_evaluations':0,'elapsed_wall_seconds':time.perf_counter()-started}

if __name__=='__main__':
    require(not TARGET.exists(),'immutable_report');report=audit()
    TARGET.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'report':ref(TARGET),'status':report['status'],'counts':report['status_counts'],
        'bundle_reasons':report['unknown_bundle_reasons'],'pure_times':report['pure_time_conformance'],'wall':report['elapsed_wall_seconds']}))
