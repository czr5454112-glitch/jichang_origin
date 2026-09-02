#!/usr/bin/env python3
"""Aggregate the preregistered CIE potential experiment without cohort leakage.

The S4 rows form a 2x2 factorial: H_FF/H_SA by dynamic terms off/full.
The CIE-DH rows are deliberately reported only as a common-executor adaptation
decomposition.  They are never labelled as native Feng DH evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA = "czr005.cie_potential_factorial.single_cell.v1"
TARGET_MAPS = ("map2", "nanning")
TARGET_SCALES = (1, 2)
S4_CELLS = (("ff", "off"), ("sa", "off"), ("ff", "full"), ("sa", "full"))
CIE_DH_CELLS = (("ff", "full"), ("sa", "full"))

METRICS = (
    ("completed_segment_count", "completed segments", "higher"),
    ("completed_raw_bag_count", "completed raw bags", "higher"),
    ("completion_rate", "raw-bag completion rate", "higher"),
    ("population_latency_mean_seconds", "population latency mean (s)", "lower"),
    ("population_latency_p95_seconds", "population latency P95 (s)", "lower"),
    ("population_latency_p99_seconds", "population latency P99 (s)", "lower"),
    ("population_latency_max_seconds", "population latency max (s)", "lower"),
    (
        "business_on_time_raw_bag_count",
        "fixed-denominator on-time raw bags",
        "higher",
    ),
    (
        "business_on_time_rate",
        "fixed-denominator on-time rate",
        "higher",
    ),
    (
        "business_missed_raw_bag_count",
        "fixed-denominator missed raw bags",
        "lower",
    ),
    (
        "business_missed_rate",
        "fixed-denominator missed rate",
        "lower",
    ),
    (
        "business_fixed_horizon_tardiness_sum_seconds",
        "fixed-horizon all-population tardiness sum (s)",
        "lower",
    ),
    (
        "business_fixed_horizon_tardiness_mean_seconds",
        "fixed-horizon all-population tardiness mean (s)",
        "lower",
    ),
    (
        "business_fixed_horizon_tardiness_p95_seconds",
        "fixed-horizon all-population tardiness P95 (s)",
        "lower",
    ),
    (
        "business_fixed_horizon_tardiness_p99_seconds",
        "fixed-horizon all-population tardiness P99 (s)",
        "lower",
    ),
    (
        "business_fixed_horizon_tardiness_max_seconds",
        "fixed-horizon all-population tardiness max (s)",
        "lower",
    ),
    (
        "business_time_to_90_percent_elapsed_seconds",
        "time to 90% completion from first arrival (s)",
        "lower",
    ),
    (
        "business_time_to_95_percent_elapsed_seconds",
        "time to 95% completion from first arrival (s)",
        "lower",
    ),
    (
        "business_time_to_99_percent_elapsed_seconds",
        "time to 99% completion from first arrival (s)",
        "lower",
    ),
    (
        "business_raw_total_backlog_area_seconds",
        "raw-bag total backlog area (bag-s)",
        "lower",
    ),
    (
        "business_raw_total_backlog_peak",
        "raw-bag total backlog peak",
        "lower",
    ),
    (
        "business_raw_total_backlog_end",
        "raw-bag total backlog at horizon end",
        "lower",
    ),
    (
        "business_raw_source_backlog_area_seconds",
        "raw-bag source backlog area (bag-s)",
        "lower",
    ),
    (
        "business_raw_source_backlog_peak",
        "raw-bag source backlog peak",
        "lower",
    ),
    (
        "business_raw_source_backlog_end",
        "raw-bag source backlog at horizon end",
        "lower",
    ),
    (
        "business_raw_network_backlog_area_seconds",
        "raw-bag network backlog area (bag-s)",
        "lower",
    ),
    (
        "business_raw_network_backlog_peak",
        "raw-bag network backlog peak",
        "lower",
    ),
    (
        "business_raw_network_backlog_end",
        "raw-bag network backlog at horizon end",
        "lower",
    ),
    (
        "pre_feasibility_component_raw_argmin_change_count_total",
        "pre-feasibility component raw-argmin counterfactual changes (total)",
        "diagnostic only",
    ),
    ("wall_seconds", "wall time (s)", "lower is compute only"),
    ("cpu_seconds", "CPU time (s)", "lower is compute only"),
)
TIMING_METRICS = {
    "population_latency_mean_seconds",
    "population_latency_p95_seconds",
    "population_latency_p99_seconds",
    "population_latency_max_seconds",
}
TARGET_STATUS_FIELDS = {
    "business_time_to_90_percent_elapsed_seconds": (
        "business_time_to_90_percent_status"
    ),
    "business_time_to_95_percent_elapsed_seconds": (
        "business_time_to_95_percent_status"
    ),
    "business_time_to_99_percent_elapsed_seconds": (
        "business_time_to_99_percent_status"
    ),
}

LONG_FIELDS = (
    "source_file",
    "schema",
    "status",
    "map",
    "scale",
    "policy",
    "policy_label",
    "potential",
    "potential_label",
    "dynamic",
    "cell_id",
    "release_mode",
    "coordination_protocol",
    "binary_sha256",
    "workload_sha256",
    "integrity_pass",
    "population_segment_count",
    "completed_segment_count",
    "population_raw_bag_count",
    "completed_raw_bag_count",
    "completion_rate",
    "full_population_complete",
    "timing_status",
    "population_latency_mean_seconds",
    "population_latency_p95_seconds",
    "population_latency_p99_seconds",
    "population_latency_max_seconds",
    "business_on_time_raw_bag_count",
    "business_on_time_rate",
    "business_missed_raw_bag_count",
    "business_missed_rate",
    "business_fixed_horizon_tardiness_sum_seconds",
    "business_fixed_horizon_tardiness_mean_seconds",
    "business_fixed_horizon_tardiness_p95_seconds",
    "business_fixed_horizon_tardiness_p99_seconds",
    "business_fixed_horizon_tardiness_max_seconds",
    "business_time_to_90_percent_status",
    "business_time_to_90_percent_elapsed_seconds",
    "business_time_to_95_percent_status",
    "business_time_to_95_percent_elapsed_seconds",
    "business_time_to_99_percent_status",
    "business_time_to_99_percent_elapsed_seconds",
    "business_raw_total_backlog_area_seconds",
    "business_raw_total_backlog_peak",
    "business_raw_total_backlog_end",
    "business_raw_source_backlog_area_seconds",
    "business_raw_source_backlog_peak",
    "business_raw_source_backlog_end",
    "business_raw_network_backlog_area_seconds",
    "business_raw_network_backlog_peak",
    "business_raw_network_backlog_end",
    "pre_feasibility_component_raw_argmin_counterfactual_scope",
    "pre_feasibility_component_raw_argmin_change_count_total",
    "wall_seconds",
    "cpu_seconds",
)

EFFECT_FIELDS = (
    "comparison_kind",
    "map",
    "scale",
    "policy",
    "policy_label",
    "metric",
    "metric_label",
    "preferred_direction",
    "comparison_status",
    "missing_cells",
    "ff_off",
    "sa_off",
    "ff_full",
    "sa_full",
    "potential_main_effect_sa_minus_ff",
    "dynamic_main_effect_full_minus_off",
    "interaction_difference_in_differences",
    "adaptation_contrast_sa_minus_ff",
)


class PotentialAggregationError(RuntimeError):
    """Raised when an input cannot be read without corrupting the aggregate."""


def _get(root: Mapping[str, Any], *path: str) -> Any:
    value: Any = root
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    return int(value) if isinstance(value, int) else result


def _completion_target(
    business: Mapping[str, Any], percentage: str
) -> tuple[str, int | float | None]:
    target = _get(
        business, "completion_targets", f"time_to_{percentage}_percent"
    )
    if not isinstance(target, Mapping):
        return "NOT_REPORTED", None
    reached = target.get("reached")
    if reached is False:
        return "NOT_REACHED", None
    if reached is not True:
        return "REACH_STATUS_NOT_REPORTED", None
    elapsed = _number(target.get("elapsed_from_first_arrival_seconds"))
    if elapsed is None:
        return "REACHED_ELAPSED_NOT_REPORTED", None
    return "REACHED", elapsed


def _pre_feasibility_raw_argmin_change_total(
    native: Mapping[str, Any],
) -> tuple[str, int | float | None]:
    activation = native.get("cie_component_activation")
    if not isinstance(activation, Mapping):
        return "NOT_REPORTED", None
    scope = str(activation.get("counterfactual_scope", "NOT_REPORTED"))
    if "pre_feasibility" not in scope:
        return scope, None
    components = activation.get("components")
    if not isinstance(components, Mapping) or not components:
        return scope, None
    values = [
        _number(component.get("counterfactual_raw_argmin_change_count"))
        for component in components.values()
        if isinstance(component, Mapping)
    ]
    if len(values) != len(components) or any(value is None for value in values):
        return scope, None
    return scope, sum(value for value in values if value is not None)


def _discover(input_roots: Iterable[Path]) -> list[tuple[Path, Mapping[str, Any]]]:
    paths: set[Path] = set()
    for root in input_roots:
        resolved = root.resolve(strict=True)
        candidates = [resolved] if resolved.is_file() else resolved.rglob("*.json")
        paths.update(path.resolve() for path in candidates)

    runs: list[tuple[Path, Mapping[str, Any]]] = []
    for path in sorted(paths, key=lambda value: str(value).casefold()):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PotentialAggregationError(f"cannot read JSON {path}: {exc}") from exc
        if not isinstance(data, Mapping) or data.get("schema") != SCHEMA:
            continue
        if data.get("native_execution_started") is not True:
            continue
        runs.append((path, data))
    return runs


def _run_row(path: Path, data: Mapping[str, Any]) -> dict[str, Any]:
    algorithm = data.get("algorithm")
    algorithm = algorithm if isinstance(algorithm, Mapping) else {}
    potential = data.get("potential")
    potential = potential if isinstance(potential, Mapping) else {}
    population = data.get("population")
    population = population if isinstance(population, Mapping) else {}
    capacity = _get(data, "paper_subjects", "fixed_horizon_capacity")
    capacity = capacity if isinstance(capacity, Mapping) else {}
    runtime = data.get("runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    native = runtime.get("native_summary")
    native = native if isinstance(native, Mapping) else runtime
    business = _get(data, "paper_subjects", "fixed_denominator_business")
    business = business if isinstance(business, Mapping) else {}
    tardiness = _get(
        business,
        "tardiness_seconds",
        "fixed_horizon_all_population_lower_bound",
    )
    tardiness = tardiness if isinstance(tardiness, Mapping) else {}
    backlog = business.get("backlog")
    backlog = backlog if isinstance(backlog, Mapping) else {}
    total_backlog = backlog.get("raw_bag_total")
    total_backlog = total_backlog if isinstance(total_backlog, Mapping) else {}
    source_backlog = backlog.get("raw_bag_source_until_all_segments_admitted")
    source_backlog = source_backlog if isinstance(source_backlog, Mapping) else {}
    network_backlog = backlog.get("raw_bag_network_after_all_segments_admitted")
    network_backlog = network_backlog if isinstance(network_backlog, Mapping) else {}
    target_90_status, target_90_elapsed = _completion_target(business, "90")
    target_95_status, target_95_elapsed = _completion_target(business, "95")
    target_99_status, target_99_elapsed = _completion_target(business, "99")
    component_scope, component_change_total = (
        _pre_feasibility_raw_argmin_change_total(native)
    )

    segment_population = _number(population.get("segment_count"))
    completed_segments = _number(native.get("completed_count"))
    raw_population = _number(
        capacity.get("denominator_raw_bags", population.get("raw_bag_count"))
    )
    completed_bags = _number(capacity.get("completed_raw_bag_count"))
    completion_rate = _number(capacity.get("completion_rate"))
    integrity_pass = _get(data, "execution_integrity", "pass") is True
    fully_complete = bool(
        integrity_pass
        and segment_population is not None
        and completed_segments == segment_population
        and raw_population is not None
        and completed_bags == raw_population
    )

    timing = _get(data, "paper_subjects", "full_population_raw_bag_timing")
    timing = timing if isinstance(timing, Mapping) else {}
    timing_status = str(timing.get("status", "TIMING_NOT_REPORTED"))
    timing_population = _number(timing.get("raw_bag_count"))
    survivor_flag = timing.get("survivor_or_common_cohort_used")
    formal_scale = data.get("scale")
    timing_valid = bool(
        fully_complete
        and formal_scale == 1
        and timing_status == "FULL_POPULATION_RAW_BAG_TIMING"
        and timing_population == raw_population
        and survivor_flag is False
    )
    series = _get(timing, "metrics_seconds", "paper_network_from_admission")
    series = series if timing_valid and isinstance(series, Mapping) else {}
    if timing_status == "FULL_POPULATION_RAW_BAG_TIMING" and not timing_valid:
        timing_status = (
            "REJECTED_2X_TIMING_BY_PROTOCOL"
            if formal_scale == 2
            else "REJECTED_NOT_VERIFIED_FULL_POPULATION"
        )

    release = data.get("release_protocol")
    release = release if isinstance(release, Mapping) else {}
    binary = data.get("binary")
    binary = binary if isinstance(binary, Mapping) else {}
    provenance = data.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    return {
        "source_file": str(path.resolve()),
        "schema": data.get("schema", ""),
        "status": data.get("status", "NOT_REPORTED"),
        "map": data.get("map", "NOT_REPORTED"),
        "scale": data.get("scale", "NOT_REPORTED"),
        "policy": algorithm.get("policy", "NOT_REPORTED"),
        "policy_label": algorithm.get("policy_label", "NOT_REPORTED"),
        "potential": potential.get("selected", "NOT_REPORTED"),
        "potential_label": potential.get("selected_label", "NOT_REPORTED"),
        "dynamic": algorithm.get("dynamic", "NOT_REPORTED"),
        "cell_id": algorithm.get("cell_id", "NOT_REPORTED"),
        "release_mode": release.get("mode", "NOT_REPORTED"),
        "coordination_protocol": algorithm.get(
            "coordination_protocol", "NOT_REPORTED"
        ),
        "binary_sha256": binary.get("sha256", "NOT_REPORTED"),
        "workload_sha256": provenance.get("workload_sha256", "NOT_REPORTED"),
        "integrity_pass": integrity_pass,
        "population_segment_count": segment_population,
        "completed_segment_count": completed_segments,
        "population_raw_bag_count": raw_population,
        "completed_raw_bag_count": completed_bags,
        "completion_rate": completion_rate,
        "full_population_complete": fully_complete,
        "timing_status": timing_status,
        "population_latency_mean_seconds": _number(series.get("mean")),
        "population_latency_p95_seconds": _number(series.get("p95")),
        "population_latency_p99_seconds": _number(series.get("p99")),
        "population_latency_max_seconds": _number(series.get("max")),
        "business_on_time_raw_bag_count": _number(
            business.get("on_time_raw_bag_count")
        ),
        "business_on_time_rate": _number(business.get("on_time_rate")),
        "business_missed_raw_bag_count": _number(
            business.get("missed_bag_count")
        ),
        "business_missed_rate": _number(business.get("missed_bag_rate")),
        "business_fixed_horizon_tardiness_sum_seconds": _number(
            tardiness.get("sum")
        ),
        "business_fixed_horizon_tardiness_mean_seconds": _number(
            tardiness.get("mean")
        ),
        "business_fixed_horizon_tardiness_p95_seconds": _number(
            tardiness.get("p95")
        ),
        "business_fixed_horizon_tardiness_p99_seconds": _number(
            tardiness.get("p99")
        ),
        "business_fixed_horizon_tardiness_max_seconds": _number(
            tardiness.get("max")
        ),
        "business_time_to_90_percent_status": target_90_status,
        "business_time_to_90_percent_elapsed_seconds": target_90_elapsed,
        "business_time_to_95_percent_status": target_95_status,
        "business_time_to_95_percent_elapsed_seconds": target_95_elapsed,
        "business_time_to_99_percent_status": target_99_status,
        "business_time_to_99_percent_elapsed_seconds": target_99_elapsed,
        "business_raw_total_backlog_area_seconds": _number(
            total_backlog.get("backlog_area_seconds")
        ),
        "business_raw_total_backlog_peak": _number(
            total_backlog.get("peak_backlog")
        ),
        "business_raw_total_backlog_end": _number(
            total_backlog.get("end_backlog")
        ),
        "business_raw_source_backlog_area_seconds": _number(
            source_backlog.get("backlog_area_seconds")
        ),
        "business_raw_source_backlog_peak": _number(
            source_backlog.get("peak_backlog")
        ),
        "business_raw_source_backlog_end": _number(
            source_backlog.get("end_backlog")
        ),
        "business_raw_network_backlog_area_seconds": _number(
            network_backlog.get("backlog_area_seconds")
        ),
        "business_raw_network_backlog_peak": _number(
            network_backlog.get("peak_backlog")
        ),
        "business_raw_network_backlog_end": _number(
            network_backlog.get("end_backlog")
        ),
        "pre_feasibility_component_raw_argmin_counterfactual_scope": (
            component_scope
        ),
        "pre_feasibility_component_raw_argmin_change_count_total": (
            component_change_total
        ),
        "wall_seconds": _number(runtime.get("wall_seconds")),
        "cpu_seconds": _number(runtime.get("cpu_seconds")),
    }


def _identity(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(key) for key in ("map", "scale", "policy", "potential", "dynamic"))


def _contract(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return tuple(
        row.get(key)
        for key in (
            "binary_sha256",
            "workload_sha256",
            "release_mode",
            "coordination_protocol",
            "population_segment_count",
            "population_raw_bag_count",
        )
    )


def _cell_label(cell: tuple[str, str]) -> str:
    return f"{cell[0]}/{cell[1]}"


def _effect_status(
    cells: Mapping[tuple[str, str], list[Mapping[str, Any]]],
    expected: Sequence[tuple[str, str]],
    metric: str,
) -> tuple[str, str, dict[tuple[str, str], Mapping[str, Any]]]:
    missing = [cell for cell in expected if not cells.get(cell)]
    if missing:
        return (
            "MISSING_CELLS",
            ";".join(_cell_label(cell) for cell in missing),
            {},
        )
    duplicates = [cell for cell in expected if len(cells[cell]) != 1]
    if duplicates:
        return (
            "AMBIGUOUS_DUPLICATE_CELLS",
            ";".join(_cell_label(cell) for cell in duplicates),
            {},
        )
    selected = {cell: cells[cell][0] for cell in expected}
    if len({_contract(row) for row in selected.values()}) != 1:
        return "INCOMPARABLE_CONTRACT_MISMATCH", "", selected
    if any(_number(row.get(metric)) is None for row in selected.values()):
        target_status_field = TARGET_STATUS_FIELDS.get(metric)
        if target_status_field is not None:
            unavailable = [
                cell
                for cell, row in selected.items()
                if _number(row.get(metric)) is None
            ]
            target_statuses = {
                str(selected[cell].get(target_status_field, "NOT_REPORTED"))
                for cell in unavailable
            }
            status = (
                "METRIC_NOT_AVAILABLE_TARGET_NOT_REACHED"
                if "NOT_REACHED" in target_statuses
                else "METRIC_NOT_REPORTED"
            )
            return (
                status,
                ";".join(_cell_label(cell) for cell in unavailable),
                selected,
            )
        status = (
            "METRIC_NOT_AVAILABLE_FULL_POPULATION_REQUIRED"
            if metric in TIMING_METRICS
            else "METRIC_NOT_REPORTED"
        )
        return status, "", selected
    return "COMPLETE", "", selected


def _effect_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    indexed: dict[tuple[Any, ...], list[Mapping[str, Any]]] = {}
    for row in rows:
        indexed.setdefault(_identity(row), []).append(row)

    effects: list[dict[str, Any]] = []
    metric_labels = {name: (label, direction) for name, label, direction in METRICS}
    for map_name in TARGET_MAPS:
        for scale in TARGET_SCALES:
            for policy, expected, kind, policy_label in (
                (
                    "s4",
                    S4_CELLS,
                    "S4_TWO_BY_TWO_FACTORIAL",
                    "G31_S4_NEUTRAL_FIFO",
                ),
                (
                    "cie_dh",
                    CIE_DH_CELLS,
                    "CIE_DH_COMMON_EXECUTOR_ADAPTATION_ONLY_NOT_NATIVE_FENG",
                    "CIE_DH_COMMON_EXECUTOR_ADAPTED_NOT_EXACT",
                ),
            ):
                cells = {
                    cell: indexed.get((map_name, scale, policy, *cell), [])
                    for cell in expected
                }
                for metric, _, _ in METRICS:
                    status, missing, selected = _effect_status(cells, expected, metric)
                    values = {
                        cell: _number(selected.get(cell, {}).get(metric))
                        for cell in expected
                    }
                    row: dict[str, Any] = {
                        "comparison_kind": kind,
                        "map": map_name,
                        "scale": scale,
                        "policy": policy,
                        "policy_label": policy_label,
                        "metric": metric,
                        "metric_label": metric_labels[metric][0],
                        "preferred_direction": metric_labels[metric][1],
                        "comparison_status": status,
                        "missing_cells": missing,
                        "ff_off": values.get(("ff", "off")),
                        "sa_off": values.get(("sa", "off")),
                        "ff_full": values.get(("ff", "full")),
                        "sa_full": values.get(("sa", "full")),
                        "potential_main_effect_sa_minus_ff": None,
                        "dynamic_main_effect_full_minus_off": None,
                        "interaction_difference_in_differences": None,
                        "adaptation_contrast_sa_minus_ff": None,
                    }
                    if status == "COMPLETE" and policy == "s4":
                        ff0 = float(values[("ff", "off")])
                        sa0 = float(values[("sa", "off")])
                        ff1 = float(values[("ff", "full")])
                        sa1 = float(values[("sa", "full")])
                        row["potential_main_effect_sa_minus_ff"] = (
                            (sa0 + sa1) - (ff0 + ff1)
                        ) / 2.0
                        row["dynamic_main_effect_full_minus_off"] = (
                            (ff1 + sa1) - (ff0 + sa0)
                        ) / 2.0
                        row["interaction_difference_in_differences"] = (
                            (sa1 - ff1) - (sa0 - ff0)
                        )
                    elif status == "COMPLETE" and policy == "cie_dh":
                        row["adaptation_contrast_sa_minus_ff"] = float(
                            values[("sa", "full")]
                        ) - float(values[("ff", "full")])
                    effects.append(row)
    return effects


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
                    field: "" if row.get(field) is None else row.get(field, "")
                    for field in fields
                }
            )
    os.replace(temporary, path)


def _display(value: Any) -> str:
    number = _number(value)
    if number is None:
        return "—"
    if isinstance(number, int):
        return str(number)
    return f"{number:.6g}"


def _write_report(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
    effects: Sequence[Mapping[str, Any]],
    figure_status: str,
) -> None:
    complete_runs = sum(row.get("status") == "COMPLETE" for row in rows)
    timing_runs = sum(
        row.get("timing_status") == "FULL_POPULATION_RAW_BAG_TIMING"
        for row in rows
    )
    lines = [
        "# CIE potential factorial and adaptation decomposition",
        "",
        "## Evidence status",
        "",
        f"- Executed input runs discovered: **{len(rows)}**; status COMPLETE: **{complete_runs}**.",
        f"- Verified full-population timing runs: **{timing_runs}**.",
        f"- Figure: `{figure_status}`.",
        "- Population latency is reported only for integrity-passing, fully completed raw-bag populations with an explicit non-survivor timing contract; the 2× THT gate remains N/A.",
        "- Fixed-denominator business outcomes retain incomplete bags and are comparable at 1× and 2×. Unreached 90/95/99% completion targets stay blank with an explicit status.",
        "- Component raw-argmin changes are pre-feasibility counterfactual scorer diagnostics, not final-action changes.",
        "- Effect signs are raw differences, not claims of statistical significance. For completion, higher is preferred; for latency, lower is preferred; wall/CPU are compute cost only.",
        "",
        "## S4 neutral-FIFO 2×2 potential × dynamic factorial",
        "",
        "`potential main = mean(H_SA) - mean(H_FF)`; `dynamic main = mean(full) - mean(off)`; interaction is the difference-in-differences.",
        "",
        "| map | scale | metric | status | H_FF/off | H_SA/off | H_FF/full | H_SA/full | potential main | dynamic main | interaction |",
        "|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for effect in effects:
        if effect["policy"] != "s4":
            continue
        lines.append(
            "| {map} | {scale} | {metric} | {status}{missing} | {ff0} | {sa0} | {ff1} | {sa1} | {pe} | {de} | {ie} |".format(
                map=effect["map"],
                scale=effect["scale"],
                metric=effect["metric_label"],
                status=effect["comparison_status"],
                missing=(
                    f" ({effect['missing_cells']})" if effect["missing_cells"] else ""
                ),
                ff0=_display(effect["ff_off"]),
                sa0=_display(effect["sa_off"]),
                ff1=_display(effect["ff_full"]),
                sa1=_display(effect["sa_full"]),
                pe=_display(effect["potential_main_effect_sa_minus_ff"]),
                de=_display(effect["dynamic_main_effect_full_minus_off"]),
                ie=_display(effect["interaction_difference_in_differences"]),
            )
        )

    lines.extend(
        [
            "",
            "## CIE-DH common-executor adaptation decomposition",
            "",
            "This is an H_FF versus H_SA adaptation contrast in the common C++ executor. It is **not native Feng DH**, is not merged into the S4 factorial, and is not used for a cross-protocol ranking.",
            "",
            "| map | scale | metric | status | H_FF/full | H_SA/full | H_SA − H_FF |",
            "|---|---:|---|---|---:|---:|---:|",
        ]
    )
    for effect in effects:
        if effect["policy"] != "cie_dh":
            continue
        lines.append(
            "| {map} | {scale} | {metric} | {status}{missing} | {ff} | {sa} | {contrast} |".format(
                map=effect["map"],
                scale=effect["scale"],
                metric=effect["metric_label"],
                status=effect["comparison_status"],
                missing=(
                    f" ({effect['missing_cells']})" if effect["missing_cells"] else ""
                ),
                ff=_display(effect["ff_full"]),
                sa=_display(effect["sa_full"]),
                contrast=_display(effect["adaptation_contrast_sa_minus_ff"]),
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "Missing, duplicate, contract-mismatched, incomplete-population, and unreported cells remain explicit in the tables. No value is imputed, no survivor/common-cohort latency is substituted, and runtime cost is not treated as an algorithm-quality victory metric.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_figure(path: Path, effects: Sequence[Mapping[str, Any]]) -> str:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return "NOT_WRITTEN_MATPLOTLIB_UNAVAILABLE"

    selected_metrics = (
        "completion_rate",
        "population_latency_mean_seconds",
        "population_latency_p99_seconds",
    )
    figure, axes = plt.subplots(1, 3, figsize=(13.5, 4.2))
    for axis, metric in zip(axes, selected_metrics):
        subset = [
            row
            for row in effects
            if row["policy"] == "s4"
            and row["metric"] == metric
            and row["comparison_status"] == "COMPLETE"
        ]
        if not subset:
            axis.text(
                0.5,
                0.5,
                "No complete comparable cells",
                ha="center",
                va="center",
                transform=axis.transAxes,
            )
            axis.set_axis_off()
            continue
        labels = [f"{row['map']} {row['scale']}×" for row in subset]
        x = list(range(len(subset)))
        width = 0.24
        series = (
            ("potential_main_effect_sa_minus_ff", "H_SA−H_FF"),
            ("dynamic_main_effect_full_minus_off", "full−off"),
            ("interaction_difference_in_differences", "interaction"),
        )
        for offset, (field, label) in zip((-width, 0.0, width), series):
            axis.bar(
                [value + offset for value in x],
                [row[field] for row in subset],
                width=width,
                label=label,
            )
        axis.axhline(0.0, color="black", linewidth=0.8)
        axis.set_xticks(x, labels, rotation=25, ha="right")
        axis.set_title(next(label for name, label, _ in METRICS if name == metric))
        axis.grid(axis="y", alpha=0.25)
    axes[0].legend(fontsize=8)
    figure.suptitle("S4 potential × dynamic raw factorial effects")
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(figure)
    return "WRITTEN"


def aggregate(
    input_roots: Sequence[Path],
    long_csv: Path,
    effects_csv: Path,
    report: Path,
    figure: Path | None,
) -> tuple[int, str]:
    rows = [_run_row(path, data) for path, data in _discover(input_roots)]
    rows.sort(key=lambda row: tuple(str(value) for value in _identity(row)))
    effects = _effect_rows(rows)
    _write_csv(long_csv, LONG_FIELDS, rows)
    _write_csv(effects_csv, EFFECT_FIELDS, effects)
    figure_status = "NOT_REQUESTED" if figure is None else _write_figure(figure, effects)
    _write_report(report, rows, effects, figure_status)
    return len(rows), figure_status


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-root",
        action="append",
        type=Path,
        default=None,
        help="JSON file or directory; repeatable",
    )
    parser.add_argument(
        "--long-csv",
        type=Path,
        default=Path("outputs/tables/cie_potential_factorial_runs.csv"),
    )
    parser.add_argument(
        "--effects-csv",
        type=Path,
        default=Path("outputs/tables/cie_potential_factorial_effects.csv"),
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("outputs/reports/cie_potential_factorial_report.md"),
    )
    parser.add_argument(
        "--figure",
        type=Path,
        default=Path("outputs/figures/cie_potential_factorial_effects.png"),
    )
    parser.add_argument("--no-figure", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    roots = args.input_root or [
        Path("outputs/runtime/cie_revision/potential_factorial")
    ]
    try:
        count, figure_status = aggregate(
            roots,
            args.long_csv,
            args.effects_csv,
            args.report,
            None if args.no_figure else args.figure,
        )
    except (OSError, PotentialAggregationError) as exc:
        raise SystemExit(f"potential factorial aggregation failed: {exc}") from exc
    print(f"aggregated_runs={count} figure={figure_status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
