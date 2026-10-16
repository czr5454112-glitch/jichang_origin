"""New campaign wiring and failed-worker tests; no native/model/C loading."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_single_capture_campaign as c
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_single_capture_campaign as launch
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_single_capture_campaign as v


def test_exact_branch_code_full_globals_and_only_four_live_plus_schema():
    proof = c.source_proof()
    assert proof['branch_changed_globals'] == sorted(['CapturedRequest', 'FixedDefaultRequest',
        'run_continuation', 'call_with_recorded_collection', 'SCHEMA'])
    old = c.previous.run_branch
    changed = {name for name in old.__globals__ if c.run_branch.__globals__[name] is not old.__globals__[name]}
    assert changed == set(proof['branch_changed_globals'])
    assert c.run_branch.__code__ is old.__code__ and c.run_branch.__closure__ is old.__closure__
    assert c.run_branch.__defaults__ is old.__defaults__
    assert c.run_branch.__kwdefaults__ is old.__kwdefaults__
    assert set(c.run_branch.__globals__) == set(old.__globals__)
    assert c.run_branch.__globals__['_make_client'] is c.previous.integrated.make_client


@pytest.mark.parametrize('name', ['CapturedRequest', 'FixedDefaultRequest', 'run_continuation',
    'call_with_recorded_collection', 'SCHEMA', 'close_predictor'])
def test_branch_changed_or_missing_binding_rejected(monkeypatch, name):
    monkeypatch.setitem(c.run_branch.__globals__, name, object())
    with pytest.raises(ValueError, match='single_capture_branch_namespace'):
        c.source_proof()


def test_A_initial_final_B_same_fresh_wrapper_and_original_MRO():
    i = c.integrated
    proof = i.integration_proof()
    assert proof['A_initial_A_final_B_same_fresh_wrapper']
    assert proof['constructor_class_cell_and_exact_native_checks_preserved']
    assert c.FixedDefaultRequest.collect is c.CapturedRequest.collect is i.COLLECT
    assert c.FixedDefaultRequest.final_revalidate_and_submit is i.FINAL_REVALIDATE
    assert c.FixedDefaultRequest.choose is c.previous.FixedDefaultRequest.choose
    assert i.COLLECT.__globals__['old'].call_with_recorded_collection is c.call_with_recorded_collection
    assert i.FINAL_REVALIDATE.__globals__['call_with_recorded_collection'] is c.call_with_recorded_collection
    assert c.call_with_recorded_collection.__globals__['captured_collection'] is i.single.captured_collection
    assert proof['collection']['prototype_campaign_installed_field_is_historical_not_current_wiring']
    assert not proof['collection']['actual_campaign_ready']


def test_exact_worker_import_and_one_postwrite_status_gate_inverse_AST():
    proof = c.source_proof()
    assert proof['original_worker_inverse_AST_exact']
    assert proof['changed_import_sites'] == proof['post_saved_verification_status_gates'] == 1
    assert proof['invalid_saved_audit_cannot_write_completed_receipt']
    assert c.worker.__globals__['run_branch'] is c.run_branch
    assert c.worker.__globals__['verify_plan'] is c.verify_plan
    assert c.main.__globals__['worker'] is c.worker
    assert c.worker.__globals__['SAVED_PASSED'] == 'passed_saved_with_complete_unknown_denominator'


def worker_fixture(tmp_path, monkeypatch, report):
    writes, seen = {}, []
    class Accepted:
        _closed = False
        def close(self):
            seen.append('acceptance_close'); return {'test_only': 'closed'}
    plan = {'rows': {}, 'row_order': [], 'native_contract_reference': {'path': 'not_loaded'}, 'semantic_gate_reference': {},
        'image': {'path': 'not_loaded', 'version': 'not_loaded'}}
    def predictor(*args, **kwargs):
        seen.append('construction_refused'); raise ValueError('functional_stub_no_predictor')
    def checked(output, expected):
        seen.append('actual_new_verifier_import')
        assert 'predictor_lifetime.json' in writes and 'run_acceptance.json' in writes
        if isinstance(report, BaseException): raise report
        return deepcopy(report)
    monkeypatch.setattr(v, 'verify_saved', checked)
    fake_public = SimpleNamespace(run_admission=SimpleNamespace(open_run=lambda *a: Accepted()),
        load_native=lambda _: object())
    function = c.integrated.private(c.worker, {'verify_plan': lambda *a: plan,
        'check_loaded_sources': lambda *a: [], 'reference': lambda path: {'path': str(path)},
        'read': lambda _: {'binary': 'not_loaded'},
        'write': lambda path, value: writes.__setitem__(path.name, deepcopy(value)),
        'public': fake_public, 'InitialOwnerClient': predictor})
    return lambda: function(tmp_path, 'synthetic-plan'), writes, seen


def test_actual_worker_new_import_preserves_setup_failure_and_cleanup(tmp_path, monkeypatch):
    invoke, writes, seen = worker_fixture(tmp_path, monkeypatch, ValueError('new_import_reached'))
    with pytest.raises(ValueError, match='new_import_reached'): invoke()
    assert seen == ['construction_refused', 'acceptance_close', 'actual_new_verifier_import']
    assert writes['predictor_lifetime.json']['status'] == 'unknown_predictor_construction'
    assert 'worker_setup_or_loop_failure' in writes['predictor_lifetime.json']
    assert 'verification.json' not in writes and 'receipt.json' not in writes


@pytest.mark.parametrize('status', ['failed_saved_audit', 'passed', None, 'unknown'])
def test_failed_saved_status_saved_then_rejected_before_completed_receipt(tmp_path, monkeypatch, status):
    report = {'status': status, 'rows': {'retained': {'status': 'invalid'}}}
    invoke, writes, _ = worker_fixture(tmp_path, monkeypatch, report)
    with pytest.raises(ValueError, match='single_capture_saved_audit_not_passed'): invoke()
    assert writes['verification.json'] == report and 'receipt.json' not in writes


def test_verified_unknowns_do_not_prevent_saved_cohort_receipt(tmp_path, monkeypatch):
    report = {'status': c.SAVED_PASSED, 'closed_roots': 0, 'open_or_unknown_roots': 18}
    invoke, writes, _ = worker_fixture(tmp_path, monkeypatch, report)
    invoke()
    assert writes['verification.json'] == report
    assert writes['receipt.json']['status'] == 'completed_finite_request_cohort'
    assert 'never all roots succeeded' in writes['receipt.json']['timing']


def test_already_aborted_predictor_cleanup_preserves_ledger_without_second_RPC():
    events = [{'sequence': 0, 'status': 'failed'}]
    class Predictor:
        closed = True
        ledger = events
        process = SimpleNamespace(poll=lambda: 1)
        def close(self): raise AssertionError('must_not_close_aborted_RPC')
        def abort(self): raise AssertionError('must_not_repeat_abort')
    out = c.close_predictor(Predictor())
    assert c.close_predictor is c.previous.close_predictor
    assert out['status'] == 'unknown_already_aborted' and out['ledger'] == events
    assert out['ledger'] is not events and out['process_exit_code'] == 1
    assert out['cleanup_finished_ns'] >= out['close_attempt_started_ns'] >= 0


def test_original_inputs_policy_clock_and_owned600_launcher_unchanged():
    assert c.declarations() == c.previous.declarations() and len(c.declarations()) == 18
    assert c.scene is c.previous.scene and c.FAULTS is c.previous.FAULTS and c.ARMS is c.previous.ARMS
    assert c.contract.BUDGET_NS == 100_000_000 and c.LIMIT == launch.LIMIT == 600.
    assert c.request is c.previous.request and c.publish_root is c.previous.publish_root
    assert c.previous.run_branch.__globals__['CapturedRequest'] is c.previous.CapturedRequest
    assert launch.main.__code__ is launch.old.main.__code__
    assert launch.main.__closure__ is launch.old.main.__closure__
    assert launch.main.__globals__['MODULE'].endswith('.initial_owner_route_single_capture_campaign')
    assert launch.main.__globals__['bounded_windows_job'] is launch.old.bounded_windows_job
    assert launch.main.__globals__['BOOT'] == launch.BOOT


def source_fixture(tmp_path, monkeypatch, archive_kind):
    monkeypatch.setattr(c, 'ROOT', tmp_path)
    source = tmp_path/'a.py'; source.write_text('retained bytes\n')
    saved = tmp_path/'source/a.py'; saved.parent.mkdir(); saved.write_bytes(source.read_bytes())
    digest = c.sha(source)
    if archive_kind == 'absolute_map':
        sources, archive = {str(source): digest}, {str(source): 'source/a.py'}
    elif archive_kind == 'relative_map':
        sources, archive = {'a.py': digest}, {'a.py': str(saved)}
    else: sources, archive = {'a.py': digest}, str(saved.parent)
    plan = tmp_path/'reference.json'
    plan.write_text(json.dumps({'source_sha256': sources, 'source_archive': archive}))
    return c.reference(plan), {str(source): digest}, source, saved, plan


@pytest.mark.parametrize('kind', ['absolute_map', 'relative_map', 'root_directory'])
def test_source_reference_exact_current_archive_and_campaign_subset(tmp_path, monkeypatch, kind):
    ref, sources, *_ = source_fixture(tmp_path, monkeypatch, kind)
    assert c.source_reference(ref, 1, sources)['sources'] == 1


@pytest.mark.parametrize('mutation', ['live', 'archive', 'reference', 'count', 'campaign_missing', 'campaign_changed'])
def test_source_reference_drift_or_missing_domain_rejected(tmp_path, monkeypatch, mutation):
    ref, sources, source, saved, plan = source_fixture(tmp_path, monkeypatch, 'relative_map')
    count = 1
    if mutation == 'live': source.write_text('changed')
    elif mutation == 'archive': saved.write_text('changed')
    elif mutation == 'reference': plan.write_text('{}')
    elif mutation == 'count': count = 2
    elif mutation == 'campaign_missing': sources.clear()
    else: sources[str(source)] = '0'*64
    with pytest.raises(ValueError): c.source_reference(ref, count, sources)


def test_explicit_frozen_domains_and_verifier_pure_references():
    assert c.SOURCE_DOMAINS == {'frozen_entry_codec_campaign': 169, 'frozen_codec_plan': 135,
        'single_capture_integration_source': 153, 'single_capture_endpoint_source': 131}
    assert {'single_capture_verifier_source', 'single_capture_verifier_pure',
        'single_capture_campaign_pure'} <= set(c.REFERENCES)
