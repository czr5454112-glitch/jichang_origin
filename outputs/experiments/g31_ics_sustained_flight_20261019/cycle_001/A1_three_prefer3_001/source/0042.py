"""Static float bits extension; original finite JSON/model guards unchanged.

The failed v1 dependency bind treated an internal nonfinite float constant as
if it were public JSON data. Static built-in floats are now sealed by their
complete IEEE-754 bytes, including infinity, NaN payload/sign and signed zero.
No dependency is omitted. No normalization or permission is added to proof
JSON, observations or models. All frozen v1 files remain unchanged.
"""
from __future__ import annotations

import struct
from types import FunctionType
from . import live_obligation_bound_source_proof as original

VERSION = 'g31.request_owned_static_source_proof.v2'


def _atom(value):
    if type(value) is float:
        return float, struct.pack('>d', value)
    return original._atom(value)


def _clone(function, namespace):
    clone = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    clone.__kwdefaults__ = function.__kwdefaults__
    return clone


_NAMESPACE = {**vars(original), '_atom': _atom, 'VERSION': VERSION}
_visit_exact = _clone(original.DependencySeal._visit, _NAMESPACE)
_same_exact = _clone(vars(original.DependencySeal)['_same'].__func__, _NAMESPACE)


class DependencySeal(original.DependencySeal):
    _same = staticmethod(_same_exact)

    def _visit(self, value, label):
        try:
            return _visit_exact(self, value, label)
        except BaseException as error:
            # Annotate only the deepest dependency, preserving exception type
            # and object. Nested callers must not obscure that first label.
            prefix = 'bound_source_proof_v2 dependency_label='
            if not any(type(note) is str and note.startswith(prefix)
                       for note in getattr(error, '__notes__', ())):
                error.add_note(prefix + label)
            raise


_NAMESPACE['DependencySeal'] = DependencySeal


class RequestStaticProof(original.RequestStaticProof):
    __init__ = _clone(original.RequestStaticProof.__init__, _NAMESPACE)
    description = _clone(original.RequestStaticProof.description, _NAMESPACE)


_NAMESPACE['RequestStaticProof'] = RequestStaticProof
bind_declared = _clone(original.bind_declared, _NAMESPACE)
require = original.require


def source_proof():
    changed = {'_atom': _atom, 'VERSION': VERSION, 'DependencySeal': DependencySeal,
               'RequestStaticProof': RequestStaticProof}
    original.require(set(_NAMESPACE) == set(vars(original))
        and all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in changed)
        and all(_NAMESPACE[k] is v for k, v in changed.items()), 'v2_complete_private_globals')
    for actual, prior in ((_visit_exact, original.DependencySeal._visit),
        (_same_exact, vars(original.DependencySeal)['_same'].__func__),
        (RequestStaticProof.__init__, original.RequestStaticProof.__init__),
        (RequestStaticProof.description, original.RequestStaticProof.description),
        (bind_declared, original.bind_declared)):
        original.require(actual.__code__ is prior.__code__ and actual.__defaults__ is prior.__defaults__
            and actual.__kwdefaults__ is prior.__kwdefaults__ and actual.__closure__ is prior.__closure__
            and actual.__globals__ is _NAMESPACE, 'v2_exact_cloned_code')
    for name in ('_global_uses', '_module_path', '_expand_module', '_namespace', '_binding', 'check'):
        original.require(getattr(DependencySeal, name) is getattr(original.DependencySeal, name), 'v2_full_dependency_walk')
    for name in ('_check', '_inventory', '_call_identity', 'bind_private_calls', 'close'):
        original.require(getattr(RequestStaticProof, name) is getattr(original.RequestStaticProof, name), 'v2_original_dynamic_binding')
    return {'schema': VERSION, 'static_float_encoding': 'struct.pack(>d), exact64bits',
        'dependency_walk_or_class_namespace_removed': False,
        'same_proof_JSON_finite_guard': _NAMESPACE['_json_tree'] is original._json_tree,
        'original_runtime_identity_budget_loaded_checks': True,
        'exception_identity_preserved_with_deepest_dependency_note': True,
        'no_model_or_public_input_nonfinite_permission': True,
        'real_dependency_domain_validated': False, 'native_authority': False}
