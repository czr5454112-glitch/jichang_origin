"""Current-stock and forecast rules over one shared joint action catalog."""
from __future__ import annotations

import math

from .foundation_airport_inventory_projection import (
    PreparedProjection, demand_mass, project_action, require, number)
from .foundation_airport_batch_patch import digest

SCHEMA = "g31.foundation.airport_joint_rules.v1"
DEFAULT_PARAMETERS = {"transport_penalty": .01, "minimum_gain": 0., "proxy_horizon_seconds": 600.}


def _check_catalog(prepared, catalog):
    candidates = catalog["candidates"]
    require(candidates and len({row["action_id"] for row in candidates}) == len(candidates), "unique_catalog_actions")
    require(sum(row["action_type"] == "noop" for row in candidates) == 1, "one_noop")
    # The catalog/controller revalidates native admission. These checks prevent
    # stale feature contexts from being silently paired with a fresh catalog.
    for row in candidates:
        if "public_state_digest" in row:
            require(row["public_state_digest"] == prepared.public_state_digest, "prepared_catalog_state")
    return candidates


def _current_stock_key(prepared, candidate):
    state = prepared.nodes[candidate["destination"]]
    stock = state["stock"]
    waiting = state["waiting"]
    return (stock is None, 0. if stock is None else stock,
            -(0. if waiting is None else waiting), candidate["static_travel_time"],
            candidate["source"], str(candidate["tray_id"]), candidate["destination"], candidate["action_id"])


def score_joint_catalog(prepared, catalog, *, information_variant="C00", transport_penalty=.01,
                        minimum_gain=0.):
    """Score every mutually exclusive proposal against the actual no-op.

    C00 reads current accounts only. C10 uses identical physical accounting
    plus B1 demand. Ordinary return keeps its common priority; optional moves
    require positive known proxy improvement, except C00's explicit current
    zero-stock balancing rule. Unknown costs never become large gains.
    """
    require(information_variant in ("C00", "C10", "Rforecast_prior"), "rule_information_variant")
    penalty, threshold = number(transport_penalty), number(minimum_gain)
    require(penalty >= 0 and threshold >= 0, "nonnegative_frozen_parameters")
    forecast_enabled = information_variant != "C00"
    require(not forecast_enabled or prepared.forecast is not None, "C10_requires_forecast")
    candidates = _check_catalog(prepared, catalog)
    noop = next(row for row in candidates if row["action_type"] == "noop")
    scores, indexed = [], {}
    for candidate in candidates:
        result = project_action(prepared, candidate, use_forecast=forecast_enabled)
        travel = 0. if candidate["action_type"] == "noop" else number(candidate["static_travel_time"])
        score = None if result["proxy_gain"] is None else result["proxy_gain"]-penalty*travel
        row = {"action_id": candidate["action_id"], "score": score,
            "proxy_gain": result["proxy_gain"], "transport_cost": penalty*travel,
            "projection": result, "selection_basis": "no_op_relative_known_account_proxy"}
        scores.append(row)
        indexed[candidate["action_id"]] = row
    ordinary = [row for row in candidates if row["action_type"] == "transfer" and row["source"] not in prepared.loaders]
    positive = [row for row in candidates if row["action_type"] == "transfer"
                and indexed[row["action_id"]]["score"] is not None
                and indexed[row["action_id"]]["score"] > threshold]
    positive.sort(key=lambda row: (-indexed[row["action_id"]]["score"], _current_stock_key(prepared, row)))
    selected, reason = noop, "hold_no_positive_known_proxy_gain"
    if ordinary:
        ordinary_ids = {row["action_id"] for row in ordinary}
        useful = [row for row in positive if row["action_id"] in ordinary_ids]
        selected = useful[0] if useful else min(ordinary, key=lambda row: _current_stock_key(prepared, row))
        reason = "ordinary_return_positive_proxy" if useful else "ordinary_return_current_stock_then_eta"
    elif positive:
        selected, reason = positive[0], "positive_known_proxy_gain"
    elif not forecast_enabled:
        balance = [row for row in candidates if row["action_type"] == "transfer"
            and prepared.nodes[row["destination"]]["stock"] == 0.
            and prepared.nodes[row["source"]]["stock"] is not None
            and prepared.nodes[row["source"]]["stock"] >= 2.]
        if balance:
            selected, reason = min(balance, key=lambda row: _current_stock_key(prepared, row)), "current_zero_stock_balance"
    return {"schema": SCHEMA, "information_variant": information_variant,
        "selected_action_id": selected["action_id"], "selection_reason": reason,
        "scores": scores, "parameters": {"transport_penalty": penalty, "minimum_gain": threshold,
            "proxy_horizon_seconds": prepared.horizon_seconds, "supply_mode": prepared.supply_mode},
        "forecast_id": digest(prepared.forecast) if forecast_enabled else None,
        "mapping_id": prepared.forecast.get("airport_mapping_sha256") if forecast_enabled else None,
        "arrival_support_contract_sha256": prepared.audit["arrival_support_contract_sha256"],
        "future_information_read": forecast_enabled, "outcome_labels_read": False,
        "native_execution_authority": False}


def select_joint_action(prepared, catalog, **kwargs):
    report = score_joint_catalog(prepared, catalog, **kwargs)
    chosen = report["selected_action_id"]
    return {"action_id": chosen, "catalog_id": catalog["catalog_id"],
        "policy": report["information_variant"]+"_joint_inventory_v1", "reason": report["selection_reason"],
        "behavior_reference": chosen, "comparison_reference": chosen, "selection_probability": 1.,
        "score_report": report}


def _shortage(projection, side):
    row = projection.get(side)
    return None if row is None else row["first_shortage_offset"]


def _sum_known(values):
    return None if any(value is None for value in values) else math.fsum(values)


def joint_candidate_features(prepared: PreparedProjection, catalog):
    """Return independently computed current and forecast feature dictionaries.

    None means missing. The trainer adds missing indicators and fits train-only
    normalization. A support key is a descriptive action class, not proof that
    behavior data cover that action or that a learned Q estimate is supported.
    """
    candidates = _check_catalog(prepared, catalog)
    common_current = {"decision_time": prepared.now, "proxy_horizon_seconds": prepared.horizon_seconds,
        "known_inventory_nodes": float(sum(row["inventory_known"] for row in prepared.nodes.values())),
        "known_waiting_nodes": float(sum(row["waiting_known"] for row in prepared.nodes.values())),
        "visible_current_stock_sum": math.fsum(row["stock"] for row in prepared.nodes.values() if row["stock"] is not None),
        "visible_current_waiting_sum": math.fsum(row["waiting"] for row in prepared.nodes.values() if row["waiting"] is not None)}
    common_forecast = {"forecast_age": None if prepared.forecast is None else prepared.now-prepared.forecast_origin}
    forecast = prepared.forecast or {}
    forecast_id = digest(forecast) if forecast else None
    provenance = forecast.get("calendar_provenance", {})
    absolute_cutoffs = provenance.get("absolute", {}).get("information_cutoffs", {})
    availability = [value for value in (
        forecast.get("model_available_at_epoch_seconds"),
        forecast.get("loader_mapping_model_available_at_epoch_seconds"),
        absolute_cutoffs.get("model_frozen_at")) if type(value) in (int, float) and math.isfinite(value)]
    for window in (300, 900, 1800):
        common_forecast[f"loader_demand_total_{window}s"] = _sum_known(
            [demand_mass(prepared, node, 0., window) for node in sorted(prepared.loaders)])
    result = {}
    for candidate in candidates:
        move = candidate["action_type"] == "transfer"
        current = project_action(prepared, candidate, use_forecast=False)
        projected = project_action(prepared, candidate, use_forecast=True) if prepared.forecast is not None else None
        fields_current = {**common_current, "is_transfer": float(move),
            "departure_delay": current.get("departure_delay", 0.), "arrival_offset": current.get("arrival_offset", 0.),
            "static_travel_time": candidate.get("static_travel_time", 0.),
            "current_proxy_gain": current["proxy_gain"], "source_current_area_delta": current["source_area_delta"],
            "destination_current_area_delta": current["destination_area_delta"]}
        fields_forecast = {**common_forecast,
            "forecast_proxy_gain": None if projected is None else projected["proxy_gain"],
            "source_proxy_backlog_area_delta": None if projected is None else projected["source_area_delta"],
            "destination_proxy_backlog_area_delta": None if projected is None else projected["destination_area_delta"],
            "source_first_shortage_time_without_move": None if projected is None else _shortage(projected, "source_without_move"),
            "destination_first_shortage_time": None if projected is None else _shortage(projected, "destination_without_move")}
        for role in ("source", "destination"):
            state = prepared.nodes[candidate[role]] if move else None
            fields_current.update({f"{role}_stock": None if state is None else state["stock"],
                f"{role}_waiting": None if state is None else state["waiting"],
                f"{role}_inventory_known": float(state is not None and state["inventory_known"]),
                f"{role}_waiting_known": float(state is not None and state["waiting_known"]),
                f"{role}_is_loader": float(move and candidate[role] in prepared.loaders),
                f"{role}_message_age": None if state is None or state["inventory_as_of"] is None else prepared.now-state["inventory_as_of"]})
            arrival_nodes = prepared.audit["external_arrival_nodes"]
            fields_current[f"{role}_external_arrival_possible"] = (
                None if not move or arrival_nodes is None else float(candidate[role] in arrival_nodes))
            forecast_known = (move and prepared.forecast is not None and demand_mass(prepared,
                candidate[role], 0., min(prepared.horizon_seconds, prepared.forecast_edges[-1])) is not None)
            fields_forecast[f"{role}_coverage_mask"] = float(state is not None and state["inventory_known"]
                and state["waiting_known"] and forecast_known)
            fields_forecast[f"{role}_forecast_known"] = float(forecast_known)
            for window in (300, 900, 1800):
                fields_forecast[f"{role}_demand_{window}s"] = demand_mass(prepared, candidate[role], 0., window) if move else None
        arrival = current.get("arrival_offset", 0.)
        support_end = prepared.forecast_edges[-1] if prepared.forecast is not None else None
        fields_forecast.update({
            "destination_demand_before_arrival": demand_mass(prepared, candidate["destination"], 0., min(arrival, support_end)) if move and support_end is not None else None,
            "destination_demand_after_arrival_300s": demand_mass(prepared, candidate["destination"], min(arrival, support_end), min(arrival+300., support_end)) if move and support_end is not None else None,
            "horizon_exceeded": None if support_end is None else float(arrival+300. > support_end),
            "conditional_release_mass_used": math.fsum(state["conditional_mass"] for state in prepared.nodes.values())})
        fields_current["known_inbound_before_arrival"] = (math.fsum(mass for at, mass, kind in prepared.nodes[candidate["destination"]]["events"]
            if kind == "accepted_inbound" and at <= arrival) if move else 0.)
        coverage = "".join(str(int(fields_current[f"{role}_{kind}_known"]))
                           for role in ("source", "destination") for kind in ("inventory", "waiting"))
        support = ("transfer:"+("loader" if candidate["source"] in prepared.loaders else "return")
                   +":loader:coverage_"+coverage) if move else "noop:current_public"
        result[candidate["action_id"]] = {"features_current": fields_current, "features_forecast": fields_forecast,
            "action_support_key": support, "forecast_id": forecast_id,
            "mapping_id": forecast.get("airport_mapping_sha256"), "model_id": forecast.get("model_id", forecast.get("model_sha256")),
            "model_available_at": max(availability) if availability else None,
            "arrival_support_contract_sha256": prepared.audit["arrival_support_contract_sha256"],
            "action_class_does_not_imply_empirical_support": True}
    return result
