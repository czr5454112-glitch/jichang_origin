"""Converter/metric boundary fixtures only: no fitting or invented training run."""
import ast
from pathlib import Path

import pytest

from scripts.experiments.g31_ics_circulation import foundation_repeated_supervised as supervised


def prediction():
    return {'status': 'conditional_prediction', 'online_executable': False,
        'native_protection_certified': False, 'model_version': 'registered-model',
        'completion': {'done': 7., 'active': 15.}}


def target(proposal):
    return supervised.complete_prediction(proposal, identities=['done', 'active'], prefix={'done': 7.},
        jobs={'done': {'arrival': 1.}, 'active': {'arrival': 2.}}, now=10., horizon=40., model_version='registered-model')


def test_conditional_label_is_remaining_flow_not_actual_native_return():
    assert target(prediction()) == -5.
    assert 'not_actual_return_training_not_RL' in supervised.protocol()['scope']
    assert supervised.protocol()['label_kind'] == 'frozen_full_job_conditional_model_prediction_on_actual_native_delivered_evidence'


@pytest.mark.parametrize('mutate,reason', [
    (lambda p: p.update(status='unknown'), 'complete_conditional_prediction_without_authority'),
    (lambda p: p.update(online_executable=True), 'complete_conditional_prediction_without_authority'),
    (lambda p: p.update(native_protection_certified=True), 'complete_conditional_prediction_without_authority'),
    (lambda p: p.update(model_version='different'), 'complete_conditional_prediction_without_authority'),
    (lambda p: p['completion'].pop('done'), 'full_job_completion_vector_required'),
    (lambda p: p['completion'].update(extra=12.), 'full_job_completion_vector_required'),
    (lambda p: p['completion'].update(active=float('nan')), 'finite_number'),
    (lambda p: p['completion'].update(active=True), 'finite_number'),
    (lambda p: p['completion'].update(active=41.), 'finite_uncensored_predicted_completion'),
    (lambda p: p['completion'].update(active=9.), 'future_prediction_after_current_seed'),
    (lambda p: p['completion'].update(done=8.), 'preserved_observed_completed_prefix'),
])
def test_unknown_partial_censored_or_authoritative_predictions_cannot_label(mutate, reason):
    proposed = prediction()
    mutate(proposed)
    with pytest.raises(ValueError, match=reason):
        target(proposed)


def test_exact_parent_split_and_three_seed_protocol_is_fixed_before_source_read():
    protocol = supervised.protocol()
    assert protocol['train_cases'] == ['three_reuse_blocker_11_1']
    assert protocol['development_cases'] == ['four_reuse_blocker_12_5']
    assert protocol['formal_test_cases_reserved_not_read'] == ['three_reuse_blocker_12_1']
    assert protocol['seeds'] == [1701, 1702, 1703]
    assert protocol['native_branches'] == 0
    assert protocol['epochs'] == 200
    assert protocol['total_wall_seconds'] == 180.
    assert protocol['per_seed_wall_seconds'] == 45.
    assert protocol['deployment_seed_if_needed'] == 1701


def test_formal_test_case_rejected_before_any_file_read(monkeypatch):
    monkeypatch.setattr(Path, 'read_bytes', lambda self: pytest.fail('test data must not be opened'))
    monkeypatch.setattr(Path, 'read_text', lambda self, **kwargs: pytest.fail('test data must not be opened'))
    with pytest.raises(ValueError, match='formal_test_or_unregistered_source_forbidden'):
        supervised.closed_native_source('does-not-exist', case='three_reuse_blocker_12_1')


def test_wrong_split_cannot_relabel_same_parent_as_development():
    with pytest.raises(ValueError, match='registered_parent_split'):
        supervised.extract_rows({}, split='development', case=supervised.TRAIN_CASE, origin={})


def test_conditional_scoring_respects_guard_mask_and_ties(monkeypatch):
    monkeypatch.setattr(supervised.value, 'predict', lambda model, observations, actions: [100., 2., 1., 1.])
    rows = [{'observation': {}, 'action': {}, 'target_value': target,
        'parent_group': 'one-parent', 'source_decision_id': decision, 'action_id': action,
        'admissible_under_current_guard': allowed} for target, decision, action, allowed in (
            (-10., 'd1', 'rejected', False), (3., 'd1', 'choice1', True), (2., 'd1', 'choice2', True),
            (1., 'd2', 'only', True))]
    result = supervised.score({}, rows)
    assert result['independent_parent_groups'] == 1
    assert result['guard_admissible_multiple_action_decisions'] == 1
    assert result['guard_admissible_teacher_differentiated_decisions'] == 1
    assert result['guard_admissible_teacher_all_tied_decisions'] == 0
    assert result['teacher_best_match_fraction'] == 1.
    assert result['mean_teacher_regret'] == 0.
    assert result['native_policy_improvement_measured'] is False


def test_all_tied_admissible_teacher_has_no_differentiated_choice_evidence(monkeypatch):
    monkeypatch.setattr(supervised.value, 'predict', lambda model, observations, actions: [1., 2., 100.])
    rows = [{'observation': {}, 'action': {}, 'target_value': target,
        'parent_group': 'one-parent', 'source_decision_id': 'same-decision', 'action_id': action,
        'admissible_under_current_guard': allowed} for target, action, allowed in (
            (3., 'default', True), (3., 'prefer3', True), (1., 'rejected8', False))]
    result = supervised.score({}, rows)
    assert result['teacher_best_match_fraction'] == 1.
    assert result['guard_admissible_teacher_differentiated_decisions'] == 0
    assert result['guard_admissible_teacher_all_tied_decisions'] == 1
    assert result['differentiated_teacher_best_match_fraction'] is None
    assert result['differentiated_mean_teacher_regret'] is None


def test_converter_has_no_native_or_conditional_engine_imports():
    tree = ast.parse(Path(supervised.__file__).read_text(encoding='utf8'))
    imports = [node.module or '' for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in node.names]
    assert not any(any(token in name for token in ('foundation_repeated_native', 'foundation_repeated_domain',
        'foundation_repeated_campaign', 'native_host', 'foundation_flight')) for name in imports)
