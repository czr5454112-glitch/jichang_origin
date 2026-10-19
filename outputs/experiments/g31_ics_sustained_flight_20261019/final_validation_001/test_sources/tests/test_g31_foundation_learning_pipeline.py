import copy

import pytest

from scripts.experiments.g31_ics_circulation import run_learning_pipeline as pipeline


@pytest.fixture
def config():
    path = pipeline.ROOT / "configs/g31_ics_circulation/learning_pilot_v1.json"
    return pipeline.load_config(path)


@pytest.mark.parametrize("field,value", [
    ("runtime_mode", "realtime_async"), ("information_scope", "global_truth"),
    ("candidate_budget", 0), ("candidate_budget", 33), ("candidate_budget", True),
    ("complete_request_target_ms", 10000), ("run_id", "../old_run"),
    ("baseline", "unprotected"), ("scenario", "fabricated"),
    ("horizon_seconds", 86400), ("message_tape", "unregistered_fault"),
])
def test_configuration_rejects_unimplemented_or_weakened_contract(config, field, value):
    config[field] = value
    with pytest.raises(ValueError):
        pipeline.validate_config(config)


@pytest.mark.parametrize("field,value", [
    ("maximum_training_rows", 20001), ("maximum_transitions", 0),
    ("command_wall_seconds", float("inf")), ("training_wall_seconds", 7201),
])
def test_training_limits_are_not_silently_expanded(config, field, value):
    config["limits"][field] = value
    with pytest.raises(ValueError):
        pipeline.validate_config(config)


def test_strict_protection_is_not_replaced_with_tolerance(config):
    config["protection"]["tolerance"] = 0.001
    with pytest.raises(ValueError, match="strict_reference"):
        pipeline.validate_config(config)


def test_output_cannot_escape_workspace(config):
    config["output_root"] = "../outside_workspace"
    with pytest.raises(ValueError, match="inside_research_workspace"):
        pipeline.validate_config(config)


def test_dataset_budget_counts_actual_rows(tmp_path):
    path = tmp_path / "dataset.jsonl"
    path.write_text('{}\n\n{}\n', encoding="utf-8")
    assert pipeline._check_dataset_budget(path, 2) == 2
    with pytest.raises(ValueError, match="budget_exceeded"):
        pipeline._check_dataset_budget(path, 1)


def test_smoke_continues_offline_learning_after_native_failure(config, tmp_path, monkeypatch):
    calls = []

    def missing_native(settings, output):
        calls.append("baseline")
        raise RuntimeError("missing compiled artifact")

    def export(settings, output):
        calls.append("collect")
        return {"status": "completed", "manifest": {"dataset_path": "data.jsonl"}}

    def train(settings, output, dataset):
        calls.append("train")
        return {"status": "completed", "closed_loop_RL_trained": False}

    monkeypatch.setattr(pipeline, "baseline", missing_native)
    monkeypatch.setattr(pipeline, "collect", export)
    monkeypatch.setattr(pipeline, "train_ranker", train)
    result = pipeline.execute("smoke", config, tmp_path)
    assert calls == ["baseline", "collect", "train"]
    assert result["status"] == "partial_failure"
    assert not result["L1_certified"]
    assert result["stages"]["baseline"]["status"] == "failed"


def test_rl_command_preserves_explicit_unmet_gate(config, tmp_path):
    original = copy.deepcopy(config)
    result = pipeline.execute("train-rl", config, tmp_path)
    assert result["status"] == "blocked_L1_not_certified"
    assert result["missing_capabilities"]
    assert result["training_started"] is False
    assert config == original


def test_failed_data_collection_does_not_train(config, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "baseline", lambda settings, output: {"status": "completed"})

    def failed_collection(settings, output):
        raise ValueError("dataset identity changed")

    def forbidden_training(*arguments, **keywords):
        pytest.fail("Training must not run after dataset validation failed")

    monkeypatch.setattr(pipeline, "collect", failed_collection)
    monkeypatch.setattr(pipeline, "train_ranker", forbidden_training)
    result = pipeline.execute("smoke", config, tmp_path)
    assert result["status"] == "partial_failure"
    assert "train-ranker" not in result["stages"]


@pytest.mark.parametrize("process", [
    {"status": "exited", "exitcode": 1},
    {"status": "hard_timeout", "exitcode": 0},
])
def test_written_success_cannot_hide_failed_or_timed_out_process(process):
    assert pipeline.aggregate_result(process, {"status": "completed"}).startswith("unknown_process_")


def test_success_requires_actual_result():
    process = {"status": "exited", "exitcode": 0}
    assert pipeline.aggregate_result(process, None) == "unknown_missing_result"
    assert pipeline.aggregate_result(process, {"status": "completed"}) == "completed"


@pytest.mark.parametrize("status", ["failed", "partial_failure"])
def test_explicit_stage_failure_is_not_hidden_by_normal_failure_exit(status):
    assert pipeline.aggregate_result({"status": "exited", "exitcode": 1}, {"status": status}) == status


def test_worker_uses_registered_config_and_rejects_changed_live_file(config, tmp_path):
    path = tmp_path / "config.json"
    pipeline.write_json(path, config)
    registration = {"command": "collect", "config": config,
        "config_sha256": pipeline.hashlib.sha256(path.read_bytes()).hexdigest()}
    pipeline.write_json(tmp_path / "preregistered.json", registration)
    assert pipeline.registered_config(path, tmp_path, "collect") == config
    config["learner"]["epochs"] += 1
    pipeline.write_json(path, config)
    with pytest.raises(ValueError, match="configuration_changed"):
        pipeline.registered_config(path, tmp_path, "collect")


def test_completed_smoke_outputs_are_discoverable(config, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_input", lambda value: tmp_path)
    smoke = tmp_path / config["run_id"] / "smoke"
    pipeline.write_json(smoke / "receipt.json", {"status": "completed_first_round_smoke"})
    assert pipeline._stage_directory(config, "collect") == smoke / "collect"
    assert pipeline._stage_directory(config, "train-ranker") == smoke / "train-ranker"


def test_failed_smoke_is_not_implicitly_used_as_completed_artifact(config, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "resolve_input", lambda value: tmp_path)
    run = tmp_path / config["run_id"]
    pipeline.write_json(run / "smoke" / "receipt.json", {"status": "partial_failure"})
    assert pipeline._stage_directory(config, "collect") == run / "collect"
