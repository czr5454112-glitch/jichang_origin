"""Independent saved-evidence verification for the finite operation probe.

All computation remains in the measured lifetime plus full setup. This verifier
does not derive production admissions, subtract physics, or divide shared work.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

from . import probe_installed_operations as probe
from . import native025_request_timing as abi
from . import native025_timing_gate as gate
from .protocol_control import ProtocolClient
from .rolling_request_lineage import RequestLineage


def same(a,b):
    return json.dumps(a,sort_keys=True,allow_nan=False)==json.dumps(b,sort_keys=True,allow_nan=False)


def replay_lineage(raw):
    """Run the real finite contract again; assigning saved dicts is insufficient."""
    events=[]
    def add(stamp,kind,identity,index=None):
        gate.require(isinstance(stamp,dict) and type(stamp.get("sequence")) is int,"missing_lineage_stamp")
        events.append((stamp["sequence"],kind,identity,index,stamp))
    for root,row in raw["lineage"].items():
        for field in ("accepted","observation","decision_seal","mandatory_drain","output_returned"):
            if row[field] is not None:add(row[field],field,root)
    for identity,row in raw["protocol_lineage"].items():
        for index,stamp in enumerate(row["attempts"]):add(stamp,"attempt",identity,index)
        for index,stamp in enumerate(row["handling_events"]):add(stamp,"ack",identity,index)
    events.sort(key=lambda row:row[0])
    gate.require([row[0] for row in events]==list(range(1,len(events)+1)),"lineage_sequence_gap_or_duplicate")
    checker=RequestLineage()
    for _,kind,identity,index,stamp in events:
        at={"at":stamp["at"],"wall_ns":stamp["wall_ns"]}
        if kind in {"attempt","ack"}:
            row=raw["protocol_lineage"][identity]
            if kind=="attempt":
                checker.submit(row["parent_roots"][0],identity,raw["outbox"][identity]["payload"],
                    required_terminal_statuses=row["required_terminal_statuses"],retry=index>0,**at)
            else:checker.handle_ack(identity,row["terminal_delivered_ack"],**at)
            continue
        row=raw["lineage"][identity]
        if kind=="accepted":checker.accept(identity,scope=row["scope"],completion_contract=row["completion_contract"],
            owner=row["owner"],trigger_id=row["trigger_id"],trigger_kind=row["trigger_kind"],relation=row["relation"],
            parents=row["continuation_parent_roots"],predecessor_protocol_id=row["predecessor_protocol_id"],
            jobs=row["jobs"],trays=row["trays"],**at)
        elif kind=="observation":checker.observe(identity,references=row["input_references"],**at)
        elif kind=="decision_seal":checker.seal(identity,disposition=stamp["disposition"],classification_complete=not row["unclassified"],**at)
        elif kind=="mandatory_drain":checker.drain(identity,timestamp_complete=True,**at)
        else:checker.output(identity,**at)
    gate.require(same(checker.roots,raw["lineage"]) and same(checker.protocol,raw["protocol_lineage"]),"lineage_replay_mismatch")
    return checker


def validate_service_evidence(raw):
    checker=replay_lineage(raw)
    tape=raw["service_tape"]
    gate.require(isinstance(tape,list) and tape and [r["ordinal"] for r in tape]==list(range(1,len(tape)+1)),"service_tape_gap")
    last_end=0;last_physical=0.
    for row in tape:
        gate.require(row["endpoint"] in probe.SERVICE_ENDPOINTS and "error" not in row,"unclassified_or_failed_service_call")
        gate.require(all(type(row[k]) is int and row[k]>=0 for k in ("start_ns","end_ns")) and
            last_end<=row["start_ns"]<=row["end_ns"]<=raw["ended_ns"],"invalid_service_clock")
        gate.require(all(type(row[k]) in (int,float) and math.isfinite(row[k]) for k in ("physical_before","physical_after")) and
            last_physical==row["physical_before"]<=row["physical_after"]<=probe.contract()["physical_budget"],"invalid_service_physical_clock")
        last_end,last_physical=row["end_ns"],row["physical_after"]
    gate.require(last_physical==raw["physical_time"],"unrecorded_final_physical_advance")
    first=tape[0];epoch=10. if raw["case"] in {"empty_supply","cancel_pending"} else .11
    gate.require(first["endpoint"]=="advance_to" and first["args"]==[epoch] and first["kwargs"]=={"max_events":100000} and
        raw["setup_intervals"][1]["start_ns"]<=first["start_ns"]<=first["end_ns"]<=raw["setup_intervals"][1]["end_ns"],"mandatory_initial_advance_missing")
    for root,record in raw["roots"].items():
        line=raw["lineage"][root];entry=tape[record["observation_call_ordinal"]-1]
        owner="B" if raw["case"] in {"empty_supply","cancel_pending"} else "A"
        gate.require(line["owner"]==owner and line["jobs"]==["B2" if owner=="B" else "B1"] and
            line["trigger_id"]==raw["case"]+":"+root and line["trigger_kind"]=="predeclared_public_epoch" and
            line["scope"]=="business_task_update","undeclared_root_scope")
        gate.require(entry["endpoint"]=="observe_protocol" and entry["args"]==[line["owner"]] and not entry["kwargs"] and
            line["observation"]["wall_ns"]<=entry["start_ns"]<=entry["end_ns"]<=raw["observations"][root]["returned_wall_ns"],"admission_observation_call_mismatch")
        annotated=ProtocolClient._annotate_view(SimpleNamespace(state={"forecast_validity":120.}),deepcopy(entry["result"]))
        gate.require(same(annotated,raw["admission_views"][root]),"admission_not_actual_returned_view")
        if record["end_ns"] is not None:
            drain=tape[record["drain_call_ordinal"]-1];result=drain["result"];returned=json.loads(record["returned_output"])
            stamp=line["mandatory_drain"]
            gate.require(drain["endpoint"]=="advance_to" and drain["args"]==[stamp["at"]] and drain["kwargs"]=={"max_events":100000} and
                line["decision_seal"]["wall_ns"]<=drain["start_ns"]<=drain["end_ns"]<=stamp["wall_ns"] and
                result["status"]=="reached" and result["horizon_complete"] is True and result["physical_time"]==stamp["at"] and
                returned["status"]=="returned" and same(returned["drain"],result),"mandatory_drain_not_actual_completed_call")
            output=json.loads(returned["output"])
            gate.require(same(output,{"root":root,"disposition":line["decision_seal"]["disposition"],"decisions":raw["decisions"]}),"returned_disposition_or_decisions_mismatch")
    submissions=[r for r in tape if r["endpoint"].startswith("submit_protocol_")]
    gate.require(len(submissions)==len(raw["calls"]),"submission_tape_count")
    cursor={}
    for entry,call in zip(submissions,raw["calls"],strict=True):
        payload=entry["args"][0];identity=payload["request_id"];operation=raw["protocol_lineage"][identity]
        index=cursor.get(identity,0);stamp=operation["attempts"][index];cursor[identity]=index+1
        gate.require(len(entry["args"])==1 and not entry["kwargs"] and same(payload,raw["outbox"][identity]["payload"]) and
            same(call["request"],payload) and same(call["reply"],entry["result"]) and call["retry"] is (index>0) and
            call["kind"]==raw["outbox"][identity]["kind"] and call["at"]==entry["physical_after"]==stamp["at"],"submission_or_retry_lineage_changed")
        gate.require((stamp["wall_ns"]<=entry["start_ns"] if index==0 else stamp["wall_ns"]>=entry["end_ns"]),"submission_stamp_relation")
    gate.require(cursor=={identity:len(row["attempts"]) for identity,row in raw["protocol_lineage"].items()},"unrecorded_submission_attempt")
    for identity,operation in raw["protocol_lineage"].items():
        if operation["terminal_delivered_ack"] is None:continue
        ack=operation["terminal_delivered_ack"]
        queries=[r for r in tape if r["endpoint"] in {"protocol_command","protocol_request"} and r["args"][1]==identity and
            r["end_ns"]<=operation["handled"]["wall_ns"] and same({**(r["result"].get("last_delivered_ack") or {}),"request_id":identity},ack)]
        gate.require(queries,"terminal_ack_not_delivered_by_actual_query")
    if "timing" in raw:
        envelopes=raw["timing"]["envelopes"]
        gate.require(len(envelopes)==len(tape),"native_envelope_tape_count")
        for entry,envelope in zip(tape,envelopes,strict=True):
            gate.require(envelope["api_endpoint"]==entry["endpoint"] and
                entry["start_ns"]<=envelope["start_ns"]<=envelope["end_ns"]<=entry["end_ns"],"native_envelope_tape_mismatch")
            if entry["endpoint"].startswith("submit_protocol_"):
                gate.require(envelope["protocol_request_id"]==entry["args"][0]["request_id"],"native_submission_identity")
            elif entry["endpoint"] in {"protocol_command","protocol_request"}:
                gate.require(envelope["protocol_request_id"]==entry["args"][1],"native_query_identity")
    return checker


def case_coverage(raw):
    """A finite scenario succeeds only if its declared actual outcomes occurred."""
    name=raw["case"];outbox=raw["outbox"];protocol=raw["protocol_lineage"]
    expected=(["transfer","cancel_transfer"] if name=="cancel_pending" else ["transfer"] if name=="empty_supply" else
        [] if name=="no_action" else ["route","route"] if name=="route_replacement" else ["route"])
    gate.require([row["kind"] for row in outbox.values()]==expected and not raw["failures"],"declared_operation_scenario_not_executed")
    for identity,row in outbox.items():
        required={"route":"updated","transfer":"received","cancel_transfer":"cancelled"}[row["kind"]]
        gate.require(protocol[identity]["required_terminal_statuses"]==[required],"operation_completion_contract_changed")
    roots=raw["roots"];lines=raw["lineage"]
    for root,line in lines.items():
        gate.require(line["completion_contract"]=={"kind":"one_shot_update","goal_id":"install_operation_or_explicit_failure","terminal_failure_allowed":True},"declared_finite_contract_changed")
        gate.require(line["relation"]==("independent_offer" if root=="root" else "cancellation" if root=="cancel" else "replacement_replan") and
            line["continuation_parent_roots"]==([] if root=="root" else ["root"]),"declared_root_relation_changed")
    if name not in {"empty_supply","cancel_pending"}:
        gate.require(len(raw["decisions"])==len(roots),"candidate_decision_count")
        for decision in raw["decisions"]:
            root=decision["root"];wire=.2 if name=="route_replacement" and root=="root" else .01
            payload,candidates=probe.route_candidate(raw["admission_views"][root],roots[root]["job"],wire=wire)
            gate.require(same(decision["candidates"],candidates) and same(decision["selected"],None if name=="no_action" else payload),"candidate_not_derived_from_admitted_public_view")
            if name!="no_action":
                operations=[row for identity,row in outbox.items() if protocol[identity]["parent_roots"][0]==root]
                gate.require(len(operations)==1 and all(operations[0]["payload"].get(k)==v for k,v in payload.items()),"selected_route_not_submitted")
    if name=="ack_still_missing":
        operation=next(iter(protocol.values()))
        gate.require(operation["terminal_delivered_ack"] is None and operation["handled"] is None and roots["root"]["end_ns"] is None and
            len(operation["attempts"])>=2,"missing_ack_negative_not_exercised")
    else:gate.require(all(row["end_ns"] is not None for row in roots.values()),"declared_completion_missing")
    if name=="route_lost_ack":gate.require(len(next(iter(protocol.values()))["attempts"])>=2,"lost_ack_retry_not_exercised")
    if name=="route_replacement":
        first,second=list(protocol.values())
        gate.require(first["terminal_delivered_ack"]["status"]=="rejected" and
            first["terminal_delivered_ack"]["reason"]=="stale_executed_prefix" and second["terminal_delivered_ack"]["status"]=="updated" and
            lines["fallback"]["predecessor_protocol_id"]==first["request_id"] and lines["fallback"]["relation"]=="replacement_replan","replacement_not_actual_stale_to_fresh")
    if name=="cancel_pending":
        first,second=list(protocol.values())
        gate.require(first["terminal_delivered_ack"]["status"]==second["terminal_delivered_ack"]["status"]=="cancelled" and
            lines["root"]["decision_seal"]["disposition"]=="terminal_failure" and lines["cancel"]["decision_seal"]["disposition"]=="completed" and
            lines["cancel"]["predecessor_protocol_id"]==first["request_id"],"cancellation_goal_or_parent_relabelled")
    if name=="no_action":gate.require(lines["root"]["decision_seal"]["disposition"]=="no_action","no_action_negative_not_exercised")
    return {"status":"declared_scenario_exercised","operation_count":len(protocol),"attempt_count":sum(len(row["attempts"]) for row in protocol.values())}


def semantic_record(raw):
    """Remove only declared instrumentation clocks at their known locations."""
    result={key:deepcopy(raw[key]) for key in ("case","input","decisions","outbox","calls","lineage","protocol_lineage",
        "admission_views","observations","failures","physical_time","native_state_sha256","native_binary","service_tape")}
    for call in result["calls"]:call.pop("submit_compute_ms")
    for line in result["lineage"].values():
        for field in ("accepted","observation","decision_seal","mandatory_drain","output_returned"):
            if line[field] is not None:line[field].pop("wall_ns")
    for line in result["protocol_lineage"].values():
        for stamp in line["attempts"]+line["handling_events"]+([line["handled"]] if line["handled"] is not None else []):stamp.pop("wall_ns",None)
    for observation in result["observations"].values():observation.pop("returned_wall_ns")
    for row in result["service_tape"]:
        row.pop("start_ns");row.pop("end_ns")
        if row["endpoint"]=="advance_to":row["result"].pop("wall_seconds")
    return result


def verify_saved(directory):
    directory=Path(directory);plan=gate.read(directory/"plan.json");receipt=gate.read(directory/"receipt.json")
    gate.require(all(plan.get(key)==value for key,value in probe.contract().items()),"probe_contract_changed")
    source_paths=probe.source_paths();expected={str(path.resolve()) for path in source_paths}
    gate.require(set(plan["source_sha256"])==expected and not receipt["source_changed"],"probe_source_domain")
    for path in source_paths:
        digest=plan["source_sha256"][str(path.resolve())]
        gate.require(gate.sha(path)==digest==gate.sha(directory/"source"/path.relative_to(probe.ROOT)),"probe_source_pin")
    reference=plan["contract_reference"];checked=abi.verify_contract(reference,require_runtime=True)
    gate.require(gate.sha(directory/"accepted_reference.json")==plan["accepted_reference_file_sha256"] and
        gate.read(directory/"accepted_reference.json")==reference and
        gate.sha(directory/"accepted_contract.json")==plan["accepted_contract_sha256"]==reference["sha256"] and
        plan["binary"]==checked["contract"]["binary"] and plan["binary_sha256"]==checked["contract"]["binary_sha256"],"accepted_authority_changed")
    gate.require(set(receipt["raw_sha256"])=={arm+"/"+name+".json.gz" for arm in ("plain","timed") for name in probe.CASES},"raw_case_denominator")
    reports={};records={}
    for arm in ("plain","timed"):
        process_path=directory/(arm+".process.json")
        gate.require(gate.sha(process_path)==receipt["process_sha256"][arm] and gate.read(process_path)["exit_code"]==0,"failed_or_unpinned_worker")
        completion_path=directory/arm/"worker_completion.json"
        gate.require(gate.sha(completion_path)==receipt["worker_completion_sha256"][arm],"missing_or_unpinned_worker_completion")
        completion=gate.read(completion_path)
        gate.require(not completion["source_changed"] and completion["case_count"]==len(probe.CASES) and
            not completion["unknown_accounting_cases"],"worker_not_fully_accounted")
        records[arm]={}
        for name in probe.CASES:
            relative=arm+"/"+name+".json.gz";path=directory/relative
            gate.require(gate.sha(path)==receipt["raw_sha256"][relative],"probe_raw_hash")
            raw=gate.read(path);records[arm][name]=raw
            gate.require(raw["case"]==name and same(raw["input"],probe.scene(name)),"probe_scene_changed")
            gate.require(isinstance(raw["native_state_sha256"],str) and re.fullmatch('[0-9a-f]{64}',raw["native_state_sha256"]),"invalid_native_seal")
            gate.require(raw["native_binary"]["sha256"]==checked["contract"]["binary_sha256"],"probe_native_binary")
            result=probe.analyze_case(raw)
            gate.require(result["status"]=="complete_declared_operation_accounting","incomplete_probe_accounting:"+name)
            scenario=case_coverage(raw)
            if arm=="timed":
                timing=raw["timing"];partition=abi.analyze_native025_timing(timing["batches"],timing["envelopes"],reference)
                gate.require(partition["status"]=="validated_partial_native025_phase_partition","unknown_native_phase_partition:"+name)
                reports[name]={**result,"native_phase_partition":partition,"scenario_coverage":scenario}
    for name in probe.CASES:
        gate.require(same(semantic_record(records["plain"][name]),semantic_record(records["timed"][name])),"instrumentation_semantics_changed:"+name)
    return {"status":"validated_finite_installed_operation_accounting","cases":reports,"case_count":len(probe.CASES),
        "root_denominator":probe.contract()["root_count"],"closed_count":sum(r["closed_count"] for r in reports.values()),
        "within100ms_complete_count":sum(r["within100ms_complete_count"] for r in reports.values()),
        "unclassified_or_open_roots":{name:[root for root,row in report["roots"].items() if row["complete_compute_upper_ns"] is None] for name,report in reports.items()},
        "original_business_request_100ms_certified":False,"physics_or_gc_subtracted_ns":0,
        "process_wall_seconds":receipt["wall_seconds"],"scope":"Synthetic finite installed-operation contract; transfer/cancellation job scope unverified; all shared setup fully charged."}


def verify_or_unknown(directory):
    try:return verify_saved(directory)
    except (ValueError,KeyError,TypeError,AttributeError,IndexError,OSError) as error:
        return {"status":"unknown_invalid_or_incomplete_probe","error":str(error),"root_denominator":probe.contract()["root_count"],
            "declared_roots":{name:list(roots) for name,roots in probe.CASES.items()},"original_business_request_100ms_certified":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("directory",type=Path);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=verify_or_unknown(args.directory)
    gate.write(args.output,result)


if __name__=="__main__":main()
