"""Eight new synthetic v2 driver wiring checks under the original owned120.

No old25/37/15 test rerun, real proof, model, native or custom C execution.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from types import FunctionType

from . import run_bound_source_proof_pure as original
from . import diagnose_bound_source_proof_bind_v2 as driver

MODULE = __package__ + '.run_bound_source_proof_bind_v2_pure'
TESTS = ('tests/test_g31_circulation_bound_source_proof_bind_v2_driver.py',)
EXPECTED_TESTS = 8
ROOT = original.ROOT


def sources():
    # source_files requires accepted25/old failure evidence, not this gate's
    # future result. Its explicit closure includes this runner and its test.
    return driver.source_files()


def _clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def write(path, value):
    if path.name == 'plan.json':
        value = {**value,
            'scope': 'Only8 synthetic v2 bind-driver wiring/first-write/mandatory-evidence checks; old25/37/15 suites not rerun; no real proof/model/native/custom C execution.',
            'runner_source_proof': source_proof(), 'bind_driver_v2_source_proof': driver.source_proof()}
    return original.write(path, value)


_REPLACEMENTS = {'BOOT': BOOT, 'MODULE': MODULE, 'TESTS': TESTS,
    'EXPECTED_TESTS': EXPECTED_TESTS, 'sources': sources, 'write': write}
_NAMESPACE = {**vars(original), **_REPLACEMENTS}
worker = _clone(original.worker, _NAMESPACE)
_NAMESPACE['worker'] = worker
_main = _clone(original.main, _NAMESPACE)


def source_proof():
    allowed = {*_REPLACEMENTS, 'worker'}
    driver.require(set(_NAMESPACE) == set(vars(original))
        and all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in allowed), 'v2_driver_pure_all_globals')
    driver.require(all(_NAMESPACE[k] is v for k, v in _REPLACEMENTS.items())
        and _NAMESPACE['worker'] is worker, 'v2_driver_pure_replacements')
    for actual, reference in ((worker, original.worker), (_main, original.main)):
        driver.require(actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
            and actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
            and actual.__globals__ is _NAMESPACE, 'v2_driver_pure_exact_original_code')
    return {'original_worker_and_main_code': True, 'complete_private_namespace': True,
        'test_count': EXPECTED_TESTS, 'tests': list(TESTS),
        'prior25_37_15_not_reexecuted': True, 'sticky_original_execution_monitor_unchanged': True}


def main():
    source_proof()
    return _main()


if __name__ == '__main__':
    raise SystemExit(main())
