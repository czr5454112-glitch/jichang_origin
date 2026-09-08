"""Independent HCA paper-suite adapter; full population only timing at every load.

Base and first-round-known all-day directed edge failures are implemented.
Runtime failure notifications and propagation are separate, unsupported modes.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import stat
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external
from scripts.eval.run_feng_paper_env_cie_dh import _aggregate_sha256 as content_sha

METHOD = "HCA_TIME_LABEL_REPAIR_V3"
SCHEMA = "czr005.hca_paper_suite_result.v1"

ISOLATED = ROOT / "benchmarks/java/hca_paper_suite_v3"
WRAPPER = ISOLATED / "HcaPaperSuiteBenchmark.java"
BUILD_NAME = "build_identity.json"
HORIZON = 98259.0
STATS = ("min", "mean", "p95", "p99", "max")
PRIMARY = tuple(f"tht_scheduled_release_{s}_seconds" for s in STATS)
SECONDARY = tuple(f"tht_admission_{s}_seconds" for s in STATS)
FORMAL_TIMING = set(PRIMARY + SECONDARY) | set(external.TIMING_METRICS)
NATIVE_FILES = ("segment_execution_identity.csv", "execution_terminal.csv", "release.csv",
                "routes.csv", "outputstarttime.txt", "output.txt", "summary.csv", "suite_audit.csv")
OPTIONAL_ZERO_EVENT_LOGS = {"outputstarttime.txt", "output.txt"}
DERIVED_FILES = ("segment_lifecycle.csv", "raw_bag_timings.csv", "population_audit.json")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha(path: Path) -> str:
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    external._atomic_json(Path(path), value)


def rows(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, values: list[dict]) -> None:
    require(bool(values), "cannot write empty population table")
    with Path(path).open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(values[0]))
        writer.writeheader()
        writer.writerows(values)


def close(a: object, b: object, label: str) -> None:
    left, right = float(a), float(b)
    require(math.isfinite(left) and math.isfinite(right) and abs(left-right) <= 1e-6,
            f"{label}: {a} != {b}")


def source_files() -> list[Path]:
    return [*sorted((ISOLATED / "App").glob("*.java")), ISOLATED / "ICS_GUI/ICS_GUI.java", WRAPPER]


def file_set(paths: list[Path], base: Path) -> list[dict]:
    return [{"path": p.resolve().relative_to(base.resolve()).as_posix(), "sha256": sha(p),
             "size_bytes": p.stat().st_size} for p in sorted(paths)]


def set_sha(records: list[dict]) -> str:
    return hashlib.sha256("".join(f"{r['path']}\0{r['sha256']}\n" for r in records).encode()).hexdigest()


def tool_identity(path: str) -> dict:
    resolved = Path(path).resolve(strict=True)
    p = subprocess.run([str(resolved), "-version"], capture_output=True, text=True, check=True)
    return {"path": str(resolved), "sha256": sha(resolved), "version": (p.stdout+p.stderr).strip()}


def verify_build(classes_dir: Path, java: str | None = None, javac: str | None = None) -> dict:
    classes_dir = Path(classes_dir).resolve(strict=True)
    value = read_json(classes_dir / BUILD_NAME)
    require(value.get("schema") == "czr005.hca_paper_suite_build.v1" and value.get("method") == METHOD,
            "wrong or missing frozen HCA execution-ID build")
    sources = file_set(source_files(), ROOT)
    classes = file_set(list(classes_dir.rglob("*.class")), classes_dir)
    require(sources == value["source_files"] and set_sha(sources) == value["source_sha256"], "source drift")
    require(classes and classes == value["class_files"] and set_sha(classes) == value["class_sha256"], "class drift")
    require(content_sha(source_files(), ROOT) == value["source_content_aggregate_sha256"], "source content aggregate drift")
    require(content_sha(classes_dir.rglob("*.class"), classes_dir) == value["class_content_aggregate_sha256"], "class content aggregate drift")
    for key, path in (("java", java), ("javac", javac)):
        if path is not None:
            require(tool_identity(path) == value[key], f"{key} runtime/compiler drift")
    return value


def compile_production(classes_dir: Path, java: str, javac: str) -> dict:
    """Compile once into an empty directory; an existing build is only verified."""
    classes_dir = Path(classes_dir).resolve()
    if (classes_dir / BUILD_NAME).exists():
        return verify_build(classes_dir, java, javac)
    require(not classes_dir.exists() or not any(classes_dir.iterdir()), "compile requires an empty new directory")
    classes_dir.mkdir(parents=True, exist_ok=True)
    sources = file_set(source_files(), ROOT)
    command = [str(Path(javac).resolve()), "-encoding", "UTF-8", "-d", str(classes_dir),
               *[str(p.resolve()) for p in source_files()]]
    subprocess.run(command, cwd=ROOT, check=True)
    classes = file_set(list(classes_dir.rglob("*.class")), classes_dir)
    require(classes, "compiler produced no classes")
    value = {"schema": "czr005.hca_paper_suite_build.v1", "method": METHOD,
             "source_files": sources, "source_sha256": set_sha(sources),
             "class_files": classes, "class_sha256": set_sha(classes),
             "manifest_aggregate_algorithm": "SHA256_CONCAT_RELATIVE_PATH_NUL_FILE_SHA256_NEWLINE",
             "source_content_aggregate_sha256": content_sha(source_files(), ROOT),
             "class_content_aggregate_sha256": content_sha(classes_dir.rglob("*.class"), classes_dir),
             "content_aggregate_algorithm": "FENG_SHA256_SORTED_RELATIVE_PATH_AND_CONTENT_WITH_UINT64_BIG_ENDIAN_LENGTH_PREFIXES",
             "java": tool_identity(java), "javac": tool_identity(javac), "compile_command": command,
             "classes_dir": str(classes_dir), "compiled_at": datetime.now(timezone.utc).isoformat()}
    write_json(classes_dir / BUILD_NAME, value)
    return verify_build(classes_dir, java, javac)


def indexed(values: list[dict], key: str, label: str) -> dict[int, dict]:
    result = {}
    for row in values:
        identity = int(row[key])
        require(identity not in result, f"duplicate {label} execution ID {identity}")
        result[identity] = row
    return result


def parse_events(path: Path, planning: bool) -> list[dict]:
    result = []
    if not path.exists():
        require(path.name in OPTIONAL_ZERO_EVENT_LOGS, "unexpected missing event file")
        return result  # caller must independently prove the native event counter and state count are zero
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split()
        require(len(parts) == (4 if planning else 2), f"invalid event row in {path.name}")
        row = {"task_id": int(parts[0])}
        if planning:
            row.update(start=int(parts[1]), legacy_task_pass_time=float(parts[2]), processed_attempt_epoch=float(parts[3]))
        else:
            row["finish_epoch"] = float(parts[1])
        result.append(row)
    return result


def audit_records(canonical: list[dict], mappings: list[dict], releases: list[dict], plans: list[dict],
                  completions: list[dict], terminals: list[dict], summary: dict,
                  route_rows: list[dict] | None = None, raw_order: list[int] | None = None,
                  *, expected_speed_mps: float = 2.5, expected_fault_count: int = 0) -> tuple[list[dict], dict]:
    """Pure exact-ID audit, independent of derived lifecycle/timing CSVs."""
    canonical_by_key = {}
    for row in canonical:
        key = (int(row["task_id"]), row["leg"])
        require(key not in canonical_by_key, "duplicate canonical raw/leg identity")
        canonical_by_key[key] = row
    m = indexed(mappings, "execution_id", "mapping")
    t = indexed(terminals, "execution_id", "terminal")
    r, p, c = (indexed(v, "task_id", label) for v, label in
               ((releases, "release"), (plans, "successful planning"), (completions, "completion")))
    require(len(m) == len(canonical) and set(t) == set(m), "mapping/terminal population mismatch")
    require(set(c) <= set(p) <= set(r) <= set(m), "foreign or causally missing execution event")
    raw_order = raw_order or list(dict.fromkeys(int(row["task_id"]) for row in canonical))
    require(set(raw_order) == {key[0] for key in canonical_by_key}, "raw identity coverage mismatch")
    next_id = max(raw_order) + 1
    expected_ids = {}
    for raw_id in raw_order:
        for leg in ("direct", "storage_in", "storage_out"):
            if (raw_id, leg) in canonical_by_key:
                expected_ids[(raw_id, leg)] = next_id if leg == "storage_out" else raw_id
                if leg == "storage_out":
                    next_id += 1
    seen_keys = set()
    lifecycle = []
    states = Counter()
    for execution_id, mapping in m.items():
        key = (int(mapping["raw_task_id"]), mapping["leg"])
        require(key in canonical_by_key and key not in seen_keys, "foreign/duplicate mapped canonical segment")
        seen_keys.add(key)
        can = canonical_by_key[key]
        require(execution_id == expected_ids[key], "execution-ID allocation differs from frozen raw-order rule")
        for field in ("start", "goal"):
            require(int(mapping[field]) == int(can[field]), f"mapping {field} mismatch")
        for a, b in (("scheduled_release_seconds", "pass_time"), ("original_entry_seconds", "original_entry_time"),
                     ("deadline_seconds", "std")):
            close(mapping[a], can[b], f"mapping {a}")
        release = float(r[execution_id]["release_epoch"]) if execution_id in r else None
        planned = float(p[execution_id]["processed_attempt_epoch"]) if execution_id in p else None
        finish = float(c[execution_id]["finish_epoch"]) if execution_id in c else None
        if release is not None:
            for field in ("start", "goal"):
                require(int(r[execution_id][field]) == int(can[field]), "release OD mismatch")
            require(8260 <= release <= HORIZON and float(can["pass_time"])-release < 1+1e-6,
                    "release violates unchanged integer-clock rule")
        if planned is not None:
            require(int(p[execution_id]["start"]) == int(can["start"]), "plan source mismatch")
            require(release <= planned <= HORIZON, "planning time precedes release or exceeds horizon")
        if finish is not None:
            require(planned <= finish <= HORIZON, "completion precedes planning or exceeds horizon")
        terminal = t[execution_id]
        for field in ("raw_task_id", "leg", "start", "goal"):
            require(str(terminal[field]) == str(mapping[field]), f"terminal {field} mismatch")
        close(terminal["scheduled_release_seconds"], can["pass_time"], "terminal scheduled release")
        for field, value in (("release_epoch", release), ("planned_epoch", planned), ("completion_epoch", finish)):
            if value is None:
                require(terminal[field] in ("", None), f"unexpected terminal {field}")
            else:
                close(terminal[field], value, f"terminal {field}")
        state = terminal["terminal_state"]
        expected_state = "COMPLETED" if finish is not None else "ACTIVE_ROUTE" if planned is not None else \
                         "UNPLANNED" if release is not None else "NOT_RELEASED"
        require(state == expected_state, f"native terminal/event mismatch execution {execution_id}: {state}/{expected_state}")
        def is_true(value: object) -> bool:
            require(str(value).lower() in {"true", "false", "1", "0"}, "invalid terminal membership flag")
            return str(value).lower() in {"true", "1"}
        members = [is_true(terminal[field]) for field in ("active_route_member", "unplanned_member", "source_pending_member")]
        require(members == [state == "ACTIVE_ROUTE", state == "UNPLANNED", state == "NOT_RELEASED"],
                "actual native membership sets violate terminal state")
        states[state] += 1
        lifecycle.append({"execution_id": execution_id, "segment_id": can["segment_id"], "task_id": key[0],
                          "leg": key[1], "start": can["start"], "goal": can["goal"],
                          "original_entry_time": can["original_entry_time"], "scheduled_pass_time": can["pass_time"],
                          "release_epoch": release, "processed_attempt_epoch": planned, "finish_epoch": finish,
                          "legacy_planning_task_pass_time": p[execution_id].get("legacy_task_pass_time") if execution_id in p else None,
                          "terminal_state": state, "complete": finish is not None})
    require(seen_keys == set(canonical_by_key), "canonical segment omitted")
    for route in route_rows or []:
        eid = int(route["task_id"])
        require(eid in p, "exported route has no successful planning event")
        for field in ("start", "goal"):
            require(int(route[field]) == int(m[eid][field]), "exported route OD mismatch")
        close(route["epoch"], p[eid]["processed_attempt_epoch"], "route planning epoch")
        close(route["finish_time"], t[eid]["planned_finish_epoch"], "terminal predicted finish time")
    if route_rows is not None:
        require(set(indexed(route_rows, "task_id", "route export")) == set(p), "successful plans/routes coverage differs")
    for field, expected in {"generated_count": len(r), "planned_count": len(p), "completed_count": len(c),
                            "active_route_count": states["ACTIVE_ROUTE"], "unfinished_count": states["UNPLANNED"]}.items():
        require(int(summary[field]) == expected, f"summary {field} differs from exact-ID evidence")
    for field, expected in {"repeat": 1, "start_epoch": 8260, "max_epochs": 90000, "max_new_tasks": 0,
                            "epochs_run": 90000, "last_epoch": HORIZON, "speed_mps": expected_speed_mps,
                            "fault_event_count": expected_fault_count, "repair_event_count": 0,
                            "active_fault_count": expected_fault_count,
                            "generated_fault_edge_count": expected_fault_count, "generated_repair_edge_count": 0}.items():
        close(summary[field], expected, f"fixed run contract {field}")
    residual = len(r)-len(c)-states["ACTIVE_ROUTE"]-states["UNPLANNED"]
    require(residual == 0, "positive/negative terminal segment accounting residual")
    overlap = []
    by_raw = defaultdict(dict)
    for row in lifecycle:
        by_raw[row["task_id"]][row["leg"]] = row
    for raw, legs in by_raw.items():
        if "storage_in" in legs:
            first, second = legs["storage_in"], legs["storage_out"]
            if second["processed_attempt_epoch"] is not None and (first["finish_epoch"] is None or
                    second["processed_attempt_epoch"] < first["finish_epoch"]):
                overlap.append(raw)
    return lifecycle, {"schema": "czr005.hca_paper_suite_population_audit.v1", "status": "PASS",
        "canonical_segment_count": len(canonical), "raw_bag_count": len(by_raw),
        "execution_id_count": len(m), "released_segment_count": len(r), "planned_segment_count": len(p),
        "completed_segment_count": len(c), "terminal_state_counts": dict(states), "terminal_accounting_residual": residual,
        "ebs_storage_out_planned_before_storage_in_completed_count": len(overlap),
        "ebs_overlap_raw_task_ids": sorted(overlap),
        "coverage": "EXACT_EXECUTION_ID_MAPPING_EVENTS_NATIVE_TERMINAL_AND_FULL_CANONICAL_POPULATION",
        "limitations": "Accounting audit is not an exhaustive continuous-time collision or reservation proof; independent EBS segments retain the shared workload contract."}


def distribution(values: list[float], prefix: str) -> dict:
    require(values and all(math.isfinite(v) for v in values), "invalid timing population")
    return {f"{prefix}_{k}_seconds": v for k, v in {"min": min(values), "mean": statistics.fmean(values),
        "p95": external._quantile(values, .95), "p99": external._quantile(values, .99), "max": max(values)}.items()}


def recompute_population(identity: dict, native_dir: Path, expected_identity_sha: str, *, speed_mps: float,
                         failed_edges: list[list[int]] | None = None) -> dict:
    """Portable pure recomputation from remapped inputs and unmodified native bytes.

    Caller verifies original identity JSON bytes against expected_identity_sha,
    then may remap its three paths. No build directory or original absolute path
    is accessed, and no artifacts are written. Java is never executed here.
    """
    native_dir = Path(native_dir)
    require(len(expected_identity_sha) == 64, "original identity SHA is required")
    for field in ("raw", "canonical", "map"):
        require(sha(Path(identity[field+"_path"])) == identity[field+"_sha256"], f"remapped {field} bytes differ")
    canonical = [json.loads(line) for line in Path(identity["canonical_path"]).read_text(encoding="utf-8").splitlines() if line.strip()]
    summaries = rows(native_dir / "summary.csv")
    require(len(summaries) == 1, "run must contain exactly one measured repeat")
    _, raw = external.parse_legacy_tasks(Path(identity["raw_path"]))
    failed = {tuple(edge) for edge in (failed_edges or [])}
    map_lines = Path(identity["map_path"]).read_text(encoding="utf-8-sig").splitlines()
    node_count = int(map_lines[0].split()[0])
    through = {int(line.split()[0]): float(line.split()[2]) for line in map_lines[1:1+node_count]}
    lengths = {tuple(map(int, fields[:2])): float(fields[2])
               for fields in (line.split() for line in map_lines[1+2*node_count:]) if fields}
    route_rows = rows(native_dir / "routes.csv")
    for route in route_rows:
        path = [int(node) for node in route["path"].split(";")]
        require(path and path[0] == int(route["start"]) and path[-1] == int(route["goal"]), "native route path endpoints differ")
        require(all(node in through for node in path) and all(pair in lengths for pair in zip(path, path[1:])),
                "native route includes an unknown node or edge")
        require(not any(pair in failed for pair in zip(path, path[1:])), "native planned route uses declared failed edge")
        expected_finish = float(route["epoch"]) + sum(through[node] for node in path) \
            + sum(lengths[pair] / speed_mps for pair in zip(path, path[1:]))
        close(route["finish_time"], expected_finish, "native planned goal T2 recurrence includes source and goal through")
    lifecycle, audit = audit_records(canonical, rows(native_dir / NATIVE_FILES[0]), rows(native_dir / "release.csv"),
        parse_events(native_dir / "outputstarttime.txt", True), parse_events(native_dir / "output.txt", False),
        rows(native_dir / "execution_terminal.csv"), summaries[0], route_rows,
        [int(task.task_id) for task in raw], expected_speed_mps=speed_mps, expected_fault_count=len(failed))
    require(len(lifecycle) == int(identity["segment_count"]) and audit["raw_bag_count"] == int(identity["raw_bag_count"]),
            "full identity denominator mismatch")
    bags, completion, admission = [], {}, {}
    grouped = defaultdict(list)
    for row in lifecycle:
        grouped[row["task_id"]].append(row)
    for task_id, segments in sorted(grouped.items()):
        full = all(s["complete"] for s in segments)
        all_planned = all(s["processed_attempt_epoch"] is not None for s in segments)
        completion[task_id] = max(s["finish_epoch"] for s in segments) if full else None
        admission[task_id] = max(s["processed_attempt_epoch"] for s in segments) if all_planned else None
        row = {"task_id": task_id, "canonical_segment_count": len(segments),
               "released_segment_count": sum(s["release_epoch"] is not None for s in segments),
               "planned_segment_count": sum(s["processed_attempt_epoch"] is not None for s in segments),
               "completed_segment_count": sum(s["complete"] for s in segments), "complete": full,
               "final_completion_epoch": completion[task_id], "all_segments_processed_epoch": admission[task_id]}
        for name, start in (("scheduled_release", "scheduled_pass_time"), ("native_release", "release_epoch"),
                            ("processed_attempt", "processed_attempt_epoch"), ("raw_entry", "original_entry_time")):
            row[f"tht_{name}_seconds"] = sum(s["finish_epoch"]-float(s[start]) for s in segments) if full else None
        row["source_wait_seconds"] = sum(s["processed_attempt_epoch"]-s["release_epoch"] for s in segments) if full else None
        bags.append(row)
    metrics, full = external._raw_business_metrics(identity, completion_by_task=completion, admission_by_task=admission)
    metrics.update({name: None for name in FORMAL_TIMING})
    eligible = full
    if eligible:
        metrics.update(distribution([b["tht_scheduled_release_seconds"] for b in bags], "tht_scheduled_release"))
        metrics.update(distribution([b["tht_processed_attempt_seconds"] for b in bags], "tht_admission"))
        for suffix in STATS:
            if suffix != "min":
                metrics[f"population_latency_{suffix}_seconds"] = metrics[f"tht_admission_{suffix}_seconds"]
    deadline_by_raw = {int(task.task_id): float(task.std) for task in raw}
    for label, margin in (("std", 0.0), ("std_minus_2700", 2700.0)):
        count = sum(completion[task_id] is not None and completion[task_id] <= deadline - margin + 1e-9
                    for task_id, deadline in deadline_by_raw.items())
        metrics[f"success_{label}_raw_bag_count"] = count
        metrics[f"success_{label}_rate"] = count / len(deadline_by_raw)
    for bag in bags:
        deadline = deadline_by_raw[bag["task_id"]]
        bag["std_seconds"] = deadline
        bag["success_std"] = bag["complete"] and bag["final_completion_epoch"] <= deadline + 1e-9
        bag["success_std_minus_2700"] = bag["complete"] and bag["final_completion_epoch"] <= deadline - 2700 + 1e-9
    metrics["TH_completed_raw_bags"] = int(metrics["completed_raw_bag_count"])
    metrics["unfinished_raw_bag_count"] = len(bags)-int(metrics["completed_raw_bag_count"])
    metrics["completed_raw_bags_per_fixed_horizon_hour"] = metrics["completed_raw_bag_count"]*3600/HORIZON
    offsets = [s["release_epoch"]-float(s["scheduled_pass_time"]) for s in lifecycle if s["release_epoch"] is not None]
    audit.update(workload_identity_sha256=expected_identity_sha, full_population_complete=full,
                 planned_route_time_recurrence_status="PASS", planned_route_time_recurrence_count=len(route_rows),
                 declared_failed_edge_use_count=0,
                 completed_raw_bag_count=metrics["completed_raw_bag_count"],
                 native_release_minus_canonical_D_min_seconds=min(offsets) if offsets else None,
                 native_release_minus_canonical_D_max_seconds=max(offsets) if offsets else None)
    audit["absent_zero_event_logs"] = sorted(name for name in OPTIONAL_ZERO_EVENT_LOGS if not (native_dir / name).exists())
    return {"segment_lifecycle": lifecycle, "raw_bag_timings": bags, "population_audit": audit,
            "metrics": metrics, "full_population_complete": full}


def normalize_cell(identity_path: Path, native_dir: Path, *, identity_audited: bool = False) -> dict:
    identity_path, native_dir = Path(identity_path).resolve(strict=True), Path(native_dir).resolve(strict=True)
    identity = read_json(identity_path) if identity_audited else external._identity_payload(identity_path)[1]
    status = read_json(native_dir / "runner_status.json")
    spec = read_json(native_dir / "run_spec.json")
    validate_spec(spec, identity)
    require(sha(native_dir / "run_spec.json") == status["run_spec_sha256"], "run spec drift")
    require(status.get("method") == METHOD and status.get("status") == "complete" and status.get("returncode") == 0,
            "native process not completed under repaired HCA method")
    target = native_dir / "normalized_result.json"
    if target.exists():
        for record in read_json(target)["native_evidence"]:
            require(sha(Path(record["path"])) == record["sha256"], "refusing to regenerate over altered existing evidence")
    require(status["workload_identity_sha256"] == sha(identity_path), "run consumed another workload identity")
    build = read_json(native_dir / BUILD_NAME)
    require(build.get("method") == METHOD and build.get("schema") == "czr005.hca_paper_suite_build.v1",
            "cell references another build schema/method")
    require(sha(native_dir / BUILD_NAME) == status["build_identity_sha256"], "cell build manifest changed")
    for field in ("raw", "canonical", "map"):
        require(identity[field+"_sha256"] == status["inputs"][field]["sha256"], f"run input {field} identity differs")
    require(sha(Path(spec["protocol_path"])) == spec["protocol_sha256"] == status["protocol_sha256"], "protocol drift")
    require(status["python_runner_sha256"] == sha(Path(__file__)), "Python runner source drift")
    summary_rows = rows(native_dir / "summary.csv")
    require(len(summary_rows) == 1 and summary_rows[0]["method"] == METHOD, "native wrapper method differs")
    suite_rows = rows(native_dir / "suite_audit.csv")
    expected_edges = {tuple(edge) for edge in spec.get("failed_edges", [])}
    require(len(suite_rows) == max(1, len(expected_edges)), "native failed-edge audit count differs")
    seen_edges = set()
    for row in suite_rows:
        require(row["method"] == METHOD and row["suite_mode"] == native_mode(spec), "native suite scope differs")
        close(row["standard_speed_mps"], spec["speed_mps"], "native standard speed")
        close(row["actual_speed_mps"], spec["speed_mps"], "native actual speed")
        close(row["bias_fraction"], 0, "native zero bias")
        require(int(row["seed"]) == int(spec["seed"]), "native seed label differs")
        require(row["dynamic_replanning_implemented"] == row["static_lra_implemented"] == "false", "unsupported algorithm scope")
        close(row["active_fault_count"], len(expected_edges), "native active fault count")
        close(row["terminal_accounting_residual"], 0, "native terminal accounting")
        if spec["family"] == "all_day_fault":
            close(row["fault_start_epoch"], 8260, "native first-round fault epoch")
            require(row["full_day_known_fault"] == "true", "native fault disclosure differs")
            edge = (int(row["failed_edge_from"]), int(row["failed_edge_to"]))
            require(edge not in seen_edges, "native duplicated fault audit edge")
            seen_edges.add(edge)
        else:
            require(row["full_day_known_fault"] == "false" and all(row[k] == "" for k in
                    ("fault_start_epoch", "failed_edge_from", "failed_edge_to")), "unexpected native base fault")
    require(seen_edges == expected_edges, "native/spec exact failed-edge identity differs")
    derived = recompute_population(identity, native_dir, sha(identity_path), speed_mps=float(spec["speed_mps"]),
                                   failed_edges=spec.get("failed_edges", []))
    lifecycle, bags, audit, metrics, full = (derived[k] for k in
        ("segment_lifecycle", "raw_bag_timings", "population_audit", "metrics", "full_population_complete"))
    audit.update(source_sha256=build["source_sha256"], class_sha256=build["class_sha256"])
    write_csv(native_dir / "segment_lifecycle.csv", lifecycle)
    write_csv(native_dir / "raw_bag_timings.csv", bags)
    write_json(native_dir / "population_audit.json", audit)
    result = {"schema": SCHEMA, "status": "COMPLETE", "method": METHOD, "reporting_method": METHOD,
        "family": spec["family"], "speed_mps": float(spec["speed_mps"]), "run_spec_sha256": sha(native_dir / "run_spec.json"),
        "scenario_id": spec.get("scenario_id"), "disabled_edges": spec.get("failed_edges", []),
        "disabled_edge_count": len(expected_edges), "initial_failed_edges": spec.get("initial_failed_edges"),
        "initial_failed_edge_count": len(spec["initial_failed_edges"]) if "initial_failed_edges" in spec else None,
        "internal_propagation_implemented": False,
        "fault_set_provenance": "EXTERNALLY_SUPPLIED_DISABLED_EDGE_SET_NO_INTERNAL_PROPAGATION",
        "fault_contract": "KNOWN_BEFORE_FIRST_PLANNING_NO_REPAIR" if expected_edges else "NO_FAULT",
        "map": identity["map"], "load_factor": float(identity["load_factor"]), "seed": int(identity["seed"]),
        "fixed_horizon_seconds": HORIZON, "workload_identity_path": str(identity_path),
        "workload_identity_sha256": sha(identity_path), "workload_raw_sha256": identity["raw_sha256"],
        "workload_canonical_sha256": identity["canonical_sha256"], "workload_map_sha256": identity["map_sha256"],
        "storage_in_goal": identity["storage_in_goal"], "storage_out_start": identity["storage_out_start"],
        "raw_bag_denominator": identity["raw_bag_count"], "segment_denominator": identity["segment_count"],
        "full_population_complete": full, "survivor_timing_used": False,
        "formal_timing_status": "FULL_POPULATION_RAW_BAG_TIMING" if full else "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
        "normalization_contract": {"native_terminal_status": "COMPLETE" if full else "HORIZON_REACHED",
            "simulation_end_seconds": HORIZON, "declared_horizon_seconds": HORIZON,
            "primary_timing_definition": "SUM_PER_RAW_BAG_SEGMENT_COMPLETION_MINUS_CANONICAL_SCHEDULED_RELEASE",
            "secondary_timing_definition": "SUM_PER_RAW_BAG_SEGMENT_COMPLETION_MINUS_PROCESSED_ATTEMPT",
            "timing_policy": "full_population_only", "success_denominator": "ALL_ORIGINAL_RAW_BAGS",
            "success_thresholds": ["STD", "STD_MINUS_2700_SECONDS"], "historical_shared_D": False, "fixed_denominator": True, "survivor_or_common_cohort_forbidden": True,
            "reconstruction_java_source_sha256": build["source_sha256"], "compiled_java_class_sha256": build["class_sha256"],
            "build_identity_sha256": status["build_identity_sha256"], "protocol_sha256": status["protocol_sha256"],
            "source_backlog_definition": "RAW_ENTRY_UNTIL_ALL_SEGMENTS_PROCESSED_INCLUDES_EBS_SCHEDULE_GAP",
            "scientific_validity": "SEGMENT_EXECUTION_ID_REPAIR_ACCOUNTING_VALIDATED_NOT_EXHAUSTIVE_PHYSICAL_PROOF",
            "native_release_clock": "UNCHANGED_INTEGER_EPOCH_MAY_PRECEDE_CANONICAL_D_BY_LESS_THAN_ONE_SECOND"},
        "population_audit": audit, "metrics": metrics,
        "native_evidence": external._native_evidence([native_dir / name for name in
            (*NATIVE_FILES, *DERIVED_FILES, BUILD_NAME, "runner_status.json", "run_spec.json") if (native_dir / name).exists()])}
    if target.exists():
        require(read_json(target) == result, "refusing to overwrite differing normalized evidence")
    else:
        write_json(target, result)
    return result


def archive_cell(native_dir: Path) -> dict:
    """Lossless portable native/derived bytes; never overwrite a different archive."""
    archive_dir = native_dir / "native_archive"
    archive_dir.mkdir(exist_ok=True)
    records = []
    for name in (*NATIVE_FILES, *DERIVED_FILES, BUILD_NAME, "runner_status.json", "run_spec.json", "normalized_result.json", "stdout.txt", "stderr.txt"):
        path = native_dir / name
        if not path.exists() and name in OPTIONAL_ZERO_EVENT_LOGS:
            audit = read_json(native_dir / "population_audit.json")
            counter = "planned_segment_count" if name == "outputstarttime.txt" else "completed_segment_count"
            require(audit["status"] == "PASS" and audit[counter] == 0 and name in audit["absent_zero_event_logs"],
                    "absent event log lacks independent zero-event proof")
            records.append({"source_name": name, "absent": True, "basis": "NATIVE_ZERO_COUNTER_AND_TERMINAL_EXACT_ID_AUDIT"})
            continue
        target = archive_dir / (name+".gz")
        if not target.exists():
            with path.open("rb") as src, target.open("wb") as out, gzip.GzipFile(filename="", fileobj=out, mode="wb", mtime=0) as dst:
                shutil.copyfileobj(src, dst)
        with gzip.open(target, "rb") as stream:
            require(hashlib.file_digest(stream, "sha256").hexdigest() == sha(path), "archive bytes differ from original")
        records.append({"source_name": name, "path": target.relative_to(native_dir).as_posix(),
                        "sha256": sha(target), "uncompressed_sha256": sha(path), "uncompressed_size_bytes": path.stat().st_size})
    value = {"schema": "czr005.hca_paper_suite_archive.v1", "method": METHOD, "files": records,
             "scope": "Full identity, release, successful planning, completion, terminal, lifecycle and raw-bag evidence; epoch task scratch files are not required to recompute these outputs."}
    target = archive_dir / "manifest.json"
    if target.exists():
        require(read_json(target) == value, "archive manifest drift")
    else:
        write_json(target, value)
    return value


def validate_output_directory(output: Path) -> Path:
    """Admit only this repair's runtime namespace or explicitly named local tests."""
    original = Path(output).absolute()
    resolved = original.resolve()
    require(original == resolved, "output path may not traverse a symlink/junction")
    allowed = False
    for base in (ROOT / "outputs/runtime", ROOT / "tmp"):
        if resolved.is_relative_to(base):
            relative = resolved.relative_to(base)
            allowed = bool(relative.parts) and relative.parts[0].startswith(("hca_paper_suite_v3_", "feng_paper_suite_"))
    require(allowed, "use a new outputs/runtime or tmp directory prefixed hca_paper_suite_v3_ or feng_paper_suite_")
    for ancestor in (original, *original.parents):
        if ancestor.exists():
            require(not ancestor.is_symlink() and not (ancestor.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                    if hasattr(ancestor.lstat(), "st_file_attributes") else False), "output ancestor is a reparse point")
        if ancestor == ROOT:
            break
    return resolved


def cleanup_epoch_scratch(output: Path) -> dict:
    """Delete only flat native task scratch files, after lossless archives verify."""
    import os
    output = validate_output_directory(output)
    archive_cell(output)  # checks every gzip against still-present original lifecycle evidence
    scratch = output / "task"
    note = output / "scratch_cleanup.json"
    if note.exists():
        result = read_json(note)
        require(not scratch.exists() and result["status"] == "REMOVED_AFTER_NATIVE_ARCHIVE_VERIFICATION",
                "scratch cleanup state changed")
        require(result["archive_manifest_sha256"] == sha(output / "native_archive/manifest.json"), "scratch archive identity changed")
        return result
    entries = []
    if scratch.exists():
        require(scratch.resolve(strict=True) == scratch and scratch.parent == output,
                "scratch target escaped the new run directory")
        require(scratch.is_dir() and not scratch.is_symlink() and not (scratch.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
                if hasattr(scratch.lstat(), "st_file_attributes") else False), "scratch target is a reparse point")
        # The parent is resolved and non-reparse; the native process has ended
        # and run_cell still holds its exclusive lock. Inspect every flat child
        # before unlinking any. Windows DirEntry.stat caches enumeration data,
        # avoiding a new filesystem handle/resolve for each of 90000 files.
        with os.scandir(scratch) as scan:
            for entry in scan:
                info = entry.stat(follow_symlinks=False)
                item = Path(entry.path)
                require(stat.S_ISREG(info.st_mode) and item.parent == scratch
                        and not getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                        "non-flat/reparse scratch entry; retain for manual inspection")
                entries.append((item, info.st_size))
    total = sum(size for _, size in entries)
    for item, _ in entries:
        item.unlink()
    if scratch.exists():
        scratch.rmdir()
    result = {"schema": "czr005.hca_paper_suite_scratch_cleanup.v1",
        "status": "REMOVED_AFTER_NATIVE_ARCHIVE_VERIFICATION", "target": str(scratch),
        "removed_file_count": len(entries), "removed_size_bytes": total,
        "archive_manifest_sha256": sha(output / "native_archive/manifest.json"),
        "retained": "Complete mapping, release, plan, completion, terminal, lifecycle, per-bag and summary originals plus lossless gzip archives.",
        "finished_at": datetime.now(timezone.utc).isoformat()}
    write_json(note, result)
    return result


def native_mode(spec: dict) -> str:
    return "FULL_DAY_KNOWN_EDGE_FAILURE" if spec["family"] == "all_day_fault" else "BASELINE"


def java_run_command(identity: dict, output: Path, classes_dir: Path, java: str, spec: dict, *, heap_mb: int = 1536) -> list[str]:
    schedule = ";".join(f"8260:{int(edge[0])}:{int(edge[1])}:fault" for edge in spec.get("failed_edges", [])) or "none"
    return [str(Path(java).resolve()), f"-Xmx{heap_mb}m", "-Djava.awt.headless=true", "-cp", str(classes_dir.resolve()),
        "HcaPaperSuiteBenchmark", str(Path(identity["map_path"]).resolve()), str(Path(identity["raw_path"]).resolve()),
        "8260", "90000", "0", "1", "0", str(output / "routes.csv"), str(output / "summary.csv"), schedule, "0", "0",
        str(output / "release.csv"), str(float(spec["speed_mps"])), str(identity["storage_in_goal"]), str(identity["storage_out_start"]),
        "4800.0", "2700.0", str(output / "segment_execution_identity.csv"), str(output / "execution_terminal.csv"),
        native_mode(spec), "0", str(int(spec["seed"])), str(output / "suite_audit.csv")]


def _run_cell(identity_path: Path, output: Path, classes_dir: Path, java: str, javac: str, spec: dict, spec_path: Path, *,
             heap_mb: int = 1536, timeout_seconds: float = 0) -> dict:
    identity_path, identity = external._identity_payload(Path(identity_path))
    validate_spec(spec, identity)
    output, classes_dir = validate_output_directory(output), Path(classes_dir).resolve(strict=True)
    require(heap_mb > 0 and timeout_seconds >= 0, "invalid execution resource limits")
    build = verify_build(classes_dir, java, javac)
    command = java_run_command(identity, output, classes_dir, java, spec, heap_mb=heap_mb)
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".run_lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise RuntimeError(f"another process or interrupted run holds {lock}; inspect it before manual recovery")
    try:
        status_path = output / "runner_status.json"
        if status_path.exists():
            status = read_json(status_path)
            require(status.get("status") == "complete" and status.get("command") == command,
                    "existing run is incomplete or command differs; use a new output directory")
            require(status["build_identity_sha256"] == sha(classes_dir / BUILD_NAME), "existing run build differs")
            require(status["run_spec_sha256"] == sha(spec_path), "existing run spec differs")
            result = normalize_cell(identity_path, output, identity_audited=True)
            cleanup_epoch_scratch(output)
            return result
        require(set(p.name for p in output.iterdir()) == {".run_lock"}, "refusing to run into nonempty evidence directory")
        shutil.copyfile(classes_dir / BUILD_NAME, output / BUILD_NAME)
        shutil.copyfile(spec_path, output / "run_spec.json")
        status = {"schema": "czr005.hca_paper_suite_run.v1", "method": METHOD, "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(), "command": command, "cwd": str(output),
            "workload_identity_path": str(identity_path), "workload_identity_sha256": sha(identity_path),
            "build_identity_sha256": sha(classes_dir / BUILD_NAME), "protocol_sha256": spec["protocol_sha256"],
            "run_spec_sha256": sha(spec_path), "run_spec_source_path": str(spec_path),
            "source_sha256": build["source_sha256"], "class_sha256": build["class_sha256"],
            "python_runner_sha256": sha(Path(__file__)), "python_executable": sys.executable,
            "python_version": sys.version, "horizon_seconds": HORIZON,
            "inputs": {key: {"path": identity[key+"_path"], "sha256": identity[key+"_sha256"]} for key in ("raw", "canonical", "map")}}
        write_json(status_path, status)
        started = time.perf_counter()
        try:
            with (output / "stdout.txt").open("wb") as stdout, (output / "stderr.txt").open("wb") as stderr:
                proc = subprocess.run(command, cwd=output, stdout=stdout, stderr=stderr, timeout=timeout_seconds or None)
            status.update(returncode=proc.returncode, wall_seconds=time.perf_counter()-started,
                          finished_at=datetime.now(timezone.utc).isoformat(), status="complete" if proc.returncode == 0 else "failed")
            write_json(status_path, status)
            require(proc.returncode == 0, f"Java exited {proc.returncode}; native evidence retained")
            verify_build(classes_dir, java, javac)
            result = normalize_cell(identity_path, output, identity_audited=True)
            cleanup_epoch_scratch(output)
            return result
        except Exception as error:
            if status.get("status") == "running":
                status.update(status="failed", error=str(error), wall_seconds=time.perf_counter()-started)
                write_json(status_path, status)
            write_json(output / "run_failure.json", {"error": str(error), "native_process_status": status.get("status")})
            raise
    finally:
        lock.rmdir()


def load_result(path: Path) -> dict:
    """Recompute exact-ID audit and verify original bytes before result reuse."""
    value = read_json(Path(path))
    require(value.get("schema") == SCHEMA and value.get("method") == METHOD and value.get("status") == "COMPLETE",
            "not a completed HCA segment identity result")
    for item in value["native_evidence"]:
        require(sha(Path(item["path"])) == item["sha256"], "native evidence drift")
    return normalize_cell(Path(value["workload_identity_path"]), Path(path).parent)


def validate_spec(spec: dict, identity: dict) -> None:
    require(spec.get("method") == METHOD, "wrong paper-suite HCA method")
    require(spec.get("family") in ("base", "all_day_fault"), "only base and known all-day fault families are enabled")
    require(float(spec.get("speed_mps", 0)) in (1.5, 2.5, 3.0), "standard speed must be 1.5, 2.5 or 3 m/s")
    require(float(spec.get("horizon_seconds", -1)) == HORIZON, "fixed absolute horizon must be 98259")
    require(spec.get("timing_policy") == "full_population_only", "survivor timing or old 2x exclusion is forbidden")
    require(identity["map"] in ("map2", "nanning") and float(identity["load_factor"]) in (1.0, 2.0), "unauthorized map/load")
    require(int(spec["seed"]) == int(identity["seed"]) and int(spec["seed"]) in external.SEEDS, "common seed identity differs")
    require(float(identity["fixed_horizon_seconds"]) == HORIZON, "workload horizon differs")
    if "workload_identity_sha256" in spec:
        require(sha(Path(spec["workload_identity_path"])) == spec["workload_identity_sha256"], "specified workload identity drift")
    require(spec.get("protocol_path") and len(spec.get("protocol_sha256", "")) == 64, "explicit protocol path and SHA required")
    require(sha(Path(spec["protocol_path"])) == spec["protocol_sha256"], "suite protocol bytes differ")
    require(not spec.get("faults") and not spec.get("fault_schedule") and not spec.get("repairs")
            and float(spec.get("bias_fraction", 0)) == 0, "do not silently ignore alternate fault fields, repairs or bias")
    failed = spec.get("failed_edges", [])
    require(isinstance(failed, list) and all(isinstance(edge, list) and len(edge) == 2
            and all(type(node) is int and node >= 0 for node in edge) for edge in failed), "failed_edges must be directed integer node pairs")
    require(len({tuple(edge) for edge in failed}) == len(failed), "duplicate directed failed edge")
    if "initial_failed_edges" in spec:
        initial = spec["initial_failed_edges"]
        require(isinstance(initial, list) and all(isinstance(edge, list) and len(edge) == 2
                and all(type(node) is int and node >= 0 for node in edge) for edge in initial), "invalid initial failure set")
        require(len({tuple(edge) for edge in initial}) == len(initial)
                and {tuple(edge) for edge in initial} <= {tuple(edge) for edge in failed}, "initial failures must be a unique subset of disabled edges")
    if spec["family"] == "base":
        require(not failed, "base requires an empty failure set")
    else:
        require(failed and spec.get("scenario_id"), "fault requires an explicit scenario and failure set")
        require(spec.get("fault_notification_epoch") == 8260, "faults must be known before first planning at epoch 8260")
        scenario = spec.get("scenario", {})
        require(scenario.get("information_contract") == "KNOWN_SURVIVING_TOPOLOGY_NO_SOURCE_PREFILTER",
                "common fault information contract differs")
        require(scenario.get("fault_edges") == failed, "common C++ and HCA disabled-edge lists differ")
        lines = Path(identity["map_path"]).read_text(encoding="utf-8-sig").splitlines()
        node_count = int(lines[0].split()[0])
        edges = {tuple(map(int, line.split()[:2])) for line in lines[1+2*node_count:] if line.strip()}
        require(all(tuple(edge) in edges for edge in failed), "failure set contains a nonexistent directed map edge")
    if spec.get("fault_mapping_path"):
        require(sha(Path(spec["fault_mapping_path"])) == spec.get("fault_mapping_sha256"), "fault mapping source drift")


def run_spec(spec_path: str | Path, output_dir: str | Path) -> dict:
    """Consume one immutable suite spec; never silently compile or simulate another cell."""
    spec_path = Path(spec_path).resolve(strict=True)
    spec = read_json(spec_path)
    identity_path, identity = external._identity_payload(Path(spec["workload_identity_path"]))
    validate_spec(spec, identity)
    java = str(Path(spec.get("java") or shutil.which("java")).resolve(strict=True))
    javac = str(Path(spec.get("javac") or shutil.which("javac")).resolve(strict=True))
    classes = Path(spec.get("classes_dir", ROOT / "build/hca_paper_suite_v3_20260907")).resolve(strict=True)
    return _run_cell(identity_path, Path(output_dir), classes, java, javac, spec, spec_path,
                     heap_mb=int(spec.get("heap_mb", 1536)), timeout_seconds=float(spec.get("timeout_seconds", 0)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--classes-dir", type=Path, default=ROOT / "build/hca_paper_suite_v3_20260907")
    compile_parser.add_argument("--java", default=shutil.which("java"))
    compile_parser.add_argument("--javac", default=shutil.which("javac"))
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--spec", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "compile":
        value = compile_production(args.classes_dir, args.java, args.javac)
        print(json.dumps({key: value[key] for key in ("method", "source_sha256", "class_sha256")}))
    elif args.action == "run":
        value = run_spec(args.spec, args.output)
        print(json.dumps({"status": value["status"], "method": METHOD, "map": value["map"],
                          "load_factor": value["load_factor"], "seed": value["seed"], "speed_mps": value["speed_mps"],
                          "completed_raw_bag_count": value["metrics"]["completed_raw_bag_count"],
                          "full_population_complete": value["full_population_complete"]}))
    else:
        print(json.dumps(load_result(args.result)["population_audit"]))


if __name__ == "__main__":
    main()
