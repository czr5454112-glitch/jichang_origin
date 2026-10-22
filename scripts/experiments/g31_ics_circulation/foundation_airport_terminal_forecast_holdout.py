"""Evaluate a frozen TRAIN demand model on saved closed DEV public observations.

Predictions are built before opening the DEV label tape. This report never fits
parameters, creates native processes, or treats offline replay as actor execution.
Both methods use the same public B1, loader mapping, 300-second representation,
29 saved physical origins and mature 5/15/30-minute arrival labels.
"""
from __future__ import annotations

import argparse
import copy
import gzip
from itertools import zip_longest
import json
from pathlib import Path

from . import foundation_airport_joint_calendar_prepared as prepared
from . import foundation_airport_terminal_forecast as demand
from . import foundation_airport_terminal_forecast_evaluation as study
from . import foundation_airport_terminal_prediction_audit as audit
from . import foundation_airport_terminal_predictor as calibration
from . import foundation_airport_terminal_support_predictor as supported
from .foundation_airport_inventory_spi_campaign import read_bound

SCHEMA = "g31.terminal_demand_saved_public_DEV_evaluation.v1"
ORIGINS = tuple(range(7200, 59400-1800+1, 1800))
PRODUCER_FILES = (Path(__file__).name, "foundation_airport_joint_calendar_prepared.py",
    "foundation_airport_terminal_forecast.py", "foundation_airport_terminal_predictor.py",
    "foundation_airport_terminal_support_predictor.py", "foundation_airport_joint_calendar.py",
    "foundation_airport_loader_mapping.py", "foundation_flight_forecaster.py",
    "foundation_flight_forecaster_arrays.py", "foundation_flight_context.py",
    "foundation_airport_feasible_domain.py", "foundation_airport_flight.py",
    "foundation_airport_calendar_forecast.py", "foundation_airport_learning_public.py",
    "foundation_airport_terminal_forecast_evaluation.py", "foundation_airport_terminal_prediction_audit.py")


def require(value, reason):
    if not value:
        raise ValueError("terminal_forecast_holdout:"+reason)


def model_base(model):
    if model.get("schema") == supported.SCHEMA:
        supported.validate_model(model)
        return model["base_calibration"]
    return calibration.validate_model(model)


def producer_bindings():
    return {name: study.bound(Path(__file__).with_name(name)) for name in PRODUCER_FILES}


def predict_saved_observation(plan, observation, provider, model):
    """This function has no label argument; replay is not original consumption."""
    evidence = provider(observation=observation, parent=plan["parent"])
    raw = copy.deepcopy(evidence["forecast"])
    require(raw["forecast_origin"] == observation["now"] and raw["owner_scope"] == observation["owner_id"],
            "saved_current_owner_clock")
    require(evidence["model_available_at_epoch_seconds"] <=
            plan["parent"]["calendar_start_epoch_seconds"]+observation["now"], "public_B1_available_at_origin")
    # The prepared producer normally runs inside a live actor. Its numerical
    # output is reused here, but its live-consumption assertion is not copied.
    raw["calendar_provenance"].update(forecast_provenance="offline_replay_saved_public_observation",
        actual_callback_consumption=False, offline_provider_output_sha256=evidence["forecast_sha256"])
    base = demand.rebin_forecast(raw, bin_edges_seconds=demand.bin_edges("300"))
    transform = supported.transform if model.get("schema") == supported.SCHEMA else calibration.transform
    candidate = transform(model, base, now=observation["now"], parent_id=plan["parent"]["parent_group"])
    return {"TF-B1-300": base, "TF-predictor": candidate}


def build_public_predictions(directory, model):
    """Stream large saved views; keep only 29 small forecast records in memory."""
    directory = Path(directory)
    plan = study.read(directory/"plan.json")
    require(plan["parent"]["split"] == "dev", "DEV_only_no_TEST_or_TRAIN_evaluation")
    verified, worker = audit.closed_plan(directory)
    require(verified == plan and worker["final_physical_time"] == plan["horizon"] == 59400.,
            "complete_closed_DEV_59400")
    require(plan["method"] == "C00", "common_saved_C00_state_source")
    base_model = model_base(model)
    require(calibration.parent_uid(plan["parent"]["parent_group"]) not in base_model["train_parent_uids"],
            "held_out_parent_lineage")
    mapping = read_bound(plan["mapping"])
    require(mapping["sha256"] == base_model["mapping_sha256"], "same_TRAIN_loader_mapping")
    binding = read_bound(plan["forecast_binding"])
    receipts = study.read(directory/"plan_preload_receipts.json")
    provider = prepared.prepare_forecast_provider(binding, receipts, loader_mapping=mapping)
    records, origin_means, references = {}, {}, []
    observations = audit.iter_json_array(directory/"observations.json.gz")
    decisions = audit.iter_json_array(directory/"decisions.json.gz")
    scanned = 0
    for decision, saved in zip_longest(decisions, observations):
        require(decision is not None and saved is not None, "matching_public_stream_lengths")
        observation = saved["observation"]
        origin = observation["now"]
        if origin > ORIGINS[-1]:
            break
        scanned += 1
        if origin not in ORIGINS:
            continue
        require(audit.public_digest(observation) == saved["digest"] == decision["public_observation_ref"],
                "saved_public_observation_digest")
        require(mapping["model_available_at_epoch_seconds"] <=
                plan["parent"]["calendar_start_epoch_seconds"]+origin, "mapping_available_at_origin")
        predictions = predict_saved_observation(plan, observation, provider, model)
        means = predictions["TF-B1-300"]["new_demand_mean_by_region"]
        if origin in records:
            require(means == origin_means[origin], "owner_copies_same_demand_population")
            continue
        origin_means[origin] = means
        records[origin] = {"parent_id": plan["parent"]["parent_group"], "split": "dev", "predictions": predictions}
        references.append({"physical_origin": origin, "owner": observation["owner_id"],
            "saved_observation_sha256": saved["digest"], "saved_decision_id": decision["decision_id"],
            "original_C00_consumed_forecast": False})
    require(sorted(records) == list(ORIGINS), "all_29_predeclared_saved_origins_required")
    return plan, [records[origin] for origin in ORIGINS], {"saved_references": references,
        "public_states_streamed": scanned, "owners_deduplicated_by_origin": True,
        "owner_selection": "first_saved_callback_per_origin_after_equal_demand_check",
        "plan": study.bound(directory/"plan.json"), "receipt": study.bound(directory/"receipt.json"),
        "observations": study.bound(directory/"observations.json.gz"),
        "decisions": study.bound(directory/"decisions.json.gz"),
        "actual_preload_receipts": study.bound(directory/"plan_preload_receipts.json"),
        "native_data_source_bundle": plan["source_bundle"], "mapping": plan["mapping"],
        "B1_binding": plan["forecast_binding"], "future_truth_read_by_prediction_builder": False}


def score_mature_labels(records, model, *, parent, arrivals, source):
    """Attach observed outcomes only after all frozen-model predictions exist."""
    require(parent["split"] == "dev" and source["physical_clock"] == 59400., "complete_DEV_labels")
    records = copy.deepcopy(records)
    start = parent["calendar_start_epoch_seconds"]
    for record in records:
        require(record["parent_id"] == parent["parent_group"] and record["split"] == "dev", "same_DEV_label_parent")
        raw = record["predictions"]["TF-B1-300"]
        origin = raw["forecast_origin"]
        record["labels"] = [{"station": station, "window_seconds": window,
            "actual_arrivals": study.count(arrivals, station, origin, origin+window),
            "label_available_at_epoch_seconds": start+source["physical_clock"],
            "source_evidence_id": source["source_evidence_id"]}
            for station in sorted(raw["new_demand_mean_by_region"]) for window in (300, 900, 1800)]
        record["observed_through_epoch_seconds"] = start+source["physical_clock"]
    return calibration.evaluate_common_windows(records, model=model_base(model)), records


def run(directory, model_path, output):
    directory, model_path, output = Path(directory), Path(model_path), Path(output)
    require(not output.exists(), "fresh_output_directory")
    producer_sources = producer_bindings()
    frozen_model_ref = study.bound(model_path)
    model = read_bound(frozen_model_ref)
    model_base(model)
    plan, predictions, provenance = build_public_predictions(directory, model)
    predictions_sha256 = demand.digest(predictions)
    # First label access occurs here; no prediction helper receives arrivals.
    label_plan, arrivals, label_source = study.load_closed_run(directory, split="dev")
    require(label_plan == plan, "same_public_and_label_plan")
    evaluation, records = score_mature_labels(predictions, model, parent=plan["parent"], arrivals=arrivals, source=label_source)
    require(demand.digest(predictions) == predictions_sha256, "labels_do_not_mutate_predictions")
    require(study.sha(model_path) == frozen_model_ref["sha256"], "frozen_model_unchanged_after_DEV_evaluation")
    require(all(study.sha(reference["path"]) == reference["sha256"] for reference in producer_sources.values()),
            "producer_source_changed_during_evaluation")
    evaluation["origin_periods"] = {f"{left}:{right}": calibration.evaluate_common_windows(
        [record for record in records if left <= record["predictions"]["TF-B1-300"]["forecast_origin"] < right],
        model=model_base(model)) for left, right in ((7200, 18000), (18000, 36000), (36000, 59400))}
    evaluation.update(schema=SCHEMA, evaluation_window_physical_seconds=[7200., 59400.],
        forecast_origins_stride_seconds=1800., model_file=frozen_model_ref, model_sha256=model["sha256"],
        model_training_row_count=model_base(model)["training_row_count"],
        comparison="same_saved_public_origins_same_B1_mapping_grid_and_mature_labels",
        native_data_method="C00", forecast_provenance="offline_replay_not_actual_C00_consumption",
        model_fitted_or_selected_by_this_report=False, native_policy_pair_comparison=False,
        independence="DEV_evaluation_only; reuse_of_diagnosed_DEV2201_is_not_independent_confirmation")
    provenance.update(schema=SCHEMA, model=frozen_model_ref, labels=label_source,
        predictions_frozen_before_label_tape_opened_sha256=predictions_sha256,
        model_unchanged_after_DEV=True, DEV_labels_used_for_fitting=False, TEST_opened=False, native_starts=0,
        prediction_producer_source_files=producer_sources, producer_sources_unchanged=True,
        different_native_data_source_and_current_offline_producer_are_distinguished=True)
    output.mkdir(parents=True)
    for name, value in (("evaluation.json", evaluation), ("provenance.json", provenance)):
        (output/name).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    with gzip.open(output/"evaluation_records.json.gz", "wt", encoding="utf-8") as stream:
        json.dump(records, stream, ensure_ascii=False, allow_nan=False)
    return {"output": str(output.resolve()), "model_sha256": model["sha256"], "labels": evaluation["label_count"],
        "native_starts": 0, "mae": {method: {window: value["mae"] for window, value in metrics.items()}
                                  for method, metrics in evaluation["methods"].items()}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.run, args.model, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
