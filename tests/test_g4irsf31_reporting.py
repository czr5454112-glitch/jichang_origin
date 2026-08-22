from __future__ import annotations

import copy
import json
from pathlib import Path

from scripts.eval import run_g4irsf31_reporting as g31


def _manifests() -> dict[int, dict[str, object]]:
    return {
        scale: {
            "schema": g31.MANIFEST_SCHEMA,
            "status": "COMPLETE",
            "scale": scale,
            "map_id": g31.MAP_ID,
            "protocol": f"registered-{scale}x",
            "raw_task_count": population["raw_bags"],
            "expanded_segment_count": population["segments"],
            "invariants": {"registered": True},
        }
        for scale, population in g31.FIXED_POPULATIONS.items()
    }


def _hca_row(cell: g31.PrimaryCell, *, completed: int | None = None) -> dict:
    repeats = 2 if cell.group == "stable_speed" else 1
    count = (
        cell.fixed_raw_bag_denominator - 1 if completed is None else completed
    )
    full = count == cell.fixed_raw_bag_denominator
    return {
        "case_id": cell.hca_case_id,
        "case_group": cell.group,
        "scale": cell.scale,
        "protocol_status": (
            "FULL_POPULATION_TIMING" if full and cell.group == "stable_speed"
            else "FIXED_HORIZON_CAPACITY"
        ),
        "repeats_expected": repeats,
        "repeats_complete": repeats,
        "fixed_raw_bag_denominator": cell.fixed_raw_bag_denominator,
        "fixed_segment_population": cell.fixed_segment_population,
        "primary_capacity_eligible": True,
        "completed_raw_bag_count_by_repeat": [count] * repeats,
        "full_population_completion": full,
        "formal_timing_comparison_allowed": full and cell.group == "stable_speed",
        "timing_scope": (
            "FULL_POPULATION" if full and cell.group == "stable_speed"
            else "NOT_REPORTED"
        ),
    }


def _native_case(cell: g31.PrimaryCell, *, completed: int | None = None) -> dict:
    count = cell.fixed_raw_bag_denominator if completed is None else completed
    full = count == cell.fixed_raw_bag_denominator
    timing = (
        {
            "status": "S4_FULL_POPULATION_DESCRIPTIVE",
            "population": "all_selected_raw_bags_complete",
            "raw_bag_count": count,
            "distributions": {"processed_attempt": {"mean_seconds": 60.0}},
        }
        if full
        else {
            "status": "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
            "survivor_only_timing_allowed": False,
        }
    )
    return {
        "schema": g31.NATIVE_CASE_SCHEMA,
        "case_id": cell.native_case_id,
        "status": g31.g31_native.COMPLETE,
        "selection": {
            "scale": cell.scale,
            "selected_raw_bag_count": cell.fixed_raw_bag_denominator,
            "selected_segment_count": cell.fixed_segment_population,
        },
        "request_contract": {
            "max_simulation_time": g31.g31_native.FIXED_END_EPOCH,
            "max_events": g31.g31_native.MAX_EVENTS,
        },
        "outcome": {
            "completed_raw_bag_count": count,
            "success": {"denominator_raw_bags": cell.fixed_raw_bag_denominator},
        },
        "timing": timing,
        "safety": {"pass": True, "topology": None},
        "runtime": {"event_limit_reached": False},
    }


def _aggregates() -> tuple[dict, dict]:
    cells = g31.primary_cells()
    hca_rows = [_hca_row(cell) for cell in cells]
    native_cases = [_native_case(cell) for cell in cells]
    hca = {
        "schema": g31.HCA_SCHEMA,
        "status": "COMPLETE",
        "protocol": {"expected_case_count": len(cells)},
        "complete_case_count": len(cells),
        "missing_case_ids": [],
        "invalid_case_ids": [],
        "rows": hca_rows,
    }
    native_ids = [cell.native_case_id for cell in cells]
    native = {
        "schema": g31.NATIVE_SCHEMA,
        "status": "COMPLETE",
        "expected_primary_case_count": len(cells),
        "observed_case_count": len(cells),
        "complete_case_ids": native_ids,
        "failed_case_ids": [],
        "stale_case_ids": [],
        "missing_case_ids": [],
        "cases": native_cases,
    }
    return hca, native


def _by_native_id(rows: list[dict], case_id: str) -> dict:
    return next(row for row in rows if row["native_case_id"] == case_id)


def _paired_artifact(speed: float) -> dict:
    token = f"{speed:g}".replace(".", "p")
    case_id = f"t5_2_nanning_1x_speed_{token}"
    hca_metrics = {
        "min": 59.0 if speed == 2.0 else 49.0 if speed == 2.5 else 42.0,
        "mean": 400.0,
        "p95": 700.0,
        "p99": 900.0,
        "max": 3000.0,
    }
    s4_metrics = {
        "min": 59.001 if speed == 2.0 else hca_metrics["min"] - 0.5,
        "mean": 300.0,
        "p95": 500.0,
        "p99": 600.0,
        "max": 800.0,
    }
    return {
        "schema": g31.paired31.SCHEMA,
        "status": g31.paired31.COMPLETE,
        "case_id": case_id,
        "map_id": g31.MAP_ID,
        "view_role": "SECONDARY_STABLE_TIMING_ONLY",
        "selection": {
            "scale": 1,
            "speed_mps": speed,
            "raw_bag_count": 28_506,
            "segment_count": 43_603,
        },
        "comparison_contract": {
            "same_segment_release_required": True,
            "both_full_raw_bag_populations_required": True,
            "survivor_only_comparison_allowed": False,
            "common_cohort_comparison_allowed": False,
            "capacity_verdict_allowed": False,
        },
        "hca_release_trace": {"pass": True},
        "hca_timing": {
            "pass": True,
            "metrics_seconds": hca_metrics,
        },
        "paired_s4_timing": {
            "status": "FULL_POPULATION_TIMING",
            "raw_bag_count": 28_506,
            "metrics_seconds": s4_metrics,
        },
        "outcome": {"completed_raw_bag_count": 28_506},
        "safety": {"pass": True},
        "runtime": {"event_limit_reached": False},
    }


def _paired_artifacts() -> dict[float, dict]:
    return {speed: _paired_artifact(speed) for speed in (2.0, 2.5, 3.0)}


def _bias_aggregate() -> dict:
    ids = [f"bias_{index}" for index in range(24)]
    return {
        "schema": g31.bias31.AGGREGATE_SCHEMA,
        "status": "COMPLETE",
        "protocol_fidelity": g31.bias31.PROTOCOL_FIDELITY,
        "fresh_exact_primary_target_eligible": False,
        "expected_case_count": 24,
        "complete_case_ids": ids,
        "failed_case_ids": [],
        "stale_case_ids": [],
        "missing_case_ids": [],
    }


def _map2_bias_aggregate() -> dict:
    cases = []
    for case in g31.map2_bias.CASES:
        denominator, segments = g31.map2_native.SCALE_COUNTS[case.scale]
        cases.append(
            {
                "schema": g31.map2_bias.SCHEMA,
                "status": g31.map2_bias.COMPLETE,
                "case_id": case.case_id,
                "case": case.as_dict(),
                "map_id": g31.map2_native.MAP_ID,
                "protocol_fidelity": g31.map2_bias.PROTOCOL_FIDELITY,
                "evidence_role": g31.map2_bias.EVIDENCE_ROLE,
                "fresh_exact_primary_target_eligible": False,
                "cross_map_target_eligible": False,
                "observation_bias": g31.map2_bias.bias_contract(case),
                "selection": {
                    "selected_raw_bag_count": denominator,
                    "selected_segment_count": segments,
                },
                "outcome": {"completed_raw_bag_count": denominator},
                "timing": {"status": "S4_FULL_POPULATION_DESCRIPTIVE"},
                "safety": {"pass": True},
            }
        )
    ids = [case["case_id"] for case in cases]
    return {
        "schema": g31.map2_bias.AGGREGATE_SCHEMA,
        "status": "COMPLETE",
        "map_id": g31.map2_native.MAP_ID,
        "protocol_fidelity": g31.map2_bias.PROTOCOL_FIDELITY,
        "evidence_role": g31.map2_bias.EVIDENCE_ROLE,
        "fresh_exact_primary_target_eligible": False,
        "cross_map_target_eligible": False,
        "expected_case_count": 24,
        "complete_case_ids": ids,
        "failed_case_ids": [],
        "stale_case_ids": [],
        "missing_case_ids": [],
        "cases": cases,
    }


def _map2_native_case(case: g31.map2_native.CaseSpec) -> dict:
    denominator, segments = g31.map2_native.SCALE_COUNTS[case.scale]
    return {
        "schema": g31.map2_native.SCHEMA,
        "status": g31.map2_native.COMPLETE,
        "case_id": case.case_id,
        "case": case.as_dict(),
        "selection": {
            "selected_raw_bag_count": denominator,
            "selected_segment_count": segments,
        },
        "request_contract": {
            "max_simulation_time": g31.map2_native.FIXED_END_EPOCH,
            "max_events": g31.map2_native.MAX_EVENTS,
        },
        "outcome": {"completed_raw_bag_count": denominator},
        "safety": {"pass": True, "topology": None},
        "runtime": {"event_limit_reached": False},
    }


def _map2_aggregate() -> dict:
    cases = [_map2_native_case(case) for case in g31.map2_native.PRIMARY_CASES]
    ids = [case["case_id"] for case in cases]
    return {
        "schema": g31.map2_native.AGGREGATE_SCHEMA,
        "protocol": g31.map2_native.FINAL_POLICY_PROTOCOL,
        "status": "COMPLETE",
        "expected_executable_case_count": 38,
        "expected_stable_speed_case_count": 8,
        "expected_measurable_fault_case_count": 30,
        "not_measurable_case_count": 2,
        "observed_current_case_count": 38,
        "complete_case_ids": ids,
        "failed_case_ids": [],
        "stale_case_ids": [],
        "missing_case_ids": [],
        "cases": cases,
    }


def _map2_hca_1x_report() -> dict:
    table_52 = []
    for speed in g31.map2_native.SPEEDS_MPS:
        for metric in ("min", "mean", "max"):
            table_52.append(
                {
                    "speed_mps": speed,
                    "metric": f"tth_{metric}_minutes",
                    "measurement_status": "MEASURED",
                    "hca_evidence": "EXACT_FRESH",
                    "hca_value": 1.0,
                }
            )
    denominator = g31.map2_native.SCALE_COUNTS[1][0]
    table_55 = [
        {
            "row_id": case.fault_scenario,
            "measurement_status": "MEASURED",
            "hca_evidence": "EXACT_FRESH",
            "hca_primary_success": (denominator - 1) / denominator,
        }
        for case in g31.map2_native.PRIMARY_CASES
        if case.scale == 1 and case.group == "all_day_line_interruption"
    ]
    return {
        "schema": "czr005.g4irsf26.reporting.v1",
        "tables": {"5.2": table_52, "5.5": table_55},
    }


def _map2_hca_2x_aggregate() -> dict:
    denominator = g31.map2_native.SCALE_COUNTS[2][0]
    rows = []
    for case in g31.map2_native.PRIMARY_CASES:
        if case.scale != 2:
            continue
        repeats = 2 if case.group == "stable_speed" else 1
        rows.append(
            {
                "case_id": g31._map2_hca_case_id(case),
                "execution_class": "PRIMARY_MEASURABLE",
                "primary_capacity_eligible": True,
                "fixed_horizon_pass": True,
                "repeats_expected": repeats,
                "repeats_complete": repeats,
                "canonical_complete_raw_bag_count_by_repeat": [
                    denominator - 1
                ]
                * repeats,
            }
        )
    return {
        "schema": "czr005.g4irsf29.hca_campaign.v1",
        "status": "COMPLETE_WITH_ARCHIVED_ONLY_GAP",
        "protocol": {"primary_case_count": 19},
        "primary_complete_case_count": 19,
        "missing_primary_case_ids": [],
        "invalid_primary_case_ids": [],
        "rows": rows,
    }


def _map2_paired_artifact(speed: float) -> dict:
    token = f"{speed:g}".replace(".", "p")
    hca = {"min": 100.0, "mean": 200.0, "p95": 300.0, "p99": 400.0, "max": 500.0}
    s4 = {"min": 100.001, "mean": 150.0, "p95": 200.0, "p99": 250.0, "max": 300.0}
    return {
        "schema": g31.map2_paired.SCHEMA,
        "status": g31.map2_paired.COMPLETE,
        "case_id": f"t5_2_map2_1x_speed_{token}",
        "map_id": g31.map2_native.MAP_ID,
        "view_role": "SECONDARY_STABLE_TIMING_ONLY",
        "selection": {
            "scale": 1,
            "speed_mps": speed,
            "raw_bag_count": 28_506,
            "segment_count": 43_603,
        },
        "comparison_contract": {
            "same_segment_release_required": True,
            "both_frameworks_full_raw_bag_populations_required": True,
            "survivor_only_comparison_allowed": False,
            "common_cohort_comparison_allowed": False,
            "capacity_verdict_allowed": False,
        },
        "hca_release_trace": {"pass": True},
        "hca_timing": {"pass": True, "metrics_seconds": hca},
        "paired_s4_timing": {"metrics_seconds": s4},
        "outcome": {"completed_raw_bag_count": 28_506},
        "safety": {"pass": True},
        "runtime": {"event_limit_reached": False},
    }


def _map2_paired_artifacts() -> dict[float, dict]:
    return {
        speed: _map2_paired_artifact(speed)
        for speed in g31.map2_native.SPEEDS_MPS
    }


def _map2_inputs() -> dict:
    return {
        "map2_aggregate": _map2_aggregate(),
        "map2_hca_1x_report": _map2_hca_1x_report(),
        "map2_hca_2x_aggregate": _map2_hca_2x_aggregate(),
        "map2_paired_artifacts": _map2_paired_artifacts(),
    }


def test_primary_registry_is_eight_stable_plus_thirty_two_fault_cells() -> None:
    cells = g31.primary_cells()

    assert len(cells) == 40
    assert sum(cell.group == "stable_speed" for cell in cells) == 8
    assert sum(cell.group == "all_day_line_interruption" for cell in cells) == 32
    assert {cell.fixed_raw_bag_denominator for cell in cells if cell.scale == 1} == {
        28_506
    }
    assert {cell.fixed_raw_bag_denominator for cell in cells if cell.scale == 2} == {
        57_012
    }
    assert (
        _by_native_id(
            [cell.__dict__ for cell in cells],
            "t5_2_nanning_1x_speed_1p5",
        )["hca_case_id"]
        == "nanning_1x_t5_2_speed_1p5"
    )


def test_one_millisecond_min_boundary_is_a_non_win_resolution_tie() -> None:
    boundary = g31.classify_cross_framework_timing_metric(
        "min", 59.0, 59.0010000000002
    )

    assert boundary["strict_numeric_order"] == "HCA_LOWER"
    assert boundary["verdict"] == g31.PHYSICAL_SEMANTICS_RESOLUTION_TIE
    assert boundary["candidate_boundary"] is True
    assert boundary["counts_as_s4_win"] is False
    assert boundary["counts_as_hca_win"] is False
    assert boundary["counts_as_tie"] is True

    clear_win = g31.classify_cross_framework_timing_metric(
        "min", 49.0, 48.401
    )
    assert clear_win["verdict"] == "S4_LOWER"
    assert clear_win["counts_as_s4_win"] is True
    assert clear_win["candidate_boundary"] is False

    non_min = g31.classify_cross_framework_timing_metric(
        "mean", 59.0, 59.001
    )
    assert non_min["verdict"] == "HCA_LOWER"
    assert non_min["candidate_boundary"] is False


def test_complete_matrix_evaluates_capacity_before_full_population_timing() -> None:
    hca, native = _aggregates()
    payload = g31.build_report(_manifests(), hca, native)

    assert payload["status"] == g31.MATRIX_READY
    assert payload["capacity_summary"]["verdict_counts"] == {"S4_WIN": 40}
    assert payload["fresh_target"]["target_met"] is None
    assert payload["fresh_target"]["final_policy_pending"] is True
    stable = _by_native_id(
        payload["primary_rows"], "t5_2_nanning_1x_speed_1p5"
    )
    assert stable["capacity"]["verdict"] == "S4_WIN"
    assert stable["timing"]["status"] == "N_A_HCA_BASELINE_INCOMPLETE"
    assert stable["timing"][
        "own_source_timing_cross_algorithm_verdict_allowed"
    ] is False
    boundary = payload["protocol"]["cross_framework_min_candidate_boundary"]
    assert boundary["status"] == g31.PHYSICAL_SEMANTICS_RESOLUTION_TIE
    assert boundary["maximum_absolute_difference_seconds"] == 0.001
    assert boundary["counts_as_win"] is False
    assert boundary["final_policy"] == "ACTIVE_REPORTING_RULE"

    stable_cell = next(
        cell
        for cell in g31.primary_cells()
        if cell.native_case_id == "t5_2_nanning_1x_speed_1p5"
    )
    hca["rows"][0] = _hca_row(
        stable_cell, completed=stable_cell.fixed_raw_bag_denominator
    )
    ready = g31.build_report(_manifests(), hca, native)
    stable = _by_native_id(ready["primary_rows"], stable_cell.native_case_id)
    assert stable["capacity"]["verdict"] == "FULL_POPULATION_CEILING_TIE"
    assert stable["timing"]["status"] == "N_A_HCA_BASELINE_INCOMPLETE"


def test_fault_cells_are_capacity_only_and_never_release_paired() -> None:
    hca, native = _aggregates()
    fault_cell = next(
        cell
        for cell in g31.primary_cells()
        if cell.native_case_id == "t5_5_nanning_1x_fault_single_4"
    )
    index = next(
        index
        for index, row in enumerate(hca["rows"])
        if row["case_id"] == fault_cell.hca_case_id
    )
    hca["rows"][index] = _hca_row(
        fault_cell, completed=fault_cell.fixed_raw_bag_denominator
    )

    payload = g31.build_report(_manifests(), hca, native)
    row = _by_native_id(payload["primary_rows"], fault_cell.native_case_id)

    assert row["capacity"]["verdict"] == "FULL_POPULATION_CEILING_TIE"
    assert row["timing"]["status"] == "FAULT_CAPACITY_ONLY_NOT_RELEASE_PAIRED"
    assert row["timing"]["fault_release_pairing"] == "NOT_RELEASE_PAIRED"
    assert payload["protocol"]["fault_release_paired"] is False


def test_partial_aggregate_is_diagnostic_and_never_predeclares_a_verdict() -> None:
    hca, native = _aggregates()
    missing = native["cases"].pop()
    native["complete_case_ids"].remove(missing["case_id"])
    native["status"] = "PARTIAL"
    native["observed_case_count"] = 39
    native["missing_case_ids"] = [missing["case_id"]]

    payload = g31.build_report(_manifests(), hca, native)

    assert payload["status"] == g31.PARTIAL_DIAGNOSTIC
    assert payload["input_diagnostics"]["portable_matrix_complete"] is False
    assert payload["fresh_target"]["target_met"] is None
    assert payload["capacity_summary"]["verdict_counts"] == {}
    assert all(
        row["capacity"]["verdict"] == g31.NOT_EVALUATED_PARTIAL
        for row in payload["primary_rows"]
    )


def test_manifest_denominators_and_paper_context_are_validation_gates_only() -> None:
    hca, native = _aggregates()
    manifests = _manifests()
    manifests[2]["raw_task_count"] = 57_011

    payload = g31.build_report(manifests, hca, native)

    assert payload["status"] == g31.PARTIAL_DIAGNOSTIC
    assert payload["input_diagnostics"]["workloads"]["2"]["ready"] is False
    assert payload["paper_context"]["table_5_3"]["drives_fresh_target"] is False
    assert payload["paper_context"]["table_5_4"]["status"] == (
        "NON_EXACT_CONTEXT_PARTIAL_OR_UNAVAILABLE"
    )
    assert payload["paper_context"]["table_5_4"]["drives_fresh_target"] is False
    assert payload["fresh_target"]["table_5_3_or_5_4_drives_target"] is False


def test_same_release_artifacts_supply_all_15_cross_algorithm_timing_metrics() -> None:
    hca, native = _aggregates()
    payload = g31.build_report(
        _manifests(), hca, native, paired_artifacts=_paired_artifacts()
    )

    timing = payload["same_hca_release_timing"]
    assert timing["status"] == "COMPLETE_SAME_HCA_RELEASE_TIMING"
    assert timing["eligible_artifact_count"] == 3
    assert timing["eligible_metric_count"] == 15
    assert timing["verdict_counts"] == {
        g31.PHYSICAL_SEMANTICS_RESOLUTION_TIE: 1,
        "S4_LOWER": 14,
    }
    assert timing["own_source_timing_used_for_cross_algorithm_verdict"] is False
    speed_1p5 = next(row for row in timing["slots"] if row["speed_mps"] == 1.5)
    assert speed_1p5["status"] == "N_A_HCA_BASELINE_INCOMPLETE"
    speed_2 = next(row for row in timing["slots"] if row["speed_mps"] == 2.0)
    minimum = next(row for row in speed_2["metric_rows"] if row["metric"] == "min")
    assert minimum["verdict"] == g31.PHYSICAL_SEMANTICS_RESOLUTION_TIE
    assert minimum["counts_as_s4_win"] is False
    assert minimum["counts_as_hca_win"] is False

    stable_1x = _by_native_id(
        payload["primary_rows"], "t5_2_nanning_1x_speed_2"
    )
    stable_2x = _by_native_id(
        payload["primary_rows"], "t5_2_nanning_2x_speed_2"
    )
    assert stable_1x["timing"]["status"] == (
        "ELIGIBLE_FULL_POPULATION_SAME_HCA_RELEASE"
    )
    assert stable_2x["timing"]["status"] == (
        "SAME_RELEASE_TIMING_NOT_REGISTERED_FOR_2X"
    )
    assert payload["fresh_target"]["target_met"] is True
    assert payload["fresh_target"]["final_policy_pending"] is False


def test_complete_capacity_with_missing_paired_artifact_never_declares_target_met() -> None:
    hca, native = _aggregates()
    paired = _paired_artifacts()
    paired.pop(2.5)

    payload = g31.build_report(
        _manifests(), hca, native, paired_artifacts=paired
    )

    assert payload["status"] == g31.MATRIX_READY
    assert payload["same_hca_release_timing"]["all_required_artifacts_ready"] is False
    assert payload["fresh_target"]["evaluation_status"] == (
        "NOT_EVALUATED_PAIRED_TIMING_INCOMPLETE"
    )
    assert payload["fresh_target"]["target_met"] is None


def test_non_min_hca_timing_win_is_an_evaluated_target_failure() -> None:
    hca, native = _aggregates()
    paired = _paired_artifacts()
    paired[3.0]["paired_s4_timing"]["metrics_seconds"]["mean"] = 401.0

    payload = g31.build_report(
        _manifests(), hca, native, paired_artifacts=paired
    )

    assert payload["fresh_target"]["evaluation_status"] == (
        "EVALUATED_COMPLETE_PRIMARY_AND_PAIRED_EVIDENCE"
    )
    assert payload["fresh_target"]["target_met"] is False


def test_bias_remains_context_only_and_complete_map2_drives_cross_map_target() -> None:
    hca, native = _aggregates()
    payload = g31.build_report(
        _manifests(),
        hca,
        native,
        paired_artifacts=_paired_artifacts(),
        bias_aggregate=_bias_aggregate(),
        map2_bias_aggregate=_map2_bias_aggregate(),
        **_map2_inputs(),
    )

    table_5_4 = payload["paper_context"]["table_5_4"]
    assert table_5_4["status"] == "NON_EXACT_CONTEXT_AVAILABLE_BOTH_MAPS"
    assert table_5_4["drives_fresh_target"] is False
    assert table_5_4["bias_aggregate"]["target_contribution"] is None
    map2_bias = table_5_4["maps"]["map2"]
    assert map2_bias["ready"] is True
    assert map2_bias["admitted_case_count"] == 24
    assert map2_bias["full_population_case_count"] == 24
    assert map2_bias["all_safety_pass"] is True
    assert map2_bias["cross_algorithm_verdict_generated"] is False
    map2 = payload["map2_context"]
    assert map2["status"] == "COMPLETE_MAP2_CROSS_ALGORITHM_EVIDENCE"
    assert map2["capacity"]["verdict_counts"] == {
        "FULL_POPULATION_CEILING_TIE": 4,
        "S4_WIN": 34,
    }
    assert map2["same_hca_release_timing"]["verdict_counts"] == {
        g31.PHYSICAL_SEMANTICS_RESOLUTION_TIE: 4,
        "S4_LOWER": 16,
    }
    assert map2["target_met"] is True
    assert map2["drives_nanning_target"] is False
    assert payload["fresh_target"]["target_met"] is True
    assert payload["cross_map_target"]["target_met"] is True
    quantitative = payload["capacity_quantitative_summary"]
    assert len(quantitative["groups"]) == 8
    assert quantitative["cross_map_total"]["strict_wins"] == 74
    assert quantitative["cross_map_total"]["ties"] == 4
    assert quantitative["cross_map_total"]["strict_losses"] == 0
    assert payload["protocol"]["capacity_is_segment_release_paired"] is False


def test_map2_never_forms_cross_map_conclusion_before_all_38_cells() -> None:
    hca, native = _aggregates()
    map2_inputs = _map2_inputs()
    missing = map2_inputs["map2_aggregate"]["cases"].pop()
    map2_inputs["map2_aggregate"]["complete_case_ids"].remove(
        missing["case_id"]
    )
    map2_inputs["map2_aggregate"]["status"] = "PARTIAL"
    map2_inputs["map2_aggregate"]["observed_current_case_count"] = 37
    map2_inputs["map2_aggregate"]["missing_case_ids"] = [missing["case_id"]]

    payload = g31.build_report(
        _manifests(),
        hca,
        native,
        paired_artifacts=_paired_artifacts(),
        **map2_inputs,
    )

    assert payload["fresh_target"]["target_met"] is True
    assert payload["map2_context"]["ready"] is False
    assert payload["map2_context"]["target_met"] is None
    assert payload["cross_map_target"]["target_met"] is None


def test_partial_cli_writes_no_final_outputs(
    tmp_path: Path, capsys
) -> None:
    manifests = _manifests()
    hca, native = _aggregates()
    paths = {
        "one": tmp_path / "one.json",
        "two": tmp_path / "two.json",
        "hca": tmp_path / "hca.json",
        "native": tmp_path / "native.json",
    }
    paths["one"].write_text(json.dumps(manifests[1]), encoding="utf-8")
    paths["two"].write_text(json.dumps(manifests[2]), encoding="utf-8")
    paths["hca"].write_text(json.dumps(hca), encoding="utf-8")
    paths["native"].write_text(json.dumps(native), encoding="utf-8")
    args = [
        "--manifest-1x",
        str(paths["one"]),
        "--manifest-2x",
        str(paths["two"]),
        "--hca-aggregate",
        str(paths["hca"]),
        "--native-aggregate",
        str(paths["native"]),
        "--paired-dir",
        str(tmp_path / "missing-paired"),
        "--bias-aggregate",
        str(tmp_path / "missing-bias.json"),
        "--map2-aggregate",
        str(tmp_path / "missing-map2.json"),
        "--map2-hca-1x-report",
        str(tmp_path / "missing-map2-hca-1x.json"),
        "--map2-hca-2x-aggregate",
        str(tmp_path / "missing-map2-hca-2x.json"),
        "--map2-paired-dir",
        str(tmp_path / "missing-map2-paired"),
        "--map2-bias-aggregate",
        str(tmp_path / "missing-map2-bias.json"),
        "--json-output",
        str(tmp_path / "report.json"),
        "--csv-output",
        str(tmp_path / "report.csv"),
        "--markdown-output",
        str(tmp_path / "report.md"),
        "--require-complete",
    ]

    assert g31.main(args) == 2
    printed = json.loads(capsys.readouterr().out)
    assert printed["status"] == g31.MATRIX_READY
    assert printed["final_outputs_written"] is False
    assert printed["final_evidence_complete"] is False
    assert set(tmp_path.iterdir()) == set(paths.values())

    paths["native"].unlink()
    assert g31.main(args) == 2
    partial = json.loads(capsys.readouterr().out)
    assert partial["status"] == g31.PARTIAL_DIAGNOSTIC


def test_complete_cli_writes_and_byte_validates_portable_reports(
    tmp_path: Path, capsys
) -> None:
    manifests = _manifests()
    hca, native = _aggregates()
    manifest_1x = tmp_path / "one.json"
    manifest_2x = tmp_path / "two.json"
    hca_path = tmp_path / "hca.json"
    native_path = tmp_path / "native.json"
    paired_dir = tmp_path / "paired"
    paired_dir.mkdir()
    map2 = _map2_inputs()
    map2_aggregate_path = tmp_path / "map2.json"
    map2_hca_1x_path = tmp_path / "map2-hca-1x.json"
    map2_hca_2x_path = tmp_path / "map2-hca-2x.json"
    map2_bias_path = tmp_path / "map2-bias.json"
    map2_paired_dir = tmp_path / "map2-paired"
    map2_paired_dir.mkdir()
    manifest_1x.write_text(json.dumps(manifests[1]), encoding="utf-8")
    manifest_2x.write_text(json.dumps(manifests[2]), encoding="utf-8")
    hca_path.write_text(json.dumps(hca), encoding="utf-8")
    native_path.write_text(json.dumps(native), encoding="utf-8")
    map2_aggregate_path.write_text(
        json.dumps(map2["map2_aggregate"]), encoding="utf-8"
    )
    map2_hca_1x_path.write_text(
        json.dumps(map2["map2_hca_1x_report"]), encoding="utf-8"
    )
    map2_hca_2x_path.write_text(
        json.dumps(map2["map2_hca_2x_aggregate"]), encoding="utf-8"
    )
    map2_bias_path.write_text(
        json.dumps(_map2_bias_aggregate()), encoding="utf-8"
    )
    for speed, artifact in _paired_artifacts().items():
        token = f"{speed:g}".replace(".", "p")
        (paired_dir / f"t5_2_nanning_1x_speed_{token}.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )
    for speed, artifact in map2["map2_paired_artifacts"].items():
        token = f"{speed:g}".replace(".", "p")
        (map2_paired_dir / f"t5_2_map2_1x_speed_{token}.json").write_text(
            json.dumps(artifact), encoding="utf-8"
        )
    outputs = {
        "json": tmp_path / "report.json",
        "csv": tmp_path / "report.csv",
        "markdown": tmp_path / "report.md",
    }
    args = [
        "--manifest-1x",
        str(manifest_1x),
        "--manifest-2x",
        str(manifest_2x),
        "--hca-aggregate",
        str(hca_path),
        "--native-aggregate",
        str(native_path),
        "--paired-dir",
        str(paired_dir),
        "--bias-aggregate",
        str(tmp_path / "missing-bias.json"),
        "--map2-aggregate",
        str(map2_aggregate_path),
        "--map2-hca-1x-report",
        str(map2_hca_1x_path),
        "--map2-hca-2x-aggregate",
        str(map2_hca_2x_path),
        "--map2-paired-dir",
        str(map2_paired_dir),
        "--map2-bias-aggregate",
        str(map2_bias_path),
        "--json-output",
        str(outputs["json"]),
        "--csv-output",
        str(outputs["csv"]),
        "--markdown-output",
        str(outputs["markdown"]),
        "--require-complete",
    ]

    assert g31.main(args) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["final_evidence_complete"] is True
    assert printed["final_outputs_written"] is True
    assert json.loads(outputs["json"].read_text(encoding="utf-8"))[
        "cross_map_target"
    ]["target_met"] is True
    assert len(outputs["csv"].read_text(encoding="utf-8").splitlines()) == 114
    markdown = outputs["markdown"].read_text(encoding="utf-8")
    assert "fresh_target_met=true" in markdown
    assert "cross_map_target_met=true" in markdown
    assert "74W / 4T / 0L" in markdown
    assert "逐 segment release-paired" in markdown
    assert "admitted=24/24" in markdown
    assert "不生成跨算法胜负" in markdown

    assert g31.main(["--validate-committed", *args]) == 0
    capsys.readouterr()
    outputs["markdown"].write_text("stale\n", encoding="utf-8")
    assert g31.main(["--validate-committed", *args]) == 2
