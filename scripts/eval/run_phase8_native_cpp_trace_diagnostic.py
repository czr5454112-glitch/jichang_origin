from __future__ import annotations

import csv
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUILD_PYTHON_PATH = ROOT / "build_nmake" / "python"
LEGACY = ROOT / "legacy" / "jichang_origin_readonly"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"
FIRST_MISMATCH_TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_trace_first_mismatch.csv"
CONTEXT_TABLE_PATH = ROOT / "outputs" / "tables" / "phase8_native_cpp_trace_context.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "phase8_native_cpp_trace_diagnostic_report.md"
MAX_TASKS = 24
FLOAT_TOLERANCE = 1.0e-6


COMPARE_FIELDS = (
    "event",
    "task_id",
    "current",
    "goal",
    "ready_time",
    "executed_index",
    "executed_next",
    "executed_kind",
    "reached_goal",
)


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(BUILD_PYTHON_PATH))


def _candidate_by_index(candidates: list[dict[str, Any]], index: int | None) -> dict[str, Any] | None:
    if index is None:
        return None
    for candidate in candidates:
        if int(candidate["index"]) == index:
            return candidate
    return None


def _model_item_from_obs(obs: dict[str, Any]) -> dict[str, Any]:
    return {
        "obs": obs["task"],
        "candidate_edges": obs["candidates"],
        "action_mask": obs["action_mask"],
        "goal": obs["task"]["goal"],
        "expert_action": 0,
    }


def _runtime_action(runtime_model: Any, obs: dict[str, Any], info: dict[str, Any]) -> tuple[int, int, bool]:
    from czr005.envs import shortest_safe_policy  # pylint: disable=import-outside-toplevel
    from czr005.models.edge_score import featurize_slice  # pylint: disable=import-outside-toplevel

    features, candidate_indices, action_mask = featurize_slice(_model_item_from_obs(obs))
    try:
        selected_position = int(runtime_model.predict(features, action_mask))
        return int(candidate_indices[selected_position]), selected_position, False
    except (RuntimeError, ValueError):
        return shortest_safe_policy(obs, info), -1, True


def _python_runtime_trace(graph: Any, tasks: tuple[Any, ...], runtime_model: Any) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    from czr005.envs import IcsJunctionEnv  # pylint: disable=import-outside-toplevel

    env = IcsJunctionEnv(
        graph,
        tasks[:MAX_TASKS],
        max_decisions_per_task=128,
    )
    obs, info = env.reset(seed=43)
    trace: list[dict[str, Any]] = []
    route_sizes: dict[str, int] = {}
    terminated = False
    truncated = False
    steps = 0
    while not terminated:
        if steps >= MAX_TASKS * 128:
            truncated = True
            break
        task = obs["task"]
        candidates = list(obs["candidates"])
        task_decision_ordinal = env.task_decisions + 1
        action, proposed_position, fallback_used = _runtime_action(runtime_model, obs, info)
        next_obs, _, terminated, truncated_step, next_info = env.step(action)
        executed_index = next_info.get("executed_action")
        executed = _candidate_by_index(candidates, int(executed_index) if executed_index is not None else None)
        segment_id = str(task["segment_id"])
        route_size_before = route_sizes.setdefault(segment_id, 1)
        route_size_after = route_size_before + (1 if executed is not None and executed["kind"] == "move" else 0)
        route_sizes[segment_id] = route_size_after
        trace.append(
            {
                "decision_ordinal": steps + 1,
                "task_decision_ordinal": task_decision_ordinal,
                "event": str(next_info.get("event", "step")),
                "terminal_reason": str(next_info.get("reason", "")),
                "task_index": int(info["task_index"]),
                "segment_id": segment_id,
                "task_id": int(task["task_id"]),
                "current": int(task["current"]),
                "goal": int(task["goal"]),
                "ready_time": float(task["ready_time"]),
                "waiting_time": float(task["waiting_time"]),
                "proposed_position": proposed_position,
                "executed_index": int(executed_index) if executed_index is not None else -1,
                "executed_next": int(executed["next_node"]) if executed is not None else int(task["current"]),
                "executed_kind": str(executed["kind"]) if executed is not None else "none",
                "executed_safe": bool(executed["safe"]) if executed is not None else False,
                "unsafe_proposal": bool(next_info.get("unsafe_proposal", False)),
                "fallback_used": bool(fallback_used or next_info.get("shield_blocked", False)),
                "reached_goal": bool(next_info.get("reached_goal", False)),
                "candidate_count": len(candidates),
                "safe_candidate_count": sum(1 for candidate in candidates if bool(candidate["safe"])),
                "route_size_after": route_size_after,
            }
        )
        steps += 1
        if truncated_step:
            truncated = True
            break
        obs, info = next_obs, next_info

    result = env.episode_result()
    summary = env.episode_summary()
    return (
        {
            "planned_count": result.metrics.planned_count,
            "unplanned_count": result.metrics.unplanned_count,
            "decision_count": steps,
            "mean_travel_time": result.metrics.mean_travel_time,
            "post_shield_conflicts": int(summary["post_shield_conflicts"]),
            "truncated": truncated,
        },
        trace,
        truncated,
    )


def _values_match(field: str, python_value: Any, cpp_value: Any) -> bool:
    if field == "ready_time":
        return abs(float(python_value) - float(cpp_value)) <= FLOAT_TOLERANCE
    return python_value == cpp_value


def _first_mismatch(python_trace: list[dict[str, Any]], cpp_trace: list[dict[str, Any]]) -> dict[str, Any]:
    shared = min(len(python_trace), len(cpp_trace))
    for index in range(shared):
        python_row = python_trace[index]
        cpp_row = cpp_trace[index]
        for field in COMPARE_FIELDS:
            if not _values_match(field, python_row[field], cpp_row[field]):
                return {
                    "status": "mismatch",
                    "decision_ordinal": index + 1,
                    "field": field,
                    "python_value": python_row[field],
                    "cpp_value": cpp_row[field],
                    "python_task_id": python_row["task_id"],
                    "cpp_task_id": cpp_row["task_id"],
                    "python_segment_id": python_row["segment_id"],
                    "cpp_segment_id": cpp_row["segment_id"],
                }
    if len(python_trace) != len(cpp_trace):
        return {
            "status": "length_mismatch",
            "decision_ordinal": shared + 1,
            "field": "trace_length",
            "python_value": len(python_trace),
            "cpp_value": len(cpp_trace),
            "python_task_id": python_trace[shared - 1]["task_id"] if shared else "",
            "cpp_task_id": cpp_trace[shared - 1]["task_id"] if shared else "",
            "python_segment_id": python_trace[shared - 1]["segment_id"] if shared else "",
            "cpp_segment_id": cpp_trace[shared - 1]["segment_id"] if shared else "",
        }
    return {
        "status": "match",
        "decision_ordinal": "",
        "field": "none",
        "python_value": "",
        "cpp_value": "",
        "python_task_id": "",
        "cpp_task_id": "",
        "python_segment_id": "",
        "cpp_segment_id": "",
    }


def _context_rows(
    python_trace: list[dict[str, Any]],
    cpp_trace: list[dict[str, Any]],
    mismatch: dict[str, Any],
) -> list[dict[str, Any]]:
    if mismatch["decision_ordinal"] == "":
        center = min(len(python_trace), len(cpp_trace), 1)
    else:
        center = int(mismatch["decision_ordinal"])
    start = max(1, center - 3)
    end = min(max(len(python_trace), len(cpp_trace)), center + 3)
    rows: list[dict[str, Any]] = []
    for decision_ordinal in range(start, end + 1):
        index = decision_ordinal - 1
        for source, trace in (("python", python_trace), ("cpp", cpp_trace)):
            if index >= len(trace):
                continue
            row = trace[index]
            rows.append(
                {
                    "source": source,
                    "decision_ordinal": row["decision_ordinal"],
                    "task_decision_ordinal": row["task_decision_ordinal"],
                    "event": row["event"],
                    "terminal_reason": row["terminal_reason"],
                    "task_index": row["task_index"],
                    "segment_id": row["segment_id"],
                    "task_id": row["task_id"],
                    "current": row["current"],
                    "goal": row["goal"],
                    "ready_time": row["ready_time"],
                    "waiting_time": row["waiting_time"],
                    "proposed_position": row["proposed_position"],
                    "executed_index": row["executed_index"],
                    "executed_next": row["executed_next"],
                    "executed_kind": row["executed_kind"],
                    "unsafe_proposal": row["unsafe_proposal"],
                    "fallback_used": row["fallback_used"],
                    "reached_goal": row["reached_goal"],
                    "candidate_count": row["candidate_count"],
                    "safe_candidate_count": row["safe_candidate_count"],
                    "route_size_after": row["route_size_after"],
                }
            )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_report(
    python_summary: dict[str, Any],
    cpp_summary: dict[str, Any],
    mismatch: dict[str, Any],
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    safety_pass = (
        int(python_summary["post_shield_conflicts"]) == 0
        and int(cpp_summary["post_shield_conflicts"]) == 0
        and not bool(python_summary["truncated"])
    )
    trace_match = mismatch["status"] == "match"
    notes = (
        "The configured 24-task decision trace now matches exactly between Python and compact native C++ replay. This validates the previously mismatching unreachable-goal safety and unplanned-task cleanup semantics on this window."
        if trace_match
        else "This report narrows the larger-window mismatch from aggregate counts to a concrete decision-level comparison. It is intended to guide the next implementation step: aligning compact replay semantics or replacing them with the full C++ event scheduler."
    )
    lines = [
        "# Phase8 Native C++ Trace Diagnostic",
        "",
        "Date: 2026-06-17",
        "",
        "## Scope",
        "",
        f"This diagnostic compares Python and compact native C++ EdgeScore decision traces on the first `{MAX_TASKS}` same-map tasks. It verifies trace parity on this window and localizes the first divergence when parity does not hold.",
        "",
        "## Summary",
        "",
        "| Runtime | Planned | Unplanned | Decisions | Mean travel | Conflicts | Truncated |",
        "|---|---:|---:|---:|---:|---:|---|",
        "| Python | {planned_count} | {unplanned_count} | {decision_count} | {mean_travel_time:.6f} | {post_shield_conflicts} | {truncated} |".format(**python_summary),
        "| C++ compact replay | {planned_count} | {unplanned_count} | {decision_count} | {mean_travel_time:.6f} | {post_shield_conflicts} | False |".format(**cpp_summary),
        "",
        "## First Divergence",
        "",
        "| Status | Decision | Field | Python | C++ | Python task | C++ task |",
        "|---|---:|---|---|---|---|---|",
        "| {status} | {decision_ordinal} | {field} | {python_value} | {cpp_value} | {python_task_id} / {python_segment_id} | {cpp_task_id} / {cpp_segment_id} |".format(**mismatch),
        "",
        f"First mismatch CSV: `{FIRST_MISMATCH_TABLE_PATH.relative_to(ROOT).as_posix()}`",
        f"Trace context CSV: `{CONTEXT_TABLE_PATH.relative_to(ROOT).as_posix()}`",
        "",
        "## Gate Status",
        "",
        "- trace diagnostic safety: PASS" if safety_pass else "- trace diagnostic safety: FAIL",
        "- 24-task decision trace parity: PASS" if trace_match else "- 24-task decision trace parity: FAIL",
        "- full high-throughput event-scheduler parity: not covered",
        "",
        "## Notes",
        "",
        notes,
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(ROOT / "data" / "processed" / "maps" / "map2.json")
    tasks = tuple(TaskStream.from_jsonl(ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"))
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))

    python_summary, python_trace, truncated = _python_runtime_trace(graph, tasks, runtime_model)
    cpp_payload = czr005_cpp.edge_score_native_replay_trace(
        str(LEGACY / "map2.txt"),
        str(LEGACY / "inputdata.txt"),
        str(MODEL_PATH),
        max_tasks=MAX_TASKS,
        fault_edges=[],
        max_decisions_per_task=128,
    )
    cpp_summary = dict(cpp_payload["summary"])
    cpp_summary["truncated"] = False
    cpp_trace = [dict(row) for row in cpp_payload["trace"]]

    mismatch = _first_mismatch(python_trace, cpp_trace)
    context_rows = _context_rows(python_trace, cpp_trace, mismatch)
    _write_csv(FIRST_MISMATCH_TABLE_PATH, [mismatch])
    _write_csv(CONTEXT_TABLE_PATH, context_rows)
    _write_report(python_summary, cpp_summary, mismatch)

    if truncated:
        raise AssertionError("Python trace diagnostic truncated")
    if int(python_summary["post_shield_conflicts"]) != 0 or int(cpp_summary["post_shield_conflicts"]) != 0:
        raise AssertionError("trace diagnostic produced post-shield conflicts")
    if not python_trace or not cpp_trace:
        raise AssertionError("trace diagnostic produced an empty trace")

    print(
        "phase8_native_cpp_trace window={} status={} decision={} field={}".format(
            MAX_TASKS,
            mismatch["status"],
            mismatch["decision_ordinal"],
            mismatch["field"],
        )
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
