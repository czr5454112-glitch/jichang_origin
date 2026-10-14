"""Routing-only real-topology proxy; no empty-tray operational assumptions.

Example staged run:
  python -m scripts.experiments.ics_circulation_v3.nanning_routing_benchmark --od-count 8
  python -m scripts.experiments.ics_circulation_v3.nanning_routing_benchmark --od-count 100
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import asdict
import hashlib
from heapq import heappop, heappush
import json
import math
from pathlib import Path
import platform
from statistics import mean
from time import perf_counter

from .audit_nanning import DEFAULT_PROFILE
from .experiment_protocol import check_output_directory, create_output_directory
from .model import Bag, Edge, FixedLocalModule, Network, Node, Snapshot, Tray
from .routing import RegionalCandidateGenerator, clear_static_cache
from .runtime import ExecutionValidator

ROOT = Path(__file__).resolve().parents[3]


def static_distances(edges: list[tuple[str, str, int]], source: str) -> dict[str, int]:
    """Independent physical-graph Dijkstra reference, not the planner's cache."""
    adjacency = defaultdict(list)
    for start, end, travel in edges:
        adjacency[start].append((end, travel))
    result = {source: 0}
    queue = [(0, source)]
    while queue:
        value, node = heappop(queue)
        if value != result[node]:
            continue
        for end, travel in adjacency[node]:
            proposed = value + travel
            if proposed < result.get(end, math.inf):
                result[end] = proposed
                heappush(queue, (proposed, end))
    return result


def synthetic_partitions(node_ids: list[str], edges: list[tuple[str, str, int]], count: int) -> dict[str, str]:
    """Farthest-point hop seeds, then deterministic multi-source hop Voronoi.

    The undirected graph is used only to synthesize control regions. Physical
    routing preserves every edge's original direction. Disconnected components
    receive seeds before already covered components; uncovered components are
    explicitly assigned their own region rather than guessed adjacency.
    """
    if not 1 <= count <= len(node_ids):
        raise ValueError("partition count must be within the node population")
    neighbors = defaultdict(set)
    for start, end, _ in edges:
        neighbors[start].add(end)
        neighbors[end].add(start)
    seeds, nearest = [], {node: math.inf for node in node_ids}
    for _ in range(count):
        seed = min(node_ids, key=lambda node: (-nearest[node], node))
        seeds.append(seed)
        queue, distance = deque([seed]), {seed: 0}
        while queue:
            node = queue.popleft()
            nearest[node] = min(nearest[node], distance[node])
            for target in sorted(neighbors[node]):
                if target not in distance:
                    distance[target] = distance[node] + 1
                    queue.append(target)
    assigned = {}
    queue = [(0, index, seed) for index, seed in enumerate(seeds)]
    # Seed rank and then node ID deterministically resolve equal-hop ties.
    import heapq
    heapq.heapify(queue)
    while queue:
        distance, region, node = heappop(queue)
        if node in assigned:
            continue
        assigned[node] = f"synthetic:{region:02d}"
        for neighbor in sorted(neighbors[node]):
            if neighbor not in assigned:
                heappush(queue, (distance + 1, region, neighbor))
    for node in node_ids:
        if node not in assigned:
            assigned[node] = f"isolated:{node}"
    return assigned


def load_routing_proxy(profile_path: Path, partition_count: int, *, tick_seconds: float = 1., node_capacity: int = 4):
    if tick_seconds <= 0 or node_capacity < 1:
        raise ValueError("tick_seconds and node_capacity must be positive")
    raw = profile_path.read_bytes()
    profile = json.loads(raw.decode("utf-8-sig"))
    source_nodes = {str(row["location"]): row for row in profile["nodes"]}
    if len(source_nodes) != len(profile["nodes"]):
        raise ValueError("Duplicate source node IDs")
    all_edges, active_edges, excluded = [], [], []
    for row in profile["edges"]:
        start, end = str(row["start"]), str(row["end"])
        travel_seconds = float(row["length"]) / float(row["speed"])
        if not math.isfinite(travel_seconds) or travel_seconds <= 0:
            raise ValueError("Source travel time must be finite and positive")
        travel = math.ceil(travel_seconds / tick_seconds)
        all_edges.append((start, end, travel))
        capacity = row.get("capacity")
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 0:
            raise ValueError("Missing/noninteger source capacity: no implicit capacity uplift is permitted")
        if capacity == 0:
            excluded.append({"start": start, "end": end, "capacity": 0, "reason": "closed_in_proxy"})
            continue
        if start not in source_nodes or end not in source_nodes:
            raise ValueError("Source edge endpoint missing")
        active_edges.append(Edge(f"{start}->{end}", start, end, travel, capacity))
    directed = [(edge.source, edge.target, edge.travel_time) for edge in active_edges]
    partitions = synthetic_partitions(sorted(source_nodes), directed, partition_count)
    nodes = {key: Node(key, str(row.get("system_key", "unknown_logistics_system")), partitions[key],
                       capacity=node_capacity, can_wait=True) for key, row in source_nodes.items()}
    loaders = sorted(key for key, row in source_nodes.items() if row["node_type"] == 1)
    unloaders = sorted(key for key, row in source_nodes.items() if row["node_type"] == 2)
    before, after = [], []
    for start in loaders:
        original, positive = static_distances(all_edges, start), static_distances(directed, start)
        before.extend((start, end) for end in unloaders if end in original)
        after.extend((start, end, positive[end]) for end in unloaders if end in positive)
    metadata = {
        "source_path": str(profile_path.resolve()), "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_node_count": len(source_nodes), "source_edge_count": len(profile["edges"]),
        "active_edge_count": len(active_edges), "closed_zero_capacity_edges": excluded,
        "loader_count": len(loaders), "unloader_count": len(unloaders),
        "all_loader_unloader_od_count": len(loaders) * len(unloaders),
        "reachable_od_before_zero_closure": len(before), "reachable_od_after_zero_closure": len(after),
        "lost_reachable_od_pairs": sorted(set(before) - {(start, end) for start, end, _ in after}),
        "requested_partitions": partition_count, "actual_partitions": len(set(partitions.values())),
        "partition_sizes": dict(sorted(Counter(partitions.values()).items())), "node_partitions": partitions,
        "proxy_flags": {
            "scope": "real_source_topology_routing_only_synthetic_resource_semantics",
            "partition_algorithm": "undirected_hop_farthest_seeds_then_nearest_seed_hop_voronoi_lexicographic_ties",
            "partition_is_field_control_boundary": False,
            "tick_seconds": tick_seconds, "travel_conversion": "ceil((source_length/source_speed)/tick_seconds)",
            "positive_edge_capacity": "preserved_recorded_integer_not_validated_as_calendar_occupancy_semantics",
            "zero_capacity": "edge_closed_without_uplift",
            "node_capacity": node_capacity, "node_capacity_source": "synthetic_constant_unknown_in_source",
            "can_wait": "all_nodes_true_synthetic_permission_not_confirmed",
            "node_service_time": "excluded_in_route_only_proxy_not_claimed_zero_in_airport",
            "unload_ticks": 0, "local_module_hold": 0, "initial_trays": "one_loaded_tray_per_independent_OD",
            "dynamic_congestion": "none", "forecast_or_empty_business_parameters": "not_supplied",
            "physical_and_permission_validation": "original_proxy_ExecutionValidator_not_supplier_authorization",
        },
    }
    return Network(nodes, {edge.edge_id: edge for edge in active_edges}), sorted(after, key=lambda row: (row[2], row[0], row[1])), metadata


def _quantiles(values):
    values = sorted(values)
    return {"count": len(values), "mean": mean(values) if values else None,
            **{label: values[round((len(values) - 1) * q)] if values else None
               for label, q in (("p50", .5), ("p95", .95), ("p99", .99), ("max", 1.))}}


def benchmark(profile_path: Path, output: Path, *, od_count: int = 100,
              partition_counts=(4, 8, 16), k: int = 3, expansion_limit: int = 5000,
              deadline_ms: float = 80., repeat_count: int = 1) -> dict:
    output = check_output_directory(output)
    if min(od_count, repeat_count, k, expansion_limit) < 1 or (deadline_ms is not None and deadline_ms <= 0):
        raise ValueError("OD, repeat, candidate, expansion and deadline bounds must be positive")
    if not partition_counts or len(set(partition_counts)) != len(partition_counts):
        raise ValueError("Partition counts must be nonempty and distinct")
    prepared = []
    for partition_count in partition_counts:
        begin = perf_counter()
        network, available, metadata = load_routing_proxy(profile_path, partition_count)
        metadata["offline_proxy_and_partition_build_ms"] = (perf_counter() - begin) * 1000
        if not available:
            raise ValueError("No reachable loader-to-unloader OD after declared edge closures")
        prepared.append((partition_count, network, available, metadata))
    output = create_output_directory(output)
    records, topologies = [], []
    for partition_count, network, available, metadata in prepared:
        selected_count = min(od_count, len(available))
        indices = sorted({round(index * (len(available) - 1) / max(1, selected_count - 1)) for index in range(selected_count)})
        selected = [available[index] for index in indices]
        metadata["selected_od_count"] = len(selected)
        metadata["selection"] = "even_quantiles_of_static_distance_sorted_reachable_OD_list"
        topologies.append(metadata)
        clear_static_cache()
        for repeat in range(repeat_count):
            for index, (source, target, reference) in enumerate(selected):
                bag = Bag("route_bag", source, target, 0, reference + 120)
                state = Snapshot(0, network, {"route_tray": Tray("route_tray", source, "loaded", bag.bag_id)},
                                 {bag.bag_id: bag}, module=FixedLocalModule(unload_ticks=0, reception_capacity=1))
                horizon = reference + max(120, math.ceil(reference * .25))
                generator = RegionalCandidateGenerator(horizon=horizon, expansion_limit=expansion_limit,
                                                       static_path_limit=max(12, k * 4), deadline_ms=deadline_ms)
                started = perf_counter()
                candidates = generator.generate(state, bag.bag_id, "route_tray", k)
                generation_ms = (perf_counter() - started) * 1000
                validation_started = perf_counter()
                validator = ExecutionValidator()
                validations = [validator.validate(state, candidate) for candidate in candidates]
                validation_ms = (perf_counter() - validation_started) * 1000
                commit_started = perf_counter()
                committed = validator.commit(state, candidates[0]).accepted if candidates else False
                commit_ms = (perf_counter() - commit_started) * 1000
                request_ms = (perf_counter() - started) * 1000
                best_arrival = min((candidate.legs[-1].arrive if candidate.legs else 0 for candidate in candidates), default=None)
                records.append({"partitions": partition_count, "repeat": repeat, "od_index": index,
                                "source": source, "target": target, "horizon_ticks": horizon,
                                "static_dijkstra_reference_ticks": reference, "best_candidate_arrival_ticks": best_arrival,
                                "static_shortest_match": best_arrival == reference if candidates else None,
                                "candidate_count": len(candidates), "requested_candidates": k,
                                "candidate_paths": [[leg.edge_id for leg in candidate.legs] for candidate in candidates],
                                "all_candidates_valid": all(value.accepted for value in validations) if candidates else None,
                                "status": "new_route_success" if committed else generator.last_search_status,
                                "search_status": generator.last_search_status, "committed": committed,
                                "cold_static_cache_request": repeat == 0 and index == 0,
                                "generation_ms": generation_ms, "validation_ms": validation_ms, "commit_ms": commit_ms,
                                "local_request_ms": request_ms, "local_over_100ms": request_ms >= 100,
                                "distributed_end_to_end_ms": None, "diagnostics": generator.last_diagnostics})
    grouped = {}
    for partition_count in partition_counts:
        rows = [row for row in records if row["partitions"] == partition_count]
        successful = [row for row in rows if row["committed"]]
        grouped[str(partition_count)] = {
            "request_count": len(rows), "successful_requests": len(successful),
            "failed_requests": len(rows) - len(successful),
            "outcomes": dict(Counter(row["status"] for row in rows)),
            "search_statuses": dict(Counter(row["search_status"] for row in rows)),
            "full_k_candidate_requests": sum(row["candidate_count"] == k for row in rows),
            "shortest_reference_matches": sum(row["static_shortest_match"] is True for row in rows),
            "shortest_reference_mismatches": sum(row["static_shortest_match"] is False for row in rows),
            "local_over_100ms": sum(row["local_over_100ms"] for row in rows),
            "timing_ms_all_requests_including_failures": {key: _quantiles([row[key] for row in rows])
                                                         for key in ("generation_ms", "validation_ms", "commit_ms", "local_request_ms")},
        }
    summary = {
        "schema": "ics_v3_nanning_regional_routing_only_v1", "scope": "routing_only_proxy_not_two_requirements_acceptance",
        "requested_unique_od_count_per_partition": od_count, "repeat_count": repeat_count,
        "requested_candidate_count": k, "expansion_limit": expansion_limit, "deadline_ms": deadline_ms,
        "total_requests": len(records), "by_partition": grouped, "topology_proxies": topologies,
        "limits": ["No flight demand, tray population, local supplier module or circulation business parameters added",
                   "No dynamic congestion: this baseline checks static abstraction, legal refinement and local timing",
                   "Each OD is independently initialized; repetitions are not independent operating days",
                   "One static local shortest witness per portal pair may omit feasible alternative local paths",
                   "Candidate count shortage and exhausted budgets are not global physical infeasibility",
                   "Request time includes generation, full validation and commit, excludes offline topology partition construction",
                   "No network communication, distributed edge process or airport 100 ms guarantee is measured",
                   "Explosive reference time-expanded planner was not run on large horizon real-map cases; physical Dijkstra is an independent static path reference"],
        "source_sha256": {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                          for name in ("experiment_protocol.py", "audit_nanning.py", "routing.py", "nanning_routing_benchmark.py", "runtime.py", "model.py")},
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "requests.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in records), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--od-count", type=int, default=100)
    parser.add_argument("--partitions", type=int, nargs="+", default=[4, 8, 16])
    parser.add_argument("--candidate-count", type=int, default=3)
    parser.add_argument("--expansion-limit", type=int, default=5000)
    parser.add_argument("--deadline-ms", type=float, default=80.)
    parser.add_argument("--repeat-count", type=int, default=1)
    args = parser.parse_args()
    output = args.output or ROOT / "outputs/experiments/ics_circulation_v3" / f"nanning_routing_{args.od_count}od_20261009"
    result = benchmark(args.profile, output, od_count=args.od_count, partition_counts=tuple(args.partitions),
                       k=args.candidate_count, expansion_limit=args.expansion_limit,
                       deadline_ms=args.deadline_ms, repeat_count=args.repeat_count)
    print(json.dumps({key: result[key] for key in ("total_requests", "by_partition")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
