"""Conditional route-command/dispatch primitive matching the frozen native API.

This replaces the *meaning* of a forced route in a new projection component;
it does not change old projection code or certify its remaining calendars.
All arguments are public/projected facts. Native outcome rows are usable only
by a separate offline validator, never required by this implementation.
"""
from __future__ import annotations

import copy
import math

VERSION = "public-native-route-preference-v1"
PREFERENCE_SCORE_BONUS = 1.0e9


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def identifier(value):
    return type(value) is int and value >= 0


def unknown(reason):
    return {"status": "unknown", "reason": reason, "model_version": VERSION,
            "native_execution_certified": False, "online_information_delivered": False}


def project_command(request, state, *, at):
    """Validate at wire execution, distinct from submit time and ACK delivery.

`can_enter_reason` and optimistic completion are supplied by the resource
projection at *at*. They must never be copied from an earlier observation
without a justified transition/stability calculation. Unknown stays unknown.
"""
    try:
        required = ("request_id", "owner_id", "tray_id", "business_bag_id", "from", "next",
                    "expected_generation", "expected_traversal", "expiry")
        if (any(k not in request for k in required) or not number(at) or at < 0
                or any(type(request[k]) is not str or not request[k] for k in required[:4])
                or any(not identifier(request[k]) for k in ("from", "next", "expected_generation", "expected_traversal"))
                or not number(request["expiry"]) or state.get("at") != at):
            return unknown("missing_or_malformed_execution_epoch")
        if (state.get("coverage_complete") is not True or state.get("current_state_certified") is not False
                or any(type(state.get(k)) is not bool for k in ("stationary", "active_leg", "allow_suffix_reroute",
                    "directed_edge", "static_suffix_reachable", "advertised_fault"))
                or not number(state.get("optimistic_completion")) or not number(state.get("deadline"))
                or type(state.get("can_enter_reason")) is not str or not state["can_enter_reason"]):
            return unknown("incomplete_projected_permission_state")
        reason = "allowed"
        if request["expiry"] < at:
            reason = "request_expired"
        elif (not state["stationary"] or not state["active_leg"] or
              any(state.get(field) != request[expected] for field, expected in
                  (("tray_id", "tray_id"), ("node", "from"), ("generation", "expected_generation"),
                   ("public_traversal", "expected_traversal")))):
            reason = "stale_executed_prefix"
        elif state.get("resource_owner") != request["owner_id"]:
            reason = "resource_owner_mismatch"
        elif state.get("business_bag_id") != request["business_bag_id"]:
            reason = "business_identity_mismatch"
        elif not state["allow_suffix_reroute"]:
            reason = "service_obligation_disallows_reroute"
        elif not state["directed_edge"]:
            reason = "not_a_directed_edge"
        elif not state["static_suffix_reachable"]:
            reason = "no_static_legal_suffix"
        elif state["advertised_fault"]:
            reason = "advertised_fault"
        elif state["deadline"] >= 0 and state["optimistic_completion"] > state["deadline"]:
            reason = "service_deadline_necessary_bound"
        elif state["can_enter_reason"] != "allowed":
            reason = state["can_enter_reason"]
        return {"status": "conditional_command_projection", "command_status": "updated" if reason == "allowed" else "rejected",
                "reason": reason, "executed_at": at, "request": copy.deepcopy(request),
                "reserves_receiving_capacity": False, "actual_next": None,
                "model_version": VERSION, "native_execution_certified": False}
    except (TypeError, ValueError, KeyError):
        return unknown("malformed_projected_command")


def project_dispatch(candidates, identity, preferences, *, at, same_bag_handoff=False):
    """Apply a live allowed preference before native candidate ranking.

The base S4 score/calendar/queue projection is an explicit dependency. This
function refuses missing scores; it does not silently turn 'best blocked'
into 'best allowed'. Finite fixtures have no physical faults/static closures;
those other native recovery modes require a separate supported contract.
"""
    try:
        if (not number(at) or at < 0 or type(same_bag_handoff) is not bool
                or type(candidates) is not list or not candidates
                or any(not identifier(identity.get(k)) for k in ("node", "generation", "public_traversal"))
                or type(identity.get("tray_id")) is not str or not identity["tray_id"]):
            return unknown("missing_dispatch_identity_or_candidates")
        seen = set(); ranked = copy.deepcopy(candidates)
        for row in ranked:
            if (not identifier(row.get("next")) or row["next"] in seen or not number(row.get("base_score"))
                    or type(row.get("allowed")) is not bool or type(row.get("advertised_fault")) is not bool
                    or type(row.get("reason")) is not str or (row["allowed"] != (row["reason"] == "allowed"))):
                return unknown("incomplete_or_inconsistent_candidate_projection")
            if row["advertised_fault"] or row["reason"] in ("physical_fault", "circulation:edge_closed", "circulation:no_static_legal_suffix"):
                return unknown("unsupported_fault_or_static_recovery_mode")
            seen.add(row["next"]); row["effective_score"] = row["base_score"]
        active = None
        for preference in reversed(preferences):
            if preference.get("status") != "conditional_command_projection":
                return unknown("unverified_projected_preference")
            request = preference["request"]
            if (not number(preference.get("executed_at")) or preference["executed_at"] > at
                    or preference.get("command_status") not in ("updated", "rejected")):
                return unknown("noncausal_projected_preference")
            if preference["command_status"] != "updated":
                continue
            if (request["expiry"] < at or any(identity.get(field) != request[key] for field, key in
                    (("tray_id", "tray_id"), ("node", "from"), ("generation", "expected_generation"),
                     ("public_traversal", "expected_traversal")))):
                continue
            active = request["request_id"]
            for row in ranked:
                if row["next"] == request["next"] and row["allowed"] and not row["advertised_fault"]:
                    row["effective_score"] -= PREFERENCE_SCORE_BONUS
            # Latest accepted intent at this prefix supersedes earlier ones
            # even if the current physical shield prevents its preference.
            break
        ranked.sort(key=lambda row: (row["effective_score"], row["next"]))
        best = ranked[0]
        selected = best if best["allowed"] else next((r for r in ranked if r["allowed"]), None) if same_bag_handoff else None
        return {"status": "conditional_dispatch_projection", "actual_next": selected["next"] if selected else None,
                "disposition": "projected_edge_entry" if selected else "projected_resource_wait",
                "active_preference_request_id": active, "ranked_candidates": ranked,
                "model_version": VERSION, "native_execution_certified": False, "online_information_delivered": False}
    except (TypeError, ValueError, KeyError):
        return unknown("malformed_dispatch_projection")


def source_local_submission_guard(view, intent, *, at, command_delay, dispatch_earliest, dispatch_latest,
                                  receiving_clear_through, known_competitor_entry_earliest):
    """Narrow, conservative closed-loop proposal gate, never a reservation.

Interval bounds must come from the same lawful public projection. A peer
capture alone does not prove the absence of another action; missing complete
coverage or a competitor bound forbids the dependent proposal.
"""
    if (not all(number(x) for x in (at, command_delay, dispatch_earliest, dispatch_latest, receiving_clear_through,
                                   known_competitor_entry_earliest)) or command_delay < 0
            or view.get("now") != at or view.get("owner_id") != intent.get("owner_id")
            or view.get("complete_declared_action_and_tray_coverage") is not True):
        return unknown("missing_lawful_current_or_interval_coverage")
    execution = at + command_delay
    if not execution < dispatch_earliest <= dispatch_latest:
        return unknown("command_not_strictly_before_possible_dispatch")
    if not dispatch_latest < receiving_clear_through or not dispatch_latest < known_competitor_entry_earliest:
        return unknown("receiving_competition_can_cross_command_dispatch_interval")
    if view.get("source_stationary_identity") != {k: intent.get(k) for k in
            ("tray_id", "business_bag_id", "from", "expected_generation", "expected_traversal")}:
        return unknown("source_identity_changed")
    if view.get("current_target_can_enter_reason") != "allowed":
        return unknown("current_target_not_allowed")
    return {"status": "conditional_submission_proposal", "request": copy.deepcopy(intent),
            "projected_execution_at": execution, "requires_delivered_native_ack": True,
            "requires_actual_edge_audit": True, "native_execution_certified": False,
            "source_current_state_certified": False}
