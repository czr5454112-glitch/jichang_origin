"""New finite action vocabulary: native default versus an actual preference.

This module is a candidate/command interface, not a completed predictor. It
requires independently derived public interval bounds from the caller and
never supplies a forced physical next edge. Historical next1/next3 actions and
their rejected commands are not relabeled by this new vocabulary.
"""
from __future__ import annotations
import copy
import itertools

from . import public_route_preference_model as route

INITIAL = ("native_default", "prefer_2")
LATER = ("native_default", "prefer_8")
RETURNS = (0., .5)


def domain(public_windows):
    """Same four externally preregistered E windows for both initial choices."""
    if (type(public_windows) not in (list, tuple) or len(public_windows) != 4
            or not all(route.number(x) and x >= 0 for x in public_windows)
            or len(set(public_windows)) != 4 or list(public_windows) != sorted(public_windows)):
        raise ValueError("preference_actions:four_distinct_ordered_public_windows_required")
    rows = [dict(initial_action=a, empty_departure=t, return_delay=d, later_action=n)
            for a, t, d, n in itertools.product(INITIAL, public_windows, RETURNS, LATER)]
    return {"schema": "g31.public_executable_preference_domain.v1", "actions": rows,
            "candidate_count": 32, "shared_evaluation_budget": 32,
            "fixed_initial_families": {a: [r for r in rows if r["initial_action"] == a] for a in INITIAL},
            "native_default_expected_next": None, "native_execution_certified": False}


def materialize(choice, *, phase, view, request_id, projected_intervals, public_command_delay):
    """Prepare a source-local command or a documented absence of a command.

The caller must run the same public interval derivation for every method.
Unknown intervals forbid a preference; they do not turn it into a successful
default action. An accepted command still requires its own ACK and edge audit.
"""
    unknown = lambda reason: {"status": "unknown", "reason": reason, "request": None,
                              "actual_next": None, "native_execution_certified": False}
    try:
        if phase not in ("initial", "first_reuse_route"):
            return unknown("unsupported_stage")
        allowed = INITIAL if phase == "initial" else LATER
        if choice not in allowed:
            return unknown("undeclared_action")
        owner, node, job, target = ("A", 0, "loaded", 2) if phase == "initial" else ("B", 7, "reuse1", 8)
        now = view["now"]
        if not route.number(now) or now < 0 or view.get("owner_id") != owner:
            return unknown("wrong_current_owner_or_clock")
        trays = [row for row in view["trays"] if row.get("tray_id") == "L"]
        jobs = [row for row in view["jobs"] if row.get("business_bag_id") == job]
        if (len(trays) != 1 or len(jobs) != 1 or trays[0].get("node") != node
                or trays[0].get("mode") != "loaded" or trays[0].get("business_bag_id") != job
                or trays[0].get("edge_from") != -1 or trays[0].get("edge_to") != -1
                or not route.identifier(trays[0].get("generation"))
                or not route.identifier(trays[0].get("traversal_id"))
                or jobs[0].get("allow_suffix_reroute") is not True):
            return unknown("source_not_current_uncommitted_loaded_stage")
        if choice == "native_default":
            return {"status": "declared_native_default", "request": None, "actual_next": None,
                    "requested_next": None, "r1_update_executed": False,
                    "requires_actual_edge_audit": True, "native_execution_certified": False,
                    "source_stage": {"owner": owner, "node": node, "job": job, "tray": "L"},
                    "meaning": "No new route preference; native scorer and shield choose the actual edge."}
        if type(request_id) is not str or not request_id:
            return unknown("missing_fresh_request_identity")
        # Delay is part of the separately declared public action contract;
        # observe_protocol does not expose an owner_protocol field.
        delay = public_command_delay
        if not route.number(delay) or delay < 0:
            return unknown("unsupported_public_command_delay")
        intent = {"request_id": request_id, "kind": "route", "owner_id": owner,
                  "business_bag_id": job, "tray_id": "L", "from": node, "next": target,
                  "expected_generation": trays[0]["generation"], "expected_traversal": trays[0]["traversal_id"],
                  "expiry": now + 5., "message_delay": delay}
        gate_view = {"now": now, "owner_id": owner,
            "complete_declared_action_and_tray_coverage": projected_intervals["complete_declared_action_and_tray_coverage"],
            "source_stationary_identity": {k:intent[k] for k in
                ("tray_id", "business_bag_id", "from", "expected_generation", "expected_traversal")},
            "current_target_can_enter_reason": projected_intervals["current_target_can_enter_reason"]}
        result = route.source_local_submission_guard(gate_view, intent, at=now, command_delay=delay,
            dispatch_earliest=projected_intervals["dispatch_earliest"],
            dispatch_latest=projected_intervals["dispatch_latest"],
            receiving_clear_through=projected_intervals["receiving_clear_through"],
            known_competitor_entry_earliest=projected_intervals["known_competitor_entry_earliest"])
        result["public_interval_provenance"] = copy.deepcopy(projected_intervals.get("provenance"))
        if not result["public_interval_provenance"]:
            return unknown("missing_interval_derivation_provenance")
        result["requested_next"] = target
        result["actual_next"] = None
        return result
    except (KeyError, TypeError, ValueError, OverflowError):
        return unknown("incomplete_public_action_input")
