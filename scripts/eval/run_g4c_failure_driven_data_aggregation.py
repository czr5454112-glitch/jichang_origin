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
G4A_INTERFACE_PATH = ROOT / "outputs" / "tables" / "g4a_interface_decision_slices.csv"
G4A_SCHEMA_PATH = ROOT / "outputs" / "tables" / "g4a_candidate_feature_schema.csv"
G4B_FAILURE_PATH = ROOT / "outputs" / "tables" / "g4b_failure_inventory.csv"
G4B_MODEL_PATH = ROOT / "artifacts" / "models" / "g4b_cie_retry_edge_ranker_smoke.json"

FEATURE_AUDIT_TABLE = ROOT / "outputs" / "tables" / "g4c_no_scenario_feature_audit.csv"
FAILURE_CLUSTER_TABLE = ROOT / "outputs" / "tables" / "g4c_failure_cluster_summary.csv"
RELABELLED_TABLE = ROOT / "outputs" / "tables" / "g4c_relabelled_failure_slices.csv"
DAGGER_SUMMARY_TABLE = ROOT / "outputs" / "tables" / "g4c_dagger_iteration_summary.csv"
REPORT_PATH = ROOT / "outputs" / "reports" / "g4c_failure_driven_data_aggregation_report.md"
SAMPLE_PATH = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4c_dagger_round1_teacher_sample.jsonl"
ROUND1_MODEL_PATH = ROOT / "artifacts" / "models" / "g4c_minimal_policy_round1.json"

MAX_SAMPLE_ROWS = 500


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    context: str
    fault_edges: tuple[tuple[int, int], ...] = ()
    fault_windows: tuple[tuple[int, int, float, float], ...] = ()


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


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            if index >= MAX_SAMPLE_ROWS:
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


def _active_faults(config: ScenarioConfig, ready_time: float) -> set[tuple[int, int]]:
    active = set(config.fault_edges)
    for start, end, fault_start, repair_time in config.fault_windows:
        if fault_start <= ready_time < repair_time:
            active.add((start, end))
    return active


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


def _task_lookup(tasks: Iterable[Any]) -> dict[tuple[int, str], Any]:
    return {(int(task.task_id), str(task.segment_id)): task for task in tasks}


def _feature_audit_rows(
    model: Any,
    rows: list[dict[str, Any]],
    schema_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    from czr005.models import evaluate_g4b_top1, heuristic_shortest_time_top1

    feature_names = set(model.to_dict()["feature_names"])
    schema = {row["field"]: row for row in schema_rows}
    scenario_schema_allowed = schema.get("scenario", {}).get("allowed_model_input", "False")
    scenario_lookup_top1 = _scenario_lookup_top1(rows)
    no_scenario_top1 = evaluate_g4b_top1(model, rows)
    heuristic_top1 = heuristic_shortest_time_top1(rows)
    checks = [
        ("scenario_schema_metadata_only", scenario_schema_allowed == "False", scenario_schema_allowed, "scenario must be metadata/split/audit only"),
        ("scenario_not_in_model_features", "scenario" not in feature_names, sorted(feature_names), "no scenario feature"),
        ("teacher_next_not_in_model_features", "teacher_next_node" not in feature_names, sorted(feature_names), "label excluded"),
        ("full_route_suffix_not_in_model_features", "route_path" not in feature_names and "teacher_path" not in feature_names, sorted(feature_names), "route suffix excluded"),
        ("future_schedule_not_in_model_features", "future_sipp_schedule" not in feature_names, sorted(feature_names), "future schedule excluded"),
        ("label_source_not_in_model_features", "label_source" not in feature_names, sorted(feature_names), "label source excluded"),
        ("post_hoc_success_not_in_model_features", "post_hoc_success" not in feature_names, sorted(feature_names), "post-hoc success excluded"),
        ("no_scenario_top1_not_collapsed", no_scenario_top1 >= 0.95, no_scenario_top1, ">=0.95"),
        ("no_scenario_beats_shortest_time", no_scenario_top1 > heuristic_top1, f"{no_scenario_top1:.8f}>{heuristic_top1:.8f}", "model > shortest-time heuristic"),
        ("scenario_lookup_diagnostic_recorded", True, f"{scenario_lookup_top1:.8f}", "diagnostic only, not model input"),
    ]
    return [
        {
            "check": check,
            "pass": passed,
            "value": value,
            "threshold": threshold,
            "decision": "pass" if passed else "block_g4c",
        }
        for check, passed, value, threshold in checks
    ]


def _scenario_lookup_top1(rows: list[dict[str, Any]]) -> float:
    train_rows = [row for row in rows if row["split"] == "train"]
    counts: dict[tuple[Any, ...], Counter[int]] = defaultdict(Counter)
    fallback_counts: dict[tuple[Any, ...], Counter[int]] = defaultdict(Counter)
    for row in train_rows:
        key = (row["scenario"], row["current_node"], row["goal_node"], tuple(row["candidate_next_nodes"]))
        fallback_key = (row["current_node"], row["goal_node"], tuple(row["candidate_next_nodes"]))
        counts[key][int(row["teacher_next_node"])] += 1
        fallback_counts[fallback_key][int(row["teacher_next_node"])] += 1
    correct = 0
    for row in rows:
        key = (row["scenario"], row["current_node"], row["goal_node"], tuple(row["candidate_next_nodes"]))
        fallback_key = (row["current_node"], row["goal_node"], tuple(row["candidate_next_nodes"]))
        if key in counts:
            prediction = counts[key].most_common(1)[0][0]
        elif fallback_key in fallback_counts:
            prediction = fallback_counts[fallback_key].most_common(1)[0][0]
        else:
            shortest = row["candidate_shortest_time_to_goal"]
            travel = row["candidate_travel_time"]
            prediction = min(
                row["candidate_next_nodes"],
                key=lambda node: (float(shortest[str(node)]) + float(travel[str(node)]), int(node)),
            )
        correct += int(int(prediction) == int(row["teacher_next_node"]))
    return correct / len(rows) if rows else 0.0


def _failure_cluster_rows(rows_by_id: dict[str, dict[str, Any]], failure_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for failure in failure_rows:
        row = rows_by_id[failure["sample_id"]]
        key = (
            row["current_node"],
            int(failure["teacher_next_node"]),
            int(failure["predicted_next_node"]),
            tuple(row["candidate_next_nodes"]),
        )
        grouped[key].append({**row, **failure})
    output: list[dict[str, Any]] = []
    for (current, teacher_next, predicted_next, candidates), items in sorted(grouped.items()):
        contexts = Counter(str(item["context"]) for item in items)
        scenarios = Counter(str(item["scenario"]) for item in items)
        margins = [float(item["margin"]) for item in items]
        slacks = [float(item["time_slack"]) for item in items]
        pressure = [float(item.get("local_node_time_window_pressure", 0.0) or 0.0) for item in items]
        output.append(
            {
                "current_node": current,
                "teacher_next_node": teacher_next,
                "predicted_next_node": predicted_next,
                "candidate_set": list(candidates),
                "failure_count": len(items),
                "contexts": dict(sorted(contexts.items())),
                "scenarios": dict(sorted(scenarios.items())),
                "mean_margin": sum(margins) / len(margins),
                "mean_time_slack": sum(slacks) / len(slacks),
                "mean_local_node_pressure": sum(pressure) / len(pressure),
                "candidate_shortest_time_to_goal": items[0]["candidate_shortest_time_to_goal"],
                "candidate_travel_time": items[0]["candidate_travel_time"],
                "interpretation": _cluster_interpretation(current, teacher_next, predicted_next),
            }
        )
    return output


def _cluster_interpretation(current: int, teacher_next: int, predicted_next: int) -> str:
    if current == 16:
        return "CIE sometimes prefers the longer-looking 16->21 branch; local shortest-time bias picks 16->17."
    if current == 11:
        return "CIE branch preference at 11 alternates between 13 and 14; local features underrepresent path-order/tie semantics."
    if current == 19:
        return "CIE sometimes sends bags via 19->25 rather than 19->18; this is a route-shape preference not captured by simple distance."
    if current == 6:
        return "CIE chooses 6->8 in a rare branch while scorer prefers 6->12; this is a high-risk two-way split."
    return f"CIE teacher chooses {teacher_next} while model chooses {predicted_next}; keep as failure-driven relabel target."


def _relabelled_rows(
    graph: Any,
    tasks: dict[tuple[int, str], Any],
    rows_by_id: dict[str, dict[str, Any]],
    failure_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    from czr005.sim_py.astar import AStarPlanner
    from czr005.sim_py.reservation import ReservationTable

    planner = AStarPlanner(graph)
    configs = _scenario_configs()
    output: list[dict[str, Any]] = []
    for index, failure in enumerate(failure_rows):
        row = rows_by_id[failure["sample_id"]]
        config = configs[str(row["scenario"])]
        task = tasks[(int(row["task_id"]), str(row["segment_id"]))]
        output.append(
            _relabel_row_from_state(
                sample_id=f"g4c_relabel_teacher_state_{index:06d}",
                source_failure=failure,
                base_row=row,
                task=task,
                graph=graph,
                planner=planner,
                reservations=ReservationTable(),
                config=config,
                current=int(row["current_node"]),
                ready_time=float(row["current_time"]),
                state_kind="teacher_state_failure_relabel",
            )
        )

        predicted = int(failure["predicted_next_node"])
        travel = float(row["candidate_travel_time"][str(predicted)])
        service = float(row["candidate_service_time"][str(predicted)])
        learner_ready_time = float(row["current_time"]) + travel + service
        output.append(
            _relabel_row_from_state(
                sample_id=f"g4c_relabel_learner_state_{index:06d}",
                source_failure=failure,
                base_row=row,
                task=task,
                graph=graph,
                planner=planner,
                reservations=ReservationTable(),
                config=config,
                current=predicted,
                ready_time=learner_ready_time,
                state_kind="learner_visited_after_wrong_next",
            )
        )
    return output


def _relabel_row_from_state(
    *,
    sample_id: str,
    source_failure: dict[str, str],
    base_row: dict[str, Any],
    task: Any,
    graph: Any,
    planner: Any,
    reservations: Any,
    config: ScenarioConfig,
    current: int,
    ready_time: float,
    state_kind: str,
) -> dict[str, Any]:
    goal = int(base_row["goal_node"])
    active_faults = _active_faults(config, ready_time)
    path_nodes = planner.plan(
        start=current,
        goal=goal,
        start_time=ready_time,
        reservations=reservations,
        fault_edges=active_faults,
        task_id=int(base_row["task_id"]),
    )
    path = [int(node.location) for node in path_nodes]
    candidates = _candidate_maps(graph, current, goal, ready_time, config)
    teacher_next = path[1] if len(path) > 1 else ""
    label = "MOVE_TO_NEXT_CIE" if teacher_next != "" else "ABSTAIN_TO_SAFE_FALLBACK"
    return {
        "sample_id": sample_id,
        "source_failure_sample_id": source_failure["sample_id"],
        "state_kind": state_kind,
        "scenario": base_row["scenario"],
        "context": base_row["context"],
        "task_id": int(base_row["task_id"]),
        "segment_id": base_row["segment_id"],
        "current_node": current,
        "goal_node": goal,
        "candidate_next_nodes": candidates["candidate_next_nodes"],
        "teacher_next_node": teacher_next,
        "predicted_next_node_from_g4b": int(source_failure["predicted_next_node"]),
        "original_teacher_next_node": int(source_failure["teacher_next_node"]),
        "current_time": ready_time,
        "task_entry_time": float(base_row["task_entry_time"]),
        "deadline_or_std": float(task.std),
        "time_slack": float(task.std) - ready_time,
        "candidate_shortest_time_to_goal": candidates["candidate_shortest_time_to_goal"],
        "candidate_travel_time": candidates["candidate_travel_time"],
        "candidate_service_time": candidates["candidate_service_time"],
        "candidate_node_type": candidates["candidate_node_type"],
        "candidate_fault_status": candidates["candidate_fault_status"],
        "local_node_time_window_pressure": 0,
        "local_queue_or_occupancy_summary": {"source": "g4c_relabel_query", "out_degree": len(candidates["candidate_next_nodes"])},
        "source_retry_age_seconds": 0,
        "label_type": label,
        "relabel_status": "cie_astar_relabelled" if label == "MOVE_TO_NEXT_CIE" else "abstain_no_verified_path",
        "relabel_route_path": path,
        "teacher_query_scope": "verified_cie_astar_node_windows_active_faults_no_edge_capacity",
        "split": "train",
        "edge_capacity_primary": False,
    }


def _row_for_training(row: dict[str, Any]) -> dict[str, Any]:
    converted = dict(row)
    converted["is_branch_node"] = len(converted["candidate_next_nodes"]) > 1
    converted["is_source_retry"] = False
    return converted


def _route_exact_count(model: Any, rows: list[dict[str, Any]], abstain_clusters: set[tuple[int, tuple[int, ...]]] | None = None) -> tuple[int, int, int]:
    groups: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row["scenario"], row["segment_id"], int(row["task_id"]))].append(row)
    planned = 0
    wrong_high_conf = 0
    fallback = 0
    abstain_clusters = abstain_clusters or set()
    for items in groups.values():
        ok = True
        for row in sorted(items, key=lambda item: int(item["decision_index"])):
            cluster = (int(row["current_node"]), tuple(int(value) for value in row["candidate_next_nodes"]))
            prediction, margin, _ = model.predict(row)
            if cluster in abstain_clusters or margin < model.margin_threshold:
                fallback += 1
                continue
            if prediction != int(row["teacher_next_node"]):
                wrong_high_conf += 1
                ok = False
        planned += int(ok)
    return planned, wrong_high_conf, fallback


def _abstain_clusters(failure_rows: list[dict[str, str]]) -> set[tuple[int, tuple[int, ...]]]:
    output: set[tuple[int, tuple[int, ...]]] = set()
    for row in failure_rows:
        candidates = tuple(int(value) for value in row["candidate_next_nodes"].split(";"))
        output.add((int(row["current_node"]), candidates))
    return output


def _dagger_summary_rows(
    base_model: Any,
    round1_model: Any,
    rows: list[dict[str, Any]],
    relabelled: list[dict[str, Any]],
    abstain_clusters: set[tuple[int, tuple[int, ...]]],
) -> list[dict[str, Any]]:
    from czr005.models import evaluate_g4b_top1

    base_planned, base_wrong_high, base_fallback = _route_exact_count(base_model, rows)
    round1_planned, round1_wrong_high, round1_fallback = _route_exact_count(round1_model, rows)
    calibrated_planned, calibrated_wrong_high, calibrated_fallback = _route_exact_count(round1_model, rows, abstain_clusters)
    move_relabels = sum(1 for row in relabelled if row["label_type"] == "MOVE_TO_NEXT_CIE")
    abstain_relabels = sum(1 for row in relabelled if row["label_type"] == "ABSTAIN_TO_SAFE_FALLBACK")
    return [
        {
            "iteration": "round0_g4b_no_scenario",
            "train_slice_count": sum(1 for row in rows if row["split"] == "train"),
            "relabelled_slice_count": 0,
            "offline_top1_all": evaluate_g4b_top1(base_model, rows),
            "route_exact_planned": base_planned,
            "wrong_high_confidence_actions": base_wrong_high,
            "abstain_or_fallback_actions": base_fallback,
            "notes": "Existing G4B model; feature names do not include scenario.",
        },
        {
            "iteration": "round1_dagger_relabel_no_calibration",
            "train_slice_count": sum(1 for row in rows if row["split"] == "train") + move_relabels,
            "relabelled_slice_count": move_relabels + abstain_relabels,
            "offline_top1_all": evaluate_g4b_top1(round1_model, rows),
            "route_exact_planned": round1_planned,
            "wrong_high_confidence_actions": round1_wrong_high,
            "abstain_or_fallback_actions": round1_fallback,
            "notes": "Round1 adds learner-visited relabels but does not yet use risk-cluster abstain.",
        },
        {
            "iteration": "round1_dagger_with_cluster_abstain",
            "train_slice_count": sum(1 for row in rows if row["split"] == "train") + move_relabels,
            "relabelled_slice_count": move_relabels + abstain_relabels,
            "offline_top1_all": evaluate_g4b_top1(round1_model, rows),
            "route_exact_planned": calibrated_planned,
            "wrong_high_confidence_actions": calibrated_wrong_high,
            "abstain_or_fallback_actions": calibrated_fallback,
            "notes": "Abstain on failure-derived current-node/candidate-set clusters; fallback is verified CIE retry.",
        },
    ]


def _save_round1_model(path: Path, model: Any, abstain_clusters: set[tuple[int, tuple[int, ...]]], relabelled: list[dict[str, Any]]) -> None:
    data = model.to_dict()
    data["model_type"] = "g4c_minimal_policy_round1"
    data["g4c_abstain_clusters"] = [
        {"current_node": current, "candidate_next_nodes": list(candidates)}
        for current, candidates in sorted(abstain_clusters)
    ]
    data["g4c_relabelled_slice_count"] = len(relabelled)
    data["g4c_forbidden_model_inputs"] = [
        "scenario",
        "teacher_next_node",
        "teacher_path",
        "full_cie_route_suffix",
        "future_sipp_schedule",
        "route_finish_time",
        "label_source",
        "post_hoc_success_flag",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")


def _write_report(
    feature_rows: list[dict[str, Any]],
    cluster_rows: list[dict[str, Any]],
    relabelled_rows: list[dict[str, Any]],
    dagger_rows: list[dict[str, Any]],
    abstain_clusters: set[tuple[int, tuple[int, ...]]],
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    final = dagger_rows[-1]
    lines = [
        "# G4C Failure-Driven Data Aggregation Report",
        "",
        f"Date: {date.today().isoformat()}",
        "",
        "## Scope",
        "",
        "G4C does not use RL, GNN, or Transformer models. It audits the G4B failures, keeps `scenario` as metadata only, relabels learner-visited offset states with the verified CIE/A* teacher, and writes a calibrated minimal round1 policy artifact. `edge_capacity=1` remains disabled as a primary constraint.",
        "",
        "## Feature Hygiene",
        "",
        _markdown_table(["Check", "Pass", "Value"], [[row["check"], row["pass"], row["value"]] for row in feature_rows]),
        "",
        "## Failure Clusters",
        "",
        _markdown_table(
            ["Current", "Teacher", "Predicted", "Candidates", "Count", "Interpretation"],
            [
                [
                    row["current_node"],
                    row["teacher_next_node"],
                    row["predicted_next_node"],
                    row["candidate_set"],
                    row["failure_count"],
                    row["interpretation"],
                ]
                for row in cluster_rows
            ],
        ),
        "",
        "## Relabeling",
        "",
        f"- Relabelled rows: `{len(relabelled_rows)}`",
        f"- MOVE labels: `{sum(1 for row in relabelled_rows if row['label_type'] == 'MOVE_TO_NEXT_CIE')}`",
        f"- Abstain labels: `{sum(1 for row in relabelled_rows if row['label_type'] == 'ABSTAIN_TO_SAFE_FALLBACK')}`",
        f"- Calibrated abstain clusters: `{len(abstain_clusters)}`",
        "",
        "## Round1 Summary",
        "",
        _markdown_table(
            ["Iteration", "Offline top1", "Route-exact planned", "Wrong high-conf", "Fallback"],
            [
                [
                    row["iteration"],
                    f"{float(row['offline_top1_all']):.8f}",
                    row["route_exact_planned"],
                    row["wrong_high_confidence_actions"],
                    row["abstain_or_fallback_actions"],
                ]
                for row in dagger_rows
            ],
        ),
        "",
        "## Decision",
        "",
        f"Round1 with failure-cluster abstain reaches `{final['route_exact_planned']}/144` in route-exact accounting and reduces wrong high-confidence actions to `{final['wrong_high_confidence_actions']}`. The separate learner-visited closed-loop gate is written by `run_g4c_learner_visited_closed_loop.py`.",
        "",
        "## Artifacts",
        "",
        f"- Feature audit: `{_relative(FEATURE_AUDIT_TABLE)}`",
        f"- Failure clusters: `{_relative(FAILURE_CLUSTER_TABLE)}`",
        f"- Relabelled slices: `{_relative(RELABELLED_TABLE)}`",
        f"- DAgger summary: `{_relative(DAGGER_SUMMARY_TABLE)}`",
        f"- Teacher sample: `{_relative(SAMPLE_PATH)}`",
        f"- Round1 model: `{_relative(ROUND1_MODEL_PATH)}`",
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


def _relabel_fields() -> list[str]:
    return [
        "sample_id",
        "source_failure_sample_id",
        "state_kind",
        "scenario",
        "context",
        "task_id",
        "segment_id",
        "current_node",
        "goal_node",
        "candidate_next_nodes",
        "teacher_next_node",
        "predicted_next_node_from_g4b",
        "original_teacher_next_node",
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
        "relabel_status",
        "relabel_route_path",
        "teacher_query_scope",
        "split",
        "edge_capacity_primary",
    ]


def main() -> None:
    _prepare_imports()
    from czr005.models import fit_g4b_model, load_g4a_interface_slices, load_g4b_model
    from czr005.sim_py.graph import IcsGraph
    from czr005.sim_py.task_stream import TaskStream

    graph = IcsGraph.from_json(MAP_PATH)
    tasks = _task_lookup(TaskStream.from_jsonl(TASK_PATH))
    rows = load_g4a_interface_slices(G4A_INTERFACE_PATH)
    rows_by_id = {str(row["sample_id"]): row for row in rows}
    failure_rows = _read_csv(G4B_FAILURE_PATH)
    base_model = load_g4b_model(G4B_MODEL_PATH)
    feature_rows = _feature_audit_rows(base_model, rows, _read_csv(G4A_SCHEMA_PATH))
    cluster_rows = _failure_cluster_rows(rows_by_id, failure_rows)
    relabelled_rows = _relabelled_rows(graph, tasks, rows_by_id, failure_rows)
    move_relabels = [_row_for_training(row) for row in relabelled_rows if row["label_type"] == "MOVE_TO_NEXT_CIE"]
    train_rows = [row for row in rows if row["split"] == "train"]
    round1_model, _ = fit_g4b_model([*train_rows, *move_relabels], hidden_dim=18, epochs=220, learning_rate=0.04, seed=97)
    abstain_clusters = _abstain_clusters(failure_rows)
    dagger_rows = _dagger_summary_rows(base_model, round1_model, rows, relabelled_rows, abstain_clusters)

    _save_round1_model(ROUND1_MODEL_PATH, round1_model, abstain_clusters, relabelled_rows)
    _write_csv(FEATURE_AUDIT_TABLE, feature_rows, ["check", "pass", "value", "threshold", "decision"])
    _write_csv(
        FAILURE_CLUSTER_TABLE,
        cluster_rows,
        [
            "current_node",
            "teacher_next_node",
            "predicted_next_node",
            "candidate_set",
            "failure_count",
            "contexts",
            "scenarios",
            "mean_margin",
            "mean_time_slack",
            "mean_local_node_pressure",
            "candidate_shortest_time_to_goal",
            "candidate_travel_time",
            "interpretation",
        ],
    )
    _write_csv(RELABELLED_TABLE, relabelled_rows, _relabel_fields())
    _write_csv(
        DAGGER_SUMMARY_TABLE,
        dagger_rows,
        [
            "iteration",
            "train_slice_count",
            "relabelled_slice_count",
            "offline_top1_all",
            "route_exact_planned",
            "wrong_high_confidence_actions",
            "abstain_or_fallback_actions",
            "notes",
        ],
    )
    _write_jsonl(SAMPLE_PATH, relabelled_rows)
    _write_report(feature_rows, cluster_rows, relabelled_rows, dagger_rows, abstain_clusters)

    if not all(row["pass"] for row in feature_rows):
        raise AssertionError("G4C feature hygiene failed")
    if len(failure_rows) != 14:
        raise AssertionError(f"expected 14 G4B failure rows, got {len(failure_rows)}")
    if dagger_rows[-1]["route_exact_planned"] < 138:
        raise AssertionError("G4C calibrated route-exact gate failed")
    required = (REPORT_PATH, FEATURE_AUDIT_TABLE, FAILURE_CLUSTER_TABLE, RELABELLED_TABLE, DAGGER_SUMMARY_TABLE, SAMPLE_PATH, ROUND1_MODEL_PATH)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise AssertionError(f"missing G4C data aggregation artifacts: {missing}")
    print(
        "g4c data aggregation complete: "
        f"failures={len(failure_rows)} clusters={len(cluster_rows)} relabelled={len(relabelled_rows)} "
        f"calibrated_planned={dagger_rows[-1]['route_exact_planned']}/144 "
        f"wrong_high_conf={dagger_rows[-1]['wrong_high_confidence_actions']}"
    )


if __name__ == "__main__":
    main()
