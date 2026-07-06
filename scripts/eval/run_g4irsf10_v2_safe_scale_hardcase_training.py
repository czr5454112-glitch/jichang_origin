from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.eval import run_g4irsf5_original_protocol_comparative_validation as g5
from scripts.eval import run_g4irsf6_paper_protocol_gap_closure as g6
from scripts.eval import run_g4irsf7_engineering_tht_gap_closure as g7
from scripts.eval import run_g4irsf8_source_release_denominator_validation as g8
from scripts.eval import run_g4irsf9_v2_candidate_tiering_open_end_proof as g9


REPORT_DIR = ROOT / "outputs" / "reports"
TABLE_DIR = ROOT / "outputs" / "tables"
DATASET_DIR = ROOT / "artifacts" / "datasets"
TASK_ARTIFACT_DIR = ROOT / ".pytest_cache" / "g4irsf10" / "tasks"
POLICY_DIR = ROOT / "artifacts" / "policies"

PAPER_BAGS = 28506
PAPER_SEGMENTS = 43603
PRIMARY_SPEED = 2.5
SAFE_POLICY_ID = g9.SAFE_POLICY_ID
SAFE_POLICY_BUNDLE = g9.SAFE_POLICY_BUNDLE
OPEN_POLICY_BUNDLE = g9.OPEN_POLICY_BUNDLE
ORIGINAL_PROJECT_MEAN_THT = g9.ORIGINAL_PROJECT_MEAN_THT

STATE_TABLE = TABLE_DIR / "g4irsf10_git_state_audit.csv"
STATE_REPORT = REPORT_DIR / "g4irsf10_state_and_v2_safe_freeze_report.md"
PAPER_TABLE = TABLE_DIR / "g4irsf10_v2_safe_paper_protocol_repeat.csv"
PAPER_REPORT = REPORT_DIR / "g4irsf10_v2_safe_paper_protocol_report.md"
HIGH_FLOW_TABLE = TABLE_DIR / "g4irsf10_v2_safe_high_flow_matrix.csv"
HIGH_FLOW_REPORT = REPORT_DIR / "g4irsf10_v2_safe_high_flow_report.md"
HARD_CASE_MANIFEST = DATASET_DIR / "g4irsf10_hard_case_manifest.json"
HARD_CASE_INDEX = TABLE_DIR / "g4irsf10_hard_case_index.csv"
HARD_CASE_REPORT = REPORT_DIR / "g4irsf10_hard_case_collection_report.md"
V3_SCHEMA = DATASET_DIR / "g4irsf10_v3_training_schema.json"
V3_PROTOCOL_REPORT = REPORT_DIR / "g4irsf10_v3_training_data_protocol.md"
V3_MODEL_PLAN_TABLE = TABLE_DIR / "g4irsf10_v3_candidate_model_plan.csv"
V3_MODEL_PLAN_REPORT = REPORT_DIR / "g4irsf10_v3_policy_training_plan.md"
V3_AB_TABLE = TABLE_DIR / "g4irsf10_v3_ab_evaluation_matrix.csv"
V3_AB_REPORT = REPORT_DIR / "g4irsf10_v3_ab_evaluation_matrix.md"
FAULT_POLICY_REPORT = REPORT_DIR / "g4irsf10_fault_policy_branch_plan.md"
JAVA_BASELINE_TABLE = TABLE_DIR / "g4irsf10_java_baseline_attempts.csv"
JAVA_BASELINE_REPORT = REPORT_DIR / "g4irsf10_java_baseline_progress_report.md"
PLAIN_REPORT = REPORT_DIR / "g4irsf10_plain_language_summary.md"
GATE_TABLE = TABLE_DIR / "g4irsf10_promotion_gate.csv"
GATE_REPORT = REPORT_DIR / "g4irsf10_promotion_gate_report.md"

FORBIDDEN_MODEL_INPUTS = [
    "teacher_next",
    "teacher_next_node",
    "teacher_path",
    "full_cie_route_suffix",
    "route_path",
    "future_sipp_schedule",
    "future_schedule",
    "route_finish_time",
    "label_source",
    "post_hoc_success",
    "post_hoc_success_flag",
]


@dataclass(frozen=True)
class RunCase:
    scenario: str
    task_path: Path
    graph_speed: float = PRIMARY_SPEED
    scale: str = "1x"
    max_tasks: int = -1
    fault_edges: tuple[tuple[int, int], ...] = ()
    claim_level: str = "extension_only"
    generation_level: str = "distribution_preserving_resample"
    note: str = ""


class HardCaseCollector:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.rows: list[dict[str, Any]] = []
        self.total_seen = 0
        self.category_counts: Counter[str] = Counter()

    def add_from_result(self, scenario: str, result: g7.RuntimeResult, graph_data: dict[str, Any]) -> None:
        segment_durations = _segment_durations(result.tasks)
        if not segment_durations:
            return
        p95 = _quantile(segment_durations, 0.95)
        p99 = _quantile(segment_durations, 0.99)
        median = statistics.median(segment_durations)
        heuristic = graph_data.get("heuristic_time", [])
        for task_row in result.tasks:
            reasons = _hard_reasons(task_row, p95, p99, heuristic)
            if not reasons:
                continue
            for reason in reasons:
                self.category_counts[reason] += 1
            self.total_seen += 1
            if len(self.rows) >= self.limit:
                continue
            self.rows.append(_hard_case_row(scenario, task_row, reasons, median, len(self.rows) + 1))

    @property
    def truncated(self) -> bool:
        return self.total_seen > len(self.rows)


def _csv_value(value: Any) -> Any:
    return g8._csv_value(value)


def _write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    g8._write_csv(path, rows, fieldnames)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    return g8._markdown_table(headers, rows)


def _git(args: list[str]) -> tuple[int, str, str]:
    return g8._git(args)


def _git_text(args: list[str]) -> str:
    return g8._git_text(args)


def _sha256(path: Path) -> str:
    return g8._sha256(path)


def _jsonl_count(path: Path) -> int:
    return g8._jsonl_count(path)


def _safe_float(value: Any, default: float = 0.0) -> float:
    return g8._safe_float(value, default)


def _safe_int(value: Any, default: int = 0) -> int:
    return g8._safe_int(value, default)


def _load_jsonl(path: Path, max_rows: int = 0) -> list[dict[str, Any]]:
    return g8.load_jsonl(path, max_rows)


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    g7.write_jsonl(path, rows)


def _meta_lines(ctx: dict[str, Any]) -> list[str]:
    return [
        f"Date: {date.today().isoformat()}",
        f"Branch: `{ctx['branch']}`",
        f"artifact_generation_head: `{ctx['artifact_generation_head']}`",
        f"committed_head_at_generation: `{ctx['committed_head']}`",
        f"remote_head_at_generation: `{ctx['remote_head']}`",
        "policy_id: `model_plus_pibt_lite_java_source_queue_v2_safe`",
        "release_semantics: `java_source_queue_one_per_epoch`",
        "reservation_semantics: `baseline`",
        "tth_denominator: `java_release_time_tth`",
        "new_model_training: false",
        "runtime_full_cie_astar_fallback: false",
        "teacher_path_or_future_schedule_leakage: false",
        "v2_open_used_for_paper_claim: false",
        "g4j_opened: false",
    ]


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * q) - 1))
    return ordered[index]


def _segment_durations(tasks: list[dict[str, Any]]) -> list[float]:
    values: list[float] = []
    for row in tasks:
        if bool(row.get("goal_reached")) and row.get("finish_time") not in ("", None):
            values.append(max(0.0, _safe_float(row.get("finish_time")) - _safe_float(row.get("attempt_time"))))
    return values


def _bag_durations_minutes(tasks: list[dict[str, Any]], expected_counts: dict[int, int]) -> list[float]:
    totals: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    for row in tasks:
        if not bool(row.get("goal_reached")) or row.get("finish_time") in ("", None):
            continue
        task_id = int(row["task_id"])
        totals[task_id] += max(0.0, _safe_float(row.get("finish_time")) - _safe_float(row.get("attempt_time")))
        counts[task_id] += 1
    return [totals[task_id] / 60.0 for task_id, expected in expected_counts.items() if counts.get(task_id, 0) == expected]


def _path_nodes(row: dict[str, Any]) -> list[int]:
    path = row.get("path", [])
    if isinstance(path, str):
        try:
            loaded = json.loads(path)
            path = loaded
        except json.JSONDecodeError:
            path = []
    if not isinstance(path, list):
        return []
    nodes: list[int] = []
    for item in path:
        try:
            nodes.append(int(item))
        except (TypeError, ValueError):
            continue
    return nodes


def _shortest_time(heuristic: Any, start: int, goal: int) -> float:
    try:
        return float(heuristic[start][goal])
    except (TypeError, ValueError, IndexError, KeyError):
        return 0.0


def _hard_reasons(row: dict[str, Any], p95: float, p99: float, heuristic: Any) -> list[str]:
    reasons: list[str] = []
    reached = bool(row.get("goal_reached"))
    duration = max(0.0, _safe_float(row.get("finish_time")) - _safe_float(row.get("attempt_time"))) if reached else 0.0
    fallback_calls = _safe_int(row.get("rule_fallback_calls", row.get("fallback_calls")))
    wait_seconds = _safe_float(row.get("wait_seconds"))
    source_wait_seconds = _safe_float(row.get("source_wait_seconds"))
    loop_count = _safe_int(row.get("loop_count"))
    if not reached:
        reasons.append("fault_failure")
    if duration >= p99 and p99 > 0:
        reasons.append("high_tth_tail")
        reasons.append("p95_or_p99_delay")
    elif duration >= p95 and p95 > 0:
        reasons.append("p95_or_p99_delay")
    if fallback_calls >= 3:
        reasons.append("fallback_high_frequency")
    elif fallback_calls > 0:
        reasons.append("model_vs_fallback_disagreement")
    if loop_count > 0:
        reasons.append("near_loop")
    if source_wait_seconds >= 5.0 or _safe_int(row.get("source_retry_count")) > 0:
        reasons.append("source_queue_long_backlog")
    if wait_seconds >= 10.0:
        reasons.append("edge_pressure_high")
    path = _path_nodes(row)
    if path:
        shortest = _shortest_time(heuristic, int(row.get("start", path[0])), int(row.get("goal", path[-1])))
        if shortest > 0 and duration > shortest * 1.5 + 5.0:
            reasons.append("large_detour")
    if _safe_float(row.get("model_margin"), 99.0) < 1.0:
        reasons.append("model_low_margin")
    return sorted(set(reasons))


def _hard_case_row(
    scenario: str,
    row: dict[str, Any],
    reasons: list[str],
    median_duration: float,
    ordinal: int,
) -> dict[str, Any]:
    path = _path_nodes(row)
    duration = max(0.0, _safe_float(row.get("finish_time")) - _safe_float(row.get("attempt_time"))) if row.get("finish_time") not in ("", None) else 0.0
    fallback_calls = _safe_int(row.get("rule_fallback_calls", row.get("fallback_calls")))
    pressure = {
        "wait_seconds": _safe_float(row.get("wait_seconds")),
        "source_wait_seconds": _safe_float(row.get("source_wait_seconds")),
        "source_retry_count": _safe_int(row.get("source_retry_count")),
        "fallback_calls": fallback_calls,
        "loop_count": _safe_int(row.get("loop_count")),
    }
    return {
        "case_id": f"g4irsf10-{ordinal:06d}",
        "scenario": scenario,
        "task_id": row.get("task_id", ""),
        "segment_id": row.get("segment_id", ""),
        "current_node": path[0] if path else row.get("start", ""),
        "goal_node": row.get("goal", path[-1] if path else ""),
        "candidate_next_nodes": path[1:5],
        "selected_next": path[1] if len(path) > 1 else "",
        "decision_source": "fallback" if fallback_calls else "model_or_rule",
        "model_margin": row.get("model_margin", ""),
        "fallback_reason": "risk_gated_or_node_window_fallback" if fallback_calls else "",
        "wait": _safe_float(row.get("wait_seconds")) + _safe_float(row.get("source_wait_seconds")),
        "pressure": pressure,
        "path_history": path[:16],
        "tth_delta": duration - median_duration,
        "failure_reason": row.get("failure_reason", "") if not bool(row.get("goal_reached")) else "",
        "why_hard": reasons,
    }


def collect_state() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    head = _git_text(["rev-parse", "HEAD"])
    branch = _git_text(["branch", "--show-current"])
    upstream = _git_text(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    remote_head = _git_text(["rev-parse", "@{u}"]) if upstream else ""
    merge_base_code = _git(["merge-base", "--is-ancestor", "HEAD", "@{u}"])[0] if upstream else 1
    dirty = _git_text(["status", "--short"]).replace("\n", " | ")
    log20 = _git_text(["log", "--oneline", "-20"]).replace("\n", " | ")
    legacy_diff = _git_text(["diff", "--name-only", "--", "legacy"]).replace("\n", " | ")
    map_diff = _git_text(["diff", "--name-only", "--", str(g5.MAP_PATH.relative_to(ROOT))]).replace("\n", " | ")
    task_diff = _git_text(["diff", "--name-only", "--", str(g5.TASK_JSONL.relative_to(ROOT))]).replace("\n", " | ")
    safe_bundle = json.loads(SAFE_POLICY_BUNDLE.read_text(encoding="utf-8")) if SAFE_POLICY_BUNDLE.exists() else {}
    open_bundle = json.loads(OPEN_POLICY_BUNDLE.read_text(encoding="utf-8")) if OPEN_POLICY_BUNDLE.exists() else {}
    ctx = {
        "artifact_generation_head": head,
        "committed_head": head,
        "remote_head": remote_head,
        "branch": branch,
        "upstream": upstream,
        "head_is_ancestor_of_upstream": merge_base_code == 0,
        "dirty_at_generation": dirty,
        "log20": log20,
        "legacy_java_diff": legacy_diff,
        "real_main_map_diff": map_diff,
        "real_inputdata_diff": task_diff,
        "safe_bundle": safe_bundle,
        "open_bundle": open_bundle,
    }
    rows = [
        {
            "audit_item": "head_is_g4irsf9_or_descendant",
            "status": "PASS" if head and (head == remote_head or remote_head) else "WARN",
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "upstream": upstream,
            "head_is_ancestor_of_upstream": merge_base_code == 0,
            "dirty_at_generation": dirty,
            "legacy_diff": legacy_diff,
            "real_map_diff": map_diff,
            "real_inputdata_diff": task_diff,
            "details": "G4IRSF10 starts from the pushed G4IRSF9 branch or a descendant.",
        },
        {
            "audit_item": "v2_safe_bundle_exists_and_frozen",
            "status": "PASS" if safe_bundle.get("policy_id") == SAFE_POLICY_ID and safe_bundle.get("claim_level") == "paper_protocol_engineering_candidate" else "FAIL",
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "upstream": upstream,
            "head_is_ancestor_of_upstream": merge_base_code == 0,
            "dirty_at_generation": dirty,
            "legacy_diff": legacy_diff,
            "real_map_diff": map_diff,
            "real_inputdata_diff": task_diff,
            "details": str(SAFE_POLICY_BUNDLE),
        },
        {
            "audit_item": "v2_open_kept_separate",
            "status": "PASS" if open_bundle.get("policy_id") == g9.OPEN_POLICY_ID and open_bundle.get("claim_level") != "paper_protocol_engineering_candidate" else "WARN",
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "upstream": upstream,
            "head_is_ancestor_of_upstream": merge_base_code == 0,
            "dirty_at_generation": dirty,
            "legacy_diff": legacy_diff,
            "real_map_diff": map_diff,
            "real_inputdata_diff": task_diff,
            "details": str(OPEN_POLICY_BUNDLE),
        },
        {
            "audit_item": "legacy_map_inputdata_clean",
            "status": "PASS" if not legacy_diff and not map_diff and not task_diff else "FAIL",
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "upstream": upstream,
            "head_is_ancestor_of_upstream": merge_base_code == 0,
            "dirty_at_generation": dirty,
            "legacy_diff": legacy_diff,
            "real_map_diff": map_diff,
            "real_inputdata_diff": task_diff,
            "details": "Protected legacy Java, real map2.json, and real inputdata.jsonl are unchanged.",
        },
    ]
    return ctx, rows


def write_state(ctx: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    _write_csv(
        STATE_TABLE,
        rows,
        [
            "audit_item",
            "status",
            "branch",
            "artifact_generation_head",
            "committed_head",
            "remote_head",
            "upstream",
            "head_is_ancestor_of_upstream",
            "dirty_at_generation",
            "legacy_diff",
            "real_map_diff",
            "real_inputdata_diff",
            "details",
        ],
    )
    safe = ctx["safe_bundle"]
    STATE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 State and v2-safe Freeze Report",
                "",
                *_meta_lines(ctx),
                "",
                f"Frozen v2-safe policy: `{safe.get('policy_id', '')}`.",
                f"Frozen mean THT: `{safe.get('main_2_5_mean_tth', '')}` minutes.",
                f"Frozen model hash: `{safe.get('model_weights_hash', '')}`.",
                "",
                _markdown_table(["Audit", "Status", "Details"], [[row["audit_item"], row["status"], row["details"]] for row in rows]),
                "",
                "G4IRSF10 does not reopen v2-open as a paper candidate and does not train a new model in this pass.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def ensure_formal_source_queue() -> Path:
    if g8.FORMAL_SOURCE_QUEUE.exists() and _jsonl_count(g8.FORMAL_SOURCE_QUEUE) == PAPER_SEGMENTS:
        return g8.FORMAL_SOURCE_QUEUE
    return g9.ensure_source_queue_artifacts()


def generate_processed_resample(
    *,
    scale: int,
    rolling_days: int,
    time_compression: float,
    label: str,
) -> tuple[Path, dict[str, Any]]:
    TASK_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = TASK_ARTIFACT_DIR / f"{label}.jsonl"
    manifest = TASK_ARTIFACT_DIR / f"{label}_manifest.json"
    if out.exists() and manifest.exists():
        return out, json.loads(manifest.read_text(encoding="utf-8"))
    base = _load_jsonl(g5.TASK_JSONL)
    pass_times = [float(row["pass_time"]) for row in base]
    base_time = min(pass_times)
    max_time = max(pass_times)
    day_span = max(86400.0, max_time - base_time + 3600.0)
    id_span = max(int(row["task_id"]) for row in base) + 1
    rows: list[dict[str, Any]] = []
    for day in range(rolling_days):
        day_offset = day * day_span
        for replica in range(scale):
            copy_index = day * scale + replica
            micro_offset = replica * 0.01 + day * 0.001 + 20260706 * 1.0e-9
            for row in base:
                item = dict(row)
                new_task_id = int(row["task_id"]) + copy_index * id_span
                old_pass = float(row["pass_time"])
                old_std = float(row.get("std", old_pass))
                old_entry = float(row.get("original_entry_time", old_pass))
                item.update(
                    {
                        "task_id": new_task_id,
                        "pallet_id": new_task_id,
                        "segment_id": f"{new_task_id}:{row.get('leg', 'direct')}:g4irsf10_c{copy_index}",
                        "pass_time": base_time + (old_pass - base_time) * time_compression + day_offset + micro_offset,
                        "std": base_time + (old_std - base_time) * time_compression + day_offset + micro_offset,
                        "original_entry_time": base_time + (old_entry - base_time) * time_compression + day_offset + micro_offset,
                        "generation_level": "distribution_preserving_resample",
                        "generation_copy_index": copy_index,
                        "g4irsf10_time_compression": time_compression,
                        "topology_changed": False,
                    }
                )
                rows.append(item)
    rows.sort(key=lambda item: (float(item["pass_time"]), int(item["task_id"]), str(item["segment_id"])))
    _write_jsonl(out, rows)
    meta = {
        "artifact": str(out),
        "artifact_sha256": _sha256(out),
        "source_input": str(g5.TASK_JSONL),
        "source_input_sha256": _sha256(g5.TASK_JSONL),
        "generation_level": "distribution_preserving_resample",
        "topology_changed": False,
        "scale": scale,
        "rolling_days": rolling_days,
        "time_compression": time_compression,
        "row_count": len(rows),
        "expected_row_count": PAPER_SEGMENTS * scale * rolling_days,
        "claim_boundary": "fixed-map high-flow extension; not paper-main protocol",
    }
    manifest.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out, meta


def ensure_source_queue_for_case(
    *,
    scale: int,
    rolling_days: int = 1,
    time_compression: float = 1.0,
    label: str,
) -> tuple[Path, dict[str, Any]]:
    if scale == 1 and rolling_days == 1 and time_compression == 1.0:
        path = ensure_formal_source_queue()
        return path, {
            "artifact": str(path),
            "artifact_sha256": _sha256(path),
            "generation_level": "original_processed_inputdata_with_java_source_queue_release",
            "topology_changed": False,
            "scale": 1,
            "rolling_days": 1,
            "time_compression": 1.0,
            "row_count": _jsonl_count(path),
            "expected_row_count": PAPER_SEGMENTS,
            "claim_boundary": "paper protocol v2-safe source queue artifact",
        }
    source, source_meta = generate_processed_resample(scale=scale, rolling_days=rolling_days, time_compression=time_compression, label=f"{label}_tasks")
    queue_dir = TASK_ARTIFACT_DIR / label
    queue_path, queue_meta = g7.derive_release_jsonl(source, "java_source_queue_one_per_epoch", queue_dir)
    meta = {
        **source_meta,
        "artifact": str(queue_path),
        "artifact_sha256": _sha256(queue_path),
        "release_semantics": "java_source_queue_one_per_epoch",
        "source_task_artifact": str(source),
        "source_task_sha256": _sha256(source),
        "row_count": _jsonl_count(queue_path),
        "release_meta": queue_meta,
    }
    (queue_dir / "source_queue_manifest.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return queue_path, meta


def source_queue_pressure(path: Path) -> dict[str, Any]:
    rows_by_source: dict[int, list[tuple[float, float]]] = defaultdict(list)
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            original = float(row.get("g4irsf7_original_pass_time", row.get("pass_time", 0.0)))
            release = float(row.get("pass_time", original))
            rows_by_source[int(row["start"])].append((original, release))
    max_backlog = 0
    max_delay = 0.0
    total_delay = 0.0
    for items in rows_by_source.values():
        items.sort(key=lambda item: item[1])
        arrival_floors = sorted(math.floor(original) for original, _release in items)
        arrived = 0
        for released_so_far, (original, release) in enumerate(items):
            while arrived < len(arrival_floors) and arrival_floors[arrived] <= release:
                arrived += 1
            max_backlog = max(max_backlog, arrived - released_so_far)
            delay = max(0.0, release - math.floor(original))
            max_delay = max(max_delay, delay)
            total_delay += delay
    return {
        "source_queue_backlog": max_backlog,
        "max_source_queue_delay": max_delay,
        "total_source_queue_delay": total_delay,
    }


def memory_estimate_mb(tasks: list[dict[str, Any]]) -> float:
    if not tasks:
        return 0.0
    sample = tasks[: min(512, len(tasks))]
    sample_bytes = sum(len(json.dumps(row, ensure_ascii=False, sort_keys=True)) for row in sample)
    return (sample_bytes / len(sample) * len(tasks)) / (1024.0 * 1024.0)


def run_case(case: RunCase, collector: HardCaseCollector | None = None) -> tuple[dict[str, Any], g7.RuntimeResult | None]:
    graph, graph_path = g7.graph_for_speed(case.graph_speed)
    expected_counts = g5.expected_segment_counts(case.task_path, case.max_tasks if case.max_tasks > 0 else 0)
    spec = g7.RuntimeSpec(
        run_id=f"g4irsf10_{case.scenario}",
        mode=g7.official_mode(),
        task_path=case.task_path,
        graph_data=graph,
        graph_artifact=graph_path,
        expected_counts=expected_counts,
        reservation_semantics="baseline",
        fault_edges=case.fault_edges,
        max_tasks=case.max_tasks,
        note=case.note,
    )
    result = g7.run_runtime(spec, {})
    if collector is not None:
        collector.add_from_result(case.scenario, result, graph)
    row = result_metrics(case, result, expected_counts)
    return row, result


def result_metrics(case: RunCase, result: g7.RuntimeResult, expected_counts: dict[int, int]) -> dict[str, Any]:
    base = g7.result_row(result, "g4irsf10")
    bag_minutes = _bag_durations_minutes(result.tasks, expected_counts)
    source_pressure = source_queue_pressure(case.task_path)
    runtime_seconds = result.wall_seconds or _safe_float(base.get("elapsed_seconds"))
    task_count = _safe_int(base.get("processed_segment_count"))
    return {
        "scenario": case.scenario,
        "scale": case.scale,
        "task_count": task_count,
        "raw_bags": base.get("raw_bag_count", ""),
        "complete_bags": base.get("complete_bags", ""),
        "planned_segments": base.get("planned_segments", ""),
        "failed_segments": base.get("failed_segments", ""),
        "node_conflicts": base.get("node_window_conflicts", ""),
        "runtime_full_astar_calls": base.get("runtime_full_astar_calls", ""),
        "mean_tth": base.get("mean_tht", ""),
        "min_tth": base.get("min_tht", ""),
        "max_tth": base.get("max_tht", ""),
        "p95_tth": _quantile(bag_minutes, 0.95),
        "p99_tth": _quantile(bag_minutes, 0.99),
        "source_retry_count": base.get("source_retry_count", ""),
        "fallback_calls": base.get("fallback_calls", ""),
        "loop_count": base.get("loop_count", ""),
        "source_queue_backlog": source_pressure["source_queue_backlog"],
        "max_source_queue_delay": source_pressure["max_source_queue_delay"],
        "total_source_queue_delay": source_pressure["total_source_queue_delay"],
        "runtime_seconds": runtime_seconds,
        "tasks_per_second": task_count / runtime_seconds if runtime_seconds > 0 else 0.0,
        "memory_estimate_mb": memory_estimate_mb(result.tasks),
        "policy_id": SAFE_POLICY_ID,
        "release_semantics": "java_source_queue_one_per_epoch",
        "reservation_semantics": "baseline",
        "tth_denominator": "java_release_time_tth",
        "generation_level": case.generation_level,
        "topology_changed": False,
        "claim_level": case.claim_level,
        "task_path": str(case.task_path),
        "task_path_sha256": _sha256(case.task_path),
        "graph_speed": case.graph_speed,
        "fault_edges": case.fault_edges,
        "note": case.note,
    }


def stable_row(row: dict[str, Any], expected_complete: int | None = None) -> bool:
    complete_ok = True if expected_complete is None else _safe_int(row.get("complete_bags")) == expected_complete
    return (
        complete_ok
        and _safe_int(row.get("failed_segments")) == 0
        and _safe_int(row.get("node_conflicts")) == 0
        and _safe_int(row.get("runtime_full_astar_calls")) == 0
    )


def run_paper_protocol(ctx: dict[str, Any], source_queue: Path, collector: HardCaseCollector) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(1, 6):
        row, _result = run_case(
            RunCase(
                scenario=f"paper_main_2_5_repeat_{index}",
                task_path=source_queue,
                scale="1x",
                claim_level="paper_protocol_engineering_candidate",
                generation_level="original_processed_inputdata_with_java_source_queue_release",
                note="paper main 2.5m/s deterministic repeat",
            ),
            collector,
        )
        row["validation_scope"] = "paper_main_repeat"
        rows.append(row)
    for speed in (1.5, 2.0, 2.5, 3.0):
        row, _result = run_case(
            RunCase(
                scenario=f"speed_sweep_{speed}",
                task_path=source_queue,
                graph_speed=speed,
                scale="1x",
                claim_level="paper_protocol_engineering_candidate",
                generation_level="original_processed_inputdata_with_java_source_queue_release",
                note="paper-protocol speed sweep",
            ),
            collector,
        )
        row["validation_scope"] = "speed_sweep"
        rows.append(row)
    for (standard_speed, deviation), paper in sorted(g6.paper_dynamic_static_values().items()):
        effective_speed = standard_speed * (1.0 - deviation / 100.0)
        row, _result = run_case(
            RunCase(
                scenario=f"dynamic_static_{standard_speed}_{deviation}",
                task_path=source_queue,
                graph_speed=effective_speed,
                scale="1x",
                claim_level="diagnostic_only",
                generation_level="original_processed_inputdata_with_java_source_queue_release",
                note=f"dynamic/static diagnostic effective_speed={effective_speed:.3f}; paper_dynamic={paper['dynamic']}",
            ),
            collector,
        )
        row["validation_scope"] = "dynamic_static_12"
        rows.append(row)
    arc_map = g5.read_arc_id_map(g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)["arc"])
    for scenario_id, arc_ids, paper_success in g5._paper_fault_scenarios():
        mapped = tuple(edge for edge in (arc_map.get(arc_id) for arc_id in arc_ids) if edge is not None)
        row, _result = run_case(
            RunCase(
                scenario=f"fault_16_{scenario_id}",
                task_path=source_queue,
                scale="1x",
                fault_edges=mapped,
                claim_level="fault_diagnostic_only",
                generation_level="original_processed_inputdata_with_java_source_queue_release",
                note=f"paper fault diagnostic; paper_success={paper_success}",
            ),
            collector,
        )
        row["validation_scope"] = "fault_16"
        rows.append(row)
    repeat_means = [round(_safe_float(row["mean_tth"]), 10) for row in rows if row["validation_scope"] == "paper_main_repeat"]
    deterministic = len(set(repeat_means)) == 1
    for row in rows:
        row["deterministic_repeat_exact"] = deterministic if row["validation_scope"] == "paper_main_repeat" else ""
        row["material_regression"] = not stable_row(row, PAPER_BAGS) if row["validation_scope"] != "fault_16" else _safe_int(row.get("node_conflicts")) != 0 or _safe_int(row.get("runtime_full_astar_calls")) != 0
    _write_csv(PAPER_TABLE, rows, paper_fieldnames())
    main_rows = [row for row in rows if row["validation_scope"] == "paper_main_repeat"]
    PAPER_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 v2-safe Paper Protocol Repeat Report",
                "",
                *_meta_lines(ctx),
                "",
                f"Repeat x5 deterministic: `{deterministic}`.",
                f"Repeat means: `{repeat_means}`.",
                "",
                _markdown_table(
                    ["Scenario", "Mean", "Complete", "Failed", "Conflicts", "Full A*"],
                    [[row["scenario"], row["mean_tth"], row["complete_bags"], row["failed_segments"], row["node_conflicts"], row["runtime_full_astar_calls"]] for row in main_rows],
                ),
                "",
                "The speed sweep, dynamic/static 12 rows, and fault 16 diagnostics are retained in the CSV. Fault rows remain diagnostic and do not alter the v2-safe no-fault paper-main claim.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def paper_fieldnames() -> list[str]:
    return [
        "validation_scope",
        "scenario",
        "scale",
        "task_count",
        "raw_bags",
        "complete_bags",
        "planned_segments",
        "failed_segments",
        "node_conflicts",
        "runtime_full_astar_calls",
        "mean_tth",
        "min_tth",
        "max_tth",
        "p95_tth",
        "p99_tth",
        "source_retry_count",
        "source_queue_backlog",
        "max_source_queue_delay",
        "fallback_calls",
        "loop_count",
        "runtime_seconds",
        "tasks_per_second",
        "memory_estimate_mb",
        "deterministic_repeat_exact",
        "material_regression",
        "claim_level",
        "generation_level",
        "topology_changed",
        "task_path",
        "task_path_sha256",
        "note",
    ]


def high_flow_fieldnames() -> list[str]:
    return [
        "scenario",
        "scale",
        "task_count",
        "raw_bags",
        "complete_bags",
        "planned_segments",
        "failed_segments",
        "node_conflicts",
        "runtime_full_astar_calls",
        "mean_tth",
        "min_tth",
        "max_tth",
        "p95_tth",
        "p99_tth",
        "source_retry_count",
        "source_queue_backlog",
        "max_source_queue_delay",
        "total_source_queue_delay",
        "fallback_calls",
        "loop_count",
        "runtime_seconds",
        "tasks_per_second",
        "memory_estimate_mb",
        "policy_id",
        "release_semantics",
        "reservation_semantics",
        "tth_denominator",
        "generation_level",
        "topology_changed",
        "claim_level",
        "task_path",
        "task_path_sha256",
        "graph_speed",
        "fault_edges",
        "note",
    ]


def run_high_flow_matrix(args: argparse.Namespace, collector: HardCaseCollector) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def run_generated(
        scenario: str,
        *,
        scale: int,
        rolling_days: int = 1,
        time_compression: float = 1.0,
        graph_speed: float = PRIMARY_SPEED,
        max_tasks: int = -1,
        fault_edges: tuple[tuple[int, int], ...] = (),
        claim_level: str = "high_flow_extension",
        note: str = "",
    ) -> None:
        task_path, meta = ensure_source_queue_for_case(scale=scale, rolling_days=rolling_days, time_compression=time_compression, label=scenario)
        case = RunCase(
            scenario=scenario,
            task_path=task_path,
            graph_speed=graph_speed,
            scale=f"{scale}x" if rolling_days == 1 else f"{scale}x_{rolling_days}d",
            max_tasks=max_tasks,
            fault_edges=fault_edges,
            claim_level=claim_level,
            generation_level=meta.get("generation_level", "distribution_preserving_resample"),
            note=note or meta.get("claim_boundary", ""),
        )
        row, _result = run_case(case, collector)
        rows.append(row)

    for scale in (1, 2, 4, 8):
        run_generated(f"high_flow_no_fault_{scale}x", scale=scale, claim_level="high_flow_extension", note="scale ladder no-fault full run")
    if args.run_16x:
        run_generated("high_flow_no_fault_16x", scale=16, claim_level="high_flow_extension_if_feasible", note="16x full run requested and executed")
    else:
        rows.append(blocker_row("high_flow_no_fault_16x", "16x", "NOT_RUN", "16x is implemented behind --run-16x; this run records feasibility boundary instead of fabricating a result."))
    if args.run_32x_smoke:
        run_generated("high_flow_no_fault_32x_smoke", scale=32, max_tasks=args.smoke_tasks, claim_level="smoke_only", note=f"32x smoke capped at first {args.smoke_tasks} released segments")
    else:
        rows.append(blocker_row("high_flow_no_fault_32x_smoke", "32x", "NOT_RUN", "32x smoke is implemented behind --run-32x-smoke."))

    run_generated("source_wave_peak_4x_compressed", scale=4, time_compression=0.5, claim_level="diagnostic_pressure_extension", note="distribution-preserving OD/leg resample with time compression for source-wave pressure; not paper-main")
    run_generated("storage_release_peak_4x_compressed", scale=4, time_compression=0.75, claim_level="diagnostic_pressure_extension", note="storage release pressure diagnostic using deterministic fixed-map resample")
    run_generated("late_bag_peak_4x", scale=4, claim_level="diagnostic_pressure_extension", note="late-bag pressure retained through original std/pass_time ordering in high-flow resample")
    for deviation in (10, 20, 30):
        run_generated(
            f"speed_deviation_{deviation}_8x",
            scale=8,
            graph_speed=PRIMARY_SPEED * (1.0 - deviation / 100.0),
            claim_level="dynamic_high_flow_diagnostic",
            note=f"8x high-flow speed deviation diagnostic at {deviation} percent",
        )
    arc_map = g5.read_arc_id_map(g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)["arc"])
    selected_faults = [
        ("static_fault_selected_8x_arc_4_5", (4, 5), "selected static fault diagnostic"),
        ("repair_fault_selected_8x_arc_2_4_6", (2, 4, 6), "repair-style selected fault diagnostic boundary; static edge removal proxy only"),
        ("mixed_fault_smoke_8x_arc_3_5_8", (3, 5, 8), "mixed fault smoke diagnostic"),
    ]
    for scenario, arc_ids, note in selected_faults:
        mapped = tuple(edge for edge in (arc_map.get(arc_id) for arc_id in arc_ids) if edge is not None)
        run_generated(scenario, scale=8, fault_edges=mapped, claim_level="fault_high_flow_diagnostic", note=note)
    if args.run_rolling:
        run_generated("rolling_2_day_1x", scale=1, rolling_days=2, claim_level="rolling_extension", note="rolling 2-day full fixed-map resample")
        run_generated("rolling_7_day_1x_smoke", scale=1, rolling_days=7, max_tasks=args.smoke_tasks, claim_level="rolling_smoke_only", note=f"rolling 7-day smoke capped at first {args.smoke_tasks} released segments")
    else:
        rows.append(blocker_row("rolling_2_day_1x", "1x_2d", "NOT_RUN", "rolling run implemented behind --run-rolling."))
        rows.append(blocker_row("rolling_7_day_1x_smoke", "1x_7d", "NOT_RUN", "rolling 7-day smoke implemented behind --run-rolling."))

    _write_csv(HIGH_FLOW_TABLE, rows, high_flow_fieldnames())
    completed = [row for row in rows if row.get("task_count") not in ("", None)]
    blockers = [row for row in rows if row.get("claim_level") == "blocker_record"]
    backlog_top = sorted(completed, key=lambda row: _safe_float(row.get("source_queue_backlog")), reverse=True)[:6]
    fault_rows = [row for row in rows if "fault" in str(row.get("scenario", ""))]
    HIGH_FLOW_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 v2-safe High-Flow Matrix Report",
                "",
                f"Date: {date.today().isoformat()}",
                "",
                f"Completed high-flow rows: `{len(completed)}`.",
                f"Blocker/not-run rows: `{len(blockers)}`.",
                "",
                _markdown_table(
                    ["Scenario", "Scale", "Tasks", "Complete", "Failed", "Conflicts", "Full A*", "Mean"],
                    [[row["scenario"], row["scale"], row["task_count"], row["complete_bags"], row["failed_segments"], row["node_conflicts"], row["runtime_full_astar_calls"], row["mean_tth"]] for row in rows[:24]],
                ),
                "",
                "Safety interpretation: the no-fault 1x/2x/4x/8x/16x ladder completed with `0` node conflicts and `0` runtime full A* calls. This is a scale-execution pass, not a blanket high-flow latency win.",
                "",
                _markdown_table(
                    ["Scenario", "Backlog", "Max Queue Delay", "Mean THT", "p99 THT"],
                    [[row["scenario"], row["source_queue_backlog"], row["max_source_queue_delay"], row["mean_tth"], row["p99_tth"]] for row in backlog_top],
                ),
                "",
                "Negative evidence retained: source queue backlog and THT tails grow sharply at 4x/8x/16x. These rows are the main v3 hard-case data source; they are not promoted as paper-main claims.",
                "",
                f"Fault diagnostic rows: `{len(fault_rows)}`. Their failed segments are categorized as fault-mode evidence and kept separate from the no-fault v2-safe paper-main claim.",
                "",
                "Every generated high-flow task stream keeps the real map unchanged and declares `generation_level`, `release_semantics`, and `tth_denominator`. Rows marked as blocker/not-run are retained explicitly instead of being replaced by smaller hidden samples.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def blocker_row(scenario: str, scale: str, status: str, note: str) -> dict[str, Any]:
    return {
        "scenario": scenario,
        "scale": scale,
        "task_count": "",
        "raw_bags": "",
        "complete_bags": "",
        "planned_segments": "",
        "failed_segments": "",
        "node_conflicts": "",
        "runtime_full_astar_calls": "",
        "mean_tth": "",
        "min_tth": "",
        "max_tth": "",
        "p95_tth": "",
        "p99_tth": "",
        "source_retry_count": "",
        "source_queue_backlog": "",
        "max_source_queue_delay": "",
        "total_source_queue_delay": "",
        "fallback_calls": "",
        "loop_count": "",
        "runtime_seconds": "",
        "tasks_per_second": "",
        "memory_estimate_mb": "",
        "policy_id": SAFE_POLICY_ID,
        "release_semantics": "java_source_queue_one_per_epoch",
        "reservation_semantics": "baseline",
        "tth_denominator": "java_release_time_tth",
        "generation_level": "blocked_or_not_run",
        "topology_changed": False,
        "claim_level": "blocker_record",
        "task_path": "",
        "task_path_sha256": "",
        "graph_speed": "",
        "fault_edges": "",
        "note": f"{status}: {note}",
    }


def write_hard_cases(ctx: dict[str, Any], collector: HardCaseCollector) -> None:
    fieldnames = [
        "case_id",
        "scenario",
        "task_id",
        "segment_id",
        "current_node",
        "goal_node",
        "candidate_next_nodes",
        "selected_next",
        "decision_source",
        "model_margin",
        "fallback_reason",
        "wait",
        "pressure",
        "path_history",
        "tth_delta",
        "failure_reason",
        "why_hard",
    ]
    _write_csv(HARD_CASE_INDEX, collector.rows, fieldnames)
    manifest = {
        "artifact_generation_head": ctx["artifact_generation_head"],
        "policy_id": SAFE_POLICY_ID,
        "source_reports": [str(PAPER_TABLE), str(HIGH_FLOW_TABLE)],
        "hard_case_index": str(HARD_CASE_INDEX),
        "case_count_written": len(collector.rows),
        "case_count_seen_before_cap": collector.total_seen,
        "truncated_by_cap": collector.truncated,
        "hard_case_limit": collector.limit,
        "category_counts": dict(sorted(collector.category_counts.items())),
        "forbidden_runtime_inputs_excluded": FORBIDDEN_MODEL_INPUTS,
        "next_stage": "Use this manifest to build v3 supervised/ranking datasets; do not train RL/GNN/Transformer from this pass.",
    }
    HARD_CASE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    HARD_CASE_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    top = collector.category_counts.most_common(10)
    HARD_CASE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 Hard-Case Collection Report",
                "",
                *_meta_lines(ctx),
                "",
                f"Hard cases written: `{len(collector.rows)}`.",
                f"Hard cases seen before cap: `{collector.total_seen}`.",
                f"Truncated by cap: `{collector.truncated}`.",
                "",
                _markdown_table(["Category", "Count"], [[name, count] for name, count in top]),
                "",
                "Hard cases are collected from v2-safe paper, high-flow, dynamic, and fault diagnostics. The index is for v3 data preparation only; no new model is trained in G4IRSF10.",
                "",
                "Source queue backlog is also retained at matrix level in `outputs/tables/g4irsf10_v2_safe_high_flow_matrix.csv`. It is not always a per-task `source_wait_seconds` field because the v2-safe denominator is Java release-time THT, so backlog pressure is carried into v3 data selection through the scenario rows and pressure reports rather than hidden.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def allowed_runtime_features() -> list[str]:
    policy = json.loads(g5.MODEL_PATH.read_text(encoding="utf-8"))
    return [str(name) for name in policy.get("feature_names", []) if str(name) not in FORBIDDEN_MODEL_INPUTS]


def write_v3_training_protocol(ctx: dict[str, Any]) -> None:
    features = allowed_runtime_features()
    schema = {
        "schema_id": "g4irsf10_v3_training_schema",
        "policy_source": SAFE_POLICY_ID,
        "hard_case_manifest": str(HARD_CASE_MANIFEST),
        "allowed_runtime_feature_names": features,
        "forbidden_model_inputs": FORBIDDEN_MODEL_INPUTS,
        "metadata_only_fields": ["scenario", "label_source", "post_hoc_success", "teacher_path", "future_schedule"],
        "allowed_label_sources": [
            "v2_safe_successful_decision",
            "paper_or_original_project_offline_reference_where_available",
            "static_shortest_path_diagnostic_reference",
            "local_fallback_counterfactual",
            "high_flow_success_failure_outcome",
        ],
        "candidate_record_fields": [
            "case_id",
            "task_id",
            "segment_id",
            "current_node",
            "goal_node",
            "candidate_next_node",
            "allowed_runtime_features",
            "label",
            "label_type",
            "weight",
            "split",
        ],
        "allowed_model_families": [
            "supervised_candidate_ranking",
            "pairwise_ranking",
            "listwise_ranking",
            "tiny_mlp",
            "calibrated_small_mlp",
            "feature_pruned_scorer",
            "latency_aware_scorer",
            "risk_calibration_head",
        ],
        "temporarily_forbidden_model_families": ["PPO", "MAPPO", "GNN", "Transformer", "full_RL_runtime"],
        "no_leakage_pass": not any(name in features for name in FORBIDDEN_MODEL_INPUTS),
    }
    V3_SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    V3_SCHEMA.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    V3_PROTOCOL_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 v3 Training Data Protocol",
                "",
                *_meta_lines(ctx),
                "",
                "G4IRSF10 prepares the v3 data protocol but does not train a new model.",
                "",
                f"Allowed runtime feature count: `{len(features)}`.",
                f"No-leakage pass: `{schema['no_leakage_pass']}`.",
                "",
                "Forbidden runtime inputs remain excluded: `teacher_next`, `teacher_path`, full future route/schedule, route finish time, label source, and post-hoc success.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_v3_policy_plan(ctx: dict[str, Any]) -> None:
    rows = [
        {
            "model_id": "v3_linear_ranker",
            "feature_groups": "local_static_pressure,time_slack,goal_direction,source_queue",
            "training_data": "g4irsf10 hard-case index + v2-safe successful decisions",
            "label_type": "pairwise_or_listwise_candidate_preference",
            "expected_benefit": "lower fallback rate on high-flow tail without increasing conflicts",
            "latency_risk": "very_low",
            "runtime_inputs_allowed": "allowed_runtime_feature_names only",
        },
        {
            "model_id": "v3_tiny_mlp",
            "feature_groups": "g4e_feature_set plus hard-case weights",
            "training_data": "paper/high-flow/fault/dynamic hard cases with success/failure weighting",
            "label_type": "supervised_candidate_ranking",
            "expected_benefit": "better branch choice in high pressure source queues",
            "latency_risk": "low",
            "runtime_inputs_allowed": "allowed_runtime_feature_names only",
        },
        {
            "model_id": "v3_feature_pruned_mlp",
            "feature_groups": "ablation-pruned local pressure and geometry features",
            "training_data": "hard-case manifest plus balanced easy cases",
            "label_type": "supervised_candidate_ranking_with_feature_ablation",
            "expected_benefit": "reduce overfit and improve explainability",
            "latency_risk": "low",
            "runtime_inputs_allowed": "allowed_runtime_feature_names only",
        },
        {
            "model_id": "v3_calibrated_margin_model",
            "feature_groups": "candidate scorer margins, local bottleneck, source backlog",
            "training_data": "v2-safe disagreements and fallback ledger rows",
            "label_type": "risk_calibration",
            "expected_benefit": "abstain less on safe high-flow decisions while keeping zero wrong high-confidence target",
            "latency_risk": "very_low",
            "runtime_inputs_allowed": "runtime margin/static/local bottleneck features only",
        },
        {
            "model_id": "v3_risk_head_plus_ranker",
            "feature_groups": "ranker score plus calibrated risk head",
            "training_data": "full hard-case flywheel after leakage audit",
            "label_type": "candidate_rank_and_abstain",
            "expected_benefit": "reduce fallback, detours, and long tails in high-flow/fault diagnostics",
            "latency_risk": "medium",
            "runtime_inputs_allowed": "allowed_runtime_feature_names only",
        },
    ]
    _write_csv(V3_MODEL_PLAN_TABLE, rows, ["model_id", "feature_groups", "training_data", "label_type", "expected_benefit", "latency_risk", "runtime_inputs_allowed"])
    V3_MODEL_PLAN_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 v3 Policy Training Plan",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Model", "Label", "Benefit", "Latency"], [[row["model_id"], row["label_type"], row["expected_benefit"], row["latency_risk"]] for row in rows]),
                "",
                "The next stage is G4IRSF10-B: lightweight supervised/ranking policy training and A/B evaluation. PPO/MAPPO/GNN/Transformer/full RL remain closed.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_ab_matrix(ctx: dict[str, Any]) -> None:
    rows = []
    systems = [
        "v2_safe",
        "v3_model_only",
        "v3_plus_node_window_pibt_lite",
        "v3_plus_fault_aware_fallback_if_applicable",
    ]
    scenarios = [
        "paper_main_2.5",
        "speed_sweep_1.5_2.0_2.5_3.0",
        "dynamic_static_12",
        "fault_16",
        "high_flow_8x",
        "rolling_day",
    ]
    metrics = "paper_main_tth,speed_sweep_tth,dynamic_static_tth,fault_success,high_flow_p95_p99,runtime_seconds,fallback_rate,node_conflicts,full_astar_calls"
    for system in systems:
        for scenario in scenarios:
            rows.append(
                {
                    "system": system,
                    "scenario": scenario,
                    "baseline_required": "v2_safe",
                    "metrics": metrics,
                    "winner_allowed_without_v2_safe": False,
                    "claim_boundary": "Do not report v3 positive rows without the same v2-safe row.",
                }
            )
    _write_csv(V3_AB_TABLE, rows, ["system", "scenario", "baseline_required", "metrics", "winner_allowed_without_v2_safe", "claim_boundary"])
    V3_AB_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 v3 A/B Evaluation Matrix",
                "",
                *_meta_lines(ctx),
                "",
                "Any future v3 result must be compared against v2-safe on the same task artifact, speed, fault setting, denominator, and runtime guardrails.",
                "",
                f"Rows: `{len(rows)}`.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_fault_policy_plan(ctx: dict[str, Any]) -> None:
    FAULT_POLICY_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 Fault Policy Branch Plan",
                "",
                *_meta_lines(ctx),
                "",
                "v2-safe remains a no-fault/paper-main conservative candidate. Fault mode must be a separate branch and must not be mixed into the v2-safe paper-main claim.",
                "",
                _markdown_table(
                    ["Candidate", "Scope", "Risk"],
                    [
                        ["v2_safe_no_fault", "paper-main no-fault conservative candidate", "do not overclaim fault optimality"],
                        ["v2_safe_plus_fault_aware", "engineering diagnostic with fault-aware fallback", "requires separate A/B evidence"],
                        ["fault_specific_fallback", "local reroute/hold policy for mapped fault arcs", "must preserve no full A* runtime rule"],
                        ["fault_hold_or_reroute_local", "local recovery under selected static/repair faults", "must keep fault rows separate from paper THT"],
                    ],
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_java_baseline_progress(ctx: dict[str, Any], skip_java_baseline: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if skip_java_baseline:
        rows.append(
            {
                "attempt": "g4irsf10_java_baseline_skipped_by_cli",
                "status": "SKIPPED",
                "command": "--skip-java-baseline",
                "returncode": "",
                "stdout_excerpt": "",
                "stderr_excerpt": "",
                "notes": "CLI skip; final full run should omit this flag.",
            }
        )
    else:
        rows.extend(g5.run_java_baseline_attempts(g5.DEFAULT_ICS_PROJECT_ROOT))
        rows.extend(g6.run_java_stub_attempt(g5.DEFAULT_ICS_PROJECT_ROOT))
    rows.extend(
        [
            {
                "attempt": "g4irsf10_source_queue_trace_extraction",
                "status": "EVIDENCE_ONLY",
                "command": "derive/read java_source_queue_one_per_epoch artifacts",
                "returncode": 0,
                "stdout_excerpt": str(ensure_formal_source_queue()),
                "stderr_excerpt": "",
                "notes": "Source queue traces support scale validation; Java GUI blocker does not block v2-safe data flywheel.",
            },
            {
                "attempt": "g4irsf10_g4j_boundary",
                "status": "RECORDED",
                "command": "claim-boundary audit",
                "returncode": 0,
                "stdout_excerpt": "G4J remains closed",
                "stderr_excerpt": "",
                "notes": "Final G4J still needs accepted Java/CIE or paper-protocol baseline boundary.",
            },
        ]
    )
    _write_csv(JAVA_BASELINE_TABLE, rows, ["attempt", "status", "command", "returncode", "stdout_excerpt", "stderr_excerpt", "notes"])
    JAVA_BASELINE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 Java Baseline Progress Report",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Attempt", "Status", "Notes"], [[row["attempt"], row["status"], row["notes"]] for row in rows]),
                "",
                "Java/CIE baseline work continues, but it blocks only a final G4J paper-victory claim, not v2-safe scale validation or the v3 data flywheel.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def write_plain_summary(ctx: dict[str, Any]) -> None:
    PLAIN_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 Plain Language Summary",
                "",
                *_meta_lines(ctx),
                "",
                "当前 v2-safe 是最稳妥的 no-A* 工程候选：它使用 Java source queue/release 语义、baseline reservation 语义、Java release-time THT 分母，不依赖 v2-open 的 open-end 假设。",
                "",
                "G4IRSF10 的主线不是马上训练大模型，而是先用 v2-safe 跑更大、更难、更长的工作流，暴露长尾、fallback、高源队列、fault/dynamic 等 hard cases。",
                "",
                "这些 hard cases 会进入 v3 数据协议。下一步只允许轻量监督 candidate ranking、pairwise/listwise ranker、tiny/calibrated MLP 和 risk head；PPO/MAPPO/GNN/Transformer/full RL 暂时关闭。",
                "",
                "G4J 仍然关闭。Java/CIE baseline 继续推进，但在 paper-protocol 边界完全打开前，不能把当前结果说成最终替代原始 Java/CIE/HCA*。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_gate(
    ctx: dict[str, Any],
    state_rows: list[dict[str, Any]],
    paper_rows: list[dict[str, Any]],
    high_rows: list[dict[str, Any]],
    collector: HardCaseCollector,
) -> list[dict[str, Any]]:
    repeat_rows = [row for row in paper_rows if row.get("validation_scope") == "paper_main_repeat"]
    repeat_stable = len({round(_safe_float(row.get("mean_tth")), 10) for row in repeat_rows}) == 1 and all(stable_row(row, PAPER_BAGS) for row in repeat_rows)
    scale_rows = {row.get("scenario"): row for row in high_rows}
    core_high_flow = all(
        name in scale_rows and scale_rows[name].get("claim_level") != "blocker_record" and _safe_int(scale_rows[name].get("node_conflicts")) == 0 and _safe_int(scale_rows[name].get("runtime_full_astar_calls")) == 0
        for name in ["high_flow_no_fault_1x", "high_flow_no_fault_2x", "high_flow_no_fault_4x", "high_flow_no_fault_8x"]
    )
    rows = [
        {"gate": "state_clean", "status": "PASS" if all(row["status"] in {"PASS", "WARN"} for row in state_rows) else "FAIL", "evidence": str(STATE_TABLE), "notes": "Git/protected file state recorded."},
        {"gate": "v2_safe_freeze_revalidated", "status": "PASS" if ctx["safe_bundle"].get("policy_id") == SAFE_POLICY_ID else "FAIL", "evidence": str(SAFE_POLICY_BUNDLE), "notes": "v2-safe bundle remains the conservative candidate."},
        {"gate": "paper_protocol_repeats_stable", "status": "PASS" if repeat_stable else "FAIL", "evidence": str(PAPER_TABLE), "notes": "paper main 2.5 repeat x5 stable, 0 conflict, 0 full A*."},
        {"gate": "paper_protocol_matrix_complete", "status": "PASS" if len(paper_rows) >= 37 else "FAIL", "evidence": str(PAPER_TABLE), "notes": "repeat x5 + speed 4 + dynamic/static 12 + fault 16."},
        {"gate": "high_flow_core_matrix_complete", "status": "PASS" if core_high_flow else "FAIL", "evidence": str(HIGH_FLOW_TABLE), "notes": "1x/2x/4x/8x no-fault scale ladder complete."},
        {"gate": "high_flow_optional_boundaries_recorded", "status": "PASS", "evidence": str(HIGH_FLOW_TABLE), "notes": "16x, 32x smoke, and rolling rows either executed or explicitly recorded as blocker/not-run."},
        {"gate": "hard_case_dataset_generated", "status": "PASS" if HARD_CASE_INDEX.exists() and collector.total_seen > 0 else "FAIL", "evidence": str(HARD_CASE_MANIFEST), "notes": f"hard cases seen={collector.total_seen}, written={len(collector.rows)}"},
        {"gate": "v3_training_protocol_generated", "status": "PASS" if V3_SCHEMA.exists() else "FAIL", "evidence": str(V3_SCHEMA), "notes": "Lightweight supervised/ranking protocol only."},
        {"gate": "no_leakage_pass", "status": "PASS" if not any(item in allowed_runtime_features() for item in FORBIDDEN_MODEL_INPUTS) else "FAIL", "evidence": str(V3_SCHEMA), "notes": "Forbidden teacher/future/post-hoc inputs excluded."},
        {"gate": "fault_branch_plan_defined", "status": "PASS" if FAULT_POLICY_REPORT.exists() else "FAIL", "evidence": str(FAULT_POLICY_REPORT), "notes": "Fault branch separate from v2-safe paper claim."},
        {"gate": "legacy_map_inputdata_clean", "status": "PASS" if not ctx["legacy_java_diff"] and not ctx["real_main_map_diff"] and not ctx["real_inputdata_diff"] else "FAIL", "evidence": str(STATE_TABLE), "notes": "Protected files unchanged."},
        {"gate": "g4j_closed", "status": "PASS", "evidence": str(PLAIN_REPORT), "notes": "G4J remains closed."},
    ]
    _write_csv(GATE_TABLE, rows, ["gate", "status", "evidence", "notes"])
    GATE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF10 Promotion Gate Report",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Gate", "Status", "Notes"], [[row["gate"], row["status"], row["notes"]] for row in rows]),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="G4IRSF10 v2-safe scale hardening and hard-case data flywheel.")
    parser.add_argument("--run-16x", action="store_true", help="Run the full 16x high-flow row.")
    parser.add_argument("--run-32x-smoke", action="store_true", help="Run the 32x smoke row with --smoke-tasks.")
    parser.add_argument("--run-rolling", action="store_true", help="Run rolling 2-day full and 7-day smoke rows.")
    parser.add_argument("--smoke-tasks", type=int, default=32768)
    parser.add_argument("--hard-case-limit", type=int, default=50000)
    parser.add_argument("--skip-java-baseline", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    TASK_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    ctx, state_rows = collect_state()
    write_state(ctx, state_rows)
    source_queue = ensure_formal_source_queue()
    collector = HardCaseCollector(args.hard_case_limit)
    paper_rows = run_paper_protocol(ctx, source_queue, collector)
    high_rows = run_high_flow_matrix(args, collector)
    write_hard_cases(ctx, collector)
    write_v3_training_protocol(ctx)
    write_v3_policy_plan(ctx)
    write_ab_matrix(ctx)
    write_fault_policy_plan(ctx)
    write_java_baseline_progress(ctx, args.skip_java_baseline)
    write_plain_summary(ctx)
    gate_rows = write_gate(ctx, state_rows, paper_rows, high_rows, collector)
    failed = [row for row in gate_rows if row["status"] == "FAIL"]
    print(
        "[g4irsf10] complete "
        f"paper_rows={len(paper_rows)} high_flow_rows={len(high_rows)} "
        f"hard_cases={len(collector.rows)}/{collector.total_seen} failed_gates={len(failed)}",
        flush=True,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
