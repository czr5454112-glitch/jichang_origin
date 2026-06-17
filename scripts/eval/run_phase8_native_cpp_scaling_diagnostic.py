from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_scaling_diagnostic.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_scaling_diagnostic_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    no_conflicts = all(int(row["python_conflicts"]) == 0 and int(row["cpp_conflicts"]) == 0 for row in rows)
    no_crashes = all(not bool(row["python_truncated"]) for row in rows)
    any_divergence = any(not bool(row["planned_match"]) or not bool(row["decision_match"]) for row in rows)
    lines = [
        "# Phase8 Native C++ Scaling Diagnostic",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This diagnostic extends the compact native C++ / Python comparison to larger same-map task windows. It is intentionally a diagnostic rather than a parity gate: the compact C++ replay and Python environment still diverge after fallback-heavy states appear.",
        "",
        "## Metrics",
        "",
        "| Window | Py planned | C++ planned | Py unplanned | C++ unplanned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Planned match | Decision match |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {max_tasks} | {python_planned} | {cpp_planned} | {python_unplanned} | {cpp_unplanned} | "
            "{python_steps} | {cpp_decision_count} | {mean_travel_abs_diff:.6f} | "
            "{python_conflicts} | {cpp_conflicts} | {planned_match} | {decision_match} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Diagnostic Status",
            "",
            "- larger-window safety: PASS" if no_conflicts and no_crashes else "- larger-window safety: FAIL",
            "- larger-window divergence observed: YES" if any_divergence else "- larger-window divergence observed: NO",
            "- strict larger-window parity: not claimed",
            "",
            "## Notes",
            "",
            "The first 8/16 task windows have strict EdgeScore parity in the separate Phase8 parity report. Larger windows remain conflict-free but diverge in planned counts and decision counts once fallback-heavy local states occur. This gives the next C++ event-scheduler work a concrete target instead of hiding the mismatch.",
            "",
            "## Remaining Work",
            "",
            "- align fallback execution semantics and task cleanup between compact C++ replay and Python env",
            "- add trace-level divergence localization for the first mismatching task/decision",
            "- replace compact replay with the full C++ event scheduler and rerun this diagnostic",
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
    for max_tasks in (24, 32, 48, 64):
        env = IcsJunctionEnv(
            graph,
            tasks[:max_tasks],
            max_decisions_per_task=128,
        )
        python_result, python_run = env.run_policy(
            runtime_edge_score_policy_factory(runtime_model),
            seed=43,
            max_steps=max_tasks * 128,
        )
        python_summary = env.episode_summary()
        cpp_summary = czr005_cpp.edge_score_native_replay_summary(
            str(LEGACY / "map2.txt"),
            str(LEGACY / "inputdata.txt"),
            str(MODEL_PATH),
            max_tasks=max_tasks,
            fault_edges=[],
            max_decisions_per_task=128,
        )
        mean_diff = abs(python_result.metrics.mean_travel_time - float(cpp_summary["mean_travel_time"]))
        rows.append(
            {
                "max_tasks": max_tasks,
                "python_planned": python_result.metrics.planned_count,
                "cpp_planned": int(cpp_summary["planned_count"]),
                "planned_match": python_result.metrics.planned_count == int(cpp_summary["planned_count"]),
                "python_unplanned": python_result.metrics.unplanned_count,
                "cpp_unplanned": int(cpp_summary["unplanned_count"]),
                "unplanned_match": python_result.metrics.unplanned_count == int(cpp_summary["unplanned_count"]),
                "python_steps": python_run.steps,
                "cpp_decision_count": int(cpp_summary["decision_count"]),
                "decision_match": python_run.steps == int(cpp_summary["decision_count"]),
                "python_mean_travel_time": python_result.metrics.mean_travel_time,
                "cpp_mean_travel_time": float(cpp_summary["mean_travel_time"]),
                "mean_travel_abs_diff": mean_diff,
                "python_conflicts": int(python_summary["post_shield_conflicts"]),
                "cpp_conflicts": int(cpp_summary["post_shield_conflicts"]),
                "python_truncated": python_run.truncated,
            }
        )

    write_table(rows)
    write_report(rows)
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("larger-window diagnostic produced post-shield conflicts")
    if any(bool(row["python_truncated"]) for row in rows):
        raise AssertionError("larger-window Python diagnostic truncated")

    print(
        "phase8_native_cpp_scaling windows={} divergences={}".format(
            len(rows),
            sum(1 for row in rows if not bool(row["planned_match"]) or not bool(row["decision_match"])),
        )
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
