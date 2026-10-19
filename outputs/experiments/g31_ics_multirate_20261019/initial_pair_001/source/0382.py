"""One private validated bundle, retaining every original dynamic guard.

The only changed statement removes the second deepcopy of the fresh result
returned by revalidate. The revalidation result is local and not retained or
exposed by any callback. This is a closed supplied-data model candidate; it
does not establish native origin, and is not a general borrowed-object API.
"""
from __future__ import annotations
import ast
import copy
import hashlib
import inspect
import json
import textwrap
from types import FunctionType, SimpleNamespace

from . import public_live_obligation_initial_scoped_inputs as initial_scope
from . import public_live_obligation_scoped_inputs_v2 as scoped

SCHEMA = 'g31.live_obligation.owned_initial_bundle.v1'
_CONTEXT = scoped.prior.context
_PROJECTION = _CONTEXT.initial_projection_bundle
_REVALIDATE = _CONTEXT.revalidate
_PROJECTION_CODE, _REVALIDATE_CODE = _PROJECTION.__code__, _REVALIDATE.__code__
_GLOBALS = dict(_REVALIDATE.__globals__)
_JSON_LOADS, _DEEPCOPY = json.loads, copy.deepcopy
_SUPPLIED = _CONTEXT.SuppliedContext
_SUPPLIED_INIT_CODE = _SUPPLIED.__init__.__code__
_BUILD = initial_scope._BUILD
_BASE_SCOPE = scoped.PublicInputScope


def require(ok, reason):
    if not ok: raise ValueError('owned_initial_bundle:' + reason)


def _tree(function):
    return ast.parse(textwrap.dedent(inspect.getsource(function)))


def _dump(tree): return ast.dump(tree, include_attributes=False)


def _ownership_proof():
    # A closed body proof, not an inference from a "fresh" flag on a value.
    # json.loads creates the private tree; all original reconstruction and
    # byte-integrity gates run before the still-retained deepcopy return.
    expected = ast.parse('''def revalidate(context):
    if type(context) is not SuppliedContext: return unknown('context_type')
    try:
        require(hashlib.sha256(context._payload.encode()).hexdigest()==context._digest,'context_bytes_changed')
        payload = json.loads(context._payload)
        rebuilt = (initial_context(**payload['evidence']) if payload['phase']=='initial'
                   else later_context(**payload['evidence']))
        require(type(rebuilt) is SuppliedContext and rebuilt._payload==context._payload,
                'context_revalidation_changed')
        return copy.deepcopy(payload['validated'])
    except (KeyError,TypeError,ValueError,AttributeError,OverflowError) as exc:
        return unknown(exc)
''')
    actual = _tree(_REVALIDATE)
    require(isinstance(actual.body[0].body[0], ast.Expr)
        and isinstance(actual.body[0].body[0].value, ast.Constant)
        and type(actual.body[0].body[0].value.value) is str, 'revalidate_docstring')
    actual.body[0].body.pop(0)
    require(_dump(actual) == _dump(expected), 'closed_revalidate_body')
    return hashlib.sha256(_dump(expected).encode()).hexdigest()


def _compile_projection():
    original = _tree(_PROJECTION); changed = copy.deepcopy(original)
    matches = [node for node in ast.walk(changed) if isinstance(node, ast.Assign)
        and ast.unparse(node) == "bundle = copy.deepcopy(result['bundle'])"]
    require(len(matches) == 1, 'single_redundant_bundle_copy')
    old_value = copy.deepcopy(matches[0].value)
    matches[0].value = ast.parse("result['bundle']", mode='eval').body
    inverse = copy.deepcopy(changed)
    restored = [node for node in ast.walk(inverse) if isinstance(node, ast.Assign)
        and ast.unparse(node) == "bundle = result['bundle']"]
    require(len(restored) == 1, 'single_inverse_bundle_binding')
    restored[0].value = old_value
    require(_dump(inverse) == _dump(original), 'inverse_projection_AST')
    # No supplied input is used during compilation. Defining globals are not
    # changed; each runtime binding receives the actual scope's full namespace.
    namespace = dict(_PROJECTION.__globals__)
    exec(compile(ast.fix_missing_locations(changed), '<owned-initial-bundle>', 'exec'), namespace)
    return namespace[_PROJECTION.__name__].__code__, {
        'original_projection_AST_sha256': hashlib.sha256(_dump(original).encode()).hexdigest(),
        'modified_projection_AST_sha256': hashlib.sha256(_dump(changed).encode()).hexdigest(),
        'inverse_AST_exact': True,
        'changed_statement_only': "bundle = copy.deepcopy(result['bundle']) -> bundle = result['bundle']"}


_OWNERSHIP_AST = _ownership_proof()
_CODE, _AST_PROOF = _compile_projection()


def implementation_identity():
    require(_CONTEXT.initial_projection_bundle is _PROJECTION
        and _CONTEXT.revalidate is _REVALIDATE
        and _PROJECTION.__code__ is _PROJECTION_CODE
        and _REVALIDATE.__code__ is _REVALIDATE_CODE,
        'original_context_functions_changed')
    require(set(_REVALIDATE.__globals__) == set(_GLOBALS)
        and all(_REVALIDATE.__globals__[key] is value for key,value in _GLOBALS.items()),
        'original_context_globals_changed')
    require(json.loads is _JSON_LOADS and copy.deepcopy is _DEEPCOPY
        and _CONTEXT.SuppliedContext is _SUPPLIED
        and _SUPPLIED.__init__.__code__ is _SUPPLIED_INIT_CODE,
        'ownership_primitives_changed')
    require(initial_scope._BUILD is _BUILD and scoped.PublicInputScope is _BASE_SCOPE,
        'initial_scope_interfaces_changed')


def _private_projection(original):
    require(original.__code__ is _PROJECTION_CODE
        and original.__defaults__ is _PROJECTION.__defaults__
        and original.__kwdefaults__ is _PROJECTION.__kwdefaults__
        and original.__closure__ is _PROJECTION.__closure__, 'projection_metadata')
    namespace = original.__globals__
    require(set(namespace) == set(_GLOBALS)
        and namespace['revalidate'].__code__ is _REVALIDATE_CODE
        and namespace['revalidate'].__globals__ is namespace
        and namespace['SuppliedContext'] is _SUPPLIED,
        'complete_scope_context_namespace')
    # Sharing the existing namespace here is safe: no mutation is performed.
    # revalidate, initial/later guards and unknown retain the original binding.
    function = FunctionType(_CODE, namespace, original.__name__, original.__defaults__, original.__closure__)
    function.__kwdefaults__ = original.__kwdefaults__
    return function


class PublicInputScope(_BASE_SCOPE):
    def __init__(self):
        implementation_identity()
        super().__init__()
        self._owned_original_context = self.context
        self._owned_original_predict = self.predict
        projection = _private_projection(self.context.initial_projection_bundle)
        self.context = SimpleNamespace(**{**vars(self.context), 'initial_projection_bundle': projection})
        self.predict = scoped.prior.private(self.predict, {**self.predict.__globals__, 'context': self.context})

    def source_proof(self):
        implementation_identity()
        # This verifies the retained, unchanged guard namespace. Its historical
        # unchanged-functions list does not describe our separately bound helper.
        retained = super().source_proof()
        function = self.context.initial_projection_bundle
        require(function.__code__ is _CODE and function.__globals__ is self._context_namespace
            and function.__defaults__ is _PROJECTION.__defaults__
            and function.__kwdefaults__ is _PROJECTION.__kwdefaults__
            and function.__closure__ is _PROJECTION.__closure__, 'owned_projection_binding')
        require(set(vars(self.context)) == set(vars(self._owned_original_context))
            and all(getattr(self.context,key) is value for key,value in vars(self._owned_original_context).items()
                    if key != 'initial_projection_bundle'), 'context_facade_only_one_change')
        require(self._context_namespace['initial_projection_bundle'] is self._owned_original_context.initial_projection_bundle
            and self.context.revalidate is self._owned_original_context.revalidate
            and self.context.revalidate.__code__ is _REVALIDATE_CODE
            and self.context.revalidate.__globals__ is self._context_namespace,
            'dynamic_revalidation_unchanged')
        require(self.predict.__code__ is self._owned_original_predict.__code__
            and self.predict.__defaults__ is self._owned_original_predict.__defaults__
            and self.predict.__kwdefaults__ is self._owned_original_predict.__kwdefaults__
            and self.predict.__closure__ is self._owned_original_predict.__closure__
            and set(self.predict.__globals__) == set(self._owned_original_predict.__globals__)
            and all(self.predict.__globals__[key] is value for key,value in self._owned_original_predict.__globals__.items()
                    if key != 'context') and self.predict.__globals__['context'] is self.context,
            'predict_context_binding_only')
        return {**source_proof(), 'retained_guard_namespace_proof': retained,
            'retained_namespace_proof_is_not_modified_projection_code_proof': True,
            'actual_projection_binding_checked': True, 'dynamic_revalidation_code_and_namespace_unchanged': True}


def reference(public):
    """Current initial-scope candidate: original bundle deepcopy retained."""
    return initial_scope.predict(public)


def predict(public):
    """Fresh scope; exact original A/B constructor and model entry."""
    scope = PublicInputScope()
    supplied = _BUILD(public, SimpleNamespace(context=scope.context))
    return scope.predict(supplied, public['action'])


def source_proof():
    implementation_identity()
    require(_ownership_proof() == _OWNERSHIP_AST, 'ownership_source_changed')
    return {**_AST_PROOF, 'schema': SCHEMA, 'ownership_revalidate_AST_sha256': _OWNERSHIP_AST,
        'revalidate_full_guards_and_deepcopy_return_retained': True,
        'removed_copy_count_per_projection_bundle_call': 1,
        'fresh_result_ownership': 'Original revalidate returns deepcopy of a private json.loads tree; its result is only a local variable here.',
        'protocol_copy_resource_conversion_load_end_and_output_fields_unchanged': True,
        'initial_A_B_guards_fact_comparison_and_predictor_unchanged': True,
        'cross_call_validation_or_observation_or_output_cache': False,
        'allocation_failure_timing_equivalent': False, 'per_sample_cycle_cleanup_certified': False,
        'all_scope_construction_and_guards_must_be_charged': True,
        'source_domain': 'Frozen serial builtin supplied-data implementation; no concurrent private-namespace mutation or callback injection.',
        'native_authority': False, 'complete_request100ms_certified': False}
