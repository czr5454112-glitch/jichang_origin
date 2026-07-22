from __future__ import annotations

import json

from scripts.eval.g4irsf11_g4irsf10_audit import (
    audit_hard_case_rows,
    audit_high_flow_rows,
    audit_jsonl_span,
)


def test_aggregate_scale_rows_never_become_capacity_pass() -> None:
    rows = [
        {
            "scenario": f"high_flow_no_fault_{scale}x",
            "scale": f"{scale}x",
            "raw_bags": 10,
            "complete_bags": 10,
            "planned_segments": 20,
            "failed_segments": 0,
            "node_conflicts": 0,
            "runtime_full_astar_calls": 0,
            "runtime_seconds": 2,
            "fallback_calls": 5,
        }
        for scale in (1, 2, 4, 8, 16)
    ]

    audited = audit_high_flow_rows(rows)

    assert all(row["safe_execution_pass"] for row in audited)
    assert all(row["queue_stability_status"] == "UNVERIFIED_NO_TIME_SERIES" for row in audited)
    assert all(row["service_level_status"] == "UNVERIFIED_NO_SLO" for row in audited)
    assert all(row["capacity_status"] == "UNVERIFIED" for row in audited)
    assert audited[0]["segment_throughput_per_second"] == 10.0
    assert audited[0]["fallback_per_planned_segment"] == 0.25
    assert audited[0]["decision_count_status"] == "UNAVAILABLE_IN_G4IRSF10_TASK_ROWS"
    assert audited[0]["fallback_per_decision"] == ""


def test_jsonl_span_uses_only_executed_prefix(tmp_path) -> None:
    path = tmp_path / "rolling.jsonl"
    rows = [
        {"pass_time": 10.0, "generation_copy_index": 0},
        {"pass_time": 20.0, "generation_copy_index": 0},
        {"pass_time": 86410.0, "generation_copy_index": 1},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    span = audit_jsonl_span(path, executed_limit=2)

    assert span.rows_used == 2
    assert span.full_row_count == 3
    assert span.elapsed_seconds == 10.0
    assert span.copy_indices == (0,)
    assert span.coverage_fraction == 2 / 3


def test_hard_case_audit_detects_duplicates_and_missing_families() -> None:
    base = {
        "scenario": "paper_main_2_5_repeat_1",
        "task_id": 7,
        "segment_id": "7:storage_in",
        "current_node": 3,
        "goal_node": 47,
        "candidate_next_nodes": "[16, 17]",
        "selected_next": 16,
        "decision_source": "fallback",
        "fallback_reason": "risk",
        "path_history": "[3, 16, 47]",
        "why_hard": '["model_vs_fallback_disagreement"]',
    }
    repeated = dict(base, scenario="paper_main_2_5_repeat_2")

    summary, distributions = audit_hard_case_rows([base, repeated])

    assert summary["row_count"] == 2
    assert summary["unique_content_count"] == 1
    assert summary["duplicate_rate"] == 0.5
    assert summary["covers_high_flow"] is False
    assert summary["covers_fault"] is False
    assert summary["covers_tail"] is False
    assert summary["required_family_gate"] is False
    assert summary["source_node_evidence_count"] == 0
    assert summary["source_goal_distribution_status"] == "UNVERIFIED_MISSING_SOURCE_OR_GOAL"
    assert summary["sampling_bias_status"] == "UNVERIFIED_NO_STRATUM_WEIGHT_EVIDENCE"
    assert summary["legacy_hardcase_gate_status"] == "FAIL"
    assert any(row["dimension"] == "scenario" for row in distributions)
