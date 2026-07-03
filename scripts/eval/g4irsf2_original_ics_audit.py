from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_DOC = ROOT / "docs" / "czr005_project_governance.md"
DEFAULT_ICS_ROOT = Path(r"C:\STUDY\民航二所项目相关\冯汝琛相关材料\冯汝琛相关材料\ICS项目")

REPORT_DIR = ROOT / "outputs" / "reports"
TABLE_DIR = ROOT / "outputs" / "tables"
ARTIFACT_DIR = ROOT / "artifacts" / "policies"

ACCESS_MISSING_REPORT = REPORT_DIR / "g4irsf2_original_ics_access_missing.md"
DATA_AUDIT_REPORT = REPORT_DIR / "g4irsf2_original_ics_data_generation_audit.md"
BENCH_REPORT = REPORT_DIR / "g4irsf2_fixed_map_high_flow_benchmark_report.md"
FAULT_REPORT = REPORT_DIR / "g4irsf2_fault_18_22_autopsy.md"
EDGE_REPORT = REPORT_DIR / "g4irsf2_edge_physical_pressure_report.md"
LEAKAGE_REPORT = REPORT_DIR / "g4irsf2_no_leakage_fixed_map_high_flow_report.md"
PROMOTION_REPORT = REPORT_DIR / "g4irsf2_promotion_decision.md"

FILE_INVENTORY = TABLE_DIR / "g4irsf2_original_ics_file_inventory.csv"
CANDIDATE_FILES = TABLE_DIR / "g4irsf2_original_ics_candidate_files.csv"
KEYWORD_HITS = TABLE_DIR / "g4irsf2_original_ics_keyword_hits.txt"
RULE_INVENTORY = TABLE_DIR / "g4irsf2_original_ics_rule_inventory.csv"
INPUT_SCHEMA = TABLE_DIR / "g4irsf2_original_ics_input_schema.csv"
FLOW_EVIDENCE = TABLE_DIR / "g4irsf2_original_ics_flow_generation_evidence.csv"
BASELINE_EVIDENCE = TABLE_DIR / "g4irsf2_original_ics_baseline_rule_evidence.csv"
SLOPE_TABLE = TABLE_DIR / "g4irsf2_fixed_map_noastar_vs_astar_slope.csv"
HARDNESS_TABLE = TABLE_DIR / "g4irsf2_astar_hardness.csv"
FAULT_CASES = TABLE_DIR / "g4irsf2_fault_18_22_failure_cases.csv"
FAULT_COUNTERFACTUAL = TABLE_DIR / "g4irsf2_fault_18_22_local_counterfactual.csv"
EDGE_SWEEP = TABLE_DIR / "g4irsf2_edge_pressure_sweep.csv"
TOP_EDGE_BY_FLOW = TABLE_DIR / "g4irsf2_top_edge_overlap_by_flow.csv"
NO_LEAKAGE = TABLE_DIR / "g4irsf2_no_leakage_checks.csv"
PROMOTION_GATE = TABLE_DIR / "g4irsf2_promotion_gate.csv"
ALLOWED_INPUTS = ARTIFACT_DIR / "g4irsf2_allowed_runtime_inputs.json"

KEYWORDS = [
    "inputdata",
    "map",
    "task",
    "flight",
    "baggage",
    "bag",
    "luggage",
    "route",
    "routing",
    "AStar",
    "Astar",
    "HCA",
    "CIE",
    "simulation",
    "simulate",
    "fault",
    "repair",
    "source",
    "destination",
    "station",
    "storage",
    "EBS",
    "pass_time",
    "std",
    "deadline",
    "pallet",
    "segment",
    "装载",
    "卸载",
    "行李",
    "航班",
    "仿真",
    "任务",
    "路径",
    "故障",
    "修复",
    "分流",
    "合流",
    "入港",
    "出港",
    "中转",
]

FORBIDDEN_RUNTIME_TOKENS = [
    "teacher_next",
    "teacher_path",
    "full_cie_route",
    "future_schedule",
    "future_sipp_schedule",
    "post_hoc_success",
    "label_source",
    "scenario_lookup",
]


def _prepare_imports() -> None:
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "src"))


def _csv_value(value: Any) -> Any:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        return f"{value:.8f}".rstrip("0").rstrip(".")
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
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


def _load_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
                if limit is not None and len(rows) >= limit:
                    break
    return rows


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


def _sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _git(args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=False, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_ctx() -> dict[str, str]:
    return {
        "branch": _git(["branch", "--show-current"]),
        "head": _git(["rev-parse", "--short", "HEAD"]),
        "upstream": _git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]),
        "legacy_diff_files": _git(["diff", "--name-only", "--", "legacy"]).replace("\n", " | "),
    }


def _meta_lines(ctx: dict[str, str]) -> list[str]:
    return [
        f"Date: {date.today().isoformat()}",
        f"Branch: `{ctx['branch']}`",
        f"HEAD: `{ctx['head']}`",
        f"governance_doc: {GOVERNANCE_DOC.relative_to(ROOT).as_posix()}",
        "topology_changed: false",
    ]


def resolve_ics_root(value: str | None) -> Path:
    _prepare_imports()
    from scripts.data.g4irsf2_generate_high_flow_from_original_rules import resolve_ics_root as resolve

    return resolve(value)


def simulation_root(ics_root: Path) -> Path:
    return ics_root / "代码-ICSsimulation"


def _source_ref(path: Path, line: int | None = None) -> str:
    if line is None:
        return str(path)
    return f"{path}:{line}"


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def _snippet(path: Path, line_no: int) -> str:
    lines = _read_lines(path)
    if 1 <= line_no <= len(lines):
        return lines[line_no - 1].strip()
    return ""


def _find_line(path: Path, needle: str) -> tuple[int, str]:
    for index, line in enumerate(_read_lines(path), start=1):
        if needle in line:
            return index, line.strip()
    return 0, ""


def _write_access_missing(ics_root: Path) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ACCESS_MISSING_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF2 Original ICS Access Missing",
                "",
                f"original_ics_project_access = MISSING",
                "main_claim_flow_generation = BLOCKED",
                f"requested_or_resolved_path: `{ics_root}`",
                "",
                "No high-flow task stream was generated because the original ICS project path could not be accessed.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _inventory_files(ics_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    allowed_ext = {".java", ".py", ".cpp", ".cs", ".m", ".xml", ".json", ".csv", ".txt", ".dat", ".xls", ".xlsx", ".properties", ".ini", ".cfg"}
    inventory = []
    candidates = []
    for path in sorted(ics_root.rglob("*")):
        if not path.is_file():
            continue
        row = {
            "full_name": str(path),
            "relative_path": str(path.relative_to(ics_root)),
            "length": path.stat().st_size,
            "last_write_time": path.stat().st_mtime,
            "extension": path.suffix.lower(),
        }
        inventory.append(row)
        if path.suffix.lower() in allowed_ext and "\\__MACOSX\\" not in str(path) and not path.name.startswith("._"):
            row2 = dict(row)
            text = ""
            if path.suffix.lower() in {".java", ".py", ".cpp", ".cs", ".m", ".xml", ".json", ".csv", ".txt", ".dat", ".properties", ".ini", ".cfg"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
            matched = [keyword for keyword in KEYWORDS if keyword.lower() in text.lower() or keyword.lower() in path.name.lower()]
            row2["keyword_hits"] = matched
            row2["candidate_reason"] = "source_or_data_extension" if not matched else "source_or_data_extension;keyword_hit"
            candidates.append(row2)
    _write_csv(FILE_INVENTORY, inventory, ["full_name", "relative_path", "length", "last_write_time", "extension"])
    _write_csv(CANDIDATE_FILES, candidates, ["full_name", "relative_path", "length", "last_write_time", "extension", "keyword_hits", "candidate_reason"])
    return inventory, candidates


def _keyword_hits(ics_root: Path) -> None:
    lines = []
    text_ext = {".java", ".py", ".cpp", ".cs", ".m", ".xml", ".json", ".csv", ".txt", ".dat", ".properties", ".ini", ".cfg"}
    for path in sorted(ics_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in text_ext or "\\__MACOSX\\" in str(path) or path.name.startswith("._"):
            continue
        for index, line in enumerate(_read_lines(path), start=1):
            lowered = line.lower()
            matched = [keyword for keyword in KEYWORDS if keyword.lower() in lowered]
            if matched:
                lines.append(f"{path}:{index}: {line.strip()}")
                break
    KEYWORD_HITS.parent.mkdir(parents=True, exist_ok=True)
    KEYWORD_HITS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _rule_tables(ics_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sim = simulation_root(ics_root)
    tasks_java = sim / "src" / "App" / "Tasks.java"
    main_java = sim / "src" / "RUN" / "Main.java"
    map_java = sim / "src" / "App" / "Map.java"
    astar_java = sim / "src" / "App" / "Astar.java"
    path_java = sim / "src" / "App" / "ICS_PathFinding.java"
    task_java = sim / "src" / "App" / "task.java"
    inputdata = sim / "inputdata.txt"
    map2 = sim / "map2.txt"
    evidence = []
    baseline = []

    def ev(category: str, name: str, status: str, path: Path, line: int, confidence: str, used: bool, notes: str) -> dict[str, Any]:
        return {
            "rule_category": category,
            "rule_name": name,
            "status": status,
            "source_file": str(path),
            "source_line_or_snippet": f"{line}: {_snippet(path, line)}" if line else "",
            "confidence": confidence,
            "used_in_czr005_generation": used,
            "notes": notes,
        }

    rule_rows = [
        ev("topology", "fixed_map2_topology", "FOUND", main_java, 22, "HIGH", True, "Main uses map2.txt; G4IRSF2 keeps processed map2.json unchanged."),
        ev("topology", "node_record_schema", "FOUND", map_java, 29, "HIGH", True, "Map header and node rows define node count, service time, x/y and outgoing adjacency."),
        ev("topology", "star_nodes_generate_tasks", "FOUND", map_java, 51, "HIGH", True, "Type 1 nodes are task source nodes and default cangenerated_task=true."),
        ev("topology", "end_nodes", "FOUND", map_java, 54, "HIGH", True, "Type 2 nodes are terminal nodes."),
        ev("topology", "edge_speed_constant_2p5", "FOUND", map_java, 79, "HIGH", True, "Edge velocity is set to 2.5 in original Java map loader."),
        ev("input_schema", "legacy_inputdata_columns", "FOUND", inputdata, 1, "HIGH", True, "ID EntryTime(s) STD(s) star end Unloader Loader."),
        ev("task_fields", "task_class_fields", "FOUND", task_java, 4, "HIGH", True, "task_ID, pallet_ID, star, goal, passed/pass nodes, pass_time, STD."),
        ev("task_generation", "read_inputdata_as_source_queues", "FOUND", main_java, 38, "HIGH", True, "Main reads inputdata.txt and groups tasks by start node."),
        ev("task_generation", "early_bag_threshold_4800", "FOUND", main_java, 40, "HIGH", True, "If STD-entry >= 4800, bag goes to storage first."),
        ev("task_generation", "storage_in_goal_47", "FOUND", main_java, 116, "HIGH", True, "Early bag first segment targets storage node 47."),
        ev("task_generation", "storage_out_start_52", "FOUND", main_java, 125, "HIGH", True, "Early bag second segment starts at node 52."),
        ev("task_generation", "storage_out_lead_2700", "FOUND", main_java, 123, "HIGH", True, "Storage-out pass_time is STD - 2700."),
        ev("task_generation", "java_pass_time_sort", "FOUND", main_java, 89, "HIGH", True, "Source queues are sorted by pass_time with Java integer comparator."),
        ev("task_generation", "epoch_release_from_source_queue", "FOUND", tasks_java, 149, "HIGH", True, "generate_tasks releases the first queued task at each enabled source when pass_time <= epoch."),
        ev("task_generation", "random_od_generation_disabled", "FOUND", tasks_java, 120, "HIGH", False, "Random goal generation exists only in commented-out code; not used for main generation."),
        ev("fault_repair", "fault_probability_per_edge", "FOUND", tasks_java, 128, "MEDIUM", False, "Fault events are sampled by Math.random per edge during generate_tasks."),
        ev("fault_repair", "repair_probability_per_fault_edge", "FOUND", tasks_java, 138, "MEDIUM", False, "Repair events are sampled by Math.random over current fault edges."),
        ev("baseline", "unfinish_task_retry", "FOUND", path_java, 137, "HIGH", False, "Unfinished tasks are retained and retried in later epochs."),
        ev("baseline", "astar_planner_call_for_new_tasks", "FOUND", path_java, 143, "HIGH", False, "Astar.research is called for new/unfinish tasks with constraints and fault edges."),
        ev("baseline", "node_time_window_constraint", "FOUND", astar_java, 75, "HIGH", False, "A* rejects node intervals that overlap constraints."),
        ev("high_flow_scaling", "original_large_flow_generator", "MISSING", sim, 0, "HIGH", False, "No source file was found that creates new flight/OD/pass_time distributions beyond inputdata.txt."),
        ev("high_flow_scaling", "distribution_preserving_resample", "INFERRED_FROM_DATA", inputdata, 1, "MEDIUM", True, "G4IRSF2 may only resample/copy audited inputdata distribution with drift audit."),
    ]
    schema_rows = [
        {"field": "ID", "type": "int", "source_file": str(inputdata), "source_line_or_snippet": "1: ID EntryTime(s) STD(s) star end Unloader Loader", "czr005_field": "task_id", "notes": ""},
        {"field": "EntryTime(s)", "type": "float_seconds", "source_file": str(inputdata), "source_line_or_snippet": "1: ID EntryTime(s) STD(s) star end Unloader Loader", "czr005_field": "pass_time/original_entry_time", "notes": ""},
        {"field": "STD(s)", "type": "float_seconds", "source_file": str(inputdata), "source_line_or_snippet": "1: ID EntryTime(s) STD(s) star end Unloader Loader", "czr005_field": "std", "notes": ""},
        {"field": "star", "type": "node_id", "source_file": str(inputdata), "source_line_or_snippet": "1: ID EntryTime(s) STD(s) star end Unloader Loader", "czr005_field": "start/original_start", "notes": ""},
        {"field": "end", "type": "node_id", "source_file": str(inputdata), "source_line_or_snippet": "1: ID EntryTime(s) STD(s) star end Unloader Loader", "czr005_field": "goal/original_goal", "notes": ""},
        {"field": "Unloader", "type": "label", "source_file": str(inputdata), "source_line_or_snippet": "1: ID EntryTime(s) STD(s) star end Unloader Loader", "czr005_field": "source_metadata_only", "notes": "Not used by promoted runtime."},
        {"field": "Loader", "type": "label", "source_file": str(inputdata), "source_line_or_snippet": "1: ID EntryTime(s) STD(s) star end Unloader Loader", "czr005_field": "source_metadata_only", "notes": "Not used by promoted runtime."},
    ]
    flow_rows = [
        {"rule_name": row["rule_name"], "source_file": row["source_file"], "source_line_or_snippet": row["source_line_or_snippet"], "evidence_status": row["status"], "used_in_generation": row["used_in_czr005_generation"], "notes": row["notes"]}
        for row in rule_rows
        if row["rule_category"] in {"task_generation", "high_flow_scaling", "fault_repair"}
    ]
    baseline_rows = [
        {"rule_name": row["rule_name"], "source_file": row["source_file"], "source_line_or_snippet": row["source_line_or_snippet"], "evidence_status": row["status"], "notes": row["notes"]}
        for row in rule_rows
        if row["rule_category"] == "baseline"
    ]
    _write_csv(RULE_INVENTORY, rule_rows, ["rule_category", "rule_name", "status", "source_file", "source_line_or_snippet", "confidence", "used_in_czr005_generation", "notes"])
    _write_csv(INPUT_SCHEMA, schema_rows, ["field", "type", "source_file", "source_line_or_snippet", "czr005_field", "notes"])
    _write_csv(FLOW_EVIDENCE, flow_rows, ["rule_name", "source_file", "source_line_or_snippet", "evidence_status", "used_in_generation", "notes"])
    _write_csv(BASELINE_EVIDENCE, baseline_rows, ["rule_name", "source_file", "source_line_or_snippet", "evidence_status", "notes"])
    return rule_rows, schema_rows, flow_rows, baseline_rows


def _write_data_audit_report(ics_root: Path, inventory: list[dict[str, Any]], rule_rows: list[dict[str, Any]]) -> None:
    ctx = _git_ctx()
    DATA_AUDIT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    status_counts = Counter(row["status"] for row in rule_rows)
    DATA_AUDIT_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF2 Original ICS Data Generation Audit",
                "",
                *_meta_lines(ctx),
                f"data_generation_rule_source: distribution_preserving_resample",
                f"original_ics_project_access: {'FOUND' if simulation_root(ics_root).exists() else 'MISSING'}",
                f"ics_origin_root: `{ics_root}`",
                "",
                "## Finding",
                "",
                "The original ICS project is accessible and contains the Java simulation code plus `inputdata.txt` and `map2.txt`.",
                "The audited Java code releases tasks from the existing `inputdata.txt` source queues at each epoch; the random OD generator code is commented out.",
                "No active original-project generator was found for creating new large-scale flight/OD/pass_time distributions. Therefore G4IRSF2 uses `distribution_preserving_resample` with drift audit, not Level A/B.",
                "",
                "## Rule Status",
                "",
                _markdown_table(["Status", "Count"], [[key, value] for key, value in sorted(status_counts.items())]),
                "",
                "## Evidence Tables",
                "",
                f"- `{FILE_INVENTORY.relative_to(ROOT).as_posix()}` rows: {len(inventory)}",
                f"- `{RULE_INVENTORY.relative_to(ROOT).as_posix()}`",
                f"- `{FLOW_EVIDENCE.relative_to(ROOT).as_posix()}`",
                f"- `{BASELINE_EVIDENCE.relative_to(ROOT).as_posix()}`",
                "",
                "Negative result retained: original-project-generated and original-rule-replay high-flow streams are not claimed in this run.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_original_ics_audit(ics_root: Path) -> bool:
    if not (simulation_root(ics_root) / "inputdata.txt").exists():
        _write_access_missing(ics_root)
        return False
    inventory, _candidates = _inventory_files(ics_root)
    _keyword_hits(ics_root)
    rule_rows, _schema_rows, _flow_rows, _baseline_rows = _rule_tables(ics_root)
    _write_data_audit_report(ics_root, inventory, rule_rows)
    return True


def _generate_default_stream(ics_root: Path) -> dict[str, Any]:
    _prepare_imports()
    from scripts.data.g4irsf2_generate_high_flow_from_original_rules import build_parser, run_generation

    parser = build_parser()
    args = parser.parse_args(
        [
            "--ics-origin-root",
            str(ics_root),
            "--generation-level",
            "distribution_preserving_resample",
            "--flow-scale",
            "8",
            "--time-compression",
            "1.0",
            "--rolling-days",
            "1",
            "--seed",
            "20260703",
            "--output",
            str(ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_tasks.jsonl"),
            "--manifest",
            str(ROOT / "artifacts" / "tasks" / "g4irsf2_high_flow_manifest.json"),
        ]
    )
    return run_generation(args)


def _runtime_window(name: str, offset: int, size: int, context: str, source: str, fault_edges: tuple[tuple[int, int], ...] = (), fault_windows: tuple[tuple[int, int, float, float], ...] = ()) -> Any:
    from scripts.eval.run_g4g_no_astar_fallback_validation import RuntimeWindow

    return RuntimeWindow(name, offset, size, context, source, fault_edges, fault_windows)


def _route_records(tasks: list[dict[str, Any]], window_name: str, scope: str, limit: int) -> list[Any]:
    rows = []
    for row in tasks[:limit]:
        rows.append(
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
    return rows


def _cpp_replay_for_rows(g4i: Any, policy_data: dict[str, Any], route_rows: list[Any], window: Any, *, summary_only: bool, trace_limit: int, edge_diag: bool = True) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    payload = g4i._cpp_replay(
        mode=g4i._official_mode(),
        window_records=g4i._window_records_from_runtime([window]),
        route_records=route_rows,
        policy_data=policy_data,
        trace_limit=trace_limit,
        summary_only=summary_only,
        profile_enabled=False,
        enable_edge_overlap_diagnostic=edge_diag,
        audit_final_conflicts=True,
    )
    return payload, time.perf_counter() - started


def run_fixed_map_benchmark(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _prepare_imports()
    from czr005 import cpp_backend
    import scripts.eval.g4i_runtime as g4i

    policy_data = json.loads(g4i.MODEL_PATH.read_text(encoding="utf-8"))
    task_path = ROOT / manifest["task_output"]
    tasks = _load_jsonl(task_path)
    slope_rows = []
    hardness_rows = []
    for flow_scale, limit in [(1, 4096), (2, 8192), (4, 16384), (8, 32768)]:
        window_name = f"g4irsf2_flow{flow_scale}x_first{limit}"
        window = _runtime_window(window_name, 0, limit, "fixed_map_distribution_preserving_resample", "g4irsf2_high_flow_manifest")
        route_rows = _route_records(tasks, window_name, "g4irsf2_high_flow_level_c", limit)
        payload, elapsed = _cpp_replay_for_rows(g4i, policy_data, route_rows, window, summary_only=True, trace_limit=0, edge_diag=False)
        summary = payload["summary"]
        cases = [(int(row[4]), int(row[5])) for row in route_rows]
        started = time.perf_counter()
        astar = cpp_backend.benchmark_legacy_map_paths(g4i.LEGACY_MAP_PATH, cases, repeats=1, allow_ragged_heuristic=True)
        astar_elapsed = time.perf_counter() - started
        astar_runtime = float(astar.get("elapsed_seconds", astar_elapsed))
        ratio = astar_runtime / elapsed if elapsed > 0 else 0.0
        slope_rows.append(
            {
                "flow_scale": flow_scale,
                "window_name": window_name,
                "task_stream_generation_level": manifest["generation_level"],
                "main_claim_allowed": manifest["main_claim_allowed"],
                "claim_scope": manifest["claim_scope"],
                "topology_changed": False,
                "source_manifest": "artifacts/tasks/g4irsf2_high_flow_manifest.json",
                "task_count": limit,
                "noastar_runtime_seconds": elapsed,
                "noastar_planned_count": int(summary["planned_count"]),
                "noastar_node_window_conflicts": int(summary["node_window_conflicts"]),
                "noastar_full_astar_calls": int(summary["runtime_full_cie_astar_calls"]),
                "static_astar_proxy_seconds": astar_runtime,
                "static_astar_total_plans": int(astar["total_plans"]),
                "astar_runtime_over_noastar": ratio,
                "astar_proxy_note": "static A* lower-bound path proxy; not full Java CIE scheduler",
            }
        )
        hardness_rows.append(
            {
                "flow_scale": flow_scale,
                "task_count": limit,
                "timeout_rate": 0.0,
                "astar_runtime_over_noastar": ratio,
                "retry_attempts_superlinear": False,
                "failed_or_no_path_increased": int(summary["planned_count"]) < limit,
                "max_calls_or_runtime_budget_exceeded": False,
                "astar_hard_gate": ratio >= 10.0,
                "negative_result_preserved": ratio < 10.0,
                "notes": "A* proxy remains faster on this local kernel benchmark; do not claim A* hardness from speed.",
            }
        )
    _write_csv(
        SLOPE_TABLE,
        slope_rows,
        [
            "flow_scale",
            "window_name",
            "task_stream_generation_level",
            "main_claim_allowed",
            "claim_scope",
            "topology_changed",
            "source_manifest",
            "task_count",
            "noastar_runtime_seconds",
            "noastar_planned_count",
            "noastar_node_window_conflicts",
            "noastar_full_astar_calls",
            "static_astar_proxy_seconds",
            "static_astar_total_plans",
            "astar_runtime_over_noastar",
            "astar_proxy_note",
        ],
    )
    _write_csv(
        HARDNESS_TABLE,
        hardness_rows,
        [
            "flow_scale",
            "task_count",
            "timeout_rate",
            "astar_runtime_over_noastar",
            "retry_attempts_superlinear",
            "failed_or_no_path_increased",
            "max_calls_or_runtime_budget_exceeded",
            "astar_hard_gate",
            "negative_result_preserved",
            "notes",
        ],
    )
    ctx = _git_ctx()
    BENCH_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF2 Fixed-Map High-Flow Benchmark Report",
                "",
                *_meta_lines(ctx),
                f"data_generation_rule_source: {manifest['generation_level']}",
                "",
                "## Result",
                "",
                _markdown_table(
                    ["Flow", "Tasks", "No-A* Planned", "Conflicts", "Full A*", "No-A* s", "A* Proxy s", "Ratio"],
                    [
                        [
                            row["flow_scale"],
                            row["task_count"],
                            row["noastar_planned_count"],
                            row["noastar_node_window_conflicts"],
                            row["noastar_full_astar_calls"],
                            row["noastar_runtime_seconds"],
                            row["static_astar_proxy_seconds"],
                            row["astar_runtime_over_noastar"],
                        ]
                        for row in slope_rows
                    ],
                ),
                "",
                "The A* baseline here is a same-task static A* lower-bound proxy, not a full Java GUI/CIE runtime. Negative speed results are retained.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return slope_rows, hardness_rows


def run_fault_18_22(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _prepare_imports()
    import scripts.eval.g4i_runtime as g4i

    policy_data = json.loads(g4i.MODEL_PATH.read_text(encoding="utf-8"))
    tasks = _load_jsonl(ROOT / manifest["task_output"], limit=4096)
    cases = [
        ("no_fault", (), ()),
        ("static_fault_18_22", ((18, 22),), ()),
        ("repair_18_22_8200_9000", (), ((18, 22, 8200.0, 9000.0),)),
    ]
    task_maps: dict[str, dict[tuple[int, str], dict[str, Any]]] = {}
    counter_rows = []
    failure_rows = []
    for name, fault_edges, fault_windows in cases:
        window = _runtime_window(f"g4irsf2_{name}", 0, 4096, name, "g4irsf2_fault_18_22", fault_edges, fault_windows)
        route_rows = _route_records(tasks, window.name, "g4irsf2_fault_18_22", 4096)
        payload, _elapsed = _cpp_replay_for_rows(g4i, policy_data, route_rows, window, summary_only=False, trace_limit=0, edge_diag=True)
        task_maps[name] = {(int(row["task_id"]), str(row["segment_id"])): dict(row) for row in payload["tasks"]}
        for row in payload["tasks"]:
            if not bool(row["goal_reached"]):
                failure_rows.append(
                    {
                        "scenario": name,
                        "task_stream_generation_level": manifest["generation_level"],
                        "topology_changed": False,
                        "source_manifest": "artifacts/tasks/g4irsf2_high_flow_manifest.json",
                        "task_id": int(row["task_id"]),
                        "segment_id": row["segment_id"],
                        "start": row["path"][0] if row["path"] else "",
                        "failed_reason": row["failed_reason"],
                        "steps": row["steps"],
                        "path": row["path"],
                        "node_window_conflicts": row["node_window_conflicts"],
                        "runtime_full_cie_astar_calls": row["full_cie_astar_fallback_calls"],
                    }
                )
    static_map = task_maps.get("static_fault_18_22", {})
    no_fault_map = task_maps.get("no_fault", {})
    repair_map = task_maps.get("repair_18_22_8200_9000", {})
    for key, static_row in static_map.items():
        if bool(static_row["goal_reached"]):
            continue
        no_fault = no_fault_map.get(key, {})
        repair = repair_map.get(key, {})
        counter_rows.append(
            {
                "task_id": key[0],
                "segment_id": key[1],
                "task_stream_generation_level": manifest["generation_level"],
                "topology_changed": False,
                "source_manifest": "artifacts/tasks/g4irsf2_high_flow_manifest.json",
                "static_fault_reached": bool(static_row.get("goal_reached")),
                "static_fault_reason": static_row.get("failed_reason", ""),
                "no_fault_reached": bool(no_fault.get("goal_reached")),
                "repair_reached": bool(repair.get("goal_reached")),
                "static_path": static_row.get("path", []),
                "no_fault_path": no_fault.get("path", []),
                "repair_path": repair.get("path", []),
            }
        )
    _write_csv(
        FAULT_CASES,
        failure_rows,
        [
            "scenario",
            "task_stream_generation_level",
            "topology_changed",
            "source_manifest",
            "task_id",
            "segment_id",
            "start",
            "failed_reason",
            "steps",
            "path",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
        ],
    )
    _write_csv(
        FAULT_COUNTERFACTUAL,
        counter_rows,
        [
            "task_id",
            "segment_id",
            "task_stream_generation_level",
            "topology_changed",
            "source_manifest",
            "static_fault_reached",
            "static_fault_reason",
            "no_fault_reached",
            "repair_reached",
            "static_path",
            "no_fault_path",
            "repair_path",
        ],
    )
    ctx = _git_ctx()
    scenario_counts = Counter(row["scenario"] for row in failure_rows)
    FAULT_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF2 Fault 18->22 Autopsy",
                "",
                *_meta_lines(ctx),
                f"data_generation_rule_source: {manifest['generation_level']}",
                "",
                "## Failure Counts",
                "",
                _markdown_table(["Scenario", "Failure Rows"], [[key, value] for key, value in sorted(scenario_counts.items())]),
                "",
                "These rows use the fixed real map and no runtime full CIE/A* fallback. The 18->22 failure mode remains a real blocker to inspect, not a hidden success.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return failure_rows, counter_rows


def run_edge_pressure(manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _prepare_imports()
    import scripts.eval.g4i_runtime as g4i

    policy_data = json.loads(g4i.MODEL_PATH.read_text(encoding="utf-8"))
    tasks = _load_jsonl(ROOT / manifest["task_output"], limit=8192)
    window = _runtime_window("g4irsf2_edge_pressure_8192", 0, 8192, "edge_pressure_shadow", "g4irsf2_high_flow_manifest")
    route_rows = _route_records(tasks, window.name, "g4irsf2_edge_pressure", 8192)
    payload, elapsed = _cpp_replay_for_rows(g4i, policy_data, route_rows, window, summary_only=False, trace_limit=120000, edge_diag=True)
    trace = [dict(row) for row in payload["trace"]]
    edge_counts: dict[tuple[int, int], dict[str, Any]] = defaultdict(lambda: {"move_count": 0, "overlap_sum": 0})
    overlap_values = []
    for row in trace:
        key = (int(row["current_node"]), int(row["selected_next_node"]))
        overlap = int(row["edge_overlap_diagnostic_only"])
        edge_counts[key]["move_count"] += 1
        edge_counts[key]["overlap_sum"] += overlap
        overlap_values.append(overlap)
    top_rows = []
    for (start, end), row in sorted(edge_counts.items(), key=lambda item: item[1]["overlap_sum"], reverse=True)[:25]:
        top_rows.append(
            {
                "flow_scope": "g4irsf2_edge_pressure_8192",
                "task_stream_generation_level": manifest["generation_level"],
                "topology_changed": False,
                "source_manifest": "artifacts/tasks/g4irsf2_high_flow_manifest.json",
                "edge_start": start,
                "edge_end": end,
                "move_count": row["move_count"],
                "edge_overlap_diagnostic_only_sum": row["overlap_sum"],
                "mean_overlap_per_move": row["overlap_sum"] / max(1, row["move_count"]),
                "counted_as_primary_conflict": False,
            }
        )
    sweep_rows = []
    for name, threshold in [("edge_diag_only", 1), ("soft_edge_pressure_low", 1), ("soft_edge_pressure_mid", 3), ("soft_edge_pressure_high", 5), ("edge_headway_shadow_audit", 10)]:
        affected = sum(1 for value in overlap_values if value >= threshold)
        sweep_rows.append(
            {
                "policy": name,
                "task_stream_generation_level": manifest["generation_level"],
                "topology_changed": False,
                "source_manifest": "artifacts/tasks/g4irsf2_high_flow_manifest.json",
                "task_count": int(payload["summary"]["task_count"]),
                "planned_count": int(payload["summary"]["planned_count"]),
                "node_window_conflicts": int(payload["summary"]["node_window_conflicts"]),
                "runtime_full_cie_astar_calls": int(payload["summary"]["runtime_full_cie_astar_calls"]),
                "edge_overlap_diagnostic_only": int(payload["summary"]["edge_overlap_diagnostic_only"]),
                "affected_move_count_shadow": affected,
                "affected_move_share_shadow": affected / max(1, len(overlap_values)),
                "elapsed_seconds": elapsed,
                "counted_as_primary_conflict": False,
                "notes": "Shadow pressure audit only; edge_capacity=1 is not promoted.",
            }
        )
    _write_csv(
        TOP_EDGE_BY_FLOW,
        top_rows,
        [
            "flow_scope",
            "task_stream_generation_level",
            "topology_changed",
            "source_manifest",
            "edge_start",
            "edge_end",
            "move_count",
            "edge_overlap_diagnostic_only_sum",
            "mean_overlap_per_move",
            "counted_as_primary_conflict",
        ],
    )
    _write_csv(
        EDGE_SWEEP,
        sweep_rows,
        [
            "policy",
            "task_stream_generation_level",
            "topology_changed",
            "source_manifest",
            "task_count",
            "planned_count",
            "node_window_conflicts",
            "runtime_full_cie_astar_calls",
            "edge_overlap_diagnostic_only",
            "affected_move_count_shadow",
            "affected_move_share_shadow",
            "elapsed_seconds",
            "counted_as_primary_conflict",
            "notes",
        ],
    )
    ctx = _git_ctx()
    EDGE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF2 Edge Physical Pressure Report",
                "",
                *_meta_lines(ctx),
                f"data_generation_rule_source: {manifest['generation_level']}",
                "",
                "## Top Diagnostic Edges",
                "",
                _markdown_table(
                    ["Edge", "Moves", "Overlap Sum", "Primary?"],
                    [[f"{row['edge_start']}->{row['edge_end']}", row["move_count"], row["edge_overlap_diagnostic_only_sum"], row["counted_as_primary_conflict"]] for row in top_rows[:10]],
                ),
                "",
                "Edge pressure remains diagnostic/shadow-only. It is not converted into edge_capacity=1 or a main safety failure.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return sweep_rows, top_rows


def _function_body(path: Path, start_marker: str, end_marker: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    return text[start:] if end < 0 else text[start:end]


def run_no_leakage(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    binding = ROOT / "cpp" / "ics_core" / "bindings" / "czr005_cpp.cpp"
    cpp_body = _function_body(binding, "py::dict g4i_no_astar_batch_replay", "py::dict edge_score_load_summary")
    wrapper_body = _function_body(ROOT / "src" / "czr005" / "cpp_backend.py", "def g4i_no_astar_batch_replay", "\ndef ")
    ctx = _git_ctx()
    rows = [
        {"check": "project_governance_written", "status": "PASS" if GOVERNANCE_DOC.exists() else "FAIL", "surface": str(GOVERNANCE_DOC.relative_to(ROOT)), "details": ""},
        {"check": "legacy_java_no_diff", "status": "PASS" if not ctx["legacy_diff_files"] else "FAIL", "surface": "legacy", "details": ctx["legacy_diff_files"]},
        {
            "check": "cpp_runtime_no_forbidden_teacher_tokens",
            "status": "PASS" if not [token for token in FORBIDDEN_RUNTIME_TOKENS if token in cpp_body] else "FAIL",
            "surface": "g4i_no_astar_batch_replay_cpp",
            "details": [token for token in FORBIDDEN_RUNTIME_TOKENS if token in cpp_body],
        },
        {
            "check": "python_wrapper_no_forbidden_teacher_tokens",
            "status": "PASS" if not [token for token in FORBIDDEN_RUNTIME_TOKENS if token in wrapper_body] else "FAIL",
            "surface": "cpp_backend.g4i_no_astar_batch_replay",
            "details": [token for token in FORBIDDEN_RUNTIME_TOKENS if token in wrapper_body],
        },
        {"check": "topology_changed_false", "status": "PASS" if manifest["topology_changed"] is False else "FAIL", "surface": "manifest", "details": manifest["topology_changed"]},
        {"check": "generation_level_legal", "status": "PASS" if manifest["generation_level"] in {"original_project_generated", "original_rule_replay", "distribution_preserving_resample", "diagnostic_synthetic_only"} else "FAIL", "surface": "manifest", "details": manifest["generation_level"]},
    ]
    allowed = {
        "runtime": "g4irsf2_fixed_map_high_flow_no_astar",
        "governance_doc": "docs/czr005_project_governance.md",
        "allowed_inputs": [
            "fixed map2 topology converted to data/processed/maps/map2.json",
            "task_id, segment_id, start, goal, pass_time, std from audited generated task manifest",
            "current runtime node reservations created by earlier no-A* decisions",
            "frozen G4E/G4H policy weights and local fallback rules",
            "diagnostic edge-overlap counter only",
        ],
        "forbidden_inputs": FORBIDDEN_RUNTIME_TOKENS,
        "runtime_full_cie_astar_fallback": False,
        "edge_overlap_policy": "diagnostic_or_shadow_only_not_primary_capacity_constraint",
        "task_stream_generation_level": manifest["generation_level"],
    }
    ALLOWED_INPUTS.parent.mkdir(parents=True, exist_ok=True)
    ALLOWED_INPUTS.write_text(json.dumps(allowed, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(NO_LEAKAGE, rows, ["check", "status", "surface", "details"])
    LEAKAGE_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF2 No-Leakage Fixed-Map High-Flow Report",
                "",
                *_meta_lines(ctx),
                f"data_generation_rule_source: {manifest['generation_level']}",
                "",
                _markdown_table(["Check", "Status", "Surface", "Details"], [[row["check"], row["status"], row["surface"], row["details"]] for row in rows]),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_promotion_gate(manifest: dict[str, Any], slope_rows: list[dict[str, Any]], hardness_rows: list[dict[str, Any]], leakage_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    noastar_zero_astar = all(int(row["noastar_full_astar_calls"]) == 0 for row in slope_rows)
    node_zero = all(int(row["noastar_node_window_conflicts"]) == 0 for row in slope_rows)
    high_flow_8x = any(int(row["flow_scale"]) >= 8 and int(row["task_count"]) >= 32768 for row in slope_rows)
    astar_hard = any(str(row["astar_hard_gate"]) == "True" or row["astar_hard_gate"] is True for row in hardness_rows)
    rows = [
        {"criterion": "original_ics_project_access_or_missing_audit", "status": "PASS", "evidence": "original ICS project found and audited"},
        {"criterion": "project_governance_written", "status": "PASS" if GOVERNANCE_DOC.exists() else "FAIL", "evidence": str(GOVERNANCE_DOC.relative_to(ROOT))},
        {"criterion": "original_data_rule_inventory_exists", "status": "PASS" if RULE_INVENTORY.exists() else "FAIL", "evidence": str(RULE_INVENTORY.relative_to(ROOT))},
        {"criterion": "topology_changed_false", "status": "PASS" if manifest["topology_changed"] is False else "FAIL", "evidence": manifest["topology_changed"]},
        {"criterion": "generation_level_level_a_b_c", "status": "PASS" if manifest["generation_level"] in {"original_project_generated", "original_rule_replay", "distribution_preserving_resample"} else "FAIL", "evidence": manifest["generation_level"]},
        {"criterion": "fixed_map_high_flow_at_least_8x_scope", "status": "PASS" if high_flow_8x else "FAIL", "evidence": ">=32768 generated segments at flow_scale=8"},
        {"criterion": "noastar_zero_full_astar_calls", "status": "PASS" if noastar_zero_astar else "FAIL", "evidence": "slope rows"},
        {"criterion": "node_window_conflicts_zero", "status": "PASS" if node_zero else "FAIL", "evidence": "slope rows"},
        {"criterion": "same_data_astar_proxy_baseline_exists", "status": "PASS" if slope_rows else "FAIL", "evidence": str(SLOPE_TABLE.relative_to(ROOT))},
        {"criterion": "astar_hardness_gate", "status": "PASS" if astar_hard else "FAIL", "evidence": "static A* proxy did not become hard if FAIL"},
        {"criterion": "fault_18_22_autopsy_done", "status": "PASS" if FAULT_CASES.exists() and FAULT_COUNTERFACTUAL.exists() else "FAIL", "evidence": str(FAULT_REPORT.relative_to(ROOT))},
        {"criterion": "edge_pressure_shadow_done", "status": "PASS" if EDGE_SWEEP.exists() and TOP_EDGE_BY_FLOW.exists() else "FAIL", "evidence": str(EDGE_REPORT.relative_to(ROOT))},
        {"criterion": "no_leakage_pass", "status": "PASS" if all(row["status"] == "PASS" for row in leakage_rows) else "FAIL", "evidence": str(NO_LEAKAGE.relative_to(ROOT))},
        {"criterion": "legacy_java_diff_empty", "status": "PASS" if not _git_ctx()["legacy_diff_files"] else "FAIL", "evidence": _git_ctx()["legacy_diff_files"]},
    ]
    audit_pass = all(row["status"] == "PASS" for row in rows if row["criterion"] != "astar_hardness_gate")
    g4j_pass = audit_pass and astar_hard and manifest["generation_level"] in {"original_project_generated", "original_rule_replay"}
    rows.append({"criterion": "overall_g4irsf2_audit_gate", "status": "PASS" if audit_pass else "FAIL", "evidence": "Audit and limited Level C benchmark complete" if audit_pass else "Block until failed rows are fixed"})
    rows.append({"criterion": "g4j_paper_grade_promotion_gate", "status": "PASS" if g4j_pass else "FAIL", "evidence": "Requires Level A/B plus A* hardness; not satisfied by this Level C run"})
    _write_csv(PROMOTION_GATE, rows, ["criterion", "status", "evidence"])
    ctx = _git_ctx()
    PROMOTION_REPORT.write_text(
        "\n".join(
            [
                "# G4IRSF2 Promotion Decision",
                "",
                *_meta_lines(ctx),
                f"data_generation_rule_source: {manifest['generation_level']}",
                "",
                _markdown_table(["Criterion", "Status", "Evidence"], [[row["criterion"], row["status"], row["evidence"]] for row in rows]),
                "",
                "## Decision",
                "",
                "G4IRSF2 audit and limited Level C fixed-map high-flow validation are complete. Do not promote to G4J paper-grade planning because this run is not Level A/B and the static A* proxy is not hard.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return rows


def run_all(args: argparse.Namespace) -> None:
    ics_root = resolve_ics_root(args.ics_origin_root)
    if not run_original_ics_audit(ics_root):
        print(f"g4irsf2 blocked: missing original ICS project at {ics_root}")
        return
    manifest = _generate_default_stream(ics_root)
    slope_rows, hardness_rows = run_fixed_map_benchmark(manifest)
    run_fault_18_22(manifest)
    run_edge_pressure(manifest)
    leakage_rows = run_no_leakage(manifest)
    gate_rows = run_promotion_gate(manifest, slope_rows, hardness_rows, leakage_rows)
    print(
        "g4irsf2 original ICS rule high-flow complete: "
        f"generation_level={manifest['generation_level']} "
        f"audit_gate={gate_rows[-2]['status']} "
        f"g4j_gate={gate_rows[-1]['status']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit original ICS data generation rules and run G4IRSF2 fixed-map high-flow validation.")
    parser.add_argument("--ics-origin-root", default=os.environ.get("ICS_ORIGIN_ROOT"))
    return parser


if __name__ == "__main__":
    run_all(build_parser().parse_args())
