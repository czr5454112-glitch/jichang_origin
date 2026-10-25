"""Isolated candidate011 runner derived from the official continuous adapter.

The registered model uses local next-hop scoring and a complete continuation
certificate. Registration is not a performance promotion or distributed-network
deployment claim. Historical waiting-model execution is not changed here.
"""
from __future__ import annotations

import gzip
import hashlib
import importlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[4]
AUDITORS = Path(__file__).resolve().parent.parent / "candidate010" / "auditors"
DEFAULT_CONTRACT = ROOT / "configs/eval/g31_continuous/contract.json"
MODEL = "continuous_headway_2s"
FIXED = dict(interval_mode="half_open",strict_endpoint_resources=True,
             edge_entry_headway_seconds=2.0,time_grid_seconds=1e-6,
             terminal_reservation_service=True,enable_inroute_replanning=True,
             enable_ebs_predecessor_gate=True,release_quantum=1.0,completion_quantum=1.0,
             source_fifo=True,source_generation_interval=1.0,source_fifo_order="canonical")
DEFAULT_CONTROLS = dict(end_time=98259.0,min_depth=1,max_depth=4,adaptive=True,
    congestion_weight=1.0,pressure_window=30.0,max_expansions=256,max_score_expansions=64,
    max_retries=100000,max_events=10000000,retry_mode="calendar_jump",retry_step=1.0,
    audit_failed_calendar_hash=False,skip_scoring_single_choice=True,route_excess_retry_relaxation_rate=0.0,
    future_source_reservation_horizon_seconds=0,future_source_reservation_min_wait_seconds=2.0,**FIXED)
ALLOWED = set(DEFAULT_CONTROLS) | {"max_route_excess_seconds"}


def rooted(path):
    path=Path(path)
    return path if path.is_absolute() else ROOT/path


def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def evidence(path):
    path=Path(path).resolve(strict=True)
    return dict(path=str(path),sha256=digest(path),bytes=path.stat().st_size)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON: "+value)))


def write(path,value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


def registered_file(record):
    path=rooted(record["path"]).resolve(strict=True)
    if digest(path)!=record["sha256"]: raise ValueError("registered input/source hash mismatch: "+str(path))
    return path


def validate_controls(raw, horizon):
    if not isinstance(raw,dict): raise ValueError("controls must be an object")
    unknown=set(raw)-ALLOWED
    if unknown: raise ValueError("unknown continuous control: "+",".join(sorted(unknown)))
    controls={**DEFAULT_CONTROLS,**raw}
    for key,value in FIXED.items():
        if controls[key]!=value or (isinstance(value,bool) and type(controls[key]) is not bool):
            raise ValueError("continuous model requires "+key+"="+str(value))
    if controls["end_time"]!=horizon: raise ValueError("registered full-horizon contract changed")
    integers={"min_depth","max_depth","max_expansions","max_score_expansions","max_retries","max_events","future_source_reservation_horizon_seconds"}
    booleans={key for key,value in DEFAULT_CONTROLS.items() if isinstance(value,bool)}
    for key,value in controls.items():
        if key in integers:
            if type(value) is not int: raise ValueError(key+" must be an integer")
        elif key in booleans:
            if type(value) is not bool: raise ValueError(key+" must be a boolean")
        elif key not in ("interval_mode","retry_mode","source_fifo_order"):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0:
                raise ValueError(key+" must be finite and nonnegative")
    if not 1<=controls["min_depth"]<=controls["max_depth"]<=32: raise ValueError("invalid observation depth")
    if controls["max_expansions"]<1 or controls["max_score_expansions"]<0 or controls["max_retries"]<0 or controls["max_events"]<1:
        raise ValueError("invalid search/event budget")
    if controls["retry_step"]<=0: raise ValueError("retry_step must be positive")
    if controls["route_excess_retry_relaxation_rate"]>0 and "max_route_excess_seconds" not in controls:
        raise ValueError("retry cap relaxation requires a finite base route excess")
    if controls["retry_mode"] not in ("calendar_jump","futurecalendar_jump","1s","fixed_step"):
        raise ValueError("unknown retry mode")
    future=controls["future_source_reservation_horizon_seconds"]
    if not 0<=future<=60:
        raise ValueError("future reservation horizon must be an integer in [0,60]")
    if future and controls["congestion_weight"]!=0:
        raise ValueError("candidate011 future reservations require the fixed static-H ranking (w0)")
    return controls


def validate_profile(original, profile):
    before={int(n["location"]):n for n in original["nodes"]}
    after={int(n["location"]):n for n in profile["nodes"]}
    if before.keys()!=after.keys() or len(after)!=len(profile["nodes"]): raise ValueError("node identity changed")
    for node,old in before.items():
        expected=2.0 if float(old["service_time"])>0 else 0.0
        if after[node]["service_time"]!=expected: raise ValueError("service2 normalization mismatch")
    edges=lambda p: sorted((int(e["start"]),int(e["end"]),float(e["length"])) for e in p["edges"])
    if edges(original)!=edges(profile): raise ValueError("topology or edge length changed")


def validate_build(binary, expected_core):
    build=binary.parent.parent
    receipt_path=build/"build_receipt.json"
    receipt=read(receipt_path)
    if receipt.get("status")!="complete" or digest(binary) not in receipt.get("binaries",{}).values():
        raise ValueError("binary does not match a completed immutable build")
    if receipt["source_sha256"].get("core.cpp")!=expected_core:
        raise ValueError("binary core does not match registered formal engine")
    for filename,expected in receipt["source_sha256"].items():
        if digest(build/"source"/filename)!=expected: raise ValueError("frozen build source changed")
    return receipt_path


def prepare(map_name, *, scale=1, controls_path=None, binary=None, contract_path=DEFAULT_CONTRACT):
    """Validate inputs and construct the request without loading a native module."""
    contract_path=rooted(contract_path).resolve(strict=True)
    contract=read(contract_path)
    if contract.get("schema")!="g31.continuous.physical_contract.v1" or contract.get("execution_model")!=MODEL:
        raise ValueError("unknown continuous physical contract")
    if (contract.get("speed_mps"),contract.get("fault_schedule"),contract.get("empty_trays"),
        contract.get("time_grid_seconds"),contract.get("positive_node_service_seconds"),
        contract.get("edge_entry_headway_seconds"))!=(2.0,"none",False,1e-6,2.0,2.0):
        raise ValueError("unsupported physical contract")
    selected=contract.get("selected_controls")
    if controls_path is None:
        if selected is None: raise ValueError("continuous mode requires explicit --controls; no winner has been selected")
        controls_path=registered_file(selected)
    controls_path=rooted(controls_path).resolve(strict=True)
    controls=validate_controls(read(controls_path),contract["end_time"])
    cell_key=f"{map_name}_{scale}x"
    if cell_key not in contract["cells"]: raise ValueError("unsupported map/scale cell")
    cell=contract["cells"][cell_key]
    registered_file(contract["native_source"])
    map_record=contract["maps"][map_name]
    profile_path=registered_file(map_record["profile"])
    profile=read(profile_path)
    validate_profile(read(registered_file(map_record["original_profile"])),profile)
    canonical=registered_file(cell["canonical"])
    data=canonical.read_bytes()
    if cell["canonical"]["encoding"]=="gzip_jsonl": data=gzip.decompress(data)
    elif cell["canonical"]["encoding"]!="jsonl": raise ValueError("unknown canonical encoding")
    if hashlib.sha256(data).hexdigest()!=cell["canonical"].get("content_sha256",cell["canonical"]["sha256"]):
        raise ValueError("canonical content hash changed")
    rows=[json.loads(line) for line in data.decode("utf-8").splitlines() if line.strip()]
    if len(rows)!=cell["segment_denominator"] or len({r["segment_id"] for r in rows})!=len(rows) or len({r["task_id"] for r in rows})!=cell["business_denominator"]:
        raise ValueError("full population denominator changed")
    binary_path=rooted(binary).resolve(strict=True) if binary else registered_file(contract["default_binary"])
    receipt_path=validate_build(binary_path,contract["native_source"]["sha256"])
    request=dict(nodes=[(n["location"],n["service_time"]) for n in profile["nodes"]],
                 edges=[(e["start"],e["end"],e["length"]/2.0) for e in profile["edges"]],
                 tasks=[dict(segment_id=r["segment_id"],task_id=r["task_id"],release=r["pass_time"],
                             deadline=r["std"],start=r["start"],goal=r["goal"],leg=r["leg"]) for r in rows],config=controls)
    selection=dict(schema="g31.standard.selection.v2",execution_model=MODEL,map=map_name,scale=scale,
                   standard_id=contract.get("candidate_id","g31_continuous_explicit_candidate"),is_standard_selection=False,
                   selection_label="explicit_continuous_candidate_not_promoted",historical_default_modified=False,
                   contract=evidence(contract_path),controls=evidence(controls_path),binary=evidence(binary_path),
                   canonical=evidence(canonical),profile=evidence(profile_path),build_receipt=evidence(receipt_path),
                   native_source=contract["native_source"],effective_controls=controls,
                   business_denominator=cell["business_denominator"],segment_denominator=cell["segment_denominator"],
                   paper_tht_definition="per original task_id: sum over its transport legs of finish-admission; full population only when all bags complete",
                   user_primary_tht_definition="per original task_id: sum over its transport legs of actual goal arrival minus first_planning_attempt_time; failed search/retry time included; source activation/FIFO preplanning hold and canonical elapsed reported separately",
                   user_primary_tht_status="explicit_first_planning_attempt_time; admission-based paper/network values are diagnostic",
                   source_order_contract="stable canonical nominal release; input row order for ties; an unreleased or predecessor-blocked head blocks later tasks",
                   source_wait_separately_reported=True,claim_boundary=contract["claim_boundary"])
    return dict(request=request,selection=selection,rows=rows,profile=profile,binary=binary_path)


def load_native(binary):
    spec=importlib.util.spec_from_file_location("g31_nowait",binary)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(prepared, output):
    """Run a fully prepared request; retain evidence even if a hard gate fails."""
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=False)
    selection=prepared["selection"]
    manifest=dict(schema="g31.continuous.run.v1",status="prepared",selection=selection)
    write(output/"manifest.json",manifest)
    sources=output/"standard_sources";sources.mkdir()
    for key in ("contract","controls","profile","build_receipt"):
        shutil.copyfile(selection[key]["path"],sources/(key+".json"))
    shutil.copyfile(ROOT/selection["native_source"]["path"],sources/"core.cpp")
    shutil.copyfile(__file__,sources/"g31_continuous_adapter.py")
    for filename in ("__init__.py","future_metadata.py","headway_audit.py","rolling_replay.py","tht_metrics.py","source_policy_audit.py"):
        shutil.copyfile(AUDITORS/filename,sources/filename)
    shutil.copyfile(ROOT/"scripts/experiments/g31_no_wait/run.py",sources/"memory_snapshot_provider.py")
    manifest["source_sha256"]={p.name:digest(p) for p in sources.iterdir()}
    if manifest["source_sha256"]["core.cpp"]!=selection["native_source"]["sha256"]:
        raise ValueError("formal source changed while preparing run evidence")
    write(output/"config.json",prepared["request"]["config"])
    write(output/"map.json",prepared["profile"])
    with gzip.open(output/"request.json.gz","wt",encoding="utf-8") as stream:
        json.dump(prepared["request"],stream,allow_nan=False)
    try:
        manifest["status"]="running";write(output/"manifest.json",manifest)
        module=load_native(prepared["binary"])
        started=time.perf_counter();cpu_started=time.process_time()
        payload=module.plan(**prepared["request"])
        wall=time.perf_counter()-started;cpu=time.process_time()-cpu_started
        from scripts.experiments.g31_no_wait.run import process_memory_snapshot
        memory_after_native=process_memory_snapshot()
        for key,filename in (("bags","bags.jsonl"),("rolling_events","rolling_events.jsonl")):
            with (output/filename).open("w",encoding="utf-8") as stream:
                for row in payload[key]: stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+"\n")
        write(output/"native_summary.json",payload["summary"])
        if payload["summary"].get("event_budget_exhausted"): raise ValueError("event budget exhausted; incomplete execution retained")
        audits=audit_result(prepared,payload,source_dir=sources)
        memory_after_audit=process_memory_snapshot()
        for name,value in audits.items(): write(output/(name+".json"),value)
        if not all(value["passed"] for value in audits.values()): raise ValueError("continuous physical/causal/THT audit failed")
        for key in ("contract","controls","binary","canonical","profile","build_receipt"):
            if digest(selection[key]["path"])!=selection[key]["sha256"]: raise ValueError(key+" changed during execution")
        manifest.update(status="complete",native_wall_seconds=wall,native_process_cpu_seconds=cpu,
                        bags_sha256=digest(output/"bags.jsonl"),audits_passed=True,
                        memory_after_native=memory_after_native,memory_after_audit=memory_after_audit,
                        full_population_performance_available=(audits["business_audit"]["completed_businesses"]==len({r["task_id"] for r in prepared["rows"]}) and audits["tht_audit"]["user_tht_full_population_available"]))
        write(output/"summary.json",dict(execution_model=MODEL,primary_metric="sum_leg_finish_minus_first_planning_attempt_per_business",
                    primary_metric_status=selection["user_primary_tht_status"],
                    tht=audits["tht_audit"],business=audits["business_audit"],native=payload["summary"],
                    performance_promoted=False))
        write(output/"manifest.json",manifest)
        return manifest
    except BaseException as exc:
        manifest.update(status="failed",error=repr(exc));write(output/"manifest.json",manifest);raise


def verified_auditors(source_dir):
    """Load the frozen audit package, checking every live source against it."""
    names=("headway_audit","future_metadata","rolling_replay","tht_metrics","source_policy_audit")
    package_name="g31_candidate011_auditors_"+hashlib.sha256(str(source_dir.resolve()).encode()).hexdigest()[:16]
    package=types.ModuleType(package_name)
    package.__path__=[str(source_dir)]
    sys.modules[package_name]=package
    modules={}
    for name in names:
        live=AUDITORS/(name+".py")
        if digest(live)!=digest(source_dir/(name+".py")):
            raise ValueError("auditor source changed before replay: "+name)
        full_name=package_name+"."+name
        spec=importlib.util.spec_from_file_location(full_name,source_dir/(name+".py"))
        module=importlib.util.module_from_spec(spec)
        sys.modules[full_name]=module
        spec.loader.exec_module(module)
        modules[name]=module
        if digest(live)!=digest(source_dir/(name+".py")):
            raise ValueError("auditor source changed while loading: "+name)
    return [modules[name] for name in ("headway_audit","rolling_replay","tht_metrics","source_policy_audit")]


def audit_result(prepared,payload,*,source_dir):
    headway_module,rolling_module,tht_module,source_module=verified_auditors(source_dir)
    rows,bags,profile=prepared["rows"],payload["bags"],prepared["profile"]
    cfg=prepared["request"]["config"]
    headway=headway_module.audit_headway(rows,bags,profile,time_grid_seconds=cfg["time_grid_seconds"],
                         strict_endpoint_resources=True,edge_entry_headway_seconds=2,
                         horizon=payload["summary"]["executed_horizon"])
    rolling=rolling_module.replay_rolling(rows,bags,profile,payload["rolling_events"],
                          horizon=payload["summary"]["executed_horizon"],require_nonincreasing_finish=True)
    tht=tht_module.audit_tht(rows,bags,horizon=payload["summary"]["executed_horizon"])
    if tht["missing_first_planning_attempt_segments"]:
        raise ValueError("required first planning attempt telemetry missing; cannot substitute admission")
    business=audit_business(rows,bags,payload["summary"]["executed_horizon"])
    source_policy=source_module.audit_source_policy(rows,bags,
        source_generation_interval=cfg["source_generation_interval"],
        release_quantum=cfg["release_quantum"],source_fifo_order=cfg["source_fifo_order"],
        horizon=payload["summary"]["executed_horizon"])
    for name in ("__init__","future_metadata","headway_audit","rolling_replay","tht_metrics","source_policy_audit"):
        if digest(AUDITORS/(name+".py"))!=digest(source_dir/(name+".py")):
            raise ValueError("auditor source changed during replay")
    return dict(headway_audit=headway,rolling_replay=rolling,tht_audit=tht,
                business_audit=business,source_policy_audit=source_policy)


def audit_business(rows,bags,horizon):
    """Identity, actual completion and EBS dependency checks, with full denominators."""
    expected={str(r["segment_id"]):r for r in rows};actual={str(b["segment_id"]):b for b in bags}
    if len(actual)!=len(bags) or expected.keys()!=actual.keys(): raise ValueError("segment population changed")
    groups={};violations=[];counts=dict(completed_businesses=0,finish_le_std=0,finish_le_std_minus_2700=0)
    original_window_end=98259.0
    cutoff_available=horizon>=original_window_end
    completed_by_cutoff=0
    for sid,row in expected.items():
        b=actual[sid]
        for key,canonical in (("task_id","task_id"),("leg","leg"),("start","start"),("goal","goal"),("release","pass_time"),("deadline","std")):
            if b.get(key)!=row[canonical]: violations.append([sid,"identity_changed",key])
        if b.get("completed") and (b.get("actual_finish") is None or b["actual_finish"]!=b.get("finish") or b["finish"]>horizon):
            violations.append([sid,"completed_without_actual_goal"])
        group=groups.setdefault(row["task_id"],{})
        if row["leg"] in group: violations.append([row["task_id"],"duplicate_business_leg"])
        group[row["leg"]]=(row,b)
    for task,legs in groups.items():
        if set(legs) not in ({"direct"},{"storage_in","storage_out"}):
            violations.append([task,"invalid_business_legs"]);continue
        row,final=legs.get("direct",legs.get("storage_out"))
        if any(r["std"]!=row["std"] for r,_ in legs.values()): violations.append([task,"inconsistent_business_deadline"])
        if "storage_in" in legs and final.get("admission") is not None:
            inbound=legs["storage_in"][1]
            if not inbound.get("completed") or inbound.get("actual_finish") is None or inbound["actual_finish"]>final["admission"]:
                violations.append([task,"outbound_admitted_before_actual_inbound_goal"])
        complete=all(b.get("completed") is True for _,b in legs.values())
        counts["completed_businesses"]+=complete
        completed_by_cutoff+=complete and final["finish"]<=original_window_end
        counts["finish_le_std"]+=complete and final["finish"]<=row["std"]
        counts["finish_le_std_minus_2700"]+=complete and final["finish"]<=row["std"]-2700
    return dict(schema="g31.continuous.business_audit.v1",passed=not violations,
                business_denominator=len(groups),segment_denominator=len(rows),**counts,
                original_window_end=original_window_end,
                original_window_completed_businesses=completed_by_cutoff if cutoff_available else None,
                original_window_count_available=cutoff_available,
                cutoff_count_method="All transport legs completed; final actual goal arrival at or before the common original cutoff. Derived from this run, not a separate short execution.",
                violation_count=len(violations),violation_examples=violations[:20])
