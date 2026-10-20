"""Pure public-static path benchmark; no native session or online integration."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

from .analytic_control import PublicTravel
from .public_travel_pool import PublicTravelPool


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def execute(observation, owners, nodes, width, pooled):
    pool = PublicTravelPool(max_graphs=len(owners)) if pooled else None
    outputs = []
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    for activation in range(128):
        current = {**observation, "owner_id": owners[activation % len(owners)], "now": float(activation)}
        travel = pool.checkout(current) if pooled else PublicTravel(current)
        # Fixed, outcome-independent query schedule, identical in both arms.
        for j in range(width):
            source = nodes[(j * 7 + activation % 8) % len(nodes)]
            target = nodes[(j * 17 + 13 + activation % 8) % len(nodes)]
            cost, path = travel.path(source, target)
            outputs.append((cost.hex(), path, travel.complete(source, target).hex()))
    elapsed = {"wall_ns": time.perf_counter_ns() - wall,
               "cpu_ns": time.process_time_ns() - cpu}
    elapsed.update(checkouts=128, queries=128 * width,
                   cache_hits=pool.hits if pool else 0, cache_misses=pool.misses if pool else 0)
    return outputs, elapsed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__), Path(__file__).with_name("public_travel_pool.py"),
               Path(__file__).with_name("analytic_control.py")]
    before = {str(p): sha(p) for p in sources}
    data = json.load(gzip.open(args.input, "rt", encoding="utf-8"))
    owners = sorted({n.get("resource_owner", n["zone"]) for n in data["node_contracts"]})
    observation = {key: data[key] for key in ("node_records", "edge_records", "edge_contracts")}
    observation["known_faults"] = []  # No future input fault tape is consumed.
    del data
    nodes = sorted({int(row[0]) for row in observation["node_records"]})
    (args.output / "public_static_observation.json").write_text(json.dumps(observation, indent=2), encoding="utf-8")
    cases = []
    for width in (1, 24):
        expected = None
        for replicate in range(3):
            pair = {}
            # Alternate serial order; every pool starts cold for its own arm.
            for pooled in ((False, True) if replicate % 2 == 0 else (True, False)):
                rows, timing = execute(observation, owners, nodes, width, pooled)
                if expected is None:
                    expected = rows
                if rows != expected:
                    raise ValueError("travel_pool:oracle_mismatch")
                timing["ordered_output_sha256"] = hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()
                pair["pooled" if pooled else "fresh"] = timing
            cases.append({"queries_per_activation": width, "replicate": replicate,
                "ordered_outputs_exact": True, "arms": pair,
                "wall_change_fraction": pair["pooled"]["wall_ns"] / pair["fresh"]["wall_ns"] - 1,
                "cpu_change_fraction": pair["pooled"]["cpu_ns"] / pair["fresh"]["cpu_ns"] - 1})
    changed = [str(p) for p in sources if sha(p) != before[str(p)]]
    result = {"schema": "g31.public_travel_pool_pure_benchmark.v1", "status": "passed" if not changed else "source_changed",
        "input": str(args.input.resolve()), "input_sha256": sha(args.input), "source_before": before,
        "source_changed": changed, "owners": owners, "nodes": len(nodes), "edges": len(observation["edge_records"]),
        "cases": cases, "native_workers": 0, "controller_integrated": False,
        "scope": "Pure original public static topology; fixed synthetic queries, full key construction/checkouts/copies/searches/output row construction timed in both arms. Empty known-fault view. No job or future fault data used.",
        "limitations": "Concurrent parent simulations prevent isolated wall benchmark; this is not an actual controller tape or full-request/100ms test. Key and view cost are included; input parsing and result hashing are outside both arms."}
    (args.output / "receipt.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "cases": [{k: c[k] for k in ("queries_per_activation", "replicate", "wall_change_fraction", "cpu_change_fraction")} for c in cases]}))


if __name__ == "__main__":
    main()
