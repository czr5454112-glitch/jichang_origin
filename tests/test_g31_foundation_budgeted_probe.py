import copy
import json
import math

import pytest

from scripts.experiments.g31_ics_circulation import foundation_budgeted_probe as probe


@pytest.fixture
def comparison():
    actions = probe.provider.teacher.future.core.lazy.original.physics.previous.actions()
    rows = [{'candidate_index': index, 'action': action, 'status': 'conditional_forecast',
        'completion': {job: 10. for job in probe.provider.teacher.JOBS},
        'prediction': {'routes': [index, {'suffix': action['later_action']}]}} for index, action in enumerate(actions)]
    requested = [4, 0]
    budgeted = copy.deepcopy(rows)
    for index, row in enumerate(budgeted):
        if index not in requested:
            row.update(status='not_requested', completion=None)
            row.pop('prediction')
    report = {'owner': 'B', 'initial_public_sha256': 'current-public', 'actual_collection_at': .11,
        'requested_indices': requested, 'candidate_budget': 2, 'rows': budgeted,
        'counts': {'future_resumes': 2}, 'source_binding': {'close_completed': True,
            'before_close': {'proof_binding': {'proof_uses': 5}}},
        'selection': {'selected_index': 4, 'current_revalidation': {'status': 'fresh_local_component_proposal'}},
        'timing': {'exclusive_outer_stage_ns': {'guarded_prefix_clone_and_rollout': 100}}}
    measured = {'report': report, 'compute_wall_ms': 2., 'seal_wall_ms': .1}
    evidence = {'owner': 'B', 'initial_public_sha256': 'current-public', 'actual_collection_at': .11,
        'rows': rows, 'counts': {'future_resumes': 32}}
    teacher = {'selection': {'provider_evidence': evidence,
        'accounting': {'provider_measured_through_seal_seconds': .01}}}
    return measured, teacher


def test_exact_saved_parity_does_not_grant_authority(comparison):
    result = probe.compare_variant(*comparison)
    assert result['all_requested_prediction_parity']
    assert result['unrequested_rows_not_evaluated']
    assert result['component_compatible_regret_s'] == 0
    assert result['selected_strictly_protected_and_component_compatible']
    assert not result['native_authority']
    assert not result['strict_speed_causal_claim']
    assert result['costs']['budgeted_export_cpu_ms'] is None


@pytest.mark.parametrize('field,value', [('owner', 'A'), ('initial_public_sha256', 'old'),
    ('actual_collection_at', .1)])
def test_no_old_or_other_owner_context_comparison(comparison, field, value):
    comparison[0]['report'][field] = value
    result = probe.compare_variant(*comparison)
    assert not result['same_context']
    assert not result['full32_reference_known']
    assert result['component_compatible_regret_s'] is None


def test_full_prediction_not_only_endpoint_comparison(comparison):
    comparison[0]['report']['rows'][0]['prediction']['routes'].append('different')
    result = probe.compare_variant(*comparison)
    assert not result['all_requested_prediction_parity']
    assert result['conditional_protected_regret_s'] is None


@pytest.mark.parametrize('original,changed', [(1, True), (0, False), (1, 1.), (0., -0.)])
def test_strict_prediction_encoding_rejects_python_numeric_equality(comparison, original, changed):
    measured, teacher = comparison
    measured['report']['rows'][0]['prediction']['typed_field'] = changed
    teacher['selection']['provider_evidence']['rows'][0]['prediction']['typed_field'] = original
    assert measured['report']['rows'][0]['prediction'] == teacher['selection']['provider_evidence']['rows'][0]['prediction']
    result = probe.compare_variant(*comparison)
    row = next(row for row in result['comparisons'] if row['candidate_index'] == 0)
    assert not row['prediction_exact']
    assert row['budgeted_prediction_sha256'] != row['teacher_prediction_sha256']
    assert not result['all_requested_prediction_parity']
    assert result['conditional_protected_regret_s'] is None


def test_canonical_strict_comparison_ignores_dictionary_insertion_order():
    assert probe.strict_equal({'first': 1, 'second': [True, 1.]}, {'second': [True, 1.], 'first': 1})


def test_unknown_teacher_not_hidden_as_complete_optimum(comparison):
    comparison[1]['selection']['provider_evidence']['rows'][31].update(status='unknown', completion=None)
    result = probe.compare_variant(*comparison)
    assert result['all_requested_prediction_parity']
    assert not result['full32_reference_known']
    assert result['conditional_optimum_retained'] is None


def test_unrequested_prediction_is_reported(comparison):
    comparison[0]['report']['rows'][31]['prediction'] = {'unexpected': True}
    assert not probe.compare_variant(*comparison)['unrequested_rows_not_evaluated']


def test_close_failure_is_not_complete(comparison):
    comparison[0]['report']['source_binding']['close_completed'] = False
    assert probe.compare_variant(*comparison)['status'] == 'unknown_or_mismatched_predictions'


def test_one_ulp_harm_never_counts_as_protected(comparison):
    measured, teacher = comparison
    measured['report']['selection']['selected_index'] = 0
    for rows in (measured['report']['rows'], teacher['selection']['provider_evidence']['rows']):
        rows[0]['completion']['loaded'] = math.nextafter(10., math.inf)
    result = probe.compare_variant(*comparison)
    assert result['all_requested_prediction_parity']
    assert not result['selected_strictly_protected_and_component_compatible']
    assert result['component_compatible_regret_s'] is None


def test_peer_component_deviation_not_reported_as_executable_gain(comparison):
    measured, teacher = comparison
    rows = teacher['selection']['provider_evidence']['rows']
    candidate = next(index for index, row in enumerate(rows)
        if row['action']['initial_action'] != rows[4]['action']['initial_action'])
    measured['report']['requested_indices'].append(candidate)
    measured['report']['rows'][candidate] = copy.deepcopy(rows[candidate])
    measured['report']['selection']['selected_index'] = candidate
    result = probe.compare_variant(*comparison)
    assert result['all_requested_prediction_parity']
    assert not result['selected_strictly_protected_and_component_compatible']
    assert result['component_compatible_regret_s'] is None


def test_rule_wrapper_matches_shared_semantics(monkeypatch):
    calls = []
    monkeypatch.setattr(probe.ranker, 'rule_scores', lambda observation, candidates: calls.append(
        (observation, candidates)) or [1., 2.])
    assert probe.shared_rule({'own': 1}, [{}, {}], 'shared_semantic_rule_v1') == [1., 2.]
    assert calls == [({'own': 1}, [{}, {}])]
    with pytest.raises(ValueError, match='rule_version'):
        probe.shared_rule({}, [], 'semantic_rule_v1')


@pytest.mark.parametrize('process_status,exitcode', [('hard_timeout', 0), ('exited', 1), ('exited', 0)])
def test_parent_never_accepts_child_success_after_process_failure(tmp_path, monkeypatch, process_status, exitcode):
    probe.write(tmp_path / 'plan.json', {})
    probe.write(tmp_path / 'worker_report.json', {'status': 'complete_advice_only_same_context_probe'})
    monkeypatch.setattr(probe, 'check_pins', lambda plan: None)
    monkeypatch.setattr(probe.bounded_windows_job, 'run', lambda *args, **kwargs: {
        'status': process_status, 'exitcode': exitcode, 'hard_process_seconds': kwargs['timeout']})
    result = probe.launch(tmp_path)
    assert (result['status'] == 'complete_advice_only_same_context_probe') == (
        process_status == 'exited' and exitcode == 0)
    assert result['process']['hard_process_seconds'] == 90
    with pytest.raises(ValueError, match='one_launch_only'):
        probe.launch(tmp_path)


def test_source_pins_fail_closed(tmp_path):
    path = tmp_path / 'source.py'
    path.write_text('before')
    plan = {'source_sha256': {str(path): probe.sha(path)}}
    path.write_text('after')
    with pytest.raises(ValueError, match='frozen_source'):
        probe.check_pins(plan)


def test_model_requires_real_mechanism_holdout(tmp_path):
    path = tmp_path / 'model.json'
    payload = {'schema': probe.ranker.MODEL_SCHEMA, 'feature_schema': probe.ranker.data.SCHEMA,
        'kind': 'linear', 'trained_source_groups': ['mechanism', 'no_overlap'],
        'validation_or_test_used_for_fit': False, 'uses_candidate_index_as_feature': False,
        'native_execution_authority': False}
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='heldout_mechanism_linear_model'):
        probe.validate_model(path)


def test_callback_orders_both_budgeted_calls_without_teacher_access(tmp_path, monkeypatch):
    events = []

    class Decision:
        def audit_copy(self):
            return {'owner': 'B', 'public_sha256': 'current', 'at': .11}

    class Batch:
        def audit_copy(self):
            return {'status': 'conditional_forecasts_complete'}

    def evaluate(decision, **kwargs):
        events.append((kwargs['budget'], kwargs['scorer'], kwargs['model_version']))
        return {'batch': Batch(), 'compute_wall_ms': 1.}

    monkeypatch.setattr(probe.provider.origin, 'require_current', lambda decision: None)
    monkeypatch.setattr(probe.provider, 'evaluate_budgeted', evaluate)
    result = probe.make_callback('heldout_model', tmp_path)(Decision())
    assert events == [(8, probe.shared_rule, 'shared_semantic_rule_v1'),
        (8, probe.ranker.score_candidates, 'heldout_model')]
    assert list(result['variants']) == ['rule', 'learned']
    assert result['full32_teacher_not_available_to_callback']
    assert not result['native_authority']
