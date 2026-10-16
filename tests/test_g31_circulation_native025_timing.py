"""Explicit025 candidate ABI does not widen022 or claim pending runtime gates."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import native025_request_timing as versioned
from scripts.experiments.g31_ics_circulation import native_request_timing as legacy
from scripts.experiments.g31_ics_circulation import capture_native025_request_timing as capture


def header(abi):
    return "\n".join("enum class "+name+" : unsigned {"+",".join(values)+"};" for name, values in abi.items())


def fixture():
    def row(identity, index):
        return {"span_id": index, "parent_span_id": -1 if index == 0 else 0,
            "start_ns": 0 if index == 0 else index*10, "end_ns": 100 if index == 0 else index*10+5,
            "phase": 0 if index == 0 else 10, "method": 10 if index == 0 else 0,
            "trace_epoch": 1, "call_ordinal": 1, "event_sequence": 0, "logical_time": 2., "attempt": 1,
            "identity_kind": identity, "identity_index": -1 if index == 0 else 0,
            "related_identity_kind": 0, "related_identity_index": -1, "ended": True, "exception_exit": False}
    batch = {"schema": "g31.native_request_timing.v1", "clock": "steady_clock_relative_nanoseconds",
        "coverage": "known_control_phases_and_unclassified_remainder", "physics_subtraction_authorized": False,
        "session_identity": 1, "trace_epoch": 1, "errors": 0, "completed_outer_calls": 1, "emitted_span_count": 3,
        "rows": [row(0, 0), row(9, 1), row(10, 2)], "transfer_identities": [], "leg_identities": [], "job_identities": [],
        "command_identities": [{"index": 0, "request_id": "old", "kind": "planning_snapshot", "native_index": 0},
            {"index": 1, "request_id": "new", "kind": "planning_snapshot_v2", "native_index": 0}]}
    envelope = {"session_identity": 1, "trace_epoch": 1, "call_ordinal": 1, "method": 10,
        "start_ns": 1000, "end_ns": 1105, "api_endpoint": "protocol_planning_snapshots_v2"}
    return [batch], [envelope]


def prepared(tmp_path):
    archive = tmp_path/"archive"
    path = archive/"cpp/ics_core/runtime/request_timing_recorder.hpp"
    path.parent.mkdir(parents=True); path.write_text(header(versioned.ABI025))
    binary = tmp_path/"native025.pyd"; binary.write_bytes(b"unit_fixture_not_a_native_binary")
    sources = {"cpp/ics_core/runtime/request_timing_recorder.hpp": versioned.sha(path)}
    build = {"schema": "g31.circulation.build_only.v1", "status": "build_passed_tests_held",
        "source_before": sources, "source_after": sources, "source_changed": [],
        "binary_sha256": {str(binary): versioned.sha(binary)}}
    receipt = tmp_path/"build.json"; receipt.write_text(json.dumps(build))
    reference = versioned.prepare_contract(receipt, archive, binary, tmp_path/"contract.json")
    return reference, path, binary


def rewrite_contract(reference, mutate):
    path = Path(reference["path"]); data = json.loads(path.read_bytes())
    mutate(data); path.write_text(json.dumps(data)); reference["sha256"] = versioned.sha(path)


def test_only_exact_two_closed_abis_supported_and_old_numeric_ids_preserved():
    assert versioned.exact_header_abi(header(versioned.ABI022))[0] == "native022"
    assert versioned.exact_header_abi(header(versioned.ABI025))[0] == "native025"
    assert versioned.ABI025["RequestTimingIdentity"][:-1] == legacy.IDENTITIES
    assert versioned.ABI025["RequestTimingIdentity"][10] == "planning_snapshot_v2"
    assert legacy.METHODS[10] == "planning_snapshots"
    for name in versioned.ABI025:
        bad = copy.deepcopy(versioned.ABI025)
        bad[name] = (*bad[name], "future_unknown")
        with pytest.raises(ValueError, match="unsupported_or_reordered_abi"):
            versioned.exact_header_abi(header(bad))
        bad[name] = (bad[name][1], bad[name][0], *bad[name][2:-1])
        with pytest.raises(ValueError, match="unsupported_or_reordered_abi"):
            versioned.exact_header_abi(header(bad))


def test_025_namespaces_resolve_separately_while022_rejects_new_tag():
    batches, envelopes = fixture()
    original = copy.deepcopy((batches, envelopes))
    result = versioned.analyze_candidate_partition(batches, envelopes)
    assert result["status"] == "structurally_valid_native025_candidate_partition", result
    assert result["runtime_accepted"] is False
    assert result["unchanged_whole_native_envelope_ns"] == 105
    assert result["physics_subtracted_ns"] == 0
    assert legacy.analyze_native_timing(batches, envelopes)["status"] == "unknown"
    assert legacy.IDENTITIES == versioned.ABI022["RequestTimingIdentity"]
    assert (batches, envelopes) == original


@pytest.mark.parametrize("defect", ["unknown_identity", "missing_v2_identity", "v1_substituted_for_v2",
    "missing_endpoint", "wrong_endpoint_method", "unknown_endpoint", "missing_final_span", "exception"])
def test_closed025_partition_rejects_unknown_or_unbound_records(defect):
    batches, envelopes = fixture()
    if defect == "unknown_identity": batches[0]["rows"][2]["identity_kind"] = 11
    elif defect == "missing_v2_identity": batches[0]["command_identities"].pop()
    elif defect == "v1_substituted_for_v2": batches[0]["command_identities"][1]["kind"] = "planning_snapshot"
    elif defect == "missing_endpoint": del envelopes[0]["api_endpoint"]
    elif defect == "wrong_endpoint_method": envelopes[0]["method"] = 11
    elif defect == "unknown_endpoint": envelopes[0]["api_endpoint"] = "future_query"
    elif defect == "missing_final_span": batches[0]["rows"].pop()
    else: batches[0]["rows"][2]["exception_exit"] = True
    assert versioned.analyze_candidate_partition(batches, envelopes)["status"] == "unknown"


def test_build_only_contract_never_becomes_runtime_acceptance(tmp_path):
    reference, _, _ = prepared(tmp_path)
    assert versioned.verify_contract(reference)["runtime_accepted"] is False
    with pytest.raises(ValueError, match="runtime_acceptance_pending"):
        versioned.verify_contract(reference, require_runtime=True)
    result = versioned.analyze_native025_timing(*fixture(), reference)
    assert result["status"] == "unknown_runtime_acceptance_pending"
    assert result["candidate_partition"]["status"] == "structurally_valid_native025_candidate_partition"
    assert result["complete_request_100ms_certified"] is False


@pytest.mark.parametrize("defect", ["archive", "binary", "contract_hash", "endpoint_inventory", "validator_hash",
    "old_abi", "fake_acceptance", "missing_runtime_gate"])
def test_pinned_contract_tampering_and_incomplete_acceptance_fail_closed(tmp_path, defect):
    reference, archived, binary = prepared(tmp_path)
    if defect == "archive": archived.write_text("changed")
    elif defect == "binary": binary.write_bytes(b"changed")
    elif defect == "contract_hash": Path(reference["path"]).write_text("{}")
    elif defect == "endpoint_inventory": rewrite_contract(reference, lambda d:d["endpoint_methods"].pop("protocol_planning_snapshots_v2"))
    elif defect == "validator_hash": rewrite_contract(reference, lambda d:d.update(legacy_validator_sha256="bad"))
    elif defect == "old_abi": rewrite_contract(reference, lambda d:d["abi"].update(RequestTimingIdentity=list(legacy.IDENTITIES)))
    else:
        contract = json.loads(Path(reference["path"]).read_bytes())
        acceptance = {"schema": "g31.native025_timing_acceptance.v1", "status": "passed", "source_changed": [],
            "binary_sha256": contract["binary_sha256"], "build_receipt_sha256": contract["build_receipt_sha256"],
            "versioned_validator_sha256": contract["versioned_validator_sha256"],
            "gates": {gate: True for gate in versioned.RUNTIME_GATES}, "evidence": {}}
        if defect == "missing_runtime_gate": acceptance["gates"].pop(versioned.RUNTIME_GATES[-1])
        path = tmp_path/"acceptance.json"; path.write_text(json.dumps(acceptance))
        rewrite_contract(reference, lambda d:d.update(runtime_acceptance={"path": str(path), "sha256": versioned.sha(path)}))
    assert versioned.analyze_native025_timing(*fixture(), reference)["status"] == "unknown"


def test_capture_names_v2_endpoint_without_mutating_legacy_mapping(tmp_path, monkeypatch):
    class Session:
        def offline_request_timing_start(self, capacity, identity): pass
        def offline_request_timing_take(self): return {"rows": [], "errors": 0, "completed_outer_calls": 0,
            "trace_epoch": 1, "session_identity": 7}
        def protocol_planning_snapshots_v2(self, owner): return response
    binary = tmp_path/"native025.pyd"
    calls = []
    def verify(reference, *, require_runtime=False):
        calls.append(require_runtime)
        return {"contract": {"binary": str(binary)}, "runtime_accepted": False}
    monkeypatch.setattr(capture, "verify_contract", verify)
    native = SimpleNamespace(NativeSession=Session, __file__=str(binary))
    response = [{"nested": {"unchanged": True}}]
    raw = Session()
    proxy = capture.Native025TimingCapture(raw, native_module=native, contract_reference={}, acceptance_probe=True,
        session_identity=7)
    assert proxy.protocol_planning_snapshots_v2("A") is response
    assert proxy.envelopes[0]["api_endpoint"] == "protocol_planning_snapshots_v2"
    assert proxy.envelopes[0]["method"] == 10
    assert "protocol_planning_snapshots_v2" not in capture.RecentNativeTimingCapture._invoke.__globals__["API_METHODS"]
    assert calls == [False]
    with pytest.raises(ValueError, match="session_module_identity_mismatch"):
        capture.Native025TimingCapture(raw, native_module=SimpleNamespace(NativeSession=object, __file__=str(binary)),
            contract_reference={}, session_identity=7)


def attach_attestation(tmp_path, reference, defect=None):
    contract = json.loads(Path(reference["path"]).read_bytes())
    pins = {k: contract[k] for k in ("binary_sha256", "build_receipt_sha256", "versioned_validator_sha256")}
    acceptance = {"schema": "g31.native025_timing_acceptance.v1", "status": "passed", "source_changed": [],
        **pins, "gates": {g: True for g in versioned.RUNTIME_GATES}, "evidence": {}}
    for gate in versioned.RUNTIME_GATES:
        report = {"schema": "g31.native025_timing_gate_attestation.v1", "status": "passed", "gate": gate,
            **pins, "source_changed": [], "checks": {"externally_declared_case": True}}
        if defect == "failed": report["status"] = "failed"
        if defect == "wrong_binary": report["binary_sha256"] = "bad"
        if defect == "changed_source": report["source_changed"] = ["source"]
        if defect == "missing_checks": report["checks"] = {}
        if defect == "false_check": report["checks"]["externally_declared_case"] = False
        path = tmp_path/(gate+".json")
        path.write_text("arbitrary text" if defect == "non_json" else json.dumps(report))
        acceptance["evidence"][gate] = [{"path": str(path), "sha256": versioned.sha(path)}]
    path = tmp_path/"attested_acceptance.json"; path.write_text(json.dumps(acceptance))
    rewrite_contract(reference, lambda c:c.update(runtime_acceptance={"path": str(path), "sha256": versioned.sha(path)}))


@pytest.mark.parametrize("defect", ["failed", "wrong_binary", "changed_source", "missing_checks", "false_check", "non_json"])
def test_hash_pinned_failed_or_malformed_evidence_cannot_enable_runtime(tmp_path, defect):
    reference, _, _ = prepared(tmp_path)
    attach_attestation(tmp_path, reference, defect)
    assert versioned.analyze_native025_timing(*fixture(), reference)["status"] == "unknown"


def test_complete_external_attestation_is_not_independent_runtime_verification(tmp_path):
    reference, _, _ = prepared(tmp_path)
    attach_attestation(tmp_path, reference)
    result = versioned.verify_contract(reference)
    assert result["runtime_gates_externally_attested"] is True
    assert result["runtime_accepted"] is False
    with pytest.raises(ValueError, match="runtime_acceptance_pending"):
        versioned.verify_contract(reference, require_runtime=True)
    assert versioned.analyze_native025_timing(*fixture(), reference)["status"] == "unknown_runtime_acceptance_pending"
