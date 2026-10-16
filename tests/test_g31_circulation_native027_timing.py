"""New identity cannot silently widen old validators or enable runtime claims."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import native027_request_timing as new
from scripts.experiments.g31_ics_circulation import native025_request_timing as old
from scripts.experiments.g31_ics_circulation import native_request_timing as legacy
from scripts.experiments.g31_ics_circulation import capture_native027_request_timing as capture
from test_g31_circulation_native025_timing import fixture as old_fixture, header


def fixture():
    batches, envelopes = old_fixture()
    row = copy.deepcopy(batches[0]["rows"][-1]); row.update(span_id=3, start_ns=30, end_ns=35, identity_kind=11)
    batches[0]["rows"].append(row); batches[0]["emitted_span_count"] = 4
    batches[0]["command_identities"].append({"index": 2, "request_id": "third", "kind": "planning_snapshot_v3", "native_index": 0})
    envelopes[0]["api_endpoint"] = "protocol_planning_snapshots_v3"
    return batches, envelopes


def prepared(tmp_path):
    archive = tmp_path/"source"; path = archive/"cpp/ics_core/runtime/request_timing_recorder.hpp"
    path.parent.mkdir(parents=True); path.write_text(header(new.ABI027))
    binary = tmp_path/"fake.pyd"; binary.write_bytes(b"unit fixture only, not native execution")
    sources = {"cpp/ics_core/runtime/request_timing_recorder.hpp": new.sha(path)}
    build = {"schema": "g31.circulation.build_only.v1", "status": "build_passed_tests_held", "source_changed": [],
        "source_before": sources, "source_after": sources, "binary_sha256": {str(binary): new.sha(binary)}}
    receipt = tmp_path/"build.json"; receipt.write_text(json.dumps(build))
    return new.prepare_contract(receipt, archive, binary, tmp_path/"contract.json"), path, binary


def test_identity_11_is_separate_and_old_validators_still_reject_it():
    before = (legacy.IDENTITIES, copy.deepcopy(old.ABI025), copy.deepcopy(old.ENDPOINTS025))
    data = fixture(); unchanged = copy.deepcopy(data)
    result = new.analyze_candidate_partition(*data)
    assert result["status"] == "structurally_valid_native027_candidate_partition", result
    assert not result["runtime_accepted"] and not result["complete_request_100ms_certified"]
    assert result["unchanged_whole_native_envelope_ns"] == 105 and result["physics_subtracted_ns"] == 0
    assert old.analyze_candidate_partition(*data)["status"] == legacy.analyze_native_timing(*data)["status"] == "unknown"
    assert new.ABI027["RequestTimingIdentity"][:-1] == old.ABI025["RequestTimingIdentity"]
    assert new.ABI027["RequestTimingIdentity"][11] == "planning_snapshot_v3"
    assert data == unchanged and before == (legacy.IDENTITIES, old.ABI025, old.ENDPOINTS025)


@pytest.mark.parametrize("defect", ["new_tag", "missing_v3_mapping", "mapped_to_v2", "wrong_index",
    "unended", "overflow", "wrong_endpoint", "wrong_method", "exception"])
def test_unknown_unbound_and_incomplete_records_stay_unknown(defect):
    batches, envelopes = fixture(); row = batches[0]["rows"][-1]
    if defect == "new_tag": row["identity_kind"] = 12
    elif defect == "missing_v3_mapping": batches[0]["command_identities"].pop()
    elif defect == "mapped_to_v2": batches[0]["command_identities"][-1]["kind"] = "planning_snapshot_v2"
    elif defect == "wrong_index": row["identity_index"] = 5
    elif defect == "unended": row["ended"] = False
    elif defect == "overflow": batches[0]["errors"] = 1
    elif defect == "wrong_endpoint": envelopes[0]["api_endpoint"] = "invented"
    elif defect == "wrong_method": envelopes[0]["method"] = 11
    else: row["exception_exit"] = True
    assert new.analyze_candidate_partition(batches, envelopes)["status"] == "unknown"


def test_closed_header_rejects_old_reordered_and_unknown_enum():
    assert new.exact_header_abi(header(new.ABI027)) == new.ABI027
    for changed in (old.ABI025, {**new.ABI027, "RequestTimingIdentity": tuple(reversed(new.ABI027["RequestTimingIdentity"]))},
                    {**new.ABI027, "RequestTimingMethod": (*new.ABI027["RequestTimingMethod"], "future")}):
        with pytest.raises(ValueError, match="unsupported_or_reordered_abi"):
            new.exact_header_abi(header(changed))
    with pytest.raises(ValueError): old.exact_header_abi(header(new.ABI027))


def test_build_only_contract_cannot_enable_runtime_or_100ms(tmp_path):
    reference, _, _ = prepared(tmp_path)
    assert not new.verify_contract(reference)["runtime_accepted"]
    with pytest.raises(ValueError, match="runtime_acceptance_pending"):
        new.verify_contract(reference, require_runtime=True)
    result = new.analyze_native027_timing(*fixture(), reference)
    assert result["status"] == "unknown_runtime_acceptance_pending"
    assert result["candidate_partition"]["status"] == "structurally_valid_native027_candidate_partition"
    assert result["complete_request_100ms_certified"] is False


@pytest.mark.parametrize("defect", ["archive", "binary", "contract_hash", "endpoint_inventory", "validator_hash", "fake_acceptance", "source_path"])
def test_contract_and_source_tampering_cannot_become_acceptance(tmp_path, defect):
    reference, source, binary = prepared(tmp_path); path = Path(reference["path"])
    if defect == "archive": source.write_text("changed")
    elif defect == "binary": binary.write_bytes(b"changed")
    elif defect == "contract_hash": path.write_text("{}")
    else:
        contract = json.loads(path.read_bytes())
        if defect == "endpoint_inventory": del contract["endpoint_methods"]["protocol_planning_snapshots_v3"]
        elif defect == "validator_hash": contract["validator_source_sha256"] = {}
        elif defect == "source_path": contract["source_sha256"] = {"../outside": "fake"}
        else: contract["runtime_acceptance"] = {"status": "passed", "all_gates": True}
        path.write_text(json.dumps(contract)); reference["sha256"] = new.sha(path)
    assert new.analyze_native027_timing(*fixture(), reference)["status"] == "unknown"


def test_probe_capture_binds_actual_v3_endpoint_without_legacy_mapping_mutation(tmp_path, monkeypatch):
    class Session:
        def offline_request_timing_start(self, capacity, identity): pass
        def offline_request_timing_take(self): return {"rows": [], "errors": 0, "completed_outer_calls": 0,
            "trace_epoch": 1, "session_identity": 7}
        def protocol_planning_snapshots_v3(self, owner): return response
    binary = tmp_path/"fixture.pyd"; gates = []
    def verify(reference, *, require_runtime=False):
        gates.append(require_runtime)
        if require_runtime: raise ValueError("native027_timing:runtime_acceptance_pending")
        return {"contract": {"binary": str(binary)}, "runtime_accepted": False}
    monkeypatch.setattr(capture, "verify_contract", verify)
    raw = Session(); native = SimpleNamespace(NativeSession=Session, __file__=str(binary)); response = [{"source": "unchanged"}]
    with pytest.raises(ValueError, match="runtime_acceptance_pending"):
        capture.Native027TimingCapture(raw, native_module=native, contract_reference={}, session_identity=7)
    proxy = capture.Native027TimingCapture(raw, native_module=native, contract_reference={}, acceptance_probe=True, session_identity=7)
    assert proxy.protocol_planning_snapshots_v3("A") is response
    assert proxy.envelopes[-1]["api_endpoint"] == "protocol_planning_snapshots_v3" and proxy.envelopes[-1]["method"] == 10
    assert "protocol_planning_snapshots_v3" not in capture.RecentNativeTimingCapture._invoke.__globals__["API_METHODS"]
    assert gates == [True, False]
