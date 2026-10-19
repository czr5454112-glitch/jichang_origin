import copy
import json
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_component_compatibility as subject
from scripts.experiments.g31_ics_circulation import public_live_obligation_projection as construction


def selection(owner, queried=None):
    actions = construction.actions()
    rows = [{'candidate_index': index, 'action': action, 'status': 'conditional_forecast',
        'completion': {job: float(10 if index == 4 else 9 if index == 12 else 8 if index == 25 else 11)
            for job in subject.JOBS}} for index, action in enumerate(actions)]
    return {'selected_index': 25, 'selected_action': actions[25],
        'accounting': {'query_indices': list(range(32)) if queried is None else queried},
        'allowed_candidate_indices': list(range(32)),
        'provider_evidence': {'owner': owner, 'rows': rows}}


def test_12_25_mixture_is_not_promoted_and_nondefault12_survives():
    proposed = {owner: selection(owner) for owner in ('A', 'B')}
    proposed['A']['selected_index'] = 12
    result = {owner: subject.select_component(proposed[owner], owner, 4) for owner in ('A', 'B')}
    assert result['A']['selected_index'] == 4
    assert result['B']['original_selected_index'] == 25
    assert result['B']['selected_index'] == 12
    mixed = {field: result[owner]['selected_action'][field]
        for owner, fields in subject.OWNER_FIELDS.items() for field in fields}
    assert mixed == construction.actions()[12]
    assert mixed != construction.actions()[9]
    assert result['B']['protected_indices_excluded_by_public_contract'] == [25]
    assert not result['B']['native_protection_certified']
    assert not result['B']['hard_reservation_granted']


def test_unqueried_safe_candidate_cannot_be_selected_by_filter():
    result = subject.select_component(selection('B', [4, 25]), 'B', 4)
    assert result['selected_index'] == 4
    assert result['additional_model_predictions'] == result['additional_selector_queries'] == 0


def test_unknown_baseline_and_unknown_candidate_are_not_success():
    proposed = selection('B')
    proposed['provider_evidence']['rows'][12]['status'] = 'unknown_projection'
    assert subject.select_component(proposed, 'B', 4)['selected_index'] == 4
    proposed['provider_evidence']['rows'][4]['completion'] = None
    result = subject.select_component(proposed, 'B', 4)
    assert result['selected_action'] is None
    assert result['status'] == 'unknown_no_compatible_component'


def test_private_peer_table_and_changed_incumbent_are_rejected():
    with pytest.raises(ValueError, match='own_complete_domain'):
        subject.select_component(selection('A'), 'B', 4)
    with pytest.raises(ValueError, match='frozen_incumbent04'):
        subject.select_component(selection('B'), 'B', 0)


def test_submillisecond_damage_is_rejected_without_tolerance():
    proposed = selection('B')
    proposed['provider_evidence']['rows'][12]['completion']['reuse2'] = 10.001
    assert subject.select_component(proposed, 'B', 4)['selected_index'] == 4


def test_allowed_family_and_result_aliases_are_preserved():
    proposed = selection('B')
    original = copy.deepcopy(proposed)
    proposed['allowed_candidate_indices'] = [4]
    result = subject.select_component(proposed, 'B', 4)
    result['selected_action']['empty_departure'] = 99
    assert proposed['provider_evidence'] == original['provider_evidence']
    assert result['selected_index'] == 4


def test_saved_native_counterexample_has_two_strict_reuse_regressions():
    evidence = json.loads((Path(__file__).parent / 'fixtures/g31_component_counterexample.json').read_text())
    saved = evidence['rows']
    mixed = {field: saved[str(index)]['action'][field]
        for owner, index in (('A', 12), ('B', 25)) for field in subject.OWNER_FIELDS[owner]}
    assert mixed == saved['9']['action']
    damaged = [job for job, actual, baseline in zip(evidence['job_order'], saved['9']['completion'],
        saved['4']['completion'], strict=True) if actual > baseline]
    assert damaged == ['reuse1', 'reuse2']
    proposed = selection('B')
    for row in proposed['provider_evidence']['rows']:
        row.update(status='unknown_projection', completion=None)
    for key, value in saved.items():
        row = proposed['provider_evidence']['rows'][int(key)]
        assert row['action'] == value['action']
        row.update(status='conditional_forecast', completion=dict(zip(evidence['job_order'], value['completion'], strict=True)))
    result = subject.select_component(proposed, 'B', 4)
    assert result['selected_index'] == 12 and 9 not in result['eligible_queried_indices']
    assert not result['native_protection_certified']
