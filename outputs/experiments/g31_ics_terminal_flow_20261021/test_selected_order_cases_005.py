import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('cases005', Path(__file__).with_name('selected_order_cases_005.py'))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def example():
    return dict(decision_id='d1', owner_id='owner', decision_time=60.,
        requested_action=dict(action_type='transfer', source=1, destination=2, tray_id='t1'),
        empty_transport_order=dict(target_by=50., estimated_arrival=90.),
        selection=dict(flow_plan=dict(station_table=[dict(node=1), dict(node=2), dict(node=3)]))), dict(
        decision_id='d1', source=1, destination=2, tray_id='t1', received=False, failed=True,
        right_censored=False, nominal_arrival=90., actual_submission=None)

def test_failed_selection_remains_with_soft_times_and_no_fabricated_receipt():
    decision, life = example(); result = m.extract(decision, life)
    assert result['lifecycle'] == life and result['lifecycle']['failed']
    assert result['planned_order']['target_by'] == 50.
    assert result['actual_submission'] is None
    assert result['source_and_destination_stations'] == [dict(node=1), dict(node=2)]

@pytest.mark.parametrize('key,value', [('decision_id','later'),('source',3),('destination',3),('tray_id','other')])
def test_cannot_join_later_or_other_physical_order(key, value):
    decision, life = example(); life[key] = value
    with pytest.raises(ValueError, match='identity'): m.extract(decision, life)

def test_changed_bound_input_is_rejected(tmp_path):
    path=tmp_path/'input.json'; path.write_text('{}'); ref=m.bind(path); path.write_text('{"changed":true}')
    with pytest.raises(ValueError, match='changed_bound_bytes'): m.read(ref)

def test_pre_submission_decision_null_does_not_erase_audited_submission():
    decision, life = example()
    decision['actual_submission'] = None
    life['actual_submission'] = dict(request_id='actual-request', issued_at=60.)
    result=m.extract(decision,life)
    assert result['actual_submission']==life['actual_submission']
    assert result['decision_record_submission'] is None
