"""Bounded pure enumeration of simple paths using only original two-second ties.

This is offline hypothesis construction, not an installed full-suffix grant.
Each selected deviation would require a new current-owner observation, a new
two-second command, native revalidation, ACK and actual edge audit.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
from . import research_r1 as r1
from . import original_command_window_census as single
from .original_workload import digest, write_json

MAX_STATES_PER_SOURCE = 100000
MAX_TERMINALS_PER_SOURCE = 50000


def enumerate_paths(graph, services, origin, storage, *, max_states=MAX_STATES_PER_SOURCE,
                    max_terminals=MAX_TERMINALS_PER_SOURCE):
    default = {u: r1.shortest_path(graph, u, storage) for u in graph}
    baseline = default[origin]
    if not baseline:
        return {"status": "unreachable_storage", "paths": [], "states_expanded": 0, "frontier": []}
    pending = [((origin,), 0., ())]
    expanded, rejected, paths = 0, Counter(), []
    while pending and expanded < max_states and len(paths) < max_terminals:
        path, cost, commands = pending.pop()
        expanded += 1
        node = path[-1]
        if node == storage:
            paths.append({"path": list(path), "free_flow_seconds": cost,
                "additional_free_flow_seconds": cost - single.path_cost(graph, baseline),
                "command_count": len(commands), "commands": [dict(zip(("from", "next"), c)) for c in commands],
                "native_executability": "unknown_same_timestamp_commands", "physical_protection": "unknown"})
            continue
        route = default[node]
        if not route:
            rejected["no_static_continuation"] += 1
            continue
        ordinary = route[1]
        choices = graph[node] if services[node] == single.COMMAND_DELAY else [(v, w) for v, w in graph[node] if v == ordinary]
        # Stack reverse gives deterministic ascending-next DFS, not outcome order.
        for target, weight in reversed(choices):
            if target in path:
                rejected["simple_prefix_cycle"] += 1
                continue
            if not default[target]:
                rejected["no_static_continuation"] += 1
                continue
            next_commands = commands + ((node, target),) if target != ordinary else commands
            pending.append((path + (target,), cost + weight, next_commands))
    return {"status": "complete_finite_simple_domain" if not pending else "unknown_budget_frontier",
        "origin": origin, "storage": storage, "canonical_path": list(baseline),
        "baseline_free_flow_seconds": single.path_cost(graph, baseline), "states_expanded": expanded,
        "candidate_path_count": len(paths), "rejected_extensions": dict(rejected), "paths": paths,
        "frontier": [{"prefix": list(p), "cost": c, "commands": [list(q) for q in commands]} for p, c, commands in pending],
        "budget": {"partial_states": max_states, "terminal_paths": max_terminals},
        "coverage_complete": not pending, "continuous_or_live_optimality": "unknown"}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--census", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    data = json.load(gzip.open(args.input, "rt"))
    original = json.load(gzip.open(args.census / "complete_static_census.json.gz", "rt"))
    diagnosis = json.loads((args.census / "offline_receipt_diagnosis.json").read_text())
    if digest(args.input) != original["source_input"]["sha256"]:
        raise ValueError("tie_paths:input_identity")
    keys = sorted(original["unreachable_cohort_stage_keys"], key=lambda s: tuple(map(int, s.split(":"))))
    protocol = {"schema": "g31.lt2.original_two_second_paths.v1", "native_calls": 0,
        "offered_denominator": original["offered_denominator"], "unreachable_cohort_count": original["unreachable_cohort_count"],
        "source_cohort": "all eleven pre-Storage source paths in the full4001-unreachable census;1877 noStorage contracts remain outside this pre-Storage hypothesis",
        "stage_keys": keys, "max_states_per_source": MAX_STATES_PER_SOURCE,
        "max_terminal_paths_per_source": MAX_TERMINALS_PER_SOURCE,
        "selection": "for observed unreachable head only: simple terminal path with delay strictly exceeding recorded first-reachable gap; fewest commands then minimum path cost then lexicographic full path",
        "deviations": "only nodes with public service exactly2s; all other nodes follow unconstrained static shortest next; positive-capacity edges only; no repeated full-prefix node",
        "action_contract": "every future intent issued only at actual current local node with actual generation/traversal;2s wire then native revalidation; no preissue, pause, full-suffix grant or delay reduction",
        "source_input_sha256": digest(args.input), "script_sha256": digest(Path(__file__)),
        "offline_receipt_sha256": digest(args.census / "offline_receipt_diagnosis.json"),
        "claim_limits": ["S4 live queues may choose different uncommanded edges", "exact-tie executability unknown until native", "unfinished-vs-unfinished protection stays unknown"]}
    write_json(args.output / "preregistered_protocol.json", protocol)
    graph = r1.positive_graph(data); services = {r[0]: max(.001, r[2]) for r in data["node_records"]}
    stages = {key: enumerate_paths(graph, services, *map(int, key.split(":"))) for key in keys}
    selections = []
    jobs = {j["business_bag_id"]: j for j in data["jobs"]}
    for head in diagnosis["storage_heads"]:
        job = jobs[head["actual_first_head"]["business_bag_id"]]
        stage = stages[f"{job['origin']}:{job['storage_node']}"]
        eligible = [r for r in stage["paths"] if r["additional_free_flow_seconds"] > head["required_strict_delay"]]
        best = min(eligible, key=lambda r: (r["command_count"], r["free_flow_seconds"], r["path"])) if eligible else None
        selections.append({"business_bag_id": job["business_bag_id"], "required_delay": head["required_strict_delay"],
            "eligible_enumerated_paths": len(eligible), "selected_offline_hypothesis": best,
            "status": "candidate_requires_native_gate" if best else "no_candidate_in_complete_static_domain" if stage["coverage_complete"] else "unknown_unexplored_frontier",
            "native_business_reordering": "unknown", "full_population_protection": "unknown"})
    with gzip.open(args.output / "complete_path_census.json.gz", "wt", encoding="utf-8") as out:
        json.dump(stages, out, allow_nan=False)
    summary = {"schema": protocol["schema"], "native_calls": 0, "offered_denominator": original["offered_denominator"],
        "unreachable_cohort_count": original["unreachable_cohort_count"], "stages": {k: {a: b for a, b in v.items() if a not in ("paths", "frontier")}
            for k, v in stages.items()}, "selected_hypotheses": selections}
    write_json(args.output / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
