"""Derive one isolated next-tick through-server reuse probe and bounded fixtures."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from derive_feng_dh_id_order_probes import aggregate, files_identity

ROOT = Path(__file__).resolve().parents[2]
NAME = "feng_cie_dh_next_tick_service_v4"
METHOD = "FENG_DH_NEXT_TICK_SERVICE_V4"
OUTPUT = ROOT / "outputs/runtime/feng_dh_semantics_reaudit_20260905/next_tick_service_fixtures"


def verify(name: str, next_tick: bool) -> dict:
    classes = ROOT / "build/feng_dh_next_tick_service_probe" / name / "classes"
    audit = classes.parent / "audit"
    classes.mkdir(parents=True, exist_ok=True)
    audit.mkdir(parents=True, exist_ok=True)
    source = ROOT / "benchmarks/java" / name / "App"
    compile_command = [shutil.which("javac") or "javac", "--release", "8", "-Xlint:all",
                       "-encoding", "UTF-8", "-d", str(classes),
                       *map(str, sorted(source.glob("*.java")))]
    subprocess.run(compile_command, check=True, capture_output=True, timeout=60)
    test = ROOT / "tests/java/App/NextTickServiceAudit.java"
    subprocess.run([compile_command[0], "--release", "8", "-Xlint:all", "-encoding", "UTF-8",
                    "-cp", str(classes), "-d", str(audit), str(test)],
                   check=True, capture_output=True, timeout=60)
    directory = OUTPUT / name
    directory.mkdir(parents=True, exist_ok=True)
    command = [shutil.which("java") or "java", "-cp", str(classes) + os.pathsep + str(audit),
               "App.NextTickServiceAudit", "next" if next_tick else "same", str(directory)]
    result = subprocess.run(command, check=True, capture_output=True, timeout=60)
    (directory / "results.jsonl").write_bytes(result.stdout)
    (directory / "stderr.txt").write_bytes(result.stderr)
    checks = [json.loads(row) for row in result.stdout.decode("utf-8").splitlines()]
    if len(checks) != 4 or not all(row["pass"] for row in checks):
        raise RuntimeError("bounded fixture failure")
    return {"name": name, "checks": checks, "compile_command": compile_command, "command": command,
            "class_aggregate_sha256": aggregate(classes, "*.class"),
            "test_source": files_identity(test.parent, test.name),
            "outputs": files_identity(directory, "*")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    parent = ROOT / "benchmarks/java/feng_cie_dh"
    target = ROOT / "benchmarks/java" / NAME
    before = files_identity(parent, "*.java")
    if len(before) != 5:
        raise RuntimeError("expected five parent sources")
    payloads = {}
    for path in sorted((parent / "App").glob("*.java")):
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if path.name == "FengDhSimulator.java":
            old = "boolean available = occupant == null || nodeThroughDepartures.contains(nodeValue);"
            if text.count(old) != 1:
                raise RuntimeError("parent service availability contract differs")
            text = text.replace(old, "boolean available = occupant == null;")
        elif path.name == "FengDhBenchmark.java":
            text, count = re.subn(r'private static final String METHOD = "[A-Z0-9_]+";',
                                 f'private static final String METHOD = "{METHOD}";', text)
            if count != 1:
                raise RuntimeError("expected one METHOD")
            text = text.replace("STATIC_FREE_FLOW_FENG_EXECUTOR", "STATIC_FREE_FLOW_NEXT_TICK_SERVICE_V4")
        payload = text.replace("\n", "\r\n").encode("utf-8")
        if path.name not in ("FengDhSimulator.java", "FengDhBenchmark.java") and payload != raw:
            raise RuntimeError("parent must be canonical CRLF")
        payloads[path.name] = payload
    (target / "App").mkdir(parents=True, exist_ok=True)
    if {p.name for p in (target / "App").glob("*.java")} - set(payloads):
        raise RuntimeError("unexpected target sources")
    for name, payload in payloads.items():
        path = target / "App" / name
        if path.exists() and path.read_bytes() != payload:
            raise RuntimeError("refusing to overwrite differing probe source")
    for name, payload in payloads.items():
        path = target / "App" / name
        if not path.exists():
            path.write_bytes(payload)
    verification = [verify("feng_cie_dh", False), verify(NAME, True)] if args.verify else []
    if files_identity(parent, "*.java") != before:
        raise RuntimeError("parent changed during derivation")
    identity = files_identity(target, "*.java")
    manifest = {"schema": "feng.dh.next_tick_service_derivation.v1", "method": METHOD,
                "parent_files": before, "target_files": identity,
                "parent_source_aggregate_sha256": aggregate(parent, "*.java"),
                "source_aggregate_sha256": aggregate(target, "*.java"),
                "changed_files": [p for p in identity if identity[p] != before[p]],
                "semantic_change": "node-through availability reads current occupant only",
                "verification": verification, "formal_experiments_started": 0}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "derivation_and_fixtures.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("method", "source_aggregate_sha256", "changed_files")}, indent=2))


if __name__ == "__main__":
    main()
