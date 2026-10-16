import copy
import pytest
from scripts.experiments.g31_ics_circulation import public_executable_preference_actions as actions


def inputs(phase="initial"):
    owner, node, job = ("A", 0, "loaded") if phase == "initial" else ("B", 7, "reuse1")
    return dict(phase=phase, view={"owner_id": owner, "now": 1.,
        "trays": [{"tray_id": "L", "business_bag_id": job, "node": node, "mode": "loaded",
            "edge_from": -1, "edge_to": -1, "generation": 1, "traversal_id": 0}],
        "jobs": [{"business_bag_id": job, "allow_suffix_reroute": True}]}, request_id="fresh",
        public_command_delay=.01, projected_intervals={
            "complete_declared_action_and_tray_coverage": True,
            "current_target_can_enter_reason": "allowed", "dispatch_earliest": 1.09,
            "dispatch_latest": 1.11, "receiving_clear_through": 40.,
            "known_competitor_entry_earliest": 40., "provenance": {"status": "supplied_public_bound_fixture"}})


def test_same_32_actions_and_four_windows_in_each_fixed_initial_family():
    result = actions.domain([.11, 1.11, 2.21, 3.11])
    assert result["candidate_count"] == result["shared_evaluation_budget"] == 32
    for family in result["fixed_initial_families"].values():
        assert len(family) == 16
        assert {r["empty_departure"] for r in family} == {.11, 1.11, 2.21, 3.11}
    assert result["native_default_expected_next"] is None


@pytest.mark.parametrize("windows", [[.11, .11, 1., 2.], [0., 1., 2.], [0., 1., 3., 2.],
                                     [0., 1., 2., float("inf")], [False, 1., 2., 3.]])
def test_invalid_window_domain_rejected(windows):
    with pytest.raises(ValueError): actions.domain(windows)


@pytest.mark.parametrize("phase", ["initial", "first_reuse_route"])
def test_default_is_absence_of_route_update_not_fixed_next(phase):
    supplied = inputs(phase)
    supplied["request_id"] = None
    supplied["projected_intervals"] = {}
    result = actions.materialize("native_default", **supplied)
    assert result["status"] == "declared_native_default"
    assert result["request"] is None and result["actual_next"] is None and result["requested_next"] is None
    assert result["r1_update_executed"] is False


@pytest.mark.parametrize("phase,choice,target", [("initial", "prefer_2", 2), ("first_reuse_route", "prefer_8", 8)])
def test_preference_materializes_true_source_local_command_with_audit_required(phase, choice, target):
    result = actions.materialize(choice, **inputs(phase))
    assert result["status"] == "conditional_submission_proposal"
    assert result["request"]["next"] == target and result["request"]["message_delay"] == .01
    assert result["requires_delivered_native_ack"] and result["requires_actual_edge_audit"]
    assert result["actual_next"] is None


def test_source_already_committed_does_not_preissue_an_old_prefix():
    supplied = inputs(); supplied["view"]["trays"][0]["edge_to"] = 1
    assert actions.materialize("prefer_2", **supplied)["reason"] == "source_not_current_uncommitted_loaded_stage"


def test_current_receiving_full_never_becomes_successful_default():
    supplied = inputs(); supplied["projected_intervals"]["current_target_can_enter_reason"] = "receiving_full"
    result = actions.materialize("prefer_2", **supplied)
    assert result["status"] == "unknown" and result["reason"] == "current_target_not_allowed"


def test_competitor_can_arrive_between_command_and_dispatch_is_unknown():
    supplied = inputs(); supplied["projected_intervals"]["known_competitor_entry_earliest"] = 1.05
    assert actions.materialize("prefer_2", **supplied)["reason"] == "receiving_competition_can_cross_command_dispatch_interval"


def test_same_timestamp_wire_and_dispatch_not_assumed_executable():
    supplied = inputs(); supplied["projected_intervals"]["dispatch_earliest"] = 1.01
    assert actions.materialize("prefer_2", **supplied)["reason"] == "command_not_strictly_before_possible_dispatch"


def test_bounds_need_explicit_derivation_and_complete_action_coverage():
    supplied = inputs(); supplied["projected_intervals"]["provenance"] = None
    assert actions.materialize("prefer_2", **supplied)["reason"] == "missing_interval_derivation_provenance"
    supplied = inputs(); supplied["projected_intervals"]["complete_declared_action_and_tray_coverage"] = False
    assert actions.materialize("prefer_2", **supplied)["status"] == "unknown"
