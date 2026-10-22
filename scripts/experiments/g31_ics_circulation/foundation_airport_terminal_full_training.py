"""Fit one frozen demand candidate from two complete, explicitly named TRAIN runs.

The CLI reads no DEV or TEST trajectory and starts no native process. It consumes
actual TF-B1-300 callbacks and matured BAG_ARRIVAL labels, preserving the fixed
B1, loader mapping, representation and physical source contract.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from . import foundation_airport_terminal_forecast as demand
from . import foundation_airport_terminal_forecast_evaluation as study
from . import foundation_airport_terminal_support_predictor as supported
from . import foundation_airport_terminal_prediction_audit as audit
from .foundation_airport_inventory_spi_campaign import read_bound

SCHEMA = "g31.terminal_demand_complete_TRAIN_fit.v1"
ORIGINS = tuple(range(7200, 59400-1800+1, 1800))
PRODUCER_FILES = (Path(__file__).name, "foundation_airport_terminal_forecast_evaluation.py",
    "foundation_airport_terminal_predictor.py", "foundation_airport_terminal_support_predictor.py",
    "foundation_airport_terminal_forecast.py", "foundation_airport_terminal_prediction_audit.py")


def require(value, reason):
    if not value:
        raise ValueError("terminal_full_training:"+reason)


def producer_bindings():
    return {name: study.bound(Path(__file__).with_name(name)) for name in PRODUCER_FILES}


def load_training_source(directory):
    directory = Path(directory).resolve()
    # Reject other splits before reading any labels or observation/decision tape.
    plan = study.read(directory/"plan.json")
    require(plan["parent"]["split"] == "train", "TRAIN_only_source")
    require(plan["method"] == "TF-B1-300" and plan["horizon"] == 59400., "complete_TF_B1_300_source")
    require(not plan.get("demand_model") and not plan.get("model"), "unmodified_B1_training_forecasts")
    require(plan.get("forecast_bin_edges_seconds") == demand.bin_edges("300"), "fixed_300_second_grid")
    source = read_bound(plan["source_bundle"])
    for relative, expected in source["files"].items():
        require(study.sha(Path(source["root"])/relative) == expected, "immutable_execution_source:"+relative)
    mapping = read_bound(plan["mapping"])
    rows, reproduced_plan, provenance = study.training_rows(directory)
    require(reproduced_plan == plan and provenance["physical_clock"] == 59400., "complete_closed_physical_window")
    callbacks, required_available = 0, -float("inf")
    for decision in audit.iter_json_array(directory/"decisions.json.gz"):
        evidence = decision.get("forecast_binding")
        if evidence is None:
            continue
        now = plan["parent"]["calendar_start_epoch_seconds"]+decision["decision_time"]
        available = max(evidence["model_available_at_epoch_seconds"], mapping["model_available_at_epoch_seconds"])
        require(available <= now, "B1_and_mapping_available_at_actual_callback")
        require(evidence["forecast_sha256"] == audit.public_digest(evidence["forecast"]), "final_actor_forecast_identity")
        require(evidence["forecast"]["bin_edges_seconds"] == demand.bin_edges("300")
                and not evidence["forecast"].get("predictor_calibration"), "actual_callback_unmodified_B1_300")
        required_available = max(required_available, available)
        callbacks += 1
    require(callbacks > 0, "actual_callback_evidence_required")
    return {"rows": rows, "parent": plan["parent"], "end": provenance["physical_clock"],
        "provenance": provenance, "source_bundle": plan["source_bundle"], "mapping": plan["mapping"],
        "base_model_sha256": rows[0]["base_model_sha256"],
        "pipeline_available_at_epoch_seconds": required_available, "actual_callback_count": callbacks}


def fit_complete_sources(sources, *, model_available_at_epoch_seconds=None):
    """Pure validation/fitting after native provenance verification by the loader."""
    sources = list(sources)
    require(len(sources) == 2, "exactly_two_registered_TRAIN_sources")
    parents = [source["parent"] for source in sources]
    require(all(parent["split"] == "train" for parent in parents), "TRAIN_only_source")
    require(len({parent["parent_group"].rsplit(":r", 1)[0] for parent in parents}) == 2,
            "distinct_TRAIN_parent_lineages")
    require(all(source["end"] == 59400. for source in sources), "complete_59400_second_sources")
    for identity in ("source_bundle", "mapping"):
        require(len({source[identity]["sha256"] for source in sources}) == 1, "same_"+identity)
    require(len({source["base_model_sha256"] for source in sources}) == 1, "same_B1_model")
    station_sets, rows = [], []
    for source in sources:
        parent = source["parent"]
        start = parent["calendar_start_epoch_seconds"]
        expected = {(station, origin) for station in {row["station"] for row in source["rows"]}
                    for origin in ORIGINS}
        actual = {(row["station"], row["interval_start_epoch_seconds"]-start) for row in source["rows"]}
        require(len(source["rows"]) == len(actual) == len(expected) and actual == expected,
                "complete_nonoverlapping_29_windows_per_station")
        require(all(row["parent_id"] == parent["parent_group"]
                    and row["interval_end_epoch_seconds"]-row["interval_start_epoch_seconds"] == 1800.
                    and row["issued_at_epoch_seconds"] == row["interval_start_epoch_seconds"]
                    and row["label_available_at_epoch_seconds"] == start+59400.
                    for row in source["rows"]), "actual_issued_mature_window_contract")
        station_sets.append({row["station"] for row in source["rows"]})
        rows.extend(source["rows"])
    require(len(station_sets[0]) == 10 and station_sets[0] == station_sets[1], "same_ten_business_loader_stations")
    require(len(rows) == 580, "580_mature_nonoverlapping_station_windows")
    closed = max(row["label_available_at_epoch_seconds"] for row in rows)
    pipeline_available = max(source["pipeline_available_at_epoch_seconds"] for source in sources)
    available = closed+1. if model_available_at_epoch_seconds is None else model_available_at_epoch_seconds
    require(demand.finite(available) and max(closed, pipeline_available) <= available,
            "model_available_after_all_labels_and_inputs")
    model = supported.fit(rows, train_parents=parents,
        training_labels_closed_at_epoch_seconds=closed, model_available_at_epoch_seconds=available,
        bin_edges_seconds=demand.bin_edges("300"), prior_exposure=8.)
    require(all(windows == [[7200., 59400.]] for windows in model["support_by_station"].values()),
            "full_common_TRAIN_support_reproduced")
    return model, rows


def run_training(directories, output, *, model_available_at_epoch_seconds=None):
    directories, output = list(directories), Path(output).resolve()
    require(len(directories) == 2 and len({Path(path).resolve() for path in directories}) == 2,
            "two_explicit_distinct_source_paths")
    require(not output.exists(), "fresh_output_directory")
    producer_sources = producer_bindings()
    sources = [load_training_source(directory) for directory in directories]
    model, rows = fit_complete_sources(sources, model_available_at_epoch_seconds=model_available_at_epoch_seconds)
    require(all(study.sha(reference["path"]) == reference["sha256"] for reference in producer_sources.values()),
            "producer_source_changed_during_TRAIN_fit")
    provenance = {"schema": SCHEMA, "sources": [{k: v for k, v in source.items() if k != "rows"} for source in sources],
        "source_files": producer_sources, "producer_sources_unchanged": True,
        "row_count": len(rows), "common_time_support": [7200., 59400.],
        "forecast_bin_seconds": 300., "forecast_horizon_seconds": 1800., "prior_exposure": 8.,
        "training_labels_sha256": demand.digest(rows), "model_sha256": model["sha256"],
        "model_available_at_epoch_seconds": model["base_calibration"]["model_available_at_epoch_seconds"],
        "availability_semantics": "registered_simulated_calendar_not_wall_clock_deployment",
        "DEV_or_TEST_labels_read": False, "native_starts": 0, "is_RL": False,
        "allocator_or_native_parameters_fitted": False, "service_feedback_used_to_update_parameters": False,
        "candidate_status": "TRAIN_fitted_requires_new_fixed_allocator_native_held_out_validation",
        "no_independent_new_real_airport_days": True}
    output.mkdir(parents=True)
    for name, value in (("model.json", model), ("provenance.json", provenance)):
        (output/name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    with gzip.open(output/"training_rows.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(rows, stream, ensure_ascii=False, allow_nan=False)
    return {"schema": SCHEMA, "model": study.bound(output/"model.json"),
        "model_sha256": model["sha256"], "training_rows": study.bound(output/"training_rows.json.gz"),
        "provenance": study.bound(output/"provenance.json"), "row_count": len(rows), "native_starts": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train-runs", type=Path, nargs=2, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model-available-at", type=float)
    args = parser.parse_args()
    print(json.dumps(run_training(args.train_runs, args.output,
        model_available_at_epoch_seconds=args.model_available_at), ensure_ascii=False))


if __name__ == "__main__":
    main()
