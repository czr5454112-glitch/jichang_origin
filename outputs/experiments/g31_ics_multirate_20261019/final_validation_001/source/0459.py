"""Prespecified SYNTHETIC two-owner route/transfer and three-way berth probes.

Exactly four two-tray factorial cells and eight fixed-three-tray subsets. Native
G31 owns physics, reservations, owner validation, FIFO and capacity. Public
projections/delivered demand construct requests; forks are offline reference.
This is a mechanism probe, not an airport result or a new solver.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import itertools
import json
from pathlib import Path
import sys
import time
import traceback

from .native_host import audit_result, load_native, prepare_input
from .original_workload import digest, write_json


def scene(*, higher_order: bool = False) -> dict:
    if higher_order:
        edges = [(0, 3, 1., 1.), (1, 3, 1., 1.), (2, 3, 1., 1.)]
        owners = {0: "B", 1: "B", 2: "B", 3: "A"}
        capacities = {0: 1, 1: 1, 2: 1, 3: 2}
        services = {n: .1 for n in owners}
        trays = [{"tray_id": f"E{n}", "node": n} for n in range(3)]
        jobs = []
    else:
        edges = [(0, 1, 1., 1.), (0, 2, 2., 1.), (1, 3, 1., 1.),
                 (2, 3, 1., 1.), (3, 4, 1., 1.), (5, 1, .2, 1.)]
        owners = {n: "B" if n == 5 else "A" for n in range(6)}
        capacities = {n: 2 if n == 4 else 1 for n in owners}
        services = {n: 1. if n == 0 else .1 for n in owners}
        trays = [{"tray_id": "L", "node": 0}, {"tray_id": "E", "node": 5}]
        jobs = [{"business_bag_id": identity, "origin": origin, "destination": 4,
                 "arrival": arrival, "deadline": 40., "storage_node": -1,
                 "storage_release_at": 0., "storage_min_dwell": 0., "load_seconds": loading,
                 "unload_seconds": .1, "hold_seconds": .1, "allow_suffix_reroute": True}
                for identity, origin, arrival, loading in [("loaded", 0, 0., .1), ("receiver", 1, .05, 3.)]]
    return prepare_input({"schema": "g31.circulation.input.v1",
        "model_scope": "SYNTHETIC LT2 shared-resource mechanism only; no original-map or field claim",
        "node_records": [(n, 1, services[n], n, 0, [v for u, v, _, _ in edges if u == n]) for n in owners],
        "edge_records": edges,
        "node_contracts": [{"node": n, "zone": owner, "resource_owner": owner,
                            "control_partition": "partition_" + owner, "capacity": capacities[n],
                            "allow_export": True, "allow_receive": True, "export_min_stock": 0}
                           for n, owner in owners.items()],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1, "entry_headway": .5}
                           for u, v, _, _ in edges],
        "trays": trays, "jobs": jobs, "transfers": [], "faults": [],
        "owner_protocol": {"enabled": True, "timeout": 1., "ack_delay": .02},
        "options": {"max_simulation_time": 40., "max_events": 100000, "trace_limit": 1000}})


def request_id(owner: str, name: str) -> str:
    return f"live:{len(owner.encode('utf-8'))}:{owner}:{name}"


def transfer(view: dict, tray_id: str, target: int, *, label: str, earliest: float) -> dict:
    tray = next(t for t in view["trays"] if t["tray_id"] == tray_id)
    assert tray["mode"] == "empty" and tray["edge_to"] < 0
    return {"request_id": request_id(view["owner_id"], label), "owner_id": view["owner_id"],
            "tray_id": tray_id, "source": tray["node"], "destination": target,
            "earliest_departure": earliest, "expiry": 30., "message_delay": .01}


def replay(data: dict, calls: list[dict]) -> dict:
    data = copy.deepcopy(data)
    data["transfers"] = [{**row["request"], "issued_at": row["at"]} for row in calls]
    return data


def classify(result: dict, data: dict) -> dict:
    complete_horizon = result["advance"]["status"] == "reached" and result["advance"]["horizon_complete"]
    jobs = result["jobs"]
    all_jobs = complete_horizon and len(jobs) == len(data["jobs"]) and all(j["completed_at"] >= 0 for j in jobs)
    return {"common_horizon_complete": complete_horizon, "business_complete": all_jobs,
            "jobs": jobs, "completion_sum": sum(j["completed_at"] for j in jobs) if all_jobs and jobs else None,
            "request_statuses": result["transfers"],
            "physical_received_count": sum(r["event"] == "EMPTY_RECEIVED" for r in result["receipts"])}


def finish_with_ack_retry(branch, calls: list[dict]) -> tuple[dict, list[dict]]:
    """A common public timer obtains terminal ACKs using immutable payloads."""
    branch.advance_to(39.)
    retries = [{"at": 39., "request": copy.deepcopy(call["request"]),
                "response": branch.submit_protocol_transfer(copy.deepcopy(call["request"]))} for call in calls]
    return branch.result_at(40.), retries


def classify_joint_subset(row: dict) -> str:
    """Nonreceipt is unknown unless a complete native/ACK contract proves why."""
    acks = row.get("acks", [])
    if (not row.get("common_horizon_complete") or len(acks) != row["selected_count"] or
            any(not ack or ack.get("status") not in {"received", "rejected"} for ack in acks)):
        return "unknown_incomplete_or_unresolved"
    if (row["physical_received_count"] == row["selected_count"] and
            all(ack["status"] == "received" for ack in acks)):
        return "all_selected_executed"
    rejected = [ack for ack in acks if ack["status"] == "rejected"]
    if (rejected and all(ack.get("reason") == "receiving_full" for ack in rejected)
            and row["physical_received_count"] == sum(ack["status"] == "received" for ack in acks)):
        return "unexecutable_joint_set"
    return "unknown_other_failure_or_receipt_mismatch"


def run_factorial(native, data: dict) -> tuple[dict, dict]:
    parent = native.NativeSession(data)
    parent.advance_to(.05)
    demand = {"request_id": request_id("A", "demand"), "owner_id": "A", "kind": "demand",
              "target_owner": "B", "message_delay": .01, "publication_delay": .01}
    parent.submit_protocol_command(demand)
    parent.advance_to(.11)
    views = {o: parent.observe_protocol(o) for o in ["A", "B"]}
    assert any(m.get("kind") == "demand" for m in views["B"]["delivered_messages"])
    local_tray = next(t for t in views["A"]["trays"] if t["tray_id"] == "L")
    assert local_tray["mode"] == "loaded" and local_tray["edge_to"] < 0
    route = {"request_id": request_id("A", "route-alternative"), "owner_id": "A", "kind": "route",
             "business_bag_id": local_tray["business_bag_id"], "tray_id": "L", "from": local_tray["node"],
             "next": 2, "expected_generation": local_tray["generation"],
             "expected_traversal": local_tray["traversal_id"], "expiry": 10., "message_delay": .01}
    saved = parent.offline_state_sha256()
    rows, raw = {}, {"public_views": views, "route": route, "checkpoint_identity": saved}
    for route_on, early in itertools.product([False, True], repeat=2):
        key = f"route{int(route_on)}_early{int(early)}"
        branch = parent.fork()
        assert branch.offline_state_sha256() == saved
        if route_on:
            branch.submit_protocol_command(route)
        # Both levels submit the same executable transfer at the checkpoint;
        # only its public departure window differs. No branch is censored by
        # omitting the receiver's required service or by a privileged fallback.
        payload = transfer(views["B"], "E", 1, label="supply", earliest=.11 if early else 10.)
        response = branch.submit_protocol_transfer(payload)
        calls = [{"at": .11, "request": payload, "response": response}]
        result, retries = finish_with_ack_retry(branch, calls)
        row = classify(result, data)
        row["audit"] = audit_result(replay(data, calls), result)
        row["route_ack"] = branch.protocol_command("A", route["request_id"]).get("last_delivered_ack") if route_on else None
        row["transfer_ack"] = branch.protocol_request("B", payload["request_id"]).get("last_delivered_ack")
        row["loaded_edges"] = [r for r in result["receipts"] if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == "loaded"]
        row["empty_edges"] = [r for r in result["receipts"] if r["event"] == "EDGE_ENTER" and not r["business_bag_id"]]
        rows[key] = row
        raw[key] = {"result": result, "calls": calls, "fixed_timer_retries": retries}
    valid = all(r["business_complete"] and r["physical_received_count"] == 1 and
                (r["transfer_ack"] or {}).get("status") == "received" and
                (not key.startswith("route1") or ((r["route_ack"] or {}).get("status") == "updated"
                  and r["loaded_edges"] and r["loaded_edges"][0]["to"] == 2))
                for key, r in rows.items())
    kappa = (rows["route1_early1"]["completion_sum"] - rows["route1_early0"]["completion_sum"]
             - rows["route0_early1"]["completion_sum"] + rows["route0_early0"]["completion_sum"]) if valid else None
    baseline = rows["route0_early0"]
    for row in rows.values():
        row["job_delta_vs_route0_late"] = {j["business_bag_id"]: j["completed_at"] - b["completed_at"]
            for j, b in zip(row["jobs"], baseline["jobs"], strict=True) if j["completed_at"] >= 0 and b["completed_at"] >= 0}
        row["zero_regression_passed"] = row["business_complete"] and all(x <= 0 for x in row["job_delta_vs_route0_late"].values())
    return {"status": "assessed" if valid else "unknown_unexecutable_or_incomplete_cell", "cells": rows,
            "kappa_completion_sum_seconds": kappa, "checkpoint_identity": saved,
            "bidirectional_online_joint_solver": False, "innovation": "not_established"}, raw


def run_higher_order(native, data: dict) -> tuple[dict, dict]:
    parent = native.NativeSession(data)
    parent.advance_to(.11)
    view = parent.observe_protocol("B")
    candidates = [transfer(view, f"E{n}", 3, label=f"receive-{n}", earliest=.11) for n in range(3)]
    saved = parent.offline_state_sha256()
    rows, raw = {}, {"public_view": view, "candidates": candidates, "checkpoint_identity": saved}
    for mask in range(8):
        branch = parent.fork()
        assert branch.offline_state_sha256() == saved
        calls = []
        for i, payload in enumerate(candidates):
            if mask & (1 << i):
                response = branch.submit_protocol_transfer(payload)
                calls.append({"at": .11, "request": payload, "response": response})
        result, retries = finish_with_ack_retry(branch, calls)
        row = classify(result, data)
        row["audit"] = audit_result(replay(data, calls), result)
        row["selected_count"] = len(calls)
        row["acks"] = [branch.protocol_request("B", c["request"]["request_id"]).get("last_delivered_ack") for c in calls]
        row["status"] = classify_joint_subset(row)
        row["selected_actions_all_received"] = row["status"] == "all_selected_executed"
        rows[str(mask)] = row
        raw[str(mask)] = {"result": result, "calls": calls, "fixed_timer_retries": retries}
    pairwise = all(rows[str(mask)]["selected_actions_all_received"] for mask in [3, 5, 6])
    triple = rows["7"]
    assessed = all(not row["status"].startswith("unknown") for row in rows.values())
    return {"status": "assessed" if assessed else "unknown_incomplete_domain", "subsets": rows, "checkpoint_identity": saved,
            "fixed_trays_every_subset": 3, "receiving_capacity": 2,
            "all_pairs_execute": pairwise, "triple_all_execute": triple["selected_actions_all_received"],
            "higher_order_overcapacity_witness": assessed and pairwise and triple["status"] == "unexecutable_joint_set"
                and triple["physical_received_count"] == 2,
            "scope": "separate SYNTHETIC three-tray factor; simple capacity counterexample, no algorithmic novelty"}, raw


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", type=Path, required=True)
    p.add_argument("--expected-binary-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    paths = [Path(__file__), Path(__file__).with_name("native_host.py"), Path(__file__).with_name("original_workload.py")]
    receipt = {"schema": "g31.lt2.synthetic_contention.v1", "status": "running", "command": sys.argv,
               "source_before": {str(path): digest(path) for path in paths}, "branch_budget": 12,
               "scope": "SYNTHETIC ONLY; four two-tray cells plus eight fixed-three-tray subsets"}
    archive = args.output / "source_archive"
    archive.mkdir()
    for path in paths:
        (archive / path.name).write_bytes(path.read_bytes())
    write_json(args.output / "preregistered_protocol.json", {**receipt,
        "factors": {"two_tray": {"R1": ["S4", "prefer0-to2"], "R2_window": [.11, 10.]},
                    "three_tray": "all eight subsets of three permitted exports to capacity-two receiver"},
        "continuation": "native fixed input through40; no adaptive future lookup; no Python simulator",
        "ack_timer": "identical immutable request retry at39 to receive terminal owner ACKs",
        "objective": "sum completion times only for four complete/executable equal-business cells",
        "protection": "zero per-job regression versus route0 late-transfer; no relaxation",
        "native_compute_budget": "12 bounded branches, max100000 events/input; no full-stream claim"})
    write_json(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    try:
        receipt["binary_sha256"] = digest(args.binary)
        if receipt["binary_sha256"] != args.expected_binary_sha256:
            raise ValueError("synthetic_contention:binary_identity_mismatch")
        native = load_native(args.binary)
        for name, higher, execute in [("two_tray", False, run_factorial), ("three_tray", True, run_higher_order)]:
            data = scene(higher_order=higher)
            write_json(args.output / f"{name}_input.json", data)
            summary, raw = execute(native, data)
            receipt[name] = summary
            with gzip.open(args.output / f"{name}_native.json.gz", "wt", encoding="utf-8") as stream:
                json.dump(raw, stream, allow_nan=False)
            write_json(args.output / "receipt.json", receipt)
        receipt["status"] = "executed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["wall_seconds"] = time.perf_counter() - started
    receipt["source_changed"] = [str(path) for path in paths if digest(path) != receipt["source_before"][str(path)]]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    receipt["complete_100ms_requirement_certified"] = False
    write_json(args.output / "receipt.json", receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"two_tray", "three_tray"}}, indent=2))
    return int(receipt["status"] != "executed")


if __name__ == "__main__":
    raise SystemExit(main())
