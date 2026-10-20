"""Standard-library independent arithmetic over saved paired native evidence."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path


def read(path):
    content = Path(path).read_bytes()
    return json.loads(gzip.decompress(content) if str(path).endswith(".gz") else content)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cost_from_raw(specifications, result, start, end):
    jobs = {row["business_bag_id"]: row for row in result["jobs"]}
    if len(jobs) != len(specifications) or set(jobs) != set(specifications):
        raise ValueError("independent_review:lost_population")
    if result["physical_clock"] < end or not result["advance"]["horizon_complete"]:
        raise ValueError("independent_review:unclosed_window")
    arrivals, completions, loads = {}, {}, {}
    for row in result["receipts"]:
        target = (arrivals if row["event"] == "BAG_ARRIVAL" else
            completions if row["event"] == "UNLOAD_COMPLETE" else
            loads if row["event"] == "LOAD_START" else None)
        if target is not None:
            identity = row["business_bag_id"]
            if identity in target:
                raise ValueError("independent_review:duplicate_business_event")
            target[identity] = row["time"]
    per_job, waits, service, completed_by_end = {}, [], [], {}
    for identity, specification in specifications.items():
        arrival = specification["arrival"]
        complete = completions.get(identity, math.inf)
        job = jobs[identity]
        if arrival <= result["physical_clock"] and arrivals.get(identity) != arrival:
            raise ValueError("independent_review:arrival_receipt_disagrees_with_input")
        if (complete < math.inf) != (job["completed_at"] >= 0):
            raise ValueError("independent_review:completion_receipt_disagrees_with_snapshot")
        if complete < math.inf and job["completed_at"] != complete:
            raise ValueError("independent_review:completion_time_disagrees")
        cost = max(0., min(complete,end)-max(arrival,start))
        wait = max(0., min(loads.get(identity,math.inf),end)-max(arrival,start))
        per_job[identity] = cost
        waits.append(wait)
        service.append(cost-wait)
        if complete <= end:
            completed_by_end[identity] = complete
    return {"cost": math.fsum(per_job.values()), "waiting": math.fsum(waits),
        "loaded_processing": math.fsum(service), "per_job": per_job,
        "completed": completed_by_end, "arrived": sum(row["arrival"]<=end for row in specifications.values())}


def review(cycle, pair_name):
    cycle = Path(cycle)
    directories = [cycle/(pair_name+"_"+branch+"_001") for branch in ("a_ref","a_patch")]
    dataset_path = cycle/(pair_name+"_dataset_001.json.gz")
    dataset = read(dataset_path)
    plans = [read(path/"plan.json") for path in directories]
    traces = [read(path/"pair_trace.json.gz") for path in directories]
    results = [read(path/"final_result.json.gz") for path in directories]
    input_data = [read(path/"input.json") for path in directories]
    calls = [read(path/"client_calls.json.gz") for path in directories]
    if input_data[0] != input_data[1] or plans[0]["binary"] != plans[1]["binary"]:
        raise ValueError("independent_review:input_or_binary_differs")
    if plans[0]["sources"] != plans[1]["sources"]:
        raise ValueError("independent_review:full_archived_source_manifest_differs")
    selected = [trace["selected"] for trace in traces]
    if any(row is None for row in selected):
        raise ValueError("independent_review:no_actual_anchor")
    if selected[0]["observation"] != selected[1]["observation"] or selected[0]["prefix"] != selected[1]["prefix"]:
        raise ValueError("independent_review:public_or_full_prefix_differs")
    if selected[0]["baseline_decision"] != selected[1]["baseline_decision"]:
        raise ValueError("independent_review:baseline_batch_differs")
    start, end = selected[0]["label_start"], selected[0]["label_end"]
    specs = {row["business_bag_id"]: row for row in input_data[0]["jobs"]}
    recomputed = [cost_from_raw(specs,result,start,end) for result in results]
    difference = recomputed[0]["cost"]-recomputed[1]["cost"]
    if abs(difference-dataset["pair"]["advantage_bag_seconds"])>1e-7:
        raise ValueError("independent_review:pair_target_disagrees")
    target = selected[1]["chosen_action"]["tray_id"]
    other_batches = [[row for row in selection["chosen_decision"]["intents"]
        if row["tray_id"] != target] for selection in selected]
    if other_batches[0] != other_batches[1]:
        raise ValueError("independent_review:other_initial_batch_allocations_changed")
    execution = []
    for branch, selection, result, submitted in zip(("a_ref","a_patch"),selected,results,calls):
        action = [row for row in submitted if row.get("kind")=="transfer" and not row.get("retry")
            and row["at"]==start and row["request"]["tray_id"]==target]
        if len(action)>1:
            raise ValueError("independent_review:multiple_target_submits")
        observed = [row for row in result["receipts"] if row.get("tray_id")==target
            and start<=row["time"]<=end and row["event"] in
            ("EXPORT_GRANTED","EMPTY_RECEIVED","LOAD_START","UNLOAD_COMPLETE","HOLD_COMPLETE")]
        execution.append({"branch":branch,"actual_anchor_submissions":action,
            "target_tray_lifecycle":observed})
    categories = Counter()
    completed_difference, cost_difference = [], []
    for identity in specs:
        left,right = [row["completed"].get(identity) for row in recomputed]
        category = ("unknown_incomplete" if left is None or right is None else
            "improved" if right<left else "harmed" if right>left else "equal")
        categories[category]+=1
        if category in ("harmed","improved"):
            completed_difference.append({"business_bag_id":identity,"comparison":category,
                "patched_minus_reference_completion_seconds":right-left})
        amount=recomputed[0]["per_job"][identity]-recomputed[1]["per_job"][identity]
        if amount:
            cost_difference.append({"business_bag_id":identity,"advantage_bag_seconds":amount,
                "reference_completed_at_or_unknown":left,"patch_completed_at_or_unknown":right})
    old_completed,new_completed=[set(row["completed"]) for row in recomputed]
    return {"schema":"g31.airport.pair_independent_review.v1","registered_pair":pair_name,
        "sources":{str(path.resolve()):sha(path) for path in [dataset_path]+[
            directory/name for directory in directories for name in
            ("plan.json","pair_trace.json.gz","final_result.json.gz","input.json","client_calls.json.gz")]},
        "same_full_archived_source_manifest":True,"same_binary_and_input":True,
        "same_full_recorded_native_controller_client_selector_prefix":True,
        "prefix":selected[0]["prefix"],"native_state_independently_replayed":False,
        "prefix_verification_scope":"compared recorded full-state hashes and exact public evidence; no new native replay",
        "label_start":start,"label_end":end,"physical_population":len(specs),
        "complete_cost_recomputed_from_input_and_native_receipts":True,
        "costs":[{k:v for k,v in row.items() if k not in ("per_job","completed")} for row in recomputed],
        "advantage_bag_seconds":difference,
        "wait_for_tray_improvement_bag_seconds":recomputed[0]["waiting"]-recomputed[1]["waiting"],
        "loaded_processing_improvement_bag_seconds":recomputed[0]["loaded_processing"]-recomputed[1]["loaded_processing"],
        "completed_counts":[len(row["completed"]) for row in recomputed],
        "reference_only_completed":sorted(old_completed-new_completed),"patch_only_completed":sorted(new_completed-old_completed),
        "per_job_comparison_counts":dict(categories),"known_completion_differences":completed_difference,
        "all_other_initial_batch_allocations_preserved":True,"preserved_count":len(other_batches[0]),
        "execution":execution,
        "largest_positive_cost_contributors":sorted(cost_difference,key=lambda row:-row["advantage_bag_seconds"])[:10],
        "largest_negative_cost_contributors":sorted(cost_difference,key=lambda row:row["advantage_bag_seconds"])[:10],
        "finite_window_per_job_contributions_sum":math.fsum(row["advantage_bag_seconds"] for row in cost_difference),
        "strict_per_job_nonharm":False,"trained_rl_increment":False,
        "scope":"one isolated bounded action comparison on a conditional synthetic train parent"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle",type=Path,required=True)
    parser.add_argument("--pair",required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    result=review(args.cycle,args.pair)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf8") as stream:
        json.dump(result,stream,indent=2,ensure_ascii=False,allow_nan=False)
    print(json.dumps({k:result[k] for k in ("registered_pair","advantage_bag_seconds",
        "wait_for_tray_improvement_bag_seconds","loaded_processing_improvement_bag_seconds",
        "completed_counts","per_job_comparison_counts","reference_only_completed","patch_only_completed")}))


if __name__=="__main__":
    main()
