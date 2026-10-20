"""Explicit process-local public path pool around the accepted sparse driver.

No existing controller or sparse-driver file is edited. The same worker owns
every native call and shard. Cached facts are restricted to owner-isolated
public graph/path computations, never observations, decisions or checkpoints.
"""
from __future__ import annotations
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from . import full_day_sparse as sparse
from .install_public_travel_pool import installed_public_travel_pool

shared, ROOT = sparse.shared, sparse.ROOT


def worker(args):
    shared.require(args.travel_pool in {"on", "off"}, "invalid_sparse_pool_mode")
    context = installed_public_travel_pool() if args.travel_pool == "on" else nullcontext(None)
    with context as state:
        result = sparse.worker(args)
        diagnostics = {"mode": args.travel_pool, "cold_at_worker_start": True,
            "cached_information": "owner-isolated public static graph and exact path tuples only",
            "cost_scope": "Graph keys, checkouts and searches inside unchanged controller windows; empty pool construction/cleanup remain in parent wall time.",
            "persisted_in_controller_state": False}
        if state is not None:
            pool, counters = state
            diagnostics.update(counters, graph_hits=pool.hits, graph_misses=pool.misses)
    shared.dump(args.output / "travel_pool.json", diagnostics)
    return result


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
    parser.add_argument("--travel-pool", choices=("on", "off"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    sparse.validate_args(args)
    if args.worker:
        try:
            return worker(args)
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    args.output.mkdir(parents=True, exist_ok=False)
    sources = sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module, "__file__", None) and str(module.__file__).endswith(".py")
        and Path(module.__file__).resolve().is_relative_to(ROOT)})
    before = {str(path.relative_to(ROOT)): shared.sha(path) for path in sources}
    for path in sources:
        archive = args.output / "source_archive" / path.relative_to(ROOT)
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, archive)
    command = [sys.executable, "-m", __spec__.name, "--binary", str(args.binary),
        "--expected-binary-sha256", args.expected_binary_sha256, "--suite", args.suite,
        "--horizon", str(args.horizon), "--segment-seconds", str(args.segment_seconds),
        "--event-budget", str(args.event_budget), "--max-activations", str(args.max_activations),
        "--activation-shard-budget", str(args.activation_shard_budget), "--hard-timeout", str(args.hard_timeout),
        "--travel-pool", args.travel_pool, "--output", str(args.output), "--worker"]
    receipt = {"schema": "g31.full_day_sparse_public_pool_worker.v1", "status": "running", "command": command,
        "source_before": before, "binary_sha256": args.expected_binary_sha256, "cache_mode": args.travel_pool,
        "hard_timeout_seconds": args.hard_timeout, "maximum_native_workers": 1,
        "new_seal_schedule": sparse.SEAL_SCHEDULE, "complete_100ms_requirement_certified": False}
    shared.dump(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    with (args.output / "stdout.log").open("w", encoding="utf-8") as out, (args.output / "stderr.log").open("w", encoding="utf-8") as err:
        try:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=args.hard_timeout, check=False)
            receipt.update(status="completed" if result.returncode == 0 else "failed", exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            receipt.update(status="hard_timeout", exit_code=None, result="unknown_unsealed_tail_preserved")
    receipt.update(wall_seconds=time.perf_counter() - started,
        source_changed=[path for path, digest in before.items() if shared.sha(ROOT / path) != digest],
        binary_after_sha256=shared.sha(args.binary))
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    if receipt["binary_after_sha256"] != args.expected_binary_sha256:
        receipt["status"] = "invalidated_binary_changed"
    shared.dump(args.output / "receipt.json", receipt)
    if receipt["status"] == "completed" and (args.suite == "synthetic" or args.horizon == 86400.):
        total = len(shared.read_gz(args.output / "input.json.gz")["jobs"])
        shared.finalize_verification(args.output, receipt, {"horizon": args.horizon, "offered_total": total})
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
