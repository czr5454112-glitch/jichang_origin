"""Unexecuted focused draft: synthetic only, no C/native/model/raw load.

The Python-only publisher fixture below does NOT satisfy accepted C authority.
Real loader/ABI/DLL tests belong to the future actual campaign. No bare sibling
test import is used, so the module closure can be resolved from these imports.
"""
from __future__ import annotations
import ast
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

from scripts.experiments.g31_ics_circulation import single_capture_static_inventory_runtime as r
from scripts.experiments.g31_ics_circulation import initial_owner_route_static_inventory_campaign as c
from scripts.experiments.g31_ics_circulation import verify_initial_owner_route_static_inventory_campaign as v
from scripts.experiments.g31_ics_circulation import launch_initial_owner_route_static_inventory_campaign as launch
from scripts.experiments.g31_ics_circulation import prepare_initial_owner_route_static_inventory_campaign as prep
from scripts.experiments.g31_ics_circulation import run_static_inventory_campaign_pure as pure


def python_live():
    publisher = r.static.owned.publisher
    raw = publisher.reference._bind_provider(publisher.owned.normalization.normalize)
    return r.static.owned._compose(publisher._compose(raw))


def record():
    return {'constructors': []}


def test_runtime_original_provider_close_failure_and_complete_globals():
    assert r.Provider.close is r.original.Provider.close
    assert r.Provider.failed is r.original.Provider.failed
    source = r.source_proof()
    assert source['accepted_C_open_code_only_private_binding_facade']
    assert source['same_C_original_fallback_counts_remain_unknown']


def test_pure_runner_only_new_test_and_actual_collection_full_globals():
    proof = pure.source_proof()
    assert proof['old49_tests_not_reexecuted']
    assert pure.TEST == prep.TEST
    assert pure.MODULE == prep.PURE_MODULE
    assert pure.WRAPPER == c.ROOT/prep.PURE_WRAPPER
    assert pure.worker.__code__ is pure.original.worker.__code__
    assert pure.main.__code__ is pure.original.main.__code__
    assert pure.Collection.pytest_collection_finish.__globals__['TEST'] == prep.TEST
    assert pure.worker.__globals__['source_files'] is pure.source_files
    assert pure.source_files.__globals__['BASE'] == prep.STATIC
    assert pure.source_files.__globals__['BASE_COUNT'] == 222


def test_composition_full_code_classcell_and_original_exact_drain():
    live, journal = python_live(), record()
    result = r.compose(live, journal)
    bound = result.static_binding
    proof = r.composition_proof(result)
    assert proof['constructor_callable_returns_reviewed_exact_class']
    assert result.run_continuation.__code__ is live.run_continuation.__code__
    assert result.run_continuation.__closure__ is live.run_continuation.__closure__
    assert result.run_continuation.__globals__['ActualAdvanceChain'] is result.constructor_timer
    assert result.constructor_timer.exact_class is bound.ActualAdvanceChain
    assert bound._actual_root_drain.__globals__['ActualAdvanceChain'] is bound.ActualAdvanceChain
    assert bound.ActualAdvanceChain.__init__.__closure__ is live.ActualAdvanceChain.__init__.__closure__
    assert result.run_branch.__globals__['publish_root'] is live.publish_root
    assert result.run_branch.__globals__['call_with_recorded_collection'] is live.call_with_recorded_collection
    assert bound.run_continuation.__globals__['ActualAdvanceChain'] is bound.ActualAdvanceChain
    assert journal['cold_bind_status'] == 'returned' and journal['constructors'] == []


@pytest.mark.parametrize('name', ['collect', 'final_revalidate_and_submit', 'observe_after_boundary', '_record', 'evidence'])
def test_original_dynamic_request_methods_unchanged(name):
    live = python_live(); result = r.compose(live, record())
    assert getattr(result.static_binding.CapturedRequest, name) is getattr(live.CapturedRequest, name)


def test_timed_constructor_preserves_arguments_exact_result_and_no_root_reference():
    calls, rows = [], []
    class Exact:
        def __init__(self, *args): calls.append(args)
    root = SimpleNamespace(request_id='synthetic', started_ns=10, deadline_ns=100000010, cutoff_ns=60000010)
    args = (object(), object(), root, {})
    clocks = iter([20, 30])
    timer = r.ConstructorTimer(Exact, rows, lambda: next(clocks))
    result = timer(*args)
    assert type(result) is Exact and calls == [args]
    assert rows == [{'ordinal': 0, 'root': vars(root).copy(), 'status': 'constructor_returned',
        'error_type': None, 'started_ns': 20, 'finished_ns': 30}]
    root.request_id = 'changed'
    assert rows[0]['root']['request_id'] == 'synthetic'
    assert set(vars(timer)) == {'exact_class', 'rows', 'clock', 'boundary'}


def test_timed_constructor_preserves_original_exception_object_and_failed_interval():
    error, rows = ValueError('actual constructor refusal'), []
    class Refused:
        def __init__(self, *args): raise error
    clocks = iter([20, 31])
    with pytest.raises(ValueError) as caught:
        r.ConstructorTimer(Refused, rows, lambda: next(clocks))(None, None, object(), {})
    assert caught.value is error
    assert rows[0]['status'] == 'constructor_raised' and rows[0]['error_type'] == 'ValueError'
    assert rows[0]['finished_ns'] == 31 and all(x is None for x in rows[0]['root'].values())


def test_constructor_wrong_return_type_is_rejected_and_recorded():
    class ForeignResult:
        def __new__(cls, *args): return object()
    rows = []; clocks = iter([20, 31])
    with pytest.raises(ValueError, match='constructor_wrong_return_type'):
        r.ConstructorTimer(ForeignResult, rows, lambda: next(clocks))(None, None, object(), {})
    assert rows[0]['status'] == 'constructor_raised' and rows[0]['failure_stage'] == 'exact_return_type'


def test_real_bound_class_rejects_fake_native_admission_and_timer_preserves_failure():
    result = r.compose(python_live(), record())
    root = object.__new__(result.static_binding.CapturedRequest)
    root.session, root.client, root.native, root.accepted = object(), object(), object(), {}
    root.request_id, root.started_ns = 'synthetic', 1
    root.deadline_ns, root.cutoff_ns = 100000001, 60000001
    with pytest.raises(ValueError, match='missing_actual_accepted_session'):
        result.constructor_timer(root.session, root.client, root, {})
    assert result.constructor_timer.rows[0]['status'] == 'constructor_raised'


@pytest.mark.parametrize('kind', ['exact_class', 'clock', 'helper_code', 'run_global'])
def test_new_timing_boundary_rejects_changed_program_before_constructor(kind):
    result = r.compose(python_live(), record()); timer = result.constructor_timer
    old = None
    try:
        if kind == 'exact_class':
            old = timer.exact_class; timer.exact_class = lambda *args: object()
        elif kind == 'clock':
            old = timer.clock; timer.clock = lambda: 1
        elif kind == 'helper_code':
            old = r._root_fields.__code__; r._root_fields.__code__ = (lambda root: {}).__code__
        else:
            old = result.run_continuation.__globals__['ActualAdvanceChain']
            result.run_continuation.__globals__['ActualAdvanceChain'] = object
        with pytest.raises(ValueError, match='static_'):
            timer(None, None, object(), {})
        assert timer.rows == []
    finally:
        if kind == 'exact_class': timer.exact_class = old
        elif kind == 'clock': timer.clock = old
        elif kind == 'helper_code': r._root_fields.__code__ = old
        else: result.run_continuation.__globals__['ActualAdvanceChain'] = old


def test_saved_two_levels_full_globals_and_passive_callback():
    namespace = v.make_namespace(c)
    assert all(not x for x in namespace.source_proof()['recursive_LOAD_GLOBAL_missing'].values())
    assert namespace.original.functions['root_replay'].__globals__['c'] is c
    assert namespace.original.functions['original_root_replay'].__globals__['c'] is c
    assert namespace.original.namespace['verify_branch'] is namespace.verify_branch
    assert namespace.original.functions['original_rpc_scope'].__globals__['c'] is c


def test_worker_inverse_fullglobals_new_import_and_original_close_status_gate():
    proof = c.source_proof(); function = c.worker_function(None, None)
    assert proof['only_new_saved_verifier_import_inverse_AST_exact']
    assert proof['accepted_C18_worker_source']['original_worker_inverse_AST_exact']
    assert v.previous.original.previous.previous.missing_globals(function) == []
    assert function.__globals__['verify_plan'] is c.verify_plan
    assert function.__globals__['check_loaded_sources'] is c.previous.check_loaded_sources
    assert 'verify_initial_owner_route_static_inventory_campaign' in function.__code__.co_names
    assert 'owned_saved_audit_not_passed' in function.__code__.co_consts
    assert launch.LIMIT == c.LIMIT == 600.
    assert launch.main.__code__ is launch.old.main.__code__
    assert launch.main.__globals__['MODULE'].endswith('.initial_owner_route_static_inventory_campaign')


def timing_fixture():
    root = {'request_id': 'one:row', 'started_ns': 100, 'deadline_ns': 100000100, 'cutoff_ns': 60000100}
    proof = {'static_inventory': {'cold_original_method_inventory_calls': 1,
        'cold_original_collection_inventory_calls': 1,
        'dynamic_session_handle_transport_owner_ACK_current_checks_removed': 0},
        'constructor_callable_returns_reviewed_exact_class': True}
    C = {'load_started_ns': 1, 'setup_finished_ns': 20, 'close_started_ns': 500,
        'binding_proof': proof}
    side = {'schema': r.SCHEMA, 'status': 'closed_identity_checked',
        'cold_bind_status': 'returned', 'cold_bind_started_ns': 2, 'cold_bind_finished_ns': 15,
        'binding_proof': copy.deepcopy(proof), 'cold_binding_charged_to_campaign': True,
        'per_root_cycle_cleanup_claimed': False, 'constructor_CPU_or_inventory_only_claimed': False,
        'no_per_root_disk_write': True, 'actual_direct_C_supported': None,
        'constructors': [{'ordinal': 0, 'root': root, 'status': 'constructor_returned',
            'error_type': None, 'started_ns': 150, 'finished_ns': 180}]}
    ledger = {'one/row': {'attempt_started_ns': 50, 'attempt_finished_ns': 400}}
    observed = {'one/row': {'envelope': copy.deepcopy(ledger['one/row']),
        'roots': [{'root_id': root['request_id'], 'root_started_ns': 100,
            'root_deadline_ns': root['deadline_ns'], 'decision_cutoff_ns': root['cutoff_ns'],
            'outside_return_ns': 250, 'has_actual_advance': True}],
        'clocks': {'root_started_ns': 100, 'result_capture_started_ns': 300},
        'root_constructed': True, 'failure': None, 'has_native_batches': True}}
    return side, C, observed, ledger


def test_saved_constructor_interval_nested_not_added_to_root():
    result = v.static_lifetime(*timing_fixture())
    assert result['constructor_rows'] == 1 and result['rows']['one/row']['wall_ms'] == 30/1e6
    assert result['cold_binding_ms'] == 13/1e6
    assert result['native_authority_from_sidecar'] is False


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'wrong_id', 'wrong_start', 'late',
    'bool_clock', 'wrong_deadline', 'wrong_cutoff', 'false_return', 'failed_cold', 'bad_projection'])
def test_saved_sidecar_negative(mutation):
    side, C, observed, ledger = timing_fixture(); row = side['constructors'][0]
    if mutation == 'missing': side['constructors'] = []
    elif mutation == 'duplicate': side['constructors'].append(copy.deepcopy(row))
    elif mutation == 'wrong_id': row['root']['request_id'] = 'other'
    elif mutation == 'wrong_start': row['root']['started_ns'] += 1
    elif mutation == 'late': row['finished_ns'] = 301
    elif mutation == 'bool_clock': row['started_ns'] = True
    elif mutation == 'wrong_deadline': row['root']['deadline_ns'] -= 1
    elif mutation == 'wrong_cutoff': row['root']['cutoff_ns'] += 1
    elif mutation == 'false_return': row['status'] = 'constructor_raised'; row['error_type'] = 'ValueError'
    elif mutation == 'failed_cold': side['cold_bind_status'] = 'failed'
    elif mutation == 'bad_projection': observed['one/row'] = {'projection_error': 'synthetic'}
    with pytest.raises(ValueError): v.static_lifetime(side, C, observed, ledger)


def test_failure_before_constructor_remains_missing_not_zero_or_success():
    side, C, observed, ledger = timing_fixture()
    side['constructors'] = []
    observed['one/row'].update(failure='actual prior failure', roots=[], has_native_batches=False)
    result = v.static_lifetime(side, C, observed, ledger)
    assert result['rows'] == {} and result['missing_before_constructor_failures'] == ['one/row']


def test_missing_raw_after_actual_attempt_keeps_unverified_constructor_not_zero():
    side, C, observed, ledger = timing_fixture()
    observed.clear(); ledger['one/row']['status'] = 'unknown_failed'
    result = v.static_lifetime(side, C, observed, ledger)
    assert result['rows'] == {}
    value = result['unverified_missing_raw_constructor_rows']['one/row']
    assert value['wall_ms'] is None and value['reported_wall_ms'] == 30/1e6


def test_unknown_unexecuted_cannot_have_constructor_sidecar():
    side, C, observed, ledger = timing_fixture()
    observed.clear(); ledger['one/row']['status'] = 'unknown_unexecuted'
    with pytest.raises(ValueError, match='unbound_constructor'): v.static_lifetime(side, C, observed, ledger)


def test_provider_adds_sidecar_only_at_original_save_sites(tmp_path):
    writes = []
    instance = r.Provider({}, tmp_path, lambda path, value: writes.append((path.name, copy.deepcopy(value))))
    assert [x[0] for x in writes] == ['C_provider_lifetime.json', 'static_inventory_lifetime.json']
    instance.failed(ValueError('synthetic interruption'))
    assert [x[0] for x in writes][-2:] == ['C_provider_lifetime.json', 'static_inventory_lifetime.json']
    assert writes[-1][1]['status'] == 'unknown_interrupted_worker'


def fake_worker(tmp_path, monkeypatch, report, *, close_error=None):
    """Execute the changed worker control flow, but refuse all real providers."""
    calls, writes = [], {}
    class Accepted:
        _closed = False
        def close(self): calls.append('native_closed'); self._closed = True; return {}
        def active_for(self, key): return True
        def enter_branch(self, *args): calls.append('enter')
        def finish_branch(self, *args): calls.append('finish')
    predictor = SimpleNamespace(ready={}, command=['fake'], started_ns=10, ready_ns=20)
    def branch(*args): calls.append('new_timed_branch'); return {'synthetic_only': True}
    provider = SimpleNamespace(run_branch=branch)
    def open_provider(*args): calls.append('cold_static_setup'); return provider
    def close_provider(value):
        assert value is provider; calls.append('provider_close')
        if close_error is not None: raise close_error
    def verify(*args):
        calls.append('new_complete_saved_checker')
        assert calls.index('provider_close') > calls.index('native_closed')
        return copy.deepcopy(report)
    monkeypatch.setattr(v, 'verify_saved', verify)
    plan = {'rows': {'one': {}}, 'row_order': ['one'],
        'native_contract_reference': {'path': 'not_loaded'}, 'semantic_gate_reference': {},
        'image': {'path': 'not_loaded', 'version': 'fake'}, 'expected_READY': {}}
    implementation = c.worker_function(open_provider, close_provider)
    implementation = c.integrated.private(implementation, {
        'verify_plan': lambda *args: plan, 'check_loaded_sources': lambda *args: [],
        'reference': lambda path: {'path': str(path)}, 'read': lambda path: {'binary': 'not_loaded'},
        'write': lambda path, value: writes.__setitem__(path.name, copy.deepcopy(value)),
        'public': SimpleNamespace(run_admission=SimpleNamespace(open_run=lambda *args: Accepted()),
            load_native=lambda path: object()), 'InitialOwnerClient': lambda *args, **kwargs: predictor,
        'close_predictor': lambda obj: {'cleanup_finished_ns': 30, 'ledger': []}})
    return lambda: implementation(tmp_path, 'synthetic-plan'), calls, writes


def test_new_worker_executes_local_timed_binding_and_full_saved_checker(tmp_path, monkeypatch):
    invoke, calls, writes = fake_worker(tmp_path, monkeypatch, {'status': c.SAVED_PASSED})
    invoke()
    assert calls == ['cold_static_setup', 'enter', 'new_timed_branch', 'finish', 'native_closed',
        'provider_close', 'new_complete_saved_checker']
    assert 'worker_setup_or_loop_failure' not in writes['predictor_lifetime.json']
    assert writes['branch_ledger.json']['one']['status'] == 'raw_saved'
    assert writes['receipt.json']['status'] == 'completed_finite_request_cohort'


@pytest.mark.parametrize('status', ['failed_saved_audit', 'unknown', None])
def test_new_worker_saves_failed_audit_without_success_receipt(tmp_path, monkeypatch, status):
    invoke, calls, writes = fake_worker(tmp_path, monkeypatch, {'status': status})
    with pytest.raises(ValueError, match='owned_saved_audit_not_passed'): invoke()
    assert writes['verification.json']['status'] == status and 'receipt.json' not in writes
    assert 'new_timed_branch' in calls


def test_new_worker_close_failure_never_reaches_saved_success(tmp_path, monkeypatch):
    error = ValueError('synthetic actual DLL identity failure')
    invoke, calls, writes = fake_worker(tmp_path, monkeypatch, {'status': c.SAVED_PASSED}, close_error=error)
    with pytest.raises(ValueError) as caught: invoke()
    assert caught.value is error and 'new_complete_saved_checker' not in calls
    assert 'receipt.json' not in writes


def test_branch_projection_failure_still_runs_original_row_checks(monkeypatch):
    calls = []
    namespace = {'verify_branch': None}
    original = SimpleNamespace(namespace=namespace, verify_saved=lambda *a: None,
        verify_branch=lambda *args, **kwargs: calls.append('original_complete_row') or {'audit_status': 'invalid'},
        source_proof=lambda: {})
    monkeypatch.setattr(v.previous, 'make_namespace', lambda campaign: original)
    bound = v.make_namespace(object())
    assert bound.verify_branch({}, {}, 'one', branch_envelope={}) == {'audit_status': 'invalid'}
    assert calls == ['original_complete_row'] and 'projection_error' in bound.observations['one']


def test_prepare_late_long_input_target_rejected_before_first_archive_write(tmp_path):
    files = {'scripts/short.py': b'pass\n'}
    with pytest.raises(ValueError, match='all_target_preflight'):
        prep.all_targets(tmp_path/'new', files, {'row_order': ['one', 'x'*260]})
    assert not (tmp_path/'new/source/scripts/short.py').exists()
    assert not (tmp_path/'new').exists()


def test_prepare_canonical_union_target_never_rewrites_current(tmp_path):
    with pytest.raises(ValueError, match='canonical_archive_key'):
        prep.all_targets(tmp_path/'new', {str(c.ROOT/'scripts/short.py'): b'pass\n'}, {'row_order': []})
    assert not (tmp_path/'new').exists()


def outer_fixture(tmp_path, monkeypatch):
    directory = tmp_path.resolve(); digest = 'd'*64
    def sha(path):
        return prep.archive.PYTHON_SHA if Path(path).resolve() == Path(sys.executable).resolve() else digest
    def ref(path): return {'path': str(Path(path).resolve()), 'sha256': sha(path)}
    monkeypatch.setattr(c, 'sha', sha); monkeypatch.setattr(c, 'reference', ref)
    command = [sys.executable, '-m', prep.PURE_MODULE, '--output', str(directory)]
    environment = {'PYTHONPATH': 'src;.;tests', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONIOENCODING': 'utf-8'}
    pins = {name: digest for name in (*prep.PURE_FIXED_SOURCES, prep.PURE_WRAPPER)}
    plan = {'output_directory': str(directory), 'command': command, 'test_file': prep.TEST,
        'shared_seconds': 120., 'environment': environment,
        'python': {'path': sys.executable, 'sha256': prep.archive.PYTHON_SHA},
        'wrapper': ref(c.ROOT/prep.PURE_WRAPPER), 'source_sha256': pins}
    zeros = {name: 0 for name in ('native_calls', 'model_predictions', 'custom_C_loads', 'actual_raw_reads')}
    receipt = dict(zeros)
    parent = {**zeros, 'command': command, 'output_directory': str(directory), 'receipt_sha256': digest,
        'status': 'passed', 'shared_seconds': 120., 'post_interpreter_before_parent_export_seconds': 9.,
        'process': {'status': 'exited', 'exitcode': 0, 'windows_job_kill_on_close': True,
            'child_released_only_after_job_assignment': True, 'wall_seconds': 8., 'hard_timeout_seconds': 118.}}
    names = ('plan.json', 'collection.json', 'receipt.json', 'tests.xml',
        'bounded_parent_receipt.json', 'worker.stdout.log', 'worker.stderr.log')
    outer = {**zeros, 'schema': 'g31.static_inventory_campaign_pure.external.v1',
        'status': 'exited_zero', 'command': command, 'cwd': str(c.ROOT.resolve()),
        'output_directory': str(directory), 'exitcode': 0, 'wrapper_exitcode': 0,
        'python_launch_attempted': True, 'fixed_source_entry_passed': True, 'fixed_source_exit_passed': True,
        'environment': environment, 'stopwatch_frequency': 10, 'elapsed_ticks': 100,
        'external_application_seconds': 10., 'wrapper_before_final_receipt_seconds': 11.,
        'clock_scope': 'immediately_before_python_launch_through_process_return_including_python_startup_and_exit',
        'outputs': {name: ref(directory/name) for name in names},
        'python_sha256': prep.archive.PYTHON_SHA, 'python_after_sha256': prep.archive.PYTHON_SHA,
        'wrapper': ref(c.ROOT/prep.PURE_WRAPPER), 'wrapper_after_sha256': digest,
        'runner': ref(c.ROOT/prep.PURE_RUNNER), 'runner_after_sha256': digest,
        'fixed_source_pins': {name: {'path': str(c.ROOT/name), 'expected_sha256': digest,
            'entry_sha256': digest, 'entry_matches': True, 'exit_sha256': digest, 'exit_matches': True}
            for name in prep.PURE_FIXED_SOURCES}}
    return directory, plan, receipt, parent, outer


def test_prepare_complete_external_command_typed_ticks_and_all_outputs(tmp_path, monkeypatch):
    prep.pure_outer_gate(*outer_fixture(tmp_path, monkeypatch))


@pytest.mark.parametrize('mutation', ['command', 'cwd', 'output', 'bool_frequency', 'bool_ticks',
    'wrong_seconds', 'missing_output', 'wrapper_exit', 'missing_pin', 'not_launched', 'unowned'])
def test_prepare_external_bound_negative(tmp_path, monkeypatch, mutation):
    values = outer_fixture(tmp_path, monkeypatch); parent, outer = values[-2:]
    if mutation == 'command': outer['command'] = ['fake']
    elif mutation == 'cwd': outer['cwd'] = 'other'
    elif mutation == 'output': outer['output_directory'] = 'other'
    elif mutation == 'bool_frequency': outer['stopwatch_frequency'] = True
    elif mutation == 'bool_ticks': outer['elapsed_ticks'] = True
    elif mutation == 'wrong_seconds': outer['external_application_seconds'] = 9.
    elif mutation == 'missing_output': del outer['outputs']['worker.stderr.log']
    elif mutation == 'wrapper_exit': outer['wrapper_after_sha256'] = 'x'*64
    elif mutation == 'missing_pin': del outer['fixed_source_pins'][prep.TEST]
    elif mutation == 'not_launched': outer['python_launch_attempted'] = False
    elif mutation == 'unowned': parent['process']['windows_job_kill_on_close'] = False
    with pytest.raises(ValueError): prep.pure_outer_gate(*values)
