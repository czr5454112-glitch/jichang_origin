"""Source-only prepared owned120 gate for the constructor prelude diagnostics.

Only the new focused synthetic module is collected. The accepted worker,
parent, archive validation and actual collection plugin retain their complete
code and defining globals, except for the explicit private bindings below.
No old sinv1/sicp1 tests, model, native session, C provider or raw fixture run.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from types import FunctionType
from . import run_static_root_inventory_pure as original

ROOT = original.ROOT
MODULE = __package__ + '.run_constructor_prelude_pure'
CANDIDATE = __package__ + '.constructor_prelude_instrumentation'
TEST = 'tests/test_g31_circulation_constructor_prelude.py'
BASE = ROOT/'outputs/sicp1/plan.json'
BASE_SHA = 'b34a896cf0b9c503536198fc6131faa18b0acfd00629560d62bf14a333805d6a'
BASE_COUNT = 230
PYTHON_SHA = original.PYTHON_SHA
WRAPPER = ROOT/'outputs/invoke_cprep1.ps1'

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


# The original plugin records actual collected node IDs before any test runs.
# Its TEST binding must be the new module, not the inherited gate's test file.
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
    original.require(set(_namespace) == set(original_globals), 'prelude_pure_namespace_domain')
    original.require(all(value is allowed.get(name, original_globals[name])
        for name, value in _namespace.items()), 'prelude_pure_full_globals')
    for name in _NAMES:
        before, after = getattr(original, name), globals()[name]
        original.require(after.__code__ is before.__code__ and after.__globals__ is _namespace
            and after.__closure__ is before.__closure__ and after.__defaults__ is before.__defaults__
            and after.__kwdefaults__ is before.__kwdefaults__, 'prelude_pure_function_identity')
    for name in ('__init__', 'pytest_collection_finish'):
        before, after = getattr(original.Collection, name), getattr(Collection, name)
        original.require(after.__code__ is before.__code__ and after.__globals__ is _namespace
            and after.__closure__ is before.__closure__ and after.__defaults__ is before.__defaults__
            and after.__kwdefaults__ is before.__kwdefaults__, 'prelude_pure_collection_identity')
    return {'owned120_original_worker_and_parent_code': True,
        'all_original_defining_globals_preserved_except_explicit_bindings': True,
        'new_test_module_only_actual_collection_before_execution': True,
        'canonical_all_targets_preflight_before_first_archive_write': True,
        'inherited_230_current_and_independent_archive_checks_retained': True,
        'explicit_environment_required_by_original_worker': True,
        'old49_and54_tests_not_reexecuted': True,
        'test_count_is_actual_collection_not_a_manual_estimate': True,
        'native_C_model_raw_or_performance': False}


if __name__ == '__main__':
    source_proof()
    raise SystemExit(main())
