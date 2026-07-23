from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.eval import g4irsf12_size_ladder as ladder


def _identity() -> dict[str, object]:
    return {
        "map_path": ladder.CANONICAL_MAP_PATH,
        "map_raw_sha256": ladder.CANONICAL_MAP_RAW_SHA256,
        "map_semantic_sha256": ladder.CANONICAL_MAP_SEMANTIC_SHA256,
        "source_path": ladder.CANONICAL_SOURCE_PATH,
        "source_raw_sha256": ladder.CANONICAL_SOURCE_RAW_SHA256,
        "source_semantic_sha256": ladder.CANONICAL_SOURCE_SEMANTIC_SHA256,
        "source_row_count": ladder.FULL_SIZE_SEGMENTS,
        "source_bag_count": ladder.FULL_SIZE_BAGS,
        "implementation_sha256": "a" * 64,
        "implementation_source_bundle_sha256": "b" * 64,
        "candidate_config_sha256": "c" * 64,
        "resource_semantics_id": "R3_java_node_window_compatible",
        "scorer_id": "frozen_g4e_local_adapter",
        "pibt_mode": "off",
        "pressure_mode": "off",
        "admission_mode": "off",
        "tht_denominator": ladder.PRIMARY_THT_DENOMINATOR,
        "workload_generation_level": ladder.WORKLOAD_GENERATION_LEVEL,
    }


def _snapshot(
    *,
    time_seconds: float,
    wall_seconds: float,
    arrivals: int,
    admissions: int,
    departures: int,
    source_holds: int = 0,
    event_count: int = 0,
    starvation_count: int = 0,
    deadlock_episode_count: int = 0,
    utilization: float = 0.5,
    cycle_id: str | None = None,
) -> dict[str, object]:
    return {
        "time_seconds": time_seconds,
        "wall_seconds": wall_seconds,
        "arrivals": arrivals,
        "admissions": admissions,
        "departures": departures,
        "backlog": arrivals - departures,
        "source_holds": source_holds,
        "event_count": event_count,
        "starvation_count": starvation_count,
        "deadlock_episode_count": deadlock_episode_count,
        "critical_junction_utilization": {"11": utilization, "19": utilization},
        "wait_for_cycle_id": cycle_id,
    }


def _descriptor(
    size: int = 144,
    *,
    candidate_id: str = "candidate_r3_s1",
    attempt_index: int = 1,
    execution_status: str = "EXECUTED",
    termination_reason: str = "DRAINED",
    snapshots: list[dict[str, object]] | None = None,
    unresolved_deadlock_count: int = 0,
    projected_p99_seconds: float | None = 120.0,
) -> dict[str, object]:
    if snapshots is None:
        counts = [size // 4, size // 2, (size * 3) // 4, size]
        snapshots = [
            _snapshot(
                time_seconds=float(index + 1),
                wall_seconds=float(index + 1),
                arrivals=count,
                admissions=count,
                departures=count,
                event_count=count * 8,
            )
            for index, count in enumerate(counts)
        ]
    final = snapshots[-1] if snapshots else _snapshot(
        time_seconds=0.0,
        wall_seconds=0.0,
        arrivals=0,
        admissions=0,
        departures=0,
    )
    peak_backlog = max((int(row["backlog"]) for row in snapshots), default=0)
    summary = {
        "arrivals": final["arrivals"],
        "admissions": final["admissions"],
        "departures": final["departures"],
        "end_backlog": final["backlog"],
        "peak_backlog": peak_backlog,
        "deadlock_episode_count": final["deadlock_episode_count"],
        "unresolved_deadlock_count": unresolved_deadlock_count,
        "starvation_count": final["starvation_count"],
        "source_hold_count": final["source_holds"],
        "event_count": final["event_count"],
        "simulation_horizon_seconds": final["time_seconds"],
        "wall_seconds": final["wall_seconds"],
        "last_arrival_time_seconds": (
            final["time_seconds"] if int(final["arrivals"]) == size else None
        ),
        "projected_p99_seconds": projected_p99_seconds,
        "control_p99_seconds": 100.0,
        "critical_junction_utilization": final["critical_junction_utilization"],
    }
    return {
        "schema": ladder.RESULT_DESCRIPTOR_SCHEMA,
        "attempt_id": f"{candidate_id}-{size}-{attempt_index}",
        "attempt_index": attempt_index,
        "candidate_id": candidate_id,
        "size_segments": size,
        "execution_status": execution_status,
        "termination_reason": termination_reason,
        "identity": _identity(),
        "reproducibility": {
            "mode": "deterministic",
            "seed": None,
            "input_order": ladder.INPUT_ORDER_ID,
            "prefix_selection": ladder.PREFIX_SELECTION_ID,
            "deterministic_tie_break": "priority_desc_then_runtime_id_asc",
        },
        "summary": summary,
        "snapshots": snapshots,
    }


def _worker_failure(*, attempt_index: int = 1) -> dict[str, object]:
    descriptor = _descriptor(attempt_index=attempt_index)
    descriptor["execution_status"] = "FAILED"
    descriptor["termination_reason"] = "WORKER_FAILURE"
    descriptor["snapshots"] = []
    descriptor["summary"] = {
        "arrivals": 0,
        "admissions": 0,
        "departures": 0,
        "end_backlog": 0,
        "peak_backlog": 0,
        "deadlock_episode_count": 0,
        "unresolved_deadlock_count": 0,
        "starvation_count": 0,
        "source_hold_count": 0,
        "event_count": 0,
        "simulation_horizon_seconds": 0.0,
        "wall_seconds": 0.0,
        "last_arrival_time_seconds": None,
        "projected_p99_seconds": None,
        "control_p99_seconds": 100.0,
        "critical_junction_utilization": {"11": 0.0},
    }
    return descriptor


def test_protocol_freezes_only_the_original_scale_ladder_and_hashes() -> None:
    manifest = ladder.protocol_manifest()
    assert tuple(manifest["size_ladder_segments"]) == (
        144,
        512,
        2_048,
        8_192,
        43_603,
    )
    assert manifest["scale_authorization"] == "none_beyond_original_1x"
    assert manifest["canonical_map"]["raw_sha256"] == (
        "9e8c5a236869336cf4c05a09a8ce0554f440eb45a6896972fc54116bcf78bbb4"
    )
    assert manifest["canonical_map"]["semantic_sha256"] == (
        "67266b1746f64ae40b4b1b52a8a74eedc6338c90b646708db2dc29e93c514c63"
    )
    assert manifest["canonical_source"]["row_count"] == 43_603
    assert manifest["canonical_source"]["bag_count"] == 28_506


def test_repository_protected_input_identity_is_recomputed() -> None:
    identity = ladder.assert_protected_inputs()
    assert identity["map_raw_sha256"] == ladder.CANONICAL_MAP_RAW_SHA256
    assert identity["map_semantic_sha256"] == ladder.CANONICAL_MAP_SEMANTIC_SHA256
    assert identity["source_row_count"] == 43_603
    assert identity["source_bag_count"] == 28_506


def test_descriptor_fails_closed_for_hash_ladder_and_summary_drift() -> None:
    descriptor = _descriptor()
    descriptor["identity"]["map_raw_sha256"] = "0" * 64
    descriptor["size_segments"] = 1_000
    descriptor["summary"]["departures"] = 143
    errors = ladder.descriptor_validation_errors(descriptor)
    assert any("map_raw_sha256" in error for error in errors)
    assert any("size_segments" in error for error in errors)
    assert any("final snapshot departures differs" in error for error in errors)
    with pytest.raises(ladder.DescriptorValidationError):
        ladder.validate_result_descriptor(descriptor)


def test_clear_attempts_advance_one_tier_only_and_full_never_authorizes_scale() -> None:
    descriptors = [
        _descriptor(size, attempt_index=index)
        for index, size in enumerate(ladder.SIZE_LADDER, start=1)
    ]
    rows = ladder.evaluate_ladder_attempts(descriptors)
    assert [row["promotion_decision"] for row in rows[:-1]] == [
        "ELIGIBLE_FOR_NEXT_SIZE"
    ] * 4
    assert rows[-1]["promotion_decision"] == (
        "ORIGINAL_1X_DIAGNOSTIC_COMPLETE_NOT_FINAL_GATE"
    )
    ladder.authorize_requested_size(rows, candidate_id="candidate_r3_s1", requested_size=43_603)
    with pytest.raises(PermissionError, match="scaled workloads are forbidden"):
        ladder.authorize_requested_size(
            rows,
            candidate_id="candidate_r3_s1",
            requested_size=47_963,
        )


def test_out_of_order_attempt_is_retained_but_cannot_clear_a_tier() -> None:
    row = ladder.evaluate_ladder_attempts([_descriptor(512)])[0]
    assert row["descriptor_status"] == "VALID"
    assert row["diagnostic_status"] == "CLEAR"
    assert row["promotion_decision"] == "HOLD_MISSING_PRIOR_TIER"
    assert "prior tier 144" in row["blockers"]


def test_imbalance_plus_low_utilization_emits_frozen_collapse_status() -> None:
    snapshots = [
        _snapshot(
            time_seconds=float(index + 1),
            wall_seconds=float(index + 1),
            arrivals=arrivals,
            admissions=arrivals,
            departures=5,
            event_count=100 * (index + 1),
            utilization=0.05,
        )
        for index, arrivals in enumerate((40, 60, 80, 100))
    ]
    descriptor = _descriptor(
        execution_status="PARTIAL",
        termination_reason="SIMULATION_TIME_LIMIT",
        snapshots=snapshots,
    )
    row = ladder.evaluate_ladder_attempts([descriptor])[0]
    assert row["diagnostic_status"] == ladder.EARLY_ABORT_STATUS
    assert row["promotion_decision"] == "HOLD_DIAGNOSTIC_COLLAPSE"
    assert "sustained_arrival_departure_imbalance" in row["warning_criteria"]
    assert "large_backlog_with_low_critical_utilization" in row["warning_criteria"]


def test_repeated_wait_cycle_is_a_hard_abort_without_other_symptoms() -> None:
    snapshots = [
        _snapshot(
            time_seconds=float(index + 1),
            wall_seconds=float(index + 1),
            arrivals=40,
            admissions=40,
            departures=40,
            event_count=100 + index,
            deadlock_episode_count=index,
            cycle_id="11->19->11",
        )
        for index in range(4)
    ]
    descriptor = _descriptor(
        execution_status="PARTIAL",
        termination_reason="USER_STOP",
        snapshots=snapshots,
    )
    row = ladder.evaluate_ladder_attempts([descriptor])[0]
    assert row["diagnostic_status"] == ladder.EARLY_ABORT_STATUS
    assert "repeated_wait_for_cycle" in row["triggered_criteria"]


def test_post_arrival_drain_and_source_hold_symptoms_are_explicit() -> None:
    no_drain_snapshots = [
        _snapshot(
            time_seconds=float(index + 1),
            wall_seconds=float(index + 1),
            arrivals=144,
            admissions=144,
            departures=100,
            event_count=100 * (index + 1),
        )
        for index in range(4)
    ]
    no_drain = _descriptor(
        execution_status="PARTIAL",
        termination_reason="USER_STOP",
        snapshots=no_drain_snapshots,
    )
    no_drain["summary"]["last_arrival_time_seconds"] = 1.0
    criteria = {
        row["criterion_id"]: row
        for row in ladder.diagnose_result_descriptor(no_drain)
    }
    assert criteria["post_arrival_backlog_not_draining"]["triggered"] is True

    hold_snapshots = [
        _snapshot(
            time_seconds=float(index + 1),
            wall_seconds=float(index + 1),
            arrivals=80,
            admissions=40,
            departures=40,
            source_holds=20 * index,
            event_count=100 * (index + 1),
        )
        for index in range(4)
    ]
    source_hold = _descriptor(
        execution_status="PARTIAL",
        termination_reason="USER_STOP",
        snapshots=hold_snapshots,
    )
    criteria = {
        row["criterion_id"]: row
        for row in ladder.diagnose_result_descriptor(source_hold)
    }
    assert criteria["source_holds_without_network_throughput"]["triggered"] is True


def test_event_rate_p99_and_starvation_hard_triggers_are_fail_closed() -> None:
    event_snapshots = [
        _snapshot(
            time_seconds=float(index + 1),
            wall_seconds=float(index + 1),
            arrivals=60,
            admissions=20,
            departures=20,
            event_count=events,
        )
        for index, events in enumerate((0, 10, 20, 200))
    ]
    event_descriptor = _descriptor(
        execution_status="PARTIAL",
        termination_reason="EVENT_LIMIT",
        snapshots=event_snapshots,
    )
    event_row = ladder.evaluate_ladder_attempts([event_descriptor])[0]
    assert "nonlinear_event_rate_without_progress" in event_row["triggered_criteria"]

    p99_row = ladder.evaluate_ladder_attempts(
        [_descriptor(projected_p99_seconds=400.0)]
    )[0]
    assert "p99_projection_far_above_control" in p99_row["triggered_criteria"]
    assert p99_row["promotion_decision"] == "HOLD_DIAGNOSTIC_COLLAPSE"

    starvation_snapshots = [
        _snapshot(
            time_seconds=float(index + 1),
            wall_seconds=float(index + 1),
            arrivals=50,
            admissions=50,
            departures=50,
            event_count=100 * (index + 1),
            starvation_count=value,
        )
        for index, value in enumerate((0, 1, 2, 10))
    ]
    starvation_descriptor = _descriptor(
        execution_status="PARTIAL",
        termination_reason="USER_STOP",
        snapshots=starvation_snapshots,
    )
    starvation_row = ladder.evaluate_ladder_attempts([starvation_descriptor])[0]
    assert "rapid_starvation_accumulation" in starvation_row["triggered_criteria"]


def test_cross_tier_normalized_event_explosion_blocks_the_current_tier() -> None:
    first = _descriptor(144, attempt_index=1)
    second = _descriptor(512, attempt_index=2)
    for snapshot in second["snapshots"]:
        snapshot["event_count"] = int(snapshot["arrivals"]) * 100
    second["summary"]["event_count"] = second["snapshots"][-1]["event_count"]
    rows = ladder.evaluate_ladder_attempts([first, second])
    assert rows[0]["promotion_decision"] == "ELIGIBLE_FOR_NEXT_SIZE"
    assert rows[1]["promotion_decision"] == "HOLD_DIAGNOSTIC_COLLAPSE"
    assert "cross_tier_nonlinear_event_growth" in rows[1]["triggered_criteria"]


def test_deterministic_repeat_mismatch_revokes_tier_authorization() -> None:
    first = _descriptor(attempt_index=1)
    repeat = _descriptor(attempt_index=2)
    for snapshot in repeat["snapshots"]:
        snapshot["event_count"] = int(snapshot["arrivals"]) * 9
    repeat["summary"]["event_count"] = repeat["snapshots"][-1]["event_count"]
    rows = ladder.evaluate_ladder_attempts([first, repeat])
    assert rows[0]["promotion_decision"] == "ELIGIBLE_FOR_NEXT_SIZE"
    assert rows[1]["promotion_decision"] == "HOLD_DIAGNOSTIC_COLLAPSE"
    assert "deterministic_repeat_mismatch" in rows[1]["triggered_criteria"]
    with pytest.raises(PermissionError, match="has not cleared prior tier 144"):
        ladder.authorize_requested_size(
            rows,
            candidate_id="candidate_r3_s1",
            requested_size=512,
        )


def test_partial_and_negative_attempts_survive_a_later_clear_retry() -> None:
    failed = _worker_failure(attempt_index=1)
    recovered = _descriptor(attempt_index=2)
    rows = ladder.evaluate_ladder_attempts([recovered, failed])
    assert len(rows) == 2
    assert rows[0]["promotion_decision"] == "HOLD_INCOMPLETE_OR_NEGATIVE_RESULT"
    assert rows[1]["promotion_decision"] == "ELIGIBLE_FOR_NEXT_SIZE"
    assert rows[0]["attempt_id"] != rows[1]["attempt_id"]


def test_empty_output_initialization_is_truthful_and_schema_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ladder, "assert_protected_inputs", lambda _root: {})
    evaluations, paths = ladder.write_diagnostic_outputs([], root=tmp_path)
    assert evaluations == []
    assert all(path.is_file() for path in paths)
    report = (tmp_path / ladder.OUTPUT_PATHS["report"]).read_text(encoding="utf-8")
    assert "PROTOCOL_READY_NO_ATTEMPTS" in report
    assert "not PASS evidence" in report
    with (tmp_path / ladder.OUTPUT_PATHS["size_ladder"]).open(
        encoding="utf-8", newline=""
    ) as handle:
        assert csv.DictReader(handle).fieldnames == list(ladder.SIZE_LADDER_COLUMNS)
