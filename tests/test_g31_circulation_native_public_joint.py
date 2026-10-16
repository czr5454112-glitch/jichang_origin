"""Candidate fairness, fail-closed readiness and strict physical assessment."""
import copy
import pytest
from scripts.experiments.g31_ics_circulation import research_native_public_joint as run


def test_preregistered_twelve_rows_keep_negative_readiness_outside_business_metrics():
    plan = run.plan()
    assert plan["native_branch_budget"] == len(plan["rows"]) == 12
    assert sum(r["scope"] == "normal_business_comparison" for r in plan["rows"].values()) == 9
    assert sum(r["scope"] == "first_action_readiness_only" for r in plan["rows"].values()) == 3
    assert all(r["status"] == "unknown_unexecuted" for r in plan["rows"].values())


@pytest.mark.parametrize("receipt", [{"status": "unknown"},
    {"status": "conditional_validated_data", "native_delivery_verified": False},
    {"status": "conditional_native_delivered_model_input", "native_delivery_verified": False}])
def test_only_actual_native_collection_admits_model_proposal(receipt):
    assert run.choose(receipt, "joint_model")["selected_action"] is None


def test_fixed_model_has_same_candidate_timing_permissions_but_only_route1(monkeypatch):
    actions = [{"initial_next": 1, "departure": .11}, {"initial_next": 2, "departure": .11},
               {"initial_next": 1, "departure": 2.21}]
    monkeypatch.setattr(run.model, "candidates_from_durations", lambda b: (actions, actions[2]))
    monkeypatch.setattr(run.model, "propose", lambda b, a, i: {"actions": a, "incumbent": i})
    receipt = {"status": "conditional_native_delivered_model_input", "native_delivery_verified": True, "bundle": {}}
    fixed = run.choose(receipt, "fixed_route_model")
    joint = run.choose(receipt, "joint_model")
    assert fixed["actions"] == [actions[0], actions[2]] and joint["actions"] == actions
    assert fixed["incumbent"] == joint["incumbent"]


def test_all_three_regimes_all_four_jobs_strict_protection():
    rows = run.plan()["rows"]
    for row in rows.values(): row.update(status="assessed", summary={"completion": {j: 10. for j in ("loaded", "receiver", "reuse1", "reuse2")}})
    rows["gate6/joint_model"]["summary"]["completion"]["loaded"] += 1e-12
    report = run.assess_normal(rows)
    assert report["6.0"]["status"] == "assessed" and not report["6.0"]["joint_strict_protected"]
    rows["gate12/fixed_route_model"]["status"] = "unknown_failed"
    assert run.assess_normal(rows)["12.0"]["status"] == "unknown_incomplete_three_arm_comparison"
