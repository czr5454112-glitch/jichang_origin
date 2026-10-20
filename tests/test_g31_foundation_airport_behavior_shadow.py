"""Shadow orchestration with mocked detached operators; no native or fitting."""
from copy import deepcopy
import sys
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_shadow as shadow
from scripts.experiments.g31_ics_circulation import foundation_airport_behavior_training as training
import scripts.experiments.g31_ics_circulation as package


def record():
    return {'schema':'g31.foundation.airport_policy_observation.v2','sequence':7,'now':57840.,'owner_id':'A',
        'readonly':True,'native_execution_authority':False,'candidate_conditional_labels':None,
        'observation':{'now':57840.,'owner_id':'A','public_count':4},'policy_options':{'refresh':False},
        'decision':{'intents':[{'source':41,'destination':138},{'source':44,'destination':138}]}}


@pytest.fixture
def pipeline(monkeypatch):
    calls=[]
    forecast={'schema':'forecast_fixture','context_sha256':'public_plan','forecast_origin':57840.}
    def wrap(adapted,mapped,**kwargs):
        assert adapted['schema'].endswith('.v1') and kwargs['episode_end']==59400.
        return {'now':adapted['now'],'demand_forecast':mapped,'mapping_version':'actual_mapping',
            'information_variant':'static_plan','flight_context_sha256':'public_plan','count':adapted['observation']['public_count']},{'unknown_inbound_not_zero':True}
    def proposals(adapted):
        return [{'semantic':deepcopy(p),'source_proposal_sha256':shadow.digest(p),'enabled':None,'outcome_label':None}
            for p in adapted['decision']['intents']]
    def predict(context,checkpoint,**kwargs):
        calls.append(('forecast',kwargs));assert kwargs['observed_counts']is None
        return deepcopy(forecast)
    def validate(obs,descriptor):
        calls.append(('gate',descriptor['seed'],obs['now']))
        return SimpleNamespace(seed=descriptor['seed'],model_content_sha256='fixture')
    def features(obs,action):return {'public_count':obs['count'],'source':action['source']}
    def prepare(adapted,mapped,**kwargs):
        obs,audit=wrap(adapted,mapped,**kwargs)
        return SimpleNamespace(to_observation=lambda:deepcopy(obs)),audit,proposals(adapted)
    def matrix(current,actions):
        calls.append(('matrix',len(actions)))
        return SimpleNamespace(feature_rows=lambda:[features(current.to_observation(),a)for a in actions],
            actions=actions,actions_sha256=shadow.digest(actions))
    def value(current,matrix,model,**kwargs):
        calls.append(('forward',model.seed,len(matrix.actions)))
        return [float(model.seed+action['source'])for action in matrix.actions]
    modules={
        'foundation_airport_behavior_training':training,
        'foundation_airport_behavior_consumer':SimpleNamespace(prepare_behavior_checkpoint=validate,
            predict_prepared_behavior_checkpoint=value),
        'foundation_airport_learning_public':SimpleNamespace(prepare_record=prepare),
        'foundation_airport_learning_audit':SimpleNamespace(project=lambda forecast,mapping:deepcopy(forecast)),
        'foundation_flight_forecaster_arrays':SimpleNamespace(predict=predict),
        'foundation_action_value':SimpleNamespace(prepare_feature_matrix=matrix)}
    for name,module in modules.items():
        monkeypatch.setitem(sys.modules,package.__name__+'.'+name,module)
        monkeypatch.setattr(package,name,module,raising=False)
    kwargs={'model_descriptors':[{'seed':seed,'path':str(seed),'sha256':'file','training_receipt':{'path':'receipt','sha256':'receipt_hash'}}
            for seed in shadow.SEEDS],
        'flight_context':{'availability_basis':'static_predeclared','received_at':0.},'forecast_checkpoint':{},'mapping':{},'episode_id':'whole_trajectory'}
    return calls,modules,kwargs


def test_three_fixed_models_score_original_proposals_without_mutation_or_choice(pipeline):
    calls,_,kwargs=pipeline;original=record();before=deepcopy(original)
    result=shadow.score_record(original,**kwargs)
    assert result['status']=='completed_public_shadow_scoring' and original==before
    assert [row['seed']for row in result['models']]==[17,29,43]
    assert [c for c in calls if c[0]=='gate']==[('gate',17,57840.),('gate',29,57840.),('gate',43,57840.)]
    assert [c for c in calls if c[0]=='forward']==[('forward',17,2),('forward',29,2),('forward',43,2)]
    assert [c for c in calls if c[0]=='matrix']==[('matrix',2)]
    assert result['scores_used_for_selection']is False and result['native_runtime_verified_by_this_scorer']is False
    assert result['deployment_latency_certified']is False and result['full_callback_wall_must_be_recorded_by_wrapper']is True
    assert result['full_scorer_wall_seconds']>=sum(stage['wall_seconds']for stage in result['stages'])
    assert result['decision_sha256']==shadow.digest(before['decision']) and result['outcome_labels_created']==0


@pytest.mark.parametrize('mutation',['early','beyond_episode','wrong_episode','missing_seed','seed_order','true_authority','outcome_labels','no_intents'])
def test_invalid_or_early_callback_fails_before_forecast_and_model(pipeline,mutation):
    calls,_,kwargs=pipeline;original=record()
    if mutation=='early':original['now']=57659.99
    elif mutation=='beyond_episode':original['now']=59401.
    elif mutation=='wrong_episode':kwargs['episode_end']=40.
    elif mutation=='missing_seed':kwargs['model_descriptors'].pop()
    elif mutation=='seed_order':kwargs['model_descriptors'].reverse()
    elif mutation=='true_authority':original['native_execution_authority']=True
    elif mutation=='outcome_labels':original['candidate_conditional_labels']={'future':0.}
    else:original['decision']['intents']=[]
    before=deepcopy(original);result=shadow.score_record(original,**kwargs)
    assert result['status']=='failed_public_shadow_scoring' and calls==[] and original==before
    assert result['full_scorer_wall_seconds']>=0 and 'exception'in result


@pytest.mark.parametrize('mutation',['wrong_seed_weights','model_exception','missing_scores','nonfinite_scores','mutated_callback'])
def test_shadow_failure_never_becomes_success_or_action_authority(pipeline,mutation):
    _,modules,kwargs=pipeline;original=record()
    consumer=modules['foundation_airport_behavior_consumer']
    if mutation=='wrong_seed_weights':consumer.prepare_behavior_checkpoint=lambda o,d:SimpleNamespace(seed=17,model_content_sha256='fixture')
    elif mutation=='model_exception':
        def failure(*args,**kwargs):raise ValueError('bounded_fixture_model_failure')
        consumer.predict_prepared_behavior_checkpoint=failure
    elif mutation=='missing_scores':consumer.predict_prepared_behavior_checkpoint=lambda *args,**kwargs:[]
    elif mutation=='nonfinite_scores':consumer.predict_prepared_behavior_checkpoint=lambda *args,**kwargs:[float('nan'),0.]
    else:
        old=consumer.predict_prepared_behavior_checkpoint
        def changed(*args,**kwargs):
            original['decision']['intents'].clear();return old(*args,**kwargs)
        consumer.predict_prepared_behavior_checkpoint=changed
    result=shadow.score_record(original,**kwargs)
    assert result['status']=='failed_public_shadow_scoring'
    assert result['native_execution_authority']is False and result['scores_used_for_selection']is False
