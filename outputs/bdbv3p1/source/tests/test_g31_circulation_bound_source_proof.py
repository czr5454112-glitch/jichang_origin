"""Synthetic execution only; one real-definition import, no real proof/model/native execution."""
import copy
import os
from pathlib import Path
from types import FunctionType, ModuleType

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_bound_source_proof as subject
from scripts.experiments.g31_ics_circulation import live_obligation_bound_future_fork as adapter


def fake(tmp_path):
    module = ModuleType('synthetic.external')
    module.__dict__.update(copy=copy, calls=[], PROOF={'schema': 'fake', 'tree': [True, 1, -0.0]},
                           loaded_error=[None], current=True, dynamic=[])
    exec('''
def loaded():
    calls.append('loaded')
    if loaded_error[0] is not None:
        raise loaded_error[0]
def _source_inventory():
    calls.append('inventory')
    return copy.deepcopy(PROOF)
def source_proof():
    loaded()
    return copy.deepcopy(_source_inventory())
def _cut(state):
    dynamic.append('cut')
    if not state['current']:
        raise ValueError('dynamic_current')
def fork_later_action(state, action):
    source_proof()
    _cut(state)
    child=copy.deepcopy(state)
    child['later']=action
    return child
def resume_future_later(branch):
    source_proof()
    _cut(branch)
    if branch.get('consumed'):
        raise ValueError('dynamic_consumed')
    branch['consumed']=True
    return copy.deepcopy(branch)
''', module.__dict__)
    path = tmp_path/'source.py'
    path.write_text('fixed source\n', encoding='utf8')
    roots = {'original': module.source_proof, 'inventory': module._source_inventory,
             'loaded': module.loaded, 'proof': module.PROOF,
             'fork': module.fork_later_action, 'resume': module.resume_future_later,
             'cut': module._cut}
    # Synthetic external helpers have deliberate audit counters. Production
    # uses the project namespace and recursively seals its actual dependencies.
    bound = subject.bind_declared(module.source_proof, roots, (path,), project_prefixes=('synthetic.project',))
    return module, bound, path


def test_one_cold_inventory_65_loaded_checks_and_independent_returns(tmp_path):
    module, bound, _ = fake(tmp_path)
    assert module.calls == ['loaded', 'inventory']
    first = bound.source_proof()
    first['tree'][0] = False
    for _ in range(64):
        assert bound.source_proof() == module.PROOF
    assert module.calls.count('inventory') == 1
    assert module.calls.count('loaded') == 66
    assert bound.description()['proof_uses'] == 65
    bound.close()


def test_original_code_and_globals_unmodified(tmp_path):
    module, bound, _ = fake(tmp_path)
    before = dict(vars(module))
    assert bound._compiled.__code__ is module.source_proof.__code__
    assert bound._compiled.__defaults__ is module.source_proof.__defaults__
    assert bound._compiled.__closure__ is module.source_proof.__closure__
    bound.source_proof()
    assert tuple(vars(module)) == tuple(before)
    assert all(vars(module)[key] is value for key, value in before.items())
    assert bound._compiled.__globals__ is not module.source_proof.__globals__


def test_66th_use_rejects_and_revokes(tmp_path):
    _, bound, _ = fake(tmp_path)
    for _ in range(65):
        bound.source_proof()
    with pytest.raises(ValueError, match='declared65'):
        bound.source_proof()
    assert not bound.description()['active']


def test_closed_request_rejects(tmp_path):
    _, bound, _ = fake(tmp_path)
    bound.close()
    with pytest.raises(ValueError, match='closed_or_invalidated'):
        bound.source_proof()


@pytest.mark.parametrize('field,value', [('_pid', -1), ('_thread', -1)])
def test_process_thread_fail_closed(tmp_path, field, value):
    _, bound, _ = fake(tmp_path)
    setattr(bound, field, value)
    with pytest.raises(ValueError, match='process_or_thread'):
        bound.source_proof()
    assert not bound.description()['active']


def test_same_mtime_length_changed_source_rejected(tmp_path):
    _, bound, path = fake(tmp_path)
    stamp = path.stat()
    path.write_text('other source\n', encoding='utf8')
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    with pytest.raises(ValueError, match='source_bytes_changed'):
        bound.source_proof()


def test_missing_source_rejected(tmp_path):
    _, bound, path = fake(tmp_path)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        bound.source_proof()
    assert not bound.description()['active']


def test_cached_mutable_proof_rejected_not_returned(tmp_path):
    _, bound, _ = fake(tmp_path)
    bound._proof['tree'][0] = False
    with pytest.raises(ValueError, match='dependency_changed'):
        bound.source_proof()


def test_cached_proof_root_replacement_rejected(tmp_path):
    _, bound, _ = fake(tmp_path)
    bound._proof = copy.deepcopy(bound._proof)
    with pytest.raises(ValueError, match='cached_proof_root_changed'):
        bound.source_proof()


@pytest.mark.parametrize('value', [0.0, True])
def test_signed_zero_or_type_mutation_rejected(tmp_path, value):
    module, bound, _ = fake(tmp_path)
    module.PROOF['tree'][2] = value
    with pytest.raises(ValueError, match='dependency_changed'):
        bound.source_proof()


@pytest.mark.parametrize('which', ['original', 'loaded', 'inventory'])
def test_function_code_change_invalidates(tmp_path, which):
    module, bound, _ = fake(tmp_path)
    target = {'original': module.source_proof, 'loaded': module.loaded,
              'inventory': module._source_inventory}[which]
    def replacement():
        return {'bad': True}
    target.__code__ = replacement.__code__
    with pytest.raises(ValueError, match='dependency_changed'):
        bound.source_proof()


def test_original_loaded_exception_identity_preserved_and_revoked(tmp_path):
    module, bound, _ = fake(tmp_path)
    error = RuntimeError('original loaded rejection')
    module.loaded_error[0] = error
    with pytest.raises(RuntimeError) as observed:
        bound.source_proof()
    assert observed.value is error
    assert not bound.description()['active']


def test_private_inventory_replacement_rejected_before_invocation(tmp_path):
    _, bound, _ = fake(tmp_path)
    called = []
    bound._globals['_source_inventory'] = lambda: called.append(True)
    with pytest.raises(ValueError, match='private_complete_globals'):
        bound.source_proof()
    assert not called


def test_private_compiled_function_replacement_not_executed(tmp_path):
    _, bound, _ = fake(tmp_path)
    called = []
    bound._compiled = lambda: called.append(True)
    with pytest.raises(ValueError, match='private_original_code_binding'):
        bound.source_proof()
    assert not called


def test_full_globals_new_unused_binding_rejected(tmp_path):
    module, bound, _ = fake(tmp_path)
    module.unreviewed = 1
    with pytest.raises(ValueError, match='private_complete_globals'):
        bound.source_proof()


def make_project(code, **values):
    module = ModuleType('synthetic.project')
    module.__dict__.update(values)
    exec(code, module.__dict__)
    return module


def seal(roots):
    return subject.DependencySeal(roots, project_prefixes=('synthetic.project',))


def test_referenced_mutable_global_deep_change_rejected():
    module = make_project('def f(): return TABLE["parts"][0]\n', TABLE={'parts': [1]})
    check = seal({'f': module.f})
    module.TABLE['parts'][0] = 2
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


def test_nested_code_global_dependency_rejected():
    module = make_project('def f(): return [VALUES[0] for _ in (1,)]\n', VALUES=[1])
    check = seal({'f': module.f})
    module.VALUES.append(2)
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


def test_referenced_module_function_and_mutable_attribute_rejected():
    dependency = make_project('def helper(): return VALUES[0]\n', VALUES=[1])
    module = make_project('def f(): return dep.helper()\n', dep=dependency)
    check = seal({'f': module.f})
    dependency.VALUES[0] = 9
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


def test_module_attribute_function_replacement_rejected():
    dependency = make_project('def helper(): return 1\n')
    module = make_project('def f(): return dep.helper()\n', dep=dependency)
    check = seal({'f': module.f})
    dependency.helper = lambda: 1
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


@pytest.mark.parametrize('change', ['default', 'kwdefault', 'closure'])
def test_default_kwdefault_closure_mutation(change):
    hidden = [3]
    def function(arg=[1], *, option={'x': 2}):
        return arg, option, hidden
    check = seal({'function': function})
    if change == 'default':
        function.__defaults__[0].append(4)
    elif change == 'kwdefault':
        function.__kwdefaults__['option']['x'] = 4
    else:
        hidden.append(4)
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


def test_declared_super_method_code_rejected():
    module = make_project('''
class Parent:
    def method(self): return 1
class Child(Parent):
    def method(self): return super().method()
''')
    check = seal({'class': module.Child})
    module.Parent.method.__code__ = (lambda self: 2).__code__
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


def test_parts_map_extra_or_replaced_callable_rejected():
    module = make_project('def f(): return 1\n')
    parts = {'tail': module.f}
    check = seal({'PARTS': parts})
    parts['extra'] = module.f
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


def test_unknown_static_instance_rejects_not_skipped():
    class Unknown:
        pass
    with pytest.raises(ValueError, match='unsupported_static_object'):
        seal({'unknown': Unknown()})


def test_cyclic_mutable_dependency_supported_and_mutation_rejected():
    value = []
    value.append(value)
    check = seal({'cyclic': value})
    check.check()
    value.append(1)
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


def test_namespace_numeric_key_type_not_coerced():
    value = {1: 'x'}
    check = seal({'map': value})
    del value[1]
    value[True] = 'x'
    with pytest.raises(ValueError, match='dependency_changed'):
        check.check()


def test_fake_future_exact_code_dynamic_cut_and_consumed_retained(tmp_path):
    module, proof, _ = fake(tmp_path)
    before = dict(vars(module))
    request = adapter.BoundFutureRequest(module, proof)
    assert request._calls[0].__code__ is module.fork_later_action.__code__
    assert request._calls[1].__code__ is module.resume_future_later.__code__
    with pytest.raises(ValueError, match='dynamic_current'):
        request.facade.fork_later_action({'current': False}, 'native_default')
    child = request.facade.fork_later_action({'current': True}, 'prefer_8')
    result = request.facade.resume_future_later(child)
    assert result['later'] == 'prefer_8' and result['consumed'] is True
    with pytest.raises(ValueError, match='dynamic_consumed'):
        request.facade.resume_future_later(child)
    assert len(module.dynamic) == 4
    assert module.calls.count('inventory') == 1
    assert all(vars(module)[k] is v for k, v in before.items())
    request.close()


def test_private_future_globals_invalidated_before_operation(tmp_path):
    module, proof, _ = fake(tmp_path)
    request = adapter.BoundFutureRequest(module, proof)
    request._namespace['_cut'] = lambda state: None
    with pytest.raises(ValueError, match='one_private_future_global_replacement'):
        request.facade.fork_later_action({'current': True}, 'prefer_8')
    assert not module.dynamic
    assert not proof.description()['active']
    request._namespace['_cut'] = module._cut
    with pytest.raises(ValueError, match='closed_or_invalidated'):
        request.facade.fork_later_action({'current': True}, 'prefer_8')


def test_no_disassembly_during_warm_checks(tmp_path, monkeypatch):
    _, proof, _ = fake(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError('warm disassembly')
    monkeypatch.setattr(subject.dis, 'get_instructions', forbidden)
    proof.source_proof()


def test_close_checks_source_then_revokes_even_on_failure(tmp_path):
    _, proof, path = fake(tmp_path)
    path.write_text('changed\n', encoding='utf8')
    with pytest.raises(ValueError, match='source_bytes_changed'):
        proof.close()
    assert not proof.description()['active']


def test_plain_proof_dictionary_cannot_bind_future_request():
    with pytest.raises(AttributeError):
        adapter.BoundFutureRequest(ModuleType('bad'), {'proof': True})


def test_real_operation_code_and_all_other_globals_without_calling_proof():
    # Importing static definitions is not executing a model/proof. The owned
    # pure runner additionally forbids entry into the real source_proof code.
    from scripts.experiments.g31_ics_circulation import live_obligation_future_later_fork as real
    class FakeProof:
        def __init__(self):
            self._active = True
            self.source_proof = lambda: (_ for _ in ()).throw(AssertionError('not called'))
        def bind_private_calls(self, functions):
            self.functions = functions
        def close(self):
            self._active = False
    proof = FakeProof()
    before = dict(vars(real))
    request = adapter.BoundFutureRequest(real, proof)
    for clone, original in zip(request._calls, (real.fork_later_action, real.resume_future_later), strict=True):
        assert clone.__code__ is original.__code__
        assert clone.__defaults__ is original.__defaults__
        assert clone.__kwdefaults__ is original.__kwdefaults__
        assert clone.__closure__ is original.__closure__
        assert set(clone.__globals__) == set(original.__globals__)
        assert all(clone.__globals__[key] is value for key, value in original.__globals__.items()
                   if key != 'source_proof')
        assert clone.__globals__['_cut'] is real._cut
        assert clone.__globals__['core'] is real.core
    assert all(vars(real)[key] is value for key, value in before.items())
    request.close()
