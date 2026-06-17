from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_event_trace_diagnostic.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_event_trace_diagnostic_report.md"
MAX_DECISIONS_PER_TASK = 128
FLOAT_TOLERANCE = 1.0e-9


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _first_failure(checks: list[tuple[str, bool]]) -> str:
    for name, passed in checks:
        if not passed:
            return name
    return "none"


def _event_trace_row(case: Any, policy: str, payload: dict[str, Any]) -> dict[str, float | int | str | bool]:
    summary = payload["summary"]
    trace = list(payload["trace"])
    planned_count = int(summary["planned_count"])
    unplanned_count = int(summary["unplanned_count"])
    decision_count = int(summary["decision_count"])
    accounted_count = planned_count + unplanned_count

    ordinal_pass = all(int(row["decision_ordinal"]) == index + 1 for index, row in enumerate(trace))
    summary_trace_pass = decision_count == len(trace)
    accounted_pass = accounted_count == case.spec.task_count
    conflict_pass = int(summary["post_shield_conflicts"]) == 0
    candidate_count_pass = all(
        0 <= int(row["safe_candidate_count"]) <= int(row["candidate_count"]) for row in trace
    )
    step_safety_pass = all(
        str(row["event"]) != "step" or (bool(row["executed_safe"]) and int(row["executed_index"]) >= 0)
        for row in trace
    )
    hold_semantics_pass = all(
        str(row["event"]) != "step"
        or str(row["executed_kind"]) != "hold"
        or int(row["executed_next"]) == int(row["current"])
        for row in trace
    )
    move_semantics_pass = all(
        str(row["event"]) != "step"
        or str(row["executed_kind"]) != "move"
        or int(row["executed_next"]) != int(row["current"])
        for row in trace
    )
    terminal_event_pass = all(
        str(row["event"]) == "step"
        or (str(row["executed_kind"]) == "none" and str(row["terminal_reason"]))
        for row in trace
    )

    last_global_ready_time = -1.0e100
    global_ready_time_pass = True
    for row in trace:
        ready_time = float(row["ready_time"])
        if ready_time + FLOAT_TOLERANCE < last_global_ready_time:
            global_ready_time_pass = False
            break
        last_global_ready_time = max(last_global_ready_time, ready_time)

    task_counts: dict[tuple[str, int], int] = defaultdict(int)
    task_last_ready_time: dict[tuple[str, int], float] = {}
    task_ordinal_pass = True
    task_ready_time_pass = True
    for row in trace:
        key = (str(row["segment_id"]), int(row["task_id"]))
        task_counts[key] += 1
        if int(row["task_decision_ordinal"]) != task_counts[key]:
            task_ordinal_pass = False
        ready_time = float(row["ready_time"])
        previous_ready_time = task_last_ready_time.get(key, -1.0e100)
        if ready_time + FLOAT_TOLERANCE < previous_ready_time:
            task_ready_time_pass = False
        task_last_ready_time[key] = max(previous_ready_time, ready_time)

    max_task_decision_ordinal = max((int(row["task_decision_ordinal"]) for row in trace), default=0)
    last_ready_time = max((float(row["ready_time"]) for row in trace), default=0.0)
    checks = [
        ("accounted", accounted_pass),
        ("summary_trace", summary_trace_pass),
        ("conflicts", conflict_pass),
        ("global_ready_time", global_ready_time_pass),
        ("task_ready_time", task_ready_time_pass),
        ("decision_ordinal", ordinal_pass),
        ("task_decision_ordinal", task_ordinal_pass),
        ("candidate_counts", candidate_count_pass),
        ("step_safety", step_safety_pass),
        ("hold_semantics", hold_semantics_pass),
        ("move_semantics", move_semantics_pass),
        ("terminal_event", terminal_event_pass),
    ]
    invariant_pass = all(passed for _, passed in checks)
    return {
        "case": case.spec.name,
        "policy": policy,
        "task_count": case.spec.task_count,
        "planned_count": planned_count,
        "unplanned_count": unplanned_count,
        "accounted_count": accounted_count,
        "decision_count": decision_count,
        "trace_rows": len(trace),
        "post_shield_conflicts": int(summary["post_shield_conflicts"]),
        "mean_travel_time": float(summary["mean_travel_time"]),
        "last_ready_time": last_ready_time,
        "max_task_decision_ordinal": max_task_decision_ordinal,
        "accounted_pass": accounted_pass,
        "summary_trace_pass": summary_trace_pass,
        "conflict_pass": conflict_pass,
        "global_ready_time_pass": global_ready_time_pass,
        "task_ready_time_pass": task_ready_time_pass,
        "ordinal_pass": ordinal_pass,
        "task_ordinal_pass": task_ordinal_pass,
        "candidate_count_pass": candidate_count_pass,
        "step_safety_pass": step_safety_pass,
        "hold_semantics_pass": hold_semantics_pass,
        "move_semantics_pass": move_semantics_pass,
        "terminal_event_pass": terminal_event_pass,
        "invariant_pass": invariant_pass,
        "first_failure": _first_failure(checks),
    }


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]], manifest_path: Path) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    invariant_pass = all(bool(row["invariant_pass"]) for row in rows)
    lines = [
        "# Phase8 Native C++ Event Trace Diagnostic",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This diagnostic audits the native C++ event-queue replay trace on the persisted synthetic manifest. It checks event-scheduler invariants directly: chronological decision events, per-task ready-time monotonicity, contiguous decision ordinals, post-shield action safety, and complete planned/unplanned accounting.",
        "",
        f"Manifest: `{manifest_path.relative_to(ROOT).as_posix()}`",
        "",
        "This is an event-trace audit, not a strict compact replay parity claim. Compact replay routes one task to completion before the next task, while this scheduler interleaves active bags by event time.",
        "",
        "## Metrics",
        "",
        "| Case | Policy | Tasks | Planned | Unplanned | Decisions | Trace rows | Conflicts | Last ready | Max task decisions | Pass | First failure |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {task_count} | {planned_count} | {unplanned_count} | "
            "{decision_count} | {trace_rows} | {post_shield_conflicts} | {last_ready_time:.12f} | "
            "{max_task_decision_ordinal} | {invariant_pass} | {first_failure} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- event trace invariants: PASS" if invariant_pass else "- event trace invariants: FAIL",
            "- EdgeScore and fallback event traces covered: PASS",
            "- persisted synthetic manifest covered: PASS",
            "- Python event-scheduler trace parity: not covered",
            "- final paper-grade scheduler throughput: not covered",
            "",
            "## Remaining Work",
            "",
            "- add a Python event-scheduler reference or equivalent route-update oracle",
            "- scale this diagnostic over larger persisted manifests",
            "- carry the event trace audit into Phase9 baseline and policy comparisons",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        MANIFEST_PATH,
        load_manifest_cases,
    )

    cases = load_manifest_cases(MANIFEST_PATH)
    rows: list[dict[str, float | int | str | bool]] = []
    for case in cases:
        node_records = list(case.node_records)
        edge_records = list(case.edge_records)
        heuristic_time = [list(row) for row in case.heuristic_time]
        task_records = list(case.task_records)
        common = {
            "max_tasks": case.spec.task_count,
            "fault_edges": list(case.spec.fault_edges),
            "max_decisions_per_task": MAX_DECISIONS_PER_TASK,
            "fault_windows": list(case.spec.fault_windows),
        }
        payloads = (
            (
                "edge_score_event",
                czr005_cpp.edge_score_native_event_replay_trace_from_records(
                    node_records,
                    edge_records,
                    heuristic_time,
                    task_records,
                    str(MODEL_PATH),
                    **common,
                ),
            ),
            (
                "fallback_event",
                czr005_cpp.edge_score_native_event_fallback_replay_trace_from_records(
                    node_records,
                    edge_records,
                    heuristic_time,
                    task_records,
                    **common,
                ),
            ),
        )
        for policy, payload in payloads:
            rows.append(_event_trace_row(case, policy, payload))

    write_table(rows)
    write_report(rows, MANIFEST_PATH)
    if not all(bool(row["invariant_pass"]) for row in rows):
        raise AssertionError("event trace invariant diagnostic failed")
    print(f"phase8_native_cpp_event_trace_diagnostic rows={len(rows)} invariant_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
