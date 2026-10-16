from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation.finite_body_reference import CONTRACT, verify_schedule


def scene():
    return {"contract": CONTRACT, "short_link_semantics": "explicit_multisegment_body", "horizon": "1.3", "minimum_gap": 0,
        "segments": [
            {"segment_id": "source", "start": -2, "end": 0, "speed_limit": 2, "hardware_closed": False, "original_storage_count": 1},
            {"segment_id": "short", "start": 0, "end": ".6", "speed_limit": 2, "hardware_closed": False, "original_storage_count": 0},
            {"segment_id": "receiver", "start": ".6", "end": "2.6", "speed_limit": 2, "hardware_closed": False, "original_storage_count": 1}],
        "trays": [{"tray_id": "fixed-T", "length": 2, "front_motion": [[0,0],["1.3","2.6"]]}]}


def test_short_storage_zero_is_retained_and_tail_clears_one_second_after_front():
    data = scene(); saved = deepcopy(data); result = verify_schedule(data)
    assert result["status"] == "verified_reference_schedule" and data == saved
    row, = [r for r in result["reservations"] if r["segment_id"] == "short"]
    assert row == {"tray_id": "fixed-T", "segment_id": "short", "start": "0", "end": "13/10",
                   "active_at_horizon": False, "original_storage_count": 0}
    receiver, = [r for r in result["reservations"] if r["segment_id"] == "receiver"]
    assert receiver["start"] == "3/10" and receiver["active_at_horizon"]


def test_stopped_body_retains_all_spanned_segments_without_premature_release():
    data = scene(); data["horizon"] = 3
    data["trays"][0]["front_motion"] = [[0,0],[".3",".6"],[2,".6"],[3,"2.6"]]
    row, = [r for r in verify_schedule(data)["reservations"] if r["segment_id"] == "short"]
    assert row["end"] == "3"


def test_partial_horizon_does_not_claim_tail_release():
    data = scene(); data["horizon"] = ".3"; data["trays"][0]["front_motion"] = [[0,0],[".3",".6"]]
    row, = [r for r in verify_schedule(data)["reservations"] if r["segment_id"] == "short"]
    assert row["active_at_horizon"] and row["end"] == "3/10"


@pytest.mark.parametrize("kind", ["closed", "slow", "blocked_receiver", "unsupported"])
def test_reference_rejects_real_physical_conflicts(kind):
    data = scene()
    if kind == "closed": data["segments"][1]["hardware_closed"] = True
    elif kind == "slow": data["segments"][0]["speed_limit"] = 1
    elif kind == "blocked_receiver": data["trays"].append({"tray_id":"occupied", "length":2, "front_motion":[[0,"2.6"],["1.3","2.6"]]})
    else: data["trays"][0]["length"] = 3
    result = verify_schedule(data)
    assert result["status"] == "rejected" and result["witness"]["kind"] == {
        "closed":"hardware_closed", "slow":"body_spans_slower_drive", "blocked_receiver":"body_overlap_or_fifo_gap",
        "unsupported":"unsupported_body_outside_corridor"}[kind]


def test_collision_between_endpoint_states_is_detected_at_internal_motion_breakpoint():
    data = scene(); data["segments"][0]["start"] = -5
    data["segments"][0]["original_storage_count"] = 2
    data["trays"].append({"tray_id":"follower", "length":2, "front_motion":[[0,-3],[".5",0],["1.3",0]]})
    result = verify_schedule(data)
    assert result["status"] == "rejected" and result["witness"]["kind"] == "body_overlap_or_fifo_gap"


def test_directed_fifo_safe_follower_keeps_identity_and_gap():
    data = scene(); data["segments"][0]["start"] = "-4.2"; data["minimum_gap"] = ".2"
    data["segments"][0]["original_storage_count"] = 2
    data["trays"].append({"tray_id":"follower", "length":2, "front_motion":[[0,"-2.2"],["1.3",".4"]]})
    result = verify_schedule(data)
    assert result["status"] == "verified_reference_schedule"
    assert result["fixed_tray_ids"] == ["fixed-T", "follower"]


def test_positive_whole_body_storage_capacity_is_not_relaxed_by_spanning():
    data = scene(); data["segments"][0]["start"] = "-4.2"
    data["trays"].append({"tray_id":"follower", "length":2, "front_motion":[[0,"-2.2"],["1.3",".4"]]})
    result = verify_schedule(data)
    assert result["status"] == "rejected" and result["witness"]["kind"] == "whole_body_storage_count_exceeded"


@pytest.mark.parametrize("kind", ["implicit", "reverse", "duplicate", "nan", "broken_corridor"])
def test_invalid_or_undeclared_domain_fails_closed(kind):
    data = scene()
    if kind == "implicit": del data["short_link_semantics"]
    elif kind == "reverse": data["trays"][0]["front_motion"][-1][1] = -1
    elif kind == "duplicate": data["trays"].append(deepcopy(data["trays"][0]))
    elif kind == "nan": data["segments"][0]["speed_limit"] = "NaN"
    else: data["segments"][1]["start"] = ".1"
    with pytest.raises(ValueError, match="finite_body:"):
        verify_schedule(data)
