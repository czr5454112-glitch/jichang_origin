"""Rolling terminal allocation -> one current legal empty transfer.

The controller remains the only submitter. Forecasts supply demand only;
the flow plan and deterministic exact-ETA verification select the action.
"""
from __future__ import annotations

import copy
import time

from .foundation_airport_batch_patch import digest
from .foundation_airport_inventory_projection import project_action, require
from .foundation_airport_joint_rules import select_joint_action
from . import foundation_airport_transport_orders as orders

SCHEMA = "g31.terminal_flow.control.v1"


def _key(candidate):
    return (candidate["tray_id"], candidate["source"], candidate["destination"])


def invalidation_signature(prepared, catalog, projection, policy_state):
    """Coalesce relevant events once per callback, excluding clock/version churn."""
    return digest(dict(
        topology=[prepared.observation["node_records"], prepared.observation["edge_records"],
                  prepared.observation.get("edge_contracts"), prepared.observation.get("known_faults")],
        contracts=prepared.observation["node_contracts"],
        menu=sorted(_key(row) for row in catalog["candidates"] if row["action_type"] == "transfer"),
        accounts={node: {k: v for k, v in state.items() if k in
            ("stock", "waiting", "inventory_known", "waiting_known", "service_rate")}
            for node, state in projection.nodes.items()},
        commitments=[(r.get("request_id"), r.get("status"))
                     for r in prepared.observation.get("client_transfer_ledger", [])],
        claims=orders.outstanding_uncredited(policy_state, projection)))


def choose_next_legal_action(plan, prepared_current, catalog, projection, *, config):
    """Rebind cached suggestions to the fresh complete menu before verification."""
    indexed = {_key(r): r for r in catalog["candidates"] if r["action_type"] == "transfer"}
    ordinary = any(r.get("source_category") == "ordinary_return" for r in indexed.values())
    scored, invalid = [], []
    for proposed in plan.get("chosen", []):
        candidate = indexed.get(_key(proposed))
        if candidate is None:
            invalid.append(dict(key=list(_key(proposed)), reason="not_in_fresh_legal_menu"))
            continue
        if ordinary and candidate["source_category"] != "ordinary_return":
            continue
        exact = project_action(projection, candidate)
        net = (None if exact["proxy_gain"] is None else exact["proxy_gain"]
               - config["transport_penalty_weight"] * candidate["static_travel_time"])
        if candidate["source_category"] != "ordinary_return" and (
                net is None or net <= config["minimum_net_gain"]):
            invalid.append(dict(key=list(_key(candidate)), reason="exact_eta_nonpositive_or_unknown", net_gain=net))
            continue
        state = prepared_current.inventory["nodes"][candidate["destination"]]
        capacity = prepared_current.contracts[candidate["destination"]]["capacity"]
        occupancy = state.get("occupancy")
        slack = None if occupancy is None else capacity - occupancy
        scored.append((candidate, exact, net, slack))
    scored.sort(key=lambda row: (row[2] is None, -(row[2] or 0.), row[3] is None,
        -(row[3] or 0.), row[0]["nominal_arrival_time"], row[0]["source"],
        row[0]["destination"], str(row[0]["tray_id"])))
    if scored:
        candidate, exact, net, _ = scored[0]
        return candidate, dict(exact_projection=exact, exact_net_gain=net,
            reason="protected_ordinary_flow" if ordinary else "positive_exact_eta_flow", invalid=invalid)
    return None, dict(reason="flow_has_no_valid_first_action", invalid=invalid)


class TransportPolicy:
    def __init__(self, *, config=None, recompute_period_seconds=60.):
        from .foundation_airport_transport_allocation import DEFAULT_CONFIG
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        require(recompute_period_seconds in (60., 300.), "registered_recompute_period")
        self.period = float(recompute_period_seconds)

    def _solve(self, prepared, catalog, projection, policy_state):
        from .foundation_airport_terminal_graph import build_terminal_graph
        from .foundation_airport_transport_allocation import (
            build_supply_offers, build_marginal_values, solve_optional_transport)
        began = time.perf_counter()
        graph = build_terminal_graph(prepared, catalog=catalog)
        offers = build_supply_offers(prepared, catalog)
        claims = orders.outstanding_uncredited(policy_state, projection)
        # Generate the already-claimed prefix plus this owner's whole supply.
        # Pending claims are logical slots, never physical supply events.
        value_offers = dict(offers, total_source_cap=offers["total_source_cap"]+max(claims.values(), default=0))
        values = build_marginal_values(projection, value_offers, graph["receiver_contract"], self.config)
        claim_orders = orders.outstanding_uncredited(policy_state, projection, detailed=True)
        for node, count in claims.items():
            contract = graph["receiver_contract"].get(node)
            if contract is None:
                continue
            covered_trays = {r["tray_id"] for r in prepared.inventory["known_own_assignment_coverage"].get(node, [])}
            extra_capacity = sum(o["destination_terminal"] == node and o["physical_tray_id"] not in covered_trays
                                 for o in claim_orders)
            contract["available_slots"] = max(0, contract["available_slots"] - extra_capacity)
            for name in ("receiver_marginals", "raw_receiver_marginals"):
                if node in values[name]:
                    values[name][node] = values[name][node][count:]
        plan = solve_optional_transport(graph, offers, values, self.config)
        forecast_id = digest(projection.forecast) if projection.forecast else None
        plan.update(schema=SCHEMA+".plan", version=1, owner_scope=projection.owner,
            information_asof=projection.now, plan_valid_until=projection.now+self.period,
            forecast_id=forecast_id,
            mapping_id=(projection.forecast or {}).get("airport_mapping_sha256"),
            projection_version=projection.audit["schema"],
            projection_horizon_seconds=projection.horizon_seconds, supply_mode=projection.supply_mode,
            receiver_claims_deducted=claims, station_table=graph["station_table"],
            source_offers=copy.deepcopy(offers["sources"]),
            total_current_supply_cap=offers["total_source_cap"],
            marginal_audit=values.get("approximation_audit"),
            configuration=copy.deepcopy(self.config), recompute_period_seconds=self.period,
            native_execution_authority=False, submitted_quantity=0, already_accepted_quantity=0,
            assumptions=["future_dispatch_slots_are_optimistic_lower_bounds", "single_use_proxy",
                         "native_shared_bottleneck_admission", "upper_public_coordinator"])
        # The content identity excludes nondeterministic wall-clock diagnostics.
        plan["plan_id"] = digest(plan)
        plan["solve_seconds"] = time.perf_counter()-began
        return plan

    def select(self, prepared, catalog, projection, *, policy_state, decision_context):
        require(prepared.message_delay == self.config["command_delay_seconds"], "flow_command_delay_binding")
        orders.reconcile(policy_state, prepared.observation)
        orders.supersede_unsubmitted(policy_state, projection.now)
        cache = policy_state.setdefault("terminal_flow_plans", {})
        record = cache.get(projection.owner)
        signature = invalidation_signature(prepared, catalog, projection, policy_state)
        reason = ("initial" if record is None else "event_changed" if record["signature"] != signature
                  else "period_expired" if projection.now >= record["plan"]["plan_valid_until"] else None)
        if reason is not None:
            plan = self._solve(prepared, catalog, projection, policy_state)
            record = cache[projection.owner] = dict(signature=signature, plan=plan)
        else:
            plan = record["plan"]
        candidate, verification = choose_next_legal_action(plan, prepared, catalog, projection, config=self.config)
        ordinary = [r for r in catalog["candidates"] if r.get("source_category") == "ordinary_return"]
        if candidate is None and ordinary and reason is None:
            plan = self._solve(prepared, catalog, projection, policy_state)
            record = cache[projection.owner] = dict(signature=signature, plan=plan)
            reason = "protected_ordinary_replan"
            candidate, verification = choose_next_legal_action(plan, prepared, catalog, projection, config=self.config)
        fallback = None
        if candidate is None and ordinary:
            receiving = {r["node"]: r["receiver"] for r in plan["station_table"]}
            claims = orders.outstanding_uncredited(policy_state, projection)
            allowed = [r for r in ordinary if (
                receiving[r["destination"]]["available_slots"] > 0 if receiving[r["destination"]]["known"]
                else claims.get(r["destination"], 0) == 0)]
            if allowed:
                fallback = "flow_no_covered_ordinary_solution_C00"
                fallback_catalog = dict(catalog, candidates=[r for r in catalog["candidates"]
                    if r["action_type"] == "noop"]+allowed)
                choice = select_joint_action(projection, fallback_catalog, information_variant="C00",
                    transport_penalty=self.config["transport_penalty_weight"])
                candidate = next(r for r in allowed if r["action_id"] == choice["action_id"])
                exact = project_action(projection, candidate)
                verification.update(exact_projection=exact, exact_net_gain=(None if exact["proxy_gain"] is None
                    else exact["proxy_gain"]-self.config["transport_penalty_weight"]*candidate["static_travel_time"]))
            else:
                verification["reason"] = "protected_return_deferred_receiver_slots_claimed"
        if candidate is None:
            candidate = next(r for r in catalog["candidates"] if r["action_type"] == "noop")
        result = dict(action_id=candidate["action_id"], catalog_id=catalog["catalog_id"],
            policy="terminal_flow_v1", reason=fallback or verification["reason"],
            selection_probability=1., fallback_reason=fallback, flow_plan=copy.deepcopy(plan),
            flow_verification=verification, cache=dict(hit=reason is None, invalidation_reason=reason,
                plan_age_seconds=projection.now-plan["information_asof"],
                forecast_age_seconds=None if projection.forecast is None else projection.now-projection.forecast_origin),
            native_execution_authority=False)
        if candidate["action_type"] == "transfer":
            # Preserve the solver's proxy ordering for audit and publish the
            # actual first-order override with freshly anchored future slots.
            by_key = {_key(r): r for r in catalog["candidates"] if r["action_type"] == "transfer"}
            sequence = [candidate]+[by_key[_key(r)] for r in plan.get("chosen", [])
                if _key(r) in by_key and _key(r) != _key(candidate)]
            execution = []
            for slot, action in enumerate(sequence):
                submit = projection.now+slot*self.config["dispatch_slot_seconds"]
                departure = max(action["earliest_departure"], submit+self.config["command_delay_seconds"])
                execution.append(dict(action_id=action["action_id"], owner_id=projection.owner,
                    tray_id=action["tray_id"], source=action["source"], destination=action["destination"],
                    dispatch_slot=slot, submit_at=submit, earliest_departure=departure,
                    estimated_arrival=departure+action["static_travel_time"], optimistic_advisory_only=True))
            result["execution_dispatch_profile"] = execution
            result["flow_plan"]["execution_dispatch_profile"] = execution
            result["flow_plan"]["first_action_verification"] = dict(status="verified", **verification)
            result["empty_transport_order"] = orders.plan_order(policy_state, plan=plan, candidate=candidate,
                projection=projection, exact_projection=verification["exact_projection"], decision_context=decision_context)
        return result

    def on_submission(self, **kwargs):
        orders.record_submission(**kwargs)
