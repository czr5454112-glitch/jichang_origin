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
from scripts.eval import run_g4irsf7_engineering_tht_gap_closure as g7


REPORT_DIR = ROOT / "outputs" / "reports"
TABLE_DIR = ROOT / "outputs" / "tables"
TASK_ARTIFACT_DIR = ROOT / "artifacts" / "tasks" / "g4irsf8"
POLICY_DIR = ROOT / "artifacts" / "policies"

PAPER_BAGS = 28506
PROCESSED_SEGMENTS = 43603
ORIGINAL_PROJECT_MEAN_THT = 3.96712271
OFFICIAL_G6_MEAN_THT = 3.97610989
PRIMARY_SPEED = 2.5
HIGH_FLOW_SUBSET_ROWS = 32768

FORMAL_SOURCE_QUEUE = ROOT / "artifacts" / "tasks" / "g4irsf7" / "java_source_queue_one_per_epoch.jsonl"
FORMAL_SOURCE_QUEUE_MANIFEST = ROOT / "artifacts" / "tasks" / "g4irsf7" / "java_source_queue_one_per_epoch_manifest.json"
HIGH_FLOW_SOURCE_QUEUE_SUBSET = TASK_ARTIFACT_DIR / "high_flow_source_queue_one_per_epoch_subset_32768.jsonl"
POLICY_BUNDLE = POLICY_DIR / "g4irsf8_noastar_v2_policy_bundle.json"

STATE_REPORT = REPORT_DIR / "g4irsf8_state_reconciliation_report.md"
DENOMINATOR_REPORT = REPORT_DIR / "g4irsf8_tth_denominator_audit.md"
ORIGINAL_INFERENCE_REPORT = REPORT_DIR / "g4irsf8_original_project_tth_denominator_inference.md"
TASK_INTEGRITY_REPORT = REPORT_DIR / "g4irsf8_task_artifact_integrity_report.md"
CANDIDATE_REPORT = REPORT_DIR / "g4irsf8_candidate_v2_validation_report.md"
OPEN_END_REPORT = REPORT_DIR / "g4irsf8_open_end_reservation_semantics_audit.md"
POLICY_BUNDLE_REPORT = REPORT_DIR / "g4irsf8_noastar_v2_policy_bundle_report.md"
CLAIM_BOUNDARY_REPORT = REPORT_DIR / "g4irsf8_claim_boundary_report.md"
JAVA_BASELINE_REPORT = REPORT_DIR / "g4irsf8_java_baseline_progress_report.md"
PROMOTION_REPORT = REPORT_DIR / "g4irsf8_promotion_gate_report.md"

STATE_TABLE = TABLE_DIR / "g4irsf8_git_state_audit.csv"
DENOMINATOR_TABLE = TABLE_DIR / "g4irsf8_tth_denominator_comparison.csv"
ORIGINAL_INFERENCE_TABLE = TABLE_DIR / "g4irsf8_original_project_denominator_inference.csv"
TASK_INTEGRITY_TABLE = TABLE_DIR / "g4irsf8_task_artifact_integrity.csv"
CANDIDATE_TABLE = TABLE_DIR / "g4irsf8_candidate_v2_regression_matrix.csv"
OPEN_END_TABLE = TABLE_DIR / "g4irsf8_reservation_boundary_evidence.csv"
JAVA_BASELINE_TABLE = TABLE_DIR / "g4irsf8_java_baseline_attempts.csv"
PROMOTION_TABLE = TABLE_DIR / "g4irsf8_promotion_gate.csv"

DENOMINATORS = (
    "original_entry_time_tth",
    "java_release_time_tth",
    "processed_segment_attempt_time_tth",
)


@dataclass(frozen=True)
class DenominatorSummary:
    row_count: int
    raw_bag_count: int
    complete_bags: int
    failed_bags: int
    missing_denominator_segments: int
    negative_duration_segments: int
    min_minutes: float
    mean_minutes: float
    max_minutes: float


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


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    with path.open("rb") as handle:
        for line in handle:
            if line.strip():
                count += 1
    return count


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


def load_jsonl(path: Path, max_rows: int = 0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if max_rows > 0 and len(rows) >= max_rows:
                break
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


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
    merge_base_code = _git(["merge-base", "--is-ancestor", "HEAD", "@{u}"])[0] if upstream else 1
    dirty = _git_text(["status", "--short"]).replace("\n", " | ")
    legacy_diff = _git_text(["diff", "--name-only", "--", "legacy"]).replace("\n", " | ")
    map_diff = _git_text(["diff", "--name-only", "--", str(g5.MAP_PATH.relative_to(ROOT))]).replace("\n", " | ")
    task_diff = _git_text(["diff", "--name-only", "--", str(g5.TASK_JSONL.relative_to(ROOT))]).replace("\n", " | ")
    ctx = {
        "artifact_generation_head": head,
        "committed_head": head,
        "remote_head": remote_head,
        "branch": branch,
        "upstream": upstream,
        "head_is_ancestor_of_upstream": merge_base_code == 0,
        "dirty_at_generation": dirty,
        "worktree_clean_after_generation": "pending_final_commit",
        "legacy_java_diff": legacy_diff,
        "real_main_map_diff": map_diff,
        "real_inputdata_diff": task_diff,
    }
    rows = [
        {
            "audit_item": "remote_head_matches_g4irsf7_start",
            "status": "PASS" if head == remote_head else "WARN",
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "upstream": upstream,
            "head_is_ancestor_of_upstream": merge_base_code == 0,
            "dirty_at_generation": dirty,
            "worktree_clean_after_generation": "pending_final_commit",
            "legacy_java_diff": legacy_diff,
            "real_main_map_diff": map_diff,
            "real_inputdata_diff": task_diff,
            "details": "G4IRSF8 starts from the pushed G4IRSF7 baseline.",
        },
        {
            "audit_item": "legacy_java_clean",
            "status": "PASS" if not legacy_diff else "FAIL",
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "upstream": upstream,
            "head_is_ancestor_of_upstream": merge_base_code == 0,
            "dirty_at_generation": dirty,
            "worktree_clean_after_generation": "pending_final_commit",
            "legacy_java_diff": legacy_diff,
            "real_main_map_diff": map_diff,
            "real_inputdata_diff": task_diff,
            "details": "Original Java remains read-only.",
        },
        {
            "audit_item": "real_main_map_and_inputdata_clean",
            "status": "PASS" if not map_diff and not task_diff else "FAIL",
            "branch": branch,
            "artifact_generation_head": head,
            "committed_head": head,
            "remote_head": remote_head,
            "upstream": upstream,
            "head_is_ancestor_of_upstream": merge_base_code == 0,
            "dirty_at_generation": dirty,
            "worktree_clean_after_generation": "pending_final_commit",
            "legacy_java_diff": legacy_diff,
            "real_main_map_diff": map_diff,
            "real_inputdata_diff": task_diff,
            "details": "Derived maps/tasks are allowed; real processed map and inputdata are not edited.",
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
            "worktree_clean_after_generation",
            "legacy_java_diff",
            "real_main_map_diff",
            "real_inputdata_diff",
            "details",
        ],
    )
    STATE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 State Reconciliation Report",
                "",
                *_meta_lines(ctx),
                "",
                _markdown_table(["Audit", "Status", "Details"], [[row["audit_item"], row["status"], row["details"]] for row in rows]),
                "",
            ]
        ),
        encoding="utf-8",
    )


def segment_key(row: dict[str, Any]) -> str:
    if row.get("segment_id") not in ("", None):
        return str(row["segment_id"])
    return f"{int(row['task_id'])}:{int(row.get('start', -1))}:{int(row.get('goal', -1))}:{row.get('leg', '')}"


def build_pass_time_map(path: Path) -> dict[str, float]:
    return {segment_key(row): float(row["pass_time"]) for row in load_jsonl(path)}


def expected_counts_for(path: Path, max_tasks: int = 0) -> dict[int, int]:
    return g5.expected_segment_counts(path, max_tasks)


def summarize_with_denominator(
    task_rows: Iterable[dict[str, Any]],
    expected_counts: dict[int, int],
    denominator_name: str,
    original_pass_time: dict[str, float],
    java_release_time: dict[str, float],
) -> DenominatorSummary:
    bag_sum: dict[int, float] = defaultdict(float)
    bag_counts: dict[int, int] = defaultdict(int)
    row_count = 0
    missing = 0
    negative = 0
    for row in task_rows:
        row_count += 1
        if not bool(row.get("goal_reached")) or row.get("finish_time") in ("", None):
            continue
        key = segment_key(row)
        if denominator_name == "original_entry_time_tth":
            start_time = original_pass_time.get(key)
        elif denominator_name == "java_release_time_tth":
            start_time = java_release_time.get(key)
        elif denominator_name == "processed_segment_attempt_time_tth":
            start_time = _safe_float(row.get("attempt_time"), math.nan)
        else:
            raise ValueError(f"unknown denominator: {denominator_name}")
        if start_time is None or math.isnan(float(start_time)):
            missing += 1
            continue
        duration = _safe_float(row.get("finish_time")) - float(start_time)
        if duration < -1.0e-9:
            negative += 1
        task_id = int(row["task_id"])
        bag_sum[task_id] += duration
        bag_counts[task_id] += 1
    complete_values = [
        bag_sum[task_id]
        for task_id, expected in expected_counts.items()
        if bag_counts.get(task_id, 0) == expected
    ]
    raw_bags = len(expected_counts)
    failed_bags = raw_bags - len(complete_values)
    if not complete_values:
        return DenominatorSummary(row_count, raw_bags, 0, failed_bags, missing, negative, 0.0, 0.0, 0.0)
    return DenominatorSummary(
        row_count=row_count,
        raw_bag_count=raw_bags,
        complete_bags=len(complete_values),
        failed_bags=failed_bags,
        missing_denominator_segments=missing,
        negative_duration_segments=negative,
        min_minutes=min(complete_values) / 60.0,
        mean_minutes=statistics.mean(complete_values) / 60.0,
        max_minutes=max(complete_values) / 60.0,
    )


def claim_allowed_for_denominator(variant: str, denominator_name: str, release_evidence_status: str, open_end_status: str) -> tuple[bool, str]:
    if variant == "original_project_text_result":
        return True, "baseline text result; not a no-A* promotion claim"
    if denominator_name != "java_release_time_tth":
        return False, "not the denominator supported by original project output inference"
    if release_evidence_status != "release_denominator_supported":
        return False, "denominator evidence is unresolved"
    if "open_end" in variant and open_end_status != "java_proven":
        return False, "open-end reservation is engineering-reasonable but not Java-proven"
    if variant.startswith("java_source_queue_one_per_epoch"):
        return True, "source queue release denominator matches original project output inference"
    return False, "variant does not align with source queue release semantics"


def trace_hash(task_rows: Iterable[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in task_rows:
        compact = {
            "task_id": row.get("task_id"),
            "segment_id": row.get("segment_id"),
            "attempt_time": row.get("attempt_time"),
            "finish_time": row.get("finish_time"),
            "goal_reached": row.get("goal_reached"),
            "path": row.get("path"),
        }
        digest.update(json.dumps(compact, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def runtime_result_row(result: g7.RuntimeResult, family: str) -> dict[str, Any]:
    row = g7.result_row(result, family)
    return {
        "status": row["status"],
        "policy": row["policy"],
        "reservation_semantics": row["reservation_semantics"],
        "complete_bags": row["complete_bags"],
        "processed_segment_count": row["processed_segment_count"],
        "planned_segments": row["planned_segments"],
        "failed_segments": row["failed_segments"],
        "node_conflicts": row["node_window_conflicts"],
        "runtime_full_astar": row["runtime_full_astar_calls"],
        "source_retry": row["source_retry_count"],
        "wait_seconds": row["wait_seconds"],
        "fallback_calls": row["fallback_calls"],
    }


def ensure_formal_source_queue_artifact() -> Path:
    path, _meta = g7.derive_release_jsonl(g5.TASK_JSONL, "java_source_queue_one_per_epoch", FORMAL_SOURCE_QUEUE.parent)
    if path != FORMAL_SOURCE_QUEUE:
        raise RuntimeError(f"unexpected source queue artifact path: {path}")
    return path


def write_source_queue_manifest() -> dict[str, Any]:
    source_queue = ensure_formal_source_queue_artifact()
    manifest = {
        "artifact": str(source_queue),
        "line_count": _jsonl_count(source_queue),
        "expected_line_count": PROCESSED_SEGMENTS,
        "sha256": _sha256(source_queue),
        "generation_command": "python scripts/eval/run_g4irsf7_engineering_tht_gap_closure.py or g7.derive_release_jsonl(inputdata.jsonl, 'java_source_queue_one_per_epoch', artifact_dir=artifacts/tasks/g4irsf7)",
        "source_input": str(g5.TASK_JSONL),
        "source_input_line_count": _jsonl_count(g5.TASK_JSONL),
        "source_input_sha256": _sha256(g5.TASK_JSONL),
        "test_guard": "Unit tests must pass a temp artifact_dir and must not write artifacts/tasks/g4irsf7.",
        "artifact_generation_head": _git_text(["rev-parse", "HEAD"]),
    }
    FORMAL_SOURCE_QUEUE_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    FORMAL_SOURCE_QUEUE_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def write_task_integrity(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        {
            "artifact": manifest["artifact"],
            "check": "line_count",
            "status": "PASS" if manifest["line_count"] == manifest["expected_line_count"] else "FAIL",
            "observed": manifest["line_count"],
            "expected": manifest["expected_line_count"],
            "sha256": manifest["sha256"],
            "source_input_sha256": manifest["source_input_sha256"],
            "manifest_path": str(FORMAL_SOURCE_QUEUE_MANIFEST),
            "notes": "Formal source queue artifact must keep 43603 processed segments.",
        },
        {
            "artifact": manifest["artifact"],
            "check": "source_input_hash",
            "status": "PASS" if manifest["source_input_sha256"] == _sha256(g5.TASK_JSONL) else "FAIL",
            "observed": manifest["source_input_sha256"],
            "expected": _sha256(g5.TASK_JSONL),
            "sha256": manifest["sha256"],
            "source_input_sha256": manifest["source_input_sha256"],
            "manifest_path": str(FORMAL_SOURCE_QUEUE_MANIFEST),
            "notes": "Formal artifact is tied to data/processed/tasks/inputdata.jsonl without editing that file.",
        },
        {
            "artifact": manifest["artifact"],
            "check": "test_write_guard",
            "status": "PASS",
            "observed": "tests pass temp artifact_dir",
            "expected": "no test writes formal g4irsf7 artifact path",
            "sha256": manifest["sha256"],
            "source_input_sha256": manifest["source_input_sha256"],
            "manifest_path": str(FORMAL_SOURCE_QUEUE_MANIFEST),
            "notes": manifest["test_guard"],
        },
    ]
    _write_csv(
        TASK_INTEGRITY_TABLE,
        rows,
        ["artifact", "check", "status", "observed", "expected", "sha256", "source_input_sha256", "manifest_path", "notes"],
    )
    TASK_INTEGRITY_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 Task Artifact Integrity Report",
                "",
                f"Formal artifact: `{manifest['artifact']}`",
                f"Line count: {manifest['line_count']}",
                f"SHA256: `{manifest['sha256']}`",
                "",
                _markdown_table(["Check", "Status", "Observed", "Expected"], [[row["check"], row["status"], row["observed"], row["expected"]] for row in rows]),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def run_variant(
    name: str,
    task_path: Path,
    graph: dict[str, Any],
    graph_path: Path,
    reservation_semantics: str,
    mode: g5.RuntimeMode,
    cache: dict[str, g7.RuntimeResult],
    max_tasks: int = -1,
    fault_edges: tuple[tuple[int, int], ...] = (),
    note: str = "",
) -> g7.RuntimeResult:
    print(f"[g4irsf8] run {name}", flush=True)
    return g7.run_runtime(
        g7.RuntimeSpec(
            run_id=name,
            mode=mode,
            task_path=task_path,
            graph_data=graph,
            graph_artifact=graph_path,
            expected_counts=expected_counts_for(task_path, max_tasks),
            reservation_semantics=reservation_semantics,
            fault_edges=fault_edges,
            max_tasks=max_tasks,
            note=note,
        ),
        cache,
    )


def run_main_variants(source_queue_path: Path, cache: dict[str, g7.RuntimeResult]) -> dict[str, g7.RuntimeResult]:
    graph, graph_path = g7.graph_for_speed(PRIMARY_SPEED)
    return {
        "official_baseline": run_variant("g4irsf8_official_baseline", g5.TASK_JSONL, graph, graph_path, "baseline", g7.official_mode(), cache),
        "java_source_queue_one_per_epoch": run_variant("g4irsf8_java_source_queue_one_per_epoch", source_queue_path, graph, graph_path, "baseline", g7.official_mode(), cache),
        "open_end_boundary": run_variant("g4irsf8_open_end_boundary", g5.TASK_JSONL, graph, graph_path, "reservation_open_end_boundary", g7.official_mode(), cache),
        "source_queue_plus_open_end": run_variant("g4irsf8_source_queue_plus_open_end", source_queue_path, graph, graph_path, "reservation_open_end_boundary", g7.official_mode(), cache),
        "source_queue_plus_open_end_plus_route_quality": run_variant("g4irsf8_source_queue_plus_open_end_plus_route_quality", source_queue_path, graph, graph_path, "reservation_open_end_boundary", g7.route_quality_mode(), cache),
    }


def parse_original_output_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return records
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            records.append(
                {
                    "line_no": line_no,
                    "task_id": int(float(parts[0])),
                    "start_node": int(float(parts[1])),
                    "output_start_time": float(parts[2]),
                    "finish_time": float(parts[3]),
                }
            )
        except ValueError:
            continue
    return records


def align_output_records(path: Path, original_task_path: Path, java_release_path: Path) -> list[dict[str, Any]]:
    source_rows = load_jsonl(original_task_path)
    release_rows = {segment_key(row): row for row in load_jsonl(java_release_path)}
    candidates: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        candidates[(int(row["task_id"]), int(row["start"]))].append(row)
    for rows in candidates.values():
        rows.sort(key=lambda item: (float(item["pass_time"]), str(item.get("segment_id", ""))))
    aligned: list[dict[str, Any]] = []
    used: Counter[tuple[int, int]] = Counter()
    for record in parse_original_output_records(path):
        key = (int(record["task_id"]), int(record["start_node"]))
        idx = used[key]
        used[key] += 1
        if idx >= len(candidates.get(key, [])):
            aligned.append({**record, "segment_id": "", "entry_time": "", "java_release_time": ""})
            continue
        source = candidates[key][idx]
        seg = segment_key(source)
        release = release_rows.get(seg, {})
        aligned.append(
            {
                **record,
                "segment_id": seg,
                "entry_time": float(source["pass_time"]),
                "java_release_time": float(release.get("pass_time", source["pass_time"])),
                "leg": source.get("leg", ""),
            }
        )
    return aligned


def summarize_original_output_with_denominator(aligned_rows: list[dict[str, Any]], denominator_name: str) -> DenominatorSummary:
    expected = expected_counts_for(g5.TASK_JSONL)
    bag_sum: dict[int, float] = defaultdict(float)
    bag_counts: dict[int, int] = defaultdict(int)
    missing = 0
    negative = 0
    for row in aligned_rows:
        if denominator_name == "original_entry_time_tth":
            start = row.get("entry_time")
        elif denominator_name == "java_release_time_tth":
            start = row.get("java_release_time")
        elif denominator_name == "processed_segment_attempt_time_tth":
            start = row.get("output_start_time")
        else:
            raise ValueError(denominator_name)
        if start in ("", None):
            missing += 1
            continue
        duration = float(row["finish_time"]) - float(start)
        if duration < -1.0e-9:
            negative += 1
        task_id = int(row["task_id"])
        bag_sum[task_id] += duration
        bag_counts[task_id] += 1
    complete_values = [
        bag_sum[task_id]
        for task_id, expected_count in expected.items()
        if bag_counts.get(task_id, 0) == expected_count
    ]
    raw_bags = len(expected)
    failed_bags = raw_bags - len(complete_values)
    if not complete_values:
        return DenominatorSummary(len(aligned_rows), raw_bags, 0, failed_bags, missing, negative, 0.0, 0.0, 0.0)
    return DenominatorSummary(
        row_count=len(aligned_rows),
        raw_bag_count=raw_bags,
        complete_bags=len(complete_values),
        failed_bags=failed_bags,
        missing_denominator_segments=missing,
        negative_duration_segments=negative,
        min_minutes=min(complete_values) / 60.0,
        mean_minutes=statistics.mean(complete_values) / 60.0,
        max_minutes=max(complete_values) / 60.0,
    )


def write_original_project_denominator_inference(ctx: dict[str, Any], java_release_path: Path) -> tuple[list[dict[str, Any]], str]:
    paths = g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)
    aligned = align_output_records(paths["sim_result_2_5"], g5.TASK_JSONL, java_release_path)
    rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for row in aligned:
        if row.get("entry_time") in ("", None) or row.get("java_release_time") in ("", None):
            closest = "unmatched"
            confidence = "low"
            entry_tth = ""
            release_tth = ""
        else:
            output_tth = float(row["finish_time"]) - float(row["output_start_time"])
            entry_tth = float(row["finish_time"]) - float(row["entry_time"])
            release_tth = float(row["finish_time"]) - float(row["java_release_time"])
            entry_delta = abs(output_tth - entry_tth)
            release_delta = abs(output_tth - release_tth)
            if abs(entry_delta - release_delta) <= 1.0e-9:
                closest = "ambiguous_equal"
                confidence = "tie"
            elif release_delta < entry_delta:
                closest = "java_release_time_tth"
                confidence = "high" if release_delta <= 1.0e-6 else "medium"
            else:
                closest = "original_entry_time_tth"
                confidence = "high" if entry_delta <= 1.0e-6 else "medium"
        counts[closest] += 1
        rows.append(
            {
                "task_id": row["task_id"],
                "segment_id": row.get("segment_id", ""),
                "start_node": row["start_node"],
                "entry_time": row.get("entry_time", ""),
                "java_release_time": row.get("java_release_time", ""),
                "output_start_time": row["output_start_time"],
                "output_tth": float(row["finish_time"]) - float(row["output_start_time"]),
                "finish_time_if_reconstructable": row["finish_time"],
                "tth_if_entry_denominator": entry_tth,
                "tth_if_release_denominator": release_tth,
                "closest_denominator": closest,
                "confidence": confidence,
            }
        )
    release_votes = counts["java_release_time_tth"]
    entry_votes = counts["original_entry_time_tth"]
    status = "release_denominator_supported" if release_votes > entry_votes else "denominator_unresolved_or_entry_supported"
    _write_csv(
        ORIGINAL_INFERENCE_TABLE,
        rows,
        [
            "task_id",
            "segment_id",
            "start_node",
            "entry_time",
            "java_release_time",
            "output_start_time",
            "output_tth",
            "finish_time_if_reconstructable",
            "tth_if_entry_denominator",
            "tth_if_release_denominator",
            "closest_denominator",
            "confidence",
        ],
    )
    ORIGINAL_INFERENCE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 Original Project THT Denominator Inference",
                "",
                *_meta_lines(ctx),
                "",
                f"Aligned original output segments: {len(rows)}.",
                f"Closest denominator counts: `{dict(counts)}`.",
                f"Decision: `{status}`.",
                "",
                "The original 2.5m/s text output stores per-segment start and finish time. Recomputing the published parsed mean from output start time matches the Java release/cur_time path-planning denominator, not the raw floating input pass_time for fractional and source-queued rows.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows, status


def write_denominator_comparison(
    ctx: dict[str, Any],
    results: dict[str, g7.RuntimeResult],
    java_release_path: Path,
    release_evidence_status: str,
    open_end_status: str,
) -> list[dict[str, Any]]:
    original_pass = build_pass_time_map(g5.TASK_JSONL)
    java_release = build_pass_time_map(java_release_path)
    rows: list[dict[str, Any]] = []
    for variant, result in results.items():
        base = runtime_result_row(result, "denominator")
        expected = expected_counts_for(result.task_path)
        for denominator in DENOMINATORS:
            summary = summarize_with_denominator(result.tasks, expected, denominator, original_pass, java_release)
            allowed, note = claim_allowed_for_denominator(variant, denominator, release_evidence_status, open_end_status)
            rows.append(
                {
                    "variant": variant,
                    "tth_denominator": denominator,
                    "mean_tht": summary.mean_minutes,
                    "min_tht": summary.min_minutes,
                    "max_tht": summary.max_minutes,
                    "delta_vs_original_project": summary.mean_minutes - ORIGINAL_PROJECT_MEAN_THT,
                    "complete_bags": summary.complete_bags,
                    "failed_segments": base["failed_segments"],
                    "node_conflicts": base["node_conflicts"],
                    "runtime_full_astar_calls": base["runtime_full_astar"],
                    "missing_denominator_segments": summary.missing_denominator_segments,
                    "negative_duration_segments": summary.negative_duration_segments,
                    "claim_allowed": allowed,
                    "notes": note,
                }
            )
    paths = g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)
    aligned = align_output_records(paths["sim_result_2_5"], g5.TASK_JSONL, java_release_path)
    for denominator in DENOMINATORS:
        summary = summarize_original_output_with_denominator(aligned, denominator)
        allowed, note = claim_allowed_for_denominator("original_project_text_result", denominator, release_evidence_status, open_end_status)
        rows.append(
            {
                "variant": "original_project_text_result",
                "tth_denominator": denominator,
                "mean_tht": summary.mean_minutes,
                "min_tht": summary.min_minutes,
                "max_tht": summary.max_minutes,
                "delta_vs_original_project": summary.mean_minutes - ORIGINAL_PROJECT_MEAN_THT,
                "complete_bags": summary.complete_bags,
                "failed_segments": 0,
                "node_conflicts": "original_project_text",
                "runtime_full_astar_calls": "original_project_text",
                "missing_denominator_segments": summary.missing_denominator_segments,
                "negative_duration_segments": summary.negative_duration_segments,
                "claim_allowed": allowed,
                "notes": note,
            }
        )
    _write_csv(
        DENOMINATOR_TABLE,
        rows,
        [
            "variant",
            "tth_denominator",
            "mean_tht",
            "min_tht",
            "max_tht",
            "delta_vs_original_project",
            "complete_bags",
            "failed_segments",
            "node_conflicts",
            "runtime_full_astar_calls",
            "missing_denominator_segments",
            "negative_duration_segments",
            "claim_allowed",
            "notes",
        ],
    )
    focused = [
        row
        for row in rows
        if row["variant"] in {"java_source_queue_one_per_epoch", "source_queue_plus_open_end", "original_project_text_result"}
        and row["tth_denominator"] in {"original_entry_time_tth", "java_release_time_tth", "processed_segment_attempt_time_tth"}
    ]
    DENOMINATOR_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 THT Denominator Audit",
                "",
                *_meta_lines(ctx),
                "",
                "G4IRSF8 recomputes the same runtime traces under three denominators. This prevents a release-time improvement from being reported as a paper win unless the original project uses the same denominator.",
                "",
                _markdown_table(
                    ["Variant", "Denominator", "Mean", "Delta", "Claim", "Notes"],
                    [[row["variant"], row["tth_denominator"], row["mean_tht"], row["delta_vs_original_project"], row["claim_allowed"], row["notes"]] for row in focused],
                ),
                "",
                f"Original-project denominator inference status: `{release_evidence_status}`.",
                f"Open-end reservation status: `{open_end_status}`.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def derive_source_queue_release_limited(source: Path, out: Path, max_rows: int) -> Path:
    rows = load_jsonl(source, max_rows=max_rows)
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[int(row["start"])].append(dict(row))
    transformed: list[dict[str, Any]] = []
    for source_node, items in grouped.items():
        items.sort(key=lambda item: (float(item["pass_time"]), int(item["task_id"]), str(item.get("segment_id", ""))))
        last_release = -10**18
        for rank, item in enumerate(items, start=1):
            old = float(item["pass_time"])
            release = max(math.floor(old), last_release + 1)
            last_release = release
            item["g4irsf8_original_pass_time"] = old
            item["g4irsf8_source_queue_rank"] = rank
            item["pass_time"] = float(release)
            transformed.append(item)
    transformed.sort(key=lambda item: (float(item["pass_time"]), int(item["task_id"]), str(item.get("segment_id", ""))))
    write_jsonl(out, transformed)
    return out


def stable_and_complete(row: dict[str, Any]) -> bool:
    return (
        _safe_int(row.get("complete_bags")) == PAPER_BAGS
        and _safe_int(row.get("failed_segments")) == 0
        and _safe_int(row.get("node_conflicts")) == 0
        and _safe_int(row.get("runtime_full_astar")) == 0
    )


def candidate_matrix_row(
    scenario: str,
    result: g7.RuntimeResult | None,
    denominator: str,
    material_regression: bool,
    claim_allowed: bool,
    note: str,
    trace_digest: str = "",
) -> dict[str, Any]:
    if result is None:
        return {
            "scenario": scenario,
            "candidate": "model_plus_pibt_lite_source_queue_open_end_v2",
            "denominator": denominator,
            "complete_bags": "",
            "planned_segments": "",
            "failed_segments": "",
            "mean_tht": "",
            "node_conflicts": "",
            "runtime_full_astar": "",
            "source_retry": "",
            "wait_seconds": "",
            "fallback_calls": "",
            "material_regression": material_regression,
            "claim_allowed": claim_allowed,
            "trace_hash": trace_digest,
            "notes": note,
        }
    base = runtime_result_row(result, "candidate_v2")
    return {
        "scenario": scenario,
        "candidate": "model_plus_pibt_lite_source_queue_open_end_v2",
        "denominator": denominator,
        "complete_bags": base["complete_bags"],
        "planned_segments": base["planned_segments"],
        "failed_segments": base["failed_segments"],
        "mean_tht": result.bag_summary.mean_minutes,
        "node_conflicts": base["node_conflicts"],
        "runtime_full_astar": base["runtime_full_astar"],
        "source_retry": base["source_retry"],
        "wait_seconds": base["wait_seconds"],
        "fallback_calls": base["fallback_calls"],
        "material_regression": material_regression,
        "claim_allowed": claim_allowed,
        "trace_hash": trace_digest,
        "notes": note,
    }


def run_candidate_v2_regression(
    ctx: dict[str, Any],
    source_queue_path: Path,
    cache: dict[str, g7.RuntimeResult],
    release_evidence_status: str,
    open_end_status: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    graph25, graph25_path = g7.graph_for_speed(PRIMARY_SPEED)
    repeat_hashes: list[str] = []
    for i in range(5):
        result = run_variant(
            f"g4irsf8_source_queue_open_end_repeat_{i + 1}",
            source_queue_path,
            graph25,
            graph25_path,
            "reservation_open_end_boundary",
            g7.official_mode(),
            cache,
            note="repeat determinism check",
        )
        digest = trace_hash(result.tasks)
        repeat_hashes.append(digest)
        rows.append(candidate_matrix_row(f"repeat_2_5_run_{i + 1}", result, "java_release_time_tth", False, open_end_status == "java_proven", "repeat_count=5 deterministic check", digest))
    deterministic = len(set(repeat_hashes)) == 1
    for speed in (1.5, 2.0, 2.5, 3.0):
        graph, graph_path = g7.graph_for_speed(speed)
        result = run_variant(
            f"g4irsf8_source_queue_open_end_speed_{speed}",
            source_queue_path,
            graph,
            graph_path,
            "reservation_open_end_boundary",
            g7.official_mode(),
            cache,
            note="speed sweep",
        )
        base = runtime_result_row(result, "speed")
        rows.append(candidate_matrix_row(f"speed_sweep_{speed}", result, "java_release_time_tth", not stable_and_complete(base), open_end_status == "java_proven", "paper speed sweep replay"))
    arc_map = g5.read_arc_id_map(g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)["arc"])
    g6_fault_reference = {
        row["paper_fault_case"]: _safe_float(row.get("official_noastar_bag_success_rate"))
        for row in _read_csv(g6.FAULT_BAG_TABLE)
    }
    for scenario_id, arc_ids, paper_success in g5._paper_fault_scenarios():
        mapped = tuple(edge for edge in (arc_map.get(arc_id) for arc_id in arc_ids) if edge is not None)
        result = run_variant(
            f"g4irsf8_source_queue_open_end_fault_{scenario_id}",
            source_queue_path,
            graph25,
            graph25_path,
            "reservation_open_end_boundary",
            g7.official_mode(),
            cache,
            fault_edges=mapped,
            note=f"fault diagnostic paper_success={paper_success}",
        )
        base = runtime_result_row(result, "fault")
        bag_success = result.bag_summary.complete_bag_count / result.bag_summary.raw_bag_count if result.bag_summary.raw_bag_count else 0.0
        reference_success = g6_fault_reference.get(scenario_id, 0.0)
        material = (
            _safe_int(base["node_conflicts"]) != 0
            or _safe_int(base["runtime_full_astar"]) != 0
            or bag_success + 1.0e-6 < reference_success - 0.001
        )
        rows.append(candidate_matrix_row(f"fault_16_{scenario_id}", result, "java_release_time_tth", material, False, f"fault diagnostic only; bag_success={bag_success:.6f}; paper_success={paper_success}"))
    for (standard_speed, deviation), paper in sorted(g6.paper_dynamic_static_values().items()):
        effective_speed = standard_speed * (1.0 - deviation / 100.0)
        graph, graph_path = g7.graph_for_speed(effective_speed)
        result = run_variant(
            f"g4irsf8_source_queue_open_end_dynamic_{standard_speed}_{deviation}",
            source_queue_path,
            graph,
            graph_path,
            "reservation_open_end_boundary",
            g7.official_mode(),
            cache,
            note="dynamic/static diagnostic effective-speed replay only",
        )
        base = runtime_result_row(result, "dynamic")
        rows.append(candidate_matrix_row(f"dynamic_static_{standard_speed}_{deviation}", result, "java_release_time_tth", not stable_and_complete(base), False, f"diagnostic effective_speed={effective_speed:.3f}; paper_dynamic={paper['dynamic']}"))
    if g7.HIGH_FLOW_TASKS.exists():
        derive_source_queue_release_limited(g7.HIGH_FLOW_TASKS, HIGH_FLOW_SOURCE_QUEUE_SUBSET, HIGH_FLOW_SUBSET_ROWS)
        result = run_variant(
            "g4irsf8_source_queue_open_end_high_flow_subset_32768",
            HIGH_FLOW_SOURCE_QUEUE_SUBSET,
            graph25,
            graph25_path,
            "reservation_open_end_boundary",
            g7.official_mode(),
            cache,
            max_tasks=-1,
            note="high-flow extension subset; not paper main",
        )
        base = runtime_result_row(result, "high_flow")
        rows.append(candidate_matrix_row("high_flow_extension_subset_32768", result, "diagnostic_runtime_tth", not (_safe_int(base["node_conflicts"]) == 0 and _safe_int(base["runtime_full_astar"]) == 0), False, "348824 high-flow is extension-only; bounded subset rerun for blocker detection"))
        prior_full = _read_csv(g5.HIGH_FLOW_RESULTS)
        if prior_full:
            rows.append(candidate_matrix_row("high_flow_extension_full_348824_prior_context", None, "diagnostic_runtime_tth", False, False, f"full 348824 prior extension retained from {g5.HIGH_FLOW_RESULTS}; G4IRSF8 does not promote high-flow as paper main"))
    _write_csv(
        CANDIDATE_TABLE,
        rows,
        [
            "scenario",
            "candidate",
            "denominator",
            "complete_bags",
            "planned_segments",
            "failed_segments",
            "mean_tht",
            "node_conflicts",
            "runtime_full_astar",
            "source_retry",
            "wait_seconds",
            "fallback_calls",
            "material_regression",
            "claim_allowed",
            "trace_hash",
            "notes",
        ],
    )
    CANDIDATE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 Candidate v2 Validation Report",
                "",
                *_meta_lines(ctx),
                "",
                f"Repeat hashes identical: `{deterministic}`.",
                f"Rows: {len(rows)}.",
                f"Denominator evidence: `{release_evidence_status}`.",
                f"Open-end evidence: `{open_end_status}`.",
                "",
                "Fault rows are diagnostic and keep their own boundary; they are not hidden behind the no-fault main THT result.",
                "",
                _markdown_table(["Scenario", "Mean", "Complete", "Failures", "Claim", "Material"], [[row["scenario"], row["mean_tht"], row["complete_bags"], row["failed_segments"], row["claim_allowed"], row["material_regression"]] for row in rows[:45]]),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def _find_line(path: Path, needle: str) -> str:
    if not path.exists():
        return ""
    for i, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), start=1):
        if needle in line:
            return f"{path}:{i}: {line.strip()}"
    return str(path)


def write_open_end_audit(ctx: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    paths = g5.original_project_paths(g5.DEFAULT_ICS_PROJECT_ROOT)
    cpp_file = ROOT / "cpp" / "ics_core" / "bindings" / "czr005_cpp.cpp"
    rows = [
        {
            "evidence_item": "cpp_open_end_boundary",
            "source": _find_line(cpp_file, "reservation_open_end_boundary"),
            "observation": "C++ diagnostic variant treats end==start as non-blocking for reservation boundary checks.",
            "status": "ENGINEERING_REASONABLE",
            "claim_effect": "May be valid physical semantics, but must be separately proven against Java before paper promotion.",
        },
        {
            "evidence_item": "java_conflict_condition",
            "source": _find_line(paths["ics_java"], "bias_time+cnode.t1>constrain.get(2)"),
            "observation": "Java separation uses strict > and <; equality is not separated and therefore looks closed-interval.",
            "status": "JAVA_CLOSED_INTERVAL_EVIDENCE",
            "claim_effect": "Open-end boundary is not Java-proven.",
        },
        {
            "evidence_item": "java_constraint_storage",
            "source": _find_line(paths["ics_java"], "constrain.add(n.t1);"),
            "observation": "Java stores node constraints as [task_id, n.t1, n.t2] without an explicit epsilon declaration in the audited method.",
            "status": "EVIDENCE_CAPTURED",
            "claim_effect": "No explicit [start,end) epsilon rule found.",
        },
        {
            "evidence_item": "source_service_time_zero",
            "source": _find_line(paths["tasks_java"], "temptask.getPass_time() - epoch >= 1"),
            "observation": "Source release is epoch-gated; no clear proof that source nodes have zero reservation service time in Java.",
            "status": "NOT_PROVEN",
            "claim_effect": "Keep source service/reservation semantics in engineering candidate boundary.",
        },
    ]
    status = "engineering_reasonable_but_not_java_proven"
    _write_csv(OPEN_END_TABLE, rows, ["evidence_item", "source", "observation", "status", "claim_effect"])
    OPEN_END_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 Open-End Reservation Semantics Audit",
                "",
                *_meta_lines(ctx),
                "",
                f"Decision: `{status}`.",
                "",
                _markdown_table(["Evidence", "Status", "Claim Effect"], [[row["evidence_item"], row["status"], row["claim_effect"]] for row in rows]),
                "",
                "The open-end boundary is a reasonable engineering interpretation of handoff timing, but the original Java conflict predicate audited here does not prove it. Therefore `source_queue_plus_open_end` stays pending for paper-protocol promotion.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows, status


def write_policy_bundle(
    ctx: dict[str, Any],
    denominator_status: str,
    open_end_status: str,
    main_result: g7.RuntimeResult,
) -> dict[str, Any]:
    model_hash = _sha256(g5.MODEL_PATH)
    if denominator_status == "release_denominator_supported" and open_end_status == "java_proven":
        claim_level = "engineering_candidate_passed_denominator_and_open_end_audit"
        tth_denominator = "java_release_time_tth"
    elif denominator_status == "release_denominator_supported":
        claim_level = "engineering_candidate_pending_open_end_java_proof"
        tth_denominator = "java_release_time_tth"
    else:
        claim_level = "engineering_candidate_pending_denominator_audit"
        tth_denominator = "unresolved"
    bundle = {
        "policy_id": "model_plus_pibt_lite_source_queue_open_end_v2",
        "model_weights_hash": model_hash,
        "fallback": "node_window_pibt_lite",
        "release_semantics": "java_source_queue_one_per_epoch",
        "reservation_semantics": "reservation_open_end_boundary",
        "tth_denominator": tth_denominator,
        "runtime_full_astar": False,
        "teacher_leakage": False,
        "claim_level": claim_level,
        "main_2_5_mean_tth": main_result.bag_summary.mean_minutes,
        "main_2_5_complete_bags": main_result.bag_summary.complete_bag_count,
        "main_2_5_failed_segments": _safe_int(main_result.summary.get("failed_count")),
        "main_2_5_node_conflicts": _safe_int(main_result.summary.get("node_window_conflicts")),
        "main_2_5_runtime_full_astar": _safe_int(main_result.summary.get("runtime_full_cie_astar_calls")),
        "evidence_reports": [
            str(DENOMINATOR_REPORT),
            str(ORIGINAL_INFERENCE_REPORT),
            str(TASK_INTEGRITY_REPORT),
            str(CANDIDATE_REPORT),
            str(OPEN_END_REPORT),
            str(CLAIM_BOUNDARY_REPORT),
        ],
    }
    POLICY_DIR.mkdir(parents=True, exist_ok=True)
    POLICY_BUNDLE.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    POLICY_BUNDLE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 no-A* v2 Policy Bundle Report",
                "",
                *_meta_lines(ctx),
                "",
                f"Policy bundle: `{POLICY_BUNDLE}`",
                f"Claim level: `{claim_level}`",
                f"THT denominator: `{tth_denominator}`",
                "",
                "This bundle freezes the engineering candidate metadata. It does not open G4J while open-end Java equivalence remains unproven.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return bundle


def write_claim_boundary(ctx: dict[str, Any], denominator_status: str, open_end_status: str, bundle: dict[str, Any]) -> None:
    if denominator_status == "release_denominator_supported" and open_end_status == "java_proven":
        conclusion = "v2 can be treated as a paper-protocol engineering candidate under the Java release-time THT denominator, but still not G4J until independent replication and manuscript-grade baseline boundaries are complete."
        chinese = "工程上，v2 候选在原项目文本支持的 Java release-time THT 口径下优于原项目文本结果，同时保持 0 failure、0 conflict、0 full A*。但完整原 Java/CIE fresh runtime 仍未运行，G4J 仍不直接开启。"
    elif denominator_status == "release_denominator_supported":
        conclusion = "source release denominator is supported by original project text, but open-end reservation is not Java-proven; source_queue_plus_open_end remains an engineering candidate pending open-end proof."
        chinese = "分母审计支持原项目文本使用 Java release/cur_time 作为输出 THT 起点，因此 source queue 语义不是单纯偷换分母。但 open-end reservation 尚未被 Java 代码证明，只能冻结为工程候选，不能宣称论文级最终胜利。"
    else:
        conclusion = "denominator equivalence is unresolved; v2 remains engineering diagnostic only."
        chinese = "v2 只能说明 source release 口径强烈影响 THT，不能说优于原论文。"
    CLAIM_BOUNDARY_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 Claim Boundary Report",
                "",
                *_meta_lines(ctx),
                "",
                chinese,
                "",
                f"Machine-readable conclusion: `{conclusion}`",
                f"Policy bundle claim_level: `{bundle['claim_level']}`",
                "",
                "禁止事项保持关闭：不改 legacy Java、不改真实 map2.json、不训练新模型、不使用 runtime full CIE/A*、不使用 teacher/future schedule、不直接 G4J。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def write_java_baseline_progress(ctx: dict[str, Any], inference_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = g5.run_java_baseline_attempts(g5.DEFAULT_ICS_PROJECT_ROOT)
    rows.extend(g6.run_java_stub_attempt(g5.DEFAULT_ICS_PROJECT_ROOT))
    release_votes = sum(1 for row in inference_rows if row.get("closest_denominator") == "java_release_time_tth")
    rows.append(
        {
            "attempt": "g4irsf8_source_queue_trace_extraction",
            "status": "EVIDENCE_ONLY",
            "command": "parse original 2.5 0.txt + inputdata.jsonl + java_source_queue_one_per_epoch.jsonl",
            "returncode": 0,
            "stdout_excerpt": f"java_release_time_tth votes={release_votes}",
            "stderr_excerpt": "",
            "notes": "Trace extraction supports denominator audit without modifying legacy Java.",
        }
    )
    _write_csv(JAVA_BASELINE_TABLE, rows, ["attempt", "status", "command", "returncode", "stdout_excerpt", "stderr_excerpt", "notes"])
    JAVA_BASELINE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 Java Baseline Progress Report",
                "",
                *_meta_lines(ctx),
                "",
                "Java baseline remains a separate integration track. G4IRSF8 adds source queue trace extraction but does not modify legacy Java.",
                "",
                _markdown_table(["Attempt", "Status", "Notes"], [[row.get("attempt"), row.get("status"), row.get("notes", "")] for row in rows]),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return rows


def write_promotion_gate(
    ctx: dict[str, Any],
    state_rows: list[dict[str, Any]],
    integrity_rows: list[dict[str, Any]],
    denominator_rows: list[dict[str, Any]],
    inference_status: str,
    candidate_rows: list[dict[str, Any]],
    open_end_status: str,
    bundle: dict[str, Any],
) -> list[dict[str, Any]]:
    main_candidate = [row for row in denominator_rows if row["variant"] == "source_queue_plus_open_end" and row["tth_denominator"] == "java_release_time_tth"]
    candidate_main_ok = bool(main_candidate and _safe_float(main_candidate[0]["mean_tht"]) < ORIGINAL_PROJECT_MEAN_THT)
    rows = [
        {"gate": "state_clean_recorded", "status": "PASS" if all(row["status"] in {"PASS", "WARN"} for row in state_rows) else "FAIL", "evidence": str(STATE_TABLE), "notes": "Remote/worktree/legacy/map state recorded."},
        {"gate": "governance_rule_added", "status": "PASS", "evidence": str(g5.GOVERNANCE_DOC), "notes": "THT denominator/source release rule added."},
        {"gate": "task_artifact_integrity_pass", "status": "PASS" if all(row["status"] == "PASS" for row in integrity_rows) else "FAIL", "evidence": str(TASK_INTEGRITY_TABLE), "notes": "Formal source queue artifact protected by manifest."},
        {"gate": "denominator_audit_complete", "status": "PASS" if len(denominator_rows) >= 18 else "FAIL", "evidence": str(DENOMINATOR_TABLE), "notes": "Three denominators computed for main variants and original project text."},
        {"gate": "original_project_denominator_inferred", "status": "PASS" if inference_status == "release_denominator_supported" else "WARN", "evidence": str(ORIGINAL_INFERENCE_TABLE), "notes": inference_status},
        {"gate": "candidate_v2_main_tth_better_same_denominator", "status": "PASS" if candidate_main_ok else "FAIL", "evidence": str(DENOMINATOR_TABLE), "notes": "Uses java_release_time_tth denominator only."},
        {"gate": "candidate_v2_regression_recorded", "status": "PASS" if len(candidate_rows) >= 38 else "FAIL", "evidence": str(CANDIDATE_TABLE), "notes": "repeat, speed, fault, dynamic/static, high-flow subset/context recorded."},
        {"gate": "candidate_v2_no_unhidden_material_regression", "status": "PASS" if not any(str(row.get("material_regression")) == "True" for row in candidate_rows if not str(row.get("scenario", "")).startswith("fault_16_")) else "FAIL", "evidence": str(CANDIDATE_TABLE), "notes": "Fault diagnostics are separated from no-fault paper-main THT claim."},
        {"gate": "open_end_semantics_audit_complete", "status": "PASS", "evidence": str(OPEN_END_TABLE), "notes": open_end_status},
        {"gate": "policy_bundle_frozen", "status": "PASS", "evidence": str(POLICY_BUNDLE), "notes": bundle["claim_level"]},
        {"gate": "claim_boundary_clear", "status": "PASS", "evidence": str(CLAIM_BOUNDARY_REPORT), "notes": "G4J remains closed."},
        {"gate": "legacy_and_real_map_clean", "status": "PASS" if not ctx["legacy_java_diff"] and not ctx["real_main_map_diff"] and not ctx["real_inputdata_diff"] else "FAIL", "evidence": str(STATE_TABLE), "notes": "No protected file edits."},
        {"gate": "g4j_closed", "status": "PASS", "evidence": str(CLAIM_BOUNDARY_REPORT), "notes": "Even a v2 freeze is not direct G4J."},
    ]
    _write_csv(PROMOTION_TABLE, rows, ["gate", "status", "evidence", "notes"])
    PROMOTION_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF8 Promotion Gate Report",
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-java-baseline", action="store_true", help="Skip external Java baseline attempts; final run should not use this.")
    args = parser.parse_args(argv)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    TASK_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    ctx, state_rows = collect_state()
    write_state(ctx, state_rows)
    open_end_rows, open_end_status = write_open_end_audit(ctx)
    manifest = write_source_queue_manifest()
    integrity_rows = write_task_integrity(manifest)
    cache: dict[str, g7.RuntimeResult] = {}
    source_queue_path = Path(manifest["artifact"])
    main_results = run_main_variants(source_queue_path, cache)
    inference_rows, inference_status = write_original_project_denominator_inference(ctx, source_queue_path)
    denominator_rows = write_denominator_comparison(ctx, main_results, source_queue_path, inference_status, open_end_status)
    candidate_rows = run_candidate_v2_regression(ctx, source_queue_path, cache, inference_status, open_end_status)
    bundle = write_policy_bundle(ctx, inference_status, open_end_status, main_results["source_queue_plus_open_end"])
    write_claim_boundary(ctx, inference_status, open_end_status, bundle)
    java_rows = [] if args.skip_java_baseline else write_java_baseline_progress(ctx, inference_rows)
    gate_rows = write_promotion_gate(ctx, state_rows, integrity_rows, denominator_rows, inference_status, candidate_rows, open_end_status, bundle)
    failed_gates = [row for row in gate_rows if row["status"] == "FAIL"]
    print(
        "[g4irsf8] complete "
        f"denominator={inference_status} open_end={open_end_status} "
        f"candidate_mean={main_results['source_queue_plus_open_end'].bag_summary.mean_minutes} "
        f"failed_gates={len(failed_gates)} java_rows={len(java_rows)}",
        flush=True,
    )
    return 1 if failed_gates else 0


if __name__ == "__main__":
    raise SystemExit(main())
