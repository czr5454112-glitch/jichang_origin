"""Pure v3 runner admission, equal-domain and no-new-admission policy tests."""
import copy
import math
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import research_native_preexisting_v3 as runner
from test_g31_circulation_preexisting_v3_data_adapter import pair


def rows():
    result = runner.protocol("business")["rows"]
    for value in result.values():
        value.update(status="assessed", summary={"completion":dict.fromkeys(runner.model.JOBS,1.),
            "completion_sum":5., "business_complete":True,"common_horizon_complete":True,
            "audit":{"status":"passed"},"rolling_model_inputs_verified":True,"rolling_fallback_count":0})
    return result


def test_same_six_cases_ten_arms_and_fixed_initial_all_four_windows():
    plan = runner.protocol("business")
    assert len(plan["rows"]) == plan["native_branch_budget"] == 60
    assert len(runner.protocol("delivery_gate")["rows"]) == 9
    for case in runner.domain.cases():
        offered = [r for r in plan["rows"].values() if r["case"] == case]
        assert len(offered) == 10 and {r["method"] for r in offered} == set(runner.METHODS)
        assert {r["method"] for r in offered if r["method"].startswith("fixed_window_")} == {"fixed_window_"+str(i) for i in range(4)}
        data = runner.native_scene(case)
        assert len(data["jobs"]) == 5 and len(data["trays"]) == 3
        assert len(data["heuristic_time"]) == 10 and all(len(row)==10 for row in data["heuristic_time"])
    assert "Native physics and immutable retries continue" in plan["collection_policy_amendment"]


@pytest.mark.parametrize("bad", ["unrun", "unfinished", "censored", "nonfinite", "wrong_sum", "missing_job"])
def test_every_fixed_reference_row_is_required_and_unfinished_is_unknown(bad):
    values=rows(); case=runner.domain.cases()[0]["case_id"]; row=values[case+"/fixed_window_3"]
    if bad=="unrun": row["status"]="unknown_unexecuted"
    elif bad=="unfinished": row["summary"]["completion"]["blocker"]=-1.
    elif bad=="censored": row["summary"]["common_horizon_complete"]=False
    elif bad=="nonfinite": row["summary"]["completion"]["blocker"]=math.inf
    elif bad=="wrong_sum": row["summary"]["completion_sum"]=4.
    else: del row["summary"]["completion"]["blocker"]
    report=runner.assess(values,"business")[case]
    assert not report["complete_fixed_family"] and len(report["methods"])==10
    assert report["methods"]["resource_pair_repair"]["strict_protected_vs_complete_finite_fixed_family"] is None


def test_fifth_job_one_ulp_regression_is_not_protected():
    values=rows();case=runner.domain.cases()[0]["case_id"]
    value=values[case+"/resource_pair_repair"]["summary"]
    value["completion"]["blocker"]=math.nextafter(1.,math.inf);value["completion_sum"]=sum(value["completion"].values())
    assert runner.assess(values,"business")[case]["methods"]["resource_pair_repair"]["strict_protected_vs_incumbent"] is False


def test_forged_native_flags_or_saved_json_do_not_authorize_a_proposal():
    info={"status":"conditional_native_delivered_later_v3_model_input","native_delivery_verified":True,
        "online_information_delivered":True}
    for method in runner.METHODS:
        assert runner.choose(info,method)["selected_action"] is None


def test_source_fact_invitation_uses_v3_nesting_and_reply_is_not_an_invitation():
    view,ack,inbox,_=pair("B",phase="first_return")
    envelope=inbox[0]
    assert runner.invitation_phase(envelope,"B",view["now"])=="first_return"
    assert runner.invitation_phase(ack["planning_snapshot_v3"],"A",view["now"]) is None
    wrong=copy.deepcopy(envelope);wrong["schema"]="g31.planning_snapshot.v2"
    assert runner.invitation_phase(wrong,"B",view["now"]) is None


def test_reply_hold_is_finite_phase_scoped_and_does_not_change_native_clock():
    clock=SimpleNamespace(physical_time=5.)
    policy=runner.OwnerPolicy(None,clock,None,"A",None,None,"coordinate_strict",None)
    policy.hold_new_admissions_after_reply("reuse1_loading_ack_refresh","preflight",5.)
    assert policy.peer_quiet_until==-1. and not policy.quiet_periods
    policy.hold_new_admissions_after_reply("first_reuse_route","loaded-message",5.)
    assert policy.peer_quiet_until==5.+runner.COLLECTION_LIMIT and clock.physical_time==5.
    assert policy.quiet_periods[0]["native_physics_paused"] is False


def test_overlap_collection_cannot_admit_a_physical_action_during_peer_hold():
    policy=runner.OwnerPolicy(None,None,None,"A",None,None,"coordinate_strict",None)
    policy.pending={"phase":"first_return","deadline":4.}
    policy.peer_quiet_until=5.08
    policy.decide_pending({"now":5.})  # No outbox, native collector or action may be touched.
    assert policy.pending is not None and not policy.decisions


def test_semantic_boolean_cannot_construct_native_session():
    class NoNative:
        @property
        def NativeSession(self): raise AssertionError("Native session must not construct")
    with pytest.raises(ValueError,match="semantic_gate_missing"):
        runner.run_branch(NoNative(),{}, {}, {"passed":True})
