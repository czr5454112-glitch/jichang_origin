"""Standard registration checks using archived requests, without simulation."""
import gzip
import json
from pathlib import Path
import zipfile

import pytest

from scripts.eval import run_g31_standard as standard


def archived_request(map_name, aligned=False):
    campaign = standard.experiment.CAMPAIGN if map_name == "nanning" else standard.map2_experiment.CAMPAIGN
    arm = "g31_legacy_same_hca_release_001" if aligned else "g31_legacy_001"
    relative = (campaign / arm / "request.json.gz").relative_to(standard.ROOT)
    path = standard.ROOT / relative
    if path.is_file():
        return json.loads(gzip.decompress(path.read_bytes()))
    archive = standard.ROOT / "deliverables/g31_waiting_two_maps_review_20261023" / f"{map_name}_full_evidence.zip"
    with zipfile.ZipFile(archive) as handle:
        return json.loads(gzip.decompress(handle.read(relative.as_posix())))


@pytest.fixture
def fake_binary(tmp_path):
    # No binary is loaded. Explicit test path removes a Windows-only dependency
    # from pure request construction; all runtime controls are compared below.
    path = tmp_path / "native-request-fixture.pyd"
    path.write_bytes(b"request construction only")
    return path


def portable_request(request):
    normalized = standard.experiment.normalize(request)
    # These are loader locations, not algorithm/trace options. Nothing else,
    # including trace limits or any task field, is excluded from equality.
    return {key: value for key, value in normalized.items()
            if key not in ("expected_binary_path", "search_path")}


@pytest.mark.parametrize("map_name", standard.MAPS)
def test_explicit_legacy_matches_frozen_legacy_request(map_name, fake_binary):
    request, selection = standard.prepare_request(map_name, binary=fake_binary,execution_model="legacy_waiting")
    assert portable_request(request) == portable_request(archived_request(map_name))
    assert selection["selected_wait_estimator"] == "legacy"
    assert selection["is_standard_selection"] is False
    assert selection["matches_historical_profile"] is True
    assert selection["physics_default"] is False
    assert selection["mode_explicitly_selected"] is False
    assert selection["adoption_reason"] == "user_requested_legacy_restore"
    for mode, label in (("eta_calendar", "experimental_calendar_comparison"),
                        ("eta_flow", "experimental_flow_comparison")):
        comparison, chosen = standard.prepare_request(map_name, mode=mode, binary=fake_binary,execution_model="legacy_waiting")
        assert portable_request(comparison) == {**portable_request(request), "s4_wait_estimator": mode}
        assert chosen["selection_label"] == label
        assert chosen["is_standard_selection"] is False


@pytest.mark.parametrize("map_name", standard.MAPS)
def test_run_delegates_and_saves_separate_standard_evidence(map_name, fake_binary, tmp_path, monkeypatch):
    runner = standard.experiment if map_name == "nanning" else standard.map2_experiment
    captured = []
    def execute(args):
        captured.append(args)
        args.output.mkdir()
        with gzip.open(args.output / "request.json.gz", "wt", encoding="utf-8") as handle:
            json.dump({"s4_wait_estimator": args.s4_wait_estimator}, handle)
        standard.experiment.write(args.output / "manifest.json", {"historical_schema": "unchanged"})
    monkeypatch.setattr(runner, "run_native", execute)
    release = tmp_path / "generator.csv"
    release.write_text("fixture delegated without simulation", encoding="utf-8")
    output = tmp_path / "new-standard-run"
    args = standard.parser().parse_args(["run", "--map", map_name,"--execution-model","legacy_waiting", "--binary", str(fake_binary),
                                        "--output", str(output), "--same-hca-release", str(release)])
    standard.run(args)
    assert len(captured) == 1
    assert captured[0].s4_wait_estimator == "legacy"
    assert captured[0].same_hca_release == release
    saved = standard.experiment.read(output / "standard_selection.json")
    assert saved["execution_status"] == "completed"
    assert saved["config"] == standard.experiment.evidence(standard.DEFAULT_CONFIG)
    assert saved["entrypoint"] == standard.experiment.evidence(Path(standard.__file__))
    assert saved["same_hca_release"] == standard.experiment.evidence(release)
    assert standard.experiment.read(output / "manifest.json") == {"historical_schema": "unchanged"}


def test_existing_output_is_rejected_before_execution(tmp_path, monkeypatch):
    def prohibited(args):
        raise AssertionError("must reject existing output before executing")
    monkeypatch.setattr(standard.experiment, "run_native", prohibited)
    path = tmp_path / "old-run"
    path.mkdir()
    marker = path / "manifest.json"
    marker.write_text("keep historical bytes", encoding="utf-8")
    args = standard.parser().parse_args(["run", "--map", "nanning", "--output", str(path)])
    with pytest.raises(FileExistsError, match="preserve existing"):
        standard.run(args)
    assert marker.read_text(encoding="utf-8") == "keep historical bytes"


def test_unknown_json_mode_is_rejected(tmp_path):
    config = standard.load_config()
    assert config["s4_wait_estimator"] == "legacy"
    assert config["reference_review_commit"] == "a0b42fb6652bf048d9d2e5de047a750cdea53436"
    config["s4_wait_estimator"] = "unknown"
    path = tmp_path / "invalid-standard.json"
    standard.experiment.write(path, config)
    with pytest.raises(ValueError, match="unknown standard s4_wait_estimator"):
        standard.load_config(path)
