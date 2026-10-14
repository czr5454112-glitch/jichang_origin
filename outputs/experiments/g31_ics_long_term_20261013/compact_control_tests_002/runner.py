from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

folder = Path(__file__).resolve().parent
root = Path.cwd()
tests = ["tests/test_g31_circulation_compact_control.py", "tests/test_g31_circulation_control_projection.py",
         "tests/test_g31_circulation_analytic_reference.py"]
paths = tests+["scripts/experiments/g31_ics_circulation/analytic_control.py",
               "cpp/ics_core/bindings/circulation_session_binding.hpp", str(Path(__file__))]
digest = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
before = {p: digest(p) for p in paths}
binary = "build_lt_session_007/python/czr005_circulation.cp311-win_amd64.pyd"
env = dict(os.environ, PYTHONPATH="src;.", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTHONIOENCODING="utf-8",
           G31_CIRCULATION_BINARY=binary)
command = [sys.executable, "-m", "pytest", *tests, "-q", "--junitxml="+str(folder/"junit.xml")]
started = time.perf_counter()
result = subprocess.run(command, capture_output=True, text=True, env=env, encoding="utf-8")
(folder/"stdout.txt").write_text(result.stdout, encoding="utf-8")
(folder/"stderr.txt").write_text(result.stderr, encoding="utf-8")
counts = {k: 0 for k in ("tests", "failures", "errors", "skipped")}
if (folder/"junit.xml").exists():
    for suite in ET.parse(folder/"junit.xml").getroot().iter("testsuite"):
        for key in counts:
            counts[key] += int(suite.attrib.get(key, 0))
receipt = {"schema": "g31.compact_pytest_validation.v1", "status": "passed" if result.returncode == 0 else "failed",
           "command": command, "returncode": result.returncode, "counts": counts, "source_before": before,
           "source_changed": [p for p in paths if digest(p) != before[p]], "binary_sha256": digest(binary),
           "wall_seconds": time.perf_counter()-started,
           "scope": "compact/full controller action and physical continuation equivalence; no universal runtime or novelty claim"}
(folder/"receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
print(json.dumps(receipt, indent=2))
raise SystemExit(result.returncode or bool(receipt["source_changed"]))
