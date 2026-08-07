from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from scripts.eval import run_g4irsf19_source_gate_campaign as campaign


ROOT = Path(__file__).resolve().parents[1]


def _input(
    _: campaign.SourceGateCase,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    return (
        [
            {
                "segment_id": "seg-1",
                "task_id": 1,
                "pass_time": 0.0,
                "original_entry_time": 0.0,
                "std": 10.0,
                "start": 1,
                "goal": 4,
                "source": "node_1",
            }
        ],
        {
            "tth_denominator": "original_entry_time_tth",
            "topology_changed": False,
            "segments": 1,
            "scale": 1,
        },
    )


def _wait_row(
    ordinal: int,
    *,
    generation: int = 1,
    blocker_generation: int = 7,
    selected_bag: int = 1,
    reason: str = "SOURCE_SERVICE_NOT_READY",
) -> dict[str, Any]:
    return {
        "interval_ordinal": ordinal,
        "reason": reason,
        "source_node": 1,
        "blocker_node": 1 if reason == "SOURCE_SERVICE_NOT_READY" else 2,
        "blocker_resource": (
            "SOURCE_SERVICE_CALENDAR"
            if reason == "SOURCE_SERVICE_NOT_READY"
            else "DESTINATION_QUEUE"
        ),
        "blocker_resource_from_node": 1,
        "blocker_resource_to_node": 2,
        "source_generation": generation,
        "blocker_generation": blocker_generation,
        "selected_runtime_bag_id": selected_bag,
        "selected_segment_id": f"seg-{selected_bag}",
        "wait_seconds": 0.25,
        "affected_bag_count": 1,
        "wait_bag_seconds": 0.25,
    }


def _summary(
    arm: campaign.SourceGateArm,
    *,
    telemetry: bool,
    attempts: int,
    admitted: int,
    local_holds: int,
    downstream_holds: int,
    event_count: int,
    interval_count: int,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "merge_grant_timing_mode": campaign.J2_TIMING_MODE,
        "scorer_mode": campaign.S4_SCORER_MODE,
        "admission_mode": arm.expected_admission_mode,
        "pressure_mode": arm.expected_pressure_mode,
        "source_admission_enabled": arm.enable_source_admission,
        "source_admission_attempt_count": attempts,
        "source_admission_admitted_count": admitted,
        "source_admission_local_resource_hold_count": local_holds,
        "source_admission_downstream_pressure_hold_count": downstream_holds,
        "source_admission_beacon_read_count": downstream_holds * 2,
        "source_admission_max_observed_downstream_pressure": (
            3 if downstream_holds else 0
        ),
        "completed_count": 1,
        "failed_count": 0,
        "reservation_conflicts": 0,
        "physical_fault_edge_entry_violation_count": 0,
        "unresolved_deadlock_count": 0,
        "runtime_full_astar_calls": 0,
        "runtime_full_cie_astar_calls": 0,
        "global_reservation_scan_count": 0,
        "priority_global_scan_count": 0,
        "scorer_runtime_global_scan_count": 0,
        "microphase_runtime_global_scan_count": 0,
        "first_edge_credit_global_scan_count": 0,
        "priority_future_route_input_count": 0,
        "scorer_future_route_input_count": 0,
        "first_edge_credit_future_route_count": 0,
        "scorer_future_schedule_input_count": 0,
        "full_future_routes_stored": 0,
        "bag_future_path_field_present": False,
        "event_limit_reached": False,
        "time_limit_reached": False,
        "event_count": event_count,
    }
    if telemetry:
        result.update(
            g4irsf17_source_wait_telemetry_enabled=True,
            g4irsf17_source_wait_interval_total_count=interval_count,
            g4irsf17_source_wait_interval_stored_count=interval_count,
            g4irsf17_source_wait_interval_dropped_count=0,
            g4irsf17_source_wait_runtime_global_scan_count=0,
        )
    return result


def _payload(
    arm: campaign.SourceGateArm,
    *,
    telemetry: bool,
) -> dict[str, Any]:
    if arm.arm_id == "A0":
        attempts, admitted, local_holds, downstream_holds = 2, 1, 1, 0
        admitted_time, finish_time, event_count = 1.0, 5.0, 10
        intervals = [_wait_row(1)]
    elif arm.arm_id == "A1":
        attempts, admitted, local_holds, downstream_holds = 4, 1, 1, 2
        admitted_time, finish_time, event_count = 2.0, 6.0, 14
        intervals = [
            _wait_row(1),
            _wait_row(2),  # Same observed state: a retry, not a new mutation.
            _wait_row(
                3,
                generation=2,
                blocker_generation=9,
                reason="DESTINATION_QUEUE_CAPACITY",
            ),
        ]
    else:
        attempts, admitted, local_holds, downstream_holds = 3, 1, 1, 1
        admitted_time, finish_time, event_count = 0.5, 4.0, 12
        intervals = [
            _wait_row(1),
            _wait_row(
                2,
                blocker_generation=8,
                reason="DESTINATION_QUEUE_CAPACITY",
            ),
        ]
    if not telemetry:
        intervals = []
    result: dict[str, Any] = {
        "summary": _summary(
            arm,
            telemetry=telemetry,
            attempts=attempts,
            admitted=admitted,
            local_holds=local_holds,
            downstream_holds=downstream_holds,
            event_count=event_count,
            interval_count=len(intervals),
        ),
        "bags": [
            {
                "segment_id": "seg-1",
                "task_id": 1,
                "release_time": 0.0,
                "admitted_time": admitted_time,
                "finish_time": finish_time,
                "merge_grant_wait_seconds": 0.0,
                "completed": True,
            }
        ],
    }
    if telemetry:
        result["g4irsf17_source_wait_blockers"] = intervals
    return result


def test_build_cases_keeps_capacity_trace_free_and_bounded() -> None:
    cases = campaign.build_cases(prefixes=(144, 512), scales=(1, 2))
    assert [case.case_id for case in cases] == [
        "prefix_144",
        "prefix_512",
        "scale_1x",
        "scale_2x",
    ]
    assert [case.telemetry_mode for case in cases] == [
        "evidence_trace",
        "evidence_trace",
        "capacity",
        "capacity",
    ]
    with pytest.raises(campaign.SourceGateCampaignError, match="144 and/or 512"):
        campaign.build_cases(prefixes=(2_048,))
    with pytest.raises(campaign.SourceGateCampaignError, match="1x and 2x"):
        campaign.build_cases(prefixes=(), scales=(4,))


def test_runtime_request_changes_only_existing_source_gate_and_never_passes_model() -> None:
    rows, _ = _input(
        campaign.SourceGateCase("prefix_144", "prefix", "evidence_trace", 144)
    )
    graph = ([(1, 0, 1.0, 0, 0, [])], [], [[0.0]])
    evidence = campaign.SourceGateCase(
        "prefix_144", "prefix", "evidence_trace", 144
    )
    capacity = campaign.SourceGateCase("scale_1x", "scale", "capacity", None, 1)

    for arm in campaign.SOURCE_ARMS:
        request = campaign.build_runtime_request(
            evidence,
            arm,
            rows=rows,
            graph=graph,
            binary=Path("build/fake.pyd"),
        )
        assert request["event_semantics"] == "E4_batch_plus_destination_merge_request"
        assert request["merge_grant_timing_mode"] == campaign.J2_TIMING_MODE
        assert request["merge_grant_rule"] == campaign.J2_MERGE_RULE
        assert request["scorer_mode"] == campaign.S4_SCORER_MODE
        assert request["resource_semantics"] == "R3_java_node_window_compatible"
        assert request["pibt_mode"] == "P2"
        assert request["priority_mode"] == "Q0"
        assert request["enable_source_admission"] is arm.enable_source_admission
        assert request["enable_backpressure"] is arm.enable_backpressure
        assert request["admission_mode"] == arm.admission_mode
        assert request["pressure_mode"] == arm.pressure_mode
        assert request["enable_g4irsf17_source_wait_telemetry"] is True
        assert "scorer_model_path" not in request

        capacity_request = campaign.build_runtime_request(
            capacity,
            arm,
            rows=rows,
            graph=graph,
            binary=Path("build/fake.pyd"),
        )
        assert capacity_request["enable_g4irsf17_source_wait_telemetry"] is False
        assert capacity_request["g4irsf17_source_wait_trace_limit"] == 0
        assert "scorer_model_path" not in capacity_request


def test_distinct_hold_state_deduplicates_retries_without_claiming_mutation() -> None:
    rows = [
        _wait_row(1),
        _wait_row(2),
        _wait_row(3, generation=2, blocker_generation=8, selected_bag=2),
    ]
    result = campaign.compact_hold_opportunities(rows)
    assert result["status"] == "COMPLETE_OBSERVED_WAIT_STATE_CAPTURE"
    assert result["observed_wait_interval_count"] == 3
    assert result["observed_hold_interval_count"] == 3
    assert result["distinct_hold_opportunity_count"] == 2
    assert result["distinct_selected_bag_count"] == 2
    assert result["distinct_selected_segment_count"] == 2
    assert result["raw_interval_rows_persisted"] is False
    assert "not a bag route/action mutation" in result["claim_boundary"]

    capacity = campaign.compact_hold_opportunities([], telemetry_enabled=False)
    assert capacity["status"] == "NOT_COLLECTED_CAPACITY_MODE"
    assert capacity["observed_hold_interval_count"] is None
    assert capacity["distinct_hold_opportunity_count"] is None


def test_service_only_wait_intervals_cannot_create_a0_hold_opportunity() -> None:
    result = campaign.compact_hold_opportunities(
        [_wait_row(1, selected_bag=-1), _wait_row(2, selected_bag=-1)]
    )
    assert result["observed_wait_interval_count"] == 2
    assert result["observed_hold_interval_count"] == 0
    assert result["distinct_hold_opportunity_count"] == 0
    assert result["distinct_selected_bag_count"] == 0


def test_fake_executor_reports_counters_metrics_and_discards_raw_wait_rows() -> None:
    calls: list[Mapping[str, Any]] = []

    def fake_executor(request: Mapping[str, Any]) -> Mapping[str, Any]:
        calls.append(request)
        arm = next(
            arm
            for arm in campaign.SOURCE_ARMS
            if arm.admission_mode == request["admission_mode"]
            and arm.pressure_mode == request["pressure_mode"]
        )
        return _payload(arm, telemetry=True)

    case = campaign.SourceGateCase(
        "prefix_144", "prefix", "evidence_trace", prefix_segments=144
    )
    result = campaign.execute_case(
        case,
        binary=Path("build/fake.pyd"),
        root=ROOT,
        executor=fake_executor,
        input_loader=_input,
        graph=([(1, 0, 1.0, 0, 0, [])], [], [[0.0]]),
    )

    assert result["status"] == "COMPLETE"
    assert len(calls) == 3
    assert all("scorer_model_path" not in request for request in calls)
    assert result["arms"]["A1"]["source_counters"] == {
        "source_admission_attempt_count": 4,
        "source_admission_admitted_count": 1,
        "source_admission_local_resource_hold_count": 1,
        "source_admission_downstream_pressure_hold_count": 2,
        "source_admission_beacon_read_count": 4,
        "source_admission_max_observed_downstream_pressure": 3,
        "source_admission_hold_retry_count": 3,
    }
    assert (
        result["arms"]["A1"]["hold_observation"][
            "distinct_hold_opportunity_count"
        ]
        == 2
    )
    assert result["arms"]["A0"]["metrics"]["mean_tth_seconds"] == 5.0
    assert result["arms"]["A1"]["metrics"]["source_wait_mean_seconds"] == 2.0
    assert result["arms"]["A2"]["metrics"]["event_count"] == 12
    comparisons = {row["treatment_arm"]: row for row in result["comparisons"]}
    assert comparisons["A1"]["treatment_minus_baseline"]["mean_tth_seconds"] == 1.0
    assert comparisons["A2"]["treatment_minus_baseline"]["mean_tth_seconds"] == -1.0
    serialized = json.dumps(result)
    assert "interval_ordinal" not in serialized
    assert result["runtime_contract"]["raw_source_wait_rows_persisted"] is False


def test_capacity_fake_executor_collects_counters_but_no_wait_trace() -> None:
    def fake_executor(request: Mapping[str, Any]) -> Mapping[str, Any]:
        arm = next(
            arm
            for arm in campaign.SOURCE_ARMS
            if arm.admission_mode == request["admission_mode"]
            and arm.pressure_mode == request["pressure_mode"]
        )
        assert request["enable_g4irsf17_source_wait_telemetry"] is False
        return _payload(arm, telemetry=False)

    result = campaign.execute_case(
        campaign.SourceGateCase("scale_1x", "scale", "capacity", None, 1),
        binary=Path("build/fake.pyd"),
        root=ROOT,
        executor=fake_executor,
        input_loader=_input,
        graph=([(1, 0, 1.0, 0, 0, [])], [], [[0.0]]),
    )
    assert result["status"] == "COMPLETE"
    assert all(
        arm["hold_observation"]["status"] == "NOT_COLLECTED_CAPACITY_MODE"
        for arm in result["arms"].values()
    )
    assert all(
        arm["source_counters"]["source_admission_attempt_count"] > 0
        for arm in result["arms"].values()
    )


def test_compact_artifacts_are_atomic_and_explain_hold_boundary(tmp_path: Path) -> None:
    case = campaign.SourceGateCase("prefix_144", "prefix", "evidence_trace", 144)
    result = campaign.execute_case(
        case,
        binary=Path("build/fake.pyd"),
        root=ROOT,
        executor=lambda request: _payload(
            next(
                arm
                for arm in campaign.SOURCE_ARMS
                if arm.admission_mode == request["admission_mode"]
                and arm.pressure_mode == request["pressure_mode"]
            ),
            telemetry=True,
        ),
        input_loader=_input,
        graph=([(1, 0, 1.0, 0, 0, [])], [], [[0.0]]),
    )
    value = {
        "schema": campaign.SCHEMA_CAMPAIGN,
        "status": "COMPLETE",
        "cases": [result],
        "rows": campaign._flatten_results([result]),
    }
    json_path = tmp_path / "campaign.json"
    csv_path = tmp_path / "campaign.csv"
    report_path = tmp_path / "campaign.md"
    closed_loop_path = tmp_path / "closed_loop.md"
    campaign.write_campaign_artifacts(
        value,
        json_path=json_path,
        csv_path=csv_path,
        report_path=report_path,
        closed_loop_report_path=closed_loop_path,
    )

    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "COMPLETE"
    assert "distinct_hold_opportunity_count" in csv_path.read_text(encoding="utf-8")
    report = report_path.read_text(encoding="utf-8")
    assert "HOLD only defers admission" in report
    closed_loop = closed_loop_path.read_text(encoding="utf-8")
    assert "NOT_A_LEARNED_CLOSED_LOOP_CAMPAIGN" in closed_loop
    assert "not distinct bag mutations" in closed_loop
    assert not list(tmp_path.glob(".*.tmp"))
