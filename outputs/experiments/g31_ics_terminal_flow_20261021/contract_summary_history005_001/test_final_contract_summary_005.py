import importlib.util
from pathlib import Path
import pytest

loader=importlib.util.spec_from_file_location('contract_summary',Path(__file__).with_name('final_contract_summary_005.py'))
s=importlib.util.module_from_spec(loader);loader.loader.exec_module(s)

def example():
    plans=[dict(plan_id='multi',item_count=2,information_asof=100.),dict(plan_id='unsubmitted',item_count=2,information_asof=100.),
        dict(plan_id='single',item_count=1,information_asof=100.)]
    chains=[];life=[]
    for rid,at,received in [('first',100.,False),('later',160.,True)]:
        chains.append(dict(plan_id='multi',request_id=rid,decision_id=rid,source=1,destination=2,
            physical_tray_id=rid,actual_submission=dict(issued_at=at)))
        life.append(dict(request_id=rid,nominal_arrival=at+10.,first_edge_event=None,
            received=received,failed=not received,right_censored=False,
            eta_error_seconds=0. if received else None,final_native=dict(received_at=at+10.) if received else None))
    return dict(plan_order_chain=dict(plans=plans,order_chains=chains),selected_transfer_lifecycle=life)

def test_later_success_cannot_replace_failed_first_item():
    r=example();r['plan_order_chain']['order_chains'].reverse()
    rows=s.first_batches(r)
    assert len(rows)==2
    first=rows[0]['first_actual_submission']
    assert first['request_id']=='first' and first['failed'] and first['actual_arrival'] is None
    assert rows[0]['actual_submissions']==2 and rows[1]['first_actual_submission'] is None

def test_censored_first_item_remains_in_denominator():
    r=example();r['selected_transfer_lifecycle'][0].update(failed=False,right_censored=True,
        unreceived_eta_lateness_lower_bound_seconds=99.)
    row=s.first_batches(r)[0]['first_actual_submission']
    assert row['right_censored'] and row['unreceived_eta_lateness_lower_bound_seconds']==99.

def test_missing_first_lifecycle_is_error():
    r=example();r['selected_transfer_lifecycle'].pop(0)
    with pytest.raises(ValueError,match='without_lifecycle'):s.first_batches(r)

def test_duplicate_requests_are_not_counted_as_independent_first_batches():
    r=example();r['selected_transfer_lifecycle'].append(r['selected_transfer_lifecycle'][0])
    with pytest.raises(ValueError,match='duplicate_lifecycle'):s.first_batches(r)

def test_later_replan_success_is_not_attached_to_earlier_plan():
    r=example();r['plan_order_chain']['order_chains'][1]['plan_id']='different_plan'
    row=s.first_batches(r)[0]
    assert row['actual_submissions']==1 and row['first_actual_submission']['failed']
