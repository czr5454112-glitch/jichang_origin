from __future__ import annotations

import csv
from datetime import date
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = Path(os.environ.get("CZR005_CPP_PYTHON_PATH", ROOT / "build_nmake" / "python"))
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_randomized_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_randomized_parity_report.md"
MAX_DECISIONS_PER_TASK = 128
TOLERANCE = 1.0e-9


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))
    sys.path.insert(0, str(Path(__file__).resolve().parent))


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]], manifest_path: Path) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    strict_pass = all(bool(row["strict_parity_pass"]) for row in rows)
    safety_pass = all(
        int(row["python_conflicts"]) == 0
        and int(row["cpp_conflicts"]) == 0
        and not bool(row["python_truncated"])
        for row in rows
    )
    lines = [
        "# Phase8 Native C++ Randomized Synthetic Parity Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This diagnostic checks compact native C++ replay parity against the Python junction environment on fixed-seed synthetic directed ICS-like maps. The rows vary map edge lengths, optional branch edges, task density, static fault edges, and repair-window schedules.",
        "",
        f"Manifest: `{manifest_path.relative_to(ROOT).as_posix()}`",
        "",
        "The graph, task stream, and fault schedule are loaded from a persisted manifest and passed through the pybind in-memory record API. This is randomized synthetic-map coverage, not a real heldout airport map or the final high-throughput C++ event scheduler.",
        "",
        "## Metrics",
        "",
        "| Case | Seed | Tasks | Edges | Spacing | Static faults | Repair windows | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Strict parity |",
        "|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {seed} | {task_count} | {edge_count} | {spacing:.3f} | {fault_edges} | "
            "{fault_windows} | {python_planned} | {cpp_planned} | {python_steps} | "
            "{cpp_decision_count} | {mean_travel_abs_diff:.12f} | {strict_parity_pass} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- randomized synthetic compact replay parity: PASS" if strict_pass else "- randomized synthetic compact replay parity: FAIL",
            "- randomized synthetic safety: PASS" if safety_pass else "- randomized synthetic safety: FAIL",
            "- persisted synthetic replay manifest: PASS",
            "- event-scheduler parity: covered by `phase8_native_cpp_event_parity_report.md`",
            "- real heldout-map parity: not covered",
            "",
            "## Remaining Work",
            "",
            "- add real heldout-map fixtures when available",
            "- expand randomized density/fault seeds before paper-grade claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.envs import IcsJunctionEnv  # pylint: disable=import-outside-toplevel
    from czr005.eval import runtime_edge_score_policy_factory  # pylint: disable=import-outside-toplevel
    from phase8_synthetic_replay_cases import (  # pylint: disable=import-outside-toplevel
        MANIFEST_PATH,
        cpp_replay_kwargs,
        format_faults,
        format_fault_windows,
        graph_from_case,
        load_manifest_cases,
        tasks_from_case,
    )

    cases = load_manifest_cases(MANIFEST_PATH)
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))
    rows: list[dict[str, float | int | str | bool]] = []

    for case in cases:
        graph = graph_from_case(case)
        tasks = tasks_from_case(case)
        fault_edges = set(case.spec.fault_edges)
        fault_windows = case.spec.fault_windows
        env = IcsJunctionEnv(
            graph,
            tasks,
            fault_edges=fault_edges,
            fault_windows=fault_windows,
            node_capacities=dict(case.spec.node_capacities),
            merge_groups={
                (start_node, end_node): group for start_node, end_node, group in case.spec.merge_groups
            },
            merge_capacity=case.spec.merge_capacity,
            merge_headway_seconds=case.spec.merge_headway_seconds,
            max_decisions_per_task=MAX_DECISIONS_PER_TASK,
        )
        python_result, python_run = env.run_policy(
            runtime_edge_score_policy_factory(runtime_model),
            seed=case.spec.seed,
            max_steps=case.spec.task_count * MAX_DECISIONS_PER_TASK,
        )
        python_summary = env.episode_summary()
        cpp_summary = czr005_cpp.edge_score_native_replay_summary_from_records(
            list(case.node_records),
            list(case.edge_records),
            [list(row) for row in case.heuristic_time],
            list(case.task_records),
            str(MODEL_PATH),
            **cpp_replay_kwargs(case.spec, MAX_DECISIONS_PER_TASK),
        )
        mean_diff = abs(python_result.metrics.mean_travel_time - float(cpp_summary["mean_travel_time"]))
        planned_match = python_result.metrics.planned_count == int(cpp_summary["planned_count"])
        unplanned_match = python_result.metrics.unplanned_count == int(cpp_summary["unplanned_count"])
        decision_match = python_run.steps == int(cpp_summary["decision_count"])
        conflict_match = int(python_summary["post_shield_conflicts"]) == int(cpp_summary["post_shield_conflicts"])
        mean_match = mean_diff <= TOLERANCE
        strict_parity_pass = all((planned_match, unplanned_match, decision_match, conflict_match, mean_match))
        rows.append(
            {
                "case": case.spec.name,
                "seed": case.spec.seed,
                "task_count": case.spec.task_count,
                "node_count": len(case.node_records),
                "edge_count": len(case.edge_records),
                "spacing": case.spec.spacing,
                "fault_edges": format_faults(case.spec.fault_edges),
                "fault_windows": format_fault_windows(fault_windows),
                "python_planned": python_result.metrics.planned_count,
                "cpp_planned": int(cpp_summary["planned_count"]),
                "planned_match": planned_match,
                "python_unplanned": python_result.metrics.unplanned_count,
                "cpp_unplanned": int(cpp_summary["unplanned_count"]),
                "unplanned_match": unplanned_match,
                "python_steps": python_run.steps,
                "cpp_decision_count": int(cpp_summary["decision_count"]),
                "decision_match": decision_match,
                "python_mean_travel_time": python_result.metrics.mean_travel_time,
                "cpp_mean_travel_time": float(cpp_summary["mean_travel_time"]),
                "mean_travel_abs_diff": mean_diff,
                "mean_travel_match": mean_match,
                "python_conflicts": int(python_summary["post_shield_conflicts"]),
                "cpp_conflicts": int(cpp_summary["post_shield_conflicts"]),
                "conflict_match": conflict_match,
                "python_truncated": python_run.truncated,
                "strict_parity_pass": strict_parity_pass,
            }
        )

    write_table(rows)
    write_report(rows, MANIFEST_PATH)
    if not all(bool(row["strict_parity_pass"]) for row in rows):
        raise AssertionError("randomized synthetic compact replay parity failed")
    if any(bool(row["python_truncated"]) for row in rows):
        raise AssertionError("randomized synthetic Python replay truncated")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("randomized synthetic replay produced post-shield conflicts")

    print(f"phase8_native_cpp_randomized_parity rows={len(rows)} strict_pass=True")
    print(f"manifest={MANIFEST_PATH}")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
