"""Capture unedited native protocol pytest output, JUnit and source identities."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--select", default=None)
    args = parser.parse_args()
    root = Path(__file__).absolute().parents[3]
    out = Path(args.output).absolute(); out.mkdir(parents=True, exist_ok=False)
    binary = Path(args.binary).absolute()
    tests = ["tests/test_g31_circulation_protocol_serialization.py"]
    paths = sorted({*root.glob("cpp/**/*.hpp"), *root.glob("cpp/**/*.cpp"),
                    *(root / file for file in tests), Path(__file__).absolute()})
    snapshot = lambda: {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    before = snapshot()
    environment = dict(os.environ, PYTHONPATH="src;.", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
                       PYTHONIOENCODING="utf-8", G31_CIRCULATION_BINARY=str(binary))
    command = [sys.executable, "-m", "pytest", *tests, "-q", f"--junitxml={out / 'junit.xml'}"]
    if args.select:
        command += ["-k", args.select]
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=root, env=environment, capture_output=True)
    elapsed = time.perf_counter() - started
    (out / "stdout.txt").write_bytes(proc.stdout); (out / "stderr.txt").write_bytes(proc.stderr)
    counts = None
    if (out / "junit.xml").exists():
        tree = ET.parse(out / "junit.xml").getroot()
        counts = {key: sum(int(s.get(key, 0)) for s in tree.iter("testsuite"))
                  for key in ("tests", "failures", "errors", "skipped")}
    after = snapshot(); changed = [p for p in before if before[p] != after[p]]
    receipt = {"schema": "g31.protocol_serialization_pytest.v1", "status": "passed" if not proc.returncode and not changed else "failed",
               "command": command, "returncode": proc.returncode, "counts": counts, "elapsed_seconds": elapsed,
               "binary": str(binary), "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
               "source_before": before, "source_after": after, "source_changed": changed}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: receipt[k] for k in ("status", "returncode", "counts", "elapsed_seconds", "source_changed")}))
    print(proc.stdout.decode("utf-8", errors="replace"))
    return proc.returncode or bool(changed)


if __name__ == "__main__":
    raise SystemExit(main())
