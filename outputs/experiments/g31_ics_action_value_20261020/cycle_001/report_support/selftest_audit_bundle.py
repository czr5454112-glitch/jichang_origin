"""Hand-written DUMMY-only portable auditor checks. No experiment files read."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("portable_dummy_auditor", HERE / "audit_bundle.py")
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)


def write(path, value):
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(raw, mtime=0) if path.name.endswith(".gz") else raw)


def file_entry(root, path):
    return {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size, "included": True}


def manual_cost():
    # Hand-calculated: a:(20-10)=10, b:(40-15)=25, c:(50-30)=20, d:0.
    return {"label_start": 10., "label_end": 50., "horizon_seconds": 40.,
        "backlog_integral_bag_seconds": 55., "target_return": -55., "physical_population": 4,
        "arrived_by_end": 3, "not_yet_arrived_by_end": 1, "completed_by_end": 2,
        "arrived_unfinished_by_end": 1, "on_time_by_end": 2, "arrived_unfinished_past_deadline": 1,
        "completion_times_unknown_for_arrived": 1, "completion_times_imputed": False,
        "right_censored_for_integral_only": True, "uncompleted_jobs_excluded": 0,
        "waiting_for_tray_integral_bag_seconds": 25., "loaded_or_processing_integral_bag_seconds": 30.,
        "wait_load_decomposition_status": "actual_LOAD_START_receipts", "per_job_nonharm_certified": False}


def make_dummy(root):
    root.mkdir()
    inputs = {"jobs": [
        {"business_bag_id": "DUMMY_a", "arrival": 0., "deadline": 30.},
        {"business_bag_id": "DUMMY_b", "arrival": 15., "deadline": 45.},
        {"business_bag_id": "DUMMY_c", "arrival": 30., "deadline": 45.},
        {"business_bag_id": "DUMMY_d", "arrival": 60., "deadline": 80.}]}
    rows, runs = [], []
    for name, batch, complete, times in (
        ("DUMMY_REF", "D", True, [20., 40.]),
        ("DUMMY_CAND", "G", True, [25., 35.]),
        ("DUMMY_FAILED", "E", False, None)):
        directory = root / name
        write(directory / "input.json", inputs)
        plan = {"name": name, "batch": batch, "cost_window": [10., 50.], "horizon": 50.,
                "input": {"sha256": hashlib.sha256((directory / "input.json").read_bytes()).hexdigest()},
                "binary": {"sha256": "b" * 64}}
        write(directory / "plan.json", plan)
        status = "complete" if complete else "censored_dummy_budget"
        write(directory / "receipt.json", {"status": status,
              "plan_sha256": hashlib.sha256((directory / "plan.json").read_bytes()).hexdigest()})
        run = {"name": name, "batch": batch, "status": status, "input": name + "/input.json",
               "plan": name + "/plan.json", "receipt": name + "/receipt.json"}
        if complete:
            jobs = [{"business_bag_id": j["business_bag_id"],
                     "status": "completed" if i < 2 else "waiting_for_tray" if i == 2 else "unreleased",
                     "completed_at": times[i] if i < 2 else -1.} for i, j in enumerate(inputs["jobs"])]
            receipts = [{"event": "BAG_ARRIVAL", "business_bag_id": j["business_bag_id"], "time": j["arrival"]}
                        for j in inputs["jobs"][:3]]
            receipts.extend({"event": "UNLOAD_COMPLETE", "business_bag_id": inputs["jobs"][i]["business_bag_id"],
                             "time": time} for i, time in enumerate(times))
            receipts.extend({"event": "LOAD_START", "business_bag_id": inputs["jobs"][i]["business_bag_id"],
                             "time": time} for i, time in enumerate((10., 20.)))
            write(directory / "final_result.json.gz", {"physical_clock": 50.,
                "advance": {"status": "reached", "horizon_complete": True}, "jobs": jobs,
                "receipts": receipts, "population": {"observed": 3, "completed": 2}})
            run["final_result"] = name + "/final_result.json.gz"
        runs.append(run)
        rows.append({"name": name, "batch": batch, "status": status,
                     "full_window_cost": manual_cost() if complete else None})
    comparisons = [
        {"reference": "DUMMY_REF", "candidate": "DUMMY_CAND", "status": "complete_same_resource_comparison",
         "advantage_bag_seconds": 0., "relative_advantage": 0., "completed_delta": 0, "on_time_delta": 0,
         "arrived_unfinished_past_deadline_delta": 0,
         "per_job_comparison": {"harmed": 1, "improved": 1, "unknown_incomplete": 2},
         "incomplete_comparison_breakdown": {"neither_finished": 2}, "maximum_known_delay_seconds": 5.},
        {"reference": "DUMMY_REF", "candidate": "DUMMY_FAILED", "status": "unknown_incomplete_branch",
         "advantage_bag_seconds": None}]
    write(root / "prospective_offline_review.json", {"dummy_data": True, "rows": rows, "comparisons": comparisons,
          "independent_real_airport_days": 0, "all_parents_conditional_synthetic": True})
    files = [file_entry(root, p) for p in sorted(root.rglob("*")) if p.is_file()]
    files.append({"path": "DUMMY_REF/callback_audit.jsonl.gz", "sha256": "0" * 64, "size": 1000,
                  "included": False, "kind": "callback_stream", "reason": "DUMMY absent inventory only"})
    manifest = {"schema": auditor.MANIFEST_SCHEMA, "dummy_data": True,
        "dummy_notice": "DUMMY HAND-WRITTEN UNIT DATA; NOT AIRPORT EXPERIMENT EVIDENCE",
        "dummy_contract": {"population": 4, "cost_window": [10., 50.]},
        "files": files, "runs": runs, "review": {"path": "prospective_offline_review.json"}}
    write(root / "bundle_manifest.json", manifest)


def mutate_json(root, relative, change):
    path = root / relative
    value = auditor.load_json(path)
    change(value)
    write(path, value)
    manifest = auditor.load_json(root / "bundle_manifest.json")
    for entry in manifest["files"]:
        if entry["path"] == relative:
            entry.update(file_entry(root, path))
    write(root / "bundle_manifest.json", manifest)


def main():
    output = HERE.parent / "DUMMY_portable_audit_selftest_001"
    if output.exists():
        raise ValueError("fresh DUMMY selftest directory required")
    output.mkdir()
    base = output / "valid_dummy_bundle"
    make_dummy(base)
    result = auditor.audit(base, dummy_test=True)
    assert result["runs"][0]["full_window_cost"]["backlog_integral_bag_seconds"] == 55.
    assert result["comparisons"][0]["per_job_comparison"]["unknown_incomplete"] == 2
    assert not result["full_callback_stream_coverage_claimed"]
    write(output / "DUMMY_valid_audit.json", result)
    cases = [
        ("wrong_file_hash", lambda r: (r / "DUMMY_REF/input.json").write_bytes(b"tampered")),
        ("saved_wrong_cost", lambda r: mutate_json(r, "prospective_offline_review.json",
            lambda v: v["rows"][0]["full_window_cost"].update(backlog_integral_bag_seconds=56.))),
        ("incomplete_benefit", lambda r: mutate_json(r, "prospective_offline_review.json",
            lambda v: v["comparisons"][1].update(advantage_bag_seconds=1.))),
        ("incomplete_cost", lambda r: mutate_json(r, "prospective_offline_review.json",
            lambda v: v["rows"][2].update(full_window_cost=manual_cost()))),
        ("unknown_removed", lambda r: mutate_json(r, "prospective_offline_review.json",
            lambda v: v["comparisons"][0]["per_job_comparison"].update(unknown_incomplete=0, equal=2))),
        ("missing_job", lambda r: mutate_json(r, "DUMMY_REF/final_result.json.gz", lambda v: v["jobs"].pop())),
        ("missing_arrival", lambda r: mutate_json(r, "DUMMY_REF/final_result.json.gz",
            lambda v: v["receipts"].pop(2))),
        ("duplicate_completion", lambda r: mutate_json(r, "DUMMY_REF/final_result.json.gz",
            lambda v: v["receipts"].append(copy.deepcopy(v["receipts"][3])))),
        ("included_missing_callback", lambda r: mutate_json(r, "bundle_manifest.json",
            lambda v: v["files"][-1].update(included=True))),
        ("unsafe_path", lambda r: mutate_json(r, "bundle_manifest.json",
            lambda v: v["files"].append({"path": "../escape", "included": False, "sha256": "0" * 64}))),
    ]
    checks = [{"name": "valid_hand_calculated_full_population", "passed": True}]
    for name, mutate in cases:
        directory = output / name
        shutil.copytree(base, directory)
        mutate(directory)
        try:
            auditor.audit(directory, dummy_test=True)
        except ValueError as error:
            checks.append({"name": name, "passed": True, "rejection": str(error)})
        else:
            raise AssertionError("Expected fail-closed: " + name)
    try:
        auditor.audit(base, dummy_test=False)
    except ValueError as error:
        checks.append({"name": "dummy_cannot_pass_production", "passed": True, "rejection": str(error)})
    else:
        raise AssertionError("DUMMY data passed production mode")
    write(output / "DUMMY_selftest_receipt.json", {"dummy_only": True,
        "notice": "HAND-WRITTEN FOUR-JOB SELFTEST; NO REAL EXPERIMENT OR TEST DATA OPENED",
        "passed": len(checks), "checks": checks, "native_started": 0, "models_fit": 0,
        "auditor_sha256": hashlib.sha256((HERE / "audit_bundle.py").read_bytes()).hexdigest()})
    print(json.dumps({"dummy_only": True, "passed": len(checks), "output": str(output)}))


if __name__ == "__main__":
    main()
