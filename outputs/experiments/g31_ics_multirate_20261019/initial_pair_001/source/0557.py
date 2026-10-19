"""Prepared owned120 gate for the data-only online method comparison.

Only the new comparison test module is collected, with the count recorded by
the actual collection plugin. Full accepted worker/parent code, canonical
archive checks and source entry/exit checks retain their defining globals.
This imports no model, native session, C provider or actual raw fixture.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from types import FunctionType
from . import run_static_root_inventory_pure as original

ROOT = original.ROOT
MODULE = __package__ + '.run_online_method_comparison_pure'
CANDIDATE = __package__ + '.live_obligation_online_method_comparison'
TEST = 'tests/test_g31_circulation_online_method_comparison.py'
BASE = ROOT/'outputs/cprep1/plan.json'
BASE_SHA = '420d03035f784898ca0175ee9294b329fa5a44742ef6e8219a1bd624725f3090'
BASE_COUNT = 234
PYTHON_SHA = original.PYTHON_SHA
WRAPPER = ROOT/'outputs/invoke_ocmp1.ps1'

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
    original.require(set(_namespace) == set(original_globals), 'comparison_pure_namespace_domain')
    original.require(all(value is allowed.get(name, original_globals[name])
        for name, value in _namespace.items()), 'comparison_pure_full_globals')
    for name in _NAMES:
        before, after = getattr(original, name), globals()[name]
        original.require(after.__code__ is before.__code__ and after.__globals__ is _namespace
            and after.__closure__ is before.__closure__ and after.__defaults__ is before.__defaults__
            and after.__kwdefaults__ is before.__kwdefaults__, 'comparison_pure_function_identity')
    for name in ('__init__', 'pytest_collection_finish'):
        before, after = getattr(original.Collection, name), getattr(Collection, name)
        original.require(after.__code__ is before.__code__ and after.__globals__ is _namespace
            and after.__closure__ is before.__closure__ and after.__defaults__ is before.__defaults__
            and after.__kwdefaults__ is before.__kwdefaults__, 'comparison_pure_collection_identity')
    return {'owned120_original_worker_and_parent_code': True,
        'all_original_defining_globals_preserved_except_explicit_bindings': True,
        'new_test_module_only_actual_collection_before_execution': True,
        'canonical_all_targets_preflight_before_first_archive_write': True,
        'inherited_234_current_and_independent_archive_checks_retained': True,
        'explicit_environment_required_by_original_worker': True,
        'old49_54_36_tests_not_reexecuted': True,
        'test_count_is_actual_collection_not_a_manual_estimate': True,
        'comparison_labels_are_not_native_authority': True,
        'native_C_model_raw_or_performance': False}


if __name__ == '__main__':
    source_proof()
    raise SystemExit(main())
