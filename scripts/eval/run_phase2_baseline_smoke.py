from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = ROOT / "outputs" / "tables" / "phase2_baseline_smoke_metrics.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase2_baseline_and_shield_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase2 baseline smoke replay.")
    parser.add_argument("--max-tasks", type=int, default=128)
    parser.add_argument("--horizon-seconds", type=float, default=300.0)
    args = parser.parse_args()

    _prepare_imports()

    from czr005.baselines import RollingHorizonBaseline  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import (  # pylint: disable=import-outside-toplevel
        IcsGraph,
        ReferenceSimulator,
        TaskStream,
    )

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    stream = TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl")

    runs = []
    for name, runner in (
        ("reference_astar", ReferenceSimulator(graph)),
        ("rolling_horizon_sipp", RollingHorizonBaseline(graph, horizon_seconds=args.horizon_seconds)),
    ):
        start = perf_counter()
        result = runner.run_episode(stream, max_tasks=args.max_tasks)
        elapsed = perf_counter() - start
        metrics = result.metrics.to_dict()
        edge_reservations = getattr(runner, "edge_reservations", None)
        edge_conflicts = (
            edge_reservations.conflict_count(
                capacity=getattr(runner, "edge_capacity", 1),
                headway_seconds=getattr(runner, "edge_headway_seconds", 0.0),
            )
            if edge_reservations is not None
            else 0
        )
        runs.append(
            {
                "baseline": name,
                "max_tasks": args.max_tasks,
                "elapsed_seconds": f"{elapsed:.6f}",
                "planned_count": metrics["planned_count"],
                "unplanned_count": metrics["unplanned_count"],
                "mean_travel_time": f"{metrics['mean_travel_time']:.6f}",
                "p95_travel_time": f"{metrics['p95_travel_time']:.6f}",
                "p99_travel_time": f"{metrics['p99_travel_time']:.6f}",
                "late_count": metrics["late_count"],
                "max_lateness": f"{metrics['max_lateness']:.6f}",
                "makespan": f"{metrics['makespan']:.6f}",
                "reservation_conflicts": metrics["reservation_conflicts"],
                "edge_reservation_conflicts": edge_conflicts,
                "post_shield_conflicts": metrics["reservation_conflicts"] + edge_conflicts,
            }
        )

    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(runs[0]))
        writer.writeheader()
        writer.writerows(runs)

    rows = "\n".join(
        "| {baseline} | {planned_count} | {unplanned_count} | {post_shield_conflicts} | "
        "{mean_travel_time} | {p95_travel_time} | {elapsed_seconds} |".format(**run)
        for run in runs
    )
    conflict_gate = "PASS" if all(int(run["post_shield_conflicts"]) == 0 for run in runs) else "FAIL"
    report = f"""# Phase2 Baseline and Shield Smoke Report

Date: 2026-06-17

## Scope

This smoke runs two non-learning baselines on the same first `{args.max_tasks}` expanded task legs
from `inputdata.jsonl`:

- `reference_astar`: Phase1 Python A* reference replay
- `rolling_horizon_sipp`: Phase2 rolling-window SIPP baseline with horizon `{args.horizon_seconds}` seconds

This is still a smoke replay, not a full benchmark. It exercises node and edge reservation safety
plus baseline logging on real task-stream inputs.

## Metrics

| Baseline | Planned | Unplanned | Post-shield conflicts | Mean travel | P95 travel | Runtime seconds |
|---|---:|---:|---:|---:|---:|---:|
{rows}

CSV: `outputs/tables/phase2_baseline_smoke_metrics.csv`

Active-bag/replan-cost evidence is tracked separately in
`outputs/reports/phase2_active_bag_replanning_audit_report.md`.

Route-discarding periodic active-bag replanning parity is tracked in
`outputs/reports/phase2_periodic_replanning_parity_report.md`.

PIBT-style recursive current-node handoff parity is tracked in
`outputs/reports/phase2_cpp_pibt_parity_report.md`.

Active-bag PIBT replay parity is tracked in
`outputs/reports/phase2_pibt_active_bag_replay_parity_report.md`.

## Gate Status

- post-shield/reservation conflicts: {conflict_gate}
- reproducible baseline entry point: PASS
- full Phase2 baseline stack: incomplete

## Remaining Work

- full merge-group replay integration across every baseline
- full buffer-capacity replay integration across every baseline
- rolling-horizon active-bag replanning rather than sequential task-leg replay
- real heldout airport-map fixtures
- larger multi-seed task-density/fault sweeps
"""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")

    print(f"baselines={len(runs)} max_tasks={args.max_tasks}")
    for run in runs:
        print(
            f"{run['baseline']}: planned={run['planned_count']} "
            f"unplanned={run['unplanned_count']} conflicts={run['post_shield_conflicts']}"
        )
    if not all(int(run["post_shield_conflicts"]) == 0 for run in runs):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
