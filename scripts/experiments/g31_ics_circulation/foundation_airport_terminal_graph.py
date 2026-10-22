"""Public, directed station graph for advisory empty-tray allocation.

The witness path is a travel estimate, never a route command or an independent
capacity grant. Cache identity includes topology, service and notified closures.
"""
from __future__ import annotations

import math

from .foundation_airport_batch_patch import digest
from .foundation_airport_joint_opportunities import assert_prepared_current, build_joint_catalog

SCHEMA = "g31.foundation.airport_terminal_graph.v1"


def build_terminal_graph(prepared_current, terminal_contract=None, *, catalog=None):
    """Build physical reachability and conservative current receiving slots.

    Unknown receiving occupancy remains missing. Its optional capacity is zero;
    the controller can preserve ordinary return through its explicit native-
    admission fallback. Pending requests reserve space but are not inventory.
    """
    prepared = prepared_current
    assert_prepared_current(prepared)
    catalog = build_joint_catalog(prepared) if catalog is None else catalog
    if catalog["public_state_digest"] != prepared.public_state_digest:
        raise ValueError("terminal_graph:catalog_state")
    terminal_contract = {} if terminal_contract is None else dict(terminal_contract)
    if set(terminal_contract) - {"terminal_nodes", "contract_version"}:
        raise ValueError("terminal_graph:unknown_terminal_contract")
    observation = prepared.observation
    loaders = set(observation["static_role_contract"]["loader_nodes"])
    sources = {row["source"] for row in catalog["candidates"] if row["action_type"] == "transfer"}
    terminals = set(terminal_contract.get("terminal_nodes", loaders | sources))
    if not terminals <= set(prepared.contracts):
        raise ValueError("terminal_graph:unknown_terminal")
    terminals |= sources | loaders
    topology_version = digest({"nodes": observation["node_records"],
        "edges": observation["edge_records"], "edge_contracts": observation.get("edge_contracts", [])})
    active_faults = [row for row in observation.get("known_faults", [])
        if row.get("active", row.get("start", observation["now"]) <= observation["now"]
                   < row.get("end", math.inf))]
    closure_version = digest(active_faults)
    receiver_contract, station_table, missing = {}, [], []
    for node in sorted(terminals):
        contract, stock = prepared.contracts[node], prepared.inventory["nodes"][node]
        capacity, occupancy = contract.get("capacity"), stock.get("occupancy")
        known = (stock["known"] and type(capacity) is int and capacity >= 0
                 and type(occupancy) is int and occupancy >= 0)
        obligations = prepared.inventory["known_own_assignment_coverage"].get(node, [])
        # The coverage helper already removes received obligations represented
        # by the current destination capture; never subtract those twice.
        reserved = len({row["tray_id"] for row in obligations})
        slots = max(0, capacity - occupancy - reserved) if known else 0
        if not contract.get("allow_receive", True):
            slots = 0
        receiver_contract[node] = {"node": node, "known": known, "capacity": capacity,
            "current_occupancy": occupancy if known else None,
            "current_space": max(0, capacity-occupancy) if known else None,
            "unrepresented_committed_or_pending": reserved, "available_slots": slots,
            "observation_asof": stock.get("as_of"), "coverage": stock["source"],
            "all_owner_incoming_complete": False, "native_revalidation_required": True}
        station_table.append({"node": node, "is_loader": node in loaders,
            "is_actual_eligible_source": node in sources,
            "resource_owner": contract.get("resource_owner", contract.get("zone")),
            "inventory_known": stock["known"], "actual_empty": stock["reported_actual_empty"],
            "receiver": receiver_contract[node]})
        if not known:
            missing.append({"node": node, "reason": "receiver_occupancy_or_inventory_unknown"})
    arcs, unreachable = [], []
    for source in sorted(terminals):
        for destination in sorted(terminals - {source}):
            duration, path = prepared.travel.path(source, destination)
            complete = prepared.travel.complete(source, destination)
            if not math.isfinite(complete):
                unreachable.append([source, destination])
                continue
            transport = math.fsum(prepared.travel.edge_time[a, b] for a, b in zip(path, path[1:]))
            service = math.fsum(prepared.travel.service[node] for node in path)
            arcs.append({"source_terminal": source, "destination_terminal": destination,
                "reachable": True, "static_transport_seconds": transport,
                "static_service_seconds": service, "static_complete_seconds": complete,
                "public_path_cost_excluding_destination_service": duration,
                "physical_path_reference": list(path), "physical_edges": [list(e) for e in zip(path, path[1:])],
                "topology_version": topology_version, "notified_closure_version": closure_version,
                "estimate_asof": observation["now"], "observation_scope": observation["owner_id"],
                "receiver_type": "loader" if destination in loaders else "other_legal_terminal",
                "receiver_space_coverage": receiver_contract[destination]["coverage"],
                "independent_physical_capacity_claimed": False})
    return {"schema": SCHEMA, "public_state_digest": prepared.public_state_digest,
        "catalog_id": catalog["catalog_id"], "now": observation["now"],
        "owner_id": observation["owner_id"], "station_table": station_table, "arcs": arcs,
        "receiver_contract": receiver_contract, "unreachable_pairs": unreachable,
        "missing_coverage": missing, "topology_version": topology_version,
        "notified_closure_version": closure_version,
        "cache_scope": "immutable_prepared_observation", "native_execution_authority": False}
