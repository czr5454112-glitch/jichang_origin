"""Derive two isolated task-id grant-order probes; optionally run bounded fixtures.

Only the two arbitration comparators and scientific METHOD labels may differ
from each parent. This does not implement asynchronous movement or scoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "outputs/runtime/feng_dh_semantics_reaudit_20260905/id_order_fixtures"
BUILD = ROOT / "build/feng_dh_id_order_probes"
PROBES = (
    ("feng_cie_dh", "feng_cie_dh_overlap_id_order", "FENG_DH_OVERLAP_ID_ORDER_V1"),
    ("feng_cie_dh_retained_boundary_v2", "feng_cie_dh_retained_boundary_v2_id_order",
     "FENG_DH_RETAINED_BOUNDARY_ID_ORDER_V2"),
)
FIFO_PREFIX = """                int byArrival = Long.compare(
                        left.bag.getNodeArrivalTick(), right.bag.getNodeArrivalTick());
                if (byArrival != 0) {
                    return byArrival;
                }
                int byRelease = Long.compare(left.bag.releaseTick, right.bag.releaseTick);
                if (byRelease != 0) {
                    return byRelease;
                }
"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def files_identity(directory: Path, pattern: str) -> dict[str, str]:
    return {p.relative_to(directory).as_posix(): sha(p.read_bytes())
            for p in sorted(directory.rglob(pattern)) if p.is_file()}


def aggregate(directory: Path, pattern: str) -> str:
    # Same length-prefixed physical-byte convention as the external identity gate.
    digest = hashlib.sha256()
    for path in sorted(directory.rglob(pattern), key=lambda p: p.relative_to(directory).as_posix()):
        relative = path.relative_to(directory).as_posix().encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def derive(parent: str, target: str, method: str) -> dict:
    source_dir = ROOT / "benchmarks/java" / parent
    target_dir = ROOT / "benchmarks/java" / target
    sources = sorted((source_dir / "App").glob("*.java"))
    if len(sources) != 5:
        raise RuntimeError(f"expected exactly five parent sources: {source_dir}")
    transformed = {}
    for path in sources:
        raw = path.read_bytes()
        text = raw.decode("utf-8").replace("\r\n", "\n")
        if path.name == "FengDhSimulator.java":
            before = text
            for proposal, order in (("EntryProposal", "entryOrder"),
                                    ("NodeServiceProposal", "nodeServiceOrder")):
                start = text.index(f"    private static Comparator<{proposal}> {order}() {{")
                end = text.index("\n    }", start) + len("\n    }")
                block = text[start:end]
                if block.count(FIFO_PREFIX) != 1:
                    raise RuntimeError(f"unexpected parent comparator: {parent}/{order}")
                text = text[:start] + block.replace(FIFO_PREFIX, "", 1) + text[end:]
            if before.count(FIFO_PREFIX) != 2 or text.count(FIFO_PREFIX):
                raise RuntimeError("derivation escaped the two comparator prefix changes")
        elif path.name == "FengDhBenchmark.java":
            text, count = re.subn(r'private static final String METHOD = "[A-Z0-9_]+";',
                                 f'private static final String METHOD = "{method}";', text)
            if count != 1:
                raise RuntimeError("expected one METHOD declaration")
            # Also identify the auxiliary alpha=beta=0 control consistently.
            text = re.sub(r"STATIC_FREE_FLOW_(?:FENG_EXECUTOR|RETAINED_BOUNDARY_V2)",
                          "STATIC_FREE_FLOW_" + method, text)
        payload = text.replace("\n", "\r\n").encode("utf-8")
        if path.name not in ("FengDhSimulator.java", "FengDhBenchmark.java") and payload != raw:
            raise RuntimeError(f"parent is not canonical CRLF: {path}")
        transformed[path.name] = payload
    (target_dir / "App").mkdir(parents=True, exist_ok=True)
    existing = {p.name for p in (target_dir / "App").glob("*.java")}
    if existing - set(transformed):
        raise RuntimeError("unexpected target Java source")
    for name, payload in transformed.items():
        path = target_dir / "App" / name
        if path.exists() and path.read_bytes() != payload:
            raise RuntimeError(f"refusing to overwrite a differing derived source: {path}")
    for name, payload in transformed.items():
        path = target_dir / "App" / name
        if not path.exists():
            path.write_bytes(payload)
    parent_identity = files_identity(source_dir, "*.java")
    target_identity = files_identity(target_dir, "*.java")
    return {"parent": parent, "target": target, "method": method,
            "parent_files": parent_identity, "target_files": target_identity,
            "parent_source_aggregate_sha256": aggregate(source_dir, "*.java"),
            "source_aggregate_sha256": aggregate(target_dir, "*.java"),
            "changed_files": [name for name in target_identity
                              if parent_identity[name] != target_identity[name]],
            "semantic_change": "entryOrder and nodeServiceOrder: taskId, upstreamEdgeId",
            "full_asynchronous_update": False}


def bounded_fixtures(name: str, id_order: bool) -> dict:
    source = ROOT / "benchmarks/java" / name / "App"
    classes, audit_classes = BUILD / name / "classes", BUILD / name / "audit"
    classes.mkdir(parents=True, exist_ok=True)
    audit_classes.mkdir(parents=True, exist_ok=True)
    compile_command = [shutil.which("javac") or "javac", "--release", "8", "-Xlint:all",
                       "-encoding", "UTF-8", "-d", str(classes),
                       *map(str, sorted(source.glob("*.java")))]
    subprocess.run(compile_command, check=True, capture_output=True, timeout=60)
    test = ROOT / "tests/java/App/IdOrderProbeAudit.java"
    subprocess.run([compile_command[0], "--release", "8", "-Xlint:all", "-encoding", "UTF-8",
                    "-cp", str(classes), "-d", str(audit_classes), str(test)],
                   check=True, capture_output=True, timeout=60)
    output = RUNTIME / name
    output.mkdir(parents=True, exist_ok=True)
    import os
    command = [shutil.which("java") or "java", "-cp", str(classes) + os.pathsep + str(audit_classes),
               "App.IdOrderProbeAudit", "id" if id_order else "fifo", str(output)]
    result = subprocess.run(command, check=True, capture_output=True, timeout=60)
    (output / "results.jsonl").write_bytes(result.stdout)
    (output / "stderr.txt").write_bytes(result.stderr)
    checks = [json.loads(line) for line in result.stdout.decode("utf-8").splitlines()]
    if len(checks) != 2 or not all(row["pass"] for row in checks):
        raise RuntimeError(f"fixture failure: {name}")
    return {"name": name, "compile_command": compile_command, "command": command,
            "class_files": files_identity(classes, "*.class"),
            "class_aggregate_sha256": aggregate(classes, "*.class"),
            "test_source_sha256": sha(test.read_bytes()), "checks": checks,
            "outputs": files_identity(output, "*")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true", help="compile four classesets and run only two tiny fixtures each")
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    probes = [derive(*probe) for probe in PROBES]
    verification = []
    if args.verify:
        for parent, target, _ in PROBES:
            verification.extend((bounded_fixtures(parent, False), bounded_fixtures(target, True)))
        for probe in probes:
            parent_path = ROOT / "benchmarks/java" / probe["parent"]
            if files_identity(parent_path, "*.java") != probe["parent_files"]:
                raise RuntimeError("parent changed while fixtures ran")
    manifest = {"schema": "feng.dh.id_order_derivation.v1", "probes": probes,
                "verification": verification, "formal_experiments_started": 0}
    (RUNTIME / "derivation_and_fixtures.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"probes": [{key: item[key] for key in
          ("target", "source_aggregate_sha256", "changed_files")} for item in probes],
          "verified_classesets": len(verification)}, indent=2))


if __name__ == "__main__":
    main()
