"""Bounded independent V4/V5 identity audit; no simulation or normalization.

Reads frozen specs, existing normalized/status envelopes, and hashes the nine
retained native files against recovery bindings. Writes only a new audit JSON.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.eval import report_feng_paper_suite as reporter

V4 = ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v4/plan.json"
V5 = ROOT / "outputs/evidence/paper_suite_20260907/frozen_plan_v5/plan.json"
V4_SHA = "ad400a4363958087625903833fa4730e10c3787864e74180b3f5fa4cfcde4e71"
V5_SHA = "00a95b47298fb1aac808bec9275f6d9b3c28d340859017c0667e39ff736b9719"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def bound(path):
    p = Path(path)
    return {"path": str(p.resolve()), "sha256": sha(p), "bytes": p.stat().st_size}


def need(test, message):
    if not test:
        raise AssertionError(message)


def coordinate(cell):
    return tuple(cell[k] for k in (*reporter.COORD, "method"))


def run(output):
    need(not output.exists(), "refusing to overwrite audit evidence")
    reader = reporter.Reader()
    old = reader.read(V4, V4_SHA)
    reader.read(V5, V5_SHA)
    new, cells, specs, seeds = reporter.load_plan(V5, reader)
    previous = {coordinate(c): c for c in old["cells"]}
    current = {coordinate(c): c for c in cells}
    need(len(previous) == len(current) == 1760 and previous.keys() == current.keys(), "coordinates differ")
    need(old["protocols"] == new["protocols"] and old["workload_bindings"] == new["workload_bindings"], "common protocol/workload bindings differ")
    changed, rebound, restored = [], [], []
    for key, cell in current.items():
        prior = previous[key]
        old_spec = reader.read(prior["spec_path"], prior["spec_sha256"])
        spec = specs[cell["cell_id"]]
        fields = sorted(k for k in prior.keys() | cell.keys() if prior.get(k) != cell.get(k))
        if not fields:
            need(prior == cell, "unrecorded cell change")
            continue
        diff = sorted(k for k in old_spec.keys() | spec.keys() if old_spec.get(k) != spec.get(k))
        item = {"old_cell_id": prior["cell_id"], "cell_id": cell["cell_id"],
                "changed_plan_fields": fields, "changed_spec_fields": diff,
                "old_spec_sha256": prior["spec_sha256"], "new_spec_sha256": cell["spec_sha256"]}
        need(cell["method"] == reporter.DH, "non-DH changed")
        if fields == ["runner_path", "runner_sha256"]:
            need(not diff and prior["spec_sha256"] == cell["spec_sha256"], "future DH spec changed")
            rebound.append(item)
        else:
            need(fields == ["cell_id", "output_dir", "runner_path", "runner_sha256", "spec_path", "spec_sha256"], "unexpected recovery cell change")
            need(diff == ["cell_id", "native_recovery_from"], "recovery changed scientific parameters")
            restored.append((prior, cell, spec))
        changed.append(item)
    need(len(rebound) == 116 and len(restored) == 1 and len(changed) == 117, "wrong change partition")
    preserved = new["parser_recovery"]["accepted_cells_preserved"]
    need(len(preserved) == len(set(preserved)) == 15, "wrong preserved set")
    root = Path(new["result_root"])
    campaign = root.parent if root.name == "cells" else root
    receipts = {}
    for folder in sorted((campaign / "orchestration").iterdir()):
        top = folder / "status.json"
        if not top.exists() or reader.read(top).get("plan_sha256") != V4_SHA:
            continue
        for name in preserved:
            path = folder / "cells" / name / "status.json"
            if path.exists():
                receipt = reader.read(path)
                if receipt.get("status") in ("COMPLETE", "REUSED_VERIFIED"):
                    receipts[name] = (path, receipt)
    kept = []
    for name in preserved:
        cell = next(c for c in cells if c["cell_id"] == name)
        need(previous[coordinate(cell)] == cell, f"preserved plan cell changed: {name}")
        path, receipt = receipts[name]
        for k in ("cell_id", "method", "output_dir", "spec_sha256", "runner_sha256"):
            need(receipt[k] == cell[k], f"old receipt identity differs: {name}/{k}")
        result_path = Path(cell["output_dir"]) / "normalized_result.json"
        reader.read(result_path, receipt["normalized_result_sha256"])
        row = reporter.observe_cell(cell, specs[name], reader)
        need(row["cell_state"] == "COMPLETE", f"old cell not accepted: {name}: {row['error']}")
        kept.append({"cell_id": name, "plan_cell_unchanged": True,
                     "spec_bytes_match_v4_binding": True,
                     "normalized_bytes_match_pre_v5_receipt": True,
                     "normalized_sha256": row["normalized_sha256"], "old_receipt": bound(path)})
    prior, cell, spec = restored[0]
    source = spec["native_recovery_from"]
    need(source["spec_sha256"] == prior["spec_sha256"] and source["runner_sha256"] == prior["runner_sha256"], "recovery source identity differs")
    src, dst = Path(source["output_dir"]), Path(cell["output_dir"])
    native_files = []
    for name, expected in sorted(source["files_sha256"].items()):
        old_path, copied_path = src / name, dst / ("source_runner_status.json" if name == "runner_status.json" else name)
        need(sha(old_path) == sha(copied_path) == expected, f"original/recovered bytes changed: {name}")
        native_files.append({"name": name, "source_path": str(old_path), "copied_path": str(copied_path),
                             "sha256": expected, "bytes": old_path.stat().st_size})
    status = reader.read(dst / "runner_status.json")
    note = reader.read(dst / "native_recovery.json")
    original_status = reader.read(src / "runner_status.json")
    need(status["native_reexecuted"] is False and note["native_reexecuted"] is False, "recovery claims a rerun")
    need(status["command"] == original_status["command"] == note["original_native_command"], "native command changed")
    need(status["native_runner_sha256"] == source["runner_sha256"], "native runner attribution changed")
    row = reporter.observe_cell(cell, spec, reader)
    records = reporter.orchestration_records(new, cells, reader)
    row = reporter.apply_orchestration(row, records.get(cell["cell_id"]))
    need(row["cell_state"] == "COMPLETE" and row["terminal_result_accepted"], f"reporter rejects recovery: {row['error']}")
    need(row["raw_bag_count"] == 57012 and row["TH"] == 49638 and row["completed_segment_count"] == 79460,
         "observed recovery counts differ")
    need(row["full_population_complete"] is False and all(row[k] is None for k in reporter.TIMINGS), "censored timing was invented")
    ast_trees = []
    recovery_guard = ast.dump(ast.parse('require(not spec.get("native_recovery_from"), "recovery-only spec must use retained native evidence, never rerun Java")').body[0], include_attributes=False)
    guards_removed = 0
    for index, path in enumerate((Path(prior["runner_path"]), Path(cell["runner_path"]))):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == "finite_or_none")
                     and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str))]
        if index == 1:
            function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "run_spec")
            matched = [n for n in function.body if ast.dump(n, include_attributes=False) == recovery_guard]
            guards_removed = len(matched)
            function.body = [n for n in function.body if ast.dump(n, include_attributes=False) != recovery_guard]
        ast_trees.append(ast.dump(tree, include_attributes=False))
    need(guards_removed == 1 and ast_trees[0] == ast_trees[1], "other executable parser source changed")
    need(sha(cell["runner_path"]) == cell["runner_sha256"] and sha(prior["runner_path"]) == prior["runner_sha256"], "runner source drift")
    result = {"schema": "czr005.dh_na_parser_recovery.independent_v5_review.v1", "status": "PASS",
              "observed_at_utc": datetime.now(timezone.utc).isoformat(), "audit_source": bound(__file__),
              "old_plan": bound(V4), "new_plan": bound(V5), "reporter": bound(reporter.__file__),
              "coordinates_identical_count": 1760, "base_cells": 480, "fault_cells": 1280,
              "common_seed_count": len(seeds), "protocols_and_workload_bindings_unchanged": True,
              "old_accepted_cell_count": 15, "old_accepted_cells": kept,
              "future_dh_runner_only_change_count": 116, "future_dh_runner_only_changes": rebound,
              "recovery_only_spec_field_changes": ["cell_id", "native_recovery_from"],
              "parser_executable_ast_equal_except_finite_or_none_and_exact_recovery_guard": True,
              "recovery_only_specs_reject_native_execution": True,
              "preserved_native_files": native_files,
              "recovery_status": bound(dst / "runner_status.json"), "recovery_note": bound(dst / "native_recovery.json"),
              "reporter_recovery_acceptance": row,
              "native_simulations_invoked_by_this_audit": 0, "native_population_recomputed_by_this_audit": False,
              "scope": "Frozen plan/spec and pre-V5 result receipt identity; retained native byte equality; existing scalar reporter acceptance. Not a new simulation or exhaustive physical proof."}
    output.write_bytes(reporter.json_bytes(result))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    value = run(args.output)
    print(json.dumps({k: value[k] for k in ("status", "coordinates_identical_count", "old_accepted_cell_count", "future_dh_runner_only_change_count")}, ensure_ascii=False))
