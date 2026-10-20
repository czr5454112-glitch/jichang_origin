"""Explicit final compact builder; source preparation is not permission to run.

No discovery, native, fit, Git, hardlinks, sample reuse, or scientific source
imports. Caller supplies a SHA-bound request and allowlist002 request. All
registered native attempts and all 40 formal terminal receipts must be present
before any formal plan/result is opened or any package directory is created.
The pinned portable auditor supplies freeze/closure identity checks; its
separate post-build numerical audit remains mandatory.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SCHEMA = "g31.inventory_spi.final_compact_builder.v2"
SELECTOR_SHA = "c0738c470ac26eea8bad2b0f96b57b3174e6e994aee6e575baf7458505428342"
BASE_SHA = "7d60b20c1a4cdcee63b79f9477c96f6764e15e4908facd714b0e4fa45121271a"
FORMAL_SHA = "edb69cc0481858bed7cca9cd04d9a6b2e704d452839600aed90081a138653db4"
REVIEW_SHA = "1c9deb4197ab6609b9a632592721faab78864b756142a5b6b49f08566c015a32"
ROLES = {"diagnostic", "failed_attempt", "round0_pair", "round1_pair", "formal"}


def require(ok, reason):
    if not ok:
        raise ValueError("final_compact_builder:" + reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def refkey(ref):
    require(isinstance(ref, dict) and isinstance(ref.get("path"), str)
            and Path(ref["path"]).is_absolute(), "absolute_reference")
    require(isinstance(ref.get("sha256"), str) and len(ref["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in ref["sha256"]), "exact_sha_reference")
    return str(Path(ref["path"]).resolve()).casefold(), ref["sha256"]


def reference(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def load_pinned(name, expected):
    path = HERE / (name + ".py")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "pinned_helper:" + name)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def helpers():
    return (load_pinned("compact_publication_allowlist_002", SELECTOR_SHA),
            load_pinned("audit_compact_publication_001", BASE_SHA),
            load_pinned("audit_compact_formal_002", FORMAL_SHA))


def approved_path(path, selector):
    path = selector.path_in_workspace(path)
    require(not any(part.lower().startswith("compact_actual_sample")
                    or "dummy" in part.lower() or part.endswith("_validation_inputs")
                    for part in path.parts), "no_sample_dummy_or_fixture_tree")
    return path


def validate_request_shape(value):
    """Small pure check. It deliberately cannot authorize a build on its own."""
    require(value.get("schema") == SCHEMA + ".request"
            and value.get("actual_final_publication") is True, "actual_request_required")
    for key in ("allowlist_request", "attempt_ledger"):
        refkey(value[key])
    require(type(value.get("expected_long_attempts")) is int
            and 112 <= value["expected_long_attempts"] <= 128, "finite_complete_native_roster")
    runs = value["runs"]
    require(len(runs) == value["expected_long_attempts"]
            and len({r["name"] for r in runs}) == len(runs)
            and len({refkey(r["plan"])[0] for r in runs}) == len(runs), "all_unique_native_runs")
    for row in runs:
        require(row["role"] in ROLES and Path(row["name"]).name == row["name"]
                and row["name"] not in (".", ".."), "registered_run_role_name")
        refkey(row["receipt"])
    counts = Counter(r["role"] for r in runs)
    require(counts["round0_pair"] == 48 and counts["round1_pair"] == 24
            and counts["formal"] == 40, "fixed_pair_and_formal_denominators")
    formal = value["formal"]
    require(len(formal["runs"]) == 40
            and {r["name"] for r in formal["runs"]} ==
            {r["name"] for r in runs if r["role"] == "formal"}, "same_formal_forty_names")
    for key in ("roster", "unlock", "gate_implementation", "grid_audit", "effects"):
        refkey(formal[key])
    for row in formal["runs"]:
        for key in ("plan", "receipt", "cache"):
            refkey(row[key])
    training = value["training"]
    for key in ("stage_freeze", "spi_freeze", "round0_collection",
                "round1_collection", "execution_receipt"):
        refkey(training[key])
    require(len(training["fit_events"]) == 2, "two_chain_event_artifacts")
    for ref in training["fit_events"]:
        refkey(ref)
    require(value["gate_basis"]["implementation_review"]["sha256"] == REVIEW_SHA,
            "fixed_implementation_review")
    require(isinstance(value["administrative_artifacts"], list)
            and value["administrative_artifacts"], "administrative_failure_and_fit_artifacts_required")
    require(isinstance(value["superseded_manifests"], list)
            and value["superseded_manifests"], "superseded_scopes_required")
    require(isinstance(value["excluded_large_logs"], list), "explicit_excluded_inventory")
    return counts


class ExplicitFiles:
    """Local preflight view; references can only resolve through explicit input."""

    def __init__(self, spec, request, selector, base):
        self.selector, self.base = selector, base
        self.items, self.mapping = {}, {}
        self.manifest = {"excluded_large_logs": request["excluded_large_logs"]}
        require(spec["schema"] == selector.SCHEMA + ".request"
                and spec["template_not_final"] is False, "bound_allowlist002_request")
        for item in spec["compact_artifacts"]:
            require(item["category"] in selector.CATEGORIES, "explicit_artifact_category")
            self.add(item["reference"], item["category"], item.get("structured_audit"))
        # A source manifest explicitly enumerates every allowed archived file.
        # It does not authorize scanning its directory or finding new runs.
        for ref in spec["source_manifests"]:
            require(Path(ref["path"]).name == "source_manifest.json", "source_metadata_file_only")
            self.add(ref, "registration")
        for ref in spec["source_manifests"]:
            manifest = self.read(ref)
            root = approved_path(manifest["root"], selector)
            for logical, expected in manifest["files"].items():
                path = approved_path(root / logical, selector)
                require(path.is_relative_to(root), "source_path_cannot_escape")
                self.add({"path": str(path), "sha256": expected}, "source")
        excluded_keys = set()
        for row in request["excluded_large_logs"]:
            key = base.original_key(row["path"])
            expected = row.get("sha256") or row.get("declared_expected_sha256")
            refkey({"path": row["path"], "sha256": expected})
            approved_path(row["path"], selector)
            require(row.get("included") is False and row.get("scope")
                    and key not in self.mapping and key not in excluded_keys,
                    "explicit_unique_excluded_scope_no_included_overlap")
            excluded_keys.add(key)

    def add(self, ref, category, structured=None):
        refkey(ref)
        path = approved_path(ref["path"], self.selector)
        name = path.name.lower()
        forbidden = {n.lower() for n in self.selector.LARGE_LOCAL} | (
            self.selector.RAW_HISTORY_NAMES - {"final_result.json"})
        require(name not in forbidden, "raw_history_never_copied")
        if name == "final_result.json":
            require(category in ("input", "dataset", "receipt") and structured is None,
                    "plain_small_result_only_original_raw_category_no_expansion")
        key = self.base.original_key(str(path))
        item = {"reference": {"path": str(path), "sha256": ref["sha256"]},
                "category": category, "structured_audit": structured}
        if key in self.items:
            require(self.items[key]["reference"] == item["reference"]
                    and self.items[key]["structured_audit"] == structured, "consistent_explicit_alias")
        else:
            self.items[key] = item
            self.mapping[key] = {"sha256": ref["sha256"], "path": str(path)}

    def mapped(self, ref):
        refkey(ref)
        key = self.base.original_key(ref["path"])
        require(key in self.items and self.items[key]["reference"]["sha256"] == ref["sha256"],
                "missing_explicit_dependency:" + ref["path"])
        return self.mapping[key]

    def read(self, ref):
        row = self.mapped(ref)
        item = self.items[self.base.original_key(ref["path"])]
        maximum = (item["structured_audit"] or {}).get("max_bytes", self.selector.MAX_SMALL)
        require(type(maximum) is int and 0 < maximum <= self.selector.MAX_STRUCTURED_AUDIT,
                "bounded_metadata_read")
        path = Path(row["path"])
        require(path.stat().st_size <= maximum, "metadata_read_size_limit")
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == ref["sha256"], "metadata_original_sha")
        if path.suffix.lower() == ".gz":
            raw = gzip.decompress(raw)
        return self.base.decode(raw)

    def validate_included(self):
        # Called only after every registered attempt and formal gate is closed.
        result = []
        for item in self.items.values():
            ref = item["reference"]
            result.append(self.selector.describe(
                ref["path"], included=True, category=item["category"],
                role="explicit_artifact", expected_sha=ref["sha256"],
                structured_audit=item["structured_audit"]))
        return result


def validate_ledger(package, request, base, formal):
    ledger = package.mapped(request["attempt_ledger"])
    path = Path(ledger["path"])
    require(path.stat().st_size <= 16 * 1024**2, "small_ledger")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ledger["sha256"]
            and raw.endswith(b"\n"), "closed_bound_ledger_bytes")
    records = [base.decode(line) for line in raw.splitlines() if line.strip()]
    require(all(r.get("kind") in ("long_branch", "short_gate") for r in records), "ledger_kinds")
    longs = [r for r in records if r["kind"] == "long_branch"]
    require(len(longs) == request["expected_long_attempts"]
            and len({r["name"] for r in longs}) == len(longs)
            and sum(r["kind"] == "short_gate" for r in records) <= 24, "final_actual_attempt_counts")
    runs = {r["name"]: r for r in request["runs"]}
    require(set(runs) == {r["name"] for r in longs}, "every_long_attempt_retained")
    closures = {}
    for record in longs:
        row = runs[record["name"]]
        require(record["plan_sha256"] == row["plan"]["sha256"], "ledger_plan_sha")
        receipt = package.read(row["receipt"])
        formal.terminal(receipt, row["plan"])
        process = receipt.get("process") or {}
        complete_owned = (process.get("status") == "exited" and type(process.get("exitcode")) is int
                          and process["exitcode"] == 0 and receipt["status"] == "complete"
                          and process.get("windows_job_kill_on_close") is True
                          and process.get("child_released_only_after_job_assignment") is True)
        closures[row["name"]] = {"status": receipt["status"], "process": process,
            "successful_owned_closure": complete_owned,
            "primary_cost_allowed_by_closure_only": complete_owned,
            "closure_scope": ("complete producer owned-process receipt"
                              if complete_owned else "producer terminal declaration; failed/unknown owned evidence retained"),
            "scientific_pass_inferred": False}
    return closures


def validate_training(package, request, base, formal, unlocked):
    train = request["training"]
    require(train["spi_freeze"] == unlocked["spi_freeze"]
            and train["round1_collection"] == unlocked["round1_collection"], "training_unlock_same_refs")
    frozen = package.read(train["spi_freeze"])
    stage = package.read(train["stage_freeze"])
    require(stage["schema"] == formal.STAGE_SCHEMA + ".training_frozen"
            and stage["status"] == "first_round_learning_and_rule_champions_frozen"
            and stage["spi_freeze"] == train["spi_freeze"] and stage["rule"] == unlocked["rule"]
            and stage["test_opened"] is False and stage["second_round_fit_calls"] == 0, "actual_stage_freeze")
    registration = package.read(stage["registration"])
    require(registration["collection"] == train["round0_collection"], "round0_registration_binding")
    execution = package.read(train["execution_receipt"])
    process = execution.get("process") or {}
    require(execution["status"] == "complete_frozen"
            and execution["frozen_stage"] == train["stage_freeze"]
            and execution["spi_freeze"] == train["spi_freeze"]
            and process.get("status") == "exited" and type(process.get("exitcode")) is int
            and process["exitcode"] == 0 and process.get("windows_job_kill_on_close") is True
            and process.get("child_released_only_after_job_assignment") is True
            and execution["actual_fit_counts"] == {"started": 6, "completed": 6},
            "actual_six_fit_owned_execution")
    for key in ("request", "admission", "child_report"):
        package.mapped(execution[key])
    package.mapped(package.read(execution["child_report"])["events"])
    candidates, expected_event_paths = [], set()
    for model in frozen["models"]:
        receipt = package.read(model["chain_receipt"])
        expected_event_paths.add(base.original_key(str(Path(model["chain_receipt"]["path"]).parent
                                                       / "fit_events.jsonl")))
        require(receipt["fit_calls_started"] == receipt["fit_calls_completed"] == 3
                and len(receipt["model_candidates"]) == 4, "three_fits_plus_reference_per_variant")
        reference_count = 0
        for ref in receipt["model_candidates"]:
            value = package.read(ref)
            require(value["model_id"] == ref["model_id"] ==
                    base.digest({k: v for k, v in value.items() if k != "model_id"})
                    and value["information_variant"] == model["information_variant"]
                    and value["schema"] == "g31.foundation.airport_supported_difference_ranker.v1"
                    and value["contract"] == frozen["contract"],
                    "all_candidate_model_identities")
            require(type(value["reference_champion"]) is bool, "candidate_reference_flag")
            reference_count += int(value["reference_champion"])
            candidates.append(ref)
        require(reference_count == 1, "one_reference_three_fitted_candidates")
    require(len({refkey(r)[0] for r in candidates}) == 8, "six_fitted_two_reference_artifacts")
    require({base.original_key(r["path"]) for r in train["fit_events"]} == expected_event_paths,
            "exact_two_actual_chain_event_paths")
    for ref in train["fit_events"]:
        package.mapped(ref)
    campaign = package.read(frozen["campaign"])
    collections = []
    for round_id, key, pair_count in ((0, "round0_collection", 24), (1, "round1_collection", 12)):
        value = package.read(train[key])
        require(value["schema"] == formal.STAGE_SCHEMA + ".collection"
                and value["status"] == "all_registered_attempts_collected"
                and value["rollout_round"] == round_id and value["registered_pairs"] == pair_count
                and value["registered_arms"] == value["closed_attempt_receipts"] == pair_count * 2
                and len(value["inputs"]) == pair_count and value["test_opened"] is False
                and value["second_round_training_authorized"] is False, "complete_bound_collection")
        for row in value["inputs"]:
            package.mapped(row["dataset"])
            for key in ("reference_plan", "patched_plan"):
                package.mapped(row[key])
        if round_id == 0:
            require(campaign["train_inputs"] == value["train_inputs"]
                    and campaign["dev_inputs"] == value["dev_inputs"], "same_actual_round0_training_data")
        collections.append({"round": round_id, "pairs": pair_count})
    return {"fit_calls_completed": 6, "model_artifacts": 8, "collections": collections,
            "models_refit": False, "development_selection_recomputed": False}


def preflight(request_ref):
    selector, base, formal = helpers()
    path = approved_path(request_ref["path"], selector)
    refkey(request_ref)
    require(path.stat().st_size <= selector.MAX_SMALL and sha(path) == request_ref["sha256"],
            "bound_small_final_request")
    request = base.decode(path.read_bytes())
    validate_request_shape(request)
    spec_ref = request["allowlist_request"]
    spec_path = approved_path(spec_ref["path"], selector)
    require(spec_path.stat().st_size <= selector.MAX_SMALL and sha(spec_path) == spec_ref["sha256"],
            "bound_small_allowlist_request")
    spec = base.decode(spec_path.read_bytes())
    require(spec["formal_unlock"] == request["formal"]["unlock"], "same_allowlist_unlock")
    registered = spec["registered_run_slots"]
    require(len(registered) == len(request["runs"])
            and {(r["slot_id"], r["role"], refkey(r["plan"])) for r in registered} ==
            {(r["name"], r["role"], refkey(r["plan"])) for r in request["runs"]},
            "same_full_explicit_allowlist_run_roster")
    package = ExplicitFiles(spec, request, selector, base)
    package.add(request_ref, "registration")
    package.add(spec_ref, "registration")
    # No formal plan or raw result has been opened at this point.
    closures = validate_ledger(package, request, base, formal)
    roster, unlocked, slots, receipts, freeze = formal.unlock_graph(package, base, request["formal"])
    for ref in request["administrative_artifacts"]:
        package.mapped(ref)
    for row in request["superseded_manifests"]:
        require(row.get("scope") and row.get("status"), "superseded_scope_not_actual_run")
        package.mapped(row["reference"])
        package.mapped(row["replacement"])
    package.mapped(request["gate_basis"]["implementation_review"])
    require(request["formal"]["gate_implementation"]["sha256"] == formal.GATE_SHA, "fixed_gate_sha")
    package.mapped(request["formal"]["gate_implementation"])
    training = validate_training(package, request, base, formal, unlocked)
    all_runs = {r["name"]: r for r in request["runs"]}
    for row in request["runs"]:
        plan = package.read(row["plan"])
        require(plan["name"] == row["name"], "actual_run_name")
        for key in ("input", "binary", "source_bundle", "native_acceptance",
                    "forecast_binding", "event_calibration", "model", "rule"):
            if plan.get(key):
                package.mapped(plan[key])
        for key in ("final_result", "evaluation", "branch_evidence"):
            if row.get(key):
                package.mapped(row[key])
        if closures[row["name"]]["status"] == "complete":
            require(row.get("final_result") and row.get("evaluation"), "complete_raw_and_evaluation_required")
    caches = {}
    for entry in roster["plans"]:
        slot = slots[base.original_key(entry["plan"]["path"])]
        parent_row = all_runs[slot["name"]]
        require(parent_row["plan"] == slot["plan"] and parent_row["receipt"] == slot["receipt"],
                "formal_all_run_identity")
        for key in ("final_result", "evaluation"):
            require(parent_row.get(key) == slot.get(key), "same_formal_raw_refs")
        plan = formal.plan_binding(package, base, roster, unlocked, entry, slot)
        cache, _ = formal.cache_binding(package, base, request["formal"], entry, slot, plan)
        if receipts[slot["name"]]["status"] != "complete":
            require(cache["status"] == "blocked" and cache["row"]["full_window_cost"] is None
                    and cache["row"]["backlog_relief"] is None, "failed_formal_primary_null")
        caches[slot["name"]] = cache
    grid = package.read(request["formal"]["grid_audit"])
    effects = package.read(request["formal"]["effects"])
    expected = {row["name"]: row["cache"] for row in request["formal"]["runs"]}
    require(grid["source_manifest"] == effects["source_manifest"] == request["formal"]["roster"]
            and grid["source_cached_audits"] == effects["source_cached_audits"] == expected
            and len(grid["rows"]) == 40 and len({r["name"] for r in grid["rows"]}) == 40
            and all(row == caches[row["name"]]["row"] for row in grid["rows"]),
            "all_forty_cached_gate_basis")
    for value in (grid, effects):
        require(any(r["sha256"] == formal.GATE_SHA for r in value["implementation"]), "grid_effects_fixed_gate")
        for ref in value["implementation"]:
            package.mapped(ref)
    # This verifies every original byte, including complete raw files, only now.
    included = package.validate_included()
    return request, package, included, {"native_closures": closures, "training": training,
        "freeze": freeze, "formal_terminal_cells": 40,
        "formal_numerical_audit_still_required": True, "scientific_promotion_authorized": False}


def dump_new(path, value):
    with Path(path).open("x", encoding="utf8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write("\n")


def build(request_ref, *, output):
    """Explicit root call after actual formal closure; ordinary copies only."""
    output = Path(output).resolve()
    require(output.is_relative_to(HERE) and not output.exists(), "fresh_report_support_package")
    request, package, included, checks = preflight(request_ref)
    require(all(not output.is_relative_to(Path(r["path"])) and not Path(r["path"]).is_relative_to(output)
                for r in included), "output_cannot_contain_or_replace_input")
    output.mkdir(exist_ok=False)
    (output / "objects").mkdir()
    files, mapping = {}, []
    for row in included:
        destination = "objects/" + row["sha256"]
        if destination not in files:
            shutil.copyfile(row["path"], output / destination)
            require((output / destination).stat().st_size == row["bytes"]
                    and sha(output / destination) == row["sha256"], "copied_original_bytes")
            files[destination] = {"package_path": destination, "sha256": row["sha256"], "bytes": row["bytes"]}
        mapping.append({"original_path": row["path"], "package_path": destination,
                        "sha256": row["sha256"], "category": row["category"]})
    manifest = {"schema": package.base.SCHEMA, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "All bound actual native long attempts retained, including failures; formal numerical audit pending.",
        "files": list(files.values()), "original_path_map": mapping, "runs": request["runs"],
        "comparisons": request.get("comparisons", []),
        "training_freezes": [request["training"]["spi_freeze"]], "training": request["training"],
        "formal": request["formal"], "formal_unlock": request["formal"]["unlock"],
        "gate_basis": request["gate_basis"], "attempt_ledger": request["attempt_ledger"],
        "administrative_artifacts": request["administrative_artifacts"],
        "superseded_manifests": request["superseded_manifests"],
        "excluded_large_logs": request["excluded_large_logs"],
        "excluded_log_scope": "Explicit producer/cache SHA references only; excluded content not read or copied by builder.",
        "missing_optional_small_artifacts": [],
        "native_binary_unique_hashes": sorted({r["sha256"] for r in mapping
                                               if r["original_path"].lower().endswith(".pyd")}),
        "builder_request": request_ref, "builder": reference(__file__),
        "preflight": checks, "root_roster_completeness_certified": True,
        "native_operations": 0, "fit_operations": 0, "git_operations": 0,
        "independent_numerical_audit_completed_by_builder": False,
        "engineering_promotion_authorized": False, "protected_takeover_authorized": False}
    dump_new(output / "PACKAGE_MANIFEST.json", manifest)
    return {"schema": SCHEMA + ".result", "status": "built_pending_independent_audit",
        "package": str(output), "manifest": reference(output / "PACKAGE_MANIFEST.json"),
        "registered_native_long_attempts": len(request["runs"]), "formal_cells": 40,
        "unique_files": len(files), "path_mappings": len(mapping),
        "unique_bytes": sum(row["bytes"] for row in files.values()),
        "native_binary_versions": len(manifest["native_binary_unique_hashes"]),
        "failed_copy_policy": "partial package remains; never automatically delete or reuse",
        "required_next_step": "Run pinned audit_compact_formal_002.py with pinned base validator in a separate isolated process."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build({"path": str(args.request.resolve()), "sha256": args.request_sha256}, output=args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
