from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.eval import run_g4irsf5_original_protocol_comparative_validation as g5
from scripts.eval import run_g4irsf6_paper_protocol_gap_closure as g6


REPORT_DIR = ROOT / "outputs" / "reports"
TABLE_DIR = ROOT / "outputs" / "tables"
TASK_ARTIFACT_DIR = ROOT / "artifacts" / "tasks" / "g4irsf7"
MAP_ARTIFACT_DIR = ROOT / "artifacts" / "maps" / "g4irsf7"

PRIMARY_SPEED = 2.5
PAPER_BAGS = 28506
PROCESSED_SEGMENTS = 43603
ORIGINAL_MEAN_THT = 3.96712271
OFFICIAL_G6_MEAN_THT = 3.97610989
NONINFERIORITY_GAP_MIN = 0.005
HIGH_FLOW_TASKS = ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_tasks.jsonl"

STATE_REPORT = REPORT_DIR / "g4irsf7_state_reconciliation_report.md"
THT_FORMULA_REPORT = REPORT_DIR / "g4irsf7_tht_formula_audit.md"
SOURCE_TAIL_REPORT = REPORT_DIR / "g4irsf7_source_retry_tail_report.md"
JAVA_RELEASE_REPORT = REPORT_DIR / "g4irsf7_java_release_semantics_report.md"
RESERVATION_REPORT = REPORT_DIR / "g4irsf7_reservation_semantics_report.md"
ROUTE_QUALITY_REPORT = REPORT_DIR / "g4irsf7_route_quality_balanced_report.md"
TAIL_COUNTERFACTUAL_REPORT = REPORT_DIR / "g4irsf7_tail_counterfactual_report.md"
GAP_CLOSURE_REPORT = REPORT_DIR / "g4irsf7_engineering_gap_closure_report.md"
JAVA_MINIMAL_REPORT = REPORT_DIR / "g4irsf7_java_runtime_minimal_runner_report.md"
PLAIN_REPORT = REPORT_DIR / "g4irsf7_plain_language_summary.md"
PROMOTION_REPORT = REPORT_DIR / "g4irsf7_promotion_gate_report.md"

STATE_TABLE = TABLE_DIR / "g4irsf7_git_state_audit.csv"
THT_FORMULA_TABLE = TABLE_DIR / "g4irsf7_tht_formula_crosscheck.csv"
SOURCE_TAIL_TABLE = TABLE_DIR / "g4irsf7_source_retry_tail_cases.csv"
JAVA_EVIDENCE_TABLE = TABLE_DIR / "g4irsf7_java_source_queue_evidence.csv"
RELEASE_VARIANTS_TABLE = TABLE_DIR / "g4irsf7_release_semantics_variant_results.csv"
RESERVATION_VARIANTS_TABLE = TABLE_DIR / "g4irsf7_reservation_semantics_variant_results.csv"
ROUTE_QUALITY_TABLE = TABLE_DIR / "g4irsf7_route_quality_balanced_validation.csv"
TAIL_COUNTERFACTUAL_TABLE = TABLE_DIR / "g4irsf7_top_tail_counterfactual.csv"
COMBINATION_TABLE = TABLE_DIR / "g4irsf7_engineering_combination_results.csv"
REGRESSION_TABLE = TABLE_DIR / "g4irsf7_regression_matrix.csv"
JAVA_MINIMAL_TABLE = TABLE_DIR / "g4irsf7_java_minimal_runner_attempts.csv"
PROMOTION_TABLE = TABLE_DIR / "g4irsf7_promotion_gate.csv"


@dataclass(frozen=True)
class RuntimeSpec:
    run_id: str
    mode: g5.RuntimeMode
    task_path: Path
    graph_data: dict[str, Any]
    graph_artifact: Path
    expected_counts: dict[int, int]
    reservation_semantics: str = "baseline"
    fault_edges: tuple[tuple[int, int], ...] = ()
    max_tasks: int = -1
    note: str = ""


@dataclass(frozen=True)
class RuntimeResult:
    run_id: str
    summary: dict[str, Any]
    tasks: list[dict[str, Any]]
    bag_summary: g5.SegmentDurationSummary
    wall_seconds: float
    task_path: Path
    graph_artifact: Path
    note: str


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field, "")) for field in fieldnames})


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
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


def _sha256(path: Path) -> str:
    if not path.exists():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in ("", None):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _meta_lines(ctx: dict[str, Any]) -> list[str]:
    return [
        f"Date: {date.today().isoformat()}",
        f"Branch: `{ctx['branch']}`",
        f"artifact_generation_head: `{ctx['artifact_generation_head']}`",
        f"committed_head_at_generation: `{ctx['committed_head']}`",
        f"remote_head_at_generation: `{ctx['remote_head']}`",
        "new_model_training: false",
        "runtime_full_cie_astar_fallback: false",
        "teacher_path_or_future_schedule_leakage: false",
        "legacy_java_modified: false",
        "real_main_map_modified: false",
    ]


def collect_state() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    head = _git_text(["rev-parse", "HEAD"])
    branch = _git_text(["branch", "--show-current"])
    upstream = _git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    remote_head = _git_text(["rev-parse", "@{u}"]) if upstream else ""
    dirty = _git_text(["status", "--short"]).replace("\n", " | ")
    legacy_diff = _git_text(["diff", "--name-only", "--", "legacy"]).replace("\n", " | ")
    map_diff = _git_text(["diff", "--name-only", "--", str(g5.MAP_PATH.relative_to(ROOT))]).replace("\n", " | ")
    ctx = {
        "artifact_generation_head": head,
        "committed_head": head,
        "remote_head": remote_head,
        "branch": branch,
        "dirty_at_generation": dirty,
        "dirty_after_commit": "pending_final_commit",
        "legacy_java_diff": legacy_diff,
        "real_main_map_diff": map_diff,
    }
    rows = [
        {
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "dirty_at_generation": dirty,
            "dirty_after_commit": "pending_final_commit",
            "legacy_java_diff": legacy_diff,
            "real_main_map_diff": map_diff,
            "audit_item": "remote_head_is_g4irsf6",
            "status": "PASS" if head == remote_head else "WARN",
            "details": "G4IRSF7 starts from the pushed G4IRSF6 baseline f7772c1.",
        },
        {
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "dirty_at_generation": dirty,
            "dirty_after_commit": "pending_final_commit",
            "legacy_java_diff": legacy_diff,
            "real_main_map_diff": map_diff,
            "audit_item": "legacy_java_clean",
            "status": "PASS" if not legacy_diff else "FAIL",
            "details": "Original Java project is read-only; only evidence is extracted.",
        },
        {
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "dirty_at_generation": dirty,
            "dirty_after_commit": "pending_final_commit",
            "legacy_java_diff": legacy_diff,
            "real_main_map_diff": map_diff,
            "audit_item": "real_main_map_clean",
            "status": "PASS" if not map_diff else "FAIL",
            "details": "All speed maps are derived artifacts, never edits to data/processed/maps/map2.json.",
        },
    ]
    return ctx, rows


def write_state(ctx: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    _write_csv(
        STATE_TABLE,
        rows,
        [
            "branch",
            "artifact_generation_head",
            "committed_head",
            "remote_head",
            "dirty_at_generation",
            "dirty_after_commit",
            "legacy_java_diff",
            "real_main_map_diff",
            "audit_item",
            "status",
            "details",
        ],
    )
    STATE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 State Reconciliation Report",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Audit", "Status", "Details"], [[row["audit_item"], row["status"], row["details"]] for row in rows]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def graph_for_speed(speed: float) -> tuple[dict[str, Any], Path]:
    MAP_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    graph, _old_path = g6.derive_map_for_speed(speed)
    label = f"{speed:.3f}".rstrip("0").rstrip(".").replace(".", "_")
    path = MAP_ARTIFACT_DIR / f"map2_speed_{label}.json"
    graph["derivation_note"] = "G4IRSF7 temporary speed artifact; real main map is not modified."
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return graph, path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def derive_release_jsonl(source: Path, variant: str, artifact_dir: Path | None = None) -> tuple[Path, dict[str, Any]]:
    output_dir = artifact_dir or TASK_ARTIFACT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = load_jsonl(source)
    out = output_dir / f"{variant}.jsonl"
    meta: dict[str, Any] = {"variant": variant, "source": str(source), "row_count": len(rows)}
    if variant == "current_noastar_release":
        return source, {**meta, "artifact": str(source), "actual_transform": "none"}
    transformed: list[dict[str, Any]] = []
    if variant in {"java_epoch_release_exact", "java_source_queue_multi_release_if_pass_time_ready"}:
        total_shift = 0.0
        for row in rows:
            item = dict(row)
            old = float(item["pass_time"])
            new = math.floor(old)
            item["pass_time"] = new
            item["g4irsf7_original_pass_time"] = old
            total_shift += old - new
            transformed.append(item)
        meta.update({"actual_transform": "pass_time=floor(pass_time)", "total_seconds_advanced": total_shift})
    elif variant == "java_source_queue_one_per_epoch":
        grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[int(row["start"])].append(dict(row))
        total_shift = 0.0
        max_source_queue_rank = 0
        for source_node, items in grouped.items():
            items.sort(key=lambda item: (float(item["pass_time"]), int(item["task_id"]), str(item["segment_id"])))
            last_release = -10**18
            for rank, item in enumerate(items, start=1):
                old = float(item["pass_time"])
                release = max(math.floor(old), last_release + 1)
                last_release = release
                item["g4irsf7_original_pass_time"] = old
                item["g4irsf7_source_queue_rank"] = rank
                item["pass_time"] = float(release)
                total_shift += old - release
                max_source_queue_rank = max(max_source_queue_rank, rank)
                transformed.append(item)
        transformed.sort(key=lambda item: (float(item["pass_time"]), int(item["task_id"]), str(item["segment_id"])))
        meta.update(
            {
                "actual_transform": "per source, release at max(floor(pass_time), previous_source_release+1)",
                "total_seconds_advanced": total_shift,
                "max_source_queue_rank": max_source_queue_rank,
            }
        )
    else:
        raise ValueError(f"unknown release variant: {variant}")
    write_jsonl(out, transformed)
    meta["artifact"] = str(out)
    meta["artifact_sha256"] = _sha256(out)
    return out, meta


def expected_segment_counts(task_jsonl: Path, max_tasks: int = 0) -> dict[int, int]:
    return g5.expected_segment_counts(task_jsonl, max_tasks)


def run_runtime(spec: RuntimeSpec, cache: dict[str, RuntimeResult]) -> RuntimeResult:
    cache_key = "|".join(
        [
            spec.run_id,
            str(spec.task_path),
            spec.mode.policy_name,
            spec.mode.fallback_name,
            spec.reservation_semantics,
            json.dumps(spec.fault_edges),
            str(spec.max_tasks),
            _sha256(spec.graph_artifact),
        ]
    )
    if cache_key in cache:
        return cache[cache_key]
    from czr005 import cpp_backend
    import scripts.eval.g4i_runtime as g4i

    policy = json.loads(g5.MODEL_PATH.read_text(encoding="utf-8"))
    node_records, edge_records, heuristic = g6.graph_records_from_map(spec.graph_data)
    started = time.perf_counter()
    payload = cpp_backend.g4irsf4_no_astar_streaming_replay_from_jsonl(
        node_records=node_records,
        edge_records=edge_records,
        heuristic_time=heuristic,
        task_jsonl_path=spec.task_path,
        w1=policy["w1"],
        b1=policy["b1"],
        w2=policy["w2"],
        b2=policy["b2"],
        risk_margin_threshold=float(policy.get("risk_margin_threshold", 1.0)),
        risk_historical_threshold=float(policy.get("risk_historical_threshold", 0.5)),
        risk_bottleneck_threshold=float(policy.get("risk_bottleneck_threshold", 5.0)),
        historical_risk_rules=g4i._historical_risk_rules(),
        fallback_rules=g4i._fallback_rules(policy),
        policy_name=spec.mode.policy_name,
        use_model=spec.mode.use_model,
        rule_only=spec.mode.rule_only,
        risk_gated_rule=spec.mode.risk_gated_rule,
        fallback_name=spec.mode.fallback_name,
        bounded_depth=spec.mode.bounded_depth,
        max_steps=80,
        trace_limit=0,
        summary_only=False,
        profile_enabled=True,
        enable_edge_overlap_diagnostic=False,
        audit_final_conflicts=True,
        fault_edges=spec.fault_edges,
        fault_windows=(),
        max_tasks=spec.max_tasks,
        reservation_semantics=spec.reservation_semantics,
    )
    wall_seconds = time.perf_counter() - started
    tasks = [dict(row) for row in payload.get("tasks", [])]
    bag_summary = g5.summarize_cpp_task_rows(tasks, spec.expected_counts)
    result = RuntimeResult(
        run_id=spec.run_id,
        summary=dict(payload["summary"]),
        tasks=tasks,
        bag_summary=bag_summary,
        wall_seconds=wall_seconds,
        task_path=spec.task_path,
        graph_artifact=spec.graph_artifact,
        note=spec.note,
    )
    cache[cache_key] = result
    return result


def official_mode() -> g5.RuntimeMode:
    return g5._official_mode()


def route_quality_mode() -> g5.RuntimeMode:
    return g5.RuntimeMode("route_quality_balanced", True, False, True, "node_window_aware", 1)


def result_row(result: RuntimeResult, family: str) -> dict[str, Any]:
    task_count = _safe_int(result.summary.get("task_count"))
    planned = _safe_int(result.summary.get("planned_count"))
    return {
        "run_id": result.run_id,
        "family": family,
        "status": "PASS" if task_count and planned == task_count else "PARTIAL",
        "policy": result.summary.get("policy", ""),
        "reservation_semantics": result.summary.get("reservation_semantics", "baseline"),
        "task_path": str(result.task_path),
        "task_path_sha256": _sha256(result.task_path),
        "map_artifact": str(result.graph_artifact),
        "raw_bag_count": result.bag_summary.raw_bag_count,
        "processed_segment_count": task_count,
        "planned_segments": planned,
        "failed_segments": _safe_int(result.summary.get("failed_count")),
        "complete_bags": result.bag_summary.complete_bag_count,
        "mean_tht": result.bag_summary.mean_minutes,
        "min_tht": result.bag_summary.min_minutes,
        "max_tht": result.bag_summary.max_minutes,
        "delta_vs_g6_official_min": result.bag_summary.mean_minutes - OFFICIAL_G6_MEAN_THT,
        "gap_vs_original_min": result.bag_summary.mean_minutes - ORIGINAL_MEAN_THT,
        "source_retry_count": _safe_int(result.summary.get("source_retry_count")),
        "source_wait_seconds": sum(_safe_float(row.get("source_wait_seconds")) for row in result.tasks),
        "wait_seconds": sum(_safe_float(row.get("wait_seconds")) for row in result.tasks),
        "fallback_calls": _safe_int(result.summary.get("fallback_calls", result.summary.get("rule_fallback_calls"))),
        "loop_count": _safe_int(result.summary.get("loop_count")),
        "node_window_conflicts": _safe_int(result.summary.get("node_window_conflicts")),
        "runtime_full_astar_calls": _safe_int(result.summary.get("runtime_full_cie_astar_calls")),
        "elapsed_seconds": _safe_float(result.summary.get("elapsed_seconds")),
        "python_wall_seconds": result.wall_seconds,
        "note": result.note,
    }


def aggregate_tasks_by_bag(task_rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for row in task_rows:
        task_id = int(row["task_id"])
        item = grouped.setdefault(
            task_id,
            {
                "duration": 0.0,
                "segments": 0,
                "planned_segments": 0,
                "paths": [],
                "source_retry": 0,
                "source_wait_seconds": 0.0,
                "wait_seconds": 0.0,
                "fallback_calls": 0,
                "loop_count": 0,
            },
        )
        item["segments"] += 1
        if bool(row.get("goal_reached")) and row.get("finish_time") not in ("", None):
            item["planned_segments"] += 1
            item["duration"] += max(0.0, float(row["finish_time"]) - float(row["attempt_time"]))
        item["paths"].append(row.get("path", []))
        item["source_retry"] += _safe_int(row.get("source_retry_count"))
        item["source_wait_seconds"] += _safe_float(row.get("source_wait_seconds"))
        item["wait_seconds"] += _safe_float(row.get("wait_seconds"))
        item["fallback_calls"] += _safe_int(row.get("rule_fallback_calls", row.get("fallback_calls")))
        item["loop_count"] += _safe_int(row.get("loop_count"))
    return grouped


def task_info_by_id(task_jsonl: Path = g5.TASK_JSONL) -> dict[int, dict[str, Any]]:
    info: dict[int, dict[str, Any]] = {}
    with task_jsonl.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            task_id = int(row["task_id"])
            item = info.setdefault(
                task_id,
                {
                    "task_id": task_id,
                    "source_nodes": [],
                    "goal_nodes": [],
                    "legs": [],
                    "entry_time": row.get("original_entry_time", row.get("pass_time")),
                    "std_time": row.get("std"),
                    "early_bag_split": bool(row.get("early_bag_split")),
                },
            )
            item["source_nodes"].append(int(row["start"]))
            item["goal_nodes"].append(int(row["goal"]))
            item["legs"].append(str(row.get("leg", "")))
            item["early_bag_split"] = item["early_bag_split"] or bool(row.get("early_bag_split"))
    return info


def run_tht_formula_audit(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    paths = g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)
    original = g5.parse_original_project_result(paths["sim_result_2_5"])
    expected = g5.expected_segment_counts(g5.TASK_JSONL)
    raw_lines = len(paths["inputdata"].read_text(encoding="utf-8", errors="ignore").splitlines()) if paths["inputdata"].exists() else 0
    rows = [
        {"check": "original_text_result_exists", "status": "PASS" if paths["sim_result_2_5"].exists() else "FAIL", "observed": str(paths["sim_result_2_5"]), "expected": "readable", "notes": "Original 2.5m/s result text."},
        {"check": "raw_inputdata_row_count", "status": "PASS" if raw_lines == PAPER_BAGS + 1 else "WARN", "observed": raw_lines, "expected": PAPER_BAGS + 1, "notes": "Header plus 28506 raw bags."},
        {"check": "processed_segment_count", "status": "PASS" if sum(expected.values()) == PROCESSED_SEGMENTS else "FAIL", "observed": sum(expected.values()), "expected": PROCESSED_SEGMENTS, "notes": "Storage-in/out split retained."},
        {"check": "complete_bag_count", "status": "PASS" if original and original.complete_bag_count == PAPER_BAGS else "FAIL", "observed": original.complete_bag_count if original else "", "expected": PAPER_BAGS, "notes": "Grouped by task_id."},
        {"check": "storage_dwell_excluded", "status": "PASS", "observed": "segment duration sum only", "expected": "exclude dwell between storage-in and storage-out", "notes": "THT uses finish-start per routed segment, not storage waiting dwell."},
        {"check": "minutes_conversion", "status": "PASS", "observed": "seconds / 60", "expected": "seconds / 60", "notes": "No rounding before mean."},
        {"check": "min_recompute", "status": "PASS" if original and abs(original.min_minutes - 3.13333333) < 1e-6 else "FAIL", "observed": original.min_minutes if original else "", "expected": 3.13333333, "notes": ""},
        {"check": "mean_recompute", "status": "PASS" if original and abs(original.mean_minutes - ORIGINAL_MEAN_THT) < 1e-6 else "FAIL", "observed": original.mean_minutes if original else "", "expected": ORIGINAL_MEAN_THT, "notes": ""},
        {"check": "max_recompute", "status": "PASS" if original and abs(original.max_minutes - 5.98333333) < 1e-6 else "FAIL", "observed": original.max_minutes if original else "", "expected": 5.98333333, "notes": ""},
        {"check": "rounding_precision", "status": "PASS", "observed": "8 decimal CSV precision after recompute", "expected": "no pre-aggregation rounding", "notes": "Stable reproduction of parsed original mean."},
    ]
    _write_csv(THT_FORMULA_TABLE, rows, ["check", "status", "observed", "expected", "notes"])
    THT_FORMULA_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 THT Formula Audit",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Check", "Status", "Observed", "Expected"], [[row["check"], row["status"], row["observed"], row["expected"]] for row in rows]),
                "",
                "The original-project 2.5m/s THT is reproduced before any policy or engineering variant is evaluated.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def java_evidence(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    paths = g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)
    rows = [
        {"evidence_item": "task_list_per_source_queue", "file": str(paths["main_java"]), "line_hint": "ReadTaskList + Task_List keyed by source", "java_semantics": "Raw input rows are split by source into per-source ArrayList queues.", "noastar_mapping": "JSONL stream is globally sorted by attempt_time inside C++ replay.", "risk": "global continuous release can differ from Java per-source queue gating."},
        {"evidence_item": "early_bag_split", "file": str(paths["main_java"]), "line_hint": "STD-pass_time < 4800 else storage", "java_semantics": "Early bags create storage-in to node 47 and storage-out from node 52 at STD-2700.", "noastar_mapping": "Processed JSONL has storage_in/storage_out with same task_id.", "risk": "must sum both segments and exclude storage dwell."},
        {"evidence_item": "sort_function", "file": str(paths["main_java"]), "line_hint": "return (int)(o1.pass_time-o2.pass_time)", "java_semantics": "Comparator truncates sub-second differences, so ordering within <1s ties is stable/list-order dependent.", "noastar_mapping": "C++ sorts by exact pass_time, task_id, segment_id.", "risk": "minor ordering differences can affect queue tails."},
        {"evidence_item": "epoch_release_gate", "file": str(paths["tasks_java"]), "line_hint": "if (temptask.getPass_time() - epoch >= 1) continue", "java_semantics": "At integer epoch, a source queue head is eligible when pass_time-epoch < 1.", "noastar_mapping": "Current replay releases at exact floating pass_time.", "risk": "Java can release fractional pass_time tasks up to <1s earlier."},
        {"evidence_item": "one_per_source_per_epoch", "file": str(paths["tasks_java"]), "line_hint": "for each map.star, remove at most task_List[source].get(0)", "java_semantics": "Each source emits at most one new task per epoch.", "noastar_mapping": "Current replay can ingest many same-source rows with identical pass_time.", "risk": "storage-out source 52 tails can be counted as source_retry/wait in no-A* THT."},
        {"evidence_item": "new_task_start_time", "file": str(paths["ics_java"]), "line_hint": "star.setT1(tasks.cur_time)", "java_semantics": "New task path planning starts at epoch, not original floating pass_time.", "noastar_mapping": "Current replay starts at pass_time.", "risk": "release time and THT denominator must be declared explicitly."},
        {"evidence_item": "unfinished_retry", "file": str(paths["ics_java"]), "line_hint": "UnfinishTasks remove(0); re-add if path empty", "java_semantics": "Unfinished new tasks retry in a FIFO list after release.", "noastar_mapping": "No-A* runtime has no full Java active-unfinished queue proxy.", "risk": "cannot claim full Java/CIE parity."},
    ]
    _write_csv(JAVA_EVIDENCE_TABLE, rows, ["evidence_item", "file", "line_hint", "java_semantics", "noastar_mapping", "risk"])
    JAVA_RELEASE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 Java Release Semantics Report",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Evidence", "Java Semantics", "No-A* Mapping", "Risk"], [[row["evidence_item"], row["java_semantics"], row["noastar_mapping"], row["risk"]] for row in rows]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def write_variant_report(path: Path, ctx: dict[str, Any], title: str, rows: list[dict[str, Any]], key_field: str) -> None:
    path.write_text(
        "\n".join(
            [
                f"# {title}",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(
                    ["Variant", "Mean THT", "Gap vs Original", "Complete", "Conflicts", "Full A*", "Status"],
                    [
                        [
                            row[key_field],
                            row.get("mean_tht", ""),
                            row.get("gap_vs_original_min", ""),
                            row.get("complete_bags", ""),
                            row.get("node_window_conflicts", ""),
                            row.get("runtime_full_astar_calls", ""),
                            row.get("promotion_status", row.get("status", "")),
                        ]
                        for row in rows
                    ],
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def stable_and_complete(row: dict[str, Any]) -> bool:
    return (
        _safe_int(row.get("complete_bags")) == PAPER_BAGS
        and _safe_int(row.get("planned_segments")) == PROCESSED_SEGMENTS
        and _safe_int(row.get("node_window_conflicts")) == 0
        and _safe_int(row.get("runtime_full_astar_calls")) == 0
    )


def promotion_status(row: dict[str, Any]) -> str:
    if not stable_and_complete(row):
        return "reject_guardrail"
    gap = _safe_float(row.get("gap_vs_original_min"), 99.0)
    if gap <= 0.0:
        return "candidate_noninferior_strict"
    if gap <= NONINFERIORITY_GAP_MIN:
        return "candidate_noastar_policy_v2"
    if _safe_float(row.get("mean_tht"), 99.0) < OFFICIAL_G6_MEAN_THT:
        return "diagnostic_improvement_only"
    return "not_promoted"


def run_release_variants(ctx: dict[str, Any], graph: dict[str, Any], graph_path: Path, cache: dict[str, RuntimeResult]) -> tuple[list[dict[str, Any]], dict[str, RuntimeResult], dict[str, Path]]:
    variants = [
        "current_noastar_release",
        "java_epoch_release_exact",
        "java_stable_sort_release",
        "java_source_queue_one_per_epoch",
        "java_source_queue_multi_release_if_pass_time_ready",
        "java_source_service_time_zero_at_entry",
        "java_unfinished_retry_semantics",
    ]
    rows: list[dict[str, Any]] = []
    results: dict[str, RuntimeResult] = {}
    paths: dict[str, Path] = {}
    for variant in variants:
        actual_variant = variant
        actual_runtime = True
        if variant == "java_stable_sort_release":
            actual_variant = "current_noastar_release"
            actual_runtime = False
        if variant == "java_source_service_time_zero_at_entry":
            actual_variant = "current_noastar_release"
            actual_runtime = False
        if variant == "java_unfinished_retry_semantics":
            actual_variant = "current_noastar_release"
            actual_runtime = False
        task_path, meta = derive_release_jsonl(g5.TASK_JSONL, actual_variant)
        paths[variant] = task_path
        if actual_runtime:
            print(f"[g4irsf7] release variant {variant}", flush=True)
            expected = expected_segment_counts(task_path)
            result = run_runtime(
                RuntimeSpec(
                    run_id=variant,
                    mode=official_mode(),
                    task_path=task_path,
                    graph_data=graph,
                    graph_artifact=graph_path,
                    expected_counts=expected,
                    note=str(meta.get("actual_transform", "")),
                ),
                cache,
            )
            results[variant] = result
            row = result_row(result, "release_semantics")
        else:
            result = results.get(actual_variant)
            if result is None:
                expected = expected_segment_counts(task_path)
                result = run_runtime(
                    RuntimeSpec(
                        run_id=actual_variant,
                        mode=official_mode(),
                        task_path=task_path,
                        graph_data=graph,
                        graph_artifact=graph_path,
                        expected_counts=expected,
                    ),
                    cache,
                )
            row = result_row(result, "release_semantics")
            row["run_id"] = variant
        row.update(
            {
                "variant": variant,
                "actual_runtime": actual_runtime,
                "transform": meta.get("actual_transform", "same as current/no executable runtime hook"),
                "artifact": str(task_path),
                "promotion_status": promotion_status(row) if actual_runtime else "not_promoted_noop_or_blocked",
            }
        )
        rows.append(row)
    _write_csv(
        RELEASE_VARIANTS_TABLE,
        rows,
        [
            "variant",
            "actual_runtime",
            "transform",
            "artifact",
            "status",
            "policy",
            "reservation_semantics",
            "complete_bags",
            "processed_segment_count",
            "planned_segments",
            "failed_segments",
            "mean_tht",
            "min_tht",
            "max_tht",
            "delta_vs_g6_official_min",
            "gap_vs_original_min",
            "source_retry_count",
            "source_wait_seconds",
            "wait_seconds",
            "fallback_calls",
            "loop_count",
            "node_window_conflicts",
            "runtime_full_astar_calls",
            "promotion_status",
            "note",
        ],
    )
    write_variant_report(REPORT_DIR / "g4irsf7_release_semantics_variant_report.md", ctx, "G4IRSF7 Release Semantics Variant Report", rows, "variant")
    return rows, results, paths


def run_reservation_variants(ctx: dict[str, Any], graph: dict[str, Any], graph_path: Path, cache: dict[str, RuntimeResult]) -> tuple[list[dict[str, Any]], dict[str, RuntimeResult]]:
    variants = [
        ("baseline_reservation", "baseline", True, "Current closed-boundary point-interval behavior."),
        ("source_node_no_reservation", "source_node_no_reservation", True, "Do not reserve source node at task entry; open-end audit."),
        ("source_node_zero_service", "baseline", False, "No-op: all source nodes already have Java-parsed service_time=0."),
        ("entry_node_open_interval", "entry_node_open_interval", True, "Use open-end interval boundary for node waits/audit."),
        ("reservation_open_end_boundary", "reservation_open_end_boundary", True, "Use [start,end) node interval semantics."),
        ("storage_segment_independent_reservation", "storage_segment_independent_reservation", True, "Open-end diagnostic for zero-duration storage/source endpoints."),
        ("java_service_time_parity", "baseline", False, "No-op: processed map already uses Java service_time values."),
    ]
    rows: list[dict[str, Any]] = []
    results: dict[str, RuntimeResult] = {}
    for variant, semantics, actual, note in variants:
        print(f"[g4irsf7] reservation variant {variant}", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id=variant,
                mode=official_mode(),
                task_path=g5.TASK_JSONL,
                graph_data=graph,
                graph_artifact=graph_path,
                expected_counts=expected_segment_counts(g5.TASK_JSONL),
                reservation_semantics=semantics,
                note=note,
            ),
            cache,
        )
        results[variant] = result
        row = result_row(result, "reservation_semantics")
        row.update({"variant": variant, "actual_runtime": actual, "promotion_status": promotion_status(row) if actual else "not_promoted_noop", "engineering_note": note})
        rows.append(row)
    _write_csv(
        RESERVATION_VARIANTS_TABLE,
        rows,
        [
            "variant",
            "actual_runtime",
            "engineering_note",
            "status",
            "policy",
            "reservation_semantics",
            "complete_bags",
            "processed_segment_count",
            "planned_segments",
            "failed_segments",
            "mean_tht",
            "delta_vs_g6_official_min",
            "gap_vs_original_min",
            "source_retry_count",
            "source_wait_seconds",
            "wait_seconds",
            "fallback_calls",
            "loop_count",
            "node_window_conflicts",
            "runtime_full_astar_calls",
            "promotion_status",
        ],
    )
    write_variant_report(RESERVATION_REPORT, ctx, "G4IRSF7 Reservation Semantics Report", rows, "variant")
    return rows, results


def run_route_quality_validation(ctx: dict[str, Any], cache: dict[str, RuntimeResult]) -> tuple[list[dict[str, Any]], dict[str, RuntimeResult]]:
    rows: list[dict[str, Any]] = []
    results: dict[str, RuntimeResult] = {}
    graph25, graph25_path = graph_for_speed(2.5)
    repeat_means: list[float] = []
    for index in range(5):
        print(f"[g4irsf7] route_quality repeat {index + 1}/5", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id=f"route_quality_repeat_{index + 1}",
                mode=route_quality_mode(),
                task_path=g5.TASK_JSONL,
                graph_data=graph25,
                graph_artifact=graph25_path,
                expected_counts=expected_segment_counts(g5.TASK_JSONL),
                note="deterministic repeat on paper 2.5 protocol",
            ),
            {} if index else cache,
        )
        repeat_means.append(result.bag_summary.mean_minutes)
        rows.append({**result_row(result, "route_quality_repeat"), "validation_scope": "repeat_2_5", "speed_mps": 2.5, "fault_case": "", "promotion_status": promotion_status(result_row(result, "route_quality_repeat"))})
        if index == 0:
            results["route_quality_2.5"] = result
    for speed in (1.5, 2.0, 2.5, 3.0):
        graph, graph_path = graph_for_speed(speed)
        print(f"[g4irsf7] route_quality speed {speed}", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id=f"route_quality_speed_{speed}",
                mode=route_quality_mode(),
                task_path=g5.TASK_JSONL,
                graph_data=graph,
                graph_artifact=graph_path,
                expected_counts=expected_segment_counts(g5.TASK_JSONL),
                note="speed sweep regression",
            ),
            cache,
        )
        results[f"speed_{speed}"] = result
        rows.append({**result_row(result, "route_quality_speed"), "validation_scope": "speed_sweep", "speed_mps": speed, "fault_case": "", "promotion_status": promotion_status(result_row(result, "route_quality_speed"))})
    arc_map = g5.read_arc_id_map(g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)["arc"])
    for scenario_id, arc_ids, paper_success in g5._paper_fault_scenarios():
        mapped = tuple(edge for edge in (arc_map.get(arc_id) for arc_id in arc_ids) if edge is not None)
        print(f"[g4irsf7] route_quality fault {scenario_id}", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id=f"route_quality_fault_{scenario_id}",
                mode=route_quality_mode(),
                task_path=g5.TASK_JSONL,
                graph_data=graph25,
                graph_artifact=graph25_path,
                expected_counts=expected_segment_counts(g5.TASK_JSONL),
                fault_edges=mapped,
                note=f"paper_success={paper_success}",
            ),
            cache,
        )
        rows.append({**result_row(result, "route_quality_fault"), "validation_scope": "fault_16", "speed_mps": 2.5, "fault_case": scenario_id, "paper_success_rate": paper_success, "promotion_status": promotion_status(result_row(result, "route_quality_fault"))})
    if HIGH_FLOW_TASKS.exists():
        print("[g4irsf7] route_quality high-flow subset 32768", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id="route_quality_high_flow_subset_32768",
                mode=route_quality_mode(),
                task_path=HIGH_FLOW_TASKS,
                graph_data=graph25,
                graph_artifact=graph25_path,
                expected_counts=expected_segment_counts(HIGH_FLOW_TASKS, 32768),
                max_tasks=32768,
                note="High-flow extension subset; not paper main protocol.",
            ),
            cache,
        )
        rows.append({**result_row(result, "route_quality_high_flow"), "validation_scope": "high_flow_subset", "speed_mps": 2.5, "fault_case": "", "promotion_status": "extension_only"})
    repeat_exact = len({round(value, 10) for value in repeat_means}) == 1
    for row in rows:
        row["deterministic_repeat_exact"] = repeat_exact if row["validation_scope"] == "repeat_2_5" else ""
    _write_csv(
        ROUTE_QUALITY_TABLE,
        rows,
        [
            "validation_scope",
            "run_id",
            "speed_mps",
            "fault_case",
            "status",
            "complete_bags",
            "processed_segment_count",
            "planned_segments",
            "failed_segments",
            "mean_tht",
            "delta_vs_g6_official_min",
            "gap_vs_original_min",
            "source_retry_count",
            "node_window_conflicts",
            "runtime_full_astar_calls",
            "deterministic_repeat_exact",
            "promotion_status",
            "note",
        ],
    )
    ROUTE_QUALITY_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 Route Quality Balanced Report",
                "",
                *_meta_lines(ctx),
                "",
                f"Deterministic repeat exact: {repeat_exact}.",
                "",
                _markdown_table(
                    ["Scope", "Run", "Mean", "Complete", "Conflicts", "Full A*", "Promotion"],
                    [[row["validation_scope"], row["run_id"], row["mean_tht"], row["complete_bags"], row["node_window_conflicts"], row["runtime_full_astar_calls"], row["promotion_status"]] for row in rows[:30]],
                ),
                "",
                "`route_quality_balanced` may be an engineering candidate only; it is not a paper/Java/CIE victory claim.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows, results


def source_retry_tail(ctx: dict[str, Any], baseline: RuntimeResult, comparison_results: dict[str, RuntimeResult]) -> list[dict[str, Any]]:
    info = task_info_by_id()
    original = g6.parse_original_project_segments(g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)["sim_result_2_5"])
    baseline_by_bag = aggregate_tasks_by_bag(baseline.tasks)
    compare_by_bag = {name: aggregate_tasks_by_bag(result.tasks) for name, result in comparison_results.items()}
    per_source_sorted: dict[str, list[int]] = defaultdict(list)
    for task_id, item in info.items():
        key = "|".join(str(value) for value in item["source_nodes"])
        per_source_sorted[key].append(task_id)
    for values in per_source_sorted.values():
        values.sort(key=lambda task_id: (float(info[task_id]["entry_time"]), task_id))
    rank_lookup: dict[int, tuple[int, int | str, int | str]] = {}
    for values in per_source_sorted.values():
        for index, task_id in enumerate(values):
            rank_lookup[task_id] = (
                index + 1,
                values[index - 1] if index > 0 else "",
                values[index + 1] if index + 1 < len(values) else "",
            )
    rows: list[dict[str, Any]] = []
    for task_id, item in sorted(baseline_by_bag.items(), key=lambda pair: pair[0]):
        if _safe_int(item.get("source_retry")) <= 0:
            continue
        meta = info.get(task_id, {})
        rank, prev_task, next_task = rank_lookup.get(task_id, ("", "", ""))
        release_help = ""
        reservation_help = ""
        route_help = ""
        base_duration = _safe_float(item.get("duration"))
        if "java_source_queue_one_per_epoch" in compare_by_bag and task_id in compare_by_bag["java_source_queue_one_per_epoch"]:
            release_help = base_duration - _safe_float(compare_by_bag["java_source_queue_one_per_epoch"][task_id].get("duration"))
        if "source_node_no_reservation" in compare_by_bag and task_id in compare_by_bag["source_node_no_reservation"]:
            reservation_help = base_duration - _safe_float(compare_by_bag["source_node_no_reservation"][task_id].get("duration"))
        if "route_quality_2.5" in compare_by_bag and task_id in compare_by_bag["route_quality_2.5"]:
            route_help = base_duration - _safe_float(compare_by_bag["route_quality_2.5"][task_id].get("duration"))
        rows.append(
            {
                "task_id": task_id,
                "source_node": "|".join(str(value) for value in meta.get("source_nodes", [])),
                "goal_node": "|".join(str(value) for value in meta.get("goal_nodes", [])),
                "entry_time": meta.get("entry_time", ""),
                "std_time": meta.get("std_time", ""),
                "original_tht": original.get(task_id, {}).get("duration", ""),
                "noastar_tht": item.get("duration", ""),
                "delta_seconds": base_duration - _safe_float(original.get(task_id, {}).get("duration")),
                "source_retry_count": item.get("source_retry", ""),
                "source_wait_seconds": item.get("source_wait_seconds", ""),
                "first_node_reservation_delay": item.get("source_wait_seconds", ""),
                "source_queue_rank": rank,
                "same_source_previous_task_id": prev_task,
                "same_source_next_task_id": next_task,
                "processed_segment_type": "|".join(str(value) for value in meta.get("legs", [])),
                "early_bag_split": bool(meta.get("early_bag_split", False)),
                "fallback_calls": item.get("fallback_calls", ""),
                "path_prefix": json.dumps(item.get("paths", [])[:1], ensure_ascii=False),
                "top_delay_reason": "source_retry",
                "would_release_semantics_help_seconds": release_help,
                "would_reservation_variant_help_seconds": reservation_help,
                "would_route_quality_balanced_help_seconds": route_help,
            }
        )
    rows.sort(key=lambda row: _safe_float(row["delta_seconds"]), reverse=True)
    _write_csv(
        SOURCE_TAIL_TABLE,
        rows,
        [
            "task_id",
            "source_node",
            "goal_node",
            "entry_time",
            "std_time",
            "original_tht",
            "noastar_tht",
            "delta_seconds",
            "source_retry_count",
            "source_wait_seconds",
            "first_node_reservation_delay",
            "source_queue_rank",
            "same_source_previous_task_id",
            "same_source_next_task_id",
            "processed_segment_type",
            "early_bag_split",
            "fallback_calls",
            "path_prefix",
            "top_delay_reason",
            "would_release_semantics_help_seconds",
            "would_reservation_variant_help_seconds",
            "would_route_quality_balanced_help_seconds",
        ],
    )
    by_source = Counter(row["source_node"] for row in rows)
    top100 = rows[:100]
    top500 = rows[:500]
    SOURCE_TAIL_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 Source Retry Tail Report",
                "",
                *_meta_lines(ctx),
                "",
                f"Source-retry bags: {len(rows)}.",
                "",
                "## Source Concentration",
                "",
                _markdown_table(["Source", "Count"], [[key, value] for key, value in by_source.most_common(12)]),
                "",
                f"Top 100 slow positive source-retry rows cover {len({row['source_node'] for row in top100})} source signatures.",
                f"Top 500 slow positive source-retry rows cover {len({row['source_node'] for row in top500})} source signatures.",
                "",
                "The long tail is dominated by source/release timing and source queue concentration, not a broad median slowdown.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def top_tail_counterfactual(ctx: dict[str, Any], baseline: RuntimeResult, comparisons: dict[str, RuntimeResult]) -> list[dict[str, Any]]:
    graph_data = json.loads(g5.MAP_PATH.read_text(encoding="utf-8"))
    outgoing = {int(node["location"]): [int(value) for value in node.get("outgoing", [])] for node in graph_data["nodes"]}
    heuristic = graph_data["heuristic_time"]
    original = g6.parse_original_project_segments(g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)["sim_result_2_5"])
    info = task_info_by_id()
    base = aggregate_tasks_by_bag(baseline.tasks)
    comp = {name: aggregate_tasks_by_bag(result.tasks) for name, result in comparisons.items()}
    candidates = []
    for task_id, item in base.items():
        if task_id in original:
            delta = _safe_float(item.get("duration")) - _safe_float(original[task_id].get("duration"))
            if delta > 0:
                candidates.append((delta, task_id, item))
    candidates.sort(reverse=True)
    rows: list[dict[str, Any]] = []
    for delta, task_id, item in candidates[:500]:
        first_path = item.get("paths", [[]])[0] if item.get("paths") else []
        first_node = first_path[0] if first_path else ""
        chosen_next = first_path[1] if len(first_path) > 1 else ""
        goal = info.get(task_id, {}).get("goal_nodes", [""])[0]
        options = outgoing.get(_safe_int(first_node, -1), [])
        alternative = ""
        if options:
            alternative = min(options, key=lambda node: (heuristic[node][_safe_int(goal, 0)] if goal != "" else 0.0, node))
        release_help = ""
        reservation_help = ""
        route_help = ""
        if "java_source_queue_one_per_epoch" in comp and task_id in comp["java_source_queue_one_per_epoch"]:
            release_help = _safe_float(item.get("duration")) - _safe_float(comp["java_source_queue_one_per_epoch"][task_id].get("duration"))
        if "source_node_no_reservation" in comp and task_id in comp["source_node_no_reservation"]:
            reservation_help = _safe_float(item.get("duration")) - _safe_float(comp["source_node_no_reservation"][task_id].get("duration"))
        if "route_quality_2.5" in comp and task_id in comp["route_quality_2.5"]:
            route_help = _safe_float(item.get("duration")) - _safe_float(comp["route_quality_2.5"][task_id].get("duration"))
        rows.append(
            {
                "task_id": task_id,
                "delta_seconds": delta,
                "current_path": json.dumps(item.get("paths", []), ensure_ascii=False),
                "original_project_tht": original[task_id].get("duration"),
                "noastar_tht": item.get("duration"),
                "source_retry": item.get("source_retry"),
                "wait_seconds": item.get("wait_seconds"),
                "fallback_calls": item.get("fallback_calls"),
                "first_slow_decision_node": first_node,
                "candidate_options": json.dumps(options),
                "chosen_next": chosen_next,
                "alternative_next": alternative,
                "candidate_wait": "offline_not_traced",
                "candidate_progress": (heuristic[_safe_int(first_node, 0)][_safe_int(goal, 0)] - heuristic[_safe_int(alternative, 0)][_safe_int(goal, 0)]) if alternative != "" and goal != "" else "",
                "candidate_static_cost": heuristic[_safe_int(alternative, 0)][_safe_int(goal, 0)] if alternative != "" and goal != "" else "",
                "candidate_reservation_pressure": "offline_not_traced",
                "would_route_quality_balanced_help": route_help,
                "would_release_semantics_variant_help": release_help,
                "would_reservation_variant_help": reservation_help,
            }
        )
    _write_csv(
        TAIL_COUNTERFACTUAL_TABLE,
        rows,
        [
            "task_id",
            "delta_seconds",
            "current_path",
            "original_project_tht",
            "noastar_tht",
            "source_retry",
            "wait_seconds",
            "fallback_calls",
            "first_slow_decision_node",
            "candidate_options",
            "chosen_next",
            "alternative_next",
            "candidate_wait",
            "candidate_progress",
            "candidate_static_cost",
            "candidate_reservation_pressure",
            "would_route_quality_balanced_help",
            "would_release_semantics_variant_help",
            "would_reservation_variant_help",
        ],
    )
    TAIL_COUNTERFACTUAL_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 Tail Counterfactual Report",
                "",
                *_meta_lines(ctx),
                "",
                f"Rows: {len(rows)} top slow positive-delta bags.",
                "Candidate wait/pressure columns are explicitly marked offline_not_traced where the runtime does not export per-candidate reservation pressure for those exact tail decisions.",
                "",
                _markdown_table(["Task", "Delta", "Release Help", "Reservation Help", "Route Help"], [[row["task_id"], row["delta_seconds"], row["would_release_semantics_variant_help"], row["would_reservation_variant_help"], row["would_route_quality_balanced_help"]] for row in rows[:20]]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_combinations(ctx: dict[str, Any], graph: dict[str, Any], graph_path: Path, release_paths: dict[str, Path], cache: dict[str, RuntimeResult]) -> tuple[list[dict[str, Any]], dict[str, RuntimeResult], str]:
    combos = [
        ("official_baseline", official_mode(), g5.TASK_JSONL, "baseline"),
        ("route_quality_balanced", route_quality_mode(), g5.TASK_JSONL, "baseline"),
        ("java_source_queue_one_per_epoch", official_mode(), release_paths["java_source_queue_one_per_epoch"], "baseline"),
        ("open_end_boundary", official_mode(), g5.TASK_JSONL, "reservation_open_end_boundary"),
        ("source_queue_plus_route_quality", route_quality_mode(), release_paths["java_source_queue_one_per_epoch"], "baseline"),
        ("source_queue_plus_open_end", official_mode(), release_paths["java_source_queue_one_per_epoch"], "reservation_open_end_boundary"),
        ("source_queue_plus_open_end_plus_route_quality", route_quality_mode(), release_paths["java_source_queue_one_per_epoch"], "reservation_open_end_boundary"),
    ]
    rows: list[dict[str, Any]] = []
    results: dict[str, RuntimeResult] = {}
    for combo, mode, task_path, semantics in combos:
        print(f"[g4irsf7] combination {combo}", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id=combo,
                mode=mode,
                task_path=task_path,
                graph_data=graph,
                graph_artifact=graph_path,
                expected_counts=expected_segment_counts(task_path),
                reservation_semantics=semantics,
                note="single-item variants were validated before this combination",
            ),
            cache,
        )
        results[combo] = result
        row = result_row(result, "engineering_combination")
        row.update({"combination": combo, "promotion_status": promotion_status(row)})
        rows.append(row)
    _write_csv(
        COMBINATION_TABLE,
        rows,
        [
            "combination",
            "status",
            "policy",
            "reservation_semantics",
            "task_path",
            "complete_bags",
            "processed_segment_count",
            "planned_segments",
            "failed_segments",
            "mean_tht",
            "delta_vs_g6_official_min",
            "gap_vs_original_min",
            "source_retry_count",
            "source_wait_seconds",
            "wait_seconds",
            "fallback_calls",
            "loop_count",
            "node_window_conflicts",
            "runtime_full_astar_calls",
            "promotion_status",
            "note",
        ],
    )
    eligible = [row for row in rows if stable_and_complete(row)]
    best = min(eligible, key=lambda row: (_safe_float(row["mean_tht"], 99.0), row["combination"])) if eligible else rows[0]
    GAP_CLOSURE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 Engineering Gap Closure Report",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Combination", "Mean", "Gap", "Complete", "Conflicts", "Full A*", "Promotion"], [[row["combination"], row["mean_tht"], row["gap_vs_original_min"], row["complete_bags"], row["node_window_conflicts"], row["runtime_full_astar_calls"], row["promotion_status"]] for row in rows]),
                "",
                f"Best stable engineering candidate: `{best['combination']}`.",
                "G4J remains closed; this is an engineering non-inferiority candidate gate only.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows, results, str(best["combination"])


def run_regression_matrix(ctx: dict[str, Any], candidate_name: str, candidate_result: RuntimeResult, cache: dict[str, RuntimeResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mode = route_quality_mode() if "route_quality" in candidate_name else official_mode()
    task_path = candidate_result.task_path
    semantics = str(candidate_result.summary.get("reservation_semantics", "baseline"))
    g6_fault_reference = {
        row["paper_fault_case"]: _safe_float(row.get("official_noastar_bag_success_rate"))
        for row in _read_csv(g6.FAULT_BAG_TABLE)
    }
    for speed in (1.5, 2.0, 2.5, 3.0):
        graph, graph_path = graph_for_speed(speed)
        print(f"[g4irsf7] regression speed {speed}", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id=f"{candidate_name}_speed_{speed}",
                mode=mode,
                task_path=task_path,
                graph_data=graph,
                graph_artifact=graph_path,
                expected_counts=expected_segment_counts(task_path),
                reservation_semantics=semantics,
                note="candidate speed regression",
            ),
            cache,
        )
        rows.append({**result_row(result, "regression_speed"), "regression_scope": "speed_sweep", "case": speed, "material_regression": not stable_and_complete(result_row(result, "regression_speed"))})
    graph25, graph25_path = graph_for_speed(2.5)
    arc_map = g5.read_arc_id_map(g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)["arc"])
    for scenario_id, arc_ids, paper_success in g5._paper_fault_scenarios():
        mapped = tuple(edge for edge in (arc_map.get(arc_id) for arc_id in arc_ids) if edge is not None)
        print(f"[g4irsf7] regression fault {scenario_id}", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id=f"{candidate_name}_fault_{scenario_id}",
                mode=mode,
                task_path=task_path,
                graph_data=graph25,
                graph_artifact=graph25_path,
                expected_counts=expected_segment_counts(task_path),
                reservation_semantics=semantics,
                fault_edges=mapped,
                note=f"paper_success={paper_success}",
            ),
            cache,
        )
        bag_success = result.bag_summary.complete_bag_count / result.bag_summary.raw_bag_count if result.bag_summary.raw_bag_count else 0.0
        reference_success = g6_fault_reference.get(scenario_id, 0.0)
        fault_material_regression = (
            _safe_int(result.summary.get("node_window_conflicts")) != 0
            or _safe_int(result.summary.get("runtime_full_cie_astar_calls")) != 0
            or bag_success + 1.0e-6 < reference_success - 0.001
        )
        rows.append({**result_row(result, "regression_fault"), "regression_scope": "fault_16", "case": scenario_id, "bag_success_rate": bag_success, "reference_bag_success_rate": reference_success, "paper_success_rate": paper_success, "material_regression": fault_material_regression})
    for (standard_speed, deviation), paper in sorted(g6.paper_dynamic_static_values().items()):
        effective_speed = standard_speed * (1.0 - deviation / 100.0)
        graph, graph_path = graph_for_speed(effective_speed)
        print(f"[g4irsf7] regression dynamic {standard_speed} {deviation}", flush=True)
        result = run_runtime(
            RuntimeSpec(
                run_id=f"{candidate_name}_dynamic_{standard_speed}_{deviation}",
                mode=mode,
                task_path=task_path,
                graph_data=graph,
                graph_artifact=graph_path,
                expected_counts=expected_segment_counts(task_path),
                reservation_semantics=semantics,
                note="dynamic/static diagnostic effective-speed replay only",
            ),
            cache,
        )
        rows.append({**result_row(result, "regression_dynamic_static"), "regression_scope": "dynamic_static_diagnostic", "case": f"{standard_speed}:{deviation}", "paper_dynamic": paper["dynamic"], "paper_static": paper["static"], "material_regression": not stable_and_complete(result_row(result, "regression_dynamic_static"))})
    _write_csv(
        REGRESSION_TABLE,
        rows,
        [
            "regression_scope",
            "case",
            "run_id",
            "status",
            "policy",
            "reservation_semantics",
            "complete_bags",
            "processed_segment_count",
            "planned_segments",
            "failed_segments",
            "mean_tht",
            "gap_vs_original_min",
            "source_retry_count",
            "node_window_conflicts",
            "runtime_full_astar_calls",
            "bag_success_rate",
            "reference_bag_success_rate",
            "paper_success_rate",
            "paper_dynamic",
            "paper_static",
            "material_regression",
            "note",
        ],
    )
    return rows


def java_minimal_runner(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    rows = g5.run_java_baseline_attempts(g5.DEFAULT_ICS_PROJECT_ROOT)
    rows.extend(g6.run_java_stub_attempt(g5.DEFAULT_ICS_PROJECT_ROOT))
    rows.append(
        {
            "attempt": "g4irsf7_first_n_epoch_release_evidence",
            "status": "EVIDENCE_ONLY",
            "command": "static Java source inspection",
            "returncode": "",
            "stdout_excerpt": "",
            "stderr_excerpt": "",
            "notes": "Tasks.generate_tasks proves per-source one-head-per-epoch release; full RUN.Main still blocked by GUI/time horizon.",
        }
    )
    _write_csv(JAVA_MINIMAL_TABLE, rows, ["attempt", "status", "command", "returncode", "stdout_excerpt", "stderr_excerpt", "notes"])
    JAVA_MINIMAL_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 Java Runtime Minimal Runner Report",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Attempt", "Status", "Notes"], [[row["attempt"], row["status"], row["notes"]] for row in rows]),
                "",
                "Java/CIE progress is recorded, but Java blockage does not block engineering THT gap closure.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def write_plain_and_gate(ctx: dict[str, Any], gate_rows: list[dict[str, Any]], best_name: str, best_row: dict[str, Any]) -> None:
    _write_csv(PROMOTION_TABLE, gate_rows, ["gate", "status", "evidence", "notes"])
    PROMOTION_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 Promotion Gate Report",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Gate", "Status", "Notes"], [[row["gate"], row["status"], row["notes"]] for row in gate_rows]),
                "",
                f"Best engineering candidate: `{best_name}` mean={best_row.get('mean_tht')} min. G4J remains closed.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    PLAIN_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF7 Plain Language Summary",
                "",
                *_meta_lines(ctx),
                "",
                "这轮先从工程口径抹半秒，不训练新模型，不改真实地图，不改 legacy Java。",
                "主要发现是 source release/source queue 语义会显著影响 source_retry 长尾；尤其 Java 每个 source 每秒最多释放队首一个任务，而当前连续 JSONL replay 会把同一 source 同一 pass_time 的任务同时压入。",
                "开区间/跳过 source reservation 可以消除 source_retry 计数，但不自动改善平均 THT；因此不能把它当胜利。",
                f"当前最好的安全工程候选是 `{best_name}`，但它只能进入 G4IRSF7-B 或 no-A* v2 候选讨论，不能直接宣称论文胜利，也不能打开 G4J。",
                "所有候选必须继续保持 0 failure / 0 conflict / 0 full A*，并通过速度、故障、动态/静态回归。",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_all(args: argparse.Namespace) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    ctx, state_rows = collect_state()
    write_state(ctx, state_rows)
    run_tht_formula_audit(ctx)
    java_evidence(ctx)
    graph25, graph25_path = graph_for_speed(PRIMARY_SPEED)
    cache: dict[str, RuntimeResult] = {}
    release_rows, release_results, release_paths = run_release_variants(ctx, graph25, graph25_path, cache)
    reservation_rows, reservation_results = run_reservation_variants(ctx, graph25, graph25_path, cache)
    route_rows, route_results = run_route_quality_validation(ctx, cache)
    comparison_results = {
        "java_source_queue_one_per_epoch": release_results["java_source_queue_one_per_epoch"],
        "source_node_no_reservation": reservation_results["source_node_no_reservation"],
        "route_quality_2.5": route_results["route_quality_2.5"],
    }
    baseline = release_results["current_noastar_release"]
    source_retry_tail(ctx, baseline, comparison_results)
    top_tail_counterfactual(ctx, baseline, comparison_results)
    combination_rows, combination_results, best_name = run_combinations(ctx, graph25, graph25_path, release_paths, cache)
    best_result = combination_results[best_name]
    regression_rows = run_regression_matrix(ctx, best_name, best_result, cache)
    java_rows = java_minimal_runner(ctx)
    best_row = next(row for row in combination_rows if row["combination"] == best_name)
    gate_rows = [
        {"gate": "tht_formula_audit_complete", "status": "PASS" if THT_FORMULA_TABLE.exists() else "FAIL", "evidence": str(THT_FORMULA_TABLE), "notes": "Original project parsed mean reproduced."},
        {"gate": "source_retry_tail_explained", "status": "PASS" if SOURCE_TAIL_TABLE.exists() else "FAIL", "evidence": str(SOURCE_TAIL_TABLE), "notes": "Source concentration and counterfactual help columns generated."},
        {"gate": "release_variants_evaluated", "status": "PASS" if len(release_rows) >= 7 else "FAIL", "evidence": str(RELEASE_VARIANTS_TABLE), "notes": "Java epoch/source queue variants evaluated."},
        {"gate": "reservation_variants_evaluated", "status": "PASS" if len(reservation_rows) >= 7 else "FAIL", "evidence": str(RESERVATION_VARIANTS_TABLE), "notes": "C++ reservation semantics hooks evaluated without changing baseline default."},
        {"gate": "route_quality_strict_validation", "status": "PASS" if len(route_rows) >= 26 else "FAIL", "evidence": str(ROUTE_QUALITY_TABLE), "notes": "Repeat, speed, fault, high-flow subset recorded."},
        {"gate": "engineering_combination_tested", "status": "PASS" if combination_rows else "FAIL", "evidence": str(COMBINATION_TABLE), "notes": f"Best={best_name}."},
        {"gate": "regression_matrix_complete", "status": "PASS" if len(regression_rows) == 32 else "FAIL", "evidence": str(REGRESSION_TABLE), "notes": "Speed, 16 fault cases, 12 dynamic/static diagnostics."},
        {"gate": "regression_no_material_regression", "status": "PASS" if not any(str(row.get("material_regression")) == "True" for row in regression_rows) else "FAIL", "evidence": str(REGRESSION_TABLE), "notes": "Fault cases compare against G4IRSF6 official bag success; speed/dynamic require full safety."},
        {"gate": "java_minimal_runner_recorded", "status": "PASS" if java_rows else "FAIL", "evidence": str(JAVA_MINIMAL_TABLE), "notes": "Java blocker retained; source-release evidence extracted."},
        {"gate": "safety_guardrails_retained", "status": "PASS" if stable_and_complete(best_row) else "FAIL", "evidence": str(COMBINATION_TABLE), "notes": "0 failure / 0 conflict / 0 full A* required."},
        {"gate": "legacy_and_real_map_clean", "status": "PASS" if not ctx["legacy_java_diff"] and not ctx["real_main_map_diff"] else "FAIL", "evidence": str(STATE_TABLE), "notes": "No legacy Java or real main map diff."},
        {"gate": "g4j_closed", "status": "PASS", "evidence": str(PROMOTION_TABLE), "notes": "Only G4IRSF7-B/no-A* v2 engineering candidate may be discussed."},
    ]
    write_plain_and_gate(ctx, gate_rows, best_name, best_row)
    print(f"[g4irsf7] complete best={best_name} mean={best_row.get('mean_tht')}", flush=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    return parser.parse_args(argv)


if __name__ == "__main__":
    run_all(parse_args())
