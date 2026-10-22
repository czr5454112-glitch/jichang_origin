"""Cross-owner claims, exact dispatch order and checkpoint regression gates."""
import json
import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_projection as projection
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as r0
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_opportunities as joint
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_control as control
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_orders as orders
from test_g31_airport_inventory_rule import observation, snapshot
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


def three_owner_capture_context(*, source_capture=2., destination_capture=2., tray_at_destination=False):
    """A owns a spare; B's old tray was received by C after their peer captures."""
    obs = observation(source=0, stock=2)
    obs.update(now=60., observation_scope="controller_policy", version=7)
    obs["static_role_contract"]["loader_nodes"] = [0, 1, 2]
    captures = []
    for node, owner, at, stock in ((1, "B", source_capture, int(not tray_at_destination)),
                                  (2, "C", destination_capture, int(tray_at_destination))):
        obs["node_contracts"][node].update(resource_owner=owner, zone=owner)
        for key in ("actual_available", "occupancy"):
            obs["node_contracts"][node].pop(key)
        envelope = snapshot(stock=stock, capture=at, delivery=at+2., expiry=at+120.)
        body = envelope["capture"]
        body.update(source_owner=owner, target_owner="A", message_id=owner+"-capture")
        body["coverage"]["local_node_ids"] = [node]
        body["nodes"][0]["node"] = node
        for tray in body["trays"]:
            tray["node"] = node
        envelope["payload_sha256"] = r0.capture_digest(body)
        captures.append(envelope)
    obs["planning_snapshots"] = captures
    return policy_context(obs, forecast(obs, {2: [1.]+[0.]*29}))


def received_other_owner(state, received_at=30.):
    order = dict(status="RECEIVED", request_id="B-transfer", physical_tray_id="B0",
        destination_terminal=2, source_terminal=1, owner_scope="B", proposed_at=10.)
    if received_at is not None:
        order["received_at"] = received_at
    orders.ledger(state)["orders"]["B-received"] = order


@pytest.mark.parametrize("capture_options,received_at,expected", [
    ({}, 30., {2: 1}),
    ({"tray_at_destination": True}, 30., {2: 1}),
    ({"source_capture": 35.}, 30., {}),
    ({"destination_capture": 35.}, 30., {}),
    ({"destination_capture": 35., "tray_at_destination": True}, 30., {}),
    ({}, None, {2: 1}),
    ({"source_capture": 35.}, None, {2: 1}),
    ({"destination_capture": 35., "tray_at_destination": True}, None, {2: 1}),
])
def test_cross_owner_received_claim_requires_capture_at_or_after_receipt(capture_options, received_at, expected):
    current, _, projected = three_owner_capture_context(**capture_options)
    # These are accepted complete delivered snapshots, not rejected stale payloads.
    assert all(current.inventory["nodes"][node]["known"] and current.inventory["nodes"][node]["reason"] is None
               for node in (1, 2))
    state = {}
    received_other_owner(state, received_at)
    restored = json.loads(json.dumps(state))
    assert orders.outstanding_uncredited(restored, projected) == expected


def test_stale_source_visibility_cannot_authorize_duplicate_forecast_replenishment():
    current, catalog, projected = three_owner_capture_context()
    assert projected.actual_by_tray["B0"] == 1
    assert next(row for row in projected.supply_events if row["physical_tray_id"] == "B0")["captured_at"] == 2.
    policy, state = control.TransportPolicy(), {}
    unclaimed = policy._solve(current, catalog, projected, state)
    assert len(unclaimed["chosen"]) == 1 and unclaimed["chosen"][0]["destination"] == 2
    received_other_owner(state)
    claimed = policy._solve(current, catalog, projected, state)
    assert claimed["receiver_claims_deducted"] == {2: 1}
    assert claimed["chosen"] == []


@pytest.mark.parametrize("destination_capture,expected", [(2., {2: 1}), (35., {})])
def test_pending_cross_owner_claim_is_not_covered_by_destination_capture_before_issuance(destination_capture, expected):
    _, _, projected = three_owner_capture_context(destination_capture=destination_capture, tray_at_destination=True)
    state = {}
    received_other_owner(state)
    orders.ledger(state)["orders"]["B-received"].update(status="SUBMITTED", proposed_at=30.)
    assert orders.outstanding_uncredited(state, projected) == expected

