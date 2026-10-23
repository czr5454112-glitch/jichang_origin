"""Original map2 1x G31/Feng comparison using the unchanged official request.

No native execution occurs on import, in inspect, or during request preparation.
The six study arms vary only the existing wait-estimator/release input factors.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
import gzip
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from czr005 import cpp_backend
from scripts.eval import run_g4irsf31_map2_native as native
from scripts.experiments.g31_feng_alignment import experiment as common, metrics

CAMPAIGN = ROOT / "outputs/experiments/g31_feng_alignment_map2_20261023"
CANONICAL = native.DEFAULT_WORKLOAD_1X
CASE_ID = "t5_2_map2_1x_speed_2"
HORIZON = native.FIXED_END_EPOCH
MODES = ("legacy", "eta_calendar", "eta_flow")


def prepare_request(binary: Path | None, mode: str = "legacy", release_trace: Path | None = None):
    """Prepare the whole official cohort, optionally aligning generator epochs."""
    if mode not in MODES:
        raise ValueError("unknown wait estimator")
    canonical = metrics.read_jsonl(CANONICAL)
    workload = native.load_workload(1)
    if common.normalize(workload.rows) != canonical:
        raise ValueError("official workload differs from the map2 canonical evidence")
    release_contract = "canonical_pass_time_own_source"
    if release_trace is not None:
        releases = metrics.generator_releases(canonical, metrics.java_segments(release_trace))
        workload = replace(workload, rows=tuple(
            {**row, "pass_time": releases[row["segment_id"]]} for row in workload.rows))
        release_contract = "same_Java_generator_release_epoch_single_run_sensitivity"
    request, rows, rejected, local = native.prepare_native_request(
        native.case_by_id(CASE_ID), workload, binary=binary)
    if rejected or len(rows) != native.SCALE_COUNTS[1][1]:
        raise ValueError("map2 comparison must retain every canonical segment")
    if request["max_simulation_time"] != HORIZON or request["max_events"] != native.MAX_EVENTS:
        raise ValueError("official map2 stopping contract changed")
    if set(edge[3] for edge in request["edge_records"]) != {2.0}:
        raise ValueError("map2 comparison requires 2 m/s on both implementations")
    if request.get("local_queue_capacity") != 0 or request.get("enable_edge_capacity_holding", False):
        raise ValueError("this campaign adds no queue or edge capacity")
    request["s4_wait_estimator"] = mode
    return request, canonical, {
        "map_id": native.MAP_ID,
        "case_id": CASE_ID,
        "workload_protocol": workload.protocol,
        "raw_bags": workload.raw_bag_count,
        "segments": workload.segment_count,
        "leg_counts": dict(Counter(row["leg"] for row in canonical)),
        "start_epoch": native.FIXED_START_EPOCH,
        "horizon": HORIZON,
        "max_events": native.MAX_EVENTS,
        "speed_mps": 2.0,
        "map": common.evidence(native.CANONICAL_MAP_PATH),
        "canonical": common.evidence(CANONICAL),
        "node_count": len(request["node_records"]),
        "directed_edge_count": len(request["edge_records"]),
        "storage_in_goals": sorted({row["goal"] for row in canonical if row["leg"] == "storage_in"}),
        "storage_out_starts": sorted({row["start"] for row in canonical if row["leg"] == "storage_out"}),
        "release_contract": release_contract,
        "release_trace": common.evidence(release_trace) if release_trace else None,
        "scheduled_pass_range": [min(row["pass_time"] for row in canonical), max(row["pass_time"] for row in canonical)],
        "official_local_contract": local,
    }


def source_paths():
    paths = [Path(__file__), Path(common.__file__), Path(metrics.__file__),
             ROOT / "src/czr005/cpp_backend.py", ROOT / "CMakeLists.txt"]
    paths += [ROOT / "scripts/eval" / name for name in (
        "run_g4irsf31_map2_native.py", "g4irsf31_map_adapter.py", "g4irsf11_fixed_map.py",
        "g4irsf14_opportunity_census.py", "run_g4irsf28_service_potential.py",
        "run_g4irsf31_nanning_native.py")]
    paths += [p for p in (ROOT / "cpp").rglob("*")
              if p.is_file() and p.suffix in (".hpp", ".h", ".cpp") and "loaded_transport" not in p.name]
    return paths


def run_native(args):
    binary = args.binary.resolve(strict=True)
    directory = args.output.resolve()
    if directory.exists():
        raise FileExistsError("preserve previous runs; choose a fresh directory")
    request, canonical, contract = prepare_request(binary, args.s4_wait_estimator, args.same_hca_release)
    request["trace_limit"] = args.trace_limit
    request["event_trace_limit"] = args.event_trace_limit
    directory.mkdir(parents=True)
    with gzip.open(directory / "request.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(common.normalize(request), handle)
    paths = source_paths()
    for path in paths:
        frozen = directory / "source" / path.relative_to(ROOT)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, frozen)
    (directory / "binary").mkdir()
    shutil.copyfile(binary, directory / "binary" / binary.name)
    (directory / "inputs").mkdir()
    shutil.copyfile(CANONICAL, directory / "inputs" / CANONICAL.name)
    shutil.copyfile(native.CANONICAL_MAP_PATH, directory / "inputs" / native.CANONICAL_MAP_PATH.name)
    manifest = {"schema": "g31.feng_alignment.arm.v1", "arm": args.arm, "reused": False,
                "map_id": native.MAP_ID, "map2_contract": contract,
                "execution_contract": common.NATIVE_CONTRACT,
                "release_contract": contract["release_contract"], "release_trace": contract["release_trace"],
                "canonical": common.evidence(CANONICAL), "binary": common.evidence(binary),
                "sources": [common.evidence(p) for p in paths],
                "score_overrides": {"s4_wait_estimator": args.s4_wait_estimator},
                "request": common.evidence(directory / "request.json.gz"), "argv": sys.argv,
                "source_snapshot_boundary": "current request/harness source and native binary recorded separately",
                "causality_policy": "independent scheduled EBS segments; no predecessor coupling"}
    common.write(directory / "manifest.json", manifest)
    started = time.perf_counter()
    payload = cpp_backend.g4irsf11_event_runtime_from_records(**request)
    manifest["native_call_wall_seconds_excluding_serialization"] = time.perf_counter() - started
    if common.sha(binary) != manifest["binary"]["sha256"]:
        raise ValueError("binary changed during execution")
    with gzip.open(directory / "native_payload.json.gz", "wt", encoding="utf-8") as handle:
        json.dump(payload, handle)
    manifest["native_payload"] = common.evidence(directory / "native_payload.json.gz")
    common.finish(directory, canonical, metrics.native_segments(payload), manifest, payload["summary"], horizon=HORIZON)


def import_java(args):
    source = args.source.resolve(strict=True)
    directory = args.output.resolve()
    if directory.exists():
        raise FileExistsError("preserve previous imported results")
    canonical = metrics.read_jsonl(CANONICAL)
    recorded = common.read(source / "source_input_manifest.json")
    status = common.read(source / "run_01/run_status.json")
    if status["status"] != "complete" or status["speed_mps"] != 2 or status["fault_schedule"] != "none":
        raise ValueError("original Java run contract mismatch")
    for key, expected in (("raw_bags", native.SCALE_COUNTS[1][0]), ("segments", native.SCALE_COUNTS[1][1])):
        if recorded[key] != expected:
            raise ValueError("Java source manifest has the wrong population")
    source_checks = []
    for record in recorded["source_comparison"]:
        path = Path(recorded["original_project"]) / record["path"]
        if common.sha(path) != record["original_sha256"]:
            raise ValueError(f"original Java source changed: {path}")
        source_checks.append({**common.evidence(path), "expected_sha256": record["original_sha256"]})
    input_checks = []
    for record in recorded["inputs"]:
        path = Path(record["path"])
        if common.sha(path) != record["sha256"]:
            raise ValueError(f"Java runtime input changed: {path}")
        input_checks.append({**common.evidence(path), "expected_sha256": record["sha256"]})
    actual = metrics.java_segments(source / "run_01/segment_lifecycle.csv")
    # This rejects Nanning traces even though both maps use the same bag IDs.
    metrics.generator_releases(canonical, actual)
    directory.mkdir(parents=True)
    manifest = {"schema": "g31.feng_alignment.arm.v1", "arm": "Java_HCA_original_map2", "reused": False,
                "map_id": native.MAP_ID,
                "execution_contract": "original_Feng_Java_node_time_windows_no_edge_capacity",
                "release_contract": "original_Java_source_generation_and_full_route_planning",
                "canonical": common.evidence(CANONICAL), "map": common.evidence(native.CANONICAL_MAP_PATH),
                "original_project": recorded["original_project"], "verified_original_sources": source_checks,
                "verified_runtime_inputs": input_checks,
                "source_evidence": [common.evidence(source / p) for p in (
                    "source_input_manifest.json", "compile_receipt.json", "run_01/run_status.json",
                    "run_01/segment_lifecycle.csv", "run_01/routes.csv", "run_01/output.txt", "run_01/outputstarttime.txt")],
                "wall_seconds_original_run": status["wall_seconds"],
                "fresh_campaign_execution": True, "import_executes_java": False,
                "causality_policy": "independent scheduled EBS segments; violations reported without unilateral correction"}
    common.finish(directory, canonical, actual, manifest, horizon=HORIZON)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("inspect", help="validate/read the official map2 request without executing it")
    run = commands.add_parser("run-native")
    run.add_argument("--arm", required=True)
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--s4-wait-estimator", choices=MODES, default="legacy")
    run.add_argument("--same-hca-release", type=Path)
    run.add_argument("--trace-limit", type=int, default=0)
    run.add_argument("--event-trace-limit", type=int, default=0)
    java = commands.add_parser("import-java")
    java.add_argument("--source", type=Path, default=CAMPAIGN / "java_native_1x")
    java.add_argument("--output", type=Path, default=CAMPAIGN / "java_original_001")
    audit = commands.add_parser("audit")
    audit.add_argument("--arm", action="append", required=True)
    audit.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inspect":
        _, _, contract = prepare_request(None)
        print(json.dumps(contract, ensure_ascii=False, indent=2, default=str))
    elif args.command == "run-native":
        run_native(args)
    elif args.command == "import-java":
        import_java(args)
    else:
        common.audit_arms(args, canonical_path=CANONICAL, horizon=HORIZON)


if __name__ == "__main__":
    main()
