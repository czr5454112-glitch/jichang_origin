"""Public-only scoring inside a separately registered native callback.

The caller owns target matching and a maximum-two-hit budget. This scorer
never submits, chooses, mutates or authorizes an action. A successful report
alone does not prove that its callback belonged to a live native session:
the registered wrapper and later actual submit/ACK/edge join must prove that.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import time
import traceback

SCHEMA='g31.foundation.airport_behavior_shadow.v1'
SEEDS=(17,29,43)


def require(ok,reason):
    if not ok:raise ValueError('airport_behavior_shadow:'+reason)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def score_record(record,*,model_descriptors,flight_context,forecast_checkpoint,mapping,episode_id,episode_end=59400.,
                 prepared_checkpoints=None):
    """Score every actual baseline proposal with all three frozen final models.

    Records are detached JSON data. Return a diagnostic report even on error;
    the wrapper must return the original baseline decision in either case.
    No outcome file, private flight-parent lookup or native object is accepted.
    """
    started=time.perf_counter_ns();wall_started=time.time_ns();cpu_started=time.process_time_ns()
    report={'schema':SCHEMA,'status':'failed_public_shadow_scoring','stages':[],'models':[],
        'native_execution_authority':False,'scores_used_for_selection':False,'model_chose_action':False,
        'outcome_labels_created':0,'native_runtime_verified_by_this_scorer':False,
        'full_callback_wall_must_be_recorded_by_wrapper':True,'deployment_latency_certified':False,
        'started_perf_counter_ns':started,'started_utc_epoch_ns':wall_started}
    def phase(name,operation):
        begin=time.perf_counter_ns();entry={'name':name,'started_perf_counter_ns':begin,'status':'failed'}
        try:
            value=operation();entry['status']='completed';return value
        finally:
            entry['finished_perf_counter_ns']=time.perf_counter_ns()
            entry['wall_seconds']=(entry['finished_perf_counter_ns']-begin)/1e9
            report['stages'].append(entry)
    try:
        before=digest(record);now=record['now']
        require(type(now)in(int,float) and math.isfinite(now) and 57660.<=now<=59400. and episode_end==59400.,
            'registered_late_callback_and_59400_episode_semantics')
        require([item['seed']for item in model_descriptors]==list(SEEDS),'all_fixed_three_final_seeds_in_order')
        require(prepared_checkpoints is None or len(prepared_checkpoints)==len(model_descriptors),
            'all_prepared_checkpoints_in_fixed_order')
        require(record['readonly'] is True and record['native_execution_authority'] is False
            and record['candidate_conditional_labels'] is None and record['decision']['intents'],
            'actual_public_baseline_intents_without_outcome_labels')
        require(type(record['policy_options'])is dict,'actual_callback_policy_options')
        report.update(callback_sequence=record['sequence'],owner=record['owner_id'],at=now,
            callback_record_sha256=before,observation_sha256=digest(record['observation']),
            policy_options_sha256=digest(record['policy_options']),decision_sha256=digest(record['decision']),
            episode_id=episode_id,episode_end=episode_end,observed_counts=None)
        def imports():
            from . import foundation_airport_behavior_training as training
            from . import foundation_airport_behavior_consumer as consumer
            from . import foundation_airport_learning_public as public
            from . import foundation_airport_learning_audit as projection
            from . import foundation_flight_forecaster_arrays as arrays
            from . import foundation_action_value as value
            return training,consumer,public,projection,arrays,value
        training,consumer,public,projection,arrays,value=phase('load_public_scoring_modules',imports)
        adapted,normalization=phase('lossless_record_schema_adapter',lambda:training.normalize_callback(record))
        context=copy.deepcopy(flight_context);context['owner_scope']=record['owner_id']
        require(context['availability_basis']=='static_predeclared' and context['received_at']==0.,
            'same_explicit_static_predeclared_plan_assumption')
        regional=phase('B1_current_public_prior_forecast',lambda:arrays.predict(context,forecast_checkpoint,
            now=now,owner=record['owner_id'],observed_counts=None))
        mapped=phase('public_region_mapping',lambda:projection.project(regional,mapping))
        current,account_audit,candidates=phase('public_six_account_and_forecast_adapter',lambda:public.prepare_record(adapted,mapped,
            episode_id=episode_id,episode_end=episode_end))
        require(len(candidates)==len(record['decision']['intents']) and all(candidate['enabled']is None
            and candidate['outcome_label']is None and candidate['source_proposal_sha256']==digest(proposal)
            for candidate,proposal in zip(candidates,record['decision']['intents'],strict=True)),
            'exact_original_proposal_list_no_invented_candidates_or_guard')
        actions=[candidate['semantic']for candidate in candidates]
        matrix=phase('public_action_features',lambda:value.prepare_feature_matrix(current,actions))
        features=matrix.feature_rows()
        wrapped=current.to_observation()
        report.update(normalization=normalization,regional_forecast_sha256=digest(regional),
            mapped_forecast_sha256=digest(mapped),forecast=wrapped['demand_forecast'],
            model_observation_sha256=digest(wrapped),mapping_version=wrapped['mapping_version'],
            information_variant=wrapped['information_variant'],flight_context_sha256=wrapped['flight_context_sha256'],
            account_adapter=account_audit,candidates=candidates,features=features,features_sha256=digest(features),
            actual_baseline_first_proposal_index=0,baseline_selection_changed=False,
            current_context_build_count=1,feature_matrix_build_count=1,
            feature_matrix_actions_sha256=matrix.actions_sha256,
            prepared_static_checkpoints_used=prepared_checkpoints is not None)
        for index,descriptor in enumerate(model_descriptors):
            def forward():
                checkpoint=(consumer.prepare_behavior_checkpoint(wrapped,descriptor) if prepared_checkpoints is None
                    else prepared_checkpoints[index])
                require(checkpoint.seed==descriptor['seed'],'descriptor_seed_matches_actual_registered_weights')
                return consumer.predict_prepared_behavior_checkpoint(current,matrix,checkpoint,descriptor=descriptor),checkpoint.model_content_sha256
            scores,content_sha=phase('seed_'+str(descriptor['seed'])+'_gated_model_forward',forward)
            require(len(scores)==len(actions) and all(type(score)in(int,float) and math.isfinite(score)for score in scores),
                'all_original_proposals_have_finite_scores')
            report['models'].append({'seed':descriptor['seed'],'checkpoint':copy.deepcopy(descriptor),
                'model_content_sha256':content_sha,'scores':scores,'scores_sha256':digest(scores),
                'used_as_native_guard':False,'used_for_selection':False})
        require(digest(record)==before,'original_public_callback_and_baseline_decision_unmodified')
        report.update(status='completed_public_shadow_scoring',all_fixed_seeds_scored=True,
            original_callback_unchanged=True,candidate_count=len(candidates),fit_calls=0)
    except Exception:report['exception']=traceback.format_exc()
    report['finished_perf_counter_ns']=time.perf_counter_ns();report['finished_utc_epoch_ns']=time.time_ns()
    report['full_scorer_wall_seconds']=(report['finished_perf_counter_ns']-started)/1e9
    report['process_cpu_seconds']=(time.process_time_ns()-cpu_started)/1e9
    report['full_scorer_timing_scope']='function entry through validation/imports/forecast/features/all three gated forwards/report assembly; wrapper and storage overhead measured separately'
    return report
