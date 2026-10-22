"""Full TRAIN demand fitting stays mature, bound and separate from holdout labels."""
import copy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_full_training as training
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_support_predictor as supported


def sources():
    result = []
    for number, epoch in ((1, 100000.), (2, 200000.)):
        parent = {"parent_group": f"TRAIN:{number}:r0", "split": "train", "calendar_start_epoch_seconds": epoch}
        rows = []
        for origin in training.ORIGINS:
            for station in range(10):
                rows.append({"label_id": f"{number}:{origin}:{station}", "parent_id": parent["parent_group"],
                    "split": "train", "station": f"airport_node_{station}", "expected_arrivals": 1., "actual_arrivals": 2,
                    "interval_start_epoch_seconds": epoch+origin, "interval_end_epoch_seconds": epoch+origin+1800.,
                    "issued_at_epoch_seconds": epoch+origin, "label_available_at_epoch_seconds": epoch+59400.,
                    "provenance_kind": "actual_arrival_count", "label_status": "mature", "forecast_sha256": "forecast",
                    "source_evidence_id": f"source{number}", "base_model_sha256": "B1", "mapping_sha256": "mapping"})
        result.append({"parent": parent, "rows": rows, "end": 59400.,
            "source_bundle": {"path": "source", "sha256": "source"}, "mapping": {"path": "mapping", "sha256": "mapping"},
            "base_model_sha256": "B1", "pipeline_available_at_epoch_seconds": 99999.})
    return result


def test_complete_TRAIN_fits_580_windows_and_full_support_without_dev_data():
    model, rows = training.fit_complete_sources(sources())
    assert len(rows) == 580
    assert model["support_by_station"] == {f"airport_node_{station}": [[7200., 59400.]] for station in range(10)}
    base = model["base_calibration"]
    assert base["training_row_count"] == 580
    assert base["model_available_at_epoch_seconds"] == 259401.
    assert base["training_labels_closed_at_epoch_seconds"] == 259400.
    assert all(value["scale"] == 124./66. for value in base["parameters"].values())
    assert base["is_RL"] is False and base["native_execution_authority"] is False
    assert supported.validate_model(model) == model


@pytest.mark.parametrize("mutation,reason", [
    ("partial", "59400"), ("missing_window", "29_windows"), ("duplicate_window", "29_windows"),
    ("immature", "mature_window"), ("future_issue", "mature_window"), ("DEV", "TRAIN_only"),
    ("repeat_parent", "lineages"), ("different_source", "same_source_bundle"),
    ("different_mapping", "same_mapping"), ("different_B1", "same_B1"),
])
def test_complete_training_rejects_partial_leaky_or_unpaired_sources(mutation, reason):
    values = sources()
    if mutation == "partial": values[0]["end"] = 18000.
    elif mutation == "missing_window": values[0]["rows"].pop()
    elif mutation == "duplicate_window": values[0]["rows"].append(copy.deepcopy(values[0]["rows"][0]))
    elif mutation == "immature": values[0]["rows"][0]["label_available_at_epoch_seconds"] -= 1.
    elif mutation == "future_issue": values[0]["rows"][0]["issued_at_epoch_seconds"] += 1.
    elif mutation == "DEV": values[1]["parent"]["split"] = "dev"
    elif mutation == "repeat_parent": values[1]["parent"]["parent_group"] = "TRAIN:1:r1"
    elif mutation == "different_source": values[1]["source_bundle"]["sha256"] = "other"
    elif mutation == "different_mapping": values[1]["mapping"]["sha256"] = "other"
    elif mutation == "different_B1": values[1]["base_model_sha256"] = "other"
    with pytest.raises(ValueError, match=reason):
        training.fit_complete_sources(values)


def test_model_availability_is_explicit_and_cannot_precede_label_closure():
    with pytest.raises(ValueError, match="model_available_after"):
        training.fit_complete_sources(sources(), model_available_at_epoch_seconds=259399.)
    model, _ = training.fit_complete_sources(sources(), model_available_at_epoch_seconds=300000.)
    assert model["base_calibration"]["model_available_at_epoch_seconds"] == 300000.


@pytest.mark.parametrize("split", ["dev", "test"])
def test_cli_loader_rejects_holdout_before_opening_any_data_tape(tmp_path, split):
    (tmp_path/"plan.json").write_text(json.dumps({"parent": {"split": split}}), encoding="utf-8")
    with pytest.raises(ValueError, match="TRAIN_only_source"):
        training.load_training_source(tmp_path)


def test_fresh_candidate_artifact_contains_model_rows_and_frozen_dependencies(tmp_path, monkeypatch):
    values = sources()
    for value in values:
        value["provenance"] = {"native_arrival_count": 1, "source_evidence_id": "fixture"}
        value["actual_callback_count"] = 1742
    monkeypatch.setattr(training, "load_training_source", lambda path: values[int(path.name)])
    output = tmp_path/"candidate"
    result = training.run_training([tmp_path/"0", tmp_path/"1"], output)
    model = training.study.read(output/"model.json")
    evidence = training.study.read(output/"provenance.json")
    assert result["row_count"] == 580 and result["native_starts"] == 0
    assert result["model"]["sha256"] == training.study.sha(output/"model.json")
    assert evidence["training_labels_sha256"] == model["base_calibration"]["training_labels_sha256"]
    assert evidence["DEV_or_TEST_labels_read"] is False
    assert evidence["allocator_or_native_parameters_fitted"] is False
    assert len(training.study.read(output/"training_rows.json.gz")) == 580
    with pytest.raises(ValueError, match="fresh_output_directory"):
        training.run_training([tmp_path/"0", tmp_path/"1"], output)


def test_TRAIN_producer_source_cannot_change_during_fit(tmp_path, monkeypatch):
    values = sources()
    source_path = tmp_path/"producer.py"
    source_path.write_text("original", encoding="utf-8")
    monkeypatch.setattr(training, "producer_bindings", lambda: {"producer": training.study.bound(source_path)})
    def load(path):
        source_path.write_text("changed", encoding="utf-8")
        return values[int(path.name)]
    monkeypatch.setattr(training, "load_training_source", load)
    with pytest.raises(ValueError, match="producer_source_changed"):
        training.run_training([tmp_path/"0", tmp_path/"1"], tmp_path/"candidate")

