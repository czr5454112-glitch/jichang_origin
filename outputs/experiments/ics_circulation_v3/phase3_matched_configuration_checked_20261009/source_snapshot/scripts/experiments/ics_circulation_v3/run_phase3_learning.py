"""Frozen nonlinear/value-input comparison, with reused training and fresh evaluation.

No new framework, hidden future feature, test-based tuning or claimed theorem.
Run only after source is frozen; every outcome and compute budget is retained.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from statistics import mean
import sys
from time import perf_counter

from .learning import CandidatePolicy, ForecastRolloutPolicy, RidgeValueModel, TimedAnalyticEvaluator
from .nonlinear_learning import MLPConfig, MLPValueModel
from .phase2_scenarios import phase2_scenes
from .run_phase2_learning import assess, generator_factory, write_rows
from .run_pilot import quantiles, write_json
from .runtime import Simulation

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "outputs/experiments/ics_circulation_v3"
TRAINING = BASE / "phase2_learning_confirmatory_20261009"
ROUTE_FEATURES = ("remaining_route_ticks", "edge_ticks", "edge_count",
                  "candidate_deadline_margin", "candidate_first_departure")
PROTOCOL = {
    "schema": "ics_v3_phase3_nonlinear_protocol_v1",
    "training_source": str(TRAINING.relative_to(ROOT)).replace("\\", "/"),
    "training_groups": 80, "validation_groups": 20,
    "fresh_test_groups": 40, "fresh_deployment_groups": 40,
    "evaluation_namespace": "phase3confirm",
    "label_seeds": [0, 1], "deployment_seed": 991,
    "architecture": "one_32_unit_tanh_hidden_layer_numpy_full_batch_adam",
    "primary_training_seed": 17, "additional_fixed_training_seeds": [29, 43],
    "learning_rates": [0.003, 0.01], "l2_penalties": [0.0, 0.001], "epochs": 400,
    "validation_selection": "candidate regret, then delta RMSE, then learning rate, then L2",
    "no_test_selection_of_seed_or_architecture": True,
    "sample_size_curve": [20, 40, 80], "sample_curve_seed": 17,
    "direct_input_ablations_primary_seed_only": ["no_analytic_scores", "route_only"],
    "input_ablation_scope": "bundled input usefulness, not causal isolation of release/resource mechanisms",
    "all_models_frozen_before_generating_new_test_labels": True,
    "extra_forecast_rollout_costs_recorded": True,
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes():
    """Hash this run's loaded experiment-module dependency closure.

    Independent request/prebalance/configuration tools are not dependencies of
    this experiment; merely adding one must not invalidate frozen learning.
    Newly loaded experiment modules at the end also change this mapping.
    """
    directory = Path(__file__).resolve().parent
    paths = {Path(module.__file__).resolve() for module in tuple(sys.modules.values())
             if getattr(module, "__file__", None) and Path(module.__file__).resolve().parent == directory
             and Path(module.__file__).suffix == ".py"}
    paths.add(Path(__file__).resolve())
    return {str(path.relative_to(ROOT)).replace("\\", "/"): sha(path) for path in sorted(paths)}


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def training_rows(smoke=False):
    manifest = json.loads((TRAINING / "split_manifest.json").read_text())
    counts = {"train": 8 if smoke else 80, "validation": 4 if smoke else 20}
    groups = {key: manifest["groups"][key][:count] for key, count in counts.items()}
    records = read_rows(TRAINING / "candidates.jsonl")
    result = {key: [r for r in records if r["source_group"] in set(ids)] for key, ids in groups.items()}
    for key, rows in result.items():
        assert len(rows) == counts[key] * 4 and all(r["split"] == key for r in rows)
    assert not set(groups["train"]) & set(groups["validation"])
    return result, groups


def select_model(train, validation, kind, seed, feature_names, model_name, output, attempts):
    choices = []
    for lr in PROTOCOL["learning_rates"]:
        for penalty in PROTOCOL["l2_penalties"]:
            started = perf_counter()
            model = MLPValueModel.fit(train, kind,
                                      config=MLPConfig(epochs=PROTOCOL["epochs"], learning_rate=lr,
                                                       l2=penalty, seed=seed), feature_names=feature_names)
            elapsed = (perf_counter() - started) * 1000
            metrics = assess(validation, kind, model)
            choices.append((metrics["mean_regret"], metrics["delta_rmse"], lr, penalty, model))
            attempts.append({"model_name": model_name, "seed": seed, "kind": kind,
                             "learning_rate": lr, "l2": penalty, "fit_ms": elapsed,
                             "train_groups": len({r["source_group"] for r in train}), **metrics})
    winner = min(choices, key=lambda row: row[:4])[-1]
    write_json(output / f"{model_name}.json", winner.to_dict())
    print(json.dumps({"trained": model_name, "validation_regret": min(c[0] for c in choices)}), flush=True)
    return winner


def label_fresh_test(scenes, output):
    rows, branches, sources = [], [], []
    for number, scene in enumerate(scenes):
        engines = [Simulation(scene.initial, scene.future(seed), route_mode="next_edge",
                              generator_factory=generator_factory, search_horizon=scene.horizon,
                              candidate_count=4) for seed in (0, 1)]
        for engine in engines:
            engine.advance(scene.intervention_at)
        state = engines[0].observe()
        assert state == engines[1].observe()
        assert state.trays[scene.target_tray].node == "S" and scene.target_tray not in state.plans
        started = perf_counter()
        candidates = generator_factory().generate(state, scene.target_bag, scene.target_tray, 4)
        generation_ms = (perf_counter() - started) * 1000
        if len(candidates) != 4:
            raise RuntimeError(f"{scene.source_group}: expected exactly four authorized candidates")
        evaluator = TimedAnalyticEvaluator(scene.horizon, scene.forecasts)
        started = perf_counter()
        features = [evaluator.features(state, candidate) for candidate in candidates]
        features_ms = (perf_counter() - started) * 1000
        started = perf_counter()
        projected = ForecastRolloutPolicy(scene.horizon, scene.forecasts, generator_factory).values(state, candidates)
        forecast_ms = (perf_counter() - started) * 1000
        costs = [[] for _ in candidates]
        for seed, engine in enumerate(engines):
            checkpoint = engine.checkpoint()
            for index, candidate in enumerate(candidates):
                result = engine.branch(candidate).advance(scene.horizon)
                assert engine.checkpoint().state == checkpoint.state
                costs[index].append(result.total_cost)
                branches.append({"source_group": scene.source_group, "future_seed": seed,
                                 "candidate_index": index, "total_cost": result.total_cost,
                                 "cost_components": result.cost_components, "completed": len(result.completed),
                                 "uncompleted": list(result.uncompleted_bag_ids),
                                 "invariant_checks": result.invariant_checks})
        for index, candidate in enumerate(candidates):
            delta = [value - baseline for value, baseline in zip(costs[index], costs[0])]
            rows.append({"source_group": scene.source_group, "split": "test", "candidate_index": index,
                         "is_baseline": index == 0, "candidate": asdict(candidate), "features": features[index],
                         "cost_mean": mean(costs[index]), "costs": costs[index], "paired_deltas": delta,
                         "delta_mean": mean(delta), "analytic_delta": features[index]["analytic_absolute"] - features[0]["analytic_absolute"],
                         "timed_delta": features[index]["timed_analytic_absolute"] - features[0]["timed_analytic_absolute"],
                         "forecast_delta": projected[index] - projected[0], "generation_ms": generation_ms,
                         "features_ms": features_ms, "forecast_scoring_ms": forecast_ms})
        sources.append({"source_group": scene.source_group, "initial": asdict(scene.initial),
                        "reachable_snapshot": asdict(state), "forecasts": [asdict(f) for f in scene.forecasts],
                        "truth_metadata_not_features": {"shift": scene.truth_shift},
                        "futures": [[asdict(b) for b in scene.future(seed)] for seed in (0, 1)]})
        if (number + 1) % 10 == 0:
            print(json.dumps({"fresh_test_groups_labelled": number + 1}), flush=True)
    write_rows(output / "test_candidates.jsonl", rows)
    write_rows(output / "test_branches.jsonl", branches)
    write_rows(output / "test_sources.jsonl", sources)
    return rows, branches


def execute_deployment(scenes, models, output):
    records, sources = [], []
    policy_specs = [(kind, kind, None) for kind in ("baseline", "analytic", "timed", "forecast_rollout")]
    policy_specs.extend((name, model.kind, model) for name, model in models.items())
    for number, scene in enumerate(scenes):
        future = scene.future(991)
        initial_bags = {**scene.initial.bags, **{bag.bag_id: bag for bag in future}}
        sources.append({"source_group": scene.source_group, "initial": asdict(scene.initial),
                        "forecasts": [asdict(f) for f in scene.forecasts], "future_seed": 991,
                        "future_not_policy_input": [asdict(b) for b in future]})
        for name, kind, model in policy_specs:
            policy = (ForecastRolloutPolicy(scene.horizon, scene.forecasts, generator_factory)
                      if kind == "forecast_rollout" else CandidatePolicy(scene.horizon, scene.forecasts, kind, model))
            started = perf_counter()
            engine = Simulation(scene.initial, future, route_mode="next_edge", generator_factory=generator_factory,
                                route_selector=policy, search_horizon=scene.horizon, candidate_count=4)
            result = engine.advance(scene.horizon)
            records.append({"source_group": scene.source_group, "policy": name, "total_cost": result.total_cost,
                            "cost_components": result.cost_components, "completed": len(result.completed),
                            "completed_at": result.completed, "bag_denominator": len(initial_bags),
                            "on_time": sum(result.completed.get(bag_id, scene.horizon + 1) <= bag.deadline
                                           for bag_id, bag in initial_bags.items() if bag_id in result.completed),
                            "uncompleted": list(result.uncompleted_bag_ids), "invariant_checks": result.invariant_checks,
                            "wall_ms": (perf_counter() - started) * 1000, "policy_stats": result.policy_stats,
                            "nested_forecast_rollouts": getattr(engine.route_selector, "rollout_count", 0)})
        if (number + 1) % 10 == 0:
            print(json.dumps({"deployment_source_groups": number + 1, "deployment_runs": len(records)}), flush=True)
    write_rows(output / "deployment.jsonl", records)
    write_rows(output / "deployment_sources.jsonl", sources)
    return records


def summarize_deployment(records):
    baselines = {r["source_group"]: r for r in records if r["policy"] == "baseline"}
    timed = {r["source_group"]: r for r in records if r["policy"] == "timed"}
    result = {}
    for kind in dict.fromkeys(r["policy"] for r in records):
        subset = [r for r in records if r["policy"] == kind]
        result[kind] = {"runs": len(subset), "mean_cost": mean(r["total_cost"] for r in subset),
                        "mean_delta_from_timed": mean(r["total_cost"] - timed[r["source_group"]]["total_cost"] for r in subset),
                        "better_than_timed": sum(r["total_cost"] < timed[r["source_group"]]["total_cost"] - 1e-9 for r in subset),
                        "worse_than_timed": sum(r["total_cost"] > timed[r["source_group"]]["total_cost"] + 1e-9 for r in subset),
                        "worse_than_baseline": sum(r["total_cost"] > baselines[r["source_group"]]["total_cost"] + 1e-9 for r in subset),
                        "completed": sum(r["completed"] for r in subset), "bag_denominator": sum(r["bag_denominator"] for r in subset),
                        "on_time": sum(r["on_time"] for r in subset), "uncompleted_total": sum(len(r["uncompleted"]) for r in subset),
                        "mean_tray_wait": mean(r["cost_components"]["tray_wait"] for r in subset),
                        "wall_ms_whole_episode": quantiles([r["wall_ms"] for r in subset])}
    return result


def run(output, smoke=False):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new output directory; historical evidence is not overwritten")
    output.mkdir(parents=True, exist_ok=True)
    start_hashes = source_hashes()
    namespace = "phase3smoke" if smoke else PROTOCOL["evaluation_namespace"]
    protocol = {**PROTOCOL, "smoke": smoke, "actual_evaluation_namespace": namespace,
                "source_hash_scope": "loaded experiment module dependency closure, including entrypoint",
                "source_sha256_before": start_hashes,
                "training_input_sha256": {p.name: sha(p) for p in (TRAINING / "candidates.jsonl", TRAINING / "split_manifest.json")}}
    write_json(output / "protocol.json", protocol)  # Written before fitting or generating held-out labels.
    rows, train_groups = training_rows(smoke)
    names = tuple(sorted(rows["train"][0]["features"]))
    models, curve_models, attempts = {}, {}, []
    for kind in ("direct", "residual"):
        # Unchanged train/validation data and prior validation-selected frozen ridge.
        models[f"ridge_{kind}"] = RidgeValueModel.from_dict(json.loads((TRAINING / f"{kind}_model.json").read_text()))
    seeds = [17] if smoke else [17, 29, 43]
    for seed in seeds:
        for kind in ("direct", "residual"):
            name = f"mlp_{kind}_seed{seed}"
            models[name] = select_model(rows["train"], rows["validation"], kind, seed, names, name, output, attempts)
    for label, features in (("no_analytic_scores", tuple(n for n in names if n not in {"analytic_absolute", "timed_analytic_absolute"})),
                            ("route_only", ROUTE_FEATURES)):
        name = f"mlp_direct_{label}"
        models[name] = select_model(rows["train"], rows["validation"], "direct", 17, features, name, output, attempts)
    if not smoke:
        for size in (20, 40):
            keep = set(train_groups["train"][:size])
            subset = [r for r in rows["train"] if r["source_group"] in keep]
            for kind in ("direct", "residual"):
                name = f"curve_{size}_{kind}"
                curve_models[name] = select_model(subset, rows["validation"], kind, 17, names, name, output, attempts)
    write_json(output / "validation_selection.json", attempts)
    frozen = {name: model.to_dict() for name, model in {**models, **curve_models}.items()}
    write_json(output / "frozen_models.json", frozen)
    frozen_hash = sha(output / "frozen_models.json")
    scenes = phase2_scenes(0, 0, 4 if smoke else 40, 4 if smoke else 40, namespace)
    split_groups = {**train_groups, **{split: [s.source_group for s in scenes if s.split == split] for split in ("test", "deployment")}}
    assert len({g for groups in split_groups.values() for g in groups}) == sum(map(len, split_groups.values()))
    for old in (BASE / "phase2_learning_20261009", TRAINING):
        previous = json.loads((old / "split_manifest.json").read_text())["groups"]
        previous_all = {g for groups in previous.values() for g in groups}
        assert not previous_all & set(split_groups["test"] + split_groups["deployment"])
    write_json(output / "split_manifest.json", {"groups": split_groups, "frozen_models_sha256_before_test": frozen_hash,
                                                 "old_train_validation_reused": True, "old_evaluation_groups_reused": False})
    started = perf_counter()
    test_rows, branches = label_fresh_test([s for s in scenes if s.split == "test"], output)
    test_label_ms = (perf_counter() - started) * 1000
    metrics = {kind: assess(test_rows, kind) for kind in ("baseline", "analytic", "timed", "forecast_rollout")}
    metrics.update({name: assess(test_rows, model.kind, model) for name, model in models.items()})
    write_json(output / "test_metrics.json", metrics)
    curves = [{"train_groups": int(name.split("_")[1]), "kind": model.kind, **assess(test_rows, model.kind, model)}
              for name, model in curve_models.items()]
    curves.extend({"train_groups": 8 if smoke else 80, "kind": kind, **metrics[f"mlp_{kind}_seed17"]}
                  for kind in ("direct", "residual"))
    write_json(output / "sample_size_curve.json", curves)
    deployment = execute_deployment([s for s in scenes if s.split == "deployment"], models, output)
    assert sha(output / "frozen_models.json") == frozen_hash
    summary = {
        "scope": "same_synthetic_family_fresh_groups_nonlinear_and_input_comparison",
        "smoke": smoke, "source_groups": {key: len(groups) for key, groups in split_groups.items()},
        "reused_training_validation_candidate_rows": sum(map(len, rows.values())),
        "reused_training_validation_paired_branches": sum(map(len, rows.values())) * 2,
        "new_candidate_rows": len(test_rows), "new_paired_branch_rollouts": len(branches),
        "new_label_stage_forecast_rollouts": len(test_rows), "deployment_runs": len(deployment),
        "deployment_nested_forecast_rollouts": sum(r["nested_forecast_rollouts"] for r in deployment),
        "training_fit_count": len(attempts), "total_fit_ms": sum(r["fit_ms"] for r in attempts),
        "fresh_label_and_reference_ms": test_label_ms,
        "test_metrics": {key: {k: v for k, v in metric.items() if k != "decisions"} for key, metric in metrics.items()},
        "independent_closed_loop": summarize_deployment(deployment),
        "frozen_models_sha256": frozen_hash, "invariant_checks": sum(r["invariant_checks"] for r in branches + deployment),
        "source_sha256": start_hashes, "source_changed_during_run": source_hashes() != start_hashes,
        "limitations": ["Same seven-node synthetic family, not airport/day generalization.",
                        "Fixed three training seeds are reported individually, never selected on test.",
                        "All input/architecture choices were specified before fresh test labels.",
                        "Route-only/no-score ablations remove input bundles; they do not isolate a single causal mechanism.",
                        "Different ablation input dimensions change parameter count despite identical hidden width.",
                        "Candidate regret is relative to a finite set and two continuation futures, not globally optimal Q.",
                        "Full episode wall time is not a per-request end-to-end contract.",
                        "MLP/rollout approximations do not authorize actions or inherit PPL/DG-PG guarantees."]}
    write_json(output / "summary.json", summary)
    if summary["source_changed_during_run"]:
        raise RuntimeError("Source changed during run; keep as diagnostic only")
    print(json.dumps({"test_regret": {k: v["mean_regret"] for k, v in metrics.items()},
                      "deployment_cost": {k: v["mean_cost"] for k, v in summary["independent_closed_loop"].items()}}, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    run(args.output, args.smoke)
