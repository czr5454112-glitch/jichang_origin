"""Limited independent review of a completed saved-horizon audit.

Rechecks small evidence, the input and exactly the final raw shard. Does not
repeat the all-shard audit or claim a new native state-seal reconstruction.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def ref(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def review(report_path, preparation, directory):
    report_path, preparation, directory = map(Path, (report_path, preparation, directory))
    report = read(report_path)
    bounded = read(preparation / "bounded_execution.json")
    prepared = read(preparation / "preparation.json")
    assert bounded["status"] == "process_exited" and bounded["exit_code"] == 0
    assert bounded["audit_sha256"] == sha(report_path)
    assert bounded["prepared_plan_sha256"] == sha(preparation / "preparation.json")
    assert bounded["launcher_sha256"] == sha(preparation / "bounded_launch.py")
    assert report["audit_wall_seconds"] <= bounded["wall_seconds"] < bounded["hard_timeout_seconds"] == 1800
    args = bounded["command"]
    value = lambda name: args[args.index(name) + 1]
    assert (ROOT / value("--directory")).resolve() == directory.resolve()
    assert (ROOT / value("--output")).resolve() == report_path.resolve()
    assert int(value("--expected-total")) == report["offered"] == 28506
    assert float(value("--horizon")) == report["physical_horizon_completed"] == 86400.
    assert value("--expected-final-seal") == report["native_state_sha256"]
    assert report["status"] == "passed_saved_physical_horizon"
    assert report["producer_summary_present"] is True
    assert report["producer_receipt_status"] == "hard_timeout" and report["producer_process_success"] is False

    evidence = {}
    for name, digest in report["evidence_sha256"].items():
        if Path(name).parts[0] == "segments":
            continue
        path = directory / name
        assert sha(path) == digest
        evidence[name] = digest
    receipt = read(directory / "receipt.json")
    summary = read(directory / "summary.json")
    manifest = read(directory / "run_shards.json")
    assert receipt["status"] == "hard_timeout" and receipt["source_changed"] == []
    assert manifest["status"] == manifest["last_shard_status"] == "reached"
    assert manifest["all_raw_records_retained"] is True
    rows = manifest["shards"]
    assert len(rows) == len(manifest["segments"]) == 451
    assert {r["path"] for r in rows} == {str(p.relative_to(directory)) for p in (directory / "segments").glob("*.json.gz")}
    assert all(r["sha256"] == report["evidence_sha256"][r["path"]] for r in rows)
    assert {k: sum(r["counts"][k] for r in rows) for k in manifest["counts"]} == manifest["counts"] == report["counts"]
    assert manifest["final_state_shard"] == rows[-1]["path"] == "segments\\0450.json.gz"
    final_path = directory / rows[-1]["path"]
    assert sha(final_path) == rows[-1]["sha256"]
    final = read(final_path)
    state, result = final["controller_state"], final["result"]
    assert final["status"] == "reached" and state["native_timestamp_complete"] is True
    assert not state["pending_owners"] and not state["pending_causes"] and not state["needs_native_drain"]
    assert result["advance"]["status"] == "reached" and result["advance"]["horizon_complete"] is True
    assert result["physical_clock"] == result["horizon"] == result["advance"]["physical_time"] == 86400.
    assert final["native_batches"][-1]["timestamp_complete"] is True
    assert final["native_batches"][-1]["status"] == "horizon_reached"
    assert final["native_state_sha256"] == report["native_state_sha256"] == summary["native_state_sha256"]
    evidence[rows[-1]["path"]] = sha(final_path)

    data = read(directory / "input.json.gz")
    assert len(data["jobs"]) == len(result["jobs"]) == len(summary["metrics"]["per_job"]) == 28506
    ids = [j["business_bag_id"] for j in data["jobs"]]
    assert len(set(ids)) == 28506
    assert ids == [j["business_bag_id"] for j in result["jobs"]] == [j["business_bag_id"] for j in summary["metrics"]["per_job"]]
    completed = sum(j["completed_at"] >= 0 for j in result["jobs"])
    strict = sum(j["deadline"] >= 0 and (r["completed_at"] if r["completed_at"] >= 0 else 86400.) > j["deadline"]
                 for j, r in zip(data["jobs"], result["jobs"], strict=True))
    summary_late = sum(j["deadline"] >= 0 and (r["completed_at"] if r["completed_at"] >= 0 else 86400.) > j["deadline"] + 1e-8
                       for j, r in zip(data["jobs"], result["jobs"], strict=True))
    assert completed == report["completed"] == summary["metrics"]["completed"] == 0
    assert strict == report["strict_deadline_violations_by_horizon"] == 28506
    assert summary_late == summary["metrics"]["deadline_violations"] == strict
    assert dict(Counter(j["status"] for j in result["jobs"])) == report["business_status_counts"] == summary["business_status_counts"]
    assert report["physical_audit"] == summary["audit"]
    assert report["physical_audit"]["status"] == "passed"
    assert report["physical_audit"]["completed_traversals"] == 238 and report["physical_audit"]["open_traversals"] == 0
    assert len(result["trays"]) == len(data["trays"]) == report["tray_count"] == 22
    assert summary["tray_mode_counts"] == dict(Counter(t["mode"] for t in result["trays"]))

    for relative, digest in report["source_archive_sha256"].items():
        assert sha(ROOT / relative) == sha(directory / "source_archive" / relative) == digest
    for relative, digest in report["auditor_sources_sha256"].items():
        assert sha(ROOT / relative) == digest
    for name, digest in prepared["source_sha256"].items():
        path = Path(name)
        if not path.is_absolute():
            path = ROOT / path
        assert sha(path) == sha(preparation / "source" / path.relative_to(ROOT)) == digest

    assert report["summary_deadline_tolerance"] == 1e-8
    assert report["unpaired_zero_regression_certified"] is False
    assert report["complete_request_100ms_certified"] is False
    return {
        "schema": "g31.saved_horizon_limited_independent_review.v1", "status": "passed_limited_evidence_review",
        "created_utc": datetime.now(timezone.utc).isoformat(), "review_source": ref(__file__),
        "audit_report": ref(report_path), "bounded_execution": ref(preparation / "bounded_execution.json"),
        "preparation": ref(preparation / "preparation.json"), "checked_small_and_final_evidence": evidence,
        "source_counts": {"producer": len(report["source_archive_sha256"]), "auditor": len(report["auditor_sources_sha256"]),
                          "prepared": len(prepared["source_sha256"])},
        "manifest_parts": 451, "decoded_raw_shards": [rows[-1]["path"]], "new_native_executions": 0,
        "new_native_seal_replay": False, "producer_receipt_still_hard_timeout": True,
        "producer_summary_present_and_hash_verified": True,
        "business": {"offered": 28506, "completed": 0, "unfinished": 28506, "strict_deadline_violations": strict,
                     "legacy_summary_tolerance_deadline_violations": summary_late},
        "physical_audit_saved_result": report["physical_audit"], "tray_modes": summary["tray_mode_counts"],
        "findings": [
            "The bounded saved-file auditor exited0 within1800s. Its output hash matches the bounded receipt.",
            "Producer summary.json really exists, has the pinned hash and agrees with final raw facts; its creation did not make the producer process successful.",
            "The451-entry manifest and all saved per-shard hashes/counts agree with the report; only final0450 was rehashed and decoded in this limited review.",
            "Final timestamp is fully drained. All28506 identities remain present;0businesses completed and all28506 violate their strict deadline byH86400.",
            "Physical-audit passed means the stated identity/lifecycle/edge/headway/parked-incoming-reception capacity replay passed. It is not business success, optimality or a fresh native hidden-state proof.",
            "The1e-8 field documents legacy summary deadline classification only. Strict deadline counting uses>deadline without tolerance. No paired protection is established; future per-job protection must enforce delta<=0 with noepsilon.",
        ],
        "limitations": [
            "Did not rehash/decompress all3GiB history or rerun the complete physical auditor; relies on the source-bound completed saved-file audit for intermediate traces and full physical replay.",
            "Intermediate controller-state objects were opaque byte-bound subtrees in the first audit, as explicitly stated there.",
            "The final native seal remains producer-reported; no new NativeSession or seal reconstruction was executed.",
            "No complete-request100ms, paired zero-regression, deadlock-freedom or business-success claim.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = review(args.report, args.preparation, args.directory)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": ref(args.output), "status": result["status"], "business": result["business"]}))


if __name__ == "__main__":
    main()
