"""Pure exact API replay and double-copy kernel over all 5013 real queries."""
import argparse
from collections import Counter
import copy
import gc
import gzip
import json
from pathlib import Path
import shutil
import statistics
import sys
import time

import profile_saved_regional_paths as prior
from scripts.experiments.g31_ics_circulation.protocol_query_copy import query_view_copy,installed_query_view_copy

ROOT=Path(__file__).resolve().parent


def validate_pairs(rows,pairs):
    prior.need(len(rows)==len(pairs),"copy_denominator")
    for source,(left,right) in zip(rows,pairs):
        prior.need(prior.ordered(source)==prior.ordered(left)==prior.ordered(right),"exact_copy_values_order")
        prior.need(left is not right and left is not source and right is not source,"root_alias")
        left["status"]="copy_test_mutation"
        prior.need(source["status"]==right["status"]!="copy_test_mutation","root_mutation_isolation")
        if "last_delivered_ack" in source:
            a=left["last_delivered_ack"];b=right["last_delivered_ack"];original=source["last_delivered_ack"]
            prior.need(a is not b and a is not original and b is not original,"ack_alias")
            a["copy_test_mutation"]=True;prior.need("copy_test_mutation" not in b and "copy_test_mutation" not in original,"ack_mutation_isolation")


def measure(rows,fast):
    prior.need(gc.isenabled(),"gc_disabled")
    clone=query_view_copy if fast else copy.deepcopy
    start=time.perf_counter_ns();cpu=time.process_time_ns()
    pairs=[(clone(row),clone(row)) for row in rows]
    result=dict(arm="shallow" if fast else "deepcopy",wall_ns=time.perf_counter_ns()-start,cpu_ns=time.process_time_ns()-cpu,copies=len(rows)*2)
    # Validation deliberately outside the copy-kernel clock, identical in both arms.
    validate_pairs(rows,pairs)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--source",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();source=args.source.resolve();output=args.output.resolve();output.mkdir(exist_ok=False)
    receipt=prior.read(source/"receipt.json");prior.need(receipt["status"]=="verified_exact_pair","native_evidence_status")
    manifest=prior.read(source/"original/manifest.json");rows=[];methods=Counter();sources={}
    for index in (10,11):
        name=f"api_{index:04d}.jsonl.gz";digest=prior.sha(source/"original"/name)
        prior.need(digest==manifest["evidence_sha256"][name],"api_pin");sources[name]=digest
        with gzip.open(source/"original"/name,"rt",encoding="utf-8") as stream:
            for line in stream:
                row=json.loads(line)
                if row["method"] in {"protocol_command","protocol_request"}:
                    rows.append(row["returned"]);methods[row["method"]]+=1
    prior.need(len(rows)==5013 and methods==Counter(protocol_request=4189,protocol_command=824),"full_real_query_cohort")
    paths=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,"__file__",None)
        and Path(m.__file__).suffix==".py" and Path(m.__file__).resolve().is_relative_to(ROOT)}|{ROOT/"tests/test_g31_circulation_protocol_query_copy.py"})
    before={str(path.relative_to(ROOT)):prior.sha(path) for path in paths}
    for path in paths:
        dest=output/"source"/path.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest)
    prior.write(output/"plan.json",dict(schema="g31.protocol_query_copy.pure_actual.v1",native_executions=0,
        query_count=5013,copies_per_query=2,repetitions=5,order="alternating",source_sha256=before,
        input_receipt_sha256=prior.sha(source/"receipt.json"),input_api_sha256=sources,
        pure_tests_sha256=prior.sha(ROOT/"outputs/experiments/g31_ics_lt2_sustained_20261014/protocol_query_copy_pure_001.xml"),
        scope="double-copy kernel and exact controller API replay only; no new request latency measurement"))
    # Full saved API replay must still consume all endpoints and reproduce both
    # controller outputs, not merely the isolated view copies.
    frames=[];start=time.perf_counter_ns()
    with installed_query_view_copy():checks=prior.extract(source,frames)
    replay_ns=time.perf_counter_ns()-start;del frames
    samples=[]
    for repeat in range(5):
        for fast in ((False,True) if repeat%2==0 else (True,False)):samples.append(dict(repeat=repeat,**measure(rows,fast)))
    after={str(path.relative_to(ROOT)):prior.sha(path) for path in paths};prior.need(before==after,"source_changed")
    prior.write(output/"receipt.json",dict(status="pure_query_copy_and_full_api_replay_passed",native_executions=0,
        source_before=before,source_after=after,source_changed=[],plan_sha256=prior.sha(output/"plan.json"),
        query_methods=dict(methods),query_count=len(rows),replay_checks=checks,replay_ns=replay_ns,samples=samples,
        median_ms={arm:statistics.median(row["wall_ns"] for row in samples if row["arm"]==arm)/1e6 for arm in ("deepcopy","shallow")},
        complete_business_100ms_certified=False,gc_enabled=True))


if __name__=="__main__":main()
