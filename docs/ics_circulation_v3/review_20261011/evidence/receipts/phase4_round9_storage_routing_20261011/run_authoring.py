"""Append-only measured authoring tests; every failed attempt is retained."""
from pathlib import Path
import contextlib
import hashlib
import json
import sys
import time
import traceback

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
index = 1
while (BASE / f"run_{index:03d}").exists():
    index += 1
out = BASE / f"run_{index:03d}"
out.mkdir()
paths = ["scripts/experiments/ics_circulation_v3/storage_routing.py",
         "tests/test_ics_circulation_v3_storage_routing.py",
         "scripts/experiments/ics_circulation_v3/storage_contracts.py",
         "scripts/experiments/ics_circulation_v3/runtime.py",
         "scripts/experiments/ics_circulation_v3/routing.py",
         "scripts/experiments/ics_circulation_v3/routing_reference.py"]

def hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            if (ROOT / name).exists() else None for name in paths}

before = hashes()
(out / "before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
for name in paths:
    if (ROOT / name).exists():
        target = out / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
cpu, wall = time.process_time(), time.perf_counter()
code, error = None, None
try:
    with (out / "stdout.txt").open("w", encoding="utf-8") as stdout, (out / "stderr.txt").open("w", encoding="utf-8") as stderr:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            import pytest
            code = int(pytest.main(["-q", paths[1], "--basetemp", str(out / "pytest_tmp"),
                                   "--junitxml", str(out / "junit.xml")]))
except BaseException:
    error = traceback.format_exc()
elapsed_cpu, elapsed_wall = time.process_time() - cpu, time.perf_counter() - wall
after = hashes()
resource = {"schema": "round9_storage_routing_authoring_v1", "exit_code": code,
            "failure": error, "cpu_seconds": elapsed_cpu, "wall_seconds": elapsed_wall,
            "scope": "in-process pytest import and test execution; excludes Python startup, snapshot capture and evidence writes",
            "physical_business_batches": 0, "source_stable": before == after,
            "after": after, "unmetered_auxiliary": ["source reading", "design/code authoring", "tool orchestration"]}
(out / "resource.json").write_text(json.dumps(resource, indent=2), encoding="utf-8")
print(json.dumps({"output": str(out), **resource}, indent=2))
sys.exit(code if code is not None else 99)
