"""One-use, public inventory projection for joint tray/destination proposals.

This is a short-horizon fluid waiting proxy, not a simulator of future tray
cycles. A forecast arrival consumes an available tray once. No future job,
dispatch permission, or calibrated arrival guarantee is created here.
"""
from __future__ import annotations

from collections import defaultdict
import copy
from dataclasses import dataclass, field
import math

from .analytic_control import PublicTravel
from .foundation_airport_batch_patch import digest
from .foundation_airport_inventory_rule import inventory_view
from . import foundation_airport_learning_public as public

SCHEMA = "g31.foundation.airport_joint_inventory_projection.v1"
SUPPLY_MODES = ("committed_only", "conditional_next_release")
FORBIDDEN = {"future_jobs", "private_crosswalk", "global_result", "target_return", "reward"}


def require(value, reason):
    if not value:
        raise ValueError("airport_inventory_projection:" + reason)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "finite_number")
    return float(value)


@dataclass
class PreparedProjection:
    now: float
    owner: str
    observation_version: object
    public_state_digest: str
    horizon_seconds: float
    supply_mode: str
    nodes: dict
    supply_events: list
    actual_by_tray: dict
    forecast: dict | None
    forecast_edges: list
    forecast_curves: dict
    forecast_missing: dict
    forecast_origin: float | None
    loaders: set
    audit: dict
    baseline_cache: dict = field(default_factory=dict)
    mass_cache: dict = field(default_factory=dict)


def _empty(tray, at):
    return (tray.get("mode") == "empty" and tray.get("edge_to", -1) < 0
            and tray.get("reception_node", -1) < 0 and tray.get("available_at", at) <= at)


def prepare_inventory_projection(observation, *, forecast=None,
                                 supply_mode="committed_only", horizon_seconds=600.,
                                 prepared_current=None, arrival_support_contract=None,
                                 arrival_support_receipt=None):
    """Index one immutable observation; missing remote accounts stay missing.

    Native producer local-job enumeration supplies complete local waiting
    counts. A pure function cannot authenticate the provenance of that payload.
    Valid delivered planning captures additionally establish their stated peer
    scope. An ACK is supply evidence, never an actual-current empty tray.
    """
    require(supply_mode in SUPPLY_MODES, "supply_mode")
    require(not (FORBIDDEN & set(observation)), "private_or_label_input")
    now, owner, contracts, trays, jobs = public.validate_public(observation)
    arrival_support = None
    if arrival_support_contract is not None or arrival_support_receipt is not None:
        from .foundation_airport_arrival_support import validate_arrival_support
        arrival_support = set(validate_arrival_support(arrival_support_contract, arrival_support_receipt,
                                                       now=now, owner=owner))
    horizon = number(horizon_seconds)
    require(0 < horizon <= 1800., "short_horizon_at_most_1800")
    view = prepared_current.inventory if prepared_current is not None else inventory_view(observation)
    travel = prepared_current.travel if prepared_current is not None else PublicTravel(observation)
    if prepared_current is not None:
        require(prepared_current.observation is observation or prepared_current.observation == observation,
                "prepared_observation_scope")
    state_digest = prepared_current.public_state_digest if prepared_current is not None else digest(observation)
    node_records = {int(row[0]): row for row in observation["node_records"]}
    nodes = {}
    for node, contract in contracts.items():
        stock = view["nodes"][node]
        local = contract.get("resource_owner", contract.get("zone")) == owner
        explicit_rate = contract.get("loading_service_rate")
        rate = (number(explicit_rate) if explicit_rate is not None
                else 1. / max(.001, number(node_records[node][2])))
        require(rate > 0., "positive_public_service_rate")
        nodes[node] = {"stock": None, "inventory_known": stock["known"],
            "inventory_as_of": stock["as_of"], "waiting": 0. if local else None,
            "waiting_known": local, "waiting_as_of": now if local else None,
            "service_rate": rate,
            "service_model_kind": ("explicit_public_loading_service_rate" if explicit_rate is not None
                                   else "public_node_service_capacity_relaxation"),
            "events": [], "conditional_mass": 0., "local": local}
    physical = {identity: (tray, now, observation.get("version"), "local_sensor")
                for identity, tray in trays.items()}
    # inventory_view has already selected and checked the latest valid capture.
    captures = {row.get("payload_sha256"): row.get("capture", {})
                for row in observation.get("planning_snapshots", [])}
    selected_captures = {}
    for node, state in view["nodes"].items():
        if state["known"] and state["source"] == "delivered_planning_snapshot":
            selected_captures[state["payload_sha256"]] = captures[state["payload_sha256"]]
    for capture in selected_captures.values():
        at = capture["captured_at"]
        for node in capture["coverage"]["local_node_ids"]:
            nodes[node].update(waiting=0., waiting_known=True, waiting_as_of=at)
        for job in capture["jobs"]:
            if job.get("status") in ("waiting", "waiting_for_tray") and job["origin"] in nodes:
                node = job["origin"]
                if node in capture["coverage"]["local_node_ids"]:
                    nodes[node]["waiting"] += 1.
        for tray in capture["trays"]:
            old = physical.get(tray["tray_id"])
            if old is None or (old[3] != "local_sensor" and at > old[1]):
                physical[tray["tray_id"]] = (tray, at, capture["publication_sequence"], "delivered_capture")
    for group in observation.get("control_projection", {}).get("waiting_groups", []):
        node = group["origin"]
        at = number(group["demand_observed_at"])
        require(0 <= at <= now, "waiting_capture_cutoff")
        count = group.get("count")
        if count is not None:
            require(type(count) is int and count >= len(group.get("jobs", [])), "waiting_count")
            if nodes[node]["waiting_as_of"] is None or at >= nodes[node]["waiting_as_of"]:
                nodes[node].update(waiting=float(count), waiting_known=True, waiting_as_of=at)
    # Some legal payloads use full local jobs rather than the compact groups.
    if "control_projection" not in observation:
        for job in jobs.values():
            if job.get("status") in ("waiting", "waiting_for_tray") and nodes[job["origin"]]["local"]:
                nodes[job["origin"]]["waiting"] += 1.
    requests = observation["client_transfer_ledger"]
    active = {row["tray_id"] for row in requests if row["status"] not in public.TERMINAL}
    actual, events, audit_rows = {}, [], []
    raw_counts = defaultdict(int)
    for identity, (tray, at, version, kind) in physical.items():
        node = tray["node"]
        if _empty(tray, at) and nodes[node]["inventory_known"]:
            raw_counts[node] += 1
            # A newer destination capture dominates a stale sender ACK.
            already_at_destination = any(row["tray_id"] == identity and row["destination"] == node
                and at >= row["issued_at"] for row in requests if row["status"] in public.COMMITTED)
            if identity in active and not already_at_destination:
                continue
            actual[identity] = node
            events.append({"physical_tray_id": identity, "availability_kind": "actual_current",
                "location": node, "source_observation_version": version,
                "commitment_id_or_dependency": None, "event_time_estimate": now,
                "certainty_class": "observed_at_capture", "included_in_current_capture": True,
                "captured_at": at, "source_kind": kind})
    for node, state in nodes.items():
        reported = view["nodes"][node]["reported_actual_empty"]
        if state["inventory_known"] and raw_counts[node] == reported:
            state["stock"] = float(sum(n == node for n in actual.values()))
        else:
            state["inventory_known"] = False
            audit_rows.append({"node": node, "reason": "inventory_unknown_or_identity_count_mismatch"})
    committed_seen = set()
    for request in requests:
        identity, status = request["tray_id"], request["status"]
        if status not in public.COMMITTED and status != "received":
            continue  # pending is neither accepted nor predicted supply
        destination = request["destination"]
        capture_at = nodes[destination]["inventory_as_of"]
        received = request.get("received_at")
        included = identity in actual and actual[identity] == destination
        included |= (status == "received" and type(received) in (int, float) and received >= 0
                     and capture_at is not None and capture_at >= received)
        # A historical received request may remain in the ledger after this
        # physical tray has already loaded or returned somewhere else. Its
        # later visible state supersedes that receipt, even outside old dest.
        included |= (status == "received" and type(received) in (int, float) and received >= 0
                     and identity in physical and physical[identity][1] >= received)
        if included:
            audit_rows.append({"tray_id": identity, "request_id": request["request_id"],
                               "reason": "commitment_already_covered_by_capture"})
            continue
        if status == "received" and (type(received) not in (int, float) or received < 0):
            audit_rows.append({"tray_id": identity, "reason": "receipt_time_unknown_no_supply_credit"})
            continue
        require(identity not in committed_seen, "one_live_accepted_commitment_per_tray")
        committed_seen.add(identity)
        duration = travel.complete(request["source"], destination)
        if not math.isfinite(duration):
            audit_rows.append({"tray_id": identity, "reason": "accepted_eta_unreachable_unknown"})
            continue
        eta = (max(now, number(received)) if status == "received" else
               max(now, number(request.get("earliest_departure", now))) + duration)
        event = {"physical_tray_id": identity, "availability_kind": "accepted_inbound",
            "location": destination, "source_observation_version": observation.get("version"),
            "commitment_id_or_dependency": request["request_id"], "event_time_estimate": eta,
            "certainty_class": "delivered_ack_full_remaining_trip_estimate",
            "included_in_current_capture": False}
        events.append(event)
        nodes[destination]["events"].append((max(0., eta-now), 1., "accepted_inbound"))
    if supply_mode == "conditional_next_release":
        for identity, tray in trays.items():
            if identity in actual or identity in active or tray.get("mode") not in ("hold", "unloading"):
                continue
            job = jobs.get(tray.get("business_bag_id"))
            if tray["mode"] == "unloading" and job is None:
                continue
            eta = max(now, number(tray["available_at"]))
            if tray["mode"] == "unloading":
                hold = number(job["hold_seconds"])
                require(hold >= 0., "nonnegative_current_hold_duration")
                eta += hold
            node = tray["node"]  # actual current unloading location, never old origin
            events.append({"physical_tray_id": identity, "availability_kind": "conditional_next_release",
                "location": node, "source_observation_version": observation.get("version"),
                "commitment_id_or_dependency": str(tray.get("business_bag_id")),
                "event_time_estimate": eta, "certainty_class": "conditional_current_operation_duration",
                "included_in_current_capture": False})
            nodes[node]["events"].append((eta-now, 1., "conditional_next_release"))
            nodes[node]["conditional_mass"] += 1.
    curves, missing, edges, origin = {}, {}, [0., horizon], None
    if forecast is not None:
        require(not (FORBIDDEN & set(forecast)), "forecast_contains_outcomes")
        require(forecast.get("schema") == "g31.foundation.new_demand_forecast.v1"
                and forecast["owner_scope"] == owner, "forecast_owner")
        origin = number(forecast["forecast_origin"])
        require(origin <= now < number(forecast["remaining_support_until"]), "forecast_time_support")
        edges = [number(x) + origin-now for x in forecast["bin_edges_seconds"]]
        require(len(edges) > 1 and all(b > a for a, b in zip(edges, edges[1:])), "forecast_bins")
        for node in nodes:
            key = public.region(node)
            values = forecast["new_demand_mean_by_region"].get(key)
            mask = forecast["missing_mask_by_region"].get(key, True)
            if values is None:
                values, mask = [None] * (len(edges)-1), True
            require(len(values) == len(edges)-1, "forecast_length")
            mask = [mask] * len(values) if type(mask) is bool else list(mask)
            require(len(mask) == len(values) and all(type(x) is bool for x in mask), "forecast_missing_mask")
            for value, absent in zip(values, mask):
                if not absent:
                    require(number(value) >= 0., "nonnegative_demand")
            if arrival_support is not None and node not in arrival_support:
                require(all(absent or value == 0. for value, absent in zip(values, mask)),
                        "forecast_conflicts_with_public_arrival_support")
                # A declared static domain, not absent observations, establishes
                # this zero. Physical stock, waiting and accepted jobs keep all
                # their original masks and quantities.
                values, mask = [0.] * len(values), [False] * len(values)
            curves[node], missing[node] = list(values), mask
    return PreparedProjection(now, owner, observation.get("version"), state_digest, horizon,
        supply_mode, nodes, events, actual, copy.deepcopy(forecast), edges, curves, missing, origin,
        set(observation.get("static_role_contract", {}).get("loader_nodes", [])),
        {"schema": SCHEMA, "deduplication_and_unknown": audit_rows,
         "one_use_inventory_no_generated_return_cycles": True,
         "local_waiting_basis": "native_owner_released_job_enumeration_and_compact_counts",
         "remote_empty_or_waiting_unknown_not_imputed_as_zero": True,
         "arrival_support_contract_sha256": None if arrival_support_contract is None else arrival_support_contract["sha256"],
         "external_arrival_nodes": None if arrival_support is None else sorted(arrival_support),
         "structural_zero_scope": "new_external_business_only" if arrival_support is not None else None,
         "demand_within_bin": "uniform_continuous_mass", "native_execution_authority": False,
         "all_owner_incoming_complete": False, "arrival_times_are_not_upper_bounds": True})


def demand_mass(prepared, node, left, right):
    """Known forecast mass on an interval; None is genuinely unavailable."""
    if prepared.forecast is None:
        return None
    left, right = max(0., left), max(0., right)
    key = (node, left, right)
    if key in prepared.mass_cache:
        return prepared.mass_cache[key]
    if right <= left:
        return 0.
    if left < prepared.forecast_edges[0] or right > prepared.forecast_edges[-1]:
        return None
    total = 0.
    for a, b, value, absent in zip(prepared.forecast_edges, prepared.forecast_edges[1:],
                                  prepared.forecast_curves[node], prepared.forecast_missing[node]):
        overlap = max(0., min(right, b)-max(left, a))
        if overlap:
            if absent:
                prepared.mass_cache[key] = None
                return None
            total += value * overlap / (b-a)
    prepared.mass_cache[key] = total
    return total


def simulate_node(*, stock, waiting, supply_events, demand_edges, demand_means,
                  horizon_seconds, service_rate):
    """Exact piecewise-linear fluid queue; supplies occur at their precise ETA.

    Service consumes inventory irreversibly within this one-use projection.
    Event ordering cannot put a late supply before earlier within-bin demand.
    """
    require(stock >= 0 and waiting >= 0 and service_rate > 0, "nonnegative_physical_state")
    h = horizon_seconds
    arrivals = defaultdict(float)
    for at, amount in supply_events:
        require(at >= 0 and amount >= 0, "nonnegative_supply")
        if at <= h:
            arrivals[at] += amount
    cuts = sorted({0., h, *[x for x in demand_edges if 0 < x < h], *arrivals})
    inv, queue, area, served, first = float(stock), float(waiting), 0., 0., None
    minimum_inventory = inv
    if queue > 0:
        first = 0.
    for left, right in zip(cuts, cuts[1:]):
        inv += arrivals[left]
        rate = 0.
        for a, b, mass in zip(demand_edges, demand_edges[1:], demand_means):
            if a <= left < b:
                rate = mass / (b-a)
                break
        cursor = left
        while cursor < right - 1e-10:
            output = min(rate, service_rate) if queue <= 1e-10 else service_rate
            if inv <= 1e-10:
                output = 0.
            delta = right-cursor
            if output > 0:
                delta = min(delta, inv/output)
            slope = rate-output
            if queue > 1e-10 and slope < 0:
                delta = min(delta, queue / -slope)
            require(delta > 0, "projection_progress")
            if first is None and (queue > 1e-10 or slope > 1e-10):
                first = cursor
            area += queue*delta + .5*slope*delta*delta
            queue = max(0., queue+slope*delta)
            inv = max(0., inv-output*delta)
            minimum_inventory = min(minimum_inventory, inv)
            served += output*delta
            cursor += delta
    inv += arrivals[h]
    return {"backlog_area": max(0., area), "first_shortage_offset": first,
            "ending_inventory": inv, "ending_backlog": queue, "served_mass": served,
            "minimum_inventory": minimum_inventory, "service_model": "finite_rate_single_use_fluid"}


def _node_projection(prepared, node, *, use_forecast, stock_delta=0., added_event=None):
    key = (node, use_forecast, stock_delta, added_event)
    if key in prepared.baseline_cache:
        return prepared.baseline_cache[key]
    state = prepared.nodes[node]
    if not state["inventory_known"] or not state["waiting_known"]:
        return None
    h = prepared.horizon_seconds
    if use_forecast:
        h = min(h, prepared.forecast_edges[-1])
        if demand_mass(prepared, node, 0., h) is None:
            return None
        means, edges = prepared.forecast_curves[node], prepared.forecast_edges
    else:
        means, edges = [0.], [0., h]
    events = [(at, mass) for at, mass, _ in state["events"]]
    if added_event is not None:
        events.append(added_event)
    stock = state["stock"] + stock_delta
    require(stock >= 0, "candidate_cannot_make_negative_source_stock")
    result = simulate_node(stock=stock, waiting=state["waiting"], supply_events=events,
        demand_edges=edges, demand_means=means, horizon_seconds=h, service_rate=state["service_rate"])
    prepared.baseline_cache[key] = result
    return result


def _baseline(prepared, node, use_forecast):
    key = (node, use_forecast)
    if key not in prepared.baseline_cache:
        prepared.baseline_cache[key] = _node_projection(prepared, node, use_forecast=use_forecast)
    return prepared.baseline_cache[key]


def project_action(prepared, candidate, *, use_forecast=None):
    """Compare one real proposal with no-op, including its source opportunity cost."""
    use_forecast = prepared.forecast is not None if use_forecast is None else use_forecast
    require(not use_forecast or prepared.forecast is not None, "forecast_required")
    if candidate["action_type"] == "noop":
        return {"action_id": candidate["action_id"], "proxy_gain": 0.,
                "source_area_delta": 0., "destination_area_delta": 0., "known": True}
    require(candidate["action_type"] == "transfer", "one_transfer_or_noop")
    source, destination, tray = candidate["source"], candidate["destination"], candidate["tray_id"]
    require(source != destination and prepared.actual_by_tray.get(tray) == source,
            "candidate_actual_source_identity")
    departure = number(candidate["earliest_departure"])
    arrival = number(candidate.get("nominal_arrival_time", candidate.get("static_arrival_estimate")))
    require(prepared.now <= departure <= arrival, "candidate_exact_timing")
    offset = arrival-prepared.now
    before_source, before_destination = _baseline(prepared, source, use_forecast), _baseline(prepared, destination, use_forecast)
    # Submission reserves this exact tray immediately; no other predicted load
    # may consume it during the departure delay. Physical departure stays exact.
    after_source = _node_projection(prepared, source, use_forecast=use_forecast, stock_delta=-1.)
    after_destination = _node_projection(prepared, destination, use_forecast=use_forecast, added_event=(offset, 1.))
    source_delta = (None if before_source is None or after_source is None
                    else after_source["backlog_area"]-before_source["backlog_area"])
    destination_delta = (None if before_destination is None or after_destination is None
                         else after_destination["backlog_area"]-before_destination["backlog_area"])
    known = source_delta is not None and destination_delta is not None
    return {"action_id": candidate["action_id"], "proxy_gain": -(source_delta+destination_delta) if known else None,
        "source_area_delta": source_delta, "destination_area_delta": destination_delta, "known": known,
        "source_without_move": before_source, "source_with_move": after_source,
        "destination_without_move": before_destination, "destination_with_move": after_destination,
        "departure_delay": departure-prepared.now, "arrival_offset": offset,
        "source_reserved_at": prepared.now, "nominal_arrival_time": arrival,
        "eta_model_kind": candidate.get("eta_model_kind", "public_static_service_aware_estimate"),
        "proxy_horizon_seconds": prepared.horizon_seconds,
        "strict_nonharm_certified": False}
