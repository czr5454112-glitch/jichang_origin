#!/usr/bin/env python3
"""Build the compact G26 paper-table comparison artifacts.

The reporter consumes already-produced HCA and S4 JSON.  It never launches a
simulator.  Paper values are embedded as archived evidence, while runtime
values are admitted only when their full canonical cohort contract is visible.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "czr005.g4irsf26.reporting.v1"
CANONICAL_SEGMENTS = 43_603
CANONICAL_RAW_BAGS = 28_506
HCA_FULL_START_EPOCH = 8_260.0
HCA_FULL_MAX_EPOCHS = 90_000
HCA_FULL_LAST_EPOCH = 98_259.0

REGISTERED_RELEASE_SOURCE_BY_SPEED = {
    1.5: "artifacts/datasets/g4irsf26_release_speed_1p5.csv",
    2.0: "artifacts/datasets/g4irsf26_release_speed_2p0.csv",
    2.5: "artifacts/datasets/g4irsf24_release_compact.csv",
    3.0: "artifacts/datasets/g4irsf26_release_speed_3p0.csv",
}

DEFAULT_JSON = ROOT / "outputs/tables/g4irsf26_reporting.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf26_reporting.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/g4irsf26_reporting.md"
DEFAULT_S4_INPUT = ROOT / "outputs/tables/g4irsf26_paper_experiments.json"

EVIDENCE_ARCHIVED = "ARCHIVED"
EVIDENCE_EXACT = "EXACT_FRESH"
EVIDENCE_RECONSTRUCTED = "RECONSTRUCTED"
EVIDENCE_TOPOLOGY = "TOPOLOGY_PROVEN_RECONSTRUCTION"
EVIDENCE_PROTOCOL_CONTROLLED = "PROTOCOL_CONTROLLED_RECONSTRUCTION"
NOT_MEASURED = "NOT_MEASURED"


PAPER_TABLE_5_2 = (
    {"speed_mps": 1.5, "min": 5.10, "mean": 6.44, "max": 9.68},
    {"speed_mps": 2.0, "min": 3.87, "mean": 4.93, "max": 7.37},
    {"speed_mps": 2.5, "min": 3.13, "mean": 3.96, "max": 5.98},
    {"speed_mps": 3.0, "min": 2.63, "mean": 3.37, "max": 5.05},
)

PAPER_TABLE_5_3 = (
    {
        "method": "dispersed_heuristic",
        "unit": "minutes",
        "min": 3.56,
        "mean": 4.43,
        "max": 8.62,
    },
    {
        "method": "iot_drpa_hca_star",
        "unit": "minutes",
        "min": 3.13,
        "mean": 3.96,
        "max": 5.98,
    },
    {
        "method": "paper_improvement",
        "unit": "percent",
        "min": 12.10,
        "mean": 10.60,
        "max": 30.60,
    },
)

PAPER_TABLE_5_4 = (
    {"standard_speed_mps": 1.5, "deviation_percent": 10, "dynamic": 6.45, "static": 6.59, "improvement": 2.12},
    {"standard_speed_mps": 1.5, "deviation_percent": 20, "dynamic": 6.67, "static": 6.86, "improvement": 2.77},
    {"standard_speed_mps": 1.5, "deviation_percent": 30, "dynamic": 6.91, "static": 7.11, "improvement": 2.81},
    {"standard_speed_mps": 2.0, "deviation_percent": 10, "dynamic": 4.92, "static": 5.07, "improvement": 2.96},
    {"standard_speed_mps": 2.0, "deviation_percent": 20, "dynamic": 5.16, "static": 5.36, "improvement": 3.73},
    {"standard_speed_mps": 2.0, "deviation_percent": 30, "dynamic": 5.42, "static": 5.62, "improvement": 3.56},
    {"standard_speed_mps": 2.5, "deviation_percent": 10, "dynamic": 3.99, "static": 4.19, "improvement": 4.77},
    {"standard_speed_mps": 2.5, "deviation_percent": 20, "dynamic": 4.25, "static": 4.46, "improvement": 4.71},
    {"standard_speed_mps": 2.5, "deviation_percent": 30, "dynamic": 4.49, "static": 4.72, "improvement": 4.87},
    {"standard_speed_mps": 3.0, "deviation_percent": 10, "dynamic": 3.39, "static": 3.56, "improvement": 4.78},
    {"standard_speed_mps": 3.0, "deviation_percent": 20, "dynamic": 3.51, "static": 3.72, "improvement": 5.65},
    {"standard_speed_mps": 3.0, "deviation_percent": 30, "dynamic": 3.64, "static": 3.87, "improvement": 5.94},
)

INTERRUPTION_EDGE_BY_ID = {
    1: (6, 12),
    2: (8, 11),
    3: (13, 23),
    4: (24, 27),
    5: (14, 46),
    6: (43, 15),
    7: (33, 44),
    8: (31, 32),
}
INTERRUPTION_ID_BY_EDGE = {
    edge: interruption_id
    for interruption_id, edge in INTERRUPTION_EDGE_BY_ID.items()
}
RECONSTRUCTED_69_EDGE_LINE_IDS = frozenset({1, 6, 7})
PAIR_5_7_LINE_IDS = (5, 7)
PAIR_5_7_ARCHIVED_WORKBOOK_EDGES = ((33, 44), (46, 36))
PAIR_5_7_FRESH_PROTOCOL_STATUS = "ARCHIVED_ONLY_SOURCE_PROTOCOL_UNRESOLVED"

PAPER_TABLE_5_5 = (
    {"scenario_id": "single_1", "line_ids": (1,), "affected_conveyors": 1, "success_rate": 1.00},
    {"scenario_id": "single_2", "line_ids": (2,), "affected_conveyors": 7, "success_rate": 0.88},
    {"scenario_id": "single_3", "line_ids": (3,), "affected_conveyors": 5, "success_rate": 1.00},
    {"scenario_id": "single_4", "line_ids": (4,), "affected_conveyors": 15, "success_rate": 0.95},
    {"scenario_id": "single_5", "line_ids": (5,), "affected_conveyors": 24, "success_rate": 0.97},
    {"scenario_id": "single_6", "line_ids": (6,), "affected_conveyors": 7, "success_rate": 0.96},
    {"scenario_id": "single_7", "line_ids": (7,), "affected_conveyors": 1, "success_rate": 1.00},
    {"scenario_id": "single_8", "line_ids": (8,), "affected_conveyors": 7, "success_rate": 0.99},
    {"scenario_id": "pair_1_7", "line_ids": (1, 7), "affected_conveyors": 2, "success_rate": 1.00},
    {"scenario_id": "pair_2_4", "line_ids": (2, 4), "affected_conveyors": 22, "success_rate": 0.76},
    {"scenario_id": "pair_3_5", "line_ids": (3, 5), "affected_conveyors": 36, "success_rate": 0.66},
    {"scenario_id": "pair_4_5", "line_ids": (4, 5), "affected_conveyors": 54, "success_rate": 0.00},
    {"scenario_id": "pair_5_7", "line_ids": (5, 7), "affected_conveyors": 12, "success_rate": 0.48},
    {"scenario_id": "triple_2_4_6", "line_ids": (2, 4, 6), "affected_conveyors": 36, "success_rate": 0.26},
    {"scenario_id": "triple_3_5_8", "line_ids": (3, 5, 8), "affected_conveyors": 51, "success_rate": 0.05},
    {"scenario_id": "triple_4_6_7", "line_ids": (4, 6, 7), "affected_conveyors": 30, "success_rate": 0.26},
)


class ReportingError(RuntimeError):
    pass


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _path_get(value: Mapping[str, Any], path: Sequence[str]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _first(value: Mapping[str, Any], paths: Iterable[Sequence[str]]) -> Any:
    for path in paths:
        found = _path_get(value, path)
        if found is not None:
            return found
    return None


def _first_number(value: Mapping[str, Any], paths: Iterable[Sequence[str]]) -> float | None:
    return _number(_first(value, paths))


def _first_integer(value: Mapping[str, Any], paths: Iterable[Sequence[str]]) -> int | None:
    return _integer(_first(value, paths))


def _normal_table(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).lower().replace("table", "").replace("t", "")
    text = text.replace("_", ".").replace("-", ".").strip(" .")
    match = re.search(r"5\s*\.\s*([2345])", text)
    return f"5.{match.group(1)}" if match else None


def _status_complete(value: Any) -> bool:
    return str(value).strip().upper() in {
        "PASS",
        "COMPLETE",
        "COMPLETE_FIXED_HORIZON",
        "COMPLETE_TOPOLOGY_SATURATED",
        "COMPLETED",
        "MEASURED",
        "GO",
    }


def _line_ids_from_explicit(value: Any) -> tuple[int, ...]:
    if isinstance(value, (list, tuple)):
        parsed = [_integer(item) for item in value]
        if all(item in INTERRUPTION_EDGE_BY_ID for item in parsed):
            return tuple(sorted({int(item) for item in parsed if item is not None}))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        item = _integer(value)
        return (item,) if item in INTERRUPTION_EDGE_BY_ID else ()
    if isinstance(value, str):
        parsed = [int(part) for part in re.findall(r"\d+", value)]
        if parsed and all(item in INTERRUPTION_EDGE_BY_ID for item in parsed):
            return tuple(sorted(set(parsed)))
    return ()


def _fault_edges(record: Mapping[str, Any]) -> tuple[tuple[int, int], ...]:
    explicit = _first(
        record,
        (
            ("case", "seed_edges"),
            ("seed_edges",),
        ),
    )
    edges: set[tuple[int, int]] = set()
    if isinstance(explicit, (list, tuple)):
        for value in explicit:
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                left, right = _integer(value[0]), _integer(value[1])
                if left is not None and right is not None:
                    edges.add((left, right))
    if edges:
        return tuple(sorted(edges))

    schedule = _first(
        record,
        (
            ("case", "fault_schedule"),
            ("protocol", "fault_schedule"),
            ("fault_schedule",),
        ),
    )
    if schedule is None or str(schedule).strip().lower() in {"", "none", "off"}:
        return ()
    text = str(schedule)
    for part in text.split(";"):
        fields = part.split(":")
        if len(fields) >= 4 and fields[-1].strip().lower() == "fault":
            left = _integer(fields[-3])
            right = _integer(fields[-2])
            if left is not None and right is not None:
                edges.add((left, right))
    for left, right in re.findall(r"(\d+)\s*(?:->|,)\s*(\d+)", text):
        edges.add((int(left), int(right)))
    return tuple(sorted(edges))


def _hca_fault_protocol_exact(
    record: Mapping[str, Any], line_ids: Sequence[int]
) -> bool:
    """Require the registered all-day Java fault window, not only its edges."""

    schedule = _first(
        record,
        (
            ("case", "fault_schedule"),
            ("protocol", "fault_schedule"),
            ("fault_schedule",),
        ),
    )
    if schedule is None:
        return False
    events: list[tuple[float, int, int, str]] = []
    for part in str(schedule).split(";"):
        fields = [field.strip() for field in part.split(":")]
        if len(fields) != 4:
            return False
        epoch = _number(fields[0])
        start = _integer(fields[1])
        end = _integer(fields[2])
        action = fields[3].lower()
        if epoch is None or start is None or end is None:
            return False
        events.append((epoch, start, end, action))

    expected_edges = _expected_fault_edges(line_ids)
    if (
        len(events) != len(expected_edges)
        or any(action != "fault" for _epoch, _start, _end, action in events)
        or any(
            not math.isclose(
                epoch, HCA_FULL_START_EPOCH, rel_tol=0.0, abs_tol=1.0e-9
            )
            for epoch, _start, _end, _action in events
        )
        or tuple(sorted((start, end) for _epoch, start, end, _action in events))
        != expected_edges
    ):
        return False

    start_epoch = _first_number(
        record, (("benchmark_summary", "start_epoch"),)
    )
    max_epochs = _first_integer(
        record, (("benchmark_summary", "max_epochs"),)
    )
    last_epoch = _first_number(
        record, (("benchmark_summary", "last_epoch"),)
    )
    fault_events = _first_integer(
        record, (("benchmark_summary", "fault_event_count"),)
    )
    repair_events = _first_integer(
        record, (("benchmark_summary", "repair_event_count"),)
    )
    return (
        start_epoch is not None
        and math.isclose(
            start_epoch, HCA_FULL_START_EPOCH, rel_tol=0.0, abs_tol=1.0e-9
        )
        and max_epochs == HCA_FULL_MAX_EPOCHS
        and last_epoch is not None
        and math.isclose(
            last_epoch, HCA_FULL_LAST_EPOCH, rel_tol=0.0, abs_tol=1.0e-9
        )
        and fault_events == len(expected_edges)
        and repair_events == 0
    )


def _registered_release_source_matches(
    record: Mapping[str, Any], standard_speed_mps: float | None
) -> bool:
    if standard_speed_mps not in REGISTERED_RELEASE_SOURCE_BY_SPEED:
        return False
    source = _first(
        record, (("protocol", "exact_hca_release_alignment", "source"),)
    )
    if not isinstance(source, str):
        return False
    return (
        source.replace("\\", "/")
        == REGISTERED_RELEASE_SOURCE_BY_SPEED[standard_speed_mps]
    )


def _expected_fault_edges(line_ids: Sequence[int]) -> tuple[tuple[int, int], ...]:
    normalized = tuple(sorted(line_ids))
    if normalized == PAIR_5_7_LINE_IDS:
        return tuple(sorted(PAIR_5_7_ARCHIVED_WORKBOOK_EDGES))
    return tuple(sorted(INTERRUPTION_EDGE_BY_ID[line_id] for line_id in normalized))


def _fault_identity(record: Mapping[str, Any]) -> tuple[tuple[int, ...], bool]:
    explicit = _first(
        record,
        (
            ("case", "fault_line_ids"),
            ("case", "line_ids"),
            ("fault_line_ids",),
            ("line_ids",),
            ("interruption_ids",),
        ),
    )
    line_ids = _line_ids_from_explicit(explicit)
    if line_ids:
        return line_ids, True

    edges = set(_fault_edges(record))
    if not edges:
        return (), False
    if edges == set(PAIR_5_7_ARCHIVED_WORKBOOK_EDGES):
        return PAIR_5_7_LINE_IDS, True
    reconstructed = tuple(
        sorted(
            INTERRUPTION_ID_BY_EDGE[edge]
            for edge in edges
            if edge in INTERRUPTION_ID_BY_EDGE
        )
    )
    return reconstructed, True


def _timing_stats(record: Mapping[str, Any], *, hca: bool) -> dict[str, float] | None:
    if hca:
        candidate = _first(
            record,
            (
                ("denominators", "processed_attempt", "minutes"),
                ("metrics", "denominators", "processed_attempt", "minutes"),
            ),
        )
    else:
        candidate = _first(
            record,
            (
                ("outcome", "paper_raw_bag_tth", "distribution", "minutes"),
                ("outcome", "paper_raw_bag_tth", "minutes"),
                ("outcome", "paper_raw_bag_tth"),
                ("outcome", "raw_bag_tth", "minutes"),
                ("paper_raw_bag_tth", "minutes"),
                ("paper_raw_bag_tth",),
            ),
        )
    if not isinstance(candidate, Mapping):
        return None
    result: dict[str, float] = {}
    for name, aliases in {
        "min": ("min",),
        "mean": ("mean", "avg", "average"),
        "max": ("max",),
    }.items():
        observed = next((_number(candidate.get(alias)) for alias in aliases if alias in candidate), None)
        if observed is None:
            return None
        result[name] = observed
    return result


def _speed(record: Mapping[str, Any]) -> float | None:
    return _first_number(
        record,
        (
            ("case", "actual_speed_mps"),
            ("case", "speed_mps"),
            ("speed_mps",),
            ("benchmark_summary", "speed_mps"),
            ("metrics", "speed_mps"),
        ),
    )


def _standard_speed(record: Mapping[str, Any]) -> float | None:
    return _first_number(
        record,
        (
            ("case", "standard_speed_mps"),
            ("standard_speed_mps",),
            ("case", "speed_mps"),
            ("speed_mps",),
            ("benchmark_summary", "speed_mps"),
        ),
    )


def _s4_success(record: Mapping[str, Any]) -> dict[str, float | int | None]:
    completed = _first_integer(
        record,
        (
            ("outcome", "completed_raw_bags"),
            ("outcome", "complete_raw_bag_count"),
            ("outcome", "completed_raw_bag_count"),
            ("outcome", "raw_bags", "completed"),
            ("outcome", "success", "primary_completed_raw_bags", "count"),
            ("completed_raw_bags",),
        ),
    )
    std_count = _first_integer(
        record,
        (
            ("outcome", "success_rates", "finish_le_std_count"),
            ("outcome", "success_rates", "finish_by_std_count"),
            ("outcome", "finish_le_std_count"),
            ("outcome", "success", "finish_le_std", "count"),
        ),
    )
    literal_count = _first_integer(
        record,
        (
            ("outcome", "success_rates", "finish_le_std_minus_2700_count"),
            ("outcome", "success_rates", "literal_count"),
            ("outcome", "finish_le_std_minus_2700_count"),
            ("outcome", "success", "finish_le_std_minus_2700_literal", "count"),
        ),
    )
    std_rate = _first_number(
        record,
        (
            ("outcome", "success_rates", "finish_le_std"),
            ("outcome", "success_rates", "finish_by_std"),
            ("outcome", "success_rates", "secondary"),
            ("outcome", "success", "finish_le_std", "rate"),
        ),
    )
    literal_rate = _first_number(
        record,
        (
            ("outcome", "success_rates", "finish_le_std_minus_2700"),
            ("outcome", "success_rates", "literal"),
            ("outcome", "success", "finish_le_std_minus_2700_literal", "rate"),
        ),
    )
    return {
        "completed_raw_bags": completed,
        "primary": completed / CANONICAL_RAW_BAGS if completed is not None else None,
        "finish_le_std_count": std_count,
        "finish_le_std": (
            std_count / CANONICAL_RAW_BAGS if std_count is not None else std_rate
        ),
        "finish_le_std_minus_2700_count": literal_count,
        "finish_le_std_minus_2700": (
            literal_count / CANONICAL_RAW_BAGS
            if literal_count is not None
            else literal_rate
        ),
    }


def _hca_success(record: Mapping[str, Any]) -> dict[str, float | int | None]:
    completed = _first_integer(
        record,
        (
            ("canonical_complete_raw_bag_count",),
            ("complete_raw_bag_count",),
            ("outcome", "completed_raw_bags"),
        ),
    )
    return {
        "completed_raw_bags": completed,
        "primary": completed / CANONICAL_RAW_BAGS if completed is not None else None,
        "finish_le_std_count": None,
        "finish_le_std": None,
        "finish_le_std_minus_2700_count": None,
        "finish_le_std_minus_2700": None,
    }


def _hca_measurement(record: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(_first(record, (("denominators",), ("metrics", "denominators"))), Mapping):
        return None
    canonical_segments = _first_integer(record, (("canonical_segment_count",),))
    canonical_bags = _first_integer(record, (("canonical_raw_bag_count",),))
    released_segments = _first_integer(record, (("released_segment_count",),))
    completed_segments = _first_integer(record, (("completed_segment_count",),))
    line_ids, has_fault = _fault_identity(record)
    fault_edges = _fault_edges(record)
    status = _first(record, (("status",), ("run_status", "status")))
    # A Table 5.5 failure is represented by segments that can never be
    # released/completed after the interruption. Requiring a full released
    # cohort here would discard the primary outcome being measured. The
    # stricter all-released/all-completed gate remains below for timing rows.
    exact_cohort = (
        _status_complete(status)
        and canonical_segments == CANONICAL_SEGMENTS
        and canonical_bags == CANONICAL_RAW_BAGS
    )
    timing = _timing_stats(record, hca=True)
    fault_protocol_matches_expected = (
        not has_fault or fault_edges == _expected_fault_edges(line_ids)
    )
    fault_protocol_exact = (
        not has_fault
        or (
            fault_protocol_matches_expected
            and _hca_fault_protocol_exact(record, line_ids)
        )
    )
    exact_timing = (
        exact_cohort
        and released_segments == CANONICAL_SEGMENTS
        and completed_segments == CANONICAL_SEGMENTS
        and _first(record, (("comparison_eligible",),)) is True
        and timing is not None
    )
    return {
        "system": "HCA",
        "case_id": str(_first(record, (("case", "case_id"), ("case_id",), ("run_id",))) or ""),
        "table": _normal_table(_first(record, (("case", "table"), ("table",)))),
        "speed_mps": _speed(record),
        "standard_speed_mps": _standard_speed(record),
        "deviation_percent": _first_integer(record, (("case", "deviation_percent"), ("deviation_percent",))),
        "line_ids": line_ids,
        "has_fault": has_fault,
        "fault_edges": fault_edges,
        "fault_protocol_matches_expected": fault_protocol_matches_expected,
        "fault_protocol_exact": fault_protocol_exact,
        "timing": timing,
        "success": _hca_success(record),
        "exact_cohort": exact_cohort,
        "exact_timing": exact_timing,
        "released_segment_count": released_segments,
        "completed_segment_count": completed_segments,
    }


def _s4_measurement(record: Mapping[str, Any]) -> dict[str, Any] | None:
    if not isinstance(record.get("case"), Mapping) or not isinstance(record.get("outcome"), Mapping):
        return None
    case = record["case"]
    protocol = record.get("protocol") if isinstance(record.get("protocol"), Mapping) else {}
    outcome = record["outcome"]
    line_ids, has_fault = _fault_identity(record)
    fault_edges = _fault_edges(record)
    requested_segments = _first_integer(
        record,
        (
            ("protocol", "segment_count"),
            ("outcome", "requested_segments"),
            ("outcome", "requested_segment_count"),
            ("outcome", "segments", "requested"),
        ),
    )
    requested_bags = _first_integer(
        record,
        (
            ("protocol", "raw_bag_count"),
            ("outcome", "requested_raw_bags"),
            ("outcome", "raw_bags", "requested"),
        ),
    )
    completed_segments = _first_integer(
        record,
        (
            ("outcome", "completed_segments"),
            ("outcome", "runtime_completed_segment_count"),
            ("outcome", "segments", "completed"),
        ),
    )
    release_alignment = _first(
        record,
        (
            ("protocol", "exact_hca_release_alignment"),
            ("protocol", "exact_release_alignment"),
        ),
    )
    exact_status = _first(record, (("protocol", "exact_fresh_status"),))
    strict_safety_pass = _first(
        record,
        (
            ("safety", "pass"),
            ("safety", "safety_pass"),
            ("safety", "strict_s4", "pass"),
        ),
    )
    status = record.get("status")
    standard_speed_mps = _standard_speed(record)
    admission_pass = _first(record, (("safety", "admission", "pass"),))
    admission_mode = _first(record, (("safety", "admission", "mode"),))
    business_failure_is_safety_failure = _first(
        record, (("outcome", "business_failure_is_safety_failure"),)
    )
    business_and_safety_axes_are_separate = _first(
        record, (("outcome", "business_and_safety_axes_are_separate"),)
    )
    topology_upper_bound = _first_integer(
        record,
        (
            ("outcome", "topology_reachable_raw_bag_upper_bound"),
            (
                "outcome",
                "topology_reachability",
                "topology_reachable_raw_bag_upper_bound",
            ),
        ),
    )
    topology_safety_pass = _first(
        record, (("safety", "topology_saturation_fault", "pass"),)
    )
    secondary_metrics_censored = _first(
        record, (("outcome", "secondary_metrics_censored_by_event_limit"),)
    )
    primary_success_topology_saturated = _first(
        record, (("outcome", "primary_success_topology_saturated"),)
    )
    admitted_claim_scope = _first(
        record, (("outcome", "admitted_claim_scope"),)
    )
    if has_fault:
        safety_pass = (
            str(status).strip().upper() == "COMPLETE_FIXED_HORIZON"
            and admission_pass is True
            and admission_mode == "TABLE_5_5_FIXED_HORIZON_SAFETY"
            and business_failure_is_safety_failure is False
            and business_and_safety_axes_are_separate is True
        )
    else:
        safety_pass = (
            str(status).strip().upper() == "COMPLETE"
            and strict_safety_pass is True
        )
    canonical_cohort = (
        _status_complete(status)
        and (
            release_alignment is True
            or (
                isinstance(release_alignment, Mapping)
                and _first_integer(release_alignment, (("aligned_segment_count",),))
                == CANONICAL_SEGMENTS
            )
            or exact_status == "EXACT_G24_LIFECYCLE_ALIGNED"
        )
        and requested_segments == CANONICAL_SEGMENTS
        and requested_bags == CANONICAL_RAW_BAGS
        and _registered_release_source_matches(record, standard_speed_mps)
    )
    timing = _timing_stats(record, hca=False)
    success = _s4_success(record)
    exact_cohort = canonical_cohort and safety_pass
    topology_proven = (
        canonical_cohort
        and has_fault
        and str(status).strip().upper() == "COMPLETE_TOPOLOGY_SATURATED"
        and admission_pass is True
        and admission_mode == "TABLE_5_5_TOPOLOGY_SATURATION_EVIDENCE"
        and topology_safety_pass is True
        and topology_upper_bound is not None
        and topology_upper_bound == success["completed_raw_bags"]
        and business_failure_is_safety_failure is False
        and business_and_safety_axes_are_separate is True
        and primary_success_topology_saturated is True
        and secondary_metrics_censored is True
        and admitted_claim_scope == "TABLE_5_5_PRIMARY_SUCCESS_RATE_ONLY"
    )
    exact_timing = (
        exact_cohort
        and completed_segments == CANONICAL_SEGMENTS
        and success["completed_raw_bags"] == CANONICAL_RAW_BAGS
        and timing is not None
    )
    return {
        "system": "S4",
        "case_id": str(case.get("case_id", "")),
        "case_role": str(case.get("case_role", "")),
        "comparison_reference_case_id": case.get("comparison_reference_case_id"),
        "table": _normal_table(case.get("table") or case.get("paper_tables")),
        "speed_mps": _speed(record),
        "standard_speed_mps": standard_speed_mps,
        "deviation_percent": _first_integer(record, (("case", "deviation_percent"),)),
        "line_ids": line_ids,
        "has_fault": has_fault,
        "fault_edges": fault_edges,
        "fault_protocol_matches_expected": (
            not has_fault or fault_edges == _expected_fault_edges(line_ids)
        ),
        "timing": timing,
        "success": success,
        "exact_cohort": exact_cohort,
        "topology_proven": topology_proven,
        "exact_timing": exact_timing,
        "admission_mode": admission_mode,
        "topology_reachable_raw_bag_upper_bound": topology_upper_bound,
        "topology_safety_pass": topology_safety_pass,
        "secondary_metrics_censored": secondary_metrics_censored,
        "business_failed_raw_bags": _first_integer(
            record, (("outcome", "business_failed_raw_bag_count"),)
        ),
        "business_failure_is_safety_failure": business_failure_is_safety_failure,
        "business_and_safety_axes_are_separate": business_and_safety_axes_are_separate,
        "protocol_denominator": (
            protocol.get("tth_denominator")
            or protocol.get("paper_raw_bag_tth_denominator")
        ),
        "outcome": outcome,
    }


def _walk_records(payload: Any, inherited: Mapping[str, Any] | None = None) -> Iterable[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return
    context = dict(inherited or {})
    for key in ("case", "protocol"):
        if isinstance(payload.get(key), Mapping):
            context[key] = dict(payload[key])
    merged = {**context, **payload}
    yield merged
    for key in ("runs", "cases", "results"):
        children = payload.get(key)
        if isinstance(children, list):
            for child in children:
                yield from _walk_records(child, context)
    for key in ("result", "metrics"):
        child = payload.get(key)
        if isinstance(child, Mapping):
            yield from _walk_records(child, context)


def extract_measurements(
    hca_payloads: Sequence[Mapping[str, Any]],
    s4_payloads: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    hca: list[dict[str, Any]] = []
    s4: list[dict[str, Any]] = []
    for payload in hca_payloads:
        for record in _walk_records(payload):
            measurement = _hca_measurement(record)
            if measurement is not None:
                hca.append(measurement)
    for payload in s4_payloads:
        for record in _walk_records(payload):
            measurement = _s4_measurement(record)
            if measurement is not None:
                s4.append(measurement)
    return hca, s4


def _same_number(left: Any, right: Any) -> bool:
    left_number = _number(left)
    right_number = _number(right)
    return (
        left_number is not None
        and right_number is not None
        and math.isclose(left_number, right_number, rel_tol=0.0, abs_tol=1.0e-9)
    )


def _select(
    candidates: Iterable[dict[str, Any]],
    *,
    exact_field: str,
    value_path: Sequence[str],
) -> dict[str, Any] | None:
    eligible = [row for row in candidates if row.get(exact_field) is True]
    if not eligible:
        return None
    reference = _path_get(eligible[0], value_path)
    if _number(reference) is None:
        return None
    if any(not _same_number(_path_get(row, value_path), reference) for row in eligible[1:]):
        return None
    selected = dict(eligible[0])
    selected["repeat_count"] = len(eligible)
    return selected


def _select_timing(
    candidates: Iterable[dict[str, Any]], *, exact_field: str
) -> dict[str, Any] | None:
    """Select repeats only when every published Table 5.2 statistic agrees."""

    eligible = [row for row in candidates if row.get(exact_field) is True]
    if not eligible:
        return None
    statistics = ("min", "mean", "max")
    reference = tuple(_path_get(eligible[0], ("timing", name)) for name in statistics)
    if any(_number(value) is None for value in reference):
        return None
    if any(
        any(
            not _same_number(_path_get(row, ("timing", name)), expected)
            for name, expected in zip(statistics, reference)
        )
        for row in eligible[1:]
    ):
        return None
    selected = dict(eligible[0])
    selected["repeat_count"] = len(eligible)
    return selected


def _speed_matches(value: Any, expected: float) -> bool:
    return _same_number(value, expected)


def _speed_candidate(
    rows: Sequence[dict[str, Any]], speed: float, *, system: str
) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if row["system"] == system
        and not row["has_fault"]
        and _speed_matches(row.get("standard_speed_mps") or row.get("speed_mps"), speed)
        and row.get("table") in {None, "5.2"}
    ]


def _verdict(candidate: Any, baseline: Any, *, higher_is_better: bool = False) -> str:
    candidate_number = _number(candidate)
    baseline_number = _number(baseline)
    if candidate_number is None or baseline_number is None:
        return NOT_MEASURED
    if math.isclose(candidate_number, baseline_number, rel_tol=0.0, abs_tol=1.0e-12):
        return "TIE"
    won = candidate_number > baseline_number if higher_is_better else candidate_number < baseline_number
    return "S4_WIN" if won else "ORIGINAL_WIN"


def _edge_text(line_ids: Sequence[int]) -> str:
    return ",".join(
        f"{edge[0]}->{edge[1]}" for edge in _expected_fault_edges(line_ids)
    )


def _mapping_basis(line_ids: Sequence[int]) -> str:
    basis = ",".join(
        f"{line_id}:"
        + (
            "69_EDGE_RECONSTRUCTION"
            if line_id in RECONSTRUCTED_69_EDGE_LINE_IDS
            else "STRONG_MAPPING"
        )
        for line_id in line_ids
    )
    if tuple(sorted(line_ids)) == PAIR_5_7_LINE_IDS:
        return basis + ";ARCHIVED_WORKBOOK_LABEL_SOURCE_PROTOCOL_UNRESOLVED"
    return basis


def _table_5_2(hca: Sequence[dict[str, Any]], s4: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for archived in PAPER_TABLE_5_2:
        speed = float(archived["speed_mps"])
        hca_choice = _select_timing(
            _speed_candidate(hca, speed, system="HCA"),
            exact_field="exact_timing",
        )
        s4_choice = _select_timing(
            _speed_candidate(s4, speed, system="S4"),
            exact_field="exact_timing",
        )
        for statistic in ("min", "mean", "max"):
            paper_value = float(archived[statistic])
            hca_value = _path_get(hca_choice, ("timing", statistic)) if hca_choice else None
            s4_value = _path_get(s4_choice, ("timing", statistic)) if s4_choice else None
            rows.append(
                {
                    "table_id": "5.2",
                    "row_id": f"speed_{speed:.1f}_{statistic}",
                    "metric": f"tth_{statistic}_minutes",
                    "paper_evidence": EVIDENCE_ARCHIVED,
                    "paper_value": paper_value,
                    "hca_evidence": EVIDENCE_EXACT if hca_value is not None else NOT_MEASURED,
                    "hca_value": hca_value,
                    "s4_evidence": EVIDENCE_EXACT if s4_value is not None else NOT_MEASURED,
                    "s4_value": s4_value,
                    "measurement_status": "MEASURED" if s4_value is not None else NOT_MEASURED,
                    "speed_mps": speed,
                    "s4_vs_archived": _verdict(s4_value, paper_value),
                    "s4_vs_fresh_hca": _verdict(s4_value, hca_value),
                }
            )
    return rows


def _table_5_3(table_5_2: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    measured = {
        row["metric"]: row
        for row in table_5_2
        if _speed_matches(row.get("speed_mps"), 2.5)
    }
    rows: list[dict[str, Any]] = []
    for archived in PAPER_TABLE_5_3:
        for statistic in ("min", "mean", "max"):
            metric = f"tth_{statistic}_minutes"
            source = measured.get(metric, {})
            paper_value = float(archived[statistic])
            s4_value = source.get("s4_value") if archived["unit"] == "minutes" else None
            hca_value = source.get("hca_value") if archived["method"] == "iot_drpa_hca_star" else None
            rows.append(
                {
                    "table_id": "5.3",
                    "row_id": f"{archived['method']}_{statistic}",
                    "metric": statistic,
                    "method": archived["method"],
                    "unit": archived["unit"],
                    "paper_evidence": EVIDENCE_ARCHIVED,
                    "paper_value": paper_value,
                    "hca_evidence": EVIDENCE_EXACT if hca_value is not None else NOT_MEASURED,
                    "hca_value": hca_value,
                    "s4_evidence": EVIDENCE_EXACT if s4_value is not None else NOT_MEASURED,
                    "s4_value": s4_value,
                    "measurement_status": "MEASURED" if s4_value is not None else NOT_MEASURED,
                    "speed_mps": 2.5,
                    "s4_vs_archived": _verdict(s4_value, paper_value),
                    "s4_vs_fresh_hca": _verdict(s4_value, hca_value),
                }
            )
    return rows


def _table_5_4(s4: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for archived in PAPER_TABLE_5_4:
        standard = float(archived["standard_speed_mps"])
        deviation = int(archived["deviation_percent"])
        actual = standard * (1.0 - deviation / 100.0)
        nominal = _select(
            _speed_candidate(s4, standard, system="S4"),
            exact_field="exact_timing",
            value_path=("timing", "mean"),
        )
        degraded_candidates = [
            row
            for row in s4
            if row["system"] == "S4"
            and row.get("table") == "5.4"
            and _speed_matches(row.get("standard_speed_mps"), standard)
            and row.get("deviation_percent") == deviation
            and _speed_matches(row.get("speed_mps"), actual)
        ]
        degraded = _select(
            degraded_candidates,
            exact_field="exact_timing",
            value_path=("timing", "mean"),
        )
        nominal_value = _path_get(nominal, ("timing", "mean")) if nominal else None
        degraded_value = _path_get(degraded, ("timing", "mean")) if degraded else None
        reconstructed = nominal_value is not None and degraded_value is not None
        rows.append(
            {
                "table_id": "5.4",
                "row_id": f"speed_{standard:.1f}_dev_{deviation}",
                "metric": "mean_tth_minutes",
                "paper_evidence": EVIDENCE_ARCHIVED,
                "paper_dynamic_value": archived["dynamic"],
                "paper_static_value": archived["static"],
                "paper_improvement_percent": archived["improvement"],
                "s4_evidence": EVIDENCE_RECONSTRUCTED if reconstructed else NOT_MEASURED,
                "measurement_status": "MEASURED" if reconstructed else NOT_MEASURED,
                "standard_speed_mps": standard,
                "actual_speed_mps": actual,
                "deviation_percent": deviation,
                "s4_nominal_value": nominal_value if reconstructed else None,
                "s4_degraded_value": degraded_value if reconstructed else None,
                "s4_degradation_delta": (
                    degraded_value - nominal_value if reconstructed else None
                ),
                "s4_vs_archived_dynamic": _verdict(
                    degraded_value if reconstructed else None,
                    archived["dynamic"],
                ),
                "s4_vs_archived_static": _verdict(
                    degraded_value if reconstructed else None,
                    archived["static"],
                ),
            }
        )
    return rows


def _fault_candidate(
    rows: Sequence[dict[str, Any]], line_ids: Sequence[int], *, system: str
) -> list[dict[str, Any]]:
    wanted = tuple(line_ids)
    # The archived workbook labels this row as 33->44,46->36 and caches
    # 13,939/28,506. A fresh run of that exact edge label produces 8,013,
    # the same count as the global 14->46,33->44 reconstruction. Because the
    # workbook contains only derived timing samples (no IDs/config/schedule),
    # neither fresh edge interpretation is protocol-identifiable.
    if wanted == PAIR_5_7_LINE_IDS:
        return []
    return [
        row
        for row in rows
        if row["system"] == system
        and row["has_fault"]
        and row.get("fault_protocol_matches_expected") is True
        and (system != "HCA" or row.get("fault_protocol_exact") is True)
        and tuple(row["line_ids"]) == wanted
        and row.get("table") in {None, "5.5"}
    ]


def _table_5_5(hca: Sequence[dict[str, Any]], s4: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for archived in PAPER_TABLE_5_5:
        line_ids = tuple(archived["line_ids"])
        hca_choice = _select(
            _fault_candidate(hca, line_ids, system="HCA"),
            exact_field="exact_cohort",
            value_path=("success", "primary"),
        )
        s4_candidates = _fault_candidate(s4, line_ids, system="S4")
        fixed_candidates = [row for row in s4_candidates if row.get("exact_cohort")]
        fixed_choice = _select(
            s4_candidates,
            exact_field="exact_cohort",
            value_path=("success", "primary"),
        )
        topology_choice = (
            None
            if fixed_candidates
            else _select(
                s4_candidates,
                exact_field="topology_proven",
                value_path=("success", "primary"),
            )
        )
        s4_choice = fixed_choice or topology_choice
        hca_success = hca_choice["success"] if hca_choice else {}
        s4_success = s4_choice["success"] if s4_choice else {}
        primary = s4_success.get("primary")
        topology_evidence = topology_choice is not None
        secondary_status = (
            "CENSORED_NOT_MEASURED"
            if topology_evidence
            else "MEASURED"
            if fixed_choice
            and s4_success.get("finish_le_std") is not None
            and s4_success.get("finish_le_std_minus_2700") is not None
            else NOT_MEASURED
        )
        rows.append(
            {
                "table_id": "5.5",
                "row_id": archived["scenario_id"],
                "metric": "baggage_success_rate",
                "paper_evidence": EVIDENCE_ARCHIVED,
                "paper_value": archived["success_rate"],
                "affected_conveyors": archived["affected_conveyors"],
                "line_ids": ",".join(str(value) for value in line_ids),
                "reconstructed_edges": _edge_text(line_ids),
                "global_line_mapping_edges": ",".join(
                    f"{INTERRUPTION_EDGE_BY_ID[line_id][0]}->"
                    f"{INTERRUPTION_EDGE_BY_ID[line_id][1]}"
                    for line_id in line_ids
                ),
                "mapping_evidence": EVIDENCE_RECONSTRUCTED,
                "mapping_basis": _mapping_basis(line_ids),
                "case_specific_override": line_ids == PAIR_5_7_LINE_IDS,
                "mapping_source_inconsistency": line_ids == PAIR_5_7_LINE_IDS,
                "fresh_protocol_status": (
                    PAIR_5_7_FRESH_PROTOCOL_STATUS
                    if line_ids == PAIR_5_7_LINE_IDS
                    else "FRESH_PROTOCOL_IDENTIFIED"
                ),
                "contains_69_edge_reconstruction": any(
                    line_id in RECONSTRUCTED_69_EDGE_LINE_IDS
                    for line_id in line_ids
                ),
                "hca_evidence": EVIDENCE_EXACT if hca_choice else NOT_MEASURED,
                "hca_primary_success": hca_success.get("primary"),
                "s4_evidence": (
                    EVIDENCE_EXACT
                    if fixed_choice
                    else EVIDENCE_TOPOLOGY
                    if topology_choice
                    else NOT_MEASURED
                ),
                "s4_primary_success": primary,
                "s4_finish_le_std": (
                    s4_success.get("finish_le_std") if fixed_choice else None
                ),
                "s4_finish_le_std_minus_2700": (
                    s4_success.get("finish_le_std_minus_2700")
                    if fixed_choice
                    else None
                ),
                "s4_secondary_status": secondary_status,
                "s4_admission_mode": s4_choice.get("admission_mode") if s4_choice else None,
                "s4_topology_reachable_raw_bag_upper_bound": (
                    s4_choice.get("topology_reachable_raw_bag_upper_bound")
                    if topology_choice
                    else None
                ),
                "s4_topology_safety_pass": (
                    s4_choice.get("topology_safety_pass")
                    if topology_choice
                    else None
                ),
                "s4_business_failed_raw_bags": (
                    s4_choice.get("business_failed_raw_bags") if s4_choice else None
                ),
                "s4_business_failure_is_safety_failure": (
                    s4_choice.get("business_failure_is_safety_failure")
                    if s4_choice
                    else None
                ),
                "measurement_status": "MEASURED" if s4_choice else NOT_MEASURED,
                "s4_vs_archived": _verdict(
                    primary,
                    archived["success_rate"],
                    higher_is_better=True,
                ),
                "s4_vs_fresh_hca": _verdict(
                    primary,
                    hca_success.get("primary"),
                    higher_is_better=True,
                ),
                "s4_vs_fresh_hca_evidence": (
                    EVIDENCE_PROTOCOL_CONTROLLED
                    if s4_choice and hca_choice
                    else NOT_MEASURED
                ),
                "s4_vs_fresh_hca_release_pairing": (
                    "SAME_CANONICAL_POPULATION_AND_FIXED_DENOMINATOR_"
                    "NOT_SEGMENT_RELEASE_PAIRED"
                    if s4_choice and hca_choice
                    else NOT_MEASURED
                ),
            }
        )
    return rows


def build_report_payload(
    *,
    hca_payloads: Sequence[Mapping[str, Any]] = (),
    s4_payloads: Sequence[Mapping[str, Any]] = (),
    input_paths: Sequence[str] = (),
) -> dict[str, Any]:
    hca, s4 = extract_measurements(hca_payloads, s4_payloads)
    table_5_2 = _table_5_2(hca, s4)
    table_5_3 = _table_5_3(table_5_2)
    table_5_4 = _table_5_4(s4)
    table_5_5 = _table_5_5(hca, s4)
    flat_rows = [*table_5_2, *table_5_3, *table_5_4, *table_5_5]

    def comparison_counts(keys: set[str]) -> dict[str, int]:
        verdicts = [
            value
            for row in flat_rows
            for key, value in row.items()
            if key in keys
        ]
        return {
            "cell_count": len(verdicts),
            "measured_cell_count": sum(value != NOT_MEASURED for value in verdicts),
            "not_measured_cell_count": sum(
                value == NOT_MEASURED for value in verdicts
            ),
            "s4_win_count": sum(value == "S4_WIN" for value in verdicts),
            "original_win_count": sum(value == "ORIGINAL_WIN" for value in verdicts),
            "tie_count": sum(value == "TIE" for value in verdicts),
        }

    def outcome_counts(
        rows: Sequence[Mapping[str, Any]], verdict_key: str
    ) -> dict[str, int]:
        verdicts = [row.get(verdict_key, NOT_MEASURED) for row in rows]
        return {
            "cell_count": len(verdicts),
            "measured_cell_count": sum(value != NOT_MEASURED for value in verdicts),
            "not_measured_cell_count": sum(
                value == NOT_MEASURED for value in verdicts
            ),
            "s4_win_count": sum(value == "S4_WIN" for value in verdicts),
            "original_win_count": sum(value == "ORIGINAL_WIN" for value in verdicts),
            "tie_count": sum(value == "TIE" for value in verdicts),
        }

    table_5_2_mean = [
        row for row in table_5_2 if row.get("metric") == "tth_mean_minutes"
    ]
    outcome_summary = {
        "table_5_2_mean_vs_fresh_hca": outcome_counts(
            table_5_2_mean, "s4_vs_fresh_hca"
        ),
        "table_5_4_vs_archived_dynamic": outcome_counts(
            table_5_4, "s4_vs_archived_dynamic"
        ),
        "table_5_4_vs_archived_static": outcome_counts(
            table_5_4, "s4_vs_archived_static"
        ),
        "table_5_5_vs_fresh_hca": outcome_counts(
            table_5_5, "s4_vs_fresh_hca"
        ),
    }

    return {
        "schema": SCHEMA,
        "evidence_classes": {
            EVIDENCE_EXACT: "current canonical-cohort result admitted by the table-appropriate safety gate",
            EVIDENCE_RECONSTRUCTED: "derived only from named exact runs or the registered line mapping",
            EVIDENCE_TOPOLOGY: "Table 5.5 primary success reconstructed from a saturated directed-topology upper bound",
            EVIDENCE_PROTOCOL_CONTROLLED: "Table 5.5 S4-versus-HCA comparison on one canonical population and fixed denominator, without exact per-segment fault-release pairing",
            EVIDENCE_ARCHIVED: "paper-reported constant; not a current runtime result",
            NOT_MEASURED: "required runtime evidence is absent or incomplete",
        },
        "protocol": {
            "canonical_segment_count": CANONICAL_SEGMENTS,
            "canonical_raw_bag_count": CANONICAL_RAW_BAGS,
            "tth_denominator": "sum_over_segments(finish_time-admitted_time)",
            "repeat_policy": {
                "table_5_2": {
                    "fresh_hca_independent_java_process_repeats_per_speed": 2,
                    "s4_repeats_per_cell": 1,
                },
                "table_5_4": {"s4_repeats_per_cell": 1},
                "table_5_5": {
                    "fresh_hca_repeats_per_executable_scenario": 1,
                    "s4_repeats_per_executable_scenario": 1,
                },
                "superseded_probe_policy": (
                    "early_censored_or_truncated_probes_are_replaced_by_the_"
                    "formal_rerun_and_are_not_counted_as_repeats"
                ),
            },
            "interruption_success": {
                "primary": "completed_raw_bags/28506",
                "secondary": "finish_time<=STD",
                "literal": "finish_time<=STD-2700",
                "topology_proven_scope": "primary only; timing and deadline views are censored and NOT_MEASURED",
                "fresh_hca_comparison_scope": (
                    "protocol-controlled reconstruction on the same canonical input "
                    "and 28506 denominator; S4 uses the registered 2.5 m/s no-fault "
                    "release trace while faulted HCA realizes its own partial release, "
                    "so this is not an exact per-segment release-paired comparison"
                ),
                "pair_5_7_override": (
                    "archived workbook case-specific 33->44,46->36; "
                    "fresh exact-label run yielded 8013/28506 rather than "
                    "the cached 13939/28506, so the row is archived-only "
                    "and not a global line-5 remap"
                ),
            },
            "winner_rule": "computed cell by cell; missing or incomplete evidence is NOT_MEASURED",
            "input_paths": list(input_paths),
        },
        "tables": {
            "5.2": table_5_2,
            "5.3": table_5_3,
            "5.4": table_5_4,
            "5.5": table_5_5,
        },
        "summary": {
            "row_count": len(flat_rows),
            "measured_row_count": sum(row.get("measurement_status") == "MEASURED" for row in flat_rows),
            "not_measured_row_count": sum(row.get("measurement_status") == NOT_MEASURED for row in flat_rows),
            "comparison_counts": {
                "s4_vs_paper": comparison_counts(
                    {
                        "s4_vs_archived",
                        "s4_vs_archived_dynamic",
                        "s4_vs_archived_static",
                    }
                ),
                "s4_vs_fresh_hca": comparison_counts({"s4_vs_fresh_hca"}),
            },
            "outcome_summary": outcome_summary,
            "topology_proven_row_count": sum(
                row.get("s4_evidence") == EVIDENCE_TOPOLOGY for row in flat_rows
            ),
        },
    }


CSV_FIELDS = (
    "table_id",
    "row_id",
    "metric",
    "method",
    "unit",
    "measurement_status",
    "paper_evidence",
    "paper_value",
    "paper_dynamic_value",
    "paper_static_value",
    "paper_improvement_percent",
    "hca_evidence",
    "hca_value",
    "hca_primary_success",
    "s4_evidence",
    "s4_value",
    "s4_nominal_value",
    "s4_degraded_value",
    "s4_degradation_delta",
    "s4_primary_success",
    "s4_finish_le_std",
    "s4_finish_le_std_minus_2700",
    "s4_secondary_status",
    "s4_admission_mode",
    "s4_topology_reachable_raw_bag_upper_bound",
    "s4_topology_safety_pass",
    "s4_business_failed_raw_bags",
    "s4_business_failure_is_safety_failure",
    "speed_mps",
    "standard_speed_mps",
    "actual_speed_mps",
    "deviation_percent",
    "line_ids",
    "reconstructed_edges",
    "global_line_mapping_edges",
    "affected_conveyors",
    "mapping_evidence",
    "mapping_basis",
    "case_specific_override",
    "mapping_source_inconsistency",
    "fresh_protocol_status",
    "contains_69_edge_reconstruction",
    "s4_vs_archived",
    "s4_vs_fresh_hca",
    "s4_vs_fresh_hca_evidence",
    "s4_vs_fresh_hca_release_pairing",
    "s4_vs_archived_dynamic",
    "s4_vs_archived_static",
)


def csv_text(payload: Mapping[str, Any]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for table_id in ("5.2", "5.3", "5.4", "5.5"):
        writer.writerows(payload["tables"][table_id])
    return stream.getvalue()


def _display(value: Any, digits: int = 4) -> str:
    if value is None:
        return NOT_MEASURED
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def markdown_report(payload: Mapping[str, Any]) -> str:
    tables = payload["tables"]
    outcomes = payload["summary"]["outcome_summary"]

    def outcome_line(label: str, counts: Mapping[str, int]) -> str:
        return (
            f"- {label}: S4 wins {counts['s4_win_count']}/"
            f"{counts['measured_cell_count']} measured; ties "
            f"{counts['tie_count']}; losses {counts['original_win_count']}; "
            f"NOT_MEASURED {counts['not_measured_cell_count']}."
        )

    lines = [
        "# G4IRSF26 paper experiment report",
        "",
        "Evidence labels are strict: `EXACT_FRESH` is a current canonical-cohort result "
        "admitted by its table-appropriate safety gate, "
        "`RECONSTRUCTED` combines named exact runs or the registered line mapping, and "
        "`TOPOLOGY_PROVEN_RECONSTRUCTION` is limited to a topology-saturated Table 5.5 "
        "primary rate. `ARCHIVED` is a paper value. Missing evidence is `NOT_MEASURED`.",
        "",
        "The interruption primary success rate is `completed raw bags / 28,506`. "
        "`finish <= STD` and `finish <= STD - 2700` are secondary views.",
        "",
        "Repeat policy: Table 5.2 fresh HCA uses two independent Java-process repeats "
        "per speed, while S4 uses one run per Table 5.2 cell. Table 5.4 uses one S4 "
        "run per cell. Table 5.5 uses one fresh HCA and one S4 run per executable "
        "scenario. Early censored or truncated probes were superseded by their formal "
        "reruns and are not counted as repeats.",
        "",
        "## Outcome summary",
        "",
        outcome_line(
            "Table 5.2 mean vs fresh HCA",
            outcomes["table_5_2_mean_vs_fresh_hca"],
        ),
        outcome_line(
            "Table 5.4 vs archived dynamic",
            outcomes["table_5_4_vs_archived_dynamic"],
        ),
        outcome_line(
            "Table 5.4 vs archived static",
            outcomes["table_5_4_vs_archived_static"],
        ),
        outcome_line(
            "Table 5.5 vs fresh HCA",
            outcomes["table_5_5_vs_fresh_hca"],
        ),
        "",
        "S4 does not win every paper experiment.",
        "",
        "## Table 5.2 — speed",
        "",
        "| Speed | Metric | Paper | Fresh HCA | Fresh S4 | S4 vs paper | S4 vs HCA |",
        "|---:|---|---:|---:|---:|---|---|",
    ]
    for row in tables["5.2"]:
        lines.append(
            f"| {row['speed_mps']:.1f} | {row['metric']} | {_display(row['paper_value'])} | "
            f"{_display(row['hca_value'])} | {_display(row['s4_value'])} | "
            f"{row['s4_vs_archived']} | {row['s4_vs_fresh_hca']} |"
        )
    lines.extend(
        [
            "",
            "## Table 5.3 — archived algorithms",
            "",
            "| Method | Metric | Paper | Fresh HCA | Fresh S4 | S4 vs paper |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in tables["5.3"]:
        lines.append(
            f"| {row['method']} | {row['metric']} ({row['unit']}) | {_display(row['paper_value'])} | "
            f"{_display(row['hca_value'])} | {_display(row['s4_value'])} | {row['s4_vs_archived']} |"
        )
    lines.extend(
        [
            "",
            "## Table 5.4 — two-speed reconstruction",
            "",
            "Each cell requires both the exact nominal Table 5.2 run and the exact degraded-speed run.",
            "",
            "| Standard | Actual | Deviation | Paper dynamic | Paper static | S4 nominal | S4 degraded | Evidence | S4 vs archived dynamic | S4 vs archived static |",
            "|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
        ]
    )
    for row in tables["5.4"]:
        lines.append(
            f"| {row['standard_speed_mps']:.1f} | {row['actual_speed_mps']:.3f} | {row['deviation_percent']}% | "
            f"{_display(row['paper_dynamic_value'])} | {_display(row['paper_static_value'])} | "
            f"{_display(row['s4_nominal_value'])} | {_display(row['s4_degraded_value'])} | "
            f"{row['s4_evidence']} | {row['s4_vs_archived_dynamic']} | "
            f"{row['s4_vs_archived_static']} |"
        )
    lines.extend(
        [
            "",
            "## Table 5.5 — interruptions",
            "",
            "Line IDs 1, 6, and 7 use explicit 69-edge reconstruction mappings. "
            "`pair_5_7` alone follows the archived workbook sheet `33-44,46-36`; "
            "an exact-label fresh HCA run produced 8,013/28,506 rather than the "
            "cached 13,939/28,506, so this source-inconsistent row is archived-only "
            "and cannot produce a fresh verdict. It is not a global line remap. "
            "For topology-proven rows, both secondary deadline views are censored and remain `NOT_MEASURED`.",
            "Fresh HCA verdicts in this table are `PROTOCOL_CONTROLLED_RECONSTRUCTION`: "
            "both arms use the same canonical input and fixed 28,506-bag denominator, but "
            "S4 uses the registered 2.5 m/s no-fault release trace while faulted HCA "
            "realizes its own (possibly partial) release stream. They are not exact "
            "per-segment release-paired comparisons.",
            "",
            "| Scenario | Reconstructed edge(s) | Paper | Fresh HCA primary | Fresh S4 primary | S4 evidence | S4 <= STD | S4 literal | Secondary status | S4 vs paper | S4 vs fresh HCA | HCA comparison evidence |",
            "|---|---|---:|---:|---:|---|---:|---:|---|---|---|---|",
        ]
    )
    for row in tables["5.5"]:
        lines.append(
            f"| {row['row_id']} | {row['reconstructed_edges']} | {_display(row['paper_value'])} | "
            f"{_display(row['hca_primary_success'])} | {_display(row['s4_primary_success'])} | "
            f"{row['s4_evidence']} | {_display(row['s4_finish_le_std'])} | "
            f"{_display(row['s4_finish_le_std_minus_2700'])} | {row['s4_secondary_status']} | "
            f"{row['s4_vs_archived']} | {row['s4_vs_fresh_hca']} | "
            f"{row['s4_vs_fresh_hca_evidence']} |"
        )
    lines.extend(
        [
            "",
            "## Claim boundary",
            "",
            "Every S4 verdict above is calculated from the value in that cell. The report does not assume "
            "that S4 wins all cells. Archived, exact, topology-proven, and reconstructed values remain separate.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ReportingError(f"JSON root must be an object: {path}")
    return payload


def _input_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        raise ReportingError(f"input does not exist: {path}")
    s4_aggregate = path / "g4irsf26_paper_experiments.json"
    if s4_aggregate.exists():
        return [s4_aggregate]
    metrics = sorted(path.rglob("metrics.json"))
    if metrics:
        return metrics
    hca_campaigns = sorted(path.rglob("fresh_hca_summary.json"))
    if hca_campaigns:
        return hca_campaigns
    return sorted(path.glob("*.json"))


def _speed_from_evidence_path(path: Path) -> float | None:
    for part in reversed(path.parts):
        match = re.fullmatch(r"speed_(\d+)(?:p(\d+))?", part.lower())
        if match:
            decimal = match.group(2)
            return float(
                match.group(1) if decimal is None else f"{match.group(1)}.{decimal}"
            )
    return None


def _with_hca_status(payload: Mapping[str, Any], path: Path) -> Mapping[str, Any]:
    path_speed = _speed_from_evidence_path(path)
    if path.name == "metrics.json":
        status_path = path.with_name("run_status.json")
        if status_path.exists():
            status = _read_json(status_path)
            return {
                **payload,
                "speed_mps": status.get("speed_mps")
                or payload.get("speed_mps")
                or path_speed,
                "fault_schedule": status.get(
                    "fault_schedule", payload.get("fault_schedule")
                ),
            }
    if str(payload.get("schema", "")).endswith("fresh_hca.campaign.v1"):
        enriched = dict(payload)
        runs: list[Any] = []
        for run in payload.get("runs", []):
            if not isinstance(run, Mapping):
                runs.append(run)
                continue
            run_id = str(run.get("run_id", ""))
            status_path = path.parent / run_id / "run_status.json"
            if status_path.exists():
                status = _read_json(status_path)
                runs.append(
                    {
                        **run,
                        "speed_mps": status.get("speed_mps")
                        or run.get("speed_mps")
                        or path_speed,
                        "fault_schedule": status.get(
                            "fault_schedule", run.get("fault_schedule")
                        ),
                    }
                )
            else:
                runs.append(dict(run))
        enriched["runs"] = runs
        return enriched
    return payload


def load_payloads(
    paths: Sequence[Path], *, enrich_hca: bool = False
) -> tuple[list[Mapping[str, Any]], list[str]]:
    payloads: list[Mapping[str, Any]] = []
    loaded_paths: list[str] = []
    seen: set[str] = set()
    for supplied in paths:
        resolved = supplied if supplied.is_absolute() else ROOT / supplied
        for path in _input_files(resolved.resolve()):
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            payload = _read_json(path)
            payloads.append(_with_hca_status(payload, path) if enrich_hca else payload)
            try:
                loaded_paths.append(path.resolve().relative_to(ROOT).as_posix())
            except ValueError:
                loaded_paths.append(str(path.resolve()))
    return payloads, loaded_paths


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hca-input", action="append", type=Path, default=[])
    parser.add_argument("--s4-input", action="append", type=Path, default=[])
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--output-report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    s4_inputs = list(args.s4_input)
    if not s4_inputs and DEFAULT_S4_INPUT.exists():
        s4_inputs.append(DEFAULT_S4_INPUT)
    hca_payloads, hca_paths = load_payloads(args.hca_input, enrich_hca=True)
    s4_payloads, s4_paths = load_payloads(s4_inputs)
    payload = build_report_payload(
        hca_payloads=hca_payloads,
        s4_payloads=s4_payloads,
        input_paths=[*hca_paths, *s4_paths],
    )

    json_path = args.output_json if args.output_json.is_absolute() else ROOT / args.output_json
    csv_path = args.output_csv if args.output_csv.is_absolute() else ROOT / args.output_csv
    report_path = args.output_report if args.output_report.is_absolute() else ROOT / args.output_report
    _write(json_path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n")
    _write(csv_path, csv_text(payload))
    _write(report_path, markdown_report(payload))
    print(
        json.dumps(
            {
                "status": "PASS",
                "rows": payload["summary"]["row_count"],
                "measured": payload["summary"]["measured_row_count"],
                "json": str(json_path),
                "csv": str(csv_path),
                "report": str(report_path),
            },
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
