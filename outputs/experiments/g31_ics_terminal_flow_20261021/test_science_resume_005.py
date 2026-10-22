"""Fail-closed reuse tests with synthetic files, no native or science inputs."""
import importlib.util
import json
from pathlib import Path
import pytest

path = Path(__file__).with_name('final_science_resumable_005.py')
spec = importlib.util.spec_from_file_location('resumable_science', path)
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)

@pytest.fixture
def recovery(tmp_path):
    prior = tmp_path/'prior'; prior.mkdir()
    native = tmp_path/'native'; native.mkdir()
    def save(path, value):
        path.write_text(json.dumps(value), encoding='utf8')
        return audit.bind(path)
    source = dict(path='source', sha256='source-hash')
    workflow = dict(path='workflow', sha256='workflow-hash')
    driver = save(tmp_path/'driver.py', 'immutable producer')
    pending = save(prior/'pending.json', dict(source_bundle=source, analysis_driver=driver))
    process = save(tmp_path/'process.json', dict(closure_verified=True, direct_child_wait_completed=True,
        job_active_processes_zero_verified=True, cleanup_errors=[]))
    evidence = {name:save(native/name, {'data':name}) for name in audit.RUN_EVIDENCE_FILES}
    report = dict(parent=2201, method='C00', task_id='task', evidence=evidence,
        evidence_bound_before_consumption=True, native_starts=0, full_owner_ack_export_opened=False,
        plan_order_chain=dict(violations=[]), decision_choices=[{'choice':'HOLD'}],
        behavior=dict(decision_counts=dict(valid_decisions=1)), timing=dict(ranking_rows_truncated=False,
        ranking_rows_count=0, ranking_rows=[], all_trajectory_decisions_bound_to_digest_time_owner=True,
        validated_decision_observation_count=1))
    ref = audit.fresh(prior/'P2201_C00_behavior_timing.json.gz', report)
    manifest = dict(schema='g31.terminal_flow.science_resume.v1', source_bundle=source, workflow=workflow,
        previous_pending=pending, previous_driver=driver, previous_process=process,
        reports=[dict(parent=2201, method='C00', evidence=ref)])
    rows = {(2201,'C00'):dict(directory=native, plan=dict(task_id='task'))}
    def invoke():
        return audit.resume_reports(save(tmp_path/'resume.json', manifest), rows, source, workflow)
    return dict(manifest=manifest, report=report, rows=rows, invoke=invoke, save=save, prior=prior, native=native)

def test_valid_complete_report_is_reused_with_all_dependencies(recovery):
    reports, bindings = recovery['invoke']()
    assert reports[(2201,'C00')] == recovery['report']
    assert len(bindings) == 5

@pytest.mark.parametrize('flag', ['closure_verified','direct_child_wait_completed','job_active_processes_zero_verified'])
def test_any_unknown_process_closure_rejects_reuse(recovery, flag):
    manifest = recovery['manifest']; ref = manifest['previous_process']
    value = audit.read(ref['path']); value[flag] = False
    manifest['previous_process'] = recovery['save'](Path(ref['path']), value)
    with pytest.raises(ValueError, match='closed_process_tree'): recovery['invoke']()

def test_changed_native_input_invalidates_completed_report(recovery):
    (recovery['native']/'observations.json.gz').write_text('changed', encoding='utf8')
    with pytest.raises(ValueError, match='resume_input_changed'): recovery['invoke']()

def test_changed_original_producer_invalidates_reuse(recovery):
    Path(recovery['manifest']['previous_driver']['path']).write_text('changed', encoding='utf8')
    with pytest.raises(ValueError, match='old_driver_changed'): recovery['invoke']()

def test_duplicate_or_unregistered_report_rejected(recovery):
    recovery['manifest']['reports'] *= 2
    with pytest.raises(ValueError, match='unique_registered_run'): recovery['invoke']()

def test_successful_old_science_must_not_be_restarted(recovery):
    (recovery['prior']/'COMPLETE.json').write_text('{}', encoding='utf8')
    with pytest.raises(ValueError, match='must_not_be_rerun'): recovery['invoke']()

@pytest.mark.parametrize('mutation,match', [
    ('truncated', 'complete_decision_coverage'), ('input_missing','complete_input_binding'),
    ('wrong_task','report_identity'), ('chain_violation','chain_violation'),
    ('missing_decision','complete_decision_coverage')])
def test_semantically_partial_reports_rejected(recovery, mutation, match):
    report = recovery['report']
    if mutation == 'truncated': report['timing']['ranking_rows_truncated'] = True
    if mutation == 'input_missing': report['evidence'].pop('observations.json.gz')
    if mutation == 'wrong_task': report['task_id'] = 'another'
    if mutation == 'chain_violation': report['plan_order_chain']['violations'] = ['broken']
    if mutation == 'missing_decision': report['decision_choices'] = []
    file = recovery['prior']/'P2201_C00_behavior_timing.json.gz'
    file.unlink()
    recovery['manifest']['reports'][0]['evidence'] = audit.fresh(file, report)
    with pytest.raises(ValueError, match=match): recovery['invoke']()

def test_changed_workflow_rejected(recovery):
    recovery['manifest']['workflow'] = dict(path='different', sha256='different')
    with pytest.raises(ValueError, match='same_inputs'): recovery['invoke']()

def test_no_resume_keeps_original_fresh_execution_contract():
    assert audit.resume_reports(None, {}, {}, {}) == ({}, [])
