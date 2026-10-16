"""Independent saved96 review; never opens native or calls a predictor.

The established full readback is rebound privately to the new saved-endpoint
validator. Additional family arithmetic is independently recomputed from the
verified physical/authority facts, not from producer selection labels.
"""
from __future__ import annotations
import copy,json,math,sys,time
from collections import Counter
from pathlib import Path
from types import FunctionType,SimpleNamespace
from . import audit_live_obligation_recollection_v2 as prior
from . import research_live_obligation_unloading as c
from . import verify_live_obligation_unloading as saved

FOLDER=c.OUT/'live_obligation_unloading_native_prepare_001'
OLD=c.OUT/'live_obligation_historical_native_prepare_001'
TARGET=c.OUT/'live_obligation_unloading_native_saved_review_001.json'
PLAN_SHA='6c82cc7ad10aae82f2f9d9059899dca20753e4bf0f5a78885d2e53e505199ecd'
OLD_REVIEW=c.OUT/'live_obligation_historical_native_saved_review_001.json'
OLD_REVIEW_SHA='3ea06f5867e916bca10936c28134003e91a8cd0b0cb1f41b3a93c1eaa3321728'
MODEL=c.OUT/'live_obligation_projection_prepare_003'
MODEL_PLAN_SHA='03461658ebf717845dfbef8f23c0aba9417310971932d90ab769b7b62e1a2e0f'
MODEL_LEDGER_SHA='ca5e270390d9faa7e290351b58ff3511fe5eda45dde5a0e85a6d82826df550f7'
JOBS=('blocker','loaded','receiver','reuse1','reuse2')
require,sha,read,ref=c.require,c.sha,c.read,c.reference


def clone(function,namespace):
    result=FunctionType(function.__code__,namespace,function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__
    return result


def independent_families(plan,details):
    """Every family member, exact native terminal times and zero tolerance."""
    require(plan['branch_order']==c.ORDER and list(details)==c.ORDER,'independent96_order')
    def known(row):
        f=row.get('physical',{});times=f.get('completion',{})
        return (row['new_status']=='assessed' and row.get('independent_error') is None
            and row.get('independent_replay') is not None and not row.get('missing_raw')
            and f.get('full_H40') is True and f.get('all_five_complete') is True
            and f.get('audit',{}).get('status')=='passed'
            and row.get('all_required_inputs_verified') is True and row.get('selected_actions_executed') is True
            and set(times)==set(JOBS) and all(type(t) in (float,int) and math.isfinite(t) and 0<=t<=40 for t in times.values()))
    def compare(row,base):
        if not known(row) or not known(base):return {'status':'unknown','strict_protected':None,'delta':None}
        a,b=row['physical']['completion'],base['physical']['completion']
        return {'status':'assessed','strict_protected':all(a[j]<=b[j] for j in JOBS),
                'delta':{j:a[j]-b[j] for j in JOBS}}
    def score(key):return sum(details[key]['physical']['completion'][j] for j in JOBS)
    cases={};incumbent={'initial_action':'native_default','empty_departure':2.2100000000000004,
                       'return_delay':0.,'later_action':'native_default'}
    for case in c.CASE_ORDER:
        keys=[k for k in c.ORDER if plan['rows'][k]['case']==case]
        bases=[k for k in keys if plan['rows'][k]['vector']==incumbent]
        require(len(keys)==32 and len(bases)==1,'independent_case32_incumbent')
        basekey=bases[0];base=details[basekey];refs={}
        for name,field in (('fixed_initial_native_default','initial_action'),('later_native_default','later_action')):
            members=[k for k in keys if plan['rows'][k]['vector'][field]=='native_default']
            require(len(members)==16,'independent_family16')
            complete=known(base) and all(known(details[k]) for k in members)
            eligible=[k for k in members if complete and compare(details[k],base)['strict_protected'] is True]
            best=min(eligible,key=lambda k:(score(k),k),default=None)
            refs[name]={'status':'complete_native_finite_reference' if complete else 'unknown_incomplete_reference',
                'members':members,'member_count':16,'assessed_members':sum(known(details[k]) for k in members),
                'best_key':best,'best_sum':score(best) if best else None}
        complete=all(known(details[k]) for k in keys)
        eligible=[k for k in keys if complete and compare(details[k],base)['strict_protected'] is True]
        best=min(eligible,key=lambda k:(score(k),k),default=None)
        cases[case]={'incumbent_key':basekey,'assessed':sum(known(details[k]) for k in keys),
            'unknown':sum(not known(details[k]) for k in keys),'references':refs,
            'full32_finite_optimum':best,'rows_vs_incumbent':{k:compare(details[k],base) for k in keys}}
    return cases


def enriched_attempt_facts(raw):
    rows=prior.attempt_facts(raw)
    entries=[entry for owner in raw['collection_attempts'] for entry in raw['collection_attempts'][owner]]
    require(len(rows)==len(entries),'all_collection_attempt_facts')
    for row,entry in zip(rows,entries,strict=True):
        info=entry['information'];bundle=info.get('bundle',{})
        row['actual_publication_ledger']=copy.deepcopy(info.get('actual_publication_ledger'))
        row['derived_goal_service_bounds']=copy.deepcopy(bundle.get('derived_goal_service_bounds',{}))
        row['historical_goal_service_check']=copy.deepcopy(info.get('historical_goal_service_check'))
        row['actual_current_local_L']=[copy.deepcopy(t) for t in entry.get('actual_local_view',{}).get('trays',[]) if t['tray_id']=='L']
        row['supported_captured_L']=copy.deepcopy(bundle.get('trays',{}).get('L'))
        row['conditional_stability_only']=info.get('conditional_stability_only')
        row['current_state_certified']=info.get('current_state_certified')
        row['unloading_failed_read_fact']=copy.deepcopy(entry.get('retry_admission',{}).get('crossed_source_fact'))
        if row['unloading_failed_read_fact']:
            sequence=raw['collection_attempts'][row['owner']]
            next_rows=[candidate for candidate in sequence
                if candidate['collection']['recollection_index']==row['index']+1]
            require(len(next_rows)<=1,'unique_unloading_fresh_followup')
            final=next_rows[0] if next_rows else None
            row['unloading_fresh_outcome']={'actual_next_collection_recorded':final is not None,
                'known_final_input':False,'actual_received_receiver_terminal_receipts':[]}
            if final:
                f=final['information'];ep=f.get('raw_endpoints',{});pending=final['collection']
                selected=[m for m in ep.get('received',[]) if
                    m['capture']['capture_v2']['local_capture']['message_id']==pending['peer_message']]
                require(len(selected)<=1,'unique_fresh_peer')
                terminal=[]
                for message in selected:
                    capture=message['capture']['capture_v2'];source=capture['local_capture']
                    for receipt in capture['extension']['terminal_receipts']:
                        if receipt['business_bag_id']=='receiver':
                            terminal.append({'source_owner':source['source_owner'],
                                'message_id':source['message_id'],'captured_at':source['captured_at'],
                                'delivered_at':message['delivered_at'],'receipt':copy.deepcopy(receipt)})
                known=f.get('status')=='conditional_native_delivered_later_v3_model_input'
                if known:
                    require(len(terminal)==1 and terminal[0]['source_owner']=='A','known_fresh_receiver_terminal')
                    native=[r for r in raw['result']['receipts'] if
                        r['event']=='UNLOAD_COMPLETE' and r['business_bag_id']=='receiver' and r['tray_id']=='E']
                    require(len(native)==1 and terminal[0]['receipt']['completed_at']==native[0]['time'],
                            'fresh_terminal_matches_actual_unload')
                row['unloading_fresh_outcome']={'actual_next_collection_recorded':True,
                    'at':final['at'],'request_id':pending['request_id'],'peer_message_id':pending['peer_message'],
                    'known_final_input':known,'information_status':f.get('status'),
                    'reasons':f.get('reasons',[]),'bundle_reasons':f.get('bundle',{}).get('reasons',[]),
                    'actual_received_receiver_terminal_receipts':terminal,
                    'final_current_L':[copy.deepcopy(t) for t in final.get('actual_local_view',{}).get('trays',[]) if t['tray_id']=='L']}
    return rows


def namespace(old_receipt_sha):
    # Old physical helper uses saved.old only for its terminal-receipt checker.
    proxy=SimpleNamespace(**{**vars(saved),'old':saved.old})
    ns={**vars(prior),'__file__':__file__,'c':c,'saved':proxy,'FOLDER':FOLDER,'OLD':OLD,'TARGET':TARGET,
        'PLAN_SHA':PLAN_SHA,'OLD_RECEIPT_SHA':old_receipt_sha,'attempt_facts':enriched_attempt_facts}
    ns['physical_facts']=clone(prior.physical_facts,ns)
    return ns


def loaded_sources():
    paths={Path(__file__).resolve(),c.ROOT/'pyproject.toml'}
    for module in tuple(sys.modules.values()):
        value=getattr(module,'__file__',None)
        if value:
            path=Path(value).resolve()
            if path.is_file() and path.is_relative_to(c.ROOT) and path.suffix=='.py':paths.add(path)
    return {str(p):sha(p) for p in sorted(paths)}


def compact_summary(report):
    """Small verified-raw arithmetic; incomplete references never get a best."""
    cases={}
    for case,data in report['independently_recomputed_cases'].items():
        best=data['full32_finite_optimum'];detail=report['rows'];refs={}
        for name,item in data['references'].items():
            control=item['best_key'];delta=None
            if best is not None and control is not None:
                a=detail[best]['physical']['completion'];b=detail[control]['physical']['completion']
                delta={j:a[j]-b[j] for j in JOBS}
            refs[name]={k:item[k] for k in ('status','member_count','assessed_members','best_key','best_sum')}
            refs[name].update(best32_minus_reference=delta,
                best32_strictly_protected=all(v<=0 for v in delta.values()) if delta is not None else None)
        cases[case]={'assessed':data['assessed'],'unknown':data['unknown'],
            'full32_finite_optimum':best,'best_completion':detail[best]['physical']['completion'] if best else None,
            'references':refs}
    return {'schema':'g31.unloading_actual96_compact_summary.v1','status':report['status'],
        'status_counts':report['status_counts'],'physical_counts':report['physical_counts'],
        'old94_to_new_status':report['old_to_new_status'],
        'actual_fresh_pair_submissions':report['fresh_pair_submissions_by_owner'],
        'actual_second_collection_status':report['actual_second_collection_status'],
        'information_status_counts':report['information_status_counts'],
        'remaining_unknown_branches':[k for k,v in report['rows'].items() if v['new_status']!='assessed'],
        'remaining_unknown_reasons':report['unknown_attempt_reasons'],
        'actual_unloading_recollection_outcomes':report['actual_unloading_recollection_outcomes'],
        'independent_replay_error_count':len(report['independent_replay_errors']),
        'cases':cases,'run_references':{k:report[k] for k in ('plan','receipt','ledger','run_acceptance',
            'external_process','external_application_wall','previous_independent_actual_review')},
        'native_executions_by_auditor':0,'model_evaluations_by_auditor':0,
        'limits':['Fixed-action counterfactuals; no online optimizer or method-necessity claim.',
            'Strict per-job <=0; an incomplete sixteen-member reference or full32 domain stays unknown.',
            'Fresh eligibility never supplies a terminal receipt; actual new delivered endpoint verification is required.',
            'Original94/2 remains unchanged. No original-airport, atomic-state or100ms certification.']}


def audit():
    start=time.perf_counter();require(not TARGET.exists(),'immutable_independent_audit')
    require(sha(OLD_REVIEW)==OLD_REVIEW_SHA,'old94_2_review')
    old_review=read(OLD_REVIEW)
    require(old_review['status']=='verified_saved96_unknowns_preserved' and not old_review['independent_replay_errors'],'old94_2_review_status')
    require(sha(MODEL/'preregistered_protocol.json')==MODEL_PLAN_SHA
            and sha(MODEL/'branch_ledger.json')==MODEL_LEDGER_SHA,'frozen_conditional_model_reference')
    extra_pins=loaded_sources()
    model=read(MODEL/'branch_ledger.json');model_plan=read(MODEL/'preregistered_protocol.json')
    require(model['execution_order']==c.ORDER and model['executed']==96 and set(model['rows'])==set(c.ORDER),'model_reference96')
    plan=read(FOLDER/'preregistered_protocol.json')
    require(plan['schema']==c.SCHEMA and plan['source_sha256'] and len(plan['source_sha256'])==93,'new_campaign_schema')
    receipt=read(FOLDER/'receipt.json');external=read(FOLDER/'external_process.json')
    app=read(FOLDER/'external_application_wall.json')
    require(receipt['schema']=='g31.live_obligation_unloading_fixed96_receipt.v1'
        and receipt['unloading_failed_read_amendment']==c.policy.VERSION
        and receipt['historical_own_client_binding'] is True,'new_history_worker_receipt')
    require(external['hard_timeout_seconds']==600. and external['child_released_only_after_job_assignment'] is True
        and type(external['wall_seconds']) in (int,float) and 0<=external['wall_seconds']<=600.,'owned600_actual_wall')
    require(app['status']=='application_exited_zero' and app['exit_code']==0 and app['plan_sha256']==PLAN_SHA
        and app['evidence_unchanged'] is True and type(app['whole_python_application_seconds']) in (int,float)
        and math.isfinite(app['whole_python_application_seconds'])
        and app['whole_python_application_seconds']>=external['wall_seconds'],'external_application_terminal_and_wall')
    for field in ('binary','interpreter','native_contract_reference','semantic_gate_reference'):
        p=plan[field];require(sha(p['path'])==p['sha256'],'actual_reference_pin:'+field)
    report=clone(prior.audit,namespace(old_review['receipt']['sha256']))()
    details=report['rows'];cases=independent_families(plan,details)
    if not report['independent_replay_errors']:
        require(cases==report['comparisons']['cases'],'independent_exact_families_and_protection')
    else:
        report['producer_comparisons_not_certified']=report.pop('comparisons')
    histories=Counter();residual=Counter();time_differences=Counter();old_differences=Counter();unloading={}
    for key,row in details.items():
        expected=model['rows'][key]
        require(expected['case']==plan['rows'][key]['case'] and expected['action']==plan['rows'][key]['vector']
                and expected['execution_index']==c.ORDER.index(key),'model_action_binding:'+key)
        require(model_plan['rows'][key]['action']==expected['action'],'model_preregistered_action:'+key)
        current=row.get('physical',{}).get('completion',{})
        prior_times=old_review['rows'][key]['physical']['completion']
        projection=expected['assessment'].get('completion',{})
        complete=set(current)==set(JOBS) and all(type(t) in (float,int) and math.isfinite(t) for t in current.values())
        row['prior_actual94_2_completion_diagnostic']={'old_status':old_review['rows'][key]['new_status'],
            'old_completion':prior_times,'new_minus_old':{j:current[j]-prior_times[j] for j in JOBS} if complete else None,
            'same_message_policy':False,'old_outcome_not_reused':True}
        row['conditional_old_model_diagnostic']={'saved_projection_status':expected['status'],'completion':projection,
            'new_native_minus_old_projection':{j:current[j]-projection[j] for j in JOBS} if complete and set(projection)==set(JOBS) else None,
            'same_message_policy':False,'used_for_online_decision':False,'new_protection_certified':False}
        if complete:
            old_differences['exact_all5' if current==prior_times else 'different_at_least_one_job']+=1
            time_differences['exact_all5' if current==projection else 'different_at_least_one_job']+=1
        for entry in row.get('attempts',[]):
            if entry.get('unloading_failed_read_fact'):
                unloading[key]={'eligibility':entry['retry_admission'],
                    'first_capture_pair':entry.get('actual_pair'),
                    'fresh_request':entry.get('new_request'),
                    'fresh_outcome':entry['unloading_fresh_outcome'],'actual_branch_status':row['new_status']}
            proof=entry['derived_goal_service_bounds']
            if proof:
                histories['collections_with_derived_history']+=1
                histories['first_collection_history' if entry['index']==0 else 'fresh_collection_history']+=1
                for tray in proof:histories['tray_'+tray]+=1
            if entry['information_status']=='unknown':
                for reason in entry['reasons']+entry['bundle_reasons']:residual[reason]+=1
    for p,digest in extra_pins.items():require(sha(p)==digest,'independent_auditor_source_drift')
    require(sha(OLD_REVIEW)==OLD_REVIEW_SHA and sha(MODEL/'branch_ledger.json')==MODEL_LEDGER_SHA,'reference_stability')
    report.update(schema='g31.unloading_native_saved_independent_review.v1',
        independently_recomputed_cases=cases,actual_historical_use=dict(histories),unknown_attempt_reasons=dict(residual),
        actual_unloading_recollection_outcomes=unloading,
        prior_actual_completion_differences=dict(old_differences),old_conditional_model_differences=dict(time_differences),
        previous_independent_actual_review=ref(OLD_REVIEW),conditional_model_plan=ref(MODEL/'preregistered_protocol.json'),
        conditional_model_ledger=ref(MODEL/'branch_ledger.json'),independent_auditor_loaded_source_pins=extra_pins,
        audit_wall_seconds=time.perf_counter()-start)
    report['limits']=[
        'All original actual94assessed/2unknown and its incomplete families remain immutable; this is a fresh message-policy execution.',
        'New saved replay rechecks actual current/owner/capture/immutable-client-prefix/historical-selfACK facts; it cannot mint native authority or prove atomic global state.',
        'Every sixteen-member reference and thirty-two-member optimum requires its complete valid native family; unknown never becomes zero regression.',
        'Old fixed96 model rows are retrospective diagnostics from a different communication schedule, not held-out validation, new model evaluations, online decisions or a protection bound.',
        'No optimizer was executed in this fixed-action campaign. Same-information, same-candidate, same-budget online method comparisons remain a separate task.',
        'No native session/event replay, original-airport improvement, solver novelty or complete-request100ms certification is produced by this saved-data audit.']
    return report


if __name__=='__main__':
    value=audit();TARGET.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'report':ref(TARGET),'status':value['status'],'counts':value['status_counts'],
        'history':value['actual_historical_use'],'fresh':value['fresh_pair_submissions_by_owner'],
        'replay_errors':len(value['independent_replay_errors']),'wall_seconds':value['audit_wall_seconds']}))
