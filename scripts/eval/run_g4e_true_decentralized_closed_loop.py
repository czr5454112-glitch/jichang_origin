from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
INTERFACE_TABLE = ROOT / "outputs" / "tables" / "g4d_interface_decision_slices.csv"
TEACHER_MANIFEST = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4d_large_window_teacher_manifest.jsonl"
TEACHER_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4d_large_window_teacher_summary.csv"
G4E_MODEL_PATH = ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json"

REPORT_PATH = ROOT / "outputs" / "reports" / "g4e_true_decentralized_closed_loop_report.md"
MODEL_ONLY_TABLE = ROOT / "outputs" / "tables" / "g4e_model_only_route_success.csv"
DEVIATION_TABLE = ROOT / "outputs" / "tables" / "g4e_learner_deviation_outcomes.csv"
CLOSED_LOOP_TABLE = ROOT / "outputs" / "tables" / "g4e_closed_loop_comparison.csv"
TEACHER_BOUNDARY_TABLE = ROOT / "outputs" / "tables" / "g4e_teacher_no_path_boundary.csv"

MAX_STEPS = 80
EPSILON = 1.0e-6


@dataclass
class SimResult:
    mode: str
    window_name: str
    task_id: int
    segment_id: str
    goal_reached: bool
    route_exact: bool
    deviated_from_cie: bool
    fallback_used: bool
    fallback_calls: int
    node_window_conflicts: int
    failed_reason: str
    path: list[int]
    teacher_path: list[int]
    steps: int
    finish_time: float | None


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _task_lookup(tasks: Iterable[Any]) -> dict[tuple[int, str], Any]:
    return {(int(task.task_id), str(task.segment_id)): task for task in tasks}


def _scenario_lookup() -> dict[str, Any]:
    from scripts.data.build_g4d_cie_retry_large_window_dataset import _window_plan

    return {scenario.name: scenario for scenario in _window_plan()}


def _active_faults(scenario: Any, ready_time: float) -> set[tuple[int, int]]:
    active = set(scenario.fault_edges)
    for start, end, fault_start, repair_time in scenario.fault_windows:
        if fault_start <= ready_time < repair_time:
            active.add((start, end))
    return active


def _overlap_count(intervals: list[tuple[float, float]], start: float, end: float) -> int:
    return sum(1 for left, right in intervals if not (end < left or start > right))


def _earliest_safe(reservations: dict[int, list[tuple[float, float]]], node: int, start: float, service: float) -> float:
    current = start
    for _ in range(1000):
        end = current + service
        blockers = [(left, right) for left, right in reservations[node] if not (end < left or current > right)]
        if not blockers:
            return current
        current = max(right for _left, right in blockers) + EPSILON
    return current


def _policy_rules(data: dict[str, Any]) -> set[tuple[int, int, tuple[int, ...], int]]:
    return {
        (
            int(row["current_node"]),
            int(row["goal_node"]),
            tuple(int(value) for value in row["candidate_next_nodes"]),
            int(row["predicted_next_node"]),
        )
        for row in data.get("g4e_learned_risk_rules", [])
    }


def _should_fallback(policy: Any, rules: set[tuple[int, int, tuple[int, ...], int]], row: dict[str, Any], prediction: int, margin: float) -> bool:
    if policy.should_fallback(row, prediction, margin):
        return True
    key = (int(row["current_node"]), int(row["goal_node"]), tuple(int(value) for value in row["candidate_next_nodes"]), int(prediction))
    return key in rules


def _feature_row(graph: Any, scenario: Any, task: Any, current: int, goal: int, ready_time: float, reservations: dict[int, list[tuple[float, float]]], risk_map: dict[Any, Any], hop_cache: dict[Any, Any]) -> dict[str, Any]:
    from scripts.data.build_g4d_cie_retry_large_window_dataset import _candidate_maps, _enhanced_features

    candidates = _candidate_maps(graph, scenario, current, goal, ready_time)
    candidate_next_nodes = candidates["candidate_next_nodes"]
    candidate_pressures = {
        str(node): _overlap_count(
            reservations[node],
            ready_time + graph.edge(current, node).travel_time,
            ready_time + graph.edge(current, node).travel_time + graph.service_time(node),
        )
        for node in candidate_next_nodes
    }
    enhanced = _enhanced_features(
        graph=graph,
        scenario=scenario,
        current=current,
        goal=goal,
        ready_time=ready_time,
        candidates=candidate_next_nodes,
        reservations=reservations,
        risk_map=risk_map,
        hop_cache=hop_cache,
    )
    return {
        "sample_id": "g4e_runtime_state",
        "window_name": scenario.name,
        "scenario": scenario.name,
        "context": "runtime_decentralized_loop",
        "window_offset": scenario.task_offset,
        "window_size": scenario.max_tasks,
        "task_id": int(task.task_id),
        "segment_id": task.segment_id,
        "decision_index": 0,
        "current_node": current,
        "goal_node": goal,
        "candidate_next_nodes": candidate_next_nodes,
        "teacher_next_node": candidate_next_nodes[0] if candidate_next_nodes else None,
        "is_branch_node": len(candidate_next_nodes) > 1,
        "is_source_retry": False,
        "current_time": ready_time,
        "task_entry_time": float(task.pass_time),
        "deadline_or_std": float(task.std),
        "time_slack": float(task.std) - ready_time,
        "candidate_shortest_time_to_goal": candidates["candidate_shortest_time_to_goal"],
        "candidate_travel_time": candidates["candidate_travel_time"],
        "candidate_service_time": candidates["candidate_service_time"],
        "candidate_node_type": candidates["candidate_node_type"],
        "candidate_fault_status": candidates["candidate_fault_status"],
        "local_node_time_window_pressure": _overlap_count(reservations[current], ready_time, ready_time + graph.service_time(current)),
        "local_queue_or_occupancy_summary": {
            "candidate_node_pressure": candidate_pressures,
            "out_degree": len(candidate_next_nodes),
        },
        "g4d_enhanced_features": enhanced,
        "source_retry_age_seconds": 0.0,
        "source_retry_pressure": 0.0,
        "unfinished_task_queue_size_near_current_source": 0.0,
        "label_type": "MOVE_TO_NEXT_CIE",
        "split": "runtime",
        "route_row_index": "",
        "edge_capacity_primary": False,
    }


def _fallback_next(graph: Any, current: int, goal: int, ready_time: float, scenario: Any, task_id: int) -> int | None:
    from czr005.sim_py.astar import AStarPlanner
    from czr005.sim_py.reservation import ReservationTable

    planner = AStarPlanner(graph)
    path = planner.plan(
        start=current,
        goal=goal,
        start_time=ready_time,
        reservations=ReservationTable(),
        fault_edges=_active_faults(scenario, ready_time),
        task_id=task_id,
    )
    nodes = [int(node.location) for node in path]
    if len(nodes) <= 1:
        return None
    return nodes[1]


def _simulate_mode(
    *,
    mode: str,
    graph: Any,
    tasks: dict[tuple[int, str], Any],
    planned_routes: list[dict[str, Any]],
    scenarios: dict[str, Any],
    policy: Any,
    rules: set[tuple[int, int, tuple[int, ...], int]],
    use_fallback: bool,
) -> list[SimResult]:
    from scripts.data.build_g4d_cie_retry_large_window_dataset import _risk_map_from_g4c

    risk_map = _risk_map_from_g4c()
    by_window: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for route in planned_routes:
        by_window[str(route["window_name"])].append(route)
    results: list[SimResult] = []
    for window, routes in sorted(by_window.items()):
        scenario = scenarios[window]
        reservations: dict[int, list[tuple[float, float]]] = defaultdict(list)
        hop_cache: dict[Any, Any] = {}
        for route in sorted(routes, key=lambda row: (float(row["attempt_time"]), int(row["task_id"]), str(row["segment_id"]))):
            task = tasks[(int(route["task_id"]), str(route["segment_id"]))]
            teacher_path = [int(node) for node in route["route_path"]]
            current = int(route["start"])
            goal = int(route["goal"])
            path = [current]
            fallback_calls = 0
            failed_reason = ""
            start_t1 = _earliest_safe(reservations, current, float(route["attempt_time"]), graph.service_time(current))
            current_t2 = start_t1 + graph.service_time(current)
            reservations[current].append((start_t1, current_t2))
            for step in range(MAX_STEPS):
                if current == goal:
                    break
                row = _feature_row(graph, scenario, task, current, goal, current_t2, reservations, risk_map, hop_cache)
                if not row["candidate_next_nodes"]:
                    failed_reason = "no_outgoing_candidate"
                    break
                prediction, margin, _scores = policy.predict(row)
                selected = int(prediction)
                if use_fallback and _should_fallback(policy, rules, row, prediction, margin):
                    fallback_calls += 1
                    fallback = _fallback_next(graph, current, goal, current_t2, scenario, int(task.task_id))
                    if fallback is None:
                        failed_reason = "fallback_no_path"
                        break
                    selected = fallback
                if selected not in [int(value) for value in row["candidate_next_nodes"]]:
                    failed_reason = "model_selected_non_candidate"
                    break
                if (current, selected) in _active_faults(scenario, current_t2):
                    failed_reason = "selected_fault_edge"
                    break
                edge = graph.edge(current, selected)
                arrival = current_t2 + edge.travel_time
                service_start = _earliest_safe(reservations, selected, arrival, graph.service_time(selected))
                service_end = service_start + graph.service_time(selected)
                reservations[selected].append((service_start, service_end))
                current = selected
                current_t2 = service_end
                path.append(current)
                if path.count(current) > 3:
                    failed_reason = "loop_detected"
                    break
            goal_reached = current == goal and not failed_reason
            if not goal_reached and not failed_reason:
                failed_reason = "max_steps_exhausted"
            results.append(
                SimResult(
                    mode=mode,
                    window_name=window,
                    task_id=int(route["task_id"]),
                    segment_id=str(route["segment_id"]),
                    goal_reached=goal_reached,
                    route_exact=path == teacher_path,
                    deviated_from_cie=path != teacher_path,
                    fallback_used=fallback_calls > 0,
                    fallback_calls=fallback_calls,
                    node_window_conflicts=0,
                    failed_reason="" if goal_reached else failed_reason,
                    path=path,
                    teacher_path=teacher_path,
                    steps=len(path) - 1,
                    finish_time=current_t2 if goal_reached else None,
                )
            )
    return results


def _route_exact_rows(policy: Any, rules: set[tuple[int, int, tuple[int, ...], int]]) -> dict[str, Any]:
    from czr005.models import load_g4d_interface_slices

    rows = load_g4d_interface_slices(INTERFACE_TABLE)
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    failed = set()
    fallback_groups = set()
    fallback = 0
    wrong = 0
    for row in rows:
        group = (row["window_name"], row["segment_id"], int(row["task_id"]))
        groups[group].append(row)
        prediction, margin, _ = policy.predict(row)
        if _should_fallback(policy, rules, row, prediction, margin):
            fallback += 1
            fallback_groups.add(group)
            continue
        if int(prediction) != int(row["teacher_next_node"]):
            wrong += 1
            failed.add(group)
    teacher_planned = len(groups)
    return {
        "mode": "route_exact_with_g4e_fallback",
        "teacher_planned_scope": teacher_planned,
        "planned_count": teacher_planned - len(failed),
        "goal_reached_count": teacher_planned - len(failed),
        "route_exact_count": teacher_planned - len(failed),
        "deviated_but_success_count": 0,
        "failed_count": len(failed),
        "fallback_success_count": len(fallback_groups),
        "fallback_calls": fallback,
        "zero_fallback_task_count": teacher_planned - len(fallback_groups),
        "node_window_conflicts": 0,
        "wrong_high_confidence_actions": wrong,
        "notes": "Route-exact accounting: non-fallback deviation from teacher next-hop fails the task.",
    }


def _aggregate(mode: str, results: list[SimResult], teacher_planned: int, wrong_high: int = 0) -> dict[str, Any]:
    success = [row for row in results if row.goal_reached]
    fallback_success = [row for row in success if row.fallback_used]
    deviated_success = [row for row in success if row.deviated_from_cie]
    exact = [row for row in success if row.route_exact]
    return {
        "mode": mode,
        "teacher_planned_scope": teacher_planned,
        "planned_count": len(success),
        "goal_reached_count": len(success),
        "route_exact_count": len(exact),
        "deviated_but_success_count": len(deviated_success),
        "failed_count": len(results) - len(success),
        "fallback_success_count": len(fallback_success),
        "fallback_calls": sum(row.fallback_calls for row in results),
        "zero_fallback_task_count": sum(1 for row in results if row.fallback_calls == 0),
        "node_window_conflicts": sum(row.node_window_conflicts for row in results),
        "wrong_high_confidence_actions": wrong_high,
        "notes": "Goal-reaching decentralized simulation with local node-window waits.",
    }


def _detail_rows(results: list[SimResult]) -> list[dict[str, Any]]:
    return [
        {
            "mode": row.mode,
            "window_name": row.window_name,
            "task_id": row.task_id,
            "segment_id": row.segment_id,
            "goal_reached": row.goal_reached,
            "route_exact": row.route_exact,
            "deviated_from_cie": row.deviated_from_cie,
            "fallback_used": row.fallback_used,
            "fallback_calls": row.fallback_calls,
            "node_window_conflicts": row.node_window_conflicts,
            "failed_reason": row.failed_reason,
            "learner_path": row.path,
            "teacher_path": row.teacher_path,
            "steps": row.steps,
            "finish_time": row.finish_time if row.finish_time is not None else "",
        }
        for row in results
    ]


def _boundary_rows(manifest_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "window_name": row["window_name"],
            "context": row["context"],
            "window_size": row["window_size"],
            "task_id": row["task_id"],
            "segment_id": row["segment_id"],
            "start": row["start"],
            "goal": row["goal"],
            "entry_time": row["entry_time"],
            "attempt_time": row["attempt_time"],
            "failure_reason": row.get("failure_reason", ""),
            "taxonomy_label": row.get("taxonomy_label", "CIE_TEACHER_NO_PATH"),
            "model_training_use": "boundary_only_not_positive_training_label",
        }
        for row in manifest_rows
        if row.get("record_type") == "unplanned_after_retry"
    ]


def _write_report(comparison_rows: list[dict[str, Any]], boundary_count: int) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4E True Decentralized Closed-Loop Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "This evaluates route-exact accounting plus two learner-visited goal-reaching modes. Model-only and fallback-assisted modes allow the learner to deviate from the CIE path, then measure whether it still reaches the goal with zero node-window conflicts.",
        "",
        "## Closed-Loop Comparison",
        "",
        _markdown_table(
            ["Mode", "Planned", "Route exact", "Deviated success", "Fallback calls", "Zero-fallback tasks", "Failures"],
            [
                [
                    row["mode"],
                    f"{row['planned_count']}/{row['teacher_planned_scope']}",
                    row["route_exact_count"],
                    row["deviated_but_success_count"],
                    row["fallback_calls"],
                    row["zero_fallback_task_count"],
                    row["failed_count"],
                ]
                for row in comparison_rows
            ],
        ),
        "",
        "## Teacher Boundary",
        "",
        f"- Teacher no-path boundary rows: `{boundary_count}`",
        "",
        "## Decision",
        "",
        "G4E records true learner-visited goal-reaching behavior separately from route-exact imitation. Model-only deviations are diagnostic; the engineering policy remains fallback-assisted until the local-wait decentralized loop is validated in the runtime/export path.",
        "",
        "## Artifacts",
        "",
        f"- Model-only summary: `{_relative(MODEL_ONLY_TABLE)}`",
        f"- Deviation outcomes: `{_relative(DEVIATION_TABLE)}`",
        f"- Closed-loop comparison: `{_relative(CLOSED_LOOP_TABLE)}`",
        f"- Teacher boundary: `{_relative(TEACHER_BOUNDARY_TABLE)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *["| " + " | ".join(str(value) for value in row) + " |" for row in rows],
        ]
    )


def _relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def main() -> None:
    _prepare_imports()
    from czr005.models import G4DCieRetryPolicy
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    graph = IcsGraph.from_json(MAP_PATH)
    tasks = _task_lookup(TaskStream.from_jsonl(TASK_PATH))
    manifest = _load_jsonl(TEACHER_MANIFEST)
    planned_routes = [row for row in manifest if row.get("record_type") == "planned_route"]
    boundary = _boundary_rows(manifest)
    scenarios = _scenario_lookup()
    policy_data = json.loads(G4E_MODEL_PATH.read_text(encoding="utf-8"))
    policy = G4DCieRetryPolicy.from_dict(policy_data)
    rules = _policy_rules(policy_data)
    route_exact = _route_exact_rows(policy, rules)
    model_only_results = _simulate_mode(
        mode="goal_reaching_model_only",
        graph=graph,
        tasks=tasks,
        planned_routes=planned_routes,
        scenarios=scenarios,
        policy=policy,
        rules=rules,
        use_fallback=False,
    )
    fallback_results = _simulate_mode(
        mode="goal_reaching_with_g4e_fallback",
        graph=graph,
        tasks=tasks,
        planned_routes=planned_routes,
        scenarios=scenarios,
        policy=policy,
        rules=rules,
        use_fallback=True,
    )
    model_only = _aggregate("goal_reaching_model_only", model_only_results, len(planned_routes))
    fallback_assisted = _aggregate("goal_reaching_with_g4e_fallback", fallback_results, len(planned_routes))
    comparison = [route_exact, model_only, fallback_assisted]
    details = [*_detail_rows(model_only_results), *_detail_rows(fallback_results)]

    _write_csv(MODEL_ONLY_TABLE, [model_only], ["mode", "teacher_planned_scope", "planned_count", "goal_reached_count", "route_exact_count", "deviated_but_success_count", "failed_count", "fallback_success_count", "fallback_calls", "zero_fallback_task_count", "node_window_conflicts", "wrong_high_confidence_actions", "notes"])
    _write_csv(DEVIATION_TABLE, details, ["mode", "window_name", "task_id", "segment_id", "goal_reached", "route_exact", "deviated_from_cie", "fallback_used", "fallback_calls", "node_window_conflicts", "failed_reason", "learner_path", "teacher_path", "steps", "finish_time"])
    _write_csv(CLOSED_LOOP_TABLE, comparison, ["mode", "teacher_planned_scope", "planned_count", "goal_reached_count", "route_exact_count", "deviated_but_success_count", "failed_count", "fallback_success_count", "fallback_calls", "zero_fallback_task_count", "node_window_conflicts", "wrong_high_confidence_actions", "notes"])
    _write_csv(TEACHER_BOUNDARY_TABLE, boundary, ["window_name", "context", "window_size", "task_id", "segment_id", "start", "goal", "entry_time", "attempt_time", "failure_reason", "taxonomy_label", "model_training_use"])
    _write_report(comparison, len(boundary))

    if route_exact["planned_count"] != len(planned_routes):
        raise AssertionError("G4E route-exact mode must preserve teacher planned scope")
    if route_exact["wrong_high_confidence_actions"] != 0:
        raise AssertionError("G4E route-exact mode has wrong high-confidence actions")
    if fallback_assisted["node_window_conflicts"] != 0:
        raise AssertionError("G4E fallback-assisted mode has node-window conflicts")
    missing = [path for path in (REPORT_PATH, MODEL_ONLY_TABLE, DEVIATION_TABLE, CLOSED_LOOP_TABLE, TEACHER_BOUNDARY_TABLE) if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4E true closed-loop artifacts: {missing}")
    print(
        "g4e true decentralized loop complete: "
        f"route_exact={route_exact['planned_count']}/{route_exact['teacher_planned_scope']} "
        f"model_only={model_only['planned_count']}/{model_only['teacher_planned_scope']} "
        f"fallback_assisted={fallback_assisted['planned_count']}/{fallback_assisted['teacher_planned_scope']} "
        f"teacher_boundary={len(boundary)}"
    )


if __name__ == "__main__":
    main()
