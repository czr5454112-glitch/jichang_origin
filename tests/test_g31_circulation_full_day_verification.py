"""A full clock, complete business, and complete request are separate claims."""
from copy import deepcopy
import gzip
import hashlib
import json

import pytest

from scripts.experiments.g31_ics_circulation.verify_full_day import (
    business_counts, command_option, verify, verify_input_provenance,
)
from scripts.experiments.g31_ics_circulation.validate_protocol_control import scenarios
from scripts.experiments.g31_ics_circulation.finite_reference import outcome_cost
from scripts.experiments.g31_ics_circulation.native_host import audit_result
from scripts.experiments.g31_ics_circulation import verify_full_day as verifier


def sample():
    data = {"jobs": [{"business_bag_id": "a", "arrival": 1., "deadline": 3.},
                     {"business_bag_id": "b", "arrival": 2., "deadline": 9.}]}
    result = {"jobs": [{"business_bag_id": "a", "completed_at": 3., "status": "completed"},
                       {"business_bag_id": "b", "completed_at": -1., "status": "waiting"}]}
    return data, result


def test_full_input_retains_unfinished_and_does_not_infer_zero_regression():
    data, result = sample()
    report = business_counts(data, result, 10., 2)
    assert report["offered"] == 2 and report["completed"] == 1 and report["unfinished"] == 1
    assert report["restricted_arrival_to_unload_cost"] == 10.
    assert report["strict_deadline_violations_by_horizon"] == 1
    assert not report["all_business_completed"] and not report["unpaired_zero_regression_certified"]
    result["jobs"][0]["completed_at"] += 1e-12
    assert business_counts(data, result, 10., 2)["strict_deadline_violations_by_horizon"] == 2


@pytest.mark.parametrize("defect", ["missing", "duplicate", "extra", "before_arrival", "future", "future_arrival", "nonfinite", "false_completed"])
def test_business_denominator_and_completion_facts_fail_closed(defect):
    data, result = sample()
    if defect == "missing": result["jobs"].pop()
    elif defect == "duplicate": result["jobs"].append(deepcopy(result["jobs"][0]))
    elif defect == "extra": result["jobs"].append(dict(result["jobs"][0], business_bag_id="extra"))
    elif defect == "before_arrival": result["jobs"][0]["completed_at"] = .5
    elif defect == "future": result["jobs"][0]["completed_at"] = 11.
    elif defect == "future_arrival": data["jobs"][0]["arrival"] = 11.
    elif defect == "nonfinite": result["jobs"][0]["completed_at"] = float("nan")
    else: result["jobs"][1]["status"] = "completed"
    with pytest.raises(ValueError, match="full_day:"):
        business_counts(data, result, 10., 2)


@pytest.mark.parametrize("defect", ["worker_timeout", "source_drift", "physical_prefix", "future_inputs", "null_metrics", "unreached"])
def test_censored_execution_is_rejected_before_reading_missing_raw_data(tmp_path, defect):
    receipt = {"status": "completed", "exit_code": 0, "source_changed": []}
    summary = {"status": "reached", "physical_time": 86400., "horizon": 86400.,
               "offered_total": 28506, "offered_by_current_time": 28506,
               "all_input_arrivals_observed": True, "metrics": {"completed": 0}}
    manifest = {"status": "reached", "all_raw_records_retained": True}
    if defect == "worker_timeout": receipt["status"] = "hard_timeout"
    elif defect == "source_drift": receipt["source_changed"] = ["controller.py"]
    elif defect == "physical_prefix": summary["physical_time"] = 22000.
    elif defect == "future_inputs": summary["offered_by_current_time"] = 4000
    elif defect == "null_metrics": summary["metrics"] = None
    else: manifest["status"] = "control_budget_exhausted"
    for name, value in (("receipt.json", receipt), ("summary.json", summary), ("run_shards.json", manifest)):
        (tmp_path / name).write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="full_day:"):
        verify(tmp_path, 28506, 86400.)


def test_offered_input_verification_uses_all_fields_not_only_count(tmp_path):
    _, original, _ = scenarios()[1]
    original["owner_notifications"] = {"enabled": True}
    receipt = {"command": ["worker", "--suite", "synthetic", "--horizon", "50"]}
    report = verify_input_provenance(tmp_path, original, receipt, len(original["jobs"]), 50.)
    assert report["new_native_executions"] == 0
    for change in ("identity", "permission", "notification"):
        altered = deepcopy(original)
        if change == "identity": altered["jobs"][0]["business_bag_id"] += ":substituted"
        elif change == "permission": altered["jobs"][0]["allow_suffix_reroute"] = not altered["jobs"][0].get("allow_suffix_reroute", False)
        else: altered["owner_notifications"]["enabled"] = False
        assert len(altered["jobs"]) == len(original["jobs"])
        with pytest.raises(ValueError, match="offered_input_changed"):
            verify_input_provenance(tmp_path, altered, receipt, len(original["jobs"]), 50.)


@pytest.mark.parametrize("command", [["worker"], ["worker", "--suite"],
                                    ["--suite", "synthetic", "--suite", "full1x"]])
def test_input_provenance_rejects_ambiguous_invocation(command):
    with pytest.raises(ValueError, match="missing_or_duplicate_command_option"):
        command_option({"command": command}, "--suite")


def complete_fixture(tmp_path, monkeypatch):
    """Handwritten evidence for verifier tests; never presented as a native run."""
    _, data, _ = scenarios()[1]
    data["owner_notifications"] = {"enabled": True}
    continuation = {"status": "reached", "requested_horizon": 50., "physical_time": 50.}
    result = {"mode": "circulation", "physical_clock": 50., "horizon": 50.,
        "advance": {"status": "reached", "horizon_complete": True, "physical_time": 50.},
        "control_continuation": deepcopy(continuation), "receipts": [], "leg_identities": [], "decisions": [],
        "native_summary": {"reservation_conflicts": 0, "physical_fault_edge_entry_violation_count": 0},
        "trays": [dict(t, mode="empty", edge_to=-1) for t in data["trays"]],
        "jobs": [dict(business_bag_id=j["business_bag_id"], status="waiting", completed_at=-1.,
                      loaded_at=-1., storage_entered_at=-1., storage_released_at=-1.) for j in data["jobs"]],
        "population": {"offered_by_horizon": 2, "observed": 2, "loaded": 0, "completed": 0}}
    payload = {"request_id": "one", "owner_id": "A", "target_owner": "B", "kind": "demand"}
    calls = [{"at": t, "retry": retry, "kind": "demand", "request": deepcopy(payload),
              "reply": {"status": "pending"}} for t, retry in ((0., False), (50., True))]
    part = {"status": "reached", "control_continuation": continuation, "result": result,
        "control_records": [{"trace_sequence": seq, "owner_id": "A", "at": t, "compute_wall_ms": 1.}
                            for seq, t in ((0, 0.), (2, 50.))],
        "native_batches": [{"trace_sequence": seq, "start_at": start, "end_at": 50.,
                            "status": "horizon_reached", "timestamp_complete": True}
                           for seq, start in ((1, 0.), (3, 50.))],
        "client_calls": calls, "controller_state": {"start": 0., "native_timestamp_complete": True,
            "pending_owners": [], "pending_causes": {}, "needs_native_drain": False,
            "client": {"outbox": {"one": {"payload": deepcopy(payload), "kind": "demand", "created_at": 0.,
                "submission_reply": {"status": "pending"}, "terminal": False}}}}}
    binary = tmp_path / "test_binary_not_native.bin"
    binary.write_bytes(b"test-only; never loaded")
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    receipt = {"status": "completed", "exit_code": 0, "source_changed": [], "binary_sha256": digest,
        "command": ["worker", "--suite", "synthetic", "--horizon", "50", "--binary", binary.name]}
    summary = {"status": "reached", "physical_time": 50., "horizon": 50., "offered_total": 2,
        "offered_by_current_time": 2, "all_input_arrivals_observed": True, "owner_activations": 2,
        "wall_seconds": 1., "native_sha256": digest, "native_state_sha256": "a" * 64,
        "metrics": outcome_cost(result, data["jobs"], 50.), "audit": audit_result(data, result),
        "business_status_counts": {"waiting": 2}, "tray_mode_counts": {"empty": 1},
        "timing": {"request_count": 1, "attempt_count": 2}}
    counts = {key: len(part[key]) for key in ("control_records", "native_batches", "client_calls")}
    manifest = {"status": "reached", "last_shard_status": "reached", "all_raw_records_retained": True,
        "wall_seconds": 1., "counts": deepcopy(counts), "final_state_shard": "segments/0000.json.gz",
        "shards": [{"path": "segments/0000.json.gz", "counts": counts, "status": "reached", "physical_time": 50.}],
        "segments": [{"status": "reached", "physical_time": 50., "horizon": 50., "cumulative_control_wall_seconds": 1.}]}
    return {"receipt": receipt, "summary": summary, "manifest": manifest, "part": part,
            "input": data, "offline": {"now": 50.}}


def write_fixture(path, fixture):
    def gz(name, value):
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(target, "wt", encoding="utf-8") as stream:
            json.dump(value, stream)
        return hashlib.sha256(target.read_bytes()).hexdigest()
    digest = gz("segments/0000.json.gz", fixture["part"])
    fixture["manifest"]["shards"][0]["sha256"] = digest
    gz("input.json.gz", fixture["input"])
    gz("native_offline_diagnostics.json.gz", fixture["offline"])
    for name, key in (("receipt", "receipt"), ("summary", "summary"), ("run_shards", "manifest")):
        (path / f"{name}.json").write_text(json.dumps(fixture[key]), encoding="utf-8")


def test_complete_physical_execution_keeps_all_unfinished_business(tmp_path, monkeypatch):
    fixture = complete_fixture(tmp_path, monkeypatch)
    write_fixture(tmp_path, fixture)
    report = verify(tmp_path, 2, 50.)
    assert report["status"] == "passed" and report["unfinished"] == 2
    assert report["retry_attempt_count"] == 1 and report["open_protocol_request_count"] == 1
    assert report["native_state_seal_validation"].startswith("producer-reported")
    assert report["complete_request_100ms_certified"] is False


@pytest.mark.parametrize("defect", [
    "retry_before_creation", "duplicate_creation", "mutated_retry", "outbox_payload", "outbox_created_at",
    "outbox_reply", "clock_gap", "trace_reordered", "trace_duplicate", "call_without_activation", "call_kind",
    "final_clock", "final_result_horizon", "final_continuation", "pending_cause", "last_boundary_incomplete",
    "last_boundary_not_horizon", "manifest_status", "manifest_clock", "segment_clock", "missing_segment",
    "summary_per_job", "summary_status_counts", "summary_tray_modes", "summary_attempt_count", "summary_wall",
    "offline_clock", "population_observed", "population_completed", "business_order", "missing_creation",
    "future_receipt", "future_stage", "invalid_seal",
])
def test_complete_audit_rejects_inconsistent_raw_and_summary_evidence(tmp_path, monkeypatch, defect):
    f = complete_fixture(tmp_path, monkeypatch)
    part, manifest, summary = f["part"], f["manifest"], f["summary"]
    calls, result = part["client_calls"], part["result"]
    outbox = part["controller_state"]["client"]["outbox"]["one"]
    if defect == "retry_before_creation": calls[0]["retry"], calls[1]["retry"] = True, False
    elif defect == "duplicate_creation": calls[1]["retry"] = False
    elif defect == "mutated_retry": calls[1]["request"]["target_owner"] = "C"
    elif defect == "outbox_payload": outbox["payload"]["target_owner"] = "C"
    elif defect == "outbox_created_at": outbox["created_at"] = 1.
    elif defect == "outbox_reply": outbox["submission_reply"] = {"status": "rejected"}
    elif defect == "clock_gap": part["native_batches"][0]["start_at"] = 1.
    elif defect == "trace_reordered": part["control_records"].reverse()
    elif defect == "trace_duplicate": part["control_records"][1]["trace_sequence"] = 0
    elif defect == "call_without_activation": calls[1]["at"] = 49.
    elif defect == "call_kind": calls[1]["kind"] = "transfer"
    elif defect == "final_clock": result["physical_clock"] = 49.
    elif defect == "final_result_horizon": result["horizon"] = 49.
    elif defect == "final_continuation": result["control_continuation"]["status"] = "control_budget_exhausted"
    elif defect == "pending_cause": part["controller_state"]["pending_causes"] = {"A": {"periodic": True}}
    elif defect == "last_boundary_incomplete": part["native_batches"][-1]["timestamp_complete"] = False
    elif defect == "last_boundary_not_horizon": part["native_batches"][-1]["status"] = "notified"
    elif defect == "manifest_status": manifest["last_shard_status"] = "control_budget_exhausted"
    elif defect == "manifest_clock": manifest["shards"][0]["physical_time"] = 49.
    elif defect == "segment_clock": manifest["segments"][0]["physical_time"] = 49.
    elif defect == "missing_segment": manifest["segments"].clear()
    elif defect == "summary_per_job": summary["metrics"]["per_job"][0]["completed_at"] = 10.
    elif defect == "summary_status_counts": summary["business_status_counts"] = {"completed": 2}
    elif defect == "summary_tray_modes": summary["tray_mode_counts"] = {"quarantined": 1}
    elif defect == "summary_attempt_count": summary["timing"]["attempt_count"] = 1
    elif defect == "summary_wall": summary["wall_seconds"] = 2.
    elif defect == "offline_clock": f["offline"]["now"] = 49.
    elif defect == "population_observed": result["population"]["observed"] = 1
    elif defect == "population_completed": result["population"]["completed"] = 1
    elif defect == "business_order": result["jobs"].reverse()
    elif defect == "missing_creation": calls[0]["retry"] = True
    elif defect == "future_receipt": result["receipts"].append({"time": 51.})
    elif defect == "future_stage": result["jobs"][0]["storage_released_at"] = 51.
    elif defect == "invalid_seal": summary["native_state_sha256"] = "unknown"
    write_fixture(tmp_path, f)
    with pytest.raises(ValueError, match="full_day:"):
        verify(tmp_path, 2, 50.)


@pytest.mark.parametrize("defect", ["hash", "outside", "duplicate"])
def test_manifest_path_and_hash_guards(tmp_path, monkeypatch, defect):
    f = complete_fixture(tmp_path, monkeypatch)
    write_fixture(tmp_path, f)
    manifest = f["manifest"]
    if defect == "hash": manifest["shards"][0]["sha256"] = "0" * 64
    elif defect == "outside": manifest["shards"][0]["path"] = "../outside.json.gz"
    else:
        manifest["shards"].append(deepcopy(manifest["shards"][0]))
        manifest["segments"].append(deepcopy(manifest["segments"][0]))
    (tmp_path / "run_shards.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="shard_path_or_hash_mismatch"):
        verify(tmp_path, 2, 50.)


@pytest.mark.parametrize("field,value", [("deadline", float("nan")), ("deadline", float("inf")),
                                         ("completed_at", -2.)])
def test_invalid_deadline_and_completion_sentinel_fail_closed(field, value):
    data, result = sample()
    (data["jobs"][0] if field == "deadline" else result["jobs"][1])[field] = value
    with pytest.raises(ValueError, match="invalid_arrival_or_completion"):
        business_counts(data, result, 10., 2)


def test_manifest_cannot_omit_a_saved_raw_shard(tmp_path, monkeypatch):
    f = complete_fixture(tmp_path, monkeypatch)
    write_fixture(tmp_path, f)
    with gzip.open(tmp_path / "segments" / "0001.json.gz", "wt", encoding="utf-8") as stream:
        json.dump({"control_records": [], "native_batches": [], "client_calls": []}, stream)
    with pytest.raises(ValueError, match="manifest_denominator_mismatch"):
        verify(tmp_path, 2, 50.)


def test_strict_deadline_count_does_not_adopt_summary_tolerance():
    data, result = sample()
    result["jobs"][0]["completed_at"] = data["jobs"][0]["deadline"] + 1e-12
    legacy = outcome_cost(result, data["jobs"], 10.)
    strict = business_counts(data, result, 10., 2)
    assert legacy["deadline_violations"] == 1
    assert strict["strict_deadline_violations_by_horizon"] == 2
