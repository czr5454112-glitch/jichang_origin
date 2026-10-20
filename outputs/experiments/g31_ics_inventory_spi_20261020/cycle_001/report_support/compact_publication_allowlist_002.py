"""Artifact-only exact allowlist selector. It never copies files or runs Git.

Root supplies explicit bound references from the final registered roster. No
directory glob discovers untracked files. Absent/failed registered arms remain
in the index. Large histories stay local; optional streaming SHA is separately
reported and does not claim gzip CRC or semantic replay.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path.insert(0, str(ROOT))
SCHEMA = "g31.inventory_spi.compact_publication_allowlist.v2"
MAX_SMALL = 16 * 1024**2
MAX_STRUCTURED_AUDIT = 64 * 1024**2
# Exact raw-history names only: legitimate report names may mention controller.
RAW_HISTORY_NAMES = {
    "control_records.json", "controller_final_state.json", "ack_views.json",
    "callback_audit.json", "callback_audit.jsonl", "client_calls.json",
    "inventory_snapshot_reads.json", "warmup_prefix.json", "activation_prefix.json",
    "final_result.json",
}
LARGE_LOCAL = ("control_records.json.gz", "controller_final_state.json.gz",
               "ack_views.json.gz", "callback_audit.jsonl.gz",
               "warmup_prefix.json.gz", "activation_prefix.json.gz",
               "inventory_snapshot_reads.json.gz")
RUN_SMALL = ("plan.json", "receipt.json", "worker_report.json", "evaluation.json",
             "callback_audit_receipt.json", "planner_summary.json",
             "actual_plan_preload_receipts.json", "source_verification.json")
CATEGORIES = {"report", "registration", "review", "receipt", "test_receipt",
              "model", "curve", "dataset", "input", "ledger", "validator"}


def require(ok, reason):
    if not ok:
        raise ValueError("publication_allowlist:"+reason)


def path_in_workspace(value):
    path = Path(value).resolve()
    require(path.is_relative_to(ROOT), "workspace_reference_only")
    parts = set(path.parts)
    require(not any("DUMMY" in p or p.startswith("T06_fixture_tmp") for p in parts)
            and not parts.intersection({".git", "__pycache__", ".pytest_cache"}),
            "no_dummy_cache_or_git_files")
    return path


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_small(path):
    path = path_in_workspace(path)
    require(path.stat().st_size <= MAX_SMALL, "metadata_size_limit")
    return json.loads(path.read_text(encoding="utf-8"))


def bound(reference):
    path = path_in_workspace(reference["path"])
    require(sha(path) == reference["sha256"], "bound_reference_sha256")
    return read_small(path)


def validate_structured_audit(path, declaration, *, included, category, role, expected_sha):
    """An explicit, bounded report exception; never a raw-history exception."""
    require(included and category in ("report", "review") and role == "explicit_artifact",
            "structured_audit_only_explicit_report_or_review")
    require(isinstance(declaration, dict) and set(declaration) == {"schema", "max_bytes"},
            "structured_audit_exact_declaration")
    maximum = declaration["max_bytes"]
    require(type(maximum) is int and 0 < maximum <= MAX_STRUCTURED_AUDIT,
            "structured_audit_maximum_64MiB")
    require(isinstance(declaration["schema"], str) and declaration["schema"],
            "structured_audit_expected_schema")
    require(path.suffix.lower() == ".json" and path.name.lower() not in RAW_HISTORY_NAMES
            and path.name.lower() not in {name.lower() for name in LARGE_LOCAL},
            "structured_audit_not_raw_history_or_non_json")
    require(isinstance(expected_sha, str) and len(expected_sha) == 64
            and all(c in "0123456789abcdef" for c in expected_sha),
            "structured_audit_exact_sha_required")
    require(path.is_file() and path.stat().st_size <= maximum, "structured_audit_size_limit")
    actual = sha(path)
    require(actual == expected_sha, "listed_original_sha256")
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict) and value.get("schema") == declaration["schema"],
            "structured_audit_exact_schema")
    return {"schema": value["schema"], "declared_max_bytes": maximum,
            "maximum_supported_bytes": MAX_STRUCTURED_AUDIT,
            "actual_sha256": actual, "validation": "original_bytes_sha_and_declared_root_schema"}


def describe(path, *, included, category, role, hash_large=False, expected_sha=None,
             structured_audit=None):
    path = path_in_workspace(path)
    if not path.exists():
        require(structured_audit is None, "structured_audit_bound_file_required")
        return {"path": str(path), "included": False, "category": category, "role": role,
                "status": "missing_registered_file", "hash_verified": False}
    size = path.stat().st_size
    require(path.is_file(), "files_only")
    structured = None
    if structured_audit is not None:
        structured = validate_structured_audit(
            path, structured_audit, included=included, category=category,
            role=role, expected_sha=expected_sha)
    if included:
        maximum = structured_audit["max_bytes"] if structured is not None else MAX_SMALL
        require(path.name not in LARGE_LOCAL and size <= maximum,
                "large_history_or_large_file_cannot_enter_compact_copy_allowlist")
    actual = structured["actual_sha256"] if structured is not None else (sha(path) if included or hash_large else None)
    if expected_sha is not None and actual is not None:
        require(actual == expected_sha, "listed_original_sha256")
    return {"path": str(path), "workspace_relative_path": path.relative_to(ROOT).as_posix(),
            "included": included, "category": category, "role": role, "bytes": size,
            "sha256": actual, "declared_expected_sha256": expected_sha,
            "hash_verified": actual is not None,
            "structured_audit_validation": structured,
            "status": "hash_verified" if actual else "listed_only",
            "excluded_reason": None if included else "large evidence retained at exact local path",
            "gzip_CRC_and_semantics_verified_by_this_selector": False}


def select(spec, *, hash_local_large=False):
    require(spec["schema"] == SCHEMA+".request", "request_schema")
    require(spec.get("template_not_final") is False, "root_must_finalize_explicit_request")
    expected = spec["registered_run_slots"]
    require(expected and len(expected) == len({r["slot_id"] for r in expected})
            and len({str(path_in_workspace(r["plan"]["path"])) for r in expected}) == len(expected),
            "nonempty_unique_registered_slots_and_plans")
    if any(r["role"] == "formal" for r in expected):
        from scripts.experiments.g31_ics_circulation.foundation_airport_inventory_spi_campaign import validate_formal_unlock
        validate_formal_unlock(spec["formal_unlock"])  # Before any formal plan/result read.
    items, runs, source_map = [], [], []
    for requested in spec["compact_artifacts"]:
        category = requested["category"]
        require(category in CATEGORIES, "explicit_compact_artifact_category")
        reference = requested["reference"]
        items.append(describe(reference["path"], included=True, category=category,
                              role="explicit_artifact", expected_sha=reference["sha256"],
                              structured_audit=requested.get("structured_audit")))
    for entry in expected:
        require(entry["role"] in ("diagnostic", "failed_attempt", "round0_pair", "round1_pair", "formal"),
                "explicit_registered_run_role")
        plan_ref = entry["plan"]
        directory = path_in_workspace(plan_ref["path"]).parent
        closure_path = directory/"receipt.json"
        if not closure_path.exists():
            runs.append({"slot_id": entry["slot_id"], "role": entry["role"],
                         "plan": plan_ref, "status": "registered_without_closed_receipt",
                         "outcomes_opened": False})
            continue
        closure = read_small(closure_path)
        process = closure.get("process", {})
        closed = (closure.get("status") not in (None, "running", "prepared", "pending")
                  and process.get("status") in ("exited", "hard_timeout")
                  and process.get("exitcode") is not None)
        require(closed and closure["plan_sha256"] == plan_ref["sha256"],
                "closed_terminal_receipt_bound_to_plan_before_files")
        plan = bound(plan_ref)
        require((entry["role"] == "formal") == (plan["parent"]["parent_seed"] in range(1301, 1309)),
                "formal_role_cannot_bypass_unlock")
        if entry["role"] == "formal":
            require(plan["formal_unlock"] == spec["formal_unlock"], "same_formal_unlock")
        run = {"slot_id": entry["slot_id"], "role": entry["role"], "plan": plan_ref,
               "name": plan["name"], "status": closure["status"], "process": process,
               "parent": plan["parent"], "input": plan["input"], "binary": plan["binary"],
               "source_bundle": plan["source_bundle"], "model": plan.get("model"),
               "failed_or_censored_preserved": closure["status"] != "complete"}
        runs.append(run)
        for name in RUN_SMALL:
            items.append(describe(directory/name, included=True, category="run_metadata",
                                  role=entry["slot_id"]))
        # Small raw final results remain independently recomputable. Failed
        # runs may have no result; absence remains explicit instead of excluded.
        items.append(describe(directory/"final_result.json.gz", included=True,
                              category="raw_final_result", role=entry["slot_id"]))
        for name in LARGE_LOCAL:
            items.append(describe(directory/name, included=False, category="local_large_evidence",
                                  role=entry["slot_id"], hash_large=hash_local_large))
    for reference in spec["source_manifests"]:
        manifest = bound(reference)
        root = path_in_workspace(manifest["root"])
        items.append(describe(reference["path"], included=True, category="source_manifest",
                              role="frozen_source", expected_sha=reference["sha256"]))
        for relative, expected_sha in sorted(manifest["files"].items()):
            source = path_in_workspace(root/relative)
            require(source.is_relative_to(root), "source_relative_path_cannot_escape")
            item = describe(source, included=True, category="source", role="frozen_source",
                            expected_sha=expected_sha)
            require(item["status"] == "hash_verified", "frozen_source_file_required")
            item["content_store_key"] = "source_store/"+expected_sha+source.suffix
            items.append(item)
            source_map.append({"source_manifest": reference, "original_relative_path": relative,
                               "content_store_key": item["content_store_key"], "sha256": expected_sha})
    unique = {}
    for item in items:
        key = item["path"]
        if key in unique:
            prior = unique[key]
            require(all(prior[k] == item[k] for k in ("included", "status", "sha256") if k in prior and k in item),
                    "consistent_duplicate_path")
            prior.setdefault("also_used_by", []).append(item["role"])
        else:
            unique[key] = item
    items = list(unique.values())
    return {"schema": SCHEMA, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "allowlist_selection_only_no_copy_or_git",
        "registered_run_slot_count": len(expected), "runs": runs,
        "run_status_counts": dict(Counter(r["status"] for r in runs)),
        "files": items, "source_restore_map": source_map,
        "included_bytes_before_source_content_dedup": sum(r.get("bytes", 0) for r in items if r["included"]),
        "registered_roster_completeness_certified": False,
        "roster_limit": "root must bind these explicit slots to the final 24/12 roots, 40 formal cells, diagnostics and all attempts",
        "large_evidence_stream_hash_requested": hash_local_large,
        "copied_files": 0, "native_operations": 0, "fit_operations": 0,
        "git_operations": 0, "arbitrary_untracked_directory_scan": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--spec-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--hash-local-large", action="store_true")
    args = parser.parse_args()
    spec = bound({"path": str(args.spec), "sha256": args.spec_sha256})
    result = select(spec, hash_local_large=args.hash_local_large)
    result["request"] = {"path": str(args.spec.resolve()), "sha256": args.spec_sha256}
    result["selector"] = {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)}
    output = path_in_workspace(args.output)
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
