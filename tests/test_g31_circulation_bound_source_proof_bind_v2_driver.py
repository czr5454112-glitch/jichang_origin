"""Synthetic v2 wiring only; no real proof, model, native or C execution."""
import hashlib
import json
from types import FunctionType, SimpleNamespace

import pytest

from scripts.experiments.g31_ics_circulation import diagnose_bound_source_proof_bind_v2 as subject


def clone(function, **replacements):
    namespace = {**function.__globals__, **replacements}
    result = FunctionType(function.__code__, namespace, function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def test_exact_orchestration_and_narrow_worker_provenance():
    before = dict(vars(subject.original))
    proof = subject.source_proof()
    assert proof['inverse_worker_AST'] and proof['whole_owned_parent_and_main_unchanged']
    assert proof['worker_changes'] == ['candidate import v2', 'explicit v2 adapter source proof in report']
    assert subject._NAMESPACE['probe'] is subject.original.probe
    assert subject._NAMESPACE['CallMonitor'] is subject.original.CallMonitor
    assert subject._NAMESPACE['fixed_scope'] is subject.original.fixed_scope
    assert all(vars(subject.original)[k] is value for k, value in before.items())


def test_original_probe_replacement_is_rejected(monkeypatch):
    monkeypatch.setitem(subject._NAMESPACE, 'probe', lambda *args: {})
    with pytest.raises(ValueError, match='complete_private_globals'):
        subject.source_proof()


def test_worker_code_replacement_is_rejected(monkeypatch):
    monkeypatch.setattr(subject.worker, '__code__', (lambda output, expected: 0).__code__)
    with pytest.raises(ValueError, match='worker_exact_compiled_binding'):
        subject.source_proof()


def test_prepare_first_plan_write_is_final_version_before_verification(tmp_path, monkeypatch):
    events = []
    failure = tmp_path/'failed'; failure.mkdir()
    for name in subject.FAILED_PINS:
        (failure/name).write_text('retained failure\n', encoding='utf8')
    monkeypatch.setattr(subject, 'FAILED', failure)
    wiring = {'output_directory': 'synthetic-only', 'expected_tests': 8, 'artifacts': {}, 'wrapper': {}}
    monkeypatch.setattr(subject, '_wiring_references', lambda: wiring)
    output = tmp_path/'new'
    files = {'synthetic.py': b'fixed fixture\n'}
    def archive_sources(root, folder, values):
        mapping = {}
        for name, raw in values.items():
            destination = folder/'source'/name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            mapping[name] = 'source/' + name
        return mapping
    def checked_write(path, value):
        subject.write(path, value)
        events.append(('write', path.name))
    def check_plan(folder, plan):
        events.append(('check', 'plan.json'))
        assert plan['schema'] == subject.SCHEMA
        assert plan['candidate_integration_source_proof'] == subject.source_proof()
        assert plan['binder_v2_source_proof'] == subject.candidate_binding.source_proof()
        assert plan['failed_v1_preserved'] == {name: subject.ref(failure/name) for name in subject.FAILED_PINS}
        assert plan['required_wiring_pure'] == wiring
        assert json.loads((folder/'plan.json').read_text(encoding='utf8')) == plan
    prepared = clone(subject.prepare,
        archive=SimpleNamespace(no_execution_extensions=lambda **kwargs: None, archive_sources=archive_sources),
        prior_gate=lambda: ({}, {'old': 'proof'}, b'{"target":true}'),
        driver_pure_gate=lambda: {'new25': 'proof'}, source_files=lambda: files,
        write=checked_write, check_plan=check_plan)
    prepared(output)
    assert events == [('write', 'plan.json'), ('check', 'plan.json'), ('write', 'ready.json')]
    ready = json.loads((output/'ready.json').read_text(encoding='utf8'))
    assert ready['execute_command'][2] == subject.MODULE
    assert ready['execute_command'][-1] == hashlib.sha256((output/'plan.json').read_bytes()).hexdigest()


@pytest.mark.parametrize('bad_field', ('candidate_integration_source_proof', 'required_wiring_pure', 'evidence_sha256'))
def test_missing_v2_final_plan_provenance_rejects(bad_field, tmp_path):
    events = []
    failure = tmp_path/'failed'; failure.mkdir()
    for name in subject.FAILED_PINS:
        (failure/name).write_text('preserved\n', encoding='utf8')
    expected = {'candidate_integration_source_proof': {'version': 2},
        'binder_v2_source_proof': {'binder': 2},
        'failed_v1_preserved': {name: subject.ref(failure/name) for name in subject.FAILED_PINS},
        'required_wiring_pure': {'eight': True}, 'evidence_sha256': {'pure8': 'required'}}
    fn = clone(subject.check_plan, _check_plan=lambda *args: events.append('original_complete_checks'),
        source_proof=lambda: {'version': 2},
        candidate_binding=SimpleNamespace(source_proof=lambda: {'binder': 2}), FAILED=failure,
        _wiring_references=lambda: {'eight': True}, wiring_pure_gate=lambda: {'pure8': 'required'})
    plan = dict(expected); del plan[bad_field]
    with pytest.raises(KeyError):
        fn(tmp_path, plan)
    assert events == ['original_complete_checks']


def test_fixed_scope_still_one_cold_one_warm_no_model_operations():
    scope = subject.source_proof()['original_one_bind_one_warm_scope']
    assert scope == subject.original.fixed_scope()
    assert scope['cold_bind_requests'] == scope['maximum_original_source_proof_calls'] == scope['warm_facade_proof_uses'] == 1
    assert all(scope[key] == 0 for key in ('fork_calls', 'resume_calls', 'engine_constructions',
        'model_predictions', 'native_calls', 'custom_data_C_loads'))
    assert scope['unsupported_dependency_policy'] == 'unknown_no_retry_no_omission'
