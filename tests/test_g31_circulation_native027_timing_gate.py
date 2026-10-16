"""Pure gate guards. Mocked phase fixtures are never native acceptance evidence."""
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import native027_timing_gate as gate


def capture_fixture(case):
    spec = importlib.util.spec_from_file_location("v3_pure_fixture", gate.ROOT / "tests/test_g31_circulation_planning_capture_v3_contract.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    body = module.fixture()[0][0]
    at = 1.4 if case == "source_outage" else 1.32 if case == "expiry_tombstone" else 1.1 if case == "reserved_before_entry" else 1.3
    local = body["capture_v2"]["local_capture"]
    local.update(captured_at=at, valid_until=1.4 if case == "expiry_tombstone" else 60., publication_sequence=2 if case == "expiry_tombstone" else 1)
    tray = local["trays"][0]; tray.update(tray_id="T0", business_bag_id="B1", mode="loaded")
    extension = body["extension"]; extension["captured_at"] = at
    coverage = extension["coverage"]; coverage.update(capture_cutoff=at, source_owned_inflight_tray_ids=["T0"])
    observed = deepcopy(tray); observed["edge_exit_at"] = 11.1
    entry = extension["source_observed_inflight"][0]
    entry.update(tray_id="T0", business_bag_id="B1", entered_at=1.1, static_edge_travel_seconds=10., derived_edge_exit_at=11.1)
    if case == "reserved_before_entry":
        extension["source_observed_inflight"] = []; coverage.update(unmatched_tray_ids=["T0"], complete_for_declared_source_inflight=False)
        observed.pop("edge_exit_at")
    envelope = {"schema": "g31.planning_snapshot.v3", "kind": "planning_snapshot_v3", "capture": body,
        "payload_sha256": gate.capture_digest_v3(body), "digest_format": "g31.planning_capture_digest.v3",
        "delivered_at": 1.4 if case == "target_outage" else at + .01, "status": "conditional"}
    return envelope, observed


def v3_outputs(case):
    rows = deepcopy(gate.v3_tape(case))
    if case == "exception":
        rows[0]["exception"] = {"type": "ValueError", "message": "native negative time"}; return rows
    envelope, observed = capture_fixture(case)
    query_indices = [i for i, r in enumerate(rows) if r["endpoint"] == "protocol_command"]
    peer_indices = [i for i, r in enumerate(rows) if r["endpoint"] == "protocol_planning_snapshots_v3"]
    for row in rows:
        endpoint = row["endpoint"]
        if endpoint == "observe_protocol": row["returned"] = {"trays": [deepcopy(observed)], "delivered_command_acks": []}
        elif endpoint == "protocol_command":
            row["returned"] = {"attempt": 2 if case == "lost_ack_retry" else 1,
                "last_delivered_ack": {"status": "delivered", "planning_snapshot_v3": deepcopy(envelope)}}
        elif endpoint == "protocol_planning_snapshots_v3": row["returned"] = [deepcopy(envelope)]
        elif endpoint == "result_at":
            row["returned"] = {"receipts": [{"event": "EDGE_ENTER", "tray_id": "T0", "time": 1.1}]}
        else: row["returned"] = {"status": "pending" if endpoint == "submit_protocol_command" else "reached"}
    if case == "reserved_before_entry":
        rows[0]["returned"].update(horizon_complete=True, physical_time=1.)
        for row in rows[1:6]: row["returned"] = {"status": "budget_exhausted", "horizon_complete": False, "physical_time": 1.1}
    if case in ("lost_ack_retry", "source_outage", "target_outage"):
        rows[query_indices[0]]["returned"] = {"attempt": 1}
    if case in ("source_outage", "target_outage"): rows[peer_indices[0]]["returned"] = []
    if case == "expiry_tombstone":
        rows[query_indices[0]]["returned"] = {"last_delivered_ack": {"status": "pending_delivery", "sequence": 1}}
        rows[peer_indices[-1]]["returned"][0]["status"] = "expired"
    return rows


def records(monkeypatch):
    # Real phase conservation is separately tested against exact numeric ABI
    # fixtures. Here mock only that result and legacy dynamic scenario replay.
    monkeypatch.setattr(gate, "replay_legacy", lambda row: None)
    monkeypatch.setattr(gate.abi, "analyze_candidate_partition", lambda batches, envelopes: {
        "status": "unknown" if batches[0]["errors"] or batches[0].get("exception_fixture")
        else "structurally_valid_native027_candidate_partition"})
    result = {}
    for arm, cases in gate.ARMS.items():
        result[arm] = {}
        for case in cases:
            if case in gate.V3_CASES: outputs = v3_outputs(case)
            else:
                expected = "updated" if case == "route_allowed" else "rejected" if case in (
                    "route_stale", "source_refused", "receiver_refused", "cancel_committed") else "cancelled" if case == "cancel_pending" else "delivered" if (
                    case == "forecast_withdraw" or case.startswith("planning_snapshot")) else "received"
                outputs = [{"endpoint": name, "args": [], "kwargs": {}, "returned": {"last_delivered_ack": {
                    "status": expected, "reason": "allowed" if case == "route_allowed" else "stale_executed_prefix"}}}
                    for name in gate.old_gate.endpoints(case)]
            row = {"case": case, "status": "captured", "input": gate.scene(case), "outputs": outputs,
                "native_seal": "a" * 64, "checkpoint_seal": "a" * 64, "native_binary": {"sha256": "a" * 64}}
            if arm == "native027_timed":
                envelopes = []
                for output in outputs:
                    e = {"api_endpoint": output["endpoint"], "method": gate.abi.legacy.METHODS.index(gate.abi.ENDPOINTS027[output["endpoint"]])}
                    if output["endpoint"] == "submit_protocol_command": e["protocol_request_id"] = output["args"][0]["request_id"]
                    elif output["endpoint"] == "protocol_command": e["protocol_request_id"] = output["args"][1]
                    envelopes.append(e)
                submitted = list(dict.fromkeys(r["args"][0]["request_id"] for r in outputs if r["endpoint"] == "submit_protocol_command"))
                row["timing"] = {"envelopes": envelopes, "capture_errors": ["ValueError"] if case == "exception" else [], "batches": [{
                    "errors": 1 if case == "overflow" else 0, "exception_fixture": case == "exception",
                    "command_identities": [{"index": i, "kind": "planning_snapshot_v3", "native_index": i, "request_id": identity} for i, identity in enumerate(submitted)],
                    "rows": [{"phase": gate.PHASES.index(p), "identity_kind": 11 if p == "publication_delivery" and submitted else 0, "identity_index": 0 if submitted else -1, "exception_exit": case == "exception"}
                        for p in ("source_execution", "ack_create", "ack_delivery", "publication_delivery")]}]}
            result[arm][case] = row
    return result


def test_closed44_domain_and_all_required_gates(monkeypatch):
    assert sum(map(len, gate.ARMS.values())) == 44
    assert gate.check_records(records(monkeypatch)) == {name: True for name in gate.abi.REQUIRED_GATES}


@pytest.mark.parametrize("case", gate.V3_CASES)
def test_declared_v3_outcome_witnesses(case):
    gate.check_v3_outcome(case, v3_outputs(case))


def test_reservation_case_declares_exact_five_partial_event_prefix():
    rows = gate.v3_tape("reserved_before_entry")
    assert rows[0] == {"endpoint": "advance_to", "args": [1.], "kwargs": {}}
    assert rows[1:6] == [{"endpoint": "advance_to", "args": [1.1], "kwargs": {"max_events": 1}}] * 5
    assert rows[6] == {"endpoint": "observe_protocol", "args": ["A"], "kwargs": {}}


@pytest.mark.parametrize("defect", ["complete_step", "wrong_clock", "wrong_status", "early_incomplete", "edge_already_observed", "no_reservation", "no_later_entry"])
def test_reservation_requires_actual_partial_prefix_and_later_entry(defect):
    rows = v3_outputs("reserved_before_entry")
    if defect == "complete_step": rows[5]["returned"]["horizon_complete"] = True
    elif defect == "wrong_clock": rows[5]["returned"]["physical_time"] = 1.
    elif defect == "wrong_status": rows[5]["returned"]["status"] = "reached"
    elif defect == "early_incomplete": rows[0]["returned"]["horizon_complete"] = False
    elif defect == "edge_already_observed": rows[6]["returned"]["trays"][0]["edge_exit_at"] = 11.1
    elif defect == "no_reservation": rows[6]["returned"]["trays"][0]["edge_to"] = -1
    else: rows[-1]["returned"]["receipts"] = []
    with pytest.raises(ValueError): gate.check_v3_outcome("reserved_before_entry", rows)


@pytest.mark.parametrize("defect", ["missing_arm", "extra_case", "missing_case", "wrong_input", "undeclared_input_clock", "null_seal", "changed_checkpoint",
    "changed_legacy_order", "changed_v3_order", "wrong_query_id", "missing_envelope", "wrong_endpoint", "missing_tag11",
    "foreign_command_id", "foreign_publication_index", "missing_command_table", "wrong_overflow_bit", "negative_accepted", "missing_protocol_phase", "missing_native_exception_flag"])
def test_relationship_tampering_fails_closed(monkeypatch, defect):
    data = records(monkeypatch); timed = data["native027_timed"]["observed_entry"]
    if defect == "missing_arm": data.pop("native026_plain")
    elif defect == "extra_case": data["native027_plain"]["extra"] = deepcopy(timed)
    elif defect == "missing_case": data["native027_timed"].pop("observed_entry")
    elif defect == "wrong_input": timed["input"]["trays"] = []
    elif defect == "undeclared_input_clock": timed["input"]["wall_seconds"] = 0.
    elif defect == "null_seal": timed["native_seal"] = timed["checkpoint_seal"] = None
    elif defect == "changed_checkpoint": timed["checkpoint_seal"] = "b" * 64
    elif defect == "changed_legacy_order":
        data["native027_plain"]["normal"]["outputs"][0]["returned"] = {"z": 1, **data["native027_plain"]["normal"]["outputs"][0]["returned"]}
    elif defect == "changed_v3_order": timed["outputs"][0]["returned"] = {"extra": 1, **timed["outputs"][0]["returned"]}
    elif defect == "wrong_query_id": next(e for e in timed["timing"]["envelopes"] if e["api_endpoint"] == "protocol_command")["protocol_request_id"] = "foreign"
    elif defect == "missing_envelope": timed["timing"]["envelopes"].pop()
    elif defect == "wrong_endpoint": timed["timing"]["envelopes"][-2]["api_endpoint"] = "protocol_planning_snapshots_v2"
    elif defect == "missing_tag11":
        for span in timed["timing"]["batches"][0]["rows"]: span["identity_kind"] = 10
    elif defect == "foreign_command_id": timed["timing"]["batches"][0]["command_identities"][0]["request_id"] = "foreign"
    elif defect == "foreign_publication_index": timed["timing"]["batches"][0]["rows"][-1]["identity_index"] = 99
    elif defect == "missing_command_table": timed["timing"]["batches"][0]["command_identities"] = []
    elif defect == "wrong_overflow_bit": data["native027_timed"]["overflow"]["timing"]["batches"][0]["errors"] = 2
    elif defect == "negative_accepted": monkeypatch.setattr(gate.abi, "analyze_candidate_partition", lambda *a: {"status": "structurally_valid_native027_candidate_partition"})
    elif defect == "missing_protocol_phase": timed["timing"]["batches"][0]["rows"].pop(0)
    elif defect == "missing_native_exception_flag":
        for span in data["native027_timed"]["exception"]["timing"]["batches"][0]["rows"]: span["exception_exit"] = False
    with pytest.raises((ValueError, KeyError)): gate.check_records(data)


@pytest.mark.parametrize("defect", ["changed_retry_payload", "omitted_query", "reservation_as_entry", "wrong_actual_entry", "wrong_public_version",
    "missing_peer", "missing_final_ack", "recaptured_retry", "outage_not_real", "pending_has_body", "expired_resurrected", "digest_changed"])
def test_v3_evidence_cannot_be_replaced_by_assertions(defect):
    case = {"changed_retry_payload": "lost_ack_retry", "recaptured_retry": "lost_ack_retry",
        "reservation_as_entry": "reserved_before_entry", "outage_not_real": "source_outage",
        "pending_has_body": "expiry_tombstone", "expired_resurrected": "expiry_tombstone"}.get(defect, "observed_entry")
    rows = v3_outputs(case)
    peers = [r for r in rows if r["endpoint"] == "protocol_planning_snapshots_v3"]
    queries = [r for r in rows if r["endpoint"] == "protocol_command"]
    if defect == "changed_retry_payload": [r for r in rows if r["endpoint"] == "submit_protocol_command"][-1]["args"][0]["expiry"] = 70.
    elif defect == "omitted_query": rows.remove(queries[-1])
    elif defect == "reservation_as_entry": peers[-1]["returned"][0]["capture"]["extension"]["coverage"]["complete_for_declared_source_inflight"] = True
    elif defect == "wrong_actual_entry": rows[-1]["returned"]["receipts"][0]["time"] = 1.2
    elif defect == "wrong_public_version": rows[1]["returned"]["trays"][0]["traversal_id"] += 1
    elif defect == "missing_peer": peers[-1]["returned"] = []
    elif defect == "missing_final_ack": queries[-1]["returned"].pop("last_delivered_ack")
    elif defect == "recaptured_retry": peers[0]["returned"][0]["payload_sha256"] = "b" * 64
    elif defect == "outage_not_real": peers[0]["returned"] = deepcopy(peers[-1]["returned"])
    elif defect == "pending_has_body": queries[0]["returned"]["last_delivered_ack"]["planning_snapshot_v3"] = {}
    elif defect == "expired_resurrected": peers[-1]["returned"][0]["status"] = "conditional"
    elif defect == "digest_changed": peers[-1]["returned"][0]["payload_sha256"] = "b" * 64
    with pytest.raises((ValueError, KeyError)): gate.check_v3_outcome(case, rows)


def test_order_comparison_strips_only_explicit_native_clock_keys():
    assert gate.ordered({"a": 1, "wall_seconds": 1.}) == gate.ordered({"a": 1, "wall_seconds": 2.})
    assert gate.ordered({"a": 1, "b": 2}) != gate.ordered({"b": 2, "a": 1})
    assert gate.ordered({"captured_at": 1.}) != gate.ordered({"captured_at": 2.})


def test_source_closure_includes_actual_capture_and_old_scenario_dependencies():
    names = {str(p.relative_to(gate.ROOT)).replace("\\", "/") for p in gate.source_paths()}
    for path in ("capture_native027_request_timing.py", "native027_request_timing.py", "native025_timing_gate.py", "planning_capture_v3_contract.py"):
        assert "scripts/experiments/g31_ics_circulation/" + path in names
    assert "scripts/eval/run_g4irsf28_service_potential.py" in names


def test_saved_receipt_hash_checked_before_other_reads(tmp_path):
    path = tmp_path / "receipt.json"; gate.write(path, {})
    with pytest.raises(ValueError, match="receipt_changed"):
        gate.verify_saved_gate({"path": str(path), "sha256": "f" * 64})


def test_preparation_never_accepts_native027_as_legacy026(tmp_path, monkeypatch):
    binary = tmp_path / "wrong.pyd"; binary.write_bytes(b"candidate")
    build = tmp_path / "receipt.json"
    gate.write(build, {"schema": "g31.circulation.build_only.v1", "status": "build_passed_tests_held",
        "source_before": {"x.hpp": "a" * 64}, "source_after": {"x.hpp": "a" * 64}, "source_changed": [],
        "commands": [{"exit_code": 0}, {"exit_code": 0}], "binary_sha256": {str(binary): gate.sha(binary)}})
    with pytest.raises(ValueError, match="build_binary_mismatch"):
        gate.verify_build(build, tmp_path, binary, gate.NATIVE026_SHA)


def saved_fixture(tmp_path, monkeypatch):
    data = records(monkeypatch)
    sources = {str(Path(p).resolve()): "c" * 64 for p in (gate.__file__, gate.native_host.__file__,
        Path(gate.__file__).with_name("capture_native027_request_timing.py"))}
    plan = {"binary_sha256": "b" * 64, "binary": str(tmp_path / "027.pyd"),
        "native026_binary": str(tmp_path / "026.pyd"), "source_sha256": sources}
    gate.write(tmp_path / "plan.json", plan)
    monkeypatch.setattr(gate, "verify_plan", lambda directory, supplied: {"binary_sha256": "b" * 64})
    receipt = {"schema": gate.SCHEMA, "status": "captured_pending_independent_verification", "source_changed": [],
        "plan_sha256": gate.sha(tmp_path / "plan.json"), "raw": {}, "process_sha256": {}, "completion_sha256": {}}
    for arm, cases in gate.ARMS.items():
        directory = tmp_path / arm; directory.mkdir()
        process = {"status": "process_exited", "exit_code": 0,
            "command": [gate.sys.executable, "-m", gate.MODULE, "--output", str(tmp_path.resolve()), "--arm", arm]}
        process_path = tmp_path / (arm + ".process.json"); gate.write(process_path, process)
        receipt["process_sha256"][arm] = gate.sha(process_path)
        digest = gate.NATIVE026_SHA if arm == "native026_plain" else "b" * 64
        completion = {"schema": gate.SCHEMA, "status": "completed_declared_arm", "arm": arm, "cases": list(cases),
            "source_changed": [], "unarchived_loaded_sources": [], "runtime_loaded_sha256": sources,
            "native_binary_sha256": digest}
        gate.write(directory / "completion.json", completion); receipt["completion_sha256"][arm] = gate.sha(directory / "completion.json")
        receipt["raw"][arm] = {}
        for case in cases:
            row = data[arm][case]
            row["native_binary"] = {"sha256": digest, "resolved_path": plan["native026_binary"] if arm == "native026_plain" else plan["binary"]}
            path = directory / (case + ".json.gz"); gate.write(path, row); receipt["raw"][arm][case] = gate.sha(path)
    gate.write(tmp_path / "receipt.json", receipt)
    return {"path": str(tmp_path / "receipt.json"), "sha256": gate.sha(tmp_path / "receipt.json")}


def replace_json(path, value):
    # Counterfactual saved-file tampering fixture; never touches real evidence.
    path.unlink(); gate.write(path, value)


def test_saved_gate_reloads_all44_raw_files(tmp_path, monkeypatch):
    reference = saved_fixture(tmp_path, monkeypatch)
    assert gate.verify_saved_gate(reference)["declared_sessions"] == 44


@pytest.mark.parametrize("defect", ["missing_raw", "changed_raw_hash", "rehashed_bad_seal", "wrong_loaded_binary",
    "failed_process", "wrong_process_command", "missing_arm_receipt", "unarchived_loaded", "omitted_loaded_capture", "changed_loaded_hash"])
def test_saved_file_tampering_rejected_even_with_rehashed_receipt(tmp_path, monkeypatch, defect):
    reference = saved_fixture(tmp_path, monkeypatch)
    receipt = gate.read(tmp_path / "receipt.json"); arm = "native027_timed"; case = "observed_entry"
    raw_path = tmp_path / arm / (case + ".json.gz")
    if defect == "missing_raw": raw_path.unlink()
    elif defect in ("changed_raw_hash", "rehashed_bad_seal", "wrong_loaded_binary"):
        row = gate.read(raw_path)
        if defect == "wrong_loaded_binary": row["native_binary"]["resolved_path"] = str(tmp_path / "026.pyd")
        else: row["native_seal"] = row["checkpoint_seal"] = "d" * 64
        replace_json(raw_path, row)
        if defect != "changed_raw_hash": receipt["raw"][arm][case] = gate.sha(raw_path)
    elif defect in ("failed_process", "wrong_process_command"):
        path = tmp_path / (arm + ".process.json"); process = gate.read(path)
        if defect == "failed_process": process["exit_code"] = 1
        else: process["command"][-1] = "native026_plain"
        replace_json(path, process); receipt["process_sha256"][arm] = gate.sha(path)
    elif defect == "missing_arm_receipt": receipt["completion_sha256"].pop(arm)
    else:
        path = tmp_path / arm / "completion.json"; completion = gate.read(path)
        if defect == "unarchived_loaded": completion["unarchived_loaded_sources"] = ["outside.py"]
        elif defect == "omitted_loaded_capture": completion["runtime_loaded_sha256"].pop(str(Path(gate.__file__).with_name("capture_native027_request_timing.py").resolve()))
        else: completion["runtime_loaded_sha256"][str(Path(gate.__file__).resolve())] = "d" * 64
        replace_json(path, completion); receipt["completion_sha256"][arm] = gate.sha(path)
    replace_json(tmp_path / "receipt.json", receipt); reference["sha256"] = gate.sha(tmp_path / "receipt.json")
    with pytest.raises((ValueError, KeyError, OSError)): gate.verify_saved_gate(reference)
