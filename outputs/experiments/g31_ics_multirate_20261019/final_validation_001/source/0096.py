"""Reconstruct final physical blocking from executed receipts, without inventing queues.

The last RESOURCE_WAIT identifies an actually attempted native head. Candidate
capacity checks below are derived offline; exact pending indexes and complete
native FIFO queue order are deliberately not claimed by this reconstruction.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path

from .original_workload import ProxyContract, build_input, write_json


def diagnose(folder: Path) -> dict:
    manifest = json.loads((folder/"input_manifest.json").read_text(encoding="utf-8"))
    # Reconstruct the frozen source contract, never changing its capacities.
    proxy = manifest.get("physical_proxy_contract", manifest.get("proxy_contract"))
    if proxy is None:
        raise ValueError("no source proxy contract in manifest")
    contract = ProxyContract(**proxy)
    scale = manifest["scale"]
    data, _, _ = build_input(scale=scale, contract=contract)
    events = [json.loads(row) for row in gzip.open(folder/"physical_events.jsonl.gz", "rt", encoding="utf-8")]
    summary = json.loads((folder/"summary.json").read_text(encoding="utf-8"))
    if summary["trays_with_receiving_lease"] or any(e["event"] == "EXPORT_GRANTED" for e in events):
        raise ValueError("this no-transfer reconstruction does not model reception lease deduplication")
    jobs = {j["business_bag_id"]: j for j in data["jobs"]}
    trays = {t["tray_id"]: dict(t, mode="empty", job_id="", stage="", edge_to=-1) for t in data["trays"]}
    last_physical, last_wait, storage_releases = {}, {}, []
    lifecycle = {"LOAD_COMPLETE", "EDGE_ENTER", "EDGE_EXIT", "STORAGE_ENTER", "STORAGE_RELEASE",
                 "UNLOAD_START", "UNLOAD_COMPLETE", "HOLD_COMPLETE", "LEG_FAILED"}
    for event in events:
        tid, kind = event["tray_id"], event["event"]
        if kind == "RESOURCE_WAIT":
            last_wait[event["node"]] = event
        if not tid or kind not in lifecycle:
            continue
        tray = trays[tid]
        last_physical[tid] = event
        if kind == "LOAD_COMPLETE":
            tray.update(node=event["node"], mode="loaded", job_id=event["business_bag_id"], stage="loaded")
        elif kind == "EDGE_ENTER":
            tray["edge_to"] = event["to"]
        elif kind == "EDGE_EXIT":
            tray.update(node=event["node"], edge_to=-1)
        elif kind == "STORAGE_ENTER":
            tray["mode"] = "storage"
        elif kind == "STORAGE_RELEASE":
            tray.update(mode="loaded", stage="storage_out")
            storage_releases.append(event)
        elif kind == "UNLOAD_START":
            tray["mode"] = "unloading"
        elif kind == "UNLOAD_COMPLETE":
            tray["mode"] = "hold"
        elif kind == "HOLD_COMPLETE":
            tray.update(mode="empty", job_id="")
        elif kind == "LEG_FAILED":
            tray["mode"] = "quarantined"
    nodes = {n["node"]: n for n in data["node_contracts"]}
    occupancy = Counter(t["edge_to"] if t["edge_to"] >= 0 else t["node"] for t in trays.values())
    adjacency = defaultdict(list)
    for edge in data["edge_contracts"]:
        if edge["capacity"] > 0:
            adjacency[edge["from"]].append(edge["to"])
    reachable = {}
    for node in nodes:
        seen, pending = {node}, [node]
        while pending:
            for nxt in adjacency[pending.pop()]:
                if nxt not in seen:
                    seen.add(nxt); pending.append(nxt)
        reachable[node] = seen
    rows, dependency_edges = [], []
    for node, event in sorted(last_wait.items()):
        tray = trays[event["tray_id"]]
        # Only report a wait whose actual physical tray has not moved away.
        if tray["node"] != node or tray["edge_to"] >= 0 or tray["mode"] != "loaded":
            continue
        job = jobs[tray["job_id"]]
        goal = job["destination"] if tray["stage"] == "storage_out" or job["storage_node"] < 0 else job["storage_node"]
        candidates = []
        for edge in data["edge_contracts"]:
            if edge["from"] != node:
                continue
            target = edge["to"]
            if edge["capacity"] == 0:
                reason = "closed_edge"
            elif goal not in reachable[target]:
                reason = "no_static_legal_suffix"
            elif occupancy[target] >= nodes[target]["capacity"]:
                reason = "receiving_full"
                dependency_edges.append((node, target))
            else:
                reason = "physically_available_in_final_snapshot_not_proof_policy_selects_it"
            candidates.append({"next": target, "reason": reason,
                "occupancy": occupancy[target], "capacity": nodes[target]["capacity"],
                "occupant_trays": [t["tray_id"] for t in trays.values()
                    if (t["edge_to"] if t["edge_to"] >= 0 else t["node"]) == target]})
        rows.append({"node": node, "last_actual_wait_event": event, "stage_goal": goal,
            "offline_candidate_capacity_checks": candidates,
            "co_located_loaded_trays": [t["tray_id"] for t in trays.values() if t["node"] == node and t["mode"] == "loaded"]})
    result = {"schema": "g31.original_receipt_blocking_reconstruction.v1", "physical_clock": summary["physical_clock"],
        "complete_offered": summary["offered"], "completed": summary["completed"],
        "scope": "executed identities and physical position plus offline full candidate capacity checks; exact pending wait indexes and full native FIFO queue order unavailable",
        "storage_release_events": storage_releases, "trays": [{**t, "last_physical_event": last_physical.get(t["tray_id"])} for t in trays.values()],
        "actual_last_waiting_heads": rows,
        "candidate_receiving_dependency_edges": sorted(set(dependency_edges)),
        "static_unreachable_head_count": sum(all(c["reason"] in ("closed_edge", "no_static_legal_suffix") for c in r["offline_candidate_capacity_checks"]) for r in rows),
        "business_or_physical_state_modified": False, "optimality": "unknown"}
    write_json(folder/"blocking_diagnosis.json", result)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    result = diagnose(args.folder)
    print(json.dumps({k: v for k, v in result.items() if k not in ("trays", "actual_last_waiting_heads", "storage_release_events")}, indent=2))
