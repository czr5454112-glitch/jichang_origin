"""Offline independent delivery-gate verification from retained native reads.

Summary flags never authenticate evidence. This verifier checks saved input,
calls, raw endpoint captures, immutable digests, causal metadata and each
predeclared negative's exact failure. It performs no native calls or searches.
"""
from __future__ import annotations
import copy
import json
import math
from . import native_preexisting_initial_adapter as adapter
from . import public_preexisting_model as model


EXPECTED_REASONS = {
    None: {"A": [], "B": []},
    "missing_peer": {"A": ["missing_or_undelivered_self_copy"], "B": ["missing_duplicate_or_unexpected_peer_snapshot"]},
    "expired_capture": {"A": ["invalid_causal_time_or_unsupported_capture_age"], "B": ["invalid_causal_time_or_unsupported_capture_age"]},
    "lost_self_ack": {"A": ["missing_or_undelivered_self_copy"], "B": ["missing_or_undelivered_self_copy"]},
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def require(condition, reason):
    if not condition: raise ValueError(reason)


def _local_shape(view, data, owner):
    """Known initial physical population; faults affect publications only."""
    require(view["owner_id"] == owner and view["now"] == .11 and view["known_faults"] == [], "wrong_initial_local_epoch")
    require(canonical(model.public_contract(view)) == canonical(model.public_contract(data)), "changed_public_static_view")
    owners = {n["node"]: n["resource_owner"] for n in data["node_contracts"]}
    expected_jobs = {j["business_bag_id"]: j for j in data["jobs"] if owners[j["origin"]] == owner}
    require(len(view["jobs"]) == len(expected_jobs) and {j["business_bag_id"] for j in view["jobs"]} == set(expected_jobs), "wrong_initial_owned_job_population")
    for job in view["jobs"]:
        key = job["business_bag_id"]; expected = expected_jobs[key]
        require(all(job[field] == expected[field] for field in model.CONTRACT_FIELDS) and job["protected_service"] is True, "changed_initial_job_contract")
        require(job["status"] == ("in_transit" if key == "loaded" else "loading" if key == "blocker" else "waiting_for_tray")
            and job["loaded_at"] == (.1 if key == "loaded" else -1.)
            and job["storage_entered_at"] == job["storage_released_at"] == -1., "wrong_initial_owned_job_state")
    expected_trays = {t["tray_id"]: t["node"] for t in data["trays"] if owners[t["node"]] == owner}
    require(len(view["trays"]) == len(expected_trays) and {t["tray_id"] for t in view["trays"]} == set(expected_trays), "wrong_initial_owned_tray_population")
    for tray in view["trays"]:
        name = tray["tray_id"]
        require(tray["node"] == expected_trays[name] and tray["mode"] == {"L": "loaded", "P": "loading", "E": "empty"}[name]
            and tray["business_bag_id"] == {"L": "loaded", "P": "blocker", "E": ""}[name]
            and tray["edge_from"] == tray["edge_to"] == tray["reception_node"] == -1
            and type(tray["generation"]) is int and type(tray["traversal_id"]) is int
            and tray["generation"] >= 0 and tray["traversal_id"] >= 0, "wrong_initial_owned_tray_state")
    local_nodes = [n for n in view["node_contracts"] if n["resource_owner"] == owner]
    for node in local_nodes:
        require(node["occupancy"] == sum(t["node"] == node["node"] for t in data["trays"])
            and node["actual_available"] == int(node["node"] == 5), "wrong_initial_owned_occupancy")


def _envelope_shape(envelope, source, target, fault, data):
    body = envelope["capture"]
    require(envelope["schema"] == "g31.planning_snapshot.v1" and envelope["kind"] == "planning_snapshot"
        and envelope["digest_format"] == "g31.planning_capture_digest.v1" and body["schema"] == "g31.planning_capture.v1", "wrong_capture_schema")
    require(adapter.capture_digest(body) == envelope["payload_sha256"], "capture_digest_changed")
    require(body["source_owner"] == source and body["target_owner"] == target and body["captured_at"] == .05+.01
        and type(body["publication_sequence"]) is int and body["publication_sequence"] > 0
        and body["message_id"] and len(body["static_contract_sha256"]) == 64
        and body["semantics"] == model.SUPPORTED_NATIVE_SEMANTICS and body["known_faults"] == [], "wrong_source_capture_contract")
    require(body["valid_until"] == (.08 if fault == "expired_capture" else .21)
        and envelope["delivered_at"] == body["captured_at"] + .01, "wrong_source_capture_timing")
    owners = {n["node"]: n["resource_owner"] for n in data["node_contracts"]}
    expected_nodes = sorted(n for n, o in owners.items() if o == source)
    expected_trays = [t for t in data["trays"] if owners[t["node"]] == source]
    expected_jobs = {j["business_bag_id"]: j for j in data["jobs"] if owners[j["origin"]] == source}
    coverage = body["coverage"]
    require(coverage["complete_for_declared_local_scope"] is True and coverage["future_arrivals_included"] is False
        and coverage["unrepresented_occupancy"] == 0 and coverage["local_node_ids"] == expected_nodes
        and adapter.coverage_matches_rows(coverage["tray_ids"], body["trays"], "tray_id")
        and adapter.coverage_matches_rows(coverage["business_bag_ids"], body["jobs"], "business_bag_id")
        and len(body["trays"]) == len(expected_trays) and {t["tray_id"] for t in body["trays"]} == {t["tray_id"] for t in expected_trays}
        and len(body["jobs"]) == len(expected_jobs) and {j["business_bag_id"] for j in body["jobs"]} == set(expected_jobs), "wrong_capture_scope")
    # All surviving components of a negative must be otherwise valid. Validate
    # its source facts as current .11 facts only through the explicitly known
    # .1 L-load transition. This diagnostic does not assert actual delivery.
    local_view = {**copy.deepcopy(data), "owner_id": source, "now": .11, "known_faults": [],
        "jobs": copy.deepcopy(body["jobs"]), "trays": copy.deepcopy(body["trays"])}
    for job in local_view["jobs"]:
        if job["business_bag_id"] == "loaded":
            require(job["status"] == "loading" and job["loaded_at"] == -1., "wrong_captured_load_transition")
            job.update(status="in_transit", loaded_at=.1)
    for tray in local_view["trays"]:
        if tray["tray_id"] == "L":
            require(tray["mode"] == "loading" and tray["service_ready_known"] is True
                and tray["service_ready_at"] == tray["load_complete_at"] == .1, "wrong_captured_L_ready")
            tray["mode"] = "loaded"
        if tray["tray_id"] == "P":
            require(tray["service_ready_known"] is True and tray["service_ready_at"] == tray["load_complete_at"] == expected_jobs["blocker"]["load_seconds"], "wrong_captured_P_ready")
    resources = {n["node"]: n for n in body["nodes"]}
    require(sorted(resources) == expected_nodes and len(resources) == len(body["nodes"])
        and all(n["unrepresented_occupancy"] == 0 for n in body["nodes"]), "wrong_capture_node_scope")
    for node in local_view["node_contracts"]:
        if owners[node["node"]] == source: node.update({field: resources[node["node"]][field] for field in ("occupancy", "actual_available")})
    _local_shape(local_view, data, source)


def verify_branch(raw, specification, expected_input):
    try:
        fault = specification["fault"]
        require(fault in EXPECTED_REASONS and specification["method"] == "delivery_only", "undeclared_fault_or_method")
        require(all(raw["specification"].get(k) == specification[k] for k in ("case", "method", "fault")), "misbound_raw_specification")
        require(canonical(raw["input"]) == canonical(expected_input), "changed_raw_input")
        require(set(raw["initial_owners"]) == {"A", "B"}, "missing_owner_denominator")
        calls = raw["calls"]; require(len(calls) == 4, "unexpected_initial_call_count")
        expected_calls = []
        for owner, peer in (("A", "B"), ("B", "A")):
            expected_calls.extend([{"kind": "demand", "request_id": f"live:1:{owner}:seed-demand", "owner_id": owner,
                "target_owner": peer, "message_delay": .01, "publication_delay": .01},
                {"kind": "planning_snapshot", "request_id": f"live:1:{owner}:initial-planning", "owner_id": owner,
                "target_owner": peer, "message_delay": .01, "publication_delay": .1 if fault == "missing_peer" and owner == "A" else .01,
                "expiry": .08 if fault == "expired_capture" else .21}])
        for call, expected in zip(calls, expected_calls):
            require(call["at"] == .05 and call["retry"] is False and call["kind"] == expected["kind"]
                and call["request"] == expected and call["reply"]["status"].startswith("pending"), "undeclared_or_changed_publication_call")
        owners = {}; component_digests = []
        for owner in ("A", "B"):
            peer = ({"A", "B"} - {owner}).pop(); saved = raw["initial_owners"][owner]; endpoint = saved["raw_endpoints"]
            view, command, received = endpoint["view"], endpoint["command"], endpoint["received"]
            require(saved["owner"] == owner and saved["native_request_id"] is None
                and saved["decision"] == {"status": "delivery_probe_only", "selected_action": None}, "delivery_gate_executed_policy_action")
            _local_shape(view, expected_input, owner)
            require(command["request_id"] == f"live:1:{owner}:initial-planning" and command["kind"] == "planning_snapshot" and command["attempt"] == 1, "wrong_queried_own_command")
            ack = command.get("last_delivered_ack", {})
            need_own = fault != "lost_self_ack" and not (fault == "missing_peer" and owner == "A")
            require(bool(ack) == need_own, "wrong_fault_self_ack_presence")
            if need_own:
                require(ack["status"] == "delivered" and ack["executed_at"] == .05+.01
                    and ack["completed_at"] == (.05+.01)+.01 and ack["delivered_at"] == ((.05+.01)+.01)+.02
                    and ack["result_id"] == ack["planning_snapshot"]["capture"]["message_id"], "wrong_delivered_self_ack")
                _envelope_shape(ack["planning_snapshot"], owner, peer, fault, expected_input)
                component_digests.append(ack["planning_snapshot"]["capture"]["static_contract_sha256"])
            need_peer = not (fault == "missing_peer" and owner == "B")
            require(len(received) == int(need_peer), "wrong_fault_peer_presence")
            for envelope in received:
                _envelope_shape(envelope, peer, owner, fault, expected_input)
                require(envelope["status"] == ("expired" if fault == "expired_capture" else "conditional"), "wrong_received_expiry_status")
                component_digests.append(envelope["capture"]["static_contract_sha256"])
            result = adapter.validate_pair(view, ack, received)
            reasons = result.get("reasons", [])
            require(reasons == EXPECTED_REASONS[fault][owner], "wrong_fault_rejection_reason:" + owner)
            verified = result["status"] == "conditional_validated_data"
            require(verified == (fault is None), "wrong_fault_readiness")
            original = saved["information"].get("initial", saved["information"])
            normalized = copy.deepcopy(original); normalized.pop("native_read", None)
            if normalized.get("status") == "conditional_native_delivered_model_input":
                normalized["status"] = "conditional_validated_data"; normalized["native_delivery_verified"] = False
            require(canonical(normalized) == canonical(result), "saved_information_differs_from_raw_revalidation")
            require(saved["information"].get("native_delivery_verified") is verified, "saved_owner_verified_flag_changed")
            owners[owner] = {"verified": verified, "reasons": reasons}
        require(len(set(component_digests)) == 1, "cross_owner_static_digest_mismatch")
        summary = {"status": "readiness_observed", "both_inputs_verified": all(x["verified"] for x in owners.values()),
            "owner_status": {owner: raw["initial_owners"][owner]["information"]["status"] for owner in owners},
            "business_metrics": None, "physical_protection": "not_assessed"}
        require(raw["summary"] == summary, "saved_summary_differs_from_raw_revalidation")
        return {"status": "passed", "fault": fault, "owners": owners, "recomputed_summary": summary}
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as error:
        return {"status": "unknown_or_failed", "reason": str(error), "business_admitted": False}
