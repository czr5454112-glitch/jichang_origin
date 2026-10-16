"""Small abstract behavioral tests, no native or predictor execution."""
from dataclasses import replace
import pytest
from scripts.experiments.g31_ics_circulation.completion_baton_relay_design import (
    ReferenceBaton, Completion, Empty, Head, zero_bad_load_prefix_bound)


def opened():
    model=ReferenceBaton(tuple(f'T{i}' for i in range(22)),('A','B'))
    receipt=Completion('c:A:1','done','T0','A',10,10.)
    current=Empty('T0','A',10,2,3,11.,12.)
    model.open_completion(receipt,current,physical_barrier=True)
    return model,receipt,current


def supply(model, donor=None, head=None, request_id='q1'):
    donor=donor or Empty('T1','A',11,1,2,0.,12.)
    head=head or Head('next','B',20,5.,11.,True)
    model.supply(request_id,donor,head,head,positive_supply_path=True,
                 source_export_ok=True,receiver_capture_ok=True)


def test_same_head_can_use_existing_different_local_empty():
    model,_,_=opened();supply(model)
    assert model.pending==('q1','supply','T1','next')
    assert model.supplies==1 and model.bridges==0 and len(model.inventory)==22


@pytest.mark.parametrize('change',[{'owner':'B'},{'tray_id':'new23'},
    {'job_id':'loaded'},{'mode':'loaded'},{'edge_to':3},
    {'reception_node':4},{'available_at':13.},{'generation':True}])
def test_illegal_donor_is_never_a_supply(change):
    model,_,_=opened();donor=Empty('T1','A',11,1,2,0.,12.)
    with pytest.raises(ValueError):supply(model,replace(donor,**change))
    assert model.pending is None


def test_cannot_skip_unreachable_current_head():
    model,_,_=opened()
    with pytest.raises(ValueError):supply(model,head=Head('blocked','B',20,5.,11.,False))


def test_different_later_head_is_not_same_selected_head():
    model,_,_=opened();head=Head('head','B',20,5.,11.,True)
    with pytest.raises(ValueError,match='same_original_selected_head'):
        model.supply('q1',Empty('T1','A',11,1,2,0.,12.),head,replace(head,job_id='later'),
            positive_supply_path=True,source_export_ok=True,receiver_capture_ok=True)


def test_pending_request_prevents_second_physical_action():
    model,_,current=opened();supply(model)
    with pytest.raises(ValueError):supply(model)
    with pytest.raises(ValueError):model.bridge('q2',current,target_owner='B',target_role='ordinary',
        positive_paths=True,source_export_ok=True,receiver_capture_ok=True)


def test_received_ACK_is_not_completed_business():
    model,_,_=opened();supply(model)
    model.delivered_received('q1',ack_status='received',delivered_at=13.,now=13.)
    assert model.phase=='await_job_completion'
    with pytest.raises(ValueError):supply(model)


@pytest.mark.parametrize('status',['pending','expired','failed','rejected'])
def test_missing_successful_ACK_does_not_release_grant(status):
    model,_,_=opened();supply(model)
    model.delivered_received('q1',ack_status=status,delivered_at=13.,now=13.)
    assert model.phase=='await_received_ACK'
    assert bool(model.invalid)==(status!='pending')
    with pytest.raises(ValueError):supply(model)


def test_next_real_completion_transfers_baton_not_old_receipt():
    model,old,_=opened();supply(model)
    model.delivered_received('q1',ack_status='received',delivered_at=13.,now=13.)
    new=Completion('c:B:1','next','T1','B',30,15.)
    model.job_finished(new,Empty('T1','B',30,3,4,16.,17.),physical_barrier=True)
    assert model.phase=='owner_choice' and model.grant==new
    assert model.consumed_jobs=={'done','next'}
    with pytest.raises(ValueError):model.open_completion(old,Empty('T0','A',10,2,3,11.,17.),physical_barrier=True)


def test_bridge_cannot_substitute_carrier_or_chain():
    model,receipt,current=opened()
    with pytest.raises(ValueError):model.bridge('q1',replace(current,tray_id='T1'),
        target_owner='B',target_role='ordinary',positive_paths=True,source_export_ok=True,receiver_capture_ok=True)
    model.bridge('q1',current,target_owner='B',target_role='ordinary',positive_paths=True,
                 source_export_ok=True,receiver_capture_ok=True)
    model.delivered_received('q1',ack_status='received',delivered_at=15.,now=15.)
    arrived=Empty('T0','B',25,3,4,14.,16.)
    model.bridge_arrival(arrived,complete_barrier=True,delivered_completion=receipt)
    with pytest.raises(ValueError):model.bridge('q2',arrived,target_owner='A',target_role='ordinary',
        positive_paths=True,source_export_ok=True,receiver_capture_ok=True)
    with pytest.raises(ValueError):supply(model,replace(arrived,tray_id='T2'),Head('x','A',40,4.,15.,True))
    supply(model,arrived,Head('x','A',40,4.,15.,True),'q2')
    assert model.supplies==1 and model.bridges==1


def test_loader_arrival_or_wrong_completion_cannot_mint_bridge_permit():
    model,receipt,current=opened()
    model.bridge('q1',current,target_owner='B',target_role='ordinary',positive_paths=True,
                 source_export_ok=True,receiver_capture_ok=True)
    model.delivered_received('q1',ack_status='received',delivered_at=15.,now=15.)
    arrived=Empty('T0','B',25,3,4,14.,16.,role='loader')
    with pytest.raises(ValueError):model.bridge_arrival(arrived,complete_barrier=True,delivered_completion=receipt)
    with pytest.raises(ValueError):model.bridge_arrival(replace(arrived,role='ordinary'),
        complete_barrier=True,delivered_completion=replace(receipt,tray_id='T1'))


def test_conditional_FIFO_bound_does_not_depend_on_number_of_active_trays():
    rows={0:[(1.,True),(2.,False),(3.,True)],1:[(1.,True),(2.,True),(3.,False)]}
    assert zero_bad_load_prefix_bound(rows)==3
    assert zero_bad_load_prefix_bound({0:[(1.,True),(2.,True),(3.,True)]})==3


@pytest.mark.parametrize('rows',[{0:[(1.,True),(1.,False)]},{0:[(2.,True),(1.,True)]},
    {0:[(True,True)]},{0:[(1.,1)]}])
def test_FIFO_proof_rejects_unproved_order_or_types(rows):
    with pytest.raises(ValueError):zero_bad_load_prefix_bound(rows)
