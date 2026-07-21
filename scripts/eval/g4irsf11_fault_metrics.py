"""Temporal fault/repair metrics for the G4IRSF11 local runtime."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _truth(value: Any) -> bool:
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes", "pass"}
    return bool(value)


@dataclass(frozen=True)
class FaultWindow:
    start: int
    end: int
    fault_time: float
    repair_time: float
    message_delay: float = 0.0
    drop_notification: bool = False

    def __post_init__(self) -> None:
        if self.repair_time <= self.fault_time:
            raise ValueError("repair_time must be greater than fault_time")
        if self.message_delay < 0.0:
            raise ValueError("message_delay must be non-negative")


def _event_name(row: Mapping[str, Any]) -> str:
    return str(row.get("event", row.get("type", ""))).upper()


_REQUIRED_FAULT_SUMMARY_FIELDS = (
    "fault_policy_enabled",
    "fault_affected_bag_count",
    "fault_target_edge_candidate_exposure_count",
    "fault_target_edge_attempt_count",
    "physical_fault_interlock_rejection_count",
    "physical_fault_interlock_hold_count",
    "physical_fault_interlock_reroute_count",
    "local_fault_policy_action_count",
    "local_fault_policy_hold_count",
    "local_fault_policy_reroute_count",
    "physical_fault_edge_entry_violation_count",
    "sensor_loss_mode_used",
    "runtime_full_astar_calls",
)


def _backlog_at(bags: Sequence[Mapping[str, Any]], time: float) -> int:
    arrived = sum(
        _number(row.get("release_time", row.get("arrival_time"))) <= time
        for row in bags
    )
    finished = sum(
        row.get("finish_time") not in (None, "", -1, -1.0)
        and _number(row.get("finish_time")) <= time
        for row in bags
    )
    return max(0, arrived - finished)


def _recovery_time(
    bags: Sequence[Mapping[str, Any]], window: FaultWindow
) -> float:
    baseline = _backlog_at(bags, math.nextafter(window.fault_time, -math.inf))
    completion_times = sorted(
        _number(row.get("finish_time"))
        for row in bags
        if row.get("finish_time") not in (None, "", -1, -1.0)
        and _number(row.get("finish_time")) >= window.repair_time
    )
    for time in completion_times:
        if _backlog_at(bags, time) <= baseline:
            return time - window.repair_time
    if _backlog_at(bags, window.repair_time) <= baseline:
        return 0.0
    return math.inf


def fault_window_metrics(
    bag_rows: Iterable[Mapping[str, Any]],
    fault_audit_rows: Iterable[Mapping[str, Any]],
    summary: Mapping[str, Any],
    windows: Sequence[FaultWindow],
    *,
    max_recovery_seconds: float,
) -> list[dict[str, Any]]:
    if max_recovery_seconds < 0.0:
        raise ValueError("max_recovery_seconds must be non-negative")
    bags = list(bag_rows)
    events = list(fault_audit_rows)
    missing_summary_fields = [
        field for field in _REQUIRED_FAULT_SUMMARY_FIELDS if field not in summary
    ]
    summary_contract_complete = not missing_summary_fields
    policy_enabled = (
        _truth(summary["fault_policy_enabled"])
        if summary_contract_complete
        else None
    )
    bag_by_runtime_id: dict[int, Mapping[str, Any]] = {}
    duplicate_runtime_bag_ids: set[int] = set()
    for bag in bags:
        if "runtime_bag_id" not in bag:
            continue
        runtime_bag_id = int(bag["runtime_bag_id"])
        if runtime_bag_id in bag_by_runtime_id:
            duplicate_runtime_bag_ids.add(runtime_bag_id)
        bag_by_runtime_id[runtime_bag_id] = bag

    result: list[dict[str, Any]] = []
    for index, window in enumerate(windows):
        def on_edge(row: Mapping[str, Any]) -> bool:
            return (
                int(row.get("from_node", row.get("start", -1))) == window.start
                and int(row.get("to_node", row.get("end", -1))) == window.end
            )

        def during_physical_fault(row: Mapping[str, Any]) -> bool:
            return window.fault_time <= _number(row.get("time")) < window.repair_time

        physical_fault_events = [
            row
            for row in events
            if _event_name(row) == "FAULT"
            and str(row.get("phase", row.get("reason", ""))) == "physical_state_change"
            and on_edge(row)
            and abs(_number(row.get("time")) - window.fault_time) <= 1.0e-6
        ]
        physical_repair_events = [
            row
            for row in events
            if _event_name(row) == "REPAIR"
            and str(row.get("phase", row.get("reason", ""))) == "physical_state_change"
            and on_edge(row)
            and abs(_number(row.get("time")) - window.repair_time) <= 1.0e-6
        ]
        message_events = [
            row
            for row in events
            if str(row.get("phase", row.get("reason", ""))) == "local_message_delivery"
            and on_edge(row)
            and (
                abs(_number(row.get("time")) - (window.fault_time + window.message_delay)) <= 1.0e-6
                or abs(_number(row.get("time")) - (window.repair_time + window.message_delay)) <= 1.0e-6
            )
        ]
        dropped_events = [
            row
            for row in events
            if str(row.get("phase", row.get("reason", ""))) == "notification_dropped"
            and on_edge(row)
            and (
                abs(_number(row.get("time")) - window.fault_time) <= 1.0e-6
                or abs(_number(row.get("time")) - window.repair_time) <= 1.0e-6
            )
        ]
        inflight_at_fault_count = sum(
            int(row.get("inflight_traversal_count", 0)) for row in physical_fault_events
        )
        candidate_exposures = [
            row
            for row in events
            if str(row.get("phase", "")) == "target_edge_candidate_exposure"
            and on_edge(row)
            and during_physical_fault(row)
        ]
        target_attempts = [
            row
            for row in events
            if str(row.get("phase", "")) == "target_edge_attempt"
            and on_edge(row)
            and during_physical_fault(row)
        ]
        interlock_rejections = [
            row
            for row in events
            if str(row.get("phase", "")) == "physical_fault_interlock_rejection"
            and on_edge(row)
            and during_physical_fault(row)
        ]
        interlock_holds = [
            row
            for row in events
            if str(row.get("phase", "")) == "physical_fault_interlock_hold"
            and on_edge(row)
            and during_physical_fault(row)
        ]
        interlock_reroutes = [
            row
            for row in events
            if str(row.get("phase", "")) == "physical_fault_interlock_reroute"
            and on_edge(row)
            and during_physical_fault(row)
        ]
        local_policy_actions = [
            row
            for row in events
            if str(row.get("phase", ""))
            in {"local_fault_policy_hold", "local_fault_policy_reroute"}
            and on_edge(row)
            and during_physical_fault(row)
        ]
        local_policy_holds = [
            row
            for row in local_policy_actions
            if str(row.get("phase", "")) == "local_fault_policy_hold"
        ]
        local_policy_reroutes = [
            row
            for row in local_policy_actions
            if str(row.get("phase", "")) == "local_fault_policy_reroute"
        ]
        unsafe_entry_events = [
            row
            for row in events
            if _event_name(row) == "EDGE_ENTER"
            and str(row.get("phase", row.get("reason", "unsafe_edge_entry")))
            == "unsafe_edge_entry"
            and on_edge(row)
            and during_physical_fault(row)
        ]
        # Count per-window rows from the uncapped audit.  The summary value is
        # run-global and therefore cannot be assigned to every window when a
        # scenario contains multiple independent faults.
        unsafe_entry_count = len(unsafe_entry_events)
        release_cohort = [
            row
            for row in bags
            if window.fault_time
            <= _number(row.get("release_time", row.get("arrival_time")))
            < window.repair_time
        ]
        release_cohort_completed = sum(
            _truth(row.get("complete", row.get("completed")))
            for row in release_cohort
        )
        affected_runtime_ids = {
            int(row["runtime_bag_id"])
            for row in candidate_exposures
            if "runtime_bag_id" in row and int(row["runtime_bag_id"]) >= 0
        }
        affected_bags = [
            bag_by_runtime_id[runtime_bag_id]
            for runtime_bag_id in sorted(affected_runtime_ids)
            if runtime_bag_id in bag_by_runtime_id
        ]
        affected_link_complete = (
            bool(affected_runtime_ids)
            and len(affected_bags) == len(affected_runtime_ids)
            and not (affected_runtime_ids & duplicate_runtime_bag_ids)
        )
        affected_completed = sum(
            _truth(row.get("complete", row.get("completed")))
            for row in affected_bags
        )
        recovery = _recovery_time(bags, window)
        trace_complete = bool(physical_fault_events) and bool(physical_repair_events)
        if window.drop_notification:
            message_complete = len(dropped_events) == 2 and not message_events
        else:
            message_complete = len(message_events) == 2 and not dropped_events

        real_exposure_pass = (
            len(candidate_exposures) > 0
            and len(target_attempts) > 0
            and len(affected_runtime_ids) > 0
            and affected_link_complete
        )
        affected_completion_pass = (
            affected_link_complete
            and affected_completed == len(affected_runtime_ids)
        )
        policy_audit_consistent = all(
            _truth(row.get("fault_policy_enabled")) == policy_enabled
            for row in candidate_exposures
            + target_attempts
            + interlock_rejections
            + local_policy_actions
        ) if policy_enabled is not None else False
        if policy_enabled is None:
            policy_action_evidence_pass = False
        elif window.drop_notification:
            # With notifications intentionally lost, only the non-disableable
            # physical interlock may act.  Treat any advertised-policy action
            # as fabricated evidence.
            policy_action_evidence_pass = (
                not local_policy_actions and bool(interlock_rejections)
            )
        elif policy_enabled:
            policy_action_evidence_pass = bool(local_policy_actions)
        else:
            policy_action_evidence_pass = (
                not local_policy_actions and bool(interlock_rejections)
            )
        sensor_loss_interlock_boundary_pass = (
            not window.drop_notification
            or (
                _truth(summary.get("sensor_loss_mode_used", False))
                and len(dropped_events) == 2
                and bool(interlock_rejections)
                and not local_policy_actions
                and unsafe_entry_count == 0
            )
        )
        summary_counts_consistent = False
        if summary_contract_complete:
            summary_counts_consistent = (
                int(summary["fault_affected_bag_count"]) >= len(affected_runtime_ids)
                and int(summary["fault_target_edge_candidate_exposure_count"])
                >= len(candidate_exposures)
                and int(summary["fault_target_edge_attempt_count"])
                >= len(target_attempts)
                and int(summary["physical_fault_interlock_rejection_count"])
                >= len(interlock_rejections)
                and int(summary["physical_fault_interlock_hold_count"])
                >= len(interlock_holds)
                and int(summary["physical_fault_interlock_reroute_count"])
                >= len(interlock_reroutes)
                and int(summary["local_fault_policy_action_count"])
                >= len(local_policy_actions)
                and int(summary["local_fault_policy_hold_count"])
                >= len(local_policy_holds)
                and int(summary["local_fault_policy_reroute_count"])
                >= len(local_policy_reroutes)
            )
        safety_boundary_pass = (
            unsafe_entry_count == 0
            and summary_contract_complete
            and int(summary["physical_fault_edge_entry_violation_count"]) == 0
            and int(summary["runtime_full_astar_calls"]) == 0
        )

        gate_checks = {
            "summary_contract_complete": summary_contract_complete,
            "summary_counts_consistent": summary_counts_consistent,
            "policy_audit_consistent": policy_audit_consistent,
            "trace_complete": trace_complete,
            "message_complete": message_complete,
            "real_exposure_pass": real_exposure_pass,
            "affected_completion_pass": affected_completion_pass,
            "policy_action_evidence_pass": policy_action_evidence_pass,
            "sensor_loss_interlock_boundary_pass": sensor_loss_interlock_boundary_pass,
            "safety_boundary_pass": safety_boundary_pass,
            "recovery_time_pass": recovery <= max_recovery_seconds,
        }
        pass_gate = all(gate_checks.values())
        gate_failures = [name for name, passed in gate_checks.items() if not passed]
        result.append(
            {
                "fault_window_index": index,
                "edge_start": window.start,
                "edge_end": window.end,
                "fault_time": window.fault_time,
                "repair_time": window.repair_time,
                "fault_duration_seconds": window.repair_time - window.fault_time,
                "message_delay_seconds": window.message_delay,
                "drop_notification": window.drop_notification,
                "physical_fault_event_count": len(physical_fault_events),
                "physical_repair_event_count": len(physical_repair_events),
                "message_delivery_event_count": len(message_events),
                "notification_dropped_event_count": len(dropped_events),
                "inflight_at_fault_count": inflight_at_fault_count,
                "fault_policy_enabled": policy_enabled,
                "target_edge_candidate_exposure_count": len(candidate_exposures),
                "target_edge_attempt_count": len(target_attempts),
                "affected_cohort_count": len(affected_runtime_ids),
                "affected_cohort_complete_count": affected_completed,
                "affected_cohort_completion_rate": (
                    affected_completed / len(affected_runtime_ids)
                    if affected_runtime_ids
                    else 0.0
                ),
                "affected_cohort_link_complete": affected_link_complete,
                "physical_interlock_rejection_count": len(interlock_rejections),
                "physical_interlock_hold_count": len(interlock_holds),
                "physical_interlock_reroute_count": len(interlock_reroutes),
                "local_fault_policy_action_count": len(local_policy_actions),
                "local_fault_policy_hold_count": len(local_policy_holds),
                "local_fault_policy_reroute_count": len(local_policy_reroutes),
                "unsafe_edge_entry_during_physical_fault_count": unsafe_entry_count,
                "run_physical_fault_edge_entry_violation_count": int(
                    summary["physical_fault_edge_entry_violation_count"]
                ) if summary_contract_complete else None,
                "fault_edge_traversal_count": unsafe_entry_count,
                "during_fault_release_count": len(release_cohort),
                "during_fault_complete_count": release_cohort_completed,
                "during_fault_completion_rate": (
                    release_cohort_completed / len(release_cohort)
                    if release_cohort
                    else 0.0
                ),
                "backlog_before_fault": _backlog_at(
                    bags, math.nextafter(window.fault_time, -math.inf)
                ),
                "backlog_at_repair": _backlog_at(bags, window.repair_time),
                "recovery_time_seconds": recovery,
                "max_recovery_seconds": max_recovery_seconds,
                "summary_contract_complete": summary_contract_complete,
                "missing_summary_fields": missing_summary_fields,
                "summary_counts_consistent": summary_counts_consistent,
                "policy_audit_consistent": policy_audit_consistent,
                "real_exposure_pass": real_exposure_pass,
                "affected_completion_pass": affected_completion_pass,
                "policy_action_evidence_pass": policy_action_evidence_pass,
                "sensor_loss_interlock_boundary_pass": sensor_loss_interlock_boundary_pass,
                "safety_boundary_pass": safety_boundary_pass,
                "fault_recovery_gate_failures": gate_failures,
                "stale_fault_shield_rejection_count": (
                    int(summary["stale_fault_shield_rejection_count"])
                    if "stale_fault_shield_rejection_count" in summary
                    else None
                ),
                "resolved_deadlock_count": (
                    int(summary["resolved_deadlock_count"])
                    if "resolved_deadlock_count" in summary
                    else None
                ),
                "unresolved_deadlock_count": (
                    int(summary["unresolved_deadlock_count"])
                    if "unresolved_deadlock_count" in summary
                    else None
                ),
                "runtime_full_astar_calls": (
                    int(summary["runtime_full_astar_calls"])
                    if summary_contract_complete
                    else None
                ),
                "fault_recovery_pass": pass_gate,
            }
        )
    return result
