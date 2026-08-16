from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf30_reporting as g30


def _workload() -> dict:
    return {
        "schema": g30.WORKLOAD_SCHEMA,
        "status": "COMPLETE",
        "protocol": g30.WORKLOAD_PROTOCOL,
        "scale": 3,
        "input_raw_task_count": 28_506,
        "input_expanded_segment_count": 43_603,
        "input_flight_count": 360,
        "raw_task_count": g30.FULL_RAW_BAGS,
        "expanded_segment_count": g30.FULL_SEGMENTS,
        "flight_count": 1_080,
        "original_flight_count": 360,
        "inserted_flight_count": 720,
        "inserted_flights_per_original": 2,
        "inserted_id_offsets": [28_506, 57_012],
        "stream_count": 13,
        "flight_key": ["STD", "end", "Unloader"],
        "stream_key": ["end", "Unloader"],
        "direct_raw_task_count": 40_227,
        "early_split_raw_task_count": 45_291,
        "raw_by_end": {"48": 18_918, "49": 39_903, "50": 26_697},
        "raw_by_loader": {
            "A1": 3_528,
            "B1": 8_616,
            "B2": 16_632,
            "C1": 13_599,
            "C2": 22_626,
            "D1": 7_755,
            "T": 12_762,
        },
        "raw_by_start": {
            "0": 9_600,
            "1": 9_579,
            "2": 9_597,
            "3": 14_661,
            "4": 14_661,
            "5": 14_658,
            "53": 12_762,
        },
        "raw_by_unloader": {
            "1": 28_413,
            "2": 26_973,
            "3": 12_192,
            "4": 9_417,
            "5": 8_523,
        },
        "expanded_by_start": {
            "0": 9_600,
            "1": 9_579,
            "2": 9_597,
            "3": 14_661,
            "4": 14_661,
            "5": 14_658,
            "52": 45_291,
            "53": 12_762,
        },
        "insertion_rule": {
            "manifest_shift": "EntryTime_and_STD_receive_the_same_delta",
            "nonterminal": "one_third_and_two_thirds_to_next_STD_in_same_stream",
            "terminal": (
                "lower_median_positive_stream_headway_times_one_third_and_"
                "two_thirds"
            ),
        },
        "lifecycle": {
            "bag_id_rule": (
                "original task_id retained; inserted cohort 1/2 uses its "
                "registered ID offset plus source row rank"
            ),
            "early_bag_threshold_seconds": 4_800.0,
            "segment_id_rule": "<task_id>:direct|storage_in|storage_out",
            "storage_in_goal": 47,
            "storage_out_lead_seconds": 2_700.0,
            "storage_out_start": 52,
        },
        "timing": {
            "time_compression": 1.0,
            "rolling_days": 1,
            "day_axis_seconds": 86_400.0,
            "earliest_entry_time": 8_267.845453,
            "latest_entry_time": 82_703.72582,
            "earliest_std": 22_200.0,
            "latest_std": 85_900.0,
        },
        "invariants": {
            "canonical_was_expanded_from_generated_raw": True,
            "categorical_manifest_is_copied_per_inserted_flight": True,
            "direct_count_is_exactly_3x": True,
            "early_split_count_is_exactly_3x": True,
            "end_counts_are_exactly_3x": True,
            "expanded_segment_count_is_exactly_3x": True,
            "flight_count_is_exactly_3x": True,
            "loader_counts_are_exactly_3x": True,
            "raw_task_count_is_exactly_3x": True,
            "same_24h_axis_no_time_compression": True,
            "slack_and_storage_class_are_preserved": True,
            "start_counts_are_exactly_3x": True,
            "unloader_counts_are_exactly_3x": True,
        },
    }


def _group(case_id: str) -> str:
    if case_id.startswith("t5_5_fault_"):
        return "fault"
    if case_id.startswith("t5_4_bias_"):
        return "observation_bias"
    return "stable_speed"


def _distribution(mean: float = 10.0) -> dict[str, float]:
    return {
        "min": mean * 0.8,
        "mean": mean,
        "p95": mean * 1.2,
        "p99": mean * 1.3,
        "max": mean * 1.5,
    }


def _native_timing(mean: float) -> dict:
    return {
        "status": g30.MEASURED,
        "population": "all_selected_raw_bags_complete",
        "raw_bag_count": g30.FULL_RAW_BAGS,
        "units": "seconds",
        "full_outcome_timing_comparison_allowed": True,
        "distributions": {
            "processed_attempt": {
                "count": g30.FULL_RAW_BAGS,
                "min_seconds": mean * 0.8 * 60.0,
                "mean_seconds": mean * 60.0,
                "p95_seconds": mean * 1.2 * 60.0,
                "p99_seconds": mean * 1.3 * 60.0,
                "max_seconds": mean * 1.5 * 60.0,
            }
        },
    }


def _native_case(
    case_id: str,
    *,
    completed: int = g30.FULL_RAW_BAGS,
    topology_upper: int | None = None,
    measured_mean: float | None = None,
) -> dict:
    timing_allowed = measured_mean is not None
    topology = (
        {"topology_reachable_raw_bag_upper_bound": topology_upper}
        if topology_upper is not None
        else None
    )
    return {
        "schema": g30.NATIVE_CASE_SCHEMA,
        "status": g30.g30_native.COMPLETE_OWN_SOURCE,
        "case_id": case_id,
        "case_group": _group(case_id),
        "workload_protocol": g30.WORKLOAD_PROTOCOL,
        "selection": {
            "mode": "full",
            "selected_raw_bag_count": g30.FULL_RAW_BAGS,
            "selected_segment_count": g30.FULL_SEGMENTS,
        },
        "fixed_horizon": {
            "required": True,
            "pass": True,
            "expected_max_simulation_time": g30.FIXED_HORIZON,
            "request_max_simulation_time": g30.FIXED_HORIZON,
            "summary_declared_max_simulation_time": g30.FIXED_HORIZON,
        },
        "exact_release_gate": {
            "pass": True,
            "mode": "SCHEDULED_ARRIVAL_OWN_SOURCE_FIXED_HORIZON_CAPACITY",
            "release_pairing": "NOT_PAIRED",
            "exact_release_applied": False,
            "full_population_capacity_comparison_allowed": True,
            "full_outcome_timing_comparison_allowed": timing_allowed,
            "survivor_only_full_claim_allowed": False,
        },
        "outcome": {
            "completed_raw_bag_count": completed,
            "topology_reachability": topology,
        },
        "timing": (
            _native_timing(measured_mean)
            if measured_mean is not None
            else {
                "status": g30.NOT_MEASURED,
                "reason": "own_source_fixed_horizon_capacity_only_not_timing_paired",
                "full_outcome_timing_comparison_allowed": False,
            }
        ),
        "event_budget": {
            "required": True,
            "expected_max_events": g30.G30_MAX_EVENTS,
            "request_max_events": g30.G30_MAX_EVENTS,
            "summary_declared_max_events": g30.G30_MAX_EVENTS,
            "summary_event_count": 1_000,
            "summary_event_limit_reached": False,
            "event_limit_not_reached": True,
            "pass": True,
        },
        "safety": {
            "pass": True,
            "fixed_horizon_capacity_admission": {"pass": True},
        },
        "runtime": {"wall_seconds": 10.0},
    }


def _hca_row(
    case_id: str,
    *,
    completed: int | None = None,
    full_timing: bool = False,
    mean: float = 10.0,
) -> dict:
    group = "all_day_line_interruption" if case_id.startswith("t5_5_") else "stable_speed"
    if case_id == g30.PAIR_5_7_CASE_ID:
        return {
            "case_id": case_id,
            "case_group": group,
            "execution_class": "ARCHIVED_ONLY_PROBE",
            "protocol_status": "ARCHIVED_ONLY_NOT_EXECUTED",
            "primary_capacity_eligible": False,
            "repeats_complete": 0,
            "repeats_expected": 0,
        }
    repeats = 2 if group == "stable_speed" else 1
    completed = g30.FULL_RAW_BAGS - 100 if completed is None else completed
    full = bool(full_timing and group == "stable_speed" and completed == g30.FULL_RAW_BAGS)
    distributions = [_distribution(mean) for _ in range(repeats)]
    return {
        "case_id": case_id,
        "case_group": group,
        "execution_class": "PRIMARY_MEASURABLE",
        "protocol_status": (
            "EXACT_FULL_COMPLETION" if full else "FIXED_HORIZON_END_TO_END_CAPACITY"
        ),
        "primary_capacity_eligible": True,
        "fixed_horizon_pass": True,
        "cohort_pass": True,
        "repeats_complete": repeats,
        "repeats_expected": repeats,
        "counts_consistent_across_repeats": True,
        "canonical_complete_raw_bag_count_by_repeat": [completed] * repeats,
        "full_completion_eligible": full,
        "formal_timing_comparison_allowed": full,
        "timing_scope": (
            "FULL_POPULATION"
            if full
            else "CENSORED_COMPLETED_SURVIVORS_SECONDARY"
            if group == "stable_speed"
            else "CAPACITY_ONLY_TABLE_5_5"
        ),
        "secondary_timing_censored": group == "stable_speed" and not full,
        "full_population_processed_attempt_minutes_by_repeat": (
            distributions if full else [None] * repeats
        ),
        "secondary_censored_processed_attempt_minutes_by_repeat": (
            distributions if group == "stable_speed" and not full else [None] * repeats
        ),
    }


def _evidence() -> tuple[dict, dict, dict]:
    paper = g30.g26.paper_cases()
    stable = [case for case in paper if case["case_group"] == "stable_speed"]
    faults = [
        case for case in paper if case["case_group"] == "all_day_line_interruption"
    ]
    hca = {
        "schema": g30.HCA_SCHEMA,
        "status": "COMPLETE_WITH_ARCHIVED_ONLY_GAP",
        "primary_complete_case_count": 19,
        "missing_primary_case_ids": [],
        "invalid_primary_case_ids": [],
        "rows": [
            _hca_row(str(case["case_id"])) for case in (*stable, *faults)
        ],
    }
    native_cases = [_native_case(str(case["case_id"])) for case in stable]
    native_cases.extend(
        _native_case(str(case["case_id"])) for case in g30.g27_bias.bias_cases()
    )
    native_cases.extend(
        _native_case(
            str(case["case_id"]),
            topology_upper=g30.FULL_RAW_BAGS,
        )
        for case in faults
        if case["case_id"] != g30.PAIR_5_7_CASE_ID
    )
    admitted_case_ids = sorted(str(case["case_id"]) for case in native_cases)
    native = {
        "schema": g30.NATIVE_SCHEMA,
        "status": "COMPLETE",
        "workload_protocol": g30.WORKLOAD_PROTOCOL,
        "fixed_population": {
            "raw_bag_count": g30.FULL_RAW_BAGS,
            "segment_count": g30.FULL_SEGMENTS,
        },
        "expected_case_count": g30.EXPECTED_NATIVE_CASE_COUNT,
        "observed_case_count": g30.EXPECTED_NATIVE_CASE_COUNT,
        "complete_case_ids": admitted_case_ids,
        "blocked_release_case_ids": [],
        "failed_case_ids": [],
        "stale_admission_case_ids": [],
        "missing_case_ids": [],
        "fixed_horizon_admission": {
            "expected_max_simulation_time": g30.FIXED_HORIZON,
            "admitted_case_ids": admitted_case_ids,
            "pass": True,
        },
        "event_budget_admission": {
            "expected_max_events": g30.G30_MAX_EVENTS,
            "admitted_case_ids": admitted_case_ids,
            "pass": True,
        },
        "cases": native_cases,
    }
    return _workload(), hca, native


def _by_id(rows: list[dict], case_id: str) -> dict:
    return next(row for row in rows if row["case_id"] == case_id)


def test_complete_capacity_fixture_builds_19_cell_primary_and_visible_context() -> None:
    workload, hca, native = _evidence()

    payload = g30.build_report(workload, hca, native)

    assert payload["status"] == "G30_3X_FIXED_HORIZON_PRIMARY_TARGET_MET"
    assert payload["joint_decision"]["target_met"] is True
    assert payload["joint_decision"]["primary_3x_vs_fresh_hca"] == {
        "cell_count": 19,
        "measured_count": 19,
        "not_measured_count": 0,
        "not_applicable_baseline_incomplete_count": 0,
        "s4_win_count": 19,
        "allowed_tie_count": 0,
        "unresolved_tie_count": 0,
        "baseline_win_count": 0,
    }
    assert len(payload["tables"]["5.2"]["rows"]) == 4
    assert len(payload["tables"]["5.3"]["rows"]) == 3
    assert len(payload["tables"]["5.4"]["rows"]) == 12
    assert len(payload["tables"]["5.5"]["rows"]) == 16
    assert all(
        row["s4_full_population_completed"] is True
        for row in payload["tables"]["5.2"]["rows"]
    )
    assert payload["joint_decision"]["context_gaps"] == 45
    assert payload["joint_decision"]["context_drives_3x_primary"] is False
    assert (
        payload["joint_decision"]["all_original_paper_subjects_exact_win_claimed"]
        is False
    )
    pair = _by_id(payload["tables"]["5.5"]["rows"], g30.PAIR_5_7_CASE_ID)
    assert pair["measurement_status"] == g30.NOT_MEASURED
    assert pair["s4_vs_fresh_hca"] == g30.NOT_MEASURED
    assert payload["tables"]["5.5"]["fault_release_pairing"] == "NOT_PER_SEGMENT_PAIRED"

    markdown = g30.render_markdown(payload)
    csv_text = g30.render_csv(payload)
    assert "不是逐 segment fault-release 配对" in markdown
    assert "12 个 legacy-variant reconstruction cells" in markdown
    assert "archived_static_1x_unpaired" in csv_text
    assert "archived_paper_reported_improvement_1x_unpaired" in csv_text


def test_admitted_incomplete_native_case_is_a_fixed_denominator_capacity_outcome() -> None:
    workload, hca, native = _evidence()
    case_id = "t5_5_fault_single_4"
    hca_row = _by_id(hca["rows"], case_id)
    hca_row["canonical_complete_raw_bag_count_by_repeat"] = [71_000]
    native_row = _by_id(native["cases"], case_id)
    native_row["status"] = g30.NATIVE_FIXED_HORIZON_CAPACITY
    native_row["outcome"]["completed_raw_bag_count"] = 72_029
    native_row["timing"] = _native_timing(3.0)
    native_row["timing"]["raw_bag_count"] = 72_029

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.5"]["rows"], case_id)

    assert row["measurement_status"] == g30.MEASURED
    assert row["s4_case_status"] == g30.NATIVE_FIXED_HORIZON_CAPACITY
    assert row["s4_completed_raw_bags"] == 72_029
    assert row["fresh_hca_completed_raw_bags"] == 71_000
    assert row["s4_vs_fresh_hca"] == "S4_WIN"
    assert row["s4_full_population_completed"] is False
    assert row["fresh_hca_full_population_completed"] is False
    assert row["incomplete_fixed_horizon_is_business_outcome"] is True
    assert row["incomplete_fixed_horizon_is_runtime_or_safety_failure"] is False
    assert row["survivor_timing_claim_allowed"] is False
    assert "timing" not in row
    assert payload["joint_decision"]["target_met"] is True
    assert "不表示 CPU 超时或安全失败" in g30.render_markdown(payload)


def test_fixed_horizon_capacity_status_requires_portable_aggregate_admission() -> None:
    workload, hca, native = _evidence()
    case_id = "t5_5_fault_single_4"
    case = _by_id(native["cases"], case_id)
    case["status"] = g30.NATIVE_FIXED_HORIZON_CAPACITY
    case["outcome"]["completed_raw_bag_count"] = 72_029
    native["complete_case_ids"].remove(case_id)

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.5"]["rows"], case_id)

    assert row["measurement_status"] == g30.NOT_MEASURED
    assert row["s4_vs_fresh_hca"] == g30.NOT_MEASURED
    assert payload["input_diagnostics"]["native_portable_admitted_case_count"] == 30
    assert payload["status"] == "G30_3X_PARTIAL_DIAGNOSTIC"


def test_portable_admission_is_the_three_way_intersection_and_requires_60m() -> None:
    workload, hca, native = _evidence()
    case_id = "t5_5_fault_single_4"
    native["event_budget_admission"]["admitted_case_ids"].remove(case_id)

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.5"]["rows"], case_id)
    assert row["measurement_status"] == g30.NOT_MEASURED
    assert payload["input_diagnostics"]["native_portable_admitted_case_count"] == 30
    assert payload["input_diagnostics"]["native_portable_aggregate_complete"] is False
    assert payload["status"] == "G30_3X_PARTIAL_DIAGNOSTIC"

    workload, hca, native = _evidence()
    native["event_budget_admission"]["expected_max_events"] = 59_999_999
    payload = g30.build_report(workload, hca, native)
    assert all(
        row["measurement_status"] == g30.MEASURED
        for row in payload["tables"]["5.2"]["rows"]
    )
    assert payload["input_diagnostics"]["native_portable_aggregate_complete"] is False
    assert payload["joint_decision"]["target_met"] is False


def test_native_aggregate_requires_exact_31_rows_and_registered_horizon() -> None:
    workload, hca, native = _evidence()
    candidates = []

    wrong_count = copy.deepcopy(native)
    wrong_count["observed_case_count"] = 30
    candidates.append(wrong_count)

    missing_row = copy.deepcopy(native)
    missing_row["cases"].pop()
    candidates.append(missing_row)

    wrong_horizon = copy.deepcopy(native)
    wrong_horizon["fixed_horizon_admission"][
        "expected_max_simulation_time"
    ] = 90_000.0
    candidates.append(wrong_horizon)

    duplicate_axis = copy.deepcopy(native)
    duplicate_axis["event_budget_admission"]["admitted_case_ids"][-1] = (
        duplicate_axis["event_budget_admission"]["admitted_case_ids"][0]
    )
    candidates.append(duplicate_axis)

    for candidate in candidates:
        payload = g30.build_report(workload, hca, candidate)
        assert payload["input_diagnostics"]["native_portable_aggregate_complete"] is False
        assert payload["status"] == "G30_3X_PARTIAL_DIAGNOSTIC"
        assert payload["joint_decision"]["target_met"] is False


def test_native_case_requires_safety_event_budget_and_authoritative_artifact_admission() -> None:
    workload, hca, native = _evidence()
    case_id = "t5_2_speed_1p5"
    mutations = []

    unsafe = copy.deepcopy(native)
    _by_id(unsafe["cases"], case_id)["safety"]["pass"] = False
    mutations.append((unsafe, "structural safety"))

    exhausted = copy.deepcopy(native)
    event_budget = _by_id(exhausted["cases"], case_id)["event_budget"]
    event_budget["summary_event_limit_reached"] = True
    event_budget["pass"] = False
    mutations.append((exhausted, "60M event-budget"))

    mismatched = copy.deepcopy(native)
    release_gate = _by_id(mismatched["cases"], case_id)["exact_release_gate"]
    release_gate["mode"] = "EXACT_PAIRED_FULL"
    release_gate["exact_release_applied"] = True
    mutations.append((mismatched, "authoritative admission"))

    for candidate, reason in mutations:
        payload = g30.build_report(workload, hca, candidate)
        row = _by_id(payload["tables"]["5.2"]["rows"], case_id)
        assert row["measurement_status"] == g30.NOT_MEASURED
        assert reason in " ".join(row["capacity_not_measured_reasons"])
        assert payload["joint_decision"]["target_met"] is False


def test_incomplete_speed_capacity_cannot_promote_survivor_timing() -> None:
    workload, hca, native = _evidence()
    case_id = "t5_2_speed_2p5"
    hca_row = _by_id(hca["rows"], case_id)
    hca_row["canonical_complete_raw_bag_count_by_repeat"] = [71_000, 71_000]
    native_row = _by_id(native["cases"], case_id)
    native_row["status"] = g30.NATIVE_FIXED_HORIZON_CAPACITY
    native_row["outcome"]["completed_raw_bag_count"] = 72_029
    native_row["timing"] = _native_timing(3.0)
    native_row["timing"]["raw_bag_count"] = 72_029
    native_row["exact_release_gate"][
        "full_outcome_timing_comparison_allowed"
    ] = True

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.2"]["rows"], case_id)

    assert row["measurement_status"] == g30.MEASURED
    assert row["capacity_verdict"] == "S4_WIN"
    assert row["s4_full_population_completed"] is False
    assert row["metrics"]["mean"]["s4_minutes"] is None
    assert row["metrics"]["mean"]["timing_verdict"] == (
        g30.NOT_APPLICABLE_BASELINE_INCOMPLETE
    )
    assert payload["protocol"]["survivor_timing_claim_allowed"] is False
    assert payload["joint_decision"]["target_met"] is True


def test_own_source_full_population_descriptive_timing_is_context_only() -> None:
    workload, hca, native = _evidence()
    speed = _by_id(native["cases"], "t5_2_speed_2p5")
    bias = _by_id(native["cases"], "t5_4_bias_std_2p5_dev_10")
    for case, mean in ((speed, 1.0), (bias, 1_000.0)):
        case["timing"] = _native_timing(mean)
        case["timing"].update(
            {
                "status": g30.OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE,
                "full_outcome_timing_comparison_allowed": False,
                "fresh_hca_timing_verdict_allowed": False,
            }
        )
        case["exact_release_gate"][
            "full_outcome_timing_comparison_allowed"
        ] = False

    payload = g30.build_report(workload, hca, native)
    table_52 = _by_id(payload["tables"]["5.2"]["rows"], "t5_2_speed_2p5")
    assert table_52["fresh_timing_status"] == (
        g30.NOT_APPLICABLE_BASELINE_INCOMPLETE
    )
    assert table_52["metrics"]["mean"]["s4_minutes"] is None
    assert "s4_full_population_context_minutes" not in table_52["metrics"]["mean"]
    assert "s4_context_timing_status" not in table_52["metrics"]["mean"]

    table_53 = next(
        row for row in payload["tables"]["5.3"]["rows"] if row["metric"] == "mean"
    )
    assert table_53["measurement_status"] == (
        g30.OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE
    )
    assert table_53["s4_3x_minutes"] == 1.0
    assert table_53["drives_fresh_3x_timing"] is False

    table_54 = _by_id(
        payload["tables"]["5.4"]["rows"], "t5_4_bias_std_2p5_dev_10"
    )
    assert table_54["timing_measurement_status"] == (
        g30.OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE
    )
    assert table_54["s4_3x_mean_minutes"] == 1_000.0
    assert table_54["s4_vs_archived_dynamic"] == "BASELINE_WIN"
    assert table_54["drives_fresh_3x_timing"] is False
    assert payload["protocol"][
        "own_source_full_population_descriptive_drives_fresh_timing"
    ] is False
    assert payload["joint_decision"]["target_met"] is True

    invalid = copy.deepcopy(native)
    invalid_speed = _by_id(invalid["cases"], "t5_2_speed_2p5")
    invalid_speed["timing"]["fresh_hca_timing_verdict_allowed"] = True
    invalid_payload = g30.build_report(workload, hca, invalid)
    invalid_table_53 = next(
        row
        for row in invalid_payload["tables"]["5.3"]["rows"]
        if row["metric"] == "mean"
    )
    assert invalid_table_53["measurement_status"] == g30.NOT_MEASURED
    assert invalid_table_53["s4_3x_minutes"] is None


def test_missing_or_partial_inputs_are_diagnostic_and_never_predeclare_win() -> None:
    missing = g30.build_report(None, None, None)
    assert missing["status"] == "G30_3X_PARTIAL_DIAGNOSTIC"
    assert missing["joint_decision"]["target_met"] is False

    workload, hca, native = _evidence()
    native["status"] = "PARTIAL"
    partial = g30.build_report(workload, hca, native)
    assert all(
        row["measurement_status"] == g30.MEASURED
        for row in partial["tables"]["5.2"]["rows"]
    )
    assert partial["input_diagnostics"]["portable_aggregates_complete"] is False
    assert partial["status"] == "G30_3X_PARTIAL_DIAGNOSTIC"
    assert partial["joint_decision"]["target_met"] is False


def test_own_source_capacity_win_keeps_hca_survivor_timing_secondary() -> None:
    workload, hca, native = _evidence()
    case = _by_id(native["cases"], "t5_2_speed_2p5")
    case["timing"] = _native_timing(1.0)
    case["exact_release_gate"]["full_outcome_timing_comparison_allowed"] = True

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.2"]["rows"], "t5_2_speed_2p5")

    assert row["s4_completed_raw_bags"] == g30.FULL_RAW_BAGS
    assert row["fresh_hca_completed_raw_bags"] == g30.FULL_RAW_BAGS - 100
    assert row["capacity_verdict"] == "S4_WIN"
    assert row["fresh_timing_status"] == g30.NOT_APPLICABLE_BASELINE_INCOMPLETE
    assert row["metrics"]["mean"]["s4_minutes"] == 1.0
    assert (
        row["metrics"]["mean"][
            "fresh_hca_censored_survivor_repeat_mean_minutes"
        ]
        == 10.0
    )
    assert row["metrics"]["mean"]["hca_censored_survivor_timing_drives_verdict"] is False
    assert (
        row["metrics"]["mean"]["timing_verdict"]
        == g30.NOT_APPLICABLE_BASELINE_INCOMPLETE
    )
    assert payload["joint_decision"]["target_met"] is True


def test_capacity_loss_and_unresolved_tie_fail_but_registered_ceilings_are_allowed() -> None:
    workload, hca, native = _evidence()
    hca_row = _by_id(hca["rows"], "t5_2_speed_2")
    hca_row["canonical_complete_raw_bag_count_by_repeat"] = [g30.FULL_RAW_BAGS] * 2
    native_row = _by_id(native["cases"], "t5_2_speed_2")
    native_row["outcome"]["completed_raw_bag_count"] = g30.FULL_RAW_BAGS - 1

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.2"]["rows"], "t5_2_speed_2")
    assert row["capacity_verdict"] == "BASELINE_WIN"
    assert payload["status"] == "G30_3X_FIXED_HORIZON_PRIMARY_TARGET_NOT_MET"
    assert payload["joint_decision"]["zero_baseline_losses"] is False

    assert g30._capacity_verdict(40_000, 40_000) == "UNRESOLVED_TIE"
    assert (
        g30._capacity_verdict(g30.FULL_RAW_BAGS, g30.FULL_RAW_BAGS)
        == "100_PERCENT_CEILING_TIE"
    )
    assert g30._capacity_verdict(40_000, 40_000, 40_000) == "TOPOLOGY_CEILING_TIE"


def test_fault_topology_ceiling_tie_is_an_allowed_primary_decision() -> None:
    workload, hca, native = _evidence()
    case_id = "t5_5_fault_single_2"
    hca_row = _by_id(hca["rows"], case_id)
    hca_row["canonical_complete_raw_bag_count_by_repeat"] = [40_000]
    native_row = _by_id(native["cases"], case_id)
    native_row["outcome"]["completed_raw_bag_count"] = 40_000
    native_row["outcome"]["topology_reachability"] = {
        "topology_reachable_raw_bag_upper_bound": 40_000
    }

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.5"]["rows"], case_id)
    assert row["s4_vs_fresh_hca"] == "TOPOLOGY_CEILING_TIE"
    assert payload["joint_decision"]["target_met"] is True
    assert payload["joint_decision"]["primary_3x_vs_fresh_hca"]["allowed_tie_count"] == 1


def test_bad_repeat_counts_or_native_horizon_leave_the_cell_not_measured() -> None:
    workload, hca, native = _evidence()
    hca_row = _by_id(hca["rows"], "t5_2_speed_1p5")
    hca_row["counts_consistent_across_repeats"] = False
    hca_row["canonical_complete_raw_bag_count_by_repeat"] = [1, 2]
    native_row = _by_id(native["cases"], "t5_2_speed_3")
    native_row["fixed_horizon"]["pass"] = False

    payload = g30.build_report(workload, hca, native)
    bad_hca = _by_id(payload["tables"]["5.2"]["rows"], "t5_2_speed_1p5")
    bad_native = _by_id(payload["tables"]["5.2"]["rows"], "t5_2_speed_3")
    assert bad_hca["measurement_status"] == g30.NOT_MEASURED
    assert "repeat counts" in " ".join(bad_hca["capacity_not_measured_reasons"])
    assert bad_native["measurement_status"] == g30.NOT_MEASURED
    assert "fixed-horizon" in " ".join(bad_native["capacity_not_measured_reasons"])
    assert payload["status"] == "G30_3X_PARTIAL_DIAGNOSTIC"


def test_table_54_context_loss_is_visible_but_does_not_drive_primary() -> None:
    workload, hca, native = _evidence()
    case_id = "t5_4_bias_std_2p5_dev_10"
    case = _by_id(native["cases"], case_id)
    case["timing"] = _native_timing(1_000.0)
    case["exact_release_gate"]["full_outcome_timing_comparison_allowed"] = True

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.4"]["rows"], case_id)
    assert row["s4_vs_archived_dynamic"] == "BASELINE_WIN"
    assert row["s4_vs_archived_static"] == "BASELINE_WIN"
    assert payload["joint_decision"]["context_losses"] > 0
    assert payload["joint_decision"]["context_drives_3x_primary"] is False
    assert payload["joint_decision"]["target_met"] is True
    assert case_id in g30.render_markdown(payload)


def test_full_population_timing_is_descriptive_and_never_replaced_by_survivors() -> None:
    workload, hca, native = _evidence()
    case_id = "t5_2_speed_1p5"
    replacement = _hca_row(
        case_id,
        completed=g30.FULL_RAW_BAGS,
        full_timing=True,
        mean=10.0,
    )
    hca["rows"][hca["rows"].index(_by_id(hca["rows"], case_id))] = replacement
    case = _by_id(native["cases"], case_id)
    case["timing"] = _native_timing(20.0)
    case["exact_release_gate"]["full_outcome_timing_comparison_allowed"] = True

    payload = g30.build_report(workload, hca, native)
    row = _by_id(payload["tables"]["5.2"]["rows"], case_id)
    assert row["capacity_verdict"] == "100_PERCENT_CEILING_TIE"
    assert row["fresh_timing_status"] == g30.MEASURED
    assert row["metrics"]["mean"]["timing_verdict"] == "BASELINE_WIN"
    assert row["metrics"]["mean"]["fresh_hca_censored_survivor_repeat_mean_minutes"] is None
    assert payload["joint_decision"]["target_met"] is True


def test_internal_absolute_paths_are_not_copied_into_report() -> None:
    workload, hca, native = _evidence()
    hca["workload"] = {"manifest": r"C:\foreign\checkout\manifest.json"}
    native["release_source_mapping"] = {
        "t5_2_speed_2p5": {"path": r"C:\foreign\checkout\release.csv"}
    }

    payload = g30.build_report(workload, hca, native)

    assert "C:\\foreign" not in json.dumps(payload)


def test_cli_rebuilds_from_portable_aggregates_and_detects_stale_text(
    tmp_path: Path,
) -> None:
    workload, hca, native = _evidence()
    manifest_path = tmp_path / "manifest.json"
    hca_path = tmp_path / "hca.json"
    native_path = tmp_path / "native.json"
    manifest_path.write_text(json.dumps(workload), encoding="utf-8")
    hca_path.write_text(json.dumps(hca), encoding="utf-8")
    native_path.write_text(json.dumps(native), encoding="utf-8")
    json_output = tmp_path / "report.json"
    csv_output = tmp_path / "report.csv"
    markdown_output = tmp_path / "report.md"
    arguments = [
        "--workload-manifest",
        str(manifest_path),
        "--hca-aggregate",
        str(hca_path),
        "--native-aggregate",
        str(native_path),
        "--json-output",
        str(json_output),
        "--csv-output",
        str(csv_output),
        "--markdown-output",
        str(markdown_output),
    ]

    assert g30.main(arguments) == 0
    assert json.loads(json_output.read_text(encoding="utf-8"))["joint_decision"][
        "target_met"
    ] is True
    assert g30.main(["--validate-committed", *arguments]) == 0

    markdown_output.write_text("stale\n", encoding="utf-8")
    assert g30.main(["--validate-committed", *arguments]) == 2


def test_wrong_workload_or_aggregate_identity_is_rejected() -> None:
    workload, hca, native = _evidence()
    wrong_workload = copy.deepcopy(workload)
    wrong_workload["protocol"] = "MECHANICAL_SEGMENT_COPY_3X"
    with pytest.raises(g30.Reporting30Error, match="registered G30 3x cohort"):
        g30.build_report(wrong_workload, hca, native)

    wrong_native = copy.deepcopy(native)
    wrong_native["schema"] = "czr005.g4irsf29.s4_aggregate.v1"
    with pytest.raises(g30.Reporting30Error, match="native aggregate schema"):
        g30.build_report(workload, hca, wrong_native)


def test_workload_requires_all_registered_three_x_business_invariants() -> None:
    workload, hca, native = _evidence()
    candidates = []

    broken_copy = copy.deepcopy(workload)
    broken_copy["invariants"]["slack_and_storage_class_are_preserved"] = False
    candidates.append(broken_copy)

    compressed = copy.deepcopy(workload)
    compressed["timing"]["time_compression"] = 0.5
    candidates.append(compressed)

    wrong_insertion = copy.deepcopy(workload)
    wrong_insertion["insertion_rule"]["nonterminal"] = "mechanical_segment_copy"
    candidates.append(wrong_insertion)

    wrong_distribution = copy.deepcopy(workload)
    wrong_distribution["raw_by_end"]["48"] += 3
    candidates.append(wrong_distribution)

    for candidate in candidates:
        with pytest.raises(g30.Reporting30Error, match="registered G30 3x cohort"):
            g30.build_report(candidate, hca, native)
