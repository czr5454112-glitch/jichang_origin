"""Pure independent-family arithmetic. No native/predictor or raw96 scan."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import audit_live_obligation_unloading as a


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


def followup_fixture():
    """Synthetic helper unit, deliberately not a native/endpoint proof."""
    def attempt(index,status):
        return {'phase':'first_reuse_route','at':9.23+index*.04,
            'collection':{'at':9.19+index*.04,'policy_quiet_since':9.19,'recollection_index':index,
                'request_id':'own'+str(index),'peer_message':'peer'+str(index)},
            'information':{'status':status},'retry_admission':{},'actual_local_view':{'trays':[]}}
    first=attempt(0,'unknown');first['retry_admission']={'crossed_source_fact':{'completion_inferred':False}}
    final=attempt(1,'conditional_native_delivered_later_v3_model_input')
    message={'delivered_at':9.26,'capture':{'capture_v2':{
        'local_capture':{'source_owner':'A','message_id':'peer1','captured_at':9.25},
        'extension':{'terminal_receipts':[{'business_bag_id':'receiver','completed_at':9.22}]}}}}
    final['information']['raw_endpoints']={'command':{},'received':[message]}
    return {'collection_attempts':{'A':[],'B':[first,final]},'result':{'receipts':[
        {'event':'UNLOAD_COMPLETE','business_bag_id':'receiver','tray_id':'E','time':9.22}]}}


def test_fresh_outcome_requires_actual_destination_terminal_at_exact_native_time():
    facts=a.enriched_attempt_facts(followup_fixture())[0]['unloading_fresh_outcome']
    assert facts['known_final_input'] is True
    assert facts['actual_received_receiver_terminal_receipts'][0]['receipt']['completed_at']==9.22


@pytest.mark.parametrize('change',['missing','foreign','different_time','duplicate'])
def test_claimed_known_fresh_cannot_hide_missing_or_changed_terminal(change):
    raw=followup_fixture();message=raw['collection_attempts']['B'][1]['information']['raw_endpoints']['received'][0]
    body=message['capture']['capture_v2'];terminal=body['extension']['terminal_receipts']
    if change=='missing':terminal.clear()
    elif change=='foreign':body['local_capture']['source_owner']='B'
    elif change=='different_time':terminal[0]['completed_at']+=.001
    else:terminal.append(copy.deepcopy(terminal[0]))
    with pytest.raises(ValueError):a.enriched_attempt_facts(raw)


def test_unloading_fresh_with_no_terminal_stays_unknown_in_diagnostic():
    raw=followup_fixture();final=raw['collection_attempts']['B'][1]
    final['information']['status']='unknown';final['information']['bundle']={'reasons':['stable_observed_unloading']}
    final['information']['raw_endpoints']['received'][0]['capture']['capture_v2']['extension']['terminal_receipts']=[]
    facts=a.enriched_attempt_facts(raw)[0]['unloading_fresh_outcome']
    assert facts['known_final_input'] is False and facts['actual_received_receiver_terminal_receipts']==[]
    assert facts['bundle_reasons']==['stable_observed_unloading']
