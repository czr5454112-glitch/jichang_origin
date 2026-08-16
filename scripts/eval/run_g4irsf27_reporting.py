#!/usr/bin/env python3
"""Build the compact G27 line-interruption comparison artifacts."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "czr005.g4irsf27.fault_values_reporting.v1"
G27_CASE_SCHEMA = "czr005.g4irsf27.fault_local_values_case.v1"
G27_COMPLETE = "COMPLETE_G27_LOCAL_FAULT_VALUES"
CANONICAL_RAW_BAGS = 28_506
MEASURED = "MEASURED"
NOT_MEASURED = "NOT_MEASURED"

SCENARIO_IDS = (
    "single_1",
    "single_2",
    "single_3",
    "single_4",
    "single_5",
    "single_6",
    "single_7",
    "single_8",
    "pair_1_7",
    "pair_2_4",
    "pair_3_5",
    "pair_4_5",
    "pair_5_7",
    "triple_2_4_6",
    "triple_3_5_8",
    "triple_4_6_7",
)
MEASURABLE_SCENARIO_IDS = tuple(
    scenario_id for scenario_id in SCENARIO_IDS if scenario_id != "pair_5_7"
)

DEFAULT_G27_DIR = ROOT / "outputs/runtime/g4irsf27_fault_values"
DEFAULT_G26_REPORT = ROOT / "outputs/tables/g4irsf26_reporting.json"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf27_fault_values.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf27_fault_values.csv"
DEFAULT_MARKDOWN = ROOT / "outputs/reports/g4irsf27_fault_values.md"
DEFAULT_FIFO_JSON = ROOT / "outputs/tables/g4irsf27_fifo_speed.json"
DEFAULT_FIFO_CSV = ROOT / "outputs/tables/g4irsf27_fifo_speed.csv"
DEFAULT_FIFO_MARKDOWN = ROOT / "outputs/reports/g4irsf27_fifo_speed.md"
DEFAULT_BIAS_JSON = ROOT / "outputs/tables/g4irsf27_bias_experiments.json"
DEFAULT_DECISION_JSON = ROOT / "outputs/tables/g4irsf27_decision_summary.json"
DEFAULT_DECISION_MARKDOWN = ROOT / "outputs/reports/g4irsf27_final_joint_decision.md"

FIFO_SPEED_CASES = (
    ("t5_2_speed_1p5", 1.5, "speed_1.5"),
    ("t5_2_speed_2", 2.0, "speed_2.0"),
    ("t5_2_speed_2p5", 2.5, "speed_2.5"),
    ("t5_2_speed_3", 3.0, "speed_3.0"),
)
FIFO_EXACT_OFF = "FAULT_VALUES_DLP_EXACT_OFF_NO_FAULT_CASE"
PAPER_MIN_HALF_REPORTED_UNIT_MINUTES = 0.005
FRESH_MIN_CLOCK_RESOLUTION_MINUTES = 0.0021 / 60.0


class ReportingError(RuntimeError):
    pass


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReportingError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ReportingError(f"{label} must be a list")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReportingError(f"{label} must be an integer")
    number = int(value)
    if number != value:
        raise ReportingError(f"{label} must be an integer")
    return number


def _rate(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReportingError(f"{label} must be a rate")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ReportingError(f"{label} must be between zero and one")
    return number


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReportingError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ReportingError(f"{label} must be finite")
    return number


def _path(value: Mapping[str, Any], *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _rate_to_raw(rate: float) -> int:
    """Convert a displayed rate to one canonical integer numerator."""
    return int(
        (Decimal(str(rate)) * Decimal(CANONICAL_RAW_BAGS)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _verdict(g27_raw: int, reference_raw: int) -> str:
    if g27_raw > reference_raw:
        return "G27_WIN"
    if g27_raw < reference_raw:
        return "ORIGINAL_WIN"
    return "TIE"


def _counts(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    verdicts = [str(row[key]) for row in rows if row[key] != NOT_MEASURED]
    return {
        "cell_count": len(rows),
        "measured_cell_count": len(verdicts),
        "not_measured_cell_count": len(rows) - len(verdicts),
        "g27_win_count": verdicts.count("G27_WIN"),
        "tie_count": verdicts.count("TIE"),
        "original_win_count": verdicts.count("ORIGINAL_WIN"),
    }


def _index_g26(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    denominator = _integer(
        _path(payload, "protocol", "canonical_raw_bag_count"),
        "G26 canonical_raw_bag_count",
    )
    if denominator != CANONICAL_RAW_BAGS:
        raise ReportingError("G26 report does not use the canonical 28506-bag denominator")
    table = _list(_path(payload, "tables", "5.5"), "G26 table 5.5")
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in table:
        row = _mapping(item, "G26 table 5.5 row")
        row_id = str(row.get("row_id", ""))
        if row_id in indexed:
            raise ReportingError(f"duplicate G26 row: {row_id}")
        indexed[row_id] = row
    missing = [scenario_id for scenario_id in SCENARIO_IDS if scenario_id not in indexed]
    if missing:
        raise ReportingError(f"missing G26 table 5.5 rows: {', '.join(missing)}")
    return indexed


def _index_g27(payloads: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for payload in payloads:
        case_id = str(_path(payload, "case", "case_id") or "")
        prefix = "t5_5_fault_"
        if not case_id.startswith(prefix):
            raise ReportingError(f"unexpected G27 case id: {case_id or '<missing>'}")
        scenario_id = case_id[len(prefix) :]
        if scenario_id in indexed:
            raise ReportingError(f"duplicate G27 case: {scenario_id}")
        indexed[scenario_id] = payload
    missing = [
        scenario_id
        for scenario_id in MEASURABLE_SCENARIO_IDS
        if scenario_id not in indexed
    ]
    if missing:
        raise ReportingError(f"missing required G27 cases: {', '.join(missing)}")
    extras = sorted(set(indexed) - set(MEASURABLE_SCENARIO_IDS))
    if extras:
        raise ReportingError(f"unexpected G27 cases: {', '.join(extras)}")
    return indexed


def _measured_row(
    scenario_id: str,
    g26: Mapping[str, Any],
    g27: Mapping[str, Any],
) -> dict[str, Any]:
    if g26.get("measurement_status") != MEASURED:
        raise ReportingError(f"G26 row {scenario_id} is not measured")
    if g27.get("schema") != G27_CASE_SCHEMA or g27.get("status") != G27_COMPLETE:
        raise ReportingError(f"G27 case {scenario_id} is not an admitted complete result")
    if _path(g27, "safety", "admission", "pass") is not True:
        raise ReportingError(f"G27 case {scenario_id} did not pass admission")

    paper_rate = _rate(g26.get("paper_value"), f"{scenario_id} paper rate")
    hca_rate = _rate(g26.get("hca_primary_success"), f"{scenario_id} HCA rate")
    g26_rate = _rate(g26.get("s4_primary_success"), f"{scenario_id} G26 S4 rate")
    paper_raw = _rate_to_raw(paper_rate)
    hca_raw = _rate_to_raw(hca_rate)
    g26_raw = _rate_to_raw(g26_rate)

    g27_raw = _integer(
        _path(g27, "outcome", "completed_raw_bag_count"),
        f"{scenario_id} G27 completed_raw_bag_count",
    )
    success_raw = _integer(
        _path(g27, "outcome", "success", "primary_completed_raw_bags", "count"),
        f"{scenario_id} G27 primary count",
    )
    g27_rate = _rate(
        _path(g27, "outcome", "success", "primary_completed_raw_bags", "rate"),
        f"{scenario_id} G27 primary rate",
    )
    topology_upper = _integer(
        _path(g27, "outcome", "topology_reachable_raw_bag_upper_bound"),
        f"{scenario_id} topology upper bound",
    )
    selected = _integer(
        _path(g27, "outcome", "selected_raw_bag_count"),
        f"{scenario_id} selected_raw_bag_count",
    )
    source_rejected = _integer(
        _path(g27, "outcome", "source_rejected_unreachable_segment_count"),
        f"{scenario_id} source-rejected segment count",
    )
    if selected != CANONICAL_RAW_BAGS:
        raise ReportingError(f"G27 case {scenario_id} uses the wrong denominator")
    if not (g27_raw == success_raw == _rate_to_raw(g27_rate)):
        raise ReportingError(f"G27 case {scenario_id} has inconsistent primary success")
    if not 0 <= g27_raw <= topology_upper <= CANONICAL_RAW_BAGS:
        raise ReportingError(f"G27 case {scenario_id} has invalid topology accounting")

    return {
        "scenario_id": scenario_id,
        "measurement_status": MEASURED,
        "line_ids": g26.get("line_ids"),
        "paper_completed_raw": paper_raw,
        "paper_rate": paper_rate,
        "fresh_hca_completed_raw": hca_raw,
        "fresh_hca_rate": hca_rate,
        "g26_s4_completed_raw": g26_raw,
        "g26_s4_rate": g26_rate,
        "g27_completed_raw": g27_raw,
        "g27_rate": g27_rate,
        "g27_business_failed_raw": CANONICAL_RAW_BAGS - g27_raw,
        "g27_source_rejected_unreachable_segment_count": source_rejected,
        "g27_topology_reachable_raw_bag_upper_bound": topology_upper,
        "g27_reaches_topology_upper": g27_raw == topology_upper,
        "g27_vs_fresh_hca": _verdict(g27_raw, hca_raw),
        "g27_vs_paper": _verdict(g27_raw, paper_raw),
    }


def build_report_payload(
    g26_payload: Mapping[str, Any],
    g27_payloads: Sequence[Mapping[str, Any]],
    *,
    input_paths: Sequence[str] = (),
) -> dict[str, Any]:
    g26_by_id = _index_g26(g26_payload)
    g27_by_id = _index_g27(g27_payloads)
    rows: list[dict[str, Any]] = []
    for scenario_id in SCENARIO_IDS:
        g26 = g26_by_id[scenario_id]
        if scenario_id == "pair_5_7":
            if g26.get("measurement_status") != NOT_MEASURED:
                raise ReportingError("G26 pair_5_7 must remain NOT_MEASURED")
            paper_rate = _rate(g26.get("paper_value"), "pair_5_7 paper rate")
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "measurement_status": NOT_MEASURED,
                    "line_ids": g26.get("line_ids"),
                    "paper_completed_raw": _rate_to_raw(paper_rate),
                    "paper_rate": paper_rate,
                    "fresh_hca_completed_raw": None,
                    "fresh_hca_rate": None,
                    "g26_s4_completed_raw": None,
                    "g26_s4_rate": None,
                    "g27_completed_raw": None,
                    "g27_rate": None,
                    "g27_business_failed_raw": None,
                    "g27_source_rejected_unreachable_segment_count": None,
                    "g27_topology_reachable_raw_bag_upper_bound": None,
                    "g27_reaches_topology_upper": None,
                    "g27_vs_fresh_hca": NOT_MEASURED,
                    "g27_vs_paper": NOT_MEASURED,
                    "gap_reason": g26.get("fresh_protocol_status"),
                }
            )
        else:
            rows.append(_measured_row(scenario_id, g26, g27_by_id[scenario_id]))

    measured = [row for row in rows if row["measurement_status"] == MEASURED]
    topology_count = sum(bool(row["g27_reaches_topology_upper"]) for row in measured)
    return {
        "schema": SCHEMA,
        "protocol": {
            "canonical_raw_bag_count": CANONICAL_RAW_BAGS,
            "comparison_evidence": "PROTOCOL_CONTROLLED_RECONSTRUCTION",
            "release_pairing": "SAME_CANONICAL_POPULATION_AND_FIXED_DENOMINATOR_NOT_SEGMENT_RELEASE_PAIRED",
            "paper_completed_raw_semantics": "nearest_integer_equivalent_of_archived_two_decimal_rate_on_28506_denominator",
            "winner_rule": "compare_integer_completed_raw_bag_numerators",
            "source_local_reject_semantics": "unreachable source-local segment rejection still makes its raw bag a business failure",
            "architecture_boundary": "decision-layer decentralized; scalar rounds orchestrated in one process, not a physical distributed deployment",
            "excluded_mechanisms": [
                "runtime_learning",
                "runtime_full_A_star",
                "global_route_reservation_table",
            ],
            "input_paths": list(input_paths),
        },
        "summary": {
            "row_count": len(rows),
            "measured_row_count": len(measured),
            "not_measured_row_count": len(rows) - len(measured),
            "g27_vs_fresh_hca": _counts(rows, "g27_vs_fresh_hca"),
            "g27_vs_paper": _counts(rows, "g27_vs_paper"),
            "topology_upper_reached_count": topology_count,
            "topology_upper_measured_count": len(measured),
            "all_measured_cases_reach_topology_upper": topology_count == len(measured),
        },
        "rows": rows,
    }


def discover_input_paths(directory: Path) -> tuple[list[Path], list[Path]]:
    """Keep fault evidence and no-fault FIFO controls in separate reports."""
    fault_paths = sorted(directory.glob("t5_5_fault_*_full.json"))
    fifo_paths = sorted(directory.glob("t5_2_speed_*_fifo_full.json"))
    return fault_paths, fifo_paths


def _speed_verdict(
    observed: float,
    reference: float,
    *,
    metric: str,
    min_tolerance: float,
) -> str:
    difference = observed - reference
    if metric == "min" and abs(difference) <= min_tolerance + 1e-12:
        return "RESOLUTION_BOUND_TIE"
    if difference < 0.0:
        return "G27_FIFO_WIN"
    if difference > 0.0:
        return "ORIGINAL_WIN"
    return "TIE"


def _speed_comparison_counts(
    rows: Sequence[Mapping[str, Any]], prefix: str
) -> dict[str, int]:
    verdicts = [
        str(row[f"fifo_{metric}_vs_{prefix}"])
        for row in rows
        for metric in ("min", "mean", "max")
    ]
    return {
        "cell_count": len(verdicts),
        "g27_fifo_win_count": verdicts.count("G27_FIFO_WIN"),
        "tie_count": verdicts.count("TIE")
        + verdicts.count("RESOLUTION_BOUND_TIE"),
        "resolution_bound_tie_count": verdicts.count("RESOLUTION_BOUND_TIE"),
        "original_win_count": verdicts.count("ORIGINAL_WIN"),
    }


def _index_fifo_speed(
    payloads: Sequence[Mapping[str, Any]],
) -> dict[str, Mapping[str, Any]]:
    indexed: dict[str, Mapping[str, Any]] = {}
    for payload in payloads:
        case_id = str(_path(payload, "case", "case_id") or "")
        if case_id in indexed:
            raise ReportingError(f"duplicate FIFO speed case: {case_id}")
        indexed[case_id] = payload
    expected = {case_id for case_id, _, _ in FIFO_SPEED_CASES}
    missing = sorted(expected - set(indexed))
    if missing:
        raise ReportingError(f"missing required FIFO speed cases: {', '.join(missing)}")
    extras = sorted(set(indexed) - expected)
    if extras:
        raise ReportingError(f"unexpected FIFO speed cases: {', '.join(extras)}")
    return indexed


def _index_g26_speed(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    table = _list(_path(payload, "tables", "5.2"), "G26 table 5.2")
    indexed: dict[str, Mapping[str, Any]] = {}
    for item in table:
        row = _mapping(item, "G26 table 5.2 row")
        row_id = str(row.get("row_id", ""))
        if row_id in indexed:
            raise ReportingError(f"duplicate G26 speed row: {row_id}")
        indexed[row_id] = row
    required = {
        f"{row_prefix}_{metric}"
        for _, _, row_prefix in FIFO_SPEED_CASES
        for metric in ("min", "mean", "max")
    }
    missing = sorted(required - set(indexed))
    if missing:
        raise ReportingError(f"missing G26 table 5.2 rows: {', '.join(missing)}")
    return indexed


def build_fifo_speed_payload(
    g26_payload: Mapping[str, Any],
    fifo_payloads: Sequence[Mapping[str, Any]],
    *,
    input_paths: Sequence[str] = (),
) -> dict[str, Any]:
    g26_by_id = _index_g26_speed(g26_payload)
    fifo_by_id = _index_fifo_speed(fifo_payloads)
    rows: list[dict[str, Any]] = []
    for case_id, speed, row_prefix in FIFO_SPEED_CASES:
        fifo = fifo_by_id[case_id]
        if fifo.get("schema") != G27_CASE_SCHEMA or fifo.get("status") != G27_COMPLETE:
            raise ReportingError(f"FIFO speed case {case_id} is not complete")
        if _path(fifo, "local_values", "activation") != FIFO_EXACT_OFF:
            raise ReportingError(f"FIFO speed case {case_id} did not keep fault values off")
        completed = _integer(
            _path(fifo, "outcome", "completed_raw_bag_count"),
            f"{case_id} completed_raw_bag_count",
        )
        if completed != CANONICAL_RAW_BAGS:
            raise ReportingError(f"FIFO speed case {case_id} is not canonical-complete")
        observed_speed = _number(
            _path(fifo, "case", "standard_speed_mps"), f"{case_id} speed"
        )
        if observed_speed != speed:
            raise ReportingError(f"FIFO speed case {case_id} has the wrong speed")
        distribution = _mapping(
            _path(fifo, "outcome", "paper_raw_bag_tth", "distribution", "minutes"),
            f"{case_id} minute distribution",
        )
        row: dict[str, Any] = {
            "case_id": case_id,
            "speed_mps": speed,
            "completed_raw_bags": completed,
            "fault_values_activation": FIFO_EXACT_OFF,
        }
        for metric in ("min", "mean", "p95", "p99", "max"):
            row[f"fifo_{metric}_minutes"] = _number(
                distribution.get(metric), f"{case_id} {metric}"
            )
        for metric in ("min", "mean", "max"):
            reference = g26_by_id[f"{row_prefix}_{metric}"]
            if reference.get("measurement_status") != MEASURED:
                raise ReportingError(f"G26 {row_prefix}_{metric} is not measured")
            paper = _number(reference.get("paper_value"), f"{case_id} paper {metric}")
            hca = _number(reference.get("hca_value"), f"{case_id} HCA {metric}")
            observed = float(row[f"fifo_{metric}_minutes"])
            row[f"paper_{metric}_minutes"] = paper
            row[f"fresh_hca_{metric}_minutes"] = hca
            row[f"fifo_{metric}_vs_paper"] = _speed_verdict(
                observed,
                paper,
                metric=metric,
                min_tolerance=PAPER_MIN_HALF_REPORTED_UNIT_MINUTES,
            )
            row[f"fifo_{metric}_vs_fresh_hca"] = _speed_verdict(
                observed,
                hca,
                metric=metric,
                min_tolerance=FRESH_MIN_CLOCK_RESOLUTION_MINUTES,
            )
        rows.append(row)

    return {
        "schema": "czr005.g4irsf27.fifo_speed_reporting.v1",
        "protocol": {
            "canonical_raw_bag_count": CANONICAL_RAW_BAGS,
            "control_semantics": "no-fault FIFO controls; G27 fault-local value layer is exact-off",
            "metrics_unit": "minutes",
            "winner_rule": "lower is better for min, mean, and max",
            "paper_min_resolution_bound_minutes": PAPER_MIN_HALF_REPORTED_UNIT_MINUTES,
            "fresh_min_clock_resolution_bound_minutes": FRESH_MIN_CLOCK_RESOLUTION_MINUTES,
            "resolution_bound_scope": "minimum cells only",
            "input_paths": list(input_paths),
        },
        "summary": {
            "speed_count": len(rows),
            "all_cases_canonical_complete": all(
                row["completed_raw_bags"] == CANONICAL_RAW_BAGS for row in rows
            ),
            "fifo_vs_fresh_hca": _speed_comparison_counts(rows, "fresh_hca"),
            "fifo_vs_paper": _speed_comparison_counts(rows, "paper"),
        },
        "rows": rows,
    }


def build_joint_decision_payload(
    fault: Mapping[str, Any],
    fifo: Mapping[str, Any],
    bias: Mapping[str, Any],
) -> dict[str, Any]:
    if fault.get("schema") != SCHEMA:
        raise ReportingError("unexpected G27 fault summary")
    if fifo.get("schema") != "czr005.g4irsf27.fifo_speed_reporting.v1":
        raise ReportingError("unexpected G27 FIFO speed summary")
    if bias.get("schema") != "czr005.g4irsf27.bias_report.v1":
        raise ReportingError("unexpected G27 bias summary")

    fifo_rows = [
        _mapping(row, "FIFO speed row") for row in _list(fifo.get("rows"), "FIFO rows")
    ]
    bias_rows = [
        _mapping(row, "bias row") for row in _list(bias.get("rows"), "bias rows")
    ]
    fault_rows = [
        _mapping(row, "fault row") for row in _list(fault.get("rows"), "fault rows")
    ]
    if len(fifo_rows) != 4 or len(bias_rows) != 12 or len(fault_rows) != 16:
        raise ReportingError("joint decision inputs are incomplete")

    fifo_summary = _mapping(fifo.get("summary"), "FIFO summary")
    fault_summary = _mapping(fault.get("summary"), "fault summary")
    fifo_vs_hca = _mapping(
        fifo_summary.get("fifo_vs_fresh_hca"), "FIFO versus HCA summary"
    )
    fifo_mean_wins = sum(
        row.get("fifo_mean_vs_fresh_hca") == "G27_FIFO_WIN" for row in fifo_rows
    )
    fifo_max_wins = sum(
        row.get("fifo_max_vs_fresh_hca") == "G27_FIFO_WIN" for row in fifo_rows
    )
    dynamic_wins = sum(
        row.get("status") == "COMPLETE"
        and _number(row.get("s4_minutes"), "bias S4 minutes")
        < _number(row.get("archived_dynamic_minutes"), "archived dynamic minutes")
        for row in bias_rows
    )
    static_wins = sum(
        row.get("status") == "COMPLETE"
        and _number(row.get("s4_minutes"), "bias S4 minutes")
        < _number(row.get("archived_static_minutes"), "archived static minutes")
        for row in bias_rows
    )
    pair_5_7 = next(
        (row for row in fault_rows if row.get("scenario_id") == "pair_5_7"), None
    )
    if pair_5_7 is None:
        raise ReportingError("joint decision is missing pair_5_7")

    return {
        "schema": "czr005.g4irsf27.final_joint_decision.v1",
        "status": "ADOPT_SIMPLE_G27_LOCAL_RESILIENCE",
        "active_policy": {
            "normal_operation": "S4/J2/E2+local FIFO",
            "persistent_pre_start_fault": "add local goal scalar",
            "bias_role": "experimental observation perturbation; not learning",
        },
        "table_5_2": {
            "scope": "FIFO no-fault exact-fresh controls versus fresh HCA and archived paper values",
            "min_mean_max_vs_fresh_hca": dict(fifo_vs_hca),
            "all_four_speed_means_win": fifo_mean_wins == len(fifo_rows),
            "all_four_speed_maxima_win": fifo_max_wins == len(fifo_rows),
            "mean_win_count": fifo_mean_wins,
            "max_win_count": fifo_max_wins,
        },
        "table_5_4": {
            "evidence": bias.get("protocol_fidelity"),
            "case_count": len(bias_rows),
            "s4_vs_archived_dynamic_win_count": dynamic_wins,
            "s4_vs_archived_static_win_count": static_wins,
            "exact_fresh_legacy_variant": bool(
                bias.get("exact_legacy_variant_recovered")
            ),
            "bias_is_learning": False,
        },
        "table_5_5": {
            "evidence": _path(fault, "protocol", "comparison_evidence"),
            "g27_vs_fresh_hca": dict(
                _mapping(
                    fault_summary.get("g27_vs_fresh_hca"),
                    "fault versus HCA summary",
                )
            ),
            "g27_vs_paper": dict(
                _mapping(
                    fault_summary.get("g27_vs_paper"),
                    "fault versus paper summary",
                )
            ),
            "all_measured_cases_reach_topology_upper": bool(
                fault_summary.get("all_measured_cases_reach_topology_upper")
            ),
            "pair_5_7_status": pair_5_7.get("measurement_status"),
        },
        "architecture_boundary": {
            "runtime_full_A_star": False,
            "future_route_materialization": False,
            "hca_global_reservation_table": False,
            "runtime_learning": False,
            "decentralization": "decision-layer decentralized",
            "deployment": "single-process simulator; not physical distributed deployment",
        },
        "decision_basis": {
            "keep_framework_simple": True,
            "route_scorer_and_j2_e2_framework_unchanged": True,
            "normal_queue_policy_changed_to_fifo": True,
            "fault_extension_activation_scope": "persistent pre-start faults only",
        },
    }


def render_joint_decision_markdown(payload: Mapping[str, Any]) -> str:
    table_52 = payload["table_5_2"]
    counts_52 = table_52["min_mean_max_vs_fresh_hca"]
    table_54 = payload["table_5_4"]
    table_55 = payload["table_5_5"]
    hca = table_55["g27_vs_fresh_hca"]
    paper = table_55["g27_vs_paper"]
    return "\n".join(
        [
            "# G27 最终联合决策",
            "",
            "## 决策",
            "",
            "采用保持简单的组合策略：正常运行继续使用 `S4/J2/E2 + local FIFO`；仅在持久、启动前已知的线路故障下，额外启用 local goal scalar。无需新增另一套规划框架。",
            "",
            "## 三组证据",
            "",
            f"- Table 5.2：FIFO 的 min/mean/max 对 fresh HCA 共 {counts_52['g27_fifo_win_count']} 胜、{counts_52['resolution_bound_tie_count']} 个分辨率边界平、{counts_52['original_win_count']} 负；四种速度的 mean 和 max 均胜。",
            f"- Table 5.4：在 `{table_54['evidence']}` 下，12 个场景对 archived dynamic 为 {table_54['s4_vs_archived_dynamic_win_count']}/12 胜，对 archived static 为 {table_54['s4_vs_archived_static_win_count']}/12 胜。这不是原缺失 legacy variant 的 exact fresh 复跑。",
            f"- Table 5.5：对 fresh HCA 为 {hca['g27_win_count']} 胜、{hca['tie_count']} 个拓扑上限平、{hca['original_win_count']} 负；对论文存档值为 {paper['g27_win_count']} 胜、{paper['tie_count']} 平、{paper['original_win_count']} 负。`pair_5_7` 仍为 `{table_55['pair_5_7_status']}`。",
            "",
            "## 口径与架构边界",
            "",
            "- Table 5.4 的 bias 是为重构论文观测偏差所做的实验扰动，不是 learning，也不作为在线学习模块启用。",
            "- Table 5.5 与 fresh HCA 仍属于 `PROTOCOL_CONTROLLED_RECONSTRUCTION`；达到拓扑上限的 source-local reject 仍按业务失败计入，不会被隐藏为成功。",
            "- 当前框架不调用运行时完整 A*，不生成行李未来完整路线，也不维护 HCA 全局预约表。",
            "- 它是决策层去中心化：每个转向点只做下一跳动作；当前证据来自单进程模拟器，不声称已经物理分布式部署。",
            "",
        ]
    )


CSV_FIELDS = (
    "scenario_id",
    "measurement_status",
    "line_ids",
    "paper_completed_raw",
    "paper_rate",
    "fresh_hca_completed_raw",
    "fresh_hca_rate",
    "g26_s4_completed_raw",
    "g26_s4_rate",
    "g27_completed_raw",
    "g27_rate",
    "g27_business_failed_raw",
    "g27_source_rejected_unreachable_segment_count",
    "g27_topology_reachable_raw_bag_upper_bound",
    "g27_reaches_topology_upper",
    "g27_vs_fresh_hca",
    "g27_vs_paper",
    "gap_reason",
)


def render_csv(payload: Mapping[str, Any]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for source in payload["rows"]:
        row = {field: source.get(field) for field in CSV_FIELDS}
        writer.writerow(row)
    return stream.getvalue()


def _cell(raw: Any, rate: Any) -> str:
    if raw is None or rate is None:
        return NOT_MEASURED
    return f"{raw}/{CANONICAL_RAW_BAGS} ({float(rate):.6f})"


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload["summary"]
    hca = summary["g27_vs_fresh_hca"]
    paper = summary["g27_vs_paper"]
    lines = [
        "# G27 故障局部势值实验汇总",
        "",
        f"15 个可测线路中断场景全部完成，G27 对 fresh HCA 为 {hca['g27_win_count']} 胜、{hca['tie_count']} 平、{hca['original_win_count']} 负；对论文存档值为 {paper['g27_win_count']} 胜、{paper['tie_count']} 平、{paper['original_win_count']} 负。",
        f"全部 {summary['topology_upper_reached_count']}/{summary['topology_upper_measured_count']} 个可测场景达到有向拓扑可达上界。`pair_5_7` 因原论文来源协议矛盾继续登记为 `NOT_MEASURED`。",
        "",
        "| 场景 | Paper completed/rate | Fresh HCA completed/rate | G26 S4 completed/rate | G27 completed/rate | G27 topology upper | vs HCA | vs paper |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {scenario_id} | {paper} | {hca} | {g26} | {g27} | {upper} | {vs_hca} | {vs_paper} |".format(
                scenario_id=row["scenario_id"],
                paper=_cell(row["paper_completed_raw"], row["paper_rate"]),
                hca=_cell(row["fresh_hca_completed_raw"], row["fresh_hca_rate"]),
                g26=_cell(row["g26_s4_completed_raw"], row["g26_s4_rate"]),
                g27=_cell(row["g27_completed_raw"], row["g27_rate"]),
                upper=(
                    row["g27_topology_reachable_raw_bag_upper_bound"]
                    if row["g27_topology_reachable_raw_bag_upper_bound"] is not None
                    else NOT_MEASURED
                ),
                vs_hca=row["g27_vs_fresh_hca"],
                vs_paper=row["g27_vs_paper"],
            )
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- source-local reject 不是成功规避：只要一个行李的任一段在源节点因不可达被拒绝，该原始行李仍计为业务失败。",
            "- 与 fresh HCA 的比较仍是 `PROTOCOL_CONTROLLED_RECONSTRUCTION`：使用相同 28,506 个原始行李和固定分母，但不是逐 segment 的故障 release 配对。",
            "- G27 是决策层去中心化；当前局部标量传播由单个 Python 进程编排，不能声称已经物理分布式部署。",
            "- G27 不使用运行时学习、不调用运行时完整 A*，也不维护全局路线预约表。",
            "- Paper completed raw 是论文两位小数成功率在 28,506 分母上的最近整数等价值，只用于整数胜负比较，不冒充论文未报告的原始计数。",
            "",
        ]
    )
    return "\n".join(lines)


FIFO_CSV_FIELDS = (
    "case_id",
    "speed_mps",
    "completed_raw_bags",
    "fifo_min_minutes",
    "fifo_mean_minutes",
    "fifo_p95_minutes",
    "fifo_p99_minutes",
    "fifo_max_minutes",
    "fresh_hca_min_minutes",
    "fresh_hca_mean_minutes",
    "fresh_hca_max_minutes",
    "paper_min_minutes",
    "paper_mean_minutes",
    "paper_max_minutes",
    "fifo_min_vs_fresh_hca",
    "fifo_mean_vs_fresh_hca",
    "fifo_max_vs_fresh_hca",
    "fifo_min_vs_paper",
    "fifo_mean_vs_paper",
    "fifo_max_vs_paper",
    "fault_values_activation",
)


def render_fifo_csv(payload: Mapping[str, Any]) -> str:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=FIFO_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    for source in payload["rows"]:
        writer.writerow({field: source.get(field) for field in FIFO_CSV_FIELDS})
    return stream.getvalue()


def _triple(row: Mapping[str, Any], prefix: str) -> str:
    return "/".join(f"{float(row[f'{prefix}_{metric}_minutes']):.6f}" for metric in ("min", "mean", "max"))


def _verdict_triple(row: Mapping[str, Any], suffix: str) -> str:
    return "/".join(str(row[f"fifo_{metric}_vs_{suffix}"]) for metric in ("min", "mean", "max"))


def render_fifo_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload["summary"]
    hca = summary["fifo_vs_fresh_hca"]
    paper = summary["fifo_vs_paper"]
    lines = [
        "# G27 FIFO 无故障速度控制汇总",
        "",
        "四个控制均完成全部 28,506 个原始行李；无故障时 G27 故障局部势值层保持 exact-off，因此这里测量的是 FIFO/S4 控制表现，不把故障扩展冒充为无故障收益。",
        f"按 min/mean/max 共 12 个单元，对 fresh HCA 为 {hca['g27_fifo_win_count']} 胜、{hca['tie_count']} 平、{hca['original_win_count']} 负；对论文值为 {paper['g27_fifo_win_count']} 胜、{paper['tie_count']} 平、{paper['original_win_count']} 负。",
        "",
        "| Speed (m/s) | FIFO min/mean/p95/p99/max (min) | Fresh HCA min/mean/max | Paper min/mean/max | FIFO vs HCA min/mean/max | FIFO vs paper min/mean/max |",
        "|---:|---:|---:|---:|---|---|",
    ]
    for row in payload["rows"]:
        fifo = "/".join(
            f"{float(row[f'fifo_{metric}_minutes']):.6f}"
            for metric in ("min", "mean", "p95", "p99", "max")
        )
        lines.append(
            f"| {row['speed_mps']:.1f} | {fifo} | {_triple(row, 'fresh_hca')} | {_triple(row, 'paper')} | {_verdict_triple(row, 'fresh_hca')} | {_verdict_triple(row, 'paper')} |"
        )
    lines.extend(
        [
            "",
            "## 最小值分辨率边界",
            "",
            "- 论文最小值只报告到 0.01 分钟；差异不超过半个末位单位（0.005 分钟）登记为 `RESOLUTION_BOUND_TIE`，不机械宣称微小胜负。",
            "- fresh HCA 与 FIFO 在 2.0、2.5 m/s 的最小值仅相差约 0.002 秒，也登记为 `RESOLUTION_BOUND_TIE`。mean 和 max 不套用该最小值边界。",
            "- P95、P99 在论文表 5.2 与 fresh HCA 汇总中没有对应列，因此只如实报告 FIFO 实测值，不制造比较结论。",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json(path: Path) -> Mapping[str, Any]:
    return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--g27-dir", type=Path, default=DEFAULT_G27_DIR)
    parser.add_argument("--g26-report", type=Path, default=DEFAULT_G26_REPORT)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv-out", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--markdown-out", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--fifo-json-out", type=Path, default=DEFAULT_FIFO_JSON)
    parser.add_argument("--fifo-csv-out", type=Path, default=DEFAULT_FIFO_CSV)
    parser.add_argument("--fifo-markdown-out", type=Path, default=DEFAULT_FIFO_MARKDOWN)
    parser.add_argument("--bias-json", type=Path, default=DEFAULT_BIAS_JSON)
    parser.add_argument("--decision-json-out", type=Path, default=DEFAULT_DECISION_JSON)
    parser.add_argument(
        "--decision-markdown-out", type=Path, default=DEFAULT_DECISION_MARKDOWN
    )
    args = parser.parse_args(argv)

    fault_paths, fifo_paths = discover_input_paths(args.g27_dir)
    g26 = _load_json(args.g26_report)
    g26_path = str(args.g26_report.relative_to(ROOT)).replace("\\", "/")
    fault_inputs = [g26_path]
    fault_inputs.extend(
        str(path.relative_to(ROOT)).replace("\\", "/") for path in fault_paths
    )
    fault_payload = build_report_payload(
        g26,
        [_load_json(path) for path in fault_paths],
        input_paths=fault_inputs,
    )
    fifo_inputs = [g26_path]
    fifo_inputs.extend(
        str(path.relative_to(ROOT)).replace("\\", "/") for path in fifo_paths
    )
    fifo_payload = build_fifo_speed_payload(
        g26,
        [_load_json(path) for path in fifo_paths],
        input_paths=fifo_inputs,
    )
    _write(args.json_out, json.dumps(fault_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    _write(args.csv_out, render_csv(fault_payload))
    _write(args.markdown_out, render_markdown(fault_payload))
    _write(args.fifo_json_out, json.dumps(fifo_payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    _write(args.fifo_csv_out, render_fifo_csv(fifo_payload))
    _write(args.fifo_markdown_out, render_fifo_markdown(fifo_payload))
    joint = build_joint_decision_payload(
        _load_json(args.json_out),
        _load_json(args.fifo_json_out),
        _load_json(args.bias_json),
    )
    _write(
        args.decision_json_out,
        json.dumps(joint, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
    )
    _write(args.decision_markdown_out, render_joint_decision_markdown(joint))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
