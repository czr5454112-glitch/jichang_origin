"""Exact canonical stdlib future-feature support; no general instance cache.

The v2 failed dependency remains evidence. This version supports only the
canonical ``__future__.annotations`` object, with its pinned source definition,
complete class/method definition, instance fields and live binding relations.
All other dependencies use the original walk with the v2 float-bit atom. This
is a closed serial source experiment, not arbitrary reflection protection.
"""
from __future__ import annotations

import __future__ as _future
import builtins
import hashlib
from pathlib import Path
from types import BuiltinFunctionType, CodeType, FunctionType, GetSetDescriptorType, ModuleType

from . import live_obligation_bound_source_proof as original
from . import live_obligation_bound_source_proof_v2 as previous

VERSION = 'g31.request_owned_static_source_proof.v3'
FEATURE_SOURCE_SHA256 = 'bf11d13b6c9b2b8706be425addf399965738622bb4cc553217be16399c51d51a'
_FEATURE_MODULE = _future
_FEATURE_CLASS = _future._Feature
_FEATURE_SINGLETON = _future.annotations
_FEATURE_PATH = Path(_future.__file__).resolve()
_CLASS_KEYS = ('__module__', '__init__', 'getOptionalRelease',
               'getMandatoryRelease', '__repr__', '__dict__', '__weakref__', '__doc__')
_FIELD_KEYS = ('optional', 'mandatory', 'compiler_flag')
_OPTIONAL = (3, 7, 0, 'beta', 1)
_FLAG = 0x1000000
_METHODS = ('__init__', 'getOptionalRelease', 'getMandatoryRelease', '__repr__')
_BUILTIN_REPR = builtins.repr
require = original.require
_atom = previous._atom


def _exact_tree(left, right):
    """Only builtin declaration metadata; no user equality or repr hooks."""
    if type(left) is not type(right):
        return False
    if type(left) in (type(None), bool, int, str, bytes):
        return left == right
    if type(left) is tuple:
        return len(left) == len(right) and all(_exact_tree(a, b) for a, b in zip(left, right, strict=True))
    if type(left) is dict:
        return (all(type(k) is str for k in left) and all(type(k) is str for k in right)
                and tuple(left) == tuple(right) and all(_exact_tree(left[k], right[k]) for k in left))
    return False


def _reference_namespace(path, digest):
    """Compile the pinned source in a fresh namespace, never live globals.

    The original file path is the compile filename and original source lines
    are retained. Whole code objects (including filename/firstline/linetable,
    constants, nested code and exception table) are compared, not co_code only.
    Nothing is installed in sys.modules or substituted into the live stdlib.
    """
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == digest, 'v3_stdlib_source_bytes')
    namespace = {'__builtins__': builtins.__dict__, '__name__': '__future__', '__file__': str(path)}
    exec(compile(raw, str(path), 'exec', dont_inherit=True, optimize=0), namespace)
    return namespace


def _code_signature(code):
    """Every Python3.11 code-constructor field, with exact nested constants.

    This avoids marshal's object-reference/interning representation while
    retaining filename, firstline, line table and exception table explicitly.
    """
    require(type(code) is CodeType, 'v3_feature_code_type')
    def constant(value):
        if type(value) is CodeType:
            return ('code', _code_signature(value))
        if type(value) is tuple:
            return ('tuple', tuple(constant(x) for x in value))
        atom = _atom(value)
        require(atom is not None, 'v3_feature_code_constant')
        return ('atom', atom)
    return (code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount,
        code.co_nlocals, code.co_stacksize, code.co_flags, code.co_code,
        tuple(constant(x) for x in code.co_consts), code.co_names, code.co_varnames,
        code.co_filename, code.co_name, code.co_qualname, code.co_firstlineno,
        code.co_linetable, code.co_exceptiontable, code.co_freevars, code.co_cellvars)


def _compare_method(actual, reference, namespace, path):
    require(type(actual) is FunctionType and type(reference) is FunctionType, 'v3_feature_method_type')
    # Explicit path/line checks accompany all code-constructor fields.
    require(actual.__code__.co_filename == reference.__code__.co_filename == str(path)
            and actual.__code__.co_firstlineno == reference.__code__.co_firstlineno
            and _code_signature(actual.__code__) == _code_signature(reference.__code__), 'v3_feature_full_method_code')
    require(actual.__globals__ is namespace and actual.__builtins__ is builtins.__dict__
            and actual.__closure__ is reference.__closure__ is None, 'v3_feature_method_bindings')
    for name in ('__defaults__', '__kwdefaults__', '__annotations__', '__dict__',
                 '__name__', '__qualname__', '__module__', '__doc__'):
        require(_exact_tree(getattr(actual, name), getattr(reference, name)), 'v3_feature_method_metadata:' + name)


class _FeatureAuthority:
    """One cold reference compilation for the encountered canonical feature."""
    def __init__(self, value):
        module, cls, singleton, path = _FEATURE_MODULE, _FEATURE_CLASS, _FEATURE_SINGLETON, _FEATURE_PATH
        require(type(module) is ModuleType and type(module.__name__) is str and module.__name__ == '__future__'
                and type(module.__file__) is str and Path(module.__file__).resolve() == path, 'v3_feature_module')
        namespace = vars(module)
        require(all(type(k) is str for k in namespace), 'v3_feature_namespace_keys')
        require(namespace.get('_Feature') is cls and namespace.get('annotations') is singleton
                and value is singleton and type(value) is cls and type(cls) is type, 'v3_feature_canonical_singleton')
        reference = _reference_namespace(path, FEATURE_SOURCE_SHA256)
        reference_cls = reference['_Feature']
        # No pre-cold global can shadow a builtin used by the verified methods.
        # Import metadata differs legitimately from a fresh exec namespace.
        require(tuple(k for k in namespace if not k.startswith('__'))
                == tuple(k for k in reference if not k.startswith('__'))
                and namespace.get('__builtins__') is builtins.__dict__, 'v3_feature_stdlib_namespace')
        require(builtins.repr is _BUILTIN_REPR and type(_BUILTIN_REPR) is BuiltinFunctionType
                and _BUILTIN_REPR.__module__ == 'builtins' and _BUILTIN_REPR.__name__ == 'repr',
                'v3_feature_builtin_repr_binding')
        require(_exact_tree(cls.__name__, reference_cls.__name__) and cls.__name__ == '_Feature'
                and _exact_tree(cls.__qualname__, reference_cls.__qualname__) and cls.__qualname__ == '_Feature'
                and _exact_tree(cls.__module__, reference_cls.__module__) and cls.__module__ == '__future__'
                and len(cls.__bases__) == 1 and cls.__bases__[0] is object
                and len(cls.__mro__) == 2 and cls.__mro__[0] is cls and cls.__mro__[1] is object,
                'v3_feature_class_identity')
        class_namespace, reference_class = vars(cls), vars(reference_cls)
        require(tuple(class_namespace) == tuple(reference_class) == _CLASS_KEYS, 'v3_feature_complete_class_namespace')
        for name in _CLASS_KEYS:
            actual, expected = class_namespace[name], reference_class[name]
            if name in _METHODS:
                _compare_method(actual, expected, namespace, path)
            elif name in ('__dict__', '__weakref__'):
                require(type(actual) is type(expected) is GetSetDescriptorType
                        and actual.__objclass__ is cls and actual.__name__ == expected.__name__ == name
                        and actual.__doc__ == expected.__doc__, 'v3_feature_descriptor:' + name)
            else:
                require(_exact_tree(actual, expected), 'v3_feature_class_metadata:' + name)
        self.module, self.namespace, self.cls, self.value, self.path = module, namespace, cls, value, path
        self.fields = object.__getattribute__(value, '__dict__')
        self.check()

    def check(self):
        require(_FEATURE_MODULE is self.module and _FEATURE_CLASS is self.cls
                and _FEATURE_SINGLETON is self.value and _FEATURE_PATH == self.path,
                'v3_feature_authority_binding_changed')
        require(type(self.module) is ModuleType and type(self.module.__name__) is str and self.module.__name__ == '__future__'
                and vars(self.module) is self.namespace
                and type(self.module.__file__) is str and Path(self.module.__file__).resolve() == self.path
                and self.namespace.get('_Feature') is self.cls
                and self.namespace.get('annotations') is self.value,
                'v3_feature_canonical_slot_changed')
        require(type(self.value) is self.cls and object.__getattribute__(self.value, '__dict__') is self.fields,
                'v3_feature_instance_type_or_namespace_changed')
        require(type(self.fields) is dict and tuple(self.fields) == _FIELD_KEYS
                and _exact_tree(self.fields['optional'], _OPTIONAL)
                and self.fields['mandatory'] is None
                and type(self.fields['compiler_flag']) is int and self.fields['compiler_flag'] == _FLAG,
                'v3_feature_instance_fields')
        require(hashlib.sha256(self.path.read_bytes()).hexdigest() == FEATURE_SOURCE_SHA256,
                'v3_stdlib_source_bytes')


_NAMESPACE = {**vars(original), '_atom': _atom, 'VERSION': VERSION}
_visit_exact = previous._clone(original.DependencySeal._visit, _NAMESPACE)


class DependencySeal(original.DependencySeal):
    _same = staticmethod(previous._same_exact)

    def __init__(self, roots, *, project_prefixes):
        self._features = []
        original.DependencySeal.__init__(self, roots, project_prefixes=project_prefixes)

    def _visit(self, value, label):
        try:
            if value is _FEATURE_SINGLETON or type(value) is _FEATURE_CLASS:
                # An identical-looking newly allocated _Feature is rejected.
                # Repeated aliases of the canonical object share one check.
                if id(value) in self._seen:
                    return
                authority = _FeatureAuthority(value)
                self._seen.add(id(value))
                self._features.append(authority)
                cls = authority.cls
                self._binding(authority.namespace, '_Feature', cls, label + ':canonical_class')
                self._binding(authority.namespace, 'annotations', value, label + ':canonical_singleton')
                self._namespace(authority.namespace, label + ':stdlib_namespace')
                self._records.append(('class', cls, cls.__mro__, cls.__bases__, label + ':class'))
                self._namespace(vars(cls), label + ':complete_class_namespace')
                for name, item in tuple(vars(cls).items()):
                    self._visit(item, label + ':class:' + name)
                    if name in _METHODS:
                        # Unlike a general external class, this explicitly
                        # supported class also seals each referenced global
                        # builtin slot (currently repr) using the old walker.
                        self._global_uses(item, item.__code__, label + ':method_globals:' + name)
                self._visit(authority.fields, label + ':complete_instance_namespace')
                return
            return _visit_exact(self, value, label)
        except BaseException as error:
            prefix = 'bound_source_proof_v3 dependency_label='
            if not any(type(note) is str and note.startswith(prefix) for note in getattr(error, '__notes__', ())):
                error.add_note(prefix + label)
            raise

    def check(self):
        for feature in self._features:
            feature.check()
        # The complete original record checker remains unchanged.
        return original.DependencySeal.check(self)


_NAMESPACE['DependencySeal'] = DependencySeal


class RequestStaticProof(original.RequestStaticProof):
    __init__ = previous._clone(original.RequestStaticProof.__init__, _NAMESPACE)
    description = previous._clone(original.RequestStaticProof.description, _NAMESPACE)


_NAMESPACE['RequestStaticProof'] = RequestStaticProof
bind_declared = previous._clone(original.bind_declared, _NAMESPACE)


def source_proof():
    changed = {'_atom': _atom, 'VERSION': VERSION, 'DependencySeal': DependencySeal,
               'RequestStaticProof': RequestStaticProof}
    require(set(_NAMESPACE) == set(vars(original))
            and all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in changed)
            and all(_NAMESPACE[k] is v for k, v in changed.items()), 'v3_complete_private_globals')
    for actual, prior in ((_visit_exact, original.DependencySeal._visit),
                          (RequestStaticProof.__init__, original.RequestStaticProof.__init__),
                          (RequestStaticProof.description, original.RequestStaticProof.description),
                          (bind_declared, original.bind_declared)):
        require(actual.__code__ is prior.__code__ and actual.__defaults__ is prior.__defaults__
                and actual.__kwdefaults__ is prior.__kwdefaults__ and actual.__closure__ is prior.__closure__
                and actual.__globals__ is _NAMESPACE, 'v3_exact_cloned_code')
    for name in ('_global_uses', '_module_path', '_expand_module', '_namespace', '_binding'):
        require(getattr(DependencySeal, name) is getattr(original.DependencySeal, name), 'v3_full_dependency_walk')
    for name in ('_check', '_inventory', '_call_identity', 'bind_private_calls', 'close'):
        require(getattr(RequestStaticProof, name) is getattr(original.RequestStaticProof, name), 'v3_original_dynamic_binding')
    require(_atom is previous._atom and DependencySeal._same is previous._same_exact
            and _NAMESPACE['_json_tree'] is original._json_tree, 'v3_unchanged_float_and_JSON_guards')
    require(_FEATURE_MODULE is _future and _FEATURE_CLASS is _future._Feature
            and _FEATURE_SINGLETON is _future.annotations
            and _FEATURE_PATH == Path(_future.__file__).resolve(), 'v3_current_stdlib_bindings')
    return {'schema': VERSION, 'supported_instance': 'exact canonical __future__.annotations only',
        'stdlib_source': {'path': str(_FEATURE_PATH), 'sha256': FEATURE_SOURCE_SHA256},
        'cold_reference': 'pinned whole source, fresh globals, full method code including filename and firstline',
        'whole_original_dependency_walk_and_record_checker_retained': True,
        'complete_feature_class_instance_and_live_slots_checked': True,
        'per_use_stdlib_file_bytes_checked': True,
        'v2_exact_float64bits_and_finite_JSON_unchanged': True,
        'original_runtime_identity_budget_loaded_checks': True,
        'no_model_or_public_input_permission_change': True,
        'real_dependency_domain_validated': False, 'native_authority': False}
