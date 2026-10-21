"""Pretest DAG/recovery tests with fake launchers; never starts native or trains."""
import copy
import json
import gzip
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_joint_stage as stage


def config(tmp_path, monkeypatch):
    monkeypatch.setattr(stage.campaign, "CYCLE", tmp_path)
    return dict(cycle=str(tmp_path), stage_id="stage-unit", source_bundle=dict(path="source", sha256="source"),
                mapping=dict(path="mapping", sha256="mapping"), calibration=dict(path="calibration", sha256="calibration"),
                native_calibration=dict(horizon=59400., soft_seconds=2280., hard_seconds=2400.,
                                        estimated_evidence_bytes=1000000))


def test_native_DAG_has_exact_bounded_counts_and_no_test_roster(tmp_path, monkeypatch):
    registered = config(tmp_path, monkeypatch)
    models = {f"{variant}_S{seed}": dict(path=f"{variant}-{seed}", sha256="frozen") for variant, seed in stage.MODELS}
    bridge = stage.task_specs(registered, "bridge")
    initial = stage.task_specs(registered, "initial")
    recollect = stage.task_specs(registered, "recollect", models)
    dev = stage.task_specs(registered, "development", models)
    assert [len(x) for x in (bridge, initial, recollect, dev)] == [20, 24, 12, 24]
    assert len({x["task_id"] for group in (bridge, initial, recollect, dev) for x in group}) == 80
    assert all(x["seed"] < 2300 for group in (bridge, initial, recollect, dev) for x in group)
    assert all(x["root_branch"] in (0, 1, 2) and x["mapping"] for x in initial)
    assert all(x["mapping"] is None for group in (recollect, dev) for x in group if x["method"] == "C01")
    assert all(x["mapping"] == registered["mapping"] for group in (recollect, dev) for x in group if x["method"] == "C11")
    assert {x["seed"] for x in recollect} == {2101, 2102}
    assert all(x["rollout_round"] == 1 for x in recollect)
    with pytest.raises(ValueError, match="registered_pretest_stage"):
        stage.task_specs(registered, "formal", models)


def test_immutable_registration_cannot_be_overwritten(tmp_path):
    path = tmp_path/"registration.json"
    first = stage.write_once(path, dict(identity="a", epochs=100))
    assert stage.write_once(path, dict(identity="a", epochs=100)) == first
    with pytest.raises(ValueError, match="immutable_stage_artifact_conflict"):
        stage.write_once(path, dict(identity="a", epochs=101))
    assert stage.read(path)["epochs"] == 100


def test_gate_requires_closed_native_evidence_and_explicit_admission(tmp_path):
    path = tmp_path/"receipt.json"
    reference = stage.write_once(path, dict(worker=dict(scientific_status="closed"), process=dict(exitcode=0)))
    passed = dict(status="passed", approved_for_joint_stage=True, native_gate_receipts=[reference])
    stage.validate_gate(passed)
    for key, value in (("approved_for_joint_stage", False), ("status", "pytest_passed"), ("native_gate_receipts", [])):
        invalid = dict(passed, **{key: value})
        with pytest.raises(ValueError):
            stage.validate_gate(invalid)
    with pytest.raises(ValueError, match="development_only_stage"):
        stage.validate_gate(dict(passed, test_unlocked=True))


def test_nested_prepare_fit_native_operations_share_one_durable_runner_interval(tmp_path, monkeypatch):
    registered = config(tmp_path, monkeypatch)
    events = []
    monkeypatch.setattr(stage.budget, "append", lambda cycle, kind, **kw: events.append(dict(event=kind, **kw)))
    monkeypatch.setattr(stage, "_ACTIVE_RUNNER", None)
    with stage.active_interval(registered, "whole_chain"):
        with stage.active_interval(registered, "native_stage"):
            assert len(events) == 1
        with stage.active_interval(registered, "training"):
            assert len(events) == 1
    assert [row["event"] for row in events] == ["runner_open", "runner_close"]
    assert events[0]["runner_id"] == events[1]["runner_id"]
    assert stage._ACTIVE_RUNNER is None


def test_failed_native_receipt_never_counts_as_reusable_closed_task(tmp_path):
    plan = dict(task_id="failed-task")
    plan_ref = stage.write_once(tmp_path/"plan.json", plan)
    stage.write_once(tmp_path/"receipt.json", dict(task_id="failed-task", plan_sha256=plan_ref["sha256"],
        process=dict(exitcode=0), worker=dict(process_status="completed", scientific_status="censored_budget")))
    with pytest.raises(ValueError, match="failed_or_censored_task_requires_diagnosis_new_attempt_id"):
        stage._closed_task(tmp_path)


def test_run_stage_reuses_closed_tasks_and_stops_at_failure(tmp_path, monkeypatch):
    registered = config(tmp_path, monkeypatch)
    plans = []
    for index in range(3):
        directory = tmp_path/"runs"/f"task-{index}"
        plans.append(stage.write_once(directory/"plan.json", dict(task_id=directory.name)))
    stage.write_once(tmp_path/"runs/task-0/receipt.json", dict(closed=True))
    monkeypatch.setattr(stage, "build_stage", lambda cfg, name: dict(task_plans=plans))
    events, launched = [], []
    monkeypatch.setattr(stage.budget, "append", lambda cycle, kind, **kw: events.append(kind))
    monkeypatch.setattr(stage, "_ACTIVE_RUNNER", None)

    def launch(directory):
        launched.append(directory.name)
        stage.write_once(directory/"receipt.json", dict(closed=False))

    def closed(directory):
        if not stage.read(directory/"receipt.json")["closed"]:
            raise ValueError("failed native")
        return {}, {}, dict(dataset_id="actual-dataset")

    # A reused task must still have its frozen trajectory evidence.
    (tmp_path/"runs/task-0/trajectory.json.gz").write_bytes(b"fixture-bound-by-mock")
    monkeypatch.setattr(stage.campaign, "launch", launch)
    monkeypatch.setattr(stage, "_closed_task", closed)
    with pytest.raises(ValueError, match="failed native"):
        stage.run_stage(registered, "initial")
    assert launched == ["task-1"]
    assert events == ["runner_open", "runner_close"]
    assert not (tmp_path/"runs/task-2/receipt.json").exists()
    assert not (tmp_path/"stage/stages/initial_complete.json").exists()


def test_advance_orders_real_recollection_before_retraining_and_stops_at_dev_audit(tmp_path, monkeypatch):
    registered = config(tmp_path, monkeypatch)
    events = []
    monkeypatch.setattr(stage.budget, "append", lambda cycle, kind, **kw: None)
    monkeypatch.setattr(stage, "_ACTIVE_RUNNER", None)
    monkeypatch.setattr(stage, "run_stage", lambda cfg, name: events.append(name))
    monkeypatch.setattr(stage, "train", lambda cfg, index: events.append("fit"+str(index)))
    monkeypatch.setattr(stage, "development_audit", lambda cfg: events.append("audit") or dict(test_locked=True))
    assert stage.advance(registered)["test_locked"]
    assert events == ["bridge", "initial", "fit0", "recollect", "fit1", "development", "audit"]


def test_model_availability_is_after_actual_training_round_before_dev():
    assert stage.MODEL_AVAILABLE[0] < stage.MODEL_AVAILABLE[1]
    assert stage.MODEL_AVAILABLE[0] == 1794240000.
    assert stage.MODEL_AVAILABLE[1] == 1796054400.


def retry_setup(tmp_path, monkeypatch):
    registered = config(tmp_path, monkeypatch)
    events = []
    monkeypatch.setattr(stage.budget, "append", lambda cycle, kind, **kw: events.append(dict(event=kind, **kw)))
    monkeypatch.setattr(stage.budget, "events", lambda cycle: events)
    monkeypatch.setattr(stage.budget, "status", lambda cycle: dict(native_starts=24,
        by_batch=dict(reserve=0), unfinished_native_tasks=[]))
    monkeypatch.setattr(stage.campaign, "verify", lambda plan: None)
    monkeypatch.setattr(stage, "_ACTIVE_RUNNER", None)
    stage.write_once(tmp_path/"campaign_budget.json", dict(native_start_limit=160, allocations=dict(reserve=8)))
    diagnosis = stage.write_once(tmp_path/"diagnosis.json", dict(reason="Diagnosed transient resource interruption; same scientific contract."))
    return registered, events, diagnosis


def test_native_resolution_routes_resume_to_new_reserve_attempt_and_preserves_failed_001(tmp_path, monkeypatch):
    registered, events, diagnosis = retry_setup(tmp_path, monkeypatch)
    old_dir, new_dir = tmp_path/"runs/logical_001", tmp_path/"runs/retry_002"
    old_ref = stage.write_once(old_dir/"plan.json", dict(task_id=old_dir.name, batch="initial", method="explore"))
    new_ref = stage.write_once(new_dir/"plan.json", dict(task_id=new_dir.name, batch="reserve", method="explore"))
    failed = dict(task_id=old_dir.name, plan_sha256=old_ref["sha256"], process=dict(exitcode=1),
                  worker=dict(process_status="failed", scientific_status="unknown_error"))
    stage.write_once(old_dir/"receipt.json", failed)
    before = (old_dir/"receipt.json").read_bytes()
    resolution = stage.resolve_native(registered, logical_task_id=old_dir.name,
                                       replacement_plan=new_ref, diagnosis=diagnosis)
    assert stage._native_directory(registered, old_dir.name) == new_dir
    assert resolution["native_budget_refunded"] is False
    assert (old_dir/"receipt.json").read_bytes() == before
    assert any(row["event"] == "stage_resolution" for row in events)
    monkeypatch.setattr(stage, "build_stage", lambda cfg, name: dict(task_plans=[old_ref]))
    launched = []

    def launch(directory):
        launched.append(directory)
        stage.write_once(directory/"receipt.json", dict(closed=True))
        (directory/"trajectory.json.gz").write_bytes(b"mock")

    monkeypatch.setattr(stage.campaign, "launch", launch)
    monkeypatch.setattr(stage, "_closed_task", lambda directory: ({}, {}, dict(dataset_id="new-real-dataset")))
    result = stage.run_stage(registered, "initial")
    assert launched == [new_dir]
    assert result[0]["task_id"] == new_dir.name and result[0]["logical_task_id"] == old_dir.name
    assert (old_dir/"receipt.json").read_bytes() == before


def test_native_resolution_rejects_original_batch_budget_refund_and_changed_domain(tmp_path, monkeypatch):
    registered, _, diagnosis = retry_setup(tmp_path, monkeypatch)
    old_dir = tmp_path/"runs/old"
    old_ref = stage.write_once(old_dir/"plan.json", dict(task_id="old", batch="initial", method="explore"))
    stage.write_once(old_dir/"receipt.json", dict(task_id="old", plan_sha256=old_ref["sha256"],
        process=dict(exitcode=1), worker=dict(process_status="failed", scientific_status="unknown")))
    for identity, batch, method, message in (("new-original-batch", "initial", "explore", "fresh_reserve"),
                                          ("new-domain", "reserve", "C00", "scientific_domain")):
        reference = stage.write_once(tmp_path/"runs"/identity/"plan.json", dict(task_id=identity, batch=batch, method=method))
        with pytest.raises(ValueError, match=message):
            stage.resolve_native(registered, logical_task_id="old", replacement_plan=reference, diagnosis=diagnosis)


def test_fit_resolution_prepares_new_registration_and_resume_consumes_completed_replacement(tmp_path, monkeypatch):
    registered, events, diagnosis = retry_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(stage, "MODELS", (("C01", 17),))
    old_dir = tmp_path/"stage/training/round_0/C01_S17"
    old_registration = dict(registration_id="original-fit", information_variant="C01", seed=17,
                            epochs=100, training_dataset_sha256="actual-training-only")
    old_registration_ref = stage.write_once(old_dir/"registration.json", old_registration)
    stage.write_once(old_dir/"receipt.json", dict(process_status="failed", scientific_status="unknown_fit",
                                                 registration=old_registration_ref))
    failed_bytes = (old_dir/"receipt.json").read_bytes()
    resolution = stage.prepare_fit_retry(registered, round_index=0, variant="C01", seed=17, attempt=2, diagnosis=diagnosis)
    new_dir = stage._fit_directory(registered, 0, "C01", 17)
    assert new_dir == old_dir/"attempts/attempt_002"
    new_registration = stage.read(new_dir/"registration.json")
    assert new_registration["registration_id"] != old_registration["registration_id"]
    assert {k: v for k, v in new_registration.items() if k != "registration_id"} == {
        k: v for k, v in old_registration.items() if k != "registration_id"}
    model_ref = stage.write_once(new_dir/"model.json", dict(model_id="new-weights", information_variant="C01", seed=17,
                                                           registration=new_registration))
    stage.write_once(new_dir/"receipt.json", dict(process_status="completed", scientific_status="model_frozen",
        model=model_ref, model_id="new-weights", registration=stage.bound(new_dir/"registration.json")))
    assert stage.model_references(registered, 0)["C01_S17"] == model_ref
    monkeypatch.setattr(stage, "_verify_fit_sources", lambda cfg: None)
    monkeypatch.setattr(stage, "initial_training_data", lambda cfg: ([], []))
    monkeypatch.setattr(stage.learning, "fit_model", lambda *args, **kwargs: pytest.fail("completed replacement must not refit"))
    receipts = stage.train(registered, 0)
    assert receipts[0]["model_id"] == "new-weights"
    assert (old_dir/"receipt.json").read_bytes() == failed_bytes
    assert any(row["event"] == "fit_finish" and row.get("recovered_from_closed_receipt") for row in events)


def test_missing_native_receipt_requires_verified_dead_recovery(tmp_path, monkeypatch):
    registered, _, diagnosis = retry_setup(tmp_path, monkeypatch)
    old_dir, new_dir = tmp_path/"runs/old", tmp_path/"runs/new"
    stage.write_once(old_dir/"plan.json", dict(task_id="old", batch="initial", method="explore"))
    new_ref = stage.write_once(new_dir/"plan.json", dict(task_id="new", batch="reserve", method="explore"))
    with pytest.raises(ValueError, match="explicit_dead_attempt_recovery"):
        stage.resolve_native(registered, logical_task_id="old", replacement_plan=new_ref, diagnosis=diagnosis)
    monkeypatch.setattr(stage.budget, "events", lambda cycle: [dict(event="native_finish", task_id="old", recovered=True,
        scientific_status="unknown_unclosed_attempt", process_status="interrupted_unknown")])
    stage.resolve_native(registered, logical_task_id="old", replacement_plan=new_ref, diagnosis=diagnosis)
    assert stage._native_directory(registered, "old") == new_dir


def test_closed_trajectory_must_match_full_plan_even_if_self_digest_is_valid(tmp_path):
    from test_g31_foundation_airport_joint_learning import trajectory
    data = trajectory(extra=dict(episode_parent_group="p1:r0", rollout_round=0))
    parent = dict(parent_group="p1:r0", parent_seed=101, rollout_round=0, split="train", plan_family_id="lineage-p1",
                  common_historical_template_sha256="one-historical-day", calendar_start_epoch_seconds=1000., offered_count=3)
    plan = dict(task_id="t1", parent=parent, behavior_seed=17, source_bundle=dict(sha256="source-1"),
                binary=dict(sha256="native-1"), policy_version="joint-v1", activation=0., horizon=10.)
    plan_ref = stage.write_once(tmp_path/"plan.json", plan)
    stage.write_once(tmp_path/"receipt.json", dict(task_id="t1", plan_sha256=plan_ref["sha256"], process=dict(exitcode=0),
        worker=dict(process_status="completed", scientific_status="closed", final_physical_time=10.)))

    def save(value):
        value["dataset_id"] = stage.digest({k: v for k, v in value.items() if k != "dataset_id"})
        with gzip.open(tmp_path/"trajectory.json.gz", "wt") as stream:
            json.dump(value, stream)

    save(data)
    assert stage._closed_task(tmp_path)[2]["manifest"]["parent_uid"] == "p1"
    for key, wrong in (("split", "test"), ("execution_source_id", "other-source"),
                       ("native_domain_id", "other-native"), ("physical_end", 11.),
                       ("calendar_start_epoch_seconds", 2000.), ("parent_uid", "another-parent")):
        changed = copy.deepcopy(data)
        changed["manifest"][key] = wrong
        save(changed)
        with pytest.raises(ValueError, match="trajectory_full_plan_domain_binding"):
            stage._closed_task(tmp_path)
