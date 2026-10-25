"""Full-population attribution for the fixed 2-second headway experiment.

This report separates external release/admission delay from moving detours. It
does not treat counterfactual free-flow completion as an achievable joint plan.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import heapq
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN = ROOT / "outputs/experiments/g31_no_wait_20261024"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def lines(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def distances(profile, goals):
    service = {n["location"]: n["service_time"] for n in profile["nodes"]}
    reverse = defaultdict(list)
    for edge in profile["edges"]:
        reverse[edge["end"]].append((edge["start"], edge["length"] / 2 + service[edge["start"]]))
    tables = {}
    for goal in goals:
        ds, queue = {goal: 0.}, [(0., goal)]
        while queue:
            d, v = heapq.heappop(queue)
            if ds[v] != d:
                continue
            for u, cost in reverse[v]:
                if d + cost < ds.get(u, math.inf):
                    ds[u] = d + cost
                    heapq.heappush(queue, (d + cost, u))
        tables[goal] = ds
    return tables


def summarize_run(directory):
    manifest, audit = read(directory / "manifest.json"), read(directory / "audit.json")
    if manifest["status"] != "complete":
        raise ValueError(f"incomplete run: {directory}")
    rows = lines(manifest["canonical"])
    bags = {str(b["segment_id"]): b for b in lines(directory / "bags.jsonl")}
    profile = read(directory / "map.json")
    h = distances(profile, {r["goal"] for r in rows})
    groups = defaultdict(list)
    for r in rows:
        groups[r["task_id"]].append(r)
    metrics = {}
    for label, lead in (("std", 0), ("std_minus_2700", 2700)):
        categories = defaultdict(lambda: defaultdict(float))
        for legs in groups.values():
            final = next(r for r in legs if r["leg"] in ("direct", "storage_out"))
            bag = bags[str(final["segment_id"])]
            threshold = final["std"] - lead
            earliest = math.ceil(final["pass_time"])
            inbound = next((r for r in legs if r["leg"] == "storage_in"), None)
            if inbound:
                inbound_lb = math.ceil(inbound["pass_time"]) + h[inbound["goal"]][inbound["start"]]
                earliest = max(earliest, math.ceil(inbound_lb))
            lower_bound = earliest + h[final["goal"]][final["start"]]
            complete = all(bags[str(r["segment_id"])]["completed"] for r in legs)
            observed = math.ceil(bag["finish"]) if complete else math.inf
            for category in ("all", "stored" if inbound else "direct"):
                acc = categories[category]
                acc["denominator"] += 1
                acc["on_time"] += observed <= threshold
                acc["individual_free_flow_on_time_upper_bound"] += math.ceil(lower_bound - 1e-8) <= threshold
                if observed > threshold:
                    acc["late_or_unfinished"] += 1
                    if complete:
                        # Sequential decomposition under the actual inbound completion;
                        # source delay includes nominal storage holding, reported separately.
                        effective_ready = math.ceil(final["pass_time"])
                        if inbound:
                            effective_ready = max(effective_ready, math.ceil(bags[str(inbound["segment_id"])]["finish"]))
                        source_delay = bag["admission"] - effective_ready
                        free_flow = h[final["goal"]][final["start"]]
                        excess = bag["finish"] - bag["admission"] - free_flow
                        acc["late_final_segment_external_delay_seconds"] += max(0., source_delay)
                        acc["late_final_segment_moving_detour_seconds"] += max(0., excess)
                        acc["late_final_segment_free_flow_seconds"] += free_flow
        for acc in categories.values():
            acc["on_time_rate"] = acc["on_time"] / acc["denominator"]
            acc["individual_free_flow_upper_bound_rate"] = acc["individual_free_flow_on_time_upper_bound"] / acc["denominator"]
            delay = acc.get("late_final_segment_external_delay_seconds", 0)
            excess = acc.get("late_final_segment_moving_detour_seconds", 0)
            acc["external_share_of_final_segment_excess_delay"] = delay / (delay + excess) if delay + excess else None
        metrics[label] = dict(categories)
    native = read(directory / "native_summary.json")
    return dict(run=directory.name, map=manifest["map"], scale=manifest["scale"],
                binary_sha256=manifest["binary_sha256"], config=manifest["config"],
                native_wall_seconds=manifest["native_wall_seconds"],
                native_process_cpu_seconds=manifest.get("native_process_cpu_seconds"),
                event_loop_wall_seconds=native["run_wall_seconds"],
                business=audit["business"], attribution=metrics,
                source_wait=audit["external_source_wait_seconds"],
                moving_detour=audit["route_excess_over_individual_free_flow_seconds"],
                safety_passed=read(directory / "headway_audit.json")["passed"],
                transactions_passed=read(directory / ("rolling_replay.json" if (directory / "rolling_replay.json").exists() else "calendar_replay.json"))["passed"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glob", default="g31_*_1x_headway_*_002")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report = dict(schema="g31.headway.attribution.v1",
                  boundary="Individual free-flow upper bounds ignore shared capacity and cannot be achieved simultaneously in general. Attribution is descriptive, not causal identification. Source delay excludes EBS planned storage and actual predecessor readiness.",
                  runs=[summarize_run(d) for d in sorted(CAMPAIGN.glob(args.glob))])
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    for r in report["runs"]:
        print(json.dumps({k: r[k] for k in ("run", "native_wall_seconds", "attribution")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
