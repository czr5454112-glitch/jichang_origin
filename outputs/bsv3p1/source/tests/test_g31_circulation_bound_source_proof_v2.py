"""Static float bits/labels only; no real future import, proof or model call."""
import math
import copy
import json
import struct

import pytest

from scripts.experiments.g31_ics_circulation import live_obligation_bound_source_proof as old
from scripts.experiments.g31_ics_circulation import live_obligation_bound_source_proof_v2 as subject
from scripts.experiments.g31_ics_circulation import live_obligation_bound_future_fork_v2 as future
# The fixed runner explicitly includes its qualified source closure; tests/
# is also an explicit PYTHONPATH entry in the reviewed launcher.
import test_g31_circulation_bound_source_proof as old_fixtures


def float_bits(raw):
    return struct.unpack('>d', bytes.fromhex(raw))[0]


@pytest.mark.parametrize('raw', ('7ff0000000000000', 'fff0000000000000',
    '7ff8000000000001', '7ff8000000000002', 'fff8000000000001',
    '0000000000000000', '8000000000000000', '3ff0000000000000'))
def test_exact_static_bits_supported_and_unchanged_check(raw):
    value = float_bits(raw)
    assert subject._atom(value) == (float, bytes.fromhex(raw))
    data = {'value': value}
    seal = subject.DependencySeal({'data': data}, project_prefixes=('synthetic',))
    assert seal.check() >= 1


@pytest.mark.parametrize(('left', 'right'), (
    ('7ff0000000000000', 'fff0000000000000'),
    ('7ff0000000000000', '7fefffffffffffff'),
    ('7ff8000000000001', '7ff8000000000002'),
    ('7ff8000000000001', 'fff8000000000001'),
    ('0000000000000000', '8000000000000000')))
def test_changed_bits_are_rejected(left, right):
    data = {'value': float_bits(left)}
    seal = subject.DependencySeal({'data': data}, project_prefixes=('synthetic',))
    data['value'] = float_bits(right)
    with pytest.raises(ValueError, match='dependency_changed'):
        seal.check()


@pytest.mark.parametrize('value', (math.inf, -math.inf, float_bits('7ff8000000000001')))
def test_nonfinite_JSON_proof_remains_rejected(value):
    assert subject._NAMESPACE['_json_tree'] is old._json_tree
    with pytest.raises(ValueError, match='proof_nonfinite'):
        subject._NAMESPACE['_json_tree']({'value': value})


def test_finite_JSON_stays_unchanged_and_float_subclass_rejected():
    old._json_tree({'value': [0.0, -0.0, 1, True]})
    class CustomFloat(float):
        pass
    with pytest.raises(ValueError, match='unsupported_static_object'):
        subject.DependencySeal({'custom': CustomFloat(1.0)}, project_prefixes=('synthetic',))


def test_unknown_object_retains_exact_deep_dependency_note():
    class Unknown:
        pass
    with pytest.raises(ValueError, match='unsupported_static_object') as caught:
        subject.DependencySeal({'root': {'sub': [Unknown()]}}, project_prefixes=('synthetic',))
    notes = [x for x in caught.value.__notes__ if x.startswith('bound_source_proof_v2 dependency_label=')]
    assert notes == ['bound_source_proof_v2 dependency_label=root:root:value:item']


def test_same_nan_bits_at_new_object_preserve_value_binding():
    data = {'value': float_bits('7ff8000000000001')}
    seal = subject.DependencySeal({'data': data}, project_prefixes=('synthetic',))
    data['value'] = float_bits('7ff8000000000001')
    assert seal.check() >= 1


def test_integer_bool_and_signedzero_identity_not_relaxed():
    assert not subject.DependencySeal._same(1, True)
    assert not subject.DependencySeal._same(0.0, -0.0)
    assert subject.DependencySeal._same(math.inf, math.inf)


def test_full_source_binding_and_original_module_unchanged():
    before = dict(vars(old))
    report = subject.source_proof()
    assert report['same_proof_JSON_finite_guard']
    assert not report['dependency_walk_or_class_namespace_removed']
    assert set(vars(old)) == set(before) and all(vars(old)[k] is v for k, v in before.items())
    assert future.source_proof()['same_original_fork_resume_cut_core']


def test_private_walk_replacement_rejected(monkeypatch):
    monkeypatch.setattr(subject.DependencySeal, '_global_uses', lambda *args: None)
    with pytest.raises(ValueError, match='full_dependency_walk'):
        subject.source_proof()


def test_future_static_binding_replacement_rejected(monkeypatch):
    monkeypatch.setitem(future._NAMESPACE, '_roots', lambda value: {})
    with pytest.raises(ValueError, match='one_private_binding'):
        future.source_proof()


def factory_with_static_inf(tmp_path):
    # The helper creates synthetic Python definitions only. As in its frozen
    # fake factory, audit counters are explicitly external fixture state;
    # the finite proof and nonfinite algorithm sentinel are sealed roots.
    module = old_fixtures.make_project('''
def _source_inventory():
    calls.append('inventory')
    return copy.deepcopy(PROOF)
def source_proof():
    calls.append('loaded')
    return copy.deepcopy(_source_inventory())
''', copy=copy, calls=[], PROOF={'schema': 'fake', 'tree': [True, 1, -0.0]},
        SENTINELS={'floor': math.inf})
    path = tmp_path/'source.py'
    path.write_text('fixed synthetic source\n', encoding='utf8')
    bound = subject.bind_declared(module.source_proof,
        {'original': module.source_proof, 'inventory': module._source_inventory,
         'proof': module.PROOF, 'static_algorithm_sentinel': module.SENTINELS},
        (path,), project_prefixes=('synthetic.closed_dependency',))
    return module, bound


def test_v2_factory_inf_cold_once_warm_exact_fresh_then_close(tmp_path):
    module, bound = factory_with_static_inf(tmp_path)
    assert module.calls == ['loaded', 'inventory']
    assert type(bound) is subject.RequestStaticProof
    assert type(bound._dependencies) is subject.DependencySeal
    before = json.dumps(module.PROOF, allow_nan=False, sort_keys=True).encode('utf8')
    proof = bound.source_proof()
    assert json.dumps(proof, allow_nan=False, sort_keys=True).encode('utf8') == before
    assert proof is not module.PROOF and proof is not bound._proof
    assert proof['tree'] is not module.PROOF['tree'] and proof['tree'] is not bound._proof['tree']
    proof['tree'][0] = False
    assert json.dumps(bound._proof, allow_nan=False, sort_keys=True).encode('utf8') == before
    assert module.calls == ['loaded', 'inventory', 'loaded']
    assert bound.description()['cold_original_proof_calls'] == 1
    assert bound.description()['proof_uses'] == 1
    assert bound.description()['schema'] == subject.VERSION
    bound.close()
    assert not bound.description()['active']
    with pytest.raises(ValueError, match='closed_or_invalidated'):
        bound.source_proof()


def test_v2_factory_inf_bits_mutation_warm_rejects_and_permanently_revokes(tmp_path):
    module, bound = factory_with_static_inf(tmp_path)
    assert module.calls == ['loaded', 'inventory']
    module.SENTINELS['floor'] = -math.inf
    with pytest.raises(ValueError, match='dependency_changed'):
        bound.source_proof()
    assert not bound.description()['active'] and bound.description()['proof_uses'] == 0
    assert module.calls.count('inventory') == 1
    module.SENTINELS['floor'] = math.inf
    with pytest.raises(ValueError, match='closed_or_invalidated'):
        bound.source_proof()
    assert module.calls.count('inventory') == 1
