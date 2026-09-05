from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path

import pytest

from scripts.eval import run_nanning_tail_risk_audit as audit


def test_archived_nanning_2x_cells_support_only_seed_level_tail_diagnosis() -> None:
    cells = audit.load_archived_cells(audit.DEFAULT_INPUT_ROOT)
    rows = audit.seed_rows(cells)

    assert len(cells) == 20
    assert len(rows) == 10
    assert not any(
        audit.archive_has_bag_evidence(entry["data"]) for entry in cells.values()
    )
    deltas = [float(row["max_tardiness_delta"]) for row in rows]
    assert math.isclose(math.fsum(deltas) / len(deltas), 2555.0997625434393)
    assert sum(value > 0.0 for value in deltas) == 9
    assert all(row["p1d1_completed"] > row["p0d0_completed"] for row in rows)
    assert all(
        (row["max_tardiness_delta"] > 0) == (row["max_wait_delta"] > 0)
        for row in rows
    )


def test_raw_bag_detail_preserves_ebs_and_fixed_horizon_semantics() -> None:
    inputs = [
        {
            "segment_id": "1:in",
            "task_id": 1,
            "start": 0,
            "goal": 53,
            "original_start": 0,
            "original_goal": 99,
            "original_entry_time": 10.0,
            "pass_time": 10.0,
            "std": 100.0,
            "early_bag_split": True,
        },
        {
            "segment_id": "1:out",
            "task_id": 1,
            "start": 53,
            "goal": 99,
            "original_start": 0,
            "original_goal": 99,
            "original_entry_time": 10.0,
            "pass_time": 50.0,
            "std": 100.0,
            "early_bag_split": True,
        },
        {
            "segment_id": "2:direct",
            "task_id": 2,
            "start": 4,
            "goal": 8,
            "original_entry_time": 20.0,
            "pass_time": 20.0,
            "std": 90.0,
            "early_bag_split": False,
        },
    ]
    results = [
        {
            "segment_id": "1:in",
            "release_time": 10.0,
            "admitted_time": 12.0,
            "finish_time": 30.0,
            "completed": True,
            "total_local_wait": 3.0,
            "junction_queue_wait_seconds": 2.0,
            "merge_grant_wait_seconds": 1.0,
            "edge_travel_time_seconds": 8.0,
            "node_service_time_seconds": 4.0,
            "loop_extra_time_seconds": 0.0,
            "short_history": [0, 7, 53],
        },
        {
            "segment_id": "1:out",
            "release_time": 50.0,
            "admitted_time": 52.0,
            "finish_time": 120.0,
            "completed": True,
            "total_local_wait": 7.0,
            "junction_queue_wait_seconds": 5.0,
            "merge_grant_wait_seconds": 2.0,
            "edge_travel_time_seconds": 30.0,
            "node_service_time_seconds": 9.0,
            "loop_extra_time_seconds": 0.5,
            "short_history": [53, 75, 99],
        },
        {
            "segment_id": "2:direct",
            "release_time": 20.0,
            "admitted_time": -1.0,
            "finish_time": -1.0,
            "completed": False,
            "failure_reason": "TIME_LIMIT",
            "short_history": [],
        },
    ]

    rows = audit.summarize_raw_bags(inputs, results, fixed_horizon=150.0)
    assert [row["task_id"] for row in rows] == [2, 1]
    direct, ebs = rows
    assert direct["rank_in_cell"] == 1
    assert direct["fixed_horizon_tardiness_lower_bound_seconds"] == 60.0
    assert direct["segment_source_queue_wait_sum_seconds"] == 130.0
    assert direct["routing_class"] == "DIRECT"
    assert direct["unadmitted_segment_count"] == 1
    assert direct["failure_reasons"] == "TIME_LIMIT"

    assert ebs["routing_class"] == "EBS_SPLIT"
    assert ebs["original_start"] == 0
    assert ebs["original_goal"] == 99
    assert ebs["fully_admitted_time"] == 52.0
    assert ebs["finish_time"] == 120.0
    assert ebs["fixed_horizon_tardiness_lower_bound_seconds"] == 20.0
    assert ebs["segment_source_queue_wait_sum_seconds"] == 4.0
    assert ebs["total_local_wait_sum_seconds"] == 10.0
    assert ebs["terminal_history_nodes"] == "0;7;53;53;75;99"
    assert ebs["decomposition_is_not_additive_raw_bag_latency"] is True


def test_aggregate_only_audit_writes_explicit_unavailable_outputs(tmp_path: Path) -> None:
    worst = tmp_path / "worst.csv"
    report = tmp_path / "report.md"
    figure = tmp_path / "figure.png"
    args = type(
        "Args",
        (),
        {
            "input_root": audit.DEFAULT_INPUT_ROOT,
            "summary_csv": audit.DEFAULT_SUMMARY,
            "detail_root": tmp_path / "details",
            "worst_bags_csv": worst,
            "report": report,
            "figure": figure,
        },
    )()

    result = audit.audit(args)

    assert result["status"] == "COMPLETE_AGGREGATE_AUDIT"
    assert result["worse_seed_count"] == 9
    with worst.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["task_id"] == ""
    assert rows[0]["evidence_status"] == (
        "UNAVAILABLE_ARCHIVE_AGGREGATE_ONLY_REQUIRES_VALIDATED_RERUN"
    )
    text = report.read_text(encoding="utf-8")
    assert "+2555.10 s" in text
    assert "[1027.27, 4083.66]" in text
    assert "worse in **9/10**" in text
    assert "first policy divergence remains `NOT_IDENTIFIED_NO_TRACE_REPLAY`" in text
    assert figure.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_detail_diagnosis_separates_observed_wait_from_unidentified_policy() -> None:
    details = []
    for arm in audit.ARMS:
        details.append(
            {
                "arm": arm,
                "is_max_bag": "True",
                "routing_class": "DIRECT",
                "segment_source_queue_wait_sum_seconds": "0",
                "junction_queue_wait_sum_seconds": "99",
                "total_local_wait_sum_seconds": "99",
                "merge_grant_wait_sum_seconds": "1",
                "segment_post_admission_observed_sum_seconds": "200",
                "original_start": "57",
                "original_goal": "48",
                "raw_complete": "True",
            }
        )

    lines = audit._detail_diagnosis(details)

    assert any("direct in 2/2" in line for line in lines)
    assert any("EXPECTED_CAPACITY_TRADEOFF" in line for line in lines)
    assert any("NOT_IDENTIFIED_NO_TRACE_REPLAY" in line for line in lines)


def test_rerun_default_uses_archived_relocated_workload_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "relocated" / "g4irsf31_nanning"
    bundle.mkdir(parents=True)
    canonical = bundle / "nanning_2x_canonical.jsonl"
    canonical.write_text('{"segment_id":"0:direct"}\n', encoding="utf-8")
    (bundle / "nanning_2x_manifest.json").write_text(
        '{"canonical_output":"old/root/nanning_2x_canonical.jsonl"}\n',
        encoding="utf-8",
    )
    archived = {
        "provenance": {
            "workload_path": str(canonical),
            "workload_sha256": hashlib.sha256(canonical.read_bytes()).hexdigest(),
        }
    }

    parsed = audit._parser().parse_args(
        ["rerun-cell", "--seed", "104729", "--arm", "P0D0"]
    )
    assert parsed.nanning_task_dir is None
    assert audit.resolve_nanning_task_dir(None, archived) == bundle.resolve()
    resolver = audit.random_runner.factorial.g35.nanning_native._manifest_reference
    assert resolver(
        "old/root/nanning_2x_canonical.jsonl",
        bundle / "nanning_2x_manifest.json",
    ) == canonical

    canonical.write_text('{"segment_id":"drift"}\n', encoding="utf-8")
    with pytest.raises(audit.TailAuditError, match="differs from the archived"):
        audit.resolve_nanning_task_dir(None, archived)
