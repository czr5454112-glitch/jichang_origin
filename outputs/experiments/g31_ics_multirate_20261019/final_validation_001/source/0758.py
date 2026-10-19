"""Synthetic lifecycle drafts: no real proof, engine, native or C execution."""
import copy
from types import FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_bound_owned_runtime_v3_v2 as subject


class MarkerError(Exception):
    pass


def active_request(*, uses=1):
    """Only the router state contract; not a fake native/proof capability."""
    value = object.__new__(subject.BoundCaseRuntime)
    value._started_ns = subject.time.perf_counter_ns()
    value._next = 0
    value._closed = False
    value._failed = False
    value._setup = {'status': 'bound_exact_setup_proof'}
    value._facade = SimpleNamespace(core=object())
    proof = SimpleNamespace(_active=True)
    counts = {'close': 0, 'execute': 0, 'uses': uses}

    def check():
        subject.require(not value._closed and not value._failed and proof._active,
            'synthetic_closed_or_failed')

    def close():
        counts['close'] += 1
        proof._active = False

    def execute(group, make_context, save_prediction, *, model, future):
        counts['execute'] += 1
        assert model is value._facade.core and future is value._facade
        counts['uses'] += 4
        return {'prefix_index': group['prefix_index']}

    value.check_integration = check
    value._handle = SimpleNamespace(_proof=proof, close=close,
        description=lambda: {'proof_binding': {'proof_uses': counts['uses']}})
    value._group_execute = execute
    return value, counts


def failed_constructor(*, stage):
    """Actual constructor code with a private synthetic defining namespace."""
    calls = {'cold': 0, 'warm': 0, 'close': 0}
    primary = MarkerError('original-' + stage)
    proof = SimpleNamespace(_active=True)

    def warm():
        calls['warm'] += 1
        raise primary

    def close():
        calls['close'] += 1
        proof._active = False
        if stage == 'warm_and_close':
            raise MarkerError('separate-close-failure')

    handle = SimpleNamespace(_proof=proof, facade=SimpleNamespace(source_proof=warm), close=close)

    def bind():
        calls['cold'] += 1
        if stage == 'cold':
            raise primary
        return handle

    namespace = {**subject.BoundCaseRuntime.__init__.__globals__,
        'source_proof': lambda: {'synthetic_identity_only': True},
        'binding': SimpleNamespace(bind_request=bind)}
    original = subject.BoundCaseRuntime.__init__
    initializer = FunctionType(original.__code__, namespace, original.__name__,
        original.__defaults__, original.__closure__)
    initializer.__kwdefaults__ = original.__kwdefaults__
    value = object.__new__(subject.BoundCaseRuntime)
    initializer(value, {'synthetic_expected': True})
    return value, calls


@pytest.mark.parametrize('stage', ['cold', 'warm', 'warm_and_close'])
def test_constructor_failure_has_one_revocation_and_router_does_not_close(stage):
    value, calls = failed_constructor(stage=stage)
    counts_before = dict(calls)
    record = subject.finalize_case(value, primary_error='outer-observation')
    assert record['status'] == 'unknown_constructor_revoked'
    assert record['close_called_by_router'] is False
    assert record['primary_error'] == 'outer-observation'
    assert calls == counts_before
    assert calls['cold'] == 1 and calls['warm'] == (0 if stage == 'cold' else 1)
    assert calls['close'] == (0 if stage == 'cold' else 1)
    assert ('original-' + stage) in record['setup']['error']
    assert record['closed'] is True and record['failed'] is True
    assert record['complete65_proof_uses'] is False
    if stage == 'warm_and_close':
        assert 'separate-close-failure' in record['setup']['close_after_failure_error']


def test_setup_export_is_a_copy_and_does_not_change_saved_failure():
    value, _ = failed_constructor(stage='cold')
    exported = value.setup_copy()
    exported['error'] = 'changed'
    assert 'original-cold' in value.setup_copy()['error']


@pytest.mark.parametrize('group', [{}, {'prefix_index': True}, {'prefix_index': -1},
    {'prefix_index': 1}, {'prefix_index': 16}, None])
def test_invalid_order_permanently_revokes_and_corrected_call_is_rejected(group):
    value, counts = active_request()
    with pytest.raises(Exception):
        value.execute_group(group, object(), object())
    assert value._failed and not value._handle._proof._active
    assert value._next == 0 and counts['execute'] == 0
    with pytest.raises(Exception):
        value.execute_group({'prefix_index': 0}, object(), object())
    assert counts['execute'] == 0
    record = subject.finalize_case(value)
    assert record['close']['status'] == 'unknown_close'
    assert record['close']['failed'] and record['close']['closed']


def test_execution_exception_preserved_saved_prediction_and_no_implicit_retry():
    value, counts = active_request()
    saved = []
    primary = MarkerError('after-durable-save')

    def execute(group, make_context, save_prediction, **kwargs):
        save_prediction('native_default', {'complete_prediction': True})
        raise primary

    value._group_execute = execute
    with pytest.raises(MarkerError) as caught:
        value.execute_group({'prefix_index': 0}, object(), lambda *args: saved.append(copy.deepcopy(args)))
    assert caught.value is primary
    assert value._next == 1 and saved == [('native_default', {'complete_prediction': True})]
    record = subject.finalize_case(value, primary_error='after-durable-save')
    assert record['primary_error'] == 'after-durable-save' and record['close']['failed']
    with pytest.raises(Exception):
        value.execute_group({'prefix_index': 1}, object(), object())


def test_exact_sixteen_groups_and_sixtyfive_uses_close_once():
    value, counts = active_request()
    for index in range(16):
        assert value.execute_group({'prefix_index': index}, object(), object()) == {'prefix_index': index}
    record = subject.finalize_case(value)
    assert record['status'] == 'closed_complete65'
    assert counts == {'close': 1, 'execute': 16, 'uses': 65}
    assert record['close']['complete65_proof_uses'] is True


def test_partial_work_retains_incomplete_denominator():
    value, counts = active_request()
    value.execute_group({'prefix_index': 0}, object(), object())
    record = subject.finalize_case(value)
    assert record['status'] == 'closed_with_incomplete_candidate_work'
    assert record['close']['groups_claimed'] == 1 and counts['uses'] == 5
    assert record['close']['complete65_proof_uses'] is False


def test_sixtysix_uses_never_close_complete():
    value, _ = active_request(uses=66)
    value._next = 16
    record = subject.finalize_case(value)
    assert record['status'] == 'unknown_close'
    assert record['close']['failed'] and not record['close']['complete65_proof_uses']


def test_cleanup_failure_does_not_replace_primary_failure():
    value, _ = active_request()

    def broken_close():
        raise MarkerError('cleanup-only')

    value.close = broken_close
    record = subject.finalize_case(value, primary_error='primary-execution-error')
    assert record['status'] == 'unknown_finalization_failed'
    assert record['primary_error'] == 'primary-execution-error'
    assert 'cleanup-only' in record['finalization_error']
    assert value._closed and value._failed and not value._handle._proof._active


def test_separate_case_instances_do_not_share_failure_state():
    first, _ = active_request()
    second, counts = active_request()
    with pytest.raises(Exception):
        first.execute_group({'prefix_index': 3}, object(), object())
    second.execute_group({'prefix_index': 0}, object(), object())
    assert counts['execute'] == 1 and not second._failed
    assert first._handle._proof is not second._handle._proof
