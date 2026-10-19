"""Only25 v2 synthetic cases; no real proof/model/native/custom C execution.

The frozen owned120 worker/main and sticky execution monitor keep their exact
code, defaults and closures. Old37 and driver15 tests are closure dependencies
or historical evidence; neither old suite is executed by this entry point.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from types import FunctionType

from . import run_bound_source_proof_pure as original
from . import live_obligation_bound_source_proof_v2 as candidate
from . import live_obligation_bound_future_fork_v2 as candidate_future

MODULE = __package__ + '.run_bound_source_proof_v2_pure'
TESTS = ('tests/test_g31_circulation_bound_source_proof_v2.py',)
EXPECTED_TESTS = 25
ROOT = original.ROOT
FIXTURE_MODULE = 'tests.test_g31_circulation_bound_source_proof'


def sources():
    from . import diagnose_bound_source_proof_bind as bind_driver
    from . import initial_owner_route_image as image
    from . import diagnose_future_source_inventory as archive
    files = bind_driver.source_files()
    # Explicit qualified fixture entry avoids relying on test-path imports.
    entries = (MODULE, 'tests.test_g31_circulation_bound_source_proof_v2', FIXTURE_MODULE)
    for name, raw in image.source_closure(ROOT, entries).items():
        archive.relative_python(name)
        archive.require(name not in files or files[name] == raw, 'v2_pure_source_collision')
        files[name] = raw
    archive.require('tests/test_g31_circulation_bound_source_proof.py' in files,
                    'v2_pure_fixture_source_missing')
    return dict(sorted(files.items()))


def _clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def write(path, value):
    if path.name == 'plan.json':
        value = {**value,
            'scope': 'Only25 v2 synthetic static-float bits/dependency labels and factory lifecycle cases. Old37 and driver15 suites are not rerun. No real proof, model, native or custom C execution.',
            'runner_source_proof': source_proof(),
            'binder_v2_source_proof': candidate.source_proof(),
            'future_adapter_v2_source_proof': candidate_future.source_proof(),
            'fixture_module': FIXTURE_MODULE,
            'description_schema_limit': 'The unchanged BoundFutureRequest outer description remains v1; the binder proof and candidate adapter provenance identify the v2 static encoding only.'}
    return original.write(path, value)


_REPLACEMENTS = {'BOOT': BOOT, 'MODULE': MODULE, 'TESTS': TESTS,
                 'EXPECTED_TESTS': EXPECTED_TESTS, 'sources': sources, 'write': write}
_NAMESPACE = {**vars(original), **_REPLACEMENTS}
worker = _clone(original.worker, _NAMESPACE)
_NAMESPACE['worker'] = worker
_main = _clone(original.main, _NAMESPACE)


def source_proof():
    allowed = {*_REPLACEMENTS, 'worker'}
    if set(_NAMESPACE) != set(vars(original)):
        raise ValueError('v2_pure:complete_namespace')
    if not all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in allowed):
        raise ValueError('v2_pure:unchanged_globals')
    if not all(_NAMESPACE[k] is v for k, v in _REPLACEMENTS.items()) or _NAMESPACE['worker'] is not worker:
        raise ValueError('v2_pure:declared_replacements')
    for actual, reference in ((worker, original.worker), (_main, original.main)):
        if not (actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
                and actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
                and actual.__globals__ is _NAMESPACE):
            raise ValueError('v2_pure:exact_original_code')
    return {'original_worker_and_main_code': True, 'complete_private_namespace': True,
            'test_count': EXPECTED_TESTS, 'tests': list(TESTS),
            'explicit_fixture_module': FIXTURE_MODULE,
            'original37_and_driver15_not_reexecuted': True,
            'sticky_original_execution_monitor_unchanged': True,
            'real_original_proof_model_native_custom_C_calls': 0}


def main():
    source_proof()
    return _main()


if __name__ == '__main__':
    raise SystemExit(main())
