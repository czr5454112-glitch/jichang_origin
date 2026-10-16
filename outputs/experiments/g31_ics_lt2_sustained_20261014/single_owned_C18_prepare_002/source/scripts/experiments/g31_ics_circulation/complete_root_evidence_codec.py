"""Owned complete-evidence codec candidate, not a general unchecked JSON API.

The original normalizer is still the first operation. Its fresh, exact-builtin
tree has already passed the same depth/node/key/scalar domain as artifact_encode.
Only that encoder's redundant _tree call is removed, with an inverse AST proof.
The original artifact_decode (duplicate keys, limits, finite/builtin validation)
remains. Re-encoding its result with exactly the original settings replaces the
Python exact_tree comparison. No normalized reference escapes before this check.

This argument is restricted to internally generated, ensure_ascii=False, strict
UTF-8 JSON of a fresh normalized tree. Surrogates fail at the original UTF-8 step;
the ensure_ascii=True surrogate-pair collision is NOT in the supported domain.
No custom object, external byte string, mutable caller tree, or cached authority
is accepted as proof. All validation/encoding/decoding costs remain chargeable.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import textwrap
from . import initial_owner_route_image as wire
from . import initial_owner_route_json_v3 as normalization

SCHEMA = 'g31.complete_root_evidence_codec.v1'


def _dump(tree):
    return ast.dump(tree, include_attributes=False)


def _encoder():
    syntax = ast.parse(textwrap.dedent(inspect.getsource(wire.artifact_encode)))
    original = copy.deepcopy(syntax)
    dumps = [node for node in ast.walk(syntax) if isinstance(node, ast.Call)
             and ast.unparse(node.func) == 'json.dumps']
    expected_dump = ast.parse("json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)",
                              mode='eval').body
    if len(dumps) != 1 or _dump(dumps[0]) != _dump(expected_dump):
        raise ValueError('complete_codec:encoder_canonical_domain_changed')
    body = syntax.body[0].body
    positions = [i for i, node in enumerate(body) if isinstance(node, ast.Expr)
                 and isinstance(node.value, ast.Call)
                 and ast.unparse(node.value.func) == '_tree']
    if len(positions) != 1:
        raise ValueError('complete_codec:encoder_tree_inventory')
    position = positions[0]
    removed = body.pop(position)
    expected = ast.parse('_tree(value, node_limit=MAX_ARTIFACT_NODES)').body[0]
    if _dump(removed) != _dump(expected):
        raise ValueError('complete_codec:encoder_tree_domain_changed')
    restored = copy.deepcopy(syntax)
    restored.body[0].body.insert(position, removed)
    if _dump(restored) != _dump(original):
        raise ValueError('complete_codec:encoder_AST_changed')
    namespace = dict(wire.artifact_encode.__globals__)
    exec(compile(ast.fix_missing_locations(syntax), '<owned-evidence-encoder>', 'exec'), namespace)
    return namespace['artifact_encode'], {
        'original_encoder_source_sha256': hashlib.sha256(inspect.getsource(wire.artifact_encode).encode()).hexdigest(),
        'encoder_inverse_AST_exact': True,
        'removed_expression': ast.unparse(removed),
        'original_encode_parameters_and_byte_limit': True,
    }


# Private prevalidated encoder: only normalize/strict-decode outputs reach it.
_encode_normalized, _ENCODER_PROOF = _encoder()


def _check_owned_encoding(encoded):
    decoded = wire.artifact_decode(encoded)
    if _encode_normalized(decoded) != encoded:
        # Same failure label as the original complete-evidence finisher.
        raise ValueError('initial_campaign:root_codec_roundtrip_order_or_type')


def normalize_roundtrip(value):
    """Fresh full output plus identical bytes, returned only after full check.

    No fallback widens the original input domain. Unsupported values and limits
    go through the original normalize/codec errors. This is a data-only helper;
    it neither claims native authority nor changes any request boundary.
    """
    result = normalization.normalize(value)
    encoded = _encode_normalized(result)
    _check_owned_encoding(encoded)
    return result, encoded


def source_proof():
    return {
        'schema': SCHEMA,
        **_ENCODER_PROOF,
        'normalizer_source_sha256': hashlib.sha256(inspect.getsource(normalization.normalize).encode()).hexdigest(),
        'strict_decoder_source_sha256': hashlib.sha256(inspect.getsource(wire.artifact_decode).encode()).hexdigest(),
        'normalization_unchanged': True,
        'strict_decode_and_tree_validation_unchanged': True,
        'comparison': 'same original compact JSON encoding, ordered keys, strict UTF-8, finite builtins',
        'ensure_ascii_true_not_supported': True,
        'owned_tree_returned_only_after_roundtrip': True,
        'external_encoded_input_authority': False,
        'native_or_performance_run': False,
    }
