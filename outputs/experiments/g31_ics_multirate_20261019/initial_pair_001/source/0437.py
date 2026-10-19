"""New finite public-model rolling comparison; no native forks or outcome inputs.

Copied scheduling/physical assessment paths remain explicit in this module;
no old module globals are replaced. Initial and later choice alone change.
All accepted message, identity, current-local and capture-union guards remain.
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
from . import research_native_preference_matrix as matrix_runner
from . import research_native_preexisting_v3_bound as bound
from . import native_public_preference_policy as policy
from . import bounded_windows_job

adapter=bound.adapter
run_admission=bound.run_admission
native_host=bound.native_host
v1,v2,model=bound.v1,bound.v2,bound.model
domain=bound.domain
delivery_evidence=bound.delivery_evidence
LocalTransport=bound.LocalTransport
native_scene=bound.native_scene
MAX_ACTIVATIONS=bound.MAX_ACTIVATIONS
METHODS=policy.METHODS
sha=bound.sha
write=bound.write
config_sha=bound.config_sha
imported_sources=bound.imported_sources
load_native=bound.load_native


def protocol(phase='delivery_gate'):
    value=bound.protocol(phase)
    if phase=='business':
        value['rows']={case['case_id']+'/'+method:{'case':case,'method':method,'fault':None,'status':'unknown_unexecuted'}
                       for case in domain.cases() for method in METHODS}
    value.update(schema='g31.lt2.native_public_preference.v1',native_branch_budget=len(value['rows']),
        row_configuration_sha256={key:config_sha(native_scene(row['case'],row['fault'])) for key,row in value['rows'].items()},
        initial_action='Actual native_default emits no route request and promises no next edge; prefer_2 submits a current local immutable preference. E transfer uses the selected public earliest-departure window.',
        fixed_initial_family='Four separately executed native_default initial-route arms, one for each public E window; all four current later return/route actions remain available at the same budget.',
        initial_budget=32,later_budget=4,
        later_action_domain=[{'return_delay':delay,'later_action':action} for delay in (0.,.5) for action in ('native_default','prefer_8')],
        incumbent='Initial native_default/E earliest public window, first return0 and later native_default; same collection and actual-input gates.',
        late_ablation='Pair-repair search with the same32/4 evaluation caps, but only candidates with later native_default selectable. No explicit3 request for first reuse; second reuse unchanged explicit3.',
        unsupported='All old actual v3 capture/coverage/age/action-union guards remain. Additional current-owned action endpoint facts are required; no pending action or terminal ACK at/after earliest capture. Missing facts retain common fallback return0/native_default and unknown status.',
        objective='Exact point-estimated all-five-job non-regression versus the same-stage incumbent, then completion-sum/key order; physical strict protection assessed only from matched complete actual branches.',
        model_scope='Public initial snapshot and current source-authored later snapshot only. Future normal-delivery collection remains conditional; completed prefix is immutable and phaseB cannot change the already executed first return.',
        fixed_method_later='resource_pair_repair over all four later actions, same observations and cap as the free-initial methods',
        prospective_status='New actual online execution has not been established by the retrospective192 debugging/conformance corpus.',
        timing='Every search validates/prepares and times its own32/4 candidate evaluations; raw timing retained. No100ms or exhaustive business-request accounting claim.',
        physical_assessment='CommonH40, all5 actual completions, 3tray physical audit, allnative terminal ACKs, actual preference edges, native-default edges recorded without a forced-next claim, two same-L returns/reloads.',
        hard_timeout_seconds=180.,
        budget_scope='Whole worker tree: frozen-input/source/44+21 entry checks, nine delivery raw revalidation for business, all native branches, gzip/raw validation,44+21 exit and final receipt. JobObject timeout kills owned tree; any absent final artifact remains unknown.',
        copied_continuation='Explicit copied native scheduler and OwnerPolicy methods; inherited transport/collection/recovery and second reuse from archived bound runner; no module-global monkeypatch.')
    return value


def completed_summary(data,result,client,continuation,initial_action,initial_owners,decisions):
    flat=[d for rows in decisions.values() for d in rows]
    phases={phase:[d for d in flat if d['phase']==phase] for phase in ('first_return','first_reuse_route')}
    selected=copy.deepcopy(initial_action)
    selected['return_delay']=(phases['first_return'][0]['executed_first_action']['return_delay']
                              if len(phases['first_return'])==1 else 0.)
    selected['later_action']=('prefer_8' if len(phases['first_reuse_route'])==1
        and phases['first_reuse_route'][0]['executed_first_action']['reuse_next']==8 else 'native_default')
    summary=matrix_runner.assess_cell(data,result,client,continuation,selected)
    summary['executed_stage_specification']=selected
    summary['rolling_model_inputs_verified']=len(flat)==2 and all(d['information'].get('native_delivery_verified') is True for d in flat)
    summary['rolling_fallback_count']=sum(d['fallback_used'] for d in flat)
    summary['rolling_action_count']=sum(d['native_request_id'] is not None for d in flat)
    summary['all_required_inputs_verified']=summary['rolling_model_inputs_verified'] and all(
        initial_owners[o]['information'].get('native_delivery_verified') is True for o in ('A','B'))
    summary['selected_actions_executed']=summary['status']=='assessed' and all(len(rows)==1 for rows in phases.values()) and all(
        d.get('selected_action_admitted') is True and not d['fallback_used'] for d in flat)
    if not summary['all_required_inputs_verified'] or not summary['selected_actions_executed']:
        summary['status']='unknown_missing_input_or_unexecuted_online_action'
    summary.update(conditional_stability_only=True,current_state_certified=False,native_model_protection_certified=False,
        online_policy_scope='actual owner-scoped native inputs and first-action submissions; no atomic joint agreement or unseen model-error certificate')
    summary['prediction_errors']=[{'phase':d['phase'],'status':d['decision'].get('status'),
        'native_minus_selected_prediction':{job:summary['completion'][job]-value for job,value in
            (d['decision'].get('selected_prediction') or {}).get('completion',{}).items()} if summary['business_complete'] else None} for d in flat]
    proposals=[r.get('proposal',{}) for r in initial_owners.values()]+[d['decision'] for d in flat]
    summary['search_costs']=[{'stage':p.get('stage'),'method':p.get('method'),'evaluations':p.get('evaluations'),
        'evaluation_budget':p.get('evaluation_budget'),'proposal_wall_seconds':p.get('proposal_wall_seconds')} for p in proposals]
    summary['search_cost_scope']='Actual proposal envelopes only; not complete business-request cost'
    return summary


def assess(rows,phase):
    declared=protocol(phase)['rows']
    if set(rows)!=set(declared) or any(any(row.get(f)!=declared[key][f] for f in ('case','method','fault')) for key,row in rows.items()):
        return {'status':'unknown_incomplete_or_misbound_denominator','expected_rows':len(declared),'observed_rows':len(rows)}
    if phase=='delivery_gate':return bound.assess(rows,phase)
    def valid(row):
        s=row.get('summary',{});c=s.get('completion',{})
        return (row.get('status')=='assessed' and s.get('business_complete') is True and s.get('common_horizon_complete') is True
            and s.get('all_required_inputs_verified') is True and s.get('selected_actions_executed') is True
            and s.get('audit',{}).get('status')=='passed' and set(c)==model.JOBS
            and all(type(t) in (int,float) and math.isfinite(t) and 0<=t<=40. for t in c.values())
            and s.get('completion_sum')==sum(c.values()))
    result={}
    for case in domain.cases():
        group={m:rows[case['case_id']+'/'+m] for m in METHODS};base=group['incumbent']
        fixed=[group[f'fixed_window_{i}'] for i in range(4)]
        family=valid(base) and all(valid(row) for row in fixed)
        protected=[r for r in fixed if family and all(r['summary']['completion'][j]<=base['summary']['completion'][j] for j in model.JOBS)]
        strongest=min(protected,key=lambda r:r['summary']['completion_sum'],default=None)
        comparisons={}
        for method,row in group.items():
            known=valid(row) and valid(base);s=row.get('summary',{})
            comparisons[method]={'status':'assessed' if known else 'unknown','completion':s.get('completion',{}),
                'strict_protected_vs_incumbent':all(s['completion'][j]<=base['summary']['completion'][j] for j in model.JOBS) if known else None,
                'gain_vs_incumbent':base['summary']['completion_sum']-s['completion_sum'] if known else None,
                'strict_protected_vs_complete_finite_fixed_family':all(s['completion'][j]<=strongest['summary']['completion'][j] for j in model.JOBS) if known and strongest else None,
                'gain_vs_complete_finite_fixed_family':strongest['summary']['completion_sum']-s['completion_sum'] if known and strongest else None,
                'all_later_inputs_verified':s.get('rolling_model_inputs_verified'),'fallback_count':s.get('rolling_fallback_count')}
        result[case['case_id']]={'all_offered_count':5,'complete_fixed_family':family,'methods':comparisons,
            'no_native_model_protection_certificate':True}
    return result

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
        decision = policy.later(information,self.method)
        call_prefix_count = len(self.client.calls)
        selected = decision.get("selected_action"); fallback = selected is None
        action = ({"reuse_next":8 if selected["later_action"] == "prefer_8" else None,
            "return_delay":selected["return_delay"]} if selected else {"reuse_next":None,"return_delay":0.})
        causal = {"relation":"fallback" if fallback else "result_handling", "continuation_parent_roots":[pending["root"]],
            "predecessor_protocol_id":pending["request_id"],"delivered_peer_message_id":pending["peer_message"],
            "collection_started_at":pending["at"],"public_model_method":self.method}
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

def owner_first_action(native,session,client,owner,planning_id,method,accepted):
    information,ledger,proposal = policy.initial(native,session,owner,planning_id,accepted,method)
    vector=proposal.get("selected_action")
    view = session.observe_protocol(owner); identity = None; action = None; admitted = False
    endpoints = {"view":copy.deepcopy(view),"command":session.protocol_command(owner,planning_id),
                 "received":session.protocol_planning_snapshots(owner)}
    decision = {"status":"unknown_unverified_initial_input","selected_action":None}
    if information.get("native_delivery_verified") and vector is not None:
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
                            "public_model_method":method})
                    admitted = True
        else:
            tray = next((t for t in view["trays"] if t["tray_id"] == "E" and t["node"] == 5 and t["mode"] == "empty"
                and t["edge_to"] < 0 and t["available_at"] <= view["now"]),None)
            if tray:
                identity = client.submit(owner,"transfer","initial-supply",tray_id="E",source=5,destination=1,
                    earliest_departure=vector["empty_departure"],expiry=39.,message_delay=.01,
                    causal={"relation":"result_handling","predecessor_protocol_id":planning_id,
                        "continuation_parent_roots":[client.creations[planning_id]["creating_root"]],
                        "public_model_method":method})
                admitted = True
        decision = {"status":"conditional_public_model_first_action_admitted" if admitted else "unknown_local_action_precondition",
            "selected_action":action if admitted else None, "actual_next":None,
            "native_default_no_command":owner == "A" and vector["initial_action"] == "native_default" and admitted}
    return {"owner":owner,"at":view["now"],"information":information,"decision":decision,"proposal":proposal,
        "native_request_id":identity,"local_action_view":view,"raw_endpoints":endpoints},ledger

def run_branch(native, row, contract_reference, semantic_gate_binding, *, accepted_run, branch_key):
    if type(accepted_run) is not run_admission.RunAcceptance or not accepted_run.active_for(branch_key):
        raise ValueError("preexisting_v3_run:inactive_run_or_branch")
    declared = accepted_run.branch_specification(branch_key)
    if any(row.get(field) != declared.get(field) for field in ("case", "method", "fault")):
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
            initial_owners[owner], ledgers[owner] = owner_first_action(native, session, client, owner, planning[owner], row["method"], accepted)
    if row["method"] == "delivery_only":
        return {"specification": row, "input": data, "initial_owners": initial_owners, "calls": client.calls, "outbox": client.rows,
            "summary": {"status": "readiness_observed", "both_inputs_verified": all(r["information"].get("native_delivery_verified") for r in initial_owners.values()),
                "owner_status": {o: r["information"]["status"] for o, r in initial_owners.items()}, "business_metrics": None, "physical_protection": "not_assessed"}}
    selections = {o: value["decision"].get("selected_action") for o, value in initial_owners.items()}
    if any(ledgers[o] is None or selections[o] is None for o in ("A", "B")) or selections["A"] != selections["B"]:
        session.advance_to(v1.HORIZON)
        return {"specification": row, "input": data, "initial_owners": initial_owners, "calls": client.calls, "outbox": client.rows,
            "result": session.result_at(session.physical_time), "summary": {"status": "unknown_initial_asymmetry_or_missing_ledger", "business_metrics": None}}
    policies = {o: OwnerPolicy(native, session, client, o, ledgers[o], channels[o], row["method"], accepted,
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

def prepare(output, phase):
    output.mkdir(parents=True, exist_ok=False); plan = protocol(phase)
    sources = imported_sources()
    plan["source_sha256"] = {str(p): sha(p) for p in sources}
    plan["source_scope"] = "actual loaded project Python module closure; checked before and after run, including service-aware potential preprocessing"
    plan["python_environment"] = {"executable": sys.executable, "version": sys.version}
    archive = output/"source"; archive.mkdir()
    root = Path(__file__).resolve().parents[3]
    plan["source_archive"] = {}
    for p in sources:
        target = archive/p.relative_to(root); target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes()); plan["source_archive"][str(p)] = str(target.relative_to(output))
    plan["input_file_sha256"] = {}
    for key, row in plan["rows"].items():
        target = output/"inputs"/(key+".json"); target.parent.mkdir(parents=True, exist_ok=True)
        write(target, native_scene(row["case"], row["fault"]))
        plan["input_file_sha256"][key] = sha(target)
    write(output/"preregistered_protocol.json", plan); write(output/"branch_ledger.json", plan["rows"])
    return plan

def worker(args):
    worker_started = time.perf_counter()
    if sha(args.output/'preregistered_protocol.json') != args.expected_plan_sha256:
        raise ValueError('public_preference:frozen_plan_changed')
    plan = json.loads((args.output/"preregistered_protocol.json").read_text())
    if plan['phase'] != args.phase or plan['rows'] != protocol(args.phase)['rows']:
        raise ValueError('public_preference:plan_domain_changed')
    if (set(map(str, imported_sources())) != set(plan["source_sha256"])
            or any(sha(p) != h for p, h in plan["source_sha256"].items()) or sha(args.binary) != args.expected_binary_sha256):
        raise ValueError("rolling_joint:frozen_identity_changed")
    contract_reference = {"path": str(args.native_contract.resolve()), "sha256": args.expected_native_contract_sha256}
    campaign_reference = {"path": str((args.output/"preregistered_protocol.json").resolve()),
        "sha256": sha(args.output/"preregistered_protocol.json")}
    semantic_reference = {"path": str(args.semantic_gate.resolve()), "sha256": args.expected_semantic_gate_sha256}
    accepted_run = run_admission.open_run(contract_reference, semantic_reference, campaign_reference)
    try:
        _admitted_worker(args, plan, contract_reference, campaign_reference, semantic_reference, accepted_run, worker_started)
    finally:
        if not accepted_run._closed:
            final = accepted_run.close()
            write(args.output/"run_acceptance.json", final)

def _admitted_worker(args, plan, contract_reference, campaign_reference, semantic_reference, accepted_run, worker_started):
    # The run capability is never reconstructed from this audit dictionary.
    semantic = {"status": "passed_actual_native027_semantic_gate", "reference": semantic_reference,
        "validation": copy.deepcopy(accepted_run._semantic)}
    if accepted_run._verified["contract"]["binary_sha256"] != args.expected_binary_sha256:
        raise ValueError("preexisting_v3_run:accepted_binary_mismatch")
    if plan["phase"] == "business":
        write(args.output/'delivery_gate_binding.json',require_delivery_gate(args.delivery_gate, args.expected_binary_sha256, plan))
    native = load_native(args.binary); rows = copy.deepcopy(plan["rows"]); start = time.perf_counter()
    for key, row in rows.items():
        row["status"] = "unknown_in_progress"; write(args.output/"branch_ledger.json", rows)
        try:
            input_path = args.output/"inputs"/(key+".json")
            if (sha(input_path) != plan["input_file_sha256"][key]
                    or config_sha(native_scene(row["case"], row["fault"])) != plan["row_configuration_sha256"][key]):
                raise ValueError("preexisting:frozen_input_changed")
            accepted_run.enter_branch(key, campaign_reference)
            raw = run_branch(native, row, contract_reference, semantic, accepted_run=accepted_run, branch_key=key)
            accepted_run.finish_branch(key)
            path = args.output/(key+".json.gz"); path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "wt", encoding="utf-8", compresslevel=1) as stream: json.dump(raw, stream, allow_nan=False)
            row.update(status=raw["summary"]["status"], summary=raw["summary"], raw_artifact={"path": key+".json.gz",
                "sha256": sha(path), "input_path": "inputs/"+key+".json", "input_sha256": sha(input_path)})
            if plan["phase"] == "delivery_gate":
                row["raw_validation"] = delivery_evidence.verify_branch(raw, row, json.loads(input_path.read_text(encoding="utf-8")))
                if row["raw_validation"]["status"] != "passed": row["status"] = "unknown_raw_validation_failed"
        except Exception:
            row.update(status="unknown_failed", exception=traceback.format_exc())
            if accepted_run.active_for(key):
                try: accepted_run.finish_branch(key)
                except Exception: row["acceptance_error"] = traceback.format_exc()

        write(args.output/"branch_ledger.json", rows)
    acceptance_final = accepted_run.close()
    write(args.output/"run_acceptance.json", acceptance_final)
    changed = [p for p, h in plan["source_sha256"].items() if sha(p) != h]
    closure_changed = sorted(set(map(str, imported_sources())) ^ set(plan["source_sha256"]))
    receipt = {"schema": "g31.lt2.native_public_preference_receipt.v1", "status": ("executed" if all(r["status"] in ("assessed", "readiness_observed") for r in rows.values()) else "completed_with_unknowns") if not changed else "invalidated_source_drift",
        "source_changed": changed, "source_closure_changed": closure_changed, "binary_sha256": sha(args.binary), "branch_count": len(rows),
        "branch_status_counts": {s: sum(r["status"] == s for r in rows.values()) for s in sorted({r["status"] for r in rows.values()})},
        "raw_artifacts": {key: row["raw_artifact"] for key, row in rows.items() if "raw_artifact" in row},
        "comparisons": assess(rows, plan["phase"]), "wall_seconds": time.perf_counter()-worker_started, "branch_loop_and_exit_seconds": time.perf_counter()-start, "native_forks_used": 0,
        "native_results_used_for_policy": False, "model_protection_certified": False,
        "atomic_agreement_certified": False, "complete_request_100ms_certified": False,
        "native027_contract_reference": contract_reference, "native027_semantic_gate": semantic,
        "current_state_certified": False, "conditional_stability_only": True}
    if closure_changed: receipt["status"] = "invalidated_import_closure_drift"
    receipt["run_acceptance"] = {"path": "run_acceptance.json", "sha256": sha(args.output/"run_acceptance.json"),
        "status": acceptance_final["status"]}
    if acceptance_final["status"] != "closed_run_acceptance_passed":
        receipt["status"] = "invalidated_acceptance_evidence"

    write(args.output/"receipt.json", receipt); print(json.dumps({"status":receipt["status"],"counts":receipt["branch_status_counts"]}))

def require_delivery_gate(path, binary_sha, plan):
    if path is None: raise ValueError("preexisting:business_requires_completed_delivery_gate")
    path = Path(path).resolve()
    require = delivery_evidence.require
    def read(relative): return json.loads((path/relative).read_text(encoding="utf-8"))
    receipt, previous, rows = read("receipt.json"), read("preregistered_protocol.json"), read("branch_ledger.json")
    acceptance_ref = receipt.get("run_acceptance", {})
    require(acceptance_ref.get("path") == "run_acceptance.json"
        and sha(path/"run_acceptance.json") == acceptance_ref.get("sha256")
        and acceptance_ref.get("status") == "closed_run_acceptance_passed", "preexisting:missing_closed_run_acceptance")
    admitted = read("run_acceptance.json")
    require(admitted.get("status") == "closed_run_acceptance_passed" and admitted.get("active") is False
        and admitted.get("invalid") == [] and admitted.get("branch_keys") == sorted(rows)
        and admitted.get("run_reference") == {"path": str(path/"preregistered_protocol.json"),
            "sha256": sha(path/"preregistered_protocol.json")}
        and admitted.get("contract_reference") == receipt.get("native027_contract_reference")
        and admitted.get("semantic_reference") == receipt.get("native027_semantic_gate", {}).get("reference"),
        "preexisting:misbound_run_acceptance")
    require(bool(admitted.get("evidence_sha256")) and all(sha(p) == h
        for p, h in admitted["evidence_sha256"].items()), "preexisting:admission_evidence_changed")
    phases = [cost["phase"] for cost in admitted["costs"]]
    require(phases.count("run_entry_closed_verifiers") == phases.count("run_exit_closed_verifiers") == 1
        and all(phases.count("branch_entry:"+key) == phases.count("branch_exit:"+key) == 1 for key in rows),
        "preexisting:incomplete_run_acceptance_lifetime")
    require(previous.get("phase") == "delivery_gate" and receipt.get("status") == "executed"
            and receipt.get("source_changed") == [] and receipt.get("source_closure_changed") == []
            and receipt.get("binary_sha256") == binary_sha
            and previous.get("source_sha256") == plan["source_sha256"]
            and previous.get("configuration_sha256") == plan["configuration_sha256"], "preexisting:delivery_gate_failed_or_identity_mismatch")
    declared = protocol("delivery_gate")
    require(previous["rows"] == declared["rows"] and previous["row_configuration_sha256"] == declared["row_configuration_sha256"]
        and set(rows) == set(declared["rows"]) and receipt["branch_count"] == len(rows), "preexisting:delivery_denominator_changed")
    require(set(previous["source_archive"]) == set(previous["source_sha256"]), "preexisting:source_archive_coverage")
    for source, digest in previous["source_sha256"].items():
        archived = (path/previous["source_archive"][source]).resolve()
        require(archived.is_relative_to(path/"source") and sha(archived) == digest, "preexisting:archived_source_changed")
    require(set(previous["input_file_sha256"]) == set(rows) and set(receipt["raw_artifacts"]) == set(rows), "preexisting:missing_artifact_denominator")
    revalidated = copy.deepcopy(rows)
    for key, specification in declared["rows"].items():
        require(all(rows[key].get(field) == specification[field] for field in ("case", "method", "fault")), "preexisting:misbound_delivery_row")
        raw_path, input_path = path/(key+".json.gz"), path/"inputs"/(key+".json")
        artifact = {"path": key+".json.gz", "sha256": sha(raw_path), "input_path": "inputs/"+key+".json", "input_sha256": sha(input_path)}
        require(artifact == rows[key]["raw_artifact"] == receipt["raw_artifacts"][key]
            and artifact["input_sha256"] == previous["input_file_sha256"][key], "preexisting:raw_or_input_hash_changed")
        data = json.loads(input_path.read_text(encoding="utf-8"))
        require(config_sha(data) == previous["row_configuration_sha256"][key], "preexisting:input_contract_changed")
        with gzip.open(raw_path, "rt", encoding="utf-8") as stream: raw = json.load(stream)
        result = delivery_evidence.verify_branch(raw, specification, data)
        require(result["status"] == "passed", "preexisting:raw_delivery_validation:" + str(result.get("reason")))
        require(result == rows[key]["raw_validation"] and result["recomputed_summary"] == rows[key]["summary"], "preexisting:lying_delivery_ledger")
        require(rows[key]["status"] == "readiness_observed", "preexisting:unexecuted_delivery_row")
        revalidated[key]["raw_validation"] = result
    comparison = assess(revalidated, "delivery_gate")
    require(comparison["status"] == "passed" and comparison == receipt["comparisons"]
        and receipt["branch_status_counts"] == {"readiness_observed": 9}, "preexisting:delivery_assessment_mismatch")
    return {"path": str(Path(path).resolve()), "receipt_sha256": sha(Path(path)/"receipt.json"),
        "ledger_sha256": sha(Path(path)/"branch_ledger.json"), "plan_sha256": sha(Path(path)/"preregistered_protocol.json"),
        "raw_branches_independently_revalidated": len(rows), "status": "passed"}


def launch(args):
    """All heavy validation and simulation is inside one kill-on-close job."""
    admission=str(uuid.uuid4())
    command=[sys.executable,'-m',__spec__.name,'--worker','--parent-admission',admission,
        '--output',str(args.output),'--phase',args.phase,'--expected-plan-sha256',args.expected_plan_sha256,
        '--binary',str(args.binary),'--expected-binary-sha256',args.expected_binary_sha256,
        '--native-contract',str(args.native_contract),'--expected-native-contract-sha256',args.expected_native_contract_sha256,
        '--semantic-gate',str(args.semantic_gate),'--expected-semantic-gate-sha256',args.expected_semantic_gate_sha256]
    if args.delivery_gate is not None:command.extend(['--delivery-gate',str(args.delivery_gate)])
    with (args.output/'worker.stdout.log').open('w',encoding='utf-8') as stdout,(args.output/'worker.stderr.log').open('w',encoding='utf-8') as stderr:
        result=bounded_windows_job.run(command,timeout=180.,stdout=stdout,stderr=stderr,admission=admission)
    result.update(schema='g31.native_public_preference.bounded_parent.v1',command=command,
        expected_plan_sha256=args.expected_plan_sha256,
        evidence_status='unassessed_actual_process_outcome_only',all_unfinished_branches_retained_unknown=True)
    write(args.output/'bounded_parent_receipt.json',result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--phase',choices=('delivery_gate','business'),default='delivery_gate')
    parser.add_argument('--prepared',action='store_true');parser.add_argument('--execute',action='store_true')
    parser.add_argument('--worker',action='store_true');parser.add_argument('--parent-admission')
    parser.add_argument('--expected-plan-sha256');parser.add_argument('--binary',type=Path)
    parser.add_argument('--expected-binary-sha256');parser.add_argument('--native-contract',type=Path)
    parser.add_argument('--expected-native-contract-sha256');parser.add_argument('--semantic-gate',type=Path)
    parser.add_argument('--expected-semantic-gate-sha256');parser.add_argument('--delivery-gate',type=Path)
    args=parser.parse_args();args.output=args.output.resolve()
    if args.worker:
        if not args.parent_admission or sys.stdin.readline().strip()!=args.parent_admission:
            parser.error('worker requires owned JobObject admission')
        worker(args);return
    if args.execute:
        if not args.prepared or not all((args.expected_plan_sha256,args.binary,args.expected_binary_sha256,
                args.native_contract,args.expected_native_contract_sha256,args.semantic_gate,args.expected_semantic_gate_sha256)):
            parser.error('execute requires frozen prepared plan, exact binary and both accepted gate references')
        if args.phase=='business' and args.delivery_gate is None:parser.error('business requires exact nine-row delivery gate')
        result=launch(args);print(json.dumps(result,indent=2))
        if result['status']!='exited' or result['exitcode']!=0:raise SystemExit(1)
        return
    if args.prepared:parser.error('prepared is a launch option; preparation creates a new immutable directory')
    plan=prepare(args.output,args.phase)
    print(json.dumps({'status':'prepared_no_native_calls','branches':len(plan['rows']),
        'plan_sha256':sha(args.output/'preregistered_protocol.json'),'project_sources':len(plan['source_sha256'])}))


if __name__=='__main__':main()
