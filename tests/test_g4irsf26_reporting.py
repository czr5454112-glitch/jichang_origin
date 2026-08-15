from __future__ import annotations

import csv
import io
import json
from pathlib import Path

from scripts.eval import run_g4irsf26_reporting as reporting


def _distribution(minimum: float, mean: float, maximum: float) -> dict[str, object]:
    return {
        "count": reporting.CANONICAL_RAW_BAGS,
        "seconds": {
            "min": minimum * 60.0,
            "mean": mean * 60.0,
            "max": maximum * 60.0,
        },
        "minutes": {"min": minimum, "mean": mean, "max": maximum},
    }


def _hca(
    speed: float = 2.5,
    *,
    minimum: float = 3.0,
    mean: float = 4.0,
    maximum: float = 5.9,
    fault_schedule: str = "none",
    completed_raw_bags: int = reporting.CANONICAL_RAW_BAGS,
) -> dict[str, object]:
    complete = completed_raw_bags == reporting.CANONICAL_RAW_BAGS
    fault_event_count = str(fault_schedule.count(":fault"))
    return {
        "schema": "g4irsf24.fresh_hca.metrics.v1",
        "run_id": "run_01",
        "status": "complete",
        "speed_mps": speed,
        "fault_schedule": fault_schedule,
        "comparison_eligible": complete,
        "canonical_segment_count": reporting.CANONICAL_SEGMENTS,
        "canonical_raw_bag_count": reporting.CANONICAL_RAW_BAGS,
        "released_segment_count": reporting.CANONICAL_SEGMENTS,
        "completed_segment_count": (
            reporting.CANONICAL_SEGMENTS if complete else 40_000
        ),
        "canonical_complete_raw_bag_count": completed_raw_bags,
        "benchmark_summary": {
            "start_epoch": "8260",
            "max_epochs": "90000",
            "last_epoch": "98259.0",
            "fault_event_count": fault_event_count,
            "repair_event_count": "0",
        },
        "denominators": {
            "processed_attempt": _distribution(minimum, mean, maximum),
            "java_release": _distribution(minimum, mean, maximum),
            "raw_entry": _distribution(minimum, mean, maximum),
        },
    }


def _s4(
    case_id: str,
    table: str,
    *,
    standard_speed: float = 2.5,
    actual_speed: float | None = None,
    deviation: int = 0,
    line_ids: tuple[int, ...] = (),
    minimum: float = 3.0,
    mean: float = 4.1,
    maximum: float = 5.8,
    completed_raw_bags: int = reporting.CANONICAL_RAW_BAGS,
    std_count: int | None = None,
    literal_count: int | None = None,
) -> dict[str, object]:
    actual = standard_speed if actual_speed is None else actual_speed
    is_fault = bool(line_ids)
    business_failed = reporting.CANONICAL_RAW_BAGS - completed_raw_bags
    seed_edges = reporting._expected_fault_edges(line_ids) if is_fault else ()
    return {
        "schema": "czr005.g4irsf26.paper_s4_case.v1",
        "status": "COMPLETE_FIXED_HORIZON" if is_fault else "COMPLETE",
        "case": {
            "case_id": case_id,
            "case_role": (
                "nominal_reference" if table == "5.2" else "experiment"
            ),
            "paper_tables": [table],
            "standard_speed_mps": standard_speed,
            "actual_speed_mps": actual,
            "deviation_percent": deviation,
            "fault_line_ids": list(line_ids),
            "seed_edges": [list(edge) for edge in seed_edges],
        },
        "protocol": {
            "exact_fresh_status": "EXACT_G24_LIFECYCLE_ALIGNED",
            "exact_hca_release_alignment": {
                "aligned_segment_count": reporting.CANONICAL_SEGMENTS,
                "source": reporting.REGISTERED_RELEASE_SOURCE_BY_SPEED[
                    standard_speed
                ],
            },
            "segment_count": reporting.CANONICAL_SEGMENTS,
            "raw_bag_count": reporting.CANONICAL_RAW_BAGS,
            "paper_raw_bag_tth_denominator": (
                "sum_over_segments(finish_time-admitted_time)"
            ),
        },
        "outcome": {
            "requested_segment_count": reporting.CANONICAL_SEGMENTS,
            "runtime_completed_segment_count": (
                reporting.CANONICAL_SEGMENTS - business_failed
                if is_fault
                else reporting.CANONICAL_SEGMENTS
            ),
            "completed_raw_bag_count": completed_raw_bags,
            "business_failed_raw_bag_count": business_failed,
            "business_failure_is_safety_failure": False,
            "business_and_safety_axes_are_separate": True,
            "paper_raw_bag_tth": {
                "denominator": "sum_over_segments(finish_time-admitted_time)",
                "distribution": _distribution(minimum, mean, maximum),
            },
            "success": {
                "primary_completed_raw_bags": {
                    "count": completed_raw_bags,
                    "rate": completed_raw_bags / reporting.CANONICAL_RAW_BAGS,
                },
                "finish_le_std": {
                    "count": std_count,
                    "rate": (
                        std_count / reporting.CANONICAL_RAW_BAGS
                        if std_count is not None
                        else None
                    ),
                },
                "finish_le_std_minus_2700_literal": {
                    "count": literal_count,
                    "rate": (
                        literal_count / reporting.CANONICAL_RAW_BAGS
                        if literal_count is not None
                        else None
                    ),
                },
            },
        },
        "safety": {
            "admission": {
                "pass": True,
                "mode": (
                    "TABLE_5_5_FIXED_HORIZON_SAFETY"
                    if is_fault
                    else "G24_STRICT_S4"
                ),
            },
            "strict_s4": {"pass": not is_fault},
        },
    }


def _topology_s4(
    *, completed_raw_bags: int = 7_777, upper_bound: int | None = None
) -> dict[str, object]:
    case = _s4(
        "t5_5_fault_pair_4_5",
        "5.5",
        line_ids=(4, 5),
        completed_raw_bags=completed_raw_bags,
        std_count=6_666,
        literal_count=5_555,
    )
    case["status"] = "COMPLETE_TOPOLOGY_SATURATED"
    outcome = case["outcome"]
    assert isinstance(outcome, dict)
    outcome["topology_reachable_raw_bag_upper_bound"] = (
        completed_raw_bags if upper_bound is None else upper_bound
    )
    outcome["primary_success_topology_saturated"] = True
    outcome["secondary_metrics_censored_by_event_limit"] = True
    outcome["admitted_claim_scope"] = "TABLE_5_5_PRIMARY_SUCCESS_RATE_ONLY"
    safety = case["safety"]
    assert isinstance(safety, dict)
    admission = safety["admission"]
    assert isinstance(admission, dict)
    admission["mode"] = "TABLE_5_5_TOPOLOGY_SATURATION_EVIDENCE"
    safety["topology_saturation_fault"] = {"pass": True}
    return case


def _row(payload: dict[str, object], table: str, row_id: str) -> dict[str, object]:
    rows = payload["tables"][table]  # type: ignore[index]
    return next(row for row in rows if row["row_id"] == row_id)


def test_embedded_paper_contract_and_line_mapping_are_complete() -> None:
    assert len(reporting.PAPER_TABLE_5_2) == 4
    assert len(reporting.PAPER_TABLE_5_3) == 3
    assert len(reporting.PAPER_TABLE_5_4) == 12
    assert len(reporting.PAPER_TABLE_5_5) == 16
    assert reporting.INTERRUPTION_EDGE_BY_ID == {
        1: (6, 12),
        2: (8, 11),
        3: (13, 23),
        4: (24, 27),
        5: (14, 46),
        6: (43, 15),
        7: (33, 44),
        8: (31, 32),
    }
    assert reporting.RECONSTRUCTED_69_EDGE_LINE_IDS == {1, 6, 7}
    assert reporting.PAIR_5_7_ARCHIVED_WORKBOOK_EDGES == (
        (33, 44),
        (46, 36),
    )
    assert reporting._expected_fault_edges((5, 7)) == (
        (33, 44),
        (46, 36),
    )
    assert reporting.INTERRUPTION_EDGE_BY_ID[5] == (14, 46)
    assert reporting.INTERRUPTION_EDGE_BY_ID[7] == (33, 44)


def test_speed_verdict_is_computed_per_cell_and_missing_cells_stay_unmeasured() -> None:
    payload = reporting.build_report_payload(
        hca_payloads=[_hca(mean=4.0)],
        s4_payloads=[_s4("t5_2_speed_2p5", "5.2", mean=4.1)],
    )

    minimum = _row(payload, "5.2", "speed_2.5_min")
    mean = _row(payload, "5.2", "speed_2.5_mean")
    missing = _row(payload, "5.2", "speed_1.5_mean")
    assert minimum["s4_vs_archived"] == "S4_WIN"
    assert mean["s4_vs_archived"] == "ORIGINAL_WIN"
    assert mean["s4_vs_fresh_hca"] == "ORIGINAL_WIN"
    assert missing["measurement_status"] == reporting.NOT_MEASURED
    assert missing["s4_vs_archived"] == reporting.NOT_MEASURED


def test_speed_repeats_require_consistent_min_mean_and_max() -> None:
    reference = _s4(
        "t5_2_speed_2p5", "5.2", minimum=3.0, mean=4.0, maximum=5.9
    )
    for conflicting in (
        _s4(
            "t5_2_speed_2p5",
            "5.2",
            minimum=3.1,
            mean=4.0,
            maximum=5.9,
        ),
        _s4(
            "t5_2_speed_2p5",
            "5.2",
            minimum=3.0,
            mean=4.0,
            maximum=6.0,
        ),
    ):
        payload = reporting.build_report_payload(
            s4_payloads=[reference, conflicting]
        )
        speed_rows = [
            row
            for row in payload["tables"]["5.2"]
            if row["speed_mps"] == 2.5
        ]
        assert all(
            row["measurement_status"] == reporting.NOT_MEASURED
            for row in speed_rows
        )
        assert all(row["s4_value"] is None for row in speed_rows)


def test_table_5_4_requires_both_exact_speed_runs() -> None:
    degraded = _s4(
        "t5_4_std_2p5_dev_10",
        "5.4",
        standard_speed=2.5,
        actual_speed=2.25,
        deviation=10,
        mean=4.2,
    )
    partial = reporting.build_report_payload(s4_payloads=[degraded])
    partial_row = _row(partial, "5.4", "speed_2.5_dev_10")
    assert partial_row["measurement_status"] == reporting.NOT_MEASURED
    assert partial_row["s4_degraded_value"] is None

    complete = reporting.build_report_payload(
        s4_payloads=[
            _s4("t5_2_speed_2p5", "5.2", mean=4.0),
            degraded,
        ]
    )
    row = _row(complete, "5.4", "speed_2.5_dev_10")
    assert row["s4_evidence"] == reporting.EVIDENCE_RECONSTRUCTED
    assert row["s4_nominal_value"] == 4.0
    assert row["s4_degraded_value"] == 4.2
    assert abs(row["s4_degradation_delta"] - 0.2) < 1.0e-12


def test_s4_aggregate_cases_are_consumed() -> None:
    aggregate = {
        "schema": "czr005.g4irsf26.paper_s4_aggregate.v1",
        "status": "PARTIAL_OR_FAILED",
        "cases": [_s4("t5_2_speed_2p5", "5.2", mean=3.9)],
    }
    payload = reporting.build_report_payload(s4_payloads=[aggregate])
    row = _row(payload, "5.2", "speed_2.5_mean")
    assert row["measurement_status"] == "MEASURED"
    assert row["s4_value"] == 3.9


def test_interruption_primary_and_secondary_denominators_are_explicit() -> None:
    completed = reporting.CANONICAL_RAW_BAGS // 2
    std_count = 10_000
    literal_count = 9_000
    payload = reporting.build_report_payload(
        s4_payloads=[
            _s4(
                "t5_5_fault_single_1",
                "5.5",
                line_ids=(1,),
                completed_raw_bags=completed,
                std_count=std_count,
                literal_count=literal_count,
            )
        ]
    )
    row = _row(payload, "5.5", "single_1")
    assert row["reconstructed_edges"] == "6->12"
    assert row["mapping_evidence"] == reporting.EVIDENCE_RECONSTRUCTED
    assert row["mapping_basis"] == "1:69_EDGE_RECONSTRUCTION"
    assert row["contains_69_edge_reconstruction"] is True
    assert row["s4_primary_success"] == completed / reporting.CANONICAL_RAW_BAGS
    assert row["s4_finish_le_std"] == std_count / reporting.CANONICAL_RAW_BAGS
    assert row["s4_finish_le_std_minus_2700"] == (
        literal_count / reporting.CANONICAL_RAW_BAGS
    )
    assert row["s4_admission_mode"] == "TABLE_5_5_FIXED_HORIZON_SAFETY"
    assert row["s4_business_failed_raw_bags"] == (
        reporting.CANONICAL_RAW_BAGS - completed
    )
    assert row["s4_business_failure_is_safety_failure"] is False
    assert row["s4_secondary_status"] == "MEASURED"
    assert row["s4_vs_fresh_hca_evidence"] == reporting.NOT_MEASURED
    assert row["s4_vs_fresh_hca_release_pairing"] == reporting.NOT_MEASURED


def test_pair_5_7_is_archived_only_when_exact_label_fresh_run_disagrees() -> None:
    stale_s4 = _s4(
        "t5_5_fault_pair_5_7",
        "5.5",
        line_ids=(5, 7),
        completed_raw_bags=8_013,
    )
    stale_s4["case"]["seed_edges"] = [[14, 46], [33, 44]]  # type: ignore[index]
    stale_hca = _hca(
        fault_schedule="8260:14:46:fault;8260:33:44:fault",
        completed_raw_bags=8_013,
    )
    stale = reporting.build_report_payload(
        hca_payloads=[stale_hca], s4_payloads=[stale_s4]
    )
    stale_row = _row(stale, "5.5", "pair_5_7")
    assert stale_row["hca_primary_success"] is None
    assert stale_row["s4_primary_success"] is None
    assert stale_row["s4_vs_archived"] == reporting.NOT_MEASURED

    fresh_s4 = _s4(
        "t5_5_fault_pair_5_7",
        "5.5",
        line_ids=(5, 7),
        completed_raw_bags=13_939,
    )
    fresh_hca = _hca(
        fault_schedule="8260:33:44:fault;8260:46:36:fault",
        completed_raw_bags=13_939,
    )
    fresh = reporting.build_report_payload(
        hca_payloads=[fresh_hca], s4_payloads=[fresh_s4]
    )
    row = _row(fresh, "5.5", "pair_5_7")
    assert row["reconstructed_edges"] == "33->44,46->36"
    assert row["global_line_mapping_edges"] == "14->46,33->44"
    assert row["case_specific_override"] is True
    assert row["mapping_source_inconsistency"] is True
    assert "ARCHIVED_WORKBOOK_LABEL_SOURCE_PROTOCOL_UNRESOLVED" in row[
        "mapping_basis"
    ]
    assert row["fresh_protocol_status"] == (
        reporting.PAIR_5_7_FRESH_PROTOCOL_STATUS
    )
    assert row["paper_value"] == 0.48
    assert row["hca_primary_success"] is None
    assert row["s4_primary_success"] is None
    assert row["hca_evidence"] == reporting.NOT_MEASURED
    assert row["s4_evidence"] == reporting.NOT_MEASURED
    assert row["measurement_status"] == reporting.NOT_MEASURED
    assert row["s4_vs_archived"] == reporting.NOT_MEASURED
    assert row["s4_vs_fresh_hca"] == reporting.NOT_MEASURED


def test_hca_fault_primary_admits_canonical_population_with_partial_release() -> None:
    failed = _hca(
        fault_schedule="8260:8:11:fault",
        completed_raw_bags=25_313,
    )
    failed["released_segment_count"] = 40_411
    failed["completed_segment_count"] = 40_410

    payload = reporting.build_report_payload(hca_payloads=[failed])
    fault_row = _row(payload, "5.5", "single_2")
    speed_row = _row(payload, "5.2", "speed_2.5_mean")

    assert fault_row["hca_evidence"] == reporting.EVIDENCE_EXACT
    assert fault_row["hca_primary_success"] == (
        25_313 / reporting.CANONICAL_RAW_BAGS
    )
    # The Table 5.5 population gate must not relax the timing contract.
    assert speed_row["hca_evidence"] == reporting.NOT_MEASURED
    assert speed_row["hca_value"] is None

    hca, _ = reporting.extract_measurements([failed], [])
    assert hca[0]["exact_cohort"] is True
    assert hca[0]["exact_timing"] is False
    assert hca[0]["fault_protocol_matches_expected"] is True
    assert hca[0]["fault_protocol_exact"] is True


def test_table_5_5_fresh_hca_verdict_is_not_claimed_as_release_paired() -> None:
    hca = _hca(
        fault_schedule="8260:8:11:fault",
        completed_raw_bags=25_313,
    )
    hca["released_segment_count"] = 40_411
    hca["completed_segment_count"] = 40_410
    s4 = _s4(
        "t5_5_fault_single_2",
        "5.5",
        line_ids=(2,),
        completed_raw_bags=25_284,
    )

    payload = reporting.build_report_payload(
        hca_payloads=[hca], s4_payloads=[s4]
    )
    row = _row(payload, "5.5", "single_2")
    assert row["s4_vs_fresh_hca"] == "ORIGINAL_WIN"
    assert row["s4_vs_fresh_hca_evidence"] == (
        reporting.EVIDENCE_PROTOCOL_CONTROLLED
    )
    assert row["s4_vs_fresh_hca_release_pairing"] == (
        "SAME_CANONICAL_POPULATION_AND_FIXED_DENOMINATOR_"
        "NOT_SEGMENT_RELEASE_PAIRED"
    )
    assert "not an exact per-segment release-paired" in (
        payload["protocol"]["interruption_success"]["fresh_hca_comparison_scope"]
    )


def test_hca_fault_primary_rejects_same_edge_with_repair() -> None:
    transient = _hca(
        fault_schedule="8260:8:11:fault;90000:8:11:repair",
        completed_raw_bags=25_313,
    )
    transient["benchmark_summary"]["repair_event_count"] = "1"  # type: ignore[index]

    payload = reporting.build_report_payload(hca_payloads=[transient])
    row = _row(payload, "5.5", "single_2")
    assert row["hca_evidence"] == reporting.NOT_MEASURED
    assert row["hca_primary_success"] is None

    hca, _ = reporting.extract_measurements([transient], [])
    assert hca[0]["fault_protocol_matches_expected"] is True
    assert hca[0]["fault_protocol_exact"] is False


def test_s4_exact_result_rejects_release_source_for_another_speed() -> None:
    case = _s4(
        "t5_2_speed_1p5",
        "5.2",
        standard_speed=1.5,
        mean=3.0,
    )
    case["protocol"]["exact_hca_release_alignment"]["source"] = (  # type: ignore[index]
        reporting.REGISTERED_RELEASE_SOURCE_BY_SPEED[2.5]
    )

    payload = reporting.build_report_payload(s4_payloads=[case])
    row = _row(payload, "5.2", "speed_1.5_mean")
    assert row["measurement_status"] == reporting.NOT_MEASURED
    assert row["s4_vs_archived"] == reporting.NOT_MEASURED


def test_topology_proven_primary_is_admitted_but_secondary_metrics_are_censored() -> None:
    completed = 7_777
    payload = reporting.build_report_payload(
        s4_payloads=[_topology_s4(completed_raw_bags=completed)]
    )
    row = _row(payload, "5.5", "pair_4_5")
    assert row["measurement_status"] == "MEASURED"
    assert row["s4_evidence"] == reporting.EVIDENCE_TOPOLOGY
    assert row["s4_primary_success"] == completed / reporting.CANONICAL_RAW_BAGS
    assert row["s4_topology_reachable_raw_bag_upper_bound"] == completed
    assert row["s4_topology_safety_pass"] is True
    assert row["s4_finish_le_std"] is None
    assert row["s4_finish_le_std_minus_2700"] is None
    assert row["s4_secondary_status"] == "CENSORED_NOT_MEASURED"


def test_topology_primary_requires_upper_bound_equality() -> None:
    payload = reporting.build_report_payload(
        s4_payloads=[_topology_s4(completed_raw_bags=7_777, upper_bound=7_778)]
    )
    row = _row(payload, "5.5", "pair_4_5")
    assert row["measurement_status"] == reporting.NOT_MEASURED
    assert row["s4_evidence"] == reporting.NOT_MEASURED
    assert row["s4_primary_success"] is None


def test_interruption_requires_fixed_horizon_admission() -> None:
    case = _s4("t5_5_fault_single_1", "5.5", line_ids=(1,))
    safety = case["safety"]
    assert isinstance(safety, dict)
    admission = safety["admission"]
    assert isinstance(admission, dict)
    admission["pass"] = False

    payload = reporting.build_report_payload(s4_payloads=[case])
    row = _row(payload, "5.5", "single_1")
    assert row["measurement_status"] == reporting.NOT_MEASURED
    assert row["s4_primary_success"] is None


def test_interruption_without_primary_count_is_not_measured() -> None:
    case = _s4("t5_5_fault_single_1", "5.5", line_ids=(1,))
    outcome = case["outcome"]
    assert isinstance(outcome, dict)
    outcome.pop("completed_raw_bag_count")
    success = outcome["success"]
    assert isinstance(success, dict)
    primary = success["primary_completed_raw_bags"]
    assert isinstance(primary, dict)
    primary.pop("count")

    payload = reporting.build_report_payload(s4_payloads=[case])
    row = _row(payload, "5.5", "single_1")
    assert row["measurement_status"] == reporting.NOT_MEASURED
    assert row["s4_primary_success"] is None
    assert row["s4_vs_archived"] == reporting.NOT_MEASURED


def test_hca_directory_adapter_joins_run_status_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_01"
    run_dir.mkdir()
    metrics = _hca()
    metrics.pop("speed_mps")
    metrics.pop("fault_schedule")
    (run_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (run_dir / "run_status.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "speed_mps": 2.5,
                "fault_schedule": "8260:6:12:fault;90000:6:12:repair",
            }
        ),
        encoding="utf-8",
    )

    payloads, paths = reporting.load_payloads([tmp_path], enrich_hca=True)
    hca, _ = reporting.extract_measurements(payloads, [])
    assert len(paths) == 1
    assert hca[0]["speed_mps"] == 2.5
    assert hca[0]["line_ids"] == (1,)
    assert hca[0]["has_fault"] is True


def test_hca_evidence_root_discovers_nested_campaign_summaries(
    tmp_path: Path,
) -> None:
    expected = []
    for name in ("speed_1p5", "fault_single_2"):
        campaign = tmp_path / name / "fresh_hca_summary.json"
        campaign.parent.mkdir()
        campaign.write_text("{}", encoding="utf-8")
        expected.append(campaign)
    assert reporting._input_files(tmp_path) == sorted(expected)


def test_legacy_2p5_campaign_infers_speed_from_portable_evidence_path(
    tmp_path: Path,
) -> None:
    campaign_dir = tmp_path / "speed_2p5"
    run_dir = campaign_dir / "run_01"
    run_dir.mkdir(parents=True)
    run = _hca()
    run.pop("speed_mps")
    benchmark = run["benchmark_summary"]
    assert isinstance(benchmark, dict)
    benchmark.pop("speed_mps", None)
    campaign = {
        "schema": "g4irsf24.fresh_hca.campaign.v1",
        "runs": [run],
    }
    (campaign_dir / "fresh_hca_summary.json").write_text(
        json.dumps(campaign), encoding="utf-8"
    )
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )

    payloads, _paths = reporting.load_payloads(
        [campaign_dir], enrich_hca=True
    )
    hca, _s4 = reporting.extract_measurements(payloads, [])
    assert hca[0]["speed_mps"] == 2.5
    assert hca[0]["exact_timing"] is True


def test_summary_separates_paper_and_fresh_hca_verdict_counts() -> None:
    payload = reporting.build_report_payload()
    counts = payload["summary"]["comparison_counts"]
    assert "s4_win_count" not in payload["summary"]
    assert counts["s4_vs_paper"] == {
        "cell_count": 61,
        "measured_cell_count": 0,
        "not_measured_cell_count": 61,
        "s4_win_count": 0,
        "original_win_count": 0,
        "tie_count": 0,
    }
    assert counts["s4_vs_fresh_hca"] == {
        "cell_count": 37,
        "measured_cell_count": 0,
        "not_measured_cell_count": 37,
        "s4_win_count": 0,
        "original_win_count": 0,
        "tie_count": 0,
    }


def test_repeat_policy_is_structured_and_visible_in_markdown() -> None:
    payload = reporting.build_report_payload()
    repeat_policy = payload["protocol"]["repeat_policy"]
    assert repeat_policy["table_5_2"] == {
        "fresh_hca_independent_java_process_repeats_per_speed": 2,
        "s4_repeats_per_cell": 1,
    }
    assert repeat_policy["table_5_4"] == {"s4_repeats_per_cell": 1}
    assert repeat_policy["table_5_5"] == {
        "fresh_hca_repeats_per_executable_scenario": 1,
        "s4_repeats_per_executable_scenario": 1,
    }
    assert "not_counted_as_repeats" in repeat_policy["superseded_probe_policy"]

    report = reporting.markdown_report(payload)
    assert "two independent Java-process repeats" in report
    assert "one run per Table 5.2 cell" in report
    assert "not counted as repeats" in report


def test_outcome_summary_is_derived_and_keeps_baselines_separate() -> None:
    no_fault_hca = _hca(mean=4.0)
    no_fault_s4 = _s4("t5_2_speed_2p5", "5.2", mean=3.9)
    fault_hca = _hca(
        fault_schedule="8260:8:11:fault",
        completed_raw_bags=25_313,
    )
    fault_hca["released_segment_count"] = 40_411
    fault_hca["completed_segment_count"] = 40_410
    fault_s4 = _s4(
        "t5_5_fault_single_2",
        "5.5",
        line_ids=(2,),
        completed_raw_bags=25_284,
    )
    payload = reporting.build_report_payload(
        hca_payloads=[no_fault_hca, fault_hca],
        s4_payloads=[no_fault_s4, fault_s4],
    )
    outcomes = payload["summary"]["outcome_summary"]
    assert outcomes["table_5_2_mean_vs_fresh_hca"] == {
        "cell_count": 4,
        "measured_cell_count": 1,
        "not_measured_cell_count": 3,
        "s4_win_count": 1,
        "original_win_count": 0,
        "tie_count": 0,
    }
    assert outcomes["table_5_4_vs_archived_dynamic"]["cell_count"] == 12
    assert outcomes["table_5_4_vs_archived_static"]["cell_count"] == 12
    assert outcomes["table_5_5_vs_fresh_hca"] == {
        "cell_count": 16,
        "measured_cell_count": 1,
        "not_measured_cell_count": 15,
        "s4_win_count": 0,
        "original_win_count": 1,
        "tie_count": 0,
    }

    report = reporting.markdown_report(payload)
    assert "## Outcome summary" in report
    assert "Table 5.2 mean vs fresh HCA: S4 wins 1/1 measured" in report
    assert "S4 does not win every paper experiment." in report
    assert "S4 vs archived static" in report


def test_csv_json_and_markdown_keep_evidence_classes_separate() -> None:
    payload = reporting.build_report_payload()
    csv_rows = list(csv.DictReader(io.StringIO(reporting.csv_text(payload))))
    report = reporting.markdown_report(payload)
    encoded = json.dumps(payload, allow_nan=False)

    assert len(csv_rows) == 49
    assert {row["table_id"] for row in csv_rows} == {"5.2", "5.3", "5.4", "5.5"}
    assert "EXACT_FRESH" in report
    assert "RECONSTRUCTED" in report
    assert "ARCHIVED" in report
    assert "NOT_MEASURED" in report
    assert "does not assume" in report.lower()
    assert "S4 vs fresh HCA" in report
    assert "PROTOCOL_CONTROLLED_RECONSTRUCTION" in report
    assert json.loads(encoded)["schema"] == "czr005.g4irsf26.reporting.v1"
