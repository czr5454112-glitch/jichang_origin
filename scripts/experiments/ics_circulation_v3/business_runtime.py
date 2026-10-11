"""Explicit adapter from complete business input to the common proxy runtime.

Construction does not run physics, select a time window, filter unreachable
bags or publish future task identities. This schema authorizes only declared
research proxy semantics; it cannot certify a supplier operating interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from .business_inputs import (BusinessInputError, BusinessWorkload, ceil_tick, floor_tick,
                              seconds, business_workload_sha256, _integer, _keys, _require,
                              _text, _subtract_seconds)
from .model import Bag, Edge, FixedLocalModule, Network, Node, Tray
from .routing import RegionalCandidateGenerator
from .storage_contracts import StorageBag, StorageSnapshot, StorageWaypointContract


@dataclass(frozen=True)
class RuntimeProxyContract:
    contract_id: str
    evidence_status: str
    input_contract_sha256: str
    graph_sha256: str
    partition_by_node: tuple[tuple[str, str], ...]
    unload_seconds: Decimal
    hold_seconds_by_node: tuple[tuple[str, Decimal], ...]
    reception_capacity: int
    export_min_stock: int
    route_mode: str
    search_horizon: int
    candidate_count: int
    expansion_limit: int
    static_path_limit: int
    local_label_limit: int
    dynamic_local: bool
    reactive_empty_dispatch: bool
    coordination_order: str
    evidence: tuple[tuple[str, str, str], ...]
    canonical_sha256: str


@dataclass(frozen=True)
class BusinessGeneratorFactory:
    contract: RuntimeProxyContract

    def __call__(self, horizon=None):
        c = self.contract
        if horizon is not None:
            _integer(horizon, "generator horizon", 1)
        return RegionalCandidateGenerator(horizon=c.search_horizon if horizon is None else horizon,
            expansion_limit=c.expansion_limit, static_path_limit=c.static_path_limit,
            deadline_ms=None, dynamic_local=c.dynamic_local, local_label_limit=c.local_label_limit,
            cache_contract="isolated_replay_v1")


@dataclass(frozen=True)
class BusinessRuntimeWorkload:
    initial: StorageSnapshot
    future_bags: tuple[Bag, ...]  # Private environment only, never a policy argument.
    generator_factory: BusinessGeneratorFactory
    contract: RuntimeProxyContract
    source_business_count: int
    source_segment_count: int
    input_binding_sha256: tuple[tuple[str, str], ...]
    edge_travel_seconds: tuple[tuple[str, str], ...]
    closed_edge_ids: tuple[str, ...]
    qualification: str = "Explicit research proxy; all source bags retained; no field-operational claim"

    def simulation_kwargs(self) -> dict[str, Any]:
        """Only constructor settings; callbacks and execution caps stay external."""
        c = self.contract
        return dict(generator_factory=self.generator_factory, route_mode=c.route_mode,
            search_horizon=c.search_horizon, candidate_count=c.candidate_count,
            reactive_empty_dispatch=c.reactive_empty_dispatch, coordination_order=c.coordination_order)


def parse_runtime_proxy_contract(value: Mapping[str, Any], workload: BusinessWorkload) -> RuntimeProxyContract:
    obj = _keys(value, {"schema", "contract_id", "evidence_status", "input_contract_sha256",
        "graph_sha256", "node_resource_policy", "empty_wait_policy", "edge_permission_policy",
        "edge_capacity_policy", "travel_policy", "partition_by_node", "module", "routing",
        "reactive_empty_dispatch", "coordination_order", "evidence"}, "runtime proxy contract")
    _require(obj["schema"] == "ics_business_runtime_proxy_v1", "unsupported runtime proxy schema")
    _require(obj["evidence_status"] == workload.contract.evidence_status == "proxy_research",
             "runtime adapter supports explicit proxy_research only")
    _require(obj["input_contract_sha256"] == workload.contract.canonical_sha256, "input contract binding mismatch")
    _require(obj["graph_sha256"] == workload.contract.graph_sha256, "runtime graph binding mismatch")
    for field, required in {
        "node_resource_policy": "exact_bound_input_node_capacity_and_loaded_wait",
        "empty_wait_policy": "same_as_declared_loaded_wait_proxy",
        "edge_permission_policy": "both_modes_all_source_directed_edges_proxy",
        "edge_capacity_policy": "preserve_source_integer_including_closed_zero",
        "travel_policy": "exact_length_over_speed_ceil_to_input_tick"}.items():
        _require(obj[field] == required, f"unsupported or missing {field}")
    nodes = {n.node_id for n in workload.contract.nodes}
    partitions = obj["partition_by_node"]
    _require(isinstance(partitions, dict) and set(partitions) == nodes, "exact node partition map required")
    partitions = tuple(sorted((n, _text(p, "control partition")) for n, p in partitions.items()))
    module = _keys(obj["module"], {"kind", "loading_seconds", "unload_seconds", "hold_seconds_by_node",
                                  "reception_capacity", "export_min_stock"}, "module")
    _require(module["kind"] == "existing_fixed_fifo_proxy", "supplier/unknown local module unsupported")
    _require(seconds(module["loading_seconds"]) == 0, "nonzero loading service unsupported by fixed FIFO proxy")
    unload = seconds(module["unload_seconds"], "unload_seconds")
    _require(unload >= 0, "unload_seconds must be nonnegative")
    holds = module["hold_seconds_by_node"]
    _require(isinstance(holds, dict) and set(holds) == nodes, "exact node hold service map required")
    holds = tuple(sorted((node, seconds(t, "hold seconds")) for node, t in holds.items()))
    _require(all(t >= 0 for _, t in holds), "hold seconds must be nonnegative")
    reception = _integer(module["reception_capacity"], "reception_capacity")
    export = _integer(module["export_min_stock"], "export_min_stock")
    route = _keys(obj["routing"], {"route_mode", "search_horizon", "candidate_count", "expansion_limit",
        "static_path_limit", "local_label_limit", "dynamic_local", "deadline_ms", "cache_contract"}, "routing")
    _require(route["route_mode"] in ("whole_route", "next_edge"), "unsupported route mode")
    budget = {n: _integer(route[n], n, 1) for n in ("search_horizon", "candidate_count", "expansion_limit",
                                                    "static_path_limit", "local_label_limit")}
    _require(type(route["dynamic_local"]) is bool, "dynamic_local must be explicit boolean")
    _require(route["deadline_ms"] is None and route["cache_contract"] == "isolated_replay_v1",
             "only deterministic isolated cache with explicit no wall deadline supported")
    _require(type(obj["reactive_empty_dispatch"]) is bool, "reactive_empty_dispatch must be explicit boolean")
    _require(obj["coordination_order"] in ("route_then_prebalance", "prebalance_then_route"), "unsupported coordination order")
    _require(isinstance(obj["evidence"], list), "runtime evidence list required")
    evidence = []
    for item in obj["evidence"]:
        item = _keys(item, {"field", "source_ref", "assumption_id"}, "runtime evidence")
        evidence.append(tuple(_text(item[n], "runtime evidence " + n) for n in ("field", "source_ref", "assumption_id")))
    required = {"permissions", "module", "partition", "travel_capacity", "routing", "coordination"}
    _require(len(evidence) == len(required) and {e[0] for e in evidence} == required, "exact runtime evidence coverage required")
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return RuntimeProxyContract(_text(obj["contract_id"], "contract_id"), "proxy_research",
        obj["input_contract_sha256"], obj["graph_sha256"], partitions, unload, holds, reception, export,
        route["route_mode"], budget["search_horizon"], budget["candidate_count"], budget["expansion_limit"],
        budget["static_path_limit"], budget["local_label_limit"], route["dynamic_local"],
        obj["reactive_empty_dispatch"], obj["coordination_order"], tuple(evidence), sha256(canonical.encode()).hexdigest())


def build_business_runtime(workload: BusinessWorkload, profile_path: str | Path,
                           runtime_contract: Mapping[str, Any]) -> BusinessRuntimeWorkload:
    """Construct a time-zero physical ledger plus the full private arrival tape."""
    _require(isinstance(workload, BusinessWorkload), "audited BusinessWorkload required")
    _require(workload.content_sha256 == business_workload_sha256(workload),
             "audited workload content binding mismatch")
    contract = parse_runtime_proxy_contract(runtime_contract, workload)
    path = Path(profile_path)
    raw = path.read_bytes()
    _require(sha256(raw).hexdigest() == contract.graph_sha256, "profile bytes differ from bound graph")
    profile = json.loads(raw, parse_float=Decimal)
    source_nodes = {str(n["location"]): n for n in profile["nodes"]}
    _require(len(source_nodes) == len(profile["nodes"]), "duplicate profile nodes")
    inputs = {n.node_id: n for n in workload.contract.nodes}
    _require(set(inputs) == set(source_nodes), "input/profile node identity mismatch")
    partitions = dict(contract.partition_by_node)
    nodes = {key: Node(key, _text(row["system_key"], "source system_key"), partitions[key],
                       inputs[key].capacity, inputs[key].loaded_wait_allowed)
             for key, row in source_nodes.items()}
    edges, edge_seconds, closed = {}, [], []
    tick = Fraction(workload.contract.tick_seconds)
    for row in profile["edges"]:
        origin, target = str(row["start"]), str(row["end"])
        _require(origin in nodes and target in nodes, "edge endpoint absent from original graph")
        key = f"{origin}->{target}"
        _require(key not in edges, "parallel source edge cannot be represented without a distinct edge identity")
        length, speed = seconds(row["length"], "edge length"), seconds(row["speed"], "edge speed")
        _require(length > 0 and speed > 0, "source length/speed must be positive")
        duration = Fraction(length) / Fraction(speed)
        ticks = duration / tick
        travel = -(-ticks.numerator // ticks.denominator)
        capacity = _integer(row["capacity"], "source edge capacity")
        edges[key] = Edge(key, origin, target, travel, capacity)
        edge_seconds.append((key, str(duration)))
        if capacity == 0:
            closed.append(key)
    _require(len(edges) == len(profile["edges"]), "all source edges must be retained")
    loaders = {str(n) for n in profile["business_roles"]["source_candidate_ids"]}
    unloaders = {str(n) for n in profile["business_roles"]["sink_candidate_ids"]}
    trays = {}
    for t in workload.contract.initial_trays:
        _require(t.node_id in loaders, "this initial-inventory adapter requires declared original loader nodes")
        _require(t.tray_id not in trays, "duplicate finite initial tray")
        trays[t.tray_id] = Tray(t.tray_id, t.node_id, "empty", None, t.available_at)
    module = FixedLocalModule(unload_ticks=ceil_tick(contract.unload_seconds, workload.contract.tick_seconds),
        hold_by_node={n: ceil_tick(value, workload.contract.tick_seconds) for n, value in contract.hold_seconds_by_node},
        export_min_stock=contract.export_min_stock, reception_capacity=contract.reception_capacity)
    initial = StorageSnapshot(now=0, network=Network(nodes, edges), trays=trays, bags={}, module=module)
    bags = []
    seen = set()
    protected_ids = frozenset(workload.contract.protected_business_ids)
    for task in workload.tasks:
        _require(task.business_bag_id not in seen, "duplicate business identity at runtime boundary")
        seen.add(task.business_bag_id)
        _require(task.origin in loaders and task.final_destination in unloaders, "runtime business role mismatch")
        expected_deadline = _subtract_seconds(task.std_seconds, workload.contract.deadline_lead_seconds)
        _require(task.deadline_seconds == expected_deadline, "business final deadline policy mismatch")
        expected_protected = workload.contract.protection_policy == "all" or task.business_bag_id in protected_ids
        _require(type(task.protected) is bool and task.protected == expected_protected,
                 "business protection policy mismatch")
        expected_early = _subtract_seconds(task.std_seconds, task.arrival_seconds) >= Decimal(4800)
        _require(task.lifecycle == ("early_storage" if expected_early else "direct"), "business early lifecycle policy mismatch")
        _require(task.arrival == ceil_tick(task.arrival_seconds, workload.contract.tick_seconds) and
                 task.deadline == floor_tick(task.deadline_seconds, workload.contract.tick_seconds), "business clock binding mismatch")
        fields = dict(bag_id=task.business_bag_id, origin=task.origin, destination=task.final_destination,
                      arrival=task.arrival, deadline=task.deadline, protected=task.protected)
        if task.lifecycle == "early_storage":
            _require(task.scheduled_release_seconds == _subtract_seconds(task.std_seconds, Decimal(2700)),
                     "business scheduled release policy mismatch")
            _require(task.storage_node == workload.contract.storage.node_id and
                     task.storage_node != task.final_destination, "invalid fixed storage waypoint")
            _require(task.published_at == task.arrival and task.release_at ==
                     ceil_tick(task.scheduled_release_seconds, workload.contract.tick_seconds), "unannounced or inconsistent release")
            _require(task.release_at >= task.published_at >= 0, "invalid fixed release/publication order")
            bags.append(StorageBag(**fields, storage=StorageWaypointContract(task.storage_node,
                task.release_at, task.published_at, evidence_status="proxy", carrier_policy="on_carrier")))
        elif task.lifecycle == "direct":
            _require(task.storage_node is None and task.release_at is None and task.published_at is None,
                     "direct bag cannot silently discard a storage contract")
            bags.append(Bag(**fields))
        else:
            raise BusinessInputError("unsupported business lifecycle")
    _require(len(bags) == workload.raw_business_count == workload.original_count + workload.derived_count,
             "runtime adapter must preserve complete business denominator")
    _require(sum(len(t.old_segment_ids) for t in workload.tasks) == workload.old_segment_count,
             "runtime adapter segment provenance denominator mismatch")
    _require(sha256(path.read_bytes()).hexdigest() == contract.graph_sha256, "profile changed during adaptation")
    return BusinessRuntimeWorkload(initial, tuple(bags), BusinessGeneratorFactory(contract), contract,
        workload.raw_business_count, workload.old_segment_count, workload.input_sha256,
        tuple(edge_seconds), tuple(closed))
