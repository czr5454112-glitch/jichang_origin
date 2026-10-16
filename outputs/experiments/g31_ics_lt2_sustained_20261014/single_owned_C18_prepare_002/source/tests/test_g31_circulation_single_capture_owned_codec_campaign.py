"""Synthetic source/lifecycle wiring only; never load C/native or a predictor."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from scripts.experiments.g31_ics_circulation import initial_owner_route_single_capture_owned_codec_campaign as c
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_single_capture_owned_codec_campaign as v
from scripts.experiments.g31_ics_circulation import single_capture_owned_codec_runtime as r
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_single_capture_owned_codec_campaign as launch


def test_source_proof_inverse_AST_and_complete_namespace():
    proof = c.source_proof()
    assert proof['original_worker_inverse_AST_exact']
    assert proof['provider_close_after_native_RPC_cleanup_before_saved_audit']
    assert proof['original_branch_call_uses_local_bound_function']
    function = c.worker_function(None, None)
    missing = v.original.previous.previous.missing_globals(function)
    assert missing == []
    assert 'run_branch' in function.__code__.co_varnames
    assert function.__globals__['InitialOwnerClient'] is c.old.worker.__globals__['InitialOwnerClient']


def test_verifier_both_levels_original_checks_and_recursive_globals():
    namespace = v.make_namespace(c)
    proof = namespace.source_proof()
    assert proof['both_root_replay_levels_current_campaign']
    assert all(not x for x in proof['recursive_LOAD_GLOBAL_missing'].values())
    assert namespace.functions['root_replay'].__globals__['c'] is c
    assert namespace.functions['original_root_replay'].__globals__['c'] is c
    assert namespace.namespace['complete_query_replay'] is v.original.previous.complete_query_replay
    assert namespace.functions['original_rpc_scope'].__globals__['c'] is c


def worker_fixture(tmp_path, monkeypatch, report, *, close_error=None, run_row=False):
    calls, writes = [], {}
    class Accepted:
        _closed = False
        def close(self): calls.append('native_acceptance_closed'); self._closed = True; return {}
        def active_for(self, key): return True
        def enter_branch(self, *args): calls.append('enter_branch')
        def finish_branch(self, *args): calls.append('finish_branch')
    class Predictor:
        ready = {}
        command, started_ns, ready_ns = ['fake'], 10, 20
    def construct(*args, **kwargs):
        if run_row: return Predictor()
        calls.append('predictor_construction_refused'); raise RuntimeError('synthetic constructor')
    def branch(*args):
        calls.append('NEW_bound_branch'); return {'synthetic_only': True}
    provider = SimpleNamespace(run_branch=branch)
    def open_provider(plan, directory): calls.append('C_setup_synthetic'); return provider
    def close_provider(obj):
        assert obj is provider
        calls.append('C_close_synthetic')
        if close_error: raise close_error
    def verify(*args):
        calls.append('NEW_saved_verifier')
        assert calls.index('C_close_synthetic') > calls.index('native_acceptance_closed')
        return deepcopy(report)
    monkeypatch.setattr(v, 'verify_saved', verify)
    plan = {'rows': {'one': {}} if run_row else {}, 'row_order': ['one'] if run_row else [],
        'native_contract_reference': {'path': 'not_loaded'}, 'semantic_gate_reference': {},
        'image': {'path': 'not_loaded', 'version': 'fake'}, 'expected_READY': {}}
    function = c.worker_function(open_provider, close_provider)
    function = c.integrated.private(function, {'verify_plan': lambda *args: plan,
        'check_loaded_sources': lambda *args: [], 'reference': lambda path: {'path': str(path)},
        'read': lambda path: {'binary': 'not_loaded'},
        'write': lambda path, value: writes.__setitem__(path.name, deepcopy(value)),
        'public': SimpleNamespace(run_admission=SimpleNamespace(open_run=lambda *args: Accepted()),
            load_native=lambda path: object()), 'InitialOwnerClient': construct,
        'close_predictor': lambda obj: {'cleanup_finished_ns': 30, 'ledger': []}})
    return lambda: function(tmp_path, 'synthetic-plan'), calls, writes


def test_worker_local_verified_branch_and_cleanup_before_verifier(tmp_path, monkeypatch):
    invoke, calls, writes = worker_fixture(tmp_path, monkeypatch, {'status': c.SAVED_PASSED}, run_row=True)
    invoke()
    assert 'worker_setup_or_loop_failure' not in writes['predictor_lifetime.json']
    assert calls.count('NEW_bound_branch') == 1
    assert calls == ['C_setup_synthetic', 'enter_branch', 'NEW_bound_branch', 'finish_branch',
        'native_acceptance_closed', 'C_close_synthetic', 'NEW_saved_verifier']
    assert writes['receipt.json']['status'] == 'completed_finite_request_cohort'
    assert writes['branch_ledger.json']['one']['status'] == 'raw_saved'


@pytest.mark.parametrize('status', ['failed_saved_audit', 'passed', 'unknown', None])
def test_worker_keeps_failed_saved_report_and_rejects_receipt(tmp_path, monkeypatch, status):
    invoke, calls, writes = worker_fixture(tmp_path, monkeypatch, {'status': status})
    with pytest.raises(ValueError, match='owned_saved_audit_not_passed'): invoke()
    assert writes['verification.json']['status'] == status and 'receipt.json' not in writes
    assert 'C_close_synthetic' in calls and writes['predictor_lifetime.json']['status'] == 'unknown_predictor_construction'
    assert 'predictor_construction_refused' in calls
    assert 'synthetic constructor' in writes['predictor_lifetime.json']['worker_setup_or_loop_failure']


def test_close_failure_never_runs_saved_verifier_or_mints_receipt(tmp_path, monkeypatch):
    invoke, calls, writes = worker_fixture(tmp_path, monkeypatch, {'status': c.SAVED_PASSED},
        close_error=ValueError('synthetic DLL drift'))
    with pytest.raises(ValueError, match='DLL drift'): invoke()
    assert 'NEW_saved_verifier' not in calls and 'receipt.json' not in writes


def test_original_unknown_denominator_can_remain_a_verified_unknown_cohort(tmp_path, monkeypatch):
    invoke, calls, writes = worker_fixture(tmp_path, monkeypatch,
        {'status': c.SAVED_PASSED, 'closed_roots': 0, 'open_or_unknown_roots': 18})
    invoke()
    assert 'predictor_construction_refused' in calls
    assert 'synthetic constructor' in writes['predictor_lifetime.json']['worker_setup_or_loop_failure']
    assert writes['verification.json']['open_or_unknown_roots'] == 18
    assert writes['receipt.json']['status'] == 'completed_finite_request_cohort'


def lifecycle_fixture(monkeypatch):
    binary = str((c.ROOT/'synthetic/not-loaded.pyd').resolve())
    dll = str((c.ROOT/'synthetic/not-loaded.dll').resolve())
    contract = {'binary': {'path': binary, 'sha256': 'b'*64},
        'runtime_dependencies': {'fake.dll': {'path': dll, 'sha256': 'd'*64},
            'API-set': {'API_set_resolution': 'descriptive only'}},
        'original_sources': {'original.py': 'f'*64}}
    identity = {'module': r.provider.MODULE, 'file': binary, 'spec_origin': binary,
        'loader_path': binary, 'loader_type': 'ExtensionFileLoader', 'binary_sha256': 'b'*64,
        'source_sha256': contract['original_sources'],
        'actual_DLLs': {'fake.dll': {'path': dll, 'sha256': 'd'*64}},
        'contract': {'schema': r.provider.SCHEMA, 'max_depth': 64, 'max_nodes': 2000000,
            'key_scan_limit': 2000000, 'headers_python': '3.11.9', 'native_simulation_authority': False}}
    files = {'synthetic': True}
    monkeypatch.setattr(r, 'verify_files', lambda value: deepcopy(files))
    row = {'status': 'closed_identity_checked', 'setup_started_ns': 1, 'load_started_ns': 2,
        'setup_finished_ns': 3, 'close_started_ns': 8, 'close_finished_ns': 9,
        'actual_entry': identity, 'actual_exit': deepcopy(identity),
        'files_entry': files, 'files_exit': deepcopy(files),
        'binding_proof': {'same_original_complete_runtime_query_proof': True},
        'direct_and_scheduler_publication_bound': True, 'actual_direct_C_supported': None,
        'actual_fallback_count': None, 'provider_includes_original_fallback': True,
        'request_preflight_or_instrumentation_added': False, 'extension_unload_claimed': False,
        'per_request_cycle_cleanup_claimed': False}
    return row, {'C_provider': contract}, {'one': {'attempt_started_ns': 4, 'attempt_finished_ns': 7}}


def test_synthetic_lifecycle_positive_is_identity_not_direct_support(monkeypatch):
    row, plan, branches = lifecycle_fixture(monkeypatch)
    result = v.provider_lifetime(row, plan, branches)
    assert result['status'] == 'passed_actual_provider_identity_with_unmeasured_fallback'
    assert result['actual_direct_C_supported'] is None and result['actual_fallback_count'] is None


@pytest.mark.parametrize('mutation', ['unclosed', 'clock_type', 'clock_reverse', 'branch_before_setup',
    'branch_after_close', 'entry_exit', 'spec_path', 'loader_path', 'DLL_path', 'DLL_hash',
    'ABI', 'source', 'direct_claim', 'fallback_claim', 'preflight', 'unload', 'cycle', 'proof'])
def test_lifecycle_negative_closed_identity_and_scope(monkeypatch, mutation):
    row, plan, branches = lifecycle_fixture(monkeypatch)
    if mutation == 'unclosed': row['status'] = 'opened'
    elif mutation == 'clock_type': row['setup_started_ns'] = True
    elif mutation == 'clock_reverse': row['load_started_ns'] = 12
    elif mutation == 'branch_before_setup': branches['one']['attempt_started_ns'] = 0
    elif mutation == 'branch_after_close': branches['one']['attempt_finished_ns'] = 10
    elif mutation == 'entry_exit': row['files_exit']['synthetic'] = False
    elif mutation in ('spec_path', 'loader_path'):
        field = 'spec_origin' if mutation == 'spec_path' else 'loader_path'
        row['actual_entry'][field] = row['actual_exit'][field] = str(c.ROOT/'wrong.pyd')
    elif mutation in ('DLL_path', 'DLL_hash'):
        field = 'path' if mutation == 'DLL_path' else 'sha256'
        row['actual_entry']['actual_DLLs']['fake.dll'][field] = 'wrong'
        row['actual_exit'] = deepcopy(row['actual_entry'])
    elif mutation == 'ABI':
        row['actual_entry']['contract']['headers_python'] = '3.12'; row['actual_exit'] = deepcopy(row['actual_entry'])
    elif mutation == 'source':
        row['actual_entry']['source_sha256'] = {}; row['actual_exit'] = deepcopy(row['actual_entry'])
    elif mutation == 'direct_claim': row['actual_direct_C_supported'] = 18
    elif mutation == 'fallback_claim': row['actual_fallback_count'] = 0
    elif mutation == 'preflight': row['request_preflight_or_instrumentation_added'] = True
    elif mutation == 'unload': row['extension_unload_claimed'] = True
    elif mutation == 'cycle': row['per_request_cycle_cleanup_claimed'] = True
    else: row['binding_proof']['same_original_complete_runtime_query_proof'] = False
    with pytest.raises((ValueError, TypeError)): v.provider_lifetime(row, plan, branches)


@pytest.mark.parametrize('bad', [None, object(), SimpleNamespace(module=object())])
def test_actual_identity_rejects_synthetic_without_loading(bad):
    with pytest.raises(ValueError, match='actual_candidate'): r.actual_identity(bad, {})


def test_runtime_open_and_close_preserve_original_exception_and_partial_log(tmp_path, monkeypatch):
    records = []
    obj = r.Provider({}, tmp_path, lambda path, value: records.append(deepcopy(value)))
    monkeypatch.setattr(r, 'verify_files', lambda value: (_ for _ in ()).throw(MemoryError('synthetic')))
    with pytest.raises(MemoryError, match='synthetic'): obj.open(c.SCHEMA)
    assert records[0]['status'] == 'unknown_setup'
    assert records[-1]['status'] == 'unknown_setup_failure'
    assert records[-1]['actual_direct_C_supported'] is None and obj.candidate is None


def test_runtime_interruption_retains_failure_without_fake_close(tmp_path):
    records = []
    obj = r.Provider({}, tmp_path, lambda path, value: records.append(deepcopy(value)))
    obj.record['status'] = 'opened'
    obj.failed(RuntimeError('synthetic interrupted'))
    assert records[-1]['status'] == 'unknown_interrupted_worker'
    assert 'close_finished_ns' not in records[-1]


def test_python_inventory_remains_exact_and_separate(monkeypatch):
    seen = []
    monkeypatch.setattr(c.previous, 'check_loaded_sources', lambda plan: seen.append(plan) or ['old.py'])
    plan = {'source_sha256': {'scripts/a.py': 'x'}, 'untouched': 1}
    assert c.check_loaded_sources(plan) == ['old.py']
    assert seen[0]['source_sha256'] == {str((c.ROOT/'scripts/a.py').resolve()): 'x'}
    assert seen[0]['untouched'] == 1 and plan['source_sha256'] == {'scripts/a.py': 'x'}


@pytest.mark.parametrize('name', ['../escape.py', 'C:/outside.py'])
def test_noncanonical_campaign_source_rejected(name):
    with pytest.raises(ValueError): c.absolute_sources({name: 'x'})


def test_launcher_original_owned600_and_no_import_side_effect():
    assert launch.main.__code__ is launch.old.main.__code__
    assert launch.main.__globals__['MODULE'].endswith('single_capture_owned_codec_campaign')
    assert launch.main.__globals__['bounded_windows_job'] is launch.old.bounded_windows_job
    assert launch.LIMIT == c.LIMIT == 600. and c.contract.BUDGET_NS == 100_000_000
    assert c.request is c.previous.request and c.scene is c.previous.scene
    assert len(c.declarations()) == 18 and c.declarations() == c.previous.declarations()


def test_saved_wrapper_preserves_failed_audit_status(monkeypatch, tmp_path):
    old_result = {'schema': 'old', 'status': 'failed_saved_audit',
        'rows': {'one': {'root': {'closed': False}, 'audit_status': 'invalid'}}}
    monkeypatch.setattr(v, 'make_namespace', lambda campaign: SimpleNamespace(
        verify_saved=lambda *args: deepcopy(old_result)))
    monkeypatch.setattr(c, 'verify_plan', lambda *args: {})
    monkeypatch.setattr(c, 'read', lambda path: {})
    monkeypatch.setattr(c, 'reference', lambda path: {'path': str(path), 'sha256': 'synthetic'})
    monkeypatch.setattr(v, 'provider_lifetime', lambda *args: {'status': 'synthetic_only'})
    result = v.verify_saved(tmp_path, 'synthetic')
    assert result['status'] == 'failed_saved_audit' and result['rows'] == old_result['rows']
    assert result['actual_direct_C_support_measured'] is False
