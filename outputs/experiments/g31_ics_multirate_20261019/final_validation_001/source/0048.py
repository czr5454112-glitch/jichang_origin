"""Pure, saved-public-view microbenchmark; never creates a native session.

Repeated/changed occupancies below are declared test scenarios, not a measured
original-flow activation trace or actual cache hit-rate estimate.
"""
from __future__ import annotations

import argparse
import copy
import gc
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

from .regional_path_pool import OriginalRouting, RegionalPathPool

ROOT = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def scenarios(views, activations):
    cases = []
    for owner, returned in views.items():
        public = returned["policy"]
        jobs = {row["business_bag_id"]: row for row in public["jobs"]}
        pairs = []
        for tray in public["trays"]:
            job = jobs.get(tray["business_bag_id"])
            if job is None: continue
            goal = job["storage_node"] if job["storage_node"] >= 0 and job["storage_released_at"] < 0 else job["destination"]
            pair = (tray["node"], goal)
            if pair not in pairs: pairs.append(pair)
        # Match roughly the profile's nine calls/activation, without pretending
        # these padding pairs were controller choices in the saved run.
        for edge in public["edge_records"]:
            if len(pairs) >= 9: break
            pair = tuple(edge[:2])
            if pair not in pairs: pairs.append(pair)
        pairs = pairs[:9]
        # Keep precisely the solver/key input projection. Full native policy
        # views also contain long message histories which neither arm reads.
        public = {key: public[key] for key in ("now", "owner_id", "node_contracts",
            "node_records", "edge_records", "edge_contracts", "known_faults")}
        for regime in ("repeated_facts", "two_occupancies", "unique_occupancy"):
            observations = []
            for index in range(activations):
                observation = copy.deepcopy(public)
                observation["now"] += index
                if regime != "repeated_facts":
                    local = next(row for row in observation["node_contracts"] if "occupancy" in row)
                    local["occupancy"] += index % 2 if regime == "two_occupancies" else index
                observations.append(observation)
            cases.append((owner, regime, pairs, observations))
    return cases


def measure(observations, pairs, cached):
    pool = RegionalPathPool() if cached else None
    gc_before = gc.get_stats()
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    results = []
    for observation in observations:
        routing = pool.handle(observation) if pool else OriginalRouting(observation)
        results.append([routing.path(observation, source, goal) for source, goal in pairs])
    elapsed = time.perf_counter_ns()-wall
    cpu_elapsed = time.process_time_ns()-cpu
    return results, dict(wall_ns=elapsed, cpu_ns=cpu_elapsed,
        pool=pool.snapshot() if pool else None,
        gc_collections=[after["collections"]-before["collections"] for before, after in zip(gc_before, gc.get_stats())])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--views", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--activations", type=int, default=100)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.activations < 2 or args.repeats < 1: raise ValueError("positive finite experiment required")
    args.output.mkdir(parents=True, exist_ok=False)
    sources = sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module, "__file__", None) and Path(module.__file__).suffix == ".py" and
        Path(module.__file__).resolve().is_relative_to(ROOT)})
    before = {str(path.relative_to(ROOT)): sha(path) for path in sources}
    for path in sources:
        target = args.output / "source" / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True);shutil.copyfile(path, target)
    write(args.output / "plan.json", dict(schema="g31.regional_path_pool.pure_micro.v1",
        input=str(args.views.resolve()), input_sha256=sha(args.views), source_sha256=before,
        activations=args.activations, repeats=args.repeats,
        regime_order=["repeated_facts", "two_occupancies", "unique_occupancy"],
        order="alternating old/new by repeat; fresh pool for every measured arm",
        gc="enabled and unchanged", native_calls=0,
        interpretation="Saved public graph, declared synthetic repeats/occupancy changes; no actual flow hit rate or isolated timing claim."))
    with gzip.open(args.views, "rt", encoding="utf-8") as stream: views = json.load(stream)
    setup = time.perf_counter_ns()
    cases = scenarios(views, args.activations)
    setup_ns = time.perf_counter_ns()-setup
    reports = []
    for owner, regime, pairs, observations in cases:
        for repeat in range(args.repeats):
            measured, results = {}, {}
            for cached in ((False, True) if repeat % 2 == 0 else (True, False)):
                name = "pooled" if cached else "original"
                results[name], measured[name] = measure(observations, pairs, cached)
            if results["original"] != results["pooled"]: raise AssertionError("path differential failed")
            reports.append(dict(owner=owner, regime=regime, repeat=repeat, pairs=pairs,
                exact_paths=True, path_sha256=hashlib.sha256(repr(results["original"]).encode()).hexdigest(), **measured))
    changed = [str(path) for path in sources if sha(path) != before[str(path.relative_to(ROOT))]]
    receipt = dict(status="passed" if not changed else "unknown_source_changed", native_calls=0,
        source_changed=changed, plan_sha256=sha(args.output / "plan.json"), scenario_creation_ns=setup_ns,
        timed_scope="Fresh handle + every lazy key + lookup + miss solver + maintenance + result append. Observations prebuilt identically for both arms.",
        gc_enabled=gc.isenabled(), complete_request_100ms_certified=False, reports=reports)
    write(args.output / "receipt.json", receipt)
    if changed: raise RuntimeError("source changed")
    print(json.dumps(dict(status=receipt["status"], cases=len(reports), native_calls=0)))


if __name__ == "__main__": main()
