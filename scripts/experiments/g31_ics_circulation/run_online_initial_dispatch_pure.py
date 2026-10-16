"""Owned120 synthetic initial dispatch gate; no real model or native call."""
import time
BOOT = time.monotonic()
from types import FunctionType
from . import run_bound_source_proof_pure as original

ROOT = original.ROOT
MODULE = __package__ + '.run_online_initial_dispatch_pure'
TESTS = ('tests/test_g31_circulation_online_initial_dispatch.py',)
EXPECTED_TESTS = 24


def sources():
    from . import initial_owner_route_image as image
    from . import diagnose_future_source_inventory as archive
    files = image.source_closure(ROOT, (MODULE, TESTS[0][:-3].replace('/', '.')))
    for name in files:
        archive.relative_python(name)
    return dict(sorted(files.items()))


def clone(function, values):
    result = FunctionType(function.__code__, values, function.__name__,
        function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def write(path, value):
    if path.name == 'plan.json':
        value = {**value, 'runner_source_proof': source_proof(),
            'scope': '24 synthetic owner-local dispatch cases. Real Transport/LocalTransport submit code is exercised only against fake sessions. Native getters, calls and reply-copy failures, immutable own rows, final clock failures and all seven same32 arm mappings are covered. No real model/native or complete request performance certificate.'}
    return original.write(path, value)


CHANGES = {'BOOT': BOOT, 'MODULE': MODULE, 'TESTS': TESTS,
    'EXPECTED_TESTS': EXPECTED_TESTS, 'sources': sources, 'write': write}
VALUES = {**vars(original), **CHANGES}
worker = clone(original.worker, VALUES)
VALUES['worker'] = worker
parent = clone(original.main, VALUES)


def source_proof():
    allowed = {*CHANGES, 'worker'}
    assert set(VALUES) == set(vars(original))
    assert all(VALUES[k] is v for k, v in vars(original).items() if k not in allowed)
    assert all(VALUES[k] is v for k, v in CHANGES.items()) and VALUES['worker'] is worker
    for actual, reference in ((worker, original.worker), (parent, original.main)):
        assert actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
        assert actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
        assert actual.__globals__ is VALUES
    return {'original_worker_and_main_code': True, 'complete_private_namespace': True,
        'test_count': EXPECTED_TESTS, 'tests': list(TESTS),
        'sticky_original_execution_monitor_unchanged': True,
        'actual_native_model_calls': 0, 'initial_dispatch_only': True}


def main():
    source_proof()
    return parent()


if __name__ == '__main__':
    raise SystemExit(main())
