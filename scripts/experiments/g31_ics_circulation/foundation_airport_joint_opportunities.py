"""Current-only joint tray/source/destination proposals after actual priority.

A prepared view is a calculation cache, never authority to submit. The native
protocol retains admission, ownership, capacity and physical transport control.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math

from .analytic_control import PublicTravel, public_transfer_scope
from .foundation_airport_batch_patch import ACTIVE, actual_uncommitted, digest, fixed_public_prefix
from .foundation_airport_inventory_rule import inventory_view, rank_return_destinations

SCHEMA = "g31.foundation.airport_joint_catalog.v1"
CATALOG_VERSION = "actual_multisource_loader_reserve_target_relaxed_v1"


def require(condition, reason):
    if not condition:
        raise ValueError("joint_opportunities:" + reason)


@dataclass
class PreparedCurrent:
    observation: dict
    baseline: dict
    inventory: dict
    contracts: dict
    travel: PublicTravel
    supplies: list
    public_state_digest: str
    priority_baseline_digest: str
    immutable_prefix_digest: str
    message_delay: float
    expiry_slack: float


def prepare_current(observation, priority_baseline, *, message_delay=0., expiry_slack=60.):
    require(type(message_delay) in (int, float) and math.isfinite(message_delay)
        and message_delay >= 0 and type(expiry_slack) in (int, float)
        and math.isfinite(expiry_slack) and expiry_slack > 0, "invalid_timing")
    require(not priority_baseline["intents"], "priority_intents_remain")
    require(all(row["ledger"] == "actual_available"
        for row in priority_baseline.get("forecasts", [])), "actual_only_baseline_required")
    contracts = {row["node"]: row for row in observation["node_contracts"]}
    roles = observation.get("static_role_contract", {})
    loaders = roles.get("loader_nodes")
    require(roles.get("schema") == "g31.static_node_roles.v1" and type(loaders) is list
        and len(loaders) == len(set(loaders))
        and all(type(node) is int and node in contracts for node in loaders),
        "invalid_static_loader_directory")
    return PreparedCurrent(observation, priority_baseline, inventory_view(observation), contracts,
        PublicTravel(observation), actual_uncommitted(observation, priority_baseline),
        digest(observation), digest(priority_baseline), digest(fixed_public_prefix(observation)),
        float(message_delay), float(expiry_slack))


def assert_prepared_current(prepared):
    require(digest(prepared.observation) == prepared.public_state_digest, "stale_public_state")
    require(digest(prepared.baseline) == prepared.priority_baseline_digest, "changed_priority_baseline")
    require(digest(fixed_public_prefix(prepared.observation)) == prepared.immutable_prefix_digest,
        "changed_immutable_prefix")


def build_joint_catalog(prepared, catalog_config=None):
    """Enumerate all current legal single moves; forecast input is unsupported.

    Unknown target inventory remains unknown. It neither proves zero inventory
    nor asserts native receiving admission. No learned/reference choice enters
    menu identity, and no source is selected before destinations are examined.
    """
    config = {} if catalog_config is None else dict(catalog_config)
    require(not set(config) - {"catalog_version"}, "unknown_catalog_config")
    require(config.get("catalog_version", CATALOG_VERSION) == CATALOG_VERSION, "catalog_version")
    observation, baseline = prepared.observation, prepared.baseline
    owner, now = observation["owner_id"], observation["now"]
    loaders = set(observation["static_role_contract"]["loader_nodes"])
    common = {"owner_id": owner, "public_state_digest": prepared.public_state_digest,
        "priority_baseline_digest": prepared.priority_baseline_digest,
        "immutable_prefix_digest": prepared.immutable_prefix_digest,
        "catalog_version": CATALOG_VERSION, "observed_at": now,
        "current_view_version": observation.get("version", 0)}
    actions = [{**common, "action_id": "a_noop", "action_type": "noop", "kind": "noop",
        "tray_id": None, "source": None, "destination": None, "intent": None,
        "source_generation_or_dependency": None, "earliest_departure": None,
        "static_arrival_estimate": None, "nominal_arrival_time": None,
        "static_travel_time": 0., "eta_model_kind": "not_applicable", "transfer_scope": None,
        "hard_eligibility_reasons": ["priority_exhausted"], "bridge_eligible": True}]
    pledged = {row["tray_id"] for key in ("transfers", "client_transfer_ledger")
        for row in observation.get(key, []) if row.get("status") in ACTIVE}
    local_empty = Counter(row["node"] for row in observation.get("trays", [])
        if row["mode"] == "empty" and row.get("edge_to", -1) < 0
        and row.get("reception_node", -1) < 0 and row.get("available_at", now) <= now
        and row["tray_id"] not in pledged
        and prepared.contracts[row["node"]].get("resource_owner",
            prepared.contracts[row["node"]].get("zone")) == owner)
    surplus = Counter(row["node"] for row in prepared.supplies)
    indices = {row["tray_id"]: index for index, row in enumerate(baseline.get("supplies", []))}
    priority_indices = {row["supply"] for row in baseline.get("pool", [])}
    exclusions, eligible_trays = Counter(), []
    if not prepared.supplies:
        exclusions["no_actual_uncommitted_surplus"] = 1
    for supply in sorted(prepared.supplies, key=lambda row: (row["node"], row["tray_id"])):
        source, tray_id = supply["node"], supply["tray_id"]
        if not prepared.inventory["nodes"][source]["known"]:
            exclusions["source_inventory_unknown"] += 1
            continue
        if indices[tray_id] in priority_indices:
            exclusions["feasible_priority_pair_retained"] += 1
            continue
        optional = source in loaders
        minimum = int(prepared.contracts[source].get("export_min_stock", 0))
        fifo_reserved = max(0, local_empty[source] - surplus[source] - minimum)
        if optional and local_empty[source] - fifo_reserved - 1 < max(1, minimum):
            exclusions["source_loader_fifo_or_minimum_reserve"] += 1
            continue
        eligible_trays.append(tray_id)
        bridge_destinations = {row["destination"] for row in rank_return_destinations(
            observation, source, view=prepared.inventory, travel=prepared.travel, optional=optional)}
        for destination in sorted(loaders):
            contract, stock = prepared.contracts[destination], prepared.inventory["nodes"][destination]
            scope = public_transfer_scope(observation, source, destination,
                actual_available=True, contracts=prepared.contracts)
            if (scope is None or not contract.get("allow_receive", True)
                    or contract.get("capacity", 0) <= 0):
                exclusions["scope_or_receive_ineligible"] += 1
                continue
            if destination in prepared.inventory["known_own_assignment_coverage"]:
                exclusions["known_own_assignment_coverage"] += 1
                continue
            if (stock["known"] and type(stock.get("occupancy")) is int
                    and stock["occupancy"] >= contract["capacity"]):
                exclusions["known_destination_full"] += 1
                continue
            duration = prepared.travel.complete(source, destination)
            if not math.isfinite(duration):
                exclusions["static_unreachable"] += 1
                continue
            departure = now + prepared.message_delay
            reason = "joint_optional_reposition" if optional else "ordinary_return_to_loader"
            intent = {"tray_id": tray_id, "source": source, "destination": destination,
                "owner_id": owner, "issued_at": now, "message_delay": prepared.message_delay,
                "earliest_departure": departure, "expiry": departure + duration + prepared.expiry_slack,
                "forecast_dependency": supply["dependency"], "forecast_ledger": "actual_available",
                "transfer_scope": scope, "control_reason": reason}
            identity = digest([owner, prepared.public_state_digest, tray_id, source, destination])
            actions.append({**common, "action_id": "a_transfer:" + identity,
                "action_type": "transfer", "kind": "transfer", "tray_id": tray_id,
                "source": source, "destination": destination, "intent": intent,
                "source_generation_or_dependency": supply["dependency"],
                "earliest_departure": departure, "static_arrival_estimate": departure + duration,
                "nominal_arrival_time": departure + duration, "static_travel_time": duration,
                "eta_model_kind": "public_static_capacity_relaxed_estimate",
                "transfer_scope": scope, "hard_eligibility_reasons": ["actual_uncommitted",
                    "fifo_and_minimum_reserved", "priority_exhausted", "public_scope_and_path"],
                "source_category": "loader_optional" if optional else "ordinary_return",
                "source_fifo_reserved": fifo_reserved, "source_actual_unpledged": local_empty[source],
                "destination_inventory_known": stock["known"],
                "destination_actual_empty": stock["reported_actual_empty"],
                "bridge_eligible": destination in bridge_destinations})
    moved = actions[1:]
    catalog = {"schema": SCHEMA, **common, "candidates": actions,
        "K": len(actions), "K_max": 1 + len(prepared.supplies) * len(loaders),
        "priority_surplus_supply_count": len(baseline.get("supplies", [])),
        "actual_uncommitted_supply_count": len(prepared.supplies),
        "eligible_source_tray_count": len(eligible_trays),
        "candidate_source_tray_count": len({row["tray_id"] for row in moved}),
        "candidate_source_node_count": len({row["source"] for row in moved}),
        "candidate_destination_count": len({row["destination"] for row in moved}),
        "catalog_uses_future_plan": False, "pruning": "none_full_legal_single_move_menu",
        "exclusions": dict(exclusions), "reference_candidate_id": None}
    # Reference remains deliberately absent from the identity and from actor input.
    catalog["catalog_id"] = digest({key: value for key, value in catalog.items()
        if key != "reference_candidate_id"})
    return catalog
