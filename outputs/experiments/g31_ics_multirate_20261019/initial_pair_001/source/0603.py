"""Predeclared fresh sparse-seal conformance against saved native024 execution.

Two fixed existing cases exercise lost ACKs, pending owner rounds, final horizon
and owner-budget exit. No source-domain or outcome selection is performed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from types import SimpleNamespace

from . import full_day_sparse as sparse
from .validate_resume_full_day import encoded

shared = sparse.shared
ROOT = sparse.ROOT
BASE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
CASES = {"synthetic": BASE / "stream_driver_native024_001/synthetic-optimized",
         "full1x_prefix": BASE / "stream_driver_native024_001/full1x-optimized"}


def sans_seal(part):
    # Only the root diagnostic seal can be absent. Never strip same-named
    # request/payload fields or change comparison of any native state content.
    return {key: value for key, value in part.items() if key != "native_state_sha256"}


def compare_part(actual, reference, count, maximum, horizon):
    expected_seal = shared.should_seal(actual, count, maximum, horizon)
    shared.require(("native_state_sha256" in actual) == expected_seal, "sparse_gate_wrong_seal_schedule")
    shared.require(shared.digest_string(reference.get("native_state_sha256")), "sparse_gate_reference_unsealed")
    if expected_seal:
        shared.require(actual["native_state_sha256"] == reference["native_state_sha256"], "sparse_gate_native_seal_changed")
    shared.require(encoded(sans_seal(actual)) == encoded(sans_seal(reference)), "sparse_gate_ordered_raw_changed")
    return {"native_seal_compared": expected_seal,
        "ordered_semantic_sha256": hashlib.sha256(encoded(sans_seal(actual)).encode()).hexdigest()}


def registration(binary, binary_sha256):
    shared.require(shared.sha(binary) == binary_sha256, "sparse_gate_binary_changed")
    result = {"schema": "g31.sparse_seal_conformance_preregistered.v1", "binary_sha256": binary_sha256,
        "cases": {}, "changes_allowed": ["wall diagnostics", "root diagnostic native seal absence on intermediate owner-budget cuts"],
        "required": ["exact input", "all ordered raw semantic fields", "all retained sparse seals", "final native seal", "unchanged source hashes"],
        "maximum_native_workers": 1, "full_day_or_100ms_claim": False}
    for name, source in CASES.items():
        receipt = json.loads((source / "receipt.json").read_bytes())
        shared.require(receipt["status"] == "completed" and receipt["exit_code"] == 0 and
                       receipt["binary_sha256"] == binary_sha256, "sparse_gate_reference_not_complete")
        shared.validate_policy_sources(source, receipt)
        paths = [source / "receipt.json", source / "input.json.gz", source / "summary.json",
                 *sorted((source / "segments").glob("*.json.gz"))]
        shared.require(len(paths) > 4, "sparse_gate_reference_needs_multiple_shards")
        result["cases"][name] = {"source": str(source), "files": {str(p.relative_to(source)): shared.sha(p) for p in paths},
            "command": receipt["command"], "source_before": receipt["source_before"]}
    return result


def case(args, name, registered):
    source = Path(registered["source"])
    for path, digest in registered["files"].items():
        shared.require(shared.sha(source / path) == digest, "sparse_gate_reference_changed")
    command = registered["command"]
    shared.require(shared.option(command, "--policy", "joint") == "joint", "sparse_gate_reference_policy_changed")
    output = args.output / name
    output.mkdir(exist_ok=False)
    child = SimpleNamespace(binary=args.binary, expected_binary_sha256=args.expected_binary_sha256,
        output=output, suite=shared.option(command, "--suite"), horizon=float(shared.option(command, "--horizon")),
        segment_seconds=float(shared.option(command, "--segment-seconds", "3600")),
        event_budget=int(shared.option(command, "--event-budget", "100000")),
        max_activations=int(shared.option(command, "--max-activations")),
        activation_shard_budget=int(shared.option(command, "--activation-shard-budget")), hard_timeout=args.hard_timeout)
    started = time.perf_counter()
    sparse.worker(child)
    actual_input, expected_input = (shared.read_gz(p / "input.json.gz") for p in (output, source))
    shared.require(json.dumps(actual_input, ensure_ascii=False, allow_nan=False) ==
                   json.dumps(expected_input, ensure_ascii=False, allow_nan=False), "sparse_gate_input_changed")
    actual_paths, expected_paths = (sorted((p / "segments").glob("*.json.gz")) for p in (output, source))
    shared.require([p.name for p in actual_paths] == [p.name for p in expected_paths], "sparse_gate_shard_count_changed")
    rows, count = [], 0
    for actual_path, expected_path in zip(actual_paths, expected_paths, strict=True):
        actual, expected = shared.read_gz(actual_path), shared.read_gz(expected_path)
        count += len(actual["control_records"])
        rows.append({"shard": actual_path.name, "owners": len(actual["control_records"]),
            "status": actual["status"], "physical_time": actual["control_continuation"]["physical_time"],
            **compare_part(actual, expected, count, child.max_activations, child.horizon)})
        actual = expected = None
    actual_summary, expected_summary = (json.loads((p / "summary.json").read_bytes()) for p in (output, source))
    fields = ["status", "physical_time", "horizon", "offered_total", "offered_by_current_time", "owner_activations",
              "native_sha256", "native_state_sha256", "metrics"]
    fields += [key for key in ("audit", "business_status_counts", "tray_mode_counts", "all_input_arrivals_observed") if key in expected_summary]
    shared.require(all(actual_summary.get(key) == expected_summary[key] for key in fields), "sparse_gate_summary_changed")
    shared.require(any(not row["native_seal_compared"] for row in rows) and rows[-1]["native_seal_compared"],
                   "sparse_gate_schedule_difference_not_exercised")
    for path, digest in registered["files"].items():
        shared.require(shared.sha(source / path) == digest, "sparse_gate_reference_changed")
    return {"status": "passed", "rows": rows, "summary_fields_compared": fields,
        "owner_updates": count, "wall_seconds": time.perf_counter() - started,
        "final_native_state_sha256": actual_summary["native_state_sha256"]}


def worker(args):
    registered = json.loads((args.output / "preregistered.json").read_bytes())
    shared.require(registered["binary_sha256"] == args.expected_binary_sha256 == shared.sha(args.binary),
                   "sparse_gate_binary_changed")
    results = {}
    for name, descriptor in registered["cases"].items():
        results[name] = case(args, name, descriptor)
        shared.dump(args.output / "cases.json", results)
    shared.dump(args.output / "assessment.json", {"status": "passed", "cases": results,
        "scope": "Fresh native initialization; exact old-stream input, ordered raw semantics and retained/final native seals. Diagnostic clock fields and explicitly absent intermediate root seals only differ. No full-day or timing claim."})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hard-timeout", type=float, default=180.)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    shared.require(shared.finite(args.hard_timeout, positive=True) and args.hard_timeout <= 180., "sparse_gate_timeout")
    if args.worker:
        try:
            worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
        return 0
    registered = registration(args.binary, args.expected_binary_sha256)
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
    receipt = {"schema": "g31.sparse_seal_conformance_worker.v1", "status": "running", "command": command,
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
        source_changed=[path for path, digest in before.items() if shared.sha(ROOT / path) != digest])
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    shared.require(shared.sha(args.binary) == args.expected_binary_sha256, "sparse_gate_binary_changed")
    shared.dump(args.output / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
