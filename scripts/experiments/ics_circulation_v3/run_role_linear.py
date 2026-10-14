"""Paired linear role-label comparison; freeze 16 fits before 216 full episodes."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
from time import perf_counter, process_time

import numpy as np

from .experiment_protocol import check_output_directory, create_output_directory
from .paired_linear import PairedLinearModel
from . import run_paired_recovery as shared


SOURCES = tuple(dict.fromkeys(("run_role_linear.py", "paired_linear.py", *shared.SOURCES)))
PROTOCOL = {"schema": "ics_v3_paired_linear_roles_v1", "scope": "same four synthetic development streams",
    "source_labels": "identical complete R0 role labels used by paired recovery",
    "spec": asdict(shared.SPEC), "streams": shared.PROTOCOL["streams"],
    "schemas": {key: list(value) for key, value in shared.SCHEMAS.items()},
    "kinds": list(shared.KINDS), "alpha": 1., "seed": None, "model_count": 16,
    "model_parameters": {"paired23": 23, "physical31": 31},
    "objective": "mean_squared_paired_error + alpha * sum(weights**2)",
    "targets": {"paired_direct": "delta_mean", "residual": "delta_mean_minus_timed_delta"},
    "normalization": "fold training rows only, same mean/std and constant feature threshold as role MLP",
    "fold": "entire stream held out including all roles, bands, candidate rows and observations",
    "training": "R0 only; all 16 model files frozen before any held-out assessment or deployment",
    "future_law": shared.PROTOCOL["stress_tapes"], "episode_horizon": 72,
    "deployment": {"models": 144, "baseline_timed": 72, "total": 216,
                   "realizations_per_stream": 9, "stress_per_stream": 8, "nominal_per_stream": 1},
    "baseline_comparison": "same shared deployment_scenes function and actual tape for every policy",
    "no_selection": "no alpha, seed, schema or held-out result selection",
    "limitations": ["The four development streams are not new independent operational samples.",
        "MLP and linear models differ in capacity and regularization; this is a fixed simple reference.",
        "No R1 state recovery is used by the linear models.",
        "Empirical candidate regret uses finite common-future labels and their estimated minimum.",
        "All runtime failures and uncompleted tasks remain in the full scheduled denominator.",
        "Shared-workstation wall timing is descriptive only."]}


def fit_fold(rows, held_out, schema, kind):
    streams = set(PROTOCOL["streams"])
    if held_out not in streams or schema not in shared.SCHEMAS or kind not in shared.KINDS:
        raise ValueError("undeclared linear fold, schema or kind")
    if any(r["stream"] not in streams or r.get("owner") is not None for r in rows):
        raise ValueError("only original R0 streams may enter the linear comparison")
    selected = [r for r in rows if r["stream"] != held_out]
    if {r["stream"] for r in selected} != streams - {held_out}:
        raise ValueError("missing training stream")
    groups = {r["source_group"] for r in selected}
    if groups & {r["source_group"] for r in rows if r["stream"] == held_out}:
        raise ValueError("checkpoint crosses the whole-stream fold")
    training = [dict(row, split="train") for row in shared.project_rows(selected, schema)]
    model = PairedLinearModel.fit(training, kind, feature_names=shared.SCHEMAS[schema], alpha=1.)
    matrix = np.asarray([[r["features"][n] for n in model.feature_names] for r in training])
    bounds = {n: {"minimum": float(matrix[:, i].min()), "maximum": float(matrix[:, i].max())}
              for i, n in enumerate(model.feature_names)}
    fold = {"held_out_stream": held_out, "training_streams": sorted(streams - {held_out}),
            "schema": schema, "kind": kind, "training_rows": len(training),
            "training_checkpoints": sorted(groups), "training_rows_sha256": shared.digest(training)}
    return model, bounds, fold


def _check_sources(hashes, output):
    code = Path(__file__).parent
    return all(shared.sha(code / n) == h == shared.sha(output / "source_snapshot" / n)
               for n, h in hashes.items())


def _check_inputs(inputs):
    folder = Path(inputs["directory"])
    return (shared.sha(folder / "manifest.json") == inputs["manifest_sha256"]
            and all(shared.sha(folder / p) == h for p, h in inputs["files_sha256"].items()))


def run(output, labels):
    check_output_directory(output)
    rows, labels_data, inputs = shared.load_r0_labels(labels)
    output = create_output_directory(output)
    (output / "source_snapshot").mkdir()
    hashes = {}
    for name in SOURCES:
        content = (Path(__file__).parent / name).read_bytes()
        (output / "source_snapshot" / name).write_bytes(content)
        hashes[name] = sha256(content).hexdigest()
    shared.save(output / "protocol.json", {**PROTOCOL, "source_sha256": hashes})
    shared.save(output / "input_manifest.json", inputs)
    shared.save(output / "runtime_environment.json", {"python": sys.version, "numpy": np.__version__,
                                                     "platform": platform.platform()})
    shared.save(output / "rows.json", rows)
    models, bounds, folds, fits = {}, {}, {}, []
    started, cpu = perf_counter(), process_time()
    for held in PROTOCOL["streams"]:
        for schema in shared.SCHEMAS:
            for kind in shared.KINDS:
                name = f"{held}__{schema}__{kind}"
                wall, fit_cpu = perf_counter(), process_time()
                model, bound, fold = fit_fold(rows, held, schema, kind)
                models[name], bounds[name], folds[name] = model.to_dict(), bound, fold
                fits.append({"name": name, "wall_seconds": perf_counter() - wall,
                             "cpu_seconds": process_time() - fit_cpu, **fold,
                             "training_metadata": model.training_metadata})
    assert len(models) == PROTOCOL["model_count"]
    shared.save(output / "frozen_models.json", models)
    shared.save(output / "folds_and_bounds.json", {"folds": folds, "bounds": bounds})
    shared.save(output / "fit_history.json", fits)
    frozen_hash = shared.sha(output / "frozen_models.json")
    if not _check_sources(hashes, output) or not _check_inputs(inputs):
        raise ValueError("source or label artifact changed before evaluation")
    shared.save(output / "fit_freeze.json", {"model_count": len(models), "models_sha256": frozen_hash,
        "held_out_assessment_or_deployment_started": False,
        "all_models_frozen_before_any_evaluation": True})
    loaded = {name: PairedLinearModel.from_dict(value) for name, value in models.items()}
    assessments = {}
    for held in PROTOCOL["streams"]:
        subset = [r for r in rows if r["stream"] == held]
        assessments[held] = {kind: shared.assess(subset, kind=kind) for kind in ("baseline", "timed")}
        for name, model in loaded.items():
            if folds[name]["held_out_stream"] == held:
                assessments[held][name] = shared.assess(subset, model, schema=folds[name]["schema"])
    shared.save(output / "held_out_assessments.json", assessments)
    records, tapes = [], []
    for base_scene in shared.sustained_scenes():
        for realization, scene in shared.deployment_scenes(base_scene):
            folder = output / (scene.name + "__" + realization)
            folder.mkdir()
            scene_input = shared.scene_inputs(scene)
            shared.save(folder / "inputs.json", scene_input)
            tape_hash = shared.digest(scene_input["actual_tape_event_engine_only"])
            input_hash = shared.digest(scene_input)
            tapes.append({"stream": scene.name, "realization": realization,
                          "actual_tape_sha256": tape_hash, "scene_input_sha256": input_hash})
            options = [("baseline", None, None, None), ("timed", None, None, None)]
            options += [(name.split("__", 1)[1], model, bounds[name], folds[name]["schema"])
                        for name, model in loaded.items() if folds[name]["held_out_stream"] == scene.name]
            for name, model, bound, schema in options:
                wall, run_cpu = perf_counter(), process_time()
                try:
                    result = shared.deployment(scene, model=model, bounds=bound, schema=schema, kind=name)
                except Exception as exc:
                    result = {"metrics": {"status": "failed_run", "total_cost": None, "completed": None,
                        "scheduled_bags": len(scene.initial.bags) + len(scene.future_bags),
                        "wall_seconds": perf_counter() - wall, "cpu_seconds": process_time() - run_cpu,
                        "failure": {"type": type(exc).__name__, "reason": str(exc)}}}
                result["metrics"].update(stream=scene.name, realization=realization, policy=name,
                    actual_tape_sha256=tape_hash, scene_input_sha256=input_hash, models_frozen_sha256=frozen_hash)
                shared.save(folder / (name + ".json"), result)
                records.append(result["metrics"])
                print(json.dumps(result["metrics"]), flush=True)
    assert len(records) == PROTOCOL["deployment"]["total"]
    shared.save(output / "paired_tapes.json", tapes)
    summary = {"fits": len(models), "label_checkpoints": len(labels_data), "training_source_rows": len(rows),
        "deployment_runs": len(records), "linear_deployments": sum(r["policy"] not in {"baseline", "timed"} for r in records),
        "baseline_timed_deployments": sum(r["policy"] in {"baseline", "timed"} for r in records),
        "scheduled_bag_denominator": sum(r["scheduled_bags"] for r in records),
        "completed_bags": sum(r["completed"] or 0 for r in records),
        "failures": [r for r in records if r["status"] != "completed_run"], "deployment_metrics": records,
        "source_changed_during_run": not _check_sources(hashes, output), "input_changed_during_run": not _check_inputs(inputs),
        "models_changed_during_evaluation": shared.sha(output / "frozen_models.json") != frozen_hash,
        "source_sha256": hashes, "wall_seconds": perf_counter() - started, "cpu_seconds": process_time() - cpu,
        "fit_cpu_seconds": sum(f["cpu_seconds"] for f in fits), "limits": PROTOCOL["limitations"],
        "model_selection": False, "fresh_confirmation": False}
    shared.save(output / "summary.json", summary)
    shared.save(output / "manifest.json", {p.relative_to(output).as_posix(): shared.sha(p)
        for p in sorted(output.rglob("*")) if p.is_file()})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    summary = run(args.output, args.labels)
    print(json.dumps({k: v for k, v in summary.items() if k not in {"deployment_metrics", "source_sha256"}}))
    return int(bool(summary["failures"]) or any(summary[k] for k in
        ("source_changed_during_run", "input_changed_during_run", "models_changed_during_evaluation")))


if __name__ == "__main__":
    raise SystemExit(main())
