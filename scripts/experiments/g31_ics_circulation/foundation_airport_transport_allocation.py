"""Layered integer min-cost transport with real tray nodes and optional HOLD.

The optimum is for a conservative separable station proxy. Ordinary returns
retain their protected category; physical FIFO, conflicts and arrival admission
remain native decisions. Later dispatch slots are optimistic recommendations.
"""
from __future__ import annotations

from collections import Counter
import copy
import math

from .foundation_airport_batch_patch import ACTIVE, digest
from .foundation_airport_inventory_projection import _node_projection
from .foundation_airport_joint_opportunities import assert_prepared_current

SCHEMA = "g31.foundation.airport_transport_allocation.v1"
DEFAULT_CONFIG = {
    "marginal_reference_available_offset_seconds": 2.,
    "delay_cost_model": "linear_excess_over_reference",
    "delay_penalty_weight": .01,
    "transport_penalty_weight": .01,
    "dispatch_slot_seconds": 60.,
    "command_delay_seconds": 2.,
    "first_action_verification_mode": "exact_eta_positive_net_gain",
    "minimum_net_gain": 0.,
    "marginal_approximation": "conservative_monotone_v1",
}


def allocation_config(config=None):
    config = {} if config is None else dict(config)
    if set(config) - set(DEFAULT_CONFIG):
        raise ValueError("transport_allocation:unknown_config")
    result = {**DEFAULT_CONFIG, **config}
    for key in ("marginal_reference_available_offset_seconds", "delay_penalty_weight",
                "transport_penalty_weight", "dispatch_slot_seconds", "command_delay_seconds", "minimum_net_gain"):
        value = result[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError("transport_allocation:invalid_" + key)
    if result["dispatch_slot_seconds"] <= 0:
        raise ValueError("transport_allocation:positive_dispatch_slot")
    if result["delay_cost_model"] not in ("none", "linear_excess_over_reference"):
        raise ValueError("transport_allocation:delay_cost_model")
    if result["first_action_verification_mode"] != "exact_eta_positive_net_gain":
        raise ValueError("transport_allocation:first_action_verification_mode")
    if result["marginal_approximation"] != "conservative_monotone_v1":
        raise ValueError("transport_allocation:marginal_approximation")
    return result


def build_supply_offers(prepared_current, catalog, known_commitments=None):
    """Retain each menu tray's exact destination eligibility and source ceiling."""
    prepared = prepared_current
    assert_prepared_current(prepared)
    if catalog["public_state_digest"] != prepared.public_state_digest:
        raise ValueError("transport_allocation:catalog_state")
    observation = prepared.observation
    commitments = (list(observation.get("client_transfer_ledger", [])) + list(observation.get("transfers", []))
                   if known_commitments is None else list(known_commitments))
    pledged = {row["tray_id"] for row in commitments if row.get("status") in ACTIVE}
    supplies = {row["tray_id"]: row for row in prepared.supplies}
    by_tray, sources = {}, {}
    for action in catalog["candidates"]:
        if action["action_type"] != "transfer" or action["tray_id"] in pledged:
            continue
        tray, source = action["tray_id"], action["source"]
        if tray not in supplies or supplies[tray]["node"] != source or action["owner_id"] != observation["owner_id"]:
            raise ValueError("transport_allocation:not_actual_owned_supply")
        category = action["source_category"]
        offer = by_tray.setdefault(tray, {"tray_id": tray, "source": source,
            "owner_id": action["owner_id"], "source_category": category,
            "available_at": observation["now"], "legal_actions": []})
        if offer["source"] != source or offer["source_category"] != category:
            raise ValueError("transport_allocation:inconsistent_tray")
        offer["legal_actions"].append(copy.deepcopy(action))
        minimum = int(prepared.contracts[source].get("export_min_stock", 0))
        reserve = max(1, minimum) if category == "loader_optional" else minimum
        count_limit = max(0, action["source_actual_unpledged"] - action["source_fifo_reserved"] - reserve)
        row = sources.setdefault(source, {"source": source, "owner_id": action["owner_id"],
            "source_category": category, "hard_minimum_reserve": reserve,
            "fifo_reserved": action["source_fifo_reserved"], "source_cap": count_limit,
            "tray_ids": []})
        row["source_cap"] = min(row["source_cap"], count_limit)
        if tray not in row["tray_ids"]:
            row["tray_ids"].append(tray)
    for row in sources.values():
        row["tray_ids"].sort(key=str)
        row["source_cap"] = min(row["source_cap"], len(row["tray_ids"]))
    return {"schema": SCHEMA, "public_state_digest": prepared.public_state_digest,
        "catalog_id": catalog["catalog_id"], "owner_id": observation["owner_id"],
        "now": observation["now"], "sources": sources, "trays": by_tray,
        "total_source_cap": sum(row["source_cap"] for row in sources.values()),
        "future_or_fifo_blocked_supply_included": False, "native_execution_authority": False}


def _monotone(raw, *, increasing):
    values, previous = [], 0. if increasing else math.inf
    for value in raw:
        value = max(0., value)
        previous = max(previous, value) if increasing else min(previous, value)
        values.append(previous)
    errors = [abs(a-b) for a, b in zip(raw, values)]
    return values, {"absolute_error_sum": math.fsum(errors), "maximum_absolute_error": max(errors, default=0.),
        "monotonicity_violation": math.fsum(max(0., (a-b) if increasing else (b-a)) for a, b in zip(raw, raw[1:]))}


def build_marginal_values(projection, offers, receiver_contract, config=None, *, use_forecast=None):
    """Compute conservative convex source costs and concave receiver benefits."""
    config = allocation_config(config)
    use_forecast = projection.forecast is not None if use_forecast is None else use_forecast
    if use_forecast and projection.forecast is None:
        raise ValueError("transport_allocation:forecast_required")
    if projection.public_state_digest != offers["public_state_digest"]:
        raise ValueError("transport_allocation:projection_state")
    result = {"schema": SCHEMA, "public_state_digest": offers["public_state_digest"],
        "source_marginals": {}, "receiver_marginals": {}, "source_known": {}, "receiver_known": {},
        "raw_source_marginals": {}, "raw_receiver_marginals": {}, "approximation_audit": [],
        "reference_offset_seconds": config["marginal_reference_available_offset_seconds"],
        "use_forecast": use_forecast, "units": "bag_seconds_of_backlog", "config": config,
        "proxy_is_exact_original_nonlinear_objective": False}
    for side, entries in (("source", offers["sources"]), ("receiver", receiver_contract)):
        for node, entry in entries.items():
            cap = entry["source_cap"] if side == "source" else min(entry["available_slots"], offers["total_source_cap"])
            before = _node_projection(projection, node, use_forecast=use_forecast)
            known = before is not None and (side == "source" or entry["known"])
            raw, previous = [], before
            if known:
                for quantity in range(1, cap+1):
                    kwargs = ({"stock_delta": -float(quantity)} if side == "source" else
                              {"added_event": (result["reference_offset_seconds"], float(quantity))})
                    after = _node_projection(projection, node, use_forecast=use_forecast, **kwargs)
                    delta = after["backlog_area"] - previous["backlog_area"]
                    raw.append(delta if side == "source" else -delta)
                    previous = after
            curve, audit = _monotone(raw, increasing=side == "source")
            result[side+"_known"][node] = known
            result[side+"_marginals"][node] = curve
            result["raw_"+side+"_marginals"][node] = raw
            result["approximation_audit"].append({"side": side, "node": node, "known": known, **audit})
    return result


def transport_cost(action, config=None):
    """Declared separable cost; per-owner slot delay is diagnosed separately."""
    config = allocation_config(config)
    travel = float(action["static_travel_time"])
    if not math.isfinite(travel) or travel < 0:
        raise ValueError("transport_allocation:finite_travel")
    delay = 0.
    if config["delay_cost_model"] == "linear_excess_over_reference":
        delay = config["delay_penalty_weight"] * max(0., config["command_delay_seconds"] + travel
            - config["marginal_reference_available_offset_seconds"])
    return config["transport_penalty_weight"] * travel + delay


class _ResidualFlow:
    """Small integral residual network; Bellman-Ford handles reverse costs."""
    def __init__(self):
        self.graph = []

    def node(self):
        self.graph.append([])
        return len(self.graph)-1

    def edge(self, source, target, capacity, cost):
        if type(capacity) is not int or capacity < 0 or not math.isfinite(cost):
            raise ValueError("transport_allocation:invalid_network_edge")
        edge = [target, len(self.graph[target]), capacity, float(cost), capacity]
        self.graph[source].append(edge)
        self.graph[target].append([source, len(self.graph[source])-1, 0, -float(cost), 0])
        return edge

    def solve(self, source, sink, limit):
        sent, objective = 0, 0.
        while sent < limit:
            distance, previous = [math.inf]*len(self.graph), [None]*len(self.graph)
            distance[source] = 0.
            for _ in range(len(self.graph)-1):
                changed = False
                for u, edges in enumerate(self.graph):
                    for index, (v, _, capacity, cost, _) in enumerate(edges):
                        if capacity and distance[u]+cost < distance[v]-1e-10:
                            distance[v], previous[v], changed = distance[u]+cost, (u, index), True
                if not changed:
                    break
            if previous[sink] is None:
                break
            amount, cursor, path = limit-sent, sink, []
            while cursor != source:
                if len(path) > len(self.graph):
                    raise ValueError("transport_allocation:residual_negative_cycle")
                u, index = previous[cursor]
                edge = self.graph[u][index]
                amount = min(amount, edge[2])
                path.append((u, index))
                cursor = u
            for u, index in path:
                edge = self.graph[u][index]
                edge[2] -= amount
                self.graph[edge[0]][edge[1]][2] += amount
            sent += amount
            objective += amount*distance[sink]
        return sent, objective


def _solve_layer(graph, offers, values, config, *, protected, receiver_used):
    network = _ResidualFlow()
    start, sink = network.node(), network.node()
    receivers, selected_edges, hold_edges, limit = {}, [], {}, 0
    for node, contract in sorted(graph["receiver_contract"].items()):
        cap = max(0, contract["available_slots"]-receiver_used[node])
        if not cap or (not protected and not values["receiver_known"].get(node, False)):
            continue
        receiver = receivers[node] = network.node()
        curve = values["receiver_marginals"].get(node, [])
        for index in range(receiver_used[node], receiver_used[node]+min(cap, offers["total_source_cap"])):
            if not protected and index >= len(curve):
                break
            network.edge(receiver, sink, 1, -curve[index] if index < len(curve) else 0.)
    reachable = {(row["source_terminal"], row["destination_terminal"]) for row in graph["arcs"]}
    for source, offer in sorted(offers["sources"].items()):
        if (offer["source_category"] == "ordinary_return") != protected:
            continue
        cap = offer["source_cap"]
        if not cap:
            continue
        gate, dispatch = network.node(), network.node()
        network.edge(start, gate, cap, 0.)
        limit += cap
        # Add HOLD first so a tied zero-gain optional move remains at source.
        if not protected:
            hold_edges[source] = network.edge(gate, sink, cap, 0.)
        curve = values["source_marginals"].get(source, [])
        known = values["source_known"].get(source, False)
        if not protected and not known:
            continue
        for index in range(cap):
            network.edge(gate, dispatch, 1, curve[index] if index < len(curve) else 0.)
        for tray in offer["tray_ids"]:
            tray_node = network.node()
            network.edge(dispatch, tray_node, 1, 0.)
            for action in sorted(offers["trays"][tray]["legal_actions"], key=lambda row: (row["destination"], row["action_id"])):
                destination = action["destination"]
                if destination not in receivers or (source, destination) not in reachable or source == destination:
                    continue
                cost = transport_cost(action, config)
                if not protected:
                    cost += config["minimum_net_gain"]
                edge = network.edge(tray_node, receivers[destination], 1, cost)
                selected_edges.append((edge, action))
    sent, objective = network.solve(start, sink, limit)
    chosen = [copy.deepcopy(action) for edge, action in selected_edges if edge[4]-edge[2] == 1]
    return chosen, objective, {source: edge[4]-edge[2] for source, edge in hold_edges.items()}, sent


def solve_optional_transport(graph, offers, values, config=None):
    """Protect ordinary returns, then send all optional supply through move/HOLD."""
    config = allocation_config(config)
    if any(item["public_state_digest"] != offers["public_state_digest"] for item in (graph, values)):
        raise ValueError("transport_allocation:inconsistent_public_state")
    if values["config"] != config:
        raise ValueError("transport_allocation:marginal_config_mismatch")
    used = Counter()
    ordinary, protected_objective, _, protected_sent = _solve_layer(
        graph, offers, values, config, protected=True, receiver_used=used)
    used.update(row["destination"] for row in ordinary)
    optional, optional_objective, hold, _ = _solve_layer(
        graph, offers, values, config, protected=False, receiver_used=used)
    chosen = ordinary + optional
    # Stable order is advisory. The adapter reranks the first protected/optional
    # action using exact ETA and revalidates the current physical menu.
    chosen.sort(key=lambda row: (row["source_category"] != "ordinary_return",
        transport_cost(row, config), row["source"], row["destination"], str(row["tray_id"])))
    counts, source_marginal_index, receiver_marginal_index, profile = Counter(), Counter(), Counter(), []
    for row in chosen:
        owner = row["owner_id"]
        slot = counts[owner]
        counts[owner] += 1
        submit = offers["now"] + slot*config["dispatch_slot_seconds"]
        departure = max(float(row["earliest_departure"]), submit+config["command_delay_seconds"])
        row["suggested_submit_at"] = submit
        row["suggested_departure_at"] = departure
        row["suggested_arrival_at"] = departure+row["static_travel_time"]
        source, destination = row["source"], row["destination"]
        source_curve, receiver_curve = values["source_marginals"].get(source, []), values["receiver_marginals"].get(destination, [])
        source_index, receiver_index = source_marginal_index[source], receiver_marginal_index[destination]
        source_marginal_index[source] += 1
        receiver_marginal_index[destination] += 1
        source_cost = source_curve[source_index] if source_index < len(source_curve) else None
        receiver_gain = receiver_curve[receiver_index] if receiver_index < len(receiver_curve) else None
        row["marginal_source_cost"] = source_cost
        row["marginal_receiver_benefit"] = receiver_gain
        row["transport_cost"] = transport_cost(row, config)
        row["proxy_marginal_gain"] = (None if source_cost is None or receiver_gain is None else
            receiver_gain-source_cost-row["transport_cost"])
        profile.append({"action_id": row["action_id"], "owner_id": owner, "tray_id": row["tray_id"],
            "source": row["source"], "destination": row["destination"], "dispatch_slot": slot,
            "submit_at": submit, "earliest_departure": departure,
            "estimated_arrival": row["suggested_arrival_at"], "optimistic_advisory_only": True})
    flow_counts = Counter((row["source"], row["destination"], row["source_category"]) for row in chosen)
    protected_cap = sum(row["source_cap"] for row in offers["sources"].values() if row["source_category"] == "ordinary_return")
    used_edges = Counter()
    arc_index = {(row["source_terminal"], row["destination_terminal"]): row for row in graph["arcs"]}
    for row in chosen:
        used_edges.update(tuple(edge) for edge in arc_index[row["source"], row["destination"]]["physical_edges"])
    result = {"schema": SCHEMA, "public_state_digest": offers["public_state_digest"],
        "catalog_id": offers["catalog_id"], "chosen": chosen,
        "flows": [{"source": s, "destination": d, "source_category": c, "suggested_quantity": n}
            for (s, d, c), n in sorted(flow_counts.items())],
        "hold_by_source": dict(hold), "hold_quantity": sum(hold.values()),
        "protected_unallocated_quantity": protected_cap-protected_sent,
        "ordinary_return_fallback_required": protected_cap > protected_sent,
        "proxy_flow_objective_cost": protected_objective+optional_objective,
        "objective": {"protected_cost": protected_objective, "optional_cost": optional_objective,
            "net_proxy_gain": -protected_objective-optional_objective,
            "minimum_gain_penalty_included": config["minimum_net_gain"]},
        "dispatch_profile": profile, "config": config,
        "marginal_gain_profile": [{"action_id": row["action_id"], "proxy_gain": row["proxy_marginal_gain"],
            "source_opportunity_cost": row["marginal_source_cost"],
            "receiver_benefit": row["marginal_receiver_benefit"], "transport_cost": row["transport_cost"]}
            for row in chosen],
        "shared_witness_edges": [{"from": edge[0], "to": edge[1], "planned_crossings": count}
            for edge, count in sorted(used_edges.items()) if count > 1],
        "first_action_verification": {"status": "required_in_controller", "mode": config["first_action_verification_mode"]},
        "optimization_scope": "protected_maximum_feasible_return_then_optional_conservative_separable_mcf",
        "slot_delay_in_flow_cost": False, "later_slots_require_replanning": True,
        "native_execution_authority": False}
    result["allocation_id"] = digest(result)
    return result
