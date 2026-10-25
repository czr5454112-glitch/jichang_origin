"""Full-population lifecycle audit for the mature G31/Feng comparison.

This module does not import or run a finite-body transport model.
"""
from __future__ import annotations

from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def distribution(values):
    if not values:
        return None
    ordered = sorted(values)
    def quantile(q):
        at = q * (len(ordered) - 1)
        lo = int(at)
        return ordered[lo] + (ordered[min(lo+1, len(ordered)-1)]-ordered[lo]) * (at-lo)
    return {"count": len(values), "mean": statistics.fmean(values), "min": ordered[0],
            "p50": quantile(.5), "p95": quantile(.95), "p99": quantile(.99), "max": ordered[-1]}


def native_segments(payload):
    result = []
    for row in payload["bags"]:
        completed = bool(row["completed"])
        admitted = float(row["admitted_time"])
        result.append({"segment_id": row["segment_id"], "task_id": int(row["task_id"]),
                       "start": int(row["start"]), "goal": int(row["goal"]),
                       "completed": completed, "finish": float(row["finish_time"]) if completed else None,
                       "entered": admitted if admitted >= 0 else None, "released": float(row["release_time"]),
                       "reported_source_queue_delay": row.get("source_queue_delay"),
                       "reported_local_wait_seconds": row.get("total_local_wait"),
                       "reported_edge_travel_seconds": row.get("edge_travel_time_seconds"),
                       "reported_node_service_seconds": row.get("node_service_time_seconds"),
                       "failure_reason": row.get("failure_reason", "")})
    return result


def java_segments(path):
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    def optional(value):
        return float(value) if value not in ("", None) else None
    return [{"segment_id": r["segment_id"], "task_id": int(r["task_id"]),
             "start": int(r["start"]), "goal": int(r["goal"]),
             "completed": r["complete"].lower() == "true", "finish": optional(r["finish_epoch"]),
             "entered": optional(r["processed_attempt_epoch"]), "released": optional(r["release_epoch"])}
            for r in rows]


def generator_releases(canonical, actual):
    """Validate an exact source-generator trace without using successful-plan times."""
    expected = {r["segment_id"]: r for r in canonical}
    observed = {r["segment_id"]: r for r in actual}
    if len(expected) != len(canonical) or len(observed) != len(actual):
        raise ValueError("duplicate segment in generator release trace")
    if set(expected) != set(observed):
        raise ValueError("generator release trace population mismatch")
    releases = {}
    for segment_id, source in expected.items():
        row = observed[segment_id]
        if any(int(source[k]) != int(row[k]) for k in ("task_id", "start", "goal")):
            raise ValueError(f"generator release trace identity/OD mismatch: {segment_id}")
        release = row["released"]
        if release is None or not math.isfinite(float(release)):
            raise ValueError(f"invalid generator release: {segment_id}")
        releases[segment_id] = float(release)
    return releases


def audit(canonical, actual, *, horizon=98259.0):
    expected = {r["segment_id"]: r for r in canonical}
    observed = {r["segment_id"]: r for r in actual}
    if len(expected) != len(canonical) or len(observed) != len(actual):
        raise ValueError("duplicate segment identity")
    if set(expected) != set(observed):
        raise ValueError("missing or unexpected segment: no population filtering is permitted")
    grouped = defaultdict(list)
    segment_elapsed, segment_network, segment_release_elapsed, segment_restricted = [], [], [], []
    for segment_id, source in expected.items():
        row = observed[segment_id]
        if (int(source["task_id"]), int(source["start"]), int(source["goal"])) != (row["task_id"], row["start"], row["goal"]):
            raise ValueError(f"identity/OD mismatch: {segment_id}")
        if any(row[k] is not None and not math.isfinite(row[k]) for k in ("entered", "released")):
            raise ValueError(f"non-finite lifecycle time: {segment_id}")
        if row["entered"] is not None and row["released"] is not None and row["entered"] < row["released"] - 1e-7:
            raise ValueError(f"entered before actual release: {segment_id}")
        if row["completed"]:
            if row["finish"] is None or not math.isfinite(row["finish"]) or row["finish"] > horizon + 1e-7:
                raise ValueError(f"invalid completed time: {segment_id}")
            if any(row[k] is not None and row["finish"] < row[k] - 1e-7 for k in ("entered", "released")):
                raise ValueError(f"finished before own entry/release: {segment_id}")
            segment_elapsed.append(row["finish"]-float(source["pass_time"]))
            if row["entered"] is not None:
                segment_network.append(row["finish"]-row["entered"])
            if row["released"] is not None:
                segment_release_elapsed.append(row["finish"]-row["released"])
        segment_restricted.append((row["finish"] if row["completed"] else horizon)-float(source["pass_time"]))
        grouped[int(source["task_id"])].append((source, row))
    business, violations = [], []
    for task_id, legs in sorted(grouped.items()):
        finals = [(s,r) for s,r in legs if s["leg"] in ("direct", "storage_out")]
        if len(finals) != 1:
            raise ValueError("exactly one business final leg is required")
        source, final = finals[0]
        entry, deadline = float(source["original_entry_time"]), float(source["std"])
        if any(float(s["original_entry_time"]) != entry for s,r in legs):
            raise ValueError("business entry differs across EBS legs")
        complete = all(r["completed"] for s,r in legs)
        causal = True
        if source["leg"] == "storage_out" and final["entered"] is not None:
            inbound = [r for s,r in legs if s["leg"] == "storage_in"]
            if len(inbound) != 1:
                raise ValueError("storage_out must have exactly one storage_in")
            causal = inbound[0]["completed"] and inbound[0]["finish"] <= final["entered"] + 1e-7
            if not causal:
                violations.append({"task_id": task_id, "inbound_finish": inbound[0]["finish"], "outbound_entered": final["entered"]})
        finish = final["finish"] if complete else None
        business.append({"task_id": task_id, "completed": complete, "ebs_causal": causal,
                         "original_entry": entry, "deadline": deadline, "final_finish": finish,
                         "observed_end_to_end_seconds": finish-entry if complete else None,
                         "restricted_observed_end_to_end_seconds": (finish if complete else horizon)-entry,
                         "all_segments_finished_seconds": max(r["finish"] for s,r in legs)-entry if complete else None,
                         "sum_leg_elapsed_from_scheduled_pass_seconds": sum(r["finish"]-float(s["pass_time"]) for s,r in legs) if complete else None,
                         "sum_leg_in_network_seconds": sum(r["finish"]-r["entered"] for s,r in legs) if complete and all(r["entered"] is not None for s,r in legs) else None,
                         "sum_plan_or_admission_minus_scheduled_pass_seconds": sum(r["entered"]-float(s["pass_time"]) for s,r in legs) if all(r["entered"] is not None for s,r in legs) else None,
                         "deadline_miss": finish > deadline if complete else deadline <= horizon})
    completed = [r for r in business if r["completed"]]
    full = len(completed) == len(business)
    mean_fields = ["observed_end_to_end_seconds", "all_segments_finished_seconds", "sum_leg_elapsed_from_scheduled_pass_seconds", "sum_leg_in_network_seconds"]
    summary = {"offered_business_bags": len(business), "offered_transport_legs": len(canonical),
               "primary_observation_unit": "all_independently_scheduled_transport_segments",
               "full_population_segment_elapsed_from_canonical_pass_seconds": distribution(segment_elapsed) if len(segment_elapsed)==len(canonical) else None,
               "full_population_segment_elapsed_from_actual_release_seconds": distribution(segment_release_elapsed) if len(segment_release_elapsed)==len(canonical) else None,
               "full_population_segment_in_network_seconds": distribution(segment_network) if len(segment_network)==len(canonical) else None,
               "completed_subset_segment_elapsed_descriptive": distribution(segment_elapsed),
               "full_population_restricted_segment_elapsed_seconds": distribution(segment_restricted),
               "completed_business_bags": len(completed), "unfinished_business_bags": len(business)-len(completed),
               "completed_transport_legs": sum(r["completed"] for r in actual),
               "entered_transport_legs": sum(r["entered"] is not None for r in actual),
               "deadline_misses_including_unfinished": sum(r["deadline_miss"] for r in business),
               "ebs_causality_violation_count": len(violations), "ebs_causality_violation_examples": violations[:20],
               "observed_complete_and_ebs_causal_bags": sum(r["completed"] and r["ebs_causal"] for r in business),
               "full_population_observed_end_to_end_seconds": distribution([r["observed_end_to_end_seconds"] for r in completed]) if full else None,
               "full_population_ebs_causally_valid_end_to_end_seconds": distribution([r["observed_end_to_end_seconds"] for r in completed]) if full and not violations else None,
               "full_population_restricted_observed_end_to_end_seconds": distribution([r["restricted_observed_end_to_end_seconds"] for r in business]),
               "completed_subset_descriptive": {key: distribution([r[key] for r in completed if r[key] is not None]) for key in mean_fields},
               "definitions": {"business_end_to_end": "finish of direct/storage_out minus original entry exactly once; labeled observed when EBS causality is invalid",
                               "primary_segment_elapsed": f"each independently scheduled segment finish minus its canonical pass_time; {len(canonical):,}-segment denominator, never sum-leg elapsed mislabeled as business elapsed",
                               "restricted": "unfinished uses common horizon minus original entry; is never counted as completed",
                               "network_elapsed": "sum leg finish minus native admitted/Java successful-plan epoch; source-release policy differs",
                               "java_rounding": "original Java uses integer epochs and may release less than one second before fractional canonical pass time"}}
    return summary, business


def compare(left, right):
    a, b = {r["task_id"]: r for r in left}, {r["task_id"]: r for r in right}
    if set(a) != set(b):
        raise ValueError("paired business population mismatch")
    rows = []
    for task in sorted(a):
        x,y = a[task],b[task]
        rows.append({"task_id": task, "left_completed": x["completed"], "right_completed": y["completed"],
                     "left_ebs_causal": x["ebs_causal"], "right_ebs_causal": y["ebs_causal"],
                     "observed_delta_seconds_left_minus_right": x["observed_end_to_end_seconds"]-y["observed_end_to_end_seconds"] if x["completed"] and y["completed"] else None,
                     "restricted_delta_seconds_left_minus_right": x["restricted_observed_end_to_end_seconds"]-y["restricted_observed_end_to_end_seconds"]})
    values = [r["observed_delta_seconds_left_minus_right"] for r in rows if r["observed_delta_seconds_left_minus_right"] is not None]
    return {"full_denominator": len(rows), "both_observed_complete": len(values),
            "left_faster_observed": sum(v < -1e-7 for v in values), "right_faster_observed": sum(v > 1e-7 for v in values),
            "observed_paired_delta_descriptive": distribution(values),
            "full_denominator_restricted_delta": distribution([r["restricted_delta_seconds_left_minus_right"] for r in rows])}, rows
