"""Synthetic orchestration/monitor tests; no real proof or model imports."""
import copy
from pathlib import Path
from types import FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import diagnose_bound_source_proof_bind as subject


class FakeHandle:
    def __init__(self):
        self._proof = SimpleNamespace(_proof={'a': [1, True, -0.0]})
        self.calls = []
        self.facade = SimpleNamespace(source_proof=self.warm)

    def description(self):
        return {'dependency_check_records': 7, 'files': {'fake.py': 'abc'}, 'native_authority': False}

    def warm(self):
        self.calls.append('warm')
        return copy.deepcopy(self._proof._proof)

    def close(self):
        self.calls.append('close')


def fake_target(handle):
    return subject.codec.encoded(handle._proof._proof)


def test_success_one_cold_one_warm_saved_before_compare(tmp_path):
    handle = FakeHandle(); factory_calls = []
    def factory():
        factory_calls.append(1)
        return handle
    result = subject.probe(factory, tmp_path, fake_target(handle))
    assert result['status'] == 'exact_one_bind_one_warm'
    assert factory_calls == [1] and handle.calls == ['warm', 'close']
    assert result['cold_bind_requests'] == result['warm_proof_uses'] == 1
    assert result['fresh_returned_root'] and result['close_completed']
    assert (tmp_path/'cold_proof.json').read_bytes() == (tmp_path/'warm_proof.json').read_bytes() == fake_target(handle)
    assert all(type(result[x]) is int and result[x] >= 0 for x in ('cold_bind_ns', 'warm_use_ns', 'close_ns'))


def test_unsupported_bind_retained_not_retried(tmp_path):
    calls = []
    def factory():
        calls.append(1)
        raise ValueError('unsupported_static_object:meaningful_path:CustomThing')
    result = subject.probe(factory, tmp_path, b'{}')
    assert result['status'] == 'unknown_failed_bind_or_use' and result['stage'] == 'cold_bind'
    assert calls == [1] and result['warm_proof_uses'] == 0
    assert 'meaningful_path:CustomThing' in result['error']
    assert not list(tmp_path.iterdir())


def test_cold_target_mismatch_keeps_full_proof_and_closes(tmp_path):
    handle = FakeHandle()
    result = subject.probe(lambda: handle, tmp_path, b'{}')
    assert result['status'] == 'unknown_failed_bind_or_use' and handle.calls == ['close']
    assert result['stage'] == 'cold_proof_export'
    assert (tmp_path/'cold_proof.json').read_bytes() == fake_target(handle)
    assert not (tmp_path/'warm_proof.json').exists()


def test_warm_exception_keeps_cold_and_error(tmp_path):
    handle = FakeHandle()
    def warm():
        raise ValueError('a_real_dependency_changed')
    handle.facade.source_proof = warm
    result = subject.probe(lambda: handle, tmp_path, fake_target(handle))
    assert result['status'] == 'unknown_failed_bind_or_use' and result['warm_proof_uses'] == 1
    assert result['stage'] == 'warm_use' and 'a_real_dependency_changed' in result['error']
    assert (tmp_path/'cold_proof.json').is_file() and handle.calls == ['close']


@pytest.mark.parametrize('wrong', ({'a': [1, True, 0.0]}, {'a': [True, True, -0.0]}))
def test_full_types_signed_zero_not_normalized(tmp_path, wrong):
    handle = FakeHandle(); handle.facade.source_proof = lambda: wrong
    result = subject.probe(lambda: handle, tmp_path, fake_target(handle))
    assert result['status'] == 'unknown_failed_bind_or_use'
    assert (tmp_path/'warm_proof.json').read_bytes() == subject.codec.encoded(wrong)
    assert result['stage'] == 'warm_proof_export'


def test_returning_cache_root_is_not_fresh(tmp_path):
    handle = FakeHandle(); handle.facade.source_proof = lambda: handle._proof._proof
    result = subject.probe(lambda: handle, tmp_path, fake_target(handle))
    assert result['status'] == 'unknown_failed_bind_or_use' and not result['fresh_returned_root']
    assert (tmp_path/'warm_proof.json').is_file()


def test_close_failure_prevents_pass_and_retains_both(tmp_path):
    handle = FakeHandle()
    def close():
        raise ValueError('close_changed_source')
    handle.close = close
    result = subject.probe(lambda: handle, tmp_path, fake_target(handle))
    assert result['status'] == 'unknown_failed_close' and not result['close_completed']
    assert 'close_changed_source' in result['close_error']
    assert (tmp_path/'cold_proof.json').is_file() and (tmp_path/'warm_proof.json').is_file()


def test_existing_export_never_overwrites(tmp_path):
    handle = FakeHandle(); path = tmp_path/'cold_proof.json'; path.write_bytes(b'previous_failed_output')
    result = subject.probe(lambda: handle, tmp_path, fake_target(handle))
    assert result['status'] == 'unknown_failed_bind_or_use' and path.read_bytes() == b'previous_failed_output'
    assert handle.calls == ['close'] and result['warm_proof_uses'] == 0


def test_cold_encoding_failure_still_closes(tmp_path):
    handle = FakeHandle(); handle._proof._proof = {'bad': object()}
    result = subject.probe(lambda: handle, tmp_path, b'{}')
    assert result['status'] == 'unknown_failed_bind_or_use' and result['stage'] == 'cold_proof_export'
    assert handle.calls == ['close']


def fake_future():
    def source_proof():
        return {'proof': 1}
    def inventory():
        return {'proof': 1}
    def model():
        return None
    class Projection:
        def __init__(self):
            raise AssertionError('never constructed')
    core = SimpleNamespace(Projection=Projection, **{name: model for name in
        ('start_conditional', 'advance_to_collection_or_terminal', 'fork_conditional', 'resume_same_action', '_drive')})
    return SimpleNamespace(source_proof=source_proof, _source_inventory=inventory, core=core,
                           fork_later_action=model, resume_future_later=model)


def test_monitor_counts_original_and_private_namespace_separately():
    future = fake_future(); monitor = subject.CallMonitor(future)
    monitor(SimpleNamespace(f_code=future.source_proof.__code__, f_globals=future.source_proof.__globals__), 'call', None)
    monitor(SimpleNamespace(f_code=future.source_proof.__code__, f_globals=dict(future.source_proof.__globals__)), 'call', None)
    monitor(SimpleNamespace(f_code=future._source_inventory.__code__, f_globals={}), 'call', None)
    assert monitor.summary() == {'original_source_proof_calls': 1, 'private_proof_calls': 1,
        'original_inventory_calls': 1, 'blocked_model_calls': []}


@pytest.mark.parametrize('which', ('model', 'constructor'))
def test_monitor_sticky_blocked_even_if_caller_catches(which):
    future = fake_future(); monitor = subject.CallMonitor(future)
    fn = future.core._drive if which == 'model' else future.core.Projection.__init__
    with pytest.raises(RuntimeError, match='forbidden_model_entry'):
        monitor(SimpleNamespace(f_code=fn.__code__), 'call', None)
    assert len(monitor.summary()['blocked_model_calls']) == 1


def test_noncall_profile_event_has_no_effect():
    monitor = subject.CallMonitor(fake_future())
    monitor(SimpleNamespace(), 'return', None)
    assert monitor.summary() == {'original_source_proof_calls': 0, 'private_proof_calls': 0,
        'original_inventory_calls': 0, 'blocked_model_calls': []}


def test_scope_is_only_one_warm_and_no_model():
    scope = subject.fixed_scope()
    assert scope['cold_bind_requests'] == scope['warm_facade_proof_uses'] == scope['maximum_original_source_proof_calls'] == 1
    assert all(scope[k] == 0 for k in ('fork_calls', 'resume_calls', 'engine_constructions', 'model_predictions', 'native_calls', 'custom_data_C_loads'))
    scope['warm_facade_proof_uses'] = 65
    assert subject.fixed_scope()['warm_facade_proof_uses'] == 1
