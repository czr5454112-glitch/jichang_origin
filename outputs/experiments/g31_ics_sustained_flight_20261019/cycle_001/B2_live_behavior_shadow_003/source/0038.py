"""Explicit availability gate for train-only airport behavior checkpoints.

This is a score consumer, never a native guard or an execution authority.
Artifacts must be the registered final weights and closed training receipt.
The general action-value API intentionally keeps its existing contract.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

SCHEMA='g31.foundation.airport_behavior_consumer.v1'
EARLIEST_MODEL_USE=57600.


def require(ok,reason):
    if not ok:raise ValueError('airport_behavior_consumer:'+reason)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def read_bound(reference):
    data=Path(reference['path']).read_bytes()
    require(hashlib.sha256(data).hexdigest()==reference['sha256'],'artifact_file_sha256')
    return json.loads(data)


def validate_behavior_checkpoint(observation,checkpoint):
    """Check time before reading weights; validate exact completed artifacts."""
    now=observation.get('now')
    require(type(now)in(int,float) and math.isfinite(now) and now>=EARLIEST_MODEL_USE,
        'model_unavailable_before_registered_57600_cutoff')
    model=read_bound({'path':checkpoint['path'],'sha256':checkpoint['sha256']})
    receipt=read_bound(checkpoint['training_receipt'])
    require(receipt['status']=='completed_train_only_behavior_pretraining' and receipt['source_exit_pins_passed'] is True
        and receipt['all_fixed_seeds_saved'] is True and receipt['fit_calls_completed']==3
        and receipt['independent_development_or_test'] is False and receipt['control_benefit_established'] is False
        and receipt['multistep_RL_established'] is False,'closed_train_only_receipt')
    plan=read_bound(receipt['plan']);evidence=model['behavior_evidence']
    require(plan['schema']=='g31.foundation.airport_behavior_training.v1' and plan['seeds']==[17,29,43]
        and plan['epochs']==100 and plan['fit_calls']==3 and plan['native_branches']==0
        and plan['checkpoint_selection']=='none_all_fixed_final_epochs'
        and evidence['training_plan']==receipt['plan'],'immutable_training_plan_and_fixed_final_checkpoint')
    require(len(receipt['models'])==3 and sorted(r['seed']for r in receipt['models'])==[17,29,43],
        'all_three_fixed_seeds_no_selection')
    matching=[row for row in receipt['models']if row['checkpoint']=={'path':checkpoint['path'],'sha256':checkpoint['sha256']}]
    require(len(matching)==1 and matching[0]['seed']==model['seed'] and matching[0]['epochs']==model['epochs']==100
        and matching[0]['content_sha256']==digest(model) and matching[0]['selected_by_development_or_test'] is False,
        'actual_final_weights_and_content_hash')
    require(model['schema']=='g31.foundation.action_conditioned_value.v2'
        and model['feature_schema']=='g31.foundation.action_conditioned_features.v2'
        and observation['schema']=='g31.foundation.flight_aware_observation.v2'
        and observation['mapping_version']==model['mapping_version']
        and observation['information_variant']==model['information_variant']==plan['information_variant']=='static_plan',
        'consumer_schema_mapping_and_information_variant')
    cutoff=evidence['model_first_permitted_sim_time'];closed=evidence['actual_training_labels_closed_at']
    require(type(cutoff)in(int,float) and math.isfinite(cutoff) and cutoff==EARLIEST_MODEL_USE
        and cutoff==receipt['model_first_permitted_sim_time']==plan['training_contract']['earliest_model_use_sim_time']
        and type(closed)in(int,float) and math.isfinite(closed) and 43200.<=closed<=cutoff<=now
        and closed==receipt['training_labels_closed_at'],'exact_training_and_consumption_cutoffs')
    require(model['native_execution_authority'] is False and evidence['native_execution_authority'] is False
        and evidence['counterfactual_or_RL_target'] is False and evidence['independent_validation_performed'] is False,
        'behavior_scores_have_no_guard_or_execution_authority')
    source=Path(__file__).with_name('foundation_action_value.py').resolve()
    require(hashlib.sha256(source.read_bytes()).hexdigest()==plan['source_sha256'].get(str(source)),
        'fixed_trained_feature_and_numerical_implementation')
    return model


def predict_behavior_checkpoint(observation,actions,checkpoint):
    """All supplied actions still require the current complete native guard."""
    model=validate_behavior_checkpoint(observation,checkpoint)
    from . import foundation_action_value as value
    return value.predict(model,[observation]*len(actions),actions)
