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
G3K_SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g3k_cie_retry_teacher_sample.jsonl"
G3K_SUMMARY_PATH = ROOT / "outputs" / "tables" / "g3k_retry_summary.csv"
G3K_RECOVERED_PATH = ROOT / "outputs" / "tables" / "g3k_recovered_no_path_cases.csv"

REPORT_PATH = ROOT / "outputs" / "reports" / "g4a_cie_retry_teacher_dataset_report.md"
SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4a_teacher_dataset_summary.csv"
INTERFACE_TABLE = ROOT / "outputs" / "tables" / "g4a_interface_decision_slices.csv"
SOURCE_RETRY_TABLE = ROOT / "outputs" / "tables" / "g4a_source_retry_slices.csv"
CANDIDATE_SCHEMA_TABLE = ROOT / "outputs" / "tables" / "g4a_candidate_feature_schema.csv"
FORBIDDEN_AUDIT_TABLE = ROOT / "outputs" / "tables" / "g4a_forbidden_feature_audit.csv"
BRANCH_COVERAGE_TABLE = ROOT / "outputs" / "tables" / "g4a_branch_node_coverage.csv"
SCENARIO_COVERAGE_TABLE = ROOT / "outputs" / "tables" / "g4a_scenario_coverage.csv"
LABEL_DISTRIBUTION_TABLE = ROOT / "outputs" / "tables" / "g4a_label_distribution.csv"
TEACHER_REPLAY_PARITY_TABLE = ROOT / "outputs" / "tables" / "g4a_teacher_replay_parity.csv"
SPLIT_TABLE = ROOT / "outputs" / "tables" / "g4a_train_val_test_split.csv"
DATASET_GATE_TABLE = ROOT / "outputs" / "tables" / "g4a_dataset_gate.csv"
SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4a_cie_retry_junction_teacher_sample.jsonl"

RECOMMENDED_G3K_VARIANT = "java_retry_tick_1s_max_delay_60s"
EXPECTED_PLANNED = 144
EXPECTED_SOURCE_RETRY = 17
MAX_JSONL_SAMPLE_ROWS = 500

MODEL_INPUT_FEATURES = (
    "current_node",
    "goal_node",
    "candidate_next_nodes",
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
    "source_retry_age_seconds",
)


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    context: str
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[tuple[int, int, float, float], ...] = ()


@dataclass(frozen=True)
class NodeTime:
    node: int
    t1: float
    t2: float


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT / "src"))


def _scenario_configs() -> dict[str, ScenarioConfig]:
    return {
        "legacy_first16": ScenarioConfig("legacy_first16", "no_fault"),
        "legacy_first16_buffer2": ScenarioConfig("legacy_first16_buffer2", "buffer_capacity"),
        "legacy_first32": ScenarioConfig("legacy_first32", "no_fault"),
        "legacy_offset32_static16": ScenarioConfig("legacy_offset32_static16", "static_fault", fault_edges=((16, 17),)),
        "legacy_offset64_repair32": ScenarioConfig(
            "legacy_offset64_repair32",
            "repair_window",
            fault_windows=((28, 47, 0.0, 12000.0),),
        ),
        "legacy_offset64_merge32": ScenarioConfig("legacy_offset64_merge32", "merge_window"),
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _task_lookup(tasks: Iterable[Any]) -> dict[tuple[int, str], Any]:
    return {(int(task.task_id), str(task.segment_id)): task for task in tasks}


def _route_node_times(graph: Any, path: list[int], start_time: float) -> list[NodeTime]:
    output: list[NodeTime] = []
    current_t1 = start_time
    for index, node in enumerate(path):
        if index > 0:
            prev = path[index - 1]
            current_t1 = output[-1].t2 + graph.edge(prev, node).travel_time
        output.append(NodeTime(node=node, t1=current_t1, t2=current_t1 + graph.service_time(node)))
    return output


def _active_faults(config: ScenarioConfig, ready_time: float) -> set[tuple[int, int]]:
    active = set(config.fault_edges)
    for start, end, fault_start, repair_time in config.fault_windows:
        if fault_start <= ready_time < repair_time:
            active.add((start, end))
    return active


def _overlap_count(intervals: list[tuple[float, float]], start: float, end: float) -> int:
    return sum(1 for left, right in intervals if not (end < left or start > right))


def _candidate_maps(graph: Any, current: int, goal: int, ready_time: float, config: ScenarioConfig) -> dict[str, Any]:
    candidates = list(graph.outgoing(current))
    active_faults = _active_faults(config, ready_time)
    return {
        "candidate_next_nodes": candidates,
        "candidate_shortest_time_to_goal": {str(node): graph.heuristic(node, goal) for node in candidates},
        "candidate_travel_time": {str(node): graph.edge(current, node).travel_time for node in candidates},
        "candidate_service_time": {str(node): graph.service_time(node) for node in candidates},
        "candidate_node_type": {str(node): graph.node(node).node_type for node in candidates},
        "candidate_fault_status": {str(node): (current, node) in active_faults for node in candidates},
    }


def _split_for(scenario: str, task_id: int) -> str:
    checksum = sum(ord(ch) for ch in f"{scenario}:{task_id}")
    bucket = checksum % 10
    if bucket <= 6:
        return "train"
    if bucket <= 8:
        return "val"
    return "test"


def _build_dataset(graph: Any, tasks: dict[tuple[int, str], Any], route_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    configs = _scenario_configs()
    reservations: dict[str, dict[int, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    interface_rows: list[dict[str, Any]] = []

    ordered_routes = sorted(
        route_rows,
        key=lambda row: (str(row["scenario"]), float(row["attempt_time"]), int(row["task_id"]), str(row["segment_id"])),
    )
    for route_index, route in enumerate(ordered_routes):
        scenario = str(route["scenario"])
        config = configs[scenario]
        task = tasks[(int(route["task_id"]), str(route["segment_id"]))]
        path = [int(node) for node in route["route_path"]]
        node_times = _route_node_times(graph, path, float(route["attempt_time"]))
        for decision_index, (current_time, next_time) in enumerate(zip(node_times, node_times[1:])):
            current = int(current_time.node)
            teacher_next = int(next_time.node)
            ready_time = float(current_time.t2)
            candidates = _candidate_maps(graph, current, int(route["goal"]), ready_time, config)
            candidate_next_nodes = candidates["candidate_next_nodes"]
            if teacher_next not in candidate_next_nodes:
                raise AssertionError(f"teacher next {teacher_next} missing from candidates at node {current}")
            current_pressure = _overlap_count(reservations[scenario][current], current_time.t1, current_time.t2)
            candidate_pressures = {
                str(node): _overlap_count(
                    reservations[scenario][node],
                    ready_time + graph.edge(current, node).travel_time,
                    ready_time + graph.edge(current, node).travel_time + graph.service_time(node),
                )
                for node in candidate_next_nodes
            }
            row = {
                "sample_id": f"g4a_move_{len(interface_rows):06d}",
                "scenario": scenario,
                "context": route["context"],
                "task_id": int(route["task_id"]),
                "segment_id": route["segment_id"],
                "decision_index": decision_index,
                "current_node": current,
                "goal_node": int(route["goal"]),
                "candidate_next_nodes": candidate_next_nodes,
                "teacher_next_node": teacher_next,
                "is_branch_node": len(candidate_next_nodes) > 1,
                "is_source_retry": False,
                "current_time": ready_time,
                "task_entry_time": float(route["entry_time"]),
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
                "source_retry_age_seconds": 0.0,
                "label_type": "MOVE_TO_NEXT_CIE",
                "split": _split_for(scenario, int(route["task_id"])),
                "route_row_index": route_index,
                "edge_capacity_primary": False,
            }
            interface_rows.append(row)
        for item in node_times:
            reservations[scenario][item.node].append((item.t1, item.t2))

    source_rows = _source_retry_rows(graph, tasks, configs)
    return interface_rows, source_rows


def _source_retry_rows(graph: Any, tasks: dict[tuple[int, str], Any], configs: dict[str, ScenarioConfig]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for recovered in _read_csv(G3K_RECOVERED_PATH):
        if recovered["variant"] != RECOMMENDED_G3K_VARIANT:
            continue
        scenario = recovered["scenario"]
        config = configs[scenario]
        task = tasks[(int(recovered["task_id"]), recovered["segment_id"])]
        current = int(recovered["start"])
        goal = int(recovered["goal"])
        first_no_path_time = float(recovered["first_no_path_time"])
        recovered_time = float(recovered["recovered_time"])
        candidates = _candidate_maps(graph, current, goal, first_no_path_time, config)
        rows.append(
            {
                "sample_id": f"g4a_source_retry_{len(rows):06d}",
                "scenario": scenario,
                "context": recovered["context"],
                "task_id": int(recovered["task_id"]),
                "segment_id": recovered["segment_id"],
                "decision_index": -1,
                "current_node": current,
                "goal_node": goal,
                "candidate_next_nodes": candidates["candidate_next_nodes"],
                "teacher_next_node": "",
                "is_branch_node": len(candidates["candidate_next_nodes"]) > 1,
                "is_source_retry": True,
                "current_time": first_no_path_time,
                "task_entry_time": float(task.pass_time),
                "deadline_or_std": float(task.std),
                "time_slack": float(task.std) - first_no_path_time,
                "candidate_shortest_time_to_goal": candidates["candidate_shortest_time_to_goal"],
                "candidate_travel_time": candidates["candidate_travel_time"],
                "candidate_service_time": candidates["candidate_service_time"],
                "candidate_node_type": candidates["candidate_node_type"],
                "candidate_fault_status": candidates["candidate_fault_status"],
                "local_node_time_window_pressure": "",
                "local_queue_or_occupancy_summary": {
                    "source_retry_attempts": int(recovered["attempts"]),
                    "retry_delay_seconds": recovered_time - float(task.pass_time),
                },
                "source_retry_age_seconds": max(0.0, first_no_path_time - float(task.pass_time)),
                "retry_delay_seconds": recovered_time - float(task.pass_time),
                "attempts": int(recovered["attempts"]),
                "label_type": "WAIT_AT_SOURCE_RETRY",
                "split": _split_for(scenario, int(recovered["task_id"])),
                "edge_capacity_primary": False,
                "root_cause": recovered["root_cause"],
            }
        )
    return rows


def _load_g3k_routes() -> list[dict[str, Any]]:
    rows = _load_jsonl(G3K_SAMPLE_PATH)
    output: list[dict[str, Any]] = []
    for row in rows:
        if row["variant"] != RECOMMENDED_G3K_VARIANT:
            continue
        if row["pre_route_label"] not in ("MOVE_TO_NEXT_CIE", "WAIT_AT_SOURCE_RETRY"):
            continue
        output.append(row)
    if len(output) != EXPECTED_PLANNED:
        raise AssertionError(f"expected {EXPECTED_PLANNED} G3k teacher routes, got {len(output)}")
    return output


def _summary_rows(interface_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]], gate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    route_count = len({(row["scenario"], row["segment_id"], row["task_id"]) for row in interface_rows})
    branch_count = sum(1 for row in interface_rows if row["is_branch_node"])
    return [
        {
            "metric": "g3k_variant",
            "value": RECOMMENDED_G3K_VARIANT,
            "notes": "G4A uses only the verified CIE retry variant.",
        },
        {"metric": "teacher_routes", "value": route_count, "notes": "Successful route-level G3k teacher rows."},
        {"metric": "interface_move_slices", "value": len(interface_rows), "notes": "One MOVE_TO_NEXT_CIE row per route edge."},
        {"metric": "source_retry_slices", "value": len(source_rows), "notes": "Recovered G3j no-path cases."},
        {"metric": "branch_node_slices", "value": branch_count, "notes": "Rows where the current node has more than one candidate outgoing edge."},
        {
            "metric": "dataset_gate",
            "value": "PASS" if all(row["pass"] for row in gate_rows) else "FAIL",
            "notes": "G4B may train only when this is PASS.",
        },
    ]


def _label_distribution_rows(interface_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row["label_type"] for row in [*interface_rows, *source_rows])
    for label in ("WAIT_AT_NODE_TIME_WINDOW", "ABSTAIN_TO_SAFE_FALLBACK", "CIE_NO_PATH_AFTER_RETRY"):
        counts.setdefault(label, 0)
    return [{"label_type": label, "count": count} for label, count in sorted(counts.items())]


def _branch_coverage_rows(graph: Any, interface_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in interface_rows:
        grouped[int(row["current_node"])].append(row)
    output: list[dict[str, Any]] = []
    for node, rows in sorted(grouped.items()):
        teacher_counts = Counter(str(row["teacher_next_node"]) for row in rows)
        output.append(
            {
                "current_node": node,
                "node_type": graph.node(node).node_type,
                "out_degree": len(graph.outgoing(node)),
                "is_branch_node": len(graph.outgoing(node)) > 1,
                "slice_count": len(rows),
                "teacher_next_distribution": json.dumps(dict(sorted(teacher_counts.items())), sort_keys=True),
            }
        )
    return output


def _scenario_coverage_rows(interface_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    scenarios = sorted({row["scenario"] for row in [*interface_rows, *source_rows]})
    for scenario in scenarios:
        move_rows = [row for row in interface_rows if row["scenario"] == scenario]
        wait_rows = [row for row in source_rows if row["scenario"] == scenario]
        contexts = sorted({str(row["context"]) for row in [*move_rows, *wait_rows]})
        tasks = {(row["task_id"], row["segment_id"]) for row in move_rows}
        output.append(
            {
                "scenario": scenario,
                "context": ";".join(contexts),
                "teacher_task_count": len(tasks),
                "move_slice_count": len(move_rows),
                "source_retry_slice_count": len(wait_rows),
                "branch_slice_count": sum(1 for row in move_rows if row["is_branch_node"]),
            }
        )
    return output


def _teacher_replay_parity_rows(interface_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    g3k_rows = [row for row in _read_csv(G3K_SUMMARY_PATH) if row["variant"] == RECOMMENDED_G3K_VARIANT]
    output: list[dict[str, Any]] = []
    for row in g3k_rows:
        scenario = row["scenario"]
        move_count = sum(1 for item in interface_rows if item["scenario"] == scenario) if scenario != "ALL" else len(interface_rows)
        output.append(
            {
                "variant": row["variant"],
                "scenario": scenario,
                "planned": row["planned"],
                "max_tasks": row["max_tasks"],
                "node_window_conflicts": row["node_window_conflicts"],
                "edge_capacity_model": row["edge_capacity_model"],
                "edge_overlap_counted_as_primary": row["edge_overlap_counted_as_primary"],
                "legacy_path_match_count": row["legacy_path_match_count"],
                "legacy_path_mismatch_count": row["legacy_path_mismatch_count"],
                "move_slice_count": move_count,
            }
        )
    return output


def _candidate_schema_rows() -> list[dict[str, Any]]:
    rows = [
        ("sample_id", "metadata", False, False, "stable row id"),
        ("scenario", "metadata", True, False, "runtime scenario key for split and audit"),
        ("current_node", "runtime_feature", True, False, "current bag node"),
        ("goal_node", "runtime_feature", True, False, "task destination"),
        ("candidate_next_nodes", "runtime_feature", True, False, "available outgoing neighbors"),
        ("teacher_next_node", "label", False, True, "supervision target, forbidden as input"),
        ("current_time", "runtime_feature", True, False, "decision time"),
        ("deadline_or_std", "runtime_feature", True, False, "task deadline/std from inputdata"),
        ("time_slack", "runtime_feature", True, False, "deadline_or_std minus current_time"),
        ("candidate_shortest_time_to_goal", "runtime_feature", True, False, "map heuristic from candidate to goal"),
        ("candidate_travel_time", "runtime_feature", True, False, "edge travel time from current to candidate"),
        ("candidate_service_time", "runtime_feature", True, False, "candidate node service time"),
        ("candidate_node_type", "runtime_feature", True, False, "candidate node type from map"),
        ("candidate_fault_status", "runtime_feature", True, False, "active fault on current->candidate at decision time"),
        ("local_node_time_window_pressure", "runtime_feature", True, False, "prior local node-window occupancy count"),
        ("local_queue_or_occupancy_summary", "runtime_feature", True, False, "local pressure summary available at decision time"),
        ("label_type", "label", False, True, "MOVE or WAIT teacher label"),
    ]
    return [
        {
            "field": field,
            "scope": scope,
            "allowed_model_input": allowed,
            "contains_label": label,
            "notes": notes,
        }
        for field, scope, allowed, label, notes in rows
    ]


def _forbidden_feature_rows() -> list[dict[str, Any]]:
    dataset_fields = {
        "teacher_next_node",
        "teacher_route_source",
        "label_type",
    }
    forbidden = [
        ("teacher_next_node", True, "present as label only"),
        ("teacher_path", False, "not emitted"),
        ("full CIE/A* route suffix", False, "not emitted"),
        ("future SIPP schedule", False, "not emitted"),
        ("route_finish_time", False, "not emitted"),
        ("label_source", True, "metadata only, not model input"),
        ("post-hoc success flag", False, "not emitted"),
        ("global future occupancy after this decision", False, "not emitted"),
    ]
    rows: list[dict[str, Any]] = []
    for feature, present, notes in forbidden:
        present_in_model_input = feature in MODEL_INPUT_FEATURES
        rows.append(
            {
                "forbidden_feature": feature,
                "present_in_dataset": present or feature in dataset_fields,
                "present_in_model_input": present_in_model_input,
                "pass": not present_in_model_input,
                "notes": notes,
            }
        )
    return rows


def _split_rows(interface_rows: list[dict[str, Any]], source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "sample_id": row["sample_id"],
            "split": row["split"],
            "scenario": row["scenario"],
            "task_id": row["task_id"],
            "segment_id": row["segment_id"],
            "label_type": row["label_type"],
        }
        for row in [*interface_rows, *source_rows]
    ]


def _gate_rows(
    interface_rows: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    forbidden_rows: list[dict[str, Any]],
    split_rows: list[dict[str, Any]],
    teacher_parity_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    aggregate = next(row for row in teacher_parity_rows if row["scenario"] == "ALL")
    route_edge_count = sum(len(row["candidate_next_nodes"]) >= 1 for row in interface_rows)
    contexts = {row["context"] for row in [*interface_rows, *source_rows]}
    split_names = {row["split"] for row in split_rows}
    rows = [
        ("teacher_replay_parity_144", int(aggregate["planned"]) == EXPECTED_PLANNED and int(aggregate["max_tasks"]) == EXPECTED_PLANNED, f"{aggregate['planned']}/{aggregate['max_tasks']}", "144/144"),
        ("node_window_conflicts_zero", int(aggregate["node_window_conflicts"]) == 0, aggregate["node_window_conflicts"], "0"),
        ("edge_capacity_primary_disabled", aggregate["edge_capacity_model"] == "not_applied_original_cie_node_window_primary" and aggregate["edge_overlap_counted_as_primary"] == "False", aggregate["edge_capacity_model"], "no edge_capacity=1 primary"),
        ("interface_slices_cover_all_route_edges", len(interface_rows) >= route_edge_count and len(interface_rows) > EXPECTED_PLANNED, len(interface_rows), "> route-level teacher count"),
        ("branch_node_slices_positive", any(row["is_branch_node"] for row in interface_rows), sum(1 for row in interface_rows if row["is_branch_node"]), ">0"),
        ("source_retry_slices_match_g3k", len(source_rows) == EXPECTED_SOURCE_RETRY, len(source_rows), str(EXPECTED_SOURCE_RETRY)),
        ("forbidden_feature_audit_pass", all(row["pass"] for row in forbidden_rows), "all clear", "no forbidden feature in model input"),
        ("train_val_test_split_created", {"train", "val", "test"}.issubset(split_names), ";".join(sorted(split_names)), "train;val;test"),
        ("scenario_coverage_required_contexts", {"no_fault", "static_fault", "repair_window", "merge_window"}.issubset(contexts), ";".join(sorted(contexts)), "no_fault/static_fault/repair_window/merge_window"),
    ]
    return [
        {
            "gate": gate,
            "pass": passed,
            "value": value,
            "threshold": threshold,
            "decision": "pass" if passed else "block_g4b_training",
        }
        for gate, passed, value, threshold in rows
    ]


def _json_ready(row: dict[str, Any]) -> dict[str, Any]:
    output = dict(row)
    output["model_input_feature_names"] = list(MODEL_INPUT_FEATURES)
    output["teacher_label_available"] = True
    output["forbidden_as_model_input"] = ["teacher_next_node", "teacher_path", "full_cie_route_suffix", "future_sipp_schedule", "route_finish_time", "label_source", "post_hoc_success_flag"]
    return output


def _write_report(summary_rows: list[dict[str, Any]], gate_rows: list[dict[str, Any]], label_rows: list[dict[str, Any]], scenario_rows: list[dict[str, Any]]) -> None:
    summary = {row["metric"]: row["value"] for row in summary_rows}
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# G4A CIE Retry Teacher Dataset Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "G4A converts the verified G3k CIE/Java retry teacher into per-interface decision slices. It does not train a model. The primary constraints remain CIE/A* route intent, Java-style node windows, active fault edges, and Java-style unfinished-task retry. `edge_capacity=1` remains disabled as a primary constraint.",
        "",
        "## Dataset",
        "",
        f"- G3k variant: `{RECOMMENDED_G3K_VARIANT}`",
        f"- Teacher routes: `{summary['teacher_routes']}`",
        f"- Interface MOVE slices: `{summary['interface_move_slices']}`",
        f"- Source retry slices: `{summary['source_retry_slices']}`",
        f"- Branch-node MOVE slices: `{summary['branch_node_slices']}`",
        "",
        "## Label Distribution",
        "",
        _markdown_table(["Label", "Count"], [[row["label_type"], row["count"]] for row in label_rows]),
        "",
        "## Scenario Coverage",
        "",
        _markdown_table(
            ["Scenario", "Context", "Tasks", "MOVE slices", "Source retry"],
            [[row["scenario"], row["context"], row["teacher_task_count"], row["move_slice_count"], row["source_retry_slice_count"]] for row in scenario_rows],
        ),
        "",
        "## Gates",
        "",
        _markdown_table(["Gate", "Pass", "Value", "Decision"], [[row["gate"], row["pass"], row["value"], row["decision"]] for row in gate_rows]),
        "",
        "## Leakage Guard",
        "",
        "`teacher_next_node` is present as the supervised label but is not part of `model_input_feature_names`. Full route suffixes, future SIPP schedules, route finish times, and post-hoc success flags are not emitted as model inputs.",
        "",
        "## Decision",
        "",
        "G4A passes if every gate above is true. Only then may G4B train the minimal pilot scorer; this dataset is not itself a learning result.",
        "",
        "## Artifacts",
        "",
        f"- Summary: `{_relative(SUMMARY_TABLE)}`",
        f"- Interface slices: `{_relative(INTERFACE_TABLE)}`",
        f"- Source retry slices: `{_relative(SOURCE_RETRY_TABLE)}`",
        f"- Candidate schema: `{_relative(CANDIDATE_SCHEMA_TABLE)}`",
        f"- Forbidden feature audit: `{_relative(FORBIDDEN_AUDIT_TABLE)}`",
        f"- Branch coverage: `{_relative(BRANCH_COVERAGE_TABLE)}`",
        f"- Scenario coverage: `{_relative(SCENARIO_COVERAGE_TABLE)}`",
        f"- Label distribution: `{_relative(LABEL_DISTRIBUTION_TABLE)}`",
        f"- Replay parity: `{_relative(TEACHER_REPLAY_PARITY_TABLE)}`",
        f"- Split: `{_relative(SPLIT_TABLE)}`",
        f"- Gate: `{_relative(DATASET_GATE_TABLE)}`",
        f"- JSONL sample: `{_relative(SAMPLE_PATH)}`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            if index >= MAX_JSONL_SAMPLE_ROWS:
                break
            handle.write(json.dumps(_json_ready(row), ensure_ascii=True, sort_keys=True) + "\n")


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".")
    return value


def _interface_fields() -> list[str]:
    return [
        "sample_id",
        "scenario",
        "context",
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
        "source_retry_age_seconds",
        "label_type",
        "split",
        "edge_capacity_primary",
    ]


def _source_fields() -> list[str]:
    return [
        *[field for field in _interface_fields() if field != "teacher_next_node"],
        "teacher_next_node",
        "retry_delay_seconds",
        "attempts",
        "root_cause",
    ]


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
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    graph = IcsGraph.from_json(MAP_PATH)
    tasks = _task_lookup(TaskStream.from_jsonl(TASK_PATH))
    route_rows = _load_g3k_routes()
    interface_rows, source_rows = _build_dataset(graph, tasks, route_rows)
    label_rows = _label_distribution_rows(interface_rows, source_rows)
    branch_rows = _branch_coverage_rows(graph, interface_rows)
    scenario_rows = _scenario_coverage_rows(interface_rows, source_rows)
    teacher_parity_rows = _teacher_replay_parity_rows(interface_rows)
    schema_rows = _candidate_schema_rows()
    forbidden_rows = _forbidden_feature_rows()
    split_rows = _split_rows(interface_rows, source_rows)
    gate_rows = _gate_rows(interface_rows, source_rows, forbidden_rows, split_rows, teacher_parity_rows)
    summary_rows = _summary_rows(interface_rows, source_rows, gate_rows)

    _write_csv(INTERFACE_TABLE, interface_rows, _interface_fields())
    _write_csv(SOURCE_RETRY_TABLE, source_rows, _source_fields())
    _write_csv(CANDIDATE_SCHEMA_TABLE, schema_rows, ["field", "scope", "allowed_model_input", "contains_label", "notes"])
    _write_csv(FORBIDDEN_AUDIT_TABLE, forbidden_rows, ["forbidden_feature", "present_in_dataset", "present_in_model_input", "pass", "notes"])
    _write_csv(BRANCH_COVERAGE_TABLE, branch_rows, ["current_node", "node_type", "out_degree", "is_branch_node", "slice_count", "teacher_next_distribution"])
    _write_csv(SCENARIO_COVERAGE_TABLE, scenario_rows, ["scenario", "context", "teacher_task_count", "move_slice_count", "source_retry_slice_count", "branch_slice_count"])
    _write_csv(LABEL_DISTRIBUTION_TABLE, label_rows, ["label_type", "count"])
    _write_csv(TEACHER_REPLAY_PARITY_TABLE, teacher_parity_rows, ["variant", "scenario", "planned", "max_tasks", "node_window_conflicts", "edge_capacity_model", "edge_overlap_counted_as_primary", "legacy_path_match_count", "legacy_path_mismatch_count", "move_slice_count"])
    _write_csv(SPLIT_TABLE, split_rows, ["sample_id", "split", "scenario", "task_id", "segment_id", "label_type"])
    _write_csv(DATASET_GATE_TABLE, gate_rows, ["gate", "pass", "value", "threshold", "decision"])
    _write_csv(SUMMARY_TABLE, summary_rows, ["metric", "value", "notes"])
    _write_jsonl(SAMPLE_PATH, [*interface_rows, *source_rows])
    _write_report(summary_rows, gate_rows, label_rows, scenario_rows)

    if not all(row["pass"] for row in gate_rows):
        raise AssertionError("G4A dataset gate failed; do not train G4B")
    required = (
        REPORT_PATH,
        SUMMARY_TABLE,
        INTERFACE_TABLE,
        SOURCE_RETRY_TABLE,
        CANDIDATE_SCHEMA_TABLE,
        FORBIDDEN_AUDIT_TABLE,
        BRANCH_COVERAGE_TABLE,
        SCENARIO_COVERAGE_TABLE,
        LABEL_DISTRIBUTION_TABLE,
        TEACHER_REPLAY_PARITY_TABLE,
        SPLIT_TABLE,
        DATASET_GATE_TABLE,
        SAMPLE_PATH,
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4A artifacts: {missing}")
    print(
        "g4a complete: "
        f"routes={EXPECTED_PLANNED} move_slices={len(interface_rows)} "
        f"source_retry_slices={len(source_rows)} branch_slices={sum(1 for row in interface_rows if row['is_branch_node'])}"
    )


if __name__ == "__main__":
    main()
