"""Read-only source closure against Round9 and the final Round10 test snapshot."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import process_time, perf_counter

ROOT = Path(__file__).resolve().parents[4]
BASE = Path(__file__).resolve().parent
out = BASE / sys.argv[1]
out.mkdir()
cpu, wall = process_time(), perf_counter()
old = BASE.parent / "phase4_round9_independent_review_20261011/attempt_018/source_snapshot"
final = BASE.parent / "phase4_round10_independent_review_20261011/attempt_006/source_snapshot"


def tree(folder):
    return {path.relative_to(folder).as_posix(): sha256(path.read_bytes()).hexdigest()
            for path in folder.rglob("*") if path.is_file() and path.suffix in (".py", ".hpp")}


prior, frozen = tree(old), tree(final)
live = {path: sha256((ROOT / path).read_bytes()).hexdigest() for path in frozen}
changed_old = [path for path in prior if path in frozen and prior[path] != frozen[path]]
deleted_old = sorted(set(prior) - set(frozen))
new = sorted(set(frozen) - set(prior))
mismatch = [path for path in frozen if frozen[path] != live[path]]
cpp = "cpp/ics_core/runtime/bounded_local_pibt.hpp"
expected_changed = {"scripts/experiments/ics_circulation_v3/storage_routing.py",
                    "tests/test_ics_circulation_v3_storage_routing.py"}
status = "passed" if (not mismatch and not deleted_old and set(changed_old) == expected_changed
                       and prior[cpp] == frozen[cpp] == "b94390501502b61fac64c302fd79ce5a5af1851e13c02932fbddf463284d8951") else "failed"
result = {"status": status, "round9_files": len(prior), "round10_files": len(frozen),
          "changed_old_files": changed_old, "deleted_old_files": deleted_old,
          "added_files": new, "live_mismatches": mismatch, "frozen_source_sha256": frozen,
          "cpu_seconds": process_time()-cpu, "wall_seconds": perf_counter()-wall,
          "physical_runs": 0, "scope": "read-only .py/.hpp source tree hash comparison; generated .pyc is not source; final writes excluded",
          "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest()}
(out / "script.py").write_bytes(Path(__file__).read_bytes())
(out / "results.json").write_text(json.dumps(result, indent=2))
print(json.dumps({k: v for k, v in result.items() if k != "frozen_source_sha256"}, indent=2))
raise SystemExit(0 if status == "passed" else 1)
