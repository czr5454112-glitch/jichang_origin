"""Request-bound run-scoped actual owner-local native027 collector for the v3 projection.

The acceptance handle is created only from an active closed run admission;
all owner/session/message checks remain unchanged. The saved-raw runtime gate
and exact extension/session checks. Supplied-data validation remains separate.
No other owner's observation, result, checkpoint, or native fork is read.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
from . import native027_request_timing as acceptance
from . import native027_run_acceptance as run_admission
from . import native_preexisting_rolling_adapter as previous
from .preexisting_v3_endpoint_identity import validate_collected_endpoints
from .planning_capture_v2_contract import PHYSICAL_KINDS

_ACCEPTANCE_TOKEN = object()
_COLLECTION_TOKEN = object()


def unknown(reason, **extra):
    return {"status": "unknown", "reasons": [reason], "native_delivery_verified": False,
        "online_information_delivered": False, "native_protection_certified": False,
        "current_state_certified": False, **extra}


class Native027Acceptance:
    __slots__ = ("_token", "_native", "_session", "_reference", "_identity", "_audit", "_run_acceptance", "_branch_key")

    def __init__(self, token, native, session, reference, verified, accepted_run, branch_key):
        if token is not _ACCEPTANCE_TOKEN:
            raise ValueError("v3_adapter:acceptance_requires_closed_native_runtime_gate")
        self._token, self._native, self._session = token, native, session
        self._run_acceptance, self._branch_key = accepted_run, branch_key
        self._reference = json.dumps(reference, sort_keys=True, allow_nan=False)
        self._identity = json.dumps(native._g31_native_artifact_identity, sort_keys=True)
        self._audit = json.dumps({"contract_reference": reference,
            "runtime_acceptance": verified["contract"]["runtime_acceptance"],
            "binary_sha256": verified["contract"]["binary_sha256"],
            "runtime_accepted": True}, sort_keys=True)

    def audit_copy(self):
        return json.loads(self._audit)


class NativeCollectedV3(dict):
    """Serializable raw result with a process-local, session-bound origin seal."""
    def __init__(self, token, result, accepted):
        if token is not _COLLECTION_TOKEN:
            raise ValueError("v3_adapter:collection_requires_actual_native_reads")
        super().__init__(result)
        self._token, self._accepted = token, accepted
        self._at = result["native_read"]["at"]
        self._encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)


def is_native_collected(value):
    """Saved JSON/caller truth flags cannot become online decision authority."""
    try:
        return (type(value) is NativeCollectedV3 and value._token is _COLLECTION_TOKEN
            and _valid_handle(value._accepted._native, value._accepted._session, value._accepted)
            and value._accepted._session.physical_time == value._at
            and json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) == value._encoded)
    except (TypeError, ValueError, AttributeError):
        return False


def bind_native027(native, session, contract_reference, *, accepted_run, branch_key):
    """No build-only receipt or caller Boolean can create an accepted handle."""
    if not previous._trusted_native(native, session):
        return unknown("unverified_native_session_or_binary"), None
    try:
        if type(accepted_run) is not run_admission.RunAcceptance or not accepted_run.active_for(branch_key):
            return unknown("missing_active_run_acceptance"), None
        verified = accepted_run.contract_copy(branch_key)
        if verified["reference"] != contract_reference:
            return unknown("wrong_run_contract_reference"), None
        identity = native._g31_native_artifact_identity
        if (Path(verified["contract"]["binary"]).resolve() != Path(identity["resolved_path"])
                or verified["contract"]["binary_sha256"] != identity["sha256"]
                or not callable(getattr(session, "protocol_planning_snapshots_v3", None))):
            return unknown("accepted_artifact_does_not_match_loaded_v3_session"), None
        handle = Native027Acceptance(_ACCEPTANCE_TOKEN, native, session, contract_reference, verified, accepted_run, branch_key)
        return {"status": "accepted_native027_session", "acceptance": handle.audit_copy(),
            "native_delivery_verified": False}, handle
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        return unknown("native027_runtime_acceptance_missing_or_invalid", error=str(error)), None


def _valid_handle(native, session, handle):
    try:
        if (type(handle) is not Native027Acceptance or handle._token is not _ACCEPTANCE_TOKEN
                or handle._native is not native or handle._session is not session
                or type(handle._run_acceptance) is not run_admission.RunAcceptance
                or not handle._run_acceptance.active_for(handle._branch_key)
                or not previous._trusted_native(native, session)
                or json.loads(handle._identity) != native._g31_native_artifact_identity):
            return False
        reference = json.loads(handle._reference)
        return hashlib.sha256(Path(reference["path"]).read_bytes()).hexdigest() == reference["sha256"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def collect_initial_ledger(native, session, owner, initial_request_id, *, accepted):
    if not _valid_handle(native, session, accepted):
        return unknown("missing_session_bound_native027_acceptance"), None
    return previous.collect_initial_ledger(native, session, owner, initial_request_id)


def selected_received_message(returned, identity, not_before):
    """Exact delivered revision selection; keeps all endpoint data in raw output."""
    try:
        selected = [row for row in returned if row.get("capture", {}).get("capture_v2", {})
            .get("local_capture", {}).get("message_id") == identity]
        if len(selected) != 1 or selected[0]["capture"]["capture_v2"]["local_capture"]["captured_at"] < not_before:
            return []
        return selected
    except (KeyError, TypeError, ValueError, AttributeError):
        return []



def collect_native(native, session, owner, own_request_id, *, accepted, ledger,
                   owned_client_rows, phase, peer_message_id, collection_started_at,
                   policy_quiet_since):
    if not _valid_handle(native, session, accepted):
        return unknown("missing_session_bound_native027_acceptance")
    if (type(ledger) is not previous.NativeJobLedger or ledger._token is not previous._LEDGER_TOKEN
            or ledger._session is not session or ledger._owner != owner):
        return unknown("missing_session_bound_native_contract_ledger")
    if (own_request_id not in owned_client_rows or owned_client_rows[own_request_id].get("kind") != "planning_snapshot_v3"):
        return unknown("missing_own_immutable_publication")
    retained = ledger.audit_copy()
    if retained["native_binary"] != native._g31_native_artifact_identity:
        return unknown("retained_contract_binary_changed")
    if any(row.get("request", {}).get("owner_id") != owner for row in owned_client_rows.values()):
        return unknown("foreign_client_rows_in_owned_action_ledger")
    own_actions = sorted((key, row["kind"]) for key, row in owned_client_rows.items() if row["kind"] in PHYSICAL_KINDS)
    # Exactly these three owner-scoped reads establish endpoint origin. No
    # hidden or peer view is consulted even when data validation fails.
    view = session.observe_protocol(owner)
    command = session.protocol_command(owner, own_request_id)
    returned = session.protocol_planning_snapshots_v3(owner)
    result = validate_collected_endpoints(view, command, returned, retained=retained,
        own_actions=own_actions, phase=phase, own_request_id=own_request_id,
        peer_message_id=peer_message_id, collection_started_at=collection_started_at,
        policy_quiet_since=policy_quiet_since, own_request=owned_client_rows[own_request_id]["request"])
    result["native_read"] = {"owner": owner, "own_request_id": own_request_id, "at": view["now"],
        "native_binary": copy.deepcopy(native._g31_native_artifact_identity), "acceptance": accepted.audit_copy(),
        "selected_peer_message_id": peer_message_id, "collection_started_at": collection_started_at,
        "actual_endpoints": ["observe_protocol", "protocol_command", "protocol_planning_snapshots_v3"]}
    if result["status"] == "conditional_validated_later_v3_data":
        result["status"] = "conditional_native_delivered_later_v3_model_input"
        result["native_delivery_verified"] = True
        result["online_information_delivered"] = True
        # Delivery authenticates source data; it cannot certify the policy's
        # conditional quiescence, a simultaneous state or model protection.
        result["conditional_stability_only"] = True
        result["current_state_certified"] = False
        result["native_protection_certified"] = False
        return NativeCollectedV3(_COLLECTION_TOKEN, result, accepted)
    return result
