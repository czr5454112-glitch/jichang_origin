"""Read one immutable final shard for a conditional endpoint blocking audit.

No NativeSession, tape reconstruction, or original full-run acceptance occurs.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict, deque
import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path): return json.loads(Path(path).read_text(encoding="utf-8-sig"))
def gz(path): return json.loads(gzip.decompress(Path(path).read_bytes()))
def require(value, reason):
    if not value: raise ValueError("endpoint_diagnostic:" + reason)


def analyze(data, part, offline=None):
    result, now = part["result"], part["control_continuation"]["physical_time"]
    trays, receipts = result["trays"], result["receipts"]
    nodes = {r["node"]: r for r in data["node_contracts"]}
    edge_contracts = {(r["from"], r["to"]): r for r in data["edge_contracts"]}
    graph, all_graph = defaultdict(list), defaultdict(list)
    for source, target, _, _ in data["edge_records"]:
        all_graph[source].append(target)
        if edge_contracts[source, target]["capacity"] > 0 and nodes[source]["capacity"] > 0 and nodes[target]["capacity"] > 0:
            graph[source].append(target)
    def reach(source, target):
        seen, queue = {source}, deque([source])
        while queue:
            u = queue.popleft()
            for v in graph[u]:
                if v not in seen: seen.add(v); queue.append(v)
        return {"reachable": target in seen, "source": source, "target": target,
            "complete_positive_reachable_nodes": sorted(seen),
            "closed_boundary_edges": [edge_contracts[u, v] for u in sorted(seen) for v in all_graph[u] if v not in seen]}

    identities = {t["tray_id"] for t in trays}
    require(len(identities) == len(trays) and identities == {t["tray_id"] for t in data["trays"]}, "carrier_denominator")
    positions = {t["tray_id"]: (t["node"], None) for t in data["trays"]}
    latest, live_wait, physical_receipts = defaultdict(dict), {}, []
    previous = -1.
    for ordinal, row in enumerate(receipts):
        event, time = row["event"], row["time"]
        require(previous <= time <= now, "receipt_time_order")
        previous = time
        tray, leg = row.get("tray_id"), row.get("transport_leg_id")
        if tray:
            require(tray in identities, "unknown_receipt_tray")
            if event in {"LOAD_START", "LOAD_COMPLETE", "LEG_START", "EDGE_ENTER", "EDGE_EXIT", "STORAGE_ENTER", "STORAGE_RELEASE", "RESOURCE_WAIT", "RESOURCE_WAKE", "LEG_FAILED", "UNLOAD_COMPLETE"}:
                latest[tray][event] = {"ordinal": ordinal, **row}
        if event == "RESOURCE_WAIT": live_wait[leg] = {"ordinal": ordinal, **row}
        elif event in {"RESOURCE_WAKE", "EDGE_ENTER", "LEG_COMPLETE", "LEG_FAILED"}: live_wait.pop(leg, None)
        if event == "EDGE_ENTER":
            require(positions[tray] == (row["from"], None), "entry_without_source")
            positions[tray] = row["from"], (row["from"], row["to"])
        elif event == "EDGE_EXIT":
            require(positions[tray][1] == (row["from"], row["to"]), "exit_without_entry")
            positions[tray] = row["to"], None
        if event in {"EDGE_ENTER", "EDGE_EXIT", "LOAD_START", "LOAD_COMPLETE", "STORAGE_ENTER", "STORAGE_RELEASE", "UNLOAD_COMPLETE", "LEG_FAILED", "EMPTY_RECEIVED"}:
            physical_receipts.append({"ordinal": ordinal, **row})
    for tray in trays:
        edge = None if tray["edge_to"] < 0 else (tray["edge_from"], tray["edge_to"])
        require(positions[tray["tray_id"]] == (tray["node"], edge), "final_position_not_receipt_reconstructed")
    node_rows = []
    for node, contract in sorted(nodes.items()):
        parked = [t["tray_id"] for t in trays if t["edge_to"] < 0 and t["node"] == node]
        incoming = [t["tray_id"] for t in trays if t["edge_to"] == node]
        leases = [t["tray_id"] for t in trays if t["reception_node"] == node]
        occupants = set(parked) | set(incoming) | set(leases)
        require(len(occupants) <= contract["capacity"], "capacity_exceeded")
        if occupants:
            node_rows.append({"node": node, "resource_owner": contract["resource_owner"], "capacity": contract["capacity"],
                "occupancy": len(occupants), "parked": parked, "incoming": incoming, "receiving_leases": leases,
                "available_empty_trays": [t["tray_id"] for t in trays if t["node"] == node and t["edge_to"] < 0 and
                    t["mode"] == "empty" and t["active_leg"] < 0 and t["available_at"] <= now]})
    occupancy = {r["node"]: r for r in node_rows}
    legs = {r["runtime_id"]: r for r in result["leg_identities"]}
    transferred = {r["request_id"]: r for r in result["transfers"]}
    outbox = part["controller_state"]["client"]["outbox"]
    mappings = []
    for tray in trays:
        leg = legs[tray["active_leg"]]
        job = data["jobs"][tray["job"]] if tray["job"] >= 0 else None
        if job:
            goal = job["storage_node"] if leg["kind"] == "storage_in" else job["destination"]
            mandatory = [(job["origin"], job["storage_node"]), (job["storage_node"], job["destination"])] if job["storage_node"] >= 0 else [(job["origin"], job["destination"])]
            total_reachability = [reach(u, v) for u, v in mandatory]
            transfer = None
        else:
            identity = leg["transport_leg_id"].rsplit(":empty_return:", 1)[0]
            transfer = {"request_id": identity, "payload": outbox[identity]["payload"], "resolution": transferred[identity]}
            goal = transfer["payload"]["destination"]
            total_reachability = []
        candidates = []
        for target in all_graph[tray["node"]]:
            suffix = reach(target, goal)["reachable"]
            candidate = {"to": target, "edge_capacity": edge_contracts[tray["node"], target]["capacity"],
                "positive_suffix_to_active_goal": suffix, "receiver_occupancy": occupancy.get(target, {}).get("occupancy", 0),
                "receiver_capacity": nodes[target]["capacity"], "receiver_trays": sorted(set(
                    occupancy.get(target, {}).get("parked", []) + occupancy.get(target, {}).get("incoming", []) + occupancy.get(target, {}).get("receiving_leases", [])))}
            candidate["receiver_occupancy_excluding_this_tray"] = len(set(candidate["receiver_trays"]) - {tray["tray_id"]})
            candidate["receiver_full"] = candidate["receiver_occupancy_excluding_this_tray"] >= candidate["receiver_capacity"]
            candidates.append(candidate)
        mappings.append({"tray": tray, "job": job, "active_leg": leg, "active_goal": goal,
            "current_stage_reachability": reach(tray["node"], goal), "all_mandatory_stages": total_reachability,
            "permanently_unreachable_loaded_job_under_fixed_graph": bool(job and not all(r["reachable"] for r in total_reachability)),
            "last_observed_events": latest[tray["tray_id"]], "reconstructed_outstanding_resource_wait": live_wait.get(leg["transport_leg_id"]),
            "current_outgoing_candidates": candidates, "empty_transfer": transfer})

    diagnostic = {"status": "not_yet_saved", "actual_fifo_queues_verified": False, "future_event_heap_available": False}
    dependencies = []
    if offline is not None:
        require(offline["now"] == now and {t["tray_id"] for t in offline["trays"]} == identities, "offline_time_or_tray_denominator")
        for other in offline["trays"]:
            tray = next(t for t in trays if t["tray_id"] == other["tray_id"])
            require(all(tray[k] == other[k] for k in ("node", "mode", "active_leg", "edge_from", "edge_to", "reception_node")) and tray["job"] == other["job_index"], "offline_final_tray_mismatch")
        by_id = {r["active_leg"]["runtime_id"]: r for r in mappings}
        require({r["runtime_id"] for r in offline["resource_waits"]} ==
            {r["active_leg"]["runtime_id"] for r in mappings if r["reconstructed_outstanding_resource_wait"]}, "offline_wait_denominator")
        mapped_queues = []
        for junction in offline["junctions"]:
            for queue_name in ("queue", "source_queue"):
                ids = junction[queue_name]
                require(len(set(ids)) == len(ids), "duplicate_queue_leg")
                queue = []
                for rank, identity in enumerate(ids):
                    row = by_id[identity]
                    require(row["tray"]["node"] == junction["node"] and row["tray"]["edge_to"] < 0, "queue_tray_position")
                    queue.append({"position": rank, "runtime_id": identity, "tray_id": row["tray"]["tray_id"],
                        "business_bag_id": row["job"]["business_bag_id"] if row["job"] else None,
                        "active_goal": row["active_goal"]})
                if queue: mapped_queues.append({"node": junction["node"], "queue_kind": queue_name, "ordered_rows": queue})
        diagnostic = {"status": "saved_offline_current_state_crosschecked", "actual_fifo_queues_verified": True,
            "future_event_heap_available": False, "junctions": [r for r in offline["junctions"] if r["queue"] or r["source_queue"] or r["scheduled_incoming"]],
            "mapped_queues": mapped_queues, "resource_waits": offline["resource_waits"],
            "scheduled_incoming_total": sum(j["scheduled_incoming"] for j in offline["junctions"]),
            "future_next_dispatch_nodes": [j["node"] for j in offline["junctions"] if j["next_dispatch_time"] > now]}
        for wait in offline["resource_waits"]:
            row = by_id[wait["runtime_id"]]
            require(row["reconstructed_outstanding_resource_wait"] is not None and row["tray"]["node"] == wait["node"], "offline_wait_missing_from_receipts")
            dependencies.append({"waiting_tray": row["tray"]["tray_id"], "node": wait["node"],
                "static_blocked": wait["static_blocked"], "receiving_nodes": wait["receiving_nodes"],
                "edge_indices": wait["edge_indices"], "ranking_nodes": wait["ranking_nodes"],
                "classification": "Native subscription to OR-resource/policy-ranking changes, not an AND-edge deadlock proof."})
    else:
        for row in mappings:
            if row["reconstructed_outstanding_resource_wait"]:
                dependencies.append({"waiting_tray": row["tray"]["tray_id"], "node": row["tray"]["node"],
                    "receipt_reason": row["reconstructed_outstanding_resource_wait"]["reason"],
                    "full_positive_suffix_receivers": [c["to"] for c in row["current_outgoing_candidates"] if c["edge_capacity"] > 0 and c["positive_suffix_to_active_goal"] and c["receiver_full"]],
                    "classification": "Inferred receiver blocker from saved receipt plus current occupancy; exact native subscription/queue not yet exported."})
    static_blockers = [r for r in mappings if r["job"] is not None and
        not r["current_stage_reachability"]["reachable"] and
        r["reconstructed_outstanding_resource_wait"] is not None and
        r["reconstructed_outstanding_resource_wait"]["reason"] == "no_static_legal_suffix"]
    blocker_rows = [{"tray_id": r["tray"]["tray_id"], "business_bag_id": r["job"]["business_bag_id"],
        "node": r["tray"]["node"], "event": "RESOURCE_WAIT:no_static_legal_suffix",
        "required_goal": r["active_goal"], "wait_receipt": r["reconstructed_outstanding_resource_wait"],
        "closed_boundary_edges": r["current_stage_reachability"]["closed_boundary_edges"],
        "counterexample_to_static_claim": "Exhibit a directed positive-capacity path from this node to its required goal under this exact input. Changing capacity or the required destination changes the contract.",
        "queue_scope": "Exact FIFO order only asserted when saved offline junction rows are present."} for r in static_blockers]
    for witness in blocker_rows:
        witness["verified_fifo_positions"] = [] if offline is None else [
            {"node": q["node"], "queue_kind": q["queue_kind"], "position": r["position"]}
            for q in diagnostic["mapped_queues"] for r in q["ordered_rows"] if r["tray_id"] == witness["tray_id"]]
    return {"status": "endpoint_saved_artifact_diagnostic_only", "physical_time": now,
        "business_status_counts": dict(Counter(j["status"] for j in result["jobs"])), "tray_mode_counts": dict(Counter(t["mode"] for t in trays)),
        "business_completions": sum(j["status"] == "completed" for j in result["jobs"]),
        "native_completed_legs_not_business_completions": result["native_summary"]["completed_count"],
        "receipt_edge_enters": sum(r["event"] == "EDGE_ENTER" for r in receipts), "receipt_edge_exits": sum(r["event"] == "EDGE_EXIT" for r in receipts),
        "last_physical_receipts": physical_receipts[-12:], "last_edge_exit_at": max(r["time"] for r in receipts if r["event"] == "EDGE_EXIT"),
        "all_current_positions_reconstructed_from_initial_trays": True, "nodes": node_rows, "tray_business_node_mapping": mappings,
        "wait_dependencies": dependencies, "offline_diagnostics": diagnostic,
        "timed_release_limits": {"inflight_carriers": sum(t["edge_to"] >= 0 for t in trays),
            "loading_storage_unloading_hold_carriers": sum(t["mode"] in {"loading", "storage", "unloading", "hold"} for t in trays),
            "future_input_arrivals": sum(j["arrival"] > now for j in data["jobs"]),
            "physical_fault_tape": data["faults"], "owner_outages": data["owner_protocol"].get("owner_outages", []),
            "future_internal_event_heap": "not exported; future protocol/control/calendar events cannot be excluded"},
        "individual_static_blocker_witnesses": blocker_rows,
        "deadlock_certified": False, "minimal_resource_cycle_certified": False,
        "interpretation": ["The observed dependency chain terminates in an impossible mandatory destination; it need not be a resource cycle.",
            "Full receiver occupancy is necessary blocking evidence, but alternative legal routes and FIFO/ranking policy must be considered.",
            "No current in-flight/lifecycle carrier supplies an immediate EDGE_EXIT/unload release. This is not a proof that all future timed events are absent.",
            "A waiting112 diversion may free a berth but cannot create an absent mandatory route. Whether the observed static blocker is the actual Storage FIFO head requires the saved queue diagnostic.",
            "Startup R2 must avoid permanently unreachable FIFO heads without skipping them, adding trays, changing capacity, or treating future source input as online knowledge."],
        "new_native_executions": 0, "independent_full_run_acceptance": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True); parser.add_argument("--shard", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True); parser.add_argument("--native-source", type=Path, required=True)
    args = parser.parse_args(); source = args.campaign.resolve()
    heartbeat_bytes = (source / "heartbeat.json").read_bytes(); heartbeat = json.loads(heartbeat_bytes)
    receipt_bytes = (source / "receipt.json").read_bytes(); receipt = json.loads(receipt_bytes)
    path, sidecar = source / f"segments/{args.shard:04d}.json.gz", source / f"segment_hashes/{args.shard:04d}.json"
    descriptor = read(sidecar); require(Path(descriptor["path"]).as_posix() == f"segments/{args.shard:04d}.json.gz" and sha(path) == descriptor["sha256"], "shard_sidecar")
    part = gz(path); require(part["status"] == "reached" and part["control_continuation"]["physical_time"] == part["control_continuation"]["requested_horizon"], "not_complete_endpoint")
    require(part["controller_state"]["native_timestamp_complete"] is True and not part["controller_state"]["pending_owners"] and not part["controller_state"]["needs_native_drain"], "incomplete_timestamp")
    require(heartbeat["latest_native_seal"] == {"shard": args.shard, "physical_time": part["control_continuation"]["physical_time"], "native_state_sha256": part["native_state_sha256"]}, "heartbeat_seal_fields")
    command = receipt["command"]; value = lambda key: command[command.index(key) + 1]
    cut_path = ROOT / value("--cut-manifest")
    require(sha(cut_path) == value("--expected-cut-sha256"), "producer_cut_hash")
    cut = read(cut_path); input_path = source / "input.json.gz"
    require(sha(input_path) == cut["input_sha256"], "input_cut_hash")
    data = gz(input_path); require(len(data["jobs"]) == cut["offered_total"], "offered_count")
    binary = ROOT / value("--binary"); require(sha(binary) == receipt["binary_sha256"] == cut["binary_sha256"], "native_binary_identity")
    offline_path = source / "native_offline_diagnostics.json.gz"
    offline = gz(offline_path) if offline_path.exists() else None
    report = analyze(data, part, offline)
    bound = [input_path, path, sidecar, cut_path, binary]
    if offline is not None: bound.append(offline_path)
    bound.extend(args.native_source / "cpp/ics_core/runtime" / name for name in ("circulation.hpp", "circulation_runtime_impl.hpp", "circulation_recovery_impl.hpp"))
    report.update(schema="g31.saved_final_endpoint_diagnostic.v1", final_native_seal_field=part["native_state_sha256"],
        seal_verification="Equality of retained final-part and contemporaneous heartbeat fields only; no native recomputation.",
        source_receipt_status_at_read=receipt["status"], source_heartbeat_sha256=hashlib.sha256(heartbeat_bytes).hexdigest(),
        source_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(), evidence={str(p.resolve()): sha(p) for p in bound},
        verifier_sha256=sha(__file__), raw_shards_read=1)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "source_heartbeat_snapshot.json").write_bytes(heartbeat_bytes)
    (args.output / "source_receipt_snapshot.json").write_bytes(receipt_bytes)
    shutil.copyfile(__file__, args.output / "analyzer.py")
    (args.output / "diagnostic.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "business_status_counts", "tray_mode_counts", "business_completions", "last_edge_exit_at", "deadlock_certified")}))


if __name__ == "__main__": main()
