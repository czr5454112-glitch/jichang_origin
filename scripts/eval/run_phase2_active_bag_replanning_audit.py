from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import sys
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase2_active_bag_replanning_audit.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase2_active_bag_replanning_audit_report.md"
MAX_DECISIONS_PER_TASK = 128
REPLAN_INTERVAL_SECONDS = 5.0
FLOAT_TOLERANCE = 1.0e-9


@dataclass(frozen=True)
class TickMetrics:
    tick_count: int
    active_tick_count: int
    decision_tick_count: int
    peak_active_bags: int
    mean_active_bags: float
    active_bag_tick_seconds: float
    decision_count: int
    terminal_count: int
    last_terminal_time: float


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _trace_rows(payload_or_run: Any) -> list[dict[str, Any]]:
    if hasattr(payload_or_run, "trace"):
        return [dict(row) for row in payload_or_run.trace]
    return [dict(row) for row in payload_or_run["trace"]]


def _summary(payload_or_run: Any) -> dict[str, Any]:
    if hasattr(payload_or_run, "summary"):
        return dict(payload_or_run.summary)
    return dict(payload_or_run["summary"])


def _terminal_times(graph: Any, tasks: tuple[Any, ...], trace: list[dict[str, Any]]) -> dict[tuple[str, int], float]:
    terminal_times: dict[tuple[str, int], float] = {}
    for row in trace:
        key = (str(row["segment_id"]), int(row["task_id"]))
        ready_time = float(row["ready_time"])
        event = str(row["event"])
        if event != "step":
            terminal_times[key] = ready_time
            continue
        if bool(row["reached_goal"]):
            current = int(row["current"])
            executed_next = int(row["executed_next"])
            terminal_times[key] = (
                ready_time
                + graph.edge(current, executed_next).travel_time
                + graph.service_time(executed_next)
            )
    for task in tasks:
        key = (str(task.segment_id), int(task.task_id))
        if key not in terminal_times and int(task.start) == int(task.goal):
            terminal_times[key] = float(task.pass_time)
    return terminal_times


def _tick_metrics(
    graph: Any,
    tasks: tuple[Any, ...],
    trace: list[dict[str, Any]],
    interval_seconds: float,
) -> TickMetrics:
    if interval_seconds <= 0.0:
        raise ValueError("interval_seconds must be positive")
    if not tasks:
        return TickMetrics(0, 0, 0, 0, 0.0, 0.0, len(trace), 0, 0.0)

    terminal_times = _terminal_times(graph, tasks, trace)
    pass_times = [float(task.pass_time) for task in tasks]
    start_time = min(pass_times)
    last_terminal_time = max(terminal_times.values(), default=max(pass_times))
    tick_count = int((last_terminal_time - start_time) // interval_seconds) + 1
    tick_count = max(tick_count, 1)

    active_counts: list[int] = []
    for tick_index in range(tick_count):
        tick_time = start_time + tick_index * interval_seconds
        active = 0
        for task in tasks:
            key = (str(task.segment_id), int(task.task_id))
            terminal_time = terminal_times.get(key)
            if terminal_time is None:
                continue
            if float(task.pass_time) <= tick_time < terminal_time - FLOAT_TOLERANCE:
                active += 1
        active_counts.append(active)

    decision_ticks = {
        int((float(row["ready_time"]) - start_time) // interval_seconds)
        for row in trace
        if float(row["ready_time"]) >= start_time - FLOAT_TOLERANCE
    }
    active_tick_count = sum(1 for count in active_counts if count > 0)
    peak_active_bags = max(active_counts, default=0)
    mean_active_bags = sum(active_counts) / len(active_counts) if active_counts else 0.0
    return TickMetrics(
        tick_count=tick_count,
        active_tick_count=active_tick_count,
        decision_tick_count=len(decision_ticks),
        peak_active_bags=peak_active_bags,
        mean_active_bags=mean_active_bags,
        active_bag_tick_seconds=sum(active_counts) * interval_seconds,
        decision_count=len(trace),
        terminal_count=len(terminal_times),
        last_terminal_time=last_terminal_time,
    )


def _metrics_match(left: TickMetrics, right: TickMetrics) -> bool:
    return (
        left.tick_count == right.tick_count
        and left.active_tick_count == right.active_tick_count
        and left.decision_tick_count == right.decision_tick_count
        and left.peak_active_bags == right.peak_active_bags
        and left.decision_count == right.decision_count
        and left.terminal_count == right.terminal_count
        and abs(left.mean_active_bags - right.mean_active_bags) <= FLOAT_TOLERANCE
        and abs(left.active_bag_tick_seconds - right.active_bag_tick_seconds) <= FLOAT_TOLERANCE
        and abs(left.last_terminal_time - right.last_terminal_time) <= FLOAT_TOLERANCE
    )


def _row(
    case_name: str,
    policy: str,
    task_count: int,
    python_summary: dict[str, Any],
    python_metrics: TickMetrics,
    python_elapsed: float,
    cpp_summary: dict[str, Any],
    cpp_metrics: TickMetrics,
) -> dict[str, float | int | str | bool]:
    cpp_elapsed = float(cpp_summary["elapsed_seconds"])
    parity_pass = _metrics_match(python_metrics, cpp_metrics)
    accounted_pass = (
        int(python_summary["planned_count"]) + int(python_summary["unplanned_count"]) == task_count
        and int(cpp_summary["planned_count"]) + int(cpp_summary["unplanned_count"]) == task_count
    )
    conflict_pass = int(python_summary["post_shield_conflicts"]) == 0 and int(cpp_summary["post_shield_conflicts"]) == 0
    return {
        "case": case_name,
        "policy": policy,
        "task_count": task_count,
        "replan_interval_seconds": REPLAN_INTERVAL_SECONDS,
        "python_planned": int(python_summary["planned_count"]),
        "cpp_planned": int(cpp_summary["planned_count"]),
        "python_unplanned": int(python_summary["unplanned_count"]),
        "cpp_unplanned": int(cpp_summary["unplanned_count"]),
        "python_decisions": python_metrics.decision_count,
        "cpp_decisions": cpp_metrics.decision_count,
        "python_tick_count": python_metrics.tick_count,
        "cpp_tick_count": cpp_metrics.tick_count,
        "python_active_ticks": python_metrics.active_tick_count,
        "cpp_active_ticks": cpp_metrics.active_tick_count,
        "python_decision_ticks": python_metrics.decision_tick_count,
        "cpp_decision_ticks": cpp_metrics.decision_tick_count,
        "python_peak_active_bags": python_metrics.peak_active_bags,
        "cpp_peak_active_bags": cpp_metrics.peak_active_bags,
        "python_mean_active_bags": python_metrics.mean_active_bags,
        "cpp_mean_active_bags": cpp_metrics.mean_active_bags,
        "python_active_bag_tick_seconds": python_metrics.active_bag_tick_seconds,
        "cpp_active_bag_tick_seconds": cpp_metrics.active_bag_tick_seconds,
        "python_elapsed_seconds": python_elapsed,
        "cpp_elapsed_seconds": cpp_elapsed,
        "python_decisions_per_second": (
            python_metrics.decision_count / python_elapsed if python_elapsed > 0.0 else 0.0
        ),
        "cpp_decisions_per_second": (
            cpp_metrics.decision_count / cpp_elapsed if cpp_elapsed > 0.0 else 0.0
        ),
        "accounted_pass": accounted_pass,
        "conflict_pass": conflict_pass,
        "tick_parity_pass": parity_pass,
        "audit_pass": accounted_pass and conflict_pass and parity_pass,
    }


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]], manifest_path: Path) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    audit_pass = all(bool(row["audit_pass"]) for row in rows)
    tick_parity_pass = all(bool(row["tick_parity_pass"]) for row in rows)
    conflict_pass = all(bool(row["conflict_pass"]) for row in rows)
    fault_case_count = sum(1 for row in rows if "repair" in str(row["case"]) or "static" in str(row["case"]))
    lines = [
        "# Phase2 Active-Bag Replanning Audit",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        (
            "This diagnostic samples the Python and C++ event-queue replay traces into fixed "
            f"{REPLAN_INTERVAL_SECONDS:.1f}s ticks so Phase2C active-bag/replan-cost behavior is "
            "visible in a reproducible table. It reports active-bag pressure, decision ticks, "
            "decision throughput, task accounting, and post-shield safety on the persisted "
            "synthetic manifest."
        ),
        "",
        f"Manifest: `{manifest_path.relative_to(ROOT).as_posix()}`",
        "",
        (
            "This is an active-bag periodic audit over the event scheduler, not a route-discarding "
            "periodic global replanner and not recursive PIBT."
        ),
        "",
        (
            "Route-discarding periodic SIPP replanning is tracked separately in "
            "`outputs/reports/phase2_periodic_replanning_parity_report.md`."
        ),
        "",
        "## Metrics",
        "",
        (
            "| Case | Policy | Tasks | Py/C++ planned | Peak active Py/C++ | Active ticks Py/C++ | "
            "Decision ticks Py/C++ | C++ decisions/s | Tick parity | Pass |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {task_count} | {python_planned}/{cpp_planned} | "
            "{python_peak_active_bags}/{cpp_peak_active_bags} | "
            "{python_active_ticks}/{cpp_active_ticks} | "
            "{python_decision_ticks}/{cpp_decision_ticks} | "
            "{cpp_decisions_per_second:.3f} | {tick_parity_pass} | {audit_pass} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- active-bag task-stream audit: PASS" if audit_pass else "- active-bag task-stream audit: FAIL",
            "- Python/C++ binned active-bag parity: PASS" if tick_parity_pass else "- Python/C++ binned active-bag parity: FAIL",
            "- post-shield safety under active bags: PASS" if conflict_pass else "- post-shield safety under active bags: FAIL",
            f"- fault/repair schedule rows included: `{fault_case_count}`",
            "- replan cost reported: PASS",
            "",
            "## Remaining Work",
            "",
            "- extend periodic SIPP replanning to repair-window schedules if needed",
            "- add real heldout airport-map fixtures when available",
            "- carry active-bag cost metrics into Phase9 comparisons",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.eval import run_event_replay  # pylint: disable=import-outside-toplevel
    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        MANIFEST_PATH,
        graph_from_case,
        load_manifest_cases,
        tasks_from_case,
    )

    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))
    rows: list[dict[str, float | int | str | bool]] = []
    for case in load_manifest_cases(MANIFEST_PATH):
        graph = graph_from_case(case)
        tasks = tasks_from_case(case)
        common = {
            "max_tasks": case.spec.task_count,
            "fault_edges": set(case.spec.fault_edges),
            "max_decisions_per_task": MAX_DECISIONS_PER_TASK,
            "fault_windows": tuple(case.spec.fault_windows),
        }
        record_common = {
            "max_tasks": case.spec.task_count,
            "fault_edges": list(case.spec.fault_edges),
            "max_decisions_per_task": MAX_DECISIONS_PER_TASK,
            "fault_windows": list(case.spec.fault_windows),
        }
        node_records = list(case.node_records)
        edge_records = list(case.edge_records)
        heuristic_time = [list(row) for row in case.heuristic_time]
        task_records = list(case.task_records)

        payloads: tuple[tuple[str, Any, dict[str, Any], float], ...] = ()
        edge_start = perf_counter()
        python_edge = run_event_replay(graph, tasks, runtime_model=runtime_model, **common)
        python_edge_elapsed = perf_counter() - edge_start
        cpp_edge = czr005_cpp.edge_score_native_event_replay_trace_from_records(
            node_records,
            edge_records,
            heuristic_time,
            task_records,
            str(MODEL_PATH),
            **record_common,
        )
        payloads += (("edge_score_event", python_edge, cpp_edge, python_edge_elapsed),)

        fallback_start = perf_counter()
        python_fallback = run_event_replay(graph, tasks, runtime_model=None, **common)
        python_fallback_elapsed = perf_counter() - fallback_start
        cpp_fallback = czr005_cpp.edge_score_native_event_fallback_replay_trace_from_records(
            node_records,
            edge_records,
            heuristic_time,
            task_records,
            **record_common,
        )
        payloads += (("fallback_event", python_fallback, cpp_fallback, python_fallback_elapsed),)

        for policy, python_payload, cpp_payload, python_elapsed in payloads:
            python_trace = _trace_rows(python_payload)
            cpp_trace = _trace_rows(cpp_payload)
            rows.append(
                _row(
                    case.spec.name,
                    policy,
                    case.spec.task_count,
                    _summary(python_payload),
                    _tick_metrics(graph, tasks, python_trace, REPLAN_INTERVAL_SECONDS),
                    python_elapsed,
                    _summary(cpp_payload),
                    _tick_metrics(graph, tasks, cpp_trace, REPLAN_INTERVAL_SECONDS),
                )
            )

    write_table(rows)
    write_report(rows, MANIFEST_PATH)
    if not all(bool(row["audit_pass"]) for row in rows):
        raise AssertionError("active-bag replanning audit failed")
    print(f"phase2_active_bag_replanning_audit rows={len(rows)} audit_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
