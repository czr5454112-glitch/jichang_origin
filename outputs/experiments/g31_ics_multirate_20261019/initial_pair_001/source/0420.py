"""Conservative request-compute accounting for ordered event-controller traces.

Owner envelopes include observation, policy, submission and ACK processing.
Native envelopes include physics AND delivery-side permission validation; no
unmeasured validation is subtracted as simulation. Shared work is charged in
full to every dependent request, never divided by the batch size. These are
upper envelopes, not isolated native-stage timings or a realtime certificate.
"""
from __future__ import annotations

from collections import Counter
import math

from .protocol_control import TERMINAL


def summarize_request_spans(run: dict) -> dict:
    """Account a complete trace, including failures, retries and open requests.

    The combined trace_sequence starts at zero without gaps. Segment aggregators
    must offset per-call sequences without putting diagnostic counters in the
    resumable policy state. A missing prefix or invalid physical/call/ACK order
    fails closed with the complete known request denominator instead of
    silently reporting zero compute. The final scheduler/output-copy residual
    is charged once, in full, to each request as a conservative shared bound.
    """
    owners = run.get("control_records", [])
    batches = run.get("native_batches", [])
    outbox = run.get("controller_state", {}).get("client", {}).get("outbox", {})
    calls = run.get("client_calls", [])
    known_ids = set(outbox) | {call["request"]["request_id"] for call in calls}
    for record in owners:
        for key in ("publications", "service_actions", "attempts", "refreshed"):
            known_ids.update(item["request_id"] for item in record.get(key, []) if "request_id" in item)

    def unknown(status, errors):
        return {"schema": "g31.request_compute_envelopes.v1", "status": status,
                "request_count": len(known_ids), "attempt_count": len(calls),
                "requests": [{"request_id": rid, "status": "unknown_trace", "compute_upper_ms": None,
                              "complete_request_compute_upper_ms": None} for rid in sorted(known_ids)],
                "errors": errors, "complete_100ms_requirement_certified": False,
                "scope": "Trace identity/order is incomplete or inconsistent; all known call, owner-record and outbox identities remain in the denominator."}

    def valid_time(value):
        return (isinstance(value, (int, float)) and not isinstance(value, bool)
                and math.isfinite(value) and value >= 0)

    trace = [(r.get("trace_sequence"), "owner", r) for r in owners]
    trace += [(r.get("trace_sequence"), "native", r) for r in batches]
    seqs = [s for s, _, _ in trace]
    if any(not isinstance(s, int) or isinstance(s, bool) for s in seqs) or len(set(seqs)) != len(seqs):
        return unknown("unknown_missing_or_duplicate_trace_order", [{"reason": "missing_or_duplicate_trace_order"}])
    if sorted(seqs) != list(range(len(trace))):
        return unknown("unknown_incomplete_trace", [{"reason": "missing_trace_prefix_or_sequence_gap"}])
    wall = run.get("wall_seconds")
    if not valid_time(wall):
        return unknown("unknown_missing_total_wall", [{"reason": "missing_or_invalid_total_wall"}])
    # The outbox is immutable request history, not unacknowledged native truth.
    traced_ids = {call["request"]["request_id"] for call in calls}
    missing_history = sorted(set(outbox) - traced_ids)
    if missing_history:
        return {"schema": "g31.request_compute_envelopes.v1",
            "status": "unknown_missing_request_history",
            "request_count": len(known_ids),
            "attempt_count": len(calls), "untraced_request_ids": missing_history,
            "requests": [{"request_id": rid, "status": "unknown_history",
                          "compute_upper_ms": None} for rid in sorted(known_ids)],
            "complete_100ms_requirement_certified": False,
            "scope": "Partial or resumed trace: include the original request creation and all intervening segments; "
                     "existing outbox identities cannot disappear from the denominator."}
    requests = {}
    errors = []
    previous_call_at = -math.inf
    for call in calls:
        payload = call["request"]
        rid = payload["request_id"]
        if not valid_time(call.get("at")) or call["at"] < previous_call_at:
            errors.append({"request_id": rid, "reason": "invalid_or_reversed_client_call_time"})
        else:
            previous_call_at = call["at"]
        if rid not in requests:
            if call["retry"]:
                errors.append({"request_id": rid, "reason": "missing_initial_submission"})
            requests[rid] = {"request_id": rid, "owner_id": payload["owner_id"],
                "kind": call["kind"], "business_bag_id": payload.get("business_bag_id"),
                "causal_parent_request_id": payload.get("forecast_request_id", payload.get("parent_request_id")),
                "created_at": call["at"], "attempts": 0, "retries": 0,
                "status": "unknown_open", "owner_compute_upper_ms": 0.,
                "native_compute_upper_ms": 0., "max_continuous_envelope_ms": 0.,
                "span_sequences": [], "_payload": payload, "_started": False}
        row = requests[rid]
        if payload != row["_payload"] or call["kind"] != row["kind"]:
            raise ValueError("request_spans:mutated_retry_payload")
        if row["attempts"] and not call["retry"]:
            errors.append({"request_id": rid, "reason": "duplicate_initial_submission"})
        row["attempts"] += 1
        row["retries"] += bool(call["retry"])
    # Unique sequence numbers alone do not establish causality. In particular,
    # putting a native batch before its request's creation would omit its work
    # while still producing a misleadingly complete numeric upper envelope.
    previous_end = -math.inf
    seen_creation = set()
    for seq, kind, record in sorted(trace):
        start = record.get("start_at") if kind == "native" else record.get("at")
        end = record.get("end_at") if kind == "native" else start
        if not valid_time(start) or not valid_time(end) or end < start or start < previous_end:
            errors.append({"sequence": seq, "reason": "invalid_or_reversed_physical_trace_time"})
        else:
            previous_end = end
        if kind != "owner":
            continue
        owner = record.get("owner_id")
        new = record.get("publications", []) + record.get("service_actions", []) + record.get("attempts", [])
        for item in new:
            rid = item.get("request_id")
            if rid is None:
                continue
            row = requests.get(rid)
            if row is None:
                errors.append({"sequence": seq, "reason": "request_missing_client_call", "request_id": rid})
            elif rid in seen_creation:
                errors.append({"sequence": seq, "reason": "duplicate_request_creation", "request_id": rid})
            elif row["owner_id"] != owner or row["created_at"] != start:
                errors.append({"sequence": seq, "reason": "creation_call_owner_or_time_mismatch", "request_id": rid})
            seen_creation.add(rid)
        for item in record.get("refreshed", []):
            rid = item["request_id"]
            row = requests.get(rid)
            ack = item.get("view", {}).get("last_delivered_ack", {})
            if row is None or rid not in seen_creation or row["owner_id"] != owner:
                errors.append({"sequence": seq, "reason": "refresh_without_matching_owner_creation", "request_id": rid})
            if ack:
                delivered = ack.get("delivered_at")
                if (row is None or not valid_time(row["created_at"]) or not valid_time(delivered)
                        or not valid_time(start) or not row["created_at"] <= delivered <= start):
                    errors.append({"sequence": seq, "reason": "invalid_ack_delivery_order", "request_id": rid})
    if errors:
        return unknown("unknown_incomplete_trace", errors)
    activation_keys = {(record.get("owner_id"), record.get("at")) for record in owners}
    for call in calls:
        if (call["request"]["owner_id"], call["at"]) not in activation_keys:
            errors.append({"request_id": call["request"]["request_id"], "reason": "client_call_outside_owner_activation"})
    if errors:
        return unknown("unknown_incomplete_trace", errors)
    active = set()
    accounted = 0.
    unassociated_owner = []

    def charge(rid, key, amount, seq):
        row = requests[rid]
        row[key] += amount
        row["max_continuous_envelope_ms"] = max(row["max_continuous_envelope_ms"], amount)
        row["span_sequences"].append(seq)

    for seq, kind, record in sorted(trace):
        amount = record.get("compute_wall_ms" if kind == "owner" else "wall_ms")
        if not isinstance(amount, (int, float)) or not math.isfinite(amount) or amount < 0:
            errors.append({"sequence": seq, "reason": "invalid_envelope_duration"})
            continue
        accounted += amount
        if kind == "native":
            if record.get("start_at") is None or record.get("end_at") is None or record["end_at"] < record["start_at"]:
                errors.append({"sequence": seq, "reason": "invalid_native_time_span"})
            for rid in active:
                charge(rid, "native_compute_upper_ms", amount, seq)
            continue
        new = record.get("publications", []) + record.get("service_actions", []) + record.get("attempts", [])
        closing = {}
        for item in new:
            rid = item.get("request_id")
            if rid is None:
                continue
            if rid not in requests:
                errors.append({"sequence": seq, "reason": "request_missing_client_call", "request_id": rid})
                continue
            requests[rid]["_started"] = True
            requests[rid]["first_sequence"] = seq
            active.add(rid)
            if item.get("reply", {}).get("status") == "rejected":
                closing[rid] = {"status": "rejected", "delivered_at": record["at"], "source": "submission"}
        for item in record.get("refreshed", []):
            ack = item.get("view", {}).get("last_delivered_ack", {})
            if ack.get("status") in TERMINAL:
                closing[item["request_id"]] = ack
        affected = {rid for rid in active if requests[rid]["owner_id"] == record["owner_id"]}
        for rid in affected:
            charge(rid, "owner_compute_upper_ms", amount, seq)
        if not affected:
            unassociated_owner.append({"trace_sequence": seq, "owner_id": record["owner_id"],
                                       "compute_wall_ms": amount, "at": record["at"]})
        for rid, ack in closing.items():
            if rid not in requests or rid not in active:
                errors.append({"sequence": seq, "reason": "terminal_without_open_request", "request_id": rid})
                continue
            row = requests[rid]
            row["status"] = ack["status"]
            row["ack_processed_at"] = record["at"]
            row["ack_delivered_at"] = ack.get("delivered_at")
            row["end_to_end_logical_seconds"] = record["at"] - row["created_at"]
            row["last_sequence"] = seq
            active.remove(rid)
    residual = wall * 1000 - accounted
    if residual < -1e-6:
        errors.append({"reason": "overlapping_or_inconsistent_wall_envelopes", "residual_ms": residual})
    residual = max(0., residual)
    for rid, row in requests.items():
        if not row.pop("_started"):
            errors.append({"request_id": rid, "reason": "creation_outside_trace"})
        row.pop("_payload")
        row["scheduler_residual_upper_ms"] = residual
        row["compute_upper_ms"] = row["owner_compute_upper_ms"] + row["native_compute_upper_ms"] + residual
        row["compute_upper_scope"] = "observed_prefix" if row["status"] == "unknown_open" else "complete_observed_lifetime"
        row["complete_request_compute_upper_ms"] = (None if row["status"] == "unknown_open" else row["compute_upper_ms"])
        row["upper_envelope_exceeds_100ms"] = row["compute_upper_ms"] > 100.
        row["max_continuous_envelope_ms"] = max(row["max_continuous_envelope_ms"], residual)
        saved = outbox.get(rid)
        if saved and saved.get("terminal") and row["status"] == "unknown_open":
            errors.append({"request_id": rid, "reason": "unobserved_terminal_transition"})
    if errors:
        return unknown("unknown_incomplete_trace", errors)
    return {"schema": "g31.request_compute_envelopes.v1",
        "status": "complete_conservative_accounting" if not errors else "unknown_incomplete_trace",
        "requests": list(requests.values()), "request_count": len(requests),
        "attempt_count": len(calls), "retry_count": sum(r["retries"] for r in requests.values()),
        "terminal_status_counts": dict(Counter(r["status"] for r in requests.values())),
        "open_request_count": len(active), "errors": errors,
        "complete_lifetime_request_count": len(requests) - len(active),
        "controller_wall_ms": wall*1000, "exclusive_envelopes_ms": accounted,
        "shared_scheduler_residual_upper_ms": residual,
        "no_request_owner_activations": unassociated_owner,
        "upper_envelope_over_100ms_count": sum(r["upper_envelope_exceeds_100ms"] for r in requests.values()),
        "max_request_upper_ms": max((r["compute_upper_ms"] for r in requests.values()), default=None),
        "max_complete_request_upper_ms": max((r["complete_request_compute_upper_ms"] for r in requests.values()
            if r["complete_request_compute_upper_ms"] is not None), default=None),
        "complete_100ms_requirement_certified": False,
        "scope": "Full owner and native envelopes; native includes physics, source/receiver validation and commit. "
                 "Whole shared envelopes charged to each request, never averaged. Submit is nested and not added again. "
                 "Logical ACK delay is separate; transport/queue split and native exclusive validation stages remain unknown. "
                 "Upper-envelope exceedance is not proof of isolated request compute exceeding 100ms. "
                 "Single-host diagnostic, not deployment or hard realtime certification."}
