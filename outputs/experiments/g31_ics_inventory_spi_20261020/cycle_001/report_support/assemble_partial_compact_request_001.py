"""Explicit partial-publication request preparation; never launches or packages.

The full assembler remains immutable. Only ledger, roster, cutoff and receipt
metadata are read before classifying every actual attempt. The sole named
historical unknown failure remains metadata-only; other nonformal attempts must
be terminal. Formal unknown/unstarted cells retain null evidence.
Exact caller-supplied receipt snapshots prevent reads of changing live receipts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import hashlib
import io
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
SCHEMA = "g31.inventory_spi.partial_request_assembler.v1"
FULL_NAME = "assemble_final_compact_request_002.py"
FULL_SHA = "c2e973bf7de3d6ba0457aaac745055b96c8fe1be69853b8c8575bcb84b2b5501"
PARTIAL_SHA = "4a15bf00003063fdf6a35ce566e733e322a08b76a7b48b82369eec6057f5501b"
HISTORICAL_UNKNOWN = "D_N22_C00_P901_001"


def require(ok, reason):
    if not ok:
        raise ValueError("partial_request_assembler:" + reason)


def load_module(path, expected, name):
    path = Path(path)
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, "pinned_source:" + name)
    module = types.ModuleType(name)
    module.__file__ = str(path.resolve())
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


full = load_module(HERE / FULL_NAME, FULL_SHA, "partial_frozen_full_assembler")


def validate_seeds(seeds):
    require(seeds.get("schema") == SCHEMA + ".seeds"
            and seeds.get("actual_partial_publication") is True, "explicit_partial_seeds")
    require(type(seeds.get("expected_long_attempts")) is int
            and 82 <= seeds["expected_long_attempts"] <= 122, "actual_82_plus_n_attempts")
    for key in ("attempt_ledger", "cutoff", "round0_manifest", "round1_manifest",
                "round0_collection", "round1_collection", "stage_freeze",
                "execution_receipt", "formal_roster", "formal_unlock",
                "implementation_review", "partial_publication_helper"):
        full.exact_ref(seeds[key])
    require(Path(seeds["partial_publication_helper"]["path"]).resolve()
            == HERE / "compact_partial_publication_001.py"
            and seeds["partial_publication_helper"]["sha256"] == PARTIAL_SHA,
            "exact_partial_helper_path_and_pin")
    require(set(seeds["support_groups"]) == full.SUPPORT_GROUPS
            and all(seeds["support_groups"].values()), "all_explicit_support_groups")
    require(seeds.get("comparisons", []) == [], "partial_no_comparisons")
    require(not any(seeds.get(k) for k in ("grid_audit", "effects")), "no_partial_grid_effects")
    require(isinstance(seeds.get("formal_receipt_snapshots"), list), "explicit_formal_receipt_snapshots")
    for item in seeds["formal_receipt_snapshots"]:
        require(isinstance(item.get("scope"), str) and item["scope"].strip(), "snapshot_scope")
        if item.get("receipt") is not None:
            full.exact_ref(item["receipt"])
    require(bool(seeds.get("superseded_manifests")), "superseded_history_retained")
    for item in seeds["superseded_manifests"]:
        full.exact_ref(item["reference"]); full.exact_ref(item["replacement"])
        require(item.get("status") and item.get("scope"), "superseded_scope")
    for item in seeds.get("excluded_references", []):
        full.exact_ref(item); require(item.get("scope"), "excluded_scope")
    if seeds.get("pipeline_summary") is None:
        require(bool(seeds.get("pipeline_unavailable")), "pipeline_reference_or_explicit_unavailable")
    else:
        full.exact_ref(seeds["pipeline_summary"])
    if seeds.get("pipeline_session") is not None:
        full.exact_ref(seeds["pipeline_session"])
    require(seeds.get("T06_aggregate") is None or seeds.get("pipeline_summary") is not None,
            "aggregate_needs_registered_pipeline")
    require(seeds.get("T06_aggregate") is not None or bool(seeds.get("T06_aggregate_unavailable")),
            "explicit_fixed_eight_parent_aggregate_or_unavailable")
    for ref in seeds.get("include_derived_census", []):
        full.exact_ref(ref)


def metadata_roster(seeds, *, read, raw, nonformal_receipt, partial, helpers):
    """Metadata-only admission. The callbacks are injectable for memory tests."""
    cutoff = read(seeds["cutoff"])
    require(cutoff.get("schema") == partial.SCHEMA + ".cutoff"
            and cutoff.get("status") == "publication_snapshot_frozen"
            and cutoff.get("no_further_native_launches") is True
            and isinstance(cutoff.get("reason"), str) and cutoff["reason"].strip()
            and cutoff["attempt_ledger"] == seeds["attempt_ledger"]
            and cutoff["formal_roster"] == seeds["formal_roster"], "bound_cutoff_declaration")
    data = raw(seeds["attempt_ledger"])
    require(data.endswith(b"\n"), "ledger_complete_tail")
    ledger = [helpers.base.decode(line) for line in data.splitlines() if line.strip()]
    require(all(r.get("kind") in ("long_branch", "short_gate") for r in ledger)
            and sum(r["kind"] == "short_gate" for r in ledger) == 24, "ledger_kinds_and_short24")
    longs = [r for r in ledger if r["kind"] == "long_branch"]
    require(len(longs) == seeds["expected_long_attempts"]
            and len({r["name"] for r in longs}) == len(longs), "actual_unique_long_count")
    roles = {}
    for round_, count in ((0, 48), (1, 24)):
        manifest = read(seeds[f"round{round_}_manifest"])
        require(manifest["schema"] == full.STAGE + ".pair_batch"
                and manifest["rollout_round"] == round_
                and manifest["registered_arms"] == count and len(manifest["slots"]) * 2 == count,
                "fixed_pair_roster")
        for slot in manifest["slots"]:
            require(set(slot["plans"]) == {"a_ref", "a_patch"}, "two_pair_branches")
            for ref in slot["plans"].values():
                k = full.key(ref)
                require(k not in roles, "unique_pair_plan")
                roles[k] = (f"round{round_}_pair", full.exact_ref(ref))
    roster = read(seeds["formal_roster"])
    require(roster["schema"] == full.STAGE + ".formal_batch"
            and roster["formal_unlock"] == seeds["formal_unlock"]
            and len(roster["plans"]) == 40
            and {(r["parent_seed"], r["method"]) for r in roster["plans"]}
            == {(p, m) for p in helpers.formal.PARENTS for m in helpers.formal.METHODS},
            "fixed40_real_method_roster")
    cells = []
    for entry in roster["plans"]:
        ref = full.exact_ref(entry["plan"]); k = full.key(ref)
        require(k not in roles, "disjoint_unique_formal_plan")
        roles[k] = ("formal", ref)
        cells.append({"name": Path(ref["path"]).parent.name, "parent_seed": entry["parent_seed"],
                      "method": entry["method"], "plan": ref, "started": False, "receipt": None,
                      "final_result": None, "evaluation": None, "cache": None, "primary_J": None})
    require(len({r["name"] for r in cells}) == 40, "unique_formal_names")
    by_name = {r["name"]: r for r in cells}
    snapshots = {r["name"]: r for r in seeds["formal_receipt_snapshots"]}
    require(len(snapshots) == len(seeds["formal_receipt_snapshots"]), "unique_snapshot_names")
    runs, receipts, classifications = [], {}, {}
    ledger_root = Path(seeds["attempt_ledger"]["path"]).parent
    used_roles, started_formal = set(), set()
    for entry in longs:
        name = entry["name"]
        require(isinstance(name, str) and Path(name).name == name and name not in (".", ".."),
                "safe_actual_name")
        plan = full.exact_ref({"path": str(ledger_root / "runs" / name / "plan.json"),
                               "sha256": entry["plan_sha256"]})
        k = full.key(plan)
        role, registered = roles.get(k, ("diagnostic", plan))
        require(plan == registered, "ledger_exact_plan_pin")
        used_roles.add(k)
        if role == "formal":
            require(name in snapshots and by_name[name]["plan"] == plan, "started_formal_snapshot_required")
            receipt_ref = snapshots[name].get("receipt")
            started_formal.add(name)
        else:
            require(name not in by_name, "formal_name_cannot_alias_diagnostic")
            receipt_ref = nonformal_receipt(plan)
        receipt = read(receipt_ref) if receipt_ref is not None else None
        checked = partial.classify_receipt(receipt, plan, helpers.formal)
        if role != "formal":
            retained_unknown = (role == "diagnostic" and name == HISTORICAL_UNKNOWN
                and receipt is not None and receipt.get("status") == "unknown_hard_stop")
            require(checked["terminal_verified"] or retained_unknown,
                    "all82_nonformal_terminal_except_exact_historical_unknown")
            if role == "diagnostic" and not checked["owned_complete"]:
                role = "failed_attempt"
        row = {"name": name, "plan": plan, "receipt": receipt_ref, "role": role}
        if role == "formal":
            row.update(final_result=None, evaluation=None, cache=None)
            by_name[name].update(started=True, receipt=receipt_ref)
        runs.append(row); receipts[name] = receipt; classifications[name] = checked
    require(started_formal == set(snapshots), "snapshots_only_actual_started_formal")
    require(all(k in used_roles for k, (role, _) in roles.items() if role != "formal"),
            "all72_registered_pair_arms")
    counts = Counter(r["role"] for r in runs)
    require(counts["round0_pair"] == 48 and counts["round1_pair"] == 24
            and counts["diagnostic"] + counts["failed_attempt"] == 10,
            "complete82_nonformal_denominator")
    request = {"schema": partial.SCHEMA + ".request", "actual_partial_publication": True,
               "attempt_ledger": seeds["attempt_ledger"], "cutoff": seeds["cutoff"],
               "expected_long_attempts": len(runs), "runs": runs,
               "formal": {"roster": seeds["formal_roster"], "unlock": seeds["formal_unlock"],
                   "gate_implementation": {"path": str(HERE / "formal_analysis_gate_001.py"),
                                           "sha256": helpers.formal.GATE_SHA}, "runs": cells},
               "claims": deepcopy(partial.DENIALS), "comparisons": []}
    partial.request_shape(request, helpers)
    return request, receipts, classifications, roster


class PartialGraph(full.Graph):
    """Reuse finite schema routes, with a separate partial metadata I/O gate.

    The inherited all_terminal flag stays false: no claim that unknown formal
    attempts are closed. read/add/bound_file enforce this admission and deny
    every non-complete formal run file except its plan, explicit receipt and
    exact static calendar binding.
    """
    def __init__(self, builder, selector, base):
        super().__init__(builder, selector, base)
        self.metadata_admitted = False
        self.protected_directories = {}
        self.allowed_static = set()

    def admit(self, request, classifications):
        require(not self.metadata_admitted, "single_metadata_admission")
        for cell in request["formal"]["runs"]:
            if not cell["started"] or not classifications[cell["name"]]["owned_complete"]:
                directory = Path(cell["plan"]["path"]).parent.resolve()
                self.protected_directories[directory] = cell["name"]
                self.allowed_static.add(full.key(cell["plan"]))
                if cell["receipt"] is not None:
                    self.allowed_static.add(full.key(cell["receipt"]))
        for row in request["runs"]:
            if row["role"] == "failed_attempt":
                require(row["name"] == HISTORICAL_UNKNOWN and row["role"] == "failed_attempt",
                        "only_named_historical_unknown")
                self.protected_directories[Path(row["plan"]["path"]).parent.resolve()] = row["name"]
                self.allowed_static.add(full.key(row["plan"]))
                self.allowed_static.add(full.key(row["receipt"]))
        self.metadata_admitted = True

    def guard(self, path):
        require(self.metadata_admitted, "metadata_classification_before_dependencies")
        path = Path(path).resolve()
        for directory in self.protected_directories:
            if path.is_relative_to(directory):
                require(str(path).casefold() in self.allowed_static,
                        "no_unstarted_or_noncomplete_formal_run_file:" + str(path))

    def bound_file(self, path, *, maximum=full.MAX_SMALL):
        self.guard(path)
        return super().bound_file(path, maximum=maximum)

    def read(self, ref, *, maximum=full.MAX_SMALL, early=False):
        require(not early, "partial_early_reads_use_metadata_reader")
        ref = full.exact_ref(ref); path = self.path(ref["path"]); self.guard(path)
        require(path.is_file() and path.stat().st_size <= maximum, "bounded_dependency")
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == ref["sha256"], "dependency_sha")
        if path.suffix.lower() == ".gz":
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
                data = stream.read(full.MAX_DECODED + 1)
            require(len(data) <= full.MAX_DECODED, "decoded_dependency_bound")
        return self.base.decode(data)

    def add(self, ref, category="receipt", *, structured=None):
        ref = full.exact_ref(ref); path = self.path(ref["path"]); self.guard(path)
        require(path.name.lower() not in full.HISTORY, "history_cannot_be_included")
        require(category in self.selector.CATEGORIES, "known_category")
        if path.name.lower() == "final_result.json":
            require(category in ("input", "dataset", "receipt") and structured is None, "small_plain_result")
        maximum = full.MAX_SMALL if structured is None else structured["max_bytes"]
        require(type(maximum) is int and 0 < maximum <= 64 * 1024**2, "bounded_artifact")
        k = full.key(ref)
        require(k not in self.excluded, "included_excluded_overlap")
        if k in self.items:
            require(self.items[k]["reference"] == ref, "conflicting_path_pin")
            previous = self.items[k].get("structured_audit")
            require(previous == structured or (structured is None and path.stat().st_size <= full.MAX_SMALL),
                    "conflicting_size_declaration")
            return ref
        require(path.is_file() and path.stat().st_size <= maximum and full.sha(path) == ref["sha256"],
                "missing_changed_or_oversize_artifact")
        if structured is not None:
            self.selector.validate_structured_audit(path, structured, included=True, category=category,
                                                    role="explicit_artifact", expected_sha=ref["sha256"])
        self.items[k] = {"reference": ref, "category": category}
        if structured is not None:
            self.items[k]["structured_audit"] = structured
        return ref

    def expand(self, route, value, ref):
        if (route == "plan" and Path(ref["path"]).parent.resolve() in self.protected_directories
                and value.get("forecast_binding") is not None):
            binding = full.exact_ref(value["forecast_binding"])
            require(Path(binding["path"]).name == "calendar_binding.json"
                    and Path(binding["path"]).parent == Path(ref["path"]).parent,
                    "only_exact_prepared_calendar_sibling")
            self.allowed_static.add(full.key(binding))
        return super().expand(route, value, ref)


def expand_partial_pipeline(graph, seeds, request, classifications):
    """Retain56 metadata cells; expand outputs only for owned-complete native runs."""
    if seeds.get("pipeline_summary") is None:
        return None
    ref = seeds["pipeline_summary"]; graph.add(ref, "report"); value = graph.read(ref)
    require(value["schema"] == full.PIPE + ".summary"
            and value["manifest"] == seeds["formal_roster"]
            and value["registered_jobs"] == 56 and len(value["jobs"]) == 56
            and len({r["job"]["id"] for r in value["jobs"]}) == 56
            and Counter(r["job"]["kind"] for r in value["jobs"])
            == {"cache": 40, "mechanism": 8, "census": 8}, "fixed56_pipeline_metadata")
    graph.visit(value["contract"], "registration", "pipeline_contract")
    cells = {r["name"]: r for r in request["formal"]["runs"]}
    actual = {r["name"]: r for r in request["runs"]}
    seen = set(); expected_index = {}
    for row in value["jobs"]:
        job = row["job"]; cell = cells.get(job["name"])
        require(cell is not None and job["plan"] == cell["plan"]
                and job["parent_seed"] == cell["parent_seed"] and job["method"] == cell["method"]
                and (job["kind"] != "mechanism" or job["method"] == full.R0_METHOD)
                and (job["kind"] != "census" or job["method"] == "C00"), "pipeline_exact_cell")
        require((job["kind"], job["name"]) not in seen, "unique_kind_cell")
        seen.add((job["kind"], job["name"]))
        if row["receipt"] is None:
            require(row["status"] == "not_started_pending_or_budget_insufficient", "known_pending_status")
            graph.missing.append({"job": job, "status": row["status"], "scope": "No offline coverage claimed."})
            continue
        graph.add(row["receipt"]); receipt = graph.read(row["receipt"])
        require(receipt["schema"] == full.PIPE + ".job_receipt"
                and receipt["job"] == job and receipt["status"] == row["status"], "offline_receipt_binding")
        graph.add(receipt["request"], "registration"); original = graph.read(receipt["request"])
        require(original["job"] == job and original["manifest"] == seeds["formal_roster"]
                and original["contract"] == value["contract"], "offline_request_binding")
        if original.get("command"):
            graph.add(original["command"]["helper"], "validator")
        output = receipt.get("output")
        if output is None:
            require(receipt["status"] in ("failed_offline_process", "offline_timeout_no_acceptance",
                                          "unavailable_unverified_closure", "unavailable_failed_parent"),
                    "known_offline_failure")
            graph.missing.append({"job": job, "status": row["status"], "scope": "No offline output."})
            continue
        require(receipt["status"] == "completed_audit_output_recorded", "output_needs_completed_receipt")
        if job["kind"] == "cache":
            expected_index[job["name"]] = output
        if not cell["started"] or not classifications[cell["name"]]["owned_complete"]:
            graph.exclude(output, "Saved offline output declaration only; native closure not owned-complete; not opened.")
            graph.missing.append({"job": job, "status": "output_not_opened_without_owned_complete_native"})
            continue
        graph.visit(output, "report", {"cache": "cache", "mechanism": "mechanism", "census": "T06"}[job["kind"]])
        require(graph.read(output).get("status") == receipt["output_status"], "output_status_binding")
        graph.pipeline_outputs[job["kind"]][job["name"]] = output
        if job["kind"] == "cache":
            cell["cache"] = actual[cell["name"]]["cache"] = output
    require(value["cache_index"] == expected_index
            and value["all_forty_cache_outputs_available"] == (len(expected_index) == 40), "honest_cache_index")
    if seeds.get("pipeline_session"):
        graph.add(seeds["pipeline_session"], "registration"); session = graph.read(seeds["pipeline_session"])
        require(session["schema"] == full.PIPE + ".session" and session["contract"] == value["contract"]
                and session["manifest"] == value["manifest"]
                and session["jobs"] == [r["job"] for r in value["jobs"]], "same_session56")
    return value


def formal_small_files(graph, row):
    """A complete receipt does not prove export completeness; retain missing."""
    directory = Path(row["plan"]["path"]).parent
    graph.add(row["plan"], "registration")
    graph.add(row["receipt"])
    for filename, category in full.RUN_FILES.items():
        path = directory / filename
        if not path.is_file():
            graph.missing.append({"run": row["name"], "path": str(path),
                "status": "missing_formal_export_cost_or_coverage_may_be_unknown"})
            continue
        reference = graph.add(graph.bound_file(path), category)
        for field, expected in (("evaluation", "evaluation.json"), ("final_result", "final_result.json.gz"),
                                ("branch_evidence", "branch_evidence.json.gz")):
            if filename == expected:
                row[field] = reference
        if filename == "callback_audit_receipt.json":
            callback = graph.read(reference)
            if isinstance(callback.get("sha256"), str):
                graph.exclude({"path": str(directory / "callback_audit.jsonl.gz"),
                               "sha256": callback["sha256"]},
                              "Closed producer callback digest; original stream not opened.")


def nonformal_small_files(graph, request, receipts, classifications):
    """Historical failure evidence remains metadata-only even with proven exit."""
    eligible = [row for row in request["runs"] if row["role"] != "formal"
                and classifications[row["name"]]["owned_complete"]]
    full.run_small_files(graph, eligible, receipts)


def expand_aggregate(graph, seeds):
    if seeds.get("T06_aggregate") is None:
        require(bool(seeds.get("T06_aggregate_unavailable")), "aggregate_unavailability_required")
        return
    actual = graph.pipeline_outputs["census"]
    require(len(actual) == 8, "all_eight_actual_census_refs_before_aggregate")
    value = graph.read(seeds["T06_aggregate"])
    require(value.get("status") == "all_eight_fixed_parents_censused"
            and len(value.get("parents", [])) == 8
            and [r["parent_seed"] for r in value["parents"]] == list(range(1301, 1309))
            and len(value.get("cache_summaries", [])) == 8
            and {tuple(sorted(full.exact_ref(r).items())) for r in value["cache_summaries"]}
            == {tuple(sorted(full.exact_ref(r).items())) for r in actual.values()},
            "fixed_eight_census_aggregate_exact_actual_refs")
    graph.visit(seeds["T06_aggregate"], "report", "T06")


def assemble(seeds_ref, *, output):
    builder, selector, base, formal = full.load_helpers()
    def raw(ref):
        ref = full.exact_ref(ref); path = builder.approved_path(ref["path"], selector)
        require(path.is_file() and path.stat().st_size <= full.MAX_SMALL, "small_metadata")
        data = path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == ref["sha256"], "metadata_sha")
        return data
    def read(ref):
        return base.decode(raw(ref))
    seeds = read(seeds_ref); validate_seeds(seeds)
    partial_ref = full.exact_ref(seeds["partial_publication_helper"])
    partial = load_module(partial_ref["path"], partial_ref["sha256"], "partial_publication_bound_helper")
    helpers = partial.helpers()
    output = Path(output).resolve()
    require(output.is_relative_to(HERE) and not output.exists(), "fresh_request_directory")
    def receipt_ref(plan):
        path = Path(plan["path"]).parent / "receipt.json"
        require(path.is_file() and path.stat().st_size <= full.MAX_SMALL, "nonformal_receipt_exists")
        return {"path": str(path), "sha256": full.sha(path)}
    request, receipts, classes, roster = metadata_roster(
        seeds, read=read, raw=raw, nonformal_receipt=receipt_ref, partial=partial, helpers=helpers)
    # Reuse the portable module's metadata gate before any dependency expansion.
    early_view = types.SimpleNamespace(read=read, raw_reference=raw)
    partial.metadata_gate(early_view, request, helpers)
    graph = PartialGraph(builder, selector, base)
    graph.formal_methods = tuple(formal.METHODS)
    graph.admit(request, classes)
    graph.run_lookup = {r["name"]: r for r in request["runs"]}
    graph.run_lookup.update({r["name"]: r for r in request["formal"]["runs"] if not r["started"]})
    graph.expected_collections = {n: full.exact_ref(seeds[f"round{n}_collection"]) for n in (0, 1)}
    graph.derived_include = {full.key(ref): full.exact_ref(ref) for ref in seeds.get("include_derived_census", [])}
    require(len(graph.derived_include) == len(seeds.get("include_derived_census", [])), "unique_derived_refs")
    graph.add(seeds_ref, "registration"); graph.add(seeds["cutoff"], "registration")
    graph.add(seeds["attempt_ledger"], "ledger")
    admin = full.expand_support(graph, seeds)
    for item in seeds["superseded_manifests"]:
        graph.add(item["reference"], "registration"); graph.add(item["replacement"], "registration")
    for item in seeds.get("excluded_references", []):
        graph.exclude(item, item["scope"])
    nonformal_small_files(graph, request, receipts, classes)
    for row in request["runs"]:
        if row["role"] == "formal" and classes[row["name"]]["owned_complete"]:
            formal_small_files(graph, row)
    for row in request["runs"]:
        graph.add(row["plan"], "registration")
        if row.get("receipt") is not None:
            graph.add(row["receipt"])
    for cell in request["formal"]["runs"]:
        if cell["started"] and classes[cell["name"]]["owned_complete"]:
            row = next(r for r in request["runs"] if r["name"] == cell["name"])
            cell.update(final_result=row.get("final_result"), evaluation=row.get("evaluation"))
    for row in graph.run_lookup.values():
        graph.visit(row["plan"], "registration", "plan")
    graph.visit(seeds["stage_freeze"], "model", "stage")
    graph.visit(seeds["execution_receipt"], "receipt", "fit")
    for n in (0, 1):
        graph.visit(seeds[f"round{n}_collection"], "dataset", "collection")
        graph.visit(seeds[f"round{n}_manifest"], "registration", "pair_manifest")
    graph.visit(seeds["formal_roster"], "registration", "formal_roster")
    graph.visit(seeds["formal_unlock"], "registration", "unlock")
    pipeline = expand_partial_pipeline(graph, seeds, request, classes)
    expand_aggregate(graph, seeds)
    require(set(graph.derived_include) == graph.derived_consumed, "only_bound_derived_census")
    stage = graph.read(seeds["stage_freeze"]); frozen = graph.read(stage["spi_freeze"])
    request["training"] = {"stage_freeze": seeds["stage_freeze"], "spi_freeze": stage["spi_freeze"],
        "round0_collection": seeds["round0_collection"], "round1_collection": seeds["round1_collection"],
        "execution_receipt": seeds["execution_receipt"],
        "fit_events": [graph.bound_file(Path(m["chain_receipt"]["path"]).parent / "fit_events.jsonl")
                       for m in frozen["models"]]}
    request.update(administrative_artifacts=admin + [seeds["cutoff"], seeds["execution_receipt"]],
                   superseded_manifests=seeds["superseded_manifests"],
                   excluded_large_logs=list(graph.excluded.values()),
                   gate_basis={"implementation_review": seeds["implementation_review"]})
    if seeds.get("pipeline_summary"):
        request["administrative_artifacts"].append(seeds["pipeline_summary"])
    graph.add(seeds["implementation_review"], "review")
    require(seeds["implementation_review"]["sha256"] == builder.REVIEW_SHA, "fixed_implementation_review")
    for ref in [partial_ref, {"path": str(HERE / FULL_NAME), "sha256": FULL_SHA},
                graph.bound_file(__file__), request["formal"]["gate_implementation"]]:
        graph.add(ref, "validator")
    for filename, expected in partial.PINS.values():
        graph.add({"path": str(HERE / filename), "sha256": expected}, "validator")
    spec = {"schema": selector.SCHEMA + ".request", "template_not_final": False,
            "registered_run_slots": [{"slot_id": r["name"], "role": r["role"], "plan": r["plan"]}
                                     for r in request["runs"]],
            "compact_artifacts": list(graph.items.values()), "source_manifests": list(graph.sources.values()),
            "formal_unlock": seeds["formal_unlock"]}
    partial.request_shape(request, helpers)
    view = partial.local_view(spec, request, helpers)
    checks = partial.audit_view(view, request, helpers, numerical=False)
    require(full.sha(seeds["attempt_ledger"]["path"]) == seeds["attempt_ledger"]["sha256"],
            "ledger_changed_during_assembly")
    for row in request["runs"]:
        if row.get("receipt") is not None:
            require(full.sha(row["receipt"]["path"]) == row["receipt"]["sha256"], "receipt_snapshot_changed")
    report = {"schema": SCHEMA + ".assembly_report", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "partial_requests_prepared_not_preflighted_or_built", "seeds": seeds_ref,
        "actual_attempts": len(request["runs"]), "registered_formal_slots": 40,
        "formal_started_means": "charged ledger registration; not independently observed PID launch",
        "closure_classifications": classes, "claims": deepcopy(partial.DENIALS),
        "source_count": len(graph.sources), "included_original_paths": len(graph.items),
        "excluded_bound_refs": list(graph.excluded.values()), "missing_or_unexpanded": graph.missing,
        "local_history_index": graph.local_unhashed, "historical_mutable_refs": graph.historical_mutable_refs,
        "external_environment_provenance": graph.external,
        "pipeline_scope": seeds.get("pipeline_unavailable") if pipeline is None else
            {"registered_jobs": 56, "statuses": Counter(r["status"] for r in pipeline["jobs"])},
        "offline_fixed_parents": list(range(1301, 1309)),
        "offline_job_coverage": [] if pipeline is None else [
            {"job": r["job"], "status": r["status"],
             "output_included": r["job"]["name"] in graph.pipeline_outputs[r["job"]["kind"]]}
            for r in pipeline["jobs"]],
        "T06_aggregate_unavailable": seeds.get("T06_aggregate_unavailable"),
        "identity_check": checks, "numerical_audit_performed": False,
        "native_operations": 0, "fit_operations": 0, "package_builds": 0, "preflight_runs": 0}
    output.mkdir()
    report_ref = full.write_new(output / "assembly_report.json", report, builder)
    spec["compact_artifacts"].append({"reference": report_ref, "category": "report"})
    spec_ref = full.write_new(output / "allowlist_request.json", spec, builder)
    request["allowlist_request"] = spec_ref
    request["administrative_artifacts"].append(report_ref)
    partial.request_shape(request, helpers)
    request_ref = full.write_new(output / "builder_request.json", request, builder)
    return {"schema": SCHEMA + ".result", "request": request_ref, "allowlist": spec_ref,
            "report": report_ref, "claims": deepcopy(partial.DENIALS),
            "actual_preflight_or_build_performed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--seeds-sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = assemble({"path": str(Path(args.seeds).resolve()), "sha256": args.seeds_sha256},
                      output=args.output)
    print(full.json.dumps(result, ensure_ascii=False))
