"""Explicit accepted004 data-only provider lifecycle for the new campaign.

No C load on import or metadata preparation. Runtime use retains Candidate's
original single Python fallback. Actual direct-C support is not inferred from
normalized output and is deliberately unmeasured in this campaign.
"""
from __future__ import annotations
import ctypes
import importlib.machinery
from pathlib import Path
import sys
import time
from types import BuiltinFunctionType, ModuleType

from . import complete_tree_normalizer_candidate as provider
from . import initial_owner_route_single_capture_owned_codec as binding
from . import run_single_capture_owned_codec_pure as paths

ROOT, OUT = paths.ROOT, paths.OUT
require, sha = paths.require, paths.sha
BUILD = OUT/'c_tree_normalizer_build_004/receipt.json'
BUILD_SHA = 'cc44e186ee143b76bc1993deb3a8521f800650231887caffe300ef57d0777a79'
PAIR = OUT/'complete_root_owned_decode_C_pair_prepare_001/plan.json'
PAIR_SHA = '947f7c33f012f4b4b3248cbbfe1cc037537340c3da89971160ec732d91bae00d'
FUNCTIONAL = OUT/'c_tree_normalizer_functional_001/receipt.json'
FUNCTIONAL_SHA = 'add2eef6ee390eb7c8e97ce94c37095a5041aa17ddc0a4d4b5b85e18c4603dac'


def read(path):
    import json
    return json.loads(Path(path).read_text(encoding='utf8'))


def metadata():
    for path, digest in ((BUILD, BUILD_SHA), (PAIR, PAIR_SHA), (FUNCTIONAL, FUNCTIONAL_SHA)):
        require(sha(path) == digest, 'owned_runtime_reference_changed')
    build, pair, functional = read(BUILD), read(PAIR), read(FUNCTIONAL)
    require(build['status'] == 'build_passed_imports_inspected_unloaded'
        and build['imports_inspected_before_any_extension_load'] is True
        and build['source_changed'] == build['toolchain_changed'] == []
        and build['toolchain_before'] == build['toolchain_after'], 'owned_runtime_build')
    require(functional['status'] == 'functional_passed_saved18_excluded'
        and functional['tests'] == 61 and not functional['bad_tests']
        and not functional['source_changed'] and not functional['toolchain_changed'],
        'owned_runtime_functional')
    require(pair['binary'] == build['binary'] and len(build['toolchain_before']) == 6124,
        'owned_runtime_accepted_binary')
    original = {str(Path(m.__file__).resolve()): pair['source_sha256'][str(Path(m.__file__).resolve())]
        for m in (provider.original, provider.original.wire)}
    return {'schema': 'g31.single_capture.accepted004_provider.v1',
        'references': {str(path): digest for path, digest in
            ((BUILD, BUILD_SHA), (PAIR, PAIR_SHA), (FUNCTIONAL, FUNCTIONAL_SHA))},
        'binary': build['binary'], 'runtime_dependencies': pair['runtime_dependencies'],
        'toolchain_sha256': build['toolchain_before'], 'original_sources': original,
        'provider_sources': build['source_before'],
        'provider_source_archive': {name: str(BUILD.parent/'source'/name) for name in build['source_before']},
        'ABI': 'CPython3.11.9 non-limited ABI; reviewed recursion_remaining usage',
        'actual_direct_C_supported': None, 'actual_fallback_count': None,
        'provider_includes_original_fallback': True,
        'request_preflight_or_instrumentation_added': False}


def verify_files(contract):
    require(contract == metadata(), 'owned_runtime_contract_changed')
    require(sha(contract['binary']['path']) == contract['binary']['sha256'], 'owned_runtime_binary')
    for name, digest in contract['toolchain_sha256'].items():
        require(sha(name) == digest, 'owned_runtime_toolchain:' + name)
    for name, item in contract['runtime_dependencies'].items():
        if 'path' in item: require(sha(item['path']) == item['sha256'], 'owned_runtime_DLL:' + name)
    for name, digest in contract['provider_sources'].items():
        require(sha(ROOT/name) == sha(contract['provider_source_archive'][name]) == digest,
            'owned_runtime_provider_source:' + name)
    for name, digest in contract['original_sources'].items():
        require(sha(name) == digest, 'owned_runtime_original_source')
    return {'binary_sha256': contract['binary']['sha256'], 'toolchain_count': 6124,
        'provider_source_count': len(contract['provider_sources']),
        'original_sources': contract['original_sources'],
        'runtime_file_count': sum('path' in x for x in contract['runtime_dependencies'].values())}


def actual_DLLs(contract):
    # The module handle reports what this process actually loaded. API-set
    # names without a path remain descriptions; ucrtbase is pinned separately.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetModuleHandleW.argtypes = (ctypes.c_wchar_p,)
    kernel.GetModuleHandleW.restype = ctypes.c_void_p
    kernel.GetModuleFileNameW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint)
    kernel.GetModuleFileNameW.restype = ctypes.c_uint
    found = {}
    for name, item in contract['runtime_dependencies'].items():
        if 'path' not in item: continue
        handle = kernel.GetModuleHandleW(name)
        require(bool(handle), 'owned_runtime_DLL_not_loaded:' + name)
        buffer = ctypes.create_unicode_buffer(32768)
        length = kernel.GetModuleFileNameW(handle, buffer, len(buffer))
        require(0 < length < len(buffer), 'owned_runtime_DLL_path')
        path = Path(buffer.value).resolve()
        require(path == Path(item['path']).resolve() and sha(path) == item['sha256'],
            'owned_runtime_actual_DLL_mismatch:' + name)
        found[name] = {'path': str(path), 'sha256': item['sha256']}
    return found


def actual_identity(candidate, contract):
    require(type(candidate) is provider.Candidate, 'owned_runtime_actual_candidate')
    module = candidate.module
    require(type(module) is ModuleType and module.__name__ == provider.MODULE,
        'owned_runtime_actual_module')
    spec = module.__spec__
    require(spec is not None and type(spec.loader) is importlib.machinery.ExtensionFileLoader
        and spec.name == provider.MODULE, 'owned_runtime_actual_spec')
    expected = Path(contract['binary']['path']).resolve()
    paths_found = [Path(value).resolve() for value in
        (module.__file__, spec.origin, spec.loader.path)]
    require(all(path == expected for path in paths_found)
        and sha(expected) == contract['binary']['sha256'], 'owned_runtime_actual_path')
    require(type(module.try_normalize) is BuiltinFunctionType
        and module.try_normalize.__self__ is module and candidate._try is module.try_normalize
        and type(module.contract) is BuiltinFunctionType and module.contract.__self__ is module,
        'owned_runtime_bound_builtin')
    require(candidate.source_sha256 == contract['original_sources']
        and provider.source_identity() == contract['original_sources'], 'owned_runtime_bound_sources')
    expected_contract = {'schema': provider.SCHEMA, 'max_depth': 64, 'max_nodes': 2000000,
        'key_scan_limit': 2000000, 'headers_python': '3.11.9', 'native_simulation_authority': False}
    require(sys.implementation.name == 'cpython' and sys.version_info[:3] == (3, 11, 9)
        and module.contract() == expected_contract, 'owned_runtime_bound_ABI')
    return {'module': provider.MODULE, 'file': str(paths_found[0]), 'spec_origin': str(paths_found[1]),
        'loader_path': str(paths_found[2]), 'loader_type': 'ExtensionFileLoader',
        'binary_sha256': contract['binary']['sha256'], 'contract': expected_contract,
        'actual_DLLs': actual_DLLs(contract), 'source_sha256': dict(candidate.source_sha256)}


class Provider:
    """One explicit worker-lifetime provider; no mutable request/result cache."""
    def __init__(self, contract, output, write):
        self.contract, self.output, self.write = contract, Path(output), write
        self.candidate = self.binding = self.run_branch = None
        self.record = {'schema': 'g31.single_capture.owned_C_lifetime.v1',
            'status': 'unknown_setup', 'setup_started_ns': time.perf_counter_ns(),
            'actual_direct_C_supported': None, 'actual_fallback_count': None,
            'provider_includes_original_fallback': True,
            'request_preflight_or_instrumentation_added': False,
            'extension_unload_claimed': False, 'per_request_cycle_cleanup_claimed': False}
        self.save()

    def save(self): self.write(self.output/'C_provider_lifetime.json', self.record)

    def open(self, schema):
        try:
            self.record['files_entry'] = verify_files(self.contract)
            self.record['load_started_ns'] = time.perf_counter_ns()
            self.candidate = provider.load_candidate(self.contract['binary']['path'],
                self.contract['binary']['sha256'], self.contract['original_sources'])
            self.record['actual_entry'] = actual_identity(self.candidate, self.contract)
            self.binding = binding.bind(self.candidate)
            self.run_branch = binding.private(binding.branch_function(self.binding), {'SCHEMA': schema})
            self.record.update(status='opened', setup_finished_ns=time.perf_counter_ns(),
                binding_proof=binding.binding_proof(self.binding),
                direct_and_scheduler_publication_bound=True)
            self.save()
            return self
        except BaseException as error:
            self.record.update(status='unknown_setup_failure', error_type=type(error).__name__,
                error=str(error), failure_ns=time.perf_counter_ns())
            self.save()
            raise

    def close(self):
        require(self.record['status'] == 'opened', 'owned_runtime_close_state')
        self.record['close_started_ns'] = time.perf_counter_ns()
        try:
            self.record['actual_exit'] = actual_identity(self.candidate, self.contract)
            self.record['files_exit'] = verify_files(self.contract)
            require(self.record['actual_exit'] == self.record['actual_entry']
                and self.record['files_exit'] == self.record['files_entry'], 'owned_runtime_entry_exit')
            self.record.update(status='closed_identity_checked', close_finished_ns=time.perf_counter_ns())
            # Module/class/function cycles may live until process teardown.
            # Retain the references through saved verification; no fake unload.
            self.save()
        except BaseException as error:
            self.record.update(status='unknown_close_failure', error_type=type(error).__name__,
                error=str(error), failure_ns=time.perf_counter_ns())
            self.save()
            raise

    def failed(self, error):
        if self.record['status'] in ('unknown_setup_failure', 'unknown_close_failure', 'closed_identity_checked'):
            return
        self.record.update(status='unknown_interrupted_worker', error_type=type(error).__name__,
            error=str(error), failure_ns=time.perf_counter_ns())
        self.save()
