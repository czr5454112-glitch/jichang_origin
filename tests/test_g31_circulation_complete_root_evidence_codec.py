"""Closed codec/source gate. Synthetic complete shapes; no saved raw scan/native."""
import copy
import json
import math
from types import FunctionType, MethodType, SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import complete_root_evidence_codec as c
from scripts.experiments.g31_ics_circulation import complete_root_evidence_candidate as e
from scripts.experiments.g31_ics_circulation import root_evidence_mock as mock


def clone(fn, **changes):
    return FunctionType(fn.__code__, {**fn.__globals__, **changes}, fn.__name__, fn.__defaults__, fn.__closure__)


def legacy(value):
    normalized = c.normalization.normalize(value)
    encoded = c.wire.artifact_encode(normalized)
    decoded = c.wire.artifact_decode(encoded)
    assert e.single.exact_tree(decoded, normalized)
    return normalized, encoded


VALUES = [None, True, False, 0, -1, 2**80, 1.0, -0.0, 0.0,
    float.fromhex('0x0.0000000000001p-1022'), float.fromhex('0x1.fffffffffffffp+1023'),
    '', 'a\n\t\\"', '\U0001f642', {'\U0001f642': '雪'},
    {'b': 1, 'a': 1.0, 'c': -0.0}, [('x', 1.0), {'rows': (1, 2, -0.0)}],
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {2: {'node': 2}, 1: {'node': 1}}},
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {'2': {'node': 2}, '1': {'node': 1}}}]


@pytest.mark.parametrize('value', VALUES)
def test_exact_old_normalized_fields_bytes_order_and_scalars(value):
    a, ar = legacy(value)
    b, br = c.normalize_roundtrip(value)
    assert ar == br and e.single.exact_tree(a, b)


@pytest.mark.parametrize('a,b', [(1, 1.0), (True, 1), (-0.0, 0.0),
    ({'a': 1, 'b': 2}, {'b': 2, 'a': 1}), ('\U0001f642', '\U0001f643'),
    (float.fromhex('0x1.0000000000001p+0'), 1.0)])
def test_representation_differences_are_not_equal_bytes(a, b):
    assert c.normalize_roundtrip(a)[1] != c.normalize_roundtrip(b)[1]


def outcome(fn, value):
    try:
        fn(value)
    except Exception as error:
        return type(error), error.args
    raise AssertionError('bad value was accepted')


class CustomDict(dict):
    pass


BAD = [float('nan'), float('inf'), -float('inf'), object(), CustomDict(a=1), {1: 'not resource'},
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {1: {'node': 2}}},
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {1: {'node': 1}, '2': {'node': 2}}},
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {'01': {'node': 1}}},
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {True: {'node': 1}}},
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {'-1': {'node': -1}}},
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {'1': {'node': True}}},
    '\ud800', '\udfff', '\ud83d\ude42', {'\ud800': 'x'}, {'x': '\ud83d\ude42'},
    {'\ud83d\ude42': 'x'}]


@pytest.mark.parametrize('value', BAD)
def test_original_unsupported_or_unicode_error_exactly_retained(value):
    assert outcome(c.normalize_roundtrip, value) == outcome(legacy, value)


def test_ascii_true_collision_is_a_rejected_counterexample():
    astral, explicit_pair = '\U0001f642', '\ud83d\ude42'
    assert astral != explicit_pair
    assert json.dumps(astral, ensure_ascii=True) == json.dumps(explicit_pair, ensure_ascii=True)
    assert c.normalize_roundtrip(astral)[0] == astral
    assert outcome(c.normalize_roundtrip, explicit_pair)[0] is UnicodeEncodeError


def test_cycles_depth_and_huge_integer_preserve_original_errors():
    cyc = []; cyc.append(cyc)
    deep = 0
    for _ in range(66): deep = [deep]
    for value in (cyc, deep, 10**5000):
        assert outcome(c.normalize_roundtrip, value) == outcome(legacy, value)


def test_node_limit_runs_original_normalizer_first_without_partial_acceptance():
    facade = SimpleNamespace(**vars(c.wire)); facade.MAX_ARTIFACT_NODES = 4
    normalizer = clone(c.normalization.normalize, wire=facade)
    function = clone(c.normalize_roundtrip, normalization=SimpleNamespace(normalize=normalizer))
    with pytest.raises(ValueError, match='initial_json_v3:tree_limit'):
        function({'a': [1, 2, 3]})


def test_byte_limit_is_identical_and_includes_newline():
    first = clone(c._encode_normalized, MAX_ARTIFACT_BYTES=3)
    old = clone(c.wire.artifact_encode, MAX_ARTIFACT_BYTES=3)
    assert first(0) == old(0) == b'0\n'
    for value in ('x', 100):
        assert outcome(first, value) == outcome(old, value) == (ValueError, ('artifact_limit',))


def test_shared_aliases_are_copied_and_results_do_not_escape_before_check():
    member = {'x': [1, -0.0]}; raw = [member, member]
    normalized, encoded = c.normalize_roundtrip(raw)
    assert normalized[0] is not normalized[1] and normalized[0] is not member
    member['x'].append(8)
    assert normalized == [{'x': [1, -0.0]}, {'x': [1, -0.0]}]
    normalized[0]['x'].append(9)
    assert c.wire.artifact_decode(encoded)[0]['x'] == [1, -0.0]
    def fail(encoded):
        assert type(encoded) is bytes  # No fresh mutable result is given out.
        raise ValueError('injected_roundtrip')
    failed = clone(c.normalize_roundtrip, _check_owned_encoding=fail)
    with pytest.raises(ValueError, match='injected_roundtrip'): failed(raw)
    assert c.normalize_roundtrip({'ok': 1})[0] == {'ok': 1}


@pytest.mark.parametrize('change', ['order', 'float_type', 'negative_zero', 'missing', 'extra'])
def test_strictly_decoded_representation_change_rejected(change):
    value = {'a': 1, 'b': -0.0}
    def decode(raw):
        decoded = c.wire.artifact_decode(raw)
        if change == 'order': decoded = dict(reversed(list(decoded.items())))
        elif change == 'float_type': decoded['a'] = 1.0
        elif change == 'negative_zero': decoded['b'] = 0.0
        elif change == 'missing': decoded.pop('a')
        else: decoded['extra'] = 0
        return decoded
    check = clone(c._check_owned_encoding, wire=SimpleNamespace(artifact_decode=decode))
    with pytest.raises(ValueError, match='root_codec_roundtrip_order_or_type'):
        check(c.wire.artifact_encode(value))


@pytest.mark.parametrize('raw', [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'])
def test_original_strict_decoder_not_replaced_with_permissive_loads(raw):
    with pytest.raises(ValueError): c._check_owned_encoding(raw)


def full_shape(state='closed_native_default_first_hop'):
    # Explicit synthetic whole-root shape, not alleged native/accepted evidence.
    return {'schema': e.single.contract.SCHEMA, 'root_id': 'synthetic:1', 'state': state,
        'owner': 'A', 'root_started_ns': 100, 'root_deadline_ns': 100000100,
        'decision_cutoff_ns': 60000100, 'choice': 'native_default', 'command_id': None,
        'hop': {'prefix': [0, 1], 'when': -0.0},
        'events': [{'stage': 'synthetic', 'wall_ns': 120, 'value': {'rows': [(1, 1.0, -0.0)]}}],
        'initial_endpoint_records': {'A': [{'own': {'x': [1]}}], 'B': [{'peer': {'x': [2]}}]}}


def publish_pair(value):
    proof = {'schema': 'synthetic_complete_query_proof', 'reads': [{'id': 'x', 'ack': {'n': 1.0}}],
             'outbox': {'x': {'ack': {'n': -0.0}}}, 'calls': [{'args': ('A', 'x')}]}
    records = []
    for method, finisher in ((e.frozen.EVIDENCE, e.frozen.finish_root), (e.EVIDENCE, e.finish_root)):
        stamps = iter((200, 300, 400))
        clock = SimpleNamespace(perf_counter_ns=lambda: next(stamps))
        method = clone(method, time=clock, root_runtime_proof=lambda root: proof)
        finish = clone(finisher, time=clock, evidence=method)
        publisher = clone(e.single.publish_root, time=clock, finish_root=finish)
        root = mock.root_from_evidence(value, method); holder = []
        result = publisher(root, holder)
        assert holder == [result] and holder[-1] is result
        records.append(result)
    return records, proof


@pytest.mark.parametrize('state', ['closed_native_default_first_hop', 'closed_delivered_terminal_failure',
    'closed_updated_and_requested_first_hop', 'closed_updated_but_other_first_hop', 'unknown_collection', 'open'])
def test_entire_current_root_publication_and_clock_topology_identical(state):
    value = full_shape(state)
    (old, new), proof = publish_pair(value)
    assert e.single.exact_tree(old, new)
    assert new['value']['body_finished_ns'] == 300 and new['outside_return_ns'] == 400
    assert new['finalization_started_ns'] == 200
    assert new['complete_100ms_certificate'] is False
    new['value']['evidence']['runtime_query_proof']['outbox'].clear()
    assert proof['outbox'] and old['value']['evidence']['runtime_query_proof']['outbox']
    assert value['events'][0]['value']['rows'][0] == (1, 1.0, -0.0)


@pytest.mark.parametrize('stage', ['encode', 'strict_decode', 'reencode', 'ledger'])
def test_complete_publication_failure_has_no_success_append(stage):
    value = full_shape()
    def fail(*args): raise ValueError('injected_' + stage)
    method_changes = {'root_runtime_proof': lambda root: {}}
    if stage == 'encode': method_changes['_codec_encode'] = fail
    elif stage in ('strict_decode', 'reencode'):
        check_changes = ({'wire': SimpleNamespace(artifact_decode=fail)} if stage == 'strict_decode'
                         else {'_encode_normalized': fail})
        method_changes['_codec_check'] = clone(c._check_owned_encoding, **check_changes)
    method = clone(e.EVIDENCE, **method_changes)
    finish_changes = {'evidence': method}
    if stage == 'ledger': finish_changes['image'] = SimpleNamespace(artifact_encode=fail)
    finish = clone(e.finish_root, **finish_changes)
    publisher = clone(e.single.publish_root, finish_root=finish)
    root = mock.root_from_evidence(value, method); holder = []
    with pytest.raises(ValueError, match='injected_'): publisher(root, holder)
    assert holder == []


def test_original_functions_identity_and_closed_ast_scope():
    proof = e.source_proof()
    assert all(proof[name] for name in ('evidence_inverse_AST_exact', 'runtime_query_proof_unchanged',
        'original_body_timestamp_position', 'strict_check_before_evidence_return',
        'finisher_inverse_AST_exact', 'ledger_encode_unchanged', 'original_publication_code_identical'))
    assert c.normalization.normalize is e.single.normalization.normalize
    assert c.wire.artifact_decode is e.single.image.artifact_decode
    assert e.EVIDENCE.__globals__['normalization'] is e.single.normalization
    assert e.finish_root.__globals__['evidence'] is e.EVIDENCE
    assert e.frozen.finish_root.__globals__['evidence'] is e.frozen.EVIDENCE
    assert e.publish_root.__code__ is e.frozen.publish_root.__code__
    assert proof['scheduler_installed'] is False and proof['firsthop_changed'] is False


def test_finisher_rejects_unverified_evidence_method():
    root = mock.root_from_evidence(full_shape(), e.frozen.EVIDENCE)
    with pytest.raises(ValueError, match='single_evidence_method_not_owned'): e.finish_root(root)
