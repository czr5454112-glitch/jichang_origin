"""Cross-owner claims, exact dispatch order and checkpoint regression gates."""
import json

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_projection as projection
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as r0
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_opportunities as joint
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_control as control
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_orders as orders
from test_g31_airport_inventory_rule import observation
from test_g31_foundation_airport_joint_projection import fixture, forecast, add_request

def policy_context(obs, demand=None):
    obs["observation_scope"] = "controller_policy"
    obs.pop("control_projection", None)
    current = joint.prepare_current(obs, r0.r0_priority_planner(obs), message_delay=2.)
    return current, joint.build_joint_catalog(current), projection.prepare_inventory_projection(
        obs, forecast=demand, prepared_current=current)


def pending_other_owner(state, *, destination=2):
    orders.ledger(state)["orders"]["remote"] = dict(order_id="remote", request_id="remote-request",
        status="SUBMITTED", owner_scope="B", physical_tray_id="remote-tray",
        destination_terminal=destination)


def test_uncredited_claim_retains_next_receiver_marginal_for_new_source():
    obs = observation(source=1, stock=2)
    current, catalog, projected = policy_context(obs, forecast(obs, {2: [2.]+[0.]*29}))
    state = {}
    pending_other_owner(state)
    plan = control.TransportPolicy()._solve(current, catalog, projected, state)
    assert len(plan["chosen"]) == 1
    assert plan["chosen"][0]["destination"] == 2


def test_received_then_loaded_tray_does_not_resurrect_receiver_claim():
    obs = fixture((0, 2, 0))
    obs["trays"].append(dict(tray_id="received-busy", node=2, mode="loading", available_at=40.,
        edge_to=-1, reception_node=-1, generation=1, business_bag_id="live-business"))
    obs["node_contracts"][2]["occupancy"] = 1
    add_request(obs, identity="received-busy", status="received", received_at=8.)
    _, _, projected = policy_context(obs)
    state = {}
    book = orders.ledger(state)
    book["orders"]["old"] = dict(status="RECEIVED", request_id="r1", physical_tray_id="received-busy",
        destination_terminal=2)
    assert any(row.get("reason") == "commitment_already_covered_by_capture"
        for row in projected.audit["deduplication_and_unknown"])
    assert orders.outstanding_uncredited(state, projected) == {}


def test_ordinary_fallback_cannot_bypass_known_other_owner_receiver_reservation():
    obs = observation(source=0, stock=1)
    obs["static_role_contract"]["loader_nodes"] = [2]
    obs["node_contracts"][2]["capacity"] = 1
    current, catalog, projected = policy_context(obs)
    state = {}
    pending_other_owner(state)
    result = control.TransportPolicy().select(current, catalog, projected, policy_state=state,
        decision_context={"tick": 1, "decision_id": "blocked-return"})
    assert result["action_id"] == "a_noop"
    assert result.get("empty_transport_order") is None


def test_exact_first_action_and_dispatch_profile_agree_after_json_restore():
    obs = observation(source=0, stock=2)
    for node in (1, 2):
        obs["node_contracts"][node]["capacity"] = 1
    demand = forecast(obs, {1: [0.]*9+[.1]+[0.]*20, 2: [5.]+[0.]*29})
    current, catalog, projected = policy_context(obs, demand)
    policy, state = control.TransportPolicy(), {}
    first = policy.select(current, catalog, projected, policy_state=state,
        decision_context={"tick": 1, "decision_id": "first"})
    assert first["execution_dispatch_profile"][0]["action_id"] == first["action_id"]
    state = json.loads(json.dumps(state))
    restored = policy.select(current, catalog, projected, policy_state=state,
        decision_context={"tick": 1, "decision_id": "restored"})
    assert restored["action_id"] == first["action_id"]
    assert restored["execution_dispatch_profile"][0]["action_id"] == restored["action_id"]


def test_own_pending_claim_deducts_receiving_capacity_once():
    obs = fixture((0, 3, 0))
    add_request(obs, identity="T1-0", status="pending")
    obs["client_transfer_ledger"][0]["source"] = 1
    obs["transfers"][0]["source"] = 1
    current, catalog, projected = policy_context(obs)
    state = {}
    orders.ledger(state)["orders"]["own"] = dict(status="SUBMITTED", request_id="r1",
        physical_tray_id="T1-0", destination_terminal=2)
    plan = control.TransportPolicy()._solve(current, catalog, projected, state)
    receiver = next(row["receiver"] for row in plan["station_table"] if row["node"] == 2)
    assert receiver["current_space"] == 10
    assert receiver["available_slots"] == 9


def test_received_busy_tray_in_other_owner_capture_clears_old_claim():
    obs = fixture((0, 2, 0))
    obs["trays"].append(dict(tray_id="received-busy", node=2, mode="loading", available_at=40.,
        edge_to=-1, reception_node=-1, generation=1, business_bag_id="live-business"))
    obs["node_contracts"][2]["occupancy"] = 1
    _, _, projected = policy_context(obs)  # receiver has no sender's own request ledger
    state = {}
    orders.ledger(state)["orders"]["other"] = dict(status="RECEIVED", request_id="remote-request",
        physical_tray_id="received-busy", destination_terminal=2, received_at=8., owner_scope="B")
    assert orders.outstanding_uncredited(state, projected) == {}

