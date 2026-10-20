"""Saved timing decomposition only: retain every measured wall-clock interval."""
from __future__ import annotations
import argparse
from collections import defaultdict
import gzip
import json
from pathlib import Path
from . import probe_original_route_update as p
from . import verify_original_route_update as v


def analyze(output):
    report = {"schema": "g31.original_route_update.elapsed_diagnosis.v1", "native_executions": 0,
        "source_sha256": {str(Path(__file__).resolve()): p.old.sha(__file__)}, "cases": {},
        "complete_100ms_certified": False,
        "scope": "Disjoint native call envelopes and all remaining wall time, with no subtraction from the full root. Native envelopes include physical work; gaps include policy/copies/codec/evidence/dispatch and are not exclusive CPU phases."}
    for name in p.CASES:
        folder = output / name
        raw = p.old.gzread(folder / "raw.json.gz"); root = raw["root"]
        p.require(p.old.sha(folder / "service_tape.jsonl.gz") == raw["api_sha256"], "diagnosis_api_changed")
        with gzip.open(folder / "service_tape.jsonl.gz", "rt", encoding="utf8") as stream:
            rows = [json.loads(line) for line in stream]
        v.validate_tape(rows)
        start = root["started_ns"]; end = root["returned_ns"] or root["censored_ns"]
        selected = [row for row in rows if start <= row["start_ns"] and row["end_ns"] <= end]
        groups = defaultdict(lambda: {"count": 0, "nanoseconds": 0})
        gaps = []; cursor = start
        for row in selected:
            p.require(cursor <= row["start_ns"], "diagnosis_overlapping_calls")
            gaps.append(row["start_ns"] - cursor); cursor = row["end_ns"]
            group = groups[(row["role"], row["endpoint"])]
            group["count"] += 1; group["nanoseconds"] += row["end_ns"] - row["start_ns"]
        gaps.append(end-cursor)
        total_native = sum(g["nanoseconds"] for g in groups.values())
        p.require(total_native+sum(gaps) == end-start, "diagnosis_partition_does_not_conserve")
        invocation_bounds = []
        for event in raw["events"]:
            calls = rows[event["first_api"]:event["after_api"]]
            invocation_bounds.append({"at": event["at"], "first_api": event["first_api"],
                "after_api": event["after_api"], "first_api_start_offset_ms": (calls[0]["start_ns"]-start)/1e6,
                "last_api_end_offset_ms": (calls[-1]["end_ns"]-start)/1e6,
                "native_call_sum_ms": sum(r["end_ns"]-r["start_ns"] for r in calls)/1e6,
                "scope": "First native start to last native end is only an inner invocation envelope; surrounding Python work is retained in the unclassified gaps."})
        decision = root["intent"]["decision"]
        phase = None
        if decision:
            second = next(x for x in invocation_bounds if x["at"] == decision["at"])
            submits = [r for r in selected if r["role"] == "request" and r["endpoint"] == "submit_protocol_command"]
            phase = {"first_observed_at": decision["first_observation"]["at"],
                "source_service_seconds": decision["source_service_seconds"],
                "wire_delay_seconds": decision["request"]["message_delay"],
                "public_time_lower_bound": decision["first_observation"]["at"] + p.old.WIRE + decision["source_service_seconds"],
                "actual_second_view_at": decision["at"],
                "admission_to_second_native_view_start_ms": second["first_api_start_offset_ms"],
                "second_view_start_to_submit_native_start_ms": (submits[0]["start_ns"]-start)/1e6-second["first_api_start_offset_ms"],
                "submit_native_start_to_root_end_ms": (end-submits[0]["start_ns"])/1e6,
                "counterfactual_runtime_measured": False}
        report["cases"][name] = {"raw_sha256": p.old.sha(folder / "raw.json.gz"),
            "api_sha256": raw["api_sha256"], "closed": root["returned_ns"] is not None,
            "full_root_or_censored_prefix_ms": (end-start)/1e6,
            "native_envelopes_ms": total_native/1e6, "unclassified_all_gaps_ms": sum(gaps)/1e6,
            "native_calls_within_root": len(selected), "post_root_tape_rows_excluded_from_this_partition": len(rows)-len(selected),
            "native_by_role_endpoint": [{"role": key[0], "endpoint": key[1], **value,
                "milliseconds": value["nanoseconds"]/1e6} for key, value in sorted(groups.items())],
            "request_invocation_inner_bounds": invocation_bounds, "eligibility_phase": phase,
            "partition_exact_nanoseconds": True}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(); p.require(not args.report.exists(), "diagnosis_report_exists")
    result = analyze(args.output.resolve()); p.old.write(args.report, result)
    print(json.dumps({"report": str(args.report), "sha256": p.old.sha(args.report), "baseline": result["cases"]["baseline"]}))


if __name__ == "__main__": main()
