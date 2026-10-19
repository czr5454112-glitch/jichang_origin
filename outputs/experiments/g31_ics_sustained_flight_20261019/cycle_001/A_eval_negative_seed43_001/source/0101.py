"""Conditional later projection with observed-entry facts in a finite fixture.

No native API, outcome table or online authentication. The old stationary model
and frozen delivery gate are unchanged. This version extends only predicates
explicitly discharged below; every other old guard remains a rejection.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from . import public_preexisting_model as previous
from .planning_capture_v2_contract import PHYSICAL_KINDS, TERMINAL_BY_KIND

VERSION = "public-preexisting-3tray-5job-observed-entry-v3-draft2"
JOBS = previous.JOBS
METHODS = ("coordinate_strict", "coordinate_plateau", "resource_pair_repair", "finite_horizon_enumeration")
MOVING_EDGES = {(1, 3), (3, 4)}
# These old predicates reject every moving tray. Their replacements below
# check exact moving identity, lifecycle and receiving occupancy, without
# changing any unsupported contract/population/terminal/action guard.
REPLACED_PREDICATES = {
    "unsupported_fault_or_reservation_uncertainty", "autonomous_transition_or_unknown_capture_state:E",
    "unknown_inflight_or_receiving_clearance", "unsupported_receiver_state", "unexplained_occupancy",
}


def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
def number(value): return type(value) in (int, float) and math.isfinite(value)
def latest_possible_start(finish, duration):
    """Outward upper inverse of one rounded native finish=start+duration.

The naive rounded subtraction can equal a capture boundary although a later
representable start produces the same stored finish. This intentionally may
reject boundary-equal valid starts; it never adds a business regression epsilon.
"""
    if not number(finish) or not number(duration) or duration <= 0: return math.inf
    return math.nextafter(math.nextafter(finish, math.inf) - duration, math.inf)
def unknown(reasons):
    return {"status": "unknown", "reasons": sorted(set(reasons)), "model_version": VERSION,
        "online_information_delivered": False, "native_protection_certified": False, "current_state_certified": False}


def assemble_later(contract, jobs, trays, resources, *, now, phase, source_records,
                   terminal_receipts, owner_pending_tray_requests, entry_receipts,
                   collection_contract):
    """Validate supplied source facts under an explicit conditional quiet policy.

Different source capture epochs are retained. All declared states must be
conditionally stable over their union through now. This is not an atomic cut,
and the native pending-action ledger cannot certify unsubmitted Python plans.
"""
    try:
        old = previous.assemble_later(contract, jobs, trays, resources, now=now, phase=phase,
            source_records=source_records, terminal_receipts=terminal_receipts,
            owner_pending_tray_requests=owner_pending_tray_requests)
        replacing = REPLACED_PREDICATES if trays.get("E", {}).get("edge_to", -1) >= 0 else set()
        unresolved = set(old.get("reasons", ())) - replacing
        if unresolved: return unknown(unresolved)
        if (not number(now) or len(source_records) != 2 or
                {r["owner"] for r in source_records} != {"A", "B"}):
            return unknown(["unsupported_source_epochs"])
        floor = min(r["captured_at"] for r in source_records)
        if (collection_contract != {"schema": "g31.conditional_collection_quiescence.v1",
                "physical_admissions_quiesced_from": floor, "through": now,
                "future_python_actions_certified_by_native": False}
                or any(r["known_faults"] or r["unresolved_tray_request_ids"] for r in source_records)):
            return unknown(["missing_conditional_quiescence_or_unresolved_fault_action"])
        if not number(floor) or not 0 <= floor <= now or any(j["arrival"] > floor for j in jobs.values()):
            return unknown(["unknown_future_or_uncaptured_job"])
        # Terminal at a later source capture does not establish stability from
        # an earlier source epoch. Route updates can change preference without
        # changing lifecycle, generation or committed prefix. V2 does not carry
        # their execution epochs or installed preference. Preserve the complete
        # action set and conservatively require every terminal delivered ACK to
        # be strictly before the whole capture union. Same-time ordering and
        # late ACKs remain unknown; never infer an earlier execution time.
        for record in source_records:
            actions = record.get("submitted_physical_actions")
            ids = record.get("submitted_physical_request_ids")
            if (not isinstance(actions, list) or not isinstance(ids, list)
                    or ids != [row.get("request_id") for row in actions]
                    or len(ids) != len(set(ids)) or any(not isinstance(key, str) or not key for key in ids)
                    or [(row.get("request_id"), row.get("kind")) for row in actions] != sorted((row.get("request_id"), row.get("kind")) for row in actions)):
                return unknown(["missing_or_inconsistent_complete_physical_action_set"])
            for action in actions:
                ack = action.get("last_delivered_ack")
                if (action.get("source_owner") != record["owner"] or action.get("kind") not in PHYSICAL_KINDS
                        or not isinstance(ack, dict) or type(ack.get("sequence")) is not int or ack["sequence"] <= 0
                        or ack.get("status") not in TERMINAL_BY_KIND[action["kind"]]
                        or not number(ack.get("delivered_at")) or not 0 <= ack["delivered_at"] < floor):
                    return unknown(["physical_action_not_delivered_terminal_before_capture_union"])
        if any(r["completed_at"] > floor for r in terminal_receipts):
            return unknown(["completed_prefix_crosses_capture_interval"])
        completed = {r["business_bag_id"]: r["completed_at"] for r in terminal_receipts}
        owners = {n["node"]: n["resource_owner"] for n in contract["node_contracts"]}
        source_by_owner = {r["owner"]: r for r in source_records}
        edges = {(u, v): max(.001, length/speed) for u, v, length, speed in contract["edge_records"]}
        services = {n[0]: max(.001, n[2]) for n in contract["node_records"]}
        moving = {name: t for name, t in trays.items() if t["edge_to"] >= 0}
        if moving and set(moving) != {"E"}: return unknown(["unsupported_moving_population"])
        if len(entry_receipts) != len(moving) or {r["tray_id"] for r in entry_receipts} != set(moving):
            return unknown(["missing_duplicate_or_extra_observed_entry"])
        entries = {r["tray_id"]: copy.deepcopy(r) for r in entry_receipts}
        stability = []
        for name, tray in trays.items():
            source = owners[tray["node"]]; record = source_by_owner[source]
            if any(type(tray[field]) is not int or tray[field] < 0 for field in ("generation", "traversal_id")):
                return unknown(["invalid_public_tray_identity"])
            if tray["reception_node"] != -1: return unknown(["unsupported_additional_receiving_lease"])
            if name in moving:
                row = entries[name]; edge = tray["edge_from"], tray["edge_to"]
                identity = ("tray_id", "business_bag_id", "generation", "traversal_id", "edge_from", "edge_to")
                if (edge not in MOVING_EDGES or tray["node"] != edge[0] or tray["mode"] != "loaded"
                        or tray["business_bag_id"] != "receiver" or jobs["receiver"]["status"] != "in_transit"
                        or row["source_owner"] != source or row["receipt_event"] != "EDGE_ENTER"
                        or any(row[k] != tray[k] for k in identity) or tray["traversal_id"] == 0
                        or any(type(row[k]) is not int for k in ("generation", "traversal_id", "edge_from", "edge_to"))
                        or any(not number(row[k]) for k in ("entered_at", "derived_edge_exit_at", "static_edge_travel_seconds"))
                        or not 0 <= jobs["receiver"]["loaded_at"] <= row["entered_at"] <= floor
                        or row["static_edge_travel_seconds"] != edges[edge]
                        or row["derived_edge_exit_at"] != row["entered_at"] + edges[edge]
                        or not now < row["derived_edge_exit_at"]
                        or tray["committed_prefix"] != ([1] if edge == (1, 3) else [1, 3])):
                    return unknown(["unobserved_stale_or_mismatched_current_edge"])
                bound = row["derived_edge_exit_at"]
                kind = "observed_entry_before_all_captures_exit_after_decision"
            else:
                if tray["edge_from"] != -1: return unknown(["inconsistent_stationary_edge"])
                mode = tray["mode"]
                if mode == "empty":
                    completed_job = {"L": "loaded", "P": "blocker", "E": "receiver"}[name]
                    stable = (tray.get("service_ready_known") is True and tray.get("ready_kind") == "empty_available_at"
                        and number(tray.get("available_at")) and number(tray.get("service_ready_at"))
                        and completed_job in completed and completed[completed_job] <= tray["available_at"]
                        and tray["available_at"] == tray["service_ready_at"] <= floor and not tray["business_bag_id"])
                    bound = None
                elif mode == "loading":
                    finish = tray.get("load_complete_at"); job = jobs[tray["business_bag_id"]]
                    stable = (tray.get("service_ready_known") is True and tray.get("ready_kind") == "observed_load_completion"
                        and number(finish) and number(tray.get("service_ready_at"))
                        and finish == tray["service_ready_at"] > now and latest_possible_start(finish, job["load_seconds"]) <= floor)
                    bound = finish
                elif mode == "loaded":
                    stable = (tray.get("service_ready_known") is True and tray.get("ready_kind") == "committed_local_service_end"
                        and number(tray.get("service_ready_at")) and tray["service_ready_at"] > now
                        and latest_possible_start(tray["service_ready_at"], services[tray["node"]]) <= floor
                        and 0 <= jobs[tray["business_bag_id"]]["loaded_at"] <= floor)
                    bound = tray.get("service_ready_at")
                elif mode == "hold":
                    stable = (tray.get("service_ready_known") is True and tray.get("ready_kind") == "observed_hold_completion"
                        and number(tray.get("available_at")) and number(tray.get("service_ready_at"))
                        and tray["available_at"] == tray["service_ready_at"] > now)
                    bound = tray.get("available_at")
                else: stable = False; bound = None
                if not stable: return unknown(["autonomous_transition_within_capture_union:" + name])
                kind = "stationary_lifecycle_interval"
            stability.append({"tray_id": name, "source_owner": source, "actual_captured_at": record["captured_at"],
                "conditional_stable_from": floor, "through": now, "next_transition_bound": bound, "basis": kind})
        # Compare all physical reservations, not merely the old local parked
        # count. An unidentified incoming count cannot fill missing membership.
        reservations = {node: [] for node in owners}
        for name, tray in trays.items():
            node = tray["edge_to"] if tray["edge_to"] >= 0 else tray["node"]
            reservations[node].append([name, tray["generation"], tray["traversal_id"]])
        for node, resource in resources.items():
            local_count = sum(owners[trays[name]["node"]] == owners[node] for name, _, _ in reservations[node])
            actual = sum(t["node"] == node and t["edge_to"] < 0 and t["mode"] == "empty" and t["available_at"] <= now for t in trays.values())
            if (type(resource["occupancy"]) is not int or type(resource["actual_available"]) is not int
                    or type(resource.get("unrepresented_occupancy")) is not int
                    or resource["occupancy"] != len(reservations[node]) or resource["actual_available"] != actual
                    or resource["unrepresented_occupancy"] != len(reservations[node])-local_count):
                return unknown(["incomplete_or_inconsistent_receiving_occupancy"])
        for source, record in source_by_owner.items():
            if record["unrepresented_occupancy"] != sum(r["unrepresented_occupancy"] for node, r in resources.items() if owners[node] == source):
                return unknown(["source_occupancy_coverage_mismatch"])
        bundle = copy.deepcopy(old)
        bundle.update(status="conditional_model_input", reasons=[], model_version=VERSION,
            entry_receipts=entries, stability=stability, collection_contract=copy.deepcopy(collection_contract),
            reservations_by_node=reservations, conditional_stability_only=True, current_state_certified=False,
            native_protection_certified=False, online_information_delivered=False,
            discarded_stationary_predicates=sorted(set(old.get("reasons", ())) & replacing),
            assumptions=["fixed three-tray/five-job contracts and exact public protocol; no hidden future arrival/fault",
                "conditional policy quiescence over capture union; native does not certify unsubmitted Python plans",
                "complete source physical-action sets have terminal delivered ACKs strictly before the earliest capture; no execution-time inference",
                "source-observed moving entry is before all captures and exit strictly after now",
                "all other lifecycle deadlines are outside capture union; own current view must be checked by adapter",
                "captured-state consistency and model projection only; no atomic-cut, physical-feasibility or protection proof"])
        bundle["capture_pair_sha256"] = hashlib.sha256(canonical(bundle).encode()).hexdigest()
        return bundle
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError, ZeroDivisionError):
        return unknown(["malformed_or_unsupported_v3_later_state"])


class LaterProjection(previous.LaterProjection):
    def seed(self):
        super().seed()
        for name, row in self.b["entry_receipts"].items():
            tray = self.trays[name]; target = row["edge_to"]
            tray["goal"] = self.jobs[tray["job"]]["destination"]
            self.next_entry[row["edge_from"], target] = row["entered_at"] + self.edges[row["edge_from"], target]["entry_headway"]
            if target != tray["goal"]:
                self.calendars[target].append((row["derived_edge_exit_at"], row["derived_edge_exit_at"] + self.service[target]))
            self.schedule(row["derived_edge_exit_at"], "arrive", name, target)


def predict(bundle, action):
    if bundle.get("status") != "conditional_model_input" or bundle.get("model_version") != VERSION:
        return {"status": "unknown_missing_input", "completion": {}, "native_protection_certified": False}
    if (type(action.get("reuse_next")) is not int or not number(action.get("return_delay"))
            or action not in previous.candidates(bundle)[0]):
        return {"status": "unknown_unsupported_action", "completion": {}, "native_protection_certified": False}
    return LaterProjection(bundle, action).run()


def propose(bundle, *, method="resource_pair_repair", evaluation_budget=32):
    """Same four actions, order, budget and strict five-job rule for every method."""
    if method not in METHODS or type(evaluation_budget) is not int or not 1 <= evaluation_budget <= 32:
        raise ValueError("v3_model:unsupported_method_or_budget")
    if bundle.get("status") != "conditional_model_input" or bundle.get("model_version") != VERSION:
        return {"status": "unknown_input", "selected_action": None}
    actions, _ = previous.candidates(bundle); values = {(a["reuse_next"], a["return_delay"]): a for a in actions}
    base = (3, 0.); cache = {}; hit = False
    def evaluate(key):
        nonlocal hit
        if key in cache: return cache[key]
        if len(cache) >= evaluation_budget: hit = True; return None
        prediction = predict(bundle, values[key]); reference = cache[base]["prediction"] if base in cache else prediction
        known = prediction["status"] == reference["status"] == "conditional_prediction" and set(prediction["completion"]) == set(reference["completion"]) == JOBS
        cache[key] = {"action": values[key], "prediction": prediction,
            "model_protected": all(prediction["completion"][j] <= reference["completion"][j] for j in JOBS) if known else None}
        return cache[key]
    evaluate(base); score = lambda key: (cache[key]["prediction"]["completion_sum"], key)
    if cache[base]["model_protected"] is True:
        if method in ("resource_pair_repair", "finite_horizon_enumeration"):
            for key in sorted(values):
                if evaluate(key) is None: break
        else:
            frontier, visited = [base], set()
            while frontier and not hit:
                current = min(frontier, key=score); frontier.remove(current)
                if current in visited: continue
                visited.add(current); eligible = []
                for key in sorted(values):
                    if sum(a != b for a, b in zip(current, key)) != 1: continue
                    row = evaluate(key)
                    if row is None: break
                    if row["model_protected"] is not True: continue
                    improves = score(key)[0] < score(current)[0] if method == "coordinate_strict" else score(key)[0] <= score(current)[0]
                    if improves and key not in visited: eligible.append(key)
                if method == "coordinate_strict": frontier = [min(eligible, key=score)] if eligible else []
                else: frontier.extend(k for k in eligible if k not in frontier)
    eligible = [key for key, row in cache.items() if row["model_protected"] is True]
    best = min(eligible, key=score) if eligible else None
    return {"status": "conditional_model_proposal" if best else "unknown_incumbent_projection", "model_version": VERSION,
        "method": method, "selected_action": copy.deepcopy(values[best]) if best else None,
        "selected_prediction": cache[best]["prediction"] if best else None, "evaluations": len(cache), "evaluation_budget": evaluation_budget,
        "candidate_denominator": len(values), "rows": [{**cache[k], "evaluation_status": "evaluated"} if k in cache else
            {"action": values[k], "evaluation_status": "unknown_unexecuted", "model_protected": None} for k in sorted(values)],
        "online_information_delivered": False, "native_protection_certified": False, "current_state_certified": False,
        "capture_pair_sha256": bundle["capture_pair_sha256"], "future_action_is_nonbinding_prediction": True}
