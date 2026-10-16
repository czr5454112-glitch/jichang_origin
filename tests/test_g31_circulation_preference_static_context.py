"""Static-code reuse only: every request still validates independent input."""
from copy import deepcopy
import json
import sys
from types import ModuleType

import pytest

from scripts.experiments.g31_ics_circulation import public_preference_static_context as candidate
from scripts.experiments.g31_ics_circulation import preference_wall_budget as budget
from test_g31_circulation_preference_request_context import bundle, ordered

base, original = candidate.base, candidate.base.original


@pytest.fixture(scope='module')
def implementation():
    return candidate.StaticImplementation()


@pytest.mark.parametrize('index', range(6))
def test_all_six_full32_outputs_identical(index, implementation):
    supplied = bundle(index)
    context = implementation.context(supplied)
    assert len(context.actions()) == 32
    for action in context.actions():
        assert ordered(context.predict(action)) == ordered(original.predict(supplied, action))
    assert implementation.describe()['constructor_code_identical'] is True
    assert implementation.describe()['complete_100ms_certified'] is False


def test_compile_once_dynamic_validation_every_request(monkeypatch):
    counts = {'compile': 0, 'guard': 0}
    compiler, guard = base.compile_guards, original.contract.supported_contract
    def compile_once():
        counts['compile'] += 1
        return compiler()
    def dynamic_guard():
        counts['guard'] += 1
        return guard()
    monkeypatch.setattr(base, 'compile_guards', compile_once)
    monkeypatch.setattr(original.contract, 'supported_contract', dynamic_guard)
    values = [bundle(), bundle(1)]
    counts['guard'] = 0
    implementation = candidate.StaticImplementation()
    for value in values:
        context = implementation.context(value)
        assert context.predict(context.actions()[0])['status'] == 'conditional_prediction'
    assert counts == {'compile': 1, 'guard': 2}


@pytest.mark.parametrize('defect', ['pending', 'resource', 'type', 'clock', 'missing', 'contract'])
def test_new_request_revalidates_changed_data(defect, implementation):
    value = bundle(); context = implementation.context(value); action = context.actions()[0]
    if defect == 'pending': value['owner_pending_tray_requests'] = ['x']
    elif defect == 'resource': value['resources'][5]['actual_available'] = 0
    elif defect == 'type': value['trays']['L']['generation'] = True
    elif defect == 'clock': value['trays']['E']['available_at'] = 90.
    elif defect == 'missing': value['jobs'].pop('receiver')
    else: value['contract']['node_contracts'][0]['capacity'] += 1
    expected = original.predict(value, action)
    assert expected['status'].startswith('unknown')
    assert ordered(implementation.context(value).predict(action)) == ordered(expected)
    assert context.predict(action)['status'] == 'conditional_prediction'


def test_no_input_result_actions_or_context_aliases(implementation):
    supplied = bundle(); pristine = deepcopy(supplied)
    first = implementation.context(supplied)
    second = implementation.context(supplied)
    action = first.actions()[0]
    supplied['jobs']['loaded']['destination'] = 99
    first.snapshot()['resources'][5]['actual_available'] = 0
    first.actions()[0]['return_delay'] = 99
    first.predict(action)['completion']['loaded'] = -1
    expected = original.predict(pristine, action)
    assert ordered(first.predict(action)) == ordered(second.predict(action)) == ordered(expected)


@pytest.mark.parametrize('defect', ['bool', 'nan', 'extra', 'missing', 'unsupported'])
def test_action_guards_remain_per_call(defect, implementation):
    supplied = bundle(); context = implementation.context(supplied)
    action = context.actions()[0]
    if defect == 'bool': action['return_delay'] = False
    elif defect == 'nan': action['empty_departure'] = float('nan')
    elif defect == 'extra': action['extra'] = 1
    elif defect == 'missing': action.pop('later_action')
    else: action['later_action'] = 'invented'
    assert ordered(context.predict(action)) == ordered(original.predict(supplied, action))


def test_source_change_rejected_each_request(monkeypatch, implementation):
    sha = candidate._sha
    monkeypatch.setattr(candidate, '_sha', lambda path: '0'*64 if str(path) == str(base.__file__) else sha(path))
    with pytest.raises(ValueError, match='source_changed'):
        implementation.context(bundle())


@pytest.mark.parametrize('target', ['method', 'guard', 'constant', 'mutable_constant', 'module_alias'])
def test_live_implementation_mutation_rejected(monkeypatch, target, implementation):
    supplied = bundle()
    if target == 'method': monkeypatch.setattr(original.Projection, 'run', lambda self: {})
    elif target == 'guard': monkeypatch.setattr(original.contract, 'supported_contract', lambda: {})
    elif target == 'constant': monkeypatch.setattr(original, 'VERSION', 'mutated')
    elif target == 'mutable_constant': monkeypatch.setitem(original.contract.SUPPORTED_NATIVE_SEMANTICS, 'queue_discipline', 'changed')
    else: monkeypatch.setattr(original, 'contract', ModuleType('fake_contract'))
    with pytest.raises(ValueError, match='live_implementation_changed'):
        implementation.context(supplied)


def test_closed_supplied_data_domain_preserved(implementation):
    class Custom(dict): pass
    with pytest.raises(TypeError): implementation.context(Custom(bundle()))
    value = bundle(); value['cycle'] = value
    with pytest.raises(ValueError): implementation.context(value)


def test_module_replacement_rejected(monkeypatch, implementation):
    value = bundle()
    monkeypatch.setitem(sys.modules, original.__name__, ModuleType(original.__name__))
    with pytest.raises(ValueError, match='module_replaced'):
        implementation.context(value)


def test_unrelated_module_does_not_expand_request_inventory(monkeypatch, implementation):
    value = bundle()
    foreign = ModuleType('unrelated_plugin')
    foreign.__file__ = 'Z:/unrelated/network/some_plugin.py'
    monkeypatch.setitem(sys.modules, foreign.__name__, foreign)
    context = implementation.context(value)
    assert context.predict(context.actions()[0])['status'] == 'conditional_prediction'


class Clock:
    def __init__(self): self.at = 0
    def __call__(self): self.at += 1; return self.at


_budget_implementation = None
_WARM = object()


def run_budget(*, clock=None, select=None, finalize=None, maximum=32, budget_ns=1000, reserve_ns=100,
               implementation=_WARM):
    global _budget_implementation
    if implementation is _WARM:
        if _budget_implementation is None:
            _budget_implementation = candidate.StaticImplementation()
        implementation = _budget_implementation
    value = bundle()
    actions = base.RequestContext(value).actions()
    result = budget.run(value, actions, budget_ns=budget_ns, reserve_ns=reserve_ns,
        select=select or (lambda rows, previous: next((i for i, row in enumerate(rows)
            if row['status'] == 'evaluated' and row['prediction']['status'] == 'conditional_prediction'), None)),
        finalize=finalize or (lambda snapshot, proposal, deadline: {'status': 'unknown_no_native_revalidation'}),
        maximum_candidates=maximum, implementation=implementation, clock=clock or Clock())
    return result, json.loads(result['response_bytes'])


def test_budget_has_complete_outputs_and_no_native_authority(implementation):
    result, response = run_budget(implementation=implementation)
    value = bundle()
    assert len(response['candidate_rows']) == 32
    for row in response['candidate_rows']:
        assert row['status'] == 'evaluated'
        assert ordered(row['prediction']) == ordered(original.predict(value, row['action']))
    assert result['factory_cold_cost_included'] is False
    assert result['complete_request_100ms_certified'] is False
    assert result['unassigned_inside_envelope_ns'] >= 0
    assert sum(s['end_ns']-s['start_ns'] for s in result['spans']) + result['unassigned_inside_envelope_ns'] == result['observed_admission_through_codec_ns']
    assert response['native_permission_verified'] is False


def test_four_evaluations_retain_other28_unknown():
    _, response = run_budget(maximum=4)
    assert [r['status'] for r in response['candidate_rows']] == ['evaluated']*4 + ['unknown_unexecuted']*28


def test_cold_factory_cost_scope_is_explicit():
    result, response = run_budget(implementation=None, maximum=4)
    assert result['factory_cold_cost_included'] is True


def test_internal_domain_is_derived_after_admission_and_charged(implementation):
    value = bundle(); clock = Clock()
    result = budget.run(value, budget_ns=1000, reserve_ns=100, implementation=implementation,
        clock=clock, maximum_candidates=4, select=lambda rows, previous: 0,
        finalize=lambda snapshot, proposal, deadline: {'status': 'unknown_no_native_revalidation'})
    response = json.loads(result['response_bytes'])
    assert response['action_domain_scope'] == 'derived_inside_request'
    assert response['declared_action_count'] == 32
    assert sum(row['status'] == 'evaluated' for row in response['candidate_rows']) == 4
    assert result['accepted_ns'] <= result['spans'][0]['start_ns'] < result['spans'][0]['end_ns']


def test_unavailable_dynamic_domain_does_not_fabricate_actions(implementation):
    value = bundle(); value['owner_pending_tray_requests'] = ['unresolved']
    result = budget.run(value, implementation=implementation, budget_ns=1000, reserve_ns=100,
        clock=Clock(), select=lambda rows, previous: 0,
        finalize=lambda snapshot, proposal, deadline: {'status': 'unknown_unresolved', 'proposal': proposal})
    response = json.loads(result['response_bytes'])
    assert response['candidate_domain_available'] is False
    assert response['incumbent_index'] is None
    assert response['finalization']['proposal'] is None
    assert not response['native_permission_verified']


def test_adaptive_methods_share_same_domain_budget_and_cap(implementation):
    def last(rows, incumbent):
        return max(i for i, row in enumerate(rows) if row['status'] == 'unknown_unexecuted')
    result = budget.run(bundle(), implementation=implementation, maximum_candidates=4,
        budget_ns=1000, reserve_ns=100, clock=Clock(), choose_next=last,
        select=lambda rows, previous: max(i for i, row in enumerate(rows) if row['status'] == 'evaluated'),
        finalize=lambda snapshot, proposal, deadline: {'status': 'unknown_no_native_revalidation'})
    response = json.loads(result['response_bytes'])
    assert [i for i, row in enumerate(response['candidate_rows']) if row['status'] == 'evaluated'] == [28, 29, 30, 31]
    assert response['incumbent_index'] == 31
    assert len(response['candidate_rows']) == 32


def test_method_choice_overrun_starts_no_new_solver(implementation):
    clock = Clock()
    def expensive(rows, incumbent):
        clock.at += 1000
        return 0
    result = budget.run(bundle(), implementation=implementation, maximum_candidates=32,
        budget_ns=100, reserve_ns=20, clock=clock, choose_next=expensive,
        select=lambda rows, previous: 0,
        finalize=lambda snapshot, proposal, deadline: {'status': 'unknown'})
    response = json.loads(result['response_bytes'])
    assert all(row['status'] == 'unknown_unexecuted' for row in response['candidate_rows'])
    assert result['observed_overrun_ns'] > 900


def test_repeated_method_candidate_is_unknown_not_second_execution(implementation):
    result = budget.run(bundle(), implementation=implementation, budget_ns=1000, reserve_ns=100,
        clock=Clock(), choose_next=lambda rows, incumbent: 0, select=lambda rows, previous: 0,
        finalize=lambda snapshot, proposal, deadline: {'status': 'unknown'})
    response = json.loads(result['response_bytes'])
    assert sum(row['status'] == 'evaluated' for row in response['candidate_rows']) == 1
    assert response['failure']['stage'] == 'method_candidate_choice'


def test_setup_exhaustion_keeps_all_unknown_and_runs_finalization():
    called = []
    result, response = run_budget(budget_ns=2, reserve_ns=1,
        finalize=lambda snapshot, proposal, deadline: called.append(proposal) or {'status': 'unknown'})
    assert called == [None]
    assert all(row['status'] == 'unknown_unexecuted' for row in response['candidate_rows'])
    assert result['observed_overrun_ns'] > 0


def test_candidate_overrun_not_interrupted_or_converted_to_safe():
    clock = Clock()
    def select(rows, prior):
        clock.at += 1000
        return 0
    result, response = run_budget(clock=clock, select=select, budget_ns=100, reserve_ns=10)
    assert response['candidate_rows'][0]['prediction']['status'] == 'conditional_prediction'
    assert sum(r['status'] == 'evaluated' for r in response['candidate_rows']) == 1
    assert result['observed_overrun_ns'] > 900
    assert not result['observed_budget_met_through_codec']
    assert not response['native_current_identity_verified']


def test_finalization_and_codec_cost_not_cut_at_deadline():
    clock = Clock()
    def finalize(snapshot, proposal, deadline):
        clock.at += 1000
        return {'claimed_native_permission': True, 'payload': 'x'*100}
    result, response = run_budget(clock=clock, maximum=4, finalize=finalize, budget_ns=100, reserve_ns=10)
    assert result['observed_overrun_ns'] > 900
    assert result['spans'][-1]['stage'] == 'response_codec'
    assert response['native_permission_verified'] is False


def test_failed_method_or_finalization_keeps_denominator():
    def broken(*args): raise RuntimeError('injected')
    result, response = run_budget(select=broken, finalize=broken)
    assert len(response['candidate_rows']) == 32
    assert sum(r['status'] == 'unknown_unexecuted' for r in response['candidate_rows']) == 31
    assert response['failure']['stage'] == 'method_selection'
    assert response['finalization']['status'] == 'unknown_finalization_failed'


@pytest.mark.parametrize('selected', [True, -1, 31, '0'])
def test_cannot_return_unevaluated_incumbent(selected):
    with pytest.raises(ValueError, match='incumbent'):
        run_budget(select=lambda rows, prior: selected)


def test_clock_regression_rejected():
    values = iter([10, 9])
    with pytest.raises(ValueError, match='clock_regressed'):
        run_budget(clock=lambda: next(values))
