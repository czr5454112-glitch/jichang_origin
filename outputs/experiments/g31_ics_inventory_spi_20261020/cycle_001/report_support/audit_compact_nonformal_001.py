"""Independent nonformal costs/labels from a final package; stdlib only.

Only explicitly mapped objects are opened. No directory discovery, original-path
fallback, archived-code execution, formal outcome audit, fit or native execution.
The separately pinned formal auditor covers the formal forty cells.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time
import types
import zipfile

BASE_SHA = "7d60b20c1a4cdcee63b79f9477c96f6764e15e4908facd714b0e4fa45121271a"
SCHEMA = "g31.inventory_spi.compact_nonformal_audit.v1"
STAGE = "g31.inventory_spi_offline_stages.v1"
PAIR = "g31.foundation.airport_pair_dataset.v1"
OPEN = {"running", "prepared", "pending", "not_started", "not_closed"}


def require(ok, reason):
    if not ok:
        raise ValueError("compact_nonformal:" + reason)


def load_base(path):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == BASE_SHA, "pinned_base_validator")
    module = types.ModuleType("nonformal_pinned_base")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def open_mapped(base, path, manifest_sha):
    class MappedPackage(base.Package):
        def __init__(self):
            self.path = Path(path)
            self.zip = zipfile.ZipFile(path) if self.path.is_file() else None
            self.files, self.mapping, self.read_references = {}, {}, []
            raw = self.raw("PACKAGE_MANIFEST.json")
            require(base.sha_bytes(raw) == manifest_sha, "trusted_manifest_sha")
            self.manifest = base.decode(raw)
            require(self.manifest["schema"] == base.SCHEMA, "package_schema")
            for row in self.manifest["files"]:
                name = base.safe_name(row["package_path"])
                require(name not in self.files, "unique_manifest_object")
                self.files[name] = row
            for row in self.manifest["original_path_map"]:
                key = base.original_key(row["original_path"])
                require(key not in self.mapping, "unique_original_mapping")
                target = self.files[base.safe_name(row["package_path"])]
                require(row["sha256"] == target["sha256"], "mapping_content_sha")
                self.mapping[key] = target
            if self.zip:
                infos = [x for x in self.zip.infolist() if not x.is_dir()]
                names = [base.safe_name(x.filename) for x in infos]
                require(len(names) == len(set(names))
                        and all((x.external_attr >> 16) & 0o170000 != 0o120000 for x in infos),
                        "unique_nonsymlink_zip_members")

        def raw_reference(self, reference):
            row = self.mapped(reference)
            raw = self.raw(row["package_path"])
            require(len(raw) == row["bytes"] and base.sha_bytes(raw) == reference["sha256"],
                    "required_original_object_bytes")
            self.read_references.append(dict(reference))
            return raw

        def read(self, reference):
            raw = self.raw_reference(reference)
            if reference["path"].endswith(".gz"):
                with base.gzip.GzipFile(fileobj=base.io.BytesIO(raw)) as stream:
                    raw = stream.read(base.MAX_JSON + 1)
                    require(len(raw) <= base.MAX_JSON and stream.read(1) == b"",
                            "gzip_decoded_limit_and_tail")
            return base.decode(raw)
    return MappedPackage()


def terminal(base, receipt, plan):
    process = receipt.get("process") or {}
    require(isinstance(receipt.get("status"), str) and receipt["status"]
            and receipt["status"] not in OPEN
            and process.get("status") in ("exited", "hard_timeout")
            and receipt.get("plan_sha256") == plan["sha256"], "terminal_bound_attempt")
    if receipt["status"] == "complete":
        base.closed_receipt(receipt)


def roster_and_closures(package, base):
    manifest = package.manifest
    slots = manifest["runs"]
    require(len(slots) == 122 and len({s["name"] for s in slots}) == 122
            and len({base.original_key(s["plan"]["path"]) for s in slots}) == 122,
            "all_122_unique_actual_slots")
    require(Counter(s["role"] for s in slots)["formal"] == 40
            and Counter(s["role"] for s in slots)["round0_pair"] == 48
            and Counter(s["role"] for s in slots)["round1_pair"] == 24
            and all(s["role"] in {"formal", "round0_pair", "round1_pair", "diagnostic", "failed_attempt"}
                    for s in slots), "fixed_role_partition")
    ledger_raw = package.raw_reference(manifest["attempt_ledger"])
    require(ledger_raw.endswith(b"\n"), "complete_ledger_tail")
    ledger = [base.decode(line) for line in ledger_raw.splitlines() if line.strip()]
    require(all(r["kind"] in ("long_branch", "short_gate") for r in ledger), "ledger_kinds")
    longs = [r for r in ledger if r["kind"] == "long_branch"]
    require(len(longs) == 122 and len({r["name"] for r in longs}) == 122
            and {(r["name"], r["plan_sha256"]) for r in longs}
            == {(s["name"], s["plan"]["sha256"]) for s in slots}, "exact_ledger_run_roster")
    formal = [s for s in slots if s["role"] == "formal"]
    require({(s["name"], base.original_key(s["plan"]["path"]), s["plan"]["sha256"]) for s in formal}
            == {(s["name"], base.original_key(s["plan"]["path"]), s["plan"]["sha256"])
                for s in manifest["formal"]["runs"]}, "same_formal_metadata_partition")
    receipts = {}
    # No plan, input, dataset or outcome may be read before this entire loop.
    for slot in slots:
        receipt = package.read(slot["receipt"])
        terminal(base, receipt, slot["plan"])
        receipts[slot["name"]] = receipt
    return slots, receipts


def collection_pairs(package, base, slots):
    lookup = {base.original_key(s["plan"]["path"]): s for s in slots}
    pairs, used = [], set()
    for round_, count in ((0, 24), (1, 12)):
        reference = package.manifest["training"][f"round{round_}_collection"]
        collection = package.read(reference)
        require(collection["schema"] == STAGE + ".collection"
                and collection["status"] == "all_registered_attempts_collected"
                and collection["rollout_round"] == round_
                and collection["registered_pairs"] == len(collection["inputs"]) == count
                and collection["registered_arms"] == collection["closed_attempt_receipts"] == 2*count
                and collection["test_opened"] is False, "actual_full_pair_collection")
        manifest = package.read(collection["batch_manifest"])
        require(manifest["schema"] == STAGE + ".pair_batch" and manifest["rollout_round"] == round_
                and manifest["registered_pairs"] == len(manifest["slots"]) == count
                and manifest["registered_arms"] == 2*count, "bound_pair_manifest")
        registered = {r["pair_slot_id"]: r for r in manifest["slots"]}
        require(len(registered) == count
                and {r["pair_slot_id"] for r in collection["inputs"]} == set(registered),
                "unique_complete_pair_slots")
        arm_keys = set()
        for item in collection["inputs"]:
            slot = registered[item["pair_slot_id"]]
            refs = {"a_ref": item["reference_plan"], "a_patch": item["patched_plan"]}
            require(refs == slot["plans"] and item["parent"] == slot["parent"]
                    and item["parent"]["split"] in ("train", "dev")
                    and item["parent"].get("rollout_round", 0) == round_, "pair_parent_plan_binding")
            names = {}
            for branch, ref in refs.items():
                key = base.original_key(ref["path"])
                require(key not in used and key in lookup and lookup[key]["plan"] == ref
                        and lookup[key]["role"] == f"round{round_}_pair", "unique_registered_pair_arm")
                used.add(key); arm_keys.add(key); names[branch] = lookup[key]["name"]
            pairs.append({"round": round_, "item": item, "names": names,
                          "slots": {b: lookup[base.original_key(r["path"])] for b, r in refs.items()},
                          "collection": reference, "manifest": collection["batch_manifest"]})
        require(arm_keys == {base.original_key(s["plan"]["path"]) for s in slots
                            if s["role"] == f"round{round_}_pair"}, "all_pair_role_arms_collected")
    return pairs


def audit_arm(package, base, slot, receipt):
    """Return small report plus temporary numeric indices, never a model input."""
    output = {"name": slot["name"], "role": slot["role"], "attempt_status": receipt["status"],
              "status": "unavailable_failed_attempt", "cost": None, "backlog_relief": None,
              "failed_partial_cost_used": False}
    if receipt["status"] != "complete":
        output["closure_scope"] = {"process_status": receipt["process"]["status"],
                                   "exitcode": receipt["process"].get("exitcode")}
        return output, None
    try:
        plan = package.read(slot["plan"])
        require(plan["name"] == slot["name"] and plan["parent"]["split"] != "test"
                and plan["parent"]["parent_seed"] not in range(1301, 1309), "nonformal_plan_only")
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
        selected, branch = None, None
        if plan.get("pair") is None:
            require(slot["role"] == "diagnostic", "diagnostic_role_matches_plan")
            start, end = plan["cost_window"]
            expected = [evaluation["cost"], receipt["worker"]["cost"]]
        else:
            require(slot["role"] in ("round0_pair", "round1_pair"), "pair_role_matches_plan")
            branch = package.read(slot["branch_evidence"])
            start, end, selected = base.pair_window(plan, branch, result)
            require(branch["input_sha256"] == plan["input_semantic_sha256"]
                    and branch["policy_alignment"] == plan["pair"]["policy_alignment"]
                    and branch["continuation_version"] ==
                    branch["policy_alignment"]["continuation_policy_id"]
                    and selected["policy_alignment"] == branch["policy_alignment"]
                    and selected["continuation_version"] == branch["continuation_version"]
                    and selected["patch_rank"] == plan["pair"]["patch_rank"]
                    and selected["chosen_action"] == selected["opportunity"]["candidates"][
                        0 if branch["branch"] == "a_ref" else selected["patch_rank"]],
                    "pair_continuation_and_registered_action_binding")
            expected = [branch["cost"]]
        require(result["physical_clock"] == end == receipt["worker"]["final_physical_time"],
                "exact_final_cost_endpoint")
        cost, relief, specs, completed = base.metrics(data, result, start, end)
        for previous in expected:
            base.same(cost, previous, "saved_cost")
        if branch is not None:
            expected_jobs = {identity: {
                "arrival": spec["arrival"], "completed_at": completed.get(identity),
                "status": "completed" if identity in completed else
                "arrived_unfinished" if spec["arrival"] <= end else "not_yet_arrived"}
                for identity, spec in specs.items()}
            base.same(branch["job_outcomes"], expected_jobs, "raw_branch_job_outcomes")
        output.update(status="actual_cost_recomputed", cost=cost, backlog_relief=relief,
                      method=plan["method"], parent=plan["parent"], plan=slot["plan"],
                      full_population=len(specs))
        return output, {"specs": specs, "completed": completed, "cost": cost, "plan": plan,
                        "evaluation": evaluation, "selected": selected, "branch": branch}
    except (ValueError, KeyError, TypeError, OSError, EOFError) as exc:
        output.update(status="blocked_invalid_or_missing_raw_evidence", error=str(exc))
        return output, None


def compare(base, left, right, kind):
    a, b = left["plan"], right["plan"]
    ac, bc = left["cost"], right["cost"]
    require(left["specs"] == right["specs"]
            and a["parent"] == b["parent"] and a["binary"] == b["binary"]
            and a["input_semantic_sha256"] == b["input_semantic_sha256"]
            and a["source_manifest_sha256"] == b["source_manifest_sha256"]
            and ac["label_start"] == bc["label_start"] and ac["label_end"] == bc["label_end"],
            "same_input_parent_native_source_window")
    if kind == "pilot_pair":
        require(all(a.get(key) == b.get(key) for key in (
            "controller", "behavior_model", "model", "K_max", "P_per_root")),
            "same_pair_continuation_configuration")
        sa, sb = left["selected"], right["selected"]
        require(sa["branch"] == "a_ref" and sb["branch"] == "a_patch", "actual_pair_roles")
        for key in ("owner_id", "observed_at", "opportunity", "patch_rank", "prefix",
                    "baseline_decision", "policy_alignment", "continuation_version"):
            require(sa[key] == sb[key], "same_pair_root:" + key)
    elif kind == "R0_vs_C00":
        require({a["method"], b["method"]} == {"C00", "R0_current_stock_v1"},
                "actual_registered_R0_method_id")
        for key in ("native_state_sha256", "controller_history_sha256", "at", "stage"):
            require(left["evaluation"]["warmup_prefix"][key]
                    == right["evaluation"]["warmup_prefix"][key], "same_saved_warmup")
    elif kind == "recovery_on_vs_off":
        require({key for key in a["controller"].keys() | b["controller"].keys()
                 if a["controller"].get(key) != b["controller"].get(key)} == {"recover_failed_empty"},
                "only_registered_recovery_option")
    else:
        raise ValueError("compact_nonformal:unregistered_comparison_kind")
    direction = base.directions(left["specs"], left["completed"], right["completed"], ac["label_end"])
    return {"J_reference_minus_candidate": ac["backlog_integral_bag_seconds"] - bc["backlog_integral_bag_seconds"],
            "completed_change": bc["completed_by_end"] - ac["completed_by_end"],
            "on_time_change": bc["on_time_by_end"] - ac["on_time_by_end"],
            "overdue_unfinished_change": bc["arrived_unfinished_past_deadline"] - ac["arrived_unfinished_past_deadline"],
            "direction": direction, "full_prefix_or_warmup_replayed": False,
            "strict_nonharm_certified": False, "learning_gain_demonstrated": False}


def verify_pair_dataset(package, base, pair, indices):
    item, names = pair["item"], pair["names"]
    dataset = package.read(item["dataset"])
    require(dataset["schema"] == PAIR and dataset["pair"]["schema"] == PAIR,
            "actual_pair_dataset_schema")
    provenance = dataset["collection_provenance"]
    require(provenance["batch_manifest"] == pair["manifest"]
            and provenance["pair_slot_id"] == item["pair_slot_id"]
            and provenance["plans"] == {"a_ref": item["reference_plan"], "a_patch": item["patched_plan"]},
            "actual_dataset_provenance")
    require(provenance["attempt_receipts"] == {b: s["receipt"] for b, s in pair["slots"].items()}
            and provenance["branch_evidence"] == {b: s["branch_evidence"] for b, s in pair["slots"].items()
                                                  if s.get("branch_evidence") is not None},
            "dataset_actual_raw_evidence_bindings")
    output = {"round": pair["round"], "pair_slot_id": item["pair_slot_id"], "parent": item["parent"],
              "dataset": item["dataset"], "reference": names["a_ref"], "candidate": names["a_patch"],
              "status": "unknown_unavailable_arm", "J_reference_minus_candidate": None}
    left, right = (indices[name] for name in (names["a_ref"], names["a_patch"]))
    if left is None or right is None:
        require(dataset["rows"] == [] and dataset["pair"]["status"] != "closed_actual_pair",
                "unavailable_actual_pair_has_no_labels")
        output["saved_pair_status"] = dataset["pair"]["status"]
        return output
    require(left["plan"]["parent"] == right["plan"]["parent"] == item["parent"],
            "actual_arm_parent_matches_collection")
    result = compare(base, left, right, "pilot_pair")
    saved, rows = dataset["pair"], dataset["rows"]
    require(saved["status"] == "closed_actual_pair" and saved["parent"] == item["parent"]
            and len(rows) == 2 and [r["branch"] for r in rows] == ["a_ref", "a_patch"],
            "two_closed_actual_labels")
    require(saved["pair_id"] == base.digest({"parent": item["parent"],
            "prefix": left["selected"]["prefix"], "patch": right["selected"]["chosen_action"]}),
            "actual_pair_identity")
    for key, index in (("reference_cost", left), ("patched_cost", right)):
        base.same(saved[key], index["cost"], "dataset_" + key)
    base.same(saved["advantage_bag_seconds"], result["J_reference_minus_candidate"], "dataset_pair_gain")
    direction = saved["censored_direction_summary"]
    for key, value in result["direction"].items():
        base.same(value, direction[key], "dataset_direction_" + key)
    require(direction["cutoff"] == left["cost"]["label_end"]
            and dataset["unused_candidates_have_labels"] is False
            and dataset["unused_candidate_count"] == left["selected"]["opportunity"]["K"] - 2,
            "censor_cutoff_and_unexecuted_labels")
    for row, index in zip(rows, (left, right)):
        require(row["schema"] == PAIR and row["parent"] == item["parent"] and row["pair_id"] == saved["pair_id"]
                and row["unexecuted_candidate_label"] is False, "actual_row_identity")
        base.same(row["target_return"], index["cost"]["target_return"], "actual_return")
        base.same(row["paired_advantage_bag_seconds"], result["J_reference_minus_candidate"], "row_advantage")
        for key in ("observation", "opportunity", "baseline_decision"):
            require(row[key] == index["selected"][key], "actual_row_root:" + key)
        require(row["action"] == index["selected"]["chosen_action"]
                and row["actual_execution"] == index["branch"]["execution"]
                and row.get("forecast_evidence") == index["selected"].get("forecast_evidence"),
                "actual_row_action_and_information")
    output.update(result, status="actual_pair_cost_labels_and_seven_directions_verified",
                  unused_candidate_labels_unknown=dataset["unused_candidate_count"])
    return output


def audit_view(package, base):
    slots, receipts = roster_and_closures(package, base)
    pairs = collection_pairs(package, base, slots)
    nonformal = {s["name"]: s for s in slots if s["role"] != "formal"}
    require(len(nonformal) == 82, "complete_nonformal_denominator")
    reports, pair_reports, diagnostic_indices = {}, [], {}
    for pair in pairs:
        indices = {}
        for name in pair["names"].values():
            reports[name], indices[name] = audit_arm(package, base, nonformal[name], receipts[name])
        try:
            pair_reports.append(verify_pair_dataset(package, base, pair, indices))
        except (ValueError, KeyError, TypeError, OSError, EOFError) as exc:
            pair_reports.append({"round": pair["round"], "pair_slot_id": pair["item"]["pair_slot_id"],
                "reference": pair["names"]["a_ref"], "candidate": pair["names"]["a_patch"],
                "status": "blocked_invalid_pair_labels", "error": str(exc),
                "J_reference_minus_candidate": None})
        del indices
    for name, slot in nonformal.items():
        if name not in reports:
            reports[name], diagnostic_indices[name] = audit_arm(package, base, slot, receipts[name])
    comparisons = []
    for declared in package.manifest.get("comparisons", []):
        names = (declared["reference"], declared["candidate"])
        require(names[0] != names[1] and all(name in nonformal for name in names),
                "declared_nonformal_comparison_only")
        require(declared["kind"] in {"pilot_pair", "R0_vs_C00", "recovery_on_vs_off"},
                "known_registered_comparison_kind")
        if declared["kind"] == "pilot_pair":
            matches = [p for p in pair_reports if (p.get("reference"), p.get("candidate")) == names]
            require(len(matches) == 1, "declared_pair_in_actual_collection")
            comparisons.append({**declared, "status": matches[0]["status"],
                                "pair_audit_status": matches[0]["status"]})
            continue
        require(all(name in diagnostic_indices for name in names), "diagnostic_comparison_arms")
        if any(diagnostic_indices[name] is None for name in names):
            comparisons.append({**declared, "status": "unknown_unavailable_arm",
                                "J_reference_minus_candidate": None})
            continue
        try:
            comparisons.append({**declared, **compare(base, *(diagnostic_indices[n] for n in names),
                                                      declared["kind"]), "status": "registered_comparison_verified"})
        except (ValueError, KeyError, TypeError) as exc:
            comparisons.append({**declared, "status": "blocked_invalid_comparison", "error": str(exc),
                                "J_reference_minus_candidate": None})
    invalid = any(r["status"].startswith("blocked") for r in
                  [*reports.values(), *pair_reports, *comparisons])
    return {"schema": SCHEMA, "status": "blocked_invalid_evidence" if invalid else
            "nonformal_included_numeric_evidence_verified_with_failures_retained",
            "registered_all_native_attempts": 122, "terminal_receipts_checked": len(receipts),
            "formal_metadata_only_cells": 40, "formal_costs_recomputed": 0,
            "registered_nonformal_attempts": 82, "retained_nonformal_attempts": len(reports),
            "recomputed_complete_nonformal_costs": sum(r["cost"] is not None for r in reports.values()),
            "run_status_counts": dict(Counter(r["status"] for r in reports.values())),
            "registered_pairs": 36, "pair_status_counts": dict(Counter(r["status"] for r in pair_reports)),
            "runs": list(reports.values()), "pairs": pair_reports,
            "registered_diagnostic_comparisons_only": comparisons,
            "read_references": package.read_references,
            "scope": "Full-population numeric costs and observed pair labels only; formal forty audited separately.",
            "direction_scope": "Seven categories and known harm/improvement counts; saved per-job rows, "
                               "censored magnitude bounds and transitions are not independently replayed here.",
            "source_and_native_provenance_scope": "Hash-bound manifests/maps; no executable or archived source execution.",
            "directory_inventory_scanned": False, "all_package_bytes_rehashed": False,
            "physical_or_callback_protection_replay": False, "engineering_promotion_authorized": False,
            "protected_takeover_authorized": False, "native_operations": 0, "fit_operations": 0,
            "formal_inputs_or_outcomes_opened": False, "original_absolute_paths_opened": False}


def audit(path, manifest_sha, base_path):
    started = time.perf_counter()
    base = load_base(base_path)
    package = open_mapped(base, path, manifest_sha)
    try:
        report = audit_view(package, base)
        report.update(manifest_sha256=manifest_sha, base_validator_sha256=BASE_SHA,
                      auditor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                      wall_seconds=time.perf_counter() - started)
        return report
    finally:
        package.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--base-validator", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists() and not args.output.resolve().is_relative_to(args.package.resolve()),
            "fresh_output_outside_package")
    result = audit(args.package, args.manifest_sha256, args.base_validator)
    with args.output.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"output": str(args.output), "status": result["status"],
                      "recomputed": result["recomputed_complete_nonformal_costs"],
                      "pair_status_counts": result["pair_status_counts"]}, ensure_ascii=False))
