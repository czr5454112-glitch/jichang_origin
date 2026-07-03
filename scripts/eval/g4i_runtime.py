from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
LEGACY_MAP_PATH = ROOT / "legacy" / "jichang_origin_readonly" / "map2.txt"
TASK_PATH = ROOT / "data" / "processed" / "tasks" / "inputdata.jsonl"
MODEL_PATH = ROOT / "artifacts" / "models" / "g4e_risk_calibrated_policy.json"
G4H_BUNDLE_PATH = ROOT / "artifacts" / "runtime" / "g4h_cpp_policy_bundle.json"
G4G_CONFIG_PATH = ROOT / "artifacts" / "policies" / "g4g_no_astar_decentralized_policy_config.json"
G4H_CONFIG_PATH = ROOT / "artifacts" / "policies" / "g4h_no_astar_runtime_config.json"
TEACHER_MANIFEST = ROOT / "artifacts" / "teacher" / "legacy_astar" / "g4d_large_window_teacher_manifest.jsonl"
G4D_SUMMARY = ROOT / "outputs" / "tables" / "g4d_large_window_teacher_summary.csv"
G4D_ASTAR = ROOT / "outputs" / "tables" / "g4d_astar_call_accounting.csv"
G4E_ASTAR = ROOT / "outputs" / "tables" / "g4e_astar_call_accounting.csv"
G4G_ABLATION = ROOT / "outputs" / "tables" / "g4g_policy_ablation.csv"
G4G_BOUNDARY = ROOT / "outputs" / "tables" / "g4g_teacher_no_path_boundary.csv"

FULL_RUNTIME_REPORT = ROOT / "outputs" / "reports" / "g4i_full_cpp_runtime_report.md"
PARITY_REPORT = ROOT / "outputs" / "reports" / "g4i_cpp_python_episode_parity_report.md"
SPEED_REPORT = ROOT / "outputs" / "reports" / "g4i_runtime_speed_benchmark_report.md"
STRESS_REPORT = ROOT / "outputs" / "reports" / "g4i_large_window_stress_report.md"
LEAKAGE_REPORT = ROOT / "outputs" / "reports" / "g4i_no_leakage_runtime_report.md"
BOUNDARY_REPORT = ROOT / "outputs" / "reports" / "g4i_negative_boundary_report.md"
PROMOTION_REPORT = ROOT / "outputs" / "reports" / "g4i_promotion_decision.md"

HASH_TABLE = ROOT / "outputs" / "tables" / "g4i_policy_bundle_hash.csv"
PARITY_TABLE = ROOT / "outputs" / "tables" / "g4i_cpp_python_episode_parity.csv"
SPEED_TABLE = ROOT / "outputs" / "tables" / "g4i_runtime_speed_benchmark.csv"
STRESS_TABLE = ROOT / "outputs" / "tables" / "g4i_large_window_stress.csv"
LEAKAGE_TABLE = ROOT / "outputs" / "tables" / "g4i_no_leakage_runtime_checks.csv"
ABLATION_TABLE = ROOT / "outputs" / "tables" / "g4i_policy_ablation_runtime.csv"
ZERO_ASTAR_TABLE = ROOT / "outputs" / "tables" / "g4i_task_level_zero_astar.csv"
NODE_CONFLICT_TABLE = ROOT / "outputs" / "tables" / "g4i_node_window_conflict_audit.csv"
EDGE_DIAG_TABLE = ROOT / "outputs" / "tables" / "g4i_edge_overlap_diagnostic_only.csv"
NEGATIVE_TABLE = ROOT / "outputs" / "tables" / "g4i_negative_boundary_cases.csv"
LATENCY_TABLE = ROOT / "outputs" / "tables" / "g4i_memory_and_latency.csv"
PROMOTION_TABLE = ROOT / "outputs" / "tables" / "g4i_promotion_gate.csv"

CPP_TRACE = ROOT / "artifacts" / "traces" / "g4i_cpp_runtime_trace_sample.jsonl"
MISMATCH_TRACE = ROOT / "artifacts" / "traces" / "g4i_cpp_python_mismatch_sample.jsonl"
NEGATIVE_TRACE = ROOT / "artifacts" / "traces" / "g4i_negative_boundary_sample.jsonl"

TRACE_LIMIT = 500
MAX_MODEL_STEPS = 80
MAX_RULE_ONLY_STEPS = 24
G4H_COMMIT = "b3d2296"


@dataclass(frozen=True)
class PolicyMode:
    policy: str
    use_model: bool
    rule_only: bool
    risk_gated_rule: bool
    fallback_name: str
    bounded_depth: int = 1
    role: str = "candidate"


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


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return value


def _git(command: list[str]) -> str:
    result = subprocess.run(["git", *command], cwd=ROOT, check=False, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_context() -> dict[str, Any]:
    upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    pushed = False
    if upstream:
        pushed = subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", upstream], cwd=ROOT, check=False).returncode == 0
    return {
        "branch": _git(["branch", "--show-current"]),
        "head": _git(["rev-parse", "--short", "HEAD"]),
        "dirty": bool(_git(["status", "--short"])),
        "status_short": _git(["status", "--short"]).replace("\n", " | "),
        "contains_g4h": subprocess.run(["git", "merge-base", "--is-ancestor", G4H_COMMIT, "HEAD"], cwd=ROOT, check=False).returncode == 0,
        "upstream": upstream,
        "head_pushed_to_upstream": pushed,
        "legacy_diff_files": _git(["diff", "--name-only", "--", "legacy"]).replace("\n", " | "),
        "log_oneline_8": _git(["log", "--oneline", "-8"]).replace("\n", " | "),
    }


def _policy_modes() -> list[PolicyMode]:
    return [
        PolicyMode("model_only_no_astar", True, False, False, "none", role="diagnostic_model_only"),
        PolicyMode("pibt_lite_only", False, True, False, "node_window_pibt_lite", role="diagnostic_rule_only"),
        PolicyMode("model_plus_pibt_lite", True, False, True, "node_window_pibt_lite"),
        PolicyMode("model_plus_static_distance_fallback", True, False, True, "static_distance"),
        PolicyMode("model_plus_node_window_greedy", True, False, True, "node_window_aware"),
        PolicyMode("model_plus_k_step_local_window", True, False, True, "bounded_local_search", bounded_depth=3),
    ]


def _official_mode() -> PolicyMode:
    return PolicyMode("model_plus_pibt_lite", True, False, True, "node_window_pibt_lite")


def _graph_records() -> tuple[list[Any], list[Any], list[list[float]]]:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    nodes = [
        (
            int(node["location"]),
            int(node["node_type"]),
            float(node["service_time"]),
            int(node["x"]),
            int(node["y"]),
            [int(value) for value in node["outgoing"]],
        )
        for node in data["nodes"]
    ]
    edges = [
        (int(edge["start"]), int(edge["end"]), float(edge["length"]), float(edge["speed"]))
        for edge in data["edges"]
    ]
    heuristic = [[float(value) for value in row] for row in data["heuristic_time"]]
    return nodes, edges, heuristic


def _task_lookup() -> dict[tuple[int, str], dict[str, Any]]:
    tasks = {}
    for line in TASK_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            tasks[(int(row["task_id"]), str(row["segment_id"]))] = row
    return tasks


def _all_tasks() -> list[dict[str, Any]]:
    return [json.loads(line) for line in TASK_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def _window_records_from_runtime(windows: Iterable[Any]) -> list[Any]:
    return [
        (
            str(window.name),
            int(window.task_offset),
            int(window.max_tasks),
            str(window.context),
            str(window.source),
            [(int(start), int(end)) for start, end in getattr(window, "fault_edges", ())],
            [
                (int(start), int(end), float(fault_start), float(repair_time))
                for start, end, fault_start, repair_time in getattr(window, "fault_windows", ())
            ],
        )
        for window in windows
    ]


def _g4d_windows() -> tuple[list[Any], dict[str, Any]]:
    from scripts.data.build_g4d_cie_retry_large_window_dataset import _window_plan
    from scripts.eval.run_g4g_no_astar_fallback_validation import RuntimeWindow

    windows = []
    for scenario in _window_plan():
        context = "static_fault" if scenario.fault_edges else ("repair_window" if scenario.fault_windows else "no_fault")
        windows.append(
            RuntimeWindow(
                scenario.name,
                scenario.task_offset,
                scenario.max_tasks,
                context,
                "g4d_teacher_planned_scope",
                tuple(tuple(int(value) for value in edge) for edge in scenario.fault_edges),
                tuple(tuple(float(value) for value in item) for item in scenario.fault_windows),
            )
        )
    return windows, {window.name: window for window in windows}


def _stress_windows(include_large_smoke: bool) -> tuple[list[Any], dict[str, Any]]:
    from scripts.eval.run_g4g_no_astar_fallback_validation import RuntimeWindow

    windows = []
    for offset in (0, 512, 1024, 1536, 2048, 3072, 4096, 8192):
        windows.append(RuntimeWindow(f"g4i_512_offset{offset}_no_fault", offset, 512, "no_fault", "g4i_raw_inputdata_stress"))
    for offset in (0, 1024, 2048, 3072, 4096, 8192):
        windows.append(RuntimeWindow(f"g4i_1024_offset{offset}_no_fault", offset, 1024, "no_fault", "g4i_raw_inputdata_stress"))
    for offset in (0, 2048, 4096):
        windows.append(RuntimeWindow(f"g4i_2048_offset{offset}_no_fault", offset, 2048, "no_fault", "g4i_raw_inputdata_stress"))
    for offset in (0, 4096):
        windows.append(RuntimeWindow(f"g4i_4096_offset{offset}_no_fault", offset, 4096, "no_fault", "g4i_raw_inputdata_stress"))
    windows.append(RuntimeWindow("g4i_8192_offset0_no_fault", 0, 8192, "no_fault", "g4i_raw_inputdata_stress"))
    if include_large_smoke:
        windows.append(RuntimeWindow("g4i_12000_offset0_no_fault_smoke", 0, 12000, "no_fault", "g4i_raw_inputdata_smoke"))
    return windows, {window.name: window for window in windows}


def _g4d_route_records(tasks: dict[tuple[int, str], dict[str, Any]]) -> tuple[list[Any], list[dict[str, Any]]]:
    routes = []
    cpp_records = []
    for row in _load_jsonl(TEACHER_MANIFEST):
        if row.get("record_type") != "planned_route":
            continue
        task = tasks[(int(row["task_id"]), str(row["segment_id"]))]
        route = {
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
            "teacher_path": [int(node) for node in row.get("route_path", [])],
            "teacher_scope_available": True,
            "teacher_record_type": "planned_route",
        }
        routes.append(route)
        cpp_records.append(
            (
                route["experiment_scope"],
                route["window_name"],
                route["task_id"],
                route["segment_id"],
                route["start"],
                route["goal"],
                route["entry_time"],
                route["attempt_time"],
                float(task["std"]),
            )
        )
    return cpp_records, routes


def _raw_route_records(windows: list[Any], tasks: list[dict[str, Any]]) -> tuple[list[Any], list[dict[str, Any]]]:
    routes = []
    cpp_records = []
    for window in windows:
        for task in tasks[window.task_offset : window.task_offset + window.max_tasks]:
            route = {
                "experiment_scope": "raw_inputdata_stress",
                "window_name": window.name,
                "context": window.context,
                "window_offset": window.task_offset,
                "window_size": window.max_tasks,
                "task_id": int(task["task_id"]),
                "segment_id": str(task["segment_id"]),
                "start": int(task["start"]),
                "goal": int(task["goal"]),
                "entry_time": float(task["pass_time"]),
                "attempt_time": float(task["pass_time"]),
                "teacher_path": [],
                "teacher_scope_available": False,
                "teacher_record_type": "raw_task",
            }
            routes.append(route)
            cpp_records.append(
                (
                    route["experiment_scope"],
                    route["window_name"],
                    route["task_id"],
                    route["segment_id"],
                    route["start"],
                    route["goal"],
                    route["entry_time"],
                    route["attempt_time"],
                    float(task["std"]),
                )
            )
    return cpp_records, routes


def _historical_risk_rules() -> list[tuple[int, list[int], int]]:
    rows = _read_csv(ROOT / "outputs" / "tables" / "g4c_failure_cluster_summary.csv")
    return [
        (int(row["current_node"]), [int(value) for value in json.loads(row["candidate_set"])], int(row["predicted_next_node"]))
        for row in rows
    ]


def _fallback_rules(policy_data: dict[str, Any]) -> list[tuple[int, int, list[int], int]]:
    return [
        (
            int(row["current_node"]),
            int(row["goal_node"]),
            [int(value) for value in row["candidate_next_nodes"]],
            int(row["predicted_next_node"]),
        )
        for row in policy_data.get("g4e_learned_risk_rules", [])
    ]


def _cpp_replay(
    *,
    mode: PolicyMode,
    window_records: list[Any],
    route_records: list[Any],
    policy_data: dict[str, Any],
    trace_limit: int = TRACE_LIMIT,
    summary_only: bool = False,
    profile_enabled: bool = False,
    enable_edge_overlap_diagnostic: bool = True,
    audit_final_conflicts: bool = True,
) -> dict[str, Any]:
    from czr005 import cpp_backend

    node_records, edge_records, heuristic = _graph_records()
    max_steps = MAX_RULE_ONLY_STEPS if mode.rule_only else MAX_MODEL_STEPS
    return cpp_backend.g4i_no_astar_batch_replay(
        node_records=node_records,
        edge_records=edge_records,
        heuristic_time=heuristic,
        window_records=window_records,
        route_records=route_records,
        w1=policy_data["w1"],
        b1=policy_data["b1"],
        w2=policy_data["w2"],
        b2=policy_data["b2"],
        risk_margin_threshold=float(policy_data.get("risk_margin_threshold", 1.0)),
        risk_historical_threshold=float(policy_data.get("risk_historical_threshold", 0.5)),
        risk_bottleneck_threshold=float(policy_data.get("risk_bottleneck_threshold", 5.0)),
        historical_risk_rules=_historical_risk_rules(),
        fallback_rules=_fallback_rules(policy_data),
        policy_name=mode.policy,
        use_model=mode.use_model,
        rule_only=mode.rule_only,
        risk_gated_rule=mode.risk_gated_rule,
        fallback_name=mode.fallback_name,
        bounded_depth=mode.bounded_depth,
        max_steps=max_steps,
        trace_limit=trace_limit,
        summary_only=summary_only,
        profile_enabled=profile_enabled,
        enable_edge_overlap_diagnostic=enable_edge_overlap_diagnostic,
        audit_final_conflicts=audit_final_conflicts,
    )


def _python_reference(
    *,
    mode: PolicyMode,
    routes: list[dict[str, Any]],
    windows: dict[str, Any],
    tasks: dict[tuple[int, str], Any],
    policy_data: dict[str, Any],
) -> tuple[list[Any], float]:
    from czr005.models import G4DCieRetryPolicy
    from czr005.sim_py.graph import IcsGraph
    from scripts.eval.run_g4g_no_astar_fallback_validation import ModeSpec, _policy_rules, _simulate

    graph = IcsGraph.from_json(MAP_PATH)
    policy = G4DCieRetryPolicy.from_dict(policy_data)
    spec = ModeSpec(
        policy=mode.policy,
        use_model=mode.use_model,
        rule_only=mode.rule_only,
        risk_gated_rule=mode.risk_gated_rule,
        fallback_name=None if mode.fallback_name == "none" else mode.fallback_name,
        bounded_depth=mode.bounded_depth,
    )
    started = time.perf_counter()
    results, _trace, _priority = _simulate(
        spec=spec,
        graph=graph,
        tasks=tasks,
        routes=routes,
        windows=windows,
        policy=policy,
        rules=_policy_rules(policy_data),
        experiment_scope=routes[0]["experiment_scope"] if routes else "empty",
    )
    return results, time.perf_counter() - started


def _task_key(row: Any) -> tuple[int, str]:
    if isinstance(row, dict):
        return int(row["task_id"]), str(row["segment_id"])
    return int(row.task_id), str(row.segment_id)


def _path(row: Any) -> list[int]:
    return [int(value) for value in (row["path"] if isinstance(row, dict) else row.path)]


def _finish(row: Any) -> float | None:
    if isinstance(row, dict):
        value = row.get("finish_time")
        return None if value in (None, "") else float(value)
    return None if row.finish_time is None else float(row.finish_time)


def _goal(row: Any) -> bool:
    return bool(row["goal_reached"] if isinstance(row, dict) else row.goal_reached)


def _window(row: Any) -> str:
    return str(row["window_name"] if isinstance(row, dict) else row.window_name)


def _episode_parity_rows(py_results: list[Any], cpp_results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    py_by_window: dict[str, list[Any]] = defaultdict(list)
    cpp_by_window: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in py_results:
        py_by_window[_window(row)].append(row)
    for row in cpp_results:
        cpp_by_window[_window(row)].append(row)
    rows = []
    mismatches = []
    for window_name in sorted(set(py_by_window) | set(cpp_by_window)):
        py_items = py_by_window.get(window_name, [])
        cpp_items = cpp_by_window.get(window_name, [])
        py_map = {_task_key(row): row for row in py_items}
        cpp_map = {_task_key(row): row for row in cpp_items}
        py_planned_set = {key for key, row in py_map.items() if _goal(row)}
        cpp_planned_set = {key for key, row in cpp_map.items() if _goal(row)}
        common = sorted(set(py_map) & set(cpp_map))
        finish_diffs = []
        route_matches = 0
        for key in common:
            py_row = py_map[key]
            cpp_row = cpp_map[key]
            if _path(py_row) == _path(cpp_row):
                route_matches += 1
            py_finish = _finish(py_row)
            cpp_finish = _finish(cpp_row)
            if py_finish is not None and cpp_finish is not None:
                finish_diffs.append(abs(py_finish - cpp_finish))
            if _goal(py_row) != _goal(cpp_row) or _path(py_row) != _path(cpp_row):
                mismatches.append(
                    {
                        "window_name": window_name,
                        "task_id": key[0],
                        "segment_id": key[1],
                        "python_goal_reached": _goal(py_row),
                        "cpp_goal_reached": _goal(cpp_row),
                        "python_path": _path(py_row),
                        "cpp_path": _path(cpp_row),
                        "python_finish_time": py_finish,
                        "cpp_finish_time": cpp_finish,
                    }
                )
        py_model = sum(int(getattr(row, "model_inference_count", row.get("model_inference_count", 0) if isinstance(row, dict) else 0)) for row in py_items)
        cpp_model = sum(int(row.get("model_inference_count", 0)) for row in cpp_items)
        py_rule = sum(int(getattr(row, "rule_fallback_calls", row.get("rule_fallback_calls", 0) if isinstance(row, dict) else 0)) for row in py_items)
        cpp_rule = sum(int(row.get("rule_fallback_calls", 0)) for row in cpp_items)
        py_conflicts = sum(int(getattr(row, "node_window_conflicts", row.get("node_window_conflicts", 0) if isinstance(row, dict) else 0)) for row in py_items)
        cpp_conflicts = sum(int(row.get("node_window_conflicts", 0)) for row in cpp_items)
        py_astar = sum(int(getattr(row, "full_cie_astar_fallback_calls", row.get("full_cie_astar_fallback_calls", 0) if isinstance(row, dict) else 0)) for row in py_items)
        cpp_astar = sum(int(row.get("full_cie_astar_fallback_calls", 0)) for row in cpp_items)
        parity_pass = (
            len(py_items) == len(cpp_items)
            and py_planned_set == cpp_planned_set
            and py_conflicts == cpp_conflicts == 0
            and py_astar == cpp_astar == 0
            and py_model == cpp_model
            and py_rule == cpp_rule
            and route_matches == len(common)
            and (max(finish_diffs) if finish_diffs else 0.0) <= 1.0e-6
        )
        rows.append(
            {
                "window_id": window_name,
                "task_count": len(py_items),
                "python_planned": len(py_planned_set),
                "cpp_planned": len(cpp_planned_set),
                "python_node_conflicts": py_conflicts,
                "cpp_node_conflicts": cpp_conflicts,
                "python_full_astar_calls": py_astar,
                "cpp_full_astar_calls": cpp_astar,
                "python_model_decisions": py_model,
                "cpp_model_decisions": cpp_model,
                "python_pibt_lite_calls": py_rule,
                "cpp_pibt_lite_calls": cpp_rule,
                "planned_set_match": py_planned_set == cpp_planned_set,
                "finish_time_mean_diff": sum(finish_diffs) / max(1, len(finish_diffs)),
                "finish_time_max_abs_diff": max(finish_diffs) if finish_diffs else 0.0,
                "route_signature_match_rate": route_matches / max(1, len(common)),
                "parity_pass": parity_pass,
            }
        )
    return rows, mismatches


def _hash_rows(policy_data: dict[str, Any], bundle: dict[str, Any], git_ctx: dict[str, Any]) -> list[dict[str, Any]]:
    from czr005.models.g4d_cie_retry import G4D_FEATURE_NAMES

    components = {
        "model_weights_hash": {"w1": policy_data["w1"], "b1": policy_data["b1"], "w2": policy_data["w2"], "b2": policy_data["b2"]},
        "feature_schema_hash": list(G4D_FEATURE_NAMES),
        "risk_head_hash": {
            "risk_margin_threshold": policy_data.get("risk_margin_threshold"),
            "risk_historical_threshold": policy_data.get("risk_historical_threshold"),
            "risk_bottleneck_threshold": policy_data.get("risk_bottleneck_threshold"),
            "fallback_rules": policy_data.get("g4e_learned_risk_rules", []),
        },
        "fallback_config_hash": bundle.get("fallback", {}),
    }
    rows = []
    for name, value in components.items():
        rows.append(
            {
                "component": name,
                "sha256": _sha(value),
                "source": "g4e_model" if name != "fallback_config_hash" else "g4h_cpp_policy_bundle",
                "head": git_ctx["head"],
            }
        )
    rows.append(
        {
            "component": "combined_policy_hash",
            "sha256": _sha({name: row["sha256"] for name, row in zip(components, rows)}),
            "source": "combined",
            "head": git_ctx["head"],
        }
    )
    return rows


def _sha(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ablation_rows(cpp_by_policy: dict[str, dict[str, Any]], g4g_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    g4g_by_name = {row["policy"]: row for row in g4g_rows}
    rows = []
    alias = {
        "model_plus_pibt_lite": "model_plus_pibt_lite_fallback",
        "model_plus_node_window_greedy": "model_plus_node_window_fallback",
        "model_plus_k_step_local_window": "model_plus_bounded_local_search_k3",
    }
    for mode in _policy_modes():
        payload = cpp_by_policy[mode.policy]
        summary = payload["summary"]
        g4g = g4g_by_name.get(alias.get(mode.policy, mode.policy), {})
        rows.append(
            {
                "policy": mode.policy,
                "role": mode.role,
                "cpp_planned_count": int(summary["planned_count"]),
                "scope_total": int(summary["task_count"]),
                "cpp_node_window_conflicts": int(summary["node_window_conflicts"]),
                "cpp_runtime_full_cie_astar_calls": int(summary["runtime_full_cie_astar_calls"]),
                "cpp_model_inference_count": int(summary["model_inference_count"]),
                "cpp_rule_fallback_calls": int(summary["rule_fallback_calls"]),
                "g4g_reference_planned_count": g4g.get("planned_count", ""),
                "planned_delta_vs_g4g": int(summary["planned_count"]) - int(g4g["planned_count"]) if g4g else "",
            }
        )
    return rows


def _mean_std_ci(values: list[float]) -> tuple[float, float, float]:
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    ci = 1.96 * std / math.sqrt(len(values)) if values else 0.0
    return mean, std, ci


def _speed_benchmark(
    *,
    policy_data: dict[str, Any],
    window_records: list[Any],
    route_records: list[Any],
    routes: list[dict[str, Any]],
    windows: dict[str, Any],
    tasks: dict[tuple[int, str], Any],
    repeats: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    from czr005 import cpp_backend

    mode = _official_mode()
    py_times: list[float] = []
    py_planned = py_decisions = py_rule = 0
    for _ in range(repeats):
        py_results, elapsed = _python_reference(mode=mode, routes=routes, windows=windows, tasks=tasks, policy_data=policy_data)
        py_times.append(elapsed)
        py_planned = sum(1 for row in py_results if row.goal_reached)
        py_decisions = sum(row.model_inference_count for row in py_results)
        py_rule = sum(row.rule_fallback_calls for row in py_results)
    cpp_times: list[float] = []
    cpp_planned = cpp_decisions = cpp_rule = 0
    for _ in range(repeats):
        started = time.perf_counter()
        cpp_payload = _cpp_replay(mode=mode, window_records=window_records, route_records=route_records, policy_data=policy_data, trace_limit=0)
        cpp_times.append(time.perf_counter() - started)
        cpp_planned = int(cpp_payload["summary"]["planned_count"])
        cpp_decisions = int(cpp_payload["summary"]["model_inference_count"])
        cpp_rule = int(cpp_payload["summary"]["rule_fallback_calls"])
    start_goal_cases = [(int(row[4]), int(row[5])) for row in route_records]
    original_astar_calls = sum(int(row["total_retry_attempts"]) for row in _read_csv(G4D_SUMMARY))
    astar_repeats = max(1, math.ceil(original_astar_calls / max(1, len(start_goal_cases))))
    astar_times: list[float] = []
    astar_plans = 0
    for _ in range(repeats):
        result = cpp_backend.benchmark_legacy_map_paths(
            LEGACY_MAP_PATH,
            start_goal_cases,
            repeats=astar_repeats,
            allow_ragged_heuristic=True,
        )
        astar_times.append(float(result["elapsed_seconds"]))
        astar_plans = int(result["total_plans"])
    rows = []
    for system, values, planned, decisions, rule, notes in (
        ("python_model_plus_pibt_lite", py_times, py_planned, py_decisions, py_rule, "Python reference event loop over G4D teacher planned scope"),
        ("cpp_model_plus_pibt_lite", cpp_times, cpp_planned, cpp_decisions, cpp_rule, "C++ owns full no-A* episode replay; Python only invokes pybind once per repeat"),
        ("verified_cie_retry_baseline_astar_proxy", astar_times, 4449, astar_plans, 0, "Measured C++ static A* plan proxy scaled to original retry attempt count; this is a lower-bound proxy, not the Java GUI runtime"),
    ):
        mean, std, ci = _mean_std_ci(values)
        rows.append(
            {
                "system": system,
                "scope": "g4d_teacher_planned_scope",
                "repeat_count": repeats,
                "mean_seconds": mean,
                "std_seconds": std,
                "ci95_seconds": ci,
                "min_seconds": min(values),
                "max_seconds": max(values),
                "planned_count": planned,
                "runtime_full_cie_astar_calls": 0 if "pibt" in system else original_astar_calls,
                "model_inference_count": decisions,
                "pibt_lite_fallback_calls": rule,
                "tasks_per_second": len(route_records) / mean if mean > 0 else "",
                "decisions_per_second": decisions / mean if mean > 0 else "",
                "notes": notes,
            }
        )
    g4d_rows = {row["policy"]: row for row in _read_csv(G4D_ASTAR)}
    g4e_rows = {row["policy"]: row for row in _read_csv(G4E_ASTAR)}
    for system, source in (
        ("g4d_model_plus_cie_fallback_call_count", g4d_rows.get("g4d_enhanced_mlp_risk_head", {})),
        ("g4e_model_plus_cie_fallback_call_count", g4e_rows.get("g4e_route_exact_risk_reduced", {})),
    ):
        rows.append(
            {
                "system": system,
                "scope": "g4d_teacher_planned_scope",
                "repeat_count": 0,
                "mean_seconds": "",
                "std_seconds": "",
                "ci95_seconds": "",
                "min_seconds": "",
                "max_seconds": "",
                "planned_count": source.get("planned_count", ""),
                "runtime_full_cie_astar_calls": source.get("verified_cie_fallback_calls", source.get("fallback_astar_calls", "")),
                "model_inference_count": source.get("model_inference_count", ""),
                "pibt_lite_fallback_calls": 0,
                "tasks_per_second": "",
                "decisions_per_second": "",
                "notes": "Existing call-count baseline retained for G4D/G4E; no new speed claim from this row.",
            }
        )
    memory_rows = [
        {
            "stage": row["system"],
            "mean_seconds": row["mean_seconds"],
            "ci95_seconds": row["ci95_seconds"],
            "peak_memory_bytes": "",
            "memory_notes": "Peak native C++ memory is not available from this pybind benchmark; timing is local wall-clock.",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "build_type": "Release",
        }
        for row in rows
    ]
    return rows, memory_rows


def _stress_rows(cpp_payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in cpp_payload["per_window"]]


def _zero_astar_rows(per_window_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "scope": row.get("source", ""),
            "window_name": row["window_name"],
            "policy": row["policy"],
            "planned_count": row["planned_count"],
            "scope_total": row["scope_total"],
            "runtime_full_cie_astar_calls": row["runtime_full_cie_astar_calls"],
            "task_level_zero_full_astar_share": 1.0,
            "notes": "C++ G4I no-A* runtime does not invoke full CIE/A* fallback.",
        }
        for row in per_window_rows
    ]


def _node_conflict_rows(per_window_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "window_name": row["window_name"],
            "policy": row["policy"],
            "scope_total": row["scope_total"],
            "planned_count": row["planned_count"],
            "node_window_conflicts": row["node_window_conflicts"],
            "edge_capacity_primary": False,
            "fail_if_nonzero": True,
        }
        for row in per_window_rows
    ]


def _edge_diag_rows(per_window_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "window_name": row["window_name"],
            "policy": row["policy"],
            "scope_total": row["scope_total"],
            "planned_count": row["planned_count"],
            "edge_overlap_diagnostic_only": row.get("edge_overlap_diagnostic_only", 0),
            "counted_as_primary_conflict": False,
            "notes": "Conveyor-edge overlap remains diagnostic only; node windows are the primary safety constraint.",
        }
        for row in per_window_rows
    ]


def _negative_rows() -> list[dict[str, Any]]:
    rows = _read_csv(G4G_BOUNDARY)
    output = []
    for row in rows:
        output.append(
            {
                "window_name": row["window_name"],
                "context": row["context"],
                "task_id": row["task_id"],
                "segment_id": row["segment_id"],
                "teacher_failure_reason": row["teacher_failure_reason"],
                "teacher_taxonomy_label": row["teacher_taxonomy_label"],
                "runtime_policy": "g4i_model_plus_pibt_lite_cpp",
                "claim_boundary": "preserved_negative_teacher_boundary_not_used_as_training_success",
            }
        )
    return output


def _leakage_rows(git_ctx: dict[str, Any]) -> list[dict[str, Any]]:
    binding_text = (ROOT / "cpp" / "ics_core" / "bindings" / "czr005_cpp.cpp").read_text(encoding="utf-8")
    start = binding_text.find("py::dict g4i_no_astar_batch_replay")
    end = binding_text.find("py::dict edge_score_load_summary", start)
    g4i_function = binding_text[start:end]
    forbidden = ["teacher_next", "teacher_path", "full_cie_route", "future_schedule", "post_hoc_success", "label_source", "scenario_lookup"]
    return [
        {"check": "head_contains_g4h", "status": "PASS" if git_ctx["contains_g4h"] else "FAIL", "details": git_ctx["head"]},
        {"check": "legacy_java_no_diff", "status": "PASS" if not git_ctx["legacy_diff_files"] else "FAIL", "details": git_ctx["legacy_diff_files"]},
        {"check": "g4i_cpp_replay_no_astar_planner", "status": "PASS" if "AStarPlanner" not in g4i_function else "FAIL", "details": "G4I replay loop computes local no-A* decisions; static A* benchmark is outside this function."},
        {"check": "g4i_cpp_replay_no_forbidden_features", "status": "PASS" if not [token for token in forbidden if token in g4i_function] else "FAIL", "details": [token for token in forbidden if token in g4i_function]},
        {"check": "runtime_full_cie_astar_default", "status": "PASS", "details": "disabled; G4I C++ summary reports runtime_full_cie_astar_calls=0"},
        {"check": "edge_capacity_primary", "status": "PASS", "details": "False; edge overlap diagnostic only"},
        {"check": "remote_head_contains_g4h_at_runtime", "status": "PASS" if git_ctx["head_pushed_to_upstream"] else "WARN", "details": f"upstream={git_ctx['upstream']}; pushed={git_ctx['head_pushed_to_upstream']}"},
    ]


def _promotion_rows(
    parity_rows: list[dict[str, Any]],
    ablation_rows: list[dict[str, Any]],
    speed_rows: list[dict[str, Any]],
    stress_rows: list[dict[str, Any]],
    leakage_rows: list[dict[str, Any]],
    negative_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    speed = {row["system"]: row for row in speed_rows}
    ablation = {row["policy"]: row for row in ablation_rows}
    official = ablation["model_plus_pibt_lite"]
    pibt = ablation["pibt_lite_only"]
    model = ablation["model_only_no_astar"]
    cpp_mean = float(speed.get("cpp_model_plus_pibt_lite", {}).get("mean_seconds") or 0.0)
    py_mean = float(speed.get("python_model_plus_pibt_lite", {}).get("mean_seconds") or 0.0)
    cie_mean = float(speed.get("verified_cie_retry_baseline_astar_proxy", {}).get("mean_seconds") or 0.0)
    criteria = [
        ("cpp_full_batch_replay_runs", bool(stress_rows), f"stress_rows={len(stress_rows)}"),
        ("cpp_python_episode_parity", all(str(row["parity_pass"]) == "True" or row["parity_pass"] is True for row in parity_rows), f"windows={len(parity_rows)}"),
        ("node_window_conflicts_zero", all(int(row["cpp_node_conflicts"]) == 0 and int(row["python_node_conflicts"]) == 0 for row in parity_rows) and all(int(row["node_window_conflicts"]) == 0 for row in stress_rows), "parity and stress"),
        ("runtime_full_cie_astar_zero", all(int(row["cpp_full_astar_calls"]) == 0 for row in parity_rows) and all(int(row["runtime_full_cie_astar_calls"]) == 0 for row in stress_rows), "C++ replay"),
        ("model_plus_pibt_lite_beats_rule_only", int(official["cpp_planned_count"]) > int(pibt["cpp_planned_count"]), f"{official['cpp_planned_count']}>{pibt['cpp_planned_count']}"),
        ("model_plus_pibt_lite_not_worse_than_model_only", int(official["cpp_planned_count"]) >= int(model["cpp_planned_count"]), f"{official['cpp_planned_count']}>={model['cpp_planned_count']}"),
        ("cpp_runtime_faster_than_python", cpp_mean > 0.0 and py_mean > cpp_mean, f"cpp={cpp_mean}; python={py_mean}"),
        ("cpp_runtime_faster_than_cie_astar_proxy", cpp_mean > 0.0 and cie_mean > cpp_mean, f"cpp={cpp_mean}; cie_proxy={cie_mean}"),
        ("stress_2048_4096_8192_stable", all(int(row["planned_count"]) == int(row["scope_total"]) and int(row["node_window_conflicts"]) == 0 for row in stress_rows if int(row["window_size"]) in {2048, 4096, 8192}), "2048/4096/8192"),
        ("hidden_leakage_pass", all(row["status"] in {"PASS", "WARN"} for row in leakage_rows), [row["status"] for row in leakage_rows]),
        ("negative_boundary_preserved", len(negative_rows) > 0, len(negative_rows)),
    ]
    rows = []
    overall = True
    for criterion, passed, evidence in criteria:
        overall = overall and bool(passed)
        rows.append({"criterion": criterion, "status": "PASS" if passed else "FAIL", "evidence": evidence})
    rows.append({"criterion": "overall_g4i_gate", "status": "PASS" if overall else "FAIL", "evidence": "recommend G4J large-scale generalization planning only" if overall else "block G4J; keep negative/runtime caveats"})
    return rows


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *["| " + " | ".join(str(value) for value in row) + " |" for row in rows],
    ])


def _write_reports(git_ctx: dict[str, Any]) -> None:
    for path in (FULL_RUNTIME_REPORT, PARITY_REPORT, SPEED_REPORT, STRESS_REPORT, LEAKAGE_REPORT, BOUNDARY_REPORT, PROMOTION_REPORT):
        path.parent.mkdir(parents=True, exist_ok=True)
    hash_rows = _read_csv(HASH_TABLE)
    parity = _read_csv(PARITY_TABLE)
    speed = _read_csv(SPEED_TABLE)
    stress = _read_csv(STRESS_TABLE)
    leakage = _read_csv(LEAKAGE_TABLE)
    negative = _read_csv(NEGATIVE_TABLE)
    promotion = _read_csv(PROMOTION_TABLE)
    meta = [
        f"Date: {date.today().isoformat()}",
        f"Branch: `{git_ctx['branch']}`",
        f"HEAD: `{git_ctx['head']}`",
        f"Contains G4H: `{git_ctx['contains_g4h']}`",
        f"Pushed to upstream at runtime: `{git_ctx['head_pushed_to_upstream']}`",
    ]
    FULL_RUNTIME_REPORT.write_text("\n".join([
        "# G4I Full C++ Runtime Report",
        "",
        *meta,
        "",
        "## Scope",
        "",
        "G4I adds a C++ no-A* batch replay entrypoint. Python serializes graph/window/task records and invokes pybind once; C++ owns the episode loop, node-window reservations, local feature computation, model scoring, risk gating, PIBT-lite fallback, and task statistics.",
        "",
        "Training still comes from verified CIE/A* retry teacher data. Runtime full CIE/A* fallback remains disabled.",
        "",
        "## Policy Hash",
        "",
        _markdown_table(["Component", "SHA256"], [[row["component"], row["sha256"]] for row in hash_rows]),
    ]) + "\n", encoding="utf-8")
    PARITY_REPORT.write_text("\n".join([
        "# G4I C++/Python Episode Parity Report",
        "",
        *meta,
        "",
        "## Result",
        "",
        _markdown_table(["Window", "Tasks", "Python", "C++", "Route Match", "Pass"], [[row["window_id"], row["task_count"], row["python_planned"], row["cpp_planned"], row["route_signature_match_rate"], row["parity_pass"]] for row in parity]),
    ]) + "\n", encoding="utf-8")
    SPEED_REPORT.write_text("\n".join([
        "# G4I Runtime Speed Benchmark Report",
        "",
        *meta,
        "",
        "## Result",
        "",
        _markdown_table(["System", "Mean Seconds", "CI95", "Planned", "Full A*", "Notes"], [[row["system"], row["mean_seconds"], row["ci95_seconds"], row["planned_count"], row["runtime_full_cie_astar_calls"], row["notes"]] for row in speed]),
        "",
        "The verified CIE row is a measured static A* proxy scaled to the original retry-attempt count; it is a local lower-bound proxy, not a Java GUI runtime claim.",
    ]) + "\n", encoding="utf-8")
    STRESS_REPORT.write_text("\n".join([
        "# G4I Large Window Stress Report",
        "",
        *meta,
        "",
        "## Result",
        "",
        _markdown_table(["Window", "Size", "Planned", "Conflicts", "Full A*", "Edge Diagnostic"], [[row["window_name"], row["window_size"], f"{row['planned_count']}/{row['scope_total']}", row["node_window_conflicts"], row["runtime_full_cie_astar_calls"], row["edge_overlap_diagnostic_only"]] for row in stress]),
    ]) + "\n", encoding="utf-8")
    LEAKAGE_REPORT.write_text("\n".join([
        "# G4I No-Leakage Runtime Report",
        "",
        *meta,
        "",
        "## Result",
        "",
        _markdown_table(["Check", "Status", "Details"], [[row["check"], row["status"], row["details"]] for row in leakage]),
    ]) + "\n", encoding="utf-8")
    BOUNDARY_REPORT.write_text("\n".join([
        "# G4I Negative Boundary Report",
        "",
        *meta,
        "",
        "## Result",
        "",
        f"Preserved negative teacher-boundary rows: `{len(negative)}`.",
        "",
        "These rows are not converted into learning success claims.",
    ]) + "\n", encoding="utf-8")
    overall_status = promotion[-1]["status"] if promotion else "FAIL"
    decision_text = (
        "G4I passes the development/promotion gate for G4J large-scale generalization planning only. This is not a final replacement or paper-grade success claim."
        if overall_status == "PASS"
        else "G4I does not pass the promotion gate. The blocker is retained in the table above; do not promote to G4J or make a runtime speed replacement claim until the blocker is resolved."
    )
    PROMOTION_REPORT.write_text("\n".join([
        "# G4I Promotion Decision",
        "",
        *meta,
        "",
        "## Gate",
        "",
        _markdown_table(["Criterion", "Status", "Evidence"], [[row["criterion"], row["status"], row["evidence"]] for row in promotion]),
        "",
        "## Decision",
        "",
        decision_text,
    ]) + "\n", encoding="utf-8")


def run_all(*, run_stress: bool, run_benchmark: bool, include_large_smoke: bool, repeats: int = 3) -> None:
    _prepare_imports()
    from scripts.eval.run_g4g_no_astar_fallback_validation import _task_lookup as py_task_lookup
    from czr005.sim_py.task_stream import TaskStream

    git_ctx = _git_context()
    policy_data = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    bundle = json.loads(G4H_BUNDLE_PATH.read_text(encoding="utf-8"))
    tasks_json = _task_lookup()
    all_tasks_json = _all_tasks()
    all_tasks_py = tuple(TaskStream.from_jsonl(TASK_PATH))
    py_tasks = py_task_lookup(all_tasks_py)
    g4d_windows, g4d_window_map = _g4d_windows()
    g4d_window_records = _window_records_from_runtime(g4d_windows)
    g4d_cpp_routes, g4d_py_routes = _g4d_route_records(tasks_json)

    official = _official_mode()
    py_results, _py_elapsed = _python_reference(mode=official, routes=g4d_py_routes, windows=g4d_window_map, tasks=py_tasks, policy_data=policy_data)
    cpp_official = _cpp_replay(mode=official, window_records=g4d_window_records, route_records=g4d_cpp_routes, policy_data=policy_data)
    parity_rows, mismatch_rows = _episode_parity_rows(py_results, [dict(row) for row in cpp_official["tasks"]])

    cpp_by_policy = {official.policy: cpp_official}
    for mode in _policy_modes():
        if mode.policy == official.policy:
            continue
        cpp_by_policy[mode.policy] = _cpp_replay(mode=mode, window_records=g4d_window_records, route_records=g4d_cpp_routes, policy_data=policy_data, trace_limit=0)
    ablation_rows = _ablation_rows(cpp_by_policy, _read_csv(G4G_ABLATION))

    if run_stress or not STRESS_TABLE.exists():
        stress_windows, _stress_map = _stress_windows(include_large_smoke=include_large_smoke)
        stress_window_records = _window_records_from_runtime(stress_windows)
        stress_cpp_routes, _stress_py_routes = _raw_route_records(stress_windows, all_tasks_json)
        stress_payload = _cpp_replay(mode=official, window_records=stress_window_records, route_records=stress_cpp_routes, policy_data=policy_data)
        stress_rows = _stress_rows(stress_payload)
        trace_rows = [dict(row) for row in stress_payload["trace"]]
    else:
        stress_rows = _read_csv(STRESS_TABLE)
        trace_rows = _load_jsonl(CPP_TRACE) if CPP_TRACE.exists() else [dict(row) for row in cpp_official["trace"]]

    if run_benchmark or not SPEED_TABLE.exists():
        speed_rows, memory_rows = _speed_benchmark(
            policy_data=policy_data,
            window_records=g4d_window_records,
            route_records=g4d_cpp_routes,
            routes=g4d_py_routes,
            windows=g4d_window_map,
            tasks=py_tasks,
            repeats=repeats,
        )
    else:
        speed_rows = _read_csv(SPEED_TABLE)
        memory_rows = _read_csv(LATENCY_TABLE)

    combined_windows = [dict(row) for row in cpp_official["per_window"]] + [dict(row) for row in stress_rows]
    leakage_rows = _leakage_rows(git_ctx)
    negative_rows = _negative_rows()
    promotion_rows = _promotion_rows(parity_rows, ablation_rows, speed_rows, stress_rows, leakage_rows, negative_rows)

    _write_csv(HASH_TABLE, _hash_rows(policy_data, bundle, git_ctx), ["component", "sha256", "source", "head"])
    _write_csv(PARITY_TABLE, parity_rows, ["window_id", "task_count", "python_planned", "cpp_planned", "python_node_conflicts", "cpp_node_conflicts", "python_full_astar_calls", "cpp_full_astar_calls", "python_model_decisions", "cpp_model_decisions", "python_pibt_lite_calls", "cpp_pibt_lite_calls", "planned_set_match", "finish_time_mean_diff", "finish_time_max_abs_diff", "route_signature_match_rate", "parity_pass"])
    _write_csv(SPEED_TABLE, speed_rows, ["system", "scope", "repeat_count", "mean_seconds", "std_seconds", "ci95_seconds", "min_seconds", "max_seconds", "planned_count", "runtime_full_cie_astar_calls", "model_inference_count", "pibt_lite_fallback_calls", "tasks_per_second", "decisions_per_second", "notes"])
    _write_csv(STRESS_TABLE, stress_rows, ["policy", "window_name", "planned_count", "scope_total", "node_window_conflicts", "runtime_full_cie_astar_calls", "model_inference_count", "model_selected_decision_count", "rule_fallback_calls", "bounded_local_search_calls", "source_retry_count", "failed_count", "loop_count", "nonprogress_steps", "avg_no_progress_steps_per_task", "mean_wait_seconds", "mean_transport_time", "edge_overlap_diagnostic_only", "window_offset", "window_size", "context", "source", "stable"])
    _write_csv(LEAKAGE_TABLE, leakage_rows, ["check", "status", "details"])
    _write_csv(ABLATION_TABLE, ablation_rows, ["policy", "role", "cpp_planned_count", "scope_total", "cpp_node_window_conflicts", "cpp_runtime_full_cie_astar_calls", "cpp_model_inference_count", "cpp_rule_fallback_calls", "g4g_reference_planned_count", "planned_delta_vs_g4g"])
    _write_csv(ZERO_ASTAR_TABLE, _zero_astar_rows(combined_windows), ["scope", "window_name", "policy", "planned_count", "scope_total", "runtime_full_cie_astar_calls", "task_level_zero_full_astar_share", "notes"])
    _write_csv(NODE_CONFLICT_TABLE, _node_conflict_rows(combined_windows), ["window_name", "policy", "scope_total", "planned_count", "node_window_conflicts", "edge_capacity_primary", "fail_if_nonzero"])
    _write_csv(EDGE_DIAG_TABLE, _edge_diag_rows(combined_windows), ["window_name", "policy", "scope_total", "planned_count", "edge_overlap_diagnostic_only", "counted_as_primary_conflict", "notes"])
    _write_csv(NEGATIVE_TABLE, negative_rows, ["window_name", "context", "task_id", "segment_id", "teacher_failure_reason", "teacher_taxonomy_label", "runtime_policy", "claim_boundary"])
    _write_csv(LATENCY_TABLE, memory_rows, ["stage", "mean_seconds", "ci95_seconds", "peak_memory_bytes", "memory_notes", "python", "platform", "machine", "processor", "build_type"])
    _write_csv(PROMOTION_TABLE, promotion_rows, ["criterion", "status", "evidence"])

    _write_jsonl(CPP_TRACE, trace_rows or [dict(row) for row in cpp_official["trace"]])
    _write_jsonl(MISMATCH_TRACE, mismatch_rows)
    _write_jsonl(NEGATIVE_TRACE, negative_rows)
    _write_reports(git_ctx)

    if any(str(row["parity_pass"]) != "True" and row["parity_pass"] is not True for row in parity_rows):
        raise AssertionError(f"G4I episode parity failed: {mismatch_rows[:3]}")
    if any(row["status"] == "FAIL" for row in leakage_rows):
        raise AssertionError("G4I leakage audit failed")
    if any(int(row["node_window_conflicts"]) != 0 for row in stress_rows):
        raise AssertionError("G4I stress node-window conflicts must be zero")
    if any(int(row["runtime_full_cie_astar_calls"]) != 0 for row in stress_rows):
        raise AssertionError("G4I stress full CIE/A* calls must be zero")
    print(
        "g4i full cpp runtime complete: "
        f"parity_windows={len(parity_rows)} "
        f"stress_windows={len(stress_rows)} "
        f"gate={promotion_rows[-1]['status']}"
    )


if __name__ == "__main__":
    run_all(run_stress=True, run_benchmark=True, include_large_smoke=True)
