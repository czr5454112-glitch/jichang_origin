"""Offline complete-population review of the frozen prospective grid.

This reader never selects models, starts simulations or edits source evidence.
"""
from __future__ import annotations

from collections import Counter
from bisect import bisect_right
import gzip
import json
import math
from pathlib import Path

from .foundation_airport_action_campaign import digest, read, sha
from .foundation_airport_pair_dataset import window_cost


def load_gz(path):
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def read_run(cycle, spec):
    directory = Path(cycle) / spec["name"]
    row = dict(spec)
    if not (directory / "receipt.json").exists():
        return dict(row, status="not_run")
    receipt = read(directory / "receipt.json")
    plan = read(directory / "plan.json")
    row.update(status=receipt["status"], plan_sha256=sha(directory / "plan.json"),
        receipt_sha256=sha(directory / "receipt.json"),
        input_semantic_sha256=plan["input"]["semantic_sha256"],
        binary_sha256=plan["binary"]["sha256"])
    report = receipt.get("worker", {})
    row["wall_seconds"] = report.get("wall_seconds")
    row["summary"] = report.get("summary")
    row["strict_nonharm_certified"] = False
    result_path = directory / "final_result.json.gz"
    if row["status"] != "complete" or not result_path.exists():
        row["full_window_cost"] = None
        return row
    data, result = read(directory / "input.json"), load_gz(result_path)
    row["full_window_cost"] = window_cost(data, result, start=7200., end=59400.)
    # Independent direct summation against the complete input and exported jobs.
    jobs = {item["business_bag_id"]: item for item in result["jobs"]}
    completions = {item["business_bag_id"]: item["time"] for item in result["receipts"]
        if item["event"] == "UNLOAD_COMPLETE"}
    exported = {identity: item["completed_at"] for identity, item in jobs.items()
        if item["status"] == "completed"}
    if completions != exported:
        raise ValueError("review:completion_receipt_export_mismatch")
    if set(jobs) != {item["business_bag_id"] for item in data["jobs"]}:
        raise ValueError("review:population_changed")
    independent = math.fsum(max(0., min(completions.get(item["business_bag_id"], math.inf), 59400.)
        - max(item["arrival"], 7200.)) for item in data["jobs"])
    if abs(independent-row["full_window_cost"]["backlog_integral_bag_seconds"]) > 1e-6:
        raise ValueError("review:cost_recalculation_mismatch")
    row["independent_cost_recalculation"] = independent
    row["jobs_digest"] = digest(data["jobs"])
    row["initial_trays_digest"] = digest(data["trays"])
    execution_path = directory/"execution_evidence.json.gz"
    if execution_path.exists():
        execution = load_gz(execution_path)
        evidence_counts = Counter()
        prearrival_examples = []
        specifications = {item["business_bag_id"]: item for item in data["jobs"]}
        empty_receipts = {}
        for item in result["receipts"]:
            if item["event"] == "EMPTY_RECEIVED":
                empty_receipts.setdefault(item["tray_id"], []).append(item["time"])
        for times in empty_receipts.values():
            times.sort()
        for selection in execution["rows"]:
            evidence_counts["evaluated_decisions"] += 1
            if not selection["decision_differs"]:
                continue
            evidence_counts["different_proposals"] += 1
            for attempt in selection["attempts"]:
                evidence_counts["different_actual_submissions"] += 1
                matched = all(attempt.get(key) is True for key in (
                    "selected_intent_matches_actual_submission",
                    "request_matches_native_transfer_entity",
                    "native_leg_matches_entity_and_endpoints"))
                if not matched:
                    evidence_counts["different_unverified_execution_links"] += 1
                    continue
                evidence_counts["different_verified_execution_links"] += 1
                evidence_counts["different_with_positive_ack"] += attempt["positive_delivered_ack"]
                evidence_counts["different_with_unique_leg"] += attempt["native_leg"] is not None
                evidence_counts["different_with_first_edge"] += attempt["first_edge_at"] is not None
                evidence_counts["different_with_receipt"] += attempt["received_at"] is not None
                load = attempt["next_load"]
                evidence_counts["different_with_next_load"] += load is not None
                if (load is None or attempt["received_at"] is None
                        or not attempt["positive_delivered_ack"] or attempt["first_edge_at"] is None):
                    continue
                job = specifications[load["business_bag_id"]]
                destination = attempt["actual_request"]["destination"]
                times = empty_receipts.get(attempt["actual_request"]["tray_id"], [])
                last = bisect_right(times, load["time"])-1
                ready = (job["origin"] == destination and attempt["received_at"] < job["arrival"]
                    and last >= 0 and times[last] == attempt["received_at"])
                evidence_counts["ready_before_arrival_of_next_served_job"] += ready
                if ready and len(prearrival_examples) < 5:
                    prearrival_examples.append(dict(request_id=attempt["actual_request"]["request_id"],
                        business_bag_id=load["business_bag_id"], destination=destination,
                        received_at=attempt["received_at"], bag_arrival=job["arrival"],
                        next_load_at=load["time"]))
        row["action_execution_counts"] = dict(evidence_counts)
        row["prearrival_examples"] = prearrival_examples
        row["prearrival_inference_scope"] = (
            "Actual transfer receipt precedes arrival of its next served bag at that loader; "
            "this timing alone does not prove aggregate policy benefit.")
    return row


def compare_runs(cycle, reference, candidate):
    result = dict(reference=reference["name"], candidate=candidate["name"],
        status="unknown_incomplete_branch", advantage_bag_seconds=None,
        strict_nonharm_certified=False)
    if any(row.get("full_window_cost") is None for row in (reference, candidate)):
        return result
    from .foundation_airport_prospective_campaign import compare_runs as verify_native_comparison
    bound = verify_native_comparison(Path(cycle)/reference["name"], Path(cycle)/candidate["name"])
    if bound["status"] != "closed_full_prospective_comparison":
        raise ValueError("review:common_source_and_warmup_comparison_not_closed")
    for key in ("input_semantic_sha256", "binary_sha256", "jobs_digest", "initial_trays_digest"):
        if reference[key] != candidate[key]:
            raise ValueError("review:unmatched_same_resource_comparison:" + key)
    a, b = reference["full_window_cost"], candidate["full_window_cost"]
    gain = a["backlog_integral_bag_seconds"]-b["backlog_integral_bag_seconds"]
    if abs(gain-bound["advantage_bag_seconds"]) > 1e-6:
        raise ValueError("review:independent_pair_gain_mismatch")
    result.update(status="complete_same_resource_comparison", advantage_bag_seconds=gain,
        common_sources_and_full_warmup_verified=True,
        relative_advantage=gain/a["backlog_integral_bag_seconds"],
        completed_delta=b["completed_by_end"]-a["completed_by_end"],
        on_time_delta=b["on_time_by_end"]-a["on_time_by_end"],
        arrived_unfinished_past_deadline_delta=b["arrived_unfinished_past_deadline"]
            - a["arrived_unfinished_past_deadline"])
    from .foundation_airport_behavior_evidence import snapshot_index
    indices = [snapshot_index(load_gz(Path(cycle)/row["name"]/"final_result.json.gz"),
        expected_population=a["physical_population"]) for row in (reference, candidate)]
    counts, incomplete_counts, maximum_harm = Counter(), Counter(), 0.
    for identity in indices[0]["jobs"]:
        first, second = (index["completions"].get(identity) for index in indices)
        if first is None or second is None:
            counts["unknown_incomplete"] += 1
            incomplete_counts["reference_only_finished" if first is not None else
                "candidate_only_finished" if second is not None else "neither_finished"] += 1
        else:
            difference = second-first
            counts["harmed" if difference > 1e-6 else "improved" if difference < -1e-6 else "equal"] += 1
            maximum_harm = max(maximum_harm, difference)
    if sum(counts.values()) != a["physical_population"]:
        raise ValueError("review:per_job_comparison_population")
    result.update(per_job_comparison=dict(counts), incomplete_comparison_breakdown=dict(incomplete_counts),
        maximum_known_delay_seconds=maximum_harm)
    return result


def build_review(cycle):
    cycle = Path(cycle)
    grid = read(cycle/"prospective_evaluation_grid_001.json")
    rows = [read_run(cycle, spec) for spec in grid["rows"]]
    lookup = {(row["batch"], row["fleet"], row["parent_seed"], row["variant"], row["model_seed"]): row
        for row in rows}
    comparisons, interaction = [], []
    for parent in (901, 902):
        base = lookup[("D", 22, parent, "C00", None)]
        forecast = lookup[("D", 22, parent, "C10", None)]
        comparisons.append(compare_runs(cycle, base, forecast))
        for seed in (17, 29, 43):
            no_plan = compare_runs(cycle, base, lookup[("D", 22, parent, "C01", seed)])
            with_plan = compare_runs(cycle, forecast, lookup[("D", 22, parent, "C11", seed)])
            comparisons.extend((no_plan, with_plan))
            a, b = no_plan["advantage_bag_seconds"], with_plan["advantage_bag_seconds"]
            interaction.append(dict(parent_seed=parent, model_seed=seed,
                learning_by_prediction_interaction=None if a is None or b is None else b-a))
        for fleet in (18, 22, 26):
            rules_batch = "D" if fleet == 22 else "G"
            rule = lookup[(rules_batch, fleet, parent, "C10", None)]
            learned = lookup[("G", fleet, parent, "C11", 29)]
            comparisons.append(compare_runs(cycle, rule, learned))
    return dict(schema="g31.airport.prospective_offline_review.v1",
        grid_sha256=sha(cycle/"prospective_evaluation_grid_001.json"),
        rows=rows, comparisons=comparisons, interaction=interaction,
        statuses=dict(Counter(row["status"] for row in rows)),
        independent_parent_count=2, independent_real_airport_days=0,
        all_parents_conditional_synthetic=True, strict_nonharm_certified=False,
        multistep_optimal_Q_established=False,
        limitations=["Synthetic timing shifts share a historical workload template.",
            "Incomplete jobs retain unknown completion comparisons.",
            "Synchronous callbacks do not establish deployment realtime performance."])
