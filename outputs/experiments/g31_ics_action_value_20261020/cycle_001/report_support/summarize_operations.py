"""Independent arithmetic/reporting from one explicit offline-review JSON.

No simulator, model or training import. By default only the supplied review is
read. Explicit --cycle additionally reads closed final artifacts to compare
cross-fleet completions after review; it never runs or fits anything.
--demo uses only hand-written values and writes DUMMY-labelled reports.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "g31.airport.prospective_offline_review.v1"
PARENTS, SEEDS, FLEETS = (901, 902), (17, 29, 43), (18, 22, 26)
POPULATION, TOLERANCE = 28506, 1e-6
METRICS = {
    "completed": ("completed_by_end", 1),
    "on_time": ("on_time_by_end", 1),
    "backlog_integral": ("backlog_integral_bag_seconds", -1),
    "arrived_unfinished_past_deadline": ("arrived_unfinished_past_deadline", -1),
}
LIMITATIONS = [
    "There are two conditional synthetic parent scenarios and zero independent real airport days.",
    "All parents share a historical workload template; model seeds are repeated fits, not extra independent days.",
    "All three primary seeds are retained. No best seed, model or curve is selected using test outcomes.",
    "Positive gain means lower complete-population unfinished-bag integral, not universal per-job improvement.",
    "Incomplete jobs retain unknown completion comparisons. Failed or missing branches are never imputed as zero.",
    "Cross-fleet per-job outcomes are unknown unless --cycle explicitly enables independent final-artifact comparison.",
    "Service-vector/Pareto findings are descriptive over the fixed observed grid, not fleet-replacement certificates.",
    "Candidate N* is restricted to N in {18,22,26} and the preregistered mixed-domain C11 seed 29.",
    "Native physical admission and observed nonharm on completed jobs do not certify shared-resource protection.",
    "These paired-trained contextual action rankers do not establish optimal or multistep RL control.",
    "Synchronous simulation callbacks do not establish real deployment latency or airport SLA compliance.",
]


def require(condition, reason):
    if not condition:
        raise ValueError("operational_summary:" + reason)


def finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()


def key(row):
    return row["batch"], row["fleet"], row["parent_seed"], row["variant"], row["model_seed"]


def expected_slots():
    slots = [("E", n, 801, v, None) for n in (18, 26) for v in ("C00", "C10")]
    for p in PARENTS:
        slots.extend(("D", 22, p, v, None) for v in ("C00", "C10"))
        slots.extend(("D", 22, p, v, s) for v in ("C01", "C11") for s in SEEDS)
        slots.extend(("G", n, p, "C11", 29) for n in FLEETS)
        slots.extend(("G", n, p, v, None) for n in (18, 26) for v in ("C00", "C10"))
    return slots


def index_review(review):
    require(review.get("schema") == SCHEMA, "review_schema")
    require(review.get("independent_parent_count") == 2
        and review.get("independent_real_airport_days") == 0
        and review.get("all_parents_conditional_synthetic") is True, "synthetic_parent_scope")
    rows, comparisons = {}, {}
    for row in review["rows"]:
        require(key(row) not in rows, "duplicate_run_slot")
        rows[key(row)] = row
    for comparison in review["comparisons"]:
        pair = comparison["reference"], comparison["candidate"]
        require(pair not in comparisons, "duplicate_comparison")
        comparisons[pair] = comparison
    return rows, comparisons


def cost(row):
    if row is None or row.get("status") != "complete" or row.get("full_window_cost") is None:
        return None
    result = row["full_window_cost"]
    require(result["physical_population"] == POPULATION and result["label_start"] == 7200.
        and result["label_end"] == 59400., "full_population_window")
    for name, (field, _direction) in METRICS.items():
        value = result[field]
        require(finite(value) and value >= 0., "nonnegative_complete_metric:"+field)
        if name != "backlog_integral":
            require(type(value) is int and value <= POPULATION, "integer_complete_count:"+field)
    require(result["on_time_by_end"] <= result["completed_by_end"], "on_time_subset")
    return result


def row_status(row):
    if row is None:
        return "missing_row"
    return row["status"] if row.get("status") != "complete" else \
        "complete" if row.get("full_window_cost") is not None else "missing_full_cost"


def job_assessment(comparison):
    """A sparse validated Counter may omit zero categories; missing evidence may not."""
    counts = None if comparison is None else comparison.get("per_job_comparison")
    if not isinstance(counts, dict):
        return {"status": "unknown_missing_per_job_evidence", "known_harmed": None,
            "unknown_incomplete": None, "outcome_nonharm": None, "protected_takeover_certified": False}
    categories = ("equal", "improved", "harmed", "unknown_incomplete")
    require(set(counts) <= set(categories) and all(type(v) is int and v >= 0 for v in counts.values())
        and sum(counts.values()) == POPULATION, "complete_per_job_counter")
    normalized = {name: counts.get(name, 0) for name in categories}
    harmed, unknown = normalized["harmed"], normalized["unknown_incomplete"]
    return {"status": "known_harm" if harmed else "unknown_incomplete" if unknown else "observed_no_harm",
        "counts": normalized, "known_harmed": harmed, "unknown_incomplete": unknown,
        "outcome_nonharm": False if harmed else None if unknown else True,
        "maximum_known_delay_seconds": comparison.get("maximum_known_delay_seconds"),
        "incomplete_breakdown": comparison.get("incomplete_comparison_breakdown"),
        "protected_takeover_certified": False}


def service_vector(reference, candidate):
    """Positive oriented changes favor the candidate in every reported metric."""
    a, b = cost(reference), cost(candidate)
    output = {"status": "unknown_incomplete", "meets_aggregate_target": None, "relation": "unknown",
        "reference_status": row_status(reference), "candidate_status": row_status(candidate)}
    if a is None or b is None:
        return output
    require(reference["parent_seed"] == candidate["parent_seed"], "same_resource_comparison_parent")
    for field in ("jobs_digest", "binary_sha256"):
        require(isinstance(reference.get(field), str) and reference[field]
            and reference[field] == candidate.get(field), "same_resource_exogenous_identity:"+field)
    changes, nonworse, strictly_better, strictly_worse = {}, [], [], []
    for name, (field, direction) in METRICS.items():
        oriented = direction*(b[field]-a[field])
        tol = TOLERANCE if name == "backlog_integral" else 0.
        changes[name] = {"reference": a[field], "candidate": b[field],
            "candidate_minus_reference": b[field]-a[field], "oriented_improvement": oriented,
            "nonworse": oriented >= -tol, "strictly_better": oriented > tol}
        nonworse.append(oriented >= -tol)
        strictly_better.append(oriented > tol)
        strictly_worse.append(oriented < -tol)
    relation = ("dominates" if all(nonworse) and any(strictly_better) else
        "equal" if not any(strictly_better) and not any(strictly_worse) else
        "dominated" if not any(strictly_better) and any(strictly_worse) else "tradeoff")
    output.update(status="closed_aggregate_vector", metrics=changes, relation=relation,
        meets_aggregate_target=all(nonworse),
        gain_bag_seconds=a["backlog_integral_bag_seconds"]-b["backlog_integral_bag_seconds"],
        relative_gain=(a["backlog_integral_bag_seconds"]-b["backlog_integral_bag_seconds"])
            / a["backlog_integral_bag_seconds"] if a["backlog_integral_bag_seconds"] > 0 else None,
        runtime_source_equality_established_by_this_vector=False,
        per_job_protection_established_by_aggregate_vector=False)
    return output


def completion_comparison(specifications, reference, candidate):
    """Count every identity; unknown completion is never converted into zero harm."""
    require(set(specifications) == set(reference) == set(candidate), "same_per_job_population")
    counts, incomplete, harmed = Counter(), Counter(), []
    for identity in specifications:
        a, b = reference[identity], candidate[identity]
        require((a is None or finite(a)) and (b is None or finite(b)), "finite_completion_or_unknown")
        if a is None or b is None:
            category = "unknown_incomplete"
            incomplete["reference_only_finished" if a is not None else
                "candidate_only_finished" if b is not None else "neither_finished"] += 1
        else:
            category = "harmed" if b-a > TOLERANCE else "improved" if a-b > TOLERANCE else "equal"
            if category == "harmed":
                harmed.append({"business_bag_id": identity, "reference_completed_at": a,
                    "candidate_completed_at": b, "delay_seconds": b-a})
        counts[category] += 1
    require(sum(counts.values()) == len(specifications), "per_job_population_conservation")
    return {"per_job_comparison": dict(counts), "incomplete_comparison_breakdown": dict(incomplete),
        "maximum_known_delay_seconds": max((r["delay_seconds"] for r in harmed), default=0.),
        "known_harmed_jobs": harmed, "uncompleted_jobs_excluded": 0}


def closed_artifact(cycle, row, cache):
    """Read only two explicitly named final artifacts, after an explicit --cycle."""
    require(cost(row) is not None, "closed_row_before_final_artifact_read")
    if row["name"] in cache:
        return cache[row["name"]]
    cycle = Path(cycle).resolve()
    directory = (cycle/row["name"]).resolve()
    require(directory.parent == cycle, "run_path_must_stay_inside_explicit_cycle")
    input_path, result_path = directory/"input.json", directory/"final_result.json.gz"
    input_raw, result_raw = input_path.read_bytes(), result_path.read_bytes()
    data = json.loads(input_raw)
    result = json.loads(gzip.decompress(result_raw))
    require(digest(data) == row["input_semantic_sha256"], "input_matches_review_semantic_hash")
    specifications = {r["business_bag_id"]: r for r in data["jobs"]}
    jobs = {r["business_bag_id"]: r for r in result["jobs"]}
    require(len(specifications) == len(data["jobs"]) == len(jobs) == len(result["jobs"]) == POPULATION
        and set(specifications) == set(jobs), "all_28506_final_input_identities")
    require(digest(data["jobs"]) == row["jobs_digest"], "jobs_match_review_hash")
    require(result["physical_clock"] == 59400. and result.get("advance", {}).get("status") == "reached"
        and result["advance"].get("horizon_complete") is True, "closed_requested_final_clock")
    receipts = {}
    for event in result.get("receipts", []):
        if event["event"] == "UNLOAD_COMPLETE":
            identity = event["business_bag_id"]
            require(identity not in receipts, "unique_actual_completion_receipt")
            receipts[identity] = event["time"]
    completions = {}
    for identity, job in jobs.items():
        at = job["completed_at"]
        completed = job["status"] == "completed"
        require(finite(at) and completed == (at >= 0.), "export_completion_status")
        if completed:
            require(specifications[identity]["arrival"] <= at <= result["physical_clock"],
                "completion_within_arrival_and_closed_clock")
        completions[identity] = at if completed else None
    require(receipts == {identity: at for identity, at in completions.items() if at is not None},
        "actual_completion_receipts_match_export")
    value = math.fsum(max(0., min(completions[identity] if completions[identity] is not None else math.inf,
        59400.)-max(specification["arrival"], 7200.)) for identity, specification in specifications.items())
    reviewed = cost(row)
    independently = {
        "completed_by_end": len(receipts),
        "on_time_by_end": sum(at <= specifications[identity]["deadline"] for identity, at in receipts.items()),
        "arrived_unfinished_past_deadline": sum(specification["arrival"] <= 59400.
            and specification["deadline"] < 59400. and completions[identity] is None
            for identity, specification in specifications.items()),
    }
    require(abs(value-reviewed["backlog_integral_bag_seconds"]) <= TOLERANCE
        and all(value == reviewed[name] for name, value in independently.items()),
        "independent_final_artifact_service_matches_review")
    cache[row["name"]] = {"specifications": specifications, "completions": completions,
        "sources": {"input": {"path": str(input_path), "sha256": hashlib.sha256(input_raw).hexdigest()},
            "final_result": {"path": str(result_path), "sha256": hashlib.sha256(result_raw).hexdigest()}},
        "initial_trays_semantic_sha256": digest(data["trays"])}
    return cache[row["name"]]


def compare_final_artifacts(cycle, reference, candidate, cache):
    if cost(reference) is None or cost(candidate) is None:
        return None
    first = closed_artifact(cycle, reference, cache)
    second = closed_artifact(cycle, candidate, cache)
    require(first["specifications"] == second["specifications"], "identical_business_jobs_across_fleets")
    require(reference["parent_seed"] == candidate["parent_seed"]
        and reference["binary_sha256"] == candidate["binary_sha256"], "same_parent_and_native_binary")
    comparison = completion_comparison(first["specifications"], first["completions"], second["completions"])
    comparison.update(reference_sources=first["sources"], candidate_sources=second["sources"],
        input_jobs_equal_by_complete_identity_and_specification=True,
        identical_initial_trays_required=False, identical_native_prefix_required=False,
        reference_initial_trays_sha256=first["initial_trays_semantic_sha256"],
        candidate_initial_trays_sha256=second["initial_trays_semantic_sha256"],
        strict_nonharm_certified=False)
    return comparison


def same_resource_comparison(reference, candidate, comparisons):
    output = {"reference": reference["name"] if reference else None,
        "candidate": candidate["name"] if candidate else None, "status": "unknown_incomplete",
        "reference_status": row_status(reference), "candidate_status": row_status(candidate),
        "gain_bag_seconds": None, "per_job": job_assessment(None)}
    if cost(reference) is None or cost(candidate) is None:
        return output
    require(reference["fleet"] == candidate["fleet"], "same_N_required")
    found = comparisons.get((reference["name"], candidate["name"]))
    if found is None or found.get("status") != "complete_same_resource_comparison" \
            or found.get("common_sources_and_full_warmup_verified") is not True:
        output["status"] = "unknown_unverified_same_resource_comparison"
        return output
    vector = service_vector(reference, candidate)
    require(finite(found["advantage_bag_seconds"])
        and abs(found["advantage_bag_seconds"]-vector["gain_bag_seconds"]) <= TOLERANCE,
        "independent_gain_recalculation")
    for field, metric in (("completed_delta", "completed"), ("on_time_delta", "on_time"),
                         ("arrived_unfinished_past_deadline_delta", "arrived_unfinished_past_deadline")):
        require(found[field] == vector["metrics"][metric]["candidate_minus_reference"],
            "independent_service_recalculation:"+field)
    a, b = cost(reference), cost(candidate)
    decomposition = {}
    for field in ("waiting_for_tray_integral_bag_seconds", "loaded_or_processing_integral_bag_seconds"):
        decomposition[field] = a[field]-b[field] if finite(a.get(field)) and finite(b.get(field)) else None
    output.update(status="closed_verified", gain_bag_seconds=vector["gain_bag_seconds"],
        relative_gain=vector["relative_gain"], service_vector=vector,
        cost_gain_decomposition=decomposition, per_job=job_assessment(found),
        current_proposal_and_execution_counts=candidate.get("action_execution_counts"),
        prearrival_examples=candidate.get("prearrival_examples", []),
        prearrival_timing_is_not_aggregate_benefit_proof=True)
    return output


def registered_rule(rows, parent, fleet, variant="C10"):
    return rows.get(("D" if fleet == 22 else "G", fleet, parent, variant, None))


def pareto(rows, parent):
    """Observed aggregate frontiers only; retain failed cells as unresolved."""
    candidates = []
    for fleet in FLEETS:
        candidates.extend(registered_rule(rows, parent, fleet, v) for v in ("C00", "C10"))
        candidates.append(rows.get(("G", fleet, parent, "C11", 29)))
    complete = [row for row in candidates if cost(row) is not None]
    missing = [{"run": r["name"] if r else None, "status": row_status(r)}
        for r in candidates if cost(r) is None]
    result = {"parent_seed": parent, "complete_observed_cells": len(complete),
        "unresolved_cells": missing, "frontier_scope": "complete observed fixed-grid aggregate outcomes only",
        "per_job_nonharm_in_frontier_criteria": False, "certified_fleet_frontier": False}
    for include_fleet, name in ((False, "service_only"), (True, "fleet_and_service")):
        dominating = {}
        for candidate in complete:
            by = []
            for alternative in complete:
                if alternative["name"] == candidate["name"]:
                    continue
                vector = service_vector(candidate, alternative)
                fleet_nonworse = not include_fleet or alternative["fleet"] <= candidate["fleet"]
                fleet_better = include_fleet and alternative["fleet"] < candidate["fleet"]
                if vector["meets_aggregate_target"] and fleet_nonworse \
                        and (vector["relation"] == "dominates" or fleet_better):
                    by.append(alternative["name"])
            dominating[candidate["name"]] = by
        result[name] = {"observed_nondominated": [name for name, by in dominating.items() if not by],
            "dominated_by": dominating, "unresolved_cells_can_change_frontier": bool(missing)}
    return result


def candidate_minimum(points, *, parents, final_artifacts_enabled=False):
    """A descriptive minimum within the fixed grid, never a certification."""
    aggregate, unresolved = [], []
    for fleet in FLEETS:
        relevant = [p for p in points if p["fleet"] == fleet and p["parent_seed"] in parents]
        require(len(relevant) == len(parents), "registered_resource_grid_complete_slots")
        values = [p["against_N22_C10"]["service_vector"]["meets_aggregate_target"] for p in relevant]
        # One known failure rules this fleet out even if another parent is missing.
        if False in values:
            continue
        if all(v is True for v in values):
            aggregate.append(fleet)
        else:
            unresolved.append(fleet)
    known_minimum = min(aggregate) if aggregate else None
    lower_unknown = [n for n in unresolved if known_minimum is None or n < known_minimum]
    aggregate_candidate = known_minimum if known_minimum is not None and not lower_unknown else None
    harm_free, known_harm, unknown_harm = [], [], []
    for fleet in aggregate:
        relevant = [p for p in points if p["fleet"] == fleet and p["parent_seed"] in parents]
        harms = [p["against_N22_C10"]["per_job"]["known_harmed"] for p in relevant]
        if any(h is not None and h > 0 for h in harms):
            known_harm.append(fleet)
        elif any(h is None for h in harms):
            unknown_harm.append(fleet)
        else:
            harm_free.append(fleet)
    minimum_harm_free = min(harm_free) if harm_free else None
    lower_eligibility_unknown = [n for n in unresolved+unknown_harm
        if minimum_harm_free is None or n < minimum_harm_free]
    candidate = minimum_harm_free if minimum_harm_free is not None and not lower_eligibility_unknown else None
    blockers = ["shared_resource_per_job_protection_not_certified",
        "two_conditional_synthetic_scenarios_are_not_field_acceptance"]
    relevant_jobs = [r["against_N22_C10"]["per_job"] for r in points
        if r["parent_seed"] in parents and r["fleet"] in aggregate]
    if any(r["known_harmed"] is not None and r["known_harmed"] > 0 for r in relevant_jobs):
        blockers.append("known_per_job_completion_harm_at_aggregate_qualifying_fleet")
    if any(r["unknown_incomplete"] is None or r["unknown_incomplete"] > 0 for r in relevant_jobs):
        blockers.append("incomplete_or_missing_per_job_comparisons_remain_unknown")
    if not final_artifacts_enabled:
        blockers.append("cross_fleet_per_job_outcomes_not_requested_from_final_artifacts")
    return {"parents": list(parents), "registered_fleets": list(FLEETS),
        "aggregate_qualifying_fleets": aggregate, "unresolved_fleets": unresolved,
        "minimum_among_observed_qualifying_fleets": known_minimum,
        "aggregate_candidate_N_star_within_registered_grid": aggregate_candidate,
        "qualifying_fleets_without_known_harm": harm_free,
        "aggregate_qualifiers_blocked_by_known_harm": known_harm,
        "aggregate_qualifiers_with_unknown_harm_counts": unknown_harm,
        "candidate_N_star_within_registered_grid": candidate,
        "candidate_definition": "aggregate target and no known completion harm, within fixed grid; incomplete jobs still block certification",
        "status": "candidate_without_known_harm_but_uncertified" if candidate is not None else
            "unknown_due_to_unclosed_or_unassessed_cells" if unresolved or unknown_harm else
            "no_qualifier_after_known_harm_check",
        "lower_fleets_unresolved": lower_unknown, "certified_N_star": None,
        "lower_fleets_with_unresolved_candidate_eligibility": lower_eligibility_unknown,
        "certification_blockers": blockers,
        "is_model_or_seed_selection": False, "is_deployment_recommendation": False}


def summarize(review, *, cycle=None):
    rows, comparisons = index_review(review)
    primary, interactions, resources, reactive_comparisons = [], [], [], []
    artifact_cache = {}
    recorded_interaction = {(r["parent_seed"], r["model_seed"]): r["learning_by_prediction_interaction"]
        for r in review.get("interaction", [])}
    for parent in PARENTS:
        for seed in SEEDS:
            gains = {}
            for reference_variant, candidate_variant in (("C00", "C01"), ("C10", "C11")):
                reference = rows.get(("D", 22, parent, reference_variant, None))
                candidate = rows.get(("D", 22, parent, candidate_variant, seed))
                if candidate is not None:
                    require(candidate["training_domain"] == "primary_22", "primary_training_domain")
                comparison = same_resource_comparison(reference, candidate, comparisons)
                primary.append({"parent_seed": parent, "model_seed": seed,
                    "contrast": candidate_variant+"_vs_"+reference_variant, **comparison})
                gains[candidate_variant] = comparison["gain_bag_seconds"]
            interaction = None if any(v is None for v in gains.values()) else gains["C11"]-gains["C01"]
            if (parent, seed) in recorded_interaction:
                observed = recorded_interaction[(parent, seed)]
                require((interaction is None and observed is None) or
                    (interaction is not None and finite(observed) and abs(interaction-observed) <= TOLERANCE),
                    "independent_interaction_recalculation")
            interactions.append({"parent_seed": parent, "model_seed": seed, "interaction_bag_seconds": interaction,
                "formula": "[J(C10)-J(C11)] - [J(C00)-J(C01)]",
                "interpretation": "additional learning gain with legal forecast information; no pooled causal generalization"})
            base = rows.get(("D", 22, parent, "C00", None))
            forecast = rows.get(("D", 22, parent, "C10", None))
            learned = rows.get(("D", 22, parent, "C11", seed))
            absolute = service_vector(base, learned)
            forecast_effect = service_vector(base, forecast)
            gain_absolute = absolute.get("gain_bag_seconds")
            gain_forecast_rule = forecast_effect.get("gain_bag_seconds")
            cost_pattern = "unknown"
            if gain_absolute is not None and gains["C11"] is not None:
                better_absolute, better_same_info = gain_absolute > TOLERANCE, gains["C11"] > TOLERANCE
                cost_pattern = ("beats_both_C10_and_C00_on_cost" if better_absolute and better_same_info else
                    "beats_C10_but_does_not_beat_C00_on_cost" if better_same_info else
                    "beats_C00_but_does_not_beat_C10_on_cost" if better_absolute else
                    "neither_cost_benchmark_improved")
            reactive_comparisons.append({"parent_seed": parent, "model_seed": seed,
                "contrast": "C11_vs_C00", "service_vector": absolute,
                "same_information_gain_C11_vs_C10": gains["C11"],
                "C10_vs_C00_gain_bag_seconds": gain_forecast_rule,
                "C10_cost_worse_than_C00": None if gain_forecast_rule is None else gain_forecast_rule < -TOLERANCE,
                "cost_pattern": cost_pattern, "scope": "full-row endpoint arithmetic; primary attribution remains C11 versus C10",
                "positive_against_C10_alone_establishes_general_value": False})
        for fleet in FLEETS:
            candidate = rows.get(("G", fleet, parent, "C11", 29))
            if candidate is not None:
                require(candidate["training_domain"] == "mixed_18_22_26", "resource_training_domain")
            same = same_resource_comparison(registered_rule(rows, parent, fleet), candidate, comparisons)
            fixed_reference = registered_rule(rows, parent, 22)
            vector = service_vector(fixed_reference, candidate)
            individual = compare_final_artifacts(cycle, fixed_reference, candidate, artifact_cache) if cycle else None
            jobs = job_assessment(individual) if individual is not None else same["per_job"] if fleet == 22 else job_assessment(None)
            resources.append({"parent_seed": parent, "fleet": fleet, "model_seed": 29,
                "training_domain": "mixed_18_22_26", "candidate": candidate["name"] if candidate else None,
                "candidate_status": row_status(candidate), "against_same_N_C10": same,
                "against_N22_C10": {"reference": fixed_reference["name"] if fixed_reference else None,
                    "service_vector": vector, "per_job": jobs, "certified_replacement": False,
                    "known_harm_blocks_certification": jobs["known_harmed"] is not None and jobs["known_harmed"] > 0,
                    "unknown_harm_blocks_certification": jobs["unknown_incomplete"] is None or jobs["unknown_incomplete"] > 0,
                    "incomplete_jobs_block_certification": jobs["unknown_incomplete"] is None or jobs["unknown_incomplete"] > 0,
                    "cross_fleet_individual_comparison_available": individual is not None or
                        (fleet == 22 and same["status"] == "closed_verified"),
                    "independent_final_artifact_comparison": individual}})
    unresolved = [{"run": row["name"], "slot": list(k), "status": row_status(row)}
        for k, row in rows.items() if cost(row) is None]
    missing = [list(slot) for slot in expected_slots() if slot not in rows]
    return {"schema": "g31.prospective.independent_operational_summary.v1",
        "dummy_only": bool(review.get("dummy_data")), "grid_sha256": review.get("grid_sha256"),
        "population": POPULATION, "cost_window_seconds": [7200., 59400.],
        "positive_gain_definition": "reference integral minus candidate integral in bag-seconds",
        "numerical_cost_tolerance_bag_seconds": TOLERANCE,
        "primary_comparisons": primary, "primary_vs_reactive_baseline": reactive_comparisons,
        "learning_by_prediction_interactions": interactions,
        "resource_comparisons": resources, "aggregate_pareto": [pareto(rows, p) for p in PARENTS],
        "candidate_N_star": [candidate_minimum(resources, parents=(p,), final_artifacts_enabled=cycle is not None) for p in PARENTS]
            + [candidate_minimum(resources, parents=PARENTS, final_artifacts_enabled=cycle is not None)],
        "run_coverage": {"declared_rows": len(rows), "expected_registered_slots": len(expected_slots()),
            "statuses": dict(Counter(row_status(row) for row in rows.values())),
            "failed_missing_or_incomplete_rows": unresolved, "missing_registered_slots": missing,
            "failed_branches_excluded_from_coverage": False, "missing_values_imputed": False},
        "independent_parent_count": 2, "independent_real_airport_days": 0,
        "best_seed_selected": False, "primary_seeds_are_independent_days": False,
        "strict_nonharm_certified": False, "multistep_optimal_RL_established": False,
        "limitations": LIMITATIONS}


def number_text(value, digits=3):
    return "UNKNOWN" if value is None else f"{value:+,.{digits}f}"


def text_report(summary):
    title = "DUMMY — NOT EXPERIMENT RESULTS\n\n" if summary["dummy_only"] else ""
    lines = [title+"Airport ICS: independent operational summary", "",
        "Population: 28,506; cost interval: 7,200–59,400 seconds.",
        "Positive cost gain favors the candidate. Two conditional synthetic parents; zero independent airport days.",
        "All primary seeds are listed; no seed selection or pooling into six independent days.", "",
        "PRIMARY SAME-RESOURCE COMPARISONS"]
    for row in summary["primary_comparisons"]:
        jobs = row["per_job"]
        line = (f"P{row['parent_seed']} seed{row['model_seed']} {row['contrast']}: "
            f"gain={number_text(row['gain_bag_seconds'])} bag-s; status={row['status']}; "
            f"known harmed={jobs['known_harmed']}; unknown incomplete={jobs['unknown_incomplete']}.")
        if row["status"] == "closed_verified":
            metrics = row["service_vector"]["metrics"]
            relative = row["relative_gain"]
            line += (f" Relative gain={number_text(None if relative is None else 100.*relative, 6)}%; "
                f"completed delta={metrics['completed']['candidate_minus_reference']:+d}; "
                f"on-time delta={metrics['on_time']['candidate_minus_reference']:+d}; "
                f"past-deadline unfinished delta={metrics['arrived_unfinished_past_deadline']['candidate_minus_reference']:+d}; "
                f"service relation={row['service_vector']['relation']}.")
        lines.append(line)
    lines.extend(["", "LEARNING × PREDICTION INTERACTION",
        "Interaction = [J(C10)-J(C11)] - [J(C00)-J(C01)]."])
    lines.extend(f"P{r['parent_seed']} seed{r['model_seed']}: {number_text(r['interaction_bag_seconds'])} bag-s."
        for r in summary["learning_by_prediction_interactions"])
    lines.extend(["", "C11 VERSUS REACTIVE C00: ENDPOINT ARITHMETIC",
        "Primary learning attribution remains C11 versus same-information C10. Improvement over C10 alone does not establish improvement over C00."])
    for row in summary["primary_vs_reactive_baseline"]:
        vector = row["service_vector"]
        metrics = vector.get("metrics", {})
        lines.append(f"P{row['parent_seed']} seed{row['model_seed']}: C11-vs-C00 gain="
            f"{number_text(vector.get('gain_bag_seconds'))} bag-s; completed delta="
            f"{metrics.get('completed', {}).get('candidate_minus_reference')}; on-time delta="
            f"{metrics.get('on_time', {}).get('candidate_minus_reference')}; "
            f"C10-vs-C00 gain={number_text(row['C10_vs_C00_gain_bag_seconds'])} bag-s; pattern={row['cost_pattern']}.")
    lines.extend(["", "RESOURCE CHECKS: FIXED MIXED-DOMAIN C11 SEED 29"])
    for row in summary["resource_comparisons"]:
        same, target = row["against_same_N_C10"], row["against_N22_C10"]
        vector = target["service_vector"]
        lines.append(f"P{row['parent_seed']} N={row['fleet']}: vs same-N C10 gain="
            f"{number_text(same['gain_bag_seconds'])} bag-s ({same['status']}); "
            f"vs N22 C10 gain={number_text(vector.get('gain_bag_seconds'))} bag-s; "
            f"aggregate target={vector['meets_aggregate_target']}; relation={vector['relation']}; "
            f"per-job assessment={target['per_job']['status']}; certified replacement=False.")
    lines.extend(["", "CANDIDATE MINIMUM WITHIN REGISTERED {18,22,26}; NO CERTIFIED N*"])
    for row in summary["candidate_N_star"]:
        lines.append(f"Parents {row['parents']}: aggregate qualifiers={row['aggregate_qualifying_fleets']}; "
            f"unresolved fleets={row['unresolved_fleets']}; candidate N*="
            f"{row['candidate_N_star_within_registered_grid']}; aggregate-only minimum="
            f"{row['aggregate_candidate_N_star_within_registered_grid']}; known-harm blockers="
            f"{row['aggregate_qualifiers_blocked_by_known_harm']}; status={row['status']}; certified N*=None.")
    lines.extend(["", "OBSERVED AGGREGATE PARETO FRONTIERS"])
    for row in summary["aggregate_pareto"]:
        lines.append(f"P{row['parent_seed']}: service-only={row['service_only']['observed_nondominated']}")
        lines.append(f"P{row['parent_seed']}: fleet+service={row['fleet_and_service']['observed_nondominated']}")
        lines.append(f"Unresolved cells={len(row['unresolved_cells'])}; unclosed cells may change these frontiers.")
    coverage = summary["run_coverage"]
    lines.extend(["", "FAILURES / MISSINGNESS", f"Statuses: {coverage['statuses']}"])
    lines.extend(f"{r['run']}: {r['status']}" for r in coverage["failed_missing_or_incomplete_rows"])
    lines.extend(f"Missing registered slot: {slot}" for slot in coverage["missing_registered_slots"])
    lines.extend(["", "LIMITATIONS", *[f"- {line}" for line in summary["limitations"]]])
    return "\n".join(lines)+"\n"


def dummy_review():
    """Deliberately includes a failed seed, missing fleet, known harm and unknowns."""
    rows, comparisons, interaction = [], [], []
    for batch, fleet, parent, variant, seed in expected_slots():
        value = 10_000_000.-(fleet-22)*5000-(1000 if variant == "C10" else 2000 if variant == "C11" else 500 if variant == "C01" else 0)
        status = "failed" if batch == "D" and parent == 901 and variant == "C11" and seed == 29 else \
            "not_run" if batch == "G" and parent == 902 and fleet == 18 and variant == "C11" else "complete"
        rows.append({"name": f"DUMMY_{batch}_N{fleet}_P{parent}_{variant}_S{seed}", "batch": batch,
            "fleet": fleet, "parent_seed": parent, "variant": variant, "model_seed": seed,
            "training_domain": ("primary_22" if batch == "D" else "mixed_18_22_26")
                if variant in ("C01", "C11") else None,
            "status": status, "jobs_digest": f"DUMMY_JOBS_{parent}", "binary_sha256": "DUMMY_BINARY",
            "full_window_cost": None if status != "complete" else {
                "physical_population": POPULATION, "label_start": 7200., "label_end": 59400.,
                "backlog_integral_bag_seconds": value, "completed_by_end": 1000+(fleet-22)*10+(2 if variant == "C11" else 0),
                "on_time_by_end": 100+(fleet-22), "arrived_unfinished_past_deadline": 18000-(fleet-22)*10,
                "waiting_for_tray_integral_bag_seconds": value-1000.,
                "loaded_or_processing_integral_bag_seconds": 1000.}})
    lookup = {key(row): row for row in rows}
    def add(reference, candidate):
        a, b = cost(reference), cost(candidate)
        row = {"reference": reference["name"], "candidate": candidate["name"],
            "status": "unknown_incomplete_branch", "advantage_bag_seconds": None}
        if a is not None and b is not None:
            row.update(status="complete_same_resource_comparison", common_sources_and_full_warmup_verified=True,
                advantage_bag_seconds=a["backlog_integral_bag_seconds"]-b["backlog_integral_bag_seconds"],
                completed_delta=b["completed_by_end"]-a["completed_by_end"],
                on_time_delta=b["on_time_by_end"]-a["on_time_by_end"],
                arrived_unfinished_past_deadline_delta=b["arrived_unfinished_past_deadline"]-a["arrived_unfinished_past_deadline"],
                per_job_comparison={"equal": 1000, "improved": 10, "harmed": 2, "unknown_incomplete": POPULATION-1012},
                maximum_known_delay_seconds=5., incomplete_comparison_breakdown={"neither_finished": POPULATION-1012})
        comparisons.append(row)
        return row["advantage_bag_seconds"]
    for parent in PARENTS:
        for seed in SEEDS:
            a = add(lookup[("D",22,parent,"C00",None)], lookup[("D",22,parent,"C01",seed)])
            b = add(lookup[("D",22,parent,"C10",None)], lookup[("D",22,parent,"C11",seed)])
            interaction.append({"parent_seed": parent, "model_seed": seed,
                "learning_by_prediction_interaction": None if a is None or b is None else b-a})
        for fleet in FLEETS:
            add(registered_rule(lookup,parent,fleet), lookup[("G",fleet,parent,"C11",29)])
    return {"schema": SCHEMA, "dummy_data": True, "rows": rows, "comparisons": comparisons,
        "interaction": interaction, "independent_parent_count": 2, "independent_real_airport_days": 0,
        "all_parents_conditional_synthetic": True, "strict_nonharm_certified": False}


def write_summary(review, output, *, source, demo=False, cycle=None):
    require(bool(review.get("dummy_data")) == demo, "explicit_dummy_mode")
    require(not demo or cycle is None, "dummy_must_not_read_formal_cycle_artifacts")
    result = summarize(review, cycle=cycle)
    result["source_review"] = source
    result["summarizer"] = {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)}
    result["execution_scope"] = {"raw_run_files_read": cycle is not None,
        "explicit_final_artifact_cycle": str(Path(cycle).resolve()) if cycle else None,
        "new_native_jobs": 0, "fit_calls": 0,
        "artifact_scope": "only input.json/final_result.json.gz of closed registered resource/22C10 rows"
            if cycle else "supplied review JSON only"}
    output = Path(output)
    require(not output.exists(), "fresh_output_required")
    output.mkdir(parents=True)
    prefix = "DUMMY_" if demo else ""
    for suffix, content in (("operational_summary.json", json.dumps(result, indent=2, allow_nan=False)),
                            ("operational_summary.txt", text_report(result))):
        (output/(prefix+suffix)).write_text(content, encoding="utf8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--input", type=Path)
    choice.add_argument("--demo", action="store_true")
    parser.add_argument("--cycle", type=Path,
        help="Explicit opt-in after final review: independently compare cross-fleet final completion artifacts")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.demo:
        review, source = dummy_review(), {"kind": "hand_written_dummy", "formal_DG_outcomes_read": False}
    else:
        review = json.loads(args.input.read_text(encoding="utf8"))
        source = {"path": str(args.input.resolve()), "sha256": sha(args.input)}
    report = write_summary(review, args.output, source=source, demo=args.demo, cycle=args.cycle)
    print(json.dumps({"dummy_only": report["dummy_only"], "primary_comparisons": len(report["primary_comparisons"]),
        "resource_comparisons": len(report["resource_comparisons"]), "output": str(args.output.resolve())}))


if __name__ == "__main__":
    main()
