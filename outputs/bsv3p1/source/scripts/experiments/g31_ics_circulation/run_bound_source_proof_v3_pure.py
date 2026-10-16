"""Only42 synthetic v3 feature cases; no real proof/model/native/custom C.

The original owned120 worker/main and sticky monitor retain exact code. The
external pinned stdlib fixture is separately archived and checked at receipt;
it is not smuggled into the ROOT-relative project-source map.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import hashlib
from pathlib import Path
from types import FunctionType

from . import run_bound_source_proof_pure as original
from . import live_obligation_bound_source_proof_v3 as candidate
from . import live_obligation_bound_future_fork_v3 as candidate_future

MODULE = __package__ + '.run_bound_source_proof_v3_pure'
TESTS = ('tests/test_g31_circulation_bound_source_proof_v3.py',)
EXPECTED_TESTS = 42
ROOT = original.ROOT
STDLIB_ARCHIVE = 'stdlib_fixture/__future__.py'


def sources():
    from . import diagnose_bound_source_proof_bind_v2 as inherited
    from . import initial_owner_route_image as image
    from . import diagnose_future_source_inventory as archive
    files = inherited.source_files()
    for name, raw in image.source_closure(ROOT, (MODULE,
            'tests.test_g31_circulation_bound_source_proof_v3')).items():
        archive.relative_python(name)
        archive.require(name not in files or files[name] == raw, 'v3_pure_source_collision')
        files[name] = raw
    return dict(sorted(files.items()))


def _stdlib(output, *, create):
    source = candidate._FEATURE_PATH
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != candidate.FEATURE_SOURCE_SHA256:
        raise ValueError('v3_pure:stdlib_source_bytes')
    target = output/STDLIB_ARCHIVE
    if not target.resolve().is_relative_to(output.resolve()) or len(str(target.resolve())) >= 260:
        raise ValueError('v3_pure:stdlib_archive_path')
    if create:
        if target.exists():
            raise ValueError('v3_pure:stdlib_archive_exists')
        target.parent.mkdir(exist_ok=False)
        with target.open('xb') as stream:
            stream.write(raw)
    if target.read_bytes() != raw:
        raise ValueError('v3_pure:stdlib_archive_bytes')
    return {'path': str(source), 'sha256': candidate.FEATURE_SOURCE_SHA256,
            'archive': STDLIB_ARCHIVE, 'archive_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}


def write(path, value):
    path = Path(path)
    if path.name == 'plan.json':
        value = {**value,
            'scope': 'Only42 synthetic canonical-feature, complete-code and mutation/factory cases. Isolated copies of pinned stdlib definitions; no real original proof, model, native or custom C. Old37/25/15/8 suites are not rerun.',
            'runner_source_proof': source_proof(),
            'binder_v3_source_proof': candidate.source_proof(),
            'future_adapter_v3_source_proof': candidate_future.source_proof(),
            'stdlib_feature_fixture': _stdlib(path.parent, create=True),
            'description_schema_limit': 'The unchanged BoundFutureRequest outer description remains v1. The new binder and adapter proofs identify only static-feature support, not a new model.'}
    elif path.name == 'receipt.json':
        # Never allow fixture/source check failure to erase the test receipt.
        try:
            value['stdlib_feature_fixture_exit'] = _stdlib(path.parent, create=False)
        except BaseException as error:
            value['status'] = 'failed_or_unknown'
            value['stdlib_feature_fixture_error'] = type(error).__name__ + ':' + str(error)
    return original.write(path, value)


def _clone(function, namespace):
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


_REPLACEMENTS = {'BOOT': BOOT, 'MODULE': MODULE, 'TESTS': TESTS,
                 'EXPECTED_TESTS': EXPECTED_TESTS, 'sources': sources, 'write': write}
_NAMESPACE = {**vars(original), **_REPLACEMENTS}
worker = _clone(original.worker, _NAMESPACE)
_NAMESPACE['worker'] = worker
_main = _clone(original.main, _NAMESPACE)


def source_proof():
    allowed = {*_REPLACEMENTS, 'worker'}
    if set(_NAMESPACE) != set(vars(original)):
        raise ValueError('v3_pure:complete_namespace')
    if not all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in allowed):
        raise ValueError('v3_pure:unchanged_globals')
    if not all(_NAMESPACE[k] is v for k, v in _REPLACEMENTS.items()) or _NAMESPACE['worker'] is not worker:
        raise ValueError('v3_pure:declared_replacements')
    for actual, reference in ((worker, original.worker), (_main, original.main)):
        if not (actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
                and actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
                and actual.__globals__ is _NAMESPACE):
            raise ValueError('v3_pure:exact_original_code')
    return {'original_worker_and_main_code': True, 'complete_private_namespace': True,
        'test_count': EXPECTED_TESTS, 'tests': list(TESTS),
        'only_synthetic_fixture_proofs': True, 'old37_25_15_8_not_reexecuted': True,
        'sticky_original_execution_monitor_unchanged': True,
        'stdlib_fixture_archived_and_checked_at_plan_and_receipt': True,
        'real_original_proof_model_native_custom_C_calls': 0}


def main():
    source_proof()
    return _main()


if __name__ == '__main__':
    raise SystemExit(main())
