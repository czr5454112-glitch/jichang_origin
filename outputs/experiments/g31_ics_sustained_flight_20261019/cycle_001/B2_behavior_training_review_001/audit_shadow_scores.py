"""Independently recompute live shadow saved-vector scores, standard library only.

The separate physical-chain audit must bind the original callback to its
actual request/ACK/edge. This audit never treats scoring alone as that proof.
"""
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


def forward(model,features):
    p=model['parameters'];names=model['feature_names']
    require(len(names)==88 and names==sorted(features),'exact_88_feature_coordinates')
    require(len(p['center'])==len(p['scale'])==88 and all(math.isfinite(v) and v>0 for v in p['scale']),
        'frozen_training_normalizer')
    x=[(features[name]-center)/scale for name,center,scale in zip(names,p['center'],p['scale'],strict=True)]
    require(all(math.isfinite(v)for v in x) and len(p['layers'])==3,'finite_three_layer_input')
    for index,(layer,nout)in enumerate(zip(p['layers'],(64,64,1),strict=True)):
        require(len(layer['weight'])==len(layer['bias'])==nout and all(len(row)==len(x)for row in layer['weight']),
            'frozen_64x64_matrix_shapes')
        x=[math.fsum(w*v for w,v in zip(row,x,strict=True))+bias
            for row,bias in zip(layer['weight'],layer['bias'],strict=True)]
        if index<2:x=[math.tanh(v)for v in x]
    result=x[0]*p['target_scale']+p['target_center'];require(math.isfinite(result),'finite_independent_forward')
    return result


def run(shadow,registration,output):
    started=time.perf_counter();shadow=Path(shadow).resolve();output=Path(output).resolve()
    plan=read(shadow/'plan.json');receipt=read(shadow/'receipt.json');reg=read(registration)
    outer_path=Path(registration).with_name('receipt.json');outer=read(outer_path)
    require(reg['task_id']==shadow.name and reg['source_pins'][str(shadow/'plan.json')]==sha(shadow/'plan.json')
        and outer['status']=='completed' and outer['source_changed']==[] and outer['process']['exitcode']==0
        and outer['assessment']==receipt,'registered_actual_native_launcher_closed')
    require(receipt['plan_sha256_at_launch']==sha(shadow/'plan.json') and receipt['process']['exitcode']==0
        and receipt['worker_report']['native_session_attempted']is True
        and receipt['worker_report']['acceptance_status']=='closed_run_acceptance_passed'
        and receipt['worker_report']['final_physical_time']==59400.,'real_continuous_native_run_closed_at_59400')
    source_archive={}
    for source,relative in plan['source_archive'].items():
        archived=shadow/relative
        require(sha(archived)==plan['source_sha256'][source],'immutable_actual_native_source_archive')
        source_archive[source]=ref(archived)
    targets=bound(plan['behavior_shadow']['runtime_targets'])
    diagnostic_path=shadow/'C00/behavior_shadow_receipt.json';diagnostic=read(diagnostic_path)
    require(diagnostic['registered_targets']==diagnostic['actual_hits']==len(targets)==2
        and diagnostic['all_targets_hit']is True and diagnostic['all_shadow_scores_completed']is True
        and diagnostic['recording_errors']==[] and diagnostic['policy_gain_established']is False,
        'exact_two_runtime_hits_no_retries_or_failed_shadow')
    require(ref(diagnostic['event_artifact']['path'])==diagnostic['event_artifact'],'saved_actual_event_stream')
    rows=[];maximum_error=0.;forward_count=0
    for event,target in zip(diagnostic['results'],targets,strict=True):
        scorer=event['scorer'];identity=target['callback']
        require(event['status']=='completed_shadow_scoring_only' and event['identity']==identity
            and event['actual_sequence']==identity['sequence'] and event['actual_owner']==identity['owner_id']
            and event['actual_now']==identity['now'] and event['actual_residual_index']==identity['residual_index']
            and event['original_decision_object_returned']is True and event['score_selects_action']is False,
            'actual_runtime_callback_identity_and_unchanged_baseline')
        require(scorer['status']=='completed_public_shadow_scoring' and scorer['callback_sequence']==identity['sequence']
            and scorer['owner']==identity['owner_id'] and scorer['at']==identity['now']>=57660.
            and scorer['episode_end']==59400. and scorer['all_fixed_seeds_scored']is True
            and scorer['original_callback_unchanged']is True and scorer['scores_used_for_selection']is False
            and scorer['model_chose_action']is False and scorer['outcome_labels_created']==0,
            'live_public_scoring_scope_no_selection_or_labels')
        require(scorer['features_sha256']==digest(scorer['features']) and scorer['candidate_count']==len(scorer['features'])
            ==len(scorer['candidates'])>0 and all(c['enabled']is None and c['outcome_label']is None for c in scorer['candidates']),
            'saved_public_feature_and_proposal_vectors')
        forecast=scorer['forecast']
        require(forecast['owner_scope']==identity['owner_id'] and forecast['forecast_origin']==identity['now']
            and forecast['context_sha256']==scorer['flight_context_sha256']
            and forecast['mapping_version']==scorer['mapping_version']
            and all(v is None or v<=identity['now']for v in forecast['information_cutoffs'].values())
            and scorer['observed_counts']is None,'current_prior_only_public_forecast_cutoffs')
        for region,missing in forecast['missing_mask_by_region'].items():
            values=forecast['new_demand_mean_by_region'][region]
            require((all(v is None for v in values)if missing else all(type(v)in(int,float) and math.isfinite(v) and v>=0 for v in values)),
                'unknown_demand_not_fabricated_zero')
        require([m['seed']for m in scorer['models']]==[17,29,43],'all_three_fixed_models_in_runtime_callback')
        independent=[]
        for saved in scorer['models']:
            descriptor=saved['checkpoint'];model=bound({'path':descriptor['path'],'sha256':descriptor['sha256']})
            training=bound(descriptor['training_receipt'])
            matched=[row for row in training['models']if row['checkpoint']=={'path':descriptor['path'],'sha256':descriptor['sha256']}]
            require(len(matched)==1 and model['seed']==saved['seed']==descriptor['seed']
                and saved['model_content_sha256']==digest(model)==matched[0]['content_sha256']
                and model['mapping_version']==scorer['mapping_version'] and model['information_variant']=='static_plan'
                and training['model_first_permitted_sim_time']==model['behavior_evidence']['model_first_permitted_sim_time']==57600.
                and training['source_exit_pins_passed']is True,'actual_closed_training_weights_and_runtime_model_identity')
            actual=[forward(model,vector)for vector in scorer['features']];forward_count+=len(actual)
            require(len(actual)==len(saved['scores']) and digest(saved['scores'])==saved['scores_sha256'], 'every_saved_score_present')
            errors=[abs(a-b)for a,b in zip(actual,saved['scores'],strict=True)]
            require(all(math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-6)for a,b in zip(actual,saved['scores'],strict=True)),
                'independent_stdlib_forward_matches_actual_native_callback_scores')
            maximum_error=max(maximum_error,*errors)
            independent.append({'seed':saved['seed'],'candidate_scores':actual,'maximum_absolute_difference':max(errors)})
        start,end=scorer['started_perf_counter_ns'],scorer['finished_perf_counter_ns']
        require(end>=start and math.isclose(scorer['full_scorer_wall_seconds'],(end-start)/1e9,rel_tol=0,abs_tol=1e-12)
            and all(start<=stage['started_perf_counter_ns']<=stage['finished_perf_counter_ns']<=end
                and stage['status']=='completed'for stage in scorer['stages']),'all_actual_scoring_phases_within_full_scorer_wall')
        callback=event['entire_recorded_callback_elapsed_including_all_storage_seconds']
        require(callback>=event['callback_elapsed_before_return_seconds_including_storage']>=scorer['full_scorer_wall_seconds']
            >=sum(stage['wall_seconds']for stage in scorer['stages']) and event['complete_request_100ms_certified']is False,
            'full_recorded_callback_includes_scorer_and_storage_not_only_forecast_time')
        rows.append({'identity':identity,'canonical_public_callback_sha256':scorer['callback_record_sha256'],
            'full_scorer_wall_seconds':scorer['full_scorer_wall_seconds'],'full_recorded_callback_wall_seconds':callback,
            'scorer_process_cpu_seconds':scorer['process_cpu_seconds'],'candidate_count':scorer['candidate_count'],
            'independent_scores':independent})
    report={'schema':'g31.airport_live_shadow_independent_score_review.v1','status':'saved_live_feature_forwards_and_timings_verified',
        'source':ref(__file__),'plan':ref(shadow/'plan.json'),'receipt':ref(shadow/'receipt.json'),
        'outer_receipt':ref(outer_path),'shadow_receipt':ref(diagnostic_path),'source_archive_count':len(source_archive),
        'callbacks':rows,'scalar_forwards_recomputed':forward_count,'maximum_absolute_score_difference':maximum_error,
        'actual_native_run_source_bound':True,'original_raw_callback_to_request_ACK_edge_join_done_by_this_audit':False,
        'physical_chain_audit_still_required':True,'score_affected_baseline_selection':False,'heldout_evaluation':False,
        'control_benefit_established':False,'native100ms_certified':False,'fit_calls':0,'native_calls_by_auditor':0,
        'audit_wall_seconds':time.perf_counter()-started}
    with output.open('x',encoding='utf8')as f:json.dump(report,f,indent=2,allow_nan=False)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--shadow',type=Path,required=True)
    parser.add_argument('--registration',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();r=run(a.shadow,a.registration,a.output)
    print(json.dumps({k:r[k]for k in ('status','scalar_forwards_recomputed','maximum_absolute_score_difference','callbacks','audit_wall_seconds')},indent=2))
