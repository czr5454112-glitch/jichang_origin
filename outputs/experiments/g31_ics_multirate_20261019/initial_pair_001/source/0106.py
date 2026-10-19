"""Offline all117 validation; native labels never enter public model inputs."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import time
from . import public_reuse_model as model


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def evaluate(evidence: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    source = Path(model.__file__)
    before = sha(source)
    shutil.copyfile(source, output / source.name)
    evaluator_before = sha(Path(__file__))
    shutil.copyfile(Path(__file__), output / Path(__file__).name)
    ledger = json.loads((evidence / "branch_ledger.json").read_text())
    if len(ledger) != 117 or any(r["status"] != "assessed" for r in ledger.values()):
        raise ValueError("public_model:incomplete_reference_denominator")
    protocol = {"model_version": model.VERSION, "native_branch_budget": 0, "expected_validation_cells": sorted(ledger),
        "prediction_inputs": "common static contract plus source-authorized initial A/B captures and candidate action only",
        "information_scope": "offline combination, NOT actual delivered native planning messages",
        "candidate_generation": "31 public-duration fixedroute times plus four route2 old times; before reading outcomes",
        "residuals": "all four completions, actual later edges, recovery count, per-job strict protection confusion; no fit exclusions",
        "uncertainty": "conditional point estimates; no calibrated deterministic upper bound or native protection certificate",
        "source_sha256": before, "evaluator_sha256": evaluator_before, "native_calls": 0}
    write(output / "preregistered_evaluation.json", protocol)
    bundles, proposals, proposal_ms = {}, {}, {}
    # Construct predictions before consulting native completion labels.
    predictions, raw_by_key, elapsed = {}, {}, []
    for key, row in ledger.items():
        raw = json.load(gzip.open(evidence / (key + ".json.gz"), "rt"))
        raw_by_key[key] = raw
        folder = key.split("/")[0]
        if folder not in bundles:
            views = raw["seed_views"]
            captures = tuple(model.Capture.from_view(views[owner], identity="offline-initial-" + owner,
                provenance="offline_source_authorized_capture") for owner in ("A", "B"))
            bundle = model.assemble(model.public_contract(views["A"]), captures, model.START)
            bundles[folder] = bundle
            actions, incumbent = model.candidates_from_durations(bundle)
            proposal_start = time.perf_counter()
            proposals[folder] = model.propose(bundle, actions, incumbent)
            proposal_ms[folder] = (time.perf_counter() - proposal_start) * 1000
        action = {field: row[field] for field in ("initial_next", "departure", "later_mode")}
        start = time.perf_counter()
        predictions[key] = {"action": action, "prediction": model.predict(bundles[folder], action)}
        elapsed.append((time.perf_counter() - start) * 1000)
    write(output / "frozen_model_predictions.json", predictions)
    write(output / "frozen_model_proposals.json", proposals)
    write(output / "offline_capture_bundles.json", bundles)
    confusion = {"both_protected": 0, "false_protected": 0, "missed_protected": 0, "both_unprotected": 0, "unknown": 0}
    rows, errors, unknown, max_error = {}, [], [], 0.
    for key, record in predictions.items():
        raw, pred = raw_by_key[key], record["prediction"]
        folder = key.split("/")[0]
        baseline = folder + "/old_route1_window1"
        native = raw["summary"]["completion"]
        native_protected = all(t <= raw_by_key[baseline]["summary"]["completion"][j] for j, t in native.items())
        if pred["status"] != "conditional_prediction":
            unknown.append(key)
            confusion["unknown"] += 1
            rows[key] = {"status": "unknown_model", "native_protected": native_protected}
            continue
        residual = {j: pred["completion"][j] - t for j, t in native.items()}
        modelbase = predictions[baseline]["prediction"]
        predicted_protected = all(t <= modelbase["completion"][j] for j, t in pred["completion"].items())
        label = ("both_protected" if native_protected else "false_protected") if predicted_protected else ("missed_protected" if native_protected else "both_unprotected")
        confusion[label] += 1
        errors.extend(abs(r) for r in residual.values())
        max_error = max(max_error, *(abs(r) for r in residual.values()))
        model_edges = [(r["job"], r["target"]) for r in pred["physical_projection"] if r["event"] == "EDGE_ENTER" and r["source"] == 7]
        native_edges = [(r["job"], r["actual_next"]) for r in raw["summary"]["actual_later_choices"]]
        rows[key] = {"status": "compared", "prediction_minus_native_seconds": residual,
            "model_protected": predicted_protected, "native_protected": native_protected,
            "later_executed_edges_match": model_edges == native_edges,
            "model_rejections": pred["projected_rejections"], "native_rejections": raw["summary"]["recovered_rejection_count"]}
    selected = {}
    for folder, proposal in proposals.items():
        action = proposal["selected_action"]
        matches = [key for key, item in predictions.items() if key.startswith(folder + "/") and item["action"] == action]
        if len(matches) != 1:
            selected[folder] = {"status": "unknown_unexecuted_or_ambiguous", "action": action}
        else:
            key = matches[0]
            native = raw_by_key[key]["summary"]["completion"]
            baseline = raw_by_key[folder + "/old_route1_window1"]["summary"]["completion"]
            selected[folder] = {"status": "offline_native_label_checked", "key": key, "action": action,
                "completion": native, "strict_native_protected": all(t <= baseline[j] for j, t in native.items()),
                "gain_vs_declared_incumbent_seconds": sum(baseline.values()) - sum(native.values())}
    report = {"schema": "g31.lt2.public_model_all117_validation.v1", "status": "completed_offline_validation",
        "denominator": 117, "compared": 117 - len(unknown), "unknown": unknown, "strict_protection_confusion": confusion,
        "all_job_residual_count": len(errors), "mean_absolute_completion_error_seconds": statistics.mean(errors) if errors else None,
        "max_absolute_completion_error_seconds": max_error, "exact_completion_vectors": sum(r.get("prediction_minus_native_seconds") is not None and all(x == 0 for x in r["prediction_minus_native_seconds"].values()) for r in rows.values()),
        "later_edges_match_count": sum(r.get("later_executed_edges_match", False) for r in rows.values()),
        "rejection_count_match": sum(r.get("model_rejections") == r.get("native_rejections") for r in rows.values() if r["status"] == "compared"),
        "selected_proposals": selected, "rows": rows, "prediction_only_ms_max": max(elapsed),
        "prediction_only_ms_mean": statistics.mean(elapsed), "source_before": before, "source_after": sha(source),
        "source_changed": before != sha(source) or evaluator_before != sha(Path(__file__)),
        "proposal_35candidate_model_only_ms": proposal_ms,
        "timing_scope": "Excludes owner capture, transport, validation, native action and terminal ACK; not full-request latency",
        "native_calls": 0, "online_solver_implemented": False,
        "rolling_later_checkpoint_support": False, "complete_request_100ms_certified": False,
        "model_error_bound_certified": False, "certified_model_protection": False}
    write(output / "validation.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    evaluate(a.evidence, a.output)


if __name__ == "__main__": main()
