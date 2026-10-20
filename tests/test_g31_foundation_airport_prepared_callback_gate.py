"""Actual historical-source parity using detached fixtures; never native."""
import copy
import json
from pathlib import Path

from scripts.experiments.g31_ics_circulation import foundation_airport_prepared_callback_gate as gate_module
from test_g31_foundation_airport_learning_public import record


def batch():
    row = record()
    for index in (2, 3):
        tray = copy.deepcopy(row["observation"]["trays"][0])
        tray["tray_id"] = "E"+str(index)
        row["observation"]["trays"].append(tray)
        proposal = copy.deepcopy(row["decision"]["intents"][0])
        proposal["tray_id"] = tray["tray_id"]
        row["decision"]["intents"].append(proposal)
    row["observation"]["node_contracts"][0]["actual_available"] = 3
    return row


def test_actual_batch_gate_once_preserves_no_plan_and_exact_historical_features(tmp_path, monkeypatch):
    row = batch()
    original = copy.deepcopy(row)
    calls = []
    prepare = gate_module.public.prepare_record
    def count(*args, **kwargs):
        calls.append(1)
        return prepare(*args, **kwargs)
    monkeypatch.setattr(gate_module.public, "prepare_record", count)
    hook = gate_module.make_no_plan_feature_gate(tmp_path/"gate", episode_id="fixture", episode_end=59400.)
    small = copy.deepcopy(row["decision"])
    small["intents"] = small["intents"][:2]
    assert hook(observation=row["observation"], decision=small, callback_sequence=1) is None
    receipt = hook(observation=row["observation"], decision=row["decision"], callback_sequence=2)
    assert receipt["status"] == "passed_actual_current_feature_equivalence", receipt
    report = json.loads(Path(receipt["artifact"]["path"]).read_bytes())
    assert report["feature_fields_exactly_equal"] and report["feature_matrix_build_count"] == 1
    assert report["actual_candidate_count"] == 3 and calls == [1]
    assert report["forecast_models_consumed"] == report["forward_calls"] == 0
    saved = json.loads(Path(report["full_input"]["path"]).read_bytes())
    assert saved["forecast"]["context_sha256"] is None
    assert saved["forecast"]["new_demand_mean_by_region"] == {}
    assert receipt["hook_total_wall_seconds"] >= report["hook_seconds_before_receipt_storage"]
    assert set(receipt["receipt_storage"]) == {
        "serialize_seconds", "write_seconds", "flush_seconds", "fsync_seconds", "hash_seconds", "bytes"}
    assert hook(observation=row["observation"], decision=row["decision"], callback_sequence=3) is None
    assert row == original


def test_invalid_current_is_reported_and_not_retried(tmp_path):
    row = batch()
    row["observation"]["jobs"][0]["arrival"] = 11.
    hook = gate_module.make_no_plan_feature_gate(tmp_path/"gate", episode_id="fixture", episode_end=59400.)
    receipt = hook(observation=row["observation"], decision=row["decision"], callback_sequence=1)
    assert receipt["status"] == "failed"
    report = json.loads(Path(receipt["artifact"]["path"]).read_bytes())
    assert "exception" in report
    assert hook(observation=row["observation"], decision=row["decision"], callback_sequence=2) is None
