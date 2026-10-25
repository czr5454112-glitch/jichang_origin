"""006 rate-zero physical parity and source-only retry-age budget relaxation."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from test_core_micro import task
from test_rolling_micro import base_config,independent_audits

DIAGNOSTICS={"score_expansions","local_scoring_calendar_queries","route_decisions"}


def fixture(rate, *, tiny=False):
    # Three already committed node1 slots occupy [1,7). The query's shortest
    # path reaches that node at admission+1. Its other branch costs 3s extra.
    nodes=[(n,2 if n in (1,2) else 0) for n in (0,1,2,3,4,5,6,7)]
    edges=[(4,1,1),(6,1,3),(7,1,5),(1,5,1),(0,1,1),(1,3,1),(0,2,1),(2,3,1.000001 if tiny else 4)]
    tasks=[task(0,4,5),task(1,6,5),task(2,7,5),task(3,0,3)]
    return dict(nodes=nodes,edges=edges,tasks=tasks,
        config=base_config(source_fifo_order="canonical",congestion_weight=0,max_route_excess_seconds=0,
                           route_excess_retry_relaxation_rate=rate,retry_mode="1s" if tiny else "calendar_jump"))


def run(module,priors):
    old_fields=old_events=0
    for path in priors:
        for case in json.loads(path.read_text(encoding="utf-8"))["records"]:
            request=case["request"]
            payload=module.plan(**request)
            assert len(payload["bags"])==len(case["payload"]["bags"])
            for old,new in zip(case["payload"]["bags"],payload["bags"]):
                for key,value in old.items():
                    if key in DIAGNOSTICS:
                        if key=="route_decisions":
                            assert [[r[i] for i in (0,1,4)] for r in value]==[[r[i] for i in (0,1,4)] for r in new[key]]
                        continue
                    assert json.dumps(new[key],sort_keys=True)==json.dumps(value,sort_keys=True),(case["case"],key)
                    old_fields+=1
            assert json.dumps(payload["rolling_events"],sort_keys=True)==json.dumps(case["payload"]["rolling_events"],sort_keys=True),case["case"]
            old_events+=len(payload["rolling_events"])
            independent_audits(request,payload)
    records=[]
    for rate in (0,1,2):
        request=fixture(rate);payload=module.plan(**request)
        audits=independent_audits(request,payload)
        query=payload["bags"][3]
        assert query["first_planning_attempt_time"]==0
        assert query["admission"]=={0:6,1:4,2:2}[rate],query
        assert query["admission_effective_route_excess_seconds"]==rate*query["planning_wait_seconds"]
        assert query["admission_route_excess_seconds"]<=(query["admission_effective_route_excess_seconds"])
        assert payload["summary"]["local_scoring_calendar_queries"]==0
        assert payload["summary"]["static_rank_fastpath_candidates"]>0
        assert payload["summary"]["source_route_budget_violations"]==0
        records.append(dict(case=f"source_retry_rate_{rate}",request=request,payload=payload,audits=audits))
    request=fixture(.0000005,tiny=True);payload=module.plan(**request)
    audits=independent_audits(request,payload);query=payload["bags"][3]
    assert query["admission"]==2 and query["first_planning_attempt_time"]==0,query
    assert query["admission_effective_route_excess_seconds"]==.000001
    assert query["admission_route_excess_seconds"]==.000001
    records.append(dict(case="floor_half_microsecond_growth_needs_two_seconds",request=request,payload=payload,audits=audits))
    # A zero scoring budget is still exhausted exactly as before; fast-path
    # evaluation cannot manufacture scoring allowance or consume DFS budget.
    request=fixture(0);request["config"]["max_score_expansions"]=0
    payload=module.plan(**request);audits=independent_audits(request,payload)
    assert payload["bags"][3]["admission"]==6
    assert payload["summary"]["local_score_budget_exhausted_decisions"]>0
    assert payload["summary"]["static_rank_fastpath_candidates"]==0
    records.append(dict(case="zero_score_budget_stays_exhausted",request=request,payload=payload,audits=audits))
    for value in (-1,float("inf"),float("nan")):
        try:module.plan(**fixture(value))
        except ValueError:pass
        else:raise AssertionError("invalid relaxation rate accepted")
    request=fixture(1);del request["config"]["max_route_excess_seconds"]
    try:module.plan(**request)
    except ValueError:pass
    else:raise AssertionError("positive relaxation without finite base accepted")
    return dict(status="passed",cases=len(records),old_physical_bag_fields_exact=old_fields,
                old_ledger_records_exact=old_events,allowed_old_diagnostic_changes=sorted(DIAGNOSTICS),records=records)


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
    receipt["binary_sha256"]=hashlib.sha256(args.binary.read_bytes()).hexdigest()
    receipt["source_sha256"]=hashlib.sha256(Path(__file__).with_name("core.cpp").read_bytes()).hexdigest()
    receipt["test_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!="records"}))
