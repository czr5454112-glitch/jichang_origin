"""Source-only private complete-evidence integration; old gate002 stays frozen.

The actual runtime-query proof and every evidence field stay in their original
order. The original body clock is still taken after first full encoding. Strict
decode/re-encode remains inside the enclosing complete-root clock, before any
normalized result is returned. No scheduler, first-hop, outbox or native changes.
There is deliberately no campaign/launcher or automatic live installation here.
"""
from __future__ import annotations
import ast
import builtins
import copy
import hashlib
import inspect
from . import complete_root_evidence_codec as codec
from . import initial_owner_route_gated_evidence_v2 as frozen

gate, single = frozen.gate, frozen.single
_INTEGRATION_PROOF = {}


def _compiler(syntax, filename, mode):
    frozen.require(filename == '<gated-single-evidence>' and mode == 'exec', 'complete_codec_compile_site')
    original = copy.deepcopy(syntax)
    body = syntax.body[0].body
    encode_positions = [i for i, n in enumerate(body)
                        if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'encoded']
    finish_positions = [i for i, n in enumerate(body)
                        if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == 'finished']
    frozen.require(len(encode_positions) == len(finish_positions) == 1, 'complete_codec_evidence_inventory')
    e, f = encode_positions[0], finish_positions[0]
    frozen.require(ast.unparse(body[e]) == 'encoded = image.artifact_encode(result)' and
                   ast.unparse(body[f]) == 'finished = time.perf_counter_ns()' and f == e + 1,
                   'complete_codec_original_body_boundary')
    original_encode = copy.deepcopy(body[e])
    body[e] = ast.parse('encoded = _codec_encode(result)').body[0]
    body.insert(f + 1, ast.parse('_codec_check(encoded)').body[0])
    restored = copy.deepcopy(syntax)
    del restored.body[0].body[f + 1]
    restored.body[0].body[e] = original_encode
    frozen.require(gate.dump(restored) == gate.dump(original), 'complete_codec_evidence_AST_changed')
    _INTEGRATION_PROOF.update(evidence_inverse_AST_exact=True,
        runtime_query_proof_unchanged=True, original_body_timestamp_position=True,
        strict_check_before_evidence_return=True)
    return builtins.compile(ast.fix_missing_locations(syntax), '<complete-owned-evidence>', mode)


# Reuse the frozen factory's existing full proof insertion/AST check. Only its
# private compile name is substituted; builtins and imported modules stay intact.
_factory = frozen.private(frozen._evidence_function, {'compile': _compiler})
EVIDENCE = frozen.private(_factory(), {
    '_codec_encode': codec._encode_normalized, '_codec_check': codec._check_owned_encoding})


def _finisher():
    syntax = gate.tree(single.finish_root)
    original = copy.deepcopy(syntax)
    body = syntax.body[0].body
    positions = [i for i, node in enumerate(body) if isinstance(node, ast.Assign)
                 and ast.unparse(node.targets[0]) == 'decoded']
    frozen.require(len(positions) == 1, 'complete_codec_finisher_inventory')
    i = positions[0]
    removed = copy.deepcopy(body[i:i+2])
    expected = ast.parse("decoded = image.artifact_decode(encoded)\n"
        "old.require(exact_tree(decoded, value['evidence']), 'root_codec_roundtrip_order_or_type')").body
    frozen.require([gate.dump(x) for x in removed] == [gate.dump(x) for x in expected],
                   'complete_codec_original_roundtrip_changed')
    del body[i:i+2]
    restored = copy.deepcopy(syntax)
    restored.body[0].body[i:i] = removed
    frozen.require(gate.dump(restored) == gate.dump(original), 'complete_codec_finisher_AST_changed')
    namespace = {**single.finish_root.__globals__, 'evidence': EVIDENCE}
    exec(compile(ast.fix_missing_locations(syntax), '<complete-owned-finisher>', 'exec'), namespace)
    _INTEGRATION_PROOF.update(finisher_inverse_AST_exact=True, ledger_encode_unchanged=True,
                             original_evidence_method_identity_check=True)
    return namespace['finish_root']


finish_root = _finisher()
publish_root = frozen.private(single.publish_root, {'finish_root': finish_root})


def source_proof():
    return {
        'schema': 'g31.complete_root_evidence_candidate.v1',
        **copy.deepcopy(_INTEGRATION_PROOF),
        'codec': codec.source_proof(),
        'frozen_factory_source_sha256': hashlib.sha256(inspect.getsource(frozen._evidence_function).encode()).hexdigest(),
        'original_publication_code_identical': publish_root.__code__ is single.publish_root.__code__,
        'dynamic_native_authority_added': False,
        'scheduler_installed': False,
        'firsthop_changed': False,
        'cost_scope': 'All normalization/first encoding/strict decode/re-encoding/hash/ledger/publication remain inside root.',
    }
