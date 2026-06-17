from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_python_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_python_parity_report.md"
TOLERANCE = 1.0e-9


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def _format_faults(fault_edges: set[tuple[int, int]]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    edge_rows = [row for row in rows if row["policy"] == "edge_score_runtime"]
    fallback_rows = [row for row in rows if row["policy"] == "shortest_safe_fallback"]
    edge_strict_pass = all(bool(row["strict_parity_pass"]) for row in edge_rows)
    fallback_safety_pass = all(bool(row["safety_pass"]) for row in fallback_rows)
    fallback_strict_matches = sum(1 for row in fallback_rows if bool(row["strict_parity_pass"]))
    fallback_strict_pass = fallback_strict_matches == len(fallback_rows)
    fallback_scope = (
        "The model-unavailable shortest-safe fallback is also checked for strict parity on these small windows; it remains a runtime contingency rather than the learned-policy claim."
        if fallback_strict_pass
        else "The model-unavailable shortest-safe fallback is reported as a safety diagnostic because the compact C++ fallback and Python fallback can differ in tie-breaking or task-cleanup behavior."
    )
    fallback_follow_up = (
        "- keep fallback parity covered when expanding to repair events, randomized density, and heldout maps"
        if fallback_strict_pass
        else "- align fallback tie-breaking and goal-node reservation semantics if fallback metric parity becomes a paper claim"
    )

    lines = [
        "# Phase8 Native C++ / Python Replay Parity Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This diagnostic compares the compact native C++ EdgeScore replay against the existing Python junction environment on identical map2 task windows and fault schedules.",
        "",
        "The strict parity gate applies to the loaded EdgeScore runtime policy. " + fallback_scope,
        "",
        "## Metrics",
        "",
        "| Case | Policy | Faults | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Strict parity | Safety |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {fault_edges} | {python_planned} | {cpp_planned} | "
            "{python_steps} | {cpp_decision_count} | {mean_travel_abs_diff:.12f} | "
            "{python_conflicts} | {cpp_conflicts} | {strict_parity_pass} | {safety_pass} |".format(**row)
        )
    lines.extend(
        [
            "",
            f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- EdgeScore native C++ vs Python strict replay parity: PASS" if edge_strict_pass else "- EdgeScore native C++ vs Python strict replay parity: FAIL",
            "- fallback safety diagnostic: PASS" if fallback_safety_pass else "- fallback safety diagnostic: FAIL",
            "- fallback strict replay parity: PASS" if fallback_strict_pass else "- fallback strict replay parity: FAIL",
            f"- fallback strict parity rows: `{fallback_strict_matches}/{len(fallback_rows)}`",
            "- full high-throughput C++ event simulator parity: not covered",
            "",
            "## Remaining Work",
            "",
            fallback_follow_up,
            "- expand parity to larger windows, repair events, randomized density, and heldout maps",
            "- replace the compact replay with the full C++ event scheduler before final runtime claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.envs import IcsJunctionEnv, shortest_safe_policy  # pylint: disable=import-outside-toplevel
    from czr005.eval import runtime_edge_score_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    tasks = tuple(TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"))
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))
    cases = (
        ("first8", 8, set()),
        ("first16", 16, set()),
        ("fault_alt_route_first8", 8, {(16, 17)}),
        ("fault_goal_exit_first8", 8, {(28, 47)}),
    )

    rows: list[dict[str, float | int | str | bool]] = []
    for case_name, max_tasks, fault_edges in cases:
        policies = (
            (
                "edge_score_runtime",
                runtime_edge_score_policy_factory(runtime_model),
                czr005_cpp.edge_score_native_replay_summary(
                    str(LEGACY / "map2.txt"),
                    str(LEGACY / "inputdata.txt"),
                    str(MODEL_PATH),
                    max_tasks=max_tasks,
                    fault_edges=list(fault_edges),
                    max_decisions_per_task=128,
                ),
            ),
            (
                "shortest_safe_fallback",
                shortest_safe_policy,
                czr005_cpp.edge_score_native_fallback_replay_summary(
                    str(LEGACY / "map2.txt"),
                    str(LEGACY / "inputdata.txt"),
                    max_tasks=max_tasks,
                    fault_edges=list(fault_edges),
                    max_decisions_per_task=128,
                ),
            ),
        )
        for policy_name, python_policy, cpp_summary in policies:
            env = IcsJunctionEnv(
                graph,
                tasks[:max_tasks],
                fault_edges=fault_edges,
                max_decisions_per_task=128,
            )
            python_result, python_run = env.run_policy(
                python_policy,
                seed=43,
                max_steps=max_tasks * 128,
            )
            python_summary = env.episode_summary()
            planned_match = python_result.metrics.planned_count == int(cpp_summary["planned_count"])
            unplanned_match = python_result.metrics.unplanned_count == int(cpp_summary["unplanned_count"])
            decision_match = python_run.steps == int(cpp_summary["decision_count"])
            conflict_match = int(python_summary["post_shield_conflicts"]) == int(cpp_summary["post_shield_conflicts"])
            mean_diff = abs(python_result.metrics.mean_travel_time - float(cpp_summary["mean_travel_time"]))
            mean_match = mean_diff <= TOLERANCE
            strict_parity_pass = all(
                (planned_match, unplanned_match, decision_match, conflict_match, mean_match)
            )
            safety_pass = (
                int(python_summary["post_shield_conflicts"]) == 0
                and int(cpp_summary["post_shield_conflicts"]) == 0
                and not python_run.truncated
            )
            rows.append(
                {
                    "case": case_name,
                    "policy": policy_name,
                    "fault_edges": _format_faults(fault_edges),
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
                    "safety_pass": safety_pass,
                }
            )

    write_table(rows)
    write_report(rows)
    edge_rows = [row for row in rows if row["policy"] == "edge_score_runtime"]
    fallback_rows = [row for row in rows if row["policy"] == "shortest_safe_fallback"]
    if not all(bool(row["strict_parity_pass"]) for row in edge_rows):
        raise AssertionError("EdgeScore native C++ replay parity failed")
    if not all(bool(row["safety_pass"]) for row in fallback_rows):
        raise AssertionError("fallback safety diagnostic failed")

    print(
        "phase8_native_cpp_python_parity edge_rows={} fallback_rows={} edge_strict_pass={}".format(
            len(edge_rows),
            len(fallback_rows),
            all(bool(row["strict_parity_pass"]) for row in edge_rows),
        )
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
