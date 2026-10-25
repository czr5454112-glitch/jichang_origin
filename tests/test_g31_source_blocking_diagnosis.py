import importlib.util
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / "scripts/experiments/g31_no_wait/source_blocking_diagnosis.py"
SPEC = importlib.util.spec_from_file_location("source_blocking_diagnosis", PATH)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


def row(sid, task, leg, source, release=0., goal=9):
    return dict(segment_id=sid, task_id=task, leg=leg, start=source,
                pass_time=release, goal=goal)


def bag(sid, first, admission, finish, **extra):
    return dict(segment_id=sid, first_planning_attempt_time=first,
                admission=admission, finish=finish, completed=finish is not None,
                **extra)


def group(result, source, leg):
    return next(g for g in result["source_leg_groups"] if (g["source"],g["leg"]) == (source,leg))


def test_partition_is_additive_but_overlap_is_separate():
    r=mod.clock_partition(.2,10.,12.,15.)
    assert r["release_quantization"] == pytest.approx(.8)
    assert r["own_ebs_not_ready"] == 9
    assert r["ready_predecessor_block"] == 2
    assert r["source_generation_spacing"] == 1
    assert r["unattributed_scheduling_residual"] == 2
    assert r["overlap_own_ebs_and_unadmitted_predecessor"] == 9
    assert sum(r[k] for k in mod.PARTS) == pytest.approx(r["preplanning"])


def test_first_source_has_no_predecessor_or_spacing_cost():
    r=mod.clock_partition(.2,1.,-float("inf"),1.)
    assert r["ready_predecessor_block"] == 0
    assert r["source_generation_spacing"] == 0
    assert r["overlap_own_ebs_and_unadmitted_predecessor"] == 0


def test_ebs_ready_uses_report_and_still_blocked_by_source_predecessor():
    rows=[row("head",0,"direct",5),row("in",1,"storage_in",2),row("out",1,"storage_out",5,.2)]
    bags=[bag("head",0,12,14),bag("in",0,0,8.1,observed_finish=10),bag("out",15,16,18)]
    r=mod.analyze(rows,bags,cutoff=11,horizon=30)
    g=group(r,5,"storage_out")
    assert g["cutoff_states"] == {"ready_but_canonical_predecessor_unadmitted":1}
    assert g["full_run_clocks"]["own_ebs_not_ready"]["sum"] == 9
    assert g["full_run_clocks"]["ready_predecessor_block"]["sum"] == 2
    assert g["full_run_clocks"]["unattributed_scheduling_residual"]["sum"] == 2
    assert r["source_heads_at_cutoff"][0]["head_segment_id"] == "head"
    assert r["source_heads_at_cutoff"][0]["own_ready_waiting_segments"] == 2


def test_original_window_separates_own_unready_from_ready_fifo_and_pending():
    rows=[row("head",0,"direct",5),row("in",1,"storage_in",2),
          row("out",1,"storage_out",5,1),row("later",2,"direct",5,2)]
    bags=[bag("head",0,20,22),bag("in",0,0,15),bag("out",21,21,24),bag("later",22,22,25)]
    r=mod.analyze(rows,bags,cutoff=10,horizon=30)
    assert r["cutoff_states"] == {"attempted_not_admitted":1,"admitted_in_transit":1,
                                   "own_ebs_not_ready":1,"ready_but_canonical_predecessor_unadmitted":1}
    s=next(s for s in r["source_heads_at_cutoff"] if s["source"]==5)
    assert s["waiting_segments"] == 3
    assert s["own_ready_waiting_segments"] == 2
    assert s["own_ebs_unready_waiting_segments"] == 1
    assert group(r,5,"storage_out")["cutoff_restricted_clocks"]["preplanning"]["sum"]==9


def test_future_first_attempt_and_admission_do_not_leak_into_cutoff():
    rows=[row("x",0,"direct",0)]
    bags=[bag("x",20,25,28,attempts=5,search_expansions=900)]
    r=mod.analyze(rows,bags,cutoff=10,horizon=30)
    s=r["source_heads_at_cutoff"][0]
    assert s["first_attempt"] is None
    assert s["observed_head_retry_seconds"] is None
    assert "search_expansions" not in s
    assert r["cutoff_states"] == {"ready_unattempted_unattributed":1}
    assert r["longest_full_run_head_retries"][0]["search_expansions"] == 900


def test_unreleased_tasks_have_zero_restricted_hold_and_remain_in_denominator():
    rows=[row("x",0,"direct",0,20.2)]
    r=mod.analyze(rows,[bag("x",None,None,None)],cutoff=10,horizon=30)
    assert r["segment_denominator"] == 1
    assert r["cutoff_states"] == {"not_nominally_released":1}
    g=group(r,0,"direct")
    assert g["cutoff_restricted_clocks"]["preplanning"]["sum"] == 0
    assert "preplanning" not in g["full_run_clocks"]


def test_completed_business_requires_all_legs_and_actual_report():
    rows=[row("in",0,"storage_in",0),row("out",0,"storage_out",1)]
    bags=[bag("in",0,0,3),bag("out",3,3,10.1)]
    r=mod.analyze(rows,bags,cutoff=10,horizon=20)
    assert r["completed_businesses_at_cutoff"] == 0
    assert r["cutoff_states"] == {"completed":1,"admitted_in_transit":1}


def test_missing_hca_counters_are_null_not_inferred_from_seconds():
    rows=[row("x",0,"direct",0)]
    r=mod.analyze(rows,[bag("x",0,7,10)],cutoff=20,horizon=20)
    assert r["longest_full_run_head_retries"][0]["attempts"] is None
    assert r["longest_full_run_head_retries"][0]["search_expansions"] is None
    assert group(r,0,"direct")["full_run_counters"]["retries"] == {"known_segments":0,"sum":None}


def test_stable_original_row_order_for_same_nominal_release():
    rows=[row("z",0,"direct",0),row("a",1,"direct",0)]
    bags=[bag("z",0,2,4),bag("a",3,3,5)]
    r=mod.analyze(rows,bags,cutoff=1,horizon=10)
    assert r["source_heads_at_cutoff"][0]["head_segment_id"] == "z"
    with pytest.raises(ValueError,match="predecessor"):
        mod.analyze(rows,list(reversed([bag("z",1,2,4),bag("a",0,0,5)])),cutoff=1,horizon=10)


def test_missing_or_duplicate_population_is_rejected():
    rows=[row("x",0,"direct",0)]
    with pytest.raises(ValueError,match="Exactly one"):
        mod.analyze(rows,[])
    with pytest.raises(ValueError,match="Exactly one"):
        mod.analyze(rows,[bag("x",0,0,1),bag("x",0,0,1)])


def test_early_ebs_attempt_is_rejected():
    rows=[row("in",0,"storage_in",0),row("out",0,"storage_out",1)]
    with pytest.raises(ValueError,match="eligibility"):
        mod.analyze(rows,[bag("in",0,0,4.1),bag("out",4,4,6)],cutoff=10,horizon=10)


def test_statistics_never_pretends_known_subset_is_full_population():
    s=mod.statistics([1,3],3)
    assert s["known_subset_mean"] == 2
    assert s["full_population_mean"] is None
    assert s["denominator"] == 3
