from __future__ import annotations

import csv
from datetime import date
import os
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_event_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_event_parity_report.md"
MAX_DECISIONS_PER_TASK = 128
FLOAT_TOLERANCE = 1.0e-9

SUMMARY_FIELDS = (
    "planned_count",
    "unplanned_count",
    "decision_count",
    "post_shield_conflicts",
    "mean_travel_time",
    "makespan",
)

TRACE_FIELDS = (
    "decision_ordinal",
    "task_decision_ordinal",
    "event",
    "terminal_reason",
    "task_index",
    "segment_id",
    "task_id",
    "current",
    "goal",
    "ready_time",
    "waiting_time",
    "proposed_position",
    "executed_index",
    "executed_next",
    "executed_kind",
    "executed_safe",
    "unsafe_proposal",
    "fallback_used",
    "reached_goal",
    "candidate_count",
    "safe_candidate_count",
    "route_size_after",
)


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field in {"ready_time", "waiting_time", "mean_travel_time", "makespan"}:
        return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE
    return python_value == cpp_value


def _first_summary_mismatch(python_summary: dict[str, Any], cpp_summary: dict[str, Any]) -> dict[str, Any]:
    for field in SUMMARY_FIELDS:
        if not _values_match(field, python_summary[field], cpp_summary[field]):
            return {
                "status": "summary_mismatch",
                "decision_ordinal": "",
                "field": field,
                "python_value": python_summary[field],
                "cpp_value": cpp_summary[field],
            }
    return {"status": "match", "decision_ordinal": "", "field": "none", "python_value": "", "cpp_value": ""}


def _first_trace_mismatch(
    python_trace: list[dict[str, Any]],
    cpp_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    shared = min(len(python_trace), len(cpp_trace))
    for index in range(shared):
        python_row = python_trace[index]
        cpp_row = cpp_trace[index]
        for field in TRACE_FIELDS:
            if not _values_match(field, python_row[field], cpp_row[field]):
                return {
                    "status": "trace_mismatch",
                    "decision_ordinal": index + 1,
                    "field": field,
                    "python_value": python_row[field],
                    "cpp_value": cpp_row[field],
                    "python_task_id": python_row["task_id"],
                    "cpp_task_id": cpp_row["task_id"],
                }
    if len(python_trace) != len(cpp_trace):
        return {
            "status": "trace_length_mismatch",
            "decision_ordinal": shared + 1,
            "field": "trace_length",
            "python_value": len(python_trace),
            "cpp_value": len(cpp_trace),
            "python_task_id": python_trace[shared - 1]["task_id"] if shared else "",
            "cpp_task_id": cpp_trace[shared - 1]["task_id"] if shared else "",
        }
    return {
        "status": "match",
        "decision_ordinal": "",
        "field": "none",
        "python_value": "",
        "cpp_value": "",
        "python_task_id": "",
        "cpp_task_id": "",
    }


def _parity_row(
    case_name: str,
    policy: str,
    python_summary: dict[str, Any],
    python_trace: list[dict[str, Any]],
    cpp_summary: dict[str, Any],
    cpp_trace: list[dict[str, Any]],
) -> dict[str, float | int | str | bool]:
    summary_mismatch = _first_summary_mismatch(python_summary, cpp_summary)
    trace_mismatch = _first_trace_mismatch(python_trace, cpp_trace)
    summary_match = summary_mismatch["status"] == "match"
    trace_match = trace_mismatch["status"] == "match"
    first = trace_mismatch if not trace_match else summary_mismatch
    return {
        "case": case_name,
        "policy": policy,
        "python_planned": int(python_summary["planned_count"]),
        "cpp_planned": int(cpp_summary["planned_count"]),
        "python_unplanned": int(python_summary["unplanned_count"]),
        "cpp_unplanned": int(cpp_summary["unplanned_count"]),
        "python_decisions": int(python_summary["decision_count"]),
        "cpp_decisions": int(cpp_summary["decision_count"]),
        "python_conflicts": int(python_summary["post_shield_conflicts"]),
        "cpp_conflicts": int(cpp_summary["post_shield_conflicts"]),
        "mean_travel_abs_diff": abs(
            float(python_summary["mean_travel_time"]) - float(cpp_summary["mean_travel_time"])
        ),
        "makespan_abs_diff": abs(float(python_summary["makespan"]) - float(cpp_summary["makespan"])),
        "python_trace_rows": len(python_trace),
        "cpp_trace_rows": len(cpp_trace),
        "summary_match": summary_match,
        "trace_match": trace_match,
        "strict_parity_pass": summary_match and trace_match,
        "first_mismatch_status": first["status"],
        "first_mismatch_decision": first["decision_ordinal"],
        "first_mismatch_field": first["field"],
        "python_value": first["python_value"],
        "cpp_value": first["cpp_value"],
    }


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]], manifest_path: Path) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    strict_pass = all(bool(row["strict_parity_pass"]) for row in rows)
    safety_pass = all(int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows)
    edge_score_rows = sum(1 for row in rows if row["policy"] == "edge_score_event")
    fallback_rows = sum(1 for row in rows if row["policy"] == "fallback_event")
    lines = [
        "# Phase8 Native C++ Event Scheduler Parity",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        (
            "This diagnostic compares the Python event-queue replay reference against native C++ "
            "event replay on the persisted synthetic manifest. It checks both aggregate summaries "
            "and decision-level traces for EdgeScore-runtime and shortest-safe fallback policies."
        ),
        "",
        f"Manifest: `{manifest_path.relative_to(ROOT).as_posix()}`",
        "",
        (
            "This validates event-scheduler Python/C++ semantics on synthetic heldout-like fixtures. "
            "It is still not a real-airport heldout map or final paper-grade throughput claim."
        ),
        "",
        "## Metrics",
        "",
        (
            "| Case | Policy | Py planned | C++ planned | Py decisions | C++ decisions | "
            "Mean diff | Trace rows | Strict parity | First mismatch |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {python_planned} | {cpp_planned} | {python_decisions} | "
            "{cpp_decisions} | {mean_travel_abs_diff:.12f} | {python_trace_rows}/{cpp_trace_rows} | "
            "{strict_parity_pass} | "
            "{first_mismatch_status}:{first_mismatch_field}@{first_mismatch_decision} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            (
                "- event scheduler Python/C++ trace parity: PASS"
                if strict_pass
                else "- event scheduler Python/C++ trace parity: FAIL"
            ),
            (
                "- event scheduler post-shield safety: PASS"
                if safety_pass
                else "- event scheduler post-shield safety: FAIL"
            ),
            f"- EdgeScore event parity rows: `{edge_score_rows}`",
            f"- fallback event parity rows: `{fallback_rows}`",
            "- real heldout airport map: not covered",
            "- final throughput scaling: not covered",
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
        python_node_capacities = dict(case.spec.node_capacities)
        python_merge_groups = {
            (start_node, end_node): group for start_node, end_node, group in case.spec.merge_groups
        }
        common = {
            "max_tasks": case.spec.task_count,
            "fault_edges": set(case.spec.fault_edges),
            "max_decisions_per_task": MAX_DECISIONS_PER_TASK,
            "fault_windows": tuple(case.spec.fault_windows),
            "node_capacities": python_node_capacities,
            "merge_groups": python_merge_groups,
            "merge_capacity": case.spec.merge_capacity,
            "merge_headway_seconds": case.spec.merge_headway_seconds,
        }
        record_common = {
            "max_tasks": case.spec.task_count,
            "fault_edges": list(case.spec.fault_edges),
            "max_decisions_per_task": MAX_DECISIONS_PER_TASK,
            "fault_windows": list(case.spec.fault_windows),
            "node_capacities": list(case.spec.node_capacities),
            "merge_groups": list(case.spec.merge_groups),
            "merge_capacity": case.spec.merge_capacity,
            "merge_headway_seconds": case.spec.merge_headway_seconds,
        }
        node_records = list(case.node_records)
        edge_records = list(case.edge_records)
        heuristic_time = [list(row) for row in case.heuristic_time]
        task_records = list(case.task_records)
        payloads = (
            (
                "edge_score_event",
                run_event_replay(graph, tasks, runtime_model=runtime_model, **common),
                czr005_cpp.edge_score_native_event_replay_trace_from_records(
                    node_records,
                    edge_records,
                    heuristic_time,
                    task_records,
                    str(MODEL_PATH),
                    **record_common,
                ),
            ),
            (
                "fallback_event",
                run_event_replay(graph, tasks, runtime_model=None, **common),
                czr005_cpp.edge_score_native_event_fallback_replay_trace_from_records(
                    node_records,
                    edge_records,
                    heuristic_time,
                    task_records,
                    **record_common,
                ),
            ),
        )
        for policy, python_run, cpp_payload in payloads:
            rows.append(
                _parity_row(
                    case.spec.name,
                    policy,
                    python_run.summary,
                    python_run.trace,
                    dict(cpp_payload["summary"]),
                    [dict(row) for row in cpp_payload["trace"]],
                )
            )

    write_table(rows)
    write_report(rows, MANIFEST_PATH)
    if not all(bool(row["strict_parity_pass"]) for row in rows):
        raise AssertionError("event scheduler Python/C++ parity failed")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("event scheduler parity produced post-shield conflicts")
    print(f"phase8_native_cpp_event_parity rows={len(rows)} strict_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
