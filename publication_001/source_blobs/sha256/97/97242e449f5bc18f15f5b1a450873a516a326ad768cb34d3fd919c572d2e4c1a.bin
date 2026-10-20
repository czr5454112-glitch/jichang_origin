"""V2 bind-only dependency gate draft; no execution is authorized by this file.

Only the static float encoding changes. The original one-cold/one-warm probe,
monitor, cleanup, owned process tree and budget code remain the same. The v1
failed run remains evidence. A v2 binding may still reject another unsupported
dependency; no omissions or retries are introduced here.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import ast
import copy
import hashlib
import inspect
import json
import math
from pathlib import Path
import sys
import textwrap
from types import FunctionType
import xml.etree.ElementTree as ET

from . import diagnose_bound_source_proof_bind as original
from . import live_obligation_bound_future_fork_v2 as candidate_binding

ROOT, archive, codec = original.ROOT, original.archive, original.codec
sha, read, ref, require = original.sha, original.read, original.ref, original.require
MODULE = __package__ + '.diagnose_bound_source_proof_bind_v2'
SCHEMA = 'g31.bound_source_proof.one_bind_one_use.v2'
PURE = ROOT/'outputs/bsvp1'
FAILED = ROOT/'outputs/bdb1'
WIRING_PURE = ROOT/'outputs/bdbv2p1'
WIRING_WRAPPER = ROOT/'outputs/invoke_bdbv2p1.ps1'
WIRING_MODULE = __package__ + '.run_bound_source_proof_bind_v2_pure'
WIRING_TEST = 'tests/test_g31_circulation_bound_source_proof_bind_v2_driver.py'
WIRING_OUTPUTS = ('plan.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json', 'stdout.log', 'stderr.log')
PURE_PINS = {
    'plan.json': '1d32ac448f5656f8d16c0c11b99c390ee4dd7273ab59afd330cafb508fc0820d',
    'receipt.json': '2dc2cb1ba1bfac968e66f7ddcc79940948bb2316b552751de82940783877bd43',
    'tests.xml': 'fb764d502d31f1701674a283fedcae9c095925b1fba1a2840ba0a918adb2137d',
    'bounded_parent_receipt.json': 'e52bdcfe3b7a7d2935ea0eeaf303ec30a4d6d213f4ac80d83e268b934b488522',
    'external_application_wall.json': 'f396b1872aa8de58b8e4cc91ed9a70d183e84a4a98abdedab149b3bf5eda3d73',
    'root_saved_review_001.json': 'e9ac599fe2a9cc90ab48e1a5a2debbbf18c5bc8995fece408a895ead041cc1c1',
}
FAILED_PINS = {
    'report.json': '67173f0acc53a00d043fe8eeccc51cf965d295d5d120299ce40e1932706a5076',
    'receipt.json': 'd4b74b873b652a5fcd487e2dc82161f31c862f192f2fd818e066f106cb4ab00d',
    'actual.bounded.json': '738f8ab582f7678aa304f8faceacf4c0ee0f3d07c8dfa0740d526fae7bc35b5c',
    'external_application_wall.json': '4c1739f822d59f2d739216edaad4d5c58d585b74c5fcb9b6221e501232016f46',
}
WRAPPER = ROOT/'outputs/invoke_bsvp1.ps1'
WRAPPER_SHA256 = 'df61d6b4cbdde75b05826248ca1fc298833e57f8057bf21492e45ce6829aa159'
PURE_SOURCE_KEYS = (
    'scripts/experiments/g31_ics_circulation/live_obligation_bound_source_proof.py',
    'scripts/experiments/g31_ics_circulation/live_obligation_bound_future_fork.py',
    'scripts/experiments/g31_ics_circulation/run_bound_source_proof_pure.py',
    'tests/test_g31_circulation_bound_source_proof.py',
    'scripts/experiments/g31_ics_circulation/diagnose_bound_source_proof_bind.py',
    'tests/test_g31_circulation_bound_source_proof_bind_driver.py',
    'scripts/experiments/g31_ics_circulation/live_obligation_bound_source_proof_v2.py',
    'scripts/experiments/g31_ics_circulation/live_obligation_bound_future_fork_v2.py',
    'scripts/experiments/g31_ics_circulation/run_bound_source_proof_v2_pure.py',
    'tests/test_g31_circulation_bound_source_proof_v2.py',
)


def pure_gate():
    evidence = {}
    for directory, pins in ((PURE, PURE_PINS), (FAILED, FAILED_PINS)):
        for name, expected in pins.items():
            require(sha(directory/name) == expected, 'v2_prior_identity:' + name)
            evidence[str(directory/name)] = expected
    require(sha(WRAPPER) == WRAPPER_SHA256, 'v2_pure_wrapper_bytes')
    evidence[str(WRAPPER)] = WRAPPER_SHA256
    plan, receipt, bounded, external = (read(PURE/name) for name in
        ('plan.json', 'receipt.json', 'bounded_parent_receipt.json', 'external_application_wall.json'))
    command = [sys.executable, '-m', __package__ + '.run_bound_source_proof_v2_pure', '--output', str(PURE)]
    require(plan['schema'] == 'g31.bound_source_proof.synthetic_pure.v1'
        and plan['tests'] == ['tests/test_g31_circulation_bound_source_proof_v2.py']
        and type(plan['expected_tests']) is int and plan['expected_tests'] == 25
        and plan['shared_seconds'] == 120. and plan['output_directory'] == str(PURE)
        and plan['fixture_module'] == 'tests.test_g31_circulation_bound_source_proof'
        and plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'v2_pure_plan')
    require(receipt['status'] == 'passed' and receipt['tests'] == receipt['expected_tests'] == 25
        and receipt['pytest_exitcode'] == 0 and receipt['source_changed'] == []
        and receipt['blocked_real_calls'] == [] and receipt['monitor_active_after_tests'] is True
        and all(type(receipt[k]) is int and receipt[k] == 0 for k in
            ('real_original_proof_calls', 'model_entry_calls', 'native_calls', 'custom_data_C_loads')), 'v2_pure_result')
    require(receipt['plan_sha256'] == sha(PURE/'plan.json') and receipt['XML_sha256'] == sha(PURE/'tests.xml')
        and bounded['receipt_sha256'] == sha(PURE/'receipt.json') and bounded['command'] == command
        and bounded['output_directory'] == str(PURE) and bounded['shared_seconds'] == 120.
        and bounded['status'] == 'passed' and bounded['process']['status'] == 'exited'
        and bounded['process']['exitcode'] == 0, 'v2_pure_owned_chain')
    cases = ET.parse(PURE/'tests.xml').getroot().findall('.//testcase')
    require(len(cases) == 25 and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c), 'v2_pure_XML25')
    archive.verify_archive(ROOT, PURE, plan)
    frequency, ticks, seconds = (external[k] for k in
        ('stopwatch_frequency', 'elapsed_ticks', 'external_application_seconds'))
    require(external['schema'] == 'g31.bound_source_proof.v2_pure_external.v1'
        and external['status'] == 'passed25_synthetic_with_external_bound'
        and external['command'] == command and external['cwd'] == str(ROOT.resolve())
        and external['output_directory'] == str(PURE) and external['launched'] is True
        and type(external['exitcode']) is int and external['exitcode'] == 0
        and type(external['wrapper_exitcode']) is int and external['wrapper_exitcode'] == 0,
        'v2_pure_external_execution')
    require(type(frequency) is int and frequency > 0 and type(ticks) is int and 0 <= ticks <= 120*frequency
        and type(seconds) in (int, float) and math.isfinite(seconds)
        and seconds == float(ticks)/float(frequency) and external['shared_limit_seconds'] == 120.
        and external['clock_scope'] == 'immediately_before_python_launch_through_process_return', 'v2_pure_external_clock')
    outputs = ('plan.json', 'receipt.json', 'tests.xml', 'bounded_parent_receipt.json', 'stdout.log', 'stderr.log')
    require(external['outputs'] == {name: ref(PURE/name) for name in outputs}, 'v2_pure_external_outputs')
    expected = {str(WRAPPER): sha(WRAPPER), sys.executable: sha(sys.executable)}
    expected.update({str(ROOT/archive.relative_python(name)): plan['source_sha256'][name] for name in PURE_SOURCE_KEYS})
    require(external['expected_pins'] == external['pins_before'] == external['pins_after'] == expected, 'v2_pure_external_pins')
    require(plan['binder_v2_source_proof'] == candidate_binding.binding.source_proof()
        and plan['future_adapter_v2_source_proof'] == candidate_binding.source_proof(), 'v2_pure_binding_provenance')
    failure = read(FAILED/'report.json')
    require(failure['status'] == 'unknown_failed_actual_dependency_domain'
        and failure['calls']['original_source_proof_calls'] == 0
        and failure['calls']['private_proof_calls'] == 0
        and failure['calls']['blocked_model_calls'] == [], 'v1_failure_preserved_not_accepted')
    evidence.update({str(PURE/name): sha(PURE/name) for name in outputs})
    return plan, evidence


def source_files():
    from . import initial_owner_route_image as image
    plan, _ = pure_gate()
    files = {}
    for name, digest in plan['source_sha256'].items():
        raw = (ROOT/archive.relative_python(name)).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'v2_inherited_source_bytes:' + name)
        files[name] = raw
    for name, raw in image.source_closure(ROOT, (MODULE, WIRING_MODULE,
        'tests.test_g31_circulation_bound_source_proof_bind_v2_driver')).items():
        archive.relative_python(name)
        require(name not in files or files[name] == raw, 'v2_bind_source_collision')
        files[name] = raw
    return dict(sorted(files.items()))


def driver_pure_gate():
    # The original orchestration's15 tests remain historical accepted evidence;
    # this v2 gate additionally requires the fresh25 factory/static tests.
    evidence = original.driver_pure_gate()
    _, fresh = pure_gate()
    return evidence | fresh | wiring_pure_gate()


def _wiring_references():
    return {'output_directory': str(WIRING_PURE), 'expected_tests': 8,
        'artifacts': {name: ref(WIRING_PURE/name) for name in (*WIRING_OUTPUTS, 'external_application_wall.json')},
        'wrapper': ref(WIRING_WRAPPER)}


def wiring_pure_gate():
    """Required in prepare and every actual check_plan, never during pure tests."""
    plan, receipt, bounded, external = (read(WIRING_PURE/name) for name in
        ('plan.json', 'receipt.json', 'bounded_parent_receipt.json', 'external_application_wall.json'))
    command = [sys.executable, '-m', WIRING_MODULE, '--output', str(WIRING_PURE)]
    require(plan['schema'] == 'g31.bound_source_proof.synthetic_pure.v1'
        and plan['tests'] == [WIRING_TEST] and type(plan['expected_tests']) is int and plan['expected_tests'] == 8
        and plan['output_directory'] == str(WIRING_PURE) and plan['shared_seconds'] == 120.
        and plan['environment'] == {'python': sys.executable, 'sha256': sha(sys.executable)}, 'v2_wiring_pure_plan')
    require(plan['bind_driver_v2_source_proof'] == source_proof(), 'v2_wiring_pure_exact_driver')
    archive.verify_archive(ROOT, WIRING_PURE, plan)
    require(receipt['status'] == 'passed' and type(receipt['tests']) is int
        and receipt['tests'] == receipt['expected_tests'] == 8 and receipt['pytest_exitcode'] == 0
        and receipt['source_changed'] == [] and receipt['blocked_real_calls'] == []
        and receipt['monitor_active_after_tests'] is True
        and all(type(receipt[k]) is int and receipt[k] == 0 for k in
            ('real_original_proof_calls', 'model_entry_calls', 'native_calls', 'custom_data_C_loads')), 'v2_wiring_pure_result')
    require(receipt['plan_sha256'] == sha(WIRING_PURE/'plan.json')
        and receipt['XML_sha256'] == sha(WIRING_PURE/'tests.xml')
        and bounded['receipt_sha256'] == sha(WIRING_PURE/'receipt.json')
        and bounded['command'] == command and bounded['status'] == 'passed'
        and bounded['shared_seconds'] == 120. and bounded['output_directory'] == str(WIRING_PURE), 'v2_wiring_receipt_chain')
    process = bounded['process']
    require(process['status'] == 'exited' and type(process['exitcode']) is int and process['exitcode'] == 0
        and type(process['pid']) is int and process['pid'] > 0
        and process['windows_job_kill_on_close'] is True
        and process['child_released_only_after_job_assignment'] is True, 'v2_wiring_owned_tree')
    cases = ET.parse(WIRING_PURE/'tests.xml').getroot().findall('.//testcase')
    require(len(cases) == 8 and not any(n.tag in ('failure', 'error', 'skipped') for c in cases for n in c), 'v2_wiring_XML8')
    previous = {}
    for name in ('loaded_entry', 'loaded_exit', 'loaded_exit_final'):
        loaded = receipt[name]
        require(type(loaded) is dict and loaded and previous.items() <= loaded.items()
            and all(key in plan['source_sha256'] and digest == plan['source_sha256'][key]
                for key, digest in loaded.items()), 'v2_wiring_loaded_closure:' + name)
        previous = loaded
    require(WIRING_TEST in previous and 'scripts/experiments/g31_ics_circulation/diagnose_bound_source_proof_bind_v2.py' in previous,
        'v2_wiring_loaded_test_and_driver')
    frequency, ticks, seconds = (external[k] for k in
        ('stopwatch_frequency', 'elapsed_ticks', 'external_application_seconds'))
    require(external['schema'] == 'g31.bound_source_proof.v2_bind_driver_pure_external.v1'
        and external['status'] == 'passed8_synthetic_with_external_bound'
        and external['command'] == command and external['cwd'] == str(ROOT.resolve())
        and external['output_directory'] == str(WIRING_PURE) and external['launched'] is True
        and type(external['exitcode']) is int and external['exitcode'] == 0
        and type(external['wrapper_exitcode']) is int and external['wrapper_exitcode'] == 0, 'v2_wiring_external_execution')
    require(type(frequency) is int and frequency > 0 and type(ticks) is int and 0 <= ticks <= 120*frequency
        and type(seconds) in (int, float) and math.isfinite(seconds) and seconds == float(ticks)/float(frequency)
        and external['shared_limit_seconds'] == 120.
        and external['clock_scope'] == 'immediately_before_python_launch_through_process_return', 'v2_wiring_external_clock')
    require(external['outputs'] == {name: ref(WIRING_PURE/name) for name in WIRING_OUTPUTS}, 'v2_wiring_external_outputs')
    source_keys = (*PURE_SOURCE_KEYS,
        'scripts/experiments/g31_ics_circulation/diagnose_bound_source_proof_bind_v2.py', WIRING_TEST,
        'scripts/experiments/g31_ics_circulation/run_bound_source_proof_bind_v2_pure.py')
    expected = {str(WIRING_WRAPPER): sha(WIRING_WRAPPER), sys.executable: sha(sys.executable)}
    expected.update({str(ROOT/archive.relative_python(name)): plan['source_sha256'][name] for name in source_keys})
    require(external['expected_pins'] == external['pins_before'] == external['pins_after'] == expected, 'v2_wiring_external_pins')
    evidence = {str(WIRING_PURE/name): sha(WIRING_PURE/name) for name in (*WIRING_OUTPUTS, 'external_application_wall.json')}
    evidence[str(WIRING_WRAPPER)] = sha(WIRING_WRAPPER)
    # Actual check_plan keeps every pure current/archive file explicitly bound,
    # including the runner that is not itself used by the actual dependency gate.
    for name, digest in plan['source_sha256'].items():
        evidence[str(ROOT/archive.relative_python(name))] = digest
        evidence[str(WIRING_PURE/plan['source_archive'][name])] = digest
    return evidence


def _dump(tree):
    return ast.dump(tree, include_attributes=False)


def worker_code():
    tree = ast.parse(textwrap.dedent(inspect.getsource(original.worker)))
    old = ast.parse('from . import live_obligation_bound_future_fork as candidate').body[0]
    new = ast.parse('from . import live_obligation_bound_future_fork_v2 as candidate').body[0]
    annotation = ast.parse("report['binding_adapter_source_proof'] = candidate.source_proof()").body[0]
    class Forward(ast.NodeTransformer):
        count = 0
        def visit_ImportFrom(self, node):
            if _dump(node) == _dump(old):
                self.count += 1
                return [ast.copy_location(copy.deepcopy(new), node), ast.copy_location(copy.deepcopy(annotation), node)]
            return self.generic_visit(node)
    forward = Forward(); changed = forward.visit(copy.deepcopy(tree))
    require(forward.count == 1, 'v2_one_candidate_import')
    class Inverse(ast.NodeTransformer):
        imports = 0; annotations = 0
        def visit_ImportFrom(self, node):
            if _dump(node) == _dump(new):
                self.imports += 1
                return ast.copy_location(copy.deepcopy(old), node)
            return self.generic_visit(node)
        def visit_Assign(self, node):
            if _dump(node) == _dump(annotation):
                self.annotations += 1
                return None
            return self.generic_visit(node)
    inverse = Inverse(); restored = inverse.visit(copy.deepcopy(changed))
    require(inverse.imports == inverse.annotations == 1 and _dump(restored) == _dump(tree), 'v2_inverse_worker_AST')
    namespace = {}
    exec(compile(ast.fix_missing_locations(changed), __file__, 'exec'), namespace)
    return namespace['worker'].__code__, hashlib.sha256(_dump(tree).encode()).hexdigest()


def _clone(function, namespace, *, code=None):
    result = FunctionType(function.__code__ if code is None else code, namespace,
        function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def write(path, value):
    if Path(path).name == 'plan.json':
        value = {**value, 'candidate_integration_source_proof': source_proof(),
            'binder_v2_source_proof': candidate_binding.source_proof(),
            'required_wiring_pure': _wiring_references(),
            'description_schema_limit': 'BoundFutureRequest retains its v1 outer description; inner RequestStaticProof and explicit candidate provenance identify static-float encoding v2. This is not a new model or actual acceptance.',
            'failed_v1_preserved': {name: ref(FAILED/name) for name in FAILED_PINS}}
    return original.write(path, value)


def check_plan(output, plan):
    _check_plan(output, plan)
    require(plan['candidate_integration_source_proof'] == source_proof()
        and plan['binder_v2_source_proof'] == candidate_binding.source_proof(), 'v2_plan_source_proof')
    require(plan['failed_v1_preserved'] == {name: ref(FAILED/name) for name in FAILED_PINS}, 'v2_failure_binding')
    require(plan['required_wiring_pure'] == _wiring_references(), 'v2_required_wiring_pure')
    evidence = wiring_pure_gate()
    require(all(plan['evidence_sha256'].get(path) == digest for path, digest in evidence.items()), 'v2_wiring_evidence_not_optional')


_WORKER_CODE, _WORKER_SOURCE = worker_code()
_REPLACEMENTS = {'BOOT': BOOT, 'MODULE': MODULE, 'SCHEMA': SCHEMA,
    'source_files': source_files, 'driver_pure_gate': driver_pure_gate,
    'write': write, 'check_plan': check_plan}
_NAMESPACE = {**vars(original), **_REPLACEMENTS}
_check_plan = _clone(original.check_plan, _NAMESPACE)
prepare = _clone(original.prepare, _NAMESPACE)
parent = _clone(original.parent, _NAMESPACE)
worker = _clone(original.worker, _NAMESPACE, code=_WORKER_CODE)
_NAMESPACE.update(prepare=prepare, parent=parent, worker=worker)
_main = _clone(original.main, _NAMESPACE)


def source_proof():
    _, source = worker_code()
    require(source == _WORKER_SOURCE, 'v2_worker_source_changed')
    allowed = {*_REPLACEMENTS, 'prepare', 'parent', 'worker'}
    require(set(_NAMESPACE) == set(vars(original))
        and all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in allowed), 'v2_complete_private_globals')
    require(all(_NAMESPACE[k] is v for k, v in _REPLACEMENTS.items())
        and _NAMESPACE['prepare'] is prepare and _NAMESPACE['parent'] is parent
        and _NAMESPACE['worker'] is worker, 'v2_declared_private_replacements')
    for actual, reference in ((_check_plan, original.check_plan), (prepare, original.prepare),
                              (parent, original.parent), (_main, original.main)):
        require(actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
            and actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
            and actual.__globals__ is _NAMESPACE, 'v2_exact_unmodified_orchestration')
    require(worker.__code__ is _WORKER_CODE and worker.__defaults__ is original.worker.__defaults__
        and worker.__kwdefaults__ is original.worker.__kwdefaults__ and worker.__closure__ is original.worker.__closure__
        and worker.__globals__ is _NAMESPACE, 'v2_worker_exact_compiled_binding')
    return {'schema': SCHEMA, 'original_worker_AST_sha256': _WORKER_SOURCE,
        'worker_changes': ['candidate import v2', 'explicit v2 adapter source proof in report'],
        'inverse_worker_AST': True, 'whole_owned_parent_and_main_unchanged': True,
        'probe_monitor_cleanup_complete_proof_bytes_unchanged': True,
        'shared_seconds': 120., 'original_one_bind_one_warm_scope': original.fixed_scope(),
        'frozen_v1_failure_preserved': True, 'actual_v2_dependency_acceptance_pending': True}


def main():
    source_proof()
    return _main()


if __name__ == '__main__':
    raise SystemExit(main())
