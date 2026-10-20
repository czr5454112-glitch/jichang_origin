"""Explicit data-only C typed writer prototype; never auto-loaded or installed.

Only NotImplemented permits one original call. Exact representation checks do
not authenticate captures. Stable inputs and a closed process implementation are
required; allocation/interrupt timing is not claimed equivalent to Python.
"""
from __future__ import annotations
import ast
import builtins
import hashlib
import importlib.machinery
import importlib.util
import inspect
from pathlib import Path
import struct
import sys
from types import BuiltinFunctionType, FunctionType, ModuleType, SimpleNamespace

from . import planning_capture_v2_digest as original

MODULE = '_g31_planning_v2_typed_encoder'
SCHEMA = 'g31.planning_v2.typed_encoder.candidate.v1'
WRITER_SHA = '01fc49cbded5ba70851f1294fce9f5aaa06b66e82bfb5b9862740c310faf9fd5'
_ORIGINAL, _LOCAL = original.capture_digest_v2, original._write_local_capture
_CODE, _LOCAL_CODE = _ORIGINAL.__code__, _LOCAL.__code__
_GLOBALS = dict(_ORIGINAL.__globals__)
_PACK, _SHA = struct.pack, hashlib.sha256
_LEN, _BYTEARRAY = builtins.len, builtins.bytearray


def require(ok, reason):
    if not ok: raise ValueError('typed_v2_candidate:' + reason)


class _BufferResult:
    def __init__(self, data): self.data = data
    def hexdigest(self): return self.data


_BUFFER = FunctionType(_CODE, {**_GLOBALS, 'hashlib': SimpleNamespace(sha256=_BufferResult)},
    _ORIGINAL.__name__, _ORIGINAL.__defaults__, _ORIGINAL.__closure__)
_BUFFER.__kwdefaults__ = _ORIGINAL.__kwdefaults__


def implementation_identity():
    require(original.capture_digest_v2 is _ORIGINAL and original._write_local_capture is _LOCAL
        and _ORIGINAL.__code__ is _CODE and _LOCAL.__code__ is _LOCAL_CODE,
        'original_functions_changed')
    require(set(_ORIGINAL.__globals__) == set(_GLOBALS) and
        all(_ORIGINAL.__globals__[key] is value for key, value in _GLOBALS.items()),
        'original_globals_changed')
    require(original.struct is struct and original.hashlib is hashlib and
        struct.pack is _PACK and hashlib.sha256 is _SHA and
        builtins.len is _LEN and builtins.bytearray is _BYTEARRAY,
        'original_primitives_changed')


def source_proof():
    implementation_identity()
    path = Path(original.__file__).resolve()
    require(_SHA(path.read_bytes()).hexdigest() == WRITER_SHA, 'original_source_changed')
    return {'schema': SCHEMA, 'original_source': str(path), 'original_source_sha256': WRITER_SHA,
        'original_outer_AST_sha256': _SHA(ast.dump(ast.parse(inspect.getsource(_ORIGINAL)),
            include_attributes=False).encode()).hexdigest(),
        'original_local_AST_sha256': _SHA(ast.dump(ast.parse(inspect.getsource(_LOCAL)),
            include_attributes=False).encode()).hexdigest(),
        'oracle_outer_code_identity': _BUFFER.__code__ is _CODE,
        'oracle_local_identity': _BUFFER.__globals__['_write_local_capture'] is _LOCAL,
        'oracle_changed_global_only': 'hashlib', 'native_authority': False,
        'resource_exception_equivalence': False,
        'C_handwritten_field_order_requires_source_review_and_full_byte_tests': True,
        'no_extension_loaded_by_this_function': True}


def reference_bytes_v2(body):
    """Diagnostic oracle: original exact writer, only final SHA replaced."""
    implementation_identity()
    return bytes(_BUFFER(body))


def _digest(try_bytes, body):
    """Private wiring seam for failure tests; no authority or fake C acceptance."""
    result = try_bytes(body)
    if result is NotImplemented: return _ORIGINAL(body)
    require(type(result) is bytes, 'unexpected_extension_result')
    return _SHA(result).hexdigest()


def _bytes(try_bytes, body):
    result = try_bytes(body)
    if result is NotImplemented: return reference_bytes_v2(body)
    require(type(result) is bytes, 'unexpected_extension_result')
    return result


class Candidate:
    def __init__(self, module, expected_source):
        require(type(module) is ModuleType and module.__name__ == MODULE and
            isinstance(module.__spec__.loader, importlib.machinery.ExtensionFileLoader),
            'actual_extension_required')
        require(type(module.try_typed_bytes) is BuiltinFunctionType and
            module.try_typed_bytes.__self__ is module and
            type(module.contract) is BuiltinFunctionType and module.contract.__self__ is module,
            'builtin_entries_required')
        require(source_proof() == expected_source, 'source_proof_changed')
        require(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 11, 9)
            and module.contract() == {'schema': SCHEMA, 'headers_python': '3.11.9',
                'original_writer_sha256': WRITER_SHA, 'uint64_bits': 64,
                'stable_input_required': True, 'native_simulation_authority': False},
            'ABI_or_domain')
        self.module, self._try, self._contract = module, module.try_typed_bytes, module.contract

    def _verify(self):
        implementation_identity()
        require(self.module.try_typed_bytes is self._try and self.module.contract is self._contract,
                'extension_entry_changed')

    def capture_digest_v2(self, body):
        self._verify()
        return _digest(self._try, body)

    def typed_bytes_v2(self, body):
        self._verify()
        return _bytes(self._try, body)


def load_candidate(binary, expected_sha256, expected_source):
    """Requires a separately accepted build. This function never builds anything."""
    path = Path(binary).resolve()
    require(path.is_file() and _SHA(path.read_bytes()).hexdigest() == expected_sha256,
            'binary_identity')
    require(MODULE not in sys.modules, 'extension_already_loaded')
    spec = importlib.util.spec_from_file_location(MODULE, path)
    require(spec is not None and isinstance(spec.loader, importlib.machinery.ExtensionFileLoader),
            'extension_path')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return Candidate(module, expected_source)
