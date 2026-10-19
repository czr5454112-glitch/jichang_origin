"""Same30 tests; only exact-platform artifact-key assertions are corrected.

The failed216-source/678-evidence package remains read-only mandatory history.
Original8/42 prerequisites, stdlib checks, owned120 and no-execution monitor
remain unchanged. This module does not run metadata or the real bind gate.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import ast
from pathlib import Path
from types import FunctionType
import xml.etree.ElementTree as ET

from . import run_bound_source_proof_bind_v3_pure as previous

original, driver, ROOT = previous.original, previous.driver, previous.ROOT
MODULE = __package__ + '.run_bound_source_proof_bind_v3_pure_v2'
TESTS = ('tests/test_g31_circulation_bound_source_proof_bind_v3_driver_v2.py',)
EXPECTED_TESTS = 30
FAILED = ROOT/'outputs/bdbv3p1'
FAILED_PINS = {
    'plan.json': 'f1087ee3974516420af8e339efccab5928446af0d0f5c013ae45c489f9d6a463',
    'receipt.json': '90a2180e011a647b6d066a6fe6110ecd4b988a82e6e3244fd72d6069793763ac',
    'tests.xml': 'd89770e807dcff59f77ebc6eecac86cad815d01d37d6184013b85e4e164e20af',
    'bounded_parent_receipt.json': '49b7ea71712d500f8e516ee477d8e0b17d2e0e22c649e7bf3fb52f0a26da1113',
    'external_application_wall.json': 'c8e4a84607fa0ae4bc4591cc86bd8c60172793fb81aaa70ac67ddc5c1552391f',
}
FAILED_SUMMARY = ROOT/'outputs/bdbv3p1_failure_summary_001.json'
FAILED_SUMMARY_SHA256 = 'a2142aa7621bd439924de942e26cdd66c6a74cb5e400f5c6017e70e80fd66a08'
FAILED_WRAPPER = ROOT/'outputs/invoke_bdbv3p1.ps1'
FAILED_WRAPPER_SHA256 = '93a460288100249f374c599f1f7bfa1fc58865ecf4f533621360ed6c20495272'
OLD_TEST = ROOT/'tests/test_g31_circulation_bound_source_proof_bind_v3_driver.py'
OLD_TEST_SHA256 = '000455d8a64c2747b3a4cdefa6d78331a2fe891e040c2f3df1ab926cb1bb9963'
BEFORE = """    assert any(key.endswith('stdlib_fixture/__future__.py') for key in evidence)
    assert all(any(key.endswith(name) for key in evidence) for name in subject.PURE_OUTPUTS)"""
AFTER = """    output = parser.__globals__['WIRING_PURE']
    for name in subject.PURE_OUTPUTS:
        path = str(output/name)
        assert path in evidence
        assert evidence[path] == parser.__globals__['sha'](output/name)"""


def failed_gate():
    evidence = {}
    for name, digest in FAILED_PINS.items():
        driver.require(driver.sha(FAILED/name) == digest, 'v3_driver_pathfix_failed_pin:' + name)
        evidence[str(FAILED/name)] = digest
    for path, digest in ((FAILED_SUMMARY, FAILED_SUMMARY_SHA256), (FAILED_WRAPPER, FAILED_WRAPPER_SHA256)):
        driver.require(driver.sha(path) == digest, 'v3_driver_pathfix_failed_reference')
        evidence[str(path)] = digest
    plan, receipt = driver.read(FAILED/'plan.json'), driver.read(FAILED/'receipt.json')
    driver.require(len(plan['source_sha256']) == 216 and len(plan['prior_evidence_sha256']) == 678,
        'v3_driver_pathfix_exact_prior_domain')
    driver.archive.verify_archive(ROOT, FAILED, plan)
    driver.require(receipt['status'] == 'failed_or_unknown' and receipt['tests'] == receipt['expected_tests'] == 30
        and receipt['pytest_exitcode'] == 1 and receipt['source_changed'] == []
        and receipt['blocked_real_calls'] == [] and receipt['monitor_active_after_tests'] is True
        and all(type(receipt[k]) is int and receipt[k] == 0 for k in
            ('real_original_proof_calls', 'model_entry_calls', 'native_calls', 'custom_data_C_loads')),
        'v3_driver_pathfix_failure_not_promoted')
    driver.require(receipt['prior_evidence_exit'] == plan['prior_evidence_sha256'], 'v3_driver_pathfix_prior_exit')
    cases = ET.parse(FAILED/'tests.xml').getroot().findall('.//testcase')
    failed = [case for case in cases if case.find('failure') is not None]
    driver.require(len(cases) == 30 and len(failed) == 1
        and failed[0].get('name') == 'test_instantiated_full_parser_accepts_exact42_and_calls_archive'
        and not any(n.tag in ('error', 'skipped') for case in cases for n in case), 'v3_driver_pathfix_exact_failure')
    fixture = driver._stdlib_fixture(FAILED)
    driver.require(plan['stdlib_feature_fixture'] == receipt['stdlib_feature_fixture_exit'] == fixture,
        'v3_driver_pathfix_failed_stdlib')
    for path, digest in plan['prior_evidence_sha256'].items():
        driver.require(driver.sha(path) == digest, 'v3_driver_pathfix_prior_evidence:' + path)
        evidence[path] = digest
    for name, digest in plan['source_sha256'].items():
        evidence[str(ROOT/driver.archive.relative_python(name))] = digest
        evidence[str(FAILED/plan['source_archive'][name])] = digest
    evidence[str(FAILED/fixture['archive'])] = fixture['archive_sha256']
    return plan, evidence


def sources():
    from . import initial_owner_route_image as image
    plan, _ = failed_gate()
    driver.driver_pure_gate()
    files = {name: (ROOT/driver.archive.relative_python(name)).read_bytes() for name in plan['source_sha256']}
    for name, raw in image.source_closure(ROOT, (MODULE,
            'tests.test_g31_circulation_bound_source_proof_bind_v3_driver_v2')).items():
        driver.archive.relative_python(name)
        driver.require(name not in files or files[name] == raw, 'v3_driver_pathfix_source_collision')
        files[name] = raw
    return dict(sorted(files.items()))


def _clone(function, namespace):
    value = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    value.__kwdefaults__ = function.__kwdefaults__
    return value


def write(path, value):
    path = Path(path)
    if path.name == 'plan.json':
        _, evidence = failed_gate()
        value = {**value, 'failed_v3_driver_gate': {name: driver.ref(FAILED/name) for name in FAILED_PINS},
            'failed_v3_driver_summary': driver.ref(FAILED_SUMMARY),
            'failed_v3_driver_evidence_sha256': evidence}
    elif path.name == 'receipt.json':
        try:
            _, evidence = failed_gate()
            value['failed_v3_driver_evidence_exit'] = evidence
            driver.require(evidence == driver.read(path.parent/'plan.json')['failed_v3_driver_evidence_sha256'],
                'v3_driver_pathfix_full_history_exit')
        except BaseException as error:
            value['status'] = 'failed_or_unknown'
            value['failed_v3_driver_evidence_error'] = type(error).__name__ + ':' + str(error)
    return _previous_write(path, value)


_REPLACEMENTS = {'BOOT': BOOT, 'MODULE': MODULE, 'TESTS': TESTS,
    'EXPECTED_TESTS': EXPECTED_TESTS, 'sources': sources, 'write': write}
_NAMESPACE = {**vars(original), **_REPLACEMENTS}
worker = _clone(original.worker, _NAMESPACE)
_NAMESPACE['worker'] = worker
_main = _clone(original.main, _NAMESPACE)


def source_proof():
    driver.require(driver.sha(OLD_TEST) == OLD_TEST_SHA256, 'v3_driver_pathfix_old_test_immutable')
    before = OLD_TEST.read_text(encoding='utf8')
    after = (ROOT/TESTS[0]).read_text(encoding='utf8')
    driver.require(before.count(BEFORE) == 1
        and ast.dump(ast.parse(before.replace(BEFORE, AFTER)), include_attributes=False)
            == ast.dump(ast.parse(after), include_attributes=False), 'v3_driver_pathfix_only_exact_assertions')
    allowed = {*_REPLACEMENTS, 'worker'}
    driver.require(set(_NAMESPACE) == set(vars(original))
        and all(_NAMESPACE[k] is value for k, value in vars(original).items() if k not in allowed)
        and all(_NAMESPACE[k] is value for k, value in _REPLACEMENTS.items())
        and _NAMESPACE['worker'] is worker, 'v3_driver_pathfix_complete_globals')
    for actual, reference, namespace in ((worker, original.worker, _NAMESPACE),
            (_main, original.main, _NAMESPACE), (_previous_write, previous.write, _WRITE_GLOBALS)):
        driver.require(actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
            and actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
            and actual.__globals__ is namespace, 'v3_driver_pathfix_exact_original_code')
    driver.require(set(_WRITE_GLOBALS) == set(previous.write.__globals__)
        and all(_WRITE_GLOBALS[k] is value for k, value in previous.write.__globals__.items() if k != 'source_proof')
        and _WRITE_GLOBALS['source_proof'] is source_proof,
        'v3_driver_pathfix_complete_prior_write')
    return {'original_worker_and_main_code': True, 'complete_private_namespace': True,
        'test_count': EXPECTED_TESTS, 'tests': list(TESTS),
        'old8_and42_saved_prerequisites_not_reexecuted': True,
        'sticky_original_execution_monitor_unchanged': True,
        'stdlib_and_prior_evidence_checked_at_plan_and_receipt': True,
        'failed216_sources_and678_evidence_preserved': True,
        'only_test_change': 'Both suffix assertions replaced by exact platform path membership and digest for all PURE_OUTPUTS.',
        'original_driver_parser_unchanged': True,
        'real_original_proof_model_native_custom_C_calls': 0}


_WRITE_GLOBALS = {**previous.write.__globals__, 'source_proof': source_proof}
_previous_write = _clone(previous.write, _WRITE_GLOBALS)


def main():
    source_proof()
    return _main()


if __name__ == '__main__':
    raise SystemExit(main())
