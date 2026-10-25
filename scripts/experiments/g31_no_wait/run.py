"""Isolated continuous-motion G31 research candidate; full population only.

Local scoring and a complete continuation certificate are different operations.
This runner never replaces the existing G31 standard or changes arrival/STD data.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import heapq
import importlib.util
import json
import math
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_no_wait.replay import replay_calendar

CAMPAIGN = ROOT / "outputs/experiments/g31_no_wait_20261024"
DRAFT = ROOT / "outputs/experiments/g31_nonstop_contract_20261024_draft001/contract_manifest.json"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False,
                                    allow_nan=False) + "\n", encoding="utf-8")


def process_memory_snapshot():
    """Read this process's Windows working-set peak without sampling overhead."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    current = ctypes.windll.kernel32.GetCurrentProcess
    current.restype = wintypes.HANDLE
    query = ctypes.windll.psapi.GetProcessMemoryInfo
    query.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    query.restype = wintypes.BOOL
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    if not query(current(), ctypes.byref(counters), counters.cb):
        return {"status": "unavailable"}
    return {"peak_working_set_bytes": counters.PeakWorkingSetSize,
            "current_working_set_bytes": counters.WorkingSetSize,
            "peak_pagefile_usage_bytes": counters.PeakPagefileUsage,
            "scope": "Entire Python worker process since creation, including native payload conversion."}


def quantile(values, p):
    if not values:
        return None
    values = sorted(values)
    at = (len(values) - 1) * p
    lo = int(at)
    hi = min(lo + 1, len(values) - 1)
    return values[lo] + (at - lo) * (values[hi] - values[lo])


def distribution(values):
    return {"count": len(values), "mean": sum(values) / len(values) if values else None,
            "p50": quantile(values, .5), "p95": quantile(values, .95),
            "p99": quantile(values, .99), "max": max(values) if values else None}


def normalize_route(route):
    """Native route points use (node, arrival, departure), including endpoints."""
    return [(int(p[0]), float(p[1]), float(p[2])) for p in route]


def audit(rows, bags, profile, *, horizon=98259.0, interval_mode="closed_legacy",
          strict_endpoint_resources=False):
    """Independent replay: continuity, service, resource overlap, full denominator.

    Endpoint exemption follows original Java HCA and is reported separately. A
    passing internal-only audit is NOT a proof of source/terminal equipment safety.
    """
    source = {str(r["segment_id"]): r for r in rows}
    actual = {str(b["segment_id"]): b for b in bags}
    if len(source) != len(rows) or len(actual) != len(bags) or source.keys() != actual.keys():
        raise ValueError("full canonical segment identity changed")
    service = {int(n["location"]): float(n["service_time"]) for n in profile["nodes"]}
    travel = {(int(e["start"]), int(e["end"])): float(e["length"]) / 2.0 for e in profile["edges"]}
    reverse = defaultdict(list)
    for (u, v), cost in travel.items():
        reverse[v].append((u, cost + service[u]))
    potentials = {}
    for goal in {int(r["goal"]) for r in rows}:
        distances = {goal: 0.0}
        queue = [(0.0, goal)]
        while queue:
            distance, v = heapq.heappop(queue)
            if distance != distances[v]:
                continue
            for u, cost in reverse[v]:
                candidate = distance + cost
                if candidate < distances.get(u, math.inf):
                    distances[u] = candidate
                    heapq.heappush(queue, (candidate, u))
        potentials[goal] = distances
    resources = defaultdict(list)
    violations = []
    wait_max = 0.0
    wait_sum = 0.0
    repeated = 0
    external = []
    in_network = []
    detours = []
    business = defaultdict(list)
    planned = 0
    completed = 0
    eps = 1e-7
    for sid, r in source.items():
        b = actual[sid]
        for name, expected in (("task_id", r["task_id"]), ("leg", r["leg"]),
                               ("start", r["start"]), ("goal", r["goal"]),
                               ("release", r["pass_time"]), ("deadline", r["std"])):
            if name in b and b[name] != expected:
                violations.append([sid, "input_identity_changed", name])
        route = normalize_route(b.get("route", []))
        finish = None
        admission = None
        if route:
            planned += 1
            admission = route[0][1]
            finish = route[-1][1]
            if route[0][0] != r["start"] or route[-1][0] != r["goal"]:
                violations.append([sid, "endpoints"])
            if admission + eps < float(r["pass_time"]):
                violations.append([sid, "admitted_before_release"])
            external.append(admission - float(r["pass_time"]))
            in_network.append(finish - admission)
            lower_bound = potentials[r["goal"]].get(r["start"], math.inf)
            detours.append(finish - admission - lower_bound)
            if finish - admission + eps < lower_bound:
                violations.append([sid, "faster_than_free_flow_bound"])
            repeated += int(len({p[0] for p in route}) != len(route))
            if abs(float(b["admission"]) - admission) > eps or abs(float(b["finish"]) - finish) > eps:
                violations.append([sid, "reported_time_mismatch"])
            if "source_wait_seconds" in b and abs(float(b["source_wait_seconds"])-(admission-float(r["pass_time"]))) > eps:
                violations.append([sid, "source_wait_mismatch"])
            for i, (node, arrival, departure) in enumerate(route):
                if not all(math.isfinite(v) for v in (arrival, departure)):
                    violations.append([sid, "nonfinite_time"])
                    continue
                expected = service[node]
                # Last point can include a legacy terminal reservation, but the
                # transported bag completes on arrival and does not wait there.
                if i != len(route) - 1 and abs(departure - arrival - expected) > eps:
                    violations.append([sid, "incorrect_service", node])
                if i == len(route) - 1 and min(abs(departure-arrival), abs(departure-arrival-expected)) > eps:
                    violations.append([sid, "incorrect_terminal_reservation", node])
                resources[node].append((arrival, departure, sid, 0 < i < len(route)-1,
                                        admission, finish))
                if i:
                    previous = route[i-1]
                    edge = (previous[0], node)
                    if edge not in travel:
                        violations.append([sid, "missing_edge", edge])
                        continue
                    residual = arrival - previous[2] - travel[edge]
                    if abs(residual) > eps:
                        violations.append([sid, "internal_wait_or_teleport", node, residual])
                    wait_max = max(wait_max, max(0.0, residual))
                    wait_sum += max(0.0, residual)
        is_complete = bool(route) and finish <= horizon + eps
        if bool(b.get("completed")) != is_complete:
            violations.append([sid, "completion_flag"])
        completed += is_complete
        business[int(r["task_id"])].append({"leg": r["leg"], "completed": is_complete,
                    "finish": finish, "admission": admission, "deadline": float(r["std"])})
    internal_overlap = []
    endpoint_overlap = 0
    # Sweep all overlapping closed intervals, not just adjacent pairs: source and
    # terminal intervals may overlap each other and hide an internal pair.
    for node, intervals in resources.items():
        active = []
        for interval in sorted(intervals):
            a, d, sid, internal, admission, finish = interval
            if interval_mode == "half_open":
                if round(d*1e6) <= round(a*1e6):
                    continue
                active = [p for p in active if round(p[1]*1e6) > round(a*1e6)]
            else:
                active = [p for p in active if p[1] >= a]
            for prior in active:
                if prior[2] == sid:
                    continue
                if internal and prior[3]:
                    internal_overlap.append([node, prior[2], sid, prior[:2], interval[:2]])
                else:
                    endpoint_overlap += 1
            active.append(interval)
    counts = defaultdict(int)
    for task, legs in business.items():
        deadlines = {p["deadline"] for p in legs}
        if len(deadlines) != 1:
            raise ValueError(f"inconsistent business deadline: {task}")
        final = [p for p in legs if p["leg"] in ("direct", "storage_out")]
        if len(final) != 1:
            raise ValueError(f"invalid final segment: {task}")
        final = final[0]
        complete = all(p["completed"] for p in legs)
        causal = True
        ins = [p for p in legs if p["leg"] == "storage_in"]
        if ins:
            causal = bool(ins[0]["completed"] and final["admission"] is not None
                          and ins[0]["finish"] <= final["admission"] + eps)
        counts["completed"] += complete
        counts["causally_invalid_completed"] += complete and not causal
        counts["causally_invalid_admitted"] += final["admission"] is not None and not causal
        for label, lead in (("std", 0.0), ("std_minus_2700", 2700.0)):
            ontime = complete and final["finish"] <= final["deadline"] - lead
            counts[label] += ontime
            counts[label + "_strict_causal"] += ontime and causal
            # Shared integer observation removes an advantage from continuous
            # event reporting when comparing with the original Java lifecycle.
            counts[label + "_integer_observed_strict_causal"] += (
                complete and causal and math.ceil(final["finish"]) <= final["deadline"]-lead)
    denominator = len(business)
    return {
        "schema": "g31.nowait.independent_audit.v1", "horizon": horizon,
        "segments": {"denominator": len(rows), "planned": planned, "completed": completed,
                     "unfinished": len(rows)-completed},
        "business": {"denominator": denominator, "counts": dict(counts),
                     "rates": {k: v / denominator for k,v in counts.items()}},
        "safety": {"route_violations": len(violations), "violation_examples": violations[:20],
                   "internal_internal_closed_interval_overlaps": len(internal_overlap),
                   "interval_mode": interval_mode,
                   "internal_internal_interval_overlaps": len(internal_overlap),
                   "overlap_examples": internal_overlap[:20], "endpoint_exempt_overlaps": endpoint_overlap,
                   "internal_extra_wait_max_seconds": wait_max, "internal_extra_wait_sum_seconds": wait_sum,
                   "routes_with_repeated_nodes": repeated,
                   "boundary": ("Route continuity and service ledger; all-device/edge spacing additionally checked by headway_audit.json."
                       if strict_endpoint_resources else "Node service calendars only; original HCA endpoint exemption explicitly retained; conveyor geometric headway not modeled.")},
        "external_source_wait_seconds": distribution(external),
        "in_network_seconds": distribution(in_network),
        "route_excess_over_individual_free_flow_seconds": distribution(detours),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", choices=("map2", "nanning"), required=True)
    parser.add_argument("--scale", type=int, choices=(1,2), required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise FileExistsError(f"refusing to overwrite evidence: {out}")
    contract = json.loads(DRAFT.read_text(encoding="utf-8"))
    cell = contract["cells"][f"{args.map}_{args.scale}x"]
    canonical = Path(cell["canonical"]["path"])
    profile_path = Path(contract["maps"][args.map]["draft_profile"]["path"])
    if digest(canonical) != cell["canonical"]["sha256"]:
        raise ValueError("canonical population hash mismatch")
    if digest(profile_path) != contract["maps"][args.map]["draft_profile"]["sha256"]:
        raise ValueError("shared service2 graph hash mismatch")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    rows = [json.loads(s) for s in canonical.read_text(encoding="utf-8").splitlines() if s.strip()]
    if len(rows) != cell["segment_denominator"] or len({r["task_id"] for r in rows}) != cell["business_denominator"]:
        raise ValueError("population denominator mismatch")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    config.setdefault("end_time", 98259.0)
    nodes = [(n["location"], n["service_time"]) for n in profile["nodes"]]
    edges = [(e["start"], e["end"], e["length"]/2.0) for e in profile["edges"]]
    tasks = [{"segment_id": r["segment_id"], "task_id": r["task_id"],
              "release": r["pass_time"], "deadline": r["std"], "start": r["start"],
              "goal": r["goal"], "leg": r["leg"]} for r in rows]
    binary = args.binary.resolve(strict=True)
    build_root = binary.parent.parent
    build_receipt = json.loads((build_root / "build_receipt.json").read_text(encoding="utf-8"))
    if build_receipt.get("status") != "complete" or digest(binary) not in build_receipt.get("binaries", {}).values():
        raise ValueError("binary does not match a completed immutable build")
    for filename, expected in build_receipt["source_sha256"].items():
        if digest(build_root / "source" / filename) != expected:
            raise ValueError("frozen build source changed")
    out.mkdir(parents=True)
    frozen = out / "source"
    frozen.mkdir()
    rolling_enabled = bool(config.get("enable_inroute_replanning", False))
    sources = [Path(__file__), Path(__file__).with_name("replay.py"),
               Path(__file__).with_name("headway_audit.py"),
               Path(__file__).with_name("tht_metrics.py"),
               build_root / "source/core.cpp", build_root / "source/CMakeLists.txt"]
    if rolling_enabled:
        sources.append(Path(__file__).with_name("rolling_replay.py"))
    canonical_fifo = config.get("source_fifo_order") == "canonical"
    if canonical_fifo:
        sources.append(Path(__file__).with_name("source_policy_audit.py"))
    for source_path in sources:
        shutil.copyfile(source_path, frozen / source_path.name)
    shutil.copyfile(build_root / "build_receipt.json", out / "build_receipt.json")
    write(out / "config.json", config)
    shutil.copyfile(profile_path, out / "map.json")
    manifest = {"schema": "g31.nowait.run.v1", "status": "prepared", "map": args.map,
                "scale": args.scale, "canonical": str(canonical), "canonical_sha256": digest(canonical),
                "profile_sha256": digest(profile_path), "binary": str(binary), "binary_sha256": digest(binary),
                "source_sha256": {p.name: digest(p) for p in frozen.iterdir()},
                "config": config, "task_count": len(tasks), "argv": sys.argv,
                "claim_boundary": (
                    "In-network next-hop scoring with atomic continuous-motion suffix replacement and a retained full continuation certificate. Safety requests may extend to the goal; real network concurrency and communication latency are not simulated."
                    if rolling_enabled else
                    "Local adaptive scoring + complete continuation certificate prototype, not yet dynamic rolling replanning; no change to G31 standard.")}
    write(out / "manifest.json", manifest)
    spec = importlib.util.spec_from_file_location("g31_nowait", binary)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    start = time.perf_counter()
    cpu_start = time.process_time()
    try:
        manifest["status"] = "running"
        write(out / "manifest.json", manifest)
        print(json.dumps({"status": "running", "map": args.map, "scale": args.scale}), flush=True)
        payload = module.plan(nodes, edges, tasks, config)
        elapsed = time.perf_counter() - start
        cpu_elapsed = time.process_time() - cpu_start
        native_memory = process_memory_snapshot()
        with (out / "bags.jsonl").open("w", encoding="utf-8") as stream:
            for bag in payload["bags"]:
                stream.write(json.dumps(bag, ensure_ascii=False, allow_nan=False) + "\n")
        write(out / "native_summary.json", payload["summary"])
        if rolling_enabled:
            with (out / "rolling_events.jsonl").open("w", encoding="utf-8") as stream:
                for event in payload["rolling_events"]:
                    stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        if payload["summary"].get("event_budget_exhausted"):
            raise ValueError("simulation event budget exhausted; no full-horizon performance claim")
        result = audit(rows, payload["bags"], profile, horizon=config["end_time"],
                       interval_mode=config.get("interval_mode", "closed_legacy"),
                       strict_endpoint_resources=config.get("strict_endpoint_resources", False))
        write(out / "audit.json", result)
        from scripts.experiments.g31_no_wait.tht_metrics import audit_tht
        tht = audit_tht(rows, payload["bags"], horizon=config["end_time"])
        write(out / "tht_audit.json", tht)
        if not tht["passed"]:
            raise ValueError("full-population THT telemetry audit failed")
        if rolling_enabled and tht.get("missing_first_planning_attempt_segments"):
            raise ValueError("primary THT requires explicit first-planning-entry telemetry; use native004 or later")
        if canonical_fifo:
            from scripts.experiments.g31_no_wait.source_policy_audit import audit_source_policy
            source_policy = audit_source_policy(rows, payload["bags"],
                source_generation_interval=config.get("source_generation_interval", 1),
                release_quantum=config.get("release_quantum", 1),
                source_fifo_order="canonical")
            write(out / "source_policy_audit.json", source_policy)
            if not source_policy["passed"]:
                raise ValueError("independent canonical source FIFO replay failed")
        headway = None
        if config.get("interval_mode") == "half_open":
            from scripts.experiments.g31_no_wait.headway_audit import audit_headway
            headway = audit_headway(rows, payload["bags"], profile,
                        time_grid_seconds=config.get("time_grid_seconds", 1e-6),
                        strict_endpoint_resources=config.get("strict_endpoint_resources", False),
                        edge_entry_headway_seconds=config.get("edge_entry_headway_seconds", 0))
            write(out / "headway_audit.json", headway)
            if rolling_enabled:
                from scripts.experiments.g31_no_wait.rolling_replay import replay_rolling
                replay = replay_rolling(rows, payload["bags"], profile, payload["rolling_events"],
                            time_grid_seconds=config.get("time_grid_seconds", 1e-6),
                            edge_entry_headway_seconds=config.get("edge_entry_headway_seconds", 0),
                            horizon=config["end_time"], require_nonincreasing_finish=True)
            else:
                replay = replay_calendar(rows, payload["bags"], interval_mode="half_open",
                            time_grid_seconds=config.get("time_grid_seconds", 1e-6),
                            endpoint_policy="all_nodes" if config.get("strict_endpoint_resources") else "hca_query_exempt",
                            cleanup_field="resource_cleanup_epoch",
                            edge_entry_headway_seconds=config.get("edge_entry_headway_seconds", 0))
        else:
            replay = replay_calendar(rows, payload["bags"])
        write(out / ("rolling_replay.json" if rolling_enabled else "calendar_replay.json"), replay)
        if digest(binary) != manifest["binary_sha256"]:
            raise ValueError("binary changed during execution")
        for source_path in sources:
            if digest(source_path) != manifest["source_sha256"][source_path.name]:
                raise ValueError("runner or auditor source changed during execution")
        if (result["safety"]["route_violations"] or result["safety"]["internal_internal_closed_interval_overlaps"]
                or result["safety"]["routes_with_repeated_nodes"]):
            raise ValueError("independent no-wait replay failed")
        if config.get("enable_ebs_predecessor_gate") and result["business"]["counts"]["causally_invalid_admitted"]:
            raise ValueError("causal EBS admission gate failed")
        if not replay["passed"]:
            raise ValueError("independent commit-order reservation replay failed")
        if headway is not None and not headway["passed"]:
            raise ValueError("independent integer node/edge headway replay failed")
        manifest.update(status="complete", native_wall_seconds=elapsed,
                        native_process_cpu_seconds=cpu_elapsed,
                        memory_after_native_api=native_memory,
                        memory_after_independent_audits=process_memory_snapshot(),
                        cpu_measurement="Python time.process_time around native API (includes conversion/preprocessing); legacy native std::clock field is not a Windows CPU measure.",
                        bags_sha256=digest(out / "bags.jsonl"))
        write(out / "manifest.json", manifest)
        print(json.dumps({"status": "complete", "seconds": elapsed,
                          "user_tht_mean_seconds": tht["user_tht_mean_per_business_seconds"],
                          "network_elapsed_mean_seconds": tht["paper_tht_mean_per_business_seconds"],
                          "business": result["business"],
                          "safety": result["safety"]}), flush=True)
    except BaseException as exc:
        manifest.update(status="failed", error=repr(exc), elapsed_seconds=time.perf_counter()-start)
        write(out / "manifest.json", manifest)
        raise


if __name__ == "__main__":
    main()
