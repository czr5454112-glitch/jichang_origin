from __future__ import annotations

from pathlib import Path

from scripts.eval.g4irsf11_evaluation_reporting import case_row, write_reports
from scripts.eval.g4irsf11_experiment_protocol import CaseSpec


def test_case_row_and_resource_report_expose_junction_scaling_evidence(
    tmp_path: Path,
) -> None:
    case = CaseSpec("resource_case", "size_ladder", "time_compressed", 1.0)
    resource = {
        "runtime_thread_count": 1,
        "junction_count": 17,
        "peak_active_bag_count": 12,
        "peak_working_set_bytes": 4096,
        "cpp_internal_accounted_bytes": 1024,
        "peak_junction_local_state_accounted_bytes": 128,
        "sum_final_junction_local_state_accounted_bytes": 768,
        "max_junction_service_utilization": 0.75,
        "bottleneck_node": 9,
        "bottleneck_score": 4.75,
        "wall_seconds_including_pybind_materialization": 2.0,
    }
    result = {
        "workload_segment_count": 20,
        "raw_bag_count": 20,
        "summary": {
            "completed_count": 20,
            "failed_count": 0,
            "decision_latency_us_p99": 3.0,
            "event_throughput_per_second": 100.0,
        },
        "raw_bag_capacity_metrics": {},
        "segment_capacity_metrics": {},
        "fault_window_metrics": [],
        "resource_metrics": resource,
    }
    execution = {
        "status": "EXECUTED",
        "run_id": "resource-run",
        "return_code": 0,
        "protocol_manifest_sha256": "a" * 64,
        "map_sha256": "b" * 64,
    }

    row = case_row(case, result, execution)
    assert row["protocol_manifest_sha256"] == "a" * 64
    assert row["map_sha256"] == "b" * 64
    for key, expected in resource.items():
        if key == "wall_seconds_including_pybind_materialization":
            assert row["wall_seconds"] == expected
        else:
            assert row[key] == expected

    resource_report = write_reports(tmp_path, [row])["resources"]
    text = resource_report.read_text(encoding="utf-8")
    assert "Peak active bags" in text
    assert "Peak junction bytes" in text
    assert "Max junction util." in text
    assert "Bottleneck node" in text
    assert "| resource_case | 20 | 17 | 12 | 1 |" in text


def test_temporal_fault_report_exposes_unrecovered_negative_evidence(
    tmp_path: Path,
) -> None:
    case = CaseSpec(
        "fault_case",
        "temporal_fault",
        "empirical_interarrival_jitter",
        2.5,
        fault_profile="fault_policy_off",
    )
    result = {
        "summary": {"completed_count": 0, "failed_count": 1},
        "raw_bag_capacity_metrics": {},
        "segment_capacity_metrics": {"safe_execution_pass": True},
        "resource_metrics": {},
        "fault_window_metrics": [
            {
                "recovery_observed": False,
                "recovery_time_seconds": None,
                "backlog_before_fault": 4,
                "backlog_at_repair": 5,
                "fault_recovery_gate_failures": ["recovery_time_pass"],
                "fault_recovery_pass": False,
            }
        ],
    }
    row = case_row(case, result, {"status": "EXECUTED", "return_code": 0})

    assert row["fault_recovery_pass"] is False
    assert row["fault_recovery_observed_count"] == 0
    assert row["fault_recovery_unobserved_count"] == 1
    assert row["fault_recovery_time_seconds_max"] == ""
    assert row["fault_recovery_times_seconds_json"] == "[null]"
    assert row["fault_backlog_before_fault_json"] == "[4]"
    assert row["fault_backlog_at_repair_json"] == "[5]"
    assert row["fault_recovery_gate_failures"] == "window_0:recovery_time_pass"

    stringly_result = dict(result)
    stringly_result["fault_window_metrics"] = [
        dict(result["fault_window_metrics"][0], fault_recovery_pass="False")
    ]
    assert (
        case_row(case, stringly_result, {"status": "EXECUTED"})[
            "fault_recovery_pass"
        ]
        is False
    )

    report = write_reports(tmp_path, [row])["temporal_fault"]
    text = report.read_text(encoding="utf-8")
    assert "Queue" in text
    assert "Service" in text
    assert "Capacity" in text
    assert "p99 s" in text
    assert "End backlog" in text
    assert "Backlog before fault" in text
    assert "Backlog at repair" in text
    assert "[4]" in text
    assert "[5]" in text
    assert "Unrecovered windows" in text
    assert "NOT_RECOVERED_BY_RUN_END" in text
    assert "[null]" in text
    assert "window_0:recovery_time_pass" in text
