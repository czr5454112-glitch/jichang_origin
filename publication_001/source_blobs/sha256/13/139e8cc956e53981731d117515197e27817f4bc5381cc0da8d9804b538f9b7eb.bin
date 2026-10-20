"""Offline optimistic lower bound for one tray, one FIFO loading origin.

This is a relaxation of the declared on-carrier native contract, not another
physical simulator, an executable schedule, an online feature, or a new method.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import gzip
import hashlib
import heapq
import json
import math
from pathlib import Path

from .native_host import audit_result
from .finite_reference import outcome_cost
from .validate_analytic_control import replay_input, write


def fifo_travel_bound(data: dict, horizon: float) -> dict:
    """Inductive bound on a fixed, physically forced one-tray FIFO sequence.

    C_i >= unload_i + d(S_i,D_i) +
      max(release_i, max(arrival_i,C_(i-1)+hold_(i-1)+d(D_(i-1),O))
          + load_i + d(O,S_i) + min_dwell_i).
    Direct jobs omit Storage. For job 1 the initial empty tray is at O at t=0.
    Node service, congestion, receiving/headway waits and message delays are
    all omitted; adding any unforced wait would invalidate a lower bound.
    """
    if not math.isfinite(horizon) or horizon < 0:
        raise ValueError("single_tray_bound:invalid_horizon")
    jobs = data["jobs"]
    if len(data["trays"]) != 1 or not jobs:
        raise ValueError("single_tray_bound:requires_one_tray_nonempty_jobs")
    origin_set = {j["origin"] for j in jobs}
    if len(origin_set) != 1:
        raise ValueError("single_tray_bound:requires_one_fifo_origin")
    origin = next(iter(origin_set))
    tray = data["trays"][0]
    if tray["node"] != origin or tray.get("mode", "empty") != "empty":
        raise ValueError("single_tray_bound:requires_initial_empty_tray_at_loader")
    if len({j["business_bag_id"] for j in jobs}) != len(jobs):
        raise ValueError("single_tray_bound:duplicate_business_identity")
    # A simultaneous arrival can be loaded before another same-time arrival
    # event is observed. This narrow bound declines that ambiguity rather than
    # asserting a lexical priority unsupported by the event processing order.
    if len({j["arrival"] for j in jobs}) != len(jobs):
        raise ValueError("single_tray_bound:simultaneous_arrivals_outside_proven_scope")
    if data.get("options", {}).get("queue_discipline", "fifo") != "fifo":
        raise ValueError("single_tray_bound:non_fifo_contract")
    if data.get("options", {}).get("complete_on_goal_arrival", False):
        raise ValueError("single_tray_bound:unsupported_completion_contract")
    if any(not math.isfinite(j["arrival"]) or j["arrival"] < 0 or j["arrival"] > horizon for j in jobs):
        raise ValueError("single_tray_bound:all_jobs_must_be_offered_by_horizon")
    ordered = sorted(jobs, key=lambda j: (j["arrival"], j["business_bag_id"]))
    capacities = {(int(e["from"]), int(e["to"])): int(e["capacity"]) for e in data["edge_contracts"]}
    nodes = {int(n["node"]): n for n in data["node_contracts"]}
    if any(int(n["capacity"]) <= 0 for n in nodes.values()):
        raise ValueError("single_tray_bound:zero_node_capacity_outside_proven_scope")
    graph = defaultdict(list)
    for u, v, length, speed in data["edge_records"]:
        if not all(math.isfinite(x) for x in (length, speed)) or length < 0 or speed <= 0:
            raise ValueError("single_tray_bound:invalid_edge_travel")
        if (u, v) not in capacities:
            raise ValueError("single_tray_bound:missing_edge_capacity_contract")
        if capacities[u, v] > 0:
            # Native minimum-travel rounding is nonnegative and may safely be
            # relaxed; use the original length/speed rather than inventing it.
            graph[u].append((v, float(length)/float(speed)))
    cache = {}
    def shortest(source, target):
        key = source, target
        if key in cache:
            return cache[key]
        queue = [(0., source, (source,))]
        best = {source: 0.}
        while queue:
            value, node, path = heapq.heappop(queue)
            if value > best[node]:
                continue
            if node == target:
                cache[key] = value, list(path)
                return cache[key]
            for next_node, travel in graph[node]:
                cost = value + travel
                if cost < best.get(next_node, math.inf):
                    best[next_node] = cost
                    heapq.heappush(queue, (cost, next_node, path+(next_node,)))
        raise ValueError(f"single_tray_bound:no_positive_capacity_directed_path:{source}:{target}")

    rows, ready = [], 0.
    for index, job in enumerate(ordered):
        for field in ("load_seconds", "unload_seconds", "hold_seconds", "storage_min_dwell", "storage_release_at"):
            value = job.get(field, 0.)
            if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError("single_tray_bound:invalid_physical_duration_or_release")
        start = max(float(job["arrival"]), ready)
        loaded = start + job.get("load_seconds", 0.)
        destination = int(job["destination"])
        storage = int(job.get("storage_node", -1))
        storage_arrival, release = None, None
        if storage >= 0:
            first_time, first_path = shortest(origin, storage)
            last_time, last_path = shortest(storage, destination)
            storage_arrival = loaded + first_time
            release = max(storage_arrival + job.get("storage_min_dwell", 0.), job.get("storage_release_at", 0.))
            finish = release + last_time + job.get("unload_seconds", 0.)
            paths = {"loaded_to_storage": first_path, "storage_to_destination": last_path}
        else:
            last_time, last_path = shortest(origin, destination)
            finish = loaded + last_time + job.get("unload_seconds", 0.)
            paths = {"loaded_direct": last_path}
        return_time, return_path = shortest(destination, origin) if index+1 < len(ordered) else (0., [])
        # No return is required after the final business completion. Do not
        # label its terminal hold completion as arrival back at the loader.
        ready = finish + job.get("hold_seconds", 0.) + return_time if index+1 < len(ordered) else None
        deadline = float(job.get("deadline", -1.))
        rows.append({"sequence": index+1, "business_bag_id": job["business_bag_id"], "tray_id": tray["tray_id"],
            "arrival": job["arrival"], "deadline": deadline, "origin": origin, "destination": destination,
            "load_start_lower_bound": start, "load_complete_lower_bound": loaded,
            "storage_entry_lower_bound": storage_arrival, "storage_release_lower_bound": release,
            "completion_lower_bound": finish, "next_loader_ready_lower_bound": ready,
            "hold_seconds": job.get("hold_seconds", 0.), "return_travel_lower_bound": return_time,
            "positive_capacity_directed_paths": dict(paths, return_to_loader=return_path),
            "restricted_sojourn_lower_bound": min(horizon, finish)-job["arrival"],
            "unavoidable_deadline_miss": deadline >= 0 and finish > deadline+1e-8})
    return {"schema": "g31.single_tray_fifo_travel_lower_bound.v1", "status": "bounded_relaxation",
        "scope": "one initially empty tray at one FIFO loader; distinct arrivals; on-carrier Storage; all specified jobs",
        "horizon": horizon, "offered": len(rows), "rows": rows,
        "restricted_sojourn_lower_bound": sum(r["restricted_sojourn_lower_bound"] for r in rows),
        "minimum_deadline_misses": sum(r["unavoidable_deadline_miss"] for r in rows),
        "deadline_count_scope": "necessary eventual deadline misses; also by-H violations only when all declared deadlines are at or before H",
        "all_declared_deadlines_at_or_before_horizon": all(r["deadline"] < 0 or r["deadline"] <= horizon for r in rows),
        "relaxed_nonnegative_terms": ["node service", "receiving/congestion/headway waits", "control compute and message delays", "fault waiting"],
        "not_claimed": ["feasible schedule", "attainable optimum", "multi-tray bound", "full mother-stream bound", "online score", "method novelty"]}


def check_actual(bound: dict, result: dict, data: dict) -> dict:
    expected = [r["business_bag_id"] for r in bound["rows"]]
    loading = [r for r in result["receipts"] if r["event"] == "LOAD_START"]
    if [r["business_bag_id"] for r in loading] != expected:
        raise ValueError("single_tray_bound:actual_loading_sequence_does_not_match_proven_fifo_scope")
    tray_id = data["trays"][0]["tray_id"]
    if any(r["tray_id"] != tray_id for r in loading):
        raise ValueError("single_tray_bound:actual_second_tray")
    completed = {j["business_bag_id"]: j for j in result["jobs"]}
    gaps = []
    for row in bound["rows"]:
        job = completed[row["business_bag_id"]]
        actual = job["completed_at"]
        if actual < 0:
            raise ValueError("single_tray_bound:actual_comparison_requires_all_jobs_completed")
        if actual+1e-7 < row["completion_lower_bound"]:
            raise ValueError("single_tray_bound:bound_exceeds_actual_completion")
        gaps.append({"business_bag_id": row["business_bag_id"], "completion_at": actual,
                     "completion_lower_bound": row["completion_lower_bound"],
                     "completion_gap_seconds": actual-row["completion_lower_bound"]})
    metrics = outcome_cost(result, data["jobs"], bound["horizon"])
    return {"metrics": metrics, "actual_fifo_order_verified": True,
            "all_jobs_at_or_after_lower_bound": True, "rows": gaps,
            "restricted_sojourn_gap_to_lower_bound": metrics["cost"]-bound["restricted_sojourn_lower_bound"],
            "relative_gap_of_actual_cost": (metrics["cost"]-bound["restricted_sojourn_lower_bound"])/metrics["cost"],
            "actual_deadline_misses": metrics["deadline_violations"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mechanism", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))
    data = load(args.mechanism/"input.json")
    if data != load(args.reference/"input.json"):
        raise ValueError("single_tray_bound:reference_physical_input_differs")
    horizon = float(data["options"]["max_simulation_time"])
    bound = fifo_travel_bound(data, horizon)
    crosswalk_path = args.mechanism/"mother_crosswalk_selection.jsonl.gz"
    with gzip.open(crosswalk_path, "rt", encoding="utf-8") as source:
        crosswalk = [json.loads(line) for line in source]
    selected = {r["business_bag_id"]: r for r in crosswalk if r["selected_for_witness"]}
    if set(selected) != {r["business_bag_id"] for r in bound["rows"]}:
        raise ValueError("single_tray_bound:selected_crosswalk_does_not_cover_exact_input")
    for row in bound["rows"]:
        row["mother_crosswalk"] = selected[row["business_bag_id"]]
    comparisons, audits = {}, {}
    event_table = load(args.mechanism/"actual_same_tray_event_table.json")
    artifacts = [args.mechanism/"input.json", args.mechanism/"selection.json", crosswalk_path,
                 args.mechanism/"actual_same_tray_event_table.json", args.reference/"input.json",
                 args.reference/"finite_reference_raw.json.gz", args.reference/"public_boundary_and_domain.json",
                 Path(__file__), Path("cpp/ics_core/runtime/circulation_runtime_impl.hpp")]
    for policy in ("reactive", "predictive"):
        path = args.mechanism/f"{policy}_raw.json.gz"; artifacts.append(path)
        with gzip.open(path, "rt", encoding="utf-8") as source:
            run = json.load(source)
        if hashlib.sha256(path.read_bytes()).hexdigest() != event_table["source_hashes"][path.name]:
            raise ValueError("single_tray_bound:actual_event_table_source_hash_mismatch")
        result = run["result"]
        comparisons[policy] = check_actual(bound, result, data)
        table_rows = event_table["policies"][policy]["rows"]
        if [r["business_bag_id"] for r in table_rows] != [r["business_bag_id"] for r in bound["rows"]]:
            raise ValueError("single_tray_bound:actual_event_table_order_mismatch")
        outcomes = {j["business_bag_id"]: j for j in result["jobs"]}
        if any(abs(r["unload_complete_at"]-outcomes[r["business_bag_id"]]["completed_at"]) > 1e-8 for r in table_rows):
            raise ValueError("single_tray_bound:actual_event_table_time_mismatch")
        audits[policy] = audit_result(replay_input(data, run["submitted"]), result)
    with gzip.open(args.reference/"finite_reference_raw.json.gz", "rt", encoding="utf-8") as source:
        reference = json.load(source)
    original_boundary = load(args.reference/"public_boundary_and_domain.json")
    for row in reference["rows"]:
        result, action = row["result"], row["action"]
        if result["advance"].get("horizon_complete") is not True or result["physical_clock"] != horizon:
            raise ValueError("single_tray_bound:reference_horizon_incomplete")
        name = "native006_first_return_reference:"+action["action_id"]
        comparisons[name] = check_actual(bound, result, data)
        submitted = original_boundary["prefix_submitted"]+result["offline_continuation_submitted"]
        if action["kind"] == "transfer":
            submitted += [{"request": action["request"], "reply": {"status": "pending"}}]
        audits[name] = audit_result(replay_input(data, submitted), result)
    receipt = {"schema": "g31.single_tray_lower_bound_audit.v1", "status": "passed", "bound": bound,
        "comparisons": comparisons, "independent_physical_audits": audits,
        "source_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts},
        "mother_crosswalk_rows_preserved_by_reference": len(crosswalk),
        "proof": "Unique physical tray remains loaded through Storage until unloading. Automatic loader grants oldest observed arrival before discretionary export. Distinct arrivals and common loader force the sorted sequence; every observed actual LOAD_START matches it. Induction: every actual nonnegative travel/wait is at least the positive-capacity directed free-travel bound; mandatory load, unload, hold, Storage absolute release and dwell remain.",
        "claim_boundary": "Offline bound for all 24 jobs of this separate one-tray mechanism factor only. It neither excuses deadline misses nor changes requirements; optimistic gap is not certified achievable headroom or global optimality."}
    write(args.output/"receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "offered": bound["offered"],
        "lower_bound": bound["restricted_sojourn_lower_bound"], "minimum_deadline_misses": bound["minimum_deadline_misses"],
        "actual_costs": {k:v["metrics"]["cost"] for k,v in comparisons.items()}}))


if __name__ == "__main__":
    main()
