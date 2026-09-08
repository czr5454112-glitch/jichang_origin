"""Read-only verification of the four retained DH cells; never launch a runner."""
from contextlib import redirect_stdout
from pathlib import Path
import io
import json
import sys
import time
import traceback
from unittest.mock import patch

ROOT = Path.cwd().resolve()
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_paper_suite_v2 as pool
from scripts.eval import run_feng_paper_suite_campaign_v2 as master

OUT = Path(__file__).resolve().parent
TARGET = OUT / "real_mixed_DH_verification.json"
assert not TARGET.exists(), "Read-only scientific verification is recorded once; keep the prior record."
result = dict(status="RUNNING", native_simulations_invoked=0, real_pools_started=0,
              scope="Four retained DH cells plus read-only master readiness, not all 1760 cells.",
              cells=[], started_at_unix=time.time())
pool.write(TARGET, result)
try:
    with patch.object(pool.subprocess, "Popen", side_effect=AssertionError("native/pool dispatch forbidden")), \
         patch.object(pool, "run_plan", side_effect=AssertionError("real pool forbidden")):
        plan = pool.load_plan(master.PLAN)
        pool.require(plan["_sha256"] == master.PLAN_SHA, "master/plan identity mismatch")
        base, _ = master.stage_cells(plan)
        cells = [c for c in base if c["method"] == pool.DH]
        pool.require(len(cells) == 4, "expected four DH cells in the representative base stage")
        for cell in cells:
            started = time.time()
            path = Path(cell["output_dir"]) / "normalized_result.json"
            before = pool.sha(path)
            verified = pool.verify_cell(cell)
            pool.require(before == pool.sha(path), "read-only verifier changed normalized bytes")
            spec = pool.read(Path(cell["spec_path"]))
            normalized = pool.read(path)
            result["cells"].append(dict(cell_id=cell["cell_id"], runner_path=cell["runner_path"],
                runner_sha256=cell["runner_sha256"], spec_sha256=cell["spec_sha256"], output_dir=cell["output_dir"],
                recovered="native_recovery_from" in spec, native_reexecuted=normalized.get("native_reexecuted"),
                population=normalized["metrics"], verification=verified, wall_seconds=time.time()-started,
                normalized_bytes_unchanged=True))
            pool.write(TARGET, result)
        stream = io.StringIO()
        with redirect_stdout(stream):
            code = master.main(["--check-only"])
        readiness = json.loads(stream.getvalue())
        pool.require(code == 0 and readiness["status"] == "PRECHECK_PASS_NOT_EXECUTED"
                     and readiness["existing_pool_ready"] and readiness["normal_full_2x_ready"],
                     "master is not ready for the separate authorized dispatch")
        pool.write(OUT / "master_precheck.json", readiness)
        result.update(status="PASS", plan_path=str(master.PLAN), plan_sha256=plan["_sha256"],
                      completed_cell_verifications=4, actual_recovery_count=sum(c["recovered"] for c in result["cells"]),
                      master_precheck_sha256=pool.sha(OUT / "master_precheck.json"),
                      source_sha256={str(Path(m.__file__).relative_to(ROOT)):pool.sha(Path(m.__file__)) for m in (pool, master)})
except BaseException as error:
    result.update(status="FAILED", error=repr(error), traceback=traceback.format_exc())
    raise
finally:
    result["finished_at_unix"] = time.time()
    pool.write(TARGET, result)
print(json.dumps({"status": result["status"], "output": str(TARGET), "verified_cells": len(result["cells"])}))
