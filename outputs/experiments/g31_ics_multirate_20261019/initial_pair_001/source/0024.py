"""Offline amendment: retain every measured setup gap and startup sensitivity.

This does not revise native raw files or certify the original business boundary.
The existing service contract assumes an initialized Python/native host. Its
per-case capture constructor is diagnostic-only; the full-wall alternatives
below also retain that constructor and the entire worker's startup/export cost.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

from . import verify_installed_operations as verifier


def corrected_bounds(raw, old_report, process_wall_seconds):
    def stamp(value):
        if type(value) is not int or value < 0:
            raise ValueError("setup_audit:invalid_clock")
        return value
    intervals = raw["setup_intervals"]
    if len(intervals) != 2:
        raise ValueError("setup_audit:setup_domain")
    first, second = intervals
    s0, e0, s1, e1 = (stamp(first["start_ns"]), stamp(first["end_ns"]),
                      stamp(second["start_ns"]), stamp(second["end_ns"]))
    accepted = min(stamp(row["start_ns"]) for row in raw["roots"].values())
    diagnostic = stamp(raw["diagnostic_capture_setup_ns"])
    if not s0 <= e0 <= s1 <= e1 <= accepted or diagnostic > s1-e0:
        raise ValueError("setup_audit:unordered_or_uncontained_setup")
    old_setup = e0-s0 + e1-s1
    extra = accepted-s0-old_setup-diagnostic
    if extra < 0:
        raise ValueError("setup_audit:negative_gap")
    if (isinstance(process_wall_seconds, bool) or not isinstance(process_wall_seconds, (int, float))
            or not 0 < process_wall_seconds < float("inf")):
        raise ValueError("setup_audit:invalid_process_wall")
    process_ns = math.ceil(process_wall_seconds*1_000_000_000)
    results = {}
    if set(old_report["roots"]) != set(raw["roots"]):
        raise ValueError("setup_audit:root_domain")
    for root, record in raw["roots"].items():
        start = stamp(record["start_ns"])
        end = stamp(raw["ended_ns"] if record["end_ns"] is None else record["end_ns"])
        if not accepted <= start <= end:
            raise ValueError("setup_audit:root_interval")
        old = old_report["roots"][root]
        prefix = end-start+old_setup
        if old["known_prefix_upper_ns"] != prefix:
            raise ValueError("setup_audit:old_bound_mismatch")
        closed = old["complete_compute_upper_ns"] is not None
        if closed != (record["end_ns"] is not None) or closed and old["complete_compute_upper_ns"] != prefix:
            raise ValueError("setup_audit:closure_mismatch")
        service = prefix+extra
        full_setup = service+diagnostic
        if full_setup > process_ns:
            raise ValueError("setup_audit:case_exceeds_process_envelope")
        results[root] = {
            "closed": closed, "job_scope_verified": old["job_scope_verified"],
            "original_service_upper_ns": old["complete_compute_upper_ns"],
            "added_setup_gap_ns": extra,
            "initialized_host_service_upper_ns": service if closed else None,
            "known_prefix_with_setup_gaps_ns": service,
            "all_case_setup_wall_upper_ns": full_setup if closed else None,
            "all_case_setup_known_prefix_ns": full_setup,
            "whole_worker_process_upper_ns": process_ns if closed else None,
            "whole_worker_process_known_prefix_ns": process_ns,
            "original_business_request_100ms_certified": False,
            "unconditional_complete_100ms_certified": False,
        }
    return {"setup_gap_ns": extra, "diagnostic_capture_setup_ns": diagnostic,
            "original_setup_ns": old_setup, "roots": results}


def audit(directory):
    directory = Path(directory)
    verified = verifier.verify_saved(directory)
    cases = {}
    for name, report in verified["cases"].items():
        raw = json.loads(gzip.decompress((directory/"timed"/(name+".json.gz")).read_bytes()))
        process = json.loads((directory/"timed.process.json").read_text())
        cases[name] = corrected_bounds(raw, report, process["wall_seconds"])
    return {
        "schema": "g31.installed_operation_setup_amendment.v1",
        "status": "validated_setup_gap_amendment",
        "source_run": str(directory.resolve()),
        "source_receipt_sha256": hashlib.sha256((directory/"receipt.json").read_bytes()).hexdigest(),
        "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cases": cases, "root_denominator": verified["root_denominator"],
        "closed_count": verified["closed_count"],
        "capture_dependency": "Only offline trace identity/epoch/envelope export. No captured timing or contract-verification result enters an operation payload or route choice; plain/timed native/public semantics are exact.",
        "startup_dependency": "Worker verify_contract selects the binary and load_native/import initialize the host before case timers. These are mandatory host startup but not isolated per case; the whole-worker process sensitivity retains them without division.",
        "accounting": "All case-setup gaps through the earliest root admission are charged in full to each root. A later child retains its own lifetime plus this common setup; its ancestor's full lifetime retains all earlier parent work and the child. Initialized-host service excludes only the explicitly measured per-case diagnostic capture constructor. Full-case setup includes it; full-worker process includes all case work, imports, startup, diagnostics and export. No physics/GC or shared-work subtraction.",
        "limits": ["Synthetic finite installed-operation contract only", "Open roots retain unknown complete totals", "Transfer/cancel job scope unverified", "Bounds above100ms are conservative and do not establish an actual request violation"],
        "original_business_request_100ms_certified": False,
        "unconditional_complete_100ms_certified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.directory)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")


if __name__ == "__main__":
    main()
