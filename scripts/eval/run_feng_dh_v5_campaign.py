"""Run the separately identified, user-selected V5 DH matrix after 522 OD checks.

Stages: preflight, plan, reuse, run. Only run launches full-population DH cells.
Control reuse is explicit and never includes any previous DH result. HCA reuse
has an archived-build provenance limitation; plan also emits fresh-HCA commands.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_cie_external_baseline_robustness as external
from scripts.eval import run_feng_paper_env_cie_dh as feng
from scripts.eval import audit_feng_zero_through_regression as od

METHOD = "FENG_DH_BOUNDARY_CLEARANCE_V5"
SOURCE = ROOT / "benchmarks/java/feng_cie_dh_boundary_clearance_v5/App"
SOURCE_SHA = "7deb321e34b9ebdd562eeac0c5293618df41441830789498b37ddb4bca1cccc7"
CLASS_SHA = "a0a0c35bc2e3576c83f23a60f6a3cd807f3c66ae0ea24304924b9f7fe193b869"
REFERENCE = ROOT / "outputs/runtime/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5/run_identity.json"
PROTOCOL = ROOT / "docs/baselines/feng_dh_v5_acceptance_and_campaign_protocol_20260905.md"
RESULT_ROOT = ROOT / "outputs/runtime/cie_external_baseline_boundary_clearance_v5"
CLASSES = ROOT / "build/feng_dh_v5_campaign"
BUILD_IDENTITY = "v5_campaign_compile_identity.json"
BINARY = ROOT / "build/nanning_ablation_gate_f_pybind/python/Release/czr005_cpp.cp311-win_amd64.pyd"
CONTROLS = ("FENG_NATIVE_HCA", "G31_S4_NATIVE_SYSTEM")
OD_HARNESS = ROOT / "benchmarks/java/feng_cie_dh_audit/App/FengDhOdAudit.java"
DOMAIN_HARNESS = ROOT / "tests/java/App/V5ClearanceDomainAudit.java"


def write(path: Path, value: object) -> None:
    external._atomic_json(path, value)


def sha(path: Path) -> str:
    return external._sha256_file(path)


def aggregate(paths: list[Path], root: Path) -> str:
    return feng._aggregate_sha256(paths, root)


def files(root: Path, pattern: str) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob(pattern))}


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def executable(name: str) -> str:
    return str(Path(shutil.which(name) or name).resolve(strict=True))


def tool_identity(path: str) -> dict:
    run = subprocess.run([path, "-version"], capture_output=True, text=True, check=True)
    return {"path": path, "sha256": sha(Path(path)), "version": (run.stdout + run.stderr).strip()}


def check_source() -> dict:
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    check(files(SOURCE, "*.java") == reference["source_files"], "V5 frozen source file identity drift")
    check(aggregate(list(SOURCE.glob("*.java")), SOURCE.parent) == SOURCE_SHA, "V5 source aggregate drift")
    return reference


def compiled_identity(classes: Path) -> dict:
    reference = check_source()
    check(files(classes, "*.class") == reference["class_files"], "V5 classes differ from formal JDK18 V5 run")
    check(aggregate(list(classes.rglob("*.class")), classes) == CLASS_SHA, "V5 class aggregate drift")
    value = json.loads((classes / BUILD_IDENTITY).read_text(encoding="utf-8"))
    check(value["source_aggregate_sha256"] == SOURCE_SHA and value["class_aggregate_sha256"] == CLASS_SHA,
          "compile manifest identity drift")
    return value


def compile_production(args: argparse.Namespace) -> dict:
    reference = check_source()
    manifest = args.classes_dir / BUILD_IDENTITY
    if manifest.exists():
        value = compiled_identity(args.classes_dir)
        check(value["javac"] == tool_identity(args.javac), "compiler identity changed; use a new build directory")
        return value
    check(not list(args.classes_dir.rglob("*.class")), "unidentified class files already exist in new build")
    args.classes_dir.mkdir(parents=True, exist_ok=True)
    command = [args.javac, "-encoding", "UTF-8", "-d", str(args.classes_dir),
               *map(str, sorted(SOURCE.glob("*.java")))]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    check(files(args.classes_dir, "*.class") == reference["class_files"], "new classes do not match formal V5 run")
    value = {"schema": "czr005.feng_v5_campaign_compile.v1", "method": METHOD,
             "source_dir": str(SOURCE), "source_aggregate_sha256": SOURCE_SHA,
             "class_aggregate_sha256": aggregate(list(args.classes_dir.rglob("*.class")), args.classes_dir),
             "source_files": reference["source_files"], "class_files": reference["class_files"],
             "compile_command": command, "javac": tool_identity(args.javac),
             "reference_identity_path": str(REFERENCE), "reference_identity_sha256": sha(REFERENCE)}
    write(manifest, value)
    return compiled_identity(args.classes_dir)


def preflight(args: argparse.Namespace) -> dict:
    if (args.result_root / "preflight/preflight.json").exists():
        return require_preflight(args)
    build = compile_production(args)
    output = args.result_root / "preflight"
    output.mkdir(parents=True, exist_ok=True)
    # This reuses only OD derivation, redirecting its output into this campaign.
    old_out = od.OUT
    try:
        od.OUT = output / "coverage"
        od.prepare()
    finally:
        od.OUT = old_out
    coverage = json.loads((output / "coverage/formal_od_coverage.json").read_text(encoding="utf-8"))
    check(coverage["unique_formal_ods"] == {"map2": 25, "nanning": 496}, "OD coverage changed")
    # Recompute every raw/canonical/map byte identity, not just identity declarations.
    for i, entry in enumerate(coverage["source_cells"], 1):
        external.audit_cell(ROOT / entry["identity_path"])
        if i % 10 == 0:
            print(json.dumps({"preflight_workloads_reaudited": i, "total": 60}), flush=True)
    harness_classes = args.classes_dir.parent / (args.classes_dir.name + "_od_audit")
    harness_classes.mkdir(parents=True, exist_ok=True)
    command = [args.javac, "-encoding", "UTF-8", "-cp", str(args.classes_dir), "-d", str(harness_classes),
               str(OD_HARNESS), str(DOMAIN_HARNESS)]
    subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
    classpath = os.pathsep.join(map(str, [args.classes_dir, harness_classes]))
    results, domains, evidence = {}, {}, []
    for name, count in (("map2", 25), ("nanning", 496), ("nanning_topology_witness", 1)):
        map_name = "map2" if name == "map2" else "nanning"
        map_path = external.map_protocol(map_name).map_path
        od_path = output / "coverage" / (name + (".tsv" if name.endswith("witness") else "_formal_ods.tsv"))
        result_path = output / (name + "_single_bag.jsonl")
        run_command = [args.java, "-Xmx1536m", "-cp", classpath, "App.FengDhOdAudit", str(map_path),
                       str(od_path), str(result_path), "require-pass"]
        run = subprocess.run(run_command, cwd=ROOT, capture_output=True, text=True, check=True)
        records = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines()]
        check(len(records) == count, f"{name} OD count differs")
        check(all(r["reachable"] and r["status"] == "COMPLETE" and r["first_invalid_state"] is None
                  and r["repeated_zero_service_starts"] == 0 for r in records), f"{name} OD failed")
        parent_path = ROOT / "outputs/runtime/feng_cie_dh_zero_through_repair_20260905/regression_optimized" / (
            "repaired_" + name + "_single_bag.jsonl.gz")
        parent = [json.loads(line) for line in gzip.decompress(parent_path.read_bytes()).decode().splitlines()]
        expected = {(r["start"], r["goal"]): r["completion_tick"] for r in parent}
        check({(r["start"], r["goal"]): r["completion_tick"] for r in records} == expected,
              f"{name} uncongested completion timing changed from parent")
        archive = result_path.with_suffix(".jsonl.gz")
        archive.write_bytes(gzip.compress(result_path.read_bytes(), mtime=0))
        evidence.append({"path": str(archive), "sha256": sha(archive), "uncompressed_sha256": sha(result_path)})
        results[name] = {"count": count, "complete": count, "parent_completion_ticks_identical": True,
                         "parent_reference_path": str(parent_path), "parent_reference_sha256": sha(parent_path),
                         "command": run_command, "stdout": run.stdout, "stderr": run.stderr}
        if map_name not in domains:
            domain_command = [args.java, "-cp", classpath, "App.V5ClearanceDomainAudit", str(map_path)]
            domain_run = subprocess.run(domain_command, cwd=ROOT, capture_output=True, text=True, check=True)
            domains[map_name] = {**json.loads(domain_run.stdout), "command": domain_command,
                                 "map_path": str(map_path), "map_sha256": sha(map_path)}
        print(json.dumps({"preflight": name, "completed": count}), flush=True)
    compiled_identity(args.classes_dir)
    value = {"schema": "czr005.feng_v5_campaign_preflight.v1", "status": "PASS", "method": METHOD,
             "source_aggregate_sha256": SOURCE_SHA, "class_aggregate_sha256": CLASS_SHA,
             "compile_identity": build, "java": tool_identity(args.java), "compile_harness_command": command,
             "harness_sources": {str(p): sha(p) for p in (OD_HARNESS, DOMAIN_HARNESS)},
             "harness_class_files": files(harness_classes, "*.class"), "total_independent_bags": 522,
             "results": results, "all_edge_clearance_domain": domains, "archives": evidence,
             "coverage_path": str(output / "coverage/formal_od_coverage.json"),
             "coverage_sha256": sha(output / "coverage/formal_od_coverage.json"),
             "scope": "Independent single bags and all-edge V5 applicability; not a congestion validation."}
    write(output / "preflight.json", value)
    return value


def require_preflight(args: argparse.Namespace) -> dict:
    compiled_identity(args.classes_dir)
    value = json.loads((args.result_root / "preflight/preflight.json").read_text(encoding="utf-8"))
    check(value["status"] == "PASS" and value["total_independent_bags"] == 522, "522-bag preflight required")
    check(value["source_aggregate_sha256"] == SOURCE_SHA and value["class_aggregate_sha256"] == CLASS_SHA,
          "preflight runtime identity differs")
    check(value["java"] == tool_identity(args.java), "Java runtime changed since preflight")
    for item in value["archives"]:
        data = Path(item["path"])
        check(sha(data) == item["sha256"], "preflight archive identity drift")
        check(hashlib.sha256(gzip.decompress(data.read_bytes())).hexdigest() == item["uncompressed_sha256"],
              "preflight archive decompressed identity drift")
    check(sha(Path(value["coverage_path"])) == value["coverage_sha256"], "preflight coverage identity drift")
    for map_name, domain in value["all_edge_clearance_domain"].items():
        check(sha(Path(domain["map_path"])) == domain["map_sha256"] == external.map_protocol(map_name).expected_map_sha256,
              "preflight map differs from frozen map")
    for path, expected in value["harness_sources"].items():
        check(sha(Path(path)) == expected, "preflight harness source changed")
    return value


def cells(args: argparse.Namespace):
    for map_name in external._selection(args.map, external.MAPS):
        for load in external._selection(args.load_factor, external.LOAD_FACTORS):
            for seed in external._selection(args.seed, external.SEEDS):
                yield map_name, load, seed


def run_spec(args: argparse.Namespace, map_name: str, load: float, seed: int) -> tuple[Path, Path, list, dict]:
    identity_path = external.cell_dir(external.DEFAULT_WORKLOAD_ROOT, load, seed, map_name) / "identity.json"
    _, workload = external._identity_payload(identity_path)
    protocol = external.map_protocol(map_name)
    check(workload["map"] == map_name and float(workload["load_factor"]) == load and workload["seed"] == seed,
          "workload coordinates differ from requested cell")
    check(workload["map_sha256"] == protocol.expected_map_sha256
          and workload["source"]["sha256"] == protocol.expected_source_sha256
          and workload["storage_in_goal"] == protocol.storage_in_goal
          and workload["storage_out_start"] == protocol.storage_out_start
          and workload["raw_bag_count"] == external.EXPECTED_POPULATIONS[load][0],
          "workload differs from frozen map/source/population/storage protocol")
    output = external.cell_dir(args.result_root, load, seed, map_name) / "feng_env_dh_v5"
    map_path, raw = Path(workload["map_path"]), Path(workload["raw_path"])
    alpha, beta = feng.coefficient_seconds(map_path, alpha_scale=1.0, beta_over_alpha=2.0)
    command = feng.java_run_command(java=args.java, classes_dir=args.classes_dir, map_path=map_path,
        input_path=raw, output_dir=output, alpha_seconds=alpha, beta_seconds=beta,
        max_raw_bags=0, workload_scale=1.0, seed=seed, horizon_seconds=external.FIXED_HORIZON_SECONDS,
        trace_sample_modulo=0, formal_timing_eligible=load != 2.0,
        storage_in_goal=workload["storage_in_goal"], storage_out_start=workload["storage_out_start"])
    command.insert(1, "-Xmx" + args.java_heap)
    identity = {"method": METHOD, "map_sha256": workload["map_sha256"], "input_sha256": workload["raw_sha256"],
        "canonical_sha256": workload["canonical_sha256"], "reconstruction_java_source_aggregate_sha256": SOURCE_SHA,
        "compiled_java_class_aggregate_sha256": CLASS_SHA, "map_physics": feng.read_map_physics(map_path),
        "alpha_scale": 1.0, "beta_over_alpha": 2.0, "alpha_seconds": alpha, "beta_seconds": beta,
        "workload_scale": 1.0, "seed": seed, "max_raw_bags": 0,
        "horizon_seconds": external.FIXED_HORIZON_SECONDS, "trace_sample_modulo": 0,
        "formal_timing_eligible": load != 2.0, "storage_in_goal": workload["storage_in_goal"],
        "storage_out_start": workload["storage_out_start"], "table53_schedule": None,
        "external_workload_identity": {"path": str(identity_path), "sha256": sha(identity_path),
            **{k: workload[k] for k in ("map", "map_sha256", "load_factor", "seed", "raw_bag_count", "segment_count",
                                      "storage_in_goal", "storage_out_start")}},
        "compile_identity_path": str(args.classes_dir / BUILD_IDENTITY),
        "compile_identity_sha256": sha(args.classes_dir / BUILD_IDENTITY),
        "campaign_protocol_path": str(PROTOCOL), "campaign_protocol_sha256": sha(PROTOCOL),
        "preflight_path": str(args.result_root / "preflight/preflight.json"),
        "preflight_sha256": sha(args.result_root / "preflight/preflight.json"),
        "java_heap_limit": args.java_heap, "java_runtime": tool_identity(args.java)}
    return identity_path, output, command, identity


def reuse(args: argparse.Namespace) -> dict:
    records = []
    for map_name, load, seed in cells(args):
        identity_path = external.cell_dir(external.DEFAULT_WORKLOAD_ROOT, load, seed, map_name) / "identity.json"
        external.audit_cell(identity_path)
        for method in CONTROLS:
            source = external.cell_dir(external.DEFAULT_RESULT_ROOT, load, seed, map_name) / (method + ".json")
            value = external.load_normalized_result(source)
            check(value["method"] == method and value["map"] == map_name and float(value["load_factor"]) == load
                  and int(value["seed"]) == seed, "control cell key mismatch")
            check(value["workload_identity_sha256"] == sha(identity_path), "control workload differs")
            target = external.cell_dir(args.result_root, load, seed, map_name) / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            check(not target.exists() or target.read_bytes() == source.read_bytes(), "different control already staged")
            shutil.copyfile(source, target)
            records.append({"map": map_name, "load_factor": load, "seed": seed, "method": method,
                "source": str(source), "target": str(target), "sha256": sha(source),
                "workload_identity_sha256": sha(identity_path), "full_population_complete": value["full_population_complete"],
                "provenance_tier": "ARCHIVED_HCA_RUNTIME_CLASS_IDENTITY_UNRECOVERED" if method == "FENG_NATIVE_HCA"
                    else "FROZEN_G31_B00_BINARY_AND_NATIVE_HASHES",
                "full_trajectory_archive_claim": False})
    value = {"schema": "czr005.feng_v5_control_reuse.v1", "count": len(records),
             "any_old_dh_reused": False, "actual_workload_bytes_reaudited": True, "records": records}
    write(args.result_root / (selection_label(args) + "_reused_controls.json"), value)
    return value


def plan(args: argparse.Namespace) -> dict:
    require_preflight(args)
    hca_plan = external.build_dry_run_plan(workload_root=external.DEFAULT_WORKLOAD_ROOT,
        result_root=args.result_root / "fresh_hca", python=sys.executable, java=args.java, javac=args.javac,
        binary=BINARY)
    hca = {(r["map"], r["load_factor"], r["seed"]): r["commands"]["FENG_NATIVE_HCA"] for r in hca_plan["entries"]}
    entries = []
    for map_name, load, seed in cells(args):
        identity_path, output, command, identity = run_spec(args, map_name, load, seed)
        entries.append({"map": map_name, "load_factor": load, "seed": seed, "identity_path": str(identity_path),
            "native_dir": str(output), "normalized_target": str(output.parent / (METHOD + ".json")),
            "command": command, "runtime_identity": identity, "optional_fresh_hca_command": hca[(map_name, load, seed)]})
    value = {"schema": "czr005.feng_v5_campaign_plan.v1", "execution_started": False, "method": METHOD,
        "new_dh_cell_count": len(entries), "workers": args.workers, "java_heap": args.java_heap,
        "wall_timeout_seconds": args.wall_timeout_seconds, "fixed_horizon_seconds": external.FIXED_HORIZON_SECONDS,
        "entries": entries, "fresh_hca_note": "Commands only; capture contemporary HCA source/class identity if executed.",
        "timing_contract": "Only complete 1x/1.75x populations; 2x and incomplete timing is N/A. Retain all raw/segment states."}
    write(args.result_root / (selection_label(args) + "_command_plan.json"), value)
    return value


def selection_label(args: argparse.Namespace) -> str:
    return "_".join(["-".join(external._selection(args.map, external.MAPS)),
        "-".join(external._load_token(x) for x in external._selection(args.load_factor, external.LOAD_FACTORS)),
        "all_seeds" if not args.seed else "-".join(str(x) for x in external._selection(args.seed, external.SEEDS))])


def run_one(args: argparse.Namespace, key: tuple) -> dict:
    from scripts.eval.export_feng_v5_campaign import normalize_v5_cell, archive_v5_cell
    compiled_identity(args.classes_dir)
    identity_path, output, command, identity = run_spec(args, *key)
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = output.parent / "v5_execution.lock"
    # Prevent two invocations from admitting the same cell concurrently.
    with lock.open("x", encoding="utf-8") as handle:
        handle.write(str(os.getpid()))
    try:
        status = feng.execute_java_run(command=command, output_dir=output, identity=identity,
            force=False, timeout_seconds=args.wall_timeout_seconds)
        normalized = normalize_v5_cell(identity_path, output, output.parent / (METHOD + ".json"))
        archive = archive_v5_cell(output, output.parent / "v5_native_archive")
        return {"map": key[0], "load_factor": key[1], "seed": key[2], "status": "complete",
                "runner_status": status["status"], "full_population_complete": normalized["full_population_complete"],
                "native_dir": str(output), "archive": archive}
    finally:
        lock.unlink()


def run(args: argparse.Namespace) -> dict:
    from scripts.eval.export_feng_v5_campaign import normalize_v5_cell  # fail before launches if API unavailable
    require_preflight(args)
    keys = list(cells(args))
    status_path = args.result_root / (selection_label(args) + "_execution_status.json")
    value = {"schema": "czr005.feng_v5_campaign_execution.v1", "status": "running", "method": METHOD,
        "started_at": datetime.now(timezone.utc).isoformat(), "cell_count": len(keys), "workers": args.workers,
        "java_heap": args.java_heap, "wall_timeout_seconds": args.wall_timeout_seconds,
        "fixed_horizon_seconds": external.FIXED_HORIZON_SECONDS, "host": platform.platform(),
        "logical_cpu_count": os.cpu_count(), "runner_path": str(Path(__file__).resolve()),
        "runner_sha256": sha(Path(__file__)), "results": [], "failures": []}
    write(status_path, value)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_one, args, key): key for key in keys}
        for future in as_completed(futures):
            key = futures[future]
            try:
                result = future.result()
                value["results"].append(result)
                print(json.dumps({k: result[k] for k in ("map", "load_factor", "seed", "status", "full_population_complete")}), flush=True)
            except Exception as exc:
                value["failures"].append({"map": key[0], "load_factor": key[1], "seed": key[2],
                                          "error": type(exc).__name__ + ": " + str(exc)})
                print(json.dumps(value["failures"][-1]), flush=True)
            write(status_path, value)
    value["status"] = "complete" if not value["failures"] else "failed"
    value["finished_at"] = datetime.now(timezone.utc).isoformat()
    write(status_path, value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("preflight", "plan", "reuse", "run"))
    parser.add_argument("--result-root", type=Path, default=RESULT_ROOT)
    parser.add_argument("--classes-dir", type=Path, default=CLASSES)
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default="javac")
    parser.add_argument("--map", action="append", choices=external.MAPS)
    parser.add_argument("--load-factor", type=float, action="append")
    parser.add_argument("--seed", type=int, action="append")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--java-heap", choices=("1536m", "2g"), default="1536m")
    parser.add_argument("--wall-timeout-seconds", type=int, default=0)
    args = parser.parse_args()
    args.result_root, args.classes_dir = args.result_root.resolve(), args.classes_dir.resolve()
    args.java, args.javac = executable(args.java), executable(args.javac)
    check(1 <= args.workers <= 4 and args.wall_timeout_seconds >= 0, "use 1-4 workers and nonnegative timeout")
    forbidden = [external.DEFAULT_RESULT_ROOT, ROOT / "outputs/runtime/cie_external_baseline_zero_through_optimized_v1",
                 ROOT / "outputs/runtime/feng_dh_semantics_reaudit_20260905"]
    check(not any(args.result_root == p.resolve() or p.resolve() in args.result_root.parents for p in forbidden),
          "new V5 campaign must not use an old evidence directory")
    check(args.classes_dir != external.DEFAULT_DH_CLASSES_DIR.resolve() and
          args.classes_dir != (ROOT / "build/feng_dh_semantics_reaudit_20260905/boundary_clearance_v5").resolve(),
          "use independent campaign classes")
    list(cells(args))  # validate selection before any output mutation
    value = {"preflight": preflight, "plan": plan, "reuse": reuse, "run": run}[args.stage](args)
    print(json.dumps({"stage": args.stage, "status": value.get("status", "complete"),
                      "count": value.get("count", value.get("new_dh_cell_count", value.get("total_independent_bags")))}), flush=True)
    return 2 if value.get("status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
