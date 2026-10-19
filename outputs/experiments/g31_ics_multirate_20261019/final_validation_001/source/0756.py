import ast
import io
import json
from pathlib import Path
import threading

import pytest

from scripts.experiments.g31_ics_circulation import run_compatible_initial_native as subject


def test_first9_starts_with_failed_case_without_expanding_domain():
    original = [case + '/' + arm for case in subject.online.CASES for arm in subject.FIRST_ARMS]
    actual = subject.first9_order()
    assert actual[0] == 'no_overlap/incumbent'
    assert len(actual) == len(set(actual)) == 9 and set(actual) == set(original)
    assert actual[1:] == [key for key in original if key != actual[0]]


def test_traceback_schedule_calls_synchronously_from_python_thread(monkeypatch):
    calls = []
    stream = io.StringIO()
    def dump(**kwargs):
        calls.append((threading.get_ident(), kwargs))
    monkeypatch.setattr(subject.faulthandler, 'dump_traceback', dump)
    assert subject.dump_due_traceback(19.9, 20., stream) == 20.
    assert not calls
    assert subject.dump_due_traceback(20., 20., stream) == 40.
    assert calls == [(threading.get_ident(), {'file': stream, 'all_threads': True})]
    assert subject.dump_due_traceback(39.9, 40., stream) == 40.
    assert len(calls) == 1
    assert subject.dump_due_traceback(42., 40., stream) == 62.
    assert len(calls) == 2


def test_runner_never_registers_asynchronous_C_watchdog():
    syntax = ast.parse(Path(subject.__file__).read_bytes())
    calls = {node.func.attr for node in ast.walk(syntax)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert 'dump_traceback_later' not in calls
    assert 'cancel_dump_traceback_later' not in calls
    assert 'dump_traceback' in calls


def test_remaining_subset_is_exact_disjoint_registered_twelve():
    remaining = subject.remaining12_order()
    first = subject.first9_order()
    assert len(remaining) == len(set(remaining)) == 12
    assert not set(remaining) & set(first)
    assert set(remaining) | set(first) == set(subject.online.rows())


def test_remaining_prepare_rejects_unknown_prior_audit(tmp_path):
    audit = tmp_path / 'audit.json'
    subject.write(audit, {'all9_execution_closed': False})
    with pytest.raises(ValueError, match='prior_first9_audit_incomplete'):
        subject.prior_first9_evidence(tmp_path, audit)


def test_prior_evidence_recheck_detects_changed_bytes(tmp_path):
    evidence = tmp_path / 'evidence.json'
    subject.write(evidence, {'status': 'assessed'})
    plan = {'prior_first9': {'evidence_sha256': {str(evidence): subject.online.old.sha(evidence)}}}
    subject.check_prior_evidence(plan)
    subject.write(evidence, {'status': 'unknown'})
    with pytest.raises(ValueError, match='prior_evidence_changed'):
        subject.check_prior_evidence(plan)


def test_remaining_twelve_has_own_budget_and_stops_first_failure(tmp_path, monkeypatch):
    remaining = subject.remaining12_order()
    subject.write(tmp_path / 'preregistered_protocol.json', {'rows': subject.online.rows(),
        'phase': 'remaining12', 'branch_order': remaining, 'hard_group_seconds': 780.,
        'component_contract': subject.online.dispatch.compatibility.CONTRACT})
    calls = []
    def failure(command, **kwargs):
        calls.append((command, kwargs['timeout']))
        return {'status': 'exited', 'exitcode': 7, 'wall_seconds': 1.}
    monkeypatch.setattr(subject.bounded_windows_job, 'run', failure)
    subject.launch(tmp_path)
    receipt = subject.online.old.read(tmp_path / 'receipt.json')
    assert len(calls) == 1 and calls[0][1] == 60.
    assert receipt['status'] == 'remaining12_stopped_with_unknowns'
    assert receipt['scheduled_cell_count'] == 12 and receipt['actual_cell_attempts'] == 1
    assert not receipt['all_scheduled_cells_assessed'] and not receipt['full_online21_completed']
    started = subject.online.old.read(tmp_path / 'launch_started.json')
    assert started['hard_group_seconds'] == 780.
    matrix = subject.online.old.read(tmp_path / 'execution_matrix.json')
    assert all(matrix[key]['status'] == 'unknown_unexecuted' for key in subject.first9_order())


@pytest.mark.parametrize('phase', ['first9', 'remaining12'])
@pytest.mark.parametrize('failure', [
    {'status': 'exited', 'exitcode': 7}, {'status': 'hard_timeout', 'exitcode': 0}])
def test_last_written_assessment_cannot_hide_process_failure(tmp_path, monkeypatch, phase, failure):
    order = subject.first9_order() if phase == 'first9' else subject.remaining12_order()
    subject.write(tmp_path / 'preregistered_protocol.json', {'rows': subject.online.rows(),
        'phase': phase, 'branch_order': order, 'hard_group_seconds': 600. if phase == 'first9' else 780.,
        'component_contract': subject.online.dispatch.compatibility.CONTRACT})
    calls = []
    def execute(command, **kwargs):
        key = command[command.index('--key') + 1]
        calls.append(key)
        subject.write(tmp_path / (key + '.cell.json'), {'status': 'assessed'})
        return failure if key == order[-1] else {'status': 'exited', 'exitcode': 0}
    monkeypatch.setattr(subject.bounded_windows_job, 'run', execute)
    subject.launch(tmp_path)
    receipt = subject.online.old.read(tmp_path / 'receipt.json')
    matrix = subject.online.old.read(tmp_path / 'execution_matrix.json')
    assert calls == order and receipt['actual_cell_attempts'] == len(order)
    assert not receipt['all_scheduled_cells_assessed']
    assert receipt['status'] == phase + '_stopped_with_unknowns'
    assert matrix[order[-1]]['status'] == 'unknown_process_' + failure['status']
    assert matrix[order[-1]]['child_assessment_status'] == 'assessed'
    assert subject.online.old.read(tmp_path / (order[-1] + '.cell.json'))['status'] == 'assessed'
    assert subject.online.old.read(tmp_path / 'early_stop.json')['trigger_cell'] == order[-1]


def test_hard_timeout_stops_first9_and_preserves_unknown_issuance(tmp_path, monkeypatch):
    rows = subject.online.rows()
    first = [case + '/' + arm for case in subject.online.CASES for arm in subject.FIRST_ARMS]
    subject.write(tmp_path / 'preregistered_protocol.json', {'rows': rows, 'branch_order': first,
        'component_contract': subject.online.dispatch.compatibility.CONTRACT})
    invocations = []
    def timeout(command, **kwargs):
        invocations.append(command)
        assert kwargs['timeout'] == 60.
        return {'status': 'hard_timeout', 'exitcode': 0, 'pid': 123,
            'hard_timeout_seconds': 60., 'wall_seconds': 60.}
    monkeypatch.setattr(subject.bounded_windows_job, 'run', timeout)
    subject.launch(tmp_path)
    matrix = json.loads((tmp_path / 'execution_matrix.json').read_text())
    assert len(invocations) == 1
    assert matrix[first[0]]['status'] == 'unknown_process_hard_timeout'
    assert matrix[first[0]]['native_session_attempted'] is None
    assert all(matrix[key]['status'] == 'unknown_unexecuted' for key in first[1:])
    assert (tmp_path / (first[0] + '.started.json')).exists()
    assert not (tmp_path / (first[1] + '.started.json')).exists()
    receipt = json.loads((tmp_path / 'receipt.json').read_text())
    assert receipt['actual_cell_attempts'] == 1
    assert receipt['status'] == 'first9_stopped_with_unknowns'


def test_closed_process_with_failed_business_also_stops(tmp_path, monkeypatch):
    rows = subject.online.rows()
    first = [case + '/' + arm for case in subject.online.CASES for arm in subject.FIRST_ARMS]
    subject.write(tmp_path / 'preregistered_protocol.json', {'rows': rows, 'branch_order': first,
        'component_contract': subject.online.dispatch.compatibility.CONTRACT})
    def failed(command, **kwargs):
        key = command[command.index('--key') + 1]
        subject.write(tmp_path / (key + '.cell.json'), {'status': 'unknown_missing_owner_initial_proposal'})
        return {'status': 'exited', 'exitcode': 0}
    monkeypatch.setattr(subject.bounded_windows_job, 'run', failed)
    subject.launch(tmp_path)
    receipt = json.loads((tmp_path / 'receipt.json').read_text())
    assert receipt['actual_cell_attempts'] == 1 and not receipt['full_online21_completed']
