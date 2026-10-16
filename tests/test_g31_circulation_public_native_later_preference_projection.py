"""Later source-fact and action-semantics tests, with no native session."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import public_native_later_preference_projection as model
from test_g31_circulation_public_preexisting_v3_model import fixture


def data(phase='first_return'):
    c,j,t,r,args=fixture(phase=phase)
    result=model.captured.assemble_later(c,j,t,r,**args)
    result['owner_pending_tray_requests']=[]
    result['owner_current_action_facts']={'owner':'A' if phase=='first_return' else 'B',
        'observed_at':result['now'],'actions':[],'pending_request_ids':[]}
    return result


@pytest.mark.parametrize('defect',['missing_pending','pending','missing_current','future_current',
                                  'new_post_capture_action','future_ack','equal_union_ack'])
def test_current_owned_actions_cannot_be_replaced_with_an_assumed_empty_list(defect):
    b=data()
    if defect=='missing_pending':b.pop('owner_pending_tray_requests')
    elif defect=='pending':b['owner_pending_tray_requests']=['new']
    elif defect=='missing_current':b.pop('owner_current_action_facts')
    elif defect=='future_current':b['owner_current_action_facts']['observed_at']+=1.
    else:
        row={'request_id':'new','kind':'route','last_delivered_ack':{'status':'updated','sequence':1,
            'delivered_at':b['now']+1. if defect=='future_ack' else min(r['captured_at'] for r in b['source_records'])}}
        b['owner_current_action_facts']['actions']=[row]
        if defect!='new_post_capture_action':
            source=next(r for r in b['source_records'] if r['owner']=='A')
            source['submitted_physical_request_ids']=['new']
            source['submitted_physical_actions']=[dict(row,source_owner='A')]
    assert model.predict(b,{'return_delay':0.,'later_action':'native_default'})['status'].startswith('unknown')


@pytest.mark.parametrize('phase',['first_return','first_reuse_route'])
def test_complete_prefix_and_inflight_reservation_are_seeded_from_guarded_facts(phase):
    b=data(phase); checked=model.revalidate(b)
    assert checked['status']=='conditional_model_input',checked
    p=model.LaterProjection(checked,{'return_delay':0.,'later_action':'native_default'});p.seed()
    assert p.completed==b['completed_prefix']
    assert p.trays['E']['scheduled_incoming_node']==3
    end=b['entry_receipts']['E']['derived_edge_exit_at']
    assert p.calendars[3]==[(end,end+p.service[3])]
    assert p.occupancy(3)==1
    assert all((event[0]-model.legacy.START)/model.legacy.PERIOD>=0 for event in p.events if event[-2]=='tick')


@pytest.mark.parametrize('defect',['missing_entry','exit_now','old_capture','unresolved_action','changed_contract',
                                  'completed_absence','changed_resource','wrong_population'])
def test_revalidation_preserves_old_capture_action_and_population_guards(defect):
    b=data()
    if defect=='missing_entry':b['entry_receipts']={}
    elif defect=='exit_now':b['entry_receipts']['E']['derived_edge_exit_at']=b['now']
    elif defect=='old_capture':b['source_records'][0]['captured_at']=0.
    elif defect=='unresolved_action':b['source_records'][0]['unresolved_tray_request_ids']=['unresolved']
    elif defect=='changed_contract':b['contract']['protocol']['message_delay']=1.
    elif defect=='completed_absence':b['terminal_receipts']=[]
    elif defect=='changed_resource':b['resources'][3]['occupancy']=0
    else:b['jobs'].pop('reuse2')
    result=model.predict(b,{'return_delay':0.,'later_action':'native_default'})
    assert result['status'].startswith('unknown') and result['native_protection_certified'] is False


def test_later_no_command_does_not_claim_fixed_route_and_first_return_cannot_change():
    b=data('first_reuse_route')
    zero=model.predict(b,{'return_delay':0.,'later_action':'native_default'})
    delayed=model.predict(b,{'return_delay':.5,'later_action':'native_default'})
    assert zero['status']==delayed['status']=='conditional_prediction'
    assert zero['completion']==delayed['completion']
    assert all(c['job']!='reuse1' for c in zero['projected_commands'])
    assert not zero['native_protection_certified'] and not zero['online_information_delivered']


def test_supplied_input_is_immutable_and_no_prefix_job_is_omitted():
    b=data();before=copy.deepcopy(b)
    result=model.predict(b,{'return_delay':0.,'later_action':'prefer_8'})
    assert result['status']=='conditional_prediction'
    assert set(result['completion'])==model.contract.JOBS and b==before


def test_boolean_action_delay_is_not_a_valid_numeric_contract():
    assert model.predict(data(),{'return_delay':False,'later_action':'native_default'})['status']=='unknown_unsupported_action'


@pytest.mark.parametrize('defect',['omit_prefix','change_prefix','future_publication','future_ack',
                                  'stale_service','wrong_entry','changed_owner'])
def test_additional_prefix_causal_time_and_source_scope_guards(defect):
    b=data()
    if defect=='omit_prefix':b.pop('completed_prefix')
    elif defect=='change_prefix':b['completed_prefix']['loaded']+=1.
    elif defect=='future_publication':b['source_records'][0]['delivered_at']=b['now']+1.
    elif defect=='future_ack':
        source=b['source_records'][0]
        source['submitted_physical_request_ids']=['r']
        source['submitted_physical_actions']=[{'request_id':'r','kind':'route_intent','source_owner':source['owner'],
            'last_delivered_ack':{'status':'updated','sequence':1,'delivered_at':b['now']+1.}}]
    elif defect=='stale_service':b['trays']['L']['service_ready_at']=b['now']+1.
    elif defect=='wrong_entry':b['entry_receipts']['E']['edge_to']=8
    else:b['source_records'][0]['owner']='B'
    assert model.predict(b,{'return_delay':0.,'later_action':'native_default'})['status'].startswith('unknown')
