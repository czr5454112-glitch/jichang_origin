"""Finite opt-in path-pool comparison. Preparation is pure; execution is explicit."""
from __future__ import annotations
import argparse
from collections import Counter
from contextlib import contextmanager, nullcontext
import copy
import gc
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

from . import event_protocol_control as control
from .native_host import load_native
from .reconstruct_native_tape import NativeTapeReconstructor
from .regional_path_pool import installed_regional_path_pool
from . import verify_regional_path_pool as verifier

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs/experiments/g31_ics_lt2_sustained_20261014"
SCHEMA = "g31.regional_path_pool.actual_pair.v1"
API_METHODS = frozenset({"physical_time", "protocol_demand_signature", "protocol_command", "protocol_request",
    "submit_protocol_command", "submit_protocol_transfer", "observe_protocol", "observe_protocol_control",
    "observe_protocol_control_policy", "observe_protocol_control_policy_recent", "advance_until_owner_notification", "result_at"})


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def gzread(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream: return json.load(stream)
def write(path, value):
    with Path(path).open("x", encoding="utf-8") as stream: json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
def gzwrite(path, value):
    with gzip.open(path, "xt", encoding="utf-8", compresslevel=1) as stream: json.dump(value, stream, ensure_ascii=False, allow_nan=False)
def ordered(value): return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
def imported_sources():
    return sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module, "__file__", None) and Path(module.__file__).suffix == ".py" and
        Path(module.__file__).resolve().is_relative_to(ROOT)})
def closure(): return {str(path.relative_to(ROOT)): sha(path) for path in imported_sources()}


def verify_pins(output, plan, *, runtime=False):
    verifier.verify_plan(output, plan)
    if runtime and closure() != plan["runtime_source_sha256"]: raise ValueError("pool_pair:runtime_source_closure")


class ApiTape:
    """Bounded synchronous raw recorder; explicit policy capabilities preserved."""
    def __init__(self, raw): self.raw=raw;self.stream=None;self.ordinal=0;self.segment=None
    def call(self, name, *args, **kwargs):
        if name not in API_METHODS or self.stream is None: raise ValueError("pool_pair:unrecorded_endpoint")
        ordinal=self.ordinal;self.ordinal+=1
        start=time.perf_counter_ns();before=self.raw.physical_time
        try:
            result=self.raw.physical_time if name=="physical_time" else getattr(self.raw,name)(*args,**kwargs)
        except BaseException as error:
            self.stream.write(ordered(dict(ordinal=ordinal,segment=self.segment,method=name,args=args,kwargs=kwargs,
                start_ns=start,end_ns=time.perf_counter_ns(),before=before,after=self.raw.physical_time,
                exception=dict(type=type(error).__name__,message=str(error))))+"\n")
            raise
        self.stream.write(ordered(dict(ordinal=ordinal,segment=self.segment,method=name,args=args,kwargs=kwargs,
            start_ns=start,end_ns=time.perf_counter_ns(),before=before,after=self.raw.physical_time,returned=result))+"\n")
        return result
    @property
    def physical_time(self): return self.call("physical_time")
    def observe_protocol_control_policy(self, owner): return self.call("observe_protocol_control_policy",owner)
    def observe_protocol_control_policy_recent(self, owner, validity): return self.call("observe_protocol_control_policy_recent",owner,validity)
    def __getattr__(self, name):
        if name in API_METHODS: return lambda *args,**kwargs:self.call(name,*args,**kwargs)
        raise AttributeError(name)


@contextmanager
def activation_capture(segment):
    """Measure whole activations and GC inside a declared capture envelope."""
    original=control._activate_owner;rows=[];collections=[];active=None;pending={};errors=[]
    def callback(phase, info):
        nonlocal active
        stamp=time.perf_counter_ns();generation=info["generation"]
        if phase=="start":
            if generation in pending: errors.append("nested_gc_start")
            pending[generation]=(stamp,active)
        elif phase=="stop":
            value=pending.pop(generation,None)
            if value is None: errors.append("unmatched_gc_stop")
            else: collections.append(dict(generation=generation,start_ns=value[0],end_ns=stamp,owner_context=value[1]))
        else: errors.append("unknown_gc_phase")
    def wrapped(client, owner, current, causes, **kwargs):
        nonlocal active
        active=dict(segment=segment,owner=owner,epoch=current["owner_epochs"].get(owner,0))
        start=time.perf_counter_ns();cpu=time.process_time_ns()
        try: return original(client,owner,current,causes,**kwargs)
        finally:
            row=dict(**active,start_ns=start,end_ns=time.perf_counter_ns(),cpu_ns=time.process_time_ns()-cpu)
            active=None;rows.append(row)
    envelope=dict(segment=segment,start_ns=time.perf_counter_ns(),gc_enabled=gc.isenabled(),rows=rows,collections=collections,errors=errors)
    if not envelope["gc_enabled"]: raise ValueError("pool_pair:gc_must_remain_enabled")
    gc.callbacks.append(callback);control._activate_owner=wrapped
    try: yield envelope
    finally:
        control._activate_owner=original;gc.callbacks.remove(callback)
        envelope["end_ns"]=time.perf_counter_ns()
        if pending: errors.append("unfinished_gc")


def public_views(raw, owners):
    return {owner:dict(full=raw.observe_protocol(owner),compact=raw.observe_protocol_control(owner),
        policy=raw.observe_protocol_control_policy(owner),recent=raw.observe_protocol_control_policy_recent(owner,120.)) for owner in owners}


def worker(output, arm):
    process_start=time.perf_counter_ns();cpu_start=time.process_time_ns()
    plan=read(output/"plan.json");verify_pins(output,plan,runtime=True)
    if read(output/"execution_claim.json")["plan_sha256"]!=sha(output/"plan.json"):raise ValueError("pool_pair:unclaimed_worker")
    directory=output/arm;directory.mkdir(exist_ok=False)
    write(directory/"started.json",dict(arm=arm,plan_sha256=sha(output/"plan.json"),process_start_ns=process_start,source_before=closure()))
    try:
        source=Path(plan["source"]);data=gzread(source/"input.json.gz")
        raw=load_native(plan["binary"]).NativeSession(data)
        replay=NativeTapeReconstructor(raw,event_budget=plan["limits"]["event_budget"])
        reconstruction_start=time.perf_counter_ns()
        for index in range(plan["cut"]+1):
            part=gzread(source/"segments"/f"{index:04d}.json.gz");replay.replay_part(part)
        reconstruction=replay.finish(plan["known_entry_native_seal"]);raw=replay.verified_session()
        reconstruction["wall_ns"]=time.perf_counter_ns()-reconstruction_start
        write(directory/"reconstruction.json",reconstruction)
        offset=replay.next_trace;state=part["controller_state"];del replay,part
        config=dict(state["config"]);owners=config.pop("owners")
        gzwrite(directory/"entry_views.json.gz",public_views(raw,owners))
        tape=ApiTape(raw);windows=[]
        context=installed_regional_path_pool() if arm=="pooled" else nullcontext(None)
        with context as pool:
            for spec in plan["continuation"]:
                index=spec["index"];tape.segment=index
                outer_start=time.perf_counter_ns();outer_cpu=time.process_time_ns()
                with gzip.open(directory/f"api_{index:04d}.jsonl.gz","xt",encoding="utf-8",compresslevel=1) as stream:
                    tape.stream=stream
                    with activation_capture(index) as capture:
                        result=control.run_event_protocol_control(tape,owners,horizon=spec["requested_horizon"],
                            max_activations=spec["activations"],event_budget=plan["limits"]["event_budget"],
                            state=state,_consume_state=True,**config)
                    tape.stream=None
                control_end=time.perf_counter_ns()
                for field in ("control_records","native_batches"):
                    for row in result[field]: row["trace_sequence"]+=offset
                offset+=len(result["control_records"])+len(result["native_batches"])
                result["native_state_sha256"]=raw.offline_state_sha256()
                # Preserve the original saved clock fields in expected artifacts;
                # a separate closed verifier excludes only those measured values.
                gzwrite(directory/f"segment_{index:04d}.json.gz",result)
                gzwrite(directory/f"capture_{index:04d}.json.gz",capture)
                windows.append(dict(index=index,start_ns=outer_start,control_end_ns=control_end,
                    end_ns=time.perf_counter_ns(),cpu_ns=time.process_time_ns()-outer_cpu,
                    pool=pool.snapshot() if pool else None))
                state=result["controller_state"];del result,capture
        final_seal=raw.offline_state_sha256();gzwrite(directory/"exit_views.json.gz",public_views(raw,owners))
        if raw.offline_state_sha256()!=final_seal: raise ValueError("pool_pair:read_views_mutated_seal")
        # Main session remains at the exact original budget cut. A separate
        # offline fork may drain that timestamp to render a full-population view.
        diagnostic_start=time.perf_counter_ns();diagnostic=raw.fork();fork_before=diagnostic.offline_state_sha256()
        offline_result=diagnostic.result_at(diagnostic.physical_time)
        fork_after=diagnostic.offline_state_sha256()
        gzwrite(directory/"offline_result.json.gz",offline_result)
        main_seal_after=raw.offline_state_sha256()
        if main_seal_after!=final_seal:raise ValueError("pool_pair:fork_mutated_parent")
        diagnostic_end=time.perf_counter_ns()
        verify_pins(output,plan,runtime=True)
        evidence={path.name:sha(path) for path in directory.iterdir() if path.is_file()}
        manifest=dict(schema=SCHEMA,status="complete_pair_arm",arm=arm,source_after=closure(),source_changed=[],
            plan_sha256=sha(output/"plan.json"),evidence_sha256=evidence,windows=windows,api_rows=tape.ordinal,
            final_native_seal=final_seal,physical_time=raw.physical_time,offered_total=len(data["jobs"]),
            diagnostic_fork=dict(before_seal=fork_before,after_seal=fork_after,
                main_seal_after=main_seal_after,start_ns=diagnostic_start,end_ns=diagnostic_end,
                scope="offline same-timestamp-drained fork only; not the original main-session budget cut",
                job_count=len(offline_result["jobs"]),status_counts=dict(Counter(row["status"] for row in offline_result["jobs"]))),
            process_scope_start_ns=process_start,process_scope_end_ns=time.perf_counter_ns(),
            process_cpu_ns=time.process_time_ns()-cpu_start,complete_business_100ms_certified=False)
        write(directory/"manifest.json",manifest)
    except BaseException:
        write(directory/"failure.json",dict(status="unknown_worker_failure",traceback=traceback.format_exc(),
            process_scope_start_ns=process_start,process_scope_end_ns=time.perf_counter_ns()))
        raise


def prepare(output):
    proposal_dir=BASE/"regional_path_pool_prepare_001";plan=read(proposal_dir/"plan.json")
    output.mkdir(parents=True,exist_ok=False)
    runtime=closure()
    extra=[ROOT/"tests/test_g31_circulation_regional_path_pool.py",ROOT/"tests/test_g31_circulation_regional_path_pool_pair.py"]
    frozen=dict(runtime)
    for path in extra: frozen[str(path.relative_to(ROOT))]=sha(path)
    for relative in frozen:
        target=output/"source"/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/relative,target)
    plan.update(schema=SCHEMA,status="prepared_native_execution_held",output=str(output.resolve()),
        python_executable=str(Path(sys.executable).resolve()),python_version=sys.version,
        source_sha256=frozen,runtime_source_sha256=runtime,driver_and_independent_verifier_pending=False,
        arms=["original","pooled"],proposal_sha256=sha(proposal_dir/"plan.json"),
        per_arm="Independent worker process and NativeSession; replay original input through all ten shards and verify original024 seal separately. No shared checkpoint/mutable cache across arms.",
        diagnostic_result_scope="After final original seal and views, fork only for result_at(current_time); report any same-time drain separately. Main session does not advance.")
    write(output/"plan.json",plan);verify_pins(output,plan,runtime=True)
    write(output/"prepared.json",dict(status=plan["status"],native_calls=0,plan_sha256=sha(output/"plan.json")))


def execute(output):
    begin=time.perf_counter()
    plan=read(output/"plan.json");verify_pins(output,plan,runtime=True)
    write(output/"execution_claim.json",dict(plan_sha256=sha(output/"plan.json"),started=time.time()))
    prelaunch_seconds=time.perf_counter()-begin;runs=[]
    for arm in plan["arms"]:
        remaining=plan["limits"]["native_parent_hard_timeout_seconds"]-(time.perf_counter()-begin)
        command=[sys.executable,"-m","scripts.experiments.g31_ics_circulation.run_regional_path_pool","--output",str(output),"--worker",arm]
        start=time.perf_counter();status="not_started_budget_exhausted";code=None
        if remaining>0:
            try:
                with (output/f"{arm}.log").open("xb") as stream:
                    completed=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=remaining,check=False)
                code=completed.returncode;status="finished" if code==0 else "unknown_worker_nonzero"
            except subprocess.TimeoutExpired: status="unknown_hard_timeout"
            except BaseException:
                status="unknown_parent_launch_failure"
                (output/f"{arm}_launch_error.txt").write_text(traceback.format_exc(),encoding="utf-8")
        row=dict(arm=arm,command=command,status=status,exit_code=code,wall_seconds=time.perf_counter()-start)
        write(output/f"{arm}_process.json",row);runs.append(row)
    receipt=dict(schema=SCHEMA,status="completed_workers_verification_pending",runs=runs,
        process_wall_seconds=time.perf_counter()-begin,prelaunch_pin_and_claim_seconds=prelaunch_seconds,
        parent_clock_scope="execute entry before plan/pins/claim through evidence hashing; Python interpreter startup/imports excluded, actual worker subprocess times include their startup/imports",
        plan_sha256=sha(output/"plan.json"),complete_business_100ms_certified=False)
    remaining=plan["limits"]["native_parent_hard_timeout_seconds"]-(time.perf_counter()-begin)
    verification_command=[sys.executable,"-m","scripts.experiments.g31_ics_circulation.verify_regional_path_pool",
        "--output",str(output),"--report",str(output/"independent_verification.json")]
    verification_status="not_started_budget_exhausted";verification_exit=None
    if remaining>0:
        try:
            with (output/"verification.log").open("xb") as stream:
                verified=subprocess.run(verification_command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=remaining,check=False)
            verification_exit=verified.returncode;verification_status="finished" if verification_exit==0 else "failed"
            if verification_exit==0:
                receipt["verification"]=read(output/"independent_verification.json");receipt["status"]="verified_exact_pair"
        except subprocess.TimeoutExpired: verification_status="unknown_hard_timeout"
        except BaseException: verification_status="unknown_launch_failure";receipt["verification_error"]=traceback.format_exc()
    receipt["verification_process"]=dict(command=verification_command,status=verification_status,exit_code=verification_exit)
    receipt["process_wall_seconds"]=time.perf_counter()-begin
    if receipt["status"]!="verified_exact_pair" or receipt["process_wall_seconds"]>plan["limits"]["native_parent_hard_timeout_seconds"]:
        receipt["status"]="unknown_or_mismatch"
    receipt["evidence_sha256"]={str(path.relative_to(output)):sha(path) for path in output.rglob("*") if path.is_file() and "source" not in path.relative_to(output).parts}
    receipt["process_wall_seconds"]=time.perf_counter()-begin
    if receipt["process_wall_seconds"]>plan["limits"]["native_parent_hard_timeout_seconds"]:receipt["status"]="unknown_or_mismatch"
    write(output/"receipt.json",receipt)
    if receipt["status"]!="verified_exact_pair": raise SystemExit(1)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    group=parser.add_mutually_exclusive_group(required=True);group.add_argument("--prepare",action="store_true")
    group.add_argument("--execute",action="store_true");group.add_argument("--worker",choices=("original","pooled"))
    args=parser.parse_args();output=args.output.resolve()
    if args.prepare: prepare(output)
    elif args.execute: execute(output)
    else: worker(output,args.worker)


if __name__=="__main__": main()
