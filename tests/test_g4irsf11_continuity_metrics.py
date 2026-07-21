from __future__ import annotations

from scripts.eval.g4irsf11_continuity_metrics import (
    rolling_continuity_metrics,
    rolling_input_audit,
)


def _rolling_rows(copies: int = 3) -> list[dict]:
    rows = []
    for copy_index in range(copies):
        for base, offset in (("task-a:direct", 10.0), ("task-b:direct", 20.0)):
            rows.append(
                {
                    "segment_id": f"{base}:g4irsf11_c{copy_index}:scenario",
                    "generation_copy_index": copy_index,
                    "release_time": offset + copy_index * 86_400.0,
                }
            )
    return rows


def test_input_audit_requires_every_base_copy_and_fixed_day_offset() -> None:
    rows = _rolling_rows()
    audit = rolling_input_audit(rows, expected_copies=3)
    assert audit["status"] == "PASS"
    assert audit["base_segment_count"] == 2
    assert audit["observed_copy_indices"] == [0, 1, 2]
    assert audit["day_stride_seconds"] == 86_400.0
    assert len(audit["coverage_sha256"]) == 64

    missing = rows[:-1]
    assert rolling_input_audit(missing, expected_copies=3)["status"] == "FAIL"
    shifted = [dict(row) for row in rows]
    shifted[-1]["release_time"] += 1.0
    assert rolling_input_audit(shifted, expected_copies=3)["status"] == "FAIL"


def test_runtime_audit_records_pending_and_cross_boundary_completion() -> None:
    workload = _rolling_rows()
    results = []
    for row in workload:
        result = {
            "segment_id": row["segment_id"],
            "completed": True,
            "finish_time": row["release_time"] + 5.0,
        }
        results.append(result)
    # One day-0 segment survives into day 1 in the same runtime invocation.
    results[0]["finish_time"] = 86_415.0
    audit = rolling_continuity_metrics(
        workload,
        results,
        expected_copies=3,
        runtime_instance_id="run-123",
    )
    assert audit["status"] == "PASS"
    assert audit["single_runtime_invocation_pass"] is True
    assert audit["boundary_count"] == 2
    assert audit["carry_over_observed"] is True
    assert audit["cross_boundary_completion_count"] >= 1
    assert audit["boundaries"][0]["pending_before_boundary"] >= 1


def test_runtime_audit_fails_without_single_runtime_identity_or_complete_join() -> None:
    workload = _rolling_rows(copies=2)
    results = [
        {
            "segment_id": row["segment_id"],
            "completed": True,
            "finish_time": row["release_time"] + 1.0,
        }
        for row in workload[:-1]
    ]
    audit = rolling_continuity_metrics(
        workload,
        results,
        expected_copies=2,
        runtime_instance_id="",
    )
    assert audit["status"] == "FAIL"
    assert audit["single_runtime_invocation_pass"] is False
    assert any("omitted segments" in blocker for blocker in audit["blockers"])
