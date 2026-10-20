"""Fixed eight-parent effect accounting from an already produced offline audit.

This module reads no run folders, trains no models and starts no simulator.
Unknown cells remain in every registered denominator. Leave-one-parent-out is
a descriptive concentration check, not resampling inference or causality.
"""
from __future__ import annotations

from collections import Counter
import copy
import gzip
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path

SCHEMA = "g31.inventory_spi_parent_effects.v1"
AUDIT_SCHEMA = "g31.inventory_spi_offline_audit.v1"
PARENTS = tuple(range(1301, 1309))
METHODS = ("R0_current_stock_v1", "C00", "C10", "C01", "C11")
ENGINEERING_THRESHOLD = .001
ABSOLUTE_TOLERANCE = 1e-6
MAIN_EFFECTS = ("C00_minus_C01", "C10_minus_C11", "C00_minus_C10", "C01_minus_C11")
DIRECTION_KEYS = ("exact_harmed", "exact_improved", "exact_equal", "reference_only_finished",
                  "candidate_only_finished", "both_arrived_unfinished", "both_not_yet_arrived")


def require(ok, reason):
    if not ok:
        raise ValueError("inventory_spi_effects:" + reason)


def _number(value, *, nonnegative=False):
    return type(value) in (int, float) and math.isfinite(value) and (not nonnegative or value >= 0)


def _count(value):
    return type(value) is int and value >= 0


def _all_known(values, predicate):
    if any(value is not None and not predicate(value) for value in values):
        return False
    return True if all(value is not None for value in values) else None


def _mean_complete(values):
    return math.fsum(values) / len(values) if values and all(value is not None for value in values) else None


def _direction(gain):
    return ("unknown" if gain is None else "candidate_better" if gain > ABSOLUTE_TOLERANCE
        else "candidate_worse" if gain < -ABSOLUTE_TOLERANCE else "equal_within_numeric_tolerance")


def _threshold(relative):
    return None if relative is None else relative >= ENGINEERING_THRESHOLD


def _cell(row):
    cost = row.get("full_window_cost")
    closed = row.get("status") == "complete" and row.get("audit_status") == "closed_cost_verified"
    known = closed and type(cost) is dict and _number(cost.get("backlog_integral_bag_seconds"), nonnegative=True)
    service = {}
    for key in ("completed_by_end", "on_time_by_end", "arrived_unfinished_past_deadline",
                "physical_population"):
        value = cost.get(key) if known else None
        service[key] = value if _count(value) else None
    return {"parent_seed": row["registered_parent_seed"], "method": row["registered_method"],
        "name": row["name"], "run_status": row.get("status"), "audit_status": row.get("audit_status"),
        "J_bag_seconds": cost["backlog_integral_bag_seconds"] if known else None,
        "cost_known": bool(known), "service": service,
        "physical_diagnostics": copy.deepcopy(row.get("physical")),
        "control_diagnostics": copy.deepcopy(row.get("control")),
        "missing_evidence": copy.deepcopy(row.get("missing_evidence", [])),
        "errors": copy.deepcopy(row.get("errors", [])),
        "strict_nonharm_certified": False}


def _validated_direction(value):
    if not isinstance(value, dict) or type(value.get("categories")) is not dict:
        return None, "missing_completion_direction"
    categories = value["categories"]
    valid = (set(categories) == set(DIRECTION_KEYS) and all(_count(v) for v in categories.values())
        and _count(value.get("population")) and sum(categories.values()) == value["population"]
        and value.get("known_direction_harm") == categories["exact_harmed"] + categories["reference_only_finished"]
        and value.get("known_direction_improvement") == categories["exact_improved"] + categories["candidate_only_finished"]
        and value.get("completion_times_imputed") is False)
    return (copy.deepcopy(value), "validated_seven_category_population") if valid else (
        None, "invalid_completion_direction")


def _point(parent, reference, candidate, compared):
    point = {"parent_seed": parent, "reference_method": reference["method"],
        "candidate_method": candidate["method"], "reference_name": reference["name"],
        "candidate_name": candidate["name"], "status": "unknown",
        "audit_comparison_status": None if compared is None else compared.get("status"),
        "reference_J_bag_seconds": reference["J_bag_seconds"],
        "candidate_J_bag_seconds": candidate["J_bag_seconds"],
        "advantage_bag_seconds": None, "relative_J_gain": None,
        "completed_delta": None, "on_time_delta": None, "overdue_unfinished_delta": None,
        "completion_direction": None, "completion_direction_status": "not_comparable",
        "known_direction_harm": None, "known_direction_improvement": None,
        "physical_diagnostics": {"reference": reference["physical_diagnostics"],
                                 "candidate": candidate["physical_diagnostics"]},
        "strict_nonharm_certified": False, "single_action_causal_attribution": False}
    if compared is None:
        point["reason"] = "missing_registered_pair_audit"
    elif compared.get("status") != "closed_same_parent_comparison":
        point["reason"] = "audit_did_not_establish_same_runtime_closed_comparison"
    elif not reference["cost_known"] or not candidate["cost_known"]:
        point["reason"] = "one_or_both_registered_cells_lack_verified_closed_cost"
    elif compared.get("reference") != reference["name"] or compared.get("candidate") != candidate["name"]:
        point["reason"] = "audit_comparison_name_binding_failed"
    else:
        a, b = reference["J_bag_seconds"], candidate["J_bag_seconds"]
        gain = a-b
        if not _number(compared.get("advantage_bag_seconds")) or not math.isclose(
                gain, compared["advantage_bag_seconds"], rel_tol=1e-12, abs_tol=ABSOLUTE_TOLERANCE):
            point["reason"] = "audit_gain_does_not_match_method_costs"
        else:
            relative = gain/a if a > 0 else None
            saved_relative = compared.get("relative_J_gain")
            if ((relative is None and saved_relative is not None) or
                    (relative is not None and (not _number(saved_relative) or not math.isclose(
                        relative, saved_relative, rel_tol=1e-12, abs_tol=1e-12)))):
                point["reason"] = "audit_relative_gain_does_not_match_method_costs"
            else:
                point.update(status="closed_same_parent_effect", advantage_bag_seconds=gain,
                    relative_J_gain=relative)
                for metric, key in (("completed_delta", "completed_by_end"), ("on_time_delta", "on_time_by_end"),
                                    ("overdue_unfinished_delta", "arrived_unfinished_past_deadline")):
                    old, new = reference["service"][key], candidate["service"][key]
                    actual = new-old if old is not None and new is not None else None
                    # Missing or inconsistent saved service evidence stays unknown.
                    point[metric] = actual if actual is not None and compared.get(metric) == actual else None
                direction, status = _validated_direction(compared.get("completion_direction"))
                populations = [r["service"]["physical_population"] for r in (reference, candidate)]
                if direction is not None and any(p != direction["population"] for p in populations):
                    direction, status = None, "completion_direction_population_not_bound_to_costs"
                point.update(completion_direction=direction, completion_direction_status=status)
                if direction is not None:
                    point["known_direction_harm"] = direction["known_direction_harm"]
                    point["known_direction_improvement"] = direction["known_direction_improvement"]
    point["cost_direction"] = _direction(point["advantage_bag_seconds"])
    point["engineering_threshold_reached"] = _threshold(point["relative_J_gain"])
    point["service_constraints"] = {
        "completed_non_decreasing_observed": None if point["completed_delta"] is None else point["completed_delta"] >= 0,
        "on_time_non_decreasing": None if point["on_time_delta"] is None else point["on_time_delta"] >= 0,
        "overdue_unfinished_non_increasing": None if point["overdue_unfinished_delta"] is None else point["overdue_unfinished_delta"] <= 0,
        "known_exact_and_censored_direction_harm_zero": None if point["known_direction_harm"] is None
            else point["known_direction_harm"] == 0}
    return point


def _leave_one_out(points, *, apply_threshold=True):
    entries = []
    for omitted in PARENTS:
        remaining = [r for r in points if r["parent_seed"] != omitted]
        gains = [r["advantage_bag_seconds"] for r in remaining]
        complete = len(remaining) == 7 and all(g is not None for g in gains)
        mean = math.fsum(gains)/7 if complete else None
        reference_sum = math.fsum(r["reference_J_bag_seconds"] for r in remaining) if complete else None
        relative = math.fsum(gains)/reference_sum if complete and reference_sum > 0 else None
        omitted_row = next(r for r in points if r["parent_seed"] == omitted)
        entries.append({"omitted_parent_seed": omitted, "registered_remaining_parent_count": 7,
            "known_remaining_parent_count": sum(g is not None for g in gains),
            "complete_mean_gain_bag_seconds": mean,
            "relative_gain_of_mean_J": relative,
            "positive_mean_gain": None if mean is None else mean > ABSOLUTE_TOLERANCE,
            "engineering_threshold_reached": _threshold(relative) if apply_threshold else None,
            "omitted_parent_gain_bag_seconds": omitted_row["advantage_bag_seconds"],
            "omitted_parent_physical_diagnostics": copy.deepcopy(omitted_row.get("physical_diagnostics"))})
    full_mean = _mean_complete([r["advantage_bag_seconds"] for r in points])
    positive = None if full_mean is None else full_mean > ABSOLUTE_TOLERANCE
    elimination = ([r["omitted_parent_seed"] for r in entries
        if r["positive_mean_gain"] is False] if positive else [])
    complete = full_mean is not None
    positive_parents = [r["parent_seed"] for r in points
        if r["advantage_bag_seconds"] is not None and r["advantage_bag_seconds"] > ABSOLUTE_TOLERANCE]
    return {"registered_leave_one_out_count": 8, "entries": entries,
        "full_eight_parent_mean_is_positive": positive,
        "positive_gain_parents": positive_parents,
        "positive_gain_occurs_only_in_one_parent": len(positive_parents) == 1 if complete else None,
        "parent_removal_eliminates_positive_mean": elimination if complete and positive else None,
        "positive_mean_survives_removal_of_every_parent": not elimination if complete and positive else None,
        "caused_by_single_stalled_parent": "not_established_by_leave_one_out",
        "physical_evidence_scope": "Observed progress gaps are retained for every omitted parent; no new stall threshold or causal attribution.",
        "resampling_confidence_interval_or_p_value": False}


def _service_summary(points):
    direction_rows = [r["completion_direction"] for r in points if r["completion_direction"] is not None]
    category_totals = ({key: sum(r["categories"][key] for r in direction_rows) for key in DIRECTION_KEYS}
        if len(direction_rows) == 8 else None)
    tests = {
        "completed_non_decreasing_observed": _all_known([r["completed_delta"] for r in points], lambda v: v >= 0),
        "on_time_non_decreasing_all_parents": _all_known([r["on_time_delta"] for r in points], lambda v: v >= 0),
        "overdue_unfinished_non_increasing_all_parents": _all_known(
            [r["overdue_unfinished_delta"] for r in points], lambda v: v <= 0),
        "known_direction_harm_zero_all_parents": _all_known(
            [r["known_direction_harm"] for r in points], lambda v: v == 0)}
    registered = [tests[k] for k in ("on_time_non_decreasing_all_parents",
        "overdue_unfinished_non_increasing_all_parents", "known_direction_harm_zero_all_parents")]
    return {**tests,
        "registered_service_constraints_satisfied": _all_known(registered, lambda v: v is True),
        "known_completion_direction_parent_count": len(direction_rows),
        "unknown_completion_direction_parent_ids": [r["parent_seed"] for r in points
            if r["completion_direction"] is None],
        "complete_eight_parent_category_totals": category_totals,
        "known_harmed_parent_ids": [r["parent_seed"] for r in points
            if r["known_direction_harm"] is not None and r["known_direction_harm"] > 0],
        "complete_known_direction_harm_sum": sum(r["known_direction_harm"] for r in points)
            if len(direction_rows) == 8 else None,
        "count_scope": "Repeated synthetic-parent comparisons; bag identities are not independent replicates.",
        "strict_per_job_nonharm_certified": False}


def _effect_summary(points, *, interaction=False):
    gains = [r["advantage_bag_seconds"] for r in points]
    complete = all(gain is not None for gain in gains)
    reference_sum = math.fsum(r["reference_J_bag_seconds"] for r in points) if complete else None
    relative = math.fsum(gains)/reference_sum if complete and reference_sum > 0 else None
    counts = Counter(r["cost_direction"] for r in points)
    result = {"registered_parent_count": 8, "known_parent_count": sum(g is not None for g in gains),
        "unknown_parent_ids": [r["parent_seed"] for r in points if r["advantage_bag_seconds"] is None],
        "complete_eight_parent_mean_gain_bag_seconds": _mean_complete(gains),
        "complete_mean_of_paired_relative_gains": _mean_complete([r["relative_J_gain"] for r in points]),
        "relative_gain_of_mean_J": relative,
        "relative_gain_definition": ("mean interaction / mean C00 J" if interaction
            else "sum(reference J - candidate J) / sum(reference J); distinct from mean per-parent relative gains"),
        "cost_direction_counts": {key: counts[key] for key in (
            "candidate_better", "candidate_worse", "equal_within_numeric_tolerance", "unknown")},
        "points": points, "leave_one_parent_out": _leave_one_out(points, apply_threshold=not interaction),
        "engineering_threshold_reached": _threshold(relative) if not interaction else None,
        "engineering_threshold_applied": not interaction,
        "engineering_threshold": ENGINEERING_THRESHOLD,
        "engineering_flag_is_significance_or_noninferiority": False,
        "strict_nonharm_certified": False}
    if not interaction:
        result["service"] = _service_summary(points)
    return result


def build_effects(grid):
    """Summarize one fixed 40-cell audit, preserving every missing/failed cell."""
    require(grid.get("schema") == AUDIT_SCHEMA
        and grid.get("registered_parent_count") == 8
        and grid.get("registered_method_count") == 5
        and grid.get("registered_run_count") == 40, "fixed_forty_cell_audit_schema")
    expected = {(parent, method) for parent in PARENTS for method in METHODS}
    raw_rows = grid["rows"]
    keys = [(r["registered_parent_seed"], r["registered_method"]) for r in raw_rows]
    require(len(keys) == len(set(keys)) == 40 and set(keys) == expected, "complete_unique_registered_roster")
    require(len({r["name"] for r in raw_rows}) == 40, "unique_registered_run_names")
    cells = {key: _cell(row) for key, row in zip(keys, raw_rows, strict=True)}
    comparison_lookup = {}
    valid_comparison_keys = {(parent, a, b) for parent in PARENTS for a, b in combinations(METHODS, 2)}
    for comparison in grid.get("comparisons", []):
        key = (comparison["parent_seed"], comparison["reference_method"], comparison["candidate_method"])
        require(key in valid_comparison_keys and key not in comparison_lookup, "registered_unique_comparison_orientation")
        comparison_lookup[key] = comparison
    methods = {}
    for method in METHODS:
        points = [cells[(parent, method)] for parent in PARENTS]
        methods[method] = {"registered_parent_count": 8,
            "closed_cost_parent_count": sum(p["cost_known"] for p in points),
            "unknown_parent_ids": [p["parent_seed"] for p in points if not p["cost_known"]],
            "complete_eight_parent_mean_J_bag_seconds": _mean_complete([p["J_bag_seconds"] for p in points]),
            "complete_eight_parent_mean_completed": _mean_complete([p["service"]["completed_by_end"] for p in points]),
            "complete_eight_parent_mean_on_time": _mean_complete([p["service"]["on_time_by_end"] for p in points]),
            "complete_eight_parent_mean_overdue_unfinished": _mean_complete(
                [p["service"]["arrived_unfinished_past_deadline"] for p in points]),
            "run_status_counts": dict(Counter(p["run_status"] for p in points)),
            "audit_status_counts": dict(Counter(p["audit_status"] for p in points)), "points": points}
    effects = {}
    for a, b in combinations(METHODS, 2):
        points = [_point(parent, cells[(parent, a)], cells[(parent, b)],
            comparison_lookup.get((parent, a, b))) for parent in PARENTS]
        effects[a + "_minus_" + b] = _effect_summary(points)
    interaction = []
    for index, parent in enumerate(PARENTS):
        components = {key: effects[key]["points"][index] for key in MAIN_EFFECTS}
        known = all(r["advantage_bag_seconds"] is not None for r in components.values())
        gain = (components["C10_minus_C11"]["advantage_bag_seconds"]
            - components["C00_minus_C01"]["advantage_bag_seconds"]) if known else None
        baseline = cells[(parent, "C00")]["J_bag_seconds"]
        interaction.append({"parent_seed": parent, "status": "closed_factorial_interaction" if known else "unknown",
            "reference_J_bag_seconds": baseline, "advantage_bag_seconds": gain,
            "relative_J_gain": gain/baseline if known and baseline > 0 else None,
            "cost_direction": _direction(gain),
            "component_gains": {key: r["advantage_bag_seconds"] for key, r in components.items()},
            "physical_diagnostics": {method: cells[(parent, method)]["physical_diagnostics"]
                for method in ("C00", "C10", "C01", "C11")}})
    interaction_result = _effect_summary(interaction, interaction=True)
    interaction_result.update(formula="(J_C10 - J_C11) - (J_C00 - J_C01)",
        positive_means="learning gain with forecast exceeds learning gain without forecast",
        direction_count_label="candidate_better means positive interaction, not a separate deployed candidate",
        service_constraints="No composed per-job direction is inferred by subtracting two comparisons.")
    return {"schema": SCHEMA, "source_audit_schema": AUDIT_SCHEMA,
        "registered_parent_ids": list(PARENTS), "registered_run_count": 40, "methods": methods,
        "paired_effects": effects, "main_effect_keys": list(MAIN_EFFECTS),
        "R0_effect_keys": [f"R0_current_stock_v1_minus_{m}" for m in METHODS[1:]],
        "interaction": interaction_result,
        "status_counts": dict(Counter(r.get("status") for r in raw_rows)),
        "failures_or_missing_cells_omitted": 0, "partial_parent_mean_presented_as_complete": False,
        "engineering_threshold": ENGINEERING_THRESHOLD,
        "numerical_direction_tolerance_bag_seconds": ABSOLUTE_TOLERANCE,
        "independent_real_airport_days": 0, "confidence_intervals_or_p_values_computed": False,
        "strict_nonharm_certified": False, "single_action_causal_attribution": False,
        "limitations": [
            "Eight synthetic parents share a historical group template; bags and method repetitions are not independent airport days.",
            "A positive 0.1% engineering flag is descriptive and does not establish significance, protection, or per-job noninferiority.",
            "Known completion harm and censored unknowns remain explicit even when aggregate cost improves.",
            "Leave-one-parent-out detects arithmetic dependence on a parent; observed progress gaps do not prove a causal stall explanation.",
            "All effects compare whole frozen policies; no single-action causal claim is made.",
            "Physical J excludes synchronously paused controller computation and audit I/O."]}


def write_effects(audit_reference, *, output):
    """Read exactly one bound audit artifact and save a new JSON summary."""
    path = Path(audit_reference["path"])
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == audit_reference["sha256"], "bound_audit_bytes")
    grid = json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)
    result = build_effects(grid)
    result["source_audit"] = copy.deepcopy(audit_reference)
    result["implementation"] = {"path": str(Path(__file__).resolve()),
        "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return {"path": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
