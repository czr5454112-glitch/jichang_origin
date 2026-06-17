from __future__ import annotations

import csv
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_manifest.jsonl"
DAGGER_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_dagger_smoke.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase5_robustness_sweep_metrics.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase5_robustness_sweep_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def write_table(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_report(rows: list[dict[str, float | int | str | bool]]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    no_conflicts = all(row["post_shield_conflicts"] == 0 for row in rows)
    fault_rows = [row for row in rows if row["case"].startswith("fault_")]
    dagger_fault_gap = any(
        row["policy"] == "dagger_bc" and row["unplanned_count"] > 0 for row in fault_rows
    )
    rolling_horizon_fault_recovery = any(
        row["policy"] == "rolling_horizon_sipp" and row["planned_count"] > 0 for row in fault_rows
    )

    lines = [
        "# Phase5 Robustness Sweep Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This diagnostic compares A*-guided junction policy, DAgger BC+shield, and rolling-horizon SIPP on small density and fault windows before starting Phase6 RL fine-tuning. It is intentionally allowed to expose failures so the fault curriculum has concrete targets.",
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
            "## Diagnostic Status",
            "",
            "- zero post-shield conflicts: PASS" if no_conflicts else "- zero post-shield conflicts: FAIL",
            "- fault cases expose BC robustness gap: YES" if dagger_fault_gap else "- fault cases expose BC robustness gap: NO",
            "- rolling-horizon SIPP recovers at least one fault case: YES" if rolling_horizon_fault_recovery else "- rolling-horizon SIPP recovers at least one fault case: NO",
            "- Phase6 fault curriculum target defined: PASS" if dagger_fault_gap else "- Phase6 fault curriculum target defined: INCOMPLETE",
            "",
            "## Notes",
            "",
            "The DAgger BC policy remains shield-safe, but it does not yet learn robust fallback behavior under selected faults. Rolling-horizon SIPP remains a stronger recovery baseline in these diagnostics.",
            "",
            "## Remaining Work",
            "",
            "- add fault-aware teacher slices and DAgger relabeling",
            "- train/evaluate BC on fault curriculum before RL",
            "- compare against PIBT-style resolver on simultaneous junction slices",
            "- expand density and repair-time sweeps",
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
    from czr005.envs import IcsJunctionEnv, astar_guided_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.eval import edge_score_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.models import fit_edge_score_model, load_teacher_manifest  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    tasks = tuple(TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"))
    base_slices = load_teacher_manifest(BASE_MANIFEST_PATH)
    dagger_slices = load_teacher_manifest(DAGGER_MANIFEST_PATH)
    model, _ = fit_edge_score_model(
        base_slices + dagger_slices,
        hidden_dim=16,
        epochs=200,
        learning_rate=0.05,
        seed=56,
    )

    env_policies = (
        ("astar_guided", astar_guided_policy_factory(graph)),
        ("dagger_bc", edge_score_policy_factory(model, safe_only=True)),
    )
    cases = (
        ("density_train_first8", tasks[:8], set()),
        ("density_heldout_next8", tasks[8:16], set()),
        ("density_combined_first16", tasks[:16], set()),
        ("fault_alt_route_first8", tasks[:8], {(16, 17)}),
        ("fault_goal_exit_first8", tasks[:8], {(28, 47)}),
    )

    rows: list[dict[str, float | int | str | bool]] = []
    for case_name, case_tasks, fault_edges in cases:
        for policy_name, policy in env_policies:
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
    write_report(rows)
    for row in rows:
        print(
            "{case} {policy}: planned={planned_count} unplanned={unplanned_count} "
            "conflicts={post_shield_conflicts}".format(**row)
        )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
