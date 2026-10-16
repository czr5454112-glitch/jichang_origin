"""Initial caller scope prototype: fake model/provider only unless labeled.

No real model/native invocation. The exact original build_initial function is
executed against instrumented provider interfaces to prove call order and all
independent comparison/type gates; frozen module globals remain untouched.
"""
import copy
import json
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import public_live_obligation_initial_scoped_inputs as m


def facts():
    return {'jobs': [{'id': 'j'}], 'trays': [{'id': 't'}], 'contract': {'fixed': True}, 'now': 0.1}


def public():
    return {'initial_owners': {owner: {'owner': owner, 'facts': facts()} for owner in ('A', 'B')},
        'action': {'candidate': 0}}


class Supplied:
    def __init__(self, owner, payload): self.owner = owner; self.payload = copy.deepcopy(payload)


def provider(log, *, wrong=None, failure=None, error=None):
    def initial_context(**kwargs):
        owner = kwargs['owner']; log.append(('initial', owner))
        if owner == failure: raise error
        if owner == wrong: return {'status': 'unknown'}
        return Supplied(owner, kwargs['facts'])
    def projection(context):
        log.append(('facts', context.owner)); return copy.deepcopy(context.payload)
    def encoded(value):
        log.append(('encoded', copy.deepcopy(value))); return json.dumps(value, allow_nan=False)
    return SimpleNamespace(initial_context=initial_context, SuppliedContext=Supplied,
        initial_projection_bundle=projection, encoded=encoded)


def install(monkeypatch, *, wrong=None, failure=None, error=None):
    a_log = []; b_log = []; scopes = []; predictions = []
    original = SimpleNamespace(context=provider(a_log, wrong=wrong, failure=failure, error=error))
    class Scope:
        def __init__(self):
            b_log.append(('scope', len(scopes)))
            self.context = provider(b_log, wrong=wrong, failure=failure, error=error)
            self.call_count = 0; scopes.append(self)
        def predict(self, supplied, action):
            self.call_count += 1; b_log.append(('predict', supplied.owner))
            predictions.append((self, supplied, action))
            return {'payload': copy.deepcopy(supplied.payload), 'action': copy.deepcopy(action)}
    def original_predict(supplied, action):
        a_log.append(('new_v2_predict_scope',)); a_log.append(('predict', supplied.owner))
        predictions.append(('reference', supplied, action))
        return {'payload': copy.deepcopy(supplied.payload), 'action': copy.deepcopy(action)}
    # Only new module variables are rebound; no mutation of original provider,
    # candidate modules, guard functions, or process-global APIs.
    monkeypatch.setattr(m, 'original', original)
    monkeypatch.setattr(m, 'scoped', SimpleNamespace(PublicInputScope=Scope, predict=original_predict))
    return a_log, b_log, scopes, predictions


def test_source_proof_no_scope_or_input():
    proof = m.source_proof()
    assert proof['original_initial_caller_same_function_code_globals_defaults_closure']
    assert proof['same_scope_context_and_predictor_in_B'] and proof['new_scope_each_call']
    assert proof['initial_owner_order'] == ['A', 'B']
    assert proof['independent_fact_comparison_order'] == ['jobs', 'trays', 'contract', 'now']
    assert not proof['per_sample_cycle_cleanup_certified'] and not proof['native_authority']


def test_original_function_globals_metadata_preserved():
    before = dict(m._BUILD.__globals__)
    assert m._BUILD is m.caller.build_initial
    m.source_proof()
    assert all(m._BUILD.__globals__[k] is v for k,v in before.items())
    assert m._BUILD.__code__ is m._BUILD_CODE and m._BUILD.__closure__ is m._BUILD_CLOSURE


def test_complete_reference_and_candidate_equal_order_and_single_scope(monkeypatch):
    a,b,scopes,predictions = install(monkeypatch)
    data = public(); before = copy.deepcopy(data)
    assert m.reference(data) == m.predict(data)
    assert data == before and len(scopes) == 1 and scopes[0].call_count == 1
    assert [x for x in a if x[0] not in ('new_v2_predict_scope',)] == [x for x in b if x[0] != 'scope']
    assert [x for x in b if x[0] in ('initial','facts','predict')] == [
        ('initial','A'),('initial','B'),('facts','A'),('facts','B'),('predict','A')]
    assert len([x for x in b if x[0] == 'encoded']) == 8
    assert all(item[2] is data['action'] for item in predictions)


def test_each_call_new_scope_and_mutation_isolation(monkeypatch):
    a,b,scopes,predictions = install(monkeypatch)
    data = public(); first = m.predict(data); second = m.predict(data)
    assert len(scopes) == 2 and scopes[0] is not scopes[1]
    assert all(scope.call_count == 1 for scope in scopes)
    assert predictions[0][1] is not predictions[1][1]
    first['payload']['jobs'][0]['id'] = 'mutated'
    first['action']['candidate'] = 8
    assert second['payload']['jobs'][0]['id'] == data['initial_owners']['B']['facts']['jobs'][0]['id'] == 'j'
    assert second['action']['candidate'] == data['action']['candidate'] == 0


@pytest.mark.parametrize('field', ['jobs', 'trays', 'contract', 'now'])
def test_independent_owner_fact_mismatch_cannot_predict(monkeypatch, field):
    a,b,scopes,predictions = install(monkeypatch)
    data = public(); data['initial_owners']['B']['facts'][field] = 'different'
    for function in (m.reference, m.predict):
        with pytest.raises(ValueError, match='independent_owner_facts'): function(data)
    assert not predictions
    assert [x for x in a if x[0] == 'initial'] == [('initial','A'),('initial','B')]
    assert [x for x in b if x[0] == 'initial'] == [('initial','A'),('initial','B')]


@pytest.mark.parametrize('wrong', ['A', 'B'])
def test_unknown_owner_type_guard_is_not_skipped(monkeypatch, wrong):
    a,b,scopes,predictions = install(monkeypatch, wrong=wrong)
    for function in (m.reference, m.predict):
        with pytest.raises(ValueError, match='initial_context_guards'): function(public())
    assert not predictions and not [x for x in a+b if x[0] == 'facts']
    assert [x for x in b if x[0] == 'initial'] == [('initial','A'),('initial','B')]


@pytest.mark.parametrize('failure', ['A', 'B'])
def test_initial_exception_identity_and_original_owner_order(monkeypatch, failure):
    error = RuntimeError('owner failed')
    a,b,scopes,predictions = install(monkeypatch, failure=failure, error=error)
    for function in (m.reference, m.predict):
        with pytest.raises(RuntimeError) as caught: function(public())
        assert caught.value is error
    expected = [('initial','A')] if failure == 'A' else [('initial','A'),('initial','B')]
    assert [x for x in a if x[0] == 'initial'] == expected
    assert [x for x in b if x[0] == 'initial'] == expected
    assert not predictions


def test_A_unknown_does_not_preempt_B_original_exception(monkeypatch):
    error = RuntimeError('B malformed')
    a,b,scopes,predictions = install(monkeypatch, wrong='A', failure='B', error=error)
    for function in (m.reference, m.predict):
        with pytest.raises(RuntimeError) as caught: function(public())
        assert caught.value is error
    assert not predictions


@pytest.mark.parametrize('change', ['missing_action', 'extra_key', 'missing_B', 'extra_owner'])
def test_original_minimal_public_input_gate(monkeypatch, change):
    a,b,scopes,predictions = install(monkeypatch); data = public()
    if change == 'missing_action': data.pop('action')
    elif change == 'extra_key': data['future_target'] = {}
    elif change == 'missing_B': data['initial_owners'].pop('B')
    else: data['initial_owners']['C'] = {}
    for function in (m.reference, m.predict):
        with pytest.raises(ValueError, match='minimal_initial_input'): function(data)
    assert not predictions and not [x for x in a+b if x[0] == 'initial']


def test_action_reaches_only_original_predictor_after_all_guards(monkeypatch):
    a,b,scopes,predictions = install(monkeypatch); data = public(); action = object(); data['action'] = action
    # The unchanged downstream model, not a new shortcut, owns action validation.
    def reject(supplied, received):
        assert received is action; assert len([x for x in b if x[0] == 'encoded']) == 8
        raise ValueError('original_action_guard')
    old = m.scoped.PublicInputScope
    class Scope(old):
        def __init__(self): super().__init__(); self.predict = reject
    m.scoped.PublicInputScope = Scope
    with pytest.raises(ValueError, match='original_action_guard'): m.predict(data)


def test_scope_allocation_failure_not_retried_or_hidden(monkeypatch):
    a,b,scopes,predictions = install(monkeypatch); error = MemoryError('scope allocation'); calls = []
    def fail(): calls.append(1); raise error
    m.scoped.PublicInputScope = fail
    with pytest.raises(MemoryError) as caught: m.predict(public())
    assert caught.value is error and calls == [1] and not predictions


def test_no_result_or_context_retention_on_module(monkeypatch):
    a,b,scopes,predictions = install(monkeypatch); keys = set(vars(m))
    m.predict(public()); m.predict(public())
    assert set(vars(m)) == keys
    assert not any(value is predictions[0][1] for value in vars(m).values())


def test_source_guard_rejects_replaced_caller(monkeypatch):
    monkeypatch.setattr(m, '_BUILD', lambda *args: None)
    with pytest.raises(ValueError, match='initial_caller_identity'): m.source_proof()


def test_source_guard_rejects_wrong_scope_class(monkeypatch):
    monkeypatch.setattr(m, 'scoped', SimpleNamespace(predict=m._PREDICT, PublicInputScope=object))
    with pytest.raises(ValueError, match='scoped_predictor_or_original_context_identity'): m.source_proof()
