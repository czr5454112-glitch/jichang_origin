"""Fake-only v2 full96 wiring and retained evidence/unknown guards."""
import copy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import pytest
from scripts.experiments.g31_ics_circulation import validate_live_communication_scoped_inputs_v2 as d


def test_outer_worker_all_code_and_globals_except_four():
    function = d.worker_function(); old = d.frozen.worker
    assert function.__code__ is old.__code__ and function.__closure__ is old.__closure__
    assert function.__defaults__ is old.__defaults__ and function.__kwdefaults__ is old.__kwdefaults__
    assert set(function.__globals__) == set(old.__globals__)
    allowed = {'candidate', 'SCHEMA', 'source_proof', 'pure_gate'}
    assert all(function.__globals__[k] is v for k,v in old.__globals__.items() if k not in allowed)
    assert function.__globals__['candidate'] is d.candidate


def test_original_inner_worker_and_all_helpers_unchanged():
    function = d.worker_function()
    for name in ('SaveBeforeReturn', 'run_original', 'early_inventory', 'mapping_allowed', 'exact_predictions', 'loaded_sources'):
        assert function.__globals__[name] is getattr(d.frozen, name)
    sentinel = object(); inner = d.frozen.bind_worker(sentinel)
    assert inner.__code__ is d.frozen.original.worker.__code__
    assert inner.__globals__['model'].predict is sentinel


def test_original_modules_not_mutated():
    before = dict(d.frozen.worker.__globals__); old_candidate = d.frozen.candidate
    d.source_proof(); d.worker_function()
    assert d.frozen.candidate is old_candidate and old_candidate is not d.candidate
    assert all(d.frozen.worker.__globals__[k] is v for k,v in before.items())


def test_source_proof_never_constructs_scope(monkeypatch):
    monkeypatch.setattr(d.candidate, 'PublicInputScope', lambda: pytest.fail('no actual scope'))
    proof = d.source_proof()
    assert proof['fresh_candidate_version'] == 2 and proof['candidate_fresh_scope_each_call']
    assert proof['initial_context_caller_unchanged']


def test_candidate_is_v2_and_every_call_has_fresh_scope(monkeypatch):
    made = []
    class Fake:
        def __init__(self): made.append(self)
        def predict(self, c, a): return (self, c, a)
    monkeypatch.setattr(d.candidate, 'PublicInputScope', Fake)
    first = d.candidate.predict('context', 1); second = d.candidate.predict('context', 2)
    assert first[0] is not second[0] and len(made) == 2
    assert d.candidate.__name__.endswith('_v2')


@pytest.fixture
def synthetic(tmp_path):
    output = tmp_path/'new'; output.mkdir(); previous = tmp_path/'old'; previous.mkdir()
    value = {'completion': {'j': 1.0}, 'projected_collections': []}
    encoded = json.dumps(value, allow_nan=False).encode(); old = {}; rows = {}
    for i,key in enumerate(d.ORDER):
        path = previous/f'{i:03d}.gz'; path.write_bytes(gzip.compress(encoded, mtime=0))
        old[key] = d.ref(path); rows[key] = {'action': {'ordinal': i}}
    plan = {'schema': d.SCHEMA, 'hard_timeout_seconds': d.LIMIT, 'maximum_model_evaluations': 96,
        'source_proof': d.source_proof(), 'environment': {'python': sys.executable, 'sha256': d.sha(sys.executable)},
        'old96_predictions': old, 'rows': rows}
    d.write(output/'plan.json', plan)
    return SimpleNamespace(output=output, plan=plan, value=value, calls=[])


def fake_outer(fixture, *, fail_at=None, receipt_change=None):
    def predict(context, action):
        assert context == 'synthetic-public-context'
        assert action == {'ordinal': len(fixture.calls)}
        fixture.calls.append(copy.deepcopy(action))
        if action['ordinal'] == fail_at: raise RuntimeError('synthetic model failure')
        return copy.deepcopy(fixture.value)
    def inner(saver):
        def run(output, expected):
            rows = {}
            for i,key in enumerate(d.ORDER):
                value = saver('synthetic-public-context', fixture.plan['rows'][key]['action'])
                # This is the simulated caller's first target access point.
                assert Path(saver.records[i]['prediction']['path']).exists()
                assert saver.records[i]['status'] == 'complete_prediction_saved_before_return'
                path = output/f'late_{i:03d}.gz'; path.write_bytes(gzip.compress(json.dumps(value).encode(), mtime=0))
                rows[key] = {'status': 'exact_conformance', 'prediction': d.ref(path),
                    'projected_collection_rows': [], 'actual_collection_rows': []}
            receipt = {'status': 'exact_all96_conformance', 'model_evaluations': 96,
                'actual_collection_data_checks': 226, 'actual_known_collection_data': 192,
                'complete_actual_collection_conformance': True, 'counts': {'exact_conformance': 96}}
            if receipt_change: receipt.update(receipt_change)
            d.write(output/'rows.json', rows); d.write(output/'receipt.json', receipt); d.write(output/'entry_pins.json', {})
        return run
    original_run = d.private(d.frozen.run_original, {'bind_worker': inner})
    return d.private(d.worker_function(), {'candidate': SimpleNamespace(predict=predict),
        'pure_gate': lambda: None, 'loaded_sources': lambda plan: {}, 'run_original': original_run})


def test_full_original_outer_worker_fake96_checks_and_early_mapping(synthetic):
    fake_outer(synthetic)(synthetic.output, d.sha(synthetic.output/'plan.json'))
    final = d.read(synthetic.output/'final_receipt.json')
    assert len(synthetic.calls) == 96 and final['full_output_exact'] == 96
    assert final['actual_collection_data_checks'] == 226 and final['actual_known_collection_data'] == 192
    assert final['early_invocations'] == 96 and final['early_ordinal_mapping_certified']
    assert final['unknown_or_difference'] == 0 and final['GC_enabled']
    assert final['modelspan_includes_early_full_export_hash_journal'] and not final['sample_cleanup_certified']
    assert not final['complete_request_100ms_certified'] and not final['online_executable']


@pytest.mark.parametrize('change', [
    {'actual_collection_data_checks': 225}, {'actual_known_collection_data': 191},
    {'model_evaluations': 95}, {'complete_actual_collection_conformance': False},
    {'status': 'completed_conformance_failed_unknowns_preserved'}])
def test_complete_predictions_cannot_override_missing_original_checks(synthetic, change):
    fake_outer(synthetic, receipt_change=change)(synthetic.output, d.sha(synthetic.output/'plan.json'))
    final = d.read(synthetic.output/'final_receipt.json')
    assert final['full_output_exact'] == 96 and not final['early_ordinal_mapping_certified']
    assert final['early_unbound_invocations'] == 96
    assert final['status'] == 'completed_unknowns_or_differences_preserved'


@pytest.mark.parametrize('fail_at', [0, 7, 95])
def test_partial_exception_has_unbound_ordinals_and_no_final_success(synthetic, fail_at):
    with pytest.raises(RuntimeError, match='synthetic model failure'):
        fake_outer(synthetic, fail_at=fail_at)(synthetic.output, d.sha(synthetic.output/'plan.json'))
    inventory = d.read(synthetic.output/'early_prediction_inventory.json')
    assert len(inventory['records']) == fail_at+1
    assert inventory['records'][-1]['status'] == 'unknown_prediction_or_export_error'
    assert all('key' not in row and 'branch' not in row for row in inventory['records'])
    assert not (synthetic.output/'final_receipt.json').exists()


@pytest.mark.parametrize('changed', [
    {'completion': {'j': 1}, 'projected_collections': []},
    {'completion': {'j': -0.0}, 'projected_collections': []},
    {'projected_collections': [], 'completion': {'j': 1.0}},
    {'completion': {'j': 1.0}, 'projected_collections': [], 'extra': None}])
def test_entire_old_prediction_remains_strict(synthetic, changed):
    key = d.ORDER[0]; path = Path(synthetic.plan['old96_predictions'][key]['path'])
    path.write_bytes(gzip.compress(json.dumps(changed).encode(), mtime=0))
    synthetic.plan['old96_predictions'][key] = d.ref(path)
    (synthetic.output/'plan.json').write_text(json.dumps(synthetic.plan), encoding='utf8')
    fake_outer(synthetic)(synthetic.output, d.sha(synthetic.output/'plan.json'))
    final = d.read(synthetic.output/'final_receipt.json')
    assert final['full_output_exact'] == 95 and final['unknown_or_difference'] == 1
    assert final['status'] == 'completed_unknowns_or_differences_preserved'


@pytest.mark.parametrize('status', ['completed_unknowns_or_differences_preserved', 'unknown_worker_failure', 'invented'])
def test_new_launcher_worker_status_gate_preserves_failed_report(tmp_path, monkeypatch, status):
    d.write(tmp_path/'final_receipt.json', {'status': status})
    monkeypatch.setattr(d, 'worker_function', lambda: lambda *args: None)
    with pytest.raises(ValueError, match='v2_complete_gate'): d.worker(tmp_path, 'x')
    assert d.read(tmp_path/'final_receipt.json')['status'] == status


def test_complete_status_gate_accepts_only_exact(tmp_path, monkeypatch):
    d.write(tmp_path/'final_receipt.json', {'status': 'exact_all96_original_checks_and_full_outputs'})
    monkeypatch.setattr(d, 'worker_function', lambda: lambda *args: None)
    d.worker(tmp_path, 'x')


def test_budget_source_and_initial_caller_do_not_change():
    function = d.worker_function()
    assert d.LIMIT == d.frozen.LIMIT == 360.
    assert function.__globals__['original'] is d.frozen.original
    assert function.__globals__['run_original'].__globals__['bind_worker'] is d.frozen.bind_worker


def test_proof_bound_to_fresh_predictor_code(monkeypatch):
    monkeypatch.setattr(d.candidate, 'predict', lambda c,a: None)
    with pytest.raises(ValueError, match='fresh_candidate_scope'): d.source_proof()


def test_gc_still_refuses_before_any_prediction(tmp_path, monkeypatch):
    monkeypatch.setattr(d.frozen.gc, 'isenabled', lambda: False)
    saver = d.SaveBeforeReturn(tmp_path, lambda *args: pytest.fail('no prediction'))
    try:
        with pytest.raises(ValueError, match='GC_disabled'): saver({}, {})
    finally: saver.close()
    assert saver.records == []
