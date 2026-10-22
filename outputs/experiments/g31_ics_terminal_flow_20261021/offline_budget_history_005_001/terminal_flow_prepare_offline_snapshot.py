"""One-time read-only-ledger preparation, never invokes the execution wrapper."""
from datetime import datetime, timezone
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
module = importlib.util.spec_from_file_location('offline_budget_preparation', ROOT/'outputs/terminal_flow_offline_budget.py')
w = importlib.util.module_from_spec(module); module.loader.exec_module(w)
CYCLE, DATA = w.CYCLE, w.ROOTDATA
workflow_path = CYCLE/'terminal_flow/workflow_005/registration.json'
workflow = w.read(workflow_path)
limits = w.read(CYCLE/'campaign_budget.json')
for _ in range(4):
    raw = (CYCLE/'ledger.jsonl').read_bytes()
    cutoff = datetime.now(timezone.utc)
    snapshot = w.ledger_snapshot(CYCLE/'ledger.jsonl', cutoff)
    if snapshot['ledger_snapshot_sha256'] == hashlib.sha256(raw).hexdigest():
        break
else:
    raise RuntimeError('ledger changed during read-only snapshot; retry explicitly')

start = datetime.fromisoformat(limits['registered_at_utc'])
history = dict(schema=w.SCHEMA+'.historical_holdback',
    startup_lower_bound_utc=start.isoformat(), cutoff_utc=cutoff.isoformat(),
    reserve_seconds=(cutoff-start).total_seconds(), basis_campaign_budget=w.bind(CYCLE/'campaign_budget.json'),
    startup_basis='Original budget registration is an earlier conservative bound; actual terminal-flow startup UTC was not recorded.',
    actual_task_startup_timestamp_known=False, native_seconds_subtracted=0, ledger_rewritten=False,
    is_measured_active_time=False, may_double_count_metered_native_and_offline_wall_time=True,
    concurrent_preparation_inside_native_runner_already_covered_by_wall_time=True,
    CPU_seconds_not_added=True, scope='Upper bound on potentially unmetered activity through cutoff; not proof all offline work lacked metering.',
    post_cutoff_rule='Use charged wrappers for heavy offline work. Concurrent preparation inside an existing native interval adds no CPU debit. Any newly uncovered interval needs a new explicit conservative record.',
    ledger_prefix=dict(path=str(CYCLE/'ledger.jsonl'), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()),
    original_ledger_snapshot=snapshot)
history_ref = w.save(DATA/'offline_historical_holdback_005_001.json', history)

python = w.bind(Path('C:/PROGRAMING/python3.11.9/python.exe'))
source = workflow['source_bundle']; workflow_ref = w.bind(workflow_path)
model = dict(path=str(DATA/'forecast_full_train_001/model.json'), sha256=None)
task_defs = [
    ('granularity', 'granularity_005_full_001', 1800, 128, ['COMPLETE.json', 'granularity_report.json']),
    ('final_science', 'final_science_005_001', 3600, 512, ['COMPLETE.json', 'final_science_report.json']),
    ('unified', 'unified_orders_005_001', 1800, 512, ['COMPLETE.json', 'unified_order_summary.json']),
    ('strong_baseline', 'strong_baseline_service_005_001', 300, 128, ['COMPLETE.json', 'strong_baseline_service_report.json']),
    ('forecast_holdout', 'forecast_full_train_DEV_holdout_005_001', 900, 64, ['evaluation.json', 'provenance.json', 'evaluation_records.json.gz']),
    ('figures', 'final_science_figures_005_001', 300, 32, ['COMPLETE.json', 'J_relative_to_C00.png', 'known_completion_harm.png']),
]
tasks = []
for kind, name, seconds, mib, required in task_defs:
    output = DATA/name
    if kind in w.HELPERS:
        tail = [str(w.HELPERS[kind]), '--source-manifest', source['path'], '--workflow', str(workflow_path), '--execute', '--output-dir', str(output)]
    elif kind == 'forecast_holdout':
        tail = ['-m', w.HOLDOUT, '--run', str(CYCLE/'runs/TF_bridge_all_005_C00_P2201'), '--model', model['path'], '--output', str(output)]
    else:
        tail = [str(w.FIGURES), '--complete', str(DATA/'final_science_005_001/COMPLETE.json'), '--output-dir', str(output)]
    tasks.append(dict(id=kind, kind=kind, argv=[python['path'], '-B']+tail, output=str(output),
                      hard_seconds=seconds, estimated_evidence_bytes=mib*1024**2, required_outputs=required))
resource_path = ROOT/'outputs/experiments/g31_ics_inventory_spi_20261020/cycle_001/report_support/offline_owned_resource_001.py'
policy = dict(job_commit_limit_bytes=8*1024**3,
    launch_minimum=dict(physical_available_bytes=10*1024**3, commit_available_bytes=12*1024**3, disk_free_bytes=32*1024**3),
    cancel_below=dict(physical_available_bytes=2*1024**3, commit_available_bytes=4*1024**3, disk_free_bytes=30*1024**3+512*1024**2),
    cancel_combination='(physical_low AND commit_low) OR disk_low', sample_seconds=1., consecutive_low_samples=1,
    closure_wait_seconds=15.)
spec = dict(schema=w.SCHEMA+'.spec', ready=False, reason_pending='Exact full-TRAIN model and closed workflow completion hashes await their genuine artifacts.',
    cycle=str(CYCLE), rootdata=str(DATA), python=python, wrapper=w.bind(w.__file__), budget=w.bind(CYCLE/'campaign_budget.json'),
    historical_holdback=history_ref, source_manifest=source, workflow=workflow_ref,
    workflow_completion=dict(path=str(workflow_path.parent/'completion.json'), sha256=None), model=model,
    producer_bindings=[w.bind(path) for path in list(w.HELPERS.values())+[w.FIGURES]],
    resource_helper=w.bind(resource_path), resource_policy=policy, tasks=tasks,
    wrapper_overhead_seconds=300, wrapper_estimated_evidence_bytes=64*1024**2, disk_guard_bytes=512*1024**2,
    remaining_work_reserved_seconds=0, remaining_work_reserved_bytes=0,
    remaining_scope='Final-only execution requires closed native workflow, so no remaining native reservation; original unused quotas are not new work.',
    stage_does_not_fit_or_select_any_model=True, TEST_opened=False)
w.validate_producer_roster(spec)
for task in tasks:
    if task['kind'] != 'forecast_holdout':
        w.validate_argv(task, spec)
spec_ref = w.save(DATA/'offline_budget_spec_005_pending_001.json', spec)

campaign_path = ROOT/'scripts/experiments/g31_ics_circulation/foundation_airport_transport_campaign.py'
tree = ast.parse(campaign_path.read_text(encoding='utf-8'))
methods = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == 'METHODS' for t in n.targets))
calibration = w.read(CYCLE/'runtime_calibration_001.json')
rows = [json.loads(line) for line in raw.splitlines() if line]
closed = {r['task_id'] for r in rows if r['event'] == 'native_finish'
          and r.get('process_status') == 'completed' and r.get('scientific_status') == 'closed'}
remaining = []
for stage in workflow['stages']:
    for parent in stage['parents']:
        for method in methods[stage['phase']]:
            task = f"TF_{stage['name']}_{method}_P{parent}"
            if task not in closed:
                remaining.append(dict(task_id=task, status='active' if task in snapshot['unfinished_native_tasks'] else 'not_closed',
                    hard_seconds=720. if stage['phase']=='export_gate' else calibration['hard_seconds'],
                    estimated_evidence_bytes=128*1024**2 if stage['phase']=='export_gate' else calibration['estimated_evidence_bytes']))
fit_pending = not (workflow_path.parent/'training_fit_receipt.json').exists()
native_reserve = sum(x['hard_seconds'] for x in remaining)
remaining_time = native_reserve+(workflow['fit_active_seconds_allowance'] if fit_pending else 0)
remaining_bytes = sum(x['estimated_evidence_bytes'] for x in remaining)+(workflow['fit_estimated_evidence_bytes'] if fit_pending else 0)
offline_time, offline_bytes = w.reserve(spec)
total = snapshot['active_seconds']+history['reserve_seconds']+remaining_time+offline_time
evidence = w.evidence_bytes([CYCLE, DATA]); free = shutil.disk_usage(CYCLE).free
w.need((CYCLE/'ledger.jsonl').read_bytes().startswith(raw), 'ledger_prefix_changed_during_read_only_preparation')
report = dict(schema=w.SCHEMA+'.preparation', status='prepared_not_executed', recorded_at_utc=cutoff.isoformat(),
    snapshot=snapshot, historical_holdback=history_ref, pending_spec=spec_ref,
    producer=w.bind(__file__), wrapper=w.bind(w.__file__), tests=w.bind(ROOT/'outputs/test_terminal_flow_offline_budget.py'),
    pure_test_result=w.bind(DATA/'offline_budget_pure_tests_006.xml'), pure_tests_passed=29,
    remaining_native_tasks=remaining, remaining_native_count=len(remaining), remaining_native_full_hard_seconds=native_reserve,
    pending_fit_seconds=workflow['fit_active_seconds_allowance'] if fit_pending else 0,
    conservative_calculation=dict(charged_active_seconds=snapshot['active_seconds'],
        historical_potentially_unmetered_holdback_seconds=history['reserve_seconds'],
        remaining_native_plus_fit_seconds=remaining_time, final_offline_reserved_seconds=offline_time,
        total_seconds=total, limit_seconds=limits['active_seconds_limit'], headroom_seconds=limits['active_seconds_limit']-total,
        satisfies_time_cap=total<=limits['active_seconds_limit']),
    disk_calculation=dict(observed_existing_cycle_plus_ROOTDATA_bytes=evidence, remaining_work_reserved_bytes=remaining_bytes,
        offline_reserved_bytes=offline_bytes, total_reserved_evidence_bytes=evidence+remaining_bytes+offline_bytes,
        evidence_limit_bytes=limits['new_evidence_bytes_limit'], free_bytes=free,
        free_after_reserved_new_bytes=free-remaining_bytes-offline_bytes, floor_bytes=limits['free_space_floor_bytes'],
        satisfies_evidence_cap=evidence+remaining_bytes+offline_bytes<limits['new_evidence_bytes_limit'],
        satisfies_free_floor=free-remaining_bytes-offline_bytes>=limits['free_space_floor_bytes'],
        filesystem_sizes_are_observed_during_live_native_writes_not_atomic_snapshot=True),
    actual_wrapper_admission_performed=False, currently_idle=not snapshot['open_runners'] and not snapshot['unfinished_native_tasks'],
    ledger_mutated_by_preparation=False, original_ledger_prefix_unchanged=True, no_source_or_native_changes=True,
    no_scientific_reports_generated=True, native_starts_requested=0,
    limitations=['Historical reserve deliberately double counts metered wall time and possibly original campaign time before this task.',
                 'Open native tasks retain their entire hard bound in addition to active time already charged.',
                 'This numerical snapshot is not permission to run alongside the active native chain; runtime repeats idle and resource checks.',
                 'Pending full-TRAIN model and workflow completion must be sealed before wrapper execution.'])
reference = w.save(DATA/'offline_budget_preparation_005_001.json', report)
print(json.dumps(dict(report=reference, time=report['conservative_calculation'], disk=report['disk_calculation']), indent=2))
