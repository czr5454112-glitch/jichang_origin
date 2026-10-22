"""TRAIN-derived time support prevents calibration extrapolation to unseen hours."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_support_predictor as supported
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_forecast as demand
from test_g31_terminal_predictor import base, row


def model():
    return supported.fit([row()], train_parents=[{"parent_group": "parent_train:r0", "split": "train",
                          "calendar_start_epoch_seconds": 100.}],
        training_labels_closed_at_epoch_seconds=2000., model_available_at_epoch_seconds=2100.,
        bin_edges_seconds=demand.bin_edges("300"))


def current(now):
    forecast = base()
    forecast["forecast_origin"] = now
    return demand.rebin_forecast(forecast, bin_edges_seconds=demand.bin_edges("300"))


def test_support_is_derived_from_mature_training_windows_only():
    value = model()
    assert value["support_by_station"] == {"airport_node_0": [[0., 1800.]]}
    assert value["dev_labels_used_to_fit_or_choose_support"] is False
    assert value["base_calibration"]["parameters"]["airport_node_0"]["scale"] == 48./28.


def test_after_training_support_every_bin_returns_original_B1_exactly():
    value, forecast = model(), current(1800.)
    result = supported.transform(value, forecast, now=1800., parent_id="parent_dev:r0")
    assert result["new_demand_mean_by_region"] == forecast["new_demand_mean_by_region"]
    assert result["predictor_calibration"]["mean_mass_adjustment"] == 0.
    assert result["predictor_calibration"]["supported_prior_mass"] == 0.
    assert result["predictor_calibration"]["native_execution_authority"] is False


def test_bin_cutting_support_boundary_blends_only_covered_duration():
    value, forecast = model(), current(1740.)
    result = supported.transform(value, forecast, now=1740., parent_id="parent_dev:r0")
    first = forecast["new_demand_mean_by_region"]["airport_node_0"][0]
    values = result["new_demand_mean_by_region"]["airport_node_0"]
    assert values[0] == pytest.approx(first*(1.+(48./28.-1.)*60./300.))
    assert values[1:] == forecast["new_demand_mean_by_region"]["airport_node_0"][1:]
    assert result["window_summaries_by_region"]["airport_node_0"]["300"]["mean"] == values[0]
    assert value == model()


def test_missing_forecast_is_not_imputed_by_supported_calibration():
    forecast = current(0.)
    forecast["new_demand_mean_by_region"]["airport_node_0"][0] = None
    forecast["missing_mask_by_region"]["airport_node_0"][0] = True
    result = supported.transform(model(), forecast, now=0., parent_id="parent_dev:r0")
    assert result["new_demand_mean_by_region"]["airport_node_0"][0] is None
    assert result["window_summaries_by_region"]["airport_node_0"]["300"] is None


def test_no_common_train_time_support_cannot_be_invented_from_one_parent():
    values = [row(), dict(row(), label_id="second", parent_id="second_train:r0")]
    parents = [{"parent_group": "parent_train:r0", "split": "train", "calendar_start_epoch_seconds": 100.},
               {"parent_group": "second_train:r0", "split": "train", "calendar_start_epoch_seconds": 0.}]
    with pytest.raises(ValueError, match="common_TRAIN"):
        supported.fit(values, train_parents=parents, training_labels_closed_at_epoch_seconds=2000.,
            model_available_at_epoch_seconds=2100., bin_edges_seconds=demand.bin_edges("300"))


@pytest.mark.parametrize("mutation", ["support_tamper", "same_lineage", "future_availability", "future_label"])
def test_supported_model_keeps_original_causal_and_lineage_guards(mutation):
    value, forecast, parent = model(), current(120.), "parent_dev:r0"
    if mutation == "support_tamper": value["support_by_station"]["airport_node_0"] = [[0., 86400.]]
    elif mutation == "same_lineage": parent = "parent_train:r1"
    elif mutation == "future_availability": forecast["calendar_provenance"]["calendar_start_epoch_seconds"] = 0.
    elif mutation == "future_label": value["base_calibration"]["latest_label_available_at_epoch_seconds"] = 9999.
    with pytest.raises(ValueError):
        supported.transform(value, forecast, now=120., parent_id=parent)
