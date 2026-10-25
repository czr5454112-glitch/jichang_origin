"""Missing/censored result rows cannot turn into completed-subset comparisons."""
import copy
import json
import hashlib

from scripts.experiments.g31_no_wait import compare_current as compare


def fixture():
    rows=[dict(segment_id="a",task_id=1,leg="direct",start=0,goal=1,pass_time=0,original_entry_time=0,std=100),
          dict(segment_id="b",task_id=2,leg="direct",start=0,goal=1,pass_time=1,original_entry_time=1,std=100)]
    bags=[dict(segment_id="a",task_id=1,leg="direct",start=0,goal=1,admission=2,finish=5,
               first_planning_attempt_time=0,completed=True,retries=2),
          dict(segment_id="b",task_id=2,leg="direct",start=0,goal=1,admission=4,finish=8,
               first_planning_attempt_time=3,completed=True,retries=1)]
    return rows,bags


def test_complete_population_has_exact_companion_components():
    rows,bags=fixture()
    result,tht,source=compare.summarize_population(rows,bags,100,run_finished=True)
    assert tht["passed"] and source["passed"] and result["full_population_available"]
    assert result["metrics"]["user_tht"]["mean"]==5
    assert result["metrics"]["planning_retry_wait"]["mean"]==1.5
    assert result["metrics"]["canonical_to_first_attempt"]["mean"]==1
    assert result["metrics"]["canonical_elapsed"]["mean"]==6
    assert result["metrics"]["retry_count"]["sum"]==3


def test_incomplete_population_has_no_completed_subset_statistics():
    rows,bags=fixture();bags[1]["completed"]=False
    result,_,_=compare.summarize_population(rows,bags,90,run_finished=True)
    assert result["completed_businesses"]==1 and not result["full_population_available"]
    for metric in result["metrics"].values():
        assert metric["count"]==2 and all(metric[k] is None for k in compare.STATS)
    assert result["deadlines"]["std_rate"] is None
    assert result["system"]["business_completions_in_window"]==1
    assert result["system"]["original_population_backlog_businesses"]==1
    assert result["system"]["hourly_cumulative_business_completion"][-1]["cumulative_completed_businesses"]==1


def test_elapsed_deadlines_make_full_denominator_std_final_even_if_unfinished():
    rows,bags=fixture();bags[1]["completed"]=False
    result,_,_=compare.summarize_population(rows,bags,100,run_finished=True)
    assert result["metrics"]["user_tht"]["mean"] is None
    assert result["deadlines"]["std_count"]==1 and result["deadlines"]["std_rate"]==.5
    assert result["deadlines"]["deadline_status_final"] is True


def test_drain_completions_do_not_increase_original_window_throughput():
    rows,bags=fixture()
    result,_,_=compare.summarize_population(rows,bags,100,run_finished=True,window_end=6)
    assert result["full_population_available"] and result["completed_businesses"]==2
    assert result["metrics"]["user_tht"]["mean"]==5
    system=result["system"]
    assert system["window_fully_observed"] and system["window_end"]==6 and system["observed_horizon"]==100
    assert system["business_completions_in_window"]==1
    assert system["original_population_backlog_businesses"]==1
    assert system["business_throughput_per_simulated_hour"]==600
    assert system["observed_total_completed_businesses"]==2 and system["observed_after_window_completions"]==1
    assert system["hourly_cumulative_business_completion"][-1]["time"]==6
    assert system["hourly_cumulative_business_completion"][-1]["cumulative_completed_businesses"]==1


def test_unobserved_window_end_keeps_final_throughput_null():
    rows,bags=fixture()
    result,_,_=compare.summarize_population(rows,bags,6,run_finished=True,window_end=10)
    system=result["system"]
    assert not system["window_fully_observed"]
    assert system["business_completions_in_window"] is None
    assert system["business_throughput_per_simulated_hour"] is None
    assert system["original_population_backlog_businesses"] is None
    assert system["observed_window_completions_lower_bound"]==1
    assert system["hourly_cumulative_business_completion"][-1]["time"]==6


def test_original_and_drain_runs_can_compare_same_fully_observed_window():
    rows,bags=fixture()
    original_bags=copy.deepcopy(bags);original_bags[1]["completed"]=False
    original,_,_=compare.summarize_population(rows,original_bags,6,run_finished=True,window_end=6)
    drained,_,_=compare.summarize_population(rows,bags,100,run_finished=True,window_end=6)
    def run(population, horizon, name):
        return dict(population,id=name,cell="map2_1x",canonical_content_sha256="same",horizon=horizon,
                    comparable=population["full_population_available"],audit_status={"test":True})
    pair=compare.pair_summary(run(drained,100,"drain"),run(original,6,"original"))
    assert not pair["comparable"] and "different_or_missing_horizon" in pair["reasons"]
    assert pair["system_window"]==dict(comparable=True,completions_difference=0,backlog_difference=0)


def test_missing_anchor_does_not_fallback_to_admission():
    rows,bags=fixture();del bags[0]["first_planning_attempt_time"]
    result,_,_=compare.summarize_population(rows,bags,100,run_finished=True)
    assert result["missing_first_planning_attempt_segments"]==1
    assert result["metrics"]["user_tht"]["mean"] is None


def test_no_hca_retry_counts_inferred_from_timing():
    rows,bags=fixture()
    for b in bags: del b["retries"]
    result,_,_=compare.summarize_population(rows,bags,100,run_finished=True)
    assert result["metrics"]["retry_count"]["sum"] is None
    assert result["metrics"]["planning_retry_wait"]["mean"]==1.5


def test_running_state_does_not_read_partial_native_files(tmp_path):
    path=tmp_path/"g31_map2_1x_rolling_fixed1_w0_005";path.mkdir()
    (path/"manifest.json").write_text(json.dumps(dict(status="running",config={})))
    (path/"bags.jsonl").write_text("partial invalid file")
    contract=dict(cells={"map2_1x":dict(business_denominator=2,segment_denominator=2)})
    result=compare.summarize_run("g31",path,contract,tmp_path,{})
    assert result["status"]=="running" and result["metrics"]["user_tht"]["mean"] is None


def test_pair_refuses_missing_population_or_different_identity():
    rows,bags=fixture();pop,_,_=compare.summarize_population(rows,bags,100,run_finished=True)
    a=dict(pop,id="a",cell="map2_1x",canonical_content_sha256="hash",horizon=100,comparable=True,audit_status={"test":True})
    b=copy.deepcopy(a);b.update(id="b",canonical_content_sha256="different")
    pair=compare.pair_summary(a,b)
    assert not pair["comparable"] and pair["metrics"]["user_tht"]["mean"]["ratio"] is None
    b["canonical_content_sha256"]="hash";b["comparable"]=False
    assert not compare.pair_summary(a,b)["comparable"]


def test_frozen_retry_name_includes_parser_alias_normalization():
    result=compare.effective_retry_policy(dict(retry_mode="calendar_jump"))
    assert result["effective"]=="futurecalendar_jump" and result["parser_alias_applied"]
    assert compare.effective_retry_policy(dict(retry_mode="futurecalendar_jump"))["effective"]=="futurecalendar_jump"
    assert compare.effective_retry_policy(dict(retry_mode="1s"))["effective"]=="1s"


def test_default_discovery_does_not_mix_prior_versions(tmp_path):
    for suffix in ("004","005"):
        (tmp_path/f"g31_map2_1x_rolling_fixed1_w0_{suffix}").mkdir()
    assert [p.name for p in compare.discover(tmp_path,[]) ]==["g31_map2_1x_rolling_fixed1_w0_005"]


def test_double_wait_roundoff_is_not_a_substitute_for_exact_grid_audit():
    movement=dict(safety=dict(route_violations=0,routes_with_repeated_nodes=0,
                             internal_internal_interval_overlaps=0,internal_extra_wait_sum_seconds=5e-7),
                  business=dict(counts=dict(causally_invalid_admitted=0)))
    assert compare.movement_audit_status(movement)
    movement["safety"]["route_violations"]=1
    assert not compare.movement_audit_status(movement)


def test_standard_adapter_manifest_supported_without_rerunning_native(tmp_path,monkeypatch):
    rows,bags=fixture()
    directory=tmp_path/"friendly_standard_run";directory.mkdir()
    source=directory/"standard_sources";source.mkdir()
    (source/"core.cpp").write_text("frozen test engine")
    source_hash=compare.sha(source/"core.cpp");monkeypatch.setattr(compare,"CORE005",source_hash)
    canonical=tmp_path/"canonical.jsonl"
    canonical.write_text("".join(json.dumps(r)+"\n" for r in rows))
    (directory/"bags.jsonl").write_text("".join(json.dumps(b)+"\n" for b in bags))
    cfg=dict(source_fifo_order="canonical",interval_mode="half_open",strict_endpoint_resources=True,
             enable_ebs_predecessor_gate=True,enable_inroute_replanning=True,edge_entry_headway_seconds=2,
             source_fifo=True,source_generation_interval=1,release_quantum=1,completion_quantum=1)
    manifest=dict(schema="g31.continuous.run.v1",status="complete",source_sha256={"core.cpp":source_hash},
                  bags_sha256=compare.sha(directory/"bags.jsonl"),selection=dict(map="map2",scale=1,
                  effective_controls=cfg,profile=dict(sha256="normalized"),canonical=dict(sha256=compare.sha(canonical))))
    def dump(name,value): (directory/name).write_text(json.dumps(value))
    dump("manifest.json",manifest);dump("native_summary.json",dict(executed_horizon=100,event_budget_exhausted=False))
    for name in ("headway_audit","rolling_replay","source_policy_audit","tht_audit","business_audit"):
        dump(name+".json",dict(passed=True))
    contract=dict(cells={"map2_1x":dict(business_denominator=2,segment_denominator=2,
                     canonical=dict(path=str(canonical),sha256=compare.sha(canonical),encoding="jsonl"))},
                  maps={"map2":dict(profile=dict(sha256="normalized"))})
    output=tmp_path/"report";output.mkdir()
    result=compare.summarize_run("g31",directory,contract,output,{},window_start=0)
    assert result["status"]=="complete" and result["comparable"]
    assert result["metrics"]["user_tht"]["mean"]==5
