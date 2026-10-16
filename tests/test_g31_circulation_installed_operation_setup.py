from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation.audit_installed_operation_setup import corrected_bounds


def fixture():
    raw = {"setup_intervals": [{"start_ns": 0, "end_ns": 10}, {"start_ns": 110, "end_ns": 120}],
           "diagnostic_capture_setup_ns": 90, "ended_ns": 200,
           "roots": {"parent": {"start_ns": 130, "end_ns": 200},
                     "child": {"start_ns": 150, "end_ns": 180}}}
    report = {"roots": {"parent": {"known_prefix_upper_ns": 90, "complete_compute_upper_ns": 90, "job_scope_verified": True},
                        "child": {"known_prefix_upper_ns": 50, "complete_compute_upper_ns": 50, "job_scope_verified": True}}}
    return raw, report


def test_all_gaps_and_shared_setup_charged_in_full():
    raw, report = fixture()
    result = corrected_bounds(raw, report, 1.)
    assert result["setup_gap_ns"] == 20
    assert result["roots"]["parent"]["initialized_host_service_upper_ns"] == 110
    assert result["roots"]["child"]["initialized_host_service_upper_ns"] == 70
    assert result["roots"]["parent"]["all_case_setup_wall_upper_ns"] == 200
    assert all(r["whole_worker_process_upper_ns"] == 1_000_000_000 for r in result["roots"].values())


def test_open_root_never_gains_complete_total():
    raw, report = fixture()
    raw["roots"]["parent"]["end_ns"] = None
    report["roots"]["parent"]["complete_compute_upper_ns"] = None
    result = corrected_bounds(raw, report, 1.)["roots"]["parent"]
    assert result["initialized_host_service_upper_ns"] is None
    assert result["all_case_setup_wall_upper_ns"] is None
    assert result["whole_worker_process_upper_ns"] is None
    assert result["known_prefix_with_setup_gaps_ns"] == 110


@pytest.mark.parametrize("mutation", [
    lambda r, p: r.update(diagnostic_capture_setup_ns=101),
    lambda r, p: r["setup_intervals"][1].update(end_ns=140),
    lambda r, p: r["setup_intervals"][0].update(start_ns=True),
    lambda r, p: p["roots"]["parent"].update(known_prefix_upper_ns=0),
    lambda r, p: p["roots"].pop("child"),
    lambda r, p: p["roots"]["parent"].update(complete_compute_upper_ns=None),
])
def test_tampered_gap_or_coverage_fails_closed(mutation):
    raw, report = fixture()
    mutation(raw, report)
    with pytest.raises(ValueError): corrected_bounds(raw, report, 1.)


@pytest.mark.parametrize("wall", [0, -1, float("nan"), float("inf"), True, 1e-8])
def test_invalid_or_too_short_process_envelope_rejected(wall):
    raw, report = fixture()
    with pytest.raises(ValueError): corrected_bounds(raw, report, wall)


def test_process_seconds_convert_upward_for_conservative_bound():
    raw, report = fixture()
    result = corrected_bounds(raw, report, .0000010001)
    assert result["roots"]["parent"]["whole_worker_process_upper_ns"] == 1001
