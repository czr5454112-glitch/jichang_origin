"""Small-file disclosure checks; no simulation or full-population exporter run."""
from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.eval import export_feng_v5_campaign as export

BASE_COMMIT = "0c99454e1b275c9d924cca92773b3149d1143b2f"
BASE_SHA = "3cdcc48f7a89846de3de9018df59b865f8dc7a171b4197c9e8a50559c8ce71fa"
NUMERIC_FUNCTIONS = ("distribution", "normalize_v5_cell", "load_v5_result", "archive_v5_cell",
                     "canonical_segments", "hca_primary_timing", "export_control", "paired_aggregate")


def expect_rejected(call, label: str, checks: list) -> None:
    try:
        call()
    except (ValueError, KeyError):
        checks.append(label)
    else:
        raise AssertionError(f"expected rejection: {label}")


def numeric_prefix(tree: ast.FunctionDef) -> str:
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "support" for t in node.targets):
            break
        nodes.append(node)
    return ast.dump(ast.Module(body=nodes, type_ignores=[]), include_attributes=False)


def main() -> int:
    checks = []
    old = subprocess.run(["git", "show", f"{BASE_COMMIT}:scripts/eval/export_feng_v5_campaign.py"],
                         cwd=ROOT, check=True, capture_output=True).stdout
    export.require(hashlib.sha256(old).hexdigest() == BASE_SHA, "frozen predecessor SHA differs")
    new = Path(export.__file__).read_bytes()
    trees = [{n.name: n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)} for code in (old, new)]
    for name in NUMERIC_FUNCTIONS:
        export.require(ast.dump(trees[0][name], include_attributes=False) == ast.dump(trees[1][name], include_attributes=False),
                       f"protected numeric/API function changed: {name}")
    export.require(numeric_prefix(trees[0]["export_campaign"]) == numeric_prefix(trees[1]["export_campaign"]),
                   "exported cell/paired table generation changed")
    checks.append("EIGHT_PROTECTED_FUNCTIONS_AND_CELL_PAIRED_EXPORT_PREFIX_AST_IDENTICAL")
    notes = export.read_json(export.RESULT_ROOT / "control_completion_notes.json")
    temporary_root = ROOT / "tmp"
    temporary_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v5_scientific_notes_", dir=temporary_root) as name:
        fixture = Path(name)
        export.require(fixture.resolve().parent == temporary_root.resolve(), "temporary fixture must remain in workspace tmp")
        qualification = export.scientific_interpretation(export.RESULT_ROOT, fixture, archive=True)
        # Only the 60 small archived native summaries are needed by this fixture.
        for cell in notes["cells"]:
            folder = export.external.cell_dir(export.EVIDENCE_ROOT, float(cell["load_factor"]), int(cell["seed"]), cell["map"])
            target = export.external.cell_dir(fixture, float(cell["load_factor"]), int(cell["seed"]), cell["map"])
            shutil.copyfile(folder / "hca/fresh_hca_summary.json", target / "hca/fresh_hca_summary.json")
        verified = export.verify_scientific_interpretation(fixture, qualification)
        export.require(verified["hca_summaries_recomputed"] == 60
                       and verified["hca_invalidated_for_no_loss_physical_comparison"] == 43
                       and verified["hca_no_positive_residual_detected_not_fully_validated"] == 17
                       and verified["proves_hca_execution_correctness"] is False, "unexpected fixture qualification")
        checks.append("ALL_60_REAL_SUMMARIES_AND_ARCHIVED_CAMPAIGN_COUNTERS_RECOMPUTE_43_POSITIVE_17_ZERO")
        checks.append("NOTES_JSON_MD_AND_60_SUMMARY_CSV_BYTES_ARCHIVED_WITH_SHA")
        empty = fixture / "absent_notes"
        empty.mkdir()
        absent = export.scientific_interpretation(empty, fixture / "unused", archive=False)
        export.require(export.verify_scientific_interpretation(fixture, absent)["status"] == "NOT_ASSESSED_NO_CONTROL_COMPLETION_NOTES",
                       "missing optional notes must not imply scientific validity")
        checks.append("ABSENT_OPTIONAL_NOTES_EXPLICIT_NOT_ASSESSED")
        bad = copy.deepcopy(notes)
        bad["cells"].pop()
        expect_rejected(lambda: export.validate_control_completion_notes(bad), "MISSING_COORDINATE_REJECTED", checks)
        wrong_total = copy.deepcopy(qualification)
        wrong_total["hca_invalidated_for_no_loss_physical_comparison"] = 42
        expect_rejected(lambda: export.verify_scientific_interpretation(fixture, wrong_total), "WRONG_43_COUNT_REJECTED", checks)
        wrong_rule = copy.deepcopy(qualification)
        wrong_rule["cells"][0]["qualification"] = "FULLY_SCIENTIFICALLY_VALID"
        expect_rejected(lambda: export.verify_scientific_interpretation(fixture, wrong_rule), "ZERO_RESIDUAL_AS_FULL_VALIDITY_REJECTED", checks)
        summary = fixture / qualification["cells"][0]["summary_archive_relative_path"]
        original = summary.read_bytes()
        summary.write_bytes(original + b"\n")
        expect_rejected(lambda: export.verify_scientific_interpretation(fixture, qualification), "ALTERED_SUMMARY_BYTES_REJECTED", checks)
        summary.write_bytes(original)
        campaign = summary.parent.parent / "fresh_hca_summary.json"
        original_campaign = campaign.read_bytes()
        changed = json.loads(original_campaign)
        changed["runs"][0]["benchmark_summary"]["completed_count"] = "0"
        campaign.write_text(json.dumps(changed), encoding="utf-8")
        expect_rejected(lambda: export.verify_scientific_interpretation(fixture, qualification), "CAMPAIGN_CSV_COUNTER_CONTRADICTION_REJECTED", checks)
        campaign.write_bytes(original_campaign)
        export.verify_scientific_interpretation(fixture, qualification)
    result = {"schema": "czr005.feng_v5_scientific_interpretation_exporter_validation.v1", "status": "PASS",
        "simulation_runs": 0, "full_population_export_runs": 0, "original_observations_modified": False,
        "base_commit": BASE_COMMIT, "base_exporter_sha256": BASE_SHA,
        "revised_exporter_sha256": export.GENERATOR_SHA, "validation_script_sha256": export.sha(Path(__file__)),
        "population_audit_sha256": export.POPULATION_GENERATOR_SHA, "checks": checks,
        "check_count": len(checks), "sidecar_json_sha256": export.sha(export.RESULT_ROOT / "control_completion_notes.json"),
        "sidecar_md_sha256": export.sha(export.RESULT_ROOT / "control_completion_notes.md"),
        "scope": "Disclosure/identity/residual consistency only; no reconstruction of lost HCA routes or proof of full physical correctness."}
    output = export.RESULT_ROOT / "scientific_interpretation_exporter_validation.json"
    export.external._atomic_json(output, result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
