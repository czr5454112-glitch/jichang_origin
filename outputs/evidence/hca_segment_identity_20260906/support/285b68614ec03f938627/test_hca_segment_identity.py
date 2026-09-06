"""Bounded HCA identity repair microtests; never starts a formal matrix cell."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_g4irsf24_fresh_hca as old
from scripts.eval import run_feng_paper_env_cie_dh as hashing

WRAPPER = ROOT / "benchmarks/java/HcaSegmentIdentityBenchmark.java"
HARNESS = ROOT / "tests/java/HcaSegmentIdentityAudit.java"
OUT = ROOT / "outputs/runtime/hca_segment_identity_20260906/preflight"
CLASSES = ROOT / "build/hca_segment_identity_preflight"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def rows(path: Path) -> list:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def fixture_map(path: Path) -> None:
    # Two independent physical lanes: inbound takes 20s, outbound 2s.
    # Outbound scheduled at t=1 overlaps inbound without adding EBS precedence.
    content = ["4 1.0 0 4", "0 1 0 0 0 1", "1 2 0 0 50", "2 1 0 10 0 3", "3 2 0 10 5",
               "0 50 1000 1000", "1000 0 1000 1000", "1000 1000 0 5", "1000 1000 1000 0",
               "0 1 50 2.5", "2 3 5 2.5"]
    path.write_text("\n".join(content) + "\n", encoding="utf-8", newline="\n")


def compile_classes(java: str, javac: str, classes: Path, *, repaired: bool) -> dict:
    classes.mkdir(parents=True, exist_ok=True)
    sources = old._java_sources()[:-1] + [WRAPPER if repaired else old.JAVA_BENCHMARK]
    command = [javac, "-encoding", "UTF-8", "-d", str(classes), *map(str, sources)]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return {"command": command, "stderr": run.stderr,
        "source_files": {p.relative_to(ROOT).as_posix(): sha(p) for p in sources},
        "source_aggregate_sha256": hashing._aggregate_sha256(sources, ROOT),
        "class_files": {p.relative_to(classes).as_posix(): sha(p) for p in sorted(classes.rglob("*.class"))},
        "class_aggregate_sha256": hashing._aggregate_sha256(classes.rglob("*.class"), classes),
        "java_version": subprocess.run([java, "-version"], capture_output=True, text=True).stderr,
        "javac_version": subprocess.run([javac, "-version"], capture_output=True, text=True).stdout}


def run_case(base: Path, name: str, lines: list[str], *, java: str, classes: Path,
             repaired: bool = True, epochs: int = 35, threshold: float = 5,
             expected_error: str | None = None) -> dict:
    directory = base / "microtest_native" / name
    directory.mkdir(parents=True, exist_ok=True)
    require(not (directory / "run_status.json").exists(), "microtest output already exists; choose a new --output-root")
    map_path, input_path = directory / "map.txt", directory / "input.txt"
    fixture_map(map_path)
    input_path.write_text("ID Entry STD Start Goal\n" + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    command = old.java_run_command(java=java, classes_dir=classes, map_path=map_path, input_path=input_path,
        start_epoch=0, max_epochs=epochs, max_new_tasks=0, run_dir=directory,
        speed_mps=2.5, storage_in_goal=1, storage_out_start=2, early_threshold_seconds=threshold, storage_lead_seconds=5)
    command.insert(1, "-Xmx512m")
    if repaired:
        command[command.index("LegacyIcsNoFaultWindowBenchmark")] = "HcaSegmentIdentityBenchmark"
    started = time.perf_counter()
    run = subprocess.run(command, cwd=directory, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    (directory / "stdout.txt").write_text(run.stdout, encoding="utf-8")
    (directory / "stderr.txt").write_text(run.stderr, encoding="utf-8")
    expected = run.returncode == 0 if expected_error is None else run.returncode != 0 and expected_error in run.stderr
    write(directory / "run_status.json", {"command": command, "returncode": run.returncode,
        "expected_error": expected_error, "test_pass": expected, "wall_seconds": time.perf_counter() - started})
    require(expected, name + " failed: " + run.stderr)
    result = {"name": name, "path": str(directory), "expected_rejection": expected_error,
              "summary": None if expected_error else rows(directory / "summary.csv")[0]}
    if not expected_error and repaired:
        mapping, terminal = rows(directory / "segment_execution_identity.csv"), rows(directory / "execution_terminal.csv")
        require(len(mapping) == len(terminal), "full execution mapping/terminal coverage mismatch")
        require(len({r["execution_id"] for r in mapping}) == len(mapping), "mapping duplicate ID")
        require(int(result["summary"]["terminal_accounting_residual"]) == 0, "nonzero terminal accounting residual")
        require(int(result["summary"]["generated_count"]) + int(result["summary"]["not_released_count"]) == len(mapping), "input accounting mismatch")
        for row in terminal:
            members = [row[k] == "true" for k in ("active_route_member", "unplanned_member", "source_pending_member")]
            require(sum(members) + (row["completion_epoch"] != "") == 1, "terminal members not exclusive/exhaustive")
        result.update(mapping=mapping, terminal=terminal)
    return result


def archive_case(base: Path, result: dict) -> dict:
    directory = Path(result["path"])
    task_dir = directory / "task"
    if task_dir.exists():
        # Preserve every generated epoch before deleting only this fixture's task directory.
        epochs = {p.relative_to(task_dir).as_posix(): p.read_text(encoding="utf-8") for p in sorted(task_dir.rglob("*")) if p.is_file()}
        packed = directory / "epoch_files.json.gz"
        packed.write_bytes(gzip.compress(json.dumps(epochs, sort_keys=True).encode(), mtime=0))
        restored = json.loads(gzip.decompress(packed.read_bytes()))
        require(restored == epochs, "epoch archive restoration failed")
        resolved = task_dir.resolve()
        require(resolved.parent == directory.resolve() and resolved.name == "task"
                and resolved.is_relative_to((base / "microtest_native").resolve()), "unsafe fixture cleanup path")
        shutil.rmtree(resolved)
    return {"name": result["name"], "expected_rejection": result["expected_rejection"],
            "files": {p.relative_to(base).as_posix(): sha(p) for p in sorted(directory.iterdir()) if p.is_file()}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUT)
    parser.add_argument("--classes-dir", type=Path, default=CLASSES)
    parser.add_argument("--java", default="java")
    parser.add_argument("--javac", default="javac")
    args = parser.parse_args()
    java, javac = shutil.which(args.java) or args.java, shutil.which(args.javac) or args.javac
    base, classes = args.output_root.resolve(), args.classes_dir.resolve()
    require(not (base / "microtests.json").exists(), "immutable preflight exists; choose a new --output-root")
    base.mkdir(parents=True, exist_ok=True)
    production = compile_classes(java, javac, classes, repaired=True)
    old_classes = classes.parent / (classes.name + "_old_control")
    old_identity = compile_classes(java, javac, old_classes, repaired=False)
    cases, checks = [], []
    overlap_old = run_case(base, "overlap_old", ["7 0 6 0 3"], java=java, classes=old_classes, repaired=False)
    overlap_new = run_case(base, "overlap_repaired", ["7 0 6 0 3"], java=java, classes=classes)
    cases += [overlap_old, overlap_new]
    old_summary = overlap_old["summary"]
    require(int(old_summary["generated_count"]) == 2 and int(old_summary["completed_count"]) == 1
            and int(old_summary["active_route_count"]) == int(old_summary["unfinished_count"]) == 0, "fixture did not reproduce old overwrite deficit")
    terminal = {r["leg"]: r for r in overlap_new["terminal"]}
    require(all(r["terminal_state"] == "COMPLETED" for r in terminal.values()), "both independent segments must complete")
    require(float(terminal["storage_out"]["release_epoch"]) < float(terminal["storage_in"]["completion_epoch"]), "EBS release was serialized")
    require(float(terminal["storage_out"]["completion_epoch"]) < float(terminal["storage_in"]["completion_epoch"]), "EBS completion was serialized")
    checks.append({"name": "overlapping_EBS_no_overwrite_no_new_precedence", "pass": True,
        "old_generated_completed_active_unplanned": [2, 1, 0, 0], "new_completed": 2, "new_terminal": terminal})

    direct_lines = ["7 0.25 100 0 1", "23 1.75 100 0 1", "123 2.25 100 2 3"]
    direct_old = run_case(base, "direct_old", direct_lines, java=java, classes=old_classes, repaired=False, threshold=1000)
    direct_new = run_case(base, "direct_repaired", direct_lines, java=java, classes=classes, threshold=1000)
    cases += [direct_old, direct_new]
    identical = {}
    for name in ("release.csv", "routes.csv", "output.txt", "outputstarttime.txt"):
        before, after = Path(direct_old["path"]) / name, Path(direct_new["path"]) / name
        require(before.read_bytes() == after.read_bytes(), "direct control changed: " + name)
        identical[name] = sha(before)
    for name, value in direct_old["summary"].items():
        require(direct_new["summary"][name] == value, "direct control summary differs: " + name)
    checks.append({"name": "ordinary_direct_control_exact_equivalence_including_fractional_release", "pass": True, "identical_files": identical})

    sparse = run_case(base, "sparse_ids", ["7 0 6 0 3", "123 10 12 2 3", "23 1 7 0 3"], java=java, classes=classes)
    cases.append(sparse)
    require({int(r["execution_id"]) for r in sparse["mapping"]} == {7, 23, 123, 124, 125}, "ID allocation differs from frozen maxRaw+ordinal rule")
    checks.append({"name": "sparse_raw_IDs_first_leg_preserved_second_leg_collision_free", "pass": True, "execution_ids": [7, 23, 123, 124, 125]})
    harness_classes = classes.parent / (classes.name + "_audit")
    harness_classes.mkdir(parents=True, exist_ok=True)
    subprocess.run([javac, "-encoding", "UTF-8", "-cp", str(classes), "-d", str(harness_classes), str(HARNESS)], check=True)
    object_run = subprocess.run([java, "-cp", os.pathsep.join(map(str, [classes, harness_classes])),
        "HcaSegmentIdentityAudit", str(Path(sparse["path"]) / "input.txt")], capture_output=True, text=True, check=True)
    objects = json.loads(object_run.stdout)
    require(objects["execution_ids"] == [7, 23, 123, 124, 125], "live Task/Pallet objects do not match execution IDs")
    checks.append({"name": "actual_Task_and_Pallet_objects_receive_unique_execution_ID", "pass": True, "audit": objects})

    active = run_case(base, "active_and_not_released", ["7 0 100 0 3"], java=java, classes=classes, epochs=5)
    pending = run_case(base, "unplanned_unreachable", ["7 0 100 0 3"], java=java, classes=classes, epochs=5, threshold=1000)
    cases += [active, pending]
    require({r["terminal_state"] for r in active["terminal"]} == {"ACTIVE_ROUTE", "NOT_RELEASED"}, "active/pending footprint lost")
    require(pending["terminal"][0]["terminal_state"] == "UNPLANNED", "unplanned task lost")
    checks.append({"name": "incomplete_terminal_states_cover_source_pending_active_unplanned", "pass": True})
    duplicate = run_case(base, "reject_duplicate_raw", ["7 0 100 0 1", "7 1 100 0 1"], java=java, classes=classes,
                         expected_error="duplicate raw task identity")
    overflow = run_case(base, "reject_execution_ID_overflow", ["2147483647 0 6 0 3"], java=java, classes=classes,
                        expected_error="insufficient integer execution IDs")
    cases += [duplicate, overflow]
    checks.append({"name": "ambiguous_raw_ID_and_integer_overflow_fail_before_execution", "pass": True})
    archives = [archive_case(base, case) for case in cases]
    require(production["class_files"] == {p.relative_to(classes).as_posix(): sha(p) for p in sorted(classes.rglob("*.class"))}, "production class identity changed during tests")
    require(production["source_files"] == {p: sha(ROOT / p) for p in production["source_files"]}, "source identity changed during tests")
    result = {"schema": "czr005.hca_segment_identity_microtests.v1", "status": "PASS", "method": "HCA_SEGMENT_IDENTITY_V1",
        "checks": checks, "check_count": len(checks), "production_identity": production, "old_control_identity": old_identity,
        "source_aggregate_sha256": production["source_aggregate_sha256"], "class_aggregate_sha256": production["class_aggregate_sha256"],
        "wrapper_sha256": sha(WRAPPER), "java_audit_source_sha256": sha(HARNESS), "test_driver_sha256": sha(Path(__file__)),
        "native_evidence": archives, "formal_population_simulations_executed": 0,
        "scope": "Bounded fixtures prove these contracts; no claim that added IDs preserve EBS HashMap traversal or counterfactual trajectories."}
    write(base / "microtests.json", result)
    print(json.dumps({"status": "PASS", "checks": len(checks), "wrapper_sha256": sha(WRAPPER),
                      "source_sha256": production["source_aggregate_sha256"], "class_sha256": production["class_aggregate_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
