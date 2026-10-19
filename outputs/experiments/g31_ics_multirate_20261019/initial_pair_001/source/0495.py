"""Only15 new synthetic bind-driver tests; original37 are frozen evidence.

Original owned120 worker/main code, defaults and closures are retained with a
complete private namespace. The only replacements are the test domain/count,
module entry, source collector, plan description and private worker used by main.
The original sticky real-proof/model-entry monitor remains unchanged.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
from types import FunctionType

from . import run_bound_source_proof_pure as original

MODULE = __package__ + '.run_bound_source_proof_bind_pure'
TESTS = ('tests/test_g31_circulation_bound_source_proof_bind_driver.py',)
EXPECTED_TESTS = 15
ROOT = original.ROOT


def sources():
    from . import diagnose_bound_source_proof_bind as bind_driver
    from . import initial_owner_route_image as image
    from . import diagnose_future_source_inventory as archive
    files = bind_driver.source_files()
    for name, raw in image.source_closure(ROOT, (MODULE,)).items():
        archive.relative_python(name)
        archive.require(name not in files or files[name] == raw, 'bind_pure_source_collision')
        files[name] = raw
    return dict(sorted(files.items()))


def _clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def write(path, value):
    if path.name == 'plan.json':
        value = {**value, 'scope': 'Only15 synthetic bind-driver orchestration/monitor tests; no real future import or original proof/model/native/custom C execution.',
                 'runner_source_proof': source_proof()}
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
        raise ValueError('bind_driver_pure:complete_namespace')
    if not all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in allowed):
        raise ValueError('bind_driver_pure:unchanged_globals')
    if not all(_NAMESPACE[k] is v for k, v in _REPLACEMENTS.items()) or _NAMESPACE['worker'] is not worker:
        raise ValueError('bind_driver_pure:declared_replacements')
    for actual, reference in ((worker, original.worker), (_main, original.main)):
        if not (actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
                and actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
                and actual.__globals__ is _NAMESPACE):
            raise ValueError('bind_driver_pure:exact_original_code')
    return {'original_worker_and_main_code': True, 'complete_private_namespace': True,
            'test_count': EXPECTED_TESTS, 'tests': list(TESTS),
            'original37_not_reexecuted': True, 'sticky_original_execution_monitor_unchanged': True}


def main():
    source_proof()
    return _main()


if __name__ == '__main__':
    raise SystemExit(main())
