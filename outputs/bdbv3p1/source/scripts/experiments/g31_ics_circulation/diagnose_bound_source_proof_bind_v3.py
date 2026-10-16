"""Source-only v3 wiring for the unchanged one-cold/one-warm dependency gate.

The old eight-case evidence parser remains mandatory and unchanged. The new
42-case parser is a reversible, declared AST instantiation of that parser;
stdlib fixture checks are additional, never a substitute for project closure.
This file does not authorize real binding, a model, native code or custom C.
"""
from __future__ import annotations
import time
BOOT = time.monotonic()
import ast
import copy
import hashlib
import inspect
from pathlib import Path
import textwrap
from types import FunctionType

from . import diagnose_bound_source_proof_bind_v2 as previous
from . import live_obligation_bound_future_fork_v3 as candidate_binding
from . import run_bound_source_proof_v3_pure as pure_runner

original = previous.original
ROOT, archive, codec = original.ROOT, original.archive, original.codec
sha, read, ref, require = original.sha, original.read, original.ref, original.require
MODULE = __package__ + '.diagnose_bound_source_proof_bind_v3'
SCHEMA = 'g31.bound_source_proof.one_bind_one_use.v3'
PURE = ROOT/'outputs/bsv3p1'
PURE_MODULE = __package__ + '.run_bound_source_proof_v3_pure'
PURE_TEST = 'tests/test_g31_circulation_bound_source_proof_v3.py'
PURE_WRAPPER = ROOT/'outputs/invoke_bsv3p1.ps1'
PURE_WRAPPER_SHA256 = '3bffd58a5a4c4787441ba5c042e8012a6977658d0379ec0d7a5f1f62c83fa60e'
PURE_OUTPUTS = (*previous.WIRING_OUTPUTS, pure_runner.STDLIB_ARCHIVE)
PURE_SOURCE_KEYS = (*previous.PURE_SOURCE_KEYS,
    'scripts/experiments/g31_ics_circulation/diagnose_bound_source_proof_bind_v2.py',
    'scripts/experiments/g31_ics_circulation/live_obligation_bound_source_proof_v3.py',
    'scripts/experiments/g31_ics_circulation/live_obligation_bound_future_fork_v3.py',
    PURE_TEST, 'scripts/experiments/g31_ics_circulation/run_bound_source_proof_v3_pure.py')
PURE_PINS = {
    'plan.json': '7f1516c956fe036beac8b2cbdc68b33084ab6389a3cb7832a8b3a5f4967e434b',
    'receipt.json': 'ad2b3bfd17abf1590b3de5fa825ce3b1d418ef6051b038af836dcdc45d1f1c41',
    'tests.xml': 'b3ff936c66ab81054b600e085c1eb7a930bcd8dc6335993d799f88885db51652',
    'bounded_parent_receipt.json': 'ae3bef55bac1b1f9aaa6fc6cfc0ff5fd8d3cf1a776312cb56d2fc3762cbcc4a1',
    'external_application_wall.json': '8e443c5655e2b1be863ecf8ed75b6036ad1e45c2188e90fc3ea0e67e85d216ff',
}
FAILED_V2 = ROOT/'outputs/bdb2'
FAILED_V2_PINS = {
    'report.json': '123317d561f9f0b72ceaef038d8ef249ac760f5aae9dde294e31210c34487934',
    'receipt.json': '48a37a6e8ad0b17a0ec43e34ba04ff566100c51f3e3b152614f5c26e60e1f854',
    'actual.bounded.json': 'fab293bc7de7c6155f68cf9a58ef4bb937f1af4dfcf9473ebd7baa38876bfbd7',
    'external_application_wall.json': '83fb0666946db0fe78163fba4ecc20b0013a642fae98b935356acad1f08ecbfb',
}
_clone, _dump = previous._clone, previous._dump


def _pure_parser_code():
    """Instantiate the complete accepted parser, then prove the exact inverse."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(previous.wiring_pure_gate)))
    constants = {
        (int, 8): 42,
        (str, 'bind_driver_v2_source_proof'): 'runner_source_proof',
        (str, 'scripts/experiments/g31_ics_circulation/diagnose_bound_source_proof_bind_v2.py'):
            'scripts/experiments/g31_ics_circulation/live_obligation_bound_source_proof_v3.py',
        (str, 'g31.bound_source_proof.v2_bind_driver_pure_external.v1'):
            'g31.bound_source_proof.v3_pure_external.v1',
        (str, 'passed8_synthetic_with_external_bound'): 'passed42_synthetic_with_external_bound',
    }
    originals = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)
        and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == 'source_keys']
    require(len(originals) == 1, 'v3_parser_source_keys_once')
    original_keys = originals[0]
    new_keys = ast.parse('source_keys = PURE_SOURCE_KEYS').body[0]
    expected_update = ast.parse("expected.update({str(ROOT/archive.relative_python(name)): plan['source_sha256'][name] for name in source_keys})").body[0]
    stdlib_update = ast.parse("expected[str(STDLIB_PATH)] = STDLIB_SHA256").body[0]
    class Forward(ast.NodeTransformer):
        def __init__(self):
            self.constants = {key: 0 for key in constants}; self.keys = 0; self.stdlib = 0
        def visit_Constant(self, node):
            key = (type(node.value), node.value)
            if key in constants:
                self.constants[key] += 1
                return ast.copy_location(ast.Constant(value=constants[key]), node)
            return node
        def visit_Assign(self, node):
            if _dump(node) == _dump(original_keys):
                self.keys += 1
                return ast.copy_location(copy.deepcopy(new_keys), node)
            return self.generic_visit(node)
        def visit_Expr(self, node):
            if _dump(node) == _dump(expected_update):
                self.stdlib += 1
                return [copy.deepcopy(node), ast.copy_location(copy.deepcopy(stdlib_update), node)]
            return self.generic_visit(node)
    forward = Forward(); changed = forward.visit(copy.deepcopy(tree))
    require(forward.keys == forward.stdlib == 1
        and list(forward.constants.values()) == [3, 1, 1, 1, 1], 'v3_parser_declared_changes')
    inverse_constants = {(type(value), value): key[1] for key, value in constants.items()}
    class Inverse(ast.NodeTransformer):
        def __init__(self):
            self.keys = 0; self.stdlib = 0
        def visit_Constant(self, node):
            key = (type(node.value), node.value)
            if key in inverse_constants:
                return ast.copy_location(ast.Constant(value=inverse_constants[key]), node)
            return node
        def visit_Assign(self, node):
            if _dump(node) == _dump(new_keys):
                self.keys += 1
                return ast.copy_location(copy.deepcopy(original_keys), node)
            if _dump(node) == _dump(stdlib_update):
                self.stdlib += 1
                return None
            return self.generic_visit(node)
    inverse = Inverse(); restored = inverse.visit(copy.deepcopy(changed))
    require(inverse.keys == inverse.stdlib == 1 and _dump(restored) == _dump(tree), 'v3_inverse_complete_pure_parser')
    namespace = {}
    exec(compile(ast.fix_missing_locations(changed), __file__, 'exec'), namespace)
    return namespace['wiring_pure_gate'].__code__, hashlib.sha256(_dump(tree).encode()).hexdigest()


_PARSER_CODE, _PARSER_SOURCE = _pure_parser_code()
_PARSER_REPLACEMENTS = {
    'WIRING_PURE': PURE, 'WIRING_MODULE': PURE_MODULE, 'WIRING_TEST': PURE_TEST,
    'WIRING_WRAPPER': PURE_WRAPPER, 'WIRING_OUTPUTS': PURE_OUTPUTS,
    'source_proof': pure_runner.source_proof,
}
_PARSER_ADDITIONS = {'PURE_SOURCE_KEYS': PURE_SOURCE_KEYS,
    'STDLIB_PATH': candidate_binding.binding._FEATURE_PATH,
    'STDLIB_SHA256': candidate_binding.binding.FEATURE_SOURCE_SHA256}
_PARSER_NAMESPACE = {**vars(previous), **_PARSER_REPLACEMENTS, **_PARSER_ADDITIONS}
_parse_pure42 = _clone(previous.wiring_pure_gate, _PARSER_NAMESPACE, code=_PARSER_CODE)


def _stdlib_fixture(output, *, create=False):
    # Exact accepted pure-runner logic: canonical source, byte-equal archive,
    # containment/short path, xb-only creation. It never imports/executes bytes.
    return pure_runner._stdlib(output, create=create)


def pure_gate():
    for name, digest in PURE_PINS.items():
        require(sha(PURE/name) == digest, 'v3_pure_pinned:' + name)
    require(sha(PURE_WRAPPER) == PURE_WRAPPER_SHA256, 'v3_pure_wrapper_pinned')
    evidence = _parse_pure42()
    plan, receipt = read(PURE/'plan.json'), read(PURE/'receipt.json')
    fixture = _stdlib_fixture(PURE)
    require(plan['stdlib_feature_fixture'] == fixture
        and receipt['stdlib_feature_fixture_exit'] == fixture
        and 'stdlib_feature_fixture_error' not in receipt, 'v3_pure_stdlib_complete_binding')
    require(plan['binder_v3_source_proof'] == candidate_binding.binding.source_proof()
        and plan['future_adapter_v3_source_proof'] == candidate_binding.source_proof(), 'v3_pure_candidate_provenance')
    evidence[str(candidate_binding.binding._FEATURE_PATH)] = candidate_binding.binding.FEATURE_SOURCE_SHA256
    evidence.update({str(PURE/name): digest for name, digest in PURE_PINS.items()})
    return plan, evidence


def _pure_references():
    return {'output_directory': str(PURE), 'expected_tests': 42,
        'artifacts': {name: ref(PURE/name) for name in (*PURE_OUTPUTS, 'external_application_wall.json')},
        'wrapper': ref(PURE_WRAPPER)}


def driver_pure_gate():
    # Includes original15, v2 factory25 and the unmodified v2 wiring8 parser.
    evidence = previous.driver_pure_gate()
    _, fresh = pure_gate()
    for name, digest in FAILED_V2_PINS.items():
        require(sha(FAILED_V2/name) == digest, 'v3_failed_v2_pinned:' + name)
        evidence[str(FAILED_V2/name)] = digest
    failure = read(FAILED_V2/'report.json')
    require(failure['status'] == 'unknown_failed_actual_dependency_domain'
        and failure['calls']['original_source_proof_calls'] == 0
        and failure['calls']['private_proof_calls'] == 0
        and failure['calls']['blocked_model_calls'] == [], 'v3_v2_failure_not_accepted')
    return evidence | fresh


def source_files():
    from . import initial_owner_route_image as image
    plan, _ = pure_gate()
    files = {}
    for name, digest in plan['source_sha256'].items():
        raw = (ROOT/archive.relative_python(name)).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == digest, 'v3_inherited_source_bytes:' + name)
        files[name] = raw
    for name, raw in image.source_closure(ROOT, (MODULE,
            'tests.test_g31_circulation_bound_source_proof_bind_v3_driver')).items():
        archive.relative_python(name)
        require(name not in files or files[name] == raw, 'v3_bind_source_collision')
        files[name] = raw
    return dict(sorted(files.items()))


def worker_code():
    # Reuse the exact reviewed v2 AST transform, including its inverse proof;
    # only the destination import string changes. Original worker is unchanged.
    tree = ast.parse(textwrap.dedent(inspect.getsource(previous.worker_code)))
    old = 'from . import live_obligation_bound_future_fork_v2 as candidate'
    new = 'from . import live_obligation_bound_future_fork_v3 as candidate'
    class Replace(ast.NodeTransformer):
        def __init__(self, before, after):
            self.before, self.after, self.count = before, after, 0
        def visit_Constant(self, node):
            if type(node.value) is str and node.value == self.before:
                self.count += 1
                return ast.copy_location(ast.Constant(value=self.after), node)
            return node
    forward = Replace(old, new); changed = forward.visit(copy.deepcopy(tree))
    inverse = Replace(new, old); restored = inverse.visit(copy.deepcopy(changed))
    require(forward.count == inverse.count == 1 and _dump(restored) == _dump(tree), 'v3_worker_transform_exact_inverse')
    namespace = dict(vars(previous))
    exec(compile(ast.fix_missing_locations(changed), __file__, 'exec'), namespace)
    return namespace['worker_code']()


def write(path, value):
    if Path(path).name == 'plan.json':
        value = {**value, 'candidate_integration_source_proof': source_proof(),
            'binder_v3_source_proof': candidate_binding.binding.source_proof(),
            'future_adapter_v3_source_proof': candidate_binding.source_proof(),
            'required_wiring_pure': previous._wiring_references(),
            'required_v3_pure': _pure_references(),
            'stdlib_feature_fixture': _stdlib_fixture(Path(path).parent, create=True),
            'failed_v1_preserved': {name: ref(previous.FAILED/name) for name in previous.FAILED_PINS},
            'failed_v2_preserved': {name: ref(FAILED_V2/name) for name in FAILED_V2_PINS},
            'description_schema_limit': 'The outer BoundFutureRequest description remains v1; explicit binder/adapter v3 provenance adds only canonical static __future__.annotations support. This is not a new model or accepted real dependency domain.'}
    return original.write(path, value)


def check_plan(output, plan):
    _check_plan(output, plan)
    require(plan['candidate_integration_source_proof'] == source_proof()
        and plan['binder_v3_source_proof'] == candidate_binding.binding.source_proof()
        and plan['future_adapter_v3_source_proof'] == candidate_binding.source_proof(), 'v3_plan_source_proof')
    require(plan['required_wiring_pure'] == previous._wiring_references()
        and plan['required_v3_pure'] == _pure_references(), 'v3_mandatory_8_and_42_references')
    require(plan['stdlib_feature_fixture'] == _stdlib_fixture(output), 'v3_plan_stdlib_source_archive')
    require(plan['failed_v1_preserved'] == {name: ref(previous.FAILED/name) for name in previous.FAILED_PINS}
        and plan['failed_v2_preserved'] == {name: ref(FAILED_V2/name) for name in FAILED_V2_PINS}, 'v3_failures_preserved')
    evidence = driver_pure_gate()
    require(all(plan['evidence_sha256'].get(path) == digest for path, digest in evidence.items()), 'v3_all_pure_evidence_mandatory')


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
    _, parser_source = _pure_parser_code()
    require(parser_source == _PARSER_SOURCE, 'v3_pure_parser_source_changed')
    require(set(_PARSER_NAMESPACE) == set(vars(previous)) | set(_PARSER_ADDITIONS)
        and all(_PARSER_NAMESPACE[k] is v for k, v in vars(previous).items()
            if k not in _PARSER_REPLACEMENTS and k not in _PARSER_ADDITIONS)
        and all(_PARSER_NAMESPACE[k] is v for k, v in (_PARSER_REPLACEMENTS | _PARSER_ADDITIONS).items()),
        'v3_complete_private_parser_globals')
    require(_parse_pure42.__code__ is _PARSER_CODE and _parse_pure42.__globals__ is _PARSER_NAMESPACE
        and _parse_pure42.__defaults__ is previous.wiring_pure_gate.__defaults__
        and _parse_pure42.__kwdefaults__ is previous.wiring_pure_gate.__kwdefaults__
        and _parse_pure42.__closure__ is previous.wiring_pure_gate.__closure__, 'v3_parser_compiled_binding')
    _, source = worker_code()
    require(source == _WORKER_SOURCE, 'v3_worker_source_changed')
    allowed = {*_REPLACEMENTS, 'prepare', 'parent', 'worker'}
    require(set(_NAMESPACE) == set(vars(original))
        and all(_NAMESPACE[k] is v for k, v in vars(original).items() if k not in allowed)
        and all(_NAMESPACE[k] is v for k, v in _REPLACEMENTS.items())
        and _NAMESPACE['prepare'] is prepare and _NAMESPACE['parent'] is parent
        and _NAMESPACE['worker'] is worker, 'v3_complete_private_globals')
    for actual, reference in ((_check_plan, original.check_plan), (prepare, original.prepare),
                              (parent, original.parent), (_main, original.main)):
        require(actual.__code__ is reference.__code__ and actual.__defaults__ is reference.__defaults__
            and actual.__kwdefaults__ is reference.__kwdefaults__ and actual.__closure__ is reference.__closure__
            and actual.__globals__ is _NAMESPACE, 'v3_exact_original_orchestration')
    require(worker.__code__ is _WORKER_CODE and worker.__globals__ is _NAMESPACE
        and worker.__defaults__ is original.worker.__defaults__
        and worker.__kwdefaults__ is original.worker.__kwdefaults__
        and worker.__closure__ is original.worker.__closure__, 'v3_worker_compiled_binding')
    return {'schema': SCHEMA, 'original_worker_AST_sha256': _WORKER_SOURCE,
        'original_pure8_parser_AST_sha256': _PARSER_SOURCE,
        'worker_changes': ['candidate import v3', 'explicit adapter source proof in report'],
        'inverse_worker_AST': True, 'inverse_complete_pure42_parser_AST': True,
        'original_pure8_verifier_unchanged_and_mandatory': True,
        'mandatory_v3_42_and_stdlib_fixture': True, 'whole_owned_parent_and_main_unchanged': True,
        'probe_monitor_cleanup_complete_proof_bytes_unchanged': True,
        'shared_seconds': 120., 'original_one_bind_one_warm_scope': original.fixed_scope(),
        'frozen_v1_v2_failures_preserved': True, 'actual_v3_dependency_acceptance_pending': True}


def main():
    source_proof()
    return _main()


if __name__ == '__main__':
    raise SystemExit(main())
