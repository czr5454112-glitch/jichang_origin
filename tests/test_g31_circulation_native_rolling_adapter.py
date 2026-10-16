"""Pure trust-boundary guards; actual v2 collection needs native025 acceptance."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import native_rolling_planning_adapter as adapter
from scripts.experiments.g31_ics_circulation.planning_capture_v2_digest import capture_digest_v2
from scripts.experiments.g31_ics_circulation.planning_capture_v2_contract import ACTION_SCOPE, COMPLETION_SCOPE
from test_g31_circulation_public_rolling_reuse_model import state


def pair():
    contract, jobs, trays, resources, args = state()
    now = args["now"]; owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
    for j in jobs.values(): j["protected_service"] = True
    retained = {"owner": "A", "retained_at": .11, "static_contract_sha256": "a" * 64,
        "contracts": {key: {k: row[k] for k in adapter.CONTRACT_FIELDS} for key, row in jobs.items()}}
    captures = {}
    for record in args["source_records"]:
        source = record["owner"]
        local = {"schema": "g31.planning_capture.v1", "message_id": "native-shaped:" + source,
            "source_owner": source, "target_owner": ({"A", "B"} - {source}).pop(), "publication_sequence": 2,
            "captured_at": now - .04, "valid_until": now + .1, "static_contract_sha256": "a" * 64,
            "semantics": deepcopy(record["semantics"]), "jobs": [deepcopy(jobs[key]) for key in record["job_ids"]],
            "trays": [deepcopy(trays[key]) for key in record["tray_ids"]],
            "nodes": [{**deepcopy(resources[key]), "unrepresented_occupancy": 0} for key in record["node_ids"]],
            "known_faults": [], "coverage": {"scope": "source_waiting_or_locally_carried_released_jobs_and_local_trays",
                "complete_for_declared_local_scope": True, "local_node_ids": record["node_ids"],
                "tray_ids": record["tray_ids"], "business_bag_ids": record["job_ids"],
                "unrepresented_occupancy": 0, "future_arrivals_included": False}}
        for tray in local["trays"]:
            tray.setdefault("load_complete_at", -1.)
            if tray["tray_id"] == "L": tray["available_at"] = tray["service_ready_at"] = now - .05
        completion = [] if source == "B" else [{"receipt_id": "completion:1:A:1", "source_local_sequence": 1,
            "source_owner": "A", "event": "UNLOAD_COMPLETE", "status": "completed", "business_bag_id": "loaded",
            "destination": 6, "tray_id": "L", "completed_at": 6.8}]
        extension = {"schema": "g31.planning_extension.v2", "source_owner": source, "captured_at": local["captured_at"],
            "terminal_receipts": completion, "completion_coverage": {"scope": COMPLETION_SCOPE,
                "complete_for_declared_scope": True, "through": local["captured_at"],
                "source_owned_destination_nodes": record["node_ids"], "future_events_included": False,
                "completed_business_bag_ids": [r["business_bag_id"] for r in completion]},
            "submitted_physical_actions": [], "action_coverage": {"scope": ACTION_SCOPE,
                "through": local["captured_at"], "complete_for_declared_scope": True,
                "includes_unsubmitted_python_plans": False, "uses_hidden_execution_truth": False,
                "submitted_request_ids": [], "unresolved_request_ids": []}}
        body = {"schema": "g31.planning_capture.v2", "local_capture": local, "extension": extension}
        captures[source] = {"schema": "g31.planning_snapshot.v2", "kind": "planning_snapshot_v2", "capture": body,
            "payload_sha256": capture_digest_v2(body), "digest_format": "g31.planning_capture_digest.v2",
            "delivered_at": now - .03, "status": "conditional"}
    own = captures["A"]["capture"]["local_capture"]
    view = {**deepcopy(contract), "owner_id": "A", "now": now, "jobs": deepcopy(own["jobs"]),
        "trays": deepcopy(own["trays"]), "known_faults": []}
    view["node_contracts"] = [dict(n, **({k: resources[n["node"]][k] for k in ("occupancy", "actual_available")} if owners[n["node"]] == "A" else {})) for n in contract["node_contracts"]]
    ack = {"status": "delivered", "executed_at": now - .04, "completed_at": now - .03, "delivered_at": now - .01,
        "result_id": own["message_id"], "planning_snapshot_v2": captures["A"]}
    return view, ack, [captures["B"]], dict(retained=retained, own_actions=[], phase="first_return")


def test_valid_native_shaped_pair_stays_data_only_and_retains_full_prefix():
    args = pair(); result = adapter.validate_later_pair(*args[:3], **args[3])
    assert result["status"] == "conditional_validated_later_data", result
    assert result["bundle"]["completed_prefix"] == {"loaded": 6.8}
    assert not result["native_delivery_verified"] and not result["online_information_delivered"]


@pytest.mark.parametrize("mutation", ["fake_delivery", "missing_receipt", "changed_contract", "new_local_action", "future_ack", "source_owner", "local_transition"])
def test_bad_pair_cannot_be_rescued_by_native_provenance_text(mutation):
    view, ack, peer, kwargs = pair()
    if mutation == "fake_delivery": ack["status"] = "pending_delivery"
    elif mutation == "missing_receipt": ack["planning_snapshot_v2"]["capture"]["extension"]["terminal_receipts"] = []
    elif mutation == "changed_contract": kwargs["retained"]["contracts"]["receiver"]["load_seconds"] = 30.
    elif mutation == "new_local_action": kwargs["own_actions"] = [("new", "transfer")]
    elif mutation == "future_ack": ack["delivered_at"] = view["now"] + 1.
    elif mutation == "source_owner": peer[0]["capture"]["extension"]["source_owner"] = "A"
    elif mutation == "local_transition": view["trays"][0]["mode"] = "loaded"
    view["provenance"] = "native_delivered_planning_contract"
    result = adapter.validate_later_pair(view, ack, peer, **kwargs)
    assert result["status"] == "unknown" and not result["native_delivery_verified"]


def test_fake_native_session_cannot_create_verified_contract_ledger_or_collect():
    native, session = SimpleNamespace(), SimpleNamespace()
    receipt, ledger = adapter.collect_initial_ledger(native, session, "A", "fake")
    assert ledger is None and receipt["status"] == "unknown"
    receipt = adapter.collect_native(native, session, "A", "fake", ledger=None, owned_client_rows={}, phase="first_return")
    assert receipt["status"] == "unknown" and not receipt["native_delivery_verified"]
    with pytest.raises(ValueError, match="ledger_requires_native_initial_collection"):
        adapter.NativeJobLedger(None, session, "A", {})


def test_full_owner_observation_completed_history_is_not_active_capture_scope():
    view, ack, peer, kwargs = pair()
    view["jobs"].append({**kwargs["retained"]["contracts"]["loaded"], "status": "completed", "loaded_at": .1,
        "storage_entered_at": 5.4, "storage_released_at": 6.})
    result = adapter.validate_later_pair(view, ack, peer, **kwargs)
    assert result["status"] == "conditional_validated_later_data", result
    assert result["bundle"]["completed_prefix"]["loaded"] == 6.8
    assert result["online_information_delivered"] is False
    body = ack["planning_snapshot_v2"]["capture"]
    body["extension"]["terminal_receipts"] = []
    body["extension"]["completion_coverage"]["completed_business_bag_ids"] = []
    ack["planning_snapshot_v2"]["payload_sha256"] = capture_digest_v2(body)
    rejected = adapter.validate_later_pair(view, ack, peer, **kwargs)
    assert rejected["status"] == "unknown"
    assert rejected["reasons"] == ["owned_completed_job_without_delivered_terminal_receipt"]
