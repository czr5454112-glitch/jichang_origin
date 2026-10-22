"""TRAIN-only supervised demand calibration and common-window offline scoring.

The Poisson exposure calibration is a forecast model, not RL or action-Q.
Labels are actual arrival counts on completed nonoverlapping TRAIN windows.
The runtime transform consumes a frozen model and demand forecast only; it
cannot issue a tray, source, allocation, request, or native command.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from . import foundation_airport_terminal_forecast as representation

SCHEMA = "g31.terminal_demand_poisson_calibration.v1"
EVALUATION_SCHEMA = "g31.terminal_demand_common_window_evaluation.v1"
digest = representation.digest
finite = representation.finite


def require(value, reason):
    if not value:
        raise ValueError("terminal_predictor:" + reason)


def parent_uid(parent):
    return parent.rsplit(":r", 1)[0]


def fit(rows, *, train_parent_ids, training_labels_closed_at_epoch_seconds,
        model_available_at_epoch_seconds, bin_edges_seconds, prior_exposure=8.,
        scale_bounds=(.25, 4.)):
    """Fit a regularized Poisson rate multiplier from mature arrival labels.

    The prior is Gamma(alpha,alpha) on the multiplicative rate. The posterior
    mean is clipped to the preregistered bounds; this does not guarantee better
    held-out accuracy. Digests bind supplied producer evidence but cannot make
    falsely labelled rows causal: producers must verify native BAG_ARRIVALs.
    """
    rows = list(rows)
    parents = list(train_parent_ids)
    require(parents and len(set(parents)) == len(parents)
            and all(type(x) is str and x for x in parents), "explicit_unique_TRAIN_parents")
    closed, available = training_labels_closed_at_epoch_seconds, model_available_at_epoch_seconds
    require(finite(closed) and finite(available) and closed <= available, "closed_before_available")
    edges = representation.validate_edges(bin_edges_seconds, horizon_seconds=1800.)
    require(finite(prior_exposure) and prior_exposure > 0, "positive_prior_exposure")
    require(len(scale_bounds) == 2 and all(finite(x) for x in scale_bounds)
            and 0 < scale_bounds[0] <= 1 <= scale_bounds[1], "positive_scale_bounds_include_one")
    require(rows, "nonempty_mature_training_rows")
    identities, intervals, totals, sources, base_models, mappings = set(), {}, {}, set(), set(), set()
    latest = -math.inf
    for row in rows:
        require(row.get("split") == "train" and row.get("parent_id") in parents, "TRAIN_only_parent")
        identity = row.get("label_id")
        require(type(identity) is str and identity and identity not in identities, "unique_label_identity")
        identities.add(identity)
        require(row.get("provenance_kind") == "actual_arrival_count"
                and row.get("label_status") == "mature", "actual_mature_arrival_labels")
        for field in ("forecast_sha256", "source_evidence_id", "base_model_sha256", "mapping_sha256"):
            require(type(row.get(field)) is str and row[field], "bound_" + field)
        left, right, issued, mature = (row.get(key) for key in
            ("interval_start_epoch_seconds", "interval_end_epoch_seconds", "issued_at_epoch_seconds",
             "label_available_at_epoch_seconds"))
        require(all(finite(x) for x in (left, right, issued, mature))
                and issued <= left < right <= mature <= closed, "completed_window_before_training_boundary")
        station, expected, actual = row.get("station"), row.get("expected_arrivals"), row.get("actual_arrivals")
        require(type(station) is str and station and finite(expected) and expected >= 0
                and type(actual) is int and actual >= 0, "destination_count_label")
        # Repeated rolling windows are correlated labels, not new independent
        # exposures. Require a nonoverlapping window selection per parent/site.
        intervals.setdefault((row["parent_id"], station), []).append((left, right))
        total = totals.setdefault(station, {"expected": 0., "actual": 0, "windows": 0})
        total["expected"] += expected
        total["actual"] += actual
        total["windows"] += 1
        sources.add(row["source_evidence_id"])
        base_models.add(row["base_model_sha256"])
        mappings.add(row["mapping_sha256"])
        latest = max(latest, mature)
    for values in intervals.values():
        values.sort()
        require(all(a[1] <= b[0] for a, b in zip(values, values[1:])), "nonoverlapping_TRAIN_windows")
    require(len(base_models) == len(mappings) == 1, "fixed_B1_and_mapping_for_calibration")
    require({row["parent_id"] for row in rows} == set(parents), "every_registered_TRAIN_parent_represented")
    parameters = {}
    for station, values in sorted(totals.items()):
        raw_scale = (values["actual"] + prior_exposure) / (values["expected"] + prior_exposure)
        parameters[station] = {**values, "scale": min(scale_bounds[1], max(scale_bounds[0], raw_scale))}
    model = {"schema": SCHEMA, "method": "supervised_regularized_Poisson_exposure_calibration",
        "parameters": parameters, "prior_exposure": float(prior_exposure), "scale_bounds": list(scale_bounds),
        "train_parent_ids": sorted(parents), "train_parent_uids": sorted({parent_uid(x) for x in parents}),
        "training_labels_sha256": digest(rows), "training_row_count": len(rows),
        "training_labels_closed_at_epoch_seconds": closed,
        "model_available_at_epoch_seconds": available, "latest_label_available_at_epoch_seconds": latest,
        "base_model_sha256": next(iter(base_models)), "mapping_sha256": next(iter(mappings)),
        "bin_edges_seconds": edges, "source_evidence_ids": sorted(sources),
        "dev_or_test_labels_used": False, "native_execution_authority": False,
        "output_semantics": "expected_new_arrivals_only", "is_RL": False,
        "label_semantics": "actual_arrival_counts_not_transport_commands",
        "calibration_status": "TRAIN_fitted_candidate_requires_held_out_same_window_validation",
        "uncertainty_status": "unknown_dependent_B1_bins_mapping_and_fitted_scale",
        "shared_template_synthetic_parents_are_independent_real_days": False}
    model["sha256"] = digest(model)
    validate_model(model)
    return model


def validate_model(model):
    require(type(model) is dict and model.get("schema") == SCHEMA, "calibration_model_schema")
    require(model.get("sha256") == digest({k: v for k, v in model.items() if k != "sha256"}), "model_binding")
    require(model["native_execution_authority"] is False and model["dev_or_test_labels_used"] is False
            and model["is_RL"] is False and model["output_semantics"] == "expected_new_arrivals_only",
            "forecast_only_TRAIN_supervised_contract")
    representation.validate_edges(model["bin_edges_seconds"], horizon_seconds=1800.)
    closed, available = model["training_labels_closed_at_epoch_seconds"], model["model_available_at_epoch_seconds"]
    require(finite(closed) and finite(available) and model["latest_label_available_at_epoch_seconds"] <= closed <= available,
            "mature_model_boundaries")
    require(model["parameters"] and model["training_row_count"] > 0, "fitted_nonempty_parameters")
    require(model["train_parent_uids"] == sorted({parent_uid(x) for x in model["train_parent_ids"]}),
            "bound_parent_lineages")
    alpha, bounds = model["prior_exposure"], model["scale_bounds"]
    require(finite(alpha) and alpha > 0 and len(bounds) == 2 and all(finite(x) for x in bounds)
            and 0 < bounds[0] <= 1 <= bounds[1], "valid_regularization")
    for values in model["parameters"].values():
        require(finite(values["expected"]) and values["expected"] >= 0
                and type(values["actual"]) is int and values["actual"] >= 0
                and type(values["windows"]) is int and values["windows"] > 0, "valid_sufficient_statistics")
        expected = min(bounds[1], max(bounds[0], (values["actual"]+alpha)/(values["expected"]+alpha)))
        require(values["scale"] == expected, "recomputed_supervised_scale")
    return model


def transform(model, forecast, *, now, parent_id=None):
    """Pure deployable transformation; runtime reads no labels, files, or trays."""
    validate_model(model)
    require(finite(now) and now == forecast.get("forecast_origin"), "current_forecast_clock")
    start = forecast.get("calendar_provenance", {}).get("calendar_start_epoch_seconds")
    require(finite(start) and model["model_available_at_epoch_seconds"] <= start+now,
            "calibration_available_at_callback")
    require(forecast.get("model_sha256") == model["base_model_sha256"]
            and forecast.get("airport_mapping_sha256") == model["mapping_sha256"], "same_B1_and_loader_mapping")
    require(forecast["bin_edges_seconds"] == model["bin_edges_seconds"], "frozen_representation_grid")
    if parent_id is not None:
        require(type(parent_id) is str, "parent_identity")
        require(parent_uid(parent_id) not in model["train_parent_uids"], "no_deployment_on_training_parent_lineage")
    result = copy.deepcopy(forecast)
    for station, values in result["new_demand_mean_by_region"].items():
        # Missing TRAIN support uses the unchanged B1 prior, never an invented
        # zero demand; this choice is recorded for every destination.
        scale = model["parameters"].get(station, {}).get("scale", 1.)
        result["new_demand_mean_by_region"][station] = [None if x is None else x*scale for x in values]
    result = representation.rebin_forecast(result, bin_edges_seconds=model["bin_edges_seconds"])
    result["predictor_calibration"] = {
        "model_sha256": model["sha256"], "method": model["method"], "is_RL": False,
        "available_at_epoch_seconds": model["model_available_at_epoch_seconds"],
        "training_labels_closed_at_epoch_seconds": model["training_labels_closed_at_epoch_seconds"],
        "prior_forecast_sha256": digest(forecast),
        "fallback_prior_stations": sorted(set(result["new_demand_mean_by_region"])-set(model["parameters"])),
        "native_execution_authority": False, "output_semantics": "expected_new_arrivals_only",
        "uncertainty_status": model["uncertainty_status"]}
    result["calibration_status"] = model["calibration_status"]
    return result


def evaluate_common_windows(records, *, model=None):
    """Score all variants on identical mature station/5,15,30-minute labels.

    Each record has predictions {method: forecast}, observed_through_epoch_seconds,
    split, parent_id and labels [{station, window_seconds, actual_arrivals,
    label_available_at_epoch_seconds, source_evidence_id}]. No raw per-bin MAE
    across unlike bin widths is presented as a model comparison.
    """
    records = list(records)
    require(records, "nonempty_evaluation")
    if model is not None:
        validate_model(model)
    methods = sorted(records[0]["predictions"])
    require(len(methods) >= 2, "at_least_two_comparison_methods")
    totals = {method: {str(w): {"count": 0, "skipped_common_missing": 0, "absolute_error_sum": 0.,
                              "squared_error_sum": 0., "signed_error_sum": 0., "actual_sum": 0.,
                              "predicted_sum": 0.} for w in (300, 900, 1800)} for method in methods}
    seen, population = set(), []
    splits = set()
    for record in records:
        require(sorted(record["predictions"]) == methods, "same_variants_every_record")
        split, parent = record.get("split"), record.get("parent_id")
        require(split in ("train", "dev", "test") and type(parent) is str and parent, "registered_evaluation_parent")
        if model is not None:
            require(parent_uid(parent) not in model["train_parent_uids"], "held_out_parent_lineage")
        splits.add(split)
        forecasts = record["predictions"]
        first = forecasts[methods[0]]
        origin, owner = first["forecast_origin"], first["owner_scope"]
        start = first.get("calendar_provenance", {}).get("calendar_start_epoch_seconds")
        require(finite(start), "explicit_evaluation_calendar")
        for forecast in forecasts.values():
            require(forecast["forecast_origin"] == origin and forecast["owner_scope"] == owner
                    and set(forecast["new_demand_mean_by_region"]) == set(first["new_demand_mean_by_region"])
                    and forecast.get("calendar_provenance", {}).get("calendar_start_epoch_seconds") == start,
                    "identical_forecast_clock_owner_station_population")
        labels = record["labels"]
        expected_population = {(station, w) for station in first["new_demand_mean_by_region"] for w in (300, 900, 1800)}
        require({(x["station"], x["window_seconds"]) for x in labels} == expected_population
                and len(labels) == len(expected_population), "complete_same_station_same_windows")
        for label in labels:
            station, window, actual = label["station"], label["window_seconds"], label["actual_arrivals"]
            identity = (parent, owner, origin, station, window)
            require(identity not in seen, "unique_evaluation_label")
            seen.add(identity)
            require(type(actual) is int and actual >= 0 and type(label.get("source_evidence_id")) is str
                    and label["source_evidence_id"], "actual_count_and_producer_binding")
            mature, observed = label["label_available_at_epoch_seconds"], record["observed_through_epoch_seconds"]
            require(finite(mature) and finite(observed) and start+origin+window <= mature <= observed,
                    "window_label_mature_before_evaluation")
            predictions = {method: representation.expected_arrivals(forecast, origin, origin+window,
                owner=owner, station=station) for method, forecast in forecasts.items()}
            missing = any(value is None for value in predictions.values())
            population.append([*identity, actual, label["source_evidence_id"], missing])
            for method, predicted in predictions.items():
                row = totals[method][str(window)]
                if missing:
                    row["skipped_common_missing"] += 1
                    continue
                error = predicted-actual
                row["count"] += 1
                row["absolute_error_sum"] += abs(error)
                row["squared_error_sum"] += error*error
                row["signed_error_sum"] += error
                row["actual_sum"] += actual
                row["predicted_sum"] += predicted
    for windows in totals.values():
        for row in windows.values():
            count = row["count"]
            row.update(mae=None if not count else row["absolute_error_sum"]/count,
                       rmse=None if not count else math.sqrt(row["squared_error_sum"]/count),
                       bias=None if not count else row["signed_error_sum"]/count)
    return {"schema": EVALUATION_SCHEMA, "methods": totals, "splits": sorted(splits),
        "population_sha256": digest(population), "label_count": len(population),
        "same_window_seconds": [300, 900, 1800], "interval_convention": "left_open_right_closed",
        "native_starts": 0, "actor_reads_labels": False, "raw_bin_MAE_cross_width_claimed": False,
        "predictive_interval_coverage": "unavailable_no_joint_bin_and_projection_uncertainty",
        "service_gain_or_RL_gain_claimed": False,
        "sampling_limitation": "rolling windows and shared historical templates are dependent"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fit", "evaluate"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), "fresh_output_required")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = fit(**payload) if args.command == "fit" else evaluate_common_windows(**payload)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "schema": result["schema"], "native_starts": 0}))


if __name__ == "__main__":
    main()
