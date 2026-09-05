"""Retain native pre/post optimization traces; never compile over either build.

Run from the repository with --output pointing to a new evidence directory.
Both production builds and tests/java/App harnesses must already be compiled.
Use --archive-only --output EXISTING_DIRECTORY to package passed raw evidence
without compiling or executing either simulator.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def same(left: Path, right: Path) -> dict:
    left_sha, right_sha = sha(left), sha(right)
    assert left_sha == right_sha, (left, right)
    return {"unoptimized": str(left), "optimized": str(right),
            "sha256": left_sha, "byte_identical": True,
            "size_bytes": left.stat().st_size}


def run(command: list[str], output: Path) -> None:
    result = subprocess.run(command, cwd=ROOT, capture_output=True, check=False)
    output.write_bytes(result.stdout)
    output.with_suffix(".stderr.txt").write_bytes(result.stderr)
    assert result.returncode == 0, (command, result.returncode, result.stderr)


def archive_shared_native(output: Path, verification: dict) -> dict:
    """Archive one copy only after both raw files match the recorded comparison."""
    if verification.get("status") != "PASS":
        raise ValueError("only passed equivalence evidence can be archived")
    recorded = {Path(row["unoptimized"]).name: row
                for row in verification["checks"]["nanning_native_files"]}
    directory = output / "nanning_128_trace1"
    archives = []
    for name in ("trace.csv", "bags.csv", "segments.csv"):
        comparison = same(directory / "unoptimized" / name, directory / "optimized" / name)
        if not recorded[name].get("byte_identical") or any(
                comparison[field] != recorded[name][field] for field in ("sha256", "size_bytes")):
            raise ValueError(f"raw evidence changed after the passed comparison: {name}")
        destination = directory / f"shared_{name}.gz"
        if not destination.exists():
            with (directory / "unoptimized" / name).open("rb") as source, destination.open("xb") as target:
                # Empty filename and zero mtime remove path/time-dependent headers.
                with gzip.GzipFile(filename="", mode="wb", fileobj=target,
                                   compresslevel=9, mtime=0) as compressed:
                    shutil.copyfileobj(source, compressed)
        digest = hashlib.sha256()
        restored_bytes = 0
        with gzip.open(destination, "rb") as restored:
            while chunk := restored.read(1024 * 1024):
                digest.update(chunk)
                restored_bytes += len(chunk)
        if digest.hexdigest() != comparison["sha256"] or restored_bytes != comparison["size_bytes"]:
            raise ValueError(f"archive differs from matched raw evidence: {destination}")
        archives.append({"native_filename": name, "both_variants_byte_identical": True,
                         "uncompressed_sha256": comparison["sha256"],
                         "uncompressed_size_bytes": comparison["size_bytes"],
                         "archive_path": destination.name,
                         "archive_sha256": sha(destination),
                         "archive_size_bytes": destination.stat().st_size,
                         "lossless_round_trip_verified": True})
    manifest = {"schema": "czr005.feng_dh_shared_optimization_trace_archive.v1",
                "status": "PASS", "population": verification["representative_congestion"],
                "archive_path_base": "this manifest directory",
                "gzip_contract": {"filename": "", "mtime": 0, "compresslevel": 9},
                "source_production_builds": verification["production_builds"], "files": archives}
    manifest_path = directory / "shared_archive_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return {"manifest_path": "nanning_128_trace1/shared_archive_manifest.json",
            "manifest_sha256": sha(manifest_path), "file_count": len(archives),
            "total_uncompressed_size_bytes": sum(row["uncompressed_size_bytes"] for row in archives),
            "total_archive_size_bytes": sum(row["archive_size_bytes"] for row in archives)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--java")
    parser.add_argument("--unoptimized-classes", type=Path)
    parser.add_argument("--optimized-classes", type=Path)
    parser.add_argument("--test-classes", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.archive_only:
        verification_path = output / "verification.json"
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
        verification["shared_native_archive"] = archive_shared_native(output, verification)
        verification_path.write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": "PASS", "simulations_run": 0,
                          "shared_native_archive": verification["shared_native_archive"]}))
        return
    if not all((args.java, args.unoptimized_classes, args.optimized_classes, args.test_classes)):
        parser.error("simulation mode requires --java, both production builds and --test-classes")
    output.mkdir(parents=True, exist_ok=False)
    builds = {"unoptimized": args.unoptimized_classes.resolve(),
              "optimized": args.optimized_classes.resolve()}
    identities = {}
    commands = []
    for variant, classes in builds.items():
        identities[variant] = json.loads(
            (classes / "feng_cie_dh_compile_identity.json").read_text())
        cp = os.pathsep.join((str(args.test_classes.resolve()), str(classes)))
        command = [args.java, "-cp", cp, "App.FengDhOptimizationRegression"]
        commands.append(command)
        run(command, output / f"{variant}_cache_regression.jsonl")
        command = [args.java, "-cp", str(classes), "App.FengDhBenchmark", "microtests",
                   "--json-out", str(output / f"{variant}_T1_T10.jsonl")]
        commands.append(command)
        run(command, output / f"{variant}_microtests.stdout.txt")
        command = [args.java, "-cp", cp, "App.ZeroThroughAudit", "--gate",
                   str(output / f"{variant}_zero_through"),
                   str(ROOT / "data/processed/maps/nanning_legacy.txt")]
        commands.append(command)
        run(command, output / f"{variant}_zero_through.jsonl")

    checks = {name: same(output / f"unoptimized_{name}", output / f"optimized_{name}")
              for name in ("cache_regression.jsonl", "T1_T10.jsonl", "zero_through.jsonl")}
    checks["zero_through_traces"] = [
        same(path, output / "optimized_zero_through" / path.name)
        for path in sorted((output / "unoptimized_zero_through").glob("*")) if path.is_file()]
    workload = ROOT / "data/processed/workloads/cie_external_robustness/nanning_1p00x/seed_104729/inputdata.txt"
    map_path = ROOT / "data/processed/maps/nanning_legacy.txt"
    summaries = {}
    for variant, classes in builds.items():
        destination = output / "nanning_128_trace1" / variant
        command = [args.java, "-Djava.awt.headless=true", "-cp", str(classes),
                   "App.FengDhBenchmark", "run", "--map", str(map_path),
                   "--input", str(workload), "--output", str(destination),
                   "--alpha", "0.4", "--beta", "0.8", "--limit", "128",
                   "--seed", "104729", "--horizon-seconds", "98259",
                   "--trace-sample-modulo", "1", "--storage-in-goal", "53",
                   "--storage-out-start", "53"]
        commands.append(command)
        run(command, output / f"{variant}_nanning.stdout.txt")
        with (destination / "summary.csv").open(encoding="utf-8", newline="") as stream:
            summaries[variant] = next(csv.DictReader(stream))
    unoptimized = output / "nanning_128_trace1/unoptimized"
    optimized = output / "nanning_128_trace1/optimized"
    checks["nanning_native_files"] = [same(unoptimized / name, optimized / name)
                                       for name in ("bags.csv", "segments.csv", "trace.csv", "event_summary.csv")]
    summary_keys = set(summaries["unoptimized"]) | set(summaries["optimized"])
    differences = {key: [summaries["unoptimized"].get(key), summaries["optimized"].get(key)]
                   for key in summary_keys
                   if summaries["unoptimized"].get(key) != summaries["optimized"].get(key)}
    assert set(differences).issubset({"wall_seconds"}), differences
    old = summaries["unoptimized"]
    assert old["status"] == "COMPLETE" and old["completed_raw_bags"] == "128", old
    assert int(old["hold_count"]) > 0 and int(old["stopped_ticks"]) > 0, old
    # Repeated requests for the same OD within a tick exercise dynamic reuse.
    seen = set()
    repeated = 0
    segments = {}
    with (unoptimized / "segments.csv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            segments[row["task_id"]] = row
    with (unoptimized / "trace.csv").open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if row.get("event") != "SELECT":
                continue
            key = (row["tick"], row["node"], segments[row["task_id"]]["goal"])
            if key in seen:
                repeated += 1
            seen.add(key)
    assert repeated > 0, "representative case did not exercise repeated snapshot/OD requests"
    result = {"schema": "czr005.feng_dh_optimization_equivalence.v1", "status": "PASS",
              "production_builds": identities, "commands": commands,
              "map_sha256": sha(map_path), "input_sha256": sha(workload),
              "checks": checks, "summary_differences_allowed_wall_only": differences,
              "representative_congestion": {key: old[key] for key in (
                  "raw_bag_count", "segment_count", "route_decisions", "tied_route_decisions",
                  "hold_count", "stopped_ticks", "junction_through_busy_holds", "following_footprint_holds")},
              "repeated_snapshot_node_goal_requests": repeated}
    result["shared_native_archive"] = archive_shared_native(output, result)
    (output / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "representative_congestion": result["representative_congestion"],
                      "repeated_snapshot_node_goal_requests": repeated,
                      "wall_seconds": differences.get("wall_seconds")}))


if __name__ == "__main__":
    main()
