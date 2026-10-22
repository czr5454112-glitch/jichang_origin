"""Diagnose prefix extrapolation and evaluate a TRAIN-support-limited candidate.

The original negative result is retained. The revised candidate is fitted and
frozen from the same TRAIN rows before this command loads DEV records. Its
design follows a seen DEV failure, so that repeated DEV result is development
evidence, not a new unbiased holdout or native service improvement.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import json
from pathlib import Path

from . import foundation_airport_terminal_forecast as demand
from . import foundation_airport_terminal_forecast_evaluation as study
from . import foundation_airport_terminal_predictor as calibration
from . import foundation_airport_terminal_support_predictor as supported


def training_source_inventory():
    """Only explicit historical TRAIN name ranges; no TEST labels or runs opened."""
    root = study.ROOT/"outputs/experiments"
    cycles = [root/"g31_ics_joint_reposition_20261021/cycle_001/runs",
              root/"g31_ics_inventory_spi_20261020/cycle_001/runs",
              root/"g31_ics_action_value_20261020/cycle_001"]
    tokens = tuple("P"+str(seed)+"_" for seed in (*range(1101, 1109), *range(2101, 2109), 701, 702))
    inventory = []
    for cycle in cycles:
        if not cycle.exists():
            continue
        for directory in sorted(cycle.iterdir()):
            if not directory.is_dir() or not any(token in directory.name for token in (*tokens, "_701_", "_702_")):
                continue
            plan_path, worker_path = directory/"plan.json", directory/"worker_report.json"
            if not plan_path.is_file() or not worker_path.is_file():
                continue
            plan, worker = study.read(plan_path), study.read(worker_path)
            parent = plan.get("parent", {})
            if parent.get("split") != "train":
                continue
            inventory.append({"run": str(directory.relative_to(study.ROOT)),
                "parent_id": parent["parent_group"], "split": "train",
                "physical_clock": worker.get("final_physical_time"),
                "status": worker.get("process_status", worker.get("status")),
                "plan": study.bound(plan_path), "worker": study.bound(worker_path),
                "has_native_terminal_export": any((directory/name).is_file()
                    for name in ("terminal_evidence.json.gz", "final_result.json.gz")),
                "loader_mapping_ref": plan.get("mapping")})
    return inventory


def diagnose_periods(records):
    report = {}
    for left, right in ((7200., 18000.), (18000., 36000.), (36000., 59400.)):
        current = [record for record in records if left <= next(iter(record["predictions"].values()))["forecast_origin"] < right]
        result = calibration.evaluate_common_windows(current)
        report[f"[{int(left)},{int(right)})"] = result["methods"]
    return report


def run(output, *, source):
    output, source = Path(output), Path(source)
    study.require(not output.exists(), "fresh_diagnostic_output")
    old_model, provenance = study.read(source/"model.json"), study.read(source/"provenance.json")
    rows = study.read(source/"training_rows.json.gz")
    study.require(demand.digest(rows) == old_model["training_labels_sha256"], "original_TRAIN_labels_binding")
    # This fit and support selection executes before reading any DEV labels.
    model = supported.fit(rows, train_parents=[entry["parent"] for entry in provenance["train"]],
        training_labels_closed_at_epoch_seconds=old_model["training_labels_closed_at_epoch_seconds"],
        model_available_at_epoch_seconds=old_model["model_available_at_epoch_seconds"],
        bin_edges_seconds=old_model["bin_edges_seconds"], prior_exposure=old_model["prior_exposure"])
    study.require(model["base_calibration"] == old_model, "same_TRAIN_calibration_only_support_rule_changed")
    output.mkdir(parents=True)
    (output/"model.json").write_text(json.dumps(model, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    records = study.read(source/"evaluation_records.json.gz")
    revised = copy.deepcopy(records)
    for record in revised:
        raw = record["predictions"]["TF-B1-300"]
        record["predictions"]["TF-predictor-supported"] = supported.transform(model, raw,
            now=raw["forecast_origin"], parent_id=record["parent_id"])
    report = calibration.evaluate_common_windows(revised, model=old_model)
    inventory = training_source_inventory()
    full = [row for row in inventory if row["status"] in ("complete", "completed")
            and row["physical_clock"] == 59400. and row["has_native_terminal_export"]]
    report.update(original_negative_result_retained=True,
        candidate_design_after_DEV_diagnosis=True,
        support_boundary_selected_from_DEV=False,
        revised_fit_reads_DEV_labels=False,
        deployment_status="development_candidate_not_promoted_without_new_validation_and_closed_loop_evidence",
        periods=diagnose_periods(revised), native_starts=0,
        mechanism="early_per_station_scale_was_extrapolated_beyond_all_available_training_windows",
        known_registered_campaign_full_TRAIN_sources=full)
    refs = {name: study.bound(source/name) for name in
            ("model.json", "evaluation.json", "provenance.json", "training_rows.json.gz", "evaluation_records.json.gz")}
    receipt = {"schema": "g31.terminal_demand_support_diagnostic.v1", "source": refs,
        "model": study.bound(output/"model.json"), "source_files": {
            name: study.bound(Path(__file__).parent/name) for name in
            (Path(__file__).name, "foundation_airport_terminal_support_predictor.py")},
        "training_source_inventory": inventory, "full_59400_TRAIN_source_count": len(full),
        "TEST_runs_or_labels_opened": False, "new_native_starts": 0,
        "old_models_or_frozen_runtime_mutated": False,
        "repeated_DEV_is_independent_new_holdout": False}
    for name, value in (("evaluation.json", report), ("provenance.json", receipt)):
        (output/name).write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    with gzip.open(output/"evaluation_records.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(revised, stream, separators=(",", ":"), allow_nan=False)
    return {"output": str(output.resolve()), "model_sha256": model["sha256"],
        "full_59400_TRAIN_source_count": len(full), "native_starts": 0,
        "mae_by_window": {method: {window: values["mae"] for window, values in windows.items()}
                          for method, windows in report["methods"].items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.output, source=args.source), indent=2))


if __name__ == "__main__":
    main()
