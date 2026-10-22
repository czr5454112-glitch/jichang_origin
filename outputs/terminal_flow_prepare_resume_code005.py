"""Prepare separate recovery code; never launch, register, or modify active producers."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
old = DATA/'final_science_audit_004.py'
new = DATA/'final_science_resumable_005.py'
source = old.read_text(encoding='utf8')
helper = '''
def resume_reports(reference, rows, source_ref, workflow_ref):
    if reference is None:
        return {}, []
    record = bound_read(reference)
    need(record['schema'] == 'g31.terminal_flow.science_resume.v1', 'resume_schema')
    need(record['source_bundle'] == source_ref and record['workflow'] == workflow_ref, 'resume_same_inputs')
    previous = bound_read(record['previous_pending'])
    need(previous['source_bundle'] == source_ref and previous['analysis_driver'] == record['previous_driver'],
         'resume_previous_producer')
    verify_bindings([record['previous_driver']], 'resume_old_driver_changed')
    closed = bound_read(record['previous_process'])
    need(closed.get('closure_verified') is True and closed.get('direct_child_wait_completed') is True
         and closed.get('job_active_processes_zero_verified') is True and not closed.get('cleanup_errors'),
         'resume_requires_closed_process_tree')
    directory = Path(record['previous_pending']['path']).resolve().parent
    need(not (directory/'COMPLETE.json').exists(), 'completed_science_must_not_be_rerun')
    reports = {}; refs = [reference, record['previous_pending'], record['previous_driver'], record['previous_process']]
    for entry in record['reports']:
        key = (entry['parent'], entry['method'])
        need(key in rows and key not in reports, 'resume_unique_registered_run')
        expected = directory/f'P{key[0]}_{key[1]}_behavior_timing.json.gz'
        need(Path(entry['evidence']['path']).resolve() == expected, 'resume_exact_report_path')
        report = bound_read(entry['evidence'])
        need((report['parent'], report['method']) == key and report['task_id'] == rows[key]['plan']['task_id'],
             'resume_report_identity')
        need(report.get('evidence_bound_before_consumption') is True and report.get('native_starts') == 0
             and report.get('full_owner_ack_export_opened') is False, 'resume_evidence_contract')
        need(set(report['evidence']) == set(RUN_EVIDENCE_FILES), 'resume_complete_input_binding')
        for name, ref in report['evidence'].items():
            need(Path(ref['path']).resolve() == (rows[key]['directory']/name).resolve(), 'resume_input_path')
            verify_bindings([ref], 'resume_input_changed')
        need(not report['plan_order_chain']['violations'], 'resume_chain_violation')
        timing = report['timing']
        need(timing['ranking_rows_truncated'] is False
             and timing['ranking_rows_count'] == len(timing['ranking_rows'])
             and timing['all_trajectory_decisions_bound_to_digest_time_owner'] is True
             and timing['validated_decision_observation_count'] == len(report['decision_choices'])
             and report['behavior']['decision_counts']['valid_decisions'] == len(report['decision_choices']),
             'resume_complete_decision_coverage')
        reports[key] = report
        refs.append(entry['evidence'])
    need(bool(reports), 'resume_requires_completed_reports')
    return reports, refs

'''
source = source.replace('def execute(rows,status,source_ref,workflow_ref,h,output,producer_ref=None):',
    helper+'def execute(rows,status,source_ref,workflow_ref,h,output,producer_ref=None,resume_ref=None):')
source = source.replace("    run_reports={};run_refs={}\n", "    cached, resume_bindings = resume_reports(resume_ref, rows, source_ref, workflow_ref)\n    run_reports={};run_refs={}\n")
source = source.replace('        report=run_audit(row,h)\n',
    "        reused = key in cached\n        report = cached.pop(key) if reused else run_audit(row,h)\n        print(json.dumps(dict(stage='run_audit_result', parent=key[0], method=key[1], reused_verified=reused)), flush=True)\n")
source = source.replace("    verify_bindings([producer_ref],'analysis_driver_changed_during_audit')", "    verify_bindings([producer_ref]+resume_bindings,'analysis_driver_or_reused_evidence_changed_during_audit')")
source = source.replace("        registered_runs=28,scientific_per_bag_pairs=24,scientific_pair_definitions=PAIRS,", "        resume_manifest=resume_ref, reused_reports_are_revalidated_not_rerun=True,\n        registered_runs=28,scientific_per_bag_pairs=24,scientific_pair_definitions=PAIRS,")
source = source.replace("    parser.add_argument('--execute',action='store_true')", "    parser.add_argument('--resume-manifest',type=Path)\n    parser.add_argument('--execute',action='store_true')")
source = source.replace('execute(rows,status,source_ref,workflow_ref,h,args.output_dir,producer_ref)',
    'execute(rows,status,source_ref,workflow_ref,h,args.output_dir,producer_ref,\n        bind(args.resume_manifest) if args.resume_manifest else None)')
with new.open('x', encoding='utf8', newline='\n') as stream:
    stream.write(source)
print(new)
