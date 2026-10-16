"""Saved-fixture/pure campaign tests. No native constructor or prediction."""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import pytest
from test_g31_circulation_live_obligation_lifecycle_v2 import raw, validate
from scripts.experiments.g31_ics_circulation import research_live_obligation_recollection as c
from scripts.experiments.g31_ics_circulation import launch_live_obligation_recollection as launch
from scripts.experiments.g31_ics_circulation import verify_live_obligation_recollection as saved


def supplied_fixture():
    """Unit-only adaptation of old endpoints, never a new native result."""
    data = deepcopy(raw('mechanism/vector_25'))
    data['collection_attempts'] = {'A': [], 'B': []}
    for owner in ('A', 'B'):
        d = data['decisions'][owner][0]
        d['collection'].update(recollection_index=0, policy_quiet_since=d['collection']['at'])
        info = validate('mechanism/vector_25', owner)
        assert info['status'] == 'conditional_validated_later_v3_data'
        info.update(native_read=d['information']['native_read'],
            status='conditional_native_delivered_later_v3_model_input', native_delivery_verified=True,
            online_information_delivered=True, conditional_stability_only=True,
            current_state_certified=False, native_protection_certified=False)
        # Actual NativeCollectionAttempt exports mapping data through JSON;
        # this unit fixture must use the same string-key representation.
        info = c.prior.json_value(info)
        d['information'] = info; d['final_local_guard_reason'] = None
        attempt = {k: deepcopy(d[k]) for k in ('at', 'phase', 'collection', 'information',
                   'actual_local_view', 'predecision_call_prefix_count')}
        attempt.update(retry_admission={'status': 'not_admitted', 'reason': 'actual_failed_owner_read_required'},
                       disposition='final_decision_no_more_recollection')
        data['collection_attempts'][owner].append(attempt)
    return data


def assessed_rows():
    rows = c.prior.probe_rows()
    for row in rows.values():
        row['status'] = 'assessed'
        row['summary'] = {'status': 'assessed', 'business_complete': True,
            'all_required_inputs_verified': True, 'selected_actions_executed': True,
            'completion': {job: 10. for job in c.prior.model.JOBS}}
    return rows


def test_private_native_function_keeps_old_bytecode_and_globals():
    assert c._native_branch.__code__ is c.prior._run_branch.__code__
    assert c._native_branch.__globals__ is c._private
    assert c._private is not vars(c.prior)
    assert c._private['OwnerPolicy'] is c.policy.OwnerPolicy
    assert c._private['adapter'] is c.adapter
    assert c._private['owner_first_action'].__code__ is c.prior.owner_first_action.__code__
    assert c.prior._run_branch.__globals__['OwnerPolicy'] is c.prior.OwnerPolicy
    assert c.prior._run_branch.__globals__['adapter'] is c.prior.adapter


def test_complete_supplied_endpoint_and_physical_replay_fixture():
    result = saved.verify_saved(supplied_fixture())
    assert result['attempts'] == result['final_decisions'] == result['verified_final_inputs'] == 2
    assert result['fresh_pairs'] == 0
    assert result['common_horizon_complete'] is True
    assert result['five_jobs_physically_complete'] is True
    assert result['physical_audit']['status'] == 'passed'


@pytest.mark.parametrize('change', ['missing_owner', 'missing_attempt', 'third_attempt', 'bool_index',
    'changed_information', 'changed_now', 'future_call', 'missing_decision', 'changed_target',
    'fake_admission', 'missing_native_read', 'wrong_peer', 'wrong_quiet_start', 'fake_retry',
    'missing_physical_job', 'changed_storage', 'changed_completion'])
def test_saved_audit_rejects_tampered_missing_or_misbound_evidence(change):
    data = supplied_fixture(); a = data['collection_attempts']['B'][0]
    if change == 'missing_owner': del data['collection_attempts']['A']
    elif change == 'missing_attempt': data['collection_attempts']['A'] = []
    elif change == 'third_attempt': data['collection_attempts']['B'] *= 3
    elif change == 'bool_index': a['collection']['recollection_index'] = False
    elif change == 'changed_information': a['information']['bundle']['trays']['P']['node'] = 99
    elif change == 'changed_now': a['at'] += .01
    elif change == 'future_call': data['calls'][0]['at'] = 100.
    elif change == 'missing_decision': data['decisions']['B'] = []
    elif change == 'changed_target': a['collection']['trigger_tray']['generation'] += 1
    elif change == 'fake_admission': a['retry_admission'] = {'status': 'conditional_retry_admissible'}
    elif change == 'missing_native_read': del a['information']['native_read']['actual_endpoints']
    elif change == 'wrong_peer': a['collection']['peer_message'] = 'other'
    elif change == 'wrong_quiet_start': a['collection']['policy_quiet_since'] += .01
    elif change == 'fake_retry': a['disposition'] = 'one_fresh_pair_requested'; a['new_request_id'] = 'fake'
    elif change == 'missing_physical_job': data['result']['jobs'].pop()
    elif change == 'changed_storage':
        next(x for x in data['result']['receipts'] if x['event'] == 'STORAGE_RELEASE')['time'] += .01
    else: data['result']['jobs'][0]['completed_at'] += .001
    with pytest.raises((ValueError, KeyError, AssertionError)): saved.verify_saved(data)


def test_unknown_row_cannot_complete_either16_or32_reference():
    rows = assessed_rows(); result = c.comparisons(rows)
    assert result['row_count'] == 96
    for case in c.CASE_ORDER:
        assert result['cases'][case]['full32_finite_optimum'] is not None
        assert all(r['member_count'] == r['assessed_members'] == 16 for r in result['cases'][case]['references'].values())
    rows['mechanism/vector_00']['status'] = 'unknown_failed'
    result = c.comparisons(rows)['cases']['mechanism']
    assert result['full32_finite_optimum'] is None
    assert all(ref['best_key'] is None for ref in result['references'].values())
    assert result['unknown'] == 1 and result['rows_vs_incumbent']['mechanism/vector_00']['strict_protected'] is None


def test_small_positive_delta_is_not_relaxed_and_old_solver_mapping_absent():
    rows = assessed_rows(); rows['mechanism/vector_25']['summary']['completion']['blocker'] += .001
    result = c.comparisons(rows)
    assert result['cases']['mechanism']['rows_vs_incumbent']['mechanism/vector_25']['strict_protected'] is False
    assert result['old_model_selection_mapping'] == 'not_reused_after_message_policy_change'
    assert result['online_solver_executed'] is False


@pytest.mark.parametrize('change', ['late_changed_payload', 'late_reordered_clock', 'duplicate_terminal', 'bool_terminal'])
def test_whole_history_and_terminal_identity_are_checked_after_decisions(change):
    data = supplied_fixture()
    if change == 'late_changed_payload':
        call = deepcopy(data['calls'][0]); call['at'] = 40.
        call['request']['expiry'] = 99.; data['calls'].append(call)
        with pytest.raises(ValueError, match='whole_immutable_request'): saved.verify_call_history(data)
    elif change == 'late_reordered_clock':
        data['calls'][-1]['at'] = -1.
        with pytest.raises(ValueError, match='whole_call_chronology'): saved.verify_call_history(data)
    elif change == 'duplicate_terminal':
        receipt = next(r for r in data['result']['receipts'] if r['event'] == 'UNLOAD_COMPLETE')
        data['result']['receipts'].append(deepcopy(receipt))
        with pytest.raises(ValueError, match='actual_terminal_receipt'): saved.verify_terminal_receipts(data)
    else:
        data['result']['jobs'][0]['completed_at'] = True
        with pytest.raises(ValueError, match='actual_terminal_receipt'): saved.verify_terminal_receipts(data)


@pytest.mark.parametrize('change', ['missing', 'extra', 'reorder', 'action', 'case'])
def test_all96_order_and_actions_are_closed(change):
    rows = assessed_rows()
    if change == 'missing': rows.pop(c.ORDER[-1])
    elif change == 'extra': rows['extra'] = deepcopy(next(iter(rows.values())))
    elif change == 'reorder': rows = dict(reversed(list(rows.items())))
    elif change == 'action': rows[c.ORDER[0]]['vector']['return_delay'] = .25
    else: rows[c.ORDER[0]]['case'] = 'other'
    with pytest.raises(ValueError): c.comparisons(rows)


def test_success_export_is_json_only_even_when_values_have_capability_attributes():
    class Capability(dict):
        def __deepcopy__(self, memo): raise RuntimeError('must not clone native capability')
    attempt = Capability(status='unknown', information={'raw': [1]}); attempt.session = object()
    policies = {'A': SimpleNamespace(collection_attempts=[attempt]), 'B': SimpleNamespace(collection_attempts=[])}
    result = c.export_attempts({'native027_acceptance': {}, 'summary': {'status': 'unknown'}}, {'policies': policies})
    assert type(result['collection_attempts']['A'][0]) is dict
    assert not hasattr(result['collection_attempts']['A'][0], 'session')
    assert result['communication_policy']['old_prediction_conformance_assumed'] is False


def test_exception_exports_actual_prefix_without_result_at_or_reconstruction(monkeypatch):
    calls = []
    class Session:
        physical_time = 2.
        def offline_diagnostics(self): calls.append('const'); return {'time': 2.}
        def result_at(self, time): pytest.fail('exception path cannot advance result_at')
    def fail(*args, progress, **kwargs):
        progress.update(session=Session(), policies={'A': SimpleNamespace(collection_attempts=[{'status': 'observed'}],
            decisions=[], exchanges=[], quiet_periods=[], accepted=SimpleNamespace(audit_copy=lambda: {}))})
        raise RuntimeError('intentional unit exception')
    monkeypatch.setattr(c, '_native_branch', fail)
    result = c.run_branch(object(), {}, {}, {}, accepted_run=object(), branch_key='case')
    assert result['partial'] is True and result['summary']['strict_protected'] is None
    assert result['collection_attempts'] == {'A': [{'status': 'observed'}], 'B': []}
    assert result['physical_time'] == result['physical_time_after_diagnostics'] == 2.
    assert calls == ['const'] and result['collection_attempt_export'] == 'all_recorded_attempts_json_only'


def test_one_unserializable_attempt_preserves_other_owner_and_stays_unknown():
    policies = {'A': SimpleNamespace(collection_attempts=[{'valid': 1}]),
                'B': SimpleNamespace(collection_attempts=[{'not_json': object()}])}
    result = c.export_attempts({'summary': {'status': 'assessed'}}, {'policies': policies})
    assert result['partial'] is True and result['summary']['status'] == 'unknown_failed_partial'
    assert result['collection_attempts']['A'] == [{'valid': 1}]
    assert 'collection_attempts_B' in result['capture_errors']


@pytest.mark.parametrize('status,exitcode,receipt', [('hard_timeout', -1, False), ('exited', 1, False), ('exited', 0, False)])
def test_owned_shared_budget_failure_or_missing_receipt_never_claims_completed(tmp_path, monkeypatch, status, exitcode, receipt):
    seen = []
    def fake(command, **kwargs):
        seen.append((command, kwargs)); return {'status': status, 'exitcode': exitcode,
            'windows_job_kill_on_close': True, 'hard_timeout_seconds': 600.}
    monkeypatch.setattr(launch.bounded_windows_job, 'run', fake)
    with pytest.raises(SystemExit): launch.launch(tmp_path)
    assert len(seen) == 1 and seen[0][1]['timeout'] == 600.
    assert '--worker' in seen[0][0] and '--admission' in seen[0][0]
    assert c.read(tmp_path/'external_process.json')['no_native_success_claim'] is True
    with pytest.raises(FileExistsError): launch.launch(tmp_path)


def test_owned_job_dispatch_error_keeps_claim_and_failure(tmp_path, monkeypatch):
    def fail(*args, **kwargs): raise OSError('unit process creation failure')
    monkeypatch.setattr(launch.bounded_windows_job, 'run', fail)
    with pytest.raises(OSError): launch.launch(tmp_path)
    assert c.read(tmp_path/'external_process.json')['status'] == 'launch_failed'
    assert (tmp_path/'launch_claim.json').exists()


def test_worker_requires_closed_plan_before_native_load(tmp_path, monkeypatch):
    c.write(tmp_path/'preregistered_protocol.json', {'rows': c.prior.probe_rows()})
    c.write(tmp_path/'prepare_receipt.json', {'plan_sha256': '0'*64})
    monkeypatch.setattr(c.prior.bound, 'load_native', lambda *args: pytest.fail('bad plan must not load native'))
    with pytest.raises(ValueError, match='plan_identity'): c.worker(tmp_path)
    assert (tmp_path/'worker_claim.json').exists()


def test_shared_deadline_is_fixed_not_extended_by_rows_or_errors():
    assert c.HARD_TIMEOUT == 600.
    assert len(c.ORDER) == 96 and c.ORDER == list(c.prior.probe_rows())
    assert c.prior.return_earliest(6.88, .5, 0) == 7.84
