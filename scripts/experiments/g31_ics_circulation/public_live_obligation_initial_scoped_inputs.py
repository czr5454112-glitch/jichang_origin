"""One-call public table scope shared by both initial guards and prediction.

This separate candidate does not modify scoped-v2. The existing caller already
accepts its context provider explicitly, so its exact function/code/globals are
used without rewriting. No supplied context, observation, validation or result
is retained between calls. This is supplied-data model work, not native power.
"""
from __future__ import annotations
import ast
import hashlib
import inspect
import textwrap
from types import SimpleNamespace
from . import profile_live_lazy_six as caller
from . import validate_live_communication_projection as original
from . import public_live_obligation_scoped_inputs_v2 as scoped

SCHEMA = 'g31.live_obligation.initial_and_prediction_scoped_inputs.v1'
_BUILD = caller.build_initial
_BUILD_CODE = _BUILD.__code__
_BUILD_DEFAULTS = _BUILD.__defaults__
_BUILD_KWDEFAULTS = _BUILD.__kwdefaults__
_BUILD_CLOSURE = _BUILD.__closure__
_BUILD_GLOBALS = dict(_BUILD.__globals__)
_PREDICT = scoped.predict
_PREDICT_CODE = _PREDICT.__code__
_SCOPE = scoped.PublicInputScope


def require(value, reason):
    if not value: raise ValueError('initial_scoped_inputs:'+reason)


def _dump(value): return ast.dump(value, include_attributes=False)


def _caller_proof():
    actual = ast.parse(textwrap.dedent(inspect.getsource(_BUILD)))
    expected = ast.parse("""def build_initial(public, prior):
    require(set(public) == {'initial_owners', 'action'} and set(public['initial_owners']) == {'A', 'B'}, 'minimal_initial_input')
    contexts = {owner: prior.context.initial_context(**public['initial_owners'][owner]) for owner in ('A', 'B')}
    require(all(type(value) is prior.context.SuppliedContext for value in contexts.values()), 'initial_context_guards')
    facts = {o: prior.context.initial_projection_bundle(c) for o, c in contexts.items()}
    require(all(prior.context.encoded({'v': facts['A'][f]}) == prior.context.encoded({'v': facts['B'][f]})
        for f in ('jobs', 'trays', 'contract', 'now')), 'independent_owner_facts')
    return contexts['A']
""")
    require(_dump(actual) == _dump(expected), 'original_initial_caller_AST_changed')
    return hashlib.sha256(_dump(actual).encode()).hexdigest()


_CALLER_AST = _caller_proof()


def reference(public):
    """A: original complete two-owner initial construction, then scoped-v2."""
    supplied = _BUILD(public, original)
    return scoped.predict(supplied, public['action'])


def predict(public):
    """B: fresh scope before both original owner guards and the same model."""
    scope = scoped.PublicInputScope()
    supplied = _BUILD(public, SimpleNamespace(context=scope.context))
    return scope.predict(supplied, public['action'])


def source_proof():
    """Preparation proof only; does not build a scope or validate an input."""
    require(caller.build_initial is _BUILD and _BUILD.__code__ is _BUILD_CODE
        and _BUILD.__defaults__ is _BUILD_DEFAULTS and _BUILD.__kwdefaults__ is _BUILD_KWDEFAULTS
        and _BUILD.__closure__ is _BUILD_CLOSURE and set(_BUILD.__globals__) == set(_BUILD_GLOBALS)
        and all(_BUILD.__globals__[k] is v for k,v in _BUILD_GLOBALS.items()), 'initial_caller_identity')
    require(scoped.predict is _PREDICT and scoped.predict.__code__ is _PREDICT_CODE
        and scoped.PublicInputScope is _SCOPE and original.context is scoped.prior.context,
        'scoped_predictor_or_original_context_identity')
    require(_caller_proof() == _CALLER_AST, 'initial_caller_source')
    expected_a = ast.parse("""def reference(public):
    supplied = _BUILD(public, original)
    return scoped.predict(supplied, public['action'])
""")
    expected_b = ast.parse("""def predict(public):
    scope = scoped.PublicInputScope()
    supplied = _BUILD(public, SimpleNamespace(context=scope.context))
    return scope.predict(supplied, public['action'])
""")
    for function,expected in ((reference, expected_a), (predict, expected_b)):
        syntax = ast.parse(textwrap.dedent(inspect.getsource(function)))
        del syntax.body[0].body[0]  # exact function docstring, not a guard
        require(_dump(syntax) == _dump(expected), 'closed_component_topology')
    return {'schema': SCHEMA, 'original_initial_caller_AST_sha256': _CALLER_AST,
        'original_initial_caller_same_function_code_globals_defaults_closure': True,
        'provider_injection': 'Original explicit prior parameter, context field only',
        'initial_owner_order': ['A', 'B'],
        'independent_fact_comparison_order': ['jobs', 'trays', 'contract', 'now'],
        'both_exact_supplied_context_types_required': True,
        'same_scope_context_and_predictor_in_B': True,
        'new_scope_each_call': True, 'cross_call_context_or_result_cache': False,
        'changed_original_guard_or_model_code': False,
        'A_boundary': 'Original two-owner context creation/comparison plus scoped-v2 fresh-scope prediction',
        'B_boundary': 'Fresh scoped-v2 construction plus identical two-owner context creation/comparison plus same-scope prediction',
        'prior_predict_only_ABBA_is_not_this_boundary': True,
        'default_GC_required': True, 'per_sample_cycle_cleanup_certified': False,
        'allocation_failure_timing_equivalent': False,
        'native_authority': False, 'complete_request100ms_certified': False,
        'scope': 'Closed fixed public input construction; stable private builtin state, no concurrent private-table or module mutation.'}
