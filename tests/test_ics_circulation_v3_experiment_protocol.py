"""W0 entrypoint regression tests; no new algorithm-performance claims."""
from importlib import import_module
import json
from pathlib import Path

import pytest

from scripts.experiments.ics_circulation_v3 import audit_nanning, nanning_routing_benchmark
from scripts.experiments.ics_circulation_v3 import run_scene_configuration as configuration
from scripts.experiments.ics_circulation_v3.experiment_protocol import manifest_groups, write_new_json


RUNNERS = ("run_joint_control", "run_matched_phase3", "run_phase2_learning", "run_phase3_learning",
           "run_pilot", "run_prebalance", "run_prebalance_reference", "run_request_service",
           "run_routing_comparison", "run_scene_configuration")


def _json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _original(tmp_path, namespace="registered"):
    groups = {split: [f"v3_phase2:{namespace}_{split}:000"] for split in ("train", "validation", "test")}
    protocol = {**configuration.PROTOCOL, "smoke": True, "actual_counts": dict.fromkeys(groups, 1),
                "actual_expected_episode_calls": 12, "weights": configuration.COST_WEIGHTS}
    return (_json(tmp_path / "protocol.json", protocol),
            _json(tmp_path / "split_manifest.json", {"groups": groups}), groups)


@pytest.mark.parametrize("runner_name", RUNNERS)
@pytest.mark.parametrize("occupied_by", ("directory", "file"))
def test_every_runner_refuses_existing_records_before_execution(tmp_path, runner_name, occupied_by):
    runner = import_module(f"scripts.experiments.ics_circulation_v3.{runner_name}")
    output = tmp_path / "output"
    if occupied_by == "directory":
        output.mkdir()
        marker = output / "prior.json"
    else:
        marker = output
    marker.write_bytes(b"unchanged evidence")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        runner.run(output)
    assert marker.read_bytes() == b"unchanged evidence"


def test_map_defaults_are_bundled_and_audit_file_is_exclusive(tmp_path):
    bundled = Path(audit_nanning.__file__).parent / "fixtures/nanning_airport_profile.json"
    assert audit_nanning.DEFAULT_PROFILE == nanning_routing_benchmark.DEFAULT_PROFILE == bundled
    assert bundled.is_file()
    output = tmp_path / "audit.json"
    assert audit_nanning.main(["--output", str(output)]) == 0
    old = output.read_bytes()
    with pytest.raises(SystemExit):
        audit_nanning.main(["--output", str(output)])
    assert output.read_bytes() == old
    empty = tmp_path / "reserved.json"
    empty.touch()
    with pytest.raises(ValueError, match="cannot be overwritten"):
        write_new_json(empty, {})


def test_nanning_checks_output_and_profile_before_creating_directory(tmp_path):
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    marker = occupied / "prior"
    marker.write_text("kept")
    with pytest.raises(ValueError, match="cannot be overwritten"):
        nanning_routing_benchmark.benchmark(audit_nanning.DEFAULT_PROFILE, occupied)
    missing_output = tmp_path / "not_created"
    with pytest.raises(FileNotFoundError):
        nanning_routing_benchmark.benchmark(tmp_path / "missing.json", missing_output)
    assert not missing_output.exists() and marker.read_text() == "kept"
    with pytest.raises(ValueError):
        nanning_routing_benchmark.benchmark(audit_nanning.DEFAULT_PROFILE, missing_output, partition_counts=())
    assert not missing_output.exists()


def test_other_external_input_preflight_does_not_create_output(tmp_path, monkeypatch):
    learning = import_module("scripts.experiments.ics_circulation_v3.run_phase3_learning")
    matched = import_module("scripts.experiments.ics_circulation_v3.run_matched_phase3")
    monkeypatch.setattr(learning, "TRAINING", tmp_path / "missing_training")
    monkeypatch.setattr(matched, "LEARNING", tmp_path / "missing_models")
    for runner in (learning, matched):
        output = tmp_path / runner.__name__.split(".")[-1]
        with pytest.raises(FileNotFoundError):
            runner.run(output)
        assert not output.exists()


def test_explicit_reproduction_preserves_exact_groups_counts_and_no_new_samples(tmp_path, monkeypatch):
    reference, manifest, expected = _original(tmp_path / "old")
    monkeypatch.setattr(configuration, "BASE", tmp_path)
    scenes, protocol, record = configuration.prepare_configuration_run(
        mode="reproduce", reference_protocol=reference, reference_manifest=manifest)
    assert {split: [scene.source_group for scene in values] for split, values in scenes.items()} == expected
    assert protocol["actual_counts"] == dict.fromkeys(expected, 1)
    assert protocol["actual_expected_episode_calls"] == 12
    assert record["new_independent_source_count"] == record["new_confirmation_test_source_count"] == 0
    assert record["disjoint_from_recorded_prior_splits"] is False
    assert all(record["overlap_with_registered_history"].values())
    assert record["original_protocol"]["sha256"] and record["original_manifest"]["sha256"]


@pytest.mark.parametrize("changes", ({"smoke": True}, {"evaluation_namespace": "extra"}, {"training_manifest": "other.json"}))
def test_reproduction_cannot_override_original_sample_set(tmp_path, monkeypatch, changes):
    reference, manifest, _ = _original(tmp_path / "old")
    monkeypatch.setattr(configuration, "BASE", tmp_path)
    output = tmp_path / "no_output"
    with pytest.raises(ValueError, match="no overrides"):
        configuration.run(output, mode="reproduce", reference_protocol=reference, reference_manifest=manifest, **changes)
    assert not output.exists()


@pytest.mark.parametrize("bad", ({}, {"groups": {}}, {"groups": {"train": []}}, {"groups": {"train": ["same"], "test": ["same"]}}))
def test_empty_invalid_or_overlapping_manifest_is_not_a_freshness_certificate(bad):
    with pytest.raises(ValueError):
        manifest_groups(bad)


def test_wrong_reference_schema_and_count_fail_before_output_creation(tmp_path, monkeypatch):
    reference, manifest, _ = _original(tmp_path / "old")
    monkeypatch.setattr(configuration, "BASE", tmp_path)
    payload = json.loads(reference.read_text())
    for field, value, message in (("schema", "wrong", "schema"), ("actual_counts", {"train": 2, "validation": 1, "test": 1}, "counts")):
        _json(reference, {**payload, field: value})
        output = tmp_path / "no_output"
        with pytest.raises(ValueError, match=message):
            configuration.run(output, mode="reproduce", reference_protocol=reference, reference_manifest=manifest)
        assert not output.exists()


def test_development_reuse_is_recorded_without_a_fresh_claim(tmp_path, monkeypatch):
    groups = {split: [scene.source_group for scene in values] for split, values in configuration.configuration_scenes(smoke=True).items()}
    _json(tmp_path / "prior/split_manifest.json", {"groups": groups})
    monkeypatch.setattr(configuration, "BASE", tmp_path)
    _, protocol, record = configuration.prepare_configuration_run(smoke=True)
    assert protocol["experiment_mode"] == "development"
    assert record["disjoint_from_recorded_prior_splits"] is False
    assert record["claim"] == "development_replay_not_fresh_evidence"
    assert record["new_independent_source_count"] == 0


def test_fresh_confirmation_allows_explicit_train_reuse_but_blocks_any_prior_evaluation_source(tmp_path, monkeypatch):
    _, manifest, groups = _original(tmp_path / "prior")
    monkeypatch.setattr(configuration, "BASE", tmp_path)
    scenes, _, record = configuration.prepare_configuration_run(
        mode="fresh-confirmation", smoke=True, evaluation_namespace="fresh", training_manifest=manifest)
    assert [scene.source_group for scene in scenes["train"]] == groups["train"]
    assert record["new_confirmation_test_source_count"] == 4
    assert record["overlap_with_registered_history"]["train"] == groups["train"]
    # A test ID already used for development TRAINING is also contaminated.
    used = scenes["test"][0].source_group
    _json(tmp_path / "development/split_manifest.json", {"groups": {"train": [used]}})
    output = tmp_path / "rejected"
    with pytest.raises(ValueError, match="overlap registered"):
        configuration.run(output, mode="fresh-confirmation", smoke=True,
                          evaluation_namespace="fresh", training_manifest=manifest)
    assert not output.exists()


def test_reproduction_cli_runs_without_pseudo_leakage_and_records_zero_new_samples(tmp_path, monkeypatch):
    reference, manifest, _ = _original(tmp_path / "prior")
    monkeypatch.setattr(configuration, "BASE", tmp_path)
    monkeypatch.setattr(configuration, "source_hashes", lambda: {})
    def collect(scenes, output, split, **kwargs):
        rows, episodes = [], []
        for scene in scenes:
            rows.append({"source_group": scene.source_group, "split": split, "features": configuration._observable(scene),
                         "costs": dict.fromkeys(configuration.CONFIGURATION_IDS, 1.),
                         "outcomes": {name: {"all_bag_denominator": 1, "completed": 1, "uncompleted": 0, "on_time": 1}
                                      for name in configuration.CONFIGURATION_IDS}})
            episodes.extend({"status": "complete", "invariant_checks": 1, "episode_wall_ms": 0.} for _ in configuration.CONFIGURATION_IDS)
        return rows, episodes
    monkeypatch.setattr(configuration, "collect_episodes", collect)
    output = tmp_path / "reproduced"
    configuration.main(["--output", str(output), "--mode", "reproduce", "--reference-protocol", str(reference),
                        "--reference-manifest", str(manifest)])
    summary = json.loads((output / "summary.json").read_text())
    split = json.loads((output / "split_manifest.json").read_text())
    assert summary["episode_calls"] == 12 and summary["new_independent_source_count"] == 0
    assert split["disjoint_from_recorded_prior_splits"] is False
