"""Pure independent-family arithmetic. No native/predictor or raw96 scan."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import audit_live_obligation_historical as a


def fixture():
    plan={'branch_order':a.c.ORDER,'rows':a.c.prior.probe_rows()}
    details={k:{'new_status':'assessed','independent_error':None,'independent_replay':{},
        'physical':{'full_H40':True,'all_five_complete':True,'audit':{'status':'passed'},
            'completion':{j:10. for j in a.JOBS}},'all_required_inputs_verified':True,
        'selected_actions_executed':True} for k in a.c.ORDER}
    return plan,details


def test_full_families_match_original_arithmetic_for_complete_fixture():
    plan,details=fixture();actual=a.independent_families(plan,details)
    rows=copy.deepcopy(plan['rows'])
    for row in rows.values():
        row.update(status='assessed',summary={'status':'assessed','business_complete':True,
            'all_required_inputs_verified':True,'selected_actions_executed':True,
            'completion':{j:10. for j in a.JOBS}})
    assert actual==a.c.comparisons(rows)['cases']
    assert all(r['member_count']==r['assessed_members']==16 for case in actual.values() for r in case['references'].values())


@pytest.mark.parametrize('change',['unknown','replay_error','missing_replay','raw_missing','physical_incomplete',
    'physical_failed','inputs_unknown','action_missing','time_bool','time_nan','job_missing'])
def test_one_bad_shared_member_blocks_family_and_full_optimum(change):
    plan,details=fixture();r=details['mechanism/vector_00']
    if change=='unknown':r['new_status']='unknown_missing_input_or_unexecuted_counterfactual'
    elif change=='replay_error':r['independent_error']='actual replay failed'
    elif change=='missing_replay':r['independent_replay']=None
    elif change=='raw_missing':r['missing_raw']=True
    elif change=='physical_incomplete':r['physical']['full_H40']=False
    elif change=='physical_failed':r['physical']['audit']['status']='failed'
    elif change=='inputs_unknown':r['all_required_inputs_verified']=False
    elif change=='action_missing':r['selected_actions_executed']=False
    elif change=='time_bool':r['physical']['completion']['loaded']=True
    elif change=='time_nan':r['physical']['completion']['loaded']=float('nan')
    else:del r['physical']['completion']['loaded']
    actual=a.independent_families(plan,details)['mechanism']
    assert actual['assessed']==31 and actual['unknown']==1 and actual['full32_finite_optimum'] is None
    assert all(r['best_key'] is None and r['status']=='unknown_incomplete_reference' for r in actual['references'].values())
    assert actual['rows_vs_incumbent']['mechanism/vector_00']['strict_protected'] is None


def test_positive_ulp_regression_is_not_tolerated():
    plan,details=fixture();r=details['mechanism/vector_25']
    r['physical']['completion']['blocker']=10.000000000000002
    comparison=a.independent_families(plan,details)['mechanism']['rows_vs_incumbent']['mechanism/vector_25']
    assert comparison['strict_protected'] is False and comparison['delta']['blocker']>0


@pytest.mark.parametrize('change',['missing','reordered','extra'])
def test_full_denominator_order_cannot_be_inferred_from_count(change):
    plan,details=fixture()
    if change=='missing':details.pop(a.c.ORDER[-1])
    elif change=='reordered':details=dict(reversed(list(details.items())))
    else:details['extra']=copy.deepcopy(details[a.c.ORDER[0]])
    with pytest.raises(ValueError):a.independent_families(plan,details)
