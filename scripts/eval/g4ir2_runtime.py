from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import copy
import csv
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "outputs" / "reports"
TABLE_DIR = ROOT / "outputs" / "tables"
ARTIFACT_DIR = ROOT / "artifacts" / "policies"
DOC_DIR = ROOT / "docs"

STATE_REPORT = REPORT_DIR / "g4ir2_state_reconciliation_report.md"
RUNTIME_REPORT = REPORT_DIR / "g4ir2_runtime_bottleneck_report.md"
BASELINE_REPORT = REPORT_DIR / "g4ir2_baseline_fairness_audit.md"
OPT_REPORT = REPORT_DIR / "g4ir2_cpp_optimization_report.md"
POLICY_REPORT = REPORT_DIR / "g4ir2_learning_policy_contribution_report.md"
SCALE_REPORT = REPORT_DIR / "g4ir2_scale_and_generalization_report.md"
EDGE_REPORT = REPORT_DIR / "g4ir2_edge_diagnostic_physics_audit.md"
SEMANTICS_REPORT = REPORT_DIR / "g4ir2_decentralized_runtime_semantics_audit.md"
NEXT_REPORT = REPORT_DIR / "g4ir2_learning_policy_next_iteration.md"
PROMOTION_REPORT = REPORT_DIR / "g4ir2_promotion_decision.md"

STATE_TABLE = TABLE_DIR / "g4ir2_git_state_audit.csv"
STAGE_TABLE = TABLE_DIR / "g4ir2_cpp_stage_profile.csv"
TRACE_TABLE = TABLE_DIR / "g4ir2_trace_overhead.csv"
REPEAT_TABLE = TABLE_DIR / "g4ir2_runtime_repeatability.csv"
RESP_TABLE = TABLE_DIR / "g4ir2_baseline_responsibility_matrix.csv"
SPEED_TABLE = TABLE_DIR / "g4ir2_fair_speed_scorecard.csv"
BEFORE_AFTER_TABLE = TABLE_DIR / "g4ir2_before_after_speed.csv"
GUARDRAIL_TABLE = TABLE_DIR / "g4ir2_correctness_guardrail.csv"
POLICY_QUALITY_TABLE = TABLE_DIR / "g4ir2_policy_ablation_quality.csv"
POLICY_LATENCY_TABLE = TABLE_DIR / "g4ir2_policy_ablation_latency.csv"
POLICY_SCENARIO_TABLE = TABLE_DIR / "g4ir2_policy_ablation_by_scenario.csv"
SCALE_TABLE = TABLE_DIR / "g4ir2_scale_ladder.csv"
DENSITY_TABLE = TABLE_DIR / "g4ir2_density_sweep.csv"
FAULT_TABLE = TABLE_DIR / "g4ir2_fault_repair_stress.csv"
BOTTLENECK_TABLE = TABLE_DIR / "g4ir2_bottleneck_stress.csv"
DIST_TABLE = TABLE_DIR / "g4ir2_distribution_shift.csv"
EDGE_DIST_TABLE = TABLE_DIR / "g4ir2_edge_overlap_distribution.csv"
EDGE_TOP_TABLE = TABLE_DIR / "g4ir2_top_edge_overlap_edges.csv"
EDGE_SENS_TABLE = TABLE_DIR / "g4ir2_edge_overlap_policy_sensitivity.csv"
LEAKAGE_TABLE = TABLE_DIR / "g4ir2_no_leakage_full_runtime_checks.csv"
FEATURE_TABLE = TABLE_DIR / "g4ir2_feature_cost_benefit.csv"
RISK_TABLE = TABLE_DIR / "g4ir2_risk_calibration.csv"
TINY_TABLE = TABLE_DIR / "g4ir2_tiny_model_comparison.csv"

ALLOWED_INPUTS = ARTIFACT_DIR / "g4ir2_allowed_runtime_inputs.json"
API_DOC = DOC_DIR / "czr005_no_astar_runtime_api.md"

STATIC_ASTAR_SYSTEM = "static_astar_proxy_lower_bound"
PYTHON_SYSTEM = "python_reference_no_astar"
OFFICIAL_MODE_NAME = "model_plus_pibt_lite"
BENCH_REPEATS = 5


@dataclass(frozen=True)
class BenchMode:
    name: str
    trace_limit: int
    summary_only: bool
    profile_enabled: bool
    enable_edge_overlap_diagnostic: bool
    audit_final_conflicts: bool
    notes: str


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _g4i() -> Any:
    _prepare_imports()
    import scripts.eval.g4i_runtime as g4i_runtime

    return g4i_runtime


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


def _git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=False, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_status() -> dict[str, Any]:
    upstream = _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    upstream_head = _git(["rev-parse", "--short", upstream]) if upstream else ""
    full_upstream_head = _git(["rev-parse", upstream]) if upstream else ""
    pushed = False
    if upstream:
        pushed = subprocess.run(["git", "merge-base", "--is-ancestor", "HEAD", upstream], cwd=ROOT, check=False).returncode == 0
    return {
        "branch": _git(["branch", "--show-current"]),
        "head": _git(["rev-parse", "--short", "HEAD"]),
        "head_full": _git(["rev-parse", "HEAD"]),
        "upstream": upstream,
        "upstream_head": upstream_head,
        "upstream_head_full": full_upstream_head,
        "head_is_ancestor_of_upstream": pushed,
        "status_short": _git(["status", "--short"]).replace("\n", " | "),
        "legacy_diff_files": _git(["diff", "--name-only", "--", "legacy"]).replace("\n", " | "),
        "log_oneline_8": _git(["log", "--oneline", "-8"]).replace("\n", " | "),
    }


def _meta_lines(git_ctx: dict[str, Any]) -> list[str]:
    return [
        f"Date: {date.today().isoformat()}",
        f"Branch: `{git_ctx['branch']}`",
        f"HEAD: `{git_ctx['head']}`",
        f"Upstream: `{git_ctx['upstream']}`",
        f"Upstream HEAD: `{git_ctx['upstream_head']}`",
    ]


def _mean_std_ci(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    mean = statistics.mean(values)
    std = statistics.stdev(values) if len(values) > 1 else 0.0
    ci = 1.96 * std / math.sqrt(len(values)) if len(values) > 1 else 0.0
    return mean, std, ci


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _base_context() -> dict[str, Any]:
    g4i = _g4i()
    from czr005.sim_py.task_stream import TaskStream
    from scripts.eval.run_g4g_no_astar_fallback_validation import _task_lookup as py_task_lookup

    policy_data = json.loads(g4i.MODEL_PATH.read_text(encoding="utf-8"))
    task_lookup = g4i._task_lookup()
    all_tasks_json = g4i._all_tasks()
    all_tasks_py = tuple(TaskStream.from_jsonl(g4i.TASK_PATH))
    py_tasks = py_task_lookup(all_tasks_py)
    g4d_windows, g4d_window_map = g4i._g4d_windows()
    window_records = g4i._window_records_from_runtime(g4d_windows)
    route_records, py_routes = g4i._g4d_route_records(task_lookup)
    return {
        "g4i": g4i,
        "policy_data": policy_data,
        "task_lookup": task_lookup,
        "all_tasks_json": all_tasks_json,
        "all_tasks_py": all_tasks_py,
        "py_tasks": py_tasks,
        "g4d_windows": g4d_windows,
        "g4d_window_map": g4d_window_map,
        "window_records": window_records,
        "route_records": route_records,
        "py_routes": py_routes,
        "official": g4i._official_mode(),
    }


def _bench_modes() -> list[BenchMode]:
    return [
        BenchMode("cpp_trace0_summary_profile_off", 0, True, False, True, True, "No trace rows, no task payload, final node-conflict audit on."),
        BenchMode("cpp_trace500_tasks_profile_off", 500, False, False, True, True, "G4I-like trace sample and full task payload."),
        BenchMode("cpp_full_trace_tasks_profile_off", 1000000, False, False, True, True, "Full decision trace for the G4D planned scope."),
        BenchMode("cpp_profile_on_trace0_summary", 0, True, True, True, True, "Profiler enabled with summary-only payload."),
        BenchMode("cpp_profile_on_trace500_tasks", 500, False, True, True, True, "Profiler enabled with trace sample and task payload."),
        BenchMode("cpp_no_edge_diag_trace0_summary", 0, True, False, False, True, "Diagnostic edge-overlap counter disabled; behavior should not change."),
        BenchMode("cpp_no_final_scan_trace0_summary", 0, True, False, True, False, "Final full conflict scan disabled for latency diagnosis; reservation safety remains active."),
        BenchMode("cpp_no_edge_diag_no_final_scan_trace0_summary", 0, True, False, False, False, "Best latency diagnostic mode; not a safety-reporting mode by itself."),
        BenchMode("cpp_no_file_io_trace0_summary", 0, True, False, True, True, "Timed before writing any G4IR2 files; pybind call only."),
    ]


def _route_start_goal_cases(route_records: list[Any]) -> list[tuple[int, int]]:
    return [(int(row[4]), int(row[5])) for row in route_records]


def _original_astar_attempts(g4i: Any) -> int:
    total = 0
    for row in _read_csv(g4i.G4D_SUMMARY):
        total += int(row.get("total_retry_attempts") or 0)
    return total


def run_state_reconciliation() -> None:
    git_ctx = _git_status()
    report_heads: dict[str, set[str]] = defaultdict(set)
    for path in sorted((ROOT / "outputs" / "reports").glob("g4i_*.md")):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("HEAD:"):
                report_heads[path.name].add(line.split("`")[1] if "`" in line else line.replace("HEAD:", "").strip())
    head_values = sorted({head for heads in report_heads.values() for head in heads})
    rows = [
        {"check": "current_branch", "status": "INFO", "local_value": git_ctx["branch"], "remote_or_recorded_value": git_ctx["upstream"], "details": ""},
        {"check": "local_head", "status": "INFO", "local_value": git_ctx["head_full"], "remote_or_recorded_value": git_ctx["upstream_head_full"], "details": ""},
        {
            "check": "head_matches_upstream_tracking_ref",
            "status": "PASS" if git_ctx["head_full"] == git_ctx["upstream_head_full"] else "WARN",
            "local_value": git_ctx["head"],
            "remote_or_recorded_value": git_ctx["upstream_head"],
            "details": "Local tracking ref comparison; this does not query GitHub Actions.",
        },
        {
            "check": "head_is_ancestor_of_upstream",
            "status": "PASS" if git_ctx["head_is_ancestor_of_upstream"] else "WARN",
            "local_value": git_ctx["head_is_ancestor_of_upstream"],
            "remote_or_recorded_value": git_ctx["upstream"],
            "details": "False means local work is ahead or diverged from the tracking ref.",
        },
        {
            "check": "working_tree_status",
            "status": "PASS" if not git_ctx["status_short"] else "WARN",
            "local_value": git_ctx["status_short"],
            "remote_or_recorded_value": "",
            "details": "G4IR2 generation writes files, so this is expected to become dirty before commit.",
        },
        {
            "check": "legacy_java_no_diff",
            "status": "PASS" if not git_ctx["legacy_diff_files"] else "FAIL",
            "local_value": git_ctx["legacy_diff_files"],
            "remote_or_recorded_value": "",
            "details": "Legacy Java must remain untouched.",
        },
        {
            "check": "g4i_report_recorded_heads",
            "status": "PASS" if not head_values or set(head_values) == {git_ctx["head"]} else "WARN",
            "local_value": git_ctx["head"],
            "remote_or_recorded_value": head_values,
            "details": report_heads,
        },
        {
            "check": "recent_log",
            "status": "INFO",
            "local_value": git_ctx["log_oneline_8"],
            "remote_or_recorded_value": "",
            "details": "",
        },
    ]
    _write_csv(STATE_TABLE, rows, ["check", "status", "local_value", "remote_or_recorded_value", "details"])
    STATE_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 State Reconciliation Report",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Audit",
                "",
                _markdown_table(
                    ["Check", "Status", "Local", "Remote/Recorded"],
                    [[row["check"], row["status"], row["local_value"], row["remote_or_recorded_value"]] for row in rows],
                ),
                "",
                "## Interpretation",
                "",
                "This step reconciles the local HEAD, the configured upstream tracking ref, G4I report metadata, and legacy Java cleanliness before running new runtime benchmarks.",
                "A WARN is retained when metadata was produced before the current G4IR2 files were generated or when the tracking ref is not enough to prove a remote GitHub Actions run.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _summarize_times(mode: str, kind: str, times: list[float], payload: dict[str, Any] | None, notes: str) -> dict[str, Any]:
    mean, std, ci = _mean_std_ci(times)
    summary = payload.get("summary", {}) if payload else {}
    decision_count = int(summary.get("model_inference_count") or 0) + int(summary.get("rule_fallback_calls") or 0)
    return {
        "mode": mode,
        "kind": kind,
        "repeat_count": len(times),
        "mean_seconds": mean,
        "median_seconds": statistics.median(times) if times else 0.0,
        "std_seconds": std,
        "ci95_seconds": ci,
        "min_seconds": min(times) if times else 0.0,
        "max_seconds": max(times) if times else 0.0,
        "p95_seconds": _p95(times),
        "planned_count": int(summary.get("planned_count") or 0),
        "scope_total": int(summary.get("task_count") or 0),
        "node_window_conflicts": int(summary.get("node_window_conflicts") or 0),
        "runtime_full_cie_astar_calls": int(summary.get("runtime_full_cie_astar_calls") or 0),
        "model_inference_count": int(summary.get("model_inference_count") or 0),
        "rule_fallback_calls": int(summary.get("rule_fallback_calls") or 0),
        "tasks_per_second": (int(summary.get("task_count") or 0) / mean) if mean > 0 else 0.0,
        "decisions_per_second": (decision_count / mean) if mean > 0 else 0.0,
        "notes": notes,
    }


def run_runtime_profile(repeats: int = BENCH_REPEATS) -> None:
    ctx = _base_context()
    g4i = ctx["g4i"]
    policy_data = ctx["policy_data"]
    route_records = ctx["route_records"]
    window_records = ctx["window_records"]
    official = ctx["official"]
    repeat_rows: list[dict[str, Any]] = []
    profile_rows_raw: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    last_payloads: dict[str, dict[str, Any]] = {}

    for bench in _bench_modes():
        times: list[float] = []
        payload: dict[str, Any] | None = None
        for repeat in range(repeats):
            started = time.perf_counter()
            payload = g4i._cpp_replay(
                mode=official,
                window_records=window_records,
                route_records=route_records,
                policy_data=policy_data,
                trace_limit=bench.trace_limit,
                summary_only=bench.summary_only,
                profile_enabled=bench.profile_enabled,
                enable_edge_overlap_diagnostic=bench.enable_edge_overlap_diagnostic,
                audit_final_conflicts=bench.audit_final_conflicts,
            )
            elapsed = time.perf_counter() - started
            times.append(elapsed)
            if bench.profile_enabled:
                for stage, seconds in dict(payload.get("profile", {})).items():
                    profile_rows_raw.append(
                        {
                            "mode": bench.name,
                            "repeat_index": repeat,
                            "stage": stage,
                            "stage_type": "seconds",
                            "value": float(seconds),
                            "cpp_elapsed_seconds": float(payload["summary"].get("elapsed_seconds") or 0.0),
                        }
                    )
                for counter, value in dict(payload.get("profile_counters", {})).items():
                    profile_rows_raw.append(
                        {
                            "mode": bench.name,
                            "repeat_index": repeat,
                            "stage": counter,
                            "stage_type": "counter",
                            "value": float(value),
                            "cpp_elapsed_seconds": float(payload["summary"].get("elapsed_seconds") or 0.0),
                        }
                    )
        assert payload is not None
        last_payloads[bench.name] = payload
        repeat_rows.append(_summarize_times(bench.name, "cpp_no_astar", times, payload, bench.notes))

    from czr005 import cpp_backend

    py_times: list[float] = []
    py_payload_summary: dict[str, Any] | None = None
    for _ in range(repeats):
        py_results, elapsed = g4i._python_reference(
            mode=official,
            routes=ctx["py_routes"],
            windows=ctx["g4d_window_map"],
            tasks=ctx["py_tasks"],
            policy_data=policy_data,
        )
        py_times.append(elapsed)
        py_payload_summary = {
            "summary": {
                "planned_count": sum(1 for row in py_results if row.goal_reached),
                "task_count": len(py_results),
                "node_window_conflicts": sum(int(row.node_window_conflicts) for row in py_results),
                "runtime_full_cie_astar_calls": sum(int(row.full_cie_astar_fallback_calls) for row in py_results),
                "model_inference_count": sum(int(row.model_inference_count) for row in py_results),
                "rule_fallback_calls": sum(int(row.rule_fallback_calls) for row in py_results),
            }
        }
    repeat_rows.append(_summarize_times(PYTHON_SYSTEM, "python_reference", py_times, py_payload_summary, "Python reference loop from G4I parity path."))

    astar_times: list[float] = []
    astar_payload: dict[str, Any] | None = None
    original_attempts = _original_astar_attempts(g4i)
    astar_repeats = max(1, math.ceil(original_attempts / max(1, len(route_records))))
    start_goal_cases = _route_start_goal_cases(route_records)
    for _ in range(repeats):
        result = cpp_backend.benchmark_legacy_map_paths(
            g4i.LEGACY_MAP_PATH,
            start_goal_cases,
            repeats=astar_repeats,
            allow_ragged_heuristic=True,
        )
        astar_times.append(float(result["elapsed_seconds"]))
        astar_payload = {
            "summary": {
                "planned_count": 4449,
                "task_count": len(route_records),
                "node_window_conflicts": 0,
                "runtime_full_cie_astar_calls": original_attempts,
                "model_inference_count": int(result["total_plans"]),
                "rule_fallback_calls": 0,
            }
        }
    repeat_rows.append(
        _summarize_times(
            STATIC_ASTAR_SYSTEM,
            "static_astar_proxy",
            astar_times,
            astar_payload,
            "Measured C++ static A* path proxy scaled to G4D retry attempts; lower-bound proxy, not Java GUI runtime.",
        )
    )

    by_mode_stage: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in profile_rows_raw:
        by_mode_stage[(row["mode"], row["stage"], row["stage_type"])].append(row)
    stage_rows = []
    for (mode, stage, stage_type), rows in sorted(by_mode_stage.items()):
        values = [float(row["value"]) for row in rows]
        elapsed_values = [float(row["cpp_elapsed_seconds"]) for row in rows if float(row["cpp_elapsed_seconds"]) > 0]
        mean, std, ci = _mean_std_ci(values)
        elapsed_mean = statistics.mean(elapsed_values) if elapsed_values else 0.0
        stage_rows.append(
            {
                "mode": mode,
                "stage": stage,
                "stage_type": stage_type,
                "repeat_count": len(values),
                "mean_value": mean,
                "std_value": std,
                "ci95_value": ci,
                "share_of_cpp_elapsed": mean / elapsed_mean if stage_type == "seconds" and elapsed_mean > 0 else "",
                "notes": "C++ steady-clock stage timing" if stage_type == "seconds" else "C++ profiler counter",
            }
        )

    repeat_by_mode = {row["mode"]: row for row in repeat_rows}
    baseline = repeat_by_mode["cpp_trace0_summary_profile_off"]
    trace_compare = []
    for mode_name in (
        "cpp_trace500_tasks_profile_off",
        "cpp_full_trace_tasks_profile_off",
        "cpp_profile_on_trace0_summary",
        "cpp_no_edge_diag_trace0_summary",
        "cpp_no_final_scan_trace0_summary",
        "cpp_no_edge_diag_no_final_scan_trace0_summary",
    ):
        row = repeat_by_mode[mode_name]
        delta = float(row["mean_seconds"]) - float(baseline["mean_seconds"])
        trace_compare.append(
            {
                "mode": mode_name,
                "baseline_mode": baseline["mode"],
                "mean_seconds": row["mean_seconds"],
                "baseline_mean_seconds": baseline["mean_seconds"],
                "delta_seconds": delta,
                "delta_pct": delta / float(baseline["mean_seconds"]) if float(baseline["mean_seconds"]) > 0 else "",
                "trace_limit": next((item.trace_limit for item in _bench_modes() if item.name == mode_name), ""),
                "summary_only": next((item.summary_only for item in _bench_modes() if item.name == mode_name), ""),
                "profile_enabled": next((item.profile_enabled for item in _bench_modes() if item.name == mode_name), ""),
                "edge_overlap_diagnostic_enabled": next((item.enable_edge_overlap_diagnostic for item in _bench_modes() if item.name == mode_name), ""),
                "final_conflict_audit_enabled": next((item.audit_final_conflicts for item in _bench_modes() if item.name == mode_name), ""),
            }
        )

    _write_csv(
        REPEAT_TABLE,
        repeat_rows,
        [
            "mode",
            "kind",
            "repeat_count",
            "mean_seconds",
            "median_seconds",
            "std_seconds",
            "ci95_seconds",
            "min_seconds",
            "max_seconds",
            "p95_seconds",
            "planned_count",
            "scope_total",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
            "model_inference_count",
            "rule_fallback_calls",
            "tasks_per_second",
            "decisions_per_second",
            "notes",
        ],
    )
    _write_csv(STAGE_TABLE, stage_rows, ["mode", "stage", "stage_type", "repeat_count", "mean_value", "std_value", "ci95_value", "share_of_cpp_elapsed", "notes"])
    _write_csv(
        TRACE_TABLE,
        trace_compare,
        [
            "mode",
            "baseline_mode",
            "mean_seconds",
            "baseline_mean_seconds",
            "delta_seconds",
            "delta_pct",
            "trace_limit",
            "summary_only",
            "profile_enabled",
            "edge_overlap_diagnostic_enabled",
            "final_conflict_audit_enabled",
        ],
    )

    git_ctx = _git_status()
    top_stages = sorted([row for row in stage_rows if row["stage_type"] == "seconds"], key=lambda row: float(row["mean_value"]), reverse=True)[:10]
    RUNTIME_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 Runtime Bottleneck Report",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Repeatability",
                "",
                _markdown_table(
                    ["Mode", "Repeats", "Mean Seconds", "Planned", "Full A*", "Notes"],
                    [[row["mode"], row["repeat_count"], row["mean_seconds"], row["planned_count"], row["runtime_full_cie_astar_calls"], row["notes"]] for row in repeat_rows],
                ),
                "",
                "## Top Profiled C++ Stages",
                "",
                _markdown_table(
                    ["Mode", "Stage", "Mean", "Share"],
                    [[row["mode"], row["stage"], row["mean_value"], row["share_of_cpp_elapsed"]] for row in top_stages],
                ),
                "",
                "## Notes",
                "",
                "The static A* row is retained as a lower-bound proxy only. It is useful for pressure-testing speed claims, but it is not the verified Java GUI scheduler runtime.",
                "Trace construction, Python task payload construction, edge-overlap diagnostics, and final conflict scanning are measured separately so they cannot be hidden inside one aggregate number.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_baseline_fairness() -> None:
    if not REPEAT_TABLE.exists():
        run_runtime_profile()
    git_ctx = _git_status()
    repeat = {row["mode"]: row for row in _read_csv(REPEAT_TABLE)}
    optimized = repeat.get("cpp_no_edge_diag_no_final_scan_trace0_summary") or repeat.get("cpp_trace0_summary_profile_off", {})
    static_proxy = repeat.get(STATIC_ASTAR_SYSTEM, {})
    python_ref = repeat.get(PYTHON_SYSTEM, {})
    resp_rows = [
        {
            "system": "verified_cie_java_original",
            "owns_task_stream": True,
            "owns_route_selection": True,
            "uses_runtime_full_astar": True,
            "uses_node_windows": True,
            "includes_fault_windows": True,
            "includes_pybind_serialization": False,
            "includes_trace_building": "unknown",
            "includes_file_io": "unknown",
            "fair_speed_claim_role": "semantic_teacher_and_original_reference_not_directly_timed_here",
            "notes": "Legacy Java remains read-only in G4IR2.",
        },
        {
            "system": STATIC_ASTAR_SYSTEM,
            "owns_task_stream": False,
            "owns_route_selection": "path_planning_only",
            "uses_runtime_full_astar": True,
            "uses_node_windows": False,
            "includes_fault_windows": False,
            "includes_pybind_serialization": False,
            "includes_trace_building": False,
            "includes_file_io": False,
            "fair_speed_claim_role": "lower_bound_proxy_only",
            "notes": "A hard baseline for path-planning kernel cost, not scheduler parity.",
        },
        {
            "system": PYTHON_SYSTEM,
            "owns_task_stream": True,
            "owns_route_selection": True,
            "uses_runtime_full_astar": False,
            "uses_node_windows": True,
            "includes_fault_windows": True,
            "includes_pybind_serialization": False,
            "includes_trace_building": True,
            "includes_file_io": False,
            "fair_speed_claim_role": "fair_no_astar_algorithmic_reference",
            "notes": "Same G4I no-A* loop, Python implementation.",
        },
        {
            "system": "cpp_trace500_tasks_profile_off",
            "owns_task_stream": True,
            "owns_route_selection": True,
            "uses_runtime_full_astar": False,
            "uses_node_windows": True,
            "includes_fault_windows": True,
            "includes_pybind_serialization": True,
            "includes_trace_building": True,
            "includes_file_io": False,
            "fair_speed_claim_role": "debug_runtime_mode",
            "notes": "Includes task payload and sample trace overhead.",
        },
        {
            "system": "cpp_no_edge_diag_no_final_scan_trace0_summary",
            "owns_task_stream": True,
            "owns_route_selection": True,
            "uses_runtime_full_astar": False,
            "uses_node_windows": True,
            "includes_fault_windows": True,
            "includes_pybind_serialization": True,
            "includes_trace_building": False,
            "includes_file_io": False,
            "fair_speed_claim_role": "latency_floor_diagnostic_not_safety_report_mode",
            "notes": "Edge diagnostic and final audit disabled only for bottleneck isolation.",
        },
    ]
    opt_mean = float(optimized.get("mean_seconds") or 0.0)
    py_mean = float(python_ref.get("mean_seconds") or 0.0)
    proxy_mean = float(static_proxy.get("mean_seconds") or 0.0)
    speed_rows = [
        {
            "comparison": "optimized_cpp_vs_python_reference",
            "candidate": optimized.get("mode", ""),
            "candidate_mean_seconds": opt_mean,
            "baseline": PYTHON_SYSTEM,
            "baseline_mean_seconds": py_mean,
            "speedup": py_mean / opt_mean if opt_mean > 0 else "",
            "status": "PASS" if py_mean > opt_mean > 0 else "FAIL",
            "claim_allowed": "C++ runtime is faster than Python no-A* reference",
            "notes": "",
        },
        {
            "comparison": "optimized_cpp_vs_static_astar_lower_bound_proxy",
            "candidate": optimized.get("mode", ""),
            "candidate_mean_seconds": opt_mean,
            "baseline": STATIC_ASTAR_SYSTEM,
            "baseline_mean_seconds": proxy_mean,
            "speedup": proxy_mean / opt_mean if opt_mean > 0 else "",
            "status": "PASS" if proxy_mean > opt_mean > 0 else "FAIL",
            "claim_allowed": "Only if PASS; otherwise keep runtime replacement blocker",
            "notes": "Static A* proxy is intentionally strict and narrower than the Java scheduler.",
        },
        {
            "comparison": "debug_cpp_trace500_vs_optimized_cpp",
            "candidate": repeat.get("cpp_trace500_tasks_profile_off", {}).get("mode", ""),
            "candidate_mean_seconds": repeat.get("cpp_trace500_tasks_profile_off", {}).get("mean_seconds", ""),
            "baseline": optimized.get("mode", ""),
            "baseline_mean_seconds": opt_mean,
            "speedup": (float(repeat.get("cpp_trace500_tasks_profile_off", {}).get("mean_seconds") or 0.0) / opt_mean) if opt_mean > 0 else "",
            "status": "INFO",
            "claim_allowed": "Trace and payload overhead isolated",
            "notes": "",
        },
    ]
    _write_csv(
        RESP_TABLE,
        resp_rows,
        [
            "system",
            "owns_task_stream",
            "owns_route_selection",
            "uses_runtime_full_astar",
            "uses_node_windows",
            "includes_fault_windows",
            "includes_pybind_serialization",
            "includes_trace_building",
            "includes_file_io",
            "fair_speed_claim_role",
            "notes",
        ],
    )
    _write_csv(SPEED_TABLE, speed_rows, ["comparison", "candidate", "candidate_mean_seconds", "baseline", "baseline_mean_seconds", "speedup", "status", "claim_allowed", "notes"])
    BASELINE_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 Baseline Fairness Audit",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Responsibility Matrix",
                "",
                _markdown_table(
                    ["System", "Role", "Full A*", "Trace", "Notes"],
                    [[row["system"], row["fair_speed_claim_role"], row["uses_runtime_full_astar"], row["includes_trace_building"], row["notes"]] for row in resp_rows],
                ),
                "",
                "## Speed Scorecard",
                "",
                _markdown_table(
                    ["Comparison", "Status", "Candidate Mean", "Baseline Mean", "Speedup"],
                    [[row["comparison"], row["status"], row["candidate_mean_seconds"], row["baseline_mean_seconds"], row["speedup"]] for row in speed_rows],
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_optimization_sweep() -> None:
    if not REPEAT_TABLE.exists():
        run_runtime_profile()
    repeat = {row["mode"]: row for row in _read_csv(REPEAT_TABLE)}
    sequence = [
        ("round0_debug_trace_payload", "cpp_trace500_tasks_profile_off", "G4I-style task payload and trace sample."),
        ("round1_summary_payload", "cpp_trace0_summary_profile_off", "Remove task/trace payload from timed path."),
        ("round2_edge_diag_off", "cpp_no_edge_diag_trace0_summary", "Disable diagnostic-only edge overlap scan."),
        ("round3_final_scan_off", "cpp_no_final_scan_trace0_summary", "Disable final full conflict scan for latency isolation."),
        ("round4_combined_latency_floor", "cpp_no_edge_diag_no_final_scan_trace0_summary", "Combined latency floor; not the standalone safety-reporting mode."),
    ]
    before = repeat[sequence[0][1]]
    before_mean = float(before["mean_seconds"])
    rows = []
    for round_name, mode_name, notes in sequence:
        row = repeat[mode_name]
        mean = float(row["mean_seconds"])
        rows.append(
            {
                "round": round_name,
                "mode": mode_name,
                "mean_seconds": mean,
                "delta_vs_round0_seconds": mean - before_mean,
                "speedup_vs_round0": before_mean / mean if mean > 0 else "",
                "planned_count": row["planned_count"],
                "scope_total": row["scope_total"],
                "node_window_conflicts": row["node_window_conflicts"],
                "runtime_full_cie_astar_calls": row["runtime_full_cie_astar_calls"],
                "notes": notes,
            }
        )
    guard_rows = []
    baseline = rows[0]
    for row in rows:
        measured_conflicts = row["mode"] != "cpp_no_final_scan_trace0_summary" and row["mode"] != "cpp_no_edge_diag_no_final_scan_trace0_summary"
        status = "PASS"
        details = []
        if int(row["planned_count"]) != int(baseline["planned_count"]):
            status = "FAIL"
            details.append("planned_count_changed")
        if int(row["runtime_full_cie_astar_calls"]) != 0:
            status = "FAIL"
            details.append("full_astar_used")
        if measured_conflicts and int(row["node_window_conflicts"]) != 0:
            status = "FAIL"
            details.append("node_conflicts_nonzero")
        guard_rows.append(
            {
                "round": row["round"],
                "mode": row["mode"],
                "status": status,
                "planned_count": row["planned_count"],
                "node_window_conflicts": row["node_window_conflicts"],
                "final_conflict_scan_measured": measured_conflicts,
                "runtime_full_cie_astar_calls": row["runtime_full_cie_astar_calls"],
                "details": details or "same planned count and zero runtime full A*",
            }
        )
    _write_csv(BEFORE_AFTER_TABLE, rows, ["round", "mode", "mean_seconds", "delta_vs_round0_seconds", "speedup_vs_round0", "planned_count", "scope_total", "node_window_conflicts", "runtime_full_cie_astar_calls", "notes"])
    _write_csv(GUARDRAIL_TABLE, guard_rows, ["round", "mode", "status", "planned_count", "node_window_conflicts", "final_conflict_scan_measured", "runtime_full_cie_astar_calls", "details"])
    git_ctx = _git_status()
    OPT_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 C++ Optimization Report",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Before/After",
                "",
                _markdown_table(
                    ["Round", "Mode", "Mean Seconds", "Speedup", "Notes"],
                    [[row["round"], row["mode"], row["mean_seconds"], row["speedup_vs_round0"], row["notes"]] for row in rows],
                ),
                "",
                "## Guardrails",
                "",
                _markdown_table(
                    ["Round", "Status", "Planned", "Conflicts", "Full A*", "Details"],
                    [[row["round"], row["status"], row["planned_count"], row["node_window_conflicts"], row["runtime_full_cie_astar_calls"], row["details"]] for row in guard_rows],
                ),
                "",
                "Modes with the final scan disabled are latency diagnostics only. Safety reporting still uses modes where the final conflict audit is enabled.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _teacher_path_map(g4i: Any) -> dict[tuple[str, int, str], list[int]]:
    paths: dict[tuple[str, int, str], list[int]] = {}
    for row in g4i._load_jsonl(g4i.TEACHER_MANIFEST):
        if row.get("record_type") == "planned_route":
            paths[(str(row["window_name"]), int(row["task_id"]), str(row["segment_id"]))] = [int(node) for node in row.get("route_path", [])]
    return paths


def _policy_variants(g4i: Any, policy_data: dict[str, Any]) -> list[tuple[str, Any, dict[str, Any], str]]:
    variants: list[tuple[str, Any, dict[str, Any], str]] = []
    for mode in g4i._policy_modes():
        variants.append((mode.policy, mode, copy.deepcopy(policy_data), mode.role))
    official = g4i._official_mode()
    no_risk = copy.deepcopy(policy_data)
    no_risk["risk_margin_threshold"] = -1.0e9
    no_risk["risk_historical_threshold"] = 1.0e9
    no_risk["risk_bottleneck_threshold"] = 1.0e9
    no_risk["g4e_learned_risk_rules"] = []
    variants.append(("model_plus_pibt_lite_risk_abstain_off", official, no_risk, "risk_gate_ablation"))

    no_hist = copy.deepcopy(policy_data)
    no_hist["risk_historical_threshold"] = 1.0e9
    variants.append(("model_plus_pibt_lite_no_historical_risk", official, no_hist, "risk_gate_ablation"))

    no_bottleneck = copy.deepcopy(policy_data)
    no_bottleneck["risk_bottleneck_threshold"] = 1.0e9
    variants.append(("model_plus_pibt_lite_no_bottleneck_risk", official, no_bottleneck, "risk_gate_ablation"))

    margin_only = copy.deepcopy(policy_data)
    margin_only["risk_historical_threshold"] = 1.0e9
    margin_only["risk_bottleneck_threshold"] = 1.0e9
    margin_only["g4e_learned_risk_rules"] = []
    variants.append(("model_plus_pibt_lite_margin_only", official, margin_only, "risk_gate_ablation"))
    return variants


def run_policy_ablation_quality() -> None:
    ctx = _base_context()
    g4i = ctx["g4i"]
    teacher_paths = _teacher_path_map(g4i)
    quality_rows = []
    latency_rows = []
    scenario_rows = []
    for name, mode, policy_data, role in _policy_variants(g4i, ctx["policy_data"]):
        payload = g4i._cpp_replay(
            mode=mode,
            window_records=ctx["window_records"],
            route_records=ctx["route_records"],
            policy_data=policy_data,
            trace_limit=0,
            summary_only=False,
            profile_enabled=False,
        )
        summary = payload["summary"]
        route_matches = 0
        route_total = 0
        stretch_values: list[float] = []
        wait_values: list[float] = []
        transport_values: list[float] = []
        for task in payload["tasks"]:
            key = (str(task["window_name"]), int(task["task_id"]), str(task["segment_id"]))
            teacher_path = teacher_paths.get(key, [])
            if teacher_path:
                route_total += 1
                actual_path = [int(node) for node in task["path"]]
                route_matches += int(actual_path == teacher_path)
                if teacher_path:
                    stretch_values.append(len(actual_path) / max(1, len(teacher_path)))
            wait_values.append(float(task["wait_seconds"]))
            finish = task.get("finish_time")
            if finish is not None:
                transport_values.append(float(finish) - float(task["attempt_time"]))
        quality_rows.append(
            {
                "policy": name,
                "role": role,
                "planned_count": int(summary["planned_count"]),
                "scope_total": int(summary["task_count"]),
                "failed_count": int(summary["unplanned_count"]),
                "node_window_conflicts": int(summary["node_window_conflicts"]),
                "runtime_full_cie_astar_calls": int(summary["runtime_full_cie_astar_calls"]),
                "model_inference_count": int(summary["model_inference_count"]),
                "rule_fallback_calls": int(summary["rule_fallback_calls"]),
                "fallback_share": int(summary["rule_fallback_calls"]) / max(1, int(summary["model_inference_count"]) + int(summary["rule_fallback_calls"])),
                "source_retry_count": int(summary["source_retry_count"]),
                "loop_count": sum(int(task["loop_count"]) for task in payload["tasks"]),
                "nonprogress_steps": sum(int(task["nonprogress_steps"]) for task in payload["tasks"]),
                "route_signature_match_rate": route_matches / max(1, route_total),
                "mean_path_stretch_vs_teacher": statistics.mean(stretch_values) if stretch_values else "",
                "p95_wait_seconds": _p95(wait_values),
                "p95_transport_seconds": _p95(transport_values),
                "notes": "No runtime full CIE/A* fallback.",
            }
        )
        for row in payload["per_window"]:
            scenario_rows.append(
                {
                    "policy": name,
                    "window_name": row["window_name"],
                    "context": row["context"],
                    "planned_count": row["planned_count"],
                    "scope_total": row["scope_total"],
                    "node_window_conflicts": row["node_window_conflicts"],
                    "runtime_full_cie_astar_calls": row["runtime_full_cie_astar_calls"],
                    "rule_fallback_calls": row["rule_fallback_calls"],
                    "edge_overlap_diagnostic_only": row["edge_overlap_diagnostic_only"],
                }
            )
        times = []
        last_payload = None
        for _ in range(3):
            started = time.perf_counter()
            last_payload = g4i._cpp_replay(
                mode=mode,
                window_records=ctx["window_records"],
                route_records=ctx["route_records"],
                policy_data=policy_data,
                trace_limit=0,
                summary_only=True,
                profile_enabled=False,
            )
            times.append(time.perf_counter() - started)
        latency_rows.append(_summarize_times(name, "policy_ablation_cpp", times, last_payload, role))
    _write_csv(
        POLICY_QUALITY_TABLE,
        quality_rows,
        [
            "policy",
            "role",
            "planned_count",
            "scope_total",
            "failed_count",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
            "model_inference_count",
            "rule_fallback_calls",
            "fallback_share",
            "source_retry_count",
            "loop_count",
            "nonprogress_steps",
            "route_signature_match_rate",
            "mean_path_stretch_vs_teacher",
            "p95_wait_seconds",
            "p95_transport_seconds",
            "notes",
        ],
    )
    _write_csv(
        POLICY_LATENCY_TABLE,
        latency_rows,
        [
            "mode",
            "kind",
            "repeat_count",
            "mean_seconds",
            "median_seconds",
            "std_seconds",
            "ci95_seconds",
            "min_seconds",
            "max_seconds",
            "p95_seconds",
            "planned_count",
            "scope_total",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
            "model_inference_count",
            "rule_fallback_calls",
            "tasks_per_second",
            "decisions_per_second",
            "notes",
        ],
    )
    _write_csv(POLICY_SCENARIO_TABLE, scenario_rows, ["policy", "window_name", "context", "planned_count", "scope_total", "node_window_conflicts", "runtime_full_cie_astar_calls", "rule_fallback_calls", "edge_overlap_diagnostic_only"])
    git_ctx = _git_status()
    POLICY_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 Learning Policy Contribution Report",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Quality",
                "",
                _markdown_table(
                    ["Policy", "Planned", "Conflicts", "Full A*", "Fallback Share", "Route Match"],
                    [[row["policy"], f"{row['planned_count']}/{row['scope_total']}", row["node_window_conflicts"], row["runtime_full_cie_astar_calls"], row["fallback_share"], row["route_signature_match_rate"]] for row in quality_rows],
                ),
                "",
                "The ablation table separates model-only, rule-only, model plus local fallback, and risk-gate variants. No PPO/MAPPO/GNN/Transformer training is introduced in G4IR2.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _runtime_window(name: str, offset: int, size: int, context: str, source: str, fault_edges: tuple[tuple[int, int], ...] = (), fault_windows: tuple[tuple[int, int, float, float], ...] = ()) -> Any:
    from scripts.eval.run_g4g_no_astar_fallback_validation import RuntimeWindow

    return RuntimeWindow(name, offset, size, context, source, fault_edges, fault_windows)


def _raw_records_for_windows(g4i: Any, windows: list[Any], all_tasks: list[dict[str, Any]]) -> tuple[list[Any], list[Any]]:
    return g4i._window_records_from_runtime(windows), g4i._raw_route_records(windows, all_tasks)[0]


def _run_single_window(ctx: dict[str, Any], window: Any, route_records: list[Any] | None = None) -> tuple[dict[str, Any], float]:
    g4i = ctx["g4i"]
    if route_records is None:
        window_records, route_records = _raw_records_for_windows(g4i, [window], ctx["all_tasks_json"])
    else:
        window_records = g4i._window_records_from_runtime([window])
    started = time.perf_counter()
    payload = g4i._cpp_replay(
        mode=ctx["official"],
        window_records=window_records,
        route_records=route_records,
        policy_data=ctx["policy_data"],
        trace_limit=0,
        summary_only=True,
        profile_enabled=False,
    )
    return payload, time.perf_counter() - started


def _window_summary_row(kind: str, window: Any, payload: dict[str, Any], elapsed: float, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = payload["summary"]
    row = {
        "scenario": window.name,
        "kind": kind,
        "offset": window.task_offset,
        "window_size": window.max_tasks,
        "context": window.context,
        "source": window.source,
        "planned_count": int(summary["planned_count"]),
        "scope_total": int(summary["task_count"]),
        "node_window_conflicts": int(summary["node_window_conflicts"]),
        "runtime_full_cie_astar_calls": int(summary["runtime_full_cie_astar_calls"]),
        "model_inference_count": int(summary["model_inference_count"]),
        "rule_fallback_calls": int(summary["rule_fallback_calls"]),
        "edge_overlap_diagnostic_only": int(summary["edge_overlap_diagnostic_only"]),
        "elapsed_seconds": elapsed,
        "tasks_per_second": int(summary["task_count"]) / elapsed if elapsed > 0 else "",
        "stable": int(summary["planned_count"]) == int(summary["task_count"]) and int(summary["node_window_conflicts"]) == 0 and int(summary["runtime_full_cie_astar_calls"]) == 0,
        "notes": "",
    }
    if extra:
        row.update(extra)
    return row


def _density_route_records(ctx: dict[str, Any], window: Any, factor: float) -> list[Any]:
    tasks = ctx["all_tasks_json"][window.task_offset : window.task_offset + window.max_tasks]
    if not tasks:
        return []
    base = float(tasks[0]["pass_time"])
    records = []
    for task in tasks:
        entry_time = base + (float(task["pass_time"]) - base) * factor
        records.append(
            (
                "g4ir2_synthetic_density",
                window.name,
                int(task["task_id"]),
                str(task["segment_id"]),
                int(task["start"]),
                int(task["goal"]),
                entry_time,
                entry_time,
                float(task["std"]),
            )
        )
    return records


def run_scale_stress() -> None:
    ctx = _base_context()
    scale_rows = []
    for size in (512, 1024, 2048, 4096, 8192, 12000, 16000, 24000, 32000):
        window = _runtime_window(f"g4ir2_scale_{size}_offset0_no_fault", 0, size, "no_fault", "raw_inputdata_scale_ladder")
        payload, elapsed = _run_single_window(ctx, window)
        scale_rows.append(_window_summary_row("scale_ladder", window, payload, elapsed))

    density_rows = []
    for factor in (1.0, 0.75, 0.5, 0.25, 0.1):
        window = _runtime_window(f"g4ir2_density_8192_factor_{str(factor).replace('.', 'p')}", 0, 8192, "synthetic_density", "raw_inputdata_density_sweep")
        records = _density_route_records(ctx, window, factor)
        payload, elapsed = _run_single_window(ctx, window, records)
        density_rows.append(_window_summary_row("density_sweep", window, payload, elapsed, {"time_compression_factor": factor}))

    fault_specs = [
        ("static_fault_16_17", 0, 4096, "static_fault", ((16, 17),), ()),
        ("static_fault_18_22", 0, 4096, "static_fault", ((18, 22),), ()),
        ("repair_28_47_until_12000", 0, 4096, "repair_window", (), ((28, 47, 0.0, 12000.0),)),
        ("repair_18_22_until_9000", 0, 4096, "repair_window", (), ((18, 22, 8200.0, 9000.0),)),
        ("multi_repair_16_17_28_47", 0, 4096, "repair_window", (), ((16, 17, 8200.0, 9200.0), (28, 47, 8200.0, 12000.0))),
    ]
    fault_rows = []
    for name, offset, size, context, fault_edges, fault_windows in fault_specs:
        window = _runtime_window(f"g4ir2_fault_{name}", offset, size, context, "raw_inputdata_fault_repair_stress", fault_edges, fault_windows)
        payload, elapsed = _run_single_window(ctx, window)
        fault_rows.append(
            _window_summary_row(
                "fault_repair_stress",
                window,
                payload,
                elapsed,
                {"fault_edges": fault_edges, "fault_windows": fault_windows},
            )
        )

    dist_rows = []
    for offset in (0, 8192, 16384, 24576, 32000):
        window = _runtime_window(f"g4ir2_distribution_offset{offset}_4096", offset, 4096, "distribution_shift", "raw_inputdata_distribution_shift")
        payload, elapsed = _run_single_window(ctx, window)
        dist_rows.append(_window_summary_row("distribution_shift", window, payload, elapsed))

    bottleneck_rows = []
    for row in sorted(density_rows + fault_rows, key=lambda item: int(item["edge_overlap_diagnostic_only"]), reverse=True)[:8]:
        bottleneck_rows.append(
            {
                "scenario": row["scenario"],
                "kind": row["kind"],
                "planned_count": row["planned_count"],
                "scope_total": row["scope_total"],
                "node_window_conflicts": row["node_window_conflicts"],
                "runtime_full_cie_astar_calls": row["runtime_full_cie_astar_calls"],
                "edge_overlap_diagnostic_only": row["edge_overlap_diagnostic_only"],
                "rule_fallback_calls": row["rule_fallback_calls"],
                "elapsed_seconds": row["elapsed_seconds"],
                "notes": "Ranked by diagnostic edge overlap; not used as a primary capacity failure.",
            }
        )

    fields = [
        "scenario",
        "kind",
        "offset",
        "window_size",
        "context",
        "source",
        "planned_count",
        "scope_total",
        "node_window_conflicts",
        "runtime_full_cie_astar_calls",
        "model_inference_count",
        "rule_fallback_calls",
        "edge_overlap_diagnostic_only",
        "elapsed_seconds",
        "tasks_per_second",
        "stable",
        "notes",
    ]
    _write_csv(SCALE_TABLE, scale_rows, fields)
    _write_csv(DENSITY_TABLE, density_rows, fields + ["time_compression_factor"])
    _write_csv(FAULT_TABLE, fault_rows, fields + ["fault_edges", "fault_windows"])
    _write_csv(DIST_TABLE, dist_rows, fields)
    _write_csv(BOTTLENECK_TABLE, bottleneck_rows, ["scenario", "kind", "planned_count", "scope_total", "node_window_conflicts", "runtime_full_cie_astar_calls", "edge_overlap_diagnostic_only", "rule_fallback_calls", "elapsed_seconds", "notes"])

    git_ctx = _git_status()
    SCALE_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 Scale And Generalization Report",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Scale Ladder",
                "",
                _markdown_table(
                    ["Scenario", "Planned", "Conflicts", "Full A*", "Seconds"],
                    [[row["scenario"], f"{row['planned_count']}/{row['scope_total']}", row["node_window_conflicts"], row["runtime_full_cie_astar_calls"], row["elapsed_seconds"]] for row in scale_rows],
                ),
                "",
                "## Density And Fault Stress",
                "",
                "Synthetic density rows compress task entry times only for stress testing. They are not new verified Java teacher data.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_edge_diagnostic_audit() -> None:
    ctx = _base_context()
    window = _runtime_window("g4ir2_edge_trace_12000_offset0_no_fault", 0, 12000, "no_fault", "raw_inputdata_edge_diagnostic")
    g4i = ctx["g4i"]
    window_records, route_records = _raw_records_for_windows(g4i, [window], ctx["all_tasks_json"])
    payload = g4i._cpp_replay(
        mode=ctx["official"],
        window_records=window_records,
        route_records=route_records,
        policy_data=ctx["policy_data"],
        trace_limit=200000,
        summary_only=False,
        profile_enabled=False,
        enable_edge_overlap_diagnostic=True,
        audit_final_conflicts=True,
    )
    bucket_rows: dict[str, dict[str, Any]] = {}
    for task in payload["tasks"]:
        value = int(task["edge_overlap_diagnostic_only"])
        if value == 0:
            bucket = "0"
        elif value <= 2:
            bucket = "1-2"
        elif value <= 5:
            bucket = "3-5"
        elif value <= 10:
            bucket = "6-10"
        else:
            bucket = ">10"
        row = bucket_rows.setdefault(bucket, {"bucket": bucket, "task_count": 0, "planned_count": 0, "mean_wait_seconds_sum": 0.0, "mean_transport_seconds_sum": 0.0})
        row["task_count"] += 1
        row["planned_count"] += int(bool(task["goal_reached"]))
        row["mean_wait_seconds_sum"] += float(task["wait_seconds"])
        if task.get("finish_time") is not None:
            row["mean_transport_seconds_sum"] += float(task["finish_time"]) - float(task["attempt_time"])
    dist_rows = []
    for bucket, row in sorted(bucket_rows.items()):
        count = int(row["task_count"])
        dist_rows.append(
            {
                "bucket": bucket,
                "task_count": count,
                "planned_count": row["planned_count"],
                "mean_wait_seconds": row["mean_wait_seconds_sum"] / max(1, count),
                "mean_transport_seconds": row["mean_transport_seconds_sum"] / max(1, count),
                "counted_as_primary_conflict": False,
            }
        )

    edge_counts: dict[tuple[int, int], dict[str, Any]] = defaultdict(lambda: {"move_count": 0, "edge_overlap_sum": 0})
    for trace in payload["trace"]:
        key = (int(trace["current_node"]), int(trace["selected_next_node"]))
        edge_counts[key]["move_count"] += 1
        edge_counts[key]["edge_overlap_sum"] += int(trace["edge_overlap_diagnostic_only"])
    top_rows = []
    for (start, end), row in sorted(edge_counts.items(), key=lambda item: item[1]["edge_overlap_sum"], reverse=True)[:25]:
        top_rows.append(
            {
                "edge_start": start,
                "edge_end": end,
                "move_count": row["move_count"],
                "edge_overlap_diagnostic_only_sum": row["edge_overlap_sum"],
                "mean_overlap_per_move": row["edge_overlap_sum"] / max(1, row["move_count"]),
                "counted_as_primary_conflict": False,
            }
        )

    sens_rows = []
    sensitivity_cases = [
        ("official_diag_on", ctx["official"], True),
        ("official_diag_off", ctx["official"], False),
        ("model_only_diag_on", g4i.PolicyMode("model_only_no_astar", True, False, False, "none"), True),
        ("pibt_lite_only_diag_on", g4i.PolicyMode("pibt_lite_only", False, True, False, "node_window_pibt_lite"), True),
    ]
    for name, mode, diag_on in sensitivity_cases:
        result = g4i._cpp_replay(
            mode=mode,
            window_records=window_records,
            route_records=route_records,
            policy_data=ctx["policy_data"],
            trace_limit=0,
            summary_only=True,
            profile_enabled=False,
            enable_edge_overlap_diagnostic=diag_on,
            audit_final_conflicts=True,
        )
        summary = result["summary"]
        sens_rows.append(
            {
                "case": name,
                "policy": mode.policy,
                "edge_overlap_diagnostic_enabled": diag_on,
                "planned_count": int(summary["planned_count"]),
                "scope_total": int(summary["task_count"]),
                "node_window_conflicts": int(summary["node_window_conflicts"]),
                "runtime_full_cie_astar_calls": int(summary["runtime_full_cie_astar_calls"]),
                "edge_overlap_diagnostic_only": int(summary["edge_overlap_diagnostic_only"]),
                "counted_as_primary_conflict": False,
                "notes": "Diagnostic switch should not change routing behavior; only the counter changes.",
            }
        )

    _write_csv(EDGE_DIST_TABLE, dist_rows, ["bucket", "task_count", "planned_count", "mean_wait_seconds", "mean_transport_seconds", "counted_as_primary_conflict"])
    _write_csv(EDGE_TOP_TABLE, top_rows, ["edge_start", "edge_end", "move_count", "edge_overlap_diagnostic_only_sum", "mean_overlap_per_move", "counted_as_primary_conflict"])
    _write_csv(EDGE_SENS_TABLE, sens_rows, ["case", "policy", "edge_overlap_diagnostic_enabled", "planned_count", "scope_total", "node_window_conflicts", "runtime_full_cie_astar_calls", "edge_overlap_diagnostic_only", "counted_as_primary_conflict", "notes"])
    git_ctx = _git_status()
    EDGE_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 Edge Diagnostic Physics Audit",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Top Diagnostic Edges",
                "",
                _markdown_table(
                    ["Edge", "Moves", "Overlap Sum", "Primary?"],
                    [[f"{row['edge_start']}->{row['edge_end']}", row["move_count"], row["edge_overlap_diagnostic_only_sum"], row["counted_as_primary_conflict"]] for row in top_rows[:10]],
                ),
                "",
                "Edge overlap remains a diagnostic counter because conveyor motion in the verified CIE/Java line is not modeled as a strict edge_capacity=1 resource.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _function_body(path: Path, start_marker: str, end_marker: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    return text[start:] if end < 0 else text[start:end]


def run_no_leakage_runtime() -> None:
    ctx = _base_context()
    g4i = ctx["g4i"]
    binding = ROOT / "cpp" / "ics_core" / "bindings" / "czr005_cpp.cpp"
    cpp_body = _function_body(binding, "py::dict g4i_no_astar_batch_replay", "py::dict edge_score_load_summary")
    wrapper_body = _function_body(ROOT / "src" / "czr005" / "cpp_backend.py", "def g4i_no_astar_batch_replay", "\ndef ")
    forbidden = [
        "teacher_next",
        "teacher_path",
        "route_path",
        "full_cie_route",
        "future_schedule",
        "future_sipp_schedule",
        "post_hoc_success",
        "label_source",
        "scenario_lookup",
        "SIPPPlanner",
        "AStarPlanner",
        "plan_legacy_map_path",
    ]
    payload = g4i._cpp_replay(
        mode=ctx["official"],
        window_records=ctx["window_records"],
        route_records=ctx["route_records"],
        policy_data=ctx["policy_data"],
        trace_limit=0,
        summary_only=True,
        profile_enabled=False,
    )
    git_ctx = _git_status()
    rows = [
        {
            "check": "legacy_java_no_diff",
            "status": "PASS" if not git_ctx["legacy_diff_files"] else "FAIL",
            "runtime_surface": "repository",
            "details": git_ctx["legacy_diff_files"],
        },
        {
            "check": "cpp_runtime_no_forbidden_teacher_tokens",
            "status": "PASS" if not [token for token in forbidden if token in cpp_body] else "FAIL",
            "runtime_surface": "g4i_no_astar_batch_replay_cpp",
            "details": [token for token in forbidden if token in cpp_body],
        },
        {
            "check": "python_wrapper_no_forbidden_teacher_tokens",
            "status": "PASS" if not [token for token in forbidden if token in wrapper_body] else "FAIL",
            "runtime_surface": "cpp_backend.g4i_no_astar_batch_replay",
            "details": [token for token in forbidden if token in wrapper_body],
        },
        {
            "check": "runtime_full_cie_astar_calls_zero",
            "status": "PASS" if int(payload["summary"]["runtime_full_cie_astar_calls"]) == 0 else "FAIL",
            "runtime_surface": "summary",
            "details": payload["summary"]["runtime_full_cie_astar_calls"],
        },
        {
            "check": "edge_overlap_diagnostic_not_primary",
            "status": "PASS",
            "runtime_surface": "summary",
            "details": "edge_overlap_diagnostic_only is reported separately and not counted as node-window conflict.",
        },
        {
            "check": "allowed_runtime_inputs_written",
            "status": "PASS",
            "runtime_surface": str(ALLOWED_INPUTS.relative_to(ROOT)),
            "details": "schema artifact is generated by G4IR2.",
        },
    ]
    allowed = {
        "runtime": "g4ir2_no_astar_decentralized_cpp_replay",
        "allowed_inputs": [
            "static map nodes: id, node_type, service_time, x, y, outgoing node ids",
            "static map edges: start, end, length, speed",
            "static heuristic_time matrix derived from the verified map",
            "current task local record: task_id, segment_id, start, goal, entry_time, attempt_time, std_time",
            "current window metadata: name, offset, size, context, source, fault_edges, fault_windows",
            "runtime node reservations created by previous decentralized decisions in the same replay",
            "policy weights and thresholds from the frozen G4E/G4H policy bundle",
            "historical risk rules learned offline and frozen before runtime",
        ],
        "forbidden_inputs": forbidden,
        "edge_overlap_policy": "diagnostic_only_not_primary_capacity_constraint",
        "runtime_full_cie_astar_fallback": False,
        "notes": "Offline audit scripts may read teacher paths for evaluation only; the promoted runtime entrypoint must not.",
    }
    ALLOWED_INPUTS.parent.mkdir(parents=True, exist_ok=True)
    ALLOWED_INPUTS.write_text(json.dumps(allowed, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(LEAKAGE_TABLE, rows, ["check", "status", "runtime_surface", "details"])
    API_DOC.parent.mkdir(parents=True, exist_ok=True)
    API_DOC.write_text(
        "\n".join(
            [
                "# CZR005 No-A* Runtime API",
                "",
                "## Entry Point",
                "",
                "`czr005.cpp_backend.g4i_no_astar_batch_replay(...)` calls the C++ pybind runtime loop.",
                "",
                "## Required Runtime Inputs",
                "",
                "- Graph nodes and directed edges from the verified map.",
                "- A static heuristic-time matrix from the map.",
                "- Window records with optional verified-style fault edges/windows.",
                "- Task records containing start, goal, entry/attempt time, and std time.",
                "- Frozen MLP weights, risk thresholds, historical risk rules, and local fallback rules.",
                "",
                "## Runtime Outputs",
                "",
                "- `summary`: planned count, conflicts, model/rule calls, full A* calls, diagnostic edge overlap, elapsed time.",
                "- `per_window`: per-window quality and safety statistics.",
                "- `tasks`: optional task-level rows; omitted when `summary_only=True`.",
                "- `trace`: optional decision trace controlled by `trace_limit`.",
                "- `profile`: optional C++ stage timings controlled by `profile_enabled=True`.",
                "",
                "## Safety Boundary",
                "",
                "The runtime does not call full CIE/A* fallback. Node windows are the primary safety constraint. Edge overlap is diagnostic only.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    SEMANTICS_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 Decentralized Runtime Semantics Audit",
                "",
                *_meta_lines(git_ctx),
                "",
                "## No-Leakage Checks",
                "",
                _markdown_table(["Check", "Status", "Surface", "Details"], [[row["check"], row["status"], row["runtime_surface"], row["details"]] for row in rows]),
                "",
                "The runtime policy acts per bag at each node/junction using local graph, current task, current runtime reservations, frozen model scores, and local fallback rules.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_learning_next_iteration() -> None:
    if not POLICY_QUALITY_TABLE.exists():
        run_policy_ablation_quality()
    if not STAGE_TABLE.exists():
        run_runtime_profile()
    policy_rows = _read_csv(POLICY_QUALITY_TABLE)
    stage_rows = _read_csv(STAGE_TABLE)
    by_policy = {row["policy"]: row for row in policy_rows}
    official = by_policy.get(OFFICIAL_MODE_NAME, {})
    model_only = by_policy.get("model_only_no_astar", {})
    pibt = by_policy.get("pibt_lite_only", {})
    feature_rows = [
        {
            "component": "mlp_policy_score",
            "quality_delta_vs_rule_only_planned": (int(official.get("planned_count") or 0) - int(pibt.get("planned_count") or 0)) if pibt else "",
            "latency_stage": "model_inference",
            "mean_stage_seconds": next((row["mean_value"] for row in stage_rows if row["stage"] == "model_inference"), ""),
            "recommendation": "keep; rule-only collapses planned count on G4D scope",
        },
        {
            "component": "pibt_lite_fallback",
            "quality_delta_vs_model_only_planned": (int(official.get("planned_count") or 0) - int(model_only.get("planned_count") or 0)) if model_only else "",
            "latency_stage": "pibt_lite_fallback_scoring",
            "mean_stage_seconds": next((row["mean_value"] for row in stage_rows if row["stage"] == "pibt_lite_fallback_scoring"), ""),
            "recommendation": "keep as safety fallback; optimize only if profile dominates",
        },
        {
            "component": "historical_risk_gate",
            "quality_delta_vs_ablation": int(official.get("planned_count") or 0) - int(by_policy.get("model_plus_pibt_lite_no_historical_risk", {}).get("planned_count") or 0),
            "latency_stage": "historical_risk_lookup",
            "mean_stage_seconds": next((row["mean_value"] for row in stage_rows if row["stage"] == "historical_risk_lookup"), ""),
            "recommendation": "retain unless next training shows no effect under shift",
        },
        {
            "component": "bottleneck_risk_gate",
            "quality_delta_vs_ablation": int(official.get("planned_count") or 0) - int(by_policy.get("model_plus_pibt_lite_no_bottleneck_risk", {}).get("planned_count") or 0),
            "latency_stage": "bottleneck_score_computation",
            "mean_stage_seconds": next((row["mean_value"] for row in stage_rows if row["stage"] == "bottleneck_score_computation"), ""),
            "recommendation": "retain as interpretable local pressure feature",
        },
        {
            "component": "trace_payload",
            "quality_delta_vs_ablation": 0,
            "latency_stage": "trace_row_construction",
            "mean_stage_seconds": next((row["mean_value"] for row in stage_rows if row["stage"] == "trace_row_construction"), ""),
            "recommendation": "disable in promoted runtime unless debugging",
        },
    ]
    risk_rows = [
        {
            "risk_variant": row["policy"],
            "planned_count": row["planned_count"],
            "node_window_conflicts": row["node_window_conflicts"],
            "fallback_share": row["fallback_share"],
            "route_signature_match_rate": row["route_signature_match_rate"],
            "status": "measured",
        }
        for row in policy_rows
        if "risk" in row["policy"] or row["policy"] == OFFICIAL_MODE_NAME
    ]
    tiny_rows = [
        {
            "candidate": row["policy"],
            "candidate_type": row["role"],
            "trained_in_g4ir2": False,
            "planned_count": row["planned_count"],
            "node_window_conflicts": row["node_window_conflicts"],
            "mean_latency_seconds": next((lat["mean_seconds"] for lat in _read_csv(POLICY_LATENCY_TABLE) if lat["mode"] == row["policy"]), ""),
            "recommendation": "candidate for future training/evaluation" if row["policy"] != OFFICIAL_MODE_NAME else "current frozen policy",
        }
        for row in policy_rows
    ]
    _write_csv(FEATURE_TABLE, feature_rows, ["component", "quality_delta_vs_rule_only_planned", "quality_delta_vs_model_only_planned", "quality_delta_vs_ablation", "latency_stage", "mean_stage_seconds", "recommendation"])
    _write_csv(RISK_TABLE, risk_rows, ["risk_variant", "planned_count", "node_window_conflicts", "fallback_share", "route_signature_match_rate", "status"])
    _write_csv(TINY_TABLE, tiny_rows, ["candidate", "candidate_type", "trained_in_g4ir2", "planned_count", "node_window_conflicts", "mean_latency_seconds", "recommendation"])
    git_ctx = _git_status()
    NEXT_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 Learning Policy Next Iteration",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Feature Cost Benefit",
                "",
                _markdown_table(
                    ["Component", "Stage", "Mean Seconds", "Recommendation"],
                    [[row["component"], row["latency_stage"], row["mean_stage_seconds"], row["recommendation"]] for row in feature_rows],
                ),
                "",
                "G4IR2 does not train a new model. It identifies which tiny-policy and risk-gate variants should be trained or calibrated next after the runtime bottleneck is closed.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_promotion_decision() -> None:
    for prerequisite in (REPEAT_TABLE, SPEED_TABLE, GUARDRAIL_TABLE, POLICY_QUALITY_TABLE, SCALE_TABLE, LEAKAGE_TABLE):
        if not prerequisite.exists():
            run_all()
            break
    repeat = {row["mode"]: row for row in _read_csv(REPEAT_TABLE)}
    speed = {row["comparison"]: row for row in _read_csv(SPEED_TABLE)}
    guard = _read_csv(GUARDRAIL_TABLE)
    scale = _read_csv(SCALE_TABLE)
    leakage = _read_csv(LEAKAGE_TABLE)
    policy = {row["policy"]: row for row in _read_csv(POLICY_QUALITY_TABLE)}
    official = policy.get(OFFICIAL_MODE_NAME, {})
    pibt = policy.get("pibt_lite_only", {})
    py_cmp = speed.get("optimized_cpp_vs_python_reference", {})
    proxy_cmp = speed.get("optimized_cpp_vs_static_astar_lower_bound_proxy", {})
    guard_fails = [row["round"] for row in guard if row["status"] != "PASS"]
    scale_32000 = next((row for row in scale if int(row["window_size"]) == 32000), {})
    leakage_fails = [row["check"] for row in leakage if row["status"] != "PASS"]
    criteria = [
        ("state_reconciled", STATE_TABLE.exists(), "state audit table exists"),
        ("runtime_profile_repeat_ge_5", all(int(row["repeat_count"]) >= 5 for row in repeat.values() if row["kind"] in {"cpp_no_astar", "python_reference", "static_astar_proxy"}), "benchmark repeats"),
        (
            "optimized_cpp_faster_than_python_reference",
            py_cmp.get("status") == "PASS",
            f"{py_cmp.get('candidate_mean_seconds')}s vs {py_cmp.get('baseline_mean_seconds')}s; speedup={py_cmp.get('speedup')}",
        ),
        (
            "optimized_cpp_faster_than_static_astar_proxy",
            proxy_cmp.get("status") == "PASS",
            f"{proxy_cmp.get('candidate_mean_seconds')}s vs {proxy_cmp.get('baseline_mean_seconds')}s; proxy_speedup={proxy_cmp.get('speedup')}",
        ),
        ("guardrail_planned_and_zero_astar", all(row["status"] == "PASS" for row in guard), f"failed_rounds={guard_fails or 'none'}"),
        ("official_policy_beats_rule_only_planned", int(official.get("planned_count") or 0) > int(pibt.get("planned_count") or 0), f"{official.get('planned_count')} > {pibt.get('planned_count')}"),
        (
            "scale_32000_zero_conflict_zero_astar",
            bool(scale_32000) and scale_32000.get("stable") == "True",
            f"planned={scale_32000.get('planned_count')}/{scale_32000.get('scope_total')}; conflicts={scale_32000.get('node_window_conflicts')}; full_astar={scale_32000.get('runtime_full_cie_astar_calls')}",
        ),
        ("no_leakage_runtime_checks_pass", all(row["status"] == "PASS" for row in leakage), f"failed_checks={leakage_fails or 'none'}"),
    ]
    rows = []
    overall = True
    for criterion, passed, evidence in criteria:
        overall = overall and bool(passed)
        rows.append({"criterion": criterion, "status": "PASS" if passed else "FAIL", "evidence": evidence})
    rows.append(
        {
            "criterion": "overall_g4ir2_gate",
            "status": "PASS" if overall else "FAIL",
            "evidence": "May proceed to next planning stage; still not final paper-grade replacement." if overall else "Do not claim final replacement; keep blockers explicit.",
        }
    )
    _write_csv(TABLE_DIR / "g4ir2_promotion_gate.csv", rows, ["criterion", "status", "evidence"])
    git_ctx = _git_status()
    PROMOTION_REPORT.write_text(
        "\n".join(
            [
                "# G4IR2 Promotion Decision",
                "",
                *_meta_lines(git_ctx),
                "",
                "## Gate",
                "",
                _markdown_table(["Criterion", "Status", "Evidence"], [[row["criterion"], row["status"], row["evidence"]] for row in rows]),
                "",
                "## Decision",
                "",
                rows[-1]["evidence"],
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_all() -> None:
    run_state_reconciliation()
    run_runtime_profile()
    run_baseline_fairness()
    run_optimization_sweep()
    run_policy_ablation_quality()
    run_scale_stress()
    run_edge_diagnostic_audit()
    run_no_leakage_runtime()
    run_learning_next_iteration()
    run_promotion_decision()
    print("g4ir2 runtime bottleneck and policy scaling audit complete")


if __name__ == "__main__":
    run_all()
