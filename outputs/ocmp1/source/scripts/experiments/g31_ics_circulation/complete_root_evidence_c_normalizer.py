"""Private complete-evidence publisher binding; no campaign installation.

Only the owned normalization provider changes. The full evidence, original
strict codec, clocks, hash, ledger and publisher return code are retained.
Loading/building the data-only extension is an explicit caller responsibility.
"""
from types import BuiltinFunctionType, MethodType, SimpleNamespace

from . import complete_tree_normalizer_candidate as provider
from . import initial_owner_route_entry_codec_integration as frozen

_METHOD = provider.Candidate.normalize
_METHOD_CODE = _METHOD.__code__
_FUNCTIONS = tuple((fn, fn.__code__) for fn in
                   (frozen.EVIDENCE, frozen.finish_root, frozen.publish_root))


def require(value, reason):
    if not value:
        raise ValueError('complete_C_evidence:' + reason)


def _bind_provider(normalize):
    """Internal source/pure binding mechanism, not C or native authority."""
    require(all(fn.__code__ is code for fn, code in _FUNCTIONS), 'frozen_code_changed')
    require((frozen.EVIDENCE, frozen.finish_root, frozen.publish_root) ==
            tuple(fn for fn, _ in _FUNCTIONS), 'frozen_function_changed')
    require(frozen.EVIDENCE.__globals__['normalization'] is provider.original,
            'original_normalization_binding')
    evidence = frozen.private(frozen.EVIDENCE,
        {'normalization': SimpleNamespace(normalize=normalize)})
    finish = frozen.private(frozen.finish_root, {'evidence': evidence})
    publish = frozen.private(frozen.publish_root, {'finish_root': finish})
    for original, current, changed in ((frozen.EVIDENCE, evidence, 'normalization'),
            (frozen.finish_root, finish, 'evidence'), (frozen.publish_root, publish, 'finish_root')):
        require(current.__code__ is original.__code__ and current.__defaults__ is original.__defaults__ and
                current.__closure__ is original.__closure__ and current.__kwdefaults__ is original.__kwdefaults__,
                'publisher_code_or_closure_changed')
        require(set(current.__globals__) == set(original.__globals__) and
                {key for key in original.__globals__
                 if current.__globals__[key] is not original.__globals__[key]} == {changed},
                'private_global_domain')
    return SimpleNamespace(EVIDENCE=evidence, finish_root=finish, publish_root=publish)


def bind(candidate):
    """Bind an independently loaded verified C provider, including its fallback."""
    require(type(candidate) is provider.Candidate, 'verified_candidate_required')
    require(provider.Candidate.normalize is _METHOD and _METHOD.__code__ is _METHOD_CODE and
            type(candidate.normalize) is MethodType and candidate.normalize.__func__ is _METHOD and
            candidate.normalize.__self__ is candidate, 'candidate_method_changed')
    require(type(candidate._try) is BuiltinFunctionType and
            candidate._try is candidate.module.try_normalize and
            candidate._try.__self__ is candidate.module, 'bound_C_builtin_required')
    # Repeat the existing loader's source/ABI/extension contract validation at
    # binding time; do not add disk hashing to each normalization/request.
    provider.Candidate(candidate.module, candidate.source_sha256)
    return _bind_provider(candidate.normalize)


def source_proof():
    return {'schema': 'g31.complete_root_evidence.C_normalizer_binding.v1',
        'reference_entry_codec': frozen.integration_proof(),
        'reference_normalization_unchanged_claim_is_historical_only': True,
        'changed': 'Private evidence global normalization.normalize is the verified Candidate bound method.',
        'unchanged': ['complete evidence fields and order', 'actual runtime proof provider',
            'original body timestamp position', 'original owned encoder and strict decoder/reencode',
            'full hash/ledger/return codec', 'publisher append/outside-return/closure code'],
        'original_fallback_retained': True,
        'direct_C_support_required_separately_for_fixed_inputs': True,
        'new_campaign_or_native_authority': False,
        'ABI_scope': 'Independently pinned CPython3.11.9 extension and stable private input only.',
        'cost_scope': 'Complete data construction through publisher return; binding/load/setup also charged in whole campaign.',
        'performance_or_100ms_claim': False}
