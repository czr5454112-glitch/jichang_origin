"""Portable standard-library audit of included files and full-population costs.

Extract the review ZIP, then run:
  python report_support/audit_bundle.py --root . --output portable_audit.json

Only paths explicitly included in bundle_manifest.json are opened. Omitted
callback streams, repeated segments and source copies have inventory hashes,
but this program cannot verify their absent bytes or full callback semantics.
Pair-training datasets and witnesses are hash checked, not refitted or replayed.
This audit never imports project code, opens a native simulator or fits a model.
"""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import sys


MANIFEST_SCHEMA = "g31.portable_airport_review_bundle.v1"
PRODUCTION_POPULATION = 28506
PRODUCTION_WINDOW = (7200., 59400.)
TOLERANCE = 1e-6


def require(value, message):
    if not value:
        raise ValueError("portable_audit:" + message)


def finite(value, context):
    require(type(value) in (int, float) and math.isfinite(value), "nonfinite:" + context)
    return float(value)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_path(root, text):
    require(type(text) is str and text and "\\" not in text and ":" not in text,
            "relative_forward_slash_path_required")
    value = PurePosixPath(text)
    require(not value.is_absolute() and all(part not in ("", ".", "..") for part in value.parts)
            and str(value) == text, "unsafe_or_noncanonical_path:" + text)
    result = (root / Path(*value.parts)).resolve()
    require(result.is_relative_to(root), "path_escapes_bundle:" + text)
    return result


def load_json(path):
    with (gzip.open(path, "rt", encoding="utf8") if path.name.endswith(".gz")
          else path.open("r", encoding="utf8")) as stream:
        return json.load(stream)


def compare_value(actual, expected, context):
    if type(actual) in (int, float) and type(expected) in (int, float):
        require(math.isfinite(actual) and math.isfinite(expected)
                and abs(actual - expected) <= TOLERANCE, "review_mismatch:" + context)
    else:
        require(actual == expected, "review_mismatch:" + context)


def compare_counts(actual, expected, context):
    require(type(expected) is dict, "review_count_mapping:" + context)
    for key in set(actual) | set(expected):
        require(type(expected.get(key, 0)) is int and expected.get(key, 0) >= 0,
                "invalid_review_count:" + context)
        compare_value(actual.get(key, 0), expected.get(key, 0), context + "." + key)


def complete_cost(data, result, *, population, start, end):
    """Recompute from every offered job and actual arrival/completion receipts."""
    require(type(data.get("jobs")) is list and len(data["jobs"]) == population, "full_offered_population")
    specifications = {row["business_bag_id"]: row for row in data["jobs"]}
    jobs = {row["business_bag_id"]: row for row in result["jobs"]}
    require(len(specifications) == len(jobs) == len(result["jobs"]) == population
            and set(specifications) == set(jobs), "unique_unchanged_business_identities")
    clock = finite(result["physical_clock"], "physical_clock")
    require(result["advance"]["status"] == "reached"
            and result["advance"]["horizon_complete"] is True and clock >= end,
            "closed_native_endpoint_required")
    arrivals, completions, loads = {}, {}, {}
    for receipt in result["receipts"]:
        at = finite(receipt["time"], "receipt.time")
        require(0 <= at <= clock, "receipt_outside_actual_snapshot")
        event = receipt["event"]
        if event not in ("BAG_ARRIVAL", "UNLOAD_COMPLETE", "LOAD_START"):
            continue
        identity = receipt["business_bag_id"]
        require(identity in jobs, "receipt_for_unknown_job")
        target = arrivals if event == "BAG_ARRIVAL" else completions if event == "UNLOAD_COMPLETE" else loads
        require(identity not in target, "duplicate_" + event + ":" + identity)
        target[identity] = at
    contributions, arrived_by_end, completed_by_end = [], {}, {}
    for identity, specification in specifications.items():
        arrival = finite(specification["arrival"], "input.arrival")
        deadline = finite(specification["deadline"], "input.deadline")
        require(arrival >= 0 and (identity in arrivals) == (arrival <= clock),
                "complete_actual_arrival_population")
        if identity in arrivals:
            require(arrivals[identity] == arrival, "input_arrival_receipt_mismatch")
        job = jobs[identity]
        exported = finite(job["completed_at"], "export.completed_at")
        require((identity in arrivals) == (job["status"] != "unreleased"), "arrival_status_mismatch")
        require((exported >= 0) == (identity in completions) == (job["status"] == "completed"),
                "completion_receipt_export_mismatch")
        if identity in completions:
            require(arrival <= completions[identity] == exported <= clock, "completion_clock_mismatch")
        if identity in loads:
            require(arrival <= loads[identity] <= completions.get(identity, clock),
                    "actual_load_clock_mismatch")
        completion = completions.get(identity, math.inf)
        contributions.append(max(0., min(completion, end) - max(arrival, start)))
        if arrival <= end:
            arrived_by_end[identity] = arrival
        if completion <= end:
            completed_by_end[identity] = completion
    require(result["population"]["observed"] == len(arrivals)
            and result["population"]["completed"] == len(completions), "native_population_receipt_counts")
    integral = math.fsum(contributions)
    unknown = len(arrived_by_end) - len(completed_by_end)
    complete_load_evidence = all(row["status"] in ("unreleased", "waiting_for_tray") or identity in loads
                                 for identity, row in jobs.items())
    waiting = (math.fsum(max(0., min(loads.get(identity, math.inf), end)
                             - max(specification["arrival"], start))
                        for identity, specification in specifications.items())
               if complete_load_evidence else None)
    cost = {
        "label_start": start, "label_end": end, "horizon_seconds": end - start,
        "backlog_integral_bag_seconds": integral, "target_return": -integral,
        "physical_population": population, "arrived_by_end": len(arrived_by_end),
        "not_yet_arrived_by_end": population - len(arrived_by_end),
        "completed_by_end": len(completed_by_end), "arrived_unfinished_by_end": unknown,
        "on_time_by_end": sum(at <= specifications[identity]["deadline"]
                              for identity, at in completed_by_end.items()),
        "arrived_unfinished_past_deadline": sum(identity not in completed_by_end
            and specification["deadline"] < end and identity in arrived_by_end
            for identity, specification in specifications.items()),
        "completion_times_unknown_for_arrived": unknown, "completion_times_imputed": False,
        "right_censored_for_integral_only": True, "uncompleted_jobs_excluded": 0,
        "waiting_for_tray_integral_bag_seconds": waiting,
        "loaded_or_processing_integral_bag_seconds": None if waiting is None else integral - waiting,
        "wait_load_decomposition_status": "actual_LOAD_START_receipts" if complete_load_evidence
            else "unknown_missing_actual_load_start",
        "per_job_nonharm_certified": False,
    }
    return cost, {identity: at for identity, at in completions.items() if at <= end}, set(jobs)


def audit(root, *, dummy_test=False):
    root = Path(root).resolve()
    manifest_path = root / "bundle_manifest.json"
    manifest = load_json(manifest_path)
    require(manifest.get("schema") == MANIFEST_SCHEMA, "manifest_schema")
    require(bool(manifest.get("dummy_data")) == dummy_test, "explicit_dummy_mode_must_match_manifest")
    if dummy_test:
        require("DUMMY" in manifest.get("dummy_notice", ""), "unambiguous_dummy_notice_required")
        population = manifest["dummy_contract"]["population"]
        start, end = manifest["dummy_contract"]["cost_window"]
        require(type(population) is int and population > 0 and 0 <= start < end, "dummy_contract")
    else:
        population = PRODUCTION_POPULATION
        start, end = PRODUCTION_WINDOW
    entries, verified, excluded = {}, [], []
    for item in manifest["files"]:
        path = relative_path(root, item["path"])
        require(item["path"] not in entries and type(item["included"]) is bool, "unique_manifest_file")
        require(type(item["sha256"]) is str and len(item["sha256"]) == 64
                and all(c in "0123456789abcdef" for c in item["sha256"]), "file_sha256_shape")
        entries[item["path"]] = item
        if not item["included"]:
            excluded.append({key: item[key] for key in ("path", "sha256", "size", "kind", "reason")
                             if key in item})
            continue
        require(path.is_file(), "included_file_missing:" + item["path"])
        actual = sha256_file(path)
        require(actual == item["sha256"], "file_sha256_mismatch:" + item["path"])
        if "size" in item:
            require(type(item["size"]) is int and path.stat().st_size == item["size"],
                    "file_size_mismatch:" + item["path"])
        verified.append({"path": item["path"], "sha256": actual, "size": path.stat().st_size})

    def included(path):
        require(type(path) is str and path in entries and entries[path]["included"],
                "required_artifact_not_included:" + str(path))
        return relative_path(root, path)

    review_ref = manifest["review"]
    review = load_json(included(review_ref["path"]))
    require(bool(review.get("dummy_data")) == dummy_test, "review_dummy_scope")
    if not dummy_test:
        require(review.get("independent_real_airport_days") == 0
                and review.get("all_parents_conditional_synthetic") is True,
                "synthetic_scope_must_not_claim_real_days")
    review_rows = review[review_ref.get("rows_key", "rows")]
    saved = {row["name"]: row for row in review_rows if row["batch"] in ("E", "D", "G")}
    require(len(saved) == sum(row["batch"] in ("E", "D", "G") for row in review_rows), "unique_review_runs")
    run_specs = manifest["runs"]
    require(len({row["name"] for row in run_specs}) == len(run_specs)
            and {row.get("review_row", row["name"]) for row in run_specs} == set(saved),
            "all_prospective_success_failure_and_not_run_rows_required")
    computed, outputs = {}, []
    for spec in run_specs:
        require(spec["batch"] in ("E", "D", "G"), "only_full_prospective_runs_in_cost_audit")
        row = saved[spec.get("review_row", spec["name"])]
        require(row["batch"] == spec["batch"] and row["status"] == spec["status"], "manifest_review_run_identity")
        status = spec["status"]
        if status != "not_run":
            receipt = load_json(included(spec["receipt"]))
            plan_path = included(spec["plan"])
            plan = load_json(plan_path)
            require(receipt["status"] == status and receipt["plan_sha256"] == sha256_file(plan_path),
                    "actual_receipt_plan_status_binding")
            require(plan["name"] == spec["name"] and plan["batch"] == spec["batch"], "plan_cell_identity")
            require(plan["cost_window"] == [start, end] and plan["horizon"] == end, "fixed_prospective_window")
        if status != "complete":
            require(row.get("full_window_cost") is None, "incomplete_run_must_not_have_full_cost")
            computed[spec["name"]] = None
            outputs.append({"name": spec["name"], "status": status, "full_window_cost": None,
                            "benefit_eligible": False, "completion_comparisons": "unknown"})
            continue
        input_path, result_path = included(spec["input"]), included(spec["final_result"])
        require(plan["input"]["sha256"] == sha256_file(input_path), "plan_input_file_binding")
        data, result = load_json(input_path), load_json(result_path)
        cost, completions, identities = complete_cost(data, result, population=population, start=start, end=end)
        expected = row.get("full_window_cost")
        require(type(expected) is dict, "complete_run_requires_saved_cost")
        for key, value in cost.items():
            require(key in expected, "saved_cost_field_missing:" + key)
            compare_value(value, expected[key], spec["name"] + "." + key)
        if "independent_cost_recalculation" in row:
            compare_value(cost["backlog_integral_bag_seconds"], row["independent_cost_recalculation"],
                          spec["name"] + ".independent_cost")
        computed[spec["name"]] = {
            "cost": cost, "completions": completions, "identities": identities,
            "input_sha256": sha256_file(input_path), "binary_sha256": plan["binary"]["sha256"],
        }
        outputs.append({"name": spec["name"], "status": "complete", "full_window_cost": cost,
                        "cost_matches_saved_review": True, "benefit_eligible": True})

    comparisons = []
    for row in review[review_ref.get("comparisons_key", "comparisons")]:
        names = row["reference"], row["candidate"]
        require(all(name in computed for name in names), "comparison_run_not_audited")
        first, second = (computed[name] for name in names)
        if first is None or second is None:
            require(row["status"] == "unknown_incomplete_branch" and row.get("advantage_bag_seconds") is None,
                    "incomplete_branch_cannot_support_benefit")
            comparisons.append({"reference": names[0], "candidate": names[1],
                "status": "unknown_incomplete_branch", "advantage_bag_seconds": None})
            continue
        require(first["input_sha256"] == second["input_sha256"]
                and first["binary_sha256"] == second["binary_sha256"]
                and first["identities"] == second["identities"], "comparison_physical_inputs_differ")
        require(row["status"] == "complete_same_resource_comparison", "complete_comparison_status")
        a, b = first["cost"], second["cost"]
        gain = a["backlog_integral_bag_seconds"] - b["backlog_integral_bag_seconds"]
        compare_value(gain, row["advantage_bag_seconds"], "comparison.gain")
        for key, value in {
            "relative_advantage": gain / a["backlog_integral_bag_seconds"]
                if a["backlog_integral_bag_seconds"] else None,
            "completed_delta": b["completed_by_end"] - a["completed_by_end"],
            "on_time_delta": b["on_time_by_end"] - a["on_time_by_end"],
            "arrived_unfinished_past_deadline_delta": b["arrived_unfinished_past_deadline"]
                - a["arrived_unfinished_past_deadline"],
        }.items():
            compare_value(value, row.get(key), "comparison." + key)
        counts, unknown, maximum_harm = Counter(), Counter(), 0.
        for identity in first["identities"]:
            left, right = first["completions"].get(identity), second["completions"].get(identity)
            if left is None or right is None:
                counts["unknown_incomplete"] += 1
                unknown["reference_only_finished" if left is not None else
                        "candidate_only_finished" if right is not None else "neither_finished"] += 1
            else:
                delta = right - left
                counts["harmed" if delta > TOLERANCE else "improved" if delta < -TOLERANCE else "equal"] += 1
                maximum_harm = max(maximum_harm, delta)
        require(sum(counts.values()) == population, "complete_per_job_comparison_population")
        compare_counts(counts, row["per_job_comparison"], "comparison.per_job")
        compare_counts(unknown, row["incomplete_comparison_breakdown"], "comparison.unknown_breakdown")
        compare_value(maximum_harm, row["maximum_known_delay_seconds"], "comparison.maximum_delay")
        comparisons.append({"reference": names[0], "candidate": names[1],
            "status": "complete_cost_and_job_comparison_recomputed", "advantage_bag_seconds": gain,
            "per_job_comparison": dict(counts), "incomplete_comparison_breakdown": dict(unknown),
            "maximum_known_delay_seconds": maximum_harm})
    return {
        "schema": "g31.portable_airport_bundle_audit.v1", "status": "passed_included_hashes_and_complete_costs",
        "dummy_only": dummy_test, "manifest_sha256": sha256_file(manifest_path),
        "verified_included_files": verified, "excluded_inventory_not_verified": excluded,
        "production_contract": {"population": population, "cost_window": [start, end]},
        "runs": outputs, "comparisons": comparisons,
        "incomplete_branches_given_benefit": False, "completion_times_imputed": False,
        "full_callback_stream_coverage_claimed": False, "callback_stream_semantics_audited": False,
        "native_replayed": False, "models_refitted": False, "independent_real_airport_days": 0,
        "scope": [
            "Only manifest files marked included were byte-verified.",
            "Complete E/D/G costs and all-job completion comparisons were recomputed from exported jobs and receipts.",
            "Omitted callback, segment and source bytes were not opened or verified.",
            "Hashes of included witnesses, paired datasets and model artifacts do not establish full callback coverage.",
            "This script does not replay native physics, revalidate every policy decision or prove per-job nonharm.",
            "Synthetic parents share a historical template; they are not independent real airport days.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output", type=Path, help="New audit JSON; existing output is refused")
    parser.add_argument("--dummy-test", action="store_true", help="Only an explicitly DUMMY manifest; never production")
    args = parser.parse_args()
    try:
        result = audit(args.root, dummy_test=args.dummy_test)
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "reason": str(error), "dummy_only": args.dummy_test}), file=sys.stderr)
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf8") as stream:
            stream.write(text)
        print(json.dumps({"status": result["status"], "dummy_only": args.dummy_test,
                          "output": str(args.output.resolve()), "runs": len(result["runs"])}))
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
