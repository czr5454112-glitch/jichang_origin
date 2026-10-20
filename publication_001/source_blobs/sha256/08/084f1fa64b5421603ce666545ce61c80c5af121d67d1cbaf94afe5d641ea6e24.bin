"""Explicit process-local code reuse for the supplied-data projection only.

The factory retains code, source identities and static implementation bindings.
It retains no request snapshot, action result or mutable projection. Each new
request rechecks source identity and executes the complete already-reviewed
RequestContext constructor, substituting only its code-generation function.
"""
from __future__ import annotations

import ast
import copy
import hashlib
from pathlib import Path
import sys
from types import FunctionType, ModuleType

from . import public_preference_request_context as base

ROOT = Path(__file__).resolve().parents[3]
EXPECTED_CONTEXT = '9c64e97e1e954a3639696ba5ca1f72f9f85e07032121f389b7e34507dfa71c3c'
VERSION = 'supplied_preference_static_implementation_v1'


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def implementation_sources():
    """Resolve repository imports without importing or executing extra modules."""
    pending, found = [Path(__file__).resolve(), Path(base.__file__).resolve()], set()
    def add(target):
        for path in (target.with_suffix('.py'), target / '__init__.py'):
            if path.is_file() and path.resolve().is_relative_to(ROOT):
                pending.append(path)
                for parent in path.parents:
                    if parent == ROOT:
                        break
                    if (parent / '__init__.py').is_file():
                        pending.append(parent / '__init__.py')
    while pending:
        path = pending.pop().resolve()
        if path in found:
            continue
        found.add(path)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            if isinstance(node, ast.ImportFrom):
                for parent in ([path.parent] if node.level else [ROOT, ROOT / 'src']):
                    for _ in range(max(0, node.level - 1)):
                        parent = parent.parent
                    if node.module:
                        parent = parent.joinpath(*node.module.split('.'))
                        add(parent)
                    for alias in node.names:
                        if alias.name != '*':
                            add(parent / alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for parent in (ROOT, ROOT / 'src'):
                        add(parent.joinpath(*alias.name.split('.')))
    return tuple(sorted(found))


def _implementation_modules(paths):
    result = []
    root_text = str(ROOT).lower()
    for name, module in sorted(tuple(sys.modules.items())):
        filename = getattr(module, '__file__', None)
        if (filename and str(filename).lower().startswith(root_text)
                and Path(filename).resolve() in paths and name != __name__):
            result.append((name, module))
    return tuple(result)


def _constant_identity(value, active=None):
    if type(value) in (str, int, float, bool, type(None)):
        return (type(value).__name__, repr(value))
    if type(value) not in (dict, list, tuple, set, frozenset):
        return None
    active = set() if active is None else active
    if id(value) in active:
        return None
    active.add(id(value))
    if type(value) is dict:
        rows = [(_constant_identity(key, active), _constant_identity(item, active)) for key, item in value.items()]
        valid = all(key is not None and item is not None for key, item in rows)
    else:
        rows = [_constant_identity(item, active) for item in value]
        valid = all(row is not None for row in rows)
        if valid and type(value) in (set, frozenset):
            rows.sort(key=repr)
    active.remove(id(value))
    return (type(value).__name__, tuple(rows)) if valid else None


def _implementation_bindings(modules):
    """Reject changed live functions/methods, beyond merely unchanged .py bytes.

This is not a security boundary against arbitrary code in the same process.
Request data are never used to form this implementation-only inventory.
"""
    result = []
    for name, module in modules:
        if sys.modules.get(name) is not module:
            raise ValueError('static_context:module_replaced')
        for key, value in sorted(vars(module).items()):
            if key.startswith('__'):
                continue
            if isinstance(value, FunctionType):
                result.append((name, key, value, value.__code__,
                    _constant_identity(value.__defaults__), _constant_identity(value.__kwdefaults__)))
            elif isinstance(value, ModuleType):
                result.append((name, key, value))
            elif isinstance(value, type) and value.__module__ == name:
                result.append((name, key, value))
                for member, method in sorted(vars(value).items()):
                    if isinstance(method, (classmethod, staticmethod)):
                        method = method.__func__
                    if isinstance(method, FunctionType):
                        result.append((name, key, member, method, method.__code__,
                            _constant_identity(method.__defaults__), _constant_identity(method.__kwdefaults__)))
            else:
                constant = _constant_identity(value)
                if constant is not None:
                    result.append((name, key, constant))
    return tuple(result)


class StaticImplementation:
    """Build once explicitly; cold construction must be charged where required.

Warm requests still perform all source reads and input-dependent validation.
Keeping this code-only object alive is an experimental initialized-host choice,
not permission to omit its cold cost from an original business request.
"""
    __slots__ = ('__pins', '__modules', '__bindings', '__compiled', '__context_type')

    def __init__(self):
        if _sha(base.__file__) != EXPECTED_CONTEXT:
            raise ValueError('static_context:unreviewed_context_revision')
        paths = implementation_sources()
        self.__pins = {path: _sha(path) for path in paths}
        self.__modules = _implementation_modules(set(paths))
        self.__bindings = _implementation_bindings(self.__modules)
        self.__compiled = base.compile_guards()
        source_init = base.RequestContext.__init__
        private_init = FunctionType(source_init.__code__, {
            **source_init.__globals__, 'compile_guards': self.__checked_compiler},
            source_init.__name__, source_init.__defaults__, source_init.__closure__)
        private_init.__kwdefaults__ = copy.deepcopy(source_init.__kwdefaults__)
        self.__context_type = type('_StaticCodeRequestContext', (base.RequestContext,), {'__init__': private_init})
        self.verify_implementation()

    def verify_implementation(self):
        if any(_sha(path) != digest for path, digest in self.__pins.items()):
            raise ValueError('static_context:source_changed')
        if _implementation_bindings(self.__modules) != self.__bindings:
            raise ValueError('static_context:live_implementation_changed')

    def __checked_compiler(self):
        self.verify_implementation()
        validate, action_check, proof = self.__compiled
        return validate, action_check, copy.deepcopy(proof)

    def context(self, bundle):
        return self.__context_type(bundle)

    def source_pins(self):
        return {str(path): digest for path, digest in self.__pins.items()}

    def describe(self):
        return {'version': VERSION, 'persistent_state': 'code_and_implementation_identity_only',
            'constructor_code_identical': self.__context_type.__init__.__code__ is base.RequestContext.__init__.__code__,
            'constructor_global_substitution': ['compile_guards'],
            'every_request_source_check': True, 'every_request_dynamic_guards': True,
            'cross_request_snapshot_or_result_cache': False, 'native_authority': False,
            'complete_100ms_certified': False}
