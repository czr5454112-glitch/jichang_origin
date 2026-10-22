"""Order identity, exact ETA, caches and native-boundary quota regressions."""
from copy import deepcopy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_projection as projection
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_control as flow
from scripts.experiments.g31_ics_circulation import foundation_airport_transport_orders as orders
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_control as joint
from scripts.experiments.g31_ics_circulation import foundation_airport_joint_opportunities as opportunities
from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_rule as rules
from scripts.experiments.g31_ics_circulation import protocol_control as protocol
from test_g31_airport_joint_interface import two_sources
from test_g31_airport_inventory_rule import observation, PublicSession
from test_g31_foundation_airport_joint_projection import forecast


def prepared(obs):
    obs.update(observation_scope="controller_policy")
    current = opportunities.prepare_current(obs, rules.r0_priority_planner(obs), message_delay=2.)
    catalog = opportunities.build_joint_catalog(current)
    projected = projection.prepare_inventory_projection(obs, prepared_current=current)
    return current, catalog, projected


def test_optional_no_value_holds_but_ordinary_returns_and_soft_time_is_not_lease():
    policy = flow.TransportPolicy()
    current, menu, projected = prepared(observation(source=1, stock=2))
    state = {}
    result = policy.select(current, menu, projected, policy_state=state, decision_context={"tick": 1})
    assert result["action_id"] == "a_noop"
    current, menu, projected = prepared(two_sources())
    result = policy.select(current, menu, projected, policy_state={}, decision_context={"tick": 1})
    order = result["empty_transport_order"]
    action = next(r for r in menu["candidates"] if r["action_id"] == result["action_id"])
    assert order["reason"] == "ORDINARY_RETURN"
    assert order["target_by"] is None
    assert order["native_expiry"] == action["intent"]["expiry"]
    assert "target_by" not in action["intent"]


def test_same_accounts_cache_and_event_change_invalidates_after_json_restore():
    current, menu, projected = prepared(observation(source=1, stock=2))
    policy = flow.TransportPolicy(recompute_period_seconds=300.)
    state = {}
    first = policy.select(current, menu, projected, policy_state=state, decision_context={"tick": 1})
    restored = json.loads(json.dumps(state))
    second = policy.select(current, menu, projected, policy_state=restored, decision_context={"tick": 2})
    assert second["cache"]["hit"]
    assert second["flow_plan"]["plan_id"] == first["flow_plan"]["plan_id"]
    obs = deepcopy(current.observation)
    obs["node_contracts"][2]["capacity"] += 1
    changed = policy.select(*prepared(obs), policy_state=restored, decision_context={"tick": 3})
    assert changed["cache"]["invalidation_reason"] == "event_changed"


class PolicyAdapter:
    def __init__(self):
        self.flow = flow.TransportPolicy()

    def __call__(self, current, catalog, *, policy_state, decision_context):
        projected = projection.prepare_inventory_projection(current.observation, prepared_current=current)
        return self.flow.select(current, catalog, projected, policy_state=policy_state, decision_context=decision_context)

    def on_submission(self, **kwargs):
        self.flow.on_submission(**kwargs)


@pytest.mark.parametrize("failure", ["rejected", "exception", "pending"])
def test_real_submit_identity_and_quota_survive_lost_reply_and_plan_expiry(failure):
    session = PublicSession()
    session.current["observation_scope"] = "controller_policy"
    def send(payload):
        session.transfer_calls.append(deepcopy(payload))
        if failure == "exception":
            raise RuntimeError("lost_reply")
        return {"status": failure}
    session.submit_protocol_transfer = send
    client = protocol.ProtocolClient(session, inventory_snapshots=True)
    state = {"next_tick": 1}
    options = dict(compact=True, command_delay=2., priority_error=False,
        stock_return_selector=joint.JointPostPrioritySelector(PolicyAdapter()),
        stock_return_selector_identity="TF-test")
    if failure == "exception":
        with pytest.raises(RuntimeError, match="lost_reply"):
            protocol._post_inventory_return(client, "A", state, **options)
    else:
        protocol._post_inventory_return(client, "A", state, **options)
    saved = json.loads(json.dumps(state))
    book = orders.ledger(saved["joint_post_priority"]["policy_state"])
    order = next(iter(book["orders"].values()))
    assert order["request_id"] == session.transfer_calls[0]["request_id"]
    assert order["status"] == ("REJECTED" if failure == "rejected" else "SUBMITTED")
    orders.supersede_unsubmitted(saved["joint_post_priority"]["policy_state"], 100000.)
    assert order["status"] != "EXPIRED_PLAN"
    assert protocol._post_inventory_return(client, "A", saved, **options)["reason"] == "owner_tick_return_quota_spent"
    assert len(session.transfer_calls) == 1


def test_two_owner_pending_claim_not_stock_and_delivered_failure_releases_slot():
    current, menu, projected = prepared(two_sources())
    state = {}
    choice = flow.TransportPolicy().select(current, menu, projected, policy_state=state, decision_context={"tick": 1})
    decision = {"joint_selection": {"choice": choice}}
    orders.record_submission(state, decision=decision, request_id="request", reply={"status": "pending"})
    destination = choice["empty_transport_order"]["destination_terminal"]
    assert orders.outstanding_uncredited(state, projected) == {destination: 1}
    assert projected.nodes[destination]["stock"] == 0.
    obs = deepcopy(current.observation)
    obs["client_transfer_ledger"] = [{"request_id": "request", "status": "rejected"}]
    orders.reconcile(state, obs)
    assert not orders.outstanding_uncredited(state, projected)


@pytest.mark.parametrize("native_reason,reason", [("observed_source_queue", "REAL_DEMAND_SUPPLY"),
    ("terminal_receiving_pressure", "NECESSARY_CLEARING")])
def test_priority_empty_orders_share_claims_and_cannot_expire_as_plans(native_reason, reason):
    current, menu, projected = prepared(two_sources())
    payload = deepcopy(menu["candidates"][1]["intent"])
    payload["control_reason"] = native_reason
    state = {}
    orders.record_priority_submission(state, payload=payload, request_id="actual-priority",
        reply=None, exception_type="LostReply")
    order = orders.ledger(state)["orders"]["native_priority:actual-priority"]
    assert order["reason"] == reason and order["status"] == "SUBMITTED"
    assert orders.outstanding_uncredited(state, projected) == {payload["destination"]: 1}
    orders.supersede_unsubmitted(state, 100000.)
    assert order["status"] == "SUBMITTED"
    assert order["native_expiry"] == payload["expiry"]
