"""Pure preparation checks: no native session or binary is imported."""
from copy import deepcopy

import pytest

from scripts.experiments.g31_ics_circulation import foundation_airport_admission_campaign as prior
from scripts.experiments.g31_ics_circulation import foundation_airport_event_budget_campaign as candidate
from scripts.experiments.g31_ics_circulation import foundation_airport_feasible_domain as domain


@pytest.fixture(scope='module')
def base_input():
    return domain.build_full_input()[0]


def test_new_resource_budget_is_the_only_change_to_receiver_policy_input(base_input):
    old = prior.apply_policy(base_input)
    new = candidate.apply_policy(base_input)
    expected = deepcopy(old)
    expected['options']['max_events'] = 500000
    assert new == expected
    assert len(new['jobs']) == 28506 and new['jobs'] == old['jobs']
    assert new['node_contracts'] == old['node_contracts']
    assert new['trays'] == old['trays'] and len(new['trays']) == 22
    assert domain.digest(new) == candidate.POLICY_INPUT_SHA
    assert domain.digest({k:v for k,v in new.items() if k != 'jobs'}) == candidate.POLICY_NONBUSINESS_SHA
    assert base_input['options']['max_events'] == 100000


def test_control_window_policy_and_per_call_limits_preserved():
    assert candidate.legacy is prior.legacy
    assert candidate.BRANCHES == prior.BRANCHES
    assert candidate.policy_contract() == prior.policy_contract()
    assert (candidate.HARD_SECONDS,candidate.SOFT_SECONDS) == (300,240)
    assert candidate.legacy.WARMUP == 57600
    assert list(candidate.legacy.BOUNDARIES) == [57600,58200,58800,59400]
    assert candidate.PER_ADVANCE_EVENT_BUDGET == 100000
    assert candidate.resource_contract()['physical_or_business_constraint_changed'] is False
    assert candidate.resource_contract()['automatic_retries'] == 0


def test_budget_justification_covers_observed_growth():
    projected = 79289 + 30179 * ((59400-28800)/3600)
    assert 300000 < projected < candidate.GLOBAL_EVENT_BUDGET == 500000


def test_new_overlay_rejects_unregistered_base_resources(base_input):
    altered = deepcopy(base_input)
    altered['options']['max_events'] = 500000
    with pytest.raises(ValueError,match='base_business_input'):
        candidate.apply_policy(altered)


def test_old_censored_calibration_is_not_a_new_C10_reference():
    path = prior.ROOT / 'outputs/experiments/g31_ics_sustained_flight_20261019/cycle_001/C00_receiver_admission_001/receipt.json'
    with pytest.raises(ValueError,match='new_domain_C00_reference'):
        candidate.calibration_reference(path)
