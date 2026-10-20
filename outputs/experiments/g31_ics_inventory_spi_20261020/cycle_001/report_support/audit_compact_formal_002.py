"""Pre-outcome fixed compact formal-package audit; standard library only.

The only executable dependency is our explicitly SHA-pinned package auditor
001, never archived project/native code. All 40 terminal receipts and the
unlock/freeze graph precede raw outcome reads. External physical/control logs
remain outside independent content coverage; producer cache claims stay named.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path, PureWindowsPath
import time
import types
import zipfile

BASE_SHA = "7d60b20c1a4cdcee63b79f9477c96f6764e15e4908facd714b0e4fa45121271a"
GATE_SHA = "09849f3b8af1e7fe48756638c0aa49c0154fff9871eeb7290c62c686bd9caa20"
SCHEMA = "g31.inventory_spi.compact_formal_audit.v2"
RUN_SCHEMA = "g31.inventory_spi_native_campaign.v1"
STAGE_SCHEMA = "g31.inventory_spi_offline_stages.v1"
GATE_SCHEMA = "g31.inventory_spi_formal_analysis_gate.v1"
PARENTS = tuple(range(1301, 1309))
METHODS = ("R0_current_stock_v1", "C00", "C10", "C01", "C11")
OPEN = {"running", "prepared", "pending", "not_started", "not_closed"}
PI0 = "airport_common_inventory_pi0_v1"


def require(ok, reason):
    if not ok:
        raise ValueError("compact_formal:"+reason)


def load_base(path):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == BASE_SHA, "trusted_base_validator_sha")
    module = types.ModuleType("pinned_compact_base")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def open_deferred(base, path, manifest_sha):
    class DeferredPackage(base.Package):
        def __init__(self, path, manifest_sha):
            self.path = Path(path)
            self.zip = zipfile.ZipFile(path) if self.path.is_file() else None
            if self.zip:
                infos = [x for x in self.zip.infolist() if not x.is_dir()]
                names = [base.safe_name(x.filename) for x in infos]
                require(len(names) == len(set(names)), "unique_zip_members")
                require(all((x.external_attr >> 16) & 0o170000 != 0o120000 for x in infos),
                        "no_zip_symlinks")
            else:
                require(self.path.is_dir(), "package_directory")
                paths = list(self.path.rglob("*"))
                require(not any(p.is_symlink() for p in paths), "no_directory_symlinks")
                names = [base.safe_name(p.relative_to(self.path).as_posix()) for p in paths if p.is_file()]
            raw = self.raw("PACKAGE_MANIFEST.json")
            require(base.sha_bytes(raw) == manifest_sha, "trusted_manifest_sha")
            self.manifest = base.decode(raw)
            require(self.manifest["schema"] == base.SCHEMA, "package_schema")
            self.files = {}
            for row in self.manifest["files"]:
                name = base.safe_name(row["package_path"])
                require(name not in self.files, "unique_file_manifest")
                self.files[name] = row
            require(set(names) == {*self.files, "PACKAGE_MANIFEST.json"}, "exact_inventory")
            self.mapping = {}
            for row in self.manifest["original_path_map"]:
                key = base.original_key(row["original_path"])
                require(key not in self.mapping, "unique_original_mapping")
                target = self.files[base.safe_name(row["package_path"])]
                require(row["sha256"] == target["sha256"], "mapping_sha")
                self.mapping[key] = target
            require({r["package_path"] for r in self.manifest["original_path_map"]} == set(self.files),
                    "every_content_object_mapped")
            self.included_bytes = None

        def verify_all(self):
            total = 0
            for name, row in self.files.items():
                raw = self.raw(name)
                require(len(raw) == row["bytes"] and base.sha_bytes(raw) == row["sha256"],
                        "included_original_bytes:"+name)
                total += len(raw)
            self.included_bytes = total
    return DeferredPackage(path, manifest_sha)


def terminal(receipt, plan_ref):
    process = receipt.get("process") or {}
    require(isinstance(receipt.get("status"), str) and receipt["status"] not in OPEN
            and process.get("status") in ("exited", "hard_timeout")
            and receipt.get("plan_sha256") == plan_ref["sha256"], "producer_terminal_attempt_before_outcome")
    if receipt["status"] == "complete":
        require((receipt.get("worker") or {}).get("status") == "complete"
                and process["status"] == "exited" and type(process.get("exitcode")) is int
                and process["exitcode"] == 0 and process.get("windows_job_kill_on_close") is True
                and process.get("child_released_only_after_job_assignment") is True,
                "complete_worker_and_successful_process")
    # A terminated failed attempt can lack a worker report or retain its last
    # partial status/cost. Those diagnostics never become primary cost.


def rules(package, base, reference, source):
    value = package.read(reference)
    require(value["schema"] == "g31.foundation.airport_spi_C10_development_selection.v1"
            and value["selection_id"] == base.digest({k: v for k, v in value.items() if k != "selection_id"})
            and value["test_opened"] is False and value["fit_calls"] == 0
            and value["rule_contract_sha256"] == base.digest(value["rule_contract"]), "C10_frozen_identity")
    contract = value["contract"]
    required = {"candidates": ["reference", "strong_rule_weight0", "strong_rule_weight1"],
        "forecast_weights": [0., 1.], "expected_dev_pairs": 8, "expected_dev_parents": 4,
        "registered_dev_parent_seeds": [1201, 1202, 1203, 1204], "root_slots_per_parent": 2,
        "K_max": 13, "max_policy_replacements_per_parent": 1, "continuation_policy_id": PI0,
        "label_horizon_seconds": 1800., "minimum_supported_fraction": .25, "known_direction_harm_limit": 0,
        "require_nonworse_on_time": True, "require_nonworse_overdue_unfinished": True,
        "incomplete_development_J_blocks_promotion": True, "reference_wins_ties": True,
        "test_used_for_selection": False, "protected_takeover_eligible": False}
    require(all(contract.get(k) == v for k, v in required.items()), "C10_preregistered_contract")
    method = value["selected_method"]
    require(method in contract["candidates"] and value["selected"] ==
            ("reference" if method == "reference" else "strong_rule")
            and value["forecast_weight"] == (0 if method == "reference" else int(method[-1])),
            "C10_selected_configuration")
    require(value["source_sha256"], "C10_nonempty_source_pins")
    for logical, expected in value["source_sha256"].items():
        require(source["files"].get(logical) == expected, "C10_runtime_source_pin")
        package.mapped({"path": base.original_join(source["root"], logical), "sha256": expected})
    inputs = value["dev_inputs"]
    require(len(inputs) == 8 and Counter(r["parent"]["parent_seed"] for r in inputs)
            == Counter({p: 2 for p in range(1201, 1205)}), "C10_all_eight_dev_roots")
    require(len({base.original_key(r["dataset"]["path"]) for r in inputs}) == 8, "unique_dev_datasets")
    for row in inputs:
        require(row["parent"]["split"] == "dev" and row["parent"].get("rollout_round", 0) == 0,
                "C10_no_test_or_second_round")
        package.mapped(row["dataset"])
    return value


def unlock_graph(package, base, formal):
    roster = package.read(formal["roster"])
    require(roster["schema"] == STAGE_SCHEMA+".formal_batch"
            and roster["registered_parents"] == 8 and roster["registered_arms"] == 40
            and roster["test_inputs_generated_after_champion_freeze"] is True
            and roster["test_outcomes_opened"] is False, "frozen_forty_roster")
    entries = roster["plans"]
    keys = [(r["parent_seed"], r["method"]) for r in entries]
    require(len(keys) == len(set(keys)) == 40
            and set(keys) == {(p, m) for p in PARENTS for m in METHODS}, "complete_forty_cells")
    require(len({base.original_key(r["plan"]["path"]) for r in entries}) == 40, "unique_plan_refs")
    require(roster["formal_unlock"] == formal["unlock"], "roster_unlock_binding")
    unlocked = package.read(formal["unlock"])
    require(unlocked["schema"] == RUN_SCHEMA+".formal_unlock"
            and unlocked["status"] == "all_champions_frozen_test_unlocked"
            and unlocked["test_parent_ids"] == list(PARENTS)
            and unlocked["test_outcomes_used_for_selection"] is False, "legal_formal_unlock")
    freeze_audit = base.validate_freeze(package, unlocked["spi_freeze"])
    frozen = package.read(unlocked["spi_freeze"])
    require(frozen["contract"]["policy_alignment"] ==
            {"behavior_policy_id": PI0, "continuation_policy_id": PI0, "improvement_round": 0,
             "max_policy_replacements": 1, "label_horizon_seconds": 1800.}, "first_round_frozen_policy")
    models = {r["information_variant"]: r["checkpoint"] for r in frozen["models"]}
    require(models == unlocked["models"], "unlocked_selected_models")
    shared = roster["shared"]
    for key in ("source_bundle", "native_acceptance", "preregistration"):
        require(shared[key] == unlocked[key], "shared_unlock_"+key)
    source = package.read(shared["source_bundle"])
    base.validate_source(package, shared["source_bundle"], source["source_manifest_sha256"])
    native = package.read(shared["native_acceptance"])
    base.accepted_native(native, native["binary"]["sha256"])
    package.mapped({"path": shared["binary"], "sha256": native["binary"]["sha256"]})
    registration = package.read(shared["preregistration"])
    require(registration["schema"] == RUN_SCHEMA+".registration", "registration_schema")
    require(package.read(registration["learning_contract"]) == frozen["contract"], "registered_learning_contract")
    runtime = package.read(registration["runtime_shared"])
    for key in ("binary", "source_bundle", "native_acceptance", "soft_seconds", "hard_seconds", "calibration"):
        require(runtime.get(key) == shared.get(key), "registered_runtime_"+key)
    package.mapped(registration["contract_document"])
    registry = package.read(registration["parent_registry"])
    require(all(registry["splits"].get(str(p)) == "test" for p in PARENTS), "registered_test_parent_ids")
    rule = rules(package, base, unlocked["rule"], source)
    campaign = package.read(frozen["campaign"])
    require(campaign["dev_inputs"] == rule["dev_inputs"], "same_frozen_dev_data_for_rules_and_models")
    collection = package.read(unlocked["round1_collection"])
    require(collection["schema"] == STAGE_SCHEMA+".collection"
            and collection["batch"] == "pi1_train_dev_pairs" and collection["rollout_round"] == 1
            and collection["registered_pairs"] == 12 and collection["registered_arms"] == 24
            and collection["closed_attempt_receipts"] == 24 and len(collection["inputs"]) == 12
            and collection["test_opened"] is False and collection["second_round_training_authorized"] is False
            and collection["fit_calls_started"] == 0
            and collection["shared"] == shared and collection["spi_freeze"] == unlocked["spi_freeze"]
            and collection["behavior_model"] == models["C01"], "real_second_round_collection")
    seeds = [r["parent"]["parent_seed"] for r in collection["inputs"]]
    require(set(seeds) == set(range(1101, 1109)) | set(range(1201, 1205))
            and len(set(seeds)) == 12, "round1_fixed_twelve_roots")
    receipt_refs = set()
    for row in collection["inputs"]:
        dataset = package.read(row["dataset"])
        provenance = dataset["collection_provenance"]
        require(dataset["pair"]["parent"] == row["parent"]
                and provenance["batch_manifest"] == collection["batch_manifest"]
                and provenance["plans"] == {"a_ref": row["reference_plan"], "a_patch": row["patched_plan"]},
                "round1_dataset_provenance")
        for branch in ("a_ref", "a_patch"):
            reference = provenance["attempt_receipts"][branch]
            key = base.original_key(reference["path"])
            require(key not in receipt_refs, "unique_24_round1_receipts")
            receipt_refs.add(key)
            terminal(package.read(reference), provenance["plans"][branch])
    require(len(receipt_refs) == 24, "all_round1_attempts_closed")
    slots = formal["runs"]
    lookup = {base.original_key(r["plan"]["path"]): r for r in slots}
    require(len(slots) == len(lookup) == 40
            and set(lookup) == {base.original_key(r["plan"]["path"]) for r in entries}
            and len({r["name"] for r in slots}) == 40, "all_forty_package_run_slots")
    # All terminal receipts are checked before opening any formal plan/input/result.
    receipts = {}
    for entry in entries:
        slot = lookup[base.original_key(entry["plan"]["path"])]
        require(slot["plan"] == entry["plan"], "slot_registered_plan_pin")
        receipt = package.read(slot["receipt"])
        terminal(receipt, entry["plan"])
        receipts[slot["name"]] = receipt
    return roster, unlocked, lookup, receipts, freeze_audit


def plan_binding(package, base, roster, unlocked, entry, slot):
    plan = package.read(entry["plan"])
    require(plan["name"] == slot["name"] and plan["method"] == entry["method"]
            and plan["parent"]["parent_seed"] == entry["parent_seed"]
            and plan["parent"]["split"] == "test" and plan["parent"]["offered_count"] == 28506
            and plan["pair"] is None and plan["cost_window"] == [7200., 59400.]
            and plan["horizon"] == 59400. and plan["activate_at"] == 7200.
            and plan["formal_unlock"] == roster["formal_unlock"], "formal_plan_identity")
    for key in ("source_bundle", "native_acceptance"):
        require(plan[key] == roster["shared"][key] == unlocked[key], "formal_shared_"+key)
    require(plan["source_manifest_sha256"] == package.read(plan["source_bundle"])["source_manifest_sha256"],
            "actual_source_semantic_identity")
    require(base.original_key(plan["binary"]["path"]) == base.original_key(roster["shared"]["binary"])
            and plan["controller"]["recover_failed_empty"] is True
            and plan.get("behavior_model") is None, "common_protocol_and_first_policy")
    if plan["method"] in ("C01", "C11"):
        require(plan["model"] == unlocked["models"][plan["method"]] and plan["rule"] is None,
                "actual_selected_model_deployed")
    elif plan["method"] == "C10":
        require(plan["rule"] == unlocked["rule"] and plan["model"] is None, "actual_frozen_rule_deployed")
    else:
        require(plan["rule"] is None and plan["model"] is None, "baseline_no_hidden_model")
    return plan


def projection(value, fields):
    return {k: value.get(k) for k in fields}


def validate_inventory(package, base, cache):
    excluded = {base.original_key(r["path"]): r for r in package.manifest.get("excluded_large_logs", [])}
    scope = Counter()
    for key, reference in cache["raw_inventory"]["present"].items():
        if base.original_key(reference["path"]) in package.mapping:
            package.mapped(reference)
            scope["included_bound_refs"] += 1
        else:
            row = excluded.get(base.original_key(reference["path"]))
            require(row is not None and (row.get("sha256") or row.get("declared_expected_sha256"))
                    == reference["sha256"], "external_inventory_must_be_explicitly_bound")
            scope["excluded_cache_declared_refs_not_rehashed"] += 1
    return dict(scope)


def cache_binding(package, base, formal, entry, slot, plan):
    cache = package.read(slot["cache"])
    require(cache["schema"] == GATE_SCHEMA and cache["manifest"] == formal["roster"]
            and cache["plan"] == entry["plan"] and cache["name"] == slot["name"]
            and cache["expected_population"] == 28506 and cache["window"] == [7200., 59400.],
            "registered_cached_gate")
    implementations = cache["implementation"]
    require(any(r["sha256"] == GATE_SHA for r in implementations), "frozen_gate_implementation")
    for reference in implementations:
        package.mapped(reference)
    require(cache["status"] in ("admitted_cost_and_physical_replay", "blocked")
            and (cache["status"] == "admitted_cost_and_physical_replay") == (cache["issues"] == []),
            "cache_status_issues")
    row = cache["row"]
    require(row["name"] == plan["name"] and row["registered_parent_seed"] == entry["parent_seed"]
            and row["registered_method"] == entry["method"], "cached_row_identity")
    if cache["status"] == "blocked":
        require(row["full_window_cost"] is None and row["backlog_relief"] is None,
                "blocked_primary_cost_is_null")
    else:
        require(row["status"] == "complete" and row["audit_status"] == "closed_cost_verified"
                and row["full_window_cost"] is not None and row["backlog_relief"] is not None,
                "admitted_row_verified_cost_required")
    inventory = cache["raw_inventory"]["present"]
    for key, ref in (("plan", entry["plan"]), ("receipt", slot["receipt"]), ("dependency.input", plan["input"])):
        require(inventory[key]["path"] == ref["path"] and inventory[key]["sha256"] == ref["sha256"],
                "cache_mandatory_raw_ref")
    return cache, validate_inventory(package, base, cache)


def tri(values, predicate):
    if any(v is not None and not predicate(v) for v in values):
        return False
    return True if all(v is not None for v in values) else None


def mean(values):
    return math.fsum(values)/len(values) if values and all(v is not None for v in values) else None


def full_direction(base, specs, left, right, cutoff):
    value = base.directions(specs, left, right, cutoff)
    exact_delay, exact_gain, lower_delay, lower_gain = [], [], [], []
    for identity in specs:
        a, b = left.get(identity), right.get(identity)
        if a is not None and b is not None:
            if b-a > 1e-6:
                exact_delay.append(b-a)
            elif a-b > 1e-6:
                exact_gain.append(a-b)
        elif a is not None:
            lower_delay.append(cutoff-a)
        elif b is not None:
            lower_gain.append(cutoff-b)
    value.update(schema="g31.completion_direction.v1", cutoff=cutoff,
        maximum_exact_delay_seconds=max(exact_delay, default=0.),
        maximum_exact_improvement_seconds=max(exact_gain, default=0.),
        maximum_censored_delay_lower_bound_seconds=max(lower_delay, default=0.),
        maximum_censored_improvement_lower_bound_seconds=max(lower_gain, default=0.),
        sum_censored_delay_lower_bound_seconds=math.fsum(lower_delay),
        sum_censored_improvement_lower_bound_seconds=math.fsum(lower_gain),
        unknown_incomplete_legacy=sum(value["categories"][k] for k in
            ("reference_only_finished", "candidate_only_finished", "both_arrived_unfinished", "both_not_yet_arrived")),
        completion_times_imputed=False, bounds_are_not_completion_times=True)
    return value


def effect_math(points, *, interaction=False):
    gains = [p["advantage_bag_seconds"] for p in points]
    total_ref = math.fsum(p["reference_J_bag_seconds"] for p in points) if all(v is not None for v in gains) else None
    relative = math.fsum(gains)/total_ref if total_ref is not None and total_ref > 0 else None
    out = {"registered_parent_count": 8, "known_parent_count": sum(v is not None for v in gains),
        "unknown_parent_ids": [p["parent_seed"] for p in points if p["advantage_bag_seconds"] is None],
        "complete_eight_parent_mean_gain_bag_seconds": mean(gains),
        "complete_mean_of_paired_relative_gains": mean([p["relative_J_gain"] for p in points]),
        "relative_gain_of_mean_J": relative,
        "engineering_threshold_reached": None if interaction or relative is None else relative >= .001,
        "engineering_threshold": .001}
    counts = Counter("unknown" if g is None else "candidate_better" if g > 1e-6 else
        "candidate_worse" if g < -1e-6 else "equal_within_numeric_tolerance" for g in gains)
    out["cost_direction_counts"] = {k: counts[k] for k in
        ("candidate_better", "candidate_worse", "equal_within_numeric_tolerance", "unknown")}
    out["leave_one_out_numeric"] = []
    for omitted in PARENTS:
        rest = [p for p in points if p["parent_seed"] != omitted]
        values = [p["advantage_bag_seconds"] for p in rest]
        known = all(v is not None for v in values)
        denominator = math.fsum(p["reference_J_bag_seconds"] for p in rest) if known else None
        rel = math.fsum(values)/denominator if known and denominator > 0 else None
        avg = mean(values)
        out["leave_one_out_numeric"].append({"omitted_parent_seed": omitted,
            "registered_remaining_parent_count": 7, "known_remaining_parent_count": sum(v is not None for v in values),
            "complete_mean_gain_bag_seconds": avg, "relative_gain_of_mean_J": rel,
            "positive_mean_gain": None if avg is None else avg > 1e-6,
            "engineering_threshold_reached": None if interaction or rel is None else rel >= .001,
            "omitted_parent_gain_bag_seconds": next(p["advantage_bag_seconds"] for p in points if p["parent_seed"] == omitted)})
    avg = mean(gains)
    positive = None if avg is None else avg > 1e-6
    positives = [p["parent_seed"] for p in points if p["advantage_bag_seconds"] is not None and p["advantage_bag_seconds"] > 1e-6]
    eliminated = [r["omitted_parent_seed"] for r in out["leave_one_out_numeric"] if r["positive_mean_gain"] is False]
    out["leave_one_out_summary"] = {"registered_leave_one_out_count": 8,
        "full_eight_parent_mean_is_positive": positive, "positive_gain_parents": positives,
        "positive_gain_occurs_only_in_one_parent": len(positives) == 1 if avg is not None else None,
        "parent_removal_eliminates_positive_mean": eliminated if positive else None,
        "positive_mean_survives_removal_of_every_parent": not eliminated if positive else None,
        "caused_by_single_stalled_parent": "not_established_by_leave_one_out",
        "resampling_confidence_interval_or_p_value": False}
    return out


def verify_effects(base, effects, grid, comparable):
    require(effects["schema"] == "g31.inventory_spi_parent_effects.v1"
            and effects["registered_parent_ids"] == list(PARENTS) and effects["registered_run_count"] == 40
            and effects["formal_admission"] == grid["formal_admission"]
            and effects["failures_or_missing_cells_omitted"] == 0
            and effects["partial_parent_mean_presented_as_complete"] is False, "effects_fixed_denominators")
    lookup = {(r["registered_parent_seed"], r["registered_method"]): r for r in grid["rows"]}
    require(set(effects["methods"]) == set(METHODS), "exact_five_effect_methods")
    for method in METHODS:
        rows = [lookup[(p, method)] for p in PARENTS]
        values = [r["full_window_cost"] if r["status"] == "complete"
                  and r["audit_status"] == "closed_cost_verified" else None for r in rows]
        saved = effects["methods"][method]
        require([p["parent_seed"] for p in saved["points"]] == list(PARENTS),
                "method_fixed_ordered_eight_points")
        for parent, row, cost, point in zip(PARENTS, rows, values, saved["points"], strict=True):
            expected = {"parent_seed": parent, "method": method, "name": row["name"],
                "run_status": row["status"], "audit_status": row["audit_status"],
                "J_bag_seconds": cost["backlog_integral_bag_seconds"] if cost is not None else None,
                "cost_known": cost is not None,
                "service": {key: cost[key] if cost is not None else None for key in
                    ("completed_by_end", "on_time_by_end", "arrived_unfinished_past_deadline", "physical_population")},
                "physical_diagnostics": row.get("physical"), "control_diagnostics": row.get("control"),
                "missing_evidence": row.get("missing_evidence", []), "errors": row.get("errors", []),
                "strict_nonharm_certified": False}
            base.same(expected, projection(point, expected.keys()), "method_point_grid_binding")
        base.same(dict(Counter(r["status"] for r in rows)), saved["run_status_counts"], "method_status_counts")
        base.same(dict(Counter(r["audit_status"] for r in rows)), saved["audit_status_counts"], "method_audit_counts")
        for outkey, costkey in (("complete_eight_parent_mean_J_bag_seconds", "backlog_integral_bag_seconds"),
            ("complete_eight_parent_mean_completed", "completed_by_end"), ("complete_eight_parent_mean_on_time", "on_time_by_end"),
            ("complete_eight_parent_mean_overdue_unfinished", "arrived_unfinished_past_deadline")):
            base.same(mean([v[costkey] if v is not None else None for v in values]), saved[outkey], outkey)
        require(saved["registered_parent_count"] == 8 and saved["closed_cost_parent_count"] == sum(v is not None for v in values)
                and saved["unknown_parent_ids"] == [p for p, v in zip(PARENTS, values) if v is None],
                "effects_method_unknowns")
    required_keys = {a+"_minus_"+b for a, b in combinations(METHODS, 2)}
    require(set(effects["paired_effects"]) == required_keys, "all_ten_effects")
    for a, b in combinations(METHODS, 2):
        saved = effects["paired_effects"][a+"_minus_"+b]
        require([p["parent_seed"] for p in saved["points"]] == list(PARENTS),
                "effect_fixed_ordered_eight_points")
        points = []
        for parent in PARENTS:
            row = comparable[(parent, a, b)]
            ac, bc = lookup[(parent, a)]["full_window_cost"], lookup[(parent, b)]["full_window_cost"]
            known = row["status"] == "closed_same_parent_comparison" and ac is not None and bc is not None
            point = {"parent_seed": parent, "advantage_bag_seconds": row["advantage_bag_seconds"] if known else None,
                "relative_J_gain": row.get("relative_J_gain") if known else None,
                "reference_J_bag_seconds": ac["backlog_integral_bag_seconds"] if ac is not None else None}
            points.append(point)
            sp = saved["points"][len(points)-1]
            base.same(projection(point, point.keys()), projection(sp, point.keys()), "effects_point")
            require(sp["status"] == ("closed_same_parent_effect" if known else "unknown"), "effect_point_status")
            for field in ("completed_delta", "on_time_delta", "overdue_unfinished_delta"):
                base.same(row.get(field) if known else None, sp[field], "effect_service_delta")
            base.same(row["completion_direction"]["known_direction_harm"] if known else None,
                      sp["known_direction_harm"], "effect_known_harm")
            base.same(row["completion_direction"] if known else None, sp["completion_direction"],
                      "effect_full_completion_direction")
        expected = effect_math(points)
        loo = expected.pop("leave_one_out_numeric")
        loo_summary = expected.pop("leave_one_out_summary")
        base.same(expected, projection(saved, expected.keys()), "effect_aggregate")
        base.same(loo_summary, projection(saved["leave_one_parent_out"], loo_summary.keys()), "concentration_flags")
        require(len(saved["leave_one_parent_out"]["entries"]) == 8, "eight_leave_one_out_rows")
        for target, actual in zip(loo, saved["leave_one_parent_out"]["entries"]):
            base.same(target, projection(actual, target.keys()), "leave_one_out")
        service = saved["service"]
        expected_service = {
            "completed_non_decreasing_observed": tri([p["completed_delta"] for p in saved["points"]], lambda x: x >= 0),
            "on_time_non_decreasing_all_parents": tri([p["on_time_delta"] for p in saved["points"]], lambda x: x >= 0),
            "overdue_unfinished_non_increasing_all_parents": tri([p["overdue_unfinished_delta"] for p in saved["points"]], lambda x: x <= 0),
            "known_direction_harm_zero_all_parents": tri([p["known_direction_harm"] for p in saved["points"]], lambda x: x == 0)}
        expected_service["registered_service_constraints_satisfied"] = tri(
            [expected_service[k] for k in ("on_time_non_decreasing_all_parents",
                "overdue_unfinished_non_increasing_all_parents", "known_direction_harm_zero_all_parents")], lambda x: x is True)
        directions = [p["completion_direction"] for p in saved["points"] if p["completion_direction"] is not None]
        expected_service.update(
            known_completion_direction_parent_count=len(directions),
            unknown_completion_direction_parent_ids=[p["parent_seed"] for p in saved["points"]
                if p["completion_direction"] is None],
            complete_eight_parent_category_totals={k: sum(d["categories"][k] for d in directions)
                for k in directions[0]["categories"]} if len(directions) == 8 else None,
            known_harmed_parent_ids=[p["parent_seed"] for p in saved["points"]
                if p["known_direction_harm"] is not None and p["known_direction_harm"] > 0],
            complete_known_direction_harm_sum=sum(p["known_direction_harm"] for p in saved["points"])
                if len(directions) == 8 else None,
            strict_per_job_nonharm_certified=False)
        base.same(expected_service, projection(service, expected_service.keys()), "effects_service_gate")
    interaction = effects["interaction"]
    require([p["parent_seed"] for p in interaction["points"]] == list(PARENTS),
            "interaction_fixed_ordered_eight_points")
    points = []
    for i, parent in enumerate(PARENTS):
        components = {k: effects["paired_effects"][k]["points"][i]["advantage_bag_seconds"]
                      for k in ("C00_minus_C01", "C10_minus_C11", "C00_minus_C10", "C01_minus_C11")}
        known = all(v is not None for v in components.values())
        gain = components["C10_minus_C11"]-components["C00_minus_C01"] if known else None
        baseline = lookup[(parent, "C00")]["full_window_cost"]
        denominator = baseline["backlog_integral_bag_seconds"] if baseline is not None else None
        point = {"parent_seed": parent, "advantage_bag_seconds": gain,
            "reference_J_bag_seconds": denominator,
            "relative_J_gain": gain/denominator if gain is not None and denominator > 0 else None}
        base.same(point, projection(interaction["points"][i], point.keys()), "interaction_point")
        require(interaction["points"][i]["status"] == ("closed_factorial_interaction" if known else "unknown"),
                "interaction_point_status")
        base.same(components, interaction["points"][i]["component_gains"], "interaction_all_four_components")
        points.append(point)
    expected = effect_math(points, interaction=True)
    loo = expected.pop("leave_one_out_numeric")
    loo_summary = expected.pop("leave_one_out_summary")
    base.same(expected, projection(interaction, expected.keys()), "interaction_aggregate")
    base.same(loo_summary, projection(interaction["leave_one_parent_out"], loo_summary.keys()), "interaction_concentration")
    for target, actual in zip(loo, interaction["leave_one_parent_out"]["entries"], strict=True):
        base.same(target, projection(actual, target.keys()), "interaction_leave_one_out")
    return {"effects_numeric_basis": "all method means, 80 pair points, 10 effects, 8-parent leave-one-out, service flags and interaction",
            "engineering_promotion_recomputed_or_authorized": False}


def audit_formal(package, base):
    formal = package.manifest["formal"]
    require(formal["gate_implementation"]["sha256"] == GATE_SHA, "fixed_formal_gate_required")
    package.mapped(formal["gate_implementation"])
    roster, unlocked, slots, receipts, freeze = unlock_graph(package, base, formal)
    # Only now are all original included bytes, including outcomes, opened.
    package.verify_all()
    plans, caches, recomputed, evidence_scopes, rows_out = {}, {}, {}, {}, []
    parent_identity = {}
    for entry in roster["plans"]:
        slot = slots[base.original_key(entry["plan"]["path"])]
        name = slot["name"]; receipt = receipts[name]
        plan = plan_binding(package, base, roster, unlocked, entry, slot)
        plans[name] = plan
        package.mapped(plan["binary"])
        native = package.read(plan["native_acceptance"])
        base.accepted_native(native, plan["binary"]["sha256"])
        data = package.read(plan["input"])
        require(len(data["jobs"]) == 28506 and base.digest(data) == plan["input_semantic_sha256"],
                "complete_formal_input_binding")
        identity = projection(plan, ("parent", "input", "input_semantic_sha256", "source_manifest_sha256", "binary"))
        parent = entry["parent_seed"]
        require(parent not in parent_identity or parent_identity[parent] == identity, "same_parent_five_arm_input")
        parent_identity[parent] = identity
        cache, scope = cache_binding(package, base, formal, entry, slot, plan)
        caches[name], evidence_scopes[name] = cache, scope
        row = cache["row"]
        output = {"name": name, "parent_seed": parent, "method": entry["method"], "status": receipt["status"],
                  "producer_admission": cache["status"], "primary_cost": None, "raw_recomputed_cost": None,
                  "closure_scope": "producer terminal declaration; failed owned-tree evidence may be incomplete or unknown"
                    if receipt["status"] != "complete" else "complete successful worker and owned process receipt",
                  "process_diagnostics": receipt["process"],
                  "worker_report_present": isinstance(receipt.get("worker"), dict),
                  "worker_report_status": (receipt.get("worker") or {}).get("status"),
                  "retained_worker_diagnostic_cost": (receipt.get("worker") or {}).get("cost")
                    if receipt["status"] != "complete" else None,
                  "worker_diagnostic_cost_rankable": False,
                  "coverage": "failed_or_blocked_retained_without_rankable_cost"}
        if receipt["status"] != "complete":
            require(row["full_window_cost"] is None and row["backlog_relief"] is None
                    and cache["status"] == "blocked",
                    "failed_attempt_cost_must_be_null")
        if slot.get("final_result") and slot.get("evaluation") and receipt["status"] == "complete":
            raw_ref = cache["raw_inventory"]["present"]["result"]
            require(raw_ref["path"] == slot["final_result"]["path"] and raw_ref["sha256"] == slot["final_result"]["sha256"],
                    "cache_actual_result_pin")
            result, evaluation = package.read(slot["final_result"]), package.read(slot["evaluation"])
            require(evaluation["parent"] == plan["parent"] and evaluation["method"] == plan["method"]
                    and evaluation["input_semantic_sha256"] == plan["input_semantic_sha256"], "formal_evaluation_identity")
            cost, relief, specs, completions = base.metrics(data, result, 7200., 59400.)
            require(result["physical_clock"] == 59400., "formal_exact_physical_endpoint")
            base.same(cost, evaluation["cost"], "raw_evaluation_cost")
            if receipt["worker"].get("cost") is not None:
                base.same(cost, receipt["worker"]["cost"], "raw_worker_cost")
            output["raw_recomputed_cost"] = cost
            output["coverage"] = "raw_cost_verified_but_formal_admission_blocked"
            if cache["status"] == "admitted_cost_and_physical_replay":
                base.closed_receipt(receipt)
                continuation = result["control_continuation"]
                require(continuation["status"] == "reached" and continuation["timestamp_complete"] is True
                        and continuation["physical_time"] == receipt["worker"]["final_physical_time"] == 59400.,
                        "formal_native_controller_worker_endpoints")
                base.same(cost, row["full_window_cost"], "admitted_cost")
                base.same(relief, {k: row["backlog_relief"][k] for k in relief}, "admitted_relief")
                physical = row["physical"]
                require(physical["native_invariant_counters"] == projection(result["native_summary"],
                    ("reservation_conflicts", "physical_fault_edge_entry_violation_count")),
                    "native_counters_match_included_raw")
                require(physical["native_invariant_status"] == "passed_reported_counters"
                        and set(physical["native_invariant_counters"]) ==
                        {"reservation_conflicts", "physical_fault_edge_entry_violation_count"}
                        and all(type(v) is int and v == 0 for v in physical["native_invariant_counters"].values())
                        and physical["lifecycle_capacity_replay"]["status"] == "passed"
                        and not row["missing_evidence"] and row["warmup_prefix"] is not None
                        and row["provenance"]["status"] == "bound_files_verified"
                        and row["provenance"]["actor_source_status"] == "fixed_actor_files_verified",
                        "producer_gate_physical_and_provenance_basis")
                output["primary_cost"] = cost
                output["coverage"] = "included_raw_cost_verified_and_bound_producer_admission"
            recomputed[name] = (specs, completions, cost)
        elif receipt["status"] == "complete":
            output["coverage"] = "complete_but_raw_not_fully_included_cost_unknown_in_package_audit"
        rows_out.append(output)
        del data
    grid = package.read(formal["grid_audit"])
    effects = package.read(formal["effects"])
    require(grid["schema"] == "g31.inventory_spi_offline_audit.v1" and grid["registered_run_count"] == 40
            and grid["registered_parent_count"] == 8 and grid["registered_method_count"] == 5
            and grid["source_manifest"] == formal["roster"] and effects["source_manifest"] == formal["roster"],
            "bound_formal_grid_and_effects")
    expected_cache_refs = {s["name"]: s["cache"] for s in formal["runs"]}
    require(grid["source_cached_audits"] == effects["source_cached_audits"] == expected_cache_refs,
            "same_forty_cached_audits")
    require(len(grid["rows"]) == 40 and len({r["name"] for r in grid["rows"]}) == 40, "grid_unique_40")
    for row in grid["rows"]:
        require(row == caches[row["name"]]["row"], "grid_exact_cached_row")
    require(grid.get("failures_omitted") == 0 and grid.get("missing_cells_imputed_as_zero") is False,
            "grid_no_failures_omitted_or_imputed")
    for value in (grid, effects):
        require(any(r["sha256"] == GATE_SHA for r in value["implementation"]), "grid_fixed_wrapper")
        for ref in value["implementation"]:
            package.mapped(ref)
    comparisons = {}
    for c in grid["comparisons"]:
        key = c["parent_seed"], c["reference_method"], c["candidate_method"]
        require(key not in comparisons, "unique_grid_comparison")
        comparisons[key] = c
    require(set(comparisons) == {(p, a, b) for p in PARENTS for a, b in combinations(METHODS, 2)},
            "all_eighty_comparisons")
    lookup = {(p["parent"]["parent_seed"], p["method"]): p["name"] for p in plans.values()}
    for (parent, a, b), c in comparisons.items():
        an, bn = lookup[(parent, a)], lookup[(parent, b)]
        require(c["reference"] == an and c["candidate"] == bn, "comparison_names")
        if c["status"] == "closed_same_parent_comparison":
            ar, br = caches[an]["row"], caches[bn]["row"]
            require(all(caches[n]["status"] == "admitted_cost_and_physical_replay" for n in (an, bn)),
                    "blocked_arm_cannot_supply_closed_comparison")
            for key in ("native_state_sha256", "controller_history_sha256", "at", "stage"):
                require(ar["warmup_prefix"][key] == br["warmup_prefix"][key], "same_saved_warmup")
            ac, bc = ar["full_window_cost"], br["full_window_cost"]
            gain = ac["backlog_integral_bag_seconds"]-bc["backlog_integral_bag_seconds"]
            base.same(gain, c["advantage_bag_seconds"], "comparison_J_gain")
            base.same(gain/ac["backlog_integral_bag_seconds"] if ac["backlog_integral_bag_seconds"] > 0 else None,
                      c["relative_J_gain"], "comparison_relative_gain")
            for name, field in (("completed_delta", "completed_by_end"), ("on_time_delta", "on_time_by_end"),
                                ("overdue_unfinished_delta", "arrived_unfinished_past_deadline")):
                base.same(bc[field]-ac[field], c[name], "comparison_service")
            if an in recomputed and bn in recomputed:
                sa, ca, _ = recomputed[an]; sb, cb, _ = recomputed[bn]
                require(sa == sb, "same_complete_job_specs")
                direction = full_direction(base, sa, ca, cb, 59400.)
                base.same(direction, projection(c["completion_direction"], direction.keys()), "raw_seven_directions")
        else:
            require(c["advantage_bag_seconds"] is None, "unmatched_comparison_no_gain")
    blocked = [r["name"] for r in grid["rows"] if caches[r["name"]]["status"] != "admitted_cost_and_physical_replay"]
    unmatched = [{"parent_seed": c["parent_seed"], "reference_method": c["reference_method"],
        "candidate_method": c["candidate_method"], "status": c["status"]} for c in grid["comparisons"]
        if c["status"] != "closed_same_parent_comparison"]
    validity = {"status": "all_forty_and_eighty_pairs_admitted" if not blocked and not unmatched
        else "blocked_failed_unknown_or_unmatched_evidence", "blocked_run_names": blocked,
        "unmatched_registered_comparisons": unmatched, "formal_algorithm_ranking_allowed": not blocked and not unmatched,
        "engineering_promotion_allowed_by_this_gate": False,
        "promotion_requires_separate_registered_service_support_gain_and_concentration_checks": True,
        "protected_takeover_authorized": False, "full_callback_protection_semantics_replayed": False}
    base.same(validity, grid["formal_admission"], "fixed_wrapper_admission")
    effect_scope = verify_effects(base, effects, grid, comparisons)
    return {"schema": SCHEMA, "status": "formal_package_bound_graph_and_numeric_basis_verified",
        "registered_cells": 40, "retained_cells": len(rows_out), "rows": rows_out,
        "included_raw_costs_recomputed": len(recomputed),
        "independent_primary_cost_coverage": sum(r["primary_cost"] is not None for r in rows_out),
        "producer_formal_admission": validity,
        "formal_ranking_fully_supported_by_included_raw_and_bound_receipts":
            validity["formal_algorithm_ranking_allowed"] and all(r["primary_cost"] is not None for r in rows_out),
        "freeze_audit": freeze, "effects_verification": effect_scope,
        "raw_inventory_coverage": evidence_scopes, "external_large_logs_rehashed_or_replayed": False,
        "physical_replay_scope": "Included hash-bound producer caches only; external native/control histories not reexecuted.",
        "engineering_promotion_authorized": False, "protected_takeover_authorized": False,
        "actual_training_or_dev_selection_reexecuted": False,
        "native_operations": 0, "fit_operations": 0, "git_operations": 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--base-validator", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.package.resolve()), "output_outside_package")
    began = time.perf_counter()
    base = load_base(args.base_validator)
    package = open_deferred(base, args.package, args.manifest_sha256)
    try:
        result = audit_formal(package, base)
        result.update(manifest_sha256=args.manifest_sha256, wall_seconds=time.perf_counter()-began,
                      included_unique_files=len(package.files), included_unique_bytes=package.included_bytes)
    finally:
        package.close()
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
