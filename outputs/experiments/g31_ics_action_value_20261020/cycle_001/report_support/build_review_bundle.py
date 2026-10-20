"""Build the fixed G31 review bundle without importing experiment code.

Dry-run is the default and creates no files. Run only after the coordinator has
released all closed experiment outputs. An explicit, new output directory is
mandatory. --execute copies the allowlist, writes a manifest and a sibling ZIP.
No simulator, fitter, git staging, deletion or source modification is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import time
import zipfile


CYCLE = "outputs/experiments/g31_ics_action_value_20261020/cycle_001"
MANIFEST_SCHEMA = "g31.portable_airport_review_bundle.v1"
RUN_NAMES = (
    ["A_common_local_return_001", "A_common_local_return_002"]
    + [f"B_{parent}_{n}_{action}_001" for parent in (701, 702)
       for n in (0, 1, 2) for action in ("a_patch", "a_ref")]
    + [f"C_{parent}_extra_{action}_001" for parent in (701, 702)
       for action in ("a_patch", "a_ref")]
    + [f"C_{parent}_{n}_{action}_001" for parent in (801, 802)
       for n in (0, 1) for action in ("a_patch", "a_ref")]
    + [f"F_{fleet}_{parent}_{action}_001"
       for fleet, parent in ((18, 701), (18, 801), (26, 702), (26, 802))
       for action in ("a_patch", "a_ref")]
    + [f"H_{parent}_calendar_{action}_001" for parent in (701, 702)
       for action in ("a_patch", "a_ref")]
)
RUN_FILES = """input.json final_result.json.gz client_calls.json.gz
ack_views.json.gz execution_evidence.json.gz branch_evidence.json.gz
pair_trace.json.gz offline_diagnostics.json.gz wait_graph_report.json.gz
activation_prefix.json.gz largest_batch.json.gz plan.json receipt.json
worker_report.json evaluation.json planner_summary.json progress.jsonl
actual_plan_preload_receipts.json calendar_binding.json
callback_audit_receipt.json actual_prepared_feature_gate_status.json
stdout.log stderr.log""".split()
SUPPORT_SCRIPTS = (
    "audit_bundle.py", "build_review_bundle.py", "render_results.py",
    "summarize_operations.py", "selftest_audit_bundle.py",
    "selftest_build_review_bundle.py", "audit_learned_callbacks_001.py",
    "audit_prearrival_witnesses_001.py",
)
FIGURES = [f"report_support/final_figures_001/{name}.{extension}"
           for name in ("primary_C11_vs_C10_gain", "fixed_fleet_service_curves")
           for extension in ("png", "pdf", "svg")]
FINAL_ARTIFACTS = (
    ["prospective_offline_review.json",
     "report_support/training_independent_audit_001.json",
     "report_support/stage_report_review_001.json",
     "report_support/review_request_provenance_001.json",
     "report_support/E_N18_C10_P801_001_callback_chain_parser_audit_001.json",
     "report_support/final_figures_001/figure_manifest.json",
     "report_support/final_operational_summary_001/operational_summary.json",
     "report_support/final_operational_summary_001/operational_summary.txt"]
    + FIGURES
    + [f"report_support/D_N22_{v}_S{s}_P{p}_001_learned_callback_audit_001.json"
       for p in (901, 902) for v in ("C01", "C11") for s in (17, 29, 43)]
    + [f"report_support/G_N{n}_C11_S29_P{p}_001_learned_callback_audit_001.json"
       for p in (901, 902) for n in (18, 22, 26)]
)
OPTIONAL_WITNESSES = [
    path.replace("_learned_callback_audit_001.json", "_prearrival_mechanism_audit_001.json")
    for path in FINAL_ARTIFACTS if path.endswith("_learned_callback_audit_001.json")
]
PREPARED_GATE_FILES = ("complete_actual_callback.json", "feature_comparison.json", "receipt.json", "setup.json")
BUILD_DIRS = ("native029_build", "native029_roles_build")
TRAIN_DIRS = ("training_primary_001", "training_resource_001")


def require(ok, reason):
    if not ok:
        raise ValueError("bundle_build:" + reason)


def read_json(path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def canonical(value):
    require(isinstance(value, str) and value and "\\" not in value and ":" not in value,
            "forward_slash_relative_path:" + str(value))
    path = PurePosixPath(value)
    require(not path.is_absolute() and str(path) == value
            and all(part not in ("", ".", "..") for part in path.parts),
            "unsafe_path:" + value)
    return value


def inside(root, value):
    path = (root / canonical(value)).resolve()
    require(path.is_relative_to(root), "path_escapes_root:" + value)
    return path


def stable_hash(path):
    """Require a regular non-symlink file unchanged across the streaming read."""
    require(path.is_file() and not path.is_symlink(), "not_regular_file:" + str(path))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns),
            "file_changed_during_hash:" + str(path))
    return digest.hexdigest(), after.st_size


def write_json_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def excluded_support(path):
    parts = PurePosixPath(path).parts
    return any("dummy" in p.lower() or "proposal" in p.lower() or p == "__pycache__"
               or "test_tmp" in p.lower() or p == "root_tests_001" for p in parts) \
        or PurePosixPath(path).suffix == ".pyc" \
        or PurePosixPath(path).name.startswith("publication_plan_") \
        or PurePosixPath(path).name == "D_P901_rules_closed_comparison_001.json"


def destination_for(repo_relative):
    canonical(repo_relative)
    if repo_relative.startswith("outputs/") or repo_relative.startswith("docs/"):
        return repo_relative
    return "code/" + repo_relative


class Collection:
    def __init__(self, repo):
        self.repo = repo.resolve()
        self.files = {}
        self.sources = []
        self.bindings = []
        self.missing_optional = []
        self.runs = []
        self.all_run_receipts = []

    def add(self, repo_relative, *, kind="evidence", required=True, expected=None):
        path = inside(self.repo, repo_relative)
        if not path.is_file():
            require(not required, "required_file_missing:" + repo_relative)
            self.missing_optional.append(repo_relative)
            return
        digest, size = stable_hash(path)
        require(expected is None or digest == expected, "pinned_hash_mismatch:" + repo_relative)
        bundle_path = destination_for(repo_relative)
        row = {"path": bundle_path, "sha256": digest, "size": size, "included": True,
               "kind": kind, "local_path": str(path), "repository_path": repo_relative}
        if bundle_path in self.files:
            require(self.files[bundle_path] == row or
                    self.files[bundle_path]["sha256"] == digest, "conflicting_inclusion:" + bundle_path)
        else:
            self.files[bundle_path] = row

    def exclude(self, path, *, reason):
        path = path.resolve()
        require(path.is_relative_to(self.repo), "excluded_file_outside_repository")
        repo_relative = path.relative_to(self.repo).as_posix()
        bundle_path = destination_for(repo_relative)
        if bundle_path in self.files:
            return
        digest, size = stable_hash(path)
        self.files[bundle_path] = {
            "path": bundle_path, "sha256": digest, "size": size, "included": False,
            "kind": "excluded_local_artifact", "local_path": str(path),
            "repository_path": repo_relative, "reason": reason,
        }

    def source(self, *, owner_kind, owner_name, binding_document, pointer,
               original_key, expected, archive):
        normalized = canonical(original_key.replace("\\", "/"))
        require(isinstance(expected, str) and len(expected) == 64
                and all(c in "0123456789abcdef" for c in expected), "source_sha_shape")
        archive = archive.resolve()
        require(archive.is_relative_to(self.repo), "source_archive_outside_repository")
        candidates = (archive, inside(self.repo, normalized))
        actual = None
        for candidate in candidates:
            if candidate.is_file():
                digest, size = stable_hash(candidate)
                if digest == expected:
                    actual = candidate
                    break
                require(candidate != archive, "historical_source_archive_hash_mismatch:" + str(archive))
        require(actual is not None, "unresolved_historical_source:" + owner_name + ":" + original_key)
        blob = "source_blobs/sha256/" + expected[:2] + "/" + expected + ".bin"
        if blob not in self.files:
            self.files[blob] = {
                "path": blob, "sha256": expected, "size": size, "included": True,
                "kind": "deduplicated_pinned_execution_source", "local_path": str(actual),
                "repository_path": None,
            }
        self.bindings.append({
            "owner_kind": owner_kind, "owner_name": owner_name,
            "binding_document": binding_document, "binding_json_pointer": pointer,
            "original_relative_path_exact": original_key,
            "normalized_repo_relative_path": normalized,
            "original_archived_local_path": str(archive), "sha256": expected,
            "size": size, "blob_relative_path": blob, "included": True,
            "verification_status": "actual_bytes_match_pinned_sha256",
        })

    def inventory_tree(self, root, *, reason):
        if not root.exists():
            return
        require(root.is_dir() and not root.is_symlink(), "inventory_root_not_directory")
        for path in sorted(root.rglob("*")):
            require(not path.is_symlink(), "symlink_in_inventory:" + str(path))
            if path.is_file():
                self.exclude(path, reason=reason)


def collect(repo, *, proposal, review, extras=(), include_native=False, progress=False):
    repo = repo.resolve()
    cycle = inside(repo, CYCLE)
    require(review.is_file(), "final_review_required_before_collection")
    require(review.resolve().is_relative_to(cycle), "review_must_be_under_cycle")
    config = read_json(proposal)
    require(config["schema"] == "g31.publication_staging_proposal.v1", "proposal_schema")
    grid = read_json(cycle / "prospective_evaluation_grid_001.json")
    grid_rows = grid["rows"]
    require(len(grid_rows) == 34 and {r["batch"] for r in grid_rows} == {"E", "D", "G"},
            "fixed_34_prospective_rows")
    names = RUN_NAMES + [row["name"] for row in grid_rows]
    require(len(names) == len(set(names)) == 72, "exact_72_registered_long_runs")
    saved_review = read_json(review)
    saved = {r["name"]: r for r in saved_review["rows"] if r["batch"] in ("E", "D", "G")}
    require(set(saved) == {r["name"] for r in grid_rows}, "review_all_prospective_rows")
    result = Collection(repo)
    # Check every final receipt before any potentially large inventory scan.
    receipts, plans = {}, {}
    for name in names:
        directory = cycle / name
        require((directory / "receipt.json").is_file() and (directory / "plan.json").is_file(),
                "all_72_closed_receipts_required:" + name)
        receipt, plan = read_json(directory / "receipt.json"), read_json(directory / "plan.json")
        require(receipt.get("status") not in (None, "running", "pending", "prepared", "not_run"),
                "run_not_closed:" + name)
        require(receipt["plan_sha256"] == stable_hash(directory / "plan.json")[0],
                "receipt_plan_binding:" + name)
        receipts[name], plans[name] = receipt, plan
    require(receipts["A_common_local_return_001"]["status"] == "censored_budget_exhausted",
            "retain_original_A1_censoring")
    exact = config["repository_commit_allowlist"]
    for relative in exact["existing_tracked_modifications_exact"] + exact["new_task_source_test_and_contract_exact"]:
        require(relative.startswith(("cpp/", "scripts/", "tests/", "docs/")), "source_allowlist_prefix")
        result.add(relative, kind="current_task_source")
    result.add("docs/g31_ics_circulation/ACTION_VALUE_STAGE_20261020.md", kind="final_report")
    for relative in exact["artifact_candidates_exact_existing"]:
        if not excluded_support(relative):
            result.add(relative, required=True)
    for script in SUPPORT_SCRIPTS:
        relative = CYCLE + "/report_support/" + script
        result.add(relative, kind="portable_review_script", required=script != "selftest_build_review_bundle.py")
    result.add(review.relative_to(repo).as_posix(), kind="final_review")
    for relative in FINAL_ARTIFACTS:
        if relative == "prospective_offline_review.json":
            continue
        result.add(CYCLE + "/" + relative, kind="final_report")
    for relative in OPTIONAL_WITNESSES:
        result.add(CYCLE + "/" + relative, kind="sampled_actual_callback_witness", required=False)
    for relative in extras:
        require(not excluded_support(relative), "dummy_or_temp_extra_forbidden")
        require(relative.startswith(("docs/", CYCLE + "/")), "extra_must_be_explicit_report_or_campaign_file")
        result.add(relative, kind="explicit_report_extra")
    for pin in config["portable_bundle"]["forecast_historical_dependency_pins"]:
        result.add(pin["original_path"], kind="historical_forecast_dependency", expected=pin["sha256"])
    for index, name in enumerate(names, 1):
        directory, plan = cycle / name, plans[name]
        for filename in RUN_FILES:
            required = filename in ("plan.json", "receipt.json", "input.json") or (
                filename == "final_result.json.gz" and receipts[name]["status"] == "complete")
            result.add(CYCLE + "/" + name + "/" + filename, required=required)
        if name in ("E_N18_C00_P801_001", "E_N26_C00_P801_001"):
            for filename in PREPARED_GATE_FILES:
                result.add(CYCLE + "/" + name + "/actual_prepared_feature_gate/" + filename,
                           kind="actual_callback_prepared_feature_gate")
        result.all_run_receipts.append({
            "name": name, "status": receipts[name]["status"],
            "receipt": CYCLE + "/" + name + "/receipt.json",
            "plan": CYCLE + "/" + name + "/plan.json",
        })
        require(isinstance(plan.get("sources"), dict) and plan["sources"], "missing_run_source_pins:" + name)
        for key, digest in plan["sources"].items():
            result.source(owner_kind="run", owner_name=name, binding_document=CYCLE + "/" + name + "/plan.json",
                          pointer="/sources/" + key.replace("~", "~0").replace("/", "~1"),
                          original_key=key, expected=digest, archive=directory / "source" / key.replace("\\", "/"))
        result.inventory_tree(directory, reason="Not in exact lightweight run allowlist; full callback streams, "
                              "intermediate segments and duplicate source snapshots remain local. "
                              "Pinned source bytes are available through source_relocation_index.json.")
        if progress:
            print(json.dumps({"event": "run_inventoried", "ordinal": index, "total": 72, "name": name}), flush=True)
    for row in grid_rows:
        name, status = row["name"], receipts[row["name"]]["status"]
        require(saved[name]["status"] == status, "review_receipt_status:" + name)
        result.runs.append({"name": name, "batch": row["batch"], "status": status,
                            **{key: CYCLE + "/" + name + "/" + filename for key, filename in
                               (("input", "input.json"), ("final_result", "final_result.json.gz"),
                                ("receipt", "receipt.json"), ("plan", "plan.json"))}})
    for dirname in TRAIN_DIRS:
        directory = cycle / dirname
        manifest = read_json(directory / "manifest.json")
        for key, item in manifest["source_archive"].items():
            require(item["sha256"] == item["archive"]["sha256"], "training_archive_pin_mismatch")
            archive = Path(item["archive"]["path"]).resolve()
            require(archive.is_relative_to(directory / "source"), "training_archive_owner_root")
            result.source(owner_kind="training", owner_name=dirname,
                          binding_document=CYCLE + "/" + dirname + "/manifest.json",
                          pointer="/source_archive/" + key.replace("~", "~0").replace("/", "~1"),
                          original_key=key, expected=item["sha256"], archive=archive)
        result.inventory_tree(directory, reason="Training artifact outside exact fitted-model/data/receipt allowlist; "
                              "duplicate pinned source bytes are in the content-addressed source store.")
    for dirname in BUILD_DIRS:
        directory = cycle / dirname
        receipt = read_json(directory / "receipt.json")
        for field in ("source_before", "source_after"):
            for key, digest in receipt[field].items():
                result.source(owner_kind="native_build", owner_name=dirname,
                              binding_document=CYCLE + "/" + dirname + "/receipt.json",
                              pointer="/" + field + "/" + key.replace("~", "~0").replace("/", "~1"),
                              original_key=key, expected=digest, archive=directory / "source" / key.replace("\\", "/"))
        result.inventory_tree(directory, reason="Repeated native build source snapshot; exact pinned bytes "
                              "are available through the source relocation index.")
    model_ids = set()
    for curve in config["portable_bundle"]["all_24_model_training_curve_metadata"]:
        model = read_json(inside(repo, curve["path"]))
        require(model["epochs"] == 100 and [p["epoch"] for p in model["training_curve"]] == list(range(0, 101, 10)),
                "all_saved_fit_curve_points_required")
        require(result.files.get(destination_for(curve["path"]), {}).get("included") is True,
                "model_not_in_included_allowlist")
        require(isinstance(model.get("model_id"), str) and model["model_id"] not in model_ids,
                "distinct_model_ids_required")
        model_ids.add(model["model_id"])
    require(len({x["path"] for x in config["portable_bundle"]["all_24_model_training_curve_metadata"]}) == 24,
            "all_24_distinct_fits_required")
    binary = config["portable_bundle"]["native_author_binary_optional"]
    if include_native:
        result.add(binary["path"], kind="author_windows_cp311_binary", expected=binary["sha256"])
    else:
        result.exclude(inside(repo, binary["path"]), reason="Author-built Windows CPython 3.11 binary omitted; "
                       "source/build receipts are included. No cross-platform rebuild claim.")
    # Inventory excluded support intermediates without admitting unrelated repo files.
    for dirname in ("report_support", "prepared_features_001", "native029_acceptance_sources",
                    "root_tests_001", "DUMMY_portable_audit_selftest_001"):
        result.inventory_tree(cycle / dirname, reason="Outside exact portable support allowlist; "
                              "DUMMY fixtures, proposals, caches and temporary files are not scientific runs.")
    result.review_path = review.relative_to(repo).as_posix()
    result.proposal_sha256 = stable_hash(proposal)[0]
    return result


def summarize(collection):
    included = [x for x in collection.files.values() if x["included"]]
    excluded = [x for x in collection.files.values() if not x["included"]]
    return {
        "included_files": len(included), "included_bytes": sum(x["size"] for x in included),
        "excluded_files": len(excluded), "excluded_local_bytes": sum(x["size"] for x in excluded),
        "source_bindings": len(collection.bindings),
        "unique_source_blobs": sum(x["kind"] == "deduplicated_pinned_execution_source" for x in included),
        "all_long_run_receipts": len(collection.all_run_receipts), "production_runs": len(collection.runs),
    }


def validate_output(repo, output):
    output = output.resolve()
    require(output != repo and output != inside(repo, CYCLE), "output_cannot_be_existing_workspace")
    require(not output.exists(), "output_directory_already_exists")
    require(output.parent.is_dir(), "output_parent_must_exist")
    archive = output.with_name(output.name + ".zip")
    receipt = output.with_name(output.name + ".publication_receipt.json")
    require(not archive.exists() and not receipt.exists(), "archive_or_publication_receipt_already_exists")
    return output, archive, receipt


def build(collection, output, *, archive, receipt):
    """Create a new immutable result. Partial failures are preserved for diagnosis."""
    require(not output.exists() and not archive.exists() and not receipt.exists(), "fresh_outputs_only")
    check_output_lengths(collection, output)
    output.mkdir()
    entries = {}
    for item in sorted(collection.files.values(), key=lambda x: x["path"]):
        entries[item["path"]] = item.copy()
        if not item["included"]:
            continue
        target = inside(output, item["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        with Path(item["local_path"]).open("rb") as source, target.open("xb") as destination:
            shutil.copyfileobj(source, destination, 1024 * 1024)
        require(stable_hash(target) == (item["sha256"], item["size"]), "copied_file_changed:" + item["path"])
    source_index = {
        "schema": "g31.portable_deduplicated_execution_sources.v1",
        "bindings": collection.bindings, "all_pinned_bytes_included_and_verified": True,
        "reconstruction": "Write blob bytes to normalized_repo_relative_path within an owner-specific new directory. "
        "Preserve original binding documents. Do not merge different owner source versions.",
    }
    write_json_new(output / "source_relocation_index.json", source_index)
    original_files = [
        {"path": x["repository_path"], "sha256": x["sha256"], "size": x["size"]}
        for x in entries.values() if x["included"] and x["repository_path"] is not None
    ]
    original_files.sort(key=lambda x: x["path"])
    generated = ["bundle_manifest.json", "source_relocation_index.json", "staging_allowlist.json"]
    generated += sorted(x["path"] for x in entries.values()
                        if x["included"] and x["kind"] == "deduplicated_pinned_execution_source")
    staging = {
        "schema": "g31.exact_repository_staging_allowlist.v1",
        "repository_root": str(collection.repo), "original_repository_files": original_files,
        "generated_publication_paths": [
            {"bundle_relative_path": path,
             "repository_relative_path": (output / path).relative_to(collection.repo).as_posix()
             if output.is_relative_to(collection.repo) else None}
            for path in generated
        ],
        "external_output_requires_explicit_relocation_before_git_staging": not output.is_relative_to(collection.repo),
        "archive_explicitly_excluded": str(archive),
        "publication_receipt_external_to_manifest": str(receipt),
        "git_index_modified_by_builder": False,
        "instruction": "Stage only these exact original paths plus reviewed generated metadata/source blobs. "
        "Never stage the copied duplicate evidence tree, the ZIP, unrelated untracked files or whole directories.",
    }
    write_json_new(output / "staging_allowlist.json", staging)
    for name in ("source_relocation_index.json", "staging_allowlist.json"):
        digest, size = stable_hash(output / name)
        entries[name] = {"path": name, "sha256": digest, "size": size, "included": True,
                         "kind": "generated_publication_metadata"}
    manifest = {
        "schema": MANIFEST_SCHEMA, "files": sorted(entries.values(), key=lambda x: x["path"]),
        "runs": collection.runs, "all_registered_long_run_receipts": collection.all_run_receipts,
        "review": {"path": collection.review_path, "rows_key": "rows", "comparisons_key": "comparisons"},
        "proposal_sha256": collection.proposal_sha256,
        "population": 28506, "cost_window": [7200.0, 59400.0],
        "manifest_self_hash": "Excluded to avoid circularity; bound in sibling publication receipt and archive SHA.",
        "scope": {"full_callback_streams_included": False, "full_callback_semantics_verified": False,
                  "native_replayed": False, "models_refitted": False, "independent_real_airport_days": 0},
        "missing_optional_files": sorted(set(collection.missing_optional)),
        "audit_command": "python " + CYCLE + "/report_support/audit_bundle.py --root . --output portable_audit.json",
        "source_index": "source_relocation_index.json", "staging_allowlist": "staging_allowlist.json",
    }
    if getattr(collection, "dummy_only", False):
        manifest["dummy_data"] = True
        manifest["dummy_notice"] = "DUMMY filesystem builder test; not experimental evidence or a cost-audit fixture."
    write_json_new(output / "bundle_manifest.json", manifest)
    # Do not silently publish an internal file that was not inventoried.
    packed = [x["path"] for x in entries.values() if x["included"]] + ["bundle_manifest.json"]
    require(set(packed) == {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()},
            "unlisted_output_file")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=6,
                         allowZip64=True) as zipped:
        for name in sorted(packed):
            zipped.write(inside(output, name), name)
    # Verify archived members by streaming, without needing a second extraction.
    with zipfile.ZipFile(archive, "r") as zipped:
        require(set(zipped.namelist()) == set(packed), "archive_member_set_mismatch")
        for name in packed:
            with zipped.open(name) as stream:
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            expected = stable_hash(output / name)[0] if name == "bundle_manifest.json" else entries[name]["sha256"]
            require(digest.hexdigest() == expected, "archive_member_hash:" + name)
    publication = {
        "schema": "g31.portable_bundle_build_receipt.v1", "status": "built_and_archive_bytes_verified",
        "output_directory": str(output), "archive": str(archive),
        "archive_sha256": stable_hash(archive)[0], "archive_bytes": archive.stat().st_size,
        "manifest_sha256": stable_hash(output / "bundle_manifest.json")[0], **summarize(collection),
        "native_starts": 0, "fits": 0, "git_index_modified": False,
        "cost_audit_status": "not_run_by_builder; invoke the included standard-library audit command",
        "full_callback_stream_coverage_claimed": False,
    }
    write_json_new(receipt, publication)
    return publication


def check_output_lengths(collection, output):
    if sys.platform == "win32":
        longest = max((str(output / x["path"]) for x in collection.files.values() if x["included"]), key=len)
        require(len(longest) < 260, "choose_short_output_directory_for_windows_paths:" + longest)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--proposal", type=Path)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--extra", action="append", default=[], help="One exact repo-relative report/figure file")
    parser.add_argument("--include-native-binary", action="store_true")
    parser.add_argument("--execute", action="store_true", help="Copy and ZIP; omitted means no output writes")
    args = parser.parse_args()
    try:
        repo = args.repo.resolve()
        output, archive, receipt = validate_output(repo, args.output_dir)
        cycle = inside(repo, CYCLE)
        proposal = args.proposal or cycle / "report_support/publication_plan_001.json"
        review = args.review or cycle / "prospective_offline_review.json"
        started = time.monotonic()
        selected = collect(repo, proposal=proposal, review=review, extras=args.extra,
                           include_native=args.include_native_binary, progress=True)
        check_output_lengths(selected, output)
        if not args.execute:
            report = {"status": "dry_run_no_output_writes", "output_directory": str(output),
                      "archive": str(archive), **summarize(selected)}
        else:
            report = build(selected, output, archive=archive, receipt=receipt)
        report["wall_seconds"] = time.monotonic() - started
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed_no_deletion_or_rollback", "reason": str(error),
                          "native_starts": 0, "fits": 0}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
