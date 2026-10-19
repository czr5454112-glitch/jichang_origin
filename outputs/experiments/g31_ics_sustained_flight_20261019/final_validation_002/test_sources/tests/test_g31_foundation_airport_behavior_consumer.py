"""Availability/provenance gates with fixture artifacts, no fitted models."""
import hashlib
import json
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_consumer as consumer


def save(path,value):
    path.write_text(json.dumps(value),encoding='utf8')
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def fixture(tmp_path):
    source=Path(consumer.__file__).with_name('foundation_action_value.py').resolve()
    plan={'schema':'g31.foundation.airport_behavior_training.v1','seeds':[17,29,43],'epochs':100,'fit_calls':3,
        'native_branches':0,'checkpoint_selection':'none_all_fixed_final_epochs','information_variant':'static_plan',
        'source_sha256':{str(source):hashlib.sha256(source.read_bytes()).hexdigest()},
        'training_contract':{'earliest_model_use_sim_time':57600.}}
    pref=save(tmp_path/'plan.json',plan);models=[]
    for seed in (17,29,43):
        model={'schema':'g31.foundation.action_conditioned_value.v2','feature_schema':'g31.foundation.action_conditioned_features.v2',
            'information_variant':'static_plan','mapping_version':'fixture_mapping','seed':seed,'epochs':100,
            'native_execution_authority':False,'behavior_evidence':{'training_plan':pref,'model_first_permitted_sim_time':57600.,
                'actual_training_labels_closed_at':54000.,'native_execution_authority':False,
                'counterfactual_or_RL_target':False,'independent_validation_performed':False}}
        mref=save(tmp_path/f'seed_{seed}.json',model)
        models.append({'seed':seed,'epochs':100,'checkpoint':mref,'content_sha256':consumer.digest(model),
            'selected_by_development_or_test':False})
    receipt={'status':'completed_train_only_behavior_pretraining','source_exit_pins_passed':True,
        'all_fixed_seeds_saved':True,'fit_calls_completed':3,'independent_development_or_test':False,
        'control_benefit_established':False,'multistep_RL_established':False,'plan':pref,'models':models,
        'model_first_permitted_sim_time':57600.,'training_labels_closed_at':54000.}
    rref=save(tmp_path/'receipt.json',receipt)
    checkpoint={**models[0]['checkpoint'],'training_receipt':rref}
    observation={'now':57600.,'schema':'g31.foundation.flight_aware_observation.v2',
        'mapping_version':'fixture_mapping','information_variant':'static_plan'}
    return observation,checkpoint


def test_exact_registered_final_weights_allowed_only_at_or_after_cutoff(tmp_path):
    observation,checkpoint=fixture(tmp_path)
    assert consumer.validate_behavior_checkpoint(observation,checkpoint)['seed']==17
    observation['now']=58000.
    assert consumer.validate_behavior_checkpoint(observation,checkpoint)['epochs']==100


@pytest.mark.parametrize('now',[0.,43200.,57599.999,None,True,float('nan')])
def test_time_gate_rejects_before_any_weight_read(now,monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Weights must not be read before availability gate')
    monkeypatch.setattr(Path,'read_bytes',forbidden)
    with pytest.raises(ValueError,match='unavailable_before_registered'):consumer.predict_behavior_checkpoint({'now':now},[],{})


@pytest.mark.parametrize('mutation',['mapping','schema','variant','file_hash','content_hash','receipt_status','seed_subset','picked_seed','future_labels','authority','cutoff'])
def test_consumer_rejects_unbound_or_incompatible_artifacts(tmp_path,mutation):
    observation,checkpoint=fixture(tmp_path)
    if mutation=='mapping':observation['mapping_version']='other'
    elif mutation=='schema':observation['schema']='old'
    elif mutation=='variant':observation['information_variant']='no_plan'
    elif mutation=='file_hash':checkpoint['sha256']='wrong'
    else:
        path=Path(checkpoint['training_receipt']['path']);receipt=json.loads(path.read_bytes())
        if mutation=='content_hash':receipt['models'][0]['content_sha256']='wrong'
        elif mutation=='receipt_status':receipt['status']='failed_train_only_behavior_pretraining'
        elif mutation=='seed_subset':receipt['models']=receipt['models'][:1]
        elif mutation=='picked_seed':receipt['models'][0]['selected_by_development_or_test']=True
        elif mutation=='future_labels':receipt['training_labels_closed_at']=57601.
        elif mutation=='cutoff':receipt['model_first_permitted_sim_time']=43200.
        else:receipt['control_benefit_established']=True
        checkpoint['training_receipt']=save(path,receipt)
    with pytest.raises(ValueError):consumer.validate_behavior_checkpoint(observation,checkpoint)
