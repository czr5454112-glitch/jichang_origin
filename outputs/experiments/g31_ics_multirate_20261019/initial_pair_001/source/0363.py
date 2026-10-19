"""Bounded native LT2 request profiling with an isolated hard-timeout worker."""
from __future__ import annotations

import argparse
import cProfile
from collections import Counter
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import pstats
import subprocess
import sys
import time
import traceback

from .event_protocol_control import run_event_protocol_control
from .finite_reference import outcome_cost
from .native_host import audit_result, load_native
from .original_mechanism import select_input
from .original_workload import ProxyContract, build_input, static_diagnostics, return_contract_diagnostics
from .request_spans import summarize_request_spans
from .run_original_protocol import add_protocol_contract, expected_digest
from .validate_protocol_control import scenarios, replay_input

ROOT = Path(__file__).absolute().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def gz(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temp, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
    temp.replace(path)


def worker(args):
    try:
        if sha(args.binary) != args.expected_binary_sha256:
            raise ValueError("lt2_profile:binary_identity_mismatch")
        if args.suite == "synthetic":
            _, data, owners = scenarios()[1]  # predeclared lost-ACK case, no outcome screening
            config = dict(control_period=.5, command_delay=.01, publication_delay=.02,
                          retry_period=.5, lease_seconds=120.)
        else:
            if args.suite == "original24":
                data, manifest, _ = select_input(24, horizon=args.horizon)
            else:
                scale = int(args.suite[-2])
                contract = ProxyContract("nanning-on-carrier-proxy-v1-n4-s4-t2", 4, 4, 2,
                                         1., 1., 0., "finite_berth_waiting_research_proxy")
                data, manifest, _ = build_input(scale=scale, contract=contract,
                    horizon=args.horizon, max_events=args.event_budget, trace_limit=0)
                atomic_json(args.output/"static_diagnostics.json", static_diagnostics(data))
                atomic_json(args.output/"return_contract_diagnostics.json", return_contract_diagnostics(data))
            atomic_json(args.output/"input_manifest.json", manifest)
            data = add_protocol_contract(data)
            owners = sorted({n.get("resource_owner", n["zone"]) for n in data["node_contracts"]})
            config = dict(control_period=60., command_delay=2., publication_delay=.5,
                          retry_period=60., lease_seconds=120.)
        data["owner_notifications"] = {"enabled": True}
        gz(args.output/"input.json.gz", data)
        atomic_json(args.output/"heartbeat.json", {"stage": "native_initialization", "offered_total": len(data["jobs"]),
            "native_persistence": "process-local; new process rebuilds from input, does not restore JSON alone"})
        session = load_native(args.binary).NativeSession(data)
        profiler = cProfile.Profile() if args.cprofile else None
        run = {"control_records": [], "native_batches": [], "client_calls": [],
               "controller_state": None, "segments": []}
        elapsed, offset, segment = 0., 0, 0
        target = min(args.segment_seconds, args.horizon)
        while True:
            started = time.perf_counter()
            if profiler:
                profiler.enable()
            part = run_event_protocol_control(session, owners, horizon=target, compact=True,
                event_budget=args.event_budget,
                max_activations=min(args.activation_shard_budget,
                                    args.max_activations-len(run["control_records"])),
                state=run["controller_state"], routes=args.policy == "joint", forecasts=args.policy != "reactive",
                predictive=args.policy != "reactive", prebalance=True, **config)
            elapsed += time.perf_counter() - started
            if profiler:
                profiler.disable()
            for row in part["control_records"] + part["native_batches"]:
                row["trace_sequence"] += offset
            offset += len(part["control_records"]) + len(part["native_batches"])
            for key in ("control_records", "native_batches", "client_calls"):
                run[key].extend(part[key])
            for key in ("status", "result", "controller_state", "control_continuation"):
                run[key] = part[key]
            run["segments"].append({"horizon": target, "physical_time": session.physical_time,
                                    "status": part["status"], "cumulative_control_wall_seconds": elapsed})
            # Complete raw shards survive a later hard timeout. JSON alone is
            # deliberately not advertised as physical process persistence.
            shard_dir = args.output/"segments"; shard_dir.mkdir(exist_ok=True)
            gz(shard_dir/f"{segment:04d}.json.gz", part)
            atomic_json(args.output/"heartbeat.json", {"stage": "segment_saved", "segment": segment,
                "status": part["status"], "physical_time": session.physical_time,
                "offered_total": len(data["jobs"]),
                "offered_by_current_time": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
                "owner_activations": len(run["control_records"]),
                "native_persistence": "process-local; saved shards require input reconstruction after process exit"})
            segment += 1
            if (part["status"] not in {"reached", "control_budget_exhausted"} or
                    (part["status"] == "reached" and target == args.horizon) or
                    len(run["control_records"]) >= args.max_activations):
                if target < args.horizon and part["status"] == "reached":
                    run["status"], run["result"] = "control_budget_exhausted", None
                break
            # An owner-budget shard may end inside a pending same-timestamp
            # round. Continue that saved round at the same target in this
            # process; a shard is not a completed physical horizon.
            if part["status"] == "reached":
                target = min(target+args.segment_seconds, args.horizon)
        if profiler:
            profiler.dump_stats(str(args.output/"controller.prof"))
            with (args.output/"profile.txt").open("w", encoding="utf-8") as stream:
                pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(40)
        # Outer envelope includes result rendering and returned checkpoint copy.
        run["wall_seconds"] = elapsed
        gz(args.output/"run.json.gz", run)
        spans = summarize_request_spans(run)
        gz(args.output/"request_spans.json.gz", spans)
        result = run.get("result")
        # Offline evidence is collected after the measured policy has stopped.
        # It cannot influence decisions and is not a replacement for a full
        # business outcome when an activation/event/time budget censored the run.
        summary = {"status": run["status"], "physical_time": session.physical_time,
            "horizon": args.horizon, "offered_total": len(data["jobs"]),
            "offered_by_current_time": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
            "wall_seconds": elapsed, "owner_activations": len(run["control_records"]),
            "timing": {k: v for k, v in spans.items() if k not in ("requests", "no_request_owner_activations")},
            "cprofile_enabled": args.cprofile, "complete_100ms_requirement_certified": False,
            "native_sha256": sha(args.binary), "metrics": None,
            "scope": "new native run, fixed input denominator; cProfile overhead when enabled; no two-machine or isolated request-stage timing"}
        if result is not None:
            gz(args.output/"native_offline_diagnostics.json.gz", session.offline_diagnostics())
            summary["metrics"] = outcome_cost(result, data["jobs"], args.horizon)
            summary["audit"] = audit_result(replay_input(data, run["client_calls"]), result)
            summary["business_status_counts"] = dict(Counter(j["status"] for j in result["jobs"]))
            summary["tray_mode_counts"] = dict(Counter(t["mode"] for t in result["trays"]))
            summary["all_input_arrivals_observed"] = all(j["arrival"] <= session.physical_time for j in data["jobs"])
        atomic_json(args.output/"summary.json", summary)
        atomic_json(args.output/"heartbeat.json", {"stage": "worker_finished", "status": run["status"],
                                                  "physical_time": session.physical_time})
        return 0
    except Exception:
        (args.output/"error.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", type=expected_digest, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", choices=("synthetic", "original24", "full1x", "full2x"), required=True)
    parser.add_argument("--policy", choices=("reactive", "predictive", "joint"), default="joint")
    parser.add_argument("--horizon", type=float, required=True)
    parser.add_argument("--event-budget", type=int, default=100000)
    parser.add_argument("--max-activations", type=int, default=20000)
    parser.add_argument("--hard-timeout", type=float, default=180.)
    parser.add_argument("--segment-seconds", type=float, default=3600.,
                        help="Save raw complete native/JSON shards between bounded controller calls")
    parser.add_argument("--activation-shard-budget", type=int, default=500,
                        help="Maximum owner activations per saved in-process continuation shard")
    parser.add_argument("--cprofile", action="store_true")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (not all(math.isfinite(v) and v > 0 for v in
                (args.segment_seconds, args.hard_timeout, args.horizon)) or
            min(args.max_activations, args.activation_shard_budget, args.event_budget) <= 0):
        parser.error("horizon, segment seconds, timeout and all budgets must be finite and positive")
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    # Freeze actual imported Python dependencies. Concurrent, unrelated R1
    # research scripts are not part of this executable's source identity.
    sources = sorted({Path(module.__file__).absolute() for module in list(sys.modules.values())
        if getattr(module, "__file__", None) and str(module.__file__).endswith(".py")
        and Path(module.__file__).absolute().is_relative_to(ROOT)})
    before = {str(p.relative_to(ROOT)): sha(p) for p in sources}
    archive = args.output/"source_archive"; archive.mkdir()
    for path in sources:
        target = archive/path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    cmd = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.profile_lt2_requests", *sys.argv[1:], "--worker"]
    receipt = {"schema": "g31.lt2.profile_worker.v1", "status": "running", "command": cmd,
        "source_before": before, "binary_sha256": sha(args.binary), "hard_timeout_seconds": args.hard_timeout,
        "platform": platform.platform(), "python": platform.python_version(),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "hardware": {"cpu_count": os.cpu_count()}, "process_persistence": "independent bounded shard; reconstruct from frozen input"}
    atomic_json(args.output/"receipt.json", receipt)
    started = time.perf_counter()
    with (args.output/"stdout.log").open("w", encoding="utf-8") as stdout, (args.output/"stderr.log").open("w", encoding="utf-8") as stderr:
        try:
            run = subprocess.run(cmd, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=args.hard_timeout)
            receipt.update(exit_code=run.returncode, status="completed" if run.returncode == 0 else "failed")
        except subprocess.TimeoutExpired:
            receipt.update(exit_code=None, status="hard_timeout", result="unknown_truncated_worker")
    receipt["wall_seconds"] = time.perf_counter() - started
    receipt["source_changed"] = [p for p, h in before.items() if sha(ROOT/p) != h]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    atomic_json(args.output/"receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
