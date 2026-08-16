from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
from typing import Mapping

import pytest

from scripts.eval import run_g4irsf28_reporting as reporting


SERVICE_VALUES = {
    "t5_2_speed_1p5": {"min": 5.0889222222, "mean": 5.7161555887, "max": 7.2222888889},
    "t5_2_speed_2": {"min": 3.8667, "mean": 4.3233930026, "max": 5.3084},
    "t5_2_speed_2p5": {"min": 3.1333666667, "mean": 3.5092248158, "max": 4.6534},
    "t5_2_speed_3": {"min": 2.6333666667, "mean": 2.9499244541, "max": 3.8056222222},
}

FRESH_VALUES = {
    1.5: {"min": 5.1, "mean": 6.4199, "max": 9.6333},
    2.0: {"min": 3.8666666667, "mean": 4.9274, "max": 7.3667},
    2.5: {"min": 3.1333333333, "mean": 3.9452, "max": 5.95},
    3.0: {"min": 2.6333333333, "mean": 3.3546, "max": 5.05},
}


def _g26() -> dict[str, object]:
    speed_rows: list[dict[str, object]] = []
    for _, speed, prefix in reporting.SPEED_CASES:
        for metric in reporting.METRICS:
            speed_rows.append(
                {
                    "row_id": f"{prefix}_{metric}",
                    "measurement_status": "MEASURED",
                    "hca_value": FRESH_VALUES[speed][metric],
                    "paper_value": FRESH_VALUES[speed][metric],
                }
            )
    table_53: list[dict[str, object]] = []
    for metric, dispersed, hca, improvement in (
        ("min", 3.56, 3.13, 12.1),
        ("mean", 4.43, 3.96, 10.6),
        ("max", 8.62, 5.98, 30.6),
    ):
        table_53.extend(
            [
                {"row_id": f"dispersed_heuristic_{metric}", "paper_value": dispersed},
                {"row_id": f"iot_drpa_hca_star_{metric}", "paper_value": hca},
                {"row_id": f"paper_improvement_{metric}", "paper_value": improvement},
            ]
        )
    table_55: list[dict[str, object]] = []
    table_54 = [
        {
            "row_id": f"speed_{speed:.1f}_dev_{deviation}",
            "standard_speed_mps": speed,
            "deviation_percent": deviation,
            "paper_improvement_percent": 5.0,
        }
        for speed in (1.5, 2.0, 2.5, 3.0)
        for deviation in (10, 20, 30)
    ]
    measured_index = 0
    for scenario_id in reporting.g27_reporting.SCENARIO_IDS:
        if scenario_id == "pair_5_7":
            table_55.append(
                {
                    "row_id": scenario_id,
                    "line_ids": "5,7",
                    "affected_conveyors": 12,
                    "measurement_status": reporting.NOT_MEASURED,
                    "paper_value": 0.48,
                    "hca_primary_success": None,
                    "s4_primary_success": None,
                    "fresh_protocol_status": "ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED",
                }
            )
            continue
        completed = 20_000 + measured_index
        hca = completed - 1 if measured_index < 6 else completed
        paper = completed - 1 if measured_index < 10 else completed
        table_55.append(
            {
                "row_id": scenario_id,
                "line_ids": str(measured_index + 1),
                "affected_conveyors": measured_index + 1,
                "measurement_status": "MEASURED",
                "paper_value": paper / reporting.CANONICAL_RAW_BAGS,
                "hca_primary_success": hca / reporting.CANONICAL_RAW_BAGS,
                "s4_primary_success": (completed - 100) / reporting.CANONICAL_RAW_BAGS,
            }
        )
        measured_index += 1
    return {
        "protocol": {"canonical_raw_bag_count": reporting.CANONICAL_RAW_BAGS},
        "tables": {
            "5.2": speed_rows,
            "5.3": table_53,
            "5.4": table_54,
            "5.5": table_55,
        },
    }


def _service() -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    for case_id, speed, _ in reporting.SPEED_CASES:
        values = SERVICE_VALUES[case_id]
        seconds = {key: value * 60.0 for key, value in values.items()}
        payloads.append(
            {
                "schema": reporting.SERVICE_SCHEMA,
                "status": reporting.SERVICE_COMPLETE,
                "case": {"case_id": case_id, "standard_speed_mps": speed},
                "outcome": {
                    "requested_segment_count": reporting.CANONICAL_SEGMENTS,
                    "completed_raw_bag_count": reporting.CANONICAL_RAW_BAGS,
                    "paper_raw_bag_tth": {
                        "distribution": {
                            "minutes": {**values, "p95": values["mean"] + 0.2, "p99": values["mean"] + 0.3},
                            "seconds": seconds,
                        }
                    },
                },
                "potential": {
                    "mode": reporting.SERVICE_POTENTIAL_MODE,
                    "runtime_decision_complexity": "O(outdegree)",
                },
                "protocol": {
                    "runtime_full_astar_used": False,
                    "future_route_materialized": False,
                    "hca_global_reservation_table_used": False,
                    "learning_active": False,
                    "change_scope": "static_heuristic_matrix_only",
                },
                "safety": {"pass": True},
            }
        )
    return payloads


def _bias_cases() -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    potential = {
        "enabled": True,
        "contract": {"mode": reporting.SERVICE_POTENTIAL_MODE},
    }
    for case in reporting.g27_bias.bias_cases():
        archived = case["archived_paper_reported"]
        observed = float(archived["dynamic"]) - 1.0
        payloads.append(
            {
                "schema": reporting.g27_bias.CASE_RESULT_SCHEMA,
                "case_id": case["case_id"],
                "status": "COMPLETE",
                "runtime_protocol": {"service_aware_potential": potential},
                "runtime_summary": {
                    "status": "COMPLETE",
                    "tth_mean_minutes": observed,
                    "selected_segment_count": reporting.CANONICAL_SEGMENTS,
                    "selected_raw_bag_count": reporting.CANONICAL_RAW_BAGS,
                    "completed_raw_bag_count": reporting.CANONICAL_RAW_BAGS,
                    "strict_safety": {"pass": True},
                    "service_aware_potential": potential,
                },
                "comparison": {
                    "s4_beats_archived_dynamic_mean": True,
                    "s4_beats_archived_static_mean": True,
                },
            }
        )
    return payloads


def _bias() -> Mapping[str, object]:
    return reporting.build_bias_summary(_bias_cases())


def _fault_cases() -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []
    measured_index = 0
    for scenario_id in reporting.g27_reporting.MEASURABLE_SCENARIO_IDS:
        completed = 20_000 + measured_index
        payloads.append(
            {
                "schema": reporting.g27_reporting.G27_CASE_SCHEMA,
                "status": reporting.g27_reporting.G27_COMPLETE,
                "case": {"case_id": f"t5_5_fault_{scenario_id}"},
                "local_values": {
                    "service_aware_potential": {
                        "enabled": True,
                        "contract": {"mode": reporting.SERVICE_POTENTIAL_MODE},
                    },
                },
                "protocol": {
                    "selected_segment_count": reporting.CANONICAL_SEGMENTS,
                    "selected_raw_bag_count": reporting.CANONICAL_RAW_BAGS,
                },
                "outcome": {
                    "selected_raw_bag_count": reporting.CANONICAL_RAW_BAGS,
                    "completed_raw_bag_count": completed,
                    "source_rejected_unreachable_segment_count": 0,
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
        measured_index += 1
    return payloads


def _fault() -> Mapping[str, object]:
    return reporting.build_fault_summary(_g26(), _fault_cases())


def _payload() -> dict[str, object]:
    return reporting.build_completion_payload(_g26(), _service(), _bias(), _fault())


def test_table_52_closes_the_three_minimum_resolution_cells_without_losses() -> None:
    payload = _payload()
    table = payload["tables"]["5.2"]

    assert table["summary"]["vs_fresh_hca"] == {
        "cell_count": 12,
        "measured_cell_count": 12,
        "not_measured_cell_count": 0,
        "g28_win_count": 9,
        "tie_count": 3,
        "resolution_tie_count": 3,
        "original_win_count": 0,
    }
    speed3 = table["summary"]["speed_3_minimum"]
    assert speed3["g28_seconds"] == pytest.approx(158.002, abs=1.0e-6)
    assert speed3["gap_seconds"] == pytest.approx(0.002, abs=1.0e-6)
    assert speed3["verdict"] == "RESOLUTION_BOUND_TIE"


def test_table_53_keeps_paper_precision_and_raw_diagnostic_separate() -> None:
    payload = _payload()
    table = payload["tables"]["5.3"]
    minimum, mean, maximum = table["rows"]

    assert minimum["g28_improvement_at_paper_precision_percent"] == 12.1
    assert minimum["g28_improvement_vs_paper_reported"] == "PAPER_RESOLUTION_TIE"
    assert minimum["g28_time_vs_paper_hca"] == "PAPER_RESOLUTION_TIE"
    assert minimum["archived_raw_diagnostic"]["drives_formal_verdict"] is False
    assert minimum["archived_raw_diagnostic"]["dispersed_minutes"] == 3.555
    assert mean["g28_improvement_vs_paper_reported"] == "G28_WIN"
    assert maximum["g28_improvement_vs_paper_reported"] == "G28_WIN"
    assert table["summary"]["improvement_vs_paper_reported"]["original_win_count"] == 0


def test_bias_and_fault_boundaries_remain_explicit_in_joint_decision() -> None:
    payload = _payload()
    bias = payload["tables"]["5.4"]
    fault = payload["tables"]["5.5"]

    assert bias["summary"]["vs_archived_dynamic"]["g28_win_count"] == 12
    assert bias["summary"]["improvement_vs_paper_reported"]["g28_win_count"] == 12
    assert all(row["evidence"] == "DESCRIPTIVE_UNPAIRED" for row in bias["rows"])
    assert all(row["paper_reported_improvement_percent"] == 5.0 for row in bias["rows"])
    assert all(row["g28_improvement_vs_paper_reported"] == "G28_WIN" for row in bias["rows"])
    assert bias["exact_legacy_variant_recovered"] is False
    assert fault["summary"]["vs_fresh_hca"]["g28_win_count"] == 6
    assert fault["summary"]["vs_fresh_hca"]["tie_count"] == 9
    assert fault["summary"]["vs_fresh_hca"]["original_win_count"] == 0
    assert fault["summary"]["pair_5_7_status"] == reporting.NOT_MEASURED
    assert payload["status"] == "MEASURABLE_TARGET_MET_WITH_EXPLICIT_LEGACY_PROTOCOL_GAPS"
    assert payload["joint_decision"]["literal_exact_replication_of_every_legacy_experiment"] is False


def test_report_rejects_missing_case_and_runtime_astar() -> None:
    cases = _service()
    cases.pop()
    with pytest.raises(reporting.ReportingError, match="missing G28 service cases"):
        reporting.build_completion_payload(_g26(), cases, _bias(), _fault())

    cases = deepcopy(_service())
    cases[0]["protocol"]["runtime_full_astar_used"] = True  # type: ignore[index]
    with pytest.raises(reporting.ReportingError, match="simple decentralized boundary"):
        reporting.build_completion_payload(_g26(), cases, _bias(), _fault())


def test_renderers_publish_the_claim_boundary() -> None:
    payload = _payload()
    markdown = reporting.render_markdown(payload)
    csv_text = reporting.render_csv(payload)

    assert "158.002 s" in markdown
    assert "6 胜 / 9 个拓扑上限平 / 0 负" in markdown
    assert "DESCRIPTIVE_UNPAIRED" in markdown
    assert "运行时不调用完整 A*" in markdown
    assert "table_id,case_id,metric" in csv_text
    assert "paper_reported_improvement" in csv_text


def test_bias_discovery_requires_exact_safe_service_aware_case_set(
    tmp_path: Path,
) -> None:
    for payload in _bias_cases():
        (tmp_path / f"{payload['case_id']}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    (tmp_path / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(reporting.ReportingError, match="JSON set is not exact"):
        reporting.discover_bias_payloads(tmp_path)

    (tmp_path / "extra.json").unlink()
    first = tmp_path / f"{reporting.BIAS_CASE_IDS[0]}.json"
    payload = json.loads(first.read_text(encoding="utf-8"))
    payload["runtime_summary"]["strict_safety"]["pass"] = False
    first.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(reporting.ReportingError, match="failed strict safety"):
        reporting.discover_bias_payloads(tmp_path)


def test_main_builds_from_31_raw_cases_and_validator_detects_stale_text(tmp_path: Path) -> None:
    service_dir = tmp_path / "service"
    bias_dir = tmp_path / "bias"
    fault_dir = tmp_path / "fault"
    reference_dir = tmp_path / "reference"
    output_dir = tmp_path / "publication"
    service_dir.mkdir()
    bias_dir.mkdir()
    fault_dir.mkdir()
    reference_dir.mkdir()
    output_dir.mkdir()
    for payload in _service():
        case_id = payload["case"]["case_id"]  # type: ignore[index]
        (service_dir / f"{case_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    for payload in _bias_cases():
        case_id = payload["case_id"]
        (bias_dir / f"{case_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    for payload in _fault_cases():
        case_id = payload["case"]["case_id"]  # type: ignore[index]
        (fault_dir / f"{case_id}_full.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    g26_path = reference_dir / "g26.json"
    g26_path.write_text(json.dumps(_g26()), encoding="utf-8")
    outputs = {
        name: output_dir / name
        for name in (
            "g4irsf28_bias_experiments.json",
            "g4irsf28_bias_experiments.csv",
            "g4irsf28_bias_experiments.md",
            "g4irsf28_fault_values.json",
            "g4irsf28_fault_values.csv",
            "g4irsf28_fault_values.md",
            "g4irsf28_completion.json",
            "g4irsf28_completion.csv",
            "g4irsf28_completion.md",
        )
    }
    common_args = [
        "--service-dir",
        str(service_dir),
        "--bias-case-dir",
        str(bias_dir),
        "--fault-case-dir",
        str(fault_dir),
        "--g26-report",
        str(g26_path),
        "--bias-json-output",
        str(outputs["g4irsf28_bias_experiments.json"]),
        "--bias-csv-output",
        str(outputs["g4irsf28_bias_experiments.csv"]),
        "--bias-markdown-output",
        str(outputs["g4irsf28_bias_experiments.md"]),
        "--fault-json-output",
        str(outputs["g4irsf28_fault_values.json"]),
        "--fault-csv-output",
        str(outputs["g4irsf28_fault_values.csv"]),
        "--fault-markdown-output",
        str(outputs["g4irsf28_fault_values.md"]),
        "--json-output",
        str(outputs["g4irsf28_completion.json"]),
        "--csv-output",
        str(outputs["g4irsf28_completion.csv"]),
        "--markdown-output",
        str(outputs["g4irsf28_completion.md"]),
    ]

    def run(*extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(Path(reporting.__file__).resolve()),
                *extra,
                *common_args,
            ],
            cwd=reporting.ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

    completed = run()

    assert completed.returncode == 0, completed.stderr
    assert all(path.is_file() for path in outputs.values())
    fault = json.loads(
        outputs["g4irsf28_fault_values.json"].read_text(encoding="utf-8")
    )
    completion = json.loads(
        outputs["g4irsf28_completion.json"].read_text(encoding="utf-8")
    )
    assert fault["schema"] == reporting.FAULT_SCHEMA
    assert fault["compat_source_schema"] == reporting.FAULT_COMPAT_SCHEMA
    assert fault["summary"]["g28_vs_fresh_hca"]["g28_win_count"] == 6
    assert all("affected_conveyors" in row for row in fault["rows"])
    assert completion["status"] == "MEASURABLE_TARGET_MET_WITH_EXPLICIT_LEGACY_PROTOCOL_GAPS"
    expected_raw = {
        reporting._relative(path)
        for directory in (service_dir, bias_dir, fault_dir)
        for path in directory.glob("*.json")
    }
    assert expected_raw <= set(completion["protocol"]["input_paths"])
    assert len(expected_raw) == 31
    fault_markdown = outputs["g4irsf28_fault_values.md"].read_text(
        encoding="utf-8"
    )
    fault_csv = outputs["g4irsf28_fault_values.csv"].read_text(encoding="utf-8")
    bias_csv = outputs["g4irsf28_bias_experiments.csv"].read_text(encoding="utf-8")
    assert "G28 Service-Aware" in fault_markdown
    assert "not an exact per-segment" in fault["protocol"]["comparison_interpretation"]
    assert "逐 segment release paired" in fault_markdown
    assert "affected conveyors" in fault_markdown
    assert "不计入胜负" in fault_markdown
    assert "G27_WIN" not in fault_csv + bias_csv
    assert "G28_WIN" in fault_csv and "G28_WIN" in bias_csv

    validated = run("--validate-committed")
    assert validated.returncode == 0, validated.stderr
    assert "validation: PASS" in validated.stdout

    outputs["g4irsf28_completion.md"].write_text("stale\n", encoding="utf-8")
    stale = run("--validate-committed")
    assert stale.returncode == 2
    assert "is stale" in stale.stderr

    (output_dir / "g4irsf28_extra.json").write_text("{}\n", encoding="utf-8")
    extra = run("--validate-committed")
    assert extra.returncode == 2
    assert "formal G28 JSON set is not exact" in extra.stderr
