"""Prepare explicit final requests from bound seeds; never build a package.

Root must invoke this only after the registered campaign has ended. The first
phase reads the bound ledger and fixed terminal receipts only. No plan, dataset,
model or outcome is expanded until every actual long attempt is terminal.
Dependencies follow named schema fields and fixed filenames, never a directory
scan or arbitrary recursive path search. Unknown administrative report shapes
are leaves whose additional dependencies must be explicitly supplied.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
SCHEMA = "g31.inventory_spi.final_compact_request_assembler.v2"
R0_METHOD = "R0_current_stock_v1"
BUILDER_SHA = "60a64acb9630d0a54818e4b65fa13d1ca33a23e631b77cb834feafa121e36c9a"
STAGE = "g31.inventory_spi_offline_stages.v1"
RUN = "g31.inventory_spi_native_campaign.v1"
TRAIN = "g31.foundation.airport_spi_training_campaign.v1"
PIPE = "g31.inventory_spi.formal_offline_pipeline.v1"
FIT = "g31.inventory_spi.registered_fit_execution.v1"
MAX_SMALL = 16 * 1024**2
MAX_DECODED = 128 * 1024**2
HISTORY = {
    "control_records.json", "control_records.json.gz",
    "controller_final_state.json", "controller_final_state.json.gz",
    "ack_views.json", "ack_views.json.gz", "callback_audit.json",
    "callback_audit.jsonl", "callback_audit.jsonl.gz",
    "warmup_prefix.json", "warmup_prefix.json.gz", "activation_prefix.json",
    "activation_prefix.json.gz", "inventory_snapshot_reads.json",
    "inventory_snapshot_reads.json.gz", "client_calls.json", "client_calls.json.gz",
}
RUN_FILES = {
    "worker_report.json": "receipt", "evaluation.json": "receipt",
    "final_result.json.gz": "dataset", "branch_evidence.json.gz": "dataset",
    "pair_trace.json.gz": "dataset", "callback_audit_receipt.json": "receipt",
    "planner_summary.json": "receipt", "actual_plan_preload_receipts.json": "receipt",
    "source_verification.json": "receipt",
}
PLAN_ROUTES = {
    "input": ("input", "leaf"), "binary": ("receipt", "leaf"),
    "native_acceptance": ("receipt", "native"), "source_bundle": ("registration", "source"),
    "forecast_binding": ("input", "calendar"), "model": ("model", "leaf"),
    "behavior_model": ("model", "leaf"), "rule": ("model", "rule"),
    "formal_unlock": ("registration", "unlock"), "event_calibration": ("receipt", "leaf"),
}
SUPPORT_GROUPS = {
    "round0_gates", "round1_gates", "training_numeric",
    "diagnostics_and_mechanisms", "timing", "administrative_and_failures",
    "final_report_and_contract",
}


def require(ok, reason):
    if not ok:
        raise ValueError("final_request_assembler:" + reason)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def exact_ref(ref):
    require(isinstance(ref, dict) and isinstance(ref.get("path"), str)
            and Path(ref["path"]).is_absolute(), "absolute_bound_reference")
    require(isinstance(ref.get("sha256"), str) and len(ref["sha256"]) == 64
            and all(c in "0123456789abcdef" for c in ref["sha256"]), "sha256_reference")
    return {"path": str(Path(ref["path"]).resolve()), "sha256": ref["sha256"]}


def key(ref):
    return exact_ref(ref)["path"].casefold()


def load_helpers():
    path = HERE / "build_final_compact_publication_002.py"
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == BUILDER_SHA, "fixed_builder_source")
    builder = types.ModuleType("final_builder_for_assembly")
    builder.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), builder.__dict__)
    selector, base, formal = builder.helpers()
    return builder, selector, base, formal


def validate_seeds(value):
    """Pure shape validation; does not read any referenced file."""
    require(value.get("schema") == SCHEMA + ".seeds"
            and value.get("actual_final_publication") is True, "actual_bound_seeds_required")
    require(type(value.get("expected_long_attempts")) is int
            and value["expected_long_attempts"] == 122, "registered_122_actual_long_attempts")
    for name in ("attempt_ledger", "round0_manifest", "round1_manifest",
                 "stage_freeze", "execution_receipt", "round0_collection",
                 "round1_collection", "formal_roster", "formal_unlock",
                 "pipeline_summary", "grid_audit", "effects", "implementation_review"):
        exact_ref(value[name])
    require(set(value["support_groups"]) == SUPPORT_GROUPS
            and all(value["support_groups"].values()), "all_explicit_support_groups")
    require(isinstance(value["superseded_manifests"], list)
            and value["superseded_manifests"], "superseded_attempt_scopes")
    for row in value["superseded_manifests"]:
        exact_ref(row["reference"])
        exact_ref(row["replacement"])
        require(row.get("status") and row.get("scope"), "supersession_scope")
    for row in value.get("excluded_references", []):
        exact_ref(row)
        require(row.get("scope"), "excluded_evidence_scope")
    require(value.get("T06_aggregate") is not None or bool(value.get("T06_aggregate_unavailable")),
            "explicit_T06_aggregate_or_unavailability")
    for ref in value.get("include_derived_census", []):
        exact_ref(ref)


class Graph:
    """Bounded metadata graph. Raw histories are recorded, never opened."""

    def __init__(self, builder, selector, base):
        self.builder, self.selector, self.base = builder, selector, base
        self.items, self.sources, self.excluded = {}, {}, {}
        self.visited, self.missing, self.local_unhashed, self.external = set(), [], [], []
        self.historical_mutable_refs = []
        self.all_terminal = False
        self.run_lookup = {}
        self.derived_include = {}
        self.derived_consumed = set()
        self.expected_collections = {}
        self.pipeline_outputs = {"cache": {}, "mechanism": {}, "census": {}}

    def path(self, value):
        return self.builder.approved_path(value, self.selector)

    def bound_file(self, path, *, maximum=MAX_SMALL):
        path = self.path(path)
        require(path.is_file() and path.stat().st_size <= maximum, "required_bounded_file:" + str(path))
        return {"path": str(path), "sha256": sha(path)}

    def read(self, ref, *, maximum=MAX_SMALL, early=False):
        require(self.all_terminal or early, "all_receipts_before_dependency_reads")
        ref = exact_ref(ref)
        path = self.path(ref["path"])
        require(path.is_file() and path.stat().st_size <= maximum, "bounded_metadata:" + str(path))
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == ref["sha256"], "changed_bound_metadata:" + str(path))
        if path.suffix.lower() == ".gz":
            with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
                raw = stream.read(MAX_DECODED + 1)
            require(len(raw) <= MAX_DECODED, "decoded_metadata_limit")
        return self.base.decode(raw)

    def add(self, ref, category="receipt", *, structured=None):
        require(self.all_terminal, "all_receipts_before_file_expansion")
        ref = exact_ref(ref)
        path = self.path(ref["path"])
        require(path.name.lower() not in HISTORY, "history_cannot_be_included")
        require(category in self.selector.CATEGORIES, "known_compact_category")
        if path.name.lower() == "final_result.json":
            require(category in ("input", "dataset", "receipt") and structured is None,
                    "ordinary_small_plain_result")
        maximum = MAX_SMALL if structured is None else structured["max_bytes"]
        require(type(maximum) is int and 0 < maximum <= 64 * 1024**2, "finite_compact_size")
        k = key(ref)
        require(k not in self.excluded, "included_excluded_overlap")
        if k in self.items:
            require(self.items[k]["reference"] == ref, "conflicting_path_sha")
            prior = self.items[k].get("structured_audit")
            require(prior == structured or (structured is None and path.stat().st_size <= MAX_SMALL),
                    "conflicting_structured_declaration")
        else:
            require(path.is_file() and path.stat().st_size <= maximum, "missing_or_oversize_dependency:" + str(path))
            require(sha(path) == ref["sha256"], "changed_dependency:" + str(path))
            if structured is not None:
                self.selector.validate_structured_audit(path, structured, included=True,
                    category=category, role="explicit_artifact", expected_sha=ref["sha256"])
            self.items[k] = {"reference": ref, "category": category}
            if structured is not None:
                self.items[k]["structured_audit"] = structured
        return ref

    def exclude(self, ref, scope):
        ref = exact_ref(ref)
        self.path(ref["path"])
        k = key(ref)
        require(k not in self.items and bool(scope), "excluded_scope_no_included_overlap")
        if k in self.excluded:
            require(self.excluded[k]["sha256"] == ref["sha256"], "conflicting_excluded_sha")
        else:
            self.excluded[k] = {**ref, "included": False, "scope": scope,
                "content_read_or_hash_recomputed_by_assembler": False}

    def implementation(self, value):
        refs = value.get("implementation", [])
        if isinstance(refs, dict):
            refs = [refs] if "path" in refs else list(refs.values())
        for ref in refs:
            self.add(ref, "validator")

    def fields(self, value, routes, *, relative=False):
        for name, (category, route) in routes.items():
            if value.get(name) is not None:
                ref = self.native_ref(value[name]) if relative else value[name]
                self.visit(ref, category, route)

    def native_ref(self, ref):
        require(isinstance(ref, dict) and {"path", "sha256"} <= ref.keys(), "native_bound_ref")
        path = Path(ref["path"])
        return exact_ref({**ref, "path": str(path if path.is_absolute() else ROOT / path)})

    def input_rows(self, rows):
        for row in rows:
            self.visit(row["dataset"], "dataset", "dataset")
            for name in ("reference_plan", "patched_plan"):
                self.visit(row[name], "registration", "plan")

    def declared_report(self, ref, route):
        item = self.items.get(key(ref))
        require(item is not None and item["reference"] == exact_ref(ref),
                "report_requires_explicit_seed_and_size_declaration")
        self.visit(ref, item["category"], route, structured=item.get("structured_audit"))

    def evidence_inventory(self, inventory):
        """Known gate inventory keys only; observations/pairs are never walked."""
        for name, ref in inventory.items():
            if name in ("client_calls", "calls", "controls", "warmup"):
                self.exclude(ref, "Original history bound by saved audit; not read or copied by assembler.")
            elif name in ("plan", "source_bundle", "native_acceptance"):
                self.visit(ref, "registration" if name != "native_acceptance" else "receipt",
                           {"plan": "plan", "source_bundle": "source", "native_acceptance": "native"}[name])
            elif name in ("receipt", "input", "final_result", "branch_evidence", "pair_trace", "binary"):
                self.add(ref, "dataset" if name in ("final_result", "branch_evidence", "pair_trace") else
                         "input" if name == "input" else "receipt")
            elif name.startswith("source."):
                self.add(ref, "validator")
            else:
                raise ValueError("final_request_assembler:unknown_gate_inventory:" + name)

    def shared(self, value):
        self.fields(value, {"source_bundle": ("registration", "source"),
            "native_acceptance": ("receipt", "native"), "preregistration": ("registration", "registration"),
            "calibration": ("receipt", "leaf")})
        if isinstance(value.get("binary"), dict):
            self.add(value["binary"], "receipt")
        elif value.get("binary"):
            native = self.read(value["native_acceptance"])
            self.add({"path": value["binary"], "sha256": native["binary"]["sha256"]}, "receipt")

    def visit(self, ref, category="receipt", route="leaf", *, structured=None):
        original_ref = ref
        ref = self.add(ref, category, structured=structured)
        token = (key(ref), route)
        if token in self.visited or route == "leaf":
            return ref
        self.visited.add(token)
        value = self.read(ref, maximum=(structured or {}).get("max_bytes", MAX_SMALL))
        require(isinstance(value, dict), "structured_dependency_object")
        self.expand(route, value, ref)
        return original_ref

    def expand(self, route, v, ref):
        schema = v.get("schema")
        if route == "plan":
            require(schema == RUN and v["name"] in self.run_lookup
                    and self.run_lookup[v["name"]]["plan"]["sha256"] == ref["sha256"],
                    "only_actual_registered_plan")
            self.fields(v, PLAN_ROUTES)
        elif route == "source":
            require(Path(ref["path"]).name == "source_manifest.json" and schema == RUN + ".sources",
                    "frozen_source_manifest_only")
            require(v["source_manifest_sha256"] == self.base.digest(v["files"]), "source_identity")
            self.sources[key(ref)] = exact_ref(ref)
            root = self.path(v["root"])
            for logical, expected in v["files"].items():
                path = self.path(root / logical)
                require(path.is_relative_to(root), "confined_source_member")
                # Explicit artifact category validator; builder also adds source aliases.
                self.add({"path": str(path), "sha256": expected}, "validator")
        elif route == "calendar":
            require(schema == "g31.foundation.airport_calendar_parameter_reuse.v1", "calendar_schema")
            producer = v["producer_manifest"]
            require(producer["schema"] == "g31.foundation.airport_absolute_forecast_binding.v1",
                    "calendar_producer_schema")
            refs = producer["source_references"]
            expected = {"flight_forecaster_checkpoint.json", "public/static_flight_plan.json", "receipt.json"}
            require(set(refs) == expected, "exact_original_B1_dependencies")
            for name, dep in refs.items():
                self.add(dep, "model" if name.endswith("checkpoint.json") else "input")
        elif route == "native":
            require(schema == "g31.native030.inventory_spi_accepted_contract.v1"
                    and v["status"] in ("passed", "passed_with_retained_fixture_failure"), "accepted_native030")
            self.fields(v, {k: ("receipt" if k in ("binary", "build_receipt") else "validator", "leaf")
                           for k in ("binary", "build_receipt", "runner", "build_helper")}, relative=True)
            for dep in v["changed_native_sources"]:
                self.add(self.native_ref(dep), "validator")
            self.add(self.native_ref(v["offline_acceptance_tests"]["source"]), "validator")
            for gate in v["gates"]:
                gate_ref = self.native_ref(gate["receipt"])
                self.add(gate_ref)
                receipt = self.read(gate_ref)
                if isinstance(receipt.get("binary"), str) and receipt.get("binary_sha256"):
                    self.add(self.native_ref({"path": receipt["binary"],
                                             "sha256": receipt["binary_sha256"]}), "receipt")
                for dep in gate["files"]:
                    dep = self.native_ref(dep)
                    if Path(dep["path"]).name.lower() in HISTORY:
                        self.exclude(dep, "Native gate dependency; original bytes not included or replayed by package.")
                    else:
                        self.add(dep, "receipt")
        elif route == "registration":
            require(schema == RUN + ".registration", "campaign_registration_schema")
            routes = {k: ("registration", "leaf") for k in ("contract_document", "parent_registry",
                "learning_contract", "budget", "collector_revision", "amendment", "ownership_amendment",
                "export_amendment", "final_export_calibration", "ownership_pure_and_failed_short",
                "exporter_readiness")}
            routes.update(runtime_shared=("registration", "runtime"),
                          supersedes_registration=("registration", "registration"))
            self.fields(v, routes)
        elif route == "runtime":
            self.shared(v)
        elif route == "pair_manifest":
            require(schema == STAGE + ".pair_batch", "pair_manifest_schema")
            self.shared(v["shared"])
            self.fields(v, {"spi_freeze": ("model", "freeze"), "behavior_model": ("model", "leaf")})
            for slot in v["slots"]:
                for dep in slot["plans"].values():
                    self.visit(dep, "registration", "plan")
            self.implementation(v)
        elif route == "collection":
            require(schema == STAGE + ".collection" and v["status"] == "all_registered_attempts_collected",
                    "closed_collection")
            self.visit(v["batch_manifest"], "registration", "pair_manifest")
            self.shared(v["shared"])
            self.fields(v, {"spi_freeze": ("model", "freeze"), "behavior_model": ("model", "leaf")})
            self.input_rows(v["inputs"])
            self.implementation(v)
        elif route == "dataset":
            provenance = v["collection_provenance"]
            self.visit(provenance["batch_manifest"], "registration", "pair_manifest")
            for dep in provenance["plans"].values():
                self.visit(dep, "registration", "plan")
            for dep in provenance["attempt_receipts"].values():
                self.add(dep)
            for dep in provenance["branch_evidence"].values():
                if dep is not None:
                    self.add(dep, "dataset")
        elif route == "stage":
            require(schema == STAGE + ".training_frozen", "actual_stage_frozen")
            self.fields(v, {"registration": ("registration", "training_registration"),
                           "spi_freeze": ("model", "freeze"), "rule": ("model", "rule")})
            self.implementation(v)
        elif route == "training_registration":
            require(schema == STAGE + ".training", "training_registration")
            self.fields(v, {"collection": ("dataset", "collection"), "campaign": ("registration", "campaign")})
            self.implementation(v)
        elif route == "campaign":
            require(schema == TRAIN, "SPI_campaign_schema")
            self.input_rows(v["train_inputs"] + v["dev_inputs"])
            for dep in v["chain_plans"]:
                self.visit(dep, "registration", "chain_plan")
            for logical, item in v["source_archive"].items():
                require(item["archive"]["sha256"] == item["sha256"], "archive_byte_pin")
                if logical in v["source_sha256"]:
                    require(item["sha256"] == v["source_sha256"][logical], "training_source_pin")
                self.add(item["archive"], "validator")
            require(set(v["source_sha256"]) <= set(v["source_archive"]), "all_training_source_archives")
        elif route == "chain_plan":
            require(schema == TRAIN + ".chain", "SPI_chain_schema")
            self.input_rows(v["train_inputs"] + v["dev_inputs"])
        elif route == "chain_receipt":
            require(schema == TRAIN + ".receipt" and v["status"] == "closed", "closed_SPI_chain")
            self.visit(v["chain_plan"], "registration", "chain_plan")
            for dep in v["model_candidates"]:
                self.add(dep, "model")
            self.add(v["selected_model"], "model")
            self.add(v["selection"], "model")
            self.add(self.bound_file(Path(ref["path"]).parent / "fit_events.jsonl"), "curve")
        elif route == "freeze":
            require(schema == TRAIN + ".freeze", "SPI_freeze_schema")
            self.visit(v["campaign"], "registration", "campaign")
            for model in v["models"]:
                self.add(model["checkpoint"], "model")
                self.add(model["selection"], "model")
                self.visit(model["chain_receipt"], "receipt", "chain_receipt")
        elif route == "rule":
            require(schema == "g31.foundation.airport_spi_C10_development_selection.v1", "C10_rule_schema")
            self.input_rows(v["dev_inputs"])
        elif route == "fit":
            require(schema in {FIT + suffix for suffix in (".receipt", ".request", ".admission", ".child_report")},
                    "fit_administrative_schema")
            self.fields(v, {k: ("receipt", "fit") for k in ("request", "admission", "child_report")})
            self.fields(v, {"frozen_stage": ("model", "stage"), "spi_freeze": ("model", "freeze"),
                "rule": ("model", "rule"), "events": ("curve", "leaf"),
                "executor": ("validator", "leaf"), "process_helper": ("validator", "leaf")})
            routes = {"registration": ("registration", "training_registration"),
                      "manifest": ("registration", "pair_manifest"), "budget": ("registration", "leaf")}
            for name, dep in v.get("bindings", {}).items():
                if name in ("raw_gate", "physical_gate"):
                    require(key(dep) in self.items, "fit_gate_must_be_explicit_support_report")
                else:
                    require(name in routes, "known_fit_binding")
                    self.visit(dep, *routes[name])
            for row in v.get("prepared", {}).get("chains", []):
                self.visit(row["plan"], "registration", "chain_plan")
            self.fields(v.get("prepared", {}), {"collection": ("dataset", "collection"),
                                               "campaign": ("registration", "campaign")})
            if v.get("python"):
                self.external.append({"reference": v["python"], "scope": "External interpreter provenance; not copied."})
        elif route == "pair_gate":
            require(schema in ("g31.inventory_spi.precollection_raw_evidence_gate.v1",
                               "g31.inventory_spi.paired_physical_admission.v1",
                               "g31.inventory_spi.selected_action_small_chain_audit.v1"), "known_pair_gate_schema")
            self.visit(v["manifest"], "registration", "pair_manifest")
            self.implementation(v)
            for field in ("raw_gate", "physical_gate"):
                if v.get(field):
                    self.declared_report(v[field], "pair_gate")
            for field in ("strict_closure_wrapper", "original_raw_gate"):
                if v.get(field):
                    self.add(v[field], "validator")
            for arm in v["arms"]:
                self.visit(arm["plan"], "registration", "plan")
                self.evidence_inventory(arm.get("raw_artifacts", arm.get("raw_evidence", {})))
            for closure in v.get("closure", v.get("strict_outer_closure", [])):
                self.visit(closure["plan"], "registration", "plan")
                self.add(closure["receipt"])
        elif route == "dispatch":
            prefix = "g31.inventory_spi.root_registered_native_dispatch."
            require(isinstance(schema, str) and schema.startswith(prefix)
                    and schema.removeprefix(prefix) in
                    {ver + suffix for ver in ("v1", "v2")
                     for suffix in ("", ".admission", ".wave_admission", ".wave_closed")},
                    "known_dispatch_schema")
            if v.get("manifest"):
                manifest = self.read(v["manifest"])
                route_ = "formal_roster" if manifest["schema"] == STAGE + ".formal_batch" else "pair_manifest"
                self.visit(v["manifest"], "registration", route_)
            self.fields(v, {k: ("receipt", "dispatch") for k in
                            ("admission", "stage_admission", "wave_admission")})
            self.fields(v, {"source_bundle": ("registration", "source")})
            self.implementation(v)
            for wave in v.get("waves", []):
                self.visit(wave["admission"], "receipt", "dispatch")
                self.visit(wave["closed"], "receipt", "dispatch")
            for row in v.get("ordered_runs", []):
                self.visit(row["plan"], "registration", "plan")
            if v.get("resources", {}).get("budget"):
                self.add(v["resources"]["budget"], "registration")
            for field in ("ledger_before", "ledger_after"):
                if field in v:
                    snapshot = v[field]
                    # The append-only ledger path now has its final bytes. An
                    # earlier digest is a time-specific declaration, not a
                    # second file at that same path; never silently rebind it.
                    self.historical_mutable_refs.append({"reference": snapshot["ledger"],
                        "scope": "Historical mutable-ledger digest declaration; original snapshot bytes not archived here."})
                    for closure in snapshot["closures"]:
                        self.add(closure["receipt"])
        elif route == "unlock":
            require(schema == RUN + ".formal_unlock", "formal_unlock_schema")
            self.fields(v, {"spi_freeze": ("model", "freeze"), "rule": ("model", "rule"),
                "source_bundle": ("registration", "source"), "native_acceptance": ("receipt", "native"),
                "preregistration": ("registration", "registration"),
                "round1_collection": ("dataset", "collection")})
            for dep in v["models"].values():
                self.add(dep, "model")
            self.implementation(v)
        elif route == "formal_roster":
            require(schema == STAGE + ".formal_batch", "formal_roster_schema")
            self.visit(v["formal_unlock"], "registration", "unlock")
            self.shared(v["shared"])
            for entry in v["plans"]:
                self.visit(entry["plan"], "registration", "plan")
            self.implementation(v)
        elif route == "pipeline_contract":
            require(schema == PIPE + ".contract", "pipeline_contract_schema")
            self.add(v["budget"], "registration")
            for dep in v["helpers"].values():
                self.add(dep, "validator")
            for name in ("scheduler", "owned_process_helper"):
                self.add(v[name], "validator")
            self.external.append({"reference": v["python"], "scope": "External interpreter; no executable copied."})
        elif route == "cache":
            require(schema == "g31.inventory_spi_formal_analysis_gate.v1", "formal_cache_schema")
            self.visit(v["manifest"], "registration", "formal_roster")
            self.visit(v["plan"], "registration", "plan")
            self.implementation(v)
            for name, dep in v["raw_inventory"]["present"].items():
                if name in ("calls", "controls", "warmup"):
                    self.exclude(dep, "External physical/control audit dependency; bytes not read by assembler.")
                elif name in ("receipt", "plan", "result", "evaluation"):
                    self.add(dep, "dataset" if name == "result" else "receipt")
                elif name.startswith("dependency."):
                    field = name.removeprefix("dependency.")
                    require(field in PLAN_ROUTES, "known_cache_dependency")
                    self.visit(dep, *PLAN_ROUTES[field])
                elif name == "shared.preregistration":
                    self.visit(dep, "registration", "registration")
                elif name.startswith("source."):
                    self.add(dep, "validator")
                else:
                    raise ValueError("final_request_assembler:unknown_cache_inventory:" + name)
        elif route == "T06":
            require(schema == "g31.inventory_spi.offline_T06_census.v1", "T06_schema")
            if v.get("status") == "all_eight_fixed_parents_censused":
                roots = v["selected_roots"]
                require(len(roots) == 2 and {r["round"] for r in roots} == {0, 1}
                        and all(exact_ref(r["collection"]) == self.expected_collections[r["round"]]
                                for r in roots), "T06_selected_roots_exact_two_collections")
                for row in roots:
                    self.visit(row["collection"], "dataset", "collection")
            self.visit(v["formal_manifest"], "registration", "formal_roster")
            self.add(v["adapter_source"], "validator")
            self.add(v["raw_reader"], "validator")
            for dep in v.get("cache_summaries", []):
                self.visit(dep, "report", "T06")
            for parent in v["parents"]:
                for name, r in (("C00_plan", "plan"), ("C10_public_binding_plan", "plan"),
                                ("binding", "calendar"), ("closed_receipt", "leaf"), ("callback_receipt", "leaf")):
                    self.visit(parent[name], "receipt", r)
                self.exclude(parent["callback_artifact"], "Original callback stream; external hash-chain audit only.")
                census = parent["census"]
                if key(census) in self.derived_include:
                    require(exact_ref(census) == self.derived_include[key(census)], "derived_census_exact_inclusion_pin")
                    self.add(census, "dataset")
                    self.derived_consumed.add(key(census))
                else:
                    self.exclude(census, "Derived offline census retained locally; no package per-callback score reexecution.")
        elif route == "mechanism":
            require(schema in ("g31.inventory_spi_offline_mechanism_audit.v1",
                               "g31.inventory_spi.single_closed_raw_byte_mechanism.v1"), "mechanism_schema")
            self.fields(v, {"source_bundle": ("registration", "source"), "receipt": ("receipt", "leaf"),
                            "adapter": ("validator", "leaf")})
            self.fields(v.get("closed_process_gate", {}), {k: ("receipt", "leaf")
                                                         for k in ("receipt", "worker_report", "adapter")})
            name = v.get("run_name") or v.get("run") or v.get("name")
            if v.get("artifact_sha256"):
                require(name in self.run_lookup, "mechanism_registered_run")
                directory = Path(self.run_lookup[name]["plan"]["path"]).parent
                for filename, expected in v["artifact_sha256"].items():
                    require(filename in HISTORY | set(RUN_FILES) | {"plan.json", "receipt.json"},
                            "known_mechanism_artifact")
                    dep = {"path": str(directory / filename), "sha256": expected}
                    if filename in HISTORY:
                        self.exclude(dep, "Original mechanism evidence; only external audit scope retained.")
                    else:
                        self.add(dep, "dataset" if filename == "final_result.json.gz" else "receipt")
        else:
            raise ValueError("final_request_assembler:unknown_route:" + route)


def terminal_roster(graph, seeds, formal):
    """Only ledger + fixed receipts. Every failure remains in the denominator."""
    ledger = exact_ref(seeds["attempt_ledger"])
    path = graph.path(ledger["path"])
    require(path.stat().st_size <= MAX_SMALL, "small_ledger")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ledger["sha256"] and raw.endswith(b"\n"), "final_ledger_bytes")
    records = [graph.base.decode(line) for line in raw.splitlines() if line.strip()]
    require(all(r.get("kind") in ("long_branch", "short_gate") for r in records), "ledger_kinds")
    longs = [r for r in records if r["kind"] == "long_branch"]
    require(len(longs) == seeds["expected_long_attempts"] and len({r["name"] for r in longs}) == len(longs)
            and sum(r["kind"] == "short_gate" for r in records) == 24, "complete_actual_budget_denominators")
    runs, receipts = [], {}
    for row in longs:
        name = row["name"]
        require(isinstance(name, str) and Path(name).name == name and name not in (".", ".."),
                "safe_registered_run_name")
        directory = graph.path(path.parent / "runs" / name)
        plan = exact_ref({"path": str(directory / "plan.json"), "sha256": row["plan_sha256"]})
        receipt_ref = graph.bound_file(directory / "receipt.json")
        receipt = graph.read(receipt_ref, early=True)
        formal.terminal(receipt, plan)
        runs.append({"name": name, "plan": plan, "receipt": receipt_ref})
        receipts[name] = receipt
    graph.all_terminal = True
    graph.run_lookup = {r["name"]: r for r in runs}
    return runs, receipts


def bind_rosters(graph, seeds, runs):
    roles = {}
    for round_, count in ((0, 48), (1, 24)):
        manifest = graph.read(seeds[f"round{round_}_manifest"])
        require(manifest["schema"] == STAGE + ".pair_batch" and manifest["rollout_round"] == round_
                and manifest["registered_arms"] == count and len(manifest["slots"]) * 2 == count,
                "fixed_pair_roster")
        for slot in manifest["slots"]:
            require(set(slot["plans"]) == {"a_ref", "a_patch"}, "two_actual_pair_arms")
            for ref in slot["plans"].values():
                k = key(ref)
                require(k not in roles, "unique_roster_plan")
                roles[k] = (f"round{round_}_pair", exact_ref(ref))
    roster = graph.read(seeds["formal_roster"])
    require(roster["schema"] == STAGE + ".formal_batch" and roster["formal_unlock"] == seeds["formal_unlock"]
            and len(roster["plans"]) == 40
            and {(r["parent_seed"], r["method"]) for r in roster["plans"]} ==
            {(p, method) for p in range(1301, 1309) for method in graph.formal_methods},
            "fixed_forty_formal_roster")
    for row in roster["plans"]:
        k = key(row["plan"])
        require(k not in roles, "disjoint_formal_pair_roster")
        roles[k] = ("formal", exact_ref(row["plan"]))
    known = {key(row["plan"]): row for row in runs}
    require(set(roles) <= set(known), "all_registered_slots_executed_and_retained")
    for k, (role, ref) in roles.items():
        require(known[k]["plan"] == ref, "ledger_roster_same_plan_pin")
        known[k]["role"] = role
    for row in runs:
        if "role" not in row:
            receipt = graph.read(row["receipt"])
            row["role"] = "diagnostic" if receipt["status"] == "complete" else "failed_attempt"
    return roster


def run_small_files(graph, runs, receipts):
    for row in runs:
        directory = Path(row["plan"]["path"]).parent
        graph.add(row["plan"], "registration")
        graph.add(row["receipt"])
        complete = receipts[row["name"]]["status"] == "complete"
        for filename, category in RUN_FILES.items():
            path = directory / filename
            if not path.is_file():
                require(not complete or filename not in ("worker_report.json", "evaluation.json", "final_result.json.gz"),
                        "complete_run_required_small_file:" + str(path))
                graph.missing.append({"run": row["name"], "path": str(path),
                    "status": "missing_optional_or_failed_partial_artifact", "failed_attempt": not complete})
                continue
            dep = graph.add(graph.bound_file(path), category)
            for field, expected in (("evaluation", "evaluation.json"), ("final_result", "final_result.json.gz"),
                                    ("branch_evidence", "branch_evidence.json.gz")):
                if filename == expected:
                    row[field] = dep
        for filename in sorted(n for n in HISTORY if n.endswith(".gz")):
            path = directory / filename
            # No SHA or content read. Null is explicit; never invent a bound ref.
            graph.local_unhashed.append({"run": row["name"], "path": str(path),
                "present": path.is_file(), "sha256": None, "content_verified_by_assembler": False})
        callback_ref = graph.items.get(str((directory / "callback_audit_receipt.json").resolve()).casefold())
        if callback_ref:
            callback = graph.read(callback_ref["reference"])
            if isinstance(callback.get("sha256"), str):
                graph.exclude({"path": str(directory / "callback_audit.jsonl.gz"), "sha256": callback["sha256"]},
                              "Producer callback receipt byte hash; excluded stream not reread by assembler.")


def expand_support(graph, seeds):
    admin = []
    # Declare all reports first, including large gates, before fit bindings use them.
    for group, entries in seeds["support_groups"].items():
        for item in entries:
            graph.add(item["reference"], item["category"], structured=item.get("structured_audit"))
            if group == "administrative_and_failures":
                admin.append(item["reference"])
    for entries in seeds["support_groups"].values():
        for item in entries:
            graph.visit(item["reference"], item["category"], item.get("route", "leaf"),
                        structured=item.get("structured_audit"))
            for dep in item.get("dependencies", []):
                graph.visit(dep["reference"], dep["category"], dep.get("route", "leaf"),
                            structured=dep.get("structured_audit"))
    schemas = {"g31.inventory_spi.precollection_raw_evidence_gate.v1",
               "g31.inventory_spi.paired_physical_admission.v1",
               "g31.inventory_spi.selected_action_small_chain_audit.v1"}
    for round_, arms in ((0, 48), (1, 24)):
        seen = set()
        for item in seeds["support_groups"][f"round{round_}_gates"]:
            require(item.get("route") == "pair_gate", "required_gate_explicit_route")
            value = graph.read(item["reference"], maximum=(item.get("structured_audit") or {}).get("max_bytes", MAX_SMALL))
            require(value["schema"] in schemas and value["schema"] not in seen
                    and value["manifest"] == seeds[f"round{round_}_manifest"]
                    and value["registered_arms"] == arms and value["registered_pairs"] == arms // 2
                    and len(value["arms"]) == arms, "same_full_round_gate_denominators")
            seen.add(value["schema"])
        require(seen == schemas, "raw_physical_T08_all_three_bound_reports")
    return admin


def expand_pipeline(graph, seeds):
    summary_ref = seeds["pipeline_summary"]
    graph.add(summary_ref, "report")
    v = graph.read(summary_ref)
    require(v["schema"] == PIPE + ".summary" and v["manifest"] == seeds["formal_roster"]
            and v["registered_jobs"] == 56 and len(v["jobs"]) == 56
            and len({r["job"]["id"] for r in v["jobs"]}) == 56
            and Counter(r["job"]["kind"] for r in v["jobs"]) == {"cache": 40, "mechanism": 8, "census": 8}
            and v["all_forty_cache_outputs_available"] is True, "final_fixed_56_job_summary")
    graph.visit(v["contract"], "registration", "pipeline_contract")
    formal_names = {name for name, row in graph.run_lookup.items() if row["role"] == "formal"}
    require(set(v["cache_index"]) == formal_names, "all_forty_cache_names")
    seen_cells = set()
    for row in v["jobs"]:
        job = row["job"]
        require(job["name"] in formal_names and job["plan"] == graph.run_lookup[job["name"]]["plan"],
                "pipeline_registered_job_plan")
        plan = graph.read(job["plan"])
        require(job["parent_seed"] == plan["parent"]["parent_seed"] and job["method"] == plan["method"]
                and (job["kind"] != "mechanism" or job["method"] == R0_METHOD)
                and (job["kind"] != "census" or job["method"] == "C00"), "fixed_pipeline_method_and_parent")
        cell = (job["kind"], job["name"])
        require(cell not in seen_cells, "unique_pipeline_kind_run")
        seen_cells.add(cell)
        if row["receipt"] is None:
            require(job["kind"] != "cache", "missing_formal_cache_receipt")
            require(row["status"] == "not_started_pending_or_budget_insufficient",
                    "known_unstarted_offline_status_only")
            graph.missing.append({"job": job, "status": row["status"], "scope": "No offline receipt/output; no coverage claimed."})
            continue
        graph.add(row["receipt"])
        receipt = graph.read(row["receipt"])
        require(receipt["schema"] == PIPE + ".job_receipt" and receipt["job"] == job
                and receipt["status"] == row["status"], "pipeline_receipt_identity")
        graph.add(receipt["request"], "registration")
        request = graph.read(receipt["request"])
        require(request["job"] == job and request["manifest"] == seeds["formal_roster"]
                and request["contract"] == v["contract"], "pipeline_request_binding")
        if request.get("command"):
            graph.add(request["command"]["helper"], "validator")
        output = receipt.get("output")
        if output is None:
            require(job["kind"] != "cache", "missing_formal_cache_output")
            require(receipt["status"] in ("failed_offline_process", "offline_timeout_no_acceptance",
                                         "unavailable_unverified_closure", "unavailable_failed_parent"),
                    "known_failed_or_unavailable_offline_status_only")
            graph.missing.append({"job": job, "status": receipt["status"], "scope": "Unavailable offline output retained."})
        else:
            require(receipt["status"] == "completed_audit_output_recorded", "only_completed_bound_job_output")
            route = {"cache": "cache", "mechanism": "mechanism", "census": "T06"}[job["kind"]]
            graph.visit(output, "report", route)
            require(graph.read(output).get("status") == receipt["output_status"], "job_output_status_binding")
            graph.pipeline_outputs[job["kind"]][job["name"]] = output
            if job["kind"] == "cache":
                require(output == v["cache_index"][job["name"]], "cache_index_output_pin")
    require(len(graph.pipeline_outputs["cache"]) == 40, "forty_actual_cache_outputs")
    if seeds.get("pipeline_session"):
        graph.add(seeds["pipeline_session"], "registration")
        session = graph.read(seeds["pipeline_session"])
        require(session["schema"] == PIPE + ".session" and session["contract"] == v["contract"]
                and session["manifest"] == v["manifest"] and session["jobs"] == [r["job"] for r in v["jobs"]],
                "pipeline_session_same_roster")
    return v


def assemble(seeds_ref, *, output):
    """Write three small reviewable files; does not invoke preflight or build."""
    builder, selector, base, formal = load_helpers()
    graph = Graph(builder, selector, base)
    graph.formal_methods = tuple(formal.METHODS)
    require(R0_METHOD in graph.formal_methods, "pinned_real_R0_method_id")
    seeds = graph.read(seeds_ref, early=True)
    validate_seeds(seeds)
    output = Path(output).resolve()
    require(output.is_relative_to(HERE) and not output.exists(), "fresh_support_request_directory")
    runs, receipts = terminal_roster(graph, seeds, formal)
    roster = bind_rosters(graph, seeds, runs)
    graph.derived_include = {key(ref): exact_ref(ref) for ref in seeds.get("include_derived_census", [])}
    graph.expected_collections = {round_: exact_ref(seeds[f"round{round_}_collection"]) for round_ in (0, 1)}
    require(len(graph.derived_include) == len(seeds.get("include_derived_census", [])), "unique_derived_inclusion_refs")
    graph.add(seeds_ref, "registration")
    graph.add(seeds["attempt_ledger"], "ledger")
    admin = expand_support(graph, seeds)
    for row in seeds["superseded_manifests"]:
        # Old unexecuted plans stay unopened; only their small manifest bytes.
        graph.add(row["reference"], "registration")
        graph.add(row["replacement"], "registration")
    for row in seeds.get("excluded_references", []):
        graph.exclude(row, row["scope"])
    run_small_files(graph, runs, receipts)
    for row in runs:
        graph.visit(row["plan"], "registration", "plan")
    graph.visit(seeds["stage_freeze"], "model", "stage")
    graph.visit(seeds["execution_receipt"], "receipt", "fit")
    for round_ in (0, 1):
        graph.visit(seeds[f"round{round_}_collection"], "dataset", "collection")
        graph.visit(seeds[f"round{round_}_manifest"], "registration", "pair_manifest")
    graph.visit(seeds["formal_roster"], "registration", "formal_roster")
    graph.visit(seeds["formal_unlock"], "registration", "unlock")
    pipeline = expand_pipeline(graph, seeds)
    if seeds.get("T06_aggregate"):
        graph.visit(seeds["T06_aggregate"], "report", "T06")
    require(set(graph.derived_include) == graph.derived_consumed, "only_actual_pipeline_derived_census_included")
    for name in ("grid_audit", "effects"):
        graph.add(seeds[name], "report")
        value = graph.read(seeds[name])
        require(value["source_manifest"] == seeds["formal_roster"]
                and value["source_cached_audits"] == pipeline["cache_index"], "grid_effects_bound_cache_basis")
        graph.implementation(value)
    graph.add(seeds["implementation_review"], "review")
    require(seeds["implementation_review"]["sha256"] == builder.REVIEW_SHA, "fixed_implementation_review")
    for name, expected in (("build_final_compact_publication_002.py", BUILDER_SHA),
                          ("compact_publication_allowlist_002.py", builder.SELECTOR_SHA),
                          ("audit_compact_publication_001.py", builder.BASE_SHA),
                          ("audit_compact_formal_002.py", builder.FORMAL_SHA)):
        graph.add({"path": str(HERE / name), "sha256": expected}, "validator")
    graph.add(graph.bound_file(__file__), "validator")
    stage = graph.read(seeds["stage_freeze"])
    frozen = graph.read(stage["spi_freeze"])
    training = {"stage_freeze": seeds["stage_freeze"], "spi_freeze": stage["spi_freeze"],
        "round0_collection": seeds["round0_collection"], "round1_collection": seeds["round1_collection"],
        "execution_receipt": seeds["execution_receipt"],
        "fit_events": [graph.bound_file(Path(m["chain_receipt"]["path"]).parent / "fit_events.jsonl")
                       for m in frozen["models"]]}
    formal_runs = [{**r, "cache": pipeline["cache_index"][r["name"]]} for r in runs if r["role"] == "formal"]
    request = {"schema": builder.SCHEMA + ".request", "actual_final_publication": True,
        "attempt_ledger": seeds["attempt_ledger"], "expected_long_attempts": seeds["expected_long_attempts"],
        "runs": runs, "training": training,
        "formal": {"roster": seeds["formal_roster"], "unlock": seeds["formal_unlock"],
            "gate_implementation": {"path": str(HERE / "formal_analysis_gate_001.py"), "sha256": formal.GATE_SHA},
            "runs": formal_runs, "grid_audit": seeds["grid_audit"], "effects": seeds["effects"]},
        "gate_basis": {"implementation_review": seeds["implementation_review"]},
        "administrative_artifacts": admin + [seeds["execution_receipt"], seeds["pipeline_summary"]],
        "superseded_manifests": seeds["superseded_manifests"],
        "excluded_large_logs": list(graph.excluded.values()), "comparisons": seeds.get("comparisons", [])}
    spec = {"schema": selector.SCHEMA + ".request", "template_not_final": False,
        "registered_run_slots": [{"slot_id": r["name"], "role": r["role"], "plan": r["plan"]} for r in runs],
        "compact_artifacts": list(graph.items.values()), "source_manifests": list(graph.sources.values()),
        "formal_unlock": seeds["formal_unlock"]}
    # Validate the mapped graph before writing a concrete request. This is not
    # builder.preflight: no copied-file validation or scientific numerical audit.
    package = builder.ExplicitFiles(spec, request, selector, base)
    _, unlocked, slots, _, freeze_check = formal.unlock_graph(package, base, request["formal"])
    training_check = builder.validate_training(package, request, base, formal, unlocked)
    for entry in roster["plans"]:
        row = slots[base.original_key(entry["plan"]["path"])]
        plan = formal.plan_binding(package, base, roster, unlocked, entry, row)
        cache, _ = formal.cache_binding(package, base, request["formal"], entry, row, plan)
        if receipts[row["name"]]["status"] != "complete":
            require(cache["status"] == "blocked" and cache["row"]["full_window_cost"] is None
                    and cache["row"]["backlog_relief"] is None, "failed_primary_null")
    # These shape checks cannot fail only after partial request output exists.
    shape_request = {**request, "allowlist_request":
                     {"path": str(output / "allowlist_request.json"), "sha256": "0" * 64}}
    builder.validate_request_shape(shape_request)
    # Stability at write boundary; no native ledger or receipt may change.
    require(sha(seeds["attempt_ledger"]["path"]) == seeds["attempt_ledger"]["sha256"], "ledger_changed_during_assembly")
    for row in runs:
        require(sha(row["receipt"]["path"]) == row["receipt"]["sha256"], "receipt_changed_during_assembly")
    report = {"schema": SCHEMA + ".assembly_report", "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "explicit_requests_prepared_not_preflighted_or_built", "seeds": seeds_ref,
        "assembler": graph.bound_file(__file__), "registered_long_attempts": len(runs),
        "role_counts": dict(Counter(r["role"] for r in runs)), "terminal_status_counts":
            dict(Counter(r["status"] for r in receipts.values())),
        "included_original_path_count": len(graph.items), "source_manifest_count": len(graph.sources),
        "excluded_bound_reference_count": len(graph.excluded), "missing_optional_small_artifacts": graph.missing,
        "local_history_index": [row for row in graph.local_unhashed if key({"path": row["path"], "sha256": "0"*64})
                                not in graph.excluded],
        "external_environment_provenance": graph.external,
        "historical_mutable_reference_declarations": graph.historical_mutable_refs,
        "pipeline_job_statuses": [{"job": r["job"], "status": r["status"]} for r in pipeline["jobs"]],
        "T06_aggregate_unavailable": seeds.get("T06_aggregate_unavailable"),
        "freeze_identity_check": freeze_check, "training_identity_check": training_check,
        "excluded_content_read": False, "native_operations": 0, "fit_operations": 0,
        "package_builds": 0, "builder_preflight_runs": 0, "numerical_audit_performed": False}
    output.mkdir()
    report_ref = write_new(output / "assembly_report.json", report, builder)
    spec["compact_artifacts"].append({"reference": report_ref, "category": "report"})
    spec_ref = write_new(output / "allowlist_request.json", spec, builder)
    request["allowlist_request"] = spec_ref
    request["administrative_artifacts"].append(report_ref)
    builder.validate_request_shape(request)
    request_ref = write_new(output / "builder_request.json", request, builder)
    return {"schema": SCHEMA + ".result", "request": request_ref, "allowlist": spec_ref, "report": report_ref,
            "next_step": "Review requests, explicitly run pinned builder002 preflight/build, then portable formal002 audit.",
            "package_builds": 0, "native_operations": 0, "fit_operations": 0}


def write_new(path, value, builder):
    builder.dump_new(path, value)
    return builder.reference(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=Path, required=True)
    parser.add_argument("--seeds-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(assemble({"path": str(args.seeds.resolve()), "sha256": args.seeds_sha256},
                              output=args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
