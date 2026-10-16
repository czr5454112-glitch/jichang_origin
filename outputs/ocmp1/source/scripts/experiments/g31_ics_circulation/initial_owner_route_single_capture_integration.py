"""Private single-triplet wiring for the accepted entry/complete-codec root.

Source/pure integration only: no worker, failure verifier or campaign dispatch.
All three collection sites read again when called; no observation, ledger or
native capability is cached. The original native/session checks and scheduler
remain. Getter-count equivalence is deliberately not claimed.
"""
from __future__ import annotations
import copy
import dis
import hashlib
import inspect
import json
from types import CodeType, SimpleNamespace

from . import initial_owner_route_entry_codec_integration as previous
from . import initial_owner_route_single_capture as single

private, require = previous.private, previous.require
gated = previous.entry.previous
gate, old, request = gated.gate, gated.old, gated.request
contract = previous.contract


# The private adapter facade is created by the original wrapper on EVERY call.
# Initial A, final A and fixed-participant B all use this identical wrapper.
call_with_recorded_collection = private(old.call_with_recorded_collection,
    {'captured_collection': single.captured_collection})
_old_facade = SimpleNamespace(**{**vars(old),
    'call_with_recorded_collection': call_with_recorded_collection})
COLLECT = private(gated.CapturedRequest.collect, {'old': _old_facade})
FINAL_REVALIDATE = private(old.CapturedRequest.final_revalidate_and_submit,
    {'call_with_recorded_collection': call_with_recorded_collection})
TRACED_COLLECT = gated.TRACED_COLLECT
TRACED_OBSERVE = previous.TRACED_OBSERVE


class ActualAdvanceChain(previous.ActualAdvanceChain):
    pass


_actual_root_drain = private(previous.entry._actual_root_drain,
    {'ActualAdvanceChain': ActualAdvanceChain})
TRACKED_DRAIN = private(previous.TRACKED_DRAIN,
    {'_actual_root_drain': _actual_root_drain})


class CapturedRequest(previous.CapturedRequest):
    collect = COLLECT
    final_revalidate_and_submit = FINAL_REVALIDATE
    drain_and_finish_if_closed = TRACKED_DRAIN


class FixedDefaultRequest(CapturedRequest):
    choose = previous.FixedDefaultRequest.choose


def _code_tree(value):
    """Stable code data, independent of marshal's object-reference flags."""
    if type(value) is CodeType:
        return ['code', {name: _code_tree(getattr(value, name)) for name in (
            'co_argcount', 'co_posonlyargcount', 'co_kwonlyargcount', 'co_nlocals',
            'co_stacksize', 'co_flags', 'co_code', 'co_consts', 'co_names',
            'co_varnames', 'co_freevars', 'co_cellvars', 'co_filename', 'co_name',
            'co_qualname', 'co_firstlineno', 'co_linetable', 'co_exceptiontable')}]
    if type(value) is tuple: return ['tuple', [_code_tree(v) for v in value]]
    if type(value) is frozenset:
        rows = [_code_tree(v) for v in value]
        return ['frozenset', sorted(rows, key=lambda v: json.dumps(v, ensure_ascii=True))]
    if type(value) is bytes: return ['bytes', value.hex()]
    if type(value) is float: return ['float', value.hex()]
    if type(value) is complex: return ['complex', value.real.hex(), value.imag.hex()]
    if value is Ellipsis: return ['ellipsis']
    if value is None or type(value) in (str, bool, int): return [type(value).__name__, value]
    raise ValueError('single_capture_unsupported_code_constant')


def _code_digest(function):
    encoded = json.dumps(_code_tree(function.__code__), ensure_ascii=True,
        allow_nan=False, separators=(',', ':')).encode('ascii')
    return hashlib.sha256(encoded).hexdigest()


# Capture actual defining attributes, not caller-supplied source identities.
# The generated template is handled separately: its co_filename deliberately
# names the ORIGINAL collector, so inspect.getsource(template) is misleading.
_LOCATIONS = (
    (single, '_compile_native_template'), (single, 'clone'),
    (single, 'require'), (single, 'source_proof'),
    (single, 'instrument_native'), (single, 'collector'),
    (single, 'captured_collection'),
    (single._Capture, '__init__'), (single._Capture, 'before'),
    (single._Capture, 'after'), (single._Capture, 'endpoints'),
    (single.normalization, 'normalize'), (single.normalization, 'typed_failure_snapshot'),
    (old, 'call_with_recorded_collection'),
)
_BINDINGS = tuple((holder, name, getattr(holder, name), getattr(holder, name).__code__)
    for holder, name in _LOCATIONS)
_CAPTURE_TYPE = single._Capture
_TEMPLATE = single._TEMPLATE
_TEMPLATE_CODE = _TEMPLATE.__code__
_TEMPLATE_AST_PROOF = copy.deepcopy(single._AST_PROOF)


def _binding_record(holder, name, function, code):
    require(getattr(holder, name) is function and function.__code__ is code,
        'single_capture_collection_source_changed:' + name)
    require(not gate.native_advance_sites(function), 'single_capture_hidden_advance:' + name)
    return {'source_sha256': hashlib.sha256(inspect.getsource(function).encode()).hexdigest(),
        'code_sha256': _code_digest(function), 'native_advance_sites': []}


def generated_template_inventory():
    require(single._Capture is _CAPTURE_TYPE and single._TEMPLATE is _TEMPLATE
        and _TEMPLATE.__code__ is _TEMPLATE_CODE and single._AST_PROOF == _TEMPLATE_AST_PROOF,
        'single_capture_template_identity_changed')
    # Direct code inspection includes the six hooks absent from the original
    # source. No fallback maps this generated code to an uninstrumented method.
    instructions = list(dis.get_instructions(_TEMPLATE))
    hooks = []
    for index, instruction in enumerate(instructions):
        if instruction.opname == 'LOAD_GLOBAL' and instruction.argval == '_capture':
            require(index + 1 < len(instructions)
                and instructions[index + 1].opname in ('LOAD_METHOD', 'LOAD_ATTR'),
                'single_capture_template_hook_shape')
            hooks.append(instructions[index + 1].argval)
    require(hooks == ['before', 'after'] * 3, 'single_capture_template_hook_order')
    require(not set(_TEMPLATE.__code__.co_names) & gate.MUTATING_ADVANCES,
        'single_capture_template_hidden_advance')
    require(_TEMPLATE_AST_PROOF.get('inverse_AST_exact') is True
        and _TEMPLATE_AST_PROOF.get('inserted_before_after_hooks') == 6,
        'single_capture_template_AST_proof')
    return {'generated_code_sha256': _code_digest(_TEMPLATE),
        'proof': copy.deepcopy(_TEMPLATE_AST_PROOF), 'ordered_code_hooks': hooks,
        'source_lookup_for_generated_function_used': False,
        'factory_source_sha256': hashlib.sha256(inspect.getsource(single._compile_native_template).encode()).hexdigest(),
        'native_advance_names': []}


def collection_inventory():
    # Keep every old pre-chain/native authority/hidden-advance guard and ADD the
    # new concrete path. This is source binding for a closed pinned program,
    # not a sandbox against arbitrary mutable Python plugins.
    original = gate.collection_inventory()
    proof = single.source_proof()
    require(single._Capture is _CAPTURE_TYPE, 'single_capture_class_changed')
    functions = {}
    for holder, name, function, code in _BINDINGS:
        functions[function.__module__ + '.' + function.__qualname__] = _binding_record(
            holder, name, function, code)
    require(call_with_recorded_collection.__code__ is old.call_with_recorded_collection.__code__
        and call_with_recorded_collection.__globals__['captured_collection'] is single.captured_collection,
        'single_capture_wrapper_binding')
    require(COLLECT.__globals__['old'] is _old_facade
        and _old_facade.call_with_recorded_collection is call_with_recorded_collection
        and COLLECT.__globals__['TRACED_COLLECT'] is TRACED_COLLECT
        and FINAL_REVALIDATE.__globals__['call_with_recorded_collection'] is call_with_recorded_collection,
        'single_capture_callsite_binding')
    return {'original_authority_and_advance_inventory': original,
        'frozen_prototype_source_proof': proof,
        'prototype_campaign_installed_field_is_historical_not_current_wiring': True,
        'private_integration_wired': True, 'actual_campaign_ready': False,
        'additional_functions': functions,
        'generated_template': generated_template_inventory(),
        'three_roles': ['A_initial', 'A_fresh_final', 'B_fixed_participant'],
        'each_invocation_fresh': True, 'session_or_native_proxy': False}


_gate_facade = SimpleNamespace(**{**vars(gate), 'collection_inventory': collection_inventory})
# Preserve the original __class__ cell: super() still starts after the defining
# gated.ActualAdvanceChain in this subclass's MRO and initializes _RecordedChain.
ActualAdvanceChain.__init__ = private(previous.ActualAdvanceChain.__init__, {
    'TRACKED_DRAIN': TRACKED_DRAIN, 'TRACED_OBSERVE': TRACED_OBSERVE,
    'CapturedRequest': CapturedRequest, 'gate': _gate_facade,
})
EVIDENCE, finish_root, publish_root = previous.EVIDENCE, previous.finish_root, previous.publish_root
run_continuation = private(previous.run_continuation, {'ActualAdvanceChain': ActualAdvanceChain})
run_continuation._source_proof = copy.deepcopy(previous.run_continuation._source_proof)
TracedContinuationOwner, make_client = previous.TracedContinuationOwner, previous.make_client


def branch_function():
    """Optional source-only branch clone; no worker/launcher/failure audit."""
    from . import initial_owner_route_entry_codec_campaign as campaign
    function = private(campaign.run_branch, {'CapturedRequest': CapturedRequest,
        'FixedDefaultRequest': FixedDefaultRequest, 'run_continuation': run_continuation,
        'call_with_recorded_collection': call_with_recorded_collection})
    branch_source_proof(function)
    return function


def branch_source_proof(function):
    from . import initial_owner_route_entry_codec_campaign as campaign
    original = campaign.run_branch
    expected = {'CapturedRequest': CapturedRequest, 'FixedDefaultRequest': FixedDefaultRequest,
        'run_continuation': run_continuation, 'call_with_recorded_collection': call_with_recorded_collection}
    require(function.__code__ is original.__code__ and function.__closure__ is original.__closure__
        and function.__defaults__ is original.__defaults__ and function.__kwdefaults__ is original.__kwdefaults__
        and set(function.__globals__) == set(original.__globals__), 'single_capture_branch_code_or_namespace')
    require(all(value is expected.get(name, original.__globals__[name])
        for name, value in function.__globals__.items()), 'single_capture_branch_binding')
    return {'original_branch_code_and_complete_globals': True,
        'changed_global_bindings': sorted(expected), 'new_B_wrapper_bound': True,
        'worker_or_failure_verifier_included': False}


def integration_proof():
    previous_proof = previous.integration_proof()
    require(COLLECT.__code__ is gated.CapturedRequest.collect.__code__
        and FINAL_REVALIDATE.__code__ is old.CapturedRequest.final_revalidate_and_submit.__code__,
        'single_capture_method_code_changed')
    require(CapturedRequest.collect is COLLECT
        and CapturedRequest.final_revalidate_and_submit is FINAL_REVALIDATE
        and FixedDefaultRequest.collect is COLLECT
        and FixedDefaultRequest.final_revalidate_and_submit is FINAL_REVALIDATE,
        'single_capture_request_methods_changed')
    require(CapturedRequest.evidence is previous.EVIDENCE
        and CapturedRequest.observe_after_boundary is previous.TRACED_OBSERVE
        and TRACKED_DRAIN.__code__ is previous.TRACKED_DRAIN.__code__
        and TRACKED_DRAIN.__globals__['_actual_root_drain'] is _actual_root_drain
        and _actual_root_drain.__globals__['ActualAdvanceChain'] is ActualAdvanceChain,
        'single_capture_root_binding')
    constructor = ActualAdvanceChain.__init__
    require(constructor.__code__ is previous.ActualAdvanceChain.__init__.__code__
        and constructor.__closure__ is previous.ActualAdvanceChain.__init__.__closure__
        and constructor.__globals__['gate'] is _gate_facade
        and constructor.__globals__['CapturedRequest'] is CapturedRequest,
        'single_capture_constructor_binding')
    cell = dict(zip(constructor.__code__.co_freevars, constructor.__closure__ or ()))['__class__']
    require(cell.cell_contents is gated.ActualAdvanceChain
        and ActualAdvanceChain.__mro__[ActualAdvanceChain.__mro__.index(gated.ActualAdvanceChain) + 1]
            is gate._RecordedChain, 'single_capture_super_MRO')
    require(run_continuation.__code__ is previous.run_continuation.__code__
        and run_continuation.__globals__['ActualAdvanceChain'] is ActualAdvanceChain
        and run_continuation.__globals__['publish_root'] is publish_root
        and publish_root is previous.publish_root and finish_root is previous.finish_root,
        'single_capture_scheduler_or_publisher_changed')
    return {'schema': 'g31.initial_owner.single_capture_integration.v1',
        'previous_entry_codec': previous_proof, 'collection': collection_inventory(),
        'same_scheduler_code_and_background_admissions': True,
        'same_complete_evidence_codec_and_firsthop_ACK_drain': True,
        'constructor_class_cell_and_exact_native_checks_preserved': True,
        'A_initial_A_final_B_same_fresh_wrapper': True,
        'all_endpoint_query_side_effect_equivalence_claimed': False,
        'old_frozen_modules_modified': False, 'campaign_ready': False,
        'failure_aware_saved_verifier_included': False, 'native_or_predictor_dispatched': False,
        'performance_or_100ms_claim': False}
