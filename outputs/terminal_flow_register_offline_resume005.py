"""Explicit post-timeout registration, never run until predecessor is closed.

Reuse only completed, fully bound per-run reports; do not repeat completed TRAIN
or granularity work. This writes a fresh spec but never executes it.
"""
from pathlib import Path
import copy
import importlib.util
import json

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def main():
    w=load(ROOT/'outputs/terminal_flow_offline_resume005.py','resume_registration')
    a=load(DATA/'final_science_resumable_005.py','resume_science_registration')
    prior_path=DATA/'offline_budget_spec_005_ready_004.json'
    prior=w.read(prior_path)
    execution=DATA/'offline_budget_execution_005_004'
    partial=w.read(execution/'PARTIAL.json')
    process=w.read(execution/'final_science/process_closed.json')
    w.need(w.closure_allows_close(process) and process['status']=='hard_timeout'
           and process['termination_reason']=='original_job_timeout', 'only_closed_registered_timeout_recovery')
    w.need(not w.snapshot()['open_runners'] and not w.snapshot()['unfinished_native_tasks'], 'idle_before_registration')
    w.need([p['task'] for p in partial['process_reports']]==['full_train_time_scale','granularity','final_science'],
           'only_expected_partial_recovery')
    old_output=Path(prior['tasks'][2]['output'])
    reports=[]; incomplete=[]
    for path in sorted(old_output.glob('P*_behavior_timing.json.gz')):
        try:
            report=a.read(path)
        except (EOFError,OSError,ValueError) as error:
            incomplete.append(dict(evidence=w.bind(path),reason=type(error).__name__,retained=True));continue
        reports.append(dict(parent=report['parent'],method=report['method'],evidence=w.bind(path)))
    previous_driver=next(r for r in prior['producer_bindings'] if Path(r['path']).name=='final_science_audit_004.py')
    resume=dict(schema='g31.terminal_flow.science_resume.v1',source_bundle=prior['source_manifest'],workflow=prior['workflow'],
        previous_pending=w.bind(old_output/'pending.json'),previous_driver=previous_driver,
        previous_process=w.bind(execution/'final_science/process_closed.json'),reports=reports,
        incomplete_files_retained_not_reused=incomplete,reason='original_3600_second_cap_exceeded; no_science_gate_relaxed')
    # Validate all cached identities and input SHA values before sealing them.
    workflow=w.read(w.checked(prior['workflow'])); rows={}
    for stage in workflow['stages']:
        if stage['phase'] not in a.PHASES: continue
        block=w.read(w.CYCLE/'terminal_flow'/stage['name']/'block.json')
        for ref in block['task_plans']:
            plan=w.read(w.checked(ref));key=(plan['parent']['parent_seed'],plan['method'])
            rows[key]=dict(plan=plan,directory=Path(ref['path']).parent)
    resume_path=DATA/'science_resume_manifest_005_001.json'
    resume_ref=w.save(resume_path,resume)
    a.resume_reports(resume_ref,rows,prior['source_manifest'],prior['workflow'])
    completed=[]
    for task in prior['tasks'][:2]:
        completed.append(dict(task=task['id'],process=w.bind(execution/task['id']/'process_closed.json'),
            outputs=[w.bind(p) for p in sorted(Path(task['output']).rglob('*')) if p.is_file()]))
    recovery=dict(schema=w.SCHEMA+'.closed_recovery',previous_spec=w.bind(prior_path),
        started=w.bind(execution/'STARTED.json'),partial=w.bind(execution/'PARTIAL.json'),
        closure_ready=w.bind(execution/'CLOSURE_READY.json'),completed_tasks=completed,
        native_starts_added=0,all_old_outputs_retained=True,failed_attempt_charged_to_original_ledger=True)
    recovery_ref=w.save(DATA/'offline_recovery_lineage_005_005.json',recovery)
    spec=copy.deepcopy(prior)
    spec.update(wrapper=w.bind(ROOT/'outputs/terminal_flow_offline_resume005.py'),
        recovery=recovery_ref,science_resume=resume_ref,reason_pending='Explicit closed-timeout continuation with verified completed-report reuse')
    spec.pop('template',None)
    spec['tasks']=spec['tasks'][2:]
    science=spec['tasks'][0]
    science['argv'][2]=str(DATA/'final_science_resumable_005.py')
    old_science_output=science['output']
    science['output']=str(DATA/'final_science_005_resumed_001')
    science['argv']=[science['output'] if arg==old_science_output else arg for arg in science['argv']]
    science['argv']+=['--resume-manifest',str(resume_path)]
    science['hard_seconds']=14400
    figures=spec['tasks'][-1]
    figures['argv']=[str(Path(science['output'])/'COMPLETE.json') if arg==str(Path(old_science_output)/'COMPLETE.json') else arg for arg in figures['argv']]
    spec['producer_bindings'] += [w.bind(DATA/'final_science_resumable_005.py')]
    spec['recovery_registration_driver']=w.bind(__file__)
    # Reserve the mandatory four-native 600-bin extension and its service audit;
    # this is reservation only, not authorization to launch concurrently.
    spec['remaining_work_reserved_seconds']=4*2400+3600
    spec['remaining_work_reserved_bytes']=4*536870912+128*1024**2
    limits,holdback=w.validate_spec(spec)
    preflight=w.checked_preflight(spec,limits,holdback)
    w.save(DATA/'offline_budget_preflight_005_005.json',dict(mode='read_only_check',ledger_mutated=False,preflight=preflight))
    reference=w.save(DATA/'offline_budget_spec_005_ready_005.json',spec)
    print(json.dumps(dict(spec=reference,reused_reports=len(reports),completed_prior_tasks=2,
        tasks_to_execute=9,preflight=preflight),indent=2))

if __name__=='__main__': main()
