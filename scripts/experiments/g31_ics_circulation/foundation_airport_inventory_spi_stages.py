"""Offline stage orchestration for the fixed inventory/SPI campaign.

Preparing or collecting a batch never starts native execution. Training is an
explicit opt-in call; second-round data cannot enter that call. Native execution
remains exclusively in the separately budgeted campaign runner.
"""
from __future__ import annotations

from collections import Counter
import copy
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path

from . import foundation_airport_inventory_spi_campaign as runner
from . import foundation_airport_pair_dataset as pairs
from . import foundation_airport_pair_training_campaign as training
from . import foundation_airport_spi as spi
from . import foundation_airport_spi_parents as parents
from . import foundation_airport_spi_rule_selection as rules
from .foundation_airport_batch_patch import digest

SCHEMA = "g31.inventory_spi_offline_stages.v1"
WINDOWS = ((7200., 9000.), (18000., 23400.), (30000., 35400.), (45000., 50400.))
TRAIN = tuple(range(1101, 1109))
DEV = tuple(range(1201, 1205))
TEST = tuple(range(1301, 1309))
WEIGHTS_AVAILABLE = datetime.fromisoformat("2026-09-28T23:59:59+08:00").timestamp()


def require(ok, reason):
    if not ok:
        raise ValueError("inventory_spi_stages:" + reason)


def read_bound(reference):
    path = Path(reference["path"])
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == reference["sha256"], "bound_artifact_changed")
    return json.loads(gzip.decompress(raw) if path.suffix == ".gz" else raw)


def write_new(path, value):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, indent=2, allow_nan=False).encode()
    if path.suffix == ".gz":
        raw = gzip.compress(raw, compresslevel=1, mtime=0)
    with path.open("xb") as stream:
        stream.write(raw)
    return runner.bound(path)


def _implementation():
    return runner.bound(__file__)


def registered_pair_slots(rollout_round):
    """The split-local rotation is independent of all outcome data."""
    require(type(rollout_round) is int and rollout_round in (0, 1), "registered_round")
    slots = []
    for split, seeds in (("train", TRAIN), ("dev", DEV)):
        for index, seed in enumerate(seeds):
            for slot in range(2 if rollout_round == 0 else 1):
                window_index = ((index + 2 * slot) % 4 if rollout_round == 0
                                else (index + 1) % 4)
                rank = 1 + ((2 * index + slot) % 10 if rollout_round == 0
                            else (3 * index + 2) % 10)
                slots.append({"pair_slot_id": f"r{rollout_round}:P{seed}:root{slot}",
                    "parent_seed": seed, "split": split, "root_slot": slot,
                    "window": list(WINDOWS[window_index]), "patch_rank": rank,
                    "anchor_rank": 0})
    return slots


def _shared(shared):
    required = {"binary", "source_bundle", "native_acceptance", "preregistration"}
    require(required <= shared.keys(), "all_shared_bound_dependencies")
    require(set(shared) <= required | {"global_event_budget", "calibration", "soft_seconds", "hard_seconds"},
        "no_unregistered_shared_override")
    value = copy.deepcopy(shared)
    value["binary"] = str(Path(value["binary"]).resolve())
    for key in ("source_bundle", "native_acceptance", "preregistration"):
        read_bound(value[key])
    registration = read_bound(value["preregistration"])
    require(registration.get("schema") == runner.SCHEMA + ".registration",
        "bound_experiment_registration")
    registry = read_bound(registration["parent_registry"])
    contract = read_bound(registration["learning_contract"])
    require(contract == spi.make_spi_contract(allowed_domains=[copy.deepcopy(parents.DOMAIN)],
        behavior_policy_id=runner.PI0, continuation_policy_id=runner.PI0),
        "registered_learning_configuration")
    document = registration["contract_document"]
    require(runner.bound(document["path"]) == document, "bound_preregistration_document")
    read_bound(registration["budget"])
    runtime = read_bound(registration["runtime_shared"])
    require(all(value.get(key) == runtime.get(key) for key in
        ("binary", "source_bundle", "native_acceptance", "soft_seconds", "hard_seconds", "calibration")),
        "registered_shared_runtime")
    require(registry.get("schema") == "g31.spi_parent_registration.v1"
        and registry.get("domain") == parents.DOMAIN
        and registry.get("splits") == {str(seed): split for seed, split in parents.SPLITS.items()},
        "fixed_parent_preregistration")
    value.setdefault("global_event_budget", 750000)
    value.setdefault("calibration", None)
    if value["calibration"]:
        read_bound(value["calibration"])
    return value


def _kwargs(shared):
    return {key: shared[key] for key in ("binary", "source_bundle", "native_acceptance",
        "global_event_budget", "calibration", "soft_seconds", "hard_seconds") if key in shared}


def _round_behavior(rollout_round, spi_freeze):
    if rollout_round == 0:
        require(spi_freeze is None, "round0_fixed_pi0_not_learned_behavior")
        return None, runner.PI0, False
    require(spi_freeze is not None, "round1_requires_frozen_first_C01_champion")
    frozen = training.validate_spi_freeze(spi_freeze)
    require(frozen["contract"]["policy_alignment"] == _alignment(0, runner.PI0),
        "round1_behavior_is_first_improvement_only")
    selected = next(row for row in frozen["models"] if row["information_variant"] == "C01")
    model = read_bound(selected["checkpoint"])
    identity = runner.PI0 if model["reference_champion"] else model["model_id"]
    return selected["checkpoint"], identity, not model["reference_champion"]


def _alignment(rollout_round, policy_id):
    return {"behavior_policy_id": policy_id, "continuation_policy_id": policy_id,
        "improvement_round": rollout_round, "max_policy_replacements": 1,
        "label_horizon_seconds": 1800.}


def prepare_pair_batch(*, shared, rollout_round, output, spi_freeze=None, name_prefix=None):
    """Prepare exactly 48 or 24 plans; return their bound root manifest.

    Invoke runner.execute(plan_directories(manifest_ref), concurrency=2) separately
    only after the campaign's global budget/admission checks are approved.
    """
    slots = registered_pair_slots(rollout_round)
    shared = _shared(shared)
    behavior, identity, nontrivial = _round_behavior(rollout_round, spi_freeze)
    alignment = _alignment(rollout_round, identity)
    batch = f"pi{rollout_round}_train_dev_pairs"
    output = Path(output).resolve()
    require(not output.exists(), "new_pair_batch_manifest")
    prefix = name_prefix or f"SPI_R{rollout_round}"
    require(prefix and all(c.isalnum() or c in "_-" for c in prefix), "simple_run_name_prefix")
    entries = []
    for slot in slots:
        entry = copy.deepcopy(slot)
        entry["plans"] = {}
        for branch in ("a_ref", "a_patch"):
            spec = {key: copy.deepcopy(slot[key]) for key in ("window", "patch_rank", "anchor_rank")}
            spec.update(branch=branch, policy_alignment=copy.deepcopy(alignment))
            name = f"{prefix}_P{slot['parent_seed']}_root{slot['root_slot']}_{branch}_001"
            directory = runner.prepare(name, seed=slot["parent_seed"], method="C00",
                batch=batch, recovery=True, rollout_round=rollout_round, pair=spec,
                behavior_model=behavior, **_kwargs(shared))
            plan_ref = runner.bound(Path(directory) / "plan.json")
            plan = read_bound(plan_ref)
            entry["plans"][branch] = plan_ref
            if "parent" in entry:
                require(entry["parent"] == plan["parent"], "same_pair_parent_before_run")
            entry["parent"] = plan["parent"]
        entries.append(entry)
    manifest = {"schema": SCHEMA + ".pair_batch", "status": "prepared_not_launched",
        "batch": batch, "rollout_round": rollout_round, "shared": shared,
        "spi_freeze": spi_freeze, "behavior_model": behavior, "policy_alignment": alignment,
        "nontrivial_policy_improvement": nontrivial,
        "registered_pairs": len(entries), "registered_arms": 2 * len(entries),
        "slots": entries, "native_runs_started_by_preparation": 0, "fit_calls_started": 0,
        "test_opened": False, "second_round_training_authorized": False,
        "same_physical_parents_replayed_later_not_new_independent_days": rollout_round == 1,
        "implementation": _implementation()}
    return write_new(output, manifest)


def _validate_pair_manifest(reference):
    manifest = read_bound(reference)
    require(manifest.get("schema") == SCHEMA + ".pair_batch", "pair_manifest_schema")
    round_ = manifest["rollout_round"]
    expected = registered_pair_slots(round_)
    require(manifest["batch"] == f"pi{round_}_train_dev_pairs"
        and manifest["registered_pairs"] == len(expected)
        and manifest["registered_arms"] == 2 * len(expected)
        and len(manifest["slots"]) == len(expected), "complete_registered_pair_roster")
    all_paths = []
    for slot, fixed in zip(manifest["slots"], expected, strict=True):
        require(all(slot[key] == value for key, value in fixed.items()), "preregistered_root_rotation")
        require(slot["parent"]["parent_seed"] == slot["parent_seed"]
            and slot["parent"]["split"] == slot["split"]
            and slot["parent"]["rollout_round"] == round_
            and slot["parent"]["spi_domain"] == parents.DOMAIN, "complete_parent_contract")
        require(set(slot["plans"]) == {"a_ref", "a_patch"}, "two_registered_actual_arms")
        for branch, plan_ref in slot["plans"].items():
            plan = read_bound(plan_ref)
            require(plan["parent"] == slot["parent"] and plan["batch"] == manifest["batch"]
                and plan["pair"]["branch"] == branch
                and plan["pair"]["policy_alignment"] == manifest["policy_alignment"]
                and plan["pair"]["window"] == slot["window"]
                and plan["pair"]["patch_rank"] == slot["patch_rank"]
                and plan["pair"]["anchor_rank"] == slot["anchor_rank"]
                and plan["behavior_model"] == manifest["behavior_model"],
                "actual_plan_bound_to_registered_slot")
            require(all(plan[key] == manifest["shared"][key] for key in
                ("source_bundle", "native_acceptance", "global_event_budget")),
                "same_shared_source_native_event_contract")
            require(all(plan.get("event_calibration" if key == "calibration" else key)
                == manifest["shared"][key] for key in ("soft_seconds", "hard_seconds", "calibration")
                if manifest["shared"].get(key) is not None),
                "same_registered_administrative_limits")
            all_paths.append(str(Path(plan_ref["path"]).resolve()))
    require(len(set(all_paths)) == len(all_paths), "distinct_registered_arm_plans")
    return manifest


def plan_directories(manifest_reference):
    """Return paths only; this helper cannot launch native execution."""
    manifest = _validate_pair_manifest(manifest_reference)
    return [str(Path(slot["plans"][branch]["path"]).parent)
        for slot in manifest["slots"] for branch in ("a_ref", "a_patch")]


def _closed_attempts(manifest):
    records = {}
    for slot in manifest["slots"]:
        for branch, plan_ref in slot["plans"].items():
            path = Path(plan_ref["path"]).parent / "receipt.json"
            require(path.exists(), "all_registered_attempts_must_close_before_collection")
            reference = runner.bound(path)
            receipt = read_bound(reference)
            require(receipt.get("plan_sha256") == plan_ref["sha256"]
                and isinstance(receipt.get("process"), dict)
                and isinstance(receipt.get("status"), str)
                and receipt["status"] not in ("running", "prepared", "pending"),
                "closed_parent_process_receipt_bound_to_plan")
            records[(slot["pair_slot_id"], branch)] = (reference, receipt)
    return records


def _unavailable(slot, manifest, reason, details):
    return {"schema": pairs.SCHEMA,
        "pair": {"schema": pairs.SCHEMA, "parent": copy.deepcopy(slot["parent"]),
            "pair_slot_id": slot["pair_slot_id"], "status": "unavailable_actual_pair",
            "policy_alignment": copy.deepcopy(manifest["policy_alignment"]),
            "advantage_bag_seconds": None, "strict_nonharm_certified": False,
            "rl_benefit_demonstrated": False, "reason": reason},
        "rows": [], "failed_pair_retained": True, "omission_reason": reason,
        "collection_failure_details": details}


def collect_pair_batch(manifest_reference, *, output):
    """Collect only closed attempts; missing or invalid branches stay unavailable."""
    manifest = _validate_pair_manifest(manifest_reference)
    attempts = _closed_attempts(manifest)  # Check all receipts before opening any outcome.
    output = Path(output).resolve()
    require(not output.exists(), "new_collection_output")
    datasets_directory = output.parent / (output.stem + "_datasets")
    require(not datasets_directory.exists(), "new_collection_datasets_directory")
    datasets_directory.mkdir(parents=True)
    inputs, statuses, arm_statuses = [], Counter(), Counter()
    for slot in manifest["slots"]:
        evidence, refs, errors = {}, {}, []
        receipts = {}
        for branch, plan_ref in slot["plans"].items():
            receipt_ref, receipt = attempts[(slot["pair_slot_id"], branch)]
            plan = read_bound(plan_ref)
            receipts[branch] = receipt_ref
            arm_statuses[receipt["status"]] += 1
            path = Path(plan_ref["path"]).parent / "branch_evidence.json.gz"
            if path.exists():
                refs[branch] = runner.bound(path)
                try:
                    value = read_bound(refs[branch])
                    require(value["parent"] == slot["parent"] and value["branch"] == branch
                        and value.get("policy_alignment") == manifest["policy_alignment"]
                        and value["input_sha256"] == plan["input_semantic_sha256"]
                        and value["continuation_version"] == manifest["policy_alignment"]["continuation_policy_id"],
                        "branch_actual_parent_and_policy")
                    require(receipt["status"] in ("complete", "no_eligible_opportunity"),
                        "failed_attempt_not_eligible_for_closed_labels")
                    evidence[branch] = value
                except (ValueError, KeyError, TypeError) as exc:
                    errors.append({"branch": branch, "reason": str(exc)})
            else:
                errors.append({"branch": branch, "reason": "missing_branch_evidence",
                               "attempt_status": receipt["status"]})
        if errors:
            data = _unavailable(slot, manifest, "missing_or_invalid_closed_branch_evidence", errors)
        else:
            try:
                data = pairs.dataset_rows(evidence["a_ref"], evidence["a_patch"])
            except (ValueError, KeyError, TypeError, StopIteration) as exc:
                data = _unavailable(slot, manifest, "paired_prefix_or_label_validation_failed",
                    [{"reason": str(exc)}])
        data["collection_provenance"] = {"pair_slot_id": slot["pair_slot_id"],
            "batch_manifest": manifest_reference, "plans": slot["plans"],
            "attempt_receipts": receipts, "branch_evidence": refs}
        ref = write_new(datasets_directory / (slot["pair_slot_id"].replace(":", "_") + ".json.gz"), data)
        statuses[data["pair"]["status"]] += 1
        inputs.append({"pair_slot_id": slot["pair_slot_id"], "parent": slot["parent"],
            "dataset": ref, "reference_plan": slot["plans"]["a_ref"],
            "patched_plan": slot["plans"]["a_patch"]})
    result = {"schema": SCHEMA + ".collection", "status": "all_registered_attempts_collected",
        "batch": manifest["batch"], "rollout_round": manifest["rollout_round"],
        "batch_manifest": manifest_reference, "shared": manifest["shared"],
        "spi_freeze": manifest["spi_freeze"], "behavior_model": manifest["behavior_model"],
        "policy_alignment": manifest["policy_alignment"],
        "nontrivial_policy_improvement": manifest["nontrivial_policy_improvement"],
        "registered_pairs": manifest["registered_pairs"], "registered_arms": manifest["registered_arms"],
        "closed_attempt_receipts": len(attempts), "pair_status_counts": dict(statuses),
        "attempt_status_counts": dict(arm_statuses), "inputs": inputs,
        "train_inputs": [row for row in inputs if row["parent"]["split"] == "train"],
        "dev_inputs": [row for row in inputs if row["parent"]["split"] == "dev"],
        "unavailable_pairs_excluded": 0, "test_opened": False,
        "second_round_training_authorized": False, "native_runs_started": 0,
        "fit_calls_started": 0, "implementation": _implementation()}
    return write_new(output, result)


def validate_collection(reference, *, rollout_round):
    value = read_bound(reference)
    count = 24 if rollout_round == 0 else 12
    require(value.get("schema") == SCHEMA + ".collection"
        and value["batch"] == f"pi{rollout_round}_train_dev_pairs"
        and value["rollout_round"] == rollout_round
        and value["registered_pairs"] == count and value["registered_arms"] == count * 2
        and value["closed_attempt_receipts"] == count * 2 and len(value["inputs"]) == count
        and value["test_opened"] is False, "all_registered_pairs_and_attempts_collected")
    manifest = _validate_pair_manifest(value["batch_manifest"])
    require(value["shared"] == manifest["shared"]
        and value["policy_alignment"] == manifest["policy_alignment"]
        and value["behavior_model"] == manifest["behavior_model"]
        and value["spi_freeze"] == manifest["spi_freeze"], "collection_manifest_binding")
    _closed_attempts(manifest)
    for item, slot in zip(value["inputs"], manifest["slots"], strict=True):
        require(item["parent"] == slot["parent"] and item["pair_slot_id"] == slot["pair_slot_id"]
            and item["reference_plan"] == slot["plans"]["a_ref"]
            and item["patched_plan"] == slot["plans"]["a_patch"], "collection_slot_identity")
        data = read_bound(item["dataset"])
        provenance = data["collection_provenance"]
        require(data["pair"]["parent"] == item["parent"]
            and data["pair"].get("policy_alignment") == value["policy_alignment"]
            and provenance["batch_manifest"] == value["batch_manifest"]
            and provenance["plans"] == slot["plans"], "dataset_collection_parent_policy_binding")
        for receipt in provenance["attempt_receipts"].values():
            read_bound(receipt)
    require(value["train_inputs"] == [r for r in value["inputs"] if r["parent"]["split"] == "train"]
        and value["dev_inputs"] == [r for r in value["inputs"] if r["parent"]["split"] == "dev"],
        "no_dropped_or_reassigned_training_inputs")
    return value


def train_and_freeze(collection_reference, *, output, execute=False, event_sink=None):
    """Register first-round training; only execute=True runs registered fits.

    Calling this for a second-round collection is always rejected. A default call
    prepares the campaign only, so offline orchestration review does not fit.
    """
    collection = validate_collection(collection_reference, rollout_round=0)
    require(collection["policy_alignment"] == _alignment(0, runner.PI0),
        "first_round_pi0_labels_only")
    directory = Path(output).resolve()
    require(not directory.exists(), "fresh_training_stage_directory")
    directory.mkdir(parents=True)
    closed = {split: sum(read_bound(item["dataset"])["pair"]["status"] == "closed_actual_pair"
        for item in collection[split + "_inputs"]) for split in ("train", "dev")}
    if not all(closed.values()):
        return write_new(directory / "insufficient.json", {
            "schema": SCHEMA + ".training_unavailable",
            "status": "insufficient_unavailable_closed_train_or_dev_labels",
            "collection": collection_reference, "closed_actual_pairs_by_split": closed,
            "registered_pairs": collection["registered_pairs"],
            "closed_attempt_receipts": collection["closed_attempt_receipts"],
            "pair_status_counts": collection["pair_status_counts"],
            "fit_calls_started": 0, "test_opened": False, "formal_unlock_authorized": False,
            "reason": "No fabricated targets or reference-only model freeze. Root must resolve the registered reference-only branch explicitly.",
            "implementation": _implementation()})
    contract = spi.make_spi_contract(allowed_domains=[copy.deepcopy(parents.DOMAIN)],
        behavior_policy_id=runner.PI0, continuation_policy_id=runner.PI0)
    campaign = training.prepare_spi_manifest(output=directory / "learning",
        train_inputs=collection["train_inputs"], dev_inputs=collection["dev_inputs"],
        contract=contract, model_available_at_epoch_seconds=WEIGHTS_AVAILABLE)
    stage = {"schema": SCHEMA + ".training", "status": "registered_not_run",
        "collection": collection_reference, "campaign": campaign, "execute_requested": bool(execute),
        "model_available_at_epoch_seconds": WEIGHTS_AVAILABLE,
        "test_opened": False, "second_round_fit_authorized": False,
        "implementation": _implementation()}
    registration = write_new(directory / "registration.json", stage)
    if not execute:
        return registration
    return execute_training_registration(registration, event_sink=event_sink)


def execute_training_registration(reference, *, event_sink=None):
    """Explicit fit boundary, suitable for a separately authorized finite call."""
    stage = read_bound(reference)
    require(stage.get("schema") == SCHEMA + ".training"
        and stage["status"] == "registered_not_run", "explicit_training_registration")
    collection = validate_collection(stage["collection"], rollout_round=0)
    campaign = training.read_bound(stage["campaign"])
    require(campaign["train_inputs"] == collection["train_inputs"]
        and campaign["dev_inputs"] == collection["dev_inputs"], "registered_training_collection")
    directory = Path(reference["path"]).parent
    from .foundation_airport_training_execution import run_spi
    frozen = run_spi(stage["campaign"], output=directory / "spi_freeze.json", event_sink=event_sink)
    rule = rules.select_and_freeze(collection["dev_inputs"], output=directory / "C10_rule_selection.json")
    return write_new(directory / "frozen.json", {"schema": SCHEMA + ".training_frozen",
        "status": "first_round_learning_and_rule_champions_frozen",
        "registration": reference, "spi_freeze": frozen, "rule": rule,
        "test_opened": False, "second_round_fit_calls": 0, "implementation": _implementation()})


def prepare_formal(*, shared, spi_freeze, rule, round1_collection, output, name_prefix="SPI_TEST"):
    """Bind every freeze before generating test inputs; prepare all 40 plans."""
    shared = _shared(shared)
    frozen = training.validate_spi_freeze(spi_freeze)
    rules.validate_rule_selection(rule)
    collection = validate_collection(round1_collection, rollout_round=1)
    require(collection["shared"] == shared and collection["spi_freeze"] == spi_freeze,
        "round1_used_same_frozen_source_and_first_champions")
    require(frozen["contract"]["policy_alignment"] == _alignment(0, runner.PI0),
        "formal_deploys_first_round_once_only_champions")
    directory = Path(output).resolve().parent
    output = Path(output).resolve()
    require(not output.exists(), "fresh_formal_manifest")
    models = {row["information_variant"]: row["checkpoint"] for row in frozen["models"]}
    require(collection["behavior_model"] == models["C01"], "round1_collected_first_C01_only")
    unlock = {"schema": runner.SCHEMA + ".formal_unlock",
        "status": "all_champions_frozen_test_unlocked", "test_parent_ids": list(TEST),
        "spi_freeze": spi_freeze, "rule": rule, "source_bundle": shared["source_bundle"],
        "native_acceptance": shared["native_acceptance"], "preregistration": shared["preregistration"],
        "round1_collection": round1_collection, "models": models,
        "test_outcomes_used_for_selection": False, "implementation": _implementation()}
    unlock_ref = write_new(directory / (output.stem + "_unlock.json"), unlock)
    runner.validate_formal_unlock(unlock_ref)  # Before any test parent materialization.
    entries = []
    for seed in TEST:
        for method in runner.METHODS:
            directory = runner.prepare(f"{name_prefix}_{method}_P{seed}_001",
                seed=seed, method=method, batch="formal_8_parents_5_methods",
                model=models.get(method), rule=rule if method == "C10" else None,
                unlock=unlock_ref, recovery=True, **_kwargs(shared))
            entries.append({"parent_seed": seed, "method": method,
                "plan": runner.bound(Path(directory) / "plan.json")})
    return write_new(output, {"schema": SCHEMA + ".formal_batch", "status": "prepared_not_launched",
        "formal_unlock": unlock_ref, "shared": shared, "registered_parents": 8,
        "registered_arms": 40, "plans": entries, "native_runs_started": 0,
        "test_inputs_generated_after_champion_freeze": True,
        "test_outcomes_opened": False, "implementation": _implementation()})
