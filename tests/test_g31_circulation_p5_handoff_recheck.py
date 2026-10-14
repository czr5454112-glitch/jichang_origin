import math

import pytest

from scripts.experiments.g31_ics_circulation import p5_handoff_recheck as recheck


def action(time=1.0, version=1, name="request"):
    return {"action_id": name, "candidates": [{"request": {"request_id": name,
        "expected_version": version, "tray_id": "T", "source": 1, "destination": 2,
        "earliest_departure": time, "owner_id": "A"}}]}


def test_nearby_physical_times_are_not_rounded_into_one_action():
    assert recheck.identity(action()) != recheck.identity(action(math.nextafter(1., 2.)))
    assert recheck.identity(action()) == recheck.identity(action(version=2, name="new_revision"))


def test_duplicate_physical_domain_is_rejected():
    with pytest.raises(ValueError, match="duplicate_domain_identity"):
        recheck.domain_index({"actions": [action(), action(version=2, name="duplicate")]})


def test_sub_epsilon_chronology_regression_is_recorded_exactly():
    before = 6.05
    after = math.nextafter(before, 0.)
    result = recheck.chronology({"receipts": [{"time": before}, {"time": after}]})
    assert result["receipts"]["regressions"] == [{"index": 1, "previous": before,
        "current": after, "previous_event": None, "current_event": None}]
    assert result["receipts"]["max_regression"] == before-after


def test_missing_business_metrics_remain_unknown():
    assert recheck.compared_metrics(None, None)["status"] == "unknown_missing_metrics"


def test_binary_identity_check_precedes_research_execution(tmp_path):
    baseline = tmp_path/"baseline"
    baseline.mkdir()
    recheck.frozen.write(baseline/"receipt.json", {"status": "executed_finite_diagnostic", "source_changed": []})
    binary = tmp_path/"native.pyd"
    binary.write_bytes(b"not-native")
    with pytest.raises(ValueError, match="unexpected_binary"):
        recheck.preflight(baseline, binary, "0"*64)
