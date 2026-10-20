"""DUMMY-only filesystem tests of the portable builder; never read experiment data."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("bundle_builder", Path(__file__).with_name("build_review_bundle.py"))
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def write(path, value):
    builder.write_json_new(path, value)


def text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def expect_failure(function, expected):
    try:
        function()
    except (ValueError, OSError) as error:
        assert expected in str(error), (expected, str(error))
        return
    raise AssertionError("expected rejection: " + expected)


def fixture(repo):
    """Create 72 tiny DUMMY ended runs, no physical simulator outputs."""
    cycle = repo / builder.CYCLE
    grid = [{"name": f"E_N{n}_{v}_P801_001", "batch": "E"}
            for n in (18, 26) for v in ("C00", "C10")]
    grid += [{"name": f"D_N22_{v}_P{p}_001", "batch": "D"} for p in (901, 902)
             for v in ("C00", "C10", "C01_S17", "C01_S29", "C01_S43", "C11_S17", "C11_S29", "C11_S43")]
    grid += [{"name": f"G_N{n}_{v}_P{p}_001", "batch": "G"} for p in (901, 902)
             for n, v in ((18, "C11_S29"), (18, "C00"), (18, "C10"), (22, "C11_S29"),
                          (26, "C11_S29"), (26, "C00"), (26, "C10"))]
    write(cycle / "prospective_evaluation_grid_001.json", {"rows": grid, "dummy_data": True})
    source = "scripts/DUMMY_source.py"
    text(repo / source, "# DUMMY historical source\n")
    sha = builder.stable_hash(repo / source)[0]
    for name in builder.RUN_NAMES + [r["name"] for r in grid]:
        directory = cycle / name
        plan = {"name": name, "sources": {source.replace("/", "\\"): sha}, "dummy_data": True}
        write(directory / "plan.json", plan)
        status = "censored_budget_exhausted" if name == "A_common_local_return_001" else "complete"
        write(directory / "receipt.json", {"status": status,
                                          "plan_sha256": builder.stable_hash(directory / "plan.json")[0]})
        write(directory / "input.json", {"dummy_data": True})
        text(directory / "final_result.json.gz", "DUMMY unparsed final placeholder; not a native output")
        text(directory / "source" / source, "# DUMMY historical source\n")
        text(directory / "callback_audit.jsonl.gz", "DUMMY omitted callback bytes")
        if name in ("E_N18_C00_P801_001", "E_N26_C00_P801_001"):
            for filename in builder.PREPARED_GATE_FILES:
                write(directory / "actual_prepared_feature_gate" / filename, {"dummy_data": True})
    write(cycle / "prospective_offline_review.json",
          {"rows": [dict(r, status="complete") for r in grid], "dummy_data": True})
    for filename in builder.FINAL_ARTIFACTS:
        if filename != "prospective_offline_review.json":
            text(cycle / filename, "DUMMY report/figure placeholder")
    candidates = []
    curves = []
    for dirname in builder.TRAIN_DIRS:
        directory = cycle / dirname
        archive = directory / "source" / source
        text(archive, "# DUMMY historical source\n")
        write(directory / "manifest.json", {"source_archive": {
            source: {"sha256": sha, "original_path": str(repo / source),
                     "archive": {"path": str(archive), "sha256": sha}}}})
        candidates.append((directory / "manifest.json").relative_to(repo).as_posix())
        for number in range(12):
            path = directory / f"model_{number}.json"
            write(path, {"epochs": 100, "model_id": hashlib.sha256(str(path).encode()).hexdigest(),
                         "training_curve": [{"epoch": n} for n in range(0, 101, 10)],
                         "dummy_data": True})
            relative = path.relative_to(repo).as_posix()
            candidates.append(relative)
            curves.append({"path": relative})
    for dirname in builder.BUILD_DIRS:
        directory = cycle / dirname
        text(directory / "source" / source, "# DUMMY historical source\n")
        write(directory / "receipt.json", {"source_before": {source: sha}, "source_after": {source: sha}})
        candidates.append((directory / "receipt.json").relative_to(repo).as_posix())
    for script in builder.SUPPORT_SCRIPTS:
        text(cycle / "report_support" / script, "# DUMMY script placeholder\n")
    text(repo / "docs/g31_ics_circulation/ACTION_VALUE_STAGE_20261020.md", "DUMMY report")
    text(repo / "build/DUMMY_native.pyd", "DUMMY nonexecutable binary")
    proposal = {
        "schema": "g31.publication_staging_proposal.v1",
        "repository_commit_allowlist": {"existing_tracked_modifications_exact": [source],
                                      "new_task_source_test_and_contract_exact": [],
                                      "artifact_candidates_exact_existing": candidates},
        "portable_bundle": {"forecast_historical_dependency_pins": [],
                            "all_24_model_training_curve_metadata": curves,
                            "native_author_binary_optional": {
                                "path": "build/DUMMY_native.pyd",
                                "sha256": builder.stable_hash(repo / "build/DUMMY_native.pyd")[0]}},
    }
    proposal_path = cycle / "report_support/publication_plan_001.json"
    write(proposal_path, proposal)
    return proposal_path, cycle / "prospective_offline_review.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    assert "DUMMY" in str(output) and not output.exists()
    output.mkdir()
    repo = output / "DUMMY_repository"
    repo.mkdir()
    proposal, review = fixture(repo)
    selected = builder.collect(repo, proposal=proposal, review=review)
    selected.dummy_only = True
    summary = builder.summarize(selected)
    assert summary["all_long_run_receipts"] == 72
    assert summary["production_runs"] == 34
    assert summary["unique_source_blobs"] == 1
    assert len(selected.bindings) == 78
    assert any(not x["included"] and x["path"].endswith("callback_audit.jsonl.gz")
               for x in selected.files.values())
    out, archive, receipt = builder.validate_output(repo, output / "DUMMY_bundle")
    built = builder.build(selected, out, archive=archive, receipt=receipt)
    manifest = builder.read_json(out / "bundle_manifest.json")
    assert manifest["dummy_data"] is True
    assert manifest["all_registered_long_run_receipts"][0]["status"] == "censored_budget_exhausted"
    staged = builder.read_json(out / "staging_allowlist.json")
    assert not any(x["path"].endswith(".zip") for x in staged["original_repository_files"])
    assert not any("/source/" in x["path"] for x in staged["original_repository_files"])
    with zipfile.ZipFile(archive) as zipped:
        assert "bundle_manifest.json" in zipped.namelist()
        assert not any(x.endswith("callback_audit.jsonl.gz") for x in zipped.namelist())
        assert not any("publication_plan_" in x for x in zipped.namelist())
    expect_failure(lambda: builder.validate_output(repo, out), "already_exists")
    expect_failure(lambda: builder.inside(repo, "../escape"), "unsafe_path")
    expect_failure(lambda: builder.inside(repo, "C:/escape"), "forward_slash")
    expect_failure(lambda: builder.collect(repo, proposal=proposal, review=repo / "missing.json"),
                   "final_review_required")
    # Missing final receipt must reject before inventory collection.
    absent = repo / builder.CYCLE / builder.RUN_NAMES[-1] / "receipt.json"
    original = absent.read_bytes()
    moved = absent.with_name("DUMMY_saved_receipt.json")
    absent.rename(moved)
    expect_failure(lambda: builder.collect(repo, proposal=proposal, review=review), "all_72_closed")
    moved.rename(absent)
    assert absent.read_bytes() == original
    # A tampered archived source must not be replaced by the matching current source.
    wrong = repo / builder.CYCLE / builder.RUN_NAMES[0] / "source/scripts/DUMMY_source.py"
    original_source = wrong.read_bytes()
    wrong.write_bytes(b"DUMMY corrupted historical source")
    expect_failure(lambda: builder.collect(repo, proposal=proposal, review=review),
                   "historical_source_archive_hash_mismatch")
    wrong.write_bytes(original_source)
    # A file appearing only in the excluded inventory cannot satisfy model coverage.
    proposal_object = builder.read_json(proposal)
    original_proposal = proposal.read_bytes()
    first_model = proposal_object["portable_bundle"]["all_24_model_training_curve_metadata"][0]["path"]
    proposal_object["repository_commit_allowlist"]["artifact_candidates_exact_existing"].remove(first_model)
    proposal.write_text(json.dumps(proposal_object), encoding="utf-8")
    expect_failure(lambda: builder.collect(repo, proposal=proposal, review=review),
                   "model_not_in_included_allowlist")
    proposal.write_bytes(original_proposal)
    proposal_object = builder.read_json(proposal)
    curves = proposal_object["portable_bundle"]["all_24_model_training_curve_metadata"]
    curves[-1] = curves[0]
    proposal.write_text(json.dumps(proposal_object), encoding="utf-8")
    expect_failure(lambda: builder.collect(repo, proposal=proposal, review=review), "distinct_model_ids_required")
    proposal.write_bytes(original_proposal)
    # CLI without --execute is read-only even after a complete DUMMY selection.
    dry_output = output / "DUMMY_dry_run_output"
    process = subprocess.run([sys.executable, "-B", str(Path(builder.__file__)), "--repo", str(repo),
                              "--output-dir", str(dry_output)], capture_output=True, text=True, check=False)
    assert process.returncode == 0, process.stderr
    assert "dry_run_no_output_writes" in process.stdout
    assert not dry_output.exists() and not dry_output.with_name(dry_output.name + ".zip").exists()
    write(output / "DUMMY_selftest_receipt.json", {
        "schema": "g31.DUMMY_bundle_builder_selftest.v1", "status": "passed",
        "dummy_only": True, "real_campaign_data_read": False, "native_starts": 0, "fits": 0,
        "checks": ["72 closed receipt and 34 production definitions", "A1 censoring retained",
                   "78 historical source bindings deduplicated into one exact blob",
                   "all 24 saved fit curves", "callback and original source copies excluded",
                   "ZIP member bytes verified by builder", "ZIP absent from staging allowlist",
                   "existing directory refused", "path traversal refused", "missing final review refused",
                   "missing final receipt refused", "tampered historic source refused",
                   "excluded-only model rejected", "duplicate model identity rejected",
                   "CLI default dry-run created no files"],
        "builder_sha256": builder.stable_hash(Path(builder.__file__))[0],
        "dummy_bundle_sha256": built["archive_sha256"],
    })
    print(json.dumps({"status": "passed_DUMMY_only", "receipt": str(output / "DUMMY_selftest_receipt.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
