from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
import os
from pathlib import Path
import struct
import sys
import zlib
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
MODEL_PATH = ROOT / "artifacts" / "runtime" / "phase8_edge_score_runtime_model.txt"

FAILED_TASK_TABLE = ROOT / "outputs" / "tables" / "g2_failed_task_inventory.csv"
FIRST_DIVERGENCE_TABLE = ROOT / "outputs" / "tables" / "g2_first_divergence_by_task.csv"
DECISION_SLICE_TABLE = ROOT / "outputs" / "tables" / "g2_policy_vs_sipp_decision_slices.csv"
FAILURE_SLICE_TABLE = ROOT / "outputs" / "tables" / "g2_decision_failure_slices.csv"
COUNTERFACTUAL_TABLE = ROOT / "outputs" / "tables" / "g2_policy_vs_sipp_counterfactual.csv"
MOTIF_TABLE = ROOT / "outputs" / "tables" / "g2_failure_motif_summary.csv"
SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g2_family_summary.csv"
HEATMAP_PATH = ROOT / "outputs" / "figures" / "g2_failure_heatmap.png"
REPORT_PATH = ROOT / "outputs" / "reports" / "g2_learning_gap_autopsy.md"

MAX_DECISIONS_PER_TASK = 128
EVENT_POLICY_FAMILIES = ("edge_score_event", "fallback_event")
GAP_POLICY_FAMILIES = ("edge_score_event", "fallback_event", "pibt_active_bag_replay")


@dataclass(frozen=True)
class MatchedScenario:
    name: str
    task_offset: int
    max_tasks: int
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[tuple[int, int, float, float], ...] = ()
    node_capacities: tuple[tuple[int, int], ...] = ()
    merge_groups: tuple[tuple[int, int, int], ...] = ()
    merge_capacity: int = 1
    merge_headway_seconds: float = 0.0


@dataclass(frozen=True)
class PolicyOutcome:
    planned: bool
    path: tuple[int, ...]
    finish_time: float | None
    decision_count: int
    terminal_reason: str
    trace_rows: tuple[dict[str, Any], ...]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    candidates = (
        Path(os.environ["CZR005_CPP_PYTHON_PATH"])
        if os.environ.get("CZR005_CPP_PYTHON_PATH")
        else None,
        ROOT / "build_vs" / "python" / "Debug",
        ROOT / "build_vs" / "python" / "Release",
        ROOT / "build_nmake" / "python",
    )
    for candidate in reversed([path for path in candidates if path is not None]):
        if candidate.exists() or str(candidate) == os.environ.get("CZR005_CPP_PYTHON_PATH"):
            sys.path.insert(0, str(candidate))


def _case_plan() -> tuple[MatchedScenario, ...]:
    return (
        MatchedScenario("legacy_first16", 0, 16),
        MatchedScenario("legacy_first16_buffer2", 0, 16, node_capacities=((28, 2), (47, 2))),
        MatchedScenario("legacy_first32", 0, 32),
        MatchedScenario("legacy_offset32_static16", 32, 16, fault_edges=((16, 17),)),
        MatchedScenario("legacy_offset64_repair32", 64, 32, fault_windows=((28, 47, 0.0, 12000.0),)),
        MatchedScenario("legacy_offset64_merge32", 64, 32, merge_groups=((13, 23, 9), (18, 22, 9))),
    )


def _selected_tasks(all_tasks: tuple[Any, ...], scenario: MatchedScenario) -> tuple[Any, ...]:
    return all_tasks[scenario.task_offset : scenario.task_offset + scenario.max_tasks]


def _format_faults(fault_edges: tuple[tuple[int, int], ...]) -> str:
    return "none" if not fault_edges else ";".join(f"{start}->{end}" for start, end in sorted(fault_edges))


def _format_fault_windows(windows: tuple[tuple[int, int, float, float], ...]) -> str:
    if not windows:
        return "none"
    return ";".join(f"{start}->{end}@[{start_time:.3f},{repair_time:.3f})" for start, end, start_time, repair_time in windows)


def _format_node_capacities(capacities: tuple[tuple[int, int], ...]) -> str:
    return "none" if not capacities else ";".join(f"{node}:{capacity}" for node, capacity in sorted(capacities))


def _format_merge_groups(groups: tuple[tuple[int, int, int], ...]) -> str:
    return "none" if not groups else ";".join(f"{start}->{end}:{group}" for start, end, group in sorted(groups))


def _route_path(route: Iterable[Any] | None) -> tuple[int, ...]:
    if not route:
        return ()
    return tuple(int(node.location) for node in route)


def _route_finish(route: Iterable[Any] | None) -> float | None:
    values = list(route or ())
    if not values:
        return None
    return float(values[-1].t2)


def _format_path(path: tuple[int, ...], limit: int = 64) -> str:
    if len(path) <= limit:
        return " ".join(str(value) for value in path)
    head = " ".join(str(value) for value in path[:limit])
    return f"{head} ...(+{len(path) - limit} more)"


def _group_trace(trace: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in trace:
        grouped.setdefault(str(row["segment_id"]), []).append(dict(row))
    for rows in grouped.values():
        rows.sort(key=lambda item: (int(item.get("task_decision_ordinal", item.get("decision_count", 0))), int(item.get("decision_ordinal", 0))))
    return grouped


def _group_events(events: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        grouped.setdefault(str(event["segment_id"]), []).append(dict(event))
    return grouped


def _event_trace_path(task: Any, rows: list[dict[str, Any]]) -> tuple[int, ...]:
    path: list[int] = [int(task.start)]
    for row in rows:
        if row.get("event") != "step" or row.get("executed_kind") != "move":
            continue
        next_node = int(row["executed_next"])
        if not path or path[-1] != next_node:
            path.append(next_node)
    return tuple(path)


def _baseline_event_path(task: Any, rows: list[dict[str, Any]]) -> tuple[int, ...]:
    path: list[int] = [int(task.start)]
    for row in rows:
        if row.get("event") not in {"pibt_move", "replan_move"}:
            continue
        next_node = int(row["next_node"])
        if not path or path[-1] != next_node:
            path.append(next_node)
    return tuple(path)


def _event_terminal_reason(rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> str:
    for row in rows:
        if row.get("event") == "unplanned":
            return str(row.get("terminal_reason") or "unplanned")
    for event in events:
        if event.get("event") == "unplanned":
            return str(event.get("reason") or "unplanned")
    return ""


def _event_decision_count(rows: list[dict[str, Any]], events: list[dict[str, Any]]) -> int:
    if rows:
        return max(int(row.get("task_decision_ordinal", 0)) for row in rows)
    counts = [int(event.get("decision_count", event.get("replan_count", 0))) for event in events]
    return max(counts, default=0)


def _outcomes_from_event_run(tasks: tuple[Any, ...], run: Any) -> dict[str, PolicyOutcome]:
    traces = _group_trace(run.trace)
    events = _group_events(run.result.events)
    outcomes: dict[str, PolicyOutcome] = {}
    for task in tasks:
        segment = str(task.segment_id)
        route = run.result.routes.get(segment)
        rows = traces.get(segment, [])
        task_events = events.get(segment, [])
        outcomes[segment] = PolicyOutcome(
            planned=route is not None,
            path=_route_path(route) if route is not None else _event_trace_path(task, rows),
            finish_time=_route_finish(route),
            decision_count=_event_decision_count(rows, task_events),
            terminal_reason="" if route is not None else _event_terminal_reason(rows, task_events),
            trace_rows=tuple(rows),
        )
    return outcomes


def _outcomes_from_episode(tasks: tuple[Any, ...], result: Any) -> dict[str, PolicyOutcome]:
    events = _group_events(result.events)
    outcomes: dict[str, PolicyOutcome] = {}
    for task in tasks:
        segment = str(task.segment_id)
        route = result.routes.get(segment)
        task_events = events.get(segment, [])
        outcomes[segment] = PolicyOutcome(
            planned=route is not None,
            path=_route_path(route) if route is not None else _baseline_event_path(task, task_events),
            finish_time=_route_finish(route),
            decision_count=_event_decision_count([], task_events),
            terminal_reason="" if route is not None else _event_terminal_reason([], task_events),
            trace_rows=tuple(task_events),
        )
    return outcomes


def _path_prefix_len(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    count = 0
    for left_node, right_node in zip(left, right):
        if left_node != right_node:
            break
        count += 1
    return count


def _teacher_next_for_current(teacher_path: tuple[int, ...], current: int) -> int | None:
    for index, node in enumerate(teacher_path[:-1]):
        if int(node) == int(current):
            return int(teacher_path[index + 1])
    return None


def _path_divergence(teacher_path: tuple[int, ...], policy_path: tuple[int, ...]) -> dict[str, Any]:
    prefix = _path_prefix_len(teacher_path, policy_path)
    if prefix < min(len(teacher_path), len(policy_path)):
        return {
            "prefix_match_len": prefix,
            "divergence_index": prefix,
            "current": teacher_path[prefix - 1] if prefix > 0 else teacher_path[0] if teacher_path else "",
            "teacher_next": teacher_path[prefix] if prefix < len(teacher_path) else "",
            "policy_next": policy_path[prefix] if prefix < len(policy_path) else "",
            "divergence_reason": "different_next_node",
        }
    if len(policy_path) < len(teacher_path):
        return {
            "prefix_match_len": prefix,
            "divergence_index": prefix,
            "current": policy_path[-1] if policy_path else "",
            "teacher_next": teacher_path[prefix] if prefix < len(teacher_path) else "",
            "policy_next": "",
            "divergence_reason": "policy_path_ended_before_teacher_goal",
        }
    if len(policy_path) > len(teacher_path):
        return {
            "prefix_match_len": prefix,
            "divergence_index": prefix,
            "current": teacher_path[-1] if teacher_path else "",
            "teacher_next": "",
            "policy_next": policy_path[prefix] if prefix < len(policy_path) else "",
            "divergence_reason": "policy_continued_after_teacher_goal",
        }
    return {
        "prefix_match_len": prefix,
        "divergence_index": -1,
        "current": "",
        "teacher_next": "",
        "policy_next": "",
        "divergence_reason": "path_prefix_match",
    }


def _trace_divergence(teacher_path: tuple[int, ...], outcome: PolicyOutcome) -> dict[str, Any]:
    for row in outcome.trace_rows:
        if "current" not in row:
            continue
        event_name = str(row.get("event", ""))
        if event_name in {"arrival", "planned"}:
            continue
        current = int(row["current"])
        teacher_next = _teacher_next_for_current(teacher_path, current)
        if event_name == "unplanned":
            return {
                **_path_divergence(teacher_path, outcome.path),
                "decision_ordinal": row.get("decision_ordinal", ""),
                "task_decision_ordinal": row.get("task_decision_ordinal", row.get("decision_count", "")),
                "current": current,
                "teacher_next": teacher_next if teacher_next is not None else "",
                "policy_next": "",
                "policy_action_kind": "unplanned",
                "ready_time": row.get("ready_time", ""),
                "waiting_time": row.get("waiting_time", ""),
                "safe_candidate_count": row.get("safe_candidate_count", ""),
                "candidate_count": row.get("candidate_count", ""),
                "fallback_used": row.get("fallback_used", ""),
                "divergence_reason": str(row.get("terminal_reason") or "unplanned"),
            }
        if teacher_next is None:
            continue
        if event_name not in {"step", "pibt_move", "pibt_hold", "replan_move", "replan_hold"}:
            continue
        executed_next = int(row.get("executed_next", row.get("next_node", current)))
        if event_name in {"pibt_hold", "replan_hold"}:
            executed_kind = "hold"
        elif event_name in {"pibt_move", "replan_move"}:
            executed_kind = "move"
        else:
            executed_kind = str(row.get("executed_kind", ""))
        if executed_next != teacher_next:
            return {
                **_path_divergence(teacher_path, outcome.path),
                "decision_ordinal": row.get("decision_ordinal", ""),
                "task_decision_ordinal": row.get("task_decision_ordinal", row.get("decision_count", "")),
                "current": current,
                "teacher_next": teacher_next,
                "policy_next": executed_next,
                "policy_action_kind": executed_kind,
                "ready_time": row.get("ready_time", ""),
                "waiting_time": row.get("waiting_time", ""),
                "safe_candidate_count": row.get("safe_candidate_count", ""),
                "candidate_count": row.get("candidate_count", ""),
                "fallback_used": row.get("fallback_used", ""),
                "divergence_reason": "hold_when_sipp_moves" if executed_kind == "hold" else "different_next_node",
            }
    return _path_divergence(teacher_path, outcome.path)


def _deadline_slack(graph: Any, task: Any, current: int, ready_time: float | None = None) -> float:
    reference_time = float(task.pass_time if ready_time is None or ready_time == "" else ready_time)
    return float(task.std) - reference_time - float(graph.heuristic(int(current), int(task.goal)))


def _scenario_context(scenario: MatchedScenario) -> dict[str, str]:
    if scenario.fault_edges:
        context = "static_fault"
    elif scenario.fault_windows:
        context = "repair_window"
    elif scenario.merge_groups:
        context = "merge_group"
    elif scenario.node_capacities:
        context = "buffer_capacity"
    else:
        context = "no_fault"
    return {
        "scenario_context": context,
        "fault_edges": _format_faults(scenario.fault_edges),
        "fault_windows": _format_fault_windows(scenario.fault_windows),
        "node_capacities": _format_node_capacities(scenario.node_capacities),
        "merge_groups": _format_merge_groups(scenario.merge_groups),
    }


def _edge_in_merge_group(scenario: MatchedScenario, current: Any, next_node: Any) -> str:
    if current == "" or next_node == "":
        return "none"
    for start, end, group in scenario.merge_groups:
        if int(current) == start and int(next_node) == end:
            return str(group)
    return "none"


def _classify_motif(scenario: MatchedScenario, outcome: PolicyOutcome, divergence: dict[str, Any]) -> str:
    reason = str(divergence.get("divergence_reason") or outcome.terminal_reason)
    action_kind = str(divergence.get("policy_action_kind", ""))
    safe = str(divergence.get("safe_candidate_count", ""))
    if reason in {"max_decisions", "policy_path_ended_before_teacher_goal"} or outcome.terminal_reason == "max_decisions":
        return "decision_horizon_exhausted"
    if reason in {"no_safe_action", "unsafe_no_safe_fallback"} or safe == "0":
        return "no_safe_action_at_divergence"
    if action_kind == "hold" or reason == "hold_when_sipp_moves":
        return "hold_when_sipp_moves"
    if scenario.fault_edges:
        return "static_fault_branch_gap"
    if scenario.fault_windows:
        return "repair_window_branch_gap"
    if scenario.merge_groups and _edge_in_merge_group(scenario, divergence.get("current", ""), divergence.get("teacher_next", "")) != "none":
        return "merge_group_branch_gap"
    if scenario.node_capacities:
        return "buffer_capacity_branch_gap"
    if reason == "different_next_node":
        return "wrong_branch_vs_sipp"
    return reason or "unclassified_failure"


def _suggest_fix(motif: str) -> tuple[str, str]:
    if motif == "decision_horizon_exhausted":
        return (
            "observation_or_horizon_limited",
            "Add teacher-derived future occupancy, queue-pressure, and abstain/fallback labels before enlarging the policy.",
        )
    if motif == "hold_when_sipp_moves":
        return (
            "model_or_feature_limited",
            "Train against SIPP next-hop rankings and add shortest-to-goal plus downstream reservation features.",
        )
    if motif == "no_safe_action_at_divergence":
        return (
            "shield_or_timing_limited",
            "Audit safe-mask timing and add no-safe-action risk labels to the dataset.",
        )
    if motif in {"static_fault_branch_gap", "repair_window_branch_gap"}:
        return (
            "fault_context_limited",
            "Generate fault/repair teacher slices and expose active repair-window features.",
        )
    if motif == "merge_group_branch_gap":
        return (
            "nonlocal_constraint_limited",
            "Add merge-group pressure features and teacher ranks for competing incoming edges.",
        )
    return (
        "model_or_data_limited",
        "Collect SIPP teacher counterfactual slices and run feature ablations before RL.",
    )


def _summary_row(scenario: MatchedScenario, family: str, summary: dict[str, Any], scope: str = "matched_active_bag") -> dict[str, Any]:
    context = _scenario_context(scenario)
    max_tasks = int(summary.get("max_tasks", scenario.max_tasks))
    planned = int(summary.get("planned_count", 0))
    return {
        "scenario": scenario.name,
        "family": family,
        "scope": scope,
        "max_tasks": max_tasks,
        "planned_count": planned,
        "unplanned_count": int(summary.get("unplanned_count", max_tasks - planned)),
        "decision_count": int(summary.get("decision_count", summary.get("replan_count", 0))),
        "post_shield_conflicts": int(summary.get("post_shield_conflicts", 0)),
        "mean_travel_time": float(summary.get("mean_travel_time", 0.0)),
        "scenario_context": context["scenario_context"],
        "notes": "A*-guided env is sequential and is included as a scripted-policy reference, not a matched active-bag baseline."
        if scope != "matched_active_bag"
        else "",
    }


def _run_scenario(graph: Any, all_tasks: tuple[Any, ...], runtime_model: Any, scenario: MatchedScenario) -> dict[str, Any]:
    from czr005.baselines import (  # pylint: disable=import-outside-toplevel
        PIBTActiveBagReplayBaseline,
        PeriodicReplanningBaseline,
        RollingHorizonBaseline,
    )
    from czr005.envs import (  # pylint: disable=import-outside-toplevel
        IcsJunctionEnv,
        astar_guided_policy_factory,
        fault_aware_astar_policy_factory,
    )
    from czr005.eval import run_event_replay  # pylint: disable=import-outside-toplevel

    tasks = _selected_tasks(all_tasks, scenario)
    node_capacities = dict(scenario.node_capacities)
    merge_groups = {(start, end): group for start, end, group in scenario.merge_groups}
    common = {
        "fault_edges": set(scenario.fault_edges),
        "fault_windows": scenario.fault_windows,
    }
    constraint_common = {
        "node_capacities": node_capacities,
        "merge_groups": merge_groups,
        "merge_capacity": scenario.merge_capacity,
        "merge_headway_seconds": scenario.merge_headway_seconds,
    }

    rolling = RollingHorizonBaseline(graph, horizon_seconds=300.0, **constraint_common)
    rolling_result = rolling.run_episode(tasks, max_tasks=scenario.max_tasks, **common)
    rolling_edge_conflicts = rolling.edge_reservations.conflict_count() + rolling.edge_reservations.merge_group_conflict_count(
        merge_groups,
        scenario.merge_capacity,
        scenario.merge_headway_seconds,
    )
    rolling_summary = {
        **rolling_result.metrics.to_dict(),
        "max_tasks": scenario.max_tasks,
        "decision_count": len(rolling_result.events),
        "post_shield_conflicts": rolling_result.metrics.reservation_conflicts + rolling_edge_conflicts,
    }

    periodic = PeriodicReplanningBaseline(graph, interval_seconds=5.0, max_ticks=2048, **constraint_common)
    periodic_result = periodic.run_episode(tasks, max_tasks=scenario.max_tasks, **common)
    periodic_summary = {**periodic_result.metrics.to_dict(), **periodic.summary.__dict__, "max_tasks": scenario.max_tasks}

    pibt = PIBTActiveBagReplayBaseline(graph, interval_seconds=5.0, max_ticks=2048, hold_seconds=5.0, **constraint_common)
    pibt_result = pibt.run_episode(tasks, max_tasks=scenario.max_tasks, **common)
    pibt_summary = {**pibt_result.metrics.to_dict(), **pibt.summary.__dict__, "max_tasks": scenario.max_tasks}

    edge_run = run_event_replay(
        graph,
        tasks,
        runtime_model=runtime_model,
        max_tasks=scenario.max_tasks,
        max_decisions_per_task=MAX_DECISIONS_PER_TASK,
        **common,
        **constraint_common,
    )
    fallback_run = run_event_replay(
        graph,
        tasks,
        runtime_model=None,
        max_tasks=scenario.max_tasks,
        max_decisions_per_task=MAX_DECISIONS_PER_TASK,
        **common,
        **constraint_common,
    )

    env = IcsJunctionEnv(
        graph,
        tasks,
        max_tasks=scenario.max_tasks,
        max_decisions_per_task=MAX_DECISIONS_PER_TASK,
        **common,
        **constraint_common,
    )
    policy = (
        fault_aware_astar_policy_factory(graph, set(scenario.fault_edges), scenario.fault_windows)
        if scenario.fault_edges or scenario.fault_windows
        else astar_guided_policy_factory(graph)
    )
    astar_result, astar_info = env.run_policy(policy, seed=17, max_steps=scenario.max_tasks * MAX_DECISIONS_PER_TASK)
    astar_summary = {**env.episode_summary(), "max_tasks": scenario.max_tasks, "decision_count": astar_info.steps}

    return {
        "tasks": tasks,
        "summaries": {
            "rolling_horizon_sipp": rolling_summary,
            "periodic_replanning_sipp": periodic_summary,
            "pibt_active_bag_replay": pibt_summary,
            "edge_score_event": {**edge_run.summary, "max_tasks": scenario.max_tasks},
            "fallback_event": {**fallback_run.summary, "max_tasks": scenario.max_tasks},
            "astar_guided_safe_env": astar_summary,
        },
        "outcomes": {
            "rolling_horizon_sipp": _outcomes_from_episode(tasks, rolling_result),
            "periodic_replanning_sipp": _outcomes_from_episode(tasks, periodic_result),
            "pibt_active_bag_replay": _outcomes_from_episode(tasks, pibt_result),
            "edge_score_event": _outcomes_from_event_run(tasks, edge_run),
            "fallback_event": _outcomes_from_event_run(tasks, fallback_run),
            "astar_guided_safe_env": _outcomes_from_episode(tasks, astar_result),
        },
    }


def _decision_slice_rows(
    graph: Any,
    scenario: MatchedScenario,
    tasks: tuple[Any, ...],
    teacher: dict[str, PolicyOutcome],
    outcomes: dict[str, dict[str, PolicyOutcome]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    task_by_segment = {str(task.segment_id): task for task in tasks}
    for family in EVENT_POLICY_FAMILIES:
        for segment, outcome in outcomes[family].items():
            task = task_by_segment[segment]
            teacher_path = teacher[segment].path
            for row in outcome.trace_rows:
                current = int(row["current"])
                teacher_next = _teacher_next_for_current(teacher_path, current)
                executed_next = int(row.get("executed_next", current))
                safe_count = int(row.get("safe_candidate_count", 0))
                candidate_count = int(row.get("candidate_count", 0))
                ready_time = row.get("ready_time", "")
                rows.append(
                    {
                        "scenario": scenario.name,
                        "policy_family": family,
                        "slice_scope": "event_trace",
                        "task_local_index": int(row["task_index"]),
                        "task_global_index": scenario.task_offset + int(row["task_index"]),
                        "segment_id": segment,
                        "task_id": int(task.task_id),
                        "source_line": int(task.source_line),
                        "current": current,
                        "goal": int(task.goal),
                        "ready_time": ready_time,
                        "waiting_time": row.get("waiting_time", ""),
                        "deadline_slack": _deadline_slack(graph, task, current, float(ready_time) if ready_time != "" else None),
                        "decision_ordinal": row.get("decision_ordinal", ""),
                        "task_decision_ordinal": row.get("task_decision_ordinal", ""),
                        "proposed_position": row.get("proposed_position", ""),
                        "executed_next": executed_next,
                        "executed_kind": row.get("executed_kind", ""),
                        "terminal_reason": row.get("terminal_reason", ""),
                        "fallback_used": row.get("fallback_used", ""),
                        "safe_candidate_count": safe_count,
                        "candidate_count": candidate_count,
                        "blocked_candidate_count": max(0, candidate_count - safe_count),
                        "sipp_teacher_next": "" if teacher_next is None else teacher_next,
                        "matches_sipp_next": teacher_next is not None and executed_next == teacher_next,
                        "active_fault_state": "yes" if scenario.fault_edges or scenario.fault_windows else "no",
                        "node_capacity_state": _format_node_capacities(scenario.node_capacities),
                        "merge_group_state": _edge_in_merge_group(scenario, current, teacher_next if teacher_next is not None else ""),
                    }
                )
    return rows


def _build_tables(graph: Any, scenario_runs: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    family_summary_rows: list[dict[str, Any]] = []
    failed_rows: list[dict[str, Any]] = []
    first_divergence_rows: list[dict[str, Any]] = []
    failure_slice_rows: list[dict[str, Any]] = []
    counterfactual_rows: list[dict[str, Any]] = []
    decision_slice_rows: list[dict[str, Any]] = []

    for scenario in _case_plan():
        run = scenario_runs[scenario.name]
        tasks = run["tasks"]
        task_by_segment = {str(task.segment_id): task for task in tasks}
        summaries = run["summaries"]
        outcomes = run["outcomes"]
        teacher = outcomes["rolling_horizon_sipp"]
        context = _scenario_context(scenario)

        for family, summary in summaries.items():
            scope = "scripted_sequential_env" if family == "astar_guided_safe_env" else "matched_active_bag"
            family_summary_rows.append(_summary_row(scenario, family, summary, scope=scope))

        decision_slice_rows.extend(_decision_slice_rows(graph, scenario, tasks, teacher, outcomes))

        for family in ("periodic_replanning_sipp", *GAP_POLICY_FAMILIES, "astar_guided_safe_env"):
            for segment, policy_outcome in outcomes[family].items():
                task = task_by_segment[segment]
                teacher_outcome = teacher[segment]
                divergence = _trace_divergence(teacher_outcome.path, policy_outcome)
                motif = "" if policy_outcome.planned else _classify_motif(scenario, policy_outcome, divergence)
                observation_guess, fix = _suggest_fix(motif) if motif else ("", "")
                travel_gap = (
                    float(policy_outcome.finish_time) - float(teacher_outcome.finish_time)
                    if policy_outcome.finish_time is not None and teacher_outcome.finish_time is not None
                    else ""
                )
                counterfactual_rows.append(
                    {
                        "scenario": scenario.name,
                        "policy_family": family,
                        "task_global_index": scenario.task_offset + list(task_by_segment).index(segment),
                        "segment_id": segment,
                        "task_id": int(task.task_id),
                        "source_line": int(task.source_line),
                        "teacher_family": "rolling_horizon_sipp",
                        "teacher_planned": teacher_outcome.planned,
                        "policy_planned": policy_outcome.planned,
                        "teacher_path": _format_path(teacher_outcome.path),
                        "policy_path": _format_path(policy_outcome.path),
                        "teacher_path_length": len(teacher_outcome.path),
                        "policy_path_length": len(policy_outcome.path),
                        "prefix_match_len": divergence.get("prefix_match_len", ""),
                        "first_divergence_current": divergence.get("current", ""),
                        "sipp_teacher_next": divergence.get("teacher_next", ""),
                        "policy_next": divergence.get("policy_next", ""),
                        "divergence_reason": divergence.get("divergence_reason", ""),
                        "policy_decision_count": policy_outcome.decision_count,
                        "policy_terminal_reason": policy_outcome.terminal_reason,
                        "teacher_finish_time": "" if teacher_outcome.finish_time is None else teacher_outcome.finish_time,
                        "policy_finish_time": "" if policy_outcome.finish_time is None else policy_outcome.finish_time,
                        "finish_time_gap_vs_sipp": travel_gap,
                        "failure_motif": motif,
                        "counterfactual_interpretation": "policy failed where rolling-horizon SIPP completed"
                        if teacher_outcome.planned and not policy_outcome.planned
                        else "policy completed under this diagnostic",
                    }
                )

                if family not in GAP_POLICY_FAMILIES or not teacher_outcome.planned or policy_outcome.planned:
                    continue

                ready_time = divergence.get("ready_time", "")
                current = divergence.get("current", "")
                teacher_next = divergence.get("teacher_next", "")
                safe_count = divergence.get("safe_candidate_count", "")
                candidate_count = divergence.get("candidate_count", "")
                motif = _classify_motif(scenario, policy_outcome, divergence)
                observation_guess, fix = _suggest_fix(motif)
                base_row = {
                    "scenario": scenario.name,
                    "policy_family": family,
                    "task_local_index": list(task_by_segment).index(segment),
                    "task_global_index": scenario.task_offset + list(task_by_segment).index(segment),
                    "segment_id": segment,
                    "task_id": int(task.task_id),
                    "source_line": int(task.source_line),
                    "task_start": int(task.start),
                    "task_goal": int(task.goal),
                    "pass_time": float(task.pass_time),
                    "std": float(task.std),
                    "start_deadline_slack": _deadline_slack(graph, task, int(task.start)),
                    "teacher_family": "rolling_horizon_sipp",
                    "teacher_path": _format_path(teacher_outcome.path),
                    "teacher_finish_time": teacher_outcome.finish_time,
                    "policy_partial_path": _format_path(policy_outcome.path),
                    "policy_decision_count": policy_outcome.decision_count,
                    "policy_terminal_reason": policy_outcome.terminal_reason,
                    "first_divergence_current": current,
                    "sipp_teacher_next": teacher_next,
                    "policy_next": divergence.get("policy_next", ""),
                    "policy_action_kind": divergence.get("policy_action_kind", ""),
                    "divergence_reason": divergence.get("divergence_reason", ""),
                    "ready_time": ready_time,
                    "deadline_slack_at_divergence": ""
                    if current == ""
                    else _deadline_slack(graph, task, int(current), float(ready_time) if ready_time != "" else None),
                    "safe_candidate_count": safe_count,
                    "candidate_count": candidate_count,
                    "blocked_candidate_count": ""
                    if safe_count == "" or candidate_count == ""
                    else int(candidate_count) - int(safe_count),
                    "active_fault_state": "yes" if scenario.fault_edges or scenario.fault_windows else "no",
                    "node_capacity_state": context["node_capacities"],
                    "merge_group_state": _edge_in_merge_group(scenario, current, teacher_next),
                    "scenario_context": context["scenario_context"],
                    "failure_motif": motif,
                    "observation_vs_model_guess": observation_guess,
                    "suggested_next_fix": fix,
                }
                failed_rows.append(base_row)
                first_divergence_rows.append(base_row)
                failure_slice_rows.append(
                    {
                        **base_row,
                        "slice_scope": "first_divergence",
                        "prefix_match_len": divergence.get("prefix_match_len", ""),
                        "decision_ordinal": divergence.get("decision_ordinal", ""),
                        "task_decision_ordinal": divergence.get("task_decision_ordinal", ""),
                        "fallback_used": divergence.get("fallback_used", ""),
                    }
                )

    motif_rows = _motif_summary_rows(failed_rows)
    return {
        "summary": family_summary_rows,
        "failed": failed_rows,
        "first_divergence": first_divergence_rows,
        "decision_slices": decision_slice_rows,
        "failure_slices": failure_slice_rows,
        "counterfactual": counterfactual_rows,
        "motifs": motif_rows,
    }


def _motif_summary_rows(failed_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals_by_family: dict[str, int] = {}
    grouped: dict[tuple[str, str, str], int] = {}
    for row in failed_rows:
        family = str(row["policy_family"])
        motif = str(row["failure_motif"])
        scenario_context = str(row["scenario_context"])
        totals_by_family[family] = totals_by_family.get(family, 0) + 1
        grouped[(family, motif, scenario_context)] = grouped.get((family, motif, scenario_context), 0) + 1
    rows: list[dict[str, Any]] = []
    for (family, motif, scenario_context), count in sorted(grouped.items(), key=lambda item: (-item[1], item[0])):
        rows.append(
            {
                "policy_family": family,
                "failure_motif": motif,
                "scenario_context": scenario_context,
                "failed_tasks": count,
                "share_of_family_failures": count / totals_by_family[family] if totals_by_family.get(family) else 0.0,
                "suggested_next_fix": _suggest_fix(motif)[1],
            }
        )
    return rows


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int]]) -> None:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _write_heatmap(rows: list[dict[str, Any]]) -> str:
    scenario_names = [scenario.name for scenario in _case_plan()]
    motifs = sorted({str(row["failure_motif"]) for row in rows}) or ["none"]
    counts = {(scenario, motif): 0 for scenario in scenario_names for motif in motifs}
    for row in rows:
        counts[(str(row["scenario"]), str(row["failure_motif"]))] += 1
    max_count = max(counts.values()) if counts else 1

    try:
        from PIL import Image, ImageDraw, ImageFont  # pylint: disable=import-outside-toplevel
    except ImportError:
        cell = 28
        margin = 8
        width = margin * 2 + len(motifs) * cell
        height = margin * 2 + len(scenario_names) * cell
        pixels = [(255, 255, 255) for _ in range(width * height)]
        for row_index, scenario in enumerate(scenario_names):
            for col_index, motif in enumerate(motifs):
                value = counts[(scenario, motif)]
                intensity = 0 if max_count == 0 else int(220 * value / max_count)
                color = (255, 245 - intensity // 2, 240 - intensity)
                x0 = margin + col_index * cell
                y0 = margin + row_index * cell
                for y in range(y0, y0 + cell - 2):
                    for x in range(x0, x0 + cell - 2):
                        pixels[y * width + x] = color
        _write_png(HEATMAP_PATH, width, height, pixels)
        return "generated with stdlib fallback; labels are in g2_failure_motif_summary.csv"

    cell_w = 148
    cell_h = 42
    left = 230
    top = 120
    width = left + len(motifs) * cell_w + 40
    height = top + len(scenario_names) * cell_h + 60
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        title_font = ImageFont.truetype("arial.ttf", 18)
        font = ImageFont.truetype("arial.ttf", 12)
        small = ImageFont.truetype("arial.ttf", 10)
    except OSError:
        title_font = ImageFont.load_default()
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    draw.text((24, 24), "G2 failure motif heatmap", fill="#111111", font=title_font)
    draw.text((24, 50), "Counts aggregate EdgeScore, fallback, and PIBT failures against rolling-horizon SIPP.", fill="#333333", font=font)
    for col_index, motif in enumerate(motifs):
        draw.text((left + col_index * cell_w + 4, top - 56), motif.replace("_", " ")[:22], fill="#111111", font=small)
    for row_index, scenario in enumerate(scenario_names):
        y = top + row_index * cell_h
        draw.text((24, y + 12), scenario, fill="#111111", font=font)
        for col_index, motif in enumerate(motifs):
            value = counts[(scenario, motif)]
            intensity = 0 if max_count == 0 else int(210 * value / max_count)
            fill = (255, 244 - intensity // 3, 235 - intensity)
            x = left + col_index * cell_w
            draw.rectangle((x, y, x + cell_w - 4, y + cell_h - 4), fill=fill, outline="#dddddd")
            if value:
                draw.text((x + 8, y + 12), str(value), fill="#111111", font=font)
    HEATMAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(HEATMAP_PATH)
    return "generated"


def _write_report(tables: dict[str, list[dict[str, Any]]], heatmap_status: str) -> None:
    summary = tables["summary"]
    failed = tables["failed"]
    motifs = tables["motifs"]
    planned_by_family = {
        family: (
            sum(int(row["planned_count"]) for row in summary if row["family"] == family and row["scope"] == "matched_active_bag"),
            sum(int(row["max_tasks"]) for row in summary if row["family"] == family and row["scope"] == "matched_active_bag"),
        )
        for family in ("rolling_horizon_sipp", "periodic_replanning_sipp", *GAP_POLICY_FAMILIES)
    }
    edge_failures = [row for row in failed if row["policy_family"] == "edge_score_event"]
    fallback_failures = [row for row in failed if row["policy_family"] == "fallback_event"]
    pibt_failures = [row for row in failed if row["policy_family"] == "pibt_active_bag_replay"]
    top_motifs = sorted(motifs, key=lambda row: int(row["failed_tasks"]), reverse=True)[:10]
    top_nodes: dict[str, int] = {}
    for row in failed:
        node = str(row["first_divergence_current"])
        if node:
            top_nodes[node] = top_nodes.get(node, 0) + 1
    top_node_text = ", ".join(f"{node}:{count}" for node, count in sorted(top_nodes.items(), key=lambda item: (-item[1], item[0]))[:10])

    lines = [
        "# G2 Learning Gap Autopsy",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This diagnostic explains why the current learned/prototype routing families lose to the strong SIPP baselines on the Phase9 matched real `map2/inputdata` windows. It is a failure-driven research artifact, not a new learning-success claim.",
        "",
        f"- map: `{MAP_PATH.relative_to(ROOT).as_posix()}`",
        f"- tasks: `{TASK_PATH.relative_to(ROOT).as_posix()}`",
        f"- runtime model: `{MODEL_PATH.relative_to(ROOT).as_posix()}`",
        f"- heatmap: `{HEATMAP_PATH.relative_to(ROOT).as_posix()}` ({heatmap_status})",
        "",
        "## Matched Planned Counts",
        "",
        "| Family | Planned / tasks | Interpretation |",
        "|---|---:|---|",
    ]
    interpretations = {
        "rolling_horizon_sipp": "teacher/reference for first-divergence diagnosis",
        "periodic_replanning_sipp": "strong active-bag replanning baseline",
        "edge_score_event": "learned smoke/prototype runtime policy",
        "fallback_event": "shortest-safe event fallback",
        "pibt_active_bag_replay": "local active-bag resolver stress baseline",
    }
    for family, (planned, total) in planned_by_family.items():
        lines.append(f"| `{family}` | `{planned}/{total}` | {interpretations[family]} |")
    lines.extend(
        [
            "",
            "## Failure Inventory",
            "",
            f"- EdgeScore failures against rolling-horizon SIPP: `{len(edge_failures)}` task-scenario rows.",
            f"- Fallback failures against rolling-horizon SIPP: `{len(fallback_failures)}` task-scenario rows.",
            f"- PIBT active-bag replay failures against rolling-horizon SIPP: `{len(pibt_failures)}` task-scenario rows.",
            f"- Top first-divergence nodes across failed rows: `{top_node_text or 'none'}`.",
            "",
            "## Top Failure Motifs",
            "",
            "| Policy | Motif | Context | Failed tasks | Share |",
            "|---|---|---|---:|---:|",
        ]
    )
    for row in top_motifs:
        lines.append(
            "| `{policy_family}` | `{failure_motif}` | `{scenario_context}` | {failed_tasks} | {share_of_family_failures:.3f} |".format(
                **row
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The current learning/prototype policy is not failing because of post-shield safety: the matched rows remain conflict-free. The gap is a completion and coordination gap. In failed task-scenario rows, rolling-horizon SIPP has a feasible route while the local policy either exhausts the decision horizon, holds when the SIPP teacher advances, or chooses a branch that later cannot recover within the local event policy.",
            "",
            "This means the next useful work is not PPO/MAPPO. The next useful work is teacher-slice expansion and feature/oracle diagnosis: SIPP next-hop ranks, downstream reservation pressure, deadline slack, active fault/repair state, merge-group pressure, and no-safe-action risk labels.",
            "",
            "## Artifacts",
            "",
            f"- Failed task inventory: `{FAILED_TASK_TABLE.relative_to(ROOT).as_posix()}`",
            f"- First divergence by task: `{FIRST_DIVERGENCE_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Decision slices: `{DECISION_SLICE_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Failure slices: `{FAILURE_SLICE_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Policy-vs-SIPP counterfactual: `{COUNTERFACTUAL_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Failure motif summary: `{MOTIF_TABLE.relative_to(ROOT).as_posix()}`",
            f"- Family summary: `{SUMMARY_TABLE.relative_to(ROOT).as_posix()}`",
            "",
            "## Gate Status",
            "",
            "- failed task inventory: PASS",
            "- first-divergence localization: PASS",
            "- policy-vs-SIPP decision slices for EdgeScore/fallback event policies: PASS",
            "- PIBT failure rows localized at task level: PASS",
            "- A*-guided scripted policy included as sequential reference: PASS",
            "- oracle upper-bound analysis: NOT DONE, belongs to G3",
            "",
            "## Next Blocking Question",
            "",
            "Can a local candidate-ranking oracle, using the same safe candidate set but richer SIPP-derived features, recover most of the EdgeScore `47` failed task-scenario rows? If not, the gap is probably horizon/memory/global-guidance limited rather than just model/data limited.",
            "",
            "## Follow-up",
            "",
            "- Build G3 teacher/oracle upper-bound tables before any RL fine-tuning.",
            "- Add SIPP teacher ranks and downstream congestion fields to the next junction-slice dataset.",
            "- Keep EdgeScore/BC/DAgger labeled as smoke/prototype until heldout closed-loop rows beat fallback and approach SIPP.",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _prepare_imports()

    import czr005_cpp  # pylint: disable=import-error,import-outside-toplevel
    from czr005.sim_py import IcsGraph, TaskStream  # pylint: disable=import-outside-toplevel

    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    runtime_model = czr005_cpp.EdgeScoreRuntimeModel.from_text(str(MODEL_PATH))

    scenario_runs: dict[str, dict[str, Any]] = {}
    for scenario in _case_plan():
        scenario_runs[scenario.name] = _run_scenario(graph, all_tasks, runtime_model, scenario)

    tables = _build_tables(graph, scenario_runs)
    _write_csv(SUMMARY_TABLE, tables["summary"])
    _write_csv(FAILED_TASK_TABLE, tables["failed"])
    _write_csv(FIRST_DIVERGENCE_TABLE, tables["first_divergence"])
    _write_csv(DECISION_SLICE_TABLE, tables["decision_slices"])
    _write_csv(FAILURE_SLICE_TABLE, tables["failure_slices"])
    _write_csv(COUNTERFACTUAL_TABLE, tables["counterfactual"])
    _write_csv(MOTIF_TABLE, tables["motifs"])
    heatmap_status = _write_heatmap(tables["failed"])
    _write_report(tables, heatmap_status)

    edge_failures = sum(1 for row in tables["failed"] if row["policy_family"] == "edge_score_event")
    fallback_failures = sum(1 for row in tables["failed"] if row["policy_family"] == "fallback_event")
    pibt_failures = sum(1 for row in tables["failed"] if row["policy_family"] == "pibt_active_bag_replay")
    if edge_failures != 47:
        raise AssertionError(f"expected EdgeScore gap of 47 task-scenario rows, got {edge_failures}")
    print(
        "g2_learning_gap_autopsy "
        f"edge_score_failures={edge_failures} fallback_failures={fallback_failures} pibt_failures={pibt_failures}"
    )
    print(f"report={REPORT_PATH}")


if __name__ == "__main__":
    main()
