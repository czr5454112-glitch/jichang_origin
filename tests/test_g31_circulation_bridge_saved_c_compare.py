import ast
from copy import deepcopy
import inspect
import math
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import bridge_saved_c_compare as c


def row(value, endpoint='observe_protocol'):
    return {'ordinal': 0, 'endpoint': endpoint, 'args': ['A'], 'kwargs': {},
            'before': 1.0, 'after': 1.0, 'result': value}


@pytest.mark.parametrize('left,right,expected', [
    ({'a': 1, 'b': 2}, {'a': 1, 'b': 2}, True),
    ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}, False),
    (True, 1, False), (1, 1.0, False), (0.0, -0.0, False),
    ([1, 2], [2, 1], False), ([1, [False]], [1, [0]], False),
    ('汉字🌍', '汉字🌍', True), (None, None, True),
    ({'x': [1.25, None, True, -0.0]}, {'x': [1.25, None, True, -0.0]}, True),
    ({'x': 1}, {'x': 1, 'extra': None}, False),
])
def test_ordered_typed_domain(left, right, expected):
    a, b = row(left), row(right)
    before = deepcopy((a, b))
    assert c.semantic_equal(a, b) is expected
    assert c.semantic_equal(a, b) is c.frozen.semantic_equal(a, b)
    assert c._SEMANTIC_API(a) == c._SEMANTIC_API(before[0])
    assert c._SEMANTIC_API(b) == c._SEMANTIC_API(before[1])


def test_only_original_native_wall_excluded():
    a = row({'wall_seconds': .1, 'now': 1.0}, 'advance_to')
    b = row({'wall_seconds': 9.0, 'now': 1.0}, 'advance_to')
    assert c.semantic_equal(a, b)
    b['result']['now'] = 1
    assert not c.semantic_equal(a, b)
    b['result']['now'] = 1.0
    b['wall_seconds'] = .1
    assert not c.semantic_equal(a, b)


@pytest.mark.parametrize('wall', [True, -1, float('nan'), float('inf'), '1', None])
def test_invalid_native_wall_rejected(wall):
    a = row({'wall_seconds': wall, 'now': 1.0}, 'advance_to')
    with pytest.raises(ValueError):
        c.semantic_equal(a, a)
    with pytest.raises(ValueError):
        c.frozen.semantic_equal(a, a)


def test_missing_native_wall_rejected():
    a = row({'now': 1.0}, 'advance_to')
    with pytest.raises(KeyError):
        c.semantic_equal(a, a)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf')])
def test_nonfinite_elsewhere_not_hidden(value):
    with pytest.raises(ValueError):
        c.semantic_equal(row(value), row(value))


def test_original_encoder_fallback_not_general_python_equality():
    # These are outside the decoded string-key domain. Restoration must keep
    # the old encoder's exact behavior rather than claim a broader new proof.
    a, b = row({1: 'a'}), row({'1': 'a'})
    assert c.semantic_equal(a, b) == (c._SEMANTIC_API(a) == c._SEMANTIC_API(b))
    with pytest.raises(TypeError):
        c.semantic_equal(row(object()), row(object()))


def test_complete_original_namespace_and_code_retained():
    original = c.frozen.bind
    before = dict(original.__globals__)
    fn = c.binder_function()
    assert fn.__code__ is original.__code__
    assert fn.__closure__ is original.__closure__
    assert fn.__defaults__ is original.__defaults__
    assert set(fn.__globals__) == set(before)
    assert {key for key in before if fn.__globals__[key] is not before[key]} == {'SharedReads', 'semantic_equal'}
    assert fn.__globals__['SharedReads'] is c.progress.SharedReads
    assert fn.__globals__['semantic_equal'] is c.semantic_equal
    assert fn.__globals__['replay_type'] is c.frozen.replay_type
    assert fn.__globals__['Path'] is before['Path']
    assert all(original.__globals__[key] is value for key, value in before.items())
    assert c.source_proof()['actor_deepcopy_unchanged'] is True


def test_comparison_expression_is_exact_inverse_of_old():
    expression = ast.parse(inspect.getsource(c.semantic_equal)).body[0].body[0].value
    for node in ast.walk(expression):
        if isinstance(node, ast.Name) and node.id == '_SEMANTIC_API':
            node.id = 'semantic_api'
    expected = ast.parse('semantic_api(a) == semantic_api(b)', mode='eval').body
    assert ast.dump(expression, include_attributes=False) == ast.dump(expected, include_attributes=False)


def test_actual_prefix_consume_clone_uses_C_without_skipping_read_or_hash():
    original = c.frozen.original.PrefixComparison.consume
    a = row({'a': 1.0, 'b': -0.0})
    calls = []
    fake_base = SimpleNamespace(sha=lambda path: calls.append(('sha', str(path))) or 'bound',
                               gzread=lambda path: calls.append(('read', str(path))) or a)
    consume, proof = c.frozen.transformed(original,
        [('semantic_api(old) == semantic_api(row)', 'semantic_equal(old, row)')],
        {**original.__globals__, 'base': fake_base, 'semantic_equal': c.semantic_equal})
    instance = SimpleNamespace(index=0, manifest=[{'path': '000000.json.gz', 'sha256': 'bound',
        'endpoint': 'observe_protocol'}], directory=Path('synthetic'), last_after=None)
    consume(instance, deepcopy(a))
    assert instance.index == 1 and instance.last_after == 1.0
    assert [x[0] for x in calls] == ['sha', 'read']
    assert proof['inverse_ast_exact'] is True
    instance.index = 0
    b = deepcopy(a); b['result']['a'] = 1
    with pytest.raises(ValueError):
        consume(instance, b)
    assert instance.index == 0


@pytest.mark.parametrize('module,name', [
    (c.frozen.original, 'semantic_api'), (c.frozen, 'bind'),
    (c.frozen, 'replay_type'), (c.progress, 'bind'), (c.progress, 'SharedReads')])
def test_identity_drift_fails_before_binding(monkeypatch, module, name):
    monkeypatch.setattr(module, name, object())
    with pytest.raises(ValueError):
        c.binder_function()


def test_no_actor_copy_replacement_in_candidate():
    source = inspect.getsource(c)
    assert 'json.loads' not in source and 'deepcopy(' not in source
    assert c.binder_function().__globals__['replay_type'] is c.frozen.replay_type
