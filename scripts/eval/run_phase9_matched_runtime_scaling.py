from __future__ import annotations

import csv
from datetime import date
import math
import os
import platform
from pathlib import Path
from statistics import mean, stdev
import sys
from time import get_clock_info, perf_counter
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
TABLE_PATH = ROOT / "outputs" / "tables" / "phase9_matched_runtime_scaling.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase9_matched_runtime_scaling_report.md"
REPEATS = int(os.environ.get("CZR005_MATCHED_RUNTIME_REPEATS", os.environ.get("CZR005_RUNTIME_REPEATS", "3")))


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    build_candidates = (
        Path(os.environ["CZR005_CPP_PYTHON_PATH"])
        if os.environ.get("CZR005_CPP_PYTHON_PATH")
        else None,
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
        BUILD_PYTHON_PATH,
    )
    for candidate in reversed([path for path in build_candidates if path is not None]):
        if candidate.exists() or str(candidate) == os.environ.get("CZR005_CPP_PYTHON_PATH"):
            sys.path.insert(0, str(candidate))


def _runtime_metadata() -> dict[str, float | int | str]:
    clock = get_clock_info("perf_counter")
    return {
        "repeat_count": REPEATS,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count() or 0,
        "timer": "perf_counter",
        "timer_resolution_seconds": clock.resolution,
    }


def _sample_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "std": 0.0, "ci95": 0.0, "min": 0.0, "max": 0.0}
    average = mean(values)
    if len(values) == 1:
        spread = 0.0
        ci95 = 0.0
    else:
        spread = stdev(values)
        ci95 = 1.96 * spread / math.sqrt(len(values))
    return {
        "mean": average,
        "std": spread,
        "ci95": ci95,
        "min": min(values),
        "max": max(values),
    }


def _timed(call: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], float]:
    started = perf_counter()
    payload = call()
    return payload, perf_counter() - started


def _stable_summary(
    matched: Any,
    family: str,
    summaries: list[dict[str, Any]],
    label: str,
) -> dict[str, Any]:
    if not summaries:
        raise ValueError(f"missing summaries for {label}")
    first = summaries[0]
    for index, summary in enumerate(summaries[1:], start=2):
        mismatch = matched._first_mismatch(family, first, summary)  # pylint: disable=protected-access
        if mismatch["field"] != "none":
            raise AssertionError(
                f"{label} summary changed on repeat {index}: "
                f"{mismatch['field']} {mismatch['python_value']} != {mismatch['cpp_value']}"
            )
    return first


def _row(
    matched: Any,
    scenario: Any,
    family: str,
    python_summary: dict[str, Any],
    python_elapsed_values: list[float],
    cpp_summary: dict[str, Any],
    cpp_elapsed_values: list[float],
    metadata: dict[str, float | int | str],
) -> dict[str, float | int | str | bool]:
    mismatch = matched._first_mismatch(family, python_summary, cpp_summary)  # pylint: disable=protected-access
    python_elapsed = _sample_stats(python_elapsed_values)
    cpp_elapsed = _sample_stats(cpp_elapsed_values)
    python_steps = matched._active_step_count(python_summary)  # pylint: disable=protected-access
    cpp_steps = matched._active_step_count(cpp_summary)  # pylint: disable=protected-access
    python_elapsed_mean = python_elapsed["mean"]
    cpp_elapsed_mean = cpp_elapsed["mean"]
    python_steps_per_second = python_steps / python_elapsed_mean if python_elapsed_mean > 0.0 else 0.0
    cpp_steps_per_second = cpp_steps / cpp_elapsed_mean if cpp_elapsed_mean > 0.0 else 0.0
    python_tasks_per_second = scenario.max_tasks / python_elapsed_mean if python_elapsed_mean > 0.0 else 0.0
    cpp_tasks_per_second = scenario.max_tasks / cpp_elapsed_mean if cpp_elapsed_mean > 0.0 else 0.0
    return {
        "scenario": scenario.name,
        "family": family,
        "task_offset": scenario.task_offset,
        "max_tasks": scenario.max_tasks,
        "fault_edges": matched._format_faults(scenario.fault_edges),  # pylint: disable=protected-access
        "fault_windows": matched._format_fault_windows(scenario.fault_windows),  # pylint: disable=protected-access
        "node_capacities": matched._format_node_capacities(scenario.node_capacities),  # pylint: disable=protected-access
        "merge_groups": matched._format_merge_groups(scenario.merge_groups),  # pylint: disable=protected-access
        "merge_capacity": scenario.merge_capacity,
        "merge_headway_seconds": scenario.merge_headway_seconds,
        "repeat_count": metadata["repeat_count"],
        "python_planned": matched._summary_int(python_summary, "planned_count"),  # pylint: disable=protected-access
        "cpp_planned": matched._summary_int(cpp_summary, "planned_count"),  # pylint: disable=protected-access
        "python_unplanned": matched._summary_int(python_summary, "unplanned_count"),  # pylint: disable=protected-access
        "cpp_unplanned": matched._summary_int(cpp_summary, "unplanned_count"),  # pylint: disable=protected-access
        "python_active_steps": python_steps,
        "cpp_active_steps": cpp_steps,
        "python_conflicts": matched._summary_int(  # pylint: disable=protected-access
            python_summary, "post_shield_conflicts"
        ),
        "cpp_conflicts": matched._summary_int(cpp_summary, "post_shield_conflicts"),  # pylint: disable=protected-access
        "python_mean_travel_time": matched._summary_float(  # pylint: disable=protected-access
            python_summary, "mean_travel_time"
        ),
        "cpp_mean_travel_time": matched._summary_float(cpp_summary, "mean_travel_time"),  # pylint: disable=protected-access
        "mean_travel_abs_diff": abs(
            matched._summary_float(python_summary, "mean_travel_time")  # pylint: disable=protected-access
            - matched._summary_float(cpp_summary, "mean_travel_time")  # pylint: disable=protected-access
        ),
        "makespan_abs_diff": abs(
            matched._summary_float(python_summary, "makespan")  # pylint: disable=protected-access
            - matched._summary_float(cpp_summary, "makespan")  # pylint: disable=protected-access
        ),
        "python_elapsed_mean_seconds": python_elapsed_mean,
        "python_elapsed_std_seconds": python_elapsed["std"],
        "python_elapsed_ci95_seconds": python_elapsed["ci95"],
        "python_elapsed_min_seconds": python_elapsed["min"],
        "python_elapsed_max_seconds": python_elapsed["max"],
        "cpp_elapsed_mean_seconds": cpp_elapsed_mean,
        "cpp_elapsed_std_seconds": cpp_elapsed["std"],
        "cpp_elapsed_ci95_seconds": cpp_elapsed["ci95"],
        "cpp_elapsed_min_seconds": cpp_elapsed["min"],
        "cpp_elapsed_max_seconds": cpp_elapsed["max"],
        "python_active_steps_per_second": python_steps_per_second,
        "cpp_active_steps_per_second": cpp_steps_per_second,
        "python_tasks_per_second": python_tasks_per_second,
        "cpp_tasks_per_second": cpp_tasks_per_second,
        "cpp_elapsed_speedup": python_elapsed_mean / cpp_elapsed_mean if cpp_elapsed_mean > 0.0 else 0.0,
        "cpp_active_step_speedup": (
            cpp_steps_per_second / python_steps_per_second if python_steps_per_second > 0.0 else 0.0
        ),
        "cpp_task_speedup": cpp_tasks_per_second / python_tasks_per_second if python_tasks_per_second > 0.0 else 0.0,
        "parity_pass": mismatch["field"] == "none",
        "first_mismatch_field": mismatch["field"],
        "python_value": mismatch["python_value"],
        "cpp_value": mismatch["cpp_value"],
        "python_version": metadata["python_version"],
        "platform": metadata["platform"],
        "machine": metadata["machine"],
        "processor": metadata["processor"],
        "cpu_count": metadata["cpu_count"],
        "timer": metadata["timer"],
        "timer_resolution_seconds": metadata["timer_resolution_seconds"],
        "notes": "repeated local timing with hardware metadata; not a cross-machine normalized benchmark",
    }


def _family_calls(matched: Any, inputs: Any, scenario: Any) -> tuple[tuple[str, Callable[[], dict[str, Any]], Callable[[], dict[str, Any]]], ...]:
    return (
        (
            "rolling_horizon_sipp",
            lambda: matched._python_rolling(inputs, scenario),  # pylint: disable=protected-access
            lambda: matched._cpp_rolling(inputs, scenario),  # pylint: disable=protected-access
        ),
        (
            "periodic_replanning_sipp",
            lambda: matched._python_periodic(inputs, scenario),  # pylint: disable=protected-access
            lambda: matched._cpp_periodic(inputs, scenario),  # pylint: disable=protected-access
        ),
        (
            "pibt_active_bag_replay",
            lambda: matched._python_pibt(inputs, scenario),  # pylint: disable=protected-access
            lambda: matched._cpp_pibt(inputs, scenario),  # pylint: disable=protected-access
        ),
        (
            "edge_score_event",
            lambda: matched._python_event(inputs, scenario, inputs.runtime_model),  # pylint: disable=protected-access
            lambda: matched._cpp_event(inputs, scenario, matched.MODEL_PATH),  # pylint: disable=protected-access
        ),
        (
            "fallback_event",
            lambda: matched._python_event(inputs, scenario, None),  # pylint: disable=protected-access
            lambda: matched._cpp_event(inputs, scenario, None),  # pylint: disable=protected-access
        ),
    )


def build_rows(matched: Any, inputs: Any, metadata: dict[str, float | int | str]) -> list[dict[str, float | int | str | bool]]:
    if REPEATS <= 0:
        raise ValueError("CZR005_MATCHED_RUNTIME_REPEATS must be positive")
    rows: list[dict[str, float | int | str | bool]] = []
    for scenario in matched._case_plan():  # pylint: disable=protected-access
        for family, python_call, cpp_call in _family_calls(matched, inputs, scenario):
            python_summaries: list[dict[str, Any]] = []
            python_elapsed_values: list[float] = []
            cpp_summaries: list[dict[str, Any]] = []
            cpp_elapsed_values: list[float] = []
            for _ in range(REPEATS):
                python_summary, python_elapsed = _timed(python_call)
                cpp_summary, cpp_elapsed = _timed(cpp_call)
                python_summaries.append(python_summary)
                python_elapsed_values.append(python_elapsed)
                cpp_summaries.append(cpp_summary)
                cpp_elapsed_values.append(cpp_elapsed)
            rows.append(
                _row(
                    matched,
                    scenario,
                    family,
                    _stable_summary(matched, family, python_summaries, f"{scenario.name}/{family}/python"),
                    python_elapsed_values,
                    _stable_summary(matched, family, cpp_summaries, f"{scenario.name}/{family}/cpp"),
                    cpp_elapsed_values,
                    metadata,
                )
            )
    return rows


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def write_report(rows: list[dict[str, float | int | str | bool]], metadata: dict[str, float | int | str]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parity_pass = all(bool(row["parity_pass"]) for row in rows)
    safety_pass = all(int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows)
    families = sorted({str(row["family"]) for row in rows})
    scenarios = sorted({str(row["scenario"]) for row in rows})
    speedups = [float(row["cpp_elapsed_speedup"]) for row in rows if float(row["cpp_elapsed_speedup"]) > 0.0]
    lines = [
        "# Phase9 Matched Runtime Scaling Diagnostic",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic repeats the Phase9 matched baseline comparison calls on the same real "
            "legacy `map2/inputdata` scenario rows. It reports Python and C++ elapsed-time means, "
            "standard deviations, and approximate 95% confidence intervals for every matched baseline family."
        ),
        "",
        "It is a repeated local timing gate with hardware metadata, not a cross-machine paper benchmark.",
        "",
        "## Environment",
        "",
        f"- repeats per row: `{metadata['repeat_count']}`",
        f"- platform: `{metadata['platform']}`",
        f"- machine: `{metadata['machine']}`",
        f"- processor: `{metadata['processor']}`",
        f"- CPU count: `{metadata['cpu_count']}`",
        f"- Python: `{metadata['python_version']}`",
        f"- timer: `{metadata['timer']}` resolution `{float(metadata['timer_resolution_seconds']):.12g}` seconds",
        "",
        "## Metrics",
        "",
        (
            "| Scenario | Family | Tasks | Config | Py seconds mean+/-95% CI | "
            "C++ seconds mean+/-95% CI | C++ elapsed speedup | Parity |"
        ),
        "|---|---|---:|---|---:|---:|---:|---|",
    ]
    for row in rows:
        config = "none"
        if row["node_capacities"] != "none":
            config = f"nodes={row['node_capacities']}"
        if row["merge_groups"] != "none":
            config = f"merge={row['merge_groups']},cap={row['merge_capacity']},headway={row['merge_headway_seconds']}"
        lines.append(
            "| {scenario} | {family} | {max_tasks} | {config} | "
            "{python_elapsed_mean_seconds:.6f}+/-{python_elapsed_ci95_seconds:.6f} | "
            "{cpp_elapsed_mean_seconds:.6f}+/-{cpp_elapsed_ci95_seconds:.6f} | "
            "{cpp_elapsed_speedup:.3f} | {parity_pass} |".format(**{**row, "config": config})
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            f"- scenarios: `{len(scenarios)}` ({', '.join(scenarios)})",
            f"- families: `{len(families)}` ({', '.join(families)})",
            f"- repeated timing rows: `{len(rows)}`",
            "- matched runtime summary parity: PASS" if parity_pass else "- matched runtime summary parity: FAIL",
            "- matched runtime post-shield safety: PASS" if safety_pass else "- matched runtime post-shield safety: FAIL",
            f"- median C++ elapsed-time speedup: `{_median(speedups):.3f}x`",
            "- repeated local timing with environment metadata: YES",
            "- confidence intervals for every compared family: YES",
            "",
            "## Remaining Work",
            "",
            "- add a separate real heldout airport map when fixture data is available",
            "- expand timing to hardware-normalized multi-machine runs before paper-grade speed claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import run_phase9_matched_baseline_comparison as matched  # pylint: disable=import-outside-toplevel

    matched._prepare_imports()  # pylint: disable=protected-access
    inputs = matched._load_inputs()  # pylint: disable=protected-access
    metadata = _runtime_metadata()
    rows = build_rows(matched, inputs, metadata)
    write_table(rows)
    write_report(rows, metadata)
    if not all(bool(row["parity_pass"]) for row in rows):
        raise AssertionError("Phase9 matched runtime scaling parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("Phase9 matched runtime scaling produced post-shield conflicts")
    print(
        "phase9_matched_runtime_scaling "
        f"rows={len(rows)} repeats={REPEATS} scenarios={len(matched._case_plan())} "  # pylint: disable=protected-access
        f"families={len(matched.SUMMARY_FIELDS_BY_FAMILY)}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
