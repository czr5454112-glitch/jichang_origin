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
    execution = {"status": "EXECUTED", "run_id": "resource-run", "return_code": 0}

    row = case_row(case, result, execution)
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
