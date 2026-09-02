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


def _add_business_metrics(
    payload: dict[str, object], *, value: float, target_99_reached: bool = True
) -> None:
    paper_subjects = payload["paper_subjects"]
    assert isinstance(paper_subjects, dict)
    paper_subjects["fixed_denominator_business"] = {
        "denominator_raw_bags": 10,
        "completed_raw_bag_count": 10,
        "completion_rate": 1.0,
        "on_time_raw_bag_count": int(value),
        "on_time_rate": value / 10.0,
        "missed_bag_count": 10 - int(value),
        "missed_bag_rate": 1.0 - value / 10.0,
        "tardiness_seconds": {
            "fixed_horizon_all_population_lower_bound": {
                "sum": value * 100.0,
                "mean": value * 10.0,
                "p95": value * 12.0,
                "p99": value * 14.0,
                "max": value * 16.0,
            }
        },
        "completion_targets": {
            "time_to_90_percent": {
                "reached": True,
                "elapsed_from_first_arrival_seconds": value * 20.0,
            },
            "time_to_95_percent": {
                "reached": True,
                "elapsed_from_first_arrival_seconds": value * 30.0,
            },
            "time_to_99_percent": {
                "reached": target_99_reached,
                "elapsed_from_first_arrival_seconds": (
                    value * 40.0 if target_99_reached else None
                ),
            },
        },
        "backlog": {
            "raw_bag_total": {
                "backlog_area_seconds": value * 1000.0,
                "peak_backlog": int(value * 2),
                "end_backlog": int(value),
                "arrival_count": 100,
                "departure_count": 100 - int(value),
                "observation_end_seconds": 98_259.0,
                "last_event_time_seconds": 90_000.0,
                "backlog_area_method": "EVENT_STEP_INTEGRAL_THROUGH_OBSERVATION_END_V2",
                "area_includes_residual_to_observation_end": True,
            },
            "raw_bag_source_until_all_segments_admitted": {
                "backlog_area_seconds": value * 600.0,
                "peak_backlog": int(value * 3),
                "end_backlog": int(value + 1),
                "arrival_count": 100,
                "departure_count": 100 - int(value + 1),
                "observation_end_seconds": 98_259.0,
                "last_event_time_seconds": 90_000.0,
                "backlog_area_method": "EVENT_STEP_INTEGRAL_THROUGH_OBSERVATION_END_V2",
                "area_includes_residual_to_observation_end": True,
            },
            "raw_bag_network_after_all_segments_admitted": {
                "backlog_area_seconds": value * 400.0,
                "peak_backlog": int(value * 4),
                "end_backlog": int(value + 2),
                "arrival_count": 100,
                "departure_count": 100 - int(value + 2),
                "observation_end_seconds": 98_259.0,
                "last_event_time_seconds": 90_000.0,
                "backlog_area_method": "EVENT_STEP_INTEGRAL_THROUGH_OBSERVATION_END_V2",
                "area_includes_residual_to_observation_end": True,
            },
        },
        "fixed_horizon_seconds": 98_259.0,
        "fixed_denominator": True,
        "survivor_or_common_cohort_used": False,
    }
    runtime = payload["runtime"]
    assert isinstance(runtime, dict)
    native = runtime["native_summary"]
    assert isinstance(native, dict)
    native["cie_component_activation"] = {
        "counterfactual_scope": (
            "same_state_pre_feasibility_raw_scorer;"
            "full_mask15_vs_one_term_removed"
        ),
        "components": {
            "Q": {"counterfactual_raw_argmin_change_count": int(value)},
            "I": {"counterfactual_raw_argmin_change_count": int(value + 1)},
            "wc": {"counterfactual_raw_argmin_change_count": 0},
            "ws": {"counterfactual_raw_argmin_change_count": int(value + 2)},
        },
    }


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


def test_two_x_fixed_denominator_business_metrics_enter_factorial(
    tmp_path: Path,
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    values = {
        ("ff", "off"): 10.0,
        ("sa", "off"): 8.0,
        ("ff", "full"): 6.0,
        ("sa", "full"): 4.0,
    }
    for (potential, dynamic), value in values.items():
        payload = _payload(
            policy="s4", potential=potential, dynamic=dynamic, mean=70.0
        )
        payload["scale"] = 2
        _add_business_metrics(payload, value=value)
        _write(inputs / f"{potential}_{dynamic}.json", payload)

    long_csv = tmp_path / "runs.csv"
    effects_csv = tmp_path / "effects.csv"
    report = tmp_path / "report.md"
    aggregate.aggregate([inputs], long_csv, effects_csv, report, None)

    runs = list(csv.DictReader(long_csv.open(encoding="utf-8")))
    ff_off = next(
        row
        for row in runs
        if row["potential"] == "ff" and row["dynamic"] == "off"
    )
    assert ff_off["timing_status"] == "REJECTED_2X_TIMING_BY_PROTOCOL"
    assert ff_off["population_latency_mean_seconds"] == ""
    assert ff_off["business_on_time_raw_bag_count"] == "10"
    assert ff_off["business_fixed_horizon_tardiness_p99_seconds"] == "140.0"
    assert ff_off["business_time_to_99_percent_status"] == "REACHED"
    assert ff_off["business_raw_total_backlog_area_seconds"] == "10000.0"
    assert ff_off["business_raw_source_backlog_peak"] == "30"
    assert ff_off["business_raw_network_backlog_end"] == "12"
    assert (
        ff_off["pre_feasibility_component_raw_argmin_counterfactual_scope"]
        == "same_state_pre_feasibility_raw_scorer;full_mask15_vs_one_term_removed"
    )
    assert ff_off["pre_feasibility_component_raw_argmin_change_count_total"] == "33"

    effects = list(csv.DictReader(effects_csv.open(encoding="utf-8")))
    latency = next(
        row
        for row in effects
        if row["map"] == "map2"
        and row["scale"] == "2"
        and row["policy"] == "s4"
        and row["metric"] == "population_latency_mean_seconds"
    )
    assert latency["comparison_status"] == (
        "METRIC_NOT_AVAILABLE_FULL_POPULATION_REQUIRED"
    )
    business = next(
        row
        for row in effects
        if row["map"] == "map2"
        and row["scale"] == "2"
        and row["policy"] == "s4"
        and row["metric"] == "business_on_time_raw_bag_count"
    )
    assert business["comparison_status"] == "COMPLETE"
    assert float(business["potential_main_effect_sa_minus_ff"]) == pytest.approx(-2)
    assert float(business["dynamic_main_effect_full_minus_off"]) == pytest.approx(-4)
    assert float(business["interaction_difference_in_differences"]) == pytest.approx(0)
    component = next(
        row
        for row in effects
        if row["map"] == "map2"
        and row["scale"] == "2"
        and row["policy"] == "s4"
        and row["metric"]
        == "pre_feasibility_component_raw_argmin_change_count_total"
    )
    assert component["comparison_status"] == "COMPLETE"
    assert "not final-action changes" in report.read_text(encoding="utf-8")


def test_legacy_incomplete_backlog_area_is_corrected_before_aggregation(
    tmp_path: Path,
) -> None:
    payload = _payload(policy="s4", potential="ff", dynamic="off", mean=70.0)
    payload["scale"] = 2
    _add_business_metrics(payload, value=2.0)
    business = payload["paper_subjects"]["fixed_denominator_business"]
    backlog = business["backlog"]
    for metric in backlog.values():
        metric.pop("backlog_area_method")
        metric.pop("observation_end_seconds")
        metric.pop("area_includes_residual_to_observation_end")
    backlog["raw_bag_total"]["drain_time_seconds"] = 5.0
    backlog["raw_bag_source_until_all_segments_admitted"][
        "drain_time_seconds"
    ] = 3.0
    path = tmp_path / "legacy.json"
    _write(path, payload)

    row = aggregate._run_row(path, payload)
    expected = 2_000.0 + 2.0 * (98_259.0 - (82_403.72582 + 5.0))

    assert row["business_raw_total_backlog_area_legacy_seconds"] == 2_000.0
    assert row["business_raw_total_backlog_area_seconds"] == pytest.approx(expected)
    assert (
        row["business_raw_total_backlog_area_status"]
        == "EXACT_LEGACY_TAIL_CORRECTED_V1"
    )


def test_unreached_completion_target_is_blank_and_statused(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for potential, dynamic in aggregate.S4_CELLS:
        payload = _payload(
            policy="s4", potential=potential, dynamic=dynamic, mean=70.0
        )
        _add_business_metrics(
            payload,
            value=8.0,
            target_99_reached=(potential, dynamic) != ("sa", "full"),
        )
        _write(inputs / f"{potential}_{dynamic}.json", payload)

    long_csv = tmp_path / "runs.csv"
    effects_csv = tmp_path / "effects.csv"
    report = tmp_path / "report.md"
    aggregate.aggregate([inputs], long_csv, effects_csv, report, None)

    runs = list(csv.DictReader(long_csv.open(encoding="utf-8")))
    unreached = next(
        row
        for row in runs
        if row["potential"] == "sa" and row["dynamic"] == "full"
    )
    assert unreached["business_time_to_99_percent_status"] == "NOT_REACHED"
    assert unreached["business_time_to_99_percent_elapsed_seconds"] == ""

    effects = list(csv.DictReader(effects_csv.open(encoding="utf-8")))
    time_to_99 = next(
        row
        for row in effects
        if row["map"] == "map2"
        and row["scale"] == "1"
        and row["policy"] == "s4"
        and row["metric"] == "business_time_to_99_percent_elapsed_seconds"
    )
    assert time_to_99["comparison_status"] == (
        "METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED"
    )
    assert time_to_99["missing_cells"] == "sa/full"
