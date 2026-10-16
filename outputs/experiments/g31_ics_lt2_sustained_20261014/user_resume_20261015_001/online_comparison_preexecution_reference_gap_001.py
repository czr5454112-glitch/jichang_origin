"""Data-only, matched prospective comparison; never native authority.

The enclosing saved verifier must reconstruct each row from its raw evidence,
validate the common source/information/budget contract, and bind run closure.
This module does arithmetic over those rows. Neither a successful comparison
nor a caller-supplied status establishes those external facts.
"""
from __future__ import annotations

import math

SCHEMA = 'g31.live_obligation.online_method_comparison.v1'
CASES = ('mechanism', 'no_overlap', 'insufficient_advance')
ARMS = ('incumbent', 'fixed_initial_MPC', 'later_default_MPC',
        'coordinate_strict', 'coordinate_plateau', 'pair_repair', 'finite_MPC')
JOBS = ('loaded', 'receiver', 'reuse1', 'reuse2', 'blocker')
RESTRICTED = ('fixed_initial_MPC', 'later_default_MPC')
REQUIRED_FLAGS = ('business_complete', 'common_horizon_complete',
    'required_transfer_lineages_received', 'all_routes_updated',
    'chosen_routes_match_executed_edges', 'blocker_actual_path1to9',
    'same_L_two_returns_and_two_reloads', 'stock_preserved',
    'recovery_decisions_valid', 'all_required_inputs_verified',
    'selected_actions_executed')


def _require(ok, label):
    if not ok:
        raise ValueError('online_method_comparison:' + label)


def _completion(row, case, arm):
    """Unknown is retained, including physical success with missing evidence."""
    reasons = []
    if type(row) is not dict:
        return None, ['row_not_dict']
    if row.get('case') != case or row.get('method') != arm or row.get('fault') is not None:
        reasons.append('row_specification')
    if row.get('status') != 'assessed':
        reasons.append('row_not_assessed')
    if row.get('saved_replay') != 'passed':
        reasons.append('saved_replay_not_passed')
    summary = row.get('summary')
    if type(summary) is not dict:
        return None, reasons + ['summary_not_dict']
    if summary.get('status') != 'assessed':
        reasons.append('summary_not_assessed')
    for key in REQUIRED_FLAGS:
        if summary.get(key) is not True:
            reasons.append('missing_true:' + key)
    if type(summary.get('audit')) is not dict or summary['audit'].get('status') != 'passed':
        reasons.append('physical_audit_not_passed')
    completion = summary.get('completion')
    if type(completion) is not dict or set(completion) != set(JOBS):
        return None, reasons + ['five_job_domain']
    if any(type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 40
           for value in completion.values()):
        return None, reasons + ['invalid_terminal_time']
    # Return a new dict in the exact objective order used by the shared selector.
    return (None if reasons else {job: completion[job] for job in JOBS}), reasons


def _pair(candidate, reference):
    if candidate is None or reference is None:
        return {'status': 'unknown', 'per_job_delta': None,
                'strict_observed_nonregression': None, 'observed_improvement': None,
                'completion_sum_delta': None}
    delta = {job: candidate[job] - reference[job] for job in JOBS}
    protected = all(candidate[job] <= reference[job] for job in JOBS)
    return {'status': 'compared', 'per_job_delta': delta,
        'strict_observed_nonregression': protected,
        'observed_improvement': protected and any(candidate[job] < reference[job] for job in JOBS),
        'completion_sum_delta': sum(candidate[job] for job in JOBS) - sum(reference[job] for job in JOBS)}


def compare(rows, *, run_acceptance_status):
    """Keep every declared branch; never choose a best among incomplete arms.

All result fields concern this finite observed campaign, conditional on its
separate saved verification. Exact-zero per-job protection is not an epsilon,
mean, percentile or sum-only test. Ties do not establish joint advantage.
"""
    expected = {case + '/' + arm for case in CASES for arm in ARMS}
    _require(type(rows) is dict and set(rows) == expected, 'complete_declared21_domain')
    closed = run_acceptance_status == 'closed_run_acceptance_passed'
    result = {'schema': SCHEMA, 'status': 'unknown_incomplete_campaign',
        'branch_denominator': 21, 'run_acceptance_status': run_acceptance_status,
        'observed_known_branches': 0, 'unknown_branch_keys': [], 'cases': {},
        'strict_protection_tolerance': 0., 'objective_job_order': list(JOBS),
        'fair_information_and_budget_certified_by_this_function': False,
        'rolling_reestimation_certified': False, 'solver_novelty_claim': False,
        'original_all_day_effectiveness_certified': False,
        'complete_request_100ms_certified': False,
        'scope': 'Matched finite observed outcomes only, conditional on independent raw/source/contract verification. No new authority, robust guarantee, hidden-state coverage or general effectiveness claim.'}
    for case in CASES:
        values, reasons = {}, {}
        for arm in ARMS:
            value, why = _completion(rows[case + '/' + arm], case, arm)
            if not closed:
                why = why + ['run_acceptance_not_closed']
                value = None
            values[arm], reasons[arm] = value, why
            if value is None:
                result['unknown_branch_keys'].append(case + '/' + arm)
            else:
                result['observed_known_branches'] += 1
        comparisons = {arm: _pair(values[arm], values['incumbent']) for arm in ARMS}
        candidate = values['finite_MPC']
        against = {arm: _pair(candidate, values[arm]) for arm in RESTRICTED}
        references_protected = all(comparisons[arm]['strict_observed_nonregression'] is True
                                   for arm in ('finite_MPC', *RESTRICTED))
        complete = all(value is not None for value in values.values())
        advantage = None
        if complete and references_protected:
            # Objective superiority under the same deployment protection rule.
            # Individual jobs need not improve versus each restricted optimum;
            # their actual deltas are retained above for inspection.
            advantage = all(against[arm]['completion_sum_delta'] < 0 for arm in RESTRICTED)
        result['cases'][case] = {
            'status': 'all7_observed' if complete else 'unknown_incomplete_case',
            'unknown_reasons': reasons,
            'completion_by_method': values,
            'versus_incumbent': comparisons,
            'finite_MPC_versus_restricted': against,
            'all_three_reference_methods_protected': references_protected if complete else None,
            'finite_MPC_objective_advantage_over_both_restrictions': advantage,
            'ordinary_methods_vs_finite_MPC': {arm: _pair(values[arm], candidate)
                for arm in ('coordinate_strict', 'coordinate_plateau', 'pair_repair')},
        }
    if not result['unknown_branch_keys']:
        result['status'] = 'complete21_observed_comparisons'
    return result
