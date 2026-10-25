"""005 nominal-order FIFO, including an EBS head not yet ready to plan."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from test_core_micro import task
from test_rolling_micro import base_config,independent_audits


def fixture(*,tie=False,reverse=False):
    tasks=[task(0,0,5,task_id=10,leg="storage_in"),
           task(1,5,6,2,task_id=10,leg="storage_out"),
           task(2,1,5,task_id=20,leg="storage_in"),
           task(3,5,6,2 if tie else 3,task_id=20,leg="storage_out"),
           task(4,5,6,20,task_id=40)]
    if reverse: tasks=tasks[2:4]+tasks[:2]+tasks[4:]
    return dict(nodes=[(0,0),(1,0),(5,2),(6,0)],edges=[(0,5,10),(1,5,1),(5,6,1)],
                tasks=tasks,config=base_config(source_fifo_order="canonical",enable_ebs_predecessor_gate=True,congestion_weight=0))


def run(module,priors):
    fields=events=0
    for prior in priors:
        for case in json.loads(Path(prior).read_text(encoding="utf-8"))["records"]:
            request=case["request"]
            assert "source_fifo_order" not in request["config"]
            payload=module.plan(**request)
            for old,new in zip(case["payload"]["bags"],payload["bags"]):
                for key,value in old.items():
                    assert json.dumps(new[key],sort_keys=True)==json.dumps(value,sort_keys=True),(case["case"],key)
                    fields+=1
            assert json.dumps(payload["rolling_events"],sort_keys=True)==json.dumps(case["payload"]["rolling_events"],sort_keys=True),case["case"]
            events+=len(payload["rolling_events"])
            independent_audits(request,payload)
    records=[]
    def execute(name,request):
        payload=module.plan(**request);audits=independent_audits(request,payload)
        records.append(dict(case=name,request=request,payload=payload,audits=audits))
        return {b["segment_id"]:b for b in payload["bags"]}
    request=fixture();bags=execute("unready_nominal_head_blocks_ready_later_outbound",request)
    assert (bags["1"]["activation_time"],bags["1"]["first_planning_attempt_time"],bags["1"]["admission"])==(10,10,12)
    assert (bags["3"]["activation_time"],bags["3"]["first_planning_attempt_time"],bags["3"]["admission"])==(3,13,14)
    assert bags["3"]["first_planning_attempt_time"]>=bags["1"]["admission"]+1
    assert bags["4"]["first_planning_attempt_time"]==20
    old=fixture();old["config"]["source_fifo_order"]="activation"
    bags=execute("explicit_activation_reproduces_ready_order_diagnostic",old)
    assert bags["3"]["admission"]==3 and bags["1"]["admission"]==12
    bags=execute("equal_nominal_time_keeps_original_row_order",fixture(tie=True))
    assert bags["3"]["first_planning_attempt_time"]==13
    bags=execute("reversed_equal_nominal_rows_reverse_the_stable_tie",fixture(tie=True,reverse=True))
    assert bags["3"]["first_planning_attempt_time"]==2 and bags["3"]["admission"]==3
    request=fixture(reverse=True)
    for t in request["tasks"]:
        if t["segment_id"]=="1":t["release"]=2.1
        if t["segment_id"]=="3":t["release"]=2.2
    bags=execute("raw_nominal_double_order_precedes_ceil_epoch_and_input_tie",request)
    assert bags["3"]["first_planning_attempt_time"]==13
    request=fixture();request["config"]["end_time"]=9
    bags=execute("censored_ready_follower_has_no_fake_first_attempt",request)
    assert bags["3"]["activation_time"]==3 and bags["3"]["first_planning_attempt_time"] is None
    assert bags["3"]["admission"] is None
    for config in (base_config(source_fifo_order="unknown"),base_config(source_fifo_order="canonical",source_fifo=False)):
        try:module.plan([(0,0)],[],[task(0,0,0)],config)
        except ValueError:pass
        else:raise AssertionError("invalid source-order combination accepted")
    return dict(status="passed",canonical_cases=len(records),old_bag_fields_exact=fields,old_ledger_records_exact=events,records=records)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--prior",type=Path,action="append",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    spec=importlib.util.spec_from_file_location("g31_nowait",args.binary.resolve())
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    receipt=run(module,args.prior)
    receipt["source_sha256"]=hashlib.sha256(Path(__file__).with_name("core.cpp").read_bytes()).hexdigest()
    receipt["binary_sha256"]=hashlib.sha256(args.binary.read_bytes()).hexdigest()
    receipt["test_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in receipt.items() if k!="records"}))
