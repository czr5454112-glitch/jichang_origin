"""Exact static directed-reachability certificate from immutable full input."""
import argparse
import gzip
import hashlib
import heapq
import json
from pathlib import Path


def analyze(data, result):
    nodes = {n[0]: n for n in data["node_records"]}
    edges = {(e["from"], e["to"]): e for e in data["edge_contracts"]}
    adjacency = {n: [] for n in nodes}
    closed = []
    for source, target, length, speed in data["edge_records"]:
        if edges[source, target]["capacity"] > 0:
            adjacency[source].append((target, max(.001, length/speed) + max(.001, nodes[target][2])))
        else: closed.append([source, target])
    def search(forbidden):
        queue, distances, paths, settled = [(0., 53)], {53: 0.}, {53: [53]}, set()
        while queue:
            cost, source = heapq.heappop(queue)
            if source in settled: continue
            settled.add(source)
            for target, duration in adjacency[source]:
                if target in forbidden: continue
                proposed = cost + duration
                if proposed < distances.get(target, float("inf")):
                    distances[target] = proposed; paths[target] = paths[source] + [target]
                    heapq.heappush(queue, (proposed, target))
        # Exhaust the complete reachable set even after reaching the goal.
        boundary = sorted({(u, v) for u in settled for v, _ in adjacency[u] if v not in settled})
        return {"forbidden_nodes": sorted(forbidden), "goal_reachable": 116 in settled,
            "path": paths.get(116), "estimated_service_travel_seconds": distances.get(116),
            "settled_node_count": len(settled), "reachable_nodes": sorted(settled),
            "outgoing_cut_boundary": [list(e) for e in boundary], "natural_queue_exhaustion": not queue,
            "visited_state_budget": "none; finite graph exhausted"}
    candidates = {"default": search(set()), "bypass28_29": search({28, 29}), "remove112": search({112})}
    return {"schema": "g31.original_static_bypass_certificate.v1", "scope": "offline immutable positive-capacity public graph; no dynamic or online permission claim",
        "source": 53, "goal": 116, "edge_domain": "all original directed edges with unchanged declared capacity>0",
        "closed_edges_retained": closed, "searches": candidates,
        "node112_is_mandatory_for_53_to116_in_this_graph": candidates["default"]["goal_reachable"] and not candidates["remove112"]["goal_reachable"],
        "critical_node_contracts": [n for n in data["node_contracts"] if n["node"] in (28, 29, 53, 112)],
        "candidate_final_occupants": {str(n): [t for t in result["trays"] if t["node"] == n and t["edge_to"] < 0] for n in (28, 29, 53, 112)},
        "limitations": ["static estimate includes downstream node services, excludes starting node53 service and all load/unload/queue/headway waits",
            "bypass is not a granted full suffix; every later deviation would still require current-owner local2s message execution and ACK",
            "bypass rejoins112, already occupied by4loadedtrays atH22200; no completion or strict protection demonstrated",
            "closed edges, FIFO, Storage gates, all28506jobs and22trays remain unchanged"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = {name: args.campaign/(name+".json.gz") for name in ("input", "candidate")}
    data = {name: json.load(gzip.open(path, "rt", encoding="utf-8")) for name, path in paths.items()}
    report = analyze(data["input"], data["candidate"]["result"])
    report["source_sha256"] = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths.values()}
    report["analysis_source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if args.output.exists(): raise ValueError("bypass:immutable_output_exists")
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: {x: v[x] for x in ("goal_reachable", "path", "settled_node_count", "outgoing_cut_boundary")}
        for k, v in report["searches"].items()}, indent=2))


if __name__ == "__main__": main()
