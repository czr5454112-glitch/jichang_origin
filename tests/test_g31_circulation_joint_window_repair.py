"""Joint proposal scope and native counterexamples; no independent simulator."""
from copy import deepcopy
import os
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation.analytic_control import PublicTravel
from scripts.experiments.g31_ics_circulation.joint_window_repair import _footprint, build_domain, digest, proposal_order, submit_action
from scripts.experiments.g31_ics_circulation.joint_window_feedback import repair_observed_source_change
from scripts.experiments.g31_ics_circulation.native_host import load_native
from scripts.experiments.g31_ics_circulation.validate_joint_window_repair import SCENARIOS, evaluate, prefix, scenario_input
from scripts.experiments.g31_ics_circulation.validate_joint_circulation_factor import circulation_factor_input, common_prefix
from scripts.experiments.g31_ics_circulation.analytic_control import run_online_matching
from scripts.experiments.g31_ics_circulation.native_host import audit_result
from scripts.experiments.g31_ics_circulation.validate_analytic_control import replay_input


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if binary is None:
        fallback = Path(__file__).absolute().parents[1] / "build_lt_session_006/python"
        binary = next(fallback.glob("czr005_circulation*.pyd"))
    return load_native(binary)


def test_long_incoming_reservation_starts_at_entry_not_arrival():
    observation = scenario_input(SCENARIOS[2])
    observation["now"] = 0
    travel = PublicTravel(observation)
    windows = _footprint(observation, [0, 2, 3], 1.65, "empty", travel)
    incoming = next(w for w in windows if w["resource"] == "node:2")
    assert incoming["start"] == pytest.approx(1.7)
    assert incoming["end"] - incoming["start"] == pytest.approx(1000.05)
    assert not any(w["resource"] == "node:3" for w in windows)  # unbounded remote lease is unknown
    assert any(w["resource"] == "headway:2:3" for w in windows)


def test_actual_shared_capacity_conflict_is_conditional_not_native_infeasibility(native):
    data = scenario_input(SCENARIOS[0])
    parent, _ = prefix(native, data)
    observation = parent.observe("A")
    domain = build_domain(observation)
    assert len(domain["actions"]) == 31
    ordinary = next(a for a in domain["actions"] if a["action_id"] == domain["selected"]["ordinary_public_windows"])
    assert ordinary["conditional_conflicts"]
    actual = evaluate(parent, data, observation, ordinary, 5000)
    assert actual["status"] == "verified" and actual["audit"]["status"] == "passed"
    assert actual["metrics"]["completed"] == 5
    assert domain["atomic_commit_supported"] is False
    assert "remote_receiving_live_occupancy_and_lease_duration" in domain["unclosed_dependencies"]


def test_5000m_touching_windows_round_outward_without_removing_candidates(native):
    parent, _ = prefix(native, scenario_input(SCENARIOS[2]))
    domain = build_domain(parent.observe("A"))
    for name in ("one_round_same_assignment", "joint_conditional_repair"):
        chosen = next(a for a in domain["actions"] if a["action_id"] == domain["selected"][name])
        assert chosen["served_count"] == 2 and not chosen["conditional_conflicts"]


def test_unseen_source_job_cannot_change_public_domain(native):
    known, _ = prefix(native, scenario_input(SCENARIOS[1]))
    unseen, _ = prefix(native, scenario_input(SCENARIOS[3]))
    assert known.observe("A") == unseen.observe("A")
    left, right = build_domain(known.observe("A")), build_domain(unseen.observe("A"))
    assert left["actions"] == right["actions"] and left["selected"] == right["selected"]
    assert "UNSEEN" not in str(left["base"])


@pytest.mark.parametrize("limit", [0, 1, 5])
def test_budget_censor_does_not_return_a_fake_best(native, limit):
    parent, _ = prefix(native, scenario_input(SCENARIOS[0]))
    domain = build_domain(parent.observe("A"), max_actions=limit)
    assert domain["status"] == "unknown_domain_budget" and "selected" not in domain


def test_stale_native_owner_read_set_is_no_mutation(native):
    parent, _ = prefix(native, scenario_input(SCENARIOS[0]))
    observed = parent.observe("A")
    action = build_domain(observed)["actions"][-1]
    parent.advance_to(.8)
    before = parent.offline_state_sha256()
    assert submit_action(parent, action, observed)["status"] == "stale_read_set"
    assert parent.offline_state_sha256() == before


class FakeOwner:
    def __init__(self, observation, replies=()):
        self.observation, self.replies, self.requests = observation, iter(replies), []
    def observe(self, owner):
        return self.observation
    def submit_transfer_intent(self, request):
        self.requests.append(request)
        return next(self.replies)


def test_unchanged_version_but_clock_advanced_still_invalidates_candidate():
    original = {"owner_id": "A", "version": 7, "now": 1.}
    session = FakeOwner(dict(original, now=2.))
    assert submit_action(session, {"candidates": []}, original)["reason"] == "decision_clock_changed"
    assert not session.requests


def test_partial_native_rejection_is_not_silent_atomic_success():
    observation = {"owner_id": "A", "version": 7, "now": 1.}
    session = FakeOwner(observation, ({"status": "pending"}, {"status": "rejected", "reason": "source_module_min_stock"}))
    action = {"public_read_sha256": digest(observation),
              "candidates": [{"request": {"request_id": "live:a"}}, {"request": {"request_id": "live:b"}}]}
    reply = submit_action(session, action, observation)
    assert reply["status"] == "partial_or_rejected" and reply["atomic"] is False
    assert len(reply["submissions"]) == 2 and len(session.requests) == 2


@pytest.mark.parametrize("mutation", ["new_pledge", "cancel_pledge"])
def test_same_clock_pending_pledge_changes_real_read_set_even_if_native_version_unchanged(native, mutation):
    session, _ = prefix(native, scenario_input(SCENARIOS[0]))
    original = session.observe("A")
    initial = build_domain(original)
    first = deepcopy(next(a for a in initial["actions"] if len(a["candidates"]) == 2)["candidates"][0]["request"])
    first["request_id"] += ":independent-controller"
    if mutation == "new_pledge":
        observed, domain = original, initial
        assert session.submit_transfer_intent(first)["status"] == "pending"
    else:
        assert session.submit_transfer_intent(first)["status"] == "pending"
        observed = session.observe("A")
        domain = build_domain(observed)
        assert session.cancel_transfer_intent(first["request_id"], "A")["status"] == "cancelled"
    current = session.observe("A")
    assert current["version"] == observed["version"] and current["now"] == observed["now"]
    assert current != observed
    action = next(a for a in domain["actions"] if a["candidates"])
    before = session.offline_state_sha256()
    reply = submit_action(session, action, observed)
    assert reply["status"] == "stale_read_set" and reply["reason"] == "public_dependency_changed"
    assert session.offline_state_sha256() == before


def test_large_timestamp_candidate_labels_are_exact_and_unique(native):
    parent, _ = prefix(native, scenario_input(SCENARIOS[0]))
    observation = parent.observe("A")
    observation["now"] = 1.e13
    domain = build_domain(observation)
    assert domain["status"] == "complete_finite_public_domain"
    actions = domain["actions"]
    assert len({a["action_id"] for a in actions}) == len(actions)
    candidates = {c["candidate_id"]: c for a in actions for c in a["candidates"]}
    for c in candidates.values():
        assert float.fromhex(c["candidate_id"].split(":t")[1]) == c["request"]["earliest_departure"]


def test_terminal_clearing_pressure_has_local_observation_clock(native):
    parent, _ = prefix(native, scenario_input(SCENARIOS[0]))
    observation = parent.observe("A")
    # A supplied projection unit case: an actually available terminal tray,
    # plus an approaching local loaded tray creates the non-business pressure
    # column. It is not fabricated as a real native execution in any receipt.
    observation["trays"].append({"tray_id": "terminal-empty", "mode": "empty", "node": 0,
                                  "edge_to": -1, "business_bag_id": "", "generation": 0})
    next(n for n in observation["node_contracts"] if n["node"] == 0)["occupancy"] = 1
    domain = build_domain(observation, max_supplies=4, max_actions=20000)
    pressure = [r for a in domain["actions"] for c in a["candidates"] for r in c["read_set"]
                if r["kind"] == "terminal_receiving_pressure"]
    assert pressure and all(r["observed_at"] == observation["now"] for r in pressure)


def test_equal_cost_policy_tie_is_invariant_to_opaque_identity_encoding():
    def action(identity, early, late):
        return {"action_id": identity, "served_count": 2, "predicted_arrival_sum": 405.,
                "candidates": [{"supply": 0, "demand": 0, "request": {"earliest_departure": early}},
                               {"supply": 1, "demand": 1, "request": {"earliest_departure": late}}]}
    first = action("z-hex-encoding", 1.65, 401.7)
    second = action("a-decimal-encoding", 401.7, 1.65)
    assert min([first, second], key=proposal_order) is first
    first["action_id"], second["action_id"] = second["action_id"], first["action_id"]
    assert min([second, first], key=proposal_order) is first


@pytest.mark.parametrize("source_changed", [False, True])
def test_feedback_uses_actual_new_source_state_and_preserves_valid_assignment(native, source_changed):
    data = scenario_input(SCENARIOS[3] if source_changed else SCENARIOS[1])
    parent, _ = prefix(native, data)
    observation = parent.observe("A")
    domain = build_domain(observation)
    joint = next(a for a in domain["actions"] if a["action_id"] == domain["selected"]["joint_conditional_repair"])
    submitted = submit_action(parent, joint, observation)
    parent.advance_to(.91)
    before = parent.offline_state_sha256()
    reply = repair_observed_source_change(parent, "A", [s["request"]["request_id"] for s in submitted["submissions"]])
    if not source_changed:
        assert reply["status"] == "no_observed_source_change" and not reply["cancellations"]
        assert parent.offline_state_sha256() == before
        return
    assert reply["status"] == "repair_submitted"
    assert len(reply["cancellations"]) == 2 and all(r["reply"]["status"] == "cancelled" for r in reply["cancellations"])
    assert reply["retained_assignments"] == [("T1", 1, 4)]
    assert len(reply["submissions"]) == 1
    assert reply["submissions"][0]["request"]["earliest_departure"] == pytest.approx(1.65)
    observed_jobs = {j["business_bag_id"]: j for j in reply["observation"]["jobs"]}
    assert observed_jobs["UNSEEN"]["arrival"] == .9
    result = parent.result_at(5000)
    assert len(result["jobs"]) == 6
    finished = {j["business_bag_id"]: j for j in result["jobs"]}
    assert finished["D1"]["completed_at"] == pytest.approx(403.5)
    assert finished["UNSEEN"]["status"] == "in_transit"


def test_circulation_factor_is_separate_from_absorbing_terminal_contract():
    original = scenario_input(SCENARIOS[3])
    before = deepcopy(original)
    factor = circulation_factor_input(SCENARIOS[3])
    assert original == before
    assert not any(e[0] == 10 for e in original["edge_records"])
    assert [e for e in factor["edge_records"] if e[0] == 10] == [(10, 7, .5, 1.)]
    assert factor["jobs"] == original["jobs"] and factor["trays"] == original["trays"]
    assert factor["node_contracts"] == original["node_contracts"]


def test_common_continuation_really_reuses_terminal_tray_without_extra_initial_tick(native):
    data = circulation_factor_input(SCENARIOS[3])
    session, state, publications = common_prefix(native, data)
    observed = session.observe("A")
    domain = build_domain(observed)
    action = next(a for a in domain["actions"] if a["action_id"] == domain["selected"]["ordinary_public_windows"])
    initial = submit_action(session, action, observed)
    run = run_online_matching(session, ["A", "B", "C"], horizon=2000., predictive=True,
        control_period=10., message_delay=.1, demand_delay=.02, respect_service_forecasts=True,
        controller_state=deepcopy(state), compact_projection=False)
    assert run["publication_records"][0]["tick"] == 1
    assert run["control_records"][0]["decision"]["now"] == pytest.approx(10.11)
    assert len(publications["demand_publications"]) == 6
    result = run["result"]
    assert result["advance"]["horizon_complete"] is True
    assert len(result["jobs"]) == 6 and all(j["completed_at"] >= 0 for j in result["jobs"])
    sequence = [r["business_bag_id"] for r in result["receipts"] if r["tray_id"] == "TP" and r["event"] == "LOAD_START"]
    assert sequence == ["P", "D0"]
    enter = next(r for r in result["receipts"] if r["tray_id"] == "TP" and r["event"] == "EDGE_ENTER" and r["from"] == 10)
    assert enter["to"] == 7 and not enter["business_bag_id"]
    audit_result(replay_input(data, initial["submissions"] + run["submitted"]), result)
