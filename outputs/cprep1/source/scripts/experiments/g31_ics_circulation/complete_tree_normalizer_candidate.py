"""Explicitly loaded data-only C prototype, never installed in a campaign.

An uncertain marker/key returns NotImplemented before supplied-data hooks;
only then is the original normalizer called once. No exception-catching retry.
All copy/validation/fallback/startup costs belong to the caller's accounting.
"""
from __future__ import annotations
import hashlib
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
from types import BuiltinFunctionType, ModuleType
from . import initial_owner_route_json_v3 as original

MODULE = '_g31_complete_tree_normalizer'
SCHEMA = 'g31.complete_tree_normalizer.candidate.v1'
_ORIGINAL = original.normalize
_CODE = _ORIGINAL.__code__


def require(ok, reason):
    if not ok: raise ValueError('tree_normalizer_candidate:'+reason)


def source_identity():
    return {str(Path(module.__file__).resolve()): hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for module in (original, original.wire)}


class Candidate:
    """One verified extension instance; no request/result cache or global patch."""
    def __init__(self, module, source_sha256):
        require(type(module) is ModuleType and module.__name__ == MODULE and
            isinstance(module.__spec__.loader, importlib.machinery.ExtensionFileLoader), 'actual_extension_required')
        require(source_identity() == source_sha256, 'source_changed')
        require(type(module.try_normalize) is BuiltinFunctionType and module.try_normalize.__self__ is module and
            type(module.contract) is BuiltinFunctionType and module.contract.__self__ is module, 'builtin_entry_required')
        expected = {'schema': SCHEMA, 'max_depth': 64, 'max_nodes': 2000000, 'key_scan_limit': 2000000,
                    'headers_python': '3.11.9', 'native_simulation_authority': False}
        require(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 11, 9) and
            module.contract() == expected, 'ABI_or_domain')
        self.module = module
        self._try = module.try_normalize
        self.source_sha256 = dict(source_sha256)

    def normalize(self, value):
        require(original.normalize is _ORIGINAL and _ORIGINAL.__code__ is _CODE and
            original.wire.MAX_DEPTH == 64 and original.wire.MAX_ARTIFACT_NODES == 2000000 and
            self.module.try_normalize is self._try, 'bound_implementation_changed')
        result = self._try(value)
        return _ORIGINAL(value) if result is NotImplemented else result


def load_candidate(binary, expected_sha256, source_sha256):
    """Call only after an independently reviewed build; no build or import on module load."""
    path = Path(binary).resolve()
    require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256,
            'binary_identity')
    require(MODULE not in sys.modules, 'extension_already_loaded')
    spec = importlib.util.spec_from_file_location(MODULE, path)
    require(spec is not None and isinstance(spec.loader, importlib.machinery.ExtensionFileLoader),
            'extension_path')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return Candidate(module, source_sha256)
