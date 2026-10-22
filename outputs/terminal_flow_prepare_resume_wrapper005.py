"""Write separate nine-task recovery supervisor; no registration or execution."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
original = ROOT/'outputs/terminal_flow_offline_budget.py'
target = ROOT/'outputs/terminal_flow_offline_resume005.py'
source = original.read_text(encoding='utf8')
source = source.replace("'final_science': ROOTDATA/'final_science_audit_004.py'", "'final_science': ROOTDATA/'final_science_resumable_005.py'")
source = source.replace("    if kind in HELPERS:\n", "    if kind == 'final_science':\n        need(len(argv) == 11 and argv[9] == '--resume-manifest'\n             and Path(argv[10]).resolve() == checked(spec['science_resume']), 'exact_science_resume_manifest')\n        argv = argv[:9]\n    if kind in HELPERS:\n")
source = source.replace("['full_train_time_scale', 'granularity', 'final_science', 'unified', 'strong_baseline']", "['final_science', 'unified', 'strong_baseline']")
source = source.replace("'fixed_eleven_tasks'", "'fixed_remaining_nine_tasks'")
helper = '''
def validate_recovery(spec):
    recovery = read(checked(spec['recovery']))
    need(recovery['schema'] == SCHEMA+'.closed_recovery', 'recovery_schema')
    prior = read(checked(recovery['previous_spec']))
    started = read(checked(recovery['started']))
    partial = read(checked(recovery['partial']))
    closing = read(checked(recovery['closure_ready']))
    need(started['spec'] == recovery['previous_spec'] and started['producer'] == prior['wrapper'], 'recovery_prior_launch')
    need(closing['runner_id'] == started['runner_id'] and partial['safe_to_close_runner'] is True,
         'recovery_prior_safe_close')
    for key in ('source_manifest', 'workflow', 'workflow_completion', 'model', 'budget', 'historical_holdback'):
        need(prior[key] == spec[key], 'recovery_unchanged_'+key)
        checked(prior[key])
    checked(prior['wrapper'])
    for ref in prior['producer_bindings']:
        checked(ref)
    events = [json.loads(line) for line in (CYCLE/'ledger.jsonl').read_text(encoding='utf8').splitlines() if line.strip()]
    own = [e for e in events if e.get('runner_id') == started['runner_id']]
    need([e['event'] for e in own] == ['runner_open', 'runner_close'], 'recovery_actual_ledger_close_required')
    need(own[0]['spec'] == recovery['previous_spec'], 'recovery_ledger_spec')
    processes = {r['task']: r['process'] for r in partial['process_reports']}
    need(len(processes) == len(partial['process_reports']) and set(processes) ==
         {'full_train_time_scale', 'granularity', 'final_science'}, 'recovery_exact_attempted_tasks')
    need([t['kind'] for t in prior['tasks'][:3]] == ['full_train_time_scale', 'granularity', 'final_science'],
         'recovery_prior_task_order')
    need(len(recovery['completed_tasks']) == 2, 'recovery_two_completed_tasks')
    for index, completed in enumerate(recovery['completed_tasks']):
        task = prior['tasks'][index]
        need(completed['task'] == task['id'] and completed['process'] == processes[task['id']], 'recovery_completed_identity')
        process = read(checked(completed['process']))
        need(child_succeeded(process), 'recovery_completed_child_not_successful')
        outputs = {Path(r['path']).resolve():r for r in completed['outputs']}
        root = Path(task['output']).resolve()
        need(len(outputs) == len(completed['outputs']) and all(p.is_relative_to(root) for p in outputs),
             'recovery_output_scope')
        need(all(root/name in outputs for name in task['required_outputs']), 'recovery_required_outputs')
        need(set(outputs) == {p.resolve() for p in root.rglob('*') if p.is_file()}, 'recovery_complete_output_inventory')
        for ref in outputs.values(): checked(ref)
        marker = read(root/'COMPLETE.json')
        need(marker['status'] == 'complete', 'recovery_complete_marker')
        checked(marker.get('final_report', marker.get('report')))
    failed = read(checked(processes['final_science']))
    need(closure_allows_close(failed) and not child_succeeded(failed), 'recovery_failed_science_closed')
    resume = read(checked(spec['science_resume']))
    old_science = prior['tasks'][2]
    need(resume['previous_process'] == processes['final_science']
         and Path(resume['previous_pending']['path']).resolve() == Path(old_science['output'])/'pending.json'
         and resume['source_bundle'] == spec['source_manifest'] and resume['workflow'] == spec['workflow'],
         'recovery_science_lineage')
    expected_driver = next(r for r in prior['producer_bindings'] if Path(r['path']).resolve() == Path(old_science['argv'][2]).resolve())
    need(resume['previous_driver'] == expected_driver, 'recovery_old_science_producer')
    # The remaining tasks keep their original semantics and output destinations,
    # except the failed science uses a fresh destination and figures follow it.
    for old, new in zip(prior['tasks'][3:], spec['tasks'][1:]):
        need(old['kind'] == new['kind'] and old['id'] == new['id'], 'recovery_remaining_task_identity')
        if old['kind'] != 'figures':
            need(old == new, 'recovery_unstarted_task_changed')
    need(len(prior['tasks'][3:]) == len(spec['tasks'][1:]), 'recovery_no_task_dropped')
    return recovery

'''
source = source.replace('def validate_spec(spec, *, require_closed=True):', helper+'def validate_spec(spec, *, require_closed=True):')
source = source.replace("    limits = read(checked(spec['budget']))", "    validate_recovery(spec)\n    limits = read(checked(spec['budget']))", 1)
source = source.replace("def verify_exit_bindings(spec, spec_ref, producer):\n", "def verify_exit_bindings(spec, spec_ref, producer):\n    validate_recovery(spec)\n")
source = source.replace("    validate_argv(task, spec)\n    raise SystemExit", "    need(task['kind'] not in ('full_train_time_scale', 'granularity'), 'completed_tasks_must_not_relaunch')\n    validate_argv(task, spec)\n    raise SystemExit")
with target.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(source)
print(target)
