from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.eval import aggregate_cie_potential_factorial as aggregate


def _payload(
    *,
    policy: str,
    potential: str,
    dynamic: str,
    mean: float,
    complete: bool = True,
) -> dict[str, object]:
    completed_bags = 10 if complete else 8
    completed_segments = 14 if complete else 12
    return {
        "schema": aggregate.SCHEMA,
        "native_execution_started": True,
        "status": "COMPLETE" if complete else "FAILED_INTEGRITY",
        "map": "map2",
        "scale": 1,
        "population": {"raw_bag_count": 10, "segment_count": 14},
        "release_protocol": {"mode": "same_hca"},
        "binary": {"sha256": "abc"},
        "provenance": {"workload_sha256": "workload"},
        "algorithm": {
            "policy": policy,
            "policy_label": (
                "G31_S4_NEUTRAL_FIFO"
                if policy == "s4"
                else "CIE_DH_COMMON_EXECUTOR_ADAPTED_NOT_EXACT"
            ),
            "dynamic": dynamic,
            "cell_id": "cell",
            "coordination_protocol": "neutral_fifo",
        },
        "potential": {
            "selected": potential,
            "selected_label": "H_FF" if potential == "ff" else "H_SA",
        },
        "execution_integrity": {"pass": complete},
        "paper_subjects": {
            "fixed_horizon_capacity": {
                "denominator_raw_bags": 10,
                "completed_raw_bag_count": completed_bags,
                "completion_rate": completed_bags / 10,
            },
            "full_population_raw_bag_timing": {
                "status": (
                    "FULL_POPULATION_RAW_BAG_TIMING"
                    if complete
                    else "NOT_MEASURED_FULL_POPULATION_INCOMPLETE"
                ),
                "raw_bag_count": 10 if complete else None,
                "survivor_or_common_cohort_used": False,
                "metrics_seconds": (
                    {
                        "paper_network_from_admission": {
                            "mean": mean,
                            "p95": mean + 5,
                            "p99": mean + 9,
                            "max": mean + 12,
                        }
                    }
                    if complete
                    else None
                ),
            },
        },
        "runtime": {
            "wall_seconds": mean / 10,
            "cpu_seconds": mean / 11,
            "native_summary": {"completed_count": completed_segments},
        },
    }


def _write(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_factorial_effects_and_adaptation_are_kept_separate(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    means = {
        ("ff", "off"): 100.0,
        ("sa", "off"): 90.0,
        ("ff", "full"): 80.0,
        ("sa", "full"): 60.0,
    }
    for (potential, dynamic), mean in means.items():
        _write(
            inputs / f"s4_{potential}_{dynamic}.json",
            _payload(
                policy="s4", potential=potential, dynamic=dynamic, mean=mean
            ),
        )
    _write(
        inputs / "dh_ff.json",
        _payload(policy="cie_dh", potential="ff", dynamic="full", mean=105.0),
    )
    _write(
        inputs / "dh_sa.json",
        _payload(policy="cie_dh", potential="sa", dynamic="full", mean=95.0),
    )

    long_csv = tmp_path / "runs.csv"
    effects_csv = tmp_path / "effects.csv"
    report = tmp_path / "report.md"
    count, figure_status = aggregate.aggregate(
        [inputs], long_csv, effects_csv, report, None
    )

    assert count == 6
    assert figure_status == "NOT_REQUESTED"
    effects = list(csv.DictReader(effects_csv.open(encoding="utf-8")))
    latency = next(
        row
        for row in effects
        if row["map"] == "map2"
        and row["scale"] == "1"
        and row["policy"] == "s4"
        and row["metric"] == "population_latency_mean_seconds"
    )
    assert latency["comparison_status"] == "COMPLETE"
    assert float(latency["potential_main_effect_sa_minus_ff"]) == pytest.approx(-15)
    assert float(latency["dynamic_main_effect_full_minus_off"]) == pytest.approx(-25)
    assert float(latency["interaction_difference_in_differences"]) == pytest.approx(-10)
    adaptation = next(
        row
        for row in effects
        if row["map"] == "map2"
        and row["scale"] == "1"
        and row["policy"] == "cie_dh"
        and row["metric"] == "population_latency_mean_seconds"
    )
    assert adaptation["comparison_status"] == "COMPLETE"
    assert float(adaptation["adaptation_contrast_sa_minus_ff"]) == pytest.approx(-10)
    assert adaptation["potential_main_effect_sa_minus_ff"] == ""
    text = report.read_text(encoding="utf-8")
    assert "not native Feng DH" in text
    assert "cross-protocol ranking" in text


def test_missing_cell_and_incomplete_timing_remain_explicit(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for potential, dynamic, mean, complete in (
        ("ff", "off", 100.0, True),
        ("sa", "off", 90.0, True),
        ("ff", "full", 80.0, False),
    ):
        _write(
            inputs / f"{potential}_{dynamic}.json",
            _payload(
                policy="s4",
                potential=potential,
                dynamic=dynamic,
                mean=mean,
                complete=complete,
            ),
        )
    long_csv = tmp_path / "runs.csv"
    effects_csv = tmp_path / "effects.csv"
    report = tmp_path / "report.md"
    aggregate.aggregate([inputs], long_csv, effects_csv, report, None)

    runs = list(csv.DictReader(long_csv.open(encoding="utf-8")))
    incomplete = next(row for row in runs if row["dynamic"] == "full")
    assert incomplete["population_latency_mean_seconds"] == ""
    assert incomplete["full_population_complete"] == "False"
    effects = list(csv.DictReader(effects_csv.open(encoding="utf-8")))
    latency = next(
        row
        for row in effects
        if row["map"] == "map2"
        and row["scale"] == "1"
        and row["policy"] == "s4"
        and row["metric"] == "population_latency_mean_seconds"
    )
    assert latency["comparison_status"] == "MISSING_CELLS"
    assert latency["missing_cells"] == "sa/full"


def test_empty_directory_writes_headers_and_honest_report(tmp_path: Path) -> None:
    inputs = tmp_path / "empty"
    inputs.mkdir()
    long_csv = tmp_path / "runs.csv"
    effects_csv = tmp_path / "effects.csv"
    report = tmp_path / "report.md"

    count, _ = aggregate.aggregate([inputs], long_csv, effects_csv, report, None)

    assert count == 0
    assert len(list(csv.DictReader(long_csv.open(encoding="utf-8")))) == 0
    effects = list(csv.DictReader(effects_csv.open(encoding="utf-8")))
    assert effects
    assert {row["comparison_status"] for row in effects} == {"MISSING_CELLS"}
    assert "Executed input runs discovered: **0**" in report.read_text(
        encoding="utf-8"
    )


def test_legacy_two_x_latency_is_rejected_by_protocol(tmp_path: Path) -> None:
    payload = _payload(
        policy="s4", potential="sa", dynamic="full", mean=70.0
    )
    payload["scale"] = 2
    path = tmp_path / "legacy_two_x.json"
    _write(path, payload)

    row = aggregate._run_row(path, payload)

    assert row["timing_status"] == "REJECTED_2X_TIMING_BY_PROTOCOL"
    assert row["population_latency_mean_seconds"] is None
