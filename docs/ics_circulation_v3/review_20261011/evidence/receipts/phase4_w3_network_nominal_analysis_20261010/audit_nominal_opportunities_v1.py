"""Independent all-opportunity nominal value/census audit, no new simulations."""
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
import argparse
import json
from pathlib import Path
from time import perf_counter, process_time

from audit_round5_full_cycle import Audit, ROOT, digest, file_hash, physical, read


def geometries(state, candidates):
    geometries, timed, interventions, witnesses = [], [], [], []
    for candidate in candidates:
        prefix = dict(candidate)
        bag = state["bags"][candidate["bag_id"]]
        if not bag["protected"]:
            for index, leg in enumerate(candidate["legs"]):
                end = state["network"]["edges"][leg["edge_id"]]["target"]
                if state["network"]["nodes"][end]["can_wait"]:
                    if index < len(candidate["legs"])-1:
                        prefix.update(legs=candidate["legs"][:index+1], unload_complete=leg["arrive"],
                            usable_at=leg["arrive"], destination_node=end, prefix_only=True,
                            continuation_destination=bag["destination"])
                    break
        end = (state["network"]["edges"][prefix["legs"][-1]["edge_id"]]["target"] if prefix["legs"]
               else state["trays"][prefix["tray_id"]]["node"])
        geometries.append(tuple(leg["edge_id"] for leg in prefix["legs"]))
        timed.append(digest({"tray_id":prefix["tray_id"],"bag_id":prefix["bag_id"],"legs":prefix["legs"],
            "destination_node":end,"unload_complete":prefix["unload_complete"],"usable_at":prefix["usable_at"],
            "prefix_only":prefix["prefix_only"]}))
        # Within one fixed state, module and each resource dependency hash are
        # constants. Route semantics determine all differing dependency names.
        def semantic(item):
            return {k:item[k] for k in ("tray_id","bag_id","legs","unload_complete","usable_at",
                                       "prefix_only","continuation_destination")}
        interventions.append(digest({"committed":semantic(prefix),"conditional":semantic(candidate) if prefix["prefix_only"] else None}))
        witnesses.append(tuple(leg["edge_id"] for leg in candidate["legs"]))
    return geometries,timed,interventions,witnesses


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--run",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    folder=args.run.resolve()
    wall,cpu=perf_counter(),process_time()
    audit=Audit()
    protocol=read(folder/"protocol.json")
    audit.bind(folder/"probe.py",protocol["script_sha256"])
    for name,expected in protocol["source_sha256"].items():
        audit.bind(folder/"source_snapshot"/name,expected)
        audit.bind(ROOT/"scripts/experiments/ics_circulation_v3"/name,expected)
    for name,expected in protocol["input_sha256"].items():
        audit.bind(ROOT/name,expected)
    audit.bind(folder/"collection_reuse_manifest.json",protocol["reused_collection_manifest_sha256"])
    reuse=read(folder/"collection_reuse_manifest.json")
    audit.bind(Path(reuse["prior"])/"manifest.json",reuse["prior_manifest_sha256"])
    for name,expected in reuse["files"].items():
        audit.bind(folder/name,expected)
        audit.bind(Path(reuse["prior"])/name,expected)
    for name,expected in read(folder/"full_input_manifest_start.json").items():
        audit.bind(folder/name,expected)
    audit.manifest(folder/"pilot")
    audit.manifest(folder/"full")
    full=read(folder/"full/summary.json")
    attempt_by_id,requests,collections={},[],{}
    previous=ROOT/"outputs/experiments/ics_circulation_v3/phase4_w3_network_role_labels_parallel_20261009"
    for scene in protocol["scenes"]:
        body=read(folder/"collections"/scene/"collection.json.gz")
        collections[scene]=body
        old=read(previous/scene/(scene+"_collection.json"))
        audit.check(physical(body["result"])==physical(old["result"]),scene,"nominal raw physical result differs")
        audit.check(body["searches"]==old["metadata"]["searches"],scene,"nominal raw search ledger differs")
        audit.check(body["search_calls"]==len(body["searches"]) and body["search_work"]==sum(q["work"] for q in body["searches"]),scene,"search count/work differs")
        audit.check([r["identity"] for r in body["attempts"]]==[r["identity"] for r in old["opportunities"]],scene,"all original attempt denominator differs")
        commits={e["candidate_id"]:e for e in body["result"]["trace"] if e["event"]=="route_commit"}
        for metadata,old_opportunity in zip(body["attempts"],old["opportunities"]):
            row=read(folder/"collections"/scene/f"d{metadata['decision_index']:04d}.json")
            identity=row["identity"]
            attempt_by_id[identity]=row
            audit.check(all(row[k]==old_opportunity[k] for k in ("time","version","source_node","role","protected","bag_id","tray_id","candidate_count","cursor","next_slow_trigger_at")),identity,"original attempt fields differ")
            audit.check(row["original_role_sample"]==old_opportunity["sampled"],identity,"original sample marker differs")
            audit.check(digest(row["state"])==row["state_sha256"] and row["candidate_count"]==len(row["candidates"]),identity,"state/candidate integrity differs")
            geo,timed,actions,witness=geometries(row["state"],row["candidates"])
            audit.check([list(g) for g in geo]==row["prefix_geometries"] and len(set(geo))==row["prefix_geometry_distinct"],identity,"spatial prefix classification differs")
            audit.check(timed==row["timed_prefix_keys"] and len(set(timed))==row["timed_prefix_distinct"],identity,"timed prefix classification differs")
            audit.check(len(set(actions))==row["actual_action_distinct"] and len(set(witness))==row["full_witness_geometry_distinct"],identity,"conditional/route distinction differs")
            audit.check(digest(row["future_event_engine_only"])==row["future_sha256"],identity,"nominal future hash differs")
            if row["candidate_count"]:
                chosen=row["candidates"][row["actual_chosen_index"]]
                commit=commits.get(chosen["candidate_id"])
                audit.check(commit is not None and commit["time"]==row["time"],identity,"reported actual choice not in original physical commit log")
            else:
                audit.check(row["actual_chosen_index"] is None,identity,"zero pool received an invented choice")
        requests.extend(body["requests"])
    audit.check(len(attempt_by_id)==180 and len(requests)==693 and sum(not r["candidate_count"] for r in attempt_by_id.values())==6,folder,"all actual 180/693/6 domain differs")
    rows=full["rows"]
    audit.check(len(rows)==len(requests)==full["planned_requests"] and {r["request_key"] for r in rows}=={r["request_key"] for r in requests},folder,"full normal candidate request set differs")
    audit.check(full["status_counts"]==dict(Counter(r["status"] for r in rows)),folder,"status counts differ")
    outcomes,per_sample= {},defaultdict(list)
    for row in rows:
        per_sample[row["sample"]].append(row)
        if row["status"]=="worker_failure":
            continue
        path=folder/row["file"]
        audit.bind(path,row["sha256"])
        data=read(path)
        where=row["request_key"]
        sample=attempt_by_id[row["sample"]]
        audit.check(all(data["request"][k]==row[k] for k in ("sample","candidate","actual_action_key","future_sha256","checkpoint_sha256")),where,"raw branch request differs")
        ledger=dict(sample["state"]["bags"])
        ledger.update((b["bag_id"],b) for b in sample["future_event_engine_only"])
        audit.check(set(data["expected_task_ids"])==set(ledger),where,"whole nominal ledger differs")
        audit.check(data["search_calls"]==len(data["searches"]) and data["search_work"]==sum(q["work"] for q in data["searches"]),where,"branch search ledger differs")
        audit.check(data["cache_before"]==sample["routing_cache"],where,"actual-cursor initial private cache differs")
        for time,endpoint in data["endpoints"].items():
            audit.result(endpoint["result"],ledger,where+":"+time)
        if data["result"] is not None:
            audit.result(data["result"],ledger,where+":final")
        if data["status"]=="controller_quiescent":
            source=read(previous/row["scene"]/(row["scene"]+"_input.json"))
            expiry=max((f["published_at"]+61 for f in source["forecasts"]),default=sample["time"])
            audit.drained(data,ledger,expiry,where)
        # Retain sufficient metric evidence, not 693 full original-map traces.
        # The immutable raw files remain the physical evidence authority.
        def compact(result):
            if result is None:
                return None
            return {k:result[k] for k in ('total_cost','cost_components','completed')} | {
                'completed_sha256':digest(result['completed']),
                'tray_positions_sha256':digest({k:t['node'] for k,t in result['final_trays'].items()})}
        outcomes[where]={"h80":compact(data["endpoints"].get(str(data["old80_at"]),{}).get("result")),"final":compact(data["result"])}
    states=[]
    for identity,sample in attempt_by_id.items():
        candidates=sorted(per_sample[identity],key=lambda r:r["candidate"])
        audit.check(len(candidates)==sample["candidate_count"],identity,"candidate count changed")
        values={}
        for endpoint in ("h80","final"):
            complete=[r for r in candidates if r["request_key"] in outcomes and outcomes[r["request_key"]][endpoint] is not None
                      and (endpoint=="h80" or r["status"]=="controller_quiescent")]
            if len(complete)!=len(candidates) or not candidates:
                values[endpoint]={"complete_pool":False}
                continue
            costs=[outcomes[r["request_key"]][endpoint]["total_cost"] for r in candidates]
            best=min(costs)
            values[endpoint]={"complete_pool":True,"costs":costs,"optset":[i for i,c in enumerate(costs) if abs(c-best)<1e-8],
                "spread":max(costs)-best,"actual_choice_regret":costs[sample["actual_chosen_index"]]-best,
                "first_normal_candidate_regret":costs[0]-best,
                "cost_components":[outcomes[r["request_key"]][endpoint]["cost_components"] for r in candidates],
                "distinct_completion_vectors":len({outcomes[r['request_key']][endpoint]['completed_sha256'] for r in candidates}),
                "distinct_tray_position_vectors":len({outcomes[r['request_key']][endpoint]['tray_positions_sha256'] for r in candidates})}
        if values["final"]["complete_pool"]:
            original=collections[sample["scene"]]["result"]
            actual=outcomes[candidates[sample["actual_chosen_index"]]["request_key"]]["final"]
            audit.check(actual["cost_components"]==original["cost_components"] and actual["completed"]==original["completed"],identity,"actual chosen continuation does not reproduce deployed nominal cost/completion")
        states.append({k:sample[k] for k in ("identity","scene","time","source_node","role","candidate_count","original_role_sample","prefix_geometry_distinct","timed_prefix_distinct","actual_action_distinct","actual_chosen_index")} | {
            "candidate_family":('zero' if not sample['candidate_count'] else 'spatial_prefix' if sample['prefix_geometry_distinct']>1 else 'timed_prefix_only' if sample['timed_prefix_distinct']>1 else 'conditional_witness_only' if sample['actual_action_distinct']>1 else 'identical_actual_action'),
            "values":values})
    def summarize(selected):
        result={"attempts":len(selected),"zero":sum(not s["candidate_count"] for s in selected),
            "original_sample_attempts":sum(s['original_role_sample'] for s in selected),
            "spatial_branching":sum(s["prefix_geometry_distinct"]>1 for s in selected),
            "actual_chosen_indices":dict(Counter(str(s['actual_chosen_index']) for s in selected)),
            "candidate_families":dict(Counter(s['candidate_family'] for s in selected))}
        for endpoint in ("h80","final"):
            complete=[s for s in selected if s["values"][endpoint]["complete_pool"]]
            result[endpoint]={"complete_pools":len(complete),
                "nonflat":sum(s["values"][endpoint]["spread"]>1e-8 for s in complete),
                "actual_choice_suboptimal":sum(s["values"][endpoint]["actual_choice_regret"]>1e-8 for s in complete),
                "correlated_sum_of_local_actual_choice_regret":sum(s["values"][endpoint]["actual_choice_regret"] for s in complete),
                "max_actual_choice_regret":max((s["values"][endpoint]["actual_choice_regret"] for s in complete),default=0),
                "first_normal_candidate_suboptimal":sum(s["values"][endpoint]["first_normal_candidate_regret"]>1e-8 for s in complete),
                "correlated_sum_of_local_first_candidate_regret":sum(s["values"][endpoint]["first_normal_candidate_regret"] for s in complete),
                "different_completion_vector_pools":sum(s["values"][endpoint]['distinct_completion_vectors']>1 for s in complete),
                "different_tray_position_pools":sum(s["values"][endpoint]['distinct_tray_position_vectors']>1 for s in complete),
                "cost_flat_but_other_metric_differs":sum(s["values"][endpoint]['spread']<=1e-8 and (s["values"][endpoint]['distinct_completion_vectors']>1 or s["values"][endpoint]['distinct_tray_position_vectors']>1) for s in complete)}
        return result
    groups={}
    for role in ("all","origin","continuation"):
        for subset in ("all","original_sample","spatial_branch"):
            selected=[s for s in states if (role=="all" or s["role"]==role) and (subset=="all" or (s["original_role_sample"] if subset=="original_sample" else s["prefix_geometry_distinct"]>1))]
            groups[role+":"+subset]=summarize(selected)
    strata={}
    for axes in (('role','source_node'),('scene','role','source_node'),('role','candidate_family'),('role','actual_chosen_index')):
        partitions=defaultdict(list)
        for state in states:
            partitions['|'.join(str(state[k]) for k in axes)].append(state)
        strata['|'.join(axes)]={key:summarize(value) for key,value in sorted(partitions.items())}
        audit.check(sum(len(v) for v in partitions.values())==180,axes,'classification omits actual attempts')
    changed=[p for p,expected in audit.files.items() if file_hash(p)!=expected]
    audit.check(not changed,folder,"source/input/physical bytes changed during audit")
    result={"schema":"ics_v3_all_nominal_opportunity_independent_audit_v1","run":str(folder),
        "checks":audit.count,"failed_checks":len(audit.errors),"errors":audit.errors,"groups":groups,"strata":strata,"states":states,
        "request_count":len(rows),"attempts":len(states),"bound_files":len(audit.files),"all_bound_files_unchanged":not changed,
        "scope":"Pure file audit and conditional single-nominal one-step counterfactual differences; repeated decisions/one tape are correlated. Regret sums are local diagnostics, NOT achievable episode savings, independent samples or sampled-future means.",
        "baseline_identity":"actual_chosen_index is the original deployed Timed selector choice; index0 is separately reported as first of the normal earliest candidate pool. Neither identity is silently replaced by offline best.",
        "intervention_limit":"Each request changes one current candidate then restores the original causal continuation. Local oracle gaps cannot be added into deployable savings; flat local pools do not prove coordinated changes over multiple later decisions have no value.",
        "wall_seconds":perf_counter()-wall,"cpu_seconds":process_time()-cpu,"script_sha256":file_hash(__file__)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps({k:result[k] for k in ("checks","failed_checks","request_count","attempts","groups","wall_seconds")},ensure_ascii=False))
    return int(bool(audit.errors))


if __name__=="__main__":
    raise SystemExit(main())
