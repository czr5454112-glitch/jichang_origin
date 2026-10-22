"""Saved-observation evaluation keeps model fitting and mature DEV labels apart."""
import copy
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_forecast_holdout as holdout
from test_g31_terminal_predictor import base, fit


def fixture():
    model, raw = fit(), base()
    raw["calendar_provenance"].update(actual_callback_consumption=True, forecast_provenance="actual_callback_received")
    plan = {"parent": {"parent_group": "parent_dev:r0", "split": "dev", "calendar_start_epoch_seconds": 2200.}}
    observation = {"now": raw["forecast_origin"], "owner_id": "A"}
    evidence = {"forecast": raw, "forecast_sha256": holdout.audit.public_digest(raw), "model_available_at_epoch_seconds": 1000.}
    return model, raw, plan, observation, lambda **_: evidence


def test_replayed_prediction_does_not_claim_original_C00_actor_consumed_it(monkeypatch):
    model, raw, plan, observation, provider = fixture()
    before = copy.deepcopy(raw)
    monkeypatch.setattr(holdout.calibration, "fit", lambda *a, **kw: pytest.fail("DEV must not fit"))
    predictions = holdout.predict_saved_observation(plan, observation, provider, model)
    assert raw == before
    for value in predictions.values():
        assert value["calendar_provenance"]["actual_callback_consumption"] is False
        assert value["calendar_provenance"]["forecast_provenance"] == "offline_replay_saved_public_observation"
        assert value["bin_edges_seconds"] == holdout.demand.bin_edges("300")
    assert predictions["TF-predictor"]["new_demand_mean_by_region"] != predictions["TF-B1-300"]["new_demand_mean_by_region"]


def test_DEV_label_change_changes_only_scores_not_frozen_predictions():
    model, _, plan, observation, provider = fixture()
    predictions = holdout.predict_saved_observation(plan, observation, provider, model)
    records = [{"parent_id": "parent_dev:r0", "split": "dev", "predictions": predictions}]
    before = holdout.demand.digest(records)
    source = {"physical_clock": 59400., "source_evidence_id": "mature_native_receipts"}
    first, _ = holdout.score_mature_labels(records, model, parent=plan["parent"], arrivals={}, source=source)
    second, evaluated = holdout.score_mature_labels(records, model, parent=plan["parent"],
        arrivals={"airport_node_0": [200.]}, source=source)
    assert first["label_count"] == second["label_count"] == 3
    assert first["methods"] != second["methods"]
    assert holdout.demand.digest(records) == before
    assert all(row["actual_arrivals"] == 1 for row in evaluated[0]["labels"])


@pytest.mark.parametrize("split", ["test", "train"])
def test_non_DEV_source_rejected_before_any_tape_is_opened(tmp_path, split):
    (tmp_path/"plan.json").write_text(json.dumps({"parent": {"split": split}}), encoding="utf-8")
    with pytest.raises(ValueError, match="DEV_only"):
        holdout.build_public_predictions(tmp_path, fit())


def test_unavailable_model_cannot_be_evaluated_at_earlier_saved_origin():
    model, raw, plan, observation, provider = fixture()
    raw["calendar_provenance"]["calendar_start_epoch_seconds"] = 0.
    with pytest.raises(ValueError, match="available_at_callback"):
        holdout.predict_saved_observation(plan, observation, provider, model)


def test_partial_label_source_rejected():
    model, _, plan, _, _ = fixture()
    with pytest.raises(ValueError, match="complete_DEV_labels"):
        holdout.score_mature_labels([], model, parent=plan["parent"], arrivals={}, source={"physical_clock": 18000.})


def test_failed_public_prediction_validation_never_opens_DEV_labels(tmp_path, monkeypatch):
    model_path = tmp_path/"model.json"
    model_path.write_text(json.dumps(fit()), encoding="utf-8")
    def reject(*args):
        raise ValueError("bad_public_observation")
    monkeypatch.setattr(holdout, "build_public_predictions", reject)
    monkeypatch.setattr(holdout.study, "load_closed_run", lambda *a, **k: pytest.fail("labels opened before public predictions"))
    with pytest.raises(ValueError, match="bad_public_observation"):
        holdout.run(tmp_path, model_path, tmp_path/"report")


def test_changed_model_file_during_DEV_evaluation_is_rejected(tmp_path, monkeypatch):
    model, _, plan, observation, provider = fixture()
    model_path = tmp_path/"model.json"
    model_path.write_text(json.dumps(model), encoding="utf-8")
    predictions = holdout.predict_saved_observation(plan, observation, provider, model)
    records = [{"parent_id": "parent_dev:r0", "split": "dev", "predictions": predictions}]
    def build(*args):
        model_path.write_text(json.dumps(model)+"\n", encoding="utf-8")
        return plan, records, {}
    monkeypatch.setattr(holdout, "build_public_predictions", build)
    monkeypatch.setattr(holdout.study, "load_closed_run", lambda *a, **k: (plan, {},
        {"physical_clock": 59400., "source_evidence_id": "labels"}))
    with pytest.raises(ValueError, match="frozen_model_unchanged"):
        holdout.run(tmp_path, model_path, tmp_path/"report")


def test_report_source_edit_cannot_be_misattributed_to_running_old_code(tmp_path, monkeypatch):
    model, _, plan, observation, provider = fixture()
    model_path, source_path = tmp_path/"model.json", tmp_path/"producer.py"
    model_path.write_text(json.dumps(model), encoding="utf-8")
    source_path.write_text("original", encoding="utf-8")
    monkeypatch.setattr(holdout, "producer_bindings", lambda: {"producer": holdout.study.bound(source_path)})
    predictions = holdout.predict_saved_observation(plan, observation, provider, model)
    def build(*args):
        source_path.write_text("edited while running", encoding="utf-8")
        return plan, [{"parent_id": "parent_dev:r0", "split": "dev", "predictions": predictions}], {}
    monkeypatch.setattr(holdout, "build_public_predictions", build)
    monkeypatch.setattr(holdout.study, "load_closed_run", lambda *a, **k: (plan, {},
        {"physical_clock": 59400., "source_evidence_id": "labels"}))
    with pytest.raises(ValueError, match="producer_source_changed"):
        holdout.run(tmp_path, model_path, tmp_path/"report")

