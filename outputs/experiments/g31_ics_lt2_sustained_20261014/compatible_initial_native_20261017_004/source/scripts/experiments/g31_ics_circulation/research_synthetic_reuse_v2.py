"""Versioned native016 continuation repair and finite offline reference.

117 predeclared native branches: old24, 81 additional fixed timing cells, and
12 causal ablations. No old evidence or original-map input is changed.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import traceback

from . import research_synthetic_reuse_chain as v1
from . import reference_reuse_timing as timing
from .native_host import audit_result, load_native
from .original_workload import digest, write_json

MAX_BRANCHES = 120
CONTINUATION_VERSION = "v2.1_initial_native_keep"
SUPPLY_ATTEMPT_LIMIT = 16
REJECTION_COOLDOWN = .5
LATER_MODES = ("adaptive", "occupancy_only", "native_keep")


def known_current_preference(client, tray: dict, now: float) -> int | None:
    """Only own delivered ACKs establish a preference; native route is hidden."""
    matches = []
    for row in client.rows.values():
        r, ack = row["request"], row.get("ack", {})
        if (row["kind"] == "route" and ack.get("status") == "updated"
                and ack.get("delivered_at", math.inf) <= now and r["expiry"] >= now
                and r["tray_id"] == tray["tray_id"] and r["business_bag_id"] == tray["business_bag_id"]
                and r["from"] == tray["node"] and r["expected_generation"] == tray["generation"]
                and r["expected_traversal"] == tray["traversal_id"]):
            matches.append((ack["delivered_at"], r["next"]))
    return max(matches)[1] if matches else None


def later_choice(view: dict, tray: dict, mode: str) -> dict:
    if mode not in LATER_MODES:
        raise ValueError("reuse_v2:undeclared_later_mode")
    if mode == "native_keep":
        return {"next": None, "delivered_forecasts": [], "selection_reason": "explicit_keep_native_no_next_claim"}
    forecast_next, messages = v1.later_route(view, tray) if mode == "adaptive" else (3, [])
    local3 = next(n for n in view["node_contracts"] if n["node"] == 3)
    if local3["resource_owner"] != view["owner_id"] or "occupancy" not in local3:
        raise ValueError("reuse_v2:missing_lawful_local_resource")
    full3 = local3["occupancy"] >= local3["capacity"]
    chosen = 8 if forecast_next == 3 and full3 else forecast_next
    return {"next": chosen, "delivered_forecasts": messages, "local_node3": copy.deepcopy(local3),
        "selection_reason": "local3_full_bypass" if full3 and forecast_next == 3 else
                            "delivered_forecast_bypass" if forecast_next == 8 else "explicit_next3"}


def recovery_basis(view: dict, predecessor: dict, attempt_count: int) -> dict | None:
    ack = predecessor.get("ack", {})
    now = view["now"]
    delivered = ack.get("delivered_at", math.inf)
    if (attempt_count >= SUPPLY_ATTEMPT_LIMIT or ack.get("status") != "rejected"
            or ack.get("reason") != "receiving_full" or not math.isfinite(delivered)
            or now < delivered + REJECTION_COOLDOWN or now + .01 >= v1.HORIZON - 1.):
        return None
    tray = next((t for t in view["trays"] if t["tray_id"] == "E" and t["node"] == 5
                 and t["mode"] == "empty" and t["edge_to"] < 0 and t["available_at"] <= now), None)
    demand = v1.latest_demand(view, "A")
    if not tray or not demand or demand["delivered_at"] > now or not any(j["origin"] == 1 for j in demand["jobs"]):
        return None
    return {"at": now, "predecessor_request_id": predecessor["request"]["request_id"],
        "delivered_rejection": copy.deepcopy(ack), "local_tray": copy.deepcopy(tray),
        "delivered_demand": copy.deepcopy(demand), "cooldown_seconds": REJECTION_COOLDOWN}


def continue_v2(branch, client, seed_channels: dict, supply_id: str, mode: str) -> dict:
    channels = copy.deepcopy(seed_channels)
    forecasts, route_keys = {}, set()
    choices, returns, recovery = [], [], []
    supplies = [supply_id]
    for tick in range(int((v1.HORIZON - v1.START) / v1.PERIOD) + 1):
        target = v1.START + tick * v1.PERIOD
        progress = branch.advance_to(target, max_events=100000)
        if progress["status"] != "reached" or not progress["horizon_complete"]:
            return {"status": "native_budget_incomplete", "route_choices": choices, "returns": returns,
                    "supply_lineage": supplies, "recovery_decisions": recovery}
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
                            forecasts[key] = {"request_id": client.submit("A", "service_forecast", f"forecast-{tick}",
                                target_owner="B", tray_id="E", next=3, message_delay=.01, publication_delay=.01)}
                for key, row in forecasts.items():
                    if key not in current and "withdrawal" not in row and client.rows[row["request_id"]]["ack"].get("status") == "delivered":
                        row["withdrawal"] = client.submit("A", "withdraw_service_forecast", f"withdraw-{tick}-{len(client.rows)}",
                            forecast_request_id=row["request_id"], message_delay=.01, publication_delay=.01)
                empty = next((t for t in view["trays"] if t["tray_id"] == "L" and t["node"] == 6
                    and t["mode"] == "empty" and t["edge_to"] < 0 and t["available_at"] <= target), None)
                demand = v1.latest_demand(view, "B")
                pending = returns and not client.rows[returns[-1]["request_id"]]["terminal"]
                if empty and not pending and len(returns) < 2 and demand and any(j["origin"] == 7 for j in demand["jobs"]):
                    identity = client.submit("A", "transfer", f"return-{len(returns)}", tray_id="L", source=6,
                        destination=7, earliest_departure=target, expiry=v1.HORIZON - 1., message_delay=.01)
                    returns.append({"at": target, "request_id": identity, "tray": copy.deepcopy(empty), "delivered_demand": copy.deepcopy(demand)})
            else:
                basis = recovery_basis(view, client.rows[supplies[-1]], len(supplies))
                if basis:
                    identity = client.submit("B", "transfer", f"initial-supply-recovery-{len(supplies)}", tray_id="E",
                        source=5, destination=1, earliest_departure=target, expiry=v1.HORIZON - 1., message_delay=.01)
                    supplies.append(identity)
                    recovery.append({**basis, "request_id": identity})
                for tray in view["trays"]:
                    if tray["tray_id"] != "L" or tray["node"] != 7 or tray["mode"] != "loaded" or tray["edge_to"] >= 0:
                        continue
                    key = (tray["business_bag_id"], tray["generation"], tray["traversal_id"])
                    if key in route_keys:
                        continue
                    route_keys.add(key)
                    choice = later_choice(view, tray, mode)
                    known = known_current_preference(client, tray, target)
                    identity = (v1.request_route(client, "B", tray, choice["next"], f"later-route-{len(choices)}")
                                if choice["next"] is not None and known != choice["next"] else None)
                    choices.append({"at": target, "request_id": identity, "job": tray["business_bag_id"],
                        **choice, "known_delivered_preference": known, "local_tray": copy.deepcopy(tray)})
    branch.advance_to(v1.HORIZON, max_events=100000)
    client.refresh(retry=False)
    return {"status": "finished", "route_choices": choices, "returns": returns,
            "supply_lineage": supplies, "recovery_decisions": recovery}


def assess_cell(data: dict, result: dict, client, continuation: dict, specification: dict) -> dict:
    complete = (result["advance"]["status"] == "reached" and result["advance"]["horizon_complete"]
                and result["advance"]["physical_time"] == v1.HORIZON)
    jobs = {j["business_bag_id"]: j["completed_at"] for j in result["jobs"]}
    expected = {j["business_bag_id"] for j in data["jobs"]}
    business = (complete and len(result["jobs"]) == len(expected) and set(jobs) == expected
                and all(math.isfinite(t) and 0 <= t <= v1.HORIZON for t in jobs.values()))
    receipts = result["receipts"]
    line = continuation["supply_lineage"]
    supply = [client.rows[i] for i in line]
    returns = [client.rows[r["request_id"]] for r in continuation["returns"]]
    transfer_ids = {i for i, r in client.rows.items() if r["kind"] == "transfer"}
    ack_ok = lambda row, status: row.get("ack", {}).get("status") == status and 0 <= row["ack"].get("delivered_at", math.inf) <= v1.HORIZON
    supply_ok = (1 <= len(line) <= SUPPLY_ATTEMPT_LIMIT and len(set(line)) == len(line)
        and ack_ok(supply[-1], "received") and all(ack_ok(r, "rejected") and r["ack"].get("reason") == "receiving_full" for r in supply[:-1]))
    recovery_ok = len(continuation["recovery_decisions"]) == len(line) - 1
    for index, decision in enumerate(continuation["recovery_decisions"]):
        predecessor = client.rows[line[index]]
        recovery_ok = recovery_ok and (decision["predecessor_request_id"] == line[index]
            and decision["request_id"] == line[index + 1] and decision["delivered_rejection"] == predecessor["ack"]
            and decision["at"] >= predecessor["ack"]["delivered_at"] + REJECTION_COOLDOWN
            and decision["delivered_demand"]["delivered_at"] <= decision["at"]
            and decision["local_tray"]["tray_id"] == "E" and decision["local_tray"]["node"] == 5
            and decision["local_tray"]["mode"] == "empty" and decision["local_tray"]["edge_to"] < 0)
    executed = (supply_ok and recovery_ok and len(returns) == 2 and all(ack_ok(r, "received") for r in returns)
                and transfer_ids == set(line) | {r["request"]["request_id"] for r in returns})
    actual_returns = [r for r in receipts if r["event"] == "EMPTY_RECEIVED" and r["tray_id"] == "L" and r["node"] == 7]
    loads = [r for r in receipts if r["event"] == "LOAD_START" and r["business_bag_id"] in {"reuse1", "reuse2"}]
    same_tray = (len(actual_returns) == 2 and len(loads) == 2 and all(r["tray_id"] == "L" for r in loads)
        and [r["business_bag_id"] for r in loads] == ["reuse1", "reuse2"]
        and all(a["time"] <= b["time"] for a, b in zip(actual_returns, loads)))
    routes = [r for r in client.rows.values() if r["kind"] == "route"]
    route_expected = int(specification["initial_next"] == 2) + sum(c["request_id"] is not None for c in continuation["route_choices"])
    accepted = len(routes) == route_expected and all(ack_ok(r, "updated") for r in routes)
    initial = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == "loaded" and r["from"] == 0]
    route_match = len(initial) == 1 and initial[0]["to"] == specification["initial_next"]
    actual_choices = []
    for choice in continuation["route_choices"]:
        edges = [r for r in receipts if r["event"] == "EDGE_ENTER" and r["business_bag_id"] == choice["job"] and r["from"] == 7]
        if choice["next"] is None:
            route_match = route_match and specification["later_mode"] == "native_keep" and len(edges) == 1 and edges[0]["to"] in (3, 8)
        else:
            route_match = route_match and len(edges) == 1 and edges[0]["to"] == choice["next"]
            if choice["request_id"] is None:
                route_match = route_match and choice["known_delivered_preference"] == choice["next"]
        actual_choices.append({"job": choice["job"], "selected_next": choice["next"],
                               "actual_next": edges[0]["to"] if len(edges) == 1 else None})
    replay = copy.deepcopy(data)
    replay["transfers"] = [{**c["request"], "issued_at": c["at"]} for c in client.calls if c["kind"] == "transfer" and not c["retry"]]
    try:
        audit = audit_result(replay, result)
    except (AssertionError, ValueError, KeyError) as exc:
        audit = {"status": "failed", "reason": str(exc)}
    stock = len(result["trays"]) == 2 and {t["tray_id"] for t in result["trays"]} == {"L", "E"}
    choices_complete = [c["job"] for c in continuation["route_choices"]] == ["reuse1", "reuse2"]
    valid = (business and executed and accepted and route_match and same_tray and stock and choices_complete
             and audit.get("status") == "passed" and continuation["status"] == "finished")
    return {"status": "assessed" if valid else "unknown_incomplete_or_unexecuted", "completion": jobs,
        "completion_sum": sum(jobs.values()) if business else None, "business_complete": business,
        "common_horizon_complete": complete, "required_transfer_lineages_received": executed,
        "all_routes_updated": accepted, "chosen_routes_match_executed_edges": route_match,
        "same_L_two_returns_and_two_reloads": same_tray, "stock_preserved": stock, "audit": audit,
        "actual_later_choices": actual_choices, "supply_attempt_count": len(line),
        "recovered_rejection_count": len(line) - 1, "recovery_decisions_valid": recovery_ok,
        "transfer_acks": [r.get("ack", {}) for r in supply + returns], "route_acks": [r.get("ack", {}) for r in routes]}


def plan_campaign(old: Path) -> tuple[dict, dict]:
    scenes, ledger = {}, {}
    for gate in v1.GATES:
        folder = old / f"gate{int(gate)}"
        data = json.loads((folder / "input.json").read_text(encoding="utf-8"))
        original = timing.read_gzip(folder / "route1_window1.json.gz")
        if data != json.loads(json.dumps(v1.scene(gate))):
            raise ValueError("reuse_v2:old_input_mismatch")
        plan = timing.candidate_plan(data, original["seed_views"])
        scenes[str(gate)] = {"input": data, "old_checkpoint": original["checkpoint_identity"], "views": original["seed_views"],
                             "timing_plan": plan}
        for route in (1, 2):
            for window, departure in enumerate(plan["old_windows"]):
                ledger[f"gate{int(gate)}/old_route{route}_window{window}"] = {"gate": gate, "initial_next": route,
                    "departure": departure, "later_mode": "adaptive", "phase": "old24", "status": "unknown_unexecuted"}
        for index, w in enumerate(plan["windows"]):
            if w["departure"] in plan["old_windows"]:
                continue
            ledger[f"gate{int(gate)}/new_fixed_{index:02d}"] = {"gate": gate, "initial_next": 1,
                "departure": w["departure"], "later_mode": "adaptive", "phase": "stronger96", "status": "unknown_unexecuted"}
        for route, window in [(2, 0), (1, 3)]:
            for mode in ("occupancy_only", "native_keep"):
                ledger[f"gate{int(gate)}/ablate_route{route}_window{window}_{mode}"] = {"gate": gate, "initial_next": route,
                    "departure": plan["old_windows"][window], "later_mode": mode, "phase": "causal12", "status": "unknown_unexecuted"}
    if len(ledger) != 117 or len(ledger) > MAX_BRANCHES:
        raise ValueError("reuse_v2:campaign_budget")
    return scenes, ledger


def assess_domain(rows: dict, baseline: dict, expected: set[str]) -> dict:
    baseline_ok = baseline.get("summary", {}).get("status") == "assessed"
    evaluated = {}
    for key, row in rows.items():
        s = row.get("summary", {})
        comparable = baseline_ok and row["status"] == "assessed" and s.get("status") == "assessed"
        delta = {j: t - baseline["summary"]["completion"][j] for j, t in s["completion"].items()} if comparable else None
        evaluated[key] = {"status": "assessed" if comparable else "unknown", "initial_next": row["initial_next"],
            "departure": row["departure"], "later_mode": row["later_mode"], "completion": s.get("completion"),
            "completion_sum": s.get("completion_sum") if comparable else None,
            "per_job_delta_vs_v2_incumbent": delta, "all_offered_protected": comparable and all(d <= 0 for d in delta.values())}
    complete = set(rows) == expected and all(r["status"] == "assessed" for r in evaluated.values())
    def best(keys):
        eligible = [k for k in keys if evaluated[k]["all_offered_protected"]]
        return min(eligible, key=lambda k: (evaluated[k]["completion_sum"], k)) if eligible else None
    fixed = best([k for k, r in evaluated.items() if r["initial_next"] == 1]) if complete else None
    joint = best(evaluated) if complete else None
    return {"status": "complete_finite_domain" if complete else "unknown_incomplete_domain", "cells": evaluated,
        "best_protected_fixed_initial_route": fixed, "best_protected_enumerated_choice": joint,
        "protected_gain_seconds": evaluated[fixed]["completion_sum"] - evaluated[joint]["completion_sum"] if fixed and joint else None,
        "continuous_optimality": "unknown", "online_solver": False}


def reports(ledger: dict, scenes: dict) -> dict:
    result = {}
    for gate in v1.GATES:
        prefix = f"gate{int(gate)}/"
        rows = {k[len(prefix):]: r for k, r in ledger.items() if k.startswith(prefix)}
        baseline = rows["old_route1_window1"]
        old = {k: r for k, r in rows.items() if r["phase"] == "old24"}
        strong = {k: r for k, r in rows.items() if r["later_mode"] == "adaptive"
                  and (r["initial_next"] == 1 or k == "old_route2_window0")}
        old_keys = {f"old_route{r}_window{w}" for r in (1, 2) for w in range(4)}
        plan = scenes[str(gate)]["timing_plan"]
        strong_keys = {f"new_fixed_{i:02d}" for i, w in enumerate(plan["windows"]) if w["departure"] not in plan["old_windows"]}
        strong_keys |= {f"old_route1_window{w}" for w in range(4)} | {"old_route2_window0"}
        causal = []
        for route, window in [(2, 0), (1, 3)]:
            adaptive = rows[f"old_route{route}_window{window}"]
            for mode in ("occupancy_only", "native_keep"):
                alternative = rows[f"ablate_route{route}_window{window}_{mode}"]
                pair = assess_domain({"adaptive": adaptive, "ablation": alternative}, baseline, {"adaptive", "ablation"})
                causal.append({"initial_next": route, "old_window": window, "ablation": mode, "comparison": pair,
                    "scope": "Only later R1 rule differs; same initial action, gate, stock and R2 recovery. Different continuation is a causal ablation, not same-continuation factorial kappa."})
        result[str(gate)] = {"old24_replay": assess_domain(old, baseline, old_keys),
                            "stronger96": assess_domain(strong, baseline, strong_keys), "causal_ablations": causal}
    return result


def worker(args) -> int:
    sources = [Path(__file__), Path(v1.__file__), Path(timing.__file__), Path(v1.__file__).with_name("native_host.py"),
               Path(v1.__file__).with_name("original_workload.py"), Path("scripts/eval/run_g4irsf28_service_potential.py")]
    archive = args.output / "source_archive"
    archive.mkdir()
    for path in sources:
        (archive / path.name).write_bytes(path.read_bytes())
    receipt = {"schema": "g31.lt2.reuse_continuation_v2.v1", "continuation_version": CONTINUATION_VERSION, "status": "preparing", "command": sys.argv,
        "source_before": {str(p): digest(p) for p in sources}, "source_changed": [], "binary_sha256": digest(args.binary)}
    started = time.perf_counter()
    ledger = {}
    try:
        scenes, ledger = plan_campaign(args.original_study)
        protocol = {"schema": "g31.lt2.reuse_v2_protocol.v1", "continuation_version": CONTINUATION_VERSION, "maximum_native_branches": MAX_BRANCHES,
            "actual_predeclared_native_branches": len(ledger), "phase_order": ["old24", "stronger96", "causal12"],
            "phase_native_counts": {"old24": 24, "stronger96": 81, "causal12": 12},
            "stronger_reference_count": 96, "stronger_reference_reused_old_cells": 15,
            "scenes": scenes, "branch_manifest": ledger,
            "initial_R1": "Option1 retains native initial route without redundant command, actual edge0to1 required for fixed-route reference. Option2 submits actual route2 command, delivered ACK and edge0to2 required. This is distinct from the later explicit desired-next rule",
            "current_route_visibility": "Native016 exposes no uncommitted next hop. It is unknown unless established by own matching delivered route ACK; no offline diagnostic used online",
            "later_R1": "Desired3/8 uses old delivered-forecast rule, but B-local node3 occupancy forces8 when3 is full. If desired differs from known ACK preference or preference unknown, submit actual route command. Native_keep ablation makes no numeric next-hop claim",
            "receiving_recovery": {"trigger": "delivered terminal receiving_full ACK", "cooldown": REJECTION_COOLDOWN,
                "requirements": "local E still empty at5, latest delivered A waiting demand at1, before expiry39",
                "maximum_supply_intents": SUPPLY_ATTEMPT_LIMIT, "identity": "fresh immutable intent after terminal rejection; ordinary transport retries keep bytes"},
            "protection": "Every four offered-job delta <=0 versus same-gate v2 route1/oldwindow1; no tolerance",
            "offline_information": "Stronger candidate timing grid combines A-local loaded_at with public durations; not available to B-only online proposal",
            "causal12": "Predeclared route2/window0 protected-gain family and route1/window3 feedback family at every gate, occupancy-only and native-keep later-R1 ablations",
            "failure_handling": "Keep every request rejection, missing ACK, incomplete branch and mismatch; no native branch selection by outcomes",
            "claim_limits": ["SYNTHETIC only", "offline finite reference", "no continuous optimum", "not new solver", "not complete100ms"]}
        write_json(args.output / "preregistered_protocol.json", protocol)
        write_json(args.output / "branch_ledger.json", ledger)
        if receipt["binary_sha256"] != args.expected_binary_sha256:
            raise ValueError("reuse_v2:binary_identity")
        native = load_native(args.binary)
        for phase in protocol["phase_order"]:
            for gate in v1.GATES:
                frozen = scenes[str(gate)]
                data = frozen["input"]
                destination = args.output / f"gate{int(gate)}"
                destination.mkdir(exist_ok=True)
                write_json(destination / "input.json", data)
                parent = native.NativeSession(data)
                parent.advance_to(.05)
                seed = v1.Transport(parent)
                channels = {owner: seed.submit(owner, "demand", "seed-demand", target_owner=recipient,
                    message_delay=.01, publication_delay=.01) for owner, recipient in [("A", "B"), ("B", "A")]}
                parent.advance_to(v1.START)
                seed.refresh(retry=False)
                views = {o: parent.observe_protocol(o) for o in ("A", "B")}
                checkpoint = parent.offline_state_sha256()
                if checkpoint != frozen["old_checkpoint"] or json.loads(json.dumps(views)) != frozen["views"]:
                    raise ValueError("reuse_v2:checkpoint_or_information_drift")
                for fullkey, row in ledger.items():
                    if row["phase"] != phase or row["gate"] != gate:
                        continue
                    label = fullkey.split("/")[1]
                    row["status"] = "unknown_in_progress"
                    write_json(args.output / "branch_ledger.json", ledger)
                    try:
                        branch = parent.fork()
                        if branch.offline_state_sha256() != checkpoint:
                            raise ValueError("reuse_v2:fork_identity")
                        client = v1.Transport(branch)
                        client.rows, client.calls = copy.deepcopy(seed.rows), copy.deepcopy(seed.calls)
                        tray = next(t for t in views["A"]["trays"] if t["tray_id"] == "L")
                        if row["initial_next"] == 2:
                            v1.request_route(client, "A", tray, row["initial_next"], "initial-route")
                        supply = client.submit("B", "transfer", "initial-supply", tray_id="E", source=5, destination=1,
                            earliest_departure=row["departure"], expiry=v1.HORIZON - 1., message_delay=.01)
                        continuation = continue_v2(branch, client, channels, supply, row["later_mode"])
                        result = branch.result_at(v1.HORIZON)
                        summary = assess_cell(data, result, client, continuation, row)
                        raw = {"specification": copy.deepcopy(row), "checkpoint_identity": checkpoint,
                            "seed_views": views, "calls": client.calls, "outbox": client.rows,
                            "continuation": continuation, "result": result, "summary": summary}
                        with gzip.open(destination / f"{label}.json.gz", "wt", encoding="utf-8") as stream:
                            json.dump(raw, stream, allow_nan=False)
                        row.update(status=summary["status"], summary=summary)
                    except Exception:
                        row.update(status="unknown_failed", exception=traceback.format_exc())
                        write_json(destination / f"{label}.failed.json", row)
                    write_json(args.output / "branch_ledger.json", ledger)
            receipt["reports"] = reports(ledger, scenes)
            receipt["completed_phase"] = phase
            write_json(args.output / "receipt.json", receipt)
            write_json(args.output / f"phase_{phase}.json", receipt["reports"])
        receipt["status"] = "executed" if all(r["status"] == "assessed" for r in ledger.values()) else "completed_with_unknowns"
    except Exception:
        receipt.update(status="failed", exception=traceback.format_exc())
    receipt["source_changed"] = [str(p) for p in sources if digest(p) != receipt["source_before"][str(p)]]
    if receipt["source_changed"]:
        receipt["status"] = "invalidated_source_changed"
    receipt["branch_status_counts"] = {s: sum(r["status"] == s for r in ledger.values()) for s in sorted({r["status"] for r in ledger.values()})}
    receipt["wall_seconds"] = time.perf_counter() - started
    receipt["complete_100ms_requirement_certified"] = False
    write_json(args.output / "receipt.json", receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k not in {"reports", "source_before"}}, indent=2))
    return int(receipt["status"] != "executed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--expected-binary-sha256", required=True)
    parser.add_argument("--original-study", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=90.)
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
    write_json(args.output / "process.json", {"status": status, "exit_code": code, "command": command,
        "hard_timeout_seconds": args.timeout_seconds, "wall_seconds": time.perf_counter() - started,
        "maximum_native_workers": 1, "interrupted_rows_remain_unknown": True})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
