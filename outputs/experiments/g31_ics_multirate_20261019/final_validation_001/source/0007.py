"""Read-only diagnosis of a saved full-input horizon, without native restoration."""
from __future__ import annotations

import argparse
from collections import Counter, deque
import gzip
import hashlib
import json
from pathlib import Path


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return json.load(stream)


def analyze(input_path, shard_path):
    data, part = load(input_path), load(shard_path)
    result = part["result"]
    if part["status"] != "reached" or result is None:
        raise ValueError("completed_saved_horizon_required")
    adjacency = {}
    positive = {(row["from"], row["to"]) for row in data["edge_contracts"] if row["capacity"] > 0}
    for source, target, *_ in data["edge_records"]:
        if (source, target) in positive:
            adjacency.setdefault(source, []).append(target)

    def reachable(source, target):
        seen, queue = {source}, deque([source])
        while queue:
            node = queue.popleft()
            if node == target:
                return True
            for nxt in adjacency.get(node, []):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return False

    stalled = []
    for tray in result["trays"]:
        if tray["job"] < 0 or tray["edge_to"] >= 0:
            continue
        contract, state = data["jobs"][tray["job"]], result["jobs"][tray["job"]]
        if contract["business_bag_id"] != state["business_bag_id"]:
            raise ValueError("job_identity_order_mismatch")
        goal = contract["storage_node"] if contract["storage_node"] >= 0 and state["storage_released_at"] < 0 else contract["destination"]
        stalled.append({"tray_id": tray["tray_id"], "business_bag_id": contract["business_bag_id"],
            "node": tray["node"], "goal": goal, "mode": tray["mode"],
            "positive_capacity_static_path_exists": reachable(tray["node"], goal)})
    waits = [row for row in result["receipts"] if row["event"] == "RESOURCE_WAIT"]
    latest = {}
    for row in waits:
        latest[row["tray_id"]] = row
    physical = [row for row in result["receipts"] if row["event"] in {"EDGE_ENTER", "EDGE_EXIT"}]
    return {"schema": "g31.saved_horizon_gridlock_diagnosis.v1",
        "input_sha256": hashlib.sha256(Path(input_path).read_bytes()).hexdigest(),
        "shard_sha256": hashlib.sha256(Path(shard_path).read_bytes()).hexdigest(),
        "physical_time": part["control_continuation"]["physical_time"],
        "offered_total": len(data["jobs"]), "business_status_counts": dict(Counter(j["status"] for j in result["jobs"])),
        "tray_mode_counts": dict(Counter(t["mode"] for t in result["trays"])),
        "inflight_trays": sum(t["edge_to"] >= 0 for t in result["trays"]),
        "last_edge_motion": physical[-1] if physical else None,
        "stationary_loaded_trays": stalled, "last_recorded_resource_wait_by_tray": list(latest.values()),
        "static_unreachable_at_current_node": [row["business_bag_id"] for row in stalled if not row["positive_capacity_static_path_exists"]],
        "native_executed": False, "full_day_metrics": None,
        "interpretation": "A saved intermediate horizon only. Static reachability removes exactly zero-capacity edges. A recorded no_static_legal_suffix at the storage-out head is consistent with FIFO blockage of other reachable jobs; actual current native queue membership needs independent reconstruction/diagnostics. No demand removal, capacity change, or intervention benefit is inferred."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--shard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.input, args.shard)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("physical_time", "offered_total", "business_status_counts", "inflight_trays", "static_unreachable_at_current_node")}))


if __name__ == "__main__":
    main()
