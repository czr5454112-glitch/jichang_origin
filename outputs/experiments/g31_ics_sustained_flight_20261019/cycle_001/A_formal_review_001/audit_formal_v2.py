"""Independent formal evaluation audit. Standard library; no native or training.
Default waits for all ten ledger attempts to close before reading any formal raw.
"""
from __future__ import annotations
import argparse
import ast
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path

PLAN_SHA = '6ede398fcf64bd74fd2d79c30ad701bd056b787f6480e8d11eafa832f25b837b'
GUARD_SHA = '67cae1b1597cc9254a2cba0c9f7e670033aa4849dbb91e653ff9c6f39ca078b6'
FEATURE_SHA = '4b4ff7a0aa74c47302c0da9e0a67770af99c0239bb44a3120c09193c757abc9d'
ADDENDUM_SHA = 'f7c862a828f2fbb0ac354ba5a997de40ed657289b6cb5b1271b964f8e06ff3bd'
ACTIONS = {'native_default', 'prefer_3', 'prefer_8'}


def require(ok, why):
    if not ok: raise ValueError('formal_audit:' + why)


def read(path): return json.loads(Path(path).read_bytes())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
def reference(path): return {'path':str(Path(path).resolve()), 'sha256':sha(path)}
def finite(value): return type(value) in (int,float) and math.isfinite(value)
def near(a,b):
    require(finite(a) and finite(b) and abs(a-b) <= 1e-9*max(1.,abs(b)), 'numeric_mismatch')
def one(rows, why):
    require(len(rows)==1, why)
    return rows[0]


def validate_design(plan, contract, selection):
    require(plan['schema']=='g31.foundation.preregistered_native_fqi_evaluation.v1'
        and plan['test_based_selection_allowed'] is False and plan['heldout_native_previously_executed'] is False,
        'frozen_design_scope')
    rows=plan['rows'];require(len(rows)==10 and len({r['task_id'] for r in rows})==10, 'ten_unique_prespecified_branches')
    require(plan['native_branch_budget']==10 and plan['native_parallelism']==1 and plan['automatic_retries']==0,
        'frozen_budget_and_no_retries')
    require({r['case'] for r in rows}==set(contract['evaluation_plan']['held_out_parent_groups']), 'exact_two_heldout_cases')
    require(selection['status']=='completed_selection_only' and len(selection['models'])==3, 'frozen_model_selection')
    models={m['seed']:m['checkpoint'] for m in selection['models']}
    require(set(models)=={17,29,43}, 'all_prespecified_seeds')
    for case in sorted({r['case'] for r in rows}):
        cohort=[r for r in rows if r['case']==case]
        baseline=one([r for r in cohort if r['mode']=='baseline'], 'one_original_baseline')
        require(baseline['model'] is None and baseline['reference'] is None, 'original_baseline_unmodeled')
        guarded=[r for r in cohort if r['mode']=='guarded']
        require(len(guarded)==4 and sum(r['model'] is None for r in guarded)==1, 'one_rule_and_three_models')
        require(all(r['selection']=='score' and r['reference']==baseline['task_id'] for r in guarded), 'same_score_and_reference')
        require(sorted(digest(r['model']) for r in guarded if r['model'])==sorted(digest(m) for m in models.values()),
            'no_test_model_reselection')
    return models


def load_guard():
    path=Path(__file__).with_name('guard_audit_snapshot.py')
    require(sha(path)==GUARD_SHA, 'guard_snapshot_changed')
    spec=importlib.util.spec_from_file_location('formal_review_guard_snapshot',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def public_features(source):
    require(hashlib.sha256(source).hexdigest()==FEATURE_SHA,'approved_feature_source')
    module=ast.parse(source.decode('utf8'))
    module.body=[n for n in module.body if not(isinstance(n,ast.Import) and any(a.name=='numpy' for a in n.names))
                 and not(isinstance(n,ast.FunctionDef) and n.name in ('fit','predict'))]
    namespace={'__name__':'independent_formal_public_features'}
    exec(compile(module,'frozen_public_features','exec'),namespace)
    return namespace['features']


def forward(model, observation, action, features):
    require(model['native_execution_authority'] is False and model['model_sha256']==digest(
        {k:v for k,v in model.items() if k!='model_sha256'}),'detached_model_content_identity')
    f=features(observation,action);p=model['parameters']
    require(sorted(f)==model['feature_names'] and len(f)==123,'frozen_123_public_features')
    require(len(p['layers'])==3 and all(finite(s) and s>0 for s in p['scale'])
        and all(finite(c) for c in p['center']) and finite(p['target_scale']) and p['target_scale']>0
        and finite(p['target_center']),'finite_frozen_three_layer_parameters')
    x=[(f[n]-c)/s for n,c,s in zip(model['feature_names'],p['center'],p['scale'],strict=True)]
    for index,layer in enumerate(p['layers']):
        require(len(layer['weight'])==len(layer['bias'])==(64,64,1)[index],'frozen_architecture')
        x=[math.fsum(a*b for a,b in zip(w,x,strict=True))+bias for w,bias in zip(layer['weight'],layer['bias'],strict=True)]
        if index<2:x=list(map(math.tanh,x))
    result=x[0]*p['target_scale']+p['target_center']
    require(finite(result),'finite_inference')
    return result


def verify_observation(decision, evidence):
    public=decision['observation'];now=decision['selected_at'];owner=decision['owner']
    endpoints=evidence['information']['raw_endpoints'];view=endpoints['view']
    visible=dict(view);visible['jobs']=[r for r in view['jobs'] if r['arrival']<=now and r['status']!='unreleased']
    require(public['local_view']==visible and public['known_contracts']==evidence['retained']
        and public['own_outbox']==evidence['own_outbox'] and public['at']==now and public['owner']==owner,
        'features_bound_to_actual_endpoint_and_retained_ledger')
    expected=[]
    for envelope in endpoints['received']:
        local=envelope['capture']['capture_v2']['local_capture']
        require(local['target_owner']==owner and local['source_owner']!=owner
                and local['captured_at']<=envelope['delivered_at']<=now, 'actual_delivered_capture_scope')
        expected.append({'envelope':envelope,'message_id':local['message_id'],'source_owner':local['source_owner'],
            'target_owner':local['target_owner'],'status':envelope['status'],'captured_at':local['captured_at'],
            'delivered_at':envelope['delivered_at'],'valid_until':local['valid_until'],
            'fresh':envelope['status']=='conditional' and local['captured_at']<=now<local['valid_until']})
    require(public['delivered_v3']==expected and public['remaining_horizon_s']==40.-now,
            'actual_messages_and_remaining_horizon')
    require(public['privileged_evaluator_state_included'] is False and public['reference_included'] is False,
            'no_reference_or_truth_in_features')


def ranking_choice(candidates, predictions, scores):
    require(len({r['action_id'] for r in candidates})==len(candidates),'unique_candidate_ids')
    enabled=[r for r in candidates if r['enabled']]
    require(bool(enabled),'no_authorized_choice')
    require(not scores or set(scores)=={r['action_id'] for r in enabled},'scores_only_enabled_candidates')
    require(all(finite(v) for v in scores.values()),'finite_scores')
    return min(enabled,key=lambda r:(-scores.get(r['action_id'],0.),
        sum(predictions[r['action_id']]['completion'].values()),r['action_id']!='prefer_3',r['action_id']))['action_id']


def verify_scoring(decision, current, model, model_ref, feature_fn):
    require(decision['behavior_selection']=='score' and decision['resolved_behavior_preference'] is None
            and not decision['worker_candidate_order'] and decision.get('worker_result_id') is None,'fixed_sync_score_selection')
    attempt=current['attempt'];verify_observation(decision,attempt['evidence'])
    service=attempt['evidence']['information']['bundle']['trays']['L']['service_ready_at']
    require(service==decision['opportunity']['service_ready_at'],'actual_service_ready_bound')
    for candidate in decision['candidate_mask']:
        identity=candidate['action_id'];require(identity in ACTIONS,'fixed_three_action_catalog')
        target=8 if identity=='prefer_8' else 3 if identity=='prefer_3' else None
        expected={'operation_kind':'no_command' if target is None else 'route','source':7,
            'destination':target,'tray_id':'L','earliest_legal_arrival':None if target is None else service+(2.8 if target==8 else 1.),
            'native_default_does_not_clear_preference':True}
        require(candidate['semantic']==expected,'every_candidate_semantic_matches_action_identity')
    enabled=[c for c in decision['candidate_mask'] if c['enabled']]
    # Run the archived strict legal-observation validator for every scored semantic.
    for candidate in enabled: feature_fn(decision['observation'],candidate['semantic'])
    ranking=decision.get('learned_ranking');scores={}
    if model is None:
        require(ranking is None,'rule_has_no_model')
    else:
        require(isinstance(ranking,dict) and ranking['used_as_authority'] is False
            and ranking['model_reference']==model_ref and ranking['candidate_ids']==[c['action_id'] for c in enabled],
            'model_scope_and_advice_only')
        require(ranking['status']=='scored_current_guarded_candidates'
            and ranking['model_content_sha256']==model['model_sha256'],'actual_successful_frozen_model_consumption')
        scores={c['action_id']:forward(model,decision['observation'],c['semantic'],feature_fn) for c in enabled}
        require(set(scores)==set(ranking['scores']),'all_enabled_scores_present')
        for key,value in scores.items():near(value,ranking['scores'][key])
    chosen=ranking_choice(decision['candidate_mask'],attempt['model_report']['candidate_results'],scores)
    require(chosen==decision['selected_action_id'],'actual_chosen_follows_recomputed_ranking')
    rule=ranking_choice(decision['candidate_mask'],attempt['model_report']['candidate_results'],{})
    rule_scores={key:math.fsum(value['completion'].values())
                 for key,value in attempt['model_report']['candidate_results'].items()}
    unique_top=model is not None and len(enabled)>=2 and sum(value==max(scores.values()) for value in scores.values())==1
    basis=('guard_singleton' if len(enabled)==1 else 'model_unique_top_score' if unique_top else
           'model_score_tie_then_rule' if model is not None else 'strong_rule_score')
    return {'status':'verified_actual_ranking','candidate_count':len(decision['candidate_mask']),
            'enabled_count':len(enabled),'chosen':chosen,'same_state_rule_choice':rule,
            'model_changes_same_state_rule_choice':model is not None and chosen!=rule,
            'model_scored':model is not None,'scores':scores,'selection_basis':basis,
            'guard_singleton_determined_choice':len(enabled)==1,'model_unique_top_score':unique_top,
            'chosen_model_score':scores.get(chosen),'chosen_rule_completion_sum':rule_scores[chosen],
            'rule_completion_sum_by_action':rule_scores,
            'candidate_admission_and_scores':[{'action_id':c['action_id'],'enabled':c['enabled'],
                'guard_status':c.get('guard_status'),'per_job_delta':c.get('per_job_delta'),
                'rule_completion_sum':rule_scores[c['action_id']],'model_score':scores.get(c['action_id'])}
                for c in decision['candidate_mask']],
            'observation_sha256':digest(decision['observation']),
            'semantic_sha256':{c['action_id']:digest(c['semantic']) for c in enabled}}


def completion_vector(raw):
    jobs=raw['input']['jobs'];outcomes=raw['result']['jobs'];clock=raw['result']['physical_clock']
    offered={j['business_bag_id']:j for j in jobs}
    require(len(offered)==len(jobs)==len(outcomes)==6 and {j['business_bag_id'] for j in outcomes}==set(offered),
            'complete_six_business_population')
    require(len(raw['input']['trays'])==3,'three_trays')
    vector={};censored=[]
    for job in outcomes:
        identity=job['business_bag_id'];arrivals=[r for r in raw['result']['receipts'] if r['event']=='BAG_ARRIVAL' and r['business_bag_id']==identity]
        require(len(arrivals)==1 and arrivals[0]['time']==offered[identity]['arrival'],'actual_arrival')
        events=[r for r in raw['result']['receipts'] if r['event']=='UNLOAD_COMPLETE' and r['business_bag_id']==identity]
        if job['status']=='completed':
            value=job['completed_at'];require(finite(value) and offered[identity]['arrival']<=value<=clock
                and len(events)==1 and events[0]['time']==value,'actual_unique_business_completion')
            vector[identity]=value
        else:
            require(not events,'censor_without_completion_receipt');censored.append(identity)
    if not censored:
        require(raw['summary']['completion']==vector and raw['summary']['business_complete'] is True
            and raw['summary']['audit']['status']=='passed' and raw['summary']['stock_preserved'] is True,
            'closed_inventory_and_business_summary')
        near(math.fsum(vector.values()),raw['summary']['completion_sum'])
    return {'complete':not censored,'completion':vector,'censored_jobs':censored,'physical_clock':clock,
            'completion_sum':math.fsum(vector.values()) if not censored else None}


def attempt_for(base, task):
    matches=list((base/'attempts').glob(task+'_*'))
    require(len(matches)<=1,'no_automatic_retries_or_duplicate_attempts')
    if not matches or not (matches[0]/'receipt.json').exists():return None
    return matches[0]


def verify_source_cohort(sources_by_task, exception=None):
    """One exact preregistered harness delta; never normalize other sources."""
    source_sets=[set(s) for s in sources_by_task.values()]
    require(not source_sets or all(s==source_sets[0] for s in source_sets),'source_inventory_changed_across_formal_branches')
    common=source_sets[0] if source_sets else set()
    changed={p for p in common if len({s[p] for s in sources_by_task.values()})!=1}
    if exception is None:
        require(not changed,'common_source_changed_across_formal_branches')
    else:
        path=exception['path'];before=exception['before_sha256'];after=exception['after_sha256']
        tasks=set(exception['tasks_after'])
        require(Path(path).name=='foundation_repeated_campaign.py' and path in common
            and before!=after and len(before)==len(after)==64,'single_exact_harness_exception')
        require(changed<={path},'unapproved_source_change')
        for task,pins in sources_by_task.items():
            require(pins[path]==(after if task in tasks else before),'source_version_matches_registered_task_partition')
    return len(common)


def verify_outer(attempt, row, formal_plan):
    registration=read(attempt/'registration.json');outer=read(attempt/'receipt.json')
    require(registration['task_id']==row['task_id'] and registration['native_branches']==1
        and registration['hard_seconds']==formal_plan['outer_hard_seconds'],'same_outer_budget')
    require(registration['registered_at']>=formal_plan['created_utc_epoch'],'formal_design_precedes_registration')
    archives={p:attempt/'source'/(f'{i:04d}'+Path(p).suffix) for i,p in enumerate(registration['source_pins'])}
    require(all(sha(archives[p])==v for p,v in registration['source_pins'].items()),'archived_launch_source_binding')
    if outer['status']=='completed':
        require(not outer['source_changed'] and outer['process']['exitcode']==0
            and outer['process']['child_released_only_after_job_assignment'] is True,'closed_outer_process')
    return registration,outer


def load_source_addendum(path, plan_path, plan):
    require(sha(path)==ADDENDUM_SHA,'exact_registered_source_addendum')
    addendum=read(path)
    require(addendum['schema']=='g31.foundation.formal_reference_eligibility_clarification.v1'
        and addendum['formal_contract']==reference(plan_path),'source_addendum_formal_binding')
    require(addendum['completed_tasks_before_change']==[r['task_id'] for r in plan['rows'][:6]]
        and addendum['first_attempt_tasks_after_change']==[r['task_id'] for r in plan['rows'][6:]],'exact_six_four_task_partition')
    require(addendum['all_other_native_campaign_sources_and_keys_must_match'] is True
        and addendum['same_formal_input_and_clock_and_10_branch_denominator'] is True
        and addendum['no_reexecution_of_completed_six'] is True and addendum['new_native_branch_budget']==4,
        'source_exception_only_budget_preserved')
    require(all(addendum[k] is False for k in ('historical_baseline_summary_modified','current_native_guard_modified',
        'model_or_selection_modified','retraining_or_test_based_selection')),'no_guard_data_or_learning_change')
    for key in ('baseline_audit','implementation_audit','interrupted_execution_log'):
        require(reference(addendum[key]['path'])==addendum[key],'frozen_addendum_evidence')
    failure=addendum['preparation_failure']
    require(failure['task_id']==plan['rows'][6]['task_id'] and failure['native_started'] is False
        and failure['ledger_registered'] is False,'prepare_refusal_not_native_failure')
    require(len(addendum['allowed_source_changes'])==1,'one_exact_source_exception')
    source,pins=next(iter(addendum['allowed_source_changes'].items()))
    require(Path(source).name=='foundation_repeated_campaign.py'
        and pins=={'before_sha256':'036819c1e15ba6f1585c410b981cf19a5cb31d713d6d57468154e2c703571986',
                   'after_sha256':'b97c8f1b41d7709f96710021e2ae2f87f5f6eb7989e9877658a95d85ee77b5b1'},
        'exact_approved_harness_bytes')
    exception={'path':source,**pins,'tasks_after':addendum['first_attempt_tasks_after_change']}
    return addendum,exception


def audit(plan_path, source_addendum_path=None):
    plan_path=Path(plan_path).resolve();require(sha(plan_path)==PLAN_SHA,'frozen_formal_plan_hash')
    plan=read(plan_path);base=plan_path.parent
    require(reference(plan['source_collection_contract']['path'])==plan['source_collection_contract']
        and reference(plan['frozen_selection']['path'])==plan['frozen_selection'],'frozen_contract_and_selection')
    selection=read(plan['frozen_selection']['path']);contract=read(plan['source_collection_contract']['path'])
    models=validate_design(plan,contract,selection)
    addendum,exception=load_source_addendum(source_addendum_path,plan_path,plan) if source_addendum_path else (None,None)
    attempts={r['task_id']:attempt_for(base,r['task_id']) for r in plan['rows']}
    if any(p is None for p in attempts.values()):
        return {'status':'awaiting_complete_evaluation','planned_denominator':10,
                'closed_attempts':sum(p is not None for p in attempts.values()),'formal_raw_results_read':False,
                'missing_tasks':[key for key,p in attempts.items() if p is None]}
    for model_ref in models.values():require(reference(model_ref['path'])==model_ref,'frozen_weight_file')
    selection_plan=read(Path(plan['frozen_selection']['path']).parent/'selection_plan.json')
    features=public_features(Path(selection_plan['feature_source']).read_bytes());guard=load_guard()
    results=[];raw_by_task={};sources_by_task={}
    for row in plan['rows']:
        task=row['task_id'];folder=base/task;registration,outer=verify_outer(attempts[task],row,plan)
        if addendum is not None:
            if task in exception['tasks_after']:
                require(registration['registered_at']>=addendum['created_utc_epoch']
                    and registration['source_pins'].get(str(Path(source_addendum_path).resolve()))==ADDENDUM_SHA,
                    'new_branch_admitted_after_pinned_addendum')
            else:
                require(outer['finished_at']<=addendum['created_utc_epoch'],'old_branch_closed_before_addendum')
        if outer['status']!='completed':
            results.append({'task_id':task,'case':row['case'],'mode':row['mode'],'model':row['model'],
                            'status':'failed_retained_in_denominator','outer_status':outer['status']});continue
        raw,worker,inner=guard.load_closed(folder);runplan=read(folder/'plan.json')
        require(runplan['hard_seconds']==plan['per_branch_hard_seconds'] and runplan['native_branch_budget']==1
            and runplan['automatic_retries']==0,'same_inner_budget')
        require(outer['assessment']==inner,'outer_inner_assessment_binding')
        spec=raw['specification']
        require(spec['case']==row['case'] and spec['mode']==row['mode'] and spec['selection']==row['selection']
            and spec.get('model_reference')==row['model'],'declared_formal_branch_identity')
        expected_split={'hold3_11_66_release27_7':'heldout_positive_hypothesis',
                        'hold3_11_69_release27_7':'heldout_negative_hypothesis'}[row['case']]
        require(spec['domain']['declared_split']==expected_split
            and spec['domain']['source_age_limit_s']==.05 and spec['domain']['strict_protection_tolerance']==0,
            'same_freshness_and_strict_guard')
        model=read(row['model']['path']) if row['model'] else None
        if model is not None:
            require(spec['model_content_sha256']==model['model_sha256'] and spec['model_used_as_authority'] is False,
                    'model_binding_and_no_guard_authority')
        physical=completion_vector(raw);decisions=[];failures=[]
        for decision in raw['repeated_decisions']:
            mode=decision['current_admission']['execution_mode']
            if mode=='protected_current':
                try:
                    current=guard.current_chain(raw,decision)
                    ranking=verify_scoring(decision,current,model,row['model'],features)
                    decisions.append({'decision_id':decision['decision_id'],'job':current['target_job'],
                                      'command_id':current['command_id'],'ack':current['ack'],'edge':current['edge'],
                                      'current_full_guard_verified':True,**ranking})
                except (KeyError,ValueError,TypeError,IndexError,OverflowError) as error:
                    failures.append({'decision_id':decision['decision_id'],'error':str(error)})
            elif mode=='original_fallback':
                require(not any(c['enabled'] for c in decision['candidate_mask']),'fallback_cannot_skip_admissible_choice')
                decisions.append({'decision_id':decision['decision_id'],'status':'original_fallback_no_model_choice',
                                  'job':decision['opportunity']['target']['business_bag_id']})
            else:require(mode=='original_fixed_rule','known_execution_mode')
        require(not failures,'decision_audit_failures:'+json.dumps(failures))
        raw_by_task[task]=raw;sources_by_task[task]=runplan['source_sha256']
        results.append({'task_id':task,'case':row['case'],'mode':row['mode'],'model':row['model'],
            'status':'closed_audited' if physical['complete'] else 'censored_retained_in_denominator',
            **physical,'decisions':decisions,'scored_decisions':sum(d.get('model_scored',False) for d in decisions),
            'multiple_enabled_model_decisions':sum(d.get('model_scored',False) and d['enabled_count']>=2 for d in decisions),
            'model_changed_same_state_rule_choices':sum(d.get('model_changes_same_state_rule_choice',False) for d in decisions),
            'guard_singleton_decisions':sum(d.get('guard_singleton_determined_choice',False) for d in decisions),
            'source_archive_verified':True,'outer_wall_seconds':outer['process']['wall_seconds']})
    source_count=verify_source_cohort(sources_by_task,exception)
    by_task={r['task_id']:r for r in results}
    for row in plan['rows']:
        result=by_task[row['task_id']]
        if row['reference'] and row['task_id'] in raw_by_task and row['reference'] in raw_by_task:
            baseline=raw_by_task[row['reference']]
            require(raw_by_task[row['task_id']]['input']==baseline['input'],'paired_identical_full_input')
            require(raw_by_task[row['task_id']]['specification']['reference']['completion']==baseline['summary']['completion'],
                    'same_immutable_full_job_baseline')
            if result.get('complete') and by_task[row['reference']].get('complete'):
                result['delta_vs_original_by_job']={j:v-baseline['summary']['completion'][j] for j,v in result['completion'].items()}
                result['zero_tolerance_native_nonharm']=all(v<=0 for v in result['delta_vs_original_by_job'].values())
    for case in {r['case'] for r in plan['rows']}:
        cohort=[r for r in results if r['case']==case]
        rules=[r for r in cohort if r.get('mode')=='guarded' and r.get('model') is None and r.get('complete')]
        if len(rules)==1:
            rule=rules[0]
            for result in cohort:
                if result.get('model') and result.get('complete'):
                    result['delta_vs_strong_rule_by_job']={j:v-rule['completion'][j] for j,v in result['completion'].items()}
                    result['completion_sum_delta_vs_strong_rule']=result['completion_sum']-rule['completion_sum']
    return {'schema':'g31.independent.formal_fqi_evaluation_audit.v1','status':'completed_independent_audit',
        'frozen_plan':reference(plan_path),'audit_script':reference(__file__),'planned_denominator':10,
        'results':results,'source_inventory_count':source_count,'unchanged_source_count':source_count-(1 if exception else 0),
        'source_addendum':None if source_addendum_path is None else reference(source_addendum_path),
        'exact_harness_source_exception':exception,
        'preparation_failure_not_a_native_attempt':None if addendum is None else addendum['preparation_failure'],
        'closed_complete_count':sum(r.get('complete',False) for r in results),
        'all_seeds_reported':True,'test_based_selection_performed':False,'training_or_native_executed_by_audit':False,
        'scope':'two synthetic heldout parent groups; not independent airport days or systemwide RL validation'}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--plan',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--source-addendum',type=Path)
    args=parser.parse_args();require(not args.output.exists(),'fresh_output_required');result=audit(args.plan,args.source_addendum)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf8')
    print(json.dumps({'status':result['status'],'planned_denominator':result['planned_denominator'],
                      'closed_complete_count':result.get('closed_complete_count')}))


if __name__=='__main__':main()

