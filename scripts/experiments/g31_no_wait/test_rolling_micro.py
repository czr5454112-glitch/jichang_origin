"""Native rolling transactions, physical event replay and disabled compatibility."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_no_wait.headway_audit import audit_headway
from scripts.experiments.g31_no_wait.rolling_replay import replay_rolling
from test_core_micro import task
from test_headway_micro import run as headway_cases


def base_config(**changes):
    config = dict(end_time=100, interval_mode="half_open", strict_endpoint_resources=True,
                  edge_entry_headway_seconds=2, release_quantum=1, completion_quantum=1,
                  source_fifo=True, source_generation_interval=1,
                  audit_failed_calendar_hash=True, enable_ebs_predecessor_gate=False,
                  enable_inroute_replanning=True, adaptive=False, min_depth=1, max_depth=1,
                  congestion_weight=4, pressure_window=30, max_expansions=256,
                  max_score_expansions=64, time_grid_seconds=1e-6)
    config.update(changes)
    return config


def fork_fixture(*, longer_fast=False, budget=False, gate=False):
    nodes = [(n, 2 if n in (1, 2, 3, 11, 12, 13) else 0)
             for n in ([0, 1, 2, 3, 5, 6, 7, 8, 9, 11, 12, 13] if budget
                       else [0, 1, 2, 3, 5, 6, 7, 8, 9])]
    edges = [(0,1,10),(1,2,1),(1,3,1),(7,2,20),(2,6,1),(8,3,19),(3,9,1)]
    edges += ([(2,11,1),(11,12,1),(12,13,1),(13,5,1),(3,5,20)] if budget
              else [(2,5,7 if longer_fast else 1),(3,5,5)])
    tasks = [task(1,7,6),task(2,0,5,task_id=2,leg="storage_in" if gate else "direct"),task(3,8,9,1)]
    if longer_fast or budget:
        tasks.append(task(4,8,9,3))
    if budget:
        # Both A-pressure reservations must exist before the query is released;
        # a future-release blocker cannot influence its initial local decision.
        nodes.append((14,0)); edges.append((14,2,22))
        tasks.insert(1,task(5,14,6))
    if gate:
        nodes.append((10,0)); edges.append((5,10,1))
        tasks.append(task(6,5,10,task_id=2,leg="storage_out"))
    return dict(nodes=nodes, edges=edges, tasks=tasks,
                config=base_config(max_expansions=4 if budget else 256,
                                   enable_ebs_predecessor_gate=gate))


def independent_audits(request, payload):
    rows = [dict(t, pass_time=t["release"]) for t in request["tasks"]]
    profile = dict(nodes=[dict(location=n,service_time=s) for n,s in request["nodes"]],
                   edges=[dict(start=u,end=v,length=travel*2) for u,v,travel in request["edges"]])
    physical = audit_headway(rows,payload["bags"],profile)
    rolling = replay_rolling(rows,payload["bags"],profile,payload["rolling_events"],
                             horizon=payload["summary"]["executed_horizon"],
                             require_nonincreasing_finish=True)
    assert physical["passed"], physical
    assert rolling["passed"], rolling
    return dict(headway=physical,rolling=rolling)


def run(module):
    records=[]

    def execute(label,request):
        payload=module.plan(**request)
        audits=independent_audits(request,payload)
        records.append(dict(case=label,request=request,payload=payload,audits=audits))
        return payload

    def bag(payload,sid):
        return next(b for b in payload["bags"] if b["segment_id"]==str(sid))

    p=execute("successful_replace_preserves_current_and_prefix",fork_fixture())
    q=bag(p,2)
    commits=[e for e in p["rolling_events"] if e["segment_id"]=="2" and e["kind"].endswith("commit")]
    assert [e["goal_arrival"] for e in commits]==[20,16],commits
    assert [r[0] for r in q["route"]]==[0,1,2,5]
    assert q["route_generation"]==2 and q["actual_finish"]==16
    cleanups=[e for e in p["rolling_events"] if e["segment_id"]=="2" and e["kind"]=="cleanup"]
    assert [(e["time"],e["valid"]) for e in cleanups]==[(17,True),(20,False)],cleanups

    p=execute("finish_cannot_increase_fallback",fork_fixture(longer_fast=True))
    assert bag(p,2)["finish"]==20 and bag(p,2)["route_generation"]==1
    assert p["summary"]["inroute_fallbacks"]>=1 and p["summary"]["route_bound_prunes"]>=1
    assert p["summary"]["failed_search_hash_checks"]>=1

    p=execute("search_budget_fallback_preserves_certificate",fork_fixture(budget=True))
    assert bag(p,2)["finish"]==35 and bag(p,2)["route_generation"]==1
    assert p["summary"]["inroute_fallbacks"]>=1 and p["summary"]["failed_search_hash_checks"]>=1

    p=execute("ebs_activation_uses_actual_latest_goal",fork_fixture(gate=True))
    assert bag(p,2)["actual_finish"]==16 and bag(p,6)["admission"]==16
    assert all(b["completed"] for b in p["bags"])

    simple=dict(nodes=[(0,0),(1,0)],edges=[(0,1,2)],tasks=[task(0,0,1)],config=base_config())
    p=execute("goal_arrival_precedes_equal_time_cleanup",simple)
    events=[e for e in p["rolling_events"] if e["time"]==2]
    assert [e["kind"] for e in events]==["arrival","cleanup"],events

    p=execute("source_equals_goal_has_actual_completion",dict(nodes=[(0,2)],edges=[],tasks=[task(0,0,0)],config=base_config()))
    assert p["bags"][0]["completed"] and p["bags"][0]["actual_finish"]==0

    capped=fork_fixture(); capped["config"]["max_route_excess_seconds"]=0
    p=execute("source_route_bound_uses_static_lower_bound",capped)
    assert bag(p,2)["finish"]==16 and p["summary"]["route_bound_prunes"]>=1

    truncated=fork_fixture(); truncated["config"]["end_time"]=12
    p=execute("horizon_retains_inflight_bags",truncated)
    assert len(p["bags"])==3 and not bag(p,2)["completed"]
    assert bag(p,2)["actual_arrived_index"]==1 and p["summary"]["executed_horizon"]==12

    for changes in ({"interval_mode":"closed_legacy"},{"strict_endpoint_resources":False},
                    {"edge_entry_headway_seconds":0},{"time_grid_seconds":.001}):
        try:
            module.plan([(0,0)],[],[task(0,0,0)],base_config(**changes))
        except ValueError:
            pass
        else:
            raise AssertionError(f"unsupported rolling contract accepted: {changes}")
    return records


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--binary",type=Path,required=True)
    parser.add_argument("--headway-receipt",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    spec=importlib.util.spec_from_file_location("g31_nowait",args.binary.resolve())
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    records=run(module)
    prior=json.loads(args.headway_receipt.read_text(encoding="utf-8"))["records"]
    disabled=headway_cases(module)
    assert len(prior)==len(disabled)
    fields=0
    for old,new in zip(prior,disabled):
        assert old["case"]==new["case"]
        for oldbag,newbag in zip(old["payload"]["bags"],new["payload"]["bags"]):
            for key,value in oldbag.items():
                assert json.dumps(value,sort_keys=True)==json.dumps(newbag[key],sort_keys=True),(old["case"],key,value,newbag[key])
                fields+=1
    receipt=dict(status="passed",rolling_cases=len(records),disabled_cases=len(disabled),
                 old_bag_fields_exact=fields,records=records,
                 source_sha256=hashlib.sha256(Path(__file__).with_name("core.cpp").read_bytes()).hexdigest(),
                 binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
                 test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:receipt[k] for k in ("status","rolling_cases","disabled_cases","old_bag_fields_exact")}))


if __name__=="__main__": main()
