"""Independent per-bag service audit preserves censoring and physical pairing."""
from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation.foundation_airport_terminal_service_audit import (
    per_bag_service, physical_comparison_contract, _execution_summary,
)


def spec(identity, arrival=0., deadline=50.):
    return dict(business_bag_id=identity, arrival=arrival, deadline=deadline)


def test_same_input_population_keeps_single_sided_completions_and_future_bags():
    specs = [spec("late"), spec("lost"), spec("rescued"), spec("both"), spec("future", 150., 200.)]
    result = per_bag_service(specs, dict(late=60., lost=40.), dict(late=75., rescued=70.), cutoff=100.)
    assert len(result["per_bag"]) == 5
    rows = {r["business_bag_id"]: r for r in result["per_bag"]}
    assert rows["late"]["exact_lateness_delta_seconds"] == 15.
    assert rows["lost"]["candidate"]["completed_at"] is None
    assert rows["lost"]["delay_lower_bound_seconds"] == 60.
    assert rows["lost"]["lateness_harm_lower_bound_seconds"] == 50.
    assert rows["rescued"]["lateness_improvement_lower_bound_seconds"] == 30.
    assert rows["both"]["lateness_direction"] == "unknown_censored"
    assert rows["future"]["reference"]["lateness_lower_bound_seconds"] is None
    assert result["completion_direction"]["known_direction_harm"] == 2
    assert result["known_lateness_harm"] == 2
    assert not result["completion_direction"]["strict_per_job_nonharm_certified"]


def test_self_comparison_does_not_certify_unknown_completions_equal():
    result = per_bag_service([spec("done"), spec("pending")], {"done": 40.}, {"done": 40.}, cutoff=100.)
    assert result["completion_direction"]["categories"]["exact_equal"] == 1
    assert result["completion_direction"]["categories"]["both_arrived_unfinished"] == 1
    assert result["lateness_direction_counts"]["unknown_censored"] == 1
    assert result["known_lateness_harm"] == 0


def test_before_deadline_single_sided_completion_has_unknown_eventual_lateness():
    result = per_bag_service([spec("bag", deadline=120.)], {"bag": 80.}, {}, cutoff=100.)
    row = result["per_bag"][0]
    assert row["category"] == "reference_only_finished"
    assert row["lateness_direction"] == "unknown_censored"
    assert result["known_lateness_harm"] == 0


def test_lateness_at_exact_cutoff_keeps_zero_lower_bound_known_direction():
    result = per_bag_service([spec("bag", deadline=100.)], {"bag": 100.}, {}, cutoff=100.)
    row = result["per_bag"][0]
    assert row["lateness_harm_lower_bound_seconds"] == 0.
    assert result["known_lateness_harm"] == 1
    assert row["candidate"]["completed_at"] is None


@pytest.mark.parametrize("field", ["input", "source_bundle", "binary", "controller", "horizon"])
def test_pairing_rejects_changed_physical_execution_contract(field):
    plan = dict(parent={}, input={}, source_bundle={}, binary={}, controller={}, activation=0.,
                horizon=100., supply_mode="committed_only", projection_horizon_seconds=600., cost_scope="full")
    other = deepcopy(plan)
    other[field] = "changed"
    with pytest.raises(ValueError, match="different_comparison_contract"):
        physical_comparison_contract(plan, other)


def test_priority_native_failures_are_visible_without_rewriting_existing_policy_gate():
    trajectory = dict(rows=[dict(requested_action=dict(kind="noop"), physical_failure=False)])
    result = _execution_summary(trajectory, dict(transfers=[dict(status="failed"), dict(status="received")]))
    assert result["selected_policy_physical_failures"] == 0
    assert result["all_native_failed_or_rejected_or_expired"] == 1
