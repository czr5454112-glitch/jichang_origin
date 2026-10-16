"""Synthetic v3 evidence/wiring cases; no real proof, model, native or C."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import FunctionType, SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from scripts.experiments.g31_ics_circulation import diagnose_bound_source_proof_bind_v3 as subject


def clone(function, **replacements):
    namespace = {**function.__globals__, **replacements}
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def parser_fixture():
    """Rehashed malformed-record domain, without loading any real evidence."""
    root = Path('synthetic_root').resolve()
    output = root/'pure'; wrapper = root/'wrapper.ps1'; stdlib = root/'stdlib.py'
    keys = subject.PURE_SOURCE_KEYS
    digest = lambda path: hashlib.sha256(str(path).encode()).hexdigest()
    ref = lambda path: {'path': str(path), 'sha256': digest(path)}
    command = [sys.executable, '-m', subject.PURE_MODULE, '--output', str(output)]
    source = {key: hashlib.sha256(key.encode()).hexdigest() for key in keys}
    plan = {'schema': 'g31.bound_source_proof.synthetic_pure.v1', 'tests': [subject.PURE_TEST],
        'expected_tests': 42, 'output_directory': str(output), 'shared_seconds': 120.,
        'environment': {'python': sys.executable, 'sha256': digest(sys.executable)},
        'runner_source_proof': {'synthetic_proof': True}, 'source_sha256': source,
        'source_archive': {key: 'source/' + key for key in keys}}
    loaded = {key: source[key] for key in (subject.PURE_TEST,
        'scripts/experiments/g31_ics_circulation/live_obligation_bound_source_proof_v3.py')}
    receipt = {'status': 'passed', 'tests': 42, 'expected_tests': 42, 'pytest_exitcode': 0,
        'source_changed': [], 'blocked_real_calls': [], 'monitor_active_after_tests': True,
        'real_original_proof_calls': 0, 'model_entry_calls': 0, 'native_calls': 0, 'custom_data_C_loads': 0,
        'plan_sha256': digest(output/'plan.json'), 'XML_sha256': digest(output/'tests.xml'),
        'loaded_entry': dict(loaded), 'loaded_exit': dict(loaded), 'loaded_exit_final': dict(loaded)}
    bounded = {'receipt_sha256': digest(output/'receipt.json'), 'command': command,
        'status': 'passed', 'shared_seconds': 120., 'output_directory': str(output),
        'process': {'status': 'exited', 'exitcode': 0, 'pid': 19,
            'windows_job_kill_on_close': True, 'child_released_only_after_job_assignment': True}}
    expected = {str(wrapper): digest(wrapper), sys.executable: digest(sys.executable)}
    expected.update({str(root/key): value for key, value in source.items()})
    expected[str(stdlib)] = 'stdlib_hash'
    external = {'schema': 'g31.bound_source_proof.v3_pure_external.v1',
        'status': 'passed42_synthetic_with_external_bound', 'command': command,
        'cwd': str(root), 'output_directory': str(output), 'launched': True,
        'exitcode': 0, 'wrapper_exitcode': 0, 'stopwatch_frequency': 10,
        'elapsed_ticks': 100, 'external_application_seconds': 10., 'shared_limit_seconds': 120.,
        'clock_scope': 'immediately_before_python_launch_through_process_return',
        'outputs': {name: ref(output/name) for name in subject.PURE_OUTPUTS},
        'expected_pins': dict(expected), 'pins_before': dict(expected), 'pins_after': dict(expected)}
    documents = {'plan.json': plan, 'receipt.json': receipt,
        'bounded_parent_receipt.json': bounded, 'external_application_wall.json': external}
    xml = ET.Element('testsuite')
    for index in range(42):
        ET.SubElement(xml, 'testcase', {'name': str(index)})
    events = []
    archive = SimpleNamespace(relative_python=Path,
        verify_archive=lambda *args: events.append(('archive', args)))
    parser = clone(subject._parse_pure42, ROOT=root, WIRING_PURE=output,
        WIRING_MODULE=subject.PURE_MODULE, WIRING_TEST=subject.PURE_TEST,
        WIRING_WRAPPER=wrapper, WIRING_OUTPUTS=subject.PURE_OUTPUTS,
        STDLIB_PATH=stdlib, STDLIB_SHA256='stdlib_hash', PURE_SOURCE_KEYS=keys,
        sha=digest, ref=ref, read=lambda path: documents[Path(path).name],
        source_proof=lambda: {'synthetic_proof': True}, archive=archive,
        ET=SimpleNamespace(parse=lambda path: ET.ElementTree(xml)))
    return parser, documents, xml, events


def test_source_proof_exact_old_orchestration_and_inverse_parsers():
    proof = subject.source_proof()
    assert proof['inverse_worker_AST'] and proof['inverse_complete_pure42_parser_AST']
    assert proof['original_pure8_verifier_unchanged_and_mandatory']
    assert subject._NAMESPACE['probe'] is subject.original.probe
    assert subject._NAMESPACE['CallMonitor'] is subject.original.CallMonitor
    assert subject._NAMESPACE['fixed_scope'] is subject.original.fixed_scope
    assert proof['original_one_bind_one_warm_scope'] == subject.original.fixed_scope()


@pytest.mark.parametrize('namespace,key', (('_NAMESPACE', 'probe'), ('_PARSER_NAMESPACE', 'require')))
def test_private_global_replacement_rejects(monkeypatch, namespace, key):
    monkeypatch.setitem(getattr(subject, namespace), key, lambda *args: None)
    with pytest.raises(ValueError, match='complete_private'):
        subject.source_proof()


def test_instantiated_full_parser_accepts_exact42_and_calls_archive():
    parser, documents, xml, events = parser_fixture()
    evidence = parser()
    assert len(xml) == 42 and events and events[0][0] == 'archive'
    output = parser.__globals__['WIRING_PURE']
    for name in subject.PURE_OUTPUTS:
        path = str(output/name)
        assert path in evidence
        assert evidence[path] == parser.__globals__['sha'](output/name)


@pytest.mark.parametrize('mutation', (
    'count8', 'count_bool', 'unknown_receipt', 'native_call', 'monitor_off', 'loaded_missing',
    'loaded_drift', 'loaded_shrink', 'unowned', 'timeout', 'fractional_ticks',
    'wrapper_failure', 'missing_stdlib_output', 'stdlib_pin_drift', 'wrong_command',
    'bad_XML', 'missing_XML', 'runner_proof_mismatch',
))
def test_parser_rejects_rehashed_malformed_evidence(mutation):
    parser, docs, xml, _ = parser_fixture()
    plan, receipt, bounded, ext = (docs[name] for name in
        ('plan.json', 'receipt.json', 'bounded_parent_receipt.json', 'external_application_wall.json'))
    if mutation == 'count8': plan['expected_tests'] = 8
    elif mutation == 'count_bool': receipt['tests'] = True
    elif mutation == 'unknown_receipt': receipt['status'] = 'unknown'
    elif mutation == 'native_call': receipt['native_calls'] = 1
    elif mutation == 'monitor_off': receipt['monitor_active_after_tests'] = False
    elif mutation == 'loaded_missing': receipt['loaded_entry'] = {}
    elif mutation == 'loaded_drift': receipt['loaded_exit'][subject.PURE_TEST] = 'changed'
    elif mutation == 'loaded_shrink': receipt['loaded_exit_final'] = {}
    elif mutation == 'unowned': bounded['process']['windows_job_kill_on_close'] = False
    elif mutation == 'timeout': ext['elapsed_ticks'] = 1201; ext['external_application_seconds'] = 120.1
    elif mutation == 'fractional_ticks': ext['elapsed_ticks'] = 100.
    elif mutation == 'wrapper_failure': ext['wrapper_exitcode'] = 1
    elif mutation == 'missing_stdlib_output': del ext['outputs']['stdlib_fixture/__future__.py']
    elif mutation == 'stdlib_pin_drift':
        key = next(key for key in ext['pins_after'] if key.endswith('stdlib.py'))
        ext['pins_after'][key] = 'changed'
    elif mutation == 'wrong_command': ext['command'] = ['different']
    elif mutation == 'bad_XML': ET.SubElement(xml[0], 'error')
    elif mutation == 'missing_XML': xml.remove(xml[-1])
    elif mutation == 'runner_proof_mismatch': plan['runner_source_proof'] = {'wrong': True}
    with pytest.raises(ValueError):
        parser()


@pytest.mark.parametrize('mutation', ('plan_fixture', 'receipt_fixture', 'fixture_error', 'binder', 'adapter'))
def test_additional_stdlib_and_candidate_guards_do_not_trust_fixture_label(mutation):
    fixture = {'path': 'synthetic_stdlib', 'sha256': 'exact', 'archive': 'stdlib_fixture/__future__.py', 'archive_sha256': 'exact'}
    plan = {'stdlib_feature_fixture': dict(fixture), 'binder_v3_source_proof': {'binder': 3}, 'future_adapter_v3_source_proof': {'adapter': 3}}
    receipt = {'stdlib_feature_fixture_exit': dict(fixture)}
    if mutation == 'plan_fixture': plan['stdlib_feature_fixture']['sha256'] = 'bad'
    elif mutation == 'receipt_fixture': receipt['stdlib_feature_fixture_exit']['archive_sha256'] = 'bad'
    elif mutation == 'fixture_error': receipt['stdlib_feature_fixture_error'] = 'retained failure'
    elif mutation == 'binder': plan['binder_v3_source_proof'] = {'binder': 2}
    elif mutation == 'adapter': plan['future_adapter_v3_source_proof'] = {'adapter': 2}
    function = clone(subject.pure_gate, PURE_PINS={}, sha=lambda path: subject.PURE_WRAPPER_SHA256,
        _parse_pure42=lambda: {}, read=lambda path: plan if Path(path).name == 'plan.json' else receipt,
        _stdlib_fixture=lambda output: fixture,
        candidate_binding=SimpleNamespace(source_proof=lambda: {'adapter': 3},
            binding=SimpleNamespace(source_proof=lambda: {'binder': 3})))
    with pytest.raises(ValueError):
        function()


def test_old_evidence_including_eight_is_called_unchanged_and_v2_failure_retained():
    events = []
    previous = SimpleNamespace(driver_pure_gate=lambda: events.append('old15_25_8') or {'old8': 'exact'})
    fn = clone(subject.driver_pure_gate, previous=previous,
        pure_gate=lambda: (None, {'new42': 'exact'}), FAILED_V2_PINS={'report.json': 'retained'},
        sha=lambda path: 'retained', read=lambda path: {
            'status': 'unknown_failed_actual_dependency_domain',
            'calls': {'original_source_proof_calls': 0, 'private_proof_calls': 0, 'blocked_model_calls': []}})
    result = fn()
    assert events == ['old15_25_8'] and result['old8'] == result['new42'] == 'exact'


def test_first_plan_write_has_all_final_v3_fields_before_verify(tmp_path, monkeypatch):
    events = []
    failure = tmp_path/'failure'; failure.mkdir()
    for name in set(subject.previous.FAILED_PINS) | set(subject.FAILED_V2_PINS):
        (failure/name).write_text('retained\n', encoding='utf8')
    old_refs, new_refs = {'eight': True}, {'forty_two': True}
    fixture = {'fixture': 'exact'}
    write = clone(subject.write, source_proof=lambda: {'driver': 3},
        previous=SimpleNamespace(_wiring_references=lambda: old_refs,
            FAILED=failure, FAILED_PINS=subject.previous.FAILED_PINS),
        FAILED_V2=failure, _pure_references=lambda: new_refs,
        _stdlib_fixture=lambda output, create: events.append(('fixture', create)) or fixture)
    def checked_write(path, value):
        write(path, value); events.append(('write', path.name))
    def checked_plan(output, plan):
        events.append(('check', 'plan.json'))
        assert plan['required_wiring_pure'] == old_refs and plan['required_v3_pure'] == new_refs
        assert plan['stdlib_feature_fixture'] == fixture
        assert plan['candidate_integration_source_proof'] == {'driver': 3}
        assert plan['binder_v3_source_proof'] == subject.candidate_binding.binding.source_proof()
        assert plan['future_adapter_v3_source_proof'] == subject.candidate_binding.source_proof()
        assert json.loads((output/'plan.json').read_text(encoding='utf8')) == plan
    def archive_sources(root, output, files):
        target = output/'source'; target.mkdir()
        for name, raw in files.items(): (target/name).write_bytes(raw)
        return {name: 'source/' + name for name in files}
    prepared = clone(subject.prepare,
        archive=SimpleNamespace(no_execution_extensions=lambda **kwargs: None, archive_sources=archive_sources),
        prior_gate=lambda: ({}, {}, b'{"target":true}'), driver_pure_gate=lambda: {'new42': 'exact'},
        source_files=lambda: {'synthetic.py': b'x=1\n'}, write=checked_write, check_plan=checked_plan)
    output = tmp_path/'new'; prepared(output)
    assert events == [('fixture', True), ('write', 'plan.json'), ('check', 'plan.json'), ('write', 'ready.json')]
    ready = json.loads((output/'ready.json').read_text(encoding='utf8'))
    assert ready['execute_command'][2] == subject.MODULE
    assert ready['execute_command'][-1] == hashlib.sha256((output/'plan.json').read_bytes()).hexdigest()


def test_every_actual_check_requires_new42_evidence_and_original_checks():
    events = []
    references = {'old': True}; new = {'new': True}; fixture = {'bytes': True}
    previous = SimpleNamespace(_wiring_references=lambda: references, FAILED_PINS={}, FAILED=Path('old'))
    fn = clone(subject.check_plan, _check_plan=lambda *args: events.append('original'),
        source_proof=lambda: {'driver': 3},
        candidate_binding=SimpleNamespace(source_proof=lambda: {'adapter': 3}, binding=SimpleNamespace(source_proof=lambda: {'binder': 3})),
        previous=previous, _pure_references=lambda: new, _stdlib_fixture=lambda output: fixture,
        FAILED_V2_PINS={}, driver_pure_gate=lambda: events.append('all_required') or {'new42': 'exact'})
    plan = {'candidate_integration_source_proof': {'driver': 3}, 'binder_v3_source_proof': {'binder': 3},
        'future_adapter_v3_source_proof': {'adapter': 3}, 'required_wiring_pure': references,
        'required_v3_pure': new, 'stdlib_feature_fixture': fixture,
        'failed_v1_preserved': {}, 'failed_v2_preserved': {}, 'evidence_sha256': {}}
    with pytest.raises(ValueError, match='all_pure_evidence_mandatory'):
        fn(Path('output'), plan)
    assert events == ['original', 'all_required']
    plan['evidence_sha256']['new42'] = 'exact'
    fn(Path('output'), plan)
