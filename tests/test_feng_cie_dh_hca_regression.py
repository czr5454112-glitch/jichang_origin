from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.eval import run_feng_paper_env_cie_dh as runner


ROOT = Path(__file__).resolve().parents[1]
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"


def test_frozen_legacy_identity_has_not_changed() -> None:
    observed = runner.verify_legacy_identity(
        map_path=LEGACY / "map2.txt",
        input_path=LEGACY / "inputdata.txt",
        legacy_root=LEGACY,
    )
    assert observed["map_sha256"] == runner.EXPECTED_MAP_SHA256
    assert observed["input_sha256"] == runner.EXPECTED_INPUT_SHA256
    assert observed["legacy_java_source_count"] == 15
    assert (
        observed["legacy_java_source_aggregate_sha256"]
        == runner.EXPECTED_LEGACY_SOURCE_AGGREGATE_SHA256
    )


def test_frozen_native_hca_full_population_regression() -> None:
    artifact = (
        ROOT
        / "outputs"
        / "runtime"
        / "feng_cie_dh_reconstruction"
        / "hca_regression.json"
    )
    observed = json.loads(artifact.read_text(encoding="utf-8"))
    assert observed["status"] == "FENG_NATIVE_HCA_REGRESSION_PASS"
    assert observed["fresh_rerun"] is True
    assert observed["comparison_eligible"] is True
    assert observed["legacy_scheduler_modified"] is False
    assert observed["segment_count"] == 43_603
    assert observed["completed_segment_count"] == 43_603
    assert observed["raw_bag_count"] == 28_506
    assert observed["completed_raw_bag_count"] == 28_506
    assert observed["survivor_timing_used"] is False
    assert observed["processed_attempt_seconds"]["min"] == 188.0
    assert observed["processed_attempt_seconds"]["mean"] == 236.710166280783
    assert observed["processed_attempt_seconds"]["max"] == 357.0
    assert observed["route_size_checksum"] == "475106"
    assert observed["route_location_checksum"] == "103288132"
    assert (
        observed["stable_aggregate_projection_sha256"]
        == "165cc039f274412d886665616e854dfda3897adf21fa583120e6751344bf5189"
    )


def test_native_hca_build_entry_remains_parallel_to_reconstruction() -> None:
    from scripts.eval import run_g4irsf24_fresh_hca as hca_runner

    hca_sources = {path.resolve() for path in hca_runner._java_sources()}
    reconstruction_sources = {path.resolve() for path in runner.java_sources()}
    assert hca_sources.isdisjoint(reconstruction_sources)
    assert any(path.name == "LegacyIcsNoFaultWindowBenchmark.java" for path in hca_sources)
    assert all(
        "benchmarks/java/feng_cie_dh" not in path.relative_to(ROOT).as_posix()
        for path in hca_sources
    )


def test_primary_coefficients_are_physical_headway_not_table_fit() -> None:
    physics = runner.read_map_physics(LEGACY / "map2.txt")
    assert physics == {
        "vertex_count": 54,
        "agv_length_m": 1.0,
        "safe_length_m": 0.0,
        "speed_mps": 2.5,
        "tick_seconds": 0.2,
        "movement_per_tick_m": 0.5,
        "headway_seconds": 0.4,
        "footprint_cells": 2,
    }
    alpha, beta = runner.coefficient_seconds(
        LEGACY / "map2.txt", alpha_scale=1.0, beta_over_alpha=2.0
    )
    assert alpha == pytest.approx(0.4)
    assert beta == pytest.approx(0.8)
    assert beta > alpha


def test_runner_command_uses_named_java_interface_and_original_inputs(tmp_path: Path) -> None:
    command = runner.java_run_command(
        java="java",
        classes_dir=tmp_path / "classes",
        map_path=LEGACY / "map2.txt",
        input_path=LEGACY / "inputdata.txt",
        output_dir=tmp_path / "run",
        alpha_seconds=0.4,
        beta_seconds=0.8,
        max_raw_bags=10,
        workload_scale=1.0,
        seed=0,
        horizon_seconds=0.0,
        trace_sample_modulo=17,
    )
    assert runner.MAIN_CLASS in command
    assert command[command.index(runner.MAIN_CLASS) + 1] == "run"
    assert command[command.index("--map") + 1] == str((LEGACY / "map2.txt").resolve())
    assert command[command.index("--input") + 1] == str(
        (LEGACY / "inputdata.txt").resolve()
    )
    assert command[command.index("--alpha") + 1] == "0.40000000000000002"
    assert command[command.index("--beta") + 1] == "0.80000000000000004"
    assert command[command.index("--limit") + 1] == "10"
    assert command[command.index("--trace-sample-modulo") + 1] == "17"
    assert command[command.index("--formal-timing-eligible") + 1] == "true"


def test_resume_requires_exact_command_and_identity(tmp_path: Path) -> None:
    output = tmp_path / "run"
    output.mkdir()
    (output / "summary.csv").write_text("status\nCOMPLETE\n", encoding="utf-8")
    command = ["java", "App.FengDhBenchmark", "run"]
    identity = {"source": "abc", "horizon_seconds": 98_259.0}
    (output / "runner_status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "returncode": 0,
                "command": command,
                "identity": identity,
            }
        ),
        encoding="utf-8",
    )
    assert runner._completed(output, command=command, identity=identity)
    assert not runner._completed(
        output, command=[*command, "--different"], identity=identity
    )
    assert not runner._completed(
        output, command=command, identity={**identity, "source": "changed"}
    )


def test_external_workload_cannot_fall_back_to_until_complete(tmp_path: Path) -> None:
    identity_path = tmp_path / "identity.json"
    identity_path.write_text(
        json.dumps(
            {
                "schema": "czr005.cie_external_baseline_workload.v1",
                    "raw_path": str((LEGACY / "inputdata.txt").resolve()),
                    "raw_sha256": runner.EXPECTED_INPUT_SHA256,
                    "map_path": str((LEGACY / "map2.txt").resolve()),
                    "map_sha256": runner.EXPECTED_MAP_SHA256,
                    "storage_in_goal": 47,
                    "storage_out_start": 52,
                    "seed": 0,
                "load_factor": 1.0,
                "raw_bag_count": 28_506,
                "segment_count": 43_603,
                "fixed_horizon_seconds": runner.FIXED_EXTERNAL_HORIZON_SECONDS,
            }
        ),
        encoding="utf-8",
    )
    args = SimpleNamespace(
        map_path=LEGACY / "map2.txt",
        input_path=LEGACY / "inputdata.txt",
        legacy_root=LEGACY,
        allow_external_workload=True,
        external_workload_identity=identity_path,
        seed=0,
        workload_scale=1.0,
        horizon_seconds=0.0,
        max_raw_bags=0,
        trace_sample_modulo=0,
        classes_dir=tmp_path / "classes",
        java="java",
        force=False,
        timeout_seconds=0,
        dry_run=True,
    )
    with pytest.raises(runner.FengDhRunError, match="98259-second horizon"):
        runner._run_one(args, alpha_scale=1.0, beta_ratio=2.0, output=tmp_path / "out")


def test_sensitivity_grid_is_frozen_complete_and_contains_primary() -> None:
    manifest = runner._load_manifest()
    coefficients = manifest["routing"]["coefficients"]
    alpha = coefficients["sensitivity"]["alpha_scales"]
    ratio = coefficients["sensitivity"]["beta_over_alpha"]
    cells = {(float(a), float(b)) for a in alpha for b in ratio}
    assert len(cells) == 9
    assert (1.0, 2.0) in cells
    assert coefficients["frozen_before_formal_run"] is True
    assert coefficients["paper_table_used_as_tuning_target"] is False
