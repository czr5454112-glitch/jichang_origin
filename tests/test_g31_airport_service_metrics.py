import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_service_metrics import (
    compare_completion_outcomes, backlog_relief, physical_progress_intervals)


def test_single_completion_preserves_censoring_but_identifies_direction():
    jobs = [{"business_bag_id": "x", "arrival": 0}]
    row = compare_completion_outcomes(jobs, {"x": 9}, {}, cutoff=10, include_rows=True)
    assert row["categories"]["exact_harmed"] == 0
    assert row["known_direction_harm"] == 1
    assert row["maximum_censored_delay_lower_bound_seconds"] == 1
    assert row["rows"][0]["candidate_completed_at"] is None
    reverse = compare_completion_outcomes(jobs, {}, {"x": 9}, cutoff=10)
    assert reverse["known_direction_improvement"] == 1
    assert reverse["unknown_incomplete_legacy"] == 1


def test_complete_population_separates_future_from_arrived_unfinished():
    jobs = [{"business_bag_id": str(n), "arrival": a}
            for n, a in enumerate((0, 0, 0, 0, 11))]
    row = compare_completion_outcomes(
        jobs, {"0": 3, "1": 5, "2": 7}, {"0": 4, "1": 4, "2": 7}, cutoff=10)
    assert row["categories"] == {
        "exact_harmed": 1, "exact_improved": 1, "exact_equal": 1,
        "reference_only_finished": 0, "candidate_only_finished": 0,
        "both_arrived_unfinished": 1, "both_not_yet_arrived": 1}
    assert row["population"] == 5
    assert row["unknown_incomplete_legacy"] == 2


def test_late_export_completion_is_not_falsely_inside_cutoff():
    jobs = [{"business_bag_id": "x", "arrival": 0}]
    row = compare_completion_outcomes(jobs, {"x": 9}, {"x": 12}, cutoff=10)
    assert row["known_direction_harm"] == 1
    with pytest.raises(ValueError, match="foreign_completion"):
        compare_completion_outcomes(jobs, {"alien": 1}, {}, cutoff=10)


def test_relief_and_no_progress_are_explanatory_not_new_cost():
    jobs = [{"business_bag_id": "x", "arrival": 2},
            {"business_bag_id": "future", "arrival": 11}]
    assert backlog_relief(jobs, {"x": 9}, start=0, end=10) == {
        "J0_bag_seconds": 8, "J_bag_seconds": 7, "relief_bag_seconds": 1,
        "frozen_J_redefined": False}
    row = physical_progress_intervals({"receipts": [
        {"event": "EDGE_EXIT", "time": 2}, {"event": "PROTOCOL", "time": 9}]},
        start=0, end=10)
    assert row["longest_no_edge_progress_interval"] == [2., 10.]
