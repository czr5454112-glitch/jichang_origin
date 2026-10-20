"""Pure diagnostic bounds from declared source-local committed-edge facts.

This module cannot authenticate delivery and never creates a planning policy
input or a protection certificate. A delivered capture authenticates identity,
not a missing entry timestamp. An empty-transfer ACK is intentionally unused.
"""
from __future__ import annotations
import math


def unknown(reason):
    return {"status": "unknown", "reason": reason, "online_information_delivered": False,
        "native_protection_certified": False, "usable_by_stationary_model": False}


def committed_loaded_arrival(local_capture, tray_id, contract, *, now, own_current_view=None):
    """Conditional current-source exact arrival; remote commitment stays unknown.

    A loaded tray at a safe native timestamp boundary reserves edge_to before
    physical entry. Its node remains edge_from until exit. Edge duration is
    deterministic only after actual entry, not commitment. Thus capture+travel
    is NOT an upper bound without an observed entry. Only the publishing
    source's own current receipt-derived exit field can close this diagnostic;
    a peer cannot borrow that field. No source clock is advanced.
    """
    try:
        capture = local_capture["captured_at"]
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (capture, now))
                or not 0 <= capture <= now or now - capture > .05):
            return unknown("invalid_or_stale_source_epoch")
        rows = [t for t in local_capture["trays"] if t["tray_id"] == tray_id]
        if len(rows) != 1: return unknown("missing_or_duplicate_tray")
        tray = rows[0]; source = local_capture["source_owner"]
        owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
        start, target = tray["edge_from"], tray["edge_to"]
        if (tray["mode"] != "loaded" or tray["node"] != start or target < 0
                or owners.get(start) != source or tray["reception_node"] != -1
                or type(tray["generation"]) is not int or type(tray["traversal_id"]) is not int
                or tray["generation"] < 0 or tray["traversal_id"] < 1):
            return unknown("not_identified_source_owned_loaded_commitment")
        jobs = [j for j in local_capture["jobs"] if j["business_bag_id"] == tray["business_bag_id"]]
        if len(jobs) != 1: return unknown("missing_or_duplicate_carried_contract")
        job = jobs[0]; loaded = job["loaded_at"]
        if (job["status"] != "in_transit" or job["storage_node"] != -1
                or type(loaded) not in (int, float) or not math.isfinite(loaded) or not 0 <= loaded <= capture):
            return unknown("unsupported_loaded_leg_or_epoch")
        minimum = contract["native_semantics"]["minimum_service_seconds"]
        if minimum != .001 or local_capture["known_faults"]:
            return unknown("unsupported_minimum_duration_or_known_fault")
        service = {n[0]: max(minimum, n[2]) for n in contract["node_records"]}
        travel = {(u, v): max(minimum, length/speed) for u, v, length, speed in contract["edge_records"]}
        capacities = {(e["from"], e["to"]): e["capacity"] for e in contract["edge_contracts"]}
        if capacities.get((start, target), 0) <= 0: return unknown("unavailable_committed_edge")
        prefix = tray["committed_prefix"]
        if (not prefix or prefix[0] != job["origin"] or prefix[-1] != start or len(prefix) != len(set(prefix))):
            return unknown("unsupported_or_incomplete_committed_prefix")
        # Outward round each addition in physical path order. Grouped sums can
        # overestimate the native sequential double epoch by an ulp; this is a
        # conservative numeric enclosure, never a business-protection epsilon.
        earliest_entry = loaded
        for index, node in enumerate(prefix):
            if index: earliest_entry = math.nextafter(earliest_entry + travel[prefix[index-1], node], -math.inf)
            earliest_entry = math.nextafter(earliest_entry + service[node], -math.inf)
        duration = travel[start, target]
        if earliest_entry > capture:
            return unknown("committed_edge_precedes_public_minimum_journey")
        lower = max(capture, math.nextafter(earliest_entry + duration, -math.inf))
        # A native current source view exposes this field only after observing
        # the matching EDGE_ENTER. Its entry is <=now, not necessarily <=capture.
        upper = math.nextafter(now + duration, math.inf)
        if own_current_view is None:
            return unknown("committed_edge_has_no_observed_entry_bound")
        provenance = "current_own_observation_receipt_derived_edge_exit_at"
        exact = False
        if own_current_view is not None:
            if own_current_view.get("owner_id") != source or own_current_view.get("now") != now:
                return unknown("current_view_is_not_source_owned_at_decision")
            current = [t for t in own_current_view["trays"] if t["tray_id"] == tray_id]
            identity_fields = ("tray_id", "node", "mode", "edge_from", "edge_to", "reception_node",
                "generation", "traversal_id", "business_bag_id", "committed_prefix")
            if len(current) != 1 or any(current[0].get(k) != tray[k] for k in identity_fields):
                return unknown("current_source_traversal_differs_from_capture")
            arrival = current[0].get("edge_exit_at")
            if (type(arrival) not in (int, float) or not math.isfinite(arrival)
                    or not now < arrival or not lower <= arrival <= upper):
                return unknown("missing_or_inconsistent_source_observed_exit")
            lower = upper = arrival; exact = True
            provenance = "current_own_observation_receipt_derived_edge_exit_at"
        return {"status": "conditional_arrival_enclosure", "tray_id": tray_id, "business_bag_id": job["business_bag_id"],
            "source_owner": source, "edge_from": start, "edge_to": target, "generation": tray["generation"],
            "traversal_id": tray["traversal_id"], "captured_at": capture, "now": now,
            "earliest_arrival": lower, "latest_arrival": upper, "exact_for_observing_source": exact,
            "definitely_still_on_captured_edge_at_decision": now < lower,
            "receiving_berth_reserved_at_capture": True, "reservation_identity": "tray_and_committed_traversal_not_transfer_request",
            "provenance": provenance, "online_information_delivered": False, "native_protection_certified": False,
            "rounding": "one nextafter outward per sequential addition; no tolerance on individual job protection",
            "usable_by_stationary_model": False,
            "limits": ["data validator does not authenticate native origin or message delivery",
                "source-local exact field cannot be copied into peer knowledge without delivery",
                "no arrival after this edge or future service ordering inferred",
                "strict action protection over a nonzero interval remains unassessed",
                "complete fixture has no unknown future actions or mid-edge interruption"]}
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return unknown("malformed_or_unsupported_source_edge_data")
