"""Independent offline verifier for the closed 1,000-activation path-pool pair."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[3]
BASE=ROOT/"outputs/experiments/g31_ics_lt2_sustained_20261014"
BINARY_SHA="c7eab9d81e3e930a3e7f2f3a320b4c92b1c1c2e5a0c07db9c4050b536d821943"
INPUT_SHA="d37118333de2aa60fb5e9b9d41bab53cccb7ddbab5842862b88a2818e08709a1"
METHODS=frozenset({"physical_time","protocol_demand_signature","protocol_command","protocol_request",
    "submit_protocol_command","submit_protocol_transfer","observe_protocol","observe_protocol_control",
    "observe_protocol_control_policy","observe_protocol_control_policy_recent","advance_until_owner_notification","result_at"})
def need(ok,why):
    if not ok: raise ValueError("pool_pair_verify:"+why)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def gzread(path):
    with gzip.open(path,"rt",encoding="utf-8") as stream:return json.load(stream)
def ordered(value):return json.dumps(value,ensure_ascii=False,separators=(",",":"),allow_nan=False)
def exact(left,right,why):need(ordered(left)==ordered(right),why)
def seal(value):return type(value) is str and re.fullmatch("[0-9a-f]{64}",value) is not None
def nonnegative(value):return type(value) in (int,float) and math.isfinite(value) and value>=0


def normalize_part(part):
    # Only exact documented locations of measured clocks; never remove fields
    # named similarly inside public observations, ACKs, causes or payloads.
    out={key:value for key,value in part.items() if key not in {"wall_seconds","diagnostic_seal_wall_ms"}}
    for field,clock_keys in (("control_records",{"compute_wall_ms","compute_cpu_ms"}),
            ("native_batches",{"wall_ms","cpu_ms"}),("client_calls",{"submit_compute_ms"})):
        out[field]=[{key:value for key,value in row.items() if key not in clock_keys} for row in part[field]]
    return out


def normalize_result(value):
    out=dict(value);out.pop("native_event_ms",None)
    if "native_summary" in out:out["native_summary"]={k:v for k,v in out["native_summary"].items() if k!="runtime_seconds"}
    if "advance" in out:out["advance"]={k:v for k,v in out["advance"].items() if k!="wall_seconds"}
    return out


def verify_plan(output,plan):
    need(plan.get("schema")=="g31.regional_path_pool.actual_pair.v1" and plan.get("arms")==["original","pooled"],"plan_domain")
    need(plan["cut"]==9 and plan["total_activations_per_arm"]==1000 and plan["limits"]==dict(
        native_workers=1,native_parent_hard_timeout_seconds=600,max_graphs=4,max_paths_per_graph=256,event_budget=1000000),"limits")
    need([r["index"] for r in plan["continuation"]]==[10,11] and all(r["activations"]==500 for r in plan["continuation"]),"continuation_domain")
    need(plan["original_input_sha256"]==INPUT_SHA and plan["original_offered_jobs"]==28506,"input_contract")
    source=Path(plan["source"]);need(source.resolve()==(BASE/"full_stream_native024_001/full1x").resolve(),"original_source")
    need(sha(source/"input.json.gz")==INPUT_SHA,"actual_input")
    need(plan["binary_sha256"]==BINARY_SHA and sha(plan["binary"])==BINARY_SHA,"binary")
    need(Path(plan["python_executable"]).resolve()==Path(sys.executable).resolve() and plan["python_version"]==sys.version,"python_identity")
    proposal=BASE/"regional_path_pool_prepare_001/plan.json"
    need(sha(proposal)==plan["proposal_sha256"],"proposal_binding")
    original=read(proposal)
    exact(plan["pins"],original["pins"],"pin_domain")
    exact(plan["compiled_archive_sha256"],original["compiled_archive_sha256"],"compiled_domain")
    exact(plan["continuation"],original["continuation"],"actual_original_exit_seals")
    need(plan["known_entry_native_seal"]==original["known_entry_native_seal"] and seal(plan["known_entry_native_seal"]),"entry_seal")
    for path,digest in {**plan["pins"],**plan["compiled_archive_sha256"]}.items():need(seal(digest) and sha(path)==digest,"evidence_pin:"+path)
    required={"scripts/experiments/g31_ics_circulation/"+name for name in (
        "run_regional_path_pool.py","verify_regional_path_pool.py","regional_path_pool.py","event_protocol_control.py",
        "protocol_control.py","analytic_control.py","regional_control.py","native_host.py","reconstruct_native_tape.py")}
    normalized={Path(name).as_posix() for name in plan["runtime_source_sha256"]}
    need(required<=normalized and set(plan["runtime_source_sha256"])<=set(plan["source_sha256"]),"source_domain")
    for name,digest in plan["source_sha256"].items():
        path=Path(name);need(not path.is_absolute() and not path.drive and ".." not in path.parts and seal(digest),"source_path")
        need(sha(ROOT/path)==digest and sha(output/"source"/path)==digest,"source_archive:"+name)
    need(all(plan["source_sha256"][name]==digest for name,digest in plan["runtime_source_sha256"].items()),"source_crosslink")


def api_semantic(row):return {k:v for k,v in row.items() if k not in {"start_ns","end_ns"}}


def validate_api_rows(rows,part,capture,start_ordinal,index,owners):
    need(len(capture["rows"])==len(part["control_records"]),"activation_count")
    need(capture["segment"]==index and capture["gc_enabled"] is True and capture["errors"]==[],"capture_state")
    need(type(capture["start_ns"]) is int and type(capture["end_ns"]) is int and 0<=capture["start_ns"]<=capture["end_ns"],"capture_envelope")
    for record,span in zip(part["control_records"],capture["rows"]):
        need(span["owner"]==record["owner_id"] and span["epoch"]==record["owner_epoch"] and span["segment"]==index,"owner_identity")
        need(capture["start_ns"]<=span["start_ns"]<=span["end_ns"]<=capture["end_ns"] and nonnegative(span["cpu_ns"]),"owner_interval")
    for left,right in zip(capture["rows"],capture["rows"][1:]):need(left["end_ns"]<=right["start_ns"],"overlapping_owners")
    for event in capture["collections"]:
        need(event["generation"] in (0,1,2) and capture["start_ns"]<=event["start_ns"]<=event["end_ns"]<=capture["end_ns"],"gc_interval")
        if event["owner_context"] is not None:
            identity=event["owner_context"]
            need(any(all(row[k]==identity[k] for k in ("segment","owner","epoch")) for row in capture["rows"]),"gc_owner")
    submits=[];queries=[];advances=[];policy_calls=0
    for offset,row in enumerate(rows):
        need(row["ordinal"]==start_ordinal+offset and row["segment"]==index and row["method"] in METHODS,"api_inventory")
        need("exception" not in row and "returned" in row,"api_exception_or_missing_return")
        need(type(row["args"]) is list and type(row["kwargs"]) is dict and
            capture["start_ns"]<=row["start_ns"]<=row["end_ns"]<=capture["end_ns"],"api_envelope")
        if offset:need(rows[offset-1]["end_ns"]<=row["start_ns"],"api_overlap")
        method=row["method"]
        if method=="physical_time":need(row["args"]==[] and row["kwargs"]=={} and row["returned"]==row["before"]==row["after"],"clock_read")
        elif method.startswith("submit_protocol_"):
            need(len(row["args"])==1 and row["kwargs"]=={},"submit_arguments")
            submits.append(("transfer" if method.endswith("transfer") else "command",row["args"][0],row["returned"],row["before"]))
        elif method in {"protocol_command","protocol_request"}:
            need(len(row["args"])==2 and row["kwargs"]=={},"query_arguments")
            queries.append((row["args"][0],row["args"][1],row["returned"],method))
        elif method=="advance_until_owner_notification":advances.append(row)
        elif method=="observe_protocol_control_policy_recent":policy_calls+=1
        elif method=="result_at":raise ValueError("pool_pair_verify:result_at_in_budget_cut_controller")
        if method!="advance_until_owner_notification":need(row["before"]==row["after"],"nonadvance_changed_clock")
    need(policy_calls>=len(part["control_records"]),"explicit_recent_projection_missing")
    expected_submits=[("transfer" if r["kind"]=="transfer" else "command",r["request"],r["reply"],r["at"]) for r in part["client_calls"]]
    exact(submits,expected_submits,"submission_tape")
    expected_queries=[(r["owner_id"],q["request_id"],q["view"],"protocol_request" if q["kind"]=="transfer" else "protocol_command") for r in part["control_records"] for q in r["refreshed"]]
    exact(queries,expected_queries,"query_tape")
    need(len(advances)==len(part["native_batches"]),"advance_count")
    for call,batch in zip(advances,part["native_batches"]):
        need(len(call["args"])==3 and call["args"][0]==owners and call["args"][2]==batch["requested_public_deadline"] and call["kwargs"]=={"max_events":1000000},"advance_arguments")
        response=call["returned"]
        need(call["before"]==batch["start_at"] and call["after"]==response["physical_time"]==batch["end_at"] and
            response["status"]==batch["status"] and response["timestamp_complete"]==batch["timestamp_complete"],"advance_response")
    return start_ordinal+len(rows)


def load_api(path):
    with gzip.open(path,"rt",encoding="utf-8") as stream:return [json.loads(line) for line in stream]


def audit_arm(output,plan,arm):
    directory=output/arm;process=read(output/f"{arm}_process.json");manifest=read(directory/"manifest.json")
    need(process["arm"]==arm and process["status"]=="finished" and process["exit_code"]==0,"worker_exit")
    exact(process["command"],[plan["python_executable"],"-m","scripts.experiments.g31_ics_circulation.run_regional_path_pool",
        "--output",str(output.resolve()),"--worker",arm],"worker_command")
    need(nonnegative(process["wall_seconds"]),"worker_wall")
    need(manifest["status"]=="complete_pair_arm" and manifest["arm"]==arm and manifest["source_changed"]==[] and
        manifest["plan_sha256"]==sha(output/"plan.json"),"manifest")
    exact(manifest["source_after"],plan["runtime_source_sha256"],"runtime_closure_after")
    started=read(directory/"started.json");exact(started["source_before"],plan["runtime_source_sha256"],"runtime_closure_before")
    need(started["arm"]==arm and started["plan_sha256"]==manifest["plan_sha256"] and
        started["process_start_ns"]==manifest["process_scope_start_ns"],"start_manifest_binding")
    expected_names={"started.json","reconstruction.json","entry_views.json.gz","exit_views.json.gz","offline_result.json.gz"}
    expected_names.update(f"{kind}_{index:04d}{suffix}" for index in (10,11) for kind,suffix in (
        ("api",".jsonl.gz"),("segment",".json.gz"),("capture",".json.gz")))
    need(set(manifest["evidence_sha256"])==expected_names,"raw_evidence_inventory")
    for name,digest in manifest["evidence_sha256"].items():need(sha(directory/name)==digest,"raw_sha:"+name)
    reconstruction=read(directory/"reconstruction.json")
    need(reconstruction["status"]=="verified_against_known_native_seal" and reconstruction["native_state_sha256"]==plan["known_entry_native_seal"] and reconstruction["parts"]==10,"entry_reconstruction")
    need(nonnegative(reconstruction["wall_ns"]),"reconstruction_wall")
    for key in ("process_scope_start_ns","process_scope_end_ns","process_cpu_ns"):
        need(type(manifest[key]) is int and manifest[key]>=0,"process_clock")
    need(len(manifest["windows"])==2,"window_inventory")
    for window in manifest["windows"]:
        need(all(type(window[key]) is int and window[key]>=0 for key in ("start_ns","control_end_ns","end_ns","cpu_ns")),"window_clock")
    need(manifest["windows"][0]["end_ns"]<=manifest["windows"][1]["start_ns"],"window_overlap")
    rows_count=0;outer=[];gc_ns=0;part_hashes=[];api_hashes=[]
    for spec,window in zip(plan["continuation"],manifest["windows"]):
        index=spec["index"];part=gzread(directory/f"segment_{index:04d}.json.gz")
        original=gzread(Path(plan["source"])/"segments"/f"{index:04d}.json.gz")
        exact(normalize_part(part),normalize_part(original),"original_shard:"+str(index))
        need(part["result"] is None and len(part["control_records"])==500 and part["native_state_sha256"]==spec["original_exit_native_seal"],"sealed_cut")
        capture=gzread(directory/f"capture_{index:04d}.json.gz");rows=load_api(directory/f"api_{index:04d}.jsonl.gz")
        rows_count=validate_api_rows(rows,part,capture,rows_count,index,plan["controller_config"]["owners"])
        need(window["index"]==index and window["start_ns"]<=capture["start_ns"]<=capture["end_ns"]<=window["control_end_ns"]<=window["end_ns"],"window_coverage")
        outer.extend((r["end_ns"]-r["start_ns"])/1e6 for r in capture["rows"])
        gc_ns+=sum(r["end_ns"]-r["start_ns"] for r in capture["collections"])
        part_hashes.append(hashlib.sha256(ordered(normalize_part(part)).encode()).hexdigest())
        api_hashes.append(hashlib.sha256(ordered([api_semantic(row) for row in rows]).encode()).hexdigest())
        del rows,part,original,capture
    need(len(manifest["windows"])==2 and rows_count==manifest["api_rows"] and len(outer)==1000,"full_denominator")
    need(manifest["offered_total"]==28506 and manifest["final_native_seal"]==plan["continuation"][-1]["original_exit_native_seal"],"final_seal")
    result=gzread(directory/"offline_result.json.gz");data=gzread(Path(plan["source"])/"input.json.gz")
    exact([r["business_bag_id"] for r in result["jobs"]],[r["business_bag_id"] for r in data["jobs"]],"offline_all_offered")
    fork=manifest["diagnostic_fork"]
    need(fork["before_seal"]==manifest["final_native_seal"] and seal(fork["after_seal"]) and
        fork["main_seal_after"]==manifest["final_native_seal"] and fork["job_count"]==28506,"fork_identity")
    need(all(type(fork[key]) is int and fork[key]>=0 for key in ("start_ns","end_ns")) and
        manifest["windows"][-1]["end_ns"]<=fork["start_ns"]<=fork["end_ns"]<=manifest["process_scope_end_ns"],"fork_clock")
    exact(fork["status_counts"],dict(Counter(r["status"] for r in result["jobs"])),"fork_counts")
    need(result["advance"]["status"]=="reached" and result["advance"]["horizon_complete"] is True and
        result["advance"]["physical_time"]==manifest["physical_time"]==plan["continuation"][-1]["expected_physical_time"],"diagnostic_drain")
    need(manifest["process_scope_start_ns"]<=manifest["windows"][0]["start_ns"] and
        manifest["windows"][-1]["end_ns"]<=manifest["process_scope_end_ns"],"process_scope")
    return dict(arm=arm,api_rows=rows_count,ordered_api_hashes=api_hashes,ordered_part_hashes=part_hashes,
        final_native_seal=manifest["final_native_seal"],full_offered=28506,owner_activations=1000,
        owner_outer_max_ms=max(outer),owner_outer_over_100ms=sum(value>100 for value in outer),
        controller_window_ms=sum(w["control_end_ns"]-w["start_ns"] for w in manifest["windows"])/1e6,
        complete_worker_process_ms=process["wall_seconds"]*1000,gc_capture_ms=gc_ns/1e6,
        pool_final=manifest["windows"][-1]["pool"],
        diagnostic_result_sha256=hashlib.sha256(ordered(normalize_result(result)).encode()).hexdigest())


def verify_saved(output):
    output=Path(output);plan=read(output/"plan.json");verify_plan(output,plan)
    arms=[audit_arm(output,plan,arm) for arm in ("original","pooled")]
    for name in ("entry_views.json.gz","exit_views.json.gz"):
        exact(gzread(output/"original"/name),gzread(output/"pooled"/name),"ordered_public_views:"+name)
    for key in ("ordered_api_hashes","ordered_part_hashes","final_native_seal","diagnostic_result_sha256"):
        exact(arms[0][key],arms[1][key],"pair:"+key)
    return dict(status="verified_exact_pair",arms=arms,complete_business_100ms_certified=False,
        timing_scope="All measured controller/key/tracing/GC costs retained; worker setup/reconstruction/export separately retained. Owner activations are not a business-request certificate.")


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--report",type=Path,required=True);args=parser.parse_args()
    result=verify_saved(args.output)
    with args.report.open("x",encoding="utf-8") as stream:json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False)


if __name__=="__main__":main()
