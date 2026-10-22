"""Demand calibration confined to time periods supported by every TRAIN parent.

This supervised candidate addresses extrapolation beyond short training
prefixes. Outside observed TRAIN time support the frozen B1 forecast remains
unchanged. The support comes from TRAIN label intervals and public parent
calendars, not DEV arrivals, a chosen transport action, or an oracle demand tape.
"""
from __future__ import annotations

import copy
import math

from . import foundation_airport_terminal_forecast as demand
from . import foundation_airport_terminal_predictor as calibration

SCHEMA = "g31.terminal_demand_supported_calibration.v1"


def require(value, reason):
    if not value:
        raise ValueError("terminal_support_predictor:" + reason)


def _merge(intervals):
    merged = []
    for left, right in sorted(intervals):
        if merged and left == merged[-1][1]:
            merged[-1][1] = right
        else:
            merged.append([left, right])
    return merged


def fit(rows, *, train_parents, training_labels_closed_at_epoch_seconds,
        model_available_at_epoch_seconds, bin_edges_seconds, prior_exposure=8.):
    """Fit the same count model; retain only periods covered in every TRAIN parent.

    Registered physical-time windows must match across parents to establish
    support. Unmatched or absent periods fall back to B1 instead of being
    generalized to other parts of the day. This is deliberately conservative.
    """
    rows, parents = list(rows), list(train_parents)
    require(parents and all(parent.get("split") == "train" for parent in parents), "TRAIN_parent_calendars")
    by_id = {parent["parent_group"]: parent for parent in parents}
    require(len(by_id) == len(parents), "unique_TRAIN_parent_calendars")
    base = calibration.fit(rows, train_parent_ids=list(by_id),
        training_labels_closed_at_epoch_seconds=training_labels_closed_at_epoch_seconds,
        model_available_at_epoch_seconds=model_available_at_epoch_seconds,
        bin_edges_seconds=bin_edges_seconds, prior_exposure=prior_exposure)
    per_station = {station: {parent: set() for parent in by_id} for station in base["parameters"]}
    for row in rows:
        parent = by_id[row["parent_id"]]
        start = parent["calendar_start_epoch_seconds"]
        require(demand.finite(start), "finite_public_calendar")
        left, right = row["interval_start_epoch_seconds"]-start, row["interval_end_epoch_seconds"]-start
        require(0 <= left < right <= 86400., "physical_day_training_window")
        per_station[row["station"]][row["parent_id"]].add((left, right))
    support = {station: _merge(set.intersection(*windows.values())) for station, windows in per_station.items()}
    require(any(support.values()), "nonempty_common_TRAIN_time_support")
    result = {"schema": SCHEMA, "base_calibration": base, "support_by_station": support,
        "train_parent_calendars": [{key: parent[key] for key in
                                   ("parent_group", "split", "calendar_start_epoch_seconds")} for parent in parents],
        "support_derivation": "intersection_of_actual_mature_nonoverlapping_TRAIN_windows_per_station",
        "outside_support": "unchanged_frozen_B1",
        "boundary_bin": "overlap_duration_weighted_mean_under_published_uniform_bin_semantics",
        "native_execution_authority": False, "is_RL": False,
        "dev_labels_used_to_fit_or_choose_support": False,
        "development_status": "candidate_after_DEV_diagnosis_requires_new_independent_validation",
        "uncertainty_status": "unavailable_dependent_B1_bins_mapping_and_fitted_scale"}
    result["sha256"] = demand.digest(result)
    validate_model(result)
    return result


def validate_model(model):
    require(type(model) is dict and model.get("schema") == SCHEMA, "model_schema")
    require(model.get("sha256") == demand.digest({k: v for k, v in model.items() if k != "sha256"}), "model_binding")
    base = calibration.validate_model(model["base_calibration"])
    require(set(model["support_by_station"]) == set(base["parameters"]), "calibrated_station_support")
    require(model["native_execution_authority"] is False and model["is_RL"] is False
            and model["dev_labels_used_to_fit_or_choose_support"] is False, "TRAIN_only_demand_contract")
    require(sorted(parent["parent_group"] for parent in model["train_parent_calendars"]) == base["train_parent_ids"]
            and all(parent["split"] == "train" for parent in model["train_parent_calendars"]), "parent_calendar_binding")
    for intervals in model["support_by_station"].values():
        require(all(len(interval) == 2 and all(demand.finite(x) for x in interval)
                    and 0 <= interval[0] < interval[1] <= 86400. for interval in intervals), "finite_support_intervals")
        require(all(a[1] < b[0] for a, b in zip(intervals, intervals[1:])), "nonoverlapping_merged_support")
    return model


def transform(model, forecast, *, now, parent_id=None):
    """Runtime only; adjust expected arrivals within covered physical-time support."""
    validate_model(model)
    base = model["base_calibration"]
    calibrated = calibration.transform(base, forecast, now=now, parent_id=parent_id)
    result = copy.deepcopy(forecast)
    edges = forecast["bin_edges_seconds"]
    supported_mass, changed_mass = 0., 0.
    for station, values in forecast["new_demand_mean_by_region"].items():
        support = model["support_by_station"].get(station, [])
        adjusted = []
        for index, (left, right, value) in enumerate(zip(edges, edges[1:], values)):
            if value is None:
                adjusted.append(None)
                continue
            covered = math.fsum(max(0., min(now+right, end)-max(now+left, start)) for start, end in support)
            fraction = covered / (right-left)
            require(0 <= fraction <= 1.+1e-12, "bounded_support_overlap")
            replacement = value + (calibrated["new_demand_mean_by_region"][station][index]-value)*fraction
            adjusted.append(replacement)
            supported_mass += value*fraction
            changed_mass += replacement-value
        result["new_demand_mean_by_region"][station] = adjusted
    result = demand.rebin_forecast(result, bin_edges_seconds=edges)
    result["predictor_calibration"] = {"model_sha256": model["sha256"],
        "base_calibration_sha256": base["sha256"], "method": "TRAIN_time_support_bounded_Poisson_calibration",
        "available_at_epoch_seconds": base["model_available_at_epoch_seconds"],
        "training_labels_closed_at_epoch_seconds": base["training_labels_closed_at_epoch_seconds"],
        "prior_forecast_sha256": demand.digest(forecast), "support_derivation": model["support_derivation"],
        "outside_support": model["outside_support"], "supported_prior_mass": supported_mass,
        "mean_mass_adjustment": changed_mass, "native_execution_authority": False,
        "output_semantics": "expected_new_arrivals_only", "is_RL": False,
        "uncertainty_status": model["uncertainty_status"]}
    result["calibration_status"] = model["development_status"]
    return result
