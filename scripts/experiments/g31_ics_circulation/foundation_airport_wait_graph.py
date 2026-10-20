"""Offline current wait/hold graph from exact native diagnostic evidence.

An SCC is a witnessed hold/wait cycle, not a proof of system deadlock: resource
wait sets may contain alternatives and edge waits may include timed headway.
Nothing from this diagnostic is an online actor feature.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from .foundation_airport_batch_patch import digest, require


SCHEMA = "g31.foundation.airport_wait_graph.v1"


def _components(adjacency):
    """Tarjan SCCs; retain edge witnesses in the caller."""
    index, stack, active, indices, low, result = 0, [], set(), {}, {}, []

    def visit(node):
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for other in adjacency.get(node, ()):
            if other not in indices:
                visit(other)
                low[node] = min(low[node], low[other])
            elif other in active:
                low[node] = min(low[node], indices[other])
        if low[node] == indices[node]:
            component = []
            while True:
                other = stack.pop()
                active.remove(other)
                component.append(other)
                if other == node:
                    break
            result.append(sorted(component))

    nodes = set(adjacency)
    nodes.update(other for row in adjacency.values() for other in row)
    for node in sorted(nodes):
        if node not in indices:
            visit(node)
    return result


def _request_summary(result, calls):
    groups = {}
    for call in calls:
        if call.get("kind") != "transfer":
            continue
        request = call["request"]
        identity = request["request_id"]
        row = groups.setdefault(identity, {"request_id": identity,
            "tray_id": request["tray_id"], "owner": request["owner_id"],
            "source": request["source"], "receiver": request["destination"],
            "transfer_scope": request.get("transfer_scope", "cross_zone_transfer"),
            "first_submissions": 0, "retries": 0, "leg_ids": []})
        row["retries" if call.get("retry") else "first_submissions"] += 1
    for transfer in result.get("transfers", []):
        row = groups.setdefault(transfer["request_id"], {"request_id": transfer["request_id"],
            "first_submissions": 0, "retries": 0, "leg_ids": [], "submit_payload_unavailable": True})
        row.update(final_status=transfer["status"], final_reason=transfer.get("reason"))
    for leg in result.get("leg_identities", []):
        if leg["kind"] == "empty_return":
            suffix = ":empty_return:" + str(leg["runtime_id"])
            identity = leg["transport_leg_id"][:-len(suffix)]
            if leg["transport_leg_id"].endswith(suffix) and identity in groups:
                groups[identity]["leg_ids"].append(leg["transport_leg_id"])
    events = [row for row in result.get("receipts", []) if row["event"] == "TRANSFER_REJECTED"]
    return {"unique_request_count": len(groups),
        "actual_nonretry_submissions": sum(row["first_submissions"] for row in groups.values()),
        "actual_retry_submissions": sum(row["retries"] for row in groups.values()),
        "native_rejection_event_count": len(events),
        "native_rejection_events_by_reason": dict(Counter(row["reason"] for row in events)),
        "request_terminal_rejections_by_reason": dict(Counter(row.get("final_reason") for row in groups.values()
            if row.get("final_status") == "rejected")),
        "request_rows": list(groups.values()),
        "native_retry_events_are_independent_samples": False}


def analyze_wait_graph(data, result, diagnostics, *, client_calls=()):
    require(diagnostics.get("schema") == "g31.circulation.offline_diagnostics.v1",
        "exact_native_offline_diagnostics_required")
    require(diagnostics["now"] == result["physical_clock"]
        and result.get("advance", {}).get("horizon_complete") is True,
        "same_complete_native_timestamp")
    now = diagnostics["now"]
    trays = diagnostics["trays"]
    result_trays = {row["tray_id"]: row for row in result["trays"]}
    require(len(result_trays) == len(trays) and set(result_trays) == {row["tray_id"] for row in trays},
        "full_physical_tray_population")
    contracts = {row["node"]: row for row in data["node_contracts"]}
    edge_contracts = data["edge_contracts"]
    legs = {row["runtime_id"]: row for row in diagnostics["legs"]}
    holder_nodes, holder_edges = defaultdict(dict), defaultdict(list)
    edges, unknown, static_blocked = [], [], []
    for i, tray in enumerate(trays):
        node_claims = defaultdict(list)
        if tray["edge_to"] < 0:
            node_claims[tray["node"]].append("physical_node_occupancy")
        else:
            node_claims[tray["edge_to"]].append("inflight_receiving_berth")
            holder_edges[(tray["edge_from"], tray["edge_to"])].append(i)
        if tray["reception_node"] >= 0:
            node_claims[tray["reception_node"]].append("irrevocable_reception_lease")
        for node, reasons in node_claims.items():
            holder_nodes[node][i] = reasons
    for wait_index, wait in enumerate(diagnostics["resource_waits"]):
        require(wait["runtime_id"] in legs, "wait_requires_actual_leg")
        leg = legs[wait["runtime_id"]]
        tray_index = leg["tray_index"]
        tray = trays[tray_index]
        require(tray["active_leg"] == wait["runtime_id"] and tray["node"] == wait["node"]
            and tray["edge_to"] < 0, "wait_matches_current_physical_tray")
        waiter = "tray:" + tray["tray_id"]
        evidence = {"source": "offline_diagnostics.resource_waits", "index": wait_index,
            "at": now, "runtime_id": wait["runtime_id"], "generation": wait["generation"]}
        if wait["static_blocked"]:
            static_blocked.append({"tray_id": tray["tray_id"], "node": tray["node"], "evidence": evidence})
        for node in wait["receiving_nodes"]:
            holders = {i: reasons for i, reasons in holder_nodes[node].items() if i != tray_index}
            if len(holders) < contracts[node]["capacity"]:
                unknown.append({"tray_id": tray["tray_id"], "resource": "node:" + str(node),
                    "reason": "wait_index_but_current_capacity_not_saturated", "evidence": evidence})
                continue
            resource = "node:" + str(node)
            edges.append({"from": waiter, "to": resource, "kind": "actual_receiving_wait", "evidence": evidence})
            for i, reasons in holders.items():
                edges.append({"from": resource, "to": "tray:" + trays[i]["tray_id"],
                    "kind": "actual_hold", "hold_reasons": reasons,
                    "evidence": {"source": "offline_diagnostics.trays", "index": i, "at": now}})
        for edge_index in wait["edge_indices"]:
            edge = edge_contracts[edge_index]
            pair = edge["from"], edge["to"]
            holders = holder_edges[pair]
            resource = f"edge:{pair[0]}->{pair[1]}"
            if edge["capacity"] <= 0 or len(holders) < edge["capacity"]:
                unknown.append({"tray_id": tray["tray_id"], "resource": resource,
                    "reason": "timed_headway_or_other_edge_wait_not_proven_held_capacity", "evidence": evidence})
                continue
            edges.append({"from": waiter, "to": resource, "kind": "actual_edge_capacity_wait", "evidence": evidence})
            for i in holders:
                edges.append({"from": resource, "to": "tray:" + trays[i]["tray_id"],
                    "kind": "actual_hold", "hold_reasons": ["physical_inflight_edge"],
                    "evidence": {"source": "offline_diagnostics.trays", "index": i, "at": now}})
    # Shared resources may be encountered by multiple waiters. Retain unique
    # edges with their exact evidence rather than multiplying apparent holds.
    edges = list({digest(row): row for row in edges}.values())
    adjacency = defaultdict(set)
    for row in edges:
        adjacency[row["from"]].add(row["to"])
    components = [row for row in _components(adjacency) if len(row) > 1]
    cyclic = {node for row in components for node in row}
    cycles = [{"vertices": row, "edges": [edge for edge in edges
        if edge["from"] in row and edge["to"] in row]} for row in components]
    chains = [row for row in edges if row["kind"] != "actual_hold" and row["from"] not in cyclic]
    empty_unattempted = []
    actual_attempts = [row for row in client_calls if row.get("kind") == "transfer" and not row.get("retry")]
    waiting_at_source = Counter()
    specs = {row["business_bag_id"]: row for row in data["jobs"]}
    for job in result["jobs"]:
        if job["status"] == "waiting_for_tray":
            waiting_at_source[specs[job["business_bag_id"]]["origin"]] += 1
    for tray in trays:
        public = result_trays[tray["tray_id"]]
        if (tray["mode"] == "empty" and tray["active_leg"] < 0 and tray["edge_to"] < 0
                and tray["reception_node"] < 0 and public["available_at"] <= now
                and not waiting_at_source[tray["node"]]
                and not any(call["request"]["tray_id"] == tray["tray_id"]
                    and call["at"] >= public["available_at"] for call in actual_attempts)):
            empty_unattempted.append({"tray_id": tray["tray_id"], "node": tray["node"],
                "available_since": public["available_at"],
                "unattempted_seconds": now-public["available_at"],
                "meaning": "observed empty with no nonretry attempt since availability; dispatch eligibility unknown"})
    roles_present = data.get("static_role_contract", {}).get("schema") == "g31.static_node_roles.v1"
    return {"schema": SCHEMA, "at": now, "scope": "offline_evaluator_only_never_actor_features",
        "physical_trays": len(trays), "actual_resource_waits": len(diagnostics["resource_waits"]),
        "edges": edges, "witnessed_hold_wait_cycles": cycles, "noncycle_wait_edges": chains,
        "unknown_or_timed_waits": unknown, "actual_static_blocked": static_blocked,
        "available_without_observed_attempt": empty_unattempted,
        "ordinary_local_return_contract": "declared" if roles_present else "missing_static_role_contract",
        "request_denominators": _request_summary(result, client_calls),
        "departure_lease_expiry_events": [row for row in result.get("receipts", [])
            if "departure_lease_expired" in row.get("reason", "")],
        "cycle_is_global_deadlock_proof": False,
        "limitations": ["alternative wait resources can break a cycle",
            "headway deadlines are not exported and are never invented",
            "no absent action or static path is treated as current dispatch permission",
            "source FIFO/min-stock legality and shared-resource per-job protection remain separate"]}
