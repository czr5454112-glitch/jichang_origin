"""Raw trace must independently agree with the separate causal ledger."""
import gzip
import json

import pytest

from scripts.experiments.g31_ics_circulation.verify_request_bundles import verify


def save(path, value):
    with gzip.open(path, "wt") as stream:
        json.dump(value, stream)


def fixture(directory):
    key = json.dumps(["A", "periodic_tick", 0])
    root = {"request_id": "root", "owner_id": "A", "owner_epoch": 0, "accepted_ns": 2,
        "logical_opened_at": 0., "logical_closed_at": 0., "status": "no_action", "message_ids": [],
        "maintenance_only": False, "activation_bundle_id": 2, "required_drain_after_bundle_id": 2,
        "drain_complete_bundle_id": 4, "trigger_bundle_ids": [0], "trigger_keys": [key],
        "activation_causes": {"periodic_tick": 0}}
    bundles = []
    for i, (kind, start, end) in enumerate([("native_advance_full", 0, 1), ("scheduler_gap_full", 1, 2),
        ("owner_activation", 2, 4), ("scheduler_gap_full", 4, 5), ("native_advance_full", 5, 7),
        ("scheduler_output_full", 7, 10)]):
        b = {"bundle_id": i, "kind": kind, "start_ns": start, "end_ns": end, "root_request_ids": ["root"]}
        if kind == "native_advance_full":
            b.update(native_status="notified", timestamp_complete=True, physical_time=0., notification_sequences={}, protocol_request_ids=[])
        if kind == "owner_activation":
            b.update(activation_root_id="root", protocol_request_ids=[])
        bundles.append(b)
    ledger = {"schema": "g31.request_bundle_ledger.v1", "clock": "monotonic_ns", "execution_lanes": 1,
        "coverage": "whole_controller_calls_and_all_native_calls", "native_physics_subtracted": False,
        "request_scope": "owner_activation_updates", "requests": [root], "messages": [], "bundles": bundles,
        "service_windows": [{"start_ns": 0, "end_ns": 10}], "cause_origins": {key: 0}}
    part = {"control_records": [{"trace_sequence": 1, "owner_id": "A", "owner_epoch": 0,
        "causes": {"periodic_tick": 0}, "compute_wall_ms": .000001}], "native_batches": [
        {"trace_sequence": i, "status": "notified", "timestamp_complete": True, "end_at": 0.} for i in (0, 2)],
        "client_calls": [], "controller_state": {"client": {"outbox": {}}}}
    (directory/"manifest.json").write_text(json.dumps({"status": "captured", "source_changed": [],
        "segments": 1, "requested_activation_limits": [5]}))
    save(directory/"ledger.json.gz", ledger)
    save(directory/"segment_0001.json.gz", part)
    return part


def test_raw_no_action_root_and_native_drains_match(tmp_path):
    fixture(tmp_path)
    result = verify(tmp_path)
    assert result["status"] == "verified_raw_execution_and_bundle_accounting", result
    assert result["owner_activations"] == 1 and result["native_advance_calls"] == 2
    assert result["protocol_identities"] == 0 and result["open_roots"] == 0
    assert result["complete_100ms_requirement_certified"] is False


@pytest.mark.parametrize("defect", ["lost_native", "lost_no_action", "changed_cause", "unknown_submission", "lost_outbox_history"])
def test_raw_trace_omissions_and_mismatches_fail_closed(tmp_path, defect):
    part = fixture(tmp_path)
    if defect == "lost_native": part["native_batches"].pop()
    elif defect == "lost_no_action": part["control_records"].clear()
    elif defect == "changed_cause": part["control_records"][0]["causes"]["periodic_tick"] = 1
    elif defect == "unknown_submission": part["client_calls"] = [{"request": {"request_id": "unknown"}}]
    else: part["controller_state"]["client"]["outbox"]["unrecorded"] = {}
    save(tmp_path/"segment_0001.json.gz", part)
    assert verify(tmp_path)["status"] == "unknown_invalid_or_missing_raw_evidence"
