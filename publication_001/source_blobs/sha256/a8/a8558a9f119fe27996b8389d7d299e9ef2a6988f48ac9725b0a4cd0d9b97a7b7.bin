"""Bounded repair of owned soft intents against newly observed occupancy.

The windows below are *minimum* committed occupancy, not an upper bound on
release. Unmodelled downstream blocking still requires native execution. This
module owns no physical state and grants no right to cancel hard commitments.
"""
from __future__ import annotations

import copy
import math
import time

from .analytic_control import PublicTravel, conditional_service_windows, release_forecasts
from .boundary_reference import ObligationWindow, capacity_violations
from .joint_window_repair import _footprint, build_domain, digest, proposal_order, submit_action


def local_inflight_minimum_windows(observation: dict) -> list[dict]:
    """Use only this owner's visible trays and deterministic entry receipts.

    An incoming node entitlement cannot be released before traversal arrival
    plus its service. It can be held LONGER. No remote occupancy is invented.
    """
    travel = PublicTravel(observation)
    windows = []
    for tray in observation["trays"]:
        u, v = int(tray.get("edge_from", -1)), int(tray.get("edge_to", -1))
        if v < 0 or u < 0 or "edge_exit_at" not in tray:
            continue
        arrival = float(tray["edge_exit_at"])
        if arrival < observation["now"]:
            continue
        proof = {"tray_id": tray["tray_id"], "traversal_id": tray["traversal_id"],
                 "source_owner": observation["owner_id"], "owner_version": observation["version"],
                 "edge_from": u, "edge_to": v, "edge_exit_at": arrival,
                 "scope": "minimum_occupancy_only; downstream_blocking_can_extend"}
        for resource, end in ((f"edge:{u}:{v}", arrival),
                              (f"node:{v}", arrival + travel.service[v])):
            if end > observation["now"]:
                windows.append({"task": "committed:" + tray["tray_id"], "resource": resource,
                                "start": observation["now"], "end": end, "amount": 1,
                                "proof": proof})
    return windows


def publish_observed_loaded_dependencies(session, owners: list[str], delay: float = .02) -> list[dict]:
    """Publish one actual local loaded next hop to its lawful resource owner.

    Shortest path is a conditional proposal. The native endpoint rejects an
    in-flight tray and does not permit forwarding its occupancy to any owner.
    """
    publications = []
    for owner in owners:
        observed = session.observe(owner)
        travel = PublicTravel(observed)
        jobs = {j["business_bag_id"]: j for j in observed["jobs"]}
        node_owner = {n["node"]: n.get("resource_owner", n["zone"]) for n in observed["node_contracts"]}
        for tray in observed["trays"]:
            if tray["mode"] not in ("loading", "loaded") or tray.get("edge_to", -1) >= 0:
                continue
            job = jobs.get(tray["business_bag_id"])
            if job is None:
                continue
            destination = job["storage_node"] if job.get("storage_node", -1) >= 0 and job.get("storage_released_at", -1) < 0 else job["destination"]
            path = travel.path(tray["node"], destination)[1]
            if len(path) < 2:
                continue
            nxt = path[1]
            reply = session.publish_service_forecast(owner, node_owner[nxt], tray["tray_id"], nxt, delay)
            publications.append({"source_owner": owner, "target_owner": node_owner[nxt],
                                 "tray_id": tray["tray_id"], "next": nxt, "observed_at": observed["now"],
                                 "delay": delay, "reply": reply,
                                 "information_scope": "actual_local_loaded_service; conditional_next_hop"})
    return publications


def _overlaps(footprint, windows):
    return [(a, b) for a in footprint for b in windows
            if a["resource"] == b["resource"] and a["start"] < b["end"] and b["start"] < a["end"]]


def retime_action_after_minimum_occupancy(action, observation, windows, message_delay=.1):
    """Right shift past the union of conditional and committed intervals.

    Two independent conditional predictions can overlap. That means their
    point estimates are inconsistent, not that a legal native continuation is
    impossible. Candidate movements conservatively avoid BOTH estimates;
    external prediction conflicts remain explicit and are not certified away.
    """
    revised = copy.deepcopy(action)
    travel = PublicTravel(observation)
    frozen = [{"task": "service:" + m["message_id"], "resource": f"node:{m['next']}",
               "start": m["entry_estimate"], "end": m["release_estimate"], "amount": 1}
              for m in conditional_service_windows(observation)]
    avoided = frozen + windows
    for candidate in revised["candidates"]:
        request = candidate["request"]
        departure = max(observation["now"] + message_delay, request["earliest_departure"])
        for _ in range(len(avoided) + 1):
            footprint = _footprint(observation, candidate["path"], departure,
                                   candidate["candidate_id"], travel)
            conflicts = _overlaps(footprint, avoided)
            if not conflicts:
                break
            departure = math.nextafter(max(b["end"] - (a["start"] - departure)
                                           for a, b in conflicts), math.inf)
        else:
            return None
        suffix = ":observed-occupancy:" + digest({"read": digest(observation), "departure": departure})[:20]
        candidate["candidate_id"] += suffix
        request["request_id"] += suffix
        request["earliest_departure"] = departure
        request["expiry"] = departure + travel.complete(request["source"], request["destination"]) + 60
        candidate["predicted_arrival"] = departure + travel.complete(request["source"], request["destination"])
        candidate["conditional_footprint"] = _footprint(observation, candidate["path"], departure,
                                                        candidate["candidate_id"], travel)
        candidate["read_set"].append({"kind": "observed_inflight_minimum_occupancy", "windows": windows})
    revised["action_id"] = "|".join(c["candidate_id"] for c in revised["candidates"]) or "WAIT"
    revised["predicted_arrival_sum"] = sum(c["predicted_arrival"] for c in revised["candidates"])
    capacities = {f"node:{n['node']}": n["capacity"] for n in observation["node_contracts"]}
    capacities.update({f"edge:{e['from']}:{e['to']}": e["capacity"] for e in observation["edge_contracts"]})
    capacities.update({f"headway:{e['from']}:{e['to']}": 1 for e in observation["edge_contracts"]})
    # Test each hard lower bound against proposals separately. Adding both a
    # service prediction and the same tray's actual occupancy would double-count
    # one physical tray. This still is not a full hard constraint model.
    proposed = [w for c in revised["candidates"] for w in c["conditional_footprint"]]
    revised["conditional_conflicts"] = capacity_violations([ObligationWindow(**w) for w in proposed], capacities)
    revised["conditional_forecast_conflicts"] = _overlaps(proposed, frozen)
    revised["inconsistent_fixed_predictions"] = capacity_violations([ObligationWindow(**w) for w in frozen], capacities)
    revised["certification"] = "conditional_proposal_avoids_each_external_window; external_predictions_not_jointly_certified"
    revised["observed_minimum_conflicts"] = [pair for c in revised["candidates"]
                                              for pair in _overlaps(c["conditional_footprint"], windows)]
    return revised


def repair_observed_occupancy(session, owner: str, owned_bundle_ids: list[str], *, max_bundle=2,
                             trigger="occupancy") -> dict:
    """Revalidate a bounded soft bundle while preserving its assignments.

    Trigger is an actually observed committed occupancy conflicting with the
    incumbent schedule. No owner mismatch, active hard grant, or budget failure
    is silently converted to feasible. Native cancel/submit remain non-atomic.
    """
    started = time.perf_counter()
    if trigger not in ("occupancy", "source"):
        raise ValueError("dependency_repair:unknown_trigger")
    observed = session.observe(owner)
    active = [r for r in observed["transfers"] if r["request_id"] in owned_bundle_ids
              and r["status"] in ("pending", "undelivered")]
    hard = [r for r in observed["transfers"] if r["request_id"] in owned_bundle_ids
            and r["status"] not in ("pending", "undelivered", "cancelled", "rejected", "expired", "received")]
    windows = local_inflight_minimum_windows(observed) if trigger == "occupancy" else []
    travel = PublicTravel(observed)
    forecasts = {f.tray_id: f for f in release_forecasts(observed)}
    obsolete = {r["request_id"] for r in active if r["tray_id"] not in forecasts
                or forecasts[r["tray_id"]].node != r["source"]} if trigger == "source" else set()
    changed = []
    for request in active:
        path = travel.path(request["source"], request["destination"])[1]
        footprint = _footprint(observed, path, max(observed["now"] + .1, request["earliest_departure"]),
                               request["request_id"], travel)
        conflicts = _overlaps(footprint, windows)
        if conflicts or request["request_id"] in obsolete:
            changed.append({"request_id": request["request_id"], "conflicts": conflicts,
                            "source_changed": request["request_id"] in obsolete})
    result = {"status": "no_observed_" + trigger + "_change", "observation": observed,
              "windows": windows, "changed_dependencies": changed, "frozen_hard_requests": hard,
              "cancellations": [], "submissions": [], "atomic": False,
              "normal_service_guarantee": False, "global_optimality": "unknown"}
    if len(active) > max_bundle:
        result["status"] = "unknown_domain_budget"
        return result
    if not changed:
        return result
    retained = {(r["tray_id"], r["source"], r["destination"]) for r in active if r["request_id"] not in obsolete}
    # This finite experiment closes at most two owned soft requests. It does
    # not expand across other owners or cancel already committed exports.
    for request in active:
        reply = session.cancel_transfer_intent(request["request_id"], owner)
        result["cancellations"].append({"request_id": request["request_id"], "reply": reply})
        if reply["status"] != "cancelled":
            result["status"] = "unknown_partial_repair"
            return result
    fresh = session.observe(owner)
    domain = build_domain(fresh)
    if domain["status"] != "complete_finite_public_domain":
        result["status"] = "unknown_partial_repair"
        result["reason"] = domain["status"]
        return result
    options = []
    for action in domain["actions"]:
        if {(c["request"]["tray_id"], c["request"]["source"], c["request"]["destination"])
            for c in action["candidates"]} != retained:
            continue
        revised = retime_action_after_minimum_occupancy(action, fresh, windows)
        if revised and not revised["conditional_conflicts"] and not revised["conditional_forecast_conflicts"] and not revised["observed_minimum_conflicts"]:
            options.append(revised)
    result["candidate_count"] = len(options)
    if not options:
        result["status"] = "unknown_partial_repair"
        result["reason"] = "no_conditional_retiming; not_native_infeasibility"
        return result
    chosen = min(options, key=proposal_order)
    reply = submit_action(session, chosen, fresh)
    result.update({"status": "repair_submitted" if reply["status"] == "submitted" else "unknown_partial_repair",
                   "selected_action": chosen, "submissions": reply["submissions"], "fresh_observation": fresh,
                   "compute_ms": 1000 * (time.perf_counter() - started)})
    return result
