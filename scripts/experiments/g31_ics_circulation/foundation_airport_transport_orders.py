"""JSON-owned empty-order metadata, separate from native departure leases.

This is an upper-level coordinator of owner observations and its own issuance.
Only a delivered native status releases a submitted claim. It grants neither
remote tray authority nor physical receiving capacity.
"""
from __future__ import annotations

import copy
from collections import Counter
import math

from .foundation_airport_batch_patch import digest

SCHEMA = "g31.terminal_flow.orders.v1"
FAILED = {"rejected", "cancelled", "failed", "expired", "recovered"}
COMMITTED = {"accepted", "granted", "dispatching", "departed", "in_transit"}


def ledger(policy_state):
    return policy_state.setdefault("empty_transport_orders", {
        "schema": SCHEMA, "orders": {}, "counts": {},
        "coordination": "upper_public_coordinator_owner_confirmed_native_execution"})


def _count(book, key):
    book["counts"][key] = book["counts"].get(key, 0) + 1


def reconcile(policy_state, observation):
    """Use this owner's delivered ledger; expiry never releases pending work."""
    book = ledger(policy_state)
    rows = {r["request_id"]: r for r in observation.get("client_transfer_ledger", [])}
    for order in book["orders"].values():
        row = rows.get(order.get("request_id"))
        if row is None:
            continue
        status = row["status"]
        order["native_status"] = status
        order["last_status_observed_at"] = observation["now"]
        if status in FAILED:
            new = status.upper()
        elif status == "received":
            new = "RECEIVED"
        elif status in {"departed", "in_transit"}:
            new = "DEPARTED"
        elif status in COMMITTED:
            new = "ACCEPTED"
        else:
            new = "SUBMITTED"
        # A later pending view is not authority to undo a delivered commitment.
        if order["status"] in {"ACCEPTED", "DEPARTED", "RECEIVED"} and new == "SUBMITTED":
            continue
        if new != order["status"]:
            order["status"] = new
            _count(book, new.lower())
        for field in ("received_at", "departed_at"):
            if row.get(field, -1) >= 0:
                order[field] = row[field]
    return book


def outstanding_uncredited(policy_state, projection, *, detailed=False):
    """Logical receiver claims, excluding supply already counted by this view.

    Pending claims reduce suggested allocations, but are never added to stock.
    Received claims remain until a current capture supersedes their old receipt.
    """
    book = ledger(policy_state)
    credited = {r["commitment_id_or_dependency"] for r in projection.supply_events
                if r["availability_kind"] == "accepted_inbound"}
    covered = {r.get("request_id") for r in projection.audit["deduplication_and_unknown"]
               if r.get("reason") in {"commitment_already_covered_by_capture",
                                      "historical_receipt_superseded_by_newer_commitment"}}
    actual_captures = {r["physical_tray_id"]: r.get("captured_at") for r in projection.supply_events
                       if r["availability_kind"] == "actual_current"
                       and projection.actual_by_tray.get(r["physical_tray_id"]) == r["location"]}
    def observed_after(captured_at, cutoff):
        return (type(captured_at) in (int, float) and type(cutoff) in (int, float)
                and math.isfinite(captured_at) and math.isfinite(cutoff)
                and 0 <= cutoff <= captured_at)
    counts = Counter()
    outstanding = []
    for order in book["orders"].values():
        if order["status"] in {s.upper() for s in FAILED}:
            continue
        if order["status"] in {"PLANNED", "SUPERSEDED", "EXPIRED_PLAN"}:
            continue
        if order.get("request_id") in credited or order.get("request_id") in covered:
            continue
        receiver = projection.nodes[order["destination_terminal"]]
        received_at = order.get("received_at")
        if (order["status"] == "RECEIVED" and receiver["inventory_known"]
                and observed_after(receiver["inventory_as_of"], received_at)):
            continue
        identity = order["physical_tray_id"]
        if identity in projection.actual_by_tray:
            # A source still visible during PENDING is not a destination receipt.
            # Nor can a valid-but-old peer capture supersede a later receipt.
            captured_at = actual_captures.get(identity)
            if order["status"] == "RECEIVED":
                if observed_after(captured_at, received_at):
                    continue
            elif (projection.actual_by_tray[identity] == order["destination_terminal"]
                    and observed_after(captured_at, order.get("proposed_at"))):
                continue
        counts[order["destination_terminal"]] += 1
        outstanding.append(order)
    return outstanding if detailed else dict(counts)


def plan_order(policy_state, *, plan, candidate, projection, exact_projection, decision_context):
    book = ledger(policy_state)
    identity = digest([plan["plan_id"], decision_context, candidate["tray_id"],
                       candidate["source"], candidate["destination"]])
    before = exact_projection.get("destination_without_move") or {}
    shortage = before.get("first_shortage_offset")
    target = None if shortage is None else projection.now + shortage
    travel_and_command = candidate["nominal_arrival_time"] - projection.now
    order = dict(order_id=identity, order_type="EMPTY_TRAY_TRANSFER",
        reason="ORDINARY_RETURN" if candidate["source_category"] == "ordinary_return" else "FORECAST_REPOSITION",
        forecast_guided=projection.forecast is not None, plan_id=plan["plan_id"],
        physical_tray_id=candidate["tray_id"], source_terminal=candidate["source"],
        destination_terminal=candidate["destination"], owner_scope=projection.owner,
        forecast_id=plan.get("forecast_id"), status="PLANNED", request_id=None,
        target_by=target, useful_until=projection.now+projection.horizon_seconds,
        latest_issue_estimate=None if target is None else target-travel_and_command,
        plan_valid_until=plan["plan_valid_until"], native_expiry=candidate["intent"]["expiry"],
        estimated_arrival=candidate["nominal_arrival_time"], proposed_at=projection.now,
        allocation_epoch=plan.get("forecast_id") or plan["plan_id"],
        allocation_valid_until=plan["plan_valid_until"],
        allocation_slot_id=digest([candidate["destination"], identity]),
        decision_id=decision_context.get("decision_id"), native_business_deadline=None)
    book["orders"][identity] = order
    _count(book, "proposed")
    return copy.deepcopy(order)


def record_submission(policy_state, *, decision, request_id, reply, exception_type=None):
    choice = decision.get("joint_selection", {}).get("choice", {})
    metadata = choice.get("empty_transport_order")
    if metadata is None:
        return
    book = ledger(policy_state)
    order = book["orders"][metadata["order_id"]]
    if order["request_id"] is not None and order["request_id"] != request_id:
        raise ValueError("terminal_flow:retry_changed_request_identity")
    order.update(request_id=request_id, status="SUBMITTED", submission_reply=copy.deepcopy(reply),
                 submission_exception_type=exception_type)
    _count(book, "submitted")
    if reply is not None and reply.get("status") in FAILED:
        order["status"] = reply["status"].upper()
        _count(book, order["status"].lower())
    # Pending/exception means reserved identity, never accepted inventory.


def record_priority_submission(policy_state, *, payload, request_id, reply, exception_type=None):
    """Actual-demand and clearing orders share the same identity/claim ledger."""
    book = ledger(policy_state)
    identity = "native_priority:"+request_id
    if identity in book["orders"]:
        raise ValueError("terminal_flow:priority_retry_must_use_native_outbox")
    reason = ("NECESSARY_CLEARING" if payload.get("control_reason") == "terminal_receiving_pressure"
              else "REAL_DEMAND_SUPPLY")
    order = dict(order_id=identity, order_type="EMPTY_TRAY_TRANSFER", reason=reason,
        forecast_guided=False, plan_id=None, physical_tray_id=payload["tray_id"],
        source_terminal=payload["source"], destination_terminal=payload["destination"],
        owner_scope=payload["owner_id"], status="SUBMITTED", request_id=request_id,
        proposed_at=payload["issued_at"], native_expiry=payload["expiry"],
        plan_valid_until=None, target_by=None, useful_until=None,
        latest_issue_estimate=None, allocation_epoch="actual_demand", allocation_slot_id=identity,
        native_business_deadline=None, submission_reply=copy.deepcopy(reply),
        submission_exception_type=exception_type)
    if reply is not None and reply.get("status") in FAILED:
        order["status"] = reply["status"].upper()
    book["orders"][identity] = order
    _count(book, "proposed"); _count(book, "submitted")
    _count(book, "reason:"+reason)


def supersede_unsubmitted(policy_state, now):
    for order in ledger(policy_state)["orders"].values():
        if order["status"] == "PLANNED" and now >= order["plan_valid_until"]:
            order["status"] = "EXPIRED_PLAN"
