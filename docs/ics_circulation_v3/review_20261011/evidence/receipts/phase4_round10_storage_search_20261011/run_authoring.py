"""Append-only Round10 authoring run: source snapshots, failures and CPU."""
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
while (BASE / f"authoring_{index:03d}").exists():
    index += 1
out = BASE / f"authoring_{index:03d}"
out.mkdir()
tests = sys.argv[1:] or ["tests/test_ics_circulation_v3_storage_routing.py"]
paths = sorted((ROOT / "scripts/experiments/ics_circulation_v3").glob("*.py"))
paths += [ROOT / name for name in tests]
def hashes():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
before = hashes()
for p in paths:
    target = out / "source_snapshot" / p.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(p.read_bytes())
(out / "before.json").write_text(json.dumps(before, indent=2))
cpu, wall = time.process_time(), time.perf_counter()
code, error = None, None
try:
    with (out / "stdout.txt").open("w") as stdout, (out / "stderr.txt").open("w") as stderr:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            import pytest
            code = int(pytest.main(["-q", *tests, "--basetemp", str(out / "pytest_tmp"), "--junitxml", str(out / "junit.xml")]))
except BaseException:
    error = traceback.format_exc()
elapsed_cpu, elapsed_wall = time.process_time()-cpu, time.perf_counter()-wall
after = hashes()
result = dict(status="passed" if code==0 and before==after else "failed", exit_code=code, failure=error,
    cpu_seconds=elapsed_cpu, wall_seconds=elapsed_wall, source_stable=before==after, after=after,
    tests=tests, physical_business_batches=0,
    scope="in-process pytest import/execution; excludes source capture and report writes; fixture physics, if any, remain test calls")
(out / "result.json").write_text(json.dumps(result, indent=2))
print(json.dumps({"output":str(out), **{k:v for k,v in result.items() if k!='after'}},indent=2))
sys.exit(0 if result['status']=='passed' else 1)
