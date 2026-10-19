"""Run the preserved full original model and export exact offline wait/queue state."""
import argparse
import gzip
import json
import time

from .native_host import audit_result, load_native
from .original_workload import ProxyContract, build_input, digest, summarize_execution, write_json


def main():
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    data,manifest,_=build_input(scale=1,contract=ProxyContract(
        "nanning-on-carrier-proxy-v1-n4-s4-t2",4,4,2,1.,1.,0.,"finite_berth_waiting_research_proxy"))
    receipt={"binary_sha256":digest(args.binary),"input_sha256":manifest["input_sha256"],
             "scope":"offline diagnostic export; never passed to online controllers","status":"running"}
    write_json(args.output/"receipt.json",receipt)
    started=time.perf_counter()
    session=load_native(args.binary).NativeSession(data)
    while session.physical_time<86400:
        progress=session.advance_to(86400,max_events=10000)
        if not progress["processed_events"]:break
    result=session.result_at(session.physical_time)
    write_json(args.output/"native_offline_diagnostics.json",session.offline_diagnostics())
    write_json(args.output/"summary.json",summarize_execution(data,result))
    write_json(args.output/"event_audit.json",audit_result(data,result))
    write_json(args.output/"input_manifest.json",manifest)
    with gzip.open(args.output/"physical_events.jsonl.gz","wt",encoding="utf-8") as stream:
        for event in result["receipts"]:stream.write(json.dumps(event)+"\n")
    receipt.update(status="reached" if session.physical_time==86400 else "censored",
                   physical_time=session.physical_time,wall_seconds=time.perf_counter()-started,
                   final_state_sha256=session.offline_state_sha256())
    write_json(args.output/"receipt.json",receipt)
    print(json.dumps(receipt,indent=2))


if __name__=="__main__":main()
