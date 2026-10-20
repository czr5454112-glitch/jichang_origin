"""Explicit D16-only interim summary. Does not open E/G runs, fit or simulate."""
import collections
import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

CYCLE = Path(__file__).resolve().parent.parent
ROOT = CYCLE.parents[3]
sys.path.insert(0, str(ROOT))
from scripts.experiments.g31_ics_circulation import foundation_airport_action_review as review

PARENTS, SEEDS = (901, 902), (17, 29, 43)


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def pin(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def mean(values):
    return math.fsum(values) / len(values)


def summarize():
    grid_path = CYCLE / "prospective_evaluation_grid_001.json"
    grid = read(grid_path)
    specs = [s for s in grid["rows"] if s["batch"] == "D"]
    assert len(specs) == len({s["name"] for s in specs}) == 16
    assert {s["parent_seed"] for s in specs} == set(PARENTS)
    assert all(s["fleet"] == 22 for s in specs)
    # Require every D receipt closed before opening any D final outputs.
    receipts = {s["name"]: read(CYCLE / s["name"] / "receipt.json") for s in specs}
    assert all(r["status"] == "complete" for r in receipts.values())
    rows = []
    for spec in specs:
        row = review.read_run(CYCLE, spec)
        assert row["status"] == "complete" and row["full_window_cost"] is not None
        rows.append(row)
        print(json.dumps({"event": "D_row_recomputed", "name": row["name"]}), flush=True)
    lookup = {(r["parent_seed"], r["variant"], r["model_seed"]): r for r in rows}
    comparisons, cells = [], []
    for parent in PARENTS:
        base, forecast = lookup[parent, "C00", None], lookup[parent, "C10", None]
        rule = review.compare_runs(CYCLE, base, forecast)
        rule["comparison_kind"] = "C10_vs_C00"
        comparisons.append(rule)
        for seed in SEEDS:
            no_plan, with_plan = lookup[parent, "C01", seed], lookup[parent, "C11", seed]
            compared = {}
            for kind, a, b in (
                ("C01_vs_C00", base, no_plan), ("C11_vs_C10", forecast, with_plan),
                ("C11_vs_C00", base, with_plan),
            ):
                item = review.compare_runs(CYCLE, a, b)
                assert item["status"] == "complete_same_resource_comparison"
                item.update(comparison_kind=kind, parent_seed=parent, model_seed=seed)
                comparisons.append(item)
                compared[kind] = item
            cells.append({
                "parent_seed": parent, "model_seed": seed,
                "C11_vs_C10_gain": compared["C11_vs_C10"]["advantage_bag_seconds"],
                "C11_vs_C10_relative_gain": compared["C11_vs_C10"]["relative_advantage"],
                "C11_vs_C00_gain": compared["C11_vs_C00"]["advantage_bag_seconds"],
                "C11_vs_C00_relative_gain": compared["C11_vs_C00"]["relative_advantage"],
                "C01_vs_C00_gain": compared["C01_vs_C00"]["advantage_bag_seconds"],
                "C01_vs_C00_relative_gain": compared["C01_vs_C00"]["relative_advantage"],
                "learning_by_prediction_interaction": compared["C11_vs_C10"]["advantage_bag_seconds"]
                    - compared["C01_vs_C00"]["advantage_bag_seconds"],
                "C10_vs_C00_gain": rule["advantage_bag_seconds"],
                "C11_beats_C10_but_loses_C00": (
                    compared["C11_vs_C10"]["advantage_bag_seconds"] > 1e-6
                    and compared["C11_vs_C00"]["advantage_bag_seconds"] < -1e-6),
                "C11_completed_delta_vs_C10": compared["C11_vs_C10"]["completed_delta"],
                "C11_on_time_delta_vs_C10": compared["C11_vs_C10"]["on_time_delta"],
                "C11_completed_delta_vs_C00": compared["C11_vs_C00"]["completed_delta"],
                "C11_on_time_delta_vs_C00": compared["C11_vs_C00"]["on_time_delta"],
            })
            print(json.dumps({"event": "D_cell_compared", "parent": parent, "seed": seed}), flush=True)
    threshold = grid["engineering_followup_threshold"]["relative_mean_J_reduction"]
    assert threshold == 0.001
    gains = ("C11_vs_C10_gain", "C11_vs_C00_gain", "C01_vs_C00_gain",
             "learning_by_prediction_interaction")
    per_seed = []
    for seed in SEEDS:
        subset = [c for c in cells if c["model_seed"] == seed]
        assert len(subset) == 2
        mean_relative = mean([c["C11_vs_C10_relative_gain"] for c in subset])
        baseline_mean = mean([
            lookup[p, "C10", None]["full_window_cost"]["backlog_integral_bag_seconds"]
            for p in PARENTS])
        ratio_of_mean_costs = mean([c["C11_vs_C10_gain"] for c in subset]) / baseline_mean
        both_improve = all(c["C11_vs_C10_gain"] > 1e-6 for c in subset)
        per_seed.append({
            "model_seed": seed, "parent_count": 2,
            "means": {key: mean([c[key] for c in subset]) for key in gains},
            "mean_parent_relative_C11_vs_C10_gain": mean_relative,
            "ratio_of_mean_cost_C11_vs_C10_gain": ratio_of_mean_costs,
            "both_relative_mean_interpretations_above_0_001": (
                mean_relative >= threshold and ratio_of_mean_costs >= threshold),
            "both_parents_positive_same_information": both_improve,
            "run_completion_failures": 0,
            "run_completion_failure_scope": "Receipt/whole-run endpoint only; excludes actual transfer failures and quarantined trays, which require the separate protection audit.",
            "all_harmed_and_unknown_job_counts_reported": True,
            "numeric_and_parent_followup_conditions_met": (
                mean_relative >= threshold and ratio_of_mean_costs >= threshold and both_improve),
            "full_G2_established": False,
            "protected_takeover_eligible": False,
            "interpretation": "A predeclared research-followup scalar gate only; not statistical significance, a safety certificate or airport SLA.",
        })
    per_parent = [{
        "parent_seed": parent, "model_seeds": list(SEEDS),
        "means_across_all_three_fixed_seeds": {
            key: mean([c[key] for c in cells if c["parent_seed"] == parent]) for key in gains},
        "mean_relative_C11_vs_C10_gain": mean([
            c["C11_vs_C10_relative_gain"] for c in cells if c["parent_seed"] == parent]),
        "note": "Descriptive repeated-fit average within one synthetic parent; not three independent airport days.",
    } for parent in PARENTS]
    report = {
        "schema": "g31.airport.closed_D16_interim_main_test.v1",
        "created_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": "all_16_primary_runs_closed_recomputed_interim_only",
        "not_final_34_run_review": True, "E_or_G_outcomes_opened_by_this_script": False,
        "scope": "All preregistered D16 rows, every parent and every model seed. No post-test seed/model/resource selection.",
        "inputs": {"grid": pin(grid_path), "script": pin(Path(__file__)),
                   "review_module": pin(Path(review.__file__))},
        "engineering_threshold_contract": grid["engineering_followup_threshold"],
        "relative_mean_ambiguity_handling": "Both mean of the two parent-relative gains and ratio of the two mean costs are reported. Numeric decision requires both >= frozen0.001; no threshold redefinition or tuning.",
        "rows": rows, "comparisons": comparisons, "six_primary_cells": cells,
        "two_parent_means_by_fixed_seed": per_seed, "three_seed_means_by_parent": per_parent,
        "all_seed_descriptive_mean": {
            **{key: mean([c[key] for c in cells]) for key in gains},
            "mean_relative_C11_vs_C10_gain": mean([c["C11_vs_C10_relative_gain"] for c in cells]),
            "independence_warning": "Six values are two synthetic parents crossed with three training seeds, not six independent days.",
        },
        "closed_run_status_denominator": dict(collections.Counter(r["status"] for r in rows)),
        "quarantine_outcomes": [
            {"name": r["name"], "final_quarantined_trays": r["summary"]["trays_by_mode"].get("quarantined", 0)}
            for r in rows],
        "quarantine_interpretation": "Closed-run failure is distinct from a real in-policy failed transfer/quarantined tray. Detailed raw protection audit remains separate.",
        "known_harm_and_unknown_not_certified_away": True, "strict_nonharm_certified": False,
        "protected_takeover_eligible": False, "multistep_optimal_Q_established": False,
        "independent_synthetic_parents": 2, "independent_real_airport_days": 0,
        "native_starts": 0, "fit_calls": 0, "policy_changes": False,
    }
    return report


def text_report(report):
    lines = [
        "INTERIM D16 MAIN TEST ONLY — G/RESOURCE GRID NOT REVIEWED HERE",
        "Two conditional synthetic parents; zero independent real airport days.",
        "Positive cost gain means lower unfinished-bag integral; unit bag-seconds.",
        "",
        "Raw closed D16 outcomes: name | J | completed | on-time",
    ]
    for row in report["rows"]:
        cost = row["full_window_cost"]
        lines.append(f"{row['name']} | {cost['backlog_integral_bag_seconds']:.6f} | "
                     f"{cost['completed_by_end']} | {cost['on_time_by_end']}")
    lines += ["", "All six primary cells: parent seed | C11-C10 gain | C11-C00 gain | C01-C00 gain | interaction"]
    for cell in report["six_primary_cells"]:
        lines.append(f"{cell['parent_seed']} {cell['model_seed']} | {cell['C11_vs_C10_gain']:+.6f} | "
                     f"{cell['C11_vs_C00_gain']:+.6f} | {cell['C01_vs_C00_gain']:+.6f} | "
                     f"{cell['learning_by_prediction_interaction']:+.6f}")
    lines += ["", "Two-parent means for each fixed seed; frozen numerical continuation gate0.1%:"]
    for row in report["two_parent_means_by_fixed_seed"]:
        lines.append(f"seed{row['model_seed']}: C11-C10 mean gain={row['means']['C11_vs_C10_gain']:+.6f}; "
            f"mean relative={100*row['mean_parent_relative_C11_vs_C10_gain']:.9f}%; "
            f"ratio of means={100*row['ratio_of_mean_cost_C11_vs_C10_gain']:.9f}%; "
            f"both parents positive={row['both_parents_positive_same_information']}; "
            f"numeric+parent gate={row['numeric_and_parent_followup_conditions_met']}; "
            "full_G2_not_established; protected_takeover=False.")
    lines += ["", "All cost comparisons include full-population harmed/unknown counts in the JSON.",
        "Any positive aggregate gain is a whole-policy comparison, not a single-action causal effect.",
        "The numeric research-followup criterion is not protection certification or a statistical test.",
        "A quarantined tray is real within-policy availability loss even when the run reaches59400.",
        "No model, seed, policy or resource count was selected or modified after these results."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    output = CYCLE / "report_support/D_primary_closed_main_test_001.json"
    text_output = output.with_suffix(".txt")
    assert not output.exists() and not text_output.exists()
    report = summarize()
    with output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    with text_output.open("x", encoding="utf8", newline="\n") as stream:
        stream.write(text_report(report))
    print(json.dumps({"artifact": pin(output),
                      "two_parent_means": report["two_parent_means_by_fixed_seed"],
                      "all_seed_descriptive_mean": report["all_seed_descriptive_mean"]}, indent=2))
