"""Stream native005 versus native006 rate-zero physical fields and transactions.

Only three preregistered scoring diagnostics may differ. This does not replay the
simulator or re-audit geometry; it checks complete run records without retaining
large bag populations or the rolling ledger in memory.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from pathlib import Path

OLD_CORE="c997415fe060833da35712b6179ab24a99c122811e1364dd1f1344f098674537"
NEW_CORE="8ccaa58f56fd0b941aebf8527b713d1b1f0605164ee779f1abf3ecd689c924b0"
COUNTERS={"score_expansions","local_scoring_calendar_queries"}
ADDED_FIELDS={"last_effective_route_excess_seconds","admission_effective_route_excess_seconds",
              "admission_static_remaining_seconds","admission_route_excess_seconds","admission_route_budget_violated"}
SUMMARY_EXACT=("tasks","admitted","completed","on_time","planning_attempts","failed_attempts",
               "search_expansions","backtracks","safety_neighbor_queries","edge_safety_queries",
               "source_resource_queries","goal_resource_queries","futurecalendar_retry_jumps",
               "route_bound_prunes","events","event_budget_exhausted","executed_horizon",
               "inroute_decisions","inroute_keep_certificate","inroute_replacement_attempts",
               "inroute_replacement_successes","inroute_fallbacks","inroute_search_expansions",
               "rolling_ledger_records","score_budget_exhaustions","local_score_budget_exhausted_decisions")


def normalized(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),allow_nan=False)


def read(path): return json.loads(Path(path).read_text(encoding="utf-8"))


def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()


def compare_bag(old,new,*,require_zero_queries=True):
    problems=[]
    unknown=set(new)-set(old)-ADDED_FIELDS
    if unknown:problems.append("unregistered_new_fields:"+",".join(sorted(unknown)))
    for key,value in old.items():
        if key not in new:
            problems.append("missing_field:"+key);continue
        if key in COUNTERS:
            if type(new[key]) is not int or not 0<=new[key]<=value or (require_zero_queries and new[key]!=0):
                problems.append("invalid_diagnostic_counter:"+key)
        elif key=="route_decisions":
            a,b=value,new[key]
            if len(a)!=len(b):
                problems.append("route_decision_count_changed");continue
            for index,(left,right) in enumerate(zip(a,b)):
                if len(left)!=5 or len(right)!=5 or normalized([left[i] for i in (0,1,4)])!=normalized([right[i] for i in (0,1,4)]):
                    problems.append("logical_route_decision_changed:"+str(index))
                elif require_zero_queries and (right[2]!=0 or right[3]!=0):
                    problems.append("static_decision_reports_calendar_query:"+str(index))
        elif normalized(value)!=normalized(new[key]):
            problems.append("field_changed:"+key)
    return problems


def stream_compare(old_path,new_path,*,bags):
    old_hash,new_hash=hashlib.sha256(),hashlib.sha256()
    count=errors=0;examples=[];raw_equal=True
    with Path(old_path).open("rb") as a,Path(new_path).open("rb") as b:
        for index,(left,right) in enumerate(itertools.zip_longest(a,b),1):
            if left is not None:old_hash.update(left)
            if right is not None:new_hash.update(right)
            raw_equal &= left==right
            count+=1
            if left is None or right is None:
                problems=["record_count_changed"]
            else:
                old,new=json.loads(left),json.loads(right)
                problems=compare_bag(old,new) if bags else ([] if normalized(old)==normalized(new) else ["transaction_changed"])
            if problems:
                errors+=1
                if len(examples)<20:examples.append(dict(line=index,problems=problems))
    return dict(passed=errors==0,records=count,changed_records=errors,examples=examples,
                old_sha256=old_hash.hexdigest(),new_sha256=new_hash.hexdigest(),serialized_bytes_exact=raw_equal)


def run(old_dir,new_dir):
    old_manifest=read(old_dir/"manifest.json");new_manifest=read(new_dir/"manifest.json")
    if old_manifest.get("status")!="complete" or new_manifest.get("status")!="complete":
        raise ValueError("both runs must have completed their audit pipeline")
    for manifest,expected in ((old_manifest,OLD_CORE),(new_manifest,NEW_CORE)):
        if manifest.get("source_sha256",{}).get("core.cpp")!=expected:
            raise ValueError("expected immutable005/006 source hashes")
    for key in ("map","scale","canonical_sha256","profile_sha256","task_count"):
        if old_manifest.get(key)!=new_manifest.get(key):raise ValueError("input identity changed:"+key)
    old_cfg=dict(old_manifest["config"]);new_cfg=dict(new_manifest["config"])
    if old_cfg.pop("route_excess_retry_relaxation_rate",0)!=0 or new_cfg.pop("route_excess_retry_relaxation_rate",0)!=0:
        raise ValueError("this proof applies only to rate zero")
    if old_cfg!=new_cfg:raise ValueError("other controls changed")
    if (new_cfg.get("min_depth"),new_cfg.get("max_depth"),new_cfg.get("adaptive"),new_cfg.get("congestion_weight"))!=(1,1,False,0):
        raise ValueError("this preregistered diagnostic mask requires fixed1 weight0")
    files=[old_dir/"manifest.json",new_dir/"manifest.json",old_dir/"bags.jsonl",new_dir/"bags.jsonl",
           old_dir/"rolling_events.jsonl",new_dir/"rolling_events.jsonl",old_dir/"native_summary.json",new_dir/"native_summary.json"]
    stamps={str(p):(p.stat().st_size,p.stat().st_mtime_ns) for p in files}
    bags=stream_compare(old_dir/"bags.jsonl",new_dir/"bags.jsonl",bags=True)
    for manifest,hashkey in ((old_manifest,"old_sha256"),(new_manifest,"new_sha256")):
        if manifest.get("bags_sha256")!=bags[hashkey]:raise ValueError("finished-run bag hash changed")
    events=stream_compare(old_dir/"rolling_events.jsonl",new_dir/"rolling_events.jsonl",bags=False)
    old_summary=read(old_dir/"native_summary.json");new_summary=read(new_dir/"native_summary.json")
    differences={key:dict(old=old_summary.get(key),new=new_summary.get(key)) for key in SUMMARY_EXACT
                 if key not in old_summary or key not in new_summary or normalized(old_summary[key])!=normalized(new_summary[key])}
    if any((Path(p).stat().st_size,Path(p).stat().st_mtime_ns)!=stamp for p,stamp in stamps.items()):
        raise ValueError("run files changed during parity scan")
    return dict(schema="g31.nowait.rate0_full_parity.v1",passed=bags["passed"] and events["passed"] and not differences,
        old_run=str(old_dir.resolve()),new_run=str(new_dir.resolve()),bags=bags,rolling_events=events,
        stable_summary_differences=differences,allowed_diagnostic_changes=sorted(COUNTERS|{"route_decisions[actual_query_depth,local_score_queries]"}),
        source_sha256=dict(old=OLD_CORE,new=NEW_CORE,tool=file_sha(__file__)),
        manifest_sha256=dict(old=file_sha(old_dir/"manifest.json"),new=file_sha(new_dir/"manifest.json")),
        boundary="All prior bag fields except preregistered score observations are exact; decision node/requested k/exhaustion remain exact. All transactions exact. Performance timings are separate observations, not parity requirements.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old",type=Path,required=True)
    parser.add_argument("--new",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise FileExistsError("parity receipt already exists")
    result=run(args.old,args.new)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(passed=result['passed'],bags=result['bags']['records'],events=result['rolling_events']['records'])))
    if not result["passed"]:raise SystemExit(2)


if __name__=="__main__":main()
