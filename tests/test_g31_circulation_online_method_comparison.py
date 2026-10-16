"""Meaningful failure/denominator/protection cases for data-only comparisons."""
import copy
import math

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_online_method_comparison as subject


def rows():
    result = {case + '/' + arm: {'case': case, 'method': arm, 'fault': None,
        'status': 'assessed', 'saved_replay': 'passed',
        'summary': {'status': 'assessed', 'audit': {'status': 'passed'},
                    'completion': dict.fromkeys(subject.JOBS, 10.),
                    **dict.fromkeys(subject.REQUIRED_FLAGS, True)}}
        for case in subject.CASES for arm in subject.ARMS}
    for case in subject.CASES:
        for arm, restriction in (('finite_MPC', 'all'), ('fixed_initial_MPC', 'fixed_initial'),
                                 ('later_default_MPC', 'later_default')):
            count = 32 if arm == 'finite_MPC' else 16
            result[case + '/' + arm]['initial_selection_replay'] = {owner: {
                'status': 'passed_saved_selection_replay', 'owner': owner,
                'method': 'finite_MPC', 'restriction': restriction, 'full_reference_known': True,
                'declared_candidate_denominator': 32, 'selection_budget': 32,
                'allowed_candidate_count': count, 'known_allowed_candidate_count': count}
                for owner in ('A', 'B')}
    return result


def compare(data):
    return subject.compare(data, run_acceptance_status='closed_run_acceptance_passed')


def test_all_ties_complete_without_joint_advantage_or_novelty():
    data = rows(); before = copy.deepcopy(data); result = compare(data)
    assert data == before and result['observed_known_branches'] == 21
    assert result['status'] == 'complete21_observed_comparisons'
    for case in result['cases'].values():
        assert case['finite_MPC_objective_advantage_over_both_restrictions'] is False
        assert case['versus_incumbent']['finite_MPC']['observed_improvement'] is False
    assert result['solver_novelty_claim'] is False
    assert result['complete_request_100ms_certified'] is False


def test_joint_objective_gain_and_ordinary_pair_match_are_both_visible():
    data = rows()
    for arm in ('finite_MPC', 'pair_repair'):
        data['mechanism/' + arm]['summary']['completion']['loaded'] = 9.
    result = compare(data)['cases']['mechanism']
    assert result['finite_MPC_objective_advantage_over_both_restrictions'] is True
    assert result['ordinary_methods_vs_finite_MPC']['pair_repair']['completion_sum_delta'] == 0.
    assert result['versus_incumbent']['finite_MPC']['observed_improvement'] is True


def test_smaller_sum_cannot_hide_one_job_regression_even_tiny():
    data = rows(); values = data['mechanism/finite_MPC']['summary']['completion']
    values['loaded'] = 1.; values['blocker'] = 10. + 1e-12
    result = compare(data)['cases']['mechanism']
    pair = result['versus_incumbent']['finite_MPC']
    assert pair['completion_sum_delta'] < 0 and pair['strict_observed_nonregression'] is False
    assert pair['observed_improvement'] is False
    assert result['finite_MPC_objective_advantage_over_both_restrictions'] is None


@pytest.mark.parametrize('bad', [None, True, '10', math.nan, math.inf, -1., 40.000001])
def test_bad_terminal_value_keeps_branch_unknown(bad):
    data = rows(); data['mechanism/finite_MPC']['summary']['completion']['loaded'] = bad
    result = compare(data)
    assert result['observed_known_branches'] == 20
    assert result['unknown_branch_keys'] == ['mechanism/finite_MPC']
    assert result['cases']['mechanism']['finite_MPC_objective_advantage_over_both_restrictions'] is None


@pytest.mark.parametrize('field', subject.REQUIRED_FLAGS)
def test_missing_required_execution_or_information_flag_not_success(field):
    data = rows(); data['mechanism/pair_repair']['summary'][field] = False
    result = compare(data)
    assert result['status'] == 'unknown_incomplete_campaign'
    assert result['cases']['mechanism']['status'] == 'unknown_incomplete_case'
    assert result['cases']['mechanism']['finite_MPC_objective_advantage_over_both_restrictions'] is None


@pytest.mark.parametrize('mutation', ['missing_job', 'extra_job', 'failed_audit', 'partial_replay',
    'unknown_status', 'wrong_arm', 'wrong_case', 'fault', 'true_integer'])
def test_incomplete_or_misassociated_reference_never_becomes_best_family(mutation):
    data = rows(); row = data['mechanism/fixed_initial_MPC']; summary = row['summary']
    if mutation == 'missing_job': del summary['completion']['blocker']
    elif mutation == 'extra_job': summary['completion']['unregistered'] = 0.
    elif mutation == 'failed_audit': summary['audit']['status'] = 'failed'
    elif mutation == 'partial_replay': row['saved_replay'] = 'partial_only_unknown'
    elif mutation == 'unknown_status': row['status'] = 'unknown_failed'
    elif mutation == 'wrong_arm': row['method'] = 'finite_MPC'
    elif mutation == 'wrong_case': row['case'] = 'no_overlap'
    elif mutation == 'fault': row['fault'] = 'drop'
    elif mutation == 'true_integer': summary['business_complete'] = 1
    result = compare(data)['cases']['mechanism']
    assert result['completion_by_method']['fixed_initial_MPC'] is None
    assert result['finite_MPC_versus_restricted']['fixed_initial_MPC']['status'] == 'unknown'
    assert result['finite_MPC_objective_advantage_over_both_restrictions'] is None


def test_incomplete_campaign_does_not_erase_unrelated_complete_case():
    data = rows(); data['mechanism/incumbent']['status'] = 'unknown_failed'
    result = compare(data)
    assert result['status'] == 'unknown_incomplete_campaign'
    assert result['cases']['no_overlap']['status'] == 'all7_observed'
    assert all(pair['status'] == 'unknown' for pair in result['cases']['mechanism']['versus_incumbent'].values())


@pytest.mark.parametrize('mutation', ['missing_branch', 'extra_branch'])
def test_branch_denominator_cannot_change(mutation):
    data = rows()
    if mutation == 'missing_branch': del data['mechanism/pair_repair']
    else: data['new/finite_MPC'] = {}
    with pytest.raises(ValueError, match='complete_declared21_domain'):
        compare(data)


def test_unclosed_run_invalidates_all_outcomes():
    result = subject.compare(rows(), run_acceptance_status='invalidated_runtime_evidence')
    assert result['observed_known_branches'] == 0 and len(result['unknown_branch_keys']) == 21


def test_result_mutation_does_not_change_input():
    data = rows(); result = compare(data)
    result['cases']['mechanism']['completion_by_method']['finite_MPC']['loaded'] = -100.
    assert data['mechanism/finite_MPC']['summary']['completion']['loaded'] == 10.


@pytest.mark.parametrize('arm', ['finite_MPC', 'fixed_initial_MPC', 'later_default_MPC'])
@pytest.mark.parametrize('mutation', ['no_record', 'missing_owner', 'unknown_forecast',
    'incomplete_allowed', 'wrong_restriction', 'wrong_owner', 'boolean_count'])
def test_physical_success_does_not_complete_missing_reference_forecasts(arm, mutation):
    data = rows(); data['mechanism/finite_MPC']['summary']['completion']['loaded'] = 9.
    row = data['mechanism/' + arm]; records = row['initial_selection_replay']
    if mutation == 'no_record': del row['initial_selection_replay']
    elif mutation == 'missing_owner': del records['B']
    elif mutation == 'unknown_forecast': records['B']['full_reference_known'] = False
    elif mutation == 'incomplete_allowed': records['A']['known_allowed_candidate_count'] -= 1
    elif mutation == 'wrong_restriction': records['A']['restriction'] = 'fixed_other'
    elif mutation == 'wrong_owner': records['A']['owner'] = 'B'
    elif mutation == 'boolean_count': records['A']['selection_budget'] = True
    result = compare(data)
    assert result['observed_known_branches'] == 21
    case = result['cases']['mechanism']
    assert case['versus_incumbent']['finite_MPC']['observed_improvement'] is True
    assert case['conditional_forecast_reference_complete'][arm] is False
    assert case['finite_MPC_objective_advantage_over_both_restrictions'] is None
