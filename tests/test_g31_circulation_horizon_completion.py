"""Completeness includes all native events at H, not just numeric clock H."""
import os
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation.native_host import load_native, tiny_cycle


@pytest.fixture(scope="module")
def native():
    binary = os.environ.get("G31_CIRCULATION_BINARY")
    if not binary:
        binary = next((Path(__file__).absolute().parents[1] / "build_lt_session/python").glob("czr005_circulation*.pyd"))
    return load_native(binary)


def fixture():
    data = tiny_cycle()
    data["transfers"] = []
    return data


def test_same_timestamp_pending_microphases_are_budget_exhausted(native):
    session = native.NativeSession(fixture())
    session.advance_to(0)
    paused = session.advance_to(.1, 1)
    assert paused["physical_time"] == .1 and paused["processed_events"] == 1
    assert paused["status"] == "budget_exhausted" and paused["horizon_complete"] is False
    before = session.offline_state_sha256()
    checkpoint = session.checkpoint()
    completed = session.advance_to(.1, 10000)
    assert completed["physical_time"] == .1 and completed["processed_events"] > 0
    assert completed["status"] == "reached" and completed["horizon_complete"] is True
    assert before != session.offline_state_sha256()
    restored = native.NativeSession(fixture())
    restored.restore(checkpoint)
    assert restored.advance_to(.1, 10000)["horizon_complete"] is True
    assert restored.offline_state_sha256() == session.offline_state_sha256()
    assert "horizon_complete" not in session.observe("A")


def test_exact_event_budget_with_no_due_event_still_reaches_horizon(native):
    session = native.NativeSession(fixture())
    completed = session.advance_to(0, 1)
    assert completed["processed_events"] == 1
    assert completed["status"] == "reached" and completed["horizon_complete"] is True
    before = session.offline_state_sha256()
    assert session.advance_to(0, 1)["processed_events"] == 0
    assert session.offline_state_sha256() == before


def test_global_event_limit_at_exact_horizon_does_not_certify_result(native):
    data = fixture()
    data["options"]["max_events"] = 2
    session = native.NativeSession(data)
    result = session.result_at(.1)
    assert result["physical_clock"] == result["horizon"] == .1
    assert result["advance"]["status"] == "budget_exhausted"
    assert result["advance"]["horizon_complete"] is False
