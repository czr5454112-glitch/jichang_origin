"""Persistent finite research task ledger with one hard-bounded child tree.

Stages are explicitly registered before execution. No arbitrary code edits,
gate relaxation, automatic retry, or duplicate recovery are performed here.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sys
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = 'g31.sustained_learning.cycle.v1'
TOKEN = 'g31_sustained_child_v1'


def require(condition, reason):
    if not condition:
        raise ValueError('sustained_cycle:' + reason)


def now():
    return datetime.now(timezone.utc).timestamp()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def atomic(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    write_new(temporary, value)
    os.replace(temporary, path)


@contextmanager
def lock(path):
    guard = Path(str(path) + '.lock')
    # A leftover lock is evidence of an interrupted operation; never delete it
    # or assume another collector has stopped just because no receipt exists.
    handle = os.open(guard, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(handle, str(os.getpid()).encode())
        os.close(handle)
        yield
    finally:
        guard.unlink()


def initialize(path, plan):
    require(plan['schema'] == SCHEMA, 'schema')
    require(plan['max_native_branches'] == 120 and plan['max_native_per_task'] <= 12, 'native_budget')
    require(0 < plan['deadline_utc_epoch'] - plan['started_utc_epoch'] <= 43200, 'finite_cycle_budget')
    require(plan['native_parallelism'] == 1, 'single_native_collector')
    require(plan['deadline_utc_epoch'] > now(), 'cycle_expired')
    result = dict(plan, tasks={}, native_branches_reserved=0, created_at=now(), events=[])
    write_new(path, result)
    return result


def register(path, spec):
    path = Path(path)
    with lock(path):
        state = read(path)
        identity = spec['task_id']
        require(identity and all(c.isalnum() or c in '_-' for c in identity), 'task_id')
        require(identity not in state['tasks'], 'existing_task_requires_new_identity')
        require(spec['module'].startswith('scripts.experiments.g31_ics_circulation.'), 'module_scope')
        require(type(spec['args']) is list and all(type(x) is str for x in spec['args']), 'arguments')
        require(type(spec['native_branches']) is int and 0 <= spec['native_branches'] <= state['max_native_per_task'], 'task_native_budget')
        require(type(spec['hard_seconds']) in (int, float) and 0 < spec['hard_seconds'] <= 7200, 'task_wall_budget')
        require(all(key in state['tasks'] for key in spec.get('requires', [])), 'unregistered_dependency')
        source_files = {str(Path(p).resolve()) for p in spec['sources']}
        source_files.add(str(Path(__file__).resolve()))
        require(all(Path(p).is_file() for p in source_files), 'source_missing')
        require(all(Path(p).is_relative_to(ROOT) for p in source_files), 'source_outside_research_tree')
        pins = {p: sha(p) for p in sorted(source_files)}
        task = dict(spec, status='prepared', source_pins=pins, registered_at=now(), attempt=None)
        state['tasks'][identity] = task
        state['events'].append({'at': now(), 'task_id': identity, 'event': 'registered'})
        atomic(path, state)
    return task


def reserve(path, task_id):
    path = Path(path)
    with lock(path):
        state = read(path)
        task = state['tasks'][task_id]
        require(task['status'] == 'prepared', 'task_already_attempted_no_automatic_retry')
        require(not any(t['status'] == 'running' for t in state['tasks'].values()), 'existing_attempt_must_be_resolved')
        require(all(state['tasks'][key]['status'] == 'completed' for key in task.get('requires', [])), 'dependency_not_completed')
        remaining = state['deadline_utc_epoch'] - now()
        require(remaining >= task['hard_seconds'], 'insufficient_remaining_wall_budget')
        require(state['native_branches_reserved'] + task['native_branches'] <= state['max_native_branches'], 'cycle_native_budget_exhausted')
        require(all(sha(p) == expected for p, expected in task['source_pins'].items()), 'source_changed_since_registration')
        attempt_id = task_id + '_' + uuid.uuid4().hex[:12]
        output = path.parent / 'attempts' / attempt_id
        output.mkdir(parents=True, exist_ok=False)
        for index, source in enumerate(task['source_pins']):
            archive = output / 'source' / (f'{index:04d}' + Path(source).suffix)
            archive.parent.mkdir(exist_ok=True)
            archive.write_bytes(Path(source).read_bytes())
        task.update(status='running', attempt={'attempt_id': attempt_id, 'output': str(output.resolve()),
            'started_at': now(), 'parent_pid': os.getpid(), 'state': 'reserved_before_launch'})
        state['native_branches_reserved'] += task['native_branches']
        write_new(output / 'registration.json', task)
        state['events'].append({'at': now(), 'task_id': task_id, 'event': 'running_reserved', 'attempt_id': attempt_id})
        atomic(path, state)
    return task, output


def finish(path, task_id, result):
    with lock(path):
        state = read(path)
        task = state['tasks'][task_id]
        require(task['status'] == 'running', 'cannot_close_nonrunning_task')
        output = Path(task['attempt']['output'])
        write_new(output / 'receipt.json', result)
        task.update(status=result['status'], result=result, finished_at=now())
        task['attempt']['state'] = 'closed'
        state['events'].append({'at': now(), 'task_id': task_id, 'event': result['status'], 'reason': result['reason']})
        atomic(path, state)


def run_task(path, task_id):
    from .bounded_windows_job import run
    task, output = reserve(path, task_id)
    try:
        command = [sys.executable, '-m', 'scripts.experiments.g31_ics_circulation.run_sustained_learning',
                   'worker', '--registration', str(output / 'registration.json')]
        with (output / 'stdout.log').open('x', encoding='utf-8') as stdout, (output / 'stderr.log').open('x', encoding='utf-8') as stderr:
            process = run(command, timeout=task['hard_seconds'], stdout=stdout, stderr=stderr, admission=TOKEN, cwd=ROOT)
        changed = [p for p, expected in task['source_pins'].items() if sha(p) != expected]
        successful = process['status'] == 'exited' and process['exitcode'] == 0 and not changed
        assessment = None
        if successful and task.get('assessment'):
            declared = task['assessment']
            assessment_path = Path(declared['path'])
            assessment = read(assessment_path) if assessment_path.is_file() else None
            successful = isinstance(assessment, dict) and assessment.get('status') in declared['allowed_statuses']
        result = {'status': 'completed' if successful else 'failed', 'process': process,
            'reason': 'declared_process_and_artifact_checks_passed' if successful else 'process_source_or_declared_artifact_check_failed',
            'source_changed': changed, 'assessment': assessment, 'finished_at': now(),
            'native_branches_reserved': task['native_branches'], 'automatic_retries': 0,
            'note': 'Task completion is not a claim that scientific gates passed; inspect the stage assessment.'}
    except Exception as error:
        result = {'status': 'failed', 'reason': str(error), 'traceback': traceback.format_exc(),
            'finished_at': now(), 'native_branches_reserved': task['native_branches'], 'automatic_retries': 0}
    finish(path, task_id, result)
    return result


def worker(registration):
    require(sys.stdin.readline().strip() == TOKEN, 'bounded_parent_admission_required')
    task = read(registration)
    require(all(sha(p) == expected for p, expected in task['source_pins'].items()), 'worker_sources_changed')
    write_new(Path(registration).parent / 'process_started.json', {'pid': os.getpid(), 'started_at': now(),
        'attempt_id': task['attempt']['attempt_id'], 'job_assignment_completed_before_admission': True})
    sys.argv = [task['module'], *task['args']]
    sys.stdin = io.StringIO(task.get('inner_admission', '') + '\n')
    runpy.run_module(task['module'], run_name='__main__', alter_sys=True)


def summary(path):
    state = read(path)
    return {'status': 'budget_exhausted' if now() >= state['deadline_utc_epoch'] else 'active',
        'remaining_wall_seconds': max(0, state['deadline_utc_epoch'] - now()),
        'native_branches_reserved': state['native_branches_reserved'],
        'native_branches_remaining': state['max_native_branches'] - state['native_branches_reserved'],
        'tasks': {key: {'status': task['status'], 'next_action': task.get('next_action'),
                       'attempt': task['attempt']} for key, task in state['tasks'].items()},
        'recovery': 'Never auto-retry running/failed/unknown. Check recorded process and immutable attempt artifacts; register a new ID only after resolution.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'register', 'run', 'status', 'worker'])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--task', type=Path)
    parser.add_argument('--task-id')
    parser.add_argument('--registration', type=Path)
    args = parser.parse_args()
    if args.command == 'worker':
        worker(args.registration)
        return 0
    require(args.manifest is not None, 'manifest_required')
    if args.command == 'init':
        initialize(args.manifest, read(args.plan))
        result = summary(args.manifest)
    elif args.command == 'register':
        task = register(args.manifest, read(args.task))
        result = {'task_id': task['task_id'], 'status': task['status'], 'source_pin_count': len(task['source_pins'])}
    elif args.command == 'run':
        result = run_task(args.manifest, args.task_id)
    else:
        result = summary(args.manifest)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get('status') == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
