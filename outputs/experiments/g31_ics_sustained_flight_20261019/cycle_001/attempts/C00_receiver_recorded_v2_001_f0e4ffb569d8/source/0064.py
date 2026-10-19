"""Predeclared feasible-OD witnesses on the unchanged 151-node original graph.

This is a separately labelled mechanism subset, never the full-flow benchmark.
Selection sees only source records and static contracts, never simulation wins.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import gzip
import json
from pathlib import Path
import time

from .analytic_control import run_online_matching
from .finite_reference import outcome_cost, service_dominates
from .native_host import audit_result, load_native
from .original_workload import ProxyContract, build_input, digest, json_digest, write_json
from .validate_analytic_control import replay_input


def select_input(count: int, *, horizon: float = 86400.) -> tuple[dict, dict, list[dict]]:
    if type(count) is not int or count < 2:
        raise ValueError("mechanism witness requires at least two complete source jobs")
    source, manifest, crosswalk = build_input(scale=1,
        contract=ProxyContract("nanning-on-carrier-proxy-v1-n4-s4-t2",4,4,2,1.,1.,0.,
                               "finite_berth_waiting_research_proxy"),
        horizon=horizon, max_events=100000, trace_limit=0)
    zones = {n["node"]: n["zone"] for n in source["node_contracts"]}
    adjacency = defaultdict(list)
    for edge in source["edge_contracts"]:
        if edge["capacity"] > 0:
            adjacency[edge["from"]].append(edge["to"])
    reachable = {}
    for node in zones:
        reached, pending = {node}, [node]
        while pending:
            for nxt in adjacency[pending.pop()]:
                if nxt not in reached:
                    reached.add(nxt); pending.append(nxt)
        reachable[node] = reached
    eligible, reasons = [], {}
    for job in source["jobs"]:
        origin, destination, storage = job["origin"], job["destination"], job["storage_node"]
        if zones[origin] == zones[destination]:
            reason = "same_zone_endpoints_internal_module_needed"
        elif origin not in reachable[destination]:
            reason = "no_positive_capacity_return"
        elif storage < 0 and destination not in reachable[origin]:
            reason = "no_positive_capacity_direct_service"
        elif storage >= 0 and (storage not in reachable[origin] or destination not in reachable[storage]):
            reason = "no_positive_capacity_storage_stage"
        else:
            reason = "eligible_static_round_trip"
            eligible.append(job)
        reasons[job["business_bag_id"]] = reason
    eligible.sort(key=lambda j:(j["arrival"], j["business_bag_id"]))
    by_origin = Counter(j["origin"] for j in eligible)
    # Earliest eligible bag whose loader has enough same-rule source records.
    first = next(j for j in eligible if by_origin[j["origin"]] >= count)
    selected = [j for j in eligible if j["origin"] == first["origin"]][:count]
    selected_ids = {j["business_bag_id"] for j in selected}
    data = copy.deepcopy(source)
    data["jobs"] = copy.deepcopy(selected)
    data["trays"] = [next(copy.deepcopy(t) for t in source["trays"] if t["node"] == first["origin"])]
    data["model_scope"] = "original full directed graph; predeclared same-source static-feasible OD mechanism subset; one of existing trays retained as a separate finite-fleet factor"
    lineage = [{**row, "eligibility": reasons[row["business_bag_id"]],
                "selected_for_witness": row["business_bag_id"] in selected_ids} for row in crosswalk]
    selection = {"schema": "g31.original_mechanism_selection.v1", "mother_manifest": manifest,
        "mother_offered": len(source["jobs"]), "witness_offered": count,
        "selected_origin": first["origin"], "selected_business_ids": [j["business_bag_id"] for j in selected],
        "eligibility_counts": dict(Counter(reasons.values())), "selected_without_simulation_results": True,
        "selection_rule": "positive-capacity complete original stage path and return to original loader; cross-zone endpoints; chronological first eligible loader with enough bags; first N complete bags at that loader",
        "changed_business_fields": [], "graph_nodes": len(data["node_records"]), "graph_edges": len(data["edge_records"]),
        "capacity_direction_port_contracts_changed": False,
        "fleet_factor": {"mother_trays": len(source["trays"]), "witness_trays": 1,
                         "retained_original_tray": data["trays"][0]["tray_id"]},
        "input_sha256": json_digest(data), "claim_boundary": "mechanism witness only; does not replace the blocked full 1x/2x group or certify physical optimality"}
    return data, selection, lineage


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--horizon", type=float, default=86400.)
    parser.add_argument("--control-period", type=float, default=60.)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compact-projection", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    data, selection, lineage = select_input(args.count, horizon=args.horizon)
    write_json(args.output/"selection.json", selection)
    write_json(args.output/"input.json", data)
    with gzip.open(args.output/"mother_crosswalk_selection.jsonl.gz", "wt", encoding="utf-8") as stream:
        for row in lineage:
            stream.write(json.dumps(row)+"\n")
    paths = [Path(__file__),Path(__file__).with_name("analytic_control.py"),Path(__file__).with_name("original_workload.py")]
    receipt = {"status":"running", "source_before":{str(p):digest(p) for p in paths},
        "binary_sha256":digest(args.binary), "cases":{}, "control_period":args.control_period,
        "compact_projection": args.compact_projection,
        "claim":"original-graph same-source mechanism witness, not full-flow evidence or main-method innovation"}
    write_json(args.output/"receipt.json",receipt)
    native = load_native(args.binary)
    owners = sorted({n["resource_owner"] for n in data["node_contracts"]})
    outcomes = {}
    for predictive in (False,True):
        policy = "predictive" if predictive else "reactive"
        started = time.perf_counter()
        run = run_online_matching(native.NativeSession(data),owners,horizon=args.horizon,
            predictive=predictive,control_period=args.control_period,message_delay=2.,demand_delay=.5,
            compact_projection=args.compact_projection)
        audit = audit_result(replay_input(data,run["submitted"]),run["result"])
        outcome = outcome_cost(run["result"],data["jobs"],args.horizon)
        with gzip.open(args.output/f"{policy}_raw.json.gz","wt",encoding="utf-8") as stream:
            json.dump(run,stream)
        write_json(args.output/f"{policy}_audit.json",audit)
        write_json(args.output/f"{policy}_metrics.json",outcome)
        completed_by_tray = defaultdict(list)
        for event in run["result"]["receipts"]:
            if event["event"] == "UNLOAD_COMPLETE":
                completed_by_tray[event["tray_id"]].append(event["business_bag_id"])
        receipt["cases"][policy] = {"status":run["status"], "wall_seconds":time.perf_counter()-started,
            "completed":outcome["completed"],"offered":len(data["jobs"]),
            "same_tray_completed_business_ids":dict(completed_by_tray),
            "submitted_requests":len(run["submitted"]),
            "transfer_status_counts":dict(Counter(t["status"] for t in run["result"]["transfers"])),
            "complete_100ms_requirement_certified":False}
        outcomes[policy]=outcome
        write_json(args.output/"receipt.json",receipt)
    receipt["paired_service_preserved"] = service_dominates(outcomes["predictive"],outcomes["reactive"])
    receipt["cost_predictive_minus_reactive"] = outcomes["predictive"]["cost"]-outcomes["reactive"]["cost"]
    receipt["source_changed"] = [str(p) for p in paths if digest(p)!=receipt["source_before"][str(p)]]
    receipt["status"] = "executed" if not receipt["source_changed"] else "source_changed"
    write_json(args.output/"receipt.json",receipt)
    print(json.dumps(receipt,indent=2))
    return int(bool(receipt["source_changed"]))


if __name__ == "__main__":
    raise SystemExit(main())
