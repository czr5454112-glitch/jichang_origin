from copy import deepcopy
import pytest
from scripts.experiments.g31_ics_circulation.public_owned_action_state import current_actions, bind_supplied_bundle


def view():
    return {'owner_id':'A','now':3.,'client_requests':[{'request_id':'t','last_delivered_ack':{
        'status':'received','sequence':2,'delivered_at':2.}}],
        'client_commands':[{'request_id':'r','kind':'route','last_delivered_ack':{
            'status':'updated','sequence':1,'delivered_at':1.}},
            {'request_id':'p','kind':'planning_snapshot_v3','last_delivered_ack':None}]}


def test_current_snapshot_retains_terminal_physical_operations_without_claiming_provenance():
    v=view();before=deepcopy(v);facts=current_actions(v)
    assert [r['request_id'] for r in facts['actions']]==['r','t']
    assert facts['pending_request_ids']==[] and not facts['native_delivery_verified'] and v==before
    b=bind_supplied_bundle({'now':3.},v)
    assert b['owner_pending_tray_requests']==[] and b['owner_current_action_facts']==facts


@pytest.mark.parametrize('status',[None,'departed','dispatching'])
def test_departure_or_missing_ack_is_still_an_unresolved_current_transfer(status):
    v=view()
    if status is None:v['client_requests'][0]['last_delivered_ack']=None
    else:v['client_requests'][0]['last_delivered_ack']['status']=status
    assert current_actions(v)['pending_request_ids']==['t']


@pytest.mark.parametrize('defect',['future','bool','duplicate','missing_endpoint'])
def test_malformed_or_future_owner_endpoint_does_not_establish_absence(defect):
    v=view()
    if defect=='future':v['client_commands'][0]['last_delivered_ack']['delivered_at']=4.
    elif defect=='bool':v['client_commands'][0]['last_delivered_ack']['sequence']=True
    elif defect=='duplicate':v['client_commands'][0]['request_id']='t'
    else:v.pop('client_requests')
    with pytest.raises((ValueError,KeyError)):current_actions(v)
