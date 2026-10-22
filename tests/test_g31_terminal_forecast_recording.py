"""Actor records bind transformed demand and every model availability cutoff."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_joint_campaign as campaign
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_forecast as demand
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_predictor as calibration
from scripts.experiments.g31_ics_circulation import foundation_airport_terminal_support_predictor as supported
from scripts.experiments.g31_ics_circulation.foundation_airport_batch_patch import digest
from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import bound
from scripts.experiments.g31_ics_circulation.foundation_airport_transport_allocation import DEFAULT_CONFIG
from test_g31_airport_joint_interface import two_sources
from test_g31_foundation_airport_joint_projection import forecast
from test_g31_terminal_transport_control import prepared
from test_g31_terminal_predictor import row


def fixture(tmp_path, method, model_kind):
    current, catalog, _ = prepared(two_sources())
    obs = current.observation
    raw = forecast(obs, {0: [.5]*30, 2: [1.]*30})
    raw.update(native_execution_authority=False, model_sha256="B1",
               calendar_provenance={"calendar_start_epoch_seconds": 2200.})
    evidence = {"forecast": raw, "forecast_sha256": digest(raw),
                "model_available_at_epoch_seconds": 1000., "model_id": "B1"}
    mapping_path = tmp_path/"mapping.json"
    mapping_path.write_text(json.dumps({"model_available_at_epoch_seconds": 2050.}), encoding="utf-8")
    model = None
    if model_kind:
        labels = [dict(row(), mapping_sha256="test_mapping")]
        arguments = dict(training_labels_closed_at_epoch_seconds=2000.,
            model_available_at_epoch_seconds=2100., bin_edges_seconds=demand.bin_edges("300"))
        model = (calibration.fit(labels, train_parent_ids=["parent_train:r0"], **arguments)
                 if model_kind == "plain" else supported.fit(labels, train_parents=[{
                     "parent_group": "parent_train:r0", "split": "train", "calendar_start_epoch_seconds": 100.}], **arguments))
        model_path = tmp_path/"model.json"
        model_path.write_text(json.dumps(model), encoding="utf-8")
    plan = dict(method=method, projection_horizon_seconds=600., transport_penalty=.01, minimum_gain=0.,
        task_id="pure", policy_version="pure-policy", parent={"calendar_start_epoch_seconds": 2200.,
        "parent_group": "parent_dev:r0"}, mapping=bound(mapping_path), transport_config=DEFAULT_CONFIG,
        recompute_period_seconds=60., forecast_bin_edges_seconds=demand.bin_edges("300" if "300" in method or model_kind else "60"),
        demand_model=bound(model_path) if model else None)
    return current, catalog, evidence, plan


@pytest.mark.parametrize("method,model_kind", [("TF-B1-60", None), ("TF-B1-300", None),
    ("TF-predictor", "plain"), ("TF-predictor", "supported")])
def test_recorded_identity_and_feature_availability_match_actor_forecast(tmp_path, method, model_kind):
    current, catalog, evidence, plan = fixture(tmp_path, method, model_kind)
    decisions = []
    actor = campaign.RecordingPolicy(plan, lambda **_: evidence, decisions, [])
    actor(current, catalog, policy_state={}, decision_context={"tick": 1})
    recorded = decisions[0]["forecast_binding"]
    assert recorded["source_forecast_sha256"] == evidence["forecast_sha256"] == digest(evidence["forecast"])
    assert recorded["forecast_sha256"] == digest(recorded["forecast"])
    assert recorded["forecast_transform"]["actor_forecast_sha256"] == recorded["forecast_sha256"]
    assert recorded["forecast_transform"]["demand_model_sha256"] == (actor.demand_model or {}).get("sha256")
    available = 2100. if model_kind else 2050.
    assert recorded["forecast_pipeline_available_at_epoch_seconds"] == available
    assert all(value["model_available_at"] == available for value in decisions[0]["candidate_features"].values())
    assert decisions[0]["model_available_at"] == available
    assert "source_forecast_sha256" not in evidence


def test_historical_C10_preserves_original_provider_evidence(tmp_path):
    current, catalog, evidence, plan = fixture(tmp_path, "C10", None)
    decisions = []
    actor = campaign.RecordingPolicy(plan, lambda **_: evidence, decisions, [])
    actor(current, catalog, policy_state={}, decision_context={"tick": 1})
    assert decisions[0]["forecast_binding"] == evidence
    assert decisions[0]["model_available_at"] == 2050.


@pytest.mark.parametrize("model_kind", [None, "plain", "supported"])
def test_published_metadata_fix_preserves_frozen_runtime003_selected_action_and_inner_forecast(tmp_path, model_kind):
    path = campaign.CYCLE/"sources/terminal_flow_runtime_003/scripts/experiments/g31_ics_circulation/foundation_airport_joint_campaign.py"
    assert path.is_file(), "This regression requires the immutable runtime003 execution source."
    spec = importlib.util.spec_from_file_location(
        "scripts.experiments.g31_ics_circulation._terminal_frozen_campaign_test", path)
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    method = "TF-predictor" if model_kind else "TF-B1-300"
    current, catalog, evidence, plan = fixture(tmp_path, method, model_kind)
    old_records, new_records = [], []
    old = frozen.RecordingPolicy(plan, lambda **_: copy.deepcopy(evidence), old_records, [])
    new = campaign.RecordingPolicy(plan, lambda **_: copy.deepcopy(evidence), new_records, [])
    old_choice = old(current, catalog, policy_state={}, decision_context={"tick": 1})
    new_choice = new(current, catalog, policy_state={}, decision_context={"tick": 1})
    # Solver wall-clock measurements naturally differ; plan_id and every
    # physical decision field must remain identical.
    old_choice["flow_plan"].pop("solve_seconds")
    new_choice["flow_plan"].pop("solve_seconds")
    assert old_choice == new_choice
    assert old_records[0]["forecast_binding"]["forecast"] == new_records[0]["forecast_binding"]["forecast"]
    assert old_records[0]["forecast_binding"]["forecast_sha256"] == evidence["forecast_sha256"]
    assert new_records[0]["forecast_binding"]["forecast_sha256"] == digest(new_records[0]["forecast_binding"]["forecast"])
