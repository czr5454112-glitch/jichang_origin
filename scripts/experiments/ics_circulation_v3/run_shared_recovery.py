"""Same-data direct/residual supplement using frozen training-owner row unions.

No collection, labels, model/seed selection or new scenario is introduced. For
each held-out stream, all six owners' already collected training-source rows
are concatenated with its R0 training rows, retaining every original owner and
source group. Both paired objectives receive this exact same ordered corpus.
All 24 models freeze before any assessment or the 288 declared deployments.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from time import perf_counter, process_time
import json
import os
import platform
import sys

import numpy as np

from .experiment_protocol import check_output_directory, create_output_directory
from .nonlinear_learning import MLPConfig, MLPValueModel, PHYSICAL_FEATURE_NAMES
from . import run_paired_recovery as recovery


KINDS, SEEDS, SPEC = recovery.KINDS, recovery.SEEDS, recovery.SPEC
STREAMS = tuple(recovery.PROTOCOL["streams"])
SOURCES = tuple(dict.fromkeys(("run_shared_recovery.py", *recovery.SOURCES)))
PROTOCOL = {
    "schema": "ics_v3_shared_recovery_union_v1", "scope": "same-data objective comparison on reused synthetic development streams",
    "streams": STREAMS, "spec": asdict(SPEC), "schema_name": "physical31", "feature_names": PHYSICAL_FEATURE_NAMES,
    "kinds": KINDS, "seeds": SEEDS, "fits": 24, "architecture": "32_tanh_1057_parameters",
    "optimizer": {"epochs": 400, "learning_rate": .01, "l2": .001},
    "training": "Per held-out stream: R0 rows from its three training streams plus every row from all six physical31 collection owners for that fold; ordered concatenation by declared kind/seed then original row order.",
    "ownership": "Keep original owner and source_group on every row; validate all six complete owners and all 24 frozen units before fitting. Do not call original single-owner fit_model or rewrite owner identities.",
    "duplicate_policy": "No approximate or exact deduplication across owners; multiplicity and provenance are explicit, same for both objectives.",
    "normalization": "Fold training corpus only; identical inputs/bounds and ordered training row SHA across six objectives/seeds in each fold.",
    "freeze": "All 24 models and fit input hashes frozen before any held-out assessment or deployment.",
    "assessment": "R0 held-out checkpoint rows only; all kind/seed results retained; no model, seed or hyperparameter selection.",
    "deployment": {"realizations_per_stream": 9, "nominal_per_stream": 1, "stress_per_stream": 8,
                   "learned_episodes": 216, "control_episodes": 72, "total_episodes": 288,
                   "controls": ["baseline", "timed"], "stress_seed_rule": recovery.PROTOCOL["stress_tapes"]["seed"]},
    "new_labels": 0, "fresh_confirmation": False,
    "limits": ["Four reused constructed streams and their common stress family are development evidence, not independent field days.",
        "Owners collected different trajectories; the entire same union is now used for both objectives. The previous own-policy recovery experiment remains separate.",
        "Row weighting is unchanged concatenation; owners with more sampled candidate rows contribute more weight. No outcome-dependent balancing or filtering is applied.",
        "All row provenance is retained even when physical states or features repeat; duplicated trajectories do not become independent samples.",
        "Label targets continue the fixed timed policy, not either deployed learned policy.",
        "All elapsed times are descriptive on a shared machine; model quality does not use a timing cutoff."],
}


def fold_owners(held_out):
    if held_out not in STREAMS:
        raise ValueError("undeclared held-out stream")
    return tuple(recovery.model_name(held_out, "physical31", kind, seed) for kind in KINDS for seed in SEEDS)


def shared_training_rows(r0_rows, fold_rows_by_owner, held_out):
    """Validate a real six-owner corpus; ownership is never relabeled."""
    owners = fold_owners(held_out)
    if set(fold_rows_by_owner) != set(owners):
        raise ValueError("need exactly all six declared training owners for this fold")
    if any(r.get("owner") is not None or r.get("stream") not in STREAMS for r in r0_rows):
        raise ValueError("R0 rows contain invalid stream or recovery owner")
    training_streams = set(STREAMS) - {held_out}
    base = [deepcopy(r) for r in r0_rows if r["stream"] != held_out]
    if {r["stream"] for r in base} != training_streams:
        raise ValueError("R0 fold must retain all three training streams")
    rows, owners_per_group = list(base), {}
    for owner in owners:
        for original in fold_rows_by_owner[owner]:
            if original.get("owner") != owner or original.get("stream") not in training_streams:
                raise ValueError("recovered row has wrong owner or held-out/foreign stream")
            group = original.get("source_group")
            if not isinstance(group, str) or not group:
                raise ValueError("recovery row lacks original checkpoint group identity")
            if group in owners_per_group and owners_per_group[group] != owner:
                raise ValueError("source group reused by distinct owners; cannot merge their baselines")
            owners_per_group[group] = owner
            rows.append(deepcopy(original))
    base_groups = {r["source_group"] for r in base}
    held_groups = {r["source_group"] for r in r0_rows if r["stream"] == held_out}
    if base_groups & set(owners_per_group) or ({r["source_group"] for r in rows} & held_groups):
        raise ValueError("checkpoint identity crosses collection or held-out boundary")
    # Exactly one baseline and unique ordinal per original candidate group.
    grouped = {}
    for row in rows:
        grouped.setdefault(row["source_group"], []).append(row)
    for group in grouped.values():
        ordinals = [r["normal_ordinal"] for r in group]
        if (len(set(ordinals)) != len(ordinals) or sorted(ordinals) != list(range(len(group)))
                or sum(r["is_baseline"] for r in group) != 1
                or not next(r for r in group if r["normal_ordinal"] == 0)["is_baseline"]):
            raise ValueError("candidate group lost or duplicated its baseline/ordinal")
    return rows


def fit_shared_model(training, held_out, kind, seed, *, config=None):
    """A dedicated union fit, not an exception to the old single-owner check."""
    if held_out not in STREAMS or kind not in KINDS or seed not in SEEDS:
        raise ValueError("undeclared shared model identity")
    if any(r["stream"] == held_out or r["stream"] not in STREAMS for r in training):
        raise ValueError("held-out/foreign data cannot enter shared fitting")
    allowed = set(fold_owners(held_out))
    if any(r.get("owner") is not None and r["owner"] not in allowed for r in training):
        raise ValueError("shared fit row belongs to another fold owner")
    projected = [dict(r, features=r["features31"], split="train") for r in deepcopy(training)]
    config = config or MLPConfig(epochs=400, learning_rate=.01, l2=.001, seed=seed)
    if config.seed != seed:
        raise ValueError("optimizer seed differs from declared identity")
    model = MLPValueModel.fit(projected, kind, config, feature_names=PHYSICAL_FEATURE_NAMES)
    matrix = np.asarray([[r["features"][f] for f in PHYSICAL_FEATURE_NAMES] for r in projected])
    bounds = {f: {"minimum": float(matrix[:, i].min()), "maximum": float(matrix[:, i].max())}
              for i, f in enumerate(PHYSICAL_FEATURE_NAMES)}
    return model, bounds, {"held_out_stream": held_out, "schema": "physical31", "kind": kind, "seed": seed,
        "training_streams": sorted(set(STREAMS) - {held_out}), "training_owner_set": list(fold_owners(held_out)),
        "training_rows": len(training), "r0_training_rows": sum(r.get("owner") is None for r in training),
        "recovered_rows": sum(r.get("owner") is not None for r in training),
        "rows_by_original_owner": dict(Counter(r.get("owner") or "R0" for r in training)),
        "training_checkpoints": sorted({r["source_group"] for r in training}),
        "training_rows_sha256": recovery.digest(projected), "training_bounds_sha256": recovery.digest(bounds)}


def load_frozen_inputs(master):
    master = Path(master)
    r0 = recovery.check_stage(master, "r0")
    r1 = recovery.check_stage(master, "r1")
    recovery.check_r0_inputs(master)
    if r0["fits"] != 48 or r1["fits"] != 24 or r1["collection_episodes"] != 72 or r0["failures"] or r1["failures"]:
        raise ValueError("all original R0/R1 fits and 72 collection episodes must be complete")
    r0_rows = recovery.read(master / "r0/rows.json")
    by_owner = recovery.read(master / "r1/rows_by_owner.json")
    expected = set(recovery.recovery_owners())
    if set(by_owner) != expected:
        raise ValueError("all 24 recovered owner row sets are required")
    declared_manifests = recovery.read(master / "r1/stage_protocol.json")["unit_manifest_sha256"]
    if set(declared_manifests) != expected:
        raise ValueError("merged R1 stage lacks all owner manifests")
    units = {}
    for owner in recovery.recovery_owners():
        held_out = owner.split("__", 1)[0]
        unit = recovery.check_stage(master, "r1_units/" + owner)
        rows_path = master / "r1_units" / owner / "rows.json"
        if (unit["owner"] != owner or unit["held_out_stream"] != held_out or unit["failures"]
                or unit["collection_episodes"] != 3 or len(unit["episodes"]) != 3
                or {e["stream"] for e in unit["episodes"]} != set(STREAMS) - {held_out}
                or recovery.read(rows_path) != by_owner[owner]):
            raise ValueError("incomplete, relabeled or cross-fold owner corpus: " + owner)
        manifest_sha = recovery.sha(rows_path.with_name("stage_manifest.json"))
        if declared_manifests[owner] != manifest_sha:
            raise ValueError("merged R1 owner checksum differs")
        units[owner] = {"manifest_sha256": manifest_sha, "rows_sha256": recovery.sha(rows_path),
                        "row_count": len(by_owner[owner]), "held_out_stream": held_out,
                        "training_streams": sorted(e["stream"] for e in unit["episodes"])}
    # These immutable references include every original raw label via unit
    # manifests; no evaluation result is needed or read to choose this corpus.
    files = ("protocol.json", "r0/stage_manifest.json", "r1/stage_manifest.json", "r0/rows.json",
             "r1/rows_by_owner.json", "r0/frozen_models.json", "r1/frozen_models.json")
    inputs = {"master_directory": str(master.resolve()), "files_sha256": {p: recovery.sha(master / p) for p in files},
              "unit_manifests": units, "original_r0_fits": 48, "original_r1_fits": 24,
              "collection_episodes": 72, "new_labels": 0, "held_out_results_read_for_selection": False}
    for stream in STREAMS:
        shared_training_rows(r0_rows, {o: by_owner[o] for o in fold_owners(stream)}, stream)
    return r0_rows, by_owner, inputs


def source_hashes():
    return {name: recovery.sha(Path(__file__).parent / name) for name in SOURCES}


def validate_shared(output):
    output = Path(output)
    protocol = recovery.read(output / "protocol.json")
    normalized = json.loads(json.dumps(PROTOCOL))
    if {k: v for k, v in protocol.items() if k != "source_sha256"} != normalized:
        raise ValueError("shared protocol changed")
    if protocol["source_sha256"] != source_hashes():
        raise ValueError("shared dependency sources changed")
    for name, expected in protocol["source_sha256"].items():
        if recovery.sha(output / "source_snapshot" / name) != expected:
            raise ValueError("shared source snapshot changed")
    return protocol


def freeze(output, stage, summary):
    validate_shared(output)
    folder = Path(output) / stage
    recovery.save(folder / "summary.json", summary)
    recovery.save(folder / "stage_manifest.json", {"stage": stage, "source_changed_during_run": False,
        "protocol_sha256": recovery.sha(Path(output) / "protocol.json"),
        "input_manifest_sha256": recovery.sha(Path(output) / "input_manifest.json"),
        "files_sha256": {p.relative_to(folder).as_posix(): recovery.sha(p) for p in sorted(folder.rglob("*")) if p.is_file()}})
    return summary


def check_shared_stage(output, stage):
    validate_shared(output)
    output = Path(output)
    folder = output / stage
    if not (folder / "stage_manifest.json").is_file():
        raise ValueError("shared stage is incomplete: " + stage)
    manifest = recovery.read(folder / "stage_manifest.json")
    if (manifest["source_changed_during_run"] is not False or manifest["protocol_sha256"] != recovery.sha(output / "protocol.json")
            or manifest["input_manifest_sha256"] != recovery.sha(output / "input_manifest.json")):
        raise ValueError("shared stage protocol/input changed")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(manifest["files_sha256"]) | {"stage_manifest.json"}:
        raise ValueError("shared stage artifact set changed")
    if any(recovery.sha(folder / name) != expected for name, expected in manifest["files_sha256"].items()):
        raise ValueError("shared stage artifact checksum changed")
    return recovery.read(folder / "summary.json")


def run_fit(output, master):
    check_output_directory(output)
    r0_rows, by_owner, inputs = load_frozen_inputs(master)
    output = create_output_directory(output)
    hashes = source_hashes()
    (output / "source_snapshot").mkdir()
    for name in SOURCES:
        (output / "source_snapshot" / name).write_bytes((Path(__file__).parent / name).read_bytes())
    recovery.save(output / "protocol.json", {**PROTOCOL, "source_sha256": hashes})
    recovery.save(output / "input_manifest.json", inputs)
    folder = output / "fit"
    folder.mkdir()
    recovery.save(folder / "runtime_environment.json", {"python": sys.version, "numpy": np.__version__,
        "platform": platform.platform(), "threads": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")}})
    models, folds, bounds, logs, corpora = {}, {}, {}, [], {}
    for stream in STREAMS:
        training = shared_training_rows(r0_rows, {o: by_owner[o] for o in fold_owners(stream)}, stream)
        corpora[stream] = training
        for kind in KINDS:
            for seed in SEEDS:
                name = recovery.model_name(stream, "physical31", kind, seed)
                wall, cpu = perf_counter(), process_time()
                model, ranges, fold = fit_shared_model(training, stream, kind, seed)
                models[name], folds[name], bounds[name] = model.to_dict(), fold, ranges
                logs.append({"name": name, **fold, "wall_seconds": perf_counter() - wall,
                             "cpu_seconds": process_time() - cpu, "training_metadata": model.training_metadata})
                print(json.dumps({"stage": "shared_fit", "model": name, "training_rows": len(training)}, ensure_ascii=False), flush=True)
        names = fold_owners(stream)
        if len({folds[n]["training_rows_sha256"] for n in names}) != 1 or len({folds[n]["training_bounds_sha256"] for n in names}) != 1:
            raise ValueError("paired objectives/seeds did not receive identical training data and normalization")
    recovery.save(folder / "training_rows_by_fold.json", corpora)
    recovery.save(folder / "frozen_models.json", models)
    recovery.save(folder / "folds_and_bounds.json", {"folds": folds, "bounds": bounds})
    recovery.save(folder / "fit_history.json", logs)
    _, _, checked_inputs = load_frozen_inputs(master)
    if checked_inputs != inputs:
        raise ValueError("input corpus changed while fitting")
    return freeze(output, "fit", {"fits": len(models), "new_labels": 0, "same_data_across_objectives_and_seeds": True,
        "per_fold_training_rows": {s: len(v) for s, v in corpora.items()}, "row_owners_preserved": True,
        "all_24_models_frozen_before_held_out_assessment": True, "held_out_evaluation_started": False,
        "fit_cpu_seconds": sum(r["cpu_seconds"] for r in logs), "fit_wall_seconds_sum": sum(r["wall_seconds"] for r in logs), "failures": []})


def run_evaluation(output):
    output = Path(output)
    fitted = check_shared_stage(output, "fit")
    if fitted["fits"] != 24 or fitted["failures"]:
        raise ValueError("all 24 shared models must be frozen before evaluation")
    inputs = recovery.read(output / "input_manifest.json")
    r0_rows, _, checked = load_frozen_inputs(inputs["master_directory"])
    if checked != inputs:
        raise ValueError("original training inputs changed after fitting")
    folder = output / "evaluation"
    if folder.exists():
        raise ValueError("existing shared evaluation will not be overwritten")
    folder.mkdir()
    model_path = output / "fit/frozen_models.json"
    frozen_model_sha = recovery.sha(model_path)
    models = {n: MLPValueModel.from_dict(m) for n, m in recovery.read(model_path).items()}
    metadata = recovery.read(output / "fit/folds_and_bounds.json")
    if set(models) != set(recovery.recovery_owners()):
        raise ValueError("shared frozen model denominator differs")
    recovery.save(folder / "stage_protocol.json", {"fit_manifest_sha256": recovery.sha(output / "fit/stage_manifest.json"),
        "frozen_model_sha256": frozen_model_sha, "all_24_models_frozen_before_evaluation": True,
        "planned_episodes": 288, "new_labels": 0})
    assessments, records = {}, []
    for scene in recovery.sustained_scenes():
        held = [r for r in r0_rows if r["stream"] == scene.name]
        assessments[scene.name] = {kind: recovery.assess(held, kind=kind) for kind in ("baseline", "timed")}
        for name in fold_owners(scene.name):
            assessments[scene.name]["shared__" + name] = recovery.assess(held, models[name], schema="physical31")
    recovery.save(folder / "held_out_checkpoints.json", assessments)
    for base_scene in recovery.sustained_scenes():
        for realization, scene in recovery.deployment_scenes(base_scene):
            local = folder / (scene.name + "__" + realization)
            local.mkdir()
            scene_input = recovery.scene_inputs(scene)
            input_sha = recovery.digest(scene_input)
            recovery.save(local / "inputs.json", {"input_sha256": input_sha, **scene_input})
            options = [(kind, None, None, None) for kind in ("baseline", "timed")]
            for name in fold_owners(scene.name):
                options.append(("shared__" + name.split("__", 1)[1], models[name], metadata["bounds"][name], "physical31"))
            for policy, model, ranges, schema in options:
                wall, cpu = perf_counter(), process_time()
                try:
                    result = recovery.deployment(scene, model=model, bounds=ranges, schema=schema, kind=policy)
                except Exception as exc:
                    result = {"metrics": {"status": "failed_run", "total_cost": None, "completed": None,
                        "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags), "wall_seconds": perf_counter() - wall,
                        "cpu_seconds": process_time() - cpu, "failure": {"type": type(exc).__name__, "reason": str(exc)}}}
                result["metrics"].update(stream=scene.name, realization=realization, policy=policy, input_sha256=input_sha)
                records.append(result["metrics"])
                recovery.save(local / (policy + ".json"), result)
            print(json.dumps({"stage": "shared_deploy", "stream": scene.name, "realization": realization, "completed_runs": len(records)}), flush=True)
    if len(records) != 288:
        raise ValueError("missing shared deployment denominator")
    check_shared_stage(output, "fit")
    _, _, final_inputs = load_frozen_inputs(inputs["master_directory"])
    if final_inputs != inputs or recovery.sha(model_path) != frozen_model_sha:
        raise ValueError("frozen inputs/models changed during evaluation")
    return freeze(output, "evaluation", {"fits": 24, "deployment_runs": len(records), "learned_deployment_runs": 216,
        "control_deployment_runs": 72, "scheduled_bag_denominator": sum(r["scheduled_bags"] for r in records),
        "completed_bags": sum(r["completed"] or 0 for r in records), "failures": [r for r in records if r["status"] != "completed_run"],
        "deployment_metrics": records, "model_or_seed_selection": False, "fresh_confirmation": False,
        "new_labels": 0, "same_training_data_across_objectives": True, "limits": PROTOCOL["limits"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--master", type=Path)
    parser.add_argument("--stage", required=True, choices=("fit", "evaluation", "all"))
    args = parser.parse_args()
    if args.stage in {"fit", "all"} and args.master is None:
        parser.error("--master is required to fit from frozen recovery inputs")
    result = run_fit(args.output, args.master) if args.stage in {"fit", "all"} else None
    if args.stage in {"evaluation", "all"}:
        result = run_evaluation(args.output)
    print(json.dumps({k: v for k, v in result.items() if k != "deployment_metrics"}, indent=2))
    raise SystemExit(int(bool(result["failures"])))
