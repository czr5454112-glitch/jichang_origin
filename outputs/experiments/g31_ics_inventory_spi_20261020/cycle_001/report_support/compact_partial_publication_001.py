"""Separate partial publication; explicit CAS copies and portable stdlib audit.

No full-tool constants are changed. The complete 40-slot registration is retained
while the final ledger determines charged attempts. A missing/invalid process
closure never becomes a completed attempt. Partial formal results cannot support
parent means, comparisons, rankings, selection, or deployment authorization.
Only explicitly pinned audit helpers are executed, never archived actor sources.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import types

HERE = Path(__file__).resolve().parent
SCHEMA = "g31.inventory_spi.partial_compact_publication.v1"
HISTORICAL_UNKNOWN_NAME = "D_N22_C00_P901_001"
PINS = {
    "builder": ("build_final_compact_publication_002.py",
                "60a64acb9630d0a54818e4b65fa13d1ca33a23e631b77cb834feafa121e36c9a"),
    "selector": ("compact_publication_allowlist_002.py",
                 "c0738c470ac26eea8bad2b0f96b57b3174e6e994aee6e575baf7458505428342"),
    "base": ("audit_compact_publication_001.py",
             "7d60b20c1a4cdcee63b79f9477c96f6764e15e4908facd714b0e4fa45121271a"),
    "formal": ("audit_compact_formal_002.py",
               "edb69cc0481858bed7cca9cd04d9a6b2e704d452839600aed90081a138653db4"),
    "nonformal": ("audit_compact_nonformal_001.py",
                  "38f1929958bddfa1e3e18f80329e686fa8a8870e19f966e3863b7acc6c14f4c3"),
}
FORMAL_FIELDS = ("receipt", "final_result", "evaluation", "cache", "primary_J")
DENIALS = {
    "formal_algorithm_ranking_allowed": False,
    "engineering_promotion_authorized": False,
    "protected_takeover_authorized": False,
    "development_selection_authorized": False,
    "eight_parent_mean": None,
    "formal_paired_comparisons": None,
}


def require(ok, reason):
    if not ok:
        raise ValueError("partial_publication:" + reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def helpers(directory=HERE):
    loaded = {}
    for name, (filename, expected) in PINS.items():
        path = Path(directory) / filename
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected, "pinned_helper:" + name)
        module = types.ModuleType("partial_pinned_" + name)
        module.__file__ = str(path)
        exec(compile(raw, str(path), "exec"), module.__dict__)
        loaded[name] = module
    return types.SimpleNamespace(**loaded)


def refkey(ref, base):
    require(isinstance(ref, dict) and isinstance(ref.get("sha256"), str)
            and len(ref["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in ref["sha256"]), "bound_ref")
    return base.original_key(ref["path"]), ref["sha256"]


def request_shape(request, h):
    require(request.get("schema") == SCHEMA + ".request"
            and request.get("actual_partial_publication") is True, "explicit_partial_request")
    for name in ("attempt_ledger", "cutoff"):
        refkey(request[name], h.base)
    runs, formal = request["runs"], request["formal"]
    require(82 <= len(runs) <= 122 and request["expected_long_attempts"] == len(runs)
            and len({r["name"] for r in runs}) == len(runs)
            and len({refkey(r["plan"], h.base)[0] for r in runs}) == len(runs),
            "unique_actual_ledger_denominator")
    counts = Counter(r["role"] for r in runs)
    require(counts["round0_pair"] == 48 and counts["round1_pair"] == 24
            and counts["diagnostic"] == 9 and counts["failed_attempt"] == 1
            and set(counts) <= {"round0_pair", "round1_pair", "formal", "diagnostic", "failed_attempt"},
            "complete_eighty_two_nonformal_attempts")
    require([r["name"] for r in runs if r["role"] == "failed_attempt"] == [HISTORICAL_UNKNOWN_NAME],
            "unique_registered_historical_failure")
    slots = formal["runs"]
    require(len(slots) == 40 and len({r["name"] for r in slots}) == 40
            and len({refkey(r["plan"], h.base)[0] for r in slots}) == 40
            and {(r["parent_seed"], r["method"]) for r in slots}
            == {(p, m) for p in h.formal.PARENTS for m in h.formal.METHODS},
            "all_forty_registered_slots_real_method_ids")
    actual = {r["name"]: r for r in runs}
    for slot in slots:
        require(type(slot["started"]) is bool and all(k in slot for k in FORMAL_FIELDS)
                and slot["primary_J"] is None, "explicit_slot_status_and_no_rankable_J")
        if slot["started"]:
            require(slot["name"] in actual and actual[slot["name"]]["role"] == "formal"
                    and all(actual[slot["name"]].get(k) == slot.get(k)
                            for k in ("plan", "receipt", "final_result", "evaluation", "cache")),
                    "same_actual_formal_slot")
        else:
            require(slot["name"] not in actual and all(slot[k] is None for k in FORMAL_FIELDS),
                    "unstarted_has_no_receipt_raw_cache_or_cost")
    require({r["name"] for r in runs if r["role"] == "formal"}
            == {r["name"] for r in slots if r["started"]}, "exact_started_formal_set")
    require("grid_audit" not in formal and "effects" not in formal,
            "partial_has_no_full_grid_or_effects")
    for name in ("roster", "unlock", "gate_implementation"):
        refkey(formal[name], h.base)
    require(formal["gate_implementation"]["sha256"] == h.formal.GATE_SHA, "fixed_physical_gate")
    require(request.get("claims") == DENIALS, "explicit_no_promotion_no_means_no_ranking")
    return counts


def classify_receipt(receipt, plan, formal):
    if receipt is None:
        return {"status": "closure_unknown_missing_receipt", "owned_complete": False,
                "terminal_verified": False, "process": None}
    require(receipt.get("plan_sha256") == plan["sha256"], "receipt_actual_plan_binding")
    try:
        formal.terminal(receipt, plan)
        process = receipt.get("process") or {}
        require(type(process.get("exitcode")) is int
                and process.get("windows_job_kill_on_close") is True
                and process.get("child_released_only_after_job_assignment") is True,
                "all_terminal_attempts_require_actual_exit_and_owned_flags")
    except (KeyError, TypeError, ValueError) as exc:
        return {"status": "closure_unknown_unverified", "owned_complete": False,
                "terminal_verified": False, "process": receipt.get("process"),
                "producer_status": receipt.get("status"), "reason": str(exc)}
    return {"status": "complete_owned" if receipt["status"] == "complete" else "terminal_failed",
            "owned_complete": receipt["status"] == "complete", "terminal_verified": True,
            "process": receipt.get("process"), "producer_status": receipt["status"]}


def metadata_gate(package, request, h):
    """Before any plan/input/outcome read: ledger, cutoff, roster and receipts only."""
    request_shape(request, h)
    cutoff = package.read(request["cutoff"])
    require(cutoff.get("schema") == SCHEMA + ".cutoff"
            and cutoff.get("status") == "publication_snapshot_frozen"
            and cutoff.get("no_further_native_launches") is True
            and isinstance(cutoff.get("reason"), str) and cutoff["reason"].strip()
            and cutoff["attempt_ledger"] == request["attempt_ledger"]
            and cutoff["formal_roster"] == request["formal"]["roster"],
            "explicit_final_partial_snapshot_declaration")
    raw = package.raw_reference(request["attempt_ledger"])
    require(raw.endswith(b"\n"), "ledger_complete_line_tail")
    ledger = [h.base.decode(line) for line in raw.splitlines() if line.strip()]
    require(all(r.get("kind") in ("long_branch", "short_gate") for r in ledger)
            and sum(r["kind"] == "short_gate" for r in ledger) == 24, "fixed_short_ledger_denominator")
    longs = [r for r in ledger if r["kind"] == "long_branch"]
    require(len(longs) == len(request["runs"]) and len({r["name"] for r in longs}) == len(longs)
            and {(r["name"], r["plan_sha256"]) for r in longs}
            == {(r["name"], r["plan"]["sha256"]) for r in request["runs"]},
            "final_ledger_exact_actual_attempts")
    roster = package.read(request["formal"]["roster"])
    require(roster["schema"] == h.formal.STAGE_SCHEMA + ".formal_batch"
            and roster["registered_parents"] == 8 and roster["registered_arms"] == 40
            and roster["test_inputs_generated_after_champion_freeze"] is True
            and roster["test_outcomes_opened"] is False
            and roster["formal_unlock"] == request["formal"]["unlock"], "registered_formal_roster")
    expected = {(r["parent_seed"], r["method"], refkey(r["plan"], h.base)) for r in roster["plans"]}
    require(len(roster["plans"]) == len(expected) == 40 and expected
            == {(r["parent_seed"], r["method"], refkey(r["plan"], h.base))
                for r in request["formal"]["runs"]}, "exact_forty_roster_pins")
    receipts, closure = {}, {}
    for row in request["runs"]:
        receipt = package.read(row["receipt"]) if row.get("receipt") is not None else None
        checked = classify_receipt(receipt, row["plan"], h.formal)
        if row["role"] not in ("formal", "failed_attempt"):
            require(checked["terminal_verified"], "all_nonformal_attempts_terminal")
        if row["role"] == "failed_attempt" and not checked["terminal_verified"]:
            require(row["name"] == HISTORICAL_UNKNOWN_NAME and receipt is not None
                    and receipt.get("status") == "unknown_hard_stop",
                    "only_named_historical_unknown_exception")
        if not checked["owned_complete"] and row["role"] in ("formal", "failed_attempt"):
            require(all(row.get(k) is None for k in ("final_result", "evaluation", "branch_evidence", "cache")),
                    "failed_or_unverified_formal_closure_has_no_raw_or_cache")
        receipts[row["name"]], closure[row["name"]] = receipt, checked
    return roster, receipts, closure


def training_graph(package, request, roster, h):
    """Frozen graph validation without the full tool's 40-terminal assumption."""
    unlocked = package.read(request["formal"]["unlock"])
    require(unlocked["schema"] == h.formal.RUN_SCHEMA + ".formal_unlock"
            and unlocked["status"] == "all_champions_frozen_test_unlocked"
            and unlocked["test_parent_ids"] == list(h.formal.PARENTS)
            and unlocked["test_outcomes_used_for_selection"] is False, "legal_formal_unlock")
    freeze = h.base.validate_freeze(package, unlocked["spi_freeze"])
    frozen = package.read(unlocked["spi_freeze"])
    require(frozen["contract"]["policy_alignment"] == {
        "behavior_policy_id": h.formal.PI0, "continuation_policy_id": h.formal.PI0,
        "improvement_round": 0, "max_policy_replacements": 1, "label_horizon_seconds": 1800.},
        "one_frozen_policy_improvement")
    models = {r["information_variant"]: r["checkpoint"] for r in frozen["models"]}
    require(models == unlocked["models"], "same_frozen_selected_models")
    shared = roster["shared"]
    require(all(shared[k] == unlocked[k] for k in ("source_bundle", "native_acceptance", "preregistration")),
            "shared_unlock_bindings")
    source = package.read(shared["source_bundle"])
    h.base.validate_source(package, shared["source_bundle"], source["source_manifest_sha256"])
    native = package.read(shared["native_acceptance"])
    h.base.accepted_native(native, native["binary"]["sha256"])
    package.mapped({"path": shared["binary"], "sha256": native["binary"]["sha256"]})
    registration = package.read(shared["preregistration"])
    require(registration["schema"] == h.formal.RUN_SCHEMA + ".registration"
            and package.read(registration["learning_contract"]) == frozen["contract"],
            "registered_learning_contract")
    runtime = package.read(registration["runtime_shared"])
    require(all(runtime.get(k) == shared.get(k) for k in (
        "binary", "source_bundle", "native_acceptance", "soft_seconds", "hard_seconds", "calibration")),
        "registered_runtime")
    package.mapped(registration["contract_document"])
    package.mapped(registration["budget"])
    registry = package.read(registration["parent_registry"])
    require(all(registry["splits"].get(str(p)) == "test" for p in h.formal.PARENTS), "test_parent_registration")
    rule = h.formal.rules(package, h.base, unlocked["rule"], source)
    require(package.read(frozen["campaign"])["dev_inputs"] == rule["dev_inputs"], "same_rule_and_model_dev")
    round1 = package.read(unlocked["round1_collection"])
    require(round1["batch"] == "pi1_train_dev_pairs" and round1["fit_calls_started"] == 0
            and round1["shared"] == shared and round1["spi_freeze"] == unlocked["spi_freeze"]
            and round1["behavior_model"] == models["C01"], "same_round1_no_second_fit")
    seeds = [r["parent"]["parent_seed"] for r in round1["inputs"]]
    require(len(seeds) == len(set(seeds)) == 12
            and set(seeds) == set(range(1101, 1109)) | set(range(1201, 1205)),
            "registered_twelve_round1_roots")
    training = h.builder.validate_training(package, request, h.base, h.formal, unlocked)
    package.mapped(request["formal"]["gate_implementation"])
    for ref in request["administrative_artifacts"]:
        package.mapped(ref)
    for old in request["superseded_manifests"]:
        require(old.get("scope") and old.get("status"), "superseded_scope")
        package.mapped(old["reference"]); package.mapped(old["replacement"])
    return unlocked, {"freeze": freeze, "training": training}


def no_live_objects(package, request, closures, plans, h):
    """Check only mapped names; static calendar is allowed by exact plan ref."""
    unsafe = [s for s in request["formal"]["runs"] if not s["started"]
              or not closures[s["name"]]["owned_complete"]]
    unsafe += [s for s in request["runs"] if s["role"] == "failed_attempt"
               and not closures[s["name"]]["terminal_verified"]]
    for slot in unsafe:
        directory = refkey(slot["plan"], h.base)[0].rsplit("/", 1)[0] + "/"
        allowed = {refkey(slot["plan"], h.base)[0]}
        if slot["receipt"] is not None:
            allowed.add(refkey(slot["receipt"], h.base)[0])
        forecast = plans.get(slot["name"], {}).get("forecast_binding")
        if forecast is not None:
            require(refkey(forecast, h.base)[0].rsplit("/", 1)[-1] == "calendar_binding.json",
                    "only_exact_static_calendar_inside_unavailable_run")
            package.mapped(forecast)
            allowed.add(refkey(forecast, h.base)[0])
        require(all(not key.startswith(directory) or key in allowed for key in package.mapping),
                "no_live_or_unstarted_run_artifacts")


def nonformal_numeric(package, request, receipts, closures, h):
    """Reuse audited arithmetic/pair binding; retain all 82 attempts and 36 pairs."""
    slots = [s for s in request["runs"] if s["role"] != "formal"]
    pairs = h.nonformal.collection_pairs(package, h.base, slots)
    lookup = {s["name"]: s for s in slots}
    reports, pair_reports, diagnostics = {}, [], {}
    def arm(name):
        closure = closures[name]
        if not closure["terminal_verified"]:
            return ({"name": name, "role": lookup[name]["role"], "status": "unknown_owned_closure",
                     "cost": None, "backlog_relief": None, "closure": closure,
                     "raw_evidence_opened": False, "failed_partial_cost_used": False}, None)
        return h.nonformal.audit_arm(package, h.base, lookup[name], receipts[name])
    for pair in pairs:
        indices = {}
        for name in pair["names"].values():
            reports[name], indices[name] = arm(name)
        try:
            pair_reports.append(h.nonformal.verify_pair_dataset(package, h.base, pair, indices))
        except (KeyError, TypeError, ValueError, OSError, EOFError) as exc:
            pair_reports.append({"round": pair["round"], "pair_slot_id": pair["item"]["pair_slot_id"],
                                 "status": "blocked_invalid_pair_labels", "error": str(exc)})
    for slot in slots:
        if slot["name"] not in reports:
            reports[slot["name"]], diagnostics[slot["name"]] = arm(slot["name"])
    comparisons = []
    for declared in request.get("comparisons", []):
        names = declared["reference"], declared["candidate"]
        require(names[0] != names[1] and all(n in lookup for n in names), "nonformal_declared_comparison_only")
        if declared["kind"] == "pilot_pair":
            matches = [p for p in pair_reports if (p.get("reference"), p.get("candidate")) == names]
            require(len(matches) == 1, "comparison_is_registered_pair")
            comparisons.append({**declared, "status": matches[0]["status"]})
        else:
            require(declared["kind"] in ("R0_vs_C00", "recovery_on_vs_off")
                    and all(n in diagnostics for n in names), "registered_diagnostic_comparison")
            if any(diagnostics[n] is None for n in names):
                comparisons.append({**declared, "status": "unknown_unavailable_arm"})
            else:
                try:
                    comparisons.append({**declared, "status": "registered_comparison_verified",
                        **h.nonformal.compare(h.base, *(diagnostics[n] for n in names), declared["kind"])})
                except (KeyError, TypeError, ValueError) as exc:
                    comparisons.append({**declared, "status": "blocked_invalid_comparison", "error": str(exc)})
    return {"retained_attempts": len(reports), "registered_pairs": len(pair_reports),
            "runs": list(reports.values()), "pairs": pair_reports, "declared_comparisons": comparisons,
            "direction_scope": "Seven categories and known direction counts; no independent magnitude-bound/transition replay."}


def formal_cell(package, request, entry, slot, receipt, closure, plan, h):
    out = {"name": slot["name"], "parent_seed": entry["parent_seed"], "method": entry["method"],
           "started": slot["started"], "primary_J": None, "raw_recomputed_cost": None,
           "bound_physical_cache_status": None, "descriptive_J_with_bound_physical_cache": None,
           "status": "not_started", "independent_physical_log_replay": False}
    if not slot["started"]:
        return out
    out["closure"] = closure
    out["status"] = closure["status"]
    if not closure["terminal_verified"] or not closure["owned_complete"]:
        return out
    out["status"] = "complete_missing_raw_cost_unknown"
    if slot["final_result"] is None or slot["evaluation"] is None:
        return out
    data = package.read(plan["input"])
    require(len(data["jobs"]) == 28506 and h.base.digest(data) == plan["input_semantic_sha256"],
            "formal_full_input_pin")
    result, evaluation = package.read(slot["final_result"]), package.read(slot["evaluation"])
    require(evaluation["status"] == "complete" and evaluation["parent"] == plan["parent"]
            and evaluation["method"] == plan["method"]
            and evaluation["input_semantic_sha256"] == plan["input_semantic_sha256"],
            "formal_evaluation_identity")
    cost, relief, _, _ = h.base.metrics(data, result, 7200., 59400.)
    require(result["physical_clock"] == receipt["worker"]["final_physical_time"] == 59400.,
            "formal_exact_final_endpoint")
    h.base.same(cost, evaluation["cost"], "formal_saved_evaluation_cost")
    if receipt["worker"].get("cost") is not None:
        h.base.same(cost, receipt["worker"]["cost"], "formal_saved_worker_cost")
    out.update(status="raw_cost_verified_physical_cache_unavailable", raw_recomputed_cost=cost)
    if slot["cache"] is None:
        return out
    cache, scope = h.formal.cache_binding(package, h.base, request["formal"], entry, slot, plan)
    raw = cache["raw_inventory"]["present"]
    require(refkey(raw["result"], h.base) == refkey(slot["final_result"], h.base),
            "physical_cache_actual_raw_result")
    out.update(bound_physical_cache_status=cache["status"], external_evidence_scope=scope,
               status="raw_cost_verified_bound_cache_blocked")
    if cache["status"] == "admitted_cost_and_physical_replay":
        row = cache["row"]
        continuation = result["control_continuation"]
        require(continuation["status"] == "reached" and continuation["timestamp_complete"] is True
                and continuation["physical_time"] == 59400., "timestamp_complete_continuation")
        h.base.same(cost, row["full_window_cost"], "cached_cost")
        h.base.same(relief, {k: row["backlog_relief"][k] for k in relief}, "cached_relief")
        physical = row["physical"]
        counters = h.formal.projection(result["native_summary"],
                                      ("reservation_conflicts", "physical_fault_edge_entry_violation_count"))
        require(physical["native_invariant_counters"] == counters
                and all(type(v) is int and v == 0 for v in counters.values())
                and physical["native_invariant_status"] == "passed_reported_counters"
                and physical["lifecycle_capacity_replay"]["status"] == "passed"
                and not row["missing_evidence"] and row["warmup_prefix"] is not None
                and row["provenance"]["status"] == "bound_files_verified"
                and row["provenance"]["actor_source_status"] == "fixed_actor_files_verified",
                "bound_producer_physical_basis")
        out.update(status="single_cell_raw_cost_and_bound_physical_cache_verified",
                   descriptive_J_with_bound_physical_cache=cost["backlog_integral_bag_seconds"])
    return out


def audit_view(package, request, h, *, numerical=True):
    roster, receipts, closures = metadata_gate(package, request, h)
    unlocked, training = training_graph(package, request, roster, h)
    slots = {refkey(s["plan"], h.base): s for s in request["formal"]["runs"]}
    plans = {}
    # Metadata-only plans: never read an unstarted input or result.
    for entry in roster["plans"]:
        slot = slots[refkey(entry["plan"], h.base)]
        plans[slot["name"]] = h.formal.plan_binding(package, h.base, roster, unlocked, entry, slot)
    no_live_objects(package, request, closures, plans, h)
    if not numerical:
        return {"closures": closures, "training": training, **DENIALS}
    nonformal = nonformal_numeric(package, request, receipts, closures, h)
    rows = []
    for entry in roster["plans"]:
        slot = slots[refkey(entry["plan"], h.base)]
        try:
            rows.append(formal_cell(package, request, entry, slot, receipts.get(slot["name"]),
                closures.get(slot["name"]), plans[slot["name"]], h))
        except (KeyError, TypeError, ValueError, OSError, EOFError) as exc:
            rows.append({"name": slot["name"], "parent_seed": entry["parent_seed"], "method": entry["method"],
                         "started": slot["started"], "status": "blocked_invalid_included_evidence",
                         "primary_J": None, "raw_recomputed_cost": None, "error": str(exc)})
    blocked = any(r["status"].startswith("blocked") for r in
                  [*rows, *nonformal["runs"], *nonformal["pairs"], *nonformal["declared_comparisons"]])
    return {"schema": SCHEMA + ".audit", "status": "blocked_invalid_evidence" if blocked else
            "partial_included_evidence_verified_with_missing_and_failures_retained",
            "scope": "Partial registered campaign; cellwise evidence only, never the complete primary test.",
            "registered_formal_slots": 40, "ledger_formal_attempts": sum(s["started"] for s in rows),
            "not_started_formal_slots": sum(not s["started"] for s in rows),
            "formal_status_counts": dict(Counter(r["status"] for r in rows)),
            "formal_rows": rows, "nonformal": nonformal, "training": training,
            "started_basis": "Final native ledger administrative attempt registration, not independent PID-start proof.",
            "all_ledger_attempts_terminal_verified": all(c["terminal_verified"] for c in closures.values()),
            "registered_formal_campaign_complete_claimed": False,
            "missing_exit_not_fabricated": True, "original_absolute_paths_opened": False,
            "native_operations": 0, "fit_operations": 0, **DENIALS}


def local_view(spec, request, h):
    # Graph already explicitly lists archived members. Avoid full builder's
    # eager source-manifest expansion before the partial closure gate.
    class Local(h.builder.ExplicitFiles):
        def raw_reference(self, ref):
            row = self.mapped(ref)
            path = Path(row["path"])
            require(path.stat().st_size <= 16 * 1024**2, "small_local_raw_metadata")
            raw = path.read_bytes()
            require(h.base.sha_bytes(raw) == ref["sha256"], "local_metadata_pin")
            return raw
    view = Local({**spec, "source_manifests": []}, request, h.selector, h.base)
    for ref in spec["source_manifests"]:
        view.add(ref, "registration")
    return view


def preflight(request_ref, *, helper_directory=HERE):
    h = helpers(helper_directory)
    path = h.builder.approved_path(request_ref["path"], h.selector)
    require(path.stat().st_size <= h.selector.MAX_SMALL and sha(path) == request_ref["sha256"],
            "bound_partial_request")
    request = h.base.decode(path.read_bytes())
    request_shape(request, h)
    spec_ref = request["allowlist_request"]
    spec_path = h.builder.approved_path(spec_ref["path"], h.selector)
    require(spec_path.stat().st_size <= h.selector.MAX_SMALL and sha(spec_path) == spec_ref["sha256"],
            "bound_partial_allowlist")
    spec = h.base.decode(spec_path.read_bytes())
    require(spec["formal_unlock"] == request["formal"]["unlock"], "same_unlock")
    require(len(spec["registered_run_slots"]) == len(request["runs"])
            and {(s["slot_id"], s["role"], refkey(s["plan"], h.base)) for s in spec["registered_run_slots"]}
            == {(s["name"], s["role"], refkey(s["plan"], h.base)) for s in request["runs"]},
            "same_actual_allowlist_attempts")
    view = local_view(spec, request, h)
    view.add(request_ref, "registration"); view.add(spec_ref, "registration")
    view.manifest = request
    checks = audit_view(view, request, h, numerical=False)
    included = view.validate_included()
    return request, view, included, checks


def build(request_ref, *, output, helper_directory=HERE):
    output = Path(output).resolve()
    require(output.is_relative_to(HERE) and not output.exists(), "fresh_partial_package")
    request, view, included, checks = preflight(request_ref, helper_directory=helper_directory)
    require(all(not output.is_relative_to(Path(r["path"]))
                and not Path(r["path"]).is_relative_to(output) for r in included), "no_output_input_overlap")
    output.mkdir(); (output / "objects").mkdir()
    files, mappings = {}, []
    for row in included:
        destination = "objects/" + row["sha256"]
        if destination not in files:
            shutil.copyfile(row["path"], output / destination)
            require((output / destination).stat().st_size == row["bytes"]
                    and sha(output / destination) == row["sha256"], "copied_exact_original_bytes")
            files[destination] = {"package_path": destination, "sha256": row["sha256"], "bytes": row["bytes"]}
        mappings.append({"original_path": row["path"], "package_path": destination,
                         "sha256": row["sha256"], "category": row["category"]})
    manifest = {**request, "schema": SCHEMA + ".package", "request": request,
        "files": list(files.values()), "original_path_map": mappings, "preflight": checks,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "builder_request": request_ref, "builder": {"path": str(Path(__file__).resolve()), "sha256": sha(__file__)},
        "scope": "Partial registered campaign; no missing attempt is fabricated.",
        "native_operations": 0, "fit_operations": 0, **DENIALS}
    with (output / "PACKAGE_MANIFEST.json").open("x", encoding="utf8", newline="\n") as stream:
        json.dump(manifest, stream, ensure_ascii=False, allow_nan=False, indent=2); stream.write("\n")
    return {"status": "partial_built_pending_independent_audit", "package": str(output),
            "manifest": {"path": str(output / "PACKAGE_MANIFEST.json"),
                         "sha256": sha(output / "PACKAGE_MANIFEST.json")}, **DENIALS}


def audit(path, manifest_sha256, *, helper_directory=HERE):
    h = helpers(helper_directory)
    # Explicit schema adapter only. No helper constants or receipts are mutated.
    facade = types.SimpleNamespace(**{k: v for k, v in vars(h.base).items() if k != "SCHEMA"},
                                   SCHEMA=SCHEMA + ".package")
    package = h.formal.open_deferred(facade, path, manifest_sha256)
    def raw_reference(ref):
        row = package.mapped(ref)
        raw = package.raw(row["package_path"])
        require(len(raw) == row["bytes"] and h.base.sha_bytes(raw) == ref["sha256"], "portable_raw_ref")
        return raw
    package.raw_reference = raw_reference
    try:
        request = package.manifest["request"]
        require(package.read(package.manifest["builder_request"]) == request, "original_request_bytes")
        require(all(package.manifest[k] == request[k] for k in (
            "runs", "formal", "training", "attempt_ledger", "cutoff", "comparisons", "claims")),
            "manifest_and_bound_request_scope")
        require(all(package.manifest.get(k) == v for k, v in DENIALS.items()), "manifest_cannot_claim_full")
        report = audit_view(package, request, h)
        package.verify_all()
        report.update(manifest_sha256=manifest_sha256, auditor_sha256=sha(__file__),
                      included_bytes=package.included_bytes, all_package_bytes_rehashed=True)
        return report
    finally:
        package.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("preflight", "build"):
        child = sub.add_parser(name)
        child.add_argument("--request", type=Path, required=True)
        child.add_argument("--request-sha256", required=True)
        if name == "build":
            child.add_argument("--output", type=Path, required=True)
    child = sub.add_parser("audit")
    child.add_argument("package", type=Path)
    child.add_argument("--manifest-sha256", required=True)
    child.add_argument("--helper-directory", type=Path, default=HERE)
    child.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "audit":
        result = audit(args.package, args.manifest_sha256, helper_directory=args.helper_directory)
        with args.output.open("x", encoding="utf8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=False, allow_nan=False, indent=2); stream.write("\n")
    else:
        reference = {"path": str(args.request.resolve()), "sha256": args.request_sha256}
        if args.command == "build":
            result = build(reference, output=args.output)
        else:
            result = {"status": "partial_metadata_preflighted", "checks": preflight(reference)[3]}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
