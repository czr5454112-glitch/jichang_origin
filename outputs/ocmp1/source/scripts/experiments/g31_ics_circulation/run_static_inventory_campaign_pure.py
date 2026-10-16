"""Owned120 focused synthetic campaign gate, based on the frozen sinv1 gate.

Only this new test module is collected. Original worker/parent code and full
defining globals are retained in a private shared namespace, with explicit
module/test/wrapper/base bindings. No imported dictionary is modified.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from types import FunctionType
from . import run_static_root_inventory_pure as original

ROOT = original.ROOT
MODULE = __package__ + '.run_static_inventory_campaign_pure'
CANDIDATE = __package__ + '.single_capture_static_inventory_runtime'
TEST = 'tests/test_g31_circulation_static_inventory_campaign.py'
BASE = ROOT/'outputs/sinv1/plan.json'
BASE_SHA = 'd0b4f0748883bdc71f5205db3b8bd326348503ff306bb93491c88a52d3427a81'
BASE_COUNT = 222
PYTHON_SHA = original.PYTHON_SHA
WRAPPER = ROOT/'outputs/invoke_sicp1.ps1'

_NAMES = ('inherited_sources', 'source_files', 'verify_sources', 'loaded_sources',
    'no_execution_extensions', 'worker', 'main')
_CHANGES = {name: globals()[name] for name in
    ('BOOT', 'MODULE', 'CANDIDATE', 'TEST', 'BASE', 'BASE_SHA', 'BASE_COUNT', 'WRAPPER')}
_namespace = {**vars(original), **_CHANGES}


def _shared(function):
    value = FunctionType(function.__code__, _namespace, function.__name__,
        function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


# The collection plugin needs the same new TEST binding, even though the old
# constructor remains byte-for-byte identical. No old tests are collected.
Collection = type('Collection', (), {
    '__init__': _shared(original.Collection.__init__),
    'pytest_collection_finish': _shared(original.Collection.pytest_collection_finish)})
_namespace['Collection'] = Collection
for _name in _NAMES:
    _namespace[_name] = _shared(getattr(original, _name))
for _name in _NAMES:
    globals()[_name] = _namespace[_name]


def source_proof():
    allowed = {**_CHANGES, 'Collection': Collection,
        **{name: globals()[name] for name in _NAMES}}
    original_globals = vars(original)
    original.require(set(_namespace) == set(original_globals), 'campaign_pure_namespace_domain')
    original.require(all(value is allowed.get(name, original_globals[name])
        for name, value in _namespace.items()), 'campaign_pure_full_globals')
    for name in _NAMES:
        before, after = getattr(original, name), globals()[name]
        original.require(after.__code__ is before.__code__ and after.__globals__ is _namespace
            and after.__closure__ is before.__closure__ and after.__defaults__ is before.__defaults__
            and after.__kwdefaults__ is before.__kwdefaults__, 'campaign_pure_function_identity')
    original.require(Collection.pytest_collection_finish.__globals__ is _namespace
        and Collection.pytest_collection_finish.__code__ is original.Collection.pytest_collection_finish.__code__,
        'campaign_pure_actual_collection_binding')
    return {'owned120_original_worker_and_parent_code': True,
        'all_original_defining_globals_preserved_except_explicit_bindings': True,
        'new_test_module_only_actual_collection_before_execution': True,
        'canonical_all_targets_preflight_before_first_archive_write': True,
        'explicit_environment_required_by_original_worker': True,
        'old49_tests_not_reexecuted': True, 'native_C_model_raw_or_performance': False}


if __name__ == '__main__':
    source_proof()
    raise SystemExit(main())
