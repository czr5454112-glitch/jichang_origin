from __future__ import annotations

import csv
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
BASE_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_manifest.jsonl"
DAGGER_MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_dagger_smoke.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase5_validation_sweep_metrics.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase5_validation_sweep_report.md"


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
    by_case_policy = {(row["case"], row["policy"]): row for row in rows}
    heldout_match = (
        by_case_policy[("heldout_next8", "dagger_bc")]["planned_count"]
        >= by_case_policy[("heldout_next8", "astar_guided")]["planned_count"]
    )
    combined_match = (
        by_case_policy[("combined_first16", "dagger_bc")]["planned_count"]
        >= by_case_policy[("combined_first16", "astar_guided")]["planned_count"]
    )
    no_conflicts = all(row["post_shield_conflicts"] == 0 for row in rows)

    lines = [
        "# Phase5 Validation Sweep Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This sweep validates the DAgger BC+shield smoke policy beyond the exact first-eight training replay. It trains a pure-Python MLP-EdgeScore model from the base teacher manifest plus the DAgger smoke manifest, then compares A*-guided baseline and DAgger BC closed-loop execution on training, heldout task-leg, and combined task windows.",
        "",
        "This is a task-window heldout smoke on the same `map2` graph. It is not a heldout-map claim.",
        "",
        "## Metrics",
        "",
        "| Case | Policy | Max tasks | Planned | Unplanned | Conflicts | Steps | Mean travel | Runtime seconds |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {case} | {policy} | {max_tasks} | {planned_count} | {unplanned_count} | "
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
            "- heldout next8 planned count matches A*-guided smoke: PASS" if heldout_match else "- heldout next8 planned count matches A*-guided smoke: FAIL",
            "- combined first16 planned count matches A*-guided smoke: PASS" if combined_match else "- combined first16 planned count matches A*-guided smoke: FAIL",
            "- heldout map validation: not started",
            "",
            "## Remaining Work",
            "",
            "- add heldout-map or synthetic-map validation",
            "- add fault and density sweeps",
            "- compare against rolling-horizon SIPP and PIBT-style baselines on larger windows",
            "- use this validation harness before Phase6 RL fine-tuning claims",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

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
    policies = (
        ("astar_guided", astar_guided_policy_factory(graph)),
        ("dagger_bc", edge_score_policy_factory(model, safe_only=True)),
    )
    cases = (
        ("train_first8", tasks[:8]),
        ("heldout_next8", tasks[8:16]),
        ("combined_first16", tasks[:16]),
    )

    rows: list[dict[str, float | int | str | bool]] = []
    for case_name, case_tasks in cases:
        for policy_name, policy in policies:
            env = IcsJunctionEnv(graph, case_tasks, max_decisions_per_task=128)
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
