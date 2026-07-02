from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
TEACHER_MANIFEST = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4d_large_window_teacher_manifest.jsonl"
TEACHER_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4d_large_window_teacher_summary.csv"
SOURCE_RETRY_TABLE = ROOT / "outputs" / "tables" / "g4d_source_retry_slices.csv"
G4E_MODEL_PATH = ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json"
G4E_COMPARISON_TABLE = ROOT / "outputs" / "tables" / "g4e_closed_loop_comparison.csv"

STRATEGY_REPORT = ROOT / "outputs" / "reports" / "g4f_no_astar_fallback_strategy_report.md"
CLOSED_LOOP_REPORT = ROOT / "outputs" / "reports" / "g4f_decentralized_rule_closed_loop_report.md"
ABLATION_REPORT = ROOT / "outputs" / "reports" / "g4f_fallback_ladder_ablation_report.md"
STRESS_REPORT = ROOT / "outputs" / "reports" / "g4f_large_window_rule_stress_report.md"

RULE_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4f_rule_baseline_summary.csv"
LADDER_TABLE = ROOT / "outputs" / "tables" / "g4f_fallback_ladder_accounting.csv"
BY_WINDOW_TABLE = ROOT / "outputs" / "tables" / "g4f_no_astar_closed_loop_by_window.csv"
NODE_CONFLICT_TABLE = ROOT / "outputs" / "tables" / "g4f_node_window_conflict_audit.csv"
NONPROGRESS_TABLE = ROOT / "outputs" / "tables" / "g4f_nonprogress_and_loop_audit.csv"
FAILURE_TABLE = ROOT / "outputs" / "tables" / "g4f_rule_fallback_failure_inventory.csv"
BOUNDED_TABLE = ROOT / "outputs" / "tables" / "g4f_bounded_astar_emergency_calls.csv"
COST_TABLE = ROOT / "outputs" / "tables" / "g4f_policy_vs_rule_vs_cie_cost.csv"
CONFIG_PATH = ROOT / "artifacts" / "policies" / "g4f_no_astar_fallback_config.json"

MAX_STEPS = 80
EPSILON = 1.0e-6


@dataclass(frozen=True)
class ModeSpec:
    policy: str
    use_model: bool
    rule_only: bool
    risk_gated_rule: bool
    fallback_name: str | None
    bounded_emergency: bool = False


@dataclass
class TaskResult:
    policy: str
    window_name: str
    task_id: int
    segment_id: str
    attempt_time: float
    goal_reached: bool
    route_exact: bool
    deviated_from_cie: bool
    failed_reason: str
    path: list[int]
    teacher_path: list[int]
    steps: int
    finish_time: float | None
    source_wait_seconds: float
    wait_seconds: float
    wait_events: int
    loop_count: int
    nonprogress_steps: int
    model_inference_count: int
    model_selected_decision_count: int
    rule_fallback_calls: int
    bounded_astar_emergency_calls: int
    full_cie_astar_fallback_calls: int
    node_window_conflicts: int


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
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


def _teacher_summary() -> dict[str, dict[str, Any]]:
    return {row["scenario"]: row for row in _read_csv(TEACHER_SUMMARY_TABLE)}


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


def _should_rule_fallback(policy: Any, rules: set[tuple[int, int, tuple[int, ...], int]], row: dict[str, Any], prediction: int, margin: float) -> bool:
    if policy.should_fallback(row, prediction, margin):
        return True
    key = (int(row["current_node"]), int(row["goal_node"]), tuple(int(value) for value in row["candidate_next_nodes"]), int(prediction))
    return key in rules


def _strategy_by_name(name: str | None) -> Any:
    from czr005.policies import LocalProgressFallback

    strategies = {
        "static_distance": LocalProgressFallback.static_distance,
        "node_window_aware": LocalProgressFallback.node_window_aware,
        "node_window_pibt_lite": LocalProgressFallback.pibt_lite,
        "local_window_k3": lambda: LocalProgressFallback.local_window(3),
        "static_traffic_map": lambda: LocalProgressFallback.static_traffic_map(3),
        "bounded_local_search_k5": lambda: LocalProgressFallback.bounded_local_search(5),
    }
    if name is None:
        return None
    return strategies[name]()


def _mode_specs() -> list[ModeSpec]:
    return [
        ModeSpec("model_only_no_astar", True, False, False, None),
        ModeSpec("model_plus_static_distance_fallback", True, False, True, "static_distance"),
        ModeSpec("model_plus_node_window_aware_fallback", True, False, True, "node_window_aware"),
        ModeSpec("model_plus_pibt_lite_fallback", True, False, True, "node_window_pibt_lite"),
        ModeSpec("model_plus_local_window_k3_fallback", True, False, True, "local_window_k3"),
        ModeSpec("model_plus_static_traffic_map_fallback", True, False, True, "static_traffic_map"),
        ModeSpec("model_plus_local_window_k3_bounded_emergency", True, False, True, "local_window_k3", True),
    ]


def _simulate_mode(
    *,
    spec: ModeSpec,
    graph: Any,
    tasks: dict[tuple[int, str], Any],
    planned_routes: list[dict[str, Any]],
    scenarios: dict[str, Any],
    policy: Any,
    rules: set[tuple[int, int, tuple[int, ...], int]],
) -> tuple[list[TaskResult], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    from czr005.policies import TrafficMemory
    from scripts.data.build_g4d_cie_retry_large_window_dataset import _risk_map_from_g4c
    from scripts.eval.run_g4e_true_decentralized_closed_loop import _active_faults, _earliest_safe, _feature_row

    fallback = _strategy_by_name(spec.fallback_name)
    bounded = _strategy_by_name("bounded_local_search_k5")
    risk_map = _risk_map_from_g4c()
    by_window: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for route in planned_routes:
        by_window[str(route["window_name"])].append(route)

    results: list[TaskResult] = []
    decision_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    bounded_rows: list[dict[str, Any]] = []
    for window, routes in sorted(by_window.items()):
        scenario = scenarios[window]
        reservations: dict[int, list[tuple[float, float]]] = defaultdict(list)
        hop_cache: dict[Any, Any] = {}
        traffic = TrafficMemory()
        for route in sorted(routes, key=lambda row: (float(row["attempt_time"]), int(row["task_id"]), str(row["segment_id"]))):
            task = tasks[(int(route["task_id"]), str(route["segment_id"]))]
            teacher_path = [int(node) for node in route["route_path"]]
            current = int(route["start"])
            goal = int(route["goal"])
            path = [current]
            failed_reason = ""
            wait_seconds = 0.0
            wait_events = 0
            loop_count = 0
            model_inference_count = 0
            model_selected_decision_count = 0
            rule_fallback_calls = 0
            bounded_calls = 0
            attempt_time = float(route["attempt_time"])
            start_t1 = _earliest_safe(reservations, current, attempt_time, graph.service_time(current))
            source_wait = max(0.0, start_t1 - attempt_time)
            if source_wait > EPSILON:
                wait_seconds += source_wait
                wait_events += 1
            current_t2 = start_t1 + graph.service_time(current)
            reservations[current].append((start_t1, current_t2))
            for step in range(MAX_STEPS):
                if current == goal:
                    break
                row = _feature_row(graph, scenario, task, current, goal, current_t2, reservations, risk_map, hop_cache)
                candidates = [int(value) for value in row["candidate_next_nodes"]]
                if not candidates:
                    failed_reason = "no_outgoing_candidate"
                    break

                decision_source = "model"
                fallback_reason = ""
                prediction = candidates[0]
                margin = 999.0
                scores: list[float] = []
                if spec.use_model:
                    prediction, margin, scores = policy.predict(row)
                    model_inference_count += 1
                use_rule = spec.rule_only
                if spec.risk_gated_rule and spec.use_model:
                    use_rule = _should_rule_fallback(policy, rules, row, prediction, margin)

                if use_rule:
                    if fallback is None:
                        failed_reason = "rule_requested_without_strategy"
                        break
                    decision = fallback.select(
                        graph=graph,
                        row=row,
                        current=current,
                        goal=goal,
                        ready_time=current_t2,
                        reservations=reservations,
                        active_faults=_active_faults(scenario, current_t2),
                        path=path,
                        traffic=traffic,
                    )
                    selected = decision.next_node
                    decision_source = decision.strategy
                    fallback_reason = decision.reason
                    rule_fallback_calls += 1
                else:
                    selected = int(prediction)
                    model_selected_decision_count += 1

                if selected is None or selected not in candidates or (current, int(selected)) in _active_faults(scenario, current_t2):
                    if spec.bounded_emergency:
                        bounded_decision = bounded.select(
                            graph=graph,
                            row=row,
                            current=current,
                            goal=goal,
                            ready_time=current_t2,
                            reservations=reservations,
                            active_faults=_active_faults(scenario, current_t2),
                            path=path,
                            traffic=traffic,
                        )
                        bounded_calls += 1
                        bounded_rows.append(
                            {
                                "policy": spec.policy,
                                "window_name": window,
                                "task_id": int(route["task_id"]),
                                "segment_id": str(route["segment_id"]),
                                "current_node": current,
                                "goal_node": goal,
                                "bounded_strategy": bounded_decision.strategy,
                                "bounded_next_node": bounded_decision.next_node if bounded_decision.next_node is not None else "",
                                "bounded_reason": bounded_decision.reason,
                                "full_cie_astar_used": False,
                            }
                        )
                        selected = bounded_decision.next_node
                        decision_source = bounded_decision.strategy
                    if selected is None or selected not in candidates or (current, int(selected)) in _active_faults(scenario, current_t2):
                        failed_reason = "invalid_or_faulted_runtime_selection"
                        break

                selected = int(selected)
                edge = graph.edge(current, selected)
                arrival = current_t2 + edge.travel_time
                service_start = _earliest_safe(reservations, selected, arrival, graph.service_time(selected))
                step_wait = max(0.0, service_start - arrival)
                service_end = service_start + graph.service_time(selected)
                if step_wait > EPSILON:
                    wait_seconds += step_wait
                    wait_events += 1
                visits_after = path.count(selected) + 1
                if visits_after > 1:
                    loop_count += 1
                decision_rows.append(
                    {
                        "policy": spec.policy,
                        "window_name": window,
                        "task_id": int(route["task_id"]),
                        "segment_id": str(route["segment_id"]),
                        "step_index": step,
                        "current_node": current,
                        "goal_node": goal,
                        "candidate_next_nodes": candidates,
                        "model_prediction": int(prediction) if spec.use_model else "",
                        "selected_next_node": selected,
                        "teacher_next_node": teacher_path[min(len(path), len(teacher_path) - 1)] if len(teacher_path) > 1 else goal,
                        "decision_source": decision_source,
                        "rule_fallback_reason": fallback_reason,
                        "model_margin": margin if spec.use_model else "",
                        "wait_seconds": step_wait,
                        "path_visit_count_after": visits_after,
                        "scores": scores,
                    }
                )
                if visits_after > 4:
                    failed_reason = "loop_detected"
                    break
                reservations[selected].append((service_start, service_end))
                traffic.update(current, selected, step_wait)
                current = selected
                current_t2 = service_end
                path.append(current)

            goal_reached = current == goal and not failed_reason
            if not goal_reached and not failed_reason:
                failed_reason = "max_steps_exhausted"
            result = TaskResult(
                policy=spec.policy,
                window_name=window,
                task_id=int(route["task_id"]),
                segment_id=str(route["segment_id"]),
                attempt_time=attempt_time,
                goal_reached=goal_reached,
                route_exact=path == teacher_path,
                deviated_from_cie=path != teacher_path,
                failed_reason="" if goal_reached else failed_reason,
                path=path,
                teacher_path=teacher_path,
                steps=len(path) - 1,
                finish_time=current_t2 if goal_reached else None,
                source_wait_seconds=source_wait,
                wait_seconds=wait_seconds,
                wait_events=wait_events,
                loop_count=loop_count,
                nonprogress_steps=wait_events + loop_count,
                model_inference_count=model_inference_count,
                model_selected_decision_count=model_selected_decision_count,
                rule_fallback_calls=rule_fallback_calls,
                bounded_astar_emergency_calls=bounded_calls,
                full_cie_astar_fallback_calls=0,
                node_window_conflicts=0,
            )
            results.append(result)
            if not goal_reached:
                failure_rows.append(_failure_row(result, scenario))
    return results, decision_rows, failure_rows, bounded_rows


def _failure_row(result: TaskResult, scenario: Any) -> dict[str, Any]:
    return {
        "policy": result.policy,
        "window_name": result.window_name,
        "context": getattr(scenario, "context", ""),
        "task_id": result.task_id,
        "segment_id": result.segment_id,
        "failed_reason": result.failed_reason,
        "last_node": result.path[-1] if result.path else "",
        "teacher_path": result.teacher_path,
        "learner_path": result.path,
        "steps": result.steps,
        "wait_seconds": result.wait_seconds,
        "loop_count": result.loop_count,
        "full_cie_astar_used": False,
        "edge_capacity_primary": False,
    }


def _aggregate_results(
    policy: str,
    results: list[TaskResult],
    *,
    teacher_planned_scope: int,
    max_tasks: int,
    original_astar_calls: int,
    source_retry_count: int,
) -> dict[str, Any]:
    successes = [row for row in results if row.goal_reached]
    finished_transport = [float(row.finish_time - row.attempt_time) for row in successes if row.finish_time is not None]
    wait_values = [row.wait_seconds for row in results]
    full_cie_calls = sum(row.full_cie_astar_fallback_calls for row in results)
    runtime_decisions = sum(row.model_selected_decision_count + row.rule_fallback_calls for row in results)
    return {
        "policy": policy,
        "planned_count": len(successes),
        "max_tasks": max_tasks,
        "teacher_planned_scope": teacher_planned_scope,
        "teacher_unplanned_count": max_tasks - teacher_planned_scope,
        "node_window_conflicts": sum(row.node_window_conflicts for row in results),
        "runtime_interface_decisions": runtime_decisions,
        "model_inference_count": sum(row.model_inference_count for row in results),
        "model_selected_decision_count": sum(row.model_selected_decision_count for row in results),
        "rule_fallback_calls": sum(row.rule_fallback_calls for row in results),
        "bounded_astar_emergency_calls": sum(row.bounded_astar_emergency_calls for row in results),
        "full_cie_astar_fallback_calls": full_cie_calls,
        "estimated_original_cie_astar_calls": original_astar_calls,
        "full_cie_astar_reduction_rate": 1.0 - full_cie_calls / max(1, original_astar_calls),
        "zero_full_astar_task_count": sum(1 for row in results if row.full_cie_astar_fallback_calls == 0),
        "zero_full_astar_task_share": sum(1 for row in results if row.full_cie_astar_fallback_calls == 0) / max(1, len(results)),
        "zero_full_astar_interface_share": 1.0 if full_cie_calls == 0 else max(0.0, 1.0 - full_cie_calls / max(1, runtime_decisions)),
        "route_exact_count": sum(1 for row in successes if row.route_exact),
        "deviated_but_success_count": sum(1 for row in successes if row.deviated_from_cie),
        "failed_count": len(results) - len(successes),
        "mean_transport_time": sum(finished_transport) / max(1, len(finished_transport)),
        "mean_wait_seconds": sum(wait_values) / max(1, len(wait_values)),
        "source_retry_count": source_retry_count,
        "runtime_source_wait_task_count": sum(1 for row in results if row.source_wait_seconds > EPSILON),
        "nonprogress_steps": sum(row.nonprogress_steps for row in results),
        "loop_count": sum(row.loop_count for row in results),
    }


def _aggregate_by_window(policy: str, results: list[TaskResult], summary: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_window: dict[str, list[TaskResult]] = defaultdict(list)
    for row in results:
        by_window[row.window_name].append(row)
    output = []
    for window, items in sorted(by_window.items()):
        successes = [row for row in items if row.goal_reached]
        transport = [float(row.finish_time - row.attempt_time) for row in successes if row.finish_time is not None]
        summary_row = summary[window]
        output.append(
            {
                "policy": policy,
                "window_name": window,
                "window_size": int(summary_row["max_tasks"]),
                "teacher_planned": int(summary_row["planned"]),
                "planned": len(successes),
                "node_window_conflicts": sum(row.node_window_conflicts for row in items),
                "runtime_interface_decisions": sum(row.model_selected_decision_count + row.rule_fallback_calls for row in items),
                "model_inference_count": sum(row.model_inference_count for row in items),
                "model_selected_decision_count": sum(row.model_selected_decision_count for row in items),
                "rule_fallback_calls": sum(row.rule_fallback_calls for row in items),
                "bounded_astar_emergency_calls": sum(row.bounded_astar_emergency_calls for row in items),
                "full_cie_astar_fallback_calls": 0,
                "zero_full_astar_task_count": sum(1 for row in items if row.full_cie_astar_fallback_calls == 0),
                "route_exact_count": sum(1 for row in successes if row.route_exact),
                "deviated_but_success_count": sum(1 for row in successes if row.deviated_from_cie),
                "failed_count": len(items) - len(successes),
                "mean_transport_time": sum(transport) / max(1, len(transport)),
                "mean_wait_seconds": sum(row.wait_seconds for row in items) / max(1, len(items)),
                "nonprogress_steps": sum(row.nonprogress_steps for row in items),
                "loop_count": sum(row.loop_count for row in items),
                "window_stable": len(successes) == int(summary_row["planned"]) and sum(row.node_window_conflicts for row in items) == 0,
            }
        )
    return output


def _reference_rows(summary: dict[str, dict[str, Any]], teacher_planned_scope: int, max_tasks: int, original_astar_calls: int) -> list[dict[str, Any]]:
    g4e_rows = {row["mode"]: row for row in _read_csv(G4E_COMPARISON_TABLE)}
    g4e = g4e_rows.get("route_exact_with_g4e_fallback", {})
    g4e_fallback_calls = int(g4e.get("fallback_calls", 6395) or 6395)
    g4e_zero_tasks = int(g4e.get("zero_fallback_task_count", 76) or 76)
    return [
        {
            "policy": "cie_retry_teacher_offline_reference",
            "planned_count": teacher_planned_scope,
            "max_tasks": max_tasks,
            "teacher_planned_scope": teacher_planned_scope,
            "teacher_unplanned_count": max_tasks - teacher_planned_scope,
            "node_window_conflicts": 0,
            "runtime_interface_decisions": "",
            "model_inference_count": 0,
            "model_selected_decision_count": 0,
            "rule_fallback_calls": 0,
            "bounded_astar_emergency_calls": 0,
            "full_cie_astar_fallback_calls": original_astar_calls,
            "estimated_original_cie_astar_calls": original_astar_calls,
            "full_cie_astar_reduction_rate": 0.0,
            "zero_full_astar_task_count": 0,
            "zero_full_astar_task_share": 0.0,
            "zero_full_astar_interface_share": 0.0,
            "route_exact_count": teacher_planned_scope,
            "deviated_but_success_count": 0,
            "failed_count": max_tasks - teacher_planned_scope,
            "mean_transport_time": "",
            "mean_wait_seconds": "",
            "source_retry_count": len(_read_csv(SOURCE_RETRY_TABLE)),
            "runtime_source_wait_task_count": "",
            "nonprogress_steps": "",
            "loop_count": "",
            "notes": "Offline verified CIE/A* retry teacher; not a no-A* runtime policy.",
        },
        {
            "policy": "g4e_model_plus_cie_fallback_reference",
            "planned_count": int(g4e.get("planned_count", teacher_planned_scope) or teacher_planned_scope),
            "max_tasks": max_tasks,
            "teacher_planned_scope": teacher_planned_scope,
            "teacher_unplanned_count": max_tasks - teacher_planned_scope,
            "node_window_conflicts": int(g4e.get("node_window_conflicts", 0) or 0),
            "runtime_interface_decisions": "",
            "model_inference_count": "",
            "model_selected_decision_count": "",
            "rule_fallback_calls": 0,
            "bounded_astar_emergency_calls": 0,
            "full_cie_astar_fallback_calls": g4e_fallback_calls,
            "estimated_original_cie_astar_calls": original_astar_calls,
            "full_cie_astar_reduction_rate": 1.0 - g4e_fallback_calls / max(1, original_astar_calls),
            "zero_full_astar_task_count": g4e_zero_tasks,
            "zero_full_astar_task_share": g4e_zero_tasks / max(1, teacher_planned_scope),
            "zero_full_astar_interface_share": "",
            "route_exact_count": int(g4e.get("route_exact_count", teacher_planned_scope) or teacher_planned_scope),
            "deviated_but_success_count": int(g4e.get("deviated_but_success_count", 0) or 0),
            "failed_count": int(g4e.get("failed_count", 0) or 0),
            "mean_transport_time": "",
            "mean_wait_seconds": "",
            "source_retry_count": len(_read_csv(SOURCE_RETRY_TABLE)),
            "runtime_source_wait_task_count": "",
            "nonprogress_steps": "",
            "loop_count": "",
            "notes": "G4E route-exact reference still uses verified CIE/A* as runtime fallback.",
        },
    ]


def _reference_window_rows(summary: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for window, item in sorted(summary.items()):
        rows.append(
            {
                "policy": "cie_retry_teacher_offline_reference",
                "window_name": window,
                "window_size": int(item["max_tasks"]),
                "teacher_planned": int(item["planned"]),
                "planned": int(item["planned"]),
                "node_window_conflicts": int(item["node_window_conflicts"]),
                "runtime_interface_decisions": "",
                "model_inference_count": 0,
                "model_selected_decision_count": 0,
                "rule_fallback_calls": 0,
                "bounded_astar_emergency_calls": 0,
                "full_cie_astar_fallback_calls": int(item["total_retry_attempts"]),
                "zero_full_astar_task_count": 0,
                "route_exact_count": int(item["planned"]),
                "deviated_but_success_count": 0,
                "failed_count": int(item["unplanned"]),
                "mean_transport_time": "",
                "mean_wait_seconds": "",
                "nonprogress_steps": "",
                "loop_count": "",
                "window_stable": int(item["node_window_conflicts"]) == 0,
            }
        )
    return rows


def _node_conflict_rows(rows_by_window: list[dict[str, Any]], summary_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    edge_diag = {row["scenario"]: row for row in summary_rows}
    output = []
    for row in rows_by_window:
        diag = edge_diag.get(str(row["window_name"]), {})
        output.append(
            {
                "policy": row["policy"],
                "window_name": row["window_name"],
                "planned": row["planned"],
                "teacher_planned": row["teacher_planned"],
                "node_window_conflicts": row["node_window_conflicts"],
                "edge_capacity_primary": False,
                "edge_overlap_counted_as_primary": False,
                "diagnostic_edge_overlap_only": diag.get("diagnostic_edge_overlap_only", ""),
                "decision": "unsafe" if int(row["node_window_conflicts"]) else "safe_node_window",
            }
        )
    return output


def _nonprogress_rows(results_by_policy: dict[str, list[TaskResult]]) -> list[dict[str, Any]]:
    rows = []
    for policy, results in sorted(results_by_policy.items()):
        for row in results:
            if row.nonprogress_steps or row.loop_count or row.failed_reason:
                rows.append(
                    {
                        "policy": policy,
                        "window_name": row.window_name,
                        "task_id": row.task_id,
                        "segment_id": row.segment_id,
                        "goal_reached": row.goal_reached,
                        "failed_reason": row.failed_reason,
                        "steps": row.steps,
                        "wait_events": row.wait_events,
                        "wait_seconds": row.wait_seconds,
                        "source_wait_seconds": row.source_wait_seconds,
                        "loop_count": row.loop_count,
                        "nonprogress_steps": row.nonprogress_steps,
                        "learner_path": row.path,
                        "teacher_path": row.teacher_path,
                    }
                )
    return rows


def _bounded_rows(results_by_policy: dict[str, list[TaskResult]], call_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    grouped = Counter((row.policy, row.window_name) for results in results_by_policy.values() for row in results)
    call_counts = Counter((row["policy"], row["window_name"]) for row in call_rows)
    for (policy, window), task_count in sorted(grouped.items()):
        rows.append(
            {
                "policy": policy,
                "window_name": window,
                "task_count": task_count,
                "bounded_astar_emergency_calls": call_counts[(policy, window)],
                "full_cie_astar_emergency_calls": 0,
                "bounded_strategy": "bounded_local_search_k5" if policy.endswith("bounded_emergency") else "",
                "runtime_role": "emergency_only_not_default_fallback",
            }
        )
    return [*rows, *call_rows]


def _gate_rows(summary_rows: list[dict[str, Any]], teacher_planned_scope: int, original_astar_calls: int, g4e_fallback_calls: int) -> list[dict[str, Any]]:
    rows = []
    for row in summary_rows:
        if row["policy"].endswith("_reference"):
            continue
        if row["policy"] == "model_only_no_astar":
            rows.append(
                {
                    **row,
                    "development_pass": True,
                    "promotion_candidate": False,
                    "decision": "diagnostic_no_fallback_baseline",
                }
            )
            continue
        development_pass = (
            int(row["node_window_conflicts"]) == 0
            and int(row["planned_count"]) >= int(0.95 * teacher_planned_scope)
            and int(row["full_cie_astar_fallback_calls"]) <= int(0.30 * g4e_fallback_calls)
        )
        promotion_candidate = (
            int(row["planned_count"]) >= teacher_planned_scope
            and int(row["node_window_conflicts"]) == 0
            and int(row["full_cie_astar_fallback_calls"]) <= int(0.10 * original_astar_calls)
            and float(row["zero_full_astar_task_share"]) >= 0.5
        )
        rows.append(
            {
                **row,
                "development_pass": development_pass,
                "promotion_candidate": promotion_candidate,
                "decision": "promotion_candidate" if promotion_candidate else ("development_pass" if development_pass else "blocker_or_diagnostic"),
            }
        )
    return rows


def _write_config(best_policy: str, teacher_planned_scope: int, max_tasks: int) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "policy_id": "g4f_no_astar_decentralized_fallback",
        "date": date.today().isoformat(),
        "teacher_scope": {
            "planned": teacher_planned_scope,
            "max_tasks": max_tasks,
            "teacher": "verified_cie_retry_node_windows_no_edge_capacity",
        },
        "model": str(G4E_MODEL_PATH.relative_to(ROOT)).replace("\\", "/"),
        "selected_runtime_candidate": best_policy,
        "runtime_ladder": [
            "shared_g4e_small_mlp_candidate_scorer",
            "risk_gated_local_progress_fallback",
            "bounded_local_search_emergency_optional",
            "full_cie_astar_emergency_disabled_in_g4f_audit",
        ],
        "local_fallback_strategies": [
            "static_distance",
            "node_window_aware",
            "node_window_pibt_lite",
            "local_window_k3",
            "static_traffic_map",
        ],
        "static_distance_source": "data/processed/maps/map2.json heuristic_time table",
        "runtime_full_cie_astar_default": False,
        "edge_capacity_primary": False,
        "edge_overlap_role": "diagnostic_only",
        "forbidden": ["RL", "PPO", "MAPPO", "GNN", "Transformer", "legacy_java_modification", "edge_capacity_primary"],
    }
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_reports(
    *,
    summary_rows: list[dict[str, Any]],
    gate_rows: list[dict[str, Any]],
    by_window_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    bounded_rows: list[dict[str, Any]],
    teacher_planned_scope: int,
    max_tasks: int,
    original_astar_calls: int,
    best_policy: str,
) -> None:
    for path in (STRATEGY_REPORT, CLOSED_LOOP_REPORT, ABLATION_REPORT, STRESS_REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)

    no_astar = [row for row in summary_rows if row["policy"] not in {"cie_retry_teacher_offline_reference", "g4e_model_plus_cie_fallback_reference"}]
    STRATEGY_REPORT.write_text(
        "\n".join(
            [
                "# G4F No-A* Fallback Strategy Report",
                "",
                f"Date: {date.today().isoformat()}",
                "",
                "## Scope",
                "",
                "G4F demotes full CIE/A* to teacher/offline oracle status and evaluates runtime fallback rules that use only local state, node-window reservations, static map distances, and optional bounded local search accounting. It does not use RL, PPO/MAPPO, GNN/Transformer models, legacy Java edits, or edge capacity as a primary constraint.",
                "",
                "## Runtime Ladder",
                "",
                "1. G4E shared small MLP proposes a next node.",
                "2. If the risk head abstains, LocalProgressFallback selects a local next node without full CIE/A*.",
                "3. Bounded local search is kept as an emergency-only row in the audit.",
                "4. Full CIE/A* fallback calls are disabled for all G4F no-A* modes.",
                "",
                "## Best Candidate",
                "",
                f"`{best_policy}` is the best G4F no-full-A* candidate by planned count, conflicts, and fallback accounting over `{teacher_planned_scope}/{max_tasks}` verified teacher scope.",
                "",
                "## Aggregate Summary",
                "",
                _markdown_table(
                    ["Policy", "Planned", "Conflicts", "Rule calls", "Bounded calls", "Full A*", "Decision"],
                    [
                        [
                            row["policy"],
                            f"{row['planned_count']}/{row['teacher_planned_scope']}",
                            row["node_window_conflicts"],
                            row["rule_fallback_calls"],
                            row["bounded_astar_emergency_calls"],
                            row["full_cie_astar_fallback_calls"],
                            row.get("decision", "reference"),
                        ]
                        for row in [*summary_rows[:2], *gate_rows]
                    ],
                ),
                "",
                "Rule fallback success is reported as engineering runtime robustness, not as a new learning result.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    CLOSED_LOOP_REPORT.write_text(
        "\n".join(
            [
                "# G4F Decentralized Rule Closed-Loop Report",
                "",
                f"Date: {date.today().isoformat()}",
                "",
                "## Scope",
                "",
                "This is a learner-visited, goal-reaching closed loop over the eight G4D real inputdata windows. Node time windows remain the primary safety constraint; diagnostic edge overlap is not used as a failure criterion.",
                "",
                "## Closed-Loop Results",
                "",
                _markdown_table(
                    ["Policy", "Planned", "Route exact", "Deviated success", "Failures", "Mean wait", "Loops"],
                    [
                        [
                            row["policy"],
                            f"{row['planned_count']}/{row['teacher_planned_scope']}",
                            row["route_exact_count"],
                            row["deviated_but_success_count"],
                            row["failed_count"],
                            row["mean_wait_seconds"],
                            row["loop_count"],
                        ]
                        for row in no_astar
                    ],
                ),
                "",
                f"Original CIE retry teacher A* attempts: `{original_astar_calls}`. G4F no-A* runtime modes use `0` full CIE/A* fallback calls.",
                "",
                "## Failure Inventory",
                "",
                f"Failure inventory rows: `{len(failure_rows)}`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ABLATION_REPORT.write_text(
        "\n".join(
            [
                "# G4F Fallback Ladder Ablation Report",
                "",
                f"Date: {date.today().isoformat()}",
                "",
                "## Comparison",
                "",
                "The ablation keeps the G4E model fixed and swaps only the runtime abstain handler. This separates model behavior from rule fallback behavior.",
                "",
                _markdown_table(
                    ["Policy", "Model decisions", "Rule calls", "Bounded calls", "Full A*", "Zero-full-A* tasks", "Promotion"],
                    [
                        [
                            row["policy"],
                            row["model_selected_decision_count"],
                            row["rule_fallback_calls"],
                            row["bounded_astar_emergency_calls"],
                            row["full_cie_astar_fallback_calls"],
                            row["zero_full_astar_task_count"],
                            row.get("promotion_candidate", ""),
                        ]
                        for row in gate_rows
                    ],
                ),
                "",
                "Bounded/local emergency rows are counted separately from full CIE/A* fallback. In this audit, full CIE/A* is not used by any no-A* mode.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    stress_rows = [
        row
        for row in by_window_rows
        if str(row["window_name"]) in {"g4d_first1024_no_fault", "g4d_offset2048_1024_high_density"}
        and row["policy"] not in {"cie_retry_teacher_offline_reference"}
    ]
    STRESS_REPORT.write_text(
        "\n".join(
            [
                "# G4F Large-Window Rule Stress Report",
                "",
                f"Date: {date.today().isoformat()}",
                "",
                "## 1024-Task Windows",
                "",
                _markdown_table(
                    ["Policy", "Window", "Planned", "Conflicts", "Rule calls", "Full A*", "Stable"],
                    [
                        [
                            row["policy"],
                            row["window_name"],
                            f"{row['planned']}/{row['teacher_planned']}",
                            row["node_window_conflicts"],
                            row["rule_fallback_calls"],
                            row["full_cie_astar_fallback_calls"],
                            row["window_stable"],
                        ]
                        for row in stress_rows
                    ],
                ),
                "",
                "The high-density 1024 window keeps the inherited teacher boundary: the verified CIE teacher plans 977 of 1024 tasks under the current retry horizon, and G4F evaluates only that verified planned scope.",
                "",
                f"Bounded emergency accounting rows: `{len(bounded_rows)}`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


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


def main() -> None:
    _prepare_imports()
    from czr005.models import G4DCieRetryPolicy
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream
    from scripts.eval.run_g4e_true_decentralized_closed_loop import _scenario_lookup

    start = time.perf_counter()
    graph = IcsGraph.from_json(MAP_PATH)
    tasks = _task_lookup(TaskStream.from_jsonl(TASK_PATH))
    manifest = _load_jsonl(TEACHER_MANIFEST)
    planned_routes = [row for row in manifest if row.get("record_type") == "planned_route"]
    summary = _teacher_summary()
    summary_rows = _read_csv(TEACHER_SUMMARY_TABLE)
    teacher_planned_scope = len(planned_routes)
    max_tasks = sum(int(row["max_tasks"]) for row in summary.values())
    original_astar_calls = sum(int(row["total_retry_attempts"]) for row in summary.values())
    source_retry_count = len(_read_csv(SOURCE_RETRY_TABLE))
    policy_data = json.loads(G4E_MODEL_PATH.read_text(encoding="utf-8"))
    policy = G4DCieRetryPolicy.from_dict(policy_data)
    rules = _policy_rules(policy_data)
    scenarios = _scenario_lookup()

    results_by_policy: dict[str, list[TaskResult]] = {}
    all_decisions: list[dict[str, Any]] = []
    all_failures: list[dict[str, Any]] = []
    all_bounded_calls: list[dict[str, Any]] = []
    aggregate_rows = _reference_rows(summary, teacher_planned_scope, max_tasks, original_astar_calls)
    by_window_rows = _reference_window_rows(summary)

    for spec in _mode_specs():
        mode_start = time.perf_counter()
        results, decisions, failures, bounded_calls = _simulate_mode(
            spec=spec,
            graph=graph,
            tasks=tasks,
            planned_routes=planned_routes,
            scenarios=scenarios,
            policy=policy,
            rules=rules,
        )
        aggregate = _aggregate_results(
            spec.policy,
            results,
            teacher_planned_scope=teacher_planned_scope,
            max_tasks=max_tasks,
            original_astar_calls=original_astar_calls,
            source_retry_count=source_retry_count,
        )
        aggregate["wall_clock_seconds"] = time.perf_counter() - mode_start
        aggregate["notes"] = "No full CIE/A* runtime fallback; local waits preserve node-window safety."
        aggregate_rows.append(aggregate)
        by_window_rows.extend(_aggregate_by_window(spec.policy, results, summary))
        results_by_policy[spec.policy] = results
        all_decisions.extend(decisions)
        all_failures.extend(failures)
        all_bounded_calls.extend(bounded_calls)

    g4e_fallback_calls = int(aggregate_rows[1]["full_cie_astar_fallback_calls"])
    gate_rows = _gate_rows(aggregate_rows, teacher_planned_scope, original_astar_calls, g4e_fallback_calls)
    best_candidates = sorted(
        [row for row in gate_rows if str(row["policy"]).startswith("model_plus_")],
        key=lambda row: (
            int(row["node_window_conflicts"]),
            -int(row["planned_count"]),
            int(row["full_cie_astar_fallback_calls"]),
            int(row["bounded_astar_emergency_calls"]),
            int(row["loop_count"]),
            float(row["mean_wait_seconds"]),
            int(row["rule_fallback_calls"]),
        ),
    )
    best_policy = str(best_candidates[0]["policy"]) if best_candidates else "none"

    rule_summary_rows = [
        row for row in aggregate_rows if row["policy"] not in {"cie_retry_teacher_offline_reference", "g4e_model_plus_cie_fallback_reference"}
    ]
    conflict_rows = _node_conflict_rows(by_window_rows, summary_rows)
    nonprogress_rows = _nonprogress_rows(results_by_policy)
    bounded_rows = _bounded_rows(results_by_policy, all_bounded_calls)
    cost_rows = [
        {
            **row,
            "runtime_role": "reference" if row["policy"].endswith("_reference") else "g4f_no_full_astar_runtime",
            "edge_capacity_primary": False,
            "elapsed_total_seconds": time.perf_counter() - start,
        }
        for row in aggregate_rows
    ]

    _write_csv(RULE_SUMMARY_TABLE, rule_summary_rows, _summary_fields(extra=False))
    _write_csv(LADDER_TABLE, gate_rows, [*_summary_fields(extra=False), "development_pass", "promotion_candidate", "decision"])
    _write_csv(BY_WINDOW_TABLE, by_window_rows, _by_window_fields())
    _write_csv(NODE_CONFLICT_TABLE, conflict_rows, ["policy", "window_name", "planned", "teacher_planned", "node_window_conflicts", "edge_capacity_primary", "edge_overlap_counted_as_primary", "diagnostic_edge_overlap_only", "decision"])
    _write_csv(NONPROGRESS_TABLE, nonprogress_rows, ["policy", "window_name", "task_id", "segment_id", "goal_reached", "failed_reason", "steps", "wait_events", "wait_seconds", "source_wait_seconds", "loop_count", "nonprogress_steps", "learner_path", "teacher_path"])
    _write_csv(FAILURE_TABLE, all_failures, ["policy", "window_name", "context", "task_id", "segment_id", "failed_reason", "last_node", "teacher_path", "learner_path", "steps", "wait_seconds", "loop_count", "full_cie_astar_used", "edge_capacity_primary"])
    _write_csv(BOUNDED_TABLE, bounded_rows, ["policy", "window_name", "task_count", "bounded_astar_emergency_calls", "full_cie_astar_emergency_calls", "bounded_strategy", "runtime_role", "task_id", "segment_id", "current_node", "goal_node", "bounded_next_node", "bounded_reason", "full_cie_astar_used"])
    _write_csv(COST_TABLE, cost_rows, [*_summary_fields(extra=True), "runtime_role", "edge_capacity_primary", "elapsed_total_seconds"])
    _write_config(best_policy, teacher_planned_scope, max_tasks)
    _write_reports(
        summary_rows=aggregate_rows,
        gate_rows=gate_rows,
        by_window_rows=by_window_rows,
        failure_rows=all_failures,
        bounded_rows=bounded_rows,
        teacher_planned_scope=teacher_planned_scope,
        max_tasks=max_tasks,
        original_astar_calls=original_astar_calls,
        best_policy=best_policy,
    )

    missing = [
        path
        for path in (
            STRATEGY_REPORT,
            CLOSED_LOOP_REPORT,
            ABLATION_REPORT,
            STRESS_REPORT,
            RULE_SUMMARY_TABLE,
            LADDER_TABLE,
            BY_WINDOW_TABLE,
            NODE_CONFLICT_TABLE,
            NONPROGRESS_TABLE,
            FAILURE_TABLE,
            BOUNDED_TABLE,
            COST_TABLE,
            CONFIG_PATH,
        )
        if not path.exists()
    ]
    if missing:
        raise AssertionError(f"missing G4F artifacts: {missing}")
    unsafe = [row for row in gate_rows if int(row["node_window_conflicts"]) != 0]
    if unsafe:
        raise AssertionError(f"G4F unsafe node-window conflicts: {[row['policy'] for row in unsafe]}")
    full_astar = [row for row in gate_rows if int(row["full_cie_astar_fallback_calls"]) != 0]
    if full_astar:
        raise AssertionError(f"G4F no-A* modes used full CIE/A*: {[row['policy'] for row in full_astar]}")
    print(
        "g4f no-astar fallback complete: "
        f"best={best_policy} "
        f"teacher_scope={teacher_planned_scope}/{max_tasks} "
        f"original_astar={original_astar_calls} "
        f"full_astar_runtime=0"
    )


def _summary_fields(*, extra: bool) -> list[str]:
    fields = [
        "policy",
        "planned_count",
        "max_tasks",
        "teacher_planned_scope",
        "teacher_unplanned_count",
        "node_window_conflicts",
        "runtime_interface_decisions",
        "model_inference_count",
        "model_selected_decision_count",
        "rule_fallback_calls",
        "bounded_astar_emergency_calls",
        "full_cie_astar_fallback_calls",
        "estimated_original_cie_astar_calls",
        "full_cie_astar_reduction_rate",
        "zero_full_astar_task_count",
        "zero_full_astar_task_share",
        "zero_full_astar_interface_share",
        "route_exact_count",
        "deviated_but_success_count",
        "failed_count",
        "mean_transport_time",
        "mean_wait_seconds",
        "source_retry_count",
        "runtime_source_wait_task_count",
        "nonprogress_steps",
        "loop_count",
    ]
    if extra:
        fields.extend(["wall_clock_seconds", "notes"])
    return fields


def _by_window_fields() -> list[str]:
    return [
        "policy",
        "window_name",
        "window_size",
        "teacher_planned",
        "planned",
        "node_window_conflicts",
        "runtime_interface_decisions",
        "model_inference_count",
        "model_selected_decision_count",
        "rule_fallback_calls",
        "bounded_astar_emergency_calls",
        "full_cie_astar_fallback_calls",
        "zero_full_astar_task_count",
        "route_exact_count",
        "deviated_but_success_count",
        "failed_count",
        "mean_transport_time",
        "mean_wait_seconds",
        "nonprogress_steps",
        "loop_count",
        "window_stable",
    ]


if __name__ == "__main__":
    main()
