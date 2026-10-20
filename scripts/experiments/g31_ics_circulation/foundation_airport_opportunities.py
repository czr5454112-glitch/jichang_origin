"""Shared no-plan bounded catalogue from static roles and actual public supply."""
from __future__ import annotations

from collections import Counter
import copy
import math

from .analytic_control import (PublicTravel, ReleaseForecast,
    departure_avoiding_published_windows, public_transfer_scope)
from .foundation_airport_batch_patch import (
    SCHEMA as PATCH_SCHEMA, actual_uncommitted, digest, fixed_public_prefix, mandatory, require)


SCHEMA = "g31.foundation.airport_opportunity.v1"
CATALOG_VERSION = "static_loader_current_surplus_v1"
FULL_CATALOG_VERSION = "static_all_loaders_current_surplus_v2"


def build_opportunity(observation, baseline, *, continuation_version,
                      message_delay=2., respect_service_forecasts=True, k_max=3):
    """Build bounded complete-batch choices using only the public current.

    No flight plan or evaluator input is accepted here. Observed-source-queue
    assignments are optional R2 commitments of a locally surplus tray; terminal
    clearing is mandatory. Altering these assignments is an isolated experiment,
    not an assertion that currently waiting baggage cannot be harmed.
    """
    require(type(k_max) is int and 1 <= k_max <= 13, "K_between_one_and_thirteen")
    full_catalog = k_max > 3
    owner, now = observation["owner_id"], observation["now"]
    common = {"schema": PATCH_SCHEMA, "public_state_digest": digest(observation),
        "baseline_batch_digest": digest(baseline["intents"]),
        "immutable_request_prefix_digest": digest(fixed_public_prefix(observation))}
    reference = dict(common, action_id="a_ref", kind="a_ref", tray_id=None, intent=None)
    actual = actual_uncommitted(observation, baseline)
    by_id = {row["tray_id"]: row for row in actual}
    # The intervention must be the next transfer submitted. A later batch
    # member would disappear when the ordinary controller recomputes residual.
    first = baseline["intents"][0] if baseline["intents"] else None
    chosen = (by_id.get(first.get("tray_id")) if first and not mandatory(first) else None)
    old = first if chosen is not None else None
    if chosen is None:
        assigned = {row.get("tray_id") for row in baseline["intents"]}
        spare = sorted((row for row in actual if row["tray_id"] not in assigned),
                       key=lambda row: (row["node"], row["tray_id"]))
        chosen = spare[0] if spare else None
    actions, mask_reasons = [reference], Counter()
    roles = observation.get("static_role_contract", {})
    if chosen is None:
        mask_reasons["no_next_optional_actual_surplus_tray"] += 1
    elif roles.get("schema") != "g31.static_node_roles.v1":
        mask_reasons["missing_versioned_static_loader_roles"] += 1
    elif k_max > 1:
        contracts = {int(row["node"]): row for row in observation["node_contracts"]}
        travel = PublicTravel(observation)
        # Demand ranking uses only delivered visible queue rows, never plans.
        pressure = Counter()
        for row in baseline.get("demands", []):
            if row.get("demand_kind") == "observed_source_queue":
                pressure[int(row["origin"])] += 1
        source = int(chosen["node"])
        alternatives = []
        for destination in sorted(roles["loader_nodes"]):
            if source == destination or (old and destination == old["destination"]):
                continue
            scope = public_transfer_scope(observation, source, destination,
                actual_available=True, contracts=contracts)
            if scope is None or not contracts[destination].get("allow_receive", True):
                mask_reasons["static_scope_or_receive_not_eligible"] += 1
                continue
            if full_catalog and contracts[destination].get("capacity", 1) <= 0:
                mask_reasons["static_nonpositive_receive_capacity"] += 1
                continue
            duration = travel.complete(source, destination)
            if not math.isfinite(duration):
                mask_reasons["static_unreachable"] += 1
                continue
            window = (departure_avoiding_published_windows(observation,
                ReleaseForecast(**chosen), destination, travel, message_delay)
                if respect_service_forecasts else None)
            departure = max(now + message_delay,
                window["earliest_departure"] if window else now)
            intent = {"tray_id": chosen["tray_id"], "source": source,
                "destination": destination, "issued_at": now, "owner_id": owner,
                "message_delay": message_delay, "earliest_departure": departure,
                "expiry": departure + duration + 60.,
                "forecast_dependency": chosen["dependency"], "forecast_ledger": "actual_available",
                "transfer_scope": scope, "control_reason": "isolated_bounded_optional_patch",
                "service_window": window, "expected_version": observation.get("version", 0)}
            alternatives.append(((-pressure[destination] / (1. + duration), duration, destination), intent))
        if alternatives:
            ordered = sorted(alternatives, key=lambda row: row[0])
            available_slots = k_max - 1 - int(bool(old))
            chosen_alternatives = ordered[:available_slots] if full_catalog else ordered[:1]
            for rank, (_, intent) in enumerate(chosen_alternatives):
                actions.append(dict(common,
                    action_id="a_patch" if rank == 0 else f"a_patch:{intent['destination']}",
                    kind="replace_optional" if old else "add_optional",
                    tray_id=chosen["tray_id"], intent=intent,
                    static_arrival_estimate=intent["earliest_departure"] + travel.complete(source, intent["destination"]),
                    estimate_semantics="public_static_capacity_relaxed_estimate"))
        else:
            mask_reasons["no_different_static_destination"] += 1
        if old and len(actions) < k_max:
            actions.append(dict(common, action_id="hold_optional", kind="hold_optional",
                tray_id=chosen["tray_id"], intent=None))
    opportunity = {"schema": SCHEMA, "owner_id": owner, "observed_at": now,
        "current_view_version": observation.get("version", 0), **{k: v for k, v in common.items() if k != "schema"},
        "mandatory_intents": copy.deepcopy([row for row in baseline["intents"] if mandatory(row)]),
        "optional_intents": copy.deepcopy([row for row in baseline["intents"] if not mandatory(row)]),
        "actual_uncommitted_trays": actual,
        "received_peer_message_ids": [row.get("message_id") for row in observation.get("delivered_messages", [])],
        "candidate_catalog_version": FULL_CATALOG_VERSION if full_catalog else CATALOG_VERSION,
        "static_loader_count": len(roles.get("loader_nodes", [])),
        "legal_destination_count": len(alternatives) if chosen is not None and k_max > 1
            and roles.get("schema") == "g31.static_node_roles.v1" else 0,
        "candidate_destination_nodes": [row["intent"]["destination"] for row in actions
            if row.get("intent") is not None],
        "K": len(actions), "K_max": k_max,
        "P": 2, "K_meaning": "candidate complete-batch choices including reference",
        "P_meaning": "two separately budgeted native continuations, no internal simulation",
        "peer_policy_version": continuation_version, "continuation_version": continuation_version,
        "forecast_model_id": None, "forecast_asof": None, "model_available_at": None,
        "catalog_uses_future_plan": False, "candidates": actions,
        "mask_reasons": dict(mask_reasons), "current_guard_status": "shared_resource_nonharm_unknown",
        "protected_takeover_eligible": False}
    opportunity["opportunity_id"] = digest({k: opportunity[k] for k in
        ("owner_id", "observed_at", "public_state_digest", "baseline_batch_digest", "candidate_catalog_version")})
    return opportunity
