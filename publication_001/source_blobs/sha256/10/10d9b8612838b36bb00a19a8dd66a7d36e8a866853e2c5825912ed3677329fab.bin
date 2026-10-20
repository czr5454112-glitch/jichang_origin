"""Fresh full-input controller execution with sparse diagnostic native seals.

Every controller return is saved without rebuilding the full raw history in
memory. Seal cadence alone differs from profile_lt2_streaming: every reached
physical target and every normal final exit. A timeout's unsealed tail remains
raw evidence, never a native checkpoint or a full-day/timing certificate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from . import resume_full_day as shared

ROOT = Path(__file__).resolve().parents[3]
streaming = shared.streaming
SEAL_SCHEDULE = "Every reached segment horizon and every final budget/status exit; no extra controller activation or physical boundary"


def validate_args(args):
    shared.require(args.suite in {"synthetic", "full1x", "full2x"}, "unsupported_sparse_suite")
    shared.require(shared.finite(args.horizon, positive=True) and
                   shared.finite(args.segment_seconds, positive=True), "invalid_sparse_horizon")
    shared.require(all(type(getattr(args, key)) is int and getattr(args, key) > 0 for key in
        ("event_budget", "max_activations", "activation_shard_budget")), "invalid_sparse_budget")
    shared.require(shared.finite(args.hard_timeout, positive=True) and args.hard_timeout <= 7200,
                   "invalid_sparse_timeout")
    shared.require(shared.digest_string(args.expected_binary_sha256) and
                   shared.sha(args.binary) == args.expected_binary_sha256, "sparse_binary_identity_mismatch")


def prepare_input(args):
    """Exactly the old full-input/protocol contract, with no admission filter."""
    if args.suite == "synthetic":
        _, data, owners = streaming.scenarios()[1]
        config = dict(control_period=.5, command_delay=.01, publication_delay=.02,
                      retry_period=.5, lease_seconds=120.)
    else:
        contract = streaming.ProxyContract("nanning-on-carrier-proxy-v1-n4-s4-t2", 4, 4, 2,
            1., 1., 0., "finite_berth_waiting_research_proxy")
        data, manifest, _ = streaming.build_input(scale=int(args.suite[-2]), contract=contract,
            horizon=args.horizon, max_events=args.event_budget, trace_limit=0)
        shared.dump(args.output / "input_manifest.json", manifest)
        shared.dump(args.output / "static_diagnostics.json", streaming.static_diagnostics(data))
        shared.dump(args.output / "return_contract_diagnostics.json", streaming.return_contract_diagnostics(data))
        data = streaming.add_protocol_contract(data)
        owners = sorted({n.get("resource_owner", n["zone"]) for n in data["node_contracts"]})
        config = dict(control_period=60., command_delay=2., publication_delay=.5,
                      retry_period=60., lease_seconds=120.)
        if args.horizon == 86400.:
            shared.require(len(data["jobs"]) == 28506 * int(args.suite[-2]), "sparse_offered_count_changed")
    data["owner_notifications"] = {"enabled": True}
    config.update(compact=True, routes=True, forecasts=True, predictive=True, prebalance=True)
    return data, owners, config


def worker(args):
    validate_args(args)
    worker_started = time.perf_counter()
    data, owners, config = prepare_input(args)
    export_seconds, seal_seconds = 0., 0.

    def export(path, value):
        nonlocal export_seconds
        started = time.perf_counter()
        shared.require(not path.exists(), "sparse_artifact_already_exists")
        streaming.gz(path, value, compresslevel=1)
        export_seconds += time.perf_counter() - started

    export(args.output / "input.json.gz", data)
    shared.dump(args.output / "heartbeat.json", {"stage": "native_initialization", "offered_total": len(data["jobs"]),
        "native_persistence": "Fresh native input construction; JSON alone never restores native state."})
    started = time.perf_counter()
    session = shared.load_native(args.binary).NativeSession(data)
    initialization_seconds = time.perf_counter() - started
    run = {"controller_state": None, "segments": []}
    elapsed, offset, count, segment = 0., 0, 0, 0
    target, latest_seal = min(args.segment_seconds, args.horizon), None
    (args.output / "segments").mkdir(exist_ok=False)
    (args.output / "segment_hashes").mkdir(exist_ok=False)
    while True:
        started = time.perf_counter()
        part = shared.run_event_protocol_control(session, owners, horizon=target, event_budget=args.event_budget,
            max_activations=min(args.activation_shard_budget, args.max_activations - count),
            state=run["controller_state"], _consume_state=True, **config)
        elapsed += time.perf_counter() - started
        count += len(part["control_records"])
        if shared.should_seal(part, count, args.max_activations, args.horizon):
            started = time.perf_counter()
            part["native_state_sha256"] = session.offline_state_sha256()
            part["diagnostic_seal_wall_ms"] = 1000 * (time.perf_counter() - started)
            seal_seconds += part["diagnostic_seal_wall_ms"] / 1000
            latest_seal = {"shard": segment, "physical_time": session.physical_time,
                           "native_state_sha256": part["native_state_sha256"]}
        for key in ("control_records", "native_batches"):
            for row in part[key]:
                row["trace_sequence"] += offset
        offset += len(part["control_records"]) + len(part["native_batches"])
        for key in ("status", "result", "controller_state", "control_continuation"):
            run[key] = part[key]
        run["segments"].append({"horizon": target, "physical_time": session.physical_time,
            "status": part["status"], "cumulative_control_wall_seconds": elapsed})
        path = args.output / "segments" / f"{segment:04d}.json.gz"
        export(path, part)
        shared.dump(args.output / "segment_hashes" / f"{segment:04d}.json",
            {"path": str(path.relative_to(args.output)), "sha256": shared.sha(path)})
        shared.dump(args.output / "heartbeat.json", {"stage": "segment_saved", "segment": segment,
            "status": part["status"], "physical_time": session.physical_time, "owner_activations": count,
            "offered_total": len(data["jobs"]), "offered_by_current_time": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
            "controller_wall_seconds": elapsed, "diagnostic_export_wall_seconds": export_seconds,
            "diagnostic_seal_wall_seconds": seal_seconds, "latest_native_seal": latest_seal,
            "native_persistence": "Process-local. Only a recorded contemporaneous native seal can anchor verified tape reconstruction; unsealed tail is raw evidence."})
        segment += 1
        if (part["status"] not in {"reached", "control_budget_exhausted"} or
                (part["status"] == "reached" and target == args.horizon) or count >= args.max_activations):
            if part["status"] == "reached" and target < args.horizon:
                run["status"], run["result"] = "control_budget_exhausted", None
            shared.require(shared.digest_string(part.get("native_state_sha256")), "sparse_final_exit_not_sealed")
            final_seal = part["native_state_sha256"]
            part = None
            break
        if part["status"] == "reached":
            target = min(target + args.segment_seconds, args.horizon)
        part = None  # Persisted raw records do not survive into the next call.
    run["wall_seconds"] = elapsed
    manifest = streaming.shard_manifest(args.output, run, count)
    summary = {"status": run["status"], "physical_time": session.physical_time, "horizon": args.horizon,
        "offered_total": len(data["jobs"]), "offered_by_current_time": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
        "wall_seconds": elapsed, "owner_activations": count, "native_initialization_wall_seconds": initialization_seconds,
        "timing": {"status": "deferred_full_raw_trace_available", "request_count": len(run["controller_state"]["client"]["outbox"]),
            "attempt_count": manifest["counts"]["client_calls"], "complete_100ms_requirement_certified": False},
        "cprofile_enabled": False, "trace_gc": False, "retain_trace_in_memory": False,
        "complete_100ms_requirement_certified": False, "diagnostic_storage": "complete_shards", "gzip_level": 1,
        "native_sha256": args.expected_binary_sha256, "native_state_sha256": final_seal, "metrics": None,
        "diagnostic_export_wall_seconds": export_seconds, "diagnostic_seal_wall_seconds": seal_seconds,
        "new_seal_schedule": SEAL_SCHEDULE,
        "scope": "Unchanged full input, controller and physical model; only diagnostic sealing cadence/storage differs. No full-request timing or business protection certification."}
    result = run.get("result")
    if result is not None:
        export(args.output / "native_offline_diagnostics.json.gz", session.offline_diagnostics())
        summary.update(metrics=shared.outcome_cost(result, data["jobs"], args.horizon),
            audit=shared.audit_result(shared.replay_input(data, streaming.shard_calls(args.output)), result),
            business_status_counts=dict(Counter(j["status"] for j in result["jobs"])),
            tray_mode_counts=dict(Counter(t["mode"] for t in result["trays"])),
            all_input_arrivals_observed=all(j["arrival"] <= session.physical_time for j in data["jobs"]))
    summary["diagnostic_export_wall_seconds"] = export_seconds
    summary["worker_wall_seconds_through_summary"] = time.perf_counter() - worker_started
    shared.dump(args.output / "summary.json", summary)
    shared.dump(args.output / "heartbeat.json", {"stage": "worker_finished", "status": run["status"], "physical_time": session.physical_time})
    shared.require(shared.sha(args.binary) == args.expected_binary_sha256, "sparse_binary_changed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--suite", choices=("synthetic", "full1x", "full2x"), required=True)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--segment-seconds", type=float, default=3600.)
    parser.add_argument("--event-budget", type=int, default=1000000)
    parser.add_argument("--max-activations", type=int, default=1000000)
    parser.add_argument("--activation-shard-budget", type=int, default=500)
    parser.add_argument("--hard-timeout", type=float, default=7200.)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    validate_args(args)
    if args.worker:
        try:
            return worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    args.output.mkdir(parents=True, exist_ok=False)
    sources = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m, "__file__", None)
        and str(m.__file__).endswith(".py") and Path(m.__file__).resolve().is_relative_to(ROOT)})
    before = {str(path.relative_to(ROOT)): shared.sha(path) for path in sources}
    for path in sources:
        archive = args.output / "source_archive" / path.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, archive)
    # Include defaulted provenance options explicitly for independent verification.
    command = [sys.executable, "-m", __spec__.name, "--binary", str(args.binary),
        "--expected-binary-sha256", args.expected_binary_sha256, "--suite", args.suite,
        "--horizon", str(args.horizon), "--segment-seconds", str(args.segment_seconds),
        "--event-budget", str(args.event_budget), "--max-activations", str(args.max_activations),
        "--activation-shard-budget", str(args.activation_shard_budget), "--hard-timeout", str(args.hard_timeout),
        "--output", str(args.output), "--worker"]
    receipt = {"schema": "g31.full_day_sparse_worker.v1", "status": "running", "command": command,
        "source_before": before, "binary_sha256": args.expected_binary_sha256,
        "hard_timeout_seconds": args.hard_timeout, "maximum_native_workers": 1,
        "new_seal_schedule": SEAL_SCHEDULE, "complete_100ms_requirement_certified": False}
    shared.dump(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    with (args.output / "stdout.log").open("w", encoding="utf-8") as out, (args.output / "stderr.log").open("w", encoding="utf-8") as err:
        try:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=args.hard_timeout, check=False)
            receipt.update(status="completed" if result.returncode == 0 else "failed", exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            receipt.update(status="hard_timeout", exit_code=None, result="unknown_unsealed_tail_preserved")
    receipt.update(wall_seconds=time.perf_counter() - started,
        source_changed=[path for path, digest in before.items() if shared.sha(ROOT / path) != digest])
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    shared.dump(args.output / "receipt.json", receipt)
    if receipt["status"] == "completed" and (args.suite == "synthetic" or args.horizon == 86400.):
        total = len(shared.read_gz(args.output / "input.json.gz")["jobs"])
        shared.finalize_verification(args.output, receipt, {"horizon": args.horizon, "offered_total": total})
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
