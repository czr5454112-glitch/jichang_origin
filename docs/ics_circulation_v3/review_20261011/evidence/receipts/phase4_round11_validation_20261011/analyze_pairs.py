"""Read-only paired source-version descriptions; never infer equal-OD benefit."""
from collections import Counter
import gzip, hashlib, json
from pathlib import Path
import sys, time, traceback
ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parent
out=BASE/sys.argv[1]
out.mkdir()
cpu,wall=time.process_time(),time.perf_counter()
bindings={}

def read(path):
    data=path.read_bytes()
    bindings[path.relative_to(ROOT).as_posix()]=hashlib.sha256(data).hexdigest()
    return json.loads(gzip.decompress(data) if path.suffix==".gz" else data)

def describe(raw,tape):
    now=raw["final_snapshot"]["now"]
    complete=raw["completed"]
    return dict(now=now,observed=len(raw["final_snapshot"]["bags"]),complete=len(complete),
        full_count=len(tape),unfinished=len(tape)-len(complete),
        protected_count=sum(b["protected"] for b in tape),
        completed_ontime=sum(b["bag_id"] in complete and complete[b["bag_id"]]<=b["deadline"] for b in tape),
        unfinished_deadline_passed=sum(b["bag_id"] not in complete and now>b["deadline"] for b in tape),
        cost=raw["total_cost"],cost_components=raw["cost_components"])
rows=[]
try:
    for horizon in (80,21600):
        a,b=(BASE/f"{v}_h{horizon}_001" for v in ("original","projected"))
        ta,tb=read(a/"environment_tape.json"),read(b/"environment_tape.json")
        original={t["bag_id"]:t for t in ta}
        projected={t["bag_id"]:t for t in tb}
        assert set(original)==set(projected) and len(ta)==len(tb)==44
        changed={bid for bid in original if original[bid]["destination"]!=projected[bid]["destination"]}
        old,new=read(a/"final_result.json.gz"),read(b/"final_result.json.gz")
        at=read(a/"results.json"); bt=read(b/"results.json")
        row=dict(horizon=horizon,changed_final_count=len(changed),
            original=dict(describe(old,ta),status=at["status"],parent_cpu_seconds=at["cpu_seconds"]),
            projected=dict(describe(new,tb),status=bt["status"],parent_cpu_seconds=bt["cpu_seconds"]),
            matched=[],full_task_rows=[])
        for tick in (10080,11760,24180,28500):
            ap,bp=a/f"matched_{tick}.json.gz",b/f"matched_{tick}.json.gz"
            if not(ap.exists() and bp.exists()):
                continue
            av,bv=read(ap),read(bp)
            item=dict(tick=tick,original=describe(av,ta),projected=describe(bv,tb),completed_both=0,
                completed_only_original=0,completed_only_projected=0,unfinished_both=0,
                earlier=0,same=0,later=0,by_final_change={})
            for cohort in (False,True):
                counts=Counter()
                for bid in original:
                    if (bid in changed)!=cohort: continue
                    ac,bc=av["completed"].get(bid),bv["completed"].get(bid)
                    if ac is not None and bc is not None:
                        counts["completed_both"]+=1
                        counts["earlier" if bc<ac else "same" if bc==ac else "later"]+=1
                    elif ac is not None: counts["completed_only_original"]+=1
                    elif bc is not None: counts["completed_only_projected"]+=1
                    else: counts["unfinished_both"]+=1
                item["by_final_change"][str(cohort)]=dict(counts)
                for k,v in counts.items(): item[k]+=v
            row["matched"].append(item)
        for bid,t in original.items():
            row["full_task_rows"].append(dict(bag_id=bid,original_final=t["destination"],
                projected_final=projected[bid]["destination"],final_changed=bid in changed,
                arrival=t["arrival"],release=t["storage"]["release_at"],deadline=t["deadline"],
                protected=t["protected"],original_completed_at=old["completed"].get(bid),
                projected_completed_at=new["completed"].get(bid),
                qualification="Final raw observations may have different stop ticks; null means censored unfinished."))
        rows.append(row)
    report=dict(status="passed",rows=rows,physical_runs=0,
        qualification="Declared input-version comparison; different final destinations prevent same-OD algorithm-benefit claim. Only common ticks are paired; unfinished is not zero completion time.")
except Exception:
    report=dict(status="failed",rows=rows,physical_runs=0,exception=traceback.format_exc())
report.update(cpu_seconds=time.process_time()-cpu,wall_seconds=time.perf_counter()-wall,input_sha256=bindings,
    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    resource_scope="Read-only same-process interval; imports and final writes excluded.")
(out/"results.json").write_text(json.dumps(report,indent=2))
print(json.dumps({k:v for k,v in report.items() if k not in ("rows","input_sha256")},indent=2))
raise SystemExit(0 if report["status"]=="passed" else 1)
