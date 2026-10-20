"""Portable, read-only stdlib auditor. Never opens original absolute paths.

Audit a directory (or ZIP) containing PACKAGE_MANIFEST.json. Included objects
are original bytes in a content store, resolved through an explicit absolute
author-path map. Archived Python/native sources are hashed, never imported.
Missing external logs are outside this audit, even when an earlier receipt is
included. The manifest hash must come from an independent trusted channel.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath, PureWindowsPath
import time
import zipfile

SCHEMA = "g31.inventory_spi.compact_package.v1"
MAX_FILE = 32 * 1024**2
MAX_JSON = 256 * 1024**2
CATEGORIES = ("exact_harmed", "exact_improved", "exact_equal",
              "reference_only_finished", "candidate_only_finished",
              "both_arrived_unfinished", "both_not_yet_arrived")


def require(condition, message):
    if not condition:
        raise ValueError("compact_audit:" + message)


def sha_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha_bytes(json.dumps(value, sort_keys=True, ensure_ascii=False,
                               allow_nan=False, separators=(",", ":")).encode("utf8"))


def safe_name(name):
    require(isinstance(name, str) and name and "\\" not in name and ":" not in name,
            "unsafe_package_path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(p not in ("", ".", "..") for p in name.split("/")),
            "unsafe_package_path")
    return name


def original_key(value):
    require(isinstance(value, str), "original_path_string")
    path = PureWindowsPath(value)
    if path.is_absolute():
        require(".." not in path.parts, "original_path_no_parent_escape")
        return path.as_posix().casefold()
    path = PurePosixPath(value)
    require(path.is_absolute() and ".." not in path.parts, "absolute_original_path")
    return str(path)


def original_join(root, relative):
    safe_name(relative)
    if PureWindowsPath(root).is_absolute():
        return str(PureWindowsPath(root) / PurePosixPath(relative))
    return str(PurePosixPath(root) / relative)


def decode(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            require(key not in out, "duplicate_json_key")
            out[key] = value
        return out
    def invalid(value):
        raise ValueError("compact_audit:nonfinite_json:" + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "finite_number")
    return value


def same(a, b, path="value"):
    if isinstance(a, dict):
        require(isinstance(b, dict) and a.keys() == b.keys(), "same_keys:" + path)
        for key in a:
            same(a[key], b[key], path+"."+key)
    elif isinstance(a, list):
        require(isinstance(b, list) and len(a) == len(b), "same_list:" + path)
        for i, (left, right) in enumerate(zip(a, b)):
            same(left, right, path+"."+str(i))
    elif type(a) in (int, float):
        require(type(b) in (int, float) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-6),
                "same_number:" + path)
    else:
        require(type(a) is type(b) and a == b, "same_scalar:" + path)


class Package:
    def __init__(self, path, manifest_sha256):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(path) if self.path.is_file() else None
        if self.zip:
            infos = [x for x in self.zip.infolist() if not x.is_dir()]
            names = [safe_name(x.filename) for x in infos]
            require(len(names) == len(set(names)), "duplicate_zip_member")
            require(all((x.external_attr >> 16) & 0o170000 != 0o120000 for x in infos),
                    "zip_symlink_forbidden")
        else:
            require(self.path.is_dir(), "package_directory")
            paths = list(self.path.rglob("*"))
            require(not any(p.is_symlink() for p in paths), "directory_symlink_forbidden")
            names = [safe_name(p.relative_to(self.path).as_posix()) for p in paths if p.is_file()]
        raw = self.raw("PACKAGE_MANIFEST.json")
        require(sha_bytes(raw) == manifest_sha256, "trusted_manifest_sha256")
        self.manifest = decode(raw)
        require(self.manifest["schema"] == SCHEMA, "manifest_schema")
        self.files = {}
        for row in self.manifest["files"]:
            name = safe_name(row["package_path"])
            require(name not in self.files, "duplicate_file_manifest")
            self.files[name] = row
        require(set(names) == {*self.files, "PACKAGE_MANIFEST.json"}, "exact_package_inventory")
        self.mapping = {}
        for row in self.manifest["original_path_map"]:
            key = original_key(row["original_path"])
            require(key not in self.mapping, "duplicate_original_mapping")
            target = self.files[safe_name(row["package_path"])]
            require(row["sha256"] == target["sha256"], "mapping_content_sha")
            self.mapping[key] = target
        require(set(x["package_path"] for x in self.manifest["original_path_map"]) == set(self.files),
                "every_included_file_has_original_mapping")
        total = 0
        for name, row in self.files.items():
            raw = self.raw(name)
            require(len(raw) == row["bytes"] and sha_bytes(raw) == row["sha256"], "included_raw_sha:"+name)
            total += len(raw)
        self.included_bytes = total

    def close(self):
        if self.zip:
            self.zip.close()

    def raw(self, name):
        safe_name(name)
        if self.zip:
            require(self.zip.getinfo(name).file_size <= MAX_FILE, "file_size_limit")
            with self.zip.open(name) as stream:
                raw = stream.read(MAX_FILE+1)
                require(stream.read(1) == b"", "zip_member_tail")
        else:
            path = self.path / name
            require(path.resolve().is_relative_to(self.path.resolve()) and not path.is_symlink(),
                    "package_path_escape")
            require(path.stat().st_size <= MAX_FILE, "file_size_limit")
            raw = path.read_bytes()
        require(len(raw) <= MAX_FILE, "file_size_limit")
        return raw

    def mapped(self, reference):
        row = self.mapping.get(original_key(reference["path"]))
        require(row is not None, "required_original_not_in_package:"+reference["path"])
        require(row["sha256"] == reference["sha256"], "dependency_reference_sha")
        return row

    def read(self, reference):
        row = self.mapped(reference)
        raw = self.raw(row["package_path"])
        require(sha_bytes(raw) == reference["sha256"], "bytes_changed_after_inventory")
        if reference["path"].endswith(".gz"):
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(MAX_JSON+1)
                require(len(raw) <= MAX_JSON and stream.read(1) == b"", "gzip_decoded_limit")
        return decode(raw)


def metrics(data, result, start, end, *, expected_population=28506):
    """Independent population/receipt index and finite-window arithmetic."""
    number(start); number(end)
    clock = number(result["physical_clock"])
    require(0 <= start < end <= clock and result["advance"]["status"] == "reached"
            and result["advance"]["horizon_complete"] is True, "closed_native_window")
    specs = {r["business_bag_id"]: r for r in data["jobs"]}
    states = {r["business_bag_id"]: r for r in result["jobs"]}
    require(len(specs) == len(data["jobs"]) == len(states) == len(result["jobs"]) == expected_population
            and specs.keys() == states.keys(), "full_unique_population")
    arrivals, completed, loads = {}, {}, {}
    for receipt in result["receipts"]:
        at = number(receipt["time"])
        require(0 <= at <= clock, "receipt_closed_clock")
        lookup = {"BAG_ARRIVAL": arrivals, "UNLOAD_COMPLETE": completed, "LOAD_START": loads}.get(receipt["event"])
        if lookup is not None:
            identity = receipt["business_bag_id"]
            require(identity in specs and identity not in lookup, "unique_receipt_business")
            lookup[identity] = at
    for identity, spec in specs.items():
        arrival = number(spec["arrival"]); number(spec["deadline"])
        state = states[identity]
        require(arrival >= 0 and (identity in arrivals) == (arrival <= clock)
                == (state["status"] != "unreleased"), "arrival_population_status")
        if identity in arrivals:
            require(arrivals[identity] == arrival, "actual_arrival_binding")
        at = number(state["completed_at"])
        require((at >= 0) == (identity in completed) == (state["status"] == "completed"),
                "completion_status_binding")
        if identity in completed:
            require(arrival <= completed[identity] == at <= clock, "actual_completion_binding")
        if identity in loads:
            require(arrival <= loads[identity] <= completed.get(identity, clock), "actual_load_clock")
    require(result["population"]["observed"] == len(arrivals)
            and result["population"]["completed"] == len(completed), "native_population_counts")
    j = math.fsum(max(0., min(end, completed.get(k, math.inf))-max(start, s["arrival"]))
                  for k, s in specs.items())
    j0 = math.fsum(max(0., end-max(start, s["arrival"])) for s in specs.values())
    arrived = {k for k, s in specs.items() if s["arrival"] <= end}
    finished = {k: at for k, at in completed.items() if at <= end}
    load_complete = all(s["status"] in ("unreleased", "waiting_for_tray") or k in loads
                        for k, s in states.items())
    wait = (math.fsum(max(0., min(end, loads.get(k, math.inf))-max(start, s["arrival"]))
                     for k, s in specs.items()) if load_complete else None)
    cost = dict(label_start=start, label_end=end, horizon_seconds=end-start,
        backlog_integral_bag_seconds=j, target_return=-j, physical_population=len(specs),
        arrived_by_end=len(arrived), not_yet_arrived_by_end=len(specs)-len(arrived),
        completed_by_end=len(finished), arrived_unfinished_by_end=len(arrived)-len(finished),
        on_time_by_end=sum(at <= specs[k]["deadline"] for k, at in finished.items()),
        arrived_unfinished_past_deadline=sum(k not in finished and specs[k]["deadline"] < end for k in arrived),
        completion_times_unknown_for_arrived=len(arrived)-len(finished), completion_times_imputed=False,
        right_censored_for_integral_only=True, waiting_for_tray_integral_bag_seconds=wait,
        loaded_or_processing_integral_bag_seconds=j-wait if wait is not None else None,
        wait_load_decomposition_status="actual_LOAD_START_receipts" if load_complete else "unknown_missing_actual_load_start",
        per_job_nonharm_certified=False, uncompleted_jobs_excluded=0)
    return cost, dict(J0_bag_seconds=j0, J_bag_seconds=j, relief_bag_seconds=j0-j), specs, finished


def directions(specs, a, b, cutoff):
    counts = dict.fromkeys(CATEGORIES, 0)
    for identity, spec in specs.items():
        left, right = a.get(identity), b.get(identity)
        if left is not None and right is not None:
            delta = right-left
            category = "exact_harmed" if delta > 1e-6 else "exact_improved" if delta < -1e-6 else "exact_equal"
        elif left is not None:
            category = "reference_only_finished"
        elif right is not None:
            category = "candidate_only_finished"
        else:
            category = "both_arrived_unfinished" if spec["arrival"] <= cutoff else "both_not_yet_arrived"
        counts[category] += 1
    require(sum(counts.values()) == len(specs), "direction_complete_population")
    return {"categories": counts, "population": len(specs),
            "known_direction_harm": counts["exact_harmed"]+counts["reference_only_finished"],
            "known_direction_improvement": counts["exact_improved"]+counts["candidate_only_finished"],
            "strict_per_job_nonharm_certified": False}


def validate_source(package, reference, semantic_sha):
    source = package.read(reference)
    require(digest(source["files"]) == source["source_manifest_sha256"] == semantic_sha,
            "source_manifest_semantic_pin")
    for name, expected in source["files"].items():
        package.mapped({"path": original_join(source["root"], name), "sha256": expected})
    return len(source["files"])


def pair_window(plan, branch, result):
    selected = branch["selected"]
    require(isinstance(selected, dict) and branch["status"] == "closed_full_window",
            "closed_selected_pair")
    start, end = branch["cost"]["label_start"], branch["cost"]["label_end"]
    require(branch["parent"] == plan["parent"] and branch["branch"] == plan["pair"]["branch"]
            and selected["branch"] == branch["branch"]
            and selected["parent"] == plan["parent"]
            and plan["pair"]["window"][0] <= start == selected["observed_at"] <= plan["pair"]["window"][1]
            and end == start+1800. and selected["label_start"] == start and selected["label_end"] == end
            and branch["final_physical_time"] == result["physical_clock"], "actual_pair_label_identity")
    prefix = selected["prefix"]
    require(prefix["complete_prefix_sha256"] == digest({k: v for k, v in prefix.items()
            if k != "complete_prefix_sha256"}) and prefix["physical_time"] == start
            and prefix["owner_id"] == selected["owner_id"], "saved_complete_prefix_digest")
    return start, end, selected


def validate_freeze(package, reference):
    """Hash/identity/pretest declaration audit; no replay of training/selection."""
    frozen = package.read(reference)
    require(frozen["schema"] == "g31.foundation.airport_spi_training_campaign.v1.freeze"
            and frozen["status"] == "all_requested_champions_frozen_before_test"
            and frozen["test_opened"] is False, "pretest_freeze_declaration")
    campaign = package.read(frozen["campaign"])
    require(campaign["contract"] == frozen["contract"]
            and campaign["source_sha256"] == frozen["source_sha256"], "frozen_campaign_identity")
    for logical, expected in frozen["source_sha256"].items():
        archive = campaign["source_archive"][logical]
        require(archive["sha256"] == archive["archive"]["sha256"] == expected, "frozen_source_pin")
        package.mapped(archive["archive"])
    require(len(frozen["models"]) == 2 and {m["information_variant"] for m in frozen["models"]} == {"C01", "C11"},
            "two_variant_freeze")
    planned = {(original_key(r["path"]), r["sha256"]) for r in campaign["chain_plans"]}
    started = completed = 0
    for row in frozen["models"]:
        model, receipt, selection = (package.read(row[k]) for k in ("checkpoint", "chain_receipt", "selection"))
        plan_ref = receipt["chain_plan"]
        require((original_key(plan_ref["path"]), plan_ref["sha256"]) in planned, "registered_training_chain")
        plan = package.read(plan_ref)
        require(model["model_id"] == row["model_id"] == selection["selected_model_id"]
                == digest({k: v for k, v in model.items() if k != "model_id"}), "frozen_weight_identity")
        require(model["schema"] == "g31.foundation.airport_supported_difference_ranker.v1"
                and model["information_variant"] == row["information_variant"] == plan["information_variant"]
                and model["contract"] == frozen["contract"]
                and receipt["selected_model"] == row["checkpoint"] and receipt["selection"] == row["selection"]
                and receipt["status"] == "closed"
                and selection["test_used_for_selection"] is False and selection["frozen_before_test"] is True
                and selection["reference_champion"] == row["reference_champion"] == model["reference_champion"],
                "dev_selection_receipt_binding")
        require(0 <= receipt["fit_calls_completed"] <= receipt["fit_calls_started"] <= plan["fit_calls_planned"],
                "finite_fit_count")
        started += receipt["fit_calls_started"]; completed += receipt["fit_calls_completed"]
    require(started == frozen["fit_calls_started"] and completed == frozen["fit_calls_completed"],
            "freeze_fit_denominators")
    return {"status": "included_freeze_dependencies_and_weights_hash_verified",
            "fit_calls_started": started, "fit_calls_completed": completed,
            "training_reexecuted": False, "dev_selection_recomputed": False,
            "pretest_chronology_scope": "bound producer declarations; no external wall-clock attestation"}


def validate_roster(manifest):
    names = [r["name"] for r in manifest["runs"]]
    plans = [original_key(r["plan"]["path"]) for r in manifest["runs"]]
    require(len(names) == len(set(names)) and len(plans) == len(set(plans)),
            "unique_run_names_and_plan_paths")
    for pair in manifest["comparisons"]:
        require(pair["reference"] != pair["candidate"] and pair["reference"] in names
                and pair["candidate"] in names, "distinct_registered_comparison_arms")


def closed_receipt(receipt):
    process = receipt["process"]
    require(receipt["status"] == "complete" and process["status"] == "exited"
            and type(process["exitcode"]) is int and process["exitcode"] == 0
            and process["windows_job_kill_on_close"] is True
            and process["child_released_only_after_job_assignment"] is True
            and receipt["worker"]["status"] == "complete", "closed_run_before_outcome")


def accepted_native(contract, expected):
    require(contract["schema"] == "g31.native030.inventory_spi_accepted_contract.v1"
            and contract["status"] in ("passed", "passed_with_retained_fixture_failure")
            and contract["binary"]["sha256"] == expected, "accepted_native_binary_pin")


def audit(path, manifest_sha256):
    began = time.perf_counter()
    package = Package(path, manifest_sha256)
    try:
        manifest = package.manifest
        validate_roster(manifest)
        runs, indices = [], {}
        for slot in manifest["runs"]:
            receipt = package.read(slot["receipt"])
            closed_receipt(receipt)
            plan = package.read(slot["plan"])
            require(receipt["plan_sha256"] == slot["plan"]["sha256"], "receipt_plan_pin")
            require(plan["name"] == slot["name"], "unique_plan_name")
            require(plan["parent"]["parent_seed"] not in range(1301, 1309)
                    or manifest.get("formal_unlock") is not None, "formal_unlock_required")
            # Formal expansion must supply and validate its freeze graph first.
            if plan["parent"]["parent_seed"] in range(1301, 1309):
                raise ValueError("compact_audit:formal_expansion_not_yet_enabled")
            package.mapped(plan["binary"])
            native_contract = package.read(plan["native_acceptance"])
            accepted_native(native_contract, plan["binary"]["sha256"])
            for field in ("forecast_binding", "event_calibration"):
                if plan.get(field):
                    package.mapped(plan[field])
            source_count = validate_source(package, plan["source_bundle"], plan["source_manifest_sha256"])
            data = package.read(plan["input"])
            require(digest(data) == plan["input_semantic_sha256"], "input_semantic_pin")
            result = package.read(slot["final_result"])
            evaluation = package.read(slot["evaluation"])
            require(evaluation["status"] == "complete" and evaluation["parent"] == plan["parent"]
                    and evaluation["method"] == plan["method"]
                    and evaluation["input_semantic_sha256"] == plan["input_semantic_sha256"],
                    "evaluation_identity")
            if plan.get("pair") is None:
                start, end = plan["cost_window"]
                expected = [evaluation["cost"], receipt["worker"]["cost"]]
                selected = None
            else:
                branch = package.read(slot["branch_evidence"])
                start, end, selected = pair_window(plan, branch, result)
                expected = [branch["cost"]]
            require(result["physical_clock"] == end == receipt["worker"]["final_physical_time"],
                    "exact_closed_cost_endpoint")
            cost, relief, specs, completions = metrics(data, result, start, end)
            for previous in expected:
                same(cost, previous, "saved_cost")
            events = Counter(r["event"] for r in result["receipts"])
            runs.append({"name": plan["name"], "parent_seed": plan["parent"]["parent_seed"],
                "method": plan["method"], "population": len(specs), "cost": cost, "backlog_relief": relief,
                "source_file_pins_verified": source_count, "raw_native_summary": result.get("native_summary"),
                "failed_leg_receipts": events["LEG_FAILED"], "recovery_receipts": events["EMPTY_RECOVERY_GRANTED"],
                "recovery_rejection_receipts": events["RECOVERY_REJECTED"],
                "quarantined_final_trays": sum(r.get("mode") == "quarantined" for r in result["trays"]),
                "raw_final_gzip_crc_and_tail": True, "native_physical_replay": False})
            indices[plan["name"]] = (specs, completions, cost, plan, evaluation, selected)
            del result, data
        comparisons = []
        for contrast in manifest["comparisons"]:
            sa, ca, ac, ap, ae, selected_a = indices[contrast["reference"]]
            sb, cb, bc, bp, be, selected_b = indices[contrast["candidate"]]
            require(sa == sb and ap["input_semantic_sha256"] == bp["input_semantic_sha256"]
                    and ap["parent"] == bp["parent"] and ap["binary"] == bp["binary"]
                    and ap["source_manifest_sha256"] == bp["source_manifest_sha256"]
                    and ac["label_start"] == bc["label_start"] and ac["label_end"] == bc["label_end"],
                    "comparison_same_input_parent_source_native_window")
            if contrast["kind"] == "R0_vs_C00":
                for field in ("native_state_sha256", "controller_history_sha256", "at", "stage"):
                    require(ae["warmup_prefix"][field] == be["warmup_prefix"][field], "saved_common_warmup")
            elif contrast["kind"] == "recovery_on_vs_off":
                differences = {k for k in ap["controller"].keys() | bp["controller"].keys()
                               if ap["controller"].get(k) != bp["controller"].get(k)}
                require(differences == {"recover_failed_empty"}, "only_declared_recovery_option")
            elif contrast["kind"] == "pilot_pair":
                require(selected_a["branch"] == "a_ref" and selected_b["branch"] == "a_patch",
                        "pair_branch_roles")
                for key in ("owner_id", "observed_at", "opportunity", "patch_rank", "prefix",
                            "baseline_decision", "policy_alignment", "continuation_version"):
                    require(selected_a[key] == selected_b[key], "saved_same_pair_root:"+key)
            else:
                raise ValueError("compact_audit:unknown_comparison_kind")
            direction = directions(sa, ca, cb, ac["label_end"])
            by_origin = {}
            for origin in sorted({r["origin"] for r in sa.values()}):
                subset = {k: r for k, r in sa.items() if r["origin"] == origin}
                by_origin[str(origin)] = directions(subset, ca, cb, ac["label_end"])
            comparisons.append({**contrast, "J_gain_bag_seconds": ac["backlog_integral_bag_seconds"]-bc["backlog_integral_bag_seconds"],
                "completed_delta": bc["completed_by_end"]-ac["completed_by_end"],
                "on_time_delta": bc["on_time_by_end"]-ac["on_time_by_end"],
                "direction": direction, "direction_by_origin": by_origin,
                "whole_policy_or_protocol_comparison_only": True,
                "common_history_fully_replayed": False, "single_action_causal_claim": False})
        frozen = [validate_freeze(package, r) for r in manifest.get("training_freezes", [])]
        for row in manifest.get("superseded_manifests", []):
            package.mapped(row["reference"]); package.mapped(row["replacement"])
            require(row["status"] == "superseded_not_executed_manifest"
                    and row.get("scope"), "explicit_superseded_scope")
        return {"schema": SCHEMA+".audit", "status": "included_bytes_and_full_population_costs_verified",
            "manifest_sha256": manifest_sha256, "included_unique_files": len(package.files),
            "original_path_mappings": len(package.mapping), "included_unique_bytes": package.included_bytes,
            "recomputed_run_count": len(runs),
            "runs": runs, "comparisons": comparisons, "training_freezes": frozen,
            "training_scope": "not_present" if not frozen else "hash_identity_and_bound_pretest_declarations",
            "excluded_large_log_count": sum(r.get("category") == "local_large_evidence"
                for r in manifest.get("excluded_large_logs", [])),
            "excluded_large_log_existing_count": sum(r.get("category") == "local_large_evidence"
                and r.get("status") != "missing_registered_file" for r in manifest.get("excluded_large_logs", [])),
            "missing_optional_small_artifact_count": sum(r.get("category") != "local_large_evidence"
                and r.get("status") == "missing_registered_file" for r in manifest.get("excluded_large_logs", []))
                + len(manifest.get("missing_optional_small_artifacts", [])),
            "excluded_large_log_bytes_read": 0, "excluded_large_log_content_verified": False,
            "prior_receipt_scope": "receipt bytes verified only; excluded logs not independently reverified here",
            "endpoint_scope": "This sample auditor accepts exact final physical time == label end only.",
            "no_fallback_to_author_absolute_paths": True, "native_operations": 0, "fit_operations": 0,
            "frozen_sources_executed": False, "heldout_opened": False,
            "wall_seconds": time.perf_counter()-began}
    finally:
        package.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = audit(args.package, args.manifest_sha256)
    text = json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)+"\n"
    if args.output:
        require(not args.output.resolve().is_relative_to(args.package.resolve()), "audit_output_outside_package")
        with args.output.open("x", encoding="utf8", newline="\n") as stream:
            stream.write(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
