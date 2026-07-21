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
    result: list[dict[str, Any]] = []
    for index, window in enumerate(windows):
        physical_fault_events = [
            row
            for row in events
            if _event_name(row) == "FAULT"
            and str(row.get("phase", row.get("reason", ""))) == "physical_state_change"
            and int(row.get("from_node", row.get("start", -1))) == window.start
            and int(row.get("to_node", row.get("end", -1))) == window.end
            and abs(_number(row.get("time")) - window.fault_time) <= 1.0e-6
        ]
        physical_repair_events = [
            row
            for row in events
            if _event_name(row) == "REPAIR"
            and str(row.get("phase", row.get("reason", ""))) == "physical_state_change"
            and int(row.get("from_node", row.get("start", -1))) == window.start
            and int(row.get("to_node", row.get("end", -1))) == window.end
            and abs(_number(row.get("time")) - window.repair_time) <= 1.0e-6
        ]
        message_events = [
            row
            for row in events
            if str(row.get("phase", row.get("reason", ""))) == "local_message_delivery"
            and int(row.get("from_node", row.get("start", -1))) == window.start
            and int(row.get("to_node", row.get("end", -1))) == window.end
            and (
                abs(_number(row.get("time")) - (window.fault_time + window.message_delay)) <= 1.0e-6
                or abs(_number(row.get("time")) - (window.repair_time + window.message_delay)) <= 1.0e-6
            )
        ]
        dropped_events = [
            row
            for row in events
            if str(row.get("phase", row.get("reason", ""))) == "notification_dropped"
            and int(row.get("from_node", -1)) == window.start
            and int(row.get("to_node", -1)) == window.end
            and (
                abs(_number(row.get("time")) - window.fault_time) <= 1.0e-6
                or abs(_number(row.get("time")) - window.repair_time) <= 1.0e-6
            )
        ]
        inflight_at_fault_count = sum(
            int(row.get("inflight_traversal_count", 0)) for row in physical_fault_events
        )
        unsafe_entry_events = [
            row
            for row in events
            if _event_name(row) == "EDGE_ENTER"
            and str(row.get("phase", row.get("reason", "unsafe_edge_entry")))
            == "unsafe_edge_entry"
            and int(row.get("from_node", -1)) == window.start
            and int(row.get("to_node", -1)) == window.end
            and window.fault_time <= _number(row.get("time")) < window.repair_time
        ]
        # Count per-window rows from the uncapped audit.  The summary value is
        # run-global and therefore cannot be assigned to every window when a
        # scenario contains multiple independent faults.
        unsafe_entry_count = len(unsafe_entry_events)
        cohort = [
            row
            for row in bags
            if window.fault_time
            <= _number(row.get("release_time", row.get("arrival_time")))
            < window.repair_time
        ]
        cohort_completed = sum(
            _truth(row.get("complete", row.get("completed"))) for row in cohort
        )
        recovery = _recovery_time(bags, window)
        trace_complete = bool(physical_fault_events) and bool(physical_repair_events)
        if window.drop_notification:
            message_complete = len(dropped_events) == 2 and not message_events
        else:
            message_complete = len(message_events) == 2 and not dropped_events
        pass_gate = (
            trace_complete
            and message_complete
            and unsafe_entry_count == 0
            and cohort_completed == len(cohort)
            and recovery <= max_recovery_seconds
        )
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
                "unsafe_edge_entry_during_physical_fault_count": unsafe_entry_count,
                "run_physical_fault_edge_entry_violation_count": int(
                    summary.get("physical_fault_edge_entry_violation_count", unsafe_entry_count)
                ),
                "fault_edge_traversal_count": unsafe_entry_count,
                "during_fault_release_count": len(cohort),
                "during_fault_complete_count": cohort_completed,
                "during_fault_completion_rate": cohort_completed / len(cohort) if cohort else 1.0,
                "backlog_before_fault": _backlog_at(
                    bags, math.nextafter(window.fault_time, -math.inf)
                ),
                "backlog_at_repair": _backlog_at(bags, window.repair_time),
                "recovery_time_seconds": recovery,
                "max_recovery_seconds": max_recovery_seconds,
                "stale_fault_shield_rejection_count": int(
                    summary.get("stale_fault_shield_rejection_count", 0)
                ),
                "resolved_deadlock_count": int(summary.get("resolved_deadlock_count", 0)),
                "unresolved_deadlock_count": int(summary.get("unresolved_deadlock_count", 0)),
                "runtime_full_astar_calls": int(summary.get("runtime_full_astar_calls", 0)),
                "fault_recovery_pass": pass_gate,
            }
        )
    return result
