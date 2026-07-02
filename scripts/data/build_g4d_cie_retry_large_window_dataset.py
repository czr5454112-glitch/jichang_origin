from __future__ import annotations

from collections import Counter, defaultdict, deque
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
G4C_CLUSTER_PATH = ROOT / "outputs" / "tables" / "g4c_failure_cluster_summary.csv"

REPORT_PATH = ROOT / "outputs" / "reports" / "g4d_large_window_teacher_dataset_report.md"
WINDOW_INDEX_TABLE = ROOT / "outputs" / "tables" / "g4d_window_index.csv"
SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4d_large_window_teacher_summary.csv"
INTERFACE_TABLE = ROOT / "outputs" / "tables" / "g4d_interface_decision_slices.csv"
SOURCE_RETRY_TABLE = ROOT / "outputs" / "tables" / "g4d_source_retry_slices.csv"
LABEL_DISTRIBUTION_TABLE = ROOT / "outputs" / "tables" / "g4d_label_distribution.csv"
SCENARIO_COVERAGE_TABLE = ROOT / "outputs" / "tables" / "g4d_scenario_coverage.csv"
MANIFEST_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4d_large_window_teacher_manifest.jsonl"
SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4d_large_window_teacher_sample.jsonl"

RETRY_VARIANT_NAME = "java_retry_tick_1s_max_delay_60s"
MAX_SAMPLE_ROWS = 500


@dataclass(frozen=True)
class NodeTime:
    node: int
    t1: float
    t2: float


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _window_plan() -> list[Any]:
    from scripts.eval.run_g3k_cie_node_window_retry_audit import MatchedScenario

    return [
        MatchedScenario("g4d_first144_no_fault", 0, 144),
        MatchedScenario("g4d_first256_no_fault", 0, 256),
        MatchedScenario("g4d_first512_no_fault", 0, 512),
        MatchedScenario("g4d_first1024_no_fault", 0, 1024),
        MatchedScenario("g4d_offset512_512_high_density", 512, 512),
        MatchedScenario("g4d_offset2048_1024_high_density", 2048, 1024),
        MatchedScenario("g4d_offset64_static512", 64, 512, fault_edges=((16, 17),)),
        MatchedScenario("g4d_offset64_repair512", 64, 512, fault_windows=((28, 47, 0.0, 12000.0),)),
    ]


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


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]], limit: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            if limit is not None and index >= limit:
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


def _task_lookup(tasks: Iterable[Any]) -> dict[tuple[int, str], Any]:
    return {(int(task.task_id), str(task.segment_id)): task for task in tasks}


def _selected_tasks(all_tasks: tuple[Any, ...], scenario: Any) -> tuple[Any, ...]:
    return all_tasks[scenario.task_offset : scenario.task_offset + scenario.max_tasks]


def _context(scenario: Any) -> str:
    if scenario.fault_edges:
        return "static_fault"
    if scenario.fault_windows:
        return "repair_window"
    return "real_inputdata_window"


def _active_faults(scenario: Any, ready_time: float) -> set[tuple[int, int]]:
    active = set(scenario.fault_edges)
    for start, end, fault_start, repair_time in scenario.fault_windows:
        if fault_start <= ready_time < repair_time:
            active.add((start, end))
    return active


def _candidate_maps(graph: Any, scenario: Any, current: int, goal: int, ready_time: float) -> dict[str, Any]:
    candidates = list(graph.outgoing(current))
    active = _active_faults(scenario, ready_time)
    return {
        "candidate_next_nodes": candidates,
        "candidate_shortest_time_to_goal": {str(node): graph.heuristic(node, goal) for node in candidates},
        "candidate_travel_time": {str(node): graph.edge(current, node).travel_time for node in candidates},
        "candidate_service_time": {str(node): graph.service_time(node) for node in candidates},
        "candidate_node_type": {str(node): graph.node(node).node_type for node in candidates},
        "candidate_fault_status": {str(node): (current, node) in active for node in candidates},
    }


def _route_node_times(graph: Any, path: list[int], start_time: float) -> list[NodeTime]:
    output: list[NodeTime] = []
    current_t1 = start_time
    for index, node in enumerate(path):
        if index > 0:
            prev = path[index - 1]
            current_t1 = output[-1].t2 + graph.edge(prev, node).travel_time
        output.append(NodeTime(node=node, t1=current_t1, t2=current_t1 + graph.service_time(node)))
    return output


def _overlap_count(intervals: list[tuple[float, float]], start: float, end: float) -> int:
    return sum(1 for left, right in intervals if not (end < left or start > right))


def _hop_distance(graph: Any, start: int, goal: int, cache: dict[tuple[int, int], int]) -> int:
    key = (start, goal)
    if key in cache:
        return cache[key]
    if start == goal:
        cache[key] = 0
        return 0
    queue: deque[tuple[int, int]] = deque([(start, 0)])
    seen = {start}
    while queue:
        node, depth = queue.popleft()
        for nxt in graph.outgoing(node):
            if nxt == goal:
                cache[key] = depth + 1
                return depth + 1
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, depth + 1))
    cache[key] = 999
    return 999


def _downstream_pressure(
    graph: Any,
    reservations: dict[int, list[tuple[float, float]]],
    candidate: int,
    goal: int,
    arrival_time: float,
    depth: int,
) -> int:
    if depth <= 0:
        return 0
    service_end = arrival_time + graph.service_time(candidate)
    total = _overlap_count(reservations[candidate], arrival_time, service_end)
    if candidate == goal:
        return total
    for nxt in graph.outgoing(candidate):
        edge = graph.edge(candidate, nxt)
        nxt_arrival = service_end + edge.travel_time
        total += _downstream_pressure(graph, reservations, nxt, goal, nxt_arrival, depth - 1)
    return total


def _enhanced_features(
    graph: Any,
    scenario: Any,
    current: int,
    goal: int,
    ready_time: float,
    candidates: list[int],
    reservations: dict[int, list[tuple[float, float]]],
    risk_map: dict[tuple[int, tuple[int, ...]], set[int]],
    hop_cache: dict[tuple[int, int], int],
) -> dict[str, dict[str, float]]:
    static_cost = {
        node: float(graph.edge(current, node).travel_time) + float(graph.heuristic(node, goal))
        for node in candidates
    }
    best_cost = min(static_cost.values()) if static_cost else 0.0
    current_heuristic = float(graph.heuristic(current, goal))
    risky_candidates = risk_map.get((current, tuple(candidates)), set())
    output = {
        "candidate_downstream_node_pressure_2hop": {},
        "candidate_downstream_node_pressure_3hop": {},
        "candidate_static_remaining_hops_to_goal": {},
        "candidate_static_second_best_gap": {},
        "candidate_bottleneck_score": {},
        "candidate_goal_direction_score": {},
        "candidate_historical_risk_from_training_only": {},
    }
    active = _active_faults(scenario, ready_time)
    for node in candidates:
        arrival = ready_time + graph.edge(current, node).travel_time
        out_degree = len(list(graph.outgoing(node)))
        bottleneck = max(0.0, 2.0 - float(out_degree))
        if (current, node) in active:
            bottleneck += 5.0
        key = str(node)
        output["candidate_downstream_node_pressure_2hop"][key] = float(
            _downstream_pressure(graph, reservations, node, goal, arrival, 2)
        )
        output["candidate_downstream_node_pressure_3hop"][key] = float(
            _downstream_pressure(graph, reservations, node, goal, arrival, 3)
        )
        output["candidate_static_remaining_hops_to_goal"][key] = float(_hop_distance(graph, node, goal, hop_cache))
        output["candidate_static_second_best_gap"][key] = float(static_cost[node] - best_cost)
        output["candidate_bottleneck_score"][key] = bottleneck
        output["candidate_goal_direction_score"][key] = current_heuristic - float(graph.heuristic(node, goal))
        output["candidate_historical_risk_from_training_only"][key] = 1.0 if node in risky_candidates else 0.0
    return output


def _risk_map_from_g4c() -> dict[tuple[int, tuple[int, ...]], set[int]]:
    output: dict[tuple[int, tuple[int, ...]], set[int]] = defaultdict(set)
    for row in _read_csv(G4C_CLUSTER_PATH):
        candidates = tuple(int(value) for value in json.loads(row["candidate_set"]))
        output[(int(row["current_node"]), candidates)].add(int(row["predicted_next_node"]))
    return output


def _split_for(segment_id: str) -> str:
    checksum = sum(ord(ch) for ch in segment_id)
    bucket = checksum % 10
    if bucket <= 6:
        return "train"
    if bucket <= 8:
        return "val"
    return "test"


def _build_window_rows(
    graph: Any,
    tasks: dict[tuple[int, str], Any],
    scenario: Any,
    events: list[dict[str, Any]],
    risk_map: dict[tuple[int, tuple[int, ...]], set[int]],
    route_row_start: int,
    sample_start: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    reservations: dict[int, list[tuple[float, float]]] = defaultdict(list)
    hop_cache: dict[tuple[int, int], int] = {}
    interface_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    planned_events = [event for event in events if event.get("event") == "planned"]
    ordered_events = sorted(planned_events, key=lambda row: (float(row["attempt_time"]), int(row["task_id"]), str(row["segment_id"])))
    sample_index = sample_start
    for route_offset, event in enumerate(ordered_events):
        task = tasks[(int(event["task_id"]), str(event["segment_id"]))]
        path = [int(node) for node in event["path"]]
        node_times = _route_node_times(graph, path, float(event["attempt_time"]))
        route_row_index = route_row_start + route_offset
        manifest_rows.append(
            {
                "record_type": "planned_route",
                "window_name": scenario.name,
                "context": _context(scenario),
                "window_offset": scenario.task_offset,
                "window_size": scenario.max_tasks,
                "segment_id": event["segment_id"],
                "task_id": int(event["task_id"]),
                "start": int(event["start"]),
                "goal": int(event["goal"]),
                "entry_time": float(event["entry_time"]),
                "attempt_time": float(event["attempt_time"]),
                "attempts": int(event["attempts"]),
                "finish_time": float(event["finish_time"]),
                "route_path": path,
                "taxonomy_label": event["taxonomy_label"],
                "edge_capacity_primary": False,
                "teacher_route_source": "verified_cie_astar_retry",
            }
        )
        if int(event["attempts"]) > 1:
            source_rows.append(_source_retry_row(graph, scenario, task, event, sample_index))
            sample_index += 1
        for decision_index, (current_time, next_time) in enumerate(zip(node_times, node_times[1:])):
            current = int(current_time.node)
            teacher_next = int(next_time.node)
            ready_time = float(current_time.t2)
            candidates = _candidate_maps(graph, scenario, current, int(event["goal"]), ready_time)
            candidate_next_nodes = candidates["candidate_next_nodes"]
            if teacher_next not in candidate_next_nodes:
                raise AssertionError(f"teacher next {teacher_next} missing from candidates at {current}")
            current_pressure = _overlap_count(reservations[current], current_time.t1, current_time.t2)
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
                goal=int(event["goal"]),
                ready_time=ready_time,
                candidates=candidate_next_nodes,
                reservations=reservations,
                risk_map=risk_map,
                hop_cache=hop_cache,
            )
            row = {
                "sample_id": f"g4d_move_{sample_index:07d}",
                "window_name": scenario.name,
                "scenario": scenario.name,
                "context": _context(scenario),
                "window_offset": scenario.task_offset,
                "window_size": scenario.max_tasks,
                "task_id": int(event["task_id"]),
                "segment_id": event["segment_id"],
                "decision_index": decision_index,
                "current_node": current,
                "goal_node": int(event["goal"]),
                "candidate_next_nodes": candidate_next_nodes,
                "teacher_next_node": teacher_next,
                "is_branch_node": len(candidate_next_nodes) > 1,
                "is_source_retry": False,
                "current_time": ready_time,
                "task_entry_time": float(event["entry_time"]),
                "deadline_or_std": float(task.std),
                "time_slack": float(task.std) - ready_time,
                "candidate_shortest_time_to_goal": candidates["candidate_shortest_time_to_goal"],
                "candidate_travel_time": candidates["candidate_travel_time"],
                "candidate_service_time": candidates["candidate_service_time"],
                "candidate_node_type": candidates["candidate_node_type"],
                "candidate_fault_status": candidates["candidate_fault_status"],
                "local_node_time_window_pressure": current_pressure,
                "local_queue_or_occupancy_summary": {
                    "current_node_pressure": current_pressure,
                    "candidate_node_pressure": candidate_pressures,
                    "out_degree": len(candidate_next_nodes),
                },
                "g4d_enhanced_features": enhanced,
                "source_retry_age_seconds": max(0.0, float(event["attempt_time"]) - float(event["entry_time"])),
                "source_retry_pressure": max(0, int(event["attempts"]) - 1),
                "unfinished_task_queue_size_near_current_source": max(0, int(event["attempts"]) - 1),
                "label_type": "MOVE_TO_NEXT_CIE",
                "split": _split_for(str(event["segment_id"])),
                "route_row_index": route_row_index,
                "edge_capacity_primary": False,
            }
            interface_rows.append(row)
            sample_index += 1
        for item in node_times:
            reservations[item.node].append((item.t1, item.t2))

    for event in events:
        if event.get("event") == "unplanned":
            manifest_rows.append(
                {
                    "record_type": "unplanned_after_retry",
                    "window_name": scenario.name,
                    "context": _context(scenario),
                    "window_offset": scenario.task_offset,
                    "window_size": scenario.max_tasks,
                    "segment_id": event["segment_id"],
                    "task_id": int(event["task_id"]),
                    "start": int(event["start"]),
                    "goal": int(event["goal"]),
                    "entry_time": float(event["entry_time"]),
                    "attempt_time": float(event["attempt_time"]),
                    "failure_reason": event.get("reason", ""),
                    "taxonomy_label": "CIE_NO_PATH_AFTER_RETRY",
                    "edge_capacity_primary": False,
                    "teacher_route_source": "verified_cie_astar_retry",
                }
            )
    return interface_rows, source_rows, manifest_rows


def _source_retry_row(graph: Any, scenario: Any, task: Any, event: dict[str, Any], sample_index: int) -> dict[str, Any]:
    first_time = float(event["entry_time"])
    candidates = _candidate_maps(graph, scenario, int(task.start), int(task.goal), first_time)
    return {
        "sample_id": f"g4d_source_retry_{sample_index:07d}",
        "window_name": scenario.name,
        "scenario": scenario.name,
        "context": _context(scenario),
        "window_offset": scenario.task_offset,
        "window_size": scenario.max_tasks,
        "task_id": int(task.task_id),
        "segment_id": task.segment_id,
        "decision_index": -1,
        "current_node": int(task.start),
        "goal_node": int(task.goal),
        "candidate_next_nodes": candidates["candidate_next_nodes"],
        "teacher_next_node": "",
        "is_branch_node": len(candidates["candidate_next_nodes"]) > 1,
        "is_source_retry": True,
        "current_time": first_time,
        "task_entry_time": float(task.pass_time),
        "deadline_or_std": float(task.std),
        "time_slack": float(task.std) - first_time,
        "candidate_shortest_time_to_goal": candidates["candidate_shortest_time_to_goal"],
        "candidate_travel_time": candidates["candidate_travel_time"],
        "candidate_service_time": candidates["candidate_service_time"],
        "candidate_node_type": candidates["candidate_node_type"],
        "candidate_fault_status": candidates["candidate_fault_status"],
        "local_node_time_window_pressure": 0,
        "local_queue_or_occupancy_summary": {"out_degree": len(candidates["candidate_next_nodes"])},
        "g4d_enhanced_features": {},
        "source_retry_age_seconds": max(0.0, float(event["attempt_time"]) - float(event["entry_time"])),
        "source_retry_pressure": max(0, int(event["attempts"]) - 1),
        "unfinished_task_queue_size_near_current_source": max(0, int(event["attempts"]) - 1),
        "label_type": "WAIT_AT_SOURCE_RETRY",
        "split": _split_for(str(task.segment_id)),
        "route_row_index": "",
        "edge_capacity_primary": False,
    }


def _window_index_rows(all_tasks: tuple[Any, ...], windows: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for scenario in windows:
        selected = _selected_tasks(all_tasks, scenario)
        rows.append(
            {
                "window_name": scenario.name,
                "window_offset": scenario.task_offset,
                "window_size": scenario.max_tasks,
                "selected_count": len(selected),
                "first_pass_time": min(task.pass_time for task in selected),
                "last_pass_time": max(task.pass_time for task in selected),
                "context": _context(scenario),
                "fault_edges": [list(edge) for edge in scenario.fault_edges],
                "fault_windows": [list(window) for window in scenario.fault_windows],
                "edge_capacity_primary": False,
            }
        )
    return rows


def _label_rows(interface_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]], manifest_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["label_type"] for row in interface_rows)
    counts.update(row["label_type"] for row in source_rows)
    counts.update(row["taxonomy_label"] for row in manifest_rows if row["record_type"] == "unplanned_after_retry")
    return [{"label_type": key, "count": value} for key, value in sorted(counts.items())]


def _coverage_rows(summary_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_context: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in summary_rows:
        by_context[str(row["context"])].append(row)
    output: list[dict[str, Any]] = []
    for context, rows in sorted(by_context.items()):
        output.append(
            {
                "context": context,
                "window_count": len(rows),
                "task_count": sum(int(row["max_tasks"]) for row in rows),
                "planned": sum(int(row["planned"]) for row in rows),
                "unplanned": sum(int(row["unplanned"]) for row in rows),
                "node_window_conflicts": sum(int(row["node_window_conflicts"]) for row in rows),
            }
        )
    return output


def _write_report(
    summary_rows: list[dict[str, Any]],
    interface_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
) -> None:
    total_tasks = sum(int(row["max_tasks"]) for row in summary_rows)
    planned = sum(int(row["planned"]) for row in summary_rows)
    conflicts = sum(int(row["node_window_conflicts"]) for row in summary_rows)
    attempts = sum(int(row["total_retry_attempts"]) for row in summary_rows)
    negative = [row for row in summary_rows if int(row["unplanned"]) > 0]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4D Large-Window CIE Retry Teacher Dataset Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "G4D-A expands the verified G3k CIE/A* retry teacher to larger real inputdata windows. It does not use RL, GNN, Transformer models, or `edge_capacity=1` as a primary constraint. Edge overlap remains diagnostic only.",
        "",
        "## Window Summary",
        "",
        _markdown_table(
            ["Window", "Tasks", "Planned", "Conflicts", "A* attempts", "Context"],
            [
                [
                    row["scenario"],
                    row["max_tasks"],
                    row["planned"],
                    row["node_window_conflicts"],
                    row["total_retry_attempts"],
                    row["context"],
                ]
                for row in summary_rows
            ],
        ),
        "",
        "## Aggregate",
        "",
        f"- Total window tasks: `{total_tasks}`",
        f"- Planned by verified teacher: `{planned}/{total_tasks}`",
        f"- Node-window conflicts: `{conflicts}`",
        f"- Estimated original CIE retry A* attempts: `{attempts}`",
        f"- MOVE interface slices: `{len(interface_rows)}`",
        f"- Source retry slices: `{len(source_rows)}`",
        f"- Manifest rows, including negative outcomes: `{len(manifest_rows)}`",
        "",
        "## Negative Results",
        "",
        (
            _markdown_table(
                ["Window", "Unplanned", "Decision"],
                [[row["scenario"], row["unplanned"], "preserve_negative_inventory"] for row in negative],
            )
            if negative
            else "No unplanned large-window teacher rows in this pass."
        ),
        "",
        "## Decision",
        "",
        "G4D-A is usable for the downstream audit and small-model pass because all windows keep node-window conflicts at `0` and `edge_capacity=1` stays non-primary. The `g4d_offset2048_1024_high_density` window remains a negative teacher-capacity result under the recommended 60s retry horizon and must not be hidden.",
        "",
        "## Artifacts",
        "",
        f"- Window index: `{_relative(WINDOW_INDEX_TABLE)}`",
        f"- Teacher summary: `{_relative(SUMMARY_TABLE)}`",
        f"- Interface slices: `{_relative(INTERFACE_TABLE)}`",
        f"- Source retry slices: `{_relative(SOURCE_RETRY_TABLE)}`",
        f"- Full manifest: `{_relative(MANIFEST_PATH)}`",
        f"- Sample manifest: `{_relative(SAMPLE_PATH)}`",
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


def _interface_fields() -> list[str]:
    return [
        "sample_id",
        "window_name",
        "scenario",
        "context",
        "window_offset",
        "window_size",
        "task_id",
        "segment_id",
        "decision_index",
        "current_node",
        "goal_node",
        "candidate_next_nodes",
        "teacher_next_node",
        "is_branch_node",
        "is_source_retry",
        "current_time",
        "task_entry_time",
        "deadline_or_std",
        "time_slack",
        "candidate_shortest_time_to_goal",
        "candidate_travel_time",
        "candidate_service_time",
        "candidate_node_type",
        "candidate_fault_status",
        "local_node_time_window_pressure",
        "local_queue_or_occupancy_summary",
        "g4d_enhanced_features",
        "source_retry_age_seconds",
        "source_retry_pressure",
        "unfinished_task_queue_size_near_current_source",
        "label_type",
        "split",
        "route_row_index",
        "edge_capacity_primary",
    ]


def main() -> None:
    _prepare_imports()
    from scripts.eval.run_g3k_cie_node_window_retry_audit import RetryVariant, _run_retry_scenario
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    graph = IcsGraph.from_json(MAP_PATH)
    all_tasks = tuple(TaskStream.from_jsonl(TASK_PATH))
    tasks = _task_lookup(all_tasks)
    windows = _window_plan()
    variant = RetryVariant(RETRY_VARIANT_NAME, 1.0, 60.0)
    risk_map = _risk_map_from_g4c()

    summary_rows: list[dict[str, Any]] = []
    interface_rows: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    sample_index = 0
    route_row_index = 0
    for scenario in windows:
        summary, _timeline, _recovered, _remaining, events, _edge_rows = _run_retry_scenario(
            graph,
            all_tasks,
            scenario,
            variant,
            set(),
        )
        summary_rows.append(summary)
        window_interface, window_source, window_manifest = _build_window_rows(
            graph=graph,
            tasks=tasks,
            scenario=scenario,
            events=events,
            risk_map=risk_map,
            route_row_start=route_row_index,
            sample_start=sample_index,
        )
        route_row_index += int(summary["planned"])
        sample_index += len(window_interface) + len(window_source)
        interface_rows.extend(window_interface)
        source_rows.extend(window_source)
        manifest_rows.extend(window_manifest)

    _write_csv(WINDOW_INDEX_TABLE, _window_index_rows(all_tasks, windows), ["window_name", "window_offset", "window_size", "selected_count", "first_pass_time", "last_pass_time", "context", "fault_edges", "fault_windows", "edge_capacity_primary"])
    _write_csv(SUMMARY_TABLE, summary_rows, ["variant", "scenario", "context", "tick_seconds", "max_retry_delay_seconds", "max_tasks", "planned", "unplanned", "node_window_conflicts", "diagnostic_edge_overlap_only", "diagnostic_merge_overlap_only", "edge_capacity_model", "edge_overlap_counted_as_primary", "legacy_path_match_count", "legacy_path_mismatch_count", "inserted_wait_task_count", "g3j_no_path_recovered_count", "g3j_no_path_remaining_count", "total_retry_attempts", "g3j_retry_attempts", "mean_recovery_delay_seconds", "max_recovery_delay_seconds", "g4a_pilot_candidate", "decision", "teacher_route_source"])
    _write_csv(INTERFACE_TABLE, interface_rows, _interface_fields())
    _write_csv(SOURCE_RETRY_TABLE, source_rows, _interface_fields())
    _write_csv(LABEL_DISTRIBUTION_TABLE, _label_rows(interface_rows, source_rows, manifest_rows), ["label_type", "count"])
    _write_csv(SCENARIO_COVERAGE_TABLE, _coverage_rows(summary_rows), ["context", "window_count", "task_count", "planned", "unplanned", "node_window_conflicts"])
    _write_jsonl(MANIFEST_PATH, manifest_rows)
    _write_jsonl(SAMPLE_PATH, manifest_rows, limit=MAX_SAMPLE_ROWS)
    _write_report(summary_rows, interface_rows, source_rows, manifest_rows)

    if any(str(row["edge_overlap_counted_as_primary"]) == "True" for row in summary_rows):
        raise AssertionError("edge overlap was counted as primary")
    if sum(int(row["node_window_conflicts"]) for row in summary_rows) != 0:
        raise AssertionError("G4D large-window teacher has node-window conflicts")
    if max(int(row["max_tasks"]) for row in summary_rows) < 1024:
        raise AssertionError("G4D must include at least one 1024-task smoke window")
    missing = [path for path in (REPORT_PATH, WINDOW_INDEX_TABLE, SUMMARY_TABLE, INTERFACE_TABLE, MANIFEST_PATH, SAMPLE_PATH) if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4D teacher artifacts: {missing}")
    total_tasks = sum(int(row["max_tasks"]) for row in summary_rows)
    total_planned = sum(int(row["planned"]) for row in summary_rows)
    print(
        "g4d teacher dataset complete: "
        f"windows={len(summary_rows)} planned={total_planned}/{total_tasks} "
        f"interface_rows={len(interface_rows)} source_retry_rows={len(source_rows)}"
    )


if __name__ == "__main__":
    main()
