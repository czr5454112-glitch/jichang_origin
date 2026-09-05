"""Normalize, audit and publish the separately identified, user-adopted V5 matrix.

Primary THT is sum over a raw bag's segments of completion minus canonical
scheduled release. The independent native admission clock remains secondary.
No timing is reported for 2x or an incomplete raw population. A clean DEADLOCK
is an observed incomplete outcome, never silently removed from comparisons.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external
from scripts.eval import audit_feng_v5_population as population

METHOD = "FENG_DH_BOUNDARY_CLEARANCE_V5"
METHODS = ("FENG_NATIVE_HCA", METHOD, external.REFERENCE_METHOD)
SOURCE_SHA = population.SOURCE_SHA
CLASS_SHA = population.CLASS_SHA
SCHEMA = "czr005.feng_v5_external_result.v1"
RESULT_ROOT = ROOT / "outputs/runtime/cie_external_baseline_boundary_clearance_v5"
EVIDENCE_ROOT = ROOT / "outputs/evidence/feng_dh_boundary_clearance_v5_20260905"
TABLE_ROOT = ROOT / "outputs/tables"
SUFFIXES = ("min", "mean", "p95", "p99", "max")
PRIMARY = tuple(f"tht_scheduled_release_{s}_seconds" for s in SUFFIXES)
ADMISSION = tuple(f"tht_admission_{s}_seconds" for s in SUFFIXES)
FORMAL_TIMING = set(PRIMARY + ADMISSION) | set(external.TIMING_METRICS)
require = population.require
sha = population.sha
GENERATOR_SHA = sha(Path(__file__))
POPULATION_GENERATOR_SHA = sha(Path(population.__file__))


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def distribution(values: list[float], prefix: str) -> dict:
    values = sorted(values)
    require(bool(values) and all(math.isfinite(v) for v in values), "invalid timing population")
    return {f"{prefix}_{k}_seconds": v for k, v in {
        "min": values[0], "mean": statistics.fmean(values),
        "p95": external.internal_random._quantile(values, .95),
        "p99": external.internal_random._quantile(values, .99), "max": values[-1]}.items()}


def normalize_v5_cell(identity_path: Path, native_dir: Path, output_path: Path) -> dict:
    """Public runner API; validate exact identity and every bag before publishing."""
    identity_path, identity = external._identity_payload(Path(identity_path))
    native_dir, output_path = Path(native_dir).resolve(), Path(output_path)
    status = read_json(native_dir / "runner_status.json")
    audit = population.audit_cell(native_dir, status, float(identity["load_factor"]), int(identity["seed"]))
    require(audit["workload_identity_sha256"] == sha(identity_path), "runner consumed another identity")
    require(float(status["identity"]["horizon_seconds"]) == external.FIXED_HORIZON_SECONDS,
            "V5 must declare the shared fixed horizon")
    summary = population.rows(native_dir / "summary.csv")[0]
    require(summary.get("method") == METHOD, "native summary method differs from V5")
    segments, bags = population.rows(native_dir / "segments.csv"), population.rows(native_dir / "bags.csv")
    completion, admission = external._group_lifecycle(segments, identity,
        task_key="source_raw_bag_id", admission_key="admission_time_seconds",
        completion_key="completion_time_seconds", complete_key="status", complete_value="COMPLETED")
    metrics, full = external._raw_business_metrics(identity,
        completion_by_task=completion, admission_by_task=admission)
    metrics.update({name: None for name in PRIMARY + ADMISSION})
    eligible = full and float(identity["load_factor"]) != 2.0
    if eligible:
        metrics.update(distribution([float(b["table53_scheduled_interval_seconds"]) for b in bags],
                                    "tht_scheduled_release"))
        metrics.update(distribution([float(b["diagnostic_first_admission_to_completion_seconds"]) for b in bags],
                                    "tht_admission"))
        values, _ = external._dh_full_population_timing(summary, expected_count=int(identity["raw_bag_count"]))
        for suffix, value in values.items():
            population.close(value, metrics[f"tht_admission_{suffix}_seconds"], "native summary timing")
            metrics[f"population_latency_{suffix}_seconds"] = value
    else:
        metrics.update({name: None for name in FORMAL_TIMING})
    metrics["unfinished_raw_bag_count"] = int(identity["raw_bag_count"]) - int(metrics["completed_raw_bag_count"])
    metrics["completed_raw_bags_per_fixed_horizon_hour"] = metrics["completed_raw_bag_count"] * 3600 / external.FIXED_HORIZON_SECONDS
    contract = {
        "native_terminal_status": summary["status"], "simulation_end_seconds": float(summary["simulation_end_seconds"]),
        "declared_horizon_seconds": external.FIXED_HORIZON_SECONDS,
        "fixed_horizon_native_contract": "DECLARED_FIXED_HORIZON",
        "reconstruction_java_source_sha256": SOURCE_SHA, "compiled_java_class_sha256": CLASS_SHA,
        "scientific_validity": "USER_ADOPTED_DISCLOSED_ASSUMPTION_RECONSTRUCTION_NOT_SOURCE_EXACT",
        "validated_implementation_version": "BOUNDARY_CLEARANCE_V5_JDK18",
        "primary_timing_definition": "SUM_PER_RAW_BAG_SEGMENT_COMPLETION_MINUS_CANONICAL_SCHEDULED_RELEASE",
        "secondary_timing_definition": "SUM_PER_RAW_BAG_SEGMENT_COMPLETION_MINUS_FIRST_ADMISSION",
        "historical_shared_D": False, "fixed_denominator": True, "survivor_or_common_cohort_forbidden": True,
        "deadlock_projection": "UNFINISHED_BAGS_RETAINED_TO_FIXED_HORIZON_FOR_BUSINESS_METRICS",
        "source_backlog_definition": "RAW_ENTRY_UNTIL_ALL_SEGMENTS_ADMITTED_INCLUDES_EBS_SCHEDULE_GAP",
        "null_means_not_derivable_from_native_evidence": True,
    }
    value = {"schema": SCHEMA, "status": "COMPLETE", "method": METHOD,
        "reporting_method": METHOD + ("_NANNING_PORTED" if identity["map"] == "nanning" else ""),
        "map": identity["map"], "load_factor": float(identity["load_factor"]), "seed": int(identity["seed"]),
        "fixed_horizon_seconds": external.FIXED_HORIZON_SECONDS,
        "workload_identity_path": str(identity_path), "workload_identity_sha256": sha(identity_path),
        "workload_raw_sha256": identity["raw_sha256"], "workload_canonical_sha256": identity["canonical_sha256"],
        "workload_map_sha256": identity["map_sha256"], "storage_in_goal": identity["storage_in_goal"],
        "storage_out_start": identity["storage_out_start"], "raw_bag_denominator": identity["raw_bag_count"],
        "segment_denominator": identity["segment_count"], "full_population_complete": full,
        "survivor_timing_used": False,
        "formal_timing_status": "FORMAL_2X_TIMING_NA_BY_PROTOCOL" if float(identity["load_factor"]) == 2.0 else
            "FULL_POPULATION_RAW_BAG_TIMING" if full else "NOT_MEASURED_FULL_POPULATION_INCOMPLETE",
        "normalization_contract": contract, "population_audit": audit,
        "native_evidence": external._native_evidence([native_dir / n for n in population.FILES]), "metrics": metrics}
    if output_path.exists():
        require(read_json(output_path) == value, "refusing to replace differing frozen V5 normalization")
    else:
        external._atomic_json(output_path, value)
    return load_v5_result(output_path)


def load_v5_result(path: Path) -> dict:
    """Public strict loader; deliberately independent of the legacy DH version gate."""
    value = read_json(Path(path))
    require(value.get("schema") == SCHEMA and value.get("method") == METHOD and value.get("status") == "COMPLETE",
            "not a complete V5 normalization")
    identity_path, identity = external._identity_payload(Path(value["workload_identity_path"]))
    require(value["workload_identity_sha256"] == sha(identity_path), "identity bytes drift")
    for target, source in {"map": "map", "load_factor": "load_factor", "seed": "seed",
            "raw_bag_denominator": "raw_bag_count", "segment_denominator": "segment_count",
            "storage_in_goal": "storage_in_goal", "storage_out_start": "storage_out_start",
            "workload_raw_sha256": "raw_sha256", "workload_canonical_sha256": "canonical_sha256",
            "workload_map_sha256": "map_sha256"}.items():
        require(value[target] == identity[source], f"normalized identity mismatch: {target}")
    contract = value["normalization_contract"]
    require(contract["reconstruction_java_source_sha256"] == SOURCE_SHA
            and contract["compiled_java_class_sha256"] == CLASS_SHA, "unfrozen V5 implementation")
    require(value["survivor_timing_used"] is False and contract["survivor_or_common_cohort_forbidden"] is True,
            "survivor timing forbidden")
    require(value["fixed_horizon_seconds"] == external.FIXED_HORIZON_SECONDS, "horizon mismatch")
    require(contract["native_terminal_status"] in {"COMPLETE", "HORIZON_REACHED", "DEADLOCK"}, "unknown terminal status")
    require(value["full_population_complete"] == (contract["native_terminal_status"] == "COMPLETE"), "population/status mismatch")
    require(value["population_audit"]["status"] == "PASS", "population audit absent")
    require(len(value["native_evidence"]) == len(population.FILES), "native evidence incomplete")
    for record in value["native_evidence"]:
        require(sha(Path(record["path"])) == record["sha256"], "native evidence bytes drift")
    for name, metric in value["metrics"].items():
        if metric is not None:
            external._finite_metric(metric, name)
    if float(value["load_factor"]) == 2.0 or not value["full_population_complete"]:
        require(all(value["metrics"].get(name) is None for name in FORMAL_TIMING), "forbidden formal timing")
    else:
        require(all(value["metrics"].get(name) is not None for name in PRIMARY + ADMISSION), "full timing missing")
    return value


def archive_file(source: Path, target: Path, *, compress: bool = False) -> dict:
    """Freeze original bytes; gzip with zero timestamp and verify decompressed SHA."""
    source, target = Path(source), Path(target)
    source_sha = sha(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if compress:
            with gzip.open(target, "rb") as handle:
                restored = hashlib.file_digest(handle, "sha256").hexdigest()
        else:
            restored = sha(target)
        require(restored == source_sha, f"refusing to replace changed archive: {target}")
    else:
        temporary = target.with_name(target.name + ".tmp")
        if compress:
            with source.open("rb") as inp, temporary.open("wb") as out:
                with gzip.GzipFile(filename="", fileobj=out, mode="wb", mtime=0) as packed:
                    shutil.copyfileobj(inp, packed)
        else:
            shutil.copyfile(source, temporary)
        temporary.replace(target)
    if compress:
        with gzip.open(target, "rb") as handle:
            require(hashlib.file_digest(handle, "sha256").hexdigest() == source_sha, "gzip restoration failed")
    require(sha(source) == source_sha, "source changed during archive")
    return {"source_path": str(source.resolve()), "source_sha256": source_sha, "source_size_bytes": source.stat().st_size,
            "archive_path": str(target.resolve()), "archive_sha256": sha(target), "archive_size_bytes": target.stat().st_size,
            "gzip": compress}


def archive_v5_cell(native_dir: Path, target_dir: Path) -> dict:
    """Public runner API, called only after normalization of a clean terminal run."""
    status = read_json(Path(native_dir) / "runner_status.json")
    require(status.get("status") == "complete" and status.get("returncode") == 0, "cannot archive a running cell")
    require(status["identity"]["method"] == METHOD, "wrong archive method")
    files = [archive_file(Path(native_dir) / name,
             Path(target_dir) / (name + ".gz" if name in {"bags.csv", "segments.csv"} else name),
             compress=name in {"bags.csv", "segments.csv"}) for name in population.FILES]
    manifest = {"schema": "czr005.feng_v5_native_archive.v1", "source_sha256": SOURCE_SHA,
                "class_sha256": CLASS_SHA, "all_raw_bags_and_segments_retained": True, "files": files}
    external._atomic_json(Path(target_dir) / "archive_manifest.json", manifest)
    return manifest


def canonical_segments(identity: dict) -> dict:
    with Path(identity["canonical_path"]).open(encoding="utf-8") as handle:
        values = [json.loads(line) for line in handle]
    indexed = {str(v["segment_id"]): v for v in values}
    require(len(indexed) == len(values) == int(identity["segment_count"]), "canonical segment duplicates")
    return indexed


def hca_primary_timing(identity: dict, lifecycle: list[dict], eligible: bool, expected: dict | None = None) -> tuple[dict, dict]:
    """Use canonical D, not HCA's integer release_epoch, as the common clock."""
    expected = canonical_segments(identity) if expected is None else expected
    seen, by_bag, admissions = set(), defaultdict(float), defaultdict(float)
    offsets, completed = [], 0
    for row in lifecycle:
        sid = str(row["segment_id"])
        require(sid in expected and sid not in seen, "foreign/duplicate HCA segment")
        seen.add(sid)
        source = expected[sid]
        require(int(row["task_id"]) == int(source["task_id"]) and row["leg"] == source["leg"]
                and int(row["start"]) == int(source["start"]) and int(row["goal"]) == int(source["goal"]),
                "HCA segment identity/OD mismatch")
        population.close(float(row["scheduled_pass_time"]), float(source["pass_time"]), "HCA scheduled D")
        offsets.append(float(row["release_epoch"]) - float(source["pass_time"]))
        if external._csv_bool(row["complete"]):
            completed += 1
            finish, admitted = float(row["finish_epoch"]), float(row["processed_attempt_epoch"])
            require(admitted <= finish <= external.FIXED_HORIZON_SECONDS, "invalid HCA completion")
            by_bag[int(source["task_id"])] += finish - float(source["pass_time"])
            admissions[int(source["task_id"])] += finish - admitted
        elif eligible:
            raise ValueError("HCA eligible timing includes unfinished segment")
    metrics = {name: None for name in PRIMARY + ADMISSION}
    if eligible:
        require(seen == set(expected) and len(by_bag) == int(identity["raw_bag_count"]), "HCA full timing lacks population")
        metrics.update(distribution(list(by_bag.values()), "tht_scheduled_release"))
        metrics.update(distribution(list(admissions.values()), "tht_admission"))
    audit = {"status": "PASS", "canonical_segment_count": len(expected), "observed_lifecycle_count": len(seen),
        "unreleased_segments_absent_from_native_lifecycle": len(expected) - len(seen), "completed_segments": completed,
        "canonical_id_OD_and_scheduled_D_match": True,
        "release_epoch_minus_canonical_D_min_seconds": min(offsets) if offsets else None,
        "release_epoch_minus_canonical_D_max_seconds": max(offsets) if offsets else None,
        "primary_clock": "CANONICAL_PASS_TIME_NOT_NATIVE_INTEGER_RELEASE_EPOCH",
        "historical_build_identity_limitation": "RUN_TIME_SOURCE_AND_CLASS_SHA_NOT_RECORDED_NO_RETROACTIVE_SUBSTITUTION"}
    return metrics, audit


def export_control(value: dict, identity: dict) -> tuple[dict, dict]:
    metrics = dict(value["metrics"])
    metrics.update({name: None for name in PRIMARY + ADMISSION})
    eligible = value["full_population_complete"] and float(identity["load_factor"]) != 2.0
    evidence = [Path(record["path"]) for record in value["native_evidence"]]
    if value["method"] == external.REFERENCE_METHOD:
        paths = [p for p in evidence if p.name == "g31_native.json"]
        require(len(paths) == 1, "G31 native JSON missing")
        native = read_json(paths[0])
        fresh, full, _, _ = external._normalize_g31(identity, paths[0])
        require(full == value["full_population_complete"] and fresh == value["metrics"], "G31 normalized metrics drift")
        if eligible:
            for family, prefix in (("java_release", "tht_scheduled_release"), ("processed_attempt", "tht_admission")):
                source = native["full_population_timing"]["distributions"][family]
                require(int(source["count"]) == int(identity["raw_bag_count"]), "G31 distribution denominator mismatch")
                for suffix in SUFFIXES:
                    metrics[f"{prefix}_{suffix}_seconds"] = external._finite_metric(source[f"{suffix}_seconds"], suffix)
        diagnostic = {"status": "PASS", "native_terminal_status": native["status"],
            "binary_sha256": native["provenance"]["binary_sha256"], "wall_seconds": native["runtime"].get("wall_seconds"),
            "cpu_seconds": native["runtime"].get("cpu_seconds"), "decision_requests": native["runtime"].get("decision_count"),
            "decision_count_definition": "NATIVE_JUNCTION_DECISION_COUNT_NOT_DH_TICK_REQUESTS",
            "population_evidence_level": "ARCHIVED_NATIVE_AGGREGATE_AND_ORIGINAL_INTEGRITY_GATES_NO_RETAINED_PER_BAG_PAYLOAD",
            "primary_clock": "JAVA_RELEASE_DISTRIBUTION_USES_PROTECTED_CANONICAL_PASS_TIME"}
    else:
        lifecycle_paths = [p for p in evidence if p.name == "segment_lifecycle.csv"]
        require(len(lifecycle_paths) == 1, "HCA lifecycle missing")
        native_dir = lifecycle_paths[0].parent.parent
        fresh, full, _, _ = external._normalize_hca(identity, native_dir)
        require(full == value["full_population_complete"] and fresh == value["metrics"], "HCA normalized metrics drift")
        timing, diagnostic = hca_primary_timing(identity, population.rows(lifecycle_paths[0]), eligible)
        metrics.update(timing)
        campaign = read_json(native_dir / "fresh_hca_summary.json")
        runs = [r for r in campaign["runs"] if r["status"] == "complete"]
        diagnostic.update(native_terminal_status="COMPLETE_PROCESS_FIXED_HORIZON",
            wall_seconds=runs[0].get("wall_seconds"), cpu_seconds=None, decision_requests=None,
            population_evidence_level="ALL_EXPORTED_SEGMENTS_PLUS_CANONICAL_UNRELEASED_POPULATION")
    metrics["unfinished_raw_bag_count"] = int(identity["raw_bag_count"]) - int(metrics["completed_raw_bag_count"])
    metrics["completed_raw_bags_per_fixed_horizon_hour"] = metrics["completed_raw_bag_count"] * 3600 / external.FIXED_HORIZON_SECONDS
    return metrics, diagnostic


def paired_aggregate(rows: list[dict], replicates: int) -> dict:
    indexed = {(r["map"], r["load_factor"], r["seed"], r["method"]): r for r in rows}
    require(len(indexed) == len(rows), "duplicate matrix cell")
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for seed in external.SEEDS:
                observed = [indexed[(map_name, load, seed, m)] for m in METHODS if (map_name, load, seed, m) in indexed]
                require(len({r["workload_identity_sha256"] for r in observed}) <= 1, "paired methods differ in workload")
    higher = external.HIGHER_IS_BETTER | {"completed_raw_bags_per_fixed_horizon_hour"}
    metrics = sorted(higher | external.LOWER_IS_BETTER | set(PRIMARY + ADMISSION) | {"unfinished_raw_bag_count"})
    result = []
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for baseline, reference in ((METHOD, external.REFERENCE_METHOD), ("FENG_NATIVE_HCA", external.REFERENCE_METHOD),
                                        (METHOD, "FENG_NATIVE_HCA")):
                for metric in metrics:
                    row = {"map": map_name, "load_factor": load, "baseline": baseline, "reference": reference,
                           "metric": metric, "preferred_direction": "higher" if metric in higher else "lower"}
                    missing, pairs = [], []
                    for seed in external.SEEDS:
                        left, right = indexed.get((map_name, load, seed, baseline)), indexed.get((map_name, load, seed, reference))
                        if left is None or right is None or left.get(metric) is None or right.get(metric) is None:
                            missing.append(seed)
                        else:
                            pairs.append((seed, float(left[metric]), float(right[metric])))
                    row.update(paired_seed_count=len(pairs), missing_seed_count=len(missing), missing_seeds=",".join(map(str, missing)))
                    if metric in FORMAL_TIMING and load == 2.0:
                        row["status"] = "FORMAL_2X_TIMING_NA_BY_PROTOCOL"
                    elif missing:
                        row["status"] = "INCOMPLETE_TEN_SEED_COMPARISON_NO_SUBSET_ESTIMATE"
                    else:
                        deltas = [right - left for _, left, right in pairs]
                        oriented = deltas if metric in higher else [-v for v in deltas]
                        low, high = external.paired_bootstrap_ci(deltas, replicates=replicates,
                            seed_key=f"v5|{map_name}|{load}|{baseline}|{reference}|{metric}")
                        row.update(status="COMPLETE", baseline_mean=statistics.fmean(v[1] for v in pairs),
                            reference_mean=statistics.fmean(v[2] for v in pairs),
                            mean_delta_reference_minus_baseline=statistics.fmean(deltas), bootstrap_ci_low=low, bootstrap_ci_high=high,
                            reference_win_count=sum(v > 1e-12 for v in oriented), tie_count=sum(abs(v) <= 1e-12 for v in oriented),
                            reference_loss_count=sum(v < -1e-12 for v in oriented))
                    result.append(row)
    return {"schema": "czr005.feng_v5_seed_paired_aggregate.v1", "expected_cells": 180, "observed_cells": len(rows),
        "status": "COMPLETE" if len(rows) == 180 else "INCOMPLETE", "bootstrap_replicates": replicates,
        "confidence_level": .95, "bootstrap_unit": "MATCHED_WORKLOAD_SEED_NOT_INDIVIDUAL_BAG",
        "partial_seed_estimates_suppressed": True, "rows": result}


def archive_campaign_support(result_root: Path, evidence_root: Path, *, all_dh_finished: bool) -> dict:
    """Freeze small static support now, and dynamic orchestration only at the end."""
    records, pending = [], []
    preflight = result_root / "preflight"
    if preflight.exists():
        for source in sorted(preflight.rglob("*")):
            if source.is_file() and (source.suffix in {".json", ".tsv", ".gz"}):
                records.append(archive_file(source, evidence_root / "support/preflight" / source.relative_to(preflight)))
    compile_path = ROOT / "build/feng_dh_v5_campaign/v5_campaign_compile_identity.json"
    if compile_path.exists():
        compiled = read_json(compile_path)
        require(compiled["source_aggregate_sha256"] == SOURCE_SHA and compiled["class_aggregate_sha256"] == CLASS_SHA,
                "support compile identity differs from V5")
        records.append(archive_file(compile_path, evidence_root / "support" / compile_path.name))
    protocol = ROOT / "docs/baselines/feng_dh_v5_acceptance_and_campaign_protocol_20260905.md"
    records.append(archive_file(protocol, evidence_root / "support" / protocol.name))
    for source in sorted(result_root.glob("*.json")):
        if source.name.endswith("_reused_controls.json"):
            continue
        dynamic = source.name.endswith("_execution_status.json") or source.name == "root_orchestration.json"
        if dynamic and not all_dh_finished:
            pending.append({"name": source.name, "reason": "DYNAMIC_STATUS_NOT_FROZEN_UNTIL_ALL_60_DH_FINISH"})
            continue
        if dynamic and source.name.endswith("_execution_status.json"):
            require(read_json(source)["status"] in {"complete", "failed"}, "cannot freeze running execution status")
        records.append(archive_file(source, evidence_root / "support" / source.name))
    value = {"schema": "czr005.feng_v5_portable_support.v1", "all_60_dh_finished": all_dh_finished,
             "files": records, "pending_dynamic_records": pending,
             "reproduction_note": "Repository source and explicit compile command reproduce the recorded class identities; absolute provenance paths are retained but not needed for byte verification."}
    external._atomic_json(evidence_root / "support/support_manifest.json", value)
    return value


def export_campaign(result_root: Path, evidence_root: Path, table_root: Path, *, archive: bool, replicates: int) -> dict:
    rows, cells, failures, missing = [], [], [], []
    reuse_records, reuse_files = {}, []
    for reuse_path in sorted(result_root.glob("*_reused_controls.json")):
        reuse = read_json(reuse_path)
        require(reuse["schema"] == "czr005.feng_v5_control_reuse.v1" and reuse["any_old_dh_reused"] is False
                and reuse["actual_workload_bytes_reaudited"] is True, "invalid V5 control reuse qualification")
        require(reuse["count"] == len(reuse["records"]), "reuse count mismatch")
        for record in reuse["records"]:
            key = (record["map"], float(record["load_factor"]), int(record["seed"]), record["method"])
            require(record["method"] in METHODS and record["method"] != METHOD, "foreign method in reuse qualification")
            require(key not in reuse_records or reuse_records[key] == record, "conflicting reuse qualification")
            reuse_records[key] = record
        if archive:
            reuse_files.append(archive_file(reuse_path, evidence_root / "control_reuse" / reuse_path.name))
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for seed in external.SEEDS:
                cell = external.cell_dir(result_root, load, seed, map_name)
                target = external.cell_dir(evidence_root, load, seed, map_name)
                for method in METHODS:
                    path = cell / f"{method}.json"
                    if not path.exists():
                        missing.append({"map": map_name, "load_factor": load, "seed": seed, "method": method})
                        continue
                    try:
                        value = load_v5_result(path) if method == METHOD else external.load_normalized_result(path)
                        identity_path, identity = external._identity_payload(Path(value["workload_identity_path"]))
                        require((value["map"], value["load_factor"], value["seed"]) == (map_name, load, seed), "path coordinates mismatch")
                        files = []
                        if method == METHOD:
                            native = cell / "feng_env_dh_v5"
                            audit = population.audit_cell(native, read_json(native / "runner_status.json"), load, seed)
                            require(audit == value["population_audit"], "V5 stored population audit drift")
                            metrics = value["metrics"]
                            summary = population.rows(native / "summary.csv")[0]
                            _, raw_tasks = external.parse_legacy_tasks(Path(identity["raw_path"]))
                            raw_by_id = {int(task.task_id): task for task in raw_tasks}
                            for bag in population.rows(native / "bags.csv"):
                                raw = raw_by_id[int(bag["source_raw_bag_id"])]
                                population.close(float(bag["raw_entry_seconds"]), float(raw.entry_time), "native/raw entry")
                                population.close(float(bag["deadline_seconds"]), float(raw.std), "native/raw deadline")
                            require(int(metrics["on_time_raw_bag_count"]) == int(summary["on_time_raw_bags"]), "native/raw on-time count")
                            diagnostic = {"status": "PASS", "native_terminal_status": summary["status"],
                                "wall_seconds": float(summary["wall_seconds"]), "cpu_seconds": None,
                                "decision_requests": int(summary["route_decisions"]),
                                "decision_count_definition": "LOGICAL_ROUTE_REQUESTS_INCLUDING_TICK_HOLD_RETRIES_NOT_SCORE_COMPUTATIONS",
                                "source_sha256": SOURCE_SHA, "class_sha256": CLASS_SHA,
                                "raw_entry_and_deadline_match": True,
                                "population_evidence_level": "ALL_RAW_BAGS_ALL_SEGMENTS_COUNTERS_AND_IDENTITY_AUDITED_TRACE_0",
                                "population_audit": audit}
                            if archive:
                                files.extend(archive_v5_cell(native, target / "feng_env_dh_v5")["files"])
                        else:
                            qualification = reuse_records.get((map_name, load, seed, method))
                            require(qualification is not None and sha(path) == qualification["sha256"], "control lacks matching reuse qualification")
                            metrics, diagnostic = export_control(value, identity)
                            diagnostic["control_reuse_provenance_tier"] = qualification["provenance_tier"]
                            if archive:
                                for record in value["native_evidence"]:
                                    source = Path(record["path"])
                                    relative = source.name if source.name == "g31_native.json" else str(source.relative_to(source.parents[1] if source.parent.name.startswith("run_") else source.parent))
                                    dest = target / ("g31" if method == external.REFERENCE_METHOD else "hca") / relative
                                    compress = source.suffix == ".csv"
                                    files.append(archive_file(source, Path(str(dest) + ".gz") if compress else dest, compress=compress))
                        row = {"map": map_name, "load_factor": load, "seed": seed, "method": method,
                            "reporting_method": value.get("reporting_method", method),
                            "raw_bag_count": identity["raw_bag_count"], "segment_count": identity["segment_count"],
                            "workload_identity_sha256": value["workload_identity_sha256"], "input_sha256": identity["raw_sha256"],
                            "map_sha256": identity["map_sha256"], "canonical_sha256": identity["canonical_sha256"],
                            "full_population_complete": value["full_population_complete"], "formal_timing_status": value["formal_timing_status"],
                            "primary_timing_definition": "SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_COMMON_CANONICAL_SCHEDULED_RELEASE",
                            "historical_shared_D": False, "TH_completed_raw_bags": metrics["completed_raw_bag_count"],
                            "TH_definition": "COMPLETED_RAW_BAG_COUNT_BY_FIXED_ABSOLUTE_EPOCH_98259",
                            "hourly_rate_denominator_seconds": external.FIXED_HORIZON_SECONDS,
                            "hourly_rate_definition": "COUNT_DIVIDED_BY_ABSOLUTE_CUTOFF_FROM_MODEL_TIME_ZERO_NOT_ACTIVE_WINDOW_DURATION",
                            "fixed_horizon_seconds": external.FIXED_HORIZON_SECONDS, **metrics,
                            **{k: v for k, v in diagnostic.items() if k not in {"status", "population_audit"}}}
                        if archive:
                            files.append(archive_file(path, target / path.name))
                            for field, name, compressed in ((None, "workload_identity.json", False),
                                    ("canonical_path", "canonical.jsonl.gz", True), ("raw_path", "raw_input.txt.gz", True)):
                                source = identity_path if field is None else Path(identity[field])
                                files.append(archive_file(source, target / "workload" / name, compress=compressed))
                            files.append(archive_file(Path(identity["map_path"]), evidence_root / "maps" / (identity["map_sha256"] + ".txt.gz"), compress=True))
                        rows.append(row)
                        cells.append({"map": map_name, "load_factor": load, "seed": seed, "method": method,
                                      "diagnostic": diagnostic, "exported_metrics": metrics, "files": files})
                    except (ValueError, KeyError, OSError, TypeError, external.ExternalBaselineError) as error:
                        failures.append({"map": map_name, "load_factor": load, "seed": seed, "method": method, "error": str(error)})
    aggregate = paired_aggregate(rows, replicates)
    table_root.mkdir(parents=True, exist_ok=True)
    external._write_aggregate_csv(table_root / "feng_dh_v5_cells_20260905.csv", rows)
    external._write_aggregate_csv(table_root / "feng_dh_v5_paired_20260905.csv", aggregate["rows"])
    external._atomic_json(table_root / "feng_dh_v5_paired_20260905.json", aggregate)
    support = archive_campaign_support(result_root, evidence_root,
        all_dh_finished=sum(r["method"] == METHOD for r in rows) == 60) if archive else {"files": []}
    manifest = {"schema": "czr005.feng_v5_portable_campaign.v1", "status": "FAIL" if failures else aggregate["status"],
        "expected_cells": 180, "observed_cells": len(rows), "expected_new_dh_cells": 60,
        "new_dh_cells": sum(r["method"] == METHOD for r in rows), "reused_control_cells": sum(r["method"] != METHOD for r in rows),
        "archive_requested": archive, "source_sha256": SOURCE_SHA, "class_sha256": CLASS_SHA,
        "generator_sha256": GENERATOR_SHA, "population_audit_generator_sha256": POPULATION_GENERATOR_SHA,
        "failures": failures, "missing_cells": missing, "cells": cells, "control_reuse_files": reuse_files,
        "qualified_control_reuse_count": len(reuse_records),
        "support_files": support["files"], "pending_dynamic_support": support.get("pending_dynamic_records", []),
        "support_index_sha256": sha(evidence_root / "support/support_manifest.json") if archive else None,
        "evidence_limits": ["V5 trace=0 cannot independently prove per-tick collision/FIFO or no repeated zero-service starts.",
            "HCA historical controls lack run-time source/class hash; copied current classes do not fill this gap.",
            "G31 control JSON archives aggregate values and original integrity gates, not an absent per-bag payload.",
            "All randomized campaign methods share canonical D; these are not the original historical shared-D workload.",
            "Wall times were collected at different dates/concurrency; they are not a controlled speed benchmark."]}
    external._atomic_json(evidence_root / "campaign_manifest.json", manifest)
    write_readme(evidence_root)
    return manifest


def write_readme(root: Path) -> None:
    text = """# V5 campaign evidence

This is the separate, user-adopted boundary-clearance V5 reconstruction. Its source identity is 7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7 and its formal JDK18 class identity is a0a0c35bc2e3576c83f23a60f6a3cd807f3c66ae0ea24304924b9f7fe193b869. It is not a source-exact reproduction. Prior campaigns and audit opinions are preserved.

`campaign_manifest.json` lists actual, missing, and failed cells. COMPLETE means 60 new V5 plus 120 qualified historical controls were audited; it does not mean every baggage population completed. Clean DEADLOCK/HORIZON_REACHED outcomes retain every unfinished bag. The 2x timing prohibition remains even if a method completes.

Primary THT min/mean/max (and diagnostic P95/P99) is the per-raw-bag sum of segment completion minus the shared canonical scheduled release. Native admission-based THT is secondary. HCA actual integer release_epoch is explicitly distinct from canonical D. TH is the number of completed raw bags by fixed absolute epoch 98259; completion/on-time rates, unfinished counts and backlog are separate columns. The optional per-hour normalization divides by 98259 seconds measured from model time zero, not by the active operating window or wall time; it is not an estimate of conveyor capacity. Source backlog ends only when all segments are admitted and therefore includes the EBS schedule gap.

Confidence intervals resample the ten matched workload seeds, not individual bags. All ten eligible seed pairs are required before estimating a comparison. No incomplete bag cohort or available-seed subset is substituted. Lower values are preferred for latency/backlog/tardiness and higher values for throughput/completion/on-time measures. Win/tie/loss counts use the reference method's direction and retain adverse outcomes.

Each available V5 cell stores all native bags and segments as deterministic gzip, plus the original summary/events/runner status and normalized result. Workload canonical/raw/identity bytes and maps are preserved. HCA stores every exported segment and raw timing; canonical records account for unreleased segments omitted by HCA. G31 control JSON contains native aggregate distributions and original integrity checks, not a retained complete per-bag payload. Old HCA execution source/class hashes were not recorded; this limitation is not repaired retrospectively.

`support/support_manifest.json` indexes the 522-OD preflight JSON/gzip, coverage tables, exact compile identity, acceptance protocol, command plans and runner contract checks. The verifier connects each V5 runner's preflight/compile/protocol hashes to these portable copies. Dynamic execution/orchestration files are frozen only after all 60 V5 cells finish; a partial manifest lists them as pending.

Archive records retain their original absolute provenance but can be verified without those paths: locate the suffix beginning at this evidence directory's name and validate archive SHA and gzip-decompressed source SHA. The verifier uses only committed files:

```
python scripts/eval/export_feng_v5_campaign.py --verify-archive
```

To refresh from finished local runs (including partial progress):

```
python scripts/eval/export_feng_v5_campaign.py --archive
```

Final publication should use `--archive --require-complete`; unfinished processes are never read as completed cells. Native CSV trace=0 exports do not prove per-tick collision freedom or reveal actual edge queues. Separate Java fixtures/OD checks support implementation semantics. V5 body-clearance interpretation and its 2,000/h same-incoming bottleneck remain disclosed assumptions; the user selected this candidate after seeing its original map2 results.
"""
    (root / "README.md").write_text(text, encoding="utf-8")


def verify_archive(root: Path) -> dict:
    manifest = read_json(root / "campaign_manifest.json")
    if manifest.get("support_index_sha256"):
        require(sha(root / "support/support_manifest.json") == manifest["support_index_sha256"], "support index bytes drift")
    checked = {}
    for cell in manifest["cells"] + [{"files": manifest.get("control_reuse_files", [])}, {"files": manifest.get("support_files", [])}]:
        for record in cell["files"]:
            portable = str(record["archive_path"]).replace("\\", "/").split("/" + root.name + "/", 1)
            require(len(portable) == 2, "archive record is outside portable root")
            path = root / portable[1]
            if str(path) in checked:
                require(checked[str(path)] == (record["archive_sha256"], record["source_sha256"]), "contradictory shared archive record")
                continue
            require(sha(path) == record["archive_sha256"], "archive bytes drift")
            if record["gzip"]:
                with gzip.open(path, "rb") as handle:
                    restored = hashlib.file_digest(handle, "sha256").hexdigest()
            else:
                restored = sha(path)
            require(restored == record["source_sha256"], "restored source bytes drift")
            checked[str(path)] = (record["archive_sha256"], record["source_sha256"])
    require(bool(checked) and manifest["archive_requested"], "no archive was published")
    preflight_count = 0
    preflight_path = root / "support/preflight/preflight.json"
    if preflight_path.is_file():
        preflight = read_json(preflight_path)
        require(preflight["status"] == "PASS" and preflight["source_aggregate_sha256"] == SOURCE_SHA
                and preflight["class_aggregate_sha256"] == CLASS_SHA, "portable preflight implementation mismatch")
        for record in preflight["archives"]:
            name = str(record["path"]).replace("\\", "/").rsplit("/", 1)[-1]
            packed = root / "support/preflight" / name
            require(sha(packed) == record["sha256"], "portable OD gzip SHA mismatch")
            raw = gzip.decompress(packed.read_bytes())
            require(hashlib.sha256(raw).hexdigest() == record["uncompressed_sha256"], "portable OD decompressed SHA mismatch")
            od_rows = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
            require(all(r["reachable"] and r["status"] == "COMPLETE" and r["first_invalid_state"] is None
                        and r["repeated_zero_service_starts"] == 0 for r in od_rows), "portable OD result failed")
            preflight_count += len(od_rows)
        require(preflight_count == preflight["total_independent_bags"] == 522, "portable OD preflight count differs")
    recomputed, aggregate_only = 0, 0
    for cell in manifest["cells"]:
        folder = external.cell_dir(root, float(cell["load_factor"]), int(cell["seed"]), cell["map"])
        identity = read_json(folder / "workload/workload_identity.json")
        normalized = read_json(folder / (cell["method"] + ".json"))
        require(sha(folder / "workload/workload_identity.json") == normalized["workload_identity_sha256"],
                "portable normalized workload identity mismatch")
        for archived, field in ((folder / "workload/canonical.jsonl.gz", "canonical_sha256"),
                                (folder / "workload/raw_input.txt.gz", "raw_sha256"),
                                (root / "maps" / (identity["map_sha256"] + ".txt.gz"), "map_sha256")):
            require(checked[str(archived)][1] == identity[field], "portable workload byte identity chain mismatch")
        with gzip.open(folder / "workload/canonical.jsonl.gz", "rt", encoding="utf-8") as handle:
            values = [json.loads(line) for line in handle]
        expected = {str(v["segment_id"]): v for v in values}
        require(len(expected) == len(values) == int(identity["segment_count"]), "portable canonical multiplicity mismatch")
        eligible = normalized["full_population_complete"] and float(cell["load_factor"]) != 2.0
        if cell["method"] == METHOD:
            native = folder / "feng_env_dh_v5"
            runner_identity = read_json(native / "runner_status.json")["identity"]
            require(runner_identity["method"] == METHOD
                    and runner_identity["reconstruction_java_source_aggregate_sha256"] == SOURCE_SHA
                    and runner_identity["compiled_java_class_aggregate_sha256"] == CLASS_SHA, "portable V5 implementation mismatch")
            for archived, field in ((root / "support/preflight/preflight.json", "preflight_sha256"),
                    (root / "support/v5_campaign_compile_identity.json", "compile_identity_sha256"),
                    (root / "support/feng_dh_v5_acceptance_and_campaign_protocol_20260905.md", "campaign_protocol_sha256")):
                require(sha(archived) == runner_identity[field], "portable V5 support identity mismatch")
            summary = population.rows(native / "summary.csv")[0]
            with gzip.open(native / "segments.csv.gz", "rt", encoding="utf-8", newline="") as handle:
                segments = list(csv.DictReader(handle))
            with gzip.open(native / "bags.csv.gz", "rt", encoding="utf-8", newline="") as handle:
                bags = list(csv.DictReader(handle))
            by_identity = {(int(v["task_id"]), 1 if v["leg"] == "storage_out" else 0): v for v in values}
            require(len(by_identity) == len(segments) == int(identity["segment_count"]), "portable V5 segment denominator mismatch")
            seen, bag_parts, totals = set(), defaultdict(list), defaultdict(int)
            for segment in segments:
                key = (int(segment["source_raw_bag_id"]), int(segment["segment_id"]))
                require(key in by_identity and key not in seen, "portable V5 foreign/duplicate segment")
                seen.add(key)
                canonical = by_identity[key]
                require(int(segment["start"]) == canonical["start"] and int(segment["goal"]) == canonical["goal"], "portable V5 OD mismatch")
                population.close(float(segment["release_seconds"]), float(canonical["pass_time"]), "portable canonical D")
                bag_parts[key[0]].append(segment)
                for name in ("moving_ticks", "stopped_ticks", "hold_count"):
                    totals[name] += int(segment[name])
            require(len(bags) == len(bag_parts) == int(identity["raw_bag_count"]), "portable V5 raw denominator mismatch")
            require(len({int(b["source_raw_bag_id"]) for b in bags}) == len(bags), "portable duplicate raw bag")
            scheduled, admitted, completed = [], [], 0
            for bag in bags:
                parts = bag_parts[int(bag["source_raw_bag_id"])]
                done = all(s["status"] == "COMPLETED" for s in parts)
                require(done == (bag["complete"] == "true"), "portable raw completion mismatch")
                require(len(parts) == int(bag["segment_count"]), "portable bag multiplicity mismatch")
                completed += done
                if done:
                    t = sum(float(s["completion_time_seconds"]) - float(s["release_seconds"]) for s in parts)
                    a = sum(float(s["completion_time_seconds"]) - float(s["admission_time_seconds"]) for s in parts)
                    population.close(t, float(bag["table53_scheduled_interval_seconds"]), "portable bag scheduled sum")
                    population.close(a, float(bag["diagnostic_first_admission_to_completion_seconds"]), "portable bag admission sum")
                    scheduled.append(t)
                    admitted.append(a)
            require(completed == int(summary["completed_raw_bags"]) == int(normalized["metrics"]["completed_raw_bag_count"]),
                    "portable completed population mismatch")
            require(totals["moving_ticks"] == int(summary["move_commits"]) and totals["stopped_ticks"] == int(summary["stopped_ticks"])
                    and totals["hold_count"] == int(summary["hold_count"]), "portable counter sum mismatch")
            if eligible:
                for key, metric in {**distribution(scheduled, "tht_scheduled_release"), **distribution(admitted, "tht_admission")}.items():
                    population.close(metric, normalized["metrics"][key], "portable V5 normalized THT")
            recomputed += 1
        elif cell["method"] == "FENG_NATIVE_HCA":
            run_id = normalized["normalization_contract"]["native_run_id"]
            with gzip.open(folder / "hca" / run_id / "segment_lifecycle.csv.gz", "rt", encoding="utf-8", newline="") as handle:
                lifecycle = list(csv.DictReader(handle))
            timing, audit = hca_primary_timing(identity, lifecycle, eligible, expected)
            require(audit["observed_lifecycle_count"] == cell["diagnostic"]["observed_lifecycle_count"], "portable HCA audit mismatch")
            for key, metric in timing.items():
                if metric is not None:
                    population.close(metric, cell["exported_metrics"][key], "portable HCA exported THT")
                else:
                    require(cell["exported_metrics"][key] is None, "portable HCA prohibited THT")
            recomputed += 1
        else:
            native = read_json(folder / "g31/g31_native.json")
            require(native["provenance"]["canonical_sha256"] == identity["canonical_sha256"]
                    and native["provenance"]["binary_sha256"] == external.EXPECTED_G31_BINARY_SHA256
                    and native["execution_integrity"]["pass"] is True, "portable G31 aggregate identity mismatch")
            if eligible:
                for family, prefix in (("java_release", "tht_scheduled_release"), ("processed_attempt", "tht_admission")):
                    for suffix in SUFFIXES:
                        population.close(native["full_population_timing"]["distributions"][family][f"{suffix}_seconds"],
                            cell["exported_metrics"][f"{prefix}_{suffix}_seconds"], "portable G31 aggregate THT")
            aggregate_only += 1
    return {"status": "PASS", "checked_unique_files": len(checked), "observed_cells": manifest["observed_cells"],
            "campaign_status": manifest["status"], "original_absolute_paths_required": False,
            "cells_with_portable_lifecycle_recomputed": recomputed, "G31_cells_with_aggregate_only_evidence": aggregate_only,
            "preflight_independent_bags_verified": preflight_count,
            "campaign_manifest_sha256": sha(root / "campaign_manifest.json"), "verifier_sha256": GENERATOR_SHA}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, default=RESULT_ROOT)
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE_ROOT)
    parser.add_argument("--table-root", type=Path, default=TABLE_ROOT)
    parser.add_argument("--archive", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--verify-archive", action="store_true")
    parser.add_argument("--bootstrap-replicates", type=int, default=10_000)
    args = parser.parse_args()
    if args.verify_archive:
        verification = verify_archive(args.evidence_root)
        external._atomic_json(args.evidence_root / "archive_verification.json", verification)
        print(json.dumps(verification))
        return 0
    result = export_campaign(args.result_root, args.evidence_root, args.table_root,
                             archive=args.archive, replicates=args.bootstrap_replicates)
    print(json.dumps({k: result[k] for k in ("status", "observed_cells", "new_dh_cells", "reused_control_cells", "failures")}))
    return 1 if result["failures"] else 2 if args.require_complete and result["status"] != "COMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())
