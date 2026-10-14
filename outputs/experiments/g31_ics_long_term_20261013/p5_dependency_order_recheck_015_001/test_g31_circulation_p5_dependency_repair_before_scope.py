"""Native counterexamples for public dependency repair, not mocked physics."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.joint_window_repair import build_domain, submit_action
from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.p5_dependency_repair import (
    local_inflight_minimum_windows, publish_observed_loaded_dependencies, repair_observed_occupancy)
from scripts.experiments.g31_ics_circulation.p5_receiving_cut_certificate import certify
from scripts.experiments.g31_ics_circulation.p5_validate_dependency_repair import execute_branch
from scripts.experiments.g31_ics_circulation.validate_joint_circulation_factor import (
    OWNERS, common_prefix, circulation_factor_input)
from scripts.experiments.g31_ics_circulation.validate_joint_window_repair import SCENARIOS


@pytest.fixture(scope="module")
def native():
    fallback = Path(__file__).absolute().parents[1] / "build_lt_session_006/python"
    return load_native(os.environ.get("G31_CIRCULATION_BINARY", str(next(fallback.glob("czr005_circulation*.pyd")))))


def setup_initial(native, scenario=3):
    session, _, _ = common_prefix(native, circulation_factor_input(SCENARIOS[scenario]))
    observed = session.observe("A")
    domain = build_domain(observed)
    action = next(a for a in domain["actions"] if a["action_id"] == domain["selected"]["ordinary_public_windows"])
    submitted = submit_action(session, action, observed)
    return session, [r["request"]["request_id"] for r in submitted["submissions"]]


def test_actual_loaded_message_obeys_resource_owner_not_broadcast(native):
    session, _ = setup_initial(native)
    session.advance_to(.91)
    messages = publish_observed_loaded_dependencies(session, OWNERS)
    assert [(m["source_owner"], m["target_owner"], m["tray_id"], m["next"]) for m in messages] == [("A", "A", "T0", 2)]
    assert messages[0]["reply"]["status"] == "pending"
    session.advance_to(.91+.02)
    assert any(m.get("tray_id") == "T0" for m in session.observe("A")["delivered_messages"])
    assert not any(m.get("tray_id") == "T0" for m in session.observe("C")["delivered_messages"])


def test_inconsistent_conditional_predictions_are_reported_without_fake_physical_infeasibility(native):
    session, owned = setup_initial(native)
    session.advance_to(.91)
    publish_observed_loaded_dependencies(session, OWNERS)
    session.advance_to(.91+.02)
    repair = repair_observed_occupancy(session, "A", owned, trigger="source")
    assert repair["status"] == "repair_submitted"
    assert repair["selected_action"]["inconsistent_fixed_predictions"]
    assert not repair["selected_action"]["conditional_forecast_conflicts"]
    assert repair["normal_service_guarantee"] is False
    assert {(s["request"]["tray_id"], s["request"]["source"], s["request"]["destination"]) for s in repair["submissions"]} == {("T1", 1, 4)}
    session.advance_to(10.11)
    window = next(w for w in local_inflight_minimum_windows(session.observe("A")) if w["resource"] == "node:2")
    assert window["proof"]["tray_id"] == "T0" and window["end"] == pytest.approx(401.75)
    assert "minimum_occupancy_only" in window["proof"]["scope"]
    assert not local_inflight_minimum_windows(session.observe("C"))


def test_budget_failure_does_not_cancel_actual_soft_requests(native):
    session, owned = setup_initial(native)
    session.advance_to(.91)
    before = session.offline_state_sha256()
    reply = repair_observed_occupancy(session, "A", owned, trigger="source", max_bundle=1)
    assert reply["status"] == "unknown_domain_budget"
    assert not reply["cancellations"] and session.offline_state_sha256() == before


def test_no_change_no_native_mutation(native):
    session, owned = setup_initial(native, scenario=1)
    session.advance_to(.91)
    before = session.offline_state_sha256()
    reply = repair_observed_occupancy(session, "A", owned, trigger="source")
    assert reply["status"] == "no_observed_source_change"
    assert session.offline_state_sha256() == before


def test_later_soft_retime_can_harm_other_service_despite_local_capacity_feasibility(native):
    data = circulation_factor_input(SCENARIOS[3])
    one, _ = execute_branch(native, data, "ordinary_public_windows", "source_only_with_publication")
    two, raw = execute_branch(native, data, "ordinary_public_windows", "two_boundary_dependency")
    assert one["audit"]["status"] == two["audit"]["status"] == "passed"
    assert one["metrics"]["completed"] == two["metrics"]["completed"] == 6
    assert two["resource_repair_status"] == "repair_submitted"
    jobs = lambda r: {j["business_bag_id"]: j for j in r["metrics"]["per_job"]}
    assert jobs(two)["D0"]["completed_at"] > jobs(one)["D0"]["completed_at"] + 399
    assert jobs(two)["D1"]["completed_at"] < jobs(one)["D1"]["completed_at"] - 399
    assert raw["resource_repair"]["normal_service_guarantee"] is False
    assert not raw["resource_repair"]["selected_action"]["observed_minimum_conflicts"]


@pytest.fixture
def certificate_inputs(native):
    data = circulation_factor_input(SCENARIOS[3])
    session, _, _ = common_prefix(native, data)
    # These are comparison TARGETS for the analytical checker, not fabricated
    # execution outcomes. The campaign certificate separately binds real raw
    # reference files and their hashes. Unit tests need no ignored output tree.
    reference = {"policies": {
        "ordinary_public_windows": {"metrics": {"per_job": [{"business_bag_id": "D1", "completed": True, "completed_at": 403.5}]}},
        "WAIT": {"metrics": {"per_job": [{"business_bag_id": "UNSEEN", "completed": True, "completed_at": 480.711}]}}}}
    return data, session.result_at(.11)["receipts"], reference


def test_fixed_graph_cut_excludes_unsupported_joint_baseline_target(certificate_inputs):
    result = certify(*certificate_inputs)
    assert result["status"] == "proved_target_intersection_impossible_under_declared_contract"
    assert result["minimum_total_exclusive_time"] == 800
    assert result["available_physical_time_until_both_targets"] == pytest.approx(480.711)
    assert result["online_use"] is False


@pytest.mark.parametrize("change", ["capacity", "bypass", "new_tray", "late_target", "one_crossing_two_sequential_services"])
def test_cut_certificate_does_not_generalize_beyond_its_conditions(certificate_inputs, change):
    data, receipts, reference = deepcopy(certificate_inputs)
    if change == "capacity":
        next(n for n in data["node_contracts"] if n["node"] == 2)["capacity"] = 2
    elif change == "bypass":
        data["edge_records"].append([0, 4, .5, 1.])
    elif change == "new_tray":
        data["trays"].append({"tray_id": "EXTRA", "node": 4})
    elif change == "late_target":
        next(j for j in reference["policies"]["WAIT"]["metrics"]["per_job"] if j["business_bag_id"] == "UNSEEN")["completed_at"] = 1000.
    else:
        # One cut can carry UNSEEN to5; after unloading it can reach D1's
        # source4 without a second crossing, despite different bag endpoints.
        next(j for j in data["jobs"] if j["business_bag_id"] == "UNSEEN")["destination"] = 5
        data["edge_records"].append([5, 4, .5, 1.])
    assert certify(data, receipts, reference)["status"] in ("unknown", "bound_inconclusive")
