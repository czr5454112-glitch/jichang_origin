"""Bounded offline action-semantics matrix, not an online model or solver.

Every case/vector is fixed before the first session. Actual owner-local v1/v3
input and lifecycle guards remain the accepted bound runner's guards. The
vector replaces search only; it cannot bypass missing information or commit a
foreign/stale prefix. Native default is an explicit absence of a route request.
"""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback
import uuid
from types import SimpleNamespace

from . import research_native_preexisting_v3_bound as bound
from . import preference_matrix_contract as matrix
from . import native_preexisting_initial_adapter as initial_adapter
from . import preexisting_v3_endpoint_identity as endpoint_binding
from . import bounded_windows_job
from .planning_capture_v2_contract import PHYSICAL_KINDS

adapter = bound.adapter
run_admission = bound.run_admission
native_host = bound.native_host
v1, v2, model = bound.v1, bound.v2, bound.model
LocalTransport = bound.LocalTransport
native_scene = bound.native_scene
MAX_ACTIVATIONS = bound.MAX_ACTIVATIONS


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def require(value, reason):
    if not value: raise ValueError("preference_matrix:" + reason)


def fixed_choice(information, vector):
    # A predeclared vector supplies the action only after the same actual
    # delivered-input/stability domain gate. Raw JSON cannot mint authority.
    if (not adapter.is_native_collected(information)
            or information.get("status") != "conditional_native_delivered_later_v3_model_input"
            or information.get("native_delivery_verified") is not True):
        return {"status":"unknown_unverified_or_unsupported_input", "selected_action":None}
    return {"status":"predeclared_finite_counterfactual_action", "selected_action":{
        "return_delay":vector["return_delay"], "reuse_next":8 if vector["later_action"] == "prefer_8" else None},
        "vector":copy.deepcopy(vector), "predicted_protection":None, "native_model_protection_certified":False}


class OwnerPolicy(bound.OwnerPolicy):
    """Inherit identical transport, replies, quiet periods and recovery rules."""
    def route_tray(self, view, tray, next_node, causal):
        if next_node is not None:
            # Target8 belongs to B. A known-full target is an unexecuted
            # selected action, never relabeled a successful default.
            if next_node == 8:
                target = [n for n in view["node_contracts"] if n["node"] == 8 and n["resource_owner"] == self.owner]
                if len(target) != 1 or target[0].get("occupancy", math.inf) >= target[0]["capacity"]:
                    self.choices.append({"at":view["now"], "request_id":None, "job":tray["business_bag_id"],
                        "next":8, "local_tray":copy.deepcopy(tray), "known_delivered_preference":None,
                        "disposition":"unknown_local_receiving_precondition"})
                    self.route_keys.add((tray["business_bag_id"],tray["generation"],tray["traversal_id"]))
                    return None
            return super().route_tray(view, tray, next_node, causal)
        self.choices.append({"at":view["now"], "request_id":None, "job":tray["business_bag_id"],
            "next":None, "local_tray":copy.deepcopy(tray), "known_delivered_preference":None,
            "disposition":"native_default_no_command", "actual_next":None, "r1_update_executed":False})
        self.route_keys.add((tray["business_bag_id"],tray["generation"],tray["traversal_id"]))
        return None

    def decide_pending(self, view):
        pending = self.pending
        if not pending or view["now"] < self.peer_quiet_until: return
        own = self.client.rows[pending["request_id"]].get("ack", {})
        pair_ready = own.get("status") == "delivered" and pending["peer_message"] is not None
        if not pair_ready and view["now"] < pending["deadline"]: return
        information = adapter.collect_native(self.native,self.session,self.owner,pending["request_id"],
            accepted=self.accepted,ledger=self.ledger,owned_client_rows=self.client.owned(self.owner),phase=pending["phase"],
            peer_message_id=pending["peer_message"],collection_started_at=pending["at"],policy_quiet_since=pending["at"])
        decision = fixed_choice(information,self.method)
        call_prefix_count = len(self.client.calls)
        selected = decision.get("selected_action"); fallback = selected is None
        action = selected or {"reuse_next":None,"return_delay":0.}
        causal = {"relation":"fallback" if fallback else "result_handling", "continuation_parent_roots":[pending["root"]],
            "predecessor_protocol_id":pending["request_id"],"delivered_peer_message_id":pending["peer_message"],
            "collection_started_at":pending["at"],"predeclared_counterfactual_vector":copy.deepcopy(self.method)}
        actual = None; local_stage = False
        if pending["phase"] == "first_return":
            tray = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 6 and t["mode"] == "empty"
                and t["edge_to"] < 0 and t["available_at"] <= view["now"]),None)
            demand = v1.latest_demand(view,"B")
            if tray and demand and any(j["origin"] == 7 for j in demand["jobs"]):
                local_stage = True; actual = self.return_tray(view,tray,demand,action["return_delay"],causal)
        else:
            tray = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 7 and t["mode"] == "loaded"
                and t["edge_to"] < 0 and t["business_bag_id"] == "reuse1"),None)
            if tray:
                local_stage = True; actual = self.route_tray(view,tray,action["reuse_next"],causal)
        decision_executed = (not fallback and local_stage and (actual is not None or
            pending["phase"] == "first_reuse_route" and action["reuse_next"] is None))
        self.decisions.append({"at":view["now"],"phase":pending["phase"],"collection":copy.deepcopy(pending),
            "information":information,"decision":decision,"fallback_used":fallback,"executed_first_action":action,
            "native_request_id":actual,"actual_local_view":copy.deepcopy(view),
            "predecision_call_prefix_count":call_prefix_count,
            "selected_action_admitted":decision_executed,"future_proposal_component_executed_without_replan":False})
        self.pending = None


def owner_first_action(native,session,client,owner,planning_id,vector,accepted):
    information,ledger = adapter.collect_initial_ledger(native,session,owner,planning_id,accepted=accepted)
    view = session.observe_protocol(owner); identity = None; action = None; admitted = False
    endpoints = {"view":copy.deepcopy(view),"command":session.protocol_command(owner,planning_id),
                 "received":session.protocol_planning_snapshots(owner)}
    decision = {"status":"unknown_unverified_initial_input","selected_action":None}
    if information.get("native_delivery_verified"):
        case = information["bundle"]["case_from_delivered_contracts"]
        allowed = [r["vector"] for r in matrix.matrix_protocol()["rows"].values() if r["case"] == case]
        if vector not in allowed: raise ValueError("preference_matrix:vector_not_in_delivered_case")
        action = copy.deepcopy(vector)
        if owner == "A":
            tray = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 0 and t["mode"] == "loaded"
                and t["business_bag_id"] == "loaded" and t["edge_to"] < 0),None)
            if tray and vector["initial_action"] == "native_default":
                admitted = True
            elif tray:
                target = [n for n in view["node_contracts"] if n["node"] == 2 and n["resource_owner"] == owner]
                if len(target) == 1 and target[0].get("occupancy",math.inf) < target[0]["capacity"]:
                    identity = client.submit(owner,"route","initial-route",business_bag_id="loaded",tray_id="L",
                        **{"from":0,"next":2},expected_generation=tray["generation"],expected_traversal=tray["traversal_id"],
                        expiry=5.,message_delay=.01,causal={"relation":"result_handling","predecessor_protocol_id":planning_id,
                            "continuation_parent_roots":[client.creations[planning_id]["creating_root"]],
                            "predeclared_counterfactual_vector":copy.deepcopy(vector)})
                    admitted = True
        else:
            tray = next((t for t in view["trays"] if t["tray_id"] == "E" and t["node"] == 5 and t["mode"] == "empty"
                and t["edge_to"] < 0 and t["available_at"] <= view["now"]),None)
            if tray:
                identity = client.submit(owner,"transfer","initial-supply",tray_id="E",source=5,destination=1,
                    earliest_departure=vector["empty_departure"],expiry=39.,message_delay=.01,
                    causal={"relation":"result_handling","predecessor_protocol_id":planning_id,
                        "continuation_parent_roots":[client.creations[planning_id]["creating_root"]],
                        "predeclared_counterfactual_vector":copy.deepcopy(vector)})
                admitted = True
        decision = {"status":"declared_current_local_counterfactual" if admitted else "unknown_local_action_precondition",
            "selected_action":action if admitted else None, "actual_next":None,
            "native_default_no_command":owner == "A" and vector["initial_action"] == "native_default" and admitted}
    return {"owner":owner,"at":view["now"],"information":information,"decision":decision,
        "native_request_id":identity,"local_action_view":view,"raw_endpoints":endpoints},ledger


def run_branch(native, row, contract_reference, semantic_gate_binding, *, accepted_run, branch_key):
    if type(accepted_run) is not run_admission.RunAcceptance or not accepted_run.active_for(branch_key):
        raise ValueError("preexisting_v3_run:inactive_run_or_branch")
    declared = accepted_run.branch_specification(branch_key)
    if any(row.get(field) != declared.get(field) for field in ("case", "vector", "method", "fault")):
        raise ValueError("preexisting_v3_run:branch_action_domain_changed")
    runtime = accepted_run.contract_copy(branch_key)
    if runtime["reference"] != contract_reference:
        raise ValueError("preexisting_v3_run:contract_reference_changed")
    if runtime["contract"]["binary_sha256"] != native._g31_native_artifact_identity["sha256"]:
        raise ValueError("preexisting_v3:runtime_gate_loaded_binary_mismatch")
    data = native_scene(row["case"], row.get("fault"))
    session = native.NativeSession(data)
    admission, accepted = adapter.bind_native027(native, session, contract_reference, accepted_run=accepted_run, branch_key=branch_key)
    if accepted is None: raise ValueError("preexisting_v3:runtime_acceptance_rejected:" + str(admission))
    session.advance_to(.05)
    client = LocalTransport(session); channels, planning = {}, {}
    for owner, peer in (("A", "B"), ("B", "A")):
        client.activate(owner, {"kind": "initial_public_epoch", "at": .05})
        channels[owner] = client.submit(owner, "demand", "seed-demand", target_owner=peer, message_delay=.01, publication_delay=.01)
        planning[owner] = client.submit(owner, "planning_snapshot", "initial-planning", target_owner=peer,
            message_delay=.01, publication_delay=.1 if row.get("fault") == "missing_peer" and owner == "A" else .01,
            expiry=.08 if row.get("fault") == "expired_capture" else .21)
    session.advance_to(v1.START)
    ledgers, initial_owners = {}, {}
    for owner in ("A", "B"):
        client.activate(owner, {"kind": "initial_decision_epoch", "at": v1.START}); client.refresh_owner(owner, retry=False)
        if row["method"] == "delivery_only":
            endpoints = {"view": session.observe_protocol(owner), "command": session.protocol_command(owner, planning[owner]),
                "received": session.protocol_planning_snapshots(owner)}
            info, ledger = adapter.collect_initial_ledger(native, session, owner, planning[owner], accepted=accepted); ledgers[owner] = ledger
            initial_owners[owner] = {"owner": owner, "information": info, "raw_endpoints": endpoints,
                "decision": {"status": "delivery_probe_only", "selected_action": None}, "native_request_id": None}
        else:
            initial_owners[owner], ledgers[owner] = owner_first_action(native, session, client, owner, planning[owner], row["vector"], accepted)
    if row["method"] == "delivery_only":
        return {"specification": row, "input": data, "initial_owners": initial_owners, "calls": client.calls, "outbox": client.rows,
            "summary": {"status": "readiness_observed", "both_inputs_verified": all(r["information"].get("native_delivery_verified") for r in initial_owners.values()),
                "owner_status": {o: r["information"]["status"] for o, r in initial_owners.items()}, "business_metrics": None, "physical_protection": "not_assessed"}}
    selections = {o: value["decision"].get("selected_action") for o, value in initial_owners.items()}
    if any(ledgers[o] is None or selections[o] is None for o in ("A", "B")) or selections["A"] != selections["B"]:
        session.advance_to(v1.HORIZON)
        return {"specification": row, "input": data, "initial_owners": initial_owners, "calls": client.calls, "outbox": client.rows,
            "result": session.result_at(session.physical_time), "summary": {"status": "unknown_initial_asymmetry_or_missing_ledger", "business_metrics": None}}
    policies = {o: OwnerPolicy(native, session, client, o, ledgers[o], channels[o], row["vector"], accepted,
        initial_owners[o]["native_request_id"] if o == "B" else None) for o in ("A", "B")}
    cursors = {o: 0 for o in policies}; tick = 0; batches = []; activations = 0
    status = "finished"
    while session.physical_time < v1.HORIZON and activations < MAX_ACTIVATIONS:
        deadline = min(v1.HORIZON, v1.START + tick * v1.PERIOD,
            *(max(p.pending["deadline"], p.peer_quiet_until) for p in policies.values() if p.pending))
        if deadline < session.physical_time: raise ValueError("rolling_joint:missed_deadline")
        response = session.advance_until_owner_notification(["A", "B"], cursors, deadline, max_events=100000)
        batches.append({"deadline": deadline, "response": copy.deepcopy(response)})
        if response["status"] not in {"notified", "horizon_reached"} or response.get("timestamp_complete") is not True:
            status = "unknown_native_boundary"; break
        now = session.physical_time
        due_tick = now == v1.START + tick * v1.PERIOD
        if due_tick: tick += 1
        notices = response.get("notifications", {})
        due = {o for o in policies if due_tick or o in notices or policies[o].pending and now >= policies[o].pending["deadline"]}
        for owner, notice in notices.items(): cursors[owner] = notice["sequence"]
        for owner in sorted(due):
            policies[owner].activate({"native_notification": copy.deepcopy(notices.get(owner)), "periodic_tick": due_tick,
                "collection_deadline": bool(policies[owner].pending and now >= policies[owner].pending["deadline"])})
            activations += 1
    if activations >= MAX_ACTIVATIONS: status = "unknown_activation_budget"
    if status == "finished": session.advance_to(v1.HORIZON)
    for owner in policies:
        client.activate(owner, {"kind": "final_outbox_collection", "at": session.physical_time})
        client.refresh_owner(owner, retry=False)
    continuation = {"status": status, "route_choices": policies["B"].choices, "returns": policies["A"].returns,
        "supply_lineage": policies["B"].supplies, "recovery_decisions": policies["B"].recovery}
    result = session.result_at(session.physical_time)
    decisions = {o: p.decisions for o, p in policies.items()}
    summary = completed_summary(data,result,client,continuation,selections["A"],initial_owners,decisions)
    return {"specification": copy.deepcopy(row), "input": data, "initial_owners": initial_owners,
        "retained_ledgers": {o: l.audit_copy() for o, l in ledgers.items()}, "decisions": decisions,
        "exchanges": {o: p.exchanges for o, p in policies.items()}, "collection_policy_intervals": {o: p.quiet_periods for o,p in policies.items()},
        "native027_acceptance": accepted.audit_copy(), "calls": client.calls, "outbox": client.rows,
        "request_creations": client.creations, "owner_activation_admissions": client.roots, "ack_handling": client.ack_handling,
        "lineage_status": "experimental_proxy_causes_only_cross_owner_roots_not_transmitted_no_business_denominator_certificate",
        "continuation": continuation, "native_batches": batches, "result": result, "summary": summary}


def completed_summary(data,result,client,continuation,vector,initial_owners,decisions):
    summary = assess_cell(data,result,client,continuation,vector)
    flat = [d for rows in decisions.values() for d in rows]
    summary["rolling_model_inputs_verified"] = len(flat) == 2 and all(d["information"]["native_delivery_verified"] for d in flat)
    summary["rolling_fallback_count"] = sum(d["fallback_used"] for d in flat)
    summary["rolling_action_count"] = sum(d["native_request_id"] is not None for d in flat)
    summary["all_required_inputs_verified"] = summary["rolling_model_inputs_verified"] and all(
        initial_owners[o]["information"].get("native_delivery_verified") is True for o in ("A", "B"))
    summary["selected_actions_executed"] = (summary["status"] == "assessed" and len(flat) == 2
        and all(d.get("selected_action_admitted") is True and not d["fallback_used"] for d in flat))
    if not summary["all_required_inputs_verified"] or not summary["selected_actions_executed"]:
        summary["status"] = "unknown_missing_input_or_unexecuted_counterfactual"
    summary["conditional_stability_only"] = True
    summary["current_state_certified"] = False
    summary["native_model_protection_certified"] = False
    summary["online_model_claim"] = False
    return summary



def assess_cell(data: dict, result: dict, client, continuation: dict, specification: dict) -> dict:
    complete = (result["advance"]["status"] == "reached" and result["advance"]["horizon_complete"]
                and result["advance"]["physical_time"] == v1.HORIZON)
    jobs = {j["business_bag_id"]: j["completed_at"] for j in result["jobs"]}
    expected = {j["business_bag_id"] for j in data["jobs"]}
    business = (complete and len(result["jobs"]) == len(expected) and set(jobs) == expected
                and all(type(t) in (int,float) and math.isfinite(t) and 0 <= t <= v1.HORIZON for t in jobs.values()))
    receipts = result["receipts"]
    line = continuation["supply_lineage"]
    supply = [client.rows[i] for i in line]
    returns = [client.rows[r["request_id"]] for r in continuation["returns"]]
    transfer_ids = {i for i, r in client.rows.items() if r["kind"] == "transfer"}
    ack_ok = lambda row, status: (row.get("ack", {}).get("status") == status
        and type(row["ack"].get("delivered_at")) in (int,float)
        and 0 <= row["ack"]["delivered_at"] <= v1.HORIZON)
    supply_ok = (1 <= len(line) <= v2.SUPPLY_ATTEMPT_LIMIT and len(set(line)) == len(line)
        and ack_ok(supply[-1], "received") and all(ack_ok(r, "rejected") and r["ack"].get("reason") == "receiving_full" for r in supply[:-1]))
    recovery_ok = len(continuation["recovery_decisions"]) == len(line) - 1
    for index, decision in enumerate(continuation["recovery_decisions"]):
        predecessor = client.rows[line[index]]
        recovery_ok = recovery_ok and (decision["predecessor_request_id"] == line[index]
            and decision["request_id"] == line[index + 1] and decision["delivered_rejection"] == predecessor["ack"]
            and decision["at"] >= predecessor["ack"]["delivered_at"] + v2.REJECTION_COOLDOWN
            and decision["delivered_demand"]["delivered_at"] <= decision["at"]
            and decision["local_tray"]["tray_id"] == "E" and decision["local_tray"]["node"] == 5
            and decision["local_tray"]["mode"] == "empty" and decision["local_tray"]["edge_to"] < 0)
    executed = (supply_ok and recovery_ok and len(returns) == 2 and all(ack_ok(r, "received") for r in returns)
                and transfer_ids == set(line) | {r["request"]["request_id"] for r in returns})
    executed = (executed and supply[0]["request"]["earliest_departure"] == specification["empty_departure"]
        and all(record["selected_delay"] == (specification["return_delay"] if index == 0 else 0.)
                and request["request"]["earliest_departure"] == record["at"] + record["selected_delay"]
                for index,(record,request) in enumerate(zip(continuation["returns"],returns))))
    actual_returns = [r for r in receipts if r["event"] == "EMPTY_RECEIVED" and r["tray_id"] == "L" and r["node"] == 7]
    loads = [r for r in receipts if r["event"] == "LOAD_START" and r["business_bag_id"] in {"reuse1", "reuse2"}]
    same_tray = (len(actual_returns) == 2 and len(loads) == 2 and all(r["tray_id"] == "L" for r in loads)
        and [r["business_bag_id"] for r in loads] == ["reuse1", "reuse2"]
        and all(a["time"] <= b["time"] for a, b in zip(actual_returns, loads)))
    routes = [r for r in client.rows.values() if r["kind"] == "route"]
    route_expected = (1 if specification["initial_action"] == "prefer_2" else 0) + sum(c["request_id"] is not None for c in continuation["route_choices"])
    accepted = len(routes) == route_expected and all(ack_ok(r, "updated") for r in routes)
    initial_routes = [r for r in routes if r["request"]["business_bag_id"] == "loaded"]
    accepted = accepted and (len(initial_routes) == (1 if specification["initial_action"] == "prefer_2" else 0))
    if initial_routes:
        accepted = accepted and all(initial_routes[0]["request"][key] == value for key,value in
            {"owner_id":"A","tray_id":"L","from":0,"next":2}.items())
    initial = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == "loaded" and r["from"] == 0]
    route_match = (len(initial) == 1 and initial[0]["to"] in (1, 2)
        and (specification["initial_action"] == "native_default" or initial[0]["to"] == 2))
    actual_choices = []
    for choice in continuation["route_choices"]:
        edges = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == choice["job"] and r["from"] == 7]
        expected_next = (8 if specification["later_action"] == "prefer_8" else None) if choice["job"] == "reuse1" else 3
        route_match = route_match and choice["next"] == expected_next
        if choice["next"] is None:
            route_match = (route_match and choice["job"] == "reuse1" and specification["later_action"] == "native_default"
                and choice["request_id"] is None and choice.get("disposition") == "native_default_no_command"
                and len(edges) == 1 and edges[0]["to"] in (3, 8))
        else:
            route_match = route_match and len(edges) == 1 and edges[0]["to"] == choice["next"]
            if choice["request_id"] is None:
                route_match = route_match and choice["known_delivered_preference"] == choice["next"]
            else:
                actual_request = client.rows.get(choice["request_id"],{}).get("request",{})
                local = choice["local_tray"]
                route_match = route_match and all(actual_request.get(key) == value for key,value in
                    {"owner_id":"B","business_bag_id":choice["job"],"tray_id":"L","from":7,"next":choice["next"],
                     "expected_generation":local["generation"],"expected_traversal":local["traversal_id"]}.items())
        actual_choices.append({"job": choice["job"], "selected_next": choice["next"],
                               "actual_next": edges[0]["to"] if len(edges) == 1 else None})
    replay = copy.deepcopy(data)
    replay["transfers"] = [{**c["request"], "issued_at": c["at"]} for c in client.calls if c["kind"] == "transfer" and not c["retry"]]
    try:
        audit = native_host.audit_result(replay, result)
    except (AssertionError, ValueError, KeyError) as exc:
        audit = {"status": "failed", "reason": str(exc)}
    stock = len(result["trays"]) == 3 and {t["tray_id"] for t in result["trays"]} == {"L", "E", "P"}
    park = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == "blocker"]
    blocker_path = len(park) == 1 and park[0]["from"] == 1 and park[0]["to"] == 9
    choices_complete = [c["job"] for c in continuation["route_choices"]] == ["reuse1", "reuse2"]
    valid = (business and executed and accepted and route_match and same_tray and stock and choices_complete
             and blocker_path and expected == model.JOBS and audit.get("status") == "passed" and continuation["status"] == "finished")
    return {"status": "assessed" if valid else "unknown_incomplete_or_unexecuted", "completion": jobs,
        "completion_sum": sum(jobs.values()) if business else None, "business_complete": business,
        "common_horizon_complete": complete, "required_transfer_lineages_received": executed,
        "all_routes_updated": accepted, "chosen_routes_match_executed_edges": route_match,
        "initial_actual_next": initial[0]["to"] if len(initial) == 1 else None,
        "first_reuse_actual_next": next((c["actual_next"] for c in actual_choices if c["job"] == "reuse1"), None),
        "blocker_actual_path1to9": blocker_path, "same_L_two_returns_and_two_reloads": same_tray, "stock_preserved": stock, "audit": audit,
        "actual_later_choices": actual_choices, "supply_attempt_count": len(line),
        "recovered_rejection_count": len(line) - 1, "recovery_decisions_valid": recovery_ok,
        "transfer_acks": [r.get("ack", {}) for r in supply + returns], "route_acks": [r.get("ack", {}) for r in routes]}


def reference(path):
    return {"path":str(Path(path).resolve()),"sha256":sha(path)}


def json_value(value):
    return json.loads(json.dumps(value,allow_nan=False))


def verify_saved_inputs(raw):
    """Replay supplied endpoint data, never mint online collection authority."""
    require(set(raw["initial_owners"]) == {"A","B"},"initial_owner_domain")
    for owner,saved in raw["initial_owners"].items():
        endpoint = saved["raw_endpoints"]; actual = saved["information"]
        command = endpoint["command"]; own_id = actual["native_read"]["own_request_id"]
        require(command["request_id"] == own_id and command["kind"] == "planning_snapshot","initial_command_binding")
        replay = initial_adapter.validate_pair(endpoint["view"],command["last_delivered_ack"],endpoint["received"])
        require(endpoint["view"] == saved["local_action_view"],"initial_view_binding")
        known = replay["status"] == "conditional_validated_data"
        require(actual.get("native_delivery_verified") is known,"initial_verified_replay")
        if known:
            for field in ("bundle","envelopes","own_delivered_ack","source_capture_pair_sha256"):
                require(actual[field] == json_value(replay[field]),"initial_data_replay:"+field)
        else:
            require(actual.get("reasons") == replay.get("reasons"),"initial_unknown_replay")
    for owner,sequence in raw.get("decisions",{}).items():
        for decision in sequence:
            info = decision["information"]; endpoint = info["raw_endpoints"]; observed = info["native_read"]
            prefix = decision["predecision_call_prefix_count"]
            require(type(prefix) is int and 0 <= prefix <= len(raw["calls"]),"predecision_call_boundary")
            before = raw["calls"][:prefix]
            require(all(c["at"] <= decision["at"] for c in before),"future_prior_call")
            if prefix < len(raw["calls"]):require(raw["calls"][prefix]["at"] >= decision["at"],"call_boundary_before_decision")
            request_id = decision["native_request_id"]
            if request_id is not None:
                require(prefix < len(raw["calls"]) and raw["calls"][prefix]["request"]["request_id"] == request_id,
                        "decision_action_not_at_boundary")
            calls = [c["request"] for c in before if c["request"]["request_id"] == observed["own_request_id"]]
            require(bool(calls) and all(c == calls[0] for c in calls),"missing_or_changed_own_publication")
            actions = {}
            for call in before:
                if call["request"]["owner_id"] == owner and call["kind"] in PHYSICAL_KINDS:
                    key = call["request"]["request_id"]
                    require(key not in actions or actions[key] == call["kind"],"prior_action_kind_changed")
                    actions[key] = call["kind"]
            replay = endpoint_binding.validate_collected_endpoints(endpoint["view"],endpoint["command"],endpoint["received"],
                retained=raw["retained_ledgers"][owner],own_actions=sorted(actions.items()),phase=decision["phase"],
                own_request_id=observed["own_request_id"],peer_message_id=observed["selected_peer_message_id"],
                collection_started_at=observed["collection_started_at"],policy_quiet_since=observed["collection_started_at"],
                own_request=calls[0])
            known = replay["status"] == "conditional_validated_later_v3_data"
            require(info.get("native_delivery_verified") is known,"later_verified_replay")
            require(endpoint["view"] == decision["actual_local_view"],"later_view_binding")
            if known:
                for field in ("bundle","envelopes","own_delivered_ack","endpoint_identity_binding"):
                    require(info[field] == json_value(replay[field]),"later_data_replay:"+field)
            else:
                require(info.get("reasons") == replay.get("reasons") and info.get("bundle") == json_value(replay.get("bundle")),
                        "later_unknown_replay")


def verify_case_artifacts(output,index,master,case_id):
    directory = Path(output)/case_id;plan = read(directory/"preregistered_protocol.json")
    receipt = read(directory/"receipt.json"); rows = read(directory/"branch_ledger.json")
    require(receipt.get("status") in ("all32_assessed","completed_with_unknowns") and receipt["case_id"] == case_id
        and receipt["row_count"] == 32 and receipt["source_changed"] == [] and receipt["source_closure_changed"] == [],"case_not_closed")
    require(receipt["master_index_sha256"] == sha(Path(output)/"master_index.json")
        and receipt["case_plan_sha256"] == index["case_plans"][case_id]["sha256"]
        and receipt["ledger_sha256"] == sha(directory/"branch_ledger.json")
        and receipt["native_binary"] == master["native_binary"],"case_receipt_binding")
    require(receipt["run_acceptance"] == reference(directory/"run_acceptance.json"),"case_acceptance_binding")
    admission = read(directory/"run_acceptance.json")
    require(admission["status"] == "closed_run_acceptance_passed" and admission["active"] is False
        and admission["invalid"] == [] and admission["run_reference"] == index["case_plans"][case_id]
        and admission["contract_reference"] == master["native_contract_reference"]
        and admission["semantic_reference"] == master["semantic_gate_reference"],"case_acceptance_not_closed")
    require(admission["evidence_sha256"] == run_admission.inventory(master["native_contract_reference"],
        master["semantic_gate_reference"],index["case_plans"][case_id]),"case_acceptance_evidence_changed")
    require(set(rows) == set(plan["rows"]),"case_ledger_domain")
    require(len(admission["branch_keys"]) == len(set(admission["branch_keys"]))
        and set(admission["branch_keys"]) <= set(rows),"case_acceptance_branch_domain")
    raw_count = 0
    for key,row in rows.items():
        require(all(row[field] == plan["rows"][key][field] for field in ("case","vector","method","fault")),"case_action_binding")
        item = row.get("raw_artifact")
        if item is None:
            require(row["status"] != "assessed" and "summary" not in row,"assessed_without_raw")
            continue
        raw_path,input_path = directory/(key+".json.gz"),directory/"inputs"/(key+".json")
        require(item == {"path":key+".json.gz","sha256":sha(raw_path),"input_path":"inputs/"+key+".json",
                        "input_sha256":plan["input_file_sha256"][key]},"raw_artifact_binding")
        require(key in admission["branch_keys"] and sha(input_path) == item["input_sha256"],"raw_input_or_branch_binding")
        raw = json.loads(gzip.decompress(raw_path.read_bytes())); raw_count += 1
        require(raw["input"] == read(input_path) and bound.config_sha(raw["input"]) == plan["row_configuration_sha256"][key],"raw_input_changed")
        require(all(raw["specification"][f] == row[f] for f in ("case","vector","method","fault")),"raw_action_binding")
        verify_saved_inputs(raw)
        if "continuation" in raw:
            recomputed = completed_summary(raw["input"],raw["result"],SimpleNamespace(rows=raw["outbox"],calls=raw["calls"]),
                raw["continuation"],row["vector"],raw["initial_owners"],raw["decisions"])
        else:
            require(raw["summary"]["status"] == "unknown_initial_asymmetry_or_missing_ledger","unsupported_missing_continuation")
            recomputed = {"status":"unknown_initial_asymmetry_or_missing_ledger","business_metrics":None}
        require(json_value(recomputed) == raw["summary"] == row["summary"] and row["status"] == recomputed["status"],"raw_summary_replay")
    counts = {s:sum(r["status"] == s for r in rows.values()) for s in {r["status"] for r in rows.values()}}
    require(receipt["status_counts"] == counts,"case_status_counts")
    require((receipt["status"] == "all32_assessed") == all(r["status"] == "assessed" for r in rows.values()),"case_completion_label")
    return {"status":"case_raw_inputs_and_physics_revalidated","raw_count":raw_count,"row_count":32,
            "receipt":reference(directory/"receipt.json")}


def verify_index(output, expected):
    output = Path(output).resolve()
    index_path = output/"master_index.json"
    require(sha(index_path) == expected,"master_index_changed")
    index = read(index_path)
    require(index["schema"] == "g31.native_preference_matrix.index.v1" and index["branch_count"] == 192
        and index["max_workers"] == 1 and index["per_case_seconds"] == 180. and index["total_seconds"] == 1080.,"index_contract")
    require(sha(output/"master_protocol.json") == index["master_protocol_sha256"],"master_protocol_changed")
    master = read(output/"master_protocol.json")
    declared = matrix.matrix_protocol()
    require(all(master[k] == declared[k] for k in declared),"master_domain_or_budget_changed")
    require(list(index["case_plans"]) == master["case_order"],"case_order_changed")
    all_keys = set()
    for case_id, meta in index["case_plans"].items():
        path = output/case_id/"preregistered_protocol.json"
        require(sha(path) == meta["sha256"],"case_plan_changed:"+case_id)
        plan = read(path)
        require(meta == reference(path) and plan["case_id"] == case_id and plan["native_branch_budget"] == 32
            and plan["parent_timeout_seconds"] == 180.,"case_identity_or_budget")
        require(plan["master_protocol_reference"] == reference(output/"master_protocol.json"),"case_master_binding")
        require(set(plan["rows"]) == set(master["case_groups"][case_id]) and
            all(plan["rows"][key] == master["rows"][key] for key in plan["rows"]),"case_row_binding")
        require(plan["source_sha256"] == master["source_sha256"],"case_source_binding")
        all_keys.update(plan["rows"])
    require(all_keys == set(master["rows"]),"master_case_coverage")
    return index, master


def prepare(output, *, binary, contract, semantic_gate, delivery_gate):
    output = Path(output).resolve(); output.mkdir(parents=True,exist_ok=False)
    master = matrix.matrix_protocol()
    sources = bound.imported_sources()
    master["source_sha256"] = {str(p):sha(p) for p in sources}
    master["python_environment"] = {"executable":sys.executable,"version":sys.version,"sha256":sha(sys.executable)}
    master["native_binary"] = reference(binary)
    master["native_contract_reference"] = reference(contract)
    master["semantic_gate_reference"] = reference(semantic_gate)
    old_plan = read(Path(delivery_gate)/"preregistered_protocol.json")
    master["retained_initial_v1_gate"] = bound.require_delivery_gate(delivery_gate,sha(binary),old_plan)
    master["retained_initial_v1_gate_scope"] = "Reuses unchanged bound collector and native027 acceptance. This prior9 gate does not attest new fixed actions or later trajectories. Each new row retains actual initial and later input checks."
    master["delivery_gate_directory"] = str(Path(delivery_gate).resolve())
    write(output/"master_protocol.json",master)
    write(output/"branch_ledger.json",master["rows"])
    root = Path(__file__).resolve().parents[3]
    plans = {}
    for case_id in master["case_order"]:
        directory = output/case_id; directory.mkdir()
        rows = {key:master["rows"][key] for key in master["case_groups"][case_id]}
        plan = {"schema":"g31.native_preference_matrix.case_plan.v1","phase":"fixed_counterfactual_matrix",
            "case_id":case_id,"rows":rows,"master_protocol_reference":reference(output/"master_protocol.json"),
            "source_sha256":master["source_sha256"],"source_archive":{},"input_file_sha256":{},
            "row_configuration_sha256":{},"native_branch_budget":32,"parent_timeout_seconds":180.}
        for source,digest in plan["source_sha256"].items():
            target = directory/"source"/Path(source).relative_to(root)
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(Path(source).read_bytes())
            require(sha(target) == digest,"archive_copy")
            plan["source_archive"][source] = str(target.relative_to(directory))
        for key,row in rows.items():
            target = directory/"inputs"/(key+".json");target.parent.mkdir(parents=True,exist_ok=True)
            data = native_scene(row["case"])
            write(target,data);plan["input_file_sha256"][key] = sha(target)
            plan["row_configuration_sha256"][key] = bound.config_sha(data)
        write(directory/"preregistered_protocol.json",plan);write(directory/"branch_ledger.json",rows)
        plans[case_id] = reference(directory/"preregistered_protocol.json")
    index = {"schema":"g31.native_preference_matrix.index.v1","master_protocol_sha256":sha(output/"master_protocol.json"),
             "case_plans":plans,"branch_count":192,"max_workers":1,"per_case_seconds":180.,"total_seconds":1080.}
    write(output/"master_index.json",index)
    verify_index(output,sha(output/"master_index.json"))
    return index


def case_worker(output, expected_index_sha256, case_id):
    started = time.perf_counter()
    index,master = verify_index(output,expected_index_sha256)
    require(case_id in master["case_order"],"undeclared_case")
    directory = Path(output).resolve()/case_id;plan = read(directory/"preregistered_protocol.json")
    require(set(map(str,bound.imported_sources())) == set(plan["source_sha256"]) and
        all(sha(p) == h for p,h in plan["source_sha256"].items()),"source_closure_changed_before_worker")
    require(sha(master["native_binary"]["path"]) == master["native_binary"]["sha256"],"binary_changed")
    accepted = run_admission.open_run(master["native_contract_reference"],master["semantic_gate_reference"],
        index["case_plans"][case_id])
    rows = copy.deepcopy(plan["rows"])
    try:
        previous_plan = read(Path(master["delivery_gate_directory"])/"preregistered_protocol.json")
        bound.require_delivery_gate(master["delivery_gate_directory"],master["native_binary"]["sha256"],previous_plan)
        native = native_host.load_native(master["native_binary"]["path"])
        require(native._g31_native_artifact_identity["sha256"] == master["native_binary"]["sha256"],"loaded_native_identity")
        semantic = {"status":"passed_actual_native027_semantic_gate","reference":master["semantic_gate_reference"],
                    "validation":copy.deepcopy(accepted._semantic)}
        for key,row in rows.items():
            row["status"] = "unknown_in_progress";write(directory/"branch_ledger.json",rows)
            try:
                verify_index(output,expected_index_sha256)
                path = directory/"inputs"/(key+".json")
                require(sha(path) == plan["input_file_sha256"][key] and
                    bound.config_sha(native_scene(row["case"])) == plan["row_configuration_sha256"][key],"input_changed")
                accepted.enter_branch(key,index["case_plans"][case_id])
                raw = run_branch(native,row,master["native_contract_reference"],semantic,accepted_run=accepted,branch_key=key)
                accepted.finish_branch(key)
                path = directory/(key+".json.gz");path.parent.mkdir(parents=True,exist_ok=True)
                with gzip.open(path,"wt",encoding="utf-8",compresslevel=1) as stream:json.dump(raw,stream,allow_nan=False)
                row.update(status=raw["summary"]["status"],summary=raw["summary"],raw_artifact={"path":key+".json.gz",
                    "sha256":sha(path),"input_path":"inputs/"+key+".json","input_sha256":plan["input_file_sha256"][key]})
            except Exception:
                row.update(status="unknown_failed",exception=traceback.format_exc())
                if accepted.active_for(key):
                    try:accepted.finish_branch(key)
                    except Exception:row["acceptance_error"] = traceback.format_exc()
            write(directory/"branch_ledger.json",rows)
            if accepted._invalid:break
    finally:
        admission = accepted.close()
        write(directory/"run_acceptance.json",admission)
    verify_index(output,expected_index_sha256)
    changed = [p for p,h in plan["source_sha256"].items() if sha(p) != h]
    closure_changed = sorted(set(map(str,bound.imported_sources())) ^ set(plan["source_sha256"]))
    receipt = {"schema":"g31.native_preference_matrix.case_receipt.v1","status":"completed_with_unknowns",
        "case_id":case_id,"row_count":32,"status_counts":{s:sum(r["status"] == s for r in rows.values()) for s in {r["status"] for r in rows.values()}},
        "source_changed":changed,"source_closure_changed":closure_changed,"wall_seconds":time.perf_counter()-started,
        "master_index_sha256":expected_index_sha256,"case_plan_sha256":sha(directory/"preregistered_protocol.json"),
        "ledger_sha256":sha(directory/"branch_ledger.json"),"run_acceptance":reference(directory/"run_acceptance.json"),
        "native_binary":master["native_binary"],"online_model_claim":False,"native_policy_outcome_oracle_used":False}
    if all(r["status"] == "assessed" for r in rows.values()):receipt["status"] = "all32_assessed"
    if changed or closure_changed or admission["status"] != "closed_run_acceptance_passed":receipt["status"] = "invalidated_run_evidence"
    write(directory/"receipt.json",receipt)
    print(json.dumps({k:receipt[k] for k in ("status","case_id","status_counts","wall_seconds")}))


def campaign_worker(output, expected_index_sha256):
    output = Path(output).resolve();index,master = verify_index(output,expected_index_sha256)
    require(not any((output/name).exists() for name in ("parent_receipt.json","parent_progress.json","execution_started.json")),
            "execution_already_recorded")
    require(read(output/"branch_ledger.json") == master["rows"],"master_already_started")
    for case_id in master["case_order"]:
        directory = output/case_id
        require(read(directory/"branch_ledger.json") == {k:master["rows"][k] for k in master["case_groups"][case_id]}
            and not any((directory/name).exists() for name in ("receipt.json","run_acceptance.json","worker.stdout.log","worker.partial.stdout.log"))
            and not list(directory.rglob("*.json.gz")),"case_already_started")
    require(set(map(str,bound.imported_sources())) == set(master["source_sha256"])
        and all(sha(p) == h for p,h in master["source_sha256"].items()),"source_changed_before_parent")
    require(sha(sys.executable) == master["python_environment"]["sha256"]
        and sys.version == master["python_environment"]["version"],"parent_interpreter_changed")
    # Exclusive creation makes a crashed/partial invocation immutable too.
    with (output/"execution_started.json").open("x",encoding="utf-8") as stream:
        json.dump({"master_index_sha256":expected_index_sha256,"started_wall_ns":time.time_ns()},stream)
    started = time.perf_counter();parents = {};rows = copy.deepcopy(master["rows"])
    for case_id in master["case_order"]:
        remaining = master["total_parent_timeout_budget_seconds"] - (time.perf_counter()-started)
        if remaining <= 0:
            parents[case_id] = {"status":"unknown_unexecuted_total_budget"};continue
        command = [sys.executable,"-m",__spec__.name,"--output",str(output),"--expected-index-sha256",expected_index_sha256,
                   "--case-worker",case_id]
        limit = min(master["per_case_parent_timeout_seconds"],remaining)
        tick = time.perf_counter()
        try:
            done = subprocess.run(command,capture_output=True,text=True,timeout=limit)
            (output/case_id/"worker.stdout.log").write_text(done.stdout,encoding="utf-8")
            (output/case_id/"worker.stderr.log").write_text(done.stderr,encoding="utf-8")
            parents[case_id] = {"status":"exited" if done.returncode == 0 else "unknown_failed",
                "exitcode":done.returncode,"wall_seconds":time.perf_counter()-tick,"limit_seconds":limit}
        except subprocess.TimeoutExpired as error:
            parents[case_id] = {"status":"unknown_timeout","wall_seconds":time.perf_counter()-tick,"limit_seconds":limit}
            if error.stdout:(output/case_id/"worker.partial.stdout.log").write_bytes(error.stdout if isinstance(error.stdout,bytes) else error.stdout.encode())
            if error.stderr:(output/case_id/"worker.partial.stderr.log").write_bytes(error.stderr if isinstance(error.stderr,bytes) else error.stderr.encode())
        # Validation is a separate PURE child with only this case's remaining
        # shared180 budget. The outer Windows job owns both descendants.
        elapsed_case = time.perf_counter()-tick
        pure_remaining = min(limit-elapsed_case,master["total_parent_timeout_budget_seconds"]-(time.perf_counter()-started))
        validation_path = output/case_id/"saved_validation.json"
        if parents[case_id]["status"] == "exited" and pure_remaining > 0:
            command = [sys.executable,"-m",__spec__.name,"--output",str(output),"--expected-index-sha256",expected_index_sha256,
                       "--verify-case",case_id]
            try:
                done = subprocess.run(command,capture_output=True,text=True,timeout=pure_remaining)
                (output/case_id/"validation.stdout.log").write_text(done.stdout,encoding="utf-8")
                (output/case_id/"validation.stderr.log").write_text(done.stderr,encoding="utf-8")
                parents[case_id]["validation_process"] = {"exitcode":done.returncode,"limit_seconds":pure_remaining,"native_calls":0}
            except subprocess.TimeoutExpired:
                parents[case_id]["validation_process"] = {"status":"unknown_timeout","limit_seconds":pure_remaining,"native_calls":0}
        parents[case_id]["case_with_validation_wall_seconds"] = time.perf_counter()-tick
        supplied = read(output/case_id/"branch_ledger.json")
        require(set(supplied) == set(master["case_groups"][case_id]),"worker_ledger_domain")
        complete_worker = parents[case_id]["status"] == "exited" and (output/case_id/"receipt.json").exists()
        valid_worker = False
        if complete_worker and parents[case_id].get("validation_process",{}).get("exitcode") == 0 and validation_path.exists():
            try:
                validation = read(validation_path)
                require(validation["status"] == "case_raw_inputs_and_physics_revalidated"
                    and validation["receipt"] == reference(output/case_id/"receipt.json")
                    and validation["master_index_sha256"] == expected_index_sha256,"validation_child_binding")
                parents[case_id]["saved_artifact_validation"] = reference(validation_path)
                valid_worker = True
            except Exception:
                parents[case_id]["saved_artifact_validation"] = {"status":"invalid_saved_artifacts","exception":traceback.format_exc()}
        for key,row in supplied.items():
            require(all(row[field] == master["rows"][key][field] for field in ("case","vector","method","fault")),"worker_row_binding")
            if not valid_worker:
                row = {**row,"observed_partial_status":row["status"],"status":"unknown_case_worker_not_closed"}
            rows[key] = row
        write(output/"branch_ledger.json",rows)
        write(output/"parent_progress.json",{"cases":parents,"elapsed_seconds":time.perf_counter()-started})
    verify_index(output,expected_index_sha256)
    changed = [p for p,h in master["source_sha256"].items() if not Path(p).exists() or sha(p) != h]
    closure_changed = sorted(set(map(str,bound.imported_sources())) ^ set(master["source_sha256"]))
    if changed or closure_changed:
        rows = {key:{**row,"observed_partial_status":row["status"],"status":"unknown_parent_source_drift"} for key,row in rows.items()}
        write(output/"branch_ledger.json",rows)
    comparisons = matrix.compare(rows)
    write(output/"comparisons.json",comparisons)
    write(output/"parent_receipt.json",{"schema":"g31.native_preference_matrix.parent_receipt.v1",
        "status":"invalidated_parent_source_drift" if changed or closure_changed else "bounded_matrix_terminated_preserving_all192",
        "source_changed":changed,"source_closure_changed":closure_changed,"cases":parents,"wall_seconds":time.perf_counter()-started,
        "master_index_sha256":expected_index_sha256,"ledger":reference(output/"branch_ledger.json"),
        "comparisons":reference(output/"comparisons.json"),"native_branch_budget":192,
        "per_case_limit_seconds":180.,"total_limit_seconds":1080.,"max_workers":1,
        "online_model_claim":False,"protected_joint_benefit_claim":False})
    return 1 if changed or closure_changed else 0


def execute(output,expected_index_sha256):
    """Only the bounded outer dispatcher; all heavy work is inside its job."""
    output = Path(output).resolve()
    require(output.is_dir(),"missing_prepared_directory")
    require(not any((output/name).exists() for name in ("bounded_parent_receipt.json","bounded_dispatch.json",
        "parent_receipt.json","parent_progress.json","execution_started.json")),"execution_already_recorded")
    admission = uuid.uuid4().hex
    with (output/"bounded_dispatch.json").open("x",encoding="utf-8") as stream:
        json.dump({"expected_index_sha256":expected_index_sha256,"hard_timeout_seconds":1080.,
                   "per_case_native_and_validation_shared_seconds":180.,"max_native_workers":1},stream)
    command = [sys.executable,"-m",__spec__.name,"--output",str(output),"--expected-index-sha256",expected_index_sha256,
               "--campaign-worker","--parent-admission",admission]
    with (output/"campaign.stdout.log").open("w",encoding="utf-8") as stdout,(output/"campaign.stderr.log").open("w",encoding="utf-8") as stderr:
        result = bounded_windows_job.run(command,timeout=1080.,stdout=stdout,stderr=stderr,admission=admission)
    result.update(schema="g31.native_preference_matrix.bounded_parent.v1",master_index_sha256=expected_index_sha256,
                  campaign_process_completed=result["status"] == "exited" and result["exitcode"] == 0,
                  business_or_protection_claim=False,
                  unknown_partial_results_never_promoted=True)
    write(output/"bounded_parent_receipt.json",result)
    print(json.dumps(result))
    return 0 if result["campaign_process_completed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True);parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--binary",type=Path);parser.add_argument("--native-contract",type=Path)
    parser.add_argument("--semantic-gate",type=Path);parser.add_argument("--delivery-gate",type=Path)
    parser.add_argument("--execute",action="store_true");parser.add_argument("--expected-index-sha256")
    parser.add_argument("--case-worker")
    parser.add_argument("--verify-case");parser.add_argument("--campaign-worker",action="store_true")
    parser.add_argument("--parent-admission")
    args = parser.parse_args()
    if args.prepare:
        if args.execute or args.case_worker or args.verify_case or args.campaign_worker:parser.error("preparation cannot execute")
        if not all((args.binary,args.native_contract,args.semantic_gate,args.delivery_gate)):parser.error("all artifact paths required")
        prepare(args.output,binary=args.binary,contract=args.native_contract,semantic_gate=args.semantic_gate,delivery_gate=args.delivery_gate)
        print(json.dumps({"status":"prepared_no_native","index_sha256":sha(args.output/"master_index.json"),"rows":192}));return
    if not args.expected_index_sha256:parser.error("expected index hash required")
    if sum(bool(x) for x in (args.case_worker,args.verify_case,args.campaign_worker,args.execute)) > 1:parser.error("one execution mode required")
    if args.campaign_worker:
        if not args.parent_admission or sys.stdin.readline().strip() != args.parent_admission:parser.error("missing job assignment admission")
        return campaign_worker(args.output,args.expected_index_sha256)
    elif args.case_worker:case_worker(args.output,args.expected_index_sha256,args.case_worker)
    elif args.verify_case:
        index,master = verify_index(args.output,args.expected_index_sha256)
        result = verify_case_artifacts(args.output,index,master,args.verify_case)
        result["master_index_sha256"] = args.expected_index_sha256
        write(args.output/args.verify_case/"saved_validation.json",result)
    elif args.execute:return execute(args.output,args.expected_index_sha256)
    else:verify_index(args.output,args.expected_index_sha256);print("verified_prepared_no_native")


if __name__ == "__main__":sys.exit(main())


