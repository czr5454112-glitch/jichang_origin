"""Read-only, source-bound summary of the six saved notification cells.

No NativeSession is constructed. The existing closed verifier replays every
saved public API response before this module derives counts and timing ranges.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from . import run_original_notification_probe as campaign
from . import verify_original_notification_probe as verifier


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha(path)}


def range_or_none(values):
    return {"minimum": min(values), "maximum": max(values)} if values else None


def summarize(directory):
    directory = Path(directory).resolve()
    source_before = {str(p.resolve()): sha(p) for p in (*campaign.source_paths(), Path(__file__))}
    verified = verifier.verify_saved(directory)
    evidence = {str(p.relative_to(directory)): sha(p) for p in directory.rglob("*")
                if p.is_file() and "source" not in p.relative_to(directory).parts}
    cells = {}
    for case in campaign.CASES:
        for arm in campaign.ARMS:
            key = case + "/" + arm
            cell = directory / case / arm
            raw = campaign.read(cell / "raw.json.gz")
            checked = verified["cases"][case][arm]
            rows = [row for item in raw["chunks"]
                    for row in campaign.read(cell / item["path"])["service_tape"]]
            rows.extend(raw["unflushed_service_tape"])
            roots, operations = (raw["ledger"][k] for k in ("roots", "operations"))
            root_rows = {}
            for identity, root in roots.items():
                out = root["output"]
                bound = checked["roots"][identity]
                endpoint = out["wall_ns"] if out else raw["ended_ns"]
                lifetime = endpoint - root["accepted_wall_ns"]
                assert bound["known_prefix_upper_ns"] == lifetime + checked["mandatory_setup_ns"]
                root_rows[identity] = {
                    "closed": out is not None,
                    "disposition": out["disposition"] if out else None,
                    "operation_ids": root["operations"],
                    "pending_terminal_ack_ids": [i for i in root["operations"] if operations[i]["ack"] is None],
                    "measured_lifetime_without_setup_ns": lifetime,
                    "known_prefix_upper_with_full_setup_ns": bound["known_prefix_upper_ns"],
                    "complete_operation_upper_with_full_setup_ns": bound["complete_operation_upper_ns"],
                    "complete_operation_compute_lower_ns": None,
                    "affected_job_scope_verified": False,
                    "job_children": sorted(bound["job_children"]),
                }
            closed = [r for r in root_rows.values() if r["closed"]]
            open_rows = [r for r in root_rows.values() if not r["closed"]]
            assert len(closed) == checked["closed_count"]
            phase = checked.get("native_phase_partition")
            if phase:
                assert phase["runtime_accepted"] is True
                assert (phase["identified_control_bundle_ns"] + phase["unclassified_native_remainder_ns"]
                        + phase["python_binding_remainder_ns"] == phase["unchanged_whole_native_envelope_ns"])
            cells[key] = {
                "status": raw["status"], "physical_time": raw["physical_time"],
                "source_offered_jobs": raw["source_offered_jobs"],
                "admitted_notification_boundaries": raw["admitted_notification_boundaries"],
                "root_count": len(root_rows), "closed_count": len(closed), "open_count": len(open_rows),
                "job_child_count": checked["job_child_count"],
                "closed_dispositions": dict(Counter(r["disposition"] for r in closed)),
                "mandatory_setup_wall_ns": checked["mandatory_setup_ns"],
                "diagnostic_capture_setup_included_ns": checked["diagnostic_capture_setup_ns"],
                "closed_complete_upper_with_full_setup_ns": range_or_none(
                    [r["complete_operation_upper_with_full_setup_ns"] for r in closed]),
                "open_known_prefix_upper_with_full_setup_ns": range_or_none(
                    [r["known_prefix_upper_with_full_setup_ns"] for r in open_rows]),
                "complete_compute_lower_bound_available": False,
                "whole_worker_process_upper_ns": checked["whole_worker_process_upper_ns"],
                "engine_wall_ns": raw["ended_ns"] - raw["engine_start_ns"],
                "service_call_count": len(rows),
                "service_endpoint_counts": dict(Counter(r["endpoint"] for r in rows)),
                "operation_count": len(operations),
                "operation_kind_counts": dict(Counter(o["kind"] for o in operations.values())),
                "immutable_submission_attempts": sum(len(o["attempts"]) for o in operations.values()),
                "extra_retry_attempts": sum(len(o["attempts"]) - 1 for o in operations.values()),
                "operation_terminal_ack_count": sum(o["ack"] is not None for o in operations.values()),
                "native_phase_partition": phase,
                "roots": root_rows,
                "original_business_request_100ms_certified": False,
            }
    assert len(cells) == 6
    assert all(sha(Path(path)) == digest for path, digest in source_before.items())
    assert all(sha(directory / name) == digest for name, digest in evidence.items())
    return {
        "schema": "g31.original_notification_independent_saved_summary.v1",
        "status": "verified_saved_six_cell_summary",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "campaign": str(directory), "receipt": reference(directory / "receipt.json"),
        "plan": reference(directory / "plan.json"), "source_sha256": source_before,
        "evidence_sha256": evidence, "cells": cells,
        "independent_verifier_status": verified["status"],
        "plain_timed_public_tapes_and_final_native_seals_equal": True,
        "reviewer_native_executions": 0,
        "root_totals": {"admitted": sum(c["root_count"] for c in cells.values()),
                        "closed": sum(c["closed_count"] for c in cells.values()),
                        "open": sum(c["open_count"] for c in cells.values())},
        "interpretation": [
            "Each cell retains all28506 offered jobs, but admits only12 notification boundaries; this is not a full-day run.",
            "Native notifications lack business IDs. Job children are conservative labels, with affected-job scope unverified.",
            "Full mandatory setup, capture initialization, triggering advances and shared work are charged in full to each root, never averaged or subtracted.",
            "Closed roots have finite conservative complete-operation upper bounds. Open roots have only observed-prefix bounds; eventual completion upper bounds are unknown.",
            "The measured setup is an included wall-clock component, not a proved pure-compute lower bound. No complete per-request compute lower bound is available.",
            "Native phase reports conserve all native/binding time and have accepted finite instrumentation; they do not provide refined per-request totals or authorize physics subtraction.",
            "Every full-setup bound exceeds100ms. This prevents a100ms certificate from these upper bounds; an upper-bound exceedance alone does not prove a pure-compute violation.",
        ],
        "original_business_request_100ms_certified": False,
        "unconditional_complete_100ms_certified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.directory)
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": reference(args.output), "root_totals": report["root_totals"]}, indent=2))


if __name__ == "__main__":
    main()
