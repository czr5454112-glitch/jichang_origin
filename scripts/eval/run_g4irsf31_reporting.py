#!/usr/bin/env python3
"""Build and validate the portable G31 cross-map comparison report.

The report reads the frozen workload manifests and portable HCA*/S4 evidence
for Nanning and the original map2.  While any required campaign is partial,
every available cell remains diagnostic and no final output is written.  Once
the Nanning 40-cell/3-paired and map2 38-cell/4-paired evidence is admitted,
the script writes byte-stable JSON, CSV, and Markdown reports.  Capacity is
evaluated first; fault timing is never release-paired and therefore stays
outside the primary claim.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import io
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval import run_g4irsf31_map2_native as map2_native
from scripts.eval import run_g4irsf31_map2_bias as map2_bias
from scripts.eval import run_g4irsf31_map2_same_hca_release_timing as map2_paired
from scripts.eval import run_g4irsf31_nanning_bias as bias31
from scripts.eval import run_g4irsf31_nanning_native as g31_native
from scripts.eval import run_g4irsf31_same_hca_release_timing as paired31


SCHEMA = "czr005.g4irsf31.cross_map_reporting.v1"
MANIFEST_SCHEMA = "czr005.g4irsf31.nanning_workload_manifest.v1"
HCA_SCHEMA = "czr005.g4irsf31.nanning_hca_campaign.v1"
NATIVE_SCHEMA = "czr005.g4irsf31.nanning_s4_aggregate.v1"
NATIVE_CASE_SCHEMA = "czr005.g4irsf31.nanning_s4_case.v1"
MAP_ID = "nanning_topology_examples_1_2_namespaced_ics156"

FIXED_POPULATIONS = {
    1: {"raw_bags": 28_506, "segments": 43_603},
    2: {"raw_bags": 57_012, "segments": 87_206},
}
EXPECTED_STABLE_CASES = 8
EXPECTED_FAULT_CASES = 32
EXPECTED_PRIMARY_CASES = EXPECTED_STABLE_CASES + EXPECTED_FAULT_CASES
PAIRED_TIMING_SPEEDS = (2.0, 2.5, 3.0)
PAIRED_TIMING_METRICS = ("min", "mean", "p95", "p99", "max")

PARTIAL_DIAGNOSTIC = "G31_PARTIAL_DIAGNOSTIC"
MATRIX_READY = "G31_PRIMARY_CAPACITY_MATRIX_READY"
NOT_EVALUATED_PARTIAL = "NOT_EVALUATED_PARTIAL_CAMPAIGN"
NOT_MEASURED = "NOT_MEASURED"
PHYSICAL_SEMANTICS_RESOLUTION_TIE = "PHYSICAL_SEMANTICS_RESOLUTION_TIE"
PHYSICAL_SEMANTICS_RESOLUTION_SECONDS = 0.001

DEFAULT_MANIFEST_1X = (
    ROOT / "artifacts/tasks/g4irsf31_nanning/nanning_1x_manifest.json"
)
DEFAULT_MANIFEST_2X = (
    ROOT / "artifacts/tasks/g4irsf31_nanning/nanning_2x_manifest.json"
)
DEFAULT_HCA = ROOT / "outputs/tables/g4irsf31_nanning_hca.json"
DEFAULT_NATIVE = ROOT / "outputs/tables/g4irsf31_nanning_native.json"
DEFAULT_PAIRED_DIR = ROOT / "outputs/runtime/g4irsf31_nanning_paired"
DEFAULT_BIAS = ROOT / "outputs/tables/g4irsf31_nanning_bias.json"
DEFAULT_MAP2 = ROOT / "outputs/tables/g4irsf31_map2_native.json"
DEFAULT_MAP2_HCA_1X = ROOT / "outputs/tables/g4irsf26_reporting.json"
DEFAULT_MAP2_HCA_2X = ROOT / "outputs/tables/g4irsf29_hca.json"
DEFAULT_MAP2_PAIRED_DIR = ROOT / "outputs/runtime/g4irsf31_map2_paired"
DEFAULT_MAP2_BIAS = ROOT / "outputs/tables/g4irsf31_map2_bias.json"
DEFAULT_JSON = ROOT / "outputs/tables/g4irsf31_reporting.json"
DEFAULT_CSV = ROOT / "outputs/tables/g4irsf31_reporting.csv"
DEFAULT_MARKDOWN = ROOT / "outputs/reports/g4irsf31_reporting.md"


class Reporting31Error(RuntimeError):
    """Raised when a supplied JSON file is not a JSON object."""


@dataclass(frozen=True)
class PrimaryCell:
    native_case_id: str
    hca_case_id: str
    scale: int
    group: str
    speed_mps: float
    fault_scenario: str | None

    @property
    def fixed_raw_bag_denominator(self) -> int:
        return FIXED_POPULATIONS[self.scale]["raw_bags"]

    @property
    def fixed_segment_population(self) -> int:
        return FIXED_POPULATIONS[self.scale]["segments"]


def _speed_token(speed_mps: float) -> str:
    return f"{speed_mps:g}".replace(".", "p")


def primary_cells() -> tuple[PrimaryCell, ...]:
    """Return the registered 8 stable plus 32 fault comparison cells."""

    cells: list[PrimaryCell] = []
    for case in g31_native.PRIMARY_CASES:
        if case.group == "stable_speed":
            hca_case_id = (
                f"nanning_{case.scale}x_t5_2_speed_"
                f"{_speed_token(case.speed_mps)}"
            )
        else:
            hca_case_id = (
                f"nanning_{case.scale}x_t5_5_fault_{case.fault_scenario}"
            )
        cells.append(
            PrimaryCell(
                native_case_id=case.case_id,
                hca_case_id=hca_case_id,
                scale=case.scale,
                group=case.group,
                speed_mps=case.speed_mps,
                fault_scenario=case.fault_scenario,
            )
        )
    stable = sum(cell.group == "stable_speed" for cell in cells)
    faults = sum(cell.group == "all_day_line_interruption" for cell in cells)
    if stable != EXPECTED_STABLE_CASES or faults != EXPECTED_FAULT_CASES:
        raise Reporting31Error("G31 primary registry is not the registered 8+32 matrix")
    return tuple(cells)


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def classify_cross_framework_timing_metric(
    metric: str, hca_seconds: float, s4_seconds: float
) -> dict[str, Any]:
    """Classify a paired full-population timing metric without hiding order."""

    delta = float(s4_seconds) - float(hca_seconds)
    strict_order = (
        "S4_LOWER" if delta < 0.0 else "HCA_LOWER" if delta > 0.0 else "EXACT_TIE"
    )
    resolution_tie = bool(
        metric == "min"
        and delta != 0.0
        and abs(delta)
        <= PHYSICAL_SEMANTICS_RESOLUTION_SECONDS + 1.0e-12
    )
    verdict = (
        PHYSICAL_SEMANTICS_RESOLUTION_TIE if resolution_tie else strict_order
    )
    return {
        "metric": metric,
        "hca_seconds": float(hca_seconds),
        "s4_seconds": float(s4_seconds),
        "s4_minus_hca_seconds": delta,
        "strict_numeric_order": strict_order,
        "verdict": verdict,
        "candidate_boundary": resolution_tie,
        "physical_semantics_resolution_seconds": (
            PHYSICAL_SEMANTICS_RESOLUTION_SECONDS
        ),
        "counts_as_s4_win": verdict == "S4_LOWER",
        "counts_as_hca_win": verdict == "HCA_LOWER",
        "counts_as_tie": verdict in {
            "EXACT_TIE",
            PHYSICAL_SEMANTICS_RESOLUTION_TIE,
        },
    }


def _path(value: Mapping[str, Any] | None, *keys: str) -> Any:
    current: Any = value
    for key in keys:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _index(rows: Any, key: str = "case_id") -> dict[str, Mapping[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        str(row[key]): row
        for row in rows
        if isinstance(row, Mapping) and row.get(key) is not None
    }


def _paired_case_id(speed_mps: float) -> str:
    return f"t5_2_nanning_1x_speed_{_speed_token(speed_mps)}"


def _paired_artifact_summary(
    speed_mps: float, artifact: Mapping[str, Any] | None
) -> dict[str, Any]:
    """Validate one full-population same-HCA-release timing artifact."""

    reasons: list[str] = []
    expected_case_id = _paired_case_id(speed_mps)
    if artifact is None:
        reasons.append("same-HCA-release artifact is missing")
    else:
        if artifact.get("schema") != paired31.SCHEMA:
            reasons.append("paired artifact schema does not match G31")
        if artifact.get("status") != paired31.COMPLETE:
            reasons.append("paired artifact is not complete")
        if artifact.get("case_id") != expected_case_id:
            reasons.append("paired artifact case ID does not match")
        if artifact.get("map_id") != MAP_ID:
            reasons.append("paired artifact map does not match Nanning")
        if artifact.get("view_role") != "SECONDARY_STABLE_TIMING_ONLY":
            reasons.append("paired artifact has the wrong evidence role")
        if _integer(_path(artifact, "selection", "scale")) != 1:
            reasons.append("paired timing is registered only for 1x")
        selected_speed = _number(_path(artifact, "selection", "speed_mps"))
        if selected_speed != speed_mps:
            reasons.append("paired artifact speed does not match")
        if _integer(_path(artifact, "selection", "raw_bag_count")) != 28_506:
            reasons.append("paired raw-bag population is not complete")
        if _integer(_path(artifact, "selection", "segment_count")) != 43_603:
            reasons.append("paired segment population is not complete")
        if _path(artifact, "hca_release_trace", "pass") is not True:
            reasons.append("HCA release trace is not eligible")
        if _path(artifact, "hca_timing", "pass") is not True:
            reasons.append("HCA full-population timing is not eligible")
        if _path(artifact, "safety", "pass") is not True:
            reasons.append("paired S4 safety admission is not passed")
        if _integer(_path(artifact, "outcome", "completed_raw_bag_count")) != 28_506:
            reasons.append("paired S4 raw-bag population is incomplete")
        if _path(artifact, "runtime", "event_limit_reached") is not False:
            reasons.append("paired S4 exhausted its event budget")
        contract = artifact.get("comparison_contract")
        if not isinstance(contract, Mapping) or any(
            (
                contract.get("same_segment_release_required") is not True,
                contract.get("both_full_raw_bag_populations_required") is not True,
                contract.get("survivor_only_comparison_allowed") is not False,
                contract.get("common_cohort_comparison_allowed") is not False,
                contract.get("capacity_verdict_allowed") is not False,
            )
        ):
            reasons.append("paired comparison contract is not the frozen full view")

    hca_metrics = _path(artifact, "hca_timing", "metrics_seconds")
    s4_metrics = _path(artifact, "paired_s4_timing", "metrics_seconds")
    metric_rows: list[dict[str, Any]] = []
    if not isinstance(hca_metrics, Mapping) or not isinstance(s4_metrics, Mapping):
        reasons.append("paired five-metric timing payload is missing")
    else:
        for metric in PAIRED_TIMING_METRICS:
            hca_value = _number(hca_metrics.get(metric))
            s4_value = _number(s4_metrics.get(metric))
            if hca_value is None or s4_value is None:
                reasons.append(f"paired metric is missing or non-finite: {metric}")
                continue
            row = classify_cross_framework_timing_metric(
                metric, hca_value, s4_value
            )
            row["acceptable_for_fresh_target"] = bool(
                row["counts_as_s4_win"]
                or (metric == "min" and row["counts_as_tie"])
            )
            metric_rows.append(row)
    ready = not reasons and len(metric_rows) == len(PAIRED_TIMING_METRICS)
    return {
        "case_id": expected_case_id,
        "scale": 1,
        "speed_mps": speed_mps,
        "status": (
            "ELIGIBLE_FULL_POPULATION_SAME_HCA_RELEASE"
            if ready
            else "NOT_ELIGIBLE"
        ),
        "ready": ready,
        "denominator": (
            "sum_over_segments(finish_time-HCA_run_01_segment_release_epoch)"
        ),
        "metric_rows": metric_rows if ready else [],
        "all_metrics_acceptable_for_fresh_target": bool(
            ready and all(row["acceptable_for_fresh_target"] for row in metric_rows)
        ),
        "reasons": reasons,
        "own_source_timing_used_for_cross_algorithm_verdict": False,
    }


def _paired_timing_summary(
    artifacts: Mapping[float, Mapping[str, Any] | None] | None,
) -> dict[str, Any]:
    supplied = artifacts or {}
    slots: list[dict[str, Any]] = [
        {
            "case_id": _paired_case_id(1.5),
            "scale": 1,
            "speed_mps": 1.5,
            "status": "N_A_HCA_BASELINE_INCOMPLETE",
            "ready": False,
            "metric_rows": [],
            "excluded_from_required_paired_set": True,
            "reason": (
                "corrected HCA 1x speed-1.5 baseline did not complete the full "
                "population; survivor/common-cohort timing is forbidden"
            ),
            "own_source_timing_used_for_cross_algorithm_verdict": False,
        }
    ]
    slots.extend(
        _paired_artifact_summary(speed, supplied.get(speed))
        for speed in PAIRED_TIMING_SPEEDS
    )
    eligible = [row for row in slots if row["speed_mps"] in PAIRED_TIMING_SPEEDS]
    ready = all(row["ready"] for row in eligible)
    metric_rows = [metric for row in eligible for metric in row["metric_rows"]]
    verdict_counts: dict[str, int] = {}
    if ready:
        for row in metric_rows:
            verdict = str(row["verdict"])
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
    return {
        "status": (
            "COMPLETE_SAME_HCA_RELEASE_TIMING" if ready else "PARTIAL_OR_UNAVAILABLE"
        ),
        "required_artifact_count": len(PAIRED_TIMING_SPEEDS),
        "eligible_artifact_count": sum(row["ready"] for row in eligible),
        "expected_metric_count": len(PAIRED_TIMING_SPEEDS)
        * len(PAIRED_TIMING_METRICS),
        "eligible_metric_count": len(metric_rows) if ready else 0,
        "all_required_artifacts_ready": ready,
        "all_metrics_acceptable_for_fresh_target": bool(
            ready
            and all(
                row["all_metrics_acceptable_for_fresh_target"] for row in eligible
            )
        ),
        "verdict_counts": verdict_counts,
        "slots": slots,
        "cross_algorithm_source": "same_HCA_release_full_population_only",
        "own_source_timing_used_for_cross_algorithm_verdict": False,
        "survivor_or_common_cohort_comparison_allowed": False,
    }


def _bias_context_summary(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    reasons: list[str] = []
    if payload is None:
        return {
            "status": "NON_EXACT_CONTEXT_NOT_AVAILABLE",
            "ready": False,
            "reasons": ["bias aggregate is missing"],
            "drives_fresh_exact_target": False,
            "target_contribution": None,
        }
    if payload.get("schema") != bias31.AGGREGATE_SCHEMA:
        reasons.append("bias aggregate schema does not match G31")
    if payload.get("protocol_fidelity") != bias31.PROTOCOL_FIDELITY:
        reasons.append("bias aggregate is not labelled NON_EXACT")
    if payload.get("fresh_exact_primary_target_eligible") is not False:
        reasons.append("bias aggregate does not preserve the secondary boundary")
    if _integer(payload.get("expected_case_count")) != 24:
        reasons.append("bias aggregate does not register 24 cells")
    if payload.get("status") != "COMPLETE":
        reasons.append("bias reconstruction campaign is partial")
    if len(set(payload.get("complete_case_ids", []))) != 24:
        reasons.append("bias reconstruction has fewer than 24 admitted cells")
    if payload.get("failed_case_ids") != [] or payload.get("stale_case_ids") != []:
        reasons.append("bias reconstruction has failed or stale cells")
    if payload.get("missing_case_ids") != []:
        reasons.append("bias reconstruction has missing cells")
    return {
        "status": (
            "NON_EXACT_CONTEXT_AVAILABLE"
            if not reasons
            else "NON_EXACT_CONTEXT_PARTIAL"
        ),
        "ready": not reasons,
        "observed_admitted_case_count": len(
            set(payload.get("complete_case_ids", []))
        ),
        "reasons": reasons,
        "protocol_fidelity": bias31.PROTOCOL_FIDELITY,
        "drives_fresh_exact_target": False,
        "target_contribution": None,
    }


def _map2_bias_context_summary(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Validate optional map2 Table-5.4 context without making a verdict."""

    expected_ids = set(map2_bias.CASE_IDS)
    cases = _index(payload.get("cases") if payload else None)
    reasons: list[str] = []
    if payload is None:
        reasons.append("map2 bias aggregate is missing")
    else:
        if payload.get("schema") != map2_bias.AGGREGATE_SCHEMA:
            reasons.append("map2 bias aggregate schema does not match G31")
        if payload.get("status") != "COMPLETE":
            reasons.append("map2 bias reconstruction campaign is partial")
        if payload.get("map_id") != map2_native.MAP_ID:
            reasons.append("map2 bias aggregate map does not match")
        if payload.get("protocol_fidelity") != map2_bias.PROTOCOL_FIDELITY:
            reasons.append("map2 bias aggregate is not labelled NON_EXACT")
        if payload.get("evidence_role") != map2_bias.EVIDENCE_ROLE:
            reasons.append("map2 bias aggregate has the wrong evidence role")
        if payload.get("fresh_exact_primary_target_eligible") is not False:
            reasons.append("map2 bias aggregate is not excluded from fresh target")
        if payload.get("cross_map_target_eligible") is not False:
            reasons.append("map2 bias aggregate is not excluded from cross-map target")
        if _integer(payload.get("expected_case_count")) != 24:
            reasons.append("map2 bias aggregate does not register 24 cells")
        if set(payload.get("complete_case_ids", [])) != expected_ids:
            reasons.append("map2 bias admitted IDs do not match the 24-cell grid")
        if set(cases) != expected_ids:
            reasons.append("map2 bias case rows do not match the 24-cell grid")
        if payload.get("failed_case_ids") != []:
            reasons.append("map2 bias aggregate has failed cells")
        if payload.get("stale_case_ids") != []:
            reasons.append("map2 bias aggregate has stale cells")
        if payload.get("missing_case_ids") != []:
            reasons.append("map2 bias aggregate has missing cells")

    rows: list[dict[str, Any]] = []
    for case in map2_bias.CASES:
        artifact = cases.get(case.case_id)
        row_reasons: list[str] = []
        denominator = map2_native.SCALE_COUNTS[case.scale][0]
        if artifact is None:
            row_reasons.append("map2 bias case is missing")
        else:
            if artifact.get("schema") != map2_bias.SCHEMA:
                row_reasons.append("case schema does not match")
            if artifact.get("status") != map2_bias.COMPLETE:
                row_reasons.append("case is not complete")
            if artifact.get("map_id") != map2_native.MAP_ID:
                row_reasons.append("case map does not match")
            if artifact.get("case") != case.as_dict():
                row_reasons.append("case identity does not match")
            if artifact.get("protocol_fidelity") != map2_bias.PROTOCOL_FIDELITY:
                row_reasons.append("case protocol is not NON_EXACT")
            if artifact.get("evidence_role") != map2_bias.EVIDENCE_ROLE:
                row_reasons.append("case evidence role does not match")
            if artifact.get("fresh_exact_primary_target_eligible") is not False:
                row_reasons.append("case is not excluded from fresh target")
            if artifact.get("cross_map_target_eligible") is not False:
                row_reasons.append("case is not excluded from cross-map target")
            if artifact.get("observation_bias") != map2_bias.bias_contract(case):
                row_reasons.append("case bias contract does not match")
            if _path(artifact, "safety", "pass") is not True:
                row_reasons.append("case safety admission is not passed")
            if _integer(
                _path(artifact, "selection", "selected_raw_bag_count")
            ) != denominator:
                row_reasons.append("case fixed population does not match")
        completed = _integer(
            _path(artifact, "outcome", "completed_raw_bag_count")
        )
        if completed is None or not 0 <= completed <= denominator:
            row_reasons.append("case S4 completion count is missing")
            completed = None
        rows.append(
            {
                "case_id": case.case_id,
                "scale": case.scale,
                "standard_speed_mps": case.standard_speed_mps,
                "deviation_percent": case.deviation_percent,
                "maximum_observation_delay_seconds": case.maximum_seconds,
                "fixed_raw_bag_denominator": denominator,
                "s4_completed_raw_bags": completed,
                "s4_completion_percent": (
                    round(completed / denominator * 100.0, 6)
                    if completed is not None
                    else None
                ),
                "s4_timing_status": _path(artifact, "timing", "status"),
                "safety_pass": _path(artifact, "safety", "pass") is True,
                "ready": not row_reasons,
                "not_ready_reasons": row_reasons,
            }
        )
    ready = not reasons and all(row["ready"] for row in rows)
    return {
        "status": (
            "NON_EXACT_CONTEXT_AVAILABLE"
            if ready
            else "NON_EXACT_CONTEXT_PARTIAL_OR_UNAVAILABLE"
        ),
        "ready": ready,
        "protocol_fidelity": map2_bias.PROTOCOL_FIDELITY,
        "expected_case_count": 24,
        "admitted_case_count": sum(row["ready"] for row in rows),
        "all_safety_pass": (
            all(row["safety_pass"] for row in rows) if ready else None
        ),
        "full_population_case_count": (
            sum(
                row["s4_completed_raw_bags"]
                == row["fixed_raw_bag_denominator"]
                for row in rows
            )
            if ready
            else None
        ),
        "descriptive_s4_results": rows,
        "reasons": reasons,
        "fresh_exact_primary_target_eligible": False,
        "cross_map_target_eligible": False,
        "matched_disturbance_hca_comparison": False,
        "cross_algorithm_verdict_generated": False,
    }


def _map2_hca_case_id(case: map2_native.CaseSpec) -> str:
    if case.group == "stable_speed":
        return f"t5_2_speed_{_speed_token(case.speed_mps)}"
    return f"t5_5_fault_{case.fault_scenario}"


def _map2_native_capacity(
    case: map2_native.CaseSpec, artifact: Mapping[str, Any] | None
) -> dict[str, Any]:
    denominator, segments = map2_native.SCALE_COUNTS[case.scale]
    reasons: list[str] = []
    if artifact is None:
        reasons.append("matching map2 S4 case is missing")
    else:
        if artifact.get("schema") != map2_native.SCHEMA:
            reasons.append("map2 S4 case schema does not match")
        if artifact.get("status") != map2_native.COMPLETE:
            reasons.append("map2 S4 case is not admitted")
        if artifact.get("case") != case.as_dict():
            reasons.append("map2 S4 case identity does not match")
        if _integer(_path(artifact, "selection", "selected_raw_bag_count")) != denominator:
            reasons.append("map2 S4 denominator does not match")
        if _integer(_path(artifact, "selection", "selected_segment_count")) != segments:
            reasons.append("map2 S4 segment population does not match")
        if _path(artifact, "safety", "pass") is not True:
            reasons.append("map2 S4 safety admission is not passed")
        if _number(_path(artifact, "request_contract", "max_simulation_time")) != map2_native.FIXED_END_EPOCH:
            reasons.append("map2 S4 fixed horizon does not match")
        if _integer(_path(artifact, "request_contract", "max_events")) != map2_native.MAX_EVENTS:
            reasons.append("map2 S4 event budget does not match")
        if _path(artifact, "runtime", "event_limit_reached") is not False:
            reasons.append("map2 S4 event budget was exhausted")
    completed = _integer(_path(artifact, "outcome", "completed_raw_bag_count"))
    if completed is None or not 0 <= completed <= denominator:
        reasons.append("map2 S4 completion numerator is missing")
        completed = None
    return {
        "ready": not reasons,
        "completed_raw_bags": completed,
        "topology_upper_raw_bags": _integer(
            _path(
                artifact,
                "safety",
                "topology",
                "topology_reachable_raw_bag_upper_bound",
            )
        ),
        "reasons": reasons,
    }


def _map2_hca_1x_capacity(
    case: map2_native.CaseSpec,
    report: Mapping[str, Any] | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if report is None:
        reasons.append("G26 1x HCA report is missing")
        rows: list[Any] = []
    else:
        if report.get("schema") != "czr005.g4irsf26.reporting.v1":
            reasons.append("G26 1x HCA report schema does not match")
        rows = _path(report, "tables", "5.2" if case.group == "stable_speed" else "5.5")
        if not isinstance(rows, list):
            reasons.append("G26 1x HCA table is missing")
            rows = []
    denominator = map2_native.SCALE_COUNTS[1][0]
    completed: int | None = None
    if case.group == "stable_speed":
        matching = [
            row
            for row in rows
            if isinstance(row, Mapping)
            and _number(row.get("speed_mps")) == case.speed_mps
            and row.get("measurement_status") == "MEASURED"
            and row.get("hca_evidence") == "EXACT_FRESH"
        ]
        if {row.get("metric") for row in matching} != {
            "tth_min_minutes",
            "tth_mean_minutes",
            "tth_max_minutes",
        } or any(_number(row.get("hca_value")) is None for row in matching):
            reasons.append("G26 1x stable HCA full-population evidence is incomplete")
        else:
            completed = denominator
    else:
        matching = [
            row
            for row in rows
            if isinstance(row, Mapping) and row.get("row_id") == case.fault_scenario
        ]
        if len(matching) != 1:
            reasons.append("G26 1x fault HCA row is missing or duplicated")
        else:
            row = matching[0]
            rate = _number(row.get("hca_primary_success"))
            if (
                row.get("measurement_status") != "MEASURED"
                or row.get("hca_evidence") != "EXACT_FRESH"
                or rate is None
                or not 0.0 <= rate <= 1.0
            ):
                reasons.append("G26 1x fault HCA row is not fixed-population evidence")
            else:
                completed = int(round(rate * denominator))
                if not math.isclose(
                    completed / denominator, rate, rel_tol=0.0, abs_tol=1.0e-12
                ):
                    reasons.append("G26 1x fault HCA rate does not map to an integer count")
                    completed = None
    return {
        "ready": not reasons,
        "completed_raw_bags": completed if not reasons else None,
        "source": "g4irsf26_fresh_hca_fixed_population",
        "reasons": reasons,
    }


def _map2_hca_2x_summary(
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    expected = {_map2_hca_case_id(case) for case in map2_native.PRIMARY_CASES if case.scale == 2}
    all_rows = _index(payload.get("rows") if payload else None)
    rows = {case_id: all_rows[case_id] for case_id in expected if case_id in all_rows}
    reasons: list[str] = []
    if payload is None:
        reasons.append("G29 2x HCA aggregate is missing")
    else:
        if payload.get("schema") != "czr005.g4irsf29.hca_campaign.v1":
            reasons.append("G29 2x HCA aggregate schema does not match")
        if payload.get("status") != "COMPLETE_WITH_ARCHIVED_ONLY_GAP":
            reasons.append("G29 2x HCA aggregate is not complete")
        if _integer(_path(payload, "protocol", "primary_case_count")) != 19:
            reasons.append("G29 2x HCA primary registry is not nineteen cells")
        if _integer(payload.get("primary_complete_case_count")) != 19:
            reasons.append("G29 2x HCA primary campaign is incomplete")
        if payload.get("missing_primary_case_ids") != []:
            reasons.append("G29 2x HCA has missing primary cells")
        if payload.get("invalid_primary_case_ids") != []:
            reasons.append("G29 2x HCA has invalid primary cells")
        if set(rows) != expected:
            reasons.append("G29 2x HCA rows do not match the map2 registry")
    return {"ready": not reasons, "rows": rows, "reasons": reasons}


def _map2_hca_2x_capacity(
    case: map2_native.CaseSpec,
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    reasons = list(summary.get("reasons", []))
    row = summary.get("rows", {}).get(_map2_hca_case_id(case))
    repeats = 2 if case.group == "stable_speed" else 1
    if not isinstance(row, Mapping):
        reasons.append("matching G29 2x HCA row is missing")
        counts: Any = []
    else:
        if row.get("execution_class") != "PRIMARY_MEASURABLE":
            reasons.append("G29 2x HCA row is not primary measurable")
        if row.get("primary_capacity_eligible") is not True:
            reasons.append("G29 2x HCA row is not capacity eligible")
        if row.get("fixed_horizon_pass") is not True:
            reasons.append("G29 2x HCA row does not match the fixed horizon")
        if (
            _integer(row.get("repeats_expected")) != repeats
            or _integer(row.get("repeats_complete")) != repeats
        ):
            reasons.append("G29 2x HCA repeat count is incomplete")
        counts = row.get("canonical_complete_raw_bag_count_by_repeat")
    normalized = (
        [_integer(value) for value in counts]
        if isinstance(counts, list) and len(counts) == repeats
        else []
    )
    denominator = map2_native.SCALE_COUNTS[2][0]
    if (
        len(normalized) != repeats
        or any(value is None or not 0 <= value <= denominator for value in normalized)
        or len(set(normalized)) != 1
    ):
        reasons.append("G29 2x HCA completion counts are missing or inconsistent")
    return {
        "ready": not reasons,
        "completed_raw_bags": normalized[0] if normalized and not reasons else None,
        "source": "g4irsf29_hca_fixed_population",
        "reasons": reasons,
    }


def _map2_paired_artifact_summary(
    speed_mps: float, artifact: Mapping[str, Any] | None
) -> dict[str, Any]:
    case_id = f"t5_2_map2_1x_speed_{_speed_token(speed_mps)}"
    reasons: list[str] = []
    if artifact is None:
        reasons.append("map2 same-HCA-release artifact is missing")
    else:
        if artifact.get("schema") != map2_paired.SCHEMA:
            reasons.append("map2 paired artifact schema does not match")
        if artifact.get("status") != map2_paired.COMPLETE:
            reasons.append("map2 paired artifact is not complete")
        if artifact.get("case_id") != case_id:
            reasons.append("map2 paired artifact case ID does not match")
        if artifact.get("map_id") != map2_native.MAP_ID:
            reasons.append("map2 paired artifact map does not match")
        if artifact.get("view_role") != "SECONDARY_STABLE_TIMING_ONLY":
            reasons.append("map2 paired artifact has the wrong evidence role")
        if _integer(_path(artifact, "selection", "scale")) != 1:
            reasons.append("map2 paired timing is registered only for 1x")
        if _number(_path(artifact, "selection", "speed_mps")) != speed_mps:
            reasons.append("map2 paired speed does not match")
        if _integer(_path(artifact, "selection", "raw_bag_count")) != 28_506:
            reasons.append("map2 paired raw-bag population is incomplete")
        if _integer(_path(artifact, "selection", "segment_count")) != 43_603:
            reasons.append("map2 paired segment population is incomplete")
        if _path(artifact, "hca_release_trace", "pass") is not True:
            reasons.append("map2 HCA release trace is not eligible")
        if _path(artifact, "hca_timing", "pass") is not True:
            reasons.append("map2 HCA timing is not full population")
        if _path(artifact, "safety", "pass") is not True:
            reasons.append("map2 paired S4 safety admission is not passed")
        if _integer(_path(artifact, "outcome", "completed_raw_bag_count")) != 28_506:
            reasons.append("map2 paired S4 raw-bag population is incomplete")
        if _path(artifact, "runtime", "event_limit_reached") is not False:
            reasons.append("map2 paired S4 exhausted its event budget")
        contract = artifact.get("comparison_contract")
        if not isinstance(contract, Mapping) or any(
            (
                contract.get("same_segment_release_required") is not True,
                contract.get("both_frameworks_full_raw_bag_populations_required") is not True,
                contract.get("survivor_only_comparison_allowed") is not False,
                contract.get("common_cohort_comparison_allowed") is not False,
                contract.get("capacity_verdict_allowed") is not False,
            )
        ):
            reasons.append("map2 paired comparison contract is not the frozen full view")
    hca_metrics = _path(artifact, "hca_timing", "metrics_seconds")
    s4_metrics = _path(artifact, "paired_s4_timing", "metrics_seconds")
    metric_rows: list[dict[str, Any]] = []
    if not isinstance(hca_metrics, Mapping) or not isinstance(s4_metrics, Mapping):
        reasons.append("map2 paired five-metric timing payload is missing")
    else:
        for metric in PAIRED_TIMING_METRICS:
            hca_value = _number(hca_metrics.get(metric))
            s4_value = _number(s4_metrics.get(metric))
            if hca_value is None or s4_value is None:
                reasons.append(f"map2 paired metric is missing or non-finite: {metric}")
                continue
            row = classify_cross_framework_timing_metric(metric, hca_value, s4_value)
            row["acceptable_for_cross_map_target"] = bool(
                row["counts_as_s4_win"] or (metric == "min" and row["counts_as_tie"])
            )
            metric_rows.append(row)
    ready = not reasons and len(metric_rows) == len(PAIRED_TIMING_METRICS)
    return {
        "case_id": case_id,
        "scale": 1,
        "speed_mps": speed_mps,
        "status": "ELIGIBLE_FULL_POPULATION_SAME_HCA_RELEASE" if ready else "NOT_ELIGIBLE",
        "ready": ready,
        "metric_rows": metric_rows if ready else [],
        "all_metrics_acceptable_for_cross_map_target": bool(
            ready and all(row["acceptable_for_cross_map_target"] for row in metric_rows)
        ),
        "reasons": reasons,
    }


def _map2_evidence_summary(
    native_aggregate: Mapping[str, Any] | None,
    hca_1x_report: Mapping[str, Any] | None,
    hca_2x_aggregate: Mapping[str, Any] | None,
    paired_artifacts: Mapping[float, Mapping[str, Any] | None] | None,
) -> dict[str, Any]:
    expected_ids = {case.case_id for case in map2_native.PRIMARY_CASES}
    cases = _index(native_aggregate.get("cases") if native_aggregate else None)
    aggregate_reasons: list[str] = []
    if native_aggregate is None:
        aggregate_reasons.append("map2 final-policy aggregate is missing")
    else:
        if native_aggregate.get("schema") != map2_native.AGGREGATE_SCHEMA:
            aggregate_reasons.append("map2 aggregate schema does not match G31")
        if native_aggregate.get("protocol") != map2_native.FINAL_POLICY_PROTOCOL:
            aggregate_reasons.append("map2 aggregate protocol does not match final policy")
        if native_aggregate.get("status") != "COMPLETE":
            aggregate_reasons.append("map2 S4 campaign is partial")
        for field, expected in (
            ("expected_executable_case_count", 38),
            ("expected_stable_speed_case_count", 8),
            ("expected_measurable_fault_case_count", 30),
            ("not_measurable_case_count", 2),
            ("observed_current_case_count", 38),
        ):
            if _integer(native_aggregate.get(field)) != expected:
                aggregate_reasons.append(f"map2 aggregate {field} does not equal {expected}")
        if set(native_aggregate.get("complete_case_ids", [])) != expected_ids:
            aggregate_reasons.append("map2 admitted case IDs do not match 38-cell registry")
        if set(cases) != expected_ids:
            aggregate_reasons.append("map2 aggregate rows do not match 38-cell registry")
        if native_aggregate.get("failed_case_ids") != []:
            aggregate_reasons.append("map2 aggregate has failed cases")
        if native_aggregate.get("stale_case_ids") != []:
            aggregate_reasons.append("map2 aggregate has stale cases")
        if native_aggregate.get("missing_case_ids") != []:
            aggregate_reasons.append("map2 aggregate has missing cases")

    hca_2x = _map2_hca_2x_summary(hca_2x_aggregate)
    rows: list[dict[str, Any]] = []
    capacity_ready = not aggregate_reasons
    for case in map2_native.PRIMARY_CASES:
        s4 = _map2_native_capacity(case, cases.get(case.case_id))
        hca = (
            _map2_hca_1x_capacity(case, hca_1x_report)
            if case.scale == 1
            else _map2_hca_2x_capacity(case, hca_2x)
        )
        evidence_ready = s4["ready"] and hca["ready"]
        capacity_ready = capacity_ready and evidence_ready
        verdict = NOT_EVALUATED_PARTIAL
        if evidence_ready and not aggregate_reasons:
            verdict = _capacity_verdict(
                int(s4["completed_raw_bags"]),
                int(hca["completed_raw_bags"]),
                map2_native.SCALE_COUNTS[case.scale][0],
                s4["topology_upper_raw_bags"],
            )
        rows.append(
            {
                "case_id": case.case_id,
                "case_group": case.group,
                "scale": case.scale,
                "speed_mps": case.speed_mps,
                "fault_scenario": case.fault_scenario,
                "fixed_raw_bag_denominator": map2_native.SCALE_COUNTS[case.scale][0],
                "s4_completed_raw_bags": s4["completed_raw_bags"],
                "hca_completed_raw_bags": hca["completed_raw_bags"],
                "s4_topology_upper_raw_bags": s4["topology_upper_raw_bags"],
                "verdict": verdict,
                "evidence_ready": evidence_ready,
                "not_ready_reasons": [*s4["reasons"], *hca["reasons"]],
            }
        )
    capacity_counts: dict[str, int] = {}
    if capacity_ready:
        for row in rows:
            verdict = str(row["verdict"])
            capacity_counts[verdict] = capacity_counts.get(verdict, 0) + 1
    capacity_acceptable = bool(
        capacity_ready
        and all(
            row["verdict"] in {"S4_WIN", "FULL_POPULATION_CEILING_TIE", "TOPOLOGY_UPPER_TIE"}
            for row in rows
        )
    )

    supplied = paired_artifacts or {}
    timing_slots = [
        _map2_paired_artifact_summary(speed, supplied.get(speed))
        for speed in map2_native.SPEEDS_MPS
    ]
    timing_ready = all(slot["ready"] for slot in timing_slots)
    timing_metrics = [metric for slot in timing_slots for metric in slot["metric_rows"]]
    timing_counts: dict[str, int] = {}
    if timing_ready:
        for metric in timing_metrics:
            verdict = str(metric["verdict"])
            timing_counts[verdict] = timing_counts.get(verdict, 0) + 1
    timing_acceptable = bool(
        timing_ready
        and all(slot["all_metrics_acceptable_for_cross_map_target"] for slot in timing_slots)
    )
    ready = capacity_ready and timing_ready
    return {
        "status": "COMPLETE_MAP2_CROSS_ALGORITHM_EVIDENCE" if ready else "PARTIAL_MAP2_CROSS_ALGORITHM_EVIDENCE",
        "map_id": map2_native.MAP_ID,
        "ready": ready,
        "aggregate_reasons": aggregate_reasons,
        "capacity": {
            "ready": capacity_ready,
            "expected_case_count": 38,
            "observed_case_count": len(cases),
            "rows": rows,
            "verdict_counts": capacity_counts,
            "acceptable_for_cross_map_target": capacity_acceptable if capacity_ready else None,
        },
        "same_hca_release_timing": {
            "ready": timing_ready,
            "required_1x_artifact_count": 4,
            "eligible_1x_artifact_count": sum(slot["ready"] for slot in timing_slots),
            "eligible_metric_count": len(timing_metrics) if timing_ready else 0,
            "verdict_counts": timing_counts,
            "slots_1x": timing_slots,
            "slots_2x": [
                {
                    "case_id": f"t5_2_map2_2x_speed_{_speed_token(speed)}",
                    "scale": 2,
                    "speed_mps": speed,
                    "status": "N_A_HCA_FULL_POPULATION_TIMING_UNAVAILABLE",
                    "reason": "G29 HCA did not complete the full 2x population; survivor timing is excluded",
                }
                for speed in map2_native.SPEEDS_MPS
            ],
            "all_metrics_acceptable_for_cross_map_target": timing_acceptable if timing_ready else None,
        },
        "not_measurable_cases": [
            {
                "case_id": case_id,
                "status": "NM",
                "reason": map2_native.NM_REASON,
            }
            for case_id in map2_native.NM_CASE_IDS
        ],
        "target_met": bool(capacity_acceptable and timing_acceptable) if ready else None,
        "drives_nanning_target": False,
    }


def _manifest_summary(
    manifest: Mapping[str, Any] | None, scale: int
) -> dict[str, Any]:
    expected = FIXED_POPULATIONS[scale]
    reasons: list[str] = []
    if manifest is None:
        reasons.append(f"{scale}x workload manifest is missing")
    else:
        if manifest.get("schema") != MANIFEST_SCHEMA:
            reasons.append(f"{scale}x workload schema does not match G31")
        if manifest.get("status") != "COMPLETE":
            reasons.append(f"{scale}x workload is not COMPLETE")
        if _integer(manifest.get("scale")) != scale:
            reasons.append(f"{scale}x workload scale does not match")
        if manifest.get("map_id") != MAP_ID:
            reasons.append(f"{scale}x workload map does not match Nanning")
        if _integer(manifest.get("raw_task_count")) != expected["raw_bags"]:
            reasons.append(f"{scale}x raw-bag denominator does not match")
        if _integer(manifest.get("expanded_segment_count")) != expected["segments"]:
            reasons.append(f"{scale}x segment population does not match")
        invariants = manifest.get("invariants")
        if not isinstance(invariants, Mapping) or any(
            value is not True for value in invariants.values()
        ):
            reasons.append(f"{scale}x workload invariants are not all true")
    return {
        "scale": scale,
        "ready": not reasons,
        "fixed_raw_bag_denominator": expected["raw_bags"],
        "fixed_segment_population": expected["segments"],
        "protocol": manifest.get("protocol") if manifest else None,
        "reasons": reasons,
    }


def _hca_aggregate_summary(
    payload: Mapping[str, Any] | None, cells: Sequence[PrimaryCell]
) -> dict[str, Any]:
    expected_ids = {cell.hca_case_id for cell in cells}
    rows = _index(payload.get("rows") if payload else None)
    reasons: list[str] = []
    if payload is None:
        reasons.append("HCA aggregate is missing")
    else:
        if payload.get("schema") != HCA_SCHEMA:
            reasons.append("HCA aggregate schema does not match G31")
        if payload.get("status") != "COMPLETE":
            reasons.append("HCA aggregate is partial")
        if _integer(_path(payload, "protocol", "expected_case_count")) != len(cells):
            reasons.append("HCA expected case count is not 40")
        if _integer(payload.get("complete_case_count")) != len(cells):
            reasons.append("HCA complete case count is not 40")
        if payload.get("missing_case_ids") != []:
            reasons.append("HCA aggregate has missing cases")
        if payload.get("invalid_case_ids") != []:
            reasons.append("HCA aggregate has invalid cases")
        if set(rows) != expected_ids:
            reasons.append("HCA aggregate rows do not match the 40-cell registry")
    return {
        "ready": not reasons,
        "observed_case_count": len(rows),
        "reasons": reasons,
        "rows": rows,
    }


def _native_aggregate_summary(
    payload: Mapping[str, Any] | None, cells: Sequence[PrimaryCell]
) -> dict[str, Any]:
    expected_ids = {cell.native_case_id for cell in cells}
    cases = _index(payload.get("cases") if payload else None)
    complete_ids = set(payload.get("complete_case_ids", [])) if payload else set()
    reasons: list[str] = []
    if payload is None:
        reasons.append("native aggregate is missing")
    else:
        if payload.get("schema") != NATIVE_SCHEMA:
            reasons.append("native aggregate schema does not match G31")
        if payload.get("status") != "COMPLETE":
            reasons.append("native aggregate is partial")
        if _integer(payload.get("expected_primary_case_count")) != len(cells):
            reasons.append("native expected case count is not 40")
        if _integer(payload.get("observed_case_count")) != len(cells):
            reasons.append("native observed case count is not 40")
        if complete_ids != expected_ids:
            reasons.append("native admitted case IDs do not match the 40-cell registry")
        if set(cases) != expected_ids:
            reasons.append("native aggregate rows do not match the 40-cell registry")
        if payload.get("failed_case_ids") != []:
            reasons.append("native aggregate has failed cases")
        if payload.get("stale_case_ids") != []:
            reasons.append("native aggregate has stale cases")
        if payload.get("missing_case_ids") != []:
            reasons.append("native aggregate has missing cases")
    return {
        "ready": not reasons,
        "observed_case_count": len(cases),
        "admitted_case_count": len(complete_ids & expected_ids),
        "reasons": reasons,
        "cases": cases,
    }


def _hca_capacity(
    cell: PrimaryCell, row: Mapping[str, Any] | None
) -> dict[str, Any]:
    reasons: list[str] = []
    expected_repeats = 2 if cell.group == "stable_speed" else 1
    if row is None:
        reasons.append("matching HCA row is missing")
        counts: list[Any] = []
    else:
        if row.get("primary_capacity_eligible") is not True:
            reasons.append("HCA row is not admitted capacity evidence")
        if row.get("protocol_status") not in {
            "FIXED_HORIZON_CAPACITY",
            "FULL_POPULATION_TIMING",
        }:
            reasons.append("HCA row has no fixed-horizon capacity status")
        if _integer(row.get("fixed_raw_bag_denominator")) != (
            cell.fixed_raw_bag_denominator
        ):
            reasons.append("HCA fixed denominator does not match the manifest")
        if _integer(row.get("fixed_segment_population")) != (
            cell.fixed_segment_population
        ):
            reasons.append("HCA segment population does not match the manifest")
        if (
            _integer(row.get("repeats_expected")) != expected_repeats
            or _integer(row.get("repeats_complete")) != expected_repeats
        ):
            reasons.append("HCA repeat count is incomplete")
        counts = row.get("completed_raw_bag_count_by_repeat", [])
    normalized = (
        [_integer(value) for value in counts]
        if isinstance(counts, list) and len(counts) == expected_repeats
        else []
    )
    if (
        len(normalized) != expected_repeats
        or any(
            value is None or not 0 <= value <= cell.fixed_raw_bag_denominator
            for value in normalized
        )
        or len(set(normalized)) != 1
    ):
        reasons.append("HCA completion counts are missing or inconsistent")
    completed = normalized[0] if normalized and not reasons else None
    full_population = bool(
        completed == cell.fixed_raw_bag_denominator
        and row
        and row.get("full_population_completion") is True
    )
    timing_ready = bool(
        cell.group == "stable_speed"
        and full_population
        and row
        and row.get("formal_timing_comparison_allowed") is True
        and row.get("timing_scope") == "FULL_POPULATION"
    )
    return {
        "ready": not reasons,
        "completed_raw_bags": completed,
        "full_population_completed": full_population,
        "full_population_timing_ready": timing_ready,
        "reasons": reasons,
    }


def _native_capacity(
    cell: PrimaryCell, case: Mapping[str, Any] | None
) -> dict[str, Any]:
    reasons: list[str] = []
    if case is None:
        reasons.append("matching native case is missing")
    else:
        if case.get("schema") != NATIVE_CASE_SCHEMA:
            reasons.append("native case schema does not match G31")
        if case.get("status") != g31_native.COMPLETE:
            reasons.append("native case is not admitted capacity evidence")
        if _integer(_path(case, "selection", "scale")) != cell.scale:
            reasons.append("native workload scale does not match")
        if _integer(_path(case, "selection", "selected_raw_bag_count")) != (
            cell.fixed_raw_bag_denominator
        ):
            reasons.append("native fixed denominator does not match the manifest")
        if _integer(_path(case, "selection", "selected_segment_count")) != (
            cell.fixed_segment_population
        ):
            reasons.append("native segment population does not match the manifest")
        if _integer(_path(case, "outcome", "success", "denominator_raw_bags")) != (
            cell.fixed_raw_bag_denominator
        ):
            reasons.append("native outcome denominator does not match")
        if _path(case, "safety", "pass") is not True:
            reasons.append("native safety admission is not passed")
        if _number(_path(case, "request_contract", "max_simulation_time")) != (
            g31_native.FIXED_END_EPOCH
        ):
            reasons.append("native fixed horizon does not match")
        if _integer(_path(case, "request_contract", "max_events")) != (
            g31_native.MAX_EVENTS
        ):
            reasons.append("native event budget does not match")
        if _path(case, "runtime", "event_limit_reached") is not False:
            reasons.append("native event budget was exhausted")
    completed = _integer(_path(case, "outcome", "completed_raw_bag_count"))
    if completed is None or not 0 <= completed <= cell.fixed_raw_bag_denominator:
        reasons.append("native completion numerator is missing")
        completed = None
    full_population = completed == cell.fixed_raw_bag_denominator
    timing = case.get("timing") if case else None
    timing_ready = bool(
        cell.group == "stable_speed"
        and full_population
        and isinstance(timing, Mapping)
        and timing.get("status") == "S4_FULL_POPULATION_DESCRIPTIVE"
        and timing.get("population") == "all_selected_raw_bags_complete"
        and _integer(timing.get("raw_bag_count")) == cell.fixed_raw_bag_denominator
        and isinstance(_path(timing, "distributions", "processed_attempt"), Mapping)
    )
    return {
        "ready": not reasons,
        "completed_raw_bags": completed,
        "full_population_completed": full_population,
        "full_population_timing_ready": timing_ready,
        "topology_upper_raw_bags": _integer(
            _path(case, "safety", "topology", "topology_reachable_raw_bag_upper_bound")
        ),
        "reasons": reasons,
    }


def _capacity_verdict(
    s4_completed: int, hca_completed: int, denominator: int, topology_upper: int | None
) -> str:
    if s4_completed > hca_completed:
        return "S4_WIN"
    if s4_completed < hca_completed:
        return "HCA_WIN"
    if s4_completed == denominator:
        return "FULL_POPULATION_CEILING_TIE"
    if topology_upper is not None and s4_completed == topology_upper:
        return "TOPOLOGY_UPPER_TIE"
    return "UNRESOLVED_TIE"


def _capacity_quantitative_summary(
    nanning_rows: Sequence[Mapping[str, Any]],
    map2_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Derive compact W/T/L and fixed-denominator deltas from report rows."""

    entries: list[dict[str, Any]] = []
    for map_label, map_id, source_rows, nested_capacity in (
        ("nanning", MAP_ID, nanning_rows, True),
        ("map2", map2_native.MAP_ID, map2_rows, False),
    ):
        for row in source_rows:
            capacity = row.get("capacity") if nested_capacity else row
            if not isinstance(capacity, Mapping):
                capacity = {}
            entries.append(
                {
                    "map": map_label,
                    "map_id": map_id,
                    "scale": row.get("scale"),
                    "case_group": row.get("case_group"),
                    "denominator": row.get("fixed_raw_bag_denominator"),
                    "s4": capacity.get("s4_completed_raw_bags"),
                    "hca": capacity.get("hca_completed_raw_bags"),
                    "verdict": capacity.get("verdict"),
                    "evidence_ready": capacity.get("evidence_ready") is True,
                }
            )

    evaluated_verdicts = {
        "S4_WIN",
        "HCA_WIN",
        "FULL_POPULATION_CEILING_TIE",
        "TOPOLOGY_UPPER_TIE",
        "UNRESOLVED_TIE",
    }

    def summarize(members: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        ready = bool(members) and all(
            member["evidence_ready"]
            and _integer(member["denominator"]) is not None
            and _integer(member["s4"]) is not None
            and _integer(member["hca"]) is not None
            and member["verdict"] in evaluated_verdicts
            for member in members
        )
        if not ready:
            return {
                "evaluation_status": NOT_EVALUATED_PARTIAL,
                "case_count": len(members),
                "strict_wins": None,
                "ties": None,
                "strict_losses": None,
                "cumulative_s4_minus_hca_completed_bags": None,
                "average_s4_minus_hca_percentage_points": None,
            }
        deltas = [int(member["s4"]) - int(member["hca"]) for member in members]
        percentage_points = [
            delta / int(member["denominator"]) * 100.0
            for delta, member in zip(deltas, members, strict=True)
        ]
        return {
            "evaluation_status": "EVALUATED_COMPLETE_CAPACITY_ROWS",
            "case_count": len(members),
            "strict_wins": sum(member["verdict"] == "S4_WIN" for member in members),
            "ties": sum(str(member["verdict"]).endswith("TIE") for member in members),
            "strict_losses": sum(member["verdict"] == "HCA_WIN" for member in members),
            "cumulative_s4_minus_hca_completed_bags": sum(deltas),
            "average_s4_minus_hca_percentage_points": round(
                sum(percentage_points) / len(percentage_points), 6
            ),
        }

    groups: list[dict[str, Any]] = []
    for map_label, map_id in (
        ("nanning", MAP_ID),
        ("map2", map2_native.MAP_ID),
    ):
        for scale in (1, 2):
            for case_group in ("stable_speed", "all_day_line_interruption"):
                members = [
                    entry
                    for entry in entries
                    if entry["map"] == map_label
                    and entry["scale"] == scale
                    and entry["case_group"] == case_group
                ]
                groups.append(
                    {
                        "map": map_label,
                        "map_id": map_id,
                        "scale": scale,
                        "group": (
                            "stable"
                            if case_group == "stable_speed"
                            else "fault"
                        ),
                        **summarize(members),
                    }
                )
    total = summarize(entries)
    return {
        "status": (
            "EVALUATED_COMPLETE_CROSS_MAP_CAPACITY"
            if total["evaluation_status"] == "EVALUATED_COMPLETE_CAPACITY_ROWS"
            else NOT_EVALUATED_PARTIAL
        ),
        "groups": groups,
        "cross_map_total": total,
    }


def build_report(
    manifests: Mapping[int, Mapping[str, Any] | None],
    hca_aggregate: Mapping[str, Any] | None,
    native_aggregate: Mapping[str, Any] | None,
    *,
    paired_artifacts: Mapping[float, Mapping[str, Any] | None] | None = None,
    bias_aggregate: Mapping[str, Any] | None = None,
    map2_aggregate: Mapping[str, Any] | None = None,
    map2_hca_1x_report: Mapping[str, Any] | None = None,
    map2_hca_2x_aggregate: Mapping[str, Any] | None = None,
    map2_paired_artifacts: Mapping[float, Mapping[str, Any] | None] | None = None,
    map2_bias_aggregate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an in-memory G31 diagnostic or final cross-map report."""

    cells = primary_cells()
    workload = {
        str(scale): _manifest_summary(manifests.get(scale), scale)
        for scale in FIXED_POPULATIONS
    }
    hca = _hca_aggregate_summary(hca_aggregate, cells)
    native = _native_aggregate_summary(native_aggregate, cells)
    paired_timing = _paired_timing_summary(paired_artifacts)
    bias_context = _bias_context_summary(bias_aggregate)
    map2_evidence = _map2_evidence_summary(
        map2_aggregate,
        map2_hca_1x_report,
        map2_hca_2x_aggregate,
        map2_paired_artifacts,
    )
    map2_bias_context = _map2_bias_context_summary(map2_bias_aggregate)

    evidence: list[tuple[PrimaryCell, dict[str, Any], dict[str, Any]]] = []
    for cell in cells:
        hca_evidence = _hca_capacity(cell, hca["rows"].get(cell.hca_case_id))
        native_evidence = _native_capacity(
            cell, native["cases"].get(cell.native_case_id)
        )
        evidence.append((cell, hca_evidence, native_evidence))

    matrix_ready = bool(
        all(summary["ready"] for summary in workload.values())
        and hca["ready"]
        and native["ready"]
        and all(hca_row["ready"] and s4_row["ready"] for _, hca_row, s4_row in evidence)
    )
    rows: list[dict[str, Any]] = []
    for cell, hca_row, s4_row in evidence:
        capacity_reasons = [*hca_row["reasons"], *s4_row["reasons"]]
        verdict = NOT_EVALUATED_PARTIAL
        if matrix_ready:
            verdict = _capacity_verdict(
                int(s4_row["completed_raw_bags"]),
                int(hca_row["completed_raw_bags"]),
                cell.fixed_raw_bag_denominator,
                s4_row["topology_upper_raw_bags"],
            )
        paired_slot = next(
            (
                slot
                for slot in paired_timing["slots"]
                if cell.scale == 1 and slot["speed_mps"] == cell.speed_mps
            ),
            None,
        )
        if cell.group == "all_day_line_interruption":
            timing_status = "FAULT_CAPACITY_ONLY_NOT_RELEASE_PAIRED"
        elif cell.scale == 2:
            timing_status = "SAME_RELEASE_TIMING_NOT_REGISTERED_FOR_2X"
        elif cell.speed_mps == 1.5:
            timing_status = "N_A_HCA_BASELINE_INCOMPLETE"
        elif paired_slot and paired_slot["ready"]:
            timing_status = "ELIGIBLE_FULL_POPULATION_SAME_HCA_RELEASE"
        else:
            timing_status = "SAME_RELEASE_TIMING_ARTIFACT_NOT_AVAILABLE"
        rows.append(
            {
                "native_case_id": cell.native_case_id,
                "hca_case_id": cell.hca_case_id,
                "paper_table": "5.2" if cell.group == "stable_speed" else "5.5",
                "case_group": cell.group,
                "scale": cell.scale,
                "speed_mps": cell.speed_mps,
                "fault_scenario": cell.fault_scenario,
                "fixed_raw_bag_denominator": cell.fixed_raw_bag_denominator,
                "fixed_segment_population": cell.fixed_segment_population,
                "capacity": {
                    "evidence_ready": hca_row["ready"] and s4_row["ready"],
                    "s4_completed_raw_bags": s4_row["completed_raw_bags"],
                    "hca_completed_raw_bags": hca_row["completed_raw_bags"],
                    "s4_topology_upper_raw_bags": s4_row[
                        "topology_upper_raw_bags"
                    ],
                    "verdict": verdict,
                    "not_ready_reasons": capacity_reasons,
                },
                "timing": {
                    "status": timing_status,
                    "requires_both_full_population": True,
                    "survivor_only_allowed": False,
                    "cross_algorithm_verdict_source": (
                        "same_HCA_release_full_population_artifact"
                        if paired_slot and paired_slot.get("ready")
                        else None
                    ),
                    "same_release_timing_slot_status": (
                        paired_slot.get("status") if paired_slot else None
                    ),
                    "own_source_timing_cross_algorithm_verdict_allowed": False,
                    "hca_full_population_completed": hca_row[
                        "full_population_completed"
                    ],
                    "s4_full_population_completed": s4_row[
                        "full_population_completed"
                    ],
                    "fault_release_pairing": (
                        "NOT_RELEASE_PAIRED"
                        if cell.group == "all_day_line_interruption"
                        else "NOT_APPLICABLE"
                    ),
                },
            }
        )

    verdict_counts: dict[str, int] = {}
    capacity_target_acceptable = False
    if matrix_ready:
        for row in rows:
            verdict = str(_path(row, "capacity", "verdict"))
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
        capacity_target_acceptable = all(
            _path(row, "capacity", "verdict")
            in {"S4_WIN", "FULL_POPULATION_CEILING_TIE", "TOPOLOGY_UPPER_TIE"}
            for row in rows
        )

    target_ready = bool(
        matrix_ready and paired_timing["all_required_artifacts_ready"]
    )
    target_met = (
        bool(
            capacity_target_acceptable
            and paired_timing["all_metrics_acceptable_for_fresh_target"]
        )
        if target_ready
        else None
    )
    if not matrix_ready:
        target_status = NOT_EVALUATED_PARTIAL
    elif not paired_timing["all_required_artifacts_ready"]:
        target_status = "NOT_EVALUATED_PAIRED_TIMING_INCOMPLETE"
    else:
        target_status = "EVALUATED_COMPLETE_PRIMARY_AND_PAIRED_EVIDENCE"
    cross_map_ready = bool(target_ready and map2_evidence["ready"])
    cross_map_target_met = (
        bool(target_met and map2_evidence["target_met"])
        if cross_map_ready
        else None
    )
    capacity_quantitative = _capacity_quantitative_summary(
        rows, map2_evidence["capacity"]["rows"]
    )
    return {
        "schema": SCHEMA,
        "status": MATRIX_READY if matrix_ready else PARTIAL_DIAGNOSTIC,
        "map_id": MAP_ID,
        "protocol": {
            "primary_case_count": EXPECTED_PRIMARY_CASES,
            "stable_speed_case_count": EXPECTED_STABLE_CASES,
            "fault_capacity_case_count": EXPECTED_FAULT_CASES,
            "capacity_evaluated_before_timing": True,
            "timing_requires_both_full_population": True,
            "survivor_only_timing_allowed": False,
            "fault_release_paired": False,
            "capacity_release_alignment": (
                "same_scheduled_population_fixed_horizon_each_framework_own_source_admission"
            ),
            "capacity_is_segment_release_paired": False,
            "stable_cross_algorithm_timing_source": (
                "same_HCA_release_full_population_artifacts_only"
            ),
            "cross_framework_min_candidate_boundary": {
                "status": PHYSICAL_SEMANTICS_RESOLUTION_TIE,
                "eligible_metric": "min",
                "maximum_absolute_difference_seconds": (
                    PHYSICAL_SEMANTICS_RESOLUTION_SECONDS
                ),
                "requires_same_release_full_population": True,
                "counts_as_win": False,
                "final_policy": "ACTIVE_REPORTING_RULE",
            },
            "own_source_timing_cross_algorithm_verdict_allowed": False,
        },
        "input_diagnostics": {
            "workloads": workload,
            "hca": {key: value for key, value in hca.items() if key != "rows"},
            "native": {
                key: value for key, value in native.items() if key != "cases"
            },
            "paired_timing": {
                "status": paired_timing["status"],
                "eligible_artifact_count": paired_timing[
                    "eligible_artifact_count"
                ],
                "required_artifact_count": paired_timing[
                    "required_artifact_count"
                ],
            },
            "bias_context_status": bias_context["status"],
            "map2_context_status": map2_evidence["status"],
            "map2_bias_context_status": map2_bias_context["status"],
            "portable_matrix_complete": matrix_ready,
            "cross_map_evidence_complete": cross_map_ready,
        },
        "primary_rows": rows,
        "capacity_summary": {
            "evaluation_status": (
                "EVALUATED_COMPLETE_MATRIX" if matrix_ready else NOT_EVALUATED_PARTIAL
            ),
            "verdict_counts": verdict_counts,
            "acceptable_for_fresh_target": (
                capacity_target_acceptable if matrix_ready else None
            ),
        },
        "capacity_quantitative_summary": capacity_quantitative,
        "same_hca_release_timing": paired_timing,
        "paper_context": {
            "table_5_3": {
                "status": "UNAVAILABLE_FOR_FRESH_NANNING_COMPARISON",
                "drives_fresh_target": False,
            },
            "table_5_4": {
                "status": (
                    "NON_EXACT_CONTEXT_AVAILABLE_BOTH_MAPS"
                    if bias_context["ready"] and map2_bias_context["ready"]
                    else "NON_EXACT_CONTEXT_PARTIAL_OR_UNAVAILABLE"
                ),
                "available_in_fresh_nanning_matrix": bias_context["ready"],
                "drives_fresh_target": False,
                "protocol_fidelity": bias31.PROTOCOL_FIDELITY,
                "bias_aggregate": bias_context,
                "maps": {
                    "nanning": bias_context,
                    "map2": map2_bias_context,
                },
                "cross_algorithm_verdict_generated": False,
            },
        },
        "map2_context": map2_evidence,
        "fresh_target": {
            "evaluation_status": target_status,
            "target_met": target_met,
            "final_policy_pending": not target_ready,
            "table_5_3_or_5_4_drives_target": False,
            "map2_drives_nanning_target": False,
            "rubric": {
                "capacity_requires_all_40_cells": True,
                "capacity_allows_only_s4_win_or_physical_topology_ceiling_tie": True,
                "timing_requires_three_eligible_same_release_artifacts": True,
                "timing_requires_s4_lower_except_min_resolution_tie": True,
                "speed_1p5_timing_excluded_as_incomplete_hca_baseline": True,
                "own_source_timing_used": False,
                "bias_non_exact_context_used": False,
            },
        },
        "cross_map_target": {
            "evaluation_status": (
                "EVALUATED_COMPLETE_NANNING_AND_MAP2_EVIDENCE"
                if cross_map_ready
                else "NOT_EVALUATED_MAP2_EVIDENCE_INCOMPLETE"
            ),
            "target_met": cross_map_target_met,
            "required_maps": [MAP_ID, map2_native.MAP_ID],
            "nanning_target_met": target_met,
            "map2_target_met": map2_evidence["target_met"],
            "requires_map2_38_capacity_cells": True,
            "requires_map2_four_1x_same_release_artifacts": True,
            "map2_2x_timing_status": "N_A_HCA_FULL_POPULATION_TIMING_UNAVAILABLE",
        },
    }


def _final_evidence_ready(payload: Mapping[str, Any]) -> bool:
    return bool(
        payload.get("status") == MATRIX_READY
        and _path(
            payload,
            "same_hca_release_timing",
            "all_required_artifacts_ready",
        )
        is True
        and _path(payload, "fresh_target", "evaluation_status")
        == "EVALUATED_COMPLETE_PRIMARY_AND_PAIRED_EVIDENCE"
        and isinstance(_path(payload, "fresh_target", "target_met"), bool)
        and _path(payload, "map2_context", "ready") is True
        and _path(payload, "cross_map_target", "evaluation_status")
        == "EVALUATED_COMPLETE_NANNING_AND_MAP2_EVIDENCE"
        and isinstance(_path(payload, "cross_map_target", "target_met"), bool)
    )


def _csv_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in payload["primary_rows"]:
        capacity = row["capacity"]
        rows.append(
            {
                "section": "primary_capacity",
                "case_id": row["native_case_id"],
                "scale": row["scale"],
                "speed_mps": row["speed_mps"],
                "fault_scenario": row["fault_scenario"],
                "metric": "completed_raw_bags",
                "s4_value": capacity["s4_completed_raw_bags"],
                "hca_value": capacity["hca_completed_raw_bags"],
                "fixed_denominator": row["fixed_raw_bag_denominator"],
                "verdict": capacity["verdict"],
                "evidence_status": (
                    "ADMITTED" if capacity["evidence_ready"] else "NOT_READY"
                ),
            }
        )
    for slot in payload["same_hca_release_timing"]["slots"]:
        if slot.get("ready") is not True:
            continue
        for metric in slot["metric_rows"]:
            rows.append(
                {
                    "section": "same_hca_release_timing",
                    "case_id": slot["case_id"],
                    "scale": slot["scale"],
                    "speed_mps": slot["speed_mps"],
                    "fault_scenario": None,
                    "metric": metric["metric"],
                    "s4_value": metric["s4_seconds"],
                    "hca_value": metric["hca_seconds"],
                    "fixed_denominator": FIXED_POPULATIONS[1]["raw_bags"],
                    "verdict": metric["verdict"],
                    "evidence_status": slot["status"],
                }
            )
    for row in payload["map2_context"]["capacity"]["rows"]:
        rows.append(
            {
                "section": "map2_primary_capacity",
                "case_id": row["case_id"],
                "scale": row["scale"],
                "speed_mps": row["speed_mps"],
                "fault_scenario": row["fault_scenario"],
                "metric": "completed_raw_bags",
                "s4_value": row["s4_completed_raw_bags"],
                "hca_value": row["hca_completed_raw_bags"],
                "fixed_denominator": row["fixed_raw_bag_denominator"],
                "verdict": row["verdict"],
                "evidence_status": (
                    "ADMITTED" if row["evidence_ready"] else "NOT_READY"
                ),
            }
        )
    for slot in payload["map2_context"]["same_hca_release_timing"]["slots_1x"]:
        if slot.get("ready") is not True:
            continue
        for metric in slot["metric_rows"]:
            rows.append(
                {
                    "section": "map2_same_hca_release_timing",
                    "case_id": slot["case_id"],
                    "scale": 1,
                    "speed_mps": slot["speed_mps"],
                    "fault_scenario": None,
                    "metric": metric["metric"],
                    "s4_value": metric["s4_seconds"],
                    "hca_value": metric["hca_seconds"],
                    "fixed_denominator": map2_native.SCALE_COUNTS[1][0],
                    "verdict": metric["verdict"],
                    "evidence_status": slot["status"],
                }
            )
    return rows


def render_csv(payload: Mapping[str, Any]) -> str:
    fields = (
        "section",
        "case_id",
        "scale",
        "speed_mps",
        "fault_scenario",
        "metric",
        "s4_value",
        "hca_value",
        "fixed_denominator",
        "verdict",
        "evidence_status",
    )
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(_csv_rows(payload))
    return stream.getvalue()


def _display(value: Any, digits: int = 3) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_markdown(payload: Mapping[str, Any]) -> str:
    capacity = payload["capacity_summary"]
    quantitative = payload["capacity_quantitative_summary"]
    paired = payload["same_hca_release_timing"]
    map2 = payload["map2_context"]
    table_5_4 = payload["paper_context"]["table_5_4"]
    map2_bias_context = table_5_4["maps"]["map2"]
    cross_map = payload["cross_map_target"]
    lines = [
        "# G31 原地图与南宁机场跨地图验证报告",
        "",
        f"状态：`{payload['status']}`。",
        "",
        f"南宁：`fresh_target_met={str(payload['fresh_target']['target_met']).lower()}`。",
        f"跨地图：`cross_map_target_met={str(cross_map['target_met']).lower()}`。",
        "",
        "stable/fault capacity 使用相同 scheduled population 和固定时域，"
        "但各自进行 source admission，并非逐 segment release-paired；"
        "只有 paired 章节比较 same-HCA-release timing。",
        "",
        "Table 5.4 是 `NON_EXACT` 上下文，不驱动上述两个 exact target；"
        "map2 证据参与跨地图判定，但不改写南宁自身的 fresh 判定。",
        "",
        "## 容量量化摘要",
        "",
        "| map | scale | group | strict W/T/strict L | S4-HCA completed | avg percentage points |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for row in quantitative["groups"]:
        lines.append(
            f"| {row['map']} | {row['scale']}× | {row['group']} | "
            f"{_display(row['strict_wins'])}/{_display(row['ties'])}/"
            f"{_display(row['strict_losses'])} | "
            f"{_display(row['cumulative_s4_minus_hca_completed_bags'])} | "
            f"{_display(row['average_s4_minus_hca_percentage_points'], 2)} |"
        )
    total = quantitative["cross_map_total"]
    lines.extend(
        [
            "",
            (
                "跨地图容量合计："
                f"`{_display(total['strict_wins'])}W / "
                f"{_display(total['ties'])}T / "
                f"{_display(total['strict_losses'])}L`；"
                "累计 S4-HCA 完成件数 "
                f"`{_display(total['cumulative_s4_minus_hca_completed_bags'])}`；"
                "平均 "
                f"`{_display(total['average_s4_minus_hca_percentage_points'], 2)}` 个百分点。"
            ),
            "",
            "容量先按固定总体比较；时延只使用 same-HCA-release 且双方全人口完成的证据。",
        ]
    )
    lines.extend(
        [
            "",
            "## 固定时域容量（8 个稳定速度 + 32 个线路中断）",
            "",
            f"Verdicts：`{json.dumps(capacity['verdict_counts'], ensure_ascii=False, sort_keys=True)}`。",
            "",
            "| case | scale | speed | fault | S4/HCA completed | denominator | verdict |",
            "|---|---:|---:|---|---:|---:|---|",
        ]
    )
    for row in payload["primary_rows"]:
        cell = row["capacity"]
        lines.append(
            "| "
            f"{row['native_case_id']} | {row['scale']}× | {row['speed_mps']:.1f} | "
            f"{row['fault_scenario'] or '-'} | "
            f"{cell['s4_completed_raw_bags']} / {cell['hca_completed_raw_bags']} | "
            f"{row['fixed_raw_bag_denominator']} | {cell['verdict']} |"
        )
    lines.extend(
        [
            "",
            "## Same-HCA-release 全人口时延",
            "",
            "1.5 m/s 因 corrected HCA 未完成全人口而严格 N/A；2.0、2.5、3.0 m/s "
            "各比较 min/mean/P95/P99/max。min 差值不超过 1 ms 只记物理语义分辨率平局。",
            "",
            f"Verdicts：`{json.dumps(paired['verdict_counts'], ensure_ascii=False, sort_keys=True)}`。",
            "",
            "| speed | metric | S4/HCA seconds | verdict |",
            "|---:|---|---:|---|",
        ]
    )
    for slot in paired["slots"]:
        if slot.get("ready") is not True:
            continue
        for metric in slot["metric_rows"]:
            lines.append(
                f"| {slot['speed_mps']:.1f} | {metric['metric']} | "
                f"{_display(metric['s4_seconds'])} / {_display(metric['hca_seconds'])} | "
                f"{metric['verdict']} |"
            )
    lines.extend(
        [
            "",
            "## 原地图 map2 固定时域容量（8 个稳定速度 + 30 个可测线路中断）",
            "",
            f"状态：`{map2['status']}`；Verdicts：`{json.dumps(map2['capacity']['verdict_counts'], ensure_ascii=False, sort_keys=True)}`。",
            "",
            "`pair_5_7` 的两个尺度均因既有线路标签冲突记 NM，不计入 38 个可测 cell。",
            "",
            "| case | scale | speed | fault | S4/HCA completed | denominator | verdict |",
            "|---|---:|---:|---|---:|---:|---|",
        ]
    )
    for row in map2["capacity"]["rows"]:
        lines.append(
            "| "
            f"{row['case_id']} | {row['scale']}× | {row['speed_mps']:.1f} | "
            f"{row['fault_scenario'] or '-'} | "
            f"{row['s4_completed_raw_bags']} / {row['hca_completed_raw_bags']} | "
            f"{row['fixed_raw_bag_denominator']} | {row['verdict']} |"
        )
    map2_timing = map2["same_hca_release_timing"]
    lines.extend(
        [
            "",
            "## 原地图 map2 same-HCA-release 全人口时延",
            "",
            "1× 四种速度各比较 min/mean/P95/P99/max；min 的绝对差不超过 1 ms 记物理语义分辨率平局。2× HCA 未完成全人口，因此四种速度的时延均严格 N/A。",
            "",
            f"Verdicts：`{json.dumps(map2_timing['verdict_counts'], ensure_ascii=False, sort_keys=True)}`。",
            "",
            "| speed | metric | S4/HCA seconds | verdict |",
            "|---:|---|---:|---|",
        ]
    )
    for slot in map2_timing["slots_1x"]:
        if slot.get("ready") is not True:
            continue
        for metric in slot["metric_rows"]:
            lines.append(
                f"| {slot['speed_mps']:.1f} | {metric['metric']} | "
                f"{_display(metric['s4_seconds'])} / {_display(metric['hca_seconds'])} | "
                f"{metric['verdict']} |"
            )
    lines.extend(
        [
            "",
            "## 原地图 map2 Table 5.4 NON_EXACT 上下文",
            "",
            (
                f"状态：`{map2_bias_context['status']}`；"
                f"protocol=`{map2_bias_context['protocol_fidelity']}`；"
                f"admitted={map2_bias_context['admitted_case_count']}/24；"
                f"all_safety_pass={str(map2_bias_context['all_safety_pass']).lower()}；"
                "只报告 S4 自身描述性结果，不把 unperturbed HCA 当作 matched arm，"
                "也不生成跨算法胜负。"
            ),
            "",
            "| case | scale | speed | label | U(0,k s) | S4 completed/denominator | percent | timing status |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in map2_bias_context["descriptive_s4_results"]:
        lines.append(
            f"| {row['case_id']} | {row['scale']}× | "
            f"{row['standard_speed_mps']:.1f} | {row['deviation_percent']}% | "
            f"{row['maximum_observation_delay_seconds']:.1f} | "
            f"{_display(row['s4_completed_raw_bags'])}/"
            f"{row['fixed_raw_bag_denominator']} | "
            f"{_display(row['s4_completion_percent'], 2)} | "
            f"{row['s4_timing_status'] or 'N/A'} |"
        )
    lines.extend(
        [
            "",
            "## 证据边界",
            "",
            f"- Table 5.4 bias：`{table_5_4['status']}`，仅上下文，不产生跨算法胜负。",
            f"- map2：`{map2['status']}`；只有 38 个容量 cell 与 4 个 1× paired artifact 全部齐备后才形成跨地图结论。",
            "- 运行策略固定为 S4/J2/E2 + 节点局部 FIFO + service-aware static potential；"
            "每个转向点只决定下一条边，不使用运行时完整 A* 或 learning。",
            "",
        ]
    )
    return "\n".join(lines)


def _read_optional(path: Path) -> Mapping[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise Reporting31Error(f"JSON input is not an object: {path}")
    return value


def _read_paired_directory(
    directory: Path,
) -> dict[float, Mapping[str, Any] | None]:
    return {
        speed: _read_optional(directory / f"{_paired_case_id(speed)}.json")
        for speed in PAIRED_TIMING_SPEEDS
    }


def _read_map2_paired_directory(
    directory: Path,
) -> dict[float, Mapping[str, Any] | None]:
    return {
        speed: _read_optional(
            directory / f"t5_2_map2_1x_speed_{_speed_token(speed)}.json"
        )
        for speed in map2_native.SPEEDS_MPS
    }


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
    parser.add_argument("--manifest-1x", type=Path, default=DEFAULT_MANIFEST_1X)
    parser.add_argument("--manifest-2x", type=Path, default=DEFAULT_MANIFEST_2X)
    parser.add_argument("--hca-aggregate", type=Path, default=DEFAULT_HCA)
    parser.add_argument("--native-aggregate", type=Path, default=DEFAULT_NATIVE)
    parser.add_argument("--paired-dir", type=Path, default=DEFAULT_PAIRED_DIR)
    parser.add_argument("--bias-aggregate", type=Path, default=DEFAULT_BIAS)
    parser.add_argument("--map2-aggregate", type=Path, default=DEFAULT_MAP2)
    parser.add_argument("--map2-hca-1x-report", type=Path, default=DEFAULT_MAP2_HCA_1X)
    parser.add_argument("--map2-hca-2x-aggregate", type=Path, default=DEFAULT_MAP2_HCA_2X)
    parser.add_argument("--map2-paired-dir", type=Path, default=DEFAULT_MAP2_PAIRED_DIR)
    parser.add_argument("--map2-bias-aggregate", type=Path, default=DEFAULT_MAP2_BIAS)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv-output", type=Path, default=DEFAULT_CSV)
    parser.add_argument(
        "--markdown-output", type=Path, default=DEFAULT_MARKDOWN
    )
    parser.add_argument("--validate-committed", action="store_true")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help=(
            "return non-zero until Nanning 40-cell/3-paired and map2 "
            "38-cell/4-paired evidence are complete"
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        payload = build_report(
            {
                1: _read_optional(args.manifest_1x),
                2: _read_optional(args.manifest_2x),
            },
            _read_optional(args.hca_aggregate),
            _read_optional(args.native_aggregate),
            paired_artifacts=_read_paired_directory(args.paired_dir),
            bias_aggregate=_read_optional(args.bias_aggregate),
            map2_aggregate=_read_optional(args.map2_aggregate),
            map2_hca_1x_report=_read_optional(args.map2_hca_1x_report),
            map2_hca_2x_aggregate=_read_optional(args.map2_hca_2x_aggregate),
            map2_paired_artifacts=_read_map2_paired_directory(
                args.map2_paired_dir
            ),
            map2_bias_aggregate=_read_optional(args.map2_bias_aggregate),
        )
        payload["portable_input_sources"] = {
            "manifest_1x": _relative(args.manifest_1x),
            "manifest_2x": _relative(args.manifest_2x),
            "hca_aggregate": _relative(args.hca_aggregate),
            "native_aggregate": _relative(args.native_aggregate),
            "paired_directory": _relative(args.paired_dir),
            "bias_aggregate": _relative(args.bias_aggregate),
            "map2_aggregate": _relative(args.map2_aggregate),
            "map2_hca_1x_report": _relative(args.map2_hca_1x_report),
            "map2_hca_2x_aggregate": _relative(args.map2_hca_2x_aggregate),
            "map2_paired_directory": _relative(args.map2_paired_dir),
            "map2_bias_aggregate": _relative(args.map2_bias_aggregate),
        }
        evidence_complete = _final_evidence_ready(payload)
        texts = {
            args.json_output: json.dumps(
                payload, ensure_ascii=False, indent=2, allow_nan=False
            )
            + "\n",
            args.csv_output: render_csv(payload),
            args.markdown_output: render_markdown(payload),
        }
        if args.validate_committed:
            if not evidence_complete:
                raise Reporting31Error(
                    "committed validation requires complete Nanning and map2 capacity/paired evidence"
                )
            for path, expected in texts.items():
                if not path.is_file():
                    raise Reporting31Error(
                        f"missing committed G31 report: {path}"
                    )
                if path.read_text(encoding="utf-8") != expected:
                    raise Reporting31Error(
                        f"committed G31 report is stale: {path}"
                    )
            print("G31 committed portable reporting validation: PASS")
            return 0
        final_outputs_written = False
        if evidence_complete:
            for path, text in texts.items():
                _write(path, text)
            final_outputs_written = True
    except (Reporting31Error, OSError, json.JSONDecodeError) as exc:
        print(f"G31 reporting failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": payload["status"],
                "primary_case_count": len(payload["primary_rows"]),
                "portable_matrix_complete": payload["input_diagnostics"][
                    "portable_matrix_complete"
                ],
                "paired_timing_status": payload["same_hca_release_timing"][
                    "status"
                ],
                "fresh_target_met": payload["fresh_target"]["target_met"],
                "cross_map_target_met": payload["cross_map_target"]["target_met"],
                "final_evidence_complete": evidence_complete,
                "final_outputs_written": final_outputs_written,
                "json": (
                    _relative(args.json_output) if final_outputs_written else None
                ),
                "csv": (
                    _relative(args.csv_output) if final_outputs_written else None
                ),
                "markdown": (
                    _relative(args.markdown_output)
                    if final_outputs_written
                    else None
                ),
            },
            ensure_ascii=False,
        )
    )
    return 2 if args.require_complete and not evidence_complete else 0


if __name__ == "__main__":
    raise SystemExit(main())
