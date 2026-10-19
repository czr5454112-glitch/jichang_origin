"""Prespecified native SYNTHETIC two-tray reuse chain, not an airport model.

An exact 24-cell offline reference (three gates, two initial suffixes, four
departure windows) shares one causal continuation. The fixed-initial-suffix
window family is a strong timing diagnostic, not a complete B2/B3/B4 solver.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import itertools
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback

from .native_host import audit_result, load_native, prepare_input
from .original_workload import digest, write_json


HORIZON = 40.
START = .11
PERIOD = .05
PUBLIC_RECEIVER_LOAD = 3.
GATES = (0., 2 * PUBLIC_RECEIVER_LOAD, 4 * PUBLIC_RECEIVER_LOAD)
TERMINAL = {"received", "rejected", "failed", "expired", "cancelled", "updated", "delivered", "withdrawn"}


def scene(gate: float) -> dict:
    if gate not in GATES:
        raise ValueError("reuse_chain:undeclared_gate")
    edges = [(0, 1, 1., 1.), (0, 2, 2., 1.), (1, 3, 1., 1.),
             (2, 3, 1., 1.), (3, 4, 1., 1.), (5, 1, .2, 1.),
             (4, 6, .5, 1.), (6, 7, 2., 1.), (7, 3, 1., 1.),
             (7, 8, 1.5, 1.), (8, 4, .5, 1.)]
    owners = {n: "B" if n in (3, 5, 7, 8) else "A" for n in range(9)}
    jobs = [{"business_bag_id": identity, "origin": origin, "destination": destination,
             "arrival": arrival, "deadline": HORIZON,
             "storage_node": 4 if identity == "loaded" else -1,
             "storage_release_at": gate if identity == "loaded" else 0.,
             "storage_min_dwell": 0., "load_seconds": load,
             "unload_seconds": .1, "hold_seconds": .1, "allow_suffix_reroute": True}
            for identity, origin, destination, arrival, load in [
                ("loaded", 0, 6, 0., .1), ("receiver", 1, 4, .05, PUBLIC_RECEIVER_LOAD),
                ("reuse1", 7, 6, .02, .1), ("reuse2", 7, 6, .03, .1)]]
    return prepare_input({"schema": "g31.circulation.input.v1",
        "model_scope": "SYNTHETIC ONLY: declared mandatory on-carrier gate and two real returns; no original input changed",
        "node_records": [(n, 3 if n == 4 else 1, 1. if n == 0 else .1, n, 0,
                          [v for u, v, _, _ in edges if u == n]) for n in owners],
        "edge_records": edges,
        "node_contracts": [{"node": n, "zone": "B" if n in (5, 7, 8) else "A",
            "resource_owner": owner, "control_partition": "partition_" + owner,
            "capacity": 2 if n == 4 else 1, "allow_export": n != 4,
            "allow_receive": True, "export_min_stock": 0} for n, owner in owners.items()],
        "edge_contracts": [{"from": u, "to": v, "capacity": 1, "entry_headway": .5} for u, v, _, _ in edges],
        "trays": [{"tray_id": "L", "node": 0}, {"tray_id": "E", "node": 5}],
        "jobs": jobs, "transfers": [], "faults": [],
        "owner_protocol": {"enabled": True, "timeout": 1., "ack_delay": .02},
        "options": {"max_simulation_time": HORIZON, "max_events": 100000, "trace_limit": 2000}})


def departure_windows(data: dict, now: float = START) -> tuple[float, ...]:
    """Static public service/travel durations, frozen before any outcome exists."""
    service = {n[0]: n[2] for n in data["node_records"]}
    travel = {(u, v): length / speed for u, v, length, speed in data["edge_records"]}
    return (now, now + service[0] + travel[0, 1] + service[1],
            now + PUBLIC_RECEIVER_LOAD, now + 2 * PUBLIC_RECEIVER_LOAD)


def protocol() -> dict:
    return {"schema": "g31.lt2.synthetic_reuse_chain_protocol.v1", "branch_budget": 24,
        "gates": list(GATES), "initial_next": [1, 2], "departure_windows": departure_windows(scene(0.)),
        "keep_route_semantics": "next1 initial and next3 later retain incumbent route without a redundant command; detour2/bypass8 require native ACK and actual traversal",
        "all_offered_jobs": ["loaded", "receiver", "reuse1", "reuse2"],
        "incumbent": "initial_next1/window1, fixed before outcomes in each gate",
        "protection": "every offered job completion <= same-gate incumbent; incomplete is unknown",
        "factorial": "R1 next1/next2 x R2 window0/window1, predeclared; other windows retained",
        "common_continuation": "public 0.05s ticks; immutable 0.5s ACK retry; delivered demand and conditional service forecasts only",
        "later_R1": "at B7 choose8 if delivered E->3 forecast intersects [estimated entry3, entry3+public load3], otherwise3",
        "public_duration_contract": {"receiver_load_seconds": PUBLIC_RECEIVER_LOAD,
            "scope": "explicit synthetic common operational duration, not a hidden future-job field"},
        "return_rule": "A6 exports local available empty L to B7 only after delivered B waiting demand; at most two exports",
        "fixed_module_factor": "node4 capacity2 and export disabled, E remains there; no stock creation or branch removal",
        "reference_scope": "B5 exact enumeration of eight initial decisions/gate under one continuation; B2-like fixed-initial-suffix timing diagnostic only",
        "not_implemented": ["full rolling-horizon optimizer", "B3 MPC", "B4 LNS", "new solver novelty"],
        "failure_criteria": ["any incomplete cell", "unresolved/rejected selected transfer or route",
            "missing same-L return/load witness", "source identity change", "all-offered protection failure"],
        "horizon": HORIZON, "policy_uses_native_future_or_result": False}


class Transport:
    """Small experiment-local outbox; native delivered ACK is the only status."""
    def __init__(self, session):
        self.session = session
        self.rows: dict[str, dict] = {}
        self.calls: list[dict] = []

    def submit(self, owner: str, kind: str, label: str, **payload) -> str:
        identity = f"live:{len(owner)}:{owner}:{label}"
        if identity in self.rows:
            raise ValueError("reuse_chain:duplicate_intent")
        request = {"request_id": identity, "owner_id": owner, **payload}
        if kind != "transfer":
            request["kind"] = kind
        self.rows[identity] = {"kind": kind, "request": request, "terminal": False}
        self.send(identity, retry=False)
        return identity

    def send(self, identity: str, *, retry: bool):
        row = self.rows[identity]
        payload = copy.deepcopy(row["request"])
        reply = (self.session.submit_protocol_transfer(payload) if row["kind"] == "transfer"
                 else self.session.submit_protocol_command(payload))
        row["next_retry"] = self.session.physical_time + .5
        row["reply"] = copy.deepcopy(reply)
        row["terminal"] = reply.get("status") == "rejected"
        self.calls.append({"at": self.session.physical_time, "kind": row["kind"],
                           "retry": retry, "request": payload, "reply": reply})

    def refresh(self, *, retry=True):
        for identity, row in self.rows.items():
            owner = row["request"]["owner_id"]
            view = (self.session.protocol_request(owner, identity) if row["kind"] == "transfer"
                    else self.session.protocol_command(owner, identity))
            row["ack"] = view.get("last_delivered_ack", {})
            row["terminal"] = row["terminal"] or row["ack"].get("status") in TERMINAL
            if retry and not row["terminal"] and self.session.physical_time >= row["next_retry"]:
                self.send(identity, retry=True)


def latest_demand(view: dict, source: str) -> dict | None:
    messages = [m for m in view["delivered_messages"] if m["kind"] == "demand" and m["source_owner"] == source]
    return max(messages, key=lambda m: (m["observed_at"], m["publication_sequence"])) if messages else None


def later_route(view: dict, tray: dict) -> tuple[int, list[dict]]:
    service = {n[0]: n[2] for n in view["node_records"]}
    travel = {(u, v): length / speed for u, v, length, speed in view["edge_records"]}
    eta = view["now"] + service[7] + travel[7, 3]
    forecasts = [m for m in view["delivered_messages"] if m["kind"] == "service_forecast"
                 and m.get("tray_id") == "E" and m.get("next") == 3]
    tombstones = {m["supersedes"] for m in forecasts if m.get("status") == "withdrawn"}
    active = [m for m in forecasts if m.get("status") == "conditional"]
    latest = max(active, key=lambda m: (m["observed_at"], m.get("publication_sequence", 0)), default=None)
    if latest and latest["message_id"] in tombstones:
        latest = None
    overlap = latest is not None and latest["release_estimate"] >= eta and latest["entry_estimate"] <= eta + PUBLIC_RECEIVER_LOAD
    return (8 if overlap else 3), ([copy.deepcopy(latest)] if latest else [])


def request_route(client: Transport, owner: str, tray: dict, next_node: int, label: str) -> str:
    return client.submit(owner, "route", label, business_bag_id=tray["business_bag_id"],
        tray_id=tray["tray_id"], **{"from": tray["node"], "next": next_node},
        expected_generation=tray["generation"], expected_traversal=tray["traversal_id"],
        expiry=client.session.physical_time + 5., message_delay=.01)


def continue_branch(branch, client: Transport, seed_channels: dict) -> dict:
    channels = copy.deepcopy(seed_channels)
    forecasts: dict[tuple, dict] = {}
    route_keys: set[tuple] = set()
    route_choices, returns = [], []
    for tick in range(int((HORIZON - START) / PERIOD) + 1):
        target = START + tick * PERIOD
        response = branch.advance_to(target, max_events=100000)
        if response["status"] != "reached" or not response["horizon_complete"]:
            return {"status": "native_budget_incomplete", "route_choices": route_choices, "returns": returns}
        client.refresh()
        for owner, recipient in [("A", "B"), ("B", "A")]:
            view = branch.observe_protocol(owner)
            old = client.rows[channels[owner]]
            signature = branch.protocol_demand_signature(owner)
            if old["terminal"] and old["ack"].get("captured_demand_signature") != signature:
                channels[owner] = client.submit(owner, "demand", f"demand-{tick}",
                    target_owner=recipient, message_delay=.01, publication_delay=.01)
            if owner == "A":
                current = set()
                for tray in view["trays"]:
                    if tray["tray_id"] == "E" and tray["node"] == 1 and tray["edge_to"] < 0 and tray["mode"] in {"loading", "loaded"}:
                        key = (tray["generation"], tray["traversal_id"], tray["mode"])
                        current.add(key)
                        if key not in forecasts:
                            identity = client.submit("A", "service_forecast", f"forecast-{tick}",
                                target_owner="B", tray_id="E", next=3, message_delay=.01, publication_delay=.01)
                            forecasts[key] = {"request_id": identity}
                for key, row in forecasts.items():
                    if key not in current and "withdrawal" not in row and client.rows[row["request_id"]]["ack"].get("status") == "delivered":
                        row["withdrawal"] = client.submit("A", "withdraw_service_forecast", f"withdraw-{tick}-{len(client.rows)}",
                            forecast_request_id=row["request_id"], message_delay=.01, publication_delay=.01)
                empty = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 6
                    and t["mode"] == "empty" and t["edge_to"] < 0 and t["available_at"] <= target), None)
                demand = latest_demand(view, "B")
                pending = returns and not client.rows[returns[-1]["request_id"]]["terminal"]
                if empty and not pending and len(returns) < 2 and demand and any(j["origin"] == 7 for j in demand["jobs"]):
                    identity = client.submit("A", "transfer", f"return-{len(returns)}", tray_id="L", source=6,
                        destination=7, earliest_departure=target, expiry=HORIZON - 1., message_delay=.01)
                    returns.append({"at": target, "request_id": identity, "tray": copy.deepcopy(empty), "delivered_demand": copy.deepcopy(demand)})
            else:
                for tray in view["trays"]:
                    if tray["tray_id"] != "L" or tray["node"] != 7 or tray["mode"] != "loaded" or tray["edge_to"] >= 0:
                        continue
                    key = (tray["business_bag_id"], tray["generation"], tray["traversal_id"])
                    if key in route_keys:
                        continue
                    route_keys.add(key)
                    next_node, messages = later_route(view, tray)
                    identity = (request_route(client, "B", tray, next_node, f"later-route-{len(route_choices)}")
                                if next_node == 8 else None)
                    route_choices.append({"at": target, "request_id": identity, "job": tray["business_bag_id"],
                        "next": next_node, "delivered_forecasts": messages, "local_tray": copy.deepcopy(tray)})
    branch.advance_to(HORIZON, max_events=100000)
    client.refresh(retry=False)
    return {"status": "finished", "route_choices": route_choices, "returns": returns}


def assess_cell(data: dict, result: dict, client: Transport, continuation: dict, initial_next: int) -> dict:
    complete = result["advance"]["status"] == "reached" and result["advance"]["horizon_complete"]
    jobs = {j["business_bag_id"]: j["completed_at"] for j in result["jobs"]}
    expected_ids = {j["business_bag_id"] for j in data["jobs"]}
    business = (complete and len(result["jobs"]) == len(expected_ids) and set(jobs) == expected_ids
                and all(math.isfinite(t) and 0 <= t <= HORIZON for t in jobs.values()))
    transfers = [row for row in client.rows.values() if row["kind"] == "transfer"]
    routes = [row for row in client.rows.values() if row["kind"] == "route"]
    executed = len(transfers) == 3 and all(row["ack"].get("status") == "received" for row in transfers)
    expected_routes = int(initial_next == 2) + sum(c["next"] == 8 for c in continuation["route_choices"])
    accepted_routes = len(routes) == expected_routes and all(row["ack"].get("status") == "updated" for row in routes)
    receipts = result["receipts"]
    returns = [r for r in receipts if r["event"] == "EMPTY_RECEIVED" and r["tray_id"] == "L" and r["node"] == 7]
    loads = [r for r in receipts if r["event"] == "LOAD_START" and r["business_bag_id"] in {"reuse1", "reuse2"}]
    same_tray = (len(returns) == 2 and len(loads) == 2 and all(r["tray_id"] == "L" for r in loads)
        and [r["business_bag_id"] for r in loads] == ["reuse1", "reuse2"]
        and all(a["time"] <= b["time"] for a, b in zip(returns, loads)))
    initial_edges = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == "loaded" and r["from"] == 0]
    route_edges_match = len(initial_edges) == 1 and initial_edges[0]["to"] == initial_next
    for choice in continuation["route_choices"]:
        edges = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == choice["job"] and r["from"] == 7]
        route_edges_match = route_edges_match and len(edges) == 1 and edges[0]["to"] == choice["next"]
    replay = copy.deepcopy(data)
    replay["transfers"] = [{**c["request"], "issued_at": c["at"]} for c in client.calls if c["kind"] == "transfer" and not c["retry"]]
    try:
        audit = audit_result(replay, result)
    except (AssertionError, ValueError, KeyError) as exc:
        audit = {"status": "failed", "error_type": type(exc).__name__, "reason": str(exc)}
    choices_complete = [c["job"] for c in continuation["route_choices"]] == ["reuse1", "reuse2"]
    valid = (business and executed and accepted_routes and route_edges_match and same_tray and choices_complete
             and audit.get("status") == "passed" and continuation["status"] == "finished")
    return {"status": "assessed" if valid else "unknown_incomplete_or_unexecuted", "business_complete": business,
        "completion": jobs, "completion_sum": sum(jobs.values()) if business else None,
        "common_horizon_complete": complete, "all_transfers_received": executed, "all_routes_updated": accepted_routes,
        "same_L_two_returns_and_two_reloads": same_tray, "chosen_routes_match_executed_edges": route_edges_match, "audit": audit,
        "transfer_acks": [r["ack"] for r in transfers], "route_acks": [r["ack"] for r in routes],
        "chain_receipts": [r for r in receipts if r["tray_id"] == "L" and r["event"] in
            {"LOAD_START", "STORAGE_ENTER", "STORAGE_RELEASE", "UNLOAD_COMPLETE", "HOLD_COMPLETE", "EMPTY_RECEIVED", "EDGE_ENTER"}],
        "later_route_choices": continuation["route_choices"], "return_requests": continuation["returns"]}


def assess_regime(cells: dict) -> dict:
    expected = {f"route{route}_window{window}" for route, window in itertools.product((1, 2), range(4))}
    complete = set(cells) == expected and all(row["status"] == "assessed" for row in cells.values())
    baseline = cells.get("route1_window1", {})
    for row in cells.values():
        comparable = row["status"] == baseline.get("status") == "assessed"
        row["per_job_delta_vs_incumbent"] = ({j: t - baseline["completion"][j] for j, t in row["completion"].items()} if comparable else None)
        row["all_offered_protected"] = comparable and all(d <= 0 for d in row["per_job_delta_vs_incumbent"].values())
    def best(keys):
        eligible = [k for k in keys if cells[k]["all_offered_protected"]]
        return min(eligible, key=lambda k: (cells[k]["completion_sum"], k)) if eligible else None
    fixed = best(k for k in cells if k.startswith("route1_")) if complete else None
    joint = best(cells) if complete else None
    kappa = (cells["route2_window0"]["completion_sum"] - cells["route2_window1"]["completion_sum"]
        - cells["route1_window0"]["completion_sum"] + cells["route1_window1"]["completion_sum"]) if complete else None
    pairs = []
    for route in (1, 2):
        for left, right in itertools.combinations(range(4), 2):
            a, b = cells.get(f"route{route}_window{left}"), cells.get(f"route{route}_window{right}")
            if not a or not b or a["status"] != "assessed" or b["status"] != "assessed":
                continue
            changes = [[x["job"], x["next"], y["next"]] for x, y in zip(a["later_route_choices"], b["later_route_choices"])
                       if x["job"] == y["job"] and x["next"] != y["next"]]
            if changes:
                pairs.append({"initial_route": route, "windows": [left, right], "changed_later_R1": changes})
    effects = []
    for window in range(4):
        left, right = cells.get(f"route1_window{window}"), cells.get(f"route2_window{window}")
        if not left or not right or left["status"] != "assessed" or right["status"] != "assessed":
            continue
        # Unload completion plus the same declared hold bounds actual release;
        # the separate EMPTY_RECEIVED receipts witness its causal real return.
        unload_delta = right["completion"]["loaded"] - left["completion"]["loaded"]
        first_return = lambda row: next((r["time"] for r in row["chain_receipts"]
            if r["event"] == "EMPTY_RECEIVED" and r["node"] == 7), None)
        a, b = first_return(left), first_return(right)
        if a is not None and b is not None and abs(unload_delta) > 1e-9 and abs(b - a) > 1e-9:
            effects.append({"window": window, "initial_R1_unload_delta_seconds": unload_delta,
                            "first_real_return_delta_seconds": b - a})
    return {"status": "assessed" if complete else "unknown_incomplete_domain", "cells": cells,
        "predeclared_factorial_kappa_seconds": kappa, "B2_like_best_protected_fixed_initial_suffix": fixed,
        "B5_best_protected_enumerated_initial_decision": joint,
        "protected_joint_gain_over_best_fixed_seconds": (cells[fixed]["completion_sum"] - cells[joint]["completion_sum"]) if complete and fixed and joint else None,
        "R2_window_changes_subsequent_R1_choice_pairs": pairs,
        "initial_R1_changes_release_and_real_return": effects,
        "bidirectional_feedback_witness": complete and bool(pairs) and bool(effects), "online_joint_solver": False,
        "solver_novelty_established": False}


def run_regime(native, data: dict, output: Path | None = None) -> dict:
    parent = native.NativeSession(data)
    parent.advance_to(.05)
    seed = Transport(parent)
    channels = {owner: seed.submit(owner, "demand", "seed-demand", target_owner=recipient,
                message_delay=.01, publication_delay=.01) for owner, recipient in [("A", "B"), ("B", "A")]}
    parent.advance_to(START)
    seed.refresh(retry=False)
    seed_views = {o: parent.observe_protocol(o) for o in ("A", "B")}
    assert latest_demand(seed_views["A"], "B") and latest_demand(seed_views["B"], "A")
    checkpoint = parent.offline_state_sha256()
    cells = {}
    for next_node, index in itertools.product((1, 2), range(4)):
        key = f"route{next_node}_window{index}"
        branch = parent.fork()
        assert branch.offline_state_sha256() == checkpoint
        client = Transport(branch)
        client.rows, client.calls = copy.deepcopy(seed.rows), copy.deepcopy(seed.calls)
        tray = next(t for t in seed_views["A"]["trays"] if t["tray_id"] == "L")
        if next_node == 2:
            request_route(client, "A", tray, next_node, "initial-route")
        client.submit("B", "transfer", "initial-supply", tray_id="E", source=5, destination=1,
            earliest_departure=departure_windows(data)[index], expiry=HORIZON - 1., message_delay=.01)
        continuation = continue_branch(branch, client, channels)
        result = branch.result_at(HORIZON)
        cells[key] = assess_cell(data, result, client, continuation, next_node)
        if output:
            with gzip.open(output / f"{key}.json.gz", "wt", encoding="utf-8") as stream:
                json.dump({"checkpoint_identity": checkpoint, "seed_views": seed_views,
                    "calls": client.calls, "outbox": client.rows, "continuation": continuation,
                    "result": result, "summary": cells[key]}, stream, allow_nan=False)
            write_json(output / "progress.json", {"completed_cells": list(cells), "last_status": cells[key]["status"]})
    return {**assess_regime(cells), "checkpoint_identity": checkpoint}


def worker(args) -> int:
    paths = [Path(__file__), Path(__file__).with_name("native_host.py"), Path(__file__).with_name("original_workload.py"),
             Path("scripts/eval/run_g4irsf28_service_potential.py")]
    archive = args.output / "source_archive"
    archive.mkdir()
    for path in paths:
        (archive / path.name).write_bytes(path.read_bytes())
    receipt = {"schema": "g31.lt2.synthetic_reuse_chain.v1", "status": "running", "protocol": protocol(),
        "source_before": {str(path): digest(path) for path in paths}, "regimes": {}, "command": sys.argv,
        "binary_sha256": digest(args.binary)}
    write_json(args.output / "preregistered_protocol.json", receipt)
    write_json(args.output / "receipt.json", receipt)
    started = time.perf_counter()
    try:
        if receipt["binary_sha256"] != args.expected_binary_sha256:
            raise ValueError("reuse_chain:binary_identity_mismatch")
        native = load_native(args.binary)
        for gate in GATES:
            destination = args.output / f"gate{int(gate)}"
            destination.mkdir()
            data = scene(gate)
            write_json(destination / "input.json", data)
            receipt["regimes"][str(gate)] = run_regime(native, data, destination)
            write_json(args.output / "receipt.json", receipt)
        receipt["status"] = "executed"
    except Exception:
        receipt["status"] = "failed"
        receipt["exception"] = traceback.format_exc()
    receipt["wall_seconds"] = time.perf_counter() - started
    receipt["source_changed"] = [str(p) for p in paths if digest(p) != receipt["source_before"][str(p)]]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    receipt["complete_100ms_requirement_certified"] = False
    write_json(args.output / "receipt.json", receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"regimes", "protocol"}}, indent=2))
    return int(receipt["status"] != "executed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=180.)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    args.output.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", __spec__.name, *sys.argv[1:], "--worker"]
    started = time.perf_counter()
    with (args.output / "stdout.txt").open("w", encoding="utf-8") as stdout, (args.output / "stderr.txt").open("w", encoding="utf-8") as stderr:
        try:
            run = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.timeout_seconds, check=False)
            status, code = "finished", run.returncode
        except subprocess.TimeoutExpired:
            status, code = "hard_timeout", 124
    write_json(args.output / "process.json", {"status": status, "exit_code": code,
        "timeout_seconds": args.timeout_seconds, "wall_seconds": time.perf_counter() - started,
        "command": command, "maximum_native_workers": 1})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
