from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict, deque
import csv
from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Iterator


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_DOC = ROOT / "docs" / "czr005_project_governance.md"
MAP_PATH = ROOT / "data" / "processed" / "maps" / "map2.json"
MANIFEST_PATH = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_manifest.json"
HIGH_FLOW_TASKS = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_tasks.jsonl"
REPORT_DIR = ROOT / "outputs" / "reports"
TABLE_DIR = ROOT / "outputs" / "tables"
POLICY_DIR = ROOT / "artifacts" / "policies"

STATE_REPORT = REPORT_DIR / "g4irsf3_state_and_repro_report.md"
REPRO_REPORT = REPORT_DIR / "g4irsf3_high_flow_reproducibility_report.md"
FULL_MANIFEST_REPORT = REPORT_DIR / "g4irsf3_full_manifest_benchmark_report.md"
FAULT_REPORT = REPORT_DIR / "g4irsf3_fault_aware_upstream_avoidance_report.md"
WAIT_REPORT = REPORT_DIR / "g4irsf3_wait_or_fail_semantics_report.md"
JAVA_REPORT = REPORT_DIR / "g4irsf3_original_java_baseline_audit.md"
HARDNESS_REPORT = REPORT_DIR / "g4irsf3_astar_hardness_v2_report.md"
EDGE_REPORT = REPORT_DIR / "g4irsf3_edge_pressure_policy_report.md"
OPT_REPORT = REPORT_DIR / "g4irsf3_high_flow_runtime_optimization_report.md"
LEVEL_B_REPORT = REPORT_DIR / "g4irsf3_level_b_feasibility_report.md"
PLAIN_REPORT = REPORT_DIR / "g4irsf3_plain_language_summary.md"
PROMOTION_REPORT = REPORT_DIR / "g4irsf3_promotion_decision.md"

GIT_STATE = TABLE_DIR / "g4irsf3_git_state_audit.csv"
HASH_TABLE = TABLE_DIR / "g4irsf3_high_flow_file_hash_audit.csv"
CHUNKED_TABLE = TABLE_DIR / "g4irsf3_full_manifest_chunked_benchmark.csv"
STREAMING_TABLE = TABLE_DIR / "g4irsf3_full_manifest_streaming_benchmark.csv"
FAILED_TASKS = TABLE_DIR / "g4irsf3_full_manifest_failed_task_cases.csv"
UPSTREAM_CASES = TABLE_DIR / "g4irsf3_fault_18_22_upstream_decision_cases.csv"
DEAD_END_FEATURES = TABLE_DIR / "g4irsf3_fault_18_22_dead_end_features.csv"
FAULT_VARIANTS = TABLE_DIR / "g4irsf3_fault_18_22_policy_variant_results.csv"
WAIT_POLICY = TABLE_DIR / "g4irsf3_fault_wait_policy_results.csv"
JAVA_ATTEMPTS = TABLE_DIR / "g4irsf3_java_baseline_run_attempts.csv"
JAVA_SEMANTICS = TABLE_DIR / "g4irsf3_astar_cie_retry_semantics_proxy.csv"
NOASTAR_JAVA_PROXY = TABLE_DIR / "g4irsf3_noastar_vs_java_semantics_proxy.csv"
HARDNESS_V2 = TABLE_DIR / "g4irsf3_astar_hardness_v2.csv"
EDGE_POLICY = TABLE_DIR / "g4irsf3_edge_pressure_policy_results.csv"
STAGE_PROFILE = TABLE_DIR / "g4irsf3_high_flow_stage_profile.csv"
OPT_RESULTS = TABLE_DIR / "g4irsf3_high_flow_optimization_results.csv"
LEVEL_B_COVERAGE = TABLE_DIR / "g4irsf3_level_b_rule_coverage.csv"
PROMOTION_GATE = TABLE_DIR / "g4irsf3_promotion_gate.csv"
ALLOWED_INPUTS = POLICY_DIR / "g4irsf3_allowed_runtime_inputs.json"

G4IRSF2_FAULT_CASES = TABLE_DIR / "g4irsf2_fault_18_22_failure_cases.csv"
G4IRSF2_COUNTERFACTUAL = TABLE_DIR / "g4irsf2_fault_18_22_local_counterfactual.csv"
G4IRSF2_SLOPE = TABLE_DIR / "g4irsf2_fixed_map_noastar_vs_astar_slope.csv"
G4IRSF2_EDGE_SWEEP = TABLE_DIR / "g4irsf2_edge_pressure_sweep.csv"
G4IRSF2_TOP_EDGES = TABLE_DIR / "g4irsf2_top_edge_overlap_by_flow.csv"
G4IRSF2_RULES = TABLE_DIR / "g4irsf2_original_ics_rule_inventory.csv"
G4IRSF2_BASELINE_RULES = TABLE_DIR / "g4irsf2_original_ics_baseline_rule_evidence.csv"

REQUIRED_PREV_COMMIT = "209f895"
FAULT_EDGE = (18, 22)
DEFAULT_CHUNK_SIZE = 32768


@dataclass(frozen=True)
class FaultVariant:
    name: str
    depth: int
    penalty: float
    hard_avoid: bool
    wait_if_no_safe: bool
    notes: str


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(_jsonable(value), ensure_ascii=True, sort_keys=True)
    return value


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, set):
        return [_jsonable(item) for item in sorted(value, key=str)]
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
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


def _meta_lines(ctx: dict[str, Any], generation_level: str = "distribution_preserving_resample") -> list[str]:
    return [
        f"Date: {date.today().isoformat()}",
        f"Branch: `{ctx.get('branch', '')}`",
        f"HEAD: `{ctx.get('head_short', '')}`",
        f"governance_doc: {GOVERNANCE_DOC.relative_to(ROOT).as_posix()}",
        "topology_changed: false",
        f"data_generation_rule_source: {generation_level}",
        "runtime_full_cie_astar_fallback: false",
    ]


def _load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _parse_path(value: Any) -> list[int]:
    if isinstance(value, list):
        return [int(item) for item in value]
    text = str(value)
    try:
        return [int(item) for item in json.loads(text)]
    except Exception:
        try:
            return [int(item) for item in ast.literal_eval(text)]
        except Exception:
            return []


def _iter_jsonl_chunks(path: Path, chunk_size: int, max_chunks: int = 0) -> Iterator[tuple[int, list[dict[str, Any]]]]:
    chunk: list[dict[str, Any]] = []
    chunk_index = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            chunk.append(json.loads(line))
            if len(chunk) >= chunk_size:
                yield chunk_index, chunk
                chunk_index += 1
                if max_chunks and chunk_index >= max_chunks:
                    return
                chunk = []
        if chunk and (not max_chunks or chunk_index < max_chunks):
            yield chunk_index, chunk


def _task_lookup(keys: set[tuple[int, str]]) -> dict[tuple[int, str], dict[str, Any]]:
    found: dict[tuple[int, str], dict[str, Any]] = {}
    if not HIGH_FLOW_TASKS.exists():
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


def _route_records(rows: list[dict[str, Any]], window_name: str, scope: str) -> list[Any]:
    records = []
    for row in rows:
        records.append(
            (
                scope,
                window_name,
                int(row["task_id"]),
                str(row["segment_id"]),
                int(row["start"]),
                int(row["goal"]),
                float(row["pass_time"]),
                float(row["pass_time"]),
                float(row["std"]),
            )
        )
    return records


def _runtime_window(name: str, offset: int, size: int, context: str, source: str, fault_edges: tuple[tuple[int, int], ...] = (), fault_windows: tuple[tuple[int, int, float, float], ...] = ()) -> Any:
    from scripts.eval.run_g4g_no_astar_fallback_validation import RuntimeWindow

    return RuntimeWindow(name, offset, size, context, source, fault_edges, fault_windows)


def run_state_and_repro(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    branch = _git_text(["branch", "--show-current"])
    head_full = _git_text(["rev-parse", "HEAD"])
    head_short = _git_text(["rev-parse", "--short", "HEAD"])
    upstream = _git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    upstream_head = _git_text(["rev-parse", "@{u}"]) if upstream else ""
    status_short = _git_text(["status", "--short"])
    status_lines = [line for line in status_short.splitlines() if line.strip()]
    status_summary = "" if not status_lines else f"dirty_entries={len(status_lines)}; first={status_lines[0]}"
    log_20 = _git_text(["log", "--oneline", "-20"])
    legacy_diff = _git_text(["diff", "--name-only", "--", "legacy"])
    contains_prev = subprocess.run(["git", "merge-base", "--is-ancestor", REQUIRED_PREV_COMMIT, "HEAD"], cwd=ROOT, check=False).returncode == 0
    head_ancestor_upstream = bool(upstream) and subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", upstream], cwd=ROOT, check=False).returncode == 0
    ignored = _git_text(["check-ignore", "-v", str(HIGH_FLOW_TASKS.relative_to(ROOT))])
    file_exists = HIGH_FLOW_TASKS.exists()
    rows = [
        {"check": "branch", "status": "PASS" if branch else "WARN", "local_value": branch, "expected_or_remote_value": upstream, "details": "current local branch and tracking branch"},
        {"check": "head", "status": "INFO", "local_value": head_full, "expected_or_remote_value": upstream_head, "details": head_short},
        {"check": "head_contains_209f895", "status": "PASS" if contains_prev else "FAIL", "local_value": contains_prev, "expected_or_remote_value": REQUIRED_PREV_COMMIT, "details": "G4IRSF2 commit must be an ancestor"},
        {"check": "head_is_ancestor_of_upstream", "status": "PASS" if head_ancestor_upstream else "WARN", "local_value": head_ancestor_upstream, "expected_or_remote_value": upstream, "details": "Before this run local should match upstream; after new commit it will become ahead until push."},
        {
            "check": "working_tree_status_during_g4irsf3_generation",
            "status": "PASS" if not status_short else "INFO",
            "local_value": status_summary,
            "expected_or_remote_value": "clean_before_generation",
            "details": "The tree is expected to become dirty while G4IRSF3 artifacts are generated or staged; legacy diff is checked separately.",
        },
        {"check": "legacy_java_diff_empty", "status": "PASS" if not legacy_diff else "FAIL", "local_value": legacy_diff.replace("\n", " | "), "expected_or_remote_value": "", "details": "legacy Java must stay read-only"},
        {"check": "g4irsf2_high_flow_tasks_jsonl_ignored", "status": "PASS" if ignored else "FAIL", "local_value": ignored, "expected_or_remote_value": ".gitignore entry", "details": "large JSONL is reproduced, not committed"},
        {"check": "g4irsf2_high_flow_tasks_jsonl_exists", "status": "PASS" if file_exists else "WARN", "local_value": file_exists, "expected_or_remote_value": manifest.get("task_output", ""), "details": "reproduction script can regenerate it if missing"},
    ]
    _write_csv(GIT_STATE, rows, ["check", "status", "local_value", "expected_or_remote_value", "details"])
    ctx = {"branch": branch, "head_short": head_short}
    STATE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 State And Repro Report",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Git State",
                "",
                _markdown_table(["Check", "Status", "Details"], [[row["check"], row["status"], row["details"]] for row in rows]),
                "",
                "## Recent Log",
                "",
                "```text",
                log_20,
                "```",
                "",
                "The large high-flow task file remains ignored; the tracked manifest and G4IRSF3 reproduction script are the reproducibility boundary.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_high_flow_repro(args: argparse.Namespace) -> dict[str, Any]:
    _prepare_imports()
    from scripts.data.g4irsf3_reproduce_high_flow_tasks import run as run_repro

    ns = argparse.Namespace(
        manifest=str(MANIFEST_PATH),
        output=str(HIGH_FLOW_TASKS),
        verify_sha256=True,
        force_regenerate=bool(args.force_regenerate_tasks),
        seed=args.seed,
    )
    return run_repro(ns)


def _expected_chunk_count(manifest: dict[str, Any], chunk_size: int, max_chunks: int) -> int:
    count = math.ceil(int(manifest["task_count"]) / chunk_size)
    return min(count, max_chunks) if max_chunks else count


def _reuse_chunked_rows(manifest: dict[str, Any], chunk_size: int, max_chunks: int) -> list[dict[str, str]]:
    if not CHUNKED_TABLE.exists() or max_chunks:
        return []
    rows = _read_csv(CHUNKED_TABLE)
    expected = _expected_chunk_count(manifest, chunk_size, max_chunks)
    if len(rows) == expected and all(int(row.get("chunk_size_requested") or 0) == chunk_size for row in rows):
        return rows
    return []


def run_chunked_benchmark(manifest: dict[str, Any], args: argparse.Namespace) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reused = [] if args.force_rerun_chunks else _reuse_chunked_rows(manifest, args.chunk_size, args.max_chunks)
    if reused:
        streaming_rows = _streaming_rows_from_chunks(manifest, [dict(row) for row in reused], reused=True)
        _write_csv(STREAMING_TABLE, streaming_rows, _streaming_fields())
        _write_full_manifest_report(manifest, [dict(row) for row in reused], streaming_rows, reused=True)
        return [dict(row) for row in reused], streaming_rows

    _prepare_imports()
    from czr005 import cpp_backend
    import scripts.eval.g4i_runtime as g4i

    policy_data = json.loads(g4i.MODEL_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for chunk_index, task_rows in _iter_jsonl_chunks(HIGH_FLOW_TASKS, args.chunk_size, args.max_chunks):
        offset = chunk_index * args.chunk_size
        window_name = f"g4irsf3_full_manifest_chunk{chunk_index:03d}"
        window = _runtime_window(
            window_name,
            offset,
            len(task_rows),
            "full_manifest_chunk_reset_no_carryover",
            "g4irsf2_high_flow_manifest",
        )
        route_rows = _route_records(task_rows, window_name, "g4irsf3_full_manifest_level_c")
        started = time.perf_counter()
        payload = g4i._cpp_replay(
            mode=g4i._official_mode(),
            window_records=g4i._window_records_from_runtime([window]),
            route_records=route_rows,
            policy_data=policy_data,
            trace_limit=0,
            summary_only=True,
            profile_enabled=False,
            enable_edge_overlap_diagnostic=False,
            audit_final_conflicts=True,
        )
        noastar_elapsed = time.perf_counter() - started
        cases = [(int(row[4]), int(row[5])) for row in route_rows]
        astar_started = time.perf_counter()
        astar = cpp_backend.benchmark_legacy_map_paths(g4i.LEGACY_MAP_PATH, cases, repeats=1, allow_ragged_heuristic=True)
        astar_elapsed = time.perf_counter() - astar_started
        astar_seconds = float(astar.get("elapsed_seconds", astar_elapsed))
        summary = payload["summary"]
        rows.append(
            {
                "chunk_index": chunk_index,
                "window_name": window_name,
                "task_offset": offset,
                "task_count": len(task_rows),
                "chunk_size_requested": args.chunk_size,
                "task_stream_generation_level": manifest["generation_level"],
                "claim_scope": manifest["claim_scope"],
                "topology_changed": False,
                "source_manifest": MANIFEST_PATH.relative_to(ROOT).as_posix(),
                "carry_reservations": False,
                "carry_traffic_memory": False,
                "continuity_claim_allowed": False,
                "chunk_reset_note": "Each chunk is replayed from empty local reservation state because the current C++ API has no reservation import/export.",
                "noastar_runtime_seconds": noastar_elapsed,
                "noastar_cpp_elapsed_seconds": float(summary.get("elapsed_seconds") or 0.0),
                "noastar_planned_count": int(summary["planned_count"]),
                "noastar_node_window_conflicts": int(summary["node_window_conflicts"]),
                "noastar_full_astar_calls": int(summary["runtime_full_cie_astar_calls"]),
                "model_inference_count": int(summary.get("model_inference_count") or 0),
                "rule_fallback_calls": int(summary.get("rule_fallback_calls") or 0),
                "edge_overlap_counted_primary": False,
                "static_astar_proxy_seconds": astar_seconds,
                "static_astar_total_plans": int(astar["total_plans"]),
                "astar_proxy_note": "static lower-bound path proxy; not full Java CIE scheduler",
                "astar_runtime_over_noastar": astar_seconds / noastar_elapsed if noastar_elapsed > 0 else 0.0,
            }
        )
        print(
            "g4irsf3 chunk complete "
            f"chunk={chunk_index} tasks={len(task_rows)} planned={summary['planned_count']} "
            f"conflicts={summary['node_window_conflicts']} noastar_s={noastar_elapsed:.3f}"
        )
    _write_csv(CHUNKED_TABLE, rows, _chunk_fields())
    streaming_rows = _streaming_rows_from_chunks(manifest, rows, reused=False)
    _write_csv(STREAMING_TABLE, streaming_rows, _streaming_fields())
    _write_full_manifest_report(manifest, rows, streaming_rows, reused=False)
    return rows, streaming_rows


def _reuse_failed_task_rows(chunk_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not FAILED_TASKS.exists():
        return []
    rows = _read_csv(FAILED_TASKS)
    expected = sum(max(0, int(row["task_count"]) - int(row["noastar_planned_count"])) for row in chunk_rows)
    if len(rows) == expected:
        return rows
    return []


def run_failed_task_detail(manifest: dict[str, Any], args: argparse.Namespace, chunk_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected_failures = sum(max(0, int(row["task_count"]) - int(row["noastar_planned_count"])) for row in chunk_rows)
    if expected_failures == 0:
        _write_csv(FAILED_TASKS, [], _failed_task_fields())
        return []
    reused = _reuse_failed_task_rows(chunk_rows)
    if reused and not args.force_rerun_failed_tasks:
        return [dict(row) for row in reused]

    _prepare_imports()
    import scripts.eval.g4i_runtime as g4i

    failing_indices = {int(row["chunk_index"]) for row in chunk_rows if int(row["noastar_planned_count"]) < int(row["task_count"])}
    policy_data = json.loads(g4i.MODEL_PATH.read_text(encoding="utf-8"))
    failed_rows: list[dict[str, Any]] = []
    for chunk_index, task_rows in _iter_jsonl_chunks(HIGH_FLOW_TASKS, args.chunk_size, 0):
        if chunk_index not in failing_indices:
            continue
        offset = chunk_index * args.chunk_size
        window_name = f"g4irsf3_failed_detail_chunk{chunk_index:03d}"
        window = _runtime_window(
            window_name,
            offset,
            len(task_rows),
            "full_manifest_failure_detail_reset_state",
            "g4irsf2_high_flow_manifest",
        )
        route_rows = _route_records(task_rows, window_name, "g4irsf3_full_manifest_failure_detail")
        payload = g4i._cpp_replay(
            mode=g4i._official_mode(),
            window_records=g4i._window_records_from_runtime([window]),
            route_records=route_rows,
            policy_data=policy_data,
            trace_limit=0,
            summary_only=False,
            profile_enabled=False,
            enable_edge_overlap_diagnostic=False,
            audit_final_conflicts=True,
        )
        for task in payload.get("tasks", []):
            if bool(task.get("goal_reached")):
                continue
            failed_rows.append(
                {
                    "chunk_index": chunk_index,
                    "window_name": window_name,
                    "task_id": int(task.get("task_id", 0)),
                    "segment_id": task.get("segment_id", ""),
                    "start": task.get("path", [""])[0] if task.get("path") else "",
                    "goal": next((int(row[5]) for row in route_rows if int(row[2]) == int(task.get("task_id", -1)) and str(row[3]) == str(task.get("segment_id", ""))), ""),
                    "failed_reason": task.get("failed_reason", ""),
                    "steps": task.get("steps", ""),
                    "path": task.get("path", []),
                    "node_window_conflicts": task.get("node_window_conflicts", ""),
                    "runtime_full_cie_astar_calls": task.get("full_cie_astar_fallback_calls", ""),
                    "task_stream_generation_level": manifest["generation_level"],
                    "topology_changed": False,
                    "source_manifest": MANIFEST_PATH.relative_to(ROOT).as_posix(),
                    "edge_capacity_primary_constraint": False,
                }
            )
        print(f"g4irsf3 failure detail complete chunk={chunk_index} failed={sum(1 for row in failed_rows if int(row['chunk_index']) == chunk_index)}")
    _write_csv(FAILED_TASKS, failed_rows, _failed_task_fields())
    return failed_rows


def _failed_task_fields() -> list[str]:
    return [
        "chunk_index",
        "window_name",
        "task_id",
        "segment_id",
        "start",
        "goal",
        "failed_reason",
        "steps",
        "path",
        "node_window_conflicts",
        "runtime_full_cie_astar_calls",
        "task_stream_generation_level",
        "topology_changed",
        "source_manifest",
        "edge_capacity_primary_constraint",
    ]


def _chunk_fields() -> list[str]:
    return [
        "chunk_index",
        "window_name",
        "task_offset",
        "task_count",
        "chunk_size_requested",
        "task_stream_generation_level",
        "claim_scope",
        "topology_changed",
        "source_manifest",
        "carry_reservations",
        "carry_traffic_memory",
        "continuity_claim_allowed",
        "chunk_reset_note",
        "noastar_runtime_seconds",
        "noastar_cpp_elapsed_seconds",
        "noastar_planned_count",
        "noastar_node_window_conflicts",
        "noastar_full_astar_calls",
        "model_inference_count",
        "rule_fallback_calls",
        "edge_overlap_counted_primary",
        "static_astar_proxy_seconds",
        "static_astar_total_plans",
        "astar_proxy_note",
        "astar_runtime_over_noastar",
    ]


def _streaming_fields() -> list[str]:
    return [
        "mode",
        "status",
        "attempted",
        "task_count",
        "estimated_noastar_seconds",
        "measured_chunk_count",
        "measured_chunk_task_count",
        "planned_count_sum",
        "node_window_conflicts_sum",
        "runtime_full_cie_astar_calls_sum",
        "carry_reservations_supported",
        "carry_traffic_memory_supported",
        "continuity_claim_allowed",
        "blocked_reason",
        "notes",
    ]


def _streaming_rows_from_chunks(manifest: dict[str, Any], rows: list[dict[str, Any]], reused: bool) -> list[dict[str, Any]]:
    measured_tasks = sum(int(row["task_count"]) for row in rows)
    measured_time = sum(float(row["noastar_runtime_seconds"]) for row in rows)
    manifest_tasks = int(manifest["task_count"])
    estimate = measured_time * manifest_tasks / measured_tasks if measured_tasks else 0.0
    full_chunks_measured = measured_tasks == manifest_tasks
    return [
        {
            "mode": "chunked_full_manifest_reset_state",
            "status": "MEASURED_FULL_TASK_COVERAGE" if full_chunks_measured else "MEASURED_PARTIAL_TASK_COVERAGE",
            "attempted": True,
            "task_count": manifest_tasks,
            "estimated_noastar_seconds": estimate,
            "measured_chunk_count": len(rows),
            "measured_chunk_task_count": measured_tasks,
            "planned_count_sum": sum(int(row["noastar_planned_count"]) for row in rows),
            "node_window_conflicts_sum": sum(int(row["noastar_node_window_conflicts"]) for row in rows),
            "runtime_full_cie_astar_calls_sum": sum(int(row["noastar_full_astar_calls"]) for row in rows),
            "carry_reservations_supported": False,
            "carry_traffic_memory_supported": False,
            "continuity_claim_allowed": False,
            "blocked_reason": "chunk state resets; useful coverage benchmark but not a continuous 348824-task simulation",
            "notes": "reused_existing_table" if reused else "measured_this_run",
        },
        {
            "mode": "full_manifest_8x_streaming_single_call",
            "status": "BLOCKED_API_AND_RESOURCE_BUDGET",
            "attempted": False,
            "task_count": manifest_tasks,
            "estimated_noastar_seconds": estimate,
            "measured_chunk_count": len(rows),
            "measured_chunk_task_count": measured_tasks,
            "planned_count_sum": "",
            "node_window_conflicts_sum": "",
            "runtime_full_cie_astar_calls_sum": "",
            "carry_reservations_supported": False,
            "carry_traffic_memory_supported": False,
            "continuity_claim_allowed": False,
            "blocked_reason": "current pybind runtime does not expose reservation/traffic memory import-export; single-call run is projected from chunks and not promoted",
            "notes": "resource/API blocker preserved as negative result",
        },
    ]


def _write_full_manifest_report(manifest: dict[str, Any], rows: list[dict[str, Any]], streaming_rows: list[dict[str, Any]], reused: bool) -> None:
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    task_count = sum(int(row["task_count"]) for row in rows)
    planned = sum(int(row["noastar_planned_count"]) for row in rows)
    conflicts = sum(int(row["noastar_node_window_conflicts"]) for row in rows)
    full_astar = sum(int(row["noastar_full_astar_calls"]) for row in rows)
    elapsed = sum(float(row["noastar_runtime_seconds"]) for row in rows)
    astar_elapsed = sum(float(row["static_astar_proxy_seconds"]) for row in rows)
    failure_count = task_count - planned
    FULL_MANIFEST_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 Full-Manifest Benchmark Report",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Result",
                "",
                _markdown_table(
                    ["Measured Tasks", "Planned", "Remaining Failed", "Node Conflicts", "Full A*", "No-A* s", "Static A* Proxy s"],
                    [[task_count, planned, failure_count, conflicts, full_astar, f"{elapsed:.3f}", f"{astar_elapsed:.3f}"]],
                ),
                "",
                "## Streaming Status",
                "",
                _markdown_table(
                    ["Mode", "Status", "Continuity?", "Reason"],
                    [[row["mode"], row["status"], row["continuity_claim_allowed"], row["blocked_reason"]] for row in streaming_rows],
                ),
                "",
                "This is a full task-coverage benchmark when all chunks are present, but it is not a continuous simulation because each chunk starts with empty reservation and traffic memory. That limitation is kept as the main blocker.",
                f"Failed task case details, when any exist, are written to `{FAILED_TASKS.relative_to(ROOT).as_posix()}`.",
                "",
                f"reused_existing_chunk_table: `{reused}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _load_graph() -> tuple[dict[int, list[int]], list[list[float]]]:
    data = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    outgoing = {int(node["location"]): [int(item) for item in node["outgoing"]] for node in data["nodes"]}
    heuristic = [[float(value) for value in row] for row in data["heuristic_time"]]
    return outgoing, heuristic


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


def _static_shadow_route(
    start: int,
    goal: int,
    outgoing: dict[int, list[int]],
    heuristic: list[list[float]],
    variant: FaultVariant,
    fault_edges: set[tuple[int, int]],
    max_steps: int = 80,
) -> dict[str, Any]:
    current = start
    path = [current]
    visits = Counter({current: 1})
    held = False
    for step in range(max_steps):
        if current == goal:
            return {"goal_reached": True, "path": path, "steps": step, "failed_reason": "", "held": held}
        candidates = list(outgoing.get(current, []))
        if not candidates:
            return {"goal_reached": False, "path": path, "steps": step, "failed_reason": "no_outgoing_candidate", "held": held}
        available = [node for node in candidates if (current, node) not in fault_edges]
        if not available:
            return {"goal_reached": False, "path": path, "steps": step, "failed_reason": "all_candidates_faulted", "held": held}
        risks = {node: _dead_end_risk(node, outgoing, fault_edges, variant.depth) for node in available}
        safe = [node for node in available if not risks[node]]
        if variant.hard_avoid and safe:
            available = safe
        elif variant.wait_if_no_safe and not safe:
            return {"goal_reached": False, "path": path, "steps": step, "failed_reason": "wait_at_upstream_fault_risk", "held": True}
        best = min(
            available,
            key=lambda node: (
                (variant.penalty if risks[node] else 0.0) + heuristic[node][goal] + visits[node] * 1000.0,
                node,
            ),
        )
        current = best
        path.append(current)
        visits[current] += 1
        if visits[current] > 2:
            return {"goal_reached": False, "path": path, "steps": step + 1, "failed_reason": "loop_guard", "held": held}
    return {"goal_reached": False, "path": path, "steps": max_steps, "failed_reason": "max_steps_exceeded", "held": held}


def run_fault_aware_audit(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    outgoing, heuristic = _load_graph()
    failure_rows = _read_csv(G4IRSF2_FAULT_CASES)
    static_failures = [row for row in failure_rows if row.get("scenario") == "static_fault_18_22"]
    repair_failures = [row for row in failure_rows if row.get("scenario", "").startswith("repair_18_22")]
    keys = {(int(row["task_id"]), str(row["segment_id"])) for row in static_failures}
    tasks = _task_lookup(keys)
    fault_edges = {FAULT_EDGE}
    upstream_rows: list[dict[str, Any]] = []
    for row in static_failures:
        path = _parse_path(row.get("path", "[]"))
        key = (int(row["task_id"]), str(row["segment_id"]))
        task = tasks.get(key, {})
        for index in range(max(0, len(path) - 1)):
            current = path[index]
            chosen = path[index + 1]
            candidates = outgoing.get(current, [])
            candidate_features = [
                {
                    "candidate": cand,
                    "direct_faulted": (current, cand) in fault_edges,
                    "dead_end_depth2": _dead_end_risk(cand, outgoing, fault_edges, 2),
                    "dead_end_depth3": _dead_end_risk(cand, outgoing, fault_edges, 3),
                }
                for cand in candidates
            ]
            safe_depth3 = [item["candidate"] for item in candidate_features if not item["direct_faulted"] and not item["dead_end_depth3"]]
            upstream_rows.append(
                {
                    "scenario": row["scenario"],
                    "task_id": row["task_id"],
                    "segment_id": row["segment_id"],
                    "start": row.get("start", ""),
                    "goal": task.get("goal", ""),
                    "path": path,
                    "decision_index": index,
                    "current_node": current,
                    "selected_next_node": chosen,
                    "candidate_next_nodes": candidates,
                    "selected_direct_faulted": (current, chosen) in fault_edges,
                    "selected_dead_end_depth2": _dead_end_risk(chosen, outgoing, fault_edges, 2),
                    "selected_dead_end_depth3": _dead_end_risk(chosen, outgoing, fault_edges, 3),
                    "safe_alternatives_depth3": safe_depth3,
                    "fault_edge": FAULT_EDGE,
                    "uses_teacher_path_or_future_schedule": False,
                }
            )
    feature_rows = []
    for current, candidates in sorted(outgoing.items()):
        for candidate in candidates:
            d1 = _dead_end_risk(candidate, outgoing, fault_edges, 1)
            d2 = _dead_end_risk(candidate, outgoing, fault_edges, 2)
            d3 = _dead_end_risk(candidate, outgoing, fault_edges, 3)
            if d1 or d2 or d3 or current in {3, 4, 5, 16, 17, 18, 19}:
                feature_rows.append(
                    {
                        "current_node": current,
                        "candidate_next_node": candidate,
                        "out_degree_current": len(candidates),
                        "candidate_outgoing": outgoing.get(candidate, []),
                        "direct_faulted": (current, candidate) in fault_edges,
                        "dead_end_risk_depth1": d1,
                        "dead_end_risk_depth2": d2,
                        "dead_end_risk_depth3": d3,
                        "fault_edge": FAULT_EDGE,
                        "feature_source": "local_static_topology_plus_current_fault_edges",
                        "teacher_leakage": False,
                    }
                )
    variants = [
        FaultVariant("baseline_g4irsf2_runtime_model_plus_pibt", 0, 0.0, False, False, "Measured G4IRSF2 runtime failures; not a shadow route."),
        FaultVariant("shadow_dead_end_depth2_soft_penalty", 2, 5000.0, False, False, "Local static topology dead-end penalty."),
        FaultVariant("shadow_dead_end_depth3_soft_penalty", 3, 5000.0, False, False, "Looks one more hop upstream, enough to see 3->16->17->18->22."),
        FaultVariant("shadow_dead_end_depth3_hard_avoid", 3, 5000.0, True, False, "Avoid risky candidates only when a local safe alternative exists."),
        FaultVariant("shadow_depth3_wait_if_no_safe_candidate", 3, 5000.0, True, True, "If every visible candidate leads into the broken 18->22 corridor, hold/wait instead of entering."),
    ]
    variant_rows: list[dict[str, Any]] = []
    baseline_failures = len(static_failures)
    baseline_scope = 4096
    for variant in variants:
        if variant.name == "baseline_g4irsf2_runtime_model_plus_pibt":
            variant_rows.append(
                {
                    "policy_variant": variant.name,
                    "evaluation_scope": "g4irsf2_static_fault_18_22_4096_runtime",
                    "policy_runtime_status": "MEASURED_EXISTING_CPP_RUNTIME",
                    "task_count": baseline_scope,
                    "baseline_failure_cases_evaluated": baseline_failures,
                    "planned_count": baseline_scope - baseline_failures,
                    "recovered_from_baseline_failures_shadow": 0,
                    "held_or_waited_shadow": 0,
                    "remaining_failed_shadow": baseline_failures,
                    "node_window_conflicts": 0,
                    "runtime_full_cie_astar_calls": 0,
                    "edge_capacity_primary_constraint": False,
                    "uses_teacher_path_or_future_schedule": False,
                    "promoted_to_runtime": False,
                    "notes": variant.notes,
                }
            )
            continue
        recovered = 0
        held = 0
        failed = 0
        reasons: Counter[str] = Counter()
        sample_paths = []
        for row in static_failures:
            key = (int(row["task_id"]), str(row["segment_id"]))
            task = tasks.get(key)
            if not task:
                failed += 1
                reasons["missing_task_lookup"] += 1
                continue
            result = _static_shadow_route(int(task["start"]), int(task["goal"]), outgoing, heuristic, variant, fault_edges)
            if result["goal_reached"]:
                recovered += 1
            elif result["held"]:
                held += 1
            else:
                failed += 1
            reasons[str(result.get("failed_reason", ""))] += 1
            if len(sample_paths) < 5:
                sample_paths.append(result["path"])
        variant_rows.append(
            {
                "policy_variant": variant.name,
                "evaluation_scope": "g4irsf2_static_fault_18_22_failure_cases_shadow_only",
                "policy_runtime_status": "SHADOW_LOCAL_POLICY_PROXY_NOT_PROMOTED",
                "task_count": baseline_scope,
                "baseline_failure_cases_evaluated": baseline_failures,
                "planned_count": (baseline_scope - baseline_failures) + recovered,
                "recovered_from_baseline_failures_shadow": recovered,
                "held_or_waited_shadow": held,
                "remaining_failed_shadow": failed,
                "node_window_conflicts": "not_evaluated_shadow",
                "runtime_full_cie_astar_calls": 0,
                "edge_capacity_primary_constraint": False,
                "uses_teacher_path_or_future_schedule": False,
                "promoted_to_runtime": False,
                "notes": f"{variant.notes}; reasons={dict(reasons)}; sample_paths={sample_paths[:2]}",
            }
        )
    _write_csv(
        UPSTREAM_CASES,
        upstream_rows,
        [
            "scenario",
            "task_id",
            "segment_id",
            "start",
            "goal",
            "path",
            "decision_index",
            "current_node",
            "selected_next_node",
            "candidate_next_nodes",
            "selected_direct_faulted",
            "selected_dead_end_depth2",
            "selected_dead_end_depth3",
            "safe_alternatives_depth3",
            "fault_edge",
            "uses_teacher_path_or_future_schedule",
        ],
    )
    _write_csv(
        DEAD_END_FEATURES,
        feature_rows,
        [
            "current_node",
            "candidate_next_node",
            "out_degree_current",
            "candidate_outgoing",
            "direct_faulted",
            "dead_end_risk_depth1",
            "dead_end_risk_depth2",
            "dead_end_risk_depth3",
            "fault_edge",
            "feature_source",
            "teacher_leakage",
        ],
    )
    _write_csv(
        FAULT_VARIANTS,
        variant_rows,
        [
            "policy_variant",
            "evaluation_scope",
            "policy_runtime_status",
            "task_count",
            "baseline_failure_cases_evaluated",
            "planned_count",
            "recovered_from_baseline_failures_shadow",
            "held_or_waited_shadow",
            "remaining_failed_shadow",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
            "edge_capacity_primary_constraint",
            "uses_teacher_path_or_future_schedule",
            "promoted_to_runtime",
            "notes",
        ],
    )
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    best_shadow = max((row for row in variant_rows if "shadow" in row["policy_variant"]), key=lambda row: int(row["recovered_from_baseline_failures_shadow"]), default={})
    FAULT_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 Fault-Aware Upstream Avoidance Report",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Finding",
                "",
                f"G4IRSF2 static 18->22 failures preserved: `{baseline_failures}` out of `{baseline_scope}`.",
                f"Repair-window failures preserved from G4IRSF2: `{len(repair_failures)}`.",
                "",
                "The repeated paths show the problem happens before node 18. Once a bag reaches 18 while 18->22 is broken, node 18 has no valid outgoing edge. The local fix has to happen upstream, for example at 16 or 19, and sometimes at the source if the first corridor has no safe branch.",
                "",
                "## Shadow Variant Best Case",
                "",
                _markdown_table(
                    ["Variant", "Recovered", "Held", "Remaining", "Promoted?"],
                    [[best_shadow.get("policy_variant", ""), best_shadow.get("recovered_from_baseline_failures_shadow", ""), best_shadow.get("held_or_waited_shadow", ""), best_shadow.get("remaining_failed_shadow", ""), best_shadow.get("promoted_to_runtime", "")]],
                ),
                "",
                "The improvement is shadow-only: it uses only local static topology and the current fault edge, with no teacher path and no future schedule, but it is not wired into the promoted C++ runtime in this step.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return upstream_rows, feature_rows, variant_rows


def run_wait_policy(manifest: dict[str, Any], variant_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best_wait = next((row for row in variant_rows if row["policy_variant"] == "shadow_depth3_wait_if_no_safe_candidate"), {})
    rows = [
        {
            "case": "already_at_node18_static_fault_18_22",
            "allowed_runtime_inputs": "current_node,outgoing_edges,current_fault_edges",
            "action": "FAIL_SAFE_OR_HOLD_AT_NODE",
            "planned_as_success": False,
            "uses_repair_eta": False,
            "node_window_conflicts_evaluated": False,
            "runtime_full_cie_astar_calls": 0,
            "notes": "18 has only one outgoing edge, so the local policy cannot create a new route at node 18.",
        },
        {
            "case": "upstream_no_safe_candidate_visible",
            "allowed_runtime_inputs": "current_node,outgoing_edges,current_fault_edges,local_static_topology_depth3",
            "action": "WAIT_AT_SOURCE_OR_UPSTREAM_RETRY",
            "planned_as_success": False,
            "uses_repair_eta": False,
            "node_window_conflicts_evaluated": False,
            "runtime_full_cie_astar_calls": 0,
            "notes": f"Shadow wait variant held {best_wait.get('held_or_waited_shadow', '')} baseline failures instead of entering the dead-end corridor.",
        },
        {
            "case": "scheduled_repair_window_known_by_operations",
            "allowed_runtime_inputs": "current_node,current_fault_edges,repair_schedule_if_operationally_available",
            "action": "WAIT_UNTIL_REPAIR_THEN_RETRY",
            "planned_as_success": "diagnostic_only",
            "uses_repair_eta": True,
            "node_window_conflicts_evaluated": False,
            "runtime_full_cie_astar_calls": 0,
            "notes": "Repair ETA is not a default allowed input for promoted runtime; it can only be used if the real ICS runtime exposes it before decision time.",
        },
        {
            "case": "unknown_repair_time",
            "allowed_runtime_inputs": "current_node,current_fault_edges",
            "action": "WAIT_WITH_MAX_HOLD_THEN_SAFE_FAIL",
            "planned_as_success": False,
            "uses_repair_eta": False,
            "node_window_conflicts_evaluated": False,
            "runtime_full_cie_astar_calls": 0,
            "notes": "Do not spin forever; preserve no-path/fail result after a configured operational hold budget.",
        },
    ]
    _write_csv(
        WAIT_POLICY,
        rows,
        [
            "case",
            "allowed_runtime_inputs",
            "action",
            "planned_as_success",
            "uses_repair_eta",
            "node_window_conflicts_evaluated",
            "runtime_full_cie_astar_calls",
            "notes",
        ],
    )
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    WAIT_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 Wait Or Fail Semantics Report",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Decision Rules",
                "",
                _markdown_table(["Case", "Action", "Success Claim?"], [[row["case"], row["action"], row["planned_as_success"]] for row in rows]),
                "",
                "Waiting is a safety action, not a hidden success. If repair time is unknown, the policy should hold only up to an operational budget and then report failure/no-path.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_java_baseline_audit(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    _prepare_imports()
    from scripts.eval.g4irsf2_original_ics_audit import resolve_ics_root, simulation_root

    ics_root = resolve_ics_root(None)
    sim_root = simulation_root(ics_root)
    attempts: list[dict[str, Any]] = []
    javac = shutil.which("javac")
    java = shutil.which("java")
    attempts.append(
        {
            "attempt": "locate_original_ics_project",
            "status": "PASS" if sim_root.exists() else "FAIL",
            "command": "",
            "returncode": "",
            "stdout_excerpt": "",
            "stderr_excerpt": "",
            "notes": str(sim_root),
        }
    )
    attempts.append(
        {
            "attempt": "locate_javac",
            "status": "PASS" if javac else "BLOCKED",
            "command": "javac -version",
            "returncode": "",
            "stdout_excerpt": javac or "",
            "stderr_excerpt": "",
            "notes": "Java compiler needed for read-only baseline attempt.",
        }
    )
    compile_status = "SKIPPED"
    run_status = "SKIPPED"
    if sim_root.exists() and javac:
        java_files = sorted((sim_root / "src").rglob("*.java"))
        with tempfile.TemporaryDirectory(prefix="g4irsf3_java_classes_") as tmp:
            tmp_path = Path(tmp)
            argfile = tmp_path / "sources.txt"
            argfile.write_text("\n".join(path.as_posix() for path in java_files) + "\n", encoding="utf-8")
            command = [
                javac,
                "-encoding",
                "UTF-8",
                "-sourcepath",
                (sim_root / "src").as_posix(),
                "-d",
                tmp_path.as_posix(),
                f"@{argfile.as_posix()}",
            ]
            result = subprocess.run(command, cwd=sim_root, check=False, capture_output=True, text=True, timeout=60)
            compile_status = "PASS" if result.returncode == 0 else "FAIL"
            attempts.append(
                {
                    "attempt": "compile_original_java_read_only",
                    "status": compile_status,
                    "command": " ".join(command[:6]) + " @sources",
                    "returncode": result.returncode,
                    "stdout_excerpt": result.stdout[:500],
                    "stderr_excerpt": result.stderr[:500],
                    "notes": f"compiled {len(java_files)} source files into temporary directory; original tree not modified",
                }
            )
            if result.returncode == 0 and java:
                run_command = [java, "-Djava.awt.headless=true", "-cp", str(tmp_path), "RUN.Main"]
                try:
                    run = subprocess.run(run_command, cwd=sim_root, check=False, capture_output=True, text=True, timeout=20)
                    run_status = "PASS" if run.returncode == 0 else "BLOCKED"
                    attempts.append(
                        {
                            "attempt": "run_original_java_headless",
                            "status": run_status,
                            "command": " ".join(run_command),
                            "returncode": run.returncode,
                            "stdout_excerpt": run.stdout[:500],
                            "stderr_excerpt": run.stderr[:500],
                            "notes": "Headless run avoids opening the GUI; nonzero often indicates GUI/runtime coupling rather than source modification.",
                        }
                    )
                except subprocess.TimeoutExpired as exc:
                    run_status = "BLOCKED"
                    attempts.append(
                        {
                            "attempt": "run_original_java_headless",
                            "status": "BLOCKED",
                            "command": " ".join(run_command),
                            "returncode": "timeout",
                            "stdout_excerpt": (exc.stdout or "")[:500] if isinstance(exc.stdout, str) else "",
                            "stderr_excerpt": (exc.stderr or "")[:500] if isinstance(exc.stderr, str) else "",
                            "notes": "Timed out; treat original Java scheduler as not runnable in this local non-interactive audit.",
                        }
                    )
    semantics_rows = [
        {"semantic": "inputdata_source_queue", "java_evidence": "FOUND_G4IRSF2", "czr005_proxy": "preserved_in_high_flow_resample", "alignment": "ALIGNED_LIMITED", "notes": "Uses original inputdata distribution; high-flow is distribution-preserving resample."},
        {"semantic": "early_bag_storage_split", "java_evidence": "FOUND_G4IRSF2", "czr005_proxy": "preserved_in_expanded_tasks", "alignment": "ALIGNED_LIMITED", "notes": "Storage in/out segments are retained from parsed original input."},
        {"semantic": "astar_node_time_window_constraint", "java_evidence": "FOUND_G4IRSF2", "czr005_proxy": "node reservation conflict audit", "alignment": "ALIGNED_FOR_ZERO_CONFLICT_CHECK", "notes": "No edge capacity promoted."},
        {"semantic": "unfinished_task_retry", "java_evidence": "FOUND_G4IRSF2", "czr005_proxy": "G3k/G4D lineage reports", "alignment": "PARTIAL", "notes": "G4IRSF3 no-A* loop does not call Java A* retry online."},
        {"semantic": "fault_edge_exclusion", "java_evidence": "FOUND_G4IRSF2", "czr005_proxy": "current fault_edges input", "alignment": "ALIGNED_FOR_STATIC_FAULT", "notes": "18->22 fault is passed as current fault edge."},
        {"semantic": "java_gui_epoch_scheduler", "java_evidence": run_status, "czr005_proxy": "not_equivalent", "alignment": "BLOCKED", "notes": "Original Java main appears coupled to full simulation/UI path in local audit."},
        {"semantic": "full_java_cie_hca_baseline_speed", "java_evidence": compile_status, "czr005_proxy": "static_astar_lower_bound_only", "alignment": "BLOCKED_OR_LOWER_BOUND", "notes": "Do not claim paper-grade Java baseline speed."},
    ]
    noastar_proxy_rows = [
        {"dimension": "planner_calls", "original_java_expected": "Astar.research per new/unfinish task", "g4irsf3_runtime": "no runtime full CIE/A* calls", "alignment": "DIFFERENT_BY_DESIGN", "risk": "Needs Java baseline before final replacement claim."},
        {"dimension": "node_time_windows", "original_java_expected": "node interval overlap rejection", "g4irsf3_runtime": "node-window reservations; conflicts audited as primary", "alignment": "PARTIAL_MATCH", "risk": "Chunk reset prevents full continuous-state claim."},
        {"dimension": "fault_18_22", "original_java_expected": "fault edge excluded from A*", "g4irsf3_runtime": "fault edge excluded; upstream avoidance shadow only", "alignment": "PARTIAL_MATCH", "risk": "Fault-aware variant not promoted to C++ runtime yet."},
        {"dimension": "edge_overlap", "original_java_expected": "conveyor motion, no verified edge_capacity=1", "g4irsf3_runtime": "diagnostic only", "alignment": "MATCHES_GOVERNANCE", "risk": "Do not count edge overlap as primary failure."},
        {"dimension": "large_flow_generator", "original_java_expected": "not found active", "g4irsf3_runtime": "distribution_preserving_resample", "alignment": "LEVEL_C_ONLY", "risk": "Level B needs stronger original-rule generator or proof."},
    ]
    _write_csv(JAVA_ATTEMPTS, attempts, ["attempt", "status", "command", "returncode", "stdout_excerpt", "stderr_excerpt", "notes"])
    _write_csv(JAVA_SEMANTICS, semantics_rows, ["semantic", "java_evidence", "czr005_proxy", "alignment", "notes"])
    _write_csv(NOASTAR_JAVA_PROXY, noastar_proxy_rows, ["dimension", "original_java_expected", "g4irsf3_runtime", "alignment", "risk"])
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    JAVA_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 Original Java Baseline Audit",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Run Attempts",
                "",
                _markdown_table(["Attempt", "Status", "Notes"], [[row["attempt"], row["status"], row["notes"]] for row in attempts]),
                "",
                "The original Java tree was treated as read-only. Compile output, if any, was written only to a temporary directory. A blocked headless run means the complete Java/CIE runtime baseline is still not available for paper-grade speed claims.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return attempts, semantics_rows, noastar_proxy_rows


def run_astar_hardness(manifest: dict[str, Any], chunk_rows: list[dict[str, Any]], java_attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in chunk_rows:
        ratio = float(row["astar_runtime_over_noastar"])
        rows.append(
            {
                "scope": row["window_name"],
                "task_count": int(row["task_count"]),
                "noastar_runtime_seconds": float(row["noastar_runtime_seconds"]),
                "static_astar_proxy_seconds": float(row["static_astar_proxy_seconds"]),
                "static_astar_runtime_over_noastar": ratio,
                "java_cie_runtime_available": any(item["attempt"] == "run_original_java_headless" and item["status"] == "PASS" for item in java_attempts),
                "timeout_rate": 0.0,
                "retry_attempts_superlinear": "not_measured_without_java_runner",
                "failed_or_no_path_increased": int(row["noastar_planned_count"]) < int(row["task_count"]),
                "hardness_gate": "FAIL" if ratio < 1.0 else "PARTIAL",
                "negative_result_preserved": ratio < 1.0,
                "notes": "Static A* lower-bound proxy remains faster; Java CIE runner is required before stronger hardness claims.",
            }
        )
    _write_csv(
        HARDNESS_V2,
        rows,
        [
            "scope",
            "task_count",
            "noastar_runtime_seconds",
            "static_astar_proxy_seconds",
            "static_astar_runtime_over_noastar",
            "java_cie_runtime_available",
            "timeout_rate",
            "retry_attempts_superlinear",
            "failed_or_no_path_increased",
            "hardness_gate",
            "negative_result_preserved",
            "notes",
        ],
    )
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    HARDNESS_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 A* Hardness V2 Report",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Result",
                "",
                _markdown_table(["Chunks", "Any Hardness Pass?", "Negative Preserved"], [[len(rows), any(row["hardness_gate"] != "FAIL" for row in rows), any(row["negative_result_preserved"] for row in rows)]]),
                "",
                "G4IRSF3 still does not prove A* is hard on this map and task stream. The static A* lower-bound remains much faster, and the full Java/CIE baseline remains blocked or unavailable in this local audit.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_edge_pressure(manifest: dict[str, Any], fault_variants: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sweep = _read_csv(G4IRSF2_EDGE_SWEEP)
    rows: list[dict[str, Any]] = []
    for row in sweep:
        rows.append(
            {
                "policy_variant": row["policy"],
                "source_table": G4IRSF2_EDGE_SWEEP.relative_to(ROOT).as_posix(),
                "task_count": row["task_count"],
                "planned_count": row["planned_count"],
                "node_window_conflicts": row["node_window_conflicts"],
                "runtime_full_cie_astar_calls": row["runtime_full_cie_astar_calls"],
                "edge_overlap_diagnostic_only": row["edge_overlap_diagnostic_only"],
                "edge_capacity_primary_constraint": False,
                "policy_runtime_status": "G4IRSF2_DIAGNOSTIC_SHADOW_REUSED",
                "promoted_to_runtime": False,
                "notes": "Edge pressure is diagnostic; edge_capacity=1 is not a main constraint.",
            }
        )
    best_fault = max((row for row in fault_variants if "shadow" in row["policy_variant"]), key=lambda row: int(row["recovered_from_baseline_failures_shadow"]), default={})
    if best_fault:
        rows.append(
            {
                "policy_variant": "fault_aware_dead_end_pressure_depth3_shadow",
                "source_table": FAULT_VARIANTS.relative_to(ROOT).as_posix(),
                "task_count": best_fault["task_count"],
                "planned_count": best_fault["planned_count"],
                "node_window_conflicts": best_fault["node_window_conflicts"],
                "runtime_full_cie_astar_calls": best_fault["runtime_full_cie_astar_calls"],
                "edge_overlap_diagnostic_only": "not_used",
                "edge_capacity_primary_constraint": False,
                "policy_runtime_status": best_fault["policy_runtime_status"],
                "promoted_to_runtime": False,
                "notes": "Local fault pressure is about avoiding a broken dead-end corridor, not imposing conveyor edge capacity.",
            }
        )
    _write_csv(
        EDGE_POLICY,
        rows,
        [
            "policy_variant",
            "source_table",
            "task_count",
            "planned_count",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
            "edge_overlap_diagnostic_only",
            "edge_capacity_primary_constraint",
            "policy_runtime_status",
            "promoted_to_runtime",
            "notes",
        ],
    )
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    EDGE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 Edge Pressure Policy Report",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Boundary",
                "",
                "Edge overlap remains diagnostic only. G4IRSF3 does not turn it into edge_capacity=1 and does not count it as a primary safety conflict.",
                "",
                _markdown_table(["Variant", "Runtime Status", "Promoted?"], [[row["policy_variant"], row["policy_runtime_status"], row["promoted_to_runtime"]] for row in rows[:6]]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_profile_and_optimization(manifest: dict[str, Any], args: argparse.Namespace, chunk_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _prepare_imports()
    import scripts.eval.g4i_runtime as g4i

    policy_data = json.loads(g4i.MODEL_PATH.read_text(encoding="utf-8"))
    sample_rows = []
    for _idx, chunk in _iter_jsonl_chunks(HIGH_FLOW_TASKS, args.profile_sample_size, 1):
        sample_rows = chunk
        break
    profile_rows: list[dict[str, Any]] = []
    if sample_rows:
        window = _runtime_window("g4irsf3_profile_sample", 0, len(sample_rows), "profile_sample", "g4irsf2_high_flow_manifest")
        route_rows = _route_records(sample_rows, window.name, "g4irsf3_profile_sample")
        started = time.perf_counter()
        payload = g4i._cpp_replay(
            mode=g4i._official_mode(),
            window_records=g4i._window_records_from_runtime([window]),
            route_records=route_rows,
            policy_data=policy_data,
            trace_limit=0,
            summary_only=True,
            profile_enabled=True,
            enable_edge_overlap_diagnostic=False,
            audit_final_conflicts=True,
        )
        elapsed = time.perf_counter() - started
        for stage, seconds in dict(payload.get("profile", {})).items():
            profile_rows.append({"sample_scope": window.name, "stage": stage, "stage_type": "seconds", "value": float(seconds), "wall_seconds": elapsed, "task_count": len(sample_rows)})
        for counter, value in dict(payload.get("profile_counters", {})).items():
            profile_rows.append({"sample_scope": window.name, "stage": counter, "stage_type": "counter", "value": float(value), "wall_seconds": elapsed, "task_count": len(sample_rows)})
        profile_rows.append({"sample_scope": window.name, "stage": "python_wall_clock", "stage_type": "seconds", "value": elapsed, "wall_seconds": elapsed, "task_count": len(sample_rows)})
    _write_csv(STAGE_PROFILE, profile_rows, ["sample_scope", "stage", "stage_type", "value", "wall_seconds", "task_count"])
    measured_time = sum(float(row["noastar_runtime_seconds"]) for row in chunk_rows)
    measured_tasks = sum(int(row["task_count"]) for row in chunk_rows)
    chunk_mean = measured_time / max(1, len(chunk_rows))
    task_rate = measured_tasks / measured_time if measured_time > 0 else 0.0
    top_seconds = sorted([row for row in profile_rows if row["stage_type"] == "seconds"], key=lambda row: float(row["value"]), reverse=True)
    opt_rows = [
        {
            "optimization": "summary_only_trace0_edge_diag_off",
            "status": "MEASURED",
            "baseline_or_input": "g4irsf3_full_manifest_chunks",
            "task_count": measured_tasks,
            "runtime_seconds": measured_time,
            "tasks_per_second": task_rate,
            "quality_guardrail": "planned/conflict/full_astar columns in chunk table",
            "notes": "This is already the lean mode used for full-manifest chunking.",
        },
        {
            "optimization": "profile_sample_top_stage",
            "status": "MEASURED" if top_seconds else "BLOCKED",
            "baseline_or_input": top_seconds[0]["stage"] if top_seconds else "",
            "task_count": args.profile_sample_size if profile_rows else "",
            "runtime_seconds": top_seconds[0]["value"] if top_seconds else "",
            "tasks_per_second": "",
            "quality_guardrail": "same C++ replay summary",
            "notes": "Use stage profile to decide whether reservation lookup, feature construction, or final scans dominate.",
        },
        {
            "optimization": "cross_chunk_reservation_carryover",
            "status": "BLOCKED_API",
            "baseline_or_input": "current pybind no export/import state",
            "task_count": measured_tasks,
            "runtime_seconds": "",
            "tasks_per_second": "",
            "quality_guardrail": "required before continuous 348824 claim",
            "notes": "Do not reset chunks and claim continuity.",
        },
        {
            "optimization": "single_call_full_manifest_streaming",
            "status": "BLOCKED_RESOURCE_BUDGET",
            "baseline_or_input": f"chunk_mean_seconds={chunk_mean:.3f}",
            "task_count": manifest["task_count"],
            "runtime_seconds": "",
            "tasks_per_second": "",
            "quality_guardrail": "would need complete node-window final audit",
            "notes": "Projected runtime and memory risk kept as blocker.",
        },
    ]
    _write_csv(
        OPT_RESULTS,
        opt_rows,
        ["optimization", "status", "baseline_or_input", "task_count", "runtime_seconds", "tasks_per_second", "quality_guardrail", "notes"],
    )
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    OPT_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 High-Flow Runtime Optimization Report",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Measured Chunk Runtime",
                "",
                f"Measured chunk tasks: `{measured_tasks}`",
                f"Measured no-A* seconds: `{measured_time:.3f}`",
                f"Approx tasks/second: `{task_rate:.3f}`",
                "",
                "The immediate blocker is not only speed; it is also that reservation/traffic memory cannot yet be carried across chunks through the runtime API.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return profile_rows, opt_rows


def run_level_b_feasibility(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rule_rows = _read_csv(G4IRSF2_RULES)
    found = {row.get("rule_name"): row for row in rule_rows}
    checks = [
        ("fixed_real_map2_topology", "fixed_map2_topology", "PASS", "G4IRSF3 keeps data/processed/maps/map2.json unchanged."),
        ("inputdata_source_queue", "read_inputdata_as_source_queues", "PASS", "Original inputdata queue semantics are audited."),
        ("early_bag_storage_in", "storage_in_goal_47", "PASS", "Storage-in split exists in parsed task stream."),
        ("storage_out_lead_time", "storage_out_lead_2700", "PASS", "Storage-out split exists in parsed task stream."),
        ("source_queue_sort", "java_pass_time_sort", "PASS", "Pass-time ordering is preserved by generated JSONL sort."),
        ("unfinished_task_retry", "unfinish_task_retry", "PARTIAL", "Known from Java source; G4IRSF3 no-A* loop does not execute Java retry online."),
        ("node_time_window_constraint", "node_time_window_constraint", "PARTIAL", "Primary node-window conflicts are audited; full Java equivalence still blocked."),
        ("fault_repair_sampling", "fault_probability_per_edge", "PARTIAL", "Static and scheduled faults are supported; random Java event stream not reproduced."),
        ("active_large_flow_generator", "original_large_flow_generator", "FAIL", "No active original generator found; current stream remains Level C distribution-preserving resample."),
        ("continuous_full_manifest_state", "", "FAIL", "C++ API cannot carry reservation/traffic memory across chunks yet."),
    ]
    rows = []
    for coverage_item, rule_name, status, notes in checks:
        evidence = found.get(rule_name, {})
        rows.append(
            {
                "coverage_item": coverage_item,
                "g4irsf2_rule_name": rule_name,
                "source_evidence_status": evidence.get("status", "not_applicable"),
                "g4irsf3_status": status,
                "level_b_ready": status == "PASS",
                "notes": notes,
            }
        )
    _write_csv(LEVEL_B_COVERAGE, rows, ["coverage_item", "g4irsf2_rule_name", "source_evidence_status", "g4irsf3_status", "level_b_ready", "notes"])
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    LEVEL_B_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 Level B Feasibility Report",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Decision",
                "",
                "Level B is not fully ready. The real map and inputdata-derived rules are strong enough for Level C/Level B-light audits, but active original high-flow generation, continuous full-manifest runtime state, and runnable Java/CIE baseline remain blockers.",
                "",
                _markdown_table(["Item", "Status", "Ready?"], [[row["coverage_item"], row["g4irsf3_status"], row["level_b_ready"]] for row in rows]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_allowed_inputs() -> None:
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    ALLOWED_INPUTS.write_text(
        json.dumps(
            {
                "stage": "g4irsf3",
                "governance_doc": GOVERNANCE_DOC.relative_to(ROOT).as_posix(),
                "topology_changed": False,
                "runtime_full_cie_astar_fallback": False,
                "allowed_runtime_inputs": [
                    "current_node",
                    "candidate_next_nodes",
                    "goal_node",
                    "current_time",
                    "std_time",
                    "local_node_window_reservation_state",
                    "current_fault_edges",
                    "local_static_topology_depth3",
                    "runtime_traffic_pressure_from_past_and_present",
                ],
                "forbidden_runtime_inputs": [
                    "teacher_next_node",
                    "teacher_path",
                    "full_cie_route_suffix",
                    "future_schedule",
                    "future_sipp_schedule",
                    "post_hoc_success",
                    "label_source",
                    "edge_capacity_1_primary_constraint",
                ],
                "notes": "Fault-aware shadow variants are not promoted in G4IRSF3. Edge overlap remains diagnostic only.",
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def run_plain_summary(manifest: dict[str, Any], chunk_rows: list[dict[str, Any]], fault_variants: list[dict[str, Any]], java_attempts: list[dict[str, Any]]) -> None:
    measured_tasks = sum(int(row["task_count"]) for row in chunk_rows)
    planned = sum(int(row["noastar_planned_count"]) for row in chunk_rows)
    conflicts = sum(int(row["noastar_node_window_conflicts"]) for row in chunk_rows)
    best_shadow = max((row for row in fault_variants if "shadow" in row["policy_variant"]), key=lambda row: int(row["recovered_from_baseline_failures_shadow"]), default={})
    java_ok = any(row["attempt"] == "run_original_java_headless" and row["status"] == "PASS" for row in java_attempts)
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    PLAIN_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 Plain Language Summary",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "这轮做了三件事：",
                "",
                "1. 把 8x 高流量任务文件按 manifest 做了 hash 复核，确认大文件可以用脚本再生成，不需要放进 Git。",
                f"2. 把全量 `{manifest['task_count']}` 个任务拆块覆盖到 `{measured_tasks}` 个任务；这些块里 no-A* 规划 `{planned}/{measured_tasks}`，节点时间窗冲突 `{conflicts}`，运行时完整 A* 调用为 0。",
                "3. 对 18->22 故障做了前避让审计：不是到了 18 再神奇选路，而是要在 16、19 或更早位置发现前面是断路。",
                "",
                f"最好的 fault-aware shadow 变体从旧失败里恢复 `{best_shadow.get('recovered_from_baseline_failures_shadow', '')}` 个，但它还只是 shadow，没有真正接入当前 C++ runtime。",
                "",
                f"原始 Java/CIE 完整 baseline 可运行状态：`{java_ok}`。所以现在仍不能宣布最终替代 A*。",
                "",
                "结论：G4IRSF3 是扎实推进，不是 paper-grade 终点。下一步应该优先做跨块状态接续和把 fault-aware 前避让真实接入 runtime。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_promotion_gate(manifest: dict[str, Any], chunk_rows: list[dict[str, Any]], streaming_rows: list[dict[str, Any]], fault_variants: list[dict[str, Any]], java_attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    measured_tasks = sum(int(row["task_count"]) for row in chunk_rows)
    planned = sum(int(row["noastar_planned_count"]) for row in chunk_rows)
    conflicts = sum(int(row["noastar_node_window_conflicts"]) for row in chunk_rows)
    full_astar = sum(int(row["noastar_full_astar_calls"]) for row in chunk_rows)
    full_coverage = measured_tasks == int(manifest["task_count"])
    java_ok = any(row["attempt"] == "run_original_java_headless" and row["status"] == "PASS" for row in java_attempts)
    fault_promoted = any(row.get("promoted_to_runtime") in {True, "True"} for row in fault_variants if "shadow" in row.get("policy_variant", ""))
    continuity = any(row["mode"] == "full_manifest_8x_streaming_single_call" and row["status"] == "PASS" for row in streaming_rows)
    rows = [
        {"criterion": "high_flow_task_hash_verified", "status": "PASS" if HASH_TABLE.exists() else "FAIL", "evidence": HASH_TABLE.relative_to(ROOT).as_posix()},
        {"criterion": "full_manifest_task_coverage_by_chunks", "status": "PASS" if full_coverage else "PARTIAL", "evidence": f"{measured_tasks}/{manifest['task_count']} tasks measured"},
        {"criterion": "chunked_noastar_zero_conflict_zero_astar", "status": "PASS" if planned == measured_tasks and conflicts == 0 and full_astar == 0 else "FAIL", "evidence": f"planned={planned}/{measured_tasks}; conflicts={conflicts}; full_astar={full_astar}"},
        {"criterion": "continuous_full_manifest_state", "status": "FAIL" if not continuity else "PASS", "evidence": "chunk carry-over API missing; single-call full streaming blocked"},
        {"criterion": "fault_aware_upstream_avoidance_promoted", "status": "FAIL" if not fault_promoted else "PASS", "evidence": "best improvement is shadow-only"},
        {"criterion": "original_java_cie_baseline_runnable", "status": "FAIL" if not java_ok else "PASS", "evidence": "see g4irsf3_java_baseline_run_attempts.csv"},
        {"criterion": "astar_hardness_v2", "status": "FAIL", "evidence": "static A* lower-bound remains faster; Java runner unavailable"},
    ]
    execution_complete = (
        HASH_TABLE.exists()
        and CHUNKED_TABLE.exists()
        and STREAMING_TABLE.exists()
        and FAILED_TASKS.exists()
        and FAULT_VARIANTS.exists()
        and JAVA_ATTEMPTS.exists()
        and PROMOTION_REPORT.parent.exists()
    )
    primary_success = planned == measured_tasks and conflicts == 0 and full_astar == 0 and continuity and fault_promoted and java_ok
    paper_grade = all(row["status"] == "PASS" for row in rows) and primary_success
    rows.append({"criterion": "g4irsf3_execution_complete", "status": "PASS" if execution_complete else "FAIL", "evidence": "Audit artifacts generated and negative results preserved."})
    rows.append({"criterion": "g4irsf3_primary_success_gate", "status": "PASS" if primary_success else "FAIL", "evidence": "Full manifest has remaining no-A* failures and promotion blockers; do not claim success."})
    rows.append({"criterion": "g4j_paper_grade_gate", "status": "PASS" if paper_grade else "FAIL", "evidence": "Do not enter final replacement claim until continuous state, promoted fault-aware runtime, Java/CIE baseline, and A* hardness are resolved."})
    _write_csv(PROMOTION_GATE, rows, ["criterion", "status", "evidence"])
    ctx = {"branch": _git_text(["branch", "--show-current"]), "head_short": _git_text(["rev-parse", "--short", "HEAD"])}
    PROMOTION_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF3 Promotion Decision",
                "",
                *_meta_lines(ctx, str(manifest.get("generation_level", ""))),
                "",
                "## Gate",
                "",
                _markdown_table(["Criterion", "Status", "Evidence"], [[row["criterion"], row["status"], row["evidence"]] for row in rows]),
                "",
                "G4IRSF3 execution is complete as an honest engineering audit, but the primary success gate and paper-grade G4J gate remain failed. This is intentional: the blockers are now explicit instead of hidden.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_all(args: argparse.Namespace) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest()
    run_state_and_repro(manifest)
    run_high_flow_repro(args)
    chunk_rows, streaming_rows = run_chunked_benchmark(manifest, args)
    run_failed_task_detail(manifest, args, chunk_rows)
    _upstream_rows, _feature_rows, fault_variants = run_fault_aware_audit(manifest)
    run_wait_policy(manifest, fault_variants)
    java_attempts, _semantics, _proxy = run_java_baseline_audit(manifest)
    run_astar_hardness(manifest, chunk_rows, java_attempts)
    run_edge_pressure(manifest, fault_variants)
    run_profile_and_optimization(manifest, args, chunk_rows)
    run_level_b_feasibility(manifest)
    run_allowed_inputs()
    run_plain_summary(manifest, chunk_rows, fault_variants, java_attempts)
    gate_rows = run_promotion_gate(manifest, chunk_rows, streaming_rows, fault_variants, java_attempts)
    print(
        "g4irsf3 fault-aware full-manifest audit complete: "
        f"execution_gate={gate_rows[-3]['status']} primary_gate={gate_rows[-2]['status']} g4j_gate={gate_rows[-1]['status']} "
        f"chunks={len(chunk_rows)}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run G4IRSF3 fault-aware full-manifest audit.")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--max-chunks", type=int, default=0, help="Development knob only; default 0 means all chunks.")
    parser.add_argument("--profile-sample-size", type=int, default=4096)
    parser.add_argument("--force-regenerate-tasks", action="store_true")
    parser.add_argument("--force-rerun-chunks", action="store_true")
    parser.add_argument("--force-rerun-failed-tasks", action="store_true")
    parser.add_argument("--seed", type=int, default=20260703)
    return parser


if __name__ == "__main__":
    run_all(build_parser().parse_args())
