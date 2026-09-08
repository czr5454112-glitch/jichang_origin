"""Select the user-approved 576 coordinates without changing any native cell."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import run_feng_paper_suite_v2 as pool

SOURCE = ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v5/plan.json"
SOURCE_SHA = "00a95b47298fb1aac808bec9275f6d9b3c28d340859017c0667e39ff736b9719"
DEST = SOURCE.parent.parent / "frozen_plan_v6"
SCOPE = ROOT / "configs/eval/feng_paper_suite_reduced_20260907.json"


def main():
    pool.require(pool.sha(SOURCE) == SOURCE_SHA, "frozen V5 plan changed")
    pool.require(not DEST.exists(), "never overwrite a frozen plan")
    original = pool.load_plan(SOURCE)
    scope = pool.read(SCOPE)
    require = pool.require
    require(scope["cell_count"] == 576 and scope["family_counts"] == {"base": 480, "all_day_fault": 96}
            and scope["execution_order"] == ["base", "all_day_fault"], "unregistered scope/order")
    require(scope["all_day_fault"]["scenario_indices"] == [1, 2, 9, 14]
            and scope["all_day_fault"]["seeds"] == [104729, 130363, 155921], "unregistered sampling subset")
    selected = [c for c in original["cells"] if c["family"] == "base" or
                (c["scenario_index"] in scope["all_day_fault"]["scenario_indices"] and
                 c["seed"] in scope["all_day_fault"]["seeds"])]
    require(len(selected) == 576 and sum(c["family"] == "base" for c in selected) == 480, "wrong retained cell counts")
    require([c for c in selected if c["family"] == "base"] ==
            [c for c in original["cells"] if c["family"] == "base"], "base matrix changed")
    selected_ids = {c["cell_id"] for c in selected}
    removed = [c for c in original["cells"] if c["cell_id"] not in selected_ids]
    require(len(removed) == 1184 and all(c["family"] == "all_day_fault" for c in removed), "unexpected removed cells")
    require(not any(Path(c["output_dir"]).exists() for c in removed), "a removed cell already has evidence; review scope accounting")
    updated = copy.deepcopy({k: v for k, v in original.items() if not k.startswith("_")})
    updated.update(cells=selected, cell_count=576, family_counts=scope["family_counts"],
        execution_order=scope["execution_order"], preparer_sha256=pool.sha(Path(__file__)),
        scope_contract={"path": str(SCOPE), "sha256": pool.sha(SCOPE)})
    updated["scope_reduction"] = {"source_plan_path": str(SOURCE), "source_plan_sha256": SOURCE_SHA,
        "user_approved": True, "retained_cell_entries_exactly_equal": True,
        "normal_first": True, "removed_count": len(removed), "removed_cell_ids": [c["cell_id"] for c in removed],
        "generator_path": str(Path(__file__).resolve()), "generator_sha256": pool.sha(Path(__file__))}
    pool.write(DEST / "plan.json", updated)
    checked = pool.load_plan(DEST / "plan.json")
    assert checked["cells"] == selected
    pool.write(DEST / "selection_verification.json", {
        "status": "PASS", "source_plan_sha256": SOURCE_SHA, "plan_sha256": checked["_sha256"],
        "retained_count": 576, "base_unchanged_count": 480, "fault_count": 96, "removed_count": 1184,
        "retained_specs_and_runner_bindings_unchanged": True, "execution_order": scope["execution_order"],
        "selection_inputs": [str(SOURCE), str(SCOPE)], "native_result_metrics_read_for_selection": False,
        "native_simulations_invoked": 0})
    print(json.dumps({"status": "PASS", "plan_sha256": checked["_sha256"], "cell_count": 576, "family_counts": scope["family_counts"]}))


if __name__ == "__main__":
    main()
