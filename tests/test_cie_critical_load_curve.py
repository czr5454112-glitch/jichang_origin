from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval import run_cie_critical_load_curve as curve


def _row(method: str, factor: float, *, complete: bool = True) -> dict[str, object]:
    population = curve.EXPECTED_POPULATIONS[factor][0]
    completed = population if complete else population - 3
    return {
        "method": method,
        "load_factor": f"{factor:.2f}",
        "raw_bag_denominator": population,
        "completed_raw_bag_count": completed,
        "completion_rate": completed / population,
        "on_time_rate": completed / population,
        "capacity_deficit_raw_bags": population - completed,
        "source_backlog_end": population - completed,
        "source_backlog_peak": 17,
        "source_backlog_auc_bag_seconds": 123.0,
        "network_backlog_auc_bag_seconds": 45.0,
        "total_backlog_auc_bag_seconds": 168.0,
        "time_to_95_percent_seconds": 10.0 if complete else None,
        "time_to_99_percent_seconds": 12.0 if complete else None,
        "full_population_timing_status": (
            "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
            if factor == 2.0
            else "FULL_POPULATION_PROCESSED_ATTEMPT_TIMING"
        ),
        "population_latency_mean_seconds": (
            210.55305735634744
            if method == "G31_S4_NATIVE_SYSTEM" and factor == 1.0
            else None
        ),
        "population_latency_p95_seconds": (
            247.20199999999022
            if method == "G31_S4_NATIVE_SYSTEM" and factor == 1.0
            else None
        ),
        "population_latency_p99_seconds": (
            254.049499999997
            if method == "G31_S4_NATIVE_SYSTEM" and factor == 1.0
            else None
        ),
        "population_latency_max_seconds": (
            279.20199999999386
            if method == "G31_S4_NATIVE_SYSTEM" and factor == 1.0
            else None
        ),
        "first_incomplete_load_factor": 2.0 if not complete else None,
        "completion_rate_curve_auc": 1.0,
        "capacity_deficit_rate_curve_area": 0.0,
    }


def test_frozen_ladder_and_horizon_are_the_paper_protocol() -> None:
    assert curve.LOAD_FACTORS == (1.0, 1.25, 1.5, 1.75, 2.0)
    assert curve.FIXED_HORIZON_SECONDS == 98_259.0
    assert curve.HCA_START_EPOCH + curve.HCA_MAX_EPOCHS - 1 == 98_259
    assert curve.EXPECTED_POPULATIONS[2.0] == (57_012, 87_206)


def test_selected_factors_defaults_to_complete_ladder() -> None:
    assert curve._selected_factors([]) == curve.LOAD_FACTORS
    assert curve._selected_factors([1.25, 1.75]) == (1.25, 1.75)


def test_report_keeps_two_x_timing_na_and_fixed_denominator() -> None:
    rows = [
        _row(method, factor, complete=not (method == curve.METHODS[0] and factor == 2.0))
        for method in curve.METHODS
        for factor in curve.LOAD_FACTORS
    ]
    report = curve._report(rows)
    assert "FORMAL_2X_TIMING_NA_BY_PROTOCOL" in report
    assert "no survivor or common-success cohort" in report
    assert "57009 / 57012" in report
    assert "98,259 s" in report
    assert "Shared processed-attempt timing under the original-business protocol" in report
    assert (
        "| G31_S4_NATIVE_SYSTEM | 1.00 | 210.5531 | 247.2020 | "
        "254.0495 | 279.2020 |"
    ) in report
    assert (
        "| G31_S4_NATIVE_SYSTEM | 2.00 | N/A | N/A | N/A | N/A |"
    ) in report


def test_default_g31_binary_is_the_repaired_build_location() -> None:
    assert curve.DEFAULT_G31_BINARY.name == "czr005_cpp.cp311-win_amd64.pyd"
    assert "nanning_ablation_gate_f_pybind" in curve.DEFAULT_G31_BINARY.as_posix()
    assert curve.EXPECTED_FINAL_G31_SHA256.startswith("b00fd178")
    assert curve.EXPECTED_FINAL_G31_SHA256.endswith("a91f5")
    assert curve.EXPECTED_FINAL_DH_SOURCE_SHA256.startswith("99bf695a")
    assert curve.EXPECTED_FINAL_DH_CLASS_SHA256.startswith("d611967f")


def test_identity_paths_are_per_load(tmp_path: Path) -> None:
    assert curve._identity_path(tmp_path, 1.0) != curve._identity_path(tmp_path, 2.0)
    assert "map2_1p00x" in curve._identity_path(tmp_path, 1.0).as_posix()
    assert "map2_2p00x" in curve._identity_path(tmp_path, 2.0).as_posix()


def test_g31_release_alignment_changes_only_pass_time() -> None:
    base = [
        {
            "segment_id": "7:direct",
            "task_id": 7,
            "pass_time": 8267.845453,
            "std": 9000.0,
            "start": 3,
            "goal": 49,
        },
        {
            "segment_id": "8:storage_out",
            "task_id": 8,
            "pass_time": 19500.0,
            "std": 22200.0,
            "start": 52,
            "goal": 49,
        },
    ]
    releases = {"7:direct": 8267.0, "8:storage_out": 19501.0}

    aligned, details = curve._align_g31_rows(base, releases)

    assert [row["pass_time"] for row in aligned] == [8267.0, 19501.0]
    assert details["only_permitted_input_field"] == "pass_time"
    assert details["non_pass_time_field_difference_count"] == 0
    assert details["pass_time_value_change_count"] == 2
    for before, after in zip(base, aligned):
        assert {k: v for k, v in before.items() if k != "pass_time"} == {
            k: v for k, v in after.items() if k != "pass_time"
        }
    assert all(
        curve._validate_g31_aligned_rows(base, aligned, releases).values()
    )


def test_g31_release_alignment_rejects_nonexact_segment_population() -> None:
    base = [{"segment_id": "7:direct", "task_id": 7, "pass_time": 1.0}]
    with pytest.raises(curve.CriticalLoadError, match="exactly cover"):
        curve._align_g31_rows(base, {"foreign": 1.0})


def test_g31_normalization_identity_preserves_base_identity() -> None:
    base = {
        "raw_sha256": "raw",
        "canonical_path": "base.jsonl",
        "canonical_sha256": "base-sha",
        "raw_bag_count": 2,
    }
    normalized = curve._g31_normalization_identity(
        base,
        {
            "execution_canonical_path": "aligned.jsonl",
            "execution_canonical_sha256": "aligned-sha",
        },
    )
    assert base["canonical_sha256"] == "base-sha"
    assert normalized["raw_sha256"] == "raw"
    assert normalized["canonical_path"] == "aligned.jsonl"
    assert normalized["canonical_sha256"] == "aligned-sha"


def test_formal_g31_1x_reproduction_gate(tmp_path: Path) -> None:
    reference = tmp_path / "formal.json"
    reference.write_text(
        json.dumps(
            {
                "paper_subjects": {
                    "full_population_raw_bag_timing": {
                        "metrics_seconds": {
                            "paper_network_from_admission": {"mean": 210.5}
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    rows = [
        {
            "method": "G31_S4_NATIVE_SYSTEM",
            "load_factor": "1.00",
            "population_latency_mean_seconds": 210.5000001,
        }
    ]
    assert curve._assert_formal_g31_1x_reproduction(
        rows, reference
    )["status"] == "PASS"
    rows[0]["population_latency_mean_seconds"] = 211.0
    with pytest.raises(curve.CriticalLoadError, match="does not reproduce"):
        curve._assert_formal_g31_1x_reproduction(rows, reference)


def test_dh_resume_is_delegated_to_identity_aware_core_runner(
    tmp_path: Path, monkeypatch,
) -> None:
    destination = curve._cell_root(tmp_path, 1.0) / "feng_env_dh"
    destination.mkdir(parents=True)
    (destination / "runner_status.json").write_text(
        '{"status":"complete","identity":{"stale":true}}\n', encoding="utf-8"
    )
    raw_path = tmp_path / "inputdata.txt"
    raw_path.write_text("header\n", encoding="utf-8")
    monkeypatch.setattr(
        curve,
        "_read_identity",
        lambda _root, _factor: {"raw_path": str(raw_path)},
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(curve, "_run_checked", lambda command: commands.append(list(command)))

    curve.run_dh(
        factors=(1.0,),
        runtime_root=tmp_path,
        classes_dir=tmp_path / "classes",
        force=False,
    )

    assert len(commands) == 2
    assert "compile" in commands[0]
    assert "run" in commands[1]
    assert "--force" not in commands[1]
