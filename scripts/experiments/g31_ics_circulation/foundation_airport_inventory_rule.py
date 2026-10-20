"""R0: actual demand first, then one current-stock return; no future estimator.

Pure data validation cannot authenticate delivery. The controller obtains the
envelopes only from the native delivered planning_snapshot endpoint. Inventory
preferences never replace native admission or certify future service nonharm.
"""
from __future__ import annotations

import copy
import math
from collections import Counter

from .analytic_control import PublicTravel, public_transfer_scope, transfer_candidates
from .foundation_airport_batch_patch import (
    ACTIVE, SCHEMA as PATCH_SCHEMA, actual_uncommitted, apply_patch, digest,
    fixed_public_prefix)
from .native_preexisting_initial_adapter import capture_digest, coverage_matches_rows

METHOD = "R0_current_stock_v1"
SCHEMA = "g31.foundation.airport_current_inventory.v1"
TERMINAL_WITHOUT_RECEIPT = frozenset(("rejected", "cancelled", "failed", "expired"))


def _owner(row):
    return row.get("resource_owner", row.get("zone"))


def _count(value):
    return type(value) is int and value >= 0


def _time(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def r0_priority_planner(observation, *, predictive=False, respect_service_forecasts=False, **options):
    """Explicit actual-only baseline; fail rather than silently mask a bad config."""
    if predictive is not False or respect_service_forecasts is not False:
        raise ValueError("inventory_rule:R0_requires_actual_only_and_no_service_forecasts")
    if options.get("terminal_clearing", True) is not True:
        raise ValueError("inventory_rule:R0_requires_terminal_clearing")
    options["terminal_clearing"] = True
    decision = transfer_candidates(observation, predictive=False,
        respect_service_forecasts=False, **options)
    decision["policy"] = METHOD
    decision["information_contract"] = "actual_only_no_flight_no_future_release_no_soft_forecast"
    return decision


def make_r0_priority_planner(*, activate_at=7200.):
    """Identical common-rule warmup, then the declared lower-information R0."""
    if not _time(activate_at):
        raise ValueError("inventory_rule:invalid_activation_time")
    def planner(observation, **options):
        if observation["now"] < activate_at:
            return transfer_candidates(observation, **options)
        options["predictive"] = False
        options["respect_service_forecasts"] = False
        return r0_priority_planner(observation, **options)
    return planner


def inventory_view(observation):
    """Current local sensors plus newest *delivered* peer captures, never a sum."""
    now, owner = observation["now"], observation["owner_id"]
    if not _time(now) or not isinstance(owner, str) or not owner:
        raise ValueError("inventory_rule:invalid_current_owner_or_time")
    contracts = {row["node"]: row for row in observation["node_contracts"]}
    if len(contracts) != len(observation["node_contracts"]):
        raise ValueError("inventory_rule:duplicate_node")
    nodes = {node: {"node": node, "known": False, "reported_actual_empty": None,
        "as_of": None, "source_owner": _owner(contract), "source": "unknown",
        "reason": "missing_delivered_inventory"} for node, contract in contracts.items()}
    for node, contract in contracts.items():
        if _owner(contract) == owner:
            value = contract.get("actual_available")
            if _count(value):
                nodes[node].update(known=True, reported_actual_empty=value, as_of=now,
                    source="current_local_sensor", reason=None,
                    occupancy=contract.get("occupancy"), valid_until=None)
            else:
                nodes[node]["reason"] = "missing_local_actual_available"
    latest, invalid = {}, []
    for envelope in observation.get("planning_snapshots", []):
        body = envelope.get("capture", {})
        source = body.get("source_owner")
        captured, delivered = body.get("captured_at"), envelope.get("delivered_at")
        sequence = body.get("publication_sequence")
        # Undelivered updates never replace the actor's last delivered revision.
        if not (_time(captured) and _time(delivered) and delivered <= now
                and type(sequence) is int and sequence > 0 and isinstance(source, str)):
            continue
        key = (captured, sequence)
        old = latest.get(source)
        if old is None or key > old[0]:
            latest[source] = (key, envelope)
        elif key == old[0] and envelope != old[1]:
            raise ValueError("inventory_rule:conflicting_delivered_revision")
    for source, (_, envelope) in latest.items():
        if source == owner:
            continue  # A stale self-copy never replaces a current local sensor.
        body = envelope["capture"]
        expected = {node for node, contract in contracts.items() if _owner(contract) == source}
        reason = None
        try:
            coverage = body["coverage"]
            rows = body["nodes"]
            if (envelope.get("schema") != "g31.planning_snapshot.v1"
                    or envelope.get("kind") != "planning_snapshot"
                    or envelope.get("digest_format") != "g31.planning_capture_digest.v1"
                    or body["schema"] != "g31.planning_capture.v1"
                    or body["target_owner"] != owner or not expected):
                reason = "invalid_snapshot_channel_or_schema"
            elif not (_time(body["valid_until"])
                    and body["captured_at"] <= envelope["delivered_at"] <= now < body["valid_until"]
                    and envelope.get("status") == "conditional"):
                reason = "latest_snapshot_expired_or_invalid_time"
            elif (coverage.get("complete_for_declared_local_scope") is not True
                    or coverage.get("future_arrivals_included") is not False
                    or set(coverage["local_node_ids"]) != expected
                    or len(coverage["local_node_ids"]) != len(expected)
                    or [r["node"] for r in rows] != coverage["local_node_ids"]
                    or not coverage_matches_rows(coverage["tray_ids"], body["trays"], "tray_id")
                    or not coverage_matches_rows(coverage["business_bag_ids"], body["jobs"], "business_bag_id")):
                reason = "incomplete_or_misbound_inventory_coverage"
            elif (any(not _count(r.get("actual_available")) or not _count(r.get("occupancy"))
                    or r["actual_available"] > r["occupancy"] for r in rows)
                    or not isinstance(body.get("static_contract_sha256"), str)
                    or len(body["static_contract_sha256"]) != 64
                    or capture_digest(body) != envelope["payload_sha256"]):
                reason = "invalid_inventory_or_capture_digest"
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            reason = "malformed_inventory_capture"
        if reason:
            invalid.append({"source_owner": source, "reason": reason,
                "message_id": body.get("message_id")})
            for node in expected:
                nodes[node]["reason"] = reason
            continue
        for row in rows:
            nodes[row["node"]].update(known=True, reported_actual_empty=row["actual_available"],
                occupancy=row["occupancy"], as_of=body["captured_at"],
                captured_at=body["captured_at"], delivered_at=envelope["delivered_at"],
                valid_until=body["valid_until"], source="delivered_planning_snapshot",
                message_id=body["message_id"], revision=body["publication_sequence"],
                payload_sha256=envelope["payload_sha256"],
                static_contract_sha256=body["static_contract_sha256"], reason=None)
    # No incoming estimate is added to reported stock. Own requests are only
    # coverage/deduplication evidence and pending is never called accepted.
    coverage = {}
    requests = {}
    for request in observation.get("client_transfer_ledger", []):
        identity = request["request_id"]
        if identity in requests and requests[identity] != request:
            raise ValueError("inventory_rule:conflicting_own_request")
        requests[identity] = request
    for request in requests.values():
        destination, status = request["destination"], request["status"]
        if destination not in nodes or status in TERMINAL_WITHOUT_RECEIPT:
            continue
        state = nodes[destination]
        included = (status == "received" and _time(request.get("received_at"))
            and state["known"] and state["as_of"] >= request["received_at"])
        if included:
            continue
        coverage.setdefault(destination, []).append({
            "request_id": request["request_id"], "tray_id": request["tray_id"],
            "status": status, "accepted_supply_claimed": False,
            "reason": "received_not_yet_covered_by_inventory" if status == "received"
                else "own_request_not_terminal"})
    return {"schema": SCHEMA, "owner_id": owner, "now": now, "nodes": nodes,
        "known_own_assignment_coverage": coverage, "invalid_snapshots": invalid,
        "all_owner_incoming_known": False, "native_delivery_authenticated_by_pure_function": False}


def rank_return_destinations(observation, source, *, view=None, travel=None, optional=False):
    """Legal static loaders ranked by observed stock; unknown never becomes zero."""
    view = inventory_view(observation) if view is None else view
    contracts = {row["node"]: row for row in observation["node_contracts"]}
    roles = observation.get("static_role_contract", {})
    if (roles.get("schema") != "g31.static_node_roles.v1"
            or type(roles.get("loader_nodes")) is not list
            or len(set(roles["loader_nodes"])) != len(roles["loader_nodes"])):
        raise ValueError("inventory_rule:invalid_static_loader_directory")
    travel = PublicTravel(observation) if travel is None else travel
    rows = []
    for destination in roles["loader_nodes"]:
        if destination not in contracts:
            raise ValueError("inventory_rule:unknown_static_loader")
        contract, stock = contracts[destination], view["nodes"][destination]
        scope = public_transfer_scope(observation, source, destination,
            actual_available=True, contracts=contracts)
        if (scope is None or not contract.get("allow_receive", True)
                or contract.get("capacity", 0) <= 0
                or destination in view["known_own_assignment_coverage"]):
            continue
        if stock["known"] and _count(stock.get("occupancy")) and stock["occupancy"] >= contract["capacity"]:
            continue
        distance = travel.complete(source, destination)
        if not math.isfinite(distance):
            continue
        if optional and (not stock["known"] or stock["reported_actual_empty"] != 0):
            continue
        rows.append({"destination": destination, "transfer_scope": scope,
            "reported_actual_empty": stock["reported_actual_empty"],
            "inventory_known": stock["known"], "static_travel_cost": distance,
            "inventory_source": stock["source"], "inventory_as_of": stock["as_of"]})
    known = [row for row in rows if row["inventory_known"]]
    if known:
        return sorted(known, key=lambda r: (r["reported_actual_empty"], r["static_travel_cost"], r["destination"]))
    return [] if optional else sorted(rows, key=lambda r: (r["static_travel_cost"], r["destination"]))


def select_stock_return(observation, baseline=None, *, message_delay=0.,
                        request_prefix="inventory", expiry_slack=60.):
    """Return a baseline with zero/one addition, only after priority exhaustion."""
    if not (_time(message_delay) and _time(expiry_slack) and expiry_slack > 0):
        raise ValueError("inventory_rule:invalid_timing")
    baseline = (r0_priority_planner(observation, message_delay=message_delay,
        request_prefix=request_prefix) if baseline is None else baseline)
    result = copy.deepcopy(baseline)
    audit = {"method": METHOD, "selected": False, "reason": "no_legal_stock_return",
        "added_intents": 0, "no_future_release_or_flight_input": True}
    result["inventory_return"] = audit
    if baseline["intents"]:
        audit["reason"] = "priority_intents_remain"
        return result
    if any(row["ledger"] != "actual_available" for row in baseline.get("forecasts", [])):
        raise ValueError("inventory_rule:post_return_baseline_must_be_actual_only")
    view = inventory_view(observation)
    audit["inventory"] = view
    contracts = {r["node"]: r for r in observation["node_contracts"]}
    loaders = set(observation.get("static_role_contract", {}).get("loader_nodes", []))
    supplies = actual_uncommitted(observation, baseline)
    travel = PublicTravel(observation)
    pledged = {r["tray_id"] for r in observation.get("client_transfer_ledger", []) if r["status"] in ACTIVE}
    local_empty = Counter(t["node"] for t in observation.get("trays", [])
        if t["mode"] == "empty" and t.get("edge_to", -1) < 0
        and t.get("reception_node", -1) < 0 and t.get("available_at", observation["now"]) <= observation["now"]
        and t["tray_id"] not in pledged and _owner(contracts[t["node"]]) == observation["owner_id"])
    protected_surplus = Counter(s["node"] for s in supplies)
    supply_indices = {s["tray_id"]: i for i, s in enumerate(baseline.get("supplies", []))}
    for supply in sorted(supplies, key=lambda s: (s["node"] in loaders, s["node"], s["tray_id"])):
        source = supply["node"]
        if not view["nodes"][source]["known"]:
            continue
        # A currently feasible real-demand/mandatory pairing retains priority.
        index = supply_indices[supply["tray_id"]]
        if any(row["supply"] == index for row in baseline.get("pool", [])):
            continue
        optional = source in loaders
        minimum = int(contracts[source].get("export_min_stock", 0))
        fifo_reserved = max(0, local_empty[source] - protected_surplus[source] - minimum)
        if optional and local_empty[source] - fifo_reserved - 1 < max(1, minimum):
            continue
        ranked = rank_return_destinations(observation, source, view=view, travel=travel, optional=optional)
        if not ranked:
            continue
        destination = ranked[0]
        now = observation["now"]
        intent = {"tray_id": supply["tray_id"], "source": source,
            "destination": destination["destination"], "owner_id": observation["owner_id"],
            "issued_at": now, "message_delay": message_delay,
            "earliest_departure": now + message_delay,
            "expiry": now + message_delay + destination["static_travel_cost"] + expiry_slack,
            "forecast_dependency": supply["dependency"], "forecast_ledger": "actual_available",
            "transfer_scope": destination["transfer_scope"],
            "control_reason": "optional_zero_stock_replenishment" if optional else "ordinary_return_to_loader"}
        action = {"schema": PATCH_SCHEMA, "kind": "add_optional",
            "action_id": f"{request_prefix}:{source}:{supply['tray_id']}:{destination['destination']}",
            "tray_id": supply["tray_id"], "intent": intent,
            "public_state_digest": digest(observation), "baseline_batch_digest": digest(baseline["intents"]),
            "immutable_request_prefix_digest": digest(fixed_public_prefix(observation))}
        result = apply_patch(observation, baseline, action)
        audit.update(selected=True, reason=intent["control_reason"], added_intents=1,
            fallback_reason=None if destination["inventory_known"] else "inventory_unknown",
            ranked_destinations=ranked, legal_destination_count=len(ranked),
            selected_action=action, source_fifo_reserved=fifo_reserved,
            source_actual_unpledged=local_empty[source])
        result["inventory_return"] = audit
        return result
    return result
