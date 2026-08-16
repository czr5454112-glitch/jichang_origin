from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from scripts.eval import run_g4irsf27_reporting as reporting


def _g26() -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for index, scenario_id in enumerate(reporting.SCENARIO_IDS):
        if scenario_id == "pair_5_7":
            rows.append(
                {
                    "row_id": scenario_id,
                    "line_ids": "5,7",
                    "measurement_status": reporting.NOT_MEASURED,
                    "paper_value": 0.48,
                    "hca_primary_success": None,
                    "s4_primary_success": None,
                    "fresh_protocol_status": "ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED",
                }
            )
            continue
        reference_raw = 20_000 + index
        rows.append(
            {
                "row_id": scenario_id,
                "line_ids": str(index + 1),
                "measurement_status": reporting.MEASURED,
                "paper_value": reference_raw / reporting.CANONICAL_RAW_BAGS,
                "hca_primary_success": reference_raw / reporting.CANONICAL_RAW_BAGS,
                "s4_primary_success": (reference_raw - 100) / reporting.CANONICAL_RAW_BAGS,
            }
        )
    speed_rows: list[dict[str, object]] = []
    for _, _, row_prefix in reporting.FIFO_SPEED_CASES:
        for metric, paper, hca in (
            ("min", 1.0, 1.00002),
            ("mean", 2.0, 2.0),
            ("max", 3.0, 3.0),
        ):
            speed_rows.append(
                {
                    "row_id": f"{row_prefix}_{metric}",
                    "measurement_status": reporting.MEASURED,
                    "paper_value": paper,
                    "hca_value": hca,
                }
            )
    return {
        "protocol": {"canonical_raw_bag_count": reporting.CANONICAL_RAW_BAGS},
        "tables": {"5.2": speed_rows, "5.5": rows},
    }


def _g27() -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for index, scenario_id in enumerate(reporting.MEASURABLE_SCENARIO_IDS):
        completed = 20_000 + reporting.SCENARIO_IDS.index(scenario_id)
        payloads.append(
            {
                "schema": reporting.G27_CASE_SCHEMA,
                "status": reporting.G27_COMPLETE,
                "case": {"case_id": f"t5_5_fault_{scenario_id}"},
                "outcome": {
                    "selected_raw_bag_count": reporting.CANONICAL_RAW_BAGS,
                    "completed_raw_bag_count": completed,
                    "source_rejected_unreachable_segment_count": 7 + index,
                    "topology_reachable_raw_bag_upper_bound": completed,
                    "success": {
                        "primary_completed_raw_bags": {
                            "count": completed,
                            "rate": completed / reporting.CANONICAL_RAW_BAGS,
                        }
                    },
                },
                "safety": {"admission": {"pass": True}},
            }
        )
    return payloads


def _fifo() -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for case_id, speed, _ in reporting.FIFO_SPEED_CASES:
        payloads.append(
            {
                "schema": reporting.G27_CASE_SCHEMA,
                "status": reporting.G27_COMPLETE,
                "case": {"case_id": case_id, "standard_speed_mps": speed},
                "local_values": {"activation": reporting.FIFO_EXACT_OFF},
                "outcome": {
                    "completed_raw_bag_count": reporting.CANONICAL_RAW_BAGS,
                    "paper_raw_bag_tth": {
                        "distribution": {
                            "minutes": {
                                "min": 1.00003,
                                "mean": 1.9,
                                "p95": 2.4,
                                "p99": 2.6,
                                "max": 2.9,
                            }
                        }
                    },
                },
            }
        )
    return payloads


def test_normal_summary_is_computed_from_integer_completed_counts() -> None:
    payload = reporting.build_report_payload(_g26(), _g27())

    summary = payload["summary"]
    assert summary["measured_row_count"] == 15
    assert summary["not_measured_row_count"] == 1
    assert summary["g27_vs_fresh_hca"] == {
        "cell_count": 16,
        "measured_cell_count": 15,
        "not_measured_cell_count": 1,
        "g27_win_count": 0,
        "tie_count": 15,
        "original_win_count": 0,
    }
    assert summary["all_measured_cases_reach_topology_upper"] is True
    first = payload["rows"][0]
    assert first["g27_completed_raw"] == first["fresh_hca_completed_raw"]
    assert first["g27_vs_fresh_hca"] == "TIE"


def test_missing_required_g27_case_fails_closed() -> None:
    cases = _g27()
    cases.pop()
    with pytest.raises(reporting.ReportingError, match="missing required G27 cases"):
        reporting.build_report_payload(_g26(), cases)


def test_pair_5_7_remains_explicit_archived_only_gap() -> None:
    payload = reporting.build_report_payload(_g26(), _g27())
    row = next(row for row in payload["rows"] if row["scenario_id"] == "pair_5_7")

    assert row["measurement_status"] == reporting.NOT_MEASURED
    assert row["g27_completed_raw"] is None
    assert row["g27_vs_fresh_hca"] == reporting.NOT_MEASURED
    assert row["gap_reason"] == "ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED"

    changed = deepcopy(_g26())
    changed["tables"]["5.5"][12]["measurement_status"] = reporting.MEASURED  # type: ignore[index]
    with pytest.raises(reporting.ReportingError, match="must remain NOT_MEASURED"):
        reporting.build_report_payload(changed, _g27())


def test_discovery_keeps_speed_controls_out_of_fault_inputs(tmp_path: Path) -> None:
    for name in (
        "t5_5_fault_single_1_full.json",
        "t5_2_speed_2p5_fifo_full.json",
        "unrelated_full.json",
    ):
        (tmp_path / name).write_text("{}", encoding="utf-8")

    fault_paths, fifo_paths = reporting.discover_input_paths(tmp_path)

    assert [path.name for path in fault_paths] == ["t5_5_fault_single_1_full.json"]
    assert [path.name for path in fifo_paths] == ["t5_2_speed_2p5_fifo_full.json"]


def test_fifo_speed_summary_reports_tail_and_resolution_bound_min_ties() -> None:
    payload = reporting.build_fifo_speed_payload(_g26(), _fifo())

    assert payload["summary"]["fifo_vs_fresh_hca"] == {
        "cell_count": 12,
        "g27_fifo_win_count": 8,
        "tie_count": 4,
        "resolution_bound_tie_count": 4,
        "original_win_count": 0,
    }
    first = payload["rows"][0]
    assert first["fifo_p95_minutes"] == 2.4
    assert first["fifo_p99_minutes"] == 2.6
    assert first["fifo_min_vs_fresh_hca"] == "RESOLUTION_BOUND_TIE"
    assert first["fifo_min_vs_paper"] == "RESOLUTION_BOUND_TIE"


def test_joint_decision_is_derived_from_the_three_existing_summaries() -> None:
    fault = reporting.build_report_payload(_g26(), _g27())
    fifo = reporting.build_fifo_speed_payload(_g26(), _fifo())
    bias = {
        "schema": "czr005.g4irsf27.bias_report.v1",
        "protocol_fidelity": "LEGACY_VARIANT_RECONSTRUCTION",
        "exact_legacy_variant_recovered": False,
        "rows": [
            {
                "status": "COMPLETE",
                "s4_minutes": 1.0,
                "archived_dynamic_minutes": 2.0,
                "archived_static_minutes": 3.0,
            }
            for _ in range(12)
        ],
    }

    payload = reporting.build_joint_decision_payload(fault, fifo, bias)
    markdown = reporting.render_joint_decision_markdown(payload)

    assert payload["active_policy"]["normal_operation"] == "S4/J2/E2+local FIFO"
    assert payload["decision_basis"]["route_scorer_and_j2_e2_framework_unchanged"] is True
    assert payload["decision_basis"]["normal_queue_policy_changed_to_fifo"] is True
    assert "normal_policy_unchanged" not in payload["decision_basis"]
    assert payload["table_5_4"]["s4_vs_archived_dynamic_win_count"] == 12
    assert payload["table_5_4"]["s4_vs_archived_static_win_count"] == 12
    assert payload["table_5_4"]["bias_is_learning"] is False
    assert payload["table_5_5"]["pair_5_7_status"] == reporting.NOT_MEASURED
    assert "不是 learning" in markdown
