"""Finite experimental installed-operation updates using actual native025 ACKs.

No production admission contract is replaced. Per-job route scope is verified;
empty transfer/cancellation remain operation updates with declared job labels.
Whole native work and all request-lifetime scheduler gaps are retained.
"""
from __future__ import annotations
import argparse
import ast
from copy import deepcopy
import gzip
import heapq
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from .business_update_outbox import BusinessUpdateOutbox, _digest
from .rolling_request_lineage import RequestLineage
from .protocol_control import ProtocolClient
from .capture_native025_request_timing import Native025TimingCapture
from . import native025_request_timing as abi
from . import native025_timing_gate as gate
from . import native_host

CASES = {"route_installed":("root",), "route_lost_ack":("root",), "route_replacement":("root","fallback"),
    "empty_supply":("root",), "cancel_pending":("root","cancel"), "no_action":("root",), "ack_still_missing":("root",)}
SCHEMA="g31.experimental_installed_operation_probe.v1"
ROOT=Path(__file__).resolve().parents[3]
SERVICE_ENDPOINTS=frozenset(("advance_to", "observe_protocol", "submit_protocol_command",
    "submit_protocol_transfer", "protocol_command", "protocol_request"))


def scene(name):
    if name not in CASES: raise ValueError("operation_probe:undeclared_case")
    data=gate.scene("normal")
    if name=="route_lost_ack":data["owner_protocol"]["drop_ack_packets"]=1
    if name=="ack_still_missing":data["owner_protocol"]["drop_ack_packets"]=100
    return data


class ServiceTape:
    """Lossless diagnostic copies, made inside the measured service lifetime."""
    def __init__(self, session): self.session,self.rows=session,[]
    @property
    def physical_time(self):return self.session.physical_time
    def __getattr__(self, endpoint):
        if endpoint not in SERVICE_ENDPOINTS:raise ValueError("operation_probe:unclassified_endpoint:"+endpoint)
        def call(*args, **kwargs):
            start=time.perf_counter_ns()
            row={"ordinal":len(self.rows)+1,"endpoint":endpoint,"args":deepcopy(list(args)),"kwargs":deepcopy(kwargs),
                "physical_before":self.physical_time,"start_ns":start}
            try:
                result=getattr(self.session,endpoint)(*args,**kwargs)
                row["result"]=deepcopy(result)
                return result
            except BaseException as error:
                row["error"]=type(error).__name__+":"+str(error);raise
            finally:
                row["physical_after"]=self.physical_time;row["end_ns"]=time.perf_counter_ns();self.rows.append(row)
        return call


def source_paths():
    """Repository import graph, including absolute imports and package init files."""
    directory=Path(__file__).parent;pending=[Path(__file__),directory/"verify_installed_operations.py"];found=set()
    def enqueue(target):
        for candidate in (target.with_suffix('.py'),target/'__init__.py'):
            if candidate.is_file() and candidate.resolve().is_relative_to(ROOT):
                pending.append(candidate)
                for parent in candidate.parents:
                    if parent==ROOT:break
                    initializer=parent/'__init__.py'
                    if initializer.is_file():pending.append(initializer)
    while pending:
        path=pending.pop().resolve()
        if path in found:continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
            if isinstance(node,ast.ImportFrom):
                base=path.parent if node.level else ROOT
                for _ in range(max(0,node.level-1)):base=base.parent
                if node.module:base=base.joinpath(*node.module.split('.'));enqueue(base)
                for alias in node.names:
                    if alias.name!='*':enqueue(base.joinpath(*alias.name.split('.')))
            elif isinstance(node,ast.Import):
                for alias in node.names:enqueue(ROOT.joinpath(*alias.name.split('.')))
    return sorted(found)


def contract():
    return {"schema":SCHEMA,"cases":{k:list(v) for k,v in CASES.items()},"root_count":sum(map(len,CASES.values())),
        "admission":"Each declared finite root starts before its public observation; fallback/cancellation parents explicit before child work.",
        "completion":"Declared terminal delivered ACK and processing, required descendants, actual complete same-time drain, serialized returned output.",
        "computation_bound":"Whole measured root lifetime, including all native advances, Python work, codec and scheduler gaps, plus full common input/session/public-clock preparation. No sleeps or wall-clock logical transport waits. No physics/GC subtraction.",
        "setup":"Native capture contract verification/start/export is diagnostic-only outside service intervals and remains in process wall. Native construction, input/contract creation, ProtocolClient setup and initial physical advance are common mandatory work charged in full to every root.",
        "search":"Actual local loaded tray + observed job; Dijkstra over public static durations to required Storage before destination; select minimal cost then next-node ID. No native fork or results used.",
        "joint_scope":"This prototype accepts one job per root and cannot verify multi-job joint admission. Shared operations retain all explicitly declared parents; transfer/cancel job authority is unverified, never removed from denominator.",
        "limits":["synthetic tiny_cycle fixture only","not accepted original business admission contract","not physical job completion","not full workload or deployment100ms certification"],
        "failure_policy":"All declared roots retained, including missing-ACK/open and unknown job scope; budget remains fixed.",
        "physical_budget":70.3,"poll_steps_max":200,"poll_step":.05,"event_budget":100000}


def route_candidate(view, job_id, *, wire):
    jobs=[j for j in view["jobs"] if j["business_bag_id"]==job_id]
    trays=[t for t in view["trays"] if t["business_bag_id"]==job_id and t["mode"]=="loaded" and t["edge_to"]<0]
    if len(jobs)!=1 or len(trays)!=1:return None,[]
    job,tray=jobs[0],trays[0]
    target=job["storage_node"] if job["storage_node"]>=0 and job["storage_released_at"]<0 else job["destination"]
    graph={};service={n[0]:n[2] for n in view["node_records"]}
    for u,v,length,speed in view["edge_records"]:
        if not all(math.isfinite(x) and x>0 for x in (length,speed)):raise ValueError("operation_probe:invalid_public_edge")
        graph.setdefault(u,[]).append((v,max(length/speed,.001)+service[v]))
    def remaining(start):
        queue=[(0.,start)];dist={start:0.}
        while queue:
            value,node=heapq.heappop(queue)
            if value!=dist[node]:continue
            if node==target:return value
            for nxt,cost in graph.get(node,[]):
                total=value+cost
                if total<dist.get(nxt,math.inf):dist[nxt]=total;heapq.heappush(queue,(total,nxt))
        return math.inf
    candidates=sorted((cost+remaining(nxt),nxt) for nxt,cost in graph.get(tray["node"],[]))
    if not candidates or not math.isfinite(candidates[0][0]):return None,candidates
    payload={"business_bag_id":job_id,"tray_id":tray["tray_id"],"from":tray["node"],"next":candidates[0][1],
        "expected_generation":tray["generation"],"expected_traversal":tray["traversal_id"],
        "message_delay":wire,"expiry":view["now"]+5.}
    return json.loads(json.dumps(payload,allow_nan=False)),candidates


def run_case(native, name, reference, *, timed, identity):
    # Tool/runtime import and contract verification happened before this timer.
    started=time.perf_counter_ns();data=scene(name)
    raw=native.NativeSession(data)
    initial1={"start_ns":started,"end_ns":time.perf_counter_ns()}
    diagnostic_start=time.perf_counter_ns()
    capture=Native025TimingCapture(raw,native_module=native,contract_reference=reference,session_identity=identity) if timed else None
    diagnostic_setup=time.perf_counter_ns()-diagnostic_start
    started=time.perf_counter_ns()
    session=ServiceTape(capture if timed else raw)
    owner="B" if name in {"empty_supply","cancel_pending"} else "A"
    job="B2" if owner=="B" else "B1"
    client=ProtocolClient(session,retry_period=.5)
    bridge=BusinessUpdateOutbox(client,owner)
    session.advance_to(10. if owner=="B" else .11,max_events=100000)
    initial2={"start_ns":started,"end_ns":time.perf_counter_ns()}
    roots={};decisions=[];failures=[];admission_views={}
    def admit(root, *, parents=(), relation="independent_offer", predecessor=None):
        roots[root]={"start_ns":time.perf_counter_ns(),"end_ns":None,"job":job,"parents":list(parents)}
        bridge.admit(root,business_job_id=job,trigger_id=name+":"+root,trigger_kind="predeclared_public_epoch",
            completion_contract={"kind":"one_shot_update","goal_id":"install_operation_or_explicit_failure","terminal_failure_allowed":True},
            relation=relation,parents=parents,predecessor_protocol_id=predecessor)
        view=bridge.observe(root,compact=False);admission_views[root]=deepcopy(view)
        roots[root]["observation_call_ordinal"]=len(session.rows);return view
    def finish(root, disposition):
        output={"root":root,"disposition":disposition,"decisions":decisions}
        returned=bridge.finish(root,output,disposition=disposition,classification_complete=True,event_budget=100000)
        if returned["status"]=="returned":
            # Required final public result encoding is included after bridge output.
            roots[root]["returned_output"]=json.dumps(returned,allow_nan=False)
            roots[root]["drain_call_ordinal"]=len(session.rows);roots[root]["end_ns"]=time.perf_counter_ns()
        return returned
    def poll_until(predicate, horizon):
        for _ in range(200):
            bridge.refresh()
            if predicate():return True
            if session.physical_time>=horizon:return False
            session.advance_to(min(horizon,session.physical_time+.05),max_events=100000)
        return False
    def handled(identity):return bridge.lineage.protocol[identity]["handled"] is not None
    view=admit("root")
    try:
        if name=="no_action":
            # Candidate preprocessing is still real; declared action set is empty.
            _,candidate=route_candidate(view,job,wire=.01)
            decisions.append({"root":"root","candidates":candidate,"selected":None,"reason":"declared_no_action_update"})
            finish("root","no_action")
        elif owner=="A":
            payload,candidates=route_candidate(view,job,wire=.2 if name=="route_replacement" else .01)
            if payload is None:raise ValueError("operation_probe:missing_route_candidate")
            decisions.append({"root":"root","candidates":candidates,"selected":payload,"public_view":view})
            request,_=bridge.submit("root","route",payload,required_terminal_statuses=("updated",))
            resolved=poll_until(lambda:handled(request),.6 if name=="route_replacement" else 1.3)
            if name=="route_replacement" and resolved:
                # The fixed public service epoch is declared in this fixture;
                # only its fresh local observed tray permits the replacement.
                session.advance_to(1.16,max_events=100000)
                fresh=admit("fallback",parents=("root",),relation="replacement_replan",predecessor=request)
                replacement,candidates=route_candidate(fresh,job,wire=.01)
                if replacement is None:raise ValueError("operation_probe:missing_fresh_replacement")
                decisions.append({"root":"fallback","candidates":candidates,"selected":replacement,"public_view":fresh})
                child,_=bridge.submit("fallback","route",replacement,required_terminal_statuses=("updated",))
                if poll_until(lambda:handled(child),2.):
                    finish("fallback","completed");finish("root","completed")
            elif resolved:finish("root","completed")
        else:
            trays=[t for t in view["trays"] if t["tray_id"]=="T0" and t["node"]==4 and t["mode"]=="empty" and t["edge_to"]<0 and t["available_at"]<=view["now"]]
            if len(trays)!=1:raise ValueError("operation_probe:source_empty_not_available")
            # Destination0 is a predeclared public port. This cannot establish
            # unique assignment of this empty to B2, hence job_scope remainsfalse.
            payload={"tray_id":"T0","source":4,"destination":0,"earliest_departure":50. if name=="cancel_pending" else view["now"],
                "expiry":60.,"message_delay":0.}
            payload=json.loads(json.dumps(payload,allow_nan=False))
            decisions.append({"root":"root","selected":payload,"public_view":view})
            request,_=bridge.submit("root","transfer",payload,required_terminal_statuses=("received",))
            if name=="cancel_pending":
                session.advance_to(10.1,max_events=100000);bridge.refresh()
                admit("cancel",parents=("root",),relation="cancellation",predecessor=request)
                cancel,_=bridge.submit("cancel","cancel_transfer",{"transfer_request_id":request,"message_delay":.01},required_terminal_statuses=("cancelled",))
                if poll_until(lambda:handled(request) and handled(cancel),12.):
                    finish("cancel","completed");finish("root","terminal_failure")
            elif poll_until(lambda:handled(request),15.):finish("root","completed")
    except Exception as error:failures.append(type(error).__name__+":"+str(error))
    end=time.perf_counter_ns()
    # Capture exports, independent reports/seals and evidence serialization are
    # diagnostics after every required root return, retained in process wall.
    reports={root:bridge.report(root) for root in roots}
    result={"schema":SCHEMA,"case":name,"input":data,"setup_intervals":[initial1,initial2],
        "diagnostic_capture_setup_ns":diagnostic_setup,"roots":roots,"root_reports":reports,"ended_ns":end,
        "decisions":decisions,"outbox":client.state["outbox"],"calls":client.calls,"lineage":bridge.lineage.roots,
        "admission_views":admission_views,"observations":bridge.observations,
        "protocol_lineage":bridge.lineage.protocol,"failures":failures,"physical_time":session.physical_time,
        "service_tape":session.rows,"native_binary":deepcopy(native._g31_native_artifact_identity),
        "native_state_sha256":raw.offline_state_sha256(),"original_user_contract_accepted":False}
    if timed:
        capture.take_completed();result["timing"]={"batches":capture.batches,"envelopes":capture.envelopes,"errors":capture.errors}
    return result


def analyze_case(raw):
    name=raw.get("case")
    unknown={"status":"unknown_invalid_or_incomplete_accounting","declared_root_ids":list(CASES.get(name,())),
        "complete_request_100ms_certified":False}
    try:
        from .verify_installed_operations import validate_service_evidence
        validate_service_evidence(raw)
        gate.require(name in CASES and set(raw["roots"])==set(CASES[name]) and set(raw["root_reports"])==
            set(CASES[name])==set(raw["lineage"])==set(raw["admission_views"])==set(raw["observations"]),"admission_domain")
        def stamp(value):return type(value) is int and value>=0
        gate.require(stamp(raw["ended_ns"]),"invalid_end_clock")
        intervals=raw["setup_intervals"]
        gate.require(len(intervals)==2 and all(stamp(r["start_ns"]) and stamp(r["end_ns"]) and
            r["start_ns"]<=r["end_ns"] for r in intervals) and intervals[0]["end_ns"]<=intervals[1]["start_ns"],"invalid_setup_intervals")
        setup=sum(row["end_ns"]-row["start_ns"] for row in intervals)
        checker=RequestLineage();checker.roots=raw["lineage"];checker.protocol=raw["protocol_lineage"]
        coverage=list(intervals)
        for root,record in raw["roots"].items():
            start,end=record["start_ns"],record["end_ns"]
            gate.require(stamp(start) and start>=intervals[-1]["end_ns"] and (end is None or
                stamp(end) and start<=end<=raw["ended_ns"]),"invalid_root_interval")
            actual=checker.summary(root);saved=raw["root_reports"][root]
            expected=saved["status"]
            if expected=="complete_declared_operation_lineage_job_scope_unverified":expected="complete_declared_lineage"
            gate.require(actual["status"]==expected and actual["closure"]==saved["closure"],"lineage_summary_changed")
            lineage=raw["lineage"][root]
            gate.require(lineage["jobs"]==[record["job"]] and lineage["continuation_parent_roots"]==record["parents"] and
                start<=lineage["accepted"]["wall_ns"]<=lineage["observation"]["wall_ns"],"root_admission_or_parent_mismatch")
            view,observation=raw["admission_views"][root],raw["observations"][root]
            gate.require(_digest(view)==observation["view_sha256"] and view["owner_id"]==lineage["owner"] and
                view["now"]==observation["returned_at"]>=lineage["accepted"]["at"] and
                lineage["observation"]["wall_ns"]<=observation["returned_wall_ns"]<=raw["ended_ns"],"observed_admission_scope_changed")
            if end is not None:
                gate.require(actual["status"]=="complete_declared_lineage" and lineage["output_returned"]["wall_ns"]<=end,"return_before_completion")
            for child in actual["closure"]:
                gate.require(raw["roots"][child]["start_ns"]>=start and (end is None or
                    raw["roots"][child]["end_ns"] is not None and raw["roots"][child]["end_ns"]<=end),"child_outside_parent_lifetime")
            coverage.append({"start_ns":start,"end_ns":raw["ended_ns"] if end is None else end})
        for identity,operation in raw["protocol_lineage"].items():
            row=raw["outbox"][identity];ack=operation["terminal_delivered_ack"]
            if ack is not None:
                delivered=row.get("client_view",{}).get("last_delivered_ack")
                gate.require(delivered is not None and {**delivered,"request_id":identity}==ack,"terminal_ack_not_in_actual_client_query")
            if row["kind"]=="route":
                gate.require(all(row["payload"]["business_bag_id"]==raw["roots"][parent]["job"] for parent in operation["parent_roots"]),"route_parent_job_scope")
        gate.require(set(raw["outbox"])==set(raw["protocol_lineage"]),"unclassified_outbox")
        for root,saved in raw["root_reports"].items():
            job=raw["roots"][root]["job"]
            observed=lambda child: {r["business_bag_id"] for r in raw["admission_views"][child].get("jobs",[])} | {
                t["job_contract"]["business_bag_id"] for t in raw["admission_views"][child].get("trays",[]) if isinstance(t.get("job_contract"),dict)}
            verified=all(job in observed(child) for child in saved["closure"]) and all(
                row["kind"]=="route" for identity,row in raw["outbox"].items() if
                set(raw["protocol_lineage"][identity]["parent_roots"]) & set(saved["closure"]))
            gate.require(saved["job_scope_verified"] is verified,"unverified_job_scope_promoted")
        for call in raw["service_tape"]:
            gate.require(any(r["start_ns"]<=call["start_ns"]<=call["end_ns"]<=r["end_ns"] for r in coverage),"uncovered_service_call")
        if "timing" in raw:
            gate.require(not raw["timing"]["errors"],"native_capture_errors")
            for envelope in raw["timing"]["envelopes"]:
                gate.require(any(r["start_ns"]<=envelope["start_ns"]<=envelope["end_ns"]<=r["end_ns"] for r in coverage),"uncovered_native_call")
    except (ValueError,KeyError,TypeError,AttributeError,IndexError) as error:
        return {**unknown,"error":str(error)}
    result={}
    for root,record in raw["roots"].items():
        report=raw["root_reports"][root];end=record["end_ns"]
        closed=report["status"] in {"complete_declared_lineage","complete_declared_operation_lineage_job_scope_unverified"} and end is not None
        if raw["failures"]:closed=False
        duration=(end if closed else raw["ended_ns"])-record["start_ns"]+setup
        result[root]={"status":"complete_operation_compute_upper_bound" if closed else "unknown_open_or_failed",
            "complete_compute_upper_ns":duration if closed else None,"known_prefix_upper_ns":duration,
            "job_scope_verified":report["job_scope_verified"],"disposition":raw["lineage"][root]["decision_seal"],
            "logical_elapsed_seconds":None if not closed else raw["lineage"][root]["output_returned"]["at"]-raw["lineage"][root]["accepted"]["at"],
            "scope":"Full lifetime wall computation, no sleeps, plus full mandatory shared setup; shared work never divided."}
    return {"status":"complete_declared_operation_accounting","roots":result,"root_count":len(result),
        "closed_count":sum(r["status"]=="complete_operation_compute_upper_bound" for r in result.values()),
        "within100ms_complete_count":sum(r["complete_compute_upper_ns"] is not None and r["complete_compute_upper_ns"]<=100000000 for r in result.values()),
        "original_business_request_100ms_certified":False,"physics_or_gc_subtracted_ns":0}


def worker(args):
    plan=gate.read(args.output/"plan.json");reference=plan["contract_reference"]
    gate.require(not changed_sources(plan),"probe_sources_changed_before_worker")
    checked=abi.verify_contract(reference,require_runtime=True);native=native_host.load_native(checked["contract"]["binary"])
    rawdir=args.output/args.arm;rawdir.mkdir(exist_ok=False);reports={}
    for index,name in enumerate(CASES,1):
        gate.write(rawdir/(name+".started.json"),{"status":"unknown_in_progress","case":name,"declared_root_ids":list(CASES[name])})
        try:
            raw=run_case(native,name,reference,timed=args.arm=="timed",identity=index)
            gate.write(rawdir/(name+".json.gz"),raw);reports[name]=analyze_case(raw)
            if args.arm=="timed":
                timing=raw["timing"];partition=abi.analyze_native025_timing(timing["batches"],timing["envelopes"],reference)
                reports[name]["native_phase_partition"]=partition
        except Exception as error:
            reports[name]={"status":"unknown_failed_case","declared_root_ids":list(CASES[name]),"error":type(error).__name__+":"+str(error)}
        gate.write(rawdir/(name+".assessment.json"),reports[name])
    gate.write(rawdir/"assessment.json",reports)
    gate.write(rawdir/"worker_completion.json",{"source_changed":changed_sources(plan),"case_count":len(reports),
        "unknown_accounting_cases":[name for name,row in reports.items() if row["status"]!="complete_declared_operation_accounting"]})


def changed_sources(plan):
    return [name for name,digest in plan["source_sha256"].items() if not Path(name).is_file() or gate.sha(name)!=digest]


def execute_arm(output,arm, *, runner=subprocess.run, timeout=120.):
    """Persist every terminal launch outcome; timeout is never a success."""
    command=[sys.executable,"-m","scripts.experiments.g31_ics_circulation.probe_installed_operations","--output",str(output),"--arm",arm]
    started=time.perf_counter();record={"command":command,"timeout_seconds":timeout,"status":"unknown_failed_launch","exit_code":None}
    try:
        with (output/(arm+".stdout.log")).open("x") as out,(output/(arm+".stderr.log")).open("x") as err:
            run=runner(command,stdout=out,stderr=err,timeout=timeout)
        record.update(exit_code=run.returncode,status="process_exited" if run.returncode==0 else "process_failed")
    except subprocess.TimeoutExpired as error:record.update(status="hard_timeout",error=str(error))
    except OSError as error:record.update(status="failed_launch",error=str(error))
    record["wall_seconds"]=time.perf_counter()-started
    gate.write(output/(arm+".process.json"),record)
    return record


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--reference",type=Path);parser.add_argument("--execute",action="store_true");parser.add_argument("--arm",choices=("plain","timed"))
    args=parser.parse_args()
    if args.arm:worker(args);return
    args.output.mkdir(parents=True,exist_ok=False);reference=gate.read(args.reference);checked=abi.verify_contract(reference,require_runtime=True)
    modules=source_paths()
    archive=args.output/"source";archive.mkdir()
    for path in modules:
        target=archive/path.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
    (args.output/"accepted_contract.json").write_bytes(Path(reference["path"]).read_bytes())
    (args.output/"accepted_reference.json").write_bytes(args.reference.read_bytes())
    plan={**contract(),"contract_reference":reference,"accepted_reference_file_sha256":gate.sha(args.reference),
        "accepted_contract_sha256":reference["sha256"],"binary":checked["contract"]["binary"],
        "binary_sha256":checked["contract"]["binary_sha256"],"source_sha256":{str(p.resolve()):gate.sha(p) for p in modules}}
    gate.write(args.output/"plan.json",plan)
    if not args.execute:print("prepared_no_native_calls");return
    started=time.perf_counter()
    for arm in ("plain","timed"):execute_arm(args.output,arm)
    relative=[arm+"/"+name+".json.gz" for arm in ("plain","timed") for name in CASES]
    gate.write(args.output/"receipt.json",{"status":"executed_pending_independent_verification","source_changed":changed_sources(plan),
        "raw_sha256":{name:gate.sha(args.output/name) for name in relative if (args.output/name).is_file()},
        "missing_raw_cases":[name for name in relative if not (args.output/name).is_file()],
        "process_sha256":{arm:gate.sha(args.output/(arm+".process.json")) for arm in ("plain","timed")},
        "worker_completion_sha256":{arm:gate.sha(args.output/arm/"worker_completion.json") for arm in ("plain","timed") if (args.output/arm/"worker_completion.json").is_file()},
        "root_denominator_per_arm":contract()["root_count"],"wall_seconds":time.perf_counter()-started,
        "original_business_request_100ms_certified":False})
    from .verify_installed_operations import verify_or_unknown
    verified=verify_or_unknown(args.output);gate.write(args.output/"independent_verification.json",verified)
    print(verified["status"])
    if verified["status"]!="validated_finite_installed_operation_accounting":raise SystemExit(1)

if __name__=="__main__":main()
