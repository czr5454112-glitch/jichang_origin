"""Run: python -m scripts.experiments.ics_circulation_v3.run_pilot"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
from statistics import mean
from time import perf_counter

from .evaluation import AnalyticDeltaEvaluator, CirculationFootprint, PairedRolloutLabeler, ResidualCandidateScorer
from .counterexamples import run_counterexamples
from .runtime import CandidateGenerator, ExecutionValidator
from .scenarios import pilot_scenes


ROOT = Path(__file__).resolve().parents[3]


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def quantiles(values: list[float]) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {}
    def percentile(p):
        return ordered[min(len(ordered) - 1, max(0, int((len(ordered) - 1) * p + .5)))]
    return {"p50": percentile(.5), "p95": percentile(.95), "p99": percentile(.99),
            "max": ordered[-1], "mean": mean(ordered)}


def run(output: Path, future_count: int = 4) -> dict:
    if future_count < 1:
        raise ValueError("future_count must be positive")
    output.mkdir(parents=True, exist_ok=True)
    candidate_rows, branch_rows, timing_rows, scene_rows = [], [], [], []
    scene_manifest = []
    outcomes: Counter = Counter()
    suite_started = perf_counter()
    for scene in pilot_scenes():
        request_started = perf_counter()
        state = scene.state.clone()
        generator = CandidateGenerator(horizon=scene.horizon)
        begin = perf_counter()
        candidates = generator.generate(state, scene.target_bag_id, scene.target_tray_id, k=3)
        generation_ms = (perf_counter() - begin) * 1000
        if not candidates:
            status = generator.last_search_status
            outcomes[f"search:{status}"] += 1
            timing_rows.append({"scene_id": scene.scene_id, "status": status,
                                "candidate_count": 0, "generation_ms": generation_ms,
                                "local_request_ms": (perf_counter() - request_started) * 1000})
            continue
        baseline = candidates[0]
        evaluator = AnalyticDeltaEvaluator(scene.horizon, scene.forecasts)
        scorer = ResidualCandidateScorer(evaluator)
        begin = perf_counter()
        features = [evaluator.features(state, c) for c in candidates]
        footprints = [CirculationFootprint.between(state, c, baseline) for c in candidates]
        feature_ms = (perf_counter() - begin) * 1000
        begin = perf_counter()
        scores = [scorer.score(state, c, baseline) for c in candidates]
        ranking = sorted(range(len(candidates)), key=lambda i: (scores[i], i))
        scoring_ms = (perf_counter() - begin) * 1000
        begin = perf_counter()
        validator = ExecutionValidator()
        validation = [validator.validate(state, c) for c in candidates]
        validation_ms = (perf_counter() - begin) * 1000
        begin = perf_counter()
        commit_state = state.clone()
        selected_index = None
        for index in ranking:
            result = validator.commit(commit_state, candidates[index])
            if result.accepted:
                selected_index = index
                break
        commit_ms = (perf_counter() - begin) * 1000
        request_ms = (perf_counter() - request_started) * 1000
        status = "new_route_success" if selected_index is not None else "commit_failure"
        outcomes[status] += 1
        timing_rows.append({
            "scene_id": scene.scene_id, "status": status, "candidate_count": len(candidates),
            "search_status": generator.last_search_status,
            "generation_ms": generation_ms, "features_ms": feature_ms,
            "scoring_ms": scoring_ms, "validation_ms": validation_ms, "commit_ms": commit_ms,
            "local_request_ms": request_ms, "over_100ms": request_ms >= 100,
            "queue_communication_ms": None, "distributed_end_to_end_ms": None,
        })
        # Future truth is first generated AFTER the observable decision/commit.
        futures = [scene.future(seed) for seed in range(future_count)]
        labels, branches = PairedRolloutLabeler(scene.horizon).label(state, candidates, futures)
        best_true_index = min(range(len(candidates)), key=lambda i: (labels[i]["paired_delta_mean"], i))
        chosen = selected_index if selected_index is not None else ranking[0]
        regret = labels[chosen]["paired_delta_mean"] - labels[best_true_index]["paired_delta_mean"]
        best_gain = -labels[best_true_index]["paired_delta_mean"]
        scene_rows.append({
            "scene_id": scene.scene_id, **scene.factors,
            "analytic_selected_id": candidates[chosen].candidate_id,
            "rollout_best_id": candidates[best_true_index].candidate_id,
            "ranking_disagreement": regret > 1e-9,
            "set_regret": regret,
            "best_gain_over_baseline": best_gain,
            "candidate_count": len(candidates),
        })
        for index, (candidate, label) in enumerate(zip(candidates, labels)):
            candidate_rows.append({
                "scene_id": scene.scene_id, "source_group": scene.scene_id,
                **label, "analytic_delta": scores[index],
                "residual_label": label["paired_delta_mean"] - scores[index],
                "legal": validation[index].accepted, "validation_reason": validation[index].reason,
                "candidate": asdict(candidate), "features": features[index],
                "footprint": asdict(footprints[index]),
            })
        branch_rows.extend({"scene_id": scene.scene_id, "source_group": scene.scene_id, **row}
                           for row in branches)
        scene_manifest.append({"scene_id": scene.scene_id, "factors": scene.factors,
                               "initial_state": asdict(state),
                               "observable_forecast": [asdict(f) for f in scene.forecasts],
                               "future_trajectories": [[asdict(b) for b in future] for future in futures]})
    elapsed_ms = (perf_counter() - suite_started) * 1000
    counterexamples = run_counterexamples()
    write_json(output / "counterexamples.json", counterexamples)
    diagnostic_groups: dict[str, list[float]] = defaultdict(list)
    for scene_row in scene_rows:
        key = f"competition={scene_row['shared_resource_competition']},hold={scene_row['module_hold_ticks']}"
        diagnostic_groups[key].append(scene_row["set_regret"])
    source_files = sorted(Path(__file__).parent.glob("*.py"))
    summary = {
        "schema": "ics_circulation_v3_pilot_v1", "scope": "synthetic_fixed_proxy_mechanism_pilot",
        "scene_count": len(scene_rows), "requested_scene_count": 24,
        "candidate_count": len(candidate_rows), "branch_rollouts": len(branch_rows),
        "future_count_per_scene": future_count,
        "invariant_checks": sum(r["invariant_checks"] for r in branch_rows),
        "counterexample_count": len(counterexamples),
        "counterexamples_passed": all(row["passed"] for row in counterexamples),
        "route_request_outcomes": dict(outcomes),
        "ranking_disagreement_scenes": sum(s["ranking_disagreement"] for s in scene_rows),
        "positive_candidate_space_scenes": sum(s["best_gain_over_baseline"] > 1e-9 for s in scene_rows),
        "mean_set_regret": mean([s["set_regret"] for s in scene_rows]) if scene_rows else None,
        "max_set_regret": max([s["set_regret"] for s in scene_rows], default=None),
        "group_mean_set_regret_descriptive_only": {key: mean(values) for key, values in diagnostic_groups.items()},
        "timing_ms": {field: quantiles([r[field] for r in timing_rows if field in r]) for field in (
            "generation_ms", "features_ms", "scoring_ms", "validation_ms", "commit_ms", "local_request_ms")},
        "local_requests_over_100ms": sum(r["local_request_ms"] >= 100 for r in timing_rows),
        "rollout_ms": quantiles([r["rollout_ms"] for r in branch_rows]),
        "suite_ms": elapsed_ms,
        "independence_unit": "synthetic_initialization_not_noise_seed_or_operating_day",
        "trained_model": None, "learning_gate": "inspect_observable_residual_and_interface_before_training",
        "weights": {"tray_wait": 1, "nonprotected_tardiness": 1, "empty_distance": .1,
                    "terminal_backlog": 10, "terminal_inflight": 2},
        "limits": ["No native G31 or supplier integration", "No regional distributed A* implementation",
                   "Initial intervention commits a whole route until usable; not a V3 single-next-edge intervention",
                   "All initial proxy state is observable; regional partial-observation permissions are not implemented",
                   "No proactive predictive rebalancing; fixed causal continuation uses reactive empty transfers",
                   "No learning gain, causal field effect, novelty or real-airport 100ms claim",
                   "Timing is local in-process only, includes feature/validation/commit; no network measurement",
                   "Forecasts and all physical parameters are synthetic assumptions",
                   "Paired value is finite-horizon under one fixed continuation, not globally optimal Q",
                   "Empty distance uses synthetic unit-speed edge lengths equal to travel ticks, not airport meters",
                   "No train/validation/test or closed-loop trained-policy evaluation in this pilot"],
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "source_sha256": {str(p.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in source_files},
    }
    for filename, rows in (("candidates.jsonl", candidate_rows), ("rollouts.jsonl", branch_rows),
                           ("timings.jsonl", timing_rows), ("scenes.jsonl", scene_manifest)):
        (output / filename).write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rows),
                                       encoding="utf-8")
    write_json(output / "summary.json", summary)
    if candidate_rows:
        fields = ["scene_id", "candidate_id", "baseline_id", "analytic_delta", "paired_delta_mean", "residual_label", "legal"]
        with (output / "candidate_results.csv").open("w", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(candidate_rows)
    write_json(output / "scene_results.json", scene_rows)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/experiments/ics_circulation_v3/pilot_20261009")
    parser.add_argument("--future-count", type=int, default=4)
    args = parser.parse_args()
    summary = run(args.output, args.future_count)
    print(json.dumps({key: summary[key] for key in ("scene_count", "candidate_count", "branch_rollouts",
                     "ranking_disagreement_scenes", "mean_set_regret", "suite_ms")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
