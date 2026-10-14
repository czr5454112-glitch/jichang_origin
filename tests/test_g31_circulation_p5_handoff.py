"""Public-contract and finite-reference guards; no alternate physical simulator."""
from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation.analytic_control import PublicTravel
from scripts.experiments.g31_ics_circulation.p5_handoff import (
    FACTORS, build_domain, predicted_completion, scenario_input)
from scripts.experiments.g31_ics_circulation.p5_handoff_run import pending_feedback_boundary, summarize


def public_projection(reserve=False):
    data = scenario_input(dict(FACTORS[0], reserve_third=reserve))
    data.update(owner_id="A", now=.11, version=6, known_faults=[])
    data["trays"] = [{"tray_id": f"T{i}", "node": i, "mode": "hold", "edge_to": -1,
                       "available_at": .81, "business_bag_id": f"U{i}"} for i in range(3)]
    data["jobs"] = [dict(j, status="waiting_for_tray" if j["business_bag_id"] in ("D0", "D1") else "completed",
                         storage_node=j.get("storage_node", -1), storage_release_at=j.get("storage_release_at", 0.),
                         storage_min_dwell=j.get("storage_min_dwell", 0.)) for j in data["jobs"] if j["business_bag_id"] != "P"]
    data["delivered_messages"] = [{"kind": "service_forecast", "status": "conditional", "message_id": "public:P:1",
        "source_owner": "C", "target_owner": "A", "tray_id": "TP", "next": 3,
        "observed_at": .05, "delivered_at": .07, "generation": 1, "publication_sequence": 1,
        "entry_estimate": 2.05, "release_estimate": 4.1}]
    return data


def test_reception_lease_starts_at_grant_not_transport_arrival():
    domain = build_domain(public_projection())
    ordinary = next(a for a in domain["actions"] if a["action_id"] == domain["selected"]["ordinary_arrival_assignment"])
    c = next(c for c in ordinary["candidates"] if c["request"]["destination"] == 3)
    lease = next(w for w in c["footprint"] if w["resource"] == "node:3")
    assert lease["start"] == c["request"]["earliest_departure"] < c["predicted_arrival"]
    assert c["individual_conflicts"]
    assert domain["selected"]["joint_handoff"] == domain["selected"]["strong_service_assignment"]


def test_service_slack_absorbs_late_arrival_only_before_gate():
    obs = public_projection()
    job = next(j for j in obs["jobs"] if j["business_bag_id"] == "D1")
    travel = PublicTravel(obs)
    assert predicted_completion(job, 1., travel) == predicted_completion(job, 3., travel)
    assert predicted_completion(job, 12., travel) > predicted_completion(job, 3., travel)
    no_gate = dict(job, storage_release_at=0.)
    assert predicted_completion(no_gate, 3., travel) > predicted_completion(no_gate, 1., travel)


def test_legal_source_reserve_is_not_removed_for_joint_reassignment():
    domain = build_domain(public_projection(reserve=True))
    assert "T2" not in {s["tray_id"] for s in domain["base"]["supplies"]}
    assert all(c["request"]["tray_id"] != "T2" for a in domain["actions"] for c in a["candidates"])


def test_remote_demand_does_not_grant_private_storage_contract():
    obs = public_projection()
    removed = next(j for j in obs["jobs"] if j["business_bag_id"] == "D1")
    obs["jobs"].remove(removed)
    obs["delivered_messages"].append({"kind": "demand", "source_owner": "B", "target_owner": "A",
        "observed_at": .05, "delivered_at": .07, "jobs": [{"business_bag_id": "D1", "origin": 4,
            "arrival": 0., "deadline": 150., "status": "waiting_for_tray"}]})
    domain = build_domain(obs)
    assert domain["status"] == "unknown_private_service_contract" and not domain["actions"]
    with pytest.raises(ValueError, match="local_full_service"):
        predicted_completion({"origin": 4, "destination": 13}, 1., PublicTravel(obs))


def test_exceeded_finite_domain_is_unknown_not_best_of_prefix():
    result = build_domain(public_projection(), max_actions=1)
    assert result["status"] == "unknown_domain_budget"
    assert "selected" not in result


def test_public_readset_changes_request_identity_but_not_physical_tiebreak():
    a = public_projection()
    b = deepcopy(a); b["version"] += 1
    da, db = build_domain(a), build_domain(b)
    assert da["selected"] == db["selected"]
    aa, ab = da["actions"][1], db["actions"][1]
    assert aa["candidates"][0]["request"]["request_id"] != ab["candidates"][0]["request"]["request_id"]


def test_incomplete_reference_cannot_certify_a_metric_improvement():
    result = summarize([{"action_id": "A", "status": "execution_exception"}],
        {"ordinary_arrival_assignment": "A", "strong_service_assignment": "A", "WAIT": "A"}, ["P", "D"])
    assert all(r["status"] == "unknown_missing_baseline" for r in result["reference"].values())


def test_actual_feedback_refuses_hard_grant_without_cancelling(monkeypatch):
    from scripts.experiments.g31_ics_circulation import p5_handoff_run as runner
    class Session:
        def fork(self): return self
        def advance_to(self, _time, **_kwargs): return {"status": "reached", "horizon_complete": True}
        def observe(self, _owner): return {"transfers": [{"request_id": "r", "status": "in_transit"}]}
        def cancel_transfer_intent(self, *_args): raise AssertionError("must not cancel a hard entitlement")
    monkeypatch.setattr(runner, "submit_action", lambda *_args: {"status": "submitted",
        "submissions": [{"request": {"request_id": "r", "issued_at": .1, "message_delay": .1}}]})
    with pytest.raises(ValueError, match="must_not_cancel_hard"):
        pending_feedback_boundary(Session(), {}, {})


def test_reached_clock_with_unresolved_request_does_not_close_reference():
    metrics = {"cost": 10., "per_job": [{"business_bag_id": "D", "restricted_time": 10.,
        "completed": False, "status": "waiting_for_tray", "deadline_violated_by_horizon": False}]}
    rows = [{"action_id": "base", "status": "verified", "metrics": metrics, "completion": {"status": "reached"}},
            {"action_id": "late", "status": "unresolved_at_horizon", "metrics": metrics, "completion": {"status": "reached"}}]
    result = summarize(rows, {"ordinary_arrival_assignment": "base", "strong_service_assignment": "base", "WAIT": "base"}, ["D"])
    assert all(r["status"] == "unknown_incomplete_domain" and r["headroom_vs_baseline"] is None for r in result["reference"].values())


def test_inconsistent_external_predictions_are_unknown_not_empty_feasible_set():
    obs = public_projection()
    obs["delivered_messages"].append(dict(obs["delivered_messages"][0], message_id="public:P2:1", tray_id="TP2"))
    result = build_domain(obs)
    assert result["status"] == "unknown_inconsistent_fixed_predictions"
    assert result["inconsistent_fixed_predictions"] and not result["actions"]
    assert result["hard_infeasibility_certified"] is False
