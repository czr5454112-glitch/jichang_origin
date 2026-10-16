"""Three-arm pure benchmark over all routing calls from actual cache pair001."""
import argparse
from contextlib import nullcontext
import cProfile
import gc
import hashlib
import json
from pathlib import Path
import pstats
import shutil
import statistics
import sys
import time

import profile_saved_regional_paths as prior
from scripts.experiments.g31_ics_circulation.regional_path_bytes import installed_regional_path_bytes

ROOT=Path(__file__).resolve().parent
ARMS=("original","tuple_pool","bytes_pool")


def measure(frames,arm):
    if arm not in ARMS:raise ValueError("unknown_arm")
    context=installed_regional_path_bytes() if arm=="bytes_pool" else nullcontext()
    begin=time.perf_counter_ns();cpu=time.process_time_ns()
    with context:result=prior.route_run(frames,arm!="original")
    return dict(arm=arm,outer_wall_ns=time.perf_counter_ns()-begin,outer_cpu_ns=time.process_time_ns()-cpu,kernel=result)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--input",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args();source=args.input.resolve();output=args.output.resolve();output.mkdir(exist_ok=False)
    receipt=prior.read(source/"receipt.json")
    prior.need(receipt["status"]=="pure_actual_api_replay_passed" and receipt["handles"]==1000 and receipt["source_changed"]==[],"source_receipt")
    prior.need(prior.sha(source/"actual_routing_calls.json.gz")==receipt["raw_calls_sha256"],"source_calls")
    for name,digest in receipt["source_before"].items():
        prior.need(prior.sha(ROOT/name)==digest and prior.sha(source/"source"/name)==digest,"prior_source:"+name)
    frames=prior.gzread(source/"actual_routing_calls.json.gz")
    prior.need(len(frames)==1000 and sum(len(f["calls"]) for f in frames)==7158,"full_domain")
    paths=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,"__file__",None)
        and Path(m.__file__).suffix==".py" and Path(m.__file__).resolve().is_relative_to(ROOT)}|{
        ROOT/"tests/test_g31_circulation_regional_path_pool.py",ROOT/"tests/test_g31_circulation_regional_path_bytes.py"})
    before={str(path.relative_to(ROOT)):prior.sha(path) for path in paths}
    for path in paths:
        destination=output/"source"/path.relative_to(ROOT);destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,destination)
    prior.write(output/"plan.json",dict(schema="g31.regional_path_bytes.pure_actual.v1",arms=ARMS,repeats=3,
        order=[ARMS,ARMS[1:]+ARMS[:1],ARMS[2:]+ARMS[:2]],native_executions=0,handles=1000,path_calls=7158,
        input_receipt_sha256=prior.sha(source/"receipt.json"),input_calls_sha256=receipt["raw_calls_sha256"],source_sha256=before,
        pure_tests_sha256=prior.sha(ROOT/"outputs/experiments/g31_ics_lt2_sustained_20261014/regional_path_bytes_pure_001.xml"),
        scope="full actual routing kernel, every path checked; not controller/native/full request timing; GC unchanged"))
    samples=[]
    for repeat in range(3):
        for arm in ARMS[repeat:]+ARMS[:repeat]:samples.append(dict(repeat=repeat,**measure(frames,arm)))
    profiles={}
    for arm in ARMS:
        prof=cProfile.Profile();prof.enable();result=measure(frames,arm);prof.disable();prof.dump_stats(str(output/(arm+".prof")))
        rows=[]
        for (filename,line,name),(primitive,total,own,cumulative,_) in pstats.Stats(prof).stats.items():
            if "g31_ics_circulation" in filename or name in {"route_run","measure"}:
                rows.append(dict(file=filename,line=line,function=name,primitive_calls=primitive,total_calls=total,
                    own_seconds=own,cumulative_seconds=cumulative))
        profiles[arm]=dict(measurement=result,functions=sorted(rows,key=lambda row:-row["cumulative_seconds"]))
    after={str(path.relative_to(ROOT)):prior.sha(path) for path in paths};prior.need(before==after,"source_changed")
    prior.write(output/"receipt.json",dict(status="pure_three_arm_complete",native_executions=0,gc_enabled=gc.isenabled(),
        source_before=before,source_after=after,source_changed=[],plan_sha256=prior.sha(output/"plan.json"),samples=samples,profiles=profiles,
        median_wall_ms={arm:statistics.median(row["outer_wall_ns"] for row in samples if row["arm"]==arm)/1e6 for arm in ARMS},
        complete_business_100ms_certified=False))


if __name__=="__main__":main()
