import copy
import math

import pytest

from scripts.experiments.g31_ics_circulation import public_route_preference_model as model


def request(next_node=3, name="route-1"):
    return {"request_id": name, "owner_id": "B", "tray_id": "L", "business_bag_id": "reuse1",
            "from": 7, "next": next_node, "expected_generation": 5, "expected_traversal": 5, "expiry": 12.}


def state(at=7.70):
    return {"at": at, "coverage_complete": True, "current_state_certified": False,
            "tray_id": "L", "node": 7, "generation": 5, "public_traversal": 5,
            "stationary": True, "active_leg": True, "resource_owner": "B", "business_bag_id": "reuse1",
            "allow_suffix_reroute": True, "directed_edge": True, "static_suffix_reachable": True,
            "advertised_fault": False, "deadline": 40., "optimistic_completion": 10.4,
            "can_enter_reason": "allowed"}


def candidates(blocked=False, score3=3.7, score8=2.7):
    return [{"next": 3, "base_score": score3, "allowed": not blocked,
             "advertised_fault": False, "reason": "circulation:receiving_full" if blocked else "allowed"},
            {"next": 8, "base_score": score8, "allowed": True, "advertised_fault": False, "reason": "allowed"}]


def preference(next_node=3, name="route-1"):
    return model.project_command(request(next_node, name), state(), at=7.70)


def test_updated_preference_changes_ranking_but_is_not_a_reservation():
    p = preference()
    result = model.project_dispatch(candidates(), state(), [p], at=7.75)
    assert p["command_status"] == "updated" and p["actual_next"] is None
    assert not p["reserves_receiving_capacity"]
    assert result["actual_next"] == 3
    assert model.project_dispatch(candidates(True), state(), [p], at=7.75)["actual_next"] == 8
    assert not result["native_execution_certified"]


def test_receiving_already_full_at_command_is_rejected_not_installed():
    s = state(); s["can_enter_reason"] = "circulation:receiving_full"
    p = model.project_command(request(), s, at=7.70)
    assert p["command_status"] == "rejected"
    result = model.project_dispatch(candidates(True), state(), [p], at=7.75)
    assert result["active_preference_request_id"] is None and result["actual_next"] == 8


def test_best_blocked_does_not_always_turn_into_best_allowed():
    c = candidates(True, 1., 2.)
    assert model.project_dispatch(c, state(), [], at=7.75)["actual_next"] is None
    assert model.project_dispatch(c, state(), [], at=7.75, same_bag_handoff=True)["actual_next"] == 8


def test_latest_accepted_blocked_preference_supersedes_earlier_allowed_preference():
    earlier = preference(8, "earlier")
    later = preference(3, "later")
    result = model.project_dispatch(candidates(True, 1., 2.), state(), [earlier, later], at=7.75)
    assert result["active_preference_request_id"] == "later" and result["actual_next"] is None


def test_rejection_does_not_remove_previous_accepted_preference():
    earlier = preference(8, "earlier")
    s = state(); s["can_enter_reason"] = "circulation:receiving_full"
    rejected = model.project_command(request(3, "later"), s, at=7.70)
    result = model.project_dispatch(candidates(True, 1., 2.), state(), [earlier, rejected], at=7.75)
    assert result["active_preference_request_id"] == "earlier" and result["actual_next"] == 8


@pytest.mark.parametrize("field,value", [("generation", 6), ("public_traversal", 6), ("node", 1), ("tray_id", "E")])
def test_old_prefix_preference_never_applies_to_new_identity(field, value):
    identity = state(); identity[field] = value
    result = model.project_dispatch(candidates(), identity, [preference()], at=7.75)
    assert result["active_preference_request_id"] is None and result["actual_next"] == 8


def test_native_expiry_equality_and_causal_time_are_explicit():
    p = preference(); p["request"]["expiry"] = 7.75
    assert model.project_dispatch(candidates(), state(), [p], at=7.75)["actual_next"] == 3
    assert model.project_dispatch(candidates(), state(), [p], at=math.nextafter(7.75, math.inf))["actual_next"] == 8
    assert model.project_dispatch(candidates(), state(), [p], at=7.69)["status"] == "unknown"


@pytest.mark.parametrize("score", [True, math.nan, math.inf, "3.7"])
def test_missing_or_invalid_score_cannot_be_silently_ranked(score):
    c = candidates(); c[0]["base_score"] = score
    assert model.project_dispatch(c, state(), [preference()], at=7.75)["status"] == "unknown"


def test_incomplete_execution_epoch_never_certifies_permission():
    s = state(); s["coverage_complete"] = False
    assert model.project_command(request(), s, at=7.70)["status"] == "unknown"
    assert model.project_command(request(), state(), at=7.71)["status"] == "unknown"


def guard_inputs():
    intent = request()
    view = {"now": 7.69, "owner_id": "B", "complete_declared_action_and_tray_coverage": True,
            "source_stationary_identity": {k: intent[k] for k in
                ("tray_id", "business_bag_id", "from", "expected_generation", "expected_traversal")},
            "current_target_can_enter_reason": "allowed"}
    bounds = {"at": 7.69, "command_delay": .01, "dispatch_earliest": 7.75, "dispatch_latest": 7.80,
              "receiving_clear_through": 8., "known_competitor_entry_earliest": 8.}
    return view, intent, bounds


def test_closed_loop_guard_covers_whole_command_to_dispatch_interval():
    view, intent, bounds = guard_inputs()
    assert model.source_local_submission_guard(view, intent, **bounds)["status"] == "conditional_submission_proposal"
    for time in (7.70, 7.71, 7.75, 7.79, 7.80):
        result = model.source_local_submission_guard(view, intent, **{**bounds, "known_competitor_entry_earliest": time})
        assert result["status"] == "unknown"
    assert model.source_local_submission_guard(view, intent, **{**bounds, "dispatch_latest": math.inf})["status"] == "unknown"


def test_current_owner_occupancy_and_identity_still_required():
    view, intent, bounds = guard_inputs()
    for field, value in (("owner_id", "A"), ("current_target_can_enter_reason", "circulation:receiving_full"),
                         ("complete_declared_action_and_tray_coverage", False), ("source_stationary_identity", {})):
        assert model.source_local_submission_guard({**view, field: value}, intent, **bounds)["status"] == "unknown"
