"""Offline raw, phase, accounting and GC correlation for the two storage arms."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

from .native_request_timing import analyze_native_timing
from .profile_request_bundles import semantics
from .request_bundle_measurement import analyze_bundles
from .stream_native_request_timing import reconstruct_native_timing
from .verify_request_bundles import verify as verify_raw


def read(path):
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as stream: return json.load(stream)
    return json.loads(Path(path).read_bytes())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def overlap(a, b):
    return max(0, min(a["end_ns"], b["end_ns"])-max(a["start_ns"], b["start_ns"]))


def strip_native_clocks(value):
    if isinstance(value, dict):
        return {key: strip_native_clocks(item) for key, item in value.items() if key not in {"start_ns", "end_ns"}}
    if isinstance(value, list): return [strip_native_clocks(item) for item in value]
    return value


def audit_arm(directory):
    manifest, ledger = read(directory/"manifest.json"), read(directory/"ledger.json.gz")
    process = read(directory/"process.json")
    if process.get("status") != "finished" or process.get("exit_code") != 0 or manifest.get("source_changed"):
        raise ValueError("incomplete or changed-source arm")
    command = process["command"]
    if command.count("--event-budget") != 1:
        raise ValueError("ambiguous event budget")
    event_budget = int(command[command.index("--event-budget")+1])
    for path, expected in manifest["source_sha256"].items():
        if sha(directory/"source_archive"/Path(path).name) != expected:
            raise ValueError("captured source archive changed")
    for name, expected in manifest["input_sha256"].items():
        if sha(Path(manifest["input_profile"])/name) != expected:
            raise ValueError("captured input reference changed")
    raw = verify_raw(directory)
    if raw["status"] != "verified_raw_execution_and_bundle_accounting": raise ValueError(str(raw))
    native = ledger["native_timing"]
    phase = analyze_native_timing(native["batches"], native["call_envelopes"])
    coarse = analyze_bundles(ledger)
    saved = read(directory/"accounting.json.gz")
    if native["capture_errors"] or phase != saved["native_phase_partition"]:
        raise ValueError("native phase report changed or capture errors")
    if phase["status"] != "validated_partial_native_phase_partition": raise ValueError(str(phase))
    if any(coarse.get(key) != saved.get(key) for key in coarse): raise ValueError("coarse report changed")
    if not all(read(directory/"uninstrumented_equivalence.json").values()): raise ValueError("plain replay mismatch")
    if "native_timing_stream" in ledger and reconstruct_native_timing(ledger["native_timing_stream"]) != native:
        raise ValueError("stream reconstruction not exact")
    owners = [b for b in ledger["bundles"] if b["kind"] == "owner_activation"]
    gc_rows = []
    gc_paths = sorted((directory/"gc_0001").glob("window_*.json.gz"))
    expected_names = [f"window_{i:06d}.json.gz" for i in range(1, len(ledger["service_windows"])+1)]
    if [path.name for path in gc_paths] != expected_names:
        raise ValueError("GC window coverage mismatch")
    for index, path in enumerate(gc_paths, 1):
        gc_window = read(path)
        if (gc_window["schema"] != "g31.native_phase_gc_window.v1" or gc_window["window"] != index or
            gc_window["clock"] != "perf_counter_ns" or gc_window["errors"] or
            gc_window["gc_disabled_or_forced"] is not False or gc_window["gc_time_subtracted"] is not False):
            raise ValueError("invalid GC capture")
        for row in gc_window["rows"]:
            if (type(row["generation"]) is not int or row["generation"] not in range(3) or
                any(type(row[k]) is not int or row[k] < 0 for k in ("start_ns", "end_ns", "wall_ns")) or
                row["wall_ns"] != row["end_ns"]-row["start_ns"]):
                raise ValueError("invalid GC event interval")
        gc_rows.extend(gc_window["rows"])
    ordered_gc = sorted(gc_rows, key=lambda row:row["start_ns"])
    if any(a["end_ns"] > b["start_ns"] for a,b in zip(ordered_gc, ordered_gc[1:])):
        raise ValueError("overlapping GC intervals cannot be added")
    gc_summary = {}
    for generation in range(3):
        rows = [row for row in gc_rows if row["generation"] == generation]
        gc_summary[str(generation)] = {"count": len(rows), "total_ns": sum(row["wall_ns"] for row in rows),
            "maximum_ns": max((row["wall_ns"] for row in rows), default=0),
            "service_overlap_ns": sum(sum(overlap(row, window) for window in ledger["service_windows"]) for row in rows)}
    slow_owners = []
    for owner in owners:
        duration = owner["end_ns"]-owner["start_ns"]
        if duration > 100_000_000:
            matches = [g for g in gc_rows if overlap(owner, g)]
            slow_owners.append({"root_id": owner["activation_root_id"], "owner_ns": duration,
                "gc_overlap_ns": sum(overlap(owner, g) for g in matches),
                "gc_generations": [g["generation"] for g in matches],
                "gc_context_native_methods": [g["native_method"] for g in matches]})
    large_gc = []
    for row in gc_rows:
        if row["generation"] == 2:
            large_gc.append({**row, "service_overlap_ns": sum(overlap(row, w) for w in ledger["service_windows"]),
                "owner_overlap": [{"root_id": b["activation_root_id"], "overlap_ns": overlap(row,b)}
                                  for b in owners if overlap(row,b)]})
    result = {"raw_verification": raw, "native_partition": phase,
        "evidence_sha256": {path.name: sha(path) for path in
            [directory/"manifest.json", directory/"ledger.json.gz", directory/"accounting.json.gz",
             directory/"process.json", *sorted(directory.glob("segment_*.json.gz")), *gc_paths]},
        "coarse_summary": {key:value for key,value in coarse.items() if key != "requests"},
        "controller_wall_seconds": manifest["captured_controller_wall_seconds"],
        "process": process, "gc_by_generation": gc_summary,
        "owners_over100ms_with_gc_overlap": slow_owners, "generation2_events": large_gc,
        "root_status_counts": dict(Counter(row["status"] for row in ledger["requests"])),
        "physical_time": manifest["physical_time"], "offered_total": manifest["offered_total"],
        "native_seal": manifest["native_state_sha256"], "plain_replay": manifest["uninstrumented_equivalence"]}
    identity = {"source": manifest["source_sha256"], "input": manifest["input_sha256"],
        "native": manifest["native_sha256"], "config": manifest["config"], "owners": manifest["owners"],
        "horizon": manifest["horizon"], "limits": manifest["requested_activation_limits"],
        "event_budget": event_budget,
        "native_trace_without_clocks": digest(strip_native_clocks(native)),
        "raw_segments": [digest(semantics({key:part[key] for key in
            ("status", "controller_state", "control_records", "client_calls", "native_batches", "result", "control_continuation")}))
            for path in sorted(directory.glob("segment_*.json.gz")) for part in [read(path)]]}
    return result, identity


def verify(pair):
    execution = read(pair/"pair_execution.json")
    if (execution.get("status") != "both_workers_returned" or execution.get("source_changed") or
        set(execution.get("arms", {})) != {"retained", "streamed"} or
        any(value.get("exit_code") != 0 for value in execution["arms"].values())):
        raise ValueError("pair not fully executed")
    results, identities = {}, {}
    for arm in ("retained", "streamed"):
        results[arm], identities[arm] = audit_arm(pair/arm)
    checks = {key:identities["retained"][key] == identities["streamed"][key] for key in identities["retained"]}
    checks["native_seal"] = results["retained"]["native_seal"] == results["streamed"]["native_seal"]
    if not all(checks.values()): raise ValueError("pair identity/raw mismatch:"+str(checks))
    return {"schema": "g31.native_timing_retention_pair_audit.v1", "status": "verified", "checks": checks,
        "validator_sha256": sha(__file__), "execution_receipt_sha256": sha(pair/"pair_execution.json"),
        "arms": results, "native_workers": 0, "physics_or_gc_subtracted": False,
        "complete_request_100ms_certified": False, "isolated_speed_certified": False,
        "scope": "Two measured storage arms under recorded concurrent work. GC interval overlap is observed, not proof of which object family caused collection. All coarse/native/shared output charges remain. Upper bounds above100ms are not isolated compute violations."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args=parser.parse_args()
    report=verify(args.pair)
    with args.output.open("x",encoding="utf-8") as stream: json.dump(report,stream,indent=2,allow_nan=False)
    print(json.dumps({"status":report["status"],"checks":report["checks"]},indent=2))


if __name__ == "__main__": main()
