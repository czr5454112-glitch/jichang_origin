"""Pure static census of original-route windows, plus separate offline receipts.

Every original job is retained. The shortest continuation after one requested
next edge is unconstrained: prefix loops are diagnosed, not silently repaired
with extra commands. Native S4 congestion can change this static prediction.
"""
from __future__ import annotations
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
from . import research_r1 as r1
from .original_workload import digest, write_json

COMMAND_DELAY = 2.


def path_cost(graph, path):
    return sum(dict(graph[u])[v] for u, v in zip(path, path[1:]))


def stage_candidates(graph, services, origin, storage):
    baseline = r1.shortest_path(graph, origin, storage)
    candidates = []
    for index, node in enumerate(baseline[:-1]):
        for target, _ in graph[node]:
            if target == baseline[index + 1]:
                continue
            tail = r1.shortest_path(graph, target, storage)
            route = baseline[:index + 1] + tail if tail else ()
            simple = bool(route) and len(set(route)) == len(route)
            topology = "no_continuation" if not tail else "simple" if simple else "prefix_revisited"
            window = "too_short" if services[node] < COMMAND_DELAY else (
                "native_same_timestamp_tie_unknown" if services[node] == COMMAND_DELAY else "positive_static_margin")
            candidates.append({"from": node, "next": target, "prefix": list(baseline[:index + 1]),
                "unconstrained_shortest_continuation": list(tail), "full_predicted_path": list(route),
                "topology_status": topology, "service_seconds": services[node],
                "command_delay_seconds": COMMAND_DELAY, "window_status": window,
                "additional_free_flow_seconds": path_cost(graph, route) - path_cost(graph, baseline) if route else None,
                "native_executable": "unknown", "business_protection": "unknown"})
    return {"origin": origin, "storage": storage, "canonical_path": list(baseline),
        "free_flow_path_seconds": path_cost(graph, baseline) if baseline else None,
        "status": "unreachable_storage" if not baseline else "no_alternative" if not candidates else "alternatives_enumerated",
        "candidate_count": len(candidates), "candidates": candidates}


def census(data):
    graph = r1.positive_graph(data)
    services = {n[0]: max(.001, n[2]) for n in data["node_records"]}
    inherited = r1.candidate_census(data)
    old_status = {r["business_bag_id"]: r["status"] for r in inherited["rows"]}
    stages, jobs = {}, []
    for job in sorted(data["jobs"], key=lambda j: (j["arrival"], j["business_bag_id"])):
        stage_key = f"{job['origin']}:{job['storage_node']}" if job["storage_node"] >= 0 else None
        if stage_key and stage_key not in stages:
            stages[stage_key] = stage_candidates(graph, services, job["origin"], job["storage_node"])
        status = old_status[job["business_bag_id"]]
        jobs.append({"business_bag_id": job["business_bag_id"], "arrival": job["arrival"],
            "origin": job["origin"], "destination": job["destination"], "storage_node": job["storage_node"],
            "original_census_status": status, "unreachable_required_stage_cohort": status == "unreachable_required_stage",
            "stage_key": stage_key, "pre_storage_status": stages[stage_key]["status"] if stage_key else "no_storage_contract"})
    unreachable = [r for r in jobs if r["unreachable_required_stage_cohort"]]
    cohort_keys = sorted({r["stage_key"] for r in unreachable if r["stage_key"]})
    weighted = Counter()
    for row in unreachable:
        if row["stage_key"]:
            for c in stages[row["stage_key"]]["candidates"]:
                weighted[f"{c['topology_status']}|{c['window_status']}"] += 1
    return {"schema": "g31.lt2.original_command_window_census.v1", "native_calls": 0,
        "selection_uses_native_outcomes": False, "offered_denominator": len(jobs), "jobs": jobs, "stages": stages,
        "original_census_counts": inherited["counts"], "unreachable_cohort_count": len(unreachable),
        "unreachable_cohort_pre_storage_counts": dict(Counter(r["pre_storage_status"] for r in unreachable)),
        "unreachable_cohort_stage_keys": cohort_keys, "unreachable_job_weighted_candidate_counts": dict(weighted),
        "unreachable_unique_stage_candidate_counts": dict(Counter(f"{c['topology_status']}|{c['window_status']}"
            for k in cohort_keys for c in stages[k]["candidates"])),
        "limits": ["Uncongested static service+travel score is not the live S4 arbitration outcome.",
            "An exact two-second tie requires native wire/control-route/dispatch ordering confirmation.",
            "A short service window may be extended by real resource congestion; no physics pause is permitted.",
            "No job is excluded from original input; no suffix permission, edge capacity, delay or FIFO rule changes."]}


def offline_receipt_diagnosis(data, report, result):
    """Outcome facts for candidate diagnosis only; never inputs to an online rule."""
    by_job = {j["business_bag_id"]: j for j in data["jobs"]}
    cohort = {r["business_bag_id"] for r in report["jobs"] if r["unreachable_required_stage_cohort"]}
    stages = report["stages"]
    arrivals, windows, storage = {}, [], []
    for receipt in result["receipts"]:
        business = receipt.get("business_bag_id")
        if business not in by_job:
            continue
        job = by_job[business]
        if receipt["event"] == "STORAGE_ENTER":
            storage.append({"business_bag_id": business, "storage_node": job["storage_node"],
                "at": receipt["time"], "unreachable_required_stage": business in cohort})
        # Only actual pre-Storage loaded movement; raw transfer/reuse events
        # never fabricate service opportunity for the original storage leg.
        if ":storage_in:" not in receipt.get("transport_leg_id", ""):
            continue
        if receipt["event"] == "EDGE_EXIT":
            arrivals[business, receipt["to"]] = receipt["time"]
        elif receipt["event"] == "EDGE_ENTER" and (business, receipt["from"]) in arrivals:
            start = arrivals.pop((business, receipt["from"]))
            candidates = stages[f"{job['origin']}:{job['storage_node']}"]["candidates"]
            relevant = [c for c in candidates if c["from"] == receipt["from"]]
            if relevant:
                duration = receipt["time"] - start
                windows.append({"business_bag_id": business, "from": receipt["from"], "actual_next": receipt["to"],
                    "arrival": start, "dispatch": receipt["time"], "actual_window_seconds": duration,
                    "margin_vs_two_seconds": duration - COMMAND_DELAY, "unreachable_required_stage": business in cohort,
                    "static_service_seconds": relevant[0]["service_seconds"],
                    "simple_alternative_next_nodes": [c["next"] for c in relevant if c["topology_status"] == "simple"],
                    "uses_offline_outcome": True})
    heads = []
    for node in sorted({s["storage_node"] for s in storage}):
        rows = sorted((s for s in storage if s["storage_node"] == node), key=lambda s: (s["at"], s["business_bag_id"]))
        head = rows[0]
        reachable = next((s for s in rows if not s["unreachable_required_stage"]), None)
        if head["unreachable_required_stage"] and reachable:
            job = by_job[head["business_bag_id"]]
            stage = stages[f"{job['origin']}:{node}"]
            required = reachable["at"] - head["at"]
            candidates = [{**c, "required_delay_to_follow_first_reachable": required,
                "free_flow_delay_suffices": c["topology_status"] == "simple" and c["additional_free_flow_seconds"] > required}
                for c in stage["candidates"]]
            heads.append({"storage": node, "actual_first_head": head, "actual_first_reachable": reachable,
                "required_strict_delay": required, "single_deviation_candidates": candidates,
                "status": "candidate_for_native_confirmation" if any(c["free_flow_delay_suffices"] for c in candidates)
                    else "no_single_simple_free_flow_candidate", "native_reordering_or_protection": "unknown"})
    return {"schema": "g31.lt2.original_window_offline_receipts.v1", "scope": "offline saved full-input prefix only",
        "advance": result.get("advance"), "population": result.get("population"),
        "static_candidate_census_precedes_this_analysis": True, "actual_storage_entries": storage,
        "actual_default_path_windows": windows, "storage_heads": heads,
        "short_service_extended_past_two_seconds": [w for w in windows if w["static_service_seconds"] < 2 and w["actual_window_seconds"] > 2],
        "unknowns": ["unobserved jobs/windows beyond saved prefix", "native exact-tie action execution", "candidate live S4 continuation and resource congestion", "full-population protection"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--saved-segment", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    data = json.load(gzip.open(args.input, "rt"))
    report = census(data)
    report["source_input"] = {"path": str(args.input.resolve()), "sha256": digest(args.input)}
    report["script_sha256"] = digest(Path(__file__))
    with gzip.open(args.output / "complete_static_census.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(report, stream, allow_nan=False)
    summary = {k: v for k, v in report.items() if k not in ("jobs", "stages")}
    write_json(args.output / "static_summary.json", summary)
    if args.saved_segment:
        raw = json.load(gzip.open(args.saved_segment, "rt"))
        if not raw.get("result"):
            raise ValueError("census:missing_saved_prefix_result")
        diagnosis = offline_receipt_diagnosis(data, report, raw["result"])
        diagnosis["source_segment"] = {"path": str(args.saved_segment.resolve()), "sha256": digest(args.saved_segment)}
        write_json(args.output / "offline_receipt_diagnosis.json", diagnosis)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
