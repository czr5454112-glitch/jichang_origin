"""Source-bound saved192 review; no policy choice, simulation, or native run."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import itertools
import json
from pathlib import Path

from . import research_native_preference_matrix as runner


def audit(directory):
    directory=Path(directory).resolve();pins={}
    def pin(path,expected=None):
        path=Path(path).resolve();digest=runner.sha(path)
        runner.require(expected is None or digest==expected,"audit_evidence_hash:"+str(path))
        runner.require(str(path) not in pins or pins[str(path)]==digest,"audit_pin_conflict")
        pins[str(path)]=digest
        return json.loads(path.read_bytes()) if path.suffix=="json" or path.suffix==".json" else None
    bounded=pin(directory/"bounded_parent_receipt.json");parent=pin(directory/"parent_receipt.json")
    runner.require(bounded["status"]=="exited" and bounded["exitcode"]==0 and bounded["wall_seconds"]<1080
        and bounded["windows_job_kill_on_close"] is True and parent["source_changed"]==parent["source_closure_changed"]==[],"parent_not_closed")
    index,master=runner.verify_index(directory,bounded["master_index_sha256"])
    for name in ("master_index.json","master_protocol.json","preparation_receipt.json","bounded_dispatch.json"):
        pin(directory/name)
    rows=pin(directory/"branch_ledger.json",parent["ledger"]["sha256"])
    saved=pin(directory/"comparisons.json",parent["comparisons"]["sha256"])
    runner.require(saved==runner.matrix.compare(rows),"persisted_comparisons_mismatch")
    for path,digest in master["source_sha256"].items():pin(path,digest)
    pin(__file__)
    for path in runner.bound.imported_sources():pin(path)
    results,raws={},{}
    actual_counts,unknown_counts,input_counts,route_counts=Counter(),Counter(),Counter(),Counter()
    case_checks={}
    for case_id in master["case_order"]:
        entry=parent["cases"][case_id]
        runner.require(entry["exitcode"]==0 and entry["validation_process"]["exitcode"]==0
            and entry["case_with_validation_wall_seconds"]<180,"case_shared_budget_or_exit")
        case_checks[case_id]=runner.verify_case_artifacts(directory,index,master,case_id)
        case_dir=directory/case_id
        case_plan=pin(case_dir/"preregistered_protocol.json",index["case_plans"][case_id]["sha256"])
        case_rows=pin(case_dir/"branch_ledger.json")
        for name in ("receipt.json","run_acceptance.json","saved_validation.json"):pin(case_dir/name)
        for source,path in case_plan["source_archive"].items():pin(case_dir/path,case_plan["source_sha256"][source])
        input_digests=set()
        for key,row in case_rows.items():
            runner.require(row==rows[key],"master_case_ledger_mismatch")
            item=row["raw_artifact"];raw_path=case_dir/item["path"]
            pin(raw_path,item["sha256"]);pin(case_dir/item["input_path"],item["input_sha256"])
            raw=json.loads(gzip.decompress(raw_path.read_bytes()));raws[key]=raw
            input_digests.add(runner.bound.config_sha(raw["input"]))
            times={j["business_bag_id"]:j["completed_at"] for j in raw["result"]["jobs"]}
            runner.require(set(times)==runner.matrix.JOBS and len(raw["result"]["jobs"])==5,"raw_five_job_domain")
            summary=row["summary"];actual_counts[row["status"]]+=1
            failures=[]
            for name in ("common_horizon_complete","business_complete","required_transfer_lineages_received","all_routes_updated",
                "chosen_routes_match_executed_edges","same_L_two_returns_and_two_reloads","stock_preserved",
                "blocker_actual_path1to9","all_required_inputs_verified","selected_actions_executed"):
                if summary.get(name) is not True:failures.append(name)
            if row["status"]!="assessed":unknown_counts[tuple(failures)]+=1
            decisions=[]
            for owner,sequence in raw["decisions"].items():
                for decision in sequence:
                    info=decision["information"]
                    reasons=info.get("reasons",[])+info.get("bundle",{}).get("reasons",[])
                    input_counts[(owner,decision["phase"],info["status"],tuple(reasons))]+=1
                    decisions.append({"owner":owner,"phase":decision["phase"],"at":decision["at"],"status":info["status"],
                        "reasons":reasons,"fallback":decision["fallback_used"],"selected_action_admitted":decision["selected_action_admitted"],
                        "native_request_id":decision["native_request_id"],"actual_first_action":decision["executed_first_action"]})
            routes=[]
            for identity,operation in raw["outbox"].items():
                if operation["kind"]!="route":continue
                req=operation["request"];ack=operation.get("ack",{})
                edges=[e for e in raw["result"]["receipts"] if e["event"]=="EDGE_ENTER"
                    and e["business_bag_id"]==req["business_bag_id"] and e["from"]==req["from"]]
                actual=edges[0]["to"] if len(edges)==1 else None
                route_counts[(req["business_bag_id"],req["next"],ack.get("status"),ack.get("reason"),actual)]+=1
                routes.append({"request_id":identity,"request":req,"ack":ack,"actual_edges":edges,"selected_actual_match":actual==req["next"]})
            results[key]={"status_retained":row["status"],"vector":row["vector"],"completion":times,
                "completion_sum":summary["completion_sum"],"failure_predicates":failures,"later_inputs":decisions,
                "route_operations":routes,"initial_actual_next":summary["initial_actual_next"],
                "first_reuse_actual_next":summary["first_reuse_actual_next"],"physical_audit":summary["audit"],
                "all_five_native_complete":summary["business_complete"] is True,
                "raw_artifact":str(raw_path),"raw_sha256":item["sha256"]}
        runner.require(len(input_digests)==1,"case_input_changed_across_actions")
        case_checks[case_id]["same_full_input_sha256"]=next(iter(input_digests))
    runner.require(len(rows)==len(raws)==len(results)==192,"full192_denominator")
    family_reviews,pair_counts,pairs,interactions={},Counter(),[],[]
    for case_id,keys in master["case_groups"].items():
        base_key=master["incumbent_keys"][case_id];base=rows[base_key]
        lookup={runner.matrix.key_for(rows[k]["vector"]):k for k in keys}
        families={}
        for initial in ("native_default","prefer_2"):
            members=[k for k in keys if rows[k]["vector"]["initial_action"]==initial]
            known=runner.matrix.valid(base) and all(runner.matrix.valid(rows[k]) for k in members)
            eligible=[k for k in members if known and all(results[k]["completion"][j]<=results[base_key]["completion"][j] for j in runner.matrix.JOBS)]
            best=min(eligible,key=lambda k:(results[k]["completion_sum"],k),default=None)
            saved_family=saved["cases"][case_id]["fixed_initial_families"][initial]
            runner.require(len(members)==16 and saved_family["best_protected_key"]==best
                and (saved_family["status"]=="complete_assessed_finite_reference")==known,"complete16_family_replay")
            later_best={choice:min([k for k in eligible if rows[k]["vector"]["later_action"]==choice],
                key=lambda k:(results[k]["completion_sum"],k),default=None) for choice in ("native_default","prefer_8")}
            families[initial]={"status":saved_family["status"],"all16_member_keys":members,"best_protected_key":best,
                "best_vector":rows[best]["vector"] if best else None,"best_completion":results[best]["completion"] if best else None,
                "best_sum":results[best]["completion_sum"] if best else None,"best_by_later_action":later_best}
        if all(f["best_protected_key"] for f in families.values()):
            left,right=(families[a]["best_protected_key"] for a in ("native_default","prefer_2"))
            delta={j:results[right]["completion"][j]-results[left]["completion"][j] for j in runner.matrix.JOBS}
            families["best_family_contrast"]={"default_key":left,"prefer2_key":right,"prefer2_minus_default_per_job":delta,
                "strict_protected":all(t<=0 for t in delta.values()),"sum_gain":results[left]["completion_sum"]-results[right]["completion_sum"],
                "offline_reference_only":True,"online_method_claim":False}
        family_reviews[case_id]=families
        for key in keys:
            row=rows[key];vector=row["vector"]
            for coordinate,default,field in (("initial_action","native_default","initial_actual_next"),
                ("later_action","native_default","first_reuse_actual_next")):
                if vector[coordinate]==default:continue
                control=lookup[runner.matrix.key_for({**vector,coordinate:default})]
                known=runner.matrix.valid(row) and runner.matrix.valid(rows[control])
                status="unknown" if not known else "actual_edge_changed" if results[key][field]!=results[control][field] else "no_actual_edge_change"
                delta={j:results[key]["completion"][j]-results[control]["completion"][j] for j in runner.matrix.JOBS} if known else None
                protected=all(t<=0 for t in delta.values()) if known else None
                gain=results[control]["completion_sum"]-results[key]["completion_sum"] if known else None
                pair_counts[(coordinate,status,protected,gain is not None and gain>0)]+=1
                record={"coordinate":coordinate,"key":key,"control_key":control,"status":status,"strict_protected":protected,
                    "sum_gain":gain,"per_job_delta":delta,"candidate_actual_next":results[key][field],"control_actual_next":results[control][field]}
                if coordinate=="later_action":
                    a,b=raws[key],raws[control];da,db=a["decisions"]["B"][0],b["decisions"]["B"][0]
                    record["same_decision_epoch"]=da["at"]==db["at"]
                    record["ordered_native_call_prefix_equal"]=a["calls"][:da["predecision_call_prefix_count"]]==b["calls"][:db["predecision_call_prefix_count"]]
                    record["same_current_owner_view"]=da["actual_local_view"]==db["actual_local_view"]
                    cutoff=min(da["at"],db["at"])
                    record["physical_receipts_through_common_decision_equal"]=[r for r in a["result"]["receipts"] if r["time"]<=cutoff]==[r for r in b["result"]["receipts"] if r["time"]<=cutoff]
                    record["hidden_native_checkpoint_equality_certified"]=False
                pairs.append(record)
        windows=sorted({rows[k]["vector"]["empty_departure"] for k in keys})
        for w0,w1 in itertools.combinations(windows,2):
            for delay,later in itertools.product((0.,.5),("native_default","prefer_8")):
                cube=[lookup[(initial,window,delay,later)] for initial,window in
                    (("native_default",w0),("prefer_2",w0),("native_default",w1),("prefer_2",w1))]
                known=all(runner.matrix.valid(rows[k]) for k in cube)
                values=[results[k]["completion_sum"] for k in cube]
                interactions.append({"case":case_id,"rows00_10_01_11":cube,"status":"assessed" if known else "unknown",
                    "objective_interaction":values[3]-values[2]-values[1]+values[0] if known else None,
                    "protection_or_online_necessity_inferred":False})
    counts={"actual_status":dict(actual_counts),"unknown_predicates":[{"predicates":list(k),"count":v} for k,v in unknown_counts.items()],
        "later_inputs":[{"owner":k[0],"phase":k[1],"status":k[2],"reasons":list(k[3]),"count":v} for k,v in input_counts.items()],
        "route_outcomes":[{"job":k[0],"selected_next":k[1],"ack":k[2],"reason":k[3],"actual_next":k[4],"count":v} for k,v in route_counts.items()],
        "paired_contrasts":[{"coordinate":k[0],"status":k[1],"strict_protected":k[2],"positive_gain":k[3],"count":v} for k,v in pair_counts.items()],
        "registered_comparison_status":dict(Counter(r["status"] for g in saved["cases"].values() for r in g["rows"].values())),
        "complete_initial_families":sum(f["status"]=="complete_assessed_finite_reference" for g in saved["cases"].values() for f in g["fixed_initial_families"].values()),
        "all192_five_jobs_completed":all(r["all_five_native_complete"] for r in results.values()),
        "all192_physical_audit_passed":all(r["physical_audit"]["status"]=="passed" for r in results.values())}
    runner.require(all(runner.sha(p)==h for p,h in pins.items()),"audit_evidence_changed")
    return {"schema":"g31.native_preference_matrix.saved_audit.v1","status":"saved192_revalidated_no_new_native",
        "evidence_sha256":pins,"counts":counts,"case_checks":case_checks,"rows":results,"family_reviews":family_reviews,
        "paired_contrasts":pairs,"four_cell_interactions":interactions,"new_native_executions":0,
        "unknown_results_promoted":False,"online_method_or_novelty_certified":False,
        "limits":["Finite fixed counterfactual action family with all192 retained; no outcomes feed online choices.",
            "Actual edge differences and objective interactions do not alone establish strict protection, necessity, or a new solver.",
            "Known prior native calls/current local view and saved physical prefixes do not prove hidden native checkpoint equality.",
            "Incomplete16-member references remain unknown even when their known subset contains a good row."]}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--directory",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True);args=parser.parse_args()
    runner.require(not args.output.exists(),"audit_output_exists")
    result=audit(args.directory)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result["counts"],indent=2))


if __name__=="__main__":main()
