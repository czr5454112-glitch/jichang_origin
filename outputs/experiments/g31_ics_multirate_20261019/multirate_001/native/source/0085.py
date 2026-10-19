"""Proposed v2 extension validator; supplied data never authenticates delivery.

This is a reference contract for a future native capture endpoint. It does not
read a native result, issue commands, or infer completion from an absent job.
The v1 capture/digest and the earlier online adapter are intentionally unchanged.
"""
from __future__ import annotations

import copy
import math


SCHEMA = "g31.planning_extension.v2"
COMPLETION_SCOPE = "all_source_owned_destination_unload_completions_through_capture"
ACTION_SCOPE = "all_source_submitted_physical_operations_last_delivered_ack"
PHYSICAL_KINDS = frozenset(("transfer", "route", "cancel_transfer"))
TERMINAL_BY_KIND = {
    "transfer": frozenset(("received", "rejected", "cancelled", "failed", "expired")),
    "route": frozenset(("updated", "rejected", "failed", "expired")),
    "cancel_transfer": frozenset(("cancelled", "rejected", "failed", "expired")),
}


def _number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def validate_extension(extension, *, source_owner, captured_at, node_owners,
                       retained_job_contracts, local_action_ledger=None):
    """Check proposed source facts, while preserving the native trust boundary.

``retained_job_contracts`` must eventually come from this owner's earlier
delivered capture ledger, not a complete experiment input. This pure function
cannot verify that provenance and therefore never returns online=True.

Every physical operation is represented, including already delivered terminal
ones, so the reference is deliberately simple and auditable. A later compact
wire format needs its own authenticated coverage rule, not silent omission.
``local_action_ledger`` is optional for peer validation; the deciding owner
must supply its own exact submitted ID/kind set before using a self capture.
"""
    reasons = []
    def fail(reason):
        reasons.append(reason)
    try:
        if extension.get("schema") != SCHEMA:
            fail("unsupported_extension_schema")
        if (extension.get("source_owner") != source_owner or not _number(captured_at)
                or captured_at < 0 or extension.get("captured_at") != captured_at):
            fail("source_or_capture_mismatch")
        owned_nodes = sorted(n for n, owner in node_owners.items() if owner == source_owner)
        completion = extension["completion_coverage"]
        if (completion.get("scope") != COMPLETION_SCOPE
                or completion.get("complete_for_declared_scope") is not True
                or completion.get("through") != captured_at
                or completion.get("source_owned_destination_nodes") != owned_nodes
                or completion.get("future_events_included") is not False):
            fail("incomplete_destination_receipt_scope")
        receipts = extension["terminal_receipts"]
        ids, completed, previous_completion = set(), {}, -1.
        for sequence, row in enumerate(receipts, 1):
            job_id = row["business_bag_id"]
            contract = retained_job_contracts.get(job_id)
            if (type(row["source_local_sequence"]) is not int or row["source_local_sequence"] != sequence or row["receipt_id"] in ids
                    or row["receipt_id"] != f"completion:{len(source_owner.encode('utf-8'))}:{source_owner}:{sequence}"):
                fail("invalid_completion_identity_or_sequence")
            ids.add(row["receipt_id"])
            if (not contract or job_id in completed or row.get("event") != "UNLOAD_COMPLETE"
                    or row.get("status") != "completed" or row.get("source_owner") != source_owner
                    or row.get("destination") != contract.get("destination")
                    or node_owners.get(row.get("destination")) != source_owner
                    or not row.get("tray_id") or not _number(row.get("completed_at"))
                    or not 0 <= row["completed_at"] <= captured_at
                    or row["completed_at"] < previous_completion):
                fail("invalid_or_unauthorized_completion_receipt")
            completed[job_id] = row
            previous_completion = row["completed_at"]
        if completion.get("completed_business_bag_ids") != [r["business_bag_id"] for r in receipts]:
            fail("completion_coverage_membership_mismatch")
        coverage = extension["action_coverage"]
        if (coverage.get("scope") != ACTION_SCOPE or coverage.get("through") != captured_at
                or coverage.get("complete_for_declared_scope") is not True
                or coverage.get("includes_unsubmitted_python_plans") is not False
                or coverage.get("uses_hidden_execution_truth") is not False):
            fail("incomplete_or_overclaimed_action_scope")
        actions, ids, unresolved, pairs = extension["submitted_physical_actions"], set(), [], []
        for row in actions:
            request_id, kind = row["request_id"], row["kind"]
            if not request_id or request_id in ids or kind not in PHYSICAL_KINDS or row.get("source_owner") != source_owner:
                fail("invalid_action_identity_kind_or_owner")
            ids.add(request_id); pairs.append((request_id, kind))
            ack = row.get("last_delivered_ack")
            if ack is None:
                unresolved.append(request_id); continue
            if (not isinstance(ack.get("sequence"), int) or isinstance(ack.get("sequence"), bool)
                    or ack["sequence"] <= 0 or not _number(ack.get("delivered_at"))
                    or not 0 <= ack["delivered_at"] <= captured_at):
                fail("invalid_or_future_delivered_action_ack")
            if ack.get("status") not in TERMINAL_BY_KIND.get(kind, ()):
                unresolved.append(request_id)
        if (coverage.get("submitted_request_ids") != [r["request_id"] for r in actions]
                or coverage.get("unresolved_request_ids") != unresolved):
            fail("action_coverage_membership_or_resolution_mismatch")
        if pairs != sorted(pairs):
            fail("noncanonical_action_identity_order")
        if local_action_ledger is not None and pairs != sorted(local_action_ledger):
            fail("self_capture_differs_from_owned_submission_ledger")
        if unresolved:
            fail("unresolved_source_physical_action")
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        fail("malformed_extension")
        completed, unresolved = {}, []
    return {"status": "unknown" if reasons else "conditional_extension_data",
        "reasons": sorted(set(reasons)), "completed_receipts": copy.deepcopy(completed),
        "unresolved_request_ids": unresolved, "native_delivery_verified": False,
        "online_information_delivered": False, "native_protection_certified": False,
        "future_source_actions_certified_absent": False}
