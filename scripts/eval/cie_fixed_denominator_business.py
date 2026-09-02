"""Fixed-denominator raw-bag business metrics for CIE revision runs.

Incomplete bags remain in every denominator. Their fixed-horizon tardiness
uses the horizon as an observed lower bound; it is never presented as a
completed-bag latency or survivor timing.
"""

from __future__ import annotations

import math
import statistics
from typing import Any, Mapping, Sequence

from scripts.eval import g4irsf11_capacity_metrics as capacity


class BusinessMetricError(RuntimeError):
    """Raised when protected input/result identity is ambiguous."""


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BusinessMetricError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise BusinessMetricError(f"{name} must be finite")
    return result


def _completed(row: Mapping[str, Any]) -> bool:
    return bool(row.get("completed", row.get("complete", False)))


def _describe(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "mean": None,
            "p50": None,
            "p95": None,
            "p99": None,
            "max": None,
            "sum": 0.0,
        }
    numbers = [float(value) for value in values]
    return {
        "count": len(numbers),
        "min": min(numbers),
        "mean": statistics.fmean(numbers),
        "p50": capacity.quantile(numbers, 0.50),
        "p95": capacity.quantile(numbers, 0.95),
        "p99": capacity.quantile(numbers, 0.99),
        "max": max(numbers),
        "sum": math.fsum(numbers),
    }


def _backlog(
    arrivals: Sequence[float],
    departures: Sequence[float],
    *,
    observation_end: float,
) -> dict[str, Any]:
    return vars(
        capacity.backlog_metrics(
            arrivals,
            departures,
            observation_end=observation_end,
        )
    )


def summarize(
    input_rows: Sequence[Mapping[str, Any]],
    result_rows: Sequence[Mapping[str, Any]],
    *,
    fixed_horizon: float,
) -> dict[str, Any]:
    horizon = _finite(fixed_horizon, "fixed_horizon")
    inputs_by_segment: dict[str, Mapping[str, Any]] = {}
    inputs_by_task: dict[int, list[Mapping[str, Any]]] = {}
    for row in input_rows:
        segment_id = str(row.get("segment_id", ""))
        if not segment_id or segment_id in inputs_by_segment:
            raise BusinessMetricError("input segment IDs must be unique and non-empty")
        inputs_by_segment[segment_id] = row
        inputs_by_task.setdefault(int(row["task_id"]), []).append(row)

    results_by_segment: dict[str, Mapping[str, Any]] = {}
    for row in result_rows:
        segment_id = str(row.get("segment_id", ""))
        if segment_id not in inputs_by_segment or segment_id in results_by_segment:
            raise BusinessMetricError(
                "runtime segment identity is missing, duplicate, or foreign"
            )
        results_by_segment[segment_id] = row
    if set(results_by_segment) != set(inputs_by_segment):
        raise BusinessMetricError("runtime must return every protected segment")

    raw_rows: list[dict[str, Any]] = []
    for task_id, task_inputs in sorted(inputs_by_task.items()):
        task_results = [results_by_segment[str(row["segment_id"])] for row in task_inputs]
        arrival = min(
            _finite(row.get("original_entry_time", row["pass_time"]), "raw arrival")
            for row in task_inputs
        )
        std = min(_finite(row["std"], "STD") for row in task_inputs)
        complete = all(_completed(row) for row in task_results)
        finish = (
            max(_finite(row["finish_time"], "finish_time") for row in task_results)
            if complete
            else None
        )
        admissions = [
            _finite(row["admitted_time"], "admitted_time")
            for row in task_results
            if row.get("admitted_time") not in (None, "")
            and float(row["admitted_time"]) >= 0.0
        ]
        fully_admitted = max(admissions) if len(admissions) == len(task_results) else None
        observed_endpoint = finish if finish is not None else horizon
        tardiness = max(0.0, observed_endpoint - std)
        on_time = finish is not None and finish <= std
        raw_rows.append(
            {
                "task_id": task_id,
                "arrival": arrival,
                "std": std,
                "complete": complete,
                "finish": finish,
                "fully_admitted": fully_admitted,
                "on_time": on_time,
                "fixed_horizon_tardiness_lower_bound": tardiness,
            }
        )

    denominator = len(raw_rows)
    if denominator == 0:
        raise BusinessMetricError("raw-bag denominator cannot be zero")
    complete_rows = [row for row in raw_rows if row["complete"]]
    on_time_count = sum(bool(row["on_time"]) for row in raw_rows)
    finishes = [float(row["finish"]) for row in complete_rows]
    arrivals = [float(row["arrival"]) for row in raw_rows]
    fully_admitted = [
        float(row["fully_admitted"])
        for row in raw_rows
        if row["fully_admitted"] is not None
    ]

    completion_targets: dict[str, Any] = {}
    ordered_finishes = sorted(finishes)
    first_arrival = min(arrivals)
    for label, fraction in (("90", 0.90), ("95", 0.95), ("99", 0.99)):
        required = math.ceil(denominator * fraction)
        reached = len(ordered_finishes) >= required
        epoch = ordered_finishes[required - 1] if reached else None
        completion_targets[f"time_to_{label}_percent"] = {
            "required_raw_bag_count": required,
            "reached": reached,
            "epoch_seconds": epoch,
            "elapsed_from_first_arrival_seconds": epoch - first_arrival if reached else None,
        }

    missed_by_flight: dict[float, int] = {}
    for row in raw_rows:
        missed_by_flight.setdefault(float(row["std"]), 0)
        if not row["on_time"]:
            missed_by_flight[float(row["std"])] += 1

    segment_arrivals = [
        _finite(row.get("release_time", row.get("arrival_time")), "segment release")
        for row in result_rows
    ]
    segment_admissions = [
        _finite(row["admitted_time"], "segment admitted")
        for row in result_rows
        if row.get("admitted_time") not in (None, "")
        and float(row["admitted_time"]) >= 0.0
    ]
    segment_finishes = [
        _finite(row["finish_time"], "segment finish")
        for row in result_rows
        if _completed(row)
    ]

    return {
        "denominator_raw_bags": denominator,
        "completed_raw_bag_count": len(complete_rows),
        "completion_rate": len(complete_rows) / denominator,
        "on_time_raw_bag_count": on_time_count,
        "on_time_rate": on_time_count / denominator,
        "missed_bag_count": denominator - on_time_count,
        "missed_bag_rate": 1.0 - on_time_count / denominator,
        "tardiness_seconds": {
            "fixed_horizon_all_population_lower_bound": _describe(
                [float(row["fixed_horizon_tardiness_lower_bound"]) for row in raw_rows]
            ),
            "completed_population_only_diagnostic": _describe(
                [max(0.0, float(row["finish"]) - float(row["std"])) for row in complete_rows]
            ),
            "incomplete_bags_use_fixed_horizon_not_survivor_timing": True,
        },
        "per_flight_missed_bag_count": _describe(list(missed_by_flight.values())),
        "completion_targets": completion_targets,
        "backlog": {
            "raw_bag_total": _backlog(
                arrivals, finishes, observation_end=horizon
            ),
            "raw_bag_source_until_all_segments_admitted": _backlog(
                arrivals, fully_admitted, observation_end=horizon
            ),
            "raw_bag_network_after_all_segments_admitted": _backlog(
                fully_admitted, finishes, observation_end=horizon
            ),
            "segment_source": _backlog(
                segment_arrivals, segment_admissions, observation_end=horizon
            ),
            "segment_network": _backlog(
                segment_admissions, segment_finishes, observation_end=horizon
            ),
        },
        "backlog_area_contract": {
            "method": capacity.BACKLOG_AREA_METHOD_OBSERVATION_END_V2,
            "observation_end_seconds": horizon,
            "tail_backlog_integrated_to_observation_end": True,
            "legacy_incomplete_last_event_area_is_not_reportable_without_exact_correction": True,
        },
        "fixed_horizon_seconds": horizon,
        "fixed_denominator": True,
        "survivor_or_common_cohort_used": False,
    }
