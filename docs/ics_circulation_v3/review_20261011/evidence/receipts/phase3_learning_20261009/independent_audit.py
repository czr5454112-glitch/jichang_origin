"""Read-only, standard-library audit of the saved phase3 learning evidence.

Run from any working directory. This does not import the experiment code,
retrain a model, execute a rollout, or edit any original experiment artifact.
Only the adjacent independent_audit.json is written.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import mean

ARTIFACT = Path(__file__).resolve().parent
ROOT = ARTIFACT.parents[3]
BASE = ARTIFACT.parent
WEIGHTS = {"tray_wait": 1., "nonprotected_tardiness": 1., "empty_distance": .1,
           "terminal_backlog": 10., "terminal_inflight": 2.}
CHECKS = []


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def same(actual, expected):
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same(actual[k], expected[k]) for k in actual)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    if type(actual) in (float, int) and type(expected) in (float, int):
        return math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-8)
    return actual == expected


def check(name, passed, detail=None):
    result = {"name": name, "passed": bool(passed)}
    if detail is not None:
        result["detail"] = detail
    CHECKS.append(result)


def grouped(records):
    result = defaultdict(list)
    for record in records:
        result[record["source_group"]].append(record)
    return result


def raw_value(model, features):
    z = [(features[n] - c) / s for n, c, s in zip(model["feature_names"], model["center"], model["scale"])]
    if "parameters" not in model:
        return sum(v * w for v, w in zip(z, model["coefficients"])) + model["intercept"]
    p = model["parameters"]
    hidden = [math.tanh(sum(v * row[j] for v, row in zip(z, p["w1"])) + bias)
              for j, bias in enumerate(p["b1"])]
    return sum(v * w for v, w in zip(hidden, p["w2"])) + p["b2"][0]


def model_score(model, features, base):
    result = raw_value(model, features) - raw_value(model, base)
    if model["kind"] == "residual":
        result += features["timed_analytic_absolute"] - base["timed_analytic_absolute"]
    return result


def assessment(records, policy, model=None):
    decisions, errors = [], []
    for group, choices in grouped(records).items():
        base = next(r for r in choices if r["is_baseline"])
        if model is None:
            key = {"baseline": "candidate_index", "analytic": "analytic_delta", "timed": "timed_delta",
                   "forecast_rollout": "forecast_delta"}[policy]
            scores = [r[key] for r in choices]
        else:
            scores = [model_score(model, r["features"], base["features"]) for r in choices]
        selected = min(range(len(choices)), key=lambda i: (scores[i], choices[i]["candidate_index"]))
        chosen = choices[selected]
        decisions.append({"source_group": group, "selected_index": chosen["candidate_index"],
                          "regret": chosen["delta_mean"] - min(r["delta_mean"] for r in choices),
                          "gain_over_baseline": -chosen["delta_mean"]})
        if policy != "baseline":
            errors.extend((score - r["delta_mean"]) ** 2 for score, r in zip(scores, choices))
    return {"groups": len(decisions), "mean_regret": mean(r["regret"] for r in decisions),
            "max_regret": max(r["regret"] for r in decisions),
            "positive_regret_groups": sum(r["regret"] > 1e-9 for r in decisions),
            "mean_gain_over_baseline": mean(r["gain_over_baseline"] for r in decisions),
            "delta_rmse": math.sqrt(mean(errors)) if errors else None, "decisions": decisions}


def label_audit(records, branches, expected_groups, expected_split):
    errors = []
    index = {(r["source_group"], r["candidate_index"], r["future_seed"]): r for r in branches}
    if len(index) != len(branches):
        errors.append("duplicate branch key")
    groups = grouped(records)
    if set(groups) != set(expected_groups):
        errors.append("source group mismatch")
    for group, choices in groups.items():
        if len(choices) != 4 or {r["candidate_index"] for r in choices} != set(range(4)):
            errors.append(group + ": four-candidate denominator")
            continue
        bases = [r for r in choices if r["is_baseline"]]
        if len(bases) != 1 or bases[0]["candidate_index"] != 0:
            errors.append(group + ": baseline identity")
            continue
        base = bases[0]
        for r in choices:
            if r["split"] not in expected_split:
                errors.append(group + ": split mismatch")
            actual_costs = [index[(group, r["candidate_index"], seed)]["total_cost"] for seed in (0, 1)]
            paired = [value - reference for value, reference in zip(actual_costs, base["costs"])]
            if not same([r["costs"], r["cost_mean"], r["paired_deltas"], r["delta_mean"]],
                        [actual_costs, mean(actual_costs), paired, mean(paired)]):
                errors.append(group + ": paired cost mismatch")
            for prefix, feature in (("analytic", "analytic_absolute"), ("timed", "timed_analytic_absolute")):
                if not same(r[prefix + "_delta"], r["features"][feature] - base["features"][feature]):
                    errors.append(group + ": feature difference mismatch")
        if any(base[key] != 0 for key in ("delta_mean", "analytic_delta", "timed_delta", "forecast_delta")) or base["paired_deltas"] != [0., 0.]:
            errors.append(group + ": nonzero baseline")
    for r in branches:
        if set(r["cost_components"]) != set(WEIGHTS) or not same(r["total_cost"], sum(r["cost_components"][k] * w for k, w in WEIGHTS.items())):
            errors.append(str((r["source_group"], r["candidate_index"], r["future_seed"])) + ": cost components")
    return errors


def quantiles(values):
    ordered = sorted(values)
    pick = lambda p: ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * p + .5)))]
    return {"p50": pick(.5), "p95": pick(.95), "p99": pick(.99), "max": max(values), "mean": mean(values)}


def main():
    originals = {p: digest(p) for p in ARTIFACT.rglob("*") if p.is_file() and p.name not in {"independent_audit.py", "independent_audit.json"}}
    protocol, manifest, summary = (read(ARTIFACT / name) for name in ("protocol.json", "split_manifest.json", "summary.json"))
    models, selection, saved_test = (read(ARTIFACT / name) for name in ("frozen_models.json", "validation_selection.json", "test_metrics.json"))
    test, branches, sources, deployment, deployment_sources = (rows(ARTIFACT / name) for name in
        ("test_candidates.jsonl", "test_branches.jsonl", "test_sources.jsonl", "deployment.jsonl", "deployment_sources.jsonl"))
    training = ROOT / protocol["training_source"]
    old_manifest = read(training / "split_manifest.json")
    old_rows, old_branches = rows(training / "candidates.jsonl"), rows(training / "branches.jsonl")
    groups = manifest["groups"]
    reused = [r for r in old_rows if r["split"] in {"train", "validation"}]
    train = [r for r in reused if r["split"] == "train"]
    validation = [r for r in reused if r["split"] == "validation"]
    reused_ids = set(groups["train"] + groups["validation"])
    reused_branches = [r for r in old_branches if r["source_group"] in reused_ids]
    evaluation_ids = set(groups["test"] + groups["deployment"])
    check("disjoint_frozen_splits", len({g for values in groups.values() for g in values}) == sum(map(len, groups.values()))
          and {k: len(v) for k, v in groups.items()} == {"train": 80, "validation": 20, "test": 40, "deployment": 40})
    previous_overlaps = {}
    for path in sorted(BASE.glob("*learning*/split_manifest.json")):
        if path.parent == ARTIFACT:
            continue
        previous = read(path)["groups"]
        previous_ids = {g for values in previous.values() for g in values}
        previous_overlaps[path.parent.name] = sorted(previous_ids & evaluation_ids)
    check("fresh_evaluation_ids_disjoint_all_phase2_and_smoke_ids", all(not ids for ids in previous_overlaps.values()), previous_overlaps)
    check("train_validation_reused_exact_groups_and_input_hashes",
          all(groups[k] == old_manifest["groups"][k] for k in ("train", "validation")) and
          all(digest(training / name) == value for name, value in protocol["training_input_sha256"].items()))
    check("400_reused_candidates_800_paired_branches", len(reused) == 400 and len(reused_branches) == 800)
    reused_errors = label_audit(reused, reused_branches, reused_ids, {"train", "validation"})
    check("reused_labels_recomputed_costs_pairing_and_100_baseline_zeros", not reused_errors, reused_errors)
    check("160_fresh_candidates_320_paired_branches_40_sources", len(test) == 160 and len(branches) == 320 and len(sources) == 40
          and {s["source_group"] for s in sources} == set(groups["test"]))
    test_errors = label_audit(test, branches, groups["test"], {"test"})
    check("fresh_labels_recomputed_costs_pairing_and_40_baseline_zeros", not test_errors, test_errors)
    source_errors = []
    source_index = {r["source_group"]: r for r in sources}
    for r in branches:
        source = source_index[r["source_group"]]
        bags = {**source["initial"]["bags"], **{b["bag_id"]: b for b in source["futures"][r["future_seed"]]}}
        if r["completed"] + len(r["uncompleted"]) != len(bags) or not set(r["uncompleted"]) <= set(bags):
            source_errors.append([r["source_group"], r["candidate_index"], r["future_seed"]])
    check("test_branch_task_denominators_match_saved_exogenous_tapes", not source_errors, source_errors)

    full_names = {f"mlp_{kind}_seed{seed}" for kind in ("direct", "residual") for seed in (17, 29, 43)}
    ablation_names = {"mlp_direct_no_analytic_scores", "mlp_direct_route_only"}
    curve_names = {f"curve_{size}_{kind}" for size in (20, 40) for kind in ("direct", "residual")}
    mlp_names = full_names | ablation_names | curve_names
    policy_names = {"baseline", "analytic", "timed", "forecast_rollout", "ridge_direct", "ridge_residual"} | full_names | ablation_names
    check("fixed_three_seeds_all_reported_no_best_seed_filter", set(saved_test) == policy_names and len(policy_names) == 14
          and set(models) == mlp_names | {"ridge_direct", "ridge_residual"})
    check("frozen_ridge_models_equal_prior_validation_selected_models", all(models[f"ridge_{kind}"] == read(training / f"{kind}_model.json") for kind in ("direct", "residual")))
    fit_groups = defaultdict(list)
    for record in selection:
        fit_groups[record["model_name"]].append(record)
    grid = {(lr, penalty) for lr in (.003, .01) for penalty in (0., .001)}
    check("48_fits_match_frozen_grid", len(selection) == 48 and set(fit_groups) == mlp_names and
          all(len(records) == 4 and {(r["learning_rate"], r["l2"]) for r in records} == grid for records in fit_groups.values())
          and same(sum(r["fit_ms"] for r in selection), summary["total_fit_ms"]))
    validation_errors, selected_configs, normalization_errors, fingerprints, final_objective_errors = [], {}, [], {}, []
    val_groups = grouped(validation)
    for fit in selection:
        decisions = fit["decisions"]
        if len(decisions) != 20 or {d["source_group"] for d in decisions} != set(groups["validation"]):
            validation_errors.append(fit["model_name"] + ": validation-only group count")
            continue
        for d in decisions:
            choices = val_groups[d["source_group"]]
            chosen = next(r for r in choices if r["candidate_index"] == d["selected_index"])
            if not same([d["regret"], d["gain_over_baseline"]], [chosen["delta_mean"] - min(r["delta_mean"] for r in choices), -chosen["delta_mean"]]):
                validation_errors.append(fit["model_name"] + ": decision regret")
        if not same([fit["mean_regret"], fit["max_regret"], fit["positive_regret_groups"], fit["mean_gain_over_baseline"]],
                    [mean(d["regret"] for d in decisions), max(d["regret"] for d in decisions), sum(d["regret"] > 1e-9 for d in decisions), mean(d["gain_over_baseline"] for d in decisions)]):
            validation_errors.append(fit["model_name"] + ": aggregate regret")
    for name in sorted(mlp_names):
        model = models[name]
        winner = min(fit_groups[name], key=lambda r: (r["mean_regret"], r["delta_rmse"], r["learning_rate"], r["l2"]))
        cfg, meta = model["config"], model["training_metadata"]
        selected_configs[name] = {"seed": cfg["seed"], "learning_rate": cfg["learning_rate"], "l2": cfg["l2"], "train_groups": meta["source_group_count"]}
        if cfg["seed"] != winner["seed"] or cfg["learning_rate"] != winner["learning_rate"] or cfg["l2"] != winner["l2"] or read(ARTIFACT / (name + ".json")) != model:
            validation_errors.append(name + ": selected winner differs from validation-only lexicographic rule")
        actual_val = assessment(validation, model["kind"], model)
        if not same(actual_val, {k: winner[k] for k in actual_val}):
            validation_errors.append(name + ": independently inferred selected-model validation metric differs")
        count = int(name.split("_")[1]) if name.startswith("curve_") else 80
        keep = set(groups["train"][:count])
        subset = [r for r in train if r["source_group"] in keep]
        names = model["feature_names"]
        if meta["source_groups"] != sorted(keep) or meta["row_count"] != 4 * count or meta["source_group_count"] != count or cfg["epochs"] != 400 or meta["epochs_completed"] != 400 or meta["validation_or_test_access"] or meta["early_stopping"]:
            normalization_errors.append(name + ": training population or schedule metadata")
        x = [[float(r["features"][n]) for n in names] for r in subset]
        centers = [mean(v[i] for v in x) for i in range(len(names))]
        scales = [math.sqrt(mean((v[i] - centers[i]) ** 2 for v in x)) for i in range(len(names))]
        scales = [s if s >= 1e-9 else 1. for s in scales]
        if not same([centers, scales], [model["center"], model["scale"]]):
            normalization_errors.append(name + ": normalization not reconstructed from selected training rows")
        baselines = {r["source_group"]: i for i, r in enumerate(subset) if r["is_baseline"]}
        y = [float(r["cost_mean"]) if model["kind"] == "direct" else float(r["delta_mean"]) - float(r["timed_delta"]) for r in subset]
        fingerprint = {"groups": [r["source_group"] for r in subset], "baseline_indices": baselines, "feature_names": names, "x": x, "y": y}
        actual_hash = sha256(json.dumps(fingerprint, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
        fingerprints[name] = actual_hash
        if actual_hash != meta["training_data_sha256"]:
            normalization_errors.append(name + ": training data fingerprint")
        values = [raw_value(model, r["features"]) for r in subset]
        predictions = values if model["kind"] == "direct" else [v - values[baselines[r["source_group"]]] for v, r in zip(values, subset)]
        mse = mean((v - target) ** 2 for v, target in zip(predictions, y))
        p = model["parameters"]
        objective = mse + .5 * cfg["l2"] * (sum(w*w for row in p["w1"] for w in row) + sum(w*w for w in p["w2"]))
        if not same([mse, objective], [meta["final_data_mse"], meta["final_objective"]]):
            final_objective_errors.append(name)
    check("all_validation_decisions_and_selected_parameters_verified", not validation_errors, validation_errors)
    check("selected_models_training_only_normalization_fingerprints_400_epochs", not normalization_errors, normalization_errors)
    check("selected_models_saved_weights_recompute_final_training_objectives", not final_objective_errors, final_objective_errors)

    test_metrics = {}
    for policy in sorted(policy_names):
        model = models.get(policy)
        computed = assessment(test, model["kind"] if model else policy, model)
        test_metrics[policy] = {k: v for k, v in computed.items() if k != "decisions"}
        check("test_scores_decisions_and_metrics:" + policy, same(computed, saved_test[policy]) and same(test_metrics[policy], summary["test_metrics"][policy]))
    curve_errors = []
    curves = read(ARTIFACT / "sample_size_curve.json")
    for entry in curves:
        name = f"curve_{entry['train_groups']}_{entry['kind']}" if entry["train_groups"] != 80 else f"mlp_{entry['kind']}_seed17"
        computed = assessment(test, entry["kind"], models[name])
        if not same(computed, {k: entry[k] for k in computed}):
            curve_errors.append(name)
    check("sample_size_curve_six_fixed_seed_entries_recomputed", len(curves) == 6 and not curve_errors, curve_errors)
    check("every_frozen_model_reference_score_exact_zero", all(model_score(model, r["features"], r["features"]) == 0. for model in models.values() for r in test if r["is_baseline"]))

    dsource = {r["source_group"]: r for r in deployment_sources}
    index = {(r["source_group"], r["policy"]): r for r in deployment}
    check("560_deployment_rows_equal_14_policies_times_40_groups", len(deployment) == len(index) == 560
          and set(index) == {(g, p) for g in groups["deployment"] for p in policy_names}
          and len(deployment_sources) == 40 and set(dsource) == set(groups["deployment"]))
    task_errors, cost_errors, on_time_errors = [], [], []
    for r in deployment:
        source = dsource[r["source_group"]]
        bags = {**source["initial"]["bags"], **{b["bag_id"]: b for b in source["future_not_policy_input"]}}
        completed = r["completed_at"]
        if source["future_seed"] != 991 or r["bag_denominator"] != len(bags) or r["completed"] != len(completed) or set(completed) & set(r["uncompleted"]) or set(completed) | set(r["uncompleted"]) != set(bags):
            task_errors.append([r["source_group"], r["policy"]])
        on_time = sum(tick <= bags[bag_id]["deadline"] for bag_id, tick in completed.items())
        if on_time != r["on_time"]:
            on_time_errors.append([r["source_group"], r["policy"]])
        if set(r["cost_components"]) != set(WEIGHTS) or not same(r["total_cost"], sum(r["cost_components"][k] * w for k, w in WEIGHTS.items())):
            cost_errors.append([r["source_group"], r["policy"]])
        tardiness = sum(max(0, tick - bags[bag_id]["deadline"]) for bag_id, tick in completed.items() if not bags[bag_id]["protected"])
        if not same(tardiness, r["cost_components"]["nonprotected_tardiness"]):
            cost_errors.append([r["source_group"], r["policy"], "tardiness_from_completion_times"])
    check("deployment_identity_denominators_same_saved_future991_for_each_policy", not task_errors, task_errors)
    check("deployment_deadlines_recomputed_from_completed_at", not on_time_errors, on_time_errors)
    check("deployment_full_cost_and_tardiness_recomputed", not cost_errors, cost_errors)
    deployment_metrics = {}
    for policy in sorted(policy_names):
        subset = [r for r in deployment if r["policy"] == policy]
        timed = [index[(r["source_group"], "timed")]["total_cost"] for r in subset]
        baseline = [index[(r["source_group"], "baseline")]["total_cost"] for r in subset]
        computed = {"runs": len(subset), "mean_cost": mean(r["total_cost"] for r in subset),
                    "mean_delta_from_timed": mean(r["total_cost"] - t for r, t in zip(subset, timed)),
                    "better_than_timed": sum(r["total_cost"] < t - 1e-9 for r, t in zip(subset, timed)),
                    "worse_than_timed": sum(r["total_cost"] > t + 1e-9 for r, t in zip(subset, timed)),
                    "worse_than_baseline": sum(r["total_cost"] > b + 1e-9 for r, b in zip(subset, baseline)),
                    "completed": sum(r["completed"] for r in subset), "bag_denominator": sum(r["bag_denominator"] for r in subset),
                    "on_time": sum(r["on_time"] for r in subset), "uncompleted_total": sum(len(r["uncompleted"]) for r in subset),
                    "mean_tray_wait": mean(r["cost_components"]["tray_wait"] for r in subset),
                    "wall_ms_whole_episode": quantiles([r["wall_ms"] for r in subset])}
        deployment_metrics[policy] = computed
        check("deployment_aggregates:" + policy, same(computed, summary["independent_closed_loop"][policy]))
    check("all_policies_153_complete_but_on_time_separate", all(r["completed"] == r["bag_denominator"] == 153 and r["on_time"] < 153 and r["uncompleted_total"] == 0 for r in deployment_metrics.values()))
    check("rollout_and_invariant_denominators_match_summary", sum(r["invariant_checks"] for r in branches + deployment) == summary["invariant_checks"]
          and sum(r["nested_forecast_rollouts"] for r in deployment) == summary["deployment_nested_forecast_rollouts"] == 320
          and summary["reused_training_validation_candidate_rows"] == 400 and summary["reused_training_validation_paired_branches"] == 800
          and summary["new_candidate_rows"] == 160 and summary["new_paired_branch_rollouts"] == 320
          and summary["deployment_runs"] == 560 and summary["training_fit_count"] == 48)
    frozen_hash = digest(ARTIFACT / "frozen_models.json")
    check("frozen_models_hash_matches_pretest_manifest_and_postrun_summary", frozen_hash == manifest["frozen_models_sha256_before_test"] == summary["frozen_models_sha256"])
    snapshot = read(ARTIFACT / "source_snapshot" / "manifest.json")
    check("13_archived_dependency_sources_match_protocol_and_summary", len(snapshot) == 13 and snapshot == protocol["source_sha256_before"] == summary["source_sha256"]
          and all(digest(ARTIFACT / "source_snapshot" / name) == value for name, value in snapshot.items()))
    current_source_mismatches = [name for name, value in snapshot.items() if digest(ROOT / name) != value]
    check("current_dependency_sources_still_match_frozen_run", not current_source_mismatches and summary["source_changed_during_run"] is False, current_source_mismatches)
    modified = [str(p.relative_to(ARTIFACT)) for p, before in originals.items() if digest(p) != before]
    check("original_artifacts_unchanged_during_this_audit", not modified, modified)
    report = {
        "schema": "ics_v3_phase3_learning_independent_artifact_audit_v1",
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "Read-only JSON/hash audit and independent standard-library arithmetic/model inference; no experiment imports, training, simulation, or performance measurements.",
        "root": str(ROOT), "artifact": str(ARTIFACT), "audit_script_sha256": digest(Path(__file__)),
        "passed": all(r["passed"] for r in CHECKS), "check_count": len(CHECKS), "failed_checks": [r for r in CHECKS if not r["passed"]], "checks": CHECKS,
        "recomputed_test_metrics": test_metrics, "recomputed_deployment_metrics": deployment_metrics,
        "selected_validation_configs": selected_configs, "recomputed_training_fingerprints": fingerprints,
        "frozen_models_sha256": frozen_hash,
        "original_artifact_hashes": {str(p.relative_to(ARTIFACT)).replace("\\", "/"): value for p, value in originals.items()},
        "limitations_and_statistical_caveats": [
            "The independent evaluation unit is the source group (40 test and 40 deployment groups), not 160 candidate rows, 320 paired branches, or 153 bags; within-group choices, futures and bags are correlated.",
            "Fresh IDs are disjoint from every saved phase2 and smoke split checked, but the data remain from the same seven-node synthetic family. Disjoint identifiers alone do not establish airport/day/topology generalization or independent real-world sampling.",
            "All three fixed optimizer seeds (17, 29, 43) are retained. Their results vary substantially; there is no evidence here for stable nonlinear superiority over timed analytic or rollout references.",
            "48 fits reuse only 20 validation groups. This audit verifies the recorded grid, all validation regret decisions, selection rule and selected-model predictions. Losing model weights were not saved, so their RMSE and optimizer histories cannot be independently reconstructed.",
            "Training inputs, normalization, target hashes and saved final objectives are independently reconstructed for selected models. The 400 optimizer updates were not rerun, and saved metadata is not an independent proof of every training operation.",
            "Hashes show consistency with the recorded pretest freeze and unchanged artifacts; they are not external trusted timestamps and cannot independently prove the chronology of actions outside the saved run.",
            "Input ablations remove feature bundles and change parameter counts. They measure bundled input usefulness, not isolation of a single causal mechanism.",
            "Finite-candidate regret uses four feasible witnesses and two continuation futures per group. It is not regret against globally optimal routing or an exact Q function.",
            "All policies complete 153/153 bags, but completion does not imply on-time delivery; deadline counts are separately recomputed from saved completion times and bag deadlines.",
            "Test action labels and full-episode deployment costs are distinct endpoints. No confidence intervals or inferential significance tests are claimed by this descriptive artifact audit.",
            "Saved wall times cover entire local synthetic episodes; this audit does not treat them as measured network latency or a 100 ms request-level end-to-end guarantee."
        ],
    }
    (ARTIFACT / "independent_audit.json").write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(CHECKS), "failed_checks": report["failed_checks"],
                      "deployment": {k: {n: v[n] for n in ("mean_cost", "completed", "bag_denominator", "on_time")} for k, v in deployment_metrics.items()}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
