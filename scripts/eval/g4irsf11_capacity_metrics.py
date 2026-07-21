"""Capacity, queue-stability, fairness and resource metrics for G4IRSF11.

All gates require explicit inputs.  Missing SLO or drain boundaries produce an
UNVERIFIED status; they never inherit a convenient threshold from the data.
"""

from __future__ import annotations

import math
import os
import statistics
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _truth(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass"}
    return bool(value)


def quantile(values: Sequence[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, probability)) * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def jain_fairness(values: Sequence[float]) -> float:
    if not values:
        return 1.0
    nonnegative = [max(0.0, float(value)) for value in values]
    denominator = len(nonnegative) * sum(value * value for value in nonnegative)
    if denominator == 0.0:
        return 1.0
    return sum(nonnegative) ** 2 / denominator


def _linear_slope(xs: Sequence[float], ys: Sequence[float]) -> float:
    if len(xs) < 2 or len(xs) != len(ys):
        return 0.0
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((value - x_mean) ** 2 for value in xs)
    if denominator <= 0.0:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator


@dataclass(frozen=True)
class BacklogMetrics:
    arrival_count: int
    departure_count: int
    peak_backlog: int
    end_backlog: int
    backlog_at_last_arrival: int
    backlog_area_seconds: float
    backlog_slope_per_second: float
    backlog_slope_fraction_of_arrival_rate: float
    arrival_rate_per_second: float
    departure_rate_during_arrivals_per_second: float
    drain_time_seconds: float


def backlog_metrics(
    arrivals: Sequence[float],
    departures: Sequence[float],
    *,
    sample_count: int = 201,
) -> BacklogMetrics:
    arrival_times = sorted(float(value) for value in arrivals)
    departure_times = sorted(float(value) for value in departures)
    if not arrival_times:
        return BacklogMetrics(0, len(departure_times), 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    events = sorted(
        [(time, 1) for time in arrival_times] + [(time, -1) for time in departure_times],
        key=lambda item: (item[0], -item[1]),
    )
    backlog = 0
    peak = 0
    area = 0.0
    previous_time = events[0][0]
    for event_time, delta in events:
        area += backlog * max(0.0, event_time - previous_time)
        backlog += delta
        peak = max(peak, backlog)
        previous_time = event_time

    first_arrival = arrival_times[0]
    last_arrival = arrival_times[-1]
    arrival_span = max(0.0, last_arrival - first_arrival)
    departure_during_arrivals = sum(time <= last_arrival for time in departure_times)
    backlog_at_last = len(arrival_times) - departure_during_arrivals
    arrival_rate = len(arrival_times) / arrival_span if arrival_span > 0.0 else 0.0
    departure_rate = departure_during_arrivals / arrival_span if arrival_span > 0.0 else 0.0

    slope = 0.0
    if arrival_span > 0.0:
        count = max(3, sample_count)
        xs = [first_arrival + arrival_span * index / (count - 1) for index in range(count)]
        ys: list[float] = []
        arrival_index = 0
        departure_index = 0
        for time in xs:
            while arrival_index < len(arrival_times) and arrival_times[arrival_index] <= time:
                arrival_index += 1
            while departure_index < len(departure_times) and departure_times[departure_index] <= time:
                departure_index += 1
            ys.append(float(arrival_index - departure_index))
        warmup = count // 3
        slope = _linear_slope(xs[warmup:], ys[warmup:])

    drain_time = 0.0
    if departure_times:
        drain_time = max(0.0, departure_times[-1] - last_arrival)
    elif arrival_times:
        drain_time = math.inf
    return BacklogMetrics(
        arrival_count=len(arrival_times),
        departure_count=len(departure_times),
        peak_backlog=peak,
        end_backlog=max(0, len(arrival_times) - len(departure_times)),
        backlog_at_last_arrival=max(0, backlog_at_last),
        backlog_area_seconds=area,
        backlog_slope_per_second=slope,
        backlog_slope_fraction_of_arrival_rate=(slope / arrival_rate if arrival_rate > 0.0 else 0.0),
        arrival_rate_per_second=arrival_rate,
        departure_rate_during_arrivals_per_second=departure_rate,
        drain_time_seconds=drain_time,
    )


@dataclass(frozen=True)
class CapacityGateConfig:
    max_backlog_slope_fraction: float
    max_drain_seconds: float
    max_p95_total_seconds: float
    max_p99_total_seconds: float
    max_deadline_miss_rate: float = 0.0
    starvation_seconds: float = math.inf

    def __post_init__(self) -> None:
        for name in (
            "max_backlog_slope_fraction",
            "max_drain_seconds",
            "max_p95_total_seconds",
            "max_p99_total_seconds",
            "max_deadline_miss_rate",
            "starvation_seconds",
        ):
            if _number(getattr(self, name), -1.0) < 0.0:
                raise ValueError(f"{name} must be non-negative")


def capacity_metrics(
    bag_rows: Iterable[Mapping[str, Any]],
    summary: Mapping[str, Any],
    gate: CapacityGateConfig,
) -> dict[str, Any]:
    bags = list(bag_rows)
    arrivals = [_number(row.get("release_time", row.get("arrival_time"))) for row in bags]
    admitted = [
        _number(row.get("admitted_time"))
        for row in bags
        if row.get("admitted_time") not in (None, "")
        and _number(row.get("admitted_time"), -1.0) >= 0.0
    ]
    completed_rows = [
        row for row in bags if _truth(row.get("complete", row.get("completed")))
    ]
    finishes = [
        _number(row.get("finish_time"))
        for row in completed_rows
        if row.get("finish_time") not in (None, "")
    ]
    total_times = [
        _number(row.get("finish_time")) - _number(row.get("release_time", row.get("arrival_time")))
        for row in completed_rows
    ]
    source_delays = [
        _number(row.get("admitted_time")) - _number(row.get("release_time", row.get("arrival_time")))
        for row in bags
        if row.get("admitted_time") not in (None, "")
        and _number(row.get("admitted_time"), -1.0) >= 0.0
    ]
    network_times = [
        _number(row.get("finish_time")) - _number(row.get("admitted_time"))
        for row in completed_rows
        if row.get("admitted_time") not in (None, "")
        and _number(row.get("admitted_time"), -1.0) >= 0.0
    ]
    java_release_tths = [
        _number(row.get("java_release_tth_seconds"))
        for row in completed_rows
        if row.get("java_release_tth_seconds") not in (None, "")
    ]
    service_times = (
        java_release_tths
        if len(java_release_tths) == len(completed_rows) and java_release_tths
        else total_times
    )
    service_time_basis = (
        "sum_segment_java_release_to_finish"
        if service_times is java_release_tths
        else "original_entry_to_finish"
    )
    waits = [
        _number(row.get("total_wait", row.get("total_local_wait"))) for row in bags
    ]
    deadline_rows = [row for row in completed_rows if _number(row.get("deadline")) > 0.0]
    deadline_misses = sum(
        _number(row.get("finish_time")) > _number(row.get("deadline"))
        for row in deadline_rows
    )
    deadline_miss_rate = deadline_misses / len(deadline_rows) if deadline_rows else 0.0

    total_backlog = backlog_metrics(arrivals, finishes)
    source_backlog = backlog_metrics(arrivals, admitted)
    network_backlog = backlog_metrics(admitted, finishes)

    conflict_count = _integer(
        summary.get(
            "conflict_count",
            summary.get("conflicts", summary.get("reservation_conflicts")),
        )
    )
    full_astar_calls = _integer(summary.get("runtime_full_astar_calls", summary.get("full_astar_calls")))
    safe_pass = conflict_count == 0 and full_astar_calls == 0
    slope_pass = (
        total_backlog.backlog_slope_fraction_of_arrival_rate
        <= gate.max_backlog_slope_fraction
    )
    drain_pass = (
        total_backlog.end_backlog == 0
        and total_backlog.drain_time_seconds <= gate.max_drain_seconds
    )
    queue_pass = slope_pass and drain_pass
    p50 = quantile(service_times, 0.50)
    p95 = quantile(service_times, 0.95)
    p99 = quantile(service_times, 0.99)
    starvation_count = sum(value > gate.starvation_seconds for value in waits)
    service_pass = (
        len(completed_rows) == len(bags)
        and p95 <= gate.max_p95_total_seconds
        and p99 <= gate.max_p99_total_seconds
        and deadline_miss_rate <= gate.max_deadline_miss_rate
        and starvation_count == 0
    )

    runtime_seconds = _number(summary.get("runtime_seconds"))
    event_count = _integer(summary.get("event_count"))
    decision_count = _integer(summary.get("decision_count"))
    return {
        "bag_count": len(bags),
        "complete_count": len(completed_rows),
        "failed_count": len(bags) - len(completed_rows),
        "arrival_count": total_backlog.arrival_count,
        "departure_count": total_backlog.departure_count,
        "arrival_rate_per_second": total_backlog.arrival_rate_per_second,
        "departure_rate_during_arrivals_per_second": total_backlog.departure_rate_during_arrivals_per_second,
        "backlog_slope_per_second": total_backlog.backlog_slope_per_second,
        "backlog_slope_fraction_of_arrival_rate": total_backlog.backlog_slope_fraction_of_arrival_rate,
        "backlog_at_last_arrival": total_backlog.backlog_at_last_arrival,
        "end_backlog": total_backlog.end_backlog,
        "peak_backlog": total_backlog.peak_backlog,
        "backlog_area_seconds": total_backlog.backlog_area_seconds,
        "drain_time_seconds": total_backlog.drain_time_seconds,
        "source_peak_backlog": source_backlog.peak_backlog,
        "source_end_backlog": source_backlog.end_backlog,
        "source_backlog_area_seconds": source_backlog.backlog_area_seconds,
        "network_peak_backlog": network_backlog.peak_backlog,
        "network_end_backlog": network_backlog.end_backlog,
        "total_time_mean_seconds": statistics.fmean(total_times) if total_times else 0.0,
        "total_time_p50_seconds": quantile(total_times, 0.50),
        "total_time_p95_seconds": quantile(total_times, 0.95),
        "total_time_p99_seconds": quantile(total_times, 0.99),
        "total_time_max_seconds": max(total_times, default=0.0),
        "java_release_tth_mean_seconds": statistics.fmean(java_release_tths) if java_release_tths else 0.0,
        "java_release_tth_p50_seconds": quantile(java_release_tths, 0.50),
        "java_release_tth_p95_seconds": quantile(java_release_tths, 0.95),
        "java_release_tth_p99_seconds": quantile(java_release_tths, 0.99),
        "service_time_basis": service_time_basis,
        "service_time_p50_seconds": p50,
        "service_time_p95_seconds": p95,
        "service_time_p99_seconds": p99,
        "source_delay_p95_seconds": quantile(source_delays, 0.95),
        "source_delay_p99_seconds": quantile(source_delays, 0.99),
        "network_time_p95_seconds": quantile(network_times, 0.95),
        "deadline_count": len(deadline_rows),
        "deadline_miss_count": deadline_misses,
        "deadline_miss_rate": deadline_miss_rate,
        "starvation_count": starvation_count,
        "max_wait_seconds": max(waits, default=0.0),
        # Convert waiting time to a positive service score before Jain's index;
        # larger score means less waiting and avoids rewarding equal starvation.
        "wait_fairness_jain": jain_fairness([1.0 / (1.0 + value) for value in waits]),
        "conflict_count": conflict_count,
        "deadlock_count": _integer(summary.get("deadlock_count")),
        "loop_count": _integer(summary.get("loop_count")),
        "runtime_full_astar_calls": full_astar_calls,
        "event_count": event_count,
        "decision_count": decision_count,
        "runtime_seconds": runtime_seconds,
        "event_throughput_per_second": event_count / runtime_seconds if runtime_seconds > 0.0 else 0.0,
        "decision_throughput_per_second": decision_count / runtime_seconds if runtime_seconds > 0.0 else 0.0,
        "decision_latency_us_p50": _number(summary.get("decision_latency_us_p50")),
        "decision_latency_us_p95": _number(summary.get("decision_latency_us_p95")),
        "decision_latency_us_p99": _number(summary.get("decision_latency_us_p99")),
        "internal_state_bytes": _integer(
            summary.get("internal_state_bytes", summary.get("cpp_internal_accounted_bytes"))
        ),
        "peak_local_queue": _integer(
            summary.get("peak_local_queue", summary.get("max_junction_queue_length"))
        ),
        "peak_local_calendar": _integer(
            summary.get("peak_local_calendar", summary.get("max_local_calendar_intervals"))
        ),
        "safe_execution_pass": safe_pass,
        "queue_slope_pass": slope_pass,
        "queue_drain_pass": drain_pass,
        "queue_stability_pass": queue_pass,
        "service_level_pass": service_pass,
        "capacity_pass": safe_pass and queue_pass and service_pass,
        "gate_max_backlog_slope_fraction": gate.max_backlog_slope_fraction,
        "gate_max_drain_seconds": gate.max_drain_seconds,
        "gate_max_p95_total_seconds": gate.max_p95_total_seconds,
        "gate_max_p99_total_seconds": gate.max_p99_total_seconds,
        "gate_max_deadline_miss_rate": gate.max_deadline_miss_rate,
        "gate_starvation_seconds": gate.starvation_seconds,
    }


def process_working_set_bytes() -> tuple[int, int]:
    """Return ``(current, peak)`` OS working-set bytes for this process."""

    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel32.GetCurrentProcess()
        try:
            get_memory_info = kernel32.K32GetProcessMemoryInfo
        except AttributeError:
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            get_memory_info = psapi.GetProcessMemoryInfo
        get_memory_info.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        get_memory_info.restype = wintypes.BOOL
        ok = get_memory_info(process, ctypes.byref(counters), counters.cb)
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)

    import resource

    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    # Linux reports KiB; macOS reports bytes.
    peak_bytes = peak if os.uname().sysname == "Darwin" else peak * 1024
    current_bytes = peak_bytes
    try:
        with open("/proc/self/statm", "r", encoding="ascii") as handle:
            resident_pages = int(handle.read().split()[1])
        current_bytes = resident_pages * os.sysconf("SC_PAGE_SIZE")
    except (FileNotFoundError, IndexError, OSError, ValueError):
        pass
    return current_bytes, peak_bytes


def current_peak_working_set_bytes() -> int:
    """Return OS-reported peak working set, never a JSON-row estimate."""

    return process_working_set_bytes()[1]
