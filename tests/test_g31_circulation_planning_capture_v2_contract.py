import copy

import pytest

from scripts.experiments.g31_ics_circulation import planning_capture_v2_contract as spec


def fixture():
    row = {"receipt_id": "completion:1:A:1", "source_local_sequence": 1,
        "source_owner": "A", "event": "UNLOAD_COMPLETE", "status": "completed",
        "business_bag_id": "loaded", "destination": 6, "tray_id": "L", "completed_at": 6.8}
    extension = {"schema": spec.SCHEMA, "source_owner": "A", "captured_at": 6.91,
        "terminal_receipts": [row], "completion_coverage": {"scope": spec.COMPLETION_SCOPE,
            "complete_for_declared_scope": True, "through": 6.91, "source_owned_destination_nodes": [0, 6],
            "future_events_included": False, "completed_business_bag_ids": ["loaded"]},
        "submitted_physical_actions": [{"request_id": "route-old", "kind": "route", "source_owner": "A",
            "last_delivered_ack": {"sequence": 1, "delivered_at": .14, "status": "updated"}}],
        "action_coverage": {"scope": spec.ACTION_SCOPE, "through": 6.91, "complete_for_declared_scope": True,
            "includes_unsubmitted_python_plans": False, "uses_hidden_execution_truth": False,
            "submitted_request_ids": ["route-old"], "unresolved_request_ids": []}}
    args = dict(source_owner="A", captured_at=6.91, node_owners={0: "A", 6: "A", 7: "B"},
        retained_job_contracts={"loaded": {"destination": 6}}, local_action_ledger=[("route-old", "route")])
    return extension, args


def test_receipt_survives_tray_departure_and_pure_data_never_authenticates():
    extension, args = fixture(); before = copy.deepcopy(extension)
    result = spec.validate_extension(extension, **args)
    assert result["status"] == "conditional_extension_data" and extension == before
    assert result["completed_receipts"]["loaded"]["completed_at"] == 6.8
    assert not result["native_delivery_verified"] and not result["future_source_actions_certified_absent"]


@pytest.mark.parametrize("field,value", [("destination", 7), ("source_owner", "B"),
    ("completed_at", 7.), ("event", "HOLD_COMPLETE"), ("source_local_sequence", 2),
    ("receipt_id", "global-runtime:123"), ("completed_at", float("nan")), ("source_local_sequence", True)])
def test_receipts_need_local_destination_actual_event_and_causal_identity(field, value):
    extension, args = fixture(); extension["terminal_receipts"][0][field] = value
    assert spec.validate_extension(extension, **args)["status"] == "unknown"


def test_missing_retained_contract_or_missing_receipt_never_implies_completion():
    extension, args = fixture(); args["retained_job_contracts"] = {}
    assert spec.validate_extension(extension, **args)["status"] == "unknown"
    extension, args = fixture(); extension["terminal_receipts"] = []
    assert spec.validate_extension(extension, **args)["status"] == "unknown"


def test_unreceived_terminal_truth_cannot_clear_a_pending_action():
    extension, args = fixture(); row = extension["submitted_physical_actions"][0]
    row["last_delivered_ack"] = None; row["hidden_execution_status"] = "updated"
    extension["action_coverage"]["unresolved_request_ids"] = ["route-old"]
    result = spec.validate_extension(extension, **args)
    assert "unresolved_source_physical_action" in result["reasons"]


@pytest.mark.parametrize("mutation", ["future_ack", "publication_status", "missing_action", "unknown_kind", "claims_future_plans", "hidden_truth"])
def test_action_coverage_failures_are_unknown(mutation):
    extension, args = fixture(); row = extension["submitted_physical_actions"][0]
    if mutation == "future_ack": row["last_delivered_ack"]["delivered_at"] = 7.
    elif mutation == "publication_status": row["last_delivered_ack"]["status"] = "delivered"
    elif mutation == "missing_action": extension["submitted_physical_actions"] = []
    elif mutation == "unknown_kind": row["kind"] = "new_physical_kind"
    elif mutation == "claims_future_plans": extension["action_coverage"]["includes_unsubmitted_python_plans"] = True
    elif mutation == "hidden_truth": extension["action_coverage"]["uses_hidden_execution_truth"] = True
    assert spec.validate_extension(extension, **args)["status"] == "unknown"


def test_duplicate_receipts_and_post_capture_local_admission_do_not_pass():
    extension, args = fixture(); extension["terminal_receipts"].append(copy.deepcopy(extension["terminal_receipts"][0]))
    assert spec.validate_extension(extension, **args)["status"] == "unknown"
    extension, args = fixture(); args["local_action_ledger"].append(("later-return", "transfer"))
    assert "self_capture_differs_from_owned_submission_ledger" in spec.validate_extension(extension, **args)["reasons"]
