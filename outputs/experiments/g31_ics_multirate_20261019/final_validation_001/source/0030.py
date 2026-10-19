"""Independent saved96 audit. No native session, predictor or policy oracle."""
from __future__ import annotations
import copy, gzip, hashlib, json, math, time, traceback
from collections import Counter
from pathlib import Path
from . import research_live_obligation_recollection_v2 as c
from . import verify_live_obligation_recollection_v2 as saved

FOLDER=c.OUT/'live_obligation_recollection_native_v2_prepare_001'
OLD=c.OUT/'live_obligation_recollection_native_prepare_001'
TARGET=c.OUT/'live_obligation_recollection_native_v2_saved_review_001.json'
PLAN_SHA='f0db13dfee5ba0329664137cbcb1ef1452dc18be785950423cc8a7b6e020f6f8'
OLD_RECEIPT_SHA='c39e537d40b5a1dbcc09359aad490ffc266e286d41af7d658c769faf9643b8a5'
require,sha,read,ref=c.require,c.sha,c.read,c.reference


def one(rows, reason):
    require(len(rows)==1,reason)
    return rows[0]


def events(raw,name,job=None,tray=None):
    return [r for r in raw['result']['receipts'] if r['event']==name
        and (job is None or r['business_bag_id']==job) and (tray is None or r['tray_id']==tray)]


def physical_facts(raw):
    summary=raw['summary']
    times=saved.old.verify_terminal_receipts(raw)
    facts={'full_H40':summary.get('common_horizon_complete') is True,
        'all_five_complete':all(t is not None for t in times.values()),'completion':times,
        'audit':summary.get('audit'), 'initial_actual_next':summary.get('initial_actual_next'),
        'first_reuse_actual_next':summary.get('first_reuse_actual_next'),
        'route_acks':summary.get('route_acks'), 'returns':[]}
    if not facts['all_five_complete']: return facts
    enter=one(events(raw,'STORAGE_ENTER','blocker','P'),'P_storage_enter')
    release=one(events(raw,'STORAGE_RELEASE','blocker','P'),'P_storage_release')
    job=one([j for j in raw['input']['jobs'] if j['business_bag_id']=='blocker'],'P_job')
    require(enter['node']==release['node']==9 and release['time']==max(job['storage_release_at'],
        enter['time']+job['storage_min_dwell']),'P_mandatory_storage')
    require([(e['from'],e['to']) for e in events(raw,'EDGE_ENTER','blocker','P')]==[(1,9),(9,3),(3,10)],'P_actual_path')
    facts['P_storage']={'enter':enter,'release':release}
    for key in ('reuse1','reuse2'):
        require(len(events(raw,'LOAD_START',key,'L'))==1,'same_tray_reuse:'+key)
    for index,record in enumerate(raw['continuation']['returns']):
        rid=record['request_id']; request=raw['outbox'][rid]['request']; ack=raw['outbox'][rid]['ack']
        received=one([e for e in events(raw,'EMPTY_RECEIVED',tray='L') if e['reason']==rid],'return_receipt')
        require(ack['status']=='received' and ack['received_at']==received['time']<=ack['delivered_at']<=40.,'return_final_ack')
        selected=raw['specification']['vector']['return_delay'] if index==0 else 0.
        expected=c.prior.return_earliest(record['at'],selected,index)
        facts['returns'].append({'request_id':rid,'issue_at':record['at'],'earliest_departure':request['earliest_departure'],
            'expected_earliest_departure':expected,'matches_fixed_action':request['earliest_departure']==expected,
            'received_at':received['time'],'ack':ack})
    facts['actual_edges']=[{k:e[k] for k in ('time','business_bag_id','tray_id','from','to')}
                           for e in events(raw,'EDGE_ENTER')]
    return facts


def attempt_facts(raw):
    result=[]
    for owner,rows in raw['collection_attempts'].items():
        for item in rows:
            info=item['information']; pending=item['collection']
            entry={'owner':owner,'phase':item['phase'],'at':item['at'],'collection_started_at':pending['at'],
                'policy_quiet_since':pending['policy_quiet_since'],'index':pending['recollection_index'],
                'request_id':pending['request_id'],'peer_message_id':pending['peer_message'],
                'information_status':info['status'],'native_delivery_verified':info.get('native_delivery_verified'),
                'reasons':info.get('reasons',[]),'bundle_reasons':info.get('bundle',{}).get('reasons',[]),
                'retry_admission':item['retry_admission'],'disposition':item.get('disposition')}
            if 'raw_endpoints' in info:
                ep=info['raw_endpoints']; ack=ep['command'].get('last_delivered_ack',{})
                envelope=ack.get('planning_snapshot_v3')
                selected=[e for e in ep['received'] if e['capture']['capture_v2']['local_capture']['message_id']==pending['peer_message']]
                if envelope and len(selected)==1:
                    bodies=[e['capture']['capture_v2']['local_capture'] for e in (envelope,selected[0])]
                    entry['actual_pair']=[{'source_owner':b['source_owner'],'message_id':b['message_id'],
                        'captured_at':b['captured_at'],'delivered_at':e['delivered_at'],'valid_until':b['valid_until']}
                        for e,b in zip((envelope,selected[0]),bodies,strict=True)]
                    entry['capture_union_floor']=min(b['captured_at'] for b in bodies)
                    entry['own_delivered_ack']=ack
            if item.get('new_request_id'):
                key=item['new_request_id']; row=raw['outbox'][key]
                entry['new_request']={'request':row['request'],'final_ack':row['ack'],
                    'creation':raw['request_creations'][key]}
            result.append(entry)
    return result


def audit():
    start=time.perf_counter(); require(not TARGET.exists(),'immutable_audit')
    require(sha(FOLDER/'preregistered_protocol.json')==PLAN_SHA,'fixed_plan')
    require(sha(OLD/'receipt.json')==OLD_RECEIPT_SHA,'old_receipt')
    plan=read(FOLDER/'preregistered_protocol.json'); receipt=read(FOLDER/'receipt.json')
    rows=read(FOLDER/'branch_ledger.json'); acceptance=read(FOLDER/'run_acceptance.json')
    external=read(FOLDER/'external_process.json')
    require(external['status']=='exited' and external['exitcode']==0 and external['windows_job_kill_on_close'] is True,'bounded_child_terminal')
    require(receipt['plan_sha256']==PLAN_SHA and receipt['ledger_sha256']==sha(FOLDER/'branch_ledger.json')
        and receipt['run_acceptance']==ref(FOLDER/'run_acceptance.json'),'producer_hashes')
    require(receipt['status'] in ('complete96_assessed','completed_with_unknowns') and
        receipt['source_changed']==receipt['source_closure_changed']==[],'producer_final_status')
    require(list(rows)==plan['branch_order']==receipt['branch_order']==c.ORDER and len(rows)==96
        and receipt['branch_count']==receipt['native_branch_attempts']==96,'all96_denominator_order')
    require(plan['hard_timeout_seconds']==600. and plan['common_horizon']==40.
        and plan['strict_protection_tolerance']==0. and plan['rows']==c.prior.probe_rows(),'fixed_contract')
    c.prior.domain_contract.validate_rows(rows)
    require(acceptance['status']=='closed_run_acceptance_passed' and acceptance['active'] is False
        and acceptance['invalid']==[] and acceptance['branch_keys']==sorted(c.ORDER)
        and acceptance['run_reference']==ref(FOLDER/'preregistered_protocol.json'),'accepted_run_closed')
    phases=Counter(item['phase'] for item in acceptance['costs'])
    require(phases['run_entry_closed_verifiers']==phases['run_exit_closed_verifiers']==1,'entry_exit44_21')
    pins={**plan['source_sha256'],**acceptance['evidence_sha256'],str(Path(__file__)):sha(__file__)}
    for path,digest in plan['source_sha256'].items():
        require(sha(FOLDER/plan['source_archive'][path])==digest,'source_archive')
        require(path not in acceptance['evidence_sha256'] or acceptance['evidence_sha256'][path]==digest,'pin_collision')
    for path,digest in pins.items(): require(sha(path)==digest,'entry_pin:'+path)
    for reference in plan['auxiliary_references'].values(): require(sha(reference['path'])==reference['sha256'],'auxiliary_pin')
    old_receipt=read(OLD/'receipt.json');old_rows=read(OLD/'branch_ledger.json')
    require(sha(OLD/'branch_ledger.json')==old_receipt['ledger_sha256'],'old_ledger')
    status=Counter(); transition=Counter(); stages=Counter(); reasons=Counter(); failures={}; detail={}
    physical=Counter();fresh=Counter();actual_pairs=Counter()
    for index,key in enumerate(c.ORDER):
        row=rows[key];status[row['status']]+=1;transition[(old_rows[key]['status'],row['status'])]+=1
        require(row['execution_index']==index and phases['branch_entry:'+key]==phases['branch_exit:'+key]==1,'branch_boundary:'+key)
        artifact=row.get('raw_artifact')
        if artifact is None:
            require(row['status']!='assessed' and row.get('exception'),'missing_raw_assessed')
            detail[key]={'old_status':old_rows[key]['status'],'new_status':row['status'],'missing_raw':True};continue
        require(sha(artifact['path'])==artifact['sha256'],'raw_hash:'+key)
        raw=json.loads(gzip.decompress(Path(artifact['path']).read_bytes()))
        require(all(raw['specification'][f]==plan['rows'][key][f] for f in ('case','vector','method','fault')),'raw_action:'+key)
        inp=FOLDER/'inputs'/(key+'.json')
        require(sha(inp)==plan['input_file_sha256'][key] and read(inp)==raw['input']==c.prior.native_scene(row['case']),'input_identity:'+key)
        require(raw['summary']==row['summary'],'summary_identity:'+key)
        validation=None;error=None
        try:
            validation=saved.verify_partial(raw) if raw.get('partial') is True else saved.verify_saved(raw)
            require(validation==row['saved_replay'],'saved_replay_identity:'+key)
            require(row['status']==raw['summary']['status'],'assessor_status:'+key)
        except Exception:
            error=traceback.format_exc();failures[key]=error
        facts=physical_facts(raw) if raw.get('result') and raw.get('continuation') else {'all_five_complete':False,'full_H40':False}
        physical['full_H40']+=int(facts['full_H40']);physical['all_five_complete']+=int(facts['all_five_complete'])
        attempts=attempt_facts(raw)
        for entry in attempts:
            stages[entry['information_status']]+=1;reasons.update(entry['reasons']);reasons.update(entry['bundle_reasons'])
            if entry['disposition']=='one_fresh_pair_requested':fresh[entry['owner']]+=1
            if entry['index']==1:actual_pairs[entry['information_status']]+=1
        detail[key]={'raw':artifact,'old_status':old_rows[key]['status'],'new_status':row['status'],
            'independent_replay':validation,'independent_error':error,'physical':facts,'attempts':attempts,
            'selected_actions_executed':raw['summary'].get('selected_actions_executed'),
            'all_required_inputs_verified':raw['summary'].get('all_required_inputs_verified'),
            'all_old_unknowns_preserved_in_original_campaign':True}
    comparison=c.comparisons(rows)
    require(comparison==receipt['comparisons'],'finite_reference_comparisons')
    for path,digest in pins.items():require(sha(path)==digest,'exit_pin:'+path)
    return {'schema':'g31.recollection_v2_saved_independent_review.v1',
        'status':'verified_saved96_unknowns_preserved' if not failures else 'saved96_replay_failures_preserved',
        'plan':ref(FOLDER/'preregistered_protocol.json'),'receipt':ref(FOLDER/'receipt.json'),
        'ledger':ref(FOLDER/'branch_ledger.json'),'run_acceptance':ref(FOLDER/'run_acceptance.json'),
        'external_process':ref(FOLDER/'external_process.json'),'external_application_wall':ref(FOLDER/'external_application_wall.json'),
        'old_receipt':ref(OLD/'receipt.json'),'auditor_source':ref(__file__),
        'source_pins':len(plan['source_sha256']),'all_entry_exit_pins':len(pins),
        'all96_denominator':True,'status_counts':dict(status),'old_to_new_status':{str(k):v for k,v in transition.items()},
        'physical_counts':dict(physical),'information_status_counts':dict(stages),'information_reasons':dict(reasons),
        'fresh_pair_submissions_by_owner':dict(fresh),'actual_second_collection_status':dict(actual_pairs),
        'independent_replay_errors':failures,'comparisons':comparison,'rows':detail,
        'limits':['Actual fixed-action counterfactuals, not online optimization or a native-oracle policy.',
            'Original52/44 results unchanged. New policy may shift physical times, so old normal-exchange model conformance is not assumed.',
            'Any incomplete16 family/full32 domain remains unknown. Strict per-job <=0 uses no tolerance.',
            'Source-state stability remains conditional; no atomic joint agreement, original-airport improvement, novelty or complete-request100ms claim.',
            'Saved audit does not create native authority or independently replay the native event engine.'],
        'native_executions':0,'model_evaluations':0,'audit_wall_seconds':time.perf_counter()-start}


if __name__=='__main__':
    value=audit();TARGET.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'report':ref(TARGET),'status':value['status'],'counts':value['status_counts'],
        'fresh_pairs':value['fresh_pair_submissions_by_owner'],'second':value['actual_second_collection_status'],
        'replay_errors':len(value['independent_replay_errors']),'wall':value['audit_wall_seconds']}))
