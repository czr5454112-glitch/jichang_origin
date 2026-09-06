"""Supplemental reflection audit against frozen HCA production classes.

This tests execution-ID isolation in shared-node reservation storage, not full
path feasibility or continuous-time collision freedom. It never runs a matrix.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_hca_segment_identity as runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--classes-dir", type=Path, default=ROOT / "build/hca_segment_identity_v1")
    parser.add_argument("--audit-classes", type=Path, default=ROOT / "build/hca_segment_identity_reservation_audit")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/runtime/hca_segment_identity_20260906/preflight/reservation_audit.json")
    parser.add_argument("--java", default="C:/PROGRAMING/jdk-18/bin/java.exe")
    parser.add_argument("--javac", default="C:/PROGRAMING/jdk-18/bin/javac.exe")
    args = parser.parse_args()
    source = ROOT / "tests/java/HcaSegmentReservationAudit.java"
    fixture = ROOT / "outputs/runtime/hca_segment_identity_20260906/preflight/microtest_native/overlap_repaired/input.txt"
    build = runner.verify_build(args.classes_dir, args.java, args.javac)
    runner.require(not args.output.exists(), "supplementary audit is immutable; use a new output")
    runner.require(not args.audit_classes.exists() or not any(args.audit_classes.iterdir()), "use a new separate audit class directory")
    runner.require(args.audit_classes.resolve() != args.classes_dir.resolve(), "audit classes must be separate from production")
    args.audit_classes.mkdir(parents=True, exist_ok=True)
    compile_command = [args.javac, "-encoding", "UTF-8", "-cp", str(args.classes_dir.resolve()), "-d",
                       str(args.audit_classes.resolve()), str(source)]
    subprocess.run(compile_command, cwd=ROOT, check=True, capture_output=True, text=True)
    command = [args.java, "-Djava.awt.headless=true", "-cp", os.pathsep.join(map(str, [args.classes_dir.resolve(), args.audit_classes.resolve()])),
               "HcaSegmentReservationAudit", str(fixture)]
    process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=True)
    observed = json.loads(process.stdout)
    runner.require(observed["status"] == "PASS", "reservation audit failed")
    runner.verify_build(args.classes_dir, args.java, args.javac)
    value = {"schema": "czr005.hca_segment_reservation_audit.v1", "status": "PASS", "method": runner.METHOD,
        "production_build_identity_sha256": runner.sha(args.classes_dir / runner.BUILD_NAME),
        "production_source_sha256": build["source_sha256"], "production_class_sha256": build["class_sha256"],
        "audit_source": {"path": source.relative_to(ROOT).as_posix(), "sha256": runner.sha(source)},
        "audit_generator_sha256": runner.sha(Path(__file__)),
        "audit_classes": runner.file_set(list(args.audit_classes.rglob("*.class")), args.audit_classes),
        "fixture": {"path": fixture.relative_to(ROOT).as_posix(), "sha256": runner.sha(fixture)},
        "compile_command": compile_command, "command": command, "observed": observed,
        "scope": "Actual frozen update_constrain/Contains methods: two execution IDs at two shared nodes coexist; updating one preserves the other object and interval; same-ID control overwrites.",
        "limitations": "Synthetic overlapping intervals test storage isolation only. No route feasibility or physical collision-free guarantee follows. Supplemental evidence does not replace or alter the original six-case microtest gate."}
    runner.write_json(args.output, value)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == "__main__":
    main()
