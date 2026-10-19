"""Owner-local native v2 input adapter for the restricted later rolling model.

The pure validator accepts data but never certifies delivery. Native collection
requires a verified extension, an exact NativeSession, and a job-contract ledger
created from this owner's earlier actually delivered initial capture pair.
No result(), checkpoint, fork or other owner's observation is used here.
"""
from __future__ import annotations

import copy
import hashlib
from importlib.machinery import ExtensionFileLoader
import json
import math
from pathlib import Path
from types import ModuleType

from . import native_preexisting_initial_adapter as initial_adapter
from . import public_preexisting_model as model
from .planning_capture_v2_contract import PHYSICAL_KINDS, validate_extension
from .planning_capture_v2_digest import capture_digest_v2


_LEDGER_TOKEN = object()
CONTRACT_FIELDS = ("business_bag_id", "origin", "destination", "arrival", "deadline", "storage_node",
    "storage_release_at", "storage_min_dwell", "load_seconds", "unload_seconds", "hold_seconds",
    "protected_service", "allow_suffix_reroute")


class NativeJobLedger:
    __slots__ = ("_session", "_owner", "_data", "_token")

    def __init__(self, token, session, owner, data):
        if token is not _LEDGER_TOKEN:
            raise ValueError("rolling_adapter:ledger_requires_native_initial_collection")
        self._token, self._session, self._owner = token, session, owner
        self._data = json.dumps(data, sort_keys=True, allow_nan=False)

    def audit_copy(self):
        return json.loads(self._data)


def unknown(reason, **extra):
    return {"status": "unknown", "reasons": [reason], "native_delivery_verified": False,
        "online_information_delivered": False, "native_protection_certified": False, **extra}


def _trusted_native(native, session):
    try:
        identity = native._g31_native_artifact_identity
        path = Path(native.__file__).resolve(strict=True)
        return (isinstance(native, ModuleType) and isinstance(native.__spec__.loader, ExtensionFileLoader)
            and native.__name__ == "czr005_circulation" and type(session) is native.NativeSession
            and type(session).__module__ == "czr005_circulation" and path.suffix.lower() == ".pyd"
            and str(path) == identity["resolved_path"] and hashlib.sha256(path.read_bytes()).hexdigest() == identity["sha256"])
    except (AttributeError, KeyError, TypeError, OSError):
        return False


def collect_initial_ledger(native, session, owner, initial_request_id):
    """Retain source-authored public contracts through the initial native adapter."""
    if not _trusted_native(native, session):
        return unknown("unverified_native_session_or_binary"), None
    initial = initial_adapter.collect_native(native, session, owner, initial_request_id)
    if not initial.get("native_delivery_verified"):
        return unknown("missing_verified_initial_contract_capture", initial=initial), None
    contracts, sources, digest = {}, {}, set()
    for source, envelope in initial["envelopes"].items():
        body = envelope["capture"]
        digest.add(body["static_contract_sha256"])
        for job in body["jobs"]:
            key = job["business_bag_id"]
            if key in contracts:
                return unknown("duplicate_initial_contract"), None
            contracts[key] = {k: job[k] for k in CONTRACT_FIELDS}
            sources[key] = {"source_owner": source, "message_id": body["message_id"],
                "payload_sha256": envelope["payload_sha256"], "captured_at": body["captured_at"],
                "delivered_at": initial["own_delivered_ack"]["delivered_at"] if source == owner else envelope["delivered_at"]}
    if set(contracts) != model.JOBS or len(digest) != 1:
        return unknown("incomplete_initial_contract_population"), None
    data = {"contracts": contracts, "sources": sources, "static_contract_sha256": digest.pop(),
        "owner": owner, "retained_at": session.physical_time,
        "native_binary": copy.deepcopy(native._g31_native_artifact_identity)}
    return initial, NativeJobLedger(_LEDGER_TOKEN, session, owner, data)


def validate_later_pair(view, own_ack, received, *, retained, own_actions, phase):
    """Validate data only; native collection below establishes endpoint origin."""
    try:
        owner, now = view["owner_id"], view["now"]
        peer = {"A": "B", "B": "A"}[owner]
        if (not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now)
                or retained["owner"] != owner or not 0 <= retained["retained_at"] <= now
                or set(retained["contracts"]) != model.JOBS):
            return unknown("missing_retained_public_contract_ledger")
        if own_ack.get("status") != "delivered" or not 0 <= own_ack.get("delivered_at", math.inf) <= now:
            return unknown("missing_delivered_v2_self_copy")
        if len(received) != 1:
            return unknown("missing_duplicate_or_unexpected_v2_peer_capture")
        envelopes = {owner: own_ack["planning_snapshot_v2"], peer: received[0]}
        contract = model.public_contract(view)
        contract["native_semantics"] = copy.deepcopy(model.SUPPORTED_NATIVE_SEMANTICS)
        owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
        jobs = {key: {**copy.deepcopy(row), "status": "unknown", "loaded_at": -1.,
            "storage_entered_at": -1., "storage_released_at": -1.} for key, row in retained["contracts"].items()}
        trays, resources, source_records, terminals, own_local = {}, {}, [], [], None
        seen_jobs = set()
        for source, envelope in envelopes.items():
            body = envelope["capture"]
            if (envelope.get("schema") != "g31.planning_snapshot.v2" or envelope.get("kind") != "planning_snapshot_v2"
                    or envelope.get("digest_format") != "g31.planning_capture_digest.v2"
                    or body.get("schema") != "g31.planning_capture.v2"
                    or capture_digest_v2(body) != envelope["payload_sha256"]):
                return unknown("invalid_v2_schema_or_digest")
            local, extension = body["local_capture"], body["extension"]
            capture, delivery, expiry = local["captured_at"], envelope["delivered_at"], local["valid_until"]
            if (local.get("schema") != "g31.planning_capture.v1" or local["source_owner"] != source
                    or local["target_owner"] != ({"A", "B"} - {source}).pop()
                    or local["static_contract_sha256"] != retained["static_contract_sha256"]
                    or envelope.get("status") != "conditional"
                    or not all(math.isfinite(v) for v in (capture, delivery, expiry))
                    or not 0 <= capture <= delivery <= now < expiry or now - capture > .05):
                return unknown("invalid_v2_channel_contract_or_causal_age")
            available = delivery
            if source == owner:
                if (not (capture == own_ack["executed_at"] <= own_ack["completed_at"] == delivery
                        <= own_ack["delivered_at"] <= now) or own_ack["result_id"] != local["message_id"]):
                    return unknown("v2_self_ack_identity_or_time_mismatch")
                available = own_ack["delivered_at"]
                own_local = local
            checked = validate_extension(extension, source_owner=source, captured_at=capture,
                node_owners=owners, retained_job_contracts=retained["contracts"],
                local_action_ledger=own_actions if source == owner else None)
            if checked["status"] != "conditional_extension_data":
                return unknown("unsupported_v2_extension", extension_check=checked)
            coverage = local["coverage"]
            if (coverage["complete_for_declared_local_scope"] is not True or coverage["future_arrivals_included"] is not False
                    or coverage["unrepresented_occupancy"] != 0 or local["known_faults"]
                    or coverage["local_node_ids"] != [n["node"] for n in local["nodes"]]
                    or coverage["tray_ids"] != [t["tray_id"] for t in local["trays"]]
                    or coverage["business_bag_ids"] != [j["business_bag_id"] for j in local["jobs"]]):
                return unknown("incomplete_v2_local_scope")
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
                "node_ids": coverage["local_node_ids"], "tray_ids": coverage["tray_ids"], "job_ids": coverage["business_bag_ids"]})
        canonical = lambda rows, fields: sorted(({key: row[key] for key in fields} for row in rows), key=lambda row: json.dumps(row, sort_keys=True))
        tray_fields = ("tray_id", "node", "mode", "edge_from", "edge_to", "reception_node", "generation", "traversal_id", "business_bag_id", "committed_prefix")
        if canonical(view["trays"], tray_fields) != canonical(own_local["trays"], tray_fields):
            return unknown("owned_tray_changed_after_v2_capture")
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
            return unknown("owned_job_changed_after_v2_capture")
        own_nodes = [n for n in view["node_contracts"] if n["resource_owner"] == owner]
        if canonical(own_nodes, ("node", "occupancy", "actual_available")) != canonical(own_local["nodes"], ("node", "occupancy", "actual_available")) or view["known_faults"]:
            return unknown("owned_resource_or_fault_changed_after_v2_capture")
        bundle = model.assemble_later(contract, jobs, trays, resources, now=now, phase=phase,
            source_records=source_records, terminal_receipts=terminals, owner_pending_tray_requests=[])
        if bundle["status"] != "conditional_model_input":
            return unknown("unsupported_later_model_state", bundle=bundle)
        return {"status": "conditional_validated_later_data", "bundle": bundle, "native_delivery_verified": False,
            "online_information_delivered": False, "native_protection_certified": False,
            "agreement_certified": False, "envelopes": copy.deepcopy(envelopes), "own_delivered_ack": copy.deepcopy(own_ack),
            "assumptions": ["published three-tray five-job domain and no unannounced exogenous actions",
                "common controller quiesces physical admissions while collecting this pair; native does not certify future Python plans",
                "only this owner's current view is revalidated; peer age remains conditional"]}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        return unknown("malformed_later_capture_pair", error=type(error).__name__ + ":" + str(error))


def selected_received_message(returned, identity, not_before):
    """Select an explicit delivered revision; preserve the endpoint list outside.

    Selection does not authenticate data. Schema, digest, source, expiry and
    delivery causality are checked separately after native endpoint collection.
    """
    selected = [row for row in returned if row.get("capture", {}).get("local_capture", {}).get("message_id") == identity]
    if len(selected) != 1 or selected[0]["capture"]["local_capture"].get("captured_at", -1) < not_before:
        return []
    return selected


def collect_native(native, session, owner, own_request_id, *, ledger, owned_client_rows, phase,
                   peer_message_id=None, collection_started_at=None):
    if not _trusted_native(native, session):
        return unknown("unverified_native_session_or_binary")
    if (type(ledger) is not NativeJobLedger or ledger._token is not _LEDGER_TOKEN
            or ledger._session is not session or ledger._owner != owner):
        return unknown("missing_session_bound_native_contract_ledger")
    retained = ledger.audit_copy()
    if retained["native_binary"] != native._g31_native_artifact_identity:
        return unknown("retained_contract_binary_changed")
    if (not isinstance(peer_message_id, str) or not peer_message_id
            or isinstance(collection_started_at, bool) or not isinstance(collection_started_at, (int, float))
            or not math.isfinite(collection_started_at) or not 0 <= collection_started_at <= session.physical_time):
        return unknown("missing_explicit_collection_message_binding")
    own_actions = sorted((key, row["kind"]) for key, row in owned_client_rows.items()
        if row["request"]["owner_id"] == owner and row["kind"] in PHYSICAL_KINDS)
    view = session.observe_protocol(owner)
    command = session.protocol_command(owner, own_request_id)
    returned = session.protocol_planning_snapshots_v2(owner)
    received = selected_received_message(returned, peer_message_id, collection_started_at)
    if (len(received) != 1
            or command.get("last_delivered_ack", {}).get("planning_snapshot_v2", {}).get("capture", {}).get("local_capture", {}).get("captured_at", -1) < collection_started_at):
        return unknown("selected_message_missing_or_precedes_collection", native_returned_messages=copy.deepcopy(returned))
    result = validate_later_pair(view, command.get("last_delivered_ack", {}), received,
        retained=retained, own_actions=own_actions, phase=phase)
    result["native_read"] = {"owner": owner, "own_request_id": own_request_id, "at": view["now"],
        "native_binary": copy.deepcopy(native._g31_native_artifact_identity), "selected_peer_message_id": peer_message_id,
        "collection_started_at": collection_started_at, "native_returned_messages": copy.deepcopy(returned)}
    if result["status"] == "conditional_validated_later_data":
        result["status"] = "conditional_native_delivered_later_model_input"
        result["native_delivery_verified"] = True
        result["online_information_delivered"] = True
    return result
