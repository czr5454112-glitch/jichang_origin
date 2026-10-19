"""Independent unbounded recursive check of the completed bag0 static domain.

Uses reverse distance labels and recursive path enumeration, not the producer's
forward shortest paths, explicit stack, or budget stopping implementation.
"""
import argparse
import gzip
import heapq
import json
from pathlib import Path
from .original_workload import digest, write_json


def verify(input_file, evidence):
    data = json.load(gzip.open(input_file, "rt"))
    produced = json.load(gzip.open(evidence / "complete_path_census.json.gz", "rt"))["0:53"]
    services = {r[0]: max(.001, r[2]) for r in data["node_records"]}
    closed = {(r["from"], r["to"]) for r in data["edge_contracts"] if r["capacity"] <= 0}
    graph = {n: [] for n in services}; reverse = {n: [] for n in services}
    for u, v, length, speed in data["edge_records"]:
        if (u, v) not in closed:
            weight = services[u] + max(.001, length / speed)
            graph[u].append((v, weight)); reverse[v].append((u, weight))
    distances, queue = {53: 0.}, [(0., 53)]
    while queue:
        cost, node = heapq.heappop(queue)
        if cost != distances[node]: continue
        for previous, weight in reverse[node]:
            alternate = cost + weight
            if alternate < distances.get(previous, float("inf")):
                distances[previous] = alternate; heapq.heappush(queue, (alternate, previous))
    allowed = {}
    for node, edges in graph.items():
        if node == 53 or node not in distances: allowed[node] = []
        elif services[node] == 2.:
            allowed[node] = sorted(v for v, _ in edges if v in distances)
        else:
            allowed[node] = [min(edges, key=lambda e: (e[1] + distances.get(e[0], float("inf")), e[0]))[0]]
    counts = {"states": 0, "terminals": 0, "cycle_extensions": 0}
    paths = set()
    def visit(node, seen, path):
        counts["states"] += 1
        if node == 53:
            counts["terminals"] += 1; paths.add(path); return
        for target in allowed[node]:
            if target in seen: counts["cycle_extensions"] += 1
            else: visit(target, seen | {target}, path + (target,))
    visit(0, {0}, (0,))
    expected = {tuple(row["path"]) for row in produced["paths"]}
    checks = {"path_sets_equal": paths == expected, "no_duplicate_produced_paths": len(expected) == len(produced["paths"]),
        "natural_stack_exhaustion": produced["frontier"] == [] and produced["coverage_complete"],
        "state_count_equal": counts["states"] == produced["states_expanded"],
        "cycle_count_equal": counts["cycle_extensions"] == produced["rejected_extensions"]["simple_prefix_cycle"],
        "strictly_below_budget": counts["states"] < produced["budget"]["partial_states"]}
    report = {"schema": "g31.lt2.original_tie_paths_independent_check.v1", "status": "verified" if all(checks.values()) else "failed",
        "native_calls": 0, "counts": counts, "checks": checks, "missing_paths": len(paths - expected), "extra_paths": len(expected - paths),
        "input_sha256": digest(input_file), "producer_census_sha256": digest(evidence / "complete_path_census.json.gz"),
        "verifier_sha256": digest(Path(__file__)), "scope": "only completed0:53 domain; four other cappedsource domains remain unknown; static, not live execution"}
    write_json(evidence / "independent_bag0_completeness.json", report)
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True); p.add_argument("--evidence", type=Path, required=True)
    a = p.parse_args(); print(json.dumps(verify(a.input, a.evidence), indent=2))
