"""Small saved-report review. Does not decode native tapes or run a session."""
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
read = lambda path: json.loads(Path(path).read_text(encoding="utf8"))
report_path = OUT / "route_native027_saved_audit_001/audit/report.json"
bounded_path = OUT / "route_native027_saved_audit_001/bounded_execution.json"
external_path = OUT / "route_native027_saved_audit_prepare_001/external_application_wall.json"
old_external_path = OUT / "original_route_native027_phase_prepare_002/powershell_launch_receipt.json"
old_inner_path = old_external_path.with_name("external_launch_receipt.json")
report, bounded, external, old_external, old_inner = map(read,
    (report_path, bounded_path, external_path, old_external_path, old_inner_path))
assert sha(report_path) == "fbb2cff19d93a02416aa54067d98ec714c901cd600fa447242f3ee3b2481cae7"
assert report["status"] == "passed_saved_six_cell_audit_after_original_timeout"
assert report["native_executions"] == bounded["native_executions"] == external["native_executions"] == 0
assert bounded["process"]["exitcode"] == external["exit_code"] == 0
assert bounded["process"]["windows_job_kill_on_close"] and bounded["hard_limit_seconds"] == 1800.
assert external["changed"] == [] and external["elapsed_seconds"] < 1800.
for path, digest in bounded["artifacts"].items():
    assert sha(bounded_path.parent / path) == digest
assert old_inner["process"]["status"] == "hard_timeout" and old_inner["process"]["windows_job_kill_on_close"]
assert old_external["status"] == "application_failed_or_unknown" and old_external["exit_code"] != 0
assert old_external["evidence_identities_unchanged"] and report["original_timeout_preserved"]
assert report["original_external_receipt_sha256"] == sha(old_inner_path)
assert report["declared_roots"] == 6 and report["closed_roots"] == 4 and report["open_roots"] == 2
assert not report["complete_computation_available"] and not report["complete_100ms_certified"]
assert report["physics_subtracted_ns"] == 0
cases = {}
for name, case in report["cases"].items():
    result = {k: case[k] for k in ("status", "attempts", "request_api_rows", "native_call_count_within_root",
        "whole_child_wall_seconds", "producer_native_seal")}
    result["warm_elapsed_ms"] = case.get("warm_elapsed_upper_ms", case.get("warm_elapsed_prefix_ms"))
    result["closed"] = case["status"] == "closed_finite_request"
    phase = case["phase_diagnostics"]
    if phase["status"] != "disabled":
        assert phase["partition_exact"] and phase["physics_subtracted_ns"] == 0
        components = ("root_native_envelope_ns", "root_python_request_service_remainder_ns", "root_other_unclassified_ns")
        assert sum(phase[key] for key in components) == phase["root_total_ns"]
        result["conserved_root_partition_ms"] = {key.removesuffix("_ns"): phase[key]/1e6 for key in components}
        result["measured_request_invocation_max_ms"] = phase["max_request_service_invocation_ns"]/1e6
        result["python_nested_bundles_ms_not_additive_to_partition"] = {
            key: value/1e6 for key, value in phase["python_exclusive_bundles_including_nested_native_ns"].items()}
    cases[name] = result
previous = 0.
stages = []
for row in report["stages"]:
    stages.append({**row, "stage_increment_seconds": row["elapsed_seconds"]-previous})
    previous = row["elapsed_seconds"]
result = {"schema": "g31.route_phase.saved_audit_report_review.v1", "status": "passed_report_and_bounded_evidence_binding",
    "source": {str(Path(__file__).resolve()): sha(__file__)},
    "evidence": {str(p): sha(p) for p in (report_path, bounded_path, external_path, old_external_path, old_inner_path)},
    "review_scope": "Read final report and bounded/external receipts, rehash reported audit outputs. Does not repeat all large raw tape decoding or create a new native state seal.",
    "native_executions": 0, "closed_roots": 4, "open_roots": 2, "cases": cases,
    "exact_plain_timed_semantic_parity": report["parity"],
    "original_campaign": {"status": old_inner["status"], "process_status": old_inner["process"]["status"],
        "full_python_application_wall_seconds": old_external["whole_application_campaign_wall_seconds"],
        "full_charge_policy": old_external["full_charge_policy"], "exclusions": old_external["exclusions"],
        "successful_campaign_completion_claim": False},
    "separate_saved_audit": {"external_python_application_wall_seconds": external["elapsed_seconds"],
        "inner_pre_final_export_dispatch_seconds": bounded["whole_dispatch_wall_seconds"],
        "child_audit_seconds": report["audit_wall_seconds"], "scope": external["external_wall_scope"], "stages": stages},
    "interpretation": [
        "Original six native workers exited zero; original shared600s campaign timed out during saved verification and remains failed/unknown.",
        "New1800s pure audit passes all unchanged guards and exact ordered comparisons; it is separate research verification cost.",
        "Native labels are broad bundles, not exemptions. All shared/background work and unclassified remainder remain charged.",
        "The measured service maximum concerns request invocations only, not all executor/background services.",
        "Timed versus plain instrumentation changes measured durations; this serial pair with concurrent work does not prove stable overhead or speedup.",
        "Pending-ACK observation removal targets part of the measured request service; it cannot explain or remove the open case's28.3421723s unclassified remainder without new evidence."],
    "complete_computation_available": False, "complete_100ms_certified": False, "physics_subtracted_ns": 0}
destination = OUT / "route_native027_saved_audit_001/report_review_001.json"
assert not destination.exists()
destination.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf8")
print(json.dumps({"path": str(destination), "sha256": sha(destination), "status": result["status"]}))
