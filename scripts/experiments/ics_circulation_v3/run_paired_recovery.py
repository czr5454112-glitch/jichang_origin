"""Multi-role, whole-stream held-out fixed-timed-value recovery development.

Stages are deliberately separate commands. R0 freezes all 48 fits and reports
the predeclared noise rule. R1 samples only each model's three training streams,
then fits all 24 physical-input models. Evaluation cannot begin until both
stages and their input/output checksums are complete. This is development on
four constructed streams, not a fresh confirmation or learned-policy Q target.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, replace
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
from time import perf_counter, process_time

import numpy as np

from .experiment_protocol import create_output_directory, check_output_directory
from .label_stability import digest, sampled_futures, sustained_scenes
from .learning import TimedAnalyticEvaluator
from .nonlinear_learning import FULL_FEATURE_NAMES, PHYSICAL_FEATURE_NAMES, MLPConfig, MLPValueModel
from .phase4_control import ControlSpec, PublishedRoutingSelector, build_engine
from .role_coverage import RoleQuota, branch_role_decision, collect_role_decisions, sample_artifact
from .role_features import physical_features
from .runtime import COST_WEIGHTS, actual_action_key


SCHEMAS = {"paired23": FULL_FEATURE_NAMES, "physical31": PHYSICAL_FEATURE_NAMES}
KINDS, SEEDS = ("paired_direct", "residual"), (17, 29, 43)
SPEC = ControlSpec(routing="timed", predictive=True, planning_horizon=20, slow_period=2,
                   route_mode="next_edge", candidate_count=4, expansion_limit=2000)
SOURCES = ("run_paired_recovery.py", "role_coverage.py", "role_features.py", "nonlinear_learning.py",
           "label_stability.py", "feedback_scenarios.py", "phase4_control.py", "conditional_evaluation.py",
           "prebalance.py", "learning.py", "evaluation.py", "runtime.py", "model.py", "routing.py",
           "routing_reference.py", "experiment_protocol.py")
PROTOCOL = {
    "schema": "ics_v3_multirole_paired_recovery_v1", "scope": "synthetic_four_stream_development",
    "streams": [s.name for s in sustained_scenes()], "spec": asdict(SPEC),
    "quota": {"bands": [0, 20, 40], "nodes": ["S", "B", "C", "G"],
              "roles": ["origin", "continuation", "arrival_at_destination"], "per_cell": 1,
              "max_samples": 9, "selection_rule": "node_role_round_robin"},
    "normal_candidates": 4, "include_zero_single_multiple_opportunities": True,
    "schemas": {k: list(v) for k, v in SCHEMAS.items()}, "parameters": {"paired23": 801, "physical31": 1057},
    "kinds": list(KINDS), "seeds": list(SEEDS), "epochs": 400, "learning_rate": .01, "l2": .001,
    "r0": {"collector": "timed", "groups": 4, "futures_per_group": 8, "fits": 48, "max_checkpoints": 36,
           "max_requested_branches": 4608},
    "r1": {"collector": "each frozen physical31 R0 model on only its three training streams",
           "schema": "physical31", "collection_episodes": 72, "fits": 24, "max_checkpoints": 648,
           "futures_per_group": 8, "groups": "per fold's three training streams only: 2 if every strict gate passes and sampled node/role was observed there; otherwise 4",
           "max_requested_branches_at_4_groups": 82944, "fit_rows": "R0 training rows plus this model's R1 rows"},
    "noise_gate": {"comparison": "within each of four R0 groups, first 2 vs all 8 futures exact optimal-set equality",
                   "tie_tolerance": 1e-9, "optimal_set_agreement_minimum": .95,
                   "cross_group_regret": "choose first-index optimum of one 8-future group, evaluate in each other group",
                   "cross_group_mean_regret_maximum": .1,
                   "group_budget_check": "first two groups vs all four exact optimal-set equality; chosen first-half action evaluated on last two groups",
                   "group_budget_agreement_minimum": .95, "last_two_groups_mean_regret_maximum": .1,
                   "required_subsets": ["all", "source_B"], "empty_required_subset_passes": False,
                   "single_action_states": "reported but excluded from ranking-stability gate",
                   "fold_isolation": "held-out labels never affect its recovery budget or role support; pooled diagnostic cannot select budget",
                   "unseen_node_role": "always four groups even if the training-fold gate passes"},
    "label_continuation": "fixed timed with original exact physical cursor and slow clock",
    "target": "paired common-future cost delta; residual subtracts timed analytic delta",
    "fold_rule": "hold out an entire stream including every time band, task role and recovered checkpoint",
    "normalization": "only the current fold/model training rows",
    "selection": "no hyperparameter, seed, schema or held-out-result model selection",
    "fit_freeze": "all R0 and R1 data and 72 models complete before any held-out assessment/deployment",
    "stress_tapes": {"count_per_stream": 8, "seed": "int(digest([scene.name,'role_recovery_deployment_v1'])[:16],16)",
                     "law": "sampled_futures on initial observed state; fixed public forecast stream"},
    "deployment": {"policies_per_stream": 20, "realizations_per_stream": 9, "episodes": 720,
                   "policies": "baseline,timed,all 12 R0 models,all 6 R1 models", "nominal_episodes": 80,
                   "stress_episodes": 640},
    "cache": "R1 sample-local exact candidate+future-tape reuse, scoped to same complete checkpoint, fixed timed continuation and horizon; retain every requested branch",
    "limits": ["Four synthetic streams are not independent airport days or fresh confirmation.",
               "R1 is fixed-policy value recovery at learned-policy states, not on-policy Q learning.",
               "23/31 input comparison changes input semantics and parameter count, with paired/residual equal within each schema.",
               "Role cells never reached are reported empty; quota coverage does not establish representative operational coverage.",
               "Deployment shares the synthetic stress family, not the label state-conditional distribution or a calibrated posterior.",
               "R0/R1 collection uses nominal streams; pressure-deployment states remain outside this collection guarantee.",
               "R0/R1 concatenation weights candidate rows equally; it does not equalize role or episode frequency.",
               "Wall timing on a shared workstation is descriptive; process CPU and all branch denominators are retained."],
}


def save(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def model_name(stream, schema, kind, seed):
    return f"{stream}__{schema}__{kind}_seed{seed}"


def validate_source(output):
    output = Path(output)
    protocol = read(output / "protocol.json")
    if {k: v for k, v in protocol.items() if k != "source_sha256"} != PROTOCOL:
        raise ValueError("Frozen recovery protocol differs from current declared protocol")
    for name, expected in protocol["source_sha256"].items():
        if sha(Path(__file__).parent / name) != expected or sha(output / "source_snapshot" / name) != expected:
            raise ValueError("Frozen recovery source changed: " + name)
    return protocol


def freeze_stage(output, stage, summary):
    validate_source(output)
    folder = Path(output) / stage
    save(folder / "summary.json", summary)
    files = {p.relative_to(folder).as_posix(): sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}
    save(folder / "stage_manifest.json", {"stage": stage, "files_sha256": files,
         "protocol_sha256": sha(Path(output) / "protocol.json"), "source_changed_during_run": False})
    return summary


def check_stage(output, stage):
    validate_source(output)
    folder = Path(output) / stage
    if not (folder / "stage_manifest.json").is_file():
        raise ValueError("Stage incomplete; no frozen manifest: " + stage)
    manifest = read(folder / "stage_manifest.json")
    if (manifest["source_changed_during_run"] is not False
            or manifest["protocol_sha256"] != sha(Path(output) / "protocol.json")):
        raise ValueError("Stage source/protocol changed")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(manifest["files_sha256"]) | {"stage_manifest.json"}:
        raise ValueError("Stage artifact set changed")
    for name, expected in manifest["files_sha256"].items():
        if sha(folder / name) != expected:
            raise ValueError("Stage artifact changed: " + name)
    return read(folder / "summary.json")


def stage_directory(output, stage):
    folder = Path(output) / stage
    if folder.exists():
        raise ValueError("Existing stage will not be overwritten: " + stage)
    folder.mkdir()
    return folder


def label_rows(label, stream, *, owner=None):
    """Validate every paired physical branch and build both observable schemas."""
    keys, proposals = label["actual_action_keys"], label["proposals"]
    count, groups, futures = label["candidate_count"], label["groups"], label["futures_per_group"]
    if count != len(keys) or count > 4 or len(set(keys)) != count or len(proposals) != count:
        raise ValueError("Normal K4 candidate alignment/uniqueness failure")
    if groups not in (2, 4) or futures != 8 or label["horizon_ticks"] != 20 or label["regime"] != "stress":
        raise ValueError("Label common-future/horizon protocol differs")
    if label["failures"]:
        raise ValueError("Incomplete or failed paired label cannot enter training")
    base, physical = label["features_observable_only"], label["features_physical"]
    if len(base) != count or len(physical) != count:
        raise ValueError("Feature count differs from candidate count")
    for left, right in zip(base, physical):
        if set(left) != set(FULL_FEATURE_NAMES) or set(right) != set(PHYSICAL_FEATURE_NAMES):
            raise ValueError("Observable feature schema mismatch; hidden fields forbidden")
        if any(left[k] != right[k] for k in FULL_FEATURE_NAMES) or not np.isfinite(list(right.values())).all():
            raise ValueError("Base/physical features differ or are nonfinite")
    costs = np.asarray(label["paired_costs"], dtype=float)
    expected_shape = (groups, count, futures) if count else (groups, 0)
    if costs.shape != expected_shape or not np.isfinite(costs).all():
        raise ValueError("Incomplete finite paired cost tensor")
    expected = {(g, c, f) for g in range(groups) for c in range(count) for f in range(futures)}
    indices = [(b["group"], b["candidate"], b["future_index"]) for b in label["raw_branches"]]
    if len(indices) != len(expected) or set(indices) != expected:
        raise ValueError("Missing or duplicated paired branch")
    for branch, index in zip(label["raw_branches"], indices):
        components = branch["cost_components"]
        if branch["failed"] or set(components) != set(COST_WEIGHTS):
            raise ValueError("Shared physical cost or branch success mismatch")
        total = sum(COST_WEIGHTS[k] * value for k, value in components.items())
        if (not np.isfinite(total) or not np.isfinite(branch["total_cost"])
                or abs(total - costs[index]) > 1e-8 or abs(total - branch["total_cost"]) > 1e-8):
            raise ValueError("Label total differs from original physical components")
        tape = label["future_groups_offline_only"][index[0]]["tapes"][index[2]]
        if branch["future_sha256"] != digest(tape):
            raise ValueError("Candidate branches must share the same indexed future tape")
    if not count:
        return []
    reference = costs[:, 0, :].reshape(-1)
    return [{"stream": stream, "source_group": label["identity"], "owner": owner,
             "source_node": label["source_node"], "role": label["role"], "band": label["band"],
             "time": label["state"]["now"], "normal_ordinal": c, "is_baseline": c == 0,
             "actual_action_key": keys[c], "checkpoint_sha256": label["checkpoint_sha256"],
             "features23": base[c], "features31": physical[c],
             "cost_mean": float(costs[:, c, :].mean()),
             "delta_mean": float((costs[:, c, :].reshape(-1) - reference).mean()),
             "paired_deltas": (costs[:, c, :].reshape(-1) - reference).tolist(),
             "timed_delta": base[c]["timed_analytic_absolute"] - base[0]["timed_analytic_absolute"]}
            for c in range(count)]


def project_rows(rows, schema):
    if schema not in SCHEMAS:
        raise ValueError("Unknown feature schema")
    return [dict(r, features=r["features23" if schema == "paired23" else "features31"]) for r in rows]


def fit_model(r0_rows, held_out, schema, kind, seed, *, r1_rows=(), owner=None, config=None):
    streams = set(PROTOCOL["streams"])
    if held_out not in streams or seed not in SEEDS or kind not in KINDS or schema not in SCHEMAS:
        raise ValueError("Undeclared fold, schema, kind or seed")
    if any(r["stream"] not in streams or r.get("owner") is not None for r in r0_rows):
        raise ValueError("Invalid R0 source stream or recovery ownership")
    if any(r["stream"] == held_out or r["stream"] not in streams or r.get("owner") != owner for r in r1_rows):
        raise ValueError("R1 rows must belong to this model and its three training streams only")
    training = [r for r in r0_rows if r["stream"] != held_out] + list(r1_rows)
    if {r["stream"] for r in training} != streams - {held_out}:
        raise ValueError("Missing training stream in fold denominator")
    groups = {r["source_group"] for r in training}
    if groups & {r["source_group"] for r in r0_rows if r["stream"] == held_out}:
        raise ValueError("Checkpoint crosses the held-out stream boundary")
    rows = [dict(r, split="train") for r in project_rows(training, schema)]
    config = config or MLPConfig(epochs=400, learning_rate=.01, l2=.001, seed=seed)
    if config.seed != seed:
        raise ValueError("Optimizer seed differs from frozen identity")
    model = MLPValueModel.fit(rows, kind, config, feature_names=SCHEMAS[schema])
    matrix = np.asarray([[r["features"][name] for name in SCHEMAS[schema]] for r in rows])
    bounds = {name: {"minimum": float(matrix[:, i].min()), "maximum": float(matrix[:, i].max())}
              for i, name in enumerate(SCHEMAS[schema])}
    return model, bounds, {"held_out_stream": held_out, "schema": schema, "kind": kind, "seed": seed,
        "owner": owner, "training_streams": sorted(streams - {held_out}), "training_rows": len(rows),
        "r0_training_rows": len(rows) - len(r1_rows), "r1_training_rows": len(r1_rows),
        "training_checkpoints": sorted(groups), "training_rows_sha256": digest(rows)}


def noise_gate(labels):
    """Predeclared label precision diagnostic; not a learned-model selection."""
    details = []
    for label in labels:
        if label["groups"] != 4 or label["futures_per_group"] != 8:
            raise ValueError("Noise gate requires all four R0 groups with eight futures")
        if label["candidate_count"] < 2:
            continue
        costs = np.asarray(label["paired_costs"], dtype=float)
        small, full = costs[:, :, :2].mean(axis=2), costs.mean(axis=2)
        sets = lambda a: [np.flatnonzero(np.abs(v - v.min()) <= 1e-9).tolist() for v in a]
        left, right = sets(small), sets(full)
        regrets = [float(full[b, right[a][0]] - full[b].min()) for a in range(4) for b in range(4) if a != b]
        half, whole, last = full[:2].mean(axis=0), full.mean(axis=0), full[2:].mean(axis=0)
        half_set, whole_set = sets([half])[0], sets([whole])[0]
        details.append({"identity": label["identity"], "source_node": label["source_node"],
                        "role": label["role"], "candidate_count": label["candidate_count"],
                        "prefix2_optimal_sets": left, "full8_optimal_sets": right,
                        "agreements": [a == b for a, b in zip(left, right)], "cross_group_regrets": regrets,
                        "first_two_groups_optimal_set": half_set, "all_four_groups_optimal_set": whole_set,
                        "two_group_agreement": half_set == whole_set,
                        "last_two_groups_regret": float(last[half_set[0]] - last.min())})
    subsets = {}
    for name, subset in (("all", details), ("source_B", [d for d in details if d["source_node"] == "B"])):
        agreement = [v for d in subset for v in d["agreements"]]
        regrets = [v for d in subset for v in d["cross_group_regrets"]]
        rate, regret = (float(np.mean(agreement)) if agreement else None), (float(np.mean(regrets)) if regrets else None)
        half_rate = float(np.mean([d["two_group_agreement"] for d in subset])) if subset else None
        half_regret = float(np.mean([d["last_two_groups_regret"] for d in subset])) if subset else None
        subsets[name] = {"multi_candidate_states": len(subset), "agreement_denominator": len(agreement),
                         "agreement_rate": rate, "cross_group_comparisons": len(regrets), "mean_cross_group_regret": regret,
                         "two_group_comparisons": len(subset), "two_group_agreement_rate": half_rate,
                         "last_two_groups_mean_regret": half_regret,
                         "passes": rate is not None and rate >= .95 and regret <= .1 and half_rate >= .95 and half_regret <= .1}
    return {"rule": PROTOCOL["noise_gate"], "subsets": subsets, "details": details,
            "zero_single_candidate_states": sum(l["candidate_count"] < 2 for l in labels),
            "r1_groups": 2 if all(v["passes"] for v in subsets.values()) else 4,
            "selection_scope": "future simulation budget only; no model or seed selection"}


def fold_precision(labels, held_out):
    if held_out not in PROTOCOL["streams"]:
        raise ValueError("Unknown held-out stream")
    selected = [l for l in labels if l["identity"].split(":", 1)[0] != held_out]
    sources = {l["identity"].split(":", 1)[0] for l in selected}
    if sources != set(PROTOCOL["streams"]) - {held_out}:
        raise ValueError("Precision gate needs exactly the three training-source streams")
    return {"held_out_stream": held_out, "training_streams": sorted(sources),
            "observed_node_role_support": [list(pair) for pair in sorted({(l["source_node"], l["role"]) for l in selected})],
            **noise_gate(selected)}


def fold_groups(r0, held_out, requested=None):
    recommended = r0["r1_groups_by_fold"][held_out]
    if requested is None:
        return recommended
    if requested == 4 or requested == recommended:
        return requested
    raise ValueError("R1 groups undercut the training-fold precision gate")


def sample_groups(sample, groups, support):
    return groups if (sample["source_node"], sample["role"]) in {tuple(p) for p in support} else 4


class RecoverySelector:
    """Observable schema-consistent scoring; no engine or future tape reference."""
    def __init__(self, model, bounds, forecasts, *, schema):
        if tuple(model.feature_names) != SCHEMAS[schema] or set(bounds) != set(SCHEMAS[schema]):
            raise ValueError("Runtime model, schema and training bounds differ")
        self.model, self.bounds, self.forecasts, self.schema = model, bounds, tuple(forecasts), schema
        self.history = []

    def __call__(self, state, candidates):
        if not candidates:
            raise ValueError("No authorized candidates")
        published = tuple(f for f in self.forecasts if f.published_at <= state.now)
        if self.schema == "physical31":
            features = [physical_features(state, c, state.now + 20, published, route_mode="next_edge") for c in candidates]
        else:
            evaluator = TimedAnalyticEvaluator(state.now + 20, published)
            features = [evaluator.features(state, c) for c in candidates]
        scores = [self.model.score_features(f, features[0]) for f in features]
        if scores[0] != 0. or not np.isfinite(scores).all():
            raise AssertionError("Invalid score or nonzero reference")
        index = min(range(len(candidates)), key=lambda i: (scores[i], i))
        tray, bag = state.trays[candidates[0].tray_id], state.bags[candidates[0].bag_id]
        role = "arrival_at_destination" if tray.node == bag.destination else "origin" if tray.node == bag.origin else "continuation"
        self.history.append({"time": state.now, "state_sha256": digest(asdict(state)), "source_node": tray.node,
            "role": role, "bag_id": bag.bag_id, "features": features, "scores": scores, "chosen_index": index,
            "actual_action_keys": [actual_action_key(state, c, route_mode="next_edge") for c in candidates],
            "published_forecasts": [asdict(f) for f in published], "reference_zero": scores[0] == 0.,
            "outside_training_range": [[n for n in SCHEMAS[self.schema] if f[n] < self.bounds[n]["minimum"] - 1e-9
                                          or f[n] > self.bounds[n]["maximum"] + 1e-9] for f in features]})
        return candidates[index]


def selector_manifest(model, bounds, schema):
    return {"implementation": "RecoverySelector", "schema": schema, "kind": model.kind, "seed": model.config.seed,
            "model_sha256": digest(model.to_dict()), "training_bounds_sha256": digest(bounds)}


def scene_inputs(scene):
    return {"name": scene.name, "initial": asdict(scene.initial), "forecasts": [asdict(f) for f in scene.forecasts],
            "actual_tape_event_engine_only": [asdict(b) for b in scene.future_bags], "horizon": scene.horizon}


def quota():
    values = dict(PROTOCOL["quota"])
    for key in ("bands", "nodes", "roles"):
        values[key] = tuple(values[key])
    return RoleQuota(**values)


def cached_label(sample, nominal_future, *, groups, continuation_selector, selector_manifest, cache=True):
    """Memoize identical physical rollouts, never approximate states or tapes.

    The dictionary cannot escape this one checkpoint/continuation/horizon call.
    Group/future slots remain separate requested Monte Carlo records. Repeated
    tapes are not new independent operational data or extra physical runs.
    """
    if groups not in (2, 4):
        raise ValueError("R1 must use two or four groups of eight")
    wall, cpu = perf_counter(), process_time()
    checkpoint, pool = sample["checkpoint"], sample["pool"]
    state, horizon = checkpoint.state, checkpoint.state.now + 20
    if sample["continuation_contract"]["spec"]["planning_horizon"] != 20:
        raise ValueError("Recovery label horizon differs from collected control contract")
    future_groups, costs, branches, failures, memo = [], [], [], [], {}
    unique_calls = 0
    for group in range(groups):
        seed = int(digest([sample["identity"], "role_coverage_future", group])[:16], 16)
        futures = sampled_futures(nominal_future, state, count=8, seed=seed)
        future_groups.append({"seed": seed, "tapes": [[asdict(b) for b in tape] for tape in futures]})
        candidate_costs = []
        for index, candidate in enumerate(pool):
            values = []
            for future_index, tape in enumerate(futures):
                tape_sha = digest([asdict(b) for b in tape])
                key = (index, tape_sha)
                hit = cache and key in memo
                if hit:
                    outcome_record = deepcopy(memo[key])
                else:
                    unique_calls += 1
                    try:
                        result = branch_role_decision(checkpoint, candidate, tape, horizon,
                            continuation_selector=continuation_selector, selector_manifest=selector_manifest)
                        outcome_record = {"total_cost": result.total_cost, "cost_components": result.cost_components,
                            "completed": result.completed, "uncompleted": result.uncompleted_bag_ids,
                            "invariant_checks": result.invariant_checks, "failed": False}
                    except (ValueError, AssertionError) as error:
                        outcome_record = {"failed": True, "error": type(error).__name__, "reason": str(error)}
                    if cache:
                        memo[key] = deepcopy(outcome_record)
                branch = {"group": group, "candidate": index, "future_index": future_index,
                          "future_sha256": tape_sha, "cache_hit": hit, **outcome_record}
                values.append(branch.get("total_cost"))
                if branch["failed"]:
                    failures.append(branch)
                branches.append(branch)
            candidate_costs.append(values)
        costs.append(candidate_costs)
    return {"identity": sample["identity"], "regime": "stress", "horizon_ticks": 20,
        "groups": groups, "futures_per_group": 8, "candidate_count": len(pool),
        "checkpoint_sha256": sample["checkpoint_sha256"], "state": asdict(state),
        "source_node": sample["source_node"], "role": sample["role"], "band": sample["band"],
        "actual_action_keys": list(sample["normal_keys"]), "proposals": [asdict(p) for p in pool],
        "features_observable_only": sample["features"], "features_physical": sample["features_physical"],
        "future_groups_offline_only": future_groups, "paired_costs": costs, "raw_branches": branches,
        "failures": failures, "sampled_policy_sha": sample["policy_sha"], "continuation_override": selector_manifest,
        "source_continuation_contract": sample["continuation_contract"], "zero_candidate_preserved": not pool,
        "requested_branches": groups * 8 * len(pool), "actual_unique_branch_calls": unique_calls,
        "cache_reused_branches": sum(b["cache_hit"] for b in branches),
        "cache_scope": "this exact checkpoint, candidate index, full tape hash, fixed timed continuation and horizon only",
        "wall_seconds": perf_counter() - wall, "cpu_seconds": process_time() - cpu}


def collect_and_label(folder, scene, *, owner=None, model=None, bounds=None, groups=4, role_support=()):
    folder.mkdir(exist_ok=True)
    schema = "physical31"
    external = RecoverySelector(model, bounds, scene.forecasts, schema=schema) if model is not None else None
    manifest = selector_manifest(model, bounds, schema) if model is not None else None
    collection = collect_role_decisions(scene, replace(SPEC, routing="external") if model else SPEC, quota=quota(),
        route_selector=external, selector_manifest=manifest, source_group=owner or "R0_timed")
    # Replacement alters the dispatcher only; physical cursor, already accepted
    # routes, generator, FIFO and current independent slow trigger are retained.
    timed = PublishedRoutingSelector(SPEC, scene.forecasts)
    timed_manifest = {"implementation": "PublishedRoutingSelector", "kind": "timed", "spec": asdict(SPEC),
                      "implementation_sha256": collection.contract["continuation"]["implementation_sha256"]}
    attempt = len(list(folder.glob("collection_attempt_*.json")))
    save(folder / f"collection_attempt_{attempt:03d}.json", {"inputs": scene_inputs(scene), "metadata": collection.metadata,
        "contract": collection.contract, "opportunities": collection.opportunities,
        "episode_result": asdict(collection.episode_result)})
    rows, labels, records = [], [], []
    for ordinal, sample in enumerate(collection.samples):
        actual_groups = sample_groups(sample, groups, role_support)
        artifact = sample_artifact(sample)
        sample_path, label_path = folder / f"sample_{ordinal:02d}.json", folder / f"label_{ordinal:02d}.json"
        if sample_path.exists():
            previous = read(sample_path)
            if previous["checkpoint_sha256"] != sample["checkpoint_sha256"] or previous["normal_keys"] != list(sample["normal_keys"]):
                raise ValueError("Resumed collection differs from preserved exact checkpoint")
        else:
            save(sample_path, artifact)
        if label_path.exists():
            label = read(label_path)
            if (label["checkpoint_sha256"] != sample["checkpoint_sha256"] or label["groups"] != actual_groups
                    or label["continuation_override"] != json.loads(json.dumps(timed_manifest))):
                raise ValueError("Preserved label has a different checkpoint, budget or continuation")
        else:
            label = cached_label(sample, scene.future_bags, groups=actual_groups,
                                 continuation_selector=timed, selector_manifest=timed_manifest)
            save(label_path, label)
        rows.extend(label_rows(label, scene.name, owner=owner))
        labels.append(label)
        records.append({"identity": sample["identity"], "stream": scene.name, "owner": owner,
            "source_node": sample["source_node"], "role": sample["role"], "band": sample["band"],
            "candidate_count": len(sample["pool"]), "groups": actual_groups,
            "requested_branches": actual_groups * 8 * len(sample["pool"]),
            "actual_branches": label["actual_unique_branch_calls"], "cache_reused_branches": label["cache_reused_branches"],
            "failures": len(label["failures"]), "wall_seconds": label["wall_seconds"], "cpu_seconds": label["cpu_seconds"]})
        print(json.dumps({"stage": "R1" if model else "R0", **records[-1]}), flush=True)
    return rows, labels, {"stream": scene.name, "owner": owner, "collection": collection.metadata,
                          "collection_attempt_count": attempt + 1,
                          "all_collection_attempt_cpu_seconds": sum(read(p)["metadata"]["cpu_seconds"] for p in folder.glob("collection_attempt_*.json")),
                          "collection_cost": collection.episode_result.total_cost, "labels": records}


def fit_models(folder, r0_rows, *, r1_by_owner=None):
    models, bounds, folds, logs = {}, {}, {}, []
    r1 = r1_by_owner is not None
    for stream in PROTOCOL["streams"]:
        for schema in (("physical31",) if r1 else tuple(SCHEMAS)):
            for kind in KINDS:
                for seed in SEEDS:
                    name = model_name(stream, schema, kind, seed)
                    start, cpu = perf_counter(), process_time()
                    if r1 and name not in r1_by_owner:
                        raise ValueError("Missing recovery model collection denominator: " + name)
                    model, ranges, fold = fit_model(r0_rows, stream, schema, kind, seed,
                        r1_rows=r1_by_owner[name] if r1 else (), owner=name if r1 else None)
                    models[name], bounds[name], folds[name] = model.to_dict(), ranges, fold
                    logs.append({"name": name, **fold, "wall_seconds": perf_counter() - start,
                                 "cpu_seconds": process_time() - cpu, "training_metadata": model.training_metadata})
    save(folder / "frozen_models.json", models)
    save(folder / "folds_and_bounds.json", {"folds": folds, "bounds": bounds})
    save(folder / "fit_history.json", logs)
    return logs


def load_r0_labels(directory):
    directory = Path(directory)
    if not (directory / "manifest.json").is_file() or not (directory / "summary.json").is_file():
        raise ValueError("Complete frozen R0 labels are required before fitting")
    manifest, summary, protocol = read(directory / "manifest.json"), read(directory / "summary.json"), read(directory / "protocol.json")
    if summary.get("source_changed_during_run") is not False or summary.get("failures") != []:
        raise ValueError("R0 requires unchanged sources and zero failed branches")
    for name, expected in manifest.items():
        if sha(directory / name) != expected:
            raise ValueError("R0 label artifact checksum mismatch: " + name)
    code = Path(__file__).parent
    for name, expected in summary["source_sha256"].items():
        current = (code.parents[2] / "tests" / name) if name.startswith("test_") else code / name
        if sha(directory / "source_snapshot" / name) != expected or sha(current) != expected:
            raise ValueError("R0 label source snapshot/current dependency mismatch: " + name)
    normalized = lambda value: json.loads(json.dumps(value))
    if (protocol["spec"] != normalized(asdict(SPEC)) or protocol["quota"] != PROTOCOL["quota"]
            or not protocol["labels_enabled"] or protocol["stress_groups"] != 4
            or protocol["stress_futures_per_group"] != 8 or protocol["label_horizon_ticks"] != 20):
        raise ValueError("R0 label controller, quota, horizon or future protocol differs")
    if len(summary["episodes"]) != 4 or {e["scene"] for e in summary["episodes"]} != set(PROTOCOL["streams"]):
        raise ValueError("R0 must retain all four whole stream episodes")
    samples = summary["samples"]
    if len({s["identity"] for s in samples}) != len(samples) or summary["sample_count"] != len(samples):
        raise ValueError("R0 sample denominator or identity mismatch")
    rows, labels = [], []
    for record in samples:
        sample, label = read(directory / record["sample_file"]), read(directory / record["stress_file"])
        stream = record["identity"].split(":", 1)[0]
        if (stream not in PROTOCOL["streams"] or sample["identity"] != record["identity"] or label["identity"] != record["identity"]
                or sample["checkpoint_sha256"] != record["checkpoint_sha256"] or label["checkpoint_sha256"] != record["checkpoint_sha256"]
                or sample["state"] != label["state"] or sample["features"] != label["features_observable_only"]
                or sample["features_physical"] != label["features_physical"] or record["candidate_count"] != label["candidate_count"]
                or label["source_continuation_contract"]["spec"] != normalized(asdict(SPEC))
                or label["continuation_override"] is not None):
            raise ValueError("R0 checkpoint/features/continuation evidence mismatch")
        rows.extend(label_rows(label, stream))
        labels.append(label)
    if (summary["stress_branches"] != sum(len(l["raw_branches"]) for l in labels)
            or summary["stress_branches"] != sum(s["candidate_count"] * 32 for s in samples)):
        raise ValueError("R0 stress branch denominator mismatch")
    for scene in sustained_scenes():
        episode = read(directory / (scene.name + "_episode.json"))
        if (episode["initial"] != normalized(asdict(scene.initial))
                or episode["nominal_future_driver_only"] != normalized([asdict(b) for b in scene.future_bags])
                or episode["forecast_publications"] != normalized([asdict(f) for f in scene.forecasts])):
            raise ValueError("R0 label scene differs from current recovery/deployment source")
    return rows, labels, {"directory": str(directory.resolve()), "manifest_sha256": sha(directory / "manifest.json"),
        "files_sha256": manifest, "label_source_sha256": summary["source_sha256"], "summary": summary}


def check_r0_inputs(output):
    inputs = read(Path(output) / "r0/input_manifest.json")
    directory = Path(inputs["directory"])
    if sha(directory / "manifest.json") != inputs["manifest_sha256"]:
        raise ValueError("Original R0 input manifest changed")
    for name, expected in inputs["files_sha256"].items():
        if sha(directory / name) != expected:
            raise ValueError("Original R0 input artifact changed: " + name)


def run_r0(output, labels):
    check_output_directory(output)
    rows, label_values, inputs = load_r0_labels(labels)
    output = create_output_directory(output)
    (output / "source_snapshot").mkdir()
    hashes = {}
    for name in SOURCES:
        data = (Path(__file__).parent / name).read_bytes()
        (output / "source_snapshot" / name).write_bytes(data)
        hashes[name] = sha256(data).hexdigest()
    save(output / "protocol.json", {**PROTOCOL, "source_sha256": hashes})
    folder = stage_directory(output, "r0")
    save(folder / "runtime_environment.json", {"python": sys.version, "numpy": np.__version__, "platform": platform.platform(),
         "thread_environment": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}})
    save(folder / "input_manifest.json", inputs)
    save(folder / "rows.json", rows)
    gates = {stream: fold_precision(label_values, stream) for stream in PROTOCOL["streams"]}
    save(folder / "noise.strict.json", {"folds": gates, "pooled_descriptive_only": noise_gate(label_values),
                                      "budget_owner": "each model's own three training streams; no pooled gate"})
    logs = fit_models(folder, rows)
    check_r0_inputs(output)
    return freeze_stage(output, "r0", {"stage": "r0", "fits": len(logs), "collection_episodes": 0,
        "reused_original_r0_collection_episodes": 4, "candidate_rows": len(rows), "checkpoints": len(label_values),
        "requested_branches": 0, "actual_branches": 0, "reused_original_r0_branches": inputs["summary"]["stress_branches"],
        "cache_reused_branches": 0,
        "failures": [], "r1_groups_by_fold": {s: gate["r1_groups"] for s, gate in gates.items()},
        "r1_role_support_by_fold": {s: gate["observed_node_role_support"] for s, gate in gates.items()},
        "held_out_assessment_or_deployment_started": False, "next_stage": "explicit r1 command only"})


def recovery_owners():
    return [model_name(stream, "physical31", kind, seed) for stream in PROTOCOL["streams"] for kind in KINDS for seed in SEEDS]


def run_r1_unit(output, *, groups=None, owner):
    """One process owns one model's three training-source episodes.

    Separate processes may run distinct owners. All child-process CPU is in
    their unit artifacts; the merge adds those values instead of presenting
    coordinator CPU as total work. Completed unit files are immutable.
    """
    output = Path(output)
    r0 = check_stage(output, "r0")
    check_r0_inputs(output)
    if owner not in recovery_owners():
        raise ValueError("Undeclared recovery owner")
    held_out = owner.split("__", 1)[0]
    groups = fold_groups(r0, held_out, groups)
    support = r0["r1_role_support_by_fold"][held_out]
    stage = "r1_units/" + owner
    if (output / stage / "stage_manifest.json").exists():
        existing = check_stage(output, stage)
        if existing["groups"] != groups:
            raise ValueError("Cannot reuse unit with a different future budget")
        return existing
    (output / "r1_units").mkdir(exist_ok=True)
    folder = output / stage
    folder.mkdir(exist_ok=True)
    unit_protocol = {"owner": owner, "groups": groups, "r0_manifest_sha256": sha(output / "r0/stage_manifest.json"),
                     "protocol_sha256": sha(output / "protocol.json"), "collection_episodes": 3,
                     "continuation": "fixed timed", "cache": PROTOCOL["cache"], "observed_node_role_support": support}
    if (folder / "unit_protocol.json").exists():
        if read(folder / "unit_protocol.json") != unit_protocol:
            raise ValueError("Cannot resume unit with changed sources, model owner or future budget")
    else:
        save(folder / "unit_protocol.json", unit_protocol)
    models, meta = read(output / "r0/frozen_models.json"), read(output / "r0/folds_and_bounds.json")
    model = MLPValueModel.from_dict(models[owner])
    held_out = meta["folds"][owner]["held_out_stream"]
    rows, episodes = [], []
    wall, cpu = perf_counter(), process_time()
    for scene in sustained_scenes():
        if scene.name == held_out:
            continue
        current_rows, _, record = collect_and_label(folder / scene.name, scene, owner=owner,
            model=model, bounds=meta["bounds"][owner], groups=groups, role_support=support)
        rows.extend(current_rows)
        episodes.append(record)
    if {r["stream"] for r in episodes} != set(PROTOCOL["streams"]) - {held_out} or len(episodes) != 3:
        raise ValueError("Recovery episode denominator or training-stream isolation failure")
    if (folder / "rows.json").exists():
        if read(folder / "rows.json") != rows:
            raise ValueError("Existing recovered rows differ on resume")
    else:
        save(folder / "rows.json", rows)
    return freeze_stage(output, stage, {"owner": owner, "held_out_stream": held_out, "groups": groups,
        "episodes": episodes, "collection_episodes": 3, "requested_branches": sum(l["requested_branches"] for e in episodes for l in e["labels"]),
        "actual_branches": sum(l["actual_branches"] for e in episodes for l in e["labels"]),
        "cache_reused_branches": sum(l["cache_reused_branches"] for e in episodes for l in e["labels"]),
        "wall_seconds_this_invocation": perf_counter() - wall, "cpu_seconds_this_invocation": process_time() - cpu,
        "recorded_collection_and_label_cpu_seconds": sum(e["all_collection_attempt_cpu_seconds"]
            + sum(l["cpu_seconds"] for l in e["labels"]) for e in episodes), "failures": []})


def run_r1(output, *, groups=None, merge_only=False):
    output = Path(output)
    r0 = check_stage(output, "r0")
    check_r0_inputs(output)
    if (output / "r1").exists():
        raise ValueError("Existing stage will not be overwritten: r1")
    by_owner, episodes, units = {}, [], []
    for owner in recovery_owners():
        unit = check_stage(output, "r1_units/" + owner) if merge_only else run_r1_unit(output, groups=groups, owner=owner)
        expected_groups = fold_groups(r0, owner.split("__", 1)[0], groups)
        if unit["groups"] != expected_groups or unit["owner"] != owner or unit["failures"]:
            raise ValueError("Wrong-budget, wrong-owner or failed recovery unit")
        units.append(unit)
        by_owner[owner] = read(output / "r1_units" / owner / "rows.json")
        episodes.extend(unit["episodes"])
    folder = stage_directory(output, "r1")
    save(folder / "stage_protocol.json", {"groups_override": groups, "r0_manifest_sha256": sha(output / "r0/stage_manifest.json"),
         "models": 24, "collection_episodes": 72, "cache": PROTOCOL["cache"], "continuation": "fixed timed",
         "unit_manifest_sha256": {o: sha(output / "r1_units" / o / "stage_manifest.json") for o in recovery_owners()}})
    r0_rows = read(output / "r0/rows.json")
    save(folder / "rows_by_owner.json", by_owner)
    logs = fit_models(folder, r0_rows, r1_by_owner=by_owner)
    check_stage(output, "r0")
    return freeze_stage(output, "r1", {"stage": "r1", "fits": len(logs), "collection_episodes": len(episodes),
        "episodes": episodes, "candidate_rows": sum(len(v) for v in by_owner.values()),
        "checkpoints": sum(len(e["labels"]) for e in episodes),
        "requested_branches": sum(l["requested_branches"] for e in episodes for l in e["labels"]),
        "actual_branches": sum(l["actual_branches"] for e in episodes for l in e["labels"]),
        "cache_reused_branches": sum(u["cache_reused_branches"] for u in units),
        "recorded_collection_and_label_cpu_seconds_including_worker_processes": sum(u["recorded_collection_and_label_cpu_seconds"] for u in units),
        "worker_completion_invocations_process_cpu_seconds": sum(u["cpu_seconds_this_invocation"] for u in units),
        "worker_completion_invocations_wall_seconds_sum_not_makespan": sum(u["wall_seconds_this_invocation"] for u in units),
        "fit_cpu_seconds": sum(log["cpu_seconds"] for log in logs),
        "failures": [], "held_out_assessment_or_deployment_started": False})


def assess(rows, model=None, *, schema="paired23", kind="timed"):
    projected = project_rows(rows, schema)
    decisions = []
    for group in sorted({r["source_group"] for r in projected}):
        candidates = sorted((r for r in projected if r["source_group"] == group), key=lambda r: r["normal_ordinal"])
        scores = ([model.score_features(r["features"], candidates[0]["features"]) for r in candidates] if model else
                  [r["timed_delta"] if kind == "timed" else r["normal_ordinal"] for r in candidates])
        chosen = min(range(len(scores)), key=lambda i: (scores[i], i))
        if scores[0] != 0.:
            raise ValueError("Nonzero reference in paired assessment")
        decisions.append({"source_group": group, "source_node": candidates[0]["source_node"], "role": candidates[0]["role"],
            "candidate_count": len(candidates), "chosen_key": candidates[chosen]["actual_action_key"], "scores": scores,
            "chosen_cost_mean": candidates[chosen]["cost_mean"], "chosen_delta": candidates[chosen]["delta_mean"],
            "regret": candidates[chosen]["cost_mean"] - min(r["cost_mean"] for r in candidates)})
    return {"checkpoint_count": len(decisions), "candidate_rows": len(rows), "decisions": decisions,
            "mean_regret": float(np.mean([d["regret"] for d in decisions])) if decisions else None}


def deployment(scene, *, model=None, bounds=None, schema=None, kind="timed"):
    wall, cpu = perf_counter(), process_time()
    if model is None:
        engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, replace(SPEC, routing=kind))
    else:
        engine = build_engine(scene.initial, scene.forecasts, scene.future_bags, replace(SPEC, routing="external"),
            route_selector=RecoverySelector(model, bounds, scene.forecasts, schema=schema),
            selector_manifest=selector_manifest(model, bounds, schema))
    boundaries = []
    while engine.state.now < scene.horizon:
        state = engine.observe()
        boundaries.append({"time": state.now, "state_sha256": digest(asdict(state)), "completed": len(state.completed),
                           "visible_bags": sorted(state.bags)})
        engine.advance(state.now + 1)
    result = engine.result()
    bags = {**scene.initial.bags, **{b.bag_id: b for b in scene.future_bags}}
    history = engine.route_selector.selector.history if model else []
    metrics = {"status": "completed_run", "total_cost": result.total_cost, "cost_components": result.cost_components,
        "scheduled_bags": len(bags), "completed": len(result.completed), "uncompleted": list(result.uncompleted_bag_ids),
        "on_time": sum(k in result.completed and result.completed[k] <= b.deadline for k, b in bags.items()),
        "selector_calls": len(engine.route_selector.history), "candidate_feature_vectors": sum(len(h["features"]) for h in history),
        "out_of_range_vectors": sum(bool(v) for h in history for v in h["outside_training_range"]),
        "source_node_calls": dict(Counter(h["source_node"] for h in history)),
        "role_calls": dict(Counter(h["role"] for h in history)), "wall_seconds": perf_counter() - wall,
        "cpu_seconds": process_time() - cpu}
    return {"metrics": metrics, "control_contract": engine.control_contract, "result": asdict(result), "boundaries": boundaries,
            "route_history": engine.route_selector.history, "learned_feature_history": history,
            "slow_history": engine.slow_controller.history, "slow_trigger_times": engine.slow_controller.trigger_times}


def deployment_scenes(scene):
    seed = int(digest([scene.name, "role_recovery_deployment_v1"])[:16], 16)
    futures = sampled_futures(scene.future_bags, scene.initial, count=8, seed=seed)
    return [("nominal", scene)] + [(f"stress_{i}", replace(scene, future_bags=tuple(tape))) for i, tape in enumerate(futures)]


def run_evaluation(output):
    output = Path(output)
    check_stage(output, "r0")
    check_stage(output, "r1")
    check_r0_inputs(output)
    folder = stage_directory(output, "evaluation")
    save(folder / "stage_protocol.json", {"r0_manifest_sha256": sha(output / "r0/stage_manifest.json"),
         "r1_manifest_sha256": sha(output / "r1/stage_manifest.json"), "all_72_models_frozen_before_evaluation": True})
    r0_rows = read(output / "r0/rows.json")
    r1_rows = read(output / "r1/rows_by_owner.json")
    models, metadata = {}, {}
    for stage in ("r0", "r1"):
        models[stage] = {n: MLPValueModel.from_dict(m) for n, m in read(output / stage / "frozen_models.json").items()}
        metadata[stage] = read(output / stage / "folds_and_bounds.json")
    assessments, recovery_before_after = {}, {}
    for scene in sustained_scenes():
        held = [r for r in r0_rows if r["stream"] == scene.name]
        assessments[scene.name] = {k: assess(held, kind=k) for k in ("baseline", "timed")}
        for stage in ("r0", "r1"):
            for name, model in models[stage].items():
                fold = metadata[stage]["folds"][name]
                if fold["held_out_stream"] == scene.name:
                    assessments[scene.name][stage + "__" + name] = assess(held, model, schema=fold["schema"])
                if stage == "r1" and fold["held_out_stream"] == scene.name:
                    recovery_before_after[name] = {"scope": "same training-source recovered checkpoints, in-sample after refit",
                        "before": assess(r1_rows[name], models["r0"][name], schema="physical31"),
                        "after": assess(r1_rows[name], model, schema="physical31")}
    save(folder / "held_out_checkpoints.json", assessments)
    save(folder / "training_source_recovery_before_after.json", recovery_before_after)
    records = []
    for base_scene in sustained_scenes():
        for realization, scene in deployment_scenes(base_scene):
            scene_folder = folder / (scene.name + "__" + realization)
            scene_folder.mkdir()
            save(scene_folder / "inputs.json", scene_inputs(scene))
            options = [("timed", None, None, None), ("baseline", None, None, None)]
            for stage in ("r0", "r1"):
                for name, model in models[stage].items():
                    fold = metadata[stage]["folds"][name]
                    if fold["held_out_stream"] == scene.name:
                        options.append((stage + "__" + name.split("__", 1)[1], model, metadata[stage]["bounds"][name], fold["schema"]))
            for name, model, bounds, schema in options:
                start, cpu = perf_counter(), process_time()
                try:
                    result = deployment(scene, model=model, bounds=bounds, schema=schema, kind=name)
                except Exception as error:
                    result = {"metrics": {"status": "failed_run", "total_cost": None, "completed": None,
                        "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags), "wall_seconds": perf_counter() - start,
                        "cpu_seconds": process_time() - cpu, "failure": {"type": type(error).__name__, "reason": str(error)}}}
                result["metrics"].update(stream=scene.name, realization=realization, policy=name)
                records.append(result["metrics"])
                save(scene_folder / (name + ".json"), result)
                print(json.dumps(result["metrics"]), flush=True)
    if len(records) != PROTOCOL["deployment"]["episodes"]:
        raise ValueError("Missing planned deployment episode denominator")
    check_stage(output, "r0")
    check_stage(output, "r1")
    return freeze_stage(output, "evaluation", {"stage": "evaluation", "fits": 72, "deployment_runs": len(records),
        "scheduled_bag_denominator": sum(r["scheduled_bags"] for r in records),
        "completed_bags": sum(r["completed"] or 0 for r in records),
        "failures": [r for r in records if r["status"] != "completed_run"], "deployment_metrics": records,
        "limits": PROTOCOL["limits"], "model_or_seed_selection": False, "fresh_confirmation": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--stage", choices=("r0", "r1", "r1-unit", "r1-merge", "evaluation"), required=True)
    parser.add_argument("--labels", help="Complete run_role_coverage output; required for R0 only")
    parser.add_argument("--r1-groups", type=int, choices=(2, 4))
    parser.add_argument("--owner", help="Exact physical31 model key, for one independently resumable R1 unit")
    args = parser.parse_args()
    if args.stage == "r0" and args.labels is None:
        parser.error("R0 requires --labels pointing to complete frozen role coverage output")
    if args.stage == "r1-unit" and args.owner is None:
        parser.error("R1 unit requires --owner")
    result = (run_r0(args.output, args.labels) if args.stage == "r0"
              else run_r1_unit(args.output, groups=args.r1_groups, owner=args.owner) if args.stage == "r1-unit"
              else run_r1(args.output, groups=args.r1_groups, merge_only=args.stage == "r1-merge") if args.stage.startswith("r1")
              else run_evaluation(args.output))
    print(json.dumps({k: v for k, v in result.items() if k not in {"episodes", "deployment_metrics"}}), flush=True)
    return int(bool(result["failures"]))


if __name__ == "__main__":
    raise SystemExit(main())
