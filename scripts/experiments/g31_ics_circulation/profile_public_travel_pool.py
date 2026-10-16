"""Bounded original streaming worker with an explicit public path-cache arm.

Controller code, native methods, shard boundaries, input and raw retention are
the same in both arms. Cache-key construction and checkout happen inside the
normal measured controller windows. No cached graph is restored from evidence.
"""
import argparse
from contextlib import nullcontext
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback
from . import profile_lt2_streaming as original
from .install_public_travel_pool import installed_public_travel_pool

ROOT = original.ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", choices=("synthetic", "full1x", "full2x"), required=True)
    parser.add_argument("--horizon", type=float, required=True)
    parser.add_argument("--max-activations", type=int, required=True)
    parser.add_argument("--travel-pool", choices=("off", "on"), required=True)
    parser.add_argument("--hard-timeout", type=float, default=180.)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if (not math.isfinite(args.hard_timeout) or not 0 < args.hard_timeout <= 300 or
            not math.isfinite(args.horizon) or not args.horizon > 0 or not args.max_activations > 0):
        parser.error("positive bounded timeout, horizon and activation budget required")
    args.policy = "joint"
    args.event_budget = 1000000
    args.segment_seconds = 3600.
    args.activation_shard_budget = 500
    args.cprofile = args.trace_gc = args.retain_trace_in_memory = False
    args.shards_only = args.consume_controller_state = args.seal_shards = True
    args.gzip_level = 1
    if original.sha(args.binary) != args.expected_binary_sha256:
        raise ValueError("travel_pool_profile:binary_identity")
    if args.worker:
        try:
            context = installed_public_travel_pool() if args.travel_pool == "on" else nullcontext(None)
            with context as state:
                code = original.worker(args)
                diagnostics = {"mode": args.travel_pool, "cold_at_worker_start": True,
                    "cached_information": "owner-isolated public static graph and exact path tuples only",
                    "cost_scope": "all graph keys, searches and checkouts occur inside unchanged controller windows"}
                if state is not None:
                    pool, counters = state
                    diagnostics.update(counters, graph_hits=pool.hits, graph_misses=pool.misses)
            original.atomic_json(args.output / "travel_pool.json", diagnostics)
            return code
        except Exception:
            (args.output / "error.txt").write_text(traceback.format_exc(), encoding="utf-8")
            raise
    args.output.mkdir(parents=True, exist_ok=False)
    sources = sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module, "__file__", None) and str(module.__file__).endswith(".py")
        and Path(module.__file__).resolve().is_relative_to(ROOT)})
    before = {str(path.relative_to(ROOT)): original.sha(path) for path in sources}
    for path in sources:
        target = args.output / "source_archive" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    receipt = {"schema": "g31.public_travel_pool_worker.v1", "status": "running", "command": command,
        "source_before": before, "binary_sha256": args.expected_binary_sha256,
        "hard_timeout_seconds": args.hard_timeout, "maximum_native_workers": 1,
        "cache_mode": args.travel_pool, "complete_100ms_requirement_certified": False}
    original.atomic_json(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    with (args.output / "stdout.log").open("w", encoding="utf-8") as out, (args.output / "stderr.log").open("w", encoding="utf-8") as err:
        try:
            result = subprocess.run(command, cwd=ROOT, stdout=out, stderr=err, timeout=args.hard_timeout, check=False)
            receipt.update(status="completed" if result.returncode == 0 else "failed", exit_code=result.returncode)
        except subprocess.TimeoutExpired:
            receipt.update(status="hard_timeout_unknown", exit_code=None)
    receipt.update(wall_seconds=time.perf_counter() - started,
        source_changed=[p for p, expected in before.items() if original.sha(ROOT / p) != expected],
        binary_after_sha256=original.sha(args.binary))
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    if receipt["binary_after_sha256"] != args.expected_binary_sha256:
        receipt["status"] = "invalidated_binary_changed"
    original.atomic_json(args.output / "receipt.json", receipt)
    print(json.dumps({k: receipt[k] for k in ("status", "exit_code", "wall_seconds", "source_changed")}))
    return 0 if receipt["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
