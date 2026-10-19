"""Isolated fixtures are not native collection capabilities or live evidence."""
import copy
import json
from types import FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import foundation_budgeted_provider as subject
from test_g31_circulation_future_later_paired_driver import harness, action


def actions():
    return subject.teacher.future.core.lazy.original.physics.previous.actions()


def test_subset_has_exact_original_code_and_only_declared_global_change():
    for choices in (('native_default',), ('prefer_8',), subject.domain.LATER):
        function = subject._subset_run(choices)
        subject._check_subset_run(function, choices)
        assert function.__code__ is subject.execution._run.__code__
        assert function.__globals__ is not subject.execution._run.__globals__
        assert subject.execution._run.__globals__['CHOICES'] == subject.domain.LATER


@pytest.mark.parametrize('choices', [(), ('unknown',), ('prefer_8', 'native_default'), ('native_default', 'native_default')])
def test_invalid_suffix_subsets_rejected(choices):
    with pytest.raises(ValueError, match='ordered_suffix_subset'):
        subject._subset_run(choices)


@pytest.mark.parametrize('name', ['graph', 'point_description', 'CHOICES', 'injected'])
def test_subset_global_tampering_is_rejected(name):
    choices = ('native_default',)
    function = subject._subset_run(choices)
    function.__globals__[name] = object()
    with pytest.raises(ValueError, match='only_declared_suffix_subset_global'):
        subject._check_subset_run(function, choices)


def synthetic_run(model, future, choices, saved):
    namespace = {**subject.execution._run.__globals__, 'CHOICES': choices,
        'point_description': subject.execution.previous.point_description,
        'terminal_description': subject.execution.previous.terminal_description}
    function = FunctionType(subject._RUN_CODE, namespace, 'synthetic_subset')
    return function('initial_only', action(), 4, model, future,
        lambda label, prediction: saved.setdefault(label, copy.deepcopy(prediction)))


@pytest.mark.parametrize('choices', [('native_default',), ('prefer_8',), ('native_default', 'prefer_8')])
@pytest.mark.parametrize('cuts', [2, 4])
def test_same_context_predictions_match_paired_without_unselected_suffix(harness, choices, cuts):
    model, future, _, _, _ = harness(cuts)
    expected = {}
    synthetic_run(model, future, subject.domain.LATER, expected)
    model, future, _, _, _ = harness(cuts)
    observed = []
    original_fork = future.fork_later_action
    original_resume = future.resume_future_later

    def fork(state, choice):
        assert choice in choices
        observed.append(('fork', choice))
        return original_fork(state, choice)

    def resume(branch):
        choice = branch._after['later_action']
        assert choice in choices
        observed.append(('resume', choice))
        return original_resume(branch)

    future.fork_later_action = fork
    future.resume_future_later = resume
    actual = {}
    result = synthetic_run(model, future, choices, actual)
    assert actual == {choice: expected[choice] for choice in choices}
    assert tuple(result['suffixes']) == choices
    assert observed == [('fork', choice) for choice in choices] + [('resume', choice) for choice in choices]
    assert result['prefix']['parent_unconsumed'] is True
    assert model.starts == model.advances == 1
    assert result['counts']['future_forks'] == result['counts']['future_resumes'] == len(choices)


@pytest.mark.parametrize('failure', ['bad_cut', 'unknown_B', 'fail_prefix', 'early'])
def test_unknown_prefix_never_executes_requested_suffix(harness, failure):
    model, future, _, _, _ = harness(**{failure: True})
    result = synthetic_run(model, future, ('prefer_8',), {})
    assert result['counts']['future_forks'] == result['counts']['future_resumes'] == 0
    assert result['suffixes']['prefer_8']['status'] == 'unknown_unexecuted'


@pytest.fixture
def provider_fixture(monkeypatch):
    events = []
    public = {'view': {'owner_id': 'B', 'now': .11}, 'received': [{'delivered_fact': 7}]}
    decision = SimpleNamespace(audit_copy=lambda: {'owner': 'B', 'at': .11,
        'public_sha256': 'unit-fixture-only', 'public': copy.deepcopy(public)})
    request = SimpleNamespace(uses=0, closed=False)

    def current(actual):
        assert actual is decision
        events.append('current')

    def bind():
        events.append('bind')
        return request

    def proof(actual):
        assert actual is request
        actual.uses += 1
        return {'unit_fixture_only': True}

    def close():
        events.append('close')
        request.closed = True

    def execute(actual, group, context, selected):
        assert actual is request and context == 'fixture_context'
        events.append(('group', group['prefix_index'], selected))
        request.uses += 2 * len(selected)
        suffixes, predictions = {}, {}
        for index in selected:
            choice = actions()[index]['later_action']
            completion = {job: 10. if index == 4 else 9. for job in subject.teacher.JOBS}
            predictions[choice] = {'status': 'conditional_prediction', 'completion': completion,
                'unknown_information_phases': [], 'mutable_nested': []}
            suffixes[choice] = {'status': 'returned', 'isolation_basis': subject.execution.OWNERSHIP}
        return {'prefix_index': group['prefix_index'], 'candidate_indices': list(selected),
            'detail': {'counts': {'initial_engines': 1, 'initial_advances': 1,
                'prefix_same_resumes': 1, 'future_forks': len(selected), 'future_resumes': len(selected)},
                'prefix': {'status': 'supported_known_B_cut', 'isolation_basis': subject.execution.OWNERSHIP,
                    'diagnostic_graphs_computed': False, 'parent_unconsumed': True}, 'suffixes': suffixes},
            'predictions': predictions, 'binding_error': None}

    request.close = close
    request.description = lambda: {'proof_binding': {'proof_uses': request.uses}}
    monkeypatch.setattr(subject.origin, 'require_current', current)
    monkeypatch.setattr(subject.origin, 'supplied_snapshot', lambda actual: 'fixture_context')
    monkeypatch.setattr(subject.origin, 'revalidate_first_component', lambda actual, action:
        {'status': 'fresh_local_component_proposal', 'dispatch_authorized': False})
    monkeypatch.setattr(subject.teacher, '_prepare_copy_metadata', lambda: {})
    monkeypatch.setattr(subject.binding, 'bind_request', bind)
    monkeypatch.setattr(subject, 'source_contract', proof)
    monkeypatch.setattr(subject, 'execute_selected_prefix', execute)
    monkeypatch.setattr(subject.teacher, 'evaluate_declared32', lambda *args: pytest.fail('hidden_full32'))
    return decision, request, events, public


@pytest.mark.parametrize('indices', [(4,), (4, 5), (4, 12, 13), (4, 1, 8, 20)])
def test_exact_requested_candidates_prefixes_and_proof_denominator(provider_fixture, indices):
    decision, request, events, _ = provider_fixture
    measured = subject.evaluate_budgeted(decision, budget=len(indices), candidate_indices=indices)
    report = measured['batch'].audit_copy()
    assert report['status'] == 'conditional_forecasts_complete'
    assert report['requested_indices'] == list(indices)
    assert report['counts']['context_constructions'] == len({index // 2 for index in indices})
    assert report['counts']['future_forks'] == report['counts']['future_resumes'] == len(indices)
    assert report['counts']['known_candidate_predictions'] == len(indices)
    assert request.uses == 1 + 2 * len(indices) and request.closed
    assert all(row['status'] == 'not_requested' and 'prediction' not in row
        for row in report['rows'] if row['candidate_index'] not in indices)
    assert report['selection']['dispatch_authorized'] is False
    assert measured['compute_wall_ms'] >= measured['seal_wall_ms'] >= 0
    assert events.index('bind') > events.index('current')


def test_ranker_precedes_every_context_and_gets_detached_public_semantics(provider_fixture):
    decision, request, events, public = provider_fixture
    expected_actions = actions()

    def scorer(observation, candidates, model_version):
        assert model_version == 'test-model' and 'bind' not in events
        assert observation == public and candidates == expected_actions
        assert all('candidate_index' not in action for action in candidates)
        observation['received'][0]['delivered_fact'] = 'mutated'
        candidates[0]['initial_action'] = 'mutated'
        events.append('rank')
        return list(range(32))

    report = subject.evaluate_budgeted(decision, budget=4, scorer=scorer,
        model_version='test-model')['batch'].audit_copy()
    assert report['requested_indices'] == [4, 31, 30, 29]
    assert events.index('rank') < events.index('bind')
    assert public['received'][0]['delivered_fact'] == 7 and actions() == expected_actions


@pytest.mark.parametrize('indices,budget', [((1, 2), 2), ((4, 4), 2), ((4, 5), 1), ((4, True), 2), ((4, 32), 2)])
def test_bad_budget_input_never_binds_or_rolls_out(provider_fixture, indices, budget):
    decision, _, events, _ = provider_fixture
    report = subject.evaluate_budgeted(decision, budget=budget, candidate_indices=indices)['batch'].audit_copy()
    assert report['status'].startswith('unknown') and 'bind' not in events
    assert report['counts']['future_resumes'] == 0


@pytest.mark.parametrize('scores', [[0.] * 31, [float('nan')] * 32, [True] * 32])
def test_invalid_ranker_output_never_binds(provider_fixture, scores):
    decision, _, events, _ = provider_fixture
    result = subject.evaluate_budgeted(decision, scorer=lambda **kwargs: scores)['batch'].audit_copy()
    assert result['status'].startswith('unknown') and 'bind' not in events


def test_closed_batch_has_one_decode_and_no_mutable_alias(provider_fixture, monkeypatch):
    decision, _, _, _ = provider_fixture
    original = json.loads
    calls = []

    def counted(value, *args, **kwargs):
        calls.append(value)
        return original(value, *args, **kwargs)

    monkeypatch.setattr(subject.json, 'loads', counted)
    batch = subject.evaluate_budgeted(decision, budget=2, candidate_indices=(4, 5))['batch']
    assert len(calls) == 1
    for _ in range(32):
        row = batch.query(4)
        row['prediction']['mutable_nested'].append('caller')
    assert len(calls) == 1 and batch.query(4)['prediction']['mutable_nested'] == []
    assert batch.query(5)['prediction']['mutable_nested'] == []
    exported = batch.audit_copy()
    exported['rows'][4]['completion']['loaded'] = -999.
    assert batch.query(4)['completion']['loaded'] == 10.
    with pytest.raises(ValueError, match='candidate_not_requested'):
        batch.query(12)
    with pytest.raises(TypeError):
        batch._data['rows'][4]['completion']['loaded'] = 0.
    with pytest.raises(ValueError, match='immutable_batch'):
        batch._data = {}
    object.__setattr__(batch, '_bytes', 'forged')
    with pytest.raises(ValueError, match='batch_integrity'):
        batch.audit_copy()


def test_exact_component_protection_and_unknown_never_pass(provider_fixture, monkeypatch):
    decision, _, _, _ = provider_fixture
    original = subject.execute_selected_prefix

    def harmed(*args):
        result = original(*args)
        if 12 in result['candidate_indices']:
            result['predictions']['native_default']['completion']['loaded'] = 10.000000000000002
        return result

    monkeypatch.setattr(subject, 'execute_selected_prefix', harmed)
    report = subject.evaluate_budgeted(decision, budget=2, candidate_indices=(4, 12))['batch'].audit_copy()
    assert report['selection']['selected_index'] == 4
    assert report['selection']['component_compatibility']['eligible_queried_indices'] == [4]


def test_binding_close_failure_invalidates_all_requested_estimates(provider_fixture):
    decision, request, _, _ = provider_fixture

    def failed():
        raise ValueError('changed_dependency')

    request.close = failed
    report = subject.evaluate_budgeted(decision, budget=2, candidate_indices=(4, 12))['batch'].audit_copy()
    assert report['status'] == 'unknown_origin_or_provider'
    assert report['counts']['known_candidate_predictions'] == 0
    assert report['selection']['selected_index'] is None
    assert 'changed_dependency' in report['close_error']


def test_saved_dictionary_has_no_actual_decision_authority():
    report = subject.evaluate_budgeted({'public': {}})['batch'].audit_copy()
    assert report['status'] == 'unknown_origin_or_provider'
    assert report['counts']['future_resumes'] == 0
    assert 'initial_decision_type' in report['error']


def test_native_adapter_callback_returns_detached_json_and_charges_export(provider_fixture):
    decision, request, _, _ = provider_fixture
    result = subject.initial_diagnostic(decision)
    assert result['report']['counts']['future_resumes'] == 4 and request.closed
    assert result['diagnostic_through_export_wall_ms'] >= result['compute_wall_ms']
    assert result['report']['dispatch_authorized'] is False
    assert json.loads(json.dumps(result)) == result


def test_public_mask_is_exact_existing_component_contract():
    assert subject.public_compatible_indices('A', actions()) == [4]
    assert subject.public_compatible_indices('B', actions()) == [0, 1, 4, 5, 8, 9, 12, 13]
    with pytest.raises(ValueError, match='known_public_contract_owner'):
        subject.public_compatible_indices('other', actions())


def test_compatible_exhaustive8_uses_only_four_prefixes_before_teacher(provider_fixture):
    decision, request, events, _ = provider_fixture
    indices = subject.public_compatible_indices('B', actions())
    report = subject.evaluate_budgeted(decision, budget=8, candidate_indices=indices,
        compatible_only=True, prefix_budget=4)['batch'].audit_copy()
    assert report['status'] == 'conditional_forecasts_complete'
    assert set(report['requested_indices']) == set(indices)
    assert report['allocation']['legal_domain_size'] == 8
    assert report['allocation']['scoring_row_count'] == 0
    assert report['allocation']['requested_prefix_count'] == report['evaluated_prefix_count'] == 4
    assert report['counts']['context_constructions'] == 4
    assert report['counts']['future_forks'] == report['counts']['future_resumes'] == 8
    assert request.uses == 17 and request.closed
    assert all(set(item[2]) <= set(indices) for item in events if type(item) is tuple)
    assert all(row['status'] == 'not_requested' and 'prediction' not in row
        for index, row in enumerate(report['rows']) if index not in indices)


def test_compatible_ranker_receives_only_legal_semantics_before_binding(provider_fixture):
    decision, _, events, _ = provider_fixture
    eligible = [0, 1, 4, 5, 8, 9, 12, 13]

    def scorer(observation, candidates, model_version):
        assert 'bind' not in events
        assert candidates == [actions()[index] for index in eligible]
        assert all('candidate_index' not in candidate for candidate in candidates)
        return [1., 0., 2., 3., 5., 4., 9., 8.]

    report = subject.evaluate_budgeted(decision, budget=4, scorer=scorer, compatible_only=True,
        prefix_budget=2)['batch'].audit_copy()
    assert report['requested_indices'] == [4, 12, 13, 5]
    assert report['allocation']['scoring_row_count'] == 8
    assert report['allocation']['requested_prefix_indices'] == [2, 6]
    assert report['evaluated_prefix_count'] == 2
    assert all(score is None for index, score in enumerate(report['scores']) if index not in eligible)


@pytest.mark.parametrize('prefix_budget,expected_count', [(1, 2), (2, 4)])
def test_prefix_limit_does_not_force_candidate_budget_fill(provider_fixture, prefix_budget, expected_count):
    decision, request, _, _ = provider_fixture
    report = subject.evaluate_budgeted(decision, budget=8, compatible_only=True,
        prefix_budget=prefix_budget)['batch'].audit_copy()
    assert report['status'] == 'conditional_forecasts_complete'
    assert len(report['requested_indices']) == expected_count
    assert report['evaluated_prefix_count'] == prefix_budget
    assert request.uses == 1 + 2 * expected_count


def test_cost_rule_pays_shared_prefix_once(provider_fixture):
    decision, _, _, _ = provider_fixture
    report = subject.evaluate_budgeted(decision, budget=4, compatible_only=True,
        prefix_budget=2, ranking_policy='marginal_prefix_cost')['batch'].audit_copy()
    allocation = report['allocation']
    assert report['requested_indices'] == [4, 5, 0, 1]
    assert [step['incremental_cost_units'] for step in allocation['selection_steps']] == [2, 1, 2, 1]
    assert allocation['estimated_total_cost_units'] == 6
    assert report['evaluated_prefix_count'] == 2
    assert 'not milliseconds' in allocation['incremental_cost_scope']


@pytest.mark.parametrize('kwargs', [
    {'candidate_indices': [4, 16]}, {'candidate_indices': [4, 0], 'prefix_budget': 1},
    {'prefix_budget': True}, {'prefix_budget': 0}, {'prefix_budget': 17}, {'ranking_policy': 'unknown'},
])
def test_invalid_compatible_request_never_binds(provider_fixture, kwargs):
    decision, _, events, _ = provider_fixture
    report = subject.evaluate_budgeted(decision, budget=4, compatible_only=True, **kwargs)['batch'].audit_copy()
    assert report['status'] == 'unknown_origin_or_provider'
    assert 'bind' not in events
    assert report['counts']['future_resumes'] == 0


def test_owner_A_only_incumbent_even_when_budget_is_larger(provider_fixture):
    decision, _, _, _ = provider_fixture
    original = decision.audit_copy
    decision.audit_copy = lambda: {**original(), 'owner': 'A'}
    report = subject.evaluate_budgeted(decision, budget=8, compatible_only=True,
        prefix_budget=4)['batch'].audit_copy()
    assert report['requested_indices'] == [4]
    assert report['allocation']['legal_domain_size'] == report['allocation']['scoring_row_count'] == 1
    assert report['evaluated_prefix_count'] == 1
