"""Full-information, scene-start configuration baseline; no PPL/AIPW claim.

Generate four paired complete-episode returns for each train/validation/test
source. Freeze a training-only stump and best fixed controller, then gate on
validation. Default runs are development replays, not new held-out evidence.
Explicit reproduce/fresh-confirmation modes register their source semantics.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import re
from statistics import mean
from time import perf_counter
import traceback

from .joint_control import build_engine
from .experiment_protocol import (check_output_directory, create_output_directory, manifest_groups,
                                  read_json_object, source_reuse_record)
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
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    directory = Path(__file__).resolve().parent
    names = ("experiment_protocol.py", "scene_configuration.py", "run_scene_configuration.py", "joint_control.py", "phase2_scenarios.py",
             "learning.py", "evaluation.py", "model.py", "runtime.py", "routing.py", "prebalance.py")
    return {name: _sha(directory / name) for name in names}


def configuration_scenes(*, smoke=False):
    counts = {"train": 8, "validation": 4, "test": 4} if smoke else PROTOCOL["counts"]
    namespace = "phase3_config_smoke" if smoke else PROTOCOL["source_namespace"]
    return {split: tuple(replace(make_scene(index, f"{namespace}_{split}"), split=split) for index in range(count))
            for split, count in counts.items()}


def _scenes_from_groups(groups):
    scenes = {}
    for split, identifiers in groups.items():
        values = []
        for identifier in identifiers:
            match = re.fullmatch(r"v3_phase2:([^:]+):(\d+)", identifier)
            if not match:
                raise ValueError(f"Unsupported source ID for this scene generator: {identifier}")
            scene = replace(make_scene(int(match[2]), match[1]), split=split)
            if scene.source_group != identifier:
                raise ValueError(f"Noncanonical source ID: {identifier}")
            values.append(scene)
        scenes[split] = tuple(values)
    return scenes


def prepare_configuration_run(*, smoke=False, mode="development", reference_protocol=None,
                              reference_manifest=None, evaluation_namespace=None,
                              training_manifest=None, history_manifests=()):
    """Validate provenance and construct sources before creating output files."""
    if mode not in {"development", "reproduce", "fresh-confirmation"}:
        raise ValueError("Unknown experiment mode")
    references, allowed_train = {}, ()
    protocol = dict(PROTOCOL)
    if mode == "reproduce":
        if reference_protocol is None or reference_manifest is None:
            raise ValueError("reproduce requires --reference-protocol and --reference-manifest")
        if smoke or evaluation_namespace is not None or training_manifest is not None:
            raise ValueError("reproduce takes counts and sources only from its original protocol/manifest; no overrides")
        original = read_json_object(reference_protocol)
        if original.get("schema") != PROTOCOL["schema"]:
            raise ValueError("Unsupported reference protocol schema")
        for field in ("configurations", "feature_names", "decision_time", "stump_training", "fixed_training",
                      "validation_selection", "held_out_protocol", "label_scope", "estimator", "evaluation"):
            if original.get(field) != PROTOCOL[field]:
                raise ValueError(f"Reference protocol incompatible with this runner: {field}")
        if original.get("weights") != COST_WEIGHTS:
            raise ValueError("Reference cost weights differ from this runner")
        groups = manifest_groups(read_json_object(reference_manifest), required_splits=("train", "validation", "test"))
        counts = original.get("actual_counts")
        if (not isinstance(counts, dict) or counts != {split: len(ids) for split, ids in groups.items()}
                or any(type(value) is not int or value < 1 for value in counts.values())):
            raise ValueError("Reference counts must exactly match its manifest; reproduction cannot add samples")
        if (type(original.get("actual_expected_episode_calls")) is not int
                or original["actual_expected_episode_calls"] != sum(counts.values()) * len(CONFIGURATIONS)):
            raise ValueError("Reference episode count does not match its manifest")
        if type(original.get("future_seed")) is not int or type(original.get("min_leaf_groups")) is not int or original["min_leaf_groups"] < 1:
            raise ValueError("Reference future_seed/min_leaf_groups must be valid integers")
        if type(original.get("smoke")) is not bool:
            raise ValueError("Reference smoke flag must be a boolean")
        smoke = original["smoke"]
        protocol.update(future_seed=original["future_seed"], min_leaf_groups=original["min_leaf_groups"],
                        source_namespace=original.get("source_namespace"), counts=counts)
        references = {"original_protocol": {"path": str(Path(reference_protocol).resolve()), "sha256": _sha(reference_protocol)},
                      "original_manifest": {"path": str(Path(reference_manifest).resolve()), "sha256": _sha(reference_manifest)},
                      "original_source_sha256": original.get("source_sha256_before", {}),
                      "same_source_groups_not_new_samples": True}
    else:
        if reference_protocol is not None or reference_manifest is not None:
            raise ValueError("Reference protocol/manifest are only accepted in reproduce mode")
        if mode == "fresh-confirmation" and not evaluation_namespace:
            raise ValueError("fresh-confirmation requires --evaluation-namespace and registered-source checks")
        if evaluation_namespace is not None and not re.fullmatch(r"[A-Za-z0-9_-]+", evaluation_namespace):
            raise ValueError("evaluation namespace must contain only letters, digits, underscores or hyphens")
        scenes = configuration_scenes(smoke=smoke)
        groups = {split: [scene.source_group for scene in values] for split, values in scenes.items()}
        if evaluation_namespace is not None:
            groups = {split: [make_scene(index, f"{evaluation_namespace}_{split}").source_group for index in range(len(ids))]
                      for split, ids in groups.items()}
            protocol["source_namespace"] = evaluation_namespace
        if training_manifest is not None:
            if mode != "fresh-confirmation":
                raise ValueError("--training-manifest is explicit training reuse for fresh-confirmation only")
            prior = manifest_groups(read_json_object(training_manifest))
            if "train" not in prior:
                raise ValueError("Training manifest must contain a train split")
            groups["train"] = prior["train"]
            allowed_train = tuple(prior["train"])
            references["reused_training_manifest"] = {"path": str(Path(training_manifest).resolve()), "sha256": _sha(training_manifest)}
    manifest_groups({"groups": groups}, required_splits=("train", "validation", "test"))
    history = list(BASE.glob("*/split_manifest.json")) + list(history_manifests)
    history += [path for path in (reference_manifest, training_manifest) if path is not None]
    reuse = source_reuse_record(groups, mode=mode, history_paths=history, allowed_training_ids=allowed_train)
    reuse.update(references)
    protocol.update(smoke=smoke, pipeline_only_if_smoke=smoke, experiment_mode=mode,
                    actual_counts={split: len(ids) for split, ids in groups.items()},
                    actual_expected_episode_calls=sum(map(len, groups.values())) * len(CONFIGURATIONS),
                    weights=COST_WEIGHTS, source_reuse=reuse)
    return _scenes_from_groups(groups), protocol, reuse


def _observable(scene):
    return initial_features(scene.initial, scene.forecasts, target_bag_id=scene.target_bag, horizon=scene.horizon)


def collect_episodes(scenes, output: Path, split: str, *, future_seed=None):
    """Exactly one simulation for each (source, configuration); never a selector."""
    table, episodes, sources = [], [], []
    for number, scene in enumerate(scenes):
        features = _observable(scene)
        seed = PROTOCOL["future_seed"] if future_seed is None else future_seed
        future = scene.future(seed)
        expected = {**scene.initial.bags, **{bag.bag_id: bag for bag in future}}
        if len(expected) != len(scene.initial.bags) + len(future):
            raise ValueError("Duplicate bag IDs invalidate episode denominators")
        initial, forecasts, tape = asdict(scene.initial), [asdict(f) for f in scene.forecasts], [asdict(b) for b in future]
        hashes = {"initial_sha256": _hash(initial), "forecast_sha256": _hash(forecasts),
                  "future_sha256": _hash(tape), "features_sha256": _hash(features)}
        sources.append({"source_group": scene.source_group, "split": split, "initial": initial,
                        "published_forecasts": forecasts, "future_event_engine_only": tape,
                        "horizon": scene.horizon, "future_seed": seed,
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


def run(output: Path, *, smoke=False, mode="development", reference_protocol=None,
        reference_manifest=None, evaluation_namespace=None, training_manifest=None, history_manifests=()):
    output = check_output_directory(output)
    before = source_hashes()
    scenes, protocol, reuse = prepare_configuration_run(
        smoke=smoke, mode=mode, reference_protocol=reference_protocol, reference_manifest=reference_manifest,
        evaluation_namespace=evaluation_namespace, training_manifest=training_manifest, history_manifests=history_manifests)
    smoke = protocol["smoke"]
    groups = {split: [scene.source_group for scene in values] for split, values in scenes.items()}
    actual_calls = sum(map(len, groups.values())) * 4
    protocol.update(source_sha256_before=before,
                    historical_split_manifest_sha256={path: row["sha256"] for path, row in reuse["history"].items()})
    output = create_output_directory(output)
    _write(output / "protocol.json", protocol)
    _write(output / "split_manifest.json", {"groups": groups, "mode": mode,
                                           "disjoint_from_recorded_prior_splits": reuse["disjoint_from_recorded_prior_splits"],
                                           "new_independent_source_count": reuse["new_independent_source_count"],
                                           "new_confirmation_test_source_count": reuse["new_confirmation_test_source_count"]})
    _write(output / "reproduction_manifest.json", reuse)
    seed_kwargs = {} if protocol["future_seed"] == PROTOCOL["future_seed"] else {"future_seed": protocol["future_seed"]}
    train, train_runs = collect_episodes(scenes["train"], output, "train", **seed_kwargs)
    validation, validation_runs = collect_episodes(scenes["validation"], output, "validation", **seed_kwargs)
    try:
        fixed, stump = fit_selectors(train, min_leaf_groups=protocol["min_leaf_groups"])
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
    test, test_runs = collect_episodes(scenes["test"], output, "test", **seed_kwargs)
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
               "experiment_mode": mode, "source_reuse_claim": reuse["claim"],
               "new_independent_source_count": reuse["new_independent_source_count"],
               "new_confirmation_test_source_count": reuse["new_confirmation_test_source_count"],
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


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--mode", choices=("development", "reproduce", "fresh-confirmation"), default="development",
                        help="default: development replay; it never adds held-out evidence")
    parser.add_argument("--reference-protocol", type=Path)
    parser.add_argument("--reference-manifest", type=Path)
    parser.add_argument("--evaluation-namespace")
    parser.add_argument("--training-manifest", type=Path)
    parser.add_argument("--history-manifest", type=Path, action="append", default=[],
                        help="additional prior source registry outside the repository's saved split manifests")
    args = parser.parse_args(argv)
    run(args.output, smoke=args.smoke, mode=args.mode, reference_protocol=args.reference_protocol,
        reference_manifest=args.reference_manifest, evaluation_namespace=args.evaluation_namespace,
        training_manifest=args.training_manifest, history_manifests=args.history_manifest)


if __name__ == "__main__":
    main()
