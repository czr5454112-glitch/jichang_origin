"""Mature TRAIN demand labels and common-window evaluation boundaries."""
import copy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_predictor as predictor
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_forecast as demand
from test_g31_terminal_forecast import forecast


def row():
    return {"label_id": "label", "parent_id": "parent_train:r0", "split": "train",
        "station": "airport_node_0", "expected_arrivals": 20., "actual_arrivals": 40,
        "interval_start_epoch_seconds": 100., "interval_end_epoch_seconds": 1900.,
        "issued_at_epoch_seconds": 100., "label_available_at_epoch_seconds": 2000.,
        "provenance_kind": "actual_arrival_count", "label_status": "mature",
        "forecast_sha256": "forecast", "source_evidence_id": "native_receipts",
        "base_model_sha256": "B1", "mapping_sha256": "mapping"}


def fit(rows=None):
    return predictor.fit([row()] if rows is None else rows, train_parent_ids=["parent_train:r0"],
        training_labels_closed_at_epoch_seconds=2000., model_available_at_epoch_seconds=2100.,
        bin_edges_seconds=demand.bin_edges("300"))


def base():
    value = demand.rebin_forecast(forecast(), bin_edges_seconds=demand.bin_edges("300"))
    value.update(calendar_provenance={"calendar_start_epoch_seconds": 2200.},
                 model_sha256="B1", airport_mapping_sha256="mapping")
    return value


def test_fitted_calibration_changes_demand_only_with_current_availability_and_bound_grid():
    model, prior = fit(), base()
    result = demand.predictor_transform(model, prior, now=120.25, parent_id="parent_dev:r0")
    assert model["parameters"]["airport_node_0"]["scale"] == 48./28.
    assert result["new_demand_mean_by_region"]["airport_node_0"][0] == pytest.approx(15.*48./28.)
    assert result["predictor_calibration"]["is_RL"] is False
    assert result["native_execution_authority"] is False
    assert result["uncertainty_by_region"]["airport_node_0"] is None
    assert not ({"source", "physical_tray_id", "transfer_request", "allocation"} & set(result))
    assert prior == base()


@pytest.mark.parametrize("mutation", ["dev", "future", "overlap", "command_label", "future_issue", "binding"])
def test_training_causal_and_identity_gates(mutation):
    values = [row()]
    if mutation == "dev": values[0]["split"] = "dev"
    elif mutation == "future": values[0]["label_available_at_epoch_seconds"] = 2001.
    elif mutation == "overlap": values += [dict(row(), label_id="other")]
    elif mutation == "command_label": values[0]["provenance_kind"] = "transport_command"
    elif mutation == "future_issue": values[0]["issued_at_epoch_seconds"] = 101.
    elif mutation == "binding": values[0]["source_evidence_id"] = ""
    with pytest.raises(ValueError): fit(values)


@pytest.mark.parametrize("mutation", ["same_lineage", "clock", "unavailable", "mapping", "grid", "model_tamper"])
def test_runtime_rejects_unavailable_wrong_or_training_parent_model(mutation):
    model, prior, now, parent = fit(), base(), 120.25, "parent_dev:r0"
    if mutation == "same_lineage": parent = "parent_train:r1"
    elif mutation == "clock": now = 121.
    elif mutation == "unavailable": prior["calendar_provenance"]["calendar_start_epoch_seconds"] = 0.
    elif mutation == "mapping": prior["airport_mapping_sha256"] = "wrong"
    elif mutation == "grid": prior["bin_edges_seconds"] = demand.bin_edges("60")
    elif mutation == "model_tamper": model["parameters"]["airport_node_0"]["scale"] = 999.
    with pytest.raises(ValueError): predictor.transform(model, prior, now=now, parent_id=parent)


def record():
    prior = base()
    coarse = demand.rebin_forecast(prior, bin_edges_seconds=demand.bin_edges("600"))
    labels = [{"station": "airport_node_0", "window_seconds": w, "actual_arrivals": n,
               "label_available_at_epoch_seconds": 2200.+120.25+w, "source_evidence_id": "native_receipts"}
              for w, n in [(300, 15), (900, 120), (1800, 465)]]
    return {"parent_id": "parent_dev:r0", "split": "dev", "predictions": {"300": prior, "600": coarse},
            "labels": labels, "observed_through_epoch_seconds": 5000.}


def test_comparison_uses_identical_common_window_station_population():
    result = predictor.evaluate_common_windows([record()], model=fit())
    assert result["methods"]["300"]["300"]["mae"] == 0.
    assert result["methods"]["600"]["300"]["mae"] == 12.5
    assert result["methods"]["300"]["1800"]["mae"] == result["methods"]["600"]["1800"]["mae"] == 0.
    assert result["same_window_seconds"] == [300, 900, 1800]
    assert result["raw_bin_MAE_cross_width_claimed"] is False


@pytest.mark.parametrize("mutation", ["not_mature", "population", "TRAIN_lineage", "duplicate", "owner"])
def test_evaluation_rejects_mismatched_or_unmature_labels(mutation):
    value = record()
    if mutation == "not_mature": value["labels"][0]["label_available_at_epoch_seconds"] = 2200.
    elif mutation == "population": value["labels"].pop()
    elif mutation == "TRAIN_lineage": value["parent_id"] = "parent_train:r1"
    elif mutation == "owner": value["predictions"]["600"]["owner_scope"] = "B"
    values = [value, copy.deepcopy(value)] if mutation == "duplicate" else [value]
    with pytest.raises(ValueError): predictor.evaluate_common_windows(values, model=fit())


def test_missing_prediction_skips_same_population_for_every_method():
    value = record()
    value["predictions"]["600"]["new_demand_mean_by_region"]["airport_node_0"][0] = None
    value["predictions"]["600"]["missing_mask_by_region"]["airport_node_0"][0] = True
    result = predictor.evaluate_common_windows([value])
    for method in ("300", "600"):
        for window in ("300", "900", "1800"):
            assert result["methods"][method][window]["count"] == 0
            assert result["methods"][method][window]["skipped_common_missing"] == 1
