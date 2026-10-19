"""Independent saved96 audit: standard library only, no model/native calls."""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path
import time

JOBS={"loaded","receiver","reuse1","reuse2","blocker"}
CASES=["mechanism","no_overlap","insufficient_advance"]
FIELDS=("initial_action","empty_departure","return_delay","later_action")


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def require(value,reason):
    if not value:raise ValueError("saved_live96:"+reason)
def key(action):return tuple(action[f] for f in FIELDS)
def score(vector):
    # The producer assigns completions in nondecreasing native-model event
    # time. JSON sorts job keys; recover that summation order, never round.
    return sum(sorted(vector.values()))
def deltas(a,b):return {job:a[job]-b[job] for job in sorted(JOBS)}
def protected(a,b):return all(a[job]<=b[job] for job in JOBS)
def decision_epoch(at):return max(((at+.01)+.01)+.02,(((at+.01)+.01)+.01)+.01)


def lifecycle(data,prediction,action):
    jobs={j["business_bag_id"]:j for j in data["jobs"]};nodes={n["node"]:n for n in data["node_contracts"]}
    service={n[0]:max(.001,n[2]) for n in data["node_records"]}
    travel={(a,b):max(.001,length/speed) for a,b,length,speed in data["edge_records"]}
    edges={(e["from"],e["to"]):e for e in data["edge_contracts"]}
    completions=prediction["completion"]
    require(set(completions)==JOBS and all(type(t) in (int,float) and math.isfinite(t) and 0<=t<=40 for t in completions.values()),"five_finite_completions")
    require(prediction["completion_sum"]==score(completions),"chronological_completion_sum")
    require(prediction["status"]=="conditional_prediction" and 0<prediction["event_count"]<=20000,"completion_and_event_budget")
    require(all(prediction.get(f) is False for f in ("native_execution_certified","native_protection_certified","online_information_delivered","complete_request_100ms_certified")),"authority_flags")
    receipts=prediction["physical_projection"]
    require(all(a["at"]<=b["at"] for a,b in zip(receipts,receipts[1:])),"receipt_chronology")
    location={t["tray_id"]:t["node"] for t in data["trays"]};inflight={};routes={j:[] for j in JOBS};last_exit={};empty=[];storage={};loads={}
    matched_entries={}
    for r in receipts:
        tray=r["tray"];require(tray in location,"tray_identity")
        if r["event"]=="EDGE_ENTER":
            edge=r["source"],r["target"]
            require(tray not in inflight and location[tray]==edge[0] and edge in edges and edges[edge]["capacity"]>0,"edge_identity_and_positive_capacity")
            require(r["job"] is None or r["job"] in JOBS,"edge_job_identity")
            inflight[tray]=r;matched_entries[tray,r["at"],*edge]=r
            if r["job"] is None:
                require(r["at"]<=39 and edge in ((5,1),(6,7)),"empty_departure_expiry_or_path");empty.append(r)
            else:routes[r["job"]].append(r)
        elif r["event"]=="EDGE_EXIT":
            entry=inflight.pop(tray)
            require((r["source"],r["target"])==(entry["source"],entry["target"]),"paired_edge_exit")
            require(r["at"]==entry["at"]+travel[entry["source"],entry["target"]],"exact_travel_addition")
            location[tray]=r["target"]
            if entry["job"] is not None:last_exit[entry["job"]]=r
        elif r["event"]=="STORAGE_ENTER":
            job="blocker" if tray=="P" else "loaded" if tray=="L" else None
            require(job and job not in storage and location[tray]==jobs[job]["storage_node"],"mandatory_storage_identity")
            require(r["at"]==last_exit[job]["at"]+service[location[tray]],"storage_entry_service_epoch");storage[job]=r
        elif r["event"]=="LOAD_START":
            require(r["job"] not in loads and location[tray]==jobs[r["job"]]["origin"],"unique_load_at_origin");loads[r["job"]]=r
    require(not inflight and set(storage)=={"loaded","blocker"} and set(loads)=={"receiver","reuse1","reuse2"},"all_lifecycles_present")
    for job,path in routes.items():
        require(path and path[0]["source"]==jobs[job]["origin"] and path[-1]["target"]==jobs[job]["destination"],"full_job_path")
        require(all(a["target"]==b["source"] for a,b in zip(path,path[1:])),"path_continuity")
        require(completions[job]==(last_exit[job]["at"]+service[jobs[job]["destination"]])+jobs[job]["unload_seconds"],"exact_terminal_service_and_unload")
        start=.1 if job=="loaded" else jobs[job]["load_seconds"] if job=="blocker" else loads[job]["at"]+jobs[job]["load_seconds"]
        require(path[0]["at"]>=start+service[jobs[job]["origin"]],"loaded_departure_after_actual_load")
        if job in storage:
            out=next(r for r in path if r["source"]==jobs[job]["storage_node"])
            ready=max(storage[job]["at"]+jobs[job]["storage_min_dwell"],jobs[job]["storage_release_at"])
            require(out["at"]>=ready+service[out["source"]],"storage_release_and_new_source_service")
    require([r["job"] for r in receipts if r["event"]=="LOAD_START" and r["tray"]=="L"]==["reuse1","reuse2"],"reuse_FIFO")
    commands=prediction["projected_commands"]
    for command in commands:
        require(command["status"]=="updated" and command["reason"]=="allowed","route_rejection_not_success")
        require(command["executed_at"]==command["issued_at"]+.01 and command["ack_delivered_at"]==command["executed_at"]+.02,"route_wire_ACK_arithmetic")
        require(command["executed_at"]<=command["expiry"] and command["ack_delivered_at"]<=40,"route_expiry")
        first=next(r for r in routes[command["job"]] if r["source"]==command["from"])
        require(first["target"]==command["next"] and first["at"]>=command["executed_at"],"updated_preference_and_executed_edge")
        prefix=sum(r["event"]=="EDGE_ENTER" and r["tray"]==command["tray"] and r["at"]<=command["issued_at"] for r in receipts)
        require(prefix==command["prefix"],"current_committed_prefix")
    for field,job,target in (("initial_action","loaded",2),("later_action","reuse1",8)):
        rows=[c for c in commands if c["job"]==job]
        require(len(rows)==(action[field]!="native_default"),"selected_route_command_count")
        if rows:require(rows[0]["next"]==target,"selected_route_target")
    require(len([c for c in commands if c["job"]=="reuse2" and c["next"]==3])==1,"common_second_reuse")
    transfers=prediction["projected_transfers"]
    guards=prediction["conditional_operation_guards"]
    transfer_guards=[g for g in guards if g["kind"]=="transfer"]
    require(len(transfers)==len(transfer_guards),"full_transfer_guard_coverage")
    for g in guards:require(g["conditional_local_state_only"] is True and g["source_owner"]==nodes[g["source"]]["resource_owner"],"source_owner_guard")
    for r,g in zip(transfers,transfer_guards,strict=True):
        require((r["tray"],r["destination"],r["earliest"])==(g["tray"],g["destination"],g["earliest"]),"immutable_transfer_binding")
        require(r["terminal"] is True and r["ack"]==r["physical_status"] and r["ack"] in ("received","rejected") and r["ack_at"]<=40,"terminal_transfer_ACK")
        require(nodes[g["source"]]["allow_export"] and nodes[g["destination"]]["allow_receive"] and nodes[g["source"]]["export_min_stock"]==0,"static_transfer_permissions")
        require(nodes[g["source"]]["resource_owner"]!=nodes[g["destination"]]["resource_owner"],"actual_modeled_cross_owner_resource")
    successful=[g for r,g in zip(transfers,transfer_guards,strict=True) if r["ack"]=="received"]
    require(len(successful)==3 and len(empty)==3,"one_supply_two_returns")
    returns=[g for g in transfer_guards if g["tray"]=="L"]
    require(len(returns)==2 and returns[0]["at"]==decision_epoch(completions["loaded"]+jobs["loaded"]["hold_seconds"]),"release_to_first_return_message_chain")
    require(returns[0]["earliest"]==(returns[0]["at"] if action["return_delay"]==0. else max(7.84,returns[0]["at"])) and returns[1]["at"]==completions["reuse1"]+jobs["reuse1"]["hold_seconds"],"shared_return_policy")
    require([r["at"] for r in receipts if r["event"]=="EMPTY_RECEIVED" and r["tray"]=="L"]==[loads[j]["at"] for j in ("reuse1","reuse2")],"same_carrier_receive_to_load")
    later=[c for c in commands if c["job"]=="reuse1"]
    if later:require(later[0]["issued_at"]==decision_epoch(loads["reuse1"]["at"]+jobs["reuse1"]["load_seconds"]),"later_message_delay_from_local_load")

    # Independent OR receiving-occupancy reconstruction. At an equal timestamp
    # exits precede grants; direct source commits precede merge phase9. Within
    # each commit phase, preserve the producer's chronological phase sequence.
    state={t["tray_id"]:{"node":t["node"],"edge":None,"lease":None} for t in data["trays"]}
    agenda=[];indegree=Counter(b for a,b in edges)
    for i,r in enumerate(receipts):
        if r["event"]=="EDGE_EXIT":agenda.append((r["at"],2,i,"exit",r))
        elif r["event"]=="EMPTY_RECEIVED":agenda.append((r["at"],8,i,"received",r))
    for i,(r,g) in enumerate(zip(transfers,transfer_guards,strict=True)):
        agenda.append((max(g["at"]+.01,g["earliest"]),6,i,"grant",(r,g)))
    commits=[r for r in prediction["projected_native_phases"] if r["phase"]=="destination_merge_commit"]
    require(len(commits)==len(matched_entries),"all_commits_have_observed_entry")
    for i,r in enumerate(commits):
        entry=matched_entries[r["tray"],r["at"],r["from"],r["target"]];job=entry["job"]
        goal=(1 if r["tray"]=="E" else 7) if job is None else (jobs[job]["storage_node"] if job in storage and r["at"]<storage[job]["at"] else jobs[job]["destination"])
        rank=8 if r["target"]==goal or indegree[r["target"]]<=1 else 9
        agenda.append((r["at"],rank,10000+i,"commit",r))
    next_entry={e:-math.inf for e in edges};max_occupancy={n:0 for n in nodes};reservations=[]
    def occupants(node,exclude=None):
        return [k for k,s in state.items() if k!=exclude and ((s["edge"] is None and s["node"]==node) or (s["edge"] and s["edge"][1]==node) or s["lease"]==node)]
    for at,rank,index,kind,payload in sorted(agenda,key=lambda r:r[:3]):
        if kind=="exit":
            r=payload;s=state[r["tray"]];require(s["edge"]==(r["source"],r["target"]),"reconstructed_exit_identity");s["node"]=r["target"];s["edge"]=None
        elif kind=="received":state[payload["tray"]]["lease"]=None
        elif kind=="grant":
            request,g=payload;occupancy=len(occupants(g["destination"],g["tray"]))
            require((occupancy>=nodes[g["destination"]]["capacity"])==(request["ack"]=="rejected"),"grant_or_rejection_against_actual_modeled_occupancy")
            if request["ack"]=="received":state[g["tray"]]["lease"]=g["destination"]
        else:
            r=payload;s=state[r["tray"]];edge=r["from"],r["target"]
            require(s["node"]==r["from"] and s["edge"] is None,"reconstructed_commit_source")
            require(len(occupants(r["target"],r["tray"]))<nodes[r["target"]]["capacity"],"receiving_capacity_at_irreversible_reservation")
            require(sum(t["edge"]==edge for t in state.values())<edges[edge]["capacity"] and at+1e-9>=next_entry[edge],"edge_capacity_and_native_headway")
            s["edge"]=edge;next_entry[edge]=at+edges[edge]["entry_headway"]
            reservations.append({"at":at,"tray":r["tray"],"from":r["from"],"target":r["target"],"target_occupants":occupants(r["target"])})
        for node,n in nodes.items():
            occupancy=len(occupants(node));require(occupancy<=n["capacity"],"OR_occupancy_capacity");max_occupancy[node]=max(max_occupancy[node],occupancy)
    return {"completion":completions,"routes":routes,"storage":storage,"loads":loads,"returns":returns,
        "resource_reservations":reservations,"max_occupancy":max_occupancy,"route_commands":len(commands),
        "transfer_attempts":len(transfers),"point_protection_only":True}


def search(group,incumbent,method):
    by={key(r["action"]):r for r in group.values()};base=by[key(incumbent)];query=[];seen=set();frontier=[key(incumbent)];expanded=set()
    def ask(k):
        if k not in seen:seen.add(k);query.append(list(k))
        return by[k]
    def objective(k):return score(by[k]["completion"]),k
    ask(key(incumbent))
    if method=="finite_MPC_reference":
        for k in sorted(by):ask(k)
    else:
        while frontier:
            current=min(frontier,key=objective);frontier.remove(current)
            if current in expanded:continue
            expanded.add(current);moves=[]
            for k in sorted(by):
                distance=sum(a!=b for a,b in zip(k,current,strict=True))
                if not 1<=distance<=(2 if method=="pair_repair" else 1):continue
                row=ask(k)
                if not protected(row["completion"],base["completion"]):continue
                improves=objective(k)[0]<objective(current)[0] if method=="coordinate_strict" else objective(k)[0]<=objective(current)[0]
                if improves and k not in expanded:moves.append(k)
            if method=="coordinate_strict":frontier=[min(moves,key=objective)] if moves else []
            else:frontier.extend(k for k in moves if k not in frontier)
    candidates=[k for k in seen if protected(by[k]["completion"],base["completion"])]
    best=min(candidates,key=objective)
    return {"selected_action":by[best]["action"],"selected_sum":objective(best)[0],"query_order":query,"evaluations":len(query)}


def audit(folder,output):
    started=time.perf_counter();folder=Path(folder).resolve();output=Path(output).resolve()
    require(not output.exists(),"immutable_audit_output")
    own_before=sha(__file__);receipt=read(folder/"receipt.json");plan=read(folder/"preregistered_protocol.json")
    bindings={str(folder/name):sha(folder/name) for name in ("receipt.json","preregistered_protocol.json","branch_ledger.json","comparisons.json","external_process.json","external_application_wall.json","prepare_receipt.json")}
    require(sha(folder/"preregistered_protocol.json")==receipt["plan_sha256"]==read(folder/"prepare_receipt.json")["plan_sha256"],"plan_hash")
    require(sha(folder/"branch_ledger.json")==receipt["ledger_sha256"] and sha(folder/"comparisons.json")==receipt["comparisons_sha256"],"final_artifact_hashes")
    require(receipt["executed"]==receipt["candidate_denominator"]==96 and receipt["source_changed"]==[] and receipt["native_calls"]==0,"terminal_count_scope")
    for path,row in plan["sources"].items():require(sha(path)==sha(folder/row["archive"])==row["sha256"],"live_and_archived_sources")
    for row in plan["references"].values():require(sha(row["path"])==row["sha256"],"reference_hash")
    external=read(folder/"external_process.json");app=read(folder/"external_application_wall.json")
    require(external["status"]=="exited" and external["exitcode"]==0 and external["hard_timeout_seconds"]==120. and external["windows_job_kill_on_close"] is True,"owned_job_exit")
    require(app["exit_code"]==0 and app["native_executions"]==0 and app["plan_sha256"]==receipt["plan_sha256"],"whole_application_exit")
    wrapper=folder.parent/"user_resume_20261015_001/invoke_live_obligation_003_measured.ps1"
    require(sha(wrapper)==app["wrapper_sha256"],"external_wrapper_source")
    require(plan["case_order"]==CASES and plan["incumbent"]["return_delay"]==0.,"strong_incumbent_and_case_order")
    ledger=read(folder/"branch_ledger.json");comparisons=read(folder/"comparisons.json")
    expected=[c+f"/vector_{i:02d}" for c in CASES for i in range(32)]
    require(ledger["executed"]==96 and ledger["execution_order"]==expected and set(ledger["rows"])==set(expected),"actual_full96_order")
    audits={};rawbindings={}
    for index,name in enumerate(expected):
        row=ledger["rows"][name];declared=plan["rows"][name];require(row["execution_index"]==index and all(row[f]==declared[f] for f in ("case","action")),"row_identity")
        path=Path(row["raw"]);require(path==folder/"raw"/f"{index:03d}.json.gz" and sha(path)==row["raw_sha256"],"raw_order_and_hash")
        rawbindings[str(path)]=sha(path);raw=json.loads(gzip.decompress(path.read_bytes()))
        require((raw["key"],raw["case"],raw["action"])==(name,row["case"],row["action"]),"raw_selected_action_identity")
        item=plan["cases"][row["case"]];require(sha(folder/item["input"])==item["input_sha256"] and sha(folder/item["snapshot"])==item["snapshot_sha256"],"input_snapshot_hash")
        require((folder/item["input"]).read_bytes()==Path(item["source_input_path"]).read_bytes(),"unchanged_fixed_parameters")
        checked=lifecycle(read(folder/item["input"]),raw["prediction"],row["action"])
        require(raw["assessment"]==row["assessment"] and row["assessment"]["status"]=="assessed_conditional_model" and checked["completion"]==row["assessment"]["completion"],"recomputed_full_lifecycle_against_claim")
        audits[name]={"action":row["action"],**checked}
    summaries={}
    for case in CASES:
        group={name:r for name,r in audits.items() if name.startswith(case+"/")};base=next(r for r in group.values() if r["action"]==plan["incumbent"])
        methods={}
        for method,claimed in comparisons["cases"][case]["methods"].items():
            actual=search(group,plan["incumbent"],method)
            require(all(actual[k]==claimed[k] for k in actual),"independent_search_sequence")
            methods[method]=actual
        families={}
        for family,field in (("fixed_initial_native_default","initial_action"),("later_native_default","later_action")):
            members={name:r for name,r in group.items() if r["action"][field]=="native_default"}
            require(len(members)==16,"complete_reference_family")
            eligible=[n for n,r in members.items() if protected(r["completion"],base["completion"])]
            best=min(eligible,key=lambda n:(score(members[n]["completion"]),n));claim=comparisons["cases"][case]["references"][family]
            require(set(claim["members"])==set(members) and claim["member_count"]==16 and claim["best_key"]==best and claim["status"]=="complete_conditional_reference","independent_family_optimum")
            families[family]={"member_count":16,"best_key":best,"best_completion":members[best]["completion"],"best_sum":score(members[best]["completion"])}
        for name,row in group.items():
            claim=comparisons["cases"][case]["strict_point_comparisons"][name]
            require(claim["protected"]==protected(row["completion"],base["completion"]) and claim["deltas"]==deltas(row["completion"],base["completion"]),"strict_zero_tolerance_comparison")
        summaries[case]={"baseline_completion":base["completion"],"protected_count":sum(protected(r["completion"],base["completion"]) for r in group.values()),"methods":methods,"families":families}
    require(all(sha(p)==digest for p,digest in bindings.items()) and all(sha(p)==digest for p,digest in rawbindings.items()),"post_read_artifact_stability")
    require(sha(__file__)==own_before,"audit_source_drift")
    report={"schema":"g31.live_obligation_saved96_independent_review.v1","status":"passed_saved96_conditional_model_checks",
        "artifact_bindings":bindings,"raw_bindings":rawbindings,"source_count":len(plan["sources"]),"row_count":96,"case_order":CASES,
        "all96_five_jobs_complete":True,"all6_full_reference_families":True,"all4_method_query_sequences_recomputed":True,
        "independent_lifecycle_scope":["matched full job paths, exact travel/service/unload and mandatory Storage","sameL receives and FIFO two-reuse loads","every selected route updated plus target edge, source prefix/owner/wire/ACK/expiry","all transfer source/receiver contracts and terminal ACK states","reservation-publication receiving OR occupancy, edge capacity/headway and grant/rejection reconstruction"],
        "summaries":summaries,"rows":audits,"whole_application_seconds":app["whole_python_application_seconds"],
        "audit_wall_seconds":time.perf_counter()-started,"audit_source":{"path":str(Path(__file__).resolve()),"sha256":own_before},
        "new_model_evaluations":0,"native_executions":0,"all_information_hypothetical":True,
        "limits":["This audits saved model consistency, not independent native replay or a model-error bound.","Future planning readiness and complete source-owned observations were hypothetical, not native-delivered.","Timing is full96 application wall, not a100ms accepted-business-request result.","Finite pair repair/MPC can explain this result; no solver novelty or original-airport benefit."]}
    output.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    return {"output":str(output),"sha256":sha(output),"status":report["status"],"row_count":96,"audit_wall_seconds":report["audit_wall_seconds"]}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--folder",required=True);parser.add_argument("--output",required=True)
    args=parser.parse_args();print(json.dumps(audit(args.folder,args.output)))
