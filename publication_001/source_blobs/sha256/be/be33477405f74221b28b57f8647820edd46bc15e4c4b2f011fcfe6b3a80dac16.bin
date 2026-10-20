"""Offline conditional FIFO/carrier upper bound, never an online policy input."""
from __future__ import annotations
import argparse
from collections import defaultdict, deque
import gzip
import hashlib
import json
from pathlib import Path


def analyze(data):
    nodes = {r["node"]: r for r in data["node_contracts"]}
    edges = {(r["from"], r["to"]): r["capacity"] for r in data["edge_contracts"]}
    graph = defaultdict(list)
    for u, v, _, _ in data["edge_records"]:
        if edges[u, v] > 0 and nodes[u]["capacity"] > 0 and nodes[v]["capacity"] > 0:
            graph[u].append(v)
    witnesses = {}
    def stage(source, target):
        key = f"{source}->{target}"
        if key not in witnesses:
            paths = {source: [source]}; queue = deque([source])
            while queue:
                u = queue.popleft()
                for v in sorted(graph[u]):
                    if v not in paths: paths[v] = paths[u] + [v]; queue.append(v)
            witnesses[key] = {"source": source, "target": target, "reachable": target in paths,
                "positive_path": paths.get(target), "complete_reachable_set": sorted(paths)}
        return witnesses[key]["reachable"]
    population = sorted(data["jobs"], key=lambda j: (j["arrival"], j["business_bag_id"]))
    if len({j["business_bag_id"] for j in population}) != len(population): raise ValueError("duplicate_job")
    if len({(j["origin"], j["arrival"]) for j in population}) != len(population):
        raise ValueError("same_origin_arrival_ties_require_event_release_order_proof")
    loaders = defaultdict(list)
    for job in population:
        mandatory = ([job["origin"], job["storage_node"], job["destination"]]
                     if job["storage_node"] >= 0 else [job["origin"], job["destination"]])
        stages = [(a, b, stage(a, b)) for a, b in zip(mandatory, mandatory[1:])]
        loaders[job["origin"]].append({"business_bag_id": job["business_bag_id"], "arrival": job["arrival"],
            "mandatory_stages": [f"{a}->{b}" for a, b, _ in stages], "reachable": all(v for _, _, v in stages)})
    carriers = len(data["trays"])
    if carriers < 1: raise ValueError("no_carriers")
    rewards = {}; prefix_rows = []
    for origin, jobs in sorted(loaders.items()):
        bad = good = 0; reward = [0] * carriers
        for row in jobs:
            bad += not row["reachable"]; good += row["reachable"]
            row["unreachable_through_prefix"] = bad; row["reachable_through_prefix"] = good
            if bad < carriers: reward[bad] = good
        for b in range(1, carriers): reward[b] = max(reward[b], reward[b-1])
        rewards[origin] = reward
        prefix_rows.append({"origin": origin, "reward_by_at_most_bad": reward, "jobs_in_native_fifo_order": jobs})
    dp = [(0, {}) for _ in range(carriers)]; tables = []
    for origin, reward in sorted(rewards.items()):
        dp = [max(((dp[b-k][0] + reward[k], {**dp[b-k][1], str(origin): k}) for k in range(b+1)),
                  key=lambda pair: pair[0]) for b in range(carriers)]
        tables.append({"through_origin": origin, "max_reachable_by_bad_budget": [v for v, _ in dp]})
    # Independent formulation: enumerate every physical loader prefix as a
    # choice; retain the best reachable count at each exact trapped-load cost.
    reference = {0: 0}
    for origin, jobs in sorted(loaders.items()):
        choices = {(0, 0)} | {(r["unreachable_through_prefix"], r["reachable_through_prefix"])
                               for r in jobs if r["unreachable_through_prefix"] < carriers}
        following = {}
        for used, value in reference.items():
            for cost, gain in choices:
                if used + cost < carriers:
                    following[used+cost] = max(following.get(used+cost, -1), value+gain)
        reference = following
    assert dp[-1][0] == max(reference.values())
    return {"schema": "g31.fixed_contract_carrier_bound.v1", "status": "conditional_static_necessary_upper_bound",
        "offered": len(population), "carriers": carriers, "topologically_reachable": sum(r["reachable"] for a in loaders.values() for r in a),
        "zero_unreachable_load_prefix_bound": sum(r[0] for r in rewards.values()),
        "completion_upper_bound": dp[-1][0], "relaxed_bad_allocation": dp[-1][1], "independent_prefix_dp_agrees": True,
        "same_origin_arrival_tie_groups": 0,
        "loaders": prefix_rows, "stages": witnesses, "dp_tables": tables,
        "conditions": ["All mandatory stages preserve fixed positive-capacity directed graph and service goals.",
            "One physical tray per loaded job until required destination unload and hold; no loaded offload/cancel/recovery.",
            "Source loading is FIFO by (arrival,business_bag_id); later releases cannot precede older waiting heads.",
            "This input has no equal-arrival pairs at one origin; per-event release cannot reverse the stated prefix order.",
            "No new trays; all existing carriers counted, including failed/quarantined loaded trays."],
        "proof": "Immediately before the last reachable completion, its carrier is still occupied by that reachable job, so at most N-1 permanently unreachable jobs have loaded. Loaded jobs at each origin form a FIFO prefix. Maximize the reachable jobs in all such prefixes with total unreachable count <=N-1. Queue/berth/timing/return constraints are relaxed, never enlarged into a feasibility claim.",
        "online_use": False, "realizable_schedule_proved": False, "strict_protection_proved": False}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--input", type=Path, required=True); p.add_argument("--output", type=Path, required=True)
    args = p.parse_args(); data = json.load(gzip.open(args.input, "rt")); result = analyze(data)
    args.output.mkdir(parents=True, exist_ok=False)
    result["input_path"] = str(args.input.resolve()); result["input_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    result["analyzer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with gzip.open(args.output / "analysis.json.gz", "wt", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, allow_nan=False)
    (args.output / "analyzer.py").write_bytes(Path(__file__).read_bytes())
    summary = {k: v for k, v in result.items() if k not in {"loaders", "stages", "dp_tables"}}
    summary["analysis_sha256"] = hashlib.sha256((args.output / "analysis.json.gz").read_bytes()).hexdigest()
    (args.output / "receipt.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("status", "offered", "topologically_reachable", "zero_unreachable_load_prefix_bound", "completion_upper_bound")}))


if __name__ == "__main__": main()
