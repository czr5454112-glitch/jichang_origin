"""Independent artifact mapping audit; no author input/projection/runtime imports."""
from collections import Counter
from itertools import zip_longest
import gzip,hashlib,json
from pathlib import Path
import sys,time,traceback
ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parent
out=BASE/sys.argv[1];out.mkdir()
cpu,wall=time.process_time(),time.perf_counter()
bindings={};checks=0;rows=[]
def check(ok,message):
    global checks
    checks+=1
    if not ok:raise AssertionError(message)
def raw(path):
    data=path.read_bytes();bindings[path.relative_to(ROOT).as_posix()]=hashlib.sha256(data).hexdigest();return data
def read(path):return json.loads(raw(path))
def canonical(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False)
try:
    current=BASE.parent/"phase4_round11_projection_runtime_20261011/full_adapter_002"
    prior=BASE.parent/"phase4_round10_business_projection_20261011/full_audit_002"
    previous_audit=read(BASE.parent/"phase4_round10_validation_20261011/projection_independent_001/results.json")
    manifest=read(current/"manifest.json")
    for name,digest in manifest["input_sha256"].items():check(hashlib.sha256(raw(ROOT/name)).hexdigest()==digest,"bound upstream source")
    for name,digest in manifest["outputs"].items():check(hashlib.sha256(raw(current/name)).hexdigest()==digest,"sealed current artifact")
    mappings={}
    for scale in (1,2):
        old_path=prior/f"projected_tasks_{scale}x.jsonl.gz"
        check(hashlib.sha256(raw(old_path)).hexdigest()==previous_audit["input_sha256"][old_path.relative_to(ROOT).as_posix()],"previous independent projection seal")
        metadata=read(prior/f"projection_metadata_{scale}x.json")
        run=read(current/f"run_contract_{scale}x.json")
        run_sha=hashlib.sha256(canonical(run).encode()).hexdigest()
        check(run["projection_sha256"]==metadata["content_sha256"],"fixed projection identity")
        check(run["source_workload_sha256"]==metadata["contract"]["source_workload_sha256"],"fixed source identity")
        seen=set();counts=Counter();groups={}
        with gzip.open(old_path,"rt",encoding="utf-8") as old, gzip.open(current/f"private_runtime_tape_{scale}x.jsonl.gz","rt",encoding="utf-8") as new:
            for old_line,new_line in zip_longest(old,new):
                check(old_line is not None and new_line is not None,"complete ordered denominator")
                previous,current_row=json.loads(old_line),json.loads(new_line)
                check(canonical({k:current_row[k] for k in previous})==canonical(previous),"all original source, full group, old/new final preserved")
                task=current_row["original"];bid=task["business_bag_id"]
                check(bid not in seen,"unique complete business identity");seen.add(bid)
                bag=dict(bag_id=bid,origin=task["origin"],destination=current_row["projected_destination"],
                    arrival=task["arrival"],deadline=task["deadline"],protected=task["protected"])
                if task["lifecycle"]=="early_storage":
                    bag["storage"]=dict(node_id=task["storage_node"],release_at=task["release_at"],published_at=task["published_at"],
                        carrier_policy="on_carrier",evidence_status="proxy")
                check(canonical(bag)==canonical(current_row["runtime_bag"]),"exact independent runtime bag mapping")
                check(current_row["run_contract_sha256"]==run_sha,"external run seal")
                check(type(bag["protected"]) is bool and type(bag["arrival"]) is int and type(bag["deadline"]) is int,"clock/protection types")
                group=current_row["group_id"]
                check(groups.setdefault(group,current_row["projected_destination"])==current_row["projected_destination"],"whole family mapping")
                counts[task["lifecycle"]]+=1
                counts["changed"]+=current_row["original_destination"]!=current_row["projected_destination"]
                counts["segments"]+=len(task["old_segment_ids"])
        check(len(seen)==28506*scale and len(groups)==360,"all expected source and parent groups")
        check(counts["changed"]==4001*scale and counts["early_storage"]==15097*scale,"complete known source counts")
        check(counts["segments"]==43603*scale,"complete original segment counts")
        mappings[scale]=groups
        rows.append(dict(scale=scale,records=len(seen),parent_groups=len(groups),counts=dict(counts)))
    check(mappings[1]==mappings[2],"same full-parent choice across scales")
    result=dict(status="passed",rows=rows)
except Exception:
    result=dict(status="failed",rows=rows,exception=traceback.format_exc())
result.update(checks=checks,physical_runs=0,cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,
    input_sha256=bindings,source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    resource_scope="Same-process independent read/hash/JSON comparison; imports and final writes excluded.",
    qualification="All85518 mappings checked against previously independently audited full projection; no new domain calculation, physics, or independent operating day.")
(out/"results.json").write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='input_sha256'},indent=2))
raise SystemExit(0 if result["status"]=="passed" else 1)
