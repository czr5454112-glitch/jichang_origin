from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.eval import aggregate_cie_targeted_ablation as aggregate


def _artifact(
    *,
    map_name: str,
    arm: str,
    completed: int,
    on_time: int,
    binary_sha: str = "b" * 64,
    workload_sha: str | None = None,
) -> dict[str, object]:
    denominator = aggregate.targeted.REGISTERED_2X_RAW_BAG_COUNT
    missed = denominator - on_time
    workload_sha = workload_sha or (("m" if map_name == "map2" else "n") * 64)
    mask = aggregate.targeted.ARMS[arm]
    return {
        "schema": aggregate.targeted.SCHEMA,
        "status": "COMPLETE",
        "native_execution_started": True,
        "map": map_name,
        "scale": 2,
        "population": {
            "raw_bag_denominator": denominator,
            "segment_count": aggregate.targeted.REGISTERED_2X_SEGMENT_COUNT,
            "whole_population": True,
        },
        "algorithm": {
            "arm": arm,
            "s4_score_component_mask": mask,
            "static_potential": "H_SA",
        },
        "ablation_contract": {
            "identity_pass": True,
            "sole_permitted_algorithmic_delta": "s4_score_component_mask",
        },
        "execution_integrity": {"pass": True},
        "full_population_timing": {
            "status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
            "raw_bag_count": None,
            "survivor_or_common_cohort_used": False,
            "distributions": None,
        },
        "fixed_denominator_business": {
            "detailed": {
                "denominator_raw_bags": denominator,
                "completed_raw_bag_count": completed,
                "completion_rate": completed / denominator,
                "on_time_raw_bag_count": on_time,
                "on_time_rate": on_time / denominator,
                "missed_bag_count": missed,
                "missed_bag_rate": missed / denominator,
                "tardiness_seconds": {
                    "fixed_horizon_all_population_lower_bound": {
                        "sum": float(missed * 10),
                        "mean": float(missed * 10 / denominator),
                        "p95": float(missed),
                        "p99": float(missed + 1),
                    }
                },
                "backlog": {
                    "raw_bag_total": {
                        "backlog_area_seconds": float(missed * 100),
                        "peak_backlog": missed,
                        "end_backlog": denominator - completed,
                    }
                },
                "fixed_denominator": True,
                "survivor_or_common_cohort_used": False,
            }
        },
        "provenance": {
            "binary_sha256": binary_sha,
            "canonical_workload_sha256": workload_sha,
        },
        "runtime": {"wall_seconds": 10.0, "cpu_seconds": 9.0},
        "activation_telemetry": {
            "Q": {"counterfactual_raw_argmin_change_count": 123}
        },
    }


def _write_artifact(root: Path, payload: dict[str, object]) -> Path:
    arm = str(payload["algorithm"]["arm"])  # type: ignore[index]
    map_name = str(payload["map"])
    path = root / arm / f"{map_name}_2x.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_matrix_enumeration_keeps_missing_cells_na_and_selects_no_arm(
    tmp_path: Path,
) -> None:
    _write_artifact(
        tmp_path,
        _artifact(map_name="map2", arm="FULL_S4", completed=50_000, on_time=20_000),
    )
    _write_artifact(
        tmp_path,
        _artifact(
            map_name="map2", arm="FULL_MINUS_Q", completed=51_000, on_time=21_000
        ),
    )

    rows = aggregate.collect_rows(tmp_path)

    assert len(rows) == len(aggregate.MAPS) * len(aggregate.ARMS)
    assert {(row["map"], row["arm"]) for row in rows} == {
        (map_name, arm) for map_name in aggregate.MAPS for arm in aggregate.ARMS
    }
    missing = next(
        row
        for row in rows
        if row["map"] == "nanning" and row["arm"] == "FULL_MINUS_Q"
    )
    assert missing["cell_status"] == "MISSING_CELL"
    assert missing["completed_raw_bag_count"] == "NA"
    assert missing["tht_mean_seconds"] == "NA"
    assert missing["pre_feasibility_raw_argmin_is_final_action"] is False


def test_paired_difference_is_arm_minus_full_with_contract_checks(
    tmp_path: Path,
) -> None:
    _write_artifact(
        tmp_path,
        _artifact(map_name="map2", arm="FULL_S4", completed=50_000, on_time=20_000),
    )
    _write_artifact(
        tmp_path,
        _artifact(
            map_name="map2", arm="FULL_MINUS_Q", completed=51_000, on_time=21_000
        ),
    )

    pairs = aggregate.paired_rows(aggregate.collect_rows(tmp_path))
    effect = next(
        row
        for row in pairs
        if row["map"] == "map2"
        and row["arm"] == "FULL_MINUS_Q"
        and row["metric"] == "completed_raw_bag_count"
    )
    self_reference = next(
        row
        for row in pairs
        if row["map"] == "map2"
        and row["arm"] == "FULL_S4"
        and row["metric"] == "completed_raw_bag_count"
    )

    assert effect["comparison_status"] == "COMPLETE"
    assert effect["delta_arm_minus_full_s4"] == 1_000.0
    assert effect["binary_sha256_match"] is True
    assert effect["workload_sha256_match"] is True
    assert self_reference["comparison_status"] == "SELF_REFERENCE"
    assert self_reference["delta_arm_minus_full_s4"] == 0.0


def test_two_x_timing_remains_na_and_protocol_violation_is_rejected(
    tmp_path: Path,
) -> None:
    payload = _artifact(
        map_name="map2", arm="FULL_S4", completed=57_012, on_time=25_000
    )
    payload["full_population_timing"] = {
        "status": "FULL_POPULATION_RAW_BAG_TIMING",
        "raw_bag_count": 57_012,
        "survivor_or_common_cohort_used": False,
        "distributions": {"mean": 1.0},
    }
    _write_artifact(tmp_path, payload)

    row = next(
        row
        for row in aggregate.collect_rows(tmp_path)
        if row["map"] == "map2" and row["arm"] == "FULL_S4"
    )

    assert row["cell_status"] == "REJECTED_2X_TIMING_PROTOCOL_VIOLATION"
    assert row["tht_mean_seconds"] == "NA"
    assert row["tht_p95_seconds"] == "NA"
    assert row["tht_p99_seconds"] == "NA"


def test_outputs_use_literal_na_and_report_raw_argmin_boundary(
    tmp_path: Path,
) -> None:
    input_root = tmp_path / "runtime"
    _write_artifact(
        input_root,
        _artifact(map_name="map2", arm="FULL_S4", completed=50_000, on_time=20_000),
    )
    runs_csv = tmp_path / "runs.csv"
    paired_csv = tmp_path / "paired.csv"
    report = tmp_path / "report.md"

    complete, figure_status = aggregate.aggregate(
        input_root=input_root,
        runs_csv=runs_csv,
        paired_csv=paired_csv,
        report=report,
        figure=None,
    )

    assert complete == 1
    assert figure_status == "NOT_REQUESTED"
    with runs_csv.open(encoding="utf-8", newline="") as handle:
        run_rows = list(csv.DictReader(handle))
    missing = next(
        row
        for row in run_rows
        if row["map"] == "nanning" and row["arm"] == "FULL_S4"
    )
    assert missing["completed_raw_bag_count"] == "NA"
    assert all(row["tht_mean_seconds"] == "NA" for row in run_rows)
    text = report.read_text(encoding="utf-8")
    assert "No arm was selected" in text
    assert "not final-action changes" in text
    assert "no value is interpolated" in text


def test_business_figure_contains_both_maps_and_missing_gaps(
    tmp_path: Path,
) -> None:
    pytest.importorskip("matplotlib")
    _write_artifact(
        tmp_path,
        _artifact(map_name="map2", arm="FULL_S4", completed=50_000, on_time=20_000),
    )
    _write_artifact(
        tmp_path,
        _artifact(map_name="nanning", arm="FULL_S4", completed=49_000, on_time=19_000),
    )
    figure = tmp_path / "business.png"

    status = aggregate._write_figure(figure, aggregate.collect_rows(tmp_path))

    assert status == "WRITTEN"
    assert figure.exists()
    assert figure.stat().st_size > 0
