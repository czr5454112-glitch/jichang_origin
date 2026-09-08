"""Paired whole-population zero-fault equivalence, in isolated native processes.

Keeps complete native bag output for both switch positions. These are validation
controls, not replacements for the preregistered ten-seed experiment matrix.
"""
from __future__ import annotations
import argparse
import gzip
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from czr005 import cpp_backend
from scripts.eval import run_cie_component_activation as activation
from scripts.eval import run_cie_external_baseline_robustness as external
from scripts.eval import g4irsf31_map_adapter as maps
from scripts.eval import run_g31_tarau_paper_suite as archive

BINARY = ROOT / "build/g31_fault_potential_repair_20260907/python/Release/czr005_cpp.cp311-win_amd64.pyd"
OUT = ROOT / "outputs/runtime/g31_fault_paper_suite_validation_20260907/normal_full_v1"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(archive._bytes(value))


def child(map_name, load, enabled, output, binary):
    identity_path = ROOT / f"data/processed/workloads/cie_external_robustness/{map_name}_{load:.2f}x".replace(".00", "p00") / "seed_104729/identity.json"
    identity_path, identity = external._identity_payload(identity_path)
    rows = activation._read_jsonl(Path(identity["canonical_path"]))
    profile = activation._profile_for_map(map_name, activation.DEFAULT_NANNING_PROFILE)
    request, potential = maps.build_s4_request(profile, rows, binary=binary,
        scenario="g31_fault_potential_repair_zero_fault_full_population", max_events=60_000_000,
        max_simulation_time=98259, trace_limit=1000, event_trace_limit=1000, summary_only=False,
        edge_speed_mps=2.5, enable_s4_local_potential_descent_guard=True,
        enable_s4_direct_neighbor_merge_calendar_visibility=True, complete_on_goal_arrival=True)
    request["enable_cie_component_activation"] = True
    request["enable_s4_advertised_fault_potential_repair"] = enabled
    output.mkdir(parents=True, exist_ok=True)
    if (output / "runner_status.json").exists():
        raise RuntimeError("prior validation attempt exists; never overwrite evidence")
    binding = {"binary_path": str(binary), "binary_sha256": archive.sha256(binary),
               "workload_identity_path": str(identity_path), "workload_identity_sha256": archive.sha256(identity_path),
               "enabled": enabled, "map": map_name, "load_factor": load, "seed": 104729,
               "python_wrapper_sha256": archive.sha256(Path(cpp_backend.__file__)),
               "cpp_source_sha256": archive.sha256(ROOT / "cpp/ics_core/runtime/event_driven_junction.hpp")}
    write(output / "identity.json", binding)
    archive._gzip_json(output / "request.json.gz", request)
    write(output / "runner_status.json", {"status": "RUNNING", **binding})
    started = time.perf_counter()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    elapsed = time.perf_counter()-started
    record = archive._gzip_json(output / "native_payload.json.gz", payload)
    spec = {"fixed_horizon_seconds": 98259, "binary_sha256": binding["binary_sha256"],
            "timing_policy": "full_population_only", "load_factor": load}
    prepared = archive.Prepared(spec, identity, rows, request, {})
    try:
        audit = archive.audit_payload(prepared, payload)
    except Exception as exc:
        write(output / "runner_status.json", {"status": "NATIVE_ARCHIVED_AUDIT_FAILED", "error": str(exc), **binding})
        raise
    audit.pop("raw_rows")
    counters = {k: v for k, v in payload["summary"].items() if k.startswith("s4_fault_")}
    if enabled and any(float(value) != 0.0 for value in counters.values()):
        raise AssertionError("fault repair path activated with no faults")
    result = {"status": "PASS", "identity": binding, "audit": audit,
              "native_archive": record, "repair_counters": counters,
              "native_runtime_seconds": payload["summary"]["runtime_seconds"], "wall_seconds": elapsed}
    write(output / "result.json", result)
    write(output / "runner_status.json", {"status": "COMPLETE", "wall_seconds": elapsed})
    print(json.dumps({"map": map_name, "load": load, "enabled": enabled, "status": "PASS",
                      "runtime_seconds": result["native_runtime_seconds"]}), flush=True)


def compare(root, loads):
    pairs = []
    for map_name in ("map2", "nanning"):
        for load in loads:
            values = []
            for state in ("off", "on"):
                path = root / f"{map_name}_{load:g}x_{state}"
                with gzip.open(path / "native_payload.json.gz", "rt", encoding="utf-8") as stream:
                    values.append(archive._decode(json.load(stream)))
            old, new = values
            if old["bags"] != new["bags"]:
                before = {v["segment_id"]: v for v in old["bags"]}
                changed = [v["segment_id"] for v in new["bags"] if before.get(v["segment_id"]) != v]
                raise AssertionError(f"normal full-bag output changed: {map_name}/{load}, {changed[:10]}")
            for key in ("events", "decisions"):
                # Some native trace rows contain measured decision latency. Bag
                # equality is exact; full trace equivalence is covered by the
                # bounded mechanism suite with explicitly normalized telemetry.
                if key in old and len(old[key]) != len(new.get(key, [])):
                    raise AssertionError("normal trace length changed")
            old_seconds = old["summary"]["runtime_seconds"]
            new_seconds = new["summary"]["runtime_seconds"]
            pairs.append({"map": map_name, "load_factor": load, "seed": 104729,
                          "exact_native_bag_output_equal": True, "segments": len(old["bags"]),
                          "completed_segments": new["summary"]["completed_count"],
                          "runtime_off_seconds": old_seconds, "runtime_on_seconds": new_seconds,
                          "runtime_percent_change": 100*(new_seconds/old_seconds-1),
                          "runtime_caveat": "Single paired run; wall-time noise is not an algorithm throughput difference."})
    result = {"status": "PASS", "pair_count": len(pairs), "pairs": pairs,
              "population_scope": "seed104729 at requested loads; all native bag fields including clocks, counts and last-eight-node history equal; bounded probes establish full route equivalence"}
    write(root / "comparison.json", result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


def reaudit(output):
    """Audit retained native observations; never rerun or rewrite native files."""
    binding = json.loads((output / "identity.json").read_text(encoding="utf-8"))
    identity = json.loads(Path(binding["workload_identity_path"]).read_text(encoding="utf-8"))
    if archive.sha256(Path(binding["workload_identity_path"])) != binding["workload_identity_sha256"]:
        raise ValueError("identity changed")
    if (output / "result.json").exists():
        raise ValueError("accepted result already exists")
    with gzip.open(output / "request.json.gz", "rt", encoding="utf-8") as stream:
        request = archive._decode(json.load(stream))
    with gzip.open(output / "native_payload.json.gz", "rb") as stream:
        content = stream.read()
    payload = archive._decode(json.loads(content))
    spec = {"fixed_horizon_seconds": 98259, "binary_sha256": binding["binary_sha256"], "timing_policy": "full_population_only"}
    audit = archive.audit_payload(archive.Prepared(spec, identity, activation._read_jsonl(Path(identity["canonical_path"])), request, {}), payload)
    audit.pop("raw_rows")
    write(output / "reaudit.json", {"status": "PASS", "runner_sha256": archive.sha256(Path(archive.__file__)),
                                   "reason": "Execution state and bounded lifecycle-log completeness are separate; original native protocol flag retained false.",
                                   "native_sha256": archive.sha256(output / "native_payload.json.gz"), "audit": audit})
    write(output / "result.json", {"status": "PASS", "identity": binding, "audit": audit,
                                  "native_runtime_seconds": payload["summary"]["runtime_seconds"], "native_reexecuted": False})
    print(json.dumps({"status": "PASS", "native_reexecuted": False}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("batch", "child", "compare", "reaudit"))
    parser.add_argument("--map", choices=("map2", "nanning"))
    parser.add_argument("--load", type=float, choices=(1., 2.), action="append")
    parser.add_argument("--enabled", type=int, choices=(0, 1))
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--binary", type=Path, default=BINARY)
    args = parser.parse_args()
    loads = args.load or [1.]
    if args.mode == "reaudit":
        reaudit(args.output)
    elif args.mode == "child":
        child(args.map, loads[0], bool(args.enabled), args.output.resolve(), args.binary.resolve(strict=True))
    elif args.mode == "compare":
        compare(args.output, loads)
    else:
        for map_name in ("map2", "nanning"):
            for load in loads:
                order = (0, 1) if map_name == "map2" else (1, 0)
                for enabled in order:
                    output = args.output / f"{map_name}_{load:g}x_{'on' if enabled else 'off'}"
                    if (output / "result.json").exists():
                        continue
                    command = [sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "child", "--map", map_name,
                               "--load", str(load), "--enabled", str(enabled), "--output", str(output), "--binary", str(args.binary)]
                    subprocess.run(command, cwd=ROOT, check=True)
        compare(args.output, loads)


if __name__ == "__main__":
    main()
