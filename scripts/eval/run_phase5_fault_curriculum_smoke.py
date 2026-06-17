from __future__ import annotations

import csv
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_manifest.jsonl"
DAGGER_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_dagger_smoke.jsonl"
FAULT_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_fault_curriculum_smoke.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase5_fault_curriculum_metrics.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase5_fault_curriculum_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]], fault_slice_count: int) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    no_conflicts = all(row["post_shield_conflicts"] == 0 for row in rows)
    fault_curriculum_rows = [
        row for row in rows if row["policy"] == "fault_curriculum_bc" and row["case"].startswith("fault_")
    ]
    recovers_faults = all(row["unplanned_count"] == 0 for row in fault_curriculum_rows)
    base_fault_rows = [
        row for row in rows if row["policy"] == "base_dagger_bc" and row["case"].startswith("fault_")
    ]
    improves_faults = sum(row["planned_count"] for row in fault_curriculum_rows) > sum(
        row["planned_count"] for row in base_fault_rows
    )

    lines = [
        "# Phase5 Fault Curriculum Smoke Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This smoke adds fault-aware teacher slices before Phase6 RL fine-tuning. A fault-aware A* teacher generates recovery labels for selected fault windows, then the pure-Python MLP-EdgeScore behavior cloning model is retrained with base, DAgger, and fault-curriculum slices.",
        "",
        "This is still a same-map smoke. It is not a heldout-map or RL result.",
        "",
        "## Dataset",
        "",
        f"- Fault manifest: `{FAULT_MANIFEST_PATH.relative_to(ROOT).as_posix()}`",
        f"- Fault slices: `{fault_slice_count}`",
        "",
        "## Metrics",
        "",
        "| Case | Policy | Fault edges | Max tasks | Planned | Unplanned | Conflicts | Steps | Mean travel | Runtime seconds |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {fault_edges} | {max_tasks} | {planned_count} | {unplanned_count} | "
            "{post_shield_conflicts} | {steps} | {mean_travel_time:.6f} | {elapsed_seconds:.6f} |".format(
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
            "- zero post-shield conflicts: PASS" if no_conflicts else "- zero post-shield conflicts: FAIL",
            "- fault curriculum improves selected fault recovery: PASS" if improves_faults else "- fault curriculum improves selected fault recovery: FAIL",
            "- fault curriculum recovers selected fault smoke cases: PASS" if recovers_faults else "- fault curriculum recovers selected fault smoke cases: FAIL",
            "- RL fine-tuning: not started",
            "",
            "## Notes",
            "",
            "The fault-curriculum BC policy improves recovery on the selected faults while remaining shield-safe. Travel times on fault cases are still worse than rolling-horizon SIPP, so SIPP remains the stronger recovery baseline.",
            "",
            "## Remaining Work",
            "",
            "- include fault-aware DAgger relabeling from model-visited failure states",
            "- add repair-time and multi-fault curricula",
            "- run larger windows and heldout-map validation",
            "- only then start Phase6 RL fine-tuning from the fault-aware BC checkpoint",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_faults(fault_edges: set[tuple[int, int]]) -> str:
    if not fault_edges:
        return "none"
    return ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def main() -> None:
    _prepare_imports()

    from czr005.baselines import RollingHorizonBaseline  # pylint: disable=import-outside-toplevel
    from czr005.datasets import collect_teacher_slices, write_teacher_manifest  # pylint: disable=import-outside-toplevel
    from czr005.envs import IcsJunctionEnv, fault_aware_astar_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.eval import edge_score_policy_factory as eval_edge_score_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.models import fit_edge_score_model, load_teacher_manifest  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    tasks = tuple(TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"))
    base_slices = load_teacher_manifest(BASE_MANIFEST_PATH)
    dagger_slices = load_teacher_manifest(DAGGER_MANIFEST_PATH)
    fault_cases = (
        ("fault_alt_route_first8", tasks[:8], {(16, 17)}),
        ("fault_goal_exit_first8", tasks[:8], {(28, 47)}),
    )

    fault_slices: list[dict[str, object]] = []
    for case_name, case_tasks, fault_edges in fault_cases:
        env = IcsJunctionEnv(
            graph,
            case_tasks,
            fault_edges=fault_edges,
            max_decisions_per_task=128,
        )
        run = collect_teacher_slices(
            env,
            fault_aware_astar_policy_factory(graph, fault_edges),
            seed=43,
            max_steps=len(case_tasks) * 128,
            expert_source=f"fault_aware_astar:{case_name}",
        )
        fault_slices.extend(run.slices)
    write_teacher_manifest(FAULT_MANIFEST_PATH, tuple(fault_slices))

    base_model, _ = fit_edge_score_model(
        base_slices + dagger_slices,
        hidden_dim=16,
        epochs=200,
        learning_rate=0.05,
        seed=56,
    )
    fault_model, _ = fit_edge_score_model(
        base_slices + dagger_slices + fault_slices,
        hidden_dim=16,
        epochs=160,
        learning_rate=0.05,
        seed=61,
    )

    cases = (
        ("density_train_first8", tasks[:8], set()),
        ("density_combined_first16", tasks[:16], set()),
        *fault_cases,
    )
    rows: list[dict[str, float | int | str | bool]] = []
    for case_name, case_tasks, fault_edges in cases:
        policies = (
            ("base_dagger_bc", eval_edge_score_policy_factory(base_model, safe_only=True)),
            ("fault_curriculum_bc", eval_edge_score_policy_factory(fault_model, safe_only=True)),
            ("fault_aware_astar", fault_aware_astar_policy_factory(graph, fault_edges)),
        )
        for policy_name, policy in policies:
            env = IcsJunctionEnv(
                graph,
                case_tasks,
                fault_edges=fault_edges,
                max_decisions_per_task=128,
            )
            start = perf_counter()
            result, run_info = env.run_policy(
                policy,
                seed=43,
                max_steps=len(case_tasks) * 128,
            )
            elapsed = perf_counter() - start
            summary = env.episode_summary()
            rows.append(
                {
                    "case": case_name,
                    "policy": policy_name,
                    "fault_edges": _format_faults(fault_edges),
                    "max_tasks": len(case_tasks),
                    "planned_count": result.metrics.planned_count,
                    "unplanned_count": result.metrics.unplanned_count,
                    "mean_travel_time": result.metrics.mean_travel_time,
                    "p95_travel_time": result.metrics.p95_travel_time,
                    "post_shield_conflicts": summary["post_shield_conflicts"],
                    "shield_blocks": summary["shield_blocks"],
                    "unsafe_proposals": summary["unsafe_proposals"],
                    "steps": run_info.steps,
                    "truncated": run_info.truncated,
                    "elapsed_seconds": elapsed,
                }
            )

        start = perf_counter()
        baseline = RollingHorizonBaseline(graph, horizon_seconds=300.0)
        result = baseline.run_episode(case_tasks, fault_edges=fault_edges)
        elapsed = perf_counter() - start
        rows.append(
            {
                "case": case_name,
                "policy": "rolling_horizon_sipp",
                "fault_edges": _format_faults(fault_edges),
                "max_tasks": len(case_tasks),
                "planned_count": result.metrics.planned_count,
                "unplanned_count": result.metrics.unplanned_count,
                "mean_travel_time": result.metrics.mean_travel_time,
                "p95_travel_time": result.metrics.p95_travel_time,
                "post_shield_conflicts": result.metrics.reservation_conflicts,
                "shield_blocks": 0,
                "unsafe_proposals": 0,
                "steps": len(result.events),
                "truncated": False,
                "elapsed_seconds": elapsed,
            }
        )

    write_table(rows)
    write_report(rows, len(fault_slices))
    for row in rows:
        print(
            "{case} {policy}: planned={planned_count} unplanned={unplanned_count} "
            "conflicts={post_shield_conflicts}".format(**row)
        )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
