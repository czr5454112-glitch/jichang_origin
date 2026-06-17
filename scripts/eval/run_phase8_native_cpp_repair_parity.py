from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_repair_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_repair_parity_report.md"
WINDOW_SIZE = 24
TOLERANCE = 1.0e-9

FaultWindow = tuple[int, int, float, float]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def _format_fault_windows(fault_windows: tuple[FaultWindow, ...]) -> str:
    if not fault_windows:
        return "none"
    return ";".join(
        f"{start}->{end}@[{fault_start:.3f},{repair_time:.3f})"
        for start, end, fault_start, repair_time in fault_windows
    )


def _case_plan() -> tuple[tuple[str, int, tuple[FaultWindow, ...]], ...]:
    return (
        (
            "repair_alt_route_first24",
            0,
            ((16, 17, 0.0, 10400.0),),
        ),
        (
            "repair_goal_exit_first24",
            0,
            ((28, 47, 0.0, 10350.0),),
        ),
        (
            "repair_branch_offset16",
            16,
            ((6, 8, 10650.0, 10750.0),),
        ),
        (
            "repair_multi_window_offset32",
            32,
            (
                (16, 17, 10700.0, 10825.0),
                (28, 47, 10800.0, 10950.0),
            ),
        ),
    )


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    strict_pass = all(bool(row["strict_parity_pass"]) for row in rows)
    safety_pass = all(
        int(row["python_conflicts"]) == 0
        and int(row["cpp_conflicts"]) == 0
        and not bool(row["python_truncated"])
        for row in rows
    )
    lines = [
        "# Phase8 Native C++ Repair-Window Parity Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        f"This diagnostic checks compact native C++ replay parity against the Python junction environment on `{WINDOW_SIZE}`-task map2 windows with time-bounded fault/repair windows. A window is active when `fault_start <= ready_time < repair_time`; after `repair_time`, the edge is available again.",
        "",
        "These rows validate repair-window semantics at the compact replay boundary. They are not a substitute for full Java route-update parity or the final high-throughput C++ event scheduler.",
        "",
        "## Metrics",
        "",
        "| Case | Offset | Repair windows | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Strict parity |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {task_offset} | {fault_windows} | {python_planned} | {cpp_planned} | "
            "{python_steps} | {cpp_decision_count} | {mean_travel_abs_diff:.12f} | "
            "{python_conflicts} | {cpp_conflicts} | {strict_parity_pass} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- repair-window strict compact replay parity: PASS" if strict_pass else "- repair-window strict compact replay parity: FAIL",
            "- repair-window safety: PASS" if safety_pass else "- repair-window safety: FAIL",
            "- full fault/repair event scheduler parity: not covered",
            "- heldout-map parity: not covered",
            "",
            "## Remaining Work",
            "",
            "- validate repair schedules on heldout and randomized maps",
            "- move from compact decision replay to the final event scheduler before runtime-throughput claims",
            "- expand repeated fault/repair schedule coverage after scheduler events are in place",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.envs import IcsJunctionEnv  # pylint: disable=import-outside-toplevel
    from czr005.eval import runtime_edge_score_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    tasks = tuple(TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"))
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))

    rows: list[dict[str, float | int | str | bool]] = []
    for case_name, task_offset, fault_windows in _case_plan():
        case_tasks = tasks[task_offset : task_offset + WINDOW_SIZE]
        env = IcsJunctionEnv(
            graph,
            case_tasks,
            fault_windows=fault_windows,
            max_decisions_per_task=128,
        )
        python_result, python_run = env.run_policy(
            runtime_edge_score_policy_factory(runtime_model),
            seed=43,
            max_steps=WINDOW_SIZE * 128,
        )
        python_summary = env.episode_summary()
        cpp_summary = czr005_cpp.edge_score_native_replay_summary(
            str(LEGACY / "map2.txt"),
            str(LEGACY / "inputdata.txt"),
            str(MODEL_PATH),
            max_tasks=WINDOW_SIZE,
            max_decisions_per_task=128,
            task_offset=task_offset,
            fault_windows=list(fault_windows),
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
                "case": case_name,
                "task_offset": task_offset,
                "window_size": WINDOW_SIZE,
                "fault_windows": _format_fault_windows(fault_windows),
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
    write_report(rows)
    if not all(bool(row["strict_parity_pass"]) for row in rows):
        raise AssertionError("repair-window compact replay parity failed")
    if any(bool(row["python_truncated"]) for row in rows):
        raise AssertionError("repair-window Python replay truncated")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("repair-window replay produced post-shield conflicts")

    print(f"phase8_native_cpp_repair_parity rows={len(rows)} strict_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
