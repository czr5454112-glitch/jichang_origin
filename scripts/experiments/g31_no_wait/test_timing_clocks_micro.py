"""004 observational timestamps: retries/FIFO/gate, with exact 003 replay parity."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from test_core_micro import task
from test_rolling_micro import base_config,independent_audits


def run(module,old_receipt):
    old=json.loads(Path(old_receipt).read_text(encoding="utf-8"))
    fields=0;ledgers=0
    for case in old["records"]:
        new=module.plan(**case["request"])
        for prior,current in zip(case["payload"]["bags"],new["bags"]):
            for key,value in prior.items():
                assert json.dumps(current[key],sort_keys=True)==json.dumps(value,sort_keys=True),(case["case"],key)
                fields+=1
        assert json.dumps(new["rolling_events"],sort_keys=True)==json.dumps(case["payload"]["rolling_events"],sort_keys=True),case["case"]
        ledgers+=len(new["rolling_events"])
        independent_audits(case["request"],new)
    records=[]
    nodes=[(0,0),(1,2),(2,0),(3,0),(4,0)]
    edges=[(3,1,1),(0,1,1),(1,2,1)]
    request=dict(nodes=nodes,edges=edges,tasks=[task(0,3,2),task(1,0,2),task(2,0,2,1),task(3,0,2,200)],
                 config=base_config(congestion_weight=0))
    payload=module.plan(**request);independent_audits(request,payload)
    a,b,c,future=payload["bags"]
    assert (b["activation_time"],b["first_planning_attempt_time"],b["admission"])==(0,0,2)
    assert b["retries"]>=1 and b["planning_wait_seconds"]==2
    assert (c["activation_time"],c["first_planning_attempt_time"],c["admission"])==(1,3,4)
    assert c["preplanning_hold_seconds"]==2 and c["canonical_to_first_planning_seconds"]==2
    assert c["planning_wait_seconds"]==1
    assert future["activation_time"] is None and future["first_planning_attempt_time"] is None
    records.append(dict(case="failure_retry_keeps_first_attempt_and_fifo_has_three_clocks",request=request,payload=payload))
    request=dict(nodes=nodes,edges=edges,tasks=[task(4,4,2,1)],config=base_config(max_retries=0))
    payload=module.plan(**request);bag=payload["bags"][0]
    assert bag["first_planning_attempt_time"]==1 and bag["activation_time"]==1
    assert bag["admission"] is None and bag["planning_wait_seconds"] is None and not bag["completed"]
    records.append(dict(case="unsuccessful_task_still_has_first_attempt",request=request,payload=payload))
    request=dict(nodes=[(0,0),(1,2),(2,0)],edges=[(0,1,5),(1,2,1)],
                 tasks=[task(0,0,1,task_id=7,leg="storage_in"),task(1,1,2,task_id=7,leg="storage_out")],
                 config=base_config(enable_ebs_predecessor_gate=True))
    payload=module.plan(**request);independent_audits(request,payload)
    inbound,outbound=payload["bags"]
    assert inbound["finish"]==5
    assert outbound["activation_time"]==5 and outbound["first_planning_attempt_time"]==5
    assert outbound["admission"]==7 and outbound["planning_wait_seconds"]==2
    records.append(dict(case="ebs_storage_dwell_excluded_but_first_failed_out_attempt_counted",request=request,payload=payload))
    return dict(status="passed",clock_cases=len(records),old_bag_fields_exact=fields,
                old_ledger_records_exact=ledgers,records=records)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--binary",required=True,type=Path)
    parser.add_argument("--prior",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    spec=importlib.util.spec_from_file_location("g31_nowait",args.binary.resolve())
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    receipt=run(module,args.prior)
    receipt["binary_sha256"]=hashlib.sha256(args.binary.read_bytes()).hexdigest()
    receipt["source_sha256"]=hashlib.sha256(Path(__file__).with_name("core.cpp").read_bytes()).hexdigest()
    receipt["test_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in receipt.items() if k!="records"}))
