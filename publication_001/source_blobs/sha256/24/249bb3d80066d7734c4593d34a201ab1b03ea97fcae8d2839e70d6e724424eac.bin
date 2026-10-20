"""Sufficient dead-end certificate for one fixed native on-carrier/FIFO state.

Uses actual offline queues plus independent positive-capacity graph search.
Does not authorize state repair or claim an airport/global-optimum theorem.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path

from .original_workload import ProxyContract, build_input, digest, write_json


def certify(data: dict, snapshot: dict) -> dict:
    nodes = {n["node"]: n for n in data["node_contracts"]}
    adjacency = defaultdict(list)
    for edge in data["edge_contracts"]:
        if edge["capacity"] > 0:
            adjacency[edge["from"]].append(edge["to"])
    legs = {x["runtime_id"]:x for x in snapshot["legs"]}
    junctions = {x["node"]:x for x in snapshot["junctions"]}
    waits = {x["runtime_id"]:x for x in snapshot["resource_waits"]}
    trays = snapshot["trays"]
    # The witnessed source model has a single on-carrier Storage, not a
    # fabricated generic exception bay or an off-carrier bag warehouse.
    storage_nodes = {j["storage_node"] for j in data["jobs"] if j["storage_node"] >= 0}
    conditions = {"single_declared_storage":len(storage_nodes)==1,
                  "no_physical_fault_tape":not data["faults"],
                  "no_transfer_tape":not data["transfers"],
                  "all_trays_loaded_and_stationary":all(t["mode"]=="loaded" and t["edge_to"]<0 for t in trays),
                  "no_receiving_leases":all(t["reception_node"]<0 for t in trays)}
    witness = {}
    if len(storage_nodes)==1:
        storage = next(iter(storage_nodes))
        queue = junctions.get(storage,{}).get("queue",[])
        parked = [t for t in trays if t["node"]==storage and t["edge_to"]<0]
        conditions["storage_full"] = len(parked)==nodes[storage]["capacity"]
        conditions["storage_fifo_queue_covers_all_occupants"] = sorted(queue)==sorted(t["active_leg"] for t in parked)
        conditions["storage_fifo_head_exists"] = bool(queue)
        if queue:
            head = legs[queue[0]]
            job = data["jobs"][head["job_index"]]
            goal = job["destination"]
            reached, pending = {storage}, [storage]
            while pending:
                for nxt in adjacency[pending.pop()]:
                    if nxt not in reached:
                        reached.add(nxt);pending.append(nxt)
            conditions["head_is_storage_out"] = head["kind"]=="storage_out"
            conditions["head_goal_unreachable_independently"] = goal not in reached
            conditions["native_head_static_wait_matches"] = waits.get(head["runtime_id"],{}).get("static_blocked") is True
            outside = [t for t in trays if t["node"]!=storage]
            conditions["other_trays_all_need_same_storage_before_service"] = all(
                t["active_leg"] in legs and legs[t["active_leg"]]["kind"]=="storage_in" and
                data["jobs"][legs[t["active_leg"]]["job_index"]]["storage_node"]==storage for t in outside)
            dependency = {w["node"]:set(w["receiving_nodes"]) for w in snapshot["resource_waits"]}
            def reaches_storage(node):
                seen,pending=set(),[node]
                while pending:
                    cur=pending.pop()
                    if cur==storage:return True
                    if cur in seen:continue
                    seen.add(cur);pending.extend(dependency.get(cur,()))
                return False
            conditions["actual_receiving_wait_chain_ends_at_storage"] = all(reaches_storage(t["node"]) for t in outside)
            witness = {"storage":storage,"storage_capacity":nodes[storage]["capacity"],
                "storage_fifo_runtime_ids":queue,"head_business_bag_id":job["business_bag_id"],
                "head_runtime_id":head["runtime_id"],"head_stage_goal":goal,
                "independent_reachable_nodes":sorted(reached),
                "other_loaded_trays":len(outside),"actual_receiving_dependencies":{str(k):sorted(v) for k,v in dependency.items()}}
    proved = all(conditions.values())
    return {"schema":"g31.fixed_contract_blocking_certificate.v1",
        "status":"proved_under_listed_fixed_contract" if proved else "unknown",
        "conditions":conditions,"witness":witness,
        "claim":"No currently loaded bag can finish and no actual empty tray can be produced without changing at least one listed contract condition.",
        "required_contract_assumptions":["native FIFO cannot bypass its head",
            "on-carrier Storage occupancy persists through transport-stage release",
            "raw zero capacity interpreted as permanently closed in this research group",
            "fixed capacities, directions and accepted business stage goals",
            "no unauthorized offload, job cancellation, loaded-tray export or tray creation"],
        "reasoning":"The unreachable FIFO head cannot depart. Every Storage occupant is in that same FIFO, so all Storage berths remain occupied. All other loaded trays must enter that Storage before service and their executed receiving waits lead to it. With no empty, in-flight or recovering tray, future source arrivals cannot create a serviceable carrier.",
        "conditional_on_current_state_and_model":True,
        "airport_physical_infeasibility_claim":False,"global_optimality":"unknown"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    args=parser.parse_args()
    manifest=json.loads((args.folder/"input_manifest.json").read_text(encoding="utf-8"))
    for path, expected in manifest["source_sha256"].items():
        if digest(Path(path))!=expected:raise ValueError("source changed since execution")
    data,new_manifest,_=build_input(scale=manifest["scale"],contract=ProxyContract(**manifest["proxy_contract"]))
    if new_manifest["input_sha256"]!=manifest["input_sha256"]:raise ValueError("input hash differs")
    snapshot=json.loads((args.folder/"native_offline_diagnostics.json").read_text(encoding="utf-8"))
    result=certify(data,snapshot)
    write_json(args.folder/"fixed_contract_blocking_certificate.json",result)
    print(json.dumps(result,indent=2))


if __name__=="__main__":main()
