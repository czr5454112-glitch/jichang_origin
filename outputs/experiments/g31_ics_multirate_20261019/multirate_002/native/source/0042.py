"""Request-owned static-proof reuse; no model/observation/decision cache.

Draft, not performance accepted. A cold bind calls the original proof exactly
once. Its existing loaded checks and final deepcopy execute on EVERY use via
the original code in a private globals dictionary. Only its static inventory
call is replaced. Dependency checks are deliberately conservative and reject
unsupported static objects. This is closed serial code ownership, not a
security boundary against arbitrary reflection or concurrent mutation.
"""
from __future__ import annotations

import copy
import dis
import hashlib
import math
import os
from pathlib import Path
import threading
from types import (BuiltinFunctionType, CodeType, FunctionType, MappingProxyType,
                   MemberDescriptorType, MethodDescriptorType, ModuleType,
                   GetSetDescriptorType, WrapperDescriptorType)

VERSION = 'g31.request_owned_static_source_proof.v1'
_EMPTY_CELL = object()
_ISSUER = object()


def require(ok, reason):
    if not ok:
        raise ValueError('bound_source_proof:' + reason)


def _atom(value):
    kind = type(value)
    if kind in (type(None), bool, int, str, bytes):
        return kind, value
    if kind is float:
        require(math.isfinite(value), 'nonfinite_static_value')
        return kind, value.hex()
    if value is Ellipsis or value is NotImplemented:
        return kind, id(value)
    return None


def _cell(cell):
    try:
        return cell.cell_contents
    except ValueError:
        return _EMPTY_CELL


def _json_tree(value):
    """No tuple normalization, custom copying hooks or fabricated authority."""
    if type(value) in (type(None), bool, int, str):
        return
    if type(value) is float:
        require(math.isfinite(value), 'proof_nonfinite')
        return
    if type(value) is list:
        for item in value:
            _json_tree(item)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values():
            _json_tree(item)
        return
    raise ValueError('bound_source_proof:proof_not_builtin_JSON')


class DependencySeal:
    """Cold compiled checks over a declared project dependency graph.

    Function globals retain the complete mapping of binding identities. Only
    LOAD_GLOBAL/LOAD_NAME dependencies (including nested code) are recursively
    traversed. Project module attributes used by a direct bytecode attribute
    chain are followed; an indirectly passed project module is conservatively
    expanded. No sys.modules scan, per-use disassembly, AST or inspect calls.
    External modules/functions are explicit identity/code boundaries; arbitrary
    mutation inside the interpreter/stdlib is outside this closed experiment.
    """
    def __init__(self, roots, *, project_prefixes):
        require(type(roots) is dict and roots and all(type(k) is str for k in roots), 'roots')
        require(type(project_prefixes) is tuple and project_prefixes
                and all(type(x) is str and x for x in project_prefixes), 'project_prefixes')
        self._prefixes = project_prefixes
        self._records = []
        self._seen = set()
        self._namespaces = set()
        self._expanded_modules = set()
        self._roots = dict(roots)
        for name, value in roots.items():
            self._visit(value, 'root:' + name)
        self.check()

    def _project(self, name):
        return type(name) is str and any(name == p or name.startswith(p + '.') for p in self._prefixes)

    def _binding(self, namespace, name, value, label):
        self._records.append(('binding', namespace, name, value, label))

    def _namespace(self, namespace, label):
        require(type(namespace) in (dict, MappingProxyType), 'namespace_type:' + label)
        if id(namespace) in self._namespaces:
            return
        self._namespaces.add(id(namespace))
        self._records.append(('namespace', namespace, tuple(namespace), tuple(namespace.values()), label))

    def _module_path(self, value, instructions, index, label):
        """Follow only literal attribute bytecode; dynamic access expands module."""
        self._visit(value, label)
        cursor = value
        used = False
        for item in instructions[index + 1:]:
            if item.opname not in ('LOAD_ATTR', 'LOAD_METHOD'):
                break
            if type(cursor) is ModuleType:
                namespace = vars(cursor)
                require(item.argval in namespace, 'module_attribute:' + label)
                child = namespace[item.argval]
                self._binding(namespace, item.argval, child, label + '.' + item.argval)
                self._visit(child, label + '.' + item.argval)
                cursor = child
                used = True
            else:
                # The class seal separately includes its entire MRO namespace.
                break
        if not used and type(value) is ModuleType and self._project(value.__name__):
            self._expand_module(value, label)

    def _expand_module(self, module, label):
        if id(module) in self._expanded_modules:
            return
        self._expanded_modules.add(id(module))
        namespace = vars(module)
        self._namespace(namespace, label)
        for name, value in tuple(namespace.items()):
            if name.startswith('__') or type(value) is ModuleType:
                continue
            self._visit(value, label + '.' + name)

    def _global_uses(self, function, code, label):
        instructions = tuple(dis.get_instructions(code))
        for index, item in enumerate(instructions):
            if item.opname not in ('LOAD_GLOBAL', 'LOAD_NAME'):
                continue
            name = item.argval
            namespace = function.__globals__
            if name not in namespace:
                namespace = function.__builtins__
            require(name in namespace, 'missing_global:' + label + ':' + name)
            value = namespace[name]
            self._binding(namespace, name, value, label + ':' + name)
            if type(value) is ModuleType:
                self._module_path(value, instructions, index, label + ':' + name)
            else:
                self._visit(value, label + ':' + name)
        for item in code.co_consts:
            if type(item) is CodeType:
                self._global_uses(function, item, label + ':nested')

    def _visit(self, value, label):
        if _atom(value) is not None or value is _EMPTY_CELL:
            return
        if id(value) in self._seen:
            return
        self._seen.add(id(value))
        kind = type(value)
        if kind in (dict, MappingProxyType):
            self._namespace(value, label)
            for key, item in tuple(value.items()):
                self._visit(key, label + ':key')
                self._visit(item, label + ':value')
        elif kind in (list, tuple):
            self._records.append(('sequence', value, tuple(value), label))
            for item in value:
                self._visit(item, label + ':item')
        elif kind in (set, frozenset):
            self._records.append(('set', value, frozenset(id(x) for x in value), label))
            for item in value:
                self._visit(item, label + ':member')
        elif kind is bytearray:
            self._records.append(('bytes', value, bytes(value), label))
        elif kind is FunctionType:
            self._records.append(('function', value, value.__code__, value.__defaults__,
                value.__kwdefaults__, value.__closure__, value.__globals__, value.__builtins__, label))
            self._namespace(value.__globals__, label + ':globals')
            for item in (value.__defaults__, value.__kwdefaults__, value.__annotations__, value.__dict__):
                self._visit(item, label + ':metadata')
            for cell in value.__closure__ or ():
                contents = _cell(cell)
                self._records.append(('cell', cell, contents, label))
                self._visit(contents, label + ':cell')
            if self._project(value.__module__):
                self._global_uses(value, value.__code__, label)
        elif kind is ModuleType:
            # Referenced attribute slots are added by _module_path. Merely
            # naming a module is not permission to traverse all imported ones.
            self._records.append(('module', value, value.__dict__, value.__name__, label))
        elif isinstance(value, type):
            if not self._project(value.__module__):
                return  # fixed external type boundary
            self._records.append(('class', value, value.__mro__, value.__bases__, label))
            for cls in value.__mro__:
                if not self._project(cls.__module__):
                    continue
                namespace = vars(cls)
                self._namespace(namespace, label + ':MRO:' + cls.__qualname__)
                for name, item in tuple(namespace.items()):
                    if name in ('__dict__', '__weakref__'):
                        continue
                    self._visit(item, label + '.' + name)
        elif kind in (staticmethod, classmethod):
            self._records.append(('descriptor', value, value.__func__, label))
            self._visit(value.__func__, label + ':function')
        elif kind is property:
            self._records.append(('property', value, value.fget, value.fset, value.fdel, label))
            for item in (value.fget, value.fset, value.fdel):
                self._visit(item, label + ':accessor')
        elif kind is CodeType:
            # Code objects are immutable; all references to them are retained.
            return
        elif kind in (BuiltinFunctionType, MethodDescriptorType, MemberDescriptorType,
                      GetSetDescriptorType, WrapperDescriptorType, object):
            return  # identity is checked at its owning slot
        elif isinstance(value, Path):
            self._records.append(('path', value, str(value), label))
        else:
            raise ValueError('bound_source_proof:unsupported_static_object:' + label + ':' + kind.__name__)

    @staticmethod
    def _same(left, right):
        a, b = _atom(left), _atom(right)
        return a == b if a is not None and b is not None else left is right

    def check(self):
        for row in self._records:
            tag, value, *rest = row
            label = rest[-1]
            if tag == 'binding':
                name, expected, _ = rest
                ok = name in value and self._same(value[name], expected)
            elif tag == 'namespace':
                keys, items, _ = rest
                current = tuple(value)
                ok = len(current) == len(keys) and all(self._same(a, b) for a, b in zip(current, keys, strict=True))
                ok = ok and all(self._same(value[k], x) for k, x in zip(keys, items, strict=True))
            elif tag == 'sequence':
                items, _ = rest
                ok = len(value) == len(items) and all(self._same(a, b) for a, b in zip(value, items, strict=True))
            elif tag == 'set':
                ok = frozenset(id(x) for x in value) == rest[0]
            elif tag == 'bytes':
                ok = bytes(value) == rest[0]
            elif tag == 'function':
                current = (value.__code__, value.__defaults__, value.__kwdefaults__, value.__closure__, value.__globals__, value.__builtins__)
                ok = all(a is b for a, b in zip(current, rest[:-1], strict=True))
            elif tag == 'cell':
                ok = self._same(_cell(value), rest[0])
            elif tag == 'module':
                ok = value.__dict__ is rest[0] and value.__name__ == rest[1]
            elif tag == 'class':
                ok = value.__mro__ == rest[0] and value.__bases__ == rest[1]
            elif tag == 'descriptor':
                ok = value.__func__ is rest[0]
            elif tag == 'property':
                ok = all(a is b for a, b in zip((value.fget, value.fset, value.fdel), rest[:-1], strict=True))
            elif tag == 'path':
                ok = str(value) == rest[0]
            else:
                raise ValueError('bound_source_proof:unknown_check')
            require(ok, 'dependency_changed:' + label)
        return len(self._records)


class FileSeal:
    """Exact finite proof-read domain; bytes each time, never mtime/stat only."""
    def __init__(self, source_paths):
        require(type(source_paths) is tuple and source_paths, 'source_paths')
        self._paths = tuple(Path(p).resolve(strict=True) for p in source_paths)
        require(len(set(self._paths)) == len(self._paths)
                and all(p.is_file() and p.suffix == '.py' for p in self._paths), 'source_file_domain')
        self._hashes = tuple(hashlib.sha256(p.read_bytes()).hexdigest() for p in self._paths)

    def check(self):
        require(tuple(hashlib.sha256(p.read_bytes()).hexdigest() for p in self._paths) == self._hashes,
                'proof_source_bytes_changed')

    def description(self):
        return {str(p): h for p, h in zip(self._paths, self._hashes, strict=True)}


def _clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


class RequestStaticProof:
    """One active PID/thread/request, explicitly closed; at most65 proof uses.

    Private members are not authenticated native capabilities. The public
    source-bound factory is responsible for the declared dependency roots.
    No capture, initial context, engine, action or predicted output is stored.
    """
    def __init__(self, original, roots, source_paths, project_prefixes, *, issuer):
        require(issuer is _ISSUER and type(original) is FunctionType, 'factory_only')
        require('_source_inventory' in original.__globals__, 'original_inventory_global')
        self._pid, self._thread = os.getpid(), threading.get_ident()
        self._active = True
        self._uses = 0
        self._original = original
        self._files = FileSeal(source_paths)
        self._dependencies = DependencySeal(roots, project_prefixes=project_prefixes)
        # Exactly one original full audit. Any failure aborts construction.
        proof = original()
        _json_tree(proof)
        self._proof = copy.deepcopy(proof)
        self._proof_root = self._proof
        self._proof_seal = DependencySeal({'cached_builtin_proof': self._proof}, project_prefixes=project_prefixes)
        self._dependencies.check()
        self._files.check()
        self._replacement = self._inventory
        self._globals = {**original.__globals__, '_source_inventory': self._replacement}
        self._compiled = _clone(original, self._globals)
        self._private = (self._compiled, self._compiled.__code__, self._compiled.__defaults__,
                         self._compiled.__kwdefaults__, self._compiled.__closure__)
        def checked_proof():
            try:
                require(self._active, 'closed_or_invalidated_request')
                self._call_identity()
                return self._compiled()
            except BaseException:
                # Also revoke when the ORIGINAL loaded check raises before
                # reaching our inventory callback. Preserve that exception.
                self._active = False
                raise
        self.source_proof = checked_proof
        self._checked = (checked_proof, checked_proof.__code__, checked_proof.__closure__)
        self._private_calls = ()

    def bind_private_calls(self, functions):
        """Factory-only setup before any warm use; no replacement after use."""
        require(self._active and self._uses == 0 and not self._private_calls, 'private_calls_already_bound')
        require(type(functions) is tuple and functions and all(type(f) is FunctionType for f in functions),
                'private_call_functions')
        self._private_calls = tuple((f, f.__code__, f.__defaults__, f.__kwdefaults__, f.__closure__,
            f.__globals__, tuple(f.__globals__), tuple(f.__globals__.values())) for f in functions)

    def _call_identity(self):
        require(os.getpid() == self._pid and threading.get_ident() == self._thread, 'process_or_thread_changed')
        require(set(self._globals) == set(self._original.__globals__)
                and all(self._globals[k] is v for k, v in self._original.__globals__.items() if k != '_source_inventory')
                and self._globals['_source_inventory'] is self._replacement, 'private_complete_globals')
        function, code, defaults, kwdefaults, closure = self._private
        require(self._compiled is function and function.__code__ is code and function.__defaults__ is defaults
                and function.__kwdefaults__ is kwdefaults and function.__closure__ is closure
                and function.__globals__ is self._globals, 'private_original_code_binding')
        checked, checked_code, checked_closure = self._checked
        require(self.source_proof is checked and checked.__code__ is checked_code
                and checked.__closure__ is checked_closure and len(checked_closure) == 1
                and checked_closure[0].cell_contents is self, 'checked_wrapper_binding')
        for f, code, defaults, kwdefaults, closure, namespace, keys, values in self._private_calls:
            require(f.__code__ is code and f.__defaults__ is defaults and f.__kwdefaults__ is kwdefaults
                    and f.__closure__ is closure and f.__globals__ is namespace
                    and tuple(namespace) == keys and all(namespace[k] is v for k, v in zip(keys, values, strict=True)),
                    'private_future_call_binding')

    def _check(self):
        require(self._active, 'closed_or_invalidated_request')
        self._call_identity()
        self._dependencies.check()
        require(self._proof is self._proof_root, 'cached_proof_root_changed')
        self._proof_seal.check()
        self._files.check()

    def _inventory(self):
        try:
            self._check()
            require(self._uses < 65, 'declared65_proof_budget')
            self._uses += 1
            # The ORIGINAL source_proof immediately deepcopies this value.
            return self._proof
        except BaseException:
            self._active = False
            raise

    def close(self):
        try:
            self._check()
        finally:
            self._active = False

    def description(self):
        return {'schema': VERSION, 'cold_original_proof_calls': 1, 'proof_uses': self._uses,
            'active': self._active, 'maximum_proof_uses': 65,
            'source_file_sha256': self._files.description(),
            'dependency_check_records': len(self._dependencies._records),
            'original_loaded_checks_each_use': True, 'fresh_original_deepcopy_each_use': True,
            'dynamic_model_guards_cached': False, 'observation_or_context_cache': False,
            'native_authority': False, '100ms_certified': False,
            'scope': 'Closed serial source-owned process; explicit external interpreter/stdlib identity boundary, no arbitrary reflection/concurrent mutation protection.'}


def bind_declared(original, roots, source_paths, *, project_prefixes):
    """Internal factory seam; production must supply its exact closed roots."""
    return RequestStaticProof(original, roots, source_paths, project_prefixes, issuer=_ISSUER)
