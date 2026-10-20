"""Fixed fresh pooled-sparse conformance against accepted unpooled sparse raw."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

from . import full_day_sparse_pool as pooled
from .validate_resume_full_day import encoded

shared, ROOT = pooled.shared, pooled.ROOT
SOURCE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014/sparse_full_day_native_gate_001"


def register(binary, binary_sha256):
    receipt = json.loads((SOURCE / "receipt.json").read_bytes())
    shared.require(receipt["status"] == "passed" and receipt["exit_code"] == 0 and receipt["source_changed"] == [] and
        receipt["binary_sha256"] == binary_sha256 == shared.sha(binary), "pooled_sparse_reference_invalid")
    for name, digest in receipt["source_before"].items():
        shared.require(shared.sha(ROOT / name) == shared.sha(SOURCE / "source_archive" / name) == digest,
                       "pooled_sparse_reference_source_changed")
    old = json.loads((SOURCE / "preregistered.json").read_bytes())
    shared.require(shared.sha(SOURCE / "preregistered.json") == receipt["preregistration_sha256"] and
                   set(old["cases"]) == {"synthetic", "full1x_prefix"}, "pooled_sparse_reference_domain")
    files = [SOURCE / "receipt.json", SOURCE / "preregistered.json", SOURCE / "assessment.json"]
    for name in old["cases"]:
        files.extend([SOURCE / name / "input.json.gz", SOURCE / name / "summary.json",
                      *sorted((SOURCE / name / "segments").glob("*.json.gz"))])
    return {"schema": "g31.pooled_sparse_conformance_preregistered.v1", "source": str(SOURCE),
        "files": {str(path.relative_to(SOURCE)): shared.sha(path) for path in files},
        "cases": {name: row["command"] for name, row in old["cases"].items()}, "binary_sha256": binary_sha256,
        "allowed_changes": "Known diagnostic clocks and separate travel_pool.json only; raw seal cadence and all ordered semantics unchanged.",
        "maximum_native_workers": 1, "complete_request_100ms_certified": False}


def compare_raw(actual, expected):
    shared.require(encoded(actual) == encoded(expected), "pooled_sparse_ordered_raw_changed")


def worker(args):
    registered = json.loads((args.output / "preregistered.json").read_bytes())
    source = Path(registered["source"])
    shared.require(shared.sha(args.binary) == args.expected_binary_sha256 == registered["binary_sha256"],
                   "pooled_sparse_binary_changed")
    for name, digest in registered["files"].items():
        shared.require(shared.sha(source / name) == digest, "pooled_sparse_reference_changed")
    cases = {}
    for name, command in registered["cases"].items():
        output = args.output / name
        output.mkdir(exist_ok=False)
        child = SimpleNamespace(binary=args.binary, expected_binary_sha256=args.expected_binary_sha256,
            output=output, travel_pool="on", suite=shared.option(command, "--suite"),
            horizon=float(shared.option(command, "--horizon")),
            segment_seconds=float(shared.option(command, "--segment-seconds", "3600")),
            event_budget=int(shared.option(command, "--event-budget", "100000")),
            max_activations=int(shared.option(command, "--max-activations")),
            activation_shard_budget=int(shared.option(command, "--activation-shard-budget")), hard_timeout=args.hard_timeout)
        pooled.worker(child)
        expected_dir = source / name
        a, b = (shared.read_gz(directory / "input.json.gz") for directory in (output, expected_dir))
        shared.require(json.dumps(a, ensure_ascii=False, allow_nan=False) == json.dumps(b, ensure_ascii=False, allow_nan=False),
                       "pooled_sparse_input_changed")
        actual_paths, expected_paths = (sorted((directory / "segments").glob("*.json.gz")) for directory in (output, expected_dir))
        shared.require([p.name for p in actual_paths] == [p.name for p in expected_paths] and actual_paths,
                       "pooled_sparse_shard_domain_changed")
        count, sealed = 0, 0
        for actual_path, expected_path in zip(actual_paths, expected_paths, strict=True):
            actual, expected = shared.read_gz(actual_path), shared.read_gz(expected_path)
            compare_raw(actual, expected)
            count += len(actual["control_records"])
            sealed += "native_state_sha256" in actual
            actual = expected = None
        actual_summary, expected_summary = (json.loads((d / "summary.json").read_bytes()) for d in (output, expected_dir))
        fields = ["status", "physical_time", "horizon", "owner_activations", "offered_total", "offered_by_current_time",
            "native_sha256", "native_state_sha256", "metrics", "audit", "business_status_counts", "tray_mode_counts",
            "all_input_arrivals_observed", "new_seal_schedule"]
        shared.require(all(actual_summary.get(key) == expected_summary.get(key) for key in fields), "pooled_sparse_summary_changed")
        counters = json.loads((output / "travel_pool.json").read_bytes())
        shared.require(counters["mode"] == "on" and counters["cold_at_worker_start"] is True and
            counters["graph_misses"] > 0 and counters["graph_hits"] > 0 and
            counters["graph_hits"] + counters["graph_misses"] == counters["checkouts"], "pooled_sparse_cache_not_exercised")
        cases[name] = {"status": "passed", "owner_updates": count, "shards": len(actual_paths), "seals": sealed,
            "cache_counts": counters, "final_native_state_sha256": actual_summary["native_state_sha256"]}
        shared.dump(args.output / "cases.json", cases)
    for name, digest in registered["files"].items():
        shared.require(shared.sha(source / name) == digest, "pooled_sparse_reference_changed")
    shared.dump(args.output / "assessment.json", {"status": "passed", "cases": cases,
        "scope": "Fresh pooled sparse worker exactly matches accepted unpooled sparse ordered raw semantics, seal placement and final native seals. Existing diagnostic clocks only excluded. No full-day or latency certification."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hard-timeout", type=float, default=180.)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    shared.require(shared.finite(args.hard_timeout, positive=True) and args.hard_timeout <= 180., "pooled_sparse_gate_timeout")
    if args.worker:
        try:
            worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
        return 0
    registered = register(args.binary, args.expected_binary_sha256)
    args.output.mkdir(parents=True, exist_ok=False)
    shared.dump(args.output / "preregistered.json", registered)
    sources = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, "__file__", None)
        and str(m.__file__).endswith(".py") and Path(m.__file__).resolve().is_relative_to(ROOT)})
    before = {str(path.relative_to(ROOT)): shared.sha(path) for path in sources}
    for path in sources:
        archive = args.output / "source_archive" / path.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(path.read_bytes())
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    receipt = {"schema": "g31.pooled_sparse_conformance_worker.v1", "status": "running", "command": command,
        "source_before": before, "binary_sha256": args.expected_binary_sha256, "maximum_native_workers": 1,
        "preregistration_sha256": shared.sha(args.output / "preregistered.json")}
    shared.dump(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    with (args.output / "stdout.log").open("w", encoding="utf-8") as out, (args.output / "stderr.log").open("w", encoding="utf-8") as err:
        try:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=args.hard_timeout, check=False)
            receipt.update(status="passed" if result.returncode == 0 else "failed", exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            receipt.update(status="hard_timeout_unknown", exit_code=None)
    receipt.update(wall_seconds=time.perf_counter() - started,
        source_changed=[path for path, digest in before.items() if shared.sha(ROOT / path) != digest],
        binary_after_sha256=shared.sha(args.binary))
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    if receipt["binary_after_sha256"] != args.expected_binary_sha256:
        receipt["status"] = "invalidated_binary_changed"
    shared.dump(args.output / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
