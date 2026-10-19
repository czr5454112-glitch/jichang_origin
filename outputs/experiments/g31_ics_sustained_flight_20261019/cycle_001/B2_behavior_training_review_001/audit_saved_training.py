"""Small stdlib audit of saved B2 fits; no forward, fitting or native calls."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time


def require(ok,reason):
    if not ok:raise ValueError(reason)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def ref(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def read(path):return json.loads(Path(path).read_bytes())
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def bound(reference):
    require(ref(reference['path'])==reference,'exact_artifact_bytes')
    return read(reference['path'])
def write(path,value):
    with path.open('x',encoding='utf8')as f:json.dump(value,f,indent=2,allow_nan=False)


def run(training,registration,output):
    started=time.perf_counter();training=Path(training).resolve();output=Path(output).resolve()
    receipt=read(training/'receipt.json');plan=bound(receipt['plan']);reg=read(registration)
    outer_path=Path(registration).with_name('receipt.json');outer=read(outer_path)
    require(receipt['status']=='completed_train_only_behavior_pretraining' and receipt['source_exit_pins_passed'] is True,
        'actual_completed_training')
    require(reg['task_id']==training.name and reg['args']==['--run','--output',str(training)]
        and reg['source_pins'][str(training/'plan.json')]==sha(training/'plan.json')
        and outer['status']=='completed' and outer['source_changed']==[] and outer['process']['exitcode']==0
        and outer['assessment']==receipt,'actual_launcher_and_inner_assessment_match')
    archive={}
    for index,(source,expected)in enumerate(reg['source_pins'].items()):
        if source not in plan['source_sha256']:continue
        archived=Path(registration).parent/'source'/(f'{index:04d}'+Path(source).suffix)
        require(sha(archived)==expected==plan['source_sha256'][source],'exact_executed_training_source_archive')
        archive[source]=ref(archived)
    require(set(archive)==set(plan['source_sha256']),'all_training_sources_archived')
    require(plan['seeds']==[17,29,43] and plan['epochs']==100 and plan['fit_calls']==3
        and plan['native_branches']==0 and plan['checkpoint_selection']=='none_all_fixed_final_epochs'
        and plan['information_variant']=='static_plan' and plan['observed_counts']is None,'fixed_training_scope')
    require(receipt['training_rows']==plan['expected_rows']==81 and receipt['fit_calls_completed']==3
        and receipt['all_fixed_seeds_saved']is True and receipt['independent_development_or_test']is False
        and receipt['control_benefit_established']is False and receipt['multistep_RL_established']is False,'honest_train_only_claims')
    materialization=bound(receipt['materialization'])
    require(materialization['row_count']==81 and materialization['parent_count']==1
        and materialization['forecaster_forward_calls']==81 and len(materialization['records'])==81
        and ref(materialization['rows']['path'])==materialization['rows'],'actual_materialized_rows')
    require(all(row['normalization']['raw_modified']is False and row['normalization']['only_changed_field']=='schema'
        and row['observed_counts']is None and row['counterfactual_protection_certified']is False
        for row in materialization['records']),'original_callbacks_and_unknown_counts_preserved')
    require(receipt['model_first_permitted_sim_time']==57600.
        and 43200.<=receipt['training_labels_closed_at']<=57600.,'actual_model_availability_cutoff')
    metrics=[];descriptors=[]
    require([row['seed']for row in receipt['models']]==[17,29,43],'all_fixed_seed_order')
    for saved in receipt['models']:
        model=bound(saved['checkpoint']);parameters=model['parameters'];names=model['feature_names']
        require(saved['content_sha256']==digest(model) and saved['selected_by_development_or_test']is False
            and model['seed']==saved['seed'] and model['epochs']==saved['epochs']==100,'actual_final_model_content')
        require(model['schema']=='g31.foundation.action_conditioned_value.v2' and model['feature_schema']=='g31.foundation.action_conditioned_features.v2'
            and model['information_variant']=='static_plan' and model['training_row_count']==81
            and model['training_parent_groups']==[plan['training_contract']['parent_group']]
            and model['native_execution_authority']is False and model['device']=='cpu','actual_model_scope')
        require(len(names)==88 and names==sorted(set(names)) and not any('job_id'in n or 'tray_id'in n or 'request_id'in n for n in names),
            '88_features_without_opaque_identity_coordinates')
        require(len(parameters['center'])==len(parameters['scale'])==88
            and all(type(v)in(int,float) and math.isfinite(v)for v in parameters['center'])
            and all(type(v)in(int,float) and math.isfinite(v) and v>0 for v in parameters['scale']), 'finite_positive_normalization')
        require(len(parameters['layers'])==3,'three_actual_weight_layers')
        for layer,(n_in,n_out)in zip(parameters['layers'],((88,64),(64,64),(64,1)),strict=True):
            require(len(layer['weight'])==n_out and all(len(row)==n_in for row in layer['weight'])
                and len(layer['bias'])==n_out and all(type(v)in(int,float) and math.isfinite(v)
                for row in layer['weight']for v in row) and all(math.isfinite(v)for v in layer['bias']), 'actual_finite_64x64_weights')
        curve=model['training_curve']
        require([point['epoch']for point in curve]==list(range(0,101,10))
            and all(math.isfinite(point['mse']) and point['mse']>=0 for point in curve)
            and math.isfinite(saved['training_mse']) and saved['training_mse']>=0,'actual_complete_loss_curve')
        evidence=model['behavior_evidence']
        require(evidence['training_plan']==receipt['plan'] and evidence['materialized_rows']==materialization['rows']
            and evidence['model_first_permitted_sim_time']==57600. and evidence['actual_training_labels_closed_at']==receipt['training_labels_closed_at']
            and evidence['counterfactual_or_RL_target']is False,'weight_training_evidence')
        metrics.append({'seed':saved['seed'],'checkpoint':saved['checkpoint'],'content_sha256':saved['content_sha256'],
            'initial_training_curve_mse':curve[0]['mse'],'final_training_curve_mse':curve[-1]['mse'],
            'saved_full_training_forward_mse':saved['training_mse'],'saved_full_training_forward_rmse':math.sqrt(saved['training_mse'])})
        descriptors.append({'seed':saved['seed'],**saved['checkpoint'],'training_receipt':ref(training/'receipt.json')})
    diagnostic=bound(receipt['forecast_action_diagnostic']);pairs=bound(diagnostic['fixed_pairs'])
    require(pairs['selected_before_fitting']is True and pairs['target_values_not_used_for_pair_selection']is True
        and pairs['actual_pair_count']==len(pairs['pairs'])<=3 and pairs['contract']==plan['diagnostic_contract']
        and [row['seed']for row in diagnostic['results']]==[17,29,43]
        and diagnostic['model_selection_performed']is False and diagnostic['native_consumption_performed']is False,
        'fixed_input_interventions_all_three_seeds_not_model_selection')
    interaction=[]
    for seed in diagnostic['results']:
        require(len(seed['pairs'])==len(pairs['pairs']),'same_fixed_pairs_for_every_seed')
        for row,pair in zip(seed['pairs'],pairs['pairs'],strict=True):
            require(row['pair_sha256']==digest(pair) and row['callback_sequence']==pair['callback_sequence']
                and set(row['scores'])=={'actual_forecast','forecast_values_masked','zero_new_demand'}, 'same_actual_diagnostic_pairs')
            gaps={name:scores[0]-scores[1]for name,scores in row['scores'].items()}
            deltas={name:gap-gaps['actual_forecast']for name,gap in gaps.items()if name!='actual_forecast'}
            require(gaps==row['chosen_minus_other_score'] and deltas==row['gap_change_from_actual_forecast']
                and row['numerical_nonadditivity_at_1e_minus_8']==any(abs(v)>1e-8 for v in deltas.values())
                and row['physical_control_benefit_established']is False and row['counterfactual_outcome_labels_created']is False,
                'exact_gap_arithmetic_and_limited_claim')
            interaction.append({'seed':seed['seed'],'callback_sequence':row['callback_sequence'],
                'score_gaps':gaps,'changes':deltas,'numerically_nonadditive':row['numerical_nonadditivity_at_1e_minus_8']})
    descriptor_artifact={'schema':'g31.airport_behavior_shadow_models.v1','training_receipt':ref(training/'receipt.json'),
        'training_plan':receipt['plan'],'training_registration':ref(registration),'training_outer_receipt':ref(outer_path),
        'model_descriptors':descriptors,'all_fixed_seeds_no_selection':True,'minimum_consumption_sim_time':57600.,
        'native_execution_authority':False,'actual_native_model_consumptions_at_preparation':0}
    write(output/'shadow_model_descriptors.json',descriptor_artifact)
    report={'schema':'g31.airport_behavior_saved_training_review.v1','status':'saved_weights_curves_and_diagnostics_passed',
        'source':ref(__file__),'training_receipt':ref(training/'receipt.json'),'training_plan':receipt['plan'],
        'training_outer_receipt':ref(outer_path),'executed_source_archives':archive,'training_rows':81,'independent_parent_count':1,
        'metrics':metrics,'interaction_diagnostics':interaction,'fixed_pair_count':len(pairs['pairs']),
        'descriptor_artifact':ref(output/'shadow_model_descriptors.json'),'inner_training_wall_seconds':receipt['wall_seconds'],
        'outer_training_wall_seconds':outer['process']['wall_seconds'],'independent_forward_recomputed':False,
        'actual_native_consumption_established':False,'control_benefit_established':False,'multistep_RL_established':False,
        'scope':'Checks saved actual weights, full epoch curves, frozen provenance and exact diagnostic arithmetic; training forward MSE is producer-recorded, not independently recomputed.',
        'audit_wall_seconds':time.perf_counter()-started}
    write(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--training',type=Path,required=True)
    parser.add_argument('--registration',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=run(args.training,args.registration,args.output)
    print(json.dumps({k:result[k]for k in ('status','training_rows','metrics','interaction_diagnostics','audit_wall_seconds')},indent=2))
