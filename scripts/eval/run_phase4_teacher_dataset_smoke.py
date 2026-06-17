from __future__ import annotations

import csv
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "junction_slices_manifest.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase4_teacher_dataset_summary.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase4_teacher_dataset_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def write_summary(row: dict[str, float | int | str | bool]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)


def write_report(row: dict[str, float | int | str | bool]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Phase4 Teacher Dataset Smoke Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This smoke exports the first shielded teacher junction-slice manifest from the Phase3 environment. The expert source is an A*-guided safe scripted policy executed through the same action mask and hard shield used by the environment.",
        "",
        "## Dataset",
        "",
        f"- Manifest: `{MANIFEST_PATH.relative_to(ROOT).as_posix()}`",
        f"- Summary CSV: `{TABLE_PATH.relative_to(ROOT).as_posix()}`",
        f"- Expert source: `{row['expert_source']}`",
        f"- Task legs: `{row['max_tasks']}`",
        f"- Slices: `{row['slice_count']}`",
        f"- Planned task legs: `{row['planned_count']}`",
        f"- Unplanned task legs: `{row['unplanned_count']}`",
        f"- Reservation conflicts: `{row['reservation_conflicts']}`",
        f"- Fallback actions: `{row['fallback_count']}`",
        f"- Unsafe proposals: `{row['unsafe_proposal_count']}`",
        "",
        "## Slice Fields",
        "",
        "`obs`, `candidate_edges`, `action_mask`, `proposed_action`, `expert_action`, `expert_rank`, `expert_cost_to_goal`, `future_delay`, `shield_result`, `unsafe_proposal`, `reward`, and `reached_goal`.",
        "",
        "## Gate Status",
        "",
        "- teacher manifest written: PASS",
        "- action masks included: PASS",
        "- expert actions included: PASS",
        "- post-shield conflicts: PASS" if row["reservation_conflicts"] == 0 else "- post-shield conflicts: FAIL",
        "- BC training: not started",
        "",
        "## Remaining Work",
        "",
        "- collect larger multi-density teacher datasets",
        "- add rolling-horizon/SIPP and PIBT-style teacher sources",
        "- add train/validation split metadata",
        "- train the first MLP-EdgeScore behavior cloning baseline",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    from czr005.datasets import collect_teacher_slices, write_teacher_manifest  # pylint: disable=import-outside-toplevel
    from czr005.envs import IcsJunctionEnv, astar_guided_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    task_stream = TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl")
    max_tasks = 8
    env = IcsJunctionEnv(graph, task_stream.first(max_tasks), max_decisions_per_task=128)
    run = collect_teacher_slices(
        env=env,
        policy=astar_guided_policy_factory(graph),
        seed=31,
        max_steps=max_tasks * 128,
        expert_source="astar_guided_safe",
    )
    write_teacher_manifest(MANIFEST_PATH, run.slices)
    summary = run.summary()
    row: dict[str, float | int | str | bool] = {
        "expert_source": "astar_guided_safe",
        "max_tasks": max_tasks,
        **summary,
    }
    write_summary(row)
    write_report(row)
    print(
        "teacher_slices={slice_count} planned={planned_count} "
        "unplanned={unplanned_count} conflicts={reservation_conflicts}".format(**row)
    )
    print(f"manifest={MANIFEST_PATH}")


if __name__ == "__main__":
    main()
