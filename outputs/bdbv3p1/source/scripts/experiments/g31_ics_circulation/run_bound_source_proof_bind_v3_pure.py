"""Thirty synthetic v3 driver/parser tests; unchanged owned120 worker/main.

Old8 and42 complete saved evidence is required, never rerun. No real proof,
model, native or custom C. The external stdlib fixture is separate from the
canonical ROOT-relative project-source archive.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from pathlib import Path
from types import FunctionType

from . import run_bound_source_proof_pure as original
from . import diagnose_bound_source_proof_bind_v3 as driver

MODULE = __package__ + '.run_bound_source_proof_bind_v3_pure'
TESTS = ('tests/test_g31_circulation_bound_source_proof_bind_v3_driver.py',)
EXPECTED_TESTS = 30
ROOT = original.ROOT


def sources():
    from . import initial_owner_route_image as image
    # Full old8/new42 validators are read-only prerequisites, not pytest calls.
    driver.driver_pure_gate()
    files = driver.source_files()
    for name, raw in image.source_closure(ROOT, (MODULE,
            'tests.test_g31_circulation_bound_source_proof_bind_v3_driver')).items():
        driver.archive.relative_python(name)
        driver.require(name not in files or files[name] == raw, 'v3_driver_pure_source_collision')
        files[name] = raw
    return dict(sorted(files.items()))


def _clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def write(path, value):
    path = Path(path)
    if path.name == 'plan.json':
        value = {**value,
            'scope': 'Only30 synthetic v3 driver/parser/stdlib/mandatory-evidence tests. Original8 and42 are saved prerequisites; old suites are not rerun. No real proof/model/native/custom C execution.',
            'runner_source_proof': source_proof(),
            'bind_driver_v3_source_proof': driver.source_proof(),
            'required_wiring_pure': driver.previous._wiring_references(),
            'required_v3_pure': driver._pure_references(),
            'prior_evidence_sha256': driver.driver_pure_gate(),
            'stdlib_feature_fixture': driver._stdlib_fixture(path.parent, create=True)}
    elif path.name == 'receipt.json':
        # Retain the receipt even when post-test evidence or fixture validation
        # fails. Such a receipt cannot be accepted by the external wrapper.
        try:
            plan = driver.read(path.parent/'plan.json')
            value['stdlib_feature_fixture_exit'] = driver._stdlib_fixture(path.parent)
            driver.require(value['stdlib_feature_fixture_exit'] == plan['stdlib_feature_fixture'],
                'v3_driver_pure_stdlib_exit')
            value['prior_evidence_exit'] = driver.driver_pure_gate()
            driver.require(value['prior_evidence_exit'] == plan['prior_evidence_sha256'],
                'v3_driver_pure_prior_evidence_exit')
        except BaseException as error:
            value['status'] = 'failed_or_unknown'
            value['prior_evidence_or_stdlib_exit_error'] = type(error).__name__ + ':' + str(error)
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
        and all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in allowed),
        'v3_driver_pure_all_globals')
    driver.require(all(_NAMESPACE[k] is v for k, v in _REPLACEMENTS.items())
        and _NAMESPACE['worker'] is worker, 'v3_driver_pure_replacements')
    for actual, reference in ((worker, original.worker), (_main, original.main)):
        driver.require(actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
            and actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
            and actual.__globals__ is _NAMESPACE, 'v3_driver_pure_exact_original_code')
    return {'original_worker_and_main_code': True, 'complete_private_namespace': True,
        'test_count': EXPECTED_TESTS, 'tests': list(TESTS),
        'old8_and42_saved_prerequisites_not_reexecuted': True,
        'sticky_original_execution_monitor_unchanged': True,
        'stdlib_and_prior_evidence_checked_at_plan_and_receipt': True,
        'real_original_proof_model_native_custom_C_calls': 0}


def main():
    source_proof()
    return _main()


if __name__ == '__main__':
    raise SystemExit(main())
