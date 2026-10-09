"""Independent saved-evidence arithmetic/hash audit; no simulation or imports.

Run from any working directory. Writes only the sibling audit JSON. The
enumeration below reconstructs the small recorded training argmin from saved
costs; it never trains/executes the experiment's controllers or models.
"""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
from statistics import mean

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
MATCHED = BASE / "phase3_matched_configuration_checked_20261009"
CONFIG = BASE / "phase3_scene_configuration_20261009"
REFERENCE = BASE / "phase3_prebalance_reference_20261009"
WEIGHTS = {"tray_wait": 1., "nonprotected_tardiness": 1., "empty_distance": .1,
           "terminal_backlog": 10., "terminal_inflight": 2.}
CHECKS = []


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x]


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def value_hash(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def same(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if type(a) in (float, int) and type(b) in (float, int):
        return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-8)
    return a == b


def check(name, passed, detail=None):
    CHECKS.append({"name": name, "passed": bool(passed), **({"detail": detail} if detail is not None else {})})


def choose(selector, features):
    feature = selector["split_feature"]
    return selector["left_configuration"] if feature is None or features[feature] <= selector["threshold"] else selector["right_configuration"]


def cost_ok(row, nested=True):
    c = row["cost_components"] if nested else row
    return all(c[k] is not None for k in WEIGHTS) and same(row["total_cost"], sum(c[k] * w for k, w in WEIGHTS.items()))


def main():
    originals = {p: sha(p) for folder in (MATCHED, CONFIG, REFERENCE) for p in folder.rglob("*") if p.is_file()}
    mp, ms = read(MATCHED / "protocol.json"), read(MATCHED / "summary.json")
    cp, cs, cm = read(CONFIG / "protocol.json"), read(CONFIG / "summary.json"), read(CONFIG / "split_manifest.json")
    selectors = read(CONFIG / "frozen_selectors.json")
    config_ids = selectors["best_fixed"]["training_metadata"]["configurations"]
    ct = {split: rows(CONFIG / f"{split}_rows.jsonl") for split in ("train", "validation", "test")}
    ce = {split: rows(CONFIG / f"{split}_episodes.jsonl") for split in ct}
    sources = {split: rows(CONFIG / f"{split}_sources.jsonl") for split in ct}
    all_episodes = [r for records in ce.values() for r in records]
    episodes, choices = rows(MATCHED / "episodes.jsonl"), rows(MATCHED / "selector_choices.jsonl")
    test_index = {r["source_group"]: r for r in ct["test"]}
    groups = cm["groups"]
    check("configuration_80_20_40_disjoint_sources_560_four_way_episodes", {k: len(v) for k, v in groups.items()} == {"train": 80, "validation": 20, "test": 40}
          and len({g for values in groups.values() for g in values}) == 140 and len(all_episodes) == 560
          and all(len(ce[k]) == 4 * len(groups[k]) and len(ct[k]) == len(groups[k]) == len(sources[k]) for k in groups))
    prior = cp["historical_split_manifest_sha256"]
    overlap = {path: sorted({g for values in read(ROOT / path)["groups"].values() for g in values} & {g for values in groups.values() for g in values}) for path in prior}
    check("configuration_splits_disjoint_historical_learning_and_smoke", all(not x for x in overlap.values()) and all(sha(ROOT / p) == v for p, v in prior.items()), overlap)
    config_errors, feature_errors, ledger_errors = [], [], []
    for split in ct:
        table = {r["source_group"]: r for r in ct[split]}
        source_map = {r["source_group"]: r for r in sources[split]}
        index = {(r["source_group"], r["configuration"]): r for r in ce[split]}
        if set(table) != set(groups[split]) or set(source_map) != set(groups[split]) or len(index) != len(ce[split]):
            config_errors.append(split + ": population or uniqueness")
        for group, r in table.items():
            source = source_map[group]
            bags = {**source["initial"]["bags"], **{b["bag_id"]: b for b in source["future_event_engine_only"]}}
            hashes = {"initial_sha256": value_hash(source["initial"]), "forecast_sha256": value_hash(source["published_forecasts"]),
                      "future_sha256": value_hash(source["future_event_engine_only"]), "features_sha256": value_hash(source["features"])}
            if r["features"] != source["features"] or not all(source[k] == r[k] == v for k, v in hashes.items()):
                config_errors.append(group + ": source/feature hashes")
            if source["future_seed"] != 991 or source["initial"]["now"] != 0:
                config_errors.append(group + ": initial decision or future seed")
            # Independently derive the ONLY feature used by the fitted stump.
            # All these initial forecasts are unique published aggregate records.
            forecasts = source["published_forecasts"]
            target = source["initial"]["bags"]["bag:target"]
            valid_shape = len({f["forecast_id"] for f in forecasts}) == len(forecasts) and all(f["published_at"] <= 0 <= f["at"] and not f["unit_ids"] for f in forecasts)
            feature = float(sum(f["count"] for f in forecasts if f["node"] == target["destination"]))
            if not valid_shape or feature != r["features"]["forecast_destination_origin_count"]:
                feature_errors.append(group)
            if set(r["costs"]) != set(config_ids) or set(r["outcomes"]) != set(config_ids):
                config_errors.append(group + ": four configurations missing")
            for config in config_ids:
                e = index[(group, config)]
                if e != r["outcomes"][config] or e["total_cost"] != r["costs"][config] or not cost_ok(e) or not all(e[k] == v for k, v in hashes.items()):
                    config_errors.append(group + ": return/cost/hash mismatch " + config)
                ledger = e["bag_ledger"]
                complete = {b["bag_id"]: b["completed_at"] for b in ledger if b["completed_at"] is not None}
                ontime = sum(t <= bags[bid]["deadline"] for bid, t in complete.items())
                if len(ledger) != len(bags) or {b["bag_id"] for b in ledger} != set(bags) or e["all_bag_denominator"] != len(bags) or e["completed"] != len(complete) or e["uncompleted"] != len(bags) - len(complete) or e["on_time"] != ontime:
                    ledger_errors.append([group, config])
                for b in ledger:
                    if b["deadline"] != bags[b["bag_id"]]["deadline"] or b["arrival"] != bags[b["bag_id"]]["arrival"] or b["on_time"] != (b["completed_at"] is not None and b["completed_at"] <= b["deadline"]):
                        ledger_errors.append([group, config, b["bag_id"]])
    check("configuration_all_four_returns_inputs_costs_match_raw_episode_records", not config_errors, config_errors)
    check("selector_used_feature_independently_derived_only_from_initial_published_forecasts", not feature_errors, feature_errors)
    check("configuration_all_560_episode_bag_ledgers_deadlines_denominators", not ledger_errors, ledger_errors)

    # Reconstruct the recorded training-only exhaustive cost table argmin.
    train = sorted([{k: r[k] for k in ("source_group", "split", "features", "costs")} for r in ct["train"]], key=lambda r: r["source_group"])
    fingerprint = sha256(json.dumps(train, sort_keys=True, allow_nan=False).encode()).hexdigest()
    def best_action(subset):
        sums = [sum(r["costs"][config] for r in subset) for config in config_ids]
        i = min(range(4), key=lambda j: (sums[j], j))
        return i, sums[i]
    fixed_action, fixed_sum = best_action(train)
    fixed = selectors["best_fixed"]
    check("training_best_fixed_reconstructed_with_declared_configuration_ties", fixed["left_configuration"] == fixed["right_configuration"] == config_ids[fixed_action]
          and same(fixed["training_metadata"]["training_mean_cost"], fixed_sum / 80))
    candidates = []
    for feature in cp["feature_names"]:
        values = sorted({r["features"][feature] for r in train})
        for a, b in zip(values, values[1:]):
            threshold = a / 2 + b / 2
            if threshold >= b:
                threshold = a
            left = [r for r in train if r["features"][feature] <= threshold]
            right = [r for r in train if r["features"][feature] > threshold]
            if min(len(left), len(right)) < cp["min_leaf_groups"]:
                continue
            li, ls = best_action(left)
            ri, rs = best_action(right)
            candidates.append((ls + rs, feature, threshold, li, ri, len(left), len(right)))
    best = min(candidates, key=lambda x: x[:5])
    stump = selectors["stump"]
    check("stump_67_train_only_threshold_argmin_and_leaf_actions_reconstructed", len(candidates) == stump["training_metadata"]["eligible_thresholds"] == 67
          and [stump["split_feature"], stump["threshold"], stump["left_configuration"], stump["right_configuration"]] == [best[1], best[2], config_ids[best[3]], config_ids[best[4]]]
          and stump["training_metadata"]["leaf_group_counts"] == list(best[5:]) and same(stump["training_metadata"]["training_mean_cost"], best[0] / 80))
    check("selector_training_metadata_fingerprint_and_train_only_source_ids", all(s["training_metadata"]["training_data_sha256"] == fingerprint and s["training_metadata"]["source_groups"] == sorted(groups["train"]) and s["training_metadata"]["training_groups"] == 80 for s in (fixed, stump)))
    val_costs = {name: mean(r["costs"][choose(selectors[name], r["features"])] for r in ct["validation"]) for name in ("best_fixed", "stump")}
    winner = "stump" if val_costs["stump"] < val_costs["best_fixed"] - 1e-12 else "best_fixed"
    gate = {"selected": winner, "mean_cost": val_costs, "validation_groups": 20, "tie_prefers": "best_fixed", "no_threshold_or_leaf_refit": True}
    check("validation_only_gate_recomputed_tie_prefers_fixed_no_test_selection", same(gate, selectors["validation_gate"]) and same(gate, cs["validation_gate"]) and selectors["validation_selected"] == selectors[winner]
          and val_costs["best_fixed"] == val_costs["stump"] == 16.14)
    pre_choices = rows(CONFIG / "test_choices_before_episode_labels.jsonl")
    check("40_saved_prelabel_choices_follow_frozen_initial_feature_selectors", len(pre_choices) == 40 and {r["source_group"] for r in pre_choices} == set(groups["test"])
          and all(r["features"] == test_index[r["source_group"]]["features"] and r["configuration_choices"] == {name: choose(selectors[name], r["features"]) for name in ("best_fixed", "stump", "validation_selected")} for r in pre_choices))
    config_metrics = {}
    saved_metrics = read(CONFIG / "test_metrics.json")
    for name in saved_metrics:
        decisions, selected = [], []
        for r in sorted(ct["test"], key=lambda x: x["source_group"]):
            chosen = name.split(":", 1)[1] if name.startswith("fixed_reference:") else choose(selectors[name], r["features"])
            cost = r["costs"][chosen]
            selected.append(r["outcomes"][chosen])
            decisions.append({"source_group": r["source_group"], "configuration": chosen, "cost": cost,
                              "delta_from_baseline": cost - r["costs"][config_ids[0]], "regret_to_best_recorded_configuration": cost - min(r["costs"].values())})
        result = {"source_groups": 40, "cost_available_count": 40, "failed_selected_episodes": 0,
                  "mean_cost": mean(d["cost"] for d in decisions), "paired_baseline_count": 40,
                  "mean_delta_from_baseline": mean(d["delta_from_baseline"] for d in decisions),
                  "regret_available_count": 40, "mean_regret": mean(d["regret_to_best_recorded_configuration"] for d in decisions),
                  "selection_counts": {c: sum(d["configuration"] == c for d in decisions) for c in config_ids},
                  "additional_simulation_calls": 0, "decisions": decisions,
                  "all_bag_denominator": sum(e["all_bag_denominator"] for e in selected), "completed": sum(e["completed"] for e in selected),
                  "uncompleted": sum(e["uncompleted"] for e in selected), "on_time": sum(e["on_time"] for e in selected)}
        config_metrics[name] = {k: v for k, v in result.items() if k != "decisions"}
        check("configuration_test_metrics:" + name, same(result, saved_metrics[name]) and same(config_metrics[name], cs["test_metrics"][name]))
    check("configuration_summary_episode_failures_invariants", cs["episode_calls"] == cs["expected_episode_calls"] == 560 and cs["failed_episode_count"] == sum(e["status"] == "failed" for e in all_episodes) == 0
          and cs["invariant_checks"] == sum(e["invariant_checks"] for e in all_episodes) and same(cs["mean_episode_wall_ms_descriptive"], mean(e["episode_wall_ms"] for e in all_episodes)))

    policies = {"baseline", "analytic", "timed", "forecast_rollout"} | set(mp["models"])
    index = {(e["source_group"], e["policy"]): e for e in episodes}
    check("matched_560_unique_records_14_policies_by_same40_configuration_test_groups", len(episodes) == len(index) == 560 and len(policies) == 14 and set(index) == {(g, p) for g in groups["test"] for p in policies})
    matched_errors, baseline_errors = [], []
    for e in episodes:
        original = test_index[e["source_group"]]
        if not cost_ok(e) or not all(e[k] == original[k] for k in ("initial_sha256", "forecast_sha256", "future_sha256")):
            matched_errors.append([e["source_group"], e["policy"]])
        if e["policy"] in {"baseline", "timed"}:
            saved = original["outcomes"][e["policy"] + "__reactive_only"]
            if [e["total_cost"], e["completed"], e["bag_denominator"], e["on_time"], e["cost_components"]] != [saved["total_cost"], saved["completed"], saved["all_bag_denominator"], saved["on_time"], saved["cost_components"]]:
                baseline_errors.append([e["source_group"], e["policy"]])
        if e["bag_denominator"] != original["outcomes"][config_ids[0]]["all_bag_denominator"] or e["completed"] != e["bag_denominator"] or not 0 <= e["on_time"] <= e["completed"]:
            matched_errors.append([e["source_group"], e["policy"], "denominator"])
    check("matched_inputs_and_weighted_cost_same_as_configuration_four_way_cohort", not matched_errors, matched_errors)
    check("80_matched_baseline_timed_cost_components_completion_and_ontime_counts", not baseline_errors, baseline_errors)
    choice_errors = []
    for d in choices:
        r = test_index[d["source_group"]]
        choice = choose(selectors[d["selector"]], r["features"])
        e = r["outcomes"][choice]
        expected = {"source_group": r["source_group"], "selector": d["selector"], "configuration": choice, "total_cost": e["total_cost"], "on_time": e["on_time"], "bag_denominator": e["all_bag_denominator"], "completed": e["completed"], "uses_stored_complete_episode": True}
        if d != expected:
            choice_errors.append([d["source_group"], d["selector"]])
    check("matched_120_selector_choices_follow_initial_features_and_exact_stored_returns", len(choices) == len({(d["source_group"], d["selector"]) for d in choices}) == 120 and not choice_errors, choice_errors)
    selected = {d["source_group"]: d for d in choices if d["selector"] == "validation_selected"}
    matched_metrics = {}
    for policy in sorted(policies):
        subset = [e for e in episodes if e["policy"] == policy]
        deltas = [e["total_cost"] - selected[e["source_group"]]["total_cost"] for e in subset]
        result = {"groups": len(subset), "mean_cost": mean(e["total_cost"] for e in subset),
                  "mean_delta_from_selected_configuration": mean(deltas), "better_than_selected_configuration": sum(x < -1e-9 for x in deltas),
                  "worse_than_selected_configuration": sum(x > 1e-9 for x in deltas), "completed": sum(e["completed"] for e in subset),
                  "bag_denominator": sum(e["bag_denominator"] for e in subset), "on_time": sum(e["on_time"] for e in subset)}
        matched_metrics[policy] = result
        check("matched_metrics:" + policy, same(result, ms["metrics"][policy]) and result["completed"] == result["bag_denominator"] == 148 and result["on_time"] < 148)
    selector_metrics = {name: {"mean_cost": mean(d["total_cost"] for d in choices if d["selector"] == name),
                              "completed": sum(d["completed"] for d in choices if d["selector"] == name),
                              "on_time": sum(d["on_time"] for d in choices if d["selector"] == name)} for name in ("best_fixed", "stump", "validation_selected")}
    check("matched_selector_aggregates_recomputed", same(selector_metrics, ms["selectors"]))
    check("matched_denominators_invariants_and_rollout_budget", ms["new_episode_calls"] == 560 and ms["reused_configuration_episodes"] == 160 and ms["nested_forecast_rollouts"] == sum(e["nested_forecast_rollouts"] for e in episodes) == 320 and ms["invariant_checks"] == sum(e["invariant_checks"] for e in episodes))
    check("matched_declares_reused_cohort_and_distinct_training_and_decision_budgets", mp["no_training_no_retuning_no_new_generalization_claim"] and mp["training_budgets_and_decision_times_are_not_identical"] and "REUSE" in mp["evaluation_kind"] and mp["all_predeclared_mlp_seeds_retained"] == [17, 29, 43])

    rs, rm, manifest, comparisons = (read(REFERENCE / x) for x in ("summary.json", "metrics.json", "manifest.json", "comparisons.json"))
    ridx = {(e["source_group"], e["policy"]): e for e in rm}
    ref_policies = ("reactive_only", "predictive_greedy", "bounded_forecast_reference")
    check("reference36_unique_runs_three_policies12_sources_four_fixture_eight_new", len(rm) == len(ridx) == 36 and len(manifest) == 12 and Counter(s["family"] for s in manifest) == {"mechanism_fixture": 4, "new_synthetic_holdout": 8}
          and set(ridx) == {(s["source_group"], p) for s in manifest for p in ref_policies})
    ref_errors, diagnostic_errors = [], []
    for number, source in enumerate(manifest):
        hashes = {"initial_sha256": value_hash(source["state"]), "forecast_sha256": value_hash(source["forecasts"]), "future_sha256": value_hash(source["future_event_engine_only"])}
        bags = {**source["state"]["bags"], **{b["bag_id"]: b for b in source["future_event_engine_only"]}}
        for policy in ref_policies:
            e = ridx[(source["source_group"], policy)]
            case = read(REFERENCE / f"case_{number:03d}__{policy}.json")
            ledger, final, history = case["actual_bag_ledger"], case["final_snapshot"], case["controller_history"]
            completed = {b["bag_id"]: b["completion_time"] for b in ledger if b["completion_time"] is not None}
            ontime = sum(t <= bags[bid]["deadline"] for bid, t in completed.items())
            if case["metrics"] != e or not cost_ok(e, False) or not all(source[k] == e[k] == v for k, v in hashes.items()) or case["failure"] is not None or e["status"] != "completed_run":
                ref_errors.append([source["source_group"], policy, "record or input or cost"])
            if len(ledger) != len(bags) or {b["bag_id"] for b in ledger} != set(bags) or e["actual_bag_count"] != len(bags) or e["completed_count"] != len(completed) or e["on_time_count"] != ontime or e["uncompleted_count"] != len(bags)-len(completed) or final["completed"] != completed or set(final["trays"]) != set(source["state"]["trays"]) or set(final["bags"]) != {bid for bid, b in bags.items() if b["arrival"] <= final["now"]}:
                ref_errors.append([source["source_group"], policy, "identity/ledger"])
            for b in ledger:
                if any(b[k] != bags[b["bag_id"]][k] for k in ("arrival", "deadline", "origin", "destination", "protected")) or b["on_time"] != (b["completion_time"] is not None and b["completion_time"] <= b["deadline"]):
                    ref_errors.append([source["source_group"], policy, "bag metadata"])
            actual = {"full_proxy_simulator_calls": sum(h.get("rollout_calls", 0) for h in history), "failed_proxy_rollouts": sum(len(h.get("failed_proxy_rollouts", [])) for h in history),
                      "candidate_generation_calls": sum(h["search_calls"] for h in history), "bounded_partial_decisions": sum(h.get("status") == "partial_bounded_search" for h in history),
                      "max_proxy_calls_at_one_decision": max((h.get("rollout_calls", 0) for h in history), default=0), "max_decision_ms": max((h["elapsed_ms"] for h in history), default=0),
                      "proxy_rollout_ms": sum(h.get("rollout_ms", 0) for h in history)}
            if not all(same(e[k], v) for k, v in actual.items()):
                diagnostic_errors.append([source["source_group"], policy])
    check("reference_all36_inputs_raw_case_ledgers_identity_costs_deadlines", not ref_errors, ref_errors)
    check("reference_saved_controller_history_rollout_search_timing_denominators", not diagnostic_errors, diagnostic_errors)
    calculated_comparisons = []
    for source in manifest:
        g, p = ridx[(source["source_group"], "predictive_greedy")], ridx[(source["source_group"], "bounded_forecast_reference")]
        calculated_comparisons.append({"source_group": source["source_group"], "family": source["family"], "reference_minus_greedy_cost": p["total_cost"] - g["total_cost"],
                                       "reference_minus_greedy_completed": p["completed_count"] - g["completed_count"], "reference_minus_greedy_on_time": p["on_time_count"] - g["on_time_count"],
                                       "matched_observations_initial_and_truth": all(p[k] == g[k] for k in ("initial_sha256", "forecast_sha256", "future_sha256"))})
    check("all12_reference_greedy_pairs_equal_cost_completion_ontime_with_matching_inputs", same(calculated_comparisons, comparisons) and len(comparisons) == 12 and all(c["reference_minus_greedy_cost"] == c["reference_minus_greedy_completed"] == c["reference_minus_greedy_on_time"] == 0 for c in calculated_comparisons))
    ref_metrics = {}
    for policy in ref_policies:
        subset = [e for e in rm if e["policy"] == policy]
        result = {"run_count": len(subset), "failed_runs": sum(e["status"] == "failed" for e in subset), "cost_available_count": len(subset), "mean_cost": mean(e["total_cost"] for e in subset),
                  "all_bags_denominator": sum(e["actual_bag_count"] for e in subset), "completed_count": sum(e["completed_count"] for e in subset), "on_time_count": sum(e["on_time_count"] for e in subset),
                  "full_proxy_simulator_calls": sum(e["full_proxy_simulator_calls"] for e in subset), "full_evaluation_simulator_calls": sum(e["full_evaluation_simulator_calls"] for e in subset),
                  "failed_proxy_rollouts": sum(e["failed_proxy_rollouts"] for e in subset), "empty_transfer_commits": sum(e["empty_transfer_commits"] for e in subset),
                  "bounded_partial_decisions": sum(e["bounded_partial_decisions"] for e in subset), "mean_runtime_ms": mean(e["runtime_ms"] for e in subset), "max_decision_ms": max(e["max_decision_ms"] for e in subset)}
        ref_metrics[policy] = result
        check("reference_aggregate:" + policy, same(result, rs["by_policy"][policy]) and result["all_bags_denominator"] == result["completed_count"] == 37 and result["on_time_count"] < 37)
    check("reference_pair_summary_family_counts", rs["reference_vs_greedy"] == {"cost_pairs_available": 12, "mean_cost_delta": 0., "better": 0, "equal": 12, "worse": 0}
          and all(rs["reference_vs_greedy_by_family"][family] == {"source_group_count": n, "cost_pairs_available": n, "mean_cost_delta": 0., "better": 0, "equal": n, "worse": 0, "completed_delta": 0, "on_time_delta": 0} for family, n in (("mechanism_fixture", 4), ("new_synthetic_holdout", 8))))

    check("matched18_source_snapshots_and_current_sources_match_summary_protocol", len(mp["source_sha256"]) == 18 and mp["source_sha256"] == ms["source_sha256"] and all(sha(MATCHED / "source_snapshot" / p) == sha(ROOT / p) == v for p, v in mp["source_sha256"].items()) and not ms["source_changed_during_run"])
    check("matched_frozen_learning_selectors_config_inputs_hash_unchanged", all(sha(ROOT / p) == v for p, v in mp["frozen_input_sha256"].items()) and ms["frozen_inputs_unchanged"])
    check("configuration10_sources_match_archived_matched_dependency_sources", len(cs["source_sha256"]) == 10 and cs["source_sha256"] == cp["source_sha256_before"] and all(sha(ROOT / "scripts/experiments/ics_circulation_v3" / p) == sha(MATCHED / "source_snapshot/scripts/experiments/ics_circulation_v3" / p) == v for p, v in cs["source_sha256"].items()) and not cs["source_changed_during_run"])
    check("configuration_all_output_manifest_hashes_and_frozen_selector_hash", all(sha(CONFIG / p) == v for p, v in cs["output_sha256_before_summary"].items()) and sha(CONFIG / "frozen_selectors.json") == cs["frozen_selectors_sha256"])
    check("reference10_sources_match_before_after_and_archived_sources", len(rs["source_sha256"]) == 10 and rs["source_sha256"] == rs["source_sha256_after"] and all(sha(REFERENCE / "source_snapshot" / p) == sha(ROOT / "scripts/experiments/ics_circulation_v3" / p) == v for p, v in rs["source_sha256"].items()) and not rs["source_changed_during_run"])
    modified = [str(p.relative_to(BASE)) for p, before in originals.items() if sha(p) != before]
    check("all_original_artifacts_unchanged_during_audit", not modified, modified)
    report = {"schema": "ics_v3_phase3_cross_artifact_audit_v1", "audited_at_utc": datetime.now(timezone.utc).isoformat(),
              "method": "Independent standard-library JSON, hash, saved-cost argmin and aggregate arithmetic. No experiment imports, simulations, optimizer fitting or performance measurements.",
              "root": str(ROOT), "audit_script_sha256": sha(Path(__file__)), "passed": all(c["passed"] for c in CHECKS), "check_count": len(CHECKS),
              "failed_checks": [c for c in CHECKS if not c["passed"]], "checks": CHECKS,
              "recomputed_configuration_metrics": config_metrics, "recomputed_validation_gate": gate,
              "reconstructed_training_stump": {"eligible_thresholds": len(candidates), "feature": best[1], "threshold": best[2], "left": config_ids[best[3]], "right": config_ids[best[4]], "leaf_groups": list(best[5:])},
              "recomputed_matched_metrics": matched_metrics, "recomputed_selector_metrics": selector_metrics, "recomputed_reference_metrics": ref_metrics,
              "original_artifact_hashes": {str(p.relative_to(BASE)).replace("\\", "/"): v for p, v in originals.items()},
              "evidence_limits_and_statistical_caveats": [
                  "Matched560 is a supplementary reuse of the already evaluated 40 configuration test groups, not a fresh unseen test. Every policy shares recorded initial state, forecast and true-future hashes; the four configuration returns are reused, not newly simulated.",
                  "The 80 baseline/timed episode costs, components, completed counts, on-time counts and input hashes independently match prior configuration records. Matched episode rows omit completion timestamps, so timestamp equality cannot be independently recomputed from saved matched rows. The archived hashed runner asserts timestamp equality during execution; that assertion is weaker evidence than saved paired timestamps.",
                  "Configuration selection uses one initial observable decision; learned candidate policies choose at later routing opportunities. Training sources and budgets differ (configuration80 sources x4 full episodes; learning80 source states x4 candidates x2 futures), and complete configuration policies may also proactively rebalance. The matched comparison is not an isolated learning-algorithm treatment effect.",
                  "All148 matched bags complete, but only82-87 are on time depending on policy; configuration selectors complete148 with85 on time. Completion is not on-time service.",
                  "Reference and greedy have equal saved costs for all12 pairs, complete37/37 and have19 on time; reactive completes37/37 with20 on time. Reference extra computation shows no cost benefit on this small set; equality does not establish equivalence beyond these cases.",
                  "Reference evidence includes four known mechanism fixtures and eight separately named synthetic sources. It is a bounded published-forecast action search, not globally optimal MPC, airport integration, or a real network latency guarantee.",
                  "Source groups, not rows or bags, are the paired independent unit. Forty matched groups and twelve reference groups remain small same-family synthetic cohorts; no confidence interval, causal identification, airport generalization or best-seed selection claim is made.",
                  "The best-fixed and stump validation costs tie16.14, so the frozen validation gate correctly keeps fixed even though the reused test stump mean12.78 is lower than fixed12.795. Switching to the test-better stump would be test selection.",
                  "Hashes verify recorded data/source consistency and unchanged artifacts; they are not trusted external timestamps proving prelabel chronology. Configuration's10 source files are verified through the matching18-file supplementary source archive; its own directory has no separate source archive.",
                  "The selector feature actually used by the stump is independently reconstructed from initial published forecasts. All other saved feature values are checked across source/row/prelabel hashes; this audit does not independently rederive every unused feature implementation."
              ]}
    output = BASE / "phase3_cross_artifact_audit_20261009.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "checks": len(CHECKS), "failed_checks": report["failed_checks"], "validation_gate": gate,
                      "matched_selected_cost": selector_metrics["validation_selected"]["mean_cost"], "reference": ref_metrics}, indent=2))


if __name__ == "__main__":
    main()
