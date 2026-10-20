"""Fair private C-publisher/owned-decoder composition; no automatic C load.

A is exactly the accepted C-normalizer publisher binding. B uses that SAME
verified provider and normalization facade, and changes only the complete
owned evidence decoder's redundant tree walk. Both retain C fallback, fresh
normalization, all evidence fields/clocks, strict parser/canonical reencoding,
ledger tree validation and publication. This is not Python-versus-C evidence.

Public bind repeats the existing verified C loader/binder contract; the private
composition helper is useful for synthetic wiring tests but grants no C/native
authority. No inputs, normalized trees, parser results or predictions are cached.
"""
from __future__ import annotations

import copy
from types import FunctionType, SimpleNamespace

from . import complete_root_evidence_c_normalizer as reference
from . import complete_root_evidence_owned_decode_v2 as owned

SCHEMA = 'g31.complete_root_evidence_owned_decode.C_binding.v1'
_REFERENCE_BIND = reference.bind
_REFERENCE_BIND_CODE = _REFERENCE_BIND.__code__
_REFERENCE_BIND_GLOBALS = dict(_REFERENCE_BIND.__globals__)


def require(value, reason):
    if not value:
        raise ValueError('owned_C_binding:' + reason)


def _private_delta(original, current, changed):
    require(type(current) is FunctionType and current.__code__ is original.__code__ and
            current.__defaults__ is original.__defaults__ and current.__closure__ is original.__closure__ and
            current.__kwdefaults__ is original.__kwdefaults__, 'function_code_or_closure_changed')
    require(set(current.__globals__) == set(original.__globals__) and
            {key for key in original.__globals__
             if current.__globals__[key] is not original.__globals__[key]} == {changed},
            'private_global_delta')


def _compose(reference_functions):
    """Private wiring only; calling this with test functions is not C authority."""
    require(type(reference_functions) is SimpleNamespace and
            set(vars(reference_functions)) == {'EVIDENCE', 'finish_root', 'publish_root'},
            'reference_function_inventory')
    _private_delta(reference.frozen.EVIDENCE, reference_functions.EVIDENCE, 'normalization')
    _private_delta(reference.frozen.finish_root, reference_functions.finish_root, 'evidence')
    _private_delta(reference.frozen.publish_root, reference_functions.publish_root, 'finish_root')
    facade = reference_functions.EVIDENCE.__globals__['normalization']
    require(type(facade) is SimpleNamespace and set(vars(facade)) == {'normalize'} and
            reference_functions.finish_root.__globals__['evidence'] is reference_functions.EVIDENCE and
            reference_functions.publish_root.__globals__['finish_root'] is reference_functions.finish_root,
            'reference_complete_chain')
    evidence = owned.private(owned.EVIDENCE, {'normalization': facade})
    finish = owned.private(owned.finish_root, {'evidence': evidence})
    publish = owned.private(owned.publish_root, {'finish_root': finish})
    for old, new, name in ((owned.EVIDENCE, evidence, 'normalization'),
                           (owned.finish_root, finish, 'evidence'),
                           (owned.publish_root, publish, 'finish_root')):
        _private_delta(old, new, name)
    require(evidence.__globals__['normalization'] is facade and
            evidence.__globals__['normalization'].normalize is facade.normalize and
            evidence.__globals__['root_runtime_proof'] is
                reference_functions.EVIDENCE.__globals__['root_runtime_proof'] and
            finish.__globals__['image'] is reference_functions.finish_root.__globals__['image'] and
            finish.__code__ is reference_functions.finish_root.__code__ and
            publish.__code__ is reference_functions.publish_root.__code__,
            'unfair_provider_proof_codec_or_publication')
    return SimpleNamespace(EVIDENCE=evidence, finish_root=finish, publish_root=publish)


def bind(candidate):
    """Explicit already-loaded verified provider; no load/build/run is implicit."""
    owned.source_proof()
    require(reference.bind is _REFERENCE_BIND and _REFERENCE_BIND.__code__ is _REFERENCE_BIND_CODE and
            set(_REFERENCE_BIND.__globals__) == set(_REFERENCE_BIND_GLOBALS) and
            all(_REFERENCE_BIND.__globals__[key] is value
                for key, value in _REFERENCE_BIND_GLOBALS.items()), 'reference_binder_changed')
    # The unchanged binder checks exact Candidate/MethodType/C builtins, ABI,
    # source hashes and extension contract. Its existing single fallback stays.
    functions_a = _REFERENCE_BIND(candidate)
    functions_b = _compose(functions_a)
    return SimpleNamespace(A=functions_a, B=functions_b, proof={
        'schema': SCHEMA, 'verified_existing_C_binder_invoked': True,
        'same_normalizer_facade_and_bound_method': True,
        'A_current_C_publisher': True, 'B_same_C_plus_owned_decoder': True,
        'normalization_included_each_call': True, 'decoder_only_difference': True,
        'candidate_input_or_result_cached': False,
        'all_resource_failure_points_equivalent': False,
        'new_native_authority_or_performance_claim': False})


def source_proof():
    return {'schema': SCHEMA, 'owned_decoder': owned.source_proof(),
        'reference_C_contract': copy.deepcopy(reference.source_proof()),
        'public_bind_uses_original_verified_C_binder': reference.bind is _REFERENCE_BIND,
        'proof_scope': 'Source composition only; this call does not load C or establish actual C execution.',
        'fair_comparison': 'A=current verified C publisher; B=identical C provider plus internal owned decoder.',
        'binding_startup_and_complete_publisher_cost_charged': True,
        'fixture_direct_C_support_check_still_required': True,
        'C_binary_or_ABI_acceptance_replaced': False,
        'C_loaded_by_this_module': False, 'native_or_performance_dispatched': False,
        'latency_or_full_day_claim': False}
