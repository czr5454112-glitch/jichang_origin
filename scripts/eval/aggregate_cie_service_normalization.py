#!/usr/bin/env python3
"""Aggregate the frozen CIE service-rate-normalization three-arm study.

Every comparison requires all three arms, a common binary/workload/request
identity, and passing native integrity.  Missing, failed, or non-full-population
timing cells remain explicit N/M values; they are never replaced with survivor
or common-cohort timing.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
for _bootstrap in (ROOT, ROOT / "src"):
    if str(_bootstrap) not in sys.path:
        sys.path.insert(0, str(_bootstrap))

from scripts.eval import aggregate_cie_potential_factorial as common  # noqa: E402
from scripts.eval import run_cie_service_normalization as runner  # noqa: E402


SUMMARY_SCHEMA = "czr005.cie_service_normalization.summary.v1"
DEFAULT_SUMMARY = ROOT / "outputs/tables/cie_service_normalization_summary.csv"
DEFAULT_REPORT = ROOT / "outputs/reports/cie_service_normalization_report.md"

# These are the original fixed-population business and latency subjects plus
# event/decision work.  No new optimization objective is introduced here.
METRICS = (
    ("completed_segment_count", "completed segments", "higher"),
    ("completed_raw_bag_count", "completed raw bags", "higher"),
    ("completion_rate", "raw-bag completion rate", "higher"),
    ("population_latency_min_seconds", "population latency minimum (s)", "lower"),
    ("population_latency_mean_seconds", "population latency mean (s)", "lower"),
    ("population_latency_p95_seconds", "population latency P95 (s)", "lower"),
    ("population_latency_p99_seconds", "population latency P99 (s)", "lower"),
    ("population_latency_max_seconds", "population latency maximum (s)", "lower"),
    ("business_on_time_raw_bag_count", "on-time raw bags", "higher"),
    ("business_on_time_rate", "on-time raw-bag rate", "higher"),
    ("business_missed_raw_bag_count", "missed raw bags", "lower"),
    ("business_missed_rate", "missed raw-bag rate", "lower"),
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
        "fixed-horizon all-population tardiness maximum (s)",
        "lower",
    ),
    (
        "business_time_to_90_percent_elapsed_seconds",
        "time to 90% completion (s)",
        "lower",
    ),
    (
        "business_time_to_95_percent_elapsed_seconds",
        "time to 95% completion (s)",
        "lower",
    ),
    (
        "business_time_to_99_percent_elapsed_seconds",
        "time to 99% completion (s)",
        "lower",
    ),
    (
        "business_raw_total_backlog_area_seconds",
        "raw-bag total backlog area (bag-s)",
        "lower",
    ),
    ("business_raw_total_backlog_peak", "raw-bag total backlog peak", "lower"),
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
    ("business_raw_source_backlog_peak", "raw-bag source backlog peak", "lower"),
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
    ("business_raw_network_backlog_peak", "raw-bag network backlog peak", "lower"),
    (
        "business_raw_network_backlog_end",
        "raw-bag network backlog at horizon end",
        "lower",
    ),
    ("event_count", "native event count", "diagnostic"),
    ("decision_count", "native decision count", "diagnostic"),
    ("wall_seconds", "wall time (s)", "compute only"),
    ("cpu_seconds", "CPU time (s)", "compute only"),
)

FIELDS = (
    "schema",
    "map",
    "scale",
    "service_condition",
    "service_time_multiplier",
    "comparison_status",
    "missing_or_failed_arms",
    "metric",
    "metric_label",
    "preferred_direction",
    "raw_count_as_seconds",
    "service_rate_normalized",
    "no_qi_but_calendar",
    "normalized_minus_raw",
    "normalized_relative_to_raw_percent",
    "normalized_outcome",
    "no_qi_minus_raw",
    "no_qi_relative_to_raw_percent",
    "no_qi_outcome",
    "comparison_identity_sha256",
    "timing_protocol",
    "source_files",
)


class ServiceNormalizationAggregationError(RuntimeError):
    """Raised when aggregate inputs are ambiguous or contradictory."""


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    return int(value) if isinstance(value, int) else result


def _get(root: Mapping[str, Any], *path: str) -> Any:
    value: Any = root
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            return None
        value = value[key]
    return value


def _discover(
    input_roots: Iterable[Path],
) -> list[tuple[Path, Mapping[str, Any]]]:
    paths: set[Path] = set()
    for root in input_roots:
        resolved = root.resolve(strict=True)
        candidates = [resolved] if resolved.is_file() else resolved.rglob("*.json")
        paths.update(path.resolve() for path in candidates)
    runs: list[tuple[Path, Mapping[str, Any]]] = []
    for path in sorted(paths, key=lambda item: str(item).casefold()):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ServiceNormalizationAggregationError(
                f"cannot read JSON {path}: {exc}"
            ) from exc
        if not isinstance(value, Mapping) or value.get("schema") != runner.SCHEMA:
            continue
        if value.get("native_execution_started") is not True:
            continue
        runs.append((path, value))
    return runs


def _arm_identity_ok(data: Mapping[str, Any], arm: str) -> bool:
    expected = runner.ARMS[arm]
    algorithm = data.get("algorithm")
    contract = data.get("service_normalization_contract")
    if not isinstance(algorithm, Mapping) or not isinstance(contract, Mapping):
        return False
    return bool(
        algorithm.get("queue_time_scaling") == expected["queue_time_scaling"]
        and algorithm.get("s4_score_component_mask")
        == expected["s4_score_component_mask"]
        and contract.get("no_qi_but_calendar_exact_existing_interface") is True
    )


def _metric_values(path: Path, data: Mapping[str, Any]) -> dict[str, Any]:
    values = common._run_row(path, data)
    timing = _get(
        data,
        "paper_subjects",
        "full_population_raw_bag_timing",
        "metrics_seconds",
        "paper_network_from_admission",
    )
    values["population_latency_min_seconds"] = (
        _number(timing.get("min"))
        if values.get("full_population_complete") is True
        and values.get("timing_status") == "FULL_POPULATION_RAW_BAG_TIMING"
        and isinstance(timing, Mapping)
        else None
    )
    native = _get(data, "runtime", "native_summary")
    native = native if isinstance(native, Mapping) else {}
    values["event_count"] = _number(native.get("event_count"))
    values["decision_count"] = _number(native.get("decision_count"))
    return values


def _outcome(delta: float | None, preferred: str) -> str:
    if delta is None:
        return "N/M"
    if abs(delta) <= 1.0e-12:
        return "TIE"
    if preferred == "higher":
        return "IMPROVED" if delta > 0.0 else "WORSE"
    if preferred == "lower":
        return "IMPROVED" if delta < 0.0 else "WORSE"
    return "DIAGNOSTIC_ONLY"


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temporary, path)


def aggregate(
    input_roots: Sequence[Path], summary_csv: Path, report_path: Path
) -> tuple[int, int]:
    """Write fixed three-arm contrasts for all four required groups."""

    discovered = _discover(input_roots)
    cells: dict[tuple[str, str, str], tuple[Path, Mapping[str, Any]]] = {}
    for path, data in discovered:
        map_name = str(data.get("map", ""))
        condition = str(data.get("service_condition", ""))
        arm = str(_get(data, "algorithm", "arm") or "")
        if map_name not in runner.MAPS or condition not in runner.SERVICE_CONDITIONS:
            raise ServiceNormalizationAggregationError(
                f"unregistered map/service condition in {path}"
            )
        if data.get("scale") != runner.SCALE or arm not in runner.ARMS:
            raise ServiceNormalizationAggregationError(
                f"unregistered scale/arm in {path}"
            )
        key = (map_name, condition, arm)
        if key in cells:
            raise ServiceNormalizationAggregationError(
                f"duplicate service-normalization cell {key}: "
                f"{cells[key][0]} and {path}"
            )
        cells[key] = (path, data)

    rows: list[dict[str, Any]] = []
    complete_groups = 0
    arm_order = tuple(runner.ARMS)
    cross_condition_identity_by_map = {
        map_name: {
            str(
                _get(
                    data,
                    "service_normalization_contract",
                    "cross_service_condition_identity_sha256",
                )
            )
            for (cell_map, _condition, _arm), (_path, data) in cells.items()
            if cell_map == map_name
        }
        for map_name in runner.MAPS
    }
    for map_name in runner.MAPS:
        for condition in runner.SERVICE_CONDITIONS:
            selected = {
                arm: cells.get((map_name, condition, arm)) for arm in arm_order
            }
            missing = [arm for arm, item in selected.items() if item is None]
            present = [item for item in selected.values() if item is not None]
            failed = [
                arm
                for arm, item in selected.items()
                if item is not None
                and (
                    item[1].get("status") != "COMPLETE"
                    or _get(item[1], "execution_integrity", "pass") is not True
                )
            ]
            bad_arm_identity = [
                arm
                for arm, item in selected.items()
                if item is not None and not _arm_identity_ok(item[1], arm)
            ]
            identity_values = {
                str(
                    _get(
                        item[1],
                        "service_normalization_contract",
                        "comparison_identity_sha256",
                    )
                )
                for item in present
            }
            multiplier_values = {
                _number(
                    _get(
                        item[1],
                        "service_normalization_contract",
                        "service_control",
                        "service_time_multiplier",
                    )
                )
                for item in present
            }
            expected_multiplier = 1.0 if condition == "REAL_SERVICE" else 2.0
            multiplier_ok = multiplier_values == {expected_multiplier}
            cross_condition_identity_values = cross_condition_identity_by_map[
                map_name
            ]
            cross_condition_identity_ok = (
                len(cross_condition_identity_values) == 1
                and "None" not in cross_condition_identity_values
            )
            if missing:
                group_status = "MISSING_CELLS"
                detail = missing
            elif failed:
                group_status = "FAILED_CELLS"
                detail = failed
            elif bad_arm_identity:
                group_status = "ARM_IDENTITY_MISMATCH"
                detail = bad_arm_identity
            elif len(identity_values) != 1 or "None" in identity_values:
                group_status = "COMPARISON_IDENTITY_MISMATCH"
                detail = list(identity_values)
            elif not multiplier_ok:
                group_status = "SERVICE_CONTROL_MISMATCH"
                detail = [str(value) for value in multiplier_values]
            elif not cross_condition_identity_ok:
                group_status = "CROSS_SERVICE_CONDITION_IDENTITY_MISMATCH"
                detail = sorted(cross_condition_identity_values)
            else:
                group_status = "COMPLETE"
                detail = []
                complete_groups += 1

            extracted = {
                arm: _metric_values(*item) if item is not None else {}
                for arm, item in selected.items()
            }
            identity = next(iter(identity_values)) if len(identity_values) == 1 else ""
            sources = ";".join(str(item[0]) for item in present)
            for metric, label, preferred in METRICS:
                values = {
                    arm: _number(extracted[arm].get(metric)) for arm in arm_order
                }
                metric_status = group_status
                metric_detail = list(detail)
                if group_status == "COMPLETE" and any(
                    value is None for value in values.values()
                ):
                    metric_status = "N_M_METRIC_NOT_AVAILABLE"
                    metric_detail = [
                        arm for arm, value in values.items() if value is None
                    ]
                raw = values["RAW_COUNT_AS_SECONDS"]
                normalized = values["SERVICE_RATE_NORMALIZED"]
                no_qi = values["NO_QI_BUT_CALENDAR"]
                normalized_delta = (
                    float(normalized) - float(raw)
                    if metric_status == "COMPLETE"
                    and normalized is not None
                    and raw is not None
                    else None
                )
                no_qi_delta = (
                    float(no_qi) - float(raw)
                    if metric_status == "COMPLETE"
                    and no_qi is not None
                    and raw is not None
                    else None
                )
                rows.append(
                    {
                        "schema": SUMMARY_SCHEMA,
                        "map": map_name,
                        "scale": runner.SCALE,
                        "service_condition": condition,
                        "service_time_multiplier": expected_multiplier,
                        "comparison_status": metric_status,
                        "missing_or_failed_arms": ";".join(metric_detail),
                        "metric": metric,
                        "metric_label": label,
                        "preferred_direction": preferred,
                        "raw_count_as_seconds": raw,
                        "service_rate_normalized": normalized,
                        "no_qi_but_calendar": no_qi,
                        "normalized_minus_raw": normalized_delta,
                        "normalized_relative_to_raw_percent": (
                            100.0 * normalized_delta / float(raw)
                            if normalized_delta is not None and raw not in (None, 0)
                            else None
                        ),
                        "normalized_outcome": _outcome(
                            normalized_delta, preferred
                        ),
                        "no_qi_minus_raw": no_qi_delta,
                        "no_qi_relative_to_raw_percent": (
                            100.0 * no_qi_delta / float(raw)
                            if no_qi_delta is not None and raw not in (None, 0)
                            else None
                        ),
                        "no_qi_outcome": _outcome(no_qi_delta, preferred),
                        "comparison_identity_sha256": identity,
                        "timing_protocol": (
                            "1x full-population raw-bag timing only; "
                            "no survivor/common cohort"
                        ),
                        "source_files": sources,
                    }
                )

    _write_csv(summary_csv, rows)
    report_lines = [
        "# CIE service-rate normalization three-arm audit",
        "",
        f"Executed input runs discovered: **{len(discovered)}** (expected 12).",
        f"Complete matched map/control groups: **{complete_groups}/4**.",
        "",
        "## Exact arm semantics",
        "",
        "- `RAW_COUNT_AS_SECONDS`: full mask 15 and raw Q/I counts.",
        "- `SERVICE_RATE_NORMALIZED`: full mask 15 and the existing "
        "`service_rate_normalized` Q/I scaling.",
        "- `NO_QI_BUT_CALENDAR`: mask 12, which removes Q/I while retaining "
        "corridor-calendar and target-service-calendar waits. Direct-neighbour "
        "calendar visibility and physical service calendars remain enabled.",
        "- `SERVICE_X2` comes only from the frozen manifest multiplier 2.0; "
        "topology, tasks, release, and all other G31 controls stay fixed.",
        "",
        "## Fixed comparisons",
        "",
        "| Map | Service | Metric | Status | Raw | Normalized | No Q/I | "
        "Norm - raw | No Q/I - raw |",
        "|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        report_lines.append(
            "| {map} | {service_condition} | {metric_label} | "
            "{comparison_status} | {raw_count_as_seconds} | "
            "{service_rate_normalized} | {no_qi_but_calendar} | "
            "{normalized_minus_raw} | {no_qi_minus_raw} |".format(
                **{
                    key: "N/M" if row.get(key) is None else row.get(key)
                    for key in row
                }
            )
        )
    report_lines.extend(
        [
            "",
            "## Interpretation boundary",
            "",
            "No incomplete timing cell is replaced by survivor timing; no "
            "survivor/common cohort is used. This "
            "aggregate does not select a winning arm or tune a parameter. A "
            "general service-normalization claim requires attributable, "
            "directionally consistent evidence on both real maps and the "
            "pre-specified service-pressure-enhancement control; otherwise the "
            "pre-specified "
            "stopping conclusion applies.",
            "",
        ]
    )
    _atomic_text(report_path, "\n".join(report_lines))
    return len(discovered), complete_groups


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    summary = args.summary_csv if args.summary_csv.is_absolute() else ROOT / args.summary_csv
    report = args.report if args.report.is_absolute() else ROOT / args.report
    existing = [path for path in (summary, report) if path.exists()]
    if existing and not args.force:
        raise ServiceNormalizationAggregationError(
            "output exists; pass --force to replace: "
            + ", ".join(str(path) for path in existing)
        )
    count, complete_groups = aggregate(args.input, summary, report)
    print(
        json.dumps(
            {
                "status": "COMPLETE" if complete_groups == 4 else "INCOMPLETE",
                "run_count": count,
                "complete_groups": complete_groups,
                "summary_csv": str(summary),
                "report": str(report),
            }
        )
    )
    return 0 if complete_groups == 4 else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ServiceNormalizationAggregationError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        print(f"CIE service-normalization aggregate failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
