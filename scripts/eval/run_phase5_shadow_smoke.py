from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_manifest.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase5_shadow_smoke_metrics.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase5_shadow_and_closed_loop_smoke.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def write_table(row: dict[str, float | int | str | bool]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def write_report(row: dict[str, float | int | str | bool]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase5 Shadow And Closed-Loop Smoke Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This smoke evaluates the Phase4 MLP-EdgeScore model in shadow mode against the A*-guided safe baseline, then runs a small BC+shield closed-loop replay. The model is trained in-memory from the Phase4 teacher manifest for reproducibility.",
        "",
        "## Metrics",
        "",
        "| Decisions | Disagreements | Disagreement rate | Unsafe proposals | Unsafe rate | Improvement opportunities | Baseline planned | Closed-loop planned | Closed-loop conflicts |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| {decisions} | {disagreements} | {disagreement_rate:.6f} | {unsafe_proposals} | {unsafe_proposal_rate:.6f} | {safe_improvement_opportunities} | {baseline_planned} | {closed_loop_planned} | {closed_loop_conflicts} |".format(
            **row
        ),
        "",
        f"CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "## Gate Status",
        "",
        "- shadow replay completed: PASS",
        "- closed-loop BC+shield replay completed: PASS",
        "- shadow post-shield conflicts: PASS" if row["baseline_conflicts"] == 0 else "- shadow post-shield conflicts: FAIL",
        "- closed-loop post-shield conflicts: PASS" if row["closed_loop_conflicts"] == 0 else "- closed-loop post-shield conflicts: FAIL",
        "- unsafe proposal rate acceptable for smoke: PASS" if row["unsafe_proposal_rate"] <= 0.10 else "- unsafe proposal rate acceptable for smoke: FAIL",
        "",
        "## Remaining Work",
        "",
        "- train/evaluate on larger heldout teacher splits",
        "- add deadline-critical mistake analysis",
        "- compare closed-loop BC+shield against Phase2 baselines on larger task sets",
        "- add fault and density shadow sweeps",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    from czr005.envs import IcsJunctionEnv, astar_guided_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.eval import edge_score_policy_factory, run_shadow_replay  # pylint: disable=import-outside-toplevel
    from czr005.models import evaluate_top1, fit_edge_score_model, load_teacher_manifest  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    stream = TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl")
    slices = load_teacher_manifest(MANIFEST_PATH)
    model, _ = fit_edge_score_model(slices, hidden_dim=16, epochs=200, learning_rate=0.05, seed=41)
    teacher_top1 = evaluate_top1(model, slices)

    max_tasks = 8
    shadow_env = IcsJunctionEnv(graph, stream.first(max_tasks), max_decisions_per_task=128)
    shadow = run_shadow_replay(
        shadow_env,
        astar_guided_policy_factory(graph),
        model,
        seed=43,
        max_steps=max_tasks * 128,
    )

    closed_env = IcsJunctionEnv(graph, stream.first(max_tasks), max_decisions_per_task=128)
    closed_result, closed_run = closed_env.run_policy(
        edge_score_policy_factory(model, safe_only=True),
        seed=43,
        max_steps=max_tasks * 128,
    )
    closed_summary = closed_env.episode_summary()
    row: dict[str, float | int | str | bool] = {
        "max_tasks": max_tasks,
        "teacher_top1": teacher_top1,
        **shadow.to_dict(),
        "closed_loop_planned": closed_result.metrics.planned_count,
        "closed_loop_unplanned": closed_result.metrics.unplanned_count,
        "closed_loop_conflicts": closed_summary["post_shield_conflicts"],
        "closed_loop_steps": closed_run.steps,
        "closed_loop_truncated": closed_run.truncated,
    }
    write_table(row)
    write_report(row)
    print(
        "shadow_decisions={decisions} disagreement_rate={disagreement_rate:.6f} "
        "unsafe_rate={unsafe_proposal_rate:.6f} closed_loop_planned={closed_loop_planned} "
        "closed_loop_conflicts={closed_loop_conflicts}".format(**row)
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
