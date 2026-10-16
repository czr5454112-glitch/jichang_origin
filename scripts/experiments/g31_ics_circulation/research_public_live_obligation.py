"""Prepare/run exactly96 fixed model projections under one owned120s job.

No native import is loaded, no parameter search, and no future validation grid
is read. Every unknown retains its slot and complete reference-family status.
"""
from __future__ import annotations
import argparse
import ast
from collections import Counter
import copy
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback
import uuid
import xml.etree.ElementTree as ET

from . import public_live_obligation_projection as model
from . import live_obligation_projection_protocol as protocol
from . import bounded_windows_job

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/"outputs/experiments/g31_ics_lt2_sustained_20261014"
SCHEMA="g31.public_live_obligation_fixed96.v1"


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_bytes(model.construction.encoded(value))


def execution_keys(plan):
    if plan.get("case_order")!=list(model.construction.CASE_IDS):raise ValueError("changed_declared_case_order")
    keys=[case+f"/vector_{index:02d}" for case in plan["case_order"] for index in range(32)]
    if len(keys)!=96 or set(plan.get("rows",{}))!=set(keys):raise ValueError("incomplete_ordered_fixed96")
    return keys


def verify_execution_order(plan,ledger):
    expected=execution_keys(plan)
    if (ledger.get("executed")!=96 or ledger.get("execution_order")!=expected
            or any(ledger["rows"][key].get("execution_index")!=index for index,key in enumerate(expected))):
        raise ValueError("actual_execution_order_differs_from_preregistration")


def inventory():
    paths={Path(__file__).resolve(),ROOT/"pyproject.toml",ROOT/"scripts/experiments/g31_ics_circulation/validate_live_obligation_legacy.py"}
    for module in tuple(sys.modules.values()):
        value=getattr(module,"__file__",None)
        if value:
            path=Path(value).resolve()
            if path.is_file() and path.is_relative_to(ROOT) and path.suffix==".py":paths.add(path)
    for name in ("live_obligation_interval","live_obligation_projection","live_obligation_protocol"):
        paths.add(ROOT/("tests/test_g31_circulation_"+name+".py"))
    return {str(path):sha(path) for path in sorted(paths)}


def regression_proof(path):
    value=read(path)
    if (value.get("status")!="exact_old192_outputs" or value.get("row_count")!=192 or len(value.get("rows",[]))!=192
            or not all(r.get("exact") is True and r["reference_sha256"]==r["candidate_sha256"] for r in value["rows"])
            or value.get("source_changed")!=[] or value.get("native_executions")!=0 or value.get("new_three_case_predictions")!=0):
        raise ValueError("missing_complete_exact_old192_regression")
    candidate_path=Path(model.__file__).resolve();original_hash=value["source_pins"][str(candidate_path)]
    current=candidate_path.read_bytes()
    # This exact previous file was archived before prepare001's JSON-key
    # roundtrip failure. The regression invoked Projection directly, never
    # predict/revalidate. Only these two public wrapper functions may differ.
    archived=OUT/"live_obligation_projection_prepare_001/old_regressed_projection.py"
    reconstructed=archived.read_bytes()
    if hashlib.sha256(reconstructed).hexdigest()!=original_hash:
        raise ValueError("changed_regressed_projection_implementation")
    def common_ast(source):
        tree=ast.parse(source)
        tree.body=[node for node in tree.body if not(isinstance(node,ast.FunctionDef) and node.name in ("predict","revalidate"))]
        return ast.dump(tree,include_attributes=False)
    if common_ast(current)!=common_ast(reconstructed):raise ValueError("changed_regressed_projection_AST")
    for source,digest in value["source_pins"].items():
        if Path(source).resolve()!=candidate_path and sha(source)!=digest:raise ValueError("changed_regression_input_or_harness")
    return {"path":str(Path(path).resolve()),"sha256":sha(path),"passed_full_outputs":192,
        "regressed_source_sha256":original_hash,"current_source_sha256":sha(candidate_path),
        "compatibility":"Exact old source archived and hash-bound; every top-level AST node except predict/revalidate is identical. Only new-domain wrapper diagnostics and canonical JSON resource-key handling changed; regressed Projection class/constants/imports and inherited run/scorer unchanged.",
        "prior_source_bytes":reconstructed}


def verify(output,plan):
    if (plan.get("schema")!=SCHEMA or plan.get("hard_timeout_seconds")!=120. or plan.get("native_calls")!=0
            or plan.get("candidate_denominator")!=96 or plan.get("rows")!=protocol.plan_rows()
            or plan.get("incumbent")!=protocol.incumbent_action() or plan.get("case_order")!=list(model.construction.CASE_IDS)):
        raise ValueError("changed_fixed96_plan")
    execution_keys(plan)
    if set(plan["sources"])!=set(inventory()):raise ValueError("omitted_or_extra_source_closure")
    for path,row in plan["sources"].items():
        if sha(path)!=row["sha256"] or sha(output/row["archive"])!=row["sha256"]:raise ValueError("source_drift:"+path)
    for row in plan["references"].values():
        if sha(row["path"])!=row["sha256"]:raise ValueError("changed_reference")
    if sha(sys.executable)!=plan["interpreter"]["sha256"]:raise ValueError("changed_interpreter")
    proof=regression_proof(plan["references"]["old192"]["path"])
    if sha(output/"old_regressed_projection.py")!=proof["regressed_source_sha256"]:raise ValueError("changed_old_regression_source")
    fixed=model.inputs()
    for case,row in plan["cases"].items():
        if sha(output/row["input"])!=row["input_sha256"] or sha(output/row["snapshot"])!=row["snapshot_sha256"]:
            raise ValueError("changed_case_input")
        data=read(output/row["input"]);snapshot=read(output/row["snapshot"])
        if model.construction.encoded(data)!=model.construction.encoded(fixed[case]):raise ValueError("changed_fixed_numerical_parameters")
        rebuilt=model.revalidate(snapshot)
        if rebuilt.get("status")!="conditional_model_input" or rebuilt["case_from_public_input"]!=case:raise ValueError("invalid_prepared_snapshot")


def prepare(output,test_xml):
    output=Path(output).resolve();test_xml=Path(test_xml).resolve()
    if not output.is_relative_to(OUT) or output.exists():raise ValueError("unsafe_or_existing_output")
    suite=ET.parse(test_xml).getroot().findall("testsuite")
    if len(suite)!=1 or any(int(suite[0].get(k,"-1"))!=v for k,v in {"tests":43,"failures":0,"errors":0,"skipped":0}.items()):
        raise ValueError("expected43_pure_checks")
    frozen=OUT/"live_obligation_interval_001";construction_receipt=read(frozen/"receipt.json")
    construction_record=read(frozen/"construction.json")
    if sha(frozen/"construction.json")!=construction_receipt["construction"]["sha256"]:raise ValueError("changed_analytic_construction")
    old=regression_proof(OUT/"live_obligation_old192_regression_002.json")
    before=inventory();output.mkdir(parents=True,exist_ok=False)
    source_rows={}
    for index,(path,digest) in enumerate(before.items()):
        relative=f"source/{index:04d}.py";target=output/relative;target.parent.mkdir(exist_ok=True)
        target.write_bytes(Path(path).read_bytes());source_rows[path]={"sha256":digest,"archive":relative}
    (output/"old_regressed_projection.py").write_bytes(old.pop("prior_source_bytes"))
    cases={}
    for row in construction_record["cases"]:
        case=row["case_id"];data=read(row["input_path"])
        if sha(row["input_path"])!=row["input_sha256"]:raise ValueError("changed_frozen_input")
        snapshot=model.assemble(data,model.declared_captures(data))
        if snapshot.get("status")!="conditional_model_input":raise ValueError("invalid_constructed_initial_facts")
        input_name=case+".input.json";snapshot_name=case+".snapshot.json"
        write(output/input_name,data);write(output/snapshot_name,snapshot)
        cases[case]={"input":input_name,"input_sha256":sha(output/input_name),"snapshot":snapshot_name,
            "snapshot_sha256":sha(output/snapshot_name),"source_input_path":row["input_path"]}
    references={name:{"path":str(path),"sha256":sha(path)} for name,path in {
        "construction_receipt":frozen/"receipt.json","construction":frozen/"construction.json",
        "old192":OUT/"live_obligation_old192_regression_002.json","pure_tests":test_xml}.items()}
    plan={"schema":SCHEMA,"hard_timeout_seconds":120.,"candidate_denominator":96,"native_calls":0,
        "sources":source_rows,"references":references,"interpreter":{"path":sys.executable,"sha256":sha(sys.executable)},
        "case_order":list(model.construction.CASE_IDS),"cases":cases,"rows":protocol.plan_rows(),
        "incumbent":protocol.incumbent_action(),"regression":old,
        "scope":"NEW SYNTHETIC11-node/14-edge five-job/three-tray model; not original airport input or native execution.",
        "arithmetic":"Existing binary-float event loop, START+i*PERIOD and native-derived source expressions unchanged; rational screen is not inserted into physical clocks.",
        "generic_extension":"Per-job mandatory Storage completion/release and public absolute b for alternative return_delay.5; immediate0 remains incumbent.",
        "source_input":"Complete hypothetical source-owned initial facts. No actual delivered capture/token; every future planning exchange is conditional normal-delivery modeling.",
        "interval_claim_boundary":"The isolated D-HX bound concerns resource noninterference, not automatically final completion. X delay may be absorbed downstream; only full five-job continuation can assess strict point-model protection.",
        "execution_order":"Explicit case_order followed by vector00..31. JSON map sorting is not execution order; final ledger must retain and verify the actual ordered96 list.",
        "expiry_scope":"New wrapper rejects conditional assessment if any modeled empty EDGE_ENTER is strictly after expiry39; no expired native ACK is fabricated and all projected events remain retained.",
        "reference_families":"All16 fixed-initial native_default actions and all16 later-native_default actions. Unknown member makes the full reference unknown.",
        "methods":list(protocol.METHODS),"evaluation_budget_each_method":32,
        "search_limits":"Same model/info/actions/budget. Coordinate/plateau/pair may evaluate unprotected proposals but deploy only protected vectors. Complete32 finite MPC reference permits all internal paths; no claim to replicate or surpass general LNS.",
        "all_costs":"Worker import, full source/input verification, all construction/revalidation, every simulation, output hashing/compression, comparison and final verification inside owned120s child. Parent/app external timing separately retained; no100ms claim.",
        "stop_rule":"Exactly96 once; no parameter adjustment or outcome screening. Retain every unexecuted/censored/rejected/mismatched action as unknown. Preserve old validation256 unread.",
        "claims_forbidden":["native feasibility/protection","online delivery","new solver","100ms","actual original-map improvement"]}
    if inventory()!=before:raise ValueError("source_changed_during_prepare")
    verify(output,plan);write(output/"preregistered_protocol.json",plan)
    write(output/"prepare_receipt.json",{"status":"prepared96_unexecuted_zero_native","plan_sha256":sha(output/"preregistered_protocol.json"),
        "source_count":len(source_rows),"old192_exact":192,"pure_passed":43,"new_predictions":0,
        "launch_command":[sys.executable,"-m","scripts.experiments.g31_ics_circulation.research_public_live_obligation","--launch","--output",str(output)]})
    return {"output":str(output),"plan_sha256":sha(output/"preregistered_protocol.json"),"sources":len(source_rows),"new_predictions":0}


def worker(output):
    started=time.perf_counter();plan=read(output/"preregistered_protocol.json")
    if sha(output/"preregistered_protocol.json")!=read(output/"prepare_receipt.json")["plan_sha256"]:
        raise ValueError("changed_prepared_plan_identity")
    verify(output,plan)
    rows=copy.deepcopy(plan["rows"]);rawdir=output/"raw";rawdir.mkdir(exist_ok=False);actual_order=[]
    write(output/"branch_ledger.json",{"rows":rows,"executed":0,"execution_order":actual_order})
    for index,key in enumerate(execution_keys(plan)):
        row=rows[key]
        snapshot=read(output/plan["cases"][row["case"]]["snapshot"])
        call=time.perf_counter();prediction=model.predict(snapshot,row["action"]);seconds=time.perf_counter()-call
        result=protocol.assessment(prediction,row["action"])
        artifact={"key":key,"case":row["case"],"action":row["action"],"prediction":prediction,
            "assessment":result,"model_call_wall_seconds":seconds,"native_calls":0}
        path=rawdir/f"{index:03d}.json.gz";path.write_bytes(gzip.compress(model.construction.encoded(artifact),compresslevel=1,mtime=0))
        row.update(status=result["status"],assessment=result,raw=str(path),raw_sha256=sha(path),model_call_wall_seconds=seconds,execution_index=index)
        actual_order.append(key)
        write(output/"branch_ledger.json",{"rows":rows,"executed":index+1,"execution_order":actual_order,"elapsed_wall_seconds":time.perf_counter()-started})
    verify_execution_order(plan,read(output/"branch_ledger.json"))
    comparison=protocol.compare(rows);verify(output,plan)
    write(output/"comparisons.json",comparison)
    receipt={"schema":SCHEMA,"status":"completed_fixed96_with_unknowns" if any(not protocol.valid(r) for r in rows.values()) else "completed_fixed96_conditional",
        "plan_sha256":sha(output/"preregistered_protocol.json"),"executed":len(rows),"candidate_denominator":96,
        "status_counts":dict(Counter(r["status"] for r in rows.values())),"worker_wall_seconds":time.perf_counter()-started,
        "ledger_sha256":sha(output/"branch_ledger.json"),"comparisons_sha256":sha(output/"comparisons.json"),
        "source_changed":[],"native_calls":0,"online_information_delivered":False,"native_protection_certified":False}
    write(output/"receipt.json",receipt)


def launch(output):
    if (output/"external_process.json").exists() or (output/"receipt.json").exists():raise ValueError("immutable_attempt_already_started")
    started=time.perf_counter();token=uuid.uuid4().hex
    command=[sys.executable,"-m","scripts.experiments.g31_ics_circulation.research_public_live_obligation","--worker","--output",str(output),"--admission",token]
    with (output/"stdout.log").open("w") as stdout,(output/"stderr.log").open("w") as stderr:
        result=bounded_windows_job.run(command,timeout=120.,stdout=stdout,stderr=stderr,admission=token,cwd=str(ROOT))
    write(output/"external_process.json",{**result,"command":command,"parent_post_import_wall_seconds":time.perf_counter()-started,"native_calls":0})
    if result["status"]!="exited" or result["exitcode"]!=0:raise SystemExit(1)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--test-xml",type=Path);parser.add_argument("--admission")
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument("--prepare",action="store_true");mode.add_argument("--launch",action="store_true");mode.add_argument("--worker",action="store_true")
    args=parser.parse_args();args.output=args.output.resolve()
    if args.prepare:print(json.dumps(prepare(args.output,args.test_xml)))
    elif args.launch:launch(args.output)
    else:
        if not args.admission or sys.stdin.readline().strip()!=args.admission:raise ValueError("missing_owned_job_admission")
        try:worker(args.output)
        except Exception as exc:
            write(args.output/"failure.json",{"status":"failed","error":str(exc),"traceback":traceback.format_exc(),"native_calls":0});raise
