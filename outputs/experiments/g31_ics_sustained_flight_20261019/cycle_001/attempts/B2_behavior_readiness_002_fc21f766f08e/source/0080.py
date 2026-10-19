"""Closed native025 timing runtime gate with saved raw transcripts and spans.

This is a finite ABI/coverage acceptance gate. It never certifies full-request
latency and does not subtract physics, Python overhead or unlabeled intervals.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import re
from pathlib import Path
import subprocess
import sys
import time

from . import native025_request_timing as abi
from . import capture_native025_request_timing as capture
from . import native_host
from .native_request_timing import PHASES
from .profile_request_bundles import semantics

V1_CASES = ("normal", "future_departure", "source_refused", "receiver_refused", "lost_duplicate_ack",
    "owner_recovery", "route_allowed", "route_stale", "forecast_withdraw", "cancel_pending", "cancel_committed", "planning_snapshot")
V2_CASES = ("planning_snapshot_v2", "planning_snapshot_v2_lost_ack")
NEGATIVE_CASES = ("overflow", "exception")
ARMS = {"native022_plain": V1_CASES, "native025_plain": V1_CASES+V2_CASES,
    "native025_timed": V1_CASES+V2_CASES+NEGATIVE_CASES}
SCHEMA = "g31.native025_timing_raw_gate.v1"
SOURCE_NAMES = ("native025_timing_gate.py", "native025_request_timing.py", "capture_native025_request_timing.py",
    "native_host.py", "native_request_timing.py", "capture_native_request_timing.py", "profile_request_bundles.py",
    "profile_native_request_timing.py")


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f: return json.load(f)
    return json.loads(Path(path).read_bytes())
def write(path, value):
    if str(path).endswith(".gz"):
        with gzip.open(path, "xt", encoding="utf-8", compresslevel=1) as f: json.dump(value, f, allow_nan=False)
    else:
        with Path(path).open("x", encoding="utf-8") as f: json.dump(value, f, indent=2, allow_nan=False)
def require(value, reason):
    if not value: raise ValueError("native025_gate:"+reason)
def stable(value):
    if isinstance(value, dict): return {k:stable(v) for k,v in value.items() if k != "wall_seconds"}
    if isinstance(value, list): return [stable(v) for v in value]
    return value
def ordered(value): return json.dumps(stable(semantics(value)), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def scene(case):
    data = native_host.tiny_cycle(); data["transfers"] = []
    data["owner_protocol"] = {"enabled": True, "timeout": .5, "ack_delay": .2}
    data["owner_notifications"] = {"enabled": True}
    data["jobs"][0]["allow_suffix_reroute"] = True
    if case in {"lost_duplicate_ack", "planning_snapshot_v2_lost_ack"}:
        data["owner_protocol"].update(drop_ack_packets=1, duplicate_acks=True, duplicate_ack_delay=2.)
    if case == "owner_recovery": data["owner_protocol"]["owner_outages"] = [{"owner":"A", "start":9., "end":20.}]
    if case in {"source_refused", "receiver_refused"}:
        node, field = (4,"allow_export") if case == "source_refused" else (0,"allow_receive")
        next(n for n in data["node_contracts"] if n["node"] == node)[field] = False
    if case == "forecast_withdraw": data["node_contracts"][1]["resource_owner"] = "B"
    return data


def endpoints(case):
    if case in NEGATIVE_CASES: return ["advance_to"]
    if case.startswith("route"):
        names=["advance_to","observe_protocol","submit_protocol_command","advance_to","protocol_command"]
    elif case=="forecast_withdraw":
        names=["advance_to","submit_protocol_command","advance_to","submit_protocol_command","advance_to","protocol_command"]
    elif case.startswith("cancel"):
        names=["advance_to","submit_protocol_transfer","advance_to","submit_protocol_command","advance_to","protocol_command"]
    elif case.startswith("planning_snapshot"):
        names=["submit_protocol_command","advance_to","protocol_command"]
        if case.endswith("lost_ack"): names += ["submit_protocol_command","advance_to"]
        names += ["protocol_command", "protocol_planning_snapshots_v2" if case in V2_CASES else "protocol_planning_snapshots"]
    else:
        names=["advance_to","submit_protocol_transfer","advance_to","protocol_request","observe_protocol",
            "observe_protocol_control","observe_protocol_control_policy","observe_protocol_control_policy_recent",
            "protocol_demand_signature","protocol_planning_snapshots","submit_protocol_transfer","advance_to",
            "submit_protocol_transfer","advance_to","protocol_request"]
    return names+["result_at"]


def check_outcome(case, outputs):
    if case in NEGATIVE_CASES: return
    queries=[row for row in outputs if row["endpoint"] in {"protocol_request","protocol_command"}]
    ack=queries[-1]["returned"]["last_delivered_ack"]
    expected=("updated" if case=="route_allowed" else "rejected" if case in
        {"route_stale","source_refused","receiver_refused","cancel_committed"} else
        "cancelled" if case=="cancel_pending" else "delivered" if case=="forecast_withdraw" or
        case.startswith("planning_snapshot") else "received")
    require(ack["status"]==expected,"raw_outcome:"+case)
    if case.startswith("route"):
        require(ack["reason"]==("allowed" if case=="route_allowed" else "stale_executed_prefix"),"raw_route_reason")
    if case.startswith("planning_snapshot"):
        require(outputs[-2]["returned"],"raw_planning_delivery_missing")


def run_case(native, case, *, timed, reference, identity):
    data = scene(case); raw = native.NativeSession(data)
    session = capture.Native025TimingCapture(raw, native_module=native, contract_reference=reference,
        acceptance_probe=True, session_identity=identity, capacity=2 if case == "overflow" else 100000) if timed else raw
    outputs=[]
    def call(endpoint, *args, **kwargs):
        entry={"endpoint":endpoint,"args":deepcopy(args),"kwargs":deepcopy(kwargs)}
        try: value=getattr(session,endpoint)(*args,**kwargs)
        except Exception as error:
            entry["exception"]={"type":type(error).__name__,"message":str(error)}; outputs.append(entry); raise
        entry["returned"]=deepcopy(value);outputs.append(entry);return value
    def command(kind, owner="A", **payload):
        return {"request_id":f"live:1:{owner}:{kind}:one", "owner_id":owner,"kind":kind,**payload}
    def transfer(earliest=10.):
        return {"request_id":"live:1:B:return-1","owner_id":"B","tray_id":"T0","source":4,
            "destination":0,"earliest_departure":earliest,"expiry":60.,"message_delay":0.}
    if case == "exception":
        try: call("advance_to", -1.)
        except (ValueError, RuntimeError): pass
        else: raise ValueError("native025_gate:expected_native_exception_missing")
    elif case == "overflow": call("advance_to",10.)
    elif case.startswith("route"):
        call("advance_to",.11); tray=call("observe_protocol","A")["trays"][0]
        p=command("route",business_bag_id=tray["business_bag_id"],tray_id=tray["tray_id"],
            expected_generation=tray["generation"],expected_traversal=tray["traversal_id"],
            expiry=5.,message_delay=.01 if case == "route_allowed" else .2,next=1)
        p["from"]=tray["node"];call("submit_protocol_command",p);call("advance_to",.6)
        ack=call("protocol_command","A",p["request_id"])["last_delivered_ack"]
        require(ack["reason"] == ("allowed" if case=="route_allowed" else "stale_executed_prefix"), "route_outcome")
    elif case=="forecast_withdraw":
        call("advance_to",.05); f=command("service_forecast",target_owner="B",tray_id="T0",next=1,publication_delay=2.)
        call("submit_protocol_command",f);call("advance_to",.06)
        p=command("withdraw_service_forecast",forecast_request_id=f["request_id"],publication_delay=.1)
        call("submit_protocol_command",p);call("advance_to",2.5)
        require(call("protocol_command","A",p["request_id"])["last_delivered_ack"]["status"]=="delivered","withdrawal_outcome")
    elif case.startswith("cancel"):
        call("advance_to",10.);p=transfer(50. if case=="cancel_pending" else 10.)
        call("submit_protocol_transfer",p);call("advance_to",10.1)
        c=command("cancel_transfer",owner="B",transfer_request_id=p["request_id"])
        call("submit_protocol_command",c);call("advance_to",11.)
        require(call("protocol_command","B",c["request_id"])["last_delivered_ack"]["status"]==
            ("cancelled" if case=="cancel_pending" else "rejected"),"cancel_outcome")
    elif case.startswith("planning_snapshot"):
        kind="planning_snapshot_v2" if case in V2_CASES else "planning_snapshot"
        p=command(kind,target_owner="B",message_delay=.01,publication_delay=.02,expiry=5.)
        call("submit_protocol_command",p);call("advance_to",.5)
        call("protocol_command","A",p["request_id"])
        if case.endswith("lost_ack"):
            call("submit_protocol_command",p);call("advance_to",1.)
        ack=call("protocol_command","A",p["request_id"])["last_delivered_ack"]
        require(ack["status"]=="delivered","planning_ack_missing")
        require(call("protocol_planning_snapshots_v2" if kind.endswith("v2") else "protocol_planning_snapshots","B"),"planning_delivery_missing")
    else:
        call("advance_to",10.);p=transfer(12. if case=="future_departure" else 10.)
        call("submit_protocol_transfer",p);call("advance_to",11.);call("protocol_request","B",p["request_id"])
        for method,args in (("observe_protocol",("B",)),("observe_protocol_control",("B",)),
            ("observe_protocol_control_policy",("B",)),("observe_protocol_control_policy_recent",("B",120.)),
            ("protocol_demand_signature",("B",)),("protocol_planning_snapshots",("B",))): call(method,*args)
        call("submit_protocol_transfer",p);call("advance_to",70.);call("submit_protocol_transfer",p)
        call("advance_to",70.3);call("protocol_request","B",p["request_id"])
    if case not in NEGATIVE_CASES: call("result_at",max(70.3,raw.physical_time))
    result={"case":case,"status":"captured","input":data,"outputs":outputs,
        "native_binary":deepcopy(native._g31_native_artifact_identity),
        "native_seal":raw.offline_state_sha256(),"checkpoint_seal":raw.checkpoint().offline_state_sha256}
    if timed:
        session.take_completed(); result["timing"]={"batches":session.batches,"envelopes":session.envelopes,"capture_errors":session.errors}
    return result


def check_records(records):
    require(set(records)==set(ARMS),"arm_domain")
    for arm,cases in ARMS.items():
        require(set(records[arm])==set(cases),"case_domain:"+arm)
        require(all(row.get("status")=="captured" and row.get("case")==case for case,row in records[arm].items()),"case_status")
        for case,row in records[arm].items():
            require(ordered(row["input"])==ordered(scene(case)),"predeclared_input:"+case)
            require([r["endpoint"] for r in row["outputs"]]==endpoints(case),"predeclared_endpoint_tape:"+case)
            check_outcome(case,row["outputs"])
            require(all(isinstance(row.get(k),str) and re.fullmatch(r"[0-9a-f]{64}",row[k]) for k in
                ("native_seal","checkpoint_seal")),"invalid_native_seal:"+case)
            if arm=="native025_timed":
                envelopes=row["timing"]["envelopes"]
                require([e["api_endpoint"] for e in envelopes]==endpoints(case),"envelope_tape:"+case)
                for entry,envelope in zip(row["outputs"],envelopes,strict=True):
                    endpoint=entry["endpoint"]
                    if endpoint.startswith("submit_protocol_"):
                        require(envelope.get("protocol_request_id")==entry["args"][0]["request_id"],"submit_identity_tape")
                    elif endpoint in {"protocol_request","protocol_command"}:
                        require(envelope.get("protocol_request_id")==entry["args"][1],"query_identity_tape")
    for case in V1_CASES+V2_CASES:
        plain,timed=(records[arm][case] for arm in ("native025_plain","native025_timed"))
        require(ordered(plain["input"])==ordered(timed["input"]),"timed_input:"+case)
        require(ordered(plain["outputs"])==ordered(timed["outputs"]),"timed_transcript:"+case)
        require(plain["native_seal"]==timed["native_seal"]==plain["checkpoint_seal"]==timed["checkpoint_seal"],"timed_seal:"+case)
        if case in V1_CASES:
            old=records["native022_plain"][case]
            require(ordered(old["input"])==ordered(plain["input"]) and ordered(old["outputs"])==ordered(plain["outputs"]),"v1_ordered_transcript:"+case)
            require(old["native_seal"]==old["checkpoint_seal"]==plain["native_seal"],"v1_seal:"+case)
        timing=timed["timing"]
        require(not timing["capture_errors"],"capture_errors:"+case)
        report=abi.analyze_candidate_partition(timing["batches"],timing["envelopes"])
        require(report["status"]=="structurally_valid_native025_candidate_partition","phase_conservation:"+case)
        rows=[r for batch in timing["batches"] for r in batch["rows"]]
        phases={PHASES[r["phase"]] for r in rows}
        require({"source_execution","ack_create","ack_delivery"} <= phases,"missing_protocol_phases:"+case)
        if case in V2_CASES:
            require(any(e["api_endpoint"]=="protocol_planning_snapshots_v2" and e["method"]==10 for e in timing["envelopes"]),"v2_endpoint_missing")
            require(any(r["identity_kind"]==10 and PHASES[r["phase"]]=="publication_delivery" for r in rows),"v2_publication_identity_missing")
            require(any(c["kind"]=="planning_snapshot_v2" for b in timing["batches"] for c in b["command_identities"]),"v2_identity_table_missing")
    for case in NEGATIVE_CASES:
        timing=records["native025_timed"][case]["timing"]
        require(abi.analyze_candidate_partition(timing["batches"],timing["envelopes"])["status"]=="unknown","negative_did_not_fail_closed:"+case)
        if case=="overflow": require(any(type(b["errors"]) is int and b["errors"] & 1 for b in timing["batches"]),"overflow_not_recorded")
        else: require(timing["capture_errors"] and any("exception" in r for r in records["native025_timed"][case]["outputs"]),"exception_not_recorded")
    return {gate:True for gate in abi.RUNTIME_GATES}


def verify_saved_gate(reference, contract):
    path=Path(reference["path"]);require(sha(path)==reference["sha256"],"receipt_changed");receipt=read(path)
    require(receipt.get("schema")==SCHEMA and receipt.get("status")=="verified_raw_runtime_gate","unsupported_receipt")
    plan_path=path.parent/"plan.json";require(sha(plan_path)==receipt["plan_sha256"],"plan_changed");plan=read(plan_path)
    require(plan["abi"]=={k:list(v) for k,v in abi.ABI025.items()} and plan["cases"]=={k:list(v) for k,v in ARMS.items()},"plan_domain")
    for key in ("binary_sha256","build_receipt_sha256","versioned_validator_sha256"):
        require(plan[key]==contract[key],"contract_identity:"+key)
    require(plan["gate_validator_sha256"]==sha(__file__),"gate_verifier_changed")
    from .profile_native_request_timing import verify_build_receipt
    old_build=Path(plan["native022_build"])
    require(sha(old_build)==plan["native022_build_sha256"],"old_build_receipt_changed")
    verify_build_receipt(old_build,Path(plan["native022_binary"]),plan["native022_sha256"])
    require(set(plan["source_sha256"])==set(SOURCE_NAMES),"source_inventory")
    require(plan["source_sha256"]["native025_timing_gate.py"]==plan["gate_validator_sha256"] and
        plan["source_sha256"]["native025_request_timing.py"]==contract["versioned_validator_sha256"] and
        plan["source_sha256"]["native_request_timing.py"]==contract["legacy_validator_sha256"],"validator_archive_crosslink")
    for name,expected in plan["source_sha256"].items():
        require(sha(path.parent/"source"/name)==expected and sha(Path(__file__).with_name(name))==expected,"source_archive_or_live_changed")
    require(receipt["source_changed"]==[] and set(receipt["raw"])==set(ARMS),"receipt_domain")
    records={}
    for arm,cases in ARMS.items():
        require(sha(path.parent/(arm+".process.json"))==receipt["process_sha256"][arm],"process_receipt_changed")
        process=read(path.parent/(arm+".process.json"))
        require(process["exit_code"]==0,"worker_failed:"+arm)
        require(set(receipt["raw"][arm])==set(cases),"raw_domain")
        records[arm]={}
        for case in cases:
            entry=receipt["raw"][arm][case];raw_path=path.parent/arm/(case+".json.gz")
            require(sha(raw_path)==entry["sha256"],"raw_changed:"+arm+":"+case)
            records[arm][case]=read(raw_path)
            require(records[arm][case]["native_binary"]["sha256"]==
                (plan["native022_sha256"] if arm=="native022_plain" else contract["binary_sha256"]),"raw_binary_identity")
    gates=check_records(records)
    require(receipt["gates"]==gates,"claimed_gates_mismatch")
    return {"status":"verified_raw_runtime_gate","gates":gates,"runtime_accepted":True,
        "complete_request_100ms_certified":False,"physics_subtracted_ns":0}


def worker(args):
    plan=read(args.output/"plan.json");arm=args.arm
    reference=plan["contract_reference"];contract=abi.verify_contract(reference)["contract"]
    binary=Path(plan["native022_binary"] if arm=="native022_plain" else contract["binary"])
    require(sha(binary)==(plan["native022_sha256"] if arm=="native022_plain" else contract["binary_sha256"]),"worker_binary")
    native=native_host.load_native(binary);directory=args.output/arm;directory.mkdir(exist_ok=False)
    for index,case in enumerate(ARMS[arm],1):
        write(directory/(case+".json.gz"),run_case(native,case,timed=arm=="native025_timed",reference=reference,identity=index))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--reference",type=Path);parser.add_argument("--native022",type=Path)
    parser.add_argument("--native022-build",type=Path);parser.add_argument("--execute",action="store_true")
    parser.add_argument("--arm",choices=ARMS);args=parser.parse_args()
    if args.arm: worker(args);return
    args.output.mkdir(parents=True,exist_ok=False)
    reference=read(args.reference);contract=abi.verify_contract(reference)["contract"]
    from .profile_native_request_timing import verify_build_receipt
    old=verify_build_receipt(args.native022_build,args.native022,sha(args.native022))
    sources={name:Path(__file__).with_name(name) for name in SOURCE_NAMES}
    archive=args.output/"source";archive.mkdir()
    for name,path in sources.items(): (archive/name).write_bytes(path.read_bytes())
    plan={"schema":"g31.native025_timing_gate_plan.v1","cases":{k:list(v) for k,v in ARMS.items()},
        "abi":{k:list(v) for k,v in abi.ABI025.items()},"contract_reference":reference,
        **{k:contract[k] for k in ("binary_sha256","build_receipt_sha256","versioned_validator_sha256")},
        "gate_validator_sha256":sha(__file__),"source_sha256":{name:sha(path) for name,path in sources.items()},
        "native022_binary":str(args.native022.resolve()),"native022_sha256":sha(args.native022),
        "native022_build":str(args.native022_build.resolve()),"native022_build_sha256":sha(args.native022_build),
        "maximum_native_workers":1,"physics_subtracted":False,"complete_request_100ms_certified":False}
    write(args.output/"plan.json",plan)
    if not args.execute: print("prepared_no_native_calls");return
    started=time.perf_counter()
    for arm in ARMS:
        command=[sys.executable,"-m",__spec__.name,"--output",str(args.output),"--arm",arm]
        with (args.output/(arm+".stdout.log")).open("x") as out,(args.output/(arm+".stderr.log")).open("x") as err:
            try: result=subprocess.run(command,stdout=out,stderr=err,timeout=120.)
            except subprocess.TimeoutExpired:
                write(args.output/(arm+".process.json"),{"command":command,"status":"unknown_timeout","exit_code":None})
                raise
        write(args.output/(arm+".process.json"),{"command":command,"status":"returned","exit_code":result.returncode})
        require(result.returncode==0,"worker_failed:"+arm)
    records={arm:{case:read(args.output/arm/(case+".json.gz")) for case in cases} for arm,cases in ARMS.items()}
    gates=check_records(records)
    changed=[name for name,path in sources.items() if sha(path)!=plan["source_sha256"][name]]
    require(not changed,"source_changed")
    receipt={"schema":SCHEMA,"status":"verified_raw_runtime_gate","source_changed":changed,
        "plan_sha256":sha(args.output/"plan.json"),"gates":gates,"wall_seconds":time.perf_counter()-started,
        "process_sha256":{arm:sha(args.output/(arm+".process.json")) for arm in ARMS},
        "raw":{arm:{case:{"sha256":sha(args.output/arm/(case+".json.gz"))} for case in cases} for arm,cases in ARMS.items()},
        "complete_request_100ms_certified":False,"physics_subtracted_ns":0}
    write(args.output/"receipt.json",receipt)
    ref={"path":str((args.output/"receipt.json").resolve()),"sha256":sha(args.output/"receipt.json")}
    verified=verify_saved_gate(ref,contract);write(args.output/"independent_reassessment.json",verified)
    print(json.dumps({"receipt":ref,"verification":verified},indent=2))

if __name__=="__main__": main()
