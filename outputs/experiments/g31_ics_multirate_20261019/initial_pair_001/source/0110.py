"""Bounded independent replay of an immutable tape against a saved native seal.

The replay proves physical reconstruction, not policy recomputation or arbitrary
JSON restoration. Missing original native seals are not generated retroactively.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback

from . import native_host, reconstruct_native_tape

ROOT = Path(__file__).absolute().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def read_gz(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def verify_sources(args):
    pins = {args.binary: args.expected_binary_sha256,
            args.input: args.expected_input_sha256,
            args.reference_summary: args.expected_summary_sha256,
            args.assignment: args.expected_assignment_sha256}
    if any(sha(path) != digest for path, digest in pins.items()):
        raise ValueError("tape_driver:source_identity_mismatch")
    summary = json.loads(args.reference_summary.read_text(encoding="utf-8"))
    assignment = json.loads(args.assignment.read_text(encoding="utf-8"))
    if (summary["status"] != "completed" or summary["native_sha256"] != args.expected_binary_sha256
            or assignment["status"] != "recorded_call_assignment_validated"
            or not assignment["evidence"]):
        raise ValueError("tape_driver:unaccepted_reference")
    paths = []
    for row in assignment["evidence"]:
        path = (ROOT / row["path"]).resolve()
        if not path.is_relative_to(ROOT) or path in paths or sha(path) != row["sha256"]:
            raise ValueError("tape_driver:shard_identity_mismatch")
        paths.append(path)
    return summary, assignment, paths


def worker(args):
    summary, assignment, paths = verify_sources(args)
    data = read_gz(args.input)
    if len(data["jobs"]) != summary["input_jobs"]:
        raise ValueError("tape_driver:input_population_mismatch")
    started = time.perf_counter()
    session = native_host.load_native(args.binary).NativeSession(data)
    replay = reconstruct_native_tape.NativeTapeReconstructor(session, event_budget=args.event_budget)
    for i, path in enumerate(paths):
        part = read_gz(path)
        row = replay.replay_part(part)
        write(args.output / "heartbeat.json", dict(row, saved_part=i, source_shard_sha256=sha(path)))
        del part
    result = replay.finish(summary["native_state_sha256"])
    if (result["owners"] != summary["activations"] or result["submissions"] != summary["submissions"]
            or result["native_boundaries"] != summary["boundaries"]
            or result["physical_time"] != summary["physical_time"]
            or result["parts"] != assignment["parts"]):
        raise ValueError("tape_driver:reference_denominator_mismatch")
    result.update(wall_seconds=time.perf_counter()-started, source_input_sha256=sha(args.input),
        native_sha256=sha(args.binary), source_assignment_sha256=sha(args.assignment),
        source_reference_summary_sha256=sha(args.reference_summary),
        scope="Fresh native input plus exact recorded mutation/boundary/query replay. Original final seal checked; policy calculations and observation rendering not reexecuted. No request timing comparison.")
    write(args.output / "assessment.json", result)
    print(json.dumps({key: result[key] for key in ("status", "owners", "submissions", "wall_seconds", "native_state_sha256")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("binary", "input", "reference-summary", "assignment", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("binary", "input", "summary", "assignment"):
        parser.add_argument("--expected-" + name + "-sha256", required=True)
    parser.add_argument("--event-budget", type=int, required=True)
    parser.add_argument("--hard-timeout", type=float, default=180.)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.event_budget <= 0 or not 0 < args.hard_timeout <= 3600:
        parser.error("positive event budget and bounded timeout required")
    if args.worker:
        try:
            worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
        return 0
    verify_sources(args)
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), Path(native_host.__file__), Path(reconstruct_native_tape.__file__)]
    before = {str(path.resolve()): sha(path) for path in sources}
    archive = args.output / "source_archive"
    archive.mkdir()
    for path in sources:
        (archive / path.name).write_bytes(path.read_bytes())
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    receipt = {"schema": "g31.native_tape_execution.v1", "status": "running", "command": command,
               "source_before": before, "simulation_workers": 1, "hard_timeout_seconds": args.hard_timeout,
               "whole_request_100ms_certified": False}
    write(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    with (args.output / "stdout.log").open("w", encoding="utf-8") as stdout, (args.output / "stderr.log").open("w", encoding="utf-8") as stderr:
        try:
            process = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=args.hard_timeout)
            receipt.update(status="passed" if process.returncode == 0 else "failed", exit_code=process.returncode)
        except subprocess.TimeoutExpired:
            receipt.update(status="hard_timeout_unknown", exit_code=None)
    receipt["wall_seconds"] = time.perf_counter()-started
    receipt["source_changed"] = [path for path, digest in before.items() if sha(path) != digest]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    write(args.output / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
