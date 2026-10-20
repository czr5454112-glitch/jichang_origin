"""Offline stage tests; mock runner preparation and scientific fitting."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_spi_stages as s


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    def save(name, value):
        return s.write_new(tmp_path / name, value)
    binary = tmp_path / "dummy-not-a-native-binary.pyd"
    binary.write_text("DUMMY")
    runtime = {"binary": str(binary.resolve()),
        "source_bundle": save("sources.json", {"files": {}, "source_manifest_sha256": "dummy"}),
        "native_acceptance": save("accepted.json", {"status": "DUMMY"})}
    document = tmp_path / "preregistration.md"
    document.write_text("DUMMY ONLY")
    registration = save("registration.json", {
        "schema": s.runner.SCHEMA + ".registration",
        "parent_registry": save("parents.json", {
            "schema": "g31.spi_parent_registration.v1", "domain": s.parents.DOMAIN,
            "splits": {str(k): v for k, v in s.parents.SPLITS.items()}}),
        "learning_contract": save("learning.json", s.spi.make_spi_contract(
            allowed_domains=[s.parents.DOMAIN], behavior_policy_id=s.runner.PI0,
            continuation_policy_id=s.runner.PI0)),
        "contract_document": s.runner.bound(document),
        "budget": save("budget.json", {"DUMMY": True}),
        "runtime_shared": save("runtime.json", runtime)})
    shared = {**runtime, "preregistration": registration}
    calls = []

    def prepare(name, **kwargs):
        calls.append((name, deepcopy(kwargs)))
        directory = tmp_path / "runs" / name
        directory.mkdir(parents=True)
        round_ = kwargs.get("rollout_round", 0)
        seed = kwargs["seed"]
        parent = {"parent_seed": seed, "split": s.parents.SPLITS[seed],
            "parent_group": f"DUMMY:{seed}:r{round_}", "rollout_round": round_,
            "spi_domain": s.parents.DOMAIN, "synthetic": True,
            "calendar_start_epoch_seconds": 1.}
        plan = {**kwargs, "name": name, "parent": parent,
            "input_semantic_sha256": "DUMMY_SHARED",
            "event_calibration": kwargs.get("calibration"),
            "behavior_model": kwargs.get("behavior_model"), "pair": kwargs.get("pair")}
        s.write_new(directory / "plan.json", plan)
        return directory
    monkeypatch.setattr(s.runner, "prepare", prepare)
    return {"root": tmp_path, "shared": shared, "save": save, "calls": calls}


def batch(sandbox, round_=0, freeze=None):
    return s.prepare_pair_batch(shared=sandbox["shared"], rollout_round=round_,
        spi_freeze=freeze, output=sandbox["root"] / f"batch{round_}.json")


def close_all(manifest_ref, *, missing_evidence_at=None, leave_pending_at=None):
    manifest = s.read_bound(manifest_ref)
    index = 0
    for slot in manifest["slots"]:
        for branch, ref in slot["plans"].items():
            directory = Path(ref["path"]).parent
            if index != leave_pending_at:
                s.write_new(directory / "receipt.json", {"plan_sha256": ref["sha256"],
                    "process": {"status": "DUMMY_CLOSED"},
                    "status": "failed" if index == missing_evidence_at else "no_eligible_opportunity"})
            if index != missing_evidence_at:
                s.write_new(directory / "branch_evidence.json.gz", {
                    "branch": branch, "parent": slot["parent"], "input_sha256": "DUMMY_SHARED",
                    "continuation_version": manifest["policy_alignment"]["continuation_policy_id"],
                    "policy_alignment": manifest["policy_alignment"], "selected": None,
                    "status": "no_eligible_anchor", "cost": None})
            index += 1


def frozen_reference(sandbox, monkeypatch):
    contract = s.spi.make_spi_contract(allowed_domains=[s.parents.DOMAIN],
        behavior_policy_id=s.runner.PI0, continuation_policy_id=s.runner.PI0)
    models = []
    for variant in ("C01", "C11"):
        model = s.spi.make_reference_champion(information_variant=variant, contract=contract,
            model_available_at_epoch_seconds=s.WEIGHTS_AVAILABLE)
        ref = sandbox["save"](variant + ".json", model)
        models.append({"information_variant": variant, "checkpoint": ref,
            "model_id": model["model_id"], "reference_champion": True})
    value = {"contract": contract, "models": models}
    reference = sandbox["save"]("spi_freeze.json", value)
    monkeypatch.setattr(s.training, "validate_spi_freeze", s.read_bound)
    return reference


def test_exact_preregistered_rotations_and_no_test_slots():
    first, second = s.registered_pair_slots(0), s.registered_pair_slots(1)
    assert len(first) == 24 and len(second) == 12
    assert sum(r["split"] == "train" for r in first) == 16
    assert first[0]["window"] == [7200., 9000.] and first[1]["window"] == [30000., 35400.]
    assert [r["patch_rank"] for r in first[:4]] == [1, 2, 3, 4]
    assert second[0]["window"] == [18000., 23400.] and second[0]["patch_rank"] == 3
    assert first[16]["parent_seed"] == 1201 and first[16]["window"] == first[0]["window"]
    assert not {r["parent_seed"] for r in first + second}.intersection(s.TEST)


def test_prepare_all_48_plans_does_not_pass_preregistration_to_native_runner(sandbox):
    ref = batch(sandbox)
    manifest = s.read_bound(ref)
    assert manifest["registered_arms"] == 48 and len(sandbox["calls"]) == 48
    assert len(s.plan_directories(ref)) == 48
    assert manifest["native_runs_started_by_preparation"] == 0
    assert all("preregistration" not in kwargs and kwargs["recovery"]
        and kwargs["pair"]["policy_alignment"] == s._alignment(0, s.runner.PI0)
        for _, kwargs in sandbox["calls"])
    assert all(slot["parent"]["spi_domain"] == s.parents.DOMAIN for slot in manifest["slots"])


def test_round1_requires_selected_C01_then_replays_degenerate_reference(sandbox, monkeypatch):
    with pytest.raises(ValueError, match="round1_requires"):
        batch(sandbox, 1)
    assert sandbox["calls"] == []
    frozen = frozen_reference(sandbox, monkeypatch)
    reference = batch(sandbox, 1, frozen)
    manifest = s.read_bound(reference)
    assert len(s.plan_directories(reference)) == 24
    assert not manifest["nontrivial_policy_improvement"]
    assert manifest["policy_alignment"] == s._alignment(1, s.runner.PI0)
    assert manifest["behavior_model"] == s.read_bound(frozen)["models"][0]["checkpoint"]
    assert all(row["parent"]["rollout_round"] == 1 for row in manifest["slots"])


def test_all_receipts_checked_before_any_branch_outcome_read(sandbox, monkeypatch):
    ref = batch(sandbox)
    close_all(ref, leave_pending_at=47)
    original = s.read_bound
    def guarded(reference):
        assert "branch_evidence" not in reference["path"]
        return original(reference)
    monkeypatch.setattr(s, "read_bound", guarded)
    with pytest.raises(ValueError, match="all_registered_attempts_must_close"):
        s.collect_pair_batch(ref, output=sandbox["root"] / "collection.json")
    assert not (sandbox["root"] / "collection_datasets").exists()


def test_failed_missing_branch_is_retained_with_empty_rows_and_all_parent_metadata(sandbox):
    ref = batch(sandbox)
    close_all(ref, missing_evidence_at=0)
    result_ref = s.collect_pair_batch(ref, output=sandbox["root"] / "collection.json")
    result = s.validate_collection(result_ref, rollout_round=0)
    assert result["registered_pairs"] == 24 and result["closed_attempt_receipts"] == 48
    assert result["pair_status_counts"] == {"unavailable_actual_pair": 1, "not_comparable": 23}
    assert result["attempt_status_counts"]["failed"] == 1
    data = s.read_bound(result["inputs"][0]["dataset"])
    assert data["rows"] == [] and data["failed_pair_retained"]
    assert data["pair"]["parent"] == result["inputs"][0]["parent"]
    assert data["pair"]["advantage_bag_seconds"] is None
    assert data["collection_failure_details"][0]["reason"] == "missing_branch_evidence"
    assert len(result["train_inputs"]) == 16 and len(result["dev_inputs"]) == 8


def test_prefix_validation_error_is_unavailable_not_a_silent_exclusion(sandbox, monkeypatch):
    ref = batch(sandbox)
    close_all(ref)
    def reject(*_):
        raise ValueError("different_complete_prefix")
    monkeypatch.setattr(s.pairs, "dataset_rows", reject)
    result_ref = s.collect_pair_batch(ref, output=sandbox["root"] / "collection.json")
    value = s.validate_collection(result_ref, rollout_round=0)
    assert value["pair_status_counts"] == {"unavailable_actual_pair": 24}
    assert value["unavailable_pairs_excluded"] == 0


def test_no_closed_labels_produces_explicit_insufficient_receipt_without_fit(sandbox, monkeypatch):
    ref = batch(sandbox)
    close_all(ref)
    collection = s.collect_pair_batch(ref, output=sandbox["root"] / "collection.json")
    def forbidden(**_):
        pytest.fail("No-label collection must not register/fabricate a model")
    monkeypatch.setattr(s.training, "prepare_spi_manifest", forbidden)
    out = s.train_and_freeze(collection, output=sandbox["root"] / "training", execute=True)
    receipt = s.read_bound(out)
    assert receipt["status"] == "insufficient_unavailable_closed_train_or_dev_labels"
    assert receipt["registered_pairs"] == 24 and receipt["closed_attempt_receipts"] == 48
    assert receipt["closed_actual_pairs_by_split"] == {"train": 0, "dev": 0}
    assert receipt["fit_calls_started"] == 0 and not receipt["formal_unlock_authorized"]


def test_round1_collection_cannot_enter_first_round_training(sandbox, monkeypatch):
    freeze = frozen_reference(sandbox, monkeypatch)
    ref = batch(sandbox, 1, freeze)
    close_all(ref)
    collection = s.collect_pair_batch(ref, output=sandbox["root"] / "collection.json")
    with pytest.raises(ValueError, match="all_registered_pairs"):
        s.train_and_freeze(collection, output=sandbox["root"] / "training")
    assert not (sandbox["root"] / "training").exists()


def test_default_train_call_only_registers_and_never_fits(sandbox, monkeypatch):
    ref = batch(sandbox)
    close_all(ref)
    original = s.pairs.dataset_rows
    def labeled(left, right):
        value = original(left, right)
        value["pair"]["status"] = "closed_actual_pair"  # DUMMY orchestration only.
        return value
    monkeypatch.setattr(s.pairs, "dataset_rows", labeled)
    collection = s.collect_pair_batch(ref, output=sandbox["root"] / "collection.json")
    registered = []
    def register(**kwargs):
        registered.append(kwargs)
        return sandbox["save"]("dummy-training-manifest.json", {"DUMMY": True})
    monkeypatch.setattr(s.training, "prepare_spi_manifest", register)
    monkeypatch.setattr(s, "execute_training_registration",
        lambda *_a, **_kw: pytest.fail("default registration cannot fit"))
    ref = s.train_and_freeze(collection, output=sandbox["root"] / "training")
    assert s.read_bound(ref)["status"] == "registered_not_run"
    assert len(registered[0]["train_inputs"]) == 16 and len(registered[0]["dev_inputs"]) == 8
    assert registered[0]["model_available_at_epoch_seconds"] == s.WEIGHTS_AVAILABLE


def test_formal_unlock_validated_before_any_test_prepare_then_exact_40_cells(sandbox, monkeypatch):
    frozen = frozen_reference(sandbox, monkeypatch)
    batch_ref = batch(sandbox, 1, frozen)
    close_all(batch_ref)
    collection = s.collect_pair_batch(batch_ref, output=sandbox["root"] / "collection.json")
    rule = sandbox["save"]("rule.json", {"selected": "reference", "forecast_weight": 0})
    monkeypatch.setattr(s.rules, "validate_rule_selection", s.read_bound)
    calls_before = len(sandbox["calls"])
    unlocked = []
    def validate(ref):
        assert len(sandbox["calls"]) == calls_before
        value = s.read_bound(ref)
        assert value["round1_collection"] == collection
        assert value["models"] == {r["information_variant"]: r["checkpoint"]
            for r in s.read_bound(frozen)["models"]}
        unlocked.append(ref)
        return value
    monkeypatch.setattr(s.runner, "validate_formal_unlock", validate)
    ref = s.prepare_formal(shared=sandbox["shared"], spi_freeze=frozen, rule=rule,
        round1_collection=collection, output=sandbox["root"] / "formal.json")
    value = s.read_bound(ref)
    assert len(unlocked) == 1 and value["registered_arms"] == 40
    assert len({(row["parent_seed"], row["method"]) for row in value["plans"]}) == 40
    assert not value["test_outcomes_opened"]
    assert {k["method"] for _, k in sandbox["calls"][calls_before:]} == set(s.runner.METHODS)


def test_invalid_rule_freeze_blocks_test_materialization(sandbox, monkeypatch):
    frozen = frozen_reference(sandbox, monkeypatch)
    def invalid(_):
        raise ValueError("DUMMY invalid rule")
    monkeypatch.setattr(s.rules, "validate_rule_selection", invalid)
    with pytest.raises(ValueError, match="invalid rule"):
        s.prepare_formal(shared=sandbox["shared"], spi_freeze=frozen,
            rule={"path": "unused", "sha256": "unused"},
            round1_collection={"path": "must-not-read", "sha256": "unused"},
            output=sandbox["root"] / "formal.json")
    assert sandbox["calls"] == []


def test_shared_revised_administrative_limits_are_bound_and_passed_through(sandbox):
    shared = sandbox["shared"]
    calibration = sandbox["save"]("calibration.json", {"DUMMY": True})
    shared.update(soft_seconds=2280., hard_seconds=2400., calibration=calibration)
    registration = s.read_bound(shared["preregistration"])
    runtime = s.read_bound(registration["runtime_shared"])
    runtime.update(soft_seconds=2280., hard_seconds=2400., calibration=calibration)
    registration["runtime_shared"] = sandbox["save"]("runtime2.json", runtime)
    shared["preregistration"] = sandbox["save"]("registration2.json", registration)
    ref = batch(sandbox)
    assert len(s.plan_directories(ref)) == 48
    assert all(kwargs["soft_seconds"] == 2280. and kwargs["hard_seconds"] == 2400.
        and kwargs["calibration"] == calibration for _, kwargs in sandbox["calls"])
