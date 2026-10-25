import copy
import json

import pytest

from scripts.experiments.g31_no_wait import drain_prefix as prefix


def bag():
    return dict(segment_id="a", task_id=1, leg="direct", start=0, goal=2,
                activation_time=0, first_planning_attempt_time=1, admission=3,
                completed=False, actual_finish=None, finish=15, route=[[0,3,5],[2,15,17]], retries=5)


def write_lines(path, rows):
    path.write_text("".join(json.dumps(row)+"\n" for row in rows), encoding="utf-8")


def test_drain_final_route_and_retry_totals_do_not_rewrite_prefix():
    old=bag();new=copy.deepcopy(old)
    new.update(completed=True, actual_finish=12, finish=12, route=[[0,3,5],[1,7,9],[2,12,14]], retries=20)
    assert prefix.compare_bag_prefix(old,new,10)==[]
    new["first_planning_attempt_time"]=2
    assert "clock_prefix_changed:first_planning_attempt_time" in prefix.compare_bag_prefix(old,new,10)


def test_future_first_attempt_is_allowed_but_backdated_attempt_is_not():
    old=bag();old.update(first_planning_attempt_time=None, admission=None)
    new=copy.deepcopy(old);new.update(first_planning_attempt_time=11, admission=12)
    assert prefix.compare_bag_prefix(old,new,10)==[]
    new["first_planning_attempt_time"]=10
    assert "clock_prefix_changed:first_planning_attempt_time" in prefix.compare_bag_prefix(old,new,10)


def test_actual_completions_at_cutoff_are_exact():
    old=bag();old.update(completed=True,actual_finish=10,finish=10)
    new=copy.deepcopy(old)
    assert prefix.compare_bag_prefix(old,new,10)==[]
    new["actual_finish"]=9
    assert "actual_completed_set_or_time_changed" in prefix.compare_bag_prefix(old,new,10)


def test_ledger_filters_only_after_cutoff_and_compares_cleanup_validity(tmp_path):
    original=tmp_path/"old.jsonl";drain=tmp_path/"drain.jsonl"
    rows=[dict(ledger_order=1,time=3,kind="source_commit",segment_id="a"),
          dict(ledger_order=2,time=10,kind="cleanup",valid=False)]
    write_lines(original,rows)
    write_lines(drain,rows+[dict(ledger_order=3,time=11,kind="arrival",segment_id="a")])
    result=prefix.stream_ledger(original,drain,10)
    assert result["passed"] and result["serialized_prefix_bytes_exact"]
    assert result["prefix_records"]==2 and result["drain"]["after_cutoff_records"]==1
    rows[1]["valid"]=True;write_lines(drain,rows)
    assert not prefix.stream_ledger(original,drain,10)["passed"]


def test_only_horizon_can_change_in_controls_and_contract():
    old=dict(end_time=10, rate=1);new=dict(end_time=20,rate=1)
    assert prefix.only_end_time_changed(old,new,10)==20
    new["rate"]=2
    with pytest.raises(ValueError,match="beyond end_time"):
        prefix.only_end_time_changed(old,new,10)


def test_predeclared_inert_drain_annotation_is_narrowly_whitelisted():
    old=dict(end_time=98259,physical="unchanged")
    new=dict(end_time=200000,physical="unchanged",observation_window_extension=dict(
        original_start=8260,original_end=98259,extended_end=200000,new_arrivals_added=False,
        deadlines_changed=False,purpose="Drain the identical finite cohort."))
    assert prefix.validate_contract_change(old,new,98259)==200000
    bad=copy.deepcopy(new);bad["observation_window_extension"]["new_arrivals_added"]=True
    with pytest.raises(ValueError,match="changes the registered cohort"):
        prefix.validate_contract_change(old,bad,98259)
    bad=copy.deepcopy(new);bad["observation_window_extension"]["hidden_control"]=1
    with pytest.raises(ValueError,match="unrecognized"):
        prefix.validate_contract_change(old,bad,98259)
    bad=copy.deepcopy(new);bad["physical"]="changed"
    with pytest.raises(ValueError,match="beyond end_time"):
        prefix.validate_contract_change(old,bad,98259)


def formal_pair(tmp_path):
    roots=[tmp_path/"original",tmp_path/"drain"]
    old_bag=bag();new_bag=copy.deepcopy(old_bag);new_bag.update(completed=True,actual_finish=15)
    for directory,end,item in zip(roots,(10,20),(old_bag,new_bag)):
        directory.mkdir();sources=directory/"standard_sources";sources.mkdir()
        (sources/"core.cpp").write_text("same frozen core")
        config=dict(end_time=end,rate=1)
        for name,value in (("contract.json",dict(config,physical="same")),("controls.json",config)):
            (sources/name).write_text(json.dumps(value))
        write_lines(directory/"bags.jsonl",[item])
        ledger=[dict(ledger_order=1,time=3,kind="source_commit",segment_id="a")]
        if end==20:ledger.append(dict(ledger_order=2,time=15,kind="arrival",segment_id="a"))
        write_lines(directory/"rolling_events.jsonl",ledger)
        source_hashes={p.name:prefix.file_sha(p) for p in sources.iterdir()}
        selection=dict(execution_model="continuous_headway_2s",map="map2",scale=2,
                       business_denominator=1,segment_denominator=1,effective_controls=config)
        for key in ("binary","canonical","profile","build_receipt","native_source"):
            selection[key]=dict(sha256="same-"+key)
        manifest=dict(schema="g31.continuous.run.v1",status="complete",audits_passed=True,
                      selection=selection,source_sha256=source_hashes,bags_sha256=prefix.file_sha(directory/"bags.jsonl"))
        (directory/"manifest.json").write_text(json.dumps(manifest))
        (directory/"native_summary.json").write_text(json.dumps(dict(tasks=1,event_budget_exhausted=False,executed_horizon=end)))
    return roots


def test_complete_streaming_formal_prefix_receipt_and_binary_mismatch(tmp_path):
    old,new=formal_pair(tmp_path)
    result=prefix.run(old,new,10)
    assert result["passed"] and result["bags"]["records"]==1
    assert result["rolling_events"]["prefix_records"]==1
    path=new/"manifest.json";manifest=prefix.read(path)
    manifest["selection"]["binary"]["sha256"]="changed"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="identity changed: binary"):
        prefix.run(old,new,10)


def test_identical_adapter_defaults_can_expand_raw_controls(tmp_path):
    old,new=formal_pair(tmp_path)
    for directory in (old,new):
        path=directory/"manifest.json";manifest=prefix.read(path)
        manifest["selection"]["effective_controls"].update(retry_step=1.,audit_failed_calendar_hash=False)
        path.write_text(json.dumps(manifest))
    assert prefix.run(old,new,10)["passed"]
    path=new/"manifest.json";manifest=prefix.read(path)
    manifest["selection"]["effective_controls"]["retry_step"]=2.
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match="beyond end_time"):
        prefix.run(old,new,10)


def test_original_executed_event_after_cutoff_fails_closed(tmp_path):
    old=tmp_path/"old.jsonl";new=tmp_path/"new.jsonl"
    rows=[dict(ledger_order=1,time=11,kind="arrival")]
    write_lines(old,rows);write_lines(new,rows)
    with pytest.raises(ValueError,match="after its horizon"):
        prefix.stream_ledger(old,new,10)
