"""Full-input execution with streamed diagnostic shards and explicit GC evidence.

Only the redundant in-memory diagnostic trace is optional. Every raw record
is retained in immutable shards and reconstructed after measured control stops.
"""
from __future__ import annotations

import argparse
import cProfile
from collections import Counter
import gzip
import gc
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

from . import event_protocol_control as controller_module
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


def gz(path, value, *, compresslevel=9):
    temp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temp, "wt", encoding="utf-8", compresslevel=compresslevel) as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False))
    temp.replace(path)


def shard_manifest(output, run, activation_count):
    """Index complete raw shards without reconstructing their growing history.

    This changes diagnostic storage only. Every returned controller checkpoint,
    client call, owner record and native boundary remains in its original shard.
    A manifest is never a cross-process native checkpoint or a timing certificate.
    """
    shards = []
    counts = {key: 0 for key in ("control_records", "native_batches", "client_calls")}
    next_sequence = 0
    for path in sorted((output / "segments").glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            part = json.load(stream)
        for key in counts:
            counts[key] += len(part[key])
        sequences = sorted(row["trace_sequence"] for key in ("control_records", "native_batches") for row in part[key])
        if sequences != list(range(next_sequence, next_sequence + len(sequences))):
            raise ValueError("stream_manifest:missing_or_duplicate_trace_sequence")
        next_sequence += len(sequences)
        shards.append({"path": str(path.relative_to(output)), "sha256": sha(path),
                       "counts": {key: len(part[key]) for key in counts},
                       "status": part["status"], "physical_time": part["control_continuation"]["physical_time"]})
    if counts["control_records"] != activation_count or not shards:
        raise ValueError("stream_manifest:incomplete_owner_denominator")
    # Timer heaps contain tuples in-process and JSON arrays in saved shards.
    # Compare their public JSON meaning without changing either representation.
    if json.dumps(part["controller_state"], sort_keys=True, allow_nan=False) != json.dumps(run["controller_state"], sort_keys=True, allow_nan=False):
        raise ValueError("stream_manifest:final_state_mismatch")
    result = {"schema": "g31.lt2.complete_sharded_trace.v1", "shards": shards, "counts": counts,
              "status": run["status"], "last_shard_status": part["status"], "wall_seconds": run["wall_seconds"],
              "segments": run["segments"], "final_state_shard": shards[-1]["path"],
              "all_raw_records_retained": True, "cross_process_native_checkpoint": False,
              "scope": "Complete diagnostic history in ordered raw shards; deferred request accounting is not certified."}
    atomic_json(output / "run_shards.json", result)
    return result


def shard_calls(output):
    """Feed all original submissions/retries to the unchanged physical auditor."""
    for path in sorted((output / "segments").glob("*.json.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            part = json.load(stream)
        yield from part["client_calls"]


def worker(args):
    try:
        export_seconds = 0.
        seal_seconds = 0.
        def export(path, value):
            nonlocal export_seconds
            started_export = time.perf_counter()
            gz(path, value, compresslevel=getattr(args, "gzip_level", 9))
            export_seconds += time.perf_counter() - started_export
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
        export(args.output/"input.json.gz", data)
        atomic_json(args.output/"heartbeat.json", {"stage": "native_initialization", "offered_total": len(data["jobs"]),
            "native_persistence": "process-local; new process rebuilds from input, does not restore JSON alone"})
        session = load_native(args.binary).NativeSession(data)
        profiler = cProfile.Profile() if args.cprofile else None
        run = {"control_records": [], "native_batches": [], "client_calls": [],
               "controller_state": None, "segments": []}
        elapsed, offset, segment, activation_count = 0., 0, 0, 0
        gc_rows, gc_pending = [], {}
        owner_scope = [None]
        in_control = [False]
        original_activate = controller_module._activate_owner
        def measured_activate(client, owner, current, causes, **kwargs):
            owner_scope[0] = {"owner_id": owner, "owner_epoch": current["owner_epochs"].get(owner, 0),
                              "physical_time": client.session.physical_time}
            try:
                return original_activate(client, owner, current, causes, **kwargs)
            finally:
                owner_scope[0] = None
        def gc_event(phase, info):
            generation = info["generation"]
            if phase == "start":
                gc_pending[generation] = (time.perf_counter_ns(), time.process_time_ns(), in_control[0],
                                          dict(owner_scope[0]) if owner_scope[0] is not None else None)
            else:
                started_gc = gc_pending.pop(generation, None)
                if started_gc is not None:
                    begin, cpu_begin, inside, owner = started_gc
                    gc_rows.append({"generation": generation, "start_ns": begin, "end_ns": time.perf_counter_ns(),
                        "cpu_ns": time.process_time_ns()-cpu_begin, "inside_controller": inside and in_control[0],
                        "owner": owner, "collected": info["collected"], "uncollectable": info["uncollectable"]})
        if args.trace_gc:
            gc.callbacks.append(gc_event)
            controller_module._activate_owner = measured_activate
        gc_saved = 0
        try:
            target = min(args.segment_seconds, args.horizon)
            while True:
                started = time.perf_counter()
                in_control[0] = True
                if profiler:
                    profiler.enable()
                part = run_event_protocol_control(session, owners, horizon=target, compact=True,
                    event_budget=args.event_budget,
                    max_activations=min(args.activation_shard_budget,
                                        args.max_activations-activation_count),
                    state=run["controller_state"], routes=args.policy == "joint", forecasts=args.policy != "reactive",
                    predictive=args.policy != "reactive", prebalance=True,
                    _consume_state=getattr(args, "consume_controller_state", False), **config)
                elapsed += time.perf_counter() - started
                in_control[0] = False
                activation_count += len(part["control_records"])
                if profiler:
                    profiler.disable()
                # Diagnostic native seal is outside the measured controller call.
                # It binds this actual in-process cut, never a JSON-only restore.
                if getattr(args, "seal_shards", False):
                    seal_started = time.perf_counter()
                    part["native_state_sha256"] = session.offline_state_sha256()
                    part["diagnostic_seal_wall_ms"] = 1000 * (time.perf_counter() - seal_started)
                    seal_seconds += part["diagnostic_seal_wall_ms"] / 1000
                for row in part["control_records"] + part["native_batches"]:
                    row["trace_sequence"] += offset
                offset += len(part["control_records"]) + len(part["native_batches"])
                for key in ("control_records", "native_batches", "client_calls"):
                    if args.retain_trace_in_memory:
                        run[key].extend(part[key])
                for key in ("status", "result", "controller_state", "control_continuation"):
                    run[key] = part[key]
                run["segments"].append({"horizon": target, "physical_time": session.physical_time,
                                        "status": part["status"], "cumulative_control_wall_seconds": elapsed})
                # Complete raw shards survive a later hard timeout. JSON alone is
                # deliberately not advertised as physical process persistence.
                shard_dir = args.output/"segments"; shard_dir.mkdir(exist_ok=True)
                export(shard_dir/f"{segment:04d}.json.gz", part)
                if args.trace_gc:
                    gc_dir = args.output/"gc_segments"; gc_dir.mkdir(exist_ok=True)
                    gc_cut = len(gc_rows)
                    export(gc_dir/f"{segment:04d}.json.gz", gc_rows[gc_saved:gc_cut])
                    gc_saved = gc_cut
                atomic_json(args.output/"heartbeat.json", {"stage": "segment_saved", "segment": segment,
                    "status": part["status"], "physical_time": session.physical_time,
                    "offered_total": len(data["jobs"]),
                    "offered_by_current_time": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
                    "owner_activations": activation_count,
                    "controller_wall_seconds": elapsed, "diagnostic_export_wall_seconds": export_seconds,
                    "diagnostic_seal_wall_seconds": seal_seconds,
                    "native_persistence": "process-local; saved shards require input reconstruction after process exit"})
                segment += 1
                if (part["status"] not in {"reached", "control_budget_exhausted"} or
                        (part["status"] == "reached" and target == args.horizon) or
                        activation_count >= args.max_activations):
                    if target < args.horizon and part["status"] == "reached":
                        run["status"], run["result"] = "control_budget_exhausted", None
                    part = None  # Raw records are already persisted; run retains only required continuation references.
                    break
                # An owner-budget shard may end inside a pending same-timestamp
                # round. Continue that saved round at the same target in this
                # process; a shard is not a completed physical horizon.
                if part["status"] == "reached":
                    target = min(target+args.segment_seconds, args.horizon)
                part = None  # Do not keep the previous raw record graph alive during the next call.
        finally:
            in_control[0] = False
            if profiler:
                profiler.disable()
            if args.trace_gc:
                gc.callbacks.remove(gc_event)
                controller_module._activate_owner = original_activate
                export(args.output/"gc_events.json.gz", gc_rows)
        # Reconstruct the same complete diagnostic artifact only after all
        # measured controller calls. No request/history is discarded.
        shards_only = getattr(args, "shards_only", False)
        if not args.retain_trace_in_memory and not shards_only:
            for shard in sorted((args.output/"segments").glob("*.json.gz")):
                with gzip.open(shard, "rt", encoding="utf-8") as stream:
                    saved_part = json.load(stream)
                for key in ("control_records", "native_batches", "client_calls"):
                    run[key].extend(saved_part[key])
            assert len(run["control_records"]) == activation_count
        if profiler:
            profiler.dump_stats(str(args.output/"controller.prof"))
            with (args.output/"profile.txt").open("w", encoding="utf-8") as stream:
                pstats.Stats(profiler, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(40)
        # Outer envelope includes result rendering and returned checkpoint copy.
        run["wall_seconds"] = elapsed
        if shards_only:
            manifest = shard_manifest(args.output, run, activation_count)
            spans = {"status": "deferred_full_raw_trace_available",
                     "request_count": len(run["controller_state"]["client"]["outbox"]),
                     "attempt_count": manifest["counts"]["client_calls"],
                     "complete_100ms_requirement_certified": False,
                     "scope": "Full-day physical execution study; all raw timing records retained in run_shards.json. Complete request accounting is a separate gate."}
        else:
            export(args.output/"run.json.gz", run)
            spans = summarize_request_spans(run)
            export(args.output/"request_spans.json.gz", spans)
        result = run.get("result")
        # Offline evidence is collected after the measured policy has stopped.
        # It cannot influence decisions and is not a replacement for a full
        # business outcome when an activation/event/time budget censored the run.
        summary = {"status": run["status"], "physical_time": session.physical_time,
            "horizon": args.horizon, "offered_total": len(data["jobs"]),
            "offered_by_current_time": sum(j["arrival"] <= session.physical_time for j in data["jobs"]),
            "wall_seconds": elapsed, "owner_activations": activation_count,
            "timing": {k: v for k, v in spans.items() if k not in ("requests", "no_request_owner_activations")},
            "cprofile_enabled": args.cprofile, "trace_gc": args.trace_gc,
            "retain_trace_in_memory": args.retain_trace_in_memory, "complete_100ms_requirement_certified": False,
            "diagnostic_storage": "complete_shards" if shards_only else "shards_and_reconstructed_run",
            "native_sha256": sha(args.binary), "native_state_sha256": session.offline_state_sha256(), "metrics": None,
            "scope": "new native run, fixed input denominator; cProfile overhead when enabled; no two-machine or isolated request-stage timing"}
        if result is not None:
            export(args.output/"native_offline_diagnostics.json.gz", session.offline_diagnostics())
            summary["metrics"] = outcome_cost(result, data["jobs"], args.horizon)
            audit_calls = shard_calls(args.output) if shards_only else run["client_calls"]
            summary["audit"] = audit_result(replay_input(data, audit_calls), result)
            summary["business_status_counts"] = dict(Counter(j["status"] for j in result["jobs"]))
            summary["tray_mode_counts"] = dict(Counter(t["mode"] for t in result["trays"]))
            summary["all_input_arrivals_observed"] = all(j["arrival"] <= session.physical_time for j in data["jobs"])
        summary.update(gzip_level=getattr(args, "gzip_level", 9),
            diagnostic_export_wall_seconds=export_seconds, diagnostic_seal_wall_seconds=seal_seconds)
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
    parser.add_argument("--trace-gc", action="store_true")
    parser.add_argument("--retain-trace-in-memory", action="store_true", help="Comparison arm: retain the same redundant trace used by the old harness")
    parser.add_argument("--shards-only", action="store_true",
                        help="Keep and hash every raw shard without reconstructing the growing trace in RAM; request accounting remains explicitly deferred")
    parser.add_argument("--consume-controller-state", action="store_true",
                        help="Transfer exclusive ownership of each in-process controller state; failed state must be discarded")
    parser.add_argument("--seal-shards", action="store_true",
                        help="Save an actual native state seal and its diagnostic cost for every raw shard; no request-timing certification")
    parser.add_argument("--gzip-level", type=int, choices=range(10), default=9,
                        help="Lossless diagnostic archive compression; all decompressed JSON bytes and records are retained")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.shards_only and args.retain_trace_in_memory:
        parser.error("shards-only and retained in-memory trace are mutually exclusive")
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
    cmd = [sys.executable, "-m", "scripts.experiments.g31_ics_circulation.profile_lt2_streaming", *sys.argv[1:], "--worker"]
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
