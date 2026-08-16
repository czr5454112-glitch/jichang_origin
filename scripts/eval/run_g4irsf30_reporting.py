#!/usr/bin/env python3
"""Report the G30 3x fixed-window HCA* versus S4 campaign.

The fresh primary claim is deliberately narrow: four speed-capacity cells and
fifteen measurable interruption-capacity cells on the fixed 85,518-bag
population.  Own-source fixed-window capacity is not release- or timing-paired.
Table 5.3 and the twelve Table 5.4 reconstruction cells remain descriptive
archived context.  Partial inputs produce diagnostics and never predeclare a
win; committed validation rebuilds from the workload and two portable
aggregates only.
"""

from __future__ import annotations

import argparse
import csv
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
from scripts.eval import run_g4irsf29_reporting as g29
from scripts.eval import run_g4irsf30_native as g30_native


SCHEMA = "czr005.g4irsf30.reporting.v1"
WORKLOAD_SCHEMA = "czr005.g4irsf30.workload_manifest.v1"
WORKLOAD_PROTOCOL = "SCHEDULE_PRESERVING_INTERMEDIATE_FLIGHT_DENSIFICATION_3X"
HCA_SCHEMA = "czr005.g4irsf30.hca_campaign.v1"
NATIVE_SCHEMA = "czr005.g4irsf30.s4_aggregate.v1"
NATIVE_CASE_SCHEMA = "czr005.g4irsf30.s4_case.v1"

FULL_RAW_BAGS = 85_518
FULL_SEGMENTS = 130_809
FIXED_START_EPOCH = 8_260
FIXED_WINDOW_EPOCHS = 90_000
FIXED_HORIZON = 98_259.0
G30_MAX_EVENTS = 60_000_000
EXPECTED_NATIVE_CASE_COUNT = 31
PAIR_5_7_CASE_ID = "t5_5_fault_pair_5_7"
NATIVE_FIXED_HORIZON_CAPACITY = "COMPLETE_G30_3X_FIXED_HORIZON_CAPACITY"
OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE = (
    "OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE"
)

MEASURED = "MEASURED"
NOT_MEASURED = "NOT_MEASURED"
NOT_APPLICABLE_BASELINE_INCOMPLETE = "NOT_APPLICABLE_BASELINE_INCOMPLETE"
TIME_METRICS = g29.TIME_METRICS
PAPER_TIME_METRICS = g29.PAPER_TIME_METRICS
PAPER_TABLE_5_3 = g29.PAPER_TABLE_5_3
ALLOWED_TIES = {
    "100_PERCENT_CEILING_TIE",
    "TOPOLOGY_CEILING_TIE",
    "PAPER_PRECISION_TIE",
    "PHYSICAL_RESOLUTION_TIE",
}

DEFAULT_WORKLOAD = ROOT / "artifacts/tasks/g4irsf30/g4irsf30_workload_manifest.json"
DEFAULT_HCA = ROOT / "outputs/tables/g4irsf30_hca.json"
DEFAULT_NATIVE = ROOT / "outputs/tables/g4irsf30_native.json"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf30_reporting.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf30_reporting.csv"
DEFAULT_MARKDOWN = ROOT / "outputs/reports/g4irsf30_reporting.md"


class Reporting30Error(RuntimeError):
    """Raised for malformed evidence; absent or partial evidence stays diagnostic."""


def _path(value: Mapping[str, Any] | None, *keys: str) -> Any:
    return g29._path(value, *keys)


def _number(value: Any) -> float | None:
    return g29._number(value)


def _integer(value: Any) -> int | None:
    return g29._integer(value)


def _index(payload: Mapping[str, Any] | None, key: str) -> dict[str, Mapping[str, Any]]:
    try:
        return g29._index(payload, key)
    except g29.ReportingError as exc:
        raise Reporting30Error(str(exc)) from exc


def _hca_aggregate_complete(payload: Mapping[str, Any] | None) -> bool:
    return bool(
        payload
        and payload.get("status") == "COMPLETE_WITH_ARCHIVED_ONLY_GAP"
        and _integer(payload.get("primary_complete_case_count")) == 19
        and payload.get("missing_primary_case_ids") == []
        and payload.get("invalid_primary_case_ids") == []
    )


def _native_admitted_case_ids(payload: Mapping[str, Any] | None) -> set[str]:
    if payload is None:
        return set()
    complete = payload.get("complete_case_ids")
    horizon = _path(payload, "fixed_horizon_admission", "admitted_case_ids")
    events = _path(payload, "event_budget_admission", "admitted_case_ids")
    if not all(isinstance(value, list) for value in (complete, horizon, events)):
        return set()
    return (
        {str(value) for value in complete}
        & {str(value) for value in horizon}
        & {str(value) for value in events}
    )


def _native_aggregate_complete(payload: Mapping[str, Any] | None) -> bool:
    cases = payload.get("cases") if payload else None
    complete = payload.get("complete_case_ids") if payload else None
    horizon_ids = (
        _path(payload, "fixed_horizon_admission", "admitted_case_ids")
        if payload
        else None
    )
    event_ids = (
        _path(payload, "event_budget_admission", "admitted_case_ids")
        if payload
        else None
    )
    case_ids = (
        {
            str(value.get("case_id"))
            for value in cases
            if isinstance(value, Mapping) and value.get("case_id") is not None
        }
        if isinstance(cases, list)
        else set()
    )
    expected_ids = set(g30_native.CASE_IDS)
    return bool(
        payload
        and payload.get("status") == "COMPLETE"
        and payload.get("workload_protocol") == WORKLOAD_PROTOCOL
        and _integer(_path(payload, "fixed_population", "raw_bag_count"))
        == FULL_RAW_BAGS
        and _integer(_path(payload, "fixed_population", "segment_count"))
        == FULL_SEGMENTS
        and _integer(payload.get("expected_case_count"))
        == EXPECTED_NATIVE_CASE_COUNT
        and _integer(payload.get("observed_case_count"))
        == EXPECTED_NATIVE_CASE_COUNT
        and _number(
            _path(
                payload,
                "fixed_horizon_admission",
                "expected_max_simulation_time",
            )
        )
        == FIXED_HORIZON
        and _path(payload, "fixed_horizon_admission", "pass") is True
        and _integer(
            _path(payload, "event_budget_admission", "expected_max_events")
        )
        == G30_MAX_EVENTS
        and _path(payload, "event_budget_admission", "pass") is True
        and all(
            isinstance(values, list)
            and len(values) == EXPECTED_NATIVE_CASE_COUNT
            and len({str(value) for value in values})
            == EXPECTED_NATIVE_CASE_COUNT
            and {str(value) for value in values} == expected_ids
            for values in (complete, horizon_ids, event_ids)
        )
        and _native_admitted_case_ids(payload) == expected_ids
        and isinstance(cases, list)
        and len(cases) == EXPECTED_NATIVE_CASE_COUNT
        and case_ids == expected_ids
        and payload.get("blocked_release_case_ids", []) == []
        and payload.get("failed_case_ids", []) == []
        and payload.get("stale_admission_case_ids", []) == []
        and payload.get("missing_case_ids", []) == []
    )


def _three_x_count_map_ready(value: Any, total: int) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    counts = [_integer(count) for count in value.values()]
    return bool(
        all(count is not None and count >= 0 and count % 3 == 0 for count in counts)
        and sum(int(count) for count in counts if count is not None) == total
    )


def _workload_summary(manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    if manifest is None:
        return {
            "measurement_status": NOT_MEASURED,
            "reason": "G30 workload manifest is missing",
            "fixed_raw_bag_count": FULL_RAW_BAGS,
            "fixed_segment_count": FULL_SEGMENTS,
        }
    invariants = manifest.get("invariants")
    required_invariants = {
        "canonical_was_expanded_from_generated_raw",
        "categorical_manifest_is_copied_per_inserted_flight",
        "direct_count_is_exactly_3x",
        "early_split_count_is_exactly_3x",
        "end_counts_are_exactly_3x",
        "expanded_segment_count_is_exactly_3x",
        "flight_count_is_exactly_3x",
        "loader_counts_are_exactly_3x",
        "raw_task_count_is_exactly_3x",
        "same_24h_axis_no_time_compression",
        "slack_and_storage_class_are_preserved",
        "start_counts_are_exactly_3x",
        "unloader_counts_are_exactly_3x",
    }
    insertion = manifest.get("insertion_rule")
    lifecycle = manifest.get("lifecycle")
    timing = manifest.get("timing")
    direct = _integer(manifest.get("direct_raw_task_count"))
    early = _integer(manifest.get("early_split_raw_task_count"))
    if (
        manifest.get("schema") != WORKLOAD_SCHEMA
        or manifest.get("status") != "COMPLETE"
        or manifest.get("protocol") != WORKLOAD_PROTOCOL
        or _integer(manifest.get("scale")) != 3
        or _integer(manifest.get("input_raw_task_count")) != 28_506
        or _integer(manifest.get("input_expanded_segment_count")) != 43_603
        or _integer(manifest.get("input_flight_count")) != 360
        or _integer(manifest.get("raw_task_count")) != FULL_RAW_BAGS
        or _integer(manifest.get("expanded_segment_count")) != FULL_SEGMENTS
        or _integer(manifest.get("flight_count")) != 1_080
        or _integer(manifest.get("original_flight_count")) != 360
        or _integer(manifest.get("inserted_flight_count")) != 720
        or _integer(manifest.get("inserted_flights_per_original")) != 2
        or manifest.get("inserted_id_offsets") != [28_506, 57_012]
        or _integer(manifest.get("stream_count")) != 13
        or manifest.get("flight_key") != ["STD", "end", "Unloader"]
        or manifest.get("stream_key") != ["end", "Unloader"]
        or direct is None
        or early is None
        or direct + early != FULL_RAW_BAGS
        or direct % 3 != 0
        or early % 3 != 0
        or not _three_x_count_map_ready(manifest.get("raw_by_end"), FULL_RAW_BAGS)
        or not _three_x_count_map_ready(manifest.get("raw_by_loader"), FULL_RAW_BAGS)
        or not _three_x_count_map_ready(manifest.get("raw_by_start"), FULL_RAW_BAGS)
        or not _three_x_count_map_ready(manifest.get("raw_by_unloader"), FULL_RAW_BAGS)
        or not _three_x_count_map_ready(
            manifest.get("expanded_by_start"), FULL_SEGMENTS
        )
        or not isinstance(invariants, Mapping)
        or set(invariants) != required_invariants
        or any(invariants.get(key) is not True for key in required_invariants)
        or not isinstance(insertion, Mapping)
        or insertion.get("manifest_shift")
        != "EntryTime_and_STD_receive_the_same_delta"
        or insertion.get("nonterminal")
        != "one_third_and_two_thirds_to_next_STD_in_same_stream"
        or insertion.get("terminal")
        != "lower_median_positive_stream_headway_times_one_third_and_two_thirds"
        or not isinstance(lifecycle, Mapping)
        or lifecycle.get("bag_id_rule")
        != (
            "original task_id retained; inserted cohort 1/2 uses its "
            "registered ID offset plus source row rank"
        )
        or _number(lifecycle.get("early_bag_threshold_seconds")) != 4_800.0
        or lifecycle.get("segment_id_rule")
        != "<task_id>:direct|storage_in|storage_out"
        or _integer(lifecycle.get("storage_in_goal")) != 47
        or _number(lifecycle.get("storage_out_lead_seconds")) != 2_700.0
        or _integer(lifecycle.get("storage_out_start")) != 52
        or not isinstance(timing, Mapping)
        or _number(timing.get("time_compression")) != 1.0
        or _integer(timing.get("rolling_days")) != 1
        or _number(timing.get("day_axis_seconds")) != 86_400.0
        or any(
            value is None or not 0.0 <= value < 86_400.0
            for value in (
                _number(timing.get("earliest_entry_time")),
                _number(timing.get("latest_entry_time")),
                _number(timing.get("earliest_std")),
                _number(timing.get("latest_std")),
            )
        )
    ):
        raise Reporting30Error("workload manifest is not the registered G30 3x cohort")
    return {
        "measurement_status": MEASURED,
        "protocol": WORKLOAD_PROTOCOL,
        "fixed_raw_bag_count": FULL_RAW_BAGS,
        "fixed_segment_count": FULL_SEGMENTS,
        "flight_count": 1_080,
        "inserted_flight_count": manifest.get("inserted_flight_count"),
        "insertion_rule": manifest.get("insertion_rule"),
    }


def _distribution_mean(
    distributions: Any, metric: str
) -> tuple[float | None, list[float]]:
    if not isinstance(distributions, list) or not distributions:
        return None, []
    values = [
        _number(value.get(metric)) if isinstance(value, Mapping) else None
        for value in distributions
    ]
    if any(value is None for value in values):
        return None, []
    present = [float(value) for value in values if value is not None]
    return statistics.fmean(present), present


def _hca_capacity_ready(
    row: Mapping[str, Any] | None, *, repeats: int
) -> tuple[bool, list[str], int | None, list[int]]:
    reasons: list[str] = []
    if row is None:
        return False, ["HCA aggregate row is missing"], None, []
    if (
        row.get("primary_capacity_eligible") is not True
        or row.get("protocol_status")
        not in {"FIXED_HORIZON_END_TO_END_CAPACITY", "EXACT_FULL_COMPLETION"}
        or row.get("fixed_horizon_pass") is not True
        or row.get("cohort_pass") is not True
        or _integer(row.get("repeats_complete")) != repeats
    ):
        reasons.append("HCA row is not admitted fixed-window capacity evidence")
    if repeats == 2 and row.get("counts_consistent_across_repeats") is not True:
        reasons.append("HCA stable repeat counts are not consistent")
    counts = row.get("canonical_complete_raw_bag_count_by_repeat")
    normalized = (
        [_integer(value) for value in counts]
        if isinstance(counts, list) and len(counts) == repeats
        else []
    )
    if (
        len(normalized) != repeats
        or any(value is None or not 0 <= value <= FULL_RAW_BAGS for value in normalized)
        or len(set(normalized)) != 1
    ):
        reasons.append("HCA fixed-population completion counts are missing or inconsistent")
    present = [int(value) for value in normalized if value is not None]
    return not reasons, reasons, (present[0] if len(present) == repeats else None), present


def _hca_full_timing_ready(row: Mapping[str, Any] | None) -> bool:
    return bool(
        row
        and row.get("full_completion_eligible") is True
        and row.get("formal_timing_comparison_allowed") is True
        and row.get("timing_scope") == "FULL_POPULATION"
        and isinstance(
            row.get("full_population_processed_attempt_minutes_by_repeat"), list
        )
        and len(row["full_population_processed_attempt_minutes_by_repeat"]) == 2
    )


def _native_capacity_ready(
    case: Mapping[str, Any] | None,
) -> tuple[bool, list[str], int | None]:
    reasons: list[str] = []
    if case is None:
        return False, ["native case is missing"], None
    if (
        case.get("schema") != NATIVE_CASE_SCHEMA
        or case.get("status")
        not in {*g30_native.COMPLETE_STATUSES, NATIVE_FIXED_HORIZON_CAPACITY}
    ):
        reasons.append("native case is not admitted complete")
    if case.get("workload_protocol") != WORKLOAD_PROTOCOL:
        reasons.append("native case does not echo the G30 3x protocol")
    if (
        _integer(_path(case, "selection", "selected_raw_bag_count"))
        != FULL_RAW_BAGS
        or _integer(_path(case, "selection", "selected_segment_count"))
        != FULL_SEGMENTS
    ):
        reasons.append("native case does not select the fixed 3x population")
    horizon = case.get("fixed_horizon")
    if not isinstance(horizon, Mapping) or any(
        (
            horizon.get("required") is not True,
            horizon.get("pass") is not True,
            _number(horizon.get("expected_max_simulation_time")) != FIXED_HORIZON,
            _number(horizon.get("request_max_simulation_time")) != FIXED_HORIZON,
            _number(horizon.get("summary_declared_max_simulation_time"))
            != FIXED_HORIZON,
        )
    ):
        reasons.append("native fixed-horizon admission is incomplete")
    if (
        _path(case, "exact_release_gate", "pass") is not True
        or _path(
            case,
            "exact_release_gate",
            "full_population_capacity_comparison_allowed",
        )
        is not True
    ):
        reasons.append("native fixed-population capacity comparison is not allowed")
    if _path(case, "safety", "pass") is not True:
        reasons.append("native structural safety admission is not passed")
    if (
        _path(case, "event_budget", "required") is not True
        or _integer(_path(case, "event_budget", "expected_max_events"))
        != G30_MAX_EVENTS
        or _integer(_path(case, "event_budget", "request_max_events"))
        != G30_MAX_EVENTS
        or _integer(
            _path(case, "event_budget", "summary_declared_max_events")
        )
        != G30_MAX_EVENTS
        or _path(case, "event_budget", "summary_event_limit_reached") is not False
        or _path(case, "event_budget", "pass") is not True
    ):
        reasons.append("native 60M event-budget admission is incomplete")
    if not g30_native._artifact_admitted(case):
        reasons.append("native artifact does not pass the authoritative admission")
    completed = _integer(_path(case, "outcome", "completed_raw_bag_count"))
    if completed is None or not 0 <= completed <= FULL_RAW_BAGS:
        reasons.append("native completion numerator is missing")
    return not reasons, reasons, completed


def _native_minutes(case: Mapping[str, Any] | None) -> Mapping[str, float] | None:
    seconds = _path(case, "timing", "distributions", "processed_attempt")
    if not isinstance(seconds, Mapping):
        return None
    values: dict[str, float] = {}
    for metric in TIME_METRICS:
        value = _number(seconds.get(f"{metric}_seconds"))
        if value is None:
            return None
        values[metric] = value / 60.0
    return values


def _native_full_timing_ready(case: Mapping[str, Any] | None) -> bool:
    capacity, _reasons, completed = _native_capacity_ready(case)
    return bool(
        capacity
        and completed == FULL_RAW_BAGS
        and _path(case, "timing", "status") == MEASURED
        and _path(case, "timing", "full_outcome_timing_comparison_allowed")
        is True
        and _path(
            case,
            "exact_release_gate",
            "full_outcome_timing_comparison_allowed",
        )
        is True
        and _integer(_path(case, "timing", "raw_bag_count")) == FULL_RAW_BAGS
        and _native_minutes(case) is not None
    )


def _native_context_timing_status(case: Mapping[str, Any] | None) -> str:
    capacity, _reasons, completed = _native_capacity_ready(case)
    status = _path(case, "timing", "status")
    if not (
        capacity
        and completed == FULL_RAW_BAGS
        and status in {MEASURED, OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE}
        and _integer(_path(case, "timing", "raw_bag_count")) == FULL_RAW_BAGS
        and _path(case, "timing", "population")
        == "all_selected_raw_bags_complete"
        and _native_minutes(case) is not None
    ):
        return NOT_MEASURED
    if status == OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE:
        if (
            _path(case, "case_group") not in {"stable_speed", "observation_bias"}
            or _path(
                case,
                "exact_release_gate",
                "full_outcome_timing_comparison_allowed",
            )
            is not False
            or _path(case, "timing", "full_outcome_timing_comparison_allowed")
            is not False
            or _path(case, "timing", "fresh_hca_timing_verdict_allowed")
            is not False
        ):
            return NOT_MEASURED
    return str(status)


def _native_context_minutes(
    case: Mapping[str, Any] | None,
) -> Mapping[str, float] | None:
    return (
        _native_minutes(case)
        if _native_context_timing_status(case) != NOT_MEASURED
        else None
    )


def _capacity_verdict(
    observed: int | None, reference: int | None, topology_upper: int | None = None
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
    return "100_PERCENT_CEILING_TIE" if math.isclose(observed, 1.0) else "UNRESOLVED_TIE"


def _verdict_counts(values: Sequence[str]) -> dict[str, int]:
    measured = [
        value
        for value in values
        if value not in {NOT_MEASURED, NOT_APPLICABLE_BASELINE_INCOMPLETE}
    ]
    return {
        "cell_count": len(values),
        "measured_count": len(measured),
        "not_measured_count": values.count(NOT_MEASURED),
        "not_applicable_baseline_incomplete_count": values.count(
            NOT_APPLICABLE_BASELINE_INCOMPLETE
        ),
        "s4_win_count": measured.count("S4_WIN"),
        "allowed_tie_count": sum(value in ALLOWED_TIES for value in measured),
        "unresolved_tie_count": measured.count("UNRESOLVED_TIE"),
        "baseline_win_count": measured.count("BASELINE_WIN"),
    }


def _build_table_52(
    workload_ready: bool,
    hca_rows: Mapping[str, Mapping[str, Any]],
    native_cases: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in (
        case for case in g26.paper_cases() if case["case_group"] == "stable_speed"
    ):
        case_id = str(spec["case_id"])
        hca = hca_rows.get(case_id)
        native = native_cases.get(case_id)
        hca_ok, hca_reasons, hca_completed, hca_counts = _hca_capacity_ready(
            hca, repeats=2
        )
        native_ok, native_reasons, s4_completed = _native_capacity_ready(native)
        ready = workload_ready and hca_ok and native_ok
        if not ready:
            hca_completed = None
            s4_completed = None
        verdict = _capacity_verdict(s4_completed, hca_completed)

        s4_timing = _native_minutes(native) if _native_full_timing_ready(native) else None
        hca_full = (
            hca.get("full_population_processed_attempt_minutes_by_repeat")
            if _hca_full_timing_ready(hca)
            else None
        )
        hca_secondary = (
            hca.get("secondary_censored_processed_attempt_minutes_by_repeat")
            if hca and hca.get("secondary_timing_censored") is True
            else None
        )
        timing_ready = bool(s4_timing is not None and hca_full is not None)
        hca_incomplete = bool(hca_ok and hca and hca.get("full_completion_eligible") is not True)
        metrics: dict[str, Any] = {}
        for metric in TIME_METRICS:
            full_mean, full_values = _distribution_mean(hca_full, metric)
            secondary_mean, secondary_values = _distribution_mean(
                hca_secondary, metric
            )
            observed = _number(s4_timing.get(metric)) if s4_timing else None
            metrics[metric] = {
                "s4_minutes": observed,
                "fresh_hca_full_population_repeat_mean_minutes": full_mean,
                "fresh_hca_full_population_repeat_values_minutes": full_values,
                "fresh_hca_censored_survivor_repeat_mean_minutes": secondary_mean,
                "fresh_hca_censored_survivor_repeat_values_minutes": secondary_values,
                "hca_censored_survivor_timing_drives_verdict": False,
                "timing_verdict": (
                    g29._time_verdict(observed, full_mean, metric)
                    if timing_ready
                    else NOT_APPLICABLE_BASELINE_INCOMPLETE
                    if hca_incomplete
                    else NOT_MEASURED
                ),
            }
        rows.append(
            {
                "case_id": case_id,
                "speed_mps": float(spec["actual_speed_mps"]),
                "measurement_status": MEASURED if ready else NOT_MEASURED,
                "fixed_raw_bag_denominator": FULL_RAW_BAGS,
                "s4_completed_raw_bags": s4_completed,
                "fresh_hca_completed_raw_bags": hca_completed,
                "fresh_hca_completed_raw_bags_by_repeat": hca_counts,
                "capacity_verdict": verdict,
                "s4_case_status": native.get("status") if native else NOT_MEASURED,
                "s4_full_population_completed": (
                    s4_completed == FULL_RAW_BAGS if s4_completed is not None else None
                ),
                "fresh_hca_full_population_completed": (
                    hca_completed == FULL_RAW_BAGS
                    if hca_completed is not None
                    else None
                ),
                "incomplete_fixed_horizon_is_business_outcome": True,
                "incomplete_fixed_horizon_is_runtime_or_safety_failure": False,
                "capacity_not_measured_reasons": (
                    []
                    if ready
                    else (["workload manifest is missing"] if not workload_ready else [])
                    + hca_reasons
                    + native_reasons
                ),
                "comparison_protocol": "OWN_SOURCE_FIXED_HORIZON_CAPACITY_NOT_RELEASE_PAIRED",
                "full_release_required_for_capacity": False,
                "fresh_timing_status": (
                    MEASURED
                    if timing_ready
                    else NOT_APPLICABLE_BASELINE_INCOMPLETE
                    if hca_incomplete
                    else NOT_MEASURED
                ),
                "fresh_timing_drives_3x_primary": False,
                "own_source_descriptive_timing_drives_fresh_timing": False,
                "metrics": metrics,
            }
        )
    verdicts = [row["capacity_verdict"] for row in rows]
    return {
        "title": "Table 5.2 — G30 3x own-source fixed-window capacity",
        "rows": rows,
        "summary": _verdict_counts(verdicts),
    }


def _build_table_53(
    table_52: Mapping[str, Any],
    native_cases: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    source = next(
        (row for row in table_52["rows"] if math.isclose(row["speed_mps"], 2.5)),
        None,
    )
    native = native_cases.get("t5_2_speed_2p5")
    context_timing = _native_context_minutes(native)
    context_status = _native_context_timing_status(native)
    rows: list[dict[str, Any]] = []
    for metric in PAPER_TIME_METRICS:
        observed = (
            _number(context_timing.get(metric)) if context_timing else None
        )
        paper = PAPER_TABLE_5_3[metric]
        improvement = (
            (paper["dispersed"] - observed) / paper["dispersed"] * 100.0
            if observed is not None
            else None
        )
        rows.append(
            {
                "metric": metric,
                "measurement_status": (
                    context_status if observed is not None else NOT_MEASURED
                ),
                "timing_evidence_class": context_status,
                "s4_3x_minutes": observed,
                "fresh_hca_3x_timing_status": (
                    source["fresh_timing_status"] if source else NOT_MEASURED
                ),
                "archived_paper_1x_dispersed_minutes": paper["dispersed"],
                "archived_paper_1x_hca_minutes": paper["hca"],
                "s4_vs_archived_dispersed": g29._paper_time_verdict(
                    observed, paper["dispersed"]
                ),
                "s4_vs_archived_hca": g29._paper_time_verdict(
                    observed, paper["hca"]
                ),
                "s4_3x_improvement_from_archived_dispersed_percent": improvement,
                "paper_reported_improvement_percent": paper["improvement"],
                "improvement_vs_paper_reported": g29._paper_improvement_verdict(
                    improvement, paper["improvement"]
                ),
                "comparison_boundary": "DESCRIPTIVE_3X_VS_ARCHIVED_1X_NOT_PRIMARY",
                "drives_fresh_3x_timing": False,
            }
        )
    verdicts = [
        row[key]
        for row in rows
        for key in (
            "s4_vs_archived_dispersed",
            "s4_vs_archived_hca",
            "improvement_vs_paper_reported",
        )
    ]
    return {
        "title": "Table 5.3 — archived 1x context",
        "rows": rows,
        "summary": _verdict_counts(verdicts),
        "drives_3x_primary": False,
    }


def _build_table_54(
    workload_ready: bool,
    native_cases: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for spec in g27_bias.bias_cases():
        case_id = str(spec["case_id"])
        native = native_cases.get(case_id)
        capacity_ok, reasons, completed = _native_capacity_ready(native)
        capacity_ok = workload_ready and capacity_ok
        if not capacity_ok:
            completed = None
        timing = _native_context_minutes(native)
        context_status = _native_context_timing_status(native)
        observed = _number(timing.get("mean")) if timing else None
        archived = spec["archived_paper_reported"]
        dynamic = float(archived["dynamic"])
        static = float(archived["static"])
        improvement = (static - observed) / static * 100.0 if observed is not None else None
        rows.append(
            {
                "case_id": case_id,
                "standard_speed_mps": float(spec["standard_speed_mps"]),
                "deviation_percent": int(spec["deviation_percent"]),
                "capacity_measurement_status": MEASURED if capacity_ok else NOT_MEASURED,
                "fixed_raw_bag_denominator": FULL_RAW_BAGS,
                "s4_completed_raw_bags": completed,
                "capacity_not_measured_reasons": (
                    []
                    if capacity_ok
                    else (["workload manifest is missing"] if not workload_ready else [])
                    + reasons
                ),
                "timing_measurement_status": (
                    context_status if observed is not None else NOT_MEASURED
                ),
                "timing_evidence_class": context_status,
                "s4_3x_mean_minutes": observed,
                "archived_paper_1x_dynamic_minutes": dynamic,
                "archived_paper_1x_static_minutes": static,
                "s4_vs_archived_dynamic": g29._paper_time_verdict(observed, dynamic),
                "s4_vs_archived_static": g29._paper_time_verdict(observed, static),
                "s4_improvement_vs_archived_static_percent": improvement,
                "paper_reported_improvement_percent": float(archived["improvement"]),
                "improvement_vs_paper_reported": g29._paper_improvement_verdict(
                    improvement, float(archived["improvement"])
                ),
                "evidence": "DESCRIPTIVE_UNPAIRED_LEGACY_VARIANT_RECONSTRUCTION",
                "exact_legacy_variant_recovered": False,
                "drives_3x_primary": False,
                "drives_fresh_3x_timing": False,
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
        "title": "Table 5.4 — G30 observation-bias reconstruction context",
        "rows": rows,
        "summary": _verdict_counts(verdicts),
        "exact_legacy_variant_recovered": False,
        "drives_3x_primary": False,
    }


def _topology_upper(case: Mapping[str, Any] | None) -> int | None:
    return _integer(
        _path(
            case,
            "outcome",
            "topology_reachability",
            "topology_reachable_raw_bag_upper_bound",
        )
    )


def _build_table_55(
    workload_ready: bool,
    hca_rows: Mapping[str, Mapping[str, Any]],
    native_cases: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    specs = [
        case
        for case in g26.paper_cases()
        if case["case_group"] == "all_day_line_interruption"
    ]
    for spec in specs:
        case_id = str(spec["case_id"])
        scenario = case_id.removeprefix("t5_5_fault_")
        if case_id == PAIR_5_7_CASE_ID:
            rows.append(
                {
                    "case_id": case_id,
                    "scenario_id": scenario,
                    "measurement_status": NOT_MEASURED,
                    "s4_vs_fresh_hca": NOT_MEASURED,
                    "s4_vs_archived_paper": NOT_MEASURED,
                    "reason": "archived pair_5_7 source protocol remains unresolved",
                }
            )
            continue
        hca = hca_rows.get(case_id)
        native = native_cases.get(case_id)
        hca_ok, hca_reasons, hca_completed, _counts = _hca_capacity_ready(
            hca, repeats=1
        )
        native_ok, native_reasons, s4_completed = _native_capacity_ready(native)
        ready = workload_ready and hca_ok and native_ok
        if not ready:
            hca_completed = None
            s4_completed = None
        topology = _topology_upper(native) if ready else None
        verdict = _capacity_verdict(s4_completed, hca_completed, topology)
        s4_rate = s4_completed / FULL_RAW_BAGS if s4_completed is not None else None
        paper_rate = float(spec["paper_reported"]["success_rate"])
        rows.append(
            {
                "case_id": case_id,
                "scenario_id": scenario,
                "fault_line_ids": list(spec["fault_line_ids"]),
                "measurement_status": MEASURED if ready else NOT_MEASURED,
                "not_measured_reasons": (
                    []
                    if ready
                    else (["workload manifest is missing"] if not workload_ready else [])
                    + hca_reasons
                    + native_reasons
                ),
                "fixed_raw_bag_denominator": FULL_RAW_BAGS,
                "s4_completed_raw_bags": s4_completed,
                "fresh_hca_completed_raw_bags": hca_completed,
                "topology_reachable_raw_bag_upper_bound": topology,
                "s4_success_rate": s4_rate,
                "fresh_hca_success_rate": (
                    hca_completed / FULL_RAW_BAGS if hca_completed is not None else None
                ),
                "paper_success_rate": paper_rate,
                "s4_vs_fresh_hca": verdict,
                "s4_vs_archived_paper": _rate_verdict(s4_rate, paper_rate),
                "s4_case_status": native.get("status") if native else NOT_MEASURED,
                "s4_full_population_completed": (
                    s4_completed == FULL_RAW_BAGS if s4_completed is not None else None
                ),
                "fresh_hca_full_population_completed": (
                    hca_completed == FULL_RAW_BAGS
                    if hca_completed is not None
                    else None
                ),
                "incomplete_fixed_horizon_is_business_outcome": True,
                "incomplete_fixed_horizon_is_runtime_or_safety_failure": False,
                "survivor_timing_claim_allowed": False,
                "comparison_boundary": "FIXED_85518_POPULATION_CAPACITY_NOT_PER_SEGMENT_RELEASE_PAIRED",
            }
        )
    return {
        "title": "Table 5.5 — G30 fixed-population interruptions",
        "fixed_denominator_raw_bags": FULL_RAW_BAGS,
        "pair_5_7_status": NOT_MEASURED,
        "fault_release_pairing": "NOT_PER_SEGMENT_PAIRED",
        "claim_class": "FIXED_85518_POPULATION_CAPACITY_NOT_PER_SEGMENT_RELEASE_PAIRED",
        "rows": rows,
        "summary": {
            "vs_fresh_hca": _verdict_counts(
                [row["s4_vs_fresh_hca"] for row in rows]
            ),
            "vs_archived_paper": _verdict_counts(
                [row["s4_vs_archived_paper"] for row in rows]
            ),
        },
    }


def build_report(
    workload: Mapping[str, Any] | None,
    hca: Mapping[str, Any] | None,
    native: Mapping[str, Any] | None,
    *,
    inputs: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    workload_summary = _workload_summary(workload)
    workload_ready = workload_summary["measurement_status"] == MEASURED
    if hca is not None and hca.get("schema") != HCA_SCHEMA:
        raise Reporting30Error("unexpected G30 HCA aggregate schema")
    if native is not None and native.get("schema") != NATIVE_SCHEMA:
        raise Reporting30Error("unexpected G30 native aggregate schema")
    hca_rows = _index(hca, "rows")
    indexed_native_cases = _index(native, "cases")
    admitted_native_case_ids = _native_admitted_case_ids(native)
    native_cases = {
        case_id: case
        for case_id, case in indexed_native_cases.items()
        if case_id in admitted_native_case_ids
    }

    table_52 = _build_table_52(workload_ready, hca_rows, native_cases)
    table_53 = _build_table_53(table_52, native_cases)
    table_54 = _build_table_54(workload_ready, native_cases)
    table_55 = _build_table_55(workload_ready, hca_rows, native_cases)
    primary = [row["capacity_verdict"] for row in table_52["rows"]] + [
        row["s4_vs_fresh_hca"]
        for row in table_55["rows"]
        if row["case_id"] != PAIR_5_7_CASE_ID
    ]
    context = [
        row[key]
        for row in table_53["rows"]
        for key in (
            "s4_vs_archived_dispersed",
            "s4_vs_archived_hca",
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
    ]
    counts = _verdict_counts(primary)
    context_counts = _verdict_counts(context)
    aggregate_inputs_complete = _hca_aggregate_complete(
        hca
    ) and _native_aggregate_complete(native)
    complete = aggregate_inputs_complete and all(
        value != NOT_MEASURED for value in primary
    )
    zero_losses = complete and all(value != "BASELINE_WIN" for value in primary)
    zero_unresolved = complete and all(value != "UNRESOLVED_TIE" for value in primary)
    target_met = complete and zero_losses and zero_unresolved
    status = (
        "G30_3X_FIXED_HORIZON_PRIMARY_TARGET_MET"
        if target_met
        else "G30_3X_FIXED_HORIZON_PRIMARY_TARGET_NOT_MET"
        if complete
        else "G30_3X_PARTIAL_DIAGNOSTIC"
    )
    return {
        "schema": SCHEMA,
        "title": "G30 3× own-source fixed-horizon capacity report",
        "status": status,
        "report_scope": "G30_3X_FIXED_HORIZON_CAPACITY_WITH_SEPARATE_ARCHIVED_CONTEXT",
        "workload": workload_summary,
        "input_diagnostics": {
            "hca_aggregate_status": hca.get("status") if hca else NOT_MEASURED,
            "hca_primary_complete_case_count": (
                hca.get("primary_complete_case_count") if hca else 0
            ),
            "hca_missing_primary_case_ids": (
                hca.get("missing_primary_case_ids", []) if hca else []
            ),
            "native_aggregate_status": native.get("status") if native else NOT_MEASURED,
            "native_observed_case_count": native.get("observed_case_count", 0) if native else 0,
            "native_portable_admitted_case_count": len(admitted_native_case_ids),
            "hca_portable_aggregate_complete": _hca_aggregate_complete(hca),
            "native_portable_aggregate_complete": _native_aggregate_complete(native),
            "portable_aggregates_complete": aggregate_inputs_complete,
            "partial_inputs_are_diagnostic_only": True,
        },
        "protocol": {
            "inputs": dict(inputs or {}),
            "fixed_raw_bag_denominator": FULL_RAW_BAGS,
            "fixed_segment_population": FULL_SEGMENTS,
            "fixed_start_epoch": FIXED_START_EPOCH,
            "fixed_window_epochs": FIXED_WINDOW_EPOCHS,
            "fixed_last_epoch": int(FIXED_HORIZON),
            "speed_primary": "OWN_SOURCE_FIXED_HORIZON_CAPACITY_NOT_RELEASE_OR_TIMING_PAIRED",
            "timing_claim": "FULL_POPULATION_ONLY;_HCA_SURVIVORS_SECONDARY",
            "fault_claim": "FIXED_85518_POPULATION_NOT_PER_SEGMENT_RELEASE_PAIRED",
            "pair_5_7": NOT_MEASURED,
            "fixed_horizon_capacity_semantics": (
                "S4_AND_HCA_MAY_BOTH_COMPLETE_FEWER_THAN_85518_RAW_BAGS;_"
                "THE_NUMERATOR_IS_THE_BUSINESS_OUTCOME"
            ),
            "incomplete_fixed_horizon_interpretation": (
                "NOT_CPU_TIMEOUT_AND_NOT_SAFETY_FAILURE_WHEN_THE_CASE_IS_"
                "PORTABLE_AGGREGATE_ADMITTED"
            ),
            "survivor_timing_claim_allowed": False,
            "own_source_full_population_descriptive_scope": (
                "TABLE_5_3_AND_TABLE_5_4_CONTEXT_ONLY"
            ),
            "own_source_full_population_descriptive_drives_fresh_timing": False,
        },
        "tables": {"5.2": table_52, "5.3": table_53, "5.4": table_54, "5.5": table_55},
        "joint_decision": {
            "target_name": "G30_3X_FIXED_HORIZON_PRIMARY_CAPACITY_TARGET",
            "target_met": target_met,
            "evidence_complete": complete,
            "zero_baseline_losses": zero_losses,
            "zero_unresolved_ties": zero_unresolved,
            "primary_3x_vs_fresh_hca": counts,
            "archived_reconstruction_context": context_counts,
            "context_losses": context_counts["baseline_win_count"],
            "context_gaps": context_counts["not_measured_count"],
            "context_drives_3x_primary": False,
            "all_original_paper_subjects_exact_win_claimed": False,
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

    def add(table: str, case: str, metric: str, s4: Any, baseline: Any, comparison: str, status: str, verdict: str) -> None:
        rows.append(
            {
                "table_id": table,
                "case_id": case,
                "metric": metric,
                "s4_value": s4,
                "baseline_value": baseline,
                "comparison": comparison,
                "measurement_status": status,
                "verdict": verdict,
            }
        )

    for row in payload["tables"]["5.2"]["rows"]:
        add("5.2", row["case_id"], "completed_raw_bags", row["s4_completed_raw_bags"], row["fresh_hca_completed_raw_bags"], "fresh_hca_3x_fixed_population", row["measurement_status"], row["capacity_verdict"])
        for metric in TIME_METRICS:
            value = row["metrics"][metric]
            add("5.2", row["case_id"], metric, value["s4_minutes"], value["fresh_hca_full_population_repeat_mean_minutes"], "fresh_hca_3x_full_population_timing", row["fresh_timing_status"], value["timing_verdict"])
    for row in payload["tables"]["5.3"]["rows"]:
        add("5.3", "t5_2_speed_2p5", row["metric"], row["s4_3x_minutes"], row["archived_paper_1x_dispersed_minutes"], "archived_paper_dispersed_1x", row["measurement_status"], row["s4_vs_archived_dispersed"])
        add("5.3", "t5_2_speed_2p5", row["metric"], row["s4_3x_minutes"], row["archived_paper_1x_hca_minutes"], "archived_paper_hca_1x", row["measurement_status"], row["s4_vs_archived_hca"])
        add("5.3", "t5_2_speed_2p5", f"{row['metric']}_improvement_percent", row["s4_3x_improvement_from_archived_dispersed_percent"], row["paper_reported_improvement_percent"], "archived_paper_reported_improvement_1x", row["measurement_status"], row["improvement_vs_paper_reported"])
    for row in payload["tables"]["5.4"]["rows"]:
        add("5.4", row["case_id"], "completed_raw_bags", row["s4_completed_raw_bags"], None, "3x_capacity_diagnostic", row["capacity_measurement_status"], NOT_MEASURED)
        add("5.4", row["case_id"], "mean", row["s4_3x_mean_minutes"], row["archived_paper_1x_dynamic_minutes"], "archived_dynamic_1x_unpaired", row["timing_measurement_status"], row["s4_vs_archived_dynamic"])
        add("5.4", row["case_id"], "mean", row["s4_3x_mean_minutes"], row["archived_paper_1x_static_minutes"], "archived_static_1x_unpaired", row["timing_measurement_status"], row["s4_vs_archived_static"])
        add("5.4", row["case_id"], "improvement_percent", row["s4_improvement_vs_archived_static_percent"], row["paper_reported_improvement_percent"], "archived_paper_reported_improvement_1x_unpaired", row["timing_measurement_status"], row["improvement_vs_paper_reported"])
    for row in payload["tables"]["5.5"]["rows"]:
        add("5.5", row["case_id"], "completed_raw_bags", row.get("s4_completed_raw_bags"), row.get("fresh_hca_completed_raw_bags"), "fresh_hca_3x_fixed_population", row["measurement_status"], row["s4_vs_fresh_hca"])
        add("5.5", row["case_id"], "success_rate", row.get("s4_success_rate"), row.get("paper_success_rate"), "archived_paper_success_rate_1x", row["measurement_status"], row["s4_vs_archived_paper"])
    return rows


def render_csv(payload: Mapping[str, Any]) -> str:
    fields = (
        "table_id",
        "case_id",
        "metric",
        "s4_value",
        "baseline_value",
        "comparison",
        "measurement_status",
        "verdict",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(_csv_rows(payload))
    return stream.getvalue()


def _fmt(value: Any, digits: int = 4) -> str:
    return NOT_MEASURED if value is None else f"{float(value):.{digits}f}"


def render_markdown(payload: Mapping[str, Any]) -> str:
    decision = payload["joint_decision"]
    lines = [
        "# G30 3× own-source fixed-horizon capacity 报告",
        "",
        f"状态：`{payload['status']}`。这是固定 **85,518 件 raw bags / 130,809 segments**、epoch 8,260–98,259 的容量报告，不是 release-paired 或 timing-paired 声明。partial inputs 只产生诊断，不预写胜利。",
        "",
        "S4 与 HCA 都允许在固定时域结束时只完成 85,518 总体的一部分；该固定分母 numerator 是业务容量结果。只要 case 已通过 portable aggregate 准入，这不表示 CPU 超时或安全失败。",
        "",
        "## Table 5.2 — 四速度容量",
        "",
        "| speed | S4/HCA completed | capacity verdict | timing status | HCA survivor secondary mean |",
        "|---:|---:|---|---|---:|",
    ]
    for row in payload["tables"]["5.2"]["rows"]:
        secondary = row["metrics"]["mean"]["fresh_hca_censored_survivor_repeat_mean_minutes"]
        lines.append(
            f"| {row['speed_mps']:.1f} | {row['s4_completed_raw_bags']} / {row['fresh_hca_completed_raw_bags']} | {row['capacity_verdict']} | {row['fresh_timing_status']} | {_fmt(secondary)} |"
        )
    lines.extend(
        [
            "",
            "HCA 未完成固定总体时，正式 timing 为 `NOT_APPLICABLE_BASELINE_INCOMPLETE`；完成者分布只作 `CENSORED_SECONDARY`，不参与胜负。",
            "",
            "## Archived/reconstruction context（不驱动 3× primary）",
            "",
            "`OWN_SOURCE_FULL_POPULATION_DESCRIPTIVE` 只允许进入 Table 5.3/5.4 上下文；它不形成 fresh HCA timing verdict，也不驱动 3× primary。",
            "",
            f"Context losses={decision['context_losses']}，gaps={decision['context_gaps']}；全部显式保留。",
            "",
            "### Table 5.3",
            "",
            "| metric | S4 3× | archived dispersed/HCA 1× | verdicts | status |",
            "|---|---:|---:|---|---|",
        ]
    )
    for row in payload["tables"]["5.3"]["rows"]:
        lines.append(
            f"| {row['metric']} | {_fmt(row['s4_3x_minutes'])} | {row['archived_paper_1x_dispersed_minutes']:.2f} / {row['archived_paper_1x_hca_minutes']:.2f} | {row['s4_vs_archived_dispersed']} / {row['s4_vs_archived_hca']} | {row['measurement_status']} |"
        )
    lines.extend(
        [
            "",
            "### Table 5.4 — 12 个 legacy-variant reconstruction cells",
            "",
            "| case | completed/85,518 | S4 mean | archived dynamic/static | S4 improvement / paper | verdicts (dynamic/static/improvement) | capacity/timing status |",
            "|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for row in payload["tables"]["5.4"]["rows"]:
        lines.append(
            f"| {row['case_id']} | {row['s4_completed_raw_bags']} | {_fmt(row['s4_3x_mean_minutes'])} | {row['archived_paper_1x_dynamic_minutes']:.2f} / {row['archived_paper_1x_static_minutes']:.2f} | {_fmt(row['s4_improvement_vs_archived_static_percent'])} / {row['paper_reported_improvement_percent']:.2f} | {row['s4_vs_archived_dynamic']} / {row['s4_vs_archived_static']} / {row['improvement_vs_paper_reported']} | {row['capacity_measurement_status']} / {row['timing_measurement_status']} |"
        )
    lines.extend(
        [
            "",
            "Table 5.4 仍是 `DESCRIPTIVE_UNPAIRED`；legacy 实现、随机流和逐 case 配对未恢复。",
            "",
            "## Table 5.5 — 线路中断",
            "",
            "**固定 85,518 总体容量比较；不是逐 segment fault-release 配对。**",
            "",
            "S4/HCA 的 numerator 都可低于 85,518；这仍是完整固定时域业务 outcome，禁止用幸存者 timing 替代容量比较。",
            "",
            "| scenario | S4/HCA completed | topology upper | verdict | status |",
            "|---|---:|---:|---|---|",
        ]
    )
    for row in payload["tables"]["5.5"]["rows"]:
        lines.append(
            f"| {row['scenario_id']} | {row.get('s4_completed_raw_bags', NOT_MEASURED)} / {row.get('fresh_hca_completed_raw_bags', NOT_MEASURED)} | {row.get('topology_reachable_raw_bag_upper_bound', NOT_MEASURED)} | {row['s4_vs_fresh_hca']} | {row['measurement_status']} |"
        )
    lines.extend(
        [
            "",
            "`pair_5_7` 固定为 `NOT_MEASURED`，且不进入 19 格 fresh primary。",
            "",
            "## 联合判定",
            "",
            f"target_met=`{str(decision['target_met']).lower()}`；evidence_complete=`{str(decision['evidence_complete']).lower()}`；primary wins/ties/losses/gaps={decision['primary_3x_vs_fresh_hca']['s4_win_count']}/{decision['primary_3x_vs_fresh_hca']['allowed_tie_count']}/{decision['primary_3x_vs_fresh_hca']['baseline_win_count']}/{decision['primary_3x_vs_fresh_hca']['not_measured_count']}。",
            "",
            "运行时边界仍是 S4/J2/E2 + local FIFO + service-aware static local potential；每个转向点只决定下一跳，没有完整 A*、未来完整路线、HCA 全局预约表或 learning。",
            "",
        ]
    )
    return "\n".join(lines)


def _load_optional(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise Reporting30Error(f"JSON object required: {path}")
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
            raise Reporting30Error(
                "committed validation requires the workload and both portable aggregates"
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
            args.json_output: json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            args.csv_output: render_csv(payload),
            args.markdown_output: render_markdown(payload),
        }
        if args.validate_committed:
            for path, expected in texts.items():
                if not path.is_file():
                    raise Reporting30Error(f"missing committed G30 report: {path}")
                if path.read_text(encoding="utf-8") != expected:
                    raise Reporting30Error(f"committed G30 report is stale: {path}")
            print("G30 committed portable reporting validation: PASS")
            return 0
        for path, text in texts.items():
            _write(path, text)
    except (Reporting30Error, OSError, json.JSONDecodeError) as exc:
        print(f"G30 reporting failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": payload["status"],
                "json": _relative(args.json_output),
                "csv": _relative(args.csv_output),
                "markdown": _relative(args.markdown_output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
