"""Explicit single-capture / verified C + owned-decoder publisher binding.

Only the complete evidence publication path changes. Collection normalization,
native authority, actual advance chain, first-hop predicate, ACK/drain and all
clock positions remain the frozen single-capture implementation. No C loading,
worker, campaign installation or native execution happens on import.
"""
from __future__ import annotations

import copy
from types import FunctionType, SimpleNamespace

from . import initial_owner_route_single_capture_integration as previous
from . import complete_root_evidence_owned_decode_c_binding as publisher

SCHEMA = 'g31.single_capture.verified_C_owned_publisher_binding.v1'
private, require = previous.private, previous.require
_BIND = publisher.bind
_BIND_CODE = _BIND.__code__
_BIND_GLOBALS = dict(_BIND.__globals__)


def _delta(original, current, changes):
    require(type(current) is FunctionType and current.__code__ is original.__code__
        and current.__defaults__ is original.__defaults__
        and current.__kwdefaults__ is original.__kwdefaults__
        and current.__closure__ is original.__closure__, 'owned_live_function_identity')
    require(set(current.__globals__) == set(original.__globals__)
        and all(value is changes.get(name, original.__globals__[name])
            for name, value in current.__globals__.items()), 'owned_live_full_globals')


def _publisher_check(functions):
    """Shape/source composition only. This does not establish C execution."""
    require(type(functions) is SimpleNamespace
        and set(vars(functions)) == {'EVIDENCE', 'finish_root', 'publish_root'},
        'owned_live_publisher_inventory')
    facade = functions.EVIDENCE.__globals__['normalization']
    require(type(facade) is SimpleNamespace and set(vars(facade)) == {'normalize'}
        and callable(facade.normalize), 'owned_live_normalizer_facade')
    _delta(publisher.owned.EVIDENCE, functions.EVIDENCE, {'normalization': facade})
    _delta(publisher.owned.finish_root, functions.finish_root, {'evidence': functions.EVIDENCE})
    _delta(publisher.owned.publish_root, functions.publish_root, {'finish_root': functions.finish_root})
    require(functions.EVIDENCE.__globals__['root_runtime_proof']
            is previous.EVIDENCE.__globals__['root_runtime_proof']
        and functions.finish_root.__code__ is previous.finish_root.__code__
        and functions.publish_root.__code__ is previous.publish_root.__code__,
        'owned_live_runtime_proof_or_clock_code')


def _compose(functions):
    """Private synthetic wiring seam; NOT a verified-C/provider entry point."""
    _publisher_check(functions)

    class CapturedRequest(previous.CapturedRequest):
        evidence = functions.EVIDENCE

    class FixedDefaultRequest(CapturedRequest):
        choose = previous.FixedDefaultRequest.choose

    # The original chain checks exact collect/observer/drain method identities,
    # not the request subclass or evidence method. All three methods are still
    # inherited unchanged. Retaining this SAME chain preserves its exact-type
    # drain check and original __class__/super cell without a new allowlist.
    run = private(previous.run_continuation, {'publish_root': functions.publish_root})
    run._source_proof = copy.deepcopy(previous.run_continuation._source_proof)
    result = SimpleNamespace(CapturedRequest=CapturedRequest, FixedDefaultRequest=FixedDefaultRequest,
        ActualAdvanceChain=previous.ActualAdvanceChain,
        EVIDENCE=functions.EVIDENCE, finish_root=functions.finish_root, publish_root=functions.publish_root,
        run_continuation=run, call_with_recorded_collection=previous.call_with_recorded_collection,
        TracedContinuationOwner=previous.TracedContinuationOwner, make_client=previous.make_client,
        TRACED_OBSERVE=previous.TRACED_OBSERVE, TRACKED_DRAIN=previous.TRACKED_DRAIN,
        collection_inventory=previous.collection_inventory)
    binding_proof(result)
    return result


def binding_proof(binding):
    require(type(binding) is SimpleNamespace, 'owned_live_binding_type')
    _publisher_check(SimpleNamespace(EVIDENCE=binding.EVIDENCE,
        finish_root=binding.finish_root, publish_root=binding.publish_root))
    for name in ('ActualAdvanceChain', 'call_with_recorded_collection', 'TracedContinuationOwner',
                 'make_client', 'TRACED_OBSERVE', 'TRACKED_DRAIN', 'collection_inventory'):
        require(getattr(binding, name) is getattr(previous, name), 'owned_live_changed_' + name)
    require(binding.CapturedRequest.__bases__ == (previous.CapturedRequest,)
        and binding.FixedDefaultRequest.__bases__ == (binding.CapturedRequest,), 'owned_live_request_MRO')
    for cls in (binding.CapturedRequest, binding.FixedDefaultRequest):
        for name in ('collect', 'final_revalidate_and_submit', 'observe_after_boundary',
                     'drain_and_finish_if_closed', '_record'):
            require(getattr(cls, name) is getattr(previous.CapturedRequest, name),
                'owned_live_changed_request_' + name)
        require(cls.evidence is binding.EVIDENCE, 'owned_live_request_evidence')
    require(binding.FixedDefaultRequest.choose is previous.FixedDefaultRequest.choose,
        'owned_live_default_policy_changed')
    _delta(previous.run_continuation, binding.run_continuation, {'publish_root': binding.publish_root})
    require(binding.run_continuation._source_proof == previous.run_continuation._source_proof,
        'owned_live_scheduler_proof_changed')
    constructor = binding.ActualAdvanceChain.__init__
    require(constructor is previous.ActualAdvanceChain.__init__
        and constructor.__globals__['CapturedRequest'].collect is binding.CapturedRequest.collect
        and constructor.__globals__['TRACKED_DRAIN'] is binding.TRACKED_DRAIN
        and constructor.__globals__['TRACED_OBSERVE'] is binding.TRACED_OBSERVE
        and previous._actual_root_drain.__globals__['ActualAdvanceChain'] is binding.ActualAdvanceChain,
        'owned_live_exact_chain_contract')
    return {'schema': SCHEMA, 'complete_publisher_only': True,
        'same_single_capture_initial_A_final_A_and_B_wrapper': True,
        'collection_normalization_changed': False, 'model_or_predictor_changed': False,
        'same_exact_chain_constructor_classcell_and_drain': True,
        'same_current_native_handle_transport_and_ACK_guards': True,
        'same_scheduler_code_admissions_and_firsthop': True,
        'same_original_complete_runtime_query_proof': True,
        'same_full_evidence_clocks_hash_ledger_and_return': True,
        'verified_C_claim_from_this_shape_check': False,
        'direct_C_support_must_be_measured_separately': True,
        'general_owned_bytes_decoder_created': False,
        'campaign_or_failure_aware_saved_verifier_included': False,
        'native_or_model_dispatched': False, 'complete100ms_certified': False}


def branch_function(binding):
    """Optional current branch clone; includes its direct failure publication.

B has no separate request publisher: its freshly collected records are part of
the complete A root. The B wrapper and all collection paths remain identical.
No worker/launcher or saved-verifier installation is supplied here.
"""
    from . import initial_owner_route_single_capture_campaign as campaign
    binding_proof(binding)
    function = private(campaign.run_branch, {
        'CapturedRequest': binding.CapturedRequest,
        'FixedDefaultRequest': binding.FixedDefaultRequest,
        'run_continuation': binding.run_continuation,
        'publish_root': binding.publish_root})
    branch_source_proof(binding, function)
    return function


def branch_source_proof(binding, function):
    from . import initial_owner_route_single_capture_campaign as campaign
    binding_proof(binding)
    _delta(campaign.run_branch, function, {
        'CapturedRequest': binding.CapturedRequest,
        'FixedDefaultRequest': binding.FixedDefaultRequest,
        'run_continuation': binding.run_continuation,
        'publish_root': binding.publish_root})
    require(function.__globals__['call_with_recorded_collection'] is previous.call_with_recorded_collection,
        'owned_live_B_wrapper_changed')
    return {'original_branch_code_and_complete_globals': True,
        'direct_and_scheduler_publication_both_bound': True,
        'B_fresh_collection_and_failure_paths_unchanged': True,
        'schema_and_branch_start_clock_unchanged': True,
        'worker_or_saved_verifier_installed': False}


def bind(candidate):
    """Explicit verified Candidate only; existing binder performs acceptance."""
    source_proof()
    require(publisher.bind is _BIND and _BIND.__code__ is _BIND_CODE
        and set(_BIND.__globals__) == set(_BIND_GLOBALS)
        and all(_BIND.__globals__[key] is value for key, value in _BIND_GLOBALS.items()),
        'owned_live_verified_binder_changed')
    # Exact Candidate / bound C builtin / module / ABI / original-source checks
    # all execute in the unchanged existing binder. No fallback is added here.
    accepted = _BIND(candidate)
    return _compose(accepted.B)


def source_proof():
    return {'schema': SCHEMA, 'single_capture': previous.integration_proof(),
        'owned_C_publisher': publisher.source_proof(),
        'explicit_verified_candidate_required': True, 'C_load_or_build_implicit': False,
        'complete_collection_inventory_and_generated_hooks_retained': True,
        'exact_native_type_or_classcell_changed': False,
        'frozen_source_or_imported_globals_modified': False,
        'binding_setup_and_all_complete_publisher_costs_must_be_charged': True,
        'per_sample_cycle_cleanup_certified': False,
        'resource_failure_points_equivalent': False,
        'actual_campaign_or_performance_claim': False}
