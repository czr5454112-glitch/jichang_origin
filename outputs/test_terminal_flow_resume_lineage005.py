"""Synthetic recovery authorization, not a live run or ledger mutation."""
import copy
import importlib.util
import json
from pathlib import Path
import pytest

path = Path(__file__).with_name('terminal_flow_offline_resume005.py')
loader = importlib.util.spec_from_file_location('resume_wrapper_lineage', path)
w = importlib.util.module_from_spec(loader); loader.loader.exec_module(w)

@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(w, 'CYCLE', tmp_path)
    def save(name, value):
        p = tmp_path/name; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value), encoding='utf8'); return w.bind(p)
    def closed(ok=True):
        return dict(closure_verified=True, direct_child_wait_completed=True,
            job_active_processes_zero_verified=True, cleanup_errors=[], status='exited' if ok else 'hard_timeout',
            exitcode=0 if ok else 1, termination_reason=None if ok else 'timeout')
    producer = save('producer.py', 'producer'); wrapper = save('wrapper.py', 'wrapper')
    common = {key:save(key+'.json', {}) for key in
        ('source_manifest','workflow','workflow_completion','model','budget','historical_holdback')}
    tasks = []; completed = []; processes = []
    for kind in ('full_train_time_scale','granularity','final_science'):
        out = tmp_path/kind; out.mkdir()
        task = dict(id=kind,kind=kind,output=str(out),required_outputs=['COMPLETE.json'],
            argv=['python','-B',producer['path']])
        tasks.append(task)
        process = save(kind+'_process.json', closed(kind != 'final_science'))
        processes.append(dict(task=kind,process=process))
        if kind != 'final_science':
            report = save(kind+'/report.json', dict(status='complete'))
            marker = save(kind+'/COMPLETE.json', dict(status='complete',final_report=report))
            completed.append(dict(task=kind,process=process,outputs=[report,marker]))
    remaining = [dict(kind=k,id=k+str(i),output=str(tmp_path/(k+str(i)))) for i,k in enumerate(
        ['unified','strong_baseline']+['forecast_holdout']*4+['forecast_summary','figures'])]
    prior = dict(common, wrapper=wrapper, producer_bindings=[producer],tasks=tasks+remaining)
    previous_spec = save('prior_spec.json',prior)
    started = save('STARTED.json',dict(spec=previous_spec,producer=wrapper,runner_id='prior'))
    partial = save('PARTIAL.json',dict(safe_to_close_runner=True,process_reports=processes))
    closing = save('CLOSURE_READY.json',dict(runner_id='prior'))
    events = [dict(event='runner_open',runner_id='prior',spec=previous_spec),dict(event='runner_close',runner_id='prior')]
    def ledger():
        (tmp_path/'ledger.jsonl').write_text('\n'.join(json.dumps(e) for e in events), encoding='utf8')
    ledger()
    resume = save('resume.json', dict(previous_process=processes[2]['process'],
        previous_pending=dict(path=str(tmp_path/'final_science/pending.json'),sha256='unused-in-wrapper'),
        previous_driver=producer,source_bundle=common['source_manifest'],workflow=common['workflow']))
    recovery = dict(schema=w.SCHEMA+'.closed_recovery', previous_spec=previous_spec,
        started=started,partial=partial,closure_ready=closing,completed_tasks=completed)
    spec = dict(common,science_resume=resume,tasks=[copy.deepcopy(tasks[2])]+copy.deepcopy(remaining))
    def invoke():
        spec['recovery'] = save('recovery.json',recovery)
        return w.validate_recovery(spec)
    return dict(invoke=invoke,recovery=recovery,spec=spec,events=events,ledger=ledger,save=save,root=tmp_path)

def test_closed_predecessor_and_two_completed_tasks_authorize_only_remaining_work(setup):
    assert setup['invoke']()['schema'] == w.SCHEMA+'.closed_recovery'

def test_closure_ready_without_actual_ledger_close_is_rejected(setup):
    setup['events'].pop(); setup['ledger']()
    with pytest.raises(ValueError,match='actual_ledger_close'): setup['invoke']()

def test_duplicate_close_is_rejected(setup):
    setup['events'].append(setup['events'][-1]); setup['ledger']()
    with pytest.raises(ValueError,match='actual_ledger_close'): setup['invoke']()

def test_changed_model_cannot_be_hidden_as_recovery(setup):
    setup['spec']['model'] = setup['save']('other_model.json', {})
    with pytest.raises(ValueError,match='unchanged_model'): setup['invoke']()

def test_changed_completed_science_file_is_rejected(setup):
    (setup['root']/'granularity/report.json').write_text('changed',encoding='utf8')
    with pytest.raises(ValueError,match='binding_changed'): setup['invoke']()

def test_failed_completed_child_cannot_be_reused(setup):
    # Keeping the prior outer manifest bound makes tampering detectable even
    # if a new recovery record supplies an updated process hash.
    target=setup['recovery']['completed_tasks'][0]['process']
    Path(target['path']).write_text('{}',encoding='utf8')
    with pytest.raises(ValueError,match='binding_changed'): setup['invoke']()

def test_unstarted_task_semantics_cannot_change(setup):
    setup['spec']['tasks'][1]['output'] = 'changed'
    with pytest.raises(ValueError,match='unstarted_task_changed'): setup['invoke']()

def test_task_cannot_silently_disappear(setup):
    setup['spec']['tasks'].pop()
    with pytest.raises(ValueError,match='no_task_dropped'): setup['invoke']()

def test_added_unbound_completed_output_is_rejected(setup):
    (setup['root']/'granularity/extra.json').write_text('{}',encoding='utf8')
    with pytest.raises(ValueError,match='complete_output_inventory'): setup['invoke']()
