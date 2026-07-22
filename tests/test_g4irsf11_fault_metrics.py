from __future__ import annotations

import math

from scripts.eval.g4irsf11_fault_metrics import (
    FaultWindow,
    _recovery_time,
    fault_window_metrics,
)


def _summary(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "fault_policy_enabled": True,
        "fault_affected_bag_count": 1,
        "fault_target_edge_candidate_exposure_count": 1,
        "fault_target_edge_attempt_count": 1,
        "physical_fault_interlock_rejection_count": 0,
        "physical_fault_interlock_hold_count": 0,
        "physical_fault_interlock_reroute_count": 0,
        "local_fault_policy_action_count": 1,
        "local_fault_policy_hold_count": 0,
        "local_fault_policy_reroute_count": 1,
        "physical_fault_edge_entry_violation_count": 0,
        "sensor_loss_mode_used": False,
        "runtime_full_astar_calls": 0,
    }
    row.update(overrides)
    return row


def _control_events(*, drop_notification: bool = False) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = [
        {
            "event": "FAULT",
            "phase": "physical_state_change",
            "time": 10.0,
            "from_node": 0,
            "to_node": 1,
            "fault_policy_enabled": True,
        },
        {
            "event": "REPAIR",
            "phase": "physical_state_change",
            "time": 20.0,
            "from_node": 0,
            "to_node": 1,
            "fault_policy_enabled": True,
        },
    ]
    if drop_notification:
        rows.extend(
            [
                {
                    "event": "FAULT",
                    "phase": "notification_dropped",
                    "time": 10.0,
                    "from_node": 0,
                    "to_node": 1,
                    "notification_dropped": True,
                    "fault_policy_enabled": True,
                },
                {
                    "event": "REPAIR",
                    "phase": "notification_dropped",
                    "time": 20.0,
                    "from_node": 0,
                    "to_node": 1,
                    "notification_dropped": True,
                    "fault_policy_enabled": True,
                },
            ]
        )
    else:
        rows.extend(
            [
                {
                    "event": "FAULT",
                    "phase": "local_message_delivery",
                    "time": 12.0,
                    "from_node": 0,
                    "to_node": 1,
                    "fault_policy_enabled": True,
                },
                {
                    "event": "REPAIR",
                    "phase": "local_message_delivery",
                    "time": 22.0,
                    "from_node": 0,
                    "to_node": 1,
                    "fault_policy_enabled": True,
                },
            ]
        )
    return rows


def _bags() -> list[dict[str, object]]:
    return [
        {
            "runtime_bag_id": 6,
            "release_time": 0.0,
            "finish_time": 5.0,
            "completed": True,
        },
        {
            "runtime_bag_id": 7,
            "release_time": 12.0,
            "finish_time": 22.0,
            "completed": True,
        },
    ]


def _exposure_events(*, policy_enabled: bool = True) -> list[dict[str, object]]:
    common = {
        "event": "ARRIVE_JUNCTION",
        "time": 13.0,
        "from_node": 0,
        "to_node": 1,
        "runtime_bag_id": 7,
        "task_id": 70,
        "segment_id": "70:direct",
        "fault_policy_enabled": policy_enabled,
    }
    rows = [
        {**common, "phase": "target_edge_candidate_exposure"},
        {**common, "phase": "target_edge_attempt"},
    ]
    if policy_enabled:
        rows.append(
            {
                **common,
                "phase": "local_fault_policy_reroute",
                "selected_next_node": 2,
            }
        )
    else:
        rows.extend(
            [
                {**common, "phase": "physical_fault_interlock_rejection"},
                {**common, "phase": "physical_fault_interlock_hold"},
            ]
        )
    return rows


def test_temporal_fault_requires_non_vacuous_policy_exposure() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    events = _control_events() + _exposure_events()

    row = fault_window_metrics(
        _bags(), events, _summary(), [window], max_recovery_seconds=5.0
    )[0]

    assert row["physical_fault_event_count"] == 1
    assert row["physical_repair_event_count"] == 1
    assert row["message_delivery_event_count"] == 2
    assert row["target_edge_candidate_exposure_count"] == 1
    assert row["target_edge_attempt_count"] == 1
    assert row["affected_cohort_count"] == 1
    assert row["affected_cohort_complete_count"] == 1
    assert row["local_fault_policy_reroute_count"] == 1
    assert row["recovery_observed"] is True
    assert row["recovery_time_seconds"] == 2.0
    assert row["recovery_time_pass"] is True
    assert row["fault_recovery_gate_failures"] == []
    assert row["fault_recovery_pass"] is True


def test_policy_off_uses_only_non_disableable_physical_interlock() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    control = [
        {**row, "fault_policy_enabled": False} for row in _control_events()
    ]
    summary = _summary(
        fault_policy_enabled=False,
        physical_fault_interlock_rejection_count=1,
        physical_fault_interlock_hold_count=1,
        local_fault_policy_action_count=0,
        local_fault_policy_reroute_count=0,
    )
    row = fault_window_metrics(
        _bags(),
        control + _exposure_events(policy_enabled=False),
        summary,
        [window],
        max_recovery_seconds=5.0,
    )[0]

    assert row["fault_policy_enabled"] is False
    assert row["physical_interlock_rejection_count"] == 1
    assert row["physical_interlock_hold_count"] == 1
    assert row["local_fault_policy_action_count"] == 0
    assert row["policy_action_evidence_pass"] is True
    assert row["fault_recovery_pass"] is True


def test_zero_bag_or_zero_exposure_can_never_pass() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    summary = _summary(
        fault_affected_bag_count=0,
        fault_target_edge_candidate_exposure_count=0,
        fault_target_edge_attempt_count=0,
        local_fault_policy_action_count=0,
        local_fault_policy_reroute_count=0,
    )

    row = fault_window_metrics(
        [], _control_events(), summary, [window], max_recovery_seconds=5.0
    )[0]

    assert row["affected_cohort_count"] == 0
    assert row["target_edge_candidate_exposure_count"] == 0
    assert row["real_exposure_pass"] is False
    assert "real_exposure_pass" in row["fault_recovery_gate_failures"]
    assert row["fault_recovery_pass"] is False


def test_unrecovered_backlog_is_nullable_fail_closed_negative_evidence() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    bags = _bags()
    # Keep the actually exposed bag complete so this isolates recovery-time
    # evidence from affected-cohort completion evidence.
    bags.append(
        {
            "runtime_bag_id": 8,
            "release_time": 13.0,
            "finish_time": None,
            "completed": False,
        }
    )

    row = fault_window_metrics(
        bags,
        _control_events() + _exposure_events(),
        _summary(),
        [window],
        max_recovery_seconds=5.0,
    )[0]

    assert row["recovery_observed"] is False
    assert row["recovery_time_seconds"] is None
    assert row["recovery_time_pass"] is False
    assert row["affected_completion_pass"] is True
    assert row["fault_recovery_gate_failures"] == ["recovery_time_pass"]
    assert row["fault_recovery_pass"] is False


def test_backlog_already_recovered_at_repair_reports_zero_seconds() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    bags = [
        {
            "runtime_bag_id": 6,
            "release_time": 0.0,
            "finish_time": 15.0,
            "completed": True,
        },
        {
            "runtime_bag_id": 7,
            "release_time": 12.0,
            "finish_time": 22.0,
            "completed": True,
        },
    ]

    row = fault_window_metrics(
        bags,
        _control_events() + _exposure_events(),
        _summary(),
        [window],
        max_recovery_seconds=5.0,
    )[0]

    assert row["backlog_before_fault"] == 1
    assert row["backlog_at_repair"] == 1
    assert row["recovery_observed"] is True
    assert row["recovery_time_seconds"] == 0.0
    assert row["recovery_time_pass"] is True


def test_finite_recovery_over_slo_is_distinct_from_unobserved_recovery() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    bags = _bags()
    bags[1]["finish_time"] = 27.0

    row = fault_window_metrics(
        bags,
        _control_events() + _exposure_events(),
        _summary(),
        [window],
        max_recovery_seconds=5.0,
    )[0]

    assert row["recovery_observed"] is True
    assert row["recovery_time_seconds"] == 7.0
    assert row["recovery_time_pass"] is False
    assert row["fault_recovery_gate_failures"] == ["recovery_time_pass"]


def test_recovery_sweep_scans_large_bag_sequence_only_once() -> None:
    class CountingRows(list[dict[str, object]]):
        iteration_count = 0

        def __iter__(self):  # type: ignore[no-untyped-def]
            self.iteration_count += 1
            return super().__iter__()

    bags = CountingRows(
        [
            {
                "runtime_bag_id": index,
                "release_time": 12.0,
                "finish_time": 21.0 + index,
                "completed": True,
            }
            for index in range(500)
        ]
        + [
            {
                "runtime_bag_id": 500,
                "release_time": 12.0,
                "finish_time": None,
                "completed": False,
            }
        ]
    )

    assert _recovery_time(bags, FaultWindow(0, 1, 10.0, 20.0)) is None
    assert bags.iteration_count == 1


def test_missing_critical_summary_fields_fail_closed() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    row = fault_window_metrics(
        _bags(),
        _control_events() + _exposure_events(),
        {},
        [window],
        max_recovery_seconds=5.0,
    )[0]

    assert row["summary_contract_complete"] is False
    assert "fault_policy_enabled" in row["missing_summary_fields"]
    assert "summary_contract_complete" in row["fault_recovery_gate_failures"]
    assert row["fault_recovery_pass"] is False


def test_sensor_loss_requires_observed_physical_interlock_boundary() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0, True)
    base_exposure = _exposure_events(policy_enabled=False)
    exposure = [
        {**row, "fault_policy_enabled": True} for row in base_exposure
    ]
    summary = _summary(
        sensor_loss_mode_used=True,
        physical_fault_interlock_rejection_count=1,
        physical_fault_interlock_hold_count=1,
        local_fault_policy_action_count=0,
        local_fault_policy_reroute_count=0,
    )
    row = fault_window_metrics(
        _bags(),
        _control_events(drop_notification=True) + exposure,
        summary,
        [window],
        max_recovery_seconds=5.0,
    )[0]

    assert row["notification_dropped_event_count"] == 2
    assert row["local_fault_policy_action_count"] == 0
    assert row["physical_interlock_rejection_count"] == 1
    assert row["sensor_loss_interlock_boundary_pass"] is True
    assert row["fault_recovery_pass"] is True

    without_interlock = [
        event
        for event in _control_events(drop_notification=True) + exposure
        if event.get("phase")
        not in {"physical_fault_interlock_rejection", "physical_fault_interlock_hold"}
    ]
    failed = fault_window_metrics(
        _bags(),
        without_interlock,
        summary,
        [window],
        max_recovery_seconds=5.0,
    )[0]
    assert failed["sensor_loss_interlock_boundary_pass"] is False
    assert failed["fault_recovery_pass"] is False


def test_static_removal_or_unsafe_fault_entry_cannot_pass() -> None:
    window = FaultWindow(0, 1, 10.0, 20.0, 2.0)
    events = _control_events() + _exposure_events()
    events.append(
        {
            "event": "EDGE_ENTER",
            "phase": "unsafe_edge_entry",
            "time": 15.0,
            "from_node": 0,
            "to_node": 1,
        }
    )
    summary = _summary(physical_fault_edge_entry_violation_count=1)

    row = fault_window_metrics(
        _bags(), events, summary, [window], max_recovery_seconds=5.0
    )[0]

    assert row["fault_edge_traversal_count"] == 1
    assert row["safety_boundary_pass"] is False
    assert row["fault_recovery_pass"] is False

    no_control = fault_window_metrics(
        _bags(),
        _exposure_events(),
        _summary(),
        [window],
        max_recovery_seconds=5.0,
    )[0]
    assert no_control["physical_fault_event_count"] == 0
    assert math.isfinite(no_control["recovery_time_seconds"])
    assert "trace_complete" in no_control["fault_recovery_gate_failures"]
    assert no_control["fault_recovery_pass"] is False
