"""Run declared circulation contracts on the compiled G31 host.

No Python simulation clock, routing executor, or inventory is advanced here.
The potential calculation is the existing mature G31 preprocessing algorithm.
"""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from typing import Any

from scripts.eval.run_g4irsf28_service_potential import service_aware_potential


def load_native(binary: str | Path):
    path = Path(binary).resolve(strict=True)
    spec = importlib.util.spec_from_file_location("czr005_circulation", path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load native module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_input(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    potential, contract = service_aware_potential(
        data["node_records"], data["edge_records"], minimum_service_seconds=0.001
    )
    result["heuristic_time"] = potential
    result["potential_contract"] = contract
    return result


def tiny_cycle() -> dict[str, Any]:
    edges = [(0, 1, 1.0, 1.0), (0, 6, 1.2, 1.0), (1, 2, 1.0, 1.0),
             (6, 2, 1.0, 1.0), (6, 3, 1.0, 1.0), (2, 3, 1.0, 1.0),
             (3, 4, 1.0, 1.0), (4, 5, 1.0, 1.0), (5, 0, 1.0, 1.0)]
    return prepare_input({
        "schema": "g31.circulation.input.v1",
        "model_scope": "synthetic on-carrier Storage, per-berth unloading, fixed module ports",
        "node_records": [(n, 3 if n == 2 else 1, 0.05, n, 0,
                          [v for u, v, _, _ in edges if u == n]) for n in range(7)],
        "edge_records": edges,
        "node_contracts": [{"node": n, "zone": "B" if n in (3, 4) else "A",
                            "capacity": 1} for n in range(7)],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1, "entry_headway": 0.2}
                           for u, v, _, _ in edges],
        "trays": [{"tray_id": "T0", "node": 0}],
        "jobs": [
            {"business_bag_id": "B1", "origin": 0, "destination": 4, "arrival": 0.0,
             "deadline": 40.0, "storage_node": 2, "storage_release_at": 6.0,
             "storage_min_dwell": 2.0, "load_seconds": 0.1,
             "unload_seconds": 0.5, "hold_seconds": 1.25},
            {"business_bag_id": "B2", "origin": 0, "destination": 4, "arrival": 0.2,
             "deadline": 60.0, "storage_node": 2, "storage_release_at": 0.0,
             "storage_min_dwell": 0.25, "load_seconds": 0.1,
             "unload_seconds": 0.5, "hold_seconds": 1.25},
        ],
        "transfers": [{"request_id": "return-T0", "tray_id": "T0", "source": 4,
                       "destination": 0, "issued_at": 0.1, "message_delay": 0.0,
                       "earliest_departure": 0.0, "expiry": 50.0}],
        "faults": [],
        "options": {"max_simulation_time": 80.0},
    })


def audit_result(data: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Independent consistency checks over executed receipts, not expected success.

    Checks flow conservation, traversal pairs, travel duration, tail headway,
    business/leg/tray identity separation and causal Storage/reuse bounds.
    It does not prove optimality or every owner-internal invariant.
    """
    assert result["mode"] == "circulation"
    expected_trays = {t["tray_id"] for t in data["trays"]}
    assert {t["tray_id"] for t in result["trays"]} == expected_trays
    assert len(result["trays"]) == len(expected_trays)
    leg_map = {r["transport_leg_id"]: r for r in result["leg_identities"]}
    assert len(leg_map) == len(result["leg_identities"])
    business_ids = {j["business_bag_id"] for j in data["jobs"]}
    assert not set(leg_map) & business_ids
    assert not set(leg_map) & expected_trays
    travel = {(u, v): max(length / speed, 0.001) for u, v, length, speed in data["edge_records"]}
    edges = {(e["from"], e["to"]): e for e in data["edge_contracts"]}
    last_entry: dict[tuple[int, int], float] = {}
    active: dict[int, dict[str, Any]] = {}
    completed: set[int] = set()
    physical = {t["tray_id"]: t["node"] for t in data["trays"]}
    edge_counts = {key: 0 for key in edges}
    node_contracts = {n["node"]: n for n in data["node_contracts"]}
    job_specs = {j["business_bag_id"]: j for j in data["jobs"]}
    transfer_specs = {t["request_id"]: t for t in data["transfers"]}
    phases = {t: "empty" for t in expected_trays}
    phase_time = {t: 0.0 for t in expected_trays}
    lease: dict[str, int] = {}
    transit_target: dict[str, int] = {}
    active_load: dict[str, str] = {}
    actual_completed: dict[str, float] = {}

    def check_berths():
        counts = {n: 0 for n in node_contracts}
        for tray_id in expected_trays:
            # Remote reception is a real owner reservation, and an in-flight
            # next hop is counted before arrival. Same tray/node is deduplicated.
            for n in {physical.get(tray_id), transit_target.get(tray_id), lease.get(tray_id)} - {None}:
                counts[n] += 1
        for n, count in counts.items():
            assert count <= node_contracts[n]["capacity"], ("berth or reception oversubscription", n, count)

    check_berths()
    time = -math.inf
    for r in result["receipts"]:
        assert r["time"] + 1e-8 >= time, ("receipt time reversed", r)
        time = r["time"]
        tray_id, event = r["tray_id"], r["event"]
        if event == "LOAD_START":
            spec = job_specs[r["business_bag_id"]]
            assert phases[tray_id] == "empty" and tray_id not in active_load
            assert physical[tray_id] == spec["origin"] and time + 1e-8 >= spec["arrival"]
            phases[tray_id] = "loading"
            phase_time[tray_id] = time
            active_load[tray_id] = r["business_bag_id"]
        elif event == "LOAD_COMPLETE":
            spec = job_specs[active_load[tray_id]]
            assert phases[tray_id] == "loading"
            assert time + 1e-8 >= phase_time[tray_id] + spec.get("load_seconds", 0)
            phases[tray_id] = "loaded"
        elif event == "STORAGE_ENTER":
            spec = job_specs[active_load[tray_id]]
            assert phases[tray_id] == "loaded" and physical[tray_id] == spec["storage_node"]
            phases[tray_id] = "storage"
            phase_time[tray_id] = time
        elif event == "STORAGE_RELEASE":
            spec = job_specs[active_load[tray_id]]
            assert phases[tray_id] == "storage"
            assert time + 1e-8 >= max(spec.get("storage_release_at", 0), phase_time[tray_id] + spec.get("storage_min_dwell", 0))
            phases[tray_id] = "loaded"
        elif event == "UNLOAD_START":
            spec = job_specs[active_load[tray_id]]
            assert phases[tray_id] == "loaded" and physical[tray_id] == spec["destination"]
            phases[tray_id] = "unloading"
            phase_time[tray_id] = time
        elif event == "UNLOAD_COMPLETE":
            spec = job_specs[active_load[tray_id]]
            assert phases[tray_id] == "unloading"
            assert time + 1e-8 >= phase_time[tray_id] + spec["unload_seconds"]
            actual_completed[active_load[tray_id]] = time
            phases[tray_id] = "hold"
            phase_time[tray_id] = time + spec["hold_seconds"]
        elif event == "HOLD_COMPLETE":
            assert phases[tray_id] == "hold" and time + 1e-8 >= phase_time[tray_id]
            phases[tray_id] = "empty"
            del active_load[tray_id]
        elif event == "EXPORT_GRANTED":
            spec = transfer_specs[r["reason"]]
            assert phases[tray_id] == "empty" and physical[tray_id] == spec["source"]
            assert node_contracts[spec["source"]]["zone"] != node_contracts[spec["destination"]]["zone"]
            assert node_contracts[spec["source"]].get("allow_export", True)
            assert node_contracts[spec["destination"]].get("allow_receive", True)
            available = sum(phases[t] == "empty" and physical[t] == spec["source"] for t in expected_trays)
            assert available > node_contracts[spec["source"]].get("export_min_stock", 0)
            assert time + 1e-8 >= max(spec["issued_at"] + spec["message_delay"], spec["earliest_departure"])
            assert time <= spec["expiry"] + 1e-8
            lease[tray_id] = spec["destination"]
            phases[tray_id] = "empty_transit"
            check_berths()
        elif event == "EMPTY_RECEIVED":
            assert phases[tray_id] == "empty_transit" and physical[tray_id] == lease[tray_id]
            del lease[tray_id]
            phases[tray_id] = "empty"
        elif event == "UNUSED_RECEIVING_RELEASED":
            assert physical[tray_id] is not None and tray_id not in transit_target
            lease.pop(tray_id)
        elif event == "LEG_FAILED":
            phases[tray_id] = "quarantined"
        elif event == "EMPTY_RECOVERY_GRANTED":
            assert phases[tray_id] == "quarantined" and tray_id not in active_load
            assert tray_id in physical and tray_id not in transit_target and tray_id not in lease
            assert r["node"] == physical[tray_id]
            phases[tray_id] = "empty"
        if r["event"] not in ("EDGE_ENTER", "EDGE_EXIT"):
            continue
        assert r["tray_id"] in expected_trays
        assert r["transport_leg_id"] in leg_map
        identity = leg_map[r["transport_leg_id"]]
        assert data["trays"][identity["tray"]]["tray_id"] == r["tray_id"]
        assert r["business_bag_id"] == ("" if identity["job"] < 0 else data["jobs"][identity["job"]]["business_bag_id"])
        key = (r["from"], r["to"])
        assert key in travel
        tid = r["traversal_id"]
        assert tid > 0
        if r["event"] == "EDGE_ENTER":
            assert tid not in active and tid not in completed
            assert physical[r["tray_id"]] == r["from"]
            assert phases[tray_id] in ("loaded", "empty_transit")
            assert r["time"] + 1e-8 >= last_entry.get(key, -math.inf) + edges[key]["entry_headway"]
            last_entry[key] = r["time"]
            active[tid] = r
            physical[r["tray_id"]] = None
            transit_target[tray_id] = r["to"]
            edge_counts[key] += 1
            assert edge_counts[key] <= edges[key]["capacity"]
        else:
            assert tid in active, ("exit without unique entry", r)
            entry = active.pop(tid)
            assert (entry["tray_id"], entry["from"], entry["to"], entry["transport_leg_id"]) == (
                r["tray_id"], r["from"], r["to"], r["transport_leg_id"])
            assert abs(r["time"] - entry["time"] - travel[key]) < 1e-7
            physical[r["tray_id"]] = r["to"]
            del transit_target[tray_id]
            completed.add(tid)
            edge_counts[key] -= 1
        check_berths()
    for tray in result["trays"]:
        if tray["edge_to"] < 0:
            assert tray["node"] == physical[tray["tray_id"]]
    for spec, job in zip(data["jobs"], result["jobs"], strict=True):
        if job["loaded_at"] >= 0:
            assert job["loaded_at"] + 1e-8 >= spec["arrival"]
        if job["storage_released_at"] >= 0:
            assert job["storage_entered_at"] >= 0
            assert job["storage_released_at"] + 1e-8 >= max(
                spec.get("storage_release_at", 0),
                job["storage_entered_at"] + spec.get("storage_min_dwell", 0))
        if job["completed_at"] >= 0:
            assert actual_completed[spec["business_bag_id"]] == job["completed_at"]
            assert job["loaded_at"] >= 0
            assert job["completed_at"] >= job["loaded_at"]
            if spec.get("storage_node", -1) >= 0:
                assert job["storage_released_at"] >= 0
            assert job["deadline_met"] == (spec["deadline"] < 0 or job["completed_at"] <= spec["deadline"] + 1e-8)
    assert result["native_summary"]["reservation_conflicts"] == 0
    assert result["native_summary"]["physical_fault_edge_entry_violation_count"] == 0
    assert all(not d["full_astar_used"] for d in result["decisions"])
    return {"status": "passed", "completed_traversals": len(completed),
            "open_traversals": len(active), "tray_count": len(expected_trays),
            "optimality": "unknown", "scope": "independent identity, lifecycle, edge/headway, parked/incoming/reception capacity replay"}
