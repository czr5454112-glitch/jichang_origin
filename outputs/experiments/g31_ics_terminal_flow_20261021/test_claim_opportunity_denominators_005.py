import importlib.util
from pathlib import Path

p=Path(__file__).with_name('claim_opportunity_denominators_005.py')
s=importlib.util.spec_from_file_location('claim_denominators_test',p)
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

def decision(actions,known=True,slots=1):
    return dict(catalog=dict(candidates=actions),selection=dict(flow_plan=dict(station_table=[
        dict(node=3,receiver=dict(known=known,available_slots=slots))])))
def action(source,kind='loader_optional'):
    return dict(action_type='transfer',source=source,destination=3,source_category=kind)
def test_two_trays_same_od_are_not_two_od_competitors():
    r=m.classify(decision([action(1),action(1)]))
    assert r['transfer_candidates']==2 and r['known_available_receiver_OD']==1
def test_unknown_receiver_is_not_known_zero_or_rankable():
    r=m.classify(decision([action(1),action(2)],known=False))
    assert r['transfer_candidates']==2 and r['known_available_receiver_OD']==0
def test_logically_reserved_capacity_is_not_recreated():
    assert m.classify(decision([action(1),action(2)],slots=0))['known_available_receiver_OD']==0
def test_ordinary_priority_filters_optional_rankings():
    r=m.classify(decision([action(1,'ordinary_return'),action(2)]))
    assert r['protected_category_applied'] and r['known_available_receiver_OD']==1
def test_empty_menu_is_separate_from_unknown_capacity():
    assert m.classify(decision([]))['transfer_candidates']==0
