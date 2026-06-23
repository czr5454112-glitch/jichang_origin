from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import math
import os
import platform
from pathlib import Path
from statistics import mean, stdev
from time import get_clock_info, perf_counter
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase9_event_runtime_scaling.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase9_event_runtime_scaling_report.md"
MAX_DECISIONS_PER_TASK = 128
FLOAT_TOLERANCE = 1.0e-9
REPEATS = int(os.environ.get("CZR005_RUNTIME_REPEATS", "5"))

NodeRecord = tuple[int, int, float, int, int, list[int]]
EdgeRecord = tuple[int, int, float, float]
TaskRecord = tuple[str, int, int, float, float, int, int, int, int, float, str, bool, int]
FaultWindow = tuple[int, int, float, float]

SUMMARY_FIELDS = (
    "planned_count",
    "unplanned_count",
    "decision_count",
    "post_shield_conflicts",
    "mean_travel_time",
    "makespan",
)


@dataclass(frozen=True)
class RuntimeScalingCase:
    name: str
    task_offset: int
    max_tasks: int
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[FaultWindow, ...] = ()


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def _node_records(graph: Any) -> tuple[NodeRecord, ...]:
    return tuple(
        (
            int(node.location),
            int(node.node_type),
            float(node.service_time),
            int(node.x),
            int(node.y),
            [int(value) for value in node.outgoing],
        )
        for node in sorted(graph.nodes.values(), key=lambda item: item.location)
    )


def _edge_records(graph: Any) -> tuple[EdgeRecord, ...]:
    return tuple(
        (int(edge.start), int(edge.end), float(edge.length), float(edge.speed))
        for edge in sorted(graph.edges.values(), key=lambda item: (item.start, item.end))
    )


def _task_records(tasks: tuple[Any, ...]) -> tuple[TaskRecord, ...]:
    return tuple(
        (
            str(task.segment_id),
            int(task.task_id),
            int(task.pallet_id),
            float(task.pass_time),
            float(task.std),
            int(task.start),
            int(task.goal),
            int(task.original_start),
            int(task.original_goal),
            float(task.original_entry_time),
            str(task.leg),
            bool(task.early_bag_split),
            int(task.source_line),
        )
        for task in tasks
    )


def _format_faults(fault_edges: tuple[tuple[int, int], ...]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def _format_fault_windows(fault_windows: tuple[FaultWindow, ...]) -> str:
    if not fault_windows:
        return "none"
    return ";".join(
        f"{start}->{end}@[{fault_start:.3f},{repair_time:.3f})"
        for start, end, fault_start, repair_time in fault_windows
    )


def _case_plan() -> tuple[RuntimeScalingCase, ...]:
    return (
        RuntimeScalingCase("legacy_first16", 0, 16),
        RuntimeScalingCase("legacy_first32", 0, 32),
        RuntimeScalingCase("legacy_first64", 0, 64),
        RuntimeScalingCase("legacy_offset64_repair32", 64, 32, fault_windows=((28, 47, 0.0, 12000.0),)),
    )


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field in {"mean_travel_time", "makespan"}:
        return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE
    return python_value == cpp_value


def _first_summary_mismatch(python_summary: dict[str, Any], cpp_summary: dict[str, Any]) -> dict[str, Any]:
    for field in SUMMARY_FIELDS:
        if not _values_match(field, python_summary[field], cpp_summary[field]):
            return {
                "status": "summary_mismatch",
                "field": field,
                "python_value": python_summary[field],
                "cpp_value": cpp_summary[field],
            }
    return {"status": "match", "field": "none", "python_value": "", "cpp_value": ""}


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


def _stable_summary(summaries: list[dict[str, Any]], label: str) -> dict[str, Any]:
    if not summaries:
        raise ValueError(f"missing summaries for {label}")
    first = summaries[0]
    for index, summary in enumerate(summaries[1:], start=2):
        mismatch = _first_summary_mismatch(first, summary)
        if mismatch["status"] != "match":
            raise AssertionError(
                f"{label} summary changed on repeat {index}: "
                f"{mismatch['field']} {mismatch['python_value']} != {mismatch['cpp_value']}"
            )
    return first


def _run_python_event(
    graph: Any,
    tasks: tuple[Any, ...],
    runtime_model: Any | None,
    case: RuntimeScalingCase,
    run_event_replay: Any,
) -> tuple[dict[str, Any], float]:
    start = perf_counter()
    run = run_event_replay(
        graph,
        tasks,
        runtime_model=runtime_model,
        max_tasks=case.max_tasks,
        fault_edges=set(case.fault_edges),
        fault_windows=tuple(case.fault_windows),
        max_decisions_per_task=MAX_DECISIONS_PER_TASK,
    )
    elapsed = perf_counter() - start
    return dict(run.summary), elapsed


def _row(
    case: RuntimeScalingCase,
    policy: str,
    python_summary: dict[str, Any],
    python_elapsed_values: list[float],
    cpp_summary: dict[str, Any],
    cpp_elapsed_values: list[float],
) -> dict[str, float | int | str | bool]:
    mismatch = _first_summary_mismatch(python_summary, cpp_summary)
    python_decisions = int(python_summary["decision_count"])
    cpp_decisions = int(cpp_summary["decision_count"])
    python_elapsed = _sample_stats(python_elapsed_values)
    cpp_elapsed = _sample_stats(cpp_elapsed_values)
    python_elapsed_mean = python_elapsed["mean"]
    cpp_elapsed_mean = cpp_elapsed["mean"]
    python_dps = python_decisions / python_elapsed_mean if python_elapsed_mean > 0.0 else 0.0
    cpp_dps = cpp_decisions / cpp_elapsed_mean if cpp_elapsed_mean > 0.0 else 0.0
    python_tps = case.max_tasks / python_elapsed_mean if python_elapsed_mean > 0.0 else 0.0
    cpp_tps = case.max_tasks / cpp_elapsed_mean if cpp_elapsed_mean > 0.0 else 0.0
    return {
        "case": case.name,
        "policy": policy,
        "task_offset": case.task_offset,
        "max_tasks": case.max_tasks,
        "fault_edges": _format_faults(case.fault_edges),
        "fault_windows": _format_fault_windows(case.fault_windows),
        "python_planned": int(python_summary["planned_count"]),
        "cpp_planned": int(cpp_summary["planned_count"]),
        "python_unplanned": int(python_summary["unplanned_count"]),
        "cpp_unplanned": int(cpp_summary["unplanned_count"]),
        "python_decisions": python_decisions,
        "cpp_decisions": cpp_decisions,
        "python_conflicts": int(python_summary["post_shield_conflicts"]),
        "cpp_conflicts": int(cpp_summary["post_shield_conflicts"]),
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
        "python_decisions_per_second": python_dps,
        "cpp_decisions_per_second": cpp_dps,
        "python_tasks_per_second": python_tps,
        "cpp_tasks_per_second": cpp_tps,
        "cpp_decision_speedup": cpp_dps / python_dps if python_dps > 0.0 else 0.0,
        "cpp_task_speedup": cpp_tps / python_tps if python_tps > 0.0 else 0.0,
        "mean_travel_abs_diff": abs(float(python_summary["mean_travel_time"]) - float(cpp_summary["mean_travel_time"])),
        "makespan_abs_diff": abs(float(python_summary["makespan"]) - float(cpp_summary["makespan"])),
        "summary_parity_pass": mismatch["status"] == "match",
        "first_mismatch_status": mismatch["status"],
        "first_mismatch_field": mismatch["field"],
        "python_value": mismatch["python_value"],
        "cpp_value": mismatch["cpp_value"],
    }


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]], metadata: dict[str, float | int | str]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    parity_pass = all(bool(row["summary_parity_pass"]) for row in rows)
    safety_pass = all(int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows)
    edge_rows = [row for row in rows if row["policy"] == "edge_score_event"]
    fallback_rows = [row for row in rows if row["policy"] == "fallback_event"]
    median_speedup = _median([float(row["cpp_decision_speedup"]) for row in rows])
    lines = [
        "# Phase9 Event Runtime Scaling Diagnostic",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic measures Python event replay against native C++ event replay on real "
            "legacy `map2/inputdata` task windows. It records scheduler runtime, decision throughput, "
            "task throughput, safety, and summary parity for EdgeScore-runtime and shortest-safe fallback policies."
        ),
        "",
        f"Map: `{MAP_PATH.relative_to(ROOT).as_posix()}`",
        f"Tasks: `{TASK_PATH.relative_to(ROOT).as_posix()}`",
        "",
        (
            "This is an early Phase9 runtime-scaling gate. It is not a final paper benchmark: "
            "results are repeated local timings on one workstation and should be expanded before making claims."
        ),
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
            "| Case | Policy | Tasks | Py decisions | C++ decisions | Py seconds mean+/-95% CI | "
            "C++ seconds mean+/-95% CI | Py decisions/s | C++ decisions/s | C++ speedup | Parity | First mismatch |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {max_tasks} | {python_decisions} | {cpp_decisions} | "
            "{python_elapsed_mean_seconds:.6f}+/-{python_elapsed_ci95_seconds:.6f} | "
            "{cpp_elapsed_mean_seconds:.6f}+/-{cpp_elapsed_ci95_seconds:.6f} | "
            "{python_decisions_per_second:.2f} | {cpp_decisions_per_second:.2f} | "
            "{cpp_decision_speedup:.3f} | {summary_parity_pass} | "
            "{first_mismatch_status}:{first_mismatch_field} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- event runtime summary parity: PASS" if parity_pass else "- event runtime summary parity: FAIL",
            "- event runtime post-shield safety: PASS" if safety_pass else "- event runtime post-shield safety: FAIL",
            f"- EdgeScore runtime rows: `{len(edge_rows)}`",
            f"- fallback runtime rows: `{len(fallback_rows)}`",
            f"- median C++ decision-throughput speedup: `{median_speedup:.3f}x`",
            "- repeated local timing with environment metadata: YES",
            "- final paper-grade throughput claim: not covered",
            "",
            "## Remaining Work",
            "",
            "- add more task windows and hardware-normalized runs",
            "- scale to larger persisted manifests and separate heldout maps",
            "- extend the unified Phase9 comparison with matched baseline-family runtime rows",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return 0.5 * (ordered[mid - 1] + ordered[mid])


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.eval import run_event_replay  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(MAP_PATH)
    tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    node_records = list(_node_records(graph))
    edge_records = list(_edge_records(graph))
    heuristic_time = [list(row) for row in graph.heuristic_time]
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))

    if REPEATS <= 0:
        raise ValueError("CZR005_RUNTIME_REPEATS must be positive")
    metadata = _runtime_metadata()
    rows: list[dict[str, float | int | str | bool]] = []
    for case in _case_plan():
        selected_tasks = tasks[case.task_offset : case.task_offset + case.max_tasks]
        task_records = list(_task_records(selected_tasks))
        common = {
            "max_tasks": case.max_tasks,
            "fault_edges": list(case.fault_edges),
            "fault_windows": list(case.fault_windows),
            "max_decisions_per_task": MAX_DECISIONS_PER_TASK,
        }
        python_edge_summaries: list[dict[str, Any]] = []
        python_edge_elapsed: list[float] = []
        cpp_edge_summaries: list[dict[str, Any]] = []
        cpp_edge_elapsed: list[float] = []
        for _ in range(REPEATS):
            summary, elapsed = _run_python_event(
                graph,
                selected_tasks,
                runtime_model,
                RuntimeScalingCase(case.name, 0, case.max_tasks, case.fault_edges, case.fault_windows),
                run_event_replay,
            )
            python_edge_summaries.append(summary)
            python_edge_elapsed.append(elapsed)
            cpp_summary = dict(
                czr005_cpp.edge_score_native_event_replay_summary_from_records(
                    node_records,
                    edge_records,
                    heuristic_time,
                    task_records,
                    str(MODEL_PATH),
                    **common,
                )
            )
            cpp_edge_summaries.append(cpp_summary)
            cpp_edge_elapsed.append(float(cpp_summary["elapsed_seconds"]))
        rows.append(
            _row(
                case,
                "edge_score_event",
                _stable_summary(python_edge_summaries, f"{case.name}/edge_score/python"),
                python_edge_elapsed,
                _stable_summary(cpp_edge_summaries, f"{case.name}/edge_score/cpp"),
                cpp_edge_elapsed,
            )
        )

        python_fallback_summaries: list[dict[str, Any]] = []
        python_fallback_elapsed: list[float] = []
        cpp_fallback_summaries: list[dict[str, Any]] = []
        cpp_fallback_elapsed: list[float] = []
        for _ in range(REPEATS):
            summary, elapsed = _run_python_event(
                graph,
                selected_tasks,
                None,
                RuntimeScalingCase(case.name, 0, case.max_tasks, case.fault_edges, case.fault_windows),
                run_event_replay,
            )
            python_fallback_summaries.append(summary)
            python_fallback_elapsed.append(elapsed)
            cpp_summary = dict(
                czr005_cpp.edge_score_native_event_fallback_replay_summary_from_records(
                    node_records,
                    edge_records,
                    heuristic_time,
                    task_records,
                    **common,
                )
            )
            cpp_fallback_summaries.append(cpp_summary)
            cpp_fallback_elapsed.append(float(cpp_summary["elapsed_seconds"]))
        rows.append(
            _row(
                case,
                "fallback_event",
                _stable_summary(python_fallback_summaries, f"{case.name}/fallback/python"),
                python_fallback_elapsed,
                _stable_summary(cpp_fallback_summaries, f"{case.name}/fallback/cpp"),
                cpp_fallback_elapsed,
            )
        )

    for row in rows:
        row.update(metadata)
    write_table(rows)
    write_report(rows, metadata)
    if not all(bool(row["summary_parity_pass"]) for row in rows):
        raise AssertionError("Phase9 event runtime scaling parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("Phase9 event runtime scaling produced post-shield conflicts")
    print(f"phase9_event_runtime_scaling rows={len(rows)} summary_parity=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
