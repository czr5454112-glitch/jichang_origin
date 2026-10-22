"""Read-only, full-population service comparison of closed native runs.

Uses actual arrival and UNLOAD_COMPLETE receipts. Unfinished bags keep unknown
completion times; their observed lateness is a lower bound, never an imputed
completion. This evaluator cannot dispatch, fit a model, or unlock TEST.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path

from .foundation_airport_behavior_evidence import snapshot_index
from .foundation_airport_inventory_spi_campaign import read_bound
from .foundation_airport_pair_dataset import window_cost
from .foundation_airport_service_metrics import compare_completion_outcomes, physical_progress_intervals
from .foundation_airport_terminal_flow_audit import ACCEPTED, closed_run
from .foundation_airport_transport_evidence import binding, read

SCHEMA = "g31.terminal_flow.full_population_service_audit.v1"


def require(condition, reason):
    if not condition:
        raise ValueError("terminal_service_audit:" + reason)


def _bag_state(spec, completed_at, *, cutoff):
    deadline, arrival = spec["deadline"], spec["arrival"]
    if completed_at is not None:
        lateness = max(0., completed_at - deadline)
        return dict(status="completed_late" if lateness > 0 else "completed_on_time",
                    completed_at=completed_at, exact_lateness_seconds=lateness,
                    lateness_lower_bound_seconds=lateness, completion_censored=False)
    arrived = arrival <= cutoff
    return dict(status=("unfinished_overdue" if deadline < cutoff else "unfinished_before_or_at_deadline")
                if arrived else "not_yet_arrived", completed_at=None, exact_lateness_seconds=None,
                lateness_lower_bound_seconds=max(0., cutoff-deadline) if arrived else None,
                completion_censored=arrived)


def per_bag_service(specs, reference_completions, candidate_completions, *, cutoff, tolerance=1e-6):
    """A row for every offered identity, including future and unfinished bags."""
    require(all(type(r.get("deadline")) in (int, float) and math.isfinite(r["deadline"])
                and type(r.get("arrival")) in (int, float) and math.isfinite(r["arrival"])
                and r["arrival"] >= 0 for r in specs), "finite_deadlines_and_arrivals")
    direction = compare_completion_outcomes(specs, reference_completions, candidate_completions,
                                           cutoff=cutoff, tolerance=tolerance, include_rows=True)
    specs_by_id = {r["business_bag_id"]: r for r in specs}
    counts, rows = Counter(), []
    ref_status, candidate_status = Counter(), Counter()
    for completion_row in direction.pop("rows"):
        spec = specs_by_id[completion_row["business_bag_id"]]
        a = _bag_state(spec, completion_row["reference_completed_at"], cutoff=cutoff)
        b = _bag_state(spec, completion_row["candidate_completed_at"], cutoff=cutoff)
        ref_status[a["status"]] += 1
        candidate_status[b["status"]] += 1
        ae, be = a["exact_lateness_seconds"], b["exact_lateness_seconds"]
        extra = {}
        if ae is not None and be is not None:
            delta = be - ae
            category = "exact_harmed" if delta > tolerance else "exact_improved" if delta < -tolerance else "exact_equal"
            extra["exact_lateness_delta_seconds"] = delta
        elif ae is not None and cutoff >= spec["deadline"]:
            category = "reference_only_finished_known_lateness_harm"
            extra["lateness_harm_lower_bound_seconds"] = max(0., cutoff-spec["deadline"])-ae
        elif be is not None and cutoff >= spec["deadline"]:
            category = "candidate_only_finished_known_lateness_improvement"
            extra["lateness_improvement_lower_bound_seconds"] = max(0., cutoff-spec["deadline"])-be
        else:
            category = "unknown_censored" if spec["arrival"] <= cutoff else "unknown_not_yet_arrived"
        counts[category] += 1
        rows.append(dict(completion_row, arrival=spec["arrival"], deadline=spec["deadline"],
            reference=a, candidate=b, lateness_direction=category, **extra))
    return dict(completion_direction=direction, reference_status=dict(ref_status), candidate_status=dict(candidate_status),
        lateness_direction_counts=dict(counts),
        known_lateness_harm=counts["exact_harmed"]+counts["reference_only_finished_known_lateness_harm"],
        known_lateness_improvement=counts["exact_improved"]+counts["candidate_only_finished_known_lateness_improvement"],
        censored_lateness_bounds_are_not_eventual_completion_times=True,
        both_unfinished_never_declared_equal=True, per_bag=rows)


def physical_comparison_contract(reference, candidate):
    """Source changes require a separate equivalence audit, never silent pairing."""
    keys = ("parent", "input", "binary", "source_bundle", "controller", "activation", "horizon",
            "supply_mode", "projection_horizon_seconds", "cost_scope")
    missing = [key for key in keys if key not in reference or key not in candidate]
    changed = [key for key in keys if reference.get(key) != candidate.get(key)]
    require(not missing, "missing_comparison_contract:" + ",".join(missing))
    require(not changed, "different_comparison_contract:" + ",".join(changed))
    return {key: reference[key] for key in keys}


def _execution_summary(trajectory, terminal):
    rows = trajectory["rows"]
    transfers = [row for row in rows if row["requested_action"]["kind"] == "transfer"]
    missing = sum(row.get("actual_submission") is None or not any(
        ack.get("status") in ACCEPTED for ack in (row.get("ack") or [])) for row in transfers)
    statuses = Counter(row["status"] for row in terminal["transfers"])
    return dict(selected_transfer_decisions=len(transfers),
        selected_policy_physical_failures=sum(bool(row.get("physical_failure")) for row in rows),
        selected_missing_positive_ack_or_submission=missing,
        all_native_transfer_status_counts=dict(statuses),
        all_native_failed_or_rejected_or_expired=sum(statuses[k] for k in ("failed", "rejected", "expired", "cancelled")),
        selected_policy_counts_do_not_include_upstream_priority_requests=True)


def compare_runs(reference_dir, candidate_dir):
    directories = [Path(reference_dir), Path(candidate_dir)]
    closed = [closed_run(path) for path in directories]
    plans, receipts, trajectories = zip(*closed)
    contract = physical_comparison_contract(*plans)
    require(plans[0]["parent"]["split"] != "test", "test_remains_locked")
    data = read_bound(plans[0]["input"])
    read_bound(plans[0]["source_bundle"])
    require(binding(plans[0]["binary"]["path"])["sha256"] == plans[0]["binary"]["sha256"], "native_binary_changed")
    terminal = [read(path/"terminal_evidence.json.gz") for path in directories]
    start, end = plans[0]["activation"], plans[0]["horizon"]
    indexes = [snapshot_index(result, expected_population=len(data["jobs"])) for result in terminal]
    require(all(index["clock"] == end for index in indexes), "exact_common_closed_endpoint")
    costs = [window_cost(data, result, start=start, end=end) for result in terminal]
    for cost, receipt, trajectory in zip(costs, receipts, trajectories):
        recorded = receipt["worker"]["cost"]
        for key, value in cost.items():
            require(key in recorded, "missing_recorded_cost:" + key)
            require(math.isclose(value, recorded[key], rel_tol=1e-12, abs_tol=1e-6)
                    if type(value) in (float, int) else value == recorded[key], "recomputed_cost_differs:" + key)
        require(math.isclose(cost["backlog_integral_bag_seconds"], trajectory["system_J"],
                             rel_tol=1e-12, abs_tol=1e-6), "recomputed_J_differs")
    bags = per_bag_service(data["jobs"], indexes[0]["completions"], indexes[1]["completions"], cutoff=end)
    execution = [_execution_summary(t, result) for t, result in zip(trajectories, terminal)]
    a, b = costs
    checks = dict(no_known_completion_direction_harm=bags["completion_direction"]["known_direction_harm"] == 0,
        completed_nonworse=b["completed_by_end"] >= a["completed_by_end"],
        on_time_nonworse=b["on_time_by_end"] >= a["on_time_by_end"],
        overdue_unfinished_nonworse=b["arrived_unfinished_past_deadline"] <= a["arrived_unfinished_past_deadline"],
        no_selected_policy_physical_failure=execution[1]["selected_policy_physical_failures"] == 0,
        no_selected_missing_execution=execution[1]["selected_missing_positive_ack_or_submission"] == 0)
    gain = a["backlog_integral_bag_seconds"] - b["backlog_integral_bag_seconds"]
    return dict(schema=SCHEMA, reference_task=plans[0]["task_id"], candidate_task=plans[1]["task_id"],
        reference_method=plans[0]["method"], candidate_method=plans[1]["method"], physical_contract=contract,
        evidence=[{name: binding(path/name) for name in ("plan.json", "receipt.json", "trajectory.json.gz",
            "terminal_evidence.json.gz")} for path in directories],
        cost_window=[start, end], population=len(data["jobs"]),
        reference_cost=a, candidate_cost=b, gain_bag_seconds=gain,
        completed_delta=b["completed_by_end"]-a["completed_by_end"],
        on_time_delta=b["on_time_by_end"]-a["on_time_by_end"],
        overdue_unfinished_delta=b["arrived_unfinished_past_deadline"]-a["arrived_unfinished_past_deadline"],
        execution=dict(reference=execution[0], candidate=execution[1]),
        physical_progress=[physical_progress_intervals(result, start=start, end=end) for result in terminal],
        existing_observed_service_gate_checks=checks, existing_observed_service_gate_passed=all(checks.values()),
        passes_observed_service_and_positive_gain_gate=all(checks.values()) and gain > 0,
        strict_per_bag_nonharm_certified=False, protected_takeover_eligible=False, test_unlocked=False,
        completion_times_imputed=False, population_exclusions=0, **bags)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "fresh_output_required")
    result = compare_runs(args.reference, args.candidate)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf8") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")
    print(json.dumps(dict(output=str(args.output.resolve()), population=result["population"],
        known_completion_harm=result["completion_direction"]["known_direction_harm"],
        known_lateness_harm=result["known_lateness_harm"], gain_bag_seconds=result["gain_bag_seconds"], native_starts=0)))


if __name__ == "__main__":
    main()
