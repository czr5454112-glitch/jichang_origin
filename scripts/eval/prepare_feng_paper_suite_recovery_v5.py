"""Freeze the existing 1760 coordinates with DH parser V2; never generate workloads."""
from __future__ import annotations
import copy
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_paper_suite_v2 as pool
from scripts.eval import recover_feng_dh_paper_suite_v2 as recovery

V4 = ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v4/plan.json"
V4_SHA = "ad400a4363958087625903833fa4730e10c3787864e74180b3f5fa4cfcde4e71"
DEST = V4.parent.parent / "frozen_plan_v5"
FAILED_ID = "b_nanning_2x_v2p5_s104729_q00_dh"


def main():
    pool.require(pool.sha(V4) == V4_SHA, "frozen V4 plan changed")
    pool.require(not DEST.exists(), "V5 plan must be new; never overwrite frozen plan")
    original = pool.load_plan(V4)
    updated = copy.deepcopy({k: v for k, v in original.items() if not k.startswith("_")})
    accepted, changes = [], []
    new_runner = ROOT / "scripts/eval/run_feng_dh_paper_suite_v2.py"
    for cell in updated["cells"]:
        output = Path(cell["output_dir"])
        if (output / "normalized_result.json").exists():
            pool.check_result_envelope(cell)
            accepted.append(cell["cell_id"])
            continue
        if cell["cell_id"] == FAILED_ID:
            source = copy.deepcopy(cell)
            spec = pool.read(Path(cell["spec_path"]))
            spec["cell_id"] += "_postprocess_v2"
            spec["native_recovery_from"] = {
                "output_dir": cell["output_dir"], "spec_path": cell["spec_path"], "spec_sha256": cell["spec_sha256"],
                "runner_path": cell["runner_path"], "runner_sha256": cell["runner_sha256"],
                "files_sha256": {name: pool.sha(output / name) for name in recovery.FILES}}
            new_output = output.parent / spec["cell_id"]
            recovery.validate_source(spec, new_output)
            spec_path = DEST / "specs" / (spec["cell_id"] + ".json")
            pool.write(spec_path, spec)
            cell.update(cell_id=spec["cell_id"], output_dir=str(new_output), spec_path=str(spec_path), spec_sha256=pool.sha(spec_path))
        else:
            pool.require(not output.exists(), "unexpected existing partial attempt: " + cell["cell_id"])
        if cell["method"] == pool.DH:
            old_runner_sha = cell["runner_sha256"]
            cell.update(runner_path=str(new_runner), runner_sha256=pool.sha(new_runner))
            changes.append({"cell_id": cell["cell_id"], "old_runner_sha256": old_runner_sha,
                            "new_runner_sha256": cell["runner_sha256"]})
    pool.require(len(accepted) == 15 and len(changes) == 117, "unexpected accepted or remaining DH count")
    coordinate = lambda c: tuple(c[k] for k in ("family", "method", "map", "load_factor", "speed_mps", "seed", "scenario_index"))
    pool.require(len(updated["cells"]) == 1760 and
                 {coordinate(c) for c in original["cells"]} == {coordinate(c) for c in updated["cells"]}, "experimental scope changed")
    updated["parser_recovery"] = {"original_plan_path": str(V4), "original_plan_sha256": V4_SHA,
        "reason": "Accept native N/A missing clocks for censored DH population; no algorithm or physical parameter change.",
        "accepted_cells_preserved": accepted, "parser_rebound_cells": changes,
        "original_failed_cell": source, "recovered_cell_id": FAILED_ID + "_postprocess_v2",
        "native_reexecuted": False, "generator_path": str(Path(__file__).resolve()), "generator_sha256": pool.sha(Path(__file__)),
        "recovery_tool_path": str(Path(recovery.__file__).resolve()), "recovery_tool_sha256": pool.sha(Path(recovery.__file__))}
    pool.write(DEST / "plan.json", updated)
    checked = pool.load_plan(DEST / "plan.json")
    print({"status": "PASS", "plan_sha256": checked["_sha256"], "cell_count": len(checked["cells"]),
           "accepted_unchanged": len(accepted), "dh_parser_rebound": len(changes)})


if __name__ == "__main__":
    main()
