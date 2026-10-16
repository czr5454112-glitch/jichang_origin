"""Internal complete-evidence decoder experiment; no public bytes entry point.

The original normalizer owns a fresh exact-builtin tree. Before its first escape,
the original canonical encoder produces bytes, the original strict JSON parser
decodes them, and canonical re-encoding must reproduce those exact bytes. Only
the decoded tree's second depth/node/type walk is omitted. The source AST below
proves this order inside the COMPLETE evidence function, rather than accepting a
caller's claim that arbitrary bytes are owned. Public artifact_decode, the
normalizer, ledger artifact_encode, root clocks and publication code stay intact.

This is a version-closed, single-threaded source contract, not a security sandbox
against code/globals mutation. There is no native installation or C loading here.
Codec errors propagate; there is no success fallback. Resource-failure points
(allocation, recursion and interpreter limits) need not be identical and remain
unknown failures. Removing one Python walk does not certify a latency benefit.
"""
from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import inspect
import textwrap
from types import SimpleNamespace

from . import complete_root_evidence_codec as codec
from . import complete_root_evidence_candidate as previous
from . import initial_owner_route_entry_codec_integration as baseline

SCHEMA = 'g31.complete_root_evidence_owned_decode.v2'
wire, normalization = codec.wire, codec.normalization
private, require = previous.frozen.private, previous.frozen.require
_PROOF = {}
_UPSTREAM_COMPILER_PROOF = {}


def _dump(node):
    return ast.dump(node, include_attributes=False)


def _syntax(function):
    return ast.parse(textwrap.dedent(inspect.getsource(function)))


class _DecoderNames(ast.NodeTransformer):
    """Mechanical private-name substitution, with a checked inverse."""
    names = {'raw': 'encoded', 'value': '_owned_decoded',
             'MAX_ARTIFACT_BYTES': '_owned_byte_limit', '_pairs': '_owned_pairs',
             '_constant': '_owned_constant'}

    def __init__(self, inverse=False):
        self.inverse = inverse
        self.mapping = ({v: k for k, v in self.names.items()} if inverse else self.names)

    def visit_Call(self, node):
        node = self.generic_visit(node)
        if not self.inverse and _dump(node.func) == _dump(ast.parse('json.loads', mode='eval').body):
            node.func = ast.copy_location(ast.Name('_owned_json_loads', ast.Load()), node.func)
        elif self.inverse and isinstance(node.func, ast.Name) and node.func.id == '_owned_json_loads':
            node.func = ast.copy_location(ast.parse('json.loads', mode='eval').body, node.func)
        return node

    def visit_Name(self, node):
        return ast.copy_location(ast.Name(self.mapping.get(node.id, node.id), node.ctx), node)


def _decoder_statements():
    """Return AST only. No function accepting encoded bytes is constructed."""
    original = _syntax(wire.artifact_decode)
    expected = ast.parse("""def artifact_decode(raw):
    if type(raw) is not bytes or len(raw)>MAX_ARTIFACT_BYTES: raise ValueError('artifact_limit')
    value=json.loads(raw.decode('utf8'),object_pairs_hook=_pairs,parse_constant=_constant)
    _tree(value,node_limit=MAX_ARTIFACT_NODES)
    return value
""")
    require(_dump(original) == _dump(expected), 'owned_decoder_original_AST_changed')
    prefix = copy.deepcopy(original.body[0].body[:2])
    changed = [_DecoderNames().visit(node) for node in prefix]
    restored = copy.deepcopy(original)
    restored.body[0].body[:2] = [_DecoderNames(inverse=True).visit(copy.deepcopy(node))
                               for node in changed]
    require(_dump(restored) == _dump(original), 'owned_decoder_inverse_AST_changed')
    _PROOF.update(decoder_inverse_AST_exact=True,
                  removed_decoder_expression=ast.unparse(original.body[0].body[2]),
                  original_strict_parser_and_byte_bound=True)
    return changed


def _compile_complete(syntax, filename, mode):
    require(filename == '<complete-owned-evidence>' and mode == 'exec',
            'owned_decoder_compile_site')
    original = copy.deepcopy(syntax)
    function = syntax.body[0]
    body = function.body
    markers = [i for i, node in enumerate(body)
               if _dump(node) == _dump(ast.parse('result = normalization.normalize(raw)').body[0])]
    require(len(markers) == 1, 'owned_decoder_normalization_inventory')
    position = markers[0]
    expected = ast.parse("""result = normalization.normalize(raw)
encoded = _codec_encode(result)
finished = time.perf_counter_ns()
_codec_check(encoded)
return {'evidence':result,'encoded':encoded,'body_finished_ns':finished,
        'body_elapsed_ns':finished-self.started_ns,'outside_return_tail_required':True}
""").body
    require([_dump(node) for node in body[position:]] == [_dump(node) for node in expected],
            'owned_decoder_ownership_or_clock_topology_changed')
    # No prior use or binding of these locals can lend out the fresh result.
    # In the verified suffix, result is only given to the fixed encoder and the
    # final return; encoded is only used by the check and the final return.
    reserved = {'result', 'encoded', '_owned_decoded'}
    require(not any(isinstance(node, ast.Name) and node.id in reserved
                    for statement in body[:position] for node in ast.walk(statement)),
            'owned_decoder_prior_alias_or_binding')
    require(not any(isinstance(node, ast.Name) and node.id.startswith('_owned_')
                    for node in ast.walk(original)), 'owned_decoder_private_name_collision')
    inline = _decoder_statements()
    inline.extend(ast.parse("""if _codec_encode(_owned_decoded) != encoded:
    raise ValueError('initial_campaign:root_codec_roundtrip_order_or_type')
""").body)
    index = position + 3
    body[index:index+1] = inline
    restored = copy.deepcopy(syntax)
    restored.body[0].body[index:index+len(inline)] = [copy.deepcopy(expected[3])]
    require(_dump(restored) == _dump(original), 'owned_decoder_evidence_inverse_AST_changed')
    _PROOF.update(evidence_inverse_AST_exact=True, complete_owned_entry=True,
                  normalization_first_and_no_escape_before_check=True,
                  original_body_timestamp_position=True,
                  encoded_bytes_decoder_API_created=False,
                  original_evidence_AST_sha256=hashlib.sha256(_dump(original).encode()).hexdigest(),
                  candidate_evidence_AST_sha256=hashlib.sha256(_dump(syntax).encode()).hexdigest())
    return builtins.compile(ast.fix_missing_locations(syntax), '<complete-owned-decode-v2>', mode)


# The frozen factory inserts the complete runtime proof; its frozen compiler
# first proves the original encoder/check substitution. This final private
# compiler sees that exact resulting AST. No imported dict/class is patched.
_compiler = private(previous._compiler, {
    'builtins': SimpleNamespace(compile=_compile_complete),
    '_INTEGRATION_PROOF': _UPSTREAM_COMPILER_PROOF})
_factory = private(previous.frozen._evidence_function, {'compile': _compiler})
EVIDENCE = private(_factory(), {
    '_codec_encode': codec._encode_normalized,
    'root_runtime_proof': baseline.entry.root_runtime_proof,
    '_owned_json_loads': wire.artifact_decode.__globals__['json'].loads,
    '_owned_pairs': wire._pairs, '_owned_constant': wire._constant,
    '_owned_byte_limit': wire.MAX_ARTIFACT_BYTES})
finish_root = private(baseline.finish_root, {'evidence': EVIDENCE})
publish_root = private(baseline.publish_root, {'finish_root': finish_root})

# Preparation-time identities, not per-request validation or mutable input caches.
_EVIDENCE_CODE = EVIDENCE.__code__
_EVIDENCE_GLOBALS = dict(EVIDENCE.__globals__)
_FINISH_GLOBALS = dict(finish_root.__globals__)
_PUBLISH_GLOBALS = dict(publish_root.__globals__)
_IDENTITIES = (wire.artifact_decode, wire.artifact_decode.__code__,
               wire.artifact_encode, wire.artifact_encode.__code__,
               normalization.normalize, normalization.normalize.__code__,
               wire._pairs, wire._constant, wire.json.loads, wire.json.dumps,
               wire.MAX_DEPTH, wire.MAX_ARTIFACT_NODES, wire.MAX_ARTIFACT_BYTES)


def source_proof():
    """Closed-source preparation proof; no input or byte authority parameter."""
    current = (wire.artifact_decode, wire.artifact_decode.__code__,
               wire.artifact_encode, wire.artifact_encode.__code__,
               normalization.normalize, normalization.normalize.__code__,
               wire._pairs, wire._constant, wire.json.loads, wire.json.dumps,
               wire.MAX_DEPTH, wire.MAX_ARTIFACT_NODES, wire.MAX_ARTIFACT_BYTES)
    require(all(a is b for a, b in zip(current, _IDENTITIES)), 'owned_decoder_source_identity_changed')
    for function, expected in ((EVIDENCE, _EVIDENCE_GLOBALS), (finish_root, _FINISH_GLOBALS),
                               (publish_root, _PUBLISH_GLOBALS)):
        require(set(function.__globals__) == set(expected) and
                all(function.__globals__[key] is value for key, value in expected.items()),
                'owned_decoder_private_globals_changed')
    require(EVIDENCE.__code__ is _EVIDENCE_CODE and
            EVIDENCE.__globals__['normalization'] is normalization and
            EVIDENCE.__globals__['root_runtime_proof'] is baseline.entry.root_runtime_proof and
            finish_root.__code__ is baseline.finish_root.__code__ and
            finish_root.__globals__['image'].artifact_encode is wire.artifact_encode and
            finish_root.__globals__['evidence'] is EVIDENCE and
            publish_root.__code__ is baseline.publish_root.__code__ and
            publish_root.__globals__['finish_root'] is finish_root,
            'owned_decoder_complete_binding_changed')
    return {'schema': SCHEMA, **copy.deepcopy(_PROOF),
        'upstream_compiler': copy.deepcopy(_UPSTREAM_COMPILER_PROOF),
        'original_normalizer_source_sha256': hashlib.sha256(inspect.getsource(normalization.normalize).encode()).hexdigest(),
        'original_decoder_source_sha256': hashlib.sha256(inspect.getsource(wire.artifact_decode).encode()).hexdigest(),
        'public_artifact_decoder_unchanged': True, 'ledger_tree_validation_unchanged': True,
        'original_complete_runtime_query_and_entry_marker': True,
        'original_finisher_publisher_code_and_cost_boundary': True,
        'external_bytes_authorized': False, 'general_decoder_created': False,
        'C_normalizer_bound_or_loaded': False, 'native_or_performance_dispatched': False,
        'all_resource_failures_equivalent': False,
        'scope': 'Only internally normalized, canonically encoded complete evidence before first escape; immutable source image, no adversarial monkeypatch.',
        'cost': 'Normalization, first encode, strict parse, canonical reencode, hash, ledger encode, append and outside-return all remain charged.'}
