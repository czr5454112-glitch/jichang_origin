import copy
import json

from scripts.experiments.g31_no_wait.full_parity import compare_bag,stream_compare


def fixture():
    old=dict(segment_id="a",admission=4.,finish=10.,route=[[0,4.,6.],[1,10.,12.]],
             score_expansions=3,local_scoring_calendar_queries=3,route_decisions=[[0,1,1,3,False]])
    new=copy.deepcopy(old);new.update(score_expansions=0,local_scoring_calendar_queries=0,
                                     route_decisions=[[0,1,0,0,False]],admission_effective_route_excess_seconds=120)
    return old,new


def test_only_registered_query_diagnostics_can_change():
    old,new=fixture();assert not compare_bag(old,new)
    new["finish"]=9.;assert "field_changed:finish" in compare_bag(old,new)


def test_logical_budget_flag_and_missing_old_fields_must_match():
    old,new=fixture();new["route_decisions"][0][4]=True
    assert compare_bag(old,new)==["logical_route_decision_changed:0"]
    old,new=fixture();del new["admission"]
    assert "missing_field:admission" in compare_bag(old,new)


def test_extra_unregistered_output_field_is_not_silently_ignored():
    old,new=fixture();new["invented"]=False
    assert compare_bag(old,new)==["unregistered_new_fields:invented"]


def test_stream_detects_dropped_rows_and_ledger_changes(tmp_path):
    old,new=fixture();a=tmp_path/"old.jsonl";b=tmp_path/"new.jsonl"
    a.write_text(json.dumps(old)+'\n'+json.dumps(old)+'\n');b.write_text(json.dumps(new)+'\n')
    result=stream_compare(a,b,bags=True)
    assert not result["passed"] and result["changed_records"]==1
    a.write_text(json.dumps(dict(generation=1))+'\n');b.write_text(json.dumps(dict(generation=2))+'\n')
    assert not stream_compare(a,b,bags=False)["passed"]
