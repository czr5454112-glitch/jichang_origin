"""Pure fixtures and pre-existing training observations only; never formal raw."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).with_name('audit_formal.py')
spec = importlib.util.spec_from_file_location('formal_audit_fixture',PATH)
audit = importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


def design():
    models={s:{'path':f'model{s}.json','sha256':str(s)} for s in (17,29,43)}
    rows=[]
    for case in ('positive','negative'):
        baseline=case+'_baseline'
        rows.append({'task_id':baseline,'case':case,'mode':'baseline','model':None,'reference':None,'selection':'score'})
        for key,model in [('rule',None),*[(str(s),m) for s,m in models.items()]]:
            rows.append({'task_id':case+'_'+key,'case':case,'mode':'guarded','model':model,'reference':baseline,'selection':'score'})
    plan={'schema':'g31.foundation.preregistered_native_fqi_evaluation.v1','test_based_selection_allowed':False,
          'heldout_native_previously_executed':False,'native_branch_budget':10,'native_parallelism':1,'automatic_retries':0,'rows':rows}
    contract={'evaluation_plan':{'held_out_parent_groups':['positive','negative']}}
    selection={'status':'completed_selection_only','models':[{'seed':s,'checkpoint':m} for s,m in models.items()]}
    return plan,contract,selection


def test_full_denominator_and_all_seeds():
    assert set(audit.validate_design(*design()))=={17,29,43}


@pytest.mark.parametrize('mutation,reason', [
    ('drop_seed','ten_unique'),
    ('swap_weight','no_test_model'),
    ('change_reference','same_score_and_reference'),
    ('async','one_rule_and_three'),
    ('enable_test_selection','frozen_design_scope'),
    ('retry','frozen_budget')])
def test_invalid_evaluation_design_rejected(mutation,reason):
    plan,contract,selection=design()
    if mutation=='drop_seed':plan['rows'].pop()
    elif mutation=='swap_weight':plan['rows'][2]['model']={'path':'test_chosen.json','sha256':'unknown'}
    elif mutation=='change_reference':plan['rows'][1]['reference']='other'
    elif mutation=='async':plan['rows'][1]['mode']='async'
    elif mutation=='enable_test_selection':plan['test_based_selection_allowed']=True
    else:plan['automatic_retries']=1
    with pytest.raises(ValueError,match=reason):audit.validate_design(plan,contract,selection)


def candidates():
    return [{'action_id':a,'enabled':enabled} for a,enabled in [('native_default',True),('prefer_3',True),('prefer_8',False)]]


def predictions():
    return {a:{'completion':{'job':v}} for a,v in [('native_default',2.),('prefer_3',1.),('prefer_8',0.)]}


def test_learned_score_really_precedes_rule_and_never_enables_disabled():
    cs=candidates();ps=predictions()
    assert audit.ranking_choice(cs,ps,{})=='prefer_3'
    assert audit.ranking_choice(cs,ps,{'native_default':3.,'prefer_3':2.})=='native_default'
    with pytest.raises(ValueError,match='scores_only_enabled'):
        audit.ranking_choice(cs,ps,{'native_default':3.,'prefer_3':2.,'prefer_8':99.})


@pytest.mark.parametrize('value',[True,float('nan'),float('inf')])
def test_bad_model_scores_rejected(value):
    with pytest.raises(ValueError,match='finite_scores'):
        audit.ranking_choice(candidates(),predictions(),{'native_default':value,'prefer_3':2.})


def test_duplicate_candidates_rejected():
    cs=candidates();cs.append(copy.deepcopy(cs[0]))
    with pytest.raises(ValueError,match='unique_candidate_ids'):audit.ranking_choice(cs,predictions(),{})


def fixture_observation():
    view={'jobs':[{'arrival':1.,'status':'completed'},{'arrival':10.,'status':'unreleased'}],'now':2.,'owner_id':'B'}
    public={'local_view':{**view,'jobs':view['jobs'][:1]},'known_contracts':{'contracts':{}},
            'own_outbox':{},'at':2.,'owner':'B','delivered_v3':[],'remaining_horizon_s':38.,
            'privileged_evaluator_state_included':False,'reference_included':False}
    evidence={'information':{'raw_endpoints':{'view':view,'received':[]}},'retained':{'contracts':{}},'own_outbox':{}}
    decision={'observation':public,'selected_at':2.,'owner':'B'}
    return decision,evidence


def test_actual_observation_filters_future_jobs():
    decision,evidence=fixture_observation()
    audit.verify_observation(decision,evidence)
    decision['observation']['local_view']=evidence['information']['raw_endpoints']['view']
    with pytest.raises(ValueError,match='features_bound'):audit.verify_observation(decision,evidence)


def test_retained_and_delivered_cannot_be_invented():
    decision,evidence=fixture_observation()
    decision['observation']['known_contracts']={'contracts':{'future':'private'}}
    with pytest.raises(ValueError,match='features_bound'):audit.verify_observation(decision,evidence)
    decision,evidence=fixture_observation();decision['observation']['delivered_v3']=[{'invented':True}]
    with pytest.raises(ValueError,match='actual_messages'):audit.verify_observation(decision,evidence)


def test_unapproved_feature_source_not_executed():
    with pytest.raises(ValueError,match='approved_feature_source'):
        audit.public_features(b'raise RuntimeError("not executed")')


def test_unselected_action_semantic_cannot_be_swapped(monkeypatch):
    monkeypatch.setattr(audit,'verify_observation',lambda *_:None)
    candidates=[]
    for identity,target in [('native_default',None),('prefer_3',3),('prefer_8',8)]:
        candidates.append({'action_id':identity,'enabled':True,'semantic':{
            'operation_kind':'no_command' if target is None else 'route','source':7,'destination':target,'tray_id':'L',
            'earliest_legal_arrival':None if target is None else 3.+(2.8 if target==8 else 1.),
            'native_default_does_not_clear_preference':True}})
    decision={'behavior_selection':'score','resolved_behavior_preference':None,'worker_candidate_order':[],
              'worker_result_id':None,'candidate_mask':candidates,'selected_action_id':'prefer_8',
              'observation':{},'opportunity':{'service_ready_at':3.},'learned_ranking':None}
    current={'attempt':{'evidence':{'information':{'bundle':{'trays':{'L':{'service_ready_at':3.}}}}},
                        'model_report':{'candidate_results':predictions()}}}
    assert audit.verify_scoring(decision,current,None,None,lambda *_:{})['chosen']=='prefer_8'
    decision['candidate_mask'][1]['semantic']=copy.deepcopy(decision['candidate_mask'][2]['semantic'])
    with pytest.raises(ValueError,match='every_candidate_semantic'):
        audit.verify_scoring(decision,current,None,None,lambda *_:{})


def test_missing_layer_rejected_before_inference():
    names=[f'f{i:03d}' for i in range(123)]
    model={'native_execution_authority':False,'feature_names':names,'parameters':{
        'center':[0.]*123,'scale':[1.]*123,'target_center':0.,'target_scale':1.,'layers':[]}}
    model['model_sha256']=audit.digest(model)
    with pytest.raises(ValueError,match='finite_frozen_three_layer'):
        audit.forward(model,{}, {},lambda *_:{n:0. for n in names})


def test_incomplete_attempts_return_before_any_formal_raw_read(monkeypatch,tmp_path):
    plan,contract,selection=design()
    plan['source_collection_contract']={'path':'contract','sha256':'contractsha'}
    plan['frozen_selection']={'path':'selection','sha256':'selectionsha'}
    planpath=tmp_path/'evaluation.json';seen=[]
    def fake_read(path):
        path=str(path);seen.append(path)
        if path==str(planpath):return plan
        if path=='contract':return contract
        if path=='selection':return selection
        pytest.fail('formal raw or unregistered result read before all attempts closed: '+path)
    monkeypatch.setattr(audit,'read',fake_read)
    monkeypatch.setattr(audit,'sha',lambda p:audit.PLAN_SHA)
    monkeypatch.setattr(audit,'reference',lambda p:{'path':p,'sha256':p+'sha'})
    monkeypatch.setattr(audit,'attempt_for',lambda *_:None)
    monkeypatch.setattr(audit,'load_guard',lambda:pytest.fail('must not load result auditor yet'))
    report=audit.audit(planpath)
    assert report['status']=='awaiting_complete_evaluation' and report['formal_raw_results_read'] is False
    assert len(report['missing_tasks'])==10


def test_no_nonstdlib_or_native_imports():
    import ast
    tree=ast.parse(PATH.read_text())
    imports={a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names}
    assert imports<={'argparse','ast','gzip','hashlib','importlib','json','math'}

