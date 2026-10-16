"""Planned differential gate for the separately built data-only extension.

Not run by preparation and never builds or imports a circulation simulator.
An explicit reviewed extension path+SHA are required; missing binary fails,
not skips. The saved18 test is a separately scheduled full-fixture readback.
"""
from copy import deepcopy
import gc
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import pytest
from scripts.experiments.g31_ics_circulation import complete_tree_normalizer_candidate as c


@pytest.fixture(scope='module')
def candidate():
    path = os.environ.get('G31_TREE_NORMALIZER_BINARY')
    digest = os.environ.get('G31_TREE_NORMALIZER_SHA256')
    assert path and digest, 'Explicit reviewed binary and SHA are required; this suite does not build.'
    return c.load_candidate(path, digest, c.source_identity())


def exact(a, b):
    if type(a) is not type(b): return False
    if type(a) is dict:
        return list(a) == list(b) and all(exact(a[k], b[k]) for k in a)
    if type(a) is list:
        return len(a) == len(b) and all(exact(x, y) for x, y in zip(a, b))
    if type(a) is float: return a.hex() == b.hex()
    return a == b


def mutable_ids(value):
    result = set()
    def visit(v):
        if type(v) in (dict, list, tuple):
            result.add(id(v))
            for child in (v.values() if type(v) is dict else v): visit(child)
    visit(value)
    return result


def outcome(function, value):
    try: return ('ok', function(value))
    except BaseException as error: return ('error', type(error), error.args)


def equivalent(candidate, value):
    expected = outcome(c.original.normalize, value)
    actual = outcome(candidate.normalize, value)
    assert expected[0] == actual[0]
    if expected[0] == 'error':
        assert expected[1:] == actual[1:]
    else:
        assert exact(expected[1], actual[1])
        assert not (mutable_ids(value) & mutable_ids(actual[1]))
    return actual


def bundle(resources):
    return {'status': 'conditional_model_input', 'contract': {}, 'resources': resources}


@pytest.mark.parametrize('value', [None, True, False, 0, 1, -4, 2**200, '', '中文🌍',
    0., -0., 1.25, 5e-324, sys.float_info.max, [], (), {},
    {'z': [1, 1., True, None, -0.], 'a': ((1, 2), [])},
    bundle({3: {'node': 3, 'tail': (1, 2)}, 0: {'node': 0}}),
    bundle({'3': {'node': 3}, '0': {'node': 0}}), bundle({})])
def test_exact_supported_tree_and_ownership(candidate, value):
    assert equivalent(candidate, value)[0] == 'ok'


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -float('inf'),
    {1: None}, bundle({-1: {'node': -1}}), bundle({'01': {'node': 1}}),
    bundle({'+1': {'node': 1}}), bundle({' 1': {'node': 1}}), bundle({'١': {'node': 1}}),
    bundle({'': {'node': 0}}), bundle({True: {'node': 1}}),
    bundle({0: {'node': 0}, '2': {'node': 2}}), bundle({1: {'node': True}}),
    bundle({1: {'node': 1.}}), bundle({1: {'node': 2}}), bundle({1: {}}), bundle({1: []}),
    {'resources': {1: {'node': 1}}}, {'status': 'conditional_model_input', 'contract': [], 'resources': {1: {'node': 1}}}])
def test_original_domain_and_error_args(candidate, value):
    assert equivalent(candidate, value)[0] == 'error'


@pytest.mark.parametrize('text', ['\ud800', '\udfff', '\ud83c\udf0d', '🌍'])
def test_surrogates_normalize_then_original_utf8_boundary(candidate, text):
    value = {text: [text]}
    result = equivalent(candidate, value)[1]
    expected = outcome(c.original.artifact_encode, value)
    actual = outcome(c.original.wire.artifact_encode, result)
    assert expected == actual


def test_shared_alias_copied_per_occurrence_and_between_calls(candidate):
    leaf = {'a': [1, -0.]}; value = [leaf, leaf, (leaf,)]
    first = equivalent(candidate, value)[1]; second = candidate.normalize(value)
    assert first[0] is not first[1] and first[0]['a'] is not first[1]['a']
    assert not (mutable_ids(first) & mutable_ids(second))
    first[0]['a'].append('changed')
    assert value[0]['a'] == [1, -0.] and first[1]['a'] == [1, -0.]


@pytest.mark.parametrize('kind', ['list', 'dict', 'tuple_indirect'])
def test_active_cycle_not_global_alias(candidate, kind):
    if kind == 'dict': value = {}; value['x'] = value
    elif kind == 'list': value = []; value.append(value)
    else: child = []; value = (child,); child.append(value)
    assert equivalent(candidate, value)[2] == ('initial_json_v3:cycle',)


def nested(value, levels):
    for _ in range(levels): value = [value]
    return value


def test_depth_exact_boundary_and_error_priority(candidate):
    assert equivalent(candidate, nested(None, 64))[0] == 'ok'
    assert equivalent(candidate, nested(float('nan'), 65))[2] == ('initial_json_v3:tree_limit',)
    assert equivalent(candidate, nested(float('nan'), 64))[2] == ('initial_json_v3:nonfinite',)


def test_exact_node_limit_counts_root_and_emitted_keys(candidate):
    # The root and the emitted key count; tuple-to-list visits every occurrence.
    count = c.original.wire.MAX_ARTIFACT_NODES
    value = {'a': (None,) * (count-3)}  # dict + key + tuple + members == limit
    assert equivalent(candidate, value)[0] == 'ok'
    value['a'] += (None,)
    assert equivalent(candidate, value)[2] == ('initial_json_v3:tree_limit',)


def test_integer_string_conversion_limit_matches_and_restores(candidate):
    previous = sys.get_int_max_str_digits()
    try:
        sys.set_int_max_str_digits(640)
        for value in (bundle({10**700: {'node': 10**700}}), bundle({'9'*700: {'node': 0}})):
            assert equivalent(candidate, value)[0] == 'error'
        # Integer values are not serialized by normalize and must not be narrowed.
        assert equivalent(candidate, {'n': 10**700})[0] == 'ok'
    finally: sys.set_int_max_str_digits(previous)


def test_custom_status_hook_is_not_called_in_C_then_called_once_in_fallback(candidate):
    calls = []
    class Stop(Exception): pass
    class Status:
        def __eq__(self, other): calls.append(other); raise Stop('status hook')
    value = {'status': Status(), 'contract': {}, 'resources': {}}
    assert candidate.module.try_normalize(value) is NotImplemented and calls == []
    with pytest.raises(Stop, match='status hook'): candidate.normalize(value)
    assert calls == ['conditional_model_input']


def test_custom_metaclass_membership_hooks_only_in_original_fallback(candidate):
    calls = []
    class Meta(type):
        def __eq__(self, other): calls.append(other); return False
    class Value(metaclass=Meta): pass
    value = Value()
    assert candidate.module.try_normalize(value) is NotImplemented and not calls
    expected = outcome(c.original.normalize, value); expected_calls = list(calls); calls.clear()
    assert outcome(candidate.normalize, value) == expected and calls == expected_calls


def test_legacy_metaclass_acceptance_quirk_is_fallback_not_widened_C_domain(candidate):
    calls = []
    class Meta(type):
        def __eq__(self, other): calls.append(other); return other is str
    class Value(metaclass=Meta): pass
    value = Value()
    assert candidate.module.try_normalize(value) is NotImplemented and calls == []
    assert c.original.normalize(value) is value
    expected_calls = list(calls); calls.clear()
    assert candidate.normalize(value) is value and calls == expected_calls
    # This is an original unsupported-domain quirk, not a fresh builtin C tree
    # or permission to bypass the later unchanged strict codec.


def test_mixed_resource_scan_does_not_suppress_later_metaclass_hash_hook(candidate):
    calls = []
    class Stop(Exception): pass
    class Meta(type):
        def __hash__(self): calls.append('type hash'); raise Stop('type set hook')
    class Key(metaclass=Meta): pass
    value = bundle({0: {'node': 0}, '1': {'node': 1}, Key(): {}})
    assert candidate.module.try_normalize(value) is NotImplemented and calls == []
    with pytest.raises(Stop, match='type set hook'): candidate.normalize(value)
    assert calls == ['type hash']


def test_custom_key_lookup_hook_only_once_in_fallback(candidate):
    calls = []
    class Stop(Exception): pass
    class Key:
        def __hash__(self): return hash('status')
        def __eq__(self, other): calls.append(other); raise Stop('key hook')
    value = {Key(): 1}
    assert candidate.module.try_normalize(value) is NotImplemented and calls == []
    with pytest.raises(Stop, match='key hook'): candidate.normalize(value)
    assert calls == ['status']


@pytest.mark.parametrize('factory', [lambda: object(), lambda: set(), lambda: b'bytes'])
def test_unsupported_type_full_original_fallback(candidate, factory):
    value = factory()
    assert candidate.module.try_normalize(value) is NotImplemented
    assert equivalent(candidate, value)[0] == 'error'


def test_gc_state_and_input_unchanged_no_request_cache(candidate):
    enabled = gc.isenabled(); value = {'a': list(range(32)), 'b': (None, -0.)}; before = deepcopy(value)
    outputs = [candidate.normalize(value) for _ in range(8)]
    assert gc.isenabled() is enabled and value == before
    all_ids = [mutable_ids(v) for v in outputs]
    assert all(not (a & b) for i, a in enumerate(all_ids) for b in all_ids[i+1:])


def test_binding_rejects_source_change_and_forged_engine():
    from types import ModuleType
    with pytest.raises((ValueError, AttributeError)):
        c.Candidate(ModuleType('fake'), {})


@pytest.mark.saved18
def test_fixed18_full_saved_root_values_and_codec(candidate):
    """Separate authorized gate only:18 fixed roots, no outcome/model/native input."""
    root = Path(__file__).resolve().parents[1]
    directory = root/'outputs/experiments/g31_ics_lt2_sustained_20261014/initial_owner_route_entry_codec_campaign_prepare_001'
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha(directory/'campaign.json') == '8884b22d2de102693a8ca3855b0d22ffda10312b2e7806908edd26caaa2dd61a'
    assert sha(directory/'receipt.json') == '49b0d7e2f4d019c1546fb34f941813198d21189d39735eb6e0ac3101f8c184bf'
    assert sha(directory/'branch_ledger.json') == '661896d2848c1bcffcf9e7e405222b7955bd9ab1bf03956381ec10e4538b052a'
    ledger = json.loads((directory/'branch_ledger.json').read_text())
    assert len(ledger) == 18
    counts = {'roots': 0, 'closed': 0, 'unknown': 0}
    for row in ledger.values():
        assert row['status'] == 'raw_saved'
        path = Path(row['raw']['path']); assert sha(path) == row['raw']['sha256']
        with gzip.open(path, 'rt', encoding='utf8') as stream: raw = json.load(stream)
        assert len(raw['root_records']) == 1
        value = raw['root_records'][0]  # full evidence AND ledger/outer fields, never physical outcome
        expected = c.original.normalize(value); actual = candidate.normalize(value)
        assert exact(actual, expected) and not (mutable_ids(value) & mutable_ids(actual))
        encoded = c.original.wire.artifact_encode(actual)
        assert encoded == c.original.wire.artifact_encode(expected)
        assert exact(c.original.wire.artifact_decode(encoded), expected)
        counts['roots'] += 1
        counts['closed' if value['closed'] else 'unknown'] += 1
    assert counts == {'roots': 18, 'closed': 16, 'unknown': 2}
