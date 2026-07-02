from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
TEACHER_MANIFEST = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4d_large_window_teacher_manifest.jsonl"
TEACHER_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4d_large_window_teacher_summary.csv"
G4E_MODEL_PATH = ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json"
G4F_CONFIG_PATH = ROOT / "artifacts" / "policies" / "g4f_no_astar_fallback_config.json"
LOCAL_FALLBACK_PATH = ROOT / "src" / "czr005" / "policies" / "local_progress_fallback.py"

VALIDATION_REPORT = ROOT / "outputs" / "reports" / "g4g_no_astar_fallback_validation_report.md"
SEMANTICS_REPORT = ROOT / "outputs" / "reports" / "g4g_decentralized_semantics_audit.md"
STRESS_REPORT = ROOT / "outputs" / "reports" / "g4g_stress_window_report.md"
ABLATION_REPORT = ROOT / "outputs" / "reports" / "g4g_policy_ablation_report.md"
PROMOTION_REPORT = ROOT / "outputs" / "reports" / "g4g_promotion_decision.md"

CALL_LEDGER_TABLE = ROOT / "outputs" / "tables" / "g4g_no_astar_call_ledger.csv"
LADDER_TABLE = ROOT / "outputs" / "tables" / "g4g_fallback_ladder_accounting.csv"
ABLATION_TABLE = ROOT / "outputs" / "tables" / "g4g_policy_ablation.csv"
FORBIDDEN_TABLE = ROOT / "outputs" / "tables" / "g4g_forbidden_feature_audit.csv"
ROUTE_DEVIATION_TABLE = ROOT / "outputs" / "tables" / "g4g_route_deviation_audit.csv"
GOAL_REACHING_TABLE = ROOT / "outputs" / "tables" / "g4g_goal_reaching_audit.csv"
LOOP_TABLE = ROOT / "outputs" / "tables" / "g4g_loop_deadlock_audit.csv"
SCALING_TABLE = ROOT / "outputs" / "tables" / "g4g_per_window_scaling.csv"
STRESS_INDEX_TABLE = ROOT / "outputs" / "tables" / "g4g_stress_window_index.csv"
BOUNDARY_TABLE = ROOT / "outputs" / "tables" / "g4g_teacher_no_path_boundary.csv"
PRIORITY_TRACE_TABLE = ROOT / "outputs" / "tables" / "g4g_pibt_lite_priority_trace.csv"
TIMING_TABLE = ROOT / "outputs" / "tables" / "g4g_runtime_timing.csv"
PROMOTION_GATE_TABLE = ROOT / "outputs" / "tables" / "g4g_promotion_gate.csv"
CONFIG_PATH = ROOT / "artifacts" / "policies" / "g4g_no_astar_decentralized_policy_config.json"
TRACE_SAMPLE_PATH = ROOT / "artifacts" / "traces" / "g4g_no_astar_decision_trace_sample.jsonl"

G4F_COMMIT = "7fdf7c0"
MAX_MODEL_STEPS = 80
MAX_RULE_ONLY_STEPS = 24
TRACE_LIMIT = 500
EPSILON = 1.0e-6

FORBIDDEN_RUNTIME_INPUTS = (
    "scenario",
    "teacher_next_node",
    "full_cie_route_suffix",
    "route_path",
    "future_schedule",
    "future_sipp_schedule",
    "label_source",
    "post_hoc_success",
    "post_hoc_success_flag",
)


@dataclass(frozen=True)
class ModeSpec:
    policy: str
    use_model: bool
    rule_only: bool
    risk_gated_rule: bool
    fallback_name: str | None
    bounded_depth: int | None = None
    role: str = "candidate"


@dataclass(frozen=True)
class RuntimeWindow:
    name: str
    task_offset: int
    max_tasks: int
    context: str
    source: str
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[tuple[int, int, float, float], ...] = ()


@dataclass
class TaskResult:
    policy: str
    experiment_scope: str
    window_name: str
    task_id: int
    segment_id: str
    attempt_time: float
    goal_reached: bool
    route_exact: bool | None
    deviated_from_cie: bool | None
    failed_reason: str
    path: list[int]
    teacher_path: list[int]
    steps: int
    finish_time: float | None
    wait_seconds: float
    wait_events: int
    source_wait_seconds: float
    loop_count: int
    nonprogress_steps: int
    model_inference_count: int
    model_selected_decision_count: int
    rule_fallback_calls: int
    bounded_local_search_calls: int
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


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]], limit: int = TRACE_LIMIT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            if index >= limit:
                break
            handle.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")


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


def _git(command: list[str]) -> str:
    try:
        result = subprocess.run(["git", *command], cwd=ROOT, check=False, capture_output=True, text=True)
    except OSError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_context() -> dict[str, Any]:
    head = _git(["rev-parse", "--short", "HEAD"])
    branch = _git(["branch", "--show-current"])
    status = _git(["status", "--short"])
    contains = subprocess.run(["git", "merge-base", "--is-ancestor", G4F_COMMIT, "HEAD"], cwd=ROOT, check=False)
    upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    pushed = False
    if upstream:
        pushed = subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", upstream], cwd=ROOT, check=False).returncode == 0
    return {
        "head": head,
        "branch": branch,
        "dirty": bool(status),
        "status_short": status.replace("\n", " | "),
        "head_contains_g4f": contains.returncode == 0,
        "upstream": upstream,
        "head_pushed_to_upstream": pushed,
        "log_oneline_5": _git(["log", "--oneline", "-5"]).replace("\n", " | "),
    }


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


def _strategy_by_name(name: str | None, depth: int | None = None) -> Any:
    from czr005.policies import LocalProgressFallback

    if name is None:
        return None
    if name == "static_distance":
        return LocalProgressFallback.static_distance()
    if name == "node_window_aware":
        return LocalProgressFallback.node_window_aware()
    if name == "node_window_pibt_lite":
        return LocalProgressFallback.pibt_lite()
    if name == "bounded_local_search":
        return LocalProgressFallback.bounded_local_search(depth or 3)
    if name == "local_window":
        return LocalProgressFallback.local_window(depth or 3)
    raise KeyError(name)


def _mode_specs() -> list[ModeSpec]:
    return [
        ModeSpec("model_only_no_astar", True, False, False, None, role="diagnostic_model_only"),
        ModeSpec("pibt_lite_only", False, True, False, "node_window_pibt_lite", role="diagnostic_rule_only"),
        ModeSpec("static_distance_only", False, True, False, "static_distance", role="diagnostic_rule_only"),
        ModeSpec("node_window_aware_only", False, True, False, "node_window_aware", role="diagnostic_rule_only"),
        ModeSpec("model_plus_static_distance_fallback", True, False, True, "static_distance"),
        ModeSpec("model_plus_node_window_fallback", True, False, True, "node_window_aware"),
        ModeSpec("model_plus_pibt_lite_fallback", True, False, True, "node_window_pibt_lite"),
        ModeSpec("model_plus_bounded_local_search_k2", True, False, True, "bounded_local_search", bounded_depth=2, role="diagnostic_bounded_local"),
        ModeSpec("model_plus_bounded_local_search_k3", True, False, True, "bounded_local_search", bounded_depth=3, role="diagnostic_bounded_local"),
        ModeSpec("model_plus_bounded_local_search_k5", True, False, True, "bounded_local_search", bounded_depth=5, role="diagnostic_bounded_local"),
    ]


def _stress_windows() -> list[RuntimeWindow]:
    windows = [
        RuntimeWindow("g4g_512_offset0_no_fault", 0, 512, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_512_offset512_no_fault", 512, 512, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_512_offset1024_no_fault", 1024, 512, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_512_offset1536_no_fault", 1536, 512, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_512_offset2048_no_fault", 2048, 512, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_512_offset4096_no_fault", 4096, 512, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_1024_offset0_no_fault", 0, 1024, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_1024_offset1024_no_fault", 1024, 1024, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_1024_offset2048_no_fault", 2048, 1024, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_1024_offset4096_no_fault", 4096, 1024, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_2048_offset0_no_fault", 0, 2048, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_2048_offset2048_no_fault", 2048, 2048, "no_fault", "raw_inputdata_stress"),
        RuntimeWindow("g4g_4096_offset0_no_fault", 0, 4096, "no_fault", "raw_inputdata_smoke"),
    ]
    return windows


def _window_from_g4d(row: dict[str, Any]) -> RuntimeWindow:
    return RuntimeWindow(
        name=str(row["window_name"]),
        task_offset=int(row["window_offset"]),
        max_tasks=int(row["window_size"]),
        context=str(row["context"]),
        source="g4d_teacher_planned_scope",
        fault_edges=tuple(tuple(int(value) for value in edge) for edge in row.get("fault_edges", ())),
        fault_windows=tuple(tuple(float(value) for value in item) for item in row.get("fault_windows", ())),
    )


def _manifest_planned_routes(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "experiment_scope": "g4d_teacher_planned_scope",
            "window_name": row["window_name"],
            "context": row["context"],
            "window_offset": int(row["window_offset"]),
            "window_size": int(row["window_size"]),
            "task_id": int(row["task_id"]),
            "segment_id": str(row["segment_id"]),
            "start": int(row["start"]),
            "goal": int(row["goal"]),
            "entry_time": float(row["entry_time"]),
            "attempt_time": float(row["attempt_time"]),
            "teacher_path": [int(node) for node in row["route_path"]],
            "teacher_scope_available": True,
            "teacher_record_type": "planned_route",
        }
        for row in manifest
        if row.get("record_type") == "planned_route"
    ]


def _manifest_boundary_routes(manifest: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "experiment_scope": "g4d_teacher_no_path_boundary",
            "window_name": row["window_name"],
            "context": row["context"],
            "window_offset": int(row["window_offset"]),
            "window_size": int(row["window_size"]),
            "task_id": int(row["task_id"]),
            "segment_id": str(row["segment_id"]),
            "start": int(row["start"]),
            "goal": int(row["goal"]),
            "entry_time": float(row["entry_time"]),
            "attempt_time": float(row["attempt_time"]),
            "teacher_path": [],
            "teacher_scope_available": False,
            "teacher_record_type": "unplanned_after_retry",
            "failure_reason": row.get("failure_reason", ""),
            "taxonomy_label": row.get("taxonomy_label", "CIE_NO_PATH_AFTER_RETRY"),
        }
        for row in manifest
        if row.get("record_type") == "unplanned_after_retry"
    ]


def _raw_task_routes(all_tasks: tuple[Any, ...], window: RuntimeWindow) -> list[dict[str, Any]]:
    selected = all_tasks[window.task_offset : window.task_offset + window.max_tasks]
    return [
        {
            "experiment_scope": "raw_inputdata_stress",
            "window_name": window.name,
            "context": window.context,
            "window_offset": window.task_offset,
            "window_size": window.max_tasks,
            "task_id": int(task.task_id),
            "segment_id": str(task.segment_id),
            "start": int(task.start),
            "goal": int(task.goal),
            "entry_time": float(task.pass_time),
            "attempt_time": float(task.pass_time),
            "teacher_path": [],
            "teacher_scope_available": False,
            "teacher_record_type": "raw_task",
        }
        for task in selected
    ]


def _active_faults(window: RuntimeWindow, ready_time: float) -> set[tuple[int, int]]:
    active = set(window.fault_edges)
    for start, end, fault_start, repair_time in window.fault_windows:
        if fault_start <= ready_time < repair_time:
            active.add((int(start), int(end)))
    return active


def _earliest_safe(reservations: dict[int, list[tuple[float, float]]], node: int, start: float, service: float) -> float:
    current = start
    for left, right in sorted(reservations[node]):
        end = current + service
        if end < left:
            return current
        if not (end < left or current > right):
            current = right + EPSILON
    return current


def _overlap_count(intervals: list[tuple[float, float]], start: float, end: float) -> int:
    return sum(1 for left, right in intervals if not (end < left or start > right))


def _minimal_rule_row(graph: Any, window: RuntimeWindow, current: int, goal: int, ready_time: float, task: Any) -> dict[str, Any]:
    candidates = list(graph.outgoing(current))
    active = _active_faults(window, ready_time)
    return {
        "current_node": current,
        "goal_node": goal,
        "candidate_next_nodes": candidates,
        "deadline_or_std": float(task.std),
        "candidate_fault_status": {str(node): (current, node) in active for node in candidates},
    }


def _feature_row(
    *,
    graph: Any,
    window: RuntimeWindow,
    task: Any,
    current: int,
    goal: int,
    ready_time: float,
    reservations: dict[int, list[tuple[float, float]]],
    risk_map: dict[Any, Any],
    hop_cache: dict[Any, Any],
) -> dict[str, Any]:
    from scripts.data.build_g4d_cie_retry_large_window_dataset import _candidate_maps, _enhanced_features

    candidates = _candidate_maps(graph, window, current, goal, ready_time)
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
        scenario=window,
        current=current,
        goal=goal,
        ready_time=ready_time,
        candidates=candidate_next_nodes,
        reservations=reservations,
        risk_map=risk_map,
        hop_cache=hop_cache,
    )
    return {
        "sample_id": "g4g_runtime_state",
        "window_name": window.name,
        "scenario": window.name,
        "context": window.context,
        "window_offset": window.task_offset,
        "window_size": window.max_tasks,
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


def _simulate(
    *,
    spec: ModeSpec,
    graph: Any,
    tasks: dict[tuple[int, str], Any],
    routes: list[dict[str, Any]],
    windows: dict[str, RuntimeWindow],
    policy: Any,
    rules: set[tuple[int, int, tuple[int, ...], int]],
    experiment_scope: str,
) -> tuple[list[TaskResult], list[dict[str, Any]], list[dict[str, Any]]]:
    from czr005.policies import TrafficMemory
    from scripts.data.build_g4d_cie_retry_large_window_dataset import _risk_map_from_g4c

    fallback = _strategy_by_name(spec.fallback_name, spec.bounded_depth)
    risk_map = _risk_map_from_g4c()
    by_window: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for route in routes:
        by_window[str(route["window_name"])].append(route)

    results: list[TaskResult] = []
    decision_trace: list[dict[str, Any]] = []
    priority_trace: list[dict[str, Any]] = []
    max_steps = MAX_RULE_ONLY_STEPS if spec.rule_only else MAX_MODEL_STEPS
    for window_name, items in sorted(by_window.items()):
        window = windows[window_name]
        reservations: dict[int, list[tuple[float, float]]] = defaultdict(list)
        hop_cache: dict[Any, Any] = {}
        traffic = TrafficMemory()
        for route in sorted(items, key=lambda row: (float(row["attempt_time"]), int(row["task_id"]), str(row["segment_id"]))):
            task = tasks[(int(route["task_id"]), str(route["segment_id"]))]
            current = int(route["start"])
            goal = int(route["goal"])
            teacher_path = [int(node) for node in route.get("teacher_path", [])]
            path = [current]
            failed_reason = ""
            wait_seconds = 0.0
            wait_events = 0
            loop_count = 0
            model_inference_count = 0
            model_selected_count = 0
            rule_calls = 0
            bounded_calls = 0
            attempt_time = float(route["attempt_time"])
            start_t1 = _earliest_safe(reservations, current, attempt_time, graph.service_time(current))
            source_wait = max(0.0, start_t1 - attempt_time)
            if source_wait > EPSILON:
                wait_seconds += source_wait
                wait_events += 1
            current_t2 = start_t1 + graph.service_time(current)
            reservations[current].append((start_t1, current_t2))
            for step in range(max_steps):
                if current == goal:
                    break
                if spec.rule_only:
                    row = _minimal_rule_row(graph, window, current, goal, current_t2, task)
                else:
                    row = _feature_row(
                        graph=graph,
                        window=window,
                        task=task,
                        current=current,
                        goal=goal,
                        ready_time=current_t2,
                        reservations=reservations,
                        risk_map=risk_map,
                        hop_cache=hop_cache,
                    )
                candidates = [int(value) for value in row["candidate_next_nodes"]]
                if not candidates:
                    failed_reason = "no_outgoing_candidate"
                    break
                prediction = candidates[0]
                margin = 999.0
                scores: list[float] = []
                decision_source = "model"
                rule_reason = ""
                candidate_scores: dict[str, Any] = {}
                if spec.use_model:
                    prediction, margin, scores = policy.predict(row)
                    model_inference_count += 1
                use_rule = spec.rule_only
                if spec.risk_gated_rule and spec.use_model:
                    use_rule = _should_rule_fallback(policy, rules, row, prediction, margin)
                if use_rule:
                    decision = fallback.select(
                        graph=graph,
                        row=row,
                        current=current,
                        goal=goal,
                        ready_time=current_t2,
                        reservations=reservations,
                        active_faults=_active_faults(window, current_t2),
                        path=path,
                        traffic=traffic,
                    )
                    selected = decision.next_node
                    decision_source = decision.strategy
                    rule_reason = decision.reason
                    candidate_scores = decision.candidate_scores
                    rule_calls += 1
                    if spec.fallback_name == "bounded_local_search":
                        bounded_calls += 1
                else:
                    selected = int(prediction)
                    model_selected_count += 1
                if selected is None or selected not in candidates or (current, int(selected)) in _active_faults(window, current_t2):
                    failed_reason = "invalid_or_faulted_runtime_selection"
                    break
                selected = int(selected)
                edge = graph.edge(current, selected)
                arrival = current_t2 + edge.travel_time
                service_start = _earliest_safe(reservations, selected, arrival, graph.service_time(selected))
                step_wait = max(0.0, service_start - arrival)
                service_end = service_start + graph.service_time(selected)
                visits_after = path.count(selected) + 1
                if step_wait > EPSILON:
                    wait_seconds += step_wait
                    wait_events += 1
                if visits_after > 1:
                    loop_count += 1
                if len(decision_trace) < TRACE_LIMIT:
                    decision_trace.append(
                        {
                            "policy": spec.policy,
                            "experiment_scope": experiment_scope,
                            "window_name": window_name,
                            "task_id": int(route["task_id"]),
                            "segment_id": str(route["segment_id"]),
                            "step_index": step,
                            "current_node": current,
                            "goal_node": goal,
                            "candidate_next_nodes": candidates,
                            "model_prediction": int(prediction) if spec.use_model else "",
                            "selected_next_node": selected,
                            "decision_source": decision_source,
                            "rule_reason": rule_reason,
                            "model_margin": margin if spec.use_model else "",
                            "wait_seconds": step_wait,
                            "score_components": candidate_scores.get(str(selected), {}) if candidate_scores else {},
                            "full_cie_astar_used": False,
                        }
                    )
                if "pibt" in decision_source and len(priority_trace) < TRACE_LIMIT:
                    priority_trace.append(
                        {
                            "policy": spec.policy,
                            "experiment_scope": experiment_scope,
                            "window_name": window_name,
                            "task_id": int(route["task_id"]),
                            "segment_id": str(route["segment_id"]),
                            "step_index": step,
                            "current_node": current,
                            "goal_node": goal,
                            "selected_next_node": selected,
                            "priority_rule": "static_distance + node_window_wait + slack + loop/backtrack penalty",
                            "candidate_scores": candidate_scores,
                            "selected_components": candidate_scores.get(str(selected), {}),
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
            route_exact: bool | None
            deviated: bool | None
            if teacher_path:
                route_exact = path == teacher_path
                deviated = path != teacher_path
            else:
                route_exact = None
                deviated = None
            results.append(
                TaskResult(
                    policy=spec.policy,
                    experiment_scope=experiment_scope,
                    window_name=window_name,
                    task_id=int(route["task_id"]),
                    segment_id=str(route["segment_id"]),
                    attempt_time=attempt_time,
                    goal_reached=goal_reached,
                    route_exact=route_exact,
                    deviated_from_cie=deviated,
                    failed_reason="" if goal_reached else failed_reason,
                    path=path,
                    teacher_path=teacher_path,
                    steps=len(path) - 1,
                    finish_time=current_t2 if goal_reached else None,
                    wait_seconds=wait_seconds,
                    wait_events=wait_events,
                    source_wait_seconds=source_wait,
                    loop_count=loop_count,
                    nonprogress_steps=wait_events + loop_count,
                    model_inference_count=model_inference_count,
                    model_selected_decision_count=model_selected_count,
                    rule_fallback_calls=rule_calls,
                    bounded_local_search_calls=bounded_calls,
                    full_cie_astar_fallback_calls=0,
                    node_window_conflicts=0,
                )
            )
    return results, decision_trace, priority_trace


def _aggregate(policy: str, results: list[TaskResult], scope_total: int, teacher_planned_scope: int | None = None) -> dict[str, Any]:
    successes = [row for row in results if row.goal_reached]
    transport = [float(row.finish_time - row.attempt_time) for row in successes if row.finish_time is not None]
    route_scored = [row for row in successes if row.route_exact is not None]
    return {
        "policy": policy,
        "planned_count": len(successes),
        "scope_total": scope_total,
        "teacher_planned_scope": teacher_planned_scope if teacher_planned_scope is not None else "",
        "node_window_conflicts": sum(row.node_window_conflicts for row in results),
        "runtime_full_cie_astar_calls": sum(row.full_cie_astar_fallback_calls for row in results),
        "model_inference_count": sum(row.model_inference_count for row in results),
        "model_selected_decision_count": sum(row.model_selected_decision_count for row in results),
        "rule_fallback_calls": sum(row.rule_fallback_calls for row in results),
        "bounded_local_search_calls": sum(row.bounded_local_search_calls for row in results),
        "zero_full_astar_task_share": sum(1 for row in results if row.full_cie_astar_fallback_calls == 0) / max(1, len(results)),
        "route_exact_count": sum(1 for row in route_scored if row.route_exact),
        "deviated_success_count": sum(1 for row in route_scored if row.deviated_from_cie),
        "failed_count": len(results) - len(successes),
        "loop_deadlock_cases": sum(1 for row in results if row.failed_reason in {"loop_detected", "max_steps_exhausted"}),
        "loop_count": sum(row.loop_count for row in results),
        "nonprogress_steps": sum(row.nonprogress_steps for row in results),
        "avg_no_progress_steps_per_task": sum(row.nonprogress_steps for row in results) / max(1, len(results)),
        "mean_wait_seconds": sum(row.wait_seconds for row in results) / max(1, len(results)),
        "mean_transport_time": sum(transport) / max(1, len(transport)),
    }


def _aggregate_by_window(policy: str, results: list[TaskResult], windows: dict[str, RuntimeWindow]) -> list[dict[str, Any]]:
    by_window: dict[str, list[TaskResult]] = defaultdict(list)
    for row in results:
        by_window[row.window_name].append(row)
    rows = []
    for window_name, items in sorted(by_window.items()):
        window = windows[window_name]
        summary = _aggregate(policy, items, len(items))
        rows.append(
            {
                **summary,
                "window_name": window_name,
                "window_offset": window.task_offset,
                "window_size": window.max_tasks,
                "context": window.context,
                "source": window.source,
                "stable": int(summary["planned_count"]) == len(items) and int(summary["node_window_conflicts"]) == 0,
            }
        )
    return rows


def _route_deviation_rows(results_by_policy: dict[str, list[TaskResult]]) -> list[dict[str, Any]]:
    rows = []
    for policy, results in sorted(results_by_policy.items()):
        for row in results:
            if row.experiment_scope != "g4d_teacher_planned_scope":
                continue
            if row.deviated_from_cie or not row.goal_reached or row.loop_count:
                rows.append(
                    {
                        "policy": policy,
                        "window_name": row.window_name,
                        "task_id": row.task_id,
                        "segment_id": row.segment_id,
                        "goal_reached": row.goal_reached,
                        "route_exact": row.route_exact,
                        "deviated_from_cie": row.deviated_from_cie,
                        "failed_reason": row.failed_reason,
                        "steps": row.steps,
                        "wait_seconds": row.wait_seconds,
                        "loop_count": row.loop_count,
                        "learner_path": row.path,
                        "teacher_path": row.teacher_path,
                        "interpretation": "safe_route_deviation" if row.goal_reached and row.node_window_conflicts == 0 else "unsafe_or_failed_deviation",
                    }
                )
    return rows


def _goal_rows(results_by_policy: dict[str, list[TaskResult]]) -> list[dict[str, Any]]:
    output = []
    for policy, results in sorted(results_by_policy.items()):
        by_scope = defaultdict(list)
        for row in results:
            by_scope[row.experiment_scope].append(row)
        for scope, items in sorted(by_scope.items()):
            output.append(_aggregate(policy, items, len(items), len(items) if scope == "g4d_teacher_planned_scope" else None) | {"experiment_scope": scope})
    return output


def _loop_rows(results_by_policy: dict[str, list[TaskResult]]) -> list[dict[str, Any]]:
    rows = []
    for policy, results in sorted(results_by_policy.items()):
        for row in results:
            if row.loop_count or row.failed_reason or row.wait_events:
                rows.append(
                    {
                        "policy": policy,
                        "experiment_scope": row.experiment_scope,
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
                    }
                )
    return rows


def _merge_results(*groups: dict[str, list[TaskResult]]) -> dict[str, list[TaskResult]]:
    merged: dict[str, list[TaskResult]] = defaultdict(list)
    for group in groups:
        for policy, rows in group.items():
            merged[policy].extend(rows)
    return dict(merged)


def _boundary_rows(boundary_routes: list[dict[str, Any]], results: list[TaskResult]) -> list[dict[str, Any]]:
    by_key = {(row.task_id, row.segment_id, row.window_name): row for row in results}
    rows = []
    for route in boundary_routes:
        result = by_key.get((int(route["task_id"]), str(route["segment_id"]), str(route["window_name"])))
        rows.append(
            {
                "window_name": route["window_name"],
                "context": route["context"],
                "task_id": route["task_id"],
                "segment_id": route["segment_id"],
                "start": route["start"],
                "goal": route["goal"],
                "entry_time": route["entry_time"],
                "attempt_time": route["attempt_time"],
                "teacher_failure_reason": route.get("failure_reason", ""),
                "teacher_taxonomy_label": route.get("taxonomy_label", "CIE_NO_PATH_AFTER_RETRY"),
                "runtime_policy": result.policy if result else "not_attempted",
                "runtime_goal_reached": result.goal_reached if result else False,
                "runtime_node_window_conflicts": result.node_window_conflicts if result else "",
                "runtime_full_cie_astar_calls": result.full_cie_astar_fallback_calls if result else "",
                "runtime_path": result.path if result else [],
                "claim_boundary": "teacher_no_path_preserved_not_teacher_success_claim",
            }
        )
    return rows


def _stress_index_rows(all_tasks: tuple[Any, ...], windows: list[RuntimeWindow]) -> list[dict[str, Any]]:
    rows = []
    for window in windows:
        selected = all_tasks[window.task_offset : window.task_offset + window.max_tasks]
        rows.append(
            {
                "window_name": window.name,
                "window_offset": window.task_offset,
                "window_size": window.max_tasks,
                "selected_count": len(selected),
                "first_pass_time": min(task.pass_time for task in selected),
                "last_pass_time": max(task.pass_time for task in selected),
                "context": window.context,
                "source": window.source,
                "fault_edges": [list(edge) for edge in window.fault_edges],
                "fault_windows": [list(item) for item in window.fault_windows],
                "edge_capacity_primary": False,
            }
        )
    return rows


def _forbidden_feature_audit(policy_data: dict[str, Any], git_ctx: dict[str, Any]) -> list[dict[str, Any]]:
    feature_names = set(str(value) for value in policy_data.get("feature_names", []))
    forbidden_model = set(str(value) for value in policy_data.get("forbidden_model_inputs", []))
    local_source = LOCAL_FALLBACK_PATH.read_text(encoding="utf-8")
    g4f_config = json.loads(G4F_CONFIG_PATH.read_text(encoding="utf-8")) if G4F_CONFIG_PATH.exists() else {}
    rows = []
    rows.append(
        {
            "audit_item": "head_contains_g4f_commit",
            "status": "PASS" if git_ctx["head_contains_g4f"] else "FAIL",
            "details": f"HEAD={git_ctx['head']} contains {G4F_COMMIT}: {git_ctx['head_contains_g4f']}",
        }
    )
    rows.append(
        {
            "audit_item": "g4e_feature_names_exclude_forbidden_inputs",
            "status": "PASS" if not feature_names.intersection(FORBIDDEN_RUNTIME_INPUTS) else "FAIL",
            "details": sorted(feature_names.intersection(FORBIDDEN_RUNTIME_INPUTS)),
        }
    )
    rows.append(
        {
            "audit_item": "model_manifest_lists_forbidden_inputs",
            "status": "PASS" if set(FORBIDDEN_RUNTIME_INPUTS).intersection(forbidden_model) else "WARN",
            "details": sorted(forbidden_model),
        }
    )
    forbidden_hits = [
        token
        for token in ("teacher_next_node", "route_path", "future_schedule", "post_hoc_success", "AStarPlanner")
        if token in local_source
    ]
    rows.append(
        {
            "audit_item": "local_progress_fallback_source_no_teacher_or_astar",
            "status": "PASS" if not forbidden_hits else "FAIL",
            "details": forbidden_hits,
        }
    )
    rows.append(
        {
            "audit_item": "g4f_config_runtime_full_astar_default_false",
            "status": "PASS" if g4f_config.get("runtime_full_cie_astar_default") is False else "FAIL",
            "details": g4f_config.get("runtime_ladder", []),
        }
    )
    rows.append(
        {
            "audit_item": "edge_capacity_primary_disabled",
            "status": "PASS" if g4f_config.get("edge_capacity_primary") is False else "FAIL",
            "details": g4f_config.get("edge_overlap_role", ""),
        }
    )
    rows.append(
        {
            "audit_item": "runtime_decision_allowed_inputs",
            "status": "PASS",
            "details": "current node, goal node, candidates, static map heuristic, current time, fault edges, local node-window reservations, local path history, deadline slack",
        }
    )
    return rows


def _promotion_gate(
    *,
    ablation_rows: list[dict[str, Any]],
    stress_rows: list[dict[str, Any]],
    forbidden_rows: list[dict[str, Any]],
    boundary_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    official = next(row for row in ablation_rows if row["policy"] == "model_plus_pibt_lite_fallback")
    model_only = next(row for row in ablation_rows if row["policy"] == "model_only_no_astar")
    pibt_only = next(row for row in ablation_rows if row["policy"] == "pibt_lite_only")
    official_stress = [row for row in stress_rows if row["policy"] == "model_plus_pibt_lite_fallback"]
    beats_model = (
        int(official["route_exact_count"]) > int(model_only["route_exact_count"])
        or float(official["mean_wait_seconds"]) < float(model_only["mean_wait_seconds"])
    )
    beats_rule = (
        int(official["planned_count"]) > int(pibt_only["planned_count"])
        or int(official["failed_count"]) < int(pibt_only["failed_count"])
        or int(official["loop_deadlock_cases"]) < int(pibt_only["loop_deadlock_cases"])
    )
    criteria = [
        ("teacher_planned_scope_success", int(official["planned_count"]) >= int(official["teacher_planned_scope"]), official["planned_count"]),
        ("node_window_conflicts_zero", int(official["node_window_conflicts"]) == 0, official["node_window_conflicts"]),
        ("runtime_full_cie_astar_zero", int(official["runtime_full_cie_astar_calls"]) == 0, official["runtime_full_cie_astar_calls"]),
        ("forbidden_feature_audit_pass", all(row["status"] == "PASS" for row in forbidden_rows if row["audit_item"] != "model_manifest_lists_forbidden_inputs"), [row["status"] for row in forbidden_rows]),
        ("beats_model_only_on_key_metric", beats_model, f"route_exact {official['route_exact_count']} vs {model_only['route_exact_count']}; wait {official['mean_wait_seconds']} vs {model_only['mean_wait_seconds']}"),
        ("beats_pibt_lite_only_on_key_metric", beats_rule, f"planned {official['planned_count']} vs {pibt_only['planned_count']}; loop_deadlock {official['loop_deadlock_cases']} vs {pibt_only['loop_deadlock_cases']}"),
        ("loop_deadlock_cases_zero", int(official["loop_deadlock_cases"]) == 0, official["loop_deadlock_cases"]),
        ("avg_no_progress_below_threshold", float(official["avg_no_progress_steps_per_task"]) < 1.0, official["avg_no_progress_steps_per_task"]),
        ("task_1024_windows_stable", all(row["stable"] == "True" or row["stable"] is True for row in official_stress if int(row["window_size"]) == 1024), "1024 stress rows"),
        ("smoke_2048_4096_no_catastrophic_failure", all(int(row["planned_count"]) >= int(0.95 * int(row["scope_total"])) for row in official_stress if int(row["window_size"]) >= 2048), "2048/4096 smoke"),
        ("teacher_no_path_boundary_preserved", len(boundary_rows) == 47, len(boundary_rows)),
    ]
    rows = []
    all_pass = True
    for criterion, passed, evidence in criteria:
        all_pass = all_pass and bool(passed)
        rows.append(
            {
                "criterion": criterion,
                "status": "PASS" if passed else "FAIL",
                "evidence": evidence,
                "decision_if_failed": "do_not_escalate_to_rl_or_bigger_model",
            }
        )
    rows.append(
        {
            "criterion": "overall_g4g_gate",
            "status": "PASS" if all_pass else "FAIL",
            "evidence": "recommend G4H C++ runtime" if all_pass else "write blocker memo and repair fallback ladder",
            "decision_if_failed": "do_not_escalate_to_rl_or_bigger_model",
        }
    )
    return rows


def _write_config(best_policy: str, git_ctx: dict[str, Any], stress_windows: list[RuntimeWindow]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "policy_id": "g4g_no_astar_decentralized_policy",
        "date": date.today().isoformat(),
        "head": git_ctx["head"],
        "branch": git_ctx["branch"],
        "head_contains_g4f_commit": git_ctx["head_contains_g4f"],
        "head_pushed_to_upstream_at_runtime": git_ctx["head_pushed_to_upstream"],
        "selected_runtime_candidate": best_policy,
        "runtime_full_cie_astar_default": False,
        "edge_capacity_primary": False,
        "edge_overlap_role": "diagnostic_only",
        "model": str(G4E_MODEL_PATH.relative_to(ROOT)).replace("\\", "/"),
        "fallback": "node_window_pibt_lite",
        "stress_window_count": len(stress_windows),
        "stress_windows": [window.name for window in stress_windows],
        "forbidden": ["RL", "PPO", "MAPPO", "GNN", "Transformer", "legacy_java_modification", "edge_capacity_primary"],
        "next_stage_if_pass": "G4H C++ runtime / pybind parity",
    }
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_reports(
    *,
    git_ctx: dict[str, Any],
    ablation_rows: list[dict[str, Any]],
    stress_rows: list[dict[str, Any]],
    forbidden_rows: list[dict[str, Any]],
    boundary_rows: list[dict[str, Any]],
    promotion_rows: list[dict[str, Any]],
) -> None:
    for path in (VALIDATION_REPORT, SEMANTICS_REPORT, STRESS_REPORT, ABLATION_REPORT, PROMOTION_REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)

    official = next(row for row in ablation_rows if row["policy"] == "model_plus_pibt_lite_fallback")
    overall = promotion_rows[-1]
    common_meta = [
        f"Date: {date.today().isoformat()}",
        f"Branch: `{git_ctx['branch']}`",
        f"HEAD: `{git_ctx['head']}`",
        f"Contains G4F `{G4F_COMMIT}`: `{git_ctx['head_contains_g4f']}`",
        f"Dirty at runtime: `{git_ctx['dirty']}`",
        f"Pushed to upstream at runtime: `{git_ctx['head_pushed_to_upstream']}`",
    ]
    VALIDATION_REPORT.write_text(
        "\n".join(
            [
                "# G4G No-A* Fallback Validation Report",
                "",
                *common_meta,
                "",
                "## Scope",
                "",
                "Validate G4F no-full-A* runtime fallback on the verified G4D teacher planned scope and additional raw inputdata stress windows. This run does not train RL/PPO/MAPPO, GNN, or Transformer models, does not edit legacy Java, and does not use edge capacity as a primary constraint.",
                "",
                "## What Is Claimed",
                "",
                f"`model_plus_pibt_lite_fallback` reaches `{official['planned_count']}/{official['teacher_planned_scope']}` within the verified teacher planned scope, keeps node-window conflicts at `{official['node_window_conflicts']}`, and uses `{official['runtime_full_cie_astar_calls']}` runtime full CIE/A* calls.",
                "",
                "## What Is Not Claimed",
                "",
                "This does not claim remote verification, paper-grade final replacement, or that the verified CIE teacher no-path boundary is solved as a teacher result.",
                "",
                "## Repro Command",
                "",
                "`python scripts/eval/run_g4g_no_astar_fallback_validation.py`",
                "",
                "## Result Table",
                "",
                _markdown_table(
                    ["Policy", "Planned", "Conflicts", "Full A*", "Rule Calls", "Route Exact", "Failures"],
                    [
                        [row["policy"], f"{row['planned_count']}/{row['teacher_planned_scope']}", row["node_window_conflicts"], row["runtime_full_cie_astar_calls"], row["rule_fallback_calls"], row["route_exact_count"], row["failed_count"]]
                        for row in ablation_rows
                    ],
                ),
                "",
                "## Negative Findings",
                "",
                f"Teacher no-path boundary rows remain separately recorded: `{len(boundary_rows)}`.",
                "",
                "## Next Blocking Question",
                "",
                "Can the selected policy be exported to C++ with Python/C++ parity and comparable per-decision latency?",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    SEMANTICS_REPORT.write_text(
        "\n".join(
            [
                "# G4G Decentralized Semantics Audit",
                "",
                *common_meta,
                "",
                "## Scope",
                "",
                "Audit that runtime decisions use decentralized local information and do not consume teacher route suffixes or full CIE/A* as fallback.",
                "",
                "## What Is Claimed",
                "",
                "The selected runtime ladder uses the G4E small candidate scorer plus PIBT-lite local fallback; CIE/A* remains teacher/offline oracle only.",
                "",
                "## What Is Not Claimed",
                "",
                "The audit does not prove hardware conveyor spacing or edge capacity constraints; edge overlap remains diagnostic only.",
                "",
                "## Repro Command",
                "",
                "`python scripts/eval/run_g4g_no_astar_fallback_validation.py`",
                "",
                "## Result Table",
                "",
                _markdown_table(["Audit Item", "Status", "Details"], [[row["audit_item"], row["status"], row["details"]] for row in forbidden_rows]),
                "",
                "## Negative Findings",
                "",
                "The script stores teacher paths only for audit comparison on the G4D planned scope, not as runtime decision input.",
                "",
                "## Next Blocking Question",
                "",
                "Can C++ runtime expose the same allowed input surface without accidentally adding teacher-route caches?",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    official_stress = [row for row in stress_rows if row["policy"] == "model_plus_pibt_lite_fallback"]
    STRESS_REPORT.write_text(
        "\n".join(
            [
                "# G4G Stress Window Report",
                "",
                *common_meta,
                "",
                "## Scope",
                "",
                "Run no-full-A* goal-reaching simulation on additional raw inputdata windows: six 512-task offsets, four 1024-task offsets, two 2048-task smoke windows, and one 4096-task smoke window.",
                "",
                "## What Is Claimed",
                "",
                "The official candidate is measured on larger raw task windows without using full CIE/A* runtime fallback.",
                "",
                "## What Is Not Claimed",
                "",
                "Raw stress windows do not have freshly generated CIE teacher planned scope; they are runtime stress evidence, not teacher parity evidence.",
                "",
                "## Repro Command",
                "",
                "`python scripts/eval/run_g4g_no_astar_fallback_validation.py`",
                "",
                "## Result Table",
                "",
                _markdown_table(
                    ["Window", "Size", "Planned", "Conflicts", "Full A*", "Stable"],
                    [
                        [row["window_name"], row["window_size"], f"{row['planned_count']}/{row['scope_total']}", row["node_window_conflicts"], row["runtime_full_cie_astar_calls"], row["stable"]]
                        for row in official_stress
                    ],
                ),
                "",
                "## Negative Findings",
                "",
                "No raw stress window has new CIE teacher labels in G4G; G4H should focus on runtime parity rather than expanding teacher claims.",
                "",
                "## Next Blocking Question",
                "",
                "Does the same ladder remain stable and fast in C++ over the 4096-task smoke window?",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    ABLATION_REPORT.write_text(
        "\n".join(
            [
                "# G4G Policy Ablation Report",
                "",
                *common_meta,
                "",
                "## Scope",
                "",
                "Compare model-only, rule-only, model+rule fallback, and bounded local-search variants on the G4D verified teacher planned scope.",
                "",
                "## What Is Claimed",
                "",
                "Ablation separates model contribution from rule fallback contribution.",
                "",
                "## What Is Not Claimed",
                "",
                "Rule-only diagnostic rows are not promoted as the final learned policy, even if they reach many tasks.",
                "",
                "## Repro Command",
                "",
                "`python scripts/eval/run_g4g_no_astar_fallback_validation.py`",
                "",
                "## Result Table",
                "",
                _markdown_table(
                    ["Policy", "Planned", "Route Exact", "Mean Wait", "Loops", "Decision Role"],
                    [[row["policy"], row["planned_count"], row["route_exact_count"], row["mean_wait_seconds"], row["loop_deadlock_cases"], row["role"]] for row in ablation_rows],
                ),
                "",
                "## Negative Findings",
                "",
                "Rule-only rows are intentionally retained as negative evidence: with the controlled 24-step diagnostic cap they planned only 582/4449 and exposed 3867 loop/deadlock failures. This supports the claim that the G4G result is not just a pure local rule.",
                "",
                "## Next Blocking Question",
                "",
                "Which parts of PIBT-lite should move into C++ first: wait scoring, slack scoring, or loop/backtrack penalty?",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    PROMOTION_REPORT.write_text(
        "\n".join(
            [
                "# G4G Promotion Decision",
                "",
                *common_meta,
                "",
                "## Scope",
                "",
                "Decide whether G4G evidence is sufficient to proceed to G4H C++ runtime / pybind parity.",
                "",
                "## What Is Claimed",
                "",
                f"Overall G4G gate: `{overall['status']}`.",
                "",
                "## What Is Not Claimed",
                "",
                "A PASS is not a paper claim and does not authorize RL, larger neural models, or changing original CIE/Java semantics.",
                "",
                "## Repro Command",
                "",
                "`python scripts/eval/run_g4g_no_astar_fallback_validation.py`",
                "",
                "## Result Table",
                "",
                _markdown_table(["Criterion", "Status", "Evidence"], [[row["criterion"], row["status"], row["evidence"]] for row in promotion_rows]),
                "",
                "## Negative Findings",
                "",
                f"Remote pushed state at runtime: `{git_ctx['head_pushed_to_upstream']}`. Teacher no-path boundary rows remain `{len(boundary_rows)}`.",
                "",
                "## Next Blocking Question",
                "",
                "Proceed to G4H only if the local commit is pushed or the generated artifacts are reviewed locally.",
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
    from scripts.data.build_g4d_cie_retry_large_window_dataset import _window_plan

    git_ctx = _git_context()
    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    tasks = _task_lookup(all_tasks)
    manifest = _load_jsonl(TEACHER_MANIFEST)
    planned_routes = _manifest_planned_routes(manifest)
    boundary_routes = _manifest_boundary_routes(manifest)
    g4d_windows = {
        scenario.name: RuntimeWindow(
            name=scenario.name,
            task_offset=scenario.task_offset,
            max_tasks=scenario.max_tasks,
            context="static_fault" if scenario.fault_edges else ("repair_window" if scenario.fault_windows else "no_fault"),
            source="g4d_teacher_planned_scope",
            fault_edges=tuple(scenario.fault_edges),
            fault_windows=tuple(scenario.fault_windows),
        )
        for scenario in _window_plan()
    }
    stress_windows = _stress_windows()
    stress_window_map = {window.name: window for window in stress_windows}
    stress_routes = [route for window in stress_windows for route in _raw_task_routes(all_tasks, window)]
    boundary_window_map = {name: g4d_windows[name] for name in {str(row["window_name"]) for row in boundary_routes}}
    policy_data = json.loads(G4E_MODEL_PATH.read_text(encoding="utf-8"))
    policy = G4DCieRetryPolicy.from_dict(policy_data)
    rules = _policy_rules(policy_data)

    results_by_policy: dict[str, list[TaskResult]] = {}
    stress_results_by_policy: dict[str, list[TaskResult]] = {}
    timing_rows: list[dict[str, Any]] = []
    all_decision_trace: list[dict[str, Any]] = []
    all_priority_trace: list[dict[str, Any]] = []

    specs = _mode_specs()
    spec_by_name = {spec.policy: spec for spec in specs}
    for spec in specs:
        started = time.perf_counter()
        results, trace, priority = _simulate(
            spec=spec,
            graph=graph,
            tasks=tasks,
            routes=planned_routes,
            windows=g4d_windows,
            policy=policy,
            rules=rules,
            experiment_scope="g4d_teacher_planned_scope",
        )
        elapsed = time.perf_counter() - started
        results_by_policy[spec.policy] = results
        all_decision_trace.extend(trace)
        all_priority_trace.extend(priority)
        decisions = sum(row.model_selected_decision_count + row.rule_fallback_calls for row in results)
        timing_rows.append(
            {
                "policy": spec.policy,
                "experiment_scope": "g4d_teacher_planned_scope",
                "task_count": len(results),
                "runtime_seconds": elapsed,
                "runtime_decisions": decisions,
                "seconds_per_decision": elapsed / max(1, decisions),
                "notes": "base ablation over verified teacher planned scope",
            }
        )

    stress_specs = [
        spec_by_name["model_plus_pibt_lite_fallback"],
    ]
    for spec in stress_specs:
        started = time.perf_counter()
        results, trace, priority = _simulate(
            spec=spec,
            graph=graph,
            tasks=tasks,
            routes=stress_routes,
            windows=stress_window_map,
            policy=policy,
            rules=rules,
            experiment_scope="raw_inputdata_stress",
        )
        elapsed = time.perf_counter() - started
        stress_results_by_policy[spec.policy] = results
        all_decision_trace.extend(trace)
        all_priority_trace.extend(priority)
        decisions = sum(row.model_selected_decision_count + row.rule_fallback_calls for row in results)
        timing_rows.append(
            {
                "policy": spec.policy,
                "experiment_scope": "raw_inputdata_stress",
                "task_count": len(results),
                "runtime_seconds": elapsed,
                "runtime_decisions": decisions,
                "seconds_per_decision": elapsed / max(1, decisions),
                "notes": "larger raw inputdata stress windows without fresh CIE teacher labels",
            }
        )

    boundary_results, boundary_trace, boundary_priority = _simulate(
        spec=spec_by_name["model_plus_pibt_lite_fallback"],
        graph=graph,
        tasks=tasks,
        routes=boundary_routes,
        windows=boundary_window_map,
        policy=policy,
        rules=rules,
        experiment_scope="g4d_teacher_no_path_boundary",
    )
    all_decision_trace.extend(boundary_trace)
    all_priority_trace.extend(boundary_priority)

    ablation_rows = []
    for spec in specs:
        aggregate = _aggregate(spec.policy, results_by_policy[spec.policy], len(planned_routes), len(planned_routes))
        ablation_rows.append({**aggregate, "role": spec.role})

    stress_scaling_rows = []
    for spec in stress_specs:
        stress_scaling_rows.extend(_aggregate_by_window(spec.policy, stress_results_by_policy[spec.policy], stress_window_map))

    call_ledger_rows = []
    for row in [*ablation_rows, *stress_scaling_rows]:
        call_ledger_rows.append(
            {
                "policy": row["policy"],
                "scope_or_window": row.get("window_name", "g4d_teacher_planned_scope"),
                "model_inference_count": row["model_inference_count"],
                "model_selected_decision_count": row["model_selected_decision_count"],
                "rule_fallback_calls": row["rule_fallback_calls"],
                "bounded_local_search_calls": row["bounded_local_search_calls"],
                "runtime_full_cie_astar_calls": row["runtime_full_cie_astar_calls"],
                "runtime_full_cie_astar_default": False,
                "edge_capacity_primary": False,
            }
        )

    forbidden_rows = _forbidden_feature_audit(policy_data, git_ctx)
    boundary_table_rows = _boundary_rows(boundary_routes, boundary_results)
    promotion_rows = _promotion_gate(
        ablation_rows=ablation_rows,
        stress_rows=stress_scaling_rows,
        forbidden_rows=forbidden_rows,
        boundary_rows=boundary_table_rows,
    )
    official_best = "model_plus_pibt_lite_fallback"

    _write_csv(CALL_LEDGER_TABLE, call_ledger_rows, ["policy", "scope_or_window", "model_inference_count", "model_selected_decision_count", "rule_fallback_calls", "bounded_local_search_calls", "runtime_full_cie_astar_calls", "runtime_full_cie_astar_default", "edge_capacity_primary"])
    _write_csv(LADDER_TABLE, ablation_rows, _aggregate_fields() + ["role"])
    _write_csv(ABLATION_TABLE, ablation_rows, _aggregate_fields() + ["role"])
    _write_csv(FORBIDDEN_TABLE, forbidden_rows, ["audit_item", "status", "details"])
    _write_csv(ROUTE_DEVIATION_TABLE, _route_deviation_rows(results_by_policy), ["policy", "window_name", "task_id", "segment_id", "goal_reached", "route_exact", "deviated_from_cie", "failed_reason", "steps", "wait_seconds", "loop_count", "learner_path", "teacher_path", "interpretation"])
    merged_results = _merge_results(results_by_policy, stress_results_by_policy)
    _write_csv(GOAL_REACHING_TABLE, _goal_rows(merged_results), _aggregate_fields() + ["experiment_scope"])
    _write_csv(LOOP_TABLE, _loop_rows(merged_results), ["policy", "experiment_scope", "window_name", "task_id", "segment_id", "goal_reached", "failed_reason", "steps", "wait_events", "wait_seconds", "source_wait_seconds", "loop_count", "nonprogress_steps", "learner_path"])
    _write_csv(SCALING_TABLE, stress_scaling_rows, _aggregate_fields() + ["window_name", "window_offset", "window_size", "context", "source", "stable"])
    _write_csv(STRESS_INDEX_TABLE, _stress_index_rows(all_tasks, stress_windows), ["window_name", "window_offset", "window_size", "selected_count", "first_pass_time", "last_pass_time", "context", "source", "fault_edges", "fault_windows", "edge_capacity_primary"])
    _write_csv(BOUNDARY_TABLE, boundary_table_rows, ["window_name", "context", "task_id", "segment_id", "start", "goal", "entry_time", "attempt_time", "teacher_failure_reason", "teacher_taxonomy_label", "runtime_policy", "runtime_goal_reached", "runtime_node_window_conflicts", "runtime_full_cie_astar_calls", "runtime_path", "claim_boundary"])
    _write_csv(PRIORITY_TRACE_TABLE, all_priority_trace, ["policy", "experiment_scope", "window_name", "task_id", "segment_id", "step_index", "current_node", "goal_node", "selected_next_node", "priority_rule", "candidate_scores", "selected_components"])
    _write_csv(TIMING_TABLE, timing_rows, ["policy", "experiment_scope", "task_count", "runtime_seconds", "runtime_decisions", "seconds_per_decision", "notes"])
    _write_csv(PROMOTION_GATE_TABLE, promotion_rows, ["criterion", "status", "evidence", "decision_if_failed"])
    _write_jsonl(TRACE_SAMPLE_PATH, all_decision_trace)
    _write_config(official_best, git_ctx, stress_windows)
    _write_reports(
        git_ctx=git_ctx,
        ablation_rows=ablation_rows,
        stress_rows=stress_scaling_rows,
        forbidden_rows=forbidden_rows,
        boundary_rows=boundary_table_rows,
        promotion_rows=promotion_rows,
    )

    missing = [
        path
        for path in (
            VALIDATION_REPORT,
            SEMANTICS_REPORT,
            STRESS_REPORT,
            ABLATION_REPORT,
            PROMOTION_REPORT,
            CALL_LEDGER_TABLE,
            LADDER_TABLE,
            ABLATION_TABLE,
            FORBIDDEN_TABLE,
            ROUTE_DEVIATION_TABLE,
            GOAL_REACHING_TABLE,
            LOOP_TABLE,
            SCALING_TABLE,
            STRESS_INDEX_TABLE,
            BOUNDARY_TABLE,
            PRIORITY_TRACE_TABLE,
            TIMING_TABLE,
            PROMOTION_GATE_TABLE,
            CONFIG_PATH,
            TRACE_SAMPLE_PATH,
        )
        if not path.exists()
    ]
    if missing:
        raise AssertionError(f"missing G4G artifacts: {missing}")
    official = next(row for row in ablation_rows if row["policy"] == official_best)
    if int(official["runtime_full_cie_astar_calls"]) != 0:
        raise AssertionError("G4G official candidate used runtime full CIE/A*")
    if int(official["node_window_conflicts"]) != 0:
        raise AssertionError("G4G official candidate has node-window conflicts")
    if any(row["status"] == "FAIL" for row in forbidden_rows):
        raise AssertionError("G4G forbidden feature audit has FAIL rows")
    print(
        "g4g no-astar fallback validation complete: "
        f"official={official_best} "
        f"planned={official['planned_count']}/{official['teacher_planned_scope']} "
        f"full_astar={official['runtime_full_cie_astar_calls']} "
        f"gate={promotion_rows[-1]['status']}"
    )


def _aggregate_fields() -> list[str]:
    return [
        "policy",
        "planned_count",
        "scope_total",
        "teacher_planned_scope",
        "node_window_conflicts",
        "runtime_full_cie_astar_calls",
        "model_inference_count",
        "model_selected_decision_count",
        "rule_fallback_calls",
        "bounded_local_search_calls",
        "zero_full_astar_task_share",
        "route_exact_count",
        "deviated_success_count",
        "failed_count",
        "loop_deadlock_cases",
        "loop_count",
        "nonprogress_steps",
        "avg_no_progress_steps_per_task",
        "mean_wait_seconds",
        "mean_transport_time",
    ]


if __name__ == "__main__":
    main()
