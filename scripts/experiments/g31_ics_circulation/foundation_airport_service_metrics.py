"""Full-population service directions without imputing censored completions."""
from __future__ import annotations

from collections import Counter
import math


def compare_completion_outcomes(specs, reference_completions, candidate_completions,
                                *, cutoff, tolerance=1e-6, include_rows=False):
    """At common closed H, single-sided completion has a known direction.

    Positive delay means the candidate is later. Censored delay magnitudes are
    lower bounds; they are never substituted for an actual completion time.
    """
    jobs = {row["business_bag_id"]: row for row in specs}
    if len(jobs) != len(specs) or not math.isfinite(cutoff):
        raise ValueError("service_metrics:unique_population_finite_cutoff")
    for completions in (reference_completions, candidate_completions):
        if not set(completions) <= set(jobs):
            raise ValueError("service_metrics:foreign_completion")
        if any(not math.isfinite(value) or value < jobs[key]["arrival"]
               for key, value in completions.items()):
            raise ValueError("service_metrics:invalid_completion_time")
    counts = Counter({key: 0 for key in (
        "exact_harmed", "exact_improved", "exact_equal",
        "reference_only_finished", "candidate_only_finished",
        "both_arrived_unfinished", "both_not_yet_arrived")})
    exact_delays, exact_gains, lower_delays, lower_gains, rows = [], [], [], [], []
    for identity, spec in jobs.items():
        a = reference_completions.get(identity)
        b = candidate_completions.get(identity)
        a = a if a is not None and a <= cutoff else None
        b = b if b is not None and b <= cutoff else None
        row = {"business_bag_id": identity, "reference_completed_at": a,
               "candidate_completed_at": b}
        if a is not None and b is not None:
            delay = b - a
            category = ("exact_harmed" if delay > tolerance else
                        "exact_improved" if delay < -tolerance else "exact_equal")
            row["exact_delay_seconds"] = delay
            if category == "exact_harmed":
                exact_delays.append(delay)
            elif category == "exact_improved":
                exact_gains.append(-delay)
        elif a is not None:
            category = "reference_only_finished"
            row["delay_lower_bound_seconds"] = cutoff - a
            lower_delays.append(cutoff - a)
        elif b is not None:
            category = "candidate_only_finished"
            row["improvement_lower_bound_seconds"] = cutoff - b
            lower_gains.append(cutoff - b)
        else:
            category = ("both_arrived_unfinished" if spec["arrival"] <= cutoff
                        else "both_not_yet_arrived")
        counts[category] += 1
        if include_rows:
            rows.append(dict(row, category=category))
    assert sum(counts.values()) == len(jobs)
    output = {
        "schema": "g31.completion_direction.v1", "cutoff": cutoff,
        "population": len(jobs), "categories": dict(counts),
        "known_direction_harm": counts["exact_harmed"] + counts["reference_only_finished"],
        "known_direction_improvement": counts["exact_improved"] + counts["candidate_only_finished"],
        "maximum_exact_delay_seconds": max(exact_delays, default=0.),
        "maximum_exact_improvement_seconds": max(exact_gains, default=0.),
        "maximum_censored_delay_lower_bound_seconds": max(lower_delays, default=0.),
        "maximum_censored_improvement_lower_bound_seconds": max(lower_gains, default=0.),
        "sum_censored_delay_lower_bound_seconds": math.fsum(lower_delays),
        "sum_censored_improvement_lower_bound_seconds": math.fsum(lower_gains),
        "unknown_incomplete_legacy": sum(counts[k] for k in (
            "reference_only_finished", "candidate_only_finished",
            "both_arrived_unfinished", "both_not_yet_arrived")),
        "completion_times_imputed": False, "bounds_are_not_completion_times": True,
        "strict_per_job_nonharm_certified": False,
    }
    if include_rows:
        output["rows"] = rows
    return output


def backlog_relief(specs, completions, *, start, end):
    """Explanatory no-service reference; does not replace the frozen J."""
    j0 = math.fsum(max(0., end - max(row["arrival"], start)) for row in specs)
    cost = math.fsum(max(0., min(end, completions.get(row["business_bag_id"], math.inf))
                         - max(row["arrival"], start)) for row in specs)
    return {"J0_bag_seconds": j0, "J_bag_seconds": cost,
            "relief_bag_seconds": j0 - cost,
            "frozen_J_redefined": False}


def physical_progress_intervals(result, *, start, end):
    """Global observed edge-progress gaps; not a proof of permanent deadlock."""
    times = sorted({float(row["time"]) for row in result.get("receipts", [])
                    if row["event"] in ("EDGE_ENTER", "EDGE_EXIT")
                    and start <= row["time"] <= end})
    points = sorted(set([float(start), *times, float(end)]))
    gaps = [(b - a, a, b) for a, b in zip(points, points[1:])]
    longest = max(gaps, default=(end-start, start, end))
    return {"window": [start, end], "edge_progress_timestamps": len(times),
            "longest_no_edge_progress_seconds": longest[0],
            "longest_no_edge_progress_interval": list(longest[1:]),
            "last_edge_progress_at": times[-1] if times else None,
            "global_only_not_node_deadlock_proof": True}
