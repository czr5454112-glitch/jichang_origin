"""Restricted, conditional public-model adapter for native delivered captures.

A caller-provided dictionary can validate as data but never prove delivery.
Only collect_native reads a verified loaded NativeSession and sets the delivery
provenance flag. The model is still a conditional predictor, not a certificate.
"""
from __future__ import annotations
import copy
import hashlib
from importlib.machinery import ExtensionFileLoader
import json
import math
from pathlib import Path
import struct
from types import ModuleType
from . import public_reuse_model as model

def capture_digest(body):
    """Independent encoding of the documented native typed capture digest."""
    data = bytearray()
    def text(value):
        encoded = value.encode("utf-8")
        data.extend(struct.pack(">Q", len(encoded)))
        data.extend(encoded)
    def integer(value):
        data.extend(struct.pack(">Q", value & ((1 << 64) - 1)))
    def floating(value):
        data.extend(struct.pack(">d", value))
    def boolean(value):
        data.append(1 if value else 0)
    text("czr005.g4irsf14.runtime-state-component.v2")
    text("g31.planning_capture_digest.v1")
    text(body["schema"])
    for key in ("message_id", "source_owner", "target_owner"):
        text(body[key])
    integer(body["publication_sequence"])
    floating(body["captured_at"])
    floating(body["valid_until"])
    text(body["static_contract_sha256"])
    for key in ("queue_discipline", "resource_semantics", "event_semantics", "scorer_mode", "merge_grant_rule", "merge_grant_timing_mode"):
        text(body["semantics"][key])
    floating(body["semantics"]["minimum_service_seconds"])
    integer(len(body["jobs"]))
    for job in body["jobs"]:
        text(job["business_bag_id"])
        integer(job["origin"])
        integer(job["destination"])
        floating(job["arrival"])
        floating(job["deadline"])
        integer(job["storage_node"])
        for key in ("storage_release_at", "storage_min_dwell", "load_seconds", "unload_seconds", "hold_seconds"):
            floating(job[key])
        boolean(job["protected_service"])
        boolean(job["allow_suffix_reroute"])
        text(job["status"])
        for key in ("loaded_at", "storage_entered_at", "storage_released_at"):
            floating(job[key])
    integer(len(body["trays"]))
    for tray in body["trays"]:
        for key in ("tray_id", "business_bag_id", "mode", "ready_kind"):
            text(tray[key])
        for key in ("node", "edge_from", "edge_to", "reception_node", "generation", "traversal_id"):
            integer(tray[key])
        for key in ("available_at", "service_ready_at", "load_complete_at"):
            floating(tray[key])
        boolean(tray["service_ready_known"])
        integer(len(tray["committed_prefix"]))
        for node in tray["committed_prefix"]:
            integer(node)
    integer(len(body["nodes"]))
    for node in body["nodes"]:
        for key in ("node", "occupancy", "actual_available", "unrepresented_occupancy"):
            integer(node[key])
    integer(len(body["known_faults"]))
    for fault in body["known_faults"]:
        integer(fault["from"])
        integer(fault["to"])
        boolean(fault["active"])
        floating(fault["received_at"])
    coverage = body["coverage"]
    text(coverage["scope"])
    boolean(coverage["complete_for_declared_local_scope"])
    integer(len(coverage["local_node_ids"]))
    for node in coverage["local_node_ids"]:
        integer(node)
    for field in ("tray_ids", "business_bag_ids"):
        integer(len(coverage[field]))
        for identity in coverage[field]:
            text(identity)
    integer(coverage["unrepresented_occupancy"])
    boolean(coverage["future_arrivals_included"])
    return hashlib.sha256(data).hexdigest()


def unknown(reason, **extra):
    return {"status": "unknown", "reasons": [reason], "native_delivery_verified": False,
            "native_protection_certified": False, **extra}


def validate_pair(view: dict, own_ack: dict, received: list[dict]) -> dict:
    """Validate an owner-local evidence bundle, without authenticating its origin.

    This is intentionally restricted to the published two-tray/four-obligation
    experiment. Its known population and absence of later arrivals are public
    experiment contracts, not inferred from an empty remote observation.
    """
    try:
        now, owner = view["now"], view["owner_id"]
        peer = {"A": "B", "B": "A"}[owner]
        if now != model.START or not math.isfinite(now):
            return unknown("unsupported_decision_epoch")
        if own_ack.get("status") != "delivered" or not (0 <= own_ack["delivered_at"] <= now):
            return unknown("missing_or_undelivered_self_copy")
        own = own_ack["planning_snapshot"]
        peers = [m for m in received if m["capture"]["source_owner"] == peer]
        if len(peers) != 1 or len(received) != 1:
            return unknown("missing_duplicate_or_unexpected_peer_snapshot")
        envelopes = {owner: own, peer: peers[0]}
        contract = model.public_contract(view)
        node_owner = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
        all_trays, all_jobs, all_nodes = {}, {}, {}
        projected, transitions = {}, []
        digests, capture_times = set(), set()
        for source, envelope in envelopes.items():
            body = envelope["capture"]
            if (envelope["schema"] != "g31.planning_snapshot.v1" or envelope["kind"] != "planning_snapshot"
                    or envelope["digest_format"] != "g31.planning_capture_digest.v1"
                    or body["schema"] != "g31.planning_capture.v1"):
                return unknown("invalid_snapshot_schema")
            if body["source_owner"] != source or body["target_owner"] != ({"A", "B"} - {source}).pop():
                return unknown("capture_channel_mismatch")
            capture, delivery, expiry = body["captured_at"], envelope["delivered_at"], body["valid_until"]
            if not (math.isfinite(capture) and math.isfinite(delivery) and math.isfinite(expiry)
                    and .05 <= capture <= delivery <= now < expiry and now - capture <= .06):
                return unknown("invalid_causal_time_or_unsupported_capture_age")
            if envelope["status"] != "conditional":
                return unknown("latest_snapshot_expired_or_unusable")
            if source == owner and (not (capture == own_ack["executed_at"] <= own_ack["completed_at"]
                    == delivery <= own_ack["delivered_at"] <= now) or own_ack["result_id"] != body["message_id"]):
                return unknown("self_ack_capture_order_or_identity_mismatch")
            if not isinstance(body["publication_sequence"], int) or body["publication_sequence"] <= 0:
                return unknown("invalid_publication_sequence")
            if len(body["static_contract_sha256"]) != 64:
                return unknown("invalid_static_digest")
            if capture_digest(body) != envelope["payload_sha256"]:
                return unknown("capture_digest_mismatch")
            digests.add(body["static_contract_sha256"])
            capture_times.add(capture)
            semantics = body["semantics"]
            if (semantics["queue_discipline"] != "fifo" or semantics["resource_semantics"] != contract["resource_semantics"]
                    or semantics["event_semantics"] != contract["event_semantics"]
                    or semantics["scorer_mode"] != "S4_queue_aware_rule_only"
                    or semantics["merge_grant_rule"] != "M3"
                    or semantics["merge_grant_timing_mode"] != "jit_fair_aging_deadline"
                    or semantics["minimum_service_seconds"] != .001):
                return unknown("unsupported_native_resource_semantics")
            coverage = body["coverage"]
            local_nodes = sorted(n for n, o in node_owner.items() if o == source)
            if (not coverage["complete_for_declared_local_scope"] or coverage["future_arrivals_included"]
                    or coverage["unrepresented_occupancy"] != 0 or coverage["local_node_ids"] != local_nodes
                    or coverage["tray_ids"] != sorted(t["tray_id"] for t in body["trays"])
                    or coverage["business_bag_ids"] != sorted(j["business_bag_id"] for j in body["jobs"])):
                return unknown("missing_or_unrepresented_coverage")
            if sorted(n["node"] for n in body["nodes"]) != local_nodes:
                return unknown("local_resource_coverage_mismatch")
            if body["known_faults"]:
                return unknown("unsupported_known_fault")
            jobs, trays = copy.deepcopy(body["jobs"]), copy.deepcopy(body["trays"])
            for row in jobs:
                if row["business_bag_id"] in all_jobs or node_owner[row["origin"]] != source:
                    return unknown("duplicate_job_or_source_authority")
                if any(row[k] > capture for k in ("arrival", "loaded_at", "storage_entered_at", "storage_released_at")):
                    return unknown("future_observed_job_epoch")
                all_jobs[row["business_bag_id"]] = row
            for tray in trays:
                if tray["tray_id"] in all_trays or node_owner[tray["node"]] != source:
                    return unknown("duplicate_tray_or_source_authority")
                if tray["edge_to"] != -1 or tray["edge_from"] != -1 or tray["reception_node"] != -1:
                    return unknown("unsupported_inflight_or_receiving_state")
                if tray["committed_prefix"] != [tray["node"]]:
                    return unknown("unsupported_committed_history")
                all_trays[tray["tray_id"]] = tray
                if tray["tray_id"] == "L":
                    job = next(j for j in jobs if j["business_bag_id"] == "loaded")
                    if (tray["node"] != 0 or tray["business_bag_id"] != "loaded" or tray["mode"] != "loading"
                            or not tray["service_ready_known"] or tray["ready_kind"] != "observed_load_completion"
                            or not capture < tray["service_ready_at"] == tray["load_complete_at"] <= now
                            or job["loaded_at"] != -1 or job["status"] != "loading"):
                        return unknown("unsupported_loading_projection")
                    finish = tray["load_complete_at"]
                    service = next(n[2] for n in contract["node_records"] if n[0] == 0)
                    if finish + service <= now:
                        return unknown("source_dispatch_may_have_occurred")
                    transitions.append({"source": source, "tray_id": "L", "from_mode": "loading", "to_mode": "loaded",
                        "source_captured_at": capture, "source_known_load_complete_at": finish,
                        "projected_at": now, "first_possible_source_service_end": finish + service,
                        "scope": "conditional native-observed committed load completion; not a fresh remote observation"})
                    tray["mode"], tray["available_at"] = "loaded", 0.
                    job["status"], job["loaded_at"] = "in_transit", finish
                elif tray["tray_id"] == "E":
                    if (tray["node"] != 5 or tray["mode"] != "empty" or tray["business_bag_id"]
                            or not tray["service_ready_known"] or tray["ready_kind"] != "empty_available_at"
                            or tray["available_at"] > capture):
                        return unknown("unsupported_empty_projection")
                else:
                    return unknown("unsupported_tray_population")
            for node in body["nodes"]:
                if node["node"] in all_nodes or node["unrepresented_occupancy"] != 0:
                    return unknown("unrepresented_or_duplicate_resource")
                all_nodes[node["node"]] = node
            projected[source] = {"owner": source, "identity": "projection:" + body["message_id"], "captured_at": now,
                "delivered_at": None, "expires_at": expiry, "provenance": "conditional_aged_native_capture_projection",
                "jobs": jobs, "trays": trays, "resources": [{k: n[k] for k in ("node", "occupancy", "actual_available")} for n in body["nodes"]],
                "coverage": {"jobs": coverage["business_bag_ids"], "trays": coverage["tray_ids"], "resources": local_nodes},
                "known_faults": [], "source_identity": body["message_id"],
                "model_epoch_field_semantics": "legacy model captured_at denotes projected state epoch here, never native capture time",
                "projected_at": now, "source_captured_at": capture, "source_delivered_at": delivery,
                "age_seconds": now - capture}
        if len(digests) != 1 or len(capture_times) != 1:
            return unknown("mismatched_static_contract_or_capture_epoch")
        if set(all_jobs) != {"loaded", "receiver", "reuse1", "reuse2"} or set(all_trays) != {"L", "E"}:
            return unknown("incomplete_declared_population")
        # Check this owner's fresh facts only. No peer observation is read.
        own_projected = projected[owner]
        local_tray_fields = ("tray_id", "node", "mode", "edge_from", "edge_to", "reception_node",
                             "generation", "traversal_id", "business_bag_id", "committed_prefix")
        canonical = lambda rows, fields: sorted([{k: r[k] for k in fields} for r in rows], key=lambda r: json.dumps(r, sort_keys=True))
        if canonical(view["trays"], local_tray_fields) != canonical(own_projected["trays"], local_tray_fields):
            return unknown("local_tray_changed_since_capture")
        job_fields = tuple(own_projected["jobs"][0])
        if canonical(view["jobs"], job_fields) != canonical(own_projected["jobs"], job_fields):
            return unknown("local_obligation_changed_since_capture")
        local_nodes = [n for n in view["node_contracts"] if n["resource_owner"] == owner]
        if canonical(local_nodes, ("node", "occupancy", "actual_available")) != canonical(own_projected["resources"], ("node", "occupancy", "actual_available")):
            return unknown("local_resource_changed_since_capture")
        if view["known_faults"]:
            return unknown("local_fault_changed_since_capture")
        captures = tuple(model.Capture(json.dumps(projected[o], sort_keys=True, separators=(",", ":"), allow_nan=False)) for o in ("A", "B"))
        bundle = model.assemble(contract, captures, now)
        if bundle["status"] != "conditional_model_input":
            return unknown("unsupported_projected_model_input", model_reasons=bundle["reasons"])
        identity = hashlib.sha256(json.dumps([envelopes[o]["capture"] for o in ("A", "B")], sort_keys=True).encode()).hexdigest()
        return {"status": "conditional_validated_data", "native_delivery_verified": False,
            "owner": owner, "peer": peer, "source_capture_pair_sha256": identity, "bundle": bundle,
            "native_protection_certified": False, "conditional_projection": transitions,
            "capture_age_seconds": {o: now - envelopes[o]["capture"]["captured_at"] for o in ("A", "B")},
            "envelopes": copy.deepcopy(envelopes), "own_delivered_ack": copy.deepcopy(own_ack),
            "agreement_certified": False, "assumptions": ["published fixture has exactly two trays and four obligations, all released by .05",
                "no intervening physical commands before .11; initial planning and demand messages only",
                "peer committed load completion is projected conditionally; only own current state revalidated",
                "one owner cannot infer peer readiness or atomic action agreement from snapshots alone"]}
    except (KeyError, TypeError, ValueError, StopIteration, OverflowError, struct.error) as exc:
        return unknown("invalid_snapshot_or_view_shape", error=type(exc).__name__ + ":" + str(exc))


def collect_native(native, session, owner: str, own_request_id: str) -> dict:
    """Read only this owner's live native observations, ACK and recipient inbox.

    The module must have been loaded by native_host.load_native, which verifies
    the local extension artifact. No caller-supplied snapshot is accepted here.
    """
    identity = getattr(native, "_g31_native_artifact_identity", {})
    try:
        path = Path(native.__file__).resolve(strict=True)
        if (not isinstance(native, ModuleType) or not isinstance(native.__spec__.loader, ExtensionFileLoader)
                or native.__name__ != "czr005_circulation" or type(session).__module__ != "czr005_circulation"
                or type(session) is not native.NativeSession or path.suffix.lower() != ".pyd"
                or str(path) != identity["resolved_path"]
                or hashlib.sha256(path.read_bytes()).hexdigest() != identity["sha256"]):
            return unknown("unverified_native_session_or_binary")
    except (AttributeError, KeyError, TypeError, OSError):
        return unknown("unverified_native_session_or_binary")
    view = session.observe_protocol(owner)
    command = session.protocol_command(owner, own_request_id)
    received = session.protocol_planning_snapshots(owner)
    result = validate_pair(view, command.get("last_delivered_ack", {}), received)
    result["native_read"] = {"owner": owner, "own_request_id": own_request_id, "native_binary": copy.deepcopy(identity), "at": view["now"]}
    if result["status"] == "conditional_validated_data":
        result["status"] = "conditional_native_delivered_model_input"
        result["native_delivery_verified"] = True
    return result

