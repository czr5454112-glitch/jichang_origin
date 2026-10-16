"""Finite search fairness and strict model-predicate tests; no native oracle."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import public_native_preference_search as model
from test_g31_circulation_public_native_preference_projection import data
from test_g31_circulation_public_native_later_preference_projection import data as later_data


def table_evaluator(calls):
    def evaluate(action):
        key=action['key'];calls.append(key)
        completion={job:10. for job in model.initial.contract.JOBS}
        if key==(1,0):completion['loaded']=11.;completion['receiver']=1.
        if key==(1,1):completion={job:9. for job in completion}
        return {'status':'conditional_prediction','completion':completion,'completion_sum':sum(completion.values())}
    return evaluate


def test_strict_plateau_pair_and_enumeration_share_domain_and_budget_without_forced_equality():
    actions={key:{'key':key} for key in ((0,0),(0,1),(1,0),(1,1))}
    results={}
    for method in model.METHODS:
        calls=[];results[method]=model.search(actions,(0,0),table_evaluator(calls),method=method,budget=4)
        assert len(calls)==len(set(calls))<=4
        assert results[method]['candidate_denominator']==4 and len(results[method]['rows'])==4
        assert results[method]['native_protection_certified'] is False
    assert results['coordinate_strict']['selected_action']=={'key':(0,0)}
    for method in model.METHODS[1:]:assert results[method]['selected_action']=={'key':(1,1)}


def test_total_improvement_cannot_override_one_job_regression():
    actions={key:{'key':key} for key in ((0,0),(1,0))};calls=[]
    result=model.search(actions,(0,0),table_evaluator(calls),method='finite_horizon_enumeration',budget=2)
    assert result['selected_action']=={'key':(0,0)}
    assert result['rows'][1]['predicted_all_job_not_worse'] is False


def test_unknown_and_unexecuted_candidates_remain_in_denominator():
    actions={key:{'key':key} for key in ((0,0),(0,1),(1,0),(1,1))}
    result=model.search(actions,(0,0),lambda _: {'status':'unknown','completion':{}},
                        method='finite_horizon_enumeration',budget=4)
    assert result['selected_action'] is None and result['evaluations']==1
    assert sum(row['evaluation_status']=='unknown_unexecuted' for row in result['rows'])==3


def test_fixed_initial_windows_keep_all_four_later_components_and_charge_reference():
    bundle,_=data();before=copy.deepcopy(bundle)
    for index in range(4):
        result=model.initial_proposal(bundle,method='fixed_initial_window',fixed_window=index)
        assert result['candidate_denominator']==32 and result['selectable_denominator']==4
        assert result['evaluations']<=5 and result['evaluation_budget']==32
        if result['selected_action']:
            assert result['selected_action']['initial_action']=='native_default'
            assert result['selected_action']['empty_departure']==result['public_window_derivation']['supply_windows'][index]
    assert bundle==before


def test_current_later_search_uses_four_actions_and_keeps_past_return_inactive():
    result=model.later_proposal(later_data('first_reuse_route'),method='finite_horizon_enumeration')
    assert result['candidate_denominator']==result['evaluation_budget']==result['evaluations']==4
    assert result['inactive_coordinates']==['return_delay']
    assert result['selected_action']['return_delay']==0.
    assert result['native_protection_certified'] is False


@pytest.mark.parametrize('budget',[0,-1,True])
def test_invalid_evaluation_budget_rejects(budget):
    with pytest.raises(ValueError):model.search({(0,):{}},(0,),lambda _: {},method='incumbent',budget=budget)
