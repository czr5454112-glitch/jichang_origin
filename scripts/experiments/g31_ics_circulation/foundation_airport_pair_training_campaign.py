"""Registered finite train/dev chains for actual received-plan paired data.

Preparing a campaign never fits. Running one registered variant/seed chain
attempts linear and small-MLP fits within one shared 300-second deadline.
No function discovers, opens, evaluates or selects using test datasets.
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import os
from pathlib import Path
import time
import traceback

from . import foundation_airport_pair_ranker as ranker
from . import foundation_multistep_learning as multistep
from . import foundation_fqi_checkpoint_selection as checkpoint_selection
from .foundation_airport_batch_patch import digest

SCHEMA = "g31.foundation.airport_pair_training_campaign.v1"
CHAIN_SCHEMA = "g31.foundation.airport_pair_training_chain.v1"
DOMAINS = ("primary_22", "mixed_18_22_26")
WALL_SECONDS = 300.


def require(ok, reason):
    if not ok:
        raise ValueError("airport_pair_training_campaign:" + reason)


def orchestration_source_pins():
    return {"scripts/experiments/g31_ics_circulation/"+Path(module.__file__).name:
        hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        for module in (multistep, checkpoint_selection)} | {
            "scripts/experiments/g31_ics_circulation/"+Path(__file__).name:
                hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def file_ref(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def read_bound(reference):
    path = Path(reference["path"])
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == reference["sha256"], "bound_artifact_bytes")
    return json.loads(gzip.decompress(raw) if path.name.endswith(".gz") else raw)


def _write_new(path, value):
    path = Path(path)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False).encode("utf8") + b"\n"
    if path.name.endswith(".gz"):
        raw = gzip.compress(raw, compresslevel=6, mtime=0)
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return file_ref(path)


def _event(path, value):
    with Path(path).open("a", encoding="utf8", newline="\n") as stream:
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _source_archive(directory):
    package = Path(__file__).resolve().parent
    root = package.parents[2]
    sources = list(package.glob("*.py"))
    sources.extend(path for path in (root/"scripts/__init__.py", root/"scripts/experiments/__init__.py")
        if path.is_file())
    archived = {}
    for source in sorted(sources):
        relative = source.relative_to(root)
        target = directory/"source"/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = source.read_bytes()
        with target.open("xb") as stream:
            stream.write(raw)
        archived[relative.as_posix()] = {"original_path": str(source),
            "sha256": hashlib.sha256(raw).hexdigest(), "archive": file_ref(target)}
    return archived


def load_datasets(inputs, *, split, training_domain):
    """Load explicit bound artifacts after rejecting test/batch metadata.

    Input item: dataset, reference_plan and patched_plan, each a path/SHA ref.
    Plans establish collection batch and parent; filenames confer no authority.
    """
    require(split in ("train", "dev") and training_domain in DOMAINS, "train_dev_domain_only")
    permitted_batches = {"H", "C"} if training_domain == "primary_22" else {"H", "C", "F"}
    datasets, provenance, duplicates, seen = [], [], [], {}
    for item in inputs:
        plans = [read_bound(item[key]) for key in ("reference_plan", "patched_plan")]
        reference, patched = plans
        # Check metadata before opening any possibly outcome-bearing dataset.
        require(reference["parent"]["split"] == patched["parent"]["split"] == split,
            "test_or_wrong_split_plan_rejected_before_data_read")
        require(reference["batch"] == patched["batch"] and reference["batch"] in permitted_batches,
            "same_fair_H_C_train_budget_B_mechanism_only")
        require(reference["branch"] == "a_ref" and patched["branch"] == "a_patch"
            and reference["parent"] == patched["parent"]
            and reference["window"] == patched["window"], "paired_collection_plan_binding")
        require(reference["input"]["sha256"] == patched["input"]["sha256"], "same_registered_physical_input")
        fleet = reference["parent"]["fleet"]
        require(fleet == 22 if training_domain == "primary_22" else fleet in (18, 22, 26),
            "registered_resource_domain")
        dataset = read_bound(item["dataset"])
        require(dataset["pair"]["parent"] == reference["parent"], "dataset_registered_parent")
        # Both variants share the same actual received-plan rows. Missing C11
        # receipt cannot silently give C01 extra data.
        ranker.prepare_pairs([dataset], information_variant="C11", split=split)
        pair = dataset["pair"]
        provenance_row = {"batch": reference["batch"], "parent": reference["parent"],
            "input_sha256": reference["input"]["sha256"], "artifacts": copy.deepcopy(item),
            "pair_status": pair["status"], "pair_id": pair.get("pair_id")}
        if pair["status"] == "closed_actual_pair":
            require(type(pair.get("complete_prefix_sha256")) is str
                and len(pair["complete_prefix_sha256"]) == 64, "complete_physical_prefix_required")
            key = digest({"parent_group": ranker._parent_group(pair["parent"]), "fleet": fleet,
                "prefix": pair["complete_prefix_sha256"],
                "actions": [row["semantic_action"] for row in dataset["rows"]],
                "label_start": pair["reference_cost"]["label_start"],
                "label_end": pair["reference_cost"]["label_end"]})
            if key in seen:
                prior = seen[key]
                require(all(pair[field] == prior["pair"][field] for field in
                    ("advantage_bag_seconds", "reference_cost", "patched_cost", "per_job_comparison_counts")),
                    "duplicate_physical_contrast_has_conflicting_outcome")
                duplicates.append(dict(provenance_row, physical_contrast_sha256=key,
                    counted_as_independent_sample=False))
                continue
            seen[key] = dataset
            provenance_row["physical_contrast_sha256"] = key
        datasets.append(dataset)
        provenance.append(provenance_row)
    return datasets, {"included": provenance, "deduplicated": duplicates,
        "input_artifact_count": len(inputs), "included_dataset_count": len(datasets)}


def _resource_gate(train, dev, provenance):
    train_F = {item["pair_id"] for item in provenance["train"]["included"] if item["batch"] == "F"}
    dev_F = {item["pair_id"] for item in provenance["dev"]["included"] if item["batch"] == "F"}
    train_resource = [item for item in train if item["pair"].get("pair_id") in train_F
        and item["pair"]["status"] == "closed_actual_pair"]
    dev_resource = [item for item in dev if item["pair"].get("pair_id") in dev_F
        and item["pair"]["status"] == "closed_actual_pair"]
    reasons = []
    if {item["pair"]["parent"]["fleet"] for item in train_resource} != {18, 26}:
        reasons.append("both_resource_train_cells_not_closed")
    if {item["pair"]["parent"]["fleet"] for item in dev_resource} != {18, 26}:
        reasons.append("both_resource_dev_cells_not_closed")
    if not any(item["pair"]["action_difference"] and abs(item["pair"]["advantage_bag_seconds"]) > 1e-9
               for item in train_resource):
        reasons.append("resource_train_pairs_have_no_nonzero_action_information")
    return {"eligible": not reasons, "reasons": reasons}


def prepare_manifest(*, output, train_inputs, dev_inputs, training_domain,
                     forecast_addendum, model_available_at_epoch_seconds):
    """Persist source/data/12 fit registrations and six chain plans; do no fits."""
    require(training_domain in DOMAINS, "registered_training_domain")
    addendum = read_bound(forecast_addendum)
    require(addendum["schema"] == "g31.action_forecast_capture_addendum.v1"
        and addendum["test_opened"] is False and addendum["H_long_branches"] == 4
        and "same" in addendum["training_fairness"], "actual_forecast_fairness_addendum")
    train, train_provenance = load_datasets(train_inputs, split="train", training_domain=training_domain)
    dev, dev_provenance = load_datasets(dev_inputs, split="dev", training_domain=training_domain)
    transition_gates = {split: multistep.airport_paired_transition_gate(datasets)
        for split, datasets in (("train", train), ("dev", dev))}
    provenance = {"train": train_provenance, "dev": dev_provenance}
    gates = {variant: ranker.sufficiency(train, information_variant=variant) for variant in ranker.VARIANTS}
    dev_pairs, unavailable_dev = ranker.prepare_pairs(dev, information_variant="C11", split="dev")
    available = ranker.number(model_available_at_epoch_seconds)
    reasons = [variant+":"+reason for variant, gate in gates.items() for reason in gate["reasons"]]
    if not dev_pairs:
        reasons.append("no_closed_actual_received_plan_development_pairs")
    else:
        require(available <= min(pair["observed_at_epoch_seconds"] for pair in dev_pairs),
            "model_availability_precedes_all_dev_decisions")
    closed_train = [item for item in train if item["pair"]["status"] == "closed_actual_pair"]
    if closed_train:
        require(available >= max(item["pair"]["parent"]["calendar_start_epoch_seconds"]
            + item["pair"]["reference_cost"]["label_end"] for item in closed_train),
            "training_labels_close_before_model_availability")
    resource = _resource_gate(train, dev, provenance) if training_domain == "mixed_18_22_26" else None
    if resource is not None:
        reasons.extend(resource["reasons"])
    directory = Path(output).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    sources = _source_archive(directory)
    transition_gate_ref = _write_new(directory/"transition_gate.json", transition_gates)
    snapshots = {"train": _write_new(directory/"train_datasets.json.gz", train),
        "dev": _write_new(directory/"dev_datasets.json.gz", dev)}
    campaign_id = digest({"domain": training_domain, "train": digest(train), "dev": digest(dev),
        "sources": ranker.source_pins(), "addendum": forecast_addendum,
        "model_available_at_epoch_seconds": available})
    chain_refs = []
    eligible = not reasons
    if eligible:
        for variant in ranker.VARIANTS:
            for seed in ranker.SEEDS:
                chain_id = f"{training_domain}_{variant}_seed{seed}"
                chain_dir = directory/chain_id
                chain_dir.mkdir()
                registrations = {}
                for architecture in ranker.ARCHITECTURES:
                    registration = ranker.make_registration(train, information_variant=variant, seed=seed,
                        architecture=architecture, model_available_at_epoch_seconds=available,
                        registration_id=campaign_id+":"+chain_id+":"+architecture)
                    registrations[architecture] = _write_new(chain_dir/(architecture+"_registration.json"), registration)
                chain_plan = {"schema": CHAIN_SCHEMA, "status": "registered_not_run",
                    "campaign_id": campaign_id, "chain_id": chain_id, "output": str(chain_dir),
                    "training_domain": training_domain, "information_variant": variant, "seed": seed,
                    "training_job_units": 1, "primary_fit_calls_planned": 2,
                    "architectures": list(ranker.ARCHITECTURES), "epochs_per_fit": 100,
                    "wall_budget_seconds": WALL_SECONDS, "snapshots": snapshots,
                    "registrations": registrations, "source_sha256": ranker.source_pins(),
                    "runner_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "orchestration_source_sha256": orchestration_source_pins(),
                    "transition_gate": transition_gate_ref,
                    "selection_rule": ranker.SELECTION_RULE, "test_opened": False,
                    "native_jobs": 0, "bootstrap_used": False}
                chain_refs.append(_write_new(chain_dir/"chain_plan.json", chain_plan))
    manifest = {"schema": SCHEMA, "campaign_id": campaign_id, "output": str(directory),
        "status": "registered_not_run" if eligible else "blocked_insufficient_information_no_fits",
        "training_domain": training_domain, "forecast_addendum": copy.deepcopy(forecast_addendum),
        "shared_train_dataset_sha256": digest(train), "shared_dev_dataset_sha256": digest(dev),
        "information_variants": list(ranker.VARIANTS), "seeds": list(ranker.SEEDS),
        "snapshots": snapshots, "dataset_provenance": provenance, "source_archive": sources,
        "orchestration_source_sha256": orchestration_source_pins(), "transition_gate": transition_gate_ref,
        "sufficiency": gates, "unavailable_dev_pairs": unavailable_dev, "resource_gate": resource,
        "blocking_reasons": reasons, "chain_plans": chain_refs, "requested_training_jobs": 6 if eligible else 0,
        "primary_fit_calls_planned": 12 if eligible else 0, "control_regression_fit_calls_planned": 1 if eligible else 0,
        "fit_calls_started": 0, "native_jobs": 0, "test_opened": False,
        "model_available_at_epoch_seconds": available, "complete_campaign_wall_seconds_upper_bound": 6*WALL_SECONDS,
        "training_job_definition": "one information variant x one seed x one resource domain; two finite model fits within that chain"}
    reference = _write_new(directory/"manifest.json", manifest)
    return {"manifest": reference, "status": manifest["status"], "chain_plans": chain_refs,
        "fit_calls_started": 0, "blocking_reasons": reasons}


def _validate_chain(plan):
    require(plan["schema"] == CHAIN_SCHEMA and plan["status"] == "registered_not_run"
        and plan["test_opened"] is False and plan["wall_budget_seconds"] == WALL_SECONDS
        and plan["architectures"] == list(ranker.ARCHITECTURES)
        and plan["epochs_per_fit"] == 100 and plan["selection_rule"] == ranker.SELECTION_RULE,
        "exact_registered_chain")
    require(plan["source_sha256"] == ranker.source_pins()
        and plan["runner_source_sha256"] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        and plan["orchestration_source_sha256"] == orchestration_source_pins(),
        "source_changed_after_registration")


def run_registered_chain(chain_reference):
    """Attempt one registered chain once. Caller owns campaign authorization."""
    plan = read_bound(chain_reference)
    directory = Path(plan["output"])
    started = time.perf_counter()
    deadline = time.monotonic()+WALL_SECONDS
    _write_new(directory/"run_started.json", {"chain_plan": chain_reference, "started_epoch_seconds": time.time(),
        "wall_budget_seconds": WALL_SECONDS, "automatic_retries": 0})
    events_path = directory/"fit_events.jsonl"
    result = {"schema": CHAIN_SCHEMA, "chain_plan": chain_reference, "status": "failed",
        "fit_calls_started": 0, "fit_calls_completed": 0, "models": [],
        "training_job_units_attempted": 1, "native_jobs": 0, "test_used": False}
    try:
        _validate_chain(plan)
        train, dev = (read_bound(plan["snapshots"][split]) for split in ("train", "dev"))
        models = []
        for architecture in plan["architectures"]:
            registration = read_bound(plan["registrations"][architecture])
            require(time.monotonic() <= deadline, "shared_chain_wall_budget")
            result["fit_calls_started"] += 1
            _event(events_path, {"event": "fit_started", "architecture": architecture,
                "fit_ordinal": result["fit_calls_started"], "at_epoch_seconds": time.time(),
                "registration": plan["registrations"][architecture]})
            model = ranker.fit_ranker(train, information_variant=plan["information_variant"], seed=plan["seed"],
                architecture=architecture, registration=registration, deadline=deadline, epochs=100)
            reference = ranker.save_model(directory/(architecture+"_model.json"), model)
            result["models"].append(dict(reference, architecture=architecture))
            result["fit_calls_completed"] += 1
            models.append(model)
            _event(events_path, {"event": "fit_completed", "architecture": architecture,
                "at_epoch_seconds": time.time(), "model": reference,
                "epochs": model["epochs"], "wall_seconds": model["wall_seconds"]})
        require(time.monotonic() <= deadline, "shared_chain_wall_budget")
        selection = checkpoint_selection.select_airport_paired_checkpoint(models, dev)
        require(time.monotonic() <= deadline, "shared_chain_wall_budget")
        result.update(status="completed_two_fits_and_frozen_dev_selection",
            selection=_write_new(directory/"selection.json", selection),
            selected_model_id=selection["selected_model_id"])
    except Exception:
        result["exception"] = traceback.format_exc()
        _event(events_path, {"event": "chain_failed", "at_epoch_seconds": time.time(),
            "fit_calls_started": result["fit_calls_started"], "fit_calls_completed": result["fit_calls_completed"],
            "exception": result["exception"]})
    result["wall_seconds"] = time.perf_counter()-started
    result["finished_epoch_seconds"] = time.time()
    result["fit_event_artifact"] = file_ref(events_path) if events_path.exists() else None
    result["receipt"] = str(directory/"receipt.json")
    return _write_new(directory/"receipt.json", result)


def run_registered_controls(campaign_reference):
    """One separately counted train-only time-control regression, never a policy."""
    campaign = read_bound(campaign_reference)
    require(campaign["status"] == "registered_not_run" and campaign["test_opened"] is False,
        "eligible_registered_campaign_required")
    output = Path(campaign["output"])
    _write_new(output/"controls_started.json", {"campaign": campaign_reference,
        "fit_calls_planned": 1, "training_job_units": 0, "started_epoch_seconds": time.time()})
    started = time.perf_counter()
    receipt = {"schema": SCHEMA, "status": "failed", "fit_calls_started": 0, "fit_calls_completed": 0,
        "training_job_units": 0, "test_used": False, "native_jobs": 0}
    try:
        for chain in campaign["chain_plans"]:
            _validate_chain(read_bound(chain))
        train, dev = (read_bound(campaign["snapshots"][split]) for split in ("train", "dev"))
        receipt["fit_calls_started"] = 1
        _event(output/"controls_events.jsonl", {"event": "control_fit_started", "fit_calls_started": 1,
            "at_epoch_seconds": time.time()})
        result = ranker.action_and_time_controls(train, dev)
        receipt.update(status="completed_train_only_control_regression", fit_calls_completed=1,
            controls=_write_new(output/"controls.json", result))
    except Exception:
        receipt["exception"] = traceback.format_exc()
    receipt["wall_seconds"] = time.perf_counter()-started
    _event(output/"controls_events.jsonl", {"event": "control_chain_finished",
        "status": receipt["status"], "fit_calls_started": receipt["fit_calls_started"],
        "fit_calls_completed": receipt["fit_calls_completed"], "at_epoch_seconds": time.time()})
    return _write_new(output/"controls_receipt.json", receipt)


def freeze_all(campaign_references, *, output):
    """Freeze all six selected models per requested domain before any test read."""
    require(campaign_references, "explicit_campaign_references")
    all_models, campaigns, fit_started, fit_completed = [], [], 0, 0
    controls, control_started, control_completed = [], 0, 0
    domains = set()
    for campaign_ref in campaign_references:
        campaign = read_bound(campaign_ref)
        require(campaign["status"] == "registered_not_run" and campaign["test_opened"] is False
            and len(campaign["chain_plans"]) == 6, "all_registered_chains_required")
        require(campaign["training_domain"] not in domains, "unique_training_domain")
        domains.add(campaign["training_domain"])
        cells = set()
        for chain_ref in campaign["chain_plans"]:
            plan = read_bound(chain_ref)
            _validate_chain(plan)
            receipt_ref = file_ref(Path(plan["output"])/"receipt.json")
            receipt = read_bound(receipt_ref)
            require(receipt["status"] == "completed_two_fits_and_frozen_dev_selection"
                and receipt["fit_calls_started"] == receipt["fit_calls_completed"] == 2
                and receipt["chain_plan"] == chain_ref, "every_chain_completed_no_partial_freeze")
            selection = read_bound(receipt["selection"])
            selected = [ref for ref in receipt["models"] if ref["model_id"] == selection["selected_model_id"]]
            require(len(selected) == 1 and selection["frozen_before_test"] is True, "one_frozen_dev_selected_model")
            model = read_bound(selected[0])
            require(model["model_id"] == selected[0]["model_id"]
                and model["model_id"] == digest({key: value for key, value in model.items() if key != "model_id"})
                and model["seed"] == plan["seed"] and model["information_variant"] == plan["information_variant"]
                and model["training_dataset_sha256"] == campaign["shared_train_dataset_sha256"],
                "frozen_selected_weight_and_fair_dataset")
            cell = (model["information_variant"], model["seed"])
            require(cell not in cells, "one_model_per_variant_seed")
            cells.add(cell)
            all_models.append({"training_domain": campaign["training_domain"],
                "information_variant": model["information_variant"], "seed": model["seed"],
                "model_id": model["model_id"], "checkpoint": selected[0],
                "chain_receipt": receipt_ref, "selection": receipt["selection"],
                "training_labels_closed_at_epoch_seconds": model["training_labels_closed_at_epoch_seconds"],
                "model_available_at_epoch_seconds": model["model_available_at_epoch_seconds"],
                "native_execution_authority": False, "protected_takeover_eligible": False})
            fit_started += receipt["fit_calls_started"]
            fit_completed += receipt["fit_calls_completed"]
        require(cells == {(variant, seed) for variant in ranker.VARIANTS for seed in ranker.SEEDS},
            "all_fixed_information_variant_seed_cells")
        controls_path = Path(campaign["output"])/"controls_receipt.json"
        require(controls_path.exists() or not (Path(campaign["output"])/"controls_started.json").exists(),
            "unfinished_control_fit_accounting")
        if controls_path.exists():
            control_ref = file_ref(controls_path)
            control = read_bound(control_ref)
            require(control["test_used"] is False and 0 <= control["fit_calls_completed"]
                <= control["fit_calls_started"] <= 1, "separate_control_fit_accounting")
            controls.append(control_ref)
            control_started += control["fit_calls_started"]
            control_completed += control["fit_calls_completed"]
        campaigns.append(campaign_ref)
    manifest = {"schema": SCHEMA, "status": "all_requested_models_frozen_before_test",
        "campaigns": campaigns, "models": all_models, "training_domains": sorted(domains),
        "training_job_units": 6*len(campaigns), "primary_fit_calls_started": fit_started,
        "primary_fit_calls_completed": fit_completed, "test_opened": False,
        "control_receipts": controls, "control_fit_calls_started": control_started,
        "control_fit_calls_completed": control_completed,
        "native_control_benefit_established": False, "multistep_RL_established": False,
        "protected_takeover_eligible": False, "selection_rule": ranker.SELECTION_RULE,
        "frozen_epoch_seconds": time.time()}
    return _write_new(output, manifest)


def validate_frozen_manifest(reference, *, required_domains, validate_runtime_sources=True):
    """Portable artifact gate for prospective test; never opens outcome data."""
    require(set(required_domains) <= set(DOMAINS) and required_domains, "explicit_required_training_domains")
    frozen = read_bound(reference)
    require(frozen["schema"] == SCHEMA and frozen["status"] == "all_requested_models_frozen_before_test"
        and frozen["test_opened"] is False and set(frozen["training_domains"]) == set(required_domains)
        and frozen["selection_rule"] == ranker.SELECTION_RULE
        and type(frozen["frozen_epoch_seconds"]) in (int, float), "all_required_domains_frozen_before_test")
    campaigns = {}
    for campaign_ref in frozen["campaigns"]:
        campaign = read_bound(campaign_ref)
        require(campaign["status"] == "registered_not_run" and campaign["test_opened"] is False
            and campaign["training_domain"] not in campaigns, "registered_unique_domain_campaign")
        campaigns[campaign["training_domain"]] = campaign
    require(set(campaigns) == set(required_domains), "all_required_campaign_artifacts")
    cells, sources_checked = set(), set()
    for selected in frozen["models"]:
        domain, variant, seed = (selected[key] for key in ("training_domain", "information_variant", "seed"))
        require(domain in campaigns and variant in ranker.VARIANTS and seed in ranker.SEEDS
            and (domain, variant, seed) not in cells, "unique_registered_frozen_cell")
        cells.add((domain, variant, seed))
        campaign = campaigns[domain]
        model = read_bound(selected["checkpoint"])
        require(model["model_id"] == selected["model_id"]
            == digest({key: item for key, item in model.items() if key != "model_id"})
            and model["information_variant"] == variant and model["seed"] == seed
            and model["training_dataset_sha256"] == campaign["shared_train_dataset_sha256"]
            and model["model_available_at_epoch_seconds"] == selected["model_available_at_epoch_seconds"]
            and model["training_labels_closed_at_epoch_seconds"] == selected["training_labels_closed_at_epoch_seconds"],
            "frozen_model_identity_and_training_binding")
        receipt = read_bound(selected["chain_receipt"])
        plan = read_bound(receipt["chain_plan"])
        require(receipt["status"] == "completed_two_fits_and_frozen_dev_selection"
            and receipt["fit_calls_started"] == receipt["fit_calls_completed"] == 2
            and receipt["chain_plan"] in campaign["chain_plans"]
            and plan["campaign_id"] == campaign["campaign_id"]
            and plan["information_variant"] == variant and plan["seed"] == seed
            and plan["training_domain"] == domain and plan["test_opened"] is False
            and selected["checkpoint"] in receipt["models"]
            and receipt["selection"] == selected["selection"], "closed_registered_training_chain")
        selection = read_bound(selected["selection"])
        require(selection["selected_model_id"] == model["model_id"]
            and selection["frozen_before_test"] is True and selection["selection_rule"] == ranker.SELECTION_RULE
            and selection["development_dataset_sha256"] == campaign["shared_dev_dataset_sha256"],
            "bound_dev_selection_without_test")
        registration = model["registration"]
        require(registration["training_dataset_sha256"] == campaign["shared_train_dataset_sha256"]
            and registration == read_bound(plan["registrations"][model["architecture"]])
            and registration["test_opened"] is False and registration["seed"] == seed
            and registration["information_variant"] == variant
            and model["training_labels_closed_at_epoch_seconds"] <= model["model_available_at_epoch_seconds"],
            "frozen_registration_dataset")
        if validate_runtime_sources:
            require(registration["feature_source_sha256"] == ranker.source_pins(),
                "runtime_feature_sources_match_frozen_training")
            require(campaign["orchestration_source_sha256"] == orchestration_source_pins(),
                "runtime_training_selection_entry_sources")
        require(plan["orchestration_source_sha256"] == campaign["orchestration_source_sha256"],
            "registered_training_selection_entry_sources")
        for logical, expected in (registration["feature_source_sha256"]
                | campaign["orchestration_source_sha256"]).items():
            archive = campaign["source_archive"][logical]
            require(archive["sha256"] == expected, "training_source_archive_binding")
            key = (archive["archive"]["path"], expected)
            if key not in sources_checked:
                raw = Path(archive["archive"]["path"]).read_bytes()
                require(hashlib.sha256(raw).hexdigest() == expected == archive["archive"]["sha256"],
                    "training_source_archive_bytes")
                sources_checked.add(key)
    expected_cells = {(domain, variant, seed) for domain in required_domains
        for variant in ranker.VARIANTS for seed in ranker.SEEDS}
    require(cells == expected_cells and frozen["training_job_units"] == 6*len(required_domains)
        and frozen["primary_fit_calls_started"] == frozen["primary_fit_calls_completed"] == 12*len(required_domains),
        "all_six_models_and_fit_counts_per_domain")
    return frozen


SPI_CAMPAIGN_SCHEMA = "g31.foundation.airport_spi_training_campaign.v1"


def _load_spi_inputs(inputs, *, split):
    """Caller must declare parent metadata before any artifact is opened."""
    require(split in ("train", "dev"), "spi_never_loads_test")
    datasets = []
    for item in inputs:
        parent = item["parent"]
        require(parent["split"] == split, "spi_declared_split_before_open")
        dataset = read_bound(item["dataset"])
        require(dataset["pair"]["parent"] == parent, "spi_declared_actual_parent_binding")
        for arm in ("reference_plan", "patched_plan"):
            if arm in item:
                plan = read_bound(item[arm])
                require(plan["parent"] == parent, "spi_actual_collection_plan_parent")
        datasets.append(dataset)
    return datasets


def _spi_sources():
    from . import foundation_airport_spi as spi
    from . import foundation_airport_pair_dataset as dataset
    from . import foundation_airport_service_metrics as metrics
    return spi.spi_source_pins() | {
        "scripts/experiments/g31_ics_circulation/"+Path(module.__file__).name:
            hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        for module in (dataset, metrics)} | {
        "scripts/experiments/g31_ics_circulation/"+Path(__file__).name:
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def prepare_spi_manifest(*, output, train_inputs, dev_inputs, contract,
                         model_available_at_epoch_seconds):
    """Register two deterministic variant chains, including real rule champions."""
    from . import foundation_airport_spi as spi
    train = _load_spi_inputs(train_inputs, split="train")
    dev = _load_spi_inputs(dev_inputs, split="dev")
    train_groups = {ranker._parent_group(d["pair"]["parent"]) for d in train}
    dev_groups = {ranker._parent_group(d["pair"]["parent"]) for d in dev}
    require(train_groups and dev_groups and not train_groups.intersection(dev_groups),
        "spi_disjoint_train_dev_parents")
    label_clocks = [d["pair"]["parent"]["calendar_start_epoch_seconds"]
        + d["pair"]["reference_cost"]["label_end"] for d in train
        if d["pair"]["status"] == "closed_actual_pair"]
    require(label_clocks and max(label_clocks) <= model_available_at_epoch_seconds,
        "spi_train_closed_before_weights_available")
    dev_clocks = [d["pair"]["parent"]["calendar_start_epoch_seconds"]
        + d["pair"]["reference_cost"]["label_end"] for d in dev
        if d["pair"]["status"] == "closed_actual_pair"]
    require(dev_clocks, "spi_at_least_one_closed_dev_pair")
    directory = Path(output).resolve()
    require(not directory.exists(), "spi_new_output_directory")
    directory.mkdir(parents=True)
    source_archive = _source_archive(directory)
    chains = []
    for variant in ranker.VARIANTS:
        pairs, unavailable = spi.prepare_spi_pairs(train, information_variant=variant,
            split="train", contract=contract)
        spi.prepare_spi_pairs(dev, information_variant=variant, split="dev", contract=contract)
        eligible = (len({ranker._parent_group(p["parent"]) for p in pairs}) >= contract["minimum_train_parents"]
            and sum(abs(p["advantage"]) > 1e-9 for p in pairs) >= contract["minimum_nonzero_contrasts"])
        registrations = [spi.make_spi_registration(train, information_variant=variant,
            solver=solver["solver"], ridge_lambda=solver["ridge_lambda"], contract=contract,
            model_available_at_epoch_seconds=model_available_at_epoch_seconds,
            registration_id=f"{directory.name}:{variant}:{index}")
            for index, solver in enumerate(contract["solver_candidates"])] if eligible else []
        for registration in registrations:
            registration["development_labels_closed_at_epoch_seconds"] = max(dev_clocks)
        chain_dir = directory/variant
        chain_dir.mkdir()
        plan = {"schema": SPI_CAMPAIGN_SCHEMA+".chain", "output": str(chain_dir),
            "information_variant": variant, "contract": copy.deepcopy(contract),
            "train_inputs": copy.deepcopy(train_inputs), "dev_inputs": copy.deepcopy(dev_inputs),
            "training_dataset_sha256": digest(train), "development_dataset_sha256": digest(dev),
            "model_available_at_epoch_seconds": model_available_at_epoch_seconds,
            "champion_selection_available_at_epoch_seconds": max(dev_clocks),
            "registrations": registrations, "reference_always_candidate": True,
            "source_sha256": _spi_sources(), "test_opened": False,
            "fit_calls_planned": len(registrations), "wall_seconds_limit": WALL_SECONDS,
            "sufficiency": {"eligible_to_fit": eligible, "unavailable_pairs": unavailable,
                "closed_pairs": len(pairs), "rule_only_if_insufficient": True}}
        chains.append(_write_new(chain_dir/"plan.json", plan))
    manifest = {"schema": SPI_CAMPAIGN_SCHEMA, "status": "registered_not_run",
        "output": str(directory), "contract": copy.deepcopy(contract),
        "train_inputs": copy.deepcopy(train_inputs), "dev_inputs": copy.deepcopy(dev_inputs),
        "train_parent_groups": sorted(train_groups), "dev_parent_groups": sorted(dev_groups),
        "source_sha256": _spi_sources(), "source_archive": source_archive,
        "chain_plans": chains, "variants": list(ranker.VARIANTS), "test_opened": False,
        "random_seed_replicas": 0, "native_runs_requested": 0}
    return _write_new(directory/"manifest.json", manifest)


def run_spi_chain(reference):
    """Execute only explicit registrations; failed solves are never silently retried."""
    from . import foundation_airport_spi as spi
    plan = read_bound(reference)
    require(plan["schema"] == SPI_CAMPAIGN_SCHEMA+".chain"
        and plan["source_sha256"] == _spi_sources() and plan["test_opened"] is False,
        "bound_spi_chain_sources")
    directory = Path(plan["output"])
    require(not (directory/"fit_events.jsonl").exists() and not (directory/"receipt.json").exists(),
        "spi_no_unregistered_retry")
    train = _load_spi_inputs(plan["train_inputs"], split="train")
    dev = _load_spi_inputs(plan["dev_inputs"], split="dev")
    require(digest(train) == plan["training_dataset_sha256"]
        and digest(dev) == plan["development_dataset_sha256"], "spi_dataset_content_freeze")
    reference_model = spi.make_reference_champion(information_variant=plan["information_variant"],
        contract=plan["contract"], model_available_at_epoch_seconds=plan["model_available_at_epoch_seconds"],
        champion_selection_available_at_epoch_seconds=plan["champion_selection_available_at_epoch_seconds"])
    models = [reference_model]
    model_refs = [ranker.save_model(directory/"reference_model.json", reference_model)]
    deadline = time.monotonic()+plan["wall_seconds_limit"]
    started, completed, errors = 0, 0, []
    for index, registration in enumerate(plan["registrations"]):
        started += 1
        _event(directory/"fit_events.jsonl", {"event": "fit_started", "registration": registration})
        try:
            model = spi.fit_difference_ranker(train, registration=registration, deadline=deadline)
            model_ref = ranker.save_model(directory/f"solver_{index}_model.json", model)
            models.append(model)
            model_refs.append(model_ref)
            completed += 1
            _event(directory/"fit_events.jsonl", {"event": "fit_completed", "model": model_ref})
        except Exception as exc:
            errors.append({"registration_id": registration["registration_id"], "error": repr(exc)})
            _event(directory/"fit_events.jsonl", {"event": "fit_failed", "error": repr(exc)})
            break
    # A failed registered chain cannot promote a partially attempted search.
    selection = spi.select_spi_on_dev([reference_model] if errors else models, dev)
    selection["registered_fit_failures"] = errors
    selection_ref = _write_new(directory/"selection.json", selection)
    selected_ref = next(r for r in model_refs if r["model_id"] == selection["selected_model_id"])
    receipt = {"schema": SPI_CAMPAIGN_SCHEMA+".receipt", "status": "closed",
        "chain_plan": reference, "model_candidates": model_refs, "selection": selection_ref,
        "selected_model": selected_ref, "reference_champion": selection["reference_champion"],
        "fit_calls_started": started, "fit_calls_completed": completed, "fit_failures": errors,
        "test_opened": False, "native_runs_started": 0}
    return _write_new(directory/"receipt.json", receipt)


def freeze_spi(campaign_reference, *, output):
    campaign = read_bound(campaign_reference)
    require(campaign["schema"] == SPI_CAMPAIGN_SCHEMA
        and campaign["source_sha256"] == _spi_sources(), "spi_campaign_source_freeze")
    models, started, completed = [], 0, 0
    for chain_ref in campaign["chain_plans"]:
        plan = read_bound(chain_ref)
        receipt_ref = file_ref(Path(plan["output"])/"receipt.json")
        receipt = read_bound(receipt_ref)
        require(receipt["status"] == "closed" and receipt["chain_plan"] == chain_ref, "closed_spi_chain")
        selection = read_bound(receipt["selection"])
        model = read_bound(receipt["selected_model"])
        require(selection["selected_model_id"] == model["model_id"], "spi_selected_model_binding")
        models.append({"information_variant": plan["information_variant"],
            "checkpoint": receipt["selected_model"], "model_id": model["model_id"],
            "reference_champion": model["reference_champion"], "chain_receipt": receipt_ref,
            "selection": receipt["selection"]})
        started += receipt["fit_calls_started"]
        completed += receipt["fit_calls_completed"]
    require({m["information_variant"] for m in models} == set(ranker.VARIANTS)
        and len(models) == 2, "spi_two_independently_selected_variants")
    return _write_new(output, {"schema": SPI_CAMPAIGN_SCHEMA+".freeze",
        "status": "all_requested_champions_frozen_before_test", "campaign": campaign_reference,
        "models": models, "source_sha256": campaign["source_sha256"],
        "fit_calls_started": started, "fit_calls_completed": completed,
        "contract": campaign["contract"], "test_opened": False,
        "frozen_epoch_seconds": time.time(), "protected_takeover_eligible": False})


def validate_spi_freeze(reference, *, validate_runtime_sources=True):
    from . import foundation_airport_spi as spi
    frozen = read_bound(reference)
    require(frozen["schema"] == SPI_CAMPAIGN_SCHEMA+".freeze"
        and frozen["status"] == "all_requested_champions_frozen_before_test"
        and frozen["test_opened"] is False, "spi_pretest_champions_required")
    campaign = read_bound(frozen["campaign"])
    require(campaign["contract"] == frozen["contract"]
        and campaign["source_sha256"] == frozen["source_sha256"], "spi_frozen_campaign_binding")
    for logical, expected in frozen["source_sha256"].items():
        archive = campaign["source_archive"][logical]
        require(archive["sha256"] == expected
            and archive["archive"]["sha256"] == expected
            and hashlib.sha256(Path(archive["archive"]["path"]).read_bytes()).hexdigest() == expected,
            "spi_archived_training_source_bytes")
    if validate_runtime_sources:
        require(frozen["source_sha256"] == _spi_sources(), "spi_current_source_freeze")
    require({m["information_variant"] for m in frozen["models"]} == set(ranker.VARIANTS)
        and len(frozen["models"]) == 2, "spi_complete_two_variant_freeze")
    started, completed = 0, 0
    registered_plans = {(r["path"], r["sha256"]) for r in campaign["chain_plans"]}
    for row in frozen["models"]:
        model = read_bound(row["checkpoint"])
        receipt, selection = read_bound(row["chain_receipt"]), read_bound(row["selection"])
        require((receipt["chain_plan"]["path"], receipt["chain_plan"]["sha256"]) in registered_plans,
            "spi_chain_in_registered_campaign")
        plan = read_bound(receipt["chain_plan"])
        require(model["model_id"] == row["model_id"] == digest({k: v for k, v in model.items() if k != "model_id"})
            and model["information_variant"] == row["information_variant"]
            and selection["selected_model_id"] == row["model_id"]
            and receipt["selected_model"] == row["checkpoint"]
            and model["schema"] == spi.SCHEMA
            and model["contract"] == frozen["contract"]
            and plan["information_variant"] == row["information_variant"]
            and receipt["selection"] == row["selection"]
            and receipt["status"] == "closed"
            and selection["test_used_for_selection"] is False
            and selection["frozen_before_test"] is True
            and selection["reference_champion"] == row["reference_champion"] == model["reference_champion"],
            "spi_weights_selection_receipt_binding")
        require(receipt["fit_calls_started"] <= plan["fit_calls_planned"]
            and receipt["fit_calls_completed"] <= receipt["fit_calls_started"], "spi_finite_registered_fit_counts")
        started += receipt["fit_calls_started"]
        completed += receipt["fit_calls_completed"]
    require(started == frozen["fit_calls_started"] and completed == frozen["fit_calls_completed"],
        "spi_frozen_fit_denominators")
    return frozen
