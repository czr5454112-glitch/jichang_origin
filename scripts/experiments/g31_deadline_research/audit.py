"""Full-denominator G31 deadline audit; no runtime or policy changes.

STD is the input deadline, not a completion rate.  The old max-leg finish
measure, final-delivery observation, and causally valid delivery are separate.
Merge grant wait overlaps junction wait and is never added a second time.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import heapq
import json
import math
from pathlib import Path
import statistics

EPS = 1e-7


def read_json(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def read_jsonl(path):
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def distribution(values):
    values = sorted(float(v) for v in values if v is not None)
    if not values:
        return {"count": 0, "sum": 0.0, "mean": None, "min": None,
                "p50": None, "p95": None, "p99": None, "max": None}
    def q(p):
        index = p * (len(values) - 1)
        left = int(index)
        return values[left] + (values[min(left + 1, len(values)-1)] - values[left]) * (index-left)
    return {"count": len(values), "sum": math.fsum(values), "mean": statistics.fmean(values),
            "min": values[0], "p50": q(.5), "p95": q(.95), "p99": q(.99), "max": values[-1]}


def _number(row, *keys):
    for key in keys:
        if row.get(key) is not None:
            value = float(row[key])
            if not math.isfinite(value):
                raise ValueError(f"non-finite {key}")
            return value
    return None


def _index(rows, label):
    result = {}
    for row in rows:
        sid = str(row["segment_id"])
        if sid in result:
            raise ValueError(f"duplicate {label} segment: {sid}")
        result[sid] = row
    return result


def _free_flow(request, goals):
    """Independent Dijkstra bound: service(source)+edge travel, no congestion.

    Original graph ignores faults and is optimistic even for fault experiments.
    This is a lower bound, never an achievable scheduler or congestion capacity.
    """
    minimum = float(request.get("minimum_service_seconds", 0.0))
    service = {int(r[0]): max(float(r[2]), minimum) for r in request["node_records"]}
    reverse = defaultdict(list)
    for edge in request["edge_records"]:
        src, dst, length, speed = int(edge[0]), int(edge[1]), float(edge[2]), float(edge[3])
        if length < 0 or speed <= 0 or service[src] < 0:
            raise ValueError("invalid graph cost")
        reverse[dst].append((src, service[src] + length / speed))
    result = {}
    for goal in goals:
        initial = 0.0 if request.get("complete_on_goal_arrival", True) else service[goal]
        distances, queue = {goal: initial}, [(initial, goal)]
        while queue:
            cost, node = heapq.heappop(queue)
            if cost != distances[node]:
                continue
            for src, weight in reverse[node]:
                candidate = cost + weight
                if candidate < distances.get(src, math.inf):
                    distances[src] = candidate
                    heapq.heappush(queue, (candidate, src))
        result[goal] = distances
    return result


def _rate(count, denominator):
    return {"count": count, "denominator": denominator,
            "rate": count / denominator if denominator else None}


def _summary(rows, *, business=False):
    total = len(rows)
    result = {"offered": total, "completed": sum(r["completed"] for r in rows),
              "unfinished": sum(not r["completed"] for r in rows),
              "completed_late": sum(r["completed"] and not r["on_time"] for r in rows),
              "on_time": _rate(sum(r["on_time"] for r in rows), total),
              "literal_std_minus_2700": _rate(sum(r["on_time_minus_2700"] for r in rows), total),
              "unfinished_deadline_elapsed": sum(r["unfinished_deadline_elapsed"] for r in rows),
              "lateness_seconds_completed_subset": distribution(r["lateness_seconds"] for r in rows)}
    if business:
        result.update({"on_time_causally_valid": _rate(sum(r["on_time"] and r["ebs_causal"] is True for r in rows), total),
                       "old_all_segments_finish_le_std": _rate(sum(r["old_max_segment_on_time"] for r in rows), total),
                       "literal_std_minus_2700_causally_valid": _rate(sum(r["on_time_minus_2700"] and r["ebs_causal"] is True for r in rows), total),
                       "old_all_segments_finish_le_std_minus_2700": _rate(sum(r["old_max_segment_on_time_minus_2700"] for r in rows), total),
                       "ebs_causality_violations": sum(r["ebs_causal"] is False for r in rows),
                       "ebs_causality_unobserved": sum(r["ebs_causal"] is None for r in rows),
                       "free_flow_infeasible_at_canonical_release": sum(r["free_flow_infeasible"] for r in rows),
                       "already_late_at_final_release": sum(r["already_late_at_release"] for r in rows)})
    return result


def _groups(rows, key, *, business=False):
    groups = defaultdict(list)
    for row in rows:
        groups[str(row[key])].append(row)
    return {name: _summary(group, business=business) for name, group in sorted(groups.items())}


def _components(rows):
    names = ("source_queue_seconds", "junction_queue_seconds", "merge_grant_wait_overlapping_seconds",
             "travel_seconds", "service_seconds", "total_local_wait_overlapping_seconds",
             "elapsed_from_release_seconds", "unattributed_residual_seconds")
    return {name: distribution(row[name] for row in rows) for name in names}


def analyze(canonical_rows, bag_rows, request):
    expected, observed = _index(canonical_rows, "canonical"), _index(bag_rows, "output")
    if set(observed) - set(expected):
        raise ValueError("unexpected output segment outside fixed denominator")
    horizon = float(request["max_simulation_time"])
    free = _free_flow(request, {int(r["goal"]) for r in canonical_rows})
    segments, grouped = [], defaultdict(list)
    for sid, source in expected.items():
        raw = observed.get(sid, {})
        for key in ("task_id", "start", "goal"):
            if key in raw and int(raw[key]) != int(source[key]):
                raise ValueError(f"identity/OD mismatch: {sid} {key}")
        deadline, scheduled = float(source["std"]), float(source["pass_time"])
        if "deadline" in raw and float(raw["deadline"]) != deadline:
            raise ValueError(f"deadline mismatch: {sid}")
        release = _number(raw, "release_time", "released")
        admitted = _number(raw, "admitted_time", "entered")
        if admitted is not None and admitted < 0:
            admitted = None
        complete = bool(raw.get("completed", False))
        finish = _number(raw, "finish_time", "finish") if complete else None
        if complete and (finish is None or finish > horizon + EPS):
            raise ValueError(f"invalid completed finish: {sid}")
        if admitted is not None and release is not None and admitted < release - EPS:
            raise ValueError(f"admission before release: {sid}")
        if complete and any(t is not None and finish < t - EPS for t in (release, admitted)):
            raise ValueError(f"finish before release/admission: {sid}")
        source_queue = _number(raw, "source_queue_delay", "reported_source_queue_delay")
        junction = _number(raw, "junction_queue_wait_seconds")
        merge = _number(raw, "merge_grant_wait_seconds")
        travel = _number(raw, "edge_travel_time_seconds", "reported_edge_travel_seconds")
        service = _number(raw, "node_service_time_seconds", "reported_node_service_seconds")
        elapsed = finish - release if complete and release is not None else None
        pieces = (source_queue, junction, travel, service)
        residual = elapsed - math.fsum(pieces) if elapsed is not None and all(x is not None for x in pieces) else None
        h = free[int(source["goal"])].get(int(source["start"]))
        row = {"segment_id": sid, "task_id": int(source["task_id"]), "leg": source["leg"],
               "start": int(source["start"]), "goal": int(source["goal"]),
               "od": f'{source["start"]}->{source["goal"]}',
               "std_hour": int(deadline // 3600), "deadline": deadline, "canonical_pass_time": scheduled,
               "release_time": release, "admitted_time": admitted, "finish_time": finish,
               "completed": complete, "output_present": sid in observed,
               "on_time": complete and finish <= deadline,
               "on_time_minus_2700": complete and finish <= deadline - 2700,
               "unfinished_deadline_elapsed": not complete and deadline <= horizon,
               "lateness_seconds": max(0.0, finish-deadline) if complete else None,
               "free_flow_seconds": h, "free_flow_finish_from_canonical": scheduled+h if h is not None else None,
               "free_flow_infeasible": h is None or scheduled+h > deadline,
               "already_late_at_release": release is not None and release > deadline,
               "already_late_at_admission": admitted is not None and admitted > deadline,
               "free_flow_infeasible_at_admission": admitted is not None and (h is None or admitted+h > deadline),
               "source_queue_seconds": source_queue, "junction_queue_seconds": junction,
               "merge_grant_wait_overlapping_seconds": merge, "travel_seconds": travel, "service_seconds": service,
               "total_local_wait_overlapping_seconds": _number(raw, "total_local_wait", "reported_local_wait_seconds"),
               "elapsed_from_release_seconds": elapsed, "unattributed_residual_seconds": residual,
               "failure_reason": raw.get("failure_reason", "missing_output" if not raw else "")}
        segments.append(row)
        grouped[row["task_id"]].append(row)
    business = []
    for task, legs in sorted(grouped.items()):
        finals = [r for r in legs if r["leg"] in ("direct", "storage_out")]
        if len(finals) != 1:
            raise ValueError(f"exactly one final leg required: {task}")
        final = finals[0]
        if len({r["deadline"] for r in legs}) != 1:
            raise ValueError(f"inconsistent business deadlines: {task}")
        inbound = [r for r in legs if r["leg"] == "storage_in"]
        causal = True
        lower = final["free_flow_finish_from_canonical"]
        if final["leg"] == "storage_out":
            if len(inbound) != 1 or len(legs) != 2:
                raise ValueError(f"EBS requires exactly two legs: {task}")
            inside = inbound[0]
            if final["admitted_time"] is None:
                causal = None
            elif not inside["completed"]:
                causal = False
            else:
                causal = inside["finish_time"] <= final["admitted_time"] + EPS
            inbound_lower = inside["free_flow_finish_from_canonical"]
            lower = (max(inbound_lower, final["canonical_pass_time"]) + final["free_flow_seconds"]
                     if inbound_lower is not None and final["free_flow_seconds"] is not None else None)
        elif len(legs) != 1:
            raise ValueError(f"direct business has extra legs: {task}")
        completed = all(r["completed"] for r in legs)
        on_time = completed and final["on_time"]
        row = {"task_id": task, "leg": final["leg"], "segment_ids": [r["segment_id"] for r in legs],
               "od": f'{inbound[0]["start"] if inbound else final["start"]}->{final["goal"]}',
               "std_hour": final["std_hour"], "deadline": final["deadline"],
               "final_finish_time": final["finish_time"], "completed": completed,
               "on_time": on_time, "on_time_minus_2700": completed and final["on_time_minus_2700"],
               "old_max_segment_on_time": completed and all(r["on_time"] for r in legs),
               "old_max_segment_on_time_minus_2700": completed and all(r["on_time_minus_2700"] for r in legs),
               "ebs_causal": causal, "unfinished_deadline_elapsed": not completed and final["deadline"] <= horizon,
               "lateness_seconds": final["lateness_seconds"] if completed else None,
               "free_flow_finish_causal_lower_bound": lower,
               "free_flow_infeasible": lower is None or lower > final["deadline"],
               "already_late_at_release": final["already_late_at_release"],
               "already_late_at_admission": final["already_late_at_admission"],
               "final_leg_lower_bound_infeasible_at_admission": final["free_flow_infeasible_at_admission"]}
        business.append(row)
    late_business = [r for r in business if not r["on_time"]]
    late_ids = {r["task_id"] for r in late_business}
    late_segments = [r for r in segments if r["task_id"] in late_ids]
    late_completed = [r for r in late_business if r["completed"]]
    return {
        "schema": "g31.deadline.audit.v2", "horizon": horizon,
        "definitions": {
            "denominator": "Every canonical business and segment, including missing outputs and unfinished work.",
            "business_on_time": "All business segments complete and direct/storage_out finish <= original STD; observed independent-leg execution.",
            "business_on_time_causally_valid": "business_on_time and storage_in finish <= storage_out admission; same full denominator.",
            "old_all_segments_finish_le_std": "Historical max(all segment finishes)<=STD, without EBS causality guarantee.",
            "literal_std_minus_2700": "All business segments complete and direct/storage_out finish <= original STD-2700; separate literal early criterion with the same full denominator.",
            "literal_std_minus_2700_causally_valid": "literal_std_minus_2700 and storage_in finish <= storage_out admission; same full denominator.",
            "old_all_segments_finish_le_std_minus_2700": "Historical max(all segment finishes)<=original STD-2700, without EBS causality guarantee; same full denominator.",
            "decomposition": "source+junction+travel+service, completed records only; merge overlaps junction and total_local_wait overlaps source+junction.",
            "residual": "Observed elapsed minus reported components; explicitly unattributed, never assigned to merge, routing or physical congestion.",
            "free_flow": "Independent service-aware Dijkstra on original graph (faults ignored), service(source)+travel, goal arrival terminal; optimistic necessary condition only.",
            "std_hour": "floor(original input STD seconds / 3600); not converted to wall-clock timezone.",
            "grouping": "All breakdown rates retain the complete canonical subgroup denominator; completed-subset timing is labeled."},
        "business": _summary(business, business=True), "segments": _summary(segments),
        "missing_output_segments": sum(not r["output_present"] for r in segments),
        "business_by_leg": _groups(business, "leg", business=True),
        "business_by_od": _groups(business, "od", business=True),
        "business_by_std_hour": _groups(business, "std_hour", business=True),
        "segments_by_leg": _groups(segments, "leg"), "segments_by_od": _groups(segments, "od"),
        "segments_by_source": _groups(segments, "start"),
        "segments_by_std_hour": _groups(segments, "std_hour"),
        "late_business_diagnostics": {"not_on_time_count": len(late_business),
            "completed_late_count": len(late_completed),
            "free_flow_infeasible": sum(r["free_flow_infeasible"] for r in late_business),
            "already_late_at_final_release": sum(r["already_late_at_release"] for r in late_business),
            "already_late_at_final_admission": sum(r["already_late_at_admission"] for r in late_business),
            "final_leg_lower_bound_infeasible_at_admission": sum(r["final_leg_lower_bound_infeasible_at_admission"] for r in late_business),
            "ebs_invalid": sum(r["ebs_causal"] is False for r in late_business),
            "classification_boundary": "Overlapping necessary-condition diagnostics; causal effects require matched interventions."},
        "components_completed_segments": _components([r for r in segments if r["completed"]]),
        "components_completed_late_final_segments": _components([
            r for r in segments if r["leg"] in ("direct", "storage_out") and r["completed"] and not r["on_time"]]),
        "components_completed_segments_of_not_on_time_business": _components([r for r in late_segments if r["completed"]]),
        "failure_reasons": dict(Counter(r["failure_reason"] for r in segments if not r["completed"])),
        "late_business_rows": late_business,
        "late_segment_rows": [r for r in segments if not r["on_time"]],
        "ebs_invalid_business_rows": [r for r in business if r["ebs_causal"] is False],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True, help="Directory containing bags.jsonl and request.json.gz")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Defaults to RUN/analysis.json; refuses overwrite")
    args = parser.parse_args()
    output = args.output or args.run / "analysis.json"
    if output.exists():
        raise FileExistsError(output)
    result = analyze(read_jsonl(args.canonical), read_jsonl(args.run / "bags.jsonl"), read_json(args.run / "request.json.gz"))
    result["inputs"] = {"canonical": str(args.canonical.resolve()), "run": str(args.run.resolve()),
                        "file_sha256": {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in (args.canonical, args.run / "bags.jsonl", args.run / "request.json.gz", Path(__file__))}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "business": result["business"], "late_business_diagnostics": result["late_business_diagnostics"]}))


if __name__ == "__main__":
    main()
