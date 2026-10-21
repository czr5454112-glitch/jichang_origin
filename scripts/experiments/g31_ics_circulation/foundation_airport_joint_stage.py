"""Recoverable joint experiment DAG through development audit, never test unlock.

No work runs on import. Build commands only freeze plans; run/advance explicitly
invoke the existing single-worker campaign launcher. Every fit is registered
before execution and charged inside the same durable active-time ledger.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime
import gzip
import inspect
import json
import math
from pathlib import Path
import secrets
import time
import traceback

from . import foundation_airport_joint_budget as budget
from . import foundation_airport_joint_campaign as campaign
from . import foundation_airport_joint_dataset as dataset
from . import foundation_airport_joint_learning as learning
from .foundation_airport_inventory_spi_campaign import bound, read_bound

SCHEMA = "g31.foundation.airport_joint_stage.v1"
BRIDGE_METHODS = ("R0_legacy", "R0_joint_bridge", "C00", "R_forecast_prior", "C10")
TRAIN_PARENTS, DEV_PARENTS = tuple(range(2101, 2109)), tuple(range(2201, 2205))
RECOLLECT_PARENTS = (2101, 2102)
MODELS = tuple((variant, seed) for variant in ("C01", "C11") for seed in (17, 29, 43))
MODEL_AVAILABLE = {0: datetime.fromisoformat("2026-11-10T00:00:00+08:00").timestamp(),
                   1: datetime.fromisoformat("2026-12-01T00:00:00+08:00").timestamp()}
STAGES = ("bridge", "initial", "recollect", "development")
_ACTIVE_RUNNER = None
require, digest = dataset.require, dataset.digest


def read(path):
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    return json.loads(path.read_text(encoding="utf-8"))


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        require(read(path) == value, "immutable_stage_artifact_conflict:"+str(path))
        return bound(path)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return bound(path)


def _root(config):
    require(Path(config["cycle"]).resolve() == campaign.CYCLE.resolve(), "stage_campaign_cycle_binding")
    return Path(config["cycle"]) / "stage"


def validate_gate(gate):
    require(gate.get("approved_for_joint_stage") is True and gate.get("status") == "passed",
            "explicit_passed_native_gate_admission")
    require(gate.get("test_unlocked", False) is False, "development_only_stage")
    receipts = gate.get("native_gate_receipts")
    require(type(receipts) is list and receipts, "actual_native_gate_receipts_required")
    for reference in receipts:
        receipt = read_bound(reference)
        require(receipt.get("worker", {}).get("scientific_status") == "closed"
                and receipt.get("process", {}).get("exitcode") == 0, "closed_native_gate_evidence")


def initialize(*, source_bundle, mapping, gate_receipt, calibration, fit_wall_seconds=900.):
    """Freeze explicit dependencies; no gate is inferred from pytest or a label."""
    source, mapped, gate, calibrated = [read_bound(item) for item in
                                       (source_bundle, mapping, gate_receipt, calibration)]
    validate_gate(gate)
    from .foundation_airport_loader_mapping import validate_mapping
    validate_mapping(mapped)
    for key in ("horizon", "soft_seconds", "hard_seconds", "estimated_evidence_bytes"):
        require(key in calibrated, "explicit_calibration_"+key)
    require(7200. < calibrated["horizon"] <= 59400.
            and 0 < calibrated["soft_seconds"] < calibrated["hard_seconds"]
            and type(calibrated["estimated_evidence_bytes"]) is int
            and calibrated["estimated_evidence_bytes"] > 0, "measured_finite_native_calibration")
    require(calibrated.get("before_training") is True, "calibration_registered_before_training")
    require(0 < fit_wall_seconds <= 3600., "bounded_fit_wall_seconds")
    config = dict(schema=SCHEMA, cycle=str(campaign.CYCLE.resolve()), source_bundle=source_bundle,
        mapping=mapping, gate_receipt=gate_receipt, calibration=calibration,
        native_calibration={key: calibrated[key] for key in
            ("horizon", "soft_seconds", "hard_seconds", "estimated_evidence_bytes")},
        fit_wall_seconds=float(fit_wall_seconds), models=[dict(variant=v, seed=s) for v, s in MODELS],
        initial_fit=dict(method="mc", epochs=100, td_updates=0, hidden_width=64),
        recollection_fit=dict(method="sarsa", epochs=100, td_updates=5, hidden_width=64),
        train_parents=list(TRAIN_PARENTS), dev_parents=list(DEV_PARENTS),
        recollect_parents=list(RECOLLECT_PARENTS), initial_root_branches=[0, 1, 2],
        model_available_at_epoch_seconds={str(k): v for k, v in MODEL_AVAILABLE.items()},
        test_locked=True, final_action="stop_after_development_audit_before_champion_freeze_and_test_unlock",
        behavior_selection="0.8_C00_plus_0.2_uniform_other_common_legal_candidates",
        service_gate="no_known_direction_harm_nonworse_completed_ontime_overdue_no_physical_failure",
        selection_unit="four_full_parent_rollouts_per_fixed_model_seed; reference_allowed",
        source_manifest_sha256=source["source_manifest_sha256"],
        driver_source_sha256=campaign.common.sha(Path(__file__)))
    config["stage_id"] = digest(config)
    write_once(_root(config)/"registration.json", config)
    return config


def load_config(path=None):
    config = read(path or campaign.CYCLE/"stage/registration.json")
    require(config.get("schema") == SCHEMA and config["test_locked"] is True
            and config["stage_id"] == digest({k: v for k, v in config.items() if k != "stage_id"}),
            "frozen_stage_registration")
    _root(config)
    require(config["driver_source_sha256"] == campaign.common.sha(Path(__file__)), "frozen_stage_driver_source")
    for key in ("source_bundle", "mapping", "gate_receipt", "calibration"):
        read_bound(config[key])
    validate_gate(read_bound(config["gate_receipt"]))
    return config


@contextmanager
def active_interval(config, purpose):
    global _ACTIVE_RUNNER
    if _ACTIVE_RUNNER is not None:
        yield
        return
    runner = "stage-"+secrets.token_hex(12)
    budget.append(config["cycle"], "runner_open", runner_id=runner, purpose=purpose,
                  stage_id=config["stage_id"])
    _ACTIVE_RUNNER = runner
    try:
        yield
    finally:
        try:
            budget.append(config["cycle"], "runner_close", runner_id=runner)
        finally:
            _ACTIVE_RUNNER = None


def _task_id(stage, method, parent, *, model_seed=None, branch=None):
    suffix = (f"_S{model_seed}" if model_seed is not None else "")+(f"_B{branch}" if branch is not None else "")
    return f"JOINT_{stage}_{method}_P{parent}{suffix}_001"


def _fit_key(round_index, variant, seed):
    require(round_index in (0, 1) and (variant, seed) in MODELS, "registered_fit_identity")
    return f"round_{round_index}/{variant}_S{seed}"


def _within(path, directory):
    return Path(path).resolve().is_relative_to(Path(directory).resolve())


def _resolution_reference(config, kind, key, original):
    reference = original
    directory = _root(config)/"resolutions"/kind/key
    if directory.exists():
        paths = sorted(directory.glob("resolution_*.json"))
        require([p.name for p in paths] == [f"resolution_{i:03d}.json" for i in range(1, len(paths)+1)],
                "contiguous_append_only_resolution_chain")
        for path in paths:
            row = read(path)
            require(row["resolution_id"] == digest({k: v for k, v in row.items() if k != "resolution_id"})
                    and row["stage_id"] == config["stage_id"] and row["kind"] == kind and row["logical_key"] == key
                    and row["previous"] == reference, "bound_resolution_chain")
            read_bound(row["diagnosis"])
            read_bound(row["failure_evidence"])
            read_bound(row["replacement"])
            reference = row["replacement"]
    return reference


def _native_plan_reference(config, logical_task_id):
    require(Path(logical_task_id).name == logical_task_id, "simple_logical_native_task_id")
    original = bound(Path(config["cycle"])/"runs"/logical_task_id/"plan.json")
    return _resolution_reference(config, "native", logical_task_id, original)


def _native_directory(config, logical_task_id):
    return Path(_native_plan_reference(config, logical_task_id)["path"]).parent


def _fit_directory(config, round_index, variant, seed):
    key = _fit_key(round_index, variant, seed)
    original = _root(config)/"training"/key/"registration.json"
    if not original.exists():
        return original.parent
    return Path(_resolution_reference(config, "fit", key, bound(original))["path"]).parent


def _append_resolution(config, *, kind, key, previous, replacement, failure_evidence, diagnosis):
    explanation = read_bound(diagnosis)
    require(type(explanation) is dict and isinstance(explanation.get("reason"), str)
            and explanation["reason"].strip(), "explicit_resolution_diagnosis_reason")
    directory = _root(config)/"resolutions"/kind/key
    count = len(list(directory.glob("resolution_*.json"))) if directory.exists() else 0
    row = dict(schema=SCHEMA+".resolution", stage_id=config["stage_id"], kind=kind, logical_key=key,
               previous=previous, replacement=replacement, failure_evidence=failure_evidence,
               diagnosis=diagnosis, failed_attempt_preserved=True, native_budget_refunded=False)
    row["resolution_id"] = digest(row)
    path = directory/f"resolution_{count+1:03d}.json"
    write_once(path, row)
    budget.append(config["cycle"], "stage_resolution", resolution=bound(path), kind_resolved=kind,
                  logical_key=key, failed_attempt_preserved=True)
    return row


def _native_failure_evidence(config, directory):
    plan = read(directory/"plan.json")
    if (directory/"receipt.json").exists():
        receipt = read(directory/"receipt.json")
        require(receipt["plan_sha256"] == campaign.common.sha(directory/"plan.json")
                and receipt["task_id"] == plan["task_id"], "failed_native_receipt_plan_binding")
        require(not (receipt["process"].get("exitcode") == 0
            and receipt["worker"].get("process_status") == "completed"
            and receipt["worker"].get("scientific_status") == "closed"), "cannot_replace_closed_native_task")
        return bound(directory/"receipt.json")
    # A hard-killed parent may not have emitted a receipt. Only the budget's
    # explicit dead-process recovery can supply unknown-attempt evidence.
    rows = budget.events(config["cycle"])
    recovered = [r for r in rows if r["event"] == "native_finish" and r.get("task_id") == plan["task_id"]
                 and r.get("recovered") is True and r.get("scientific_status") == "unknown_unclosed_attempt"]
    require(len(recovered) == 1, "missing_receipt_requires_explicit_dead_attempt_recovery")
    path = _root(config)/"recovery_evidence"/(plan["task_id"]+".json")
    write_once(path, dict(schema=SCHEMA+".recovered_unknown_native", plan=bound(directory/"plan.json"),
                         budget_recovery_event=recovered[0], failed_attempt_preserved=True))
    return bound(path)


def resolve_native(config, *, logical_task_id, replacement_plan, diagnosis):
    """Bind an explicit new reserve attempt; never restart/refund the old task."""
    with active_interval(config, "register_native_resolution"):
        previous = _native_plan_reference(config, logical_task_id)
        old, new = read_bound(previous), read_bound(replacement_plan)
        old_dir, new_dir = Path(previous["path"]).parent, Path(replacement_plan["path"]).parent
        require(_within(new_dir, Path(config["cycle"])/"runs") and new_dir != old_dir
                and new_dir.name == new["task_id"], "new_native_attempt_in_registered_cycle")
        require(new["task_id"] != old["task_id"] and new["batch"] == "reserve",
                "replacement_requires_fresh_reserve_native_attempt")
        for key in ("method", "parent", "input", "binary", "source_bundle", "mapping", "model", "root_branch",
                    "behavior_seed", "activation", "horizon", "policy_version", "supply_mode",
                    "projection_horizon_seconds", "transport_penalty", "minimum_gain", "controller",
                    "event_budget", "global_event_budget", "cost_scope"):
            require(new.get(key) == old.get(key), "replacement_preserves_scientific_domain:"+key)
        for key in ("forecast_binding", "arrival_support_contract", "origin_support_audit"):
            require((new.get(key) or {}).get("sha256") == (old.get(key) or {}).get("sha256"),
                    "replacement_preserves_public_information_contract:"+key)
        campaign.verify(new)
        failure = _native_failure_evidence(config, old_dir)
        state = budget.status(config["cycle"])
        require(old["task_id"] not in state["unfinished_native_tasks"],
                "old_native_attempt_requires_explicit_budget_recovery")
        limits = read(Path(config["cycle"])/"campaign_budget.json")
        started = any(row["event"] == "native_start" and row.get("task_id") == new["task_id"]
                      for row in budget.events(config["cycle"]))
        require(started or (state["by_batch"]["reserve"] < limits["allocations"]["reserve"]
                and state["native_starts"] < limits["native_start_limit"]), "reserve_retry_budget_available")
        return _append_resolution(config, kind="native", key=logical_task_id, previous=previous,
                                  replacement=replacement_plan, failure_evidence=failure, diagnosis=diagnosis)


def resolve_fit(config, *, round_index, variant, seed, replacement_registration, diagnosis):
    """Bind a newly preregistered fit attempt with identical scientific inputs."""
    with active_interval(config, "register_fit_resolution"):
        key = _fit_key(round_index, variant, seed)
        old_dir = _fit_directory(config, round_index, variant, seed)
        previous = bound(old_dir/"registration.json")
        old, new = read_bound(previous), read_bound(replacement_registration)
        new_dir = Path(replacement_registration["path"]).parent
        require(_within(new_dir, _root(config)/"training"/key/"attempts") and new_dir != old_dir,
                "new_fit_attempt_under_logical_model")
        require(new["registration_id"] != old["registration_id"] and
                {k: v for k, v in new.items() if k != "registration_id"} ==
                {k: v for k, v in old.items() if k != "registration_id"}, "retry_fit_preserves_inputs_and_budget")
        receipt_path = old_dir/"receipt.json"
        if receipt_path.exists():
            failed_receipt = read(receipt_path)
            require(failed_receipt.get("registration") == previous, "failed_fit_receipt_registration_binding")
            require(failed_receipt["process_status"] != "completed", "cannot_replace_completed_fit")
            failure = bound(receipt_path)
        else:
            ledger = budget.events(config["cycle"])
            starts = [r for r in ledger if r["event"] == "fit_start" and r.get("registration_id") == old["registration_id"]]
            require(len(starts) == 1, "old_interrupted_fit_was_registered")
            start_index = ledger.index(starts[0])
            prior_open = next((r for r in reversed(ledger[:start_index]) if r["event"] == "runner_open"), None)
            require(prior_open is not None and any(r["event"] == "runner_close" and r.get("recovered") is True
                    and r.get("runner_id") == prior_open["runner_id"] for r in ledger[start_index:]),
                    "interrupted_fit_requires_explicit_dead_runner_recovery")
            evidence_path = _root(config)/"recovery_evidence"/(digest(old["registration_id"])+".json")
            write_once(evidence_path, dict(schema=SCHEMA+".recovered_unknown_fit", registration=previous,
                       fit_start=starts[0], recovered_runner_id=prior_open["runner_id"], target_status="unknown"))
            failure = bound(evidence_path)
        return _append_resolution(config, kind="fit", key=key, previous=previous,
                                  replacement=replacement_registration, failure_evidence=failure, diagnosis=diagnosis)


def prepare_fit_retry(config, *, round_index, variant, seed, attempt, diagnosis):
    require(type(attempt) is int and attempt >= 2, "explicit_new_fit_attempt_number")
    key = _fit_key(round_index, variant, seed)
    old = read(_fit_directory(config, round_index, variant, seed)/"registration.json")
    new = dict(old, registration_id=f"{config['stage_id']}:{key}:attempt_{attempt:03d}")
    directory = _root(config)/"training"/key/"attempts"/f"attempt_{attempt:03d}"
    require(not directory.exists(), "fresh_fit_attempt_directory")
    reference = write_once(directory/"registration.json", new)
    return resolve_fit(config, round_index=round_index, variant=variant, seed=seed,
                       replacement_registration=reference, diagnosis=diagnosis)


def recover_dead(config, *, runner_id, task_id, diagnosis):
    explanation = read_bound(diagnosis)
    require(isinstance(explanation.get("reason"), str) and explanation["reason"].strip(),
            "explicit_dead_process_diagnosis")
    reason = explanation["reason"]
    if task_id is not None:
        starts = [row for row in budget.events(config["cycle"]) if row["event"] == "native_start"
                  and row.get("task_id") == task_id]
        require(len(starts) == 1 and starts[0]["runner_id"] == runner_id,
                "dead_attempt_belongs_to_requested_runner")
        budget.recover_attempt(config["cycle"], task_id, reason=reason)
    return budget.recover_runner(config["cycle"], runner_id, reason=reason)


def task_specs(config, stage, model_refs=None):
    """Static small DAG; test parents are absent from this module's rosters."""
    require(stage in STAGES, "registered_pretest_stage")
    common = dict(source_bundle=config["source_bundle"], **config["native_calibration"])
    specs = []
    if stage == "bridge":
        for parent in DEV_PARENTS:
            for method in BRIDGE_METHODS:
                specs.append(dict(common, task_id=_task_id(stage, method, parent), method=method,
                    seed=parent, batch="bridge", mapping=config["mapping"] if method == "C10" else None))
    elif stage == "initial":
        for parent in TRAIN_PARENTS:
            for branch in (0, 1, 2):
                specs.append(dict(common, task_id=_task_id(stage, "explore", parent, branch=branch),
                    method="explore", seed=parent, batch="initial", mapping=config["mapping"], root_branch=branch))
    else:
        require(model_refs is not None and set(model_refs) == {f"{v}_S{s}" for v, s in MODELS},
                "all_six_frozen_model_refs_required")
        parents = RECOLLECT_PARENTS if stage == "recollect" else DEV_PARENTS
        for variant, model_seed in MODELS:
            for parent in parents:
                specs.append(dict(common, task_id=_task_id(stage, variant, parent, model_seed=model_seed),
                    method=variant, seed=parent, batch=stage, model=model_refs[f"{variant}_S{model_seed}"],
                    mapping=config["mapping"] if variant == "C11" else None,
                    rollout_round=1 if stage == "recollect" else 0))
    return specs


def _closed_task(directory):
    """A process exit alone never permits reuse of an unknown scientific result."""
    directory = Path(directory)
    require((directory/"receipt.json").is_file(), "native_task_not_completed:"+directory.name)
    receipt, plan = read(directory/"receipt.json"), read(directory/"plan.json")
    require(receipt["plan_sha256"] == campaign.common.sha(directory/"plan.json")
            and receipt["task_id"] == plan["task_id"], "task_receipt_plan_binding")
    require(receipt["process"].get("exitcode") == 0
            and receipt["worker"].get("process_status") == "completed"
            and receipt["worker"].get("scientific_status") == "closed",
            "failed_or_censored_task_requires_diagnosis_new_attempt_id:"+directory.name)
    trajectory = read(directory/"trajectory.json.gz")
    require(trajectory["scientific_status"] == "closed_finite_horizon"
            and trajectory["manifest"]["trajectory_id"] == plan["task_id"]
            and trajectory["dataset_id"] == digest({k: v for k, v in trajectory.items() if k != "dataset_id"}),
            "closed_trajectory_binding")
    manifest = trajectory["manifest"]
    expected_parent_uid = plan["parent"]["parent_group"].rsplit(":r", 1)[0]
    expected = dict(parent_uid=expected_parent_uid, split=plan["parent"]["split"],
        episode_parent_group=plan["parent"]["parent_group"], rollout_round=plan["parent"]["rollout_round"],
        lineage_family=plan["parent"]["plan_family_id"],
        template_family=plan["parent"]["common_historical_template_sha256"],
        environment_seed=plan["parent"]["parent_seed"], behavior_seed=plan["behavior_seed"],
        execution_source_id=plan["source_bundle"]["sha256"], native_domain_id=plan["binary"]["sha256"],
        joint_policy_version=plan["policy_version"], physical_start=plan["activation"],
        physical_end=plan["horizon"], calendar_start_epoch_seconds=plan["parent"]["calendar_start_epoch_seconds"])
    require(all(manifest.get(key) == value for key, value in expected.items()), "trajectory_full_plan_domain_binding")
    require(trajectory["physical_clock"] >= plan["horizon"]
            and receipt["worker"]["final_physical_time"] == trajectory["physical_clock"]
            and trajectory["population_count"] == plan["parent"]["offered_count"], "trajectory_closed_clock_population_binding")
    return plan, receipt, trajectory


def model_references(config, round_index):
    references = {}
    for variant, seed in MODELS:
        directory = _fit_directory(config, round_index, variant, seed)
        receipt = read(directory/"receipt.json")
        require(receipt["process_status"] == "completed" and receipt["scientific_status"] == "model_frozen",
                "completed_registered_fit_required")
        model = read_bound(receipt["model"])
        registration = read_bound(receipt["registration"])
        require(model["information_variant"] == variant and model["seed"] == seed
                and model["model_id"] == receipt["model_id"] and model["registration"] == registration,
                "model_seed_information_binding")
        references[f"{variant}_S{seed}"] = receipt["model"]
    return references


def _build_stage(config, stage):
    references = model_references(config, 0 if stage == "recollect" else 1) if stage in ("recollect", "development") else None
    specs = task_specs(config, stage, references)
    paths = []
    for spec in specs:
        directory = Path(config["cycle"])/"runs"/spec["task_id"]
        if (directory/"plan.json").is_file():
            existing = read(directory/"plan.json")
            for key in ("method", "batch", "source_bundle", "mapping", "model", "root_branch",
                        "horizon", "soft_seconds", "hard_seconds", "estimated_evidence_bytes"):
                require(existing.get(key) == spec.get(key), "existing_native_plan_conflict:"+key)
            require(existing["parent"]["parent_seed"] == spec["seed"]
                    and existing["parent"]["rollout_round"] == spec.get("rollout_round", 0),
                    "existing_native_parent_conflict")
            require(existing.get("calibration") == config["calibration"], "existing_native_calibration_conflict")
            campaign.verify(existing)
        else:
            parameters = inspect.signature(campaign.prepare).parameters
            require("estimated_evidence_bytes" in parameters, "campaign_measured_evidence_API_required")
            kwargs = dict(spec)
            if "calibration" in parameters:
                kwargs["calibration"] = config["calibration"]
            directory = campaign.prepare(**kwargs)
        paths.append(bound(directory/"plan.json"))
    manifest = dict(schema=SCHEMA+".native_stage", stage_id=config["stage_id"], stage=stage,
                    task_plans=paths, native_tasks=len(paths), test_locked=True)
    write_once(_root(config)/"stages"/(stage+".json"), manifest)
    return manifest


def build_stage(config, stage):
    with active_interval(config, "prepare_native_stage:"+stage):
        return _build_stage(config, stage)


def run_stage(config, stage):
    with active_interval(config, "native_stage:"+stage):
        manifest = build_stage(config, stage)
        results = []
        for plan_ref in manifest["task_plans"]:
            original_plan = read_bound(plan_ref)
            resolved_ref = _native_plan_reference(config, original_plan["task_id"])
            plan = read_bound(resolved_ref)
            directory = Path(resolved_ref["path"]).parent
            if not (directory/"receipt.json").exists():
                campaign.launch(directory)
            _, _, trajectory = _closed_task(directory)
            results.append(dict(task_id=plan["task_id"], logical_task_id=original_plan["task_id"], dataset_id=trajectory["dataset_id"],
                                receipt=bound(directory/"receipt.json"), trajectory=bound(directory/"trajectory.json.gz")))
        write_once(_root(config)/"stages"/(stage+"_complete.json"),
                   dict(schema=SCHEMA+".stage_complete", stage=stage, results=results, test_locked=True))
        return results


def initial_training_data(config):
    """Require measured matched roots; never fabricate pairs from ordinary runs."""
    trajectories, pairs, sources = [], [], []
    for parent in TRAIN_PARENTS:
        arms, roots = [], []
        for branch in (0, 1, 2):
            directory = _native_directory(config, _task_id("initial", "explore", parent, branch=branch))
            _, receipt, trajectory = _closed_task(directory)
            root = receipt["worker"].get("root")
            require(root is not None and not root.get("prefix_pending", True),
                    "opportunity_insufficient_no_measured_matched_root:"+directory.name)
            selected = [row for row in trajectory["rows"] if row["owner_id"] == root["owner_id"]
                        and row["decision_time"] == root["at"]
                        and row["requested_action"]["action_id"] == root["selected_action_id"]]
            require(len(selected) == 1, "unique_actual_matched_root_decision")
            arms.append(trajectory)
            roots.append(selected[0]["decision_id"])
            sources.append(bound(directory/"trajectory.json.gz"))
        require(len({arm["rows"][next(i for i, r in enumerate(arm["rows"]) if r["decision_id"] == identity)]
                     ["requested_action"]["action_id"] for arm, identity in zip(arms, roots, strict=True)}) == 3,
                "three_distinct_actual_root_proposals")
        for index in (1, 2):
            pairs.append(dataset.make_paired_label(arms[0], arms[index], reference_decision_id=roots[0],
                alternative_decision_id=roots[index], pairing=arms[0]["manifest"]["pairing"]))
        trajectories.extend(arms)
    dataset.validate_split_lineage(trajectories)
    index = dict(schema=SCHEMA+".initial_dataset_index", sources=sources,
                 trajectory_ids=[t["dataset_id"] for t in trajectories], actual_pair_ids=[p["pair_id"] for p in pairs],
                 actual_trajectory_count=len(trajectories), actual_pair_count=len(pairs),
                 parent_count=len(TRAIN_PARENTS), independent_real_airport_days=0)
    write_once(_root(config)/"datasets/initial_index.json", index)
    write_once(_root(config)/"datasets/initial_pairs.json", pairs)
    return trajectories, pairs


def recollection_training_data(config, variant, seed):
    trajectories = []
    for parent in RECOLLECT_PARENTS:
        directory = _native_directory(config, _task_id("recollect", variant, parent, model_seed=seed))
        _, _, trajectory = _closed_task(directory)
        trajectories.append(trajectory)
    return trajectories


def _verify_fit_sources(config):
    frozen = read_bound(config["source_bundle"])["files"]
    for name, expected in learning.source_pins().items():
        relative = "scripts/experiments/g31_ics_circulation/"+name
        require(frozen.get(relative) == expected, "fit_sources_match_frozen_native_features:"+name)


def _fit_admission(config, registration_id):
    state, limits = budget.status(config["cycle"]), read(Path(config["cycle"])/"campaign_budget.json")
    require(state["active_seconds"]+config["fit_wall_seconds"] <= limits["active_seconds_limit"],
            "fit_active_time_budget")
    require(state["evidence_bytes"]+50*1024**2 < limits["new_evidence_bytes_limit"]
            and state["free_bytes"]-50*1024**2 >= limits["free_space_floor_bytes"], "fit_disk_budget")
    require(not any(row.get("registration_id") == registration_id and row["event"] == "fit_start"
                    for row in budget.events(config["cycle"])), "no_silent_failed_fit_restart")


def train(config, round_index):
    require(round_index in (0, 1), "two_registered_learning_rounds")
    with active_interval(config, "training_round:"+str(round_index)):
        _verify_fit_sources(config)
        shared_data, shared_pairs = initial_training_data(config) if round_index == 0 else (None, None)
        initial_models = model_references(config, 0) if round_index else {}
        receipts = []
        for variant, seed in MODELS:
            directory = _fit_directory(config, round_index, variant, seed)
            if (directory/"receipt.json").exists():
                receipt = read(directory/"receipt.json")
                require(receipt["process_status"] == "completed", "failed_fit_requires_diagnosis")
                saved_model = read_bound(receipt["model"])
                saved_registration = read_bound(receipt["registration"])
                require(saved_model["registration"] == saved_registration
                        and saved_model["model_id"] == receipt["model_id"], "cached_fit_model_registration_binding")
                registered_id = saved_registration["registration_id"]
                if not any(row["event"] == "fit_finish" and row.get("registration_id") == registered_id
                           for row in budget.events(config["cycle"])):
                    budget.append(config["cycle"], "fit_finish", registration_id=registered_id,
                                  process_status="completed", model_id=saved_model["model_id"],
                                  recovered_from_closed_receipt=True)
                receipts.append(receipt)
                continue
            trajectories = shared_data if round_index == 0 else recollection_training_data(config, variant, seed)
            pairs = shared_pairs if round_index == 0 else []
            versions = {t["manifest"]["joint_policy_version"] for t in trajectories}
            require(len(versions) == 1, "actual_one_joint_policy_per_fit")
            options = config["initial_fit" if round_index == 0 else "recollection_fit"]
            identity = f"{config['stage_id']}:round{round_index}:{variant}:seed{seed}"
            if (directory/"registration.json").exists():
                identity = read(directory/"registration.json")["registration_id"]
            registration = learning.make_registration(trajectories, information_variant=variant, seed=seed,
                registration_id=identity, model_available_at_epoch_seconds=MODEL_AVAILABLE[round_index],
                joint_policy_version=next(iter(versions)), paired_labels=pairs, **options)
            registration_ref = write_once(directory/"registration.json", registration)
            _fit_admission(config, identity)
            budget.append(config["cycle"], "fit_start", registration_id=identity,
                          registration=registration_ref, information_variant=variant, model_seed=seed,
                          round=round_index, max_epochs=options["epochs"], max_td_updates=options["td_updates"])
            began = time.monotonic()
            try:
                model = learning.fit_model(trajectories, registration, paired_labels=pairs,
                                           deadline=began+config["fit_wall_seconds"])
                model_ref = write_once(directory/"model.json", model)
                iteration = None
                if round_index == 1:
                    initial = read_bound(initial_models[f"{variant}_S{seed}"])
                    iteration = learning.policy_iteration_evidence(initial, trajectories, model)
                    write_once(directory/"policy_iteration_evidence.json", iteration)
                receipt = dict(schema=SCHEMA+".fit_receipt", process_status="completed", scientific_status="model_frozen",
                    registration=registration_ref, model=model_ref, model_id=model["model_id"],
                    wall_seconds=time.monotonic()-began, policy_iteration_evidence=iteration,
                    test_data_used=False, native_starts=0)
                write_once(directory/"receipt.json", receipt)
                budget.append(config["cycle"], "fit_finish", registration_id=identity,
                              process_status="completed", model_id=model["model_id"])
                receipts.append(receipt)
            except Exception:
                if (directory/"receipt.json").exists():
                    # A complete model receipt may precede an interrupted ledger
                    # append. Preserve it and reconcile that append on resume.
                    budget.append(config["cycle"], "fit_receipt_postprocessing_error", registration_id=identity,
                                  exception=traceback.format_exc(), completed_receipt_preserved=True)
                    raise
                receipt = dict(schema=SCHEMA+".fit_receipt", process_status="failed", scientific_status="unknown_fit",
                    registration=registration_ref, wall_seconds=time.monotonic()-began, exception=traceback.format_exc(),
                    resume="Diagnose and register an explicit new fit attempt; never overwrite this receipt.")
                write_once(directory/"receipt.json", receipt)
                budget.append(config["cycle"], "fit_finish", registration_id=identity, process_status="failed")
                raise
        write_once(_root(config)/"training"/f"round_{round_index}"/"complete.json",
                   dict(schema=SCHEMA+".training_complete", round=round_index,
                        model_ids=[r["model_id"] for r in receipts], test_locked=True))
        return receipts


def development_audit(config):
    """Strict observed-service gate per seed; leaves test locked for review."""
    from .foundation_airport_service_metrics import compare_completion_outcomes
    candidates = []
    for variant, seed in MODELS:
        rows = []
        reference_method = "C00" if variant == "C01" else "C10"
        for parent in DEV_PARENTS:
            reference_dir = _native_directory(config, _task_id("bridge", reference_method, parent))
            model_dir = _native_directory(config, _task_id("development", variant, parent, model_seed=seed))
            ref_plan, ref_receipt, ref_trajectory = _closed_task(reference_dir)
            model_plan, model_receipt, model_trajectory = _closed_task(model_dir)
            require(ref_plan["input"] == model_plan["input"] and ref_plan["horizon"] == model_plan["horizon"]
                    and ref_plan["source_bundle"] == model_plan["source_bundle"], "development_same_parent_domain")
            old, new = read(reference_dir/"terminal_evidence.json.gz"), read(model_dir/"terminal_evidence.json.gz")
            population = read_bound(ref_plan["input"])["jobs"]
            completed = lambda result: {j["business_bag_id"]: j["completed_at"] for j in result["jobs"] if j["completed_at"] >= 0}
            direction = compare_completion_outcomes(population, completed(old), completed(new),
                                                    cutoff=ref_plan["horizon"], include_rows=False)
            a, b = ref_receipt["worker"]["cost"], model_receipt["worker"]["cost"]
            failures = sum(bool(row["physical_failure"]) for row in model_trajectory["rows"])
            missing_execution = sum(row["requested_action"]["kind"] == "transfer" and
                (row.get("actual_submission") is None or not any(ack.get("status") in
                    ("granted", "dispatching", "departed", "in_transit", "received")
                    for ack in (row.get("ack") or []))) for row in model_trajectory["rows"])
            passed = (direction["known_direction_harm"] == 0 and b["completed_by_end"] >= a["completed_by_end"]
                      and b["on_time_by_end"] >= a["on_time_by_end"]
                      and b["arrived_unfinished_past_deadline"] <= a["arrived_unfinished_past_deadline"]
                      and failures == 0 and missing_execution == 0)
            rows.append(dict(parent_seed=parent, gain_bag_seconds=ref_trajectory["system_J"]-model_trajectory["system_J"],
                service_gate_passed=passed, known_direction_harmed=direction["known_direction_harm"],
                completion_direction=direction, physical_failure_count=failures,
                missing_positive_ack_or_submission_count=missing_execution,
                on_time_delta=b["on_time_by_end"]-a["on_time_by_end"],
                completed_delta=b["completed_by_end"]-a["completed_by_end"],
                overdue_unfinished_delta=b["arrived_unfinished_past_deadline"]-a["arrived_unfinished_past_deadline"],
                reference_receipt=bound(reference_dir/"receipt.json"), model_receipt=bound(model_dir/"receipt.json")))
        mean_gain = math.fsum(row["gain_bag_seconds"] for row in rows)/len(rows)
        eligible = all(row["service_gate_passed"] for row in rows) and mean_gain > 0
        candidates.append(dict(information_variant=variant, seed=seed, per_parent=rows,
            parent_mean_gain_bag_seconds=mean_gain, passes_observed_service_and_gain_gate=eligible,
            preliminary_recommendation="learned_candidate" if eligible else reference_method,
            strict_per_bag_nonharm_certified=False, protected_takeover_eligible=False))
    result = dict(schema=SCHEMA+".development_audit", candidates=candidates, model_seeds_retained=[17, 29, 43],
                  status="ready_for_independent_development_audit", test_locked=True, test_unlocked=False,
                  champion_freeze_performed=False, test_data_read=False, independent_real_airport_days=0,
                  resume="Review actual mechanisms, service constraints and evidence; champion freeze and test unlock require a separate audited artifact.")
    write_once(_root(config)/"development_audit.json", result)
    return result


def stage_status(config):
    root = _root(config)
    result = dict(schema=SCHEMA+".status", stage_id=config["stage_id"], budget=budget.status(config["cycle"]),
                  native_stages={}, training_rounds={}, test_locked=True)
    for stage in STAGES:
        path = root/"stages"/(stage+".json")
        tasks = read(path)["task_plans"] if path.exists() else []
        states = []
        for task in tasks:
            directory = _native_directory(config, Path(task["path"]).parent.name)
            status = "prepared"
            if (directory/"receipt.json").exists():
                receipt = read(directory/"receipt.json")
                status = receipt["worker"].get("scientific_status", "unknown")
            states.append(dict(task_id=directory.name, status=status))
        result["native_stages"][stage] = dict(prepared=len(tasks), complete=(root/"stages"/(stage+"_complete.json")).exists(), tasks=states)
    for round_index in (0, 1):
        result["training_rounds"][str(round_index)] = {}
        for variant, seed in MODELS:
            directory = _fit_directory(config, round_index, variant, seed)
            result["training_rounds"][str(round_index)][f"{variant}_S{seed}"] = (
                read(directory/"receipt.json")["process_status"] if (directory/"receipt.json").exists() else "not_started")
    return result


def advance(config):
    with active_interval(config, "complete_pretest_dependency_chain"):
        for stage in ("bridge", "initial"):
            run_stage(config, stage)
        train(config, 0)
        run_stage(config, "recollect")
        train(config, 1)
        run_stage(config, "development")
        return development_audit(config)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    for name in ("source", "mapping", "gate-receipt", "calibration"):
        init.add_argument("--"+name, type=Path, required=True)
    init.add_argument("--fit-wall-seconds", type=float, default=900.)
    for command in ("build-stage", "run-stage"):
        p = sub.add_parser(command)
        p.add_argument("stage", choices=STAGES)
    p = sub.add_parser("train")
    p.add_argument("--round", dest="round_index", type=int, choices=(0, 1), required=True)
    for command in ("advance", "audit-dev", "status"):
        sub.add_parser(command)
    p = sub.add_parser("resolve-native")
    p.add_argument("--logical-task-id", required=True)
    p.add_argument("--replacement-plan", type=Path, required=True)
    p.add_argument("--diagnosis", type=Path, required=True)
    for name in ("resolve-fit", "prepare-fit-retry"):
        p = sub.add_parser(name)
        p.add_argument("--round", dest="round_index", type=int, choices=(0, 1), required=True)
        p.add_argument("--variant", choices=("C01", "C11"), required=True)
        p.add_argument("--seed", type=int, choices=(17, 29, 43), required=True)
        p.add_argument("--diagnosis", type=Path, required=True)
        if name == "resolve-fit":
            p.add_argument("--replacement-registration", type=Path, required=True)
        else:
            p.add_argument("--attempt", type=int, required=True)
    p = sub.add_parser("recover-dead")
    p.add_argument("--runner-id", required=True)
    p.add_argument("--task-id")
    p.add_argument("--diagnosis", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "init":
        result = initialize(source_bundle=bound(args.source), mapping=bound(args.mapping),
            gate_receipt=bound(args.gate_receipt), calibration=bound(args.calibration), fit_wall_seconds=args.fit_wall_seconds)
    else:
        config = load_config(args.config)
        try:
            if args.command == "resolve-native":
                result = resolve_native(config, logical_task_id=args.logical_task_id,
                    replacement_plan=bound(args.replacement_plan), diagnosis=bound(args.diagnosis))
            elif args.command == "resolve-fit":
                result = resolve_fit(config, round_index=args.round_index, variant=args.variant, seed=args.seed,
                    replacement_registration=bound(args.replacement_registration), diagnosis=bound(args.diagnosis))
            elif args.command == "prepare-fit-retry":
                with active_interval(config, "prepare_explicit_fit_retry"):
                    result = prepare_fit_retry(config, round_index=args.round_index, variant=args.variant,
                        seed=args.seed, attempt=args.attempt, diagnosis=bound(args.diagnosis))
            elif args.command == "recover-dead":
                result = recover_dead(config, runner_id=args.runner_id, task_id=args.task_id,
                                      diagnosis=bound(args.diagnosis))
            else:
                result = (build_stage(config, args.stage) if args.command == "build-stage" else
                      run_stage(config, args.stage) if args.command == "run-stage" else
                      train(config, args.round_index) if args.command == "train" else
                      advance(config) if args.command == "advance" else
                          development_audit(config) if args.command == "audit-dev" else stage_status(config))
        except Exception:
            failure = dict(schema=SCHEMA+".interruption", command=args.command, exception=traceback.format_exc(),
                process_status="failed_or_blocked", scientific_status="unresolved", test_locked=True,
                resume="Inspect preserved receipt. For dead processes use recover-dead with a diagnosis JSON. Register a fresh reserve native plan then resolve-native, or use prepare-fit-retry/resolve-fit. Resolution chains preserve old attempts and all consumers follow the appended binding. Then resume the same advance command.")
            write_once(_root(config)/"interruptions"/(secrets.token_hex(8)+".json"), failure)
            raise
    if args.command == "status":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(dict(command=args.command, status="completed", test_locked=True,
                             result_kind=type(result).__name__), ensure_ascii=False))


if __name__ == "__main__":
    main()
