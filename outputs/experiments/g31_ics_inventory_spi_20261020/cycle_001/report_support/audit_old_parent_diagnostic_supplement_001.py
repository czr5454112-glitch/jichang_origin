"""Package-only supplement for nine exact historical diagnostic plans.

This does not replace, rerun or repair the frozen overall blocked audit. Only
SHA-pinned validator modules from the outer ZIP execute; archived project code
and original absolute paths are never imported/opened. Standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import types
import zipfile

SCHEMA = "g31.inventory_spi.old_parent_diagnostic_supplement.v1"
ADMISSION_SCHEMA = SCHEMA + ".admission"
ZIP_SHA = "59bd99f72da9031079540fccc24fb9083f6ebf700ffbb2004f2b0712e4f28a1d"
ZIP_BYTES = 314360446
MANIFEST_SHA = "bb470b50b969fc1bfba89fdee123b3dfb8cc55b2d5f1995485755df6e27f1fc0"
PARTIAL_PACKAGE_SCHEMA = "g31.inventory_spi.partial_compact_publication.v1.package"
FROZEN_BLOCKED_REPORT_SHA = "11c4be3b348964ce8edf7cafe7425df65a5a17090dd777453c0e784139cd61d6"
VALIDATORS = {
    "compact_partial_publication_001.py": "4a15bf00003063fdf6a35ce566e733e322a08b76a7b48b82369eec6057f5501b",
    "build_final_compact_publication_002.py": "60a64acb9630d0a54818e4b65fa13d1ca33a23e631b77cb834feafa121e36c9a",
    "compact_publication_allowlist_002.py": "c0738c470ac26eea8bad2b0f96b57b3174e6e994aee6e575baf7458505428342",
    "audit_compact_publication_001.py": "7d60b20c1a4cdcee63b79f9477c96f6764e15e4908facd714b0e4fa45121271a",
    "audit_compact_formal_002.py": "edb69cc0481858bed7cca9cd04d9a6b2e704d452839600aed90081a138653db4",
    "audit_compact_nonformal_001.py": "38f1929958bddfa1e3e18f80329e686fa8a8870e19f966e3863b7acc6c14f4c3",
}
# name -> (exact original plan SHA, parent seed). No name pattern admission.
PLANS = {
    "D_N22_C00_P901_REC1_002": ("f33798cb4121eb400b7767eecccccd2a81e37a2d3b3d75a41d2c477f2922a643", 901),
    "D_N22_C00_P901_REC1_004": ("9b3e292c5b0250c435820c1e8cbcaeae5975ea867b7fdf7f9ab9b4a452377b71", 901),
    "D_N22_R0_P901_REC1_004": ("f1ff9c25573955a4ac1889646f76bf2e6834135a0c86b1830af9033973c204ac", 901),
    "D_N22_R0_P902_REC1_005": ("662751bb984332a7ff7308a2d1688df5f63ebd41cd5823549dbc8e8275b5774b", 902),
    "D_N22_C00_P902_REC1_005": ("9cb6449f497ee1d218ae04c15a5dc4c5b95f690cef14d275025743a06591f6f4", 902),
    "D_N26_C00_P901_REC0_005": ("677654c2858c4e215eccf9554086be31c444faebd4a7efe94fa70a72e1e8cfd5", 901),
    "D_N26_C00_P901_REC1_005": ("d4f85dad26cff3415b4f2ead1e49f377ef043bc51276e8351932e1f30a2c711b", 901),
    "D_N26_C00_P902_REC0_005": ("7797f1cfcac3a1b5ff3d7037fa2d5c44bf25e873b8fed28afa59d8529a8d1f53", 902),
    "D_N26_C00_P902_REC1_005": ("ce3cd8448630e1b36886b850a7ebf4846f17f770fabbdd678963d7192047bed4", 902),
}


def require(ok, reason):
    if not ok:
        raise ValueError("old_diagnostic_supplement:" + reason)


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def admission_document():
    return {
        "schema": ADMISSION_SCHEMA, "outer_zip_sha256": ZIP_SHA,
        "outer_zip_bytes": ZIP_BYTES, "manifest_sha256": MANIFEST_SHA,
        "frozen_blocked_report_sha256": FROZEN_BLOCKED_REPORT_SHA,
        "validators": VALIDATORS,
        "plans": [{"name": name, "plan_sha256": sha, "parent_seed": seed,
                   "role": "diagnostic", "split": "test", "pair": None,
                   "old_parent_diagnostic_only": True}
                  for name, (sha, seed) in PLANS.items()],
        "uses": ["old_parent_diagnostic_only"],
        "formal_outcomes_allowed": False, "training_or_selection_allowed": False,
        "original_frozen_status": "blocked_invalid_evidence",
        "scope": "Supplement nine exact historical diagnostics only; do not replace frozen overall audit status.",
    }


def validate_admission(value):
    require(value == admission_document(), "exact_nine_plan_admission_contract")


def validate_plan(slot, plan):
    name = slot.get("name")
    require(name in PLANS and slot.get("role") == "diagnostic", "exact_registered_diagnostic")
    sha, seed = PLANS[name]
    require(slot["plan"]["sha256"] == sha and plan.get("name") == name,
            "original_exact_plan_identity")
    require(plan.get("pair") is None and plan.get("old_parent_diagnostic_only") is True,
            "explicit_old_diagnostic_only_no_pair")
    require(type(plan["parent"]["parent_seed"]) is int
            and plan["parent"]["parent_seed"] == seed
            and seed in (901, 902) and plan["parent"]["split"] == "test",
            "old_901_902_only_no_new_formal")
    require(plan["method"] in ("C00", "R0_current_stock_v1"), "old_diagnostic_methods_only")


def load_validators(archive):
    raw = {name: archive.read("validators/" + name) for name in VALIDATORS}
    for name, data in raw.items():
        require(hashlib.sha256(data).hexdigest() == VALIDATORS[name], "pinned_zip_validator:" + name)
    loaded = []
    for name in ("audit_compact_publication_001.py", "audit_compact_nonformal_001.py"):
        module = types.ModuleType("supplement_pinned_" + name[:-3])
        module.__file__ = "ZIP/validators/" + name
        exec(compile(raw[name], module.__file__, "exec"), module.__dict__)
        loaded.append(module)
    return tuple(loaded)


def outer_package(base, nonformal, path):
    # Reuse unchanged mapped-object/hash logic with a literal outer ZIP prefix.
    class PrefixedPackage(base.Package):
        def raw(self, name):
            return super().raw("evidence/" + base.safe_name(name))
    facade = types.SimpleNamespace(**base.__dict__)
    facade.Package = PrefixedPackage
    facade.SCHEMA = PARTIAL_PACKAGE_SCHEMA
    return nonformal.open_mapped(facade, path, MANIFEST_SHA)


def diagnostic_numeric(package, base, slot, receipt, plan):
    """Original nonformal audit_arm diagnostic numeric chain; no plan rewriting."""
    package.mapped(plan["binary"])
    base.accepted_native(package.read(plan["native_acceptance"]), plan["binary"]["sha256"])
    base.validate_source(package, plan["source_bundle"], plan["source_manifest_sha256"])
    data = package.read(plan["input"])
    require(base.digest(data) == plan["input_semantic_sha256"], "input_semantic_pin")
    result, evaluation = package.read(slot["final_result"]), package.read(slot["evaluation"])
    require(evaluation["status"] == "complete" and evaluation["parent"] == plan["parent"]
            and evaluation["method"] == plan["method"]
            and evaluation["input_semantic_sha256"] == plan["input_semantic_sha256"],
            "evaluation_identity")
    start, end = plan["cost_window"]
    require(start == 7200 and end == 59400 and result["physical_clock"] == end
            == receipt["worker"]["final_physical_time"], "exact_final_cost_endpoint")
    cost, relief, specs, completed = base.metrics(data, result, start, end)
    require(len(specs) == 28506, "complete_historical_population")
    base.same(cost, evaluation["cost"], "saved_cost_evaluation")
    base.same(cost, receipt["worker"]["cost"], "saved_cost_worker")
    return {"name": slot["name"], "role": "diagnostic", "plan": slot["plan"],
            "receipt": slot["receipt"], "status": "old_diagnostic_cost_recomputed",
            "cost": cost, "backlog_relief": relief, "full_population": len(specs),
            "parent": plan["parent"], "method": plan["method"]}, {
                "specs": specs, "completed": completed, "cost": cost, "plan": plan,
                "evaluation": evaluation, "selected": None, "branch": None}


def audit(zip_path, admission_path, admission_sha):
    began = time.perf_counter()
    require(Path(zip_path).stat().st_size == ZIP_BYTES and file_sha(zip_path) == ZIP_SHA,
            "exact_unchanged_outer_zip")
    admission_raw = Path(admission_path).read_bytes()
    require(hashlib.sha256(admission_raw).hexdigest() == admission_sha, "admission_sha")
    with zipfile.ZipFile(zip_path) as archive:
        base, nonformal = load_validators(archive)
    validate_admission(base.decode(admission_raw))
    package = outer_package(base, nonformal, zip_path)
    try:
        # Roster metadata only; do not open any formal or pair plan/outcome.
        slots = [row for row in package.manifest["runs"] if row["role"] == "diagnostic"]
        require(len(slots) == 9 and {r["name"] for r in slots} == set(PLANS), "all_nine_denominator")
        require(len({base.original_key(r["plan"]["path"]) for r in slots}) == 9, "unique_plan_paths")
        for row in slots:
            require(row["plan"]["sha256"] == PLANS[row["name"]][0], "roster_plan_pin")
        # Check every receipt before any input or final result. Keep all failures.
        receipts, closure_errors = {}, {}
        for row in slots:
            try:
                receipt = package.read(row["receipt"])
                nonformal.terminal(base, receipt, row["plan"])
                require(receipt["status"] == "complete", "registered_completed_diagnostic_required")
                receipts[row["name"]] = receipt
            except (ValueError, KeyError, TypeError, OSError, EOFError) as exc:
                closure_errors[row["name"]] = str(exc)
        reports, indices = [], {}
        for slot in slots:
            name = slot["name"]
            try:
                require(name not in closure_errors, "closure:" + closure_errors.get(name, ""))
                plan = package.read(slot["plan"])
                validate_plan(slot, plan)
                row, indices[name] = diagnostic_numeric(package, base, slot, receipts[name], plan)
            except (ValueError, KeyError, TypeError, OSError, EOFError) as exc:
                row = {"name": name, "role": "diagnostic", "plan": slot["plan"],
                       "status": "blocked_old_diagnostic_evidence", "error": str(exc),
                       "cost": None, "backlog_relief": None}
                indices[name] = None
            reports.append(row)
        comparisons = []
        for declared in package.manifest.get("comparisons", []):
            names = (declared["reference"], declared["candidate"])
            require(names[0] != names[1] and all(n in PLANS for n in names), "only_declared_old_diagnostic_comparison")
            require(declared["kind"] in ("R0_vs_C00", "recovery_on_vs_off"), "diagnostic_comparison_kind")
            try:
                require(all(indices[n] is not None for n in names), "comparison_unavailable_arm")
                values = nonformal.compare(base, *(indices[n] for n in names), declared["kind"])
                comparisons.append({**declared, **values, "status": "registered_diagnostic_comparison_verified"})
            except (ValueError, KeyError, TypeError) as exc:
                comparisons.append({**declared, "status": "blocked_old_diagnostic_comparison", "error": str(exc)})
        require(file_sha(zip_path) == ZIP_SHA, "outer_zip_unchanged_after_read")
        blocked = any(r["status"].startswith("blocked") for r in reports + comparisons)
        return {
            "schema": SCHEMA, "status": "blocked_old_diagnostic_supplement" if blocked
            else "nine_old_diagnostic_included_costs_verified_scope_limited",
            "outer_zip_sha256": ZIP_SHA, "manifest_sha256": MANIFEST_SHA,
            "admission_sha256": admission_sha, "auditor_sha256": file_sha(__file__),
            "pinned_validator_sha256": VALIDATORS, "original_frozen_report_sha256": FROZEN_BLOCKED_REPORT_SHA,
            "original_frozen_overall_status": "blocked_invalid_evidence",
            "original_frozen_overall_status_replaced": False, "registered_diagnostics": 9,
            "status_counts": dict(Counter(r["status"] for r in reports)), "runs": reports,
            "declared_diagnostic_comparisons": comparisons, "read_references": package.read_references,
            "scope": "Nine exact old-parent diagnostics only. Receipt/source/native identities and full-population saved costs. No new formal/pair/training outcomes.",
            "source_and_native_scope": "Pinned manifests and mapped identities; no simulator or archived source execution.",
            "physical_or_callback_protection_replay": False, "model_numeric_recomputation": False,
            "all_package_bytes_rehashed": False, "all_accessed_mapped_objects_rehashed": True,
            "formal_algorithm_ranking_allowed": False, "development_selection_authorized": False,
            "engineering_promotion_authorized": False, "protected_takeover_authorized": False,
            "original_absolute_paths_opened": False, "native_operations": 0, "fit_operations": 0,
            "wall_seconds": time.perf_counter() - began,
        }
    finally:
        package.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path)
    parser.add_argument("--admission", type=Path, required=True)
    parser.add_argument("--admission-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists() and args.output.resolve() not in (args.zip.resolve(), args.admission.resolve()), "fresh_output")
    result = audit(args.zip, args.admission, args.admission_sha256)
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "status_counts": result["status_counts"]}, ensure_ascii=False), flush=True)
    raise SystemExit(0 if result["status"] == "nine_old_diagnostic_included_costs_verified_scope_limited" else 2)
