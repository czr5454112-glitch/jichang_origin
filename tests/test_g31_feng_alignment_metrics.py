from copy import deepcopy

import pytest

from scripts.experiments.g31_feng_alignment.metrics import audit, generator_releases


def case():
    canonical = [
        {"segment_id": "7:storage_in", "task_id": 7, "leg": "storage_in", "start": 1, "goal": 53,
         "original_entry_time": 10.0, "pass_time": 10.0, "std": 150.0},
        {"segment_id": "7:storage_out", "task_id": 7, "leg": "storage_out", "start": 53, "goal": 2,
         "original_entry_time": 10.0, "pass_time": 50.0, "std": 150.0},
    ]
    actual = [
        {"segment_id": "7:storage_in", "task_id": 7, "start": 1, "goal": 53,
         "completed": True, "finish": 30.0, "entered": 12.0, "released": 10.0},
        {"segment_id": "7:storage_out", "task_id": 7, "start": 53, "goal": 2,
         "completed": True, "finish": 100.0, "entered": 51.0, "released": 50.0},
    ]
    return canonical, actual


def test_segment_mean_and_business_final_delivery_have_distinct_denominators():
    canonical, actual = case()
    result, rows = audit(canonical, actual, horizon=200.0)
    assert result["full_population_segment_elapsed_from_canonical_pass_seconds"]["mean"] == 35.0
    assert result["full_population_segment_in_network_seconds"]["mean"] == 33.5
    assert result["full_population_observed_end_to_end_seconds"]["mean"] == 90.0
    assert rows[0]["sum_leg_elapsed_from_scheduled_pass_seconds"] == 70.0


def test_independent_ebs_segments_remain_offered_and_causality_is_diagnostic():
    canonical, actual = case()
    actual[0]["finish"] = 90.0
    result, rows = audit(canonical, actual, horizon=200.0)
    assert result["offered_transport_legs"] == 2
    assert result["completed_transport_legs"] == 2
    assert result["completed_business_bags"] == 1
    assert result["ebs_causality_violation_count"] == 1
    assert result["full_population_segment_elapsed_from_canonical_pass_seconds"] is not None
    assert result["full_population_ebs_causally_valid_end_to_end_seconds"] is None


def test_incomplete_segments_keep_full_denominator_without_a_survivor_mean_claim():
    canonical, actual = case()
    actual[1].update(completed=False, finish=None)
    result, rows = audit(canonical, actual, horizon=200.0)
    assert result["full_population_segment_elapsed_from_canonical_pass_seconds"] is None
    assert result["full_population_restricted_segment_elapsed_seconds"]["count"] == 2
    assert result["full_population_restricted_segment_elapsed_seconds"]["mean"] == 85.0
    assert result["deadline_misses_including_unfinished"] == 1


def test_duplicate_or_missing_segment_cannot_silently_change_the_population():
    canonical, actual = case()
    with pytest.raises(ValueError, match="missing or unexpected"):
        audit(canonical, actual[:1])
    with pytest.raises(ValueError, match="duplicate"):
        audit(canonical, actual+[deepcopy(actual[0])])


def test_generator_release_sensitivity_uses_release_not_successful_plan_epoch():
    canonical, actual = case()
    actual[0]["entered"] = 26.0
    actual[0]["released"] = 9.0
    releases = generator_releases(canonical, actual)
    assert releases["7:storage_in"] == 9.0
    assert canonical[0]["pass_time"] == 10.0
    with pytest.raises(ValueError, match="duplicate"):
        generator_releases(canonical, actual + [deepcopy(actual[0])])
    actual[0]["start"] = 999
    with pytest.raises(ValueError, match="identity/OD"):
        generator_releases(canonical, actual)


def test_lifecycle_order_is_checked_against_actual_release_not_fractional_schedule():
    canonical, actual = case()
    actual[0]["released"] = 9.0
    actual[0]["entered"] = 9.0
    audit(canonical, actual, horizon=200.0)
    actual[0]["finish"] = 8.0
    with pytest.raises(ValueError, match="finished before"):
        audit(canonical, actual, horizon=200.0)
