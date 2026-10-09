"""Grouped learning pilot from reachable decision states and first-prefix labels."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from .learning import CandidatePolicy, ForecastRolloutPolicy, RidgeValueModel, TimedAnalyticEvaluator
from .phase2_scenarios import phase2_scenes
from .routing import RegionalCandidateGenerator
from .run_pilot import quantiles, write_json
from .runtime import Simulation

ROOT = Path(__file__).resolve().parents[3]


def source_hashes():
    return {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(__file__).parent.glob("*.py"))}


def generator_factory(horizon=80):
    # Reproducible labels use an expansion bound, not machine-load-dependent
    # wall truncation. The independent real-topology timing gate uses a deadline.
    return RegionalCandidateGenerator(horizon=horizon, expansion_limit=5000, static_path_limit=16, deadline_ms=None)


def write_rows(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows), encoding="utf-8")


def group_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["source_group"]].append(row)
    return groups


def assess(rows, kind, model=None):
    regrets, errors, gains = [], [], []
    decisions = []
    for group, choices in group_rows(rows).items():
        base = next(row for row in choices if row["is_baseline"])
        if kind in {"baseline", "analytic", "timed", "forecast_rollout"}:
            key = {"baseline": "candidate_index", "analytic": "analytic_delta",
                   "timed": "timed_delta", "forecast_rollout": "forecast_delta"}[kind]
            scores = [row[key] for row in choices]
        else:
            scores = [model.score_features(row["features"], base["features"]) for row in choices]
        selected = min(range(len(choices)), key=lambda i: (scores[i], choices[i]["candidate_index"]))
        best = min(row["delta_mean"] for row in choices)
        regret = choices[selected]["delta_mean"] - best
        regrets.append(regret)
        gains.append(-choices[selected]["delta_mean"])
        if kind != "baseline":
            errors.extend((score - row["delta_mean"]) ** 2 for score, row in zip(scores, choices))
        decisions.append({"source_group": group, "selected_index": choices[selected]["candidate_index"],
                          "regret": regret, "gain_over_baseline": gains[-1]})
    return {"groups": len(regrets), "mean_regret": mean(regrets), "max_regret": max(regrets),
            "positive_regret_groups": sum(r > 1e-9 for r in regrets),
            "mean_gain_over_baseline": mean(gains),
            "delta_rmse": (mean(errors) ** .5) if errors else None, "decisions": decisions}


def run(output: Path, *, train=80, validation=20, test=40, deployment=40, evaluation_namespace=""):
    if min(train, validation, test, deployment) < 1:
        raise ValueError("All four disjoint group counts must be positive")
    output.mkdir(parents=True, exist_ok=True)
    initial_source_hashes = source_hashes()
    scenes = phase2_scenes(train, validation, test, deployment, evaluation_namespace)
    split_groups = {split: [s.source_group for s in scenes if s.split == split]
                    for split in ("train", "validation", "test", "deployment")}
    assert len({group for groups in split_groups.values() for group in groups}) == len(scenes)
    write_json(output / "split_manifest.json", {
        "groups": split_groups, "unit": "source_initialization_all_snapshots_candidates_futures_stay_together",
        "label_seeds": [0, 1], "deployment_seed": 991,
        "ridge_grid_fixed_before_labels": [.01, .1, 1., 10., 100.],
        "validation_selection": "mean candidate regret, then RMSE, then ridge penalty",
        "no_test_refitting": True,
        "evaluation_namespace": evaluation_namespace,
    })
    rows, branches, source_records = [], [], []
    started = perf_counter()
    for scene_index, scene in enumerate(scenes):
        if scene.split == "deployment":
            continue
        engines = []
        for seed in (0, 1):
            engine = Simulation(scene.initial, scene.future(seed), route_mode="next_edge",
                                generator_factory=generator_factory, search_horizon=scene.horizon, candidate_count=4)
            engine.advance(scene.intervention_at)
            engines.append(engine)
        visible = engines[0].observe()
        assert engines[1].observe() == visible, "Uncertain history changed the paired decision state"
        assert visible.trays[scene.target_tray].node == "S" and scene.target_tray not in visible.plans
        before = perf_counter()
        candidates = generator_factory().generate(visible, scene.target_bag, scene.target_tray, 4)
        generation_ms = (perf_counter() - before) * 1000
        if len(candidates) != 4:
            raise RuntimeError(f"{scene.source_group}: expected four legal candidates, got {len(candidates)}")
        baseline = candidates[0]
        timed = TimedAnalyticEvaluator(scene.horizon, scene.forecasts)
        analytic = timed._base(visible)
        before = perf_counter()
        features = [timed.features(visible, candidate) for candidate in candidates]
        scoring_ms = (perf_counter() - before) * 1000
        before = perf_counter()
        projected = ForecastRolloutPolicy(scene.horizon, scene.forecasts, generator_factory).values(visible, candidates)
        forecast_scoring_ms = (perf_counter() - before) * 1000
        costs = [[] for _ in candidates]
        for seed, engine in enumerate(engines):
            initial_checkpoint = engine.checkpoint()
            for index, candidate in enumerate(candidates):
                before = perf_counter()
                outcome = engine.branch(candidate).advance(scene.horizon)
                elapsed = (perf_counter() - before) * 1000
                assert engine.checkpoint().state == initial_checkpoint.state
                costs[index].append(outcome.total_cost)
                branches.append({"source_group": scene.source_group, "split": scene.split,
                                 "candidate_index": index, "future_seed": seed,
                                 "total_cost": outcome.total_cost, "cost_components": outcome.cost_components,
                                 "completed": len(outcome.completed), "uncompleted": list(outcome.uncompleted_bag_ids),
                                 "invariant_checks": outcome.invariant_checks, "rollout_ms": elapsed})
        for index, candidate in enumerate(candidates):
            delta = [value - base for value, base in zip(costs[index], costs[0])]
            rows.append({"source_group": scene.source_group, "split": scene.split,
                         "candidate_index": index, "is_baseline": index == 0,
                         "candidate": asdict(candidate), "features": features[index],
                         "cost_mean": mean(costs[index]), "costs": costs[index],
                         "delta_mean": mean(delta), "paired_deltas": delta,
                         "analytic_delta": analytic.delta(visible, candidate, baseline),
                         "timed_delta": timed.delta(visible, candidate, baseline),
                         "forecast_delta": projected[index] - projected[0],
                         "generation_ms": generation_ms, "features_ms": scoring_ms,
                         "forecast_scoring_ms": forecast_scoring_ms})
        source_records.append({"source_group": scene.source_group, "split": scene.split,
                               "initial": asdict(scene.initial), "reachable_snapshot": asdict(visible),
                               "forecasts": [asdict(f) for f in scene.forecasts],
                               "truth_metadata_not_features": {"shift": scene.truth_shift},
                               "futures": [[asdict(b) for b in scene.future(seed)] for seed in (0, 1)]})
        if (scene_index + 1) % 20 == 0:
            print(json.dumps({"labelled_groups": scene_index + 1, "branch_rollouts": len(branches)}), flush=True)
    write_rows(output / "candidates.jsonl", rows)
    write_rows(output / "branches.jsonl", branches)
    write_rows(output / "sources.jsonl", source_records)
    label_ms = (perf_counter() - started) * 1000
    by_split = {split: [row for row in rows if row["split"] == split] for split in ("train", "validation", "test")}
    frozen_models, validation_records = {}, []
    before = perf_counter()
    for kind in ("direct", "residual"):
        attempts = []
        for alpha in (.01, .1, 1., 10., 100.):
            model = RidgeValueModel.fit(by_split["train"], kind, alpha)
            metrics = assess(by_split["validation"], kind, model)
            attempts.append((metrics["mean_regret"], metrics["delta_rmse"], alpha, model))
            validation_records.append({"kind": kind, "alpha": alpha, **metrics})
        winner = min(attempts, key=lambda item: item[:3])
        frozen_models[kind] = winner[3]
        write_json(output / f"{kind}_model.json", winner[3].to_dict())
    fitting_ms = (perf_counter() - before) * 1000
    write_json(output / "validation_selection.json", validation_records)
    # All models are frozen before reading held-out labels for evaluation.
    test_results = {kind: assess(by_split["test"], kind, frozen_models.get(kind))
                    for kind in ("baseline", "analytic", "timed", "direct", "residual", "forecast_rollout")}
    write_json(output / "test_candidates.json", test_results)
    curves = []
    for size in sorted({min(20, train), min(40, train), train}):
        selected_groups = set(split_groups["train"][:size])
        subset = [row for row in by_split["train"] if row["source_group"] in selected_groups]
        for kind in ("direct", "residual"):
            attempts = []
            for alpha in (.01, .1, 1., 10., 100.):
                model = RidgeValueModel.fit(subset, kind, alpha)
                score = assess(by_split["validation"], kind, model)
                attempts.append((score["mean_regret"], score["delta_rmse"], alpha, model))
            model = min(attempts, key=lambda item: item[:3])[3]
            curves.append({"train_groups": size, "kind": kind, "alpha": model.alpha,
                           **assess(by_split["test"], kind, model)})
    write_json(output / "sample_size_curve.json", curves)
    deploy_rows = []
    for scene in scenes:
        if scene.split != "deployment":
            continue
        future = scene.future(991)
        for kind in ("baseline", "analytic", "timed", "direct", "residual", "forecast_rollout"):
            policy = (ForecastRolloutPolicy(scene.horizon, scene.forecasts, generator_factory)
                      if kind == "forecast_rollout" else
                      CandidatePolicy(scene.horizon, scene.forecasts, kind, frozen_models.get(kind)))
            before = perf_counter()
            simulation = Simulation(scene.initial, future, route_mode="next_edge", generator_factory=generator_factory,
                                    route_selector=policy, search_horizon=scene.horizon, candidate_count=4)
            result = simulation.advance(scene.horizon)
            deploy_rows.append({"source_group": scene.source_group, "policy": kind, "total_cost": result.total_cost,
                                "cost_components": result.cost_components, "completed": len(result.completed),
                                "uncompleted": list(result.uncompleted_bag_ids), "invariant_checks": result.invariant_checks,
                                "wall_ms": (perf_counter() - before) * 1000, "policy_stats": result.policy_stats,
                                "nested_forecast_rollouts": getattr(simulation.route_selector, "rollout_count", 0)})
        if len(deploy_rows) % 60 == 0:
            print(json.dumps({"deployment_runs": len(deploy_rows)}), flush=True)
    write_rows(output / "deployment.jsonl", deploy_rows)
    deploy_summary = {}
    reference = {r["source_group"]: r for r in deploy_rows if r["policy"] == "baseline"}
    for kind in ("baseline", "analytic", "timed", "direct", "residual", "forecast_rollout"):
        subset = [r for r in deploy_rows if r["policy"] == kind]
        deploy_summary[kind] = {
            "runs": len(subset), "mean_cost": mean(r["total_cost"] for r in subset),
            "mean_gain_over_baseline": mean(reference[r["source_group"]]["total_cost"] - r["total_cost"] for r in subset),
            "worse_than_baseline": sum(r["total_cost"] > reference[r["source_group"]]["total_cost"] + 1e-9 for r in subset),
            "uncompleted_total": sum(len(r["uncompleted"]) for r in subset),
            "mean_tray_wait": mean(r["cost_components"]["tray_wait"] for r in subset),
            "wall_ms": quantiles([r["wall_ms"] for r in subset]),
        }
    summary = {
        "scope": "synthetic_first_safe_prefix_value_learning_with_disjoint_deployment_sources",
        "evaluation_namespace": evaluation_namespace,
        "source_groups": {key: len(groups) for key, groups in split_groups.items()},
        "candidate_rows": len(rows), "paired_branch_rollouts": len(branches),
        "label_stage_forecast_model_rollouts": len(rows), "deployment_runs": len(deploy_rows),
        "deployment_nested_forecast_model_rollouts": sum(r["nested_forecast_rollouts"] for r in deploy_rows),
        "invariant_checks": sum(r["invariant_checks"] for r in branches + deploy_rows),
        "feature_count": len(rows[0]["features"]), "selected_alpha": {k: v.alpha for k, v in frozen_models.items()},
        "label_and_forecast_evaluation_ms": label_ms, "ridge_fitting_ms": fitting_ms,
        "candidate_test": {k: {name: value for name, value in metric.items() if name != "decisions"}
                           for k, metric in test_results.items()},
        "independent_closed_loop": deploy_summary,
        "generation_ms": quantiles([r["generation_ms"] for r in rows if r["is_baseline"]]),
        "features_ms": quantiles([r["features_ms"] for r in rows if r["is_baseline"]]),
        "forecast_scoring_ms": quantiles([r["forecast_scoring_ms"] for r in rows if r["is_baseline"]]),
        "source_sha256": source_hashes(),
        "source_changed_during_run": source_hashes() != initial_source_hashes,
        "limitations": ["Synthetic seven-node family with full visible physical state; no airport-generalization claim",
                        "Linear ridge models only, not a trained MLP or original PPL/DG-PG algorithm",
                        "Candidate interventions stop at the first waitable node; a no-wait chain is an indivisible prefix",
                        "Forecast-rollout reference receives the same published demand forecast and extra compute, not the true tape",
                        "Strict deadline checks for loaded requests are local; future uncertainty can still cause missed service",
                        "No supplier integration and no network end-to-end latency measurement",
                        "Low-sample benefit must be judged from frozen test and independent deployment, not training loss"],
    }
    write_json(output / "summary.json", summary)
    if summary["source_changed_during_run"]:
        raise RuntimeError("Source changed during evaluation; preserve this run as diagnostic only")
    print(json.dumps({"paired_rollouts": len(branches), "deployment_runs": len(deploy_rows),
                      "test_regret": {k: v["mean_regret"] for k, v in test_results.items()},
                      "deployment_cost": {k: v["mean_cost"] for k, v in deploy_summary.items()}}, indent=2), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/experiments/ics_circulation_v3/phase2_learning_20261009")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--evaluation-namespace", default="")
    args = parser.parse_args()
    run(args.output, evaluation_namespace=args.evaluation_namespace,
        **({"train": 8, "validation": 4, "test": 4, "deployment": 4} if args.smoke else {}))
