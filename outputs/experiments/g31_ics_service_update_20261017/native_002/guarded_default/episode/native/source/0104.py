"""Exactly96 fixed native branches, prepared separately from saved pure96.
No candidate optimization, native fork or saved-outcome policy input. Every stage
uses actual current own facts and delivered planning snapshots under an explicit
conditional source-state domain. Pure96 and original airport artifacts unchanged.
"""
from __future__ import annotations
import argparse,copy,gzip,hashlib,json,math,subprocess,sys,time,traceback,uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from . import research_native_preexisting_v3_bound as bound
from . import live_obligation_domain_adapter as adapter
from . import live_obligation_domain_guard as initial_adapter
from . import live_obligation_domain_guard as endpoint_binding
from . import public_live_obligation_projection as construction
from . import live_obligation_native_domain_contract as domain_contract
from . import bounded_windows_job
from .planning_capture_v2_contract import PHYSICAL_KINDS
run_admission=bound.run_admission
native_host=bound.native_host
v1,v2,model=bound.v1,bound.v2,bound.model
LocalTransport=bound.LocalTransport
MAX_ACTIVATIONS=bound.MAX_ACTIVATIONS
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'outputs/experiments/g31_ics_lt2_sustained_20261014'
CASE_ORDER=list(construction.construction.CASE_IDS)
ORDER=[case+f"/vector_{i:02d}" for case in CASE_ORDER for i in range(32)]
BRANCH_COUNT=96
HARD_TIMEOUT=600.
RUNTIME_OVERLAY = {"owner_notifications": {"enabled": True}}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2,allow_nan=False)+'\n',encoding='utf8')
def require(value,why):
    if not value:raise ValueError('live_native_probe:'+why)
def reference(path):return {'path':str(Path(path).resolve()),'sha256':sha(path)}
def probe_rows():
    return domain_contract.rows()
def native_scene(case,fault=None):
    require(case in CASE_ORDER and fault is None,'undeclared_scene')
    data = copy.deepcopy(initial_adapter.public_input(case))
    require(not set(data).intersection(RUNTIME_OVERLAY), 'overlay_already_present')
    data.update(copy.deepcopy(RUNTIME_OVERLAY))
    validate_runtime_input(data)
    return data

def validate_runtime_input(data):
    """Only the declared observer overlay may differ from frozen physical input."""
    require(type(data) is dict, 'runtime_input_shape')
    notification = data.get('owner_notifications')
    require(type(notification) is dict and set(notification) == {'enabled'}
            and notification['enabled'] is True, 'runtime_notification_overlay')
    physical = copy.deepcopy(data); del physical['owner_notifications']
    matches=[case for case in CASE_ORDER if initial_adapter.canonical(physical)==initial_adapter.canonical(initial_adapter.public_input(case))]
    require(len(matches)==1, 'runtime_physical_input_changed')
    require(initial_adapter.canonical(initial_adapter.model.public_contract(data)) == initial_adapter.canonical(initial_adapter.supported_contract(case=matches[0])),
            'runtime_public_contract_changed')
    return physical

def return_earliest(now, alternative, return_index):
    """The frozen .5 label means absolute not-before7.84, never now+.5."""
    require(type(now) in (int,float) and math.isfinite(now) and 0<=now<=v1.HORIZON,'return_clock')
    require(type(alternative) in (int,float) and alternative in (0.,.5),'return_alternative')
    require(type(return_index) is int and return_index in (0,1),'return_index')
    require(return_index==0 or alternative==0.,'second_return_must_be_immediate')
    if alternative==0.:return now
    return max(now,construction.PROTOCOL['first_return_not_before'])

def capture_partial(progress, error):
    """Read the current failed session once; never advance or reconstruct it."""
    raw = {'partial': True, 'exception': error, 'capture_errors': {},
           'summary': {'status': 'unknown_failed_partial', 'business_metrics': None,
                       'strict_protected': None, 'current_state_certified': False}}
    def take(name, callback):
        # NativeCollectedV3 is a dict subclass whose private attributes bind
        # live authority/session capabilities. Serialize mapping data only;
        # never copy or reconstruct those attributes into offline evidence.
        try: raw[name] = json_value(callback())
        except Exception: raw['capture_errors'][name] = traceback.format_exc()
    for field in ('specification', 'input', 'initial_owners', 'native_batches', 'result'):
        if field in progress: take(field, lambda field=field: progress[field])
    raw['failure_stage'] = progress.get('stage', 'before_session_creation')
    session = progress.get('session')
    if session is not None:
        take('physical_time', lambda: session.physical_time)
        # result_at calls advance_to even at the same timestamp; do not invoke
        # it after an exception. offline_diagnostics is a const native getter.
        take('offline_diagnostics', lambda: session.offline_diagnostics())
        take('physical_time_after_diagnostics', lambda: session.physical_time)
    raw['result_capture_rule'] = 'only_preexisting_result; result_at_not_called_after_exception'
    client = progress.get('client')
    if client is not None:
        for name, attr in (('calls','calls'), ('outbox','rows'), ('request_creations','creations'),
                           ('owner_activation_admissions','roots'), ('ack_handling','ack_handling')):
            take(name, lambda attr=attr: getattr(client, attr))
    if 'ledgers' in progress:
        take('retained_ledgers', lambda: {o: l.audit_copy() for o,l in progress['ledgers'].items() if l is not None})
    if 'policies' in progress:
        for name, attr in (('decisions','decisions'), ('exchanges','exchanges'), ('collection_policy_intervals','quiet_periods')):
            take(name, lambda attr=attr: {o:getattr(p, attr) for o,p in progress['policies'].items()})
    return raw


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
    def return_tray(self, view, tray, demand, delay, causal):
        index=len(self.returns);earliest=return_earliest(view['now'],delay,index)
        identity=self.client.submit('A','transfer',f'return-{index}',causal=causal,
            tray_id='L',source=6,destination=7,earliest_departure=earliest,
            expiry=v1.HORIZON-1.,message_delay=.01)
        self.returns.append({'at':view['now'],'request_id':identity,'tray':copy.deepcopy(tray),
            'delivered_demand':copy.deepcopy(demand),'selected_delay':delay,
            'earliest_departure':earliest,'action_semantics':'first .5=absolute_not_before_public7.84; second immediate'})
        return identity

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
        require(vector in [r["vector"] for r in probe_rows().values()],"undeclared_probe_vector")
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
    progress = {'specification': copy.deepcopy(row)}
    try:
        return _run_branch(native, row, contract_reference, semantic_gate_binding,
                           accepted_run=accepted_run, branch_key=branch_key, progress=progress)
    except Exception:
        return capture_partial(progress, traceback.format_exc())

def _run_branch(native, row, contract_reference, semantic_gate_binding, *, accepted_run, branch_key, progress):
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
    progress.update(input=data, stage='native_session_constructor')
    session = native.NativeSession(data)
    progress.update(session=session, stage='runtime_admission')
    admission, accepted = adapter.bind_native027(native, session, contract_reference, accepted_run=accepted_run, branch_key=branch_key)
    if accepted is None: raise ValueError("preexisting_v3:runtime_acceptance_rejected:" + str(admission))
    session.advance_to(.05)
    client = LocalTransport(session); channels, planning = {}, {}
    progress.update(client=client, stage='initial_publications')
    for owner, peer in (("A", "B"), ("B", "A")):
        client.activate(owner, {"kind": "initial_public_epoch", "at": .05})
        channels[owner] = client.submit(owner, "demand", "seed-demand", target_owner=peer, message_delay=.01, publication_delay=.01)
        planning[owner] = client.submit(owner, "planning_snapshot", "initial-planning", target_owner=peer,
            message_delay=.01, publication_delay=.1 if row.get("fault") == "missing_peer" and owner == "A" else .01,
            expiry=.08 if row.get("fault") == "expired_capture" else .21)
    session.advance_to(v1.START)
    ledgers, initial_owners = {}, {}
    progress.update(ledgers=ledgers, initial_owners=initial_owners, stage='initial_owner_collection')
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
    progress.update(policies=policies, native_batches=batches, stage='owner_notification_continuation')
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
    progress.update(result=result, stage='complete_assessment')
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
                and request["request"]["earliest_departure"] == return_earliest(record["at"],record["selected_delay"],index)
                for index,(record,request) in enumerate(zip(continuation["returns"],returns,strict=True))))
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
    blocker_path = [(r["from"],r["to"]) for r in park] == [(1,9),(9,3),(3,10)]
    stores=[r for r in receipts if r["event"]=="STORAGE_ENTER" and r["business_bag_id"]=="blocker"]
    releases=[r for r in receipts if r["event"]=="STORAGE_RELEASE" and r["business_bag_id"]=="blocker"]
    blocker_contract=next(j for j in data['jobs'] if j['business_bag_id']=='blocker')
    blocker_path=blocker_path and len(stores)==len(releases)==1 and stores[0]["node"]==releases[0]["node"]==9 and stores[0]["time"]<=releases[0]["time"]==max(blocker_contract['storage_release_at'],stores[0]['time']+blocker_contract['storage_min_dwell'])
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

def json_value(value):
    return json.loads(json.dumps(value,allow_nan=False))

def verify_partial(raw):
    require(raw.get('partial') is True and raw.get('summary', {}).get('status') == 'unknown_failed_partial', 'partial_unknown')
    require(raw['summary'].get('strict_protected') is None and raw['summary'].get('business_metrics') is None, 'partial_no_business_claim')
    require(type(raw.get('exception')) is str and bool(raw['exception']), 'partial_exception')
    if 'input' in raw: validate_runtime_input(raw['input'])
    for field in ('physical_time', 'physical_time_after_diagnostics'):
        if field in raw: require(type(raw[field]) in (int,float) and math.isfinite(raw[field]) and raw[field]>=0, 'partial_physical_time')
    if 'physical_time' in raw and 'physical_time_after_diagnostics' in raw:
        require(raw['physical_time'] == raw['physical_time_after_diagnostics'], 'partial_diagnostic_advanced_time')
    require(raw.get('result_capture_rule') == 'only_preexisting_result; result_at_not_called_after_exception', 'partial_result_rule')
    # Verify complete already-recorded endpoint collections when available.
    # Missing intermediate collections remain absent, never synthesized.
    if set(raw.get('initial_owners', {})) == {'A','B'}:
        verify_saved_inputs(raw)
        return 'passed_available_endpoint_replay; remaining_lifecycle_unknown'
    return 'partial_endpoint_collection_not_complete; unknown'

def verify(output,plan):
    require(plan['rows']==probe_rows() and plan['branch_order']==ORDER and plan['native_branch_budget']==BRANCH_COUNT and plan['hard_timeout_seconds']==HARD_TIMEOUT,'plan_domain')
    domain_contract.validate_rows(plan['rows'])
    require(set(plan['source_sha256'])==set(map(str,bound.imported_sources())),'import_closure')
    for path,digest in plan['source_sha256'].items():require(sha(path)==sha(output/plan['source_archive'][path])==digest,'source_pin')
    for key in ORDER:
        p=output/'inputs'/(key+'.json');require(sha(p)==plan['input_file_sha256'][key] and read(p)==native_scene(plan['rows'][key]['case']),'input_pin')
        validate_runtime_input(read(p))
    require(plan.get('runtime_overlay') == RUNTIME_OVERLAY, 'declared_runtime_overlay')
    for ref in (plan['native_contract_reference'],plan['semantic_gate_reference']):require(sha(ref['path'])==ref['sha256'],'runtime_reference_pin')
    require(sha(plan['binary']['path'])==plan['binary']['sha256'],'binary_pin')
    for ref in plan['auxiliary_references'].values():require(sha(ref['path'])==ref['sha256'],'auxiliary_pin')

def prepare(output):
    require(not output.exists(),'immutable_output')
    suite=ET.parse(OUT/'live_native_domain_pure_001.xml').getroot().findall('testsuite')
    require(len(suite)==1 and all(int(suite[0].get(k,'-1'))==v for k,v in {'tests':38,'failures':0,'errors':0,'skipped':0}.items()),'expected38_pure_checks')
    output.mkdir(parents=True)
    sources=list(map(Path,bound.imported_sources()));source_sha={str(p):sha(p) for p in sources};archives={}
    for p in sources:
        dest=output/'source'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes());archives[str(p)]=str(dest.relative_to(output))
    contract=OUT/'native027_accepted_contract_001.json';semantic=OUT/'native027_semantic_native_002/receipt.json';accepted=read(contract)
    plan={'schema':'g31.live_obligation_native_fixed96.v1','case_order':CASE_ORDER,'branch_order':ORDER,'rows':probe_rows(),'native_branch_budget':BRANCH_COUNT,'hard_timeout_seconds':HARD_TIMEOUT,
        'input_file_sha256':{},'source_sha256':source_sha,'source_archive':archives,'binary':reference(accepted['binary']),
        'native_contract_reference':reference(contract),'semantic_gate_reference':reference(semantic),'interpreter':reference(sys.executable),
        'same_frozen_input':'Removing the exact declared runtime overlay yields each corresponding frozen pure003 input. Runtime bytes differ; no topology/service/capacity/action/clock retuning.',
        'runtime_overlay':copy.deepcopy(RUNTIME_OVERLAY),
        'overlay_source_scope':{'owner_notifications.enabled':'Observer notification sequence/time/mask and notification-boundary API opt-in only. Accepted027 notify_owner/notify_node update observer map; they do not edit graph, jobs, trays, reservations, event heap or native clock. The enabled policy now receives notices as preregistered; no assertion of identical controller behavior to failed001.',
            'monitoring_other_changes':None, 'existing_options_unchanged':['max_events','max_simulation_time','trace_limit'],
            'checkpoint_bytes_equal':False, 'runtime_input_equal_pure_bytes':False},
        'authority':'Native027 actual21+44 accepted. Native026 archived physical/immutable retry source is historical authority; v3 collection runs027 only.',
        'method':'All three predeclared cases x32 fixed counterfactual actions, no online optimization/native oracle. Current owned+actual delivered snapshots gate every first action. Existing public-model coordinate_strict/plateau/pair/MPC selections and their32-query budgets are mapped to actual fixed outcomes only after execution.',
        'first_return_action_semantics':{'0.0':'immediate at actual current decision','0.5':'max(actual decision time, public frozen first_return_not_before)',
            'first_return_not_before':construction.PROTOCOL['first_return_not_before'],'second_return':'immediate; .5 forbidden','source':'unchanged public_live_obligation_projection.PROTOCOL/Projection.tick absolute alternative; old three probes used only0.'},
        'timing':'Initial .11; first available return+normal actual pair exchange; loading-triggered immutable preflight retry; first reuse load+actual pair exchange; wire.01/ACK.02 unchanged. No post-failure retiming. Every actual mismatch with frozen predicted epochs remains recorded.',
        'information':'Exact three public graph+complete job-contract combinations; case identified from delivered contracts, never a case label or hidden outcome. All existing typed digest/source/currentown/ACK-union/stable interval guards remain. Supported lifecycle is deliberately unchanged; missing completed-prefix/state support stays unknown rather than silently broadened.',
        'loading_capture_correction':'Only stationary E loading may have future available_at, exactly equal to observed load_complete_at and service_ready_at>now, with observed_load_completion/known service and derived start<=capture union. All other tray availability remains finite nonnegative <=union floor. Native003 actual first-return fallback remains unknown; no historical receipt promotion.',
        'full96_native':'Exactly96 slots. Both16-member reference families require every member plus incumbent assessed. Complete32 optimum requires all32 assessed. An attempted or physically finished but information-invalid row remains unknown. Not a general online policy.',
        'cost_scope':'One600s ownedchild includes imports/prechecks/closed44+21 entry/96native branches/all branchpins/replay+physicalaudit/saved fixed-model method mapping/44+21 exit/output. Whole externalPythonwall separately. No100ms claim.',
        'budget_derivation':{'source_attempt':'live_obligation_native_probe_prepare_004','worker_seconds':27.447271900004125,
            'fixed_entry_exit_and_final_pin_seconds':20.32999550000386,'remaining_three_branch_and_harness_seconds':7.117276400000265,
            'linear_96_estimate_seconds':248.08284030001233,'shared_hard_seconds':HARD_TIMEOUT,
            'limitation':'Extrapolation only; diverse rows may differ. No extension or selective restart; unfinished slots stay unknown.'},
        'failure_rule':'Missing/refused/expired/asymmetric/censored capture or action remains unknown; raw physical completion does not erase missing information. Exceptions capture actual current input/time/calls/outbox/collected endpoints/decisions and const offline diagnostics; no post-exception advance/result_at, reconstruction, branch or parameter change.',
        'common_horizon':40.,'strict_protection_tolerance':0.,'native_forks':0,'max_native_workers':1,
        'auxiliary_references':{name:reference(path) for name,path in {
            'pure_tests':OUT/'live_native_domain_pure_001.xml',
            'pure_test_source':ROOT/'tests/test_g31_circulation_live_obligation_native_domain.py',
            'frozen_pure96_plan':OUT/'live_obligation_projection_prepare_003/preregistered_protocol.json',
            'frozen_input':OUT/'live_obligation_projection_prepare_003/mechanism.input.json',
            'frozen_no_overlap_input':OUT/'live_obligation_projection_prepare_003/no_overlap.input.json',
            'frozen_insufficient_advance_input':OUT/'live_obligation_projection_prepare_003/insufficient_advance.input.json',
            'frozen_model_comparisons':OUT/'live_obligation_projection_prepare_003/comparisons.json',
            'native004_readback':OUT/'live_obligation_native_saved_review_004.json',
            'native004_receipt':OUT/'live_obligation_native_probe_prepare_004/receipt.json',
            'native004_acceptance':OUT/'live_obligation_native_probe_prepare_004/run_acceptance.json',
            'source_timing_review':OUT/'live_obligation_causal_review_001.json',
            'failed001_readback':OUT/'live_obligation_native_failed_readback_001.json',
            'native003_readback':OUT/'live_obligation_native_saved_review_003.json',
            'native003_vector12':OUT/'live_obligation_native_probe_prepare_003/mechanism/vector_12.json.gz',
            'native003_vector24':OUT/'live_obligation_native_probe_prepare_003/mechanism/vector_24.json.gz',
            'native003_vector25':OUT/'live_obligation_native_probe_prepare_003/mechanism/vector_25.json.gz',
            'native026_build_authority':OUT/'native026_build_001/receipt.json'}.items()}}
    require(read(plan['auxiliary_references']['frozen_input']['path'])==validate_runtime_input(native_scene('mechanism')),'frozen_parameters')
    for case in CASE_ORDER:
        require(read(OUT/'live_obligation_projection_prepare_003'/(case+'.input.json'))==validate_runtime_input(native_scene(case)),'frozen_case_parameters')
    for key in ORDER:
        p=output/'inputs'/(key+'.json');p.parent.mkdir(parents=True,exist_ok=True);write(p,native_scene(plan['rows'][key]['case']));plan['input_file_sha256'][key]=sha(p)
    write(output/'preregistered_protocol.json',plan);verify(output,plan)
    write(output/'prepare_receipt.json',{'status':'prepared_unexecuted','plan_sha256':sha(output/'preregistered_protocol.json'),'source_count':len(sources),'native_executions':0,
        'launch_command':[sys.executable,'-m','scripts.experiments.g31_ics_circulation.research_live_obligation_native_domain','--launch','--output',str(output)]})
    return {'status':'prepared_unexecuted','plan_sha256':sha(output/'preregistered_protocol.json'),'source_count':len(sources),'output':str(output)}

def comparisons(rows,plan):
    source=plan['auxiliary_references']['frozen_model_comparisons']
    require(sha(source['path'])==source['sha256'],'model_selection_reference')
    return domain_contract.compare(rows,read(source['path']))

def worker(output):
    started=time.perf_counter();plan=read(output/'preregistered_protocol.json');require(sha(output/'preregistered_protocol.json')==read(output/'prepare_receipt.json')['plan_sha256'],'plan_identity');verify(output,plan)
    campaign=reference(output/'preregistered_protocol.json');accepted=run_admission.open_run(plan['native_contract_reference'],plan['semantic_gate_reference'],campaign)
    rows=copy.deepcopy(plan['rows']);order=[];write(output/'branch_ledger.json',rows)
    try:
        native=bound.load_native(Path(plan['binary']['path']))
        for key in ORDER:
            row=rows[key];row['status']='unknown_in_progress';row['execution_index']=len(order);write(output/'branch_ledger.json',rows)
            try:
                accepted.enter_branch(key,campaign)
                raw=run_branch(native,row,plan['native_contract_reference'],plan['semantic_gate_reference'],accepted_run=accepted,branch_key=key)
                path=output/(key+'.json.gz');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(gzip.compress(json.dumps(raw,allow_nan=False).encode(),compresslevel=1,mtime=0))
                row['raw_artifact']=reference(path);row['summary']=raw['summary'];row['status']=raw['summary']['status']
                accepted.finish_branch(key)
                saved=json.loads(gzip.decompress(path.read_bytes()))
                if saved.get('partial') is True:
                    row['saved_prefix_replay']=verify_partial(saved)
                else:
                    verify_saved_inputs(saved)
                if saved.get('partial') is not True and 'continuation' in saved:
                    rebuilt=completed_summary(saved['input'],saved['result'],SimpleNamespace(rows=saved['outbox'],calls=saved['calls']),saved['continuation'],row['vector'],saved['initial_owners'],saved['decisions'])
                    require(rebuilt==saved['summary'],'replayed_complete_assessment')
                row['saved_replay']='partial_only_unknown' if saved.get('partial') is True else 'passed'
            except Exception:
                row['status']='unknown_failed';row['exception']=traceback.format_exc()
                if accepted.active_for(key):
                    try:accepted.finish_branch(key)
                    except Exception:row['acceptance_error']=traceback.format_exc()
            order.append(key);write(output/'branch_ledger.json',rows)
    finally:
        closed=accepted.close();write(output/'run_acceptance.json',closed)
    verify(output,plan);require(order==ORDER,'actual_order')
    receipt={'schema':'g31.live_obligation_native_fixed96_receipt.v1','status':'complete96_assessed' if all(r['status']=='assessed' for r in rows.values()) else 'completed_with_unknowns',
        'plan_sha256':sha(output/'preregistered_protocol.json'),'branch_order':order,'branch_count':BRANCH_COUNT,'ledger_sha256':sha(output/'branch_ledger.json'),
        'source_changed':[],'run_acceptance':reference(output/'run_acceptance.json'),'run_acceptance_status':closed['status'],
        'comparisons':comparisons(rows,plan) if closed['status']=='closed_run_acceptance_passed' else None,
        'worker_wall_seconds':time.perf_counter()-started,'native_branch_attempts':len(order),
        'full96_reference_assessed':closed['status']=='closed_run_acceptance_passed' and all(domain_contract.known(r) for r in rows.values()),
        'online_optimizer_claim':False,'complete_request_100ms_certified':False}
    if closed['status']!='closed_run_acceptance_passed':receipt['status']='invalidated_runtime_evidence'
    write(output/'receipt.json',receipt)

def launch(output):
    require(not (output/'external_process.json').exists() and not (output/'receipt.json').exists(),'attempt_already_started')
    token=uuid.uuid4().hex;started=time.perf_counter()
    command=[sys.executable,'-m','scripts.experiments.g31_ics_circulation.research_live_obligation_native_domain','--worker','--output',str(output),'--admission',token]
    with (output/'stdout.log').open('w') as stdout,(output/'stderr.log').open('w') as stderr:
        result=bounded_windows_job.run(command,timeout=HARD_TIMEOUT,stdout=stdout,stderr=stderr,admission=token,cwd=str(ROOT))
    write(output/'external_process.json',{**result,'command':command,'parent_post_import_wall_seconds':time.perf_counter()-started})
    if result['status']!='exited' or result['exitcode']!=0:raise SystemExit(1)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--admission')
    modes=parser.add_mutually_exclusive_group(required=True);modes.add_argument('--prepare',action='store_true');modes.add_argument('--launch',action='store_true');modes.add_argument('--worker',action='store_true')
    args=parser.parse_args();args.output=args.output.resolve()
    if args.prepare:print(json.dumps(prepare(args.output)))
    elif args.launch:launch(args.output)
    else:
        if not args.admission or sys.stdin.readline().strip()!=args.admission:raise ValueError('owned_job_admission_required')
        try:worker(args.output)
        except Exception:
            write(args.output/'failure.json',{'status':'failed','error':traceback.format_exc()});raise
