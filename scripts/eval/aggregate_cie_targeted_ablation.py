#!/usr/bin/env python3
"""Aggregate the frozen 2x targeted CIE ablation matrix.

The input layout is fixed as ``<root>/<arm>/<map>_2x.json``.  Every registered
arm is enumerated on both maps; the tool never selects an arm from observed
outcomes.  Missing or invalid cells remain explicit ``NA`` values.  Because
these are 2x runs, full-population THT is always protocol-level N/A.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import run_cie_targeted_ablation as targeted
from scripts.eval import cie_backlog_area_correction as backlog_correction


MAPS = ("map2", "nanning")
ARMS = tuple(targeted.ARMS)
OPTIONAL_ARMS = ("FULL_MINUS_WC",)
MANDATORY_ARMS = tuple(arm for arm in ARMS if arm not in OPTIONAL_ARMS)
NA = "NA"

METRICS = (
    ("completed_raw_bag_count", "completed raw bags", "higher"),
    ("completion_rate", "completion rate", "higher"),
    ("on_time_raw_bag_count", "on-time raw bags", "higher"),
    ("on_time_rate", "on-time rate", "higher"),
    ("missed_bag_count", "missed raw bags", "lower"),
    ("missed_bag_rate", "missed rate", "lower"),
    ("tardiness_sum_seconds", "fixed-horizon tardiness sum (s)", "lower"),
    ("tardiness_mean_seconds", "fixed-horizon tardiness mean (s)", "lower"),
    ("tardiness_p95_seconds", "fixed-horizon tardiness P95 (s)", "lower"),
    ("tardiness_p99_seconds", "fixed-horizon tardiness P99 (s)", "lower"),
    ("backlog_area_seconds", "raw-bag backlog area (bag-s)", "lower"),
    ("backlog_peak", "raw-bag peak backlog", "lower"),
    ("backlog_end", "raw-bag end backlog", "lower"),
)
FIGURE_METRICS = (
    ("completed_raw_bag_count", "Completed bags"),
    ("on_time_raw_bag_count", "On-time bags"),
    ("missed_bag_count", "Missed bags"),
    ("tardiness_mean_seconds", "Tardiness mean (s)"),
    ("backlog_area_seconds", "Backlog area (bag-s)"),
)

RUN_FIELDS = (
    "source_file",
    "artifact_present",
    "cell_status",
    "artifact_status",
    "schema",
    "map",
    "scale",
    "arm",
    "artifact_map",
    "artifact_scale",
    "artifact_arm",
    "s4_score_component_mask",
    "integrity_pass",
    "execution_integrity_failed_gates",
    "request_identity_pass",
    "population_raw_bag_count",
    "population_segment_count",
    "business_denominator_raw_bags",
    "fixed_denominator",
    "survivor_or_common_cohort_used",
    "timing_status",
    "tht_mean_seconds",
    "tht_p95_seconds",
    "tht_p99_seconds",
    "completed_raw_bag_count",
    "completion_rate",
    "on_time_raw_bag_count",
    "on_time_rate",
    "missed_bag_count",
    "missed_bag_rate",
    "tardiness_sum_seconds",
    "tardiness_mean_seconds",
    "tardiness_p95_seconds",
    "tardiness_p99_seconds",
    "backlog_area_seconds",
    "backlog_area_legacy_seconds",
    "backlog_area_status",
    "backlog_area_method",
    "backlog_peak",
    "backlog_end",
    "base_full_s4_request_sha256",
    "binary_sha256",
    "runtime_loaded_binary_sha256",
    "binary_identity_match",
    "workload_sha256",
    "wall_seconds",
    "cpu_seconds",
    "pre_feasibility_raw_argmin_is_final_action",
)

PAIR_FIELDS = (
    "map",
    "scale",
    "arm",
    "full_reference_arm",
    "metric",
    "metric_label",
    "preferred_direction",
    "comparison_status",
    "arm_value",
    "full_s4_value",
    "delta_arm_minus_full_s4",
    "binary_sha256_match",
    "base_full_s4_request_sha256_match",
    "workload_sha256_match",
    "population_contract_match",
)


class TargetedAggregationError(RuntimeError):
    """Raised for an output-contract error, not for a missing experiment cell."""


def _nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return None
        current = current[key]
    return current


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        return None
    return int(value) if isinstance(value, int) else numeric


def _na_row(path: Path, map_name: str, arm: str, status: str) -> dict[str, Any]:
    row = {field: NA for field in RUN_FIELDS}
    row.update(
        {
            "source_file": str(path.resolve()),
            "artifact_present": path.exists(),
            "cell_status": status,
            "map": map_name,
            "scale": 2,
            "arm": arm,
            "s4_score_component_mask": targeted.ARMS[arm],
            "timing_status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL",
            "tht_mean_seconds": NA,
            "tht_p95_seconds": NA,
            "tht_p99_seconds": NA,
            "pre_feasibility_raw_argmin_is_final_action": False,
        }
    )
    return row


def _business_payload(data: Mapping[str, Any]) -> Mapping[str, Any]:
    outer = data.get("fixed_denominator_business")
    if not isinstance(outer, Mapping):
        return {}
    detailed = outer.get("detailed")
    return detailed if isinstance(detailed, Mapping) else outer


def _cell_status(
    data: Mapping[str, Any],
    row: Mapping[str, Any],
    *,
    expected_map: str,
    expected_arm: str,
) -> str:
    if data.get("schema") != targeted.SCHEMA:
        return "INVALID_SCHEMA"
    if data.get("native_execution_started") is not True:
        return "NOT_EXECUTED"
    if data.get("status") != "COMPLETE":
        if (
            data.get("status") == "FAILED_INTEGRITY"
            and _nested(data, "execution_integrity", "pass") is False
        ):
            return "FAILED_EXECUTION_INTEGRITY"
        return "ARTIFACT_NOT_COMPLETE"
    algorithm = data.get("algorithm")
    if not isinstance(algorithm, Mapping):
        return "INVALID_ALGORITHM_IDENTITY"
    if (
        data.get("map") != expected_map
        or data.get("scale") != 2
        or algorithm.get("arm") != expected_arm
        or algorithm.get("s4_score_component_mask")
        != targeted.ARMS[expected_arm]
    ):
        return "INVALID_CELL_IDENTITY"
    if _nested(data, "execution_integrity", "pass") is not True:
        return "FAILED_EXECUTION_INTEGRITY"
    if _nested(data, "ablation_contract", "identity_pass") is not True:
        return "FAILED_REQUEST_IDENTITY"
    base_request_sha = row.get("base_full_s4_request_sha256")
    if not isinstance(base_request_sha, str) or len(base_request_sha) != 64:
        return "INVALID_BASE_REQUEST_IDENTITY"
    binary_sha = row.get("binary_sha256")
    loaded_binary_sha = row.get("runtime_loaded_binary_sha256")
    if (
        not isinstance(binary_sha, str)
        or len(binary_sha) != 64
        or not isinstance(loaded_binary_sha, str)
        or len(loaded_binary_sha) != 64
        or binary_sha != loaded_binary_sha
    ):
        return "INVALID_BINARY_IDENTITY"
    if (
        row.get("population_raw_bag_count")
        != targeted.REGISTERED_2X_RAW_BAG_COUNT
        or row.get("population_segment_count")
        != targeted.REGISTERED_2X_SEGMENT_COUNT
    ):
        return "INVALID_2X_POPULATION"
    if (
        row.get("timing_status") != "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
        or _nested(data, "full_population_timing", "raw_bag_count") is not None
        or _nested(data, "full_population_timing", "distributions") is not None
        or _nested(
            data, "full_population_timing", "survivor_or_common_cohort_used"
        )
        is not False
    ):
        return "REJECTED_2X_TIMING_PROTOCOL_VIOLATION"
    if (
        row.get("fixed_denominator") is not True
        or row.get("survivor_or_common_cohort_used") is not False
        or row.get("business_denominator_raw_bags")
        != targeted.REGISTERED_2X_RAW_BAG_COUNT
        or row.get("business_denominator_raw_bags")
        != row.get("population_raw_bag_count")
    ):
        return "INVALID_FIXED_DENOMINATOR"
    required_metrics = [
        name for name, _label, _direction in METRICS
        if name != "backlog_area_seconds"
    ]
    if any(_number(row.get(name)) is None for name in required_metrics):
        return "BUSINESS_METRIC_NOT_REPORTED"
    denominator = int(row["business_denominator_raw_bags"])
    completed = int(row["completed_raw_bag_count"])
    on_time = int(row["on_time_raw_bag_count"])
    missed = int(row["missed_bag_count"])
    if (
        not 0 <= completed <= denominator
        or not 0 <= on_time <= denominator
        or missed != denominator - on_time
        or not math.isclose(float(row["completion_rate"]), completed / denominator)
        or not math.isclose(float(row["on_time_rate"]), on_time / denominator)
        or not math.isclose(float(row["missed_bag_rate"]), missed / denominator)
    ):
        return "INCONSISTENT_FIXED_DENOMINATOR_METRICS"
    return "COMPLETE"


def _read_cell(path: Path, map_name: str, arm: str) -> dict[str, Any]:
    if not path.exists():
        return _na_row(path, map_name, arm, "MISSING_CELL")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _na_row(path, map_name, arm, "INVALID_JSON")
    if not isinstance(data, Mapping):
        return _na_row(path, map_name, arm, "INVALID_JSON_OBJECT")

    row = _na_row(path, map_name, arm, "PENDING_VALIDATION")
    business = _business_payload(data)
    tardiness = _nested(
        business, "tardiness_seconds", "fixed_horizon_all_population_lower_bound"
    )
    tardiness = tardiness if isinstance(tardiness, Mapping) else {}
    backlog = _nested(business, "backlog", "raw_bag_total")
    backlog = backlog if isinstance(backlog, Mapping) else {}
    try:
        correction = backlog_correction.artifact_correction(data)["groups"][
            "raw_bag_total"
        ]
    except backlog_correction.BacklogAreaCorrectionError as exc:
        correction = {
            "corrected_area_seconds": None,
            "legacy_area_seconds": _number(backlog.get("backlog_area_seconds")),
            "status": f"N_M_{type(exc).__name__}",
            "reported_method": None,
        }
    provenance = data.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    runtime = data.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    native_summary = runtime.get("native_summary")
    native_summary = native_summary if isinstance(native_summary, Mapping) else {}
    execution = data.get("execution_integrity")
    execution = execution if isinstance(execution, Mapping) else {}
    execution_gates = execution.get("gates")
    execution_gates = execution_gates if isinstance(execution_gates, Mapping) else {}
    timing = data.get("full_population_timing")
    timing = timing if isinstance(timing, Mapping) else {}
    population = data.get("population")
    population = population if isinstance(population, Mapping) else {}
    algorithm = data.get("algorithm")
    algorithm = algorithm if isinstance(algorithm, Mapping) else {}
    row.update(
        {
            "artifact_present": True,
            "artifact_status": data.get("status", NA),
            "schema": data.get("schema", NA),
            "map": map_name,
            "scale": 2,
            "arm": arm,
            "artifact_map": data.get("map", NA),
            "artifact_scale": data.get("scale", NA),
            "artifact_arm": algorithm.get("arm", NA),
            "s4_score_component_mask": algorithm.get(
                "s4_score_component_mask", NA
            ),
            "integrity_pass": _nested(data, "execution_integrity", "pass"),
            "execution_integrity_failed_gates": ";".join(
                sorted(str(name) for name, value in execution_gates.items() if value is False)
            )
            or NA,
            "request_identity_pass": _nested(
                data, "ablation_contract", "identity_pass"
            ),
            "population_raw_bag_count": _number(
                population.get("raw_bag_denominator")
            ),
            "population_segment_count": _number(population.get("segment_count")),
            "business_denominator_raw_bags": _number(
                business.get("denominator_raw_bags")
            ),
            "fixed_denominator": business.get("fixed_denominator", NA),
            "survivor_or_common_cohort_used": business.get(
                "survivor_or_common_cohort_used", NA
            ),
            "timing_status": timing.get("status", "TIMING_NOT_REPORTED"),
            # These fields are intentionally never populated for 2x.
            "tht_mean_seconds": NA,
            "tht_p95_seconds": NA,
            "tht_p99_seconds": NA,
            "completed_raw_bag_count": _number(
                business.get("completed_raw_bag_count")
            ),
            "completion_rate": _number(business.get("completion_rate")),
            "on_time_raw_bag_count": _number(
                business.get("on_time_raw_bag_count")
            ),
            "on_time_rate": _number(business.get("on_time_rate")),
            "missed_bag_count": _number(business.get("missed_bag_count")),
            "missed_bag_rate": _number(business.get("missed_bag_rate")),
            "tardiness_sum_seconds": _number(tardiness.get("sum")),
            "tardiness_mean_seconds": _number(tardiness.get("mean")),
            "tardiness_p95_seconds": _number(tardiness.get("p95")),
            "tardiness_p99_seconds": _number(tardiness.get("p99")),
            "backlog_area_seconds": _number(
                correction.get("corrected_area_seconds")
            ),
            "backlog_area_legacy_seconds": _number(
                correction.get("legacy_area_seconds")
            ),
            "backlog_area_status": correction.get("status", NA),
            "backlog_area_method": correction.get("reported_method", NA),
            "backlog_peak": _number(backlog.get("peak_backlog")),
            "backlog_end": _number(backlog.get("end_backlog")),
            "base_full_s4_request_sha256": _nested(
                data, "ablation_contract", "base_full_s4_request_sha256"
            )
            or NA,
            "binary_sha256": provenance.get("binary_sha256", NA),
            "runtime_loaded_binary_sha256": native_summary.get(
                "loaded_cpp_binary_sha256", NA
            ),
            "binary_identity_match": (
                provenance.get("binary_sha256")
                == native_summary.get("loaded_cpp_binary_sha256")
                if provenance.get("binary_sha256") is not None
                and native_summary.get("loaded_cpp_binary_sha256") is not None
                else NA
            ),
            "workload_sha256": provenance.get("canonical_workload_sha256", NA),
            "wall_seconds": _number(runtime.get("wall_seconds")),
            "cpu_seconds": _number(runtime.get("cpu_seconds")),
            "pre_feasibility_raw_argmin_is_final_action": False,
        }
    )
    row["cell_status"] = _cell_status(
        data, row, expected_map=map_name, expected_arm=arm
    )
    return row


def collect_rows(input_root: Path) -> list[dict[str, Any]]:
    root = input_root.resolve()
    rows = [
        _read_cell(root / arm / f"{map_name}_2x.json", map_name, arm)
        for map_name in MAPS
        for arm in ARMS
    ]
    # A cell may be internally valid yet have been prepared from a different
    # full-S4 base request.  Such a cell remains visible but is not pairable.
    indexed = {(row["map"], row["arm"]): row for row in rows}
    for map_name in MAPS:
        reference = indexed[(map_name, "FULL_S4")]
        reference_sha = reference.get("base_full_s4_request_sha256")
        if reference.get("cell_status") != "COMPLETE":
            continue
        for arm_name in ARMS:
            row = indexed[(map_name, arm_name)]
            if (
                row.get("cell_status") == "COMPLETE"
                and row.get("base_full_s4_request_sha256") != reference_sha
            ):
                row["cell_status"] = "INVALID_BASE_REQUEST_MISMATCH"
    return rows


def _comparison_status(
    arm: Mapping[str, Any], reference: Mapping[str, Any], metric: str
) -> str:
    if arm.get("cell_status") == "INVALID_BASE_REQUEST_MISMATCH":
        return "INCOMPARABLE_BASE_REQUEST_MISMATCH"
    arm_complete = arm.get("cell_status") == "COMPLETE"
    full_complete = reference.get("cell_status") == "COMPLETE"
    if not arm_complete and not full_complete:
        return "MISSING_OR_INVALID_ARM_AND_FULL_S4"
    if not full_complete:
        return "MISSING_OR_INVALID_FULL_S4"
    if not arm_complete:
        return "MISSING_OR_INVALID_ARM"
    if arm.get("binary_sha256") != reference.get("binary_sha256"):
        return "INCOMPARABLE_BINARY_MISMATCH"
    if arm.get("workload_sha256") != reference.get("workload_sha256"):
        return "INCOMPARABLE_WORKLOAD_MISMATCH"
    population_fields = (
        "population_raw_bag_count",
        "population_segment_count",
        "business_denominator_raw_bags",
        "fixed_denominator",
        "timing_status",
    )
    if any(arm.get(key) != reference.get(key) for key in population_fields):
        return "INCOMPARABLE_POPULATION_PROTOCOL_MISMATCH"
    if _number(arm.get(metric)) is None or _number(reference.get(metric)) is None:
        return "METRIC_NA"
    return "SELF_REFERENCE" if arm.get("arm") == "FULL_S4" else "COMPLETE"


def paired_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed = {(row["map"], row["arm"]): row for row in rows}
    pairs: list[dict[str, Any]] = []
    for map_name in MAPS:
        reference = indexed[(map_name, "FULL_S4")]
        for arm_name in ARMS:
            arm = indexed[(map_name, arm_name)]
            for metric, label, direction in METRICS:
                status = _comparison_status(arm, reference, metric)
                arm_value = _number(arm.get(metric))
                full_value = _number(reference.get(metric))
                delta = (
                    float(arm_value) - float(full_value)
                    if status in {"COMPLETE", "SELF_REFERENCE"}
                    and arm_value is not None
                    and full_value is not None
                    else NA
                )
                pairs.append(
                    {
                        "map": map_name,
                        "scale": 2,
                        "arm": arm_name,
                        "full_reference_arm": "FULL_S4",
                        "metric": metric,
                        "metric_label": label,
                        "preferred_direction": direction,
                        "comparison_status": status,
                        "arm_value": arm_value if arm_value is not None else NA,
                        "full_s4_value": (
                            full_value if full_value is not None else NA
                        ),
                        "delta_arm_minus_full_s4": delta,
                        "binary_sha256_match": (
                            arm.get("binary_sha256")
                            == reference.get("binary_sha256")
                            if arm.get("cell_status") == "COMPLETE"
                            and reference.get("cell_status") == "COMPLETE"
                            else NA
                        ),
                        "base_full_s4_request_sha256_match": (
                            arm.get("base_full_s4_request_sha256")
                            == reference.get("base_full_s4_request_sha256")
                            if arm.get("cell_status") == "COMPLETE"
                            and reference.get("cell_status") == "COMPLETE"
                            else NA
                        ),
                        "workload_sha256_match": (
                            arm.get("workload_sha256")
                            == reference.get("workload_sha256")
                            if arm.get("cell_status") == "COMPLETE"
                            and reference.get("cell_status") == "COMPLETE"
                            else NA
                        ),
                        "population_contract_match": (
                            status
                            not in {
                                "INCOMPARABLE_POPULATION_PROTOCOL_MISMATCH",
                                "MISSING_OR_INVALID_ARM",
                                "MISSING_OR_INVALID_FULL_S4",
                                "MISSING_OR_INVALID_ARM_AND_FULL_S4",
                            }
                            if arm.get("cell_status") == "COMPLETE"
                            and reference.get("cell_status") == "COMPLETE"
                            else NA
                        ),
                    }
                )
    return pairs


def _write_csv(
    path: Path, fields: Sequence[str], rows: Sequence[Mapping[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: NA if row.get(field) is None else row.get(field, NA)
                    for field in fields
                }
            )
    os.replace(temporary, path)


def _display(value: Any) -> str:
    numeric = _number(value)
    if numeric is None:
        return NA
    if isinstance(numeric, int):
        return str(numeric)
    return f"{numeric:.6g}"


def _write_report(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    pairs: Sequence[Mapping[str, Any]],
    figure_status: str,
) -> None:
    status_counts = Counter(str(row["cell_status"]) for row in rows)
    pair_counts = Counter(str(row["comparison_status"]) for row in pairs)
    mandatory_complete = sum(
        row["cell_status"] == "COMPLETE" and row["arm"] in MANDATORY_ARMS
        for row in rows
    )
    mandatory_executed = sum(
        row["artifact_present"] is True
        and row["artifact_status"] not in {NA, "READY_CIE_TARGETED_ABLATION_DRY_RUN"}
        and row["arm"] in MANDATORY_ARMS
        for row in rows
    )
    optional_complete = sum(
        row["cell_status"] == "COMPLETE" and row["arm"] in OPTIONAL_ARMS
        for row in rows
    )
    lines = [
        "# CIE targeted 2× ablation audit",
        "",
        f"Mandatory cells: **{mandatory_executed}/{len(MAPS) * len(MANDATORY_ARMS)}** executed, "
        f"**{mandatory_complete}** integrity-admissible; "
        f"conditional `FULL_MINUS_WC`: **{optional_complete}/{len(MAPS) * len(OPTIONAL_ARMS)}**; "
        f"figure: `{figure_status}`.",
        "",
        "All registered arms were enumerated mechanically on both maps. No arm was selected, promoted, or removed from observed outcomes. Missing cells remain `NA`; no value is interpolated.",
        "",
        "`FULL_MINUS_WC` was pre-specified and frozen before result inspection as conditional on at least 100 wc counterfactual raw-argmin changes. The separate activation census recorded zero wc opportunities, so its missing cells are an intentional dormant-mechanism stop, not failed runs.",
        "",
        "The 2× THT columns are always `NA` under the frozen protocol. Business outcomes use the complete fixed raw-bag denominator, including incomplete bags through fixed-horizon tardiness lower bounds.",
        "",
        "Activation counters that compare pre-feasibility raw scorer argmins are diagnostics only. They are **not final-action changes** and are not used by this aggregator to rank or select arms.",
        "",
        "Executed cells that fail an integrity gate remain visible with their fixed-denominator diagnostic outcomes, but their paired effects are `NA` and they are excluded from paper-admissible comparisons.",
        "",
        "## Cell audit",
        "",
        "| map | arm | status | completed | on-time | missed | tardiness mean (s) | backlog area (bag-s) |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {map} | {arm} | {status} | {completed} | {on_time} | {missed} | {tardiness} | {backlog} |".format(
                map=row["map"],
                arm=row["arm"],
                status=row["cell_status"],
                completed=_display(row["completed_raw_bag_count"]),
                on_time=_display(row["on_time_raw_bag_count"]),
                missed=_display(row["missed_bag_count"]),
                tardiness=_display(row["tardiness_mean_seconds"]),
                backlog=_display(row["backlog_area_seconds"]),
            )
        )
    lines.extend(
        [
            "",
            "## Status counts",
            "",
            "Cell status: "
            + ", ".join(f"`{key}`={value}" for key, value in sorted(status_counts.items()))
            + ".",
            "",
            "Paired metric status: "
            + ", ".join(f"`{key}`={value}" for key, value in sorted(pair_counts.items()))
            + ".",
            "",
            "Every reported difference is `arm − FULL_S4` within the same map, binary, workload and fixed-population protocol. A raw sign is not a significance claim.",
            "",
            "Backlog area is the fixed-horizon corrected view. The run table preserves the legacy value and method; an incomplete legacy tail that cannot be reconstructed exactly is reported as N/M for that metric only.",
            "",
        ]
    )
    failed_rows = [
        row for row in rows if row["cell_status"] == "FAILED_EXECUTION_INTEGRITY"
    ]
    if failed_rows:
        lines.extend(
            [
                "## Failed integrity gates",
                "",
                "| map | arm | failed gates | interpretation |",
                "|---|---|---|---|",
            ]
        )
        for row in failed_rows:
            lines.append(
                f"| {row['map']} | {row['arm']} | "
                f"{row['execution_integrity_failed_gates']} | diagnostic outcomes retained; paired effect excluded |"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _write_figure(path: Path, rows: Sequence[Mapping[str, Any]]) -> str:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return "NOT_WRITTEN_MATPLOTLIB_UNAVAILABLE"

    indexed = {(row["map"], row["arm"]): row for row in rows}
    figure, axes = plt.subplots(2, 5, figsize=(20, 8.2), squeeze=False)
    colors = ["#303030"] + ["#4C78A8"] * (len(ARMS) - 1)
    for map_index, map_name in enumerate(MAPS):
        for metric_index, (metric, title) in enumerate(FIGURE_METRICS):
            axis = axes[map_index][metric_index]
            for arm_index, arm_name in enumerate(ARMS):
                row = indexed[(map_name, arm_name)]
                value = (
                    _number(row.get(metric))
                    if row.get("cell_status") == "COMPLETE"
                    else None
                )
                if value is None:
                    axis.text(
                        arm_index,
                        0.01,
                        "NA",
                        rotation=90,
                        ha="center",
                        va="bottom",
                        transform=axis.get_xaxis_transform(),
                        fontsize=6,
                        color="#A33",
                    )
                else:
                    axis.bar(arm_index, value, color=colors[arm_index], width=0.72)
            axis.set_xticks(range(len(ARMS)), ARMS, rotation=62, ha="right", fontsize=7)
            axis.set_title(f"{map_name}: {title}", fontsize=9)
            axis.grid(axis="y", alpha=0.25)
    figure.suptitle(
        "Targeted 2× ablations — fixed full-population business outcomes",
        fontsize=13,
    )
    figure.text(
        0.5,
        0.005,
        "NA = missing/invalid cell; no interpolation. Tardiness includes fixed-horizon lower bounds for incomplete bags.",
        ha="center",
        fontsize=8,
    )
    figure.tight_layout(rect=(0, 0.035, 1, 0.96))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(figure)
    return "WRITTEN"


def aggregate(
    *,
    input_root: Path,
    runs_csv: Path,
    paired_csv: Path,
    report: Path,
    figure: Path | None,
) -> tuple[int, str]:
    rows = collect_rows(input_root)
    pairs = paired_rows(rows)
    _write_csv(runs_csv, RUN_FIELDS, rows)
    _write_csv(paired_csv, PAIR_FIELDS, pairs)
    figure_status = "NOT_REQUESTED" if figure is None else _write_figure(figure, rows)
    _write_report(report, rows, pairs, figure_status)
    return sum(row["cell_status"] == "COMPLETE" for row in rows), figure_status


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("outputs/runtime/cie_revision/targeted_ablation"),
    )
    parser.add_argument(
        "--runs-csv",
        type=Path,
        default=Path("outputs/tables/cie_targeted_ablation_runs.csv"),
    )
    parser.add_argument(
        "--paired-csv",
        type=Path,
        default=Path("outputs/tables/cie_targeted_ablation_paired.csv"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("outputs/reports/cie_targeted_ablation_report.md"),
    )
    parser.add_argument(
        "--figure",
        type=Path,
        default=Path("outputs/figures/cie_targeted_ablation_business.png"),
    )
    parser.add_argument("--no-figure", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        complete, figure_status = aggregate(
            input_root=args.input_root,
            runs_csv=args.runs_csv,
            paired_csv=args.paired_csv,
            report=args.report,
            figure=None if args.no_figure else args.figure,
        )
    except (OSError, TargetedAggregationError) as exc:
        raise SystemExit(f"targeted ablation aggregation failed: {exc}") from exc
    print(
        f"complete_cells={complete}/{len(MAPS) * len(ARMS)} "
        f"mandatory_expected={len(MAPS) * len(MANDATORY_ARMS)} "
        f"conditional_optional_expected={len(MAPS) * len(OPTIONAL_ARMS)} "
        f"figure={figure_status}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
