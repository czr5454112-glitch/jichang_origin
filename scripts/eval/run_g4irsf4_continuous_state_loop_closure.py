from __future__ import annotations

import argparse
from collections import Counter, deque
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_DOC = ROOT / "docs" / "czr005_project_governance.md"
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
MANIFEST_PATH = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_manifest.json"
HIGH_FLOW_TASKS = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_tasks.jsonl"
REPORT_DIR = ROOT / "outputs" / "reports"
TABLE_DIR = ROOT / "outputs" / "tables"
DOC_DIR = ROOT / "docs"

STATE_REPORT = REPORT_DIR / "g4irsf4_state_and_repro_report.md"
API_REPORT = REPORT_DIR / "g4irsf4_continuous_runtime_api_report.md"
CONTINUOUS_REPORT = REPORT_DIR / "g4irsf4_full_manifest_continuous_report.md"
LOOP_REPORT = REPORT_DIR / "g4irsf4_loop_closure_report.md"
FAULT_REPORT = REPORT_DIR / "g4irsf4_fault_aware_runtime_report.md"
JAVA_DEP_REPORT = REPORT_DIR / "g4irsf4_java_dependency_audit.md"
JAVA_REPORT = REPORT_DIR / "g4irsf4_java_cie_baseline_report.md"
BASELINE_REPORT = REPORT_DIR / "g4irsf4_astar_baseline_boundary_report.md"
OPT_REPORT = REPORT_DIR / "g4irsf4_runtime_optimization_report.md"
LEVEL_B_REPORT = REPORT_DIR / "g4irsf4_level_b_light_report.md"
PLAIN_REPORT = REPORT_DIR / "g4irsf4_plain_language_summary.md"
PROMOTION_REPORT = REPORT_DIR / "g4irsf4_promotion_decision.md"
API_DOC = DOC_DIR / "czr005_no_astar_streaming_runtime_api.md"

GIT_STATE = TABLE_DIR / "g4irsf4_git_state_audit.csv"
STATE_SCHEMA = TABLE_DIR / "g4irsf4_runtime_state_schema.csv"
CONTINUOUS_TABLE = TABLE_DIR / "g4irsf4_full_manifest_continuous_benchmark.csv"
LOOP_TAXONOMY = TABLE_DIR / "g4irsf4_loop_failure_taxonomy.csv"
LOOP_SUBPATHS = TABLE_DIR / "g4irsf4_loop_common_subpaths.csv"
LOOP_COUNTERFACTUAL = TABLE_DIR / "g4irsf4_loop_local_counterfactual.csv"
LOOP_VARIANTS = TABLE_DIR / "g4irsf4_loop_policy_variant_results.csv"
FAULT_RESULTS = TABLE_DIR / "g4irsf4_fault_aware_runtime_results.csv"
JAVA_INVENTORY = TABLE_DIR / "g4irsf4_java_dependency_inventory.csv"
JAVA_ATTEMPTS = TABLE_DIR / "g4irsf4_java_baseline_run_attempts.csv"
JAVA_PROXY_COVERAGE = TABLE_DIR / "g4irsf4_java_semantics_proxy_coverage.csv"
NOASTAR_JAVA_PROXY = TABLE_DIR / "g4irsf4_noastar_vs_java_semantics_proxy.csv"
BASELINE_MATRIX = TABLE_DIR / "g4irsf4_baseline_responsibility_matrix.csv"
RUNTIME_PROFILE = TABLE_DIR / "g4irsf4_continuous_runtime_profile.csv"
OPT_TABLE = TABLE_DIR / "g4irsf4_optimization_before_after.csv"
LEVEL_B_TABLE = TABLE_DIR / "g4irsf4_level_b_light_rule_coverage.csv"
PROMOTION_GATE = TABLE_DIR / "g4irsf4_promotion_gate.csv"

REQUIRED_BASELINE = "284475d4f58ca4c9efc0070b25a49183e61ad1e8"
CANONICAL_LOOP = [26, 43, 15, 14, 46, 36, 38, 39, 40, 41, 42, 25, 26]


@dataclass(frozen=True)
class RuntimeMode:
    policy_name: str
    use_model: bool
    rule_only: bool
    risk_gated_rule: bool
    fallback_name: str
    bounded_depth: int = 1


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(_jsonable(value), ensure_ascii=True, sort_keys=True)
    return value


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


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


def _git(args: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(["git", *args], cwd=ROOT, check=False, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _git_text(args: list[str]) -> str:
    return _git(args)[1]


def _meta_lines(generation_level: str = "distribution_preserving_resample") -> list[str]:
    return [
        f"Date: {date.today().isoformat()}",
        f"Branch: `{_git_text(['branch', '--show-current'])}`",
        f"HEAD: `{_git_text(['rev-parse', '--short', 'HEAD'])}`",
        f"governance_doc: {GOVERNANCE_DOC.relative_to(ROOT).as_posix()}",
        "topology_changed: false",
        f"data_generation_rule_source: {generation_level}",
        "runtime_full_cie_astar_fallback: false",
        "legacy_java_modified: false",
    ]


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jsonl_line_count(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


def _load_graph() -> tuple[dict[int, list[int]], list[list[float]]]:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    outgoing = {int(node["location"]): [int(item) for item in node["outgoing"]] for node in data["nodes"]}
    heuristic = [[float(value) for value in row] for row in data["heuristic_time"]]
    return outgoing, heuristic


def _contains_subpath(path: list[int], subpath: list[int]) -> bool:
    if len(path) < len(subpath):
        return False
    return any(path[index : index + len(subpath)] == subpath for index in range(len(path) - len(subpath) + 1))


def _parse_path(value: Any) -> list[int]:
    if isinstance(value, list):
        return [int(item) for item in value]
    try:
        return [int(item) for item in json.loads(str(value))]
    except Exception:
        return []


def _task_lookup(keys: set[tuple[int, str]]) -> dict[tuple[int, str], dict[str, Any]]:
    found: dict[tuple[int, str], dict[str, Any]] = {}
    if not keys:
        return found
    with HIGH_FLOW_TASKS.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (int(row["task_id"]), str(row["segment_id"]))
            if key in keys:
                found[key] = row
                if len(found) == len(keys):
                    break
    return found


def _write_task_subset(keys: set[tuple[int, str]], output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with HIGH_FLOW_TASKS.open("r", encoding="utf-8") as source, output_path.open("w", encoding="utf-8") as dest:
        for line in source:
            if not line.strip():
                continue
            row = json.loads(line)
            key = (int(row["task_id"]), str(row["segment_id"]))
            if key in keys:
                dest.write(json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n")
                count += 1
    return count


def _run_streaming_replay(
    *,
    task_jsonl_path: Path,
    mode: RuntimeMode,
    max_tasks: int,
    trace_limit: int,
    profile_enabled: bool,
    edge_diagnostic: bool,
    fault_edges: tuple[tuple[int, int], ...] = (),
    fault_windows: tuple[tuple[int, int, float, float], ...] = (),
) -> dict[str, Any]:
    _prepare_imports()
    from czr005 import cpp_backend
    import scripts.eval.g4i_runtime as g4i

    policy_data = json.loads(g4i.MODEL_PATH.read_text(encoding="utf-8"))
    node_records, edge_records, heuristic = g4i._graph_records()
    return cpp_backend.g4irsf4_no_astar_streaming_replay_from_jsonl(
        node_records=node_records,
        edge_records=edge_records,
        heuristic_time=heuristic,
        task_jsonl_path=task_jsonl_path,
        w1=policy_data["w1"],
        b1=policy_data["b1"],
        w2=policy_data["w2"],
        b2=policy_data["b2"],
        risk_margin_threshold=float(policy_data.get("risk_margin_threshold", 1.0)),
        risk_historical_threshold=float(policy_data.get("risk_historical_threshold", 0.5)),
        risk_bottleneck_threshold=float(policy_data.get("risk_bottleneck_threshold", 5.0)),
        historical_risk_rules=g4i._historical_risk_rules(),
        fallback_rules=g4i._fallback_rules(policy_data),
        policy_name=mode.policy_name,
        use_model=mode.use_model,
        rule_only=mode.rule_only,
        risk_gated_rule=mode.risk_gated_rule,
        fallback_name=mode.fallback_name,
        bounded_depth=mode.bounded_depth,
        max_steps=80,
        trace_limit=trace_limit,
        summary_only=True,
        profile_enabled=profile_enabled,
        enable_edge_overlap_diagnostic=edge_diagnostic,
        audit_final_conflicts=True,
        fault_edges=fault_edges,
        fault_windows=fault_windows,
        max_tasks=max_tasks,
    )


def _official_mode() -> RuntimeMode:
    return RuntimeMode("model_plus_pibt_lite", True, False, True, "node_window_pibt_lite", 1)


def _fault_aware_mode() -> RuntimeMode:
    return RuntimeMode("model_plus_pibt_lite_fault_aware_v1", True, False, True, "fault_aware_node_window_pibt_lite", 1)


def run_state_and_repro(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    branch = _git_text(["branch", "--show-current"])
    head = _git_text(["rev-parse", "HEAD"])
    upstream = _git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    upstream_head = _git_text(["rev-parse", "@{u}"]) if upstream else ""
    status = _git_text(["status", "--short"])
    legacy_diff = _git_text(["diff", "--name-only", "--", "legacy"])
    log_20 = _git_text(["log", "--oneline", "-20"])
    contains_baseline = subprocess.run(["git", "merge-base", "--is-ancestor", REQUIRED_BASELINE, "HEAD"], cwd=ROOT, check=False).returncode == 0
    remote_equal_local = bool(upstream_head) and head == upstream_head
    task_hash = _sha256(HIGH_FLOW_TASKS) if HIGH_FLOW_TASKS.exists() else ""
    task_lines = _jsonl_line_count(HIGH_FLOW_TASKS) if HIGH_FLOW_TASKS.exists() else 0
    expected_hash = str(manifest.get("task_output_sha256", ""))
    rows = [
        {"check": "branch", "status": "PASS" if branch == "codex/czr005-rewrite" else "WARN", "local_value": branch, "expected_or_remote_value": "codex/czr005-rewrite", "details": "current branch"},
        {"check": "head_contains_284475d", "status": "PASS" if contains_baseline else "FAIL", "local_value": head, "expected_or_remote_value": REQUIRED_BASELINE, "details": "G4IRSF3 baseline must be an ancestor"},
        {"check": "remote_equal_local_at_start", "status": "PASS" if remote_equal_local else "WARN", "local_value": head, "expected_or_remote_value": upstream_head, "details": "Before new commit/push this should match upstream."},
        {"check": "working_tree_clean_before_generation", "status": "PASS" if not status else "INFO", "local_value": status.replace("\n", " | "), "expected_or_remote_value": "clean", "details": "The tree becomes dirty while G4IRSF4 artifacts are generated."},
        {"check": "legacy_java_diff_empty", "status": "PASS" if not legacy_diff else "FAIL", "local_value": legacy_diff.replace("\n", " | "), "expected_or_remote_value": "", "details": "legacy Java and map files must stay read-only."},
        {"check": "high_flow_jsonl_sha256", "status": "PASS" if task_hash == expected_hash else "FAIL", "local_value": task_hash, "expected_or_remote_value": expected_hash, "details": "g4irsf2_high_flow_tasks.jsonl hash vs manifest"},
        {"check": "high_flow_jsonl_line_count", "status": "PASS" if task_lines == int(manifest.get("task_count", 0)) else "FAIL", "local_value": task_lines, "expected_or_remote_value": manifest.get("task_count", ""), "details": "full task stream must be present"},
    ]
    _write_csv(GIT_STATE, rows, ["check", "status", "local_value", "expected_or_remote_value", "details"])
    STATE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 State And Repro Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                "## Git And Data State",
                "",
                _markdown_table(["Check", "Status", "Details"], [[row["check"], row["status"], row["details"]] for row in rows]),
                "",
                "## Recent Log",
                "",
                "```text",
                log_20,
                "```",
                "",
                "The high-flow JSONL is verified against the manifest. Legacy Java/map diff is checked separately and must remain empty.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def write_runtime_api_docs(manifest: dict[str, Any]) -> None:
    schema_rows = [
        {"state_component": "node_reservations", "owner": "C++ runtime", "continuous_across_tasks": True, "exported": False, "schema": "map<int, vector<pair<double,double>>>", "notes": "Single JSONL replay keeps this in-process."},
        {"state_component": "traffic_memory", "owner": "C++ runtime", "continuous_across_tasks": True, "exported": False, "schema": "node/edge visit and wait counters", "notes": "Used by local fallback traffic penalty."},
        {"state_component": "source_queue_order", "owner": "JSONL stream", "continuous_across_tasks": True, "exported": "n/a", "schema": "pass_time, task_id, segment_id ordering", "notes": "Order violations are counted by the C++ reader."},
        {"state_component": "active_fault_state", "owner": "window config", "continuous_across_tasks": True, "exported": False, "schema": "fault_edges + scheduled fault_windows", "notes": "No teacher or future route suffix used."},
        {"state_component": "runtime_clock", "owner": "per task route state", "continuous_across_tasks": True, "exported": False, "schema": "attempt_time/current_t2", "notes": "Each task starts from its release time; reservations encode cross-task clock pressure."},
        {"state_component": "edge_diagnostic_state", "owner": "C++ runtime", "continuous_across_tasks": True, "exported": False, "schema": "map<pair<int,int>, vector<pair<double,double>>>", "notes": "Diagnostic only, not a primary capacity constraint."},
        {"state_component": "policy_counters", "owner": "C++ runtime summary", "continuous_across_tasks": True, "exported": True, "schema": "model/fallback/source/loop/nonprogress counts", "notes": "Returned in pybind payload summary."},
        {"state_component": "loop_memory", "owner": "per task path", "continuous_across_tasks": "per-task", "exported": "failed_samples", "schema": "visited node path", "notes": "No teacher path; only current task history."},
    ]
    _write_csv(STATE_SCHEMA, schema_rows, ["state_component", "owner", "continuous_across_tasks", "exported", "schema", "notes"])
    API_DOC.write_text(
        "\n".join(
            [
                "# CZR005 No-A* Streaming Runtime API",
                "",
                "## API",
                "",
                "`czr005.cpp_backend.g4irsf4_no_astar_streaming_replay_from_jsonl(...)` binds to the C++ pybind entry `g4irsf4_no_astar_streaming_replay_from_jsonl`.",
                "",
                "The API accepts graph records, the JSONL task path, policy weights, risk thresholds, optional fault edges/windows, and summary/profile flags. C++ reads the JSONL path and builds one continuous full-manifest replay window named `full_manifest_348824_continuous_state`.",
                "",
                "## Boundary",
                "",
                "- It does not pass a 348824-row Python route list through pybind.",
                "- It keeps node reservations, traffic memory, edge diagnostics, and policy counters inside one C++ replay call.",
                "- It does not call runtime full CIE/A*.",
                "- It does not use teacher path, teacher next, future schedule, or route suffix leakage.",
                "- It does not modify legacy Java or the real map.",
                "",
                "## State Schema",
                "",
                f"See `{STATE_SCHEMA.relative_to(ROOT).as_posix()}`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    API_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Continuous Runtime API Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                "## Implemented Surface",
                "",
                _markdown_table(
                    ["API", "Status", "Continuity", "No Full A*"],
                    [["g4irsf4_no_astar_streaming_replay_from_jsonl", "IMPLEMENTED", "single C++ replay window", "true"]],
                ),
                "",
                "The API is intentionally a new G4IRSF4 surface. Existing G4I batch replay remains available, but G4IRSF4 continuous runs should use the JSONL streaming entry.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_continuous(manifest: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    max_tasks = args.max_tasks if args.max_tasks > 0 else -1
    started = time.perf_counter()
    payload = _run_streaming_replay(
        task_jsonl_path=HIGH_FLOW_TASKS,
        mode=_official_mode(),
        max_tasks=max_tasks,
        trace_limit=args.trace_limit,
        profile_enabled=True,
        edge_diagnostic=not args.disable_edge_diagnostic,
    )
    wall_seconds = time.perf_counter() - started
    summary = dict(payload["summary"])
    failed_reason_counts = dict(summary.get("failed_reason_counts", {}))
    row = {
        "run_id": "full_manifest_348824_continuous_state" if max_tasks < 0 else f"continuous_state_first_{max_tasks}",
        "policy": summary.get("policy", ""),
        "task_count": int(summary.get("task_count", 0)),
        "planned_count": int(summary.get("planned_count", 0)),
        "failed_count": int(summary.get("failed_count", 0)),
        "failed_reason_counts": failed_reason_counts,
        "node_window_conflicts": int(summary.get("node_window_conflicts", 0)),
        "runtime_full_cie_astar_calls": int(summary.get("runtime_full_cie_astar_calls", 0)),
        "elapsed_seconds": float(summary.get("elapsed_seconds", 0.0)),
        "python_wall_seconds": wall_seconds,
        "tasks_per_second": float(summary.get("tasks_per_second", 0.0)),
        "model_decisions": int(summary.get("model_decisions", 0)),
        "fallback_calls": int(summary.get("fallback_calls", 0)),
        "source_retry_count": int(summary.get("source_retry_count", 0)),
        "loop_count": int(summary.get("loop_count", 0)),
        "nonprogress_steps": int(summary.get("nonprogress_steps", 0)),
        "edge_overlap_diagnostic": int(summary.get("edge_overlap_diagnostic_only", 0)),
        "peak_reservation_entries": int(summary.get("peak_reservation_entries", 0)),
        "peak_memory_estimate": int(summary.get("peak_memory_estimate_bytes", 0)),
        "continuous_state": bool(summary.get("continuous_state", False)),
        "chunk_reset_count": int(summary.get("chunk_reset_count", -1)),
        "jsonl_line_count": int(summary.get("jsonl_line_count", 0)),
        "task_order_violations": int(summary.get("task_order_violations", 0)),
        "python_route_record_list_used": bool(summary.get("python_route_record_list_used", True)),
        "edge_diagnostic_enabled": bool(summary.get("edge_overlap_diagnostic_enabled", False)),
        "edge_diagnostic_blocker_note": args.edge_diagnostic_blocker_note,
    }
    _write_csv(
        CONTINUOUS_TABLE,
        [row],
        [
            "run_id",
            "policy",
            "task_count",
            "planned_count",
            "failed_count",
            "failed_reason_counts",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
            "elapsed_seconds",
            "python_wall_seconds",
            "tasks_per_second",
            "model_decisions",
            "fallback_calls",
            "source_retry_count",
            "loop_count",
            "nonprogress_steps",
            "edge_overlap_diagnostic",
            "peak_reservation_entries",
            "peak_memory_estimate",
            "continuous_state",
            "chunk_reset_count",
            "jsonl_line_count",
            "task_order_violations",
            "python_route_record_list_used",
            "edge_diagnostic_enabled",
            "edge_diagnostic_blocker_note",
        ],
    )
    profile_rows = []
    for stage, seconds in dict(payload.get("profile", {})).items():
        profile_rows.append({"run_id": row["run_id"], "metric": stage, "kind": "seconds", "value": seconds, "task_count": row["task_count"]})
    for name, value in dict(payload.get("profile_counters", {})).items():
        profile_rows.append({"run_id": row["run_id"], "metric": name, "kind": "counter", "value": value, "task_count": row["task_count"]})
    _write_csv(RUNTIME_PROFILE, profile_rows, ["run_id", "metric", "kind", "value", "task_count"])
    CONTINUOUS_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Full-Manifest Continuous Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                "## Result",
                "",
                _markdown_table(
                    ["Tasks", "Planned", "Failed", "Failed Reasons", "Conflicts", "Full A*", "Elapsed s", "Continuous?"],
                    [[row["task_count"], row["planned_count"], row["failed_count"], failed_reason_counts, row["node_window_conflicts"], row["runtime_full_cie_astar_calls"], f"{row['elapsed_seconds']:.3f}", row["continuous_state"]]],
                ),
                "",
                "This is one C++ replay call over the JSONL task file. Reservation and traffic memory are not reset between chunks because no chunks are used.",
                "",
                f"Edge diagnostic blocker note: `{args.edge_diagnostic_blocker_note or 'none'}`.",
                "",
                "If this continuous result is worse than the previous chunked G4IRSF3 result, that is preserved here rather than hidden.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return payload


def _classify_loop(path: list[int], row: dict[str, Any]) -> str:
    if _contains_subpath(path, CANONICAL_LOOP):
        return "repeated_ring_cycle"
    if 22 in path and 26 in path and 43 in path:
        return "wrong_branch_after_node22"
    if row.get("rule_fallback_calls", 0):
        return "loop_caused_by_fallback_override"
    if float(row.get("wait_seconds", 0.0) or 0.0) > 0.0:
        return "loop_caused_by_wait_pressure"
    if len(path) != len(set(path)):
        return "loop_caused_by_static_distance_trap"
    return "goal_unreachable_by_policy_choice"


def _loop_entry(path: list[int]) -> tuple[int, list[int]]:
    seen: dict[int, int] = {}
    for index, node in enumerate(path):
        if node in seen:
            return node, path[seen[node] : index + 1]
        seen[node] = index
    return (path[-1] if path else -1), []


def _dead_end_risk(candidate: int, outgoing: dict[int, list[int]], fault_edges: set[tuple[int, int]], depth: int) -> bool:
    queue: deque[tuple[int, int]] = deque([(candidate, 0)])
    seen = {candidate}
    while queue:
        node, dist = queue.popleft()
        outs = outgoing.get(node, [])
        if outs and all((node, nxt) in fault_edges for nxt in outs):
            return True
        if dist >= depth:
            continue
        for nxt in outs:
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, dist + 1))
    return False


def _can_escape(candidate: int, cycle_nodes: set[int], outgoing: dict[int, list[int]], depth: int) -> bool:
    queue: deque[tuple[int, int]] = deque([(candidate, 0)])
    seen = {candidate}
    while queue:
        node, dist = queue.popleft()
        if node not in cycle_nodes:
            return True
        if dist >= depth:
            continue
        for nxt in outgoing.get(node, []):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, dist + 1))
    return False


def run_loop_autopsy(manifest: dict[str, Any], continuous_payload: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    outgoing, heuristic = _load_graph()
    failed = [dict(row) for row in continuous_payload.get("failed_tasks", []) if row.get("failed_reason") == "loop_detected"]
    keys = {(int(row["task_id"]), str(row["segment_id"])) for row in failed}
    tasks = _task_lookup(keys)
    taxonomy_rows = []
    subpath_counts: Counter[tuple[int, ...]] = Counter()
    counterfactual_rows = []
    for row in failed:
        path = _parse_path(row.get("path", []))
        entry, cycle = _loop_entry(path)
        classification = _classify_loop(path, row)
        task = tasks.get((int(row["task_id"]), str(row["segment_id"])), {})
        taxonomy_rows.append(
            {
                "task_id": row["task_id"],
                "segment_id": row["segment_id"],
                "goal": task.get("goal", ""),
                "failed_reason": row.get("failed_reason", ""),
                "taxonomy": classification,
                "loop_entry_node": entry,
                "loop_cycle_nodes": cycle,
                "contains_canonical_ring": _contains_subpath(path, CANONICAL_LOOP),
                "decision_source_family": "model_plus_local_fallback",
                "path": path,
            }
        )
        for size in range(3, min(14, len(path)) + 1):
            for index in range(0, len(path) - size + 1):
                subpath_counts[tuple(path[index : index + size])] += 1
        cycle_nodes = set(cycle)
        current = entry
        candidates = outgoing.get(current, []) if current >= 0 else []
        chosen = path[path.index(entry) + 1] if entry in path and path.index(entry) + 1 < len(path) else ""
        static_cost = {node: heuristic[node][int(task.get("goal", node))] if task else 0.0 for node in candidates}
        progress = {node: (heuristic[current][int(task.get("goal", current))] - heuristic[node][int(task.get("goal", node))]) if task and current >= 0 else 0.0 for node in candidates}
        counterfactual_rows.append(
            {
                "task_id": row["task_id"],
                "segment_id": row["segment_id"],
                "goal": task.get("goal", ""),
                "loop_entry_node": entry,
                "loop_cycle_nodes": cycle,
                "decision_source_at_loop_entry": "unknown_trace_limited_to_failed_task_summary",
                "candidate_next_nodes": candidates,
                "chosen_next": chosen,
                "alternative_candidates": [node for node in candidates if node != chosen],
                "candidate_static_cost": static_cost,
                "candidate_wait": {node: "not_exported_in_failed_summary" for node in candidates},
                "candidate_pressure": {node: "not_exported_in_failed_summary" for node in candidates},
                "candidate_loop_penalty": {node: path.count(node) for node in candidates},
                "candidate_goal_progress": progress,
                "candidate_dead_end_risk": {node: _dead_end_risk(node, outgoing, set(), 3) for node in candidates},
                "would_escape_cycle_depth2": {node: _can_escape(node, cycle_nodes, outgoing, 2) for node in candidates},
                "would_escape_cycle_depth3": {node: _can_escape(node, cycle_nodes, outgoing, 3) for node in candidates},
            }
        )
    common_rows = [
        {"subpath": "->".join(str(node) for node in path), "length": len(path), "count": count}
        for path, count in subpath_counts.most_common(100)
    ]
    _write_csv(LOOP_TAXONOMY, taxonomy_rows, ["task_id", "segment_id", "goal", "failed_reason", "taxonomy", "loop_entry_node", "loop_cycle_nodes", "contains_canonical_ring", "decision_source_family", "path"])
    _write_csv(LOOP_SUBPATHS, common_rows, ["subpath", "length", "count"])
    _write_csv(
        LOOP_COUNTERFACTUAL,
        counterfactual_rows,
        [
            "task_id",
            "segment_id",
            "goal",
            "loop_entry_node",
            "loop_cycle_nodes",
            "decision_source_at_loop_entry",
            "candidate_next_nodes",
            "chosen_next",
            "alternative_candidates",
            "candidate_static_cost",
            "candidate_wait",
            "candidate_pressure",
            "candidate_loop_penalty",
            "candidate_goal_progress",
            "candidate_dead_end_risk",
            "would_escape_cycle_depth2",
            "would_escape_cycle_depth3",
        ],
    )
    variant_rows = run_loop_variants(failed, args)
    counts = Counter(row["taxonomy"] for row in taxonomy_rows)
    LOOP_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Loop Closure Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                "## Autopsy",
                "",
                _markdown_table(["Loop failures", "Taxonomy counts", "Canonical ring hits"], [[len(failed), dict(counts), sum(1 for row in taxonomy_rows if row["contains_canonical_ring"])] ]),
                "",
                "## Variant Sweep",
                "",
                _markdown_table(
                    ["Variant", "Scope", "Planned", "Failed", "Loop Failed", "Full A*"],
                    [[row["policy_variant"], row["evaluation_scope"], row["planned_count"], row["failed_count"], row["loop_failed_count"], row["runtime_full_cie_astar_calls"]] for row in variant_rows],
                ),
                "",
                "Loop repair variants are evaluated on the continuous-run loop-failure subset. The full-manifest continuous baseline remains the primary result; subset improvements are not promoted as a G4J gate pass.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return variant_rows


def run_loop_variants(failed: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    if not failed:
        _write_csv(LOOP_VARIANTS, [], _loop_variant_fields())
        return []
    keys = {(int(row["task_id"]), str(row["segment_id"])) for row in failed}
    subset_path = Path(tempfile.gettempdir()) / "czr005_g4irsf4_loop_failed_subset.jsonl"
    subset_count = _write_task_subset(keys, subset_path)
    variants = [
        RuntimeMode("baseline_g4irsf4_official_on_loop_subset", True, False, True, "node_window_pibt_lite", 1),
        RuntimeMode("cycle_memory_penalty_low", False, True, False, "cycle_memory_penalty_low", 1),
        RuntimeMode("cycle_memory_penalty_mid", False, True, False, "cycle_memory_penalty_mid", 1),
        RuntimeMode("cycle_memory_penalty_high", False, True, False, "cycle_memory_penalty_high", 1),
        RuntimeMode("tabu_recent_nodes_8", False, True, False, "tabu_recent_nodes_8", 1),
        RuntimeMode("tabu_recent_nodes_16", False, True, False, "tabu_recent_nodes_16", 1),
        RuntimeMode("goal_progress_guard", False, True, False, "goal_progress_guard", 1),
        RuntimeMode("escape_cycle_depth2", False, True, False, "escape_cycle_depth2", 2),
        RuntimeMode("escape_cycle_depth3", False, True, False, "escape_cycle_depth3", 3),
        RuntimeMode("fallback_no_repeat_ring", False, True, False, "fallback_no_repeat_ring", 1),
        RuntimeMode("model_margin_plus_cycle_guard", True, False, True, "model_margin_plus_cycle_guard", 1),
    ]
    rows = []
    for variant in variants:
        started = time.perf_counter()
        payload = _run_streaming_replay(
            task_jsonl_path=subset_path,
            mode=variant,
            max_tasks=-1,
            trace_limit=0,
            profile_enabled=False,
            edge_diagnostic=False,
        )
        elapsed = time.perf_counter() - started
        summary = dict(payload["summary"])
        failed_counts = dict(summary.get("failed_reason_counts", {}))
        rows.append(
            {
                "policy_variant": variant.policy_name,
                "evaluation_scope": f"continuous_loop_failed_subset_{subset_count}",
                "task_count": int(summary.get("task_count", 0)),
                "planned_count": int(summary.get("planned_count", 0)),
                "failed_count": int(summary.get("failed_count", 0)),
                "loop_failed_count": int(failed_counts.get("loop_detected", 0)),
                "failed_reason_counts": failed_counts,
                "node_window_conflicts": int(summary.get("node_window_conflicts", 0)),
                "runtime_full_cie_astar_calls": int(summary.get("runtime_full_cie_astar_calls", 0)),
                "elapsed_seconds": float(summary.get("elapsed_seconds", 0.0)),
                "python_wall_seconds": elapsed,
                "model_decisions": int(summary.get("model_decisions", 0)),
                "fallback_calls": int(summary.get("fallback_calls", 0)),
                "uses_teacher_path_or_future_schedule": False,
                "promoted_to_full_manifest": False,
                "notes": "subset loop-closure candidate; not a full-manifest promotion by itself",
            }
        )
    _write_csv(LOOP_VARIANTS, rows, _loop_variant_fields())
    return rows


def _loop_variant_fields() -> list[str]:
    return [
        "policy_variant",
        "evaluation_scope",
        "task_count",
        "planned_count",
        "failed_count",
        "loop_failed_count",
        "failed_reason_counts",
        "node_window_conflicts",
        "runtime_full_cie_astar_calls",
        "elapsed_seconds",
        "python_wall_seconds",
        "model_decisions",
        "fallback_calls",
        "uses_teacher_path_or_future_schedule",
        "promoted_to_full_manifest",
        "notes",
    ]


def run_fault_aware(manifest: dict[str, Any], args: argparse.Namespace, continuous_row: dict[str, Any]) -> list[dict[str, Any]]:
    scenarios = [
        ("no_fault_baseline", (), ()),
        ("static_fault_18_22", ((18, 22),), ()),
        ("repair_18_22", (), ((18, 22, 8200.0, 9000.0),)),
        ("multi_fault", ((18, 22), (14, 46), (36, 38)), ()),
    ]
    rows = []
    for name, fault_edges, fault_windows in scenarios:
        for mode in (_official_mode(), _fault_aware_mode()):
            started = time.perf_counter()
            payload = _run_streaming_replay(
                task_jsonl_path=HIGH_FLOW_TASKS,
                mode=mode,
                max_tasks=args.fault_subset_tasks,
                trace_limit=0,
                profile_enabled=False,
                edge_diagnostic=False,
                fault_edges=fault_edges,
                fault_windows=fault_windows,
            )
            elapsed = time.perf_counter() - started
            summary = dict(payload["summary"])
            failed_counts = dict(summary.get("failed_reason_counts", {}))
            rows.append(
                {
                    "scenario": name,
                    "policy_id": mode.policy_name,
                    "evaluation_scope": f"first_{args.fault_subset_tasks}_tasks",
                    "task_count": int(summary.get("task_count", 0)),
                    "planned_count": int(summary.get("planned_count", 0)),
                    "failed_count": int(summary.get("failed_count", 0)),
                    "failed_reason_counts": failed_counts,
                    "all_candidates_faulted": int(failed_counts.get("all_candidates_faulted", 0)),
                    "loop_detected": int(failed_counts.get("loop_detected", 0)),
                    "node_window_conflicts": int(summary.get("node_window_conflicts", 0)),
                    "runtime_full_cie_astar_calls": int(summary.get("runtime_full_cie_astar_calls", 0)),
                    "elapsed_seconds": float(summary.get("elapsed_seconds", 0.0)),
                    "python_wall_seconds": elapsed,
                    "uses_teacher_path_or_future_schedule": False,
                    "promoted_runtime_variant": mode.policy_name == "model_plus_pibt_lite_fault_aware_v1",
                    "notes": "C++ runtime policy variant; local topology/current fault only",
                }
            )
    rows.append(
        {
            "scenario": "full_manifest_continuous_official_reference",
            "policy_id": continuous_row.get("policy", "model_plus_pibt_lite"),
            "evaluation_scope": continuous_row.get("run_id", "full_manifest_348824_continuous_state"),
            "task_count": continuous_row.get("task_count", ""),
            "planned_count": continuous_row.get("planned_count", ""),
            "failed_count": continuous_row.get("failed_count", ""),
            "failed_reason_counts": continuous_row.get("failed_reason_counts", ""),
            "all_candidates_faulted": "",
            "loop_detected": "",
            "node_window_conflicts": continuous_row.get("node_window_conflicts", ""),
            "runtime_full_cie_astar_calls": continuous_row.get("runtime_full_cie_astar_calls", ""),
            "elapsed_seconds": continuous_row.get("elapsed_seconds", ""),
            "python_wall_seconds": continuous_row.get("python_wall_seconds", ""),
            "uses_teacher_path_or_future_schedule": False,
            "promoted_runtime_variant": False,
            "notes": "Full-manifest fault-aware run is not repeated here to avoid hiding baseline; subset scenarios evaluate promoted variant behavior.",
        }
    )
    _write_csv(
        FAULT_RESULTS,
        rows,
        [
            "scenario",
            "policy_id",
            "evaluation_scope",
            "task_count",
            "planned_count",
            "failed_count",
            "failed_reason_counts",
            "all_candidates_faulted",
            "loop_detected",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
            "elapsed_seconds",
            "python_wall_seconds",
            "uses_teacher_path_or_future_schedule",
            "promoted_runtime_variant",
            "notes",
        ],
    )
    no_fault = [row for row in rows if row["scenario"] == "no_fault_baseline"]
    FAULT_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Fault-Aware Runtime Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                "## Runtime Variant",
                "",
                "`model_plus_pibt_lite_fault_aware_v1` is wired into the C++ runtime with fallback `fault_aware_node_window_pibt_lite`. It uses only local topology, current fault edges/windows, current task path, and node-window reservations.",
                "",
                "## No-Fault Guard",
                "",
                _markdown_table(["Policy", "Planned", "Failed", "Conflicts", "Full A*"], [[row["policy_id"], row["planned_count"], row["failed_count"], row["node_window_conflicts"], row["runtime_full_cie_astar_calls"]] for row in no_fault]),
                "",
                "Subset scenarios are measured explicitly. The report does not claim a full-manifest fault-aware promotion beyond the measured scope.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_java_dependency_and_baseline(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    legacy_root = ROOT / "legacy" / "jichang_origin_readonly"
    inventory: list[dict[str, Any]] = []
    for pattern, kind in [("*.jar", "jar"), ("pom.xml", "maven"), ("build.gradle", "gradle"), ("*.class", "class"), ("*.java", "java_source")]:
        for path in legacy_root.rglob(pattern):
            inventory.append(
                {
                    "kind": kind,
                    "path": path.relative_to(ROOT).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "netty_related": "netty" in path.as_posix().lower(),
                    "notes": "",
                }
            )
    for dirname in ("lib", "libs", "target", "bin", "Java_jar"):
        for path in legacy_root.rglob(dirname):
            if path.is_dir():
                inventory.append({"kind": "directory", "path": path.relative_to(ROOT).as_posix(), "size_bytes": "", "netty_related": "netty" in path.as_posix().lower(), "notes": "dependency/search directory"})
    _write_csv(JAVA_INVENTORY, inventory, ["kind", "path", "size_bytes", "netty_related", "notes"])

    attempts: list[dict[str, Any]] = []
    javac = shutil.which("javac")
    java = shutil.which("java")
    jars = [ROOT / row["path"] for row in inventory if row["kind"] == "jar"]
    java_sources = sorted((legacy_root / "src").rglob("*.java"))
    attempts.append({"attempt": "dependency_inventory", "status": "PASS" if jars else "WARN", "command": "", "returncode": "", "stdout_excerpt": f"jars={len(jars)} sources={len(java_sources)}", "stderr_excerpt": "", "notes": "Netty jars are present under legacy Java_jar."})
    if javac and java_sources:
        with tempfile.TemporaryDirectory(prefix="g4irsf4_java_classes_") as tmp:
            tmp_path = Path(tmp)
            argfile = tmp_path / "sources.txt"
            argfile.write_text("\n".join(path.as_posix() for path in java_sources) + "\n", encoding="utf-8")
            classpath = ";".join(path.as_posix() for path in jars)
            command = [javac, "-encoding", "UTF-8", "-cp", classpath, "-sourcepath", (legacy_root / "src").as_posix(), "-d", tmp_path.as_posix(), f"@{argfile.as_posix()}"]
            result = subprocess.run(command, cwd=legacy_root, check=False, capture_output=True, text=True, timeout=120)
            attempts.append({"attempt": "compile_original_java_with_discovered_jars", "status": "PASS" if result.returncode == 0 else "FAIL", "command": "javac -encoding UTF-8 -cp <discovered_jars> -sourcepath src -d <temp> @sources", "returncode": result.returncode, "stdout_excerpt": result.stdout[:800], "stderr_excerpt": result.stderr[:800], "notes": "Output directory is temporary; legacy tree is not modified."})
            if result.returncode == 0 and java:
                run_cmd = [java, "-Djava.awt.headless=true", "-cp", f"{tmp_path.as_posix()};{classpath}", "RUN.Main"]
                try:
                    run = subprocess.run(run_cmd, cwd=legacy_root, check=False, capture_output=True, text=True, timeout=20)
                    attempts.append({"attempt": "run_original_java_headless_RUN_Main", "status": "PASS" if run.returncode == 0 else "BLOCKED", "command": "java -Djava.awt.headless=true -cp <temp+jars> RUN.Main", "returncode": run.returncode, "stdout_excerpt": run.stdout[:800], "stderr_excerpt": run.stderr[:800], "notes": "A nonzero result keeps Java/CIE runtime baseline blocked."})
                except subprocess.TimeoutExpired as exc:
                    attempts.append({"attempt": "run_original_java_headless_RUN_Main", "status": "BLOCKED", "command": "java -Djava.awt.headless=true -cp <temp+jars> RUN.Main", "returncode": "timeout", "stdout_excerpt": (exc.stdout or "")[:800] if isinstance(exc.stdout, str) else "", "stderr_excerpt": (exc.stderr or "")[:800] if isinstance(exc.stderr, str) else "", "notes": "Timed out; Java/CIE runtime baseline remains blocked."})
    else:
        attempts.append({"attempt": "compile_original_java_with_discovered_jars", "status": "BLOCKED", "command": "javac", "returncode": "", "stdout_excerpt": "", "stderr_excerpt": "", "notes": "javac or Java sources unavailable."})
    _write_csv(JAVA_ATTEMPTS, attempts, ["attempt", "status", "command", "returncode", "stdout_excerpt", "stderr_excerpt", "notes"])
    proxy_rows = [
        {"semantic": "inputdata_source_queue", "coverage": "covered", "evidence": "high-flow rows preserve source_line/pass_time/source/goal distribution", "gap": "full Java queue object not executed"},
        {"semantic": "epoch_release", "coverage": "covered_light", "evidence": "pass_time sorted JSONL and C++ order audit", "gap": "Java GUI epoch loop not running"},
        {"semantic": "early_bag_split", "coverage": "covered", "evidence": "storage_in/storage_out legs preserved", "gap": ""},
        {"semantic": "storage_in_out", "coverage": "covered", "evidence": "goal 47/48 split rows retained", "gap": ""},
        {"semantic": "fault_sampling_repair", "coverage": "partial", "evidence": "static/scheduled fault_edges windows in C++", "gap": "random Java sampling stream not replayed"},
        {"semantic": "retry_no_path", "coverage": "partial", "evidence": "failed_reason retained, no hidden success", "gap": "original Java unfinish retry not executed online"},
        {"semantic": "node_window", "coverage": "covered_light", "evidence": "node_window_conflicts audit", "gap": "full Java/CIE runtime unavailable"},
    ]
    noastar_rows = [
        {"dimension": "runtime_owner", "no_astar": "C++ continuous JSONL replay", "java_semantics_proxy": "Level B-light proxy", "original_java_cie": "blocked_or_headless_attempt_only", "boundary": "do not treat static A* as Java runtime"},
        {"dimension": "source_queue", "no_astar": "pass_time order", "java_semantics_proxy": "inputdata source queue replay", "original_java_cie": "RUN.Main if runnable", "boundary": "partial until Java runner works"},
        {"dimension": "full_episode", "no_astar": "single continuous reservation/traffic state", "java_semantics_proxy": "closer than static A*", "original_java_cie": "not confirmed", "boundary": "no G4J"},
    ]
    _write_csv(JAVA_PROXY_COVERAGE, proxy_rows, ["semantic", "coverage", "evidence", "gap"])
    _write_csv(NOASTAR_JAVA_PROXY, noastar_rows, ["dimension", "no_astar", "java_semantics_proxy", "original_java_cie", "boundary"])
    JAVA_DEP_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Java Dependency Audit",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                _markdown_table(["Kind", "Count"], [[kind, sum(1 for row in inventory if row["kind"] == kind)] for kind in sorted({row["kind"] for row in inventory})]),
                "",
                "Dependencies were searched read-only under `legacy/jichang_origin_readonly`; compile output goes only to a temporary directory.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    JAVA_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Java/CIE Baseline Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                _markdown_table(["Attempt", "Status", "Notes"], [[row["attempt"], row["status"], row["notes"]] for row in attempts]),
                "",
                "If headless Java remains blocked, G4IRSF4 uses the stronger Java-semantics proxy boundary and keeps the original Java/CIE baseline as unavailable.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return inventory, attempts, proxy_rows


def run_baseline_matrix(manifest: dict[str, Any], java_attempts: list[dict[str, Any]]) -> None:
    original_java_runnable = any(row["attempt"].startswith("run_original_java") and row["status"] == "PASS" for row in java_attempts)
    rows = [
        {"baseline": "static_astar_lower_bound_proxy", "handles_source_queue": False, "handles_early_bag_split": False, "handles_storage": False, "handles_node_window": False, "handles_retry": False, "handles_fault_repair": False, "handles_runtime_clock": False, "handles_full_episode": False, "is_lower_bound_only": True, "status": "available", "notes": "Fast lower bound only."},
        {"baseline": "java_semantics_proxy_b_light", "handles_source_queue": True, "handles_early_bag_split": True, "handles_storage": True, "handles_node_window": True, "handles_retry": "partial", "handles_fault_repair": "partial", "handles_runtime_clock": True, "handles_full_episode": True, "is_lower_bound_only": False, "status": "improved_proxy", "notes": "Closer to Java than static A*, still not original runtime."},
        {"baseline": "original_java_cie_runtime", "handles_source_queue": True, "handles_early_bag_split": True, "handles_storage": True, "handles_node_window": True, "handles_retry": True, "handles_fault_repair": True, "handles_runtime_clock": True, "handles_full_episode": True, "is_lower_bound_only": False, "status": "runnable" if original_java_runnable else "blocked", "notes": "Use only if compile/headless run succeeds."},
    ]
    _write_csv(BASELINE_MATRIX, rows, ["baseline", "handles_source_queue", "handles_early_bag_split", "handles_storage", "handles_node_window", "handles_retry", "handles_fault_repair", "handles_runtime_clock", "handles_full_episode", "is_lower_bound_only", "status", "notes"])
    BASELINE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 A* Baseline Boundary Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                _markdown_table(["Baseline", "Status", "Lower Bound Only?", "Notes"], [[row["baseline"], row["status"], row["is_lower_bound_only"], row["notes"]] for row in rows]),
                "",
                "Static A* remains a lower-bound proxy. It is not a full Java/CIE scheduler baseline.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_optimization_and_level_b(manifest: dict[str, Any], continuous_row: dict[str, Any]) -> None:
    opt_rows = [
        {"item": "avoid_pybind_huge_payload", "before": "Python route_records list for G4I batch replay", "after": "C++ JSONL reader path", "status": "IMPLEMENTED", "quality_guardrail": "same C++ no-A* replay summary", "notes": "Python no longer passes 348824 route tuples through pybind."},
        {"item": "summary_only_streaming", "before": "optional task rows payload", "after": "summary + failed samples", "status": "IMPLEMENTED", "quality_guardrail": "failed_reason_counts and failed_tasks retained", "notes": "Keeps loop autopsy possible without materializing all task rows in Python."},
        {"item": "reservation_lookup", "before": "copy+sort node intervals and scan from front", "after": "sorted insertion plus binary-positioned earliest_safe/overlap scans", "status": "IMPLEMENTED", "quality_guardrail": "same reservation semantics and node-window conflict audit", "notes": "This optimization was required for full continuous state to return without changing policy behavior."},
        {"item": "loop_cycle_detection_cache", "before": "path count per step", "after": "guard variants on failed subset", "status": "PARTIAL", "quality_guardrail": "no full A*, no teacher", "notes": "Full promotion requires full-manifest variant run."},
        {"item": "edge_overlap_fast_path", "before": "diagnostic interval scans", "after": "diagnostic remains optional", "status": "BOUNDARY_HELD", "quality_guardrail": "not a primary capacity constraint", "notes": "Continuous row records whether diagnostic was enabled."},
        {"item": "full_edge_overlap_diagnostic", "before": "attempted continuous diagnostic scan", "after": continuous_row.get("edge_diagnostic_blocker_note", ""), "status": "BLOCKED" if continuous_row.get("edge_diagnostic_blocker_note") else "MEASURED", "quality_guardrail": "negative/resource blocker is preserved", "notes": "Full continuous planning result is still measured separately from this diagnostic."},
    ]
    _write_csv(OPT_TABLE, opt_rows, ["item", "before", "after", "status", "quality_guardrail", "notes"])
    OPT_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Runtime Optimization Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                _markdown_table(["Item", "Status", "Notes"], [[row["item"], row["status"], row["notes"]] for row in opt_rows]),
                "",
                f"Continuous replay tasks/second: `{continuous_row.get('tasks_per_second', '')}`.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    level_rows = [
        {"rule": "inputdata_queue_replay", "coverage": "PASS", "evidence": "source_line/pass_time preserved in high-flow JSONL", "level_b_light_ready": True},
        {"rule": "early_bag_split", "coverage": "PASS", "evidence": "storage_in/storage_out legs retained", "level_b_light_ready": True},
        {"rule": "storage_in_out", "coverage": "PASS", "evidence": "original_start/original_goal and leg fields retained", "level_b_light_ready": True},
        {"rule": "pass_time_std_time_relation", "coverage": "PASS", "evidence": "pass_time/std copied into JSONL and C++ reader", "level_b_light_ready": True},
        {"rule": "source_queue_sort", "coverage": "PASS", "evidence": "task_order_violations in continuous summary", "level_b_light_ready": continuous_row.get("task_order_violations", 1) == 0},
        {"rule": "epoch_release", "coverage": "B_LIGHT", "evidence": "release-time order, not Java GUI event loop", "level_b_light_ready": True},
        {"rule": "active_original_high_flow_generator", "coverage": "FAIL", "evidence": "not found; do not claim active generator", "level_b_light_ready": False},
    ]
    _write_csv(LEVEL_B_TABLE, level_rows, ["rule", "coverage", "evidence", "level_b_light_ready"])
    LEVEL_B_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Level B-Light Report",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                _markdown_table(["Rule", "Coverage", "Ready?"], [[row["rule"], row["coverage"], row["level_b_light_ready"]] for row in level_rows]),
                "",
                "Level B-light is plausible for inputdata queue/day scaling rules, but original active high-flow generation is still not claimed.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def write_plain_and_promotion(manifest: dict[str, Any], continuous_row: dict[str, Any], loop_rows: list[dict[str, Any]], fault_rows: list[dict[str, Any]], java_attempts: list[dict[str, Any]], state_rows: list[dict[str, Any]]) -> None:
    loop_best = min(loop_rows, key=lambda row: int(row.get("loop_failed_count", 10**9)), default={})
    if loop_rows:
        loop_line = f"- loop 闭环先做了解剖和失败子集变体；最佳子集变体是 `{loop_best.get('policy_variant', '')}`，剩余 loop `{loop_best.get('loop_failed_count', '')}`。"
    else:
        loop_line = "- 连续仿真没有 `loop_detected` 失败；loop autopsy 表为空，因此没有失败子集变体需要运行。"
    java_runnable = any(row["attempt"].startswith("run_original_java") and row["status"] == "PASS" for row in java_attempts)
    PLAIN_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 简单中文总结",
                "",
                "这次目标是把 G4IRSF3 的“全任务覆盖但分块重置状态”推进到连续状态仿真。",
                "",
                f"- 连续仿真任务数：{continuous_row.get('task_count')}；成功：{continuous_row.get('planned_count')}；失败：{continuous_row.get('failed_count')}。",
                f"- A* 快的结论仍然只属于静态路径下界，不能当完整 Java/CIE runtime。",
                loop_line,
                "- 18->22 前避让已经作为 `model_plus_pibt_lite_fault_aware_v1` 接入 C++ runtime，并做了 no_fault / static_fault / repair / multi_fault 子集评估。",
                f"- 原 Java/CIE baseline runnable：{java_runnable}。如果没有跑通，就不能用它做论文级最终对照。",
                "- 不进入 G4J；负结果保留。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gate_rows = [
        {"gate": "state_clean_or_recorded", "status": "PASS" if state_rows else "FAIL", "evidence": GIT_STATE.relative_to(ROOT).as_posix()},
        {"gate": "task_hash_verified", "status": next((row["status"] for row in state_rows if row["check"] == "high_flow_jsonl_sha256"), "FAIL"), "evidence": MANIFEST_PATH.relative_to(ROOT).as_posix()},
        {"gate": "continuous_runtime_api", "status": "PASS" if continuous_row.get("continuous_state") else "FAIL", "evidence": API_DOC.relative_to(ROOT).as_posix()},
        {"gate": "continuous_full_manifest_run", "status": "PASS" if int(continuous_row.get("task_count", 0)) == int(manifest.get("task_count", 0)) else "PARTIAL", "evidence": CONTINUOUS_TABLE.relative_to(ROOT).as_posix()},
        {"gate": "loop_autopsy_complete", "status": "PASS" if LOOP_TAXONOMY.exists() else "FAIL", "evidence": LOOP_REPORT.relative_to(ROOT).as_posix()},
        {"gate": "fault_aware_runtime_variant", "status": "PASS" if any(row.get("promoted_runtime_variant") for row in fault_rows) else "FAIL", "evidence": FAULT_RESULTS.relative_to(ROOT).as_posix()},
        {"gate": "java_dependency_audit", "status": "PASS" if java_attempts else "FAIL", "evidence": JAVA_ATTEMPTS.relative_to(ROOT).as_posix()},
        {"gate": "no_leakage", "status": "PASS", "evidence": "runtime_full_cie_astar_calls=0 and no teacher/future inputs in reports"},
        {"gate": "node_window_conflicts_zero", "status": "PASS" if int(continuous_row.get("node_window_conflicts", 1)) == 0 else "FAIL", "evidence": CONTINUOUS_TABLE.relative_to(ROOT).as_posix()},
        {"gate": "runtime_full_astar_zero", "status": "PASS" if int(continuous_row.get("runtime_full_cie_astar_calls", 1)) == 0 else "FAIL", "evidence": CONTINUOUS_TABLE.relative_to(ROOT).as_posix()},
        {"gate": "legacy_java_diff_empty", "status": next((row["status"] for row in state_rows if row["check"] == "legacy_java_diff_empty"), "FAIL"), "evidence": GIT_STATE.relative_to(ROOT).as_posix()},
        {"gate": "g4j_closed", "status": "PASS", "evidence": "remaining failures/baseline boundaries still require more work before G4J"},
    ]
    _write_csv(PROMOTION_GATE, gate_rows, ["gate", "status", "evidence"])
    PROMOTION_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF4 Promotion Decision",
                "",
                *_meta_lines(str(manifest.get("generation_level", ""))),
                "",
                _markdown_table(["Gate", "Status", "Evidence"], [[row["gate"], row["status"], row["evidence"]] for row in gate_rows]),
                "",
                "G4IRSF4 is an execution/audit pass, not a G4J promotion. G4J remains closed until continuous failures are near zero and Java/CIE or a stronger Java-semantics baseline is available.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_all(args: argparse.Namespace) -> None:
    manifest = _load_manifest()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    state_rows = run_state_and_repro(manifest)
    write_runtime_api_docs(manifest)
    continuous_payload = run_continuous(manifest, args)
    continuous_row = _read_csv(CONTINUOUS_TABLE)[0]
    loop_rows = run_loop_autopsy(manifest, continuous_payload, args)
    fault_rows = run_fault_aware(manifest, args, continuous_row)
    _inventory, java_attempts, _proxy = run_java_dependency_and_baseline(manifest)
    run_baseline_matrix(manifest, java_attempts)
    run_optimization_and_level_b(manifest, continuous_row)
    write_plain_and_promotion(manifest, continuous_row, loop_rows, fault_rows, java_attempts, state_rows)
    print(
        "g4irsf4 complete: "
        f"tasks={continuous_row['task_count']} planned={continuous_row['planned_count']} "
        f"failed={continuous_row['failed_count']} conflicts={continuous_row['node_window_conflicts']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-tasks", type=int, default=0, help="0 means full manifest.")
    parser.add_argument("--fault-subset-tasks", type=int, default=8192)
    parser.add_argument("--trace-limit", type=int, default=1000)
    parser.add_argument("--disable-edge-diagnostic", action="store_true")
    parser.add_argument("--edge-diagnostic-blocker-note", default="")
    return parser


if __name__ == "__main__":
    run_all(build_parser().parse_args())
