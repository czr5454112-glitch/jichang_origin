"""Whole-stream leave-one-out paired-value development, never confirmation.

Labels restore a timed-route controller; deployed learned routes intentionally
change that continuation. This is one policy-improvement diagnostic, not an
on-policy learned-value estimate. Four synthetic streams are not airport days.
"""
import argparse
from collections import Counter
from dataclasses import asdict, replace
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from .experiment_protocol import create_output_directory, check_output_directory
from .label_stability import sustained_scenes, digest
from .learning import TimedAnalyticEvaluator
from .nonlinear_learning import FULL_FEATURE_NAMES, MLPConfig, MLPValueModel
from .phase4_control import ControlSpec, build_engine
from .runtime import COST_WEIGHTS, actual_action_key


PROTOCOL = {
    "schema": "ics_v3_phase4_paired_development_v1", "scope": "synthetic_whole_stream_leave_one_out_development",
    "stream_count": 4, "bands_per_stream": [0, 20, 40], "normal_candidates_only": True,
    "expanded_candidates_train_or_eval": False, "common_future_groups": 4, "futures_per_group": 32,
    "label_aggregation": "128 paired common-future cost differences per normal action, one mean target per action",
    "architecture": "one_hidden_layer_32_tanh_numpy_full_batch_adam", "features": list(FULL_FEATURE_NAMES),
    "model_kinds": ["paired_direct", "residual"], "seeds": [17, 29, 43],
    "epochs": 400, "learning_rate": .01, "l2": .001, "planned_fits": 24,
    "selection": "none; all fixed seeds reported; no evaluation-based model/seed/hyperparameter selection",
    "fold_rule": "hold out one whole stream and all three of its collected checkpoints",
    "all_24_models_frozen_before_assessment_or_deployment": True,
    "normalization": "only the three training streams in that fold",
    "planned_deployment_episodes": 32, "deployment_policies_per_stream": 8,
    "deployed_spec": asdict(ControlSpec(routing="timed", predictive=True, planning_horizon=20, slow_period=2,
                                       route_mode="next_edge", candidate_count=4, expansion_limit=2000)),
    "routing_continuation_mismatch": "labels continue timed routes; learned deployments replace only route selector; slow policy, period, candidate generation and hard permissions match",
    "interpretation": "one policy-improvement development diagnostic, not identical learned label/deployment continuations",
    "distribution_diagnostics": "all routing-boundary state hashes vs matched timed episode; every observed candidate feature against training-fold min/max",
    "independent_airport_days": 0, "fresh_confirmation": False,
    "limits": ["Four constructed streams, nine training and three held-out checkpoints per fold.",
               "Checkpoints, candidates and future replicates are correlated; no independent-sample p-values.",
               "Synthetic future law is not a calibrated operational posterior.",
               "No labels collected at learned-policy states; deployment exposes distribution shift.",
               "Shared-workstation wall timing is descriptive; process CPU also retained."],
}
SOURCES = ("run_paired_development.py", "nonlinear_learning.py", "label_stability.py", "feedback_scenarios.py",
           "phase4_control.py", "conditional_evaluation.py", "prebalance.py", "learning.py", "evaluation.py",
           "runtime.py", "model.py", "routing.py", "routing_reference.py", "experiment_protocol.py")
DEFAULT_LABELS = "outputs/experiments/ics_circulation_v3/phase4_w3_label_stability_20261009"


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def require_complete_manifest(directory):
    directory = Path(directory)
    if not (directory / "summary.json").is_file():
        raise ValueError("Labels are incomplete: summary.json is required before training")
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8-sig"))
    if summary.get("source_changed_during_run") is not False or summary.get("failures") != []:
        raise ValueError("Labels must have unchanged sources and zero failures")
    expected = {s.name for s in sustained_scenes()}
    episodes = summary.get("episodes", [])
    if len(episodes) != 4 or {e["scene"] for e in episodes} != expected:
        raise ValueError("Need exactly the four declared development streams")
    samples = summary.get("samples", [])
    if len(samples) != 12 or any(s.get("failed") is not False for s in samples):
        raise ValueError("Need all twelve complete checkpoint labels")
    if len({s["identity"] for s in samples}) != 12:
        raise ValueError("Duplicate checkpoint identity")
    for stream in expected:
        grouped = [s for s in samples if s["identity"].split(":", 1)[0] == stream]
        if len(grouped) != 3 or {s["band"] for s in grouped} != {0, 20, 40}:
            raise ValueError("All three time bands must remain with their stream")
    expected_branches = sum(s["candidate_count"] * 4 * 32 for s in samples)
    if summary.get("branch_count") != expected_branches:
        raise ValueError("Incomplete label branch denominator")
    return summary


def normal_rows(sample, stream):
    """Reconstruct paired targets from raw costs, never saved ranking statistics."""
    keys, normal = sample["actual_action_keys"], sample["normal_action_keys"]
    features, proposals = sample["features_observable_only"], sample["proposals"]
    if (not keys or len(set(keys)) != len(keys) or not normal or len(normal) > 4
            or len(set(normal)) != len(normal) or not set(normal) <= set(keys) or normal[0] != keys[0]):
        raise ValueError("Normal action pool must be unique, bounded and retain the original baseline")
    if len(features) != len(keys) or len(proposals) != len(keys):
        raise ValueError("Candidate feature/proposal alignment mismatch")
    costs = np.asarray(sample["paired_costs"], dtype=float)
    if costs.shape != (4, len(keys), 32) or not np.isfinite(costs).all():
        raise ValueError("Need complete finite 4 x candidates x 32 paired costs")
    if any(set(f) != set(FULL_FEATURE_NAMES) or not np.isfinite(list(f.values())).all() for f in features):
        raise ValueError("Observable feature schema must match the same 23 training/runtime inputs")
    branches = sample["raw_branches"]
    indices = [(b["replicate"], b["candidate"], b["future_index"]) for b in branches]
    expected = {(r, c, f) for r in range(4) for c in range(len(keys)) for f in range(32)}
    if len(indices) != len(expected) or set(indices) != expected:
        raise ValueError("Missing or duplicate raw paired branch")
    for branch, index in zip(branches, indices):
        components = branch["cost_components"]
        if set(components) != set(COST_WEIGHTS):
            raise ValueError("Raw cost components differ from shared physical objective")
        recomputed = sum(COST_WEIGHTS[name] * value for name, value in components.items())
        if not np.isfinite(recomputed) or abs(recomputed - costs[index]) > 1e-8:
            raise ValueError("Paired cost does not match its original physical components")
    reference = costs[:, 0, :].reshape(-1)
    rows = []
    for ordinal, key in enumerate(normal):
        index = keys.index(key)
        values = costs[:, index, :].reshape(-1)
        deltas = values - reference
        rows.append({"stream": stream, "source_group": sample["summary"]["identity"],
            "band": sample["summary"]["band"], "time": sample["summary"]["time"],
            "candidate_index": index, "normal_ordinal": ordinal, "actual_action_key": key,
            "is_baseline": index == 0, "features": features[index], "cost_mean": float(values.mean()),
            "delta_mean": float(deltas.mean()), "costs": values.tolist(), "paired_deltas": deltas.tolist(),
            "timed_delta": features[index]["timed_analytic_absolute"] - features[0]["timed_analytic_absolute"]})
    return rows


def load_labels(directory):
    directory = Path(directory)
    summary = require_complete_manifest(directory)
    code = Path(__file__).parent
    for name, expected in summary["source_sha256"].items():
        if sha(directory / "source_snapshot" / name) != expected or sha(code / name) != expected:
            raise ValueError("Label source snapshot/current controller mismatch: " + name)
    protocol = json.loads((directory / "protocol.json").read_text(encoding="utf-8-sig"))
    if (protocol["deployed_spec"] != PROTOCOL["deployed_spec"] or protocol["replicate_groups"] != 4
            or protocol["futures_per_group"] != 32 or protocol["sample_bands"] != [0, 20, 40]):
        raise ValueError("Label controller or common-future protocol differs")
    inputs = {"summary.json": sha(directory / "summary.json"), "protocol.json": sha(directory / "protocol.json")}
    rows = []
    for record in summary["samples"]:
        name = record["identity"].replace(":", "_") + ".json"
        sample = json.loads((directory / name).read_text(encoding="utf-8-sig"))
        if sample["summary"] != record or digest(sample["state"]) != sample["source_state_sha256"]:
            raise ValueError("Checkpoint metadata or source-state checksum mismatch")
        if sample["continuation_contract"]["spec"] != PROTOCOL["deployed_spec"]:
            raise ValueError("Checkpoint continuation is not the declared timed controller")
        rows.extend(normal_rows(sample, record["identity"].split(":", 1)[0]))
        inputs[name] = sha(directory / name)
    for scene in sustained_scenes():
        name = scene.name + "_episode.json"
        episode = json.loads((directory / name).read_text(encoding="utf-8-sig"))
        expected = json.loads(json.dumps({"initial": asdict(scene.initial),
            "nominal_future_driver_only": [asdict(b) for b in scene.future_bags],
            "forecast_publications": [asdict(f) for f in scene.forecasts]}))
        if any(episode[key] != value for key, value in expected.items()):
            raise ValueError("Current deployment scene differs from label source stream")
        inputs[name] = sha(directory / name)
    return rows, {"directory": str(directory), "files_sha256": inputs, "label_source_sha256": summary["source_sha256"],
                  "original_branch_count": summary["branch_count"], "checkpoint_count": len(summary["samples"])}


def fit_fold(rows, held_out_stream, kind, seed, *, config=None):
    streams = {r["stream"] for r in rows}
    if len(streams) != 4 or held_out_stream not in streams:
        raise ValueError("A fold requires four whole streams and one held-out stream")
    train = [dict(r, split="train") for r in rows if r["stream"] != held_out_stream]
    train_groups = {r["source_group"] for r in train}
    test_groups = {r["source_group"] for r in rows if r["stream"] == held_out_stream}
    if train_groups & test_groups:
        raise ValueError("A checkpoint cannot appear across stream folds")
    config = config or MLPConfig(epochs=400, learning_rate=.01, l2=.001, seed=seed)
    if config.seed != seed:
        raise ValueError("Training seed must match its fixed declared identity")
    model = MLPValueModel.fit(train, kind, config, feature_names=FULL_FEATURE_NAMES)
    values = np.asarray([[r["features"][name] for name in FULL_FEATURE_NAMES] for r in train])
    bounds = {name: {"minimum": float(values[:, i].min()), "maximum": float(values[:, i].max())}
              for i, name in enumerate(FULL_FEATURE_NAMES)}
    return model, bounds, {"held_out_stream": held_out_stream, "training_streams": sorted(streams - {held_out_stream}),
                           "training_checkpoints": sorted(train_groups), "evaluation_checkpoints": sorted(test_groups),
                           "training_rows": len(train), "held_out_rows": sum(r["stream"] == held_out_stream for r in rows)}


def assess(rows, model=None, kind="timed"):
    groups = sorted({r["source_group"] for r in rows})
    decisions, errors = [], []
    for group in groups:
        candidates = sorted((r for r in rows if r["source_group"] == group), key=lambda r: r["normal_ordinal"])
        reference = next(r for r in candidates if r["is_baseline"])
        scores = ([model.score_features(r["features"], reference["features"]) for r in candidates] if model else
                  [r["timed_delta"] if kind == "timed" else float(r["normal_ordinal"]) for r in candidates])
        chosen = min(range(len(candidates)), key=lambda i: (scores[i], i))
        oracle = min(r["cost_mean"] for r in candidates)
        if model or kind == "timed":
            errors.extend((score - r["delta_mean"]) ** 2 for score, r in zip(scores, candidates))
        decisions.append({"source_group": group, "candidate_count": len(candidates), "scores": scores,
            "chosen_key": candidates[chosen]["actual_action_key"], "baseline_zero": scores[0] == 0.,
            "chosen_cost_mean": candidates[chosen]["cost_mean"], "normal_pool_best_cost_mean": oracle,
            "regret": candidates[chosen]["cost_mean"] - oracle, "chosen_delta": candidates[chosen]["delta_mean"]})
    return {"checkpoint_count": len(groups), "candidate_rows": len(rows), "decisions": decisions,
            "mean_regret": float(np.mean([d["regret"] for d in decisions])),
            "mean_chosen_delta": float(np.mean([d["chosen_delta"] for d in decisions])),
            "delta_rmse": float(np.sqrt(np.mean(errors))) if errors else None,
            "all_baselines_zero": all(d["baseline_zero"] for d in decisions)}


class LearnedSelector:
    def __init__(self, model, bounds, forecasts, *, horizon=20):
        self.model, self.bounds, self.forecasts, self.horizon = model, bounds, tuple(forecasts), horizon
        self.history = []

    def __call__(self, state, candidates):
        if not candidates:
            raise ValueError("No authorized runtime candidates")
        published = tuple(f for f in self.forecasts if f.published_at <= state.now)
        evaluator = TimedAnalyticEvaluator(state.now + self.horizon, published)
        features = [evaluator.features(state, c) for c in candidates]
        scores = [self.model.score_features(f, features[0]) for f in features]
        if scores[0] != 0.:
            raise AssertionError("Reference score must be structurally zero")
        chosen = min(range(len(candidates)), key=lambda i: (scores[i], i))
        outside = [[name for name in FULL_FEATURE_NAMES if
                    f[name] < self.bounds[name]["minimum"] - 1e-9 or f[name] > self.bounds[name]["maximum"] + 1e-9]
                   for f in features]
        self.history.append({"time": state.now, "state_sha256": digest(asdict(state)),
            "published_forecasts": [asdict(f) for f in published], "features": features, "scores": scores,
            "actual_action_keys": [actual_action_key(state, c, route_mode="next_edge") for c in candidates],
            "chosen_index": chosen, "outside_training_range": outside,
            "reference_zero": scores[0] == 0., "feature_schema": list(FULL_FEATURE_NAMES)})
        return candidates[chosen]


def deployment(scene, *, model=None, bounds=None, kind="timed", model_sha256=None):
    wall, cpu = perf_counter(), process_time()
    spec = ControlSpec(**PROTOCOL["deployed_spec"])
    if model is None:
        spec = replace(spec, routing=kind)
        engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec)
    else:
        spec = replace(spec, routing="external")
        selector = LearnedSelector(model, bounds, scene.forecasts)
        engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, spec, route_selector=selector,
            selector_manifest={"implementation": "LearnedSelector", "kind": model.kind, "seed": model.config.seed,
                               "model_sha256": model_sha256, "training_feature_ranges_sha256": digest(bounds)})
    boundaries = []
    while engine.state.now < scene.horizon:
        state = engine.observe()
        boundaries.append({"time": state.now, "state_sha256": digest(asdict(state)),
            "visible_bag_ids": sorted(state.bags), "completed": len(state.completed),
            "waiting": sum(b not in state.load_times and b not in state.completed for b in state.bags),
            "in_transit": sum(t.mode == "in_transit" for t in state.trays.values())})
        engine.advance(state.now + 1)
    result = engine.result()
    bags = {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}}
    history = engine.route_selector.selector.history if model is not None else []
    range_counts = Counter(name for item in history for names in item["outside_training_range"] for name in names)
    metrics = {"status": "completed_run", "total_cost": result.total_cost, "cost_components": result.cost_components,
        "scheduled_bags": len(bags), "completed": len(result.completed), "uncompleted": list(result.uncompleted_bag_ids),
        "on_time": sum(key in result.completed and result.completed[key] <= bag.deadline for key, bag in bags.items()),
        "routing_boundaries": len(boundaries), "selector_calls": len(engine.route_selector.history),
        "candidate_feature_vectors": sum(len(item["features"]) for item in history),
        "candidate_vectors_outside_training_range": sum(bool(names) for item in history for names in item["outside_training_range"]),
        "feature_out_of_range_counts": dict(range_counts), "wall_seconds": perf_counter() - wall,
        "process_cpu_seconds": process_time() - cpu}
    return {"metrics": metrics, "control_contract": engine.control_contract, "result": asdict(result),
            "boundaries": boundaries, "route_history": engine.route_selector.history, "learned_feature_history": history,
            "slow_history": engine.slow_controller.history, "slow_trigger_times": engine.slow_controller.trigger_times}


def run(output, labels=DEFAULT_LABELS, *, protocol_only=False):
    check_output_directory(output)
    if protocol_only:
        output = create_output_directory(output)
        save(output / "protocol.json", {**PROTOCOL, "labels": str(labels), "execution": "protocol_only_no_label_read_or_training"})
        return {"protocol_only": True}
    # Refuse incomplete/changed/failing inputs before any model fit or output.
    rows, inputs = load_labels(labels)
    output = create_output_directory(output)
    code = Path(__file__).parent
    source = {name: (code / name).read_bytes() for name in SOURCES}
    hashes = {name: sha256(data).hexdigest() for name, data in source.items()}
    save(output / "protocol.json", {**PROTOCOL, "labels": str(labels), "source_sha256": hashes})
    save(output / "input_manifest.json", inputs)
    save(output / "normal_candidate_rows.json", rows)
    (output / "source_snapshot").mkdir()
    for name, data in source.items():
        (output / "source_snapshot" / name).write_bytes(data)
    models, ranges, folds, fit_logs = {}, {}, {}, []
    for stream in sorted({r["stream"] for r in rows}):
        for kind in PROTOCOL["model_kinds"]:
            for seed in PROTOCOL["seeds"]:
                name = f"{stream}__{kind}_seed{seed}"
                start, cpu = perf_counter(), process_time()
                model, bounds, fold = fit_fold(rows, stream, kind, seed)
                models[name], ranges[name], folds[name] = model, bounds, fold
                fit_logs.append({"name": name, "kind": kind, "seed": seed, **fold,
                    "wall_seconds": perf_counter() - start, "process_cpu_seconds": process_time() - cpu,
                    "training_metadata": model.training_metadata})
    save(output / "frozen_models.json", {name: m.to_dict() for name, m in models.items()})
    frozen_sha = sha(output / "frozen_models.json")
    save(output / "fold_manifest.json", {"folds": folds, "training_feature_ranges": ranges,
                                         "frozen_models_sha256_before_assessment": frozen_sha})
    save(output / "fit_history.json", fit_logs)
    assessments = {}
    for stream in sorted({r["stream"] for r in rows}):
        held_out = [r for r in rows if r["stream"] == stream]
        assessments[stream] = {kind: assess(held_out, kind=kind) for kind in ("baseline", "timed")}
        for name, model in models.items():
            if folds[name]["held_out_stream"] == stream:
                assessments[stream][name] = assess(held_out, model=model)
    save(output / "held_out_checkpoint_assessments.json", assessments)
    records = []
    for scene in sustained_scenes():
        save(output / (scene.name + "_deployment_inputs.json"), {"initial": asdict(scene.initial),
            "published_forecast_stream": [asdict(f) for f in scene.forecasts],
            "actual_tape_event_engine_only": [asdict(b) for b in scene.future_bags], "horizon": scene.horizon})
        options = [("timed", None), ("baseline", None)] + [(name, model) for name, model in models.items()
                                                           if folds[name]["held_out_stream"] == scene.name]
        timed_states = None
        for name, model in options:
            start, cpu = perf_counter(), process_time()
            try:
                result = deployment(scene, model=model, bounds=ranges.get(name), kind=name,
                                    model_sha256=digest(model.to_dict()) if model else None)
                if model is None:
                    recorded = json.loads((Path(labels) / (scene.name + "_episode.json")).read_text(encoding="utf-8-sig"))
                    expected_cost = recorded["metrics"][name + "_cost"]
                    if abs(result["metrics"]["total_cost"] - expected_cost) > 1e-9:
                        raise ValueError("Repeated reference controller differs from collected stream")
                    result["metrics"]["matches_collected_reference_cost"] = True
                states = {r["time"]: r["state_sha256"] for r in result["boundaries"]}
                if name == "timed":
                    timed_states = states
                if timed_states is None:
                    raise ValueError("Matched timed episode is required for state-drift denominator")
                result["metrics"]["state_hash_differences_from_timed"] = sum(states[t] != timed_states[t] for t in states)
                result["metrics"]["matched_state_boundary_denominator"] = len(states)
            except Exception as error:
                result = {"metrics": {"status": "failed_run", "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags),
                    "total_cost": None, "completed": None, "wall_seconds": perf_counter() - start,
                    "process_cpu_seconds": process_time() - cpu, "failure": {"type": type(error).__name__, "reason": str(error)}}}
            row = result["metrics"]
            row.update(stream=scene.name, policy=name.split("__", 1)[-1], model_name=name if model else None)
            records.append(row)
            save(output / (scene.name + "__" + row["policy"] + "_deployment.json"), result)
            print(json.dumps(row), flush=True)
    summary = {"scope": PROTOCOL["scope"], "fits": len(models), "deployment_runs": len(records),
        "normal_candidate_rows": len(rows), "checkpoint_count": len({r["source_group"] for r in rows}),
        "scheduled_bag_denominator": sum(r["scheduled_bags"] for r in records),
        "completed_bags": sum(r["completed"] or 0 for r in records), "failures": sum(r["status"] == "failed_run" for r in records),
        "deployment_metrics": records, "source_sha256": hashes,
        "source_changed_during_run": any((code / name).read_bytes() != data for name, data in source.items()),
        "frozen_models_changed": sha(output / "frozen_models.json") != frozen_sha,
        "input_files_changed": any(sha(Path(labels) / name) != value for name, value in inputs["files_sha256"].items()),
        "limits": PROTOCOL["limits"], "label_continuation": "timed", "learned_continuation_same_as_labels": False,
        "new_independent_airport_day_count": 0, "hyperparameter_or_seed_selection": False}
    save(output / "summary.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--labels", default=DEFAULT_LABELS)
    parser.add_argument("--protocol-only", action="store_true")
    args = parser.parse_args()
    result = run(args.output, args.labels, protocol_only=args.protocol_only)
    raise SystemExit(int(not args.protocol_only and (result["failures"] or result["source_changed_during_run"]
                        or result["frozen_models_changed"] or result["input_files_changed"])))
