"""Synthetic source/ownership gate only: no saved18 scan, model or native run."""
import ast
import builtins
import copy
import inspect
import json
from types import FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import complete_root_evidence_owned_decode_v2 as c
from scripts.experiments.g31_ics_circulation import root_evidence_mock as mock


def clone(function, **changes):
    result = FunctionType(function.__code__, {**function.__globals__, **changes},
                          function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def shape(state='closed_native_default_first_hop', payload=None):
    return {'root_id': 'synthetic:owned:1', 'state': state,
        'root_started_ns': 100, 'root_deadline_ns': 100000100, 'decision_cutoff_ns': 60000100,
        'choice': 'native_default', 'command_id': None, 'hop': {'prefix': [0, 1], 'at': -0.0},
        'events': [{'stage': 'synthetic', 'wall_ns': 120, 'value': payload}],
        'initial_endpoint_records': {'A': [{'view': {'rows': [(1, -0.0)]}}],
                                     'B': [{'view': {'rows': [(2, 1.0)]}}]}}


def proof():
    return {'schema': 'synthetic_runtime_proof', 'reads': [{'at': 1.0}],
            'calls': [{'arguments': ('A', 'x')}], 'outbox': {'x': {'ack': {'at': -0.0}}}}


def bound_publisher(arm, value, *, method_changes=None, finish_changes=None, supplied_proof=None):
    stamps = iter((200, 300, 400))
    clock = SimpleNamespace(perf_counter_ns=lambda: next(stamps))
    runtime = proof() if supplied_proof is None else supplied_proof
    original_method = c.baseline.EVIDENCE if arm == 'A' else c.EVIDENCE
    original_finish = c.baseline.finish_root if arm == 'A' else c.finish_root
    method = clone(original_method, time=clock, root_runtime_proof=lambda root: runtime,
                   **(method_changes or {}))
    finish = clone(original_finish, time=clock, evidence=method, **(finish_changes or {}))
    publisher = clone(c.publish_root, time=clock, finish_root=finish)
    return publisher, mock.root_from_evidence(value, method), []


def publish(arm, value, **kwargs):
    publisher, root, holder = bound_publisher(arm, value, **kwargs)
    output = publisher(root, holder)
    assert holder == [output] and holder[0] is output
    return output


def outcome(function):
    try:
        function()
    except Exception as error:
        return type(error), error.args
    raise AssertionError('Expected rejection')


GOOD = [None, False, True, 0, -3, 2**80, 0.0, -0.0, 1.0,
    float.fromhex('0x0.0000000000001p-1022'), float.fromhex('0x1.fffffffffffffp+1023'),
    '', 'a\n\t\\"', '\U0001f642', {'\U0001f642': '雪'},
    {'b': 1, 'a': 1.0, 'c': -0.0}, [(1, True, -0.0), {'sequence': (1.0, 2)}],
    {'status': 'conditional_model_input', 'contract': {}, 'resources': {2: {'node': 2}, 1: {'node': 1}}}]


@pytest.mark.parametrize('payload', GOOD)
def test_complete_publication_exact_order_type_float_bits_and_all_clocks(payload):
    value = shape(payload=payload)
    old, new = publish('A', value), publish('B', value)
    assert c.previous.single.exact_tree(old, new)
    assert list(old) == list(new) == list(mock.RECORD_KEYS)
    assert list(old['value']) == list(new['value']) == list(mock.VALUE_KEYS)
    assert new['value']['body_finished_ns'] == 300
    assert new['outside_return_ns'] == 400 and new['finalization_started_ns'] == 200
    assert new['warm_caller_elapsed_ns'] == 300
    assert new['complete_100ms_certificate'] is False


@pytest.mark.parametrize('state', ['closed_native_default_first_hop', 'closed_delivered_terminal_failure',
    'closed_updated_and_requested_first_hop', 'closed_updated_but_other_first_hop',
    'unknown_collection', 'open'])
def test_reported_state_not_upgraded_by_codec(state):
    assert c.previous.single.exact_tree(publish('A', shape(state)), publish('B', shape(state)))


def test_original_public_functions_and_complete_entry_binding():
    result = c.source_proof()
    for flag in ('decoder_inverse_AST_exact', 'evidence_inverse_AST_exact', 'complete_owned_entry',
                 'normalization_first_and_no_escape_before_check', 'public_artifact_decoder_unchanged',
                 'ledger_tree_validation_unchanged', 'original_body_timestamp_position'):
        assert result[flag] is True
    assert result['general_decoder_created'] is False and result['external_bytes_authorized'] is False
    assert result['all_resource_failures_equivalent'] is False
    assert c.EVIDENCE.__globals__['normalization'].normalize is c.normalization.normalize
    assert c.EVIDENCE.__globals__['root_runtime_proof'] is c.baseline.entry.root_runtime_proof
    assert c.finish_root.__code__ is c.baseline.finish_root.__code__
    assert c.publish_root.__code__ is c.baseline.publish_root.__code__
    assert c.finish_root.__globals__['image'].artifact_decode is c.wire.artifact_decode
    assert c.finish_root.__globals__['image'].artifact_encode is c.wire.artifact_encode
    # Functions defined by this module do not expose a bytes/raw decoder call.
    assert not any('raw' in inspect.signature(fn).parameters or 'encoded' in inspect.signature(fn).parameters
                   for fn in vars(c).values() if inspect.isfunction(fn) and fn.__module__ == c.__name__)


def complete_syntax():
    captured = []
    def compile_capture(syntax, filename, mode):
        assert filename == '<complete-owned-evidence>'
        captured.append(copy.deepcopy(syntax))
        return builtins.compile(ast.fix_missing_locations(syntax), filename, mode)
    compiler = c.private(c.previous._compiler, {'builtins': SimpleNamespace(compile=compile_capture),
                                               '_INTEGRATION_PROOF': {}})
    c.private(c.previous.frozen._evidence_function, {'compile': compiler})()
    assert len(captured) == 1
    return captured[0]


@pytest.mark.parametrize('mutation', ['escape', 'encode_before_normalize', 'clock_before_encode',
                                    'extra_after_check', 'prior_local'])
def test_owned_entry_AST_rejects_escape_or_order_changes(mutation):
    syntax = complete_syntax()
    body = syntax.body[0].body
    n = next(i for i, node in enumerate(body)
             if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == 'result')
    if mutation == 'escape': body.insert(n+1, ast.parse('leak(result)').body[0])
    elif mutation == 'encode_before_normalize': body[n], body[n+1] = body[n+1], body[n]
    elif mutation == 'clock_before_encode': body[n+1], body[n+2] = body[n+2], body[n+1]
    elif mutation == 'extra_after_check': body.insert(n+4, ast.parse('leak(encoded)').body[0])
    else: body.insert(n, ast.parse('result = escaped').body[0])
    with pytest.raises(ValueError, match='owned_decoder_'):
        c._compile_complete(syntax, '<complete-owned-evidence>', 'exec')


def test_rebuilding_factory_does_not_mutate_frozen_proof_or_globals():
    before = copy.deepcopy(c.previous._INTEGRATION_PROOF)
    names = dict(c.previous._compiler.__globals__)
    complete_syntax()
    assert c.previous._INTEGRATION_PROOF == before
    assert all(c.previous._compiler.__globals__[key] is value for key, value in names.items())


def test_source_proof_rejects_substituted_internal_encoder():
    altered = clone(c.EVIDENCE, _codec_encode=lambda value: b'{}\n')
    check = clone(c.source_proof, EVIDENCE=altered)
    with pytest.raises(ValueError, match='owned_decoder_private_globals_changed'):
        check()


class CustomDict(dict):
    pass


BAD = [float('nan'), float('inf'), -float('inf'), object(), CustomDict(a=1), {1: 'wrong'},
       '\ud800', '\udfff', '\ud83d\ude42', {'\ud800': 'x'}, {'x': '\ud83d\ude42'},
       {'\ud83d\ude42': 'x'},
       {'status': 'conditional_model_input', 'contract': {}, 'resources': {1: {'node': 1}, '2': {'node': 2}}}]


@pytest.mark.parametrize('payload', BAD)
def test_original_normalization_unicode_and_type_errors_retained(payload):
    assert outcome(lambda: publish('A', shape(payload=payload))) == outcome(lambda: publish('B', shape(payload=payload)))


def test_cycle_and_deep_input_rejected_by_original_normalizer():
    cyc = []; cyc.append(cyc)
    deep = 0
    for _ in range(66): deep = [deep]
    for item in (cyc, deep, 10**5000):
        assert outcome(lambda: publish('A', shape(payload=item))) == outcome(lambda: publish('B', shape(payload=item)))


def test_node_limit_rejects_before_encoding_and_no_return_escapes():
    facade = SimpleNamespace(**vars(c.wire)); facade.MAX_ARTIFACT_NODES = 4
    normalize = clone(c.normalization.normalize, wire=facade)
    calls = []
    publisher, root, holder = bound_publisher('B', shape(), method_changes={
        'normalization': SimpleNamespace(normalize=normalize),
        '_codec_encode': lambda v: calls.append(v)})
    with pytest.raises(ValueError, match='initial_json_v3:tree_limit'): publisher(root, holder)
    assert calls == [] and holder == []


def test_external_public_decoder_still_rejects_overdepth():
    raw = b'[' * 65 + b'0' + b']' * 65
    with pytest.raises(ValueError, match='json_limit'): c.wire.artifact_decode(raw)


def test_external_public_decoder_node_walk_is_still_executed(monkeypatch):
    # A small bound exercises the exact original public function, avoiding a
    # two-million-node fixture. The public function/code is never replaced.
    original = c.wire.artifact_decode
    monkeypatch.setattr(c.wire, 'MAX_ARTIFACT_NODES', 4)
    with pytest.raises(ValueError, match='json_limit'): original(b'{"a":[1,2,3]}')
    assert original is c.wire.artifact_decode


def test_owned_and_public_limit_counting_agree_on_normalized_tree():
    for value in GOOD:
        normalized = c.normalization.normalize(value)
        c.wire._tree(normalized, node_limit=c.wire.MAX_ARTIFACT_NODES)
        assert c.previous.single.exact_tree(c.wire.artifact_decode(c.wire.artifact_encode(normalized)), normalized)


@pytest.mark.parametrize('raw', [bytearray(b'{}'), '{}', b'\xff', b'{"a":1,"a":2}',
    b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}', b'{"a":1e400}',
    b'{"a":"\\ud83d\\ude42"}\n', b'{"a":"\\ud800"}\n', b'{"\\ud800":1}\n',
    b'{"a":1} garbage', b'{', b'{}', b'{ }\n'])
def test_fault_injected_first_encoder_cannot_create_false_success(raw):
    # Fault injection is NOT an external bytes API. The production source proof
    # rejects this replacement; the original first encoder never emits these.
    count = [0]
    def faulty(value):
        count[0] += 1
        return raw if count[0] == 1 else c.codec._encode_normalized(value)
    publisher, root, holder = bound_publisher('B', shape(), method_changes={'_codec_encode': faulty})
    with pytest.raises((ValueError, TypeError, UnicodeError)): publisher(root, holder)
    assert holder == []


def test_canonical_bytes_are_not_an_independent_origin_certificate():
    # The roundtrip alone cannot detect a substituted first encoder that emits
    # a different *canonical* tree. Hence its immutable source identity, fresh
    # normalizer and no-escape callsite are required, not merely byte equality.
    def alien_encoder(value):
        return b'null\n'
    altered = clone(c.EVIDENCE, _codec_encode=alien_encoder)
    with pytest.raises(ValueError, match='owned_decoder_private_globals_changed'):
        clone(c.source_proof, EVIDENCE=altered)()


def test_inline_byte_limit_retained():
    publisher, root, holder = bound_publisher('B', shape(), method_changes={'_owned_byte_limit': 1})
    with pytest.raises(ValueError, match='artifact_limit'): publisher(root, holder)
    assert not holder


@pytest.mark.parametrize('mutation', ['order', 'float_type', 'negative_zero', 'missing', 'extra'])
def test_decoded_change_fails_canonical_reencoding(mutation):
    def altered(*args, **kwargs):
        value = json.loads(*args, **kwargs)
        if mutation == 'order': value = dict(reversed(list(value.items())))
        elif mutation == 'float_type': value['root_started_ns'] = 100.0
        elif mutation == 'negative_zero': value['hop']['at'] = 0.0
        elif mutation == 'missing': value.pop('owner')
        else: value['unexpected'] = 0
        return value
    publisher, root, holder = bound_publisher('B', shape(), method_changes={'_owned_json_loads': altered})
    with pytest.raises(ValueError, match='root_codec_roundtrip_order_or_type'): publisher(root, holder)
    assert holder == []


def test_fresh_return_isolated_from_root_records_runtime_proof_and_another_call():
    shared = {'members': [1, -0.0]}
    value = shape(payload=[shared, shared]); runtime = proof()
    first = publish('B', value, supplied_proof=runtime)
    second = publish('B', value, supplied_proof=runtime)
    evidence = first['value']['evidence']
    payload = evidence['events'][0]['value']
    assert payload[0] is not payload[1] and payload[0] is not shared
    payload[0]['members'].append(9)
    evidence['initial_endpoint_records']['B'][0]['view'].clear()
    evidence['runtime_query_proof']['outbox'].clear()
    assert shared['members'] == [1, -0.0] and runtime['outbox']
    assert value['initial_endpoint_records']['B'][0]['view']
    assert second['value']['evidence']['events'][0]['value'][0]['members'] == [1, -0.0]
    assert first['ledger'] is not second['ledger']
    assert first['ledger']['root_id'] == value['root_id']


@pytest.mark.parametrize('stage', ['encode', 'parse', 'reencode', 'ledger'])
@pytest.mark.parametrize('error_type', [ValueError, MemoryError, RecursionError])
def test_failure_not_retried_or_appended_and_next_request_independent(stage, error_type):
    count = [0]
    def fail(*args, **kwargs):
        count[0] += 1
        raise error_type('injected_' + stage)
    method_changes, finish_changes = {}, {}
    if stage == 'encode': method_changes['_codec_encode'] = fail
    elif stage == 'parse': method_changes['_owned_json_loads'] = fail
    elif stage == 'reencode':
        first = [True]
        def encode(value):
            if first[0]:
                first[0] = False
                return c.codec._encode_normalized(value)
            return fail()
        method_changes['_codec_encode'] = encode
    else: finish_changes['image'] = SimpleNamespace(artifact_encode=fail)
    publisher, root, holder = bound_publisher('B', shape(), method_changes=method_changes,
                                             finish_changes=finish_changes)
    with pytest.raises(error_type, match='injected_'): publisher(root, holder)
    assert count == [1] and holder == []
    assert publish('B', shape())['closed'] is True


def test_one_original_public_tree_walk_remains_for_ledger(monkeypatch):
    source = c.wire._tree
    primitive = []
    def observed(value, depth=0, count=None, node_limit=None):
        if count is None: primitive.append(value)
        return source(value, depth, count, node_limit)
    monkeypatch.setattr(c.wire, '_tree', observed)
    result = publish('B', shape(payload={'large': [1, 2, 3]}))
    assert len(primitive) == 1 and primitive[0] is result['ledger']


def test_reject_old_evidence_method_without_owned_function_code():
    root = mock.root_from_evidence(shape(), c.baseline.EVIDENCE)
    with pytest.raises(ValueError, match='single_evidence_method_not_owned'): c.finish_root(root)
