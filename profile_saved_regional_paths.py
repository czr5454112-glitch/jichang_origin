"""Pure saved-API replay and routing-cost diagnosis; never loads a native binary."""
from contextlib import contextmanager
from collections import Counter
import argparse
import copy
import cProfile
import gc
import gzip
import hashlib
import json
from pathlib import Path
import pstats
import shutil
import statistics
import sys
import time

from scripts.experiments.g31_ics_circulation import event_protocol_control as control
from scripts.experiments.g31_ics_circulation import protocol_control
from scripts.experiments.g31_ics_circulation.regional_control import _ObservationRouting
from scripts.experiments.g31_ics_circulation.regional_path_pool import RegionalPathPool, public_routing_key
from scripts.experiments.g31_ics_circulation import verify_regional_path_pool as verifier

ROOT=Path(__file__).resolve().parent
FIELDS=("owner_id","now","node_contracts","node_records","edge_records","edge_contracts","known_faults")
METHODS=verifier.METHODS
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def gzread(path):
    with gzip.open(path,"rt",encoding="utf-8") as stream:return json.load(stream)
def write(path,value):
    with Path(path).open("x",encoding="utf-8") as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
def ordered(value):return json.dumps(value,ensure_ascii=False,separators=(",",":"),allow_nan=False)
def need(ok,why):
    if not ok:raise ValueError("saved_routing:"+why)


class Replay:
    def __init__(self):self.stream=None;self.ordinal=0;self.segment=None
    def call(self,method,*args,**kwargs):
        need(method in METHODS and self.stream is not None,"endpoint")
        text=self.stream.readline();need(bool(text),"missing_api")
        row=json.loads(text)
        need(row["ordinal"]==self.ordinal and row["segment"]==self.segment,"ordinal")
        need(row["method"]==method and ordered(row["args"])==ordered(args) and ordered(row["kwargs"])==ordered(kwargs),"api_arguments")
        need("exception" not in row and "returned" in row,"api_exception")
        self.ordinal+=1
        return row["returned"]
    @property
    def physical_time(self):return self.call("physical_time")
    def observe_protocol_control_policy(self,owner):return self.call("observe_protocol_control_policy",owner)
    def observe_protocol_control_policy_recent(self,owner,validity):return self.call("observe_protocol_control_policy_recent",owner,validity)
    def __getattr__(self,name):
        if name in METHODS:return lambda *args,**kwargs:self.call(name,*args,**kwargs)
        raise AttributeError(name)


@contextmanager
def capture_paths(frames):
    original=protocol_control._ObservationRouting
    need(original is _ObservationRouting,"factory_identity")
    class Captured:
        def __init__(self,observation):
            self.routing=original(observation)
            self.frame={"owner":observation["owner_id"],"now":observation["now"],"calls":[]}
            frames.append(self.frame)
        def path(self,observation,source,goal):
            result=self.routing.path(observation,source,goal)
            if "projection" not in self.frame:
                self.frame["projection"]=copy.deepcopy({key:observation[key] for key in FIELDS if key in observation})
            self.frame["calls"].append({"source":source,"goal":goal,"path":list(result)})
            return result
    protocol_control._ObservationRouting=Captured
    try:yield
    finally:protocol_control._ObservationRouting=original


def extract(source,frames):
    plan=read(source/"plan.json");verifier.verify_plan(source,plan)
    receipt=read(source/"receipt.json")
    need(receipt["status"]=="verified_exact_pair","native_pair_not_verified")
    manifest=read(source/"original/manifest.json")
    for name,digest in manifest["evidence_sha256"].items():need(sha(source/"original"/name)==digest,"raw_pin:"+name)
    part=gzread(Path(plan["source"])/"segments/0009.json.gz")
    state=part["controller_state"];offset=max(r["trace_sequence"] for k in ("control_records","native_batches") for r in part[k])+1
    config=dict(state["config"]);owners=config.pop("owners");tape=Replay();checks=[]
    with capture_paths(frames):
        for spec in plan["continuation"]:
            index=spec["index"];tape.segment=index
            with gzip.open(source/"original"/f"api_{index:04d}.jsonl.gz","rt",encoding="utf-8") as stream:
                tape.stream=stream
                actual=control.run_event_protocol_control(tape,owners,horizon=spec["requested_horizon"],
                    max_activations=spec["activations"],event_budget=plan["limits"]["event_budget"],state=state,_consume_state=True,**config)
                need(not stream.readline(),"unused_api_tail")
                tape.stream=None
            for field in ("control_records","native_batches"):
                for row in actual[field]:row["trace_sequence"]+=offset
            offset+=len(actual["control_records"])+len(actual["native_batches"])
            expected=gzread(source/"original"/f"segment_{index:04d}.json.gz")
            expected.pop("native_state_sha256")  # This pure replay cannot recompute a native seal.
            need(ordered(verifier.normalize_part(actual))==ordered(verifier.normalize_part(expected)),"controller_output:"+str(index))
            checks.append({"segment":index,"exact_controller_output":True,"api_ordinal_end":tape.ordinal})
            state=actual["controller_state"]
    need(tape.ordinal==manifest["api_rows"]==24571 and len(frames)==1000,"complete_denominator")
    return checks


def route_run(frames,pooled):
    need(gc.isenabled(),"gc_disabled")
    pool=RegionalPathPool() if pooled else None;calls=0
    begin=time.perf_counter_ns();cpu=time.process_time_ns()
    for frame in frames:
        if not frame["calls"]:continue
        observation=frame["projection"]
        routing=pool.handle(observation) if pool else _ObservationRouting(observation)
        for request in frame["calls"]:
            path=routing.path(observation,request["source"],request["goal"])
            need(list(path)==request["path"],"path_mismatch")
            calls+=1
    return {"pooled":pooled,"wall_ns":time.perf_counter_ns()-begin,"cpu_ns":time.process_time_ns()-cpu,
        "calls":calls,"pool":pool.snapshot() if pool else None}


def profile(frames,pooled,path):
    profiler=cProfile.Profile();profiler.enable();result=route_run(frames,pooled);profiler.disable();profiler.dump_stats(str(path))
    rows=[]
    for (filename,line,name),(primitive,total,own,cumulative,_) in pstats.Stats(profiler).stats.items():
        if "g31_ics_circulation" in filename or name=="route_run":
            rows.append(dict(file=filename,line=line,function=name,primitive_calls=primitive,total_calls=total,
                own_seconds=own,cumulative_seconds=cumulative))
    return {"profiled_run":result,"functions":sorted(rows,key=lambda r:-r["cumulative_seconds"])}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--source",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();source=args.source.resolve();output=args.output.resolve();output.mkdir(exist_ok=False)
    paths=sorted({Path(module.__file__).resolve() for module in list(sys.modules.values()) if getattr(module,"__file__",None)
        and Path(module.__file__).suffix==".py" and Path(module.__file__).resolve().is_relative_to(ROOT)}|{Path(__file__).resolve()})
    before={str(path.relative_to(ROOT)):sha(path) for path in paths}
    for path in paths:
        destination=output/"source"/path.relative_to(ROOT);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination)
    write(output/"started.json",dict(native_executions=0,source= str(source),source_sha256=before,
        input_receipt_sha256=sha(source/"receipt.json"),scope="pure exact API replay followed by routing-kernel diagnostic; no complete request timing"))
    frames=[];begin=time.perf_counter_ns();checks=extract(source,frames);extract_ns=time.perf_counter_ns()-begin
    with gzip.open(output/"actual_routing_calls.json.gz","xt",encoding="utf-8",compresslevel=1) as stream:json.dump(frames,stream,ensure_ascii=False,allow_nan=False)
    identities=Counter();distinct_pairs=Counter();empty=0
    for frame in frames:
        if not frame["calls"]:empty+=1;continue
        value=public_routing_key(frame["projection"]);need(value is not None,"unsupported_actual_projection")
        # Key diagnostic is outside kernel timing; immutable key repr includes exact float bytes.
        digest=hashlib.sha256(repr(value[0]).encode()).hexdigest();identities[digest]+=1
        for call in frame["calls"]:distinct_pairs[(frame["owner"],call["source"],call["goal"])]+=1
    results=[]
    for repeat in range(3):
        for pooled in ((False,True) if repeat%2==0 else (True,False)):
            results.append(dict(repeat=repeat,**route_run(frames,pooled)))
    profiles={name:profile(frames,pooled,output/(name+".prof")) for name,pooled in (("original",False),("pooled",True))}
    after={str(path.relative_to(ROOT)):sha(path) for path in paths};need(before==after,"source_changed")
    receipt=dict(status="pure_actual_api_replay_passed",native_executions=0,complete_business_100ms_certified=False,
        scope="All 1000 actual activation routing requests; kernel profile excludes native/controller/JSON work and cannot be added to native elapsed totals.",
        source_before=before,source_after=after,source_changed=[],input_receipt_sha256=sha(source/"receipt.json"),
        extraction_ns=extract_ns,replay_checks=checks,handles=len(frames),no_route_handles=empty,graph_keys=dict(identities),
        distinct_pairs=[dict(owner=k[0],source=k[1],goal=k[2],calls=v) for k,v in distinct_pairs.items()],
        samples=results,median_wall_ms={name:statistics.median(r["wall_ns"] for r in results if r["pooled"]==flag)/1e6 for name,flag in (("original",False),("pooled",True))},
        profiles=profiles,gc_enabled=True,raw_calls_sha256=sha(output/"actual_routing_calls.json.gz"))
    write(output/"receipt.json",receipt)


if __name__=="__main__":main()
