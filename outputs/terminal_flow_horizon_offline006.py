"""Explicitly admitted, sequential offline science; check-only by default.

This administrative wrapper never fits models, selects parameters, admits native
starts, repairs ledger history, or interprets a successful exit as scientific gain.
The bound specification is the only source of child argv. Windows Job ownership
and resource supervision are supplied by a separately SHA-pinned local helper.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CYCLE = ROOT/'outputs/experiments/g31_ics_joint_reposition_20261021/cycle_001'
ROOTDATA = ROOT/'outputs/experiments/g31_ics_terminal_flow_20261021'
SCHEMA = 'g31.terminal_flow.offline_budget.v1'
HELPERS = {'horizon_science': ROOTDATA/'horizon_science_006.py'}

FIGURES = ROOT/'outputs/terminal_flow_science_figures005.py'
FORECAST_SUMMARY = ROOTDATA/'forecast_holdout_summary_005.py'
HOLDOUT = 'scripts.experiments.g31_ics_circulation.foundation_airport_terminal_forecast_holdout'


def need(ok, reason):
    if not ok:
        raise ValueError('offline_budget:'+reason)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def bind(path):
    path = Path(path).resolve()
    return dict(path=str(path), sha256=digest(path))


def read(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate_json_key:'+key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique)


def checked(ref):
    need(isinstance(ref, dict) and isinstance(ref.get('sha256'), str), 'missing_frozen_binding')
    need(digest(ref['path']) == ref['sha256'], 'binding_changed:'+ref['path'])
    return Path(ref['path']).resolve()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return bind(path)


def instant(value):
    value = datetime.fromisoformat(value)
    need(value.tzinfo is not None, 'timezone_required')
    return value


def number(value, name, positive=False):
    need(type(value) in (int, float) and math.isfinite(value) and value >= 0
         and (not positive or value > 0), 'invalid_'+name)
    return value


def historical_seconds(record):
    need(record['schema'] == SCHEMA+'.historical_holdback', 'holdback_schema')
    seconds = (instant(record['cutoff_utc'])-instant(record['startup_lower_bound_utc'])).total_seconds()
    need(seconds >= 0 and record['reserve_seconds'] >= seconds, 'holdback_understates_calendar_upper_bound')
    need(record['native_seconds_subtracted'] == 0 and record['ledger_rewritten'] is False
         and record['is_measured_active_time'] is False, 'holdback_is_reserve_not_ledger_charge')
    return number(record['reserve_seconds'], 'historical_reserve')


def ledger_snapshot(path, at, *, coverage_cutoff=None):
    """Read one newline-terminated snapshot; never creates a lock or writes ledger."""
    raw = Path(path).read_bytes()
    need(not raw or raw.endswith(b'\n'), 'incomplete_ledger_snapshot')
    active, unfinished, elapsed, starts, intervals, last_when = {}, set(), 0., 0, [], None
    for row in (json.loads(line) for line in raw.splitlines() if line):
        event = row['event']
        when = instant(row['at'])
        need(when <= at, 'ledger_event_after_snapshot_clock')
        need(last_when is None or when >= last_when, 'ledger_event_clock_regression')
        last_when = when
        if event == 'runner_open':
            need(not active, 'overlapping_runner_intervals')
            active[row['runner_id']] = when
        elif event == 'runner_close':
            need(row['runner_id'] in active, 'runner_close_without_open')
            opened = active.pop(row['runner_id'])
            delta = (when-opened).total_seconds()
            need(delta >= 0, 'ledger_clock_regression')
            elapsed += delta
            intervals.append((opened, when))
        elif event == 'native_start':
            need(row['task_id'] not in unfinished, 'duplicate_native_attempt')
            unfinished.add(row['task_id']); starts += 1
        elif event == 'native_finish':
            need(row['task_id'] in unfinished, 'native_finish_without_start')
            unfinished.remove(row['task_id'])
    elapsed += sum((at-when).total_seconds() for when in active.values())
    intervals.extend((when, at) for when in active.values())
    result = dict(active_seconds=elapsed, open_runners=list(active), unfinished_native_tasks=sorted(unfinished),
                native_starts=starts, ledger_snapshot_bytes=len(raw),
                ledger_snapshot_sha256=hashlib.sha256(raw).hexdigest(), at_utc=at.isoformat())
    if coverage_cutoff is not None:
        need(coverage_cutoff.tzinfo is not None and coverage_cutoff <= at, 'invalid_coverage_cutoff')
        window = (at-coverage_cutoff).total_seconds()
        covered = sum(max(0., (min(right, at)-max(left, coverage_cutoff)).total_seconds()) for left,right in intervals)
        need(covered <= window+1e-8, 'runner_coverage_exceeds_calendar_window')
        result.update(coverage_cutoff_utc=coverage_cutoff.isoformat(), post_cutoff_calendar_seconds=window,
                      post_cutoff_runner_covered_seconds=covered,
                      post_cutoff_uncovered_calendar_seconds=max(0.,window-covered))
    return result


def evidence_bytes(roots):
    # scandir metadata avoids resolving thousands of ordinary paths per sample.
    # Every child reparse point (including Windows junctions) is rejected before
    # traversal, so unlinked descendant names cannot escape these resolved roots.
    import os
    import stat
    total, selected = 0, []
    for root in sorted({Path(p).resolve() for p in roots}, key=lambda p: len(p.parts)):
        if any(root.is_relative_to(parent) for parent in selected):
            continue
        selected.append(root)
        pending = [root]
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    need(not stat.S_ISLNK(info.st_mode) and not
                         (getattr(info, 'st_file_attributes', 0) & 0x400),
                         'evidence_symlink_or_reparse_requires_audit:'+entry.path)
                    if stat.S_ISDIR(info.st_mode): pending.append(entry.path)
                    elif stat.S_ISREG(info.st_mode): total += info.st_size
    return total


def preflight(snapshot, limits, *, offline_seconds, remaining_seconds, holdback_seconds,
              existing_bytes, reserved_bytes, free_bytes, owned_runner=None):
    need(snapshot['open_runners'] == ([] if owned_runner is None else [owned_runner]), 'runner_not_idle_or_owned')
    need(not snapshot['unfinished_native_tasks'], 'unfinished_native_attempt')
    need('post_cutoff_uncovered_calendar_seconds' in snapshot, 'dynamic_gap_snapshot_required')
    components = dict(charged_active_seconds=number(snapshot['active_seconds'], 'active'),
                      offline_reserved_seconds=number(offline_seconds, 'offline'),
                      remaining_work_reserved_seconds=number(remaining_seconds, 'remaining'),
                      historical_unmetered_holdback_seconds=number(holdback_seconds, 'holdback'))
    components['post_cutoff_uncovered_holdback_seconds'] = number(
        snapshot['post_cutoff_uncovered_calendar_seconds'], 'post_cutoff_uncovered')
    total = sum(components.values())
    need(total <= limits['active_seconds_limit'], 'active_time_budget')
    need(existing_bytes+reserved_bytes < limits['new_evidence_bytes_limit'], 'evidence_budget')
    need(free_bytes-reserved_bytes >= limits['free_space_floor_bytes'], 'disk_floor')
    return dict(**components, total_reserved_active_seconds=total,
                active_seconds_headroom=limits['active_seconds_limit']-total,
                existing_evidence_bytes=existing_bytes, reserved_evidence_bytes=reserved_bytes,
                free_bytes=free_bytes)


def validate_argv(task, spec):
    argv = task['argv']
    need(isinstance(argv, list) and all(isinstance(s, str) and s and '\x00' not in s for s in argv), 'literal_argv')
    if len(argv) > 1 and argv[1] == '-B':
        argv = [argv[0]]+argv[2:]  # The sole allowed interpreter option disables bytecode writes.
    need(Path(argv[0]).resolve() == checked(spec['python']), 'registered_python_required')
    kind = task['kind']
    if kind in HELPERS:
        need(len(argv) == 9 and Path(argv[1]).resolve() == HELPERS[kind].resolve(), 'allowed_script_argv')
        need(argv[2] == '--source-manifest' and Path(argv[3]).resolve() == checked(spec['source_manifest'])
             and argv[4] == '--workflow' and Path(argv[5]).resolve() == checked(spec['workflow'])
             and argv[6:8] == ['--execute', '--output-dir'], 'fixed_science_options')
        output = Path(argv[8]).resolve()
    elif kind == 'figures':
        need(len(argv) == 6 and Path(argv[1]).resolve() == FIGURES.resolve()
             and argv[2] == '--complete' and argv[4] == '--output-dir', 'allowed_figures_argv')
        science = next(t for t in spec['tasks'] if t['kind'] == 'final_science')
        need(Path(argv[3]).resolve() == Path(science['output'])/'COMPLETE.json', 'figures_bound_science_dependency')
        output = Path(argv[5]).resolve()
    elif kind == 'forecast_summary':
        need(len(argv) == 11 and Path(argv[1]).resolve() == FORECAST_SUMMARY.resolve()
             and argv[2] == '--model' and Path(argv[3]).resolve() == checked(spec['model'])
             and argv[4] == '--reports' and argv[9] == '--output-dir', 'allowed_forecast_summary_argv')
        expected = [Path(t['output']).resolve() for t in spec['tasks'] if t['kind'] == 'forecast_holdout']
        need(len(expected) == 4 and [Path(p).resolve() for p in argv[5:9]] == expected, 'all_four_holdouts_in_fixed_order')
        output = Path(argv[10]).resolve()
    else:
        need(kind == 'forecast_holdout' and len(argv) == 9 and argv[1:3] == ['-m', HOLDOUT], 'allowed_holdout_module')
        need(argv[3] == '--run' and argv[5] == '--model' and argv[7] == '--output', 'fixed_holdout_options')
        parent = task['parent_seed']
        need(type(parent) is int and parent in (2201, 2202, 2203, 2204), 'fixed_DEV_parent')
        need(Path(argv[4]).resolve() == CYCLE/f'runs/TF_bridge_all_005_C00_P{parent}', 'fixed_DEV_C00_holdout')
        need(Path(argv[6]).resolve() == checked(spec['model']), 'frozen_TRAIN_model_required')
        output = Path(argv[8]).resolve()
    need(output.is_relative_to(ROOTDATA) and output != ROOTDATA, 'output_in_accounted_ROOTDATA')
    need(str(output) == task['output'], 'output_argv_binding')
    need(not output.exists(), 'fresh_science_output_required:'+str(output))
    number(task['hard_seconds'], 'task_timeout', positive=True)
    need(type(task['estimated_evidence_bytes']) is int and task['estimated_evidence_bytes'] > 0, 'task_evidence_estimate')
    return output


def validate_sources(spec):
    manifest = read(checked(spec['source_manifest']))
    need(Path(manifest['root']).name == 'terminal_flow_runtime_006', 'source006_only')
    need(HOLDOUT.replace('.', '/')+'.py' in manifest['files'], 'holdout_entry_in_frozen_source')
    for relative, sha in manifest['files'].items():
        for root in (ROOT, Path(manifest['root'])):
            path = (root/relative).resolve()
            need(path.is_relative_to(root.resolve()) and digest(path) == sha, 'frozen_or_current_source_changed:'+relative)


def verify_exit_bindings(spec, spec_ref, producer):
    validate_horizon_inputs(spec)
    validate_producer_roster(spec)
    for key in ('wrapper', 'budget', 'historical_holdback', 'python', 'source_manifest', 'workflow',
                'workflow_completion', 'model', 'resource_helper', 'resource_helper_origin'):
        checked(spec[key])
    for ref in spec['producer_bindings']+[spec_ref, producer]:
        checked(ref)
    completion = read(checked(spec['workflow_completion']))
    for ref in completion['blocks']+completion['receipts']:
        checked(ref)


def validate_producer_roster(spec):
    paths = [Path(ref['path']).resolve() for ref in spec['producer_bindings']]
    need(len(paths) == len(set(paths)), 'duplicate_producer_binding')
    expected = {path.resolve() for path in HELPERS.values()} | {FIGURES.resolve(), FORECAST_SUMMARY.resolve()}
    need(expected <= set(paths), 'actual_script_missing_producer_binding')


def validate_task_roster(tasks):
    need(len(tasks) == 1 and tasks[0]['kind'] == 'horizon_science' and tasks[0]['id'] == 'horizon_science', 'single_horizon_science_task')


def validate_horizon_inputs(spec):
    registration = read(checked(spec['horizon_registration']))
    completion = read(checked(spec['horizon_completion']))
    need(spec['horizon_registration'] == spec['workflow'] and spec['horizon_completion'] == spec['workflow_completion'],
         'same_horizon_workflow_bindings')
    need(registration['schema'] == 'g31.terminal_flow.projection_horizon_workflow.v1'
         and registration['source_bundle'] == spec['source_manifest'] and registration['new_native_starts'] == 8,
         'registered_eight_horizon_runs')
    block = read(checked(registration['block']))
    need(block['parents'] == [2201,2202,2203,2204] and block['methods'] == ['TF-B1-60','TF-B1-60-H1800']
         and block['source_bundle'] == spec['source_manifest'], 'fixed_horizon_matrix')
    need(completion['registration'] == spec['workflow'] and completion['status'] == 'closed'
         and completion['all_registered_development_tasks_closed'] is True
         and len(block['task_plans']) == len(completion['receipts']) == 8, 'horizon_native_closed')
    for i,(ref,receipt_ref) in enumerate(zip(block['task_plans'],completion['receipts'])):
        plan = read(checked(ref)); receipt = read(checked(receipt_ref))
        need(Path(receipt_ref['path']).resolve() == Path(ref['path']).resolve().parent/'receipt.json'
             and receipt['plan_sha256'] == ref['sha256'] and receipt['process']['exitcode'] == 0
             and receipt['worker']['scientific_status'] == 'closed'
             and receipt['worker']['final_physical_time'] == 59400.
             and plan['method'] == block['methods'][i%2]
             and plan['parent']['parent_seed'] == block['parents'][i//2]
             and plan['parent']['split'] == 'dev' and plan['source_bundle'] == spec['source_manifest'],
             'horizon_receipt_identity_contract')
    for ref in registration['dependencies'].values(): checked(ref)
    checked(registration['driver']); checked(spec['registration_driver'])


def validate_spec(spec, *, require_closed=True):
    validate_horizon_inputs(spec)
    need(spec['schema'] == SCHEMA+'.spec' and spec['ready'] is True, 'ready_spec_required')
    need(Path(spec['cycle']).resolve() == CYCLE and Path(spec['rootdata']).resolve() == ROOTDATA, 'fixed_budget_scope')
    need(checked(spec['wrapper']) == Path(__file__).resolve(), 'bound_wrapper_required')
    limits = read(checked(spec['budget']))
    need(checked(spec['budget']) == CYCLE/'campaign_budget.json', 'original_budget_required')
    need(limits['active_seconds_limit'] == 172800 and limits['new_evidence_bytes_limit'] == 40*1024**3
         and limits['free_space_floor_bytes'] == 30*1024**3, 'unchanged_original_caps')
    holdback = read(checked(spec['historical_holdback'])); historical_seconds(holdback)
    need(holdback['basis_campaign_budget'] == spec['budget']
         and instant(holdback['startup_lower_bound_utc']) <= instant(limits['registered_at_utc']), 'conservative_startup_basis')
    with (CYCLE/'ledger.jsonl').open('rb') as stream:
        prefix = stream.read(holdback['ledger_prefix']['bytes'])
    need(hashlib.sha256(prefix).hexdigest() == holdback['ledger_prefix']['sha256'], 'historical_ledger_prefix_changed')
    validate_sources(spec)
    validate_producer_roster(spec)
    for ref in spec['producer_bindings']:
        checked(ref)
    checked(spec['resource_helper']); checked(spec['python']); checked(spec['model'])
    origin = read(checked(spec['resource_helper_origin']))
    need(checked(spec['resource_helper']) == ROOTDATA/'offline_budget_support_005/offline_owned_resource_001.py'
         and Path(origin['copy_path']).resolve() == checked(spec['resource_helper'])
         and origin['sha256'] == spec['resource_helper']['sha256'] and origin['exact_byte_copy'] is True,
         'published_resource_copy_matches_origin')
    workflow = read(checked(spec['workflow']))
    need(workflow['source_bundle'] == spec['source_manifest'], 'workflow_source_binding')
    if require_closed:
        completion = read(checked(spec['workflow_completion']))
        need(completion['registration'] == spec['workflow'] and completion['all_registered_development_tasks_closed'] is True
             and completion['TEST_unlocked'] is False, 'full_workflow_closed_required')
        for ref in completion['blocks']+completion['receipts']:
            checked(ref)
    tasks = spec['tasks']
    validate_task_roster(tasks)
    need(len({str(validate_argv(t, spec)) for t in tasks}) == len(tasks), 'distinct_fresh_outputs')
    number(spec['remaining_work_reserved_seconds'], 'remaining')
    number(spec['wrapper_overhead_seconds'], 'overhead', positive=True)
    need(spec['wrapper_overhead_seconds'] >= 120, 'cleanup_and_validation_overhead_reserved')
    need(type(spec['remaining_work_reserved_bytes']) is int and spec['remaining_work_reserved_bytes'] >= 0, 'remaining_bytes')
    need(type(spec['wrapper_estimated_evidence_bytes']) is int and spec['wrapper_estimated_evidence_bytes'] > 0, 'wrapper_bytes')
    need(type(spec['disk_guard_bytes']) is int and spec['disk_guard_bytes'] >= 512*1024**2, 'disk_growth_guard')
    return limits, holdback


def load_helper(reference, name):
    module_spec = importlib.util.spec_from_file_location(name, checked(reference))
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def closure_allows_close(report):
    return (report.get('closure_verified') is True and report.get('direct_child_wait_completed') is True
            and report.get('job_active_processes_zero_verified') is True and not report.get('cleanup_errors'))


def child_succeeded(report):
    return (closure_allows_close(report) and report.get('status') == 'exited' and report.get('exitcode') == 0
            and not report.get('termination_reason'))


def reserve(spec):
    return (sum(t['hard_seconds'] for t in spec['tasks'])+spec['wrapper_overhead_seconds'],
            sum(t['estimated_evidence_bytes'] for t in spec['tasks'])+spec['wrapper_estimated_evidence_bytes'])


def snapshot(*, coverage_cutoff=None):
    return ledger_snapshot(CYCLE/'ledger.jsonl', datetime.now(timezone.utc), coverage_cutoff=coverage_cutoff)


def checked_preflight(spec, limits, holdback, *, owned_runner=None, offline_seconds=None):
    seconds, size = reserve(spec)
    return preflight(snapshot(coverage_cutoff=instant(holdback['cutoff_utc'])), limits,
        offline_seconds=seconds if offline_seconds is None else offline_seconds,
        remaining_seconds=spec['remaining_work_reserved_seconds'], holdback_seconds=historical_seconds(holdback),
        existing_bytes=evidence_bytes([CYCLE, ROOTDATA]),
        reserved_bytes=size+spec['remaining_work_reserved_bytes'], free_bytes=shutil.disk_usage(CYCLE).free,
        owned_runner=owned_runner)


def execute(spec_path, directory):
    # Only bootstrap bindings, idle state and numerical admission precede runner_open.
    # Heavy source hashes, imports, child work and all reports are inside the interval.
    producer = bind(__file__); spec_ref = bind(spec_path); spec = read(checked(spec_ref))
    need(spec['schema'] == SCHEMA+'.spec' and spec['ready'] is True, 'ready_spec_required')
    need(checked(spec['wrapper']) == Path(__file__).resolve(), 'bound_wrapper_required')
    need(checked(spec['budget']) == CYCLE/'campaign_budget.json', 'original_budget_required')
    limits, holdback = read(checked(spec['budget'])), read(checked(spec['historical_holdback']))
    initial = checked_preflight(spec, limits, holdback)
    initial_native_starts = snapshot()['native_starts']
    directory = Path(directory).resolve()
    need(directory.is_relative_to(ROOTDATA) and directory != ROOTDATA and not directory.exists(), 'fresh_wrapper_output')
    sys.path.insert(0, str(ROOT))
    from scripts.experiments.g31_ics_circulation import foundation_airport_joint_budget as budget
    runner = 'terminal-flow-offline-'+secrets.token_hex(12)
    budget.append(CYCLE, 'runner_open', runner_id=runner, purpose='offline_final_science', spec=spec_ref)
    began = time.monotonic(); total_seconds, _ = reserve(spec)
    safe_to_close, reports, failure = True, [], None
    try:
        directory.mkdir(parents=True)
        save(directory/'STARTED.json', dict(schema=SCHEMA+'.execution', spec=spec_ref, producer=producer,
             runner_id=runner, preflight=initial, native_starts_requested=0))
        validate_spec(spec)
        checked_preflight(spec, limits, holdback, owned_runner=runner)
        resource = load_helper(spec['resource_helper'], 'terminal_offline_owned_resource')
        resource.validate_policy(spec['resource_policy'])
        need(spec['resource_policy']['cancel_below']['disk_free_bytes'] >= limits['free_space_floor_bytes'], 'resource_disk_floor')
        need(spec['resource_policy']['closure_wait_seconds']*2+spec['resource_policy']['sample_seconds'] < spec['wrapper_overhead_seconds'],
             'cleanup_allowance')
        for index, task in enumerate(spec['tasks']):
            checked(spec_ref); checked(producer)
            need(time.monotonic()-began < total_seconds-spec['wrapper_overhead_seconds']/2, 'wrapper_time_reserve')
            attempt = directory/task['id']; attempt.mkdir()
            token = secrets.token_hex(24)
            command = [spec['python']['path'], '-B', str(Path(__file__).resolve()), '--gated-child',
                       str(spec_path), '--task-index', str(index), '--admission', token]
            def cancel(_report):
                if time.monotonic()-began >= total_seconds-spec['wrapper_overhead_seconds']/2:
                    return 'offline_total_timeout_reserving_cleanup'
                state = snapshot(coverage_cutoff=instant(holdback['cutoff_utc']))
                if state['open_runners'] != [runner] or state['unfinished_native_tasks']:
                    return 'runner_or_native_state_changed'
                if (state['active_seconds']+historical_seconds(holdback)+state['post_cutoff_uncovered_calendar_seconds']
                        +spec['remaining_work_reserved_seconds']+60 >= limits['active_seconds_limit']):
                    return 'active_budget_cleanup_margin'
                if evidence_bytes([CYCLE, ROOTDATA])+spec['remaining_work_reserved_bytes']+spec['disk_guard_bytes'] >= limits['new_evidence_bytes_limit']:
                    return 'evidence_budget_guard'
                if shutil.disk_usage(CYCLE).free < limits['free_space_floor_bytes']+spec['remaining_work_reserved_bytes']+spec['disk_guard_bytes']:
                    return 'disk_floor_guard'
                return None
            def before_release():
                checked(spec_ref); checked(producer)
                need(cancel({}) is None, 'release_resource_preflight')
            safe_to_close = False
            with (attempt/'stdout.log').open('x', encoding='utf-8') as stdout, (attempt/'stderr.log').open('x', encoding='utf-8') as stderr:
                timeout = min(task['hard_seconds'], total_seconds-(time.monotonic()-began)-spec['wrapper_overhead_seconds']/2)
                need(timeout > 0, 'total_timeout_before_launch')
                report = resource.run(command, timeout=timeout, stdout=stdout, stderr=stderr,
                    admission=token, cwd=str(ROOT), directory=attempt, policy=spec['resource_policy'],
                    cancel_probe=cancel, before_release=before_release)
            safe_to_close = closure_allows_close(report)
            reports.append(dict(task=task['id'], process=bind(attempt/'process_closed.json')))
            need(child_succeeded(report), 'child_failed_or_tree_unclosed:'+task['id'])
            for name in task['required_outputs']:
                path = (Path(task['output'])/name).resolve()
                need(path.is_relative_to(Path(task['output'])) and path.is_file(), 'missing_science_output:'+str(path))
            for ref in spec['producer_bindings']+[spec['resource_helper'], spec['source_manifest'], spec['model'], spec_ref, producer]:
                checked(ref)
        validate_sources(spec)
        verify_exit_bindings(spec, spec_ref, producer)
        need(snapshot()['native_starts'] == initial_native_starts, 'offline_must_not_admit_native')
        preflight(snapshot(coverage_cutoff=instant(holdback['cutoff_utc'])), limits,
            offline_seconds=0, remaining_seconds=spec['remaining_work_reserved_seconds'],
            holdback_seconds=historical_seconds(holdback), existing_bytes=evidence_bytes([CYCLE, ROOTDATA]),
            reserved_bytes=spec['remaining_work_reserved_bytes'], free_bytes=shutil.disk_usage(CYCLE).free,
            owned_runner=runner)
        need(time.monotonic()-began <= total_seconds, 'offline_total_allowance_exceeded_during_exit_checks')
        save(directory/'EXECUTED.json', dict(schema=SCHEMA+'.execution', status='all_children_exited_zero',
             scientific_claims_not_inferred=True, spec=spec_ref, process_reports=reports))
    except BaseException as exc:
        failure = type(exc).__name__+':'+str(exc)
        if directory.exists():
            save(directory/'PARTIAL.json', dict(schema=SCHEMA+'.execution', status='partial', error=failure,
                safe_to_close_runner=safe_to_close, process_reports=reports, outputs_retained=True))
        raise
    finally:
        if safe_to_close:
            if directory.exists():
                save(directory/'CLOSURE_READY.json', dict(runner_id=runner, status='children_closed_ready_to_close_interval',
                     failure=failure, ledger_before_close=snapshot(coverage_cutoff=instant(holdback['cutoff_utc'])),
                     historical_holdback=spec['historical_holdback'],
                     actual_runner_close_must_be_verified_in_ledger=True))
            budget.append(CYCLE, 'runner_close', runner_id=runner)
        # Unknown closure deliberately leaves the interval open for explicit dead-runner recovery.


def gated_child(args):
    # No campaign import before the gate, and the actual task gets another fresh interpreter.
    need(sys.stdin.readline().rstrip('\n') == args.admission, 'stdin_gate')
    spec = read(args.gated_child)
    need(type(args.task_index) is int and 0 <= args.task_index < len(spec['tasks']), 'task_index')
    task = spec['tasks'][args.task_index]
    validate_argv(task, spec)
    raise SystemExit(subprocess.run(task['argv'], cwd=str(ROOT), shell=False, check=False).returncode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spec', type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--seal-template', type=Path, help='Freeze the two explicitly pending input bindings; no execution or ledger write')
    parser.add_argument('--gated-child', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--task-index', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--admission', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.gated_child:
        gated_child(args)
    if args.seal_template:
        need(not args.execute and args.output is not None, 'seal_requires_fresh_output_without_execute')
        spec = read(args.seal_template)
        need(spec['schema'] == SCHEMA+'.spec' and spec['ready'] is False, 'pending_template_required')
        for key in ('model', 'workflow_completion'):
            need(spec[key]['sha256'] is None, 'only_pending_bindings_may_be_sealed')
            spec[key] = bind(spec[key]['path'])
        # No command/timeout/cost parameter is changed by sealing.
        spec['template'] = bind(args.seal_template)
        spec['ready'] = True
        print(json.dumps(save(args.output, spec), indent=2))
        return
    need(args.spec is not None, 'spec_required')
    if args.execute:
        need(args.output is not None, 'execute_output_required')
        execute(args.spec.resolve(), args.output)
    else:
        spec = read(args.spec); limits, holdback = validate_spec(spec)
        print(json.dumps(dict(mode='read_only_check', ledger_mutated=False,
             preflight=checked_preflight(spec, limits, holdback)), indent=2))


if __name__ == '__main__':
    main()
