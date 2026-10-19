"""Profile a replayed late state; absent original hidden-state seals stay absent."""
from __future__ import annotations

import argparse
import cProfile
import gc
import gzip
import importlib
import json
from pathlib import Path
import pstats
import shutil
import subprocess
import sys
import time
import traceback
import types

from .execute_native_tape import sha, write, read_gz, ROOT
from .native_host import load_native
from .reconstruct_native_tape import NativeTapeReconstructor

DIAGNOSTIC = {"wall_seconds", "compute_wall_ms", "compute_cpu_ms", "submit_compute_ms",
              "wall_ms", "cpu_ms", "native_event_ms", "runtime_seconds"}


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items() if k not in DIAGNOSTIC}
    if isinstance(value, (tuple, list)):
        return [normalized(v) for v in value]
    return value


def worker(args):
    plan = json.loads((args.output/"plan.json").read_text(encoding="utf-8"))
    for path, digest in plan["input_files"].items():
        if sha(path) != digest:
            raise ValueError("late_research:input_identity_changed")
    # Load private archived modules so live shared Python can evolve separately.
    package = types.ModuleType("_g31_late_frozen_policy")
    package.__path__ = [str(args.output/"frozen_policy")]
    sys.modules[package.__name__] = package
    controller = importlib.import_module(package.__name__+".event_protocol_control")
    session = load_native(args.binary).NativeSession(read_gz(args.source/"input.json.gz"))
    replay = NativeTapeReconstructor(session, event_budget=plan["event_budget"])
    started = time.perf_counter()
    part = None
    for i, path in enumerate(plan["replay_shards"]):
        part = read_gz(path)
        row = replay.replay_part(part)
        write(args.output/"heartbeat.json", dict(row, source_shard=i))
    if part["status"] != "reached" or part["result"] is None:
        raise ValueError("late_research:completed_observable_cut_required")
    state = part["controller_state"]
    offset = replay.next_trace
    horizon = part["control_continuation"]["physical_time"]
    del part
    # Deliberately do NOT call finish(): the original cut has no saved seal.
    write(args.output/"reconstruction.json", dict(replay.report(),
        status="observable_evidence_reproduced_for_research_only",
        original_native_seal_available=False, original_hidden_state_equality="unproven",
        reconstructed_native_seal=session.offline_state_sha256(),
        reconstruction_wall_seconds=time.perf_counter()-started))
    write(args.output/"offline_diagnostics.json", session.offline_diagnostics())
    config = dict(state["config"])
    owners = config.pop("owners")
    gc_rows, pending = [], {}
    def gc_event(phase, info):
        gen = info["generation"]
        if phase == "start":
            pending[gen] = time.perf_counter_ns()
        elif gen in pending:
            gc_rows.append(dict(info, wall_ns=time.perf_counter_ns()-pending.pop(gen)))
    profile = cProfile.Profile()
    gc.callbacks.append(gc_event)
    started = time.perf_counter()
    try:
        profile.enable()
        actual = controller.run_event_protocol_control(session, owners,
            horizon=plan["next_run"]["horizon"],
            max_activations=plan["next_run"]["activations"], event_budget=plan["event_budget"],
            state=state, **config)
    finally:
        profile.disable()
        gc.callbacks.remove(gc_event)
    elapsed = time.perf_counter()-started
    # Flush small diagnostics before expensive raw JSON compression so a later
    # timeout cannot silently lose an already completed profiled call.
    profile.dump_stats(str(args.output/"controller.prof"))
    with (args.output/"profile.txt").open("w", encoding="utf-8") as stream:
        pstats.Stats(profile, stream=stream).strip_dirs().sort_stats("cumulative").print_stats(60)
    write(args.output/"gc.json", gc_rows)
    write(args.output/"profile_completion.json", {"controller_profiled_wall_seconds": elapsed,
        "physical_time": session.physical_time, "policy_next_shard_comparison": "pending"})
    for name in ("control_records", "native_batches"):
        for row in actual[name]:
            row["trace_sequence"] += offset
    with gzip.open(args.output/"next_shard.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(actual, stream, ensure_ascii=False, allow_nan=False)
    expected = read_gz(plan["next_shard"])
    exact = json.dumps(normalized(actual), ensure_ascii=False, separators=(",", ":"), allow_nan=False) == json.dumps(normalized(expected), ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    write(args.output/"assessment.json", {"status": "observable_replay_and_next_shard_exact" if exact else "failed_next_shard_mismatch",
        "cut_physical_time": horizon, "final_physical_time": session.physical_time,
        "owner_activations": len(actual["control_records"]), "controller_profiled_wall_seconds": elapsed,
        "controller_next_shard_exact_excluding_clock_fields": exact,
        "original_native_seal_available": False, "original_hidden_state_equality": "unproven",
        "final_reconstructed_native_seal": session.offline_state_sha256(),
        "complete_request_100ms_certified": False,
        "scope": "Research reconstruction reproduces all recorded prior mutating calls, replies, notifications/cursors and completed horizon results, then one full next policy shard. cProfile and different GC history preclude direct speed comparison with the original run; not a restored original native checkpoint."})
    if not exact:
        raise ValueError("late_research:next_shard_mismatch")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "binary", "output"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--cut", type=int, default=44)
    parser.add_argument("--hard-timeout", type=float, default=360.)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.source = args.source.resolve()
    args.binary = args.binary.resolve()
    if args.worker:
        try:
            worker(args)
        except Exception:
            (args.output/"error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
        return 0
    if args.cut < 0 or not 0 < args.hard_timeout <= 1800 or sha(args.binary) != args.expected_binary_sha256:
        raise ValueError("late_research:invalid_identity_or_limit")
    known = ROOT/"outputs/experiments/g31_ics_lt2_sustained_20261014/native_tape_replay_001/native_10000_001/assessment.json"
    if json.loads(known.read_text())["native_state_sha256"] != "b4e4cb626efd6ddddf4a4aa1721dd292e17f3534c7e9821c2b83a3bd0c5b8e70":
        raise ValueError("late_research:known_seal_gate_missing")
    args.output.mkdir(parents=True, exist_ok=False)
    policy = args.output/"frozen_policy"
    policy.mkdir()
    source_files = [Path(__file__), Path(__file__).with_name("reconstruct_native_tape.py"),
                    Path(__file__).with_name("native_host.py"), Path(__file__).with_name("execute_native_tape.py")]
    for name in ("analytic_control", "regional_control", "protocol_control", "event_protocol_control"):
        original = Path(__file__).with_name(name+".py")
        shutil.copyfile(original, policy/original.name)
    archive = args.output/"source_archive"
    archive.mkdir()
    for path in source_files:
        shutil.copyfile(path, archive/path.name)
    shards = [args.source/"segments"/f"{i:04d}.json.gz" for i in range(args.cut+1)]
    next_shard = args.source/"segments"/f"{args.cut+1:04d}.json.gz"
    receipt = json.loads((args.source/"receipt.json").read_text())
    command = receipt["command"]
    event_budget = int(command[command.index("--event-budget")+1])
    all_inputs = [args.binary, args.source/"input.json.gz", args.source/"receipt.json", known, *shards, next_shard, *policy.glob("*.py")]
    plan = {"schema": "g31.late_observable_research_plan.v1", "cut_index": args.cut,
        "replay_shards": list(map(str, shards)), "next_shard": str(next_shard), "event_budget": event_budget,
        "input_files": {str(path): sha(path) for path in all_inputs},
        "original_native_seal_available": False, "original_hidden_state_equality": "unproven"}
    next_part = read_gz(next_shard)
    plan["next_run"] = {"horizon": next_part["control_continuation"]["requested_horizon"],
                        "activations": len(next_part["control_records"])}
    del next_part
    write(args.output/"plan.json", plan)
    before = {str(path.resolve()): sha(path) for path in source_files}
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    record = {"status": "running", "source_before": before, "command": command,
              "native_workers": 1, "hard_timeout_seconds": args.hard_timeout}
    write(args.output/"receipt.json", record)
    started = time.perf_counter()
    with (args.output/"stdout.log").open("wb") as stdout, (args.output/"stderr.log").open("wb") as stderr:
        try:
            process = subprocess.run(command, cwd=ROOT, stdout=stdout, stderr=stderr, timeout=args.hard_timeout)
            record.update(status="passed" if process.returncode == 0 else "failed", exit_code=process.returncode)
        except subprocess.TimeoutExpired:
            record.update(status="hard_timeout_unknown", exit_code=None)
    record["source_changed"] = [path for path, digest in before.items() if sha(path) != digest]
    record["input_changed"] = [path for path, digest in plan["input_files"].items() if sha(path) != digest]
    if record["source_changed"] or record["input_changed"]:
        record["status"] = "invalidated_source_changed"
    record["wall_seconds"] = time.perf_counter()-started
    write(args.output/"receipt.json", record)
    print(json.dumps({key: record[key] for key in ("status", "wall_seconds", "source_changed")}))
    return int(record["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
