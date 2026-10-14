"""Compare saved complete-denominator controller runs without rerunning physics."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

from .original_workload import digest, json_digest, write_json


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def compare(folders, historical_root=None):
    rows, populations = [], {}
    for folder in folders:
        receipt, summary = read_json(folder / "receipt.json"), read_json(folder / "summary.json")
        jobs = read_lines(folder / "business_results.jsonl.gz")
        events = read_lines(folder / "physical_events.jsonl.gz")
        offered = summary["offered"]
        policy = "predictive" if receipt["predictive"] else "reactive"
        key = offered, policy
        if key in populations:
            raise ValueError("duplicate population/policy; filename is not policy evidence")
        populations[key] = jobs
        event_counts = Counter(event["event"] for event in events)
        source = {Path(name).name: value for name, value in receipt["source_before"].items()}
        row = {"path": str(folder), "receipt_sha256": digest(folder / "receipt.json"),
               "policy": policy, "binary_sha256": receipt["binary_sha256"], "source": source,
               "status": receipt["status"], "source_changed": receipt["source_changed"],
               "horizon": receipt["horizon"], "summary": summary,
               "audit_status": read_json(folder / "event_audit.json")["status"],
               "actual_exports": event_counts["EXPORT_GRANTED"], "actual_received": event_counts["EMPTY_RECEIVED"],
               "transfer_rejections": event_counts["TRANSFER_REJECTED"],
               "control_compute_ms": receipt["control_compute_ms"],
               "all_business_rows_sha256": json_digest(jobs), "all_physical_rows_sha256": json_digest(events)}
        if historical_root:
            scale = 1 if offered == 28506 else 2 if offered == 57012 else None
            older = historical_root / f"p2_original_{scale}x_{policy}_H21600_001"
            if older.exists():
                old_jobs = read_lines(older / "business_results.jsonl.gz")
                old_events = read_lines(older / "physical_events.jsonl.gz")
                row["build004_comparison"] = {"path": str(older),
                    "all_business_fields_equal": old_jobs == jobs, "all_physical_fields_equal": old_events == events,
                    "business_mismatch_count": sum(a != b for a, b in zip(old_jobs, jobs)) + abs(len(old_jobs)-len(jobs))}
        rows.append(row)
    pairs = []
    for offered in sorted({key[0] for key in populations}):
        a, b = populations[(offered, "reactive")], populations[(offered, "predictive")]
        pair = [row for row in rows if row["summary"]["offered"] == offered]
        pairs.append({"offered": offered, "all_business_fields_equal": a == b,
                      "all_business_ids_equal": [r["business_bag_id"] for r in a] == [r["business_bag_id"] for r in b],
                      "same_horizon": len({row["horizon"] for row in pair}) == 1,
                      "same_binary": len({row["binary_sha256"] for row in pair}) == 1,
                      "same_sources": pair[0]["source"] == pair[1]["source"],
                      "cost_predictive_minus_reactive": next(row["summary"]["restricted_sojourn_sum_seconds_at_actual_clock"] for row in pair if row["policy"] == "predictive") - next(row["summary"]["restricted_sojourn_sum_seconds_at_actual_clock"] for row in pair if row["policy"] == "reactive")})
    return {"schema": "g31.original_control_comparison.v2", "rows": rows, "pairs": pairs,
            "all_sources_same": all(row["source"] == rows[0]["source"] for row in rows),
            "all_binary_same": len({row["binary_sha256"] for row in rows}) == 1,
            "complete_100ms_requirement_certified": False,
            "claim": "all offered source rows preserved; common observation horizon is not full-day completion; wall owner compute excludes still-unmeasured complete request components"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--historical-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.run, args.historical_root)
    write_json(args.output, result)
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}, indent=2))


if __name__ == "__main__":
    main()
