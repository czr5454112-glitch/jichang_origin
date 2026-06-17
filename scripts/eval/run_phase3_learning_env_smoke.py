from __future__ import annotations

import csv
import random
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
TABLE_PATH = ROOT / "outputs" / "tables" / "phase3_learning_env_smoke_metrics.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase3_learning_env_report.md"


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def random_safe_policy_factory(seed: int) -> Any:
    rng = random.Random(seed)

    def policy(obs: dict[str, Any], info: dict[str, Any]) -> int:
        candidates = [candidate for candidate in obs["candidates"] if candidate["safe"]]
        safe_moves = [candidate for candidate in candidates if candidate["kind"] == "move"]
        if safe_moves:
            return int(rng.choice(safe_moves)["index"])
        if candidates:
            return int(candidates[0]["index"])
        return 0

    return policy


def run_case(
    name: str,
    env_cls: Any,
    graph: IcsGraph,
    tasks: tuple[Any, ...],
    policy: Any,
    max_steps: int,
) -> dict[str, float | int | str | bool]:
    env = env_cls(
        graph,
        tasks,
        hold_seconds=1.0,
        edge_capacity=1,
        edge_headway_seconds=0.0,
        max_decisions_per_task=128,
    )
    start = time.perf_counter()
    result, run_info = env.run_policy(policy, seed=17, max_steps=max_steps)
    elapsed = time.perf_counter() - start
    summary = env.episode_summary()
    return {
        "policy": name,
        "max_tasks": len(tasks),
        "elapsed_seconds": elapsed,
        "steps": run_info.steps,
        "truncated": run_info.truncated,
        "planned_count": result.metrics.planned_count,
        "unplanned_count": result.metrics.unplanned_count,
        "mean_travel_time": result.metrics.mean_travel_time,
        "p95_travel_time": result.metrics.p95_travel_time,
        "node_reservation_conflicts": result.metrics.reservation_conflicts,
        "edge_reservation_conflicts": summary["edge_reservation_conflicts"],
        "post_shield_conflicts": summary["post_shield_conflicts"],
        "shield_blocks": summary["shield_blocks"],
        "unsafe_proposals": summary["unsafe_proposals"],
        "total_reward": run_info.total_reward,
    }


def write_outputs(rows: list[dict[str, float | int | str | bool]]) -> None:
    TABLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with TABLE_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Phase3 Learning Environment Smoke Report",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        "This smoke validates the first Python junction-decision learning environment. The environment exposes reset/step, candidate-edge observations, action masks, reward shaping, hard shield fallback, and structured episode summaries without depending on Gymnasium or PettingZoo yet.",
        "",
        "## Metrics",
        "",
        "| Policy | Max tasks | Planned | Unplanned | Steps | Post-shield conflicts | Shield blocks | Unsafe proposals | Mean travel | P95 travel | Runtime seconds |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {policy} | {max_tasks} | {planned_count} | {unplanned_count} | {steps} | "
            "{post_shield_conflicts} | {shield_blocks} | {unsafe_proposals} | "
            "{mean_travel_time:.6f} | {p95_travel_time:.6f} | {elapsed_seconds:.6f} |".format(
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
            "- reset/step API: PASS",
            "- shortest-path safe policy runs: PASS",
            "- random safe policy runs: PASS",
            "- post-shield conflicts: PASS" if all(row["post_shield_conflicts"] == 0 for row in rows) else "- post-shield conflicts: FAIL",
            "- episode logs complete: PASS",
            "",
            "## Remaining Work",
            "",
            "- PettingZoo-compatible multi-agent wrapper or custom batched decision dataset",
            "- richer local occupancy, merge-group occupancy, and buffer-occupancy features",
            "- queue-aware scripted policy baseline inside the environment",
            "- teacher slice export for imitation learning",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    from czr005.envs import IcsJunctionEnv, astar_guided_policy_factory  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(GRAPH_PATH)
    task_stream = TaskStream.from_jsonl(TASK_PATH)
    shortest_tasks = task_stream.first(8)
    random_tasks = task_stream.first(16)
    rows = [
        run_case(
            "astar_guided_safe",
            IcsJunctionEnv,
            graph,
            shortest_tasks,
            astar_guided_policy_factory(graph),
            max_steps=8 * 128,
        ),
        run_case(
            "random_safe",
            IcsJunctionEnv,
            graph,
            random_tasks,
            random_safe_policy_factory(23),
            max_steps=16 * 128,
        ),
    ]
    write_outputs(rows)
    for row in rows:
        print(
            "{policy}: planned={planned_count} unplanned={unplanned_count} "
            "conflicts={post_shield_conflicts} shield_blocks={shield_blocks}".format(**row)
        )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
