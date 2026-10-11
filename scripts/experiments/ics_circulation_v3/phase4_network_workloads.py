"""Original Nanning topology plus explicit finite-tray workload proxies.

No edge is added, reversed or capacity-uplifted. Missing operating parameters
remain declared assumptions. Historical projected bags are not Nanning traffic
observations, and their early-bag EBS lifecycle is not implemented here.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, replace
from heapq import heappop, heappush
import hashlib
import json
import math
from pathlib import Path

from .audit_nanning import DEFAULT_PROFILE
from .learning import RoutingDemandForecast
from .model import Bag, FixedLocalModule, Network, Snapshot, Tray
from .nanning_routing_benchmark import load_routing_proxy
from .phase4_control import ControlSpec, GeneratorFactory
from .runtime import Simulation, assert_invariants


@dataclass(frozen=True)
class NetworkAssumptions:
    tick_seconds: float = 10.0
    node_capacity: int = 2
    partition_count: int = 8
    no_wait_divert_modulus: int = 3
    unload_ticks: int = 1
    reception_capacity: int = 1
    export_min_stock: int = 0

    def __post_init__(self):
        if not math.isfinite(self.tick_seconds) or self.tick_seconds <= 0:
            raise ValueError("tick_seconds must be finite and positive")
        if any(type(v) is not int or v < 1 for v in
               (self.node_capacity, self.partition_count, self.reception_capacity)):
            raise ValueError("capacities and partitions must be positive integers")
        if any(type(v) is not int or v < 0 for v in
               (self.no_wait_divert_modulus, self.unload_ticks, self.export_min_stock)):
            raise ValueError("proxy wait modulus, service and minimum stock must be nonnegative integers")


@dataclass(frozen=True)
class NetworkWorkload:
    name: str
    initial: Snapshot
    forecasts: tuple
    future_bags: tuple  # Evaluation engine only; never a controller argument.
    horizon: int
    provenance: dict


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shortest_paths(network, source):
    """Independent static directed witnesses; no scheduling/infeasibility claim."""
    adjacency = defaultdict(list)
    for edge in network.edges.values():
        if edge.capacity > 0:
            adjacency[edge.source].append(edge)
    distance, witnesses, queue = {source: 0}, {source: ()}, [(0, source)]
    while queue:
        value, node = heappop(queue)
        if value != distance[node]:
            continue
        for edge in sorted(adjacency[node], key=lambda e: e.edge_id):
            target_value = value + edge.travel_time
            if target_value < distance.get(edge.target, math.inf):
                distance[edge.target] = target_value
                witnesses[edge.target] = witnesses[node] + (edge.edge_id,)
                heappush(queue, (target_value, edge.target))
    return distance, witnesses


def load_network(profile_path=DEFAULT_PROFILE, assumptions=NetworkAssumptions()):
    profile_path = Path(profile_path)
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    network, _, previous = load_routing_proxy(profile_path, assumptions.partition_count,
        tick_seconds=assumptions.tick_seconds, node_capacity=assumptions.node_capacity)
    raw_nodes = {str(n["location"]): n for n in profile["nodes"]}
    no_wait = sorted(key for key, n in raw_nodes.items() if assumptions.no_wait_divert_modulus and
                     n["node_type"] == 4 and int(key) % assumptions.no_wait_divert_modulus == 0)
    nodes = {key: replace(node, can_wait=key not in no_wait) for key, node in network.nodes.items()}
    network = Network(nodes, network.edges)
    loaders = sorted(key for key, n in raw_nodes.items() if n["node_type"] == 1)
    unloaders = sorted(key for key, n in raw_nodes.items() if n["node_type"] == 2)
    paths = {key: shortest_paths(network, key) for key in set(loaders + unloaders)}
    pairs = []
    for origin in loaders:
        for destination in unloaders:
            outward = paths[origin][0].get(destination)
            returning = paths[destination][0].get(origin)
            status = ("outbound_unreachable" if outward is None else
                      "return_unreachable" if returning is None else "directed_cycle_available")
            pairs.append({"origin": origin, "destination": destination, "status": status,
                          "loaded_ticks": outward, "return_ticks": returning,
                          "cross_system": nodes[origin].logistics_zone != nodes[destination].logistics_zone,
                          "loaded_path": list(paths[origin][1].get(destination, ())),
                          "return_path": list(paths[destination][1].get(origin, ()))})
    provenance = {"schema": "ics_v3_nanning_finite_workload_topology_v1",
        "source_path": str(profile_path.resolve()), "source_sha256": file_sha(profile_path),
        "source_node_count": len(profile["nodes"]), "source_edge_count": len(profile["edges"]),
        "active_edge_count": len(network.edges), "closed_zero_capacity_edges": previous["closed_zero_capacity_edges"],
        "physical_edges_added": 0, "physical_edge_directions_changed": 0,
        "positive_edge_capacity_preserved": True,
        "all_loader_unloader_od_count": len(pairs), "od_class_counts": dict(Counter(p["status"] for p in pairs)),
        "od_classes": pairs, "assumptions": asdict(assumptions), "no_wait_nodes": no_wait,
        "control_partitions": previous["node_partitions"],
        "source_node_roles": {key: {"alias": row["alias"], "type": row["node_type"],
                                   "system": row["system_key"]} for key, row in raw_nodes.items()},
        "operational_gaps": [
            "Initial tray inventory and node/reception capacities are synthetic, not field measurements.",
            "Divert modulo selection as no-wait permission is a sensitivity proxy, not a supplier rule.",
            "Node service times are not a complete transit/loading service model; one unload tick is an explicit proxy.",
            "Recorded edge pallet capacity uses floor(length/2m); interpreting it as simultaneous calendar occupancy is unvalidated.",
            "Both tray modes share all positive directed edges; actual mode-specific module pass permissions are absent.",
            "FixedLocalModule is the existing synthetic owner; supplier API/authorization is not available.",
            "Demand forecasts, revisions, faults, initial inventory and operating-day linkage are absent from the map.",
            "Static directed cycles are necessary, not sufficient, for dynamic capacity feasibility or sustainable throughput.",
        ]}
    return network, provenance


def read_projected_tasks(raw_path, canonical_path, manifest_path, topology):
    """Audit every row; return original bags without pretending EBS is supported."""
    raw_path, canonical_path, manifest_path = map(Path, (raw_path, canonical_path, manifest_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("schema") != "czr005.g4irsf31.nanning_workload_manifest.v1":
        raise ValueError("unsupported projected workload manifest schema")
    rows = {}
    with raw_path.open(encoding="utf-8-sig") as stream:
        header = next(stream).split()
        if header[:5] != ["ID", "EntryTime(s)", "STD(s)", "star", "end"]:
            raise ValueError("unexpected projected raw header")
        for line_number, line in enumerate(stream, 2):
            fields = line.split()
            if not fields:
                continue
            if len(fields) != 7:
                raise ValueError(f"malformed raw task line {line_number}")
            identifier, arrival, deadline = int(fields[0]), float(fields[1]), float(fields[2])
            if identifier in rows or not all(map(math.isfinite, (arrival, deadline))) or deadline < arrival:
                raise ValueError("duplicate task identity or invalid task clock")
            rows[identifier] = {"task_id": identifier, "arrival_seconds": arrival,
                                "deadline_seconds": deadline, "origin": str(int(fields[3])),
                                "destination": str(int(fields[4])), "source_line": line_number,
                                "canonical_legs": []}
    leg_counts, segment_ids, raw_reference_counts = Counter(), set(), Counter()
    for line in canonical_path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        segment = json.loads(line)
        row = rows[segment["task_id"]]
        if segment["segment_id"] in segment_ids:
            raise ValueError("duplicate canonical segment identity")
        segment_ids.add(segment["segment_id"])
        if (str(segment["original_start"]) != row["origin"] or
            str(segment["original_goal"]) != row["destination"] or
            segment["original_entry_time"] != row["arrival_seconds"] or
            segment["std"] != row["deadline_seconds"]):
            raise ValueError("canonical segment disagrees with its original raw task")
        row["canonical_legs"].append(segment["leg"])
        raw_reference_counts[segment["task_id"]] += 1
        leg_counts[segment["leg"]] += 1
    od_status = {(p["origin"], p["destination"]): p["status"] for p in topology["od_classes"]}
    counts, origins, destinations = Counter(), Counter(), Counter()
    for row in rows.values():
        legs = sorted(row["canonical_legs"])
        if legs == ["direct"]:
            row["lifecycle"] = "supported_direct_bag"
        elif legs == ["storage_in", "storage_out"]:
            row["lifecycle"] = "unsupported_early_bag_storage_lifecycle"
        else:
            raise ValueError("canonical lifecycle must contain direct OR both storage legs")
        key = (row["origin"], row["destination"])
        if key not in od_status:
            raise ValueError("projected task origin/destination is outside registered loader/unloader roles")
        row["topology_class"] = od_status[key]
        counts[row["topology_class"]] += 1
        origins[row["origin"]] += 1
        destinations[row["destination"]] += 1
    actual = {"raw_task_count": len(rows), "expanded_segment_count": len(segment_ids),
              "direct_raw_task_count": leg_counts["direct"], "early_split_raw_task_count": leg_counts["storage_in"]}
    for key, value in actual.items():
        if value != manifest[key]:
            raise ValueError(f"full-denominator mismatch: {key}")
    if dict(origins) != manifest["raw_by_start"] or dict(destinations) != manifest["raw_by_goal"]:
        raise ValueError("full projected OD marginals disagree with source manifest")
    if leg_counts["storage_in"] != leg_counts["storage_out"]:
        raise ValueError("unpaired early-bag storage lifecycle")
    summary = {"schema": "ics_v3_nanning_projected_task_full_audit_v1", **actual,
        "files": {kind: {"path": str(p.resolve()), "sha256": file_sha(p), "bytes": p.stat().st_size}
                  for kind, p in (("raw", raw_path), ("canonical", canonical_path), ("manifest", manifest_path))},
        "flight_count_recorded_in_manifest": manifest["flight_count"],
        "flight_identity_not_present_in_raw_rows": True,
        "topology_class_counts_all_original_bags": dict(counts),
        "lifecycle_counts_all_original_bags": dict(Counter(r["lifecycle"] for r in rows.values())),
        "source_protocol": manifest["protocol"], "projection_rule": manifest["mapping_rule"],
        "full_input_denominator_preserved": True, "all_original_tasks_simulated": False,
        "qualification": "Existing timetable-preserving projection from a different map; not observed Nanning operating history. Early-bag storage remains unsupported, not converted to direct bags.",
        "storage_proxy": manifest["storage_pair"],
        "original_task_identity_sha256": hashlib.sha256(json.dumps(sorted(rows), separators=(",", ":")).encode()).hexdigest()}
    return tuple(rows[k] for k in sorted(rows)), summary


SCENE_NAMES = ("short_cycle", "cross_cycle", "shared_receiver", "near_full", "long_line",
               "protected", "source_min_stock", "ample", "reversal", "capacity_one",
               "all_waitable", "closed_od", "one_way_return", "budget_probe", "counterflow")


def _cycle_rows(topology, cross=None):
    return sorted((p for p in topology["od_classes"] if p["status"] == "directed_cycle_available"
                   and (cross is None or p["cross_system"] == cross)),
                  key=lambda p: (p["loaded_ticks"] + p["return_ticks"], p["origin"], p["destination"]))


def make_workload(name, network, topology, *, rounds=3):
    """Predeclared mechanisms on unchanged 151-node topology; no outcome selection."""
    if name not in SCENE_NAMES or type(rounds) is not int or rounds < 2:
        raise ValueError("unknown scene or fewer than two circulation rounds")
    cross = _cycle_rows(topology, True)
    primary = (_cycle_rows(topology, False)[0] if name == "short_cycle" else
               cross[-1] if name == "long_line" else cross[0])
    alternatives = [p for p in cross if p["origin"] != primary["origin"] and
                    ((p["destination"] == primary["destination"]) if name == "shared_receiver" else
                     (p["destination"] != primary["destination"]))]
    secondary = alternatives[0] if alternatives else primary
    flows = [primary] if name in {"short_cycle", "long_line", "capacity_one"} else [primary, secondary]
    if name == "counterflow":
        # Select opposing real-role flows whose loaded witnesses intersect the
        # primary empty-return witness; selection reads topology, not outcomes.
        opposing = [p for p in cross if network.nodes[p["origin"]].logistics_zone !=
                    network.nodes[primary["origin"]].logistics_zone and
                    set(p["loaded_path"]) & set(primary["return_path"])]
        secondary = opposing[0]
        third = next(p for p in opposing if p["origin"] != secondary["origin"] and
                     p["destination"] != secondary["destination"] and
                     set(p["loaded_path"]) & set(secondary["loaded_path"]) & set(primary["return_path"]))
        flows = [primary, secondary, third]
    nodes = dict(network.nodes)
    if name == "capacity_one":
        nodes = {key: replace(node, capacity=1) for key, node in nodes.items()}
    if name == "all_waitable":
        nodes = {key: replace(node, can_wait=True) for key, node in nodes.items()}
    if name == "ample":
        # Joint stock/capacity control, explicitly not a stock-only ablation.
        nodes = {key: replace(node, capacity=max(node.capacity, rounds + 1)) for key, node in nodes.items()}
    network = Network(nodes, network.edges)
    spec = topology["assumptions"]
    module = FixedLocalModule(unload_ticks=spec["unload_ticks"], reception_capacity=spec["reception_capacity"],
                              export_min_stock=1 if name == "source_min_stock" else spec["export_min_stock"])
    warm = Bag(f"{name}:warm", primary["origin"], primary["destination"], 0,
               primary["loaded_ticks"] + module.unload_ticks + 12, protected=True)
    trays = {"warm_tray": Tray("warm_tray", warm.origin, "loaded", warm.bag_id)}
    for origin in sorted({p["origin"] for p in flows}):
        stock = rounds if name == "ample" else 0 if name == "capacity_one" else 1
        for i in range(stock):
            trays[f"initial:{origin}:{i}"] = Tray(f"initial:{origin}:{i}", origin)
    if name in {"near_full", "source_min_stock", "reversal", "shared_receiver"}:
        trays["receiver_stock"] = Tray("receiver_stock", primary["destination"])
    initial = Snapshot(0, network, trays, {warm.bag_id: warm}, module=module)
    assert_invariants(initial)
    burn = Simulation(initial, generator_factory=GeneratorFactory(ControlSpec(routing="baseline", predictive=False,
                      planning_horizon=180, route_mode="whole_route", candidate_count=1,
                      expansion_limit=30000)), candidate_count=1, search_horizon=180,
                      reactive_empty_dispatch=False).advance(1)
    if "warm_tray" not in burn.final_snapshot.plans:
        raise ValueError("No admitted burn-in route under the declared bounded search; no hand-authored state substituted")
    assert_invariants(burn.final_snapshot)
    forecasts, truth = [], []
    cycle = max(p["loaded_ticks"] + p["return_ticks"] + module.unload_ticks for p in flows)
    spacing = max(16, math.ceil(cycle * (1.1 if name == "capacity_one" else .7)))
    alignment = None
    if name == "counterflow":
        spacing = 60
        common = set(primary["return_path"])
        for flow in flows[1:]:
            common.intersection_update(flow["loaded_path"])
        shared_edge = sorted(common)[0]
        def offset(path):
            return sum(network.edges[e].travel_time for e in path[:path.index(shared_edge)])
        ideal_empty_entry = 2 + spacing - primary["return_ticks"] + offset(primary["return_path"])
        phases = [2] + [ideal_empty_entry - offset(flow["loaded_path"]) for flow in flows[1:]]
        if min(phases) < 2:
            raise ValueError("topology-derived counterflow alignment requires a nonnegative publication lead")
        alignment = {"shared_edge": shared_edge, "preserved_capacity": network.edges[shared_edge].capacity,
                     "flow_arrival_phases": phases, "nominal_empty_entry_tick": ideal_empty_entry,
                     "method": "align two loaded static witnesses with the latest-return static empty witness; actual policies may delay, reroute, reject or exhaust budget"}
    for round_index in range(rounds):
        for flow_index, flow in enumerate(flows):
            at = (alignment["flow_arrival_phases"][flow_index] if alignment else 2) + round_index * spacing
            identifier = f"{name}:round{round_index}:flow{flow_index}"
            origin, destination = flow["origin"], flow["destination"]
            actual_origin = origin
            if name == "reversal" and round_index == 1 and flow_index == 0:
                actual_origin = secondary["origin"]
            deadline = at + flow["loaded_ticks"] + cycle + 20
            forecast = RoutingDemandForecast(identifier, origin, destination, at, deadline,
                                             published_at=max(1, at - 40))
            forecasts.append(forecast)
            if name == "reversal" and round_index == 1 and flow_index == 0:
                forecasts.append(replace(forecast, count=0, published_at=max(7, at - 8)))
            truth.append(Bag(identifier + ":0", actual_origin, destination, at, deadline,
                             protected=name == "protected"))
    if name in {"closed_od", "one_way_return"}:
        status = "outbound_unreachable" if name == "closed_od" else "return_unreachable"
        chosen = min((p for p in topology["od_classes"] if p["status"] == status),
                     key=lambda p: (p["origin"], p["destination"]))
        # Keep the valid burn-in and add a distinct real-role stock identity.
        state = burn.final_snapshot.clone()
        if sum(t.node == chosen["origin"] for t in state.trays.values()) >= nodes[chosen["origin"]].capacity:
            raise ValueError("unreachable diagnostic source lacks a legal initial parking slot")
        state.trays["unreachable_stock"] = Tray("unreachable_stock", chosen["origin"])
        assert_invariants(state)
        truth = [Bag(f"{name}:{i}", chosen["origin"], chosen["destination"], 2 + i * 80, 180 + i * 80)
                 for i in range(2)]
        forecasts = []
    else:
        chosen, state = None, burn.final_snapshot
    horizon = max(b.arrival for b in truth) + cycle * 2 + 30
    provenance = {"source": "predeclared_synthetic_continuing_flows_on_original_nanning_topology",
        "is_observed_operating_history": False, "held_out_performance_claim": False,
        "topology_source_sha256": topology["source_sha256"], "scenario": name,
        "flow_selection": "shortest same-system/cross-system directed cycle; longest cross-system for long_line; second distinct origin and receiver by same static ordering, except shared_receiver deliberately shares its receiver",
        "flows": flows, "rounds": rounds, "spacing_ticks": spacing,
        "counterflow_alignment": alignment,
        "finite_initial_trays": len(state.trays), "initial_inventory": [asdict(t) for t in state.trays.values()],
        "burn_in": {"ticks": 1, "trace": list(burn.trace), "invariant_checks": burn.invariant_checks,
                    "accepted_plan": asdict(burn.final_snapshot.plans["warm_tray"])},
        "explicit_unreachable_case": chosen,
        "no_wait_nodes": sorted(key for key, node in nodes.items() if not node.can_wait),
        "overrides": {"node_capacities": {key: node.capacity for key, node in nodes.items()},
                      "module": asdict(module)},
        "ample_qualification": "Stock and all node capacities increased together to keep initial and final parking legal; not a stock-only ablation." if name == "ample" else None,
        "reversal_qualification": "A published source forecast is cancelled eight ticks before nominal arrival; actual source changes. Previously accepted transfers remain irrevocable." if name == "reversal" else None,
        "future_tape_access": "engine and evaluation ledger only"}
    return NetworkWorkload(name, state, tuple(forecasts), tuple(truth), horizon, provenance)


def projected_window(rows, network, topology, *, start_seconds=36000, duration_seconds=60):
    if duration_seconds <= 0:
        raise ValueError("window duration must be positive")
    window = [row for row in rows if start_seconds <= row["arrival_seconds"] < start_seconds + duration_seconds]
    supported = [row for row in window if row["lifecycle"] == "supported_direct_bag"]
    tick_seconds = topology["assumptions"]["tick_seconds"]
    # The entire selected direct window is included, even unreachable ODs.
    truth = tuple(Bag(f"projected:{r['task_id']}", r["origin"], r["destination"],
                      2 + math.ceil((r["arrival_seconds"] - start_seconds) / tick_seconds),
                      2 + math.ceil((r["deadline_seconds"] - start_seconds) / tick_seconds)) for r in supported)
    if not truth:
        raise ValueError("specified window contains no supported direct bags")
    scene = make_workload("cross_cycle", network, topology)
    state = scene.initial.clone()
    for origin in sorted({row["origin"] for row in supported}):
        count = sum(t.node == origin for t in state.trays.values())
        for i in range(count, network.nodes[origin].capacity):
            state.trays[f"projected_stock:{origin}:{i}"] = Tray(f"projected_stock:{origin}:{i}", origin)
    assert_invariants(state)
    provenance = {"source": "existing_nanning_timetable_projection_direct_window",
        "is_observed_operating_history": False, "all_original_input_bag_denominator": len(rows),
        "window_seconds": [start_seconds, start_seconds + duration_seconds],
        "all_bags_in_window": len(window), "included_direct_bags": len(truth),
        "unsupported_early_bags_in_window": len(window) - len(truth),
        "outside_window_bags": len(rows) - len(window),
        "window_task_ids": [r["task_id"] for r in window],
        "included_task_ids": [r["task_id"] for r in supported],
        "topology_class_counts_included": dict(Counter(r["topology_class"] for r in supported)),
        "arrival_transform": "retain order with ceil((source seconds - fixed window start)/10s)+2 ticks; no load thinning",
        "forecasts": "none; absent in original projected dataset",
        "burn_in": scene.provenance["burn_in"],
        "initial_inventory_source": "synthetic legal source-node stock; not reconstructed airport inventory",
        "unsupported_lifecycle": "early storage_in/storage_out excluded explicitly because node53 is an empty-tray store, not a field EBS"}
    return NetworkWorkload("projected_direct_36000_36060", state, (), truth, 220, provenance)
