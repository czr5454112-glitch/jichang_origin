#!/usr/bin/env python3
"""Summarize the G29 faithful-2x HCA* versus S4 campaign.

The reporter is deliberately read-only with respect to experiments: it only
consumes the frozen workload manifest, the two campaign aggregates, and the
per-repeat HCA metrics.  Missing evidence stays ``NOT_MEASURED``.  In
particular, the unresolved Table 5.5 ``pair_5_7`` source protocol is never
promoted by the presence of an ad-hoc run.
"""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, ROUND_HALF_UP
import io
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval import run_g4irsf26_paper_experiments as g26
from scripts.eval import run_g4irsf27_bias_experiments as g27_bias


SCHEMA = "czr005.g4irsf29.reporting.v1"
WORKLOAD_SCHEMA = "czr005.g4irsf29.workload_manifest.v1"
WORKLOAD_PROTOCOL = "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_2X"
HCA_SCHEMA = "czr005.g4irsf29.hca_campaign.v1"
NATIVE_SCHEMA = "czr005.g4irsf29.s4_aggregate.v1"
NATIVE_CASE_SCHEMA = "czr005.g4irsf29.s4_case.v1"
NATIVE_COMPLETE = "COMPLETE_G29_2X_ADMISSION"

FULL_RAW_BAGS = 57_012
FULL_SEGMENTS = 87_206
FIXED_START_EPOCH = 8_260
FIXED_WINDOW_EPOCHS = 90_000
FIXED_HORIZON = 98_259.0
EXPECTED_NATIVE_CASE_COUNT = 31
SIMULATED_HOURS = FIXED_WINDOW_EPOCHS / 3600.0
NOT_MEASURED = "NOT_MEASURED"
NOT_APPLICABLE_BASELINE_INCOMPLETE = "NOT_APPLICABLE_BASELINE_INCOMPLETE"
MEASURED = "MEASURED"
PAIR_5_7_CASE_ID = "t5_5_fault_pair_5_7"

TIME_METRICS = ("min", "mean", "p95", "p99", "max")
PAPER_TIME_METRICS = ("min", "mean", "max")
ALLOWED_TIES = {
    "PHYSICAL_RESOLUTION_TIE",
    "PAPER_PRECISION_TIE",
    "100_PERCENT_CEILING_TIE",
    "TOPOLOGY_CEILING_TIE",
}

DEFAULT_WORKLOAD = (
    ROOT / "artifacts/tasks/g4irsf29/g4irsf29_workload_manifest.json"
)
DEFAULT_HCA = ROOT / "outputs/tables/g4irsf29_hca.json"
DEFAULT_NATIVE = ROOT / "outputs/tables/g4irsf29_native.json"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf29_reporting.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf29_reporting.csv"
DEFAULT_MARKDOWN = ROOT / "outputs/reports/g4irsf29_reporting.md"

PAPER_TABLE_5_3 = {
    "min": {"dispersed": 3.56, "hca": 3.13, "improvement": 12.1},
    "mean": {"dispersed": 4.43, "hca": 3.96, "improvement": 10.6},
    "max": {"dispersed": 8.62, "hca": 5.98, "improvement": 30.6},
}


class ReportingError(RuntimeError):
    """Raised for malformed evidence, as distinct from absent evidence."""


def _path(value: Mapping[str, Any] | None, *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    result = _number(value)
    if result is None or result != int(result):
        return None
    return int(result)


def _round(value: float, quantum: str) -> Decimal:
    return Decimal(str(value)).quantize(Decimal(quantum), rounding=ROUND_HALF_UP)


def _time_verdict(observed: float | None, reference: float | None, metric: str) -> str:
    if observed is None or reference is None:
        return NOT_MEASURED
    delta = observed - reference
    # The established fresh comparison resolution is 2.1 ms.  It is only
    # admitted for the physical minimum; distribution aggregates must win.
    if metric == "min" and abs(delta) <= 0.0021 / 60.0 + 1.0e-12:
        return "PHYSICAL_RESOLUTION_TIE"
    if delta < 0.0:
        return "S4_WIN"
    if delta > 0.0:
        return "BASELINE_WIN"
    return "UNRESOLVED_TIE"


def _paper_time_verdict(observed: float | None, reference: float | None) -> str:
    if observed is None or reference is None:
        return NOT_MEASURED
    left, right = _round(observed, "0.01"), _round(reference, "0.01")
    if left < right:
        return "S4_WIN"
    if left > right:
        return "BASELINE_WIN"
    return "PAPER_PRECISION_TIE"


def _paper_improvement_verdict(observed: float | None, reference: float | None) -> str:
    if observed is None or reference is None:
        return NOT_MEASURED
    left, right = _round(observed, "0.1"), _round(reference, "0.1")
    if left > right:
        return "S4_WIN"
    if left < right:
        return "BASELINE_WIN"
    return "PAPER_PRECISION_TIE"


def _capacity_verdict(
    observed: int | None,
    reference: int | None,
    topology_upper: int | None,
) -> str:
    if observed is None or reference is None:
        return NOT_MEASURED
    if observed > reference:
        return "S4_WIN"
    if observed < reference:
        return "BASELINE_WIN"
    if observed == FULL_RAW_BAGS:
        return "100_PERCENT_CEILING_TIE"
    if topology_upper is not None and observed == topology_upper:
        return "TOPOLOGY_CEILING_TIE"
    return "UNRESOLVED_TIE"


def _rate_verdict(observed: float | None, reference: float | None) -> str:
    if observed is None or reference is None:
        return NOT_MEASURED
    if observed > reference + 1.0e-12:
        return "S4_WIN"
    if observed < reference - 1.0e-12:
        return "BASELINE_WIN"
    if math.isclose(observed, 1.0, abs_tol=1.0e-12):
        return "100_PERCENT_CEILING_TIE"
    return "UNRESOLVED_TIE"


def _verdict_counts(verdicts: Sequence[str]) -> dict[str, int]:
    measured = [
        value
        for value in verdicts
        if value not in {NOT_MEASURED, NOT_APPLICABLE_BASELINE_INCOMPLETE}
    ]
    return {
        "cell_count": len(verdicts),
        "measured_count": len(measured),
        "not_measured_count": verdicts.count(NOT_MEASURED),
        "not_applicable_baseline_incomplete_count": verdicts.count(
            NOT_APPLICABLE_BASELINE_INCOMPLETE
        ),
        "s4_win_count": measured.count("S4_WIN"),
        "allowed_tie_count": sum(value in ALLOWED_TIES for value in measured),
        "unresolved_tie_count": measured.count("UNRESOLVED_TIE"),
        "baseline_win_count": measured.count("BASELINE_WIN"),
    }


def _index(payload: Mapping[str, Any] | None, key: str) -> dict[str, Mapping[str, Any]]:
    values = payload.get(key) if isinstance(payload, Mapping) else None
    if values is None:
        return {}
    if not isinstance(values, list):
        raise ReportingError(f"{key} must be a list")
    result: dict[str, Mapping[str, Any]] = {}
    for row in values:
        if not isinstance(row, Mapping) or not isinstance(row.get("case_id"), str):
            raise ReportingError(f"{key} contains a row without case_id")
        result[str(row["case_id"])] = row
    return result


def portable_hca_metrics(
    hca: Mapping[str, Any] | None,
) -> dict[str, list[Mapping[str, Any]]]:
    """Rehydrate the small per-repeat view embedded in the HCA aggregate."""

    result: dict[str, list[Mapping[str, Any]]] = {}
    for case_id, row in _index(hca, "rows").items():
        if row.get("case_group") != "stable_speed":
            continue
        full = row.get("full_population_processed_attempt_minutes_by_repeat")
        censored = row.get(
            "secondary_censored_processed_attempt_minutes_by_repeat"
        )
        distributions = full if row.get("timing_scope") == "FULL_POPULATION" else censored
        completed = row.get("canonical_complete_raw_bag_count_by_repeat")
        walls = row.get("wall_seconds_by_repeat")
        eligible = row.get("comparison_eligible_by_repeat")
        if not all(isinstance(value, list) for value in (distributions, completed, walls, eligible)):
            result[case_id] = []
            continue
        repeat_count = _integer(row.get("repeats_complete")) or 0
        if not all(len(value) == repeat_count for value in (distributions, completed, walls, eligible)):
            result[case_id] = []
            continue
        values: list[Mapping[str, Any]] = []
        for distribution, complete, wall, comparable in zip(
            distributions, completed, walls, eligible
        ):
            if not isinstance(distribution, Mapping):
                continue
            values.append(
                {
                    "canonical_raw_bag_count": FULL_RAW_BAGS,
                    "canonical_segment_count": FULL_SEGMENTS,
                    "canonical_complete_raw_bag_count": complete,
                    "comparison_eligible": comparable,
                    "wall_seconds": wall,
                    "denominators": {
                        "processed_attempt": {
                            "count": complete,
                            "minutes": dict(distribution),
                        }
                    },
                }
            )
        result[case_id] = values
    return result


def _workload_summary(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if manifest is None:
        return {
            "measurement_status": NOT_MEASURED,
            "reason": "workload manifest is missing",
            "fixed_raw_bag_count": FULL_RAW_BAGS,
            "fixed_segment_count": FULL_SEGMENTS,
        }
    observed_raw = _integer(manifest.get("raw_task_count"))
    observed_segments = _integer(manifest.get("expanded_segment_count"))
    if (
        manifest.get("schema") != WORKLOAD_SCHEMA
        or manifest.get("status") != "COMPLETE"
        or manifest.get("protocol") != WORKLOAD_PROTOCOL
        or observed_raw != FULL_RAW_BAGS
        or observed_segments != FULL_SEGMENTS
    ):
        raise ReportingError("workload manifest is not the registered G29 2x cohort")
    return {
        "measurement_status": MEASURED,
        "protocol": manifest.get("protocol"),
        "fixed_raw_bag_count": FULL_RAW_BAGS,
        "fixed_segment_count": FULL_SEGMENTS,
        "original_flight_count": manifest.get("original_flight_count"),
        "inserted_flight_count": manifest.get("inserted_flight_count"),
        "stream_count": manifest.get("stream_count"),
        "insertion_rule": manifest.get("insertion_rule"),
    }


def _native_minutes(case: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    seconds = _path(case, "timing", "distributions", "processed_attempt")
    if not isinstance(seconds, Mapping):
        return None
    result: dict[str, float] = {}
    for metric in TIME_METRICS:
        value = _number(seconds.get(f"{metric}_seconds"))
        if value is None:
            return None
        result[metric] = value / 60.0
    return result


def _native_population_ready(
    case: Mapping[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Admit a fixed-population result without requiring a timing comparator."""

    reasons: list[str] = []
    if case is None:
        return False, ["native case is missing"]
    if case.get("schema") != NATIVE_CASE_SCHEMA or case.get("status") != NATIVE_COMPLETE:
        reasons.append("native case is not admitted complete")
    if case.get("workload_protocol") != WORKLOAD_PROTOCOL:
        reasons.append("native case does not echo the schedule-preserving 2x protocol")
    fixed_horizon = case.get("fixed_horizon")
    if not isinstance(fixed_horizon, Mapping):
        reasons.append("native case has no fixed-horizon admission evidence")
    else:
        if fixed_horizon.get("required") is not True:
            reasons.append("native case does not require the registered fixed horizon")
        if fixed_horizon.get("pass") is not True:
            reasons.append("native case does not pass the registered fixed horizon")
        for field in (
            "expected_max_simulation_time",
            "request_max_simulation_time",
            "summary_declared_max_simulation_time",
        ):
            if _number(fixed_horizon.get(field)) != FIXED_HORIZON:
                reasons.append(f"native case {field} is not 98259")
    if _integer(_path(case, "selection", "selected_raw_bag_count")) != FULL_RAW_BAGS:
        reasons.append("native case does not select 57012 raw bags")
    if _integer(_path(case, "selection", "selected_segment_count")) != FULL_SEGMENTS:
        reasons.append("native case does not select 87206 segments")
    if _path(case, "exact_release_gate", "pass") is not True:
        reasons.append("exact HCA release gate is not complete")
    if (
        _path(
            case,
            "exact_release_gate",
            "full_population_capacity_comparison_allowed",
        )
        is not True
    ):
        reasons.append("full-population capacity comparison is not allowed")
    completed = _integer(_path(case, "outcome", "completed_raw_bag_count"))
    if completed is None or not 0 <= completed <= FULL_RAW_BAGS:
        reasons.append("native fixed-population completion numerator is missing")
    return not reasons, reasons


def _native_aggregate_ready(
    native: Mapping[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Admit only the complete 31-cell, fixed-horizon native campaign."""

    reasons: list[str] = []
    if native is None:
        return False, ["native aggregate is missing"]
    if native.get("status") != "COMPLETE":
        reasons.append("native aggregate status is not COMPLETE")
    if _integer(native.get("expected_case_count")) != EXPECTED_NATIVE_CASE_COUNT:
        reasons.append("native aggregate expected_case_count is not 31")
    if _path(native, "fixed_horizon_admission", "pass") is not True:
        reasons.append("native aggregate fixed-horizon admission does not pass")
    return not reasons, reasons


def _native_full_timing_ready(
    case: Mapping[str, Any] | None,
) -> tuple[bool, list[str]]:
    """Admit S4's complete-population timing, independently of HCA completion."""

    population_ok, reasons = _native_population_ready(case)
    reasons = list(reasons)
    if not population_ok:
        return False, reasons
    if _integer(_path(case, "outcome", "completed_raw_bag_count")) != FULL_RAW_BAGS:
        reasons.append("native timing case does not complete all 57012 raw bags")
    if (
        _path(case, "timing", "status") != MEASURED
        or _integer(_path(case, "timing", "raw_bag_count")) != FULL_RAW_BAGS
        or _integer(
            _path(
                case,
                "timing",
                "distributions",
                "processed_attempt",
                "count",
            )
        )
        != FULL_RAW_BAGS
        or _native_minutes(case) is None
    ):
        reasons.append("native full-cohort timing distribution is missing")
    return not reasons, reasons


def _native_fresh_timing_pairing_allowed(case: Mapping[str, Any] | None) -> bool:
    return bool(
        _path(
            case,
            "exact_release_gate",
            "full_outcome_timing_comparison_allowed",
        )
        is True
        and _path(case, "timing", "full_outcome_timing_comparison_allowed")
        is True
    )


def _native_fault_capacity_ready(
    case: Mapping[str, Any] | None,
) -> tuple[bool, list[str]]:
    population_ok, reasons = _native_population_ready(case)
    reasons = list(reasons)
    if not population_ok:
        return False, reasons
    completed = _integer(_path(case, "outcome", "completed_raw_bag_count"))
    protected = _integer(_path(case, "timing", "fixed_population_success", "count"))
    if (
        _path(case, "timing", "status") != NOT_MEASURED
        or _path(case, "timing", "full_outcome_timing_comparison_allowed")
        is not False
        or protected is None
        or protected != completed
    ):
        reasons.append("native protected fixed-population success numerator is missing")
    return not reasons, reasons


def _hca_stable_capacity_ready(
    aggregate_row: Mapping[str, Any] | None,
) -> tuple[bool, list[str], int | None, list[int]]:
    reasons: list[str] = []
    if aggregate_row is None:
        return False, ["HCA aggregate row is missing"], None, []
    if (
        aggregate_row.get("protocol_status")
        not in {
            "EXACT_FULL_COMPLETION",
            "EXACT_RELEASE_FULL_POPULATION_FIXED_HORIZON",
        }
        or aggregate_row.get("primary_capacity_eligible") is not True
        or _integer(aggregate_row.get("repeats_complete")) != 2
        or aggregate_row.get("release_repeat_match") is not True
    ):
        reasons.append("HCA stable row is not an exact-release two-repeat fixed population")
    raw_counts = aggregate_row.get("canonical_complete_raw_bag_count_by_repeat")
    counts = (
        [_integer(value) for value in raw_counts]
        if isinstance(raw_counts, list) and len(raw_counts) == 2
        else []
    )
    if (
        len(counts) != 2
        or any(value is None or not 0 <= value <= FULL_RAW_BAGS for value in counts)
        or len(set(counts)) != 1
    ):
        reasons.append("HCA repeat completion numerators are missing or inconsistent")
    normalized = [int(value) for value in counts if value is not None]
    return not reasons, reasons, (normalized[0] if len(normalized) == 2 else None), normalized


def _hca_full_timing_ready(
    aggregate_row: Mapping[str, Any] | None,
    metrics: Sequence[Mapping[str, Any]],
) -> tuple[bool, list[str]]:
    capacity_ok, capacity_reasons, _completed, _repeats = (
        _hca_stable_capacity_ready(aggregate_row)
    )
    reasons: list[str] = list(capacity_reasons)
    if not capacity_ok and not reasons:
        reasons.append("HCA fixed-population capacity is not eligible")
    if (
        aggregate_row is None
        or aggregate_row.get("protocol_status") != "EXACT_FULL_COMPLETION"
        or aggregate_row.get("full_completion_eligible") is not True
        or aggregate_row.get("timing_scope") != "FULL_POPULATION"
    ):
        reasons.append("HCA full-population timing is not eligible")
    if len(metrics) != 2:
        reasons.append("two HCA repeat metrics are required")
    for value in metrics:
        if (
            _integer(value.get("canonical_raw_bag_count")) != FULL_RAW_BAGS
            or _integer(value.get("canonical_segment_count")) != FULL_SEGMENTS
            or _integer(value.get("canonical_complete_raw_bag_count")) != FULL_RAW_BAGS
            or value.get("comparison_eligible") is not True
            or _integer(
                _path(value, "denominators", "processed_attempt", "count")
            )
            != FULL_RAW_BAGS
            or not isinstance(_path(value, "denominators", "processed_attempt", "minutes"), Mapping)
        ):
            reasons.append("an HCA repeat lacks full-cohort processed-attempt metrics")
            break
    return not reasons, reasons


def _mean_metric(metrics: Sequence[Mapping[str, Any]], metric: str) -> tuple[float | None, list[float]]:
    values = [
        _number(_path(value, "denominators", "processed_attempt", "minutes", metric))
        for value in metrics
    ]
    present = [value for value in values if value is not None]
    return (statistics.fmean(present) if len(present) == len(metrics) and present else None, present)


def _wall_throughput(metrics: Sequence[Mapping[str, Any]]) -> float | None:
    values: list[float] = []
    for value in metrics:
        wall = _number(value.get("wall_seconds"))
        completed = _integer(value.get("canonical_complete_raw_bag_count"))
        if wall is None or wall <= 0.0 or completed is None:
            return None
        values.append(completed / wall)
    return statistics.fmean(values) if values else None


def _build_table_52(
    workload_ready: bool,
    hca_rows: Mapping[str, Mapping[str, Any]],
    native_cases: Mapping[str, Mapping[str, Any]],
    hca_metrics: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in (case for case in g26.paper_cases() if case["case_group"] == "stable_speed"):
        case_id = str(spec["case_id"])
        native = native_cases.get(case_id)
        native_capacity_ok, native_capacity_reasons = _native_population_ready(native)
        native_timing_ok, native_timing_reasons = _native_full_timing_ready(native)
        repeats = list(hca_metrics.get(case_id, ()))
        hca_row = hca_rows.get(case_id)
        (
            hca_capacity_ok,
            hca_capacity_reasons,
            hca_completed,
            hca_completed_repeats,
        ) = _hca_stable_capacity_ready(hca_row)
        hca_timing_ok, hca_timing_reasons = _hca_full_timing_ready(
            hca_row, repeats
        )
        capacity_ready = workload_ready and native_capacity_ok and hca_capacity_ok
        fresh_timing_ready = bool(
            workload_ready
            and native_timing_ok
            and hca_timing_ok
            and _native_fresh_timing_pairing_allowed(native)
        )
        s4_timing_ready = workload_ready and native_timing_ok
        native_minutes = _native_minutes(native)
        s4_completed = (
            _integer(_path(native, "outcome", "completed_raw_bag_count"))
            if capacity_ready
            else None
        )
        capacity_verdict = _capacity_verdict(s4_completed, hca_completed, None)
        baseline_incomplete_capacity_decision = bool(
            capacity_ready
            and s4_completed == FULL_RAW_BAGS
            and hca_completed is not None
            and hca_completed < FULL_RAW_BAGS
            and hca_row is not None
            and hca_row.get("protocol_status")
            == "EXACT_RELEASE_FULL_POPULATION_FIXED_HORIZON"
        )
        metrics: dict[str, Any] = {}
        timing_verdicts: list[str] = []
        for metric in TIME_METRICS:
            observed = (
                _number(native_minutes.get(metric))
                if s4_timing_ready and native_minutes
                else None
            )
            reference, repeat_values = (
                _mean_metric(repeats, metric)
                if fresh_timing_ready
                else (None, [])
            )
            censored_reference, censored_repeat_values = (
                _mean_metric(repeats, metric)
                if capacity_ready
                and hca_row is not None
                and hca_row.get("timing_scope")
                == "CENSORED_COMPLETED_SURVIVORS_SECONDARY"
                else (None, [])
            )
            verdict = (
                NOT_APPLICABLE_BASELINE_INCOMPLETE
                if baseline_incomplete_capacity_decision
                else _time_verdict(observed, reference, metric)
            )
            metrics[metric] = {
                "s4_minutes": observed,
                "fresh_hca_repeat_mean_minutes": reference,
                "fresh_hca_repeat_values_minutes": repeat_values,
                "fresh_hca_censored_survivor_repeat_mean_minutes": censored_reference,
                "fresh_hca_censored_survivor_repeat_values_minutes": censored_repeat_values,
                "hca_censored_survivor_timing_drives_verdict": False,
                "verdict": verdict,
                "formal_original_paper_metric": metric in PAPER_TIME_METRICS,
            }
            if metric in PAPER_TIME_METRICS:
                timing_verdicts.append(verdict)
        native_wall = (
            _number(_path(native, "runtime", "wall_seconds"))
            if native_capacity_ok
            else None
        )
        if baseline_incomplete_capacity_decision:
            primary_decision_status = "COMPLETE_CAPACITY_DECISION_BASELINE_INCOMPLETE"
            primary_decision_verdicts = [capacity_verdict]
        elif capacity_ready and hca_completed == FULL_RAW_BAGS:
            primary_decision_status = (
                "COMPLETE_CAPACITY_AND_TIMING_DECISION"
                if fresh_timing_ready
                else NOT_MEASURED
            )
            primary_decision_verdicts = [capacity_verdict, *timing_verdicts]
        else:
            primary_decision_status = NOT_MEASURED
            primary_decision_verdicts = [NOT_MEASURED]
        rows.append(
            {
                "case_id": case_id,
                "speed_mps": float(spec["actual_speed_mps"]),
                "measurement_status": MEASURED if capacity_ready else NOT_MEASURED,
                "capacity_measurement_status": MEASURED if capacity_ready else NOT_MEASURED,
                "fresh_timing_measurement_status": (
                    MEASURED
                    if fresh_timing_ready
                    else NOT_APPLICABLE_BASELINE_INCOMPLETE
                    if baseline_incomplete_capacity_decision
                    else NOT_MEASURED
                ),
                "s4_full_population_timing_status": MEASURED if s4_timing_ready else NOT_MEASURED,
                "primary_decision_status": primary_decision_status,
                "capacity_not_measured_reasons": (
                    []
                    if capacity_ready
                    else (["workload manifest is missing"] if not workload_ready else [])
                    + native_capacity_reasons
                    + hca_capacity_reasons
                ),
                "fresh_timing_not_measured_reasons": (
                    []
                    if fresh_timing_ready or baseline_incomplete_capacity_decision
                    else (["workload manifest is missing"] if not workload_ready else [])
                    + native_timing_reasons
                    + hca_timing_reasons
                    + (
                        ["native/HCA full-outcome timing pairing is not allowed"]
                        if native_timing_ok
                        and not _native_fresh_timing_pairing_allowed(native)
                        else []
                    )
                ),
                "fresh_timing_non_applicable_reason": (
                    "HCA released the full population but did not complete it within the fixed horizon; survivor timing is censored"
                    if baseline_incomplete_capacity_decision
                    else None
                ),
                "evidence": (
                    "EXACT_RELEASE_FIXED_POPULATION_CAPACITY"
                    if capacity_ready
                    else NOT_MEASURED
                ),
                "fixed_raw_bag_count": FULL_RAW_BAGS,
                "s4_completed_raw_bags": s4_completed,
                "fresh_hca_completed_raw_bags": hca_completed,
                "fresh_hca_completed_raw_bags_by_repeat": hca_completed_repeats,
                "s4_success_rate": (
                    s4_completed / FULL_RAW_BAGS if s4_completed is not None else None
                ),
                "fresh_hca_success_rate": (
                    hca_completed / FULL_RAW_BAGS if hca_completed is not None else None
                ),
                "capacity_verdict": capacity_verdict,
                "business_throughput_bags_per_simulated_hour": {
                    "s4": (
                        s4_completed / SIMULATED_HOURS
                        if s4_completed is not None
                        else None
                    ),
                    "fresh_hca": (
                        hca_completed / SIMULATED_HOURS
                        if hca_completed is not None
                        else None
                    ),
                    "verdict": capacity_verdict,
                },
                "hca_timing_scope": (
                    hca_row.get("timing_scope") if hca_row is not None else None
                ),
                "computational_throughput_diagnostic": {
                    "formal_metric": False,
                    "s4_raw_bags_per_wall_second": (
                        s4_completed / native_wall
                        if s4_completed is not None and native_wall and native_wall > 0.0
                        else None
                    ),
                    "hca_raw_bags_per_wall_second": (
                        _wall_throughput(repeats) if capacity_ready else None
                    ),
                    "interpretation": "implementation/runtime diagnostic, not simulated-clock baggage throughput",
                },
                "metrics": metrics,
                "formal_verdicts": primary_decision_verdicts,
                "primary_decision_verdicts": primary_decision_verdicts,
            }
        )
    verdicts = [value for row in rows for value in row["formal_verdicts"]]
    return {
        "title": "Table 5.2 — four conveyor speeds on the faithful 2x cohort",
        "rows": rows,
        "summary": _verdict_counts(verdicts),
    }


def _build_table_53(table_52: Mapping[str, Any]) -> dict[str, Any]:
    source = next(
        (row for row in table_52["rows"] if math.isclose(row["speed_mps"], 2.5)),
        None,
    )
    rows: list[dict[str, Any]] = []
    for metric in PAPER_TIME_METRICS:
        current = source["metrics"][metric] if source else {}
        observed = current.get("s4_minutes")
        paper = PAPER_TABLE_5_3[metric]
        dispersed_verdict = _paper_time_verdict(observed, paper["dispersed"])
        paper_hca_verdict = _paper_time_verdict(observed, paper["hca"])
        improvement = (
            (paper["dispersed"] - observed) / paper["dispersed"] * 100.0
            if observed is not None
            else None
        )
        rows.append(
            {
                "metric": metric,
                "measurement_status": MEASURED if observed is not None else NOT_MEASURED,
                "s4_2x_minutes": observed,
                "fresh_hca_2x_minutes": current.get("fresh_hca_repeat_mean_minutes"),
                "fresh_hca_2x_censored_survivor_minutes": current.get(
                    "fresh_hca_censored_survivor_repeat_mean_minutes"
                ),
                "fresh_hca_2x_censored_survivor_drives_verdict": False,
                "s4_vs_fresh_hca_2x": current.get("verdict", NOT_MEASURED),
                "archived_paper_1x_dispersed_minutes": paper["dispersed"],
                "archived_paper_1x_hca_minutes": paper["hca"],
                "s4_2x_vs_archived_dispersed": dispersed_verdict,
                "s4_2x_vs_archived_hca": paper_hca_verdict,
                "s4_2x_improvement_from_archived_dispersed_percent": improvement,
                "paper_reported_improvement_percent": paper["improvement"],
                "improvement_vs_paper_reported": _paper_improvement_verdict(
                    improvement, paper["improvement"]
                ),
                "archived_comparison_boundary": "DESCRIPTIVE_2X_VS_ARCHIVED_1X_AT_PAPER_PRECISION",
            }
        )
    verdicts = [
        row[key]
        for row in rows
        for key in (
            "s4_2x_vs_archived_dispersed",
            "s4_2x_vs_archived_hca",
            "improvement_vs_paper_reported",
        )
    ]
    return {
        "title": "Table 5.3 — 2.5 m/s algorithm comparison",
        "evidence_boundary": "fresh 2x HCA is controlled; paper dispersed/HCA values are archived 1x context",
        "rows": rows,
        "summary": _verdict_counts(verdicts),
    }


def _build_table_54(
    workload_ready: bool,
    native_cases: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in g27_bias.bias_cases():
        case_id = str(spec["case_id"])
        native = native_cases.get(case_id)
        ready, reasons = _native_full_timing_ready(native)
        ready = workload_ready and ready
        minutes = _native_minutes(native)
        observed = _number(minutes.get("mean")) if ready and minutes else None
        archived = spec["archived_paper_reported"]
        dynamic = float(archived["dynamic"])
        static = float(archived["static"])
        paper_improvement = float(archived["improvement"])
        improvement = (
            (static - observed) / static * 100.0 if observed is not None else None
        )
        rows.append(
            {
                "case_id": case_id,
                "standard_speed_mps": float(spec["standard_speed_mps"]),
                "deviation_percent": int(spec["deviation_percent"]),
                "measurement_status": MEASURED if ready else NOT_MEASURED,
                "not_measured_reasons": [] if ready else (["workload manifest is missing"] if not workload_ready else []) + reasons,
                "s4_2x_mean_minutes": observed,
                "archived_paper_1x_dynamic_minutes": dynamic,
                "archived_paper_1x_static_minutes": static,
                "s4_vs_archived_dynamic": _paper_time_verdict(observed, dynamic),
                "s4_vs_archived_static": _paper_time_verdict(observed, static),
                "s4_improvement_vs_archived_static_percent": improvement,
                "paper_reported_improvement_percent": paper_improvement,
                "improvement_vs_paper_reported": _paper_improvement_verdict(
                    improvement, paper_improvement
                ),
                "evidence": "OBSERVATION_BIAS_RECONSTRUCTION_DESCRIPTIVE_UNPAIRED",
                "exact_legacy_variant_recovered": False,
            }
        )
    verdicts = [
        row[key]
        for row in rows
        for key in (
            "s4_vs_archived_dynamic",
            "s4_vs_archived_static",
            "improvement_vs_paper_reported",
        )
    ]
    return {
        "title": "Table 5.4 — observation-bias reconstruction",
        "exact_legacy_variant_recovered": False,
        "comparison_boundary": "2x S4 reconstruction versus unpaired archived 1x values; not an exact legacy causal replay",
        "rows": rows,
        "summary": _verdict_counts(verdicts),
    }


def _topology_upper(case: Mapping[str, Any] | None) -> int | None:
    topology = _path(case, "outcome", "topology_reachability")
    if not isinstance(topology, Mapping):
        return None
    return _integer(topology.get("topology_reachable_raw_bag_upper_bound"))


def _build_table_55(
    workload_ready: bool,
    hca_rows: Mapping[str, Mapping[str, Any]],
    native_cases: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    specs = [case for case in g26.paper_cases() if case["case_group"] == "all_day_line_interruption"]
    rows: list[dict[str, Any]] = []
    for spec in specs:
        case_id = str(spec["case_id"])
        scenario_id = case_id.removeprefix("t5_5_fault_")
        if case_id == PAIR_5_7_CASE_ID:
            rows.append(
                {
                    "case_id": case_id,
                    "scenario_id": scenario_id,
                    "fault_line_ids": list(spec["fault_line_ids"]),
                    "affected_conveyor_count": spec["paper_reported"]["affected_conveyor_count"],
                    "measurement_status": NOT_MEASURED,
                    "s4_vs_fresh_hca": NOT_MEASURED,
                    "s4_vs_archived_paper": NOT_MEASURED,
                    "reason": "archived-only pair_5_7 source protocol remains unresolved",
                }
            )
            continue
        hca = hca_rows.get(case_id)
        native = native_cases.get(case_id)
        native_ok, native_reasons = _native_fault_capacity_ready(native)
        hca_ok = bool(
            hca
            and hca.get("protocol_status") == "FIXED_HORIZON_CAPACITY"
            and hca.get("primary_capacity_eligible") is True
            and _integer(hca.get("repeats_complete")) == 1
        )
        ready = workload_ready and native_ok and hca_ok
        hca_counts = hca.get("canonical_complete_raw_bag_count_by_repeat") if hca else None
        hca_completed = (
            _integer(hca_counts[0])
            if ready and isinstance(hca_counts, list) and len(hca_counts) == 1
            else None
        )
        s4_completed = (
            _integer(_path(native, "timing", "fixed_population_success", "count"))
            if ready
            else None
        )
        topology_upper = _topology_upper(native) if ready else None
        paper_rate = float(spec["paper_reported"]["success_rate"])
        s4_rate = s4_completed / FULL_RAW_BAGS if s4_completed is not None else None
        rows.append(
            {
                "case_id": case_id,
                "scenario_id": scenario_id,
                "fault_line_ids": list(spec["fault_line_ids"]),
                "affected_conveyor_count": spec["paper_reported"]["affected_conveyor_count"],
                "measurement_status": MEASURED if ready and hca_completed is not None else NOT_MEASURED,
                "not_measured_reasons": [] if ready and hca_completed is not None else (["workload manifest is missing"] if not workload_ready else []) + native_reasons + ([] if hca_ok else ["HCA fixed-horizon capacity row is missing or ineligible"]) + ([] if hca_completed is not None or not ready else ["HCA fixed-population numerator is missing"]),
                "fixed_denominator_raw_bags": FULL_RAW_BAGS,
                "s4_completed_raw_bags": s4_completed,
                "fresh_hca_completed_raw_bags": hca_completed,
                "topology_reachable_raw_bag_upper_bound": topology_upper,
                "s4_success_rate": s4_rate,
                "fresh_hca_success_rate": (
                    hca_completed / FULL_RAW_BAGS if hca_completed is not None else None
                ),
                "archived_paper_1x_success_rate": paper_rate,
                "s4_vs_fresh_hca": _capacity_verdict(
                    s4_completed, hca_completed, topology_upper
                ),
                "s4_vs_archived_paper": _rate_verdict(s4_rate, paper_rate),
                "comparison_boundary": "same 57012 population and fixed horizon; fault releases are not paired segment by segment",
            }
        )
    fresh = [row["s4_vs_fresh_hca"] for row in rows]
    paper = [row["s4_vs_archived_paper"] for row in rows]
    return {
        "title": "Table 5.5 — all-day line interruptions",
        "fixed_denominator_raw_bags": FULL_RAW_BAGS,
        "claim_class": "FIXED_57012_POPULATION_CAPACITY_DESCRIPTIVE_NOT_PER_SEGMENT_RELEASE_PAIRED",
        "fault_release_pairing": "NOT_PER_SEGMENT_PAIRED",
        "pair_5_7_status": NOT_MEASURED,
        "rows": rows,
        "summary": {
            "vs_fresh_hca": _verdict_counts(fresh),
            "vs_archived_paper": _verdict_counts(paper),
        },
    }


def build_report(
    workload: Mapping[str, Any] | None,
    hca: Mapping[str, Any] | None,
    native: Mapping[str, Any] | None,
    hca_metrics: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    *,
    inputs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    workload_summary = _workload_summary(workload)
    workload_ready = workload_summary["measurement_status"] == MEASURED
    if hca is not None and hca.get("schema") != HCA_SCHEMA:
        raise ReportingError("unexpected G29 HCA aggregate schema")
    if native is not None and native.get("schema") != NATIVE_SCHEMA:
        raise ReportingError("unexpected G29 native aggregate schema")
    native_aggregate_ready, native_aggregate_reasons = _native_aggregate_ready(native)
    if native is not None and not native_aggregate_ready:
        raise ReportingError(
            "native aggregate is not the complete fixed-horizon G29 campaign: "
            + "; ".join(native_aggregate_reasons)
        )
    hca_rows = _index(hca, "rows")
    native_cases = _index(native, "cases") if native_aggregate_ready else {}
    admitted_hca_metrics = (
        hca_metrics if hca_metrics is not None else portable_hca_metrics(hca)
    )
    table_52 = _build_table_52(
        workload_ready, hca_rows, native_cases, admitted_hca_metrics
    )
    table_53 = _build_table_53(table_52)
    table_54 = _build_table_54(workload_ready, native_cases)
    table_55 = _build_table_55(workload_ready, hca_rows, native_cases)

    primary = [
        verdict
        for row in table_52["rows"]
        for verdict in row["primary_decision_verdicts"]
    ] + [
        row["s4_vs_fresh_hca"]
        for row in table_55["rows"]
        if row["case_id"] != PAIR_5_7_CASE_ID
    ]
    reconstructed = [
        row[key]
        for row in table_53["rows"]
        for key in (
            "s4_2x_vs_archived_dispersed",
            "s4_2x_vs_archived_hca",
            "improvement_vs_paper_reported",
        )
    ] + [
        row[key]
        for row in table_54["rows"]
        for key in (
            "s4_vs_archived_dynamic",
            "s4_vs_archived_static",
            "improvement_vs_paper_reported",
        )
    ] + [
        row["s4_vs_archived_paper"]
        for row in table_55["rows"]
        if row["case_id"] != PAIR_5_7_CASE_ID
    ]
    primary_counts = _verdict_counts(primary)
    reconstructed_counts = _verdict_counts(reconstructed)
    context_evidence_complete = all(value != NOT_MEASURED for value in reconstructed)
    evidence_complete = all(value != NOT_MEASURED for value in primary)
    zero_losses = evidence_complete and all(
        value != "BASELINE_WIN" for value in primary
    )
    no_unresolved_ties = evidence_complete and all(
        value != "UNRESOLVED_TIE" for value in primary
    )
    target_met = evidence_complete and zero_losses and no_unresolved_ties
    status = (
        "G29_FRESH_2X_PRIMARY_TARGET_MET"
        if target_met
        else "G29_FRESH_2X_PRIMARY_TARGET_NOT_MET"
        if evidence_complete
        else "G29_FRESH_2X_PRIMARY_NOT_FULLY_MEASURED"
    )
    return {
        "schema": SCHEMA,
        "title": "G29 fresh 2× primary target report",
        "report_scope": "FRESH_2X_FIXED_HORIZON_PRIMARY_WITH_SEPARATE_DESCRIPTIVE_CONTEXT",
        "status": status,
        "workload": workload_summary,
        "protocol": {
            "inputs": dict(inputs or {}),
            "fixed_raw_bag_denominator": FULL_RAW_BAGS,
            "fixed_segment_population": FULL_SEGMENTS,
            "fixed_start_epoch": FIXED_START_EPOCH,
            "fixed_window_epochs": FIXED_WINDOW_EPOCHS,
            "fixed_last_epoch": int(FIXED_HORIZON),
            "fixed_max_simulation_time": FIXED_HORIZON,
            "native_expected_case_count": EXPECTED_NATIVE_CASE_COUNT,
            "native_aggregate_fixed_horizon_admitted": native_aggregate_ready,
            "native_aggregate_not_admitted_reasons": native_aggregate_reasons,
            "stable_and_bias_require_complete_exact_hca_release": True,
            "stable_capacity_and_timing_are_separate_axes": True,
            "fresh_timing_requires_both_full_populations_complete": True,
            "hca_survivor_timing_scope": "CENSORED_SECONDARY_NOT_A_VERDICT",
            "baseline_incomplete_speed_decision": "S4 full completion versus HCA incomplete completion is decided by fixed-population capacity; fresh timing is not applicable",
            "fault_comparison": "fixed-population business outcome, not per-segment fault-release timing pairing",
            "fault_claim_class": "FIXED_57012_POPULATION_CAPACITY_DESCRIPTIVE_NOT_PER_SEGMENT_RELEASE_PAIRED",
            "tie_policy": "only physical resolution, paper precision, 100 percent, or proven topology ceilings are admissible",
            "pair_5_7": NOT_MEASURED,
        },
        "tables": {"5.2": table_52, "5.3": table_53, "5.4": table_54, "5.5": table_55},
        "joint_decision": {
            "target_name": "G29_FRESH_2X_PRIMARY_TARGET",
            "target_scope": "fresh 2x fixed-horizon primary comparisons only",
            "target_met": target_met,
            "evidence_complete": evidence_complete,
            "zero_baseline_losses": zero_losses,
            "zero_unresolved_ties": no_unresolved_ties,
            "primary_2x_vs_fresh_hca": primary_counts,
            "archived_reconstruction_context": reconstructed_counts,
            "context_evidence_complete": context_evidence_complete,
            "context_losses": reconstructed_counts["baseline_win_count"],
            "context_drives_2x_fresh_target": False,
            "all_original_paper_subjects_exact_win_claimed": False,
            "claim_boundary": "the 2x fresh target uses Table 5.2 per-speed fixed-horizon decisions and Table 5.5 fresh fixed-population completion; all archived 1x arms and Table 5.4 are unpaired descriptive context only",
        },
        "architecture_boundary": {
            "framework": "S4/J2/E2 + local FIFO + service-aware static local potential",
            "junction_action": "one next-hop action at the current junction",
            "runtime_full_astar": False,
            "future_route_materialization": False,
            "hca_global_reservation_table": False,
            "runtime_learning": False,
        },
    }


def _csv_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add(table: str, case: str, metric: str, s4: Any, baseline: Any, unit: str, comparison: str, status: str, evidence: str, verdict: str) -> None:
        rows.append({
            "table_id": table, "case_id": case, "metric": metric,
            "s4_value": s4, "baseline_value": baseline, "unit": unit,
            "comparison": comparison, "measurement_status": status,
            "evidence": evidence, "verdict": verdict,
        })

    for row in payload["tables"]["5.2"]["rows"]:
        add(
            "5.2",
            row["case_id"],
            "completed_raw_bags",
            row["s4_completed_raw_bags"],
            row["fresh_hca_completed_raw_bags"],
            "raw_bags",
            "fresh_hca_2x_fixed_population",
            row["capacity_measurement_status"],
            row["evidence"],
            row["capacity_verdict"],
        )
        for metric in TIME_METRICS:
            value = row["metrics"][metric]
            add("5.2", row["case_id"], metric, value["s4_minutes"], value["fresh_hca_repeat_mean_minutes"], "minutes", "fresh_hca_2x_full_population_timing", row["fresh_timing_measurement_status"], row["evidence"], value["verdict"])
            if value["fresh_hca_censored_survivor_repeat_mean_minutes"] is not None:
                add("5.2", row["case_id"], metric, value["s4_minutes"], value["fresh_hca_censored_survivor_repeat_mean_minutes"], "minutes", "fresh_hca_censored_survivors_secondary", "CENSORED_SECONDARY", "does_not_drive_verdict", NOT_MEASURED)
    for row in payload["tables"]["5.3"]["rows"]:
        add("5.3", "t5_2_speed_2p5", row["metric"], row["s4_2x_minutes"], row["archived_paper_1x_dispersed_minutes"], "minutes", "archived_paper_dispersed_1x", row["measurement_status"], row["archived_comparison_boundary"], row["s4_2x_vs_archived_dispersed"])
    for row in payload["tables"]["5.4"]["rows"]:
        add("5.4", row["case_id"], "mean", row["s4_2x_mean_minutes"], row["archived_paper_1x_dynamic_minutes"], "minutes", "archived_paper_dynamic_1x", row["measurement_status"], row["evidence"], row["s4_vs_archived_dynamic"])
    for row in payload["tables"]["5.5"]["rows"]:
        add("5.5", row["case_id"], "completed_raw_bags", row.get("s4_completed_raw_bags"), row.get("fresh_hca_completed_raw_bags"), "raw_bags", "fresh_hca_2x_fixed_population", row["measurement_status"], row.get("comparison_boundary", row.get("reason", "")), row["s4_vs_fresh_hca"])
    return rows


def render_csv(payload: Mapping[str, Any]) -> str:
    fields = ("table_id", "case_id", "metric", "s4_value", "baseline_value", "unit", "comparison", "measurement_status", "evidence", "verdict")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(_csv_rows(payload))
    return stream.getvalue()


def _fmt(value: Any, digits: int = 4) -> str:
    return NOT_MEASURED if value is None else f"{float(value):.{digits}f}"


def render_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# G29 fresh 2× primary target 报告",
        "",
        f"状态：`{payload['status']}`。这是 **fresh 2× fixed-horizon primary target**，不是“原论文所有科目 exact 全胜”的声明。固定总体为 **57,012 件原始行李 / 87,206 个 segment**；缺失 primary 证据保留为 `NOT_MEASURED`。",
        "",
        f"固定窗口从 epoch **{payload['protocol']['fixed_start_epoch']:,}** 开始，共 **{payload['protocol']['fixed_window_epochs']:,} epochs**，最后有效 epoch / native `max_simulation_time` 为 **{payload['protocol']['fixed_last_epoch']:,}**；native 31 格汇总及每格 request/summary 时域回显必须通过准入。当前 native 固定时域汇总准入：`{str(payload['protocol']['native_aggregate_fixed_horizon_admitted']).lower()}`。",
        "",
        "2× 流量由原航班时刻流的中间航班加密产生，不是复制已经展开的 segment。稳定速度与偏差重构要求完整 exact HCA release；线路中断只比较同一 57,012 分母的业务完成结果，**不是逐 segment 故障 release 配对**。",
        "",
        "## Table 5.2 — 四种速度",
        "",
        "| speed | completed S4/HCA | capacity verdict | S4 min/mean/P95/P99/max | full-pop HCA min/mean/P95/P99/max | HCA censored secondary min/mean/P95/P99/max | time verdict min/mean/max | timing status |",
        "|---:|---:|---|---|---|---|---|---|",
    ]
    for row in payload["tables"]["5.2"]["rows"]:
        m = row["metrics"]
        s4 = " / ".join(_fmt(m[key]["s4_minutes"]) for key in TIME_METRICS)
        hca = " / ".join(_fmt(m[key]["fresh_hca_repeat_mean_minutes"]) for key in TIME_METRICS)
        hca_censored = " / ".join(
            _fmt(m[key]["fresh_hca_censored_survivor_repeat_mean_minutes"])
            for key in TIME_METRICS
        )
        verdict = " / ".join(m[key]["verdict"] for key in PAPER_TIME_METRICS)
        lines.append(f"| {row['speed_mps']:.1f} | {row['s4_completed_raw_bags']} / {row['fresh_hca_completed_raw_bags']} | {row['capacity_verdict']} | {s4} | {hca} | {hca_censored} | {verdict} | {row['fresh_timing_measurement_status']} |")
    lines.extend([
        "",
        "若 HCA 在固定窗口内已释放完整 57,012 件但没有全部完成，而 S4 完成 100%，该速度由容量结果形成完整主决策；fresh timing 标为 `NOT_APPLICABLE_BASELINE_INCOMPLETE`。HCA 完成幸存者分布只登记为 `CENSORED_SECONDARY`，不参与时间胜负。S4 自身完整总体 timing 仍可用于 Table 5.3/5.4 的归档上下文比较。",
        "",
        "`computational_throughput_diagnostic` 是实现/运行时诊断，不等同于模拟时钟中的业务吞吐；不进入正式胜负。",
        "",
        f"## Archived/reconstruction context（不驱动 fresh 2× primary）",
        "",
        f"Context 当前明确记录 **{payload['joint_decision']['context_losses']} 个 loss**、**{payload['joint_decision']['archived_reconstruction_context']['not_measured_count']} 个 gap/NOT_MEASURED**；这些结果不隐藏，也不冒充 fresh 2× 配对证据。",
        "",
        "## Context A — Table 5.3 archived 1× 算法比较",
        "",
        "| metric | S4 2× | fresh HCA 2× verdict | HCA censored secondary | archived dispersed 1× | archived HCA 1× | context verdicts |",
        "|---|---:|---|---:|---:|---:|---|",
    ])
    for row in payload["tables"]["5.3"]["rows"]:
        lines.append(f"| {row['metric']} | {_fmt(row['s4_2x_minutes'])} | {row['s4_vs_fresh_hca_2x']} | {_fmt(row['fresh_hca_2x_censored_survivor_minutes'])} | {row['archived_paper_1x_dispersed_minutes']:.2f} | {row['archived_paper_1x_hca_minutes']:.2f} | {row['s4_2x_vs_archived_dispersed']} / {row['s4_2x_vs_archived_hca']} / improvement {row['improvement_vs_paper_reported']} |")
    lines.extend([
        "",
        "归档分散式/HCA 数字属于 1× 论文上下文；与 2× S4 的关系按论文显示精度登记，但不是同流量因果配对。",
        "",
        "## Context B — Table 5.4 observation-bias reconstruction",
        "",
        "| case | S4 2× mean | archived dynamic/static 1× | verdict dynamic/static/improvement | status |",
        "|---|---:|---|---|---|",
    ])
    for row in payload["tables"]["5.4"]["rows"]:
        lines.append(f"| {row['case_id']} | {_fmt(row['s4_2x_mean_minutes'])} | {row['archived_paper_1x_dynamic_minutes']:.2f} / {row['archived_paper_1x_static_minutes']:.2f} | {row['s4_vs_archived_dynamic']} / {row['s4_vs_archived_static']} / {row['improvement_vs_paper_reported']} | {row['measurement_status']} |")
    lines.extend([
        "",
        "Table 5.4 是 deterministic observation-bias reconstruction；原 legacy variant、随机流和逐 case 配对未恢复，因此 `exact_legacy_variant_recovered=false`。",
        "Table 5.3、Table 5.4 及所有 archived 1× 比较仅统计为 unpaired descriptive context；其胜负不会驱动 2× fresh `target_met`。",
        "",
        "## Table 5.5 — 线路中断",
        "",
        "**醒目边界：这是固定 57,012 人口的容量描述比较，不是逐 segment release 配对，也不是逐行李 timing 因果比较。**",
        "",
        "| scenario | S4/HCA completed (of 57,012) | topology upper | S4 vs HCA | S4 vs paper rate | status |",
        "|---|---:|---:|---|---|---|",
    ])
    for row in payload["tables"]["5.5"]["rows"]:
        lines.append(f"| {row['scenario_id']} | {row.get('s4_completed_raw_bags', NOT_MEASURED)} / {row.get('fresh_hca_completed_raw_bags', NOT_MEASURED)} | {row.get('topology_reachable_raw_bag_upper_bound', NOT_MEASURED)} | {row['s4_vs_fresh_hca']} | {row['s4_vs_archived_paper']} | {row['measurement_status']} |")
    decision = payload["joint_decision"]
    lines.extend([
        "",
        "`pair_5_7` 固定为 `NOT_MEASURED`：其 archived-only 来源协议仍未解决。100%、有证据的拓扑上限、物理分辨率和论文显示精度可以平局；普通平局不算达标。",
        "",
        "## 联合判定与架构边界",
        "",
        f"target_met=`{str(decision['target_met']).lower()}`；evidence_complete=`{str(decision['evidence_complete']).lower()}`；zero_baseline_losses=`{str(decision['zero_baseline_losses']).lower()}`；zero_unresolved_ties=`{str(decision['zero_unresolved_ties']).lower()}`；context_evidence_complete=`{str(decision['context_evidence_complete']).lower()}`；context_losses=`{decision['context_losses']}`（context 不驱动 2× fresh 门）。",
        "",
        "运行时仍是 S4/J2/E2 + 节点局部 FIFO + service-aware static local potential：每个转向点只决定下一跳；不调用完整 A*，不生成未来完整路线，不使用 HCA 全局预约表，也没有启用 learning。",
        "",
    ])
    return "\n".join(lines)


def _load_optional(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ReportingError(f"JSON object required: {path}")
    return value


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-committed", action="store_true")
    parser.add_argument("--workload-manifest", type=Path, default=DEFAULT_WORKLOAD)
    parser.add_argument("--hca-aggregate", type=Path, default=DEFAULT_HCA)
    parser.add_argument("--native-aggregate", type=Path, default=DEFAULT_NATIVE)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        workload = _load_optional(args.workload_manifest)
        hca = _load_optional(args.hca_aggregate)
        native = _load_optional(args.native_aggregate)
        if args.validate_committed and any(
            value is None for value in (workload, hca, native)
        ):
            raise ReportingError(
                "committed validation requires the workload manifest and both portable aggregates"
            )
        payload = build_report(
            workload,
            hca,
            native,
            inputs={
                "workload_manifest": _relative(args.workload_manifest),
                "hca_aggregate": _relative(args.hca_aggregate),
                "native_aggregate": _relative(args.native_aggregate),
            },
        )
        texts = {
            args.json_output: json.dumps(payload, ensure_ascii=False, indent=2)
            + "\n",
            args.csv_output: render_csv(payload),
            args.markdown_output: render_markdown(payload),
        }
        if args.validate_committed:
            for path, expected in texts.items():
                if not path.is_file():
                    raise ReportingError(f"missing committed G29 report: {path}")
                if path.read_text(encoding="utf-8") != expected:
                    raise ReportingError(f"committed G29 report is stale: {path}")
            print("G29 committed portable reporting validation: PASS")
            return 0
        for path, text in texts.items():
            _write(path, text)
    except (ReportingError, OSError, json.JSONDecodeError) as exc:
        print(f"G29 reporting failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"status": payload["status"], "json": _relative(args.json_output), "csv": _relative(args.csv_output), "markdown": _relative(args.markdown_output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
