from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_replay.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_replay_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def _format_faults(fault_edges: list[tuple[int, int]]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in fault_edges)


def write_table(rows: list[dict[str, float | int | str]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    no_conflicts = all(int(row["post_shield_conflicts"]) == 0 for row in rows)
    no_missing_tasks = all(
        int(row["planned_count"]) + int(row["unplanned_count"]) == int(row["max_tasks"])
        for row in rows
    )
    any_planned = any(int(row["planned_count"]) > 0 for row in rows)
    fallback_rows = [row for row in rows if row["policy"] == "shortest_safe_fallback"]
    fallback_ok = bool(fallback_rows) and all(int(row["post_shield_conflicts"]) == 0 for row in fallback_rows)
    lines = [
        "# Phase8 Native C++ EdgeScore Replay Smoke",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This smoke runs the loaded MLP-EdgeScore runtime artifact inside the native C++ replay loop. Unlike the previous Phase8 policy smoke, both candidate construction and action execution happen in C++ through the pybind summary boundary.",
        "",
        "The replay is intentionally compact and sequential. It is a native-runtime gate, not the final high-throughput event simulator.",
        "",
        "## Metrics",
        "",
        "| Case | Policy | Fault edges | Tasks | Planned | Unplanned | Decisions | Conflicts | Mean travel | Decisions/s |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {fault_edges} | {max_tasks} | {planned_count} | {unplanned_count} | "
            "{decision_count} | {post_shield_conflicts} | {mean_travel_time:.6f} | "
            "{decisions_per_second:.2f} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- native C++ replay callable through pybind: PASS",
            "- all configured task windows accounted for: PASS" if no_missing_tasks else "- all configured task windows accounted for: FAIL",
            "- zero post-shield conflicts: PASS" if no_conflicts else "- zero post-shield conflicts: FAIL",
            "- at least one task planned by native replay: PASS" if any_planned else "- at least one task planned by native replay: FAIL",
            "- model-unavailable fallback replay: PASS" if fallback_ok else "- model-unavailable fallback replay: FAIL",
            "- full high-throughput event simulator: not covered",
            "",
            "## Remaining Work",
            "",
            "- replace the compact sequential native replay with the full C++ event simulator",
            "- align C++ replay features and metrics one-for-one with the Python environment over larger windows",
            "- add repair events, randomized density schedules, and heldout-map replay",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel

    cases = (
        ("native_first8", 8, []),
        ("native_first16", 16, []),
        ("native_fault_alt_route_first8", 8, [(16, 17)]),
        ("native_fault_goal_exit_first8", 8, [(28, 47)]),
    )
    rows: list[dict[str, float | int | str]] = []
    for case_name, max_tasks, fault_edges in cases:
        policies = (
            (
                "edge_score_runtime",
                czr005_cpp.edge_score_native_replay_summary(
                    str(LEGACY / "map2.txt"),
                    str(LEGACY / "inputdata.txt"),
                    str(MODEL_PATH),
                    max_tasks=max_tasks,
                    fault_edges=fault_edges,
                    max_decisions_per_task=128,
                ),
            ),
            (
                "shortest_safe_fallback",
                czr005_cpp.edge_score_native_fallback_replay_summary(
                    str(LEGACY / "map2.txt"),
                    str(LEGACY / "inputdata.txt"),
                    max_tasks=max_tasks,
                    fault_edges=fault_edges,
                    max_decisions_per_task=128,
                ),
            ),
        )
        for policy_name, summary in policies:
            rows.append(
                {
                    "case": case_name,
                    "policy": policy_name,
                    "fault_edges": _format_faults(fault_edges),
                    "max_tasks": max_tasks,
                    "planned_count": int(summary["planned_count"]),
                    "unplanned_count": int(summary["unplanned_count"]),
                    "decision_count": int(summary["decision_count"]),
                    "shield_blocks": int(summary["shield_blocks"]),
                    "unsafe_proposals": int(summary["unsafe_proposals"]),
                    "post_shield_conflicts": int(summary["post_shield_conflicts"]),
                    "mean_travel_time": float(summary["mean_travel_time"]),
                    "makespan": float(summary["makespan"]),
                    "elapsed_seconds": float(summary["elapsed_seconds"]),
                    "decisions_per_second": float(summary["decisions_per_second"]),
                }
            )

    write_table(rows)
    write_report(rows)
    if any(int(row["post_shield_conflicts"]) != 0 for row in rows):
        raise AssertionError("native C++ replay produced post-shield conflicts")
    if any(int(row["planned_count"]) + int(row["unplanned_count"]) != int(row["max_tasks"]) for row in rows):
        raise AssertionError("native C++ replay did not account for all configured tasks")
    if not any(int(row["planned_count"]) > 0 for row in rows):
        raise AssertionError("native C++ replay did not plan any tasks")

    print(
        "phase8_native_cpp_replay cases={} planned_total={} conflicts={}".format(
            len(cases),
            sum(int(row["planned_count"]) for row in rows),
            sum(int(row["post_shield_conflicts"]) for row in rows),
        )
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
