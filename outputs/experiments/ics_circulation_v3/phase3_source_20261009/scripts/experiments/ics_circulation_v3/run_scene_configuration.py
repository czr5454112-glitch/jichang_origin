"""Full-information, scene-start configuration baseline; no PPL/AIPW claim.

Generate four paired complete-episode returns for each train/validation/test
source. Freeze a training-only stump and best fixed controller, gate on
validation, then look up fresh test outcomes without extra simulations.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter
import traceback

from .joint_control import build_engine
from .phase2_scenarios import make_scene
from .runtime import COST_WEIGHTS
from .scene_configuration import (
    CONFIGURATIONS, CONFIGURATION_IDS, FEATURE_NAMES, SceneSelector,
    evaluate_stored, fit_selectors, initial_features, select_on_validation,
)

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
PROTOCOL = {
    "schema": "ics_v3_full_information_scene_configuration_protocol_v1",
    "counts": {"train": 80, "validation": 20, "test": 40},
    "source_namespace": "phase3_config", "future_seed": 991, "min_leaf_groups": 8,
    "configurations": [asdict(policy) for policy in CONFIGURATIONS],
    "feature_names": list(FEATURE_NAMES), "decision_time": "initial_snapshot_before_episode_execution",
    "stump_training": "all adjacent observed training feature midpoints; training-only per-leaf best actions",
    "fixed_training": "single configuration with minimum training mean cost; declared configuration order breaks ties",
    "validation_selection": "compare fitted stump with training-best fixed; ties prefer fixed; no refit",
    "held_out_protocol": "freeze both fitted selectors and validation gate before generating test episode costs",
    "label_scope": "all four complete episode costs for each source, same future and physical permissions",
    "estimator": "full_information_supervised_cost_minimization; not_PPL_not_AIPW_no_propensity_estimation",
    "evaluation": "exact stored full-episode outcome lookup for the once-per-scene selected fixed controller",
    "expected_episode_calls": 560, "extra_selector_evaluation_simulations": 0,
}


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def _rows(path, values):
    path.write_text("".join(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n" for value in values), encoding="utf-8")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    directory = Path(__file__).resolve().parent
    names = ("scene_configuration.py", "run_scene_configuration.py", "joint_control.py", "phase2_scenarios.py",
             "learning.py", "evaluation.py", "model.py", "runtime.py", "routing.py", "prebalance.py")
    return {name: _sha(directory / name) for name in names}


def configuration_scenes(*, smoke=False):
    counts = {"train": 8, "validation": 4, "test": 4} if smoke else PROTOCOL["counts"]
    namespace = "phase3_config_smoke" if smoke else PROTOCOL["source_namespace"]
    return {split: tuple(replace(make_scene(index, f"{namespace}_{split}"), split=split) for index in range(count))
            for split, count in counts.items()}


def _observable(scene):
    return initial_features(scene.initial, scene.forecasts, target_bag_id=scene.target_bag, horizon=scene.horizon)


def collect_episodes(scenes, output: Path, split: str):
    """Exactly one simulation for each (source, configuration); never a selector."""
    table, episodes, sources = [], [], []
    for number, scene in enumerate(scenes):
        features = _observable(scene)
        future = scene.future(PROTOCOL["future_seed"])
        expected = {**scene.initial.bags, **{bag.bag_id: bag for bag in future}}
        if len(expected) != len(scene.initial.bags) + len(future):
            raise ValueError("Duplicate bag IDs invalidate episode denominators")
        initial, forecasts, tape = asdict(scene.initial), [asdict(f) for f in scene.forecasts], [asdict(b) for b in future]
        hashes = {"initial_sha256": _hash(initial), "forecast_sha256": _hash(forecasts),
                  "future_sha256": _hash(tape), "features_sha256": _hash(features)}
        sources.append({"source_group": scene.source_group, "split": split, "initial": initial,
                        "published_forecasts": forecasts, "future_event_engine_only": tape,
                        "horizon": scene.horizon, "future_seed": PROTOCOL["future_seed"],
                        "features": features, **hashes})
        costs, outcomes = {}, {}
        # Rotation balances call order. Wall cutoffs are disabled for all four
        # fixed configurations; local wall times do not decide actions.
        offset = number % len(CONFIGURATIONS)
        order = CONFIGURATIONS[offset:] + CONFIGURATIONS[:offset]
        for order_index, config in enumerate(order):
            before = perf_counter()
            result, failure = None, None
            engine = None
            try:
                engine = build_engine(scene, future, config)
                result = engine.advance(scene.horizon)
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc), "traceback": traceback.format_exc()}
                if engine is not None:
                    try:
                        result = engine.result()
                    except Exception:
                        pass
            completed = result.completed if result is not None else {}
            ledger = [{"bag_id": bag_id, "deadline": bag.deadline, "arrival": bag.arrival,
                       "completed_at": completed.get(bag_id),
                       "on_time": bag_id in completed and completed[bag_id] <= bag.deadline}
                      for bag_id, bag in sorted(expected.items())]
            cost = result.total_cost if result is not None and failure is None else None
            row = {"source_group": scene.source_group, "split": split, "configuration": config.policy_id,
                   "configuration_spec": asdict(config), "execution_order_index": order_index,
                   "status": "failed" if failure else "complete", "total_cost": cost,
                   "cost_components": result.cost_components if result is not None else None,
                   "all_bag_denominator": len(expected), "completed": len(completed),
                   "uncompleted": len(expected) - len(completed), "on_time": sum(item["on_time"] for item in ledger),
                   "bag_ledger": ledger, "invariant_checks": result.invariant_checks if result is not None else 0,
                   "episode_wall_ms": (perf_counter() - before) * 1000,
                   "policy_stats": result.policy_stats if result is not None else {}, "failure": failure, **hashes}
            episodes.append(row)
            costs[config.policy_id], outcomes[config.policy_id] = cost, row
        if _hash(asdict(scene.initial)) != hashes["initial_sha256"]:
            raise RuntimeError("An episode mutated a shared initial snapshot")
        table.append({"source_group": scene.source_group, "split": split, "features": features,
                      "costs": costs, "outcomes": outcomes, **hashes})
        if (number + 1) % 20 == 0:
            print(json.dumps({"split": split, "source_groups_complete": number + 1, "episode_calls": len(episodes)}), flush=True)
    _rows(output / f"{split}_rows.jsonl", table)
    _rows(output / f"{split}_episodes.jsonl", episodes)
    _rows(output / f"{split}_sources.jsonl", sources)
    return table, episodes


def _evaluate(rows, selector):
    metrics = evaluate_stored(rows, selector)
    lookup = {row["source_group"]: row for row in rows}
    selected = [lookup[decision["source_group"]]["outcomes"][decision["configuration"]] for decision in metrics["decisions"]]
    metrics.update(all_bag_denominator=sum(row["all_bag_denominator"] for row in selected),
                   completed=sum(row["completed"] for row in selected),
                   uncompleted=sum(row["uncompleted"] for row in selected),
                   on_time=sum(row["on_time"] for row in selected))
    return metrics


def run(output: Path, *, smoke=False):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new output directory; prior evidence cannot be overwritten")
    output.mkdir(parents=True, exist_ok=True)
    before = source_hashes()
    scenes = configuration_scenes(smoke=smoke)
    groups = {split: [scene.source_group for scene in values] for split, values in scenes.items()}
    all_groups = {group for values in groups.values() for group in values}
    if len(all_groups) != sum(len(values) for values in groups.values()):
        raise ValueError("Source groups overlap between train/validation/test")
    historical_hashes = {}
    for path in sorted(BASE.glob("*/split_manifest.json")):
        if path.parent.resolve() == output.resolve():
            continue
        previous = json.loads(path.read_text(encoding="utf-8-sig"))
        previous_groups = {group for values in previous.get("groups", {}).values() for group in values}
        if all_groups & previous_groups:
            raise ValueError(f"Configuration sources overlap prior labels: {path}")
        historical_hashes[str(path.relative_to(ROOT)).replace("\\", "/")] = _sha(path)
    actual_calls = sum(map(len, groups.values())) * 4
    protocol = {**PROTOCOL, "smoke": smoke, "pipeline_only_if_smoke": smoke,
                "actual_counts": {split: len(values) for split, values in groups.items()},
                "actual_expected_episode_calls": actual_calls, "weights": COST_WEIGHTS,
                "source_sha256_before": before, "historical_split_manifest_sha256": historical_hashes}
    _write(output / "protocol.json", protocol)
    _write(output / "split_manifest.json", {"groups": groups, "disjoint_from_recorded_prior_splits": True})
    train, train_runs = collect_episodes(scenes["train"], output, "train")
    validation, validation_runs = collect_episodes(scenes["validation"], output, "validation")
    try:
        fixed, stump = fit_selectors(train, min_leaf_groups=PROTOCOL["min_leaf_groups"])
        selected, selection = select_on_validation(fixed, stump, validation)
    except ValueError as exc:
        _write(output / "failed_fit.json", {"error": str(exc), "episode_calls": len(train_runs) + len(validation_runs),
                                           "failed_episode_count": sum(r["status"] == "failed" for r in train_runs + validation_runs),
                                           "test_not_generated": True})
        raise
    frozen = {"best_fixed": fixed.to_dict(), "stump": stump.to_dict(), "validation_selected": selected.to_dict(),
              "validation_gate": selection}
    _write(output / "frozen_selectors.json", frozen)
    frozen_sha = _sha(output / "frozen_selectors.json")
    selectors = {"best_fixed": fixed, "stump": stump, "validation_selected": selected}
    decisions_before_labels = [{"source_group": scene.source_group, "features": _observable(scene),
                                "configuration_choices": {name: selector.select(_observable(scene)) for name, selector in selectors.items()}}
                               for scene in scenes["test"]]
    _rows(output / "test_choices_before_episode_labels.jsonl", decisions_before_labels)
    test, test_runs = collect_episodes(scenes["test"], output, "test")
    for decision, row in zip(decisions_before_labels, test):
        if decision["source_group"] != row["source_group"] or decision["features"] != row["features"]:
            raise RuntimeError("Test feature view changed after frozen scene-start selection")
    metrics = {name: _evaluate(test, selector) for name, selector in selectors.items()}
    for name in CONFIGURATION_IDS:
        constant = SceneSelector("best_fixed", None, None, name, name, {"evaluation_reference_only": True})
        metrics[f"fixed_reference:{name}"] = _evaluate(test, constant)
    _write(output / "test_metrics.json", metrics)
    if _sha(output / "frozen_selectors.json") != frozen_sha:
        raise RuntimeError("Frozen scene selectors changed after test labels")
    episodes = train_runs + validation_runs + test_runs
    summary = {"schema": "ics_v3_full_information_scene_configuration_result_v1", "smoke": smoke,
               "scope": "initial_observable_scene_selection_of_one_fixed_causal_episode_controller",
               "source_groups": {split: len(values) for split, values in groups.items()},
               "configuration_count": 4, "episode_calls": len(episodes), "expected_episode_calls": actual_calls,
               "additional_evaluation_simulations": 0, "validation_gate": selection,
               "test_metrics": {name: {key: item for key, item in metric.items() if key != "decisions"}
                                for name, metric in metrics.items()},
               "failed_episode_count": sum(row["status"] == "failed" for row in episodes),
               "invariant_checks": sum(row["invariant_checks"] for row in episodes),
               "mean_episode_wall_ms_descriptive": mean(row["episode_wall_ms"] for row in episodes),
               "frozen_selectors_sha256": frozen_sha,
               "source_sha256": before, "source_changed_during_run": source_hashes() != before,
               "output_sha256_before_summary": {path.name: _sha(path) for path in sorted(output.iterdir()) if path.is_file()},
               "limitations": [
                   "Full information from all four simulated returns; no propensities, bandit identification, PPL or AIPW claim.",
                   "One selector decision at scene start; no learned reselection within the episode.",
                   "The four fixed controller implementations may react causally to later visible state under the same physical permissions.",
                   "Only the same synthetic seven-node family, one shared future seed per source; no airport or operating-day generalization.",
                   "Static shortest-path shared-edge features are congestion proxies, not future reservations or truth.",
                   "Validation gates two training-fitted alternatives; test costs never tune thresholds, actions or model complexity.",
                   "Selector evaluation reuses exact complete-episode returns and incurs no new simulator calls.",
                   "Any failed episode remains explicit; failed train/validation matrices stop fitting rather than dropping rows.",
                   "Smoke has only eight training groups and may fall back to a fixed policy under min_leaf_groups=8; pipeline check only.",
               ]}
    _write(output / "summary.json", summary)
    if summary["source_changed_during_run"]:
        raise RuntimeError("Source changed during run; preserve evidence as diagnostic only")
    print(json.dumps({"episode_calls": len(episodes), "selected": selection["selected"],
                      "test_mean_cost": {name: metric["mean_cost"] for name, metric in metrics.items()}}, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    run(args.output, smoke=args.smoke)
