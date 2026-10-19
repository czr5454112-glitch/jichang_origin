"""Pure v3 endpoint binding with distinct client-request and native-message IDs.

This is a new diagnostic/adapter version. It does not mutate historical runners,
mint an online collection token, or change age, coverage, stability or model
predicates. Native protocol_command(owner, request_id) supplies the request
identity; its delivered ACK.result_id binds the generated planning message.
"""
from __future__ import annotations

import copy
import math

from . import preexisting_v3_data_adapter as data_adapter


def unknown(reason, **extra):
    return {"status": "unknown", "reasons": [reason], "native_delivery_verified": False,
            "online_information_delivered": False, "native_protection_certified": False,
            "current_state_certified": False, **extra}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_collected_endpoints(view, command, returned, *, retained, own_actions, phase,
                                 own_request_id, peer_message_id, collection_started_at,
                                 policy_quiet_since, own_request):
    """Validate supplied endpoint data only; all existing downstream guards run."""
    raw = {"view": copy.deepcopy(view), "command": copy.deepcopy(command),
           "received": copy.deepcopy(returned)}
    try:
        now, owner = view["now"], view["owner_id"]
        if (not all(finite(v) for v in (now, collection_started_at, policy_quiet_since))
                or not 0 <= policy_quiet_since <= collection_started_at <= now
                or owner not in {"A", "B"}
                or not isinstance(peer_message_id, str) or not peer_message_id
                or not isinstance(own_request_id, str) or not own_request_id):
            return unknown("missing_explicit_collection_or_quiet_policy_binding", raw_endpoints=raw)
        peer = {"A": "B", "B": "A"}[owner]
        if (own_request.get("request_id") != own_request_id
                or own_request.get("owner_id") != owner
                or own_request.get("target_owner") != peer
                or own_request.get("kind") != "planning_snapshot_v3"):
            return unknown("own_immutable_publication_payload_binding_mismatch", raw_endpoints=raw)
        if (command.get("request_id") != own_request_id
                or command.get("kind") != "planning_snapshot_v3"
                or command.get("status") != "acknowledged"
                or type(command.get("attempt")) is not int or command["attempt"] < 1):
            return unknown("own_command_request_binding_mismatch", raw_endpoints=raw)
        ack = command.get("last_delivered_ack", {})
        own = ack.get("planning_snapshot_v3", {}).get("capture", {}).get("capture_v2", {}).get("local_capture", {})
        if (ack.get("status") != "delivered"
                or not isinstance(ack.get("result_id"), str) or not ack["result_id"]
                or ack["result_id"] != own.get("message_id")
                or own.get("source_owner") != owner or own.get("target_owner") != peer):
            return unknown("own_ack_generated_message_binding_mismatch", raw_endpoints=raw)
        selected = [row for row in returned if row.get("capture", {}).get("capture_v2", {})
                    .get("local_capture", {}).get("message_id") == peer_message_id]
        if len(selected) != 1:
            return unknown("selected_peer_message_missing_or_duplicate", raw_endpoints=raw)
        peer_local = selected[0]["capture"]["capture_v2"]["local_capture"]
        if (not finite(own.get("captured_at")) or not finite(peer_local.get("captured_at"))
                or not collection_started_at <= own["captured_at"] <= now
                or not collection_started_at <= peer_local["captured_at"] <= now):
            return unknown("selected_capture_precedes_collection_or_is_future", raw_endpoints=raw)
        floor = min(own["captured_at"], peer_local["captured_at"])
        quiet = {"schema": "g31.conditional_collection_quiescence.v1",
                 "physical_admissions_quiesced_from": floor, "through": now,
                 "future_python_actions_certified_by_native": False}
        result = data_adapter.validate_later_pair(view, ack, selected, retained=retained,
            own_actions=own_actions, phase=phase, collection_contract=quiet)
        result.update(raw_endpoints=raw, policy_quiet_since=policy_quiet_since,
            collection_started_at=collection_started_at, selected_peer_message_id=peer_message_id,
            endpoint_identity_binding={"own_request_id": own_request_id,
                "native_generated_message_id": own["message_id"],
                "native_ack_result_id": ack["result_id"], "own_command_kind": command["kind"],
                "own_immutable_request": copy.deepcopy(own_request)})
        return result
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as error:
        return unknown("malformed_native_endpoint_replay", raw_endpoints=raw,
                       error=type(error).__name__ + ":" + str(error))
