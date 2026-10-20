"""Registered train-only airport behavior-value pretraining, never native RL.

Only readiness-certified actual actions are fitted. One censored trajectory
is one training parent. Final epochs for all preregistered seeds are retained;
no development/test data, model selection, or new outcome labels are used.
"""
from __future__ import annotations

import sys
TOKEN='g31_airport_behavior_training_v1'
if __name__=='__main__' and '--run' in sys.argv and sys.stdin.readline().strip()!=TOKEN:
    raise SystemExit('airport_behavior_training:bounded_parent_admission_required')

import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
import traceback

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001'
SCHEMA='g31.foundation.airport_behavior_training.v1'
MODULE='scripts.experiments.g31_ics_circulation.foundation_airport_behavior_training'
SEEDS=(17,29,43)
EPOCHS=100
POSITIVE_ACKS={'accepted','granted','dispatching','departed','in_transit','received'}
DIAGNOSTIC_CONTRACT={'max_pairs':3,'pair_selection':'first_eligible_callbacks_in_sequence_with_distinct_proposed_semantics',
    'variants':['actual_forecast','forecast_values_masked','zero_new_demand'],'all_seeds':list(SEEDS),
    'numerical_tolerance':1e-8,'model_selection':False,'physical_benefit_claim':False,'labels_generated':False}


def require(ok,reason):
    if not ok:raise ValueError('airport_behavior_training:'+reason)


def number(value):
    require(type(value)in(int,float) and math.isfinite(value),'finite_numeric_evidence')
    return float(value)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}


def read(path):return json.loads(Path(path).read_bytes())


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def write(path,value):
    with Path(path).open('x',encoding='utf8')as stream:json.dump(value,stream,indent=2,allow_nan=False)


def normalize_callback(original):
    """Lossless field adaptation only; preserve the actual original record."""
    require(original['schema'] in ('g31.foundation.airport_policy_observation.v1','g31.foundation.airport_policy_observation.v2'),
        'known_record_schema')
    adapted=copy.deepcopy(original)
    adapted['schema']='g31.foundation.airport_policy_observation.v1'
    require({key:value for key,value in adapted.items()if key!='schema'}==
            {key:value for key,value in original.items()if key!='schema'},'schema_only_normalization')
    return adapted,{'original_record_sha256':digest(original),'adapter_record_sha256':digest(adapted),
        'only_changed_field':'schema' if adapted['schema']!=original['schema'] else None,
        'original_schema':original['schema'],'adapter_schema':adapted['schema'],'raw_modified':False}


def diagnostic_variants(observation):
    """Input interventions only; retain legal static-plan provenance/variant.

    Unknown demand stays unknown in every case. No outcome label or physical
    counterfactual is generated, and this is not a no-plan product evaluation.
    """
    require(observation['information_variant']=='static_plan','diagnostic_fixed_static_plan_variant')
    variants={'actual_forecast':copy.deepcopy(observation)}
    for name in ('forecast_values_masked','zero_new_demand'):
        changed=copy.deepcopy(observation);forecast=changed['demand_forecast']
        known=[region for region,missing in forecast['missing_mask_by_region'].items()if not missing]
        for region in known:
            values=forecast['new_demand_mean_by_region'][region]
            require(all(type(v)in(int,float) and math.isfinite(v) and v>=0 for v in values),
                'diagnostic_changes_only_previously_known_finite_demand')
            forecast['new_demand_mean_by_region'][region]=[None if name=='forecast_values_masked' else 0. for _ in values]
            forecast['missing_mask_by_region'][region]=name=='forecast_values_masked'
            forecast.setdefault('uncertainty_by_region',{})[region]=None
        forecast['window_summaries_by_region']={}
        forecast['diagnostic_intervention']={'kind':name,'original_forecast_sha256':digest(observation['demand_forecast']),
            'changed_regions':known,'context_availability_preserved':True,'physical_world_changed':False,'label_generated':False}
        variants[name]=changed
    return variants


def diagnostic_pair(callback,wrapped,candidates):
    """First actually proposed distinct semantic, chosen without looking at y."""
    require(candidates,'actual_chosen_proposal_exists')
    first=candidates[0]
    other=next((candidate for candidate in candidates[1:]if candidate['semantic']!=first['semantic']),None)
    if other is None:return None
    return {'callback_sequence':callback['sequence'],'callback_sha256':digest(callback),'at':callback['now'],
        'owner':callback['owner_id'],'observation':copy.deepcopy(wrapped),
        'actions':[copy.deepcopy(first['semantic']),copy.deepcopy(other['semantic'])],
        'proposal_sha256':[first['source_proposal_sha256'],other['source_proposal_sha256']],
        'chosen_index':0,'second_action':'proposal_only_no_counterfactual_label_or_guard_authority'}


def score_diagnostic(model,pair,predict):
    variants=diagnostic_variants(pair['observation']);scores={};gaps={}
    for name,observation in variants.items():
        output=predict(model,[observation,observation],pair['actions'])
        require(len(output)==2 and all(type(v)in(int,float) and math.isfinite(v)for v in output),'finite_fixed_pair_scores')
        scores[name]=output;gaps[name]=output[0]-output[1]
    deltas={key:gap-gaps['actual_forecast']for key,gap in gaps.items()if key!='actual_forecast'}
    return {'callback_sequence':pair['callback_sequence'],'pair_sha256':digest(pair),'scores':scores,
        'chosen_minus_other_score':gaps,'gap_change_from_actual_forecast':deltas,
        'numerical_nonadditivity_at_1e_minus_8':any(abs(delta)>1e-8 for delta in deltas.values()),
        'physical_control_benefit_established':False,'counterfactual_outcome_labels_created':False,
        'model_selection_performed':False,'no_plan_product_evaluated':False}


def validate_row(row,contract):
    """Check immutable readiness exports before generating any model feature."""
    require(row['schema']=='g31.foundation.airport_behavior_readiness.v1' and row['split']=='train'
        and row['parent_group']==contract['parent_group'] and row['native_execution_authority'] is False,
        'single_trajectory_training_only')
    callback=row['callback_record'];submission=row['submission'];label=row['behavior_label'];execution=row['execution']
    require(submission['callback_sha256']==digest(callback) and submission['callback_sequence']==callback['sequence']
        and submission['at']==callback['now'] and submission['owner']==callback['owner_id'], 'actual_callback_binding')
    require(submission['pre_submit_source_evidence']['supports_training'] is True
        and execution['status']=='actual_execution_and_delivered_ack_bound'
        and execution['counterfactual_protection_certified'] is False,'actual_executed_behavior_only')
    require(label['label_start']==callback['now'] and label['label_end']==callback['now']+300.
        and 43200.<=callback['now'] and label['label_end']<=57600.
        and label['horizon_seconds']==300. and label['discount']==1. and label['physical_population']==28506
        and label['counterfactual_label'] is False and label['future_completion_imputed'] is False,
        'fixed_full_population_closed_behavior_window')
    target=row['target_value']
    require(type(target)in(int,float) and math.isfinite(target) and target<=0 and target==label['target_value'],
        'finite_actual_return_not_unknown_zero')
    request=submission['actual_request'];proposal=callback['decision']['intents'][0]
    expected=copy.deepcopy(proposal);expected.pop('expected_version',None)
    expected.update(request_id=request['request_id'],owner_id=callback['owner_id'])
    edge=execution['first_edge'];leg=execution.get('native_leg');ack=execution.get('positive_ack')
    require(type(leg)is dict and type(ack)is dict,'actual_positive_ack_and_native_leg_required')
    require(request==expected and request['issued_at']==callback['now'] and edge['event']=='EDGE_ENTER'
        and edge['from']==request['source'] and edge['tray_id']==request['tray_id']
        and max(number(callback['now'])+number(request['message_delay']),number(request['earliest_departure']))
        <=number(edge['time'])<=label['label_end'],'actual_action_payload_and_effect')
    require(ack['request_id']==request['request_id'] and ack['status'] in POSITIVE_ACKS
        and callback['now']<=number(ack['observed_at'])<=number(ack['delivered_at'])<=label['label_end'],
        'actual_delivered_positive_ack_bound_to_request_and_window')
    require(type(leg['runtime_id'])is int and leg['runtime_id']>=0 and leg['kind']=='empty_return' and leg['job']==-1
        and leg['transport_leg_id']==request['request_id']+':empty_return:'+str(leg['runtime_id'])
        and edge['transport_leg_id']==leg['transport_leg_id'],'actual_request_native_leg_first_edge_binding')
    return callback,request


def readiness_archives(registration_path,readiness,rplan):
    """Use the exact executed source archive, never today's collection source."""
    registration_path=Path(registration_path).resolve();registration=read(registration_path)
    require(registration['task_id']==Path(readiness).name and registration['native_branches']==0
        and registration['module']=='scripts.experiments.g31_ics_circulation.foundation_airport_behavior_readiness'
        and registration['args']==['--run','--output',str(Path(readiness).resolve())]
        and registration['assessment']=={'path':str(Path(readiness).resolve()/'receipt.json'),
            'allowed_statuses':['completed_behavior_readiness']}
        and registration['source_pins'].get(str(Path(readiness).resolve()/'plan.json'))==sha(Path(readiness)/'plan.json'),
        'actual_readiness_launcher_registration')
    outer_path=registration_path.with_name('receipt.json');outer=read(outer_path)
    require(outer['status']=='completed' and outer['process']['status']=='exited'
        and outer['process']['exitcode']==0 and outer['source_changed']==[]
        and outer.get('assessment')==read(Path(readiness)/'receipt.json'), 'actual_readiness_launcher_closed_unchanged')
    sources={};remaining=set(rplan['source_sha256'])
    for index,(source,expected)in enumerate(registration['source_pins'].items()):
        if source not in remaining:continue
        require(expected==rplan['source_sha256'][source],'readiness_source_registration_plan_binding')
        archived=registration_path.parent/'source'/(f'{index:04d}'+Path(source).suffix)
        require(sha(archived)==expected,'actual_executed_readiness_source_archive_bytes')
        sources[source]=ref(archived);remaining.remove(source)
    require(not remaining,'complete_executed_readiness_source_archive')
    return sources,{'readiness_registration':ref(registration_path),'readiness_outer_receipt':ref(outer_path)}


def prepare(readiness,arrays_validation,output,*,readiness_registration,full_feature_audit):
    readiness=Path(readiness).resolve();arrays_validation=Path(arrays_validation).resolve();output=Path(output).resolve()
    require(readiness.is_relative_to(BASE) and arrays_validation.is_relative_to(BASE)
        and output.is_relative_to(BASE) and not output.exists(),'fresh_registered_workspace_paths')
    receipt=read(readiness/'receipt.json');rplan=read(readiness/'plan.json')
    require(receipt['status']=='completed_behavior_readiness' and receipt['minimum_passed'] is True
        and receipt['eligible_for_separate_training_plan'] is True and receipt['development_only'] is False
        and receipt['source_exit_pins_passed'] is True and receipt['plan']==ref(readiness/'plan.json'),
        'closed_actual_readiness_minimum_passed')
    contract=rplan['training_contract']
    require(contract['seeds']==list(SEEDS) and contract['epochs']==EPOCHS and contract['split']=='train'
        and contract['independent_development_or_test'] is False and contract['earliest_model_use_sim_time']==57600.
        and contract['checkpoint_selection']=='fixed_last_epoch_no_development_selection','immutable_no_selection_contract')
    require(ref(receipt['eligible_rows']['path'])==receipt['eligible_rows'],'fixed_actual_eligible_rows')
    executed,launcher_inputs=readiness_archives(readiness_registration,readiness,rplan)
    prereg=read(rplan['inputs']['preregistration']['path'])
    require(prereg['contract']==contract and prereg['minimum']==rplan['minimum']==receipt['minimum'],'original_preregistration_not_changed')
    parity=read(arrays_validation/'receipt.json');aplan=read(arrays_validation/'plan.json')
    require(parity['status']=='completed_exact_saved_forecast_and_B2_parity'
        and parity['completed_saved_forecasts']==402 and len(parity['B2_rows'])==3
        and all(row['exact_forecast_and_features_bytes'] is True for row in parity['B2_rows'])
        and parity['source_exit_pins_passed'] is True and parity['no_training_or_test_selection'] is True
        and parity['plan']==ref(arrays_validation/'plan.json'),'actual_accelerated_forecast_parity_closed')
    full_feature_audit=Path(full_feature_audit).resolve()
    require(full_feature_audit.is_relative_to(BASE),'historical_feature_audit_in_workspace')
    full=read(full_feature_audit/'receipt.json');fplan=read(full_feature_audit/'plan.json')
    independent=read(full_feature_audit/'independent_complete_rows_audit_001.json')
    require(full['status']=='completed_public_feature_audit' and full['source_exit_pins_passed'] is True
        and full['plan']==ref(full_feature_audit/'plan.json') and full['counts']['records']==946
        and full['counts']['feature_vectors']==463 and full['failures']==[]
        and full['outcome_labels_created']==0 and full['native_action_consumption_tested'] is False
        and independent['status']=='complete_public_rows_independently_verified'
        and independent['receipt_sha256']==sha(full_feature_audit/'receipt.json')
        and independent['plan_sha256']==sha(full_feature_audit/'plan.json')
        and independent['recounted_records']==946 and independent['recounted_vectors']==463
        and independent['all_202_previous_record_serialized_lines_exact'] is True,
        'complete_public_features_compatibility_not_labels_or_independent_test')
    collection=read(rplan['inputs']['collection_plan']['path'])
    inputs={'readiness_receipt':ref(readiness/'receipt.json'),'readiness_plan':ref(readiness/'plan.json'),
        'eligible_rows':receipt['eligible_rows'],'preregistration':rplan['inputs']['preregistration'],
        'arrays_receipt':ref(arrays_validation/'receipt.json'),'arrays_plan':ref(arrays_validation/'plan.json'),
        'checkpoint':aplan['inputs']['checkpoint'],'public_plan':aplan['inputs']['public_plan'],
        'mapping':collection['mapping'],'collection_plan':rplan['inputs']['collection_plan'],**launcher_inputs,
        'full_public_feature_receipt':ref(full_feature_audit/'receipt.json'),
        'full_public_feature_plan':ref(full_feature_audit/'plan.json'),
        'full_public_feature_independent_audit':ref(full_feature_audit/'independent_complete_rows_audit_001.json')}
    names=['foundation_airport_behavior_training.py','foundation_airport_learning_public.py','foundation_airport_learning_audit.py',
        'foundation_action_value.py','foundation_flight_forecaster_arrays.py','foundation_flight_forecaster.py',
        'foundation_flight_context.py','analytic_control.py','__init__.py']
    sources={str(Path(__file__).with_name(name).resolve()):sha(Path(__file__).with_name(name))for name in names}
    for path,expected in sources.items():
        if Path(path).name!='foundation_airport_behavior_training.py':
            require(aplan['sources'].get(path)==expected,'execution_sources_match_actual_arrays_validation')
            require(fplan['source_sha256'].get(path)==expected,'execution_sources_match_full_public_feature_audit')
    ancestry={**rplan['historical_source_sha256']}
    ancestry.update({item['path']:item['sha256']for item in rplan['inputs'].values()})
    ancestry.update({item['path']:item['sha256']for item in executed.values()})
    # Current airport/native modules are not training dependencies. Only the
    # immutable actual collection archives certify the row provenance.
    for path,expected in ancestry.items():require(sha(path)==expected,'readiness_ancestry_bytes')
    for item in inputs.values():require(ref(item['path'])==item,'training_input_bytes')
    plan={'schema':SCHEMA,'status':'prepared_not_executed','output':str(output),'training_contract':contract,
        'inputs':inputs,'source_sha256':sources,'ancestry_sha256':ancestry,'executed_readiness_source_archive':executed,
        'expected_rows':receipt['metrics']['unique_executed_requests'],
        'seeds':list(SEEDS),'epochs':EPOCHS,'information_variant':'static_plan','soft_wall_seconds':240,'fit_seconds_per_seed':45,
        'fit_calls':3,'native_branches':0,'observed_counts':None,'checkpoint_selection':'none_all_fixed_final_epochs',
        'forecast_implementation':'g31.foundation.flight_forecaster_per_call_arrays.v1',
        'diagnostic_contract':DIAGNOSTIC_CONTRACT,
        'feature_scope':'only actual pre-submit public callback plus frozen prior-only B1; labels stay outside observation',
        'objective':'supervised_realized_300s_behavior_value_not_optimal_Q_or_RL'}
    output.mkdir(parents=True);write(output/'plan.json',plan)
    spec={'task_id':output.name,'module':MODULE,'args':['--run','--output',str(output)],'native_branches':0,'hard_seconds':270,
        'inner_admission':TOKEN,'sources':[*sources,*ancestry,*(v['path']for v in inputs.values()),str(output/'plan.json')],
        'requires':[readiness.name],'assessment':{'path':str(output/'receipt.json'),'allowed_statuses':['completed_train_only_behavior_pretraining']},
        'next_action':'Review all three weights and training-only losses; later shadow/native consumption is a separate registered diagnostic.'}
    write(output.parent/(output.name+'_task.json'),spec)
    return plan


def validate(plan):
    require(plan['schema']==SCHEMA and plan['seeds']==list(SEEDS) and plan['epochs']==EPOCHS
        and plan['fit_calls']==3 and plan['native_branches']==0 and plan['observed_counts'] is None
        and plan['information_variant']=='static_plan' and plan['checkpoint_selection']=='none_all_fixed_final_epochs'
        and plan['diagnostic_contract']==DIAGNOSTIC_CONTRACT,
        'fixed_registered_training_scope')
    for path,expected in {**plan['source_sha256'],**plan['ancestry_sha256']}.items():require(sha(path)==expected,'training_source_or_ancestry_pin')
    for item in plan['inputs'].values():require(ref(item['path'])==item,'training_input_pin')


def run(output):
    output=Path(output);plan=read(output/'plan.json');validate(plan);started=time.monotonic();deadline=started+plan['soft_wall_seconds']
    report={'schema':SCHEMA,'status':'failed_train_only_behavior_pretraining','plan':ref(output/'plan.json'),
            'native_branches':0,'fit_calls_started':0,'models':[]}
    try:
        from . import foundation_airport_learning_public as public
        from . import foundation_airport_learning_audit as projection
        from . import foundation_action_value as value
        from . import foundation_flight_forecaster as original
        from . import foundation_flight_forecaster_arrays as arrays
        checkpoint=original.validate_checkpoint(read(plan['inputs']['checkpoint']['path']))
        context=read(plan['inputs']['public_plan']['path']);mapping=read(plan['inputs']['mapping']['path'])
        require(context['availability_basis']=='static_predeclared' and context['received_at']==0.,'explicit_static_plan_assumption')
        rows=[];metadata=[];seen=set();label_ends=[];pairs=[];pair_sequences=set();last_sequence=-1
        materialized=output/'materialized_training_rows.jsonl.gz'
        with gzip.open(plan['inputs']['eligible_rows']['path'],'rt',encoding='utf8')as incoming,gzip.open(materialized,'xt',encoding='utf8')as outgoing:
            for line in incoming:
                require(time.monotonic()<deadline,'feature_materialization_wall_budget')
                item=json.loads(line);callback,request=validate_row(item,plan['training_contract'])
                require(callback['sequence']>last_sequence,'eligible_rows_actual_callback_order');last_sequence=callback['sequence']
                require(request['request_id'] not in seen,'one_row_per_actual_request');seen.add(request['request_id'])
                adapted,normalization=normalize_callback(callback)
                current_context=copy.deepcopy(context);current_context['owner_scope']=callback['owner_id']
                forecast=arrays.predict(current_context,checkpoint,now=callback['now'],owner=callback['owner_id'],observed_counts=None)
                mapped=projection.project(forecast,mapping)
                wrapped,audit=public.wrap_record(adapted,mapped,episode_id=plan['training_contract']['parent_group'],episode_end=59400.)
                candidates=public.proposal_actions(adapted);candidate=candidates[0]
                require(candidate['source_proposal_sha256']==digest(callback['decision']['intents'][0]),'chosen_action_feature_semantics')
                row={'observation':wrapped,'action':candidate['semantic'],'target_value':item['target_value'],
                     'split':'train','parent_group':item['parent_group']}
                features=value.features(wrapped,row['action']);rows.append(row);label_ends.append(item['behavior_label']['label_end'])
                if len(pairs)<3 and callback['sequence']not in pair_sequences:
                    pair=diagnostic_pair(callback,wrapped,candidates)
                    if pair is not None:pairs.append(pair);pair_sequences.add(callback['sequence'])
                meta={'request_id':request['request_id'],'normalization':normalization,'feature_sha256':digest(features),
                    'forecast_sha256':digest(mapped),'input_evidence_sha256':digest(item),'label_end':label_ends[-1],
                    'observed_counts':None,'counterfactual_protection_certified':False,'account_adapter':audit}
                metadata.append(meta);outgoing.write(json.dumps({'row':row,'evidence':meta},separators=(',',':'),allow_nan=False)+'\n')
        require(len(rows)==plan['expected_rows'] and len(rows)>=12,'all_readiness_rows_materialized_exactly')
        write(output/'materialization.json',{'row_count':len(rows),'rows':ref(materialized),'records':metadata,
            'source_schema_normalization':'only row.schema v2->v1 on a deep copy; original digest retained',
            'actual_label_end_max':max(label_ends),'parent_count':1,'forecaster_forward_calls':len(rows)})
        report['materialization_seconds']=time.monotonic()-started
        write(output/'fixed_diagnostic_pairs.json',{'contract':plan['diagnostic_contract'],'pairs':pairs,
            'actual_pair_count':len(pairs),'selected_before_fitting':True,'target_values_not_used_for_pair_selection':True,
            'insufficient_pairs_not_fabricated':len(pairs)<3})
        diagnostics=[]
        for seed in SEEDS:
            report['fit_calls_started']+=1
            model=value.fit(rows,information_variant='static_plan',seed=seed,epochs=EPOCHS,
                deadline=min(deadline,time.monotonic()+plan['fit_seconds_per_seed']),objective=plan['objective'])
            predictions=value.predict(model,[r['observation']for r in rows],[r['action']for r in rows])
            require(len(predictions)==len(rows) and all(math.isfinite(p)for p in predictions),'actual_fitted_forward_finite')
            mse=math.fsum((p-r['target_value'])**2 for p,r in zip(predictions,rows,strict=True))/len(rows)
            model['behavior_evidence']={'schema':SCHEMA,'training_plan':ref(output/'plan.json'),'materialized_rows':ref(materialized),
                'single_training_trajectory':plan['training_contract']['parent_group'],'actual_training_labels_closed_at':max(label_ends),
                'model_first_permitted_sim_time':57600.,'checkpoint_selection':'fixed_final_epoch',
                'independent_validation_performed':False,'counterfactual_or_RL_target':False,'native_execution_authority':False}
            path=output/f'seed_{seed}_final.json';write(path,model)
            report['models'].append({'seed':seed,'epochs':EPOCHS,'checkpoint':ref(path),'content_sha256':digest(model),
                'training_mse':mse,'selected_by_development_or_test':False})
            diagnostics.append({'seed':seed,'checkpoint':ref(path),
                'pairs':[score_diagnostic(model,pair,value.predict)for pair in pairs]})
        write(output/'forecast_action_interaction_diagnostic.json',{'all_fixed_seeds':list(SEEDS),
            'fixed_pairs':ref(output/'fixed_diagnostic_pairs.json'),'results':diagnostics,
            'scope':'offline score sensitivity only, not observed alternative outcomes or control benefit',
            'native_consumption_performed':False,'model_selection_performed':False})
        validate(plan)
        report.update(status='completed_train_only_behavior_pretraining',training_rows=len(rows),all_fixed_seeds_saved=True,
            materialization=ref(output/'materialization.json'),fit_calls_completed=len(report['models']),source_exit_pins_passed=True,
            training_labels_closed_at=max(label_ends),model_first_permitted_sim_time=57600.,
            forecast_action_diagnostic=ref(output/'forecast_action_interaction_diagnostic.json'),
            independent_development_or_test=False,control_benefit_established=False,multistep_RL_established=False)
    except Exception:report['exception']=traceback.format_exc()
    report['wall_seconds']=time.monotonic()-started;write(output/'receipt.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--readiness',type=Path);parser.add_argument('--arrays-validation',type=Path)
    parser.add_argument('--readiness-registration',type=Path)
    parser.add_argument('--full-feature-audit',type=Path)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=prepare(args.readiness,args.arrays_validation,args.output,readiness_registration=args.readiness_registration,
        full_feature_audit=args.full_feature_audit)if args.prepare else run(args.output)
    print(json.dumps({'status':result['status'],'native_branches':0}))
    return 0 if result['status']in('prepared_not_executed','completed_train_only_behavior_pretraining')else 1


if __name__=='__main__':raise SystemExit(main())
