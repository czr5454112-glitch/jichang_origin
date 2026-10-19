"""Isolated pinned stdlib declarations and synthetic proofs; no real proof/model execution."""
import builtins
import copy
import json
import math
from types import FunctionType, ModuleType

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_bound_source_proof as old
from scripts.experiments.g31_ics_circulation import live_obligation_bound_source_proof_v2 as v2
from scripts.experiments.g31_ics_circulation import live_obligation_bound_source_proof_v3 as subject
from scripts.experiments.g31_ics_circulation import live_obligation_bound_future_fork_v3 as future


@pytest.fixture
def feature(tmp_path, monkeypatch):
    # Never mutate the actual __future__ module or any frozen project module.
    path = tmp_path/'__future__.py'
    raw = subject._FEATURE_PATH.read_bytes()
    path.write_bytes(raw)
    module = ModuleType('__future__')
    module.__dict__.update(__builtins__=builtins.__dict__, __file__=str(path))
    exec(compile(raw, str(path), 'exec', dont_inherit=True, optimize=0), module.__dict__)
    monkeypatch.setattr(subject, '_FEATURE_MODULE', module)
    monkeypatch.setattr(subject, '_FEATURE_CLASS', module._Feature)
    monkeypatch.setattr(subject, '_FEATURE_SINGLETON', module.annotations)
    monkeypatch.setattr(subject, '_FEATURE_PATH', path)
    return module, path


def seal(feature):
    module, _ = feature
    return subject.DependencySeal({'feature': module.annotations}, project_prefixes=('synthetic.project',))


def factory(feature, tmp_path):
    module, _ = feature
    project = ModuleType('synthetic.external')
    project.__dict__.update(copy=copy, calls=[], PROOF={'finite': [True, 1, -0.0]}, FEATURE=module.annotations)
    exec('''
def _source_inventory():
    calls.append('inventory')
    return copy.deepcopy(PROOF)
def source_proof():
    calls.append('loaded')
    return copy.deepcopy(_source_inventory())
''', project.__dict__)
    source = tmp_path/'fixed.py'
    source.write_text('synthetic fixed source\n', encoding='utf8')
    bound = subject.bind_declared(project.source_proof,
        {'original': project.source_proof, 'proof': project.PROOF, 'feature': project.FEATURE},
        (source,), project_prefixes=('synthetic.project',))
    return project, bound


def test_exact_feature_complete_records_and_one_reference_compile(feature, monkeypatch):
    calls = []
    original = subject._reference_namespace
    def reference(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(subject, '_reference_namespace', reference)
    result = seal(feature)
    assert len(result._features) == 1 and len(calls) == 1
    assert result.check() >= 15 and len(calls) == 1
    assert {row[0] for row in result._records} >= {'binding', 'namespace', 'class', 'function'}
    assert any(row[0] == 'binding' and row[2] == 'repr' and row[3] is builtins.repr for row in result._records)


def test_aliases_do_not_recompile_or_drop_instance_record(feature):
    module, _ = feature
    result = subject.DependencySeal({'a': module.annotations, 'b': [module.annotations]}, project_prefixes=('synthetic.project',))
    assert len(result._features) == 1
    assert result.check() >= 15


@pytest.mark.parametrize('kind', ('custom', 'subclass', 'same_class_new_instance'))
def test_noncanonical_instances_rejected(feature, kind):
    module, _ = feature
    if kind == 'custom':
        class Custom:
            optional = (3, 7, 0, 'beta', 1)
            mandatory = None
            compiler_flag = 0x1000000
        value = Custom()
    elif kind == 'subclass':
        class Child(module._Feature):
            pass
        value = Child((3, 7, 0, 'beta', 1), None, 0x1000000)
    else:
        value = module._Feature((3, 7, 0, 'beta', 1), None, 0x1000000)
    with pytest.raises(ValueError, match='canonical_singleton|unsupported_static_object'):
        subject.DependencySeal({'feature': value}, project_prefixes=('synthetic.project',))


@pytest.mark.parametrize('change', ('optional_list', 'optional_bool', 'mandatory', 'flag_bool', 'flag_value', 'missing', 'extra', 'reorder'))
def test_wrong_exact_instance_fields_reject_cold(feature, change):
    fields = vars(feature[0].annotations)
    if change == 'optional_list': fields['optional'] = [3, 7, 0, 'beta', 1]
    elif change == 'optional_bool': fields['optional'] = (3, 7, False, 'beta', 1)
    elif change == 'mandatory': fields['mandatory'] = (3, 12, 0, 'final', 0)
    elif change == 'flag_bool': fields['compiler_flag'] = True
    elif change == 'flag_value': fields['compiler_flag'] = 0
    elif change == 'missing': del fields['optional']
    elif change == 'extra': fields['extra'] = None
    else: fields['optional'] = fields.pop('optional')
    with pytest.raises(ValueError, match='instance_fields'):
        seal(feature)


@pytest.mark.parametrize('change', ('code_filename', 'code_firstline', 'code_constants', 'defaults', 'kwdefaults', 'annotations', 'function_dict', 'extra_class_slot', 'shadow_builtin'))
def test_precold_class_method_or_namespace_tamper_rejects(feature, change):
    module, _ = feature
    function = module._Feature.__repr__
    if change == 'code_filename': function.__code__ = function.__code__.replace(co_filename='not-the-pinned-file.py')
    elif change == 'code_firstline': function.__code__ = function.__code__.replace(co_firstlineno=function.__code__.co_firstlineno + 1)
    elif change == 'code_constants': function.__code__ = function.__code__.replace(co_consts=function.__code__.co_consts + ('extra',))
    elif change == 'defaults': function.__defaults__ = (None,)
    elif change == 'kwdefaults': function.__kwdefaults__ = {'extra': None}
    elif change == 'annotations': function.__annotations__['return'] = 'fake'
    elif change == 'function_dict': function.extra = True
    elif change == 'extra_class_slot': module._Feature.extra = True
    else: module.repr = lambda value: 'fake'
    with pytest.raises(ValueError, match='v3_feature_'):
        seal(feature)


@pytest.mark.parametrize('change', ('canonical', 'class_slot', 'instance_type', 'dict_identity', 'method_code', 'class_namespace', 'module_namespace', 'source_bytes'))
def test_postcold_mutation_rejects(feature, change):
    module, path = feature
    result = seal(feature)
    value = module.annotations
    if change == 'canonical': module.annotations = module._Feature((3, 7, 0, 'beta', 1), None, 0x1000000)
    elif change == 'class_slot': module._Feature = type('Replacement', (), {})
    elif change == 'instance_type':
        class Replacement(module._Feature):
            pass
        value.__class__ = Replacement
    elif change == 'dict_identity': value.__dict__ = dict(vars(value))
    elif change == 'method_code': module._Feature.getOptionalRelease.__code__ = module._Feature.getMandatoryRelease.__code__
    elif change == 'class_namespace': module._Feature.extra = True
    elif change == 'module_namespace': module.EXTRA = True
    else: path.write_bytes(path.read_bytes() + b'\n# changed\n')
    with pytest.raises(ValueError, match='changed|source_bytes'):
        result.check()


def test_precold_source_bytes_fail_before_exec(feature):
    _, path = feature
    path.write_bytes(path.read_bytes() + b'\nraise RuntimeError("must not execute")\n')
    with pytest.raises(ValueError, match='stdlib_source_bytes'):
        seal(feature)


def test_reference_uses_fresh_globals_not_live_module(feature):
    module, path = feature
    result = subject._reference_namespace(path, subject.FEATURE_SOURCE_SHA256)
    assert result is not vars(module)
    assert result['_Feature'] is not module._Feature
    assert result['annotations'] is not module.annotations
    assert result['_Feature'].__repr__.__globals__ is result
    assert vars(result['annotations']) == vars(module.annotations)


@pytest.mark.parametrize('where', ('file', 'name', 'namespace_key', 'class_module'))
def test_precold_custom_metadata_rejects_without_user_hooks(feature, where):
    calls = []
    class Hostile:
        def __fspath__(self):
            calls.append('path'); raise AssertionError('custom path hook')
        def __eq__(self, other):
            calls.append('equal'); raise AssertionError('custom equality hook')
        def startswith(self, prefix):
            calls.append('prefix'); raise AssertionError('custom key hook')
        __hash__ = object.__hash__
    module, _ = feature
    value = Hostile()
    if where == 'file': module.__file__ = value
    elif where == 'name': module.__name__ = value
    elif where == 'namespace_key': vars(module)[value] = None
    else: module._Feature.__module__ = value
    with pytest.raises(ValueError, match='v3_feature_'):
        seal(feature)
    assert calls == []


def test_getters_and_repr_never_used_as_instance_fact_sources(feature):
    module, _ = feature
    # An injected getter is rejected by full-code comparison, without calling it.
    calls = []
    def forbidden(self):
        calls.append(True)
        raise AssertionError('never invoke')
    module._Feature.getOptionalRelease = forbidden
    with pytest.raises(ValueError, match='feature_full_method_code'):
        seal(feature)
    assert calls == []


def test_full_factory_one_synthetic_cold_one_warm_exact_fresh_close(feature, tmp_path):
    project, bound = factory(feature, tmp_path)
    assert project.calls == ['loaded', 'inventory']
    assert type(bound) is subject.RequestStaticProof
    assert len(bound._dependencies._features) == 1 and not bound._proof_seal._features
    target = json.dumps(project.PROOF, sort_keys=True, allow_nan=False).encode()
    result = bound.source_proof()
    assert json.dumps(result, sort_keys=True, allow_nan=False).encode() == target
    assert result is not project.PROOF and result is not bound._proof and result['finite'] is not bound._proof['finite']
    result['finite'][0] = False
    assert json.dumps(bound._proof, sort_keys=True, allow_nan=False).encode() == target
    assert project.calls == ['loaded', 'inventory', 'loaded']
    bound.close()
    assert not bound.description()['active']


def test_factory_warm_mutation_permanently_revokes_after_restore(feature, tmp_path):
    project, bound = factory(feature, tmp_path)
    feature[0].annotations.compiler_flag = 0
    with pytest.raises(ValueError, match='instance_fields'):
        bound.source_proof()
    feature[0].annotations.compiler_flag = 0x1000000
    with pytest.raises(ValueError, match='closed_or_invalidated'):
        bound.source_proof()
    assert project.calls.count('inventory') == 1 and bound.description()['proof_uses'] == 0


def test_unknown_deep_dependency_label_retained():
    class Custom:
        pass
    with pytest.raises(ValueError, match='unsupported_static_object') as caught:
        subject.DependencySeal({'root': {'sub': [Custom()]}}, project_prefixes=('synthetic.project',))
    assert caught.value.__notes__ == ['bound_source_proof_v3 dependency_label=root:root:value:item']


def test_float_JSON_original_walk_and_future_private_code_preserved():
    before = dict(vars(old))
    proof = subject.source_proof()
    assert proof['v2_exact_float64bits_and_finite_JSON_unchanged']
    assert subject._atom is v2._atom and subject.DependencySeal._same is v2._same_exact
    assert subject._atom(math.inf) == (float, bytes.fromhex('7ff0000000000000'))
    with pytest.raises(ValueError, match='proof_nonfinite'):
        subject._NAMESPACE['_json_tree']({'x': math.inf})
    assert future.source_proof()['same_original_fork_resume_cut_core']
    assert set(vars(old)) == set(before) and all(vars(old)[k] is v for k, v in before.items())


def test_future_globals_replacement_rejected(monkeypatch):
    monkeypatch.setitem(future._NAMESPACE, '_roots', lambda value: {})
    with pytest.raises(ValueError, match='one_private_binding'):
        future.source_proof()
