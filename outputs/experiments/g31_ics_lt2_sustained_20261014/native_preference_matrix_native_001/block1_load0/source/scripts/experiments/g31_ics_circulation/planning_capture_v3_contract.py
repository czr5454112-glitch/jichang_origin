"""Proposed source-observed entry facts; supplied data never proves delivery.

No native API or policy uses this module yet. V1/V2 remain byte-for-byte
unchanged. A committed destination without an observed entry stays unknown.
Equal capture timestamps do not establish a common atomic event-order cut.
"""
from __future__ import annotations
import copy
import hashlib
import math
import struct
from .planning_capture_v2_digest import capture_digest_v2

SCHEMA = "g31.planning_capture.v3"
EXTENSION = "g31.planning_inflight_receipts.v1"
SCOPE = "all_current_source_owned_committed_edges_with_matching_observed_entries"
ROW_FIELDS = {"source_owner", "receipt_event", "tray_id", "business_bag_id", "generation",
    "traversal_id", "edge_from", "edge_to", "entered_at", "static_edge_travel_seconds", "derived_edge_exit_at"}
COVERAGE_FIELDS = {"scope", "source_owned_inflight_tray_ids", "capture_cutoff",
    "complete_for_declared_source_inflight", "unmatched_tray_ids", "uses_future_event_heap"}


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def capture_digest_v3(body):
    """Domain-separated typed digest binding the unchanged complete v2 digest.

The nested hash is computed from capture_v2, never accepted from the caller.
This is a proposed v3 wire format; no native compatibility is claimed yet.
"""
    data = bytearray()
    def text(value):
        encoded = value.encode("utf-8")
        data.extend(struct.pack(">Q", len(encoded))); data.extend(encoded)
    def integer(value): data.extend(struct.pack(">Q", value & ((1 << 64) - 1)))
    def floating(value): data.extend(struct.pack(">d", value))
    def boolean(value): data.append(1 if value else 0)
    text("czr005.g4irsf14.runtime-state-component.v2")
    text("g31.planning_capture_digest.v3"); text(body["schema"])
    text("nested_unchanged_v2_typed_digest"); text(capture_digest_v2(body["capture_v2"]))
    extension = body["extension"]
    text(extension["schema"]); text(extension["source_owner"]); floating(extension["captured_at"])
    integer(len(extension["source_observed_inflight"]))
    for row in extension["source_observed_inflight"]:
        for key in ("source_owner", "receipt_event", "tray_id", "business_bag_id"): text(row[key])
        for key in ("generation", "traversal_id", "edge_from", "edge_to"): integer(row[key])
        for key in ("entered_at", "static_edge_travel_seconds", "derived_edge_exit_at"): floating(row[key])
    coverage = extension["coverage"]
    text(coverage["scope"]); floating(coverage["capture_cutoff"])
    boolean(coverage["complete_for_declared_source_inflight"]); boolean(coverage["uses_future_event_heap"])
    for key in ("source_owned_inflight_tray_ids", "unmatched_tray_ids"):
        integer(len(coverage[key]))
        for identity in coverage[key]: text(identity)
    return hashlib.sha256(data).hexdigest()


def uncertified():
    """Fresh flags: supplied-data consistency cannot authenticate these facts."""
    return {"native_delivery_verified": False, "native_protection_certified": False,
        "v2_base_independently_validated": False, "current_state_certified": False,
        "atomic_capture_cut_verified": False, "simultaneous_state_certified": False,
        "intervening_events_excluded": False}


def unknown(reason):
    return {"status": "unknown", "reason": reason, **uncertified()}


def static_nodes(contract):
    """Validate fixed native node contracts without coercing bools or floats."""
    nodes = contract["node_contracts"]
    if type(nodes) is not list or not nodes:
        raise ValueError("invalid_static_node_contract")
    result = {}
    for row in nodes:
        if (type(row) is not dict or type(row["node"]) is not int or row["node"] < 0
                or type(row["resource_owner"]) is not str or not row["resource_owner"]
                or type(row["capacity"]) is not int or row["capacity"] <= 0
                or row["node"] in result):
            raise ValueError("invalid_static_node_contract")
        result[row["node"]] = row
    return result


def validate_inflight(body, contract, *, now, delivered_at, maximum_age=.05):
    """Validate the proposed extension only, not native provenance or v2 facts.

Only already-entered edges whose deterministic exit is strictly after now are
supported. No post-arrival projection, future commitment, FIFO or safety claim
is inferred. Public edge duration uses the existing native minimum duration.
"""
    try:
        if set(body) != {"schema", "capture_v2", "extension"} or body["schema"] != SCHEMA:
            return unknown("unsupported_capture_schema")
        base, extension = body["capture_v2"], body["extension"]
        if base["schema"] != "g31.planning_capture.v2" or base["local_capture"]["schema"] != "g31.planning_capture.v1":
            return unknown("unsupported_nested_capture")
        local = base["local_capture"]; source, captured = local["source_owner"], local["captured_at"]
        if (any(not number(v) for v in (now, delivered_at, maximum_age, captured, local["valid_until"]))
                or maximum_age < 0 or not 0 <= captured <= delivered_at <= now < local["valid_until"]
                or now - captured > maximum_age):
            return unknown("stale_or_invalid_delivery_epoch")
        if (set(extension) != {"schema", "source_owner", "captured_at", "source_observed_inflight", "coverage"}
                or extension["schema"] != EXTENSION or extension["source_owner"] != source
                or extension["captured_at"] != captured):
            return unknown("extension_source_or_cut_mismatch")
        nodes = static_nodes(contract)
        owners = {node: row["resource_owner"] for node, row in nodes.items()}
        trays = local["trays"]
        if len({t["tray_id"] for t in trays}) != len(trays): return unknown("duplicate_local_tray")
        if any(owners.get(t["node"]) != source for t in trays): return unknown("foreign_local_tray")
        moving = {t["tray_id"]: t for t in trays if t["edge_to"] >= 0}
        coverage = extension["coverage"]
        if (set(coverage) != COVERAGE_FIELDS or coverage["scope"] != SCOPE
                or coverage["capture_cutoff"] != captured or coverage["uses_future_event_heap"] is not False
                or coverage["source_owned_inflight_tray_ids"] != [t["tray_id"] for t in trays if t["edge_to"] >= 0]):
            return unknown("inflight_coverage_mismatch")
        if coverage["complete_for_declared_source_inflight"] is not True or coverage["unmatched_tray_ids"]:
            return unknown("unobserved_or_unmatched_committed_entry")
        minimum = contract["native_semantics"]["minimum_service_seconds"]
        if not number(minimum) or minimum <= 0: return unknown("invalid_minimum_duration")
        edges = {}
        for u, v, length, speed in contract["edge_records"]:
            if (u, v) in edges or not number(length) or not number(speed) or length <= 0 or speed <= 0:
                return unknown("invalid_static_edge")
            edges[u, v] = max(minimum, length / speed)
        capacities = {}
        for edge in contract["edge_contracts"]:
            if (any(type(edge[key]) is not int or edge[key] < 0 for key in ("from", "to", "capacity"))
                    or edge["from"] not in owners or edge["to"] not in owners):
                return unknown("invalid_static_edge_contract")
            capacities[edge["from"], edge["to"]] = edge["capacity"]
        if len(capacities) != len(contract["edge_contracts"]): return unknown("duplicate_static_edge_contract")
        rows = extension["source_observed_inflight"]
        if [r["tray_id"] for r in rows] != list(moving): return unknown("entry_membership_or_order_mismatch")
        for row in rows:
            tray = moving[row["tray_id"]]
            if (set(row) != ROW_FIELDS or row["source_owner"] != source or row["receipt_event"] != "EDGE_ENTER"
                    or any(row[k] != tray[k] for k in ("tray_id", "business_bag_id", "generation", "traversal_id", "edge_from", "edge_to"))
                    or tray["node"] != row["edge_from"] or owners.get(row["edge_from"]) != source
                    or any(type(row[k]) is not int or row[k] < 0 for k in ("generation", "traversal_id", "edge_from", "edge_to"))
                    or row["traversal_id"] == 0):
                return unknown("entry_identity_or_source_mismatch")
            edge = row["edge_from"], row["edge_to"]
            if edge not in edges or capacities.get(edge, 0) <= 0: return unknown("unsupported_committed_edge")
            if (any(not number(row[k]) for k in ("entered_at", "static_edge_travel_seconds", "derived_edge_exit_at"))
                    or not 0 <= row["entered_at"] <= captured
                    or row["static_edge_travel_seconds"] != edges[edge]
                    or row["derived_edge_exit_at"] != row["entered_at"] + edges[edge]
                    or not now < row["derived_edge_exit_at"]):
                return unknown("entry_time_or_public_exit_derivation_mismatch")
        return {"status": "conditional_inflight_extension_data", "source_owner": source, "captured_at": captured,
            "entries": copy.deepcopy(rows), **uncertified(),
            "scope": "Supplied extension consistency only; independently validate v2, native origin and actual delivery before policy use."}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return unknown("malformed_inflight_capture")


def reconcile_capture_occupancy(bodies, contract, *, now, delivered_at_by_source, maximum_age=.05):
    """Check supplied occupancy at equal physical timestamps, never a joint cut.

Requires complete declared owner coverage. Cross-owner reserved receiving
berths are represented by a source-owned entered tray. The same carrier counts
once at a node even if edge_to and reception_node coincide (native OR rule).
Separate source captures can occur at different positions in a native
timestamp. Matching identities/counts cannot exclude intervening events or
prove that all supplied states ever coexisted. No barrier or global event
sequence is inferred; even native provenance alone would not establish that
additional cross-source invariant.
"""
    try:
        static = static_nodes(contract)
        owners = {node: row["resource_owner"] for node, row in static.items()}
        locals_ = [b["capture_v2"]["local_capture"] for b in bodies]
        sources = [b["source_owner"] for b in locals_]
        if len(set(sources)) != len(sources) or set(sources) != set(owners.values()):
            return unknown("incomplete_or_duplicate_owner_capture")
        if len({b["captured_at"] for b in locals_}) != 1:
            return unknown("different_capture_timestamps")
        if len({b["static_contract_sha256"] for b in locals_}) != 1:
            return unknown("mismatched_static_capture_identity")
        for body, local in zip(bodies, locals_, strict=True):
            checked = validate_inflight(body, contract, now=now,
                delivered_at=delivered_at_by_source[local["source_owner"]], maximum_age=maximum_age)
            if checked["status"] != "conditional_inflight_extension_data": return checked
        all_trays, nodes = {}, {}
        for local in locals_:
            for tray in local["trays"]:
                if tray["tray_id"] in all_trays: return unknown("duplicate_or_conflicting_carrier_identity")
                all_trays[tray["tray_id"]] = tray
            declared = [r["node"] for r in local["nodes"]]
            if declared != sorted(n for n, o in owners.items() if o == local["source_owner"]):
                return unknown("incomplete_owned_node_coverage")
            for row in local["nodes"]:
                if row["node"] in nodes: return unknown("duplicate_node_observation")
                nodes[row["node"]] = row
        reservations = {node: [] for node in owners}
        for tray in all_trays.values():
            occupied = {tray["edge_to"] if tray["edge_to"] >= 0 else tray["node"]}
            if tray["reception_node"] >= 0: occupied.add(tray["reception_node"])
            for node in occupied:
                if node not in reservations: return unknown("undeclared_reserved_node")
                reservations[node].append([tray["tray_id"], tray["generation"], tray["traversal_id"]])
        for node, row in nodes.items():
            represented_here = sum((t["edge_to"] < 0 and t["node"] == node) or t["edge_to"] == node or
                t["reception_node"] == node for t in all_trays.values() if owners[t["node"]] == owners[node])
            if (type(row["occupancy"]) is not int or type(row["unrepresented_occupancy"]) is not int
                    or row["occupancy"] != len(reservations[node])
                    or row["unrepresented_occupancy"] != row["occupancy"] - represented_here
                    or not 0 <= row["occupancy"] <= static[node]["capacity"]):
                return unknown("captured_occupancy_or_reservation_mismatch")
        return {"status": "conditional_same_timestamp_occupancy_consistency", "captured_at": locals_[0]["captured_at"],
            "supplied_capture_timestamps_equal": True, "reservations_by_node": reservations, **uncertified(),
            "scope": "Supplied owner populations and occupancy counts are consistent at equal physical timestamps only. Separate captures may straddle intervening native events; no atomic or simultaneous state, current occupancy, future capacity or execution grant is certified."}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        return unknown("malformed_capture_occupancy")
