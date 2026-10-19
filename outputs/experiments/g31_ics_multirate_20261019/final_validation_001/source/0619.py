"""Exact old-domain regression for the generic-Storage subclass; zero native."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import time
from . import public_live_obligation_projection as candidate

ROOT=Path(__file__).resolve().parents[3]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(source,output):
    source=Path(source).resolve();output=Path(output).resolve()
    if output.exists():raise ValueError("immutable_regression_output_exists")
    plan_path=source/"preregistered_protocol.json";plan=json.loads(plan_path.read_bytes())
    if len(plan["cases"])!=6:raise ValueError("old_domain_requires_six_bundles")
    pins={str(Path(candidate.__file__)):sha(candidate.__file__),str(Path(__file__)):sha(__file__),str(plan_path):sha(plan_path)}
    pins.update({str(source/c["input"]):c["input_sha256"] for c in plan["cases"]})
    candidate.check_sources()
    for p,digest in pins.items():
        if sha(p)!=digest:raise ValueError("changed_old_input_or_source")
    started=time.perf_counter();rows=[]
    for case in plan["cases"]:
        bundle=json.loads((source/case["input"]).read_bytes())
        context=candidate.old_context.RequestContext(bundle);actions=context.actions()
        if len(actions)!=32:raise ValueError("old_domain_requires_32_actions")
        for index,action in enumerate(actions):
            expected=context.predict(action)
            actual=candidate.Projection(bundle,action,new_contract=False).run()
            same=candidate.construction.encoded(expected)==candidate.construction.encoded(actual)
            rows.append({"case":case["case"],"action_index":index,"action":action,"exact":same,
                "reference_sha256":candidate.construction.digest(expected),"candidate_sha256":candidate.construction.digest(actual),
                "reference_status":expected["status"],"candidate_status":actual["status"]})
    changed=[p for p,digest in pins.items() if sha(p)!=digest]
    if len(rows)!=192 or changed:raise ValueError("incomplete_or_changed_regression")
    result={"schema":"g31.live_obligation_old_domain_regression.v1",
        "status":"exact_old192_outputs" if all(r["exact"] for r in rows) else "regression_failed",
        "rows":rows,"row_count":len(rows),"source_pins":pins,"source_changed":changed,
        "wall_seconds":time.perf_counter()-started,"new_three_case_predictions":0,"native_executions":0,
        "scope":"Retrospective code regression only. Does not change the historical18 native unknowns or validate the new11-node domain."}
    output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    return {k:v for k,v in result.items() if k!="rows" and k!="source_pins"}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--source",required=True);parser.add_argument("--output",required=True)
    args=parser.parse_args();print(json.dumps(run(args.source,args.output)))
