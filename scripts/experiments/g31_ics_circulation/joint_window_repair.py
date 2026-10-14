"""Finite joint return/receiving *proposal* solver on lawful owner projections.

This is a concrete supporting P5 candidate, not a new safety authority. It adds
joint matching/conditional occupancy to the existing independent assignment.
The interval model is deliberately labelled conditional: remote receiving,
future source queues, S4 path choice and forecast error still require native
execution. No atomic multi-owner commit or global no-delay guarantee is claimed.
"""
from __future__ import annotations

import copy
import hashlib
import itertools
import json
import math
import time
from typing import Any

from .analytic_control import (PublicTravel, ReleaseForecast, conditional_service_windows,
                               departure_avoiding_published_windows, transfer_candidates)
from .boundary_reference import ObligationWindow, capacity_violations


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def proposal_order(action: dict) -> tuple:
    """Policy tie-break uses physical numbers; opaque ID encoding is irrelevant."""
    physical = tuple(sorted((c["supply"], c["demand"], c["request"]["earliest_departure"])
                            for c in action["candidates"]))
    return -action["served_count"], action["predicted_arrival_sum"], physical


def _footprint(observation: dict, path: list[int], departure: float, task: str,
               travel: PublicTravel) -> list[dict]:
    """JIT incoming capacity spans edge entry through downstream departure.

    This is NOT just travel arrival-to-service-completion occupancy: a 5 km
    inbound edge holds its incoming-node entitlement while the tray is in
    transit. Terminal remote leases are not modelled by a fake finite window;
    their unknown actual duration is stated separately and checked natively.
    """
    rows = []
    headways = {(int(r["from"]), int(r["to"])): float(r.get("entry_headway", 0))
                for r in observation["edge_contracts"]}
    elapsed = departure
    for index, (u, v) in enumerate(zip(path, path[1:])):
        entry = elapsed + travel.service[u]
        arrival = entry + travel.edge_time[u, v]
        rows.append({"task": task, "resource": f"edge:{u}:{v}", "start": entry,
                     "end": arrival, "amount": 1})
        if headways[u, v] > 0:
            rows.append({"task": task, "resource": f"headway:{u}:{v}", "start": entry,
                         "end": entry + headways[u, v], "amount": 1})
        if index + 1 < len(path) - 1:
            rows.append({"task": task, "resource": f"node:{v}", "start": entry,
                         "end": arrival + travel.service[v], "amount": 1})
        elapsed = arrival
    return rows


def build_domain(observation: dict, *, message_delay: float = .1,
                 max_supplies: int = 2, max_actions: int = 256) -> dict:
    """Predeclare all partial injective matchings and three public timing choices.

    The timing grid is: point ETA, published-window repair, and that repair
    plus the longest incoming occupancy in the path. This is a bounded domain,
    never an exhaustive continuous-time transport domain. No native fork or
    hidden future is used to create it. Source protection is inherited from
    the common analytic supply eligibility before this joint search.
    """
    if not math.isfinite(message_delay) or message_delay < 0:
        raise ValueError("joint_window:invalid_delay")
    started = time.perf_counter()
    base = transfer_candidates(observation, predictive=True, message_delay=message_delay,
                               respect_service_forecasts=True, request_prefix="joint-base")
    if len(base["supplies"]) > max_supplies:
        return {"status": "unknown_domain_budget", "actions": [], "base": base}
    travel = PublicTravel(observation)
    capacities = {f"node:{r['node']}": r["capacity"] for r in observation["node_contracts"]}
    capacities.update({f"edge:{r['from']}:{r['to']}": r["capacity"]
                       for r in observation["edge_contracts"]})
    capacities.update({f"headway:{r['from']}:{r['to']}": 1 for r in observation["edge_contracts"]})
    frozen = [{"task": "service:" + m["message_id"], "resource": f"node:{m['next']}",
               "start": m["entry_estimate"], "end": m["release_estimate"], "amount": 1}
              for m in conditional_service_windows(observation)]
    candidates = []
    by_supply: dict[int, list[dict]] = {i: [] for i in range(len(base["supplies"]))}
    for pair in base["pool"]:
        supply = ReleaseForecast(**base["supplies"][pair["supply"]])
        job = base["demands"][pair["demand"]]
        destination = int(job["origin"])
        path = pair["path"]
        ready = max(observation["now"] + message_delay, supply.estimate)
        window = departure_avoiding_published_windows(observation, supply, destination, travel, message_delay)
        shifted = max(ready, window["earliest_departure"])
        incoming = max((travel.edge_time[u, v] + travel.service[v]
                        for u, v in zip(path[:-2], path[1:-1])), default=.001)
        # Outward rounding creates a legal tiny gap instead of declaring two
        # mathematically touching long intervals conflicting at a 1-ULP overlap.
        # Capacity checking itself remains exact; no conflict tolerance is added.
        after_incoming = math.nextafter(shifted + incoming, math.inf)
        for departure in sorted({ready, shifted, after_incoming}):
            cid = f"s{pair['supply']}:d{pair['demand']}:t{departure.hex()}"
            request = {"request_id": "live:joint:" + cid, "tray_id": supply.tray_id,
                       "source": supply.node, "destination": destination,
                       "issued_at": observation["now"], "message_delay": message_delay,
                       "earliest_departure": departure,
                       "expiry": departure + travel.complete(supply.node, destination) + 60,
                       "owner_id": observation["owner_id"], "expected_version": observation["version"]}
            candidate = {"candidate_id": cid, "supply": pair["supply"], "demand": pair["demand"],
                         "request": request, "path": path,
                         "predicted_arrival": departure + travel.complete(supply.node, destination),
                         "conditional_footprint": _footprint(observation, path, departure, cid, travel),
                         "read_set": [{"kind": "source_owner_version", "owner": observation["owner_id"],
                                       "version": observation["version"]},
                                      {"kind": "source_supply", "tray_id": supply.tray_id,
                                       "ledger": supply.ledger, "dependency": supply.dependency},
                                      {"kind": job["demand_kind"], "business_bag_id": job["business_bag_id"],
                                       "observed_at": observation["now"] if job["demand_kind"] == "terminal_receiving_pressure"
                                           else job["demand_observed_at"]},
                                      {"kind": "conditional_service", "messages": window["conditional_dependencies"]},
                                      {"kind": "static_resources", "sha256": digest(capacities)}]}
            candidates.append(candidate)
            by_supply[pair["supply"]].append(candidate)
    if len({c["candidate_id"] for c in candidates}) != len(candidates):
        raise ValueError("joint_window:duplicate_exact_candidate_identity")
    actions = []
    for selected in itertools.product(*[[None] + rows for rows in by_supply.values()]):
        selected = [c for c in selected if c is not None]
        if len({c["demand"] for c in selected}) != len(selected):
            continue
        if len(actions) >= max_actions:
            return {"status": "unknown_domain_budget", "actions": actions, "base": base}
        windows = frozen + [w for c in selected for w in c["conditional_footprint"]]
        conflicts = capacity_violations([ObligationWindow(**w) for w in windows], capacities)
        action_id = "|".join(c["candidate_id"] for c in selected) or "WAIT"
        actions.append({"action_id": action_id, "candidates": selected,
                        "public_read_sha256": digest(observation),
                        "conditional_conflicts": conflicts,
                        "served_count": len(selected),
                        "predicted_arrival_sum": sum(c["predicted_arrival"] for c in selected)})
    if len({a["action_id"] for a in actions}) != len(actions):
        raise ValueError("joint_window:duplicate_exact_action_identity")
    base_pairs = {(r["tray_id"], r["destination"]) for r in base["intents"]}
    same_assignment = [a for a in actions if {(c["request"]["tray_id"], c["request"]["destination"])
                                             for c in a["candidates"]} == base_pairs]
    objective = proposal_order
    # Ordinary independent windows ignore only *other proposed* empty moves;
    # frozen service windows are equally available to all three comparisons.
    ordinary = min((a for a in same_assignment if all(not capacity_violations(
        [ObligationWindow(**w) for w in frozen + c["conditional_footprint"]], capacities)
        for c in a["candidates"])), key=objective, default=None)
    # One feedback round keeps the original assignment and jointly retimes it.
    one_round = min((a for a in same_assignment if not a["conditional_conflicts"]),
                    key=objective, default=None)
    joint = min((a for a in actions if not a["conditional_conflicts"]), key=objective, default=None)
    return {"status": "complete_finite_public_domain", "actions": actions, "base": base,
            "conditional_windows": frozen, "capacities": capacities,
            "selected": {"ordinary_public_windows": ordinary["action_id"] if ordinary else None,
                         "one_round_same_assignment": one_round["action_id"] if one_round else None,
                         "joint_conditional_repair": joint["action_id"] if joint else None},
            "compute_ms": 1000 * (time.perf_counter() - started),
            "certification": "conditional_interval_model_only; requires_native_execution",
            "unclosed_dependencies": ["remote_receiving_live_occupancy_and_lease_duration",
                                      "current_local_occupancy_and_existing_hard_receiving_or_inflight_obligations_not_fully_windowed",
                                      "future_source_queue", "S4_actual_path", "conditional_forecast_error"],
            "atomic_commit_supported": False, "novelty": "not_established_standard_finite_CSP"}


def submit_action(session: Any, action: dict, observation: dict) -> dict:
    """All-or-none PRECHECK; native submissions remain sequential/non-atomic.

    Failed partial submission is returned verbatim and never silently cancelled
    or converted to WAIT. Each native request still checks its owner's version.
    """
    current = session.observe(observation["owner_id"])
    if current["version"] != observation["version"]:
        return {"status": "stale_read_set", "submissions": [], "reason": "source_owner_version_changed"}
    if current["now"] != observation["now"]:
        return {"status": "stale_read_set", "submissions": [], "reason": "decision_clock_changed"}
    # Native owner version tracks delivered physical/public events, not every
    # pending soft pledge/cancellation. The actual proposal therefore binds the
    # WHOLE lawful projection, including pending transfers and exact message
    # revisions. This conservative read set can over-invalidate; it is not a
    # minimal dependency proof and is not multi-owner atomic publication.
    expected = digest(observation)
    if action.get("public_read_sha256") != expected:
        return {"status": "stale_read_set", "submissions": [], "reason": "action_observation_binding_mismatch"}
    if digest(current) != expected:
        return {"status": "stale_read_set", "submissions": [], "reason": "public_dependency_changed"}
    replies = []
    for candidate in action["candidates"]:
        request = copy.deepcopy(candidate["request"])
        reply = session.submit_transfer_intent(request)
        replies.append({"request": request, "reply": reply})
        if reply.get("status") in ("rejected", "timeout_unknown", "failed_no_safe_continuation"):
            return {"status": "partial_or_rejected", "submissions": replies, "atomic": False}
    return {"status": "submitted", "submissions": replies, "atomic": False}
