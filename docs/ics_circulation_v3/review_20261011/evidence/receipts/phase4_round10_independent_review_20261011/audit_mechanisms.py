"""Independent raw event/interval/checkpoint audit; zero simulation calls."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import pickle
import sys
import time
import traceback

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
OWN = Path(__file__).resolve().parent
BASE = OWN.parent / "phase4_round10_validation_20261011"
OUT = OWN / "mechanism_review_001"
OUT.mkdir(exist_ok=False)
BATCHES = ["mechanisms_001"]
cpu, wall = time.process_time(), time.perf_counter()
result = {"status": "running", "physics_calls": 0, "checks": 0, "main_rows": [], "checkpoint_rows": []}
bindings = {}

def read(path):
    data = path.read_bytes()
    bindings[str(path)] = sha256(data).hexdigest()
    return data

def check(condition, message):
    result["checks"] += 1
    if not condition:
        raise AssertionError(message)

def audit_batch(name):
    source = BASE / name
    report = json.loads(read(source / "results.json"))
    check(report["success"] and not report["source_changed"], name + ": failed or source drift")
    before, after = json.loads(read(source / "before.json")), json.loads(read(source / "after.json"))
    check(before == after, "main execution source binding drift")
    frozen = OWN / "attempt_006/source_snapshot"
    for relative, digest in before.items():
        path = frozen / relative if (frozen / relative).exists() else ROOT / relative
        check(sha256(read(path)).hexdigest() == digest, "source differs from final independently tested source")
    protocol = json.loads(read(source / "protocol.json"))
    expected_runs = len(protocol["cases"]) * len(protocol["modes"]) * (1 + len(protocol["pause_ticks"]))
    check(report["physical_runs_started"] == report["physical_runs_completed"] == expected_runs == 66,
          "physical census differs from fixed protocol")
    check({(row["case"], row["mode"]) for row in report["rows"]} ==
          {(case, mode) for case in protocol["cases"] for mode in protocol["modes"]}, "case/mode census")
    expected_ids = {"early1", "early2", "direct"}
    for row in report["rows"]:
        case, mode = row["case"], row["mode"]
        stem = f"{case}_{mode}"
        raw = json.loads(read(source / (stem + ".json")))
        state, trace = raw["final_snapshot"], raw["trace"]
        bags, trays = state["bags"], state["trays"]
        count = 2 if case in ("two_carriers", "tight_storage") else 1
        check(set(trays) == {f"t{n}" for n in range(count)}, stem + ": carrier creation/deletion")
        check(set(bags) == expected_ids, stem + ": business denominator changed")
        check(all(not b["protected"] if case == "unprotected_reuse" else b["protected"] for b in bags.values()),
              stem + ": source protection changed")
        check([e["time"] for e in trace] == sorted(e["time"] for e in trace), stem + ": unordered trace")
        check(raw["completed"] == state["completed"], stem + ": completion mismatch")
        check(set(raw["uncompleted_bag_ids"]) == expected_ids - set(raw["completed"]), stem + ": omitted failures")
        edges, nodes, module = state["network"]["edges"], state["network"]["nodes"], state["module"]
        loaded, carry = {}, {tid: None for tid in trays}
        unload, storage_in, storage_out = {}, {}, {}
        usable_after = {tid: 0 for tid in trays}
        physical = {tid: ["S" if case == "initial_storage" else "A", 0] for tid in trays}
        slots, empty_travel, service = defaultdict(list), 0, defaultdict(list)
        last_unloading, arrivals = {}, {}
        for event in trace:
            at, kind = event["time"], event["event"]
            tid, bid = event.get("tray_id"), event.get("bag_id")
            if kind == "bag_arrival":
                check(bid not in arrivals and at == bags[bid]["arrival"], stem + ": wrong business arrival")
                arrivals[bid] = at
            elif kind == "load":
                check(bid in arrivals and bid not in loaded and carry[tid] is None, stem + ": duplicate/unobserved load")
                check(at >= usable_after[tid], stem + ": tray reloaded before hold finished")
                check(physical[tid][0] == bags[bid]["origin"] and at >= physical[tid][1], stem + ": wrong load node/time")
                loaded[bid], carry[tid] = (tid, at), bid
                service[tid].append(bid)
            elif kind == "depart":
                edge = edges[event["edge_id"]]
                node, ready = physical[tid]
                check(edge["capacity"] > 0 and node == edge["source"] and at >= ready, stem + ": illegal movement")
                check(at >= usable_after[tid], stem + ": moved before hold release")
                check(at == ready or nodes[node]["can_wait"], stem + ": waiting prohibited")
                slots["node:" + node].append((ready, at, tid))
                slots["edge:" + event["edge_id"]].append((at, at + edge["travel_time"], tid))
                physical[tid] = [edge["target"], at + edge["travel_time"]]
                if carry[tid] is None:
                    empty_travel += edge["travel_time"]
                elif edge["source"] == "S":
                    check(carry[tid] in storage_in and at >= bags[carry[tid]]["storage"]["release_at"], stem + ": early storage exit")
            elif kind == "storage_arrival":
                check(bid not in storage_in and event["node"] == "S", stem + ": duplicate/false ingress")
                check(physical[tid] == ["S", at], stem + ": ingress not physical arrival")
                check(carry[tid] == bid or (case == "initial_storage" and at == 0 and bid == "early1"), stem + ": wrong ingress carrier")
                storage_in[bid] = (tid, at)
            elif kind == "storage_departure":
                check(bid not in storage_out and carry[tid] == bid and bid in storage_in, stem + ": wrong egress carrier")
                check(storage_in[bid][0] == tid and at >= max(storage_in[bid][1], bags[bid]["storage"]["release_at"]), stem + ": release bound violated")
                storage_out[bid] = (tid, at)
            elif kind == "tray_state" and event["mode"] == "unloading":
                check(carry[tid] is not None and event["node"] == bags[carry[tid]]["destination"], stem + ": intermediate unload")
                check(physical[tid] == [event["node"], at], stem + ": wrong final arrival")
                last_unloading[tid] = at
                end = at + module["unload_ticks"] + module["hold_by_node"].get(event["node"], 0)
                slots["reception:" + event["node"]].append((at, end, tid))
            elif kind == "unload_complete":
                check(bid not in unload and carry[tid] == bid, stem + ": duplicate/wrong final unload")
                check(at == last_unloading[tid] + module["unload_ticks"], stem + ": wrong unload service")
                check(not bags[bid]["protected"] or at <= bags[bid]["deadline"], stem + ": protected late")
                if "storage" in bags[bid]:
                    check(bid in storage_out and storage_out[bid][0] == tid, stem + ": completion without same-carrier storage")
                unload[bid], carry[tid] = at, None
                usable_after[tid] = at + module["hold_by_node"].get(bags[bid]["destination"], 0)
            elif kind == "tray_state" and event["mode"] == "empty":
                check(carry[tid] is None and at >= usable_after[tid], stem + ": premature empty supply")
            elif kind == "empty_dispatch":
                check(event["visible_bag_id"] in arrivals and arrivals[event["visible_bag_id"]] <= at, stem + ": future task leaked")
        check(unload == raw["completed"], stem + ": completion not trace-derived")
        for tid, (node, arrived) in physical.items():
            slots["node:" + node].append((arrived, state["now"] + 1, tid))
            check(trays[tid]["node"] == node and trays[tid]["bag_id"] == carry[tid], stem + ": final identity/position differs")
        for resource, intervals in slots.items():
            kind, node = resource.split(":")
            cap = nodes[node]["capacity"] if kind == "node" else edges[node]["capacity"] if kind == "edge" else module["reception_capacity"]
            changes = defaultdict(int)
            for start, end, _ in intervals:
                if start < end:
                    changes[start] += 1
                    changes[end] -= 1
            occupancy = 0
            for tick, delta in sorted(changes.items()):
                occupancy += delta
                check(0 <= occupancy <= cap, stem + f": physical capacity {resource}@{tick}")
        for bid, bag in bags.items():
            expected = {"observed": True, "arrival": bag["arrival"], "deadline": bag["deadline"],
                        "loaded_at": loaded[bid][1] if bid in loaded else None,
                        "tray_id": loaded[bid][0] if bid in loaded else None,
                        "storage": state["storage_progress"].get(bid), "completed_at": unload.get(bid),
                        "uncompleted": bid not in unload}
            check(row["task_rows"][bid] == expected, stem + ": reported task milestones differ")
            progress = state["storage_progress"].get(bid)
            if progress:
                check((progress["tray_id"], progress["arrived_at"]) == storage_in[bid], stem + ": ingress record differs")
                check((progress["tray_id"], progress["departed_at"]) == storage_out.get(bid, (progress["tray_id"], None)), stem + ": egress record differs")
                check(progress["contract"] == bag["storage"], stem + ": contract drift")
        service = {tid: service[tid] for tid in trays}
        reuses = sum(max(0, len(order) - 1) for order in service.values())
        check(service == row["carrier_service_order"] and reuses == row["carrier_reuses"], stem + ": reuse differs")
        drained = len(unload) == 3 and not state["plans"] and not state["empty_targets"] and all(
            tray["mode"] == "empty" and tray["bag_id"] is None for tray in trays.values())
        check(drained == row["transport_drained"] and row["status"] == ("transport_drained" if drained else "fixed_tick_cap_censored"), stem + ": stop classification differs")
        tray_wait = sum((loaded[bid][1] if bid in loaded else state["now"]) - bag["arrival"] for bid, bag in bags.items())
        tardiness = sum(max(0, unload.get(bid, state["now"]) - bag["deadline"])
                        for bid, bag in bags.items() if not bag["protected"])
        inflight = sum(t["mode"] == "in_transit" for t in trays.values())
        check(raw["cost_components"]["tray_wait"] == tray_wait, stem + ": tray wait differs")
        check(raw["cost_components"]["empty_distance"] == empty_travel, stem + ": empty travel differs")
        check(raw["cost_components"]["terminal_backlog"] == 3 - len(unload), stem + ": backlog differs")
        check(raw["cost_components"]["terminal_inflight"] == inflight, stem + ": inflight cost differs")
        check(abs(raw["total_cost"] - (tray_wait + tardiness + .1 * empty_travel + 10 * (3 - len(unload)) + 2 * inflight)) < 1e-8, stem + ": cost differs")
        if case in ("reuse", "unprotected_reuse"):
            check(unload == {"early1": 9, "early2": 18, "direct": 24}, stem + ": hand-derived lifecycle completion")
        if case in ("closed_ingress", "deadline_before_release"):
            check(not unload, stem + ": blocked first FIFO bag cannot be discarded")
        for checkpoint_report in row["checkpoint_replays"]:
            pause = checkpoint_report["at"]
            checkpoint_bytes = read(source / f"{stem}_pause{pause}.pickle")
            replay_bytes = read(source / f"{stem}_replay{pause}.json")
            check(sha256(checkpoint_bytes).hexdigest() == checkpoint_report["checkpoint_sha256"], "checkpoint changed")
            check(sha256(replay_bytes).hexdigest() == checkpoint_report["replay_sha256"], "replay changed")
            replay = json.loads(replay_bytes)
            check(replay == raw, stem + ": replay raw differs")
            checkpoint = pickle.loads(checkpoint_bytes)
            check(checkpoint.state.now == pause and checkpoint.route_mode == mode, stem + ": wrong checkpoint boundary")
            check(list(checkpoint.trace) == trace[:len(checkpoint.trace)], stem + ": checkpoint trace not prefix")
            observed = set(checkpoint.state.bags)
            pending = {b.bag_id for group in checkpoint.pending_arrivals.values() for b in group}
            check(not observed & pending and observed | pending == expected_ids, stem + ": checkpoint loses/leaks task")
            check(all(b.arrival >= pause for group in checkpoint.pending_arrivals.values() for b in group), stem + ": pending past event")
            check(checkpoint.initial_tray_ids == set(trays), stem + ": checkpoint inventory differs")
            for bid, progress in checkpoint.state.storage_progress.items():
                check(progress.arrived_at <= pause and (progress.departed_at is None or progress.departed_at <= pause), stem + ": future progress")
            result["checkpoint_rows"].append({"batch": name, "case": case, "mode": mode, "pause": pause, "raw_exact": True,
                                               "observed": sorted(observed), "pending": sorted(pending)})
        result["main_rows"].append({"batch": name, "case": case, "mode": mode, "status": row["status"],
                                    "completed": unload, "same_carrier_storage": len(storage_in),
                                    "reuses": reuses, "total_cost": raw["total_cost"],
                                    "prefix_arrival_events": sum(e["event"] == "prefix_arrive" for e in trace)})

try:
    for batch in BATCHES:
        audit_batch(batch)
    check(len(result["main_rows"]) == 22 and len(result["checkpoint_rows"]) == 44, "audit denominator incomplete")
    for path, expected in bindings.items():
        check(sha256(Path(path).read_bytes()).hexdigest() == expected, "artifact changed during audit")
    result["status"] = "passed"
except BaseException:
    result.update(status="failed", failure=traceback.format_exc())
finally:
    result.update(cpu_seconds=time.process_time() - cpu, wall_seconds=time.perf_counter() - wall,
                  input_sha256=bindings, audit_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  qualification="22 main raw plus 44 replay raw/checkpoint boundary audits; zero Simulation calls",
                  authorship="Adapted after reading/reviewing the Round9 audit_mechanisms.py at root request; does not call production lifecycle_report or validator; independent new source/census/manual-completion checks.")
    (OUT / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in {"input_sha256", "main_rows", "checkpoint_rows"}}, indent=2))
sys.exit(0 if result["status"] == "passed" else 1)
