from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.eval import run_g4irsf29_reporting as g29


def _workload() -> dict:
    return {
        "schema": g29.WORKLOAD_SCHEMA,
        "status": "COMPLETE",
        "protocol": g29.WORKLOAD_PROTOCOL,
        "raw_task_count": g29.FULL_RAW_BAGS,
        "expanded_segment_count": g29.FULL_SEGMENTS,
        "original_flight_count": 360,
        "inserted_flight_count": 360,
        "stream_count": 13,
        "insertion_rule": {
            "nonterminal": "midpoint_to_next_STD_in_same_stream",
            "terminal": "lower_median_positive_stream_headway_divided_by_2",
        },
    }


def _native_case(
    case_id: str,
    *,
    mean: float = 1.0,
    completed: int = g29.FULL_RAW_BAGS,
    topology_upper: int | None = None,
) -> dict:
    group = (
        "fault"
        if case_id.startswith("t5_5_fault_")
        else "observation_bias"
        if case_id.startswith("t5_4_bias_")
        else "stable_speed"
    )
    topology = (
        {"topology_reachable_raw_bag_upper_bound": topology_upper}
        if topology_upper is not None
        else None
    )
    timing = (
        {
            "status": g29.NOT_MEASURED,
            "reason": "table_5_5_compares_fixed_population_success_rate_not_timing",
            "selected_raw_bag_count": g29.FULL_RAW_BAGS,
            "completed_raw_bag_count": completed,
            "fixed_population_success": {
                "count": completed,
                "rate": completed / g29.FULL_RAW_BAGS,
                "definition": "completed raw bags / fixed selected raw bags",
            },
            "full_outcome_timing_comparison_allowed": False,
        }
        if group == "fault"
        else {
            "status": g29.MEASURED,
            "source": "fake protected timing fixture",
            "population": "all_selected_raw_bags_complete",
            "raw_bag_count": g29.FULL_RAW_BAGS,
            "units": "seconds",
            "distributions": {
                "processed_attempt": {
                    "count": g29.FULL_RAW_BAGS,
                    "min_seconds": mean * 0.8 * 60.0,
                    "mean_seconds": mean * 60.0,
                    "p95_seconds": mean * 1.2 * 60.0,
                    "p99_seconds": mean * 1.3 * 60.0,
                    "max_seconds": mean * 1.5 * 60.0,
                }
            },
            "full_outcome_timing_comparison_allowed": True,
        }
    )
    return {
        "schema": g29.NATIVE_CASE_SCHEMA,
        "status": g29.NATIVE_COMPLETE,
        "case_id": case_id,
        "case_group": group,
        "workload_protocol": g29.WORKLOAD_PROTOCOL,
        "fixed_horizon": {
            "required": True,
            "expected_max_simulation_time": g29.FIXED_HORIZON,
            "request_max_simulation_time": g29.FIXED_HORIZON,
            "summary_declared_max_simulation_time": g29.FIXED_HORIZON,
            "request_matches": True,
            "summary_matches": True,
            "pass": True,
        },
        "selection": {
            "selected_raw_bag_count": g29.FULL_RAW_BAGS,
            "selected_segment_count": g29.FULL_SEGMENTS,
        },
        "exact_release_gate": {
            "pass": True,
            "full_population_capacity_comparison_allowed": True,
            "full_outcome_timing_comparison_allowed": group != "fault",
            "survivor_only_full_claim_allowed": False,
        },
        "outcome": {
            "completed_raw_bag_count": completed,
            "topology_reachability": topology,
            "paper_raw_bag_tth": {
                "denominator": g29.FULL_RAW_BAGS,
                "distribution": {
                    "count": g29.FULL_RAW_BAGS,
                    "minutes": {
                        "min": mean * 0.8,
                        "mean": mean,
                        "p95": mean * 1.2,
                        "p99": mean * 1.3,
                        "max": mean * 1.5,
                    }
                }
            },
        },
        "timing": timing,
        "runtime": {"wall_seconds": 10.0},
    }


def _hca_row(case: dict) -> dict:
    stable = case["case_group"] == "stable_speed"
    return {
        "case_id": case["case_id"],
        "case_group": case["case_group"],
        "protocol_status": (
            "EXACT_FULL_COMPLETION"
            if stable
            else "ARCHIVED_ONLY_NOT_EXECUTED"
            if case["case_id"] == g29.PAIR_5_7_CASE_ID
            else "FIXED_HORIZON_CAPACITY"
        ),
        "primary_capacity_eligible": case["case_id"] != g29.PAIR_5_7_CASE_ID,
        "repeats_complete": 2 if stable else 0 if case["case_id"] == g29.PAIR_5_7_CASE_ID else 1,
        "release_repeat_match": True if stable else None,
        "full_completion_eligible": True if stable else False,
        "timing_scope": "FULL_POPULATION" if stable else "CENSORED_COMPLETED_SURVIVORS_SECONDARY",
        "secondary_timing_censored": False if stable else True,
        "canonical_complete_raw_bag_count_by_repeat": (
            [g29.FULL_RAW_BAGS, g29.FULL_RAW_BAGS]
            if stable
            else []
            if case["case_id"] == g29.PAIR_5_7_CASE_ID
            else [56_000]
        ),
    }


def _hca_metric(
    mean: float = 10.0,
    *,
    completed: int = g29.FULL_RAW_BAGS,
    comparison_eligible: bool = True,
) -> dict:
    return {
        "canonical_raw_bag_count": g29.FULL_RAW_BAGS,
        "canonical_segment_count": g29.FULL_SEGMENTS,
        "canonical_complete_raw_bag_count": completed,
        "comparison_eligible": comparison_eligible,
        "wall_seconds": 100.0,
        "denominators": {
            "processed_attempt": {
                "count": completed,
                "minutes": {
                    "min": mean * 0.8,
                    "mean": mean,
                    "p95": mean * 1.2,
                    "p99": mean * 1.3,
                    "max": mean * 1.5,
                }
            }
        },
    }


def _evidence() -> tuple[dict, dict, dict, dict[str, list[dict]]]:
    paper_cases = g29.g26.paper_cases()
    stable = [case for case in paper_cases if case["case_group"] == "stable_speed"]
    faults = [
        case for case in paper_cases if case["case_group"] == "all_day_line_interruption"
    ]
    hca = {
        "schema": g29.HCA_SCHEMA,
        "status": "COMPLETE_WITH_ARCHIVED_ONLY_GAP",
        "rows": [_hca_row(case) for case in (*stable, *faults)],
    }
    native_cases = [_native_case(str(case["case_id"])) for case in stable]
    native_cases.extend(
        _native_case(str(case["case_id"])) for case in g29.g27_bias.bias_cases()
    )
    native_cases.extend(
        _native_case(
            str(case["case_id"]),
            topology_upper=g29.FULL_RAW_BAGS,
        )
        for case in faults
        if case["case_id"] != g29.PAIR_5_7_CASE_ID
    )
    native = {
        "schema": g29.NATIVE_SCHEMA,
        "status": "COMPLETE",
        "expected_case_count": g29.EXPECTED_NATIVE_CASE_COUNT,
        "fixed_horizon_admission": {
            "expected_max_simulation_time": g29.FIXED_HORIZON,
            "pass": True,
        },
        "cases": native_cases,
    }
    metrics = {
        str(case["case_id"]): [_hca_metric(), _hca_metric()] for case in stable
    }
    rows_by_id = {str(row["case_id"]): row for row in hca["rows"]}
    for case_id, repeats in metrics.items():
        row = rows_by_id[case_id]
        row["comparison_eligible_by_repeat"] = [
            value["comparison_eligible"] for value in repeats
        ]
        row["wall_seconds_by_repeat"] = [value["wall_seconds"] for value in repeats]
        row["full_population_processed_attempt_minutes_by_repeat"] = [
            value["denominators"]["processed_attempt"]["minutes"]
            for value in repeats
        ]
        row["secondary_censored_processed_attempt_minutes_by_repeat"] = [
            None for _value in repeats
        ]
    return _workload(), hca, native, metrics


def test_complete_winning_fixture_builds_all_tables_without_promoting_pair_5_7() -> None:
    workload, hca, native, metrics = _evidence()
    payload = g29.build_report(workload, hca, native, metrics)
    assert payload == g29.build_report(workload, hca, native)

    assert payload["status"] == "G29_FRESH_2X_PRIMARY_TARGET_MET"
    assert payload["title"] == "G29 fresh 2× primary target report"
    assert (
        payload["joint_decision"]["all_original_paper_subjects_exact_win_claimed"]
        is False
    )
    assert payload["joint_decision"]["target_met"] is True
    assert payload["protocol"]["fixed_raw_bag_denominator"] == 57_012
    assert len(payload["tables"]["5.2"]["rows"]) == 4
    assert len(payload["tables"]["5.3"]["rows"]) == 3
    assert len(payload["tables"]["5.4"]["rows"]) == 12
    assert len(payload["tables"]["5.5"]["rows"]) == 16
    pair = next(
        row
        for row in payload["tables"]["5.5"]["rows"]
        if row["case_id"] == g29.PAIR_5_7_CASE_ID
    )
    assert pair["measurement_status"] == g29.NOT_MEASURED
    assert pair["s4_vs_fresh_hca"] == g29.NOT_MEASURED
    assert payload["tables"]["5.5"]["fault_release_pairing"] == "NOT_PER_SEGMENT_PAIRED"
    assert payload["tables"]["5.5"]["fixed_denominator_raw_bags"] == 57_012
    assert "FIXED_57012" in payload["tables"]["5.5"]["claim_class"]
    assert "NOT_MEASURED" in g29.render_markdown(payload)
    assert "不是逐 segment release 配对" in g29.render_markdown(payload)
    assert "fresh_hca_2x_fixed_population" in g29.render_csv(payload)


def test_missing_artifacts_stay_not_measured_and_never_claim_a_win() -> None:
    payload = g29.build_report(None, None, None, {})

    assert payload["status"] == "G29_FRESH_2X_PRIMARY_NOT_FULLY_MEASURED"
    assert payload["joint_decision"]["target_met"] is False
    assert payload["joint_decision"]["evidence_complete"] is False
    assert all(
        row["measurement_status"] == g29.NOT_MEASURED
        for row in payload["tables"]["5.2"]["rows"]
    )


def test_legacy_native_aggregate_without_fixed_horizon_gate_is_not_admitted() -> None:
    workload, hca, native, metrics = _evidence()
    invalid_aggregates = []
    for mutation in ("status", "count", "horizon"):
        candidate = copy.deepcopy(native)
        if mutation == "status":
            candidate["status"] = "PARTIAL"
        elif mutation == "count":
            candidate["expected_case_count"] = 30
        else:
            candidate["fixed_horizon_admission"]["pass"] = False
        invalid_aggregates.append(candidate)

    for candidate in invalid_aggregates:
        try:
            g29.build_report(workload, hca, candidate, metrics)
        except g29.ReportingError as exc:
            assert "complete fixed-horizon G29 campaign" in str(exc)
        else:
            raise AssertionError("legacy native aggregate passed the fixed-horizon gate")


def test_native_case_must_echo_exact_registered_fixed_horizon() -> None:
    workload, hca, native, metrics = _evidence()
    case = next(
        row for row in native["cases"] if row["case_id"] == "t5_2_speed_2p5"
    )
    case["fixed_horizon"]["summary_declared_max_simulation_time"] = 90_000.0

    payload = g29.build_report(workload, hca, native, metrics)
    row = next(
        value
        for value in payload["tables"]["5.2"]["rows"]
        if value["case_id"] == "t5_2_speed_2p5"
    )

    assert row["capacity_measurement_status"] == g29.NOT_MEASURED
    assert "summary_declared_max_simulation_time is not 98259" in " ".join(
        row["capacity_not_measured_reasons"]
    )
    assert payload["joint_decision"]["target_met"] is False


def test_capacity_survives_when_fresh_full_outcome_timing_gate_is_false() -> None:
    workload, hca, native, metrics = _evidence()
    case = next(
        row for row in native["cases"] if row["case_id"] == "t5_2_speed_2p5"
    )
    case["exact_release_gate"]["full_outcome_timing_comparison_allowed"] = False

    payload = g29.build_report(workload, hca, native, metrics)
    row = next(
        row
        for row in payload["tables"]["5.2"]["rows"]
        if row["case_id"] == "t5_2_speed_2p5"
    )

    assert row["capacity_measurement_status"] == g29.MEASURED
    assert row["capacity_verdict"] == "100_PERCENT_CEILING_TIE"
    assert row["fresh_timing_measurement_status"] == g29.NOT_MEASURED
    assert row["metrics"]["mean"]["verdict"] == g29.NOT_MEASURED
    assert row["metrics"]["mean"]["s4_minutes"] == 1.0
    assert "full-outcome timing pairing is not allowed" in " ".join(
        row["fresh_timing_not_measured_reasons"]
    )
    assert payload["joint_decision"]["target_met"] is False


def test_partial_hca_completion_is_capacity_loss_with_only_censored_timing() -> None:
    workload, hca, native, metrics = _evidence()
    hca_row = next(
        row for row in hca["rows"] if row["case_id"] == "t5_2_speed_2p5"
    )
    hca_row.update(
        {
            "protocol_status": "EXACT_RELEASE_FULL_POPULATION_FIXED_HORIZON",
            "full_completion_eligible": False,
            "timing_scope": "CENSORED_COMPLETED_SURVIVORS_SECONDARY",
            "secondary_timing_censored": True,
            "canonical_complete_raw_bag_count_by_repeat": [56_917, 56_917],
            "canonical_success_rate_by_repeat": [56_917 / 57_012] * 2,
        }
    )
    metrics["t5_2_speed_2p5"] = [
        _hca_metric(completed=56_917, comparison_eligible=False),
        _hca_metric(completed=56_917, comparison_eligible=False),
    ]
    for case in native["cases"]:
        if case["case_id"] == "t5_2_speed_2p5" or case["case_id"].startswith(
            "t5_4_bias_std_2p5_"
        ):
            case["exact_release_gate"][
                "full_outcome_timing_comparison_allowed"
            ] = False
            case["timing"]["full_outcome_timing_comparison_allowed"] = False

    payload = g29.build_report(workload, hca, native, metrics)
    row = next(
        row
        for row in payload["tables"]["5.2"]["rows"]
        if row["case_id"] == "t5_2_speed_2p5"
    )

    assert row["capacity_measurement_status"] == g29.MEASURED
    assert row["s4_completed_raw_bags"] == 57_012
    assert row["fresh_hca_completed_raw_bags"] == 56_917
    assert row["capacity_verdict"] == "S4_WIN"
    assert (
        row["fresh_timing_measurement_status"]
        == g29.NOT_APPLICABLE_BASELINE_INCOMPLETE
    )
    assert row["metrics"]["mean"]["fresh_hca_repeat_mean_minutes"] is None
    assert (
        row["metrics"]["mean"][
            "fresh_hca_censored_survivor_repeat_mean_minutes"
        ]
        == 10.0
    )
    assert (
        row["metrics"]["mean"]["verdict"]
        == g29.NOT_APPLICABLE_BASELINE_INCOMPLETE
    )
    table_53_mean = next(
        value for value in payload["tables"]["5.3"]["rows"] if value["metric"] == "mean"
    )
    assert table_53_mean["s4_2x_minutes"] == 1.0
    assert (
        table_53_mean["s4_vs_fresh_hca_2x"]
        == g29.NOT_APPLICABLE_BASELINE_INCOMPLETE
    )
    assert table_53_mean["s4_2x_vs_archived_hca"] == "S4_WIN"
    assert all(
        value["measurement_status"] == g29.MEASURED
        for value in payload["tables"]["5.4"]["rows"]
        if value["standard_speed_mps"] == 2.5
    )
    assert payload["joint_decision"]["target_met"] is True
    assert payload["joint_decision"]["evidence_complete"] is True


def test_a_distinguishable_time_loss_keeps_target_not_met() -> None:
    workload, hca, native, metrics = _evidence()
    case = next(
        row for row in native["cases"] if row["case_id"] == "t5_2_speed_2"
    )
    case["timing"]["distributions"]["processed_attempt"]["mean_seconds"] = 660.0

    payload = g29.build_report(workload, hca, native, metrics)
    row = next(
        row
        for row in payload["tables"]["5.2"]["rows"]
        if row["case_id"] == "t5_2_speed_2"
    )

    assert row["metrics"]["mean"]["verdict"] == "BASELINE_WIN"
    assert payload["status"] == "G29_FRESH_2X_PRIMARY_TARGET_NOT_MET"
    assert payload["joint_decision"]["zero_baseline_losses"] is False


def test_archived_context_loss_is_reported_but_does_not_drive_2x_target() -> None:
    workload, hca, native, metrics = _evidence()
    bias = next(
        row
        for row in native["cases"]
        if row["case_id"] == "t5_4_bias_std_2p5_dev_10"
    )
    distribution = bias["timing"]["distributions"]["processed_attempt"]
    distribution["mean_seconds"] = 20.0 * 60.0

    payload = g29.build_report(workload, hca, native, metrics)
    row = next(
        row
        for row in payload["tables"]["5.4"]["rows"]
        if row["case_id"] == "t5_4_bias_std_2p5_dev_10"
    )

    assert row["s4_vs_archived_dynamic"] == "BASELINE_WIN"
    assert payload["joint_decision"]["context_evidence_complete"] is True
    assert payload["joint_decision"]["context_losses"] > 0
    assert payload["joint_decision"]["context_drives_2x_fresh_target"] is False
    assert payload["joint_decision"]["target_met"] is True


def test_missing_archived_context_does_not_relabel_complete_fresh_target() -> None:
    workload, hca, native, metrics = _evidence()
    native["cases"] = [
        row for row in native["cases"] if not row["case_id"].startswith("t5_4_bias_")
    ]

    payload = g29.build_report(workload, hca, native, metrics)

    assert payload["joint_decision"]["context_evidence_complete"] is False
    assert payload["joint_decision"]["context_drives_2x_fresh_target"] is False
    assert payload["joint_decision"]["target_met"] is True


def test_hca_internal_absolute_paths_are_not_copied_into_report_display() -> None:
    workload, hca, native, metrics = _evidence()
    hca["workload"] = {
        "manifest": r"C:\foreign\checkout\manifest.json",
        "raw_input": r"C:\foreign\checkout\input.txt",
        "canonical_input": r"C:\foreign\checkout\input.jsonl",
    }

    payload = g29.build_report(workload, hca, native, metrics)

    assert "C:\\foreign" not in json.dumps(payload)


def test_only_registered_ceiling_ties_are_accepted() -> None:
    assert g29._capacity_verdict(40_000, 40_000, 40_000) == "TOPOLOGY_CEILING_TIE"
    assert (
        g29._capacity_verdict(g29.FULL_RAW_BAGS, g29.FULL_RAW_BAGS, None)
        == "100_PERCENT_CEILING_TIE"
    )
    assert g29._capacity_verdict(40_000, 40_000, None) == "UNRESOLVED_TIE"
    assert g29._paper_time_verdict(3.964, 3.96) == "PAPER_PRECISION_TIE"


def test_fault_survivor_timing_is_never_promoted_to_a_table_5_5_claim() -> None:
    workload, hca, native, metrics = _evidence()
    case = next(
        row
        for row in native["cases"]
        if row["case_id"] == "t5_5_fault_single_2"
    )
    case["timing"] = {
        "status": g29.MEASURED,
        "raw_bag_count": 123,
        "full_outcome_timing_comparison_allowed": True,
        "distributions": {
            "processed_attempt": {
                "count": 123,
                "min_seconds": 1.0,
                "mean_seconds": 2.0,
                "p95_seconds": 3.0,
                "p99_seconds": 4.0,
                "max_seconds": 5.0,
            }
        },
    }

    payload = g29.build_report(workload, hca, native, metrics)
    row = next(
        row
        for row in payload["tables"]["5.5"]["rows"]
        if row["case_id"] == "t5_5_fault_single_2"
    )

    assert row["measurement_status"] == g29.NOT_MEASURED
    assert "protected fixed-population" in " ".join(row["not_measured_reasons"])


def test_cli_rebuilds_from_portable_aggregates_and_validates_text(
    tmp_path: Path,
) -> None:
    workload, hca, native, _metrics = _evidence()
    manifest_path = tmp_path / "manifest.json"
    hca_path = tmp_path / "hca.json"
    native_path = tmp_path / "native.json"
    manifest_path.write_text(json.dumps(workload), encoding="utf-8")
    hca_path.write_text(json.dumps(hca), encoding="utf-8")
    native_path.write_text(json.dumps(native), encoding="utf-8")
    json_output = tmp_path / "tables.json"
    csv_output = tmp_path / "tables.csv"
    md_output = tmp_path / "report.md"

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
        str(md_output),
    ]
    code = g29.main(arguments)

    assert code == 0
    assert json.loads(json_output.read_text(encoding="utf-8"))["joint_decision"][
        "target_met"
    ] is True
    assert csv_output.read_text(encoding="utf-8").startswith("table_id,case_id")
    assert "# G29 fresh 2× primary target" in md_output.read_text(encoding="utf-8")
    assert g29.main(["--validate-committed", *arguments]) == 0

    md_output.write_text("stale\n", encoding="utf-8")
    assert g29.main(["--validate-committed", *arguments]) == 2


def test_wrong_workload_protocol_is_rejected_not_silently_relabelled() -> None:
    workload = copy.deepcopy(_workload())
    workload["protocol"] = "NAIVE_SEGMENT_DUPLICATION_2X"

    try:
        g29.build_report(workload, None, None, {})
    except g29.ReportingError as exc:
        assert "registered G29 2x cohort" in str(exc)
    else:
        raise AssertionError("wrong workload protocol was accepted")
