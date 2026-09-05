"""Export validated comparison cells and portable full-population DH evidence."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external
from scripts.eval.run_feng_repaired_campaign import RESULT_ROOT, METHOD

EVIDENCE_ROOT = ROOT / "outputs/evidence/feng_cie_dh_repair_20260905"
TABLE = ROOT / "outputs/tables/feng_cie_dh_repaired_cells_20260905.csv"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def archive_native(native: Path, target: Path) -> dict:
    target.mkdir(parents=True, exist_ok=True)
    files = {}
    for name in ("bags.csv", "segments.csv", "summary.csv", "event_summary.csv", "runner_status.json"):
        source = native / name
        sha = external._sha256_file(source)
        if name in {"bags.csv", "segments.csv"}:
            destination = target / (name + ".gz")
            if not destination.exists():
                with source.open("rb") as raw, destination.open("wb") as out:
                    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0) as compressed:
                        shutil.copyfileobj(raw, compressed)
            with gzip.open(destination, "rb") as handle:
                restored_sha = hashlib.file_digest(handle, "sha256").hexdigest()
            if restored_sha != sha:
                raise ValueError(f"archived population differs from native output: {destination}")
        else:
            destination = target / name
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                raise ValueError(f"refusing to replace different frozen evidence: {destination}")
            shutil.copyfile(source, destination)
        files[name] = {"native_sha256": sha, "native_bytes": source.stat().st_size,
                       "archive_path": destination.relative_to(ROOT).as_posix(),
                       "archive_sha256": external._sha256_file(destination),
                       "archive_bytes": destination.stat().st_size}
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, default=RESULT_ROOT)
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    rows, archive_records, normalized_paths = [], [], []
    for map_name in external.MAPS:
        for load in external.LOAD_FACTORS:
            for seed in external.SEEDS:
                for method in external.METHODS:
                    cell = external.cell_dir(args.result_root, load, seed, map_name)
                    path = cell / f"{method}.json"
                    if not path.exists():
                        continue
                    value = external.load_normalized_result(path)
                    normalized_paths.append(path)
                    identity = json.loads(Path(value["workload_identity_path"]).read_text(encoding="utf-8"))
                    row = {"map": map_name, "load_factor": load, "seed": seed, "method": method,
                           "raw_bag_count": identity["raw_bag_count"], "segment_count": identity["segment_count"],
                           "full_population_complete": value["full_population_complete"],
                           "map_sha256": identity["map_sha256"], "input_sha256": identity["raw_sha256"],
                           "workload_identity_sha256": value["workload_identity_sha256"], **value["metrics"]}
                    row["latency_definition"] = "SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_ADMISSION"
                    row["scheduled_release_latency_definition"] = "SUM_PER_BAG_SEGMENT_COMPLETION_MINUS_SCHEDULED_RELEASE_NOT_HISTORICAL_SHARED_D"
                    row["wall_seconds"] = row["cpu_seconds"] = row["decision_requests"] = None
                    for suffix in ("mean", "p95", "p99", "max"):
                        row[f"scheduled_release_latency_{suffix}_seconds"] = None
                    timing_eligible = load != 2.0 and value["full_population_complete"]
                    original = external.cell_dir(external.DEFAULT_RESULT_ROOT, load, seed, map_name)
                    if method == METHOD:
                        native = cell / "feng_env_dh" if map_name == "nanning" else original / "feng_env_dh"
                        summary = read_csv(native / "summary.csv")[0]
                        bags, segments = read_csv(native / "bags.csv"), read_csv(native / "segments.csv")
                        if len(bags) != int(identity["raw_bag_count"]) or len(segments) != int(identity["segment_count"]):
                            raise ValueError(f"native population row count mismatch: {native}")
                        ids = {b["source_raw_bag_id"] for b in bags}
                        if len(ids) != len(bags) or any(s["source_raw_bag_id"] not in ids for s in segments):
                            raise ValueError(f"bag identity lost or duplicated: {native}")
                        row["native_terminal_status"] = summary["status"]
                        row["wall_seconds"] = float(summary["wall_seconds"])
                        row["decision_requests"] = int(summary["route_decisions"])
                        row["decision_count_definition"] = "LOGICAL_ROUTE_REQUESTS_INCLUDING_EACH_TICK_HOLD_RETRY_NOT_ACTUAL_SCORE_COMPUTATIONS"
                        row["source_sha256"] = value["normalization_contract"]["reconstruction_java_source_sha256"]
                        row["class_sha256"] = value["normalization_contract"]["compiled_java_class_sha256"]
                        row["reproduction_level"] = summary["reproduction_level"]
                        if timing_eligible:
                            # External DH has no Table5.3 schedule. This native
                            # field is still exactly sum(completion-release),
                            # independently checked below from every segment.
                            grouped = {key: 0.0 for key in ids}
                            for segment in segments:
                                if segment["status"] != "COMPLETED":
                                    raise ValueError("full-population flag with an incomplete segment")
                                grouped[segment["source_raw_bag_id"]] += float(segment["completion_time_seconds"]) - float(segment["release_seconds"])
                            times = sorted(grouped.values())
                            for bag in bags:
                                if abs(grouped[bag["source_raw_bag_id"]] - float(bag["table53_scheduled_interval_seconds"])) > 1e-6:
                                    raise ValueError("scheduled-release aggregation differs from native bag output")
                            for suffix, metric in {"mean": statistics.fmean(times), "p95": external.internal_random._quantile(times, .95),
                                                   "p99": external.internal_random._quantile(times, .99), "max": times[-1]}.items():
                                row[f"scheduled_release_latency_{suffix}_seconds"] = metric
                        if args.archive and map_name == "nanning":
                            target = external.cell_dir(EVIDENCE_ROOT, load, seed, map_name)
                            files = archive_native(native, target)
                            external._atomic_json(target / "normalized_result.json", value)
                            external._atomic_json(target / "workload_identity.json", identity)
                            archive_records.append({"map": map_name, "load_factor": load, "seed": seed,
                                                    "raw_bag_count": len(bags), "segment_count": len(segments),
                                                    "source_sha256": row["source_sha256"], "files": files})
                    elif method == external.REFERENCE_METHOD:
                        native = json.loads((original / "g31_native.json").read_text(encoding="utf-8"))
                        runtime = native["runtime"]
                        row.update(wall_seconds=runtime.get("wall_seconds"), cpu_seconds=runtime.get("cpu_seconds"),
                                   decision_requests=runtime.get("decision_count"), native_terminal_status=native["status"])
                        row["binary_sha256"] = native["provenance"]["binary_sha256"]
                        row["decision_count_definition"] = "NATIVE_RUNTIME_DECISION_COUNT_JUNCTION_ARRIVALS_NOT_DH_TICK_REQUESTS"
                        if timing_eligible:
                            distribution = native["full_population_timing"]["distributions"]["java_release"]
                            for suffix in ("mean", "p95", "p99", "max"):
                                row[f"scheduled_release_latency_{suffix}_seconds"] = distribution[f"{suffix}_seconds"]
                    else:
                        native = json.loads((original / "hca_native/fresh_hca_summary.json").read_text(encoding="utf-8"))
                        row["wall_seconds"] = native["runs"][0]["wall_seconds"]
                    rows.append(row)
    external._write_aggregate_csv(TABLE, rows)
    if args.archive:
        external._atomic_json(EVIDENCE_ROOT / "archive_manifest.json", {
            "schema": "czr005.feng_repaired_portable_population_evidence.v1",
            "all_populations_retained": True, "cell_count": len(archive_records), "cells": archive_records})
        control = ROOT / "outputs/runtime/cie_external_baseline_zero_through_v1/nanning_1p00x/seed_104729/feng_env_dh"
        if (control / "summary.csv").is_file():
            status = json.loads((control / "runner_status.json").read_text(encoding="utf-8"))
            if status["identity"]["reconstruction_java_source_aggregate_sha256"] != "3b47ffcefa558365e55e27508fc8904608026fd3235102eee6c305539999a208":
                raise ValueError("unexpected unoptimized control version")
            target = EVIDENCE_ROOT / "correctness_unoptimized_nanning_1x_seed104729"
            files = archive_native(control, target)
            external._atomic_json(target / "archive_manifest.json", {
                "scope": "UNOPTIMIZED_CORRECTNESS_CONTROL_NOT_AN_ADDITIONAL_MATRIX_CELL", "files": files})
    aggregate = external.aggregate_results(normalized_paths)
    external._atomic_json(ROOT / "outputs/tables/feng_cie_dh_repaired_paired_20260905.json", aggregate)
    external._write_aggregate_csv(ROOT / "outputs/tables/feng_cie_dh_repaired_paired_20260905.csv", aggregate["rows"])
    print(json.dumps({"status": aggregate["status"], "cells": len(rows), "archived_dh_cells": len(archive_records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
