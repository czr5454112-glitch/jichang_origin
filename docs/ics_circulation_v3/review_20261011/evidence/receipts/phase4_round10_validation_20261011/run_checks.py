"""Metered in-process pytest receipt; preserve every invocation independently."""
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
BASE = Path(__file__).resolve().parent
output = BASE / sys.argv[1]
output.mkdir()
cpu, wall = time.process_time(), time.perf_counter()
paths = sorted((ROOT / "scripts/experiments/ics_circulation_v3").glob("*.py"))
paths += [ROOT / "cpp/ics_core/runtime/bounded_local_pibt.hpp", Path(__file__)]
paths += [ROOT / value for value in sys.argv[2:]]


def bindings():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


before = bindings()
(output / "before.json").write_text(json.dumps(before, indent=2))
report = {"tests": sys.argv[2:], "physical_runs": None,
          "physical_count_scope": "pytest internal simulations not instrumented; never interpret as zero"}
try:
    import pytest
    from contextlib import redirect_stderr, redirect_stdout
    with (output / "stdout.txt").open("w", encoding="utf-8") as out, (output / "stderr.txt").open("w", encoding="utf-8") as err:
        with redirect_stdout(out), redirect_stderr(err):
            code = pytest.main(["-q", "--tb=short", *sys.argv[2:]])
    report["exit_code"] = int(code)
except Exception:
    report.update(exit_code=1, exception=traceback.format_exc())
after = bindings()
report.update(cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall,
              source_changed=[p for p in before if before[p] != after[p]],
              resource_scope="parent in-process pytest inclusive; no additive nested pytest CPU; final receipt writes excluded")
(output / "after.json").write_text(json.dumps(after, indent=2))
(output / "results.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
raise SystemExit(0 if report["exit_code"] == 0 and not report["source_changed"] else 1)
