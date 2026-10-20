"""Pure admission checks. Native loading and Windows child execution are forbidden."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_inventory_spi_campaign as campaign
from scripts.experiments.g31_ics_circulation import bounded_windows_job


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return campaign.bound(path)


@pytest.fixture
def launch_fixture(tmp_path, monkeypatch):
    """Only ledger/budget admission is under test; no worker is executed."""
    clock = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock

    monkeypatch.setattr(campaign, "datetime", FrozenDatetime)
    monkeypatch.setattr(campaign, "verify", lambda plan: None)
    monkeypatch.setattr(bounded_windows_job, "run",
                        lambda *args, **kwargs: pytest.fail("native process launch forbidden in admission test"))
    directory = tmp_path / "DUMMY_run"
    directory.mkdir()
    ledger = tmp_path / "native_attempts.jsonl"
    ledger.write_text("", encoding="utf-8")
    source = write(tmp_path / "DUMMY_source_manifest.json", {"root": str(tmp_path), "files": {}})
    plan = {"name": "DUMMY_run", "cycle": str(tmp_path), "batch": "formal_8_parents_5_methods",
            "hard_seconds": 1260., "soft_seconds": 1200.,
            "source_bundle": source, "binary": {"sha256": "0" * 64}}
    write(directory / "plan.json", plan)

    def budget(remaining_seconds):
        write(tmp_path / "campaign_budget.json", {
            "created_at_utc": (clock-timedelta(seconds=16*3600-remaining_seconds)).isoformat(),
            "wall_hours_limit": 16, "long_branch_limit": 128,
            "long_allocations": {"formal_8_parents_5_methods": 40}})

    return directory, ledger, budget


@pytest.mark.parametrize("remaining_seconds", [1259., 0., -1.])
def test_total_wall_deadline_rejects_before_ledger_or_child(launch_fixture, remaining_seconds):
    directory, ledger, budget = launch_fixture
    budget(remaining_seconds)
    with pytest.raises(ValueError, match="budget|deadline|remaining|wall"):
        campaign.launch(directory)
    assert ledger.read_text(encoding="utf-8") == ""
    assert not (directory / "stdout.log").exists()
    assert not (directory / "receipt.json").exists()


def test_cached_test_parent_still_requires_unlock(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "CYCLE", tmp_path)
    directory = tmp_path / "parents/P1301_r0_N22_E750000"
    write(directory / "parent.json", {"parent_seed": 1301, "split": "test", "DUMMY": True})
    write(directory / "input.json", {"DUMMY": True})
    from scripts.experiments.g31_ics_circulation import foundation_airport_spi_parents
    monkeypatch.setattr(foundation_airport_spi_parents, "make_parent",
                        lambda *args, **kwargs: pytest.fail("test generation forbidden"))
    with pytest.raises(ValueError, match="unlock|locked|champion|formal"):
        campaign.materialize_parent(1301)


def test_cached_test_parent_rejects_tampered_unlock(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "CYCLE", tmp_path)
    directory = tmp_path / "parents/P1301_r0_N22_E750000"
    write(directory / "parent.json", {"parent_seed": 1301, "split": "test", "DUMMY": True})
    write(directory / "input.json", {"DUMMY": True})
    unlock_path = tmp_path / "DUMMY_unlock.json"
    unlock = write(unlock_path, {"status": "all_champions_frozen_test_unlocked",
                                "test_parent_ids": list(range(1301, 1309))})
    unlock_path.write_text('{"status":"tampered"}', encoding="utf-8")
    with pytest.raises(ValueError, match="bound_file_changed|unlock|locked|champion|formal"):
        campaign.materialize_parent(1301, unlock=unlock)


@pytest.mark.parametrize("method,reason", [
    ("C01", "explicit_frozen_model_required"),
    ("C11", "explicit_frozen_model_required"),
    ("C10", "explicit_frozen_rule_required"),
])
def test_formal_method_requires_explicit_frozen_artifact_before_parent_access(
        tmp_path, monkeypatch, method, reason):
    monkeypatch.setattr(campaign, "CYCLE", tmp_path)
    monkeypatch.setattr(campaign, "materialize_parent",
                        lambda *args, **kwargs: pytest.fail("parent accessed before method admission"))
    monkeypatch.setattr(campaign, "read_bound",
                        lambda *args, **kwargs: pytest.fail("artifact accessed before method admission"))
    with pytest.raises(ValueError, match=reason):
        campaign.prepare("DUMMY_missing", binary=tmp_path/"never_load.pyd",
            source_bundle=None, native_acceptance=None, seed=1301, method=method,
            batch="formal_8_parents_5_methods")
    assert not (tmp_path/"runs").exists()


@pytest.fixture
def acceptance_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(campaign, "CYCLE", tmp_path)
    binary = tmp_path/"DUMMY_not_an_extension.pyd"
    binary.write_bytes(b"dummy bytes; this file must never be loaded")
    source = write(tmp_path/"DUMMY_sources.json", {"source_manifest_sha256": "dummy"})
    acceptance = {"schema": "g31.native030.inventory_spi_accepted_contract.v1",
                  "status": "passed_with_retained_fixture_failure",
                  "binary": campaign.bound(binary),
                  "constructor_budget": {"consumed": 13, "passed_gate_attempts": 12,
                                         "failed_fixture_attempts": 1}}
    return tmp_path, binary, source, acceptance


@pytest.mark.parametrize("changed", [
    {"schema": "unrecognized"},
    {"status": "failed"},
    {"binary": {"sha256": "f"*64}},
])
def test_native_acceptance_rejects_unaccepted_schema_status_or_binary(
        acceptance_fixture, monkeypatch, changed):
    directory, binary, source, acceptance = acceptance_fixture
    acceptance.update(changed)
    reference = write(directory/"DUMMY_acceptance.json", acceptance)
    monkeypatch.setattr(campaign, "materialize_parent",
                        lambda *args, **kwargs: pytest.fail("unaccepted binary reached parent input"))
    with pytest.raises(ValueError, match="accepted_binary_required"):
        campaign.prepare("DUMMY_bad_acceptance", binary=binary, source_bundle=source,
            native_acceptance=reference, seed=901, method="C00",
            batch="common_fix_R0_old_diagnostics")
    assert not (directory/"runs").exists()


def test_actual_acceptance_status_retains_failed_fixture_instead_of_claiming_all_passed(
        acceptance_fixture, monkeypatch):
    directory, binary, source, acceptance = acceptance_fixture
    reference = write(directory/"DUMMY_acceptance.json", acceptance)

    class AdmittedThroughNativeContract(Exception):
        pass

    def stop_before_parent(*args, **kwargs):
        raise AdmittedThroughNativeContract

    monkeypatch.setattr(campaign, "materialize_parent", stop_before_parent)
    with pytest.raises(AdmittedThroughNativeContract):
        campaign.prepare("DUMMY_accepted", binary=binary, source_bundle=source,
            native_acceptance=reference, seed=901, method="C00",
            batch="common_fix_R0_old_diagnostics")
    assert not (directory/"runs").exists()


def test_sufficient_total_wall_time_does_not_unconditionally_reject(
        launch_fixture, monkeypatch):
    directory, ledger, budget = launch_fixture
    budget(1261.)
    calls = []

    def fake_job(*args, **kwargs):
        calls.append(kwargs)
        write(directory/"worker_report.json", {"status": "DUMMY_no_native_execution"})
        return {"wall_seconds": 0., "status": "DUMMY_no_native_execution"}

    monkeypatch.setattr(bounded_windows_job, "run", fake_job)
    result = campaign.launch(directory)
    assert result["status"] == "DUMMY_no_native_execution"
    assert len(calls) == 1 and calls[0]["timeout"] == 1260.
    entries = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1 and entries[0]["kind"] == "long_branch"


@pytest.mark.parametrize("case", ["missing_calibration", "mismatched_calibration", "infinite_limit"])
def test_changed_wall_limits_reject_missing_mismatched_or_nonfinite_admission(
        acceptance_fixture, monkeypatch, case):
    directory, binary, source, acceptance = acceptance_fixture
    reference = write(directory/"DUMMY_acceptance.json", acceptance)
    monkeypatch.setattr(campaign, "materialize_parent",
                        lambda *args, **kwargs: pytest.fail("invalid calibration reached parent input"))
    calibration = None
    soft, hard = 2280., 2400.
    if case == "mismatched_calibration":
        calibration = write(directory/"DUMMY_bad_calibration.json", {
            "global_event_budget": 750000, "before_first_training_pair": True,
            "soft_seconds": 2280., "hard_seconds": 2399.})
        error, match = ValueError, "explicit_pretraining_budget_calibration"
    elif case == "infinite_limit":
        soft = float("inf")
        error, match = ValueError, "finite_ordered_wall_limits"
    else:
        # Current read_bound(None) rejects before generation. Accept an explicit
        # ValueError too if the runner makes this missing-reference check clearer.
        error, match = (ValueError, TypeError), None
    with pytest.raises(error, match=match):
        campaign.prepare("DUMMY_invalid_wall", binary=binary, source_bundle=source,
            native_acceptance=reference, seed=901, method="C00",
            batch="common_fix_R0_old_diagnostics", soft_seconds=soft,
            hard_seconds=hard, calibration=calibration)
    assert not (directory/"runs").exists()
