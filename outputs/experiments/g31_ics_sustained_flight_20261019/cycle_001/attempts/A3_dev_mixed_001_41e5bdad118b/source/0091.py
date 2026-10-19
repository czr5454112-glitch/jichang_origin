"""Proposed v3 later supplied-data adapter; no native collection or trust token.

Keeps actual asynchronous capture epochs. The source facts enter the model only
under its explicit conditional stability domain. No caller dictionary can set
native_delivery_verified=True; a future accepted native adapter is separate.
"""
import copy
import json
import math
from . import public_preexisting_model as model
from . import public_preexisting_v3_model as projection
from .native_preexisting_rolling_adapter import CONTRACT_FIELDS
from .planning_capture_v2_contract import validate_extension
from .planning_capture_v3_contract import capture_digest_v3, validate_inflight


def unknown(reason, **extra):
    return {"status":"unknown", "reasons":[reason], "native_delivery_verified":False,
        "native_protection_certified":False, "online_information_delivered":False, **extra}


def validate_later_pair(view, own_ack, received, *, retained, own_actions, phase, collection_contract):
    """Validate supplied data only; no native collector or trust mint exists here."""
    try:
        owner, now = view["owner_id"], view["now"]
        peer = {"A": "B", "B": "A"}[owner]
        if (not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now)
                or retained["owner"] != owner or not 0 <= retained["retained_at"] <= now
                or set(retained["contracts"]) != model.JOBS):
            return unknown("missing_retained_public_contract_ledger")
        if own_ack.get("status") != "delivered" or not 0 <= own_ack.get("delivered_at", math.inf) <= now:
            return unknown("missing_delivered_v3_self_copy")
        if len(received) != 1:
            return unknown("missing_duplicate_or_unexpected_v3_peer_capture")
        envelopes = {owner: own_ack["planning_snapshot_v3"], peer: received[0]}
        contract = model.public_contract(view)
        contract["native_semantics"] = copy.deepcopy(model.SUPPORTED_NATIVE_SEMANTICS)
        owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
        jobs = {key: {**copy.deepcopy(row), "status": "unknown", "loaded_at": -1.,
            "storage_entered_at": -1., "storage_released_at": -1.} for key, row in retained["contracts"].items()}
        trays, resources, source_records, terminals, own_local = {}, {}, [], [], None
        entries = []
        seen_jobs = set()
        for source, envelope in envelopes.items():
            body = envelope["capture"]
            if (envelope.get("schema") != "g31.planning_snapshot.v3" or envelope.get("kind") != "planning_snapshot_v3"
                    or envelope.get("digest_format") != "g31.planning_capture_digest.v3"
                    or body.get("schema") != "g31.planning_capture.v3"
                    or capture_digest_v3(body) != envelope["payload_sha256"]):
                return unknown("invalid_v3_schema_or_digest")
            local, extension = body["capture_v2"]["local_capture"], body["capture_v2"]["extension"]
            capture, delivery, expiry = local["captured_at"], envelope["delivered_at"], local["valid_until"]
            if (local.get("schema") != "g31.planning_capture.v1" or local["source_owner"] != source
                    or local["target_owner"] != ({"A", "B"} - {source}).pop()
                    or not isinstance(local["message_id"], str) or not local["message_id"]
                    or type(local["publication_sequence"]) is not int or local["publication_sequence"] <= 0
                    or local["static_contract_sha256"] != retained["static_contract_sha256"]
                    or envelope.get("status") != "conditional"
                    or not all(math.isfinite(v) for v in (capture, delivery, expiry))
                    or not 0 <= capture <= delivery <= now < expiry or now - capture > .05):
                return unknown("invalid_v3_channel_contract_or_causal_age")
            inflight = validate_inflight(body, contract, now=now, delivered_at=delivery)
            if inflight["status"] != "conditional_inflight_extension_data":
                return unknown("invalid_v3_observed_entry_extension", extension_check=inflight)
            entries.extend(copy.deepcopy(inflight["entries"]))
            available = delivery
            if source == owner:
                if (not (capture == own_ack["executed_at"] <= own_ack["completed_at"] == delivery
                        <= own_ack["delivered_at"] <= now) or own_ack["result_id"] != local["message_id"]):
                    return unknown("v3_self_ack_identity_or_time_mismatch")
                available = own_ack["delivered_at"]
                own_local = local
            checked = validate_extension(extension, source_owner=source, captured_at=capture,
                node_owners=owners, retained_job_contracts=retained["contracts"],
                local_action_ledger=own_actions if source == owner else None)
            if checked["status"] != "conditional_extension_data":
                return unknown("unsupported_v3_extension", extension_check=checked)
            coverage = local["coverage"]
            if (coverage["scope"] != "source_waiting_or_locally_carried_released_jobs_and_local_trays"
                    or coverage["complete_for_declared_local_scope"] is not True or coverage["future_arrivals_included"] is not False
                    or type(coverage["unrepresented_occupancy"]) is not int or coverage["unrepresented_occupancy"] < 0 or local["known_faults"]
                    or coverage["local_node_ids"] != [n["node"] for n in local["nodes"]]
                    or coverage["tray_ids"] != [t["tray_id"] for t in local["trays"]]
                    or coverage["business_bag_ids"] != [j["business_bag_id"] for j in local["jobs"]]):
                return unknown("incomplete_v3_local_scope")
            for row in local["jobs"]:
                key = row["business_bag_id"]
                if key in seen_jobs or key not in jobs or {k: row[k] for k in CONTRACT_FIELDS} != retained["contracts"][key]:
                    return unknown("changed_duplicate_or_unknown_job_contract")
                seen_jobs.add(key); jobs[key] = copy.deepcopy(row)
            for row in local["trays"]:
                key = row["tray_id"]
                if key in trays or owners.get(row["node"]) != source:
                    return unknown("duplicate_or_foreign_tray_capture")
                trays[key] = copy.deepcopy(row)
            for row in local["nodes"]:
                key = row["node"]
                if key in resources or owners.get(key) != source:
                    return unknown("duplicate_or_foreign_node_capture")
                resources[key] = copy.deepcopy(row)
            for key, row in checked["completed_receipts"].items():
                if jobs[key]["status"] not in ("unknown", "completed"):
                    return unknown("completion_conflicts_with_observed_lifecycle")
                jobs[key]["status"] = "completed"
                terminals.append({"business_bag_id": key, "status": "completed", "source_owner": source,
                    "completed_at": row["completed_at"], "captured_at": capture, "delivered_at": available,
                    "identity": row["receipt_id"], "capture_message_id": local["message_id"]})
            source_records.append({"owner": source, "identity": local["message_id"], "captured_at": capture,
                "delivered_at": available, "valid_until": expiry, "known_faults": copy.deepcopy(local["known_faults"]),
                "unrepresented_occupancy": coverage["unrepresented_occupancy"],
                "unresolved_tray_request_ids": checked["unresolved_request_ids"], "semantics": copy.deepcopy(local["semantics"]),
                "submitted_physical_request_ids": copy.deepcopy(extension["action_coverage"]["submitted_request_ids"]),
                "submitted_physical_actions": copy.deepcopy(extension["submitted_physical_actions"]),
                "node_ids": coverage["local_node_ids"], "tray_ids": coverage["tray_ids"], "job_ids": coverage["business_bag_ids"]})
        canonical = lambda rows, fields: sorted(({key: row[key] for key in fields} for row in rows), key=lambda row: json.dumps(row, sort_keys=True))
        tray_fields = ("tray_id", "node", "mode", "edge_from", "edge_to", "reception_node", "generation", "traversal_id", "business_bag_id", "committed_prefix", "available_at")
        if canonical(view["trays"], tray_fields) != canonical(own_local["trays"], tray_fields):
            return unknown("owned_tray_changed_after_v3_capture")
        current_trays = {t["tray_id"]: t for t in view["trays"]}
        for entry in entries:
            if entry["source_owner"] != owner: continue
            current = current_trays.get(entry["tray_id"], {})
            actual_exit = current.get("edge_exit_at")
            if (type(actual_exit) not in (int, float) or not math.isfinite(actual_exit)
                    or actual_exit != entry["derived_edge_exit_at"] or not now < actual_exit):
                return unknown("owned_observed_entry_changed_after_v3_capture")
        job_fields = (*CONTRACT_FIELDS, "status", "loaded_at", "storage_entered_at", "storage_released_at")
        # Full owner observations retain source jobs after their trays leave.
        # The capture's explicit scope is waiting or locally carried jobs. Use
        # that exact scope for freshness, then require an actual receipt for
        # every completed job excluded from this owner's active capture.
        carried = {t["business_bag_id"] for t in view["trays"] if t["business_bag_id"]}
        if any(j["business_bag_id"] not in retained["contracts"] or
            {k: j[k] for k in CONTRACT_FIELDS} != retained["contracts"][j["business_bag_id"]] for j in view["jobs"]):
            return unknown("owned_observation_contract_differs_from_retained_ledger")
        scoped_jobs = [j for j in view["jobs"] if j["status"] != "unreleased" and
            (j["business_bag_id"] in carried or j["status"] == "waiting_for_tray" and owners.get(j["origin"]) == owner)]
        completed_ids = {r["business_bag_id"] for r in terminals}
        if any(j["status"] == "completed" and j["business_bag_id"] not in completed_ids for j in view["jobs"]):
            return unknown("owned_completed_job_without_delivered_terminal_receipt")
        if canonical(scoped_jobs, job_fields) != canonical(own_local["jobs"], job_fields):
            return unknown("owned_job_changed_after_v3_capture")
        own_nodes = [n for n in view["node_contracts"] if n["resource_owner"] == owner]
        if canonical(own_nodes, ("node", "occupancy", "actual_available")) != canonical(own_local["nodes"], ("node", "occupancy", "actual_available")) or view["known_faults"]:
            return unknown("owned_resource_or_fault_changed_after_v3_capture")
        bundle = projection.assemble_later(contract, jobs, trays, resources, now=now, phase=phase,
            source_records=source_records, terminal_receipts=terminals, owner_pending_tray_requests=[], entry_receipts=entries, collection_contract=collection_contract)
        if bundle["status"] != "conditional_model_input":
            return unknown("unsupported_later_model_state", bundle=bundle)
        return {"status": "conditional_validated_later_v3_data", "bundle": bundle, "native_delivery_verified": False,
            "online_information_delivered": False, "native_protection_certified": False,
            "agreement_certified": False, "envelopes": copy.deepcopy(envelopes), "own_delivered_ack": copy.deepcopy(own_ack),
            "assumptions": ["published three-tray five-job domain and no unannounced exogenous actions",
                "common controller quiesces physical admissions while collecting this pair; native does not certify future Python plans",
                "only this owner's current view is revalidated; peer age remains conditional"]}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        return unknown("malformed_later_capture_pair", error=type(error).__name__ + ":" + str(error))

