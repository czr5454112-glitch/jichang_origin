"""Offline, deliberately restricted necessary-bound certificate for factor001.

This is a graph/capacity argument under declared circulation contracts, not a
solver optimality claim. It uses future evaluation targets only OFFLINE and is
never an online proposal feature. Unsupported models return unknown.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from .validate_analytic_control import write


def reachable(edges, start, target):
    seen, frontier = {start}, [start]
    while frontier:
        node = frontier.pop()
        if node == target:
            return True
        for u, v, *_ in edges:
            if u == node and v not in seen:
                seen.add(v)
                frontier.append(v)
    return False


def certify(data, prefix_receipts, reference, *, boundary=.11, receiving_node=2, duration_threshold=400.):
    result = {"status": "unknown", "scope": "fixed circulation_factor_006_001 directed graph and finite trays; two baseline target intersection only",
              "online_use": False, "global_scheduling_optimality": "unknown", "checks": {},
              "contract_assumptions": ["one business bag per tray", "no unloading before that job's declared destination",
                  "no creation or teleportation of trays", "incoming reservation of capacity1 begins at edge entry and lasts at least until arrival",
                  "preserve the already loaded protected prefix jobs; no business cancellation"]}
    checks = result["checks"]
    nodes = {n["node"]: n for n in data["node_contracts"]}
    jobs = {j["business_bag_id"]: j for j in data["jobs"]}
    trays = {t["tray_id"] for t in data["trays"]}
    checks["capacity_one_shared_receiving"] = nodes[receiving_node]["capacity"] == 1
    checks["positive_fixed_edges"] = all(e[2] > 0 and e[3] > 0 for e in data["edge_records"])
    if not all(checks.values()):
        return result
    prefix = [r for r in prefix_receipts if r["time"] <= boundary]
    current = {}
    for event in prefix:
        if event["event"] == "LOAD_START":
            current[event["tray_id"]] = event["business_bag_id"]
        elif event["event"] == "UNLOAD_COMPLETE":
            current.pop(event["tray_id"], None)
    checks["every_fixed_tray_in_active_prefix_service"] = set(current) == trays
    checks["protected_direct_prefix_contracts"] = all(jobs[b]["protected_service"] and jobs[b].get("storage_node", -1) < 0 for b in current.values())
    checks["target_demand_not_already_served_at_boundary"] = not any(r["business_bag_id"] in ("D1", "UNSEEN") and r["event"] == "LOAD_START" for r in prefix)
    if not all(checks.values()):
        return result
    release_nodes = {tray: jobs[bag]["destination"] for tray, bag in current.items()}
    cut = [e for e in data["edge_records"] if e[1] == receiving_node and e[2] / e[3] >= duration_threshold]
    remainder = [e for e in data["edge_records"] if e not in cut]
    checks["cut_exists"] = bool(cut)
    checks["every_future_available_tray_needs_cut_to_D1_origin"] = all(not reachable(remainder, node, jobs["D1"]["origin"]) for node in release_nodes.values())
    checks["UNSEEN_loaded_service_needs_cut"] = not reachable(remainder, jobs["UNSEEN"]["origin"], jobs["UNSEEN"]["destination"])
    checks["direct_distinct_service_identities"] = jobs["UNSEEN"].get("storage_node", -1) < 0 and jobs["D1"].get("storage_node", -1) < 0 and jobs["UNSEEN"]["destination"] != jobs["D1"]["origin"]
    # Distinct bag IDs/endpoints alone do NOT require distinct crossings: the
    # tray could unload UNSEEN then reach D1 without recrossing. Exclude this
    # sequential reuse explicitly, over every cut-free directed path.
    checks["UNSEEN_release_cannot_supply_D1_without_second_cut"] = not reachable(
        remainder, jobs["UNSEEN"]["destination"], jobs["D1"]["origin"])
    checks["nonnegative_physical_origin"] = all(j["arrival"] >= 0 for j in data["jobs"])
    result.update({"active_prefix_bags": current, "mandatory_next_release_nodes": release_nodes,
                   "cut_edges": cut, "cut_free_reachability_scope": "all directed paths, not just current S4 or candidate shortest paths"})
    if not all(checks.values()):
        return result
    per = lambda policy: {j["business_bag_id"]: j for j in reference["policies"][policy]["metrics"]["per_job"]}
    ordinary, wait = per("ordinary_public_windows"), per("WAIT")
    checks["target_reference_tasks_completed"] = ordinary["D1"]["completed"] and wait["UNSEEN"]["completed"]
    if not all(checks.values()):
        return result
    targets = {"D1": ordinary["D1"]["completed_at"], "UNSEEN": wait["UNSEEN"]["completed_at"]}
    minimum = min(e[2] / e[3] for e in cut)
    bound, deadline = 2 * minimum, max(targets.values())
    result.update({"required_distinct_crossings": ["empty supply before D1 loading", "loaded UNSEEN service"],
                   "distinctness_reason": "after UNSEEN unloading its tray still needs another cut to D1 origin; if D1 is first, UNSEEN's loaded service separately needs its cut",
                   "minimum_exclusive_time_per_crossing": minimum, "minimum_total_exclusive_time": bound,
                   "paired_completion_targets": targets, "available_physical_time_until_both_targets": deadline,
                   "strict_positive_deficit": bound-deadline,
                   "status": "proved_target_intersection_impossible_under_declared_contract" if bound > deadline else "bound_inconclusive",
                   "not_claimed": ["general circulation infeasibility", "impossibility of improving a specified single baseline",
                       "permission to relax protection", "online access to future targets", "new algorithmic contribution"]})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    directory = args.campaign / "long_2000m_unknown_source_demand"
    data = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    reference = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    raw_path = directory / reference["policies"]["ordinary_public_windows"]["raw_file"]
    raw = json.load(gzip.open(raw_path, "rt", encoding="utf-8"))
    result = certify(data, raw["controller_run"]["result"]["receipts"], reference)
    result["source_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["input_sha256"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (directory / "input.json", directory / "summary.json", raw_path)}
    write(args.output, result)
    print(json.dumps({k: result.get(k) for k in ("status", "minimum_total_exclusive_time", "available_physical_time_until_both_targets", "strict_positive_deficit")}))


if __name__ == "__main__":
    main()
