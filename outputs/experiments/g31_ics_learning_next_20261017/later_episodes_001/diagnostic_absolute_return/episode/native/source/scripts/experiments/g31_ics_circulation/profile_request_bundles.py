"""Separate bounded worker for located, conservative full-request bundles."""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import traceback

from .event_protocol_control import run_event_protocol_control
from .native_host import load_native
from .request_bundle_measurement import BundleRecorder, analyze_bundles


SOURCE_NAMES = ("profile_request_bundles.py", "request_bundle_measurement.py", "event_protocol_control.py",
    "protocol_control.py", "analytic_control.py", "regional_control.py", "native_host.py")
TIMING_KEYS = {"compute_wall_ms", "compute_cpu_ms", "submit_compute_ms", "wall_ms", "cpu_ms"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def atomic(path, value, *, compressed=False):
    tmp = path.with_suffix(path.suffix + ".tmp")
    if compressed:
        with gzip.open(tmp, "wt", encoding="utf-8") as stream:
            json.dump(value, stream, allow_nan=False)
    else:
        tmp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    tmp.replace(path)


def read_gzip(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def semantics(value):
    if isinstance(value, dict):
        return {k: semantics(v) for k, v in value.items() if k not in TIMING_KEYS}
    if isinstance(value, list):
        return [semantics(v) for v in value]
    return value


def worker(args):
    source_paths = [Path(__file__).with_name(name) for name in SOURCE_NAMES]
    sources = {str(p): sha(p) for p in source_paths}
    archive = args.output / "source_archive"
    archive.mkdir()
    for path in source_paths:
        (archive/path.name).write_bytes(path.read_bytes())
    input_path, old_run_path = args.profile/"input.json.gz", args.profile/"run.json.gz"
    identities = {"input.json.gz": sha(input_path), "run.json.gz": sha(old_run_path)}
    if sha(args.binary) != args.expected_binary_sha256:
        raise ValueError("request_bundles:binary_identity_mismatch")
    data, old = read_gzip(input_path), read_gzip(old_run_path)
    config = copy.deepcopy(old["controller_state"]["config"])
    del old  # The prior diagnostic trace is not a live controller dependency.
    owners = config.pop("owners")
    if args.horizon != data["options"]["max_simulation_time"]:
        raise ValueError("request_bundles:declared_input_horizon_mismatch")
    manifest = {"schema": "g31.request_bundle_run.v1", "status": "running", "input_profile": str(args.profile.resolve()),
        "input_sha256": identities, "native_sha256": sha(args.binary), "source_sha256": sources,
        "offered_total": len(data["jobs"]), "horizon": args.horizon, "config": config, "owners": owners,
        "max_activations": args.max_activations, "activation_shard_budget": args.activation_shard_budget,
        "cprofile_enabled": False, "maximum_native_workers": 1,
        "request_scope": "owner_activation_updates", "native_stage_times_isolated": False,
        "physics_subtracted": False, "complete_100ms_requirement_certified": False,
        "host": {"platform": platform.platform(), "processor": platform.processor(), "python": sys.version},
        "excluded_diagnostic_work": "Evidence loading, native world construction before accepting controller updates, ledger finalization and evidence gzip/JSON writes are separately reported, not production control stages."}
    atomic(args.output/"manifest.json", manifest)
    started = time.perf_counter()
    native = load_native(args.binary)
    session = native.NativeSession(data)
    manifest["native_load_and_initialization_seconds"] = time.perf_counter()-started
    recorder = BundleRecorder(session)
    state, part_limits, activations = None, [], 0
    started = time.perf_counter()
    try:
        while activations < args.max_activations:
            requested_limit = min(args.activation_shard_budget, args.max_activations-activations)
            part = recorder.run(owners, horizon=args.horizon, event_budget=args.event_budget,
                max_activations=requested_limit, state=state, **config)
            state = part["controller_state"]
            part_limits.append(requested_limit)
            # Raw immutable forensic evidence, outside measured service windows.
            atomic(args.output/f"segment_{len(part_limits):04d}.json.gz", part, compressed=True)
            activations += len(part["control_records"])
            ledger = recorder.ledger()
            atomic(args.output/"ledger.json.gz", ledger, compressed=True)
            atomic(args.output/"accounting.json.gz", analyze_bundles(ledger), compressed=True)
            atomic(args.output/"heartbeat.json", {"stage": "complete_controller_call_saved", "segments": len(part_limits),
                "owner_activations": activations, "status": part["status"], "physical_time": session.physical_time})
            final_status = part["status"]
            del part, ledger
            if final_status != "control_budget_exhausted":
                break
        captured_hash = session.offline_state_sha256()
        checks = None
        if args.verify_uninstrumented:
            plain = native.NativeSession(data)
            plain_state = None
            keys = ("status", "controller_state", "control_records", "client_calls", "native_batches", "result", "control_continuation")
            checks = {key: True for key in keys}
            for index, limit in enumerate(part_limits, 1):
                recorded = read_gzip(args.output/f"segment_{index:04d}.json.gz")
                expected = {key: digest(semantics(recorded[key])) for key in keys}
                del recorded
                p = run_event_protocol_control(plain, owners, horizon=args.horizon, event_budget=args.event_budget,
                    max_activations=limit, state=plain_state, **config)
                plain_state = p["controller_state"]
                for key in keys:
                    checks[key] = checks[key] and expected[key] == digest(semantics(p[key]))
                del p
            checks["native_state"] = captured_hash == plain.offline_state_sha256()
            atomic(args.output/"uninstrumented_equivalence.json", checks)
            if not all(checks.values()):
                raise ValueError("request_bundles:instrumentation_changed_execution")
        report = analyze_bundles(recorder.ledger())
        atomic(args.output/"accounting.json.gz", report, compressed=True)
        atomic(args.output/"controller_state.json.gz", state, compressed=True)
        changed = [p for p, expected in sources.items() if sha(p) != expected]
        changed += [name for name, path in (("input.json.gz", input_path), ("run.json.gz", old_run_path)) if sha(path) != identities[name]]
        manifest.update(status="invalidated_source_changed" if changed else "captured", source_changed=changed,
            controller_status=final_status, physical_time=session.physical_time,
            offered_by_current_time=sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
            owner_activations=activations, segments=len(part_limits), requested_activation_limits=part_limits,
            raw_controller_segments="segment_NNNN.json.gz", native_state_sha256=captured_hash,
            complete_declared_horizon=final_status == "reached" and session.physical_time == args.horizon,
            accounting={k: v for k, v in report.items() if k != "requests"},
            captured_controller_wall_seconds=report.get("exclusive_controller_wall_ns", 0)/1e9,
            worker_measurement_and_evidence_seconds=time.perf_counter()-started,
            uninstrumented_equivalence=checks)
        atomic(args.output/"manifest.json", manifest)
        print(json.dumps({k: manifest[k] for k in ("status", "controller_status", "owner_activations", "physical_time", "accounting")}, indent=2))
        return 0 if not changed and report["status"] == "complete_conservative_bundle_accounting" else 2
    except BaseException:
        atomic(args.output/"ledger_error_prefix.json.gz", recorder.ledger(), compressed=True)
        (args.output/"error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--max-activations", type=int, default=5000)
    parser.add_argument("--activation-shard-budget", type=int, default=500)
    parser.add_argument("--event-budget", type=int, default=100000)
    parser.add_argument("--hard-timeout", type=float, default=180.)
    parser.add_argument("--verify-uninstrumented", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if min(args.max_activations, args.activation_shard_budget, args.event_budget, args.hard_timeout) <= 0:
        raise ValueError("request_bundles:invalid_budget")
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    started = time.perf_counter()
    with (args.output/"stdout.txt").open("w", encoding="utf-8") as stdout, (args.output/"stderr.txt").open("w", encoding="utf-8") as stderr:
        try:
            child = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.hard_timeout, check=False)
            status, code = "finished", child.returncode
        except subprocess.TimeoutExpired:
            status, code = "hard_timeout", 124
    atomic(args.output/"process.json", {"status": status, "exit_code": code, "command": command,
        "timeout_seconds": args.hard_timeout, "wall_seconds": time.perf_counter()-started, "maximum_native_workers": 1})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
