"""Supplementary same-cohort comparison of already frozen phase-3 methods.

This is an after-the-main-protocol matched audit, NOT another unseen test set.
Nothing is fitted or selected here. All three predeclared MLP seeds remain.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from .joint_control import build_engine, regional_factory
from .learning import CandidatePolicy, ForecastRolloutPolicy, RidgeValueModel
from .nonlinear_learning import MLPValueModel
from .run_phase3_learning import source_hashes, write_rows
from .run_scene_configuration import configuration_scenes
from .scene_configuration import CONFIGURATIONS, SceneSelector, initial_features

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
LEARNING = BASE / "phase3_learning_20261009"
CONFIG = BASE / "phase3_scene_configuration_20261009"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def run(output: Path):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new nonempty-history-free output directory")
    output.mkdir(parents=True, exist_ok=True)
    before = source_hashes()
    frozen = json.loads((LEARNING / "frozen_models.json").read_text())
    models = {name: (RidgeValueModel.from_dict(value) if name.startswith("ridge_") else MLPValueModel.from_dict(value))
              for name, value in frozen.items() if not name.startswith("curve_")}
    selectors = {name: SceneSelector.from_dict(value) for name, value in json.loads((CONFIG / "frozen_selectors.json").read_text()).items()}
    old_rows = {row["source_group"]: row for row in read_rows(CONFIG / "test_rows.jsonl")}
    input_hashes = {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path)
                    for path in (LEARNING / "frozen_models.json", CONFIG / "frozen_selectors.json", CONFIG / "test_rows.jsonl")}
    write(output / "protocol.json", {
        "evaluation_kind": "SUPPLEMENTARY_MATCHED_REUSE_OF_ALREADY_EVALUATED_CONFIGURATION_TEST_GROUPS",
        "no_training_no_retuning_no_new_generalization_claim": True,
        "scenes": 40, "models": list(models), "all_predeclared_mlp_seeds_retained": [17, 29, 43],
        "generator": "common_joint_control.regional_factory, static_path_limit=12 for every method",
        "note": "Original learning deployment used static_path_limit=16; this audit uses one common generator for all methods.",
        "configuration_training": "80 full-scene sources, all four returns; validation gates prefit fixed/stump",
        "learning_training": "different 80 source states with four paired candidates and two futures; validation selects weights",
        "training_budgets_and_decision_times_are_not_identical": True,
        "source_sha256": before, "frozen_input_sha256": input_hashes})
    specs = [(kind, kind, None) for kind in ("baseline", "analytic", "timed", "forecast_rollout")]
    specs += [(name, model.kind, model) for name, model in models.items()]
    rows, choices = [], []
    for number, scene in enumerate(configuration_scenes()["test"]):
        future = scene.future(991)
        original = old_rows[scene.source_group]
        hashes = {"initial_sha256": digest(asdict(scene.initial)),
                  "forecast_sha256": digest([asdict(f) for f in scene.forecasts]),
                  "future_sha256": digest([asdict(b) for b in future])}
        assert all(original[key] == value for key, value in hashes.items())
        visible = initial_features(scene.initial, scene.forecasts, target_bag_id=scene.target_bag, horizon=scene.horizon)
        for name, selector in selectors.items():
            choice = selector.select(visible)
            original_result = original["outcomes"][choice]
            choices.append({"source_group": scene.source_group, "selector": name, "configuration": choice,
                            "total_cost": original_result["total_cost"], "on_time": original_result["on_time"],
                            "bag_denominator": original_result["all_bag_denominator"],
                            "completed": original_result["completed"], "uses_stored_complete_episode": True})
        expected = {**scene.initial.bags, **{bag.bag_id: bag for bag in future}}
        # Rotate the matched call order; local wall time never influences actions.
        offset = number % len(specs)
        for name, kind, model in specs[offset:] + specs[:offset]:
            started = perf_counter()
            engine = build_engine(scene, future, CONFIGURATIONS[0])
            engine.route_selector = (ForecastRolloutPolicy(scene.horizon, scene.forecasts, regional_factory)
                                     if kind == "forecast_rollout" else CandidatePolicy(scene.horizon, scene.forecasts, kind, model))
            result = engine.advance(scene.horizon)
            rows.append({"source_group": scene.source_group, "policy": name, "total_cost": result.total_cost,
                         "cost_components": result.cost_components, "completed": len(result.completed),
                         "bag_denominator": len(expected),
                         "on_time": sum(bag_id in result.completed and result.completed[bag_id] <= bag.deadline
                                        for bag_id, bag in expected.items()),
                         "invariant_checks": result.invariant_checks, "wall_ms_whole_episode": (perf_counter() - started) * 1000,
                         "nested_forecast_rollouts": getattr(engine.route_selector, "rollout_count", 0), **hashes})
            if name in {"baseline", "timed"}:
                saved = original["outcomes"][f"{name}__reactive_only"]
                assert result.total_cost == saved["total_cost"]
                assert len(result.completed) == saved["completed"]
                assert result.completed == {item["bag_id"]: item["completed_at"] for item in saved["bag_ledger"]
                                            if item["completed_at"] is not None}
        if (number + 1) % 10 == 0:
            print(json.dumps({"matched_sources": number + 1, "new_episode_calls": len(rows)}), flush=True)
    write_rows(output / "episodes.jsonl", rows)
    write_rows(output / "selector_choices.jsonl", choices)
    reference = {row["source_group"]: row for row in choices if row["selector"] == "validation_selected"}
    metrics = {}
    for name, _, _ in specs:
        subset = [row for row in rows if row["policy"] == name]
        metrics[name] = {"groups": len(subset), "mean_cost": mean(row["total_cost"] for row in subset),
                         "mean_delta_from_selected_configuration": mean(row["total_cost"] - reference[row["source_group"]]["total_cost"] for row in subset),
                         "better_than_selected_configuration": sum(row["total_cost"] < reference[row["source_group"]]["total_cost"] - 1e-9 for row in subset),
                         "worse_than_selected_configuration": sum(row["total_cost"] > reference[row["source_group"]]["total_cost"] + 1e-9 for row in subset),
                         "completed": sum(row["completed"] for row in subset), "bag_denominator": sum(row["bag_denominator"] for row in subset),
                         "on_time": sum(row["on_time"] for row in subset)}
    selector_metrics = {name: {"mean_cost": mean(row["total_cost"] for row in choices if row["selector"] == name),
                               "completed": sum(row["completed"] for row in choices if row["selector"] == name),
                               "on_time": sum(row["on_time"] for row in choices if row["selector"] == name)} for name in selectors}
    source_after = source_hashes()
    assert source_after == before and all(sha(ROOT / path) == value for path, value in input_hashes.items())
    summary = {"scope": "supplementary_matched_frozen_model_audit_not_new_unseen_test",
               "new_episode_calls": len(rows), "reused_configuration_episodes": len(old_rows) * 4,
               "nested_forecast_rollouts": sum(row["nested_forecast_rollouts"] for row in rows),
               "invariant_checks": sum(row["invariant_checks"] for row in rows),
               "baseline_and_timed_match_prior_cost_completion_times": True,
               "metrics": metrics, "selectors": selector_metrics, "source_sha256": before,
               "source_changed_during_run": False, "frozen_inputs_unchanged": True,
               "limitations": ["This reuses configuration test outcomes, with no new tuning or model choice.",
                               "Same evaluation cohort, candidate generator and physical authority; training data/budgets and decision times differ.",
                               "Complete configuration policies may proactively rebalance; learned candidate policies use reactive balancing.",
                               "All cases are synthetic; averages do not establish a learning contribution or airport performance."]}
    write(output / "summary.json", summary)
    archive = output / "source_snapshot"
    for relative in before:
        target = archive / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    print(json.dumps({"metrics": metrics, "selectors": selector_metrics}, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.output)
