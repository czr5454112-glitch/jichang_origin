from __future__ import annotations

import csv
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_offset_fault_parity.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_offset_fault_parity_report.md"
RANDOM_SEED = 20260617
WINDOW_SIZE = 24
TOLERANCE = 1.0e-9


FAULT_CASES: tuple[tuple[str, set[tuple[int, int]]], ...] = (
    ("none", set()),
    ("alt_route_16_17", {(16, 17)}),
    ("goal_exit_28_47", {(28, 47)}),
    ("branch_6_8", {(6, 8)}),
)


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def _format_faults(fault_edges: set[tuple[int, int]]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def _case_plan(task_count: int) -> tuple[tuple[str, int, set[tuple[int, int]]], ...]:
    rng = random.Random(RANDOM_SEED)
    max_offset = max(0, min(task_count - WINDOW_SIZE, 256))
    sampled_offsets = sorted(rng.sample(range(max_offset + 1), 4))
    deterministic_offsets = (0, 8, 16, 32)
    offsets = tuple(dict.fromkeys((*deterministic_offsets, *sampled_offsets)))
    cases: list[tuple[str, int, set[tuple[int, int]]]] = []
    for offset in offsets:
        fault_name, faults = FAULT_CASES[len(cases) % len(FAULT_CASES)]
        cases.append((f"offset_{offset}_{fault_name}", offset, faults))
    return tuple(cases)


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
        "# Phase8 Native C++ Offset/Fault Parity Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        f"This diagnostic checks compact native C++ replay parity against the Python junction environment on `{WINDOW_SIZE}`-task windows selected from deterministic offsets plus fixed-seed randomized offsets. Each row applies either no fault or one static fault edge. This is not repair-event or heldout-map validation.",
        "",
        f"Random seed: `{RANDOM_SEED}`",
        "",
        "## Metrics",
        "",
        "| Case | Offset | Faults | Py planned | C++ planned | Py steps | C++ decisions | Mean diff | Py conflicts | C++ conflicts | Strict parity |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {task_offset} | {fault_edges} | {python_planned} | {cpp_planned} | "
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
            "- offset/fault strict compact replay parity: PASS" if strict_pass else "- offset/fault strict compact replay parity: FAIL",
            "- offset/fault safety: PASS" if safety_pass else "- offset/fault safety: FAIL",
            "- full repair-event parity: not covered",
            "- heldout-map parity: not covered",
            "",
            "## Remaining Work",
            "",
            "- add repair-event schedules rather than static fault edges",
            "- validate heldout maps and randomized synthetic maps",
            "- replace compact replay with the full C++ event scheduler before final runtime claims",
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
    for case_name, task_offset, fault_edges in _case_plan(len(tasks)):
        case_tasks = tasks[task_offset : task_offset + WINDOW_SIZE]
        env = IcsJunctionEnv(
            graph,
            case_tasks,
            fault_edges=fault_edges,
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
            fault_edges=list(fault_edges),
            max_decisions_per_task=128,
            task_offset=task_offset,
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
            }
        )

    write_table(rows)
    write_report(rows)
    if not all(bool(row["strict_parity_pass"]) for row in rows):
        raise AssertionError("offset/fault compact replay parity failed")
    if any(bool(row["python_truncated"]) for row in rows):
        raise AssertionError("offset/fault Python replay truncated")
    if any(int(row["python_conflicts"]) != 0 or int(row["cpp_conflicts"]) != 0 for row in rows):
        raise AssertionError("offset/fault replay produced post-shield conflicts")

    print(f"phase8_native_cpp_offset_fault_parity rows={len(rows)} strict_pass=True")
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
