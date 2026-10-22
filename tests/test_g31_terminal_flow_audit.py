"""Audit denominators distinguish advisory plan items from actual requests."""
from copy import deepcopy

from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_flow_audit import audit_records, audit_unified_order_book
from test_g31_terminal_transport_campaign import save


def records():
    action = dict(kind="transfer", tray_id="tray", source=0, destination=2, source_category="ordinary_return")
    profile = dict(tray_id="tray", source=0, destination=2, submit_at=10., dispatch_slot=0)
    plan = dict(plan_id="plan", owner_scope="A", information_asof=10., plan_valid_until=310.,
        chosen=[action, dict(action, tray_id="second")], dispatch_profile=[profile], flows=[])
    order = dict(order_id="order", plan_id="plan", physical_tray_id="tray",
                 source_terminal=0, destination_terminal=2, reason="ORDINARY_RETURN", forecast_guided=True)
    first = dict(decision_id="first", selection=dict(flow_plan=plan, empty_transport_order=order))
    second = dict(decision_id="second", selection=dict(flow_plan=deepcopy(plan)))
    trajectory = dict(decision_id="first", owner_id="A", decision_time=10., requested_action=action,
        public_observation_ref="current", legal_catalog_ref="menu", request_id="request",
        actual_submission=dict(request_id="request", issued_at=10.), ack=[dict(status="received")],
        received_event=dict(time=50.), physical_failure=False)
    again = dict(trajectory, decision_id="second", decision_time=70., requested_action=dict(kind="noop"),
                 request_id=None, actual_submission=None, ack=None, received_event=None)
    return [first, second], [trajectory, again], dict(transfers=[dict(request_id="request", status="received")])


def test_cached_plan_repeated_twice_is_one_plan_two_items_and_one_received_request():
    result = audit_records(*records())
    assert result["denominators"]["unique_plan_ids"] == 1
    assert result["denominators"]["unique_plan_item_keys"] == 2
    assert result["denominators"]["unique_order_ids"] == 1
    assert result["denominators"]["realized_items_per_unique_plan_item"] == .5
    assert result["denominators"]["received_per_submitted"] == 1.
    assert result["plans"][0]["occurrences"] == 2
    assert not result["violations"]


def test_rejected_request_stays_in_submitted_denominator():
    decisions, trajectory, terminal = records()
    trajectory[0].update(ack=[dict(status="rejected")], received_event=None, physical_failure=True)
    terminal["transfers"][0]["status"] = "rejected"
    result = audit_records(decisions, trajectory, terminal)
    assert result["denominators"]["unique_submitted_request_ids"] == 1
    assert result["denominators"]["unique_accepted_request_ids"] == 0
    assert result["denominators"]["received_per_submitted"] == 0.


def test_actual_legal_source_category_controls_ordinary_vs_extra():
    decisions, trajectory, terminal = records()
    decisions[0]["selection"]["empty_transport_order"]["reason"] = "FORECAST_REPOSITION"
    result = audit_records(decisions, trajectory, terminal)
    assert result["by_source_category"]["ordinary_return"]["unique_orders"] == 1
    assert result["by_source_category"]["extra_reposition"]["unique_orders"] == 0
    assert result["violations"][0]["reason"] == "metadata_category_disagrees_with_legal_source"


def test_unified_audit_retains_last_delivered_state_and_physical_receipt_separately(tmp_path):
    order = dict(order_id="priority:req", request_id="req", reason="REAL_DEMAND_SUPPLY",
        physical_tray_id="tray", source_terminal=0, destination_terminal=2, owner_scope="A",
        status="DEPARTED", proposed_at=10., native_expiry=90., target_by=None)
    save(tmp_path/"controller_checkpoint_scope.json", dict(policy_state=dict(empty_transport_orders=dict(orders={"id": order}))))
    save(tmp_path/"calls.json.gz", [dict(kind="transfer", retry=False, request=dict(request_id="req",
        tray_id="tray", source=0, destination=2, owner_id="A", issued_at=10., expiry=90.))])
    save(tmp_path/"terminal_evidence.json.gz", dict(transfers=[dict(request_id="req", status="received", received_at=49.)]))
    save(tmp_path/"delivered_ack_evidence.json.gz", dict(A=dict(delivered_transfer_acks=[dict(request_id="req", status="departed")])))
    audit = audit_unified_order_book(tmp_path)
    assert audit["request_sets_equal"]
    assert audit["by_reason"]["REAL_DEMAND_SUPPLY"]["accepted"] == 1
    assert audit["by_reason"]["REAL_DEMAND_SUPPLY"]["received"] == 1
    assert audit["chains"][0]["status"] == "DEPARTED"
    assert audit["chains"][0]["native_status"] == "received"
    assert not audit["violations"]
