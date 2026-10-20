"""Frozen C10 current-only marginal inventory rule on the shared two actions.

Forecasts, conditional releases, and ACK-bound inbound estimates are planning
quantities, never actual inventory or native admission. The one-use inventory
approximation does not simulate future routing or invent later tote cycles.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import copy
import hashlib
import json
import math
from pathlib import Path

from .analytic_control import PublicTravel, public_transfer_scope
from . import foundation_airport_learning_public as public
from .foundation_airport_batch_patch import digest, actual_uncommitted, mandatory, SCHEMA as PATCH_SCHEMA
from .foundation_airport_pair_ranker import _forecast

SCHEMA = "g31.foundation.airport_C10_strong_rule.v1"
WINDOWS = (300., 900., 1800.)
PARAMETERS = {
    "windows_seconds": list(WINDOWS), "window_weights": [1./3.] * 3,
    "empty_tray_unavailable_second_cost": 1.,
    "visible_resource_pressure_second_cost": 1.,
    "forecast_weight": 1., "observed_waiting_weight": 1.,
    "conditional_supply_weight": 1.,
    "positive_advantage_required": 0., "tie_break": "a_ref",
}
FORBIDDEN = frozenset(("target_return", "paired_advantage_bag_seconds", "actual_execution",
    "transition", "candidate_labels", "future_jobs", "private_crosswalk", "global_result",
    "reward", "outcome", "conditional_rollout"))


def require(ok, reason):
    if not ok:
        raise ValueError("airport_strong_rule:" + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "finite_number")
    return float(value)


def contract():
    return {
        "schema": SCHEMA, "parameters": copy.deepcopy(PARAMETERS),
        "information": "exact same actual current forecast_evidence as C11",
        "candidate_contract": "same plan-independent a_ref versus one patch; other baseline allocations retained",
        "objective": "mean over 300/900/1800 of integral positive(visible_waiting + cumulative_B1_mean - planning_available_trays), plus candidate tray-unavailable seconds and observed path resource pressure seconds",
        "action_effect": "transfer removes source tray at current commitment; adds destination tray only at earliest_departure plus public static travel; hold keeps it at source",
        "existing_commitment_eta": "remaining time conservatively starts a full public trip at max(now, earliest_departure), since original physical progress is not attested by an ACK-only ledger; unreachable commitments are retained as unknown without predicted supply",
        "resource_proxy": "candidate unavailable seconds capped at 1800, plus observed node occupancy/capacity times service and visible edge occupancy/capacity times travel; absent capacity or pressure is explicitly unknown",
        "supply_terms": ["observed uncommitted empty trays",
            "conditional current local unloading/hold releases",
            "own immutable request payloads with actually delivered committed ACK",
            "same retained uncommitted baseline batch allocations"],
        "missing_scope": "unknown accounts stay flagged; objective is an observed-account conditional proxy, not total actual deficit; no private stock or future-arrival oracle",
        "strong_rule_basis": "existing analytic FIFO/min-stock matching and service-aware notified-fault paths, augmented by source/destination B1 demand and commitment-aware marginal cost",
        "parameters_fit_or_selected_from_targets": False,
        "calibration": "fixed engineering units before test; no outcome-based tuning",
        "native_execution_authority": False, "strict_nonharm_certified": False,
        "limitations": ["finite one-use empty-inventory approximation",
            "conditional supplies and static arrival estimates may fail or be delayed",
            "remote account and occupancy coverage may be incomplete",
            "shared-resource per-job protection remains the external native/guard responsibility"],
    }


def _curve(forecast, node):
    key = public.region(node)
    means = forecast["new_demand_mean_by_region"].get(key)
    missing = forecast["missing_mask_by_region"].get(key, True)
    edges = [number(v) for v in forecast["bin_edges_seconds"]]
    require(edges[0] == 0. and edges[-1] >= WINDOWS[-1]
            and all(b > a for a, b in zip(edges, edges[1:])), "forecast_grid_1800")
    if means is None or missing is True or isinstance(missing, list) and any(missing):
        return edges, None
    require(len(means) == len(edges)-1, "forecast_bin_count")
    means = [number(v) for v in means]
    require(all(v >= 0. for v in means), "nonnegative_forecast")
    return edges, means


def _cumulative(edges, means, at):
    if means is None:
        return 0.  # No *known predicted contribution*; missing remains explicit.
    return math.fsum(mass * max(0., min(right, at)-left)/(right-left)
        for left, right, mass in zip(edges[:-1], edges[1:], means, strict=True))


def _positive_linear_integral(left, right, duration):
    if left >= 0. and right >= 0.:
        return .5*(left+right)*duration
    if left <= 0. and right <= 0.:
        return 0.
    positive = max(left, right)
    return .5*positive*duration*positive/abs(right-left)


def _node_cost(waiting, free, supply_events, edges, means, horizon, cumulative_cache=None):
    boundaries = sorted({0., horizon, *[v for v in edges if 0 < v < horizon],
                         *[t for t, _ in supply_events if 0 < t < horizon]})
    total = 0.
    for left, right in zip(boundaries, boundaries[1:]):
        supply = free + sum(count for t, count in supply_events if t <= left)
        def cumulative(at):
            if cumulative_cache is None:
                return _cumulative(edges, means, at)
            if at not in cumulative_cache:
                cumulative_cache[at] = _cumulative(edges, means, at)
            return cumulative_cache[at]
        a = waiting + cumulative(left) - supply
        b = waiting + cumulative(right) - supply
        total += _positive_linear_integral(a, b, right-left)
    return total


def _eta(intent, now, travel):
    source, destination = intent["source"], intent["destination"]
    duration = travel.complete(source, destination)
    require(math.isfinite(duration) and duration >= 0., "reachable_public_path")
    return max(0., number(intent["earliest_departure"])-now) + duration


def _selected_allocation(row, target, supply, observation, nodes, now):
    """Read-only equivalent of single-tray patch admission, without batch copies."""
    action = row["action"]
    require(action.get("schema") == PATCH_SCHEMA and all(action[key] == row["opportunity"][key]
        for key in ("public_state_digest", "baseline_batch_digest", "immutable_request_prefix_digest")),
        "action_current_binding")
    old = [item for item in row["baseline_decision"]["intents"] if item["tray_id"] == target]
    require(len(old) <= 1, "one_selected_tray_allocation")
    if action["kind"] == "a_ref":
        return old[0] if old else None
    require(action["kind"] in ("add_optional", "replace_optional", "hold_optional")
            and action["tray_id"] == target, "single_selected_patch_kind")
    require((not old if action["kind"] == "add_optional" else bool(old) and not mandatory(old[0])),
            "cannot_patch_mandatory_or_missing_allocation")
    if action["kind"] == "hold_optional":
        return None
    intent = action["intent"]
    require(intent["tray_id"] == target and intent["source"] == supply["node"]
            and intent["owner_id"] == observation["owner_id"]
            and intent["forecast_ledger"] == "actual_available"
            and intent["forecast_dependency"] == supply["dependency"], "replacement_source_binding")
    destination = intent["destination"]
    require(destination in observation.get("static_role_contract", {}).get("loader_nodes", [])
            and destination in nodes and nodes[destination].get("allow_receive", True),
            "replacement_static_loader_receiver")
    scope = public_transfer_scope(observation, intent["source"], destination,
                                  actual_available=True, contracts=nodes)
    require(scope is not None and intent.get("transfer_scope", "cross_zone_transfer") == scope,
            "replacement_scope_binding")
    for key in ("issued_at", "message_delay", "earliest_departure", "expiry"):
        number(intent[key])
    require(intent["issued_at"] == now and intent["message_delay"] >= 0
            and intent["earliest_departure"] >= now + intent["message_delay"]
            and intent["expiry"] > intent["earliest_departure"], "replacement_current_timing")
    require(not old or intent["destination"] != old[0]["destination"]
            or intent["earliest_departure"] != old[0]["earliest_departure"], "patch_must_change_action")
    return intent


def _prepare(reference, patch):
    for row in (reference, patch):
        require(row.get("schema") == "g31.foundation.airport_prospective_control.v1"
                and not (FORBIDDEN & set(row)), "current_candidate_rows_only_no_targets")
        require(row.get("information_variant") in ("C10", "C11"), "same_plan_information_variant")
    require(reference["branch"] == "a_ref" and patch["branch"] == "a_patch"
            and reference["observation"] == patch["observation"]
            and reference["parent"] == patch["parent"]
            and reference["information_variant"] == patch["information_variant"]
            and reference["opportunity"] == patch["opportunity"]
            and reference["baseline_decision"] == patch["baseline_decision"]
            and reference["forecast_evidence"] == patch["forecast_evidence"], "same_current_batch_and_forecast")
    observation = reference["observation"]
    validated = public.validate_public(observation)
    now, owner, nodes, trays, _ = validated
    public_digest = digest(observation)
    prefix = {key: observation.get(key, []) for key in ("transfers", "client_transfer_ledger",
        "delivered_messages", "delivered_transfer_acks", "delivered_command_acks")}
    require(reference["opportunity"]["public_state_digest"] == public_digest
            and reference["opportunity"]["baseline_batch_digest"] == digest(reference["baseline_decision"]["intents"])
            and reference["opportunity"]["immutable_request_prefix_digest"] == digest(prefix)
            and reference["opportunity"]["catalog_uses_future_plan"] is False, "public_opportunity_binding")
    forecast = _forecast(reference)
    source, target_tray = reference["semantic_action"]["source"], reference["semantic_action"]["tray_id"]
    require(patch["semantic_action"]["source"] == source and patch["semantic_action"]["tray_id"] == target_tray,
            "same_intervention_tray_and_source")
    available = {row["tray_id"]: row for row in actual_uncommitted(observation, reference["baseline_decision"])}
    require(target_tray in available, "actual_uncommitted_candidate")
    for row in (reference, patch):
        require(row["action"] in row["opportunity"]["candidates"]
                and (row["action"]["kind"] == "a_ref") == (row["branch"] == "a_ref"),
                "catalog_action_binding")
        intent = _selected_allocation(row, target_tray, available[target_tray], observation, nodes, now)
        expected = {"tray_id": target_tray, "source": source,
            "kind": "transfer" if intent else "hold_optional",
            "destination": intent["destination"] if intent else None,
            "earliest_departure": intent["earliest_departure"] if intent else None,
            "transfer_scope": intent.get("transfer_scope", "cross_zone_transfer") if intent else None}
        require(row["semantic_action"] == expected
                and trays[target_tray]["node"] == source, "semantic_action_exact_patch_binding")
    accounts, account_audit = public._adapt_accounts(observation, validated)
    free_by_tray = {row["tray_id"]: int(row["region"].removeprefix("airport_node_"))
                   for row in accounts["current_free_trays"]}
    require(target_tray in free_by_tray, "candidate_current_free_sensor_agreement")
    free = Counter(free_by_tray.values())
    releases = {row["tray_id"]: (int(row["region"].removeprefix("airport_node_")),
                                max(0., row["available_at"]-now))
                for row in accounts["loaded_release_forecast"]}
    travel = PublicTravel(observation)
    supplies, conditional = defaultdict(list), []
    # A pending/unacknowledged request is a claim, not destination supply.
    seen = set()
    for request in observation["client_transfer_ledger"]:
        if request["status"] not in public.COMMITTED:
            continue
        tray = request["tray_id"]
        require(tray not in seen, "one_committed_request_per_tray")
        seen.add(tray)
        if not math.isfinite(travel.complete(request["source"], request["destination"])):
            conditional.append({"kind": "delivered_ACK_committed_unreachable_unknown",
                "tray_id": tray, "request_id": request["request_id"],
                "destination": request["destination"], "eta_offset": None, "supply_credit": 0.})
            continue
        eta = _eta(request, now, travel)
        supplies[request["destination"]].append((eta, 1.))
        conditional.append({"kind": "delivered_ACK_committed_inbound", "tray_id": tray,
                            "request_id": request["request_id"], "eta_offset": eta,
                            "destination": request["destination"]})
    for intent in reference["baseline_decision"]["intents"]:
        tray = intent["tray_id"]
        if tray == target_tray:
            continue
        require(tray not in seen, "retained_batch_not_already_committed")
        seen.add(tray)
        if tray in free_by_tray:
            free[free_by_tray[tray]] -= 1
        releases.pop(tray, None)
        eta = _eta(intent, now, travel)
        supplies[intent["destination"]].append((eta, 1.))
        conditional.append({"kind": "retained_baseline_allocation", "tray_id": tray,
                            "destination": intent["destination"], "eta_offset": eta})
    for tray, (node, eta) in releases.items():
        supplies[node].append((eta, 1.))
        conditional.append({"kind": "current_local_release", "tray_id": tray,
                            "destination": node, "eta_offset": eta})
    groups = {group["origin"]: group for group in observation["control_projection"]["waiting_groups"]}
    waiting = {node: (number(group["count"]) if group.get("count") is not None else len(group["jobs"]))
               for node, group in groups.items()}
    affected = {source, *[row["semantic_action"]["destination"] for row in (reference, patch)
                          if row["semantic_action"]["kind"] == "transfer"]}
    curves, coverage = {}, {}
    for node in affected:
        curves[node] = _curve(forecast, node)
        coverage[node] = {
            "forecast_missing": curves[node][1] is None,
            "observed_free_complete": accounts["coverage_by_account_region"]["current_free_trays"][public.region(node)]["complete"],
            "waiting_group_present": node in groups,
            "waiting_exact_captured_count": node in groups and groups[node].get("count") is not None,
            "waiting_complete_current_region": False,
            "unobserved_inventory_imputed_as_actual_zero": False,
        }
    edge_capacity = {(int(e["from"]), int(e["to"])): number(e["capacity"])
                     for e in observation.get("edge_contracts", [])}
    return now, nodes, trays, travel, free, supplies, waiting, curves, coverage, conditional, account_audit, edge_capacity, public_digest


def _score(action, prepared):
    now, nodes, trays, travel, free, supplies, waiting, curves, _, _, _, edge_capacity, _ = prepared
    free, supplies = free.copy(), copy.deepcopy(supplies)
    source, destination = action["source"], action.get("destination")
    require(action["kind"] in ("hold_optional", "transfer"), "semantic_action_kind")
    moving = action["kind"] == "transfer"
    eta = pressure = 0.
    unknown_pressure, unknown_edges = [], []
    if moving:
        require(source != destination, "nonzero_hop")
        eta = _eta(action, now, travel)
        free[source] -= 1
        require(free[source] >= 0, "cannot_consume_unobserved_source_inventory")
        supplies[destination].append((eta, 1.))
        path = travel.path(source, destination)[1]
        edge_occupancy = Counter((t.get("edge_from", -1), t.get("edge_to", -1))
                                 for t in trays.values() if t.get("edge_to", -1) >= 0)
        # Only locally visible occupancy adds a cost; missing remote pressure
        # remains recorded as unknown, never a declaration of a free resource.
        for node in path:
            occupancy = nodes[node].get("occupancy")
            capacity = nodes[node].get("capacity")
            if occupancy is None or capacity is None or number(capacity) <= 0:
                unknown_pressure.append(node)
            else:
                require(number(occupancy) >= 0, "nonnegative_visible_occupancy")
                pressure += travel.service[node] * number(occupancy)/number(capacity)
        # Visible in-flight physical trays penalize shared edge use even where
        # a remote node's occupancy sensor is absent.
        for edge in zip(path, path[1:]):
            capacity = edge_capacity.get(edge)
            if capacity is None or capacity <= 0:
                unknown_edges.append(list(edge))
            else:
                pressure += travel.edge_time[edge] * edge_occupancy[edge]/capacity
    elif destination not in (None, source):
        raise ValueError("airport_strong_rule:hold_must_stay_at_source")
    windows = {}
    by_node = {}
    for node, (edges, means) in curves.items():
        cache = {}
        by_node[node] = {str(int(h)): _node_cost(waiting.get(node, 0.), free[node], supplies[node], edges, means, h, cache)
                         for h in WINDOWS}
    for h in WINDOWS:
        windows[str(int(h))] = math.fsum(row[str(int(h))] for row in by_node.values())
    shortage = math.fsum(weight*windows[str(int(h))] for h, weight in zip(WINDOWS, PARAMETERS["window_weights"]))
    resource = min(eta, WINDOWS[-1]) * PARAMETERS["empty_tray_unavailable_second_cost"] + pressure * PARAMETERS["visible_resource_pressure_second_cost"]
    return {"cost": shortage + resource, "visible_account_shortage_area": shortage,
            "shortage_by_horizon": windows, "shortage_by_node": by_node,
            "candidate_arrival_offset": eta, "resource_occupation_proxy": resource,
            "visible_path_pressure_seconds": pressure, "unknown_pressure_nodes": unknown_pressure,
            "unknown_edge_capacity": unknown_edges}


def explain_pair(reference, patch, *, forecast_weight=1.):
    """Return auditable costs; positive advantage selects exactly one patch."""
    prepared = _prepare(reference, patch)
    require(forecast_weight in (0., 1.), "preregistered_forecast_weight")
    if forecast_weight != 1.:
        values = list(prepared)
        values[7] = {node: (edges, None if means is None else
                           [forecast_weight * value for value in means])
                     for node, (edges, means) in prepared[7].items()}
        prepared = tuple(values)
    ref, candidate = _score(reference["semantic_action"], prepared), _score(patch["semantic_action"], prepared)
    advantage = ref["cost"] - candidate["cost"]
    require(math.isfinite(advantage), "finite_pair_advantage")
    return {"schema": SCHEMA, "rule_contract_sha256": digest(contract()),
        "registered_forecast_weight": forecast_weight,
        "public_state_digest": prepared[12],
        "forecast_sha256": reference["forecast_evidence"]["forecast_sha256"],
        "reference": ref, "patch": candidate, "predicted_patch_advantage": advantage,
        "selected_branch": "a_patch" if advantage > 0. else "a_ref",
        "account_coverage": prepared[8], "conditional_supply_events": prepared[9],
        "current_account_audit": prepared[10], "native_execution_authority": False,
        "strict_nonharm_certified": False, "outcome_labels_read": False}


def score_pair(reference, patch):
    """Drop-in selector for ProspectivePlanner(information_variant='C10')."""
    return explain_pair(reference, patch)["predicted_patch_advantage"]


def validate_rule_freeze(binding):
    """Validate a {path, sha256} freeze once, before entering controller callbacks."""
    path = Path(binding["path"])
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == binding["sha256"], "rule_freeze_file_sha256")
    frozen = json.loads(raw)
    require(frozen.get("schema") == "g31.foundation.airport_C10_rule_freeze.v1"
            and frozen["rule_contract"] == contract(), "frozen_rule_contract")
    require(frozen["scorer_source_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "frozen_scorer_source")
    require(frozen["outcome_based_parameter_selection"] is False
            and frozen["heldout_test_outcomes_read"] is False, "frozen_before_test_no_target_selection")
    return frozen


def prepare_scorer(rule_freeze):
    """Once-validated finite selector compatible with ProspectivePlanner."""
    validate_rule_freeze(rule_freeze)
    return score_pair
